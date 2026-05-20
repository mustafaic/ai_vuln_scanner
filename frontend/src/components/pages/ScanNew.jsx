/**
 * ScanNew — Yeni tarama sihirbazı (3 adım).
 *
 * Adım 1 → WizardStep1_Target  (hedef, kapsam, isim)
 * Adım 2 → WizardStep2_Mode    (tarama modu)
 * Adım 3 → WizardStep3_Tools   (araç seçimi + özet + başlat)
 *
 * Son adımda onStart() → createScan() + startScan() → /scan/:id
 */

import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import WizardStep1_Target from '../scan/wizard/WizardStep1_Target';
import WizardStep2_Mode   from '../scan/wizard/WizardStep2_Mode';
import WizardStep3_Tools  from '../scan/wizard/WizardStep3_Tools';
import useScan from '../../hooks/useScan';

// ---------------------------------------------------------------------------
// Adım tanımları
// ---------------------------------------------------------------------------

const STEPS = [
  {
    num: 1,
    label: 'Hedef',
    sublabel: 'Domain / URL / IP ve kapsam',
  },
  {
    num: 2,
    label: 'Mod',
    sublabel: 'Tarama yoğunluğu',
  },
  {
    num: 3,
    label: 'Araçlar',
    sublabel: 'Araç seçimi ve başlat',
  },
];

// ---------------------------------------------------------------------------
// Adım göstergesi
// ---------------------------------------------------------------------------

function StepIndicator({ currentStep }) {
  return (
    <nav aria-label="Sihirbaz adımları" className="flex items-start gap-0 mb-8">
      {STEPS.map((step, i) => {
        const isDone   = i < currentStep;
        const isActive = i === currentStep;

        return (
          <div key={step.num} className="flex items-start flex-1">
            {/* Düğüm */}
            <div className="flex flex-col items-center gap-1.5 flex-shrink-0 z-10">
              <div
                className={`
                  w-9 h-9 rounded-full flex items-center justify-center
                  text-sm font-bold transition-all duration-300
                  ${isDone
                    ? 'bg-green-500 text-white shadow-lg shadow-green-500/20'
                    : isActive
                    ? 'bg-blue-600 text-white ring-4 ring-blue-500/25 shadow-lg shadow-blue-500/20'
                    : 'bg-[#1f2937] text-gray-600 border border-[#374151]'}
                `}
              >
                {isDone ? (
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={3} className="w-4 h-4">
                    <polyline points="20 6 9 17 4 12" />
                  </svg>
                ) : (
                  step.num
                )}
              </div>

              {/* Etiket */}
              <div className="text-center">
                <p className={`text-[11px] font-semibold leading-tight ${
                  isDone ? 'text-green-400' : isActive ? 'text-white' : 'text-gray-600'
                }`}>
                  {step.label}
                </p>
                <p className="text-[9px] text-gray-600 leading-tight hidden sm:block mt-0.5">
                  {step.sublabel}
                </p>
              </div>
            </div>

            {/* Bağlantı çizgisi */}
            {i < STEPS.length - 1 && (
              <div className="flex-1 mx-2 mt-4 h-0.5 bg-[#374151] rounded-full overflow-hidden">
                <div
                  className="h-full bg-green-500 transition-all duration-500 ease-out"
                  style={{ width: isDone ? '100%' : '0%' }}
                />
              </div>
            )}
          </div>
        );
      })}
    </nav>
  );
}

// ---------------------------------------------------------------------------
// Varsayılan form değerleri
// ---------------------------------------------------------------------------

const DEFAULT_DATA = {
  target: '',
  scope: 'subdomains',   // Spec: subdomain kapsam tercih edilir
  name: '',
  mode: 'normal',
  tools: null,           // null = tüm araçlar seçili
  _nameManuallySet: false,
};

// ---------------------------------------------------------------------------
// Ana bileşen
// ---------------------------------------------------------------------------

export default function ScanNew() {
  const [step, setStep]   = useState(0);
  const [data, setData]   = useState(DEFAULT_DATA);

  const navigate = useNavigate();
  const { createAndStart, loading } = useScan();

  /** Kısmi güncelleme — wizard adımları bunu kullanır. */
  const patch = (updates) => setData((prev) => ({ ...prev, ...updates }));

  const goNext = () => setStep((s) => Math.min(s + 1, STEPS.length - 1));
  const goBack = () => setStep((s) => Math.max(s - 1, 0));

  const handleStart = async () => {
    try {
      const payload = {
        target: data.target.trim(),
        scope:  data.scope,
        mode:   data.mode,
        name:   data.name?.trim() || undefined,
        config: data.tools
          ? { selected_tools: data.tools }
          : undefined,
      };
      const scanId = await createAndStart(payload);
      navigate(`/scan/${scanId}`);
    } catch {
      // useScan hook zaten bildirim gösteriyor
    }
  };

  // Adım içeriği — render prop olmadan basit koşullu
  const renderStep = () => {
    switch (step) {
      case 0:
        return (
          <WizardStep1_Target
            data={data}
            onChange={patch}
            onNext={goNext}
          />
        );
      case 1:
        return (
          <WizardStep2_Mode
            data={data}
            onChange={patch}
            onNext={goNext}
            onBack={goBack}
          />
        );
      case 2:
        return (
          <WizardStep3_Tools
            data={data}
            onChange={patch}
            onStart={handleStart}
            onBack={goBack}
            loading={loading}
          />
        );
      default:
        return null;
    }
  };

  return (
    <div className="min-h-full bg-[#0a0e1a] py-8 px-4">
      <div className="max-w-2xl mx-auto">

        {/* Sayfa başlığı */}
        <div className="mb-7">
          <div className="flex items-center gap-2 mb-1">
            <button
              onClick={() => navigate('/')}
              className="text-gray-600 hover:text-gray-400 transition-colors"
              aria-label="Ana sayfaya dön"
            >
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} className="w-4 h-4">
                <line x1="19" y1="12" x2="5" y2="12" />
                <polyline points="12 19 5 12 12 5" />
              </svg>
            </button>
            <span className="text-xs text-gray-600">Ana Sayfa</span>
          </div>
          <h1 className="text-xl font-bold text-white">Yeni Tarama</h1>
          <p className="text-xs text-gray-500 mt-1">
            AI destekli zafiyet taraması — 3 adımda yapılandır ve başlat
          </p>
        </div>

        {/* Adım göstergesi */}
        <StepIndicator currentStep={step} />

        {/* Adım içeriği kartı */}
        <div
          key={step}               /* key değişince React yeni mount yapar → slide animasyonu için */
          className="bg-[#111827] border border-[#374151] rounded-2xl p-6 animate-slide-in"
        >
          {/* Adım başlığı */}
          <div className="mb-6 pb-4 border-b border-[#374151]">
            <div className="flex items-center gap-2">
              <span className="text-[10px] text-gray-600 font-mono">
                ADIM {step + 1} / {STEPS.length}
              </span>
              <span className="text-[10px] text-[#374151]">—</span>
              <span className="text-[10px] text-gray-500">{STEPS[step].sublabel}</span>
            </div>
            <h2 className="text-base font-bold text-white mt-1">
              {STEPS[step].label}
            </h2>
          </div>

          {renderStep()}
        </div>

        {/* Alt bilgi */}
        <p className="text-[10px] text-gray-700 text-center mt-4">
          Tarama başladıktan sonra istediğin zaman duraklat veya durdurabilirsin.
        </p>
      </div>
    </div>
  );
}
