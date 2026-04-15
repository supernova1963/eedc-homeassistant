"""
Daten-Aggregation für den Finanzbericht (Issue #121, Phase 4).

Liefert den Context für `templates/finanzbericht.html`: Investitions-
Tabelle mit Kosten + Alt-Kosten, Summenblock, ROI (kumuliert seit
Inbetriebnahme), Förderungen, Versicherung, Steuerdaten.

Im Gegensatz zur Anlagendokumentation enthält dieses PDF alle
Geldbeträge — es wird **nicht** zusammen mit der Anlagendokumentation
herausgegeben, sondern separat, wenn Finanzkennzahlen relevant sind.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.routes.infothek import INFOTHEK_KATEGORIEN
from backend.models.anlage import Anlage
from backend.models.infothek import InfothekEintrag
from backend.models.investition import Investition


TYP_LABELS = {
    "pv-module": "PV-Modulfeld",
    "wechselrichter": "Wechselrichter",
    "speicher": "Batteriespeicher",
    "waermepumpe": "Wärmepumpe",
    "wallbox": "Wallbox",
    "e-auto": "E-Fahrzeug",
    "balkonkraftwerk": "Balkonkraftwerk",
    "sonstiges": "Sonstiges",
}


def _format_euro(val: Optional[float]) -> str:
    if val is None:
        return "—"
    # DE-Format: 12.345,67 €
    return f"{val:_.2f} €".replace(".", ",").replace("_", ".")


def _format_year_month(d) -> str:
    if not d:
        return "—"
    return d.strftime("%m / %Y")


async def _lade_infothek_kategorie(
    db: AsyncSession,
    anlage_id: int,
    kategorie: str,
) -> list[dict]:
    """Lädt alle aktiven Einträge einer Kategorie als Feld-Liste."""
    res = await db.execute(
        select(InfothekEintrag)
        .where(InfothekEintrag.anlage_id == anlage_id)
        .where(InfothekEintrag.kategorie == kategorie)
        .where(InfothekEintrag.aktiv == True)  # noqa: E712
        .order_by(InfothekEintrag.sortierung, InfothekEintrag.created_at.desc())
    )
    eintraege = list(res.scalars().all())

    schema_felder = INFOTHEK_KATEGORIEN.get(kategorie, {}).get("felder", {})

    result: list[dict] = []
    for e in eintraege:
        params = e.parameter or {}
        felder: list[tuple[str, str]] = []
        for key, defn in schema_felder.items():
            val = params.get(key)
            if val in (None, ""):
                continue
            label = defn.get("label", key)
            felder.append((label, str(val)))
        result.append({
            "bezeichnung": e.bezeichnung,
            "notizen": e.notizen or "",
            "felder": felder,
        })
    return result


async def build_finanzbericht_context(
    db: AsyncSession,
    anlage_id: int,
) -> dict:
    """Lädt alle Daten und liefert das Context-Dict für das Template."""
    res = await db.execute(select(Anlage).where(Anlage.id == anlage_id))
    anlage = res.scalar_one_or_none()
    if not anlage:
        raise LookupError(f"Anlage {anlage_id} nicht gefunden")

    # Investitionen laden (aktiv oder nicht — historische bleiben drin)
    inv_res = await db.execute(
        select(Investition)
        .where(Investition.anlage_id == anlage_id)
        .order_by(Investition.anschaffungsdatum.nulls_last(), Investition.id)
    )
    investitionen = list(inv_res.scalars().all())

    investitionen_rows: list[dict] = []
    summe_kosten = 0.0
    summe_alt_kosten = 0.0
    summe_einsparung_jahr = 0.0
    for inv in investitionen:
        kosten = inv.anschaffungskosten_gesamt or 0
        alt = inv.anschaffungskosten_alternativ or 0
        eins = inv.einsparung_prognose_jahr or 0
        summe_kosten += kosten
        summe_alt_kosten += alt
        summe_einsparung_jahr += eins
        investitionen_rows.append({
            "bezeichnung": inv.bezeichnung,
            "typ_label": TYP_LABELS.get(inv.typ, inv.typ.title()),
            "anschaffungsdatum": _format_year_month(inv.anschaffungsdatum),
            "stilllegungsdatum": _format_year_month(inv.stilllegungsdatum) if inv.stilllegungsdatum else "",
            "kosten": _format_euro(inv.anschaffungskosten_gesamt),
            "alternativ": _format_euro(inv.anschaffungskosten_alternativ) if inv.anschaffungskosten_alternativ else "",
            "betriebskosten_jahr": _format_euro(inv.betriebskosten_jahr) if inv.betriebskosten_jahr else "",
            "einsparung_jahr": _format_euro(inv.einsparung_prognose_jahr) if inv.einsparung_prognose_jahr else "",
        })

    # ROI-Kenngrößen (einfach, ohne Cockpit-Service zu duplizieren)
    # Amortisation = Gesamt-Kosten / Einsparung-pro-Jahr
    amortisation_jahre: Optional[float] = None
    if summe_kosten > 0 and summe_einsparung_jahr > 0:
        amortisation_jahre = summe_kosten / summe_einsparung_jahr

    differenz_alt = summe_alt_kosten - summe_kosten  # positiv = EEDC-Pfad günstiger

    # Zusatz-Sektionen aus der Infothek
    foerderungen = await _lade_infothek_kategorie(db, anlage_id, "foerderung")
    versicherungen = await _lade_infothek_kategorie(db, anlage_id, "versicherung")
    steuerdaten = await _lade_infothek_kategorie(db, anlage_id, "steuerdaten")

    summe_foerderung: float = 0.0
    for f in foerderungen:
        for label, val in f["felder"]:
            if label.startswith("Betrag"):
                try:
                    summe_foerderung += float(str(val).replace(",", "."))
                except ValueError:
                    pass

    return {
        "anlage": {
            "id": anlage.id,
            "name": anlage.anlagenname,
            "leistung_kwp": anlage.leistung_kwp,
            "installationsdatum": anlage.installationsdatum,
            "standort_plz": anlage.standort_plz or "",
            "standort_ort": anlage.standort_ort or "",
        },
        "investitionen": investitionen_rows,
        "summen": {
            "kosten": _format_euro(summe_kosten),
            "alternativ": _format_euro(summe_alt_kosten) if summe_alt_kosten else "",
            "einsparung_jahr": _format_euro(summe_einsparung_jahr) if summe_einsparung_jahr else "",
            "foerderung": _format_euro(summe_foerderung) if summe_foerderung else "",
            "netto_nach_foerderung": _format_euro(summe_kosten - summe_foerderung) if summe_foerderung else "",
            "differenz_alt": _format_euro(differenz_alt) if differenz_alt else "",
        },
        "amortisation_jahre": (
            f"{amortisation_jahre:.1f} Jahre" if amortisation_jahre else "—"
        ),
        "foerderungen": foerderungen,
        "versicherungen": versicherungen,
        "steuerdaten": steuerdaten,
        "erzeugt_am": datetime.now().strftime("%d.%m.%Y"),
    }
