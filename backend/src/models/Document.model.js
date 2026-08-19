const mongoose = require('mongoose');

const documentSchema = new mongoose.Schema({
    filename: {
        type: String,
        required: true,
        trim: true
    },
    originalName: {
        type: String,
        required: true
    },
    fileHash: {
        type: String,
        required: true
    },
    owner: {
        type: mongoose.Schema.Types.ObjectId,
        ref: 'User',
        required: true
    },
    status: {
        type: String,
        enum: ['PROCESSING', 'COMPLETED', 'FAILED'],
        default: 'PROCESSING'
    },
    errorMessage: {
        type: String,
        default: ''
    },
    jobId: {
        type: String,
        default: null
    }
}, { timestamps: true });

module.exports = mongoose.model('Document', documentSchema);