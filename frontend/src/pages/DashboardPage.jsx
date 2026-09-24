import { useEffect, useState } from 'react';
import { api } from '../lib/api';
import Sidebar from '../components/Sidebar';
import ChatArea from '../components/ChatArea';

export default function DashboardPage({ user, onLogout }) {
  const [documents, setDocuments] = useState([]);
  const [sessions, setSessions] = useState([]);
  const [selectedSessionId, setSelectedSessionId] = useState(null);
  const [selectedDocumentId, setSelectedDocumentId] = useState(null);

  useEffect(() => {
    fetchSessions();
    // In a real app we'd fetch documents too if we have a GET /documents
    // For now we assume upload populates the list
  }, []);

  const fetchSessions = async () => {
    try {
      const res = await api('/sessions');
      setSessions(res.sessions);
      if (res.sessions.length > 0 && !selectedSessionId) {
        setSelectedSessionId(res.sessions[0]._id);
      }
    } catch (err) {
      console.error(err);
    }
  };

  const createSession = async () => {
    try {
      const res = await api('/sessions', {
        method: 'POST',
        body: JSON.stringify({ title: 'New Chat' })
      });
      setSessions([res.session, ...sessions]);
      setSelectedSessionId(res.session._id);
    } catch (err) {
      console.error(err);
    }
  };

  return (
    <div className="app-shell">
      <header className="topbar">
        <div className="logo"><span className="brand-mark small">A</span><strong>Ask My Docs</strong></div>
        <div className="user-menu"><span>{user.email}</span><button onClick={onLogout}>Sign out</button></div>
      </header>
      <main className="workspace">
        <Sidebar 
          documents={documents}
          setDocuments={setDocuments}
          sessions={sessions}
          selectedSessionId={selectedSessionId}
          onSelectSession={setSelectedSessionId}
          onCreateSession={createSession}
          selectedDocumentId={selectedDocumentId}
          onSelectDocument={setSelectedDocumentId}
        />
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
                <button className="primary" onClick={createSession}>Create a Session</button>
             </div>
          </section>
        )}
      </main>
    </div>
  );
}
