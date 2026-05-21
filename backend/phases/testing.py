"""
Testing fazı — Spesifikasyon Bölüm 8.3.

Akış:
  1. URL listesi üzerinde sıralı döngü
  2. Her URL için WAF kontrolü (cache veya wafw00f)
  3. WAF varsa → AI'dan bypass öneri iste → kullanıcı onayı bekle (asyncio.Event)
  4. test_types döngüsü → doğru tool'u çalıştır
  5. Her bulgu için AI analizi (analyze_finding) → DB kayıt → WS event
  6. apply_bypass / skip_bypass dışarıdan çağrılır (WebSocket handler tarafından)
"""

from __future__ import annotations

import asyncio
import logging
import os
import tempfile
from typing import Any, Dict, List, Optional, Set, Tuple

import httpx as httpx_lib
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

import websocket_manager as ws_events
from ai_engine import analyze_finding, suggest_waf_bypass
from models import Finding, Subdomain, Url
from tools.dalfox import DalfoxTool
from tools.nuclei import NucleiTool
from tools.sqlmap_tool import SqlmapTool
from tools.wafw00f_tool import Wafw00fTool

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Sabitler
# ---------------------------------------------------------------------------

BYPASS_TIMEOUT: float = 300.0  # Kullanıcı bypass kararı için bekleme (saniye)

_NUCLEI_TAGS: Dict[str, str] = {
    "lfi": "lfi",
    "ssrf": "ssrf",
    "redirect": "redirect",
    "nuclei": "cve,misconfig,exposure,default-login",
}

# WAF bypass önerisi için temsili payload'lar
_REPRESENTATIVE_PAYLOADS: Dict[str, str] = {
    "xss": "<script>alert(1)</script>",
    "sqli": "' OR 1=1--",
    "lfi": "../../../../etc/passwd",
    "ssrf": "http://169.254.169.254/latest/meta-data/",
    "redirect": "https://evil.example.com",
    "nuclei": "test_payload",
}

_REDIRECT_CANARY = "https://evil.vulnscan.internal"


# ---------------------------------------------------------------------------
# TestingPhase
# ---------------------------------------------------------------------------


