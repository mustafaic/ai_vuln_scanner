/**
 * ScanLive — Canlı tarama görünümü.
 *
 * Düzen:
 *  Sol: faz navigasyonu (Keşif | URL Keşfi | Test | Log) — aktif olan highlight
 *  Sağ: faza göre içerik
 *    recon    → SubdomainList
 *    discovery → UrlList
 *    testing  → TestPanel + FindingCard listesi
 *    log      → ToolLog
 *
 * WebSocket: useScanWebSocket hook ile bağlanır.
 */

import { useEffect, useState, useRef } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import useScanStore from '../../store/scanStore';
import useUiStore from '../../store/uiStore';
import { useScanWebSocket } from '../../hooks/useWebSocket';
import useScan from '../../hooks/useScan';

import PhaseProgress from '../scan/live/PhaseProgress';
import ScanControls from '../scan/live/ScanControls';
import SubdomainList from '../scan/live/SubdomainList';
import UrlList from '../scan/live/UrlList';
import TestPanel from '../scan/live/TestPanel';
import FindingCard from '../scan/live/FindingCard';

// ---------------------------------------------------------------------------
// Tool log
// ---------------------------------------------------------------------------

const LOG_COLORS = {
  start: 'text-blue-400', done: 'text-green-400', output: 'text-gray-400',
  error: 'text-red-400',  warn: 'text-yellow-400', phase: 'text-purple-400',
  info:  'text-gray-500',
};

function ToolLog() {
  const toolLog   = useScanStore((s) => s.toolLog);
  const bottomRef = useRef(null);
  const [autoScroll, setAutoScroll] = useState(true);

  useEffect(() => {
    if (autoScroll) bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [toolLog, autoScroll]);

  return (
    <div className="flex flex-col h-full">
      <div className="flex items-center justify-between px-3 py-1.5 border-b border-[#374151] flex-shrink-0">
        <span className="text-[10px] text-gray-500 uppercase tracking-wider">Araç Logu</span>
        <label className="flex items-center gap-1.5 text-[10px] text-gray-500 cursor-pointer">
          <input
            type="checkbox"
            checked={autoScroll}
            onChange={(e) => setAutoScroll(e.target.checked)}
            className="accent-blue-500 w-3 h-3"
          />
          Otomatik kaydır
        </label>
      </div>
      <div className="flex-1 overflow-y-auto p-3 font-mono text-[10px] space-y-0.5">
        {toolLog.length === 0 ? (
          <p className="text-gray-600">Log bekleniyor…</p>
        ) : toolLog.map((entry) => (
          <div key={entry.id} className={`leading-relaxed ${LOG_COLORS[entry.type] ?? 'text-gray-400'}`}>
            <span className="text-gray-600 select-none mr-1.5">
              {new Date(entry.time).toLocaleTimeString()}
            </span>
            {entry.tool && (
              <span className="text-gray-600 mr-1.5">[{entry.tool}]</span>
            )}
            <span>{entry.message}</span>
          </div>
        ))}
        <div ref={bottomRef} />
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Faz nav tanımları
// ---------------------------------------------------------------------------

const PHASE_NAV = [
  {
    id: 'recon',
    label: 'Keşif',
    sublabel: 'Recon',
    icon: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8} className="w-4 h-4">
        <circle cx="11" cy="11" r="8" />
        <line x1="21" y1="21" x2="16.65" y2="16.65" />
      </svg>
    ),
    phase: 'recon',
  },
  {
    id: 'discovery',
    label: 'URL Keşfi',
    sublabel: 'Discovery',
    icon: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8} className="w-4 h-4">
        <path d="M10 13a5 5 0 007.54.54l3-3a5 5 0 00-7.07-7.07l-1.72 1.71" />
        <path d="M14 11a5 5 0 00-7.54-.54l-3 3a5 5 0 007.07 7.07l1.71-1.71" />
      </svg>
    ),
    phase: 'discovery',
  },
  {
    id: 'testing',
    label: 'Test',
    sublabel: 'Testing',
    icon: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8} className="w-4 h-4">
        <polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2" />
      </svg>
    ),
    phase: 'testing',
  },
  {
    id: 'log',
    label: 'Log',
    sublabel: 'Araç Logu',
    icon: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8} className="w-4 h-4">
        <path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z" />
        <polyline points="14 2 14 8 20 8" />
        <line x1="16" y1="13" x2="8" y2="13" />
        <line x1="16" y1="17" x2="8" y2="17" />
        <polyline points="10 9 9 9 8 9" />
      </svg>
    ),
    phase: null,
  },
];

const PHASE_ORDER = ['recon', 'discovery', 'testing'];

// ---------------------------------------------------------------------------
// Ana bileşen
// ---------------------------------------------------------------------------

