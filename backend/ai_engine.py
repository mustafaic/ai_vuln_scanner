"""
AI motoru: Ollama entegrasyonu ve tum prompt sablonlari.

Spesifikasyon Bolum 9 referans alinmistir.

Hata hiyerarsisi:
    AIError (base)
     ├── AIUnavailableError   Ollama'ya ulasılamıyor
     ├── AITimeoutError       Istek zaman asimina ugradi
     └── AIResponseError      Yanit beklenen formatta degil (JSON parse, vb.)

OllamaClient:
    generate(prompt)          -> str
    generate_json(prompt)     -> dict  (max 2 deneme, JSON parse)
    generate_stream(prompt)   -> AsyncGenerator[str]
    is_available()            -> bool

Prompt fonksiyonlari:
    score_subdomains(...)     -> list[dict]   (Bolum 9.1)
    analyze_urls(...)         -> list[dict]   (Bolum 9.2, batch=50)
    pre_test_analysis(...)    -> list[dict]   (Bolum 9.3)
    suggest_waf_bypass(...)   -> list[dict]   (Bolum 9.4)
    analyze_finding(...)      -> dict         (Bolum 9.5)
    chat(...)                 -> str          (Bolum 9.6)
    chat_stream(...)          -> AsyncGenerator[str]
"""

from __future__ import annotations

import json
import logging
import re
import textwrap
from typing import Any, AsyncGenerator, Dict, List, Optional

import httpx

from config import settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Ozel istisnalar
# ---------------------------------------------------------------------------


class AIError(Exception):
    """AI motoruyla ilgili tum hatalarin base sinifi."""


class AIUnavailableError(AIError):
    """Ollama servisi erisilebilir degil."""


class AITimeoutError(AIError):
    """AI istegi belirlenen sure icinde tamamlanamadi."""


class AIResponseError(AIError):
    """Yanit beklenen formatta gelmedigi durum (JSON parse, eksik alan, vb.)."""


# ---------------------------------------------------------------------------
# JSON temizleme yardimcisi
# ---------------------------------------------------------------------------

_FENCE_RE = re.compile(r"```(?:json)?\s*([\s\S]*?)```", re.IGNORECASE)
_LEADING_TEXT_RE = re.compile(r"^[^{\[]*([{\[])", re.DOTALL)


def _clean_json(text: str) -> str:
    """
    Model ciktisindaki JSON'u soyutlanmis metin ve markdown'dan ayiklar.

    Deneme sirasi:
      1. ```json ... ``` veya ``` ... ``` blogu varsa icini al.
      2. Yoksa ilk { veya [ karakterinden itibaren al.
    """
    fence = _FENCE_RE.search(text)
    if fence:
        return fence.group(1).strip()

    match = _LEADING_TEXT_RE.search(text)
    if match:
        return text[match.start(1):].strip()

    return text.strip()


def _parse_json(text: str) -> Any:
    """
    AI ciktisini JSON'a donusturur.

    Raises:
        AIResponseError: Gecerli JSON bulunamazsa.
    """
    cleaned = _clean_json(text)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise AIResponseError(
            f"JSON parse hatasi: {exc}\nHam yanit (ilk 500 karakter):\n{text[:500]}"
        ) from exc


# ---------------------------------------------------------------------------
# OllamaClient
# ---------------------------------------------------------------------------


