/**
 * Reports — Raporlar sayfası.
 *
 * Özellikler:
 *  - Tamamlanan taramaların rapor listesi
 *  - Her rapor: hedef, tarih, bulgu özeti (severity dağılımı)
 *  - Rapor detay modal'ı (executive summary, AI analiz, istatistikler)
 */

import { useEffect, useState, useCallback } from 'react';
import { getReports, getScan } from '../../api/client';
import useUiStore from '../../store/uiStore';
import { format, formatDistanceToNow } from 'date-fns';
import { tr } from 'date-fns/locale';

// ---------------------------------------------------------------------------
// Severity bar bileşeni
// ---------------------------------------------------------------------------

const SEV_CONFIG = [
  { key: 'critical_count', label: 'Kritik',  color: 'bg-red-600',    text: 'text-red-400' },
  { key: 'high_count',     label: 'Yüksek',  color: 'bg-orange-500', text: 'text-orange-400' },
  { key: 'medium_count',   label: 'Orta',    color: 'bg-yellow-500', text: 'text-yellow-400' },
  { key: 'low_count',      label: 'Düşük',   color: 'bg-green-500',  text: 'text-green-400' },
  { key: 'info_count',     label: 'Bilgi',   color: 'bg-blue-500',   text: 'text-blue-400' },
];

function SeverityBar({ report }) {
  const total = report.total_findings ?? 0;
  if (total === 0) {
    return <span className="text-xs text-gray-600">Bulgu bulunamadı</span>;
  }
  return (
    <div className="flex items-center gap-2">
      <div className="flex h-2 rounded-full overflow-hidden w-32 bg-[#374151]">
        {SEV_CONFIG.map((s) => {
          const count = report[s.key] ?? 0;
          if (!count) return null;
          const pct = (count / total) * 100;
          return (
            <div
              key={s.key}
              className={`h-full ${s.color}`}
              style={{ width: `${pct}%` }}
              title={`${s.label}: ${count}`}
            />
          );
        })}
      </div>
      <span className="text-xs text-gray-400">{total} toplam</span>
    </div>
  );
}

