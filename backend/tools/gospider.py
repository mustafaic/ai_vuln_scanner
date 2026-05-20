"""
Gospider — hizli web spider.

Cikti: her satir "[spider] [url] [referrer]" formatinda veya duz URL
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from tools.base import BaseTool

# "[spider] [200] [https://example.com/path] - https://example.com"
_LINE_PATTERN = re.compile(
    r"\[spider\]\s+\[[\w-]+\]\s+\[(.+?)\]"
)


class GospiderTool(BaseTool):
    """
    Gospider wrapper.

    Hizli web spider; URL'leri kesfeder.
    """

    name = "gospider"
    binary = "gospider"

    def build_command(
        self,
        target: str,
        mode: str = "normal",
        **kwargs: Any,
    ) -> List[str]:
        cfg = self.mode_cfg(mode)
        threads = str(cfg.get("threads", 15))

        depth = "3"
        if mode == "stealth":
            depth = "2"
        elif mode == "aggressive":
            depth = "5"

        cmd = [
            "gospider",
            "-s", target,
            "-t", threads,
            "-d", depth,
            "--no-redirect",
            "-q",
        ]

        if mode in ("normal", "aggressive"):
            cmd += ["-c", "10"]  # concurrent requests per domain

        if mode == "aggressive":
            cmd += ["--include-subs"]

        ua = cfg.get("user_agent")
        if ua:
            cmd += ["-u", ua]

        return cmd

    def parse_line(self, line: str) -> Optional[Dict[str, Any]]:
        line = line.strip()
        if not line:
            return None

        m = _LINE_PATTERN.search(line)
        if m:
            url = m.group(1).strip()
            if url.startswith("http"):
                return {"url": url, "source": "gospider"}
            return None

        if line.startswith("http"):
            return {"url": line, "source": "gospider"}

        return None
