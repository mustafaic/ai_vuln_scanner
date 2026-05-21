"""
Tarama endpoint'leri — Spesifikasyon Bölüm 5.2 – 5.5.

Endpoint'ler:
    POST   /api/scans
    GET    /api/scans
    GET    /api/scans/{scan_id}
    DELETE /api/scans/{scan_id}
    POST   /api/scans/{scan_id}/start
    POST   /api/scans/{scan_id}/pause
    POST   /api/scans/{scan_id}/resume
    POST   /api/scans/{scan_id}/stop
    GET    /api/scans/{scan_id}/subdomains
    PATCH  /api/scans/{scan_id}/subdomains/select
    GET    /api/scans/{scan_id}/urls
    PATCH  /api/urls/{url_id}
    POST   /api/scans/{scan_id}/test/start
    POST   /api/scans/{scan_id}/test/waf-bypass
    GET    /api/scans/{scan_id}/findings
    PATCH  /api/findings/{finding_id}
"""

from __future__ import annotations

import math
import re
import uuid
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request
from sqlalchemy import asc, desc, func, select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models import Finding, Scan, Subdomain, Url
from schemas import (
    FindingResponse,
    FindingUpdate,
    MessageResponse,
    PaginatedResponse,
    ScanCreate,
    ScanListResponse,
    ScanResponse,
    SubdomainResponse,
    SubdomainSelectBody,
    TestStartRequest,
    UrlResponse,
    UrlUpdate,
    WafBypassRequest,
)

router = APIRouter(prefix="/api/scans", tags=["scans"])

# findings ve urls için ayrı prefix gerekiyor
findings_router = APIRouter(prefix="/api/findings", tags=["findings"])
urls_router = APIRouter(prefix="/api/urls", tags=["urls"])

# ---------------------------------------------------------------------------
# Yardımcılar
# ---------------------------------------------------------------------------

_DOMAIN_RE = re.compile(
    r"^(?:[a-z0-9](?:[a-z0-9\-]{0,61}[a-z0-9])?\.)+[a-z]{2,}$", re.I
)
_IP_RE = re.compile(
    r"^(?:\d{1,3}\.){3}\d{1,3}$"
)


def _validate_target(target: str) -> None:
    """Domain veya IP formatı değilse 400 fırlatır."""
    if not (_DOMAIN_RE.match(target) or _IP_RE.match(target)):
        raise HTTPException(
            status_code=400,
            detail=f"Geçersiz hedef: '{target}'. Geçerli bir domain (örn. example.com) veya IP adresi girin.",
        )


def _get_orchestrator(request: Request):
    return request.app.state.orchestrator


async def _get_scan_or_404(scan_id: str, db: AsyncSession) -> Scan:
    result = await db.execute(select(Scan).where(Scan.id == scan_id))
    scan = result.scalar_one_or_none()
    if scan is None:
        raise HTTPException(status_code=404, detail=f"Tarama bulunamadı: {scan_id}")
    return scan


def _paginate(items: List[Any], page: int, limit: int, total: int) -> PaginatedResponse:
    return PaginatedResponse(
        total=total,
        page=page,
        limit=limit,
        pages=math.ceil(total / limit) if limit else 1,
        items=items,
    )


# ===========================================================================
# Tarama CRUD
# ===========================================================================


@router.post("", response_model=ScanResponse, status_code=201)
async def create_scan(
    body: ScanCreate,
    db: AsyncSession = Depends(get_db),
) -> ScanResponse:
    """Yeni tarama kaydı oluşturur (henüz başlatmaz)."""
    _validate_target(body.target)

    scan = Scan(
        id=str(uuid.uuid4()),
        name=body.name,
        target=body.target,
        scope=body.scope,
        mode=body.mode,
        status="pending",
    )
    scan.config = body.config
    db.add(scan)
    await db.flush()
    return ScanResponse.model_validate(scan)


