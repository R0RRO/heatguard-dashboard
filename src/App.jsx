import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { AppProvider, useApp } from './context/AppContext';
import Navbar from './components/Navbar';
import AuthScreen from './components/AuthScreen';
import Toasts from './components/Toasts';
import Dashboard from './pages/Dashboard';
import Workers from './pages/Workers';
import WorkerDetail from './pages/WorkerDetail';
import MapView from './pages/MapView';
import Alerts from './pages/Alerts';
import Devices from './pages/Devices';
import Settings from './pages/Settings';

function AppShell() {
  const { user } = useApp();
  if (!user) return <AuthScreen />;
  return (
    <div className="min-h-screen">
      <Navbar />
      <Routes>
        <Route path="/" element={<Dashboard />} />
        <Route path="/workers" element={<Workers />} />
        <Route path="/workers/:workerId" element={<WorkerDetail />} />
        <Route path="/map" element={<MapView />} />
        <Route path="/alerts" element={<Alerts />} />
        <Route path="/devices" element={<Devices />} />
        <Route path="/settings" element={user.role === 'supervisor' ? <Navigate to="/" replace /> : <Settings />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
      <Toasts />
    </div>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <AppProvider>
        <AppShell />
      </AppProvider>
    </BrowserRouter>
  );
}
