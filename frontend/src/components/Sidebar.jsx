import { useRef, useState } from 'react';
import { api } from '../lib/api';

const statusLabel = {
  PROCESSING: 'Processing',
  COMPLETED: 'Ready',
  FAILED: 'Failed',
};

function DocumentCard({ document, selected, onSelect, onRetry }) {
  return (
    <button className={`document-card ${selected ? 'selected' : ''}`} onClick={() => document.status === 'COMPLETED' && onSelect(document)}>
      <span className="file-icon">PDF</span>
      <span className="document-copy">
        <strong title={document.originalName || document.filename}>{document.originalName || document.filename}</strong>
        <small className={`status ${document.status.toLowerCase()}`}>{statusLabel[document.status] || document.status}</small>
        {document.status === 'FAILED' && <small className="failure">{document.errorMessage || 'Upload failed'} <span onClick={(e) => { e.stopPropagation(); onRetry(); }}>Retry</span></small>}
      </span>
      {selected && <span className="check">✓</span>}
    </button>
  );
}

export default function Sidebar({ documents, setDocuments, sessions, selectedSessionId, onSelectSession, onCreateSession, selectedDocumentId, onSelectDocument }) {
  const [uploading, setUploading] = useState(false);
  const fileInput = useRef(null);

  const upload = async (event) => {
    const file = event.target.files?.[0];
    event.target.value = '';
    if (!file) return;
    setUploading(true); 
    try {
      const form = new FormData();
      form.append('file', file);
      const result = await api('/documents/upload', { method: 'POST', body: form });
      setDocuments((current) => [result.document, ...current.filter((doc) => String(doc._id) !== String(result.document._id))]);
    } catch (err) { 
        alert(err.message); 
    } finally { 
        setUploading(false); 
    }
  };

  return (
    <aside className="sidebar" style={{ display: 'flex', flexDirection: 'column', gap: '2rem' }}>
      
      {/* Sessions Section */}
      <div>
          <div className="sidebar-heading">
              <div>
                  <p className="eyebrow">Conversations</p>
                  <h2>Your Chats</h2>
              </div>
              <button className="icon-button" onClick={onCreateSession} aria-label="New Session">+</button>
          </div>
          <div className="documents" style={{ marginTop: '1rem' }}>
              {sessions.length === 0 ? (
                  <p className="muted" style={{ padding: '0 1rem', fontSize: '0.9rem' }}>No chats yet</p>
              ) : (
                  sessions.map(s => (
                    <button 
                        key={s._id} 
                        className={`document-card ${selectedSessionId === s._id ? 'selected' : ''}`}
                        onClick={() => onSelectSession(s._id)}
                    >
                        <span className="document-copy">
                            <strong>{s.title}</strong>
                        </span>
                        {selectedSessionId === s._id && <span className="check">✓</span>}
                    </button>
                  ))
              )}
          </div>
      </div>

      {/* Documents Section */}
      <div>
        <div className="sidebar-heading">
            <div>
                <p className="eyebrow">Workspace</p>
                <h2>Your documents</h2>
            </div>
            <button className="icon-button" onClick={() => fileInput.current?.click()} aria-label="Upload document">+</button>
        </div>
        <input ref={fileInput} type="file" accept="application/pdf,.pdf" hidden onChange={upload} />
        <button className="upload-button" onClick={() => fileInput.current?.click()} disabled={uploading}>
            <span>↑</span>{uploading ? 'Uploading…' : 'Upload a PDF'}
        </button>
        <p className="sidebar-help">PDF files only · Max 20 MB</p>
        <div className="documents">
            {documents.length === 0 ? (
                <div className="empty-docs">
                    <span>▧</span>
                    <p>No documents</p>
                </div>
            ) : documents.map((doc) => (
                <DocumentCard 
                    key={doc._id} 
                    document={doc} 
                    selected={String(doc._id) === String(selectedDocumentId)} 
                    onSelect={(item) => onSelectDocument(item._id)} 
                    onRetry={() => fileInput.current?.click()} 
                />
            ))}
        </div>
      </div>
    </aside>
  );
}
