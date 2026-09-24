const express = require('express');
const router = express.Router();
const auth = require('../middleware/auth.middleware');
const Session = require('../models/Session.model');
const QueryRecord = require('../models/QueryRecord.model');

// GET /sessions – list all sessions for the authenticated user
router.get('/', auth, async (req, res) => {
    try {
        const sessions = await Session.find({ user: req.user._id }).sort({ createdAt: -1 });
        res.json({ sessions });
    } catch (err) {
        console.error("GET /sessions error:", err);
        res.status(500).json({ error: { code: 500, message: 'Server error' } });
    }
});

// POST /sessions – create a new session
router.post('/', auth, async (req, res) => {
    try {
        const { title } = req.body;
        const session = await Session.create({
            title: title || 'New Chat',
            user: req.user._id
        });
        res.status(201).json({ session });
    } catch (err) {
        console.error("POST /sessions error:", err);
        res.status(500).json({ error: { code: 500, message: 'Server error' } });
    }
});

// GET /sessions/:id/messages – fetch chat history for a session
router.get('/:id/messages', auth, async (req, res) => {
    try {
        const session = await Session.findOne({ _id: req.params.id, user: req.user._id });
        if (!session) {
            return res.status(404).json({ error: { code: 404, message: 'Session not found' } });
        }
        const messages = await QueryRecord.find({ session: session._id }).sort({ createdAt: 1 });
        res.json({ messages });
    } catch (err) {
        console.error("GET /sessions/:id/messages error:", err);
        res.status(500).json({ error: { code: 500, message: 'Server error' } });
    }
});

module.exports = router;
