const mongoose = require('mongoose');

const sessionSchema = new mongoose.Schema({
    title: {
        type: String,
        required: true,
        default: 'New Chat'
    },
    user: {
        type: mongoose.Schema.Types.ObjectId,
        ref: 'User',
        required: true
    }
}, { timestamps: true });

module.exports = mongoose.model('Session', sessionSchema);
