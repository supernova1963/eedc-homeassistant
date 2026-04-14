"""
Daten-Aggregation für das Infothek-Dossier.

Extrahiert die bisher in `infothek_pdf_service.py` genutzte Logik und
liefert ein Context-Dict, das `templates/infothek.html` direkt verwendet.
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import Optional

from markupsafe import Markup
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.routes.infothek import INFOTHEK_KATEGORIEN
from backend.models.anlage import Anlage
from backend.models.infothek import InfothekEintrag

KATEGORIE_LABELS = {
    "stromvertrag": "Stromvertrag",
    "einspeisevertrag": "Einspeisevertrag",
    "gasvertrag": "Gasvertrag",
    "wasservertrag": "Wasservertrag",
    "fernwaerme": "Fernwärme",
    "brennstoff": "Brennstoff",
    "versicherung": "Versicherung",
    "ansprechpartner": "Vertragspartner",
    "wartungsvertrag": "Wartungsvertrag",
    "marktstammdatenregister": "Marktstammdatenregister",
    "foerderung": "Förderung",
    "garantie": "Garantie",
    "steuerdaten": "Steuerdaten",
    "sonstiges": "Sonstiges",
}


def _markdown_to_html(text: str) -> Markup:
    """
    Sehr leichter Markdown→HTML-Konverter (Listen, fett, kursiv, Links).

    Alles andere wird wörtlich übernommen, Zeilen mit `\n` zu `<br>` ergänzt.
    Vorhandene HTML-Sonderzeichen werden vorher escaped.
    """
    if not text:
        return Markup("")

    # Escapen
    safe = (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )

    out_lines: list[str] = []
    list_buf: list[str] = []

    def flush_list():
        if list_buf:
            out_lines.append("<ul>" + "".join(f"<li>{i}</li>" for i in list_buf) + "</ul>")
            list_buf.clear()

    def inline(t: str) -> str:
        t = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2">\1</a>', t)
        t = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", t)
        t = re.sub(r"\*(.+?)\*", r"<em>\1</em>", t)
        return t

    for line in safe.split("\n"):
        s = line.strip()
        if s.startswith("- ") or s.startswith("* "):
            list_buf.append(inline(s[2:]))
            continue
        flush_list()
        if not s:
            continue
        out_lines.append(f"<p>{inline(s)}</p>")
    flush_list()

    return Markup("\n".join(out_lines))


async def build_infothek_context(
    db: AsyncSession,
    anlage_id: int,
    kategorie: Optional[str] = None,
) -> dict:
    """
    Lädt Einträge und liefert das Template-Context-Dict.

    Raises:
        LookupError: Wenn die Anlage nicht existiert.
        ValueError: Wenn keine Einträge zum Exportieren existieren.
    """
    res = await db.execute(select(Anlage).where(Anlage.id == anlage_id))
    anlage = res.scalar_one_or_none()
    if not anlage:
        raise LookupError(f"Anlage {anlage_id} nicht gefunden")

    q = (
        select(InfothekEintrag)
        .where(InfothekEintrag.anlage_id == anlage_id)
        .where(InfothekEintrag.aktiv == True)  # noqa: E712
        .order_by(InfothekEintrag.sortierung, InfothekEintrag.created_at.desc())
    )
    if kategorie:
        q = q.where(InfothekEintrag.kategorie == kategorie)
    res = await db.execute(q)
    eintraege_obj = list(res.scalars().all())

    if not eintraege_obj:
        raise ValueError("Keine Einträge zum Exportieren")

    # Vertragspartner-Map (alle, auch wenn gefiltert wurde — Verknüpfungen)
    vp_res = await db.execute(
        select(InfothekEintrag)
        .where(InfothekEintrag.anlage_id == anlage_id)
        .where(InfothekEintrag.kategorie == "ansprechpartner")
    )
    vp_map = {e.id: e.bezeichnung for e in vp_res.scalars().all()}

    def to_dict(e: InfothekEintrag) -> dict:
        params = e.parameter or {}
        schema_felder = INFOTHEK_KATEGORIEN.get(e.kategorie, {}).get("felder", {})
        felder: list[tuple[str, str]] = []
        for key, defn in schema_felder.items():
            val = params.get(key)
            if val not in (None, ""):
                felder.append((defn.get("label", key), str(val)))
        # Unbekannte Keys (z.B. Legacy)
        for key, val in params.items():
            if key not in schema_felder and val not in (None, ""):
                felder.append((key.replace("_", " ").title(), str(val)))

        vp_name = vp_map.get(e.ansprechpartner_id) if e.ansprechpartner_id else None

        return {
            "id": e.id,
            "bezeichnung": e.bezeichnung,
            "kategorie": e.kategorie,
            "felder": felder,
            "notizen_html": _markdown_to_html(e.notizen) if e.notizen else None,
            "vertragspartner": vp_name,
        }

    eintraege_dicts = [to_dict(e) for e in eintraege_obj]

    # Vertragspartner zuerst, dann nach Kategorie gruppiert (Reihenfolge erste-Vorkommen)
    sektionen: list[dict] = []
    if not kategorie:
        vp_eintraege = [e for e in eintraege_dicts if e["kategorie"] == "ansprechpartner"]
        if vp_eintraege:
            sektionen.append({
                "kategorie": "ansprechpartner",
                "label": KATEGORIE_LABELS["ansprechpartner"],
                "eintraege": vp_eintraege,
            })

    seen: dict[str, dict] = {}
    for e in eintraege_dicts:
        if e["kategorie"] == "ansprechpartner" and not kategorie:
            continue
        if e["kategorie"] not in seen:
            seen[e["kategorie"]] = {
                "kategorie": e["kategorie"],
                "label": KATEGORIE_LABELS.get(e["kategorie"], e["kategorie"]),
                "eintraege": [],
            }
            sektionen.append(seen[e["kategorie"]])
        seen[e["kategorie"]]["eintraege"].append(e)

    return {
        "anlage": {
            "id": anlage.id,
            "name": anlage.anlagenname,
            "standort_ort": anlage.standort_ort,
            "standort_plz": anlage.standort_plz,
        },
        "kategorie_filter": kategorie,
        "kategorie_filter_label": KATEGORIE_LABELS.get(kategorie, kategorie) if kategorie else None,
        "sektionen": sektionen,
        "anzahl_eintraege": len(eintraege_dicts),
        "erzeugt_am": datetime.now().strftime("%d.%m.%Y %H:%M"),
    }
