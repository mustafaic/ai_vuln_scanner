"""
AI endpoint'leri — Spesifikasyon Bölüm 5.7.

Endpoint'ler:
    POST /api/ai/chat              → Serbest AI sohbeti (streaming)
    POST /api/ai/analyze-url       → URL analizi (AI risk değerlendirmesi)
    POST /api/ai/generate-payloads → Payload üretimi
    POST /api/ai/analyze-finding   → Bulgu değerlendirmesi
    POST /api/ai/generate-poc      → PoC üretimi

Streaming yanıt (chat): text/event-stream formatında token akışı.
Diğer endpoint'ler: JSON yanıt.
"""

from __future__ import annotations

import json
from typing import Any, AsyncGenerator, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

import ai_engine
from database import get_db
from models import Finding, Scan, Subdomain, Url
from schemas import (
    AiAnalyzeFindingRequest,
    AiAnalyzeUrlRequest,
    AiChatRequest,
    AiGeneratePayloadsRequest,
    AiGeneratePocRequest,
    MessageResponse,
)

router = APIRouter(prefix="/api/ai", tags=["ai"])


# ---------------------------------------------------------------------------
# Yardımcılar
# ---------------------------------------------------------------------------


def _get_ai_engine(request: Request):
    return request.app.state.ai_engine


async def _get_url_or_404(url_id: int, db: AsyncSession) -> Url:
    result = await db.execute(select(Url).where(Url.id == url_id))
    url = result.scalar_one_or_none()
    if url is None:
        raise HTTPException(status_code=404, detail=f"URL bulunamadı: {url_id}")
    return url


async def _get_finding_or_404(finding_id: int, db: AsyncSession) -> Finding:
    result = await db.execute(select(Finding).where(Finding.id == finding_id))
    finding = result.scalar_one_or_none()
    if finding is None:
        raise HTTPException(status_code=404, detail=f"Bulgu bulunamadı: {finding_id}")
    return finding


async def _get_scan_context(scan_id: str, db: AsyncSession) -> Dict[str, Any]:
    """Tarama bağlamı sözlüğü oluşturur (AI chat prompt'u için)."""
    from sqlalchemy import func

    scan_result = await db.execute(select(Scan).where(Scan.id == scan_id))
    scan = scan_result.scalar_one_or_none()
    if scan is None:
        return {}

    sub_count = (await db.execute(
        select(func.count(Subdomain.id)).where(Subdomain.scan_id == scan_id)
    )).scalar() or 0
    url_count = (await db.execute(
        select(func.count(Url.id)).where(Url.scan_id == scan_id)
    )).scalar() or 0
    finding_count = (await db.execute(
        select(func.count(Finding.id)).where(Finding.scan_id == scan_id)
    )).scalar() or 0

    return {
        "target": scan.target,
        "current_phase": scan.current_phase,
        "scan_mode": scan.mode,
        "subdomain_count": sub_count,
        "url_count": url_count,
        "finding_count": finding_count,
    }


# ---------------------------------------------------------------------------
# Endpoint'ler
# ---------------------------------------------------------------------------


