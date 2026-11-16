import { lazy, Suspense } from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { AppProvider, useApp } from './context/AppContext';
import Navbar from './components/Navbar';
import AuthScreen from './components/AuthScreen';
import Toasts from './components/Toasts';
import LiveStrip from './components/LiveStrip';
import Dashboard from './pages/Dashboard';
import Workers from './pages/Workers';
import WorkerDetail from './pages/WorkerDetail';
import Alerts from './pages/Alerts';
import Devices from './pages/Devices';
import Settings from './pages/Settings';
import WorkerApp from './pages/WorkerApp';
import Users from './pages/Users';
// El visor 3D (three.js) se carga solo al abrir la vista Producto
const Product = lazy(() => import('./pages/Product'));

function AppShell() {
  const { user, isAdmin, token } = useApp();
  if (!user) return <AuthScreen />;
  if (user.role === 'trabajador') return <WorkerApp />;
  return (
    <div className="min-h-screen">
      <Navbar />
      <LiveStrip />
      <Routes>
        <Route path="/" element={<Dashboard />} />
        <Route path="/workers" element={<Workers />} />
        <Route path="/workers/:workerId" element={<WorkerDetail />} />
        <Route path="/alerts" element={<Alerts />} />
        <Route path="/devices" element={<Devices />} />
        <Route path="/producto" element={<Suspense fallback={<div className="page-layout text-sm text-slate-500">Cargando…</div>}><Product /></Suspense>} />
        <Route path="/settings" element={isAdmin ? <Settings /> : <Navigate to="/" replace />} />
        <Route path="/usuarios" element={token ? <Users /> : <Navigate to="/" replace />} />
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
