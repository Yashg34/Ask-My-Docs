const express = require('express');
const router = express.Router();
const authMiddleware = require('../middleware/auth.middleware');
const queryController = require('../controllers/query.controller');

router.get('/events/:queryId', authMiddleware, queryController.streamQueryEvents);
router.post('/', authMiddleware, queryController.askQuery);

module.exports = router;