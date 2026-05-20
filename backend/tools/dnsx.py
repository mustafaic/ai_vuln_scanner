"""
Dnsx — DNS dogrulama ve IP cozumleme araci.

Cikti: JSON satirlari (host, a, cname, mx, ns, status_code)
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

from tools.base import BaseTool

logger = logging.getLogger(__name__)


class DnsxTool(BaseTool):
    """
    Dnsx wrapper.

    -list parametresiyle subdomain listesi dosyasi alir,
    her subdomain icin DNS kayitlarini JSON olarak doner.
    """

    name = "dnsx"
    binary = "dnsx"

    def build_command(
        self,
        target: str,
        mode: str = "normal",
        **kwargs: Any,
    ) -> List[str]:
        """
        Args:
            target: Subdomain listesi dosya yolu (her satir bir subdomain).
            mode:   Tarama modu.
            kwargs:
                wordlist (str): Alternatif liste dosyasi.
        """
        cfg = self.mode_cfg(mode)
        threads = str(cfg.get("threads", 15))

        input_file = kwargs.get("wordlist", target)

        cmd = [
            "dnsx",
            "-list", input_file,
            "-a",           # A kayitlarini coz
            "-resp",        # Cevap degerlerini goster
            "-json",        # JSON cikti
            "-t", threads,
            "-silent",
        ]

        if mode in ("normal", "aggressive"):
            cmd += ["-cname", "-mx", "-ns"]

        return cmd

    def parse_line(self, line: str) -> Optional[Dict[str, Any]]:
        line = line.strip()
        if not line:
            return None
        try:
            data = json.loads(line)
            return {
                "subdomain": data.get("host", ""),
                "ip_addresses": data.get("a", []),
                "status_code": data.get("status_code"),
                "cname": data.get("cname", []),
                "source": "dnsx",
                "raw": data,
            }
        except json.JSONDecodeError:
            logger.debug("[dnsx] JSON parse hatasi: %s", line[:100])
            return None
