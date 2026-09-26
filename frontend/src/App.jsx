import { useEffect, useState } from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { api } from './lib/api';

import LoginPage from './pages/LoginPage';
import RegisterPage from './pages/RegisterPage';
import DashboardPage from './pages/DashboardPage';
import ErrorBoundary from './components/ErrorBoundary';

function App() {
  const [user, setUser] = useState(() => JSON.parse(localStorage.getItem('ask-my-docs-user') || 'null'));

  const authenticate = (nextUser) => {
    localStorage.setItem('ask-my-docs-user', JSON.stringify(nextUser));
    setUser(nextUser);
  };

  const logout = async () => {
    try { await api('/auth/logout', { method: 'POST' }); } catch { /* ignore */ }
    localStorage.removeItem('ask-my-docs-user');
    setUser(null);
  };

  return (
    <BrowserRouter>
      <Routes>
        <Route 
          path="/login" 
          element={!user ? <LoginPage onAuthenticated={authenticate} /> : <Navigate to="/" />} 
        />
        <Route 
          path="/register" 
          element={!user ? <RegisterPage /> : <Navigate to="/" />} 
        />
        <Route 
          path="/" 
          element={user ? <ErrorBoundary><DashboardPage user={user} onLogout={logout} /></ErrorBoundary> : <Navigate to="/login" />} 
        />
      </Routes>
    </BrowserRouter>
  );
}

export default App;