class OllamaClient:
    """
    Ollama HTTP API istemcisi.

    Tum AI islemleri bu sinif uzerinden yurur; dogrudan httpx kullanir
    cunku ollama-python kutuphanesi streaming icin sinirli kalir.

    Args:
        host:    Ollama sunucu adresi (varsayilan: settings.OLLAMA_HOST)
        model:   Kullanilacak model adi (varsayilan: settings.OLLAMA_MODEL)
        timeout: Saniye cinsinden istek zaman asimi (varsayilan: settings.OLLAMA_TIMEOUT)
    """

    GENERATE_PATH = "/api/generate"
    TAGS_PATH = "/api/tags"

    def __init__(
        self,
        host: Optional[str] = None,
        model: Optional[str] = None,
        timeout: Optional[int] = None,
    ) -> None:
        self.host = (host or settings.OLLAMA_HOST).rstrip("/")
        self.model = model or settings.OLLAMA_MODEL
        self.timeout = timeout or settings.OLLAMA_TIMEOUT

    # ------------------------------------------------------------------
    # Dahili HTTP yardimcilari
    # ------------------------------------------------------------------

    def _client(self) -> httpx.AsyncClient:
        """Her istek icin taze bir AsyncClient olusturur."""
        return httpx.AsyncClient(
            base_url=self.host,
            timeout=httpx.Timeout(connect=10.0, read=self.timeout, write=30.0, pool=5.0),
        )

    async def _post_generate(
        self,
        prompt: str,
        stream: bool = False,
    ) -> httpx.Response:
        """
        /api/generate endpoint'ine POST atar.

        Raises:
            AIUnavailableError: Baglanti kurulamazsa.
            AITimeoutError:     Zaman asimina ugrarsa.
        """
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": stream,
        }
        try:
            async with self._client() as client:
                if stream:
                    # Streaming modda response nesnesi dogrudan donmez;
                    # cagiran taraf context manager kullanmali.
                    # Bu path sadece generate_stream icin cagrilir.
                    raise NotImplementedError("Streaming icin generate_stream kullanin")
                response = await client.post(self.GENERATE_PATH, json=payload)
                response.raise_for_status()
                return response
        except httpx.ConnectError as exc:
            raise AIUnavailableError(
                f"Ollama'ya baglanılamadi ({self.host}): {exc}"
            ) from exc
        except httpx.TimeoutException as exc:
            raise AITimeoutError(
                f"Ollama istegi zaman asimina ugradi ({self.timeout}s)"
            ) from exc
        except httpx.HTTPStatusError as exc:
            raise AIError(
                f"Ollama HTTP hatasi {exc.response.status_code}: {exc.response.text[:200]}"
            ) from exc

    # ------------------------------------------------------------------
    # Bağlantı testi
    # ------------------------------------------------------------------

    async def ping(self) -> bool:
        """Ollama sunucusuna bağlanılabilir mi diye kontrol eder."""
        try:
            async with self._client() as client:
                resp = await client.get(self.TAGS_PATH)
                return resp.status_code < 500
        except Exception:
            return False

    # ------------------------------------------------------------------
    # Genel uretim metodlari
    # ------------------------------------------------------------------

    async def generate(self, prompt: str) -> str:
        """
        Prompt gonderir ve tam yaniti string olarak doner.

        Args:
            prompt: Model'e gonderilecek metin.

        Returns:
            Modelin urettigi metin.

        Raises:
            AIUnavailableError, AITimeoutError, AIError
        """
        response = await self._post_generate(prompt, stream=False)
        data = response.json()
        return data.get("response", "")

    async def generate_json(self, prompt: str) -> Any:
        """
        Prompt gonderir, yaniti JSON olarak parse eder.

        Parse basarisiz olursa modele ikinci bir deneme yapilir;
        her iki deneme de basarisiz olursa AIResponseError firlatiir.

        Args:
            prompt: Model'e gonderilecek metin.

        Returns:
            Parse edilmis Python nesnesi (dict veya list).

        Raises:
            AIResponseError: Iki denemede de JSON alinamazsa.
            AIUnavailableError, AITimeoutError, AIError
        """
        last_exc: Optional[Exception] = None
        for attempt in range(1, 3):
            try:
                raw = await self.generate(prompt)
                return _parse_json(raw)
            except AIResponseError as exc:
                last_exc = exc
                logger.warning(
                    "generate_json deneme %d/2 basarisiz: %s", attempt, exc
                )
                if attempt == 1:
                    # Ikinci denemede modele formati hatirlatiyoruz
                    prompt = (
                        prompt
                        + "\n\nNOT: Onceki yanıtın JSON parse edilemedi. "
                        "YALNIZCA gecerli JSON don, baska hicbir sey ekleme."
                    )
        raise AIResponseError(
            f"2 denemede de JSON alinamadi. Son hata: {last_exc}"
        ) from last_exc

    async def generate_stream(self, prompt: str) -> AsyncGenerator[str, None]:
        """
        Prompt gonderir; modelin urettiklerini token token yield eder.

        Yields:
            Her adimda uretilen metin parcasi.

        Raises:
            AIUnavailableError, AITimeoutError, AIError
        """
        payload = {"model": self.model, "prompt": prompt, "stream": True}
        try:
            async with self._client() as client:
                async with client.stream("POST", self.GENERATE_PATH, json=payload) as resp:
                    resp.raise_for_status()
                    async for line in resp.aiter_lines():
                        if not line.strip():
                            continue
                        try:
                            chunk = json.loads(line)
                        except json.JSONDecodeError:
                            continue
                        token = chunk.get("response", "")
                        if token:
                            yield token
                        if chunk.get("done", False):
                            return
        except httpx.ConnectError as exc:
            raise AIUnavailableError(
                f"Ollama streaming baglantisi kurulamadi ({self.host}): {exc}"
            ) from exc
        except httpx.TimeoutException as exc:
            raise AITimeoutError(
                f"Ollama streaming zaman asimina ugradi ({self.timeout}s)"
            ) from exc

    async def is_available(self) -> bool:
        """
        Ollama servisinin erisilebilir olup olmadigini kontrol eder.

        Returns:
            True -> servis calisiyor ve model listesi alindi.
            False -> herhangi bir hata durumunda.
        """
        try:
            async with self._client() as client:
                resp = await client.get(self.TAGS_PATH)
                return resp.status_code == 200
        except Exception as exc:
            logger.debug("Ollama erisilebilirlik kontrolu basarisiz: %s", exc)
            return False


