"""
WebSocket baglanti yoneticisi ve event builder'lari.

Spesifikasyon Bolum 6 referans alinmistir.

Mimari:
    - ConnectionManager: tek ornek (singleton), tum scan WebSocket'lerini tutar.
    - Event builder'lar: saf fonksiyonlar, dict doner. ConnectionManager'dan
      bagimsizdir; herhangi bir yerden import edilip kullanilabilir.
    - send_to_scan / broadcast: JSON serializasyonu + sessiz hata yutma ile
      cokmus baglantilari otomatik ayiklar.

Client -> Server mesaj akisi:
    WebSocket endpoint'i (main.py) mesaji alinca scan_orchestrator'a
    iletir; bu modul yalnizca server -> client yonunu yonetir.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import WebSocket
from fastapi.websockets import WebSocketState
from starlette.websockets import WebSocketDisconnect

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Yardimcilar
# ---------------------------------------------------------------------------


def _now_iso() -> str:
    """UTC zamanim ISO 8601 formatinda doner. Ornek: '2026-05-19T14:32:01.123Z'"""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def _event(event_type: str, **payload: Any) -> Dict[str, Any]:
    """
    Temel event zarfi olusturur.

    Her event'e 'event' ve 'timestamp' alanlari eklenir; geri kalan
    anahtar-deger ciftleri ust seviyeye koyulur.
    """
    return {"event": event_type, "timestamp": _now_iso(), **payload}


# ---------------------------------------------------------------------------
# ConnectionManager
# ---------------------------------------------------------------------------


class ConnectionManager:
    """
    Tum aktif WebSocket baglantilarini yonetir.

    Her scan_id icin birden fazla WebSocket desteklenir (ornegin ayni
    taramayi izleyen birden fazla sekme).

    Kullanim:
        manager = ConnectionManager()      # main.py'de bir kez olusturulur
        await manager.connect(scan_id, ws)
        await manager.send_to_scan(scan_id, event_dict)
        manager.disconnect(scan_id, ws)
    """

    def __init__(self) -> None:
        # scan_id -> WebSocket listesi
        self._connections: Dict[str, List[WebSocket]] = defaultdict(list)
        # Yazma islemi sirasinda listeye etkilesim engellemek icin kilid
        self._lock = asyncio.Lock()

    # ------------------------------------------------------------------
    # Baglanti yonetimi
    # ------------------------------------------------------------------

    async def connect(self, scan_id: str, websocket: WebSocket) -> None:
        """
        Yeni bir WebSocket baglantiyi kabul eder ve kaydeder.

        WebSocket.accept() cagrilmadan once cagrilmali.

        Args:
            scan_id:   Abonelik yapilan tarama UUID'si.
            websocket: Kabul edilecek WebSocket baglantisi.
        """
        await websocket.accept()
        async with self._lock:
            self._connections[scan_id].append(websocket)
        logger.info(
            "WS baglanti kuruldu: scan_id=%s | toplam=%d",
            scan_id,
            len(self._connections[scan_id]),
        )

    def disconnect(self, scan_id: str, websocket: WebSocket) -> None:
        """
        Kapanis/hata sonrasinda WebSocket'i listeden cikarir.

        websocket.close() burada cagrilmaz; cagiran kod sorumludur.

        Args:
            scan_id:   Ilgili tarama UUID'si.
            websocket: Cikarilacak WebSocket.
        """
        conns = self._connections.get(scan_id, [])
        if websocket in conns:
            conns.remove(websocket)
        if not conns and scan_id in self._connections:
            del self._connections[scan_id]
        logger.debug("WS baglanti kapatildi: scan_id=%s", scan_id)

    def get_connection_count(self, scan_id: str) -> int:
        """Belirli bir scan_id icin aktif baglanti sayisini doner."""
        return len(self._connections.get(scan_id, []))

    def get_active_scan_ids(self) -> List[str]:
        """En az bir aktif baglantisi olan tum scan_id'leri doner."""
        return list(self._connections.keys())

    # ------------------------------------------------------------------
    # Gonderim
    # ------------------------------------------------------------------

    async def send_to_scan(self, scan_id: str, event_data: Dict[str, Any]) -> int:
        """
        Belirtilen scan_id'ye abone tum WebSocket'lere event gonderir.

        Kapali veya cokmus baglantilar sessizce cikarilir; uygulama
        calismaya devam eder.

        Args:
            scan_id:    Hedef tarama UUID'si.
            event_data: Gonderilecek sozluk; JSON'a cevirilir.

        Returns:
            Basariyla gonderilen baglanti sayisi.
        """
        conns = self._connections.get(scan_id, [])
        if not conns:
            return 0

        payload = json.dumps(event_data, ensure_ascii=False)
        dead: List[WebSocket] = []
        sent = 0

        for ws in list(conns):  # iterasyon sirasinda liste degismemesi icin kopya
            if ws.client_state != WebSocketState.CONNECTED:
                dead.append(ws)
                continue
            try:
                await ws.send_text(payload)
                sent += 1
            except (WebSocketDisconnect, RuntimeError) as exc:
                logger.debug("WS gonderim hatasi (baglanti koptu): %s", exc)
                dead.append(ws)
            except Exception as exc:
                logger.warning("WS beklenmedik hata: %s", exc)
                dead.append(ws)

        # Cokmus baglantilari temizle
        for ws in dead:
            self.disconnect(scan_id, ws)

        return sent

    async def broadcast(self, event_data: Dict[str, Any]) -> int:
        """
        Tum aktif baglantilara event gonderir.

        Sistem genelindeki bildirimler (global bildirim, bakim modu, vb.)
        icin kullanilir.

        Args:
            event_data: Gonderilecek sozluk.

        Returns:
            Toplam basariyla gonderilen baglanti sayisi.
        """
        total = 0
        for scan_id in list(self._connections.keys()):
            total += await self.send_to_scan(scan_id, event_data)
        return total

    async def send_json(
        self,
        scan_id: str,
        websocket: WebSocket,
        event_data: Dict[str, Any],
    ) -> bool:
        """
        Tek bir WebSocket'e gonderim yapar.

        scan_orchestrator gibi modullerin belirli bir baglantiya
        dogrudan yanit gondermesi gerektiginde kullanilir.

        Returns:
            True -> gonderildi, False -> hata/kapali.
        """
        try:
            if websocket.client_state != WebSocketState.CONNECTED:
                return False
            await websocket.send_text(json.dumps(event_data, ensure_ascii=False))
            return True
        except (WebSocketDisconnect, RuntimeError):
            self.disconnect(scan_id, websocket)
            return False
        except Exception as exc:
            logger.warning("send_json hatasi: %s", exc)
            return False


