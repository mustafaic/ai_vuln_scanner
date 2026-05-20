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

const container = document.getElementById('root');

if (!container) {
  throw new Error(
    '[VulnScan AI] #root elementi bulunamadı. index.html dosyasını kontrol edin.',
  );
}

createRoot(container).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
