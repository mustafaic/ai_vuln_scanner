"""
Nuclei — sablon tabanli zafiyet tarayici.

Cikti: JSON satirlari (templateID, info, host, matched-at, type vb.)
"""

from __future__ import annotations

import json
import logging
import shlex
from pathlib import Path
from typing import Any, Dict, List, Optional

from config import settings
from tools.base import BaseTool

logger = logging.getLogger(__name__)

# Nuclei severity -> uygulama severity eslesmesi
_SEVERITY_MAP = {
    "critical": "critical",
    "high": "high",
    "medium": "medium",
    "low": "low",
    "info": "info",
    "unknown": "info",
}

# Varsayilan sablon etiketleri mod bazinda
_TEMPLATE_TAGS = {
    "stealth": "cve,exposure",
    "normal": "cve,misconfig,exposure,default-login",
    "aggressive": "cve,misconfig,exposure,default-login,sqli,xss,lfi,ssrf,rce",
}


class NucleiTool(BaseTool):
    """
    Nuclei wrapper.

    Sablon bazli zafiyet taramasi; bulguları JSON olarak doner.
    """

    name = "nuclei"
    binary = "nuclei"

    def build_command(
        self,
        target: str,
        mode: str = "normal",
        **kwargs: Any,
    ) -> List[str]:
        """
        Args:
            target: Hedef URL veya dosya yolu (-list icin).
            mode:   Tarama modu.
            kwargs:
                templates (str):  Sablon yolu veya etiketi.
                tags (str):       Virgul ayiraci ile etiket listesi.
                severity (str):   critical,high,medium,low,info
                list_file (bool): True ise target bir dosya yolu olarak islenir.
        """
        cfg = self.mode_cfg(mode)

        templates_path = kwargs.get("templates") or settings.NUCLEI_TEMPLATES_PATH
        tags = kwargs.get("tags") or _TEMPLATE_TAGS.get(mode, _TEMPLATE_TAGS["normal"])
        severity = kwargs.get("severity", "critical,high,medium,low,info")

        rate_str = cfg.get("nuclei_rate", "50/m")
        rate_num = rate_str.split("/")[0]

        cmd = [
            "nuclei",
            "-json",
            "-silent",
            "-rate-limit", rate_num,
            "-severity", severity,
            "-tags", tags,
        ]

        # Hedef: dosya listesi mi, tek URL mi?
        if kwargs.get("list_file"):
            cmd += ["-list", target]
        else:
            cmd += ["-u", target]

        # Sablon dizini gecerliyse ekle
        t_path = Path(templates_path)
        if t_path.exists():
            cmd += ["-t", str(t_path)]

        timeout = str(cfg.get("timeout", 10))
        cmd += ["-timeout", timeout]

        return cmd

    def parse_line(self, line: str) -> Optional[Dict[str, Any]]:
        line = line.strip()
        if not line:
            return None
        try:
            data = json.loads(line)
            if not isinstance(data, dict):
                return None

            info = data.get("info", {})
            severity_raw = info.get("severity", "info").lower()
            severity = _SEVERITY_MAP.get(severity_raw, "info")

            matched_at = data.get("matched-at") or data.get("host", "")
            template_id = data.get("template-id") or data.get("templateID", "")
            name = info.get("name") or template_id

            return {
                "vuln_type": data.get("type", "nuclei").lower(),
                "severity": severity,
                "title": name,
                "template_id": template_id,
                "matched_at": matched_at,
                "url": matched_at,
                "evidence": data.get("extracted-results") or data.get("matcher-name"),
                "tags": info.get("tags", []),
                "reference": info.get("reference", []),
                "source": "nuclei",
                "raw": data,
            }
        except json.JSONDecodeError:
            logger.debug("[nuclei] JSON parse hatasi: %s", line[:120])
            return None
