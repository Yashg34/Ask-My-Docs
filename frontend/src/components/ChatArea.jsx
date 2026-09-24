import { useEffect, useState, useMemo } from 'react';
import { api } from '../lib/api';

export default function ChatArea({ sessionId, documentId, documents, onSelectDocument }) {
  const [messages, setMessages] = useState([]);
  const [question, setQuestion] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const selectedDocument = useMemo(() => 
    documents.find((doc) => String(doc._id) === String(documentId)), 
  [documents, documentId]);

  useEffect(() => {
    if (sessionId) {
      fetchMessages();
    }
  }, [sessionId]);

  const fetchMessages = async () => {
    try {
      const res = await api(`/sessions/${sessionId}/messages`);
      setMessages(res.messages);
    } catch (err) {
      console.error(err);
    }
  };

  const ask = async (event) => {
    event.preventDefault();
    if (!question.trim()) return;
    setLoading(true); setError('');
    try {
      const result = await api('/query', {
        method: 'POST',
        body: JSON.stringify({
          query: question.trim(),
          documentId: documentId || undefined,
          sessionId: sessionId,
          chatHistory: messages.slice(-6).map(({ query, answer }) => ({ query, answer })),
        }),
      });
      
      const newMsg = {
          _id: result.history_id || Date.now(),
          query: result.data.query,
          answer: result.data.answer,
          retrievedChunks: result.data.retrieved_chunks || []
      };
      
      setMessages([...messages, newMsg]);
      setQuestion('');
    } catch (err) { 
        setError(err.message); 
    } finally { 
        setLoading(false); 
    }
  };

  return (
    <section className="chat-area">
      <div className="chat-header">
          <div>
              <p className="eyebrow">AI document assistant</p>
              <h1>{selectedDocument ? `Ask about ${selectedDocument.originalName}` : 'What would you like to know?'}</h1>
          </div>
          {selectedDocument && (
              <button className="clear-button" onClick={() => onSelectDocument(null)}>
                  Ask all documents
              </button>
          )}
      </div>
      
      <div className="conversation" style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem', overflowY: 'auto' }}>
        {messages.length === 0 && !loading && (
            <div className="welcome">
                <div className="welcome-orb">✦</div>
                <h2>Find the answer in your documents.</h2>
                <p>Ask a question and I’ll search your uploaded PDFs, then show you exactly where the answer came from.</p>
                <div className="suggestions">
                    <button onClick={() => setQuestion('What is the main purpose of this document?')}>What is the main purpose of this document?</button>
                    <button onClick={() => setQuestion('Summarize the key points')}>Summarize the key points</button>
                </div>
            </div>
        )}
        
        {messages.map(msg => (
            <div key={msg._id} className="answer-card">
                <div className="question-label">Your question</div>
                <p className="question">{msg.query}</p>
                
                <div className="answer-label">Answer</div>
                <div className="answer-text">{msg.answer}</div>
                
                {msg.retrievedChunks && msg.retrievedChunks.length > 0 && (
                    <details style={{ marginTop: '1rem' }}>
                        <summary>{msg.retrievedChunks.length} source{msg.retrievedChunks.length === 1 ? '' : 's'} used</summary>
                        <div className="sources">
                            {msg.retrievedChunks.map((chunk, index) => (
                                <div className="source" key={index}>
                                    <b>Source {index + 1}</b>
                                    <span>{chunk.text || chunk.content || 'Retrieved document passage'}</span>
                                </div>
                            ))}
                        </div>
                    </details>
                )}
            </div>
        ))}
        {loading && <div className="answer-card"><p>Thinking...</p></div>}
      </div>

      {error && <p className="error toast">{error}</p>}
      
      <form className="question-box" onSubmit={ask}>
          <textarea 
            value={question} 
            onChange={(e) => setQuestion(e.target.value)} 
            placeholder={selectedDocument ? 'Ask a question about this document…' : 'Ask anything about your documents…'} 
            rows="1" 
            onKeyDown={(e) => { 
                if (e.key === 'Enter' && !e.shiftKey) { 
                    e.preventDefault(); 
                    ask(e); 
                } 
            }} 
          />
          <button className="send-button" disabled={loading || !question.trim()} aria-label="Send question">
              {loading ? '…' : '↑'}
          </button>
      </form>
      <p className="disclaimer">Answers are generated from your documents. Always verify important information.</p>
    </section>
  );
}
