/**
 * SubdomainList — Canlı subdomain listesi (Spec Bölüm 12.4).
 *
 * Özellikler:
 *  - Yeni subdomain gelince yukarıdan kayarak eklenir (animate-slide-in)
 *  - AI skoru progress bar (renk kodlu)
 *  - Sıralama ve filtreleme
 *  - Checkbox seçim + tümünü seç
 *  - "Discovery Fazına Geç" butonu (seçim yapılınca aktif)
 *  - Subdomain'e tıklayınca AI analiz popup'u
 */

import { useState, useMemo, useEffect, useRef } from 'react';
import useScanStore from '../../../store/scanStore';
import { updateSubdomainSelection } from '../../../api/client';
import useUiStore from '../../../store/uiStore';

const PRIORITY_CONFIG = {
  critical: { label: 'Kritik', cls: 'bg-red-500/20 text-red-400 border border-red-500/30' },
  high:     { label: 'Yüksek', cls: 'bg-orange-500/20 text-orange-400 border border-orange-500/30' },
  medium:   { label: 'Orta',   cls: 'bg-yellow-500/20 text-yellow-400 border border-yellow-500/30' },
  low:      { label: 'Düşük',  cls: 'bg-gray-500/20 text-gray-400 border border-gray-500/20' },
};

function scoreColor(score) {
  if (score >= 80) return 'bg-red-500';
  if (score >= 60) return 'bg-orange-500';
  if (score >= 40) return 'bg-yellow-500';
  return 'bg-gray-500';
}

function AiDetailPopup({ sub, onClose }) {
  let tags = [];
  try { tags = Array.isArray(sub.ai_tags) ? sub.ai_tags : JSON.parse(sub.ai_tags ?? '[]'); } catch { tags = []; }
  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60"
      onClick={onClose}
    >
      <div
        className="bg-[#111827] border border-[#374151] rounded-xl p-5 w-full max-w-md mx-4 animate-slide-in"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex justify-between items-start mb-3">
          <p className="font-mono text-sm text-blue-300 truncate mr-3">{sub.subdomain}</p>
          <button onClick={onClose} className="text-gray-500 hover:text-gray-300 flex-shrink-0">✕</button>
        </div>

        {sub.ai_score != null && (
          <div className="flex items-center gap-2 mb-2">
            <span className="text-[10px] text-gray-500">AI Skoru:</span>
            <span className={`text-xs font-bold ${
              sub.ai_score >= 80 ? 'text-red-400'
              : sub.ai_score >= 60 ? 'text-orange-400'
              : sub.ai_score >= 40 ? 'text-yellow-400'
              : 'text-gray-500'}`}>
              {sub.ai_score}/100
            </span>
            <div className="flex-1 h-1.5 bg-[#374151] rounded-full overflow-hidden">
              <div className={`h-full ${scoreColor(sub.ai_score)}`} style={{ width: `${sub.ai_score}%` }} />
            </div>
          </div>
        )}

        {tags.length > 0 && (
          <div className="flex flex-wrap gap-1 mb-3">
            {tags.map((t) => (
              <span key={t} className="text-[10px] bg-blue-500/10 text-blue-400 px-2 py-0.5 rounded border border-blue-500/20">
                {t}
              </span>
            ))}
          </div>
        )}

        {sub.ai_analysis && (
          <p className="text-xs text-gray-300 bg-[#1f2937] rounded-lg p-3 leading-relaxed">
            {sub.ai_analysis}
          </p>
        )}
      </div>
    </div>
  );
}

