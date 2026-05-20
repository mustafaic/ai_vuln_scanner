/**
 * UI durum yönetimi (Zustand).
 *
 * Yönetilen state:
 *  - Sidebar açık/kapalı
 *  - AI panel açık/kapalı
 *  - Aktif modal
 *  - Bildirimler (toast kuyruğu)
 */

import { create } from 'zustand';

let _notifId = 0;

const useUiStore = create((set, get) => ({
  // -----------------------------------------------------------------------
  // Layout
  // -----------------------------------------------------------------------
  sidebarOpen: true,
  aiPanelOpen: true,

  toggleSidebar: () =>
    set((s) => ({ sidebarOpen: !s.sidebarOpen })),

  setSidebarOpen: (open) => set({ sidebarOpen: open }),

  toggleAiPanel: () =>
    set((s) => ({ aiPanelOpen: !s.aiPanelOpen })),

  setAiPanelOpen: (open) => set({ aiPanelOpen: open }),

  // -----------------------------------------------------------------------
  // Modal
  // -----------------------------------------------------------------------
  /** Aktif modal ID'si ve opsiyonel veri payload'u. */
  activeModal: null, // { id: string, data?: any }

  openModal: (id, data = null) =>
    set({ activeModal: { id, data } }),

  closeModal: () => set({ activeModal: null }),

  // -----------------------------------------------------------------------
  // Bildirimler (toast kuyruğu)
  // -----------------------------------------------------------------------
  /**
   * Bildirim nesnesi:
   *  { id, title, body, type: 'info'|'success'|'warning'|'error', createdAt }
   */
  notifications: [],

  /**
   * Yeni bildirim ekler.
   * @param {{ title: string, body?: string, type?: string, duration?: number }} notif
   * @returns {number} Bildirimin ID'si (kaldırmak için kullanılır)
   */
  addNotification: (notif) => {
    const id = ++_notifId;
    const entry = {
      id,
      title: notif.title ?? '',
      body: notif.body ?? '',
      type: notif.type ?? 'info',
      createdAt: Date.now(),
    };
    set((s) => ({ notifications: [...s.notifications, entry] }));

    // Otomatik kaldır (varsayılan 5 sn, 0 = kalıcı)
    const duration = notif.duration ?? 5000;
    if (duration > 0) {
      setTimeout(() => get().removeNotification(id), duration);
    }
    return id;
  },

  removeNotification: (id) =>
    set((s) => ({
      notifications: s.notifications.filter((n) => n.id !== id),
    })),

  clearNotifications: () => set({ notifications: [] }),

  // -----------------------------------------------------------------------
  // AI Chat Bağlamı
  // -----------------------------------------------------------------------
  /** Aktif chat context — seçili URL veya bulgu enjekte edilir. */
  chatContext: null, // { type: 'url'|'finding', data: object }

  setChatContext: (ctx) => set({ chatContext: ctx }),
  clearChatContext: () => set({ chatContext: null }),
}));

export default useUiStore;
