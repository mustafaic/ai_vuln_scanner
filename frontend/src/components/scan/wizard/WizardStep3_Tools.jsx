/**
 * WizardStep3_Tools — Adım 3: Araç seçimi ve tarama özeti.
 *
 * Özellikler:
 *  - Araçlar kategoriye göre gruplandırılmış (Recon | Discovery | Analysis | Testing)
 *  - Her araç: checkbox, isim, kısa açıklama, kurulum durumu, inline kurulum
 *  - Hızlı seçim: "Tümünü Seç" | "Sadece Kurulanlar" | "Hiçbirini Seçme"
 *  - Kurulu olmayan araçlar grayed-out + "Kur" butonu
 *  - Alt: özet (hedef + mod + araç sayısı) + Başlat
 *
 * Props:
 *  data     : { target, scope, mode, name, tools?: string[] }
 *  onChange : (patch) => void
 *  onStart  : () => void
 *  onBack   : () => void
 *  loading  : boolean
 */

import { useMemo } from 'react';
import useToolStore from '../../../store/toolStore';

// ---------------------------------------------------------------------------
// Araç açıklamaları ve kategori grupları
// ---------------------------------------------------------------------------

const TOOL_META = {
  // Recon
  subfinder:   { desc: 'Pasif subdomain enumeration (ProjectDiscovery)', required: false },
  amass:       { desc: 'OWASP; DNS bruteforce + pasif tarama', required: false },
  assetfinder: { desc: 'Hızlı passive subdomain keşfi', required: false },
  dnsx:        { desc: 'DNS sorguları ve A kaydı doğrulama', required: false },
  httpx:       { desc: 'HTTP probing, başlık ve teknoloji tespiti', required: true },
  whatweb:     { desc: 'Web teknoloji tespiti (CMS, framework)', required: false },
  wafw00f:     { desc: 'Web Application Firewall tespiti', required: false },
  // Discovery
  gau:         { desc: 'GetAllUrls — arşivden URL çekimi', required: false },
  waybackurls: { desc: 'Wayback Machine URL arşivi', required: false },
  katana:      { desc: 'Aktif web crawler (JS aware)', required: false },
  hakrawler:   { desc: 'Hızlı passive + active crawler', required: false },
  gospider:    { desc: 'Paralel spider, JS parsing destekli', required: false },
  paramspider: { desc: 'URL parametre toplayıcı', required: false },
  ffuf:        { desc: 'Directory & endpoint brute-force', required: false },
  gf:          { desc: 'GF Pattern matching (XSS, SQLi vb.)', required: false },
  // Testing
  nuclei:      { desc: 'Template-tabanlı zafiyet tarayıcı', required: false },
  dalfox:      { desc: 'XSS tespiti ve sömürüsü', required: false },
  sqlmap:      { desc: 'Otomatik SQL enjeksiyonu tespiti', required: false },
};

const CATEGORY_GROUPS = [
  {
    id: 'recon',
    label: 'Keşif',
    sublabel: 'Recon',
    icon: '🔍',
    tools: ['subfinder', 'amass', 'assetfinder', 'dnsx', 'httpx', 'whatweb', 'wafw00f'],
  },
  {
    id: 'discovery',
    label: 'URL Keşfi',
    sublabel: 'Discovery',
    icon: '🕷',
    tools: ['gau', 'waybackurls', 'katana', 'hakrawler', 'gospider', 'paramspider', 'ffuf', 'gf'],
  },
  {
    id: 'testing',
    label: 'Test',
    sublabel: 'Testing',
    icon: '⚡',
    tools: ['nuclei', 'dalfox', 'sqlmap', 'wafw00f'],
  },
];

const MODE_LABEL  = { stealth: 'Gizli', normal: 'Normal', aggressive: 'Agresif' };
const SCOPE_LABEL = { single: 'Tek domain', subdomains: 'Subdomainler dahil' };

// ---------------------------------------------------------------------------
// Özet kutusu
// ---------------------------------------------------------------------------

