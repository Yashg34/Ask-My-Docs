const { Server } = require('socket.io');
const jwt = require('jsonwebtoken');
const aiClient = require('../lib/aiClient');

let io = null;

/**
 * Shared SSE consumer: opens a fetch stream to `url`, parses `data:` JSON
 * events, and calls `onEvent(event)` per event. Returns an abort function.
 */
function _consumeSSE(url, headers, onEvent) {
    const controller = new AbortController();
    (async () => {
        try {
            const response = await fetch(url, {
                headers: { Accept: 'text/event-stream', ...headers },
                signal: controller.signal,
            });
            if (!response.ok || !response.body) {
                console.error(`❌ SSE connect failed (HTTP ${response.status}): ${url}`);
                return;
            }
            const reader = response.body.getReader();
            const decoder = new TextDecoder();
            let buffer = '';
            while (true) {
                const { done, value } = await reader.read();
                if (done) break;
                buffer += decoder.decode(value, { stream: true });
                // SSE events are separated by blank lines.
                const events = buffer.split('\n\n');
                buffer = events.pop(); // keep the trailing partial event buffered
                for (const rawEvent of events) {
                    for (const line of rawEvent.split('\n')) {
                        if (!line.startsWith('data: ')) continue;
                        try { onEvent(JSON.parse(line.slice(6))); } catch (e) { console.error('⚠️ SSE parse error:', e.message); }
                    }
                }
            }
            console.log(`✅ SSE stream closed: ${url}`);
        } catch (err) {
            if (err.name === 'AbortError') console.log(`🛑 SSE stream aborted: ${url}`);
            else console.error(`❌ SSE stream error (${url}):`, err.message);
        }
    })();
    return () => controller.abort();
}

/**
 * Attach Socket.IO to the HTTP server. Authenticates connections via the JWT
 * token passed in the handshake `auth.token` (same secret as REST cookies).
 * Clients join `doc:{documentId}` (ingestion) or `query:{queryId}` (RAG
 * progress) rooms to receive real-time events.
 */
function attachSocketIO(httpServer) {
    io = new Server(httpServer, {
        cors: {
            origin: process.env.CORS_ORIGIN
                ? process.env.CORS_ORIGIN.split(',').map((s) => s.trim())
                : true,
            credentials: true,
        },
    });

    // Socket.IO auth middleware: verify the JWT from the handshake.
    io.use((socket, next) => {
        const token = socket.handshake.auth?.token;
        if (!token) return next(new Error('Not authorized: no token provided'));
        try {
            socket.user = jwt.verify(token, process.env.JWT_SECRET);
            next();
        } catch (err) {
            next(new Error('Not authorized: invalid or expired token'));
        }
    });

    io.on('connection', (socket) => {
        console.log(`🔌 Socket.IO client connected: ${socket.id} (user ${socket.user?.id})`);

        socket.on('join-document', (documentId) => {
            if (typeof documentId === 'string' && documentId) {
                socket.join(`doc:${documentId}`);
                console.log(`📡 Socket ${socket.id} joined room doc:${documentId}`);
            }
        });

        socket.on('join-query', (queryId) => {
            if (typeof queryId === 'string' && queryId) {
                socket.join(`query:${queryId}`);
                console.log(`📡 Socket ${socket.id} joined room query:${queryId}`);
            }
        });

        socket.on('disconnect', () => {
            console.log(`🔌 Socket.IO client disconnected: ${socket.id}`);
        });
    });

    return io;
}

function getIO() {
    if (!io) throw new Error('Socket.IO not initialized. Call attachSocketIO first.');
    return io;
}

/**
 * Relay FastAPI's ingestion SSE stream (job) to the document's Socket.IO room.
 */
function streamIngestStatus(documentId, jobId, userId) {
    if (!io) {
        console.error('⚠️ Socket.IO not initialized — cannot relay ingestion status');
        return () => {};
    }
    const baseUrl = process.env.FASTAPI_URL || 'http://127.0.0.1:8000';
    const url = `${baseUrl}/ingest/events/${jobId}`;

    return _consumeSSE(url, { 'X-User-Id': userId }, (event) => {
        io.to(`doc:${documentId}`).emit('ingest:status', { documentId, ...event });
        if (event.status === 'COMPLETED' || event.status === 'FAILED') {
            console.log(`✅ Ingestion terminal for job ${jobId} (${event.status})`);
        }
    });
}

/**
 * Relay FastAPI's query-progress SSE stream (queryId) to the query's Socket.IO
 * room. The relay stops on its own once the SSE stream ends.
 */
function streamQueryStatus(queryId, userId) {
    if (!io) {
        console.error('⚠️ Socket.IO not initialized — cannot relay query status');
        return () => {};
    }
    const baseUrl = process.env.FASTAPI_URL || 'http://127.0.0.1:8000';
    const url = `${baseUrl}/query/events/${queryId}`;

    return _consumeSSE(url, { 'X-User-Id': userId }, (event) => {
        io.to(`query:${queryId}`).emit('query:status', { queryId, ...event });
    });
}

module.exports = { attachSocketIO, getIO, streamIngestStatus, streamQueryStatus };