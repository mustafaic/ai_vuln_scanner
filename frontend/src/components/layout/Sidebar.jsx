/**
 * Sidebar — Sol navigasyon paneli.
 *
 * Özellikler:
 *  - VulnScan AI logo
 *  - Navigasyon linkleri (Dashboard, Yeni Tarama, Taramalar, Raporlar)
 *  - Aktif link highlight (React Router useLocation)
 *  - Daraltılabilir: geniş (isim + ikon) ↔ dar (sadece ikon)
 */

import { NavLink, useLocation } from 'react-router-dom';
import useUiStore from '../../store/uiStore';

const NAV_ITEMS = [
  {
    to: '/',
    label: 'Dashboard',
    icon: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8} className="w-4 h-4">
        <rect x="3" y="3" width="7" height="7" rx="1" />
        <rect x="14" y="3" width="7" height="7" rx="1" />
        <rect x="3" y="14" width="7" height="7" rx="1" />
        <rect x="14" y="14" width="7" height="7" rx="1" />
      </svg>
    ),
    exact: true,
  },
  {
    to: '/scan/new',
    label: 'Yeni Tarama',
    icon: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8} className="w-4 h-4">
        <circle cx="11" cy="11" r="8" />
        <line x1="21" y1="21" x2="16.65" y2="16.65" />
        <line x1="11" y1="8" x2="11" y2="14" />
        <line x1="8" y1="11" x2="14" y2="11" />
      </svg>
    ),
  },
  {
    to: '/scans',
    label: 'Taramalar',
    icon: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8} className="w-4 h-4">
        <polyline points="22 12 18 12 15 21 9 3 6 12 2 12" />
      </svg>
    ),
  },
  {
    to: '/reports',
    label: 'Raporlar',
    icon: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8} className="w-4 h-4">
        <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
        <polyline points="14 2 14 8 20 8" />
        <line x1="16" y1="13" x2="8" y2="13" />
        <line x1="16" y1="17" x2="8" y2="17" />
        <polyline points="10 9 9 9 8 9" />
      </svg>
    ),
  },
];

export default function Sidebar() {
  const sidebarOpen = useUiStore((s) => s.sidebarOpen);
  const toggleSidebar = useUiStore((s) => s.toggleSidebar);
  const location = useLocation();

  return (
    <aside
      className={`
        flex flex-col bg-[#111827] border-r border-[#374151]
        transition-all duration-200 flex-shrink-0
        ${sidebarOpen ? 'w-48' : 'w-14'}
      `}
    >
      {/* Logo + toggle */}
      <div
        className={`
          flex items-center border-b border-[#374151] h-12 px-3
          ${sidebarOpen ? 'justify-between' : 'justify-center'}
        `}
      >
        {sidebarOpen && (
          <div className="flex items-center gap-2 min-w-0">
            <div className="w-6 h-6 rounded bg-blue-600 flex items-center justify-center flex-shrink-0">
              <svg viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth={2} className="w-3.5 h-3.5">
                <path d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5" />
              </svg>
            </div>
            <span className="text-xs font-bold text-white truncate">
              VulnScan AI
            </span>
          </div>
        )}

        {!sidebarOpen && (
          <div className="w-6 h-6 rounded bg-blue-600 flex items-center justify-center">
            <svg viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth={2} className="w-3.5 h-3.5">
              <path d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5" />
            </svg>
          </div>
        )}

        {sidebarOpen && (
          <button
            onClick={toggleSidebar}
            className="text-gray-500 hover:text-gray-300 flex-shrink-0"
            title="Daralt"
          >
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8} className="w-4 h-4">
              <polyline points="15 18 9 12 15 6" />
            </svg>
          </button>
        )}
      </div>

      {/* Daraltılmış modda logo tıklanabilir toggle */}
      {!sidebarOpen && (
        <button
          onClick={toggleSidebar}
          className="flex justify-center py-2 text-gray-500 hover:text-gray-300"
          title="Genişlet"
        >
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8} className="w-4 h-4">
            <polyline points="9 18 15 12 9 6" />
          </svg>
        </button>
      )}

      {/* Navigasyon */}
      <nav className="flex-1 py-2 overflow-y-auto overflow-x-hidden">
        {NAV_ITEMS.map((item) => {
          const isActive = item.exact
            ? location.pathname === item.to
            : location.pathname.startsWith(item.to);

          return (
            <NavLink
              key={item.to}
              to={item.to}
              title={!sidebarOpen ? item.label : undefined}
              className={`
                flex items-center gap-3 px-3 py-2 mx-1 rounded-md
                text-xs font-medium transition-colors
                ${isActive
                  ? 'bg-blue-600/20 text-blue-400'
                  : 'text-gray-400 hover:text-gray-200 hover:bg-[#1f2937]'
                }
                ${!sidebarOpen ? 'justify-center' : ''}
              `}
            >
              <span className="flex-shrink-0">{item.icon}</span>
              {sidebarOpen && (
                <span className="truncate">{item.label}</span>
              )}
            </NavLink>
          );
        })}
      </nav>

      {/* Alt bilgi */}
      {sidebarOpen && (
        <div className="px-3 py-2 border-t border-[#374151]">
          <p className="text-[10px] text-gray-600">VulnScan AI v1.0</p>
        </div>
      )}
    </aside>
  );
}
