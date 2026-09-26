const Session = require('../models/Session.model');
const QueryRecord = require('../models/QueryRecord.model');

// Fetch all sessions for the authenticated user
exports.getSessions = async (req, res) => {
    try {
        const sessions = await Session.find({ user: req.user.id }).sort({ createdAt: -1 });
        res.json({ sessions });
    } catch (err) {
        console.error("GET /sessions error:", err);
        res.status(500).json({ error: { code: 500, message: 'Server error' } });
    }
};

// Create a new session
exports.createSession = async (req, res) => {
    try {
        const { title } = req.body;
        const session = await Session.create({
            title: title || 'New Chat',
            user: req.user.id
        });
        res.status(201).json({ session });
    } catch (err) {
        console.error("POST /sessions error:", err);
        res.status(500).json({ error: { code: 500, message: 'Server error' } });
    }
};

// Rename a session
exports.renameSession = async (req, res) => {
    try {
        const { title } = req.body;

        if (!title || !title.trim()) {
            return res.status(400).json({ error: { code: 400, message: 'Session title is required' } });
        }

        const session = await Session.findOneAndUpdate(
            { _id: req.params.id, user: req.user.id },
            { title: title.trim() },
            { new: true }
        );

        if (!session) {
            return res.status(404).json({ error: { code: 404, message: 'Session not found' } });
        }

        res.json({ session });
    } catch (err) {
        console.error("PATCH /sessions/:id error:", err);
        res.status(500).json({ error: { code: 500, message: 'Server error' } });
    }
};

// Delete a session and its associated queries
exports.deleteSession = async (req, res) => {
    try {
        const session = await Session.findOne({ _id: req.params.id, user: req.user.id });

        if (!session) {
            return res.status(404).json({ error: { code: 404, message: 'Session not found' } });
        }

        await QueryRecord.deleteMany({ session: session._id });
        await Session.deleteOne({ _id: session._id });

        res.json({ message: 'Session deleted successfully' });
    } catch (err) {
        console.error("DELETE /sessions/:id error:", err);
        res.status(500).json({ error: { code: 500, message: 'Server error' } });
    }
};

// Fetch chat history for a session
exports.getSessionMessages = async (req, res) => {
    try {
        const session = await Session.findOne({ _id: req.params.id, user: req.user.id });
        
        if (!session) {
            return res.status(404).json({ error: { code: 404, message: 'Session not found' } });
        }
        
        const messages = await QueryRecord.find({ session: session._id }).sort({ createdAt: 1 });
        res.json({ messages });
    } catch (err) {
        console.error("GET /sessions/:id/messages error:", err);
        res.status(500).json({ error: { code: 500, message: 'Server error' } });
    }
};