@router.get("", response_model=PaginatedResponse)
async def list_scans(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    status: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
) -> PaginatedResponse:
    """Tüm taramaları sayfalandırmalı listeler."""
    query = select(Scan)
    if status:
        query = query.where(Scan.status == status)

    count_result = await db.execute(select(func.count()).select_from(query.subquery()))
    total = count_result.scalar() or 0

    query = query.order_by(desc(Scan.created_at)).offset((page - 1) * limit).limit(limit)
    result = await db.execute(query)
    scans = result.scalars().all()

    # Toplu istatistik sorguları (N+1 önleme)
    scan_ids = [s.id for s in scans]
    sub_map: dict = {}
    url_map: dict = {}
    finding_map: dict = {}
    sev_map: dict = {}
    if scan_ids:
        sub_rows = (await db.execute(
            select(Subdomain.scan_id, func.count(Subdomain.id).label("cnt"))
            .where(Subdomain.scan_id.in_(scan_ids))
            .group_by(Subdomain.scan_id)
        )).all()
        url_rows = (await db.execute(
            select(Url.scan_id, func.count(Url.id).label("cnt"))
            .where(Url.scan_id.in_(scan_ids))
            .group_by(Url.scan_id)
        )).all()
        finding_rows = (await db.execute(
            select(Finding.scan_id, func.count(Finding.id).label("cnt"))
            .where(Finding.scan_id.in_(scan_ids))
            .group_by(Finding.scan_id)
        )).all()
        # Severity bazlı bulgu sayısı (finding_stats)
        sev_rows = (await db.execute(
            select(Finding.scan_id, Finding.severity, func.count(Finding.id).label("cnt"))
            .where(Finding.scan_id.in_(scan_ids))
            .group_by(Finding.scan_id, Finding.severity)
        )).all()
        sub_map = {r.scan_id: r.cnt for r in sub_rows}
        url_map = {r.scan_id: r.cnt for r in url_rows}
        finding_map = {r.scan_id: r.cnt for r in finding_rows}
        for r in sev_rows:
            sev_map.setdefault(r.scan_id, {})[r.severity] = r.cnt

    items = []
    for s in scans:
        resp = ScanListResponse.model_validate(s)
        resp.subdomain_count = sub_map.get(s.id, 0)
        resp.url_count = url_map.get(s.id, 0)
        resp.finding_count = finding_map.get(s.id, 0)
        resp.finding_stats = sev_map.get(s.id, {})
        items.append(resp)

    return _paginate(items, page, limit, total)


@router.get("/{scan_id}", response_model=ScanResponse)
async def get_scan(
    scan_id: str,
    db: AsyncSession = Depends(get_db),
) -> ScanResponse:
    """Tarama detayını istatistiklerle döndürür."""
    scan = await _get_scan_or_404(scan_id, db)

    sub_count = (await db.execute(
        select(func.count(Subdomain.id)).where(Subdomain.scan_id == scan_id)
    )).scalar() or 0
    url_count = (await db.execute(
        select(func.count(Url.id)).where(Url.scan_id == scan_id)
    )).scalar() or 0
    finding_count = (await db.execute(
        select(func.count(Finding.id)).where(Finding.scan_id == scan_id)
    )).scalar() or 0

    resp = ScanResponse.model_validate(scan)
    resp.subdomain_count = sub_count
    resp.url_count = url_count
    resp.finding_count = finding_count
    return resp


