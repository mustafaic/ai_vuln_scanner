"""
Rapor endpoint'leri — Spesifikasyon Bölüm 5.6.

Endpoint'ler:
    GET /api/reports           → Tüm raporlar
    GET /api/reports/{scan_id} → Tek tarama raporu
"""

from __future__ import annotations

import math
from typing import Any, List

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models import Report, Scan
from schemas import PaginatedResponse, ReportResponse

router = APIRouter(prefix="/api/reports", tags=["reports"])


# ---------------------------------------------------------------------------
# Endpoint'ler
# ---------------------------------------------------------------------------


@router.get("", response_model=PaginatedResponse)
async def list_reports(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
) -> PaginatedResponse:
    """
    Tüm raporları oluşturulma tarihine göre tersten sıralı listeler.

    Her rapor kaydı ilgili tarama adını ve hedefini içerir.
    """
    count_result = await db.execute(select(func.count(Report.id)))
    total = count_result.scalar() or 0

    result = await db.execute(
        select(Report)
        .order_by(desc(Report.created_at))
        .offset((page - 1) * limit)
        .limit(limit)
    )
    reports = result.scalars().all()

    items = [ReportResponse.model_validate(r) for r in reports]
    pages = math.ceil(total / limit) if limit else 1

    return PaginatedResponse(
        total=total,
        page=page,
        limit=limit,
        pages=pages,
        items=items,
    )


@router.get("/{scan_id}", response_model=ReportResponse)
async def get_report(
    scan_id: str,
    db: AsyncSession = Depends(get_db),
) -> ReportResponse:
    """
    Belirtilen taramaya ait raporu döndürür.

    Tarama yoksa 404, rapor henüz oluşturulmamışsa da 404 döner.
    """
    # Taramanın var olduğunu doğrula
    scan_result = await db.execute(select(Scan).where(Scan.id == scan_id))
    if scan_result.scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail=f"Tarama bulunamadı: {scan_id}")

    # Raporu al
    result = await db.execute(
        select(Report).where(Report.scan_id == scan_id)
    )
    report = result.scalar_one_or_none()
    if report is None:
        raise HTTPException(
            status_code=404,
            detail="Bu tarama için henüz rapor oluşturulmadı. Tarama tamamlanana kadar bekleyin.",
        )

    return ReportResponse.model_validate(report)
