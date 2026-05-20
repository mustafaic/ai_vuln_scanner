"""
Paramspider — URL parametre toplayici.

Cikti: her satir bir URL (parametreler iceren)
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from tools.base import BaseTool


class ParamspiderTool(BaseTool):
    """
    Paramspider wrapper.

    Wayback Machine'den parametreli URL'leri toplar.
    """

    name = "paramspider"
    binary = "paramspider"

    def build_command(
        self,
        target: str,
        mode: str = "normal",
        **kwargs: Any,
    ) -> List[str]:
        cmd = [
            "paramspider",
            "--domain", target,
            "--quiet",
        ]

        if mode == "aggressive":
            cmd += ["--subs"]

        return cmd

    def parse_line(self, line: str) -> Optional[Dict[str, Any]]:
        line = line.strip()
        if not line or not line.startswith("http"):
            return None
        # Parametre icermeyen URL'leri filtrele
        if "=" not in line:
            return None
        return {"url": line, "source": "paramspider"}
