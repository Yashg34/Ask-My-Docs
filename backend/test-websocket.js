/**
 * Standalone WebSocket test client — verifies the real-time status relay
 * end-to-end WITHOUT building the React frontend.
 *
 * Usage:
 *   node test-websocket.js query "what is a mortgage?"
 *   node test-websocket.js ingest <path-to.pdf>
 *
 * Prereqs (both running):
 *   - backend:  cd backend && npm run dev     (port 5000)
 *   - FastAPI:  cd ai-research && uvicorn main:app   (port 8000)
 *
 * The script mints its own JWT using backend/.env JWT_SECRET, so no login needed.
 */
require('dotenv').config();
const { io } = require('socket.io-client');
const axios = require('axios');
const jwt = require('jsonwebtoken');
const crypto = require('crypto');
const fs = require('fs');
const FormData = require('form-data');

const BACKEND_URL = process.env.BACKEND_URL || 'http://localhost:5000';

if (!process.env.JWT_SECRET) {
    console.error('❌ JWT_SECRET not found in backend/.env');
    process.exit(1);
}

// Mint a token for a fake user (Socket.IO + REST both just verify the JWT).
const token = jwt.sign({ id: 'test-user-1', email: 'test@example.com' }, process.env.JWT_SECRET, { expiresIn: '1h' });

function connectSocket() {
    const socket = io(BACKEND_URL, { auth: { token } });
    socket.on('connect', () => console.log(`✅ Connected to Socket.IO: ${socket.id}`));
    socket.on('connect_error', (err) => {
        console.error('❌ Socket.IO connection failed:', err.message);
        process.exit(1);
    });
    return socket;
}

// ── Query progress test ──────────────────────────────────────────────────
async function testQuery(rawQuery) {
    const queryId = crypto.randomUUID();
    const socket = connectSocket();

    socket.on('connect', () => {
        socket.emit('join-query', queryId);
        console.log(`📡 Joined query room: ${queryId}\n`);
    });

    socket.on('query:status', (data) => {
        const ts = new Date(data.ts * 1000).toISOString().substr(11, 12);
        console.log(`  [${ts}] ▸ ${data.message}`);
        if (data.stage === 'done') console.log('');
    });

    console.log(`❓ Sending query: "${rawQuery}"\n`);
    const res = await axios.post(`${BACKEND_URL}/query`, {
        query: rawQuery,
        queryId,
        topK: 15,
        topN: 5,
        chatHistory: [],
    }, { headers: { Cookie: `token=${token}` } });

    const { answer, latency_seconds } = res.data.data;
    console.log(`✅ Answer (${latency_seconds}s):\n${answer}\n`);
    process.exit(0);
}

// ── Ingestion progress test ──────────────────────────────────────────────
async function testIngest(pdfPath) {
    if (!fs.existsSync(pdfPath)) {
        console.error(`❌ File not found: ${pdfPath}`);
        process.exit(1);
    }

    const socket = connectSocket();

    // Upload first to get a real documentId + jobId, then join its room.
    const form = new FormData();
    form.append('file', fs.createReadStream(pdfPath));
    const upload = await axios.post(`${BACKEND_URL}/documents/upload`, form, {
        headers: { ...form.getHeaders(), Cookie: `token=${token}` },
    });
    const { _id } = upload.data.document;
    console.log(`\n📄 Document uploaded: ${_id}\n`);

    socket.on('connect', () => {
        socket.emit('join-document', String(_id));
        console.log(`📡 Joined document room: ${_id}\n`);
    });
    socket.on('ingest:status', (data) => {
        console.log(`  [ingest] ▸ ${data.message || data.status}`);
        if (data.status === 'COMPLETED') { console.log('\n✅ Ingestion done'); process.exit(0); }
        if (data.status === 'FAILED') { console.log('\n❌ Ingestion FAILED'); process.exit(1); }
    });
}

const cmd = process.argv[2];

if (cmd === 'query') {
    const q = process.argv[3] || 'What does this document collection cover?';
    testQuery(q).catch((e) => {
        console.error('❌ Query test failed:', e.response?.data || e.message);
        process.exit(1);
    });
} else if (cmd === 'ingest') {
    if (!process.argv[3]) { console.error('Usage: node test-websocket.js ingest <path-to.pdf>'); process.exit(1); }
    testIngest(process.argv[3]).catch((e) => {
        console.error('❌ Ingest test failed:', e.response?.data || e.message);
        process.exit(1);
    });
} else {
    console.log('Usage:\n  node test-websocket.js query "your question"\n  node test-websocket.js ingest <path-to.pdf>');
    process.exit(0);
}