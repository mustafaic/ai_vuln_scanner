/**
 * WizardStep2_Mode — Adım 2: Tarama modu seçimi.
 *
 * 3 kart: Stealth (yeşil) | Normal (mavi) | Aggressive (kırmızı)
 * Her kart: açıklama, hız göstergesi, gizlilik göstergesi, detay listesi.
 *
 * Props:
 *  data     : { mode }
 *  onChange : (patch) => void
 *  onNext   : () => void
 *  onBack   : () => void
 */

// ---------------------------------------------------------------------------
// Görsel gösterge bileşenleri
// ---------------------------------------------------------------------------

/** Dolu segmentlerden oluşan bar göstergesi (1-5 segment). */
function SegmentBar({ filled, total = 5, color }) {
  return (
    <div className="flex items-center gap-0.5">
      {Array.from({ length: total }).map((_, i) => (
        <div
          key={i}
          className={`h-2 flex-1 rounded-sm transition-all duration-300 ${
            i < filled ? color : 'bg-[#374151]'
          }`}
        />
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Mod tanımları (Spec Bölüm 11)
// ---------------------------------------------------------------------------

const MODES = [
  {
    value: 'stealth',
    label: 'Gizli',
    sublabel: 'Stealth',
    // Seçilince yeşil
    selectedBorder: 'border-green-500',
    selectedBg:     'bg-green-500/8',
    selectedRing:   'ring-1 ring-green-500/25',
    selectedTitle:  'text-green-300',
    badgeBg:        'bg-green-500/20',
    badgeText:      'text-green-400',
    icon: '🥷',
    tagline: 'Sessiz, yavaş, tespitsiz',
    desc: 'IDS/IPS sistemlerini tetiklememek için düşük hız ve rastgele gecikmeler kullanır. Pasif URL kaynakları tercih edilir. Hedef sistemde iz bırakmak istemediğinde kullan.',
    speed: {
      filled: 1,
      label: '5 req/s',
      color: 'bg-green-500',
    },
    stealth: {
      filled: 5,
      label: 'Maksimum',
      color: 'bg-green-500',
    },
    coverage: {
      filled: 2,
      label: 'Düşük',
      color: 'bg-green-500',
    },
    details: [
      { icon: '⏱', text: '1–3 sn rastgele gecikme' },
      { icon: '📋', text: 'Wordlist: top-1000 (küçük)' },
      { icon: '🌐', text: 'Sadece pasif URL kaynakları' },
      { icon: '🔒', text: 'Gerçekçi User-Agent' },
      { icon: '🧵', text: '5 thread' },
      { icon: '⏳', text: 'Timeout: 15 sn' },
    ],
    warning: null,
    riskLevel: 'Düşük',
    riskColor: 'text-green-400',
  },
  {
    value: 'normal',
    label: 'Normal',
    sublabel: 'Balanced',
    // Seçilince mavi
    selectedBorder: 'border-blue-500',
    selectedBg:     'bg-blue-500/8',
    selectedRing:   'ring-1 ring-blue-500/25',
    selectedTitle:  'text-blue-300',
    badgeBg:        'bg-blue-500/20',
    badgeText:      'text-blue-400',
    icon: '⚖️',
    tagline: 'Dengeli hız ve gizlilik',
    desc: 'Çoğu penetrasyon testi senaryosu için uygun. Hem pasif hem aktif URL kaynakları kullanılır. Makul hızda, makul iz bırakma.',
    speed: {
      filled: 3,
      label: '20 req/s',
      color: 'bg-blue-500',
    },
    stealth: {
      filled: 3,
      label: 'Orta',
      color: 'bg-blue-500',
    },
    coverage: {
      filled: 3,
      label: 'Orta',
      color: 'bg-blue-500',
    },
    details: [
      { icon: '⏱', text: '0.5–1 sn gecikme' },
      { icon: '📋', text: 'Wordlist: top-10000 (orta)' },
      { icon: '🌐', text: 'Pasif + aktif URL kaynakları' },
      { icon: '🤖', text: 'VulnScan User-Agent' },
      { icon: '🧵', text: '15 thread' },
      { icon: '⏳', text: 'Timeout: 10 sn' },
    ],
    warning: null,
    riskLevel: 'Orta',
    riskColor: 'text-yellow-400',
  },
  {
    value: 'aggressive',
    label: 'Agresif',
    sublabel: 'Aggressive',
    // Seçilince kırmızı
    selectedBorder: 'border-red-500',
    selectedBg:     'bg-red-500/8',
    selectedRing:   'ring-1 ring-red-500/20',
    selectedTitle:  'text-red-300',
    badgeBg:        'bg-red-500/20',
    badgeText:      'text-red-400',
    icon: '🔥',
    tagline: 'Maksimum kapsam, yüksek gürültü',
    desc: 'İzin verilen ortamlarda maksimum kapsam için kullan. Hız sınırı yoktur, tüm aktif kaynaklar paralel çalışır. IDS/WAF tetikler, log bırakır.',
    speed: {
      filled: 5,
      label: '100 req/s',
      color: 'bg-red-500',
    },
    stealth: {
      filled: 1,
      label: 'Minimum',
      color: 'bg-red-500',
    },
    coverage: {
      filled: 5,
      label: 'Maksimum',
      color: 'bg-red-500',
    },
    details: [
      { icon: '⏱', text: 'Gecikme yok' },
      { icon: '📋', text: 'Wordlist: SecLists big.txt' },
      { icon: '🌐', text: 'Tüm aktif + pasif kaynaklar' },
      { icon: '🤖', text: 'Agresif User-Agent' },
      { icon: '🧵', text: '50 thread' },
      { icon: '⏳', text: 'Timeout: 5 sn' },
    ],
    warning: '⚠ Yalnızca yetkili olduğun sistemlerde kullan. IDS alarmlarını tetikler.',
    riskLevel: 'Yüksek',
    riskColor: 'text-red-400',
  },
];

// ---------------------------------------------------------------------------
// Ana bileşen
// ---------------------------------------------------------------------------

export default function WizardStep2_Mode({ data, onChange, onNext, onBack }) {
  const selected = data.mode ?? 'normal';

  return (
    <div className="space-y-5">

      <div>
        <p className="text-xs text-gray-500">
          Tarama yoğunluğunu seç. Sonradan değiştiremezsin — tarama başladığında mod sabitleniyor.
        </p>
      </div>

      {/* Mod kartları */}
      <div className="grid grid-cols-1 gap-3">
        {MODES.map((mode) => {
          const isSelected = selected === mode.value;

          return (
            <button
              key={mode.value}
              type="button"
              onClick={() => onChange({ mode: mode.value })}
              className={`
                text-left p-4 rounded-xl border transition-all duration-200 w-full
                ${isSelected
                  ? `${mode.selectedBorder} ${mode.selectedBg} ${mode.selectedRing}`
                  : 'border-[#374151] bg-[#0a0e1a] hover:border-[#4b5563] hover:bg-[#111827]'}
              `}
            >
              <div className="flex items-start gap-4">
                {/* Radio */}
                <div className={`
                  mt-0.5 w-4 h-4 rounded-full border-2 flex items-center justify-center flex-shrink-0
                  ${isSelected ? mode.selectedBorder : 'border-[#4b5563]'}
                `}>
                  {isSelected && (
                    <div className={`w-2 h-2 rounded-full ${
                      mode.value === 'stealth' ? 'bg-green-400'
                      : mode.value === 'normal' ? 'bg-blue-400'
                      : 'bg-red-400'
                    }`} />
                  )}
                </div>

                {/* Gövde */}
                <div className="flex-1 min-w-0">

                  {/* Başlık satırı */}
                  <div className="flex items-center gap-2 mb-0.5">
                    <span className="text-xl">{mode.icon}</span>
                    <span className={`text-sm font-bold ${isSelected ? mode.selectedTitle : 'text-gray-300'}`}>
                      {mode.label}
                    </span>
                    <span className={`text-[10px] px-2 py-0.5 rounded font-medium font-mono
                      ${isSelected ? `${mode.badgeBg} ${mode.badgeText}` : 'bg-[#374151] text-gray-500'}`}>
                      {mode.sublabel}
                    </span>
                    <span className={`text-[10px] ml-auto font-medium ${isSelected ? mode.riskColor : 'text-gray-600'}`}>
                      {mode.riskLevel} tespit riski
                    </span>
                  </div>

                  {/* Tagline + açıklama */}
                  <p className={`text-[10px] font-medium mb-1 ${isSelected ? mode.badgeText : 'text-gray-500'}`}>
                    {mode.tagline}
                  </p>
                  <p className="text-xs text-gray-500 leading-relaxed mb-3">
                    {mode.desc}
                  </p>

                  {/* Göstergeler */}
                  <div className="grid grid-cols-3 gap-3 mb-3">
                    {[
                      { key: 'speed',    label: 'Hız',      data: mode.speed },
                      { key: 'stealth',  label: 'Gizlilik', data: mode.stealth },
                      { key: 'coverage', label: 'Kapsam',   data: mode.coverage },
                    ].map(({ key, label, data: bar }) => (
                      <div key={key}>
                        <div className="flex items-center justify-between mb-1">
                          <span className="text-[9px] text-gray-500">{label}</span>
                          <span className={`text-[9px] ${isSelected ? mode.badgeText : 'text-gray-600'}`}>
                            {bar.label}
                          </span>
                        </div>
                        <SegmentBar
                          filled={bar.filled}
                          color={isSelected ? bar.color : 'bg-[#4b5563]'}
                        />
                      </div>
                    ))}
                  </div>

                  {/* Detay listesi */}
                  <div className="grid grid-cols-2 gap-1">
                    {mode.details.map((d, i) => (
                      <div key={i} className="flex items-center gap-1.5">
                        <span className="text-[10px]">{d.icon}</span>
                        <span className={`text-[10px] ${isSelected ? 'text-gray-400' : 'text-gray-600'}`}>
                          {d.text}
                        </span>
                      </div>
                    ))}
                  </div>

                  {/* Uyarı (aggressive) */}
                  {mode.warning && isSelected && (
                    <div className="mt-2 text-[10px] text-red-400 bg-red-500/10 border border-red-500/20 rounded-lg px-3 py-2">
                      {mode.warning}
                    </div>
                  )}
                </div>
              </div>
            </button>
          );
        })}
      </div>

      {/* Navigasyon */}
      <div className="flex gap-3 pt-1">
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
          onClick={onNext}
          className="flex-1 py-3 rounded-xl text-sm font-semibold
            bg-blue-600 hover:bg-blue-500 text-white transition-colors
            flex items-center justify-center gap-2"
        >
          Devam Et
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2.5} className="w-4 h-4">
            <line x1="5" y1="12" x2="19" y2="12" />
            <polyline points="12 5 19 12 12 19" />
          </svg>
        </button>
      </div>
    </div>
  );
}