# ---------------------------------------------------------------------------
# Modul seviyesinde varsayilan istemci
# ---------------------------------------------------------------------------

_default_client: Optional[OllamaClient] = None


def get_client() -> OllamaClient:
    """
    Paylasilan varsayilan OllamaClient nesnesini doner (lazy singleton).

    Her cagri yeni bir nesne olusturmak yerine tek ornegi paylasiriz.
    Farkli host/model/timeout gerekiyorsa dogrudan OllamaClient() cagir.
    """
    global _default_client
    if _default_client is None:
        _default_client = OllamaClient()
    return _default_client


# ---------------------------------------------------------------------------
# Prompt sabitleri
# ---------------------------------------------------------------------------

_SUBDOMAIN_SCORING_PROMPT = textwrap.dedent("""\
    Sen uzman bir penetrasyon test uzmanisın. Asagidaki subdomain verilerini analiz et.
    Her subdomain icin 0-100 arasi bir saldiri oncelik skoru belirle.

    Puanlama kriterleri:
    - Subdomain ismi: admin, api, dev, staging, test, backup, portal, vpn, jenkins, grafana,
      jira, confluence gibi isimler yuksek puan alir
    - HTTP status: 200 aktif (+15), 403 ilginc (korumali icerik) (+10), 301/302 (+5)
    - Teknoloji stack: Eski/bilinen CVE'li surumler (+20), dinamik framework (+10), CDN (+0)
    - WAF varligi: degerli hedef anlamina gelir ama bypass gerektirir (+5)
    - Server basligi: surum ifsaati (+10)

    Subdomain Verisi:
    {json_data}

    SADECE asagidaki JSON formatinda yanit ver, baska aciklama ekleme:
    [
      {{
        "subdomain": "api.example.com",
        "score": 87,
        "reasoning": "API endpoint + eski Express.js surumu + WAF yok.",
        "tags": ["api", "no-waf", "outdated-software"],
        "recommended_tests": ["sqli", "idor", "auth-bypass"],
        "priority": "critical"
      }}
    ]
    priority alani: critical (80-100) | high (60-79) | medium (40-59) | low (0-39)
""")

