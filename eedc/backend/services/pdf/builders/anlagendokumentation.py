"""
Daten-Aggregation für die Anlagendokumentation (Issue #121, Phase 4).

Baut den Context für `templates/anlagendokumentation.html`:
Titelseite (Urkunde-Stil, V4-Layout) + Komponenten-Folgeseiten mit
verknüpfter Komponentenakte aus der Infothek (Kategorie `garantie`).

Hybrid-Gruppierung (Entscheidung A3):
- Alle `pv-module`-Investitionen werden auf einer Sammel-Seite gerendert
- Alle anderen Investitionen bekommen je eine eigene Folgeseite
- Reihenfolge: PV zuerst, dann Speicher, Wechselrichter, WP, Wallbox,
  E-Auto, Balkonkraftwerk, Sonstiges

Komponenten-Block (Entscheidung B1):
- Es werden nur verknüpfte Infothek-Einträge Kategorie `garantie`
  gerendert. Keine `stamm_*`-Fallbacks aus `investition.parameter`.
- Fehlt die Verknüpfung, zeigt die Seite eine Hinweis-Box.

Die Anlagendokumentation enthält **keine** Geldbeträge — das ist das
bewusste Konzept, damit die PDF z.B. an eine Versicherung oder für den
Nachlass weitergegeben werden kann.
"""
from __future__ import annotations

import base64
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from sqlalchemy import select, exists
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.routes.infothek import INFOTHEK_KATEGORIEN
from backend.models.anlage import Anlage, AnlageFoto
from backend.models.infothek import InfothekDatei, InfothekEintrag, InfothekInvestition
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

# Reihenfolge der Folgeseiten (PV zuerst, dann Erzeugungstechnik, dann
# Verbraucher, dann Rest)
TYP_REIHENFOLGE = [
    "pv-module",
    "wechselrichter",
    "speicher",
    "waermepumpe",
    "wallbox",
    "e-auto",
    "balkonkraftwerk",
    "sonstiges",
]

# Welche Felder der Komponenten-Akte sind Freitext-Blöcke (nicht ins Grid)
FREITEXT_FELDER = ("technische_daten", "bedingungen", "zugehoerige_vertraege")


def _format_value(val: Any) -> str:
    if val in (None, ""):
        return ""
    if isinstance(val, float) and val.is_integer():
        return str(int(val))
    return str(val)


def _build_komponenten_block(
    eintrag: InfothekEintrag,
    dateien: list[InfothekDatei],
) -> dict:
    """Rendert einen einzelnen Komponenten-Akte-Eintrag für die PDF."""
    params = eintrag.parameter or {}
    schema_felder = INFOTHEK_KATEGORIEN.get("garantie", {}).get("felder", {})

    grid: list[tuple[str, str]] = []
    freitext: list[tuple[str, str]] = []
    datenblatt_url: Optional[str] = None

    for key, defn in schema_felder.items():
        val = params.get(key)
        val_str = _format_value(val)
        if not val_str:
            continue
        label = defn.get("label", key)
        if key == "datenblatt_url":
            datenblatt_url = val_str
            continue
        if key in FREITEXT_FELDER:
            freitext.append((label, val_str))
        else:
            grid.append((label, val_str))

    datei_list = [
        {
            "dateiname": d.dateiname,
            "dateityp": d.dateityp,
            "beschreibung": d.beschreibung or "",
        }
        for d in dateien
    ]

    return {
        "bezeichnung": eintrag.bezeichnung,
        "notizen": eintrag.notizen or "",
        "grid": grid,
        "freitext": freitext,
        "datenblatt_url": datenblatt_url,
        "dateien": datei_list,
    }


def _build_investition_tech_grid(inv: Investition) -> list[tuple[str, str]]:
    """
    Minimal-Tech-Grid aus den Investitions-Pflichtfeldern.

    Keine Preise, keine Förderungen, keine Betriebskosten.
    """
    grid: list[tuple[str, str]] = []
    if inv.anschaffungsdatum:
        grid.append(("Anschaffungsdatum", inv.anschaffungsdatum.strftime("%d.%m.%Y")))
    if inv.leistung_kwp:
        grid.append(("Nennleistung", f"{inv.leistung_kwp:.2f} kWp"))
    if inv.ausrichtung:
        if inv.neigung_grad is not None:
            grid.append(("Ausrichtung", f"{inv.ausrichtung} · {inv.neigung_grad:.0f}° Neigung"))
        else:
            grid.append(("Ausrichtung", inv.ausrichtung))
    elif inv.neigung_grad is not None:
        grid.append(("Neigung", f"{inv.neigung_grad:.0f}°"))

    # Generische interessante Parameter
    params = inv.parameter or {}
    interessant = [
        ("leistung_wp", "Modulleistung", "{} Wp"),
        ("anzahl", "Anzahl", "{}"),
        ("hat_speicher", "Mit Speicher", None),
        ("speicher_kapazitaet_wh", "Speicherkapazität", "{} Wh"),
        ("kapazitaet_kwh", "Speicherkapazität", "{} kWh"),
        ("batterie_kapazitaet_kwh", "Batteriekapazität", "{} kWh"),
        ("heizleistung_kw", "Heizleistung", "{} kW"),
        ("jaz", "JAZ", "{}"),
        ("km_jahr", "Fahrleistung", "{} km/Jahr"),
        ("verbrauch_kwh_100km", "Verbrauch", "{} kWh/100 km"),
        ("wallbox_leistung_kw", "Ladeleistung", "{} kW"),
    ]
    for key, label, fmt in interessant:
        if key not in params:
            continue
        val = params[key]
        if val in (None, "", False):
            continue
        if fmt is None:
            grid.append((label, "Ja" if val else "Nein"))
        else:
            grid.append((label, fmt.format(val)))

    return grid


