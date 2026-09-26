import { useEffect, useState } from 'react';
import { api } from '../lib/api';
import Sidebar from '../components/Sidebar';
import ChatArea from '../components/ChatArea';

export default function DashboardPage({ user, onLogout }) {
  const [documents, setDocuments] = useState([]);
  const [sessions, setSessions] = useState([]);
  const [selectedSessionId, setSelectedSessionId] = useState(null);
  const [selectedDocumentId, setSelectedDocumentId] = useState(null);

  const [sessionsLoading, setSessionsLoading] = useState(true);
  const [documentsLoading, setDocumentsLoading] = useState(true);

  useEffect(() => {
    fetchSessions();
    fetchDocuments();
  }, []);

  const fetchDocuments = async () => {
    try {
      const res = await api('/documents');
      setDocuments(res.documents || []);
    } catch (err) {
      console.error(err);
      setDocuments([]);
    } finally {
      setDocumentsLoading(false);
    }
  };

  const fetchSessions = async () => {
    try {
      const res = await api('/sessions');
      const list = res.sessions || [];

      setSessions(list);

      if (list.length > 0 && !selectedSessionId) {
        setSelectedSessionId(list[0]._id);
      }
    } catch (err) {
      console.error(err);
      setSessions([]);
    } finally {
      setSessionsLoading(false);
    }
  };

  const createSession = async () => {
    try {
      const res = await api('/sessions', {
        method: 'POST',
        body: JSON.stringify({ title: 'New Chat' }),
      });

      setSessions((current) => [res.session, ...current]);
      setSelectedSessionId(res.session._id);
    } catch (err) {
      console.error(err);
    }
  };

  const updateSession = (updatedSession) => {
    setSessions((current) =>
      current.map((session) =>
        String(session._id) === String(updatedSession._id)
          ? updatedSession
          : session
      )
    );
  };

  const deleteSession = (sessionId) => {
    setSessions((current) => {
      const remaining = current.filter(
        (session) => String(session._id) !== String(sessionId)
      );

      if (String(selectedSessionId) === String(sessionId)) {
        setSelectedSessionId(
          remaining.length > 0 ? remaining[0]._id : null
        );
      }

      return remaining;
    });
  };

  return (
    <div className="app-shell">
      <main className="workspace">

        {/* SIDEBAR */}
        <aside className="dashboard-sidebar">

          {/* Sticky sidebar header */}
          <div className="sidebar-brand">
            <span className="brand-mark small">A</span>
            <strong>Ask My Docs</strong>
          </div>

          {/* Scrollable sidebar content */}
          <div className="sidebar-content">
            <Sidebar
              documents={documents}
              setDocuments={setDocuments}
              documentsLoading={documentsLoading}
              sessions={sessions}
              sessionsLoading={sessionsLoading}
              selectedSessionId={selectedSessionId}
              onSelectSession={setSelectedSessionId}
              onCreateSession={createSession}
              onSessionUpdated={updateSession}
              onSessionDeleted={deleteSession}
              selectedDocumentId={selectedDocumentId}
              onSelectDocument={setSelectedDocumentId}
            />
          </div>
        </aside>

        {/* MAIN DASHBOARD */}
        <section className="dashboard-main">

          {/* Fixed top-right controls */}
          <header className="dashboard-topbar">
            <button
              className="signout-button"
              onClick={onLogout}
            >
              Sign out
            </button>
          </header>

          {/* Entire right side scrolls */}
          <div className="dashboard-chat">
            {selectedSessionId ? (
              <ChatArea
                sessionId={selectedSessionId}
                documentId={selectedDocumentId}
                documents={documents}
                onSelectDocument={setSelectedDocumentId}
              />
            ) : (
              <section className="chat-area">
                <div className="welcome">
                  <h2>No Session Selected</h2>

                  <button
                    className="primary"
                    onClick={createSession}
                  >
                    Create a Session
                  </button>
                </div>
              </section>
            )}
          </div>

        </section>
      </main>
    </div>
  );
}