_URL_RISK_SCORING_PROMPT = textwrap.dedent("""\
    Penetrasyon testi uzmani olarak URL listesini analiz et.

    Hedef: {target}
    Teknoloji Stack: {tech_stack}
    Tarama Modu: {scan_mode}

    URL Listesi (kaynak ve parametrelerle birlikte):
    {url_json_list}

    Her URL icin risk degerlendirmesi yap. Sunlara dikkat et:
    - Parametre isimleri ve sayisi
    - URL path'indeki hassas kelimeler
    - Endpoint'in amaci ve acik barindirma potansiyeli
    - Parametre deger kaliplari (id=1 -> IDOR, file= -> LFI gibi)

    SADECE JSON formatinda yanit ver:
    {{
      "analyzed": [
        {{
          "url": "https://...",
          "risk_score": 85,
          "vuln_categories": ["sqli", "idor"],
          "keywords": ["id", "admin"],
          "priority": "high",
          "notes": "Kullanici ID'si parametre olarak geciyor, IDOR ve SQLi yuksek ihtimal.",
          "suggested_tests": ["sqli", "idor"]
        }}
      ],
      "summary": "Toplam X URL analiz edildi. Y tanesi yuksek oncelikli..."
    }}
""")

_PRE_TEST_ANALYSIS_PROMPT = textwrap.dedent("""\
    Asagidaki URL'ler icin {test_type} testi yapilacak.

    Hedef URL'ler:
    {url_list}

    Teknoloji Stack: {tech_stack}
    WAF: {waf_name}

    Her URL icin:
    1. Bu test tipinin basarili olma ihtimali (yuksek/orta/dusuk)
    2. Oncelikle denenmesi gereken payload'lar veya vektorler
    3. Dikkat edilmesi gereken ozel durumlar

    SADECE JSON formatinda yanit ver:
    {{
      "pre_analysis": [
        {{
          "url": "https://...",
          "success_probability": "high",
          "priority_payloads": ["payload1", "payload2"],
          "special_notes": "Login endpoint, CSRF token kontrol edilmeli",
          "suggested_tool_flags": "--level=3 --risk=2"
        }}
      ]
    }}
""")

_WAF_BYPASS_PROMPT = textwrap.dedent("""\
    Hedef sistemde {waf_name} WAF tespit edildi ve payload engellendi.

    Hedef URL: {url}
    Test Tipi: {vuln_type}
    Engellenen Payload: {blocked_payload}
    WAF Response Status: {waf_status_code}
    WAF Response Snippet: {waf_response_snippet}
    Teknoloji Stack: {tech_stack}

    {waf_name} WAF'i bypass etmek icin en az 5 teknik oner.

    SADECE JSON formatinda yanit ver:
    {{
      "waf_identified": "{waf_name}",
      "bypass_techniques": [
        {{
          "name": "Unicode Encoding",
          "description": "Payload karakterlerini unicode escape ile kodla",
          "example_payload": "<scr\\u0069pt>alert(1)</scr\\u0069pt>",
          "success_probability": "medium",
          "tool_flags": "--tamper=charunicodeescape",
          "applicable_to": ["dalfox", "sqlmap"]
        }}
      ],
      "recommended_order": [1, 3, 2, 5, 4]
    }}
""")

_FINDING_ANALYSIS_PROMPT = textwrap.dedent("""\
    Penetrasyon testi bulgusunu degerlendir.

    Zafiyet Tipi: {vuln_type}
    URL: {url}
    Kullanilan Payload: {payload}
    Arac Ciktisi: {tool_output}

    HTTP Istegi:
    {request_raw}

    HTTP Response (ilgili kisim):
    {response_snippet}

    Degerlendirme yap:
    1. Bu gercek bir acik mi, false positive mi?
    2. Ciddiyeti ve exploit edilebilirlik derecesi
    3. Potansiyel etki
    4. Adim adim PoC
    5. Duzeltme onerisi (kisa)

    SADECE JSON formatinda yanit ver:
    {{
      "is_real_vulnerability": true,
      "confidence": 92,
      "severity": "high",
      "exploitability": "easy",
      "impact": "Saldirgana kullanici tarayicisinda arbitrary JavaScript calistirma imkani saglar.",
      "poc_steps": [
        "1. Su URL'i hedef kullaniciya gonder: ...",
        "2. Kullanici linke tikladiginda payload calisir",
        "3. ..."
      ],
      "fix_recommendation": "Tum output'u htmlspecialchars() ile encode et.",
      "false_positive_risk": "low",
      "false_positive_reason": null
    }}
""")

