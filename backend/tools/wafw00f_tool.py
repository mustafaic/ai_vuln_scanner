"""
Wafw00f — WAF tespit araci.

Cikti: duz metin; WAF adi regex ile cikarilir.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from tools.base import BaseTool

# "The site https://... is behind <WAF NAME> WAF."
_WAF_PATTERN = re.compile(
    r"is behind (.+?) WAF",
    re.IGNORECASE,
)
# "No WAF detected by the simple tests"
_NO_WAF_PATTERN = re.compile(r"no waf detected", re.IGNORECASE)


class Wafw00fTool(BaseTool):
    """
    Wafw00f wrapper.

    WAF tespiti yapar; parse_line() WAF adini cikarir.
    Bulunamazsa None doner (satir atlanir).
    """

    name = "wafw00f"
    binary = "wafw00f"

    def build_command(
        self,
        target: str,
        mode: str = "normal",
        **kwargs: Any,
    ) -> List[str]:
        cmd = ["wafw00f", target]

        if mode == "aggressive":
            cmd += ["-a"]  # Tum WAF'lari test et

        return cmd

    def parse_line(self, line: str) -> Optional[Dict[str, Any]]:
        line = line.strip()
        if not line:
            return None

        m = _WAF_PATTERN.search(line)
        if m:
            return {
                "waf_detected": True,
                "waf_name": m.group(1).strip(),
                "raw_line": line,
                "source": "wafw00f",
            }

        if _NO_WAF_PATTERN.search(line):
            return {
                "waf_detected": False,
                "waf_name": None,
                "raw_line": line,
                "source": "wafw00f",
            }

        return None
