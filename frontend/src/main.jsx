/**
 * React uygulama giriş noktası.
 *
 * Başlatma sırası:
 *  1. Tailwind CSS (index.css)
 *  2. React 18 createRoot ile DOM'a bağlan
 *  3. App bileşenini render et (StrictMode etkin)
 */

import React from 'react';
import { createRoot } from 'react-dom/client';
import App from './App';
import './index.css';

// ---------------------------------------------------------------------------
// Global ErrorBoundary — herhangi bir render hatası burada yakalanır
// ---------------------------------------------------------------------------

class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false, error: null, info: null };
  }

  static getDerivedStateFromError(error) {
    return { hasError: true, error };
  }

  componentDidCatch(error, info) {
    this.setState({ info });
    console.error('[VulnScan AI] Render hatası:', error, info);
  }

  render() {
    if (this.state.hasError) {
      return (
        <div style={{
          minHeight: '100vh',
          background: '#0a0e1a',
          color: '#f9fafb',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          fontFamily: 'monospace',
          padding: '2rem',
        }}>
          <div style={{ maxWidth: 640, width: '100%' }}>
            <h1 style={{ color: '#ef4444', fontSize: 18, marginBottom: 12 }}>
              ⚠ Uygulama Hatası
            </h1>
            <p style={{ color: '#9ca3af', fontSize: 13, marginBottom: 16 }}>
              Bir render hatası oluştu. Lütfen F5 ile sayfayı yenileyin.
            </p>
            <pre style={{
              background: '#111827',
              border: '1px solid #374151',
              borderRadius: 8,
              padding: 16,
              fontSize: 12,
              color: '#fca5a5',
              overflowX: 'auto',
              whiteSpace: 'pre-wrap',
              wordBreak: 'break-all',
            }}>
              {this.state.error?.toString()}
              {'\n\n'}
              {this.state.info?.componentStack}
            </pre>
            <button
              onClick={() => window.location.reload()}
              style={{
                marginTop: 16,
                padding: '8px 16px',
                background: '#3b82f6',
                color: '#fff',
                border: 'none',
                borderRadius: 6,
                cursor: 'pointer',
                fontSize: 13,
              }}
            >
              Yenile
            </button>
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}

// ---------------------------------------------------------------------------
// Mount
// ---------------------------------------------------------------------------

const container = document.getElementById('root');

if (!container) {
  throw new Error(
    '[VulnScan AI] #root elementi bulunamadı. index.html dosyasını kontrol edin.',
  );
}

createRoot(container).render(
  <React.StrictMode>
    <ErrorBoundary>
      <App />
    </ErrorBoundary>
  </React.StrictMode>,
);
