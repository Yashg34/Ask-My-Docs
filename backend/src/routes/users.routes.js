const express = require('express');
const router = express.Router();
const auth = require('../middleware/auth.middleware');
const User = require('../models/User.model');

// GET /users – list all users (non‑sensitive fields)
router.get('/', auth, async (req, res) => {
  try {
    const users = await User.find({}).select('_id name email createdAt');
    res.json({ users });
  } catch (err) {
    console.error(err);
    res.status(500).json({ error: { code: 500, message: 'Server error' } });
  }
});

module.exports = router;
