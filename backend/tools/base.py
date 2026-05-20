"""
Tum arac wrapper'lari icin temel sinif (BaseTool).

Her araç:
  1. BaseTool'dan turetilir
  2. name ve binary class-level attribute'larini tanimlar
  3. build_command() metodunu implement eder
  4. Opsiyonel: parse_line() ile ham ciktiyi sozluge cevirir

Pause mekanizmasi:
    pause_event.set()   -> arac calisir
    pause_event.clear() -> arac bir sonraki satiri yield etmeden once bekler
    Dis taraf (scan_orchestrator) bu event'i yonetir.
"""

from __future__ import annotations

import asyncio
import logging
import os
import shutil
import sys
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, AsyncGenerator, Dict, List, Optional

from config import SCAN_MODES, settings

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# PATH yardimcisi
# ---------------------------------------------------------------------------


def _build_run_env() -> Dict[str, str]:
    """
    Subproccess icin ortam sozlugu doner.

    config.py basladiginda os.environ'u zaten gunceller; bu fonksiyon
    sadece guvenli bir kopya alir ve Go binary yollarini garantiler.
    """
    env = os.environ.copy()
    extra = [
        str(Path.home() / "go" / "bin"),
        "/usr/local/go/bin",
        settings.TOOLS_GO_PATH,
    ]
    current = env.get("PATH", "")
    for p in reversed(extra):
        if p and p not in current:
            env["PATH"] = p + os.pathsep + env["PATH"]
    return env


# ---------------------------------------------------------------------------
# BaseTool
# ---------------------------------------------------------------------------


