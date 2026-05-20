/**
 * Uygulama kök bileşeni — React Router tanımları.
 *
 * Rotalar:
 *   /              → Dashboard
 *   /scan/new      → ScanNew (wizard)
 *   /scan/:id      → ScanLive (canlı tarama)
 *   /scans         → ScanHistory
 *   /reports       → Reports
 *   *              → 404 fallback
 *
 * Tüm rotalar AppLayout sarmalayıcısı içinde render edilir
 * (Sidebar + TopBar + AI Chat Panel).
 */

import { BrowserRouter, Routes, Route } from 'react-router-dom';
import { Suspense, lazy } from 'react';

// Lazy load — büyük sayfa bileşenleri ilk yüklemede alınmaz
const AppLayout   = lazy(() => import('./components/layout/AppLayout'));
const Dashboard   = lazy(() => import('./components/pages/Dashboard'));
const ScanNew     = lazy(() => import('./components/pages/ScanNew'));
const ScanLive    = lazy(() => import('./components/pages/ScanLive'));
const ScanHistory = lazy(() => import('./components/pages/ScanHistory'));
const Reports     = lazy(() => import('./components/pages/Reports'));

// ---------------------------------------------------------------------------
// Yükleniyor ekranı
// ---------------------------------------------------------------------------

function PageLoader() {
  return (
    <div className="flex items-center justify-center h-screen bg-[#0a0e1a]">
      <div className="flex flex-col items-center gap-3">
        <div className="w-8 h-8 border-2 border-blue-500 border-t-transparent rounded-full animate-spin" />
        <span className="text-sm text-gray-400">Yükleniyor...</span>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// 404
// ---------------------------------------------------------------------------

function NotFound() {
  return (
    <div className="flex flex-col items-center justify-center flex-1 gap-4 p-8 text-center">
      <p className="text-7xl font-bold text-gray-800">404</p>
      <p className="text-lg text-gray-400">Sayfa bulunamadı.</p>
      <a href="/" className="text-sm text-blue-400 hover:underline">
        Ana sayfaya dön →
      </a>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Uygulama
// ---------------------------------------------------------------------------

export default function App() {
  return (
    <BrowserRouter>
      <Suspense fallback={<PageLoader />}>
        <Routes>
          {/*
            AppLayout tüm alt rotaları sarar.
            Alt rotalar <Outlet /> ile render edilir (AppLayout içinde).
          */}
          <Route path="/" element={<AppLayout />}>
            <Route index element={<Dashboard />} />
            <Route path="scan/new" element={<ScanNew />} />
            <Route path="scan/:id" element={<ScanLive />} />
            <Route path="scans" element={<ScanHistory />} />
            <Route path="reports" element={<Reports />} />
            <Route path="*" element={<NotFound />} />
          </Route>
        </Routes>
      </Suspense>
    </BrowserRouter>
  );
}