_CHAT_SYSTEM_PROMPT = textwrap.dedent("""\
    Sen VulnScan AI asistanisin. Kullanici aktif bir penetrasyon testi yapiyor.

    Aktif Tarama Baglami:
    - Hedef: {target}
    - Teknoloji Stack: {tech_stack}
    - Mevcut Faz: {current_phase}
    - Bulunan Subdomainler: {subdomain_count}
    - Bulunan URL'ler: {url_count}
    - Mevcut Bulgular: {finding_count}

    {context_specific_data}

    Kullanici sorusu: {user_message}

    Onemli: Asla kendi basina bir arac calistirmayi onerme, hep kullaniciya secenekler sun.
    Teknik ve kisa yanit ver. Gerekirse payload veya komut ornekleri ver.
""")


# ---------------------------------------------------------------------------
# Yardimci: guvenli AI cagrisi
# ---------------------------------------------------------------------------


async def _safe_generate_json(
    client: OllamaClient,
    prompt: str,
    fallback: Any,
    operation: str,
) -> Any:
    """
    generate_json'u calistirir; hata durumunda fallback doner ve hatay loglar.

    Args:
        client:    OllamaClient ornegi.
        prompt:    Gonderilecek prompt.
        fallback:  Hata halinde donecek deger.
        operation: Log mesajlari icin islem adi.

    Returns:
        JSON nesnesi veya fallback.
    """
    try:
        return await client.generate_json(prompt)
    except AIUnavailableError as exc:
        logger.error("[%s] Ollama erisim hatasi: %s", operation, exc)
        return fallback
    except AITimeoutError as exc:
        logger.error("[%s] Zaman asimi: %s", operation, exc)
        return fallback
    except AIResponseError as exc:
        logger.warning("[%s] Yanit parse hatasi: %s", operation, exc)
        return fallback
    except AIError as exc:
        logger.error("[%s] Genel AI hatasi: %s", operation, exc)
        return fallback


# ---------------------------------------------------------------------------
# 9.1 — Subdomain puanlama
# ---------------------------------------------------------------------------

_SUBDOMAIN_BATCH_SIZE = 20  # Cok buyuk liste modeli bunaltmasin


async def score_subdomains(
    subdomains: List[Dict[str, Any]],
    client: Optional[OllamaClient] = None,
) -> List[Dict[str, Any]]:
    """
    Subdomain listesini AI ile puanlar ve onceliklendirir (Bolum 9.1).

    Buyuk listeler batch'lere bolunur (max 20/batch).

    Args:
        subdomains: Her eleman en azindan 'subdomain' anahtari iceren sozluk.
        client:     Kullanilacak OllamaClient; None ise varsayilan.

    Returns:
        Her elemana score, reasoning, tags, recommended_tests, priority
        eklenmiş sozluk listesi.  AI hata verirse orijinal liste donus yapilir.
    """
    if not subdomains:
        return subdomains

    client = client or get_client()
    results: List[Dict[str, Any]] = []

    for i in range(0, len(subdomains), _SUBDOMAIN_BATCH_SIZE):
        batch = subdomains[i: i + _SUBDOMAIN_BATCH_SIZE]
        prompt = _SUBDOMAIN_SCORING_PROMPT.format(
            json_data=json.dumps(batch, ensure_ascii=False, indent=2)
        )
        scored: Any = await _safe_generate_json(
            client, prompt, fallback=None, operation="score_subdomains"
        )

        if not isinstance(scored, list):
            logger.warning(
                "score_subdomains: beklenmeyen yanit tipi (%s), batch atlaniyor",
                type(scored).__name__,
            )
            results.extend(batch)
            continue

        # Modelin donduugu sozluklerle orijinal verileri birlestir
        scored_map = {item.get("subdomain"): item for item in scored if isinstance(item, dict)}
        for orig in batch:
            key = orig.get("subdomain", "")
            merged = dict(orig)
            if key in scored_map:
                ai = scored_map[key]
                merged.update(
                    {
                        "ai_score": ai.get("score"),
                        "ai_analysis": ai.get("reasoning"),
                        "ai_tags": ai.get("tags", []),
                        "recommended_tests": ai.get("recommended_tests", []),
                        "priority": ai.get("priority"),
                    }
                )
            results.append(merged)

    return results


