/**
 * FindingCard — Tek bir bulgu kartı (Spec Bölüm 12.6).
 *
 * Özellikler:
 *  - Severity badge (renk)
 *  - AI güven skoru progress bar
 *  - Payload, kanıt, AI analiz, PoC adımları
 *  - "Onayla" / "False Positive" / "PoC Oluştur" butonları
 */

import { useState } from 'react';
import { updateFinding, aiGeneratePoc } from '../../../api/client';
import useUiStore from '../../../store/uiStore';

const SEV_CONFIG = {
  critical: {
    bg: 'bg-red-500/10', border: 'border-red-500/50',
    text: 'text-red-400', badge: 'bg-red-500/20 text-red-400',
    bar: 'bg-red-500',
  },
  high: {
    bg: 'bg-orange-500/10', border: 'border-orange-500/40',
    text: 'text-orange-400', badge: 'bg-orange-500/20 text-orange-400',
    bar: 'bg-orange-500',
  },
  medium: {
    bg: 'bg-yellow-500/10', border: 'border-yellow-500/40',
    text: 'text-yellow-400', badge: 'bg-yellow-500/20 text-yellow-400',
    bar: 'bg-yellow-500',
  },
  low: {
    bg: 'bg-green-500/10', border: 'border-green-500/30',
    text: 'text-green-400', badge: 'bg-green-500/20 text-green-400',
    bar: 'bg-green-500',
  },
  info: {
    bg: 'bg-blue-500/10', border: 'border-blue-500/30',
    text: 'text-blue-400', badge: 'bg-blue-500/20 text-blue-400',
    bar: 'bg-blue-500',
  },
};

const VULN_LABEL = {
  xss: 'XSS', sqli: 'SQLi', lfi: 'LFI', redirect: 'Redirect',
  ssrf: 'SSRF', idor: 'IDOR', rce: 'RCE', info: 'Info', other: 'Other',
};

const STATUS_CONFIG = {
  new:            { label: 'Yeni',           cls: 'bg-blue-500/20 text-blue-400 border-blue-500/30' },
  confirmed:      { label: 'Doğrulandı',     cls: 'bg-green-500/20 text-green-400 border-green-500/30' },
  false_positive: { label: 'Yanlış Pozitif', cls: 'bg-gray-500/20 text-gray-400 border-gray-500/20' },
};

