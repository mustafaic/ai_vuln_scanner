/**
 * TestPanel — Test fazı başlatma paneli (Spec Bölüm 12.6).
 *
 * Akış:
 *  1. Seçilen URL özeti gösterilir
 *  2. Test tipleri seçilir
 *  3. "AI Ön Analiz" tetiklenir (opsiyonel) → her URL için analiz kartları
 *  4. WAF bypass suggestion kartı (wafBypassNeeded varsa)
 *  5. "Testi Başlat" butonu
 *  6. Canlı test log feed'i
 */

import { useState, useRef, useEffect } from 'react';
import { startTest, aiGeneratePayloads, applyWafBypass } from '../../../api/client';
import useUiStore from '../../../store/uiStore';
import useScanStore from '../../../store/scanStore';

const TEST_TYPES = [
  { id: 'xss',      label: 'XSS',           icon: '⚡', desc: 'Dalfox ile Cross-Site Scripting testi' },
  { id: 'sqli',     label: 'SQLi',          icon: '💉', desc: 'SQLMap ile SQL enjeksiyonu testi' },
  { id: 'lfi',      label: 'LFI',           icon: '📁', desc: 'Nuclei LFI template\'leri' },
  { id: 'redirect', label: 'Open Redirect', icon: '↪',  desc: 'Açık yönlendirme kontrolü' },
  { id: 'ssrf',     label: 'SSRF',          icon: '🌐', desc: 'Nuclei SSRF template\'leri' },
  { id: 'nuclei',   label: 'Nuclei',        icon: '🔬', desc: 'Genel CVE, misconfig, exposure taraması' },
];

const PROB_COLOR = {
  high:   'text-green-400',
  medium: 'text-yellow-400',
  low:    'text-red-400',
};

const LOG_COLORS = {
  start: 'text-blue-400', done: 'text-green-400', output: 'text-gray-400',
  error: 'text-red-400',  warn: 'text-yellow-400', phase: 'text-purple-400',
  info:  'text-gray-500',
};

