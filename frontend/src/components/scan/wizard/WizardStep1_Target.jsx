/**
 * WizardStep1_Target — Adım 1: Hedef, kapsam ve tarama adı.
 *
 * Props:
 *  data     : { target, scope, name }
 *  onChange : (patch) => void
 *  onNext   : () => void
 */

import { useEffect } from 'react';

// ---------------------------------------------------------------------------
// Sabitler
// ---------------------------------------------------------------------------

const SCOPE_OPTIONS = [
  {
    value: 'single',
    label: 'Tek Domain',
    sublabel: 'Sadece bu hedef',
    desc: 'Girilen domain/URL/IP üzerinde doğrudan URL keşfi ve test yapılır. Subdomain taraması yapılmaz. Hızlı sonuç almak için idealdir.',
    icon: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8} className="w-5 h-5">
        <circle cx="12" cy="12" r="10" />
        <circle cx="12" cy="12" r="6" />
        <circle cx="12" cy="12" r="2" />
      </svg>
    ),
    pros: ['Hızlı', 'Az gürültü', 'Belirli bir URL için'],
    cons: ['Subdomain kör noktaları'],
  },
  {
    value: 'subdomains',
    label: 'Subdomainler Dahil',
    sublabel: 'Kapsamlı keşif',
    desc: 'Önce subdomain enumeration yapılır (subfinder, amass, vb.), canlı subdomainler tespit edilir, ardından seçtiğin subdomainler üzerinde URL keşfi ve test yapılır.',
    icon: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8} className="w-5 h-5">
        <circle cx="12" cy="5" r="2" />
        <circle cx="5" cy="19" r="2" />
        <circle cx="19" cy="19" r="2" />
        <line x1="12" y1="7" x2="5" y2="17" />
        <line x1="12" y1="7" x2="19" y2="17" />
        <line x1="5" y1="19" x2="19" y2="19" />
      </svg>
    ),
    pros: ['Kapsamlı kapsam', 'Gizli endpointler', 'AI subdomain skoru'],
    cons: ['Daha uzun süre', 'Onay adımı gerekir'],
  },
];

// ---------------------------------------------------------------------------
// Validasyon
// ---------------------------------------------------------------------------

