"""
Hakrawler — hizli web crawler.

Cikti: her satir bir URL (stdin'den URL alir)
"""

from __future__ import annotations

from typing import Any, AsyncGenerator, Dict, List, Optional

from tools.base import BaseTool, _build_run_env


class HakrawlerTool(BaseTool):
    """
    Hakrawler wrapper.

    hakrawler URL'i stdin'den alir; stream() override edilmistir.
    """

    name = "hakrawler"
    binary = "hakrawler"

    def build_command(
        self,
        target: str,
        mode: str = "normal",
        **kwargs: Any,
    ) -> List[str]:
        cfg = self.mode_cfg(mode)

        depth = "3"
        if mode == "stealth":
            depth = "2"
        elif mode == "aggressive":
            depth = "5"

        cmd = [
            "hakrawler",
            "-depth", depth,
            "-plain",
        ]

        if mode == "aggressive":
            cmd += ["-subs", "-u"]

        ua = cfg.get("user_agent")
        if ua:
            cmd += ["-h", f"User-Agent: {ua}"]

        return cmd

    async def stream(
        self,
        target: str,
        mode: str = "normal",
        **kwargs: Any,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        hakrawler'a stdin uzerinden URL verir.
        """
        import asyncio
        import logging

        log = logging.getLogger(__name__)

        if not self.is_available():
            log.warning("[hakrawler] Kurulu degil, stream atlaniyor")
            return

        env = _build_run_env()
        args = self.build_command(target, mode, **kwargs)

        proc = await asyncio.create_subprocess_exec(
            *args,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )
        self._proc = proc

        # Hedefi stdin'e yaz
        proc.stdin.write((target + "\n").encode())
        await proc.stdin.drain()
        proc.stdin.close()

        try:
            async for raw_line in proc.stdout:
                if not self.pause_event.is_set():
                    await self.pause_event.wait()

                line = raw_line.decode("utf-8", errors="replace").rstrip()
                if line and line.startswith("http"):
                    result = self.parse_line(line)
                    if result is not None:
                        yield result
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
        return {"url": line, "source": "hakrawler"}
