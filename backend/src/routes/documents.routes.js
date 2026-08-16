const express = require('express');
const router = express.Router();
const multer = require('multer');
const authMiddleware = require('../middleware/auth.middleware');
const documentController = require('../controllers/document.controller');

// Using memory storage so we don't save to disk unnecessarily on the Node server
const upload = multer({ 
    storage: multer.memoryStorage(),
    fileFilter: (req, file, cb) => {
        if (file.mimetype === 'application/pdf') {
            cb(null, true);
        } else {
            cb(new Error('Only PDF files are supported!'), false);
        }
    }
});

// The route is protected by Auth, and Multer looks for a field named "file"
router.post('/upload', authMiddleware, upload.single('file'), documentController.uploadDocument);

module.exports = router;