/**
 * AiChatPanel — Sağ panel AI sohbet arayüzü.
 *
 * Özellikler:
 *  - Serbest sohbet: aiChatStream() SSE akışı
 *  - Aktif tarama bağlamı otomatik eklenir
 *  - Seçili URL veya bulgu bağlam olarak enjekte edilir (uiStore.chatContext)
 *  - Streaming token render
 *  - Mesaj geçmişi (oturum boyunca)
 */

import { useState, useRef, useEffect, useCallback } from 'react';
import { aiChatStream } from '../../api/client';
import useScanStore from '../../store/scanStore';
import useUiStore from '../../store/uiStore';

const WELCOME =
  'Merhaba! Ben VulnScan AI asistanınım. Aktif tarama hakkında sorularınızı yanıtlayabilir, payload önerileri sunabilir veya bulgular hakkında analiz yapabilirim.';

export default function AiChatPanel() {
  const [messages, setMessages] = useState([
    { role: 'assistant', content: WELCOME, id: 0 },
  ]);
  const [input, setInput]       = useState('');
  const [streaming, setStreaming] = useState(false);
  const cancelRef  = useRef(null);
  const bottomRef  = useRef(null);
  const inputRef   = useRef(null);
  const msgId      = useRef(1);

  const activeScan   = useScanStore((s) => s.activeScan);
  const findings     = useScanStore((s) => s.findings);
  const subdomains   = useScanStore((s) => s.subdomains);
  const urls         = useScanStore((s) => s.urls);
  const chatContext  = useUiStore((s) => s.chatContext);
  const clearChatContext = useUiStore((s) => s.clearChatContext);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  // Yeni chatContext gelince otomatik mesaj gönder
  useEffect(() => {
    if (!chatContext) return;
    const label = chatContext.type === 'url'
      ? `URL analiz et: ${chatContext.data?.url}`
      : `Bulgu analiz et: ${chatContext.data?.title ?? chatContext.data?.vuln_type}`;
    setInput(label);
    inputRef.current?.focus();
  }, [chatContext]);

  const buildContext = useCallback(() => {
    const base = activeScan ? {
      scan_id: activeScan.id,
      target: activeScan.target,
      tech_stack: subdomains
        .flatMap((s) => {
          const raw = s.tech_stack;
          if (Array.isArray(raw)) return raw;
          try { return JSON.parse(raw ?? '[]'); } catch { return []; }
        })
        .filter((v, i, a) => a.indexOf(v) === i)
        .slice(0, 10),
      current_phase: activeScan.current_phase,
      subdomain_count: subdomains.length,
      url_count: urls.length,
      finding_count: findings.length,
    } : {};

    if (chatContext?.type === 'url' && chatContext.data) {
      base.selected_url = {
        url: chatContext.data.url,
        risk_score: chatContext.data.risk_score,
        vuln_categories: chatContext.data.vuln_categories,
        keywords: chatContext.data.keywords,
      };
    } else if (chatContext?.type === 'finding' && chatContext.data) {
      base.selected_finding = {
        vuln_type: chatContext.data.vuln_type,
        severity: chatContext.data.severity,
        payload: chatContext.data.payload,
        ai_confidence: chatContext.data.ai_confidence,
        ai_analysis: chatContext.data.ai_analysis,
      };
    }

    return base;
  }, [activeScan, subdomains, urls, findings, chatContext]);

  const sendMessage = useCallback(() => {
    const text = input.trim();
    if (!text || streaming) return;

    const userMsg     = { role: 'user', content: text, id: ++msgId.current };
    const assistantId = ++msgId.current;

    setMessages((prev) => [
      ...prev,
      userMsg,
      { role: 'assistant', content: '', id: assistantId, loading: true },
    ]);
    setInput('');
    setStreaming(true);
    clearChatContext();

    let accumulated = '';

    cancelRef.current = aiChatStream(
      { message: text, context: buildContext() },
      (token) => {
        accumulated += token;
        setMessages((prev) =>
          prev.map((m) =>
            m.id === assistantId ? { ...m, content: accumulated, loading: false } : m
          )
        );
      },
      () => {
        setStreaming(false);
        cancelRef.current = null;
        setMessages((prev) =>
          prev.map((m) =>
            m.id === assistantId ? { ...m, loading: false } : m
          )
        );
      },
      (err) => {
        setStreaming(false);
        cancelRef.current = null;
        setMessages((prev) =>
          prev.map((m) =>
            m.id === assistantId
              ? { ...m, content: `Hata: ${err}`, loading: false, error: true }
              : m
          )
        );
      },
    );
  }, [input, streaming, buildContext, clearChatContext]);

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  };

  const cancelStream = () => {
    cancelRef.current?.();
    cancelRef.current = null;
    setStreaming(false);
  };

  const clearHistory = () => {
    setMessages([{ role: 'assistant', content: WELCOME, id: 0 }]);
  };

  return (
    <div className="flex flex-col h-full bg-[#111827]">
      {/* Başlık */}
      <div className="flex items-center justify-between px-3 py-2 border-b border-[#374151] flex-shrink-0">
        <div className="flex items-center gap-2">
          <div className="w-2 h-2 rounded-full bg-blue-400 animate-pulse-dot" />
          <span className="text-xs font-semibold text-gray-300 uppercase tracking-wider">
            AI Asistan
          </span>
        </div>
        <button
          onClick={clearHistory}
          className="text-[10px] text-gray-600 hover:text-gray-400 transition-colors"
          title="Geçmişi temizle"
        >
          Temizle
        </button>
      </div>

      {/* Aktif bağlam göstergesi */}
      {chatContext && (
        <div className="flex items-center justify-between px-3 py-1.5 bg-blue-500/10 border-b border-blue-500/20 flex-shrink-0">
          <p className="text-[10px] text-blue-400 truncate mr-2">
            <span className="opacity-70 mr-1">Bağlam:</span>
            {chatContext.type === 'url'
              ? chatContext.data?.url?.slice(0, 50) + '…'
              : chatContext.data?.title ?? chatContext.data?.vuln_type}
          </p>
          <button
            onClick={clearChatContext}
            className="text-[10px] text-blue-400 hover:text-blue-200 flex-shrink-0"
          >
            ✕
          </button>
        </div>
      )}

      {/* Mesaj listesi */}
      <div className="flex-1 overflow-y-auto px-3 py-3 space-y-3">
        {messages.map((msg) => (
          <MessageBubble key={msg.id} msg={msg} />
        ))}
        <div ref={bottomRef} />
      </div>

      {/* Tarama özet satırı */}
      {activeScan && (
        <div className="px-3 py-1.5 bg-[#0a0e1a] border-t border-[#374151] flex-shrink-0">
          <p className="text-[10px] text-gray-600 truncate">
            <span className="font-mono text-gray-500">{activeScan.target}</span>
            {' · '}{findings.length} bulgu{' · '}{urls.length} URL
          </p>
        </div>
      )}

      {/* Giriş alanı */}
      <div className="px-3 py-2 border-t border-[#374151] flex-shrink-0">
        <div className="flex gap-2 items-end">
          <textarea
            ref={inputRef}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Bir şey sor… (Enter = gönder)"
            rows={2}
            className="
              flex-1 resize-none bg-[#1f2937] border border-[#374151]
              rounded text-xs text-gray-200 placeholder-gray-600
              px-2.5 py-2 focus:outline-none focus:border-blue-500
              transition-colors
            "
            disabled={streaming}
          />
          {streaming ? (
            <button
              onClick={cancelStream}
              className="flex-shrink-0 px-3 py-2 rounded bg-red-500/20 text-red-400
                hover:bg-red-500/30 text-xs transition-colors"
            >
              Durdur
            </button>
          ) : (
            <button
              onClick={sendMessage}
              disabled={!input.trim()}
              className="flex-shrink-0 px-3 py-2 rounded bg-blue-600 hover:bg-blue-500
                text-white text-xs font-medium
                disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
            >
              Gönder
            </button>
          )}
        </div>
        <p className="text-[10px] text-gray-700 mt-1">Shift+Enter = yeni satır</p>
      </div>
    </div>
  );
}

function MessageBubble({ msg }) {
  const isUser = msg.role === 'user';
  return (
    <div className={`flex ${isUser ? 'justify-end' : 'justify-start'}`}>
      <div className={`
        max-w-[90%] rounded-lg px-3 py-2 text-xs leading-relaxed
        ${isUser
          ? 'bg-blue-600 text-white'
          : msg.error
          ? 'bg-red-500/10 border border-red-500/30 text-red-400'
          : 'bg-[#1f2937] text-gray-200 border border-[#374151]'}
      `}>
        {msg.loading && !msg.content ? (
          <span className="flex gap-1 items-center text-gray-500">
            <span className="animate-pulse-dot">▪</span>
            <span className="animate-pulse-dot" style={{ animationDelay: '0.2s' }}>▪</span>
            <span className="animate-pulse-dot" style={{ animationDelay: '0.4s' }}>▪</span>
          </span>
        ) : (
          <span className="whitespace-pre-wrap break-words">{msg.content}</span>
        )}
      </div>
    </div>
  );
}
