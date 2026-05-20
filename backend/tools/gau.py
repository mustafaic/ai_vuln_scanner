"""
Gau — GetAllUrls araci (Wayback Machine, OTX, Common Crawl).

Cikti: her satir bir URL
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from tools.base import BaseTool


class GauTool(BaseTool):
    """
    Gau wrapper.

    Pasif URL toplama; her satir tek bir URL doner.
    """

    name = "gau"
    binary = "gau"

    def build_command(
        self,
        target: str,
        mode: str = "normal",
        **kwargs: Any,
    ) -> List[str]:
        cfg = self.mode_cfg(mode)
        threads = str(cfg.get("threads", 15))

        cmd = [
            "gau",
            target,
            "--threads", threads,
        ]

        if mode == "stealth":
            cmd += ["-providers", "wayback"]

        if mode == "aggressive":
            cmd += ["--subs"]

        return cmd

    def parse_line(self, line: str) -> Optional[Dict[str, Any]]:
        line = line.strip()
        if not line or not line.startswith("http"):
            return None
        return {"url": line, "source": "gau"}
