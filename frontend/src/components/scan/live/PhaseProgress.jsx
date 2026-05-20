/**
 * PhaseProgress — Tarama faz ilerleme göstergesi.
 * recon → discovery → testing zinciri.
 * Aktif: spinner | Tamamlandı: ✓ | Bekliyor: gri ikon
 */

import useScanStore from '../../../store/scanStore';

const PHASES = [
  { id: 'recon',     label: 'Keşif',    sublabel: 'Recon',     icon: '🔍' },
  { id: 'discovery', label: 'URL Keşfi', sublabel: 'Discovery', icon: '🕷' },
  { id: 'testing',   label: 'Test',     sublabel: 'Testing',   icon: '⚡' },
];

const PHASE_ORDER = ['recon', 'discovery', 'testing'];

function PhaseNode({ phase, state, progress }) {
  const isActive = state === 'active';
  const isDone   = state === 'completed';

  return (
    <div className="flex flex-col items-center gap-1 flex-1 min-w-0">
      {/* Ikon dairesi */}
      <div className={`
        w-9 h-9 rounded-full flex items-center justify-center transition-all duration-300
        ${isDone
          ? 'bg-green-500/20 border-2 border-green-500'
          : isActive
          ? 'bg-blue-500/20 border-2 border-blue-500'
          : 'bg-[#1f2937] border-2 border-[#374151]'}
      `}>
        {isDone ? (
          <svg viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth={2.5}
            className="w-4 h-4 text-green-400">
            <polyline points="1,6 4,9 11,3" />
          </svg>
        ) : isActive ? (
          <div className="w-4 h-4 border-2 border-blue-400 border-t-transparent rounded-full animate-spin" />
        ) : (
          <span className="text-sm opacity-30">{phase.icon}</span>
        )}
      </div>

      {/* Etiket */}
      <span className={`text-[10px] font-medium text-center leading-tight ${
        isDone ? 'text-green-400' : isActive ? 'text-blue-400' : 'text-gray-600'
      }`}>
        {phase.label}
      </span>
      <span className="text-[9px] text-gray-600 font-mono">{phase.sublabel}</span>

      {/* Yüzde — sadece aktif fazda */}
      {isActive && progress != null && (
        <span className="text-[9px] text-blue-400 font-medium">{progress}%</span>
      )}
    </div>
  );
}

export default function PhaseProgress() {
  const currentPhase = useScanStore((s) => s.currentPhase);
  const progress     = useScanStore((s) => s.progress);
  const scanStatus   = useScanStore((s) => s.activeScan?.status);

  const currentIndex = PHASE_ORDER.indexOf(currentPhase ?? '');

  const getState = (id) => {
    const i = PHASE_ORDER.indexOf(id);
    if (scanStatus === 'completed') return 'completed';
    if (currentIndex === -1) return 'pending';
    if (i < currentIndex) return 'completed';
    if (i === currentIndex) return 'active';
    return 'pending';
  };

  return (
    <div className="space-y-2">
      {/* Faz zinciri */}
      <div className="flex items-start">
        {PHASES.map((phase, i) => (
          <div key={phase.id} className="flex items-center flex-1">
            <PhaseNode
              phase={phase}
              state={getState(phase.id)}
              progress={currentPhase === phase.id ? progress : null}
            />
            {i < PHASES.length - 1 && (
              <div className="flex-1 mx-1 h-0.5 bg-[#374151] rounded-full overflow-hidden mb-6">
                <div
                  className="h-full bg-green-500 transition-all duration-500 ease-out"
                  style={{ width: getState(PHASES[i + 1].id) !== 'pending' ? '100%' : '0%' }}
                />
              </div>
            )}
          </div>
        ))}
      </div>

      {/* Genel ilerleme çubuğu */}
      <div>
        <div className="flex justify-between mb-1">
          <span className="text-[10px] text-gray-600">Genel İlerleme</span>
          <span className="text-[10px] text-gray-500">{progress ?? 0}%</span>
        </div>
        <div className="h-1 bg-[#374151] rounded-full overflow-hidden">
          <div
            className="h-full bg-gradient-to-r from-blue-600 to-blue-400 transition-all duration-500 ease-out"
            style={{ width: `${progress ?? 0}%` }}
          />
        </div>
      </div>
    </div>
  );
}
