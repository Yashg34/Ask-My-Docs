const express = require('express');
const router = express.Router();
const multer = require('multer');
const authMiddleware = require('../middleware/auth.middleware');
const documentController = require('../controllers/document.controller');

// Memory storage so the backend never stages uploads on disk.
const upload = multer({
    storage: multer.memoryStorage(),
    limits: { fileSize: 20 * 1024 * 1024 }, // 20MB limit
    fileFilter: (req, file, cb) => {
        if (file.mimetype === 'application/pdf') {
            cb(null, true);
        } else {
            // Tag 4xx so the global error middleware returns a JSON envelope.
            const err = new Error('Only PDF files are supported!');
            err.status = 400;
            err.code = 'FILE_TYPE_NOT_SUPPORTED';
            cb(err, false);
        }
    }
});

// The route is protected by Auth, and Multer looks for a field named "file"
router.post('/upload', authMiddleware, upload.single('file'), documentController.uploadDocument);

// Route for the frontend to poll document status
router.get('/:id/status', authMiddleware, documentController.checkDocumentStatus);

module.exports = router;