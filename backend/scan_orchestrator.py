"""
Tarama orkestratörü — Spesifikasyon Bölüm 7 ve 8.

Bileşenler:
    _ScanWsAdapter   — ws_manager.broadcast() çağrılarını scan_id'ye özgü
                       send_to_scan() çağrısına dönüştüren ince sarmalayıcı.
    ScanRunner       — Tek bir tarama için asyncio koordinasyon nesnesi.
    ScanOrchestrator — Tüm aktif taramaları yöneten merkezi singleton.

Tarama akışı (_run_scan):
    1. Recon  → 2. Kullanıcı subdomain seçimi bekle
    3. Discovery → 4. Kullanıcı test başlatma bekle
    5. Testing → 6. Rapor oluştur → 7. Tamamlandı

Duraklatma: asyncio.Event (set=çalışıyor, clear=duraklatıldı)
Subdomain seçimi: asyncio.Event + notify_subdomain_selection()
Test başlatma: asyncio.Event + notify_test_start()
WAF bypass: TestingPhase.apply_bypass() / skip_bypass() proxy'si
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

import websocket_manager as ws_events
from database import AsyncSessionLocal
from models import Finding, Report, Scan, Subdomain, Url
from phases.discovery import DiscoveryPhase
from phases.recon import ReconPhase
from phases.testing import TestingPhase

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Yardımcılar
# ---------------------------------------------------------------------------


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# WS adaptörü — fazlara geçilen ws_manager yerine kullanılır
# ---------------------------------------------------------------------------


class _ScanWsAdapter:
    """
    Fazların çağırdığı ws_manager.broadcast(event) çağrısını
    ilgili scan_id'ye özgü send_to_scan() çağrısına yönlendirir.

    Böylece olaylar yalnızca o taramayı dinleyen istemcilere gider.
    """

    def __init__(self, ws_manager: Any, scan_id: str) -> None:
        self._manager = ws_manager
        self._scan_id = scan_id

    async def broadcast(self, event_data: Dict[str, Any]) -> int:
        # Fazların ürettiği event dict'lerine scan_id ekle (client filtrelemesi için)
        if "scan_id" not in event_data:
            event_data = {**event_data, "scan_id": self._scan_id}
        return await self._manager.send_to_scan(self._scan_id, event_data)

    async def send_to_scan(self, scan_id: str, event_data: Dict[str, Any]) -> int:
        """Doğrudan send_to_scan çağrısına izin verir (geriye dönük uyum)."""
        return await self._manager.send_to_scan(scan_id, event_data)


# ---------------------------------------------------------------------------
# ScanRunner — tek tarama için koordinasyon nesnesi
# ---------------------------------------------------------------------------


class ScanRunner:
    """
    Tek bir tarama oturumunun in-memory koordinasyon nesnesidir.

    ScanOrchestrator tarafından oluşturulur ve active_scans sözlüğünde tutulur.
    Tarama bitince (tamamlandı / durduruldu / hata) sözlükten çıkarılır.
    """

    def __init__(
        self,
        scan_id: str,
        ws_manager: Any,
        ai_engine: Any,
        tool_manager: Any,
    ) -> None:
        self.scan_id = scan_id
        self.ws_manager = ws_manager
        self.ai_engine = ai_engine
        self.tool_manager = tool_manager

        # set() = çalışıyor, clear() = duraklatıldı
        self.pause_event: asyncio.Event = asyncio.Event()
        self.pause_event.set()

        # Subdomain seçim sinyali (Recon → Discovery arası bekleme)
        self._subdomain_selection_event: asyncio.Event = asyncio.Event()
        self._selected_subdomain_ids: List[int] = []

        # Test başlatma sinyali (Discovery → Testing arası bekleme)
        self._test_start_event: asyncio.Event = asyncio.Event()
        self._test_config: Dict[str, Any] = {}   # url_ids, test_types

        # Geçerli asyncio.Task
        self.current_task: Optional[asyncio.Task] = None

        # Durum — DB ile senkron tutulur; hızlı erişim için burada da saklanır
        self.status: str = "pending"

        # Testing fazı referansı (WAF bypass proxy'si için)
        self._testing_phase: Optional[TestingPhase] = None

    # ------------------------------------------------------------------
    # Dış sinyal metotları — API/WS handler tarafından çağrılır
    # ------------------------------------------------------------------

    def notify_subdomain_selection(self, subdomain_ids: List[int]) -> None:
        """
        Kullanıcı discovery fazı için subdomain seçimini tamamladığında çağrılır.

        Args:
            subdomain_ids: Seçilen Subdomain.id listesi.
        """
        self._selected_subdomain_ids = subdomain_ids
        self._subdomain_selection_event.set()
        logger.info(
            "[runner:%s] Subdomain seçimi alındı — %d subdomain",
            self.scan_id,
            len(subdomain_ids),
        )

    def notify_test_start(
        self,
        url_ids: List[int],
        test_types: List[str],
    ) -> None:
        """
        Kullanıcı testing fazını başlattığında çağrılır.

        Args:
            url_ids:    Test edilecek URL ID'leri.
            test_types: Çalıştırılacak test türleri (xss, sqli, …).
        """
        self._test_config = {"url_ids": url_ids, "test_types": test_types}
        self._test_start_event.set()
        logger.info(
            "[runner:%s] Test başlatma alındı — %d URL, %s",
            self.scan_id,
            len(url_ids),
            test_types,
        )

    def apply_bypass(self, technique: Dict[str, Any]) -> None:
        """WAF bypass tekniğini testing fazına iletir."""
        if self._testing_phase is not None:
            self._testing_phase.apply_bypass(technique)

    def skip_bypass(self) -> None:
        """WAF bypass atlama kararını testing fazına iletir."""
        if self._testing_phase is not None:
            self._testing_phase.skip_bypass()


# ---------------------------------------------------------------------------
# ScanOrchestrator — singleton
# ---------------------------------------------------------------------------


class ScanOrchestrator:
    """
    Tüm aktif taramaları yöneten merkezi orkestratör.

    Uygulama yaşam döngüsü boyunca tek örnek kullanılır
    (main.py'de oluşturulur, app.state.orchestrator ile erişilir).

    Özellikler:
        active_scans: Aktif ScanRunner nesneleri (scan_id → ScanRunner).
    """

    def __init__(
        self,
        ws_manager: Any,
        ai_engine: Any,
        tool_manager: Any,
    ) -> None:
        self.ws_manager = ws_manager
        self.ai_engine = ai_engine
        self.tool_manager = tool_manager
        self.active_scans: Dict[str, ScanRunner] = {}

    # ------------------------------------------------------------------
    # Tarama yönetimi
    # ------------------------------------------------------------------

    async def create_scan(self, scan_data: Dict[str, Any]) -> str:
        """
        Yeni bir tarama kaydı oluşturur ve scan_id döndürür.

        Args:
            scan_data: {
                "target": str,              — zorunlu
                "scope":  "single"|"subdomains", — zorunlu
                "mode":   "stealth"|"normal"|"aggressive",
                "name":   str,              — isteğe bağlı
                "config": dict,             — isteğe bağlı (araç seçimleri)
            }

        Returns:
            Oluşturulan taramanın UUID string ID'si.
        """
        scan_id = str(uuid.uuid4())
        async with AsyncSessionLocal() as db:
            scan = Scan(
                id=scan_id,
                name=scan_data.get("name"),
                target=scan_data["target"],
                scope=scan_data["scope"],
                mode=scan_data.get("mode", "normal"),
                status="pending",
            )
            scan.config = scan_data.get("config")
            db.add(scan)
            await db.commit()
        logger.info("[orchestrator] Tarama oluşturuldu: %s → %s", scan_id, scan_data["target"])
        return scan_id

    async def start_scan(self, scan_id: str) -> asyncio.Task:
        """
        Taramayı arka planda başlatır.

        Aynı scan_id için zaten çalışan bir runner varsa ValueError fırlatır.

        Returns:
            Arka planda çalışan asyncio.Task nesnesi.
        """
        if scan_id in self.active_scans:
            raise ValueError(f"Tarama zaten çalışıyor: {scan_id}")

        runner = ScanRunner(
            scan_id=scan_id,
            ws_manager=self.ws_manager,
            ai_engine=self.ai_engine,
            tool_manager=self.tool_manager,
        )
        self.active_scans[scan_id] = runner

        task = asyncio.create_task(
            self._run_scan(scan_id, runner),
            name=f"scan-{scan_id}",
        )
        runner.current_task = task

        # Tarama bitince active_scans'dan temizle
        def _on_done(t: asyncio.Task) -> None:
            self.active_scans.pop(scan_id, None)
            if t.cancelled():
                logger.info("[orchestrator] Task iptal edildi: %s", scan_id)
            elif t.exception():
                logger.error(
                    "[orchestrator] Task hatayla bitti: %s — %s",
                    scan_id,
                    t.exception(),
                )

        task.add_done_callback(_on_done)
        logger.info("[orchestrator] Tarama başlatıldı: %s", scan_id)
        return task

    async def pause_scan(self, scan_id: str) -> None:
        """
        Taramayı duraklatır.

        pause_event.clear() ile araçlar wait() noktasında bekler.
        DB durumu 'paused' olarak güncellenir.
        """
        runner = self._get_runner(scan_id)
        runner.pause_event.clear()
        runner.status = "paused"
        await self._update_scan_status(scan_id, "paused")
        await self.ws_manager.send_to_scan(scan_id, ws_events.scan_paused())
        logger.info("[orchestrator] Tarama duraklatıldı: %s", scan_id)

    async def resume_scan(self, scan_id: str) -> None:
        """
        Duraklatılmış taramayı devam ettirir.

        pause_event.set() ile bekleyen araçlar çalışmaya devam eder.
        """
        runner = self._get_runner(scan_id)
        runner.pause_event.set()
        runner.status = "running"
        await self._update_scan_status(scan_id, "running")
        await self.ws_manager.send_to_scan(scan_id, ws_events.scan_resumed())
        logger.info("[orchestrator] Tarama devam ettirildi: %s", scan_id)

    async def stop_scan(self, scan_id: str) -> None:
        """
        Taramayı durdurur.

        Arka plan task'ı iptal edilir; _run_scan içindeki CancelledError
        DB durumunu 'stopped' olarak kaydeder.
        """
        runner = self._get_runner(scan_id)
        if runner.current_task and not runner.current_task.done():
            runner.current_task.cancel()
        logger.info("[orchestrator] Tarama durduruldu: %s", scan_id)

    def get_scan_status(self, scan_id: str) -> Optional[Dict[str, Any]]:
        """
        Aktif taramanın in-memory durumunu döndürür.

        Tarama active_scans'da yoksa None döner.
        """
        runner = self.active_scans.get(scan_id)
        if runner is None:
            return None
        return {
            "scan_id": scan_id,
            "status": runner.status,
            "paused": not runner.pause_event.is_set(),
        }

    # ------------------------------------------------------------------
    # Dış sinyal proxy'leri
    # ------------------------------------------------------------------

    def notify_subdomain_selection(
        self, scan_id: str, subdomain_ids: List[int]
    ) -> None:
        """API/WS handler'ından subdomain seçim sinyali alır."""
        runner = self._get_runner(scan_id)
        runner.notify_subdomain_selection(subdomain_ids)

    def notify_test_start(
        self,
        scan_id: str,
        url_ids: List[int],
        test_types: List[str],
    ) -> None:
        """API/WS handler'ından test başlatma sinyali alır."""
        runner = self._get_runner(scan_id)
        runner.notify_test_start(url_ids, test_types)

    def apply_bypass(self, scan_id: str, technique: Dict[str, Any]) -> None:
        """WAF bypass tekniğini ilgili testing fazına iletir."""
        runner = self._get_runner(scan_id)
        runner.apply_bypass(technique)

    def skip_bypass(self, scan_id: str) -> None:
        """WAF bypass atlama kararını ilgili testing fazına iletir."""
        runner = self._get_runner(scan_id)
        runner.skip_bypass()

    # ------------------------------------------------------------------
    # Ana tarama akışı
    # ------------------------------------------------------------------

    async def _run_scan(self, scan_id: str, runner: ScanRunner) -> None:
        """
        Tam tarama döngüsü: Recon → Discovery → Testing → Rapor.

        Bu coroutine, start_scan() tarafından arka plan task olarak çalıştırılır.
        Hata yönetimi:
            - asyncio.CancelledError → status='stopped'
            - Diğer Exception         → status='failed'
        """
        ws = _ScanWsAdapter(self.ws_manager, scan_id)

        async with AsyncSessionLocal() as db:
            scan: Optional[Scan] = None
            try:
                # ----------------------------------------------------------------
                # Taramayı yükle
                # ----------------------------------------------------------------
                result = await db.execute(select(Scan).where(Scan.id == scan_id))
                scan = result.scalar_one_or_none()
                if scan is None:
                    logger.error("[orchestrator] Tarama bulunamadı: %s", scan_id)
                    return

                # ----------------------------------------------------------------
                # Adım 1 — RECON
                # ----------------------------------------------------------------
                runner.status = "running"
                scan.status = "running"
                scan.current_phase = "recon"
                scan.progress = 0
                await db.commit()

                await ws.broadcast(
                    ws_events.phase_started("recon", "Subdomain keşfi başladı")
                )
                await ws.broadcast(ws_events.progress(0, "recon"))

                recon_phase = ReconPhase(
                    scan_id=scan_id,
                    target=scan.target,
                    scope=scan.scope,
                    mode=scan.mode,
                    config=scan.config or {},
                    db_session=db,
                    ws_manager=ws,
                    ai_engine=self.ai_engine,
                    tool_manager=self.tool_manager,
                    pause_event=runner.pause_event,
                )
                await recon_phase.run()

                await db.commit()
                await ws.broadcast(
                    ws_events.phase_completed("recon", await self._recon_stats(scan_id, db))
                )
                await ws.broadcast(ws_events.progress(33, "recon"))

                # ----------------------------------------------------------------
                # Adım 2 — Subdomain seçim bekleme (yalnızca scope=subdomains)
                # ----------------------------------------------------------------
                if scan.scope == "subdomains":
                    scan.status = "waiting_user"
                    scan.current_phase = "recon"
                    await db.commit()

                    await ws.broadcast(
                        ws_events.notification(
                            "Subdomain Seçimi Bekleniyor",
                            "Discovery fazı için subdomainleri seçin ve onaylayın.",
                        )
                    )

                    # runner.notify_subdomain_selection() çağrılana kadar bekle
                    await runner._subdomain_selection_event.wait()

                    # Seçim yoksa is_selected=True olanları DB'den çek
                    if runner._selected_subdomain_ids:
                        targets = await self._load_targets_by_ids(
                            scan_id, runner._selected_subdomain_ids, db
                        )
                    else:
                        targets = await self._load_selected_targets(scan_id, db)

                    if not targets:
                        logger.warning(
                            "[orchestrator] Hiç subdomain seçilmedi (%s) — hedef kullanılıyor",
                            scan_id,
                        )
                        targets = [scan.target]
                else:
                    # scope=single: doğrudan hedefi kullan
                    targets = [scan.target]

                # ----------------------------------------------------------------
                # Adım 3 — DISCOVERY
                # ----------------------------------------------------------------
                runner.status = "running"
                scan.status = "running"
                scan.current_phase = "discovery"
                scan.progress = 33
                await db.commit()

                await ws.broadcast(
                    ws_events.phase_started("discovery", f"{len(targets)} hedef için URL keşfi başladı")
                )
                await ws.broadcast(ws_events.progress(33, "discovery"))

                discovery_phase = DiscoveryPhase(
                    scan_id=scan_id,
                    targets=targets,
                    mode=scan.mode,
                    config=scan.config or {},
                    db_session=db,
                    ws_manager=ws,
                    ai_engine=self.ai_engine,
                    tool_manager=self.tool_manager,
                    pause_event=runner.pause_event,
                )
                url_count = await discovery_phase.run()

                await db.commit()
                await ws.broadcast(
                    ws_events.phase_completed("discovery", {"total_urls": url_count})
                )
                await ws.broadcast(ws_events.progress(66, "discovery"))

                # ----------------------------------------------------------------
                # Adım 4 — Test başlatma bekleme
                # ----------------------------------------------------------------
                scan.status = "waiting_user"
                scan.current_phase = "discovery"
                scan.progress = 66
                await db.commit()

                await ws.broadcast(
                    ws_events.notification(
                        "Test Başlatmaya Hazır",
                        f"{url_count} URL bulundu. URL'leri ve test tiplerini seçip testi başlatın.",
                    )
                )

                # runner.notify_test_start() çağrılana kadar bekle
                await runner._test_start_event.wait()

                url_ids: List[int] = runner._test_config.get("url_ids", [])
                test_types: List[str] = runner._test_config.get("test_types", [])

                # ----------------------------------------------------------------
                # Adım 5 — TESTING
                # ----------------------------------------------------------------
                if url_ids and test_types:
                    runner.status = "running"
                    scan.status = "running"
                    scan.current_phase = "testing"
                    scan.progress = 66
                    await db.commit()

                    await ws.broadcast(
                        ws_events.phase_started(
                            "testing",
                            f"{len(url_ids)} URL, {len(test_types)} test türü",
                        )
                    )

                    testing_phase = TestingPhase(
                        scan_id=scan_id,
                        url_ids=url_ids,
                        test_types=test_types,
                        db_session=db,
                        ws_manager=ws,
                        ai_engine=self.ai_engine,
                        tool_manager=self.tool_manager,
                        pause_event=runner.pause_event,
                        mode=scan.mode,
                    )
                    runner._testing_phase = testing_phase
                    total_findings = await testing_phase.run()
                    runner._testing_phase = None

                    await db.commit()
                    await ws.broadcast(
                        ws_events.phase_completed(
                            "testing",
                            {
                                "total_findings": total_findings,
                                "urls_tested": len(url_ids),
                            },
                        )
                    )
                else:
                    logger.info(
                        "[orchestrator] Test atlandı — url_ids=%s test_types=%s",
                        url_ids,
                        test_types,
                    )

                # ----------------------------------------------------------------
                # Adım 6 — Rapor oluştur
                # ----------------------------------------------------------------
                try:
                    from utils.report_generator import generate_report  # type: ignore

                    await generate_report(scan_id, db)
                    logger.info("[orchestrator] Rapor oluşturuldu: %s", scan_id)
                except ImportError:
                    logger.debug("[orchestrator] report_generator henüz mevcut değil, atlandı.")
                except Exception as exc:
                    logger.warning("[orchestrator] Rapor oluşturma hatası: %s", exc)

                # ----------------------------------------------------------------
                # Adım 7 — Tamamlandı
                # ----------------------------------------------------------------
                runner.status = "completed"
                scan.status = "completed"
                scan.current_phase = None
                scan.progress = 100
                scan.completed_at = _utcnow()
                await db.commit()

                final_stats = await self._final_stats(scan_id, db)
                await ws.broadcast(ws_events.scan_completed(final_stats))
                await ws.broadcast(
                    ws_events.notification(
                        "Tarama Tamamlandı",
                        "{total_subdomains} subdomain, {total_urls} URL, {total_findings} bulgu".format(
                            **final_stats
                        ),
                    )
                )
                logger.info("[orchestrator] Tarama tamamlandı: %s — %s", scan_id, final_stats)

            except asyncio.CancelledError:
                # Kullanıcı stop_scan() çağırdı
                runner.status = "stopped"
                if scan is not None:
                    try:
                        scan.status = "stopped"
                        scan.updated_at = _utcnow()
                        await db.commit()
                    except Exception:
                        pass
                try:
                    await self.ws_manager.send_to_scan(scan_id, ws_events.scan_stopped())
                except Exception:
                    pass
                logger.info("[orchestrator] Tarama durduruldu: %s", scan_id)
                raise  # CancelledError yeniden fırlatılmalı

            except Exception as exc:
                runner.status = "failed"
                logger.error(
                    "[orchestrator] Tarama başarısız: %s — %s",
                    scan_id,
                    exc,
                    exc_info=True,
                )
                if scan is not None:
                    try:
                        scan.status = "failed"
                        scan.error_message = str(exc)
                        scan.updated_at = _utcnow()
                        await db.commit()
                    except Exception:
                        pass
                try:
                    await self.ws_manager.send_to_scan(
                        scan_id,
                        ws_events.scan_error(f"Tarama hatası: {exc}"),
                    )
                except Exception:
                    pass

    # ------------------------------------------------------------------
    # Yardımcı metotlar
    # ------------------------------------------------------------------

    def _get_runner(self, scan_id: str) -> ScanRunner:
        """
        ScanRunner'ı döndürür; bulunamazsa KeyError fırlatır.

        Raises:
            KeyError: Tarama aktif listede değilse.
        """
        runner = self.active_scans.get(scan_id)
        if runner is None:
            raise KeyError(f"Aktif tarama bulunamadı: {scan_id}")
        return runner

    async def _update_scan_status(self, scan_id: str, status: str) -> None:
        """DB'deki tarama durumunu günceller."""
        async with AsyncSessionLocal() as db:
            result = await db.execute(select(Scan).where(Scan.id == scan_id))
            scan = result.scalar_one_or_none()
            if scan:
                scan.status = status
                scan.updated_at = _utcnow()
                await db.commit()

    async def _load_selected_targets(
        self,
        scan_id: str,
        db: AsyncSession,
    ) -> List[str]:
        """
        DB'de is_selected=True olan subdomainlerin hostname listesini döndürür.
        """
        result = await db.execute(
            select(Subdomain.subdomain).where(
                Subdomain.scan_id == scan_id,
                Subdomain.is_selected == True,  # noqa: E712
                Subdomain.is_alive == True,       # noqa: E712
            )
        )
        return [row[0] for row in result.fetchall()]

    async def _load_targets_by_ids(
        self,
        scan_id: str,
        subdomain_ids: List[int],
        db: AsyncSession,
    ) -> List[str]:
        """
        Verilen ID listesindeki subdomainlerin hostname listesini döndürür.

        Aynı zamanda is_selected=True olarak işaretler.
        """
        result = await db.execute(
            select(Subdomain).where(
                Subdomain.scan_id == scan_id,
                Subdomain.id.in_(subdomain_ids),
            )
        )
        subs = result.scalars().all()

        targets: List[str] = []
        for sub in subs:
            sub.is_selected = True
            if sub.subdomain:
                targets.append(sub.subdomain)

        await db.commit()
        return targets

    async def _recon_stats(
        self,
        scan_id: str,
        db: AsyncSession,
    ) -> Dict[str, Any]:
        """Recon fazı tamamlanma istatistiklerini döndürür."""
        from sqlalchemy import func

        total_res = await db.execute(
            select(func.count(Subdomain.id)).where(Subdomain.scan_id == scan_id)
        )
        live_res = await db.execute(
            select(func.count(Subdomain.id)).where(
                Subdomain.scan_id == scan_id,
                Subdomain.is_alive == True,  # noqa: E712
            )
        )
        return {
            "found": total_res.scalar() or 0,
            "live": live_res.scalar() or 0,
        }

    async def _final_stats(
        self,
        scan_id: str,
        db: AsyncSession,
    ) -> Dict[str, Any]:
        """Tarama tamamlanma özet istatistiklerini döndürür."""
        from sqlalchemy import func

        sub_res = await db.execute(
            select(func.count(Subdomain.id)).where(Subdomain.scan_id == scan_id)
        )
        url_res = await db.execute(
            select(func.count(Url.id)).where(Url.scan_id == scan_id)
        )
        finding_res = await db.execute(
            select(func.count(Finding.id)).where(Finding.scan_id == scan_id)
        )
        return {
            "total_subdomains": sub_res.scalar() or 0,
            "total_urls": url_res.scalar() or 0,
            "total_findings": finding_res.scalar() or 0,
        }
