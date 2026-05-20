"""
Subfinder — pasif subdomain kesif araci.

Cikti: her satir bir subdomain adi (ornek: api.example.com)
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from tools.base import BaseTool


class SubfinderTool(BaseTool):
    """
    Subfinder wrapper.

    Her satir tek bir subdomain adi icerir.
    parse_line() subdomain'i sozluge sarar.
    """

    name = "subfinder"
    binary = "subfinder"

    def build_command(
        self,
        target: str,
        mode: str = "normal",
        **kwargs: Any,
    ) -> List[str]:
        cfg = self.mode_cfg(mode)
        threads = str(cfg.get("threads", 15))

        rate = cfg.get("rate_limit", "20/s")
        rate_num = rate.split("/")[0]

        cmd = [
            "subfinder",
            "-d", target,
            "-silent",
            "-t", threads,
            "-rate-limit", rate_num,
            "-timeout", str(cfg.get("timeout", 10)),
        ]

        if mode == "stealth":
            cmd += ["-sources", "passive"]

        return cmd

    def parse_line(self, line: str) -> Optional[Dict[str, Any]]:
        line = line.strip()
        if not line or line.startswith("["):
            return None
        return {"subdomain": line, "source": "subfinder"}
