"""Hilfen der Custom-Import-Proben (Päckchen G, N-702 … N-709) — Aufruf und Ablesen, keine Prüfung.

Die Proben rufen die echten Routen-Funktionen (`apply_custom_import`, `preview_mapping`) mit einer echten
`UploadFile` in der Test-Sitzung (`db`-Fixture); gelesen wird danach dieselbe Sitzung. Genutzt von
`test_n702_custom_import_aggregat_registry.py`, `test_n703_custom_import_wallbox_mengen.py`,
`test_n704_custom_import_sonstiges_slot.py`, `test_n705_custom_import_inv_id_der_anlage.py`,
`test_n706_custom_import_vorschau_gleich_import.py`, `test_n707_import_pv_null_ist_messwert.py`,
`test_n708_custom_import_inv_vorzeichen.py`, `test_n709_custom_import_nur_entladung.py`.
"""

from __future__ import annotations

import io
import json
from typing import Iterable, Optional

from fastapi import UploadFile
from sqlalchemy import select

from backend.models.investition import InvestitionMonatsdaten
from backend.models.monatsdaten import Monatsdaten


def csv_text(kopf: list[str], *zeilen: Iterable) -> str:
    """Eine CSV mit Semikolon — wie die Dateien, die Anwender hochladen."""
    return "\n".join([";".join(kopf), *(";".join(str(z) for z in zeile) for zeile in zeilen)]) + "\n"


def mapping_json(
    zuordnung: list[tuple[str, str]], *, einheit: str = "kwh", dezimal: str = "auto",
    datum_spalte: Optional[str] = None, invertiert: Iterable[str] = (),
) -> str:
    inv = set(invertiert)
    return json.dumps({
        "mappings": [
            {"spalte": s, "eedc_feld": f, **({"invertieren": True} if s in inv else {})} for s, f in zuordnung
        ],
        "einheit": einheit,
        "dezimalzeichen": dezimal,
        "datum_spalte": datum_spalte,
    })


def _upload(text: str) -> UploadFile:
    return UploadFile(file=io.BytesIO(text.encode("utf-8")), filename="d.csv")


async def importiere(
    db, anlage_id: int, text: str, zuordnung: list[tuple[str, str]], monate: Iterable[tuple[int, int]],
    *, ueberschreiben: bool = False, **mapping_kw,
):
    """`POST /custom-import/apply/{anlage_id}` — direkt gerufen, wie die Route es tut."""
    from backend.api.routes.custom_import.apply import apply_custom_import

    return await apply_custom_import(
        anlage_id=anlage_id,
        file=_upload(text),
        mapping_json=mapping_json(zuordnung, **mapping_kw),
        monate_json=json.dumps([{"jahr": j, "monat": m} for j, m in monate]),
        ueberschreiben=ueberschreiben,
        db=db,
    )


async def vorschau(db, anlage_id: Optional[int], text: str, zuordnung: list[tuple[str, str]], **mapping_kw):
    """`POST /custom-import/preview` — direkt gerufen."""
    from backend.api.routes.custom_import.preview import preview_mapping

    return await preview_mapping(
        file=_upload(text), mapping_json=mapping_json(zuordnung, **mapping_kw), anlage_id=anlage_id, db=db,
    )


async def imd(db, investition_id: int, jahr: int, monat: int) -> Optional[dict]:
    """`verbrauch_daten` einer Geräte-Monatszeile, `None` ohne Zeile."""
    row = (await db.execute(select(InvestitionMonatsdaten).where(
        InvestitionMonatsdaten.investition_id == investition_id,
        InvestitionMonatsdaten.jahr == jahr,
        InvestitionMonatsdaten.monat == monat,
    ))).scalar_one_or_none()
    return None if row is None else dict(row.verbrauch_daten or {})


async def monatszeile(db, anlage_id: int, jahr: int, monat: int) -> Optional[Monatsdaten]:
    return (await db.execute(select(Monatsdaten).where(
        Monatsdaten.anlage_id == anlage_id, Monatsdaten.jahr == jahr, Monatsdaten.monat == monat,
    ))).scalar_one_or_none()
