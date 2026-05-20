"""
Dalfox — XSS tarama araci.

Cikti: JSON satirlari (vuln, payload, evidence vb.)
"""

from __future__ import annotations

import json
import logging
import shlex
from typing import Any, Dict, List, Optional

from tools.base import BaseTool

logger = logging.getLogger(__name__)

# Severity haritasi
_SEVERITY_MAP = {
    "G": "high",    # GET
    "P": "high",    # POST
    "R": "medium",  # Reflected
    "S": "info",    # Stored indicator
}


class DalfoxTool(BaseTool):
    """
    Dalfox wrapper.

    URL bazli XSS taramasi yapar; bulguları JSON olarak doner.
    """

    name = "dalfox"
    binary = "dalfox"

    def build_command(
        self,
        target: str,
        mode: str = "normal",
        **kwargs: Any,
    ) -> List[str]:
        """
        Args:
            target: Taranacak URL (parametreler dahil).
            mode:   Tarama modu.
            kwargs:
                cookie (str): Cookie basligi.
                headers (list[str]): Ek HTTP basliklar.
                waf_bypass (bool): WAF atlatma modunu etkinlestir.
        """
        cfg = self.mode_cfg(mode)

        # Mode'a gore ek bayraklar
        mode_flags_str = cfg.get("dalfox_flags", "")
        mode_flags = shlex.split(mode_flags_str) if mode_flags_str else []

        cmd = [
            "dalfox",
            "url", target,
            "--silence",
            "--format", "json",
        ] + mode_flags

        cookie = kwargs.get("cookie")
        if cookie:
            cmd += ["--cookie", cookie]

        for header in kwargs.get("headers", []):
            cmd += ["--header", header]

        if kwargs.get("waf_bypass") or mode == "aggressive":
            cmd += ["--waf-evasion"]

        ua = cfg.get("user_agent")
        if ua:
            cmd += ["--ua", ua]

        return cmd

    def parse_line(self, line: str) -> Optional[Dict[str, Any]]:
        line = line.strip()
        if not line:
            return None
        try:
            data = json.loads(line)
            if not isinstance(data, dict):
                return None

            vuln_type = data.get("type", "xss").lower()
            if vuln_type not in ("xss", "reflected", "stored", "dom"):
                vuln_type = "xss"

            return {
                "vuln_type": vuln_type,
                "severity": data.get("severity", "high"),
                "title": data.get("message") or "XSS vulnerability found",
                "payload": data.get("data", {}).get("payload") if isinstance(data.get("data"), dict) else None,
                "evidence": data.get("evidence") or data.get("injected_param"),
                "param": data.get("param"),
                "url": data.get("injectionURL") or data.get("url"),
                "source": "dalfox",
                "raw": data,
            }
        except json.JSONDecodeError:
            # Dalfox bazen "[POC]" veya "[VULN]" on ekli satirlar yazar
            if "[POC]" in line or "[VULN]" in line:
                return {
                    "vuln_type": "xss",
                    "severity": "high",
                    "title": "XSS vulnerability found",
                    "evidence": line,
                    "source": "dalfox",
                }
            logger.debug("[dalfox] Parse edilemeyen satir: %s", line[:120])
            return None