async def _lade_komponenten_fuer_investition(
    db: AsyncSession,
    anlage_id: int,
    investition_id: int,
) -> list[dict]:
    """Lädt alle verknüpften Komponenten-Akte-Einträge für eine Investition."""
    q = (
        select(InfothekEintrag)
        .join(InfothekInvestition, InfothekInvestition.infothek_eintrag_id == InfothekEintrag.id)
        .where(InfothekEintrag.anlage_id == anlage_id)
        .where(InfothekEintrag.kategorie == "garantie")
        .where(InfothekInvestition.investition_id == investition_id)
        .where(InfothekEintrag.aktiv == True)  # noqa: E712
        .where(InfothekEintrag.in_anlagendoku == True)  # noqa: E712
        .order_by(InfothekEintrag.sortierung, InfothekEintrag.created_at.desc())
    )
    res = await db.execute(q)
    eintraege = list(res.scalars().all())

    blocks: list[dict] = []
    for e in eintraege:
        d_res = await db.execute(
            select(InfothekDatei)
            .where(InfothekDatei.eintrag_id == e.id)
            .order_by(InfothekDatei.created_at)
        )
        dateien = list(d_res.scalars().all())
        block = _build_komponenten_block(e, dateien)
        block["_eintrag_id"] = e.id
        blocks.append(block)
    return blocks


