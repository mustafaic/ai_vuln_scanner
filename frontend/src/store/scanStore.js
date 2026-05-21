/**
 * Tarama durum yönetimi (Zustand).
 *
 * State:
 *  activeScanId   — izlenen taramanın UUID'si
 *  activeScan     — tarama nesnesi (DB'den, API ile güncellenir)
 *  scans          — liste sayfasındaki taramalar
 *  subdomains     — canlı subdomain listesi
 *  urls           — canlı URL listesi
 *  findings       — canlı bulgu listesi
 *  toolLog        — araç çıktı logu (son 500 satır)
 *  websocket      — aktif WebSocket nesnesi
 *  wsStatus       — 'disconnected' | 'connecting' | 'connected' | 'error'
 *  progress       — genel ilerleme 0-100
 *  currentPhase   — 'recon' | 'discovery' | 'testing' | null
 *  wafBypassNeeded — WAF bypass gerektiren durum bilgisi
 *
 * WS olayları Bölüm 6.1'e göre işlenir.
 */

import { create } from 'zustand';
import useUiStore from './uiStore';

// WS URL: Vite proxy (dev) ve doğrudan bağlantı (prod) her ikisinde çalışır
const _wsBase = () =>
  `${window.location.protocol === 'https:' ? 'wss' : 'ws'}://${window.location.host}`;