# ---------------------------------------------------------------------------
# 9.2 — URL risk puanlama
# ---------------------------------------------------------------------------

_URL_BATCH_SIZE = 50


async def analyze_urls(
    urls: List[Dict[str, Any]],
    target: str,
    tech_stack: Optional[List[str]] = None,
    scan_mode: str = "normal",
    client: Optional[OllamaClient] = None,
) -> List[Dict[str, Any]]:
    """
    URL listesini AI ile risk skorlar (Bolum 9.2).

    Buyuk listeler max 50 URL'lik batch'lere bolunur.

    Args:
        urls:       Analiz edilecek URL sozlukleri.
        target:     Hedef domain/IP.
        tech_stack: Tespit edilen teknoloji listesi.
        scan_mode:  'stealth' | 'normal' | 'aggressive'
        client:     Kullanilacak OllamaClient; None ise varsayilan.

    Returns:
        Her URL'ye ai_analysis, risk_score, vuln_categories, keywords eklenmiş liste.
    """
    if not urls:
        return urls

    client = client or get_client()
    stack_str = ", ".join(tech_stack) if tech_stack else "Tespit edilemedi"
    results: List[Dict[str, Any]] = []

    for i in range(0, len(urls), _URL_BATCH_SIZE):
        batch = urls[i: i + _URL_BATCH_SIZE]
        prompt = _URL_RISK_SCORING_PROMPT.format(
            target=target,
            tech_stack=stack_str,
            scan_mode=scan_mode,
            url_json_list=json.dumps(batch, ensure_ascii=False, indent=2),
        )

        data: Any = await _safe_generate_json(
            client, prompt, fallback=None, operation="analyze_urls"
        )

        if not isinstance(data, dict) or "analyzed" not in data:
            logger.warning("analyze_urls: beklenen 'analyzed' anahtari yok, batch atlaniyor")
            results.extend(batch)
            continue

        analyzed_map: Dict[str, Dict] = {
            item.get("url", ""): item
            for item in data["analyzed"]
            if isinstance(item, dict)
        }

        for orig in batch:
            merged = dict(orig)
            url_key = orig.get("url", "")
            if url_key in analyzed_map:
                ai = analyzed_map[url_key]
                merged.update(
                    {
                        "ai_analysis": ai.get("notes"),
                        "risk_score": ai.get("risk_score", orig.get("risk_score", 0)),
                        "vuln_categories": ai.get("vuln_categories", []),
                        "keywords": ai.get("keywords", []),
                        "suggested_tests": ai.get("suggested_tests", []),
                        "ai_priority": ai.get("priority"),
                    }
                )
            results.append(merged)

    return results


# ---------------------------------------------------------------------------
# 9.3 — Test oncesi analiz
# ---------------------------------------------------------------------------


