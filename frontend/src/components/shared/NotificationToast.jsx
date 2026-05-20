/**
 * NotificationToast — Ekranın sağ alt köşesinde yığılan toast bildirimleri.
 *
 * uiStore.notifications dizisini izler; her bildirim için bir kart render eder.
 * Tipler: 'info' | 'success' | 'warning' | 'error'
 */

import { useEffect, useRef } from 'react';
import useUiStore from '../../store/uiStore';

// Tip → ikon + renk
const TYPE_CONFIG = {
  success: {
    icon: '✓',
    border: 'border-green-500',
    bg: 'bg-green-500/10',
    text: 'text-green-400',
  },
  error: {
    icon: '✗',
    border: 'border-red-500',
    bg: 'bg-red-500/10',
    text: 'text-red-400',
  },
  warning: {
    icon: '⚠',
    border: 'border-yellow-500',
    bg: 'bg-yellow-500/10',
    text: 'text-yellow-400',
  },
  info: {
    icon: 'ℹ',
    border: 'border-blue-500',
    bg: 'bg-blue-500/10',
    text: 'text-blue-400',
  },
};

function ToastItem({ notif, onRemove }) {
  const cfg = TYPE_CONFIG[notif.type] ?? TYPE_CONFIG.info;
  const timerRef = useRef(null);

  // Progress çubuğu animasyonu için kalan süreyi takip etmiyoruz;
  // sadece uiStore'daki auto-dismiss setTimeout yeterli.
  // Kullanıcı manuel kapatabilir.

  return (
    <div
      className={`
        flex items-start gap-3 p-3 rounded-lg border
        bg-[#111827] ${cfg.border} ${cfg.bg}
        shadow-lg min-w-[280px] max-w-[380px]
        animate-slide-in
      `}
      role="alert"
    >
      {/* İkon */}
      <span className={`text-base font-bold mt-0.5 flex-shrink-0 ${cfg.text}`}>
        {cfg.icon}
      </span>

      {/* İçerik */}
      <div className="flex-1 min-w-0">
        <p className="text-sm font-medium text-gray-100 leading-tight">
          {notif.title}
        </p>
        {notif.body && (
          <p className="text-xs text-gray-400 mt-0.5 leading-snug">
            {notif.body}
          </p>
        )}
      </div>

      {/* Kapat */}
      <button
        onClick={() => onRemove(notif.id)}
        className="flex-shrink-0 text-gray-500 hover:text-gray-300 text-xs ml-1 mt-0.5"
        aria-label="Kapat"
      >
        ✕
      </button>
    </div>
  );
}

export default function NotificationToast() {
  const notifications = useUiStore((s) => s.notifications);
  const removeNotification = useUiStore((s) => s.removeNotification);

  if (!notifications.length) return null;

  return (
    <div
      className="fixed bottom-4 right-4 z-50 flex flex-col gap-2 pointer-events-none"
      aria-live="polite"
      aria-atomic="false"
    >
      {notifications.map((n) => (
        <div key={n.id} className="pointer-events-auto">
          <ToastItem notif={n} onRemove={removeNotification} />
        </div>
      ))}
    </div>
  );
}
