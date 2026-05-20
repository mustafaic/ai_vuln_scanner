/**
 * Dashboard — Ana sayfa.
 *
 * Bölümler:
 *  1. Hızlı "Yeni Tarama" kartı
 *  2. Genel istatistikler (toplam tarama, findings, URL)
 *  3. Son 5 tarama özet kartları
 *  4. Araç durumu widget'ı
 */

import { useEffect, useState, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { listScans } from '../../api/client';
import useToolStore from '../../store/toolStore';
import useScanStore from '../../store/scanStore';
import { formatDistanceToNow } from 'date-fns';
import { tr } from 'date-fns/locale';

// ---------------------------------------------------------------------------
// Yardımcı bileşenler
// ---------------------------------------------------------------------------

const STATUS_CONFIG = {
  running:   { label: 'Çalışıyor',    color: 'text-blue-400',   dot: 'bg-blue-400 animate-pulse-dot' },
  paused:    { label: 'Duraklatıldı', color: 'text-purple-400', dot: 'bg-purple-400' },
  completed: { label: 'Tamamlandı',   color: 'text-green-400',  dot: 'bg-green-400' },
  failed:    { label: 'Başarısız',    color: 'text-red-400',    dot: 'bg-red-400' },
  stopped:   { label: 'Durduruldu',   color: 'text-gray-400',   dot: 'bg-gray-500' },
  pending:   { label: 'Bekliyor',     color: 'text-yellow-400', dot: 'bg-yellow-400' },
};

function StatCard({ label, value, sub, accent }) {
  return (
    <div className="bg-[#111827] border border-[#374151] rounded-xl p-4">
      <p className="text-xs text-gray-500 mb-1">{label}</p>
      <p className={`text-2xl font-bold ${accent ?? 'text-white'}`}>{value}</p>
      {sub && <p className="text-[10px] text-gray-600 mt-1">{sub}</p>}
    </div>
  );
}

function ScanCard({ scan, onClick }) {
  const cfg = STATUS_CONFIG[scan.status] ?? STATUS_CONFIG.pending;
  const ago = (() => {
    try {
      return formatDistanceToNow(new Date(scan.created_at), { addSuffix: true, locale: tr });
    } catch { return '—'; }
  })();

  const critical = scan.finding_stats?.critical ?? 0;
  const high = scan.finding_stats?.high ?? 0;

  return (
    <div
      onClick={onClick}
      className="bg-[#111827] border border-[#374151] rounded-xl p-4 cursor-pointer hover:border-blue-500/50 hover:bg-blue-500/5 transition-colors group"
    >
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="text-sm font-mono font-medium text-white truncate group-hover:text-blue-300 transition-colors">
            {scan.target}
          </p>
          <p className="text-[10px] text-gray-500 mt-0.5">{ago}</p>
        </div>
        <div className="flex items-center gap-1.5 flex-shrink-0">
          <span className={`w-2 h-2 rounded-full ${cfg.dot}`} />
          <span className={`text-[10px] font-medium ${cfg.color}`}>{cfg.label}</span>
        </div>
      </div>

      <div className="flex items-center gap-3 mt-3">
        {scan.status === 'running' || scan.status === 'paused' ? (
          <div className="flex-1 h-1 bg-[#374151] rounded-full overflow-hidden">
            <div
              className="h-full bg-blue-500 transition-all duration-500"
              style={{ width: `${scan.progress ?? 0}%` }}
            />
          </div>
        ) : (
          <div className="flex items-center gap-2 text-[10px] text-gray-500">
            <span>{scan.subdomain_count ?? 0} subdomain</span>
            <span>·</span>
            <span>{scan.url_count ?? 0} URL</span>
          </div>
        )}

        {(critical > 0 || high > 0) && (
          <div className="flex items-center gap-1 flex-shrink-0">
            {critical > 0 && (
              <span className="text-[10px] bg-red-500/20 text-red-400 px-1.5 py-0.5 rounded">
                {critical} kritik
              </span>
            )}
            {high > 0 && (
              <span className="text-[10px] bg-orange-500/20 text-orange-400 px-1.5 py-0.5 rounded">
                {high} yüksek
              </span>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Ana bileşen
// ---------------------------------------------------------------------------

export default function Dashboard() {
  const [scans, setScans] = useState([]);
  const [loading, setLoading] = useState(true);
  const navigate = useNavigate();

  const tools = useToolStore((s) => s.tools);
  const fetchToolStatus = useToolStore((s) => s.fetchToolStatus);
  const installAllMissing = useToolStore((s) => s.installAllMissing);

  const toolList = Object.values(tools);
  const installedCount = toolList.filter((t) => t.installed).length;
  const missingRequired = toolList.filter((t) => t.required && !t.installed);

  // İstatistikler
  const totalScans = scans.length;
  const completedScans = scans.filter((s) => s.status === 'completed').length;
  const totalFindings = scans.reduce((acc, s) => acc + (s.finding_count ?? 0), 0);
  const criticalFindings = scans.reduce(
    (acc, s) => acc + (s.finding_stats?.critical ?? 0),
    0,
  );

  const load = useCallback(async () => {
    try {
      const data = await listScans({ limit: 10 });
      setScans(data.scans ?? data ?? []);
    } catch {
      setScans([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
    fetchToolStatus();
  }, [load, fetchToolStatus]);

  const recentScans = scans.slice(0, 5);

  return (
    <div className="p-6 max-w-5xl mx-auto space-y-6">

      {/* Başlık */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-lg font-bold text-white">Dashboard</h1>
          <p className="text-xs text-gray-500 mt-0.5">VulnScan AI — AI destekli zafiyet tarayıcı</p>
        </div>
        <button
          onClick={() => navigate('/scan/new')}
          className="flex items-center gap-2 px-4 py-2 rounded-lg bg-blue-600 hover:bg-blue-500 text-white text-sm font-medium transition-colors"
        >
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} className="w-4 h-4">
            <line x1="12" y1="5" x2="12" y2="19" /><line x1="5" y1="12" x2="19" y2="12" />
          </svg>
          Yeni Tarama
        </button>
      </div>

      {/* Eksik gerekli araç uyarısı */}
      {missingRequired.length > 0 && (
        <div className="bg-yellow-500/10 border border-yellow-500/30 rounded-xl p-4 flex items-center justify-between gap-4">
          <div>
            <p className="text-sm font-medium text-yellow-400">
              {missingRequired.length} zorunlu araç kurulu değil
            </p>
            <p className="text-xs text-gray-500 mt-0.5">
              {missingRequired.map((t) => t.name).join(', ')}
            </p>
          </div>
          <button
            onClick={installAllMissing}
            className="px-3 py-1.5 rounded bg-yellow-500/20 text-yellow-400 hover:bg-yellow-500/30 text-xs font-medium flex-shrink-0 transition-colors"
          >
            Hepsini Kur
          </button>
        </div>
      )}

      {/* İstatistik kartları */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <StatCard
          label="Toplam Tarama"
          value={totalScans}
          sub={`${completedScans} tamamlandı`}
        />
        <StatCard
          label="Toplam Bulgu"
          value={totalFindings}
          accent={totalFindings > 0 ? 'text-orange-400' : 'text-white'}
        />
        <StatCard
          label="Kritik Bulgu"
          value={criticalFindings}
          accent={criticalFindings > 0 ? 'text-red-400' : 'text-white'}
        />
        <StatCard
          label="Kurulu Araç"
          value={`${installedCount}/${toolList.length}`}
          sub="aktif araçlar"
          accent={installedCount < toolList.length ? 'text-yellow-400' : 'text-green-400'}
        />
      </div>

      {/* Son taramalar */}
      <div>
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-sm font-semibold text-gray-300">Son Taramalar</h2>
          <button
            onClick={() => navigate('/scans')}
            className="text-xs text-blue-400 hover:underline"
          >
            Tümünü gör →
          </button>
        </div>

        {loading ? (
          <div className="space-y-2">
            {[1, 2, 3].map((i) => (
              <div key={i} className="h-20 bg-[#111827] border border-[#374151] rounded-xl animate-pulse" />
            ))}
          </div>
        ) : recentScans.length === 0 ? (
          <div className="bg-[#111827] border border-[#374151] rounded-xl p-8 text-center">
            <p className="text-sm text-gray-500">Henüz tarama yok.</p>
            <button
              onClick={() => navigate('/scan/new')}
              className="mt-3 text-sm text-blue-400 hover:underline"
            >
              İlk taramanı başlat →
            </button>
          </div>
        ) : (
          <div className="space-y-2">
            {recentScans.map((scan) => (
              <ScanCard
                key={scan.id}
                scan={scan}
                onClick={() => navigate(`/scan/${scan.id}`)}
              />
            ))}
          </div>
        )}
      </div>

      {/* Araç durumu widget'ı */}
      {toolList.length > 0 && (
        <div>
          <h2 className="text-sm font-semibold text-gray-300 mb-3">Araç Durumu</h2>
          <div className="bg-[#111827] border border-[#374151] rounded-xl p-4">
            <div className="flex items-center justify-between mb-3">
              <p className="text-xs text-gray-400">
                {installedCount}/{toolList.length} araç kurulu
              </p>
              <div className="flex-1 mx-4 h-1.5 bg-[#374151] rounded-full overflow-hidden">
                <div
                  className="h-full bg-green-500 transition-all duration-500"
                  style={{ width: `${toolList.length > 0 ? (installedCount / toolList.length) * 100 : 0}%` }}
                />
              </div>
              <span className="text-xs text-gray-500">
                {toolList.length > 0 ? Math.round((installedCount / toolList.length) * 100) : 0}%
              </span>
            </div>

            {/* Kategori özeti */}
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
              {['recon', 'discovery', 'testing', 'analysis'].map((cat) => {
                const catTools = toolList.filter((t) => t.category === cat);
                const catInstalled = catTools.filter((t) => t.installed).length;
                return (
                  <div key={cat} className="text-center">
                    <p className="text-[10px] text-gray-500 capitalize mb-1">{cat}</p>
                    <p className={`text-sm font-bold ${
                      catInstalled === catTools.length && catTools.length > 0
                        ? 'text-green-400'
                        : catInstalled > 0
                        ? 'text-yellow-400'
                        : 'text-gray-600'
                    }`}>
                      {catInstalled}/{catTools.length}
                    </p>
                  </div>
                );
              })}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
