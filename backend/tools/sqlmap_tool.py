"""
Sqlmap — SQL injection tarama araci.

Cikti: duz metin; enjeksiyon gostergesi regex ile tespit edilir.
"""

from __future__ import annotations

import re
import shlex
from typing import Any, Dict, List, Optional

from config import settings
from tools.base import BaseTool

# Enjeksiyon tespit gostergeleri
_INJECTION_PATTERNS = [
    re.compile(r"parameter .+ (is|appears to be) .+ injectable", re.IGNORECASE),
    re.compile(r"sqlmap identified the following injection", re.IGNORECASE),
    re.compile(r"Type: .+injection", re.IGNORECASE),
    re.compile(r"\[CRITICAL\].*inject", re.IGNORECASE),
    re.compile(r"back-end DBMS: (.+)", re.IGNORECASE),
]

_DBMS_PATTERN = re.compile(r"back-end DBMS:\s*(.+)", re.IGNORECASE)
_PARAM_PATTERN = re.compile(r"parameter '(.+?)' is", re.IGNORECASE)
_TYPE_PATTERN = re.compile(r"Type:\s*(.+)", re.IGNORECASE)


class SqlmapTool(BaseTool):
    """
    Sqlmap wrapper.

    URL bazli SQL injection taramasi; --batch ile otomatik calisir.
    """

    name = "sqlmap"
    binary = "sqlmap"

    def build_command(
        self,
        target: str,
        mode: str = "normal",
        **kwargs: Any,
    ) -> List[str]:
        """
        Args:
            target: Taranacak URL (GET parametreleri dahil).
            mode:   Tarama modu.
            kwargs:
                data (str):   POST body'si.
                cookie (str): Cookie basligi.
                output_dir (str): Sqlmap cikti dizini.
        """
        cfg = self.mode_cfg(mode)
        mode_flags_str = cfg.get("sqlmap_flags", "--level=2 --risk=2")
        mode_flags = shlex.split(mode_flags_str)

        output_dir = kwargs.get("output_dir", settings.SQLMAP_OUTPUT_PATH)

        cmd = [
            "sqlmap",
            "-u", target,
            "--batch",
            "--output-dir", output_dir,
        ] + mode_flags

        data = kwargs.get("data")
        if data:
            cmd += ["--data", data]

        cookie = kwargs.get("cookie")
        if cookie:
            cmd += ["--cookie", cookie]

        ua = cfg.get("user_agent")
        if ua:
            cmd += ["--user-agent", ua]

        return cmd

    def parse_line(self, line: str) -> Optional[Dict[str, Any]]:
        line_stripped = line.strip()
        if not line_stripped:
            return None

        # Enjeksiyon gostergesi var mi?
        for pattern in _INJECTION_PATTERNS:
            if pattern.search(line_stripped):
                result: Dict[str, Any] = {
                    "vuln_type": "sqli",
                    "severity": "high",
                    "evidence": line_stripped,
                    "source": "sqlmap",
                }

                dbms_m = _DBMS_PATTERN.search(line_stripped)
                if dbms_m:
                    result["dbms"] = dbms_m.group(1).strip()

                param_m = _PARAM_PATTERN.search(line_stripped)
                if param_m:
                    result["param"] = param_m.group(1)

                type_m = _TYPE_PATTERN.search(line_stripped)
                if type_m:
                    result["injection_type"] = type_m.group(1).strip()

                return result

        return None
