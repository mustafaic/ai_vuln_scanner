/**
 * useAI — AI analiz ve sohbet hook'u.
 *
 * Sağlar:
 *  - Streaming sohbet (aiChatStream)
 *  - URL analizi (aiAnalyzeUrl)
 *  - Payload üretimi (aiGeneratePayloads)
 *  - Bulgu analizi (aiAnalyzeFinding)
 *  - PoC üretimi (aiGeneratePoc)
 */

import { useState, useCallback, useRef } from 'react';
import {
  aiChatStream,
  aiAnalyzeUrl as apiAnalyzeUrl,
  aiGeneratePayloads as apiGeneratePayloads,
  aiAnalyzeFinding as apiAnalyzeFinding,
  aiGeneratePoc as apiGeneratePoc,
} from '../api/client';

export function useAI() {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const cancelRef = useRef(null);

  const clearError = useCallback(() => setError(null), []);

  /**
   * Streaming AI sohbet.
   * @param {string} message
   * @param {object} context
   * @param {{ onToken, onDone, onError }} callbacks
   * @returns {() => void} İptal fonksiyonu
   */
  const chat = useCallback((message, context, { onToken, onDone, onError } = {}) => {
    const cancel = aiChatStream(
      { message, context },
      onToken,
      () => {
        cancelRef.current = null;
        onDone?.();
      },
      (err) => {
        cancelRef.current = null;
        onError?.(err);
      },
    );
    cancelRef.current = cancel;
    return cancel;
  }, []);

  const cancelChat = useCallback(() => {
    cancelRef.current?.();
    cancelRef.current = null;
  }, []);

  /**
   * URL AI analizi — DB'yi günceller, güncellenmiş URL nesnesini döner.
   */
  const analyzeUrl = useCallback(async (urlId) => {
    setLoading(true);
    setError(null);
    try {
      return await apiAnalyzeUrl(urlId);
    } catch (err) {
      setError(err.message);
      throw err;
    } finally {
      setLoading(false);
    }
  }, []);

  /**
   * Payload üretimi.
   * @param {{ url_id: number, vuln_type: string, waf_name?: string }} params
   */
  const generatePayloads = useCallback(async (params) => {
    setLoading(true);
    setError(null);
    try {
      return await apiGeneratePayloads(params);
    } catch (err) {
      setError(err.message);
      throw err;
    } finally {
      setLoading(false);
    }
  }, []);

  /**
   * Bulgu analizi — DB'yi günceller, güncellenmiş bulgu nesnesini döner.
   */
  const analyzeFinding = useCallback(async (findingId) => {
    setLoading(true);
    setError(null);
    try {
      return await apiAnalyzeFinding(findingId);
    } catch (err) {
      setError(err.message);
      throw err;
    } finally {
      setLoading(false);
    }
  }, []);

  /**
   * PoC üretimi.
   */
  const generatePoc = useCallback(async (findingId) => {
    setLoading(true);
    setError(null);
    try {
      return await apiGeneratePoc(findingId);
    } catch (err) {
      setError(err.message);
      throw err;
    } finally {
      setLoading(false);
    }
  }, []);

  return {
    loading,
    error,
    clearError,
    chat,
    cancelChat,
    analyzeUrl,
    generatePayloads,
    analyzeFinding,
    generatePoc,
  };
}

export default useAI;