@router.delete("/{scan_id}", response_model=MessageResponse)
async def delete_scan(
    scan_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> MessageResponse:
    """Taramayı ve ilgili tüm verileri siler."""
    scan = await _get_scan_or_404(scan_id, db)

    # Çalışıyorsa önce durdur
    orch = _get_orchestrator(request)
    if scan_id in orch.active_scans:
        await orch.stop_scan(scan_id)

    await db.delete(scan)
    return MessageResponse(message=f"Tarama silindi: {scan_id}")


# ===========================================================================
# Tarama kontrolü
# ===========================================================================


@router.post("/{scan_id}/start", response_model=MessageResponse)
async def start_scan(
    scan_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> MessageResponse:
    """Taramayı arka planda başlatır."""
    scan = await _get_scan_or_404(scan_id, db)

    if scan.status == "running":
        raise HTTPException(status_code=400, detail="Tarama zaten çalışıyor.")
    if scan.status == "completed":
        raise HTTPException(status_code=400, detail="Tarama zaten tamamlandı.")

    orch = _get_orchestrator(request)
    try:
        await orch.start_scan(scan_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    return MessageResponse(message="Tarama başlatıldı.")


@router.post("/{scan_id}/pause", response_model=MessageResponse)
async def pause_scan(
    scan_id: str,
    request: Request,
) -> MessageResponse:
    """Çalışan taramayı duraklatır."""
    orch = _get_orchestrator(request)
    try:
        await orch.pause_scan(scan_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Aktif tarama bulunamadı.")
    return MessageResponse(message="Tarama duraklatıldı.")


@router.post("/{scan_id}/resume", response_model=MessageResponse)
async def resume_scan(
    scan_id: str,
    request: Request,
) -> MessageResponse:
    """Duraklatılmış taramayı devam ettirir."""
    orch = _get_orchestrator(request)
    try:
        await orch.resume_scan(scan_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Aktif tarama bulunamadı.")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return MessageResponse(message="Tarama devam ettiriliyor.")


@router.post("/{scan_id}/stop", response_model=MessageResponse)
async def stop_scan(
    scan_id: str,
    request: Request,
) -> MessageResponse:
    """Taramayı durdurur."""
    orch = _get_orchestrator(request)
    try:
        await orch.stop_scan(scan_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Aktif tarama bulunamadı.")
    return MessageResponse(message="Tarama durduruldu.")


# ===========================================================================
# Subdomain endpoint'leri
# ===========================================================================


@router.get("/{scan_id}/subdomains", response_model=PaginatedResponse)
async def list_subdomains(
    scan_id: str,
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
    sort_by: str = Query("ai_score", regex="^(subdomain|ai_score|status_code|created_at)$"),
    sort_dir: str = Query("desc", regex="^(asc|desc)$"),
    min_score: Optional[int] = Query(None, ge=0, le=100),
    has_waf: Optional[bool] = Query(None),
    is_alive: Optional[bool] = Query(None),
    status_code: Optional[int] = Query(None),
    db: AsyncSession = Depends(get_db),
) -> PaginatedResponse:
    """Subdomain listesini filtreli ve sayfalandırmalı döndürür."""
    await _get_scan_or_404(scan_id, db)

    query = select(Subdomain).where(Subdomain.scan_id == scan_id)

    if min_score is not None:
        query = query.where(Subdomain.ai_score >= min_score)
    if has_waf is True:
        query = query.where(Subdomain.waf.isnot(None))
    if has_waf is False:
        query = query.where(Subdomain.waf.is_(None))
    if is_alive is not None:
        query = query.where(Subdomain.is_alive == is_alive)
    if status_code is not None:
        query = query.where(Subdomain.status_code == status_code)

    count_result = await db.execute(select(func.count()).select_from(query.subquery()))
    total = count_result.scalar() or 0

    sort_col = {
        "subdomain": Subdomain.subdomain,
        "ai_score": Subdomain.ai_score,
        "status_code": Subdomain.status_code,
        "created_at": Subdomain.created_at,
    }.get(sort_by, Subdomain.ai_score)
    order_fn = desc if sort_dir == "desc" else asc
    query = query.order_by(order_fn(sort_col)).offset((page - 1) * limit).limit(limit)

    result = await db.execute(query)
    subs = result.scalars().all()

    return _paginate(
        [SubdomainResponse.model_validate(s) for s in subs],
        page, limit, total,
    )


@router.patch("/{scan_id}/subdomains/select", response_model=MessageResponse)
async def select_subdomains(
    scan_id: str,
    body: SubdomainSelectBody,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> MessageResponse:
    """
    Subdomain seçimini toplu günceller.

    select_all=True ise tüm canlı subdomainler seçilir.
    subdomain_ids listesi verilmişse yalnızca bunlar güncellenir.
    Aynı zamanda orchestrator'a subdomain_selection sinyali gönderir.
    """
    await _get_scan_or_404(scan_id, db)

    if body.select_all:
        result = await db.execute(
            select(Subdomain).where(
                Subdomain.scan_id == scan_id,
                Subdomain.is_alive == True,  # noqa: E712
            )
        )
        subs = result.scalars().all()
        for sub in subs:
            sub.is_selected = body.selected
        selected_ids = [sub.id for sub in subs]
    elif body.subdomain_ids:
        result = await db.execute(
            select(Subdomain).where(
                Subdomain.scan_id == scan_id,
                Subdomain.id.in_(body.subdomain_ids),
            )
        )
        subs = result.scalars().all()
        for sub in subs:
            sub.is_selected = body.selected
        selected_ids = [sub.id for sub in subs if body.selected]
    else:
        return MessageResponse(message="Güncellenecek subdomain belirtilmedi.")

    await db.flush()

    # Orkestratöre sinyal gönder (seçim tamamlandıysa)
    if body.selected and selected_ids:
        orch = _get_orchestrator(request)
        if scan_id in orch.active_scans:
            orch.notify_subdomain_selection(scan_id, selected_ids)

    return MessageResponse(
        message=f"{len(selected_ids)} subdomain {'seçildi' if body.selected else 'seçimi kaldırıldı'}."
    )


# ===========================================================================
# URL endpoint'leri
# ===========================================================================


@router.get("/{scan_id}/urls", response_model=PaginatedResponse)
async def list_urls(
    scan_id: str,
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
    category: Optional[str] = Query(None, description="xss, sqli, lfi, redirect, ssrf, idor"),
    keyword: Optional[str] = Query(None),
    min_score: Optional[int] = Query(None, ge=0, le=100),
    source: Optional[str] = Query(None),
    is_tested: Optional[bool] = Query(None),
    is_interesting: Optional[bool] = Query(None),
    db: AsyncSession = Depends(get_db),
) -> PaginatedResponse:
    """URL listesini filtreli ve sayfalandırmalı döndürür."""
    await _get_scan_or_404(scan_id, db)

    query = select(Url).where(Url.scan_id == scan_id)

    if category:
        # JSON TEXT içinde kategori arama (SQLite LIKE)
        query = query.where(Url._vuln_categories.contains(f'"{category}"'))
    if keyword:
        query = query.where(Url._keywords.contains(f'"{keyword}"'))
    if min_score is not None:
        query = query.where(Url.risk_score >= min_score)
    if source:
        query = query.where(Url.source == source)
    if is_tested is not None:
        query = query.where(Url.is_tested == is_tested)
    if is_interesting is not None:
        query = query.where(Url.is_interesting == is_interesting)

    count_result = await db.execute(select(func.count()).select_from(query.subquery()))
    total = count_result.scalar() or 0

    query = (
        query.order_by(desc(Url.risk_score))
        .offset((page - 1) * limit)
        .limit(limit)
    )
    result = await db.execute(query)
    urls = result.scalars().all()

    return _paginate(
        [UrlResponse.model_validate(u) for u in urls],
        page, limit, total,
    )


@urls_router.patch("/{url_id}", response_model=UrlResponse)
async def update_url(
    url_id: int,
    body: UrlUpdate,
    db: AsyncSession = Depends(get_db),
) -> UrlResponse:
    """URL kaydını kısmen günceller (is_interesting, is_tested, vb.)."""
    result = await db.execute(select(Url).where(Url.id == url_id))
    url = result.scalar_one_or_none()
    if url is None:
        raise HTTPException(status_code=404, detail=f"URL bulunamadı: {url_id}")

    update_data = body.model_dump(exclude_none=True)
    for field, value in update_data.items():
        # vuln_categories property setter'ı JSON encode'lar
        setattr(url, field, value)

    await db.flush()
    return UrlResponse.model_validate(url)


# ===========================================================================
# Test fazı endpoint'leri
# ===========================================================================


@router.post("/{scan_id}/test/start", response_model=MessageResponse)
async def start_test(
    scan_id: str,
    body: TestStartRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> MessageResponse:
    """
    Test fazını başlatır.

    URL'lerin ve test tiplerinin doğrulandıktan sonra orkestratöre sinyal gönderir.
    """
    await _get_scan_or_404(scan_id, db)

    # URL'lerin bu taramaya ait olduğunu doğrula
    count_result = await db.execute(
        select(func.count(Url.id)).where(
            Url.scan_id == scan_id,
            Url.id.in_(body.url_ids),
        )
    )
    matched = count_result.scalar() or 0
    if matched != len(body.url_ids):
        raise HTTPException(
            status_code=400,
            detail="Bazı URL ID'leri bu taramaya ait değil.",
        )

    orch = _get_orchestrator(request)
    if scan_id not in orch.active_scans:
        raise HTTPException(
            status_code=400,
            detail="Tarama aktif değil. Önce taramayı başlatın.",
        )

    orch.notify_test_start(scan_id, body.url_ids, body.test_types)
    return MessageResponse(
        message=f"Test başlatıldı: {len(body.url_ids)} URL, {body.test_types}"
    )


@router.post("/{scan_id}/test/waf-bypass", response_model=MessageResponse)
async def waf_bypass(
    scan_id: str,
    body: WafBypassRequest,
    request: Request,
) -> MessageResponse:
    """WAF bypass tekniğini veya atlama kararını testing fazına iletir."""
    orch = _get_orchestrator(request)
    if scan_id not in orch.active_scans:
        raise HTTPException(status_code=400, detail="Tarama aktif değil.")

    if body.technique == "__skip__":
        orch.skip_bypass(scan_id)
        return MessageResponse(message="WAF bypass atlandı.")

    orch.apply_bypass(scan_id, {"name": body.technique})
    return MessageResponse(message=f"WAF bypass uygulandı: {body.technique}")


# ===========================================================================
# Bulgu endpoint'leri
# ===========================================================================


@router.get("/{scan_id}/findings", response_model=PaginatedResponse)
async def list_findings(
    scan_id: str,
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
    severity: Optional[str] = Query(None),
    vuln_type: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
) -> PaginatedResponse:
    """Bulgular listesini filtreli ve sayfalandırmalı döndürür."""
    await _get_scan_or_404(scan_id, db)

    query = select(Finding).where(Finding.scan_id == scan_id).options(selectinload(Finding.url))
    if severity:
        query = query.where(Finding.severity == severity)
    if vuln_type:
        query = query.where(Finding.vuln_type == vuln_type)
    if status:
        query = query.where(Finding.status == status)

    severity_order = {
        "critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4,
    }

    count_result = await db.execute(select(func.count()).select_from(query.subquery()))
    total = count_result.scalar() or 0

    query = query.order_by(desc(Finding.created_at)).offset((page - 1) * limit).limit(limit)
    result = await db.execute(query)
    findings = result.scalars().all()

    return _paginate(
        [FindingResponse.model_validate(f) for f in findings],
        page, limit, total,
    )


@findings_router.patch("/{finding_id}", response_model=FindingResponse)
async def update_finding(
    finding_id: int,
    body: FindingUpdate,
    db: AsyncSession = Depends(get_db),
) -> FindingResponse:
    """Bulgu durumunu veya notlarını günceller."""
    result = await db.execute(
        select(Finding).where(Finding.id == finding_id).options(selectinload(Finding.url))
    )
    finding = result.scalar_one_or_none()
    if finding is None:
        raise HTTPException(status_code=404, detail=f"Bulgu bulunamadı: {finding_id}")

    update_data = body.model_dump(exclude_none=True)
    for field, value in update_data.items():
        setattr(finding, field, value)

    await db.flush()
    return FindingResponse.model_validate(finding)
