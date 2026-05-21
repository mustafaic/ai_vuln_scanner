"""
Faz 2 — DISCOVERY: URL keşfi, deduplikasyon, kategorizasyon ve AI analizi.

Spesifikasyon Bölüm 8.2 referans alınmıştır.

Her hedef için paralel araç çalışması:
  Pasif  → gau, waybackurls, paramspider
  Aktif  → katana, hakrawler, gospider
  Brute  → ffuf (mode'a göre wordlist)

Ardından:
  1. Global deduplikasyon (dedup.py)
  2. GF pattern kategorizasyonu
  3. Custom keyword + parametre analizi (categorizer.py)
  4. AI URL analizi (batch 50, ai_engine.analyze_urls)
  5. DB kaydı + WS event'leri
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, List, Optional, Set, Tuple
from urllib.parse import urlparse

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

import websocket_manager as ws_events
from ai_engine import OllamaClient, analyze_urls
from models import Subdomain, Url
from tools import (
    FfufTool,
    GauTool,
    GfTool,
    GospiderTool,
    HakrawlerTool,
    KatanaTool,
    ParamspiderTool,
    WaybackurlsTool,
)
from utils.categorizer import categorize_url, extract_params
from utils.dedup import deduplicate, normalize_url

logger = logging.getLogger(__name__)

# WS'e toplu event gönderme eşiği
_URL_BATCH_EMIT = 50

# GF'de çalıştırılacak pattern'lar
_GF_PATTERNS = [
    "xss", "sqli", "ssrf", "lfi", "rce",
    "idor", "redirect", "debug_logic", "interestingparams",
]


class DiscoveryPhase:
    """
    Discovery fazını yürüten sınıf.

    run() çağrıldığında tüm fazı tamamlar ve keşfedilen URL sayısını döndürür.
    """

    def __init__(
        self,
        scan_id: str,
        targets: List[str],
        mode: str,
        config: Optional[Dict[str, Any]],
        db_session: AsyncSession,
        ws_manager: Any,
        ai_engine: Optional[OllamaClient],
        tool_manager: Any,
        pause_event: asyncio.Event,
    ) -> None:
        self.scan_id = scan_id
        self.targets = targets
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
        try:
            await self.ws_manager.send_to_scan(self.scan_id, event)
        except Exception as exc:
            logger.debug("[discovery] WS send error scan=%s: %s", self.scan_id, exc)

    async def _check_pause(self) -> None:
        if not self.pause_event.is_set():
            logger.debug("[discovery] paused, waiting...")
            await self.pause_event.wait()

    @staticmethod
    def _ensure_url(target: str) -> str:
        """Hedef string'ine scheme ekler; yoksa https:// ekler."""
        if target.startswith(("http://", "https://")):
            return target
        return f"https://{target}"

    @staticmethod
    def _ensure_domain(target: str) -> str:
        """URL'den domain kısmını çıkarır; zaten domain ise olduğu gibi döner."""
        try:
            parsed = urlparse(target)
            return parsed.netloc or target
        except Exception:
            return target

    # -----------------------------------------------------------------------
    # Tek araç koleksiyonu
    # -----------------------------------------------------------------------

    async def _run_tool_collect(
        self,
        tool_cls: type,
        target: str,
        source_tag: str,
        **stream_kwargs: Any,
    ) -> List[Dict[str, Any]]:
        """
        Bir aracı çalıştırır ve tüm sonuçları toplar.

        Args:
            tool_cls:   Araç sınıfı.
            target:     Araca verilecek hedef string'i.
            source_tag: "_target" alanı için kaynak etiketi (hangi hedef için).
            stream_kwargs: tool.stream()'e iletilecek ek kwargs.

        Returns:
            [{"url": ..., "source": ..., "_target": target, ...}, ...]
        """
        tool = tool_cls(pause_event=self.pause_event)
        tool_name = tool.name
        results: List[Dict[str, Any]] = []

        if not tool.is_available():
            logger.info("[discovery] %s not installed, skipping", tool_name)
            return results

        await self._send(ws_events.tool_started(tool_name, target))
        try:
            async for result in tool.stream(target, self.mode, **stream_kwargs):
                await self._check_pause()
                url = result.get("url", "").strip()
                if url and url.startswith("http"):
                    result["_target"] = source_tag
                    results.append(result)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning("[discovery] %s error: %s", tool_name, exc)
            await self._send(ws_events.tool_error(tool_name, str(exc)))

        await self._send(ws_events.tool_completed(tool_name, len(results)))
        logger.info("[discovery] %s → %d URLs for %s", tool_name, len(results), target)
        return results

    # -----------------------------------------------------------------------
    # Hedef başına paralel URL toplama
    # -----------------------------------------------------------------------

    async def _collect_urls_for_target(
        self, target: str
    ) -> List[Dict[str, Any]]:
        """
        Bir hedef için tüm URL keşif araçlarını paralel çalıştırır.

        Pasif araçlar (gau, waybackurls, paramspider) domain string'i alır.
        Aktif araçlar (katana, hakrawler, gospider, ffuf) tam URL alır.
        """
        domain = self._ensure_domain(target)
        url = self._ensure_url(target)

        # stealth modda aktif crawl atlanır (spesifikasyon: passive_only_sources)
        is_passive_only = self.mode == "stealth"

        # Pasif görevler (her zaman çalışır)
        passive_tasks = [
            self._run_tool_collect(GauTool, domain, target),
            self._run_tool_collect(WaybackurlsTool, domain, target),
            self._run_tool_collect(ParamspiderTool, domain, target),
        ]

        # Aktif görevler (stealth modda atlanır)
        active_tasks = []
        if not is_passive_only:
            active_tasks = [
                self._run_tool_collect(KatanaTool, url, target),
                self._run_tool_collect(HakrawlerTool, url, target),
                self._run_tool_collect(GospiderTool, url, target),
                self._run_tool_collect(FfufTool, url, target),
            ]

        task_results = await asyncio.gather(
            *passive_tasks,
            *active_tasks,
            return_exceptions=True,
        )

        combined: List[Dict[str, Any]] = []
        for r in task_results:
            if isinstance(r, Exception):
                logger.warning("[discovery] collect task error: %s", r)
                continue
            combined.extend(r)

        return combined

    # -----------------------------------------------------------------------
    # GF pattern kategorizasyonu
    # -----------------------------------------------------------------------

    async def _run_gf_patterns(
        self, url_list: List[str]
    ) -> Dict[str, Set[str]]:
        """
        GF tool ile URL listesini her pattern için filtreler.

        Returns:
            {url: {vuln_category, ...}} — URL başına eşleşen kategoriler.
        """
        if not url_list:
            return {}

        gf = GfTool(pause_event=self.pause_event)
        if not gf.is_available():
            logger.info("[discovery] gf not installed, skipping GF patterns")
            return {}

        gf_results: Dict[str, Set[str]] = {}

        for pattern in _GF_PATTERNS:
            await self._check_pause()
            try:
                async for result in gf.stream(pattern, self.mode, urls=url_list):
                    await self._check_pause()
                    matched_url = result.get("url", "").strip()
                    vuln_cat = result.get("vuln_category", pattern)
                    if matched_url:
                        norm = normalize_url(matched_url)
                        if norm not in gf_results:
                            gf_results[norm] = set()
                        gf_results[norm].add(vuln_cat)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.warning("[discovery] gf pattern=%s error: %s", pattern, exc)

        logger.info("[discovery] GF → %d URLs matched", len(gf_results))
        return gf_results

    # -----------------------------------------------------------------------
    # DB yardımcıları
    # -----------------------------------------------------------------------

    async def _get_subdomain_id(self, target: str) -> Optional[int]:
        """Hedef string'ine karşılık gelen Subdomain kaydının ID'sini döner."""
        domain = self._ensure_domain(target).lower()
        stmt = select(Subdomain).where(
            Subdomain.scan_id == self.scan_id,
            Subdomain.subdomain == domain,
        )
        result = await self.db.execute(stmt)
        sub = result.scalar_one_or_none()
        return sub.id if sub else None

    async def _url_exists(self, url: str) -> bool:
        """URL'nin bu tarama için zaten kayıtlı olup olmadığını kontrol eder."""
        stmt = select(Url.id).where(
            Url.scan_id == self.scan_id,
            Url.url == url,
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none() is not None

    async def _save_url_batch(
        self,
        url_data_list: List[Dict[str, Any]],
        subdomain_id_cache: Dict[str, Optional[int]],
    ) -> int:
        """
        URL listesini DB'ye kaydeder. Zaten var olanları atlar.

        Returns:
            Eklenen yeni URL sayısı.
        """
        added = 0
        emit_buffer: List[Dict[str, Any]] = []

        for data in url_data_list:
            url_str = data.get("url", "")
            if not url_str:
                continue

            if await self._url_exists(url_str):
                continue

            target = data.get("_target", "")
            if target not in subdomain_id_cache:
                subdomain_id_cache[target] = await self._get_subdomain_id(target)
            sub_id = subdomain_id_cache[target]

            url_obj = Url(
                scan_id=self.scan_id,
                subdomain_id=sub_id,
                url=url_str,
                method=data.get("method", "GET"),
                source=data.get("source"),
                status_code=data.get("status_code"),
            )
            url_obj.params = data.get("params") or []
            url_obj.vuln_categories = data.get("vuln_categories") or []
            url_obj.keywords = data.get("keywords") or []
            url_obj.risk_score = data.get("risk_score", 0)
            url_obj.ai_analysis = data.get("ai_analysis")

            self.db.add(url_obj)
            await self.db.flush()
            added += 1
            data["_db_id"] = url_obj.id  # AI analizi sonrası güncelleme için sakla

            emit_buffer.append({
                "id": url_obj.id,
                "url": url_str,
                "source": url_obj.source,
                "param_count": url_obj.param_count,
                "vuln_categories": url_obj.vuln_categories,
                "keywords": url_obj.keywords,
                "risk_score": url_obj.risk_score,
            })

            # Toplu WS event: her _URL_BATCH_EMIT URL'de bir gönder
            if len(emit_buffer) >= _URL_BATCH_EMIT:
                await self._send(ws_events.url_batch(emit_buffer))
                emit_buffer.clear()

        # Kalan buffer'ı gönder
        if emit_buffer:
            await self._send(ws_events.url_batch(emit_buffer))

        return added

    # -----------------------------------------------------------------------
    # AI sonuçlarını DB'ye yaz
    # -----------------------------------------------------------------------

    async def _update_ai_results(
        self,
        url_data_list: List[Dict[str, Any]],
    ) -> None:
        """
        AI analiz sonuçlarını DB'deki mevcut URL kayıtlarına günceller.
        _save_url_batch sonrası, _run_ai_analysis tamamlandıktan çağrılır.
        """
        for data in url_data_list:
            db_id = data.get("_db_id")
            if not db_id:
                continue
            ai_analysis = data.get("ai_analysis")
            if ai_analysis is None:
                continue
            await self.db.execute(
                update(Url)
                .where(Url.id == db_id)
                .values(
                    ai_analysis=ai_analysis,
                    risk_score=data.get("risk_score", 0),
                    vuln_categories=data.get("vuln_categories") or [],
                )
            )

    # -----------------------------------------------------------------------
    # AI analizi
    # -----------------------------------------------------------------------

    async def _run_ai_analysis(
        self,
        url_data_list: List[Dict[str, Any]],
        target: str,
        tech_stack: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """
        URL listesini AI ile analiz eder; orijinal dicts'e sonuçları ekler.

        Hata durumunda orijinal listeyi değiştirmeden döndürür.
        """
        if not url_data_list:
            return url_data_list

        try:
            enriched = await analyze_urls(
                urls=url_data_list,
                target=target,
                tech_stack=tech_stack,
                scan_mode=self.mode,
                client=self.ai_engine,
            )
            # AI sonuçlarını WS ile bildir
            for item in enriched:
                url_str = item.get("url", "")
                if url_str and item.get("ai_analysis"):
                    await self._check_pause()
                    await self._send(
                        ws_events.url_ai_analyzed(
                            url_id=item.get("_db_id", 0),
                            risk_score=item.get("risk_score", 0),
                            vuln_categories=item.get("vuln_categories"),
                            ai_analysis=item.get("ai_analysis"),
                        )
                    )
            return enriched
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning("[discovery] AI analysis error: %s", exc)
            return url_data_list

    # -----------------------------------------------------------------------
    # Ana akış
    # -----------------------------------------------------------------------

    async def run(self) -> int:
        """
        Discovery fazını yürütür.

        Returns:
            Veritabanına kaydedilen toplam URL sayısı.

        Raises:
            asyncio.CancelledError: Tarama durdurulduğunda.
        """
        if not self.targets:
            logger.warning("[discovery] no targets, skipping")
            return 0

        logger.info(
            "[discovery] start: scan=%s targets=%d mode=%s",
            self.scan_id, len(self.targets), self.mode,
        )
        await self._send(ws_events.phase_started("discovery", "URL keşfi başladı"))
        await self._send(ws_events.progress(5, "discovery"))

        # ---------------------------------------------------------------
        # 1. Her hedef için paralel araç koleksiyonu
        # ---------------------------------------------------------------
        all_raw: List[Dict[str, Any]] = []

        for idx, target in enumerate(self.targets):
            await self._check_pause()
            logger.info("[discovery] collecting URLs for target: %s", target)
            raw = await self._collect_urls_for_target(target)
            all_raw.extend(raw)

            pct = 5 + int((idx + 1) / len(self.targets) * 30)
            await self._send(ws_events.progress(pct, "discovery"))

        logger.info("[discovery] collected %d raw URLs", len(all_raw))

        if not all_raw:
            await self._send(
                ws_events.phase_completed("discovery", {"total_urls": 0})
            )
            return 0

        await self._check_pause()
        await self._send(ws_events.progress(35, "discovery"))

        # ---------------------------------------------------------------
        # 2. Global deduplikasyon
        # ---------------------------------------------------------------
        raw_url_strings = [r["url"] for r in all_raw if r.get("url")]
        unique_urls = deduplicate(raw_url_strings)
        logger.info(
            "[discovery] dedup: %d raw → %d unique", len(raw_url_strings), len(unique_urls)
        )

        # İlk karşılaşılan meta verilerini sakla (source, target, method)
        url_meta: Dict[str, Dict[str, Any]] = {}
        for r in all_raw:
            norm = normalize_url(r.get("url", "").strip())
            if norm and norm not in url_meta:
                url_meta[norm] = r

        await self._send(ws_events.progress(40, "discovery"))

        # ---------------------------------------------------------------
        # 3. GF pattern kategorizasyonu
        # ---------------------------------------------------------------
        gf_results = await self._run_gf_patterns(unique_urls)
        await self._check_pause()
        await self._send(ws_events.progress(55, "discovery"))

        # ---------------------------------------------------------------
        # 4. Her URL için kategorize et
        # ---------------------------------------------------------------
        url_data_list: List[Dict[str, Any]] = []

        for url_str in unique_urls:
            meta = url_meta.get(url_str, {})
            gf_cats = list(gf_results.get(url_str, set()))
            cat = categorize_url(url_str, gf_categories=gf_cats)

            url_data_list.append({
                "url": url_str,
                "source": meta.get("source", "unknown"),
                "method": meta.get("method", "GET"),
                "_target": meta.get("_target", self.targets[0] if self.targets else ""),
                "status_code": meta.get("status_code"),
                **cat,
            })

        await self._send(ws_events.progress(65, "discovery"))

        # ---------------------------------------------------------------
        # 5. DB kaydı — önce kaydet, frontend'e hemen göster
        # ---------------------------------------------------------------
        subdomain_id_cache: Dict[str, Optional[int]] = {}
        total_added = await self._save_url_batch(url_data_list, subdomain_id_cache)
        await self.db.commit()

        logger.info("[discovery] saved %d URLs to DB", total_added)
        await self._send(ws_events.progress(70, "discovery"))

        # ---------------------------------------------------------------
        # 6. AI URL analizi — DB kaydı sonrası arka planda çalışır
        # ---------------------------------------------------------------
        # Tech stack: ilk hedefin subdomaininden al
        tech_stack = await self._get_tech_stack_for_target(
            self.targets[0] if self.targets else ""
        )
        primary_target = self._ensure_domain(
            self.targets[0] if self.targets else ""
        )

        url_data_list = await self._run_ai_analysis(
            url_data_list, primary_target, tech_stack
        )
        await self._check_pause()

        # AI sonuçlarını DB'de güncelle
        await self._update_ai_results(url_data_list)
        await self.db.commit()

        await self._send(ws_events.progress(100, "discovery"))
        await self._send(
            ws_events.phase_completed(
                "discovery",
                {"total_urls": total_added, "unique_found": len(unique_urls)},
            )
        )
        await self._send(
            ws_events.notification(
                "Discovery Tamamlandı",
                f"{total_added} URL keşfedildi, kategorize edildi.",
            )
        )
        return total_added

    # -----------------------------------------------------------------------
    # Tech stack yardımcısı
    # -----------------------------------------------------------------------

    async def _get_tech_stack_for_target(
        self, target: str
    ) -> Optional[List[str]]:
        """Hedef subdomainin tech_stack bilgisini DB'den alır."""
        domain = self._ensure_domain(target).lower()
        try:
            stmt = select(Subdomain).where(
                Subdomain.scan_id == self.scan_id,
                Subdomain.subdomain == domain,
            )
            result = await self.db.execute(stmt)
            sub = result.scalar_one_or_none()
            return sub.tech_stack if sub else None
        except Exception:
            return None