async def build_anlagendokumentation_context(
    db: AsyncSession,
    anlage_id: int,
) -> dict:
    """Lädt alle Daten und liefert das Context-Dict für das Template."""
    res = await db.execute(select(Anlage).where(Anlage.id == anlage_id))
    anlage = res.scalar_one_or_none()
    if not anlage:
        raise LookupError(f"Anlage {anlage_id} nicht gefunden")

    # Anlagenfoto als Data-URL einbetten (WeasyPrint kann dann ohne
    # Dateisystem-Zugriff rendern)
    foto_res = await db.execute(
        select(AnlageFoto).where(AnlageFoto.anlage_id == anlage_id)
    )
    foto = foto_res.scalar_one_or_none()
    foto_data_url: Optional[str] = None
    if foto:
        b64 = base64.b64encode(foto.daten).decode("ascii")
        foto_data_url = f"data:{foto.mime_type};base64,{b64}"
    else:
        # EEDC-Logo als Fallback (Nutzer kann eigenes Bild hochladen)
        logo_path = Path(__file__).resolve().parents[4] / "logo.png"
        if logo_path.exists():
            b64 = base64.b64encode(logo_path.read_bytes()).decode("ascii")
            foto_data_url = f"data:image/png;base64,{b64}"

    # Alle Investitionen laden (inkl. stillgelegte — Historie relevant)
    inv_res = await db.execute(
        select(Investition)
        .where(Investition.anlage_id == anlage_id)
        .where(Investition.aktiv == True)  # noqa: E712
        .order_by(Investition.id)
    )
    investitionen = list(inv_res.scalars().all())

    # Gruppieren: PV-Module gesammelt, Rest einzeln
    pv_module = [i for i in investitionen if i.typ == "pv-module"]
    einzel: list[Investition] = [i for i in investitionen if i.typ != "pv-module"]

    # Einzel-Seiten nach TYP_REIHENFOLGE sortieren (innerhalb eines Typs
    # nach ID, also Reihenfolge des Anlegens)
    def sort_key(inv: Investition) -> tuple[int, int]:
        try:
            typ_idx = TYP_REIHENFOLGE.index(inv.typ)
        except ValueError:
            typ_idx = len(TYP_REIHENFOLGE)
        return (typ_idx, inv.id)

    einzel.sort(key=sort_key)

    # Folgeseiten bauen
    seiten: list[dict] = []

    # PV-Sammel-Seite
    if pv_module:
        pv_gesamt_kwp = sum((i.leistung_kwp or 0) for i in pv_module)
        pv_items = []
        # Komponenten deduplizieren: gleiche Komponente kann mit mehreren
        # PV-Modulfeldern verknüpft sein (n:m) → nur einmal anzeigen,
        # mit Hinweis für welche Modulfelder sie gilt
        alle_komp: dict[int, dict] = {}  # eintrag_id → block
        komp_gilt_fuer: dict[int, list[str]] = {}  # eintrag_id → [Modulfeld-Namen]
        for inv in pv_module:
            komponenten = await _lade_komponenten_fuer_investition(
                db, anlage_id, inv.id
            )
            for k in komponenten:
                eid = k.pop("_eintrag_id", None)
                if eid and eid not in alle_komp:
                    alle_komp[eid] = k
                if eid:
                    komp_gilt_fuer.setdefault(eid, []).append(inv.bezeichnung)
            pv_items.append({
                "bezeichnung": inv.bezeichnung,
                "tech_grid": _build_investition_tech_grid(inv),
            })

        # "Gilt für"-Hinweis: immer anzeigen, damit bei Seitenumbruch
        # die Zuordnung klar bleibt
        pv_komponenten: list[dict] = []
        alle_namen = [inv.bezeichnung for inv in pv_module]
        for eid, block in alle_komp.items():
            namen = komp_gilt_fuer.get(eid, [])
            if set(namen) == set(alle_namen):
                block["gilt_fuer"] = "alle Modulfelder"
            else:
                block["gilt_fuer"] = ", ".join(namen)
            pv_komponenten.append(block)

        seiten.append({
            "kind": "pv-sammel",
            "typ_label": "PV-Modulfelder",
            "titel": "Photovoltaik",
            "pv_gesamt_kwp": pv_gesamt_kwp,
            "pv_anzahl": len(pv_module),
            "pv_items": pv_items,
            "pv_komponenten": pv_komponenten,
        })

    # Einzel-Seiten
    for inv in einzel:
        komponenten = await _lade_komponenten_fuer_investition(db, anlage_id, inv.id)
        for k in komponenten:
            k.pop("_eintrag_id", None)
        seiten.append({
            "kind": "einzel",
            "typ": inv.typ,
            "typ_label": TYP_LABELS.get(inv.typ, inv.typ.title()),
            "titel": inv.bezeichnung,
            "tech_grid": _build_investition_tech_grid(inv),
            "komponenten": komponenten,
        })

    # Infrastruktur: Komponenten-Akten ohne Investment-Verknüpfung
    linked_subq = (
        select(InfothekInvestition.infothek_eintrag_id)
        .where(InfothekInvestition.infothek_eintrag_id == InfothekEintrag.id)
        .correlate(InfothekEintrag)
        .exists()
    )
    infra_res = await db.execute(
        select(InfothekEintrag)
        .where(InfothekEintrag.anlage_id == anlage_id)
        .where(InfothekEintrag.kategorie == "garantie")
        .where(InfothekEintrag.in_anlagendoku == True)  # noqa: E712
        .where(InfothekEintrag.aktiv == True)  # noqa: E712
        .where(~linked_subq)
        .order_by(InfothekEintrag.sortierung, InfothekEintrag.created_at.desc())
    )
    infra_eintraege = list(infra_res.scalars().all())
    if infra_eintraege:
        infra_blocks = []
        for e in infra_eintraege:
            d_res = await db.execute(
                select(InfothekDatei)
                .where(InfothekDatei.eintrag_id == e.id)
                .order_by(InfothekDatei.created_at)
            )
            dateien = list(d_res.scalars().all())
            infra_blocks.append(_build_komponenten_block(e, dateien))
        seiten.append({
            "kind": "infrastruktur",
            "typ_label": "Infrastruktur",
            "titel": "Allgemeine Infrastruktur",
            "komponenten": infra_blocks,
        })

    # Anlagenarten-Liste für die Titelseite
    anlagenarten: list[str] = []
    if pv_module:
        kwp_sum = sum((i.leistung_kwp or 0) for i in pv_module)
        anlagenarten.append(f"Photovoltaik · {kwp_sum:.2f} kWp · {len(pv_module)} Modulfeld(er)")
    typ_counts: dict[str, int] = {}
    for inv in einzel:
        typ_counts[inv.typ] = typ_counts.get(inv.typ, 0) + 1
    for typ in TYP_REIHENFOLGE:
        if typ == "pv-module" or typ not in typ_counts:
            continue
        count = typ_counts[typ]
        label = TYP_LABELS.get(typ, typ.title())
        anlagenarten.append(f"{label}" + (f" · {count}" if count > 1 else ""))

    return {
        "anlage": {
            "id": anlage.id,
            "name": anlage.anlagenname,
            "leistung_kwp": anlage.leistung_kwp,
            "installationsdatum": anlage.installationsdatum,
            "standort_strasse": anlage.standort_strasse or "",
            "standort_plz": anlage.standort_plz or "",
            "standort_ort": anlage.standort_ort or "",
            "latitude": anlage.latitude,
            "longitude": anlage.longitude,
            "anlagenarten": anlagenarten,
        },
        "foto_data_url": foto_data_url,
        "seiten": seiten,
        "erzeugt_am": datetime.now().strftime("%d.%m.%Y"),
    }
