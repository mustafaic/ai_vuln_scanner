"""
Katana — nextgen web crawler.

Cikti: JSON satirlari (request.endpoint) veya duz URL satirlari
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

from tools.base import BaseTool

logger = logging.getLogger(__name__)


class KatanaTool(BaseTool):
    """
    Katana wrapper.

    JavaScript destekli web crawler; URL'leri JSON olarak doner.
    """

    name = "katana"
    binary = "katana"

    def build_command(
        self,
        target: str,
        mode: str = "normal",
        **kwargs: Any,
    ) -> List[str]:
        cfg = self.mode_cfg(mode)
        threads = str(cfg.get("threads", 15))
        timeout = str(cfg.get("timeout", 10))

        depth = "3"
        if mode == "stealth":
            depth = "2"
        elif mode == "aggressive":
            depth = "5"

        cmd = [
            "katana",
            "-u", target,
            "-d", depth,
            "-jc",          # JavaScript parsing
            "-json",        # JSON cikti
            "-silent",
            "-c", threads,
            "-timeout", timeout,
        ]

        if mode == "aggressive":
            cmd += ["-aff", "-jsl"]  # headless JS rendering

        ua = cfg.get("user_agent")
        if ua:
            cmd += ["-H", f"User-Agent: {ua}"]

        return cmd

    def parse_line(self, line: str) -> Optional[Dict[str, Any]]:
        line = line.strip()
        if not line:
            return None
        try:
            data = json.loads(line)
            # Katana JSON formatı: {"timestamp":..., "request":{"endpoint":...}}
            endpoint = (
                data.get("request", {}).get("endpoint")
                or data.get("endpoint")
                or data.get("url")
            )
            if not endpoint:
                return None
            return {
                "url": endpoint,
                "method": data.get("request", {}).get("method", "GET"),
                "source": "katana",
                "raw": data,
            }
        except json.JSONDecodeError:
            # Bazen duz URL satirlari da gelebilir
            if line.startswith("http"):
                return {"url": line, "source": "katana"}
            return None