class BaseTool(ABC):
    """
    Tum arac wrapper'lari icin temel sinif.

    Subclass zorunlulukları:
        name    : str   — arac adi (kucuk harf, tire ile, ornek: 'subfinder')
        binary  : str   — PATH'te aranacak binary adi
        build_command() — somut implementasyon

    Opsiyonel override:
        parse_line()    — ham cikti satirini yapılandirmak icin
    """

    name: str = "base"
    binary: str = ""

    def __init__(self, pause_event: Optional[asyncio.Event] = None) -> None:
        """
        Args:
            pause_event: Dis taraftan verilen asyncio.Event.
                         None ise yeni bir Event olusturulur (baslangicta set).
        """
        if pause_event is None:
            self.pause_event = asyncio.Event()
            self.pause_event.set()
        else:
            self.pause_event = pause_event
        self._proc: Optional[asyncio.subprocess.Process] = None

    # ------------------------------------------------------------------
    # Soyut metotlar
    # ------------------------------------------------------------------

    @abstractmethod
    def build_command(
        self,
        target: str,
        mode: str = "normal",
        **kwargs: Any,
    ) -> List[str]:
        """
        Calistirilacak komut satirini olusturur.

        Args:
            target: Hedef domain, URL, IP veya dosya yolu.
            mode:   'stealth' | 'normal' | 'aggressive'
            kwargs: Araça özgü ek parametreler (wordlist, output_file, vb.)

        Returns:
            asyncio.create_subprocess_exec'e gecilecek liste.
        """

    # ------------------------------------------------------------------
    # Cikti parse — override edilebilir
    # ------------------------------------------------------------------

    def parse_line(self, line: str) -> Optional[Dict[str, Any]]:
        """
        Ham cikti satirini yapilandirmak icin kullanilir.

        Varsayilan implementasyon ham satiri {'line': ...} olarak sarer.
        Subclass'lar bu metodu JSON parse, regex vb. icin override eder.

        Returns:
            Yapilandirilmis sozluk veya None (satir atlanmali).
        """
        return {"line": line}

    # ------------------------------------------------------------------
    # Kullanilabilirlik
    # ------------------------------------------------------------------

    def is_available(self) -> bool:
        """
        Binary'nin PATH'te mevcut olup olmadigini kontrol eder.

        Returns:
            True -> kullanilabilir, False -> kurulu degil.
        """
        env = _build_run_env()
        return shutil.which(self.binary, path=env.get("PATH")) is not None

    # ------------------------------------------------------------------
    # Dusuk seviye: ham satir generator
    # ------------------------------------------------------------------

    async def run(
        self,
        args: List[str],
        cwd: Optional[str] = None,
        env: Optional[Dict[str, str]] = None,
    ) -> AsyncGenerator[str, None]:
        """
        Verilen komut ile süreci baslatir ve stdout satirlarini yield eder.

        Her satir yield edilmeden once pause_event kontrol edilir:
        event cleared (paused) ise set olana kadar bekler.

        Islem tamamlaninca veya iptal edilince temizlik yapilir.

        Args:
            args: Calistirilacak komut listesi (binary + argümanlar).
            cwd:  Calisma dizini (None -> miras alinir).
            env:  Ortam sozlugu (None -> _build_run_env() kullanilir).

        Yields:
            Tek tek stdout satirlari (bos satirlar atlanir).
        """
        if env is None:
            env = _build_run_env()

        logger.debug("[%s] Calistiriliyor: %s", self.name, " ".join(args))

        try:
            proc = await asyncio.create_subprocess_exec(
                *args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
                cwd=cwd,
            )
        except FileNotFoundError:
            logger.error(
                "[%s] Binary bulunamadi: %s — once kurun veya PATH'i kontrol edin",
                self.name,
                args[0] if args else "?",
            )
            return
        except Exception as exc:
            logger.error("[%s] Proses baslatma hatasi: %s", self.name, exc)
            return

        self._proc = proc
        # Stderr'i arka planda bitir; buffer dolup deadlock olusmasin
        stderr_task: asyncio.Task = asyncio.create_task(
            proc.stderr.read()
        )

        try:
            async for raw_line in proc.stdout:
                # Pause noktasi — event cleared ise bekle
                if not self.pause_event.is_set():
                    logger.debug("[%s] Duraklatildi, devam bekleniyor...", self.name)
                    await self.pause_event.wait()
                    logger.debug("[%s] Devam ediyor", self.name)

                line = raw_line.decode("utf-8", errors="replace").rstrip()
                if line:
                    yield line

        except asyncio.CancelledError:
            logger.debug("[%s] Iptal edildi", self.name)
            raise

        finally:
            self._proc = None
            # Surec hala calısıyorsa sonlandir
            if proc.returncode is None:
                try:
                    proc.kill()
                except (ProcessLookupError, OSError):
                    pass
            try:
                await asyncio.wait_for(proc.wait(), timeout=5.0)
            except asyncio.TimeoutError:
                pass

            # Stderr'i topla ve kaydet
            try:
                stderr_bytes = await asyncio.wait_for(stderr_task, timeout=2.0)
                rc = proc.returncode
                if rc not in (0, 1, None) and stderr_bytes:
                    logger.debug(
                        "[%s] rc=%d stderr=%s",
                        self.name,
                        rc,
                        stderr_bytes.decode("utf-8", errors="replace")[:300],
                    )
            except (asyncio.TimeoutError, Exception):
                pass

    # ------------------------------------------------------------------
    # Yuksek seviye: yapilandirilmis sonuc generator
    # ------------------------------------------------------------------

    async def stream(
        self,
        target: str,
        mode: str = "normal",
        **kwargs: Any,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Yuksek seviye arayuz: build_command + run + parse_line zinciri.

        Binary mevcut degilse nothing yield eder ve hatay loglar.

        Args:
            target: Araça verilecek hedef.
            mode:   Tarama modu.
            kwargs: build_command'a iletilecek ek parametreler.

        Yields:
            parse_line()'in None olmayan donus degerlerini.
        """
        if not self.is_available():
            logger.warning("[%s] Kurulu degil, stream atlaniyor", self.name)
            return

        args = self.build_command(target, mode, **kwargs)
        async for line in self.run(args):
            result = self.parse_line(line)
            if result is not None:
                yield result

    # ------------------------------------------------------------------
    # Proses kontrolu
    # ------------------------------------------------------------------

    def kill(self) -> None:
        """
        Mevcut alt sureci zorla sonlandirir.

        scan_orchestrator tarafindan tarama durdurulunca cagrilir.
        """
        if self._proc is not None and self._proc.returncode is None:
            try:
                self._proc.kill()
                logger.debug("[%s] Proses zorla durduruldu", self.name)
            except (ProcessLookupError, OSError) as exc:
                logger.debug("[%s] kill hatasi: %s", self.name, exc)

    # ------------------------------------------------------------------
    # Mode yardimcisi
    # ------------------------------------------------------------------

    @staticmethod
    def mode_cfg(mode: str) -> Dict[str, Any]:
        """
        Verilen tarama modu icin yapilandirma sozlugunu doner.

        Bilinmeyen mod → 'normal' kullanilir.
        """
        return SCAN_MODES.get(mode, SCAN_MODES["normal"])

    def __repr__(self) -> str:
        available = "kurulu" if self.is_available() else "eksik"
        return f"<{self.__class__.__name__} binary={self.binary!r} [{available}]>"
