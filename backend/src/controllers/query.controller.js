const QueryRecord = require('../models/QueryRecord.model');
const Document = require('../models/Document.model');
const aiClient = require('../lib/aiClient');
const { streamQueryStatus } = require('../services/statusStream');

exports.askQuery = async (req, res) => {
    try {
        const { query, documentId, topK, topN, threshold, chatHistory, queryId } = req.body;

        if (!query || !query.trim()) {
            return res.status(400).json({ error: { code: 400, message: "Query cannot be empty." } });
        }

        // Defaults match the pipeline contract (top_k=15 wide fetch, top_n=5
        // post-FlashRank); the frontend may override via topK/topN/threshold.
        const payload = {
            query: query,
            top_k: topK ?? 15,
            top_n: topN ?? 5,
            threshold: threshold ?? 0.05,
            chat_history: chatHistory || [],
            query_id: queryId || ''
        };

        if (documentId) {
            // Defense-in-depth: never forward a document the user doesn't own.
            // Qdrant's user_id filter would block it anyway, but this fails fast
            // and reads as a proper 404 instead of a silent empty retrieval.
            const owned = await Document.findOne({ _id: documentId, owner: req.user.id });
            if (!owned) {
                return res.status(404).json({ error: { code: 404, message: "Document not found" } });
            }
            payload.document_id = documentId;
        }

        // Start relaying real-time RAG progress to the frontend's Socket.IO
        // room BEFORE forwarding, so subscription is live when the graph runs.
        if (queryId) {
            streamQueryStatus(queryId, req.user.id);
        }

        const fastApiResponse = await aiClient.post('/query', payload, {
            _userId: req.user.id
        });
        const aiData = fastApiResponse.data;

        // Persist the query/answer history in MongoDB.
        const newRecord = await QueryRecord.create({
            query: aiData.query,
            answer: aiData.answer,
            latencySeconds: aiData.latency_seconds,
            retrievedChunks: aiData.retrieved_chunks,
            owner: req.user.id,
            document: documentId || null
        });

        return res.status(200).json({
            message: "Query processed successfully",
            history_id: newRecord._id,
            data: aiData
        });

    } catch (error) {
        console.error("Query Error:", error.message);
        // Forward FastAPI's { error: { code, message } } envelope as-is.
        if (error.response && error.response.data) {
            return res.status(error.response.status).json(error.response.data);
        }
        res.status(500).json({ error: { code: 500, message: 'Server error while processing the query' } });
    }
};