"""
URL deduplication ve normalizasyon yardımcıları.

Spesifikasyon Bölüm 8.2 — Deduplikasyon adımları:
  1. normalize_url(): trailing slash, fragment kaldır; scheme+host lowercase; query sırala
  2. Tam normalize edilmiş URL hash'i ile exact duplicate kaldır
  3. Aynı path + aynı parametre ADLARI (değerler farklı olsa bile) → tek URL tut
"""

from __future__ import annotations

import hashlib
from typing import List
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse


def normalize_url(url: str) -> str:
    """
    URL'i normalize eder.

    Dönüşümler:
    - scheme ve netloc (host) → lowercase
    - Fragment (#...) kaldır
    - Trailing slash kaldır (path sadece "/" ise bırak)
    - Query parametrelerini alfabetik sırala (deterministik karşılaştırma için)

    Returns:
        Normalize edilmiş URL string'i; geçersiz URL'de girdiyi döndürür.
    """
    url = url.strip()
    if not url:
        return url
    try:
        p = urlparse(url)
        scheme = p.scheme.lower()
        netloc = p.netloc.lower()
        path = p.path

        # Kök "/" hariç trailing slash kaldır
        if path != "/" and path.endswith("/"):
            path = path.rstrip("/")

        # Query parametrelerini isimlerine göre sırala
        query = ""
        if p.query:
            params = parse_qs(p.query, keep_blank_values=True)
            query = urlencode(sorted(params.items()), doseq=True)

        # Fragment kaldır (p.fragment yok sayılır)
        return urlunparse((scheme, netloc, path, p.params, query, ""))
    except Exception:
        return url


def _url_template_key(normalized: str) -> str:
    """
    URL şablonu için deduplication anahtarı üretir.

    Kural: scheme + netloc + path + parametre_isimleri (değersiz).
    Böylece "?id=1" ve "?id=2" aynı şablon olarak değerlendirilir.

    Returns:
        Şablon string'i.
    """
    try:
        p = urlparse(normalized)
        path = p.path.rstrip("/") or "/"
        param_sig = ""
        if p.query:
            names = sorted(parse_qs(p.query, keep_blank_values=True).keys())
            param_sig = ",".join(names)
        return f"{p.scheme}://{p.netloc}{path}#{param_sig}"
    except Exception:
        return normalized


def deduplicate(url_list: List[str]) -> List[str]:
    """
    URL listesini iki aşamalı deduplikasyona tabi tutar.

    Adım 1 — Exact duplicate:
        Normalize edilmiş URL string'i aynı olan URL'lerden ilki kalır.

    Adım 2 — Şablon duplicate:
        Aynı path + aynı parametre isimleri + farklı parametre değerleri → ilki kalır.
        Örnek: /page?id=1 ve /page?id=2 → sadece /page?id=1 kalır.

    Args:
        url_list: Ham URL string listesi (normalize edilmemiş olabilir).

    Returns:
        Benzersiz, normalize edilmiş URL listesi (karşılaşma sırasına göre).
    """
    seen_exact: set = set()
    seen_template: set = set()
    result: List[str] = []

    for raw in url_list:
        if not raw or not isinstance(raw, str):
            continue

        normalized = normalize_url(raw.strip())
        if not normalized:
            continue

        # Adım 1: tam eşleşme
        exact_hash = hashlib.md5(normalized.encode("utf-8")).hexdigest()
        if exact_hash in seen_exact:
            continue
        seen_exact.add(exact_hash)

        # Adım 2: şablon eşleşmesi
        tmpl = _url_template_key(normalized)
        tmpl_hash = hashlib.md5(tmpl.encode("utf-8")).hexdigest()
        if tmpl_hash in seen_template:
            continue
        seen_template.add(tmpl_hash)

        result.append(normalized)

    return result