async def pre_test_analysis(
    urls: List[Dict[str, Any]],
    test_type: str,
    waf: Optional[str] = None,
    tech_stack: Optional[List[str]] = None,
    client: Optional[OllamaClient] = None,
) -> List[Dict[str, Any]]:
    """
    Test baslatilmadan once AI on analizi yapar (Bolum 9.3).

    Args:
        urls:       Test edilecek URL sozlukleri.
        test_type:  'xss' | 'sqli' | 'lfi' | 'redirect' | 'ssrf' | 'nuclei'
        waf:        Tespit edilen WAF adi; None ise "Tespit edilmedi"
        tech_stack: Tespit edilen teknolojiler.
        client:     Kullanilacak OllamaClient; None ise varsayilan.

    Returns:
        Her URL icin success_probability, priority_payloads,
        special_notes, suggested_tool_flags eklenmis liste.
    """
    if not urls:
        return []

    client = client or get_client()
    stack_str = ", ".join(tech_stack) if tech_stack else "Tespit edilemedi"
    waf_str = waf or "Tespit edilmedi"
    url_list_str = "\n".join(u.get("url", str(u)) for u in urls)

    prompt = _PRE_TEST_ANALYSIS_PROMPT.format(
        test_type=test_type,
        url_list=url_list_str,
        tech_stack=stack_str,
        waf_name=waf_str,
    )

    data: Any = await _safe_generate_json(
        client, prompt, fallback=None, operation="pre_test_analysis"
    )

    if not isinstance(data, dict) or "pre_analysis" not in data:
        logger.warning("pre_test_analysis: 'pre_analysis' anahtari bulunamadi")
        return []

    return data["pre_analysis"]


# ---------------------------------------------------------------------------
# 9.4 — WAF bypass onerileri
# ---------------------------------------------------------------------------


async def suggest_waf_bypass(
    waf_name: str,
    url: str,
    vuln_type: str,
    blocked_payload: str,
    waf_status_code: int = 403,
    waf_response_snippet: str = "",
    tech_stack: Optional[List[str]] = None,
    client: Optional[OllamaClient] = None,
) -> Dict[str, Any]:
    """
    WAF bypass teknikleri onerisi uretir (Bolum 9.4).

    Args:
        waf_name:             Tespit edilen WAF adi (Cloudflare, ModSecurity, vb.)
        url:                  Hedef URL.
        vuln_type:            Test tipi (xss, sqli, vb.)
        blocked_payload:      Engellenen payload.
        waf_status_code:      WAF'in dondurdugu HTTP status kodu.
        waf_response_snippet: WAF yanit govdesinden kisa bir parca.
        tech_stack:           Hedef teknoloji listesi.
        client:               Kullanilacak OllamaClient; None ise varsayilan.

    Returns:
        waf_identified, bypass_techniques listesi ve recommended_order iceren sozluk.
        Hata durumunda bos bypass_techniques ile donulur.
    """
    client = client or get_client()
    stack_str = ", ".join(tech_stack) if tech_stack else "Bilinmiyor"

    prompt = _WAF_BYPASS_PROMPT.format(
        waf_name=waf_name,
        url=url,
        vuln_type=vuln_type,
        blocked_payload=blocked_payload,
        waf_status_code=waf_status_code,
        waf_response_snippet=waf_response_snippet[:500],
        tech_stack=stack_str,
    )

    fallback = {"waf_identified": waf_name, "bypass_techniques": [], "recommended_order": []}
    data: Any = await _safe_generate_json(
        client, prompt, fallback=fallback, operation="suggest_waf_bypass"
    )

    if not isinstance(data, dict):
        return fallback

    if "bypass_techniques" not in data:
        data["bypass_techniques"] = []
    if "recommended_order" not in data:
        data["recommended_order"] = list(
            range(1, len(data["bypass_techniques"]) + 1)
        )

    return data


# ---------------------------------------------------------------------------
# 9.5 — Bulgu analizi
# ---------------------------------------------------------------------------


