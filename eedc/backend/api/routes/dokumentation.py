"""
Router für die neue Dokumentations-Pipeline (Issue #121).

- `/_selftest`  — WeasyPrint-Smoke-Test
- `/anlagendokumentation/{anlage_id}` — Phase 4 Beta
- `/finanzbericht/{anlage_id}`         — Phase 4 Beta
- `/monatsbericht/{anlage_id}`         — #395 Punkt 4 (PDF **und** Markdown)
"""
from datetime import datetime
from typing import Optional
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps import get_db

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


def _dateiname(basis: str, endung: str) -> tuple[str, str]:
    """``Content-Disposition``-Paar (ASCII-Fallback + RFC-5987).

    Ein Anlagenname darf Umlaute tragen; ein rohes ``filename="Süd"`` ist im
    Header nicht zulässig und wird von Browsern verschieden geraten. Die
    bestehenden Berichte umgehen das, indem sie nur Leerzeichen ersetzen — hier
    steht zusätzlich der Monat im Namen, und der Name kommt aus der Eingabe des
    Anwenders.
    """
    sicher = "".join(c if c.isalnum() or c in "-_." else "_" for c in basis)
    return f"{sicher}.{endung}", quote(f"{basis}.{endung}")


@router.get("/monatsbericht/{anlage_id}", tags=["Dokumentation"])
async def monatsbericht(
    anlage_id: int,
    jahr: int = Query(..., description="Berichtsjahr"),
    monat: int = Query(..., ge=1, le=12, description="Berichtsmonat (1–12)"),
    themen: Optional[list[str]] = Query(
        None,
        description="Themenschalter: energie · komponenten · finanzen · co2 · "
                    "community. Weggelassen = alle.",
    ),
    ohne: Optional[list[str]] = Query(
        None,
        description="Park-IDs aus `eedc-park:v4-cockpit-monat`, die der Client "
                    "beim Erzeugen mitschickt. Leer = vollständiger Bericht.",
    ),
    db: AsyncSession = Depends(get_db),
):
    """Monatsbericht eines **einzelnen** Monats als PDF.

    ⛔ **Es gibt bewusst nur EIN Format** (Entscheid Gernot, 2026-08-30). Bis
    dahin lieferte diese Route zusätzlich Markdown, damit man den Bericht in ein
    Forum posten kann — mit dem Entscheid, das Thema *Teilen* nicht zu
    verfolgen, ist dieser Zweck entfallen. Der zweite Renderer wäre danach ohne
    Aufrufer weitergelaufen; und mit **einem** Renderer gibt es die zweite
    Bildungsstelle gar nicht mehr, gegen die der Bericht gebaut war (**N-7**) —
    das ist stärker als die Probe, die sie bewachte.

    `ohne` trägt die Park-IDs, die im Browser des Anwenders geparkt sind. Das
    Backend führt **keine** Liste dieser IDs (Park-Doktrin: „IDs immer aus dem
    Render-Pfad ableiten, nie hart daneben") — jeder Abschnitt nennt nur seinen
    eigenen Anker. Ohne den Parameter ist der Bericht vollständig; das ist der
    Fall „am Tablet geparkt, am PC erzeugt" und darf nichts weglassen.

    **Genau ein Monat.** Eine Spanne ist der Jahresbericht mit anderem Filter,
    und den gibt es (`/api/import-export/pdf`).
    """
    from backend.services.pdf import render_document
    from backend.services.pdf.builders.monatsbericht import (
        build_monatsbericht_context,
    )

    try:
        context = await build_monatsbericht_context(
            db, anlage_id, jahr, monat,
            themen=themen,
            geparkte_ids=ohne or (),
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

    basis = f"monatsbericht_{jahr}-{monat:02d}"
    if context["anlage"]["name"]:
        basis += f"_{context['anlage']['name'].replace(' ', '_')}"

    try:
        pdf_bytes = render_document("monatsbericht.html", context)
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"PDF-Render-Fehler: {exc.__class__.__name__}: {exc}",
        )

    ascii_name, utf8_name = _dateiname(basis, "pdf")
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition":
                f'inline; filename="{ascii_name}"; filename*=UTF-8\'\'{utf8_name}',
        },
    )
