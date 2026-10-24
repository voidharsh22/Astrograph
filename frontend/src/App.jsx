import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom';
import { AuthProvider } from './hooks/useAuth.js';
import useAuth from './hooks/useAuth.js';
import Landing, { RingedPlanetLogo } from './pages/Landing.jsx';
import Features from './pages/Features.jsx';
import About from './pages/About.jsx';
import Dashboard from './pages/Dashboard.jsx';
import Repositories from './pages/Repositories.jsx';
import Analyze from './pages/Analyze.jsx';
import Workspace from './pages/Workspace.jsx';

// Pages that need a signed-in user. Dark themed transition shell to prevent white flashes.
function Protected({ children }) {
  const { user, ready } = useAuth();
  if (!ready) {
    return (
      <div
        style={{
          minHeight: '100vh',
          backgroundColor: '#020308',
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'center',
          gap: '1rem',
          color: '#FFF7ED',
          fontFamily: "'Plus Jakarta Sans', sans-serif"
        }}
      >
        <RingedPlanetLogo className="w-10 h-auto animate-pulse text-[#FB923C]" />
        <span style={{ fontSize: '0.72rem', fontFamily: "'JetBrains Mono', monospace", color: '#9CA3AF', letterSpacing: '0.12em' }}>
          ASTROGRAPH / CONNECTING...
        </span>
      </div>
    );
  }
  return user ? children : <Navigate to="/" replace />;
}

export default function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Routes>
          <Route path="/" element={<Landing />} />
          <Route path="/features" element={<Features />} />
          <Route path="/about" element={<About />} />
          <Route path="/dashboard" element={<Protected><Dashboard /></Protected>} />
          <Route path="/repositories" element={<Protected><Repositories /></Protected>} />
          <Route path="/analyze" element={<Protected><Analyze /></Protected>} />
          <Route path="/workspace" element={<Protected><Workspace /></Protected>} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </BrowserRouter>
    </AuthProvider>
  );
}
