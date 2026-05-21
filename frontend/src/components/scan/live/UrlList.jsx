/**
 * UrlList — Canlı URL listesi (Spec Bölüm 12.5).
 *
 * Özellikler:
 *  - Virtualized list (react-virtual) — 10k+ URL için
 *  - Kategori badge chip filtreleri (xss, sqli vb.)
 *  - Risk skoru slider
 *  - Keyword arama
 *  - URL tıklayınca yeni sekme
 *  - Checkbox seçim + toplu test başlatma
 */

import { useState, useMemo, useRef, useCallback } from 'react';
import { useVirtual } from 'react-virtual';
import useScanStore from '../../../store/scanStore';

// Dizi veya JSON string olarak gelen alanı güvenli şekilde array'e çevirir
function parseArray(val) {
  if (Array.isArray(val)) return val;
  if (!val) return [];
  try { const r = JSON.parse(val); return Array.isArray(r) ? r : []; } catch { return []; }
}

const CATEGORIES = [
  { id: 'xss',      label: 'XSS',       cls: 'bg-red-500/20 text-red-400 border-red-500/30' },
  { id: 'sqli',     label: 'SQLi',      cls: 'bg-orange-500/20 text-orange-400 border-orange-500/30' },
  { id: 'lfi',      label: 'LFI',       cls: 'bg-yellow-500/20 text-yellow-400 border-yellow-500/30' },
  { id: 'redirect', label: 'Redirect',  cls: 'bg-blue-500/20 text-blue-400 border-blue-500/30' },
  { id: 'ssrf',     label: 'SSRF',      cls: 'bg-purple-500/20 text-purple-400 border-purple-500/30' },
  { id: 'rce',      label: 'RCE',       cls: 'bg-red-600/30 text-red-300 border-red-600/30' },
  { id: 'idor',     label: 'IDOR',      cls: 'bg-pink-500/20 text-pink-400 border-pink-500/30' },
];

const CATEGORY_COLOR = Object.fromEntries(CATEGORIES.map((c) => [c.id, c.cls]));

const SOURCE_LABELS = {
  gau: 'GAU', wayback: 'Wayback', katana: 'Katana',
  hakrawler: 'Hakrawler', gospider: 'GoSpider',
  paramspider: 'ParamSpider', ffuf: 'FFUF',
};

function RiskBadge({ score }) {
  const cls = score >= 80 ? 'bg-red-500/20 text-red-400'
            : score >= 60 ? 'bg-orange-500/20 text-orange-400'
            : score >= 40 ? 'bg-yellow-500/20 text-yellow-400'
                          : 'bg-gray-500/20 text-gray-500';
  return (
    <span className={`text-[10px] font-bold px-1.5 py-0.5 rounded tabular-nums ${cls}`}>
      {score}
    </span>
  );
}

const ROW_HEIGHT = 38;