function SeverityCounts({ report }) {
  return (
    <div className="flex flex-wrap gap-2">
      {SEV_CONFIG.map((s) => {
        const count = report[s.key] ?? 0;
        if (!count) return null;
        return (
          <span key={s.key} className={`text-xs font-medium ${s.text}`}>
            {count} {s.label}
          </span>
        );
      })}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Detay modal
// ---------------------------------------------------------------------------

function ReportModal({ report, scan, onClose }) {
  const dateStr = (() => {
    try { return format(new Date(report.created_at), 'dd MMMM yyyy HH:mm', { locale: tr }); }
    catch { return '—'; }
  })();

  const durationStr = report.scan_duration
    ? `${Math.floor(report.scan_duration / 60)}dk ${report.scan_duration % 60}sn`
    : '—';

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 animate-fade-in p-4">
      <div className="bg-[#111827] border border-[#374151] rounded-xl shadow-2xl w-full max-w-2xl max-h-[90vh] flex flex-col">

        {/* Başlık */}
        <div className="flex items-start justify-between px-6 py-4 border-b border-[#374151]">
          <div>
            <h2 className="text-base font-bold text-white">Tarama Raporu</h2>
            <p className="text-sm font-mono text-blue-300 mt-0.5">{scan?.target ?? report.scan_id}</p>
          </div>
          <button onClick={onClose} className="text-gray-500 hover:text-gray-300 mt-0.5">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} className="w-5 h-5">
              <line x1="18" y1="6" x2="6" y2="18" /><line x1="6" y1="6" x2="18" y2="18" />
            </svg>
          </button>
        </div>

        {/* İçerik */}
        <div className="flex-1 overflow-y-auto px-6 py-4 space-y-5">

          {/* Özet istatistikler */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            {[
              { label: 'Subdomainler', val: report.total_subdomains ?? 0 },
              { label: 'Canlı', val: report.live_subdomains ?? 0 },
              { label: 'URL', val: report.total_urls ?? 0 },
              { label: 'Bulgu', val: report.total_findings ?? 0 },
            ].map((item) => (
              <div key={item.label} className="bg-[#1f2937] rounded-lg p-3 text-center">
                <p className="text-lg font-bold text-white">{item.val}</p>
                <p className="text-[10px] text-gray-500">{item.label}</p>
              </div>
            ))}
          </div>

          {/* Severity dağılımı */}
          <div>
            <h3 className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-2">
              Bulgu Dağılımı
            </h3>
            <div className="space-y-2">
              {SEV_CONFIG.map((s) => {
                const count = report[s.key] ?? 0;
                const total = report.total_findings ?? 0;
                const pct = total > 0 ? Math.round((count / total) * 100) : 0;
                return (
                  <div key={s.key} className="flex items-center gap-3">
                    <span className={`text-xs w-12 text-right ${s.text}`}>{s.label}</span>
                    <div className="flex-1 h-2 bg-[#374151] rounded-full overflow-hidden">
                      <div className={`h-full ${s.color} transition-all duration-500`} style={{ width: `${pct}%` }} />
                    </div>
                    <span className="text-xs text-gray-500 w-16 text-right">{count} ({pct}%)</span>
                  </div>
                );
              })}
            </div>
          </div>

          {/* Executive summary */}
          {report.executive_summary && (
            <div>
              <h3 className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-2">
                Özet
              </h3>
              <p className="text-sm text-gray-300 leading-relaxed bg-[#1f2937] rounded-lg p-3">
                {report.executive_summary}
              </p>
            </div>
          )}

          {/* AI analiz */}
          {report.ai_summary && (
            <div>
              <h3 className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-2">
                AI Analizi
              </h3>
              <p className="text-sm text-gray-300 leading-relaxed bg-blue-500/5 border border-blue-500/20 rounded-lg p-3">
                {report.ai_summary}
              </p>
            </div>
          )}

          {/* Meta */}
          <div className="grid grid-cols-2 gap-3 text-xs">
            <div className="bg-[#1f2937] rounded-lg p-3">
              <p className="text-gray-500 mb-1">Oluşturma Tarihi</p>
              <p className="text-gray-300">{dateStr}</p>
            </div>
            <div className="bg-[#1f2937] rounded-lg p-3">
              <p className="text-gray-500 mb-1">Tarama Süresi</p>
              <p className="text-gray-300">{durationStr}</p>
            </div>
          </div>
        </div>

        {/* Footer */}
        <div className="px-6 py-3 border-t border-[#374151] flex justify-end">
          <button
            onClick={onClose}
            className="px-4 py-2 rounded-lg text-xs text-gray-400 hover:text-gray-200 hover:bg-[#1f2937] transition-colors"
          >
            Kapat
          </button>
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Ana bileşen
// ---------------------------------------------------------------------------

export default function Reports() {
  const [reports, setReports] = useState([]);
  const [scansMap, setScansMap] = useState({});
  const [loading, setLoading] = useState(true);
  const [selectedReport, setSelectedReport] = useState(null);
  const [selectedScan, setSelectedScan] = useState(null);

  const addNotification = useUiStore((s) => s.addNotification);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const data = await getReports();
      const list = data.reports ?? data ?? [];
      setReports(list);

      // Her rapor için scan bilgisini çek (target göstermek için)
      const scanFetches = list.map(async (r) => {
        try {
          const scan = await getScan(r.scan_id);
          return [r.scan_id, scan];
        } catch {
          return [r.scan_id, null];
        }
      });
      const pairs = await Promise.all(scanFetches);
      const map = {};
      for (const [id, scan] of pairs) {
        if (scan) map[id] = scan;
      }
      setScansMap(map);
    } catch (err) {
      addNotification({ title: 'Yükleme Hatası', body: err.message, type: 'error' });
    } finally {
      setLoading(false);
    }
  }, [addNotification]);

  useEffect(() => {
    load();
  }, [load]);

  const openDetail = (report) => {
    setSelectedReport(report);
    setSelectedScan(scansMap[report.scan_id] ?? null);
  };

  return (
    <div className="p-6 space-y-4">
      {/* Başlık */}
      <div>
        <h1 className="text-lg font-bold text-white">Raporlar</h1>
        <p className="text-xs text-gray-500 mt-0.5">{reports.length} rapor</p>
      </div>

      {/* Liste */}
      {loading ? (
        <div className="space-y-3">
          {[1, 2, 3].map((i) => (
            <div key={i} className="h-24 bg-[#111827] border border-[#374151] rounded-xl animate-pulse" />
          ))}
        </div>
      ) : reports.length === 0 ? (
        <div className="bg-[#111827] border border-[#374151] rounded-xl p-12 text-center">
          <p className="text-sm text-gray-500">Henüz tamamlanmış tarama raporu yok.</p>
          <p className="text-xs text-gray-600 mt-1">
            Taramalar tamamlandığında raporlar burada görünür.
          </p>
        </div>
      ) : (
        <div className="space-y-3">
          {reports.map((report) => {
            const scan = scansMap[report.scan_id];
            const dateStr = (() => {
              try {
                return formatDistanceToNow(new Date(report.created_at), { addSuffix: true, locale: tr });
              } catch { return '—'; }
            })();

            return (
              <div
                key={report.id}
                className="bg-[#111827] border border-[#374151] rounded-xl p-4 hover:border-blue-500/40 transition-colors"
              >
                <div className="flex items-start justify-between gap-4">
                  <div className="flex-1 min-w-0">
                    {/* Hedef */}
                    <div className="flex items-center gap-2">
                      <span className="font-mono text-sm text-blue-300 truncate">
                        {scan?.target ?? report.scan_id}
                      </span>
                      <span className="text-[10px] text-green-400 bg-green-500/10 px-1.5 py-0.5 rounded flex-shrink-0">
                        Tamamlandı
                      </span>
                    </div>
                    <p className="text-[10px] text-gray-500 mt-0.5">{dateStr}</p>

                    {/* İstatistikler */}
                    <div className="flex items-center gap-3 mt-2 flex-wrap">
                      <span className="text-[10px] text-gray-500">
                        {report.total_subdomains ?? 0} subdomain
                      </span>
                      <span className="text-[10px] text-gray-600">·</span>
                      <span className="text-[10px] text-gray-500">
                        {report.total_urls ?? 0} URL
                      </span>
                      <span className="text-[10px] text-gray-600">·</span>
                      <SeverityCounts report={report} />
                    </div>

                    {/* Bar */}
                    <div className="mt-2">
                      <SeverityBar report={report} />
                    </div>
                  </div>

                  {/* Aksiyon */}
                  <div className="flex flex-col items-end gap-2 flex-shrink-0">
                    <button
                      onClick={() => openDetail(report)}
                      className="px-3 py-1.5 rounded-lg text-xs bg-blue-600/20 text-blue-400 hover:bg-blue-600/30 transition-colors font-medium"
                    >
                      Detay
                    </button>
                    {scan && (
                      <a
                        href={`/scan/${scan.id}`}
                        className="text-[10px] text-gray-500 hover:text-gray-300 hover:underline"
                      >
                        Taramaya git →
                      </a>
                    )}
                  </div>
                </div>

                {/* Executive summary önizleme */}
                {report.executive_summary && (
                  <p className="mt-2 text-xs text-gray-500 line-clamp-2 leading-relaxed">
                    {report.executive_summary}
                  </p>
                )}
              </div>
            );
          })}
        </div>
      )}

      {/* Detay modal */}
      {selectedReport && (
        <ReportModal
          report={selectedReport}
          scan={selectedScan}
          onClose={() => { setSelectedReport(null); setSelectedScan(null); }}
        />
      )}
    </div>
  );
}
