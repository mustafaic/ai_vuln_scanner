/**
 * API istemcisi — tüm backend çağrıları buradan yapılır.
 *
 * Üretim:  backend ile aynı origin (port 8080) → baseURL = ''
 * Geliştirme: Vite proxy /api → localhost:8080 → baseURL = ''
 *
 * Streaming chat için fetch tabanlı aiChatStream() ayrı sağlanır;
 * diğer tüm çağrılar axios üzerinden akar.
 */

import axios from 'axios';

// Vite proxy aktifken relative path yeterli; override için .env VITE_API_URL
const API_BASE = import.meta.env.VITE_API_URL ?? '';

// ---------------------------------------------------------------------------
// Axios instance
// ---------------------------------------------------------------------------

export const api = axios.create({
  baseURL: API_BASE,
  timeout: 30_000,
  headers: { 'Content-Type': 'application/json' },
});

// Hata mesajını normalize et
api.interceptors.response.use(
  (res) => res,
  (err) => {
    const detail =
      err.response?.data?.detail ??
      err.response?.data?.message ??
      err.message ??
      'Bilinmeyen hata';
    const error = new Error(detail);
    error.status = err.response?.status;
    error.data = err.response?.data;
    return Promise.reject(error);
  },
);

// ---------------------------------------------------------------------------
// Sağlık kontrolü
// ---------------------------------------------------------------------------

export const getHealth = () =>
  api.get('/api/health').then((r) => r.data);

// ===========================================================================
// Tarama (Scans)
// ===========================================================================

/**
 * Yeni tarama oluşturur.
 * @param {{ target, scope, mode, name?, config? }} data
 */
export const createScan = (data) =>
  api.post('/api/scans', data).then((r) => r.data);

/**
 * Taramaları listeler.
 * @param {{ page?, limit?, status? }} params
 */
export const listScans = (params = {}) =>
  api.get('/api/scans', { params }).then((r) => r.data);

/** Tek tarama detayı (istatistikler dahil). */
export const getScan = (scanId) =>
  api.get(`/api/scans/${scanId}`).then((r) => r.data);

/** Taramayı siler. */
export const deleteScan = (scanId) =>
  api.delete(`/api/scans/${scanId}`).then((r) => r.data);

/** Taramayı arka planda başlatır. */
export const startScan = (scanId) =>
  api.post(`/api/scans/${scanId}/start`).then((r) => r.data);

/** Taramayı duraklatır. */
export const pauseScan = (scanId) =>
  api.post(`/api/scans/${scanId}/pause`).then((r) => r.data);

/** Duraklatılmış taramayı devam ettirir. */
export const resumeScan = (scanId) =>
  api.post(`/api/scans/${scanId}/resume`).then((r) => r.data);

/** Taramayı durdurur. */
export const stopScan = (scanId) =>
  api.post(`/api/scans/${scanId}/stop`).then((r) => r.data);

// ===========================================================================
// Subdomain
// ===========================================================================

/**
 * Subdomain listesi.
 * @param {string} scanId
 * @param {{ page?, limit?, sort_by?, sort_dir?, min_score?, has_waf?, is_alive? }} params
 */
export const getSubdomains = (scanId, params = {}) =>
  api.get(`/api/scans/${scanId}/subdomains`, { params }).then((r) => r.data);

/**
 * Subdomain seçimini toplu günceller.
 * @param {string} scanId
 * @param {{ subdomain_ids?: number[], select_all?: boolean, selected?: boolean }} data
 */
export const updateSubdomainSelection = (scanId, data) =>
  api
    .patch(`/api/scans/${scanId}/subdomains/select`, data)
    .then((r) => r.data);

// ===========================================================================
// URL
// ===========================================================================

/**
 * URL listesi.
 * @param {string} scanId
 * @param {{ page?, limit?, category?, keyword?, min_score?, source?, is_tested? }} params
 */
export const getUrls = (scanId, params = {}) =>
  api.get(`/api/scans/${scanId}/urls`, { params }).then((r) => r.data);

/**
 * Tek URL güncelleme (is_interesting, is_tested, vb.).
 * @param {number} urlId
 * @param {{ is_interesting?, is_tested?, risk_score? }} data
 */
export const updateUrl = (urlId, data) =>
  api.patch(`/api/urls/${urlId}`, data).then((r) => r.data);

// ===========================================================================
// Test fazı
// ===========================================================================

