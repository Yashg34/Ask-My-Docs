const QueryRecord = require('../models/QueryRecord.model');
const aiClient = require('../lib/aiClient');

exports.askQuery = async (req, res) => {
    try {
        const { query, documentId } = req.body;

        if (!query || !query.trim()) {
            return res.status(400).json({ error: "Query cannot be empty." });
        }

        // 1. Prepare the payload for FastAPI
        const payload = {
            query: query,
            top_k: 10,
            top_n: 3,
            threshold: 0.05
        };

        // If querying a specific document
        if (documentId) {
            payload.document_id = documentId;
        }

        // 2. Hit the FastAPI /query route
        const fastApiResponse = await aiClient.post('/query', payload, {
            _userId: req.user.id
        });
        const aiData = fastApiResponse.data;

        // 3. Save the history in MongoDB (Persistence)
        const newRecord = await QueryRecord.create({
            query: aiData.query,
            answer: aiData.answer,
            latencySeconds: aiData.latency_seconds,
            retrievedChunks: aiData.retrieved_chunks,
            owner: req.user.id,
            document: documentId || null
        });

        // 4. Return the final response to the frontend
        return res.status(200).json({
            message: "Query processed successfully",
            history_id: newRecord._id,
            data: aiData
        });

    } catch (error) {
        console.error("Query Error:", error.message);
        // Handle FastAPI errors cleanly
        if (error.response) {
            return res.status(error.response.status).json({ error: error.response.data });
        }
        res.status(500).json({ error: 'Server error while processing the query' });
    }
};