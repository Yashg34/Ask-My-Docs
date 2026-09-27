import { useEffect, useState, useMemo, useRef } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkMath from 'remark-math';
import rehypeKatex from 'rehype-katex';
import 'katex/dist/katex.min.css';
import { api } from '../lib/api';

const DEFAULT_STAGE_LABEL = 'Thinking…';

// Adjust these if your backend uses a different refusal message.
const isRefusalAnswer = (answer) => {
  if (!answer) return false;

  const normalized = answer.toLowerCase().trim();

  return (
    normalized.includes("couldn't find information in your documents") ||
    normalized.includes("could not find information in your documents") ||
    normalized.includes("i couldn't find information in your documents") ||
    normalized.includes("i could not find information in your documents")
  );
};

export default function ChatArea({
  sessionId,
  documentId,
  documents,
  onSelectDocument,
}) {
  const [messages, setMessages] = useState([]);
  const [question, setQuestion] = useState('');
  const [loading, setLoading] = useState(false);
  const [stageMessage, setStageMessage] = useState(DEFAULT_STAGE_LABEL);

  const [error, setError] = useState('');
  const [failedQuestion, setFailedQuestion] = useState('');

  const eventSourceRef = useRef(null);
  const scrollRef = useRef(null);

  const selectedDocument = useMemo(
    () =>
      documents.find(
        (doc) => String(doc._id) === String(documentId)
      ),
    [documents, documentId]
  );

  useEffect(() => {
    if (sessionId) {
      fetchMessages();
    }
  }, [sessionId]);

  useEffect(() => {
    return () => eventSourceRef.current?.close();
  }, []);

  // Keep the newest message (or the "thinking…" placeholder) in view,
  // without scrolling the whole page — only the message list scrolls.
  useEffect(() => {
    const el = scrollRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [messages, loading, stageMessage]);

  const fetchMessages = async () => {
    try {
      const res = await api(`/sessions/${sessionId}/messages`);
      setMessages(res.messages || []);
    } catch (err) {
      console.error(err);
      setMessages([]);
    }
  };

  const ask = async (event, retryQuestion = null) => {
    event?.preventDefault();

    const query = (retryQuestion ?? question).trim();

    // Client-side validation.
    if (!query) return;
    
    setLoading(true);
    setError('');
    setFailedQuestion('');
    setStageMessage(DEFAULT_STAGE_LABEL);

    const queryId = crypto.randomUUID();

    // Open progress stream first so early stage events are not missed.
    const es = new EventSource(
      `/query/events/${queryId}`,
      { withCredentials: true }
    );

    eventSourceRef.current = es;

    es.onmessage = (msg) => {
      try {
        const evt = JSON.parse(msg.data);

        if (evt.stage === 'done') {
          es.close();
        } else if (evt.message) {
          setStageMessage(evt.message);
        }
      } catch {
        // Ignore malformed/keepalive frames.
      }
    };

    es.onerror = () => {
      // SSE is only for progress updates.
      // The actual query request still determines success/failure.
      es.close();
    };

    try {
      const result = await api('/query', {
        method: 'POST',
        body: JSON.stringify({
          query,
          documentId: documentId || undefined,
          sessionId,
          chatHistory: messages
            .slice(-6)
            .map(({ query, answer }) => ({
              query,
              answer,
            })),
          queryId,
        }),
      });

      const answer = result.data.answer || '';

      const newMsg = {
        _id: result.history_id || Date.now(),
        query: result.data.query,
        answer,
        retrievedChunks:
          result.data.retrieved_chunks || [],
        isRefusal: isRefusalAnswer(answer),
      };

      setMessages((current) => [...current, newMsg]);

      // Clear the input only after successful submission.
      if (!retryQuestion) {
        setQuestion('');
      }
    } catch (err) {
      console.error('Query failed:', err);

      // This is an actual backend/network failure.
      setError(
        err.message ||
          'Something went wrong while processing your question.'
      );

      // Keep the exact failed question so Try again
      // can resubmit it.
      setFailedQuestion(query);
    } finally {
      setLoading(false);
      es.close();
      eventSourceRef.current = null;
    }
  };

  const retry = () => {
    if (!failedQuestion || loading) return;

    ask(null, failedQuestion);
  };

  return (
    <section className="chat-area">
      <div className="chat-header">
        <div>
          <p className="eyebrow">AI document assistant</p>

          <h1>
            {selectedDocument
              ? `Ask about ${selectedDocument.originalName}`
              : 'What would you like to know?'}
          </h1>
        </div>

        {selectedDocument && (
          <button
            className="clear-button"
            onClick={() => onSelectDocument(null)}
          >
            Ask all documents
          </button>
        )}
      </div>

      <div className="conversation-scroll" ref={scrollRef}>
      <div className="conversation">
        {messages.length === 0 && !loading && (
          <div className="welcome">
            <div className="welcome-orb">✦</div>

            <h2>
              Find the answer in your documents.
            </h2>

            <p>
              Ask a question and I’ll search your
              uploaded PDFs, then show you exactly
              where the answer came from.
            </p>

          </div>
        )}

        {messages.map((msg) => (
          <div
            key={msg._id}
            className={`answer-card ${
              msg.isRefusal
                ? 'answer-card refusal'
                : ''
            }`}
          >
            <div className="question-label">
              Your question
            </div>

            <p className="question">
              {msg.query}
            </p>

            <div className="answer-label">
              {msg.isRefusal
                ? 'Not found in documents'
                : 'Answer'}
            </div>

            <div className="answer-text markdown-body">
              <ReactMarkdown
                remarkPlugins={[remarkMath]}
                rehypePlugins={[rehypeKatex]}
              >
                {msg.answer}
              </ReactMarkdown>
            </div>

            {msg.retrievedChunks &&
              msg.retrievedChunks.length > 0 && (
                <details style={{ marginTop: '1rem' }}>
                  <summary>
                    {msg.retrievedChunks.length} source
                    {msg.retrievedChunks.length === 1
                      ? ''
                      : 's'}{' '}
                    used
                  </summary>

                  <div className="sources">
                    {msg.retrievedChunks.map(
                      (chunk, index) => {
                        const meta =
                          chunk.metadata || {};

                        const {
                          document_name: docName,
                          page_start: pageStart,
                          page_end: pageEnd,
                        } = meta;

                        const pageLabel =
                          pageStart == null
                            ? null
                            : pageEnd != null &&
                              pageEnd !== pageStart
                            ? `Pages ${pageStart}-${pageEnd}`
                            : `Page ${pageStart}`;

                        return (
                          <div
                            className="source"
                            key={index}
                          >
                            <b>
                              Source {index + 1}

                              {(docName ||
                                pageLabel) && (
                                <span className="source-meta">
                                  {' '}—{' '}
                                  {docName ||
                                    'Unknown document'}
                                  {pageLabel
                                    ? `, ${pageLabel}`
                                    : ''}
                                </span>
                              )}
                            </b>

                            <span>
                              {chunk.text ||
                                chunk.content ||
                                'Retrieved document passage'}
                            </span>
                          </div>
                        );
                      }
                    )}
                  </div>
                </details>
              )}
          </div>
        ))}

        {loading && (
          <div className="answer-card">
            <p>{stageMessage}</p>
          </div>
        )}
      </div>
      </div>

      {/* Opaque footer, outside the scrolling region above, so message
          text can never appear behind the input or the disclaimer. */}
      <div className="chat-footer">
        {error && (
          <div className="error toast">
            <span>{error}</span>

            {failedQuestion && (
              <button
                type="button"
                className="retry-button"
                onClick={retry}
                disabled={loading}
              >
                Try again
              </button>
            )}
          </div>
        )}

        <form
          className="question-box"
          onSubmit={ask}
        >
          <textarea
            value={question}
            onChange={(e) => {
              setQuestion(e.target.value);

              // Remove the previous failure once
              // the user starts entering a new query.
              if (error) {
                setError('');
                setFailedQuestion('');
              }
            }}
            placeholder={
              selectedDocument
                ? 'Ask a question about this document…'
                : 'Ask anything about your documents…'
            }
            rows="1"
            onKeyDown={(e) => {
              if (
                e.key === 'Enter' &&
                !e.shiftKey
              ) {
                e.preventDefault();
                ask(e);
              }
            }}
          />

          <button
            className="send-button"
            disabled={
              loading || !question.trim()
            }
            aria-label="Send question"
          >
            {loading ? '…' : '↑'}
          </button>
        </form>

        <p className="disclaimer">
          Answers are generated from your documents.
          Always verify important information.
        </p>
      </div>
    </section>
  );
}