async def analyze_finding(
    finding: Dict[str, Any],
    client: Optional[OllamaClient] = None,
) -> Dict[str, Any]:
    """
    Zafiyet bulgusunu degerlendirir; gercek acik mi yoksa false positive mi? (Bolum 9.5)

    Args:
        finding: En azindan vuln_type, url, payload, tool_output iceren sozluk.
        client:  Kullanilacak OllamaClient; None ise varsayilan.

    Returns:
        is_real_vulnerability, confidence, severity, exploitability,
        impact, poc_steps, fix_recommendation, false_positive_risk iceren sozluk.
        Hata durumunda minimal bir sozluk doner.
    """
    client = client or get_client()

    prompt = _FINDING_ANALYSIS_PROMPT.format(
        vuln_type=finding.get("vuln_type", "unknown"),
        url=finding.get("url", "unknown"),
        payload=finding.get("payload", "Yok"),
        tool_output=finding.get("tool_output", "Yok")[:1000],
        request_raw=finding.get("request_raw", "Yok")[:1000],
        response_snippet=finding.get("response_snippet", "Yok")[:500],
    )

    fallback = {
        "is_real_vulnerability": None,
        "confidence": 0,
        "severity": finding.get("severity", "unknown"),
        "exploitability": "unknown",
        "impact": "AI analizi yapilamadi",
        "poc_steps": [],
        "fix_recommendation": "",
        "false_positive_risk": "unknown",
        "false_positive_reason": None,
    }

    data: Any = await _safe_generate_json(
        client, prompt, fallback=fallback, operation="analyze_finding"
    )

    if not isinstance(data, dict):
        return fallback

    return data


# ---------------------------------------------------------------------------
# 9.6 — AI Chat (tek seferlik + streaming)
# ---------------------------------------------------------------------------


def _build_chat_prompt(message: str, context: Optional[Dict[str, Any]]) -> str:
    """
    Chat prompt'unu baglam sozlugunden olusturur.

    context sozlugundeki beklenen anahtarlar (hepsi opsiyonel):
        target, tech_stack, current_phase, subdomain_count,
        url_count, finding_count, extra_data (serbest metin)
    """
    ctx = context or {}
    tech = ctx.get("tech_stack", [])
    tech_str = ", ".join(tech) if isinstance(tech, list) else str(tech)

    context_specific = ctx.get("extra_data", "")
    if context_specific:
        context_specific = f"Ek Baglam:\n{context_specific}"

    return _CHAT_SYSTEM_PROMPT.format(
        target=ctx.get("target", "Belirtilmemis"),
        tech_stack=tech_str or "Tespit edilemedi",
        current_phase=ctx.get("current_phase", "Belirtilmemis"),
        subdomain_count=ctx.get("subdomain_count", 0),
        url_count=ctx.get("url_count", 0),
        finding_count=ctx.get("finding_count", 0),
        context_specific_data=context_specific,
        user_message=message,
    )


async def chat(
    message: str,
    context: Optional[Dict[str, Any]] = None,
    client: Optional[OllamaClient] = None,
) -> str:
    """
    Kullanicinin serbest sorusunu yanıtlar (Bolum 9.6, tek seferlik).

    Args:
        message: Kullanicinin sorusu.
        context: Tarama baglami sozlugu.
        client:  Kullanilacak OllamaClient; None ise varsayilan.

    Returns:
        Modelin urettigi yanit metni.
        Hata durumunda aciklayici hata mesaji doner (istisna firlatmaz).
    """
    client = client or get_client()
    prompt = _build_chat_prompt(message, context)
    try:
        return await client.generate(prompt)
    except AIUnavailableError:
        return "AI servisi su anda erisemiyor. Lutfen Ollama'nin calistigini kontrol edin."
    except AITimeoutError:
        return "AI yanit suresi asimi. Daha kisa bir soru deneyin veya daha kucuk bir model kullanin."
    except AIError as exc:
        logger.error("chat hatasi: %s", exc)
        return f"AI hatasi: {exc}"


async def chat_stream(
    message: str,
    context: Optional[Dict[str, Any]] = None,
    client: Optional[OllamaClient] = None,
) -> AsyncGenerator[str, None]:
    """
    Kullanicinin sorusunu streaming modda yanıtlar (Bolum 9.6, token akisi).

    Yields:
        Her adimda uretilen metin parcasi.

    Raises:
        AIUnavailableError, AITimeoutError: Caller yakalar.
    """
    client = client or get_client()
    prompt = _build_chat_prompt(message, context)
    async for token in client.generate_stream(prompt):
        yield token
