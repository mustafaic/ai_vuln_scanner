"""
Pydantic request/response simalari.

Kural:
  - *Create  -> POST body'si; kullanicidan gelen zorunlu/opsiyonel alanlar
  - *Update  -> PATCH body'si; tum alanlar Optional
  - *Response -> API'nin donurdugu nesne; ORM modelinden populate edilir

JSON TEXT sutunlari (ip_addresses, tech_stack, params, vb.) burada
dogrudan Python dict/list olarak ifade edilir; donusturme ORM katmaninda.

Not: Python 3.9 uyumlulugu icin Optional/List kullanilir.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


# ---------------------------------------------------------------------------
# Ortak base
# ---------------------------------------------------------------------------


class _OrmBase(BaseModel):
    """ORM modellerinden otomatik populate icin ortak base."""

    model_config = ConfigDict(from_attributes=True)


# ===========================================================================
# Scan
# ===========================================================================


class ScanCreate(BaseModel):
    """Yeni tarama olusturma istegi."""

    target: str = Field(..., min_length=1, max_length=253, description="Domain, URL veya IP")
    scope: str = Field(..., pattern="^(single|subdomains)$")
    mode: str = Field("normal", pattern="^(stealth|normal|aggressive)$")
    name: Optional[str] = Field(None, max_length=120)
    config: Optional[Dict[str, Any]] = None

    @field_validator("target")
    @classmethod
    def strip_target(cls, v: str) -> str:
        """Bastaki/sondaki bosluklar ve http(s):// onekini temizler."""
        v = v.strip().lower()
        for prefix in ("https://", "http://"):
            if v.startswith(prefix):
                v = v[len(prefix):]
        return v.rstrip("/")


class ScanUpdate(BaseModel):
    """Tarama alanlarini kismi guncelleme."""

    name: Optional[str] = None
    status: Optional[str] = Field(
        None, pattern="^(pending|running|paused|completed|stopped|failed)$"
    )
    current_phase: Optional[str] = Field(None, pattern="^(recon|discovery|testing)$")
    progress: Optional[int] = Field(None, ge=0, le=100)
    error_message: Optional[str] = None
    completed_at: Optional[datetime] = None
    config: Optional[Dict[str, Any]] = None


class ScanResponse(_OrmBase):
    """Tarama detay yaniti."""

    id: str
    name: Optional[str]
    target: str
    scope: str
    mode: str
    config: Optional[Dict[str, Any]]
    status: str
    current_phase: Optional[str]
    progress: int
    error_message: Optional[str]
    created_at: datetime
    updated_at: datetime
    completed_at: Optional[datetime]

    # Istatistikler (opsiyonel; endpoint tarafindan doldurulabilir)
    subdomain_count: Optional[int] = None
    url_count: Optional[int] = None
    finding_count: Optional[int] = None


class ScanListResponse(_OrmBase):
    """Tarama liste ogesi (agir iliskiler olmadan)."""

    id: str
    name: Optional[str]
    target: str
    scope: str
    mode: str
    status: str
    current_phase: Optional[str]
    progress: int
    created_at: datetime
    updated_at: datetime
    completed_at: Optional[datetime]


# ===========================================================================
# Subdomain
# ===========================================================================


class SubdomainResponse(_OrmBase):
    """Subdomain yaniti."""

    id: int
    scan_id: str
    subdomain: str
    ip_addresses: Optional[List[str]]
    status_code: Optional[int]
    title: Optional[str]
    tech_stack: Optional[List[str]]
    server: Optional[str]
    cdn: Optional[str]
    waf: Optional[str]
    is_alive: bool
    ai_score: Optional[int]
    ai_analysis: Optional[str]
    ai_tags: Optional[List[str]]
    is_selected: bool
    source: Optional[str]
    created_at: datetime


class SubdomainUpdate(BaseModel):
    """Subdomain kismi guncelleme (secim islemleri icin)."""

    is_selected: Optional[bool] = None
    ai_score: Optional[int] = Field(None, ge=0, le=100)
    ai_analysis: Optional[str] = None
    ai_tags: Optional[List[str]] = None


class SubdomainSelectBody(BaseModel):
    """Toplu subdomain secim/secim kaldirma istegi."""

    subdomain_ids: Optional[List[int]] = None
    select_all: bool = False
    selected: bool = True


# ===========================================================================
# Url
# ===========================================================================


class UrlParam(BaseModel):
    """URL parametre nesnesi."""

    name: str
    value: Optional[str] = None


class UrlResponse(_OrmBase):
    """URL yaniti."""

    id: int
    scan_id: str
    subdomain_id: Optional[int]
    url: str
    method: str
    source: Optional[str]
    status_code: Optional[int]
    content_type: Optional[str]
    params: Optional[List[Dict[str, Any]]]
    param_count: int
    vuln_categories: Optional[List[str]]
    keywords: Optional[List[str]]
    risk_score: int
    ai_analysis: Optional[str]
    is_tested: bool
    is_interesting: bool
    created_at: datetime


class UrlUpdate(BaseModel):
    """URL kismi guncelleme."""

    is_interesting: Optional[bool] = None
    is_tested: Optional[bool] = None
    ai_analysis: Optional[str] = None
    risk_score: Optional[int] = Field(None, ge=0, le=100)
    vuln_categories: Optional[List[str]] = None


