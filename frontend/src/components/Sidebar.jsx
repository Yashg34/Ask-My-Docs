import { useEffect, useRef, useState } from 'react';
import { api } from '../lib/api';

const statusLabel = {
  PROCESSING: 'Processing',
  COMPLETED: 'Ready',
  FAILED: 'Failed',
};

function SkeletonRows({ count = 3 }) {
  return (
    <>
      {Array.from({ length: count }).map((_, index) => (
        <div
          key={index}
          className="document-card skeleton-row"
          aria-hidden="true"
        >
          <span className="skeleton-icon" />

          <span className="document-copy">
            <span className="skeleton-line" />
            <span className="skeleton-line short" />
          </span>
        </div>
      ))}
    </>
  );
}

function DocumentCard({
  document,
  selected,
  onSelect,
  onRetry,
}) {
  return (
    <button
      className={`document-card ${selected ? 'selected' : ''}`}
      onClick={() =>
        document.status === 'COMPLETED' && onSelect(document)
      }
    >
      <span className="file-icon">PDF</span>

      <span className="document-copy">
        <strong title={document.originalName || document.filename}>
          {document.originalName || document.filename}
        </strong>

        <small className={`status ${document.status.toLowerCase()}`}>
          {statusLabel[document.status] || document.status}
        </small>

        {document.status === 'FAILED' && (
          <small className="failure">
            {document.errorMessage || 'Upload failed'}{' '}
            <span
              onClick={(e) => {
                e.stopPropagation();
                onRetry();
              }}
            >
              Retry
            </span>
          </small>
        )}
      </span>

      {selected && <span className="check">✓</span>}
    </button>
  );
}

