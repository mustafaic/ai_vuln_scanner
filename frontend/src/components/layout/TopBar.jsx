/**
 * TopBar — Üst bilgi çubuğu.
 *
 * Gösterir:
 *  - Aktif tarama varsa: hedef, faz, ilerleme çubuğu, Duraklat/Devam/Durdur
 *  - Araç özeti: kaç araç kurulu / toplam
 *  - AI paneli aç/kapat butonu
 */

import { useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import useScanStore from '../../store/scanStore';
import useUiStore from '../../store/uiStore';
import useToolStore from '../../store/toolStore';
import { pauseScan, resumeScan, stopScan } from '../../api/client';

const PHASE_LABEL = {
  recon: 'Keşif',
  discovery: 'URL Keşfi',
  testing: 'Test',
};

const STATUS_COLOR = {
  running: 'text-blue-400',
  paused: 'text-purple-400',
  completed: 'text-green-400',
  failed: 'text-red-400',
  stopped: 'text-gray-400',
  pending: 'text-yellow-400',
};

export default function TopBar() {
  const activeScan = useScanStore((s) => s.activeScan);
  const progress = useScanStore((s) => s.progress);
  const currentPhase = useScanStore((s) => s.currentPhase);
  const wsStatus = useScanStore((s) => s.wsStatus);
  const updateActiveScan = useScanStore((s) => s.updateActiveScan);

  const aiPanelOpen = useUiStore((s) => s.aiPanelOpen);
  const toggleAiPanel = useUiStore((s) => s.toggleAiPanel);
  const addNotification = useUiStore((s) => s.addNotification);

  const tools = useToolStore((s) => s.tools);
  const toolList = Object.values(tools);
  const installedCount = toolList.filter((t) => t.installed).length;
  const totalCount = toolList.length;

  const navigate = useNavigate();

  const handlePause = useCallback(async () => {
    if (!activeScan) return;
    try {
      await pauseScan(activeScan.id);
      updateActiveScan({ status: 'paused' });
    } catch (err) {
      addNotification({ title: 'Hata', body: err.message, type: 'error' });
    }
  }, [activeScan, updateActiveScan, addNotification]);

  const handleResume = useCallback(async () => {
    if (!activeScan) return;
    try {
      await resumeScan(activeScan.id);
      updateActiveScan({ status: 'running' });
    } catch (err) {
      addNotification({ title: 'Hata', body: err.message, type: 'error' });
    }
  }, [activeScan, updateActiveScan, addNotification]);

  const handleStop = useCallback(async () => {
    if (!activeScan) return;
    if (!window.confirm(`"${activeScan.target}" taramasını durdurmak istiyor musunuz?`)) return;
    try {
      await stopScan(activeScan.id);
      updateActiveScan({ status: 'stopped' });
    } catch (err) {
      addNotification({ title: 'Hata', body: err.message, type: 'error' });
    }
  }, [activeScan, updateActiveScan, addNotification]);

  const isRunning = activeScan?.status === 'running';
  const isPaused = activeScan?.status === 'paused';
  const isActive = isRunning || isPaused;

  return (
    <header className="h-12 bg-[#111827] border-b border-[#374151] flex items-center px-4 gap-4 flex-shrink-0">

      {/* Aktif tarama bilgisi */}
      {activeScan && isActive ? (
        <div className="flex items-center gap-3 flex-1 min-w-0">
          {/* Durum göstergesi */}
          <div className="flex items-center gap-1.5">
            <span
              className={`w-2 h-2 rounded-full flex-shrink-0 ${
                isRunning ? 'bg-blue-400 animate-pulse-dot' : 'bg-purple-400'
              }`}
            />
            <span
              className={`text-xs font-mono font-medium truncate max-w-[140px] ${
                STATUS_COLOR[activeScan.status] ?? 'text-gray-400'
              }`}
              title={activeScan.target}
            >
              {activeScan.target}
            </span>
          </div>

          {/* Faz */}
          {currentPhase && (
            <span className="text-[10px] text-gray-500 flex-shrink-0 hidden sm:block">
              {PHASE_LABEL[currentPhase] ?? currentPhase}
            </span>
          )}

          {/* İlerleme çubuğu */}
          <div className="flex-1 max-w-[120px] hidden md:block">
            <div className="h-1 bg-[#374151] rounded-full overflow-hidden">
              <div
                className="h-full bg-blue-500 risk-score-bar"
                style={{ width: `${progress}%` }}
              />
            </div>
          </div>

          {/* Yüzde */}
          <span className="text-[10px] text-gray-500 flex-shrink-0">
            {progress}%
          </span>

          {/* Kontrol butonları */}
          <div className="flex items-center gap-1 flex-shrink-0">
            {isRunning && (
              <button
                onClick={handlePause}
                className="px-2 py-1 rounded text-[10px] bg-purple-500/20 text-purple-400 hover:bg-purple-500/30 transition-colors"
              >
                Duraklat
              </button>
            )}
            {isPaused && (
              <button
                onClick={handleResume}
                className="px-2 py-1 rounded text-[10px] bg-blue-500/20 text-blue-400 hover:bg-blue-500/30 transition-colors"
              >
                Devam
              </button>
            )}
            <button
              onClick={handleStop}
              className="px-2 py-1 rounded text-[10px] bg-red-500/10 text-red-400 hover:bg-red-500/20 transition-colors"
            >
              Durdur
            </button>
            <button
              onClick={() => navigate(`/scan/${activeScan.id}`)}
              className="px-2 py-1 rounded text-[10px] bg-[#1f2937] text-gray-400 hover:text-gray-200 transition-colors"
            >
              Görüntüle →
            </button>
          </div>
        </div>
      ) : (
        /* Aktif tarama yoksa boşluk */
        <div className="flex-1" />
      )}

      {/* WS bağlantı durumu — sadece aktif taramada göster */}
      {activeScan && (
        <div
          className="flex items-center gap-1 flex-shrink-0"
          title={`WebSocket: ${wsStatus}`}
        >
          <span
            className={`w-1.5 h-1.5 rounded-full ${
              wsStatus === 'connected'
                ? 'bg-green-400'
                : wsStatus === 'connecting'
                ? 'bg-yellow-400 animate-pulse-dot'
                : 'bg-red-400'
            }`}
          />
          <span className="text-[10px] text-gray-600 hidden lg:block">WS</span>
        </div>
      )}

      {/* Araç özeti */}
      {totalCount > 0 && (
        <button
          onClick={() => navigate('/scans')}
          className="flex items-center gap-1.5 flex-shrink-0 text-[10px] text-gray-500 hover:text-gray-300 transition-colors"
          title="Araç Durumu"
        >
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8} className="w-3.5 h-3.5">
            <path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z" />
          </svg>
          <span>
            <span className={installedCount < totalCount ? 'text-yellow-400' : 'text-green-400'}>
              {installedCount}
            </span>
            /{totalCount}
          </span>
        </button>
      )}

      {/* AI Panel toggle */}
      <button
        onClick={toggleAiPanel}
        title={aiPanelOpen ? 'AI panelini gizle' : 'AI panelini aç'}
        className={`
          flex items-center gap-1.5 px-2 py-1 rounded text-xs flex-shrink-0
          transition-colors
          ${aiPanelOpen
            ? 'bg-blue-600/20 text-blue-400'
            : 'text-gray-500 hover:text-gray-300 hover:bg-[#1f2937]'
          }
        `}
      >
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8} className="w-4 h-4">
          <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
        </svg>
        <span className="hidden sm:block">AI</span>
      </button>
    </header>
  );
}
