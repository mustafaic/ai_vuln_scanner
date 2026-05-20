"""
WhatWeb — web teknoloji parmak izi araci.

Cikti: JSON satirlari veya duz metin
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List, Optional

from tools.base import BaseTool

logger = logging.getLogger(__name__)


class WhatwebTool(BaseTool):
    """
    WhatWeb wrapper.

    Web uygulamasinin teknoloji yiginini tespit eder.
    """

    name = "whatweb"
    binary = "whatweb"

    def build_command(
        self,
        target: str,
        mode: str = "normal",
        **kwargs: Any,
    ) -> List[str]:
        aggression = "1"
        if mode == "normal":
            aggression = "3"
        elif mode == "aggressive":
            aggression = "4"

        cmd = [
            "whatweb",
            "--log-json=/dev/stdout",
            f"--aggression={aggression}",
            "--quiet",
            target,
        ]

        return cmd

    def parse_line(self, line: str) -> Optional[Dict[str, Any]]:
        line = line.strip()
        if not line:
            return None
        try:
            data = json.loads(line)
            if not isinstance(data, list) or not data:
                return None

            entry = data[0] if isinstance(data, list) else data
            plugins = entry.get("plugins", {})

            tech_stack = list(plugins.keys()) if plugins else []
            server = None
            if "HTTPServer" in plugins:
                strings = plugins["HTTPServer"].get("string", [])
                server = strings[0] if strings else None

            return {
                "url": entry.get("target", ""),
                "tech_stack": tech_stack,
                "server": server,
                "source": "whatweb",
                "raw": entry,
            }
        except (json.JSONDecodeError, IndexError, KeyError):
            logger.debug("[whatweb] Parse hatasi: %s", line[:100])
            return None
