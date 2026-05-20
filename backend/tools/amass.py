"""
Amass — OWASP subdomain kesif araci.

Cikti: her satir bir subdomain adi
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from tools.base import BaseTool


class AmassTool(BaseTool):
    """
    Amass wrapper.

    Pasif modda calistirilir; her satir bir subdomain doner.
    """

    name = "amass"
    binary = "amass"

    def build_command(
        self,
        target: str,
        mode: str = "normal",
        **kwargs: Any,
    ) -> List[str]:
        cmd = [
            "amass", "enum",
            "-passive",
            "-d", target,
            "-silent",
        ]

        if mode == "aggressive":
            # Aktif DNS taramasi ekle
            cmd.remove("-passive")
            cmd.append("-active")

        return cmd

    def parse_line(self, line: str) -> Optional[Dict[str, Any]]:
        line = line.strip()
        if not line:
            return None
        # Amass bazen "subdomain.example.com (FQDN)" gibi cikti verebilir
        subdomain = line.split()[0]
        return {"subdomain": subdomain, "source": "amass"}
