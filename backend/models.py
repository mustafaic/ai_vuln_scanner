"""
SQLAlchemy ORM modelleri.

Spesifikasyon Bolum 4'teki tum tablolar burada tanimlanmistir:
  scans, subdomains, urls, findings, reports

JSON alanlari SQLite uyumlulugu icin TEXT olarak saklanir;
yardimci property'ler Python dict/list'e donusturur.

Not: Python 3.9 uyumlulugu icin Union/Optional kullanilir (str | None degil).
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any, List, Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    Text,
    event,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base


# ---------------------------------------------------------------------------
# Yardimcilar
# ---------------------------------------------------------------------------


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _new_uuid() -> str:
    return str(uuid.uuid4())


def _json_loads(value: Optional[str]) -> Any:
    """TEXT sutundan Python nesnesine cevirir; None veya gecersiz JSON'da None doner."""
    if value is None:
        return None
    try:
        return json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return None


def _json_dumps(value: Any) -> Optional[str]:
    """Python nesnesini JSON string'e cevirir; None'da None doner."""
    if value is None:
        return None
    return json.dumps(value, ensure_ascii=False)


# ---------------------------------------------------------------------------
# Scan
# ---------------------------------------------------------------------------


class Scan(Base):
    """
    Tek bir tarama oturumunu temsil eder.

    status gecisleri:
        pending -> running -> completed
                           -> paused -> running (resume)
                           -> stopped
                           -> failed
    """

    __tablename__ = "scans"

    id: Mapped[str] = mapped_column(Text, primary_key=True, default=_new_uuid)
    name: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    target: Mapped[str] = mapped_column(Text, nullable=False)
    scope: Mapped[str] = mapped_column(Text, nullable=False)         # 'single' | 'subdomains'
    mode: Mapped[str] = mapped_column(Text, nullable=False)          # 'stealth'|'normal'|'aggressive'
    _config: Mapped[Optional[str]] = mapped_column("config", Text, nullable=True)

    status: Mapped[str] = mapped_column(Text, nullable=False, default="pending")
    current_phase: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    progress: Mapped[int] = mapped_column(Integer, default=0)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Iliskiler
    subdomains: Mapped[List["Subdomain"]] = relationship(
        "Subdomain", back_populates="scan", cascade="all, delete-orphan", lazy="select"
    )
    urls: Mapped[List["Url"]] = relationship(
        "Url", back_populates="scan", cascade="all, delete-orphan", lazy="select"
    )
    findings: Mapped[List["Finding"]] = relationship(
        "Finding", back_populates="scan", cascade="all, delete-orphan", lazy="select"
    )
    report: Mapped[Optional["Report"]] = relationship(
        "Report",
        back_populates="scan",
        cascade="all, delete-orphan",
        uselist=False,
        lazy="select",
    )

    # JSON property -- config
    @property
    def config(self) -> Optional[dict]:
        return _json_loads(self._config)

    @config.setter
    def config(self, value: Optional[dict]) -> None:
        self._config = _json_dumps(value)

    def __repr__(self) -> str:
        return f"<Scan id={self.id!r} target={self.target!r} status={self.status!r}>"


# ---------------------------------------------------------------------------
# Subdomain
# ---------------------------------------------------------------------------


class Subdomain(Base):
    """Bir taramada kesfedilen subdomain kaydi."""

    __tablename__ = "subdomains"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    scan_id: Mapped[str] = mapped_column(
        Text, ForeignKey("scans.id", ondelete="CASCADE"), nullable=False
    )

    subdomain: Mapped[str] = mapped_column(Text, nullable=False)
    _ip_addresses: Mapped[Optional[str]] = mapped_column("ip_addresses", Text, nullable=True)
    status_code: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    title: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    _tech_stack: Mapped[Optional[str]] = mapped_column("tech_stack", Text, nullable=True)
    server: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    cdn: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    waf: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_alive: Mapped[bool] = mapped_column(Boolean, default=True)

    ai_score: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    ai_analysis: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    _ai_tags: Mapped[Optional[str]] = mapped_column("ai_tags", Text, nullable=True)
    is_selected: Mapped[bool] = mapped_column(Boolean, default=False)

    source: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow
    )

    # Iliskiler
    scan: Mapped["Scan"] = relationship("Scan", back_populates="subdomains")
    urls: Mapped[List["Url"]] = relationship(
        "Url", back_populates="subdomain", cascade="all, delete-orphan", lazy="select"
    )

    # JSON property'ler
    @property
    def ip_addresses(self) -> Optional[List[str]]:
        return _json_loads(self._ip_addresses)

    @ip_addresses.setter
    def ip_addresses(self, value: Optional[List[str]]) -> None:
        self._ip_addresses = _json_dumps(value)

    @property
    def tech_stack(self) -> Optional[List[str]]:
        return _json_loads(self._tech_stack)

    @tech_stack.setter
    def tech_stack(self, value: Optional[List[str]]) -> None:
        self._tech_stack = _json_dumps(value)

    @property
    def ai_tags(self) -> Optional[List[str]]:
        return _json_loads(self._ai_tags)

    @ai_tags.setter
    def ai_tags(self, value: Optional[List[str]]) -> None:
        self._ai_tags = _json_dumps(value)

    def __repr__(self) -> str:
        return f"<Subdomain id={self.id} subdomain={self.subdomain!r} score={self.ai_score}>"


# ---------------------------------------------------------------------------
# Url
# ---------------------------------------------------------------------------