function validateTarget(raw) {
  const v = raw.trim();
  if (!v) return null; // henüz yazılmadı

  // IPv4
  if (/^\d{1,3}(\.\d{1,3}){3}$/.test(v)) {
    const parts = v.split('.');
    if (parts.every((p) => parseInt(p, 10) <= 255)) return 'ok';
    return 'Geçersiz IP adresi.';
  }

  // CIDR (192.168.1.0/24)
  if (/^\d{1,3}(\.\d{1,3}){3}\/\d{1,2}$/.test(v)) return 'ok';

  // URL veya domain — scheme opsiyonel
  const noScheme = v.replace(/^https?:\/\//i, '').split('/')[0].split('?')[0];
  if (/^[\w.-]+\.[a-z]{2,}$/i.test(noScheme)) return 'ok';

  return 'Geçerli bir domain (örn: example.com), URL veya IP adresi girin.';
}

// ---------------------------------------------------------------------------
// Otomatik isim üretici
// ---------------------------------------------------------------------------

function autoName(target, scope) {
  if (!target) return '';
  const host = target
    .trim()
    .replace(/^https?:\/\//i, '')
    .split('/')[0]
    .split('?')[0];
  const date = new Date().toLocaleDateString('tr-TR', { month: 'short', year: 'numeric' });
  const scopeLabel = scope === 'subdomains' ? 'Kapsamlı' : 'Hızlı';
  return `${scopeLabel} Tarama — ${host} — ${date}`;
}

// ---------------------------------------------------------------------------
// Bileşen
// ---------------------------------------------------------------------------

export default function WizardStep1_Target({ data, onChange, onNext }) {
  const validationResult = validateTarget(data.target);
  const isValid = validationResult === 'ok';
  const hasError = validationResult !== null && validationResult !== 'ok';

  // Hedef veya kapsam değişince isim alanını otomatik doldur
  // (sadece kullanıcı henüz elle değiştirmediyse)
  useEffect(() => {
    if (!data._nameManuallySet && data.target) {
      onChange({ name: autoName(data.target, data.scope) });
    }
  }, [data.target, data.scope]); // eslint-disable-line react-hooks/exhaustive-deps

  const handleNameChange = (e) => {
    onChange({ name: e.target.value, _nameManuallySet: true });
  };

  const handleNameBlur = () => {
    // İsim boşaltılırsa otomatik yenile
    if (!data.name?.trim()) {
      onChange({ name: autoName(data.target, data.scope), _nameManuallySet: false });
    }
  };

  return (
    <div className="space-y-7">

      {/* ── Hedef alanı ── */}
      <div>
        <label className="block text-sm font-semibold text-gray-200 mb-1.5">
          Hedef
        </label>
        <p className="text-xs text-gray-500 mb-3">
          Domain, tam URL veya IP adresi. Protokol opsiyonel.
        </p>

        <div className="relative">
          <input
            type="text"
            value={data.target}
            onChange={(e) => onChange({ target: e.target.value })}
            onKeyDown={(e) => e.key === 'Enter' && isValid && onNext()}
            placeholder="example.com  ·  https://app.example.com  ·  192.168.1.1"
            autoFocus
            spellCheck={false}
            className={`
              w-full bg-[#0a0e1a] border rounded-xl px-4 py-3.5
              text-sm font-mono text-white placeholder-gray-600
              focus:outline-none transition-all duration-200 pr-10
              ${isValid   ? 'border-green-500/60 focus:border-green-500'
              : hasError  ? 'border-red-500/60  focus:border-red-500'
                          : 'border-[#374151]   focus:border-blue-500'}
            `}
          />
          {/* Durum ikonu */}
          <span className="absolute right-3 top-1/2 -translate-y-1/2 pointer-events-none">
            {isValid && (
              <svg viewBox="0 0 24 24" fill="none" stroke="#10b981" strokeWidth={2.5} className="w-4 h-4">
                <polyline points="20 6 9 17 4 12" />
              </svg>
            )}
            {hasError && (
              <svg viewBox="0 0 24 24" fill="none" stroke="#ef4444" strokeWidth={2.5} className="w-4 h-4">
                <line x1="18" y1="6" x2="6" y2="18" /><line x1="6" y1="6" x2="18" y2="18" />
              </svg>
            )}
          </span>
        </div>

        {/* Validasyon mesajı */}
        <div className="h-5 mt-1.5">
          {hasError && (
            <p className="text-xs text-red-400 flex items-center gap-1">
              <span>⚠</span>{validationResult}
            </p>
          )}
          {isValid && (
            <p className="text-xs text-green-500">Geçerli hedef</p>
          )}
        </div>
      </div>

      {/* ── Kapsam seçimi ── */}
      <div>
        <label className="block text-sm font-semibold text-gray-200 mb-1.5">
          Tarama Kapsamı
        </label>
        <p className="text-xs text-gray-500 mb-3">
          Sadece bu hedefi mi tara, yoksa subdomainleri de keşfet mi?
        </p>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          {SCOPE_OPTIONS.map((opt) => {
            const isSelected = data.scope === opt.value;
            return (
              <button
                key={opt.value}
                type="button"
                onClick={() => onChange({ scope: opt.value })}
                className={`
                  relative text-left p-4 rounded-xl border transition-all duration-200
                  ${isSelected
                    ? 'border-blue-500 bg-blue-500/10 ring-1 ring-blue-500/30'
                    : 'border-[#374151] bg-[#0a0e1a] hover:border-[#4b5563] hover:bg-[#111827]'}
                `}
              >
                {/* Radio göstergesi */}
                <div className="flex items-start gap-3">
                  <div className={`
                    mt-0.5 w-4 h-4 rounded-full border-2 flex items-center justify-center flex-shrink-0
                    transition-colors
                    ${isSelected ? 'border-blue-400' : 'border-[#4b5563]'}
                  `}>
                    {isSelected && (
                      <div className="w-2 h-2 rounded-full bg-blue-400" />
                    )}
                  </div>

                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-0.5">
                      <span className={`text-sm font-semibold ${isSelected ? 'text-white' : 'text-gray-300'}`}>
                        {opt.label}
                      </span>
                      <span className={`text-[10px] ${isSelected ? 'text-blue-400' : 'text-gray-600'}`}>
                        {opt.sublabel}
                      </span>
                    </div>
                    <p className="text-xs text-gray-500 leading-relaxed mb-2">
                      {opt.desc}
                    </p>
                    {/* Pro/con pills */}
                    <div className="flex flex-wrap gap-1">
                      {opt.pros.map((p) => (
                        <span key={p} className={`text-[9px] px-1.5 py-0.5 rounded border
                          ${isSelected
                            ? 'border-green-500/30 text-green-400 bg-green-500/5'
                            : 'border-[#374151] text-gray-600'}`}>
                          + {p}
                        </span>
                      ))}
                      {opt.cons.map((c) => (
                        <span key={c} className={`text-[9px] px-1.5 py-0.5 rounded border
                          ${isSelected
                            ? 'border-red-500/20 text-red-400/70 bg-red-500/5'
                            : 'border-[#374151] text-gray-600'}`}>
                          − {c}
                        </span>
                      ))}
                    </div>
                  </div>

                  {/* İkon */}
                  <span className={`flex-shrink-0 transition-colors ${isSelected ? 'text-blue-400' : 'text-gray-600'}`}>
                    {opt.icon}
                  </span>
                </div>
              </button>
            );
          })}
        </div>
      </div>

      {/* ── Tarama adı ── */}
      <div>
        <label className="block text-sm font-semibold text-gray-200 mb-1.5">
          Tarama Adı
          <span className="text-gray-600 font-normal text-xs ml-2">— opsiyonel, otomatik üretilir</span>
        </label>
        <input
          type="text"
          value={data.name ?? ''}
          onChange={handleNameChange}
          onBlur={handleNameBlur}
          placeholder="Otomatik üretilecek…"
          className="w-full bg-[#0a0e1a] border border-[#374151] rounded-xl px-4 py-3
            text-sm text-gray-300 placeholder-gray-700
            focus:outline-none focus:border-blue-500 transition-colors"
        />
        <p className="text-[10px] text-gray-600 mt-1">
          Hedef ve kapsam seçimine göre otomatik dolar. İstersen değiştirebilirsin.
        </p>
      </div>

      {/* ── İleri ── */}
      <button
        onClick={onNext}
        disabled={!isValid}
        className="
          w-full py-3.5 rounded-xl text-sm font-semibold
          bg-blue-600 hover:bg-blue-500 text-white
          disabled:opacity-40 disabled:cursor-not-allowed
          transition-all duration-200 flex items-center justify-center gap-2
        "
      >
        Devam Et
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2.5} className="w-4 h-4">
          <line x1="5" y1="12" x2="19" y2="12" />
          <polyline points="12 5 19 12 12 19" />
        </svg>
      </button>
    </div>
  );
}
