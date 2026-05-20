"""
Faz 1 — RECON: Subdomain keşfi, DNS doğrulama, HTTP probing ve WAF tespiti.

Spesifikasyon Bölüm 8.1 referans alınmıştır.

Akış (scope='subdomains'):
  1. subfinder + amass + assetfinder + crt.sh → paralel subdomain toplama
  2. Deduplikasyon
  3. dnsx  → DNS doğrulama (IP yanıtı alanlar)
  4. httpx → HTTP probing (status, title, tech, server, cdn)
  5. wafw00f → WAF tespiti (200/403 olan aktif subdomainler)
  6. AI scoring → DB güncelle + WS event

Akış (scope='single'):
  1. httpx → direkt probing
  2. wafw00f → WAF tespiti
"""

from __future__ import annotations

import asyncio
import logging
import os
import tempfile
from typing import Any, Dict, List, Optional, Tuple

import httpx as httpx_lib
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

import websocket_manager as ws_events
from ai_engine import OllamaClient, score_subdomains
from models import Subdomain
from tools import (
    AmassTool,
    AssetfinderTool,
    DnsxTool,
    HttpxTool,
    SubfinderTool,
    Wafw00fTool,
)

logger = logging.getLogger(__name__)

_CRTSH_TIMEOUT = 30.0


