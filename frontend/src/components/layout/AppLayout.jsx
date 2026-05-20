/**
 * AppLayout — Tüm sayfalara sarmalayan ana düzen.
 *
 * Yapı (Spec Bölüm 12.3):
 *   TopBar (üst, tam genişlik)
 *   ├─ Sidebar (sol, daraltılabilir)
 *   ├─ Ana içerik alanı (<Outlet />)
 *   └─ AI Chat paneli (sağ, gizlenebilir)
 *
 * Modal'lar: WAF Bypass modal'ı burada render edilir.
 * Bildirimler: NotificationToast burada render edilir.
 */

import { Outlet } from 'react-router-dom';
import { lazy, Suspense, useEffect } from 'react';

import Sidebar from './Sidebar';
import TopBar from './TopBar';
import NotificationToast from '../shared/NotificationToast';
import AiChatPanel from '../shared/AiChatPanel';
import useUiStore from '../../store/uiStore';
import useToolStore from '../../store/toolStore';
import WafBypassModal from './WafBypassModal';

export default function AppLayout() {
  const aiPanelOpen = useUiStore((s) => s.aiPanelOpen);
  const activeModal = useUiStore((s) => s.activeModal);
  const fetchToolStatus = useToolStore((s) => s.fetchToolStatus);

  // İlk yüklemede araç durumunu çek
  useEffect(() => {
    fetchToolStatus();
  }, [fetchToolStatus]);

  return (
    <div className="flex flex-col h-screen overflow-hidden bg-[#0a0e1a]">
      {/* Üst çubuk */}
      <TopBar />

      {/* Gövde: Sidebar + İçerik + AI Panel */}
      <div className="flex flex-1 overflow-hidden">
        {/* Sol navigasyon */}
        <Sidebar />

        {/* Ana içerik */}
        <main className="flex-1 overflow-auto min-w-0">
          <Outlet />
        </main>

        {/* Sağ AI paneli */}
        <div
          className={`
            panel-transition border-l border-[#374151] flex-shrink-0
            ${aiPanelOpen ? 'w-72 opacity-100' : 'w-0 opacity-0'}
          `}
        >
          {aiPanelOpen && <AiChatPanel />}
        </div>
      </div>

      {/* Bildirimler */}
      <NotificationToast />

      {/* WAF Bypass modal */}
      {activeModal?.id === 'waf_bypass' && <WafBypassModal />}
    </div>
  );
}
