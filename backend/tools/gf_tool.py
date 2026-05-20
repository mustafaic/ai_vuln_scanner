"""
GF — URL pattern filtresi (tomnomnom/gf).

Cikti: her satir bir URL (ilgili pattern'a uyan)
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from tools.base import BaseTool

# Desteklenen pattern'lar ve karsilik gelen zafiyet kategorisi
PATTERN_VULN_MAP = {
    "xss": "xss",
    "sqli": "sqli",
    "ssrf": "ssrf",
    "lfi": "lfi",
    "rce": "rce",
    "idor": "idor",
    "redirect": "redirect",
    "debug_logic": "debug",
    "upload-fields": "upload",
    "interestingparams": "interesting",
}


class GfTool(BaseTool):
    """
    GF wrapper.

    URL listesini stdin'den alir, belirtilen pattern'a gore filtreler.
    """

    name = "gf"
    binary = "gf"

    def build_command(
        self,
        target: str,
        mode: str = "normal",
        **kwargs: Any,
    ) -> List[str]:
        """
        Args:
            target: GF pattern adi (ornek: 'xss', 'sqli').
            mode:   Tarama modu (kullanilmaz).
            kwargs:
                input_file (str): URL listesi dosyasi (cat ile piping yerine).
        """
        return ["gf", target]

    async def stream(
        self,
        target: str,
        mode: str = "normal",
        **kwargs: Any,
    ):
        """
        GF pattern'ina URL'leri stdin'den besler.

        Args:
            target:  GF pattern adi.
            kwargs:
                urls (list[str]): Filtrelenecek URL'ler.
        """
        import asyncio
        import logging

        log = logging.getLogger(__name__)

        urls: List[str] = kwargs.get("urls", [])
        if not urls:
            return

        if not self.is_available():
            log.warning("[gf] Kurulu degil, stream atlaniyor")
            return

        from tools.base import _build_run_env
        env = _build_run_env()
        args = self.build_command(target, mode)

        proc = await asyncio.create_subprocess_exec(
            *args,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )
        self._proc = proc

        stdin_data = "\n".join(urls).encode()
        proc.stdin.write(stdin_data)
        await proc.stdin.drain()
        proc.stdin.close()

        vuln_category = PATTERN_VULN_MAP.get(target, target)

        try:
            async for raw_line in proc.stdout:
                if not self.pause_event.is_set():
                    await self.pause_event.wait()

                line = raw_line.decode("utf-8", errors="replace").rstrip()
                if line and line.startswith("http"):
                    yield {
                        "url": line,
                        "vuln_category": vuln_category,
                        "pattern": target,
                        "source": "gf",
                    }
        except asyncio.CancelledError:
            raise
        finally:
            self._proc = None
            if proc.returncode is None:
                try:
                    proc.kill()
                except (ProcessLookupError, OSError):
                    pass
            try:
                await asyncio.wait_for(proc.wait(), timeout=5.0)
            except asyncio.TimeoutError:
                pass

    def parse_line(self, line: str) -> Optional[Dict[str, Any]]:
        line = line.strip()
        if not line or not line.startswith("http"):
            return None
        return {"url": line, "source": "gf"}
