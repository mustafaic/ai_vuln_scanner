/**
 * ToolStatusBar — Araç durumu yatay bant.
 *
 * Araçların kurulum durumunu kategoriye göre gösterir.
 * Eksik araçlar vurgulanır, kurulum tetiklenebilir.
 */

import useToolStore from '../../store/toolStore';

const CATEGORY_LABEL = {
  recon: 'Keşif',
  discovery: 'URL Keşfi',
  testing: 'Test',
  analysis: 'Analiz',
  runtime: 'Runtime',
};

const CATEGORY_ORDER = ['runtime', 'recon', 'discovery', 'analysis', 'testing'];

export default function ToolStatusBar() {
  const tools = useToolStore((s) => s.tools);
  const installing = useToolStore((s) => s.installing);
  const installTool = useToolStore((s) => s.installTool);
  const installAllMissing = useToolStore((s) => s.installAllMissing);

  const toolList = Object.values(tools);
  if (toolList.length === 0) return null;

  const installedCount = toolList.filter((t) => t.installed).length;
  const allInstalled = installedCount === toolList.length;

  return (
    <div className="bg-[#111827] border-b border-[#374151] px-4 py-2">
      <div className="flex items-center gap-4 flex-wrap">
        {CATEGORY_ORDER.map((cat) => {
          const catTools = toolList.filter((t) => t.category === cat);
          if (!catTools.length) return null;
          const catInstalled = catTools.filter((t) => t.installed).length;
          const allCatInstalled = catInstalled === catTools.length;

          return (
            <div key={cat} className="flex items-center gap-1.5">
              <span className="text-[10px] text-gray-600">
                {CATEGORY_LABEL[cat] ?? cat}
              </span>
              <div className="flex items-center gap-0.5">
                {catTools.map((tool) => (
                  <div
                    key={tool.name}
                    title={`${tool.name} — ${tool.installed ? 'Kurulu' : installing.has(tool.name) ? 'Kuruluyor…' : 'Kurulu değil'}`}
                    className={`w-2 h-2 rounded-full cursor-pointer transition-colors ${
                      tool.installed
                        ? 'bg-green-500'
                        : installing.has(tool.name)
                        ? 'bg-yellow-400 animate-pulse-dot'
                        : tool.required
                        ? 'bg-red-500 hover:bg-red-400'
                        : 'bg-gray-600 hover:bg-gray-500'
                    }`}
                    onClick={() => {
                      if (!tool.installed && !installing.has(tool.name)) {
                        installTool(tool.name);
                      }
                    }}
                  />
                ))}
              </div>
              <span className={`text-[10px] ${allCatInstalled ? 'text-green-500' : 'text-gray-500'}`}>
                {catInstalled}/{catTools.length}
              </span>
            </div>
          );
        })}

        {/* Tümünü Kur butonu */}
        {!allInstalled && (
          <button
            onClick={installAllMissing}
            className="ml-auto text-[10px] text-yellow-400 hover:text-yellow-300 hover:underline"
          >
            Eksikleri kur
          </button>
        )}
      </div>
    </div>
  );
}
