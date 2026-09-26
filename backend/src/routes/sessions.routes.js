const express = require('express');
const router = express.Router();
const auth = require('../middleware/auth.middleware');
const sessionController = require('../controllers/session.controller');

router.get('/', auth, sessionController.getSessions);
router.post('/', auth, sessionController.createSession);

router.patch('/:id', auth, sessionController.renameSession);
router.delete('/:id', auth, sessionController.deleteSession);

router.get('/:id/messages', auth, sessionController.getSessionMessages);

module.exports = router;