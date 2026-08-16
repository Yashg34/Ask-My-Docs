const express = require('express');
const router = express.Router();
const authMiddleware = require('../middleware/auth.middleware');
const queryController = require('../controllers/query.controller');

router.post('/', authMiddleware, queryController.askQuery);

module.exports = router;