class ReconPhase:
    """
    Recon fazını yürüten sınıf.

    run() çağrıldığında tüm fazı tamamlar ve
    veritabanındaki Subdomain kayıtlarının listesini döndürür.
    """

    def __init__(
        self,
        scan_id: str,
        target: str,
        scope: str,
        mode: str,
        config: Optional[Dict[str, Any]],
        db_session: AsyncSession,
        ws_manager: Any,
        ai_engine: Optional[OllamaClient],
        tool_manager: Any,
        pause_event: asyncio.Event,
    ) -> None:
        self.scan_id = scan_id
        self.target = target.strip().lower()
        self.scope = scope
        self.mode = mode
        self.config = config or {}
        self.db = db_session
        self.ws_manager = ws_manager
        self.ai_engine = ai_engine
        self.tool_manager = tool_manager
        self.pause_event = pause_event

    # -----------------------------------------------------------------------
    # Yardımcılar
    # -----------------------------------------------------------------------

    async def _send(self, event: Dict[str, Any]) -> None:
        """WS event gönderir; hata olursa sessizce devam eder."""
        try:
            await self.ws_manager.send_to_scan(self.scan_id, event)
        except Exception as exc:
            logger.debug("[recon] WS send error scan=%s: %s", self.scan_id, exc)

    async def _check_pause(self) -> None:
        """Duraklama noktası; pause_event clear ise set() edilene kadar bekler."""
        if not self.pause_event.is_set():
            logger.debug("[recon] paused, waiting...")
            await self.pause_event.wait()
            logger.debug("[recon] resumed")

    def _in_scope(self, subdomain: str) -> bool:
        """Subdomainin hedef domain kapsamında olup olmadığını kontrol eder."""
        s = subdomain.strip().lower()
        return s == self.target or s.endswith("." + self.target)

    # -----------------------------------------------------------------------
    # DB yardımcıları
    # -----------------------------------------------------------------------

    async def _upsert_subdomain(
        self,
        subdomain_str: str,
        source: str,
        extra: Optional[Dict[str, Any]] = None,
    ) -> Tuple[Subdomain, bool]:
        """
        Subdomain kaydını ekler veya günceller (None değerleri atlar).

        Returns:
            (Subdomain, created: bool)
        """
        stmt = select(Subdomain).where(
            Subdomain.scan_id == self.scan_id,
            Subdomain.subdomain == subdomain_str,
        )
        result = await self.db.execute(stmt)
        sub = result.scalar_one_or_none()

        created = sub is None
        if created:
            sub = Subdomain(
                scan_id=self.scan_id,
                subdomain=subdomain_str,
                source=source,
                is_alive=True,
            )
            self.db.add(sub)

        if extra:
            for key, val in extra.items():
                if val is not None and hasattr(sub, key):
                    setattr(sub, key, val)

        await self.db.flush()
        return sub, created

    async def _get_all_subdomains(self) -> List[Subdomain]:
        result = await self.db.execute(
            select(Subdomain).where(Subdomain.scan_id == self.scan_id)
        )
        return list(result.scalars().all())

    @staticmethod
    def _sub_to_dict(sub: Subdomain) -> Dict[str, Any]:
        return {
            "id": sub.id,
            "subdomain": sub.subdomain,
            "ip_addresses": sub.ip_addresses,
            "status_code": sub.status_code,
            "title": sub.title,
            "tech_stack": sub.tech_stack,
            "server": sub.server,
            "cdn": sub.cdn,
            "waf": sub.waf,
            "is_alive": sub.is_alive,
            "source": sub.source,
        }

    # -----------------------------------------------------------------------
    # Adım 1a: Araç bazlı subdomain toplama
    # -----------------------------------------------------------------------

    async def _enum_with_tool(
        self, tool_cls: type
    ) -> List[Tuple[str, str]]:
        """
        Verilen araç sınıfıyla subdomain toplar.

        Returns:
            [(subdomain, source_name), ...] — kapsamdaki tüm subdomainler.
        """
        tool = tool_cls(pause_event=self.pause_event)
        tool_name = tool.name
        found: List[Tuple[str, str]] = []

        if not tool.is_available():
            logger.info("[recon] %s not installed, skipping", tool_name)
            return found

        await self._send(ws_events.tool_started(tool_name, self.target))
        try:
            async for result in tool.stream(self.target, self.mode):
                await self._check_pause()
                sub = result.get("subdomain", "").strip().lower()
                if sub and self._in_scope(sub):
                    found.append((sub, tool_name))
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning("[recon] %s error: %s", tool_name, exc)
            await self._send(ws_events.tool_error(tool_name, str(exc)))

        await self._send(ws_events.tool_completed(tool_name, len(found)))
        logger.info("[recon] %s → %d subdomains", tool_name, len(found))
        return found

    # -----------------------------------------------------------------------
    # Adım 1b: crt.sh
    # -----------------------------------------------------------------------

    async def _enum_crtsh(self) -> List[Tuple[str, str]]:
        """crt.sh CT log'larından subdomain toplar."""
        found: List[Tuple[str, str]] = []
        try:
            async with httpx_lib.AsyncClient(timeout=_CRTSH_TIMEOUT) as client:
                resp = await client.get(
                    f"https://crt.sh/?q=%.{self.target}&output=json",
                    headers={"User-Agent": "vulnscan-ai/1.0"},
                )
                resp.raise_for_status()
                data = resp.json()

            for item in data:
                for name in item.get("name_value", "").split("\n"):
                    sub = name.strip().lower().lstrip("*.")
                    if sub and self._in_scope(sub):
                        found.append((sub, "crtsh"))
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning("[recon] crt.sh error: %s", exc)

        logger.info("[recon] crt.sh → %d subdomains", len(found))
        return found

    # -----------------------------------------------------------------------
    # Adım 1 + 2: Paralel enum + deduplikasyon
    # -----------------------------------------------------------------------

    async def _run_enum(self) -> Dict[str, str]:
        """
        Tüm enumeration kaynaklarını paralel çalıştırır, sonuçları dedupe eder.

        Returns:
            {subdomain: ilk_bulan_source} — unique subdomain haritası.
        """
        results = await asyncio.gather(
            self._enum_with_tool(SubfinderTool),
            self._enum_with_tool(AmassTool),
            self._enum_with_tool(AssetfinderTool),
            self._enum_crtsh(),
            return_exceptions=True,
        )

        seen: Dict[str, str] = {}
        for r in results:
            if isinstance(r, Exception):
                logger.warning("[recon] enum task error: %s", r)
                continue
            for sub, source in r:
                if sub not in seen:
                    seen[sub] = source

        logger.info("[recon] enum done: %d unique subdomains", len(seen))
        return seen

    # -----------------------------------------------------------------------
    # Adım 3: DNS doğrulama (dnsx)
    # -----------------------------------------------------------------------

    async def _run_dnsx(
        self, subdomains: List[str]
    ) -> Dict[str, Dict[str, Any]]:
        """
        dnsx ile DNS doğrulama yapar.

        Returns:
            {subdomain: dns_result} — sadece IP yanıtı alanlar.
            dnsx kurulu değilse tüm subdomainleri geçerli kabul eder.
        """
        if not subdomains:
            return {}

        tool = DnsxTool(pause_event=self.pause_event)
        if not tool.is_available():
            logger.info("[recon] dnsx not installed, accepting all subdomains")
            return {s: {} for s in subdomains}

        tmp = tempfile.NamedTemporaryFile(
            mode="w", suffix=".txt", delete=False, encoding="utf-8"
        )
        try:
            tmp.write("\n".join(subdomains))
            tmp.close()

            await self._send(ws_events.tool_started("dnsx", tmp.name))
            dns_results: Dict[str, Dict[str, Any]] = {}

            async for result in tool.stream(tmp.name, self.mode):
                await self._check_pause()
                sub = result.get("subdomain", "").strip().lower()
                if sub:
                    dns_results[sub] = result

            await self._send(ws_events.tool_completed("dnsx", len(dns_results)))
            logger.info("[recon] dnsx → %d subdomains resolved", len(dns_results))
            return dns_results
        finally:
            try:
                os.unlink(tmp.name)
            except OSError:
                pass

    # -----------------------------------------------------------------------
    # Adım 4: HTTP probing (httpx tool)
    # -----------------------------------------------------------------------

    async def _run_httpx(
        self, targets: List[str]
    ) -> Dict[str, Dict[str, Any]]:
        """
        httpx ile HTTP probing yapar.

        Args:
            targets: Subdomain veya URL listesi.

        Returns:
            {input_string: http_result} — httpx'ten yanıt alanlar.
        """
        if not targets:
            return {}

        tool = HttpxTool(pause_event=self.pause_event)
        if not tool.is_available():
            logger.info("[recon] httpx not installed, skipping HTTP probing")
            return {}

        tmp = tempfile.NamedTemporaryFile(
            mode="w", suffix=".txt", delete=False, encoding="utf-8"
        )
        try:
            tmp.write("\n".join(targets))
            tmp.close()

            await self._send(ws_events.tool_started("httpx", tmp.name))
            http_results: Dict[str, Dict[str, Any]] = {}

            async for result in tool.stream(tmp.name, self.mode):
                await self._check_pause()
                sub = result.get("subdomain", "").strip().lower()
                if sub:
                    http_results[sub] = result

            await self._send(ws_events.tool_completed("httpx", len(http_results)))
            logger.info("[recon] httpx → %d subdomains alive", len(http_results))
            return http_results
        finally:
            try:
                os.unlink(tmp.name)
            except OSError:
                pass

    # -----------------------------------------------------------------------
    # Adım 5: WAF tespiti (wafw00f)
    # -----------------------------------------------------------------------

    async def _run_waf_detection(
        self, subdomains: List[Subdomain]
    ) -> None:
        """
        Aktif (200 veya 403) subdomainlere wafw00f uygular.
        Tespit edilen WAF DB'ye yazılır, WS event gönderilir.
        """
        tool = Wafw00fTool(pause_event=self.pause_event)
        if not tool.is_available():
            logger.info("[recon] wafw00f not installed, skipping WAF detection")
            return

        candidates = [
            s for s in subdomains
            if s.status_code in (200, 403) and s.subdomain
        ]
        if not candidates:
            return

        await self._send(
            ws_events.tool_started("wafw00f", f"{len(candidates)} targets")
        )
        waf_count = 0

        for sub in candidates:
            await self._check_pause()
            url = f"https://{sub.subdomain}"
            try:
                async for result in tool.stream(url, self.mode):
                    if result.get("waf_detected"):
                        waf_name = result.get("waf_name") or "Unknown"
                        sub.waf = waf_name
                        await self.db.flush()
                        waf_count += 1
                        await self._send(ws_events.waf_detected(waf_name, url))
                    break  # subdomain başına tek sonuç yeterli
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.debug("[recon] wafw00f error %s: %s", url, exc)

        await self._send(ws_events.tool_completed("wafw00f", waf_count))
        logger.info("[recon] wafw00f → %d WAF detected", waf_count)

    # -----------------------------------------------------------------------
    # Adım 6: AI scoring
    # -----------------------------------------------------------------------

    async def _run_ai_scoring(
        self, subdomains: List[Subdomain]
    ) -> None:
        """
        AI ile subdomain öncelik skorlaması yapar.
        Sonuçlar DB'ye kaydedilir ve WS event'leri gönderilir.
        AI hata verirse loglayıp devam eder; tarama durdurmaz.
        """
        if not subdomains:
            return

        sub_data = [
            {
                "subdomain": s.subdomain,
                "status_code": s.status_code,
                "tech_stack": s.tech_stack or [],
                "server": s.server,
                "waf": s.waf,
                "cdn": s.cdn,
                "title": s.title,
                "ip_addresses": s.ip_addresses or [],
            }
            for s in subdomains
        ]

        try:
            scored = await score_subdomains(sub_data, client=self.ai_engine)
        except Exception as exc:
            logger.warning("[recon] AI scoring error: %s", exc)
            return

        scored_map: Dict[str, Dict[str, Any]] = {
            item.get("subdomain", ""): item
            for item in scored
            if isinstance(item, dict)
        }

        for sub in subdomains:
            await self._check_pause()
            ai = scored_map.get(sub.subdomain)
            if not ai:
                continue

            sub.ai_score = ai.get("ai_score")
            sub.ai_analysis = ai.get("ai_analysis")
            sub.ai_tags = ai.get("ai_tags") or []
            await self.db.flush()

            if sub.ai_score is not None:
                await self._send(
                    ws_events.subdomain_ai_scored(
                        subdomain_id=sub.id,
                        score=sub.ai_score,
                        analysis=sub.ai_analysis or "",
                        tags=sub.ai_tags,
                        priority=ai.get("priority"),
                    )
                )

    # -----------------------------------------------------------------------
    # Ana akış: scope='subdomains'
    # -----------------------------------------------------------------------

    async def _run_subdomains(self) -> List[Subdomain]:
        await self._send(ws_events.phase_started("recon", "Subdomain keşfi başladı"))
        await self._send(ws_events.progress(5, "recon"))

        # --- 1+2: Paralel enum + deduplikasyon ---
        sub_source_map = await self._run_enum()
        await self._check_pause()

        if not sub_source_map:
            logger.warning("[recon] no subdomains found for %s", self.target)
            await self._send(
                ws_events.phase_completed("recon", {"found": 0, "live": 0})
            )
            return []

        await self._send(ws_events.progress(20, "recon"))

        # --- 3: DNS doğrulama ---
        all_enum = list(sub_source_map.keys())
        dns_results = await self._run_dnsx(all_enum)
        await self._check_pause()

        # Sadece DNS yanıtı alanları tut; dnsx atlandıysa hepsi geçer
        dns_live = [s for s in all_enum if s in dns_results]
        if not dns_live:
            dns_live = all_enum

        await self._send(ws_events.progress(35, "recon"))

        # --- 4: HTTP probing ---
        http_results = await self._run_httpx(dns_live)
        await self._check_pause()
        await self._send(ws_events.progress(55, "recon"))

        # --- DB kaydı ---
        for sub_str in dns_live:
            source = sub_source_map.get(sub_str, "enum")
            dns_info = dns_results.get(sub_str, {})
            http_info = http_results.get(sub_str, {})

            extra: Dict[str, Any] = {
                "is_alive": bool(http_info),
                "ip_addresses": (
                    dns_info.get("ip_addresses")
                    or http_info.get("ip_addresses")
                ),
                "status_code": http_info.get("status_code"),
                "title": http_info.get("title"),
                "tech_stack": http_info.get("tech_stack"),
                "server": http_info.get("server"),
                "cdn": http_info.get("cdn"),
            }

            sub, created = await self._upsert_subdomain(sub_str, source, extra)
            if created:
                await self._send(
                    ws_events.subdomain_found(self._sub_to_dict(sub))
                )

        await self.db.commit()
        await self._check_pause()
        await self._send(ws_events.progress(65, "recon"))

        # --- 5: WAF tespiti ---
        all_subs = await self._get_all_subdomains()
        await self._run_waf_detection(all_subs)
        await self.db.commit()
        await self._check_pause()
        await self._send(ws_events.progress(80, "recon"))

        # --- 6: AI scoring ---
        all_subs = await self._get_all_subdomains()
        await self._run_ai_scoring(all_subs)
        await self.db.commit()

        # --- Özet ---
        all_subs = await self._get_all_subdomains()
        live_count = sum(1 for s in all_subs if s.is_alive)

        await self._send(ws_events.progress(100, "recon"))
        await self._send(
            ws_events.phase_completed(
                "recon",
                {"found": len(all_subs), "live": live_count},
            )
        )
        await self._send(
            ws_events.notification(
                "Recon Tamamlandı",
                f"{len(all_subs)} subdomain bulundu, {live_count} tanesi aktif.",
            )
        )
        return all_subs

    # -----------------------------------------------------------------------
    # Ana akış: scope='single'
    # -----------------------------------------------------------------------

    async def _run_single(self) -> List[Subdomain]:
        await self._send(ws_events.phase_started("recon", "Hedef analizi başladı"))
        await self._send(ws_events.progress(10, "recon"))

        # --- httpx probing ---
        http_results = await self._run_httpx([self.target])
        await self._check_pause()
        await self._send(ws_events.progress(50, "recon"))

        http_info = http_results.get(self.target, {})
        extra: Dict[str, Any] = {
            "is_alive": bool(http_info),
            "status_code": http_info.get("status_code"),
            "title": http_info.get("title"),
            "tech_stack": http_info.get("tech_stack"),
            "server": http_info.get("server"),
            "cdn": http_info.get("cdn"),
            "ip_addresses": http_info.get("ip_addresses"),
        }

        sub, created = await self._upsert_subdomain(self.target, "httpx", extra)
        if created:
            await self._send(ws_events.subdomain_found(self._sub_to_dict(sub)))
        await self.db.commit()

        await self._check_pause()
        await self._send(ws_events.progress(70, "recon"))

        # --- WAF tespiti ---
        all_subs = await self._get_all_subdomains()
        await self._run_waf_detection(all_subs)
        await self.db.commit()

        live = 1 if bool(http_info) else 0
        await self._send(ws_events.progress(95, "recon"))
        await self._send(
            ws_events.phase_completed("recon", {"found": 1, "live": live})
        )
        await self._send(ws_events.progress(100, "recon"))
        return await self._get_all_subdomains()

    # -----------------------------------------------------------------------
    # Giriş noktası
    # -----------------------------------------------------------------------

    async def run(self) -> List[Subdomain]:
        """
        Recon fazını yürütür.

        Returns:
            Veritabanına kaydedilmiş Subdomain nesnelerinin listesi.

        Raises:
            asyncio.CancelledError: Tarama durdurulduğunda.
            Exception: Beklenmedik hatalar (loglayıp yeniden fırlatır).
        """
        logger.info(
            "[recon] start: scan=%s target=%s scope=%s mode=%s",
            self.scan_id,
            self.target,
            self.scope,
            self.mode,
        )
        try:
            if self.scope == "subdomains":
                return await self._run_subdomains()
            return await self._run_single()
        except asyncio.CancelledError:
            logger.info("[recon] cancelled: scan=%s", self.scan_id)
            raise
        except Exception as exc:
            logger.exception(
                "[recon] unexpected error: scan=%s err=%s", self.scan_id, exc
            )
            await self._send(ws_events.scan_error(f"Recon hatası: {exc}"))
            raise
