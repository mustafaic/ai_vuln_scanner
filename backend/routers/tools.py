"""
Araç yönetimi endpoint'leri — Spesifikasyon Bölüm 5.1.

Endpoint'ler:
    GET  /api/tools/status
    POST /api/tools/{tool}/install   (arka plan görevi)
    POST /api/tools/install-all      (arka plan görevi)

Kurulum işlemleri BackgroundTasks ile yürütülür; ilerleme WebSocket
üzerinden yayınlanır.
"""

from __future__ import annotations

import asyncio
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request

import websocket_manager as ws_events
import tool_manager as tm
from schemas import MessageResponse, ToolStatusResponse, ToolsStatusResponse

router = APIRouter(prefix="/api/tools", tags=["tools"])


# ---------------------------------------------------------------------------
# Yardımcılar
# ---------------------------------------------------------------------------


async def _ws_progress(ws_manager: Any, line: str) -> None:
    """Kurulum ilerleme satırını tüm bağlı istemcilere yayınlar."""
    await ws_manager.broadcast(
        ws_events.notification(title="Araç Kurulumu", body=line)
    )


async def _install_background(
    tool_name: str,
    ws_manager: Any,
) -> None:
    """Arka planda tek araç kurar ve WebSocket ile ilerleme bildirir."""
    async def _cb(line: str) -> None:
        await _ws_progress(ws_manager, line)

    try:
        status = await tm.install_tool(tool_name, progress_callback=_cb)
        if status.installed:
            await ws_manager.broadcast(
                ws_events.notification(
                    title="Kurulum Tamamlandı",
                    body=f"{tool_name} başarıyla kuruldu. Versiyon: {status.version}",
                )
            )
        else:
            await ws_manager.broadcast(
                ws_events.notification(
                    title="Kurulum Başarısız",
                    body=f"{tool_name} kurulamadı. {status.install_error or ''}",
                )
            )
    except Exception as exc:
        await ws_manager.broadcast(
            ws_events.scan_error(f"Araç kurulum hatası ({tool_name}): {exc}")
        )


async def _install_all_background(ws_manager: Any) -> None:
    """Arka planda eksik tüm araçları kurar."""
    async def _cb(line: str) -> None:
        await _ws_progress(ws_manager, line)

    try:
        results = await tm.install_all_missing(progress_callback=_cb)
        installed = [n for n, s in results.items() if s.installed]
        failed = [n for n, s in results.items() if not s.installed]
        await ws_manager.broadcast(
            ws_events.notification(
                title="Toplu Kurulum Tamamlandı",
                body=f"Kuruldu: {len(installed)} araç. "
                     + (f"Başarısız: {', '.join(failed)}" if failed else "Tümü başarılı."),
            )
        )
    except Exception as exc:
        await ws_manager.broadcast(
            ws_events.scan_error(f"Toplu araç kurulum hatası: {exc}")
        )


# ---------------------------------------------------------------------------
# Endpoint'ler
# ---------------------------------------------------------------------------


@router.get("/status", response_model=ToolsStatusResponse)
async def get_tools_status() -> ToolsStatusResponse:
    """Tüm araçların kurulum durumunu döndürür."""
    statuses = await tm.check_all_tools()
    summary = tm.get_tools_summary(statuses)

    tools = [
        ToolStatusResponse(
            name=s.name,
            installed=s.installed,
            binary=s.binary,
            category=s.category,
            phase=s.phase,
            required=s.required,
            version=s.version,
        )
        for s in statuses.values()
    ]

    return ToolsStatusResponse(
        tools=tools,
        all_required_installed=summary["all_required_installed"],
        missing_required=summary["missing_required"],
        missing_optional=summary["missing_optional"],
    )


@router.post("/{tool}/install", response_model=MessageResponse)
async def install_tool(
    tool: str,
    request: Request,
    background_tasks: BackgroundTasks,
) -> MessageResponse:
    """
    Belirtilen aracı arka planda kurar.

    Kurulum ilerleme güncellemeleri WebSocket üzerinden yayınlanır.
    Kurulum devam ederken endpoint hemen yanıt döner.
    """
    # Araç var mı kontrolü
    if tool not in tm.TOOLS:
        raise HTTPException(
            status_code=404,
            detail=f"Bilinmeyen araç: '{tool}'. Geçerli araçlar: {list(tm.TOOLS.keys())}",
        )

    ws_manager = request.app.state.ws_manager
    background_tasks.add_task(_install_background, tool, ws_manager)
    return MessageResponse(
        message=f"'{tool}' kurulumu arka planda başlatıldı. WebSocket üzerinden ilerlemeyi takip edin."
    )


@router.post("/install-all", response_model=MessageResponse)
async def install_all_tools(
    request: Request,
    background_tasks: BackgroundTasks,
) -> MessageResponse:
    """
    Kurulu olmayan tüm araçları arka planda kurar.

    Kurulum ilerleme güncellemeleri WebSocket üzerinden yayınlanır.
    """
    ws_manager = request.app.state.ws_manager
    background_tasks.add_task(_install_all_background, ws_manager)
    return MessageResponse(
        message="Eksik araçların kurulumu arka planda başlatıldı."
    )
