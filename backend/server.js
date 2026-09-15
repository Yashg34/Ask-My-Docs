require('dotenv').config();
const express = require('express');
const mongoose = require('mongoose');
const cors = require('cors');
const cookieParser = require('cookie-parser');
const multer = require('multer');

const app = express();

app.use(express.json());
app.use(cookieParser());

// CORS is credential-safe (never wildcard + credentials): CORS_ORIGIN restricts
// origins when set; otherwise Vary-Origin reflection keeps local dev simple.
const corsOptions = process.env.CORS_ORIGIN
    ? { origin: process.env.CORS_ORIGIN.split(',').map(s => s.trim()), credentials: true }
    : { origin: true, credentials: true };
app.use(cors(corsOptions));

const authRoutes = require('./src/routes/auth.routes');
const documentRoutes = require('./src/routes/documents.routes');
const queryRoutes = require('./src/routes/query.routes');

// Use routes
app.use('/auth', authRoutes);
app.use('/documents', documentRoutes);
app.use('/query', queryRoutes);

app.get('/health', (req, res) => {
    res.status(200).json({ message: 'Node.js API Gateway is running smoothly!' });
});

// Uniform { error: { code, message } } contract for every 4xx/5xx (matches the
// ai-research FastAPI envelope). Catches errors controllers don't — notably
// multer upload failures — so they never hit Express's HTML error handler.
app.use((err, req, res, next) => {
    let status = err.status || err.statusCode || 500;
    let message = err.message || 'Internal server error';

    if (err instanceof multer.MulterError) {
        status = err.code === 'LIMIT_FILE_SIZE' ? 413 : 400;
        message = err.code === 'LIMIT_FILE_SIZE'
            ? 'File too large. Maximum size is 20MB.'
            : `Upload error: ${err.message}`;
    } else if (status >= 500) {
        console.error('❌ Unhandled error:', err);
        message = 'Internal server error'; // Don't leak internals
    }

    if (res.headersSent) return next(err);
    return res.status(status).json({ error: { code: status, message } });
});

mongoose.connect(process.env.MONGODB_URI)
    .then(() => {
        console.log('✅ Connected to MongoDB');

        const PORT = process.env.PORT || 5000;
        app.listen(PORT, () => {
            console.log(`🚀 Server running on port ${PORT}`);
        });
    })
    .catch((err) => {
        console.error('❌ MongoDB connection error:', err);
    });