"""
URL kategorisasyon yardımcıları.

Spesifikasyon Bölüm 8.2 — Kategorizasyon:
  - GF pattern sonuçlarını zafiyet kategorisine eşleme
  - Parametre adı + path analizine dayalı zafiyet tahmini
  - HIGH_VALUE_KEYWORDS ile yüksek değerli içerik tespiti
  - Risk skoru hesaplama (0-100)
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Set
from urllib.parse import parse_qs, urlparse

# ---------------------------------------------------------------------------
# Keyword sözlüğü (Spesifikasyon Bölüm 8.2)
# ---------------------------------------------------------------------------

HIGH_VALUE_KEYWORDS: Dict[str, List[str]] = {
    "auth": [
        "login", "logout", "signin", "signup", "register", "auth",
        "oauth", "sso", "jwt", "token", "session",
    ],
    "admin": [
        "admin", "administrator", "dashboard", "panel", "console",
        "manage", "manager", "backend", "staff", "superuser",
    ],
    "sensitive": [
        "password", "passwd", "secret", "key", "api_key", "apikey",
        "private", "credential", "config", "configuration",
    ],
    "data": [
        "database", "db", "sql", "query", "export", "download",
        "backup", "dump", "restore",
    ],
    "file": [
        "file", "path", "dir", "directory", "folder", "upload",
        "download", "include", "read", "load", "open",
    ],
    "debug": [
        "debug", "test", "dev", "development", "staging",
        "temp", "tmp", "old", "bak", "copy",
    ],
    "user": [
        "user", "account", "profile", "id", "uid",
        "userid", "user_id", "member",
    ],
    "payment": [
        "payment", "pay", "order", "invoice", "billing",
        "checkout", "cart", "purchase",
    ],
}

# ---------------------------------------------------------------------------
# Parametre adı → zafiyet kategorisi regex eşlemesi
# ---------------------------------------------------------------------------

_PARAM_VULN_RE: Dict[str, re.Pattern] = {
    "xss": re.compile(
        r"^(search|q|query|s|name|message|comment|text|input|data|"
        r"value|html|content|title|desc|body|keyword|term)$",
        re.I,
    ),
    "sqli": re.compile(
        r"^(id|user_?id|category|product|item|page|sort|order|filter|"
        r"type|limit|offset|num|no|count|start|from|to)$",
        re.I,
    ),
    "lfi": re.compile(
        r"^(file|path|dir|folder|include|page|doc|template|"
        r"load|read|source|lang|locale|module|section)$",
        re.I,
    ),
    "redirect": re.compile(
        r"^(url|redirect|return|next|dest|destination|goto|link|"
        r"target|ref|redir|continue|back|from|to|forward|jump)$",
        re.I,
    ),
    "ssrf": re.compile(
        r"^(url|uri|endpoint|host|ip|server|src|source|remote|"
        r"fetch|proxy|callback|webhook|ping|check)$",
        re.I,
    ),
    "idor": re.compile(
        r"^(id|uid|user_?id|account|profile|order|item|object|"
        r"record|doc|num|uuid|ticket|ref|pid|cid)$",
        re.I,
    ),
}

# ---------------------------------------------------------------------------
# Path → zafiyet kategorisi regex eşlemesi
# ---------------------------------------------------------------------------

_PATH_VULN_RE: Dict[str, re.Pattern] = {
    "lfi": re.compile(r"(\.\./|%2e%2e|%252e|/include/|/require/|/load/)", re.I),
    "redirect": re.compile(r"/(redirect|forward|go|jump|link|click|visit)/", re.I),
    "ssrf": re.compile(r"/(proxy|fetch|request|webhook|callback|ping|check|scan)/", re.I),
}


# ---------------------------------------------------------------------------
# Yardımcı fonksiyonlar
# ---------------------------------------------------------------------------


def extract_params(url: str) -> List[Dict[str, str]]:
    """
    URL'deki query parametrelerini çıkarır.

    Returns:
        [{"name": "id", "value": "1"}, ...] — parametre başına bir dict.
    """
    try:
        parsed = urlparse(url)
        result: List[Dict[str, str]] = []
        for name, values in parse_qs(parsed.query, keep_blank_values=True).items():
            for val in values:
                result.append({"name": name, "value": val})
        return result
    except Exception:
        return []


def _detect_vuln_categories(
    url: str, params: List[Dict[str, str]]
) -> List[str]:
    """
    Parametre adları ve path'e bakarak olası zafiyet kategorilerini tahmin eder.

    Returns:
        Alfabetik sıralı zafiyet kategorisi listesi.
    """
    found: Set[str] = set()

    # Parametre adlarını regex ile eşleştir
    for p in params:
        name = p.get("name", "")
        for vuln, pattern in _PARAM_VULN_RE.items():
            if pattern.match(name):
                found.add(vuln)

    # Path analizi
    try:
        path = urlparse(url).path
        for vuln, pattern in _PATH_VULN_RE.items():
            if pattern.search(path):
                found.add(vuln)
    except Exception:
        pass

    return sorted(found)


def _detect_keywords(url: str, params: List[Dict[str, str]]) -> List[str]:
    """
    URL path + query ve parametre adlarında HIGH_VALUE_KEYWORDS arar.

    Returns:
        Tespit edilen keyword kategori adları (alfabetik sıralı).
    """
    try:
        parsed = urlparse(url)
        # Hem path hem query'de ara
        search_text = (parsed.path + "?" + parsed.query).lower()
    except Exception:
        search_text = url.lower()

    param_names: Set[str] = {p["name"].lower() for p in params}
    found: Set[str] = set()

    for category, keywords in HIGH_VALUE_KEYWORDS.items():
        for kw in keywords:
            if kw in search_text or kw in param_names:
                found.add(category)
                break  # Kategoride tek eşleşme yeterli

    return sorted(found)


# ---------------------------------------------------------------------------
# Ana fonksiyonlar
# ---------------------------------------------------------------------------


def calculate_risk_score(
    params: List[Dict[str, str]],
    vuln_categories: List[str],
    keywords: List[str],
    status_code: Optional[int] = None,
) -> int:
    """
    Risk skoru hesaplar (0-100).

    Spesifikasyon Bölüm 8.2 formülü:
        param sayısı × 5  (max 30 katkı)
        vuln kategori sayısı × 15
        keyword kategori sayısı × 10
        status 200 → +10
        status 403 → +5

    Returns:
        0-100 arasında integer risk skoru.
    """
    score = 0
    score += min(len(params) * 5, 30)
    score += len(vuln_categories) * 15
    score += len(keywords) * 10
    if status_code == 200:
        score += 10
    elif status_code == 403:
        score += 5
    return min(score, 100)


def categorize_url(
    url: str,
    params: Optional[List[Dict[str, str]]] = None,
    status_code: Optional[int] = None,
    gf_categories: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    URL'i kategorize eder ve risk skoru hesaplar.

    Args:
        url:           Analiz edilecek URL.
        params:        Önceden çıkarılmış parametre listesi;
                       None verilirse extract_params() çağrılır.
        status_code:   HTTP status kodu (risk skoruna etki eder).
        gf_categories: GF tool'dan gelen ek zafiyet kategorileri.

    Returns:
        {
            "vuln_categories": List[str],  — birleşik (parametre + path + gf)
            "keywords":        List[str],  — tespit edilen keyword kategorileri
            "risk_score":      int,        — 0-100
            "params":          List[dict], — parametre listesi
            "param_count":     int,
        }
    """
    if params is None:
        params = extract_params(url)

    detected = _detect_vuln_categories(url, params)
    all_vulns: Set[str] = set(detected)
    if gf_categories:
        all_vulns.update(gf_categories)

    keywords = _detect_keywords(url, params)
    vuln_list = sorted(all_vulns)
    risk_score = calculate_risk_score(params, vuln_list, keywords, status_code)

    return {
        "vuln_categories": vuln_list,
        "keywords": keywords,
        "risk_score": risk_score,
        "params": params,
        "param_count": len(params),
    }
