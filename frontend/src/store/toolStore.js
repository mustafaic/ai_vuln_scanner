/**
 * Araç durumu yönetimi (Zustand).
 *
 * State:
 *  tools: { [name]: ToolStatus }  — backend'den gelen araç nesneleri
 *  loading: boolean               — araç durumu yüklenirken
 *  installing: Set<string>        — kurulumu devam eden araçlar
 *  error: string | null
 */

import { create } from 'zustand';
import { getToolStatus, installTool as apiInstallTool, installAllTools as apiInstallAll } from '../api/client';

const useToolStore = create((set, get) => ({
  // -----------------------------------------------------------------------
  // State
  // -----------------------------------------------------------------------
  tools: {},          // { subfinder: { name, installed, binary, category, ... }, ... }
  loading: false,
  installing: new Set(),
  error: null,

  // -----------------------------------------------------------------------
  // Selector yardımcıları
  // -----------------------------------------------------------------------
  get installedCount() {
    return Object.values(get().tools).filter((t) => t.installed).length;
  },
  get totalCount() {
    return Object.keys(get().tools).length;
  },
  get missingRequired() {
    return Object.values(get().tools)
      .filter((t) => t.required && !t.installed)
      .map((t) => t.name);
  },

  // -----------------------------------------------------------------------
  // Actions
  // -----------------------------------------------------------------------

  /**
   * Tüm araçların durumunu backend'den çeker.
   */
  fetchToolStatus: async () => {
    set({ loading: true, error: null });
    try {
      const data = await getToolStatus();
      // tools dizisini isme göre dict'e dönüştür
      const toolsMap = {};
      for (const tool of data.tools ?? []) {
        toolsMap[tool.name] = tool;
      }
      set({ tools: toolsMap, loading: false });
    } catch (err) {
      set({ error: err.message, loading: false });
    }
  },

  /**
   * Tek aracı kurar.
   * @param {string} name Araç adı (örn. 'subfinder')
   */
  installTool: async (name) => {
    set((s) => ({ installing: new Set([...s.installing, name]) }));
    try {
      await apiInstallTool(name);
      // Durum güncellemesi WS bildirimi ile gelir; burada araç listesini yenile
      await get().fetchToolStatus();
    } catch (err) {
      set((s) => {
        const next = new Set(s.installing);
        next.delete(name);
        return { installing: next, error: err.message };
      });
      return;
    }
    set((s) => {
      const next = new Set(s.installing);
      next.delete(name);
      return { installing: next };
    });
  },

  /**
   * Kurulu olmayan tüm araçları kurar.
   */
  installAllMissing: async () => {
    try {
      await apiInstallAll();
    } catch (err) {
      set({ error: err.message });
    }
  },

  /**
   * Tek bir araç durumunu dışarıdan günceller
   * (örn. WS bildirimi geldiğinde).
   */
  updateTool: (name, updates) =>
    set((s) => ({
      tools: {
        ...s.tools,
        [name]: { ...(s.tools[name] ?? {}), ...updates },
      },
    })),

  clearError: () => set({ error: null }),
}));

export default useToolStore;