@router.post("/chat")
async def ai_chat(
    body: AiChatRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    """
    Serbest AI sohbeti — SSE (Server-Sent Events) akışı.

    Her token 'data: <token>\\n\\n' formatında gönderilir.
    Akış bitince 'data: [DONE]\\n\\n' mesajı gönderilir.

    İstemci bağlamda scan_id verirse tarama verileri context'e eklenir.
    """
    client = _get_ai_engine(request)
    context: Optional[Dict[str, Any]] = body.context

    # Tarama bağlamını zenginleştir
    if context and context.get("scan_id"):
        scan_ctx = await _get_scan_context(context["scan_id"], db)
        context = {**context, **scan_ctx}

    async def _token_stream() -> AsyncGenerator[str, None]:
        try:
            async for token in ai_engine.chat_stream(
                message=body.message,
                context=context,
                client=client,
            ):
                # SSE formatı
                yield f"data: {json.dumps({'token': token}, ensure_ascii=False)}\n\n"
        except Exception as exc:
            # İç ağ detaylarını (Docker hostname, port vb.) kullanıcıya gösterme
            import re as _re
            raw = str(exc)
            sanitized = _re.sub(r"for url '[^']*'", "for AI service", raw)
            sanitized = _re.sub(r"https?://[^\s'\"]+", "[AI service URL]", sanitized)
            yield f"data: {json.dumps({'error': sanitized})}\n\n"
        finally:
            yield "data: [DONE]\n\n"

    return StreamingResponse(
        _token_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/analyze-url")
async def analyze_url(
    body: AiAnalyzeUrlRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """
    URL'i AI ile analiz eder ve risk değerlendirmesi yapar.

    DB'deki URL kaydı ai_analysis, risk_score ve vuln_categories
    alanlarıyla güncellenir.
    """
    client = _get_ai_engine(request)
    url_obj = await _get_url_or_404(body.url_id, db)

    # Tarama hedefi ve tech stack bilgisi
    scan_result = await db.execute(select(Scan).where(Scan.id == url_obj.scan_id))
    scan = scan_result.scalar_one_or_none()
    target = scan.target if scan else ""

    # Subdomain tech stack
    tech_stack: Optional[List[str]] = None
    if url_obj.subdomain_id:
        sub_result = await db.execute(
            select(Subdomain).where(Subdomain.id == url_obj.subdomain_id)
        )
        sub = sub_result.scalar_one_or_none()
        if sub:
            tech_stack = sub.tech_stack

    url_data = {
        "url": url_obj.url,
        "params": url_obj.params or [],
        "source": url_obj.source,
        "status_code": url_obj.status_code,
        "vuln_categories": url_obj.vuln_categories or [],
        "keywords": url_obj.keywords or [],
        "risk_score": url_obj.risk_score,
    }

    results = await ai_engine.analyze_urls(
        urls=[url_data],
        target=target,
        tech_stack=tech_stack,
        scan_mode=scan.mode if scan else "normal",
        client=client,
    )

    if results:
        analyzed = results[0]
        url_obj.ai_analysis = analyzed.get("ai_analysis")
        if analyzed.get("risk_score") is not None:
            url_obj.risk_score = analyzed["risk_score"]
        if analyzed.get("vuln_categories"):
            url_obj.vuln_categories = analyzed["vuln_categories"]
        await db.flush()
        return {
            "url_id": body.url_id,
            "ai_analysis": url_obj.ai_analysis,
            "risk_score": url_obj.risk_score,
            "vuln_categories": url_obj.vuln_categories,
            "suggested_tests": analyzed.get("suggested_tests", []),
        }

    return {"url_id": body.url_id, "message": "AI analizi sonuç üretemedi."}


@router.post("/generate-payloads")
async def generate_payloads(
    body: AiGeneratePayloadsRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """
    Belirtilen URL ve zafiyet türü için payload listesi üretir.

    WAF adı verilmişse bypass payload'ları üretir.
    Verilmemişse genel test payload'ları döndürür.
    """
    client = _get_ai_engine(request)
    url_obj = await _get_url_or_404(body.url_id, db)

    if body.waf_name:
        # WAF bypass payload'ları — suggest_waf_bypass kullan
        _sample_payloads: Dict[str, str] = {
            "xss": "<script>alert(1)</script>",
            "sqli": "' OR 1=1--",
            "lfi": "../../../../etc/passwd",
            "ssrf": "http://169.254.169.254/latest/meta-data/",
            "redirect": "https://evil.example.com",
        }
        blocked_payload = _sample_payloads.get(body.vuln_type, "test_payload")

        result = await ai_engine.suggest_waf_bypass(
            waf_name=body.waf_name,
            url=str(url_obj.url),
            vuln_type=body.vuln_type,
            blocked_payload=blocked_payload,
            client=client,
        )
        payloads = [
            t.get("example_payload", "")
            for t in result.get("bypass_techniques", [])
            if t.get("example_payload")
        ]
        return {
            "url_id": body.url_id,
            "vuln_type": body.vuln_type,
            "waf_name": body.waf_name,
            "payloads": payloads,
            "bypass_techniques": result.get("bypass_techniques", []),
        }

    # Genel payload'lar — chat ile üret
    prompt = (
        f"URL: {url_obj.url}\n"
        f"Zafiyet Türü: {body.vuln_type}\n\n"
        f"Bu URL için {body.vuln_type} testi yapmak üzere 10 test payload'ı listele. "
        f"Sadece JSON array döndür: [\"payload1\", \"payload2\", ...]"
    )
    response = await ai_engine.chat(message=prompt, client=client)

    # JSON parse dene
    try:
        import json as _json
        payloads = _json.loads(response)
        if not isinstance(payloads, list):
            payloads = [response]
    except Exception:
        payloads = [line.strip(" -•") for line in response.split("\n") if line.strip()]

    return {
        "url_id": body.url_id,
        "vuln_type": body.vuln_type,
        "waf_name": None,
        "payloads": payloads[:15],
    }


@router.post("/analyze-finding")
async def analyze_finding(
    body: AiAnalyzeFindingRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """
    Bulguyu AI ile değerlendirir; gerçek zafiyet mi yoksa false positive mi?

    DB'deki Finding kaydı ai_confidence ve ai_analysis ile güncellenir.
    """
    client = _get_ai_engine(request)
    finding = await _get_finding_or_404(body.finding_id, db)

    # URL bilgisini al
    url_str = ""
    if finding.url_id:
        url_result = await db.execute(select(Url).where(Url.id == finding.url_id))
        url_obj = url_result.scalar_one_or_none()
        if url_obj:
            url_str = str(url_obj.url)

    finding_dict = {
        "vuln_type": finding.vuln_type,
        "url": url_str,
        "payload": finding.payload or "",
        "tool_output": finding.evidence or "",
        "request_raw": finding.request_raw or "",
        "response_snippet": finding.response_snippet or "",
        "severity": finding.severity,
    }

    analysis = await ai_engine.analyze_finding(finding=finding_dict, client=client)

    # DB güncelle
    if "confidence" in analysis:
        finding.ai_confidence = analysis["confidence"]
    if "poc_steps" in analysis:
        import json as _json
        finding.ai_poc = _json.dumps(analysis["poc_steps"], ensure_ascii=False)
    finding.ai_analysis = _build_analysis_text(analysis)
    await db.flush()

    return {
        "finding_id": body.finding_id,
        **analysis,
    }


@router.post("/generate-poc")
async def generate_poc(
    body: AiGeneratePocRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """
    Bulgu için adım adım PoC (Proof of Concept) üretir.

    Önce mevcut ai_poc'u döndürür; yoksa analyze_finding çağırır.
    """
    client = _get_ai_engine(request)
    finding = await _get_finding_or_404(body.finding_id, db)

    if finding.ai_poc:
        try:
            import json as _json
            poc_steps = _json.loads(finding.ai_poc)
            return {"finding_id": body.finding_id, "poc_steps": poc_steps}
        except Exception:
            pass

    # Yeniden analiz et
    url_str = ""
    if finding.url_id:
        url_result = await db.execute(select(Url).where(Url.id == finding.url_id))
        url_obj = url_result.scalar_one_or_none()
        if url_obj:
            url_str = str(url_obj.url)

    finding_dict = {
        "vuln_type": finding.vuln_type,
        "url": url_str,
        "payload": finding.payload or "",
        "tool_output": finding.evidence or "",
        "request_raw": finding.request_raw or "",
        "response_snippet": finding.response_snippet or "",
    }

    analysis = await ai_engine.analyze_finding(finding=finding_dict, client=client)

    poc_steps = analysis.get("poc_steps", [])
    if poc_steps:
        import json as _json
        finding.ai_poc = _json.dumps(poc_steps, ensure_ascii=False)
        await db.flush()

    return {
        "finding_id": body.finding_id,
        "poc_steps": poc_steps,
        "fix_recommendation": analysis.get("fix_recommendation", ""),
    }


# ---------------------------------------------------------------------------
# Yardımcı
# ---------------------------------------------------------------------------


def _build_analysis_text(analysis: Dict[str, Any]) -> str:
    """AI analiz sözlüğünden okunabilir metin oluşturur."""
    parts = []
    if "is_real_vulnerability" in analysis:
        verdict = "Gerçek zafiyet" if analysis["is_real_vulnerability"] else "False positive"
        conf = analysis.get("confidence", "?")
        parts.append(f"{verdict} (Güven: {conf}%)")
    if analysis.get("impact"):
        parts.append(f"Etki: {analysis['impact']}")
    if analysis.get("exploitability"):
        parts.append(f"Exploit edilebilirlik: {analysis['exploitability']}")
    if analysis.get("fix_recommendation"):
        parts.append(f"Düzeltme: {analysis['fix_recommendation']}")
    return "\n".join(parts)