const useScanStore = create((set, get) => ({
  // -------------------------------------------------------------------------
  // State
  // -------------------------------------------------------------------------
  activeScanId: null,
  activeScan: null,
  scans: [],

  subdomains: [],  // SubdomainResponse[]
  urls: [],        // UrlResponse[]  — ilk 2000 tutulur (virtualized list için)
  findings: [],    // FindingResponse[]

  toolLog: [],     // { id, type, tool, message, time }[]

  websocket: null,
  wsStatus: 'disconnected',

  progress: 0,
  currentPhase: null,

  /** WAF bypass gerektiğinde dolu olur; null = beklenmiyor */
  wafBypassNeeded: null, // { url, waf_name, test_type, suggestions }

  // -------------------------------------------------------------------------
  // Temel setter'lar
  // -------------------------------------------------------------------------

  setActiveScanId: (id) => set({ activeScanId: id }),

  setActiveScan: (scan) =>
    set({
      activeScan: scan,
      // Sayfa yenilemesinde API'den gelen current_phase'i store'a aktar;
      // WS olayları bunu üzerine yazar ama bağlantı kurulana kadar UI doğru fazı gösterir.
      ...(scan?.current_phase ? { currentPhase: scan.current_phase } : {}),
    }),

  setScans: (scans) => set({ scans }),

  updateActiveScan: (patch) =>
    set((s) => ({
      activeScan: s.activeScan ? { ...s.activeScan, ...patch } : s.activeScan,
    })),

  clearScanData: () =>
    set({
      subdomains: [],
      urls: [],
      findings: [],
      toolLog: [],
      progress: 0,
      currentPhase: null,
      wafBypassNeeded: null,
    }),

  // -------------------------------------------------------------------------
  // Subdomain yönetimi
  // -------------------------------------------------------------------------

  addSubdomain: (sub) =>
    set((s) => {
      const idx = s.subdomains.findIndex((x) => x.id === sub.id);
      if (idx >= 0) {
        const next = [...s.subdomains];
        next[idx] = { ...next[idx], ...sub };
        return { subdomains: next };
      }
      return { subdomains: [sub, ...s.subdomains] };
    }),

  updateSubdomainAiScore: (id, patch) =>
    set((s) => ({
      subdomains: s.subdomains.map((x) =>
        x.id === id ? { ...x, ...patch } : x,
      ),
    })),

  // -------------------------------------------------------------------------
  // URL yönetimi
  // -------------------------------------------------------------------------

  addUrl: (url) =>
    set((s) => {
      if (s.urls.find((u) => u.id === url.id)) return {};
      const next = [url, ...s.urls];
      return { urls: next.slice(0, 2000) }; // bellek tavanı
    }),

  addUrlBatch: (urls) =>
    set((s) => {
      const existingIds = new Set(s.urls.map((u) => u.id));
      const fresh = urls.filter((u) => !existingIds.has(u.id));
      if (!fresh.length) return {};
      const next = [...fresh, ...s.urls];
      return { urls: next.slice(0, 2000) };
    }),

  updateUrl: (id, patch) =>
    set((s) => ({
      urls: s.urls.map((u) => (u.id === id ? { ...u, ...patch } : u)),
    })),

  // -------------------------------------------------------------------------
  // Bulgu yönetimi
  // -------------------------------------------------------------------------

  addFinding: (finding) =>
    set((s) => {
      if (s.findings.find((f) => f.id === finding.id)) return {};
      return { findings: [finding, ...s.findings] };
    }),

  updateFinding: (id, patch) =>
    set((s) => ({
      findings: s.findings.map((f) =>
        f.id === id ? { ...f, ...patch } : f,
      ),
    })),

  // -------------------------------------------------------------------------
  // Araç logu
  // -------------------------------------------------------------------------

  addLog: (entry) =>
    set((s) => {
      const log = [
        ...s.toolLog,
        { id: Date.now() + Math.random(), time: Date.now(), ...entry },
      ];
      return { toolLog: log.length > 500 ? log.slice(-500) : log };
    }),

  // -------------------------------------------------------------------------
  // WAF bypass
  // -------------------------------------------------------------------------

  setWafBypassNeeded: (data) => set({ wafBypassNeeded: data }),
  clearWafBypass: () => set({ wafBypassNeeded: null }),

  // -------------------------------------------------------------------------
  // WebSocket bağlantısı
  // -------------------------------------------------------------------------

  /**
   * Belirtilen scan_id için WebSocket bağlantısı kurar.
   * Önceki bağlantı varsa önce kapatılır.
   */
  connectWs: (scanId) => {
    const { websocket, disconnectWs } = get();
    if (websocket) disconnectWs();

    set({ wsStatus: 'connecting', activeScanId: scanId });
    const ws = new WebSocket(`${_wsBase()}/ws/${scanId}`);

    ws.onopen = () => {
      set({ websocket: ws, wsStatus: 'connected' });
    };

    ws.onclose = () => {
      set({ websocket: null, wsStatus: 'disconnected' });
    };

    ws.onerror = () => {
      set({ wsStatus: 'error' });
    };

    ws.onmessage = (evt) => {
      try {
        get()._handleWsMessage(JSON.parse(evt.data));
      } catch {
        /* geçersiz JSON */
      }
    };

    // Nesneyi hemen sakla (onopen gelmeden de sendWsMessage çalışsın diye
    // readyState kontrolü yeterli)
    set({ websocket: ws });
  },

  disconnectWs: () => {
    const { websocket } = get();
    if (websocket) {
      websocket.close();
      set({ websocket: null, wsStatus: 'disconnected' });
    }
  },

  /** WebSocket üzerinden mesaj gönderir. */
  sendWsMessage: (msg) => {
    const { websocket } = get();
    if (websocket?.readyState === WebSocket.OPEN) {
      websocket.send(JSON.stringify(msg));
    }
  },

  // -------------------------------------------------------------------------
  // WebSocket mesaj işleyici — Bölüm 6.1
  // -------------------------------------------------------------------------

  _handleWsMessage: (msg) => {
    const { event, data } = msg;
    const store = get();
    const ui = useUiStore.getState();

    switch (event) {
      // Faz olayları
      case 'phase_started':
        set({ currentPhase: msg.phase });
        store.addLog({ type: 'phase', tool: 'system', message: msg.message ?? `${msg.phase} başladı` });
        break;

      case 'phase_completed':
        store.addLog({ type: 'phase', tool: 'system', message: `${msg.phase} tamamlandı` });
        break;

      // İlerleme
      case 'progress':
        set({
          progress: msg.percent ?? 0,
          ...(msg.phase ? { currentPhase: msg.phase } : {}),
        });
        break;

      // Araç olayları
      case 'tool_started':
        store.addLog({ type: 'start', tool: msg.tool, message: `▶ ${msg.tool}: ${msg.target ?? ''}` });
        break;

      case 'tool_completed':
        store.addLog({ type: 'done', tool: msg.tool, message: `✓ ${msg.tool}: ${msg.found ?? 0} sonuç` });
        break;

      case 'tool_output':
        store.addLog({ type: 'output', tool: msg.tool, message: msg.line });
        break;

      case 'tool_error':
        store.addLog({ type: 'error', tool: msg.tool, message: `✗ ${msg.tool}: ${msg.error}` });
        break;

      // Subdomain olayları
      case 'subdomain_found':
        if (data) store.addSubdomain(data);
        break;

      case 'subdomain_ai_scored':
        if (data) {
          store.updateSubdomainAiScore(data.id, {
            ai_score: data.score,
            ai_analysis: data.analysis,
            ai_tags: data.tags,
            priority: data.priority,
          });
        }
        break;

      // URL olayları
      case 'url_found':
        if (data) store.addUrl(data);
        break;

      case 'url_batch':
        if (msg.data?.length) store.addUrlBatch(msg.data);
        break;

      case 'url_ai_analyzed':
        if (data) {
          store.updateUrl(data.id, {
            risk_score: data.risk_score,
            vuln_categories: data.categories,
            ai_analysis: data.analysis,
          });
        }
        break;

      // Test olayları
      case 'test_started':
        store.addLog({ type: 'start', tool: 'testing', message: `Test başladı: URL #${msg.url_id} — ${msg.test_type}` });
        break;

      case 'finding_found':
      case 'new_finding':
        if (data) store.addFinding(data);
        break;

      case 'waf_detected':
        store.addLog({
          type: 'warn',
          tool: 'wafw00f',
          message: `⚠ WAF: ${data?.waf} — ${data?.url}`,
        });
        break;

      case 'waf_suggestions':
        // waf_bypass_needed (testing.py'den gelen özel event)
        break;

      case 'waf_bypass_needed':
        store.setWafBypassNeeded({
          url: msg.url,
          url_id: msg.url_id,
          waf_name: msg.waf_name,
          test_type: msg.test_type,
          suggestions: msg.suggestions ?? {},
        });
        ui.openModal('waf_bypass');
        break;

      // Tarama durum olayları
      case 'scan_paused':
        store.updateActiveScan({ status: 'paused' });
        break;

      case 'scan_resumed':
        store.updateActiveScan({ status: 'running' });
        break;

      case 'scan_stopped':
        store.updateActiveScan({ status: 'stopped' });
        store.addLog({ type: 'info', tool: 'system', message: 'Tarama durduruldu.' });
        break;

      case 'scan_completed':
        store.updateActiveScan({ status: 'completed', progress: 100 });
        store.addLog({ type: 'done', tool: 'system', message: 'Tarama tamamlandı! 🎉' });
        set({ progress: 100 });
        ui.addNotification({
          title: 'Tarama Tamamlandı',
          body: `${msg.stats?.total_findings ?? 0} bulgu, ${msg.stats?.total_urls ?? 0} URL`,
          type: 'success',
          duration: 8000,
        });
        break;

      case 'scan_error':
        store.updateActiveScan({ status: 'failed' });
        store.addLog({ type: 'error', tool: 'system', message: msg.message });
        ui.addNotification({ title: 'Tarama Hatası', body: msg.message, type: 'error', duration: 0 });
        break;

      // Bildirimler
      case 'notification':
        ui.addNotification({ title: msg.title, body: msg.body, type: 'info' });
        break;

      // Bağlantı onayı
      case 'connected':
        set({ wsStatus: 'connected' });
        break;

      // Acknowledgment — no-op
      case 'ack':
        break;

      case 'error':
        store.addLog({ type: 'error', tool: 'system', message: `WS hata: ${msg.message}` });
        break;

      default:
        // Bilinmeyen event — sessizce geç
        break;
    }
  },
}));

export default useScanStore;