class Url(Base):
    """Kesfedilen veya taranan bir URL kaydi."""

    __tablename__ = "urls"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    scan_id: Mapped[str] = mapped_column(
        Text, ForeignKey("scans.id", ondelete="CASCADE"), nullable=False
    )
    subdomain_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("subdomains.id"), nullable=True
    )

    url: Mapped[str] = mapped_column(Text, nullable=False)
    method: Mapped[str] = mapped_column(Text, default="GET")
    source: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status_code: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    content_type: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    _params: Mapped[Optional[str]] = mapped_column("params", Text, nullable=True)
    param_count: Mapped[int] = mapped_column(Integer, default=0)
    _vuln_categories: Mapped[Optional[str]] = mapped_column("vuln_categories", Text, nullable=True)
    _keywords: Mapped[Optional[str]] = mapped_column("keywords", Text, nullable=True)

    risk_score: Mapped[int] = mapped_column(Integer, default=0)
    ai_analysis: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_tested: Mapped[bool] = mapped_column(Boolean, default=False)
    is_interesting: Mapped[bool] = mapped_column(Boolean, default=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow
    )

    # Iliskiler
    scan: Mapped["Scan"] = relationship("Scan", back_populates="urls")
    subdomain: Mapped[Optional["Subdomain"]] = relationship("Subdomain", back_populates="urls")
    findings: Mapped[List["Finding"]] = relationship(
        "Finding", back_populates="url", cascade="all, delete-orphan", lazy="select"
    )

    # JSON property'ler
    @property
    def params(self) -> Optional[List[dict]]:
        return _json_loads(self._params)

    @params.setter
    def params(self, value: Optional[List[dict]]) -> None:
        self._params = _json_dumps(value)
        if value is not None:
            self.param_count = len(value)

    @property
    def vuln_categories(self) -> Optional[List[str]]:
        return _json_loads(self._vuln_categories)

    @vuln_categories.setter
    def vuln_categories(self, value: Optional[List[str]]) -> None:
        self._vuln_categories = _json_dumps(value)

    @property
    def keywords(self) -> Optional[List[str]]:
        return _json_loads(self._keywords)

    @keywords.setter
    def keywords(self, value: Optional[List[str]]) -> None:
        self._keywords = _json_dumps(value)

    def __repr__(self) -> str:
        return f"<Url id={self.id} url={self.url!r} risk={self.risk_score}>"


# ---------------------------------------------------------------------------
# Finding
# ---------------------------------------------------------------------------


class Finding(Base):
    """Bir testte bulunan guvenlik acigi kaydi."""

    __tablename__ = "findings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    scan_id: Mapped[str] = mapped_column(
        Text, ForeignKey("scans.id", ondelete="CASCADE"), nullable=False
    )
    url_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("urls.id"), nullable=True)

    vuln_type: Mapped[str] = mapped_column(Text, nullable=False)
    severity: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    payload: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    evidence: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    request_raw: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    response_snippet: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    tool_used: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    ai_confidence: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    ai_analysis: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    ai_poc: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    waf_bypassed: Mapped[bool] = mapped_column(Boolean, default=False)
    bypass_technique: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    status: Mapped[str] = mapped_column(Text, default="new")
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow
    )

    # Iliskiler
    scan: Mapped["Scan"] = relationship("Scan", back_populates="findings")
    url: Mapped[Optional["Url"]] = relationship("Url", back_populates="findings")

    def __repr__(self) -> str:
        return (
            f"<Finding id={self.id} type={self.vuln_type!r} "
            f"severity={self.severity!r} status={self.status!r}>"
        )


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------


class Report(Base):
    """Bir taramanin ozet raporu (scan basina bir tane)."""

    __tablename__ = "reports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    scan_id: Mapped[str] = mapped_column(
        Text, ForeignKey("scans.id"), nullable=False, unique=True
    )

    executive_summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    total_subdomains: Mapped[int] = mapped_column(Integer, default=0)
    live_subdomains: Mapped[int] = mapped_column(Integer, default=0)
    total_urls: Mapped[int] = mapped_column(Integer, default=0)
    total_findings: Mapped[int] = mapped_column(Integer, default=0)
    critical_count: Mapped[int] = mapped_column(Integer, default=0)
    high_count: Mapped[int] = mapped_column(Integer, default=0)
    medium_count: Mapped[int] = mapped_column(Integer, default=0)
    low_count: Mapped[int] = mapped_column(Integer, default=0)
    info_count: Mapped[int] = mapped_column(Integer, default=0)

    _top_findings: Mapped[Optional[str]] = mapped_column("top_findings", Text, nullable=True)
    ai_summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    scan_duration: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow
    )

    # Iliski
    scan: Mapped["Scan"] = relationship("Scan", back_populates="report")

    @property
    def top_findings(self) -> Optional[List[dict]]:
        return _json_loads(self._top_findings)

    @top_findings.setter
    def top_findings(self, value: Optional[List[dict]]) -> None:
        self._top_findings = _json_dumps(value)

    def __repr__(self) -> str:
        return (
            f"<Report id={self.id} scan_id={self.scan_id!r} "
            f"findings={self.total_findings}>"
        )


# ---------------------------------------------------------------------------
# SQLAlchemy event: updated_at otomatik guncelleme
# ---------------------------------------------------------------------------


@event.listens_for(Scan, "before_update")
def _scan_before_update(mapper: Any, connection: Any, target: Scan) -> None:
    """Scan kaydi guncellenince updated_at'i taze tutar."""
    target.updated_at = _utcnow()
