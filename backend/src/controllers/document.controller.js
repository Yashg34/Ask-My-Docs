const Document = require('../models/Document.model');
const axios = require('axios');
const FormData = require('form-data');

exports.uploadDocument = async (req, res) => {
    let docId = null;

    try {
        if (!req.file) {
            return res.status(400).json({ error: "No file uploaded." });
        }

        // 1. Create a tracking record in MongoDB (Status: PROCESSING)
        const newDoc = await Document.create({
            filename: req.file.originalname,
            originalName: req.file.originalname,
            owner: req.user.id,
            status: 'PROCESSING'
        });

        docId = newDoc._id;

        // 2. Prepare the payload for FastAPI
        const formData = new FormData();
        formData.append('file', req.file.buffer, req.file.originalname);
        formData.append('document_id', newDoc._id.toString());

        // 3. Forward to FastAPI
        const fastApiResponse = await axios.post('http://127.0.0.1:8000/ingest', formData, {
            headers: {
                ...formData.getHeaders(),
                'x_user_id': req.user.id
            }
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
        const doc = await Document.findById(req.params.id);
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
            const fastApiResponse = await axios.get(`http://127.0.0.1:8000/ingest/status/${doc.jobId}`);
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