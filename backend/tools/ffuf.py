"""
Ffuf — web fuzzer (dizin/endpoint kesfi).

Cikti: JSON satirlari veya sonuc satirlari
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from config import settings
from tools.base import BaseTool

logger = logging.getLogger(__name__)

_DEFAULT_WORDLIST = "top-10000.txt"


def _wordlist_path(filename: str) -> str:
    """Wordlist dosyasinin tam yolunu doner; bulunamazsa adini oldugu gibi verir."""
    path = Path(settings.WORDLISTS_PATH) / filename
    if path.exists():
        return str(path)
    # Sistem wordlist dizinlerini de kontrol et
    for base in ("/usr/share/wordlists", "/usr/share/seclists"):
        candidate = Path(base) / filename
        if candidate.exists():
            return str(candidate)
    return filename  # PATH'te bulunuyor olabilir


class FfufTool(BaseTool):
    """
    Ffuf wrapper.

    Dizin ve endpoint brute-force; JSON modunda calisir.
    """

    name = "ffuf"
    binary = "ffuf"

    def build_command(
        self,
        target: str,
        mode: str = "normal",
        **kwargs: Any,
    ) -> List[str]:
        """
        Args:
            target: Hedef URL (ornek: https://example.com).
                    FUZZ kelimesi yoksa sonuna /FUZZ eklenir.
            mode:   Tarama modu.
            kwargs:
                wordlist (str): Wordlist dosya yolu veya adi.
        """
        cfg = self.mode_cfg(mode)
        threads = str(cfg.get("threads", 15))
        timeout = str(cfg.get("timeout", 10))

        wordlist_name = kwargs.get("wordlist") or cfg.get("ffuf_wordlist", _DEFAULT_WORDLIST)
        wordlist = _wordlist_path(str(wordlist_name))

        # FUZZ token
        if "FUZZ" not in target:
            fuzz_url = target.rstrip("/") + "/FUZZ"
        else:
            fuzz_url = target

        cmd = [
            "ffuf",
            "-u", fuzz_url,
            "-w", wordlist,
            "-mc", "200,201,204,301,302,307,401,403,405",
            "-t", threads,
            "-timeout", timeout,
            "-of", "json",     # JSON output (stdout)
            "-o", "/dev/null", # Dosyaya yazma; -of json stdout'a yazar
            "-s",              # Silent mode
        ]

        if mode == "stealth":
            rate = cfg.get("rate_limit", "5/s").split("/")[0]
            cmd += ["-rate", rate]

        ua = cfg.get("user_agent")
        if ua:
            cmd += ["-H", f"User-Agent: {ua}"]

        return cmd

    def parse_line(self, line: str) -> Optional[Dict[str, Any]]:
        line = line.strip()
        if not line:
            return None
        try:
            data = json.loads(line)
            # ffuf JSON output her sonucu ayri nesne olarak yazmaz;
            # -of json tum sonuclari tek bir JSON dosyasina yazar.
            # Ancak -v flag ile satir bazli cikti alinabilir.
            # Burada her satiri deniyoruz.
            if "url" in data or "input" in data:
                return {
                    "url": data.get("url", ""),
                    "status_code": data.get("status"),
                    "length": data.get("length"),
                    "words": data.get("words"),
                    "lines": data.get("lines"),
                    "source": "ffuf",
                    "raw": data,
                }
        except json.JSONDecodeError:
            pass

        # Duz cikti satirlari
        if line.startswith("http"):
            return {"url": line, "source": "ffuf"}
        return None