export default function UrlList({ onSelectForTest }) {
  const urls = useScanStore((s) => s.urls);

  const [activeCategories, setActiveCategories] = useState(new Set());
  const [minScore, setMinScore]     = useState(0);
  const [keyword, setKeyword]       = useState('');
  const [filterSource, setFilterSource] = useState('');
  const [onlyUntested, setOnlyUntested] = useState(false);
  const [selected, setSelected]     = useState(new Set());
  const parentRef = useRef(null);

  const toggleCategory = (cat) => {
    setActiveCategories((prev) => {
      const next = new Set(prev);
      next.has(cat) ? next.delete(cat) : next.add(cat);
      return next;
    });
  };

  const visible = useMemo(() => {
    let list = [...urls];

    if (activeCategories.size > 0) {
      list = list.filter((u) => {
        const cats = parseArray(u.vuln_categories);
        return [...activeCategories].some((c) => cats.includes(c));
      });
    }

    if (minScore > 0) {
      list = list.filter((u) => (u.risk_score ?? 0) >= minScore);
    }

    if (keyword.trim()) {
      const kw = keyword.toLowerCase();
      list = list.filter((u) => {
        if (u.url.toLowerCase().includes(kw)) return true;
        return parseArray(u.keywords).some((k) => k.toLowerCase().includes(kw));
      });
    }

    if (filterSource) {
      list = list.filter((u) => u.source === filterSource);
    }

    if (onlyUntested) {
      list = list.filter((u) => !u.is_tested);
    }

    return list;
  }, [urls, activeCategories, minScore, keyword, filterSource, onlyUntested]);

  const rowVirtualizer = useVirtual({
    size: visible.length,
    parentRef,
    estimateSize: useCallback(() => ROW_HEIGHT, []),
    overscan: 10,
  });

  const toggleRow = (id) => setSelected((s) => {
    const n = new Set(s);
    n.has(id) ? n.delete(id) : n.add(id);
    return n;
  });

  const selectAll = () => setSelected(new Set(visible.map((u) => u.id)));
  const clearAll  = () => setSelected(new Set());

  const allSources = useMemo(() => {
    const set = new Set(urls.map((u) => u.source).filter(Boolean));
    return [...set];
  }, [urls]);

  return (
    <div className="flex flex-col h-full">

      {/* Kategori chip'leri */}
      <div className="flex items-center gap-1.5 px-4 py-2 bg-[#111827] border-b border-[#374151] flex-wrap flex-shrink-0">
        <span className="text-[10px] text-gray-600 mr-1">Kategori:</span>
        {CATEGORIES.map((cat) => {
          const active = activeCategories.has(cat.id);
          return (
            <button
              key={cat.id}
              onClick={() => toggleCategory(cat.id)}
              className={`
                text-[10px] px-2 py-0.5 rounded border transition-colors
                ${active ? cat.cls : 'border-[#374151] text-gray-600 hover:text-gray-400 hover:border-gray-500'}
              `}
            >
              {cat.label}
            </button>
          );
        })}
        {activeCategories.size > 0 && (
          <button
            onClick={() => setActiveCategories(new Set())}
            className="text-[10px] text-gray-600 hover:text-gray-300 ml-1"
          >
            ✕ Temizle
          </button>
        )}
      </div>

      {/* İkincil filtreler */}
      <div className="flex items-center gap-4 px-4 py-2 bg-[#0a0e1a] border-b border-[#374151] flex-shrink-0 flex-wrap">
        {/* Risk slider */}
        <div className="flex items-center gap-2">
          <span className="text-[10px] text-gray-500 whitespace-nowrap">Risk ≥ {minScore}</span>
          <input
            type="range"
            min={0}
            max={100}
            step={10}
            value={minScore}
            onChange={(e) => setMinScore(Number(e.target.value))}
            className="w-24 accent-blue-500 cursor-pointer"
          />
        </div>

        {/* Keyword */}
        <input
          type="text"
          value={keyword}
          onChange={(e) => setKeyword(e.target.value)}
          placeholder="Keyword ara…"
          className="bg-[#1f2937] border border-[#374151] text-[10px] text-gray-300 rounded px-2 py-1 w-28 focus:outline-none focus:border-blue-500 placeholder-gray-600"
        />

        {/* Kaynak */}
        {allSources.length > 0 && (
          <select
            value={filterSource}
            onChange={(e) => setFilterSource(e.target.value)}
            className="bg-[#1f2937] border border-[#374151] text-[10px] text-gray-300 rounded px-2 py-1 focus:outline-none focus:border-blue-500"
          >
            <option value="">Kaynak: Tümü</option>
            {allSources.map((s) => (
              <option key={s} value={s}>{SOURCE_LABELS[s] ?? s}</option>
            ))}
          </select>
        )}

        {/* Test edilmedi */}
        <label className="flex items-center gap-1.5 text-[10px] text-gray-500 cursor-pointer select-none">
          <input
            type="checkbox"
            checked={onlyUntested}
            onChange={(e) => setOnlyUntested(e.target.checked)}
            className="accent-blue-500"
          />
          Sadece test edilmedi
        </label>

        {/* Stats */}
        <div className="ml-auto flex items-center gap-3 text-[10px] text-gray-600">
          <span>{visible.length} / {urls.length} URL</span>
          {visible.length > 0 && (
            <button
              onClick={selected.size === visible.length ? clearAll : selectAll}
              className="text-blue-400 hover:underline"
            >
              {selected.size === visible.length ? 'Seçimi Kaldır' : `Tümünü Seç (${visible.length})`}
            </button>
          )}
        </div>
      </div>

      {/* Tablo başlığı */}
      <div className="grid grid-cols-[90px_1fr_50px_130px_70px_60px_40px] gap-0 px-4 py-2 bg-[#111827] border-b border-[#374151] text-[10px] text-gray-500 flex-shrink-0">
        <span>Kaynak</span>
        <span>URL</span>
        <span className="text-center">Params</span>
        <span>Kategoriler</span>
        <span>Keywords</span>
        <span className="text-center">Risk</span>
        <span className="text-center">Seç</span>
      </div>

      {/* Virtualized list */}
      <div ref={parentRef} className="flex-1 overflow-auto">
        {visible.length === 0 ? (
          <div className="flex items-center justify-center h-32 text-gray-600 text-sm">
            {urls.length === 0 ? 'URL bekleniyor…' : 'Filtre eşleşmedi'}
          </div>
        ) : (
          <div style={{ height: rowVirtualizer.totalSize, position: 'relative' }}>
            {rowVirtualizer.virtualItems.map((vRow) => {
              const url  = visible[vRow.index];
              const cats = parseArray(url.vuln_categories);
              const keys = parseArray(url.keywords);

              return (
                <div
                  key={url.id}
                  style={{ position: 'absolute', top: vRow.start, width: '100%', height: ROW_HEIGHT }}
                  className={`
                    grid grid-cols-[90px_1fr_50px_130px_70px_60px_40px] gap-0
                    items-center px-4 border-b border-[#374151]/30
                    hover:bg-[#1f2937]/50 transition-colors
                    ${selected.has(url.id) ? 'bg-blue-500/5' : ''}
                  `}
                >
                  <span className="text-[9px] text-gray-600 truncate">
                    {SOURCE_LABELS[url.source] ?? url.source ?? '—'}
                  </span>
                  <a
                    href={url.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    onClick={(e) => e.stopPropagation()}
                    className="text-[10px] font-mono text-blue-300 hover:underline truncate block"
                    title={url.url}
                  >
                    {url.url}
                  </a>
                  <span className="text-center text-[10px] text-gray-500 tabular-nums">
                    {url.param_count ?? 0}
                  </span>
                  <div className="flex flex-wrap gap-0.5 overflow-hidden max-h-5">
                    {cats.slice(0, 3).map((c) => (
                      <span
                        key={c}
                        className={`text-[9px] px-1 py-0.5 rounded border ${
                          CATEGORY_COLOR[c] ?? 'bg-gray-500/20 text-gray-400 border-gray-500/20'
                        }`}
                      >
                        {c}
                      </span>
                    ))}
                  </div>
                  <div className="flex flex-wrap gap-0.5 overflow-hidden max-h-5">
                    {keys.slice(0, 2).map((k) => (
                      <span key={k} className="text-[9px] text-gray-600">{k}</span>
                    ))}
                  </div>
                  <div className="text-center">
                    <RiskBadge score={url.risk_score ?? 0} />
                  </div>
                  <div className="text-center">
                    <input
                      type="checkbox"
                      checked={selected.has(url.id)}
                      onChange={() => toggleRow(url.id)}
                      className="accent-blue-500"
                    />
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* Footer */}
      {onSelectForTest && selected.size > 0 && (
        <div className="flex items-center justify-between px-4 py-3 border-t border-[#374151] bg-[#111827] flex-shrink-0">
          <span className="text-xs text-gray-400">
            <strong className="text-white">{selected.size}</strong> URL seçili
          </span>
          <button
            onClick={() => onSelectForTest([...selected])}
            className="flex items-center gap-2 px-4 py-2 rounded-lg text-xs font-semibold
              bg-blue-600 hover:bg-blue-500 text-white transition-colors"
          >
            Test Fazına Taşı
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2.5} className="w-3.5 h-3.5">
              <line x1="5" y1="12" x2="19" y2="12" />
              <polyline points="12 5 19 12 12 19" />
            </svg>
          </button>
        </div>
      )}
    </div>
  );
}
