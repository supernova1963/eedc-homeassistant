"""
IA-V4 #243: `_check_investitionen` taggt komponenten-bezogene Befunde mit
`investition_id`, damit der Komponenten-Hub seine Daten-Checker-Befunde je
Gerät filtern kann. Anlagen-aggregierte Befunde (PV-Erzeugung über alle
Strings) lassen das Feld bewusst None.

        eedc/backend/tests/test_daten_checker_investition_id_tagging.py
"""

from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from backend.models import Anlage, Investition, Monatsdaten  # noqa: F401


async def test_per_komponente_befund_traegt_investition_id(db):
    """Stamm-/Monatsdaten-Befunde einer Investition tragen ihre investition_id."""
    from backend.services.daten_checker import DatenChecker

    anlage = Anlage(anlagenname="Test", leistung_kwp=10.0)
    db.add(anlage)
    await db.flush()
    # PV-Modul mit fehlender kWp → WARNING "Leistung (kWp) fehlt" (per Komponente).
    db.add(Investition(
        anlage_id=anlage.id, typ="pv-module", bezeichnung="Süd",
        leistung_kwp=None, anschaffungsdatum=date(2024, 1, 1), aktiv=True,
    ))
    await db.commit()

    anlage = (await db.execute(
        select(Anlage).options(selectinload(Anlage.investitionen)).where(Anlage.id == anlage.id)
    )).scalar_one()
    inv_id = anlage.investitionen[0].id

    checker = DatenChecker(db)
    ergebnisse = checker._check_investitionen(anlage, monatsdaten=[])

    kwp_befund = [r for r in ergebnisse if "Leistung (kWp) fehlt" in r.meldung]
    assert kwp_befund, "kWp-fehlt-Befund erwartet"
    assert all(r.investition_id == inv_id for r in kwp_befund), (
        f"Per-Komponente-Befund muss investition_id={inv_id} tragen, war: "
        f"{[(r.meldung, r.investition_id) for r in kwp_befund]}"
    )


async def test_anlagen_aggregat_traegt_keine_investition_id(db):
    """Anlagenweite PV-Erzeugungs-Befunde (vor der Investitions-Schleife)
    bleiben ungetaggt — sie gehören keinem einzelnen Gerät und damit nicht
    in den Komponenten-Hub-Filter."""
    from backend.services.daten_checker import DatenChecker

    anlage = Anlage(anlagenname="Test", leistung_kwp=10.0)
    db.add(anlage)
    await db.flush()
    db.add(Investition(
        anlage_id=anlage.id, typ="pv-module", bezeichnung="Süd",
        leistung_kwp=10.0, ausrichtung="Süd", neigung_grad=30,
        anschaffungsdatum=date(2024, 1, 1), aktiv=True,
    ))
    # Monatsdaten-Zeile ohne PV-Gesamtwert → _check_pv_erzeugung klassifiziert
    # den Monat als FEHLT (anlagenweiter ERROR, keinem Modul zuordenbar).
    md = Monatsdaten(anlage_id=anlage.id, jahr=2024, monat=6)
    db.add(md)
    await db.commit()

    anlage = (await db.execute(
        select(Anlage)
        .options(selectinload(Anlage.investitionen).selectinload(Investition.monatsdaten))
        .where(Anlage.id == anlage.id)
    )).scalar_one()
    monatsdaten = list((await db.execute(
        select(Monatsdaten).where(Monatsdaten.anlage_id == anlage.id)
    )).scalars())

    checker = DatenChecker(db)
    ergebnisse = checker._check_investitionen(anlage, monatsdaten=monatsdaten)

    pv_aggregat = [r for r in ergebnisse if "PV-Erzeugung fehlt" in r.meldung]
    assert pv_aggregat, (
        "anlagenweiter PV-Erzeugung-fehlt-Befund erwartet, alle: "
        f"{[(r.meldung, r.investition_id) for r in ergebnisse]}"
    )
    assert all(r.investition_id is None for r in pv_aggregat), (
        "anlagenweiter PV-Befund darf KEINE investition_id tragen, war: "
        f"{[(r.meldung, r.investition_id) for r in pv_aggregat]}"
    )