# ===========================================================================
# Finding
# ===========================================================================


class FindingResponse(_OrmBase):
    """Bulgu yaniti."""

    id: int
    scan_id: str
    url_id: Optional[int]
    vuln_type: str
    severity: str
    title: Optional[str]
    payload: Optional[str]
    evidence: Optional[str]
    request_raw: Optional[str]
    response_snippet: Optional[str]
    tool_used: Optional[str]
    ai_confidence: Optional[int]
    ai_analysis: Optional[str]
    ai_poc: Optional[str]
    waf_bypassed: bool
    bypass_technique: Optional[str]
    status: str
    notes: Optional[str]
    created_at: datetime


class FindingCreate(BaseModel):
    """Yeni bulgu olusturma (arac wrapper'lari tarafindan kullanilir)."""

    scan_id: str
    url_id: Optional[int] = None
    vuln_type: str
    severity: str = Field(..., pattern="^(critical|high|medium|low|info)$")
    title: Optional[str] = None
    payload: Optional[str] = None
    evidence: Optional[str] = None
    request_raw: Optional[str] = None
    response_snippet: Optional[str] = None
    tool_used: Optional[str] = None
    ai_confidence: Optional[int] = Field(None, ge=0, le=100)
    ai_analysis: Optional[str] = None
    ai_poc: Optional[str] = None
    waf_bypassed: bool = False
    bypass_technique: Optional[str] = None


class FindingUpdate(BaseModel):
    """Bulgu kismi guncelleme (kullanici notlari, dogrulama vb.)."""

    status: Optional[str] = Field(None, pattern="^(new|confirmed|false_positive)$")
    notes: Optional[str] = None
    ai_confidence: Optional[int] = Field(None, ge=0, le=100)
    ai_analysis: Optional[str] = None
    ai_poc: Optional[str] = None
    severity: Optional[str] = Field(None, pattern="^(critical|high|medium|low|info)$")


# ===========================================================================
# Report
# ===========================================================================


class ReportResponse(_OrmBase):
    """Rapor yaniti."""

    id: int
    scan_id: str
    executive_summary: Optional[str]
    total_subdomains: int
    live_subdomains: int
    total_urls: int
    total_findings: int
    critical_count: int
    high_count: int
    medium_count: int
    low_count: int
    info_count: int
    top_findings: Optional[List[Dict[str, Any]]]
    ai_summary: Optional[str]
    scan_duration: Optional[int]
    created_at: datetime


# ===========================================================================
# Tool (arac durumu)
# ===========================================================================


class ToolStatusResponse(BaseModel):
    """Tek bir aracin kurulum durumu."""

    name: str
    installed: bool
    binary: str
    category: str
    phase: Optional[str]
    required: bool
    version: Optional[str] = None


class ToolsStatusResponse(BaseModel):
    """Tum araclarin durumu."""

    tools: List[ToolStatusResponse]
    all_required_installed: bool
    missing_required: List[str]
    missing_optional: List[str]


# ===========================================================================
# AI
# ===========================================================================


class AiChatRequest(BaseModel):
    """Serbest AI sohbet istegi."""

    message: str = Field(..., min_length=1)
    context: Optional[Dict[str, Any]] = None


class AiChatResponse(BaseModel):
    """AI sohbet yaniti."""

    response: str
    model: str
    tokens_used: Optional[int] = None


class AiAnalyzeUrlRequest(BaseModel):
    """URL analiz istegi."""

    url_id: int


class AiGeneratePayloadsRequest(BaseModel):
    """Payload uretim istegi."""

    url_id: int
    vuln_type: str
    waf_name: Optional[str] = None


class AiAnalyzeFindingRequest(BaseModel):
    """Bulgu degerlendirme istegi."""

    finding_id: int


class AiGeneratePocRequest(BaseModel):
    """PoC uretim istegi."""

    finding_id: int


# ===========================================================================
# Test fazi
# ===========================================================================


class TestStartRequest(BaseModel):
    """Test baslatma istegi."""

    url_ids: List[int] = Field(..., min_length=1)
    test_types: List[str] = Field(
        ...,
        min_length=1,
        description="xss, sqli, lfi, redirect, ssrf, nuclei",
    )

    @field_validator("test_types")
    @classmethod
    def validate_test_types(cls, v: List[str]) -> List[str]:
        valid = {"xss", "sqli", "lfi", "redirect", "ssrf", "nuclei"}
        invalid = set(v) - valid
        if invalid:
            raise ValueError(f"Gecersiz test tipleri: {invalid}")
        return v


class WafBypassRequest(BaseModel):
    """WAF bypass uygulama istegi."""

    url_id: int
    finding_id: Optional[int] = None
    technique: str


# ===========================================================================
# Genel
# ===========================================================================


class HealthResponse(BaseModel):
    """Saglik kontrolu yaniti."""

    status: str
    version: str
    ollama_status: bool
    db_status: bool


class PaginatedResponse(BaseModel):
    """Sayfalandirmali liste yaniti icin base."""

    total: int
    page: int
    limit: int
    pages: int
    items: List[Any]


class MessageResponse(BaseModel):
    """Basit mesaj yaniti."""

    message: str
    success: bool = True
