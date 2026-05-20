"""
Httpx — HTTP probe ve parmak izi araci.

Cikti: JSON satirlari (url, status_code, title, tech, server, webserver, cdn, waf)
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

from tools.base import BaseTool

logger = logging.getLogger(__name__)


class HttpxTool(BaseTool):
    """
    Httpx wrapper.

    Subdomain listesini HTTP probe eder; yasayan host'lari
    baslik, teknoloji yigini ve diger meta verilerle doner.
    """

    name = "httpx"
    binary = "httpx"

    def build_command(
        self,
        target: str,
        mode: str = "normal",
        **kwargs: Any,
    ) -> List[str]:
        """
        Args:
            target: Subdomain listesi dosya yolu.
            mode:   Tarama modu.
        """
        cfg = self.mode_cfg(mode)
        threads = str(cfg.get("threads", 15))
        timeout = str(cfg.get("timeout", 10))

        cmd = [
            "httpx",
            "-list", target,
            "-title",
            "-tech-detect",
            "-status-code",
            "-server",
            "-json",
            "-silent",
            "-t", threads,
            "-timeout", timeout,
        ]

        if mode in ("normal", "aggressive"):
            cmd += ["-cdn", "-wc", "-cl", "-ct"]

        if mode == "aggressive":
            cmd += ["-follow-redirects", "-max-redirects", "5"]

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
            return {
                "subdomain": data.get("input", ""),
                "url": data.get("url", ""),
                "status_code": data.get("status_code"),
                "title": data.get("title"),
                "tech_stack": data.get("tech", []),
                "server": data.get("webserver") or data.get("server"),
                "cdn": data.get("cdn"),
                "waf": data.get("waf"),
                "ip_addresses": [data["host"]] if data.get("host") else [],
                "is_alive": True,
                "source": "httpx",
                "raw": data,
            }
        except json.JSONDecodeError:
            logger.debug("[httpx] JSON parse hatasi: %s", line[:100])
            return None