export default function FindingCard({ finding, onContextSet }) {
  const [expanded, setExpanded]   = useState(false);
  const [status, setStatus]       = useState(finding.status ?? 'new');
  const [notes, setNotes]         = useState(finding.notes ?? '');
  const [saving, setSaving]       = useState(false);
  const [pocLoading, setPocLoading] = useState(false);
  const [pocContent, setPocContent] = useState(null);
  const addNotification = useUiStore((s) => s.addNotification);

  const sev = SEV_CONFIG[finding.severity] ?? SEV_CONFIG.info;

  const saveStatus = async (newStatus) => {
    setSaving(true);
    try {
      await updateFinding(finding.id, { status: newStatus, notes });
      setStatus(newStatus);
      addNotification({ title: 'Durum güncellendi', type: 'success', duration: 2000 });
    } catch (err) {
      addNotification({ title: 'Güncelleme Hatası', body: err.message, type: 'error' });
    } finally {
      setSaving(false);
    }
  };

  const saveNotes = async () => {
    setSaving(true);
    try {
      await updateFinding(finding.id, { notes });
      addNotification({ title: 'Not kaydedildi', type: 'success', duration: 2000 });
    } catch (err) {
      addNotification({ title: 'Kaydetme Hatası', body: err.message, type: 'error' });
    } finally {
      setSaving(false);
    }
  };

  const handleGeneratePoc = async () => {
    setPocLoading(true);
    try {
      const result = await aiGeneratePoc(finding.id);
      setPocContent(result);
      if (!expanded) setExpanded(true);
    } catch (err) {
      addNotification({ title: 'PoC Oluşturma Hatası', body: err.message, type: 'error' });
    } finally {
      setPocLoading(false);
    }
  };

  const pocSteps = (() => {
    const raw = pocContent ?? finding.ai_poc;
    if (!raw) return null;
    try { return JSON.parse(raw); } catch { return [raw]; }
  })();

  return (
    <div className={`border rounded-xl overflow-hidden animate-slide-in ${sev.border} ${sev.bg}`}>
      {/* Başlık satırı */}
      <div
        className="flex items-center gap-3 px-4 py-3 cursor-pointer"
        onClick={() => setExpanded((v) => !v)}
      >
        {/* Severity badge */}
        <span className={`text-[10px] font-bold px-2 py-0.5 rounded flex-shrink-0 ${sev.badge}`}>
          {(finding.severity ?? 'info').toUpperCase()}
        </span>

        {/* Başlık + URL */}
        <div className="flex-1 min-w-0">
          <p className="text-sm font-medium text-white truncate">
            {finding.title ?? VULN_LABEL[finding.vuln_type] ?? finding.vuln_type}
          </p>
          <p className="text-[10px] font-mono text-gray-500 truncate mt-0.5">
            {finding.url?.url ?? `URL #${finding.url_id}`}
          </p>
        </div>

        {/* AI güven skoru */}
        {finding.ai_confidence != null && (
          <div className="flex flex-col items-center gap-0.5 flex-shrink-0">
            <span className={`text-xs font-bold tabular-nums ${sev.text}`}>
              {finding.ai_confidence}%
            </span>
            <div className="w-14 h-1.5 bg-[#374151] rounded-full overflow-hidden">
              <div
                className={`h-full transition-all duration-500 ${sev.bar}`}
                style={{ width: `${finding.ai_confidence}%` }}
              />
            </div>
            <span className="text-[9px] text-gray-600">AI güven</span>
          </div>
        )}

        {/* Durum */}
        <span className={`text-[10px] px-1.5 py-0.5 rounded border flex-shrink-0 ${
          STATUS_CONFIG[status]?.cls ?? STATUS_CONFIG.new.cls
        }`}>
          {STATUS_CONFIG[status]?.label ?? status}
        </span>

        {/* Araç */}
        {finding.tool_used && (
          <span className="text-[10px] text-gray-600 flex-shrink-0 font-mono">
            {finding.tool_used}
          </span>
        )}

        {/* Toggle */}
        <svg
          viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}
          className={`w-4 h-4 text-gray-500 flex-shrink-0 transition-transform ${expanded ? 'rotate-180' : ''}`}
        >
          <polyline points="6 9 12 15 18 9" />
        </svg>
      </div>

      {/* Genişletilmiş detay */}
      {expanded && (
        <div className="px-4 pb-4 space-y-3 border-t border-white/10 pt-3">

          {/* Hızlı aksiyon butonları */}
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-[10px] text-gray-500">Aksiyon:</span>
            <button
              onClick={() => saveStatus('confirmed')}
              disabled={saving || status === 'confirmed'}
              className={`text-[10px] px-2.5 py-1 rounded border transition-colors ${
                status === 'confirmed'
                  ? 'bg-green-500/20 text-green-400 border-green-500/30'
                  : 'border-[#374151] text-gray-500 hover:border-green-500/40 hover:text-green-400'
              }`}
            >
              ✓ Onayla
            </button>
            <button
              onClick={() => saveStatus('false_positive')}
              disabled={saving || status === 'false_positive'}
              className={`text-[10px] px-2.5 py-1 rounded border transition-colors ${
                status === 'false_positive'
                  ? 'bg-gray-500/20 text-gray-400 border-gray-500/20'
                  : 'border-[#374151] text-gray-500 hover:border-gray-500 hover:text-gray-300'
              }`}
            >
              ✗ False Positive
            </button>
            <button
              onClick={handleGeneratePoc}
              disabled={pocLoading}
              className="text-[10px] px-2.5 py-1 rounded border border-blue-500/30 text-blue-400
                hover:bg-blue-500/10 disabled:opacity-50 transition-colors flex items-center gap-1"
            >
              {pocLoading ? (
                <>
                  <span className="w-2.5 h-2.5 border border-blue-400 border-t-transparent rounded-full animate-spin" />
                  Oluşturuluyor…
                </>
              ) : (
                '🤖 PoC Oluştur'
              )}
            </button>
            {onContextSet && (
              <button
                onClick={onContextSet}
                className="text-[10px] px-2.5 py-1 rounded border border-purple-500/30 text-purple-400
                  hover:bg-purple-500/10 transition-colors"
              >
                💬 AI'a Sor
              </button>
            )}
          </div>

          {/* Payload */}
          {finding.payload && (
            <div>
              <p className="text-[10px] text-gray-500 mb-1">Payload</p>
              <code className="text-xs font-mono text-green-300 bg-black/30 px-3 py-2 rounded block break-all leading-relaxed">
                {finding.payload}
              </code>
            </div>
          )}

          {/* Evidence */}
          {finding.evidence && (
            <div>
              <p className="text-[10px] text-gray-500 mb-1">Kanıt</p>
              <p className="text-xs text-gray-300 bg-[#1f2937] px-3 py-2 rounded leading-relaxed">
                {finding.evidence}
              </p>
            </div>
          )}

          {/* AI analiz */}
          {finding.ai_analysis && (
            <div>
              <p className="text-[10px] text-gray-500 mb-1">AI Değerlendirmesi</p>
              <p className="text-xs text-gray-300 bg-blue-500/5 border border-blue-500/20 px-3 py-2 rounded leading-relaxed">
                {finding.ai_analysis}
              </p>
            </div>
          )}

          {/* PoC adımları */}
          {pocSteps && (
            <div>
              <p className="text-[10px] text-gray-500 mb-1">PoC Adımları</p>
              <ol className="space-y-1">
                {pocSteps.map((step, i) => (
                  <li key={i} className="flex gap-2 bg-[#1f2937] px-3 py-1.5 rounded text-xs text-gray-300">
                    <span className="text-blue-400 font-bold flex-shrink-0 tabular-nums">{i + 1}.</span>
                    <span className="leading-relaxed">{step}</span>
                  </li>
                ))}
              </ol>
            </div>
          )}

          {/* Not */}
          <div>
            <textarea
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              placeholder="Not ekle…"
              rows={2}
              className="w-full bg-[#1f2937] border border-[#374151] rounded text-xs text-gray-300
                px-2 py-1.5 focus:outline-none focus:border-blue-500 resize-none placeholder-gray-700"
            />
            <button
              onClick={saveNotes}
              disabled={saving}
              className="mt-1 text-[10px] text-blue-400 hover:underline disabled:opacity-50"
            >
              Kaydet
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
