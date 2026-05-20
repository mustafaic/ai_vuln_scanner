/**
 * useScanWebSocket — WebSocket bağlantısı yönetim hook'u.
 *
 * Özellikler:
 *  - scanStore.connectWs() üzerinden bağlantı kurar
 *  - Sayfa kapatılınca / component unmount'unda bağlantıyı keser
 *  - Yeniden bağlanma (reconnect): 3 deneme, exponential backoff
 *    Denemeler: 1 sn → 2 sn → 4 sn
 *  - Bağlantı durumu: wsStatus ('disconnected'|'connecting'|'connected'|'error')
 *
 * Kullanım:
 *   const { wsStatus, sendMessage, disconnect } = useScanWebSocket(scanId);
 */

import { useEffect, useRef, useCallback } from 'react';
import useScanStore from '../store/scanStore';

const MAX_RETRIES = 3;
const BASE_DELAY_MS = 1000; // İlk yeniden deneme gecikmesi

/**
 * @param {string|null} scanId  — null verilirse bağlantı kurulmaz
 */
export function useScanWebSocket(scanId) {
  const connectWs = useScanStore((s) => s.connectWs);
  const disconnectWs = useScanStore((s) => s.disconnectWs);
  const sendWsMessage = useScanStore((s) => s.sendWsMessage);
  const wsStatus = useScanStore((s) => s.wsStatus);

  const retryCount = useRef(0);
  const retryTimer = useRef(null);
  const isUnmounted = useRef(false);

  // Yeniden bağlanma döngüsü
  const scheduleReconnect = useCallback(() => {
    if (isUnmounted.current) return;
    if (!scanId) return;
    if (retryCount.current >= MAX_RETRIES) return;

    const delay = BASE_DELAY_MS * 2 ** retryCount.current; // 1s, 2s, 4s
    retryCount.current += 1;

    retryTimer.current = setTimeout(() => {
      if (isUnmounted.current) return;
      connectWs(scanId);
    }, delay);
  }, [scanId, connectWs]);

  // wsStatus değişince yeniden bağlanmayı tetikle
  useEffect(() => {
    if (!scanId) return;

    if (wsStatus === 'disconnected' || wsStatus === 'error') {
      scheduleReconnect();
    } else if (wsStatus === 'connected') {
      // Başarılı bağlantıda retry sayacını sıfırla
      retryCount.current = 0;
    }
  }, [wsStatus, scanId, scheduleReconnect]);

  // scanId değişince (yeni tarama) bağlantıyı kur
  useEffect(() => {
    if (!scanId) return;

    isUnmounted.current = false;
    retryCount.current = 0;
    clearTimeout(retryTimer.current);
    connectWs(scanId);

    return () => {
      isUnmounted.current = true;
      clearTimeout(retryTimer.current);
      disconnectWs();
    };
  }, [scanId, connectWs, disconnectWs]);

  // Sayfa kapatılınca bağlantıyı kes
  useEffect(() => {
    const handleUnload = () => disconnectWs();
    window.addEventListener('beforeunload', handleUnload);
    return () => window.removeEventListener('beforeunload', handleUnload);
  }, [disconnectWs]);

  /** Mesaj gönderir. readyState OPEN değilse yutulur. */
  const sendMessage = useCallback(
    (msg) => sendWsMessage(msg),
    [sendWsMessage],
  );

  /** Bağlantıyı manuel olarak keser ve yeniden bağlanmayı iptal eder. */
  const disconnect = useCallback(() => {
    isUnmounted.current = true; // scheduleReconnect'i engelle
    clearTimeout(retryTimer.current);
    disconnectWs();
  }, [disconnectWs]);

  return {
    wsStatus,
    sendMessage,
    disconnect,
    isConnected: wsStatus === 'connected',
    isConnecting: wsStatus === 'connecting',
    retryCount: retryCount.current,
  };
}

export default useScanWebSocket;
