"""
Assetfinder — hizli pasif subdomain bulucu.

Cikti: her satir bir subdomain adi
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from tools.base import BaseTool


class AssetfinderTool(BaseTool):
    """
    Assetfinder wrapper.

    Pasif kaynaklardan subdomain toplar; her satir bir subdomain doner.
    """

    name = "assetfinder"
    binary = "assetfinder"

    def build_command(
        self,
        target: str,
        mode: str = "normal",
        **kwargs: Any,
    ) -> List[str]:
        cmd = ["assetfinder"]

        # --subs-only: sadece alt domain'leri doner (ana domain harici)
        if mode != "aggressive":
            cmd.append("--subs-only")

        cmd.append(target)
        return cmd

    def parse_line(self, line: str) -> Optional[Dict[str, Any]]:
        line = line.strip()
        if not line or " " in line:
            return None
        return {"subdomain": line, "source": "assetfinder"}
