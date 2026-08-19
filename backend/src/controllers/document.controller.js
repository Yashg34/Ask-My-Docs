const Document = require('../models/Document.model');
const aiClient = require('../lib/aiClient');
const FormData = require('form-data');
const crypto = require('crypto');

exports.uploadDocument = async (req, res) => {
    let docId = null;

    try {
        if (!req.file) {
            return res.status(400).json({ error: "No file uploaded." });
        }

        // Calculate file hash for deduplication
        const fileHash = crypto.createHash('sha256').update(req.file.buffer).digest('hex');
        
        // Check if user already uploaded this exact file
        const existingDoc = await Document.findOne({ owner: req.user.id, fileHash: fileHash });
        if (existingDoc) {
            return res.status(200).json({
                message: "Document already exists.",
                document: existingDoc
            });
        }

        // 1. Create a tracking record in MongoDB (Status: PROCESSING)
        const newDoc = await Document.create({
            filename: req.file.originalname,
            originalName: req.file.originalname,
            fileHash: fileHash,
            owner: req.user.id,
            status: 'PROCESSING'
        });

        docId = newDoc._id;

        // 2. Prepare the payload for FastAPI
        const formData = new FormData();
        formData.append('file', req.file.buffer, req.file.originalname);
        formData.append('document_id', newDoc._id.toString());

        // 3. Forward to FastAPI
        const fastApiResponse = await aiClient.post('/ingest', formData, {
            headers: {
                ...formData.getHeaders()
            },
            _userId: req.user.id
        });

        // 4. Update the document with the FastAPI job_id and return 202 Accepted
        const updatedDoc = await Document.findByIdAndUpdate(
            newDoc._id,
            { jobId: fastApiResponse.data.job_id },
            { returnDocument: 'after' }
        );

        return res.status(202).json({
            message: "Document ingestion started.",
            document: updatedDoc
        });

    } catch (error) {
        if (docId) {
            await Document.findByIdAndUpdate(docId, { 
                status: 'FAILED',
                errorMessage: error.message
            });
        }
        
        if (!res.headersSent) {
            res.status(500).json({ error: 'Server error during document upload' });
        }
    }
};

exports.checkDocumentStatus = async (req, res) => {
    try {
        // Security: Ensure doc.owner matches req.user.id to prevent IDOR vulnerability
        const doc = await Document.findOne({ _id: req.params.id, owner: req.user.id });
        if (!doc) {
            return res.status(404).json({ error: "Document not found" });
        }
        
        // If it's already finished processing, just return it
        if (doc.status !== 'PROCESSING') {
            return res.status(200).json({ document: doc });
        }
        
        if (!doc.jobId) {
            return res.status(200).json({ document: doc });
        }

        // Query FastAPI for background job status
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
        res.status(500).json({ error: 'Server error checking status' });
    }
};