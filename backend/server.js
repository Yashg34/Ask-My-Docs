require('dotenv').config();
const express = require('express');
const mongoose = require('mongoose');
const cors = require('cors');
const cookieParser = require('cookie-parser');

const app = express();

// Middleware
app.use(cors());
app.use(express.json()); 
app.use(cookieParser());

const authRoutes = require('./src/routes/auth.routes');
const documentRoutes = require('./src/routes/documents.routes');
const queryRoutes = require('./src/routes/query.routes');

// Use Routes
app.use('/auth', authRoutes);
app.use('/documents', documentRoutes);
app.use('/query', queryRoutes);

app.get('/health', (req, res) => {
    res.status(200).json({ message: 'Node.js API Gateway is running smoothly!' });
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