export default function SubdomainList({ scanId, onSelectionDone }) {
  const subdomains      = useScanStore((s) => s.subdomains);
  const addNotification = useUiStore((s) => s.addNotification);

  const [selected, setSelected]   = useState(new Set());
  const [sortBy, setSortBy]       = useState('ai_score');
  const [sortDir, setSortDir]     = useState('desc');
  const [minScore, setMinScore]   = useState('');
  const [filterWaf, setFilterWaf] = useState('');
  const [filterAlive, setFilterAlive] = useState(true);
  const [detailSub, setDetailSub] = useState(null);
  const [submitting, setSubmitting] = useState(false);

  // Track new IDs for slide-in animation
  const prevIdsRef = useRef(new Set());
  const [newIds, setNewIds] = useState(new Set());

  useEffect(() => {
    const incoming = new Set(subdomains.map((s) => s.id));
    const added = new Set([...incoming].filter((id) => !prevIdsRef.current.has(id)));
    if (added.size > 0 && prevIdsRef.current.size > 0) {
      setNewIds(added);
      const t = setTimeout(() => setNewIds(new Set()), 1200);
      return () => clearTimeout(t);
    }
    prevIdsRef.current = incoming;
  }, [subdomains]);

  // Filtre + sıralama
  const visible = useMemo(() => {
    let list = [...subdomains];
    if (filterAlive) list = list.filter((s) => s.is_alive !== false);
    if (filterWaf === 'yes') list = list.filter((s) => s.waf);
    if (filterWaf === 'no')  list = list.filter((s) => !s.waf);
    if (minScore) list = list.filter((s) => (s.ai_score ?? 0) >= Number(minScore));
    list.sort((a, b) => {
      const av = a[sortBy] ?? '';
      const bv = b[sortBy] ?? '';
      if (av < bv) return sortDir === 'asc' ? -1 : 1;
      if (av > bv) return sortDir === 'asc' ? 1 : -1;
      return 0;
    });
    return list;
  }, [subdomains, filterAlive, filterWaf, minScore, sortBy, sortDir]);

  const toggleSort = (col) => {
    if (sortBy === col) setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'));
    else { setSortBy(col); setSortDir('desc'); }
  };

  const toggleRow = (id) => setSelected((s) => {
    const n = new Set(s);
    n.has(id) ? n.delete(id) : n.add(id);
    return n;
  });

  const selectAll = () => setSelected(new Set(visible.map((s) => s.id)));
  const clearAll  = () => setSelected(new Set());

  const submitSelection = async () => {
    if (!selected.size) return;
    setSubmitting(true);
    try {
      await updateSubdomainSelection(scanId, {
        subdomain_ids: [...selected],
        selected: true,
      });
      addNotification({ title: `${selected.size} subdomain seçildi`, type: 'success' });
      onSelectionDone?.([...selected]);
    } catch (err) {
      addNotification({ title: 'Seçim Hatası', body: err.message, type: 'error' });
    } finally {
      setSubmitting(false);
    }
  };

  const SortIcon = ({ col }) => (
    sortBy !== col
      ? <span className="text-gray-700 ml-0.5">↕</span>
      : <span className="text-blue-400 ml-0.5">{sortDir === 'asc' ? '↑' : '↓'}</span>
  );

  return (
    <div className="flex flex-col h-full">
      {/* Filtreler */}
      <div className="flex items-center gap-3 px-4 py-2 bg-[#111827] border-b border-[#374151] flex-wrap flex-shrink-0">
        <label className="flex items-center gap-1.5 text-xs text-gray-400 cursor-pointer select-none">
          <input
            type="checkbox"
            checked={filterAlive}
            onChange={(e) => setFilterAlive(e.target.checked)}
            className="accent-blue-500"
          />
          Sadece canlı
        </label>

        <select
          value={filterWaf}
          onChange={(e) => setFilterWaf(e.target.value)}
          className="bg-[#1f2937] border border-[#374151] text-xs text-gray-300 rounded px-2 py-1 focus:outline-none focus:border-blue-500"
        >
          <option value="">WAF: Tümü</option>
          <option value="yes">WAF var</option>
          <option value="no">WAF yok</option>
        </select>

        <div className="flex items-center gap-1.5">
          <span className="text-[10px] text-gray-500">Min. AI:</span>
          <input
            type="number"
            min={0}
            max={100}
            value={minScore}
            onChange={(e) => setMinScore(e.target.value)}
            placeholder="0"
            className="bg-[#1f2937] border border-[#374151] text-xs text-gray-300 rounded px-2 py-1 w-14 focus:outline-none focus:border-blue-500"
          />
        </div>

        <span className="text-[10px] text-gray-600 ml-auto">
          {visible.length} / {subdomains.length}
        </span>
      </div>

      {/* Tablo */}
      <div className="flex-1 overflow-auto">
        <table className="w-full text-xs">
          <thead className="sticky top-0 bg-[#0a0e1a] border-b border-[#374151] z-10">
            <tr className="text-gray-500">
              <th className="px-3 py-2 text-left w-8">
                <input
                  type="checkbox"
                  checked={selected.size === visible.length && visible.length > 0}
                  onChange={selected.size === visible.length ? clearAll : selectAll}
                  className="accent-blue-500"
                />
              </th>
              <th
                className="px-3 py-2 text-left cursor-pointer hover:text-gray-300 select-none"
                onClick={() => toggleSort('subdomain')}
              >
                Subdomain <SortIcon col="subdomain" />
              </th>
              <th className="px-3 py-2 text-left">IP</th>
              <th
                className="px-3 py-2 text-center cursor-pointer hover:text-gray-300 select-none"
                onClick={() => toggleSort('status_code')}
              >
                Status <SortIcon col="status_code" />
              </th>
              <th className="px-3 py-2 text-left">Teknoloji</th>
              <th className="px-3 py-2 text-left">WAF</th>
              <th
                className="px-3 py-2 text-center cursor-pointer hover:text-gray-300 select-none"
                onClick={() => toggleSort('ai_score')}
              >
                AI Skoru <SortIcon col="ai_score" />
              </th>
              <th className="px-3 py-2 text-center">Öncelik</th>
              <th className="px-3 py-2 text-center">Detay</th>
            </tr>
          </thead>
          <tbody>
            {visible.length === 0 ? (
              <tr>
                <td colSpan={9} className="text-center py-12 text-gray-600">
                  {subdomains.length === 0
                    ? 'Subdomain bekleniyor…'
                    : 'Filtre eşleşmedi'}
                </td>
              </tr>
            ) : visible.map((sub) => {
              let tech = [];
              let ips  = [];
              try { tech = Array.isArray(sub.tech_stack)   ? sub.tech_stack   : JSON.parse(sub.tech_stack   ?? '[]'); } catch {}
              try { ips  = Array.isArray(sub.ip_addresses) ? sub.ip_addresses : JSON.parse(sub.ip_addresses ?? '[]'); } catch {}
              const score = sub.ai_score;
              const prio  = PRIORITY_CONFIG[sub.priority];
              const isNew = newIds.has(sub.id);

              return (
                <tr
                  key={sub.id}
                  className={`
                    border-b border-[#374151]/40
                    hover:bg-[#1f2937]/50 transition-colors
                    ${selected.has(sub.id) ? 'bg-blue-500/5' : ''}
                    ${isNew ? 'animate-slide-in' : ''}
                  `}
                >
                  <td className="px-3 py-2">
                    <input
                      type="checkbox"
                      checked={selected.has(sub.id)}
                      onChange={() => toggleRow(sub.id)}
                      className="accent-blue-500"
                    />
                  </td>
                  <td className="px-3 py-2 font-mono text-blue-300 max-w-[200px] truncate">
                    {sub.subdomain}
                  </td>
                  <td className="px-3 py-2 text-gray-500 font-mono text-[10px]">
                    {ips[0] ?? '—'}
                  </td>
                  <td className="px-3 py-2 text-center">
                    <span className={`text-[10px] px-1.5 py-0.5 rounded ${
                      sub.status_code === 200 ? 'bg-green-500/20 text-green-400'
                      : sub.status_code === 403 ? 'bg-yellow-500/20 text-yellow-400'
                      : sub.status_code >= 300 && sub.status_code < 400 ? 'bg-blue-500/20 text-blue-400'
                      : 'bg-gray-500/20 text-gray-400'
                    }`}>
                      {sub.status_code ?? '—'}
                    </span>
                  </td>
                  <td className="px-3 py-2">
                    <div className="flex flex-wrap gap-1">
                      {tech.slice(0, 3).map((t) => (
                        <span key={t} className="text-[9px] bg-[#374151] text-gray-400 px-1 py-0.5 rounded">
                          {t}
                        </span>
                      ))}
                    </div>
                  </td>
                  <td className="px-3 py-2 text-[10px] text-yellow-400">{sub.waf ?? '—'}</td>
                  <td className="px-3 py-2">
                    {score != null ? (
                      <div className="flex items-center gap-1.5">
                        <div className="w-14 h-1.5 bg-[#374151] rounded-full overflow-hidden">
                          <div className={`h-full ${scoreColor(score)}`} style={{ width: `${score}%` }} />
                        </div>
                        <span className={`text-[10px] font-bold tabular-nums ${
                          score >= 80 ? 'text-red-400'
                          : score >= 60 ? 'text-orange-400'
                          : score >= 40 ? 'text-yellow-400'
                          : 'text-gray-500'
                        }`}>
                          {score}
                        </span>
                      </div>
                    ) : (
                      <span className="text-gray-600">—</span>
                    )}
                  </td>
                  <td className="px-3 py-2 text-center">
                    {prio ? (
                      <span className={`text-[10px] px-1.5 py-0.5 rounded ${prio.cls}`}>
                        {prio.label}
                      </span>
                    ) : (
                      <span className="text-gray-600">—</span>
                    )}
                  </td>
                  <td className="px-3 py-2 text-center">
                    {sub.ai_analysis && (
                      <button
                        onClick={() => setDetailSub(sub)}
                        className="text-[10px] text-blue-400 hover:text-blue-300 hover:underline"
                      >
                        AI
                      </button>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {/* Footer */}
      <div className="flex items-center justify-between px-4 py-3 border-t border-[#374151] flex-shrink-0">
        <span className="text-xs text-gray-500">
          {selected.size} seçili
          {subdomains.length > 0 && (
            <span className="text-gray-600 ml-1">/ {subdomains.length} subdomain</span>
          )}
        </span>
        <button
          onClick={submitSelection}
          disabled={!selected.size || submitting}
          className="
            flex items-center gap-2 px-4 py-2 rounded-lg text-xs font-semibold
            bg-blue-600 hover:bg-blue-500 text-white
            disabled:opacity-40 disabled:cursor-not-allowed transition-colors
          "
        >
          {submitting ? (
            <>
              <span className="w-3 h-3 border border-white/40 border-t-white rounded-full animate-spin" />
              Kaydediliyor…
            </>
          ) : (
            <>
              Discovery Fazına Geç
              {selected.size > 0 && (
                <span className="bg-white/20 rounded px-1.5 py-0.5 text-[10px]">
                  {selected.size}
                </span>
              )}
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2.5} className="w-3.5 h-3.5">
                <line x1="5" y1="12" x2="19" y2="12" />
                <polyline points="12 5 19 12 12 19" />
              </svg>
            </>
          )}
        </button>
      </div>

      {detailSub && <AiDetailPopup sub={detailSub} onClose={() => setDetailSub(null)} />}
    </div>
  );
}
