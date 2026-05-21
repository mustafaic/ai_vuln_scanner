/**
 * ScanHistory — Geçmiş taramalar sayfası.
 *
 * Özellikler:
 *  - Tüm taramaların tablosu (tablo görünümü)
 *  - Sıralama: created_at, status, target, finding_count
 *  - Filtreler: status filtresi
 *  - Aksiyonlar: Görüntüle, Sil
 *  - Sayfalama
 */

import { useEffect, useState, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { listScans, deleteScan } from '../../api/client';
import useUiStore from '../../store/uiStore';
import { format } from 'date-fns';
import { tr } from 'date-fns/locale';

const STATUS_CONFIG = {
  running:   { label: 'Çalışıyor',    bg: 'bg-blue-500/20',   text: 'text-blue-400',   dot: 'bg-blue-400 animate-pulse-dot' },
  paused:    { label: 'Duraklatıldı', bg: 'bg-purple-500/20', text: 'text-purple-400', dot: 'bg-purple-400' },
  completed: { label: 'Tamamlandı',   bg: 'bg-green-500/20',  text: 'text-green-400',  dot: 'bg-green-400' },
  failed:    { label: 'Başarısız',    bg: 'bg-red-500/20',    text: 'text-red-400',    dot: 'bg-red-400' },
  stopped:   { label: 'Durduruldu',   bg: 'bg-gray-500/20',   text: 'text-gray-400',   dot: 'bg-gray-500' },
  pending:       { label: 'Bekliyor',        bg: 'bg-yellow-500/20',  text: 'text-yellow-400',  dot: 'bg-yellow-400' },
  waiting_user:  { label: 'Kullanıcı Seçimi', bg: 'bg-orange-500/20',  text: 'text-orange-400',  dot: 'bg-orange-400 animate-pulse-dot' },
};

const MODE_LABEL = { stealth: 'Gizli', normal: 'Normal', aggressive: 'Agresif' };
const SCOPE_LABEL = { single: 'Tek domain', subdomains: 'Subdomainler' };

const PAGE_LIMIT = 20;

const ALL_STATUSES = ['', 'running', 'paused', 'completed', 'stopped', 'failed', 'pending'];

function StatusBadge({ status }) {
  const cfg = STATUS_CONFIG[status] ?? STATUS_CONFIG.pending;
  return (
    <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-medium ${cfg.bg} ${cfg.text}`}>
      <span className={`w-1.5 h-1.5 rounded-full ${cfg.dot}`} />
      {cfg.label}
    </span>
  );
}

function SeverityDots({ scan }) {
  const c = scan.finding_stats?.critical ?? 0;
  const h = scan.finding_stats?.high ?? 0;
  const m = scan.finding_stats?.medium ?? 0;
  const l = scan.finding_stats?.low ?? 0;
  const total = c + h + m + l;
  if (total === 0) return <span className="text-xs text-gray-600">—</span>;
  return (
    <div className="flex items-center gap-1">
      {c > 0 && <span className="text-[10px] text-red-400 font-medium">{c}K</span>}
      {h > 0 && <span className="text-[10px] text-orange-400 font-medium">{h}Y</span>}
      {m > 0 && <span className="text-[10px] text-yellow-400">{m}O</span>}
      {l > 0 && <span className="text-[10px] text-green-400">{l}D</span>}
    </div>
  );
}

export default function ScanHistory() {
  const [scans, setScans] = useState([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [page, setPage] = useState(1);
  const [statusFilter, setStatusFilter] = useState('');
  const [sortBy, setSortBy] = useState('created_at');
  const [sortDir, setSortDir] = useState('desc');
  const [deleting, setDeleting] = useState(null); // id

  const navigate = useNavigate();
  const addNotification = useUiStore((s) => s.addNotification);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const params = {
        page,
        limit: PAGE_LIMIT,
        ...(statusFilter ? { status: statusFilter } : {}),
      };
      const data = await listScans(params);
      const list = data.items ?? data.scans ?? [];
      setScans(list);
      setTotal(data.total ?? list.length);
    } catch (err) {
      addNotification({ title: 'Yükleme Hatası', body: err.message, type: 'error' });
    } finally {
      setLoading(false);
    }
  }, [page, statusFilter, addNotification]);

  useEffect(() => {
    load();
  }, [load]);

  const handleDelete = useCallback(async (scan) => {
    if (!window.confirm(`"${scan.target}" taramasını silmek istiyor musunuz? Bu işlem geri alınamaz.`)) return;
    setDeleting(scan.id);
    try {
      await deleteScan(scan.id);
      addNotification({ title: 'Tarama Silindi', type: 'success' });
      load();
    } catch (err) {
      addNotification({ title: 'Silme Hatası', body: err.message, type: 'error' });
    } finally {
      setDeleting(null);
    }
  }, [load, addNotification]);

  // Sıralama
  const handleSort = (col) => {
    if (sortBy === col) {
      setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'));
    } else {
      setSortBy(col);
      setSortDir('desc');
    }
  };

  // İstemci tarafı sıralama (server-side desteklenmiyorsa)
  const sortedScans = [...scans].sort((a, b) => {
    let av = a[sortBy] ?? '';
    let bv = b[sortBy] ?? '';
    if (typeof av === 'string') av = av.toLowerCase();
    if (typeof bv === 'string') bv = bv.toLowerCase();
    if (av < bv) return sortDir === 'asc' ? -1 : 1;
    if (av > bv) return sortDir === 'asc' ? 1 : -1;
    return 0;
  });

  const totalPages = Math.max(1, Math.ceil(total / PAGE_LIMIT));

  const SortIcon = ({ col }) => {
    if (sortBy !== col) return <span className="text-gray-600">↕</span>;
    return <span className="text-blue-400">{sortDir === 'asc' ? '↑' : '↓'}</span>;
  };

  return (
    <div className="p-6 space-y-4">
      {/* Başlık */}
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-lg font-bold text-white">Tarama Geçmişi</h1>
          <p className="text-xs text-gray-500 mt-0.5">{total} tarama</p>
        </div>
        <div className="flex items-center gap-2">
          {/* Status filtresi */}
          <select
            value={statusFilter}
            onChange={(e) => { setStatusFilter(e.target.value); setPage(1); }}
            className="bg-[#1f2937] border border-[#374151] rounded text-xs text-gray-300 px-2 py-1.5 focus:outline-none focus:border-blue-500"
          >
            <option value="">Tüm Durumlar</option>
            {ALL_STATUSES.filter(Boolean).map((s) => (
              <option key={s} value={s}>{STATUS_CONFIG[s]?.label ?? s}</option>
            ))}
          </select>
          <button
            onClick={() => navigate('/scan/new')}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-blue-600 hover:bg-blue-500 text-white text-xs font-medium transition-colors"
          >
            + Yeni Tarama
          </button>
        </div>
      </div>

      {/* Tablo */}
      <div className="bg-[#111827] border border-[#374151] rounded-xl overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead>
              <tr className="border-b border-[#374151] text-gray-500">
                <th
                  className="text-left px-4 py-3 font-medium cursor-pointer hover:text-gray-300 select-none"
                  onClick={() => handleSort('target')}
                >
                  Hedef <SortIcon col="target" />
                </th>
                <th className="text-left px-4 py-3 font-medium">Mod / Kapsam</th>
                <th
                  className="text-left px-4 py-3 font-medium cursor-pointer hover:text-gray-300 select-none"
                  onClick={() => handleSort('status')}
                >
                  Durum <SortIcon col="status" />
                </th>
                <th className="text-right px-4 py-3 font-medium">Subdomain</th>
                <th className="text-right px-4 py-3 font-medium">URL</th>
                <th className="text-left px-4 py-3 font-medium">Bulgular</th>
                <th
                  className="text-left px-4 py-3 font-medium cursor-pointer hover:text-gray-300 select-none"
                  onClick={() => handleSort('created_at')}
                >
                  Tarih <SortIcon col="created_at" />
                </th>
                <th className="text-right px-4 py-3 font-medium">İşlem</th>
              </tr>
            </thead>
            <tbody>
              {loading ? (
                Array.from({ length: 5 }).map((_, i) => (
                  <tr key={i} className="border-b border-[#374151]/50">
                    {Array.from({ length: 8 }).map((_, j) => (
                      <td key={j} className="px-4 py-3">
                        <div className="h-3 bg-[#1f2937] rounded animate-pulse w-full" />
                      </td>
                    ))}
                  </tr>
                ))
              ) : sortedScans.length === 0 ? (
                <tr>
                  <td colSpan={8} className="px-4 py-12 text-center text-gray-500">
                    {statusFilter ? 'Bu filtreye uygun tarama bulunamadı.' : 'Henüz tarama yok.'}
                  </td>
                </tr>
              ) : (
                sortedScans.map((scan) => {
                  const dateStr = (() => {
                    try { return format(new Date(scan.created_at), 'dd MMM yyyy HH:mm', { locale: tr }); }
                    catch { return '—'; }
                  })();

                  return (
                    <tr
                      key={scan.id}
                      className="border-b border-[#374151]/50 hover:bg-[#1f2937]/50 transition-colors"
                    >
                      {/* Hedef */}
                      <td className="px-4 py-3">
                        <span
                          className="font-mono text-blue-300 hover:underline cursor-pointer"
                          onClick={() => navigate(`/scan/${scan.id}`)}
                        >
                          {scan.target}
                        </span>
                        {scan.name && (
                          <p className="text-[10px] text-gray-600 mt-0.5">{scan.name}</p>
                        )}
                      </td>

                      {/* Mod */}
                      <td className="px-4 py-3 text-gray-400">
                        <span>{MODE_LABEL[scan.mode] ?? scan.mode}</span>
                        <span className="text-gray-600 mx-1">·</span>
                        <span className="text-gray-500">{SCOPE_LABEL[scan.scope] ?? scan.scope}</span>
                      </td>

                      {/* Durum */}
                      <td className="px-4 py-3">
                        <StatusBadge status={scan.status} />
                        {(scan.status === 'running' || scan.status === 'paused') && (
                          <p className="text-[10px] text-gray-600 mt-1">{scan.progress ?? 0}%</p>
                        )}
                      </td>

                      {/* Subdomain */}
                      <td className="px-4 py-3 text-right text-gray-400">
                        {scan.subdomain_count ?? '—'}
                      </td>

                      {/* URL */}
                      <td className="px-4 py-3 text-right text-gray-400">
                        {scan.url_count ?? '—'}
                      </td>

                      {/* Bulgular */}
                      <td className="px-4 py-3">
                        <SeverityDots scan={scan} />
                      </td>

                      {/* Tarih */}
                      <td className="px-4 py-3 text-gray-500 whitespace-nowrap">
                        {dateStr}
                      </td>

                      {/* İşlemler */}
                      <td className="px-4 py-3 text-right">
                        <div className="flex items-center justify-end gap-1">
                          <button
                            onClick={() => navigate(`/scan/${scan.id}`)}
                            className="px-2 py-1 rounded text-[10px] text-blue-400 hover:bg-blue-500/10 transition-colors"
                          >
                            Görüntüle
                          </button>
                          <button
                            onClick={() => handleDelete(scan)}
                            disabled={deleting === scan.id || scan.status === 'running'}
                            className="px-2 py-1 rounded text-[10px] text-red-400 hover:bg-red-500/10 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
                          >
                            {deleting === scan.id ? '…' : 'Sil'}
                          </button>
                        </div>
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>

        {/* Sayfalama */}
        {totalPages > 1 && (
          <div className="flex items-center justify-between px-4 py-3 border-t border-[#374151]">
            <span className="text-[10px] text-gray-500">
              Sayfa {page} / {totalPages}
            </span>
            <div className="flex items-center gap-1">
              <button
                onClick={() => setPage((p) => Math.max(1, p - 1))}
                disabled={page === 1}
                className="px-2 py-1 rounded text-xs text-gray-400 hover:text-gray-200 hover:bg-[#1f2937] disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
              >
                ← Önceki
              </button>
              <button
                onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                disabled={page === totalPages}
                className="px-2 py-1 rounded text-xs text-gray-400 hover:text-gray-200 hover:bg-[#1f2937] disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
              >
                Sonraki →
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