class TestingPhase:
    """
    Zafiyet test fazını yönetir.

    Parametreler:
        scan_id:      Mevcut tarama ID'si.
        url_ids:      Test edilecek URL ID'leri listesi.
        test_types:   Çalıştırılacak test türleri (örn. ["xss", "sqli", "nuclei"]).
        db_session:   SQLAlchemy AsyncSession.
        ws_manager:   WebSocket yayın yöneticisi.
        ai_engine:    AI istemci nesnesi (ai_engine fonksiyonlarına geçilir).
        tool_manager: Tool availability kontrolü için yönetici.
        pause_event:  asyncio.Event — set()=çalışıyor, clear()=durduruldu.
        mode:         "normal" veya "stealth".
    """

    def __init__(
        self,
        scan_id: int,
        url_ids: List[int],
        test_types: List[str],
        db_session: AsyncSession,
        ws_manager: Any,
        ai_engine: Any,
        tool_manager: Any,
        pause_event: asyncio.Event,
        mode: str = "normal",
    ) -> None:
        self.scan_id = scan_id
        self.url_ids = url_ids
        self.test_types = test_types
        self.db_session = db_session
        self.ws_manager = ws_manager
        self.ai_engine = ai_engine
        self.tool_manager = tool_manager
        self.pause_event = pause_event
        self.mode = mode

        # WAF bypass koordinasyonu
        self._bypass_event: asyncio.Event = asyncio.Event()
        self._bypass_technique: Optional[Dict[str, Any]] = None  # seçilen teknik veya None
        self._bypass_skip: bool = False  # kullanıcı "atla" seçtiyse True

        # {subdomain_id: waf_name or None} — fazın ömrü boyunca önbellek
        self._waf_cache: Dict[int, Optional[str]] = {}

    # ------------------------------------------------------------------
    # Dışarıdan çağrılan metotlar (WebSocket handler'ı tarafından)
    # ------------------------------------------------------------------

    def apply_bypass(self, technique: Dict[str, Any]) -> None:
        """
        Kullanıcı bir bypass tekniği onayladığında çağrılır.

        Args:
            technique: AI'ın önerdiği bypass teknik dict'i
                       (name, description, example_payload, tool_flags, …).
        """
        self._bypass_technique = technique
        self._bypass_skip = False
        self._bypass_event.set()

    def skip_bypass(self) -> None:
        """Kullanıcı bypass'ı atlamayı seçtiğinde çağrılır."""
        self._bypass_technique = None
        self._bypass_skip = True
        self._bypass_event.set()

    # ------------------------------------------------------------------
    # Yardımcı — duraklatma
    # ------------------------------------------------------------------

    async def _check_pause(self) -> None:
        """Tarama duraklatılmışsa devam edilene kadar bekler."""
        await self.pause_event.wait()

    # ------------------------------------------------------------------
    # WAF kontrolü
    # ------------------------------------------------------------------

    async def _get_waf_for_url(self, url_obj: Url) -> Optional[str]:
        """
        URL'in bağlı olduğu subdomain için WAF adını döndürür.

        Önce subdomain kaydına bakar; kayıtta yoksa veya subdomain
        ilişkisi yoksa wafw00f ile canlı kontrol yapar.

        Returns:
            WAF adı (örn. "Cloudflare") veya None.
        """
        subdomain_id: Optional[int] = getattr(url_obj, "subdomain_id", None)

        # Önbellekte varsa döndür
        if subdomain_id is not None and subdomain_id in self._waf_cache:
            return self._waf_cache[subdomain_id]

        # Subdomain kaydından WAF bilgisi
        if subdomain_id is not None:
            result = await self.db_session.execute(
                select(Subdomain).where(Subdomain.id == subdomain_id)
            )
            sub: Optional[Subdomain] = result.scalar_one_or_none()
            if sub is not None:
                waf_name: Optional[str] = getattr(sub, "waf", None) or None
                if waf_name:
                    self._waf_cache[subdomain_id] = waf_name
                    return waf_name

        # Canlı wafw00f taraması
        waf_name = await self._run_wafw00f(str(url_obj.url))
        if subdomain_id is not None:
            self._waf_cache[subdomain_id] = waf_name
        return waf_name

    async def _run_wafw00f(self, url_str: str) -> Optional[str]:
        """
        wafw00f aracını çalıştırır ve tespit edilen WAF adını döndürür.

        Returns:
            WAF adı veya None.
        """
        try:
            tool = Wafw00fTool(pause_event=self.pause_event)
            if not tool.is_available():
                return None
            async for line in tool.stream(url_str):
                await self._check_pause()
                result = tool.parse_line(line)
                if result and result.get("waf_detected"):
                    return result.get("waf_name")
        except Exception as exc:
            logger.warning("[testing] wafw00f hatası (%s): %s", url_str, exc)
        return None

    # ------------------------------------------------------------------
    # WAF bypass koordinasyonu
    # ------------------------------------------------------------------

    async def _wait_for_bypass(
        self,
        url_str: str,
        url_id: int,
        waf_name: str,
        test_type: str,
    ) -> Optional[Dict[str, Any]]:
        """
        WAF bypass kararı için kullanıcıyı bekler (maksimum BYPASS_TIMEOUT saniye).

        Süreç:
        1. AI'dan bypass teknikleri öner.
        2. WS üzerinden "waf_bypass_needed" eventi yayınla.
        3. asyncio.Event ile kullanıcı kararını bekle.
        4. Karar gelince veya timeout olunca tekniği (ya da None) döndür.

        Returns:
            Seçilen bypass teknik dict'i veya None (atla / timeout).
        """
        representative_payload = _REPRESENTATIVE_PAYLOADS.get(test_type, "test_payload")

        # AI'dan bypass önerileri al
        bypass_suggestions: Dict[str, Any] = {}
        try:
            bypass_suggestions = await suggest_waf_bypass(
                waf_name=waf_name,
                url=url_str,
                vuln_type=test_type,
                blocked_payload=representative_payload,
                client=self.ai_engine,
            )
        except Exception as exc:
            logger.warning("[testing] suggest_waf_bypass hatası: %s", exc)

        # WS olayı — kullanıcıya göster
        await self.ws_manager.broadcast(
            ws_events.waf_bypass_needed(
                scan_id=self.scan_id,
                url=url_str,
                url_id=url_id,
                waf_name=waf_name,
                test_type=test_type,
                suggestions=bypass_suggestions,
            )
        )

        # Bypass event'ini sıfırla ve bekle
        self._bypass_event.clear()
        self._bypass_technique = None
        self._bypass_skip = False

        try:
            await asyncio.wait_for(
                self._bypass_event.wait(),
                timeout=BYPASS_TIMEOUT,
            )
        except asyncio.TimeoutError:
            logger.info(
                "[testing] WAF bypass timeout (%ss) — URL atlanıyor: %s",
                BYPASS_TIMEOUT,
                url_str,
            )
            return None

        if self._bypass_skip:
            return None
        return self._bypass_technique

    # ------------------------------------------------------------------
    # Tool çalıştırıcılar
    # ------------------------------------------------------------------

    async def _run_dalfox(
        self,
        url_str: str,
        bypass_technique: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Dalfox ile XSS taraması yapar.

        Args:
            bypass_technique: WAF bypass tekniği (None ise bypass yok).

        Returns:
            Dalfox bulgu listesi.
        """
        findings: List[Dict[str, Any]] = []
        try:
            use_bypass = bypass_technique is not None
            tool_flags: List[str] = []
            if bypass_technique:
                tool_flags = bypass_technique.get("tool_flags", [])

            tool = DalfoxTool(pause_event=self.pause_event)
            if not tool.is_available():
                logger.warning("[testing] dalfox mevcut değil, XSS atlanıyor.")
                return findings

            async for line in tool.stream(url_str, waf_bypass=use_bypass, extra_flags=tool_flags):
                await self._check_pause()
                result = tool.parse_line(line)
                if result:
                    findings.append(result)
        except Exception as exc:
            logger.error("[testing] dalfox hatası (%s): %s", url_str, exc)
        return findings

    async def _run_sqlmap(
        self,
        url_str: str,
        bypass_technique: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Sqlmap ile SQLi taraması yapar.

        Returns:
            Sqlmap bulgu listesi.
        """
        findings: List[Dict[str, Any]] = []
        try:
            tool_flags: List[str] = []
            if bypass_technique:
                tool_flags = bypass_technique.get("tool_flags", [])
                # Bypass varsa agresif mod
                if "--level" not in " ".join(tool_flags):
                    tool_flags = ["--level=3", "--risk=2"] + tool_flags

            tool = SqlmapTool(pause_event=self.pause_event)
            if not tool.is_available():
                logger.warning("[testing] sqlmap mevcut değil, SQLi atlanıyor.")
                return findings

            async for line in tool.stream(url_str, extra_flags=tool_flags):
                await self._check_pause()
                result = tool.parse_line(line)
                if result:
                    findings.append(result)
        except Exception as exc:
            logger.error("[testing] sqlmap hatası (%s): %s", url_str, exc)
        return findings

    async def _run_nuclei(
        self,
        url_str: str,
        test_type: str,
    ) -> List[Dict[str, Any]]:
        """
        Nuclei ile template tabanlı tarama yapar.

        Args:
            test_type: "lfi", "ssrf", "redirect" veya "nuclei".

        Returns:
            Nuclei bulgu listesi.
        """
        findings: List[Dict[str, Any]] = []
        tags = _NUCLEI_TAGS.get(test_type, test_type)
        try:
            tool = NucleiTool(pause_event=self.pause_event)
            if not tool.is_available():
                logger.warning("[testing] nuclei mevcut değil, %s atlanıyor.", test_type)
                return findings

            async for line in tool.stream(url_str, tags=tags):
                await self._check_pause()
                result = tool.parse_line(line)
                if result:
                    findings.append(result)
        except Exception as exc:
            logger.error("[testing] nuclei hatası (%s, %s): %s", url_str, test_type, exc)
        return findings

    async def _check_open_redirect(self, url_str: str) -> List[Dict[str, Any]]:
        """
        Her query parametresine canary değeri ekleyerek open redirect kontrol eder.

        httpx Python kütüphanesiyle follow_redirects=True ile istek atar;
        nihai URL canary domain'ini içeriyorsa bulgu üretir.

        Returns:
            Open redirect bulgu listesi.
        """
        from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

        findings: List[Dict[str, Any]] = []
        try:
            parsed = urlparse(url_str)
            params = parse_qs(parsed.query, keep_blank_values=True)
            if not params:
                return findings

            async with httpx_lib.AsyncClient(
                follow_redirects=True,
                timeout=15.0,
                verify=False,
            ) as client:
                for param_name in params:
                    # Sadece bu parametreyi canary ile değiştir
                    test_params = dict(params)
                    test_params[param_name] = [_REDIRECT_CANARY]
                    test_query = urlencode(test_params, doseq=True)
                    test_url = urlunparse(
                        (
                            parsed.scheme,
                            parsed.netloc,
                            parsed.path,
                            parsed.params,
                            test_query,
                            "",
                        )
                    )
                    try:
                        resp = await client.get(test_url)
                        final_url = str(resp.url)
                        if "vulnscan.internal" in final_url:
                            findings.append(
                                {
                                    "vuln_type": "redirect",
                                    "severity": "medium",
                                    "title": "Open Redirect",
                                    "payload": _REDIRECT_CANARY,
                                    "evidence": f"Redirected to: {final_url}",
                                    "param": param_name,
                                    "url": test_url,
                                    "source": "custom_redirect_checker",
                                    "raw": f"GET {test_url} -> {final_url}",
                                }
                            )
                    except Exception:
                        pass  # Bağlantı hataları sessizce geç
        except Exception as exc:
            logger.warning("[testing] open redirect kontrol hatası (%s): %s", url_str, exc)
        return findings

    # ------------------------------------------------------------------
    # Test türü yönlendirici
    # ------------------------------------------------------------------

    async def _run_for_test_type(
        self,
        url_str: str,
        test_type: str,
        bypass_technique: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """
        test_type'a göre doğru aracı çalıştırır ve ham bulgu listesi döndürür.

        Eşleme:
            "xss"      → dalfox
            "sqli"     → sqlmap
            "lfi"      → nuclei (tags=lfi)
            "ssrf"     → nuclei (tags=ssrf)
            "redirect" → _check_open_redirect + nuclei (tags=redirect)
            "idor"     → nuclei (tags=idor)
            "nuclei"   → nuclei (tags=cve,misconfig,exposure,default-login)
            diğer      → nuclei (tags=<test_type>)

        Returns:
            Ham bulgu dict listesi.
        """
        if test_type == "xss":
            return await self._run_dalfox(url_str, bypass_technique)

        if test_type == "sqli":
            return await self._run_sqlmap(url_str, bypass_technique)

        if test_type == "redirect":
            redirect_findings = await self._check_open_redirect(url_str)
            nuclei_findings = await self._run_nuclei(url_str, "redirect")
            return redirect_findings + nuclei_findings

        # lfi, ssrf, idor, nuclei veya diğer test türleri
        return await self._run_nuclei(url_str, test_type)

    # ------------------------------------------------------------------
    # Bulgu işleme
    # ------------------------------------------------------------------

    async def _process_finding(
        self,
        raw: Dict[str, Any],
        url_obj: Url,
        test_type: str,
        bypass_technique: Optional[Dict[str, Any]],
        waf_name: Optional[str],
    ) -> None:
        """
        Ham bulguyu AI ile analiz eder, DB'ye kaydeder ve WS eventi yayınlar.

        Adımlar:
        1. analyze_finding() — gerçek zafiyet mi kontrol et
        2. Finding kaydı oluştur (DB)
        3. "new_finding" WS eventi yayınla
        """
        await self._check_pause()

        # AI analizi için gerekli alanları hazırla
        finding_input: Dict[str, Any] = {
            "vuln_type": raw.get("vuln_type", test_type),
            "url": raw.get("url", str(url_obj.url)),
            "payload": raw.get("payload", ""),
            "tool_output": raw.get("evidence", ""),
            "request_raw": raw.get("raw", ""),
            "response_snippet": raw.get("evidence", ""),
        }
        if bypass_technique:
            finding_input["bypass_technique"] = bypass_technique.get("name", "")
        if waf_name:
            finding_input["waf_name"] = waf_name

        ai_analysis: Dict[str, Any] = {}
        try:
            ai_analysis = await analyze_finding(
                finding=finding_input,
                client=self.ai_engine,
            )
        except Exception as exc:
            logger.warning("[testing] analyze_finding hatası: %s", exc)

        # AI false positive diyorsa kayıt oluşturmayı atla
        is_real = ai_analysis.get("is_real_vulnerability", True)
        false_positive_risk = ai_analysis.get("false_positive_risk", "low")
        if not is_real and false_positive_risk == "high":
            logger.info(
                "[testing] False positive atlandı: %s @ %s",
                finding_input["vuln_type"],
                finding_input["url"],
            )
            return

        # Severity: AI önerisi yoksa tool çıktısını kullan
        severity = (
            ai_analysis.get("severity")
            or raw.get("severity", "info")
        )

        # ai_confidence: string ("high"/"medium"/"low") → int (0-100)
        _CONF_MAP: Dict[str, int] = {"high": 90, "medium": 60, "low": 30}
        conf_raw = ai_analysis.get("confidence", "medium")
        ai_confidence_val: Optional[int] = (
            _CONF_MAP.get(str(conf_raw).lower())
            if isinstance(conf_raw, str)
            else (int(conf_raw) if conf_raw is not None else None)
        )

        # ai_analysis metnini oluştur (exploitability + impact + fix)
        _analysis_parts: List[str] = []
        if ai_analysis.get("exploitability"):
            _analysis_parts.append(f"Exploitability: {ai_analysis['exploitability']}")
        if ai_analysis.get("impact"):
            _analysis_parts.append(f"Impact: {ai_analysis['impact']}")
        if ai_analysis.get("fix_recommendation"):
            _analysis_parts.append(f"Fix: {ai_analysis['fix_recommendation']}")
        ai_analysis_text: Optional[str] = "\n".join(_analysis_parts) or None

        # ai_poc: poc_steps listesini düz metin olarak sakla
        poc_steps = ai_analysis.get("poc_steps")
        ai_poc_text: Optional[str] = None
        if poc_steps:
            if isinstance(poc_steps, list):
                ai_poc_text = "\n".join(str(s) for s in poc_steps)
            else:
                ai_poc_text = str(poc_steps)

        # DB kaydı — yalnızca Finding modelinde var olan alanlar kullanılır
        finding = Finding(
            scan_id=self.scan_id,
            url_id=url_obj.id,
            vuln_type=finding_input["vuln_type"],
            severity=severity,
            title=raw.get("title", finding_input["vuln_type"].upper()),
            payload=finding_input["payload"],
            evidence=finding_input["tool_output"],
            request_raw=finding_input.get("request_raw", ""),
            response_snippet=finding_input.get("response_snippet", ""),
            tool_used=raw.get("source", "unknown"),
            ai_confidence=ai_confidence_val,
            ai_analysis=ai_analysis_text,
            ai_poc=ai_poc_text,
            waf_bypassed=bypass_technique is not None,
            bypass_technique=bypass_technique.get("name") if bypass_technique else None,
        )
        self.db_session.add(finding)
        await self.db_session.flush()  # ID al

        # WS eventi
        await self.ws_manager.broadcast(
            ws_events.new_finding(
                scan_id=self.scan_id,
                finding_id=finding.id,
                url=finding_input["url"],
                vuln_type=finding_input["vuln_type"],
                severity=severity,
                title=finding.title,
                confidence=ai_confidence_val,
                is_real=is_real,
                payload=finding_input["payload"],
                evidence=finding_input["tool_output"],
                fix_recommendation=ai_analysis.get("fix_recommendation"),
            )
        )

        logger.info(
            "[testing] Bulgu kaydedildi: %s (%s) @ %s",
            finding_input["vuln_type"],
            severity,
            finding_input["url"],
        )

    # ------------------------------------------------------------------
    # Ana çalıştırma metodu
    # ------------------------------------------------------------------

    async def run(self) -> int:
        """
        Tüm testing fazını yürütür.

        Akış:
            - URL'leri DB'den yükle
            - Her URL için:
                1. Pause kontrolü
                2. WAF kontrolü
                3. WAF varsa → bypass koordinasyonu (test_type başına bir kez)
                4. Her test_type için:
                    a. Aracı çalıştır
                    b. Her bulguyu işle (_process_finding)
            - Commit
            - Tamamlandı eventi

        Returns:
            Toplam kaydedilen bulgu sayısı.
        """
        total_findings = 0
        url_count = len(self.url_ids)

        # İlerleme eventi — başlangıç
        await self.ws_manager.broadcast(
            ws_events.phase_progress(
                scan_id=self.scan_id,
                phase="testing",
                progress=0,
                message=f"Testing fazı başladı — {url_count} URL, {len(self.test_types)} test türü",
            )
        )

        # URL nesnelerini DB'den yükle
        result = await self.db_session.execute(
            select(Url).where(Url.id.in_(self.url_ids))
        )
        url_objects: List[Url] = list(result.scalars().all())

        if not url_objects:
            logger.warning("[testing] Hiç URL bulunamadı — url_ids: %s", self.url_ids)
            await self.ws_manager.broadcast(
                ws_events.phase_complete(
                    scan_id=self.scan_id,
                    phase="testing",
                    summary={"total_findings": 0, "urls_tested": 0},
                )
            )
            return 0

        for idx, url_obj in enumerate(url_objects):
            await self._check_pause()

            url_str = str(url_obj.url)
            url_findings_count = 0

            # Durum eventi
            await self.ws_manager.broadcast(
                ws_events.phase_progress(
                    scan_id=self.scan_id,
                    phase="testing",
                    progress=int((idx / url_count) * 90),
                    message=f"Test ediliyor: {url_str}",
                )
            )

            # WAF kontrolü
            waf_name: Optional[str] = None
            try:
                waf_name = await self._get_waf_for_url(url_obj)
            except Exception as exc:
                logger.warning("[testing] WAF kontrol hatası (%s): %s", url_str, exc)

            if waf_name:
                await self.ws_manager.broadcast(
                    ws_events.waf_detected(
                        scan_id=self.scan_id,
                        url=url_str,
                        waf_name=waf_name,
                    )
                )
                logger.info("[testing] WAF tespit edildi: %s @ %s", waf_name, url_str)

            # Her test türü için WAF bypass kararını al (URL başına önbellek)
            # bypass_decisions: {test_type: technique_or_None}
            bypass_decisions: Dict[str, Optional[Dict[str, Any]]] = {}

            for test_type in self.test_types:
                await self._check_pause()

                # WAF varsa bypass koordinasyonu
                bypass_technique: Optional[Dict[str, Any]] = None
                if waf_name:
                    if test_type not in bypass_decisions:
                        bypass_technique = await self._wait_for_bypass(
                            url_str=url_str,
                            url_id=url_obj.id,
                            waf_name=waf_name,
                            test_type=test_type,
                        )
                        bypass_decisions[test_type] = bypass_technique
                    else:
                        bypass_technique = bypass_decisions[test_type]

                # Aracı çalıştır
                try:
                    raw_findings = await self._run_for_test_type(
                        url_str=url_str,
                        test_type=test_type,
                        bypass_technique=bypass_technique,
                    )
                except Exception as exc:
                    logger.error(
                        "[testing] _run_for_test_type hatası (%s, %s): %s",
                        url_str,
                        test_type,
                        exc,
                    )
                    raw_findings = []

                # Bulguları işle
                for raw in raw_findings:
                    await self._check_pause()
                    try:
                        await self._process_finding(
                            raw=raw,
                            url_obj=url_obj,
                            test_type=test_type,
                            bypass_technique=bypass_technique,
                            waf_name=waf_name,
                        )
                        url_findings_count += 1
                        total_findings += 1
                    except Exception as exc:
                        logger.error(
                            "[testing] _process_finding hatası (%s): %s",
                            url_str,
                            exc,
                        )

            logger.info(
                "[testing] URL tamamlandı (%d/%d): %s — %d bulgu",
                idx + 1,
                url_count,
                url_str,
                url_findings_count,
            )

        # Tüm değişiklikleri kalıcı yap
        await self.db_session.commit()

        # Tamamlandı eventi
        await self.ws_manager.broadcast(
            ws_events.phase_progress(
                scan_id=self.scan_id,
                phase="testing",
                progress=100,
                message="Testing fazı tamamlandı.",
            )
        )
        await self.ws_manager.broadcast(
            ws_events.phase_complete(
                scan_id=self.scan_id,
                phase="testing",
                summary={
                    "total_findings": total_findings,
                    "urls_tested": len(url_objects),
                    "test_types": self.test_types,
                },
            )
        )

        logger.info(
            "[testing] Tamamlandı — %d URL, %d bulgu",
            len(url_objects),
            total_findings,
        )
        return total_findings
