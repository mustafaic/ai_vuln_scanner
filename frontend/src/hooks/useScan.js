/**
 * useScan — Tarama CRUD ve kontrol işlemleri hook'u.
 *
 * Sağlar:
 *  - Tarama oluştur (createScan)
 *  - Taramayı başlat (startScan)
 *  - Duraklat / devam / durdur
 *  - scanStore'u güncelle
 *  - Hata bildirimleri uiStore üzerinden
 */

import { useCallback, useState } from 'react';
import {
  createScan as apiCreateScan,
  startScan as apiStartScan,
  pauseScan as apiPauseScan,
  resumeScan as apiResumeScan,
  stopScan as apiStopScan,
  getScan as apiGetScan,
  getSubdomains as apiGetSubdomains,
  getUrls as apiGetUrls,
} from '../api/client';
import useScanStore from '../store/scanStore';
import useUiStore from '../store/uiStore';

export function useScan() {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const setActiveScan = useScanStore((s) => s.setActiveScan);
  const setActiveScanId = useScanStore((s) => s.setActiveScanId);
  const updateActiveScan = useScanStore((s) => s.updateActiveScan);
  const clearScanData = useScanStore((s) => s.clearScanData);
  const addSubdomain = useScanStore((s) => s.addSubdomain);
  const addUrlBatch = useScanStore((s) => s.addUrlBatch);

  const addNotification = useUiStore((s) => s.addNotification);

  /**
   * Yeni tarama oluşturur ve başlatır.
   * @param {{ target, scope, mode, name?, config? }} data
   * @returns {Promise<string>} Oluşturulan tarama ID'si
   */
  const createAndStart = useCallback(
    async (data) => {
      setLoading(true);
      setError(null);
      try {
        // 1. Tarama oluştur
        const scan = await apiCreateScan(data);
        setActiveScanId(scan.id);
        setActiveScan(scan);
        clearScanData();

        // 2. Başlat
        await apiStartScan(scan.id);
        updateActiveScan({ status: 'running' });

        addNotification({
          title: 'Tarama Başlatıldı',
          body: `${data.target} için tarama başladı.`,
          type: 'success',
        });

        return scan.id;
      } catch (err) {
        setError(err.message);
        addNotification({ title: 'Tarama Başlatma Hatası', body: err.message, type: 'error' });
        throw err;
      } finally {
        setLoading(false);
      }
    },
    [setActiveScan, setActiveScanId, updateActiveScan, clearScanData, addNotification],
  );

  /** Var olan taramayı yükler (sayfa yenilemesi veya URL ile erişim). */
  const loadScan = useCallback(
    async (scanId) => {
      setLoading(true);
      try {
        const scan = await apiGetScan(scanId);
        setActiveScanId(scanId);
        setActiveScan(scan); // setActiveScan artık currentPhase'i de senkronize eder

        // Sayfa yenilemesi veya direkt URL ile açılışta mevcut verileri yükle
        // WS bağlantısı kurulana kadar UI'ın doğru durumu göstermesi için
        if (scan.subdomain_count > 0) {
          apiGetSubdomains(scanId, { limit: 200 })
            .then((data) => {
              if (data.items?.length) data.items.forEach((s) => addSubdomain(s));
            })
            .catch(() => {});
        }
        if (scan.url_count > 0) {
          apiGetUrls(scanId, { limit: 500 })
            .then((data) => {
              if (data.items?.length) addUrlBatch(data.items);
            })
            .catch(() => {});
        }

        return scan;
      } catch (err) {
        setError(err.message);
        throw err;
      } finally {
        setLoading(false);
      }
    },
    [setActiveScan, setActiveScanId, addSubdomain, addUrlBatch],
  );

  const pause = useCallback(
    async (scanId) => {
      try {
        await apiPauseScan(scanId);
        updateActiveScan({ status: 'paused' });
      } catch (err) {
        addNotification({ title: 'Duraklat Hatası', body: err.message, type: 'error' });
      }
    },
    [updateActiveScan, addNotification],
  );

  const resume = useCallback(
    async (scanId) => {
      try {
        await apiResumeScan(scanId);
        updateActiveScan({ status: 'running' });
      } catch (err) {
        addNotification({ title: 'Devam Hatası', body: err.message, type: 'error' });
      }
    },
    [updateActiveScan, addNotification],
  );

  const stop = useCallback(
    async (scanId) => {
      try {
        await apiStopScan(scanId);
        updateActiveScan({ status: 'stopped' });
      } catch (err) {
        addNotification({ title: 'Durdurma Hatası', body: err.message, type: 'error' });
      }
    },
    [updateActiveScan, addNotification],
  );

  return {
    loading,
    error,
    createAndStart,
    loadScan,
    pause,
    resume,
    stop,
  };
}

export default useScan;