export default function Sidebar({
  documents,
  setDocuments,
  documentsLoading,
  sessions,
  sessionsLoading,
  selectedSessionId,
  onSelectSession,
  onCreateSession,
  onSessionUpdated,
  onSessionDeleted,
  selectedDocumentId,
  onSelectDocument,
}) {
  const [uploading, setUploading] = useState(false);
  const [editingSessionId, setEditingSessionId] = useState(null);
  const [editingTitle, setEditingTitle] = useState('');
  const [deletingId, setDeletingId] = useState(null);

  const fileInput = useRef(null);
  const documentsRef = useRef(documents);

  documentsRef.current = documents;

  // Poll any document still PROCESSING every 3 seconds.
  useEffect(() => {
    const interval = setInterval(async () => {
      const pending = documentsRef.current.filter(
        (doc) => doc.status === 'PROCESSING'
      );

      if (pending.length === 0) return;

      const updates = await Promise.all(
        pending.map((doc) =>
          api(`/documents/${doc._id}/status`)
            .then((res) => res.document)
            .catch((err) => {
              console.error(
                `Status check failed for ${doc._id}:`,
                err
              );
              return null;
            })
        )
      );

      const byId = new Map(
        updates
          .filter(Boolean)
          .map((document) => [
            String(document._id),
            document,
          ])
      );

      if (byId.size === 0) return;

      setDocuments((current) =>
        current.map(
          (doc) => byId.get(String(doc._id)) || doc
        )
      );
    }, 3000);

    return () => clearInterval(interval);
  }, [setDocuments]);

  const upload = async (event) => {
    const file = event.target.files?.[0];

    event.target.value = '';

    if (!file) return;

    setUploading(true);

    try {
      const form = new FormData();
      form.append('file', file);

      const result = await api('/documents/upload', {
        method: 'POST',
        body: form,
      });

      setDocuments((current) => [
        result.document,
        ...current.filter(
          (doc) =>
            String(doc._id) !==
            String(result.document._id)
        ),
      ]);
    } catch (err) {
      alert(err.message);
    } finally {
      setUploading(false);
    }
  };

  const renameSession = async (sessionId) => {
    const title = editingTitle.trim();

    if (!title) {
      setEditingSessionId(null);
      setEditingTitle('');
      return;
    }

    try {
      const res = await api(`/sessions/${sessionId}`, {
        method: 'PATCH',
        body: JSON.stringify({ title }),
      });

      onSessionUpdated(res.session);

      setEditingSessionId(null);
      setEditingTitle('');
    } catch (err) {
      console.error(err);
      alert(err.message || 'Failed to rename session');
    }
  };

  const deleteSession = async (sessionId) => {
    const confirmed = window.confirm(
      'Delete this chat? This action cannot be undone.'
    );

    if (!confirmed) return;

    try {
      setDeletingId(sessionId);

      await api(`/sessions/${sessionId}`, {
        method: 'DELETE',
      });

      onSessionDeleted(sessionId);
    } catch (err) {
      console.error(err);
      alert(err.message || 'Failed to delete session');
    } finally {
      setDeletingId(null);
    }
  };

  const deleteDocument = async (documentId) => {
    const confirmed = window.confirm(
      'Delete this document? Its indexed vectors will also be removed.'
    );

    if (!confirmed) return;

    try {
      setDeletingId(documentId);

      await api(`/documents/${documentId}`, {
        method: 'DELETE',
      });

      setDocuments((current) =>
        current.filter(
          (doc) =>
            String(doc._id) !== String(documentId)
        )
      );

      if (
        String(selectedDocumentId) ===
        String(documentId)
      ) {
        onSelectDocument(null);
      }
    } catch (err) {
      console.error(err);
      alert(err.message || 'Failed to delete document');
    } finally {
      setDeletingId(null);
    }
  };

  return (
    <aside
      className="sidebar"
    >
      {/* Sessions Section */}
      <section className="sidebar-section">
        <div className="sidebar-heading">
          <div>
            <p className="eyebrow">Conversations</p>
            <h2>Your Chats</h2>
          </div>

          <button
            className="icon-button"
            onClick={onCreateSession}
            aria-label="New Session"
          >
            +
          </button>
        </div>

        <div className="documents session-list">
          {sessionsLoading ? (
            <SkeletonRows count={3} />
          ) : sessions.length === 0 ? (
            <p
              className="muted"
              style={{
                padding: '0 1rem',
                fontSize: '0.9rem',
              }}
            >
              No chats yet
            </p>
          ) : (
            sessions.map((session) => (
              <div
                key={session._id}
                className={`session-row ${
                  selectedSessionId === session._id
                    ? 'selected'
                    : ''
                }`}
              >
                {editingSessionId === session._id ? (
                  <input
                    autoFocus
                    className="session-edit-input"
                    value={editingTitle}
                    onChange={(e) =>
                      setEditingTitle(e.target.value)
                    }
                    onBlur={() =>
                      renameSession(session._id)
                    }
                    onKeyDown={(e) => {
                      if (e.key === 'Enter') {
                        e.preventDefault();
                        renameSession(session._id);
                      }

                      if (e.key === 'Escape') {
                        setEditingSessionId(null);
                        setEditingTitle('');
                      }
                    }}
                    onClick={(e) =>
                      e.stopPropagation()
                    }
                  />
                ) : (
                  <button
                    className="session-select"
                    onClick={() =>
                      onSelectSession(session._id)
                    }
                  >
                    <span className="document-copy">
                      <strong>{session.title}</strong>
                    </span>
                  </button>
                )}

                <div className="session-actions">
                  {selectedSessionId === session._id && (
                    <span className="check">✓</span>
                  )}

                  <button
                    className="card-action"
                    aria-label="Rename session"
                    title="Rename"
                    onClick={(e) => {
                      e.stopPropagation();

                      setEditingSessionId(session._id);
                      setEditingTitle(
                        session.title || ''
                      );
                    }}
                  >
                    ✎
                  </button>

                  <button
                    className="card-action delete"
                    aria-label="Delete session"
                    title="Delete"
                    disabled={
                      deletingId === session._id
                    }
                    onClick={(e) => {
                      e.stopPropagation();
                      deleteSession(session._id);
                    }}
                  >
                    ×
                  </button>
                </div>
              </div>
            ))
          )}
        </div>
      </section>

      {/* Documents Section */}
      <section className="sidebar-section">
        <div className="sidebar-heading">
          <div>
            <p className="eyebrow">Workspace</p>
            <h2>Your documents</h2>
          </div>

          <button
            className="icon-button"
            onClick={() =>
              fileInput.current?.click()
            }
            aria-label="Upload document"
          >
            +
          </button>
        </div>

        <input
          ref={fileInput}
          type="file"
          accept="application/pdf,.pdf"
          hidden
          onChange={upload}
        />

        <button
          className="upload-button"
          onClick={() =>
            fileInput.current?.click()
          }
          disabled={uploading}
        >
          <span>↑</span>
          {uploading
            ? 'Uploading…'
            : 'Upload a PDF'}
        </button>

        <p className="sidebar-help">
          PDF files only · Max 20 MB
        </p>

        <div className="documents">
          {documentsLoading ? (
            <SkeletonRows count={4} />
          ) : documents.length === 0 ? (
            <div className="empty-docs">
              <span>▧</span>
              <p>No documents</p>
            </div>
          ) : (
            documents.map((doc) => (
              <div
                key={doc._id}
                className="document-row"
              >
                <DocumentCard
                  document={doc}
                  selected={
                    String(doc._id) ===
                    String(selectedDocumentId)
                  }
                  onSelect={(item) =>
                    onSelectDocument(item._id)
                  }
                  onRetry={() =>
                    fileInput.current?.click()
                  }
                />

                <button
                  className="card-action delete document-delete"
                  aria-label="Delete document"
                  title="Delete document"
                  disabled={
                    deletingId === doc._id
                  }
                  onClick={(e) => {
                    e.stopPropagation();
                    deleteDocument(doc._id);
                  }}
                >
                  ×
                </button>
              </div>
            ))
          )}
        </div>
      </section>
    </aside>
  );
}