"""
VulnScan AI — FastAPI uygulama giriş noktası.

Spesifikasyon Bölüm 13.2 — Başlatma sırası:
    1. Config yükle (.env)
    2. Data klasörlerini oluştur (data/, data/wordlists/, data/sqlmap/)
    3. init_db() → SQLite tablolarını oluştur
    4. tool_manager.check_all_tools() → durumları cache'le, logla
    5. ai_engine ping → Ollama durumunu logla
    6. Wordlist'ler yoksa SecLists'ten indir
    7. FastAPI uygulamasını başlat (port 8080)
    8. Frontend dist/ klasörünü static olarak serve et
       — html=True → tüm bilinmeyen path'ler index.html döner (React Router)
    9. Sadece TTY'de çalışıyorsa webbrowser.open()

WebSocket (Bölüm 5.8 / 6.2):
    WS /ws/{scan_id}
    Client→Server: pause, resume, stop, ping,
                   subdomain_selection, test_start, waf_bypass, waf_skip
"""

from __future__ import annotations

import json
import logging
import os
import sys
import webbrowser
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Dict, List

import uvicorn
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

import ai_engine
import tool_manager as tm
import websocket_manager as ws_events
from config import DATA_DIR, WORDLISTS_DIR, settings
from database import check_db_connection, init_db
from routers.ai import router as ai_router
from routers.reports import router as reports_router
from routers.scans import findings_router, router as scans_router, urls_router
from routers.tools import router as tools_router
from scan_orchestrator import ScanOrchestrator
from websocket_manager import manager as ws_manager

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Sabitler
# ---------------------------------------------------------------------------

_BACKEND_DIR = Path(__file__).resolve().parent
_FRONTEND_DIST = _BACKEND_DIR.parent / "frontend" / "dist"

# SecLists wordlist URL'leri ve hedef dosya adları
_WORDLISTS: List[Dict[str, str]] = [
    {
        "name": "top-1000.txt",
        "url": (
            "https://raw.githubusercontent.com/danielmiessler/SecLists"
            "/master/Discovery/Web-Content/common.txt"
        ),
    },
    {
        "name": "top-10000.txt",
        "url": (
            "https://raw.githubusercontent.com/danielmiessler/SecLists"
            "/master/Discovery/Web-Content/raft-medium-words.txt"
        ),
    },
    {
        "name": "seclists-big.txt",
        "url": (
            "https://raw.githubusercontent.com/danielmiessler/SecLists"
            "/master/Discovery/Web-Content/big.txt"
        ),
    },
]

# ---------------------------------------------------------------------------
# CORS izin verilen kökenler (yalnızca localhost)
# ---------------------------------------------------------------------------

_CORS_ORIGINS: List[str] = [
    "http://localhost",
    "http://localhost:3000",   # CRA geliştirme
    "http://localhost:5173",   # Vite geliştirme
    "http://localhost:8080",   # Üretim portu
    "http://localhost:8000",
    "http://127.0.0.1",
    "http://127.0.0.1:3000",
    "http://127.0.0.1:5173",
    "http://127.0.0.1:8080",
    "http://127.0.0.1:8000",
]

# ===========================================================================
# Startup yardımcı fonksiyonları
# ===========================================================================


def _ensure_data_dirs() -> None:
    """Gerekli veri klasörlerini oluşturur."""
    dirs = [
        DATA_DIR,
        WORDLISTS_DIR,
        DATA_DIR / "sqlmap",
        DATA_DIR / "nuclei",
        DATA_DIR / "logs",
    ]
    for d in dirs:
        d.mkdir(parents=True, exist_ok=True)
    logger.info("[startup] Veri klasörleri hazır: %s", DATA_DIR)


async def _download_wordlists() -> None:
    """
    Eksik wordlist dosyalarını SecLists GitHub'dan indirir.

    Her dosya için:
    - Hedef: data/wordlists/<name>
    - Eksikse indir; varsa atla (boyut sıfırsa yeniden indir)
    - İndirme hatası sessizce loglanır; uygulama durmaz.
    """
    try:
        import httpx as _httpx  # httpx zaten bağımlılıkta var
    except ImportError:
        logger.warning("[startup] httpx bulunamadı, wordlist indirmesi atlandı.")
        return

    for wl in _WORDLISTS:
        dest = WORDLISTS_DIR / wl["name"]
        if dest.exists() and dest.stat().st_size > 0:
            logger.debug("[startup] Wordlist mevcut, atlandı: %s", wl["name"])
            continue

        logger.info("[startup] Wordlist indiriliyor: %s ...", wl["name"])
        try:
            async with _httpx.AsyncClient(timeout=60.0, follow_redirects=True) as client:
                async with client.stream("GET", wl["url"]) as response:
                    if response.status_code != 200:
                        logger.warning(
                            "[startup] Wordlist indirilemedi (%s): HTTP %d",
                            wl["name"],
                            response.status_code,
                        )
                        continue
                    with open(dest, "wb") as f:
                        async for chunk in response.aiter_bytes(chunk_size=65536):
                            f.write(chunk)
            size_kb = dest.stat().st_size // 1024
            logger.info("[startup] Wordlist indirildi: %s (%d KB)", wl["name"], size_kb)
        except Exception as exc:
            logger.warning("[startup] Wordlist indirme hatası (%s): %s", wl["name"], exc)
            # Yarım kalan dosyayı temizle
            if dest.exists():
                try:
                    dest.unlink()
                except OSError:
                    pass


def _is_tty() -> bool:
    """Gerçek bir terminal oturumunda çalışıp çalışmadığımızı döndürür."""
    try:
        return sys.stdin.isatty() and sys.stdout.isatty()
    except Exception:
        return False


def _open_browser_once() -> None:
    """
    Tarayıcıyı bir kez açar.

    Yalnızca TTY ortamında (interaktif terminal) çalışır;
    CI, Docker veya servis olarak çalıştırılırken açılmaz.
    """
    if not _is_tty():
        logger.debug("[startup] TTY değil, tarayıcı açılmıyor.")
        return

    import threading
    import time

    url = f"http://localhost:{settings.APP_PORT}"

    def _open() -> None:
        time.sleep(2.0)  # Sunucunun tamamen ayağa kalkmasını bekle
        try:
            webbrowser.open(url)
            logger.info("[startup] Tarayıcı açıldı: %s", url)
        except Exception as exc:
            logger.debug("[startup] Tarayıcı açılamadı: %s", exc)

    t = threading.Thread(target=_open, daemon=True, name="browser-opener")
    t.start()


# ===========================================================================
# Uygulama yaşam döngüsü
# ===========================================================================


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Uygulama başlatma ve kapatma işlemlerini yönetir.

    Sıra:
        1. Data klasörleri
        2. Veritabanı init
        3. Araç kontrolü
        4. Ollama ping
        5. Wordlist indirme
        6. Orkestratör init
        7. Tarayıcı açma (TTY'de)
    """
    # -----------------------------------------------------------------
    # 1. Data klasörleri
    # -----------------------------------------------------------------
    _ensure_data_dirs()

    # -----------------------------------------------------------------
    # 2. Veritabanı
    # -----------------------------------------------------------------
    logger.info("[startup] Veritabanı başlatılıyor...")
    await init_db()
    db_ok = await check_db_connection()
    if db_ok:
        logger.info("[startup] Veritabanı hazır.")
    else:
        logger.error("[startup] Veritabanı bağlantısı başarısız — uygulama çalışmaya devam ediyor.")

    # -----------------------------------------------------------------
    # 3. Araçlar
    # -----------------------------------------------------------------
    logger.info("[startup] Araçlar kontrol ediliyor...")
    try:
        tool_statuses = await tm.check_all_tools()
        summary = tm.get_tools_summary(tool_statuses)
        app.state.tool_statuses = tool_statuses
        logger.info(
            "[startup] Araçlar: %d/%d kurulu | Eksik zorunlu: %s | Eksik opsiyonel: %s",
            sum(1 for s in tool_statuses.values() if s.installed),
            len(tool_statuses),
            summary["missing_required"] or "yok",
            summary["missing_optional"] or "yok",
        )
    except Exception as exc:
        logger.warning("[startup] Araç kontrolü hatası: %s", exc)
        tool_statuses = {}
        app.state.tool_statuses = tool_statuses

    # -----------------------------------------------------------------
    # 4. Ollama (AI Engine)
    # -----------------------------------------------------------------
    logger.info("[startup] Ollama bağlantısı test ediliyor (%s)...", settings.OLLAMA_HOST)
    ai_client = ai_engine.get_client()
    try:
        ollama_ok = await ai_client.ping()
        if ollama_ok:
            logger.info("[startup] Ollama hazır — model: %s", settings.OLLAMA_MODEL)
        else:
            logger.warning(
                "[startup] Ollama yanıt vermedi (%s). AI özellikleri çalışmayabilir.",
                settings.OLLAMA_HOST,
            )
    except Exception as exc:
        logger.warning("[startup] Ollama ping hatası: %s", exc)

    app.state.ai_engine = ai_client

    # -----------------------------------------------------------------
    # 5. Wordlist'ler
    # -----------------------------------------------------------------
    logger.info("[startup] Wordlist'ler kontrol ediliyor...")
    await _download_wordlists()

    # -----------------------------------------------------------------
    # 6. WebSocket Manager + Orkestratör
    # -----------------------------------------------------------------
    app.state.ws_manager = ws_manager

    orchestrator = ScanOrchestrator(
        ws_manager=ws_manager,
        ai_engine=ai_client,
        tool_manager=tool_statuses,
    )
    app.state.orchestrator = orchestrator
    logger.info("[startup] Orkestratör başlatıldı.")

    # -----------------------------------------------------------------
    # 7. Orphaned scan temizliği
    # -----------------------------------------------------------------
    # Sunucu yeniden başlatıldığında 'running', 'paused' veya 'waiting_user'
    # durumundaki taramalar artık orkestratörde yok — DB'yi 'stopped' yap.
    try:
        from sqlalchemy import update as _sa_update
        from models import Scan as _Scan
        from database import AsyncSessionLocal as _ASL
        async with _ASL() as _session:
            result = await _session.execute(
                _sa_update(_Scan)
                .where(_Scan.status.in_(["running", "paused", "waiting_user"]))
                .values(status="stopped")
                .execution_options(synchronize_session=False)
            )
            await _session.commit()
            if result.rowcount:
                logger.info(
                    "[startup] %d orphaned tarama 'stopped' olarak işaretlendi.",
                    result.rowcount,
                )
    except Exception as _exc:
        logger.warning("[startup] Orphaned scan temizliği başarısız: %s", _exc)

    # -----------------------------------------------------------------
    # 8. Tarayıcı aç (TTY'de)
    # -----------------------------------------------------------------
    _open_browser_once()

    logger.info(
        "[startup] ✓ VulnScan AI hazır → http://localhost:%d  |  API: /api/docs",
        settings.APP_PORT,
    )

    # -----------------------------------------------------------------
    yield  # Uygulama çalışıyor
    # -----------------------------------------------------------------

    # Kapatma
    logger.info("[shutdown] Aktif taramalar durduruluyor (%d)...", len(orchestrator.active_scans))
    for scan_id in list(orchestrator.active_scans.keys()):
        try:
            await orchestrator.stop_scan(scan_id)
        except Exception:
            pass
    logger.info("[shutdown] Kapatma tamamlandı.")


# ===========================================================================
# FastAPI uygulaması
# ===========================================================================

app = FastAPI(
    title="VulnScan AI",
    version="1.0.0",
    description="AI destekli web zafiyet tarayıcı — Pasif tespit + kullanıcı gözetiminde aktif test.",
    lifespan=lifespan,
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
)

# ---------------------------------------------------------------------------
# CORS — yalnızca localhost kökenler
# ---------------------------------------------------------------------------

app.add_middleware(
    CORSMiddleware,
    allow_origins=_CORS_ORIGINS,
    allow_origin_regex=r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$",
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Genel hata handler'ları
# ---------------------------------------------------------------------------


@app.exception_handler(404)
async def _404_handler(request: Request, exc: Exception) -> JSONResponse:
    """API rotaları için 404; SPA rotaları için index.html."""
    if request.url.path.startswith("/api/") or request.url.path.startswith("/ws/"):
        # HTTPException'dan gelen detail'i koru; yoksa genel mesaj göster
        detail = getattr(exc, "detail", None) or f"Endpoint bulunamadı: {request.url.path}"
        return JSONResponse(
            status_code=404,
            content={"detail": detail},
        )
    # React Router: API olmayan path'ler için index.html
    index = _FRONTEND_DIST / "index.html"
    if index.is_file():
        return FileResponse(str(index))
    return JSONResponse(
        status_code=404,
        content={"detail": "Sayfa bulunamadı. Frontend build mevcut değil."},
    )


@app.exception_handler(500)
async def _500_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.error("Sunucu hatası [%s %s]: %s", request.method, request.url.path, exc, exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": "Sunucu hatası oluştu. Lütfen logları kontrol edin."},
    )


# ===========================================================================
# Router'ları bağla (static mount'tan ÖNCE kayıt edilmeli)
# ===========================================================================

app.include_router(scans_router)
app.include_router(findings_router)
app.include_router(urls_router)
app.include_router(tools_router)
app.include_router(reports_router)
app.include_router(ai_router)


# ---------------------------------------------------------------------------
# Sağlık kontrolü
# ---------------------------------------------------------------------------


@app.get("/api/health", tags=["system"])
async def health_check() -> Dict[str, Any]:
    """Sistem sağlık durumunu döndürür."""
    db_ok = await check_db_connection()
    ollama_ok = False
    try:
        client = ai_engine.get_client()
        ollama_ok = await client.ping()
    except Exception:
        pass

    # Araç özeti
    tool_statuses = getattr(app.state, "tool_statuses", {})
    tool_summary = tm.get_tools_summary(tool_statuses) if tool_statuses else {}

    return {
        "status": "ok" if (db_ok and ollama_ok) else "degraded",
        "version": "1.0.0",
        "ollama_status": ollama_ok,
        "ollama_model": settings.OLLAMA_MODEL,
        "db_status": db_ok,
        "tools_all_required": tool_summary.get("all_required_installed", False),
        "missing_required": tool_summary.get("missing_required", []),
    }


# ===========================================================================
# WebSocket — Bölüm 5.8 / 6.2
# ===========================================================================


@app.websocket("/ws/{scan_id}")
async def websocket_endpoint(websocket: WebSocket, scan_id: str) -> None:
    """
    Tarama canlı güncelleme WebSocket kanalı.

    Bağlantı kabul edilince aktif tarama varsa mevcut durum bildirilir.

    Client → Server mesajları (JSON):
        { "action": "ping" }
        { "action": "pause" }
        { "action": "resume" }
        { "action": "stop" }
        { "action": "subdomain_selection", "subdomain_ids": [1, 2, 3] }
        { "action": "test_start",          "url_ids": [...], "test_types": [...] }
        { "action": "waf_bypass",          "technique": { "name": "...", ...} }
        { "action": "waf_skip" }
    """
    await ws_manager.connect(scan_id, websocket)
    orchestrator: ScanOrchestrator = app.state.orchestrator

    try:
        # Bağlantı onayı — aktif tarama varsa durumunu bildir
        status_info = orchestrator.get_scan_status(scan_id)
        # status_info zaten scan_id içerebilir — çakışmayı önlemek için çıkar
        extra = {k: v for k, v in (status_info or {}).items() if k != "scan_id"}
        await websocket.send_json(
            ws_events._event(
                "connected",
                scan_id=scan_id,
                active=status_info is not None,
                **extra,
            )
        )

        # Ana mesaj döngüsü
        while True:
            try:
                raw = await websocket.receive_text()
            except WebSocketDisconnect:
                break

            # JSON parse
            try:
                msg: Dict[str, Any] = json.loads(raw)
            except json.JSONDecodeError:
                await websocket.send_json(
                    ws_events._event("error", message="Geçersiz JSON. Beklenen format: {\"action\": \"...\"}")
                )
                continue

            action: str = msg.get("action", "")

            # ------------------------------------------------------------------
            if action == "ping":
                await websocket.send_json(ws_events.pong())

            elif action == "pause":
                try:
                    await orchestrator.pause_scan(scan_id)
                except KeyError:
                    await _send_err(websocket, "Aktif tarama bulunamadı.")

            elif action == "resume":
                try:
                    await orchestrator.resume_scan(scan_id)
                except KeyError:
                    await _send_err(websocket, "Aktif tarama bulunamadı.")

            elif action == "stop":
                try:
                    await orchestrator.stop_scan(scan_id)
                except KeyError:
                    await _send_err(websocket, "Aktif tarama bulunamadı.")

            elif action == "subdomain_selection":
                ids = msg.get("subdomain_ids")
                if not isinstance(ids, list):
                    await _send_err(websocket, "subdomain_ids alanı bir liste olmalıdır.")
                    continue
                try:
                    orchestrator.notify_subdomain_selection(scan_id, ids)
                    await websocket.send_json(
                        ws_events._event("ack", action="subdomain_selection", count=len(ids))
                    )
                except KeyError:
                    await _send_err(websocket, "Aktif tarama bulunamadı.")

            elif action == "test_start":
                url_ids = msg.get("url_ids", [])
                test_types = msg.get("test_types", [])
                if not url_ids or not test_types:
                    await _send_err(websocket, "url_ids ve test_types alanları zorunludur.")
                    continue
                try:
                    orchestrator.notify_test_start(scan_id, url_ids, test_types)
                    await websocket.send_json(
                        ws_events._event(
                            "ack",
                            action="test_start",
                            url_count=len(url_ids),
                            test_types=test_types,
                        )
                    )
                except KeyError:
                    await _send_err(websocket, "Aktif tarama bulunamadı.")

            elif action == "waf_bypass":
                technique = msg.get("technique")
                if not technique:
                    await _send_err(websocket, "technique alanı zorunludur.")
                    continue
                try:
                    orchestrator.apply_bypass(scan_id, technique)
                    await websocket.send_json(ws_events._event("ack", action="waf_bypass"))
                except KeyError:
                    await _send_err(websocket, "Aktif tarama bulunamadı.")

            elif action == "waf_skip":
                try:
                    orchestrator.skip_bypass(scan_id)
                    await websocket.send_json(ws_events._event("ack", action="waf_skip"))
                except KeyError:
                    await _send_err(websocket, "Aktif tarama bulunamadı.")

            else:
                await _send_err(websocket, f"Bilinmeyen action: '{action}'")

    except WebSocketDisconnect:
        pass
    except Exception as exc:
        logger.error("[ws:%s] Beklenmedik hata: %s", scan_id, exc, exc_info=True)
    finally:
        ws_manager.disconnect(scan_id, websocket)


async def _send_err(websocket: WebSocket, message: str) -> None:
    """WebSocket üzerinden hata mesajı gönderir; bağlantı kopuksa sessizce geçer."""
    try:
        await websocket.send_json(ws_events._event("error", message=message))
    except Exception:
        pass


# ===========================================================================
# Frontend static dosyalar + SPA fallback
# ===========================================================================
#
# StaticFiles(html=True) şu davranışı sağlar:
#   - İstek yolu dosyaya karşılık geliyorsa → dosyayı döner
#   - Karşılık gelmiyorsa → index.html döner (React Router için)
#
# ÖNEMLİ: Bu mount, tüm router kayıtlarından SONRA yapılmalıdır.
# FastAPI explicit route'ları önce kontrol eder, sonra mount'lara bakar.
# Böylece /api/* ve /ws/* yolları router'lar tarafından yaklanır.
# ===========================================================================

if _FRONTEND_DIST.is_dir():
    app.mount(
        "/",
        StaticFiles(directory=str(_FRONTEND_DIST), html=True),
        name="frontend",
    )
    logger.info("[startup] Frontend serve ediliyor: %s", _FRONTEND_DIST)
else:
    # dist yokken bile React yolları için fallback sağla
    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa_fallback(full_path: str) -> JSONResponse:
        """Frontend build olmadığında bilgilendirici yanıt döner."""
        return JSONResponse(
            status_code=503,
            content={
                "message": "Frontend henüz build edilmedi.",
                "api_docs": f"http://localhost:{settings.APP_PORT}/api/docs",
                "build_command": "cd frontend && npm install && npm run build",
            },
        )


# ===========================================================================
# Giriş noktası
# ===========================================================================

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.DEBUG if settings.DEBUG else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
        datefmt="%H:%M:%S",
    )

    uvicorn.run(
        "main:app",
        host=settings.APP_HOST,
        port=settings.APP_PORT,
        reload=settings.DEBUG,
        log_level="debug" if settings.DEBUG else "info",
        access_log=settings.DEBUG,
    )
