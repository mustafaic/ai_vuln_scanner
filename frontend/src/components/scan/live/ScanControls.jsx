/**
 * ScanControls — Duraklat / Devam / Durdur kontrol butonları.
 * Pause=turuncu, Resume=yeşil, Stop=kırmızı (inline confirm).
 * Props: scanId (string)
 */

import { useState } from 'react';
import { pauseScan, resumeScan, stopScan } from '../../../api/client';
import useScanStore from '../../../store/scanStore';
import useUiStore from '../../../store/uiStore';

export default function ScanControls({ scanId }) {
  const [busy, setBusy]           = useState(false);
  const [confirmStop, setConfirmStop] = useState(false);
  const activeScan       = useScanStore((s) => s.activeScan);
  const updateActiveScan = useScanStore((s) => s.updateActiveScan);
  const addNotification  = useUiStore((s) => s.addNotification);

  const status    = activeScan?.status;
  const isRunning = status === 'running';
  const isPaused  = status === 'paused';
  const isDone    = ['completed', 'stopped', 'failed'].includes(status);

  if (isDone || !scanId) return null;

  const act = async (fn, optimistic) => {
    if (busy) return;
    setBusy(true);
    try {
      await fn(scanId);
      updateActiveScan({ status: optimistic });
    } catch (err) {
      addNotification({ title: 'Hata', body: err.message, type: 'error' });
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="flex items-center gap-2">
      {isRunning && (
        <button
          onClick={() => act(pauseScan, 'paused')}
          disabled={busy}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium
            bg-orange-500/20 text-orange-400 hover:bg-orange-500/30
            disabled:opacity-50 transition-colors"
        >
          <svg viewBox="0 0 24 24" fill="currentColor" className="w-3.5 h-3.5">
            <rect x="6" y="4" width="4" height="16" rx="1" />
            <rect x="14" y="4" width="4" height="16" rx="1" />
          </svg>
          Duraklat
        </button>
      )}

      {isPaused && (
        <button
          onClick={() => act(resumeScan, 'running')}
          disabled={busy}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium
            bg-green-500/20 text-green-400 hover:bg-green-500/30
            disabled:opacity-50 transition-colors"
        >
          <svg viewBox="0 0 24 24" fill="currentColor" className="w-3.5 h-3.5">
            <polygon points="5,3 19,12 5,21" />
          </svg>
          Devam Et
        </button>
      )}

      {/* Durdur — inline confirm */}
      {!confirmStop ? (
        <button
          onClick={() => setConfirmStop(true)}
          disabled={busy}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium
            bg-red-500/10 text-red-400 hover:bg-red-500/20
            disabled:opacity-50 transition-colors"
        >
          <svg viewBox="0 0 24 24" fill="currentColor" className="w-3.5 h-3.5">
            <rect x="4" y="4" width="16" height="16" rx="2" />
          </svg>
          Durdur
        </button>
      ) : (
        <div className="flex items-center gap-1.5 bg-red-500/10 border border-red-500/30 rounded-lg px-2.5 py-1">
          <span className="text-[10px] text-red-400 whitespace-nowrap">Emin misin?</span>
          <button
            onClick={() => { setConfirmStop(false); act(stopScan, 'stopped'); }}
            disabled={busy}
            className="text-[10px] px-2 py-0.5 rounded bg-red-500 text-white
              hover:bg-red-600 disabled:opacity-50 transition-colors"
          >
            Evet
          </button>
          <button
            onClick={() => setConfirmStop(false)}
            className="text-[10px] text-gray-500 hover:text-gray-300 transition-colors"
          >
            İptal
          </button>
        </div>
      )}
    </div>
  );
}