/**
 * Test fazını başlatır.
 * @param {string} scanId
 * @param {{ url_ids: number[], test_types: string[] }} data
 */
export const startTest = (scanId, data) =>
  api.post(`/api/scans/${scanId}/test/start`, data).then((r) => r.data);

/**
 * WAF bypass tekniği uygular.
 * @param {string} scanId
 * @param {{ url_id: number, technique: string }} data
 */
export const applyWafBypass = (scanId, data) =>
  api
    .post(`/api/scans/${scanId}/test/waf-bypass`, data)
    .then((r) => r.data);

/**
 * Bulgular listesi.
 * @param {string} scanId
 * @param {{ page?, limit?, severity?, vuln_type?, status? }} params
 */
export const getFindings = (scanId, params = {}) =>
  api.get(`/api/scans/${scanId}/findings`, { params }).then((r) => r.data);

/** Bulgu güncelle (status, notes, vb.). */
export const updateFinding = (findingId, data) =>
  api.patch(`/api/findings/${findingId}`, data).then((r) => r.data);

// ===========================================================================
// Araçlar (Tools)
// ===========================================================================

/** Tüm araçların kurulum durumunu döndürür. */
export const getToolStatus = () =>
  api.get('/api/tools/status').then((r) => r.data);

/** Tek araç kurar (arka planda). */
export const installTool = (name) =>
  api.post(`/api/tools/${name}/install`).then((r) => r.data);

/** Eksik tüm araçları kurar (arka planda). */
export const installAllTools = () =>
  api.post('/api/tools/install-all').then((r) => r.data);

// ===========================================================================
// Raporlar
// ===========================================================================

/** Tüm raporları listeler. */
export const getReports = (params = {}) =>
  api.get('/api/reports', { params }).then((r) => r.data);

/** Belirli taramanın raporunu döndürür. */
export const getReport = (scanId) =>
  api.get(`/api/reports/${scanId}`).then((r) => r.data);

// ===========================================================================
// AI
// ===========================================================================

/**
 * AI sohbeti — tek seferlik (tam yanıt).
 * Streaming için aiChatStream() kullanın.
 */
export const aiChat = (data) =>
  api.post('/api/ai/chat', data).then((r) => r.data);

/**
 * AI sohbeti — SSE token akışı.
 *
 * @param {{ message: string, context?: object }} data
 * @param {(token: string) => void} onToken - Her token parçasında çağrılır
 * @param {() => void} [onDone] - Akış bitince çağrılır
 * @param {(err: string) => void} [onError] - Hata durumunda çağrılır
 * @returns {() => void} İptal fonksiyonu (AbortController)
 */
export const aiChatStream = (data, onToken, onDone, onError) => {
  const controller = new AbortController();

  (async () => {
    try {
      const res = await fetch(`${API_BASE}/api/ai/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data),
        signal: controller.signal,
      });

      if (!res.ok) {
        const text = await res.text();
        onError?.(text);
        return;
      }

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop(); // Tamamlanmamış satırı buffer'da tut

        for (const line of lines) {
          if (!line.startsWith('data: ')) continue;
          const payload = line.slice(6).trim();
          if (payload === '[DONE]') {
            onDone?.();
            return;
          }
          try {
            const parsed = JSON.parse(payload);
            if (parsed.token != null) onToken(parsed.token);
            if (parsed.error) onError?.(parsed.error);
          } catch {
            // Malformed line — sessizce geç
          }
        }
      }
      onDone?.();
    } catch (err) {
      if (err.name !== 'AbortError') onError?.(err.message);
    }
  })();

  return () => controller.abort();
};

/** AI ile URL analizi (DB'yi günceller). */
export const aiAnalyzeUrl = (urlId) =>
  api.post('/api/ai/analyze-url', { url_id: urlId }).then((r) => r.data);

/**
 * Payload üretimi.
 * @param {{ url_id: number, vuln_type: string, waf_name?: string }} data
 */
export const aiGeneratePayloads = (data) =>
  api.post('/api/ai/generate-payloads', data).then((r) => r.data);

/** Bulgu AI analizi (DB'yi günceller). */
export const aiAnalyzeFinding = (findingId) =>
  api
    .post('/api/ai/analyze-finding', { finding_id: findingId })
    .then((r) => r.data);

/** PoC üretimi. */
export const aiGeneratePoc = (findingId) =>
  api
    .post('/api/ai/generate-poc', { finding_id: findingId })
    .then((r) => r.data);
