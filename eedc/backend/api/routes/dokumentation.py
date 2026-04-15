"""
Router für die neue Dokumentations-Pipeline (Issue #121).

- `/_selftest`  — WeasyPrint-Smoke-Test
- `/anlagendokumentation/{anlage_id}` — Phase 4 Beta
- `/finanzbericht/{anlage_id}`         — Phase 4 Beta
"""
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps import get_db
from backend.core.config import settings

router = APIRouter()


def _require_weasyprint():
    """Phase-4-PDFs sind WeasyPrint-only — reportlab kann das Layout nicht."""
    engine = getattr(settings, "pdf_engine", "reportlab")
    if engine != "weasyprint":
        raise HTTPException(
            status_code=503,
            detail=(
                "Phase 4-PDFs (Anlagendokumentation, Finanzbericht) benötigen "
                "PDF_ENGINE=weasyprint. Im HA-Add-on in der Konfiguration umschaltbar, "
                "im Standalone-Docker via Umgebungsvariable."
            ),
        )


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


@router.get("/anlagendokumentation/{anlage_id}", tags=["Dokumentation"])
async def anlagendokumentation_pdf(
    anlage_id: int,
    db: AsyncSession = Depends(get_db),
):
    """
    Anlagendokumentation (Phase 4 Beta, Issue #121).

    Urkunden-Titelseite + Komponenten-Folgeseiten mit verknüpfter
    Komponenten-Akte. Keine Geldbeträge — die wandern in den Finanzbericht.
    Hybrid-Gruppierung: PV-Module gesammelt auf einer Seite, alles andere einzeln.
    """
    _require_weasyprint()
    from backend.services.pdf import render_document
    from backend.services.pdf.builders.anlagendokumentation import (
        build_anlagendokumentation_context,
    )

    try:
        context = await build_anlagendokumentation_context(db, anlage_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

    try:
        pdf_bytes = render_document("anlagendokumentation.html", context)
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"PDF-Render-Fehler: {exc.__class__.__name__}: {exc}",
        )

    filename = f"anlagendokumentation_{context['anlage']['name']}.pdf".replace(" ", "_")
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{filename}"'},
    )


@router.get("/finanzbericht/{anlage_id}", tags=["Dokumentation"])
async def finanzbericht_pdf(
    anlage_id: int,
    db: AsyncSession = Depends(get_db),
):
    """
    Finanzbericht (Phase 4 Beta, Issue #121).

    Investitionen, ROI, Förderungen, Versicherung, Steuerdaten.
    Enthält im Gegensatz zur Anlagendokumentation alle Geldbeträge.
    """
    _require_weasyprint()
    from backend.services.pdf import render_document
    from backend.services.pdf.builders.finanzbericht import (
        build_finanzbericht_context,
    )

    try:
        context = await build_finanzbericht_context(db, anlage_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

    try:
        pdf_bytes = render_document("finanzbericht.html", context)
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"PDF-Render-Fehler: {exc.__class__.__name__}: {exc}",
        )

    filename = f"finanzbericht_{context['anlage']['name']}.pdf".replace(" ", "_")
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{filename}"'},
    )