export default function TestPanel({ scanId, selectedUrlIds = [], onStarted }) {
  const [testTypes, setTestTypes]   = useState(new Set(['xss', 'sqli']));
  const [preAnalysis, setPreAnalysis] = useState(null);
  const [analyzing, setAnalyzing]   = useState(false);
  const [starting, setStarting]     = useState(false);
  const [logAutoScroll, setLogAutoScroll] = useState(true);

  const urls            = useScanStore((s) => s.urls);
  const toolLog         = useScanStore((s) => s.toolLog);
  const wafBypassNeeded = useScanStore((s) => s.wafBypassNeeded);
  const clearWafBypass  = useScanStore((s) => s.clearWafBypass);
  const addNotification = useUiStore((s) => s.addNotification);

  const logBottomRef = useRef(null);

  // Test fazına ait log satırları (phase=testing veya son log'lar)
  const testLog = toolLog.filter((e) => e.phase === 'testing' || !e.phase).slice(-100);

  useEffect(() => {
    if (logAutoScroll) {
      logBottomRef.current?.scrollIntoView({ behavior: 'smooth' });
    }
  }, [testLog, logAutoScroll]);

  const selectedUrls = urls.filter((u) => selectedUrlIds.includes(u.id));

  const toggleType = (id) => {
    setTestTypes((prev) => {
      const n = new Set(prev);
      n.has(id) ? n.delete(id) : n.add(id);
      return n;
    });
  };

  const runPreAnalysis = async () => {
    if (!selectedUrlIds.length || !testTypes.size) return;
    setAnalyzing(true);
    try {
      const results = await Promise.all(
        [...testTypes].map((type) =>
          aiGeneratePayloads({ url_id: selectedUrlIds[0], vuln_type: type })
            .then((r) => ({ type, result: r }))
            .catch(() => ({ type, result: null }))
        )
      );
      setPreAnalysis(results);
    } catch (err) {
      addNotification({ title: 'Analiz Hatası', body: err.message, type: 'error' });
    } finally {
      setAnalyzing(false);
    }
  };

  const handleStart = async () => {
    if (!selectedUrlIds.length || !testTypes.size) return;
    setStarting(true);
    try {
      await startTest(scanId, {
        url_ids: selectedUrlIds,
        test_types: [...testTypes],
      });
      addNotification({
        title: 'Test Başlatıldı',
        body: `${selectedUrlIds.length} URL · ${testTypes.size} test tipi`,
        type: 'success',
      });
      onStarted?.();
    } catch (err) {
      addNotification({ title: 'Test Başlatma Hatası', body: err.message, type: 'error' });
    } finally {
      setStarting(false);
    }
  };

  const handleBypass = async (technique) => {
    if (!wafBypassNeeded) return;
    try {
      await applyWafBypass(scanId, {
        url_id: wafBypassNeeded.url_id,
        finding_id: wafBypassNeeded.finding_id,
        technique,
      });
      clearWafBypass();
      addNotification({ title: 'WAF Bypass uygulandı', type: 'success' });
    } catch (err) {
      addNotification({ title: 'Bypass Hatası', body: err.message, type: 'error' });
    }
  };

  return (
    <div className="flex flex-col gap-4 p-4 overflow-auto">

      {/* Seçili URL özeti */}
      <div className="bg-[#1f2937] border border-[#374151] rounded-xl p-3">
        <p className="text-xs text-gray-400 mb-1.5">
          <strong className="text-white">{selectedUrlIds.length}</strong> URL seçili
        </p>
        <div className="space-y-0.5 max-h-20 overflow-y-auto">
          {selectedUrls.slice(0, 8).map((u) => (
            <p key={u.id} className="text-[10px] font-mono text-blue-300 truncate">{u.url}</p>
          ))}
          {selectedUrlIds.length > 8 && (
            <p className="text-[10px] text-gray-600">+{selectedUrlIds.length - 8} daha…</p>
          )}
        </div>
      </div>

      {/* Test tipi seçimi */}
      <div>
        <p className="text-xs font-semibold text-gray-400 mb-2">Test Tipleri</p>
        <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
          {TEST_TYPES.map((tt) => {
            const active = testTypes.has(tt.id);
            return (
              <button
                key={tt.id}
                onClick={() => toggleType(tt.id)}
                className={`
                  flex items-start gap-2 p-2.5 rounded-lg border text-left transition-colors
                  ${active
                    ? 'border-blue-500 bg-blue-500/10'
                    : 'border-[#374151] bg-[#1f2937] hover:border-gray-500'}
                `}
              >
                <span className="text-base mt-0.5 flex-shrink-0">{tt.icon}</span>
                <div className="min-w-0">
                  <p className={`text-xs font-medium ${active ? 'text-white' : 'text-gray-400'}`}>
                    {tt.label}
                  </p>
                  <p className="text-[9px] text-gray-600 mt-0.5 leading-tight">{tt.desc}</p>
                </div>
              </button>
            );
          })}
        </div>
      </div>

      {/* AI Ön Analiz */}
      <div>
        <button
          onClick={runPreAnalysis}
          disabled={analyzing || !selectedUrlIds.length || !testTypes.size}
          className="w-full py-2 rounded-lg text-xs border border-blue-500/40 text-blue-400
            hover:bg-blue-500/10 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
        >
          {analyzing ? (
            <span className="flex items-center justify-center gap-2">
              <span className="w-3 h-3 border border-blue-400 border-t-transparent rounded-full animate-spin" />
              AI Analiz Yapılıyor…
            </span>
          ) : (
            '🤖 AI Ön Analiz Yap (Opsiyonel)'
          )}
        </button>

        {preAnalysis && (
          <div className="mt-2 space-y-1.5">
            {preAnalysis.map(({ type, result }) => (
              <div key={type} className="bg-[#1f2937] border border-[#374151] rounded-lg p-2.5">
                <div className="flex items-center gap-2 mb-1">
                  <span className="text-[10px] font-bold text-gray-400 uppercase font-mono">{type}</span>
                  {result?.success_probability && (
                    <span className={`text-[10px] font-medium ${PROB_COLOR[result.success_probability] ?? 'text-gray-400'}`}>
                      {result.success_probability === 'high' ? 'Yüksek olasılık'
                        : result.success_probability === 'medium' ? 'Orta olasılık'
                        : 'Düşük olasılık'}
                    </span>
                  )}
                </div>
                {result ? (
                  <p className="text-[10px] text-gray-300 leading-relaxed">
                    {typeof result === 'string' ? result
                      : result.special_notes ?? JSON.stringify(result).slice(0, 150)}
                  </p>
                ) : (
                  <p className="text-[10px] text-gray-600">Analiz başarısız</p>
                )}
              </div>
            ))}
          </div>
        )}
      </div>

      {/* WAF Bypass Suggestion Card */}
      {wafBypassNeeded && (
        <div className="bg-yellow-500/8 border border-yellow-500/30 rounded-xl p-4">
          <div className="flex items-center gap-2 mb-3">
            <span className="text-yellow-400 text-base">⚠</span>
            <p className="text-sm font-semibold text-yellow-400">
              WAF Tespit Edildi: {wafBypassNeeded.waf}
            </p>
          </div>
          <p className="text-xs text-gray-400 mb-3">
            Payload engellendi. Aşağıdaki bypass tekniklerinden birini seçerek devam et:
          </p>
          <div className="space-y-2">
            {(wafBypassNeeded.suggestions?.bypass_techniques ?? []).map((tech, i) => (
              <div
                key={i}
                className="flex items-start gap-3 bg-[#1f2937] border border-[#374151] rounded-lg p-2.5"
              >
                <div className="flex-1 min-w-0">
                  <p className="text-xs font-medium text-white">{tech.name}</p>
                  <p className="text-[10px] text-gray-500 mt-0.5">{tech.description}</p>
                  {tech.example_payload && (
                    <code className="text-[9px] font-mono text-green-300 mt-1 block truncate">
                      {tech.example_payload}
                    </code>
                  )}
                </div>
                <div className="flex-shrink-0 text-right">
                  <span className={`text-[10px] block mb-1 ${
                    tech.success_probability === 'high' ? 'text-green-400'
                    : tech.success_probability === 'medium' ? 'text-yellow-400'
                    : 'text-red-400'
                  }`}>
                    {tech.success_probability === 'high' ? 'Yüksek'
                      : tech.success_probability === 'medium' ? 'Orta' : 'Düşük'}
                  </span>
                  <button
                    onClick={() => handleBypass(tech.name)}
                    className="text-[10px] px-2 py-0.5 rounded bg-yellow-500/20 text-yellow-400
                      border border-yellow-500/30 hover:bg-yellow-500/30 transition-colors"
                  >
                    Uygula
                  </button>
                </div>
              </div>
            ))}
          </div>
          <button
            onClick={() => handleBypass('__skip__')}
            className="mt-2 text-[10px] text-gray-500 hover:text-gray-300"
          >
            Bypass yapmadan devam et
          </button>
        </div>
      )}

      {/* Başlat butonu */}
      <button
        onClick={handleStart}
        disabled={starting || !selectedUrlIds.length || !testTypes.size}
        className="w-full py-3 rounded-xl text-sm font-semibold bg-blue-600 hover:bg-blue-500
          text-white disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
      >
        {starting ? (
          <span className="flex items-center justify-center gap-2">
            <span className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
            Başlatılıyor…
          </span>
        ) : (
          `⚡ ${selectedUrlIds.length} URL İçin ${testTypes.size} Test Başlat`
        )}
      </button>

      {/* Canlı test log feed'i */}
      {testLog.length > 0 && (
        <div className="bg-[#0a0e1a] border border-[#374151] rounded-xl overflow-hidden">
          <div className="flex items-center justify-between px-3 py-1.5 border-b border-[#374151]">
            <span className="text-[10px] text-gray-500 uppercase tracking-wider">Test Logu</span>
            <label className="flex items-center gap-1.5 text-[10px] text-gray-600 cursor-pointer">
              <input
                type="checkbox"
                checked={logAutoScroll}
                onChange={(e) => setLogAutoScroll(e.target.checked)}
                className="accent-blue-500 w-3 h-3"
              />
              Otomatik kaydır
            </label>
          </div>
          <div className="max-h-48 overflow-y-auto p-3 font-mono text-[10px] space-y-0.5">
            {testLog.map((entry) => (
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
            <div ref={logBottomRef} />
          </div>
        </div>
      )}
    </div>
  );
}
