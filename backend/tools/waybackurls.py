"""
Waybackurls — Wayback Machine URL toplayici.

Cikti: her satir bir URL (stdin'den domain alir)
"""

from __future__ import annotations

from typing import Any, AsyncGenerator, Dict, List, Optional

from tools.base import BaseTool, _build_run_env


class WaybackurlsTool(BaseTool):
    """
    Waybackurls wrapper.

    waybackurls domain'i stdin'den alir; build_command bu yuzden
    'echo domain | waybackurls' seklini kullanmaz — bunun yerine
    run() override edilir ve stdin beslemesi yapilir.
    """

    name = "waybackurls"
    binary = "waybackurls"

    def build_command(
        self,
        target: str,
        mode: str = "normal",
        **kwargs: Any,
    ) -> List[str]:
        # waybackurls arguman almaz; hedef stdin'den gelir
        return ["waybackurls"]

    async def stream(
        self,
        target: str,
        mode: str = "normal",
        **kwargs: Any,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        waybackurls'e stdin uzerinden domain verir.
        """
        import asyncio

        if not self.is_available():
            import logging
            logging.getLogger(__name__).warning(
                "[waybackurls] Kurulu degil, stream atlaniyor"
            )
            return

        env = _build_run_env()
        proc = await asyncio.create_subprocess_exec(
            "waybackurls",
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )
        self._proc = proc

        # Hedefi stdin'e yaz ve kapat
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
        return {"url": line, "source": "waybackurls"}
