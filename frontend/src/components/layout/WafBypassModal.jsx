/**
 * WafBypassModal — WAF bypass tekniği seçim modal'ı.
 *
 * Tetiklenme: scanStore._handleWsMessage → 'waf_bypass_needed' event
 *   → uiStore.openModal('waf_bypass')
 *
 * Kullanıcı bir teknik seçip "Uygula" der ya da "Atla" der.
 * Her iki durumda da backend'e API çağrısı yapılır.
 */

import { useState } from 'react';
import useScanStore from '../../store/scanStore';
import useUiStore from '../../store/uiStore';
import { applyWafBypass } from '../../api/client';

const PROB_COLOR = {
  high: 'text-green-400',
  medium: 'text-yellow-400',
  low: 'text-red-400',
};

export default function WafBypassModal() {
  const closeModal = useUiStore((s) => s.closeModal);
  const wafData = useScanStore((s) => s.wafBypassNeeded);
  const clearWafBypass = useScanStore((s) => s.clearWafBypass);
  const activeScanId = useScanStore((s) => s.activeScanId);
  const addNotification = useUiStore((s) => s.addNotification);

  const [selected, setSelected] = useState(null);
  const [loading, setLoading] = useState(false);

  const techniques = wafData?.suggestions?.bypass_techniques ?? [];

  const handleApply = async () => {
    if (!selected && techniques.length > 0) return;
    setLoading(true);
    try {
      await applyWafBypass(activeScanId, {
        url: wafData.url,
        technique: selected ?? '__skip__',
      });
      closeModal();
      clearWafBypass();
    } catch (err) {
      addNotification({ title: 'WAF Bypass Hatası', body: err.message, type: 'error' });
    } finally {
      setLoading(false);
    }
  };

  const handleSkip = async () => {
    setLoading(true);
    try {
      await applyWafBypass(activeScanId, {
        url: wafData?.url,
        technique: '__skip__',
      });
      closeModal();
      clearWafBypass();
    } catch {
      closeModal();
      clearWafBypass();
    } finally {
      setLoading(false);
    }
  };

  if (!wafData) return null;

  return (
    /* Overlay */
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 animate-fade-in">
      <div className="bg-[#111827] border border-[#374151] rounded-xl shadow-2xl w-full max-w-lg mx-4 max-h-[90vh] flex flex-col">

        {/* Başlık */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-[#374151]">
          <div>
            <h2 className="text-sm font-bold text-white">WAF Tespit Edildi</h2>
            <p className="text-xs text-gray-400 mt-0.5">
              <span className="text-yellow-400 font-medium">{wafData.waf_name ?? 'Bilinmeyen WAF'}</span>
              {' · '}
              <span className="font-mono text-gray-500 truncate">{wafData.url}</span>
            </p>
          </div>
          <button onClick={handleSkip} className="text-gray-500 hover:text-gray-300">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} className="w-4 h-4">
              <line x1="18" y1="6" x2="6" y2="18" /><line x1="6" y1="6" x2="18" y2="18" />
            </svg>
          </button>
        </div>

        {/* Test tipi */}
        <div className="px-5 py-3 bg-yellow-500/5 border-b border-yellow-500/20">
          <p className="text-xs text-yellow-400">
            Test Tipi: <strong>{wafData.test_type}</strong>
            {' — '}
            WAF bypass tekniği seçin veya bu URL'i atlayın.
          </p>
        </div>

        {/* Teknikler */}
        <div className="flex-1 overflow-y-auto px-5 py-3 space-y-2">
          {techniques.length === 0 ? (
            <p className="text-sm text-gray-500 text-center py-4">
              AI bypass önerisi bulunamadı.
            </p>
          ) : (
            techniques.map((t, i) => (
              <label
                key={i}
                className={`
                  block p-3 rounded-lg border cursor-pointer transition-colors
                  ${selected === t.name
                    ? 'border-blue-500 bg-blue-500/10'
                    : 'border-[#374151] bg-[#1f2937] hover:border-gray-500'
                  }
                `}
              >
                <div className="flex items-start gap-3">
                  <input
                    type="radio"
                    name="technique"
                    value={t.name}
                    checked={selected === t.name}
                    onChange={() => setSelected(t.name)}
                    className="mt-0.5 accent-blue-500"
                  />
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="text-xs font-semibold text-white">{t.name}</span>
                      <span className={`text-[10px] ${PROB_COLOR[t.success_probability] ?? 'text-gray-400'}`}>
                        {t.success_probability}
                      </span>
                    </div>
                    <p className="text-xs text-gray-400 mt-0.5">{t.description}</p>
                    {t.example_payload && (
                      <code className="text-[10px] font-mono text-blue-300 bg-black/30 px-1 py-0.5 rounded mt-1 block truncate">
                        {t.example_payload}
                      </code>
                    )}
                    {t.tool_flags && (
                      <code className="text-[10px] font-mono text-gray-500 mt-0.5 block">
                        Flags: {t.tool_flags}
                      </code>
                    )}
                  </div>
                </div>
              </label>
            ))
          )}
        </div>

        {/* Aksiyonlar */}
        <div className="flex items-center justify-end gap-2 px-5 py-4 border-t border-[#374151]">
          <button
            onClick={handleSkip}
            disabled={loading}
            className="px-4 py-2 rounded text-xs text-gray-400 hover:text-gray-200 hover:bg-[#1f2937] transition-colors disabled:opacity-50"
          >
            Bu URL'i Atla
          </button>
          <button
            onClick={handleApply}
            disabled={loading || (techniques.length > 0 && !selected)}
            className="px-4 py-2 rounded text-xs bg-blue-600 hover:bg-blue-500 text-white font-medium disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
          >
            {loading ? 'Uygulanıyor…' : 'Tekniği Uygula'}
          </button>
        </div>
      </div>
    </div>
  );
}