function SummaryBox({ data, installedSelected, totalSelected }) {
  return (
    <div className="bg-[#0a0e1a] border border-[#374151] rounded-xl p-4 space-y-2">
      <p className="text-[10px] text-gray-500 uppercase tracking-wider mb-3">Tarama Özeti</p>
      {[
        { label: 'Hedef',   value: data.target || '—', mono: true },
        { label: 'Kapsam',  value: SCOPE_LABEL[data.scope]  ?? data.scope },
        { label: 'Mod',     value: MODE_LABEL[data.mode]    ?? data.mode },
        { label: 'Araçlar', value: `${installedSelected} kurulu / ${totalSelected} seçili` },
        { label: 'Ad',      value: data.name || '(isimsiz)' },
      ].map(({ label, value, mono }) => (
        <div key={label} className="flex items-start gap-2">
          <span className="text-[10px] text-gray-600 w-14 flex-shrink-0">{label}</span>
          <span className={`text-[10px] ${mono ? 'font-mono text-blue-300' : 'text-gray-300'} break-all`}>
            {value}
          </span>
        </div>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Ana bileşen
// ---------------------------------------------------------------------------

export default function WizardStep3_Tools({ data, onChange, onStart, onBack, loading }) {
  const storeTools  = useToolStore((s) => s.tools);
  const installTool = useToolStore((s) => s.installTool);
  const installing  = useToolStore((s) => s.installing);

  // Tüm bilinen araç isimleri (store'dan + TOOL_META'dan birleşim)
  const allToolNames = useMemo(() => {
    const fromStore = Object.keys(storeTools);
    const fromMeta  = Object.keys(TOOL_META);
    return [...new Set([...fromStore, ...fromMeta])];
  }, [storeTools]);

  // Seçili araçlar — null = tümü seçili (varsayılan)
  const selectedTools = useMemo(() => {
    if (data.tools === null || data.tools === undefined) {
      return new Set(allToolNames);
    }
    return new Set(data.tools);
  }, [data.tools, allToolNames]);

  const installedNames = useMemo(
    () => new Set(Object.keys(storeTools).filter((n) => storeTools[n]?.installed)),
    [storeTools],
  );

  // Sayılar
  const totalSelected     = selectedTools.size;
  const installedSelected = [...selectedTools].filter((n) => installedNames.has(n)).length;
  const missingSelected   = totalSelected - installedSelected;

  // Aksiyonlar
  const setSelected = (names) => onChange({ tools: [...names] });

  const toggleTool = (name) => {
    const next = new Set(selectedTools);
    next.has(name) ? next.delete(name) : next.add(name);
    setSelected(next);
  };

  const selectAll       = () => setSelected(new Set(allToolNames));
  const selectInstalled = () => setSelected(new Set(installedNames));
  const selectNone      = () => setSelected(new Set());

  return (
    <div className="space-y-6">

      {/* Hızlı seçim */}
      <div className="flex items-center gap-2 flex-wrap">
        <span className="text-xs text-gray-500">Hızlı seçim:</span>
        <button onClick={selectAll}
          className="text-xs px-3 py-1 rounded-lg bg-[#1f2937] border border-[#374151] text-gray-400 hover:text-white hover:border-gray-500 transition-colors">
          Tümünü Seç
        </button>
        <button onClick={selectInstalled}
          className="text-xs px-3 py-1 rounded-lg bg-green-500/10 border border-green-500/30 text-green-400 hover:bg-green-500/20 transition-colors">
          ✓ Sadece Kurulanlar ({installedNames.size})
        </button>
        <button onClick={selectNone}
          className="text-xs px-3 py-1 rounded-lg bg-[#1f2937] border border-[#374151] text-gray-500 hover:text-gray-300 transition-colors">
          Hiçbirini Seçme
        </button>
        <span className="text-[10px] text-gray-600 ml-auto">
          {installedSelected} kurulu · {totalSelected}/{allToolNames.length} seçili
        </span>
      </div>

      {/* Kategori grupları */}
      {CATEGORY_GROUPS.map((group) => {
        const groupTools = group.tools.filter((n) => allToolNames.includes(n) || TOOL_META[n]);
        if (!groupTools.length) return null;

        const groupInstalled = groupTools.filter((n) => installedNames.has(n)).length;

        return (
          <div key={group.id}>
            {/* Grup başlığı */}
            <div className="flex items-center gap-2 mb-2">
              <span className="text-base">{group.icon}</span>
              <span className="text-xs font-semibold text-gray-300">{group.label}</span>
              <span className="text-[10px] text-gray-600 font-mono">{group.sublabel}</span>
              <span className={`text-[10px] ml-auto ${
                groupInstalled === groupTools.length ? 'text-green-500'
                : groupInstalled > 0 ? 'text-yellow-500'
                : 'text-gray-600'}`}>
                {groupInstalled}/{groupTools.length} kurulu
              </span>
            </div>

            {/* Araç grid */}
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-1.5">
              {groupTools.map((name) => {
                const storeTool    = storeTools[name];
                const meta         = TOOL_META[name];
                const installed    = storeTool?.installed ?? false;
                const isInstalling = installing.has(name);
                const isSelected   = selectedTools.has(name);
                const isRequired   = meta?.required ?? storeTool?.required ?? false;
                const desc         = meta?.desc ?? storeTool?.description ?? '';

                return (
                  <div
                    key={name}
                    onClick={() => !isRequired && toggleTool(name)}
                    className={`
                      flex items-center gap-3 px-3 py-2.5 rounded-lg border
                      transition-all duration-150
                      ${isRequired
                        ? 'border-blue-500/30 bg-blue-500/5 cursor-default'
                        : isSelected
                          ? installed
                            ? 'border-green-500/40 bg-green-500/5 hover:border-green-500/60 cursor-pointer'
                            : 'border-[#374151] bg-[#111827] hover:border-gray-500 cursor-pointer'
                          : 'border-[#374151] bg-[#0a0e1a] opacity-40 cursor-pointer hover:opacity-60'}
                    `}
                  >
                    {/* Checkbox */}
                    <div className={`
                      w-4 h-4 rounded border flex-shrink-0 flex items-center justify-center
                      transition-colors
                      ${isRequired
                        ? 'border-blue-500 bg-blue-500'
                        : isSelected
                          ? 'border-blue-500 bg-blue-500'
                          : 'border-[#4b5563]'}
                    `}>
                      {(isSelected || isRequired) && (
                        <svg viewBox="0 0 12 12" fill="none" stroke="white" strokeWidth={2.5} className="w-2.5 h-2.5">
                          <polyline points="2,6 5,9 10,3" />
                        </svg>
                      )}
                    </div>

                    {/* Kurulum durumu noktası */}
                    <span className={`w-2 h-2 rounded-full flex-shrink-0 ${
                      isInstalling ? 'bg-yellow-400 animate-pulse-dot'
                      : installed  ? 'bg-green-400'
                                   : 'bg-red-500/60'
                    }`} title={installed ? 'Kurulu' : isInstalling ? 'Kuruluyor…' : 'Kurulu değil'} />

                    {/* İsim + açıklama */}
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-1.5">
                        <span className={`text-xs font-mono font-medium ${isSelected || isRequired ? 'text-white' : 'text-gray-500'}`}>
                          {name}
                        </span>
                        {isRequired && (
                          <span className="text-[9px] bg-blue-500/20 text-blue-400 px-1 py-0.5 rounded">
                            zorunlu
                          </span>
                        )}
                      </div>
                      {desc && (
                        <p className="text-[9px] text-gray-600 truncate mt-0.5">{desc}</p>
                      )}
                    </div>

                    {/* Kurulum butonu */}
                    {!installed && !isInstalling && (
                      <button
                        onClick={(e) => { e.stopPropagation(); installTool(name); }}
                        className="flex-shrink-0 text-[9px] px-2 py-0.5 rounded border border-yellow-500/40 text-yellow-400 hover:bg-yellow-500/10 transition-colors"
                      >
                        Kur
                      </button>
                    )}
                    {isInstalling && (
                      <span className="flex-shrink-0 text-[9px] text-yellow-400">Kuruluyor…</span>
                    )}
                  </div>
                );
              })}
            </div>
          </div>
        );
      })}

      {/* Eksik araç uyarısı */}
      {missingSelected > 0 && (
        <div className="flex items-start gap-3 bg-yellow-500/8 border border-yellow-500/25 rounded-xl p-3">
          <span className="text-yellow-400 text-sm flex-shrink-0">⚠</span>
          <div>
            <p className="text-xs text-yellow-400 font-medium">
              {missingSelected} seçili araç kurulu değil
            </p>
            <p className="text-[10px] text-gray-500 mt-0.5">
              Tarama başladığında bu araçlar atlanır. "Sadece Kurulanlar" seçeneğini
              kullanabilir veya araçları kurabilirsin.
            </p>
          </div>
        </div>
      )}

      {/* Özet */}
      <SummaryBox
        data={data}
        installedSelected={installedSelected}
        totalSelected={totalSelected}
      />

      {/* Navigasyon */}
      <div className="flex gap-3">
        <button
          onClick={onBack}
          className="flex items-center gap-2 px-5 py-3 rounded-xl text-sm text-gray-400
            border border-[#374151] hover:border-[#4b5563] hover:text-gray-200 transition-colors"
        >
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2.5} className="w-4 h-4">
            <line x1="19" y1="12" x2="5" y2="12" />
            <polyline points="12 19 5 12 12 5" />
          </svg>
          Geri
        </button>

        <button
          onClick={onStart}
          disabled={loading || totalSelected === 0}
          className="
            flex-1 py-3 rounded-xl text-sm font-bold text-white
            bg-blue-600 hover:bg-blue-500
            disabled:opacity-40 disabled:cursor-not-allowed
            transition-all duration-200
            flex items-center justify-center gap-2
          "
        >
          {loading ? (
            <>
              <span className="w-4 h-4 border-2 border-white/40 border-t-white rounded-full animate-spin" />
              Başlatılıyor…
            </>
          ) : (
            <>
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2.5} className="w-4 h-4">
                <polygon points="5,3 19,12 5,21" fill="currentColor" />
              </svg>
              Taramayı Başlat
            </>
          )}
        </button>
      </div>
    </div>
  );
}
