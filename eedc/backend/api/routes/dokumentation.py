"""
Router für die neue Dokumentations-Pipeline (Issue #121).

Phase 1: nur Smoke-Test-Route, alle echten Dokumente folgen in den
weiteren Phasen (siehe Plan unter
`/home/gernot/.claude/plans/sleepy-frolicking-cupcake.md`).
"""
from datetime import datetime

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response

router = APIRouter()


@router.get("/_selftest", tags=["Dokumentation"])
async def pdf_engine_selftest():
    """
    Rendert ein Hello-World-PDF, um zu verifizieren, dass WeasyPrint +
    Jinja2 + Pango/Cairo im Container funktionieren. Liefert direkt
    `application/pdf` zurück, kein Download-Header.
    """
    try:
        from backend.services.pdf import render_document
    except ImportError as exc:
        raise HTTPException(
            status_code=503,
            detail=f"PDF-Engine nicht verfügbar: {exc}",
        )

    try:
        pdf_bytes = render_document(
            "selftest.html",
            {"erzeugt_am": datetime.now().strftime("%Y-%m-%d %H:%M:%S")},
        )
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"PDF-Render-Fehler: {exc.__class__.__name__}: {exc}",
        )

    return Response(content=pdf_bytes, media_type="application/pdf")