# ---------------------------------------------------------------------------
# Modul seviyesinde singleton
# ---------------------------------------------------------------------------

manager = ConnectionManager()
"""
Uygulama genelinde kullanilan tek ConnectionManager ornegi.

Import:
    from websocket_manager import manager
"""


# ===========================================================================
# Event builder fonksiyonlari — Bolum 6.1
# ===========================================================================
#
# Her fonksiyon saf bir sozluk doner.
# Cagiran kod bunu dogrudan manager.send_to_scan(scan_id, event) ile iletir.
# ===========================================================================


# ---------------------------------------------------------------------------
# Faz olaylari
# ---------------------------------------------------------------------------


def phase_started(phase: str, message: Optional[str] = None) -> Dict[str, Any]:
    """
    Yeni bir tarama fazi basladiginda gonderilir.

    Args:
        phase:   'recon' | 'discovery' | 'testing'
        message: Kullaniciya gosterilecek aciklama.
    """
    return _event(
        "phase_started",
        phase=phase,
        message=message or f"{phase.capitalize()} fazi basladi",
    )


def phase_completed(
    phase: str,
    stats: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Bir faz tamamlandiginda gonderilir.

    Args:
        phase: 'recon' | 'discovery' | 'testing'
        stats: Faza ozel istatistikler. Ornek: {"found": 42, "live": 38}
    """
    return _event("phase_completed", phase=phase, stats=stats or {})


# ---------------------------------------------------------------------------
# Arac olaylari
# ---------------------------------------------------------------------------


def tool_started(tool: str, target: str) -> Dict[str, Any]:
    """
    Bir arac calistirilmaya baslandiginda gonderilir.

    Args:
        tool:   Arac adi (subfinder, httpx, dalfox, vb.)
        target: Aracin hedefi (domain, URL, dosya yolu, vb.)
    """
    return _event("tool_started", tool=tool, target=target)


def tool_completed(tool: str, found_count: int = 0) -> Dict[str, Any]:
    """
    Bir arac calismasi tamamlandiginda gonderilir.

    Args:
        tool:        Arac adi.
        found_count: Aracin buldugu/urettigi sonuc sayisi.
    """
    return _event("tool_completed", tool=tool, found=found_count)


def tool_output(tool: str, line: str) -> Dict[str, Any]:
    """
    Arac stdout'undan bir satir geldiginde gonderilir.

    Cok sik gonderilmemesi icin cagiran kod debounce uygulayabilir.

    Args:
        tool: Arac adi.
        line: Cikti satiri.
    """
    return _event("tool_output", tool=tool, line=line)


def tool_error(tool: str, error: str) -> Dict[str, Any]:
    """
    Arac hatayla tamamlandiginda gonderilir.

    Args:
        tool:  Arac adi.
        error: Hata mesaji veya stderr ciktisi.
    """
    return _event("tool_error", tool=tool, error=error)


# ---------------------------------------------------------------------------
# Subdomain olaylari
# ---------------------------------------------------------------------------


def subdomain_found(subdomain_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Yeni bir subdomain kesfedildiginde gonderilir.

    Args:
        subdomain_data: Subdomain ORM modelinden turetilmis sozluk.
    """
    return _event("subdomain_found", data=subdomain_data)


def subdomain_ai_scored(
    subdomain_id: int,
    score: int,
    analysis: str,
    tags: Optional[List[str]] = None,
    priority: Optional[str] = None,
) -> Dict[str, Any]:
    """
    AI'nin bir subdomain'e skor atamasi tamamlandiginda gonderilir.

    Args:
        subdomain_id: Veritabanindaki subdomain ID'si.
        score:        0-100 arasi saldiri oncelik skoru.
        analysis:     AI'nin kisa gerekce metni.
        tags:         AI'nin atadigi etiketler (api, no-waf, vb.)
        priority:     critical | high | medium | low
    """
    return _event(
        "subdomain_ai_scored",
        data={
            "id": subdomain_id,
            "score": score,
            "analysis": analysis,
            "tags": tags or [],
            "priority": priority,
        },
    )


# ---------------------------------------------------------------------------
# URL olaylari
# ---------------------------------------------------------------------------


def url_found(url_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Tek bir URL kesfedildiginde gonderilir.

    Dusuk trafikli senaryolar icin; yuksek hacimde url_batch kullanilmali.

    Args:
        url_data: URL ORM modelinden turetilmis sozluk.
    """
    return _event("url_found", data=url_data)


def url_batch(urls: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Toplu URL kesfini bildirmek icin gonderilir.

    Cok sayida URL kesfedildiginde tek tek url_found yerine bu kullanilir.

    Args:
        urls: URL sozlukleri listesi.
    """
    return _event("url_batch", count=len(urls), data=urls)


def url_ai_analyzed(
    url_id: int,
    risk_score: int,
    vuln_categories: Optional[List[str]] = None,
    ai_analysis: Optional[str] = None,
) -> Dict[str, Any]:
    """
    AI'nin bir URL icin risk analizi tamamlandiginda gonderilir.

    Args:
        url_id:          Veritabanindaki URL ID'si.
        risk_score:      0-100 arasi risk skoru.
        vuln_categories: Tespit edilen zafiyet kategorileri.
        ai_analysis:     AI'nin kisa analiz notu.
    """
    return _event(
        "url_ai_analyzed",
        data={
            "id": url_id,
            "risk_score": risk_score,
            "categories": vuln_categories or [],
            "analysis": ai_analysis,
        },
    )


# ---------------------------------------------------------------------------
# Test / bulgu olaylari
# ---------------------------------------------------------------------------


def test_started(url_id: int, test_type: str) -> Dict[str, Any]:
    """
    Belirli bir URL icin test baslatildiginda gonderilir.

    Args:
        url_id:    Hedef URL'nin veritabani ID'si.
        test_type: 'xss' | 'sqli' | 'lfi' | 'redirect' | 'ssrf' | 'nuclei'
    """
    return _event("test_started", url_id=url_id, test_type=test_type)


def finding_found(finding_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Yeni bir zafiyet bulgusу kaydedildiginde gonderilir.

    Args:
        finding_data: Finding ORM modelinden turetilmis sozluk.
    """
    return _event("finding_found", data=finding_data)


def waf_detected(waf_name: str, url: str) -> Dict[str, Any]:
    """
    Hedefte WAF tespit edildiginde gonderilir.

    Args:
        waf_name: Tespit edilen WAF adi (Cloudflare, ModSecurity, vb.)
        url:      WAF'in tespit edildigi URL.
    """
    return _event("waf_detected", data={"waf": waf_name, "url": url})


def waf_suggestions(techniques: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    AI'nin WAF bypass teknik onerilerini iletmek icin gonderilir.

    Args:
        techniques: suggest_waf_bypass() tarafindan uretilen teknik listesi.
    """
    return _event("waf_suggestions", data={"techniques": techniques})


# ---------------------------------------------------------------------------
# Tarama durum olaylari
# ---------------------------------------------------------------------------


def scan_paused() -> Dict[str, Any]:
    """Tarama duraklatildiginda gonderilir."""
    return _event("scan_paused")


def scan_resumed() -> Dict[str, Any]:
    """Duraklatilmis tarama devam ettirildiginde gonderilir."""
    return _event("scan_resumed")


def scan_stopped() -> Dict[str, Any]:
    """Tarama kullanici tarafindan durduruldugunda gonderilir."""
    return _event("scan_stopped")


def scan_completed(stats: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Tarama basariyla tamamlandiginda gonderilir.

    Args:
        stats: Ozet istatistikler. Ornek:
               {"total_subdomains": 42, "total_urls": 1800, "total_findings": 7}
    """
    return _event("scan_completed", stats=stats or {})


def scan_error(message: str) -> Dict[str, Any]:
    """
    Tarama beklenmedik bir hatayla karsilastiginda gonderilir.

    Args:
        message: Hata aciklamasi (kullaniciya gosterilecek).
    """
    return _event("scan_error", message=message)


def progress(percent: int, phase: Optional[str] = None) -> Dict[str, Any]:
    """
    Tarama genel ilerleme durumunu bildirir.

    Fazin baslangicinda ve her onemli adimdan sonra gonderilir.

    Args:
        percent: 0-100 arasi tamamlanma yuzdesi.
        phase:   Mevcut faz adi ('recon' | 'discovery' | 'testing')
    """
    return _event("progress", percent=max(0, min(100, percent)), phase=phase)


def notification(title: str, body: str) -> Dict[str, Any]:
    """
    Kullaniciya gosterilecek bildirim mesaji.

    Tarama tamamlandi, onemli bulgu gibi durumlarda gonderilir.

    Args:
        title: Bildirim basligi.
        body:  Bildirim icerigi.
    """
    return _event("notification", title=title, body=body)


# ---------------------------------------------------------------------------
# Pong (ping'e yanit)
# ---------------------------------------------------------------------------


def pong() -> Dict[str, Any]:
    """Client'in gonderdigi 'ping' eylemine yanit olarak gonderilir."""
    return _event("pong")