export default function ScanLive() {
  const { id: scanId } = useParams();
  const navigate       = useNavigate();

  const { loadScan }   = useScan();
  const { wsStatus }   = useScanWebSocket(scanId);

  const activeScan    = useScanStore((s) => s.activeScan);
  const subdomains    = useScanStore((s) => s.subdomains);
  const urls          = useScanStore((s) => s.urls);
  const findings      = useScanStore((s) => s.findings);
  const currentPhase  = useScanStore((s) => s.currentPhase);
  const toolLog       = useScanStore((s) => s.toolLog);

  const setChatContext = useUiStore((s) => s.setChatContext);

  // Aktif görünüm — currentPhase'e göre otomatik başlar, kullanıcı değiştirebilir
  const [view, setView] = useState('recon');
  const [testUrlIds, setTestUrlIds] = useState([]);

  // Sayfa yüklenmesinde scan verisini çek
  useEffect(() => {
    if (scanId) loadScan(scanId).catch(() => {});
  }, [scanId, loadScan]);

  // currentPhase değişince view'i otomatik güncelle (ilk kez)
  const autoSwitched = useRef(false);
  useEffect(() => {
    if (currentPhase && !autoSwitched.current) {
      setView(currentPhase);
    }
  }, [currentPhase]);

  const scanStatus = activeScan?.status;
  const currentPhaseIndex = PHASE_ORDER.indexOf(currentPhase ?? '');

  const getPhaseState = (phaseId) => {
    if (!phaseId) return 'pending'; // log nav item
    const i = PHASE_ORDER.indexOf(phaseId);
    if (scanStatus === 'completed') return 'completed';
    if (currentPhaseIndex === -1) return 'pending';
    if (i < currentPhaseIndex) return 'completed';
    if (i === currentPhaseIndex) return 'active';
    return 'pending';
  };

  const counts = {
    recon:     subdomains.length,
    discovery: urls.length,
    testing:   findings.length,
    log:       toolLog.length,
  };

  const handleSelectForTest = (urlIds) => {
    setTestUrlIds(urlIds);
    setView('testing');
    autoSwitched.current = true;
  };

  const handleSelectionDone = () => {
    setView('discovery');
    autoSwitched.current = true;
  };

  return (
    <div className="flex h-full overflow-hidden">

      {/* ── Sol: faz navigasyonu ── */}
      <aside className="w-44 flex-shrink-0 bg-[#111827] border-r border-[#374151] flex flex-col">

        {/* Scan meta */}
        <div className="px-3 py-3 border-b border-[#374151]">
          <div className="flex items-center gap-1.5 mb-1.5">
            {/* WS dot */}
            <span className={`w-1.5 h-1.5 rounded-full flex-shrink-0 ${
              wsStatus === 'connected'  ? 'bg-green-400'
              : wsStatus === 'connecting' ? 'bg-yellow-400 animate-pulse-dot'
              : 'bg-red-400'
            }`} title={`WebSocket: ${wsStatus}`} />
            <span className={`text-[10px] font-medium ${
              scanStatus === 'running'   ? 'text-blue-400'
              : scanStatus === 'paused'  ? 'text-orange-400'
              : scanStatus === 'completed' ? 'text-green-400'
              : scanStatus === 'stopped' ? 'text-red-400'
              : 'text-gray-500'
            }`}>
              {scanStatus === 'running'   ? 'Çalışıyor'
               : scanStatus === 'paused'  ? 'Duraklatıldı'
               : scanStatus === 'completed' ? 'Tamamlandı'
               : scanStatus === 'stopped' ? 'Durduruldu'
               : scanStatus === 'failed'  ? 'Başarısız'
               : 'Bekleniyor'}
            </span>
          </div>
          {activeScan && (
            <p className="text-[10px] font-mono text-gray-400 truncate" title={activeScan.target}>
              {activeScan.target}
            </p>
          )}
        </div>

        {/* Faz nav butonları */}
        <nav className="flex-1 py-2">
          {PHASE_NAV.map((item) => {
            const state   = getPhaseState(item.phase);
            const isActive = view === item.id;
            const count   = counts[item.id];

            return (
              <button
                key={item.id}
                onClick={() => { setView(item.id); autoSwitched.current = true; }}
                className={`
                  w-full flex items-center gap-2.5 px-3 py-2.5
                  text-left transition-colors text-xs
                  ${isActive
                    ? 'bg-blue-500/15 text-white border-r-2 border-blue-500'
                    : 'text-gray-500 hover:text-gray-300 hover:bg-[#1f2937]'}
                `}
              >
                {/* Phase state indicator */}
                <span className={`flex-shrink-0 ${
                  isActive ? 'text-blue-400'
                  : state === 'completed' ? 'text-green-400'
                  : state === 'active' ? 'text-blue-400'
                  : 'text-gray-600'
                }`}>
                  {state === 'completed' && item.phase ? (
                    <svg viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth={2.5} className="w-4 h-4">
                      <polyline points="1,6 4,9 11,3" />
                    </svg>
                  ) : state === 'active' && item.phase ? (
                    <div className="w-4 h-4 border-2 border-blue-400 border-t-transparent rounded-full animate-spin" />
                  ) : (
                    item.icon
                  )}
                </span>

                <div className="flex-1 min-w-0">
                  <div className="flex items-center justify-between gap-1">
                    <span className={`font-medium leading-tight ${isActive ? 'text-white' : ''}`}>
                      {item.label}
                    </span>
                    {count > 0 && (
                      <span className={`text-[9px] px-1 rounded tabular-nums flex-shrink-0 ${
                        isActive ? 'bg-blue-500/30 text-blue-300' : 'bg-[#374151] text-gray-600'
                      }`}>
                        {count}
                      </span>
                    )}
                  </div>
                  <span className={`text-[9px] font-mono leading-tight ${isActive ? 'text-blue-400/70' : 'text-gray-700'}`}>
                    {item.sublabel}
                  </span>
                </div>
              </button>
            );
          })}
        </nav>

        {/* Faz ilerleme (alt) */}
        <div className="p-3 border-t border-[#374151]">
          <PhaseProgress />
        </div>
      </aside>

      {/* ── Sağ: içerik + kontrol bar ── */}
      <div className="flex-1 flex flex-col overflow-hidden">

        {/* Kontrol bar */}
        <div className="flex items-center justify-between px-4 py-2.5 bg-[#111827] border-b border-[#374151] flex-shrink-0">
          <div className="flex items-center gap-3 min-w-0">
            <button
              onClick={() => navigate('/')}
              className="text-gray-600 hover:text-gray-400 transition-colors flex-shrink-0"
            >
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} className="w-4 h-4">
                <line x1="19" y1="12" x2="5" y2="12" />
                <polyline points="12 19 5 12 12 5" />
              </svg>
            </button>
            <div className="min-w-0">
              <p className="text-xs font-semibold text-white truncate">
                {activeScan?.name || activeScan?.target || 'Tarama Yükleniyor…'}
              </p>
              {activeScan && (
                <p className="text-[10px] text-gray-600">
                  {activeScan.scope === 'subdomains' ? 'Subdomainler dahil' : 'Tek domain'}
                  {' · '}{activeScan.mode}
                  {currentPhase && ` · ${currentPhase}`}
                </p>
              )}
            </div>
          </div>
          <ScanControls scanId={scanId} />
        </div>

        {/* Faz içeriği */}
        <div className="flex-1 overflow-hidden">

          {/* recon → SubdomainList */}
          {view === 'recon' && (
            <div className="h-full">
              {subdomains.length > 0 || currentPhase === 'recon' ? (
                <SubdomainList
                  scanId={scanId}
                  onSelectionDone={handleSelectionDone}
                />
              ) : (
                <EmptyView message="Subdomain keşfi başladığında burası dolacak." />
              )}
            </div>
          )}

          {/* discovery → UrlList */}
          {view === 'discovery' && (
            <div className="h-full">
              {urls.length > 0 ? (
                <UrlList onSelectForTest={handleSelectForTest} />
              ) : (
                <EmptyView message="URL keşfi başladığında burası dolacak." />
              )}
            </div>
          )}

          {/* testing → TestPanel + FindingCard listesi */}
          {view === 'testing' && (
            <div className="h-full flex gap-0 overflow-hidden">
              {/* Test paneli */}
              <div className="w-96 flex-shrink-0 border-r border-[#374151] overflow-auto">
                <TestPanel
                  scanId={scanId}
                  selectedUrlIds={testUrlIds}
                  onStarted={() => {}}
                />
              </div>

              {/* Bulgular listesi */}
              <div className="flex-1 overflow-auto p-4 space-y-2">
                {findings.length === 0 ? (
                  <EmptyView message="Test başladığında bulgular burada görünür." />
                ) : (
                  <>
                    {/* Severity özeti */}
                    <div className="flex items-center gap-2 flex-wrap mb-2">
                      {['critical', 'high', 'medium', 'low', 'info'].map((sev) => {
                        const count = findings.filter((f) => f.severity === sev).length;
                        if (!count) return null;
                        return (
                          <span key={sev} className={`text-[10px] px-2 py-0.5 rounded font-medium ${
                            sev === 'critical' ? 'bg-red-500/20 text-red-400'
                            : sev === 'high'   ? 'bg-orange-500/20 text-orange-400'
                            : sev === 'medium' ? 'bg-yellow-500/20 text-yellow-400'
                            : sev === 'low'    ? 'bg-green-500/20 text-green-400'
                            : 'bg-blue-500/20 text-blue-400'
                          }`}>
                            {count} {sev}
                          </span>
                        );
                      })}
                    </div>
                    {findings.map((f) => (
                      <FindingCard
                        key={f.id}
                        finding={f}
                        onContextSet={() => setChatContext({ type: 'finding', data: f })}
                      />
                    ))}
                  </>
                )}
              </div>
            </div>
          )}

          {/* log → ToolLog */}
          {view === 'log' && (
            <div className="h-full">
              <ToolLog />
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function EmptyView({ message }) {
  return (
    <div className="flex items-center justify-center h-full text-gray-600 text-sm p-8 text-center">
      <div className="space-y-2">
        <div className="w-12 h-12 rounded-full bg-[#1f2937] flex items-center justify-center mx-auto text-2xl opacity-50">
          ⏳
        </div>
        <p>{message}</p>
      </div>
    </div>
  );
}
