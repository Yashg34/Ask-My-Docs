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
        formData.append('user_id', req.user.id);
        formData.append('document_id', newDoc._id.toString());

        // 3. Forward to FastAPI AND WAIT for it to finish (Synchronous)
        try {
            const fastApiResponse = await axios.post('http://127.0.0.1:8000/ingest', formData, {
                headers: {
                    ...formData.getHeaders(),
                }
            });

            // 4. Update MongoDB status to COMPLETED
            const updatedDoc = await Document.findByIdAndUpdate(
                newDoc._id, 
                { status: 'COMPLETED' },
                { new: true }
            );
            
            // 5. Send the final success response to the frontend
            return res.status(200).json({
                message: "Document successfully processed and indexed!",
                document: updatedDoc,
                ai_response: fastApiResponse.data
            });

        } catch (fastApiError) {
            console.error("❌ FastAPI Ingestion Failed:", fastApiError.message);
            await Document.findByIdAndUpdate(newDoc._id, { 
                status: 'FAILED',
                errorMessage: fastApiError.message
            });
            return res.status(500).json({ error: "AI Engine failed to process the document." });
        }

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