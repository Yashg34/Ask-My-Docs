const mongoose = require('mongoose');

const queryRecordSchema = new mongoose.Schema({
    query: {
        type: String,
        required: true
    },
    answer: {
        type: String,
        required: true
    },
    latencySeconds: {
        type: Number,
        required: true
    },
    retrievedChunks: {
        type: Array,
        default: []
    },
    document: {
        type: mongoose.Schema.Types.ObjectId,
        ref: 'Document',
        required: false // If the user queries across all their documents
    },
    owner: {
        type: mongoose.Schema.Types.ObjectId,
        ref: 'User',
        required: true
    },
    session: {
        type: mongoose.Schema.Types.ObjectId,
        ref: 'Session',
        required: false // allow existing queries to remain valid
    }
}, { timestamps: true });

module.exports = mongoose.model('QueryRecord', queryRecordSchema);