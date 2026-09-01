const Document = require('../models/Document.model');
const aiClient = require('../lib/aiClient');
const FormData = require('form-data');
const crypto = require('crypto');
const { streamIngestStatus } = require('../services/statusStream');

// Returns 202 as soon as the DB record exists and hands ingestion to FastAPI in
// the background (no disk staging); status polling never re-submits.
exports.uploadDocument = async (req, res) => {
    let docId = null;

    try {
        if (!req.file) {
            return res.status(400).json({ error: { code: 400, message: "No file uploaded." } });
        }

        const fileHash = crypto.createHash('sha256').update(req.file.buffer).digest('hex');

        // Dedup only against a COMPLETED doc. A stuck PROCESSING or FAILED row
        // must not block a re-upload, so we supersede it and start fresh.
        const existingDoc = await Document.findOne({ owner: req.user.id, fileHash: fileHash }).sort({ createdAt: -1 });
        if (existingDoc && existingDoc.status === 'COMPLETED') {
            return res.status(200).json({
                message: "Document already exists.",
                document: existingDoc
            });
        }

        if (existingDoc) {
            await Document.updateOne(
                { _id: existingDoc._id },
                { status: 'FAILED', errorMessage: 'Superseded by a new upload of the same file.' }
            );
            console.log(`♻️ Superseded previous attempt ${existingDoc._id} (status ${existingDoc.status}) for a fresh upload`);
        }

        const newDoc = await Document.create({
            filename: req.file.originalname,
            originalName: req.file.originalname,
            fileHash: fileHash,
            owner: req.user.id,
            status: 'PROCESSING'
        });

        docId = newDoc._id;

        // Fire-and-forget ingestion; a rejected file just marks the doc FAILED.
        _ingestInBackground(newDoc, req.file.buffer, req.user.id)
            .catch((e) => console.error(`⏳ ingestion task crashed (${newDoc._id}):`, e));

        return res.status(202).json({
            message: "Document ingestion started. Processing runs in the background.",
            document: newDoc
        });

    } catch (error) {
        if (docId) {
            await Document.findByIdAndUpdate(docId, {
                status: 'FAILED',
                errorMessage: error.message
            }, { returnDocument: 'after' });
        }

        if (!res.headersSent) {
            res.status(500).json({ error: { code: 500, message: 'Server error during document upload' } });
        }
    }
};

// Background hand-off to FastAPI /ingest. Stores the job_id when accepted;
// marks the doc FAILED if the AI service is unreachable so it never stays PROCESSING.
async function _ingestInBackground(doc, fileBuffer, ownerId) {
    try {
        const formData = new FormData();
        formData.append('file', fileBuffer, doc.originalName || doc.filename);
        formData.append('document_id', doc._id.toString());

        const resp = await aiClient.post('/ingest', formData, {
            headers: { ...formData.getHeaders() },
            _userId: ownerId,
        });

        await Document.findByIdAndUpdate(
            doc._id,
            { jobId: resp.data.job_id },
            { returnDocument: 'after' }
        );
        console.log(`✅ Handed ${doc._id} to FastAPI (job ${resp.data.job_id})`);

        // Relay real-time ingestion status from FastAPI to the frontend via
        // Socket.IO (FastAPI SSE -> this relay -> doc room).
        streamIngestStatus(doc._id.toString(), resp.data.job_id, ownerId);

    } catch (e) {
        console.error(`⏳ Failed to start ingestion for ${doc._id}:`, e.message);
        await Document.findByIdAndUpdate(doc._id, {
            status: 'FAILED',
            errorMessage: `Could not start ingestion: ${e.message}`
        }, { returnDocument: 'after' });
    }
}

exports.checkDocumentStatus = async (req, res) => {
    try {
        // Ensure the doc belongs to the requesting user (prevents IDOR).
        const doc = await Document.findOne({ _id: req.params.id, owner: req.user.id });
        if (!doc) {
            return res.status(404).json({ error: { code: 404, message: "Document not found" } });
        }

        // Nothing to poll if not processing or not yet handed to FastAPI.
        if (doc.status !== 'PROCESSING' || !doc.jobId) {
            return res.status(200).json({ document: doc });
        }

        try {
            const fastApiResponse = await aiClient.get(`/ingest/status/${doc.jobId}`, {
                _userId: req.user.id
            });
            const jobData = fastApiResponse.data;

            if (jobData.status === 'COMPLETED') {
                doc.status = 'COMPLETED';
                await doc.save();
            } else if (jobData.status === 'FAILED') {
                doc.status = 'FAILED';
                doc.errorMessage = jobData.errorMessage || "Unknown ingestion error";
                await doc.save();
            }

            return res.status(200).json({ document: doc, message: jobData.message });
        } catch (fastApiError) {
            console.error("❌ Failed to query FastAPI status:", fastApiError.message);
            return res.status(200).json({ document: doc, error: "Status check temporarily unavailable" });
        }

    } catch (error) {
        console.error("❌ Error checking document status:", error);
        res.status(500).json({ error: { code: 500, message: 'Server error checking status' } });
    }
};
