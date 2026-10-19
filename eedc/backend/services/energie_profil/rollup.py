"""
Monats-Rollup (Etappe 3d P3 Refactoring-Tail).

Aggregiert TagesZusammenfassungen eines Monats in Monatsdaten-Felder.
Extrahiert aus `services/energie_profil_service.py` — Verhalten unverändert.
Schreib-Pfad ist `Monatsdaten` Top-Level (5 Felder: ueberschuss_kwh,
defizit_kwh, batterie_vollzyklen, performance_ratio, peak_netzbezug_kw),
Source-Tag nach P3-Architektur-Integration `auto:monatsabschluss`.
"""

from __future__ import annotations

import logging
from datetime import date, timedelta

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.monatsdaten import Monatsdaten
from backend.models.tages_energie_profil import TagesZusammenfassung
from backend.services.provenance import write_with_provenance

logger = logging.getLogger(__name__)

# Auto-Aggregation aus Tageswerten in 5 Monatsdaten-Felder. Source-Klasse
# AUTO_AGGREGATION (Stufe 3) — manuelle Eingabe via Wizard/Form (Stufe 1)
# schlägt das, was den User-Override-Use-Case strukturell schützt.
_ROLLUP_SOURCE = "auto:monatsabschluss"
_ROLLUP_WRITER = "rollup_month"


async def rollup_month(
    anlage_id: int,
    jahr: int,
    monat: int,
    db: AsyncSession,
) -> bool:
    """
    Aggregiert TagesZusammenfassungen eines Monats in Monatsdaten-Felder.

    Args:
        anlage_id: Anlage-ID
        jahr/monat: Zeitraum

    Returns:
        True wenn Daten vorhanden und aktualisiert
    """
    erster = date(jahr, monat, 1)
    if monat == 12:
        letzter = date(jahr + 1, 1, 1)
    else:
        letzter = date(jahr, monat + 1, 1)

    result = await db.execute(
        select(TagesZusammenfassung).where(
            and_(
                TagesZusammenfassung.anlage_id == anlage_id,
                TagesZusammenfassung.datum >= erster,
                TagesZusammenfassung.datum < letzter,
            )
        )
    )
    tage = result.scalars().all()

    if not tage:
        return False

    md_result = await db.execute(
        select(Monatsdaten).where(
            and_(
                Monatsdaten.anlage_id == anlage_id,
                Monatsdaten.jahr == jahr,
                Monatsdaten.monat == monat,
            )
        )
    )
    md = md_result.scalar_one_or_none()
    if not md:
        return False

    # HA-Bauform S5 (E-S5-3): an einem Kanal-Tag schreibt `aggregate_day` Überschuss und Defizit nicht mehr in die
    # Tageszeile (S5-R2) — die Lesestelle liefert sie dort aus den Mischzeilen (in der Form der Tageszeile), an jedem
    # anderen Tag die Tageszeile wie bisher.
    from backend.services.energie_profil.kanal_stunden import ueberschuss_defizit_der_tage

    je_tag = await ueberschuss_defizit_der_tage(
        db, anlage_id, erster, letzter - timedelta(days=1), tageszeilen_form=True,
    )
    ueberschuss_vals = [u for u, _ in je_tag.values() if u is not None]
    defizit_vals = [d for _, d in je_tag.values() if d is not None]
    zyklen_vals = [t.batterie_vollzyklen for t in tage if t.batterie_vollzyklen is not None]
    pr_vals = [t.performance_ratio for t in tage if t.performance_ratio is not None]
    peak_bezug_vals = [t.peak_netzbezug_kw for t in tage if t.peak_netzbezug_kw is not None]

    rollup_values: dict[str, float | None] = {
        "ueberschuss_kwh": round(sum(ueberschuss_vals), 1) if ueberschuss_vals else None,
        "defizit_kwh": round(sum(defizit_vals), 1) if defizit_vals else None,
        "batterie_vollzyklen": round(sum(zyklen_vals), 1) if zyklen_vals else None,
        "performance_ratio": round(sum(pr_vals) / len(pr_vals), 3) if pr_vals else None,
        "peak_netzbezug_kw": round(max(peak_bezug_vals), 2) if peak_bezug_vals else None,
    }
    # Per-Feld durch den Resolver — manuelle Korrektur via Wizard/Form
    # (Source `manual:form`) schlägt diesen Auto-Rollup automatisch.
    for feld, wert in rollup_values.items():
        if wert is None:
            continue
        await write_with_provenance(
            db, md, feld, wert,
            source=_ROLLUP_SOURCE, writer=_ROLLUP_WRITER,
        )

    logger.info(
        f"Monat {jahr}/{monat:02d} Anlage {anlage_id}: "
        f"{len(tage)} Tage aggregiert, "
        f"Überschuss={rollup_values['ueberschuss_kwh']}kWh, "
        f"Defizit={rollup_values['defizit_kwh']}kWh"
    )

    return True
