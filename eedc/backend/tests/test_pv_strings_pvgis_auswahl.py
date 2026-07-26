"""Cockpit-PV-Strings: SOLL kommt aus der AKTIVEN PVGIS-Prognose (N46).

`api/routes/cockpit/pv_strings.py` wählte in beiden Endpoints nur per
`order_by(abgerufen_am.desc())` — ohne `ist_aktiv`. Der gelebte SoT im übrigen
Repo (13 Lesestellen, zuletzt b2025e0e für den PDF-Jahresbericht) ist aber
`ist_aktiv == True` **plus** `abgerufen_am.desc()` als Tiebreak.

Der Unterschied ist kein Detail: `POST /api/pvgis/prognose/{id}/aktivieren`
(api/routes/pvgis.py:810-834) lässt den Nutzer ausdrücklich eine ÄLTERE Prognose
aktivieren. „Neueste" hat diesen Willen still übersteuert — die SOLL-Kurve im
Cockpit blieb die der neuen Prognose, während Cockpit-Übersicht, Aussichten,
HA-Sensoren und PDF längst die aktive lesen.
"""

from __future__ import annotations

from datetime import date, datetime

import pytest
from sqlalchemy import select

from backend.api.routes.cockpit.pv_strings import (
    get_pv_strings,
    get_pv_strings_gesamtlaufzeit,
)
from backend.models import Anlage, Investition, InvestitionMonatsdaten, Monatsdaten
from backend.models.pvgis_prognose import PVGISPrognose

# Die ältere Prognose ist die aktive — genau der Fall, den „neueste" verfehlt.
AKTIV_ALT_JAHR = 9_000.0
NEU_INAKTIV_JAHR = 18_000.0


def _monatswerte(jahressumme: float) -> list[dict]:
    return [{"monat": m, "e_m": jahressumme / 12, "h_m": 100.0, "sd_m": 10.0} for m in range(1, 13)]


async def _seed(db) -> int:
    """Ein 10-kWp-String mit IST in Mai 2026, dazu zwei Prognosen."""
    anlage = Anlage(anlagenname="PVGIS-Auswahl-Strings", leistung_kwp=10.0)
    db.add(anlage)
    await db.flush()
    db.add(Monatsdaten(anlage_id=anlage.id, jahr=2026, monat=5,
                       einspeisung_kwh=300.0, netzbezug_kwh=200.0))
    modul = Investition(anlage_id=anlage.id, typ="pv-module", bezeichnung="Süd",
                        anschaffungsdatum=date(2024, 1, 1), leistung_kwp=10.0)
    db.add(modul)
    await db.flush()
    db.add(InvestitionMonatsdaten(investition_id=modul.id, jahr=2026, monat=5,
                                  verbrauch_daten={"pv_erzeugung_kwh": 1000.0}))

    gemeinsam = dict(anlage_id=anlage.id, latitude=48.0, longitude=11.0,
                     neigung_grad=30.0, ausrichtung_grad=0.0, gesamt_leistung_kwp=10.0)
    db.add(PVGISPrognose(
        **gemeinsam, abgerufen_am=datetime(2024, 3, 1, 12, 0),
        jahresertrag_kwh=AKTIV_ALT_JAHR, spezifischer_ertrag_kwh_kwp=AKTIV_ALT_JAHR / 10.0,
        monatswerte=_monatswerte(AKTIV_ALT_JAHR), ist_aktiv=True,
    ))
    db.add(PVGISPrognose(
        **gemeinsam, abgerufen_am=datetime(2026, 2, 1, 12, 0),
        jahresertrag_kwh=NEU_INAKTIV_JAHR, spezifischer_ertrag_kwh_kwp=NEU_INAKTIV_JAHR / 10.0,
        monatswerte=_monatswerte(NEU_INAKTIV_JAHR), ist_aktiv=False,
    ))
    await db.commit()
    return anlage.id


async def test_jahressicht_nimmt_die_aktive_nicht_die_neueste(db):
    """`/cockpit/pv-strings`: SOLL Mai = 9.000/12, nicht 18.000/12."""
    anlage_id = await _seed(db)
    resp = await get_pv_strings(anlage_id=anlage_id, jahr=2026, db=db)
    assert resp.hat_prognose is True
    assert resp.prognose_gesamt_kwh == pytest.approx(AKTIV_ALT_JAHR / 12, abs=0.5)
    assert resp.prognose_gesamt_kwh != pytest.approx(NEU_INAKTIV_JAHR / 12, abs=0.5), (
        "Cockpit-Jahressicht wählt wieder die neueste statt der aktiven Prognose."
    )


async def test_gesamtlaufzeit_nimmt_die_aktive_nicht_die_neueste(db):
    """`/cockpit/pv-strings-gesamtlaufzeit`: gleiche Regel, gleicher Wert."""
    anlage_id = await _seed(db)
    resp = await get_pv_strings_gesamtlaufzeit(anlage_id=anlage_id, db=db)
    assert resp.prognose_gesamt_kwh == pytest.approx(AKTIV_ALT_JAHR / 12, abs=0.5)


async def test_beide_endpoints_sind_symmetrisch(db):
    """Zwei Sichten derselben Anlage dürfen nicht auf verschiedenen Prognosen stehen."""
    anlage_id = await _seed(db)
    jahr = await get_pv_strings(anlage_id=anlage_id, jahr=2026, db=db)
    gesamt = await get_pv_strings_gesamtlaufzeit(anlage_id=anlage_id, db=db)
    assert jahr.prognose_gesamt_kwh == pytest.approx(gesamt.prognose_gesamt_kwh, abs=0.5)


async def test_umschalten_der_aktiven_prognose_wirkt(db):
    """Aktiviert der Nutzer die neuere, folgen beide Endpoints — `ist_aktiv` entscheidet."""
    anlage_id = await _seed(db)
    prognosen = list((await db.execute(
        select(PVGISPrognose).where(PVGISPrognose.anlage_id == anlage_id)
    )).scalars().all())
    # Zwei Phasen wie im Aktivieren-Endpoint: erst deaktivieren + flushen, dann
    # aktivieren. Der partielle Unique-Index (A17) lässt keine zwei aktiven
    # Prognosen je Anlage zu, auch nicht kurzzeitig innerhalb eines Flushes.
    for p in prognosen:
        p.ist_aktiv = False
    await db.flush()
    for p in prognosen:
        if p.jahresertrag_kwh == NEU_INAKTIV_JAHR:
            p.ist_aktiv = True
    await db.flush()

    jahr = await get_pv_strings(anlage_id=anlage_id, jahr=2026, db=db)
    gesamt = await get_pv_strings_gesamtlaufzeit(anlage_id=anlage_id, db=db)
    assert jahr.prognose_gesamt_kwh == pytest.approx(NEU_INAKTIV_JAHR / 12, abs=0.5)
    assert gesamt.prognose_gesamt_kwh == pytest.approx(NEU_INAKTIV_JAHR / 12, abs=0.5)


async def test_ohne_aktive_prognose_keine_soll_werte(db):
    """Kein Fallback auf „irgendeine": ohne aktive Prognose bleibt SOLL leer —
    wie Cockpit-Übersicht und Aussichten, keine Sonderregel für diese Sicht."""
    anlage_id = await _seed(db)
    for p in (await db.execute(
        select(PVGISPrognose).where(PVGISPrognose.anlage_id == anlage_id)
    )).scalars().all():
        p.ist_aktiv = False
    await db.flush()

    resp = await get_pv_strings(anlage_id=anlage_id, jahr=2026, db=db)
    assert resp.hat_prognose is False
    assert resp.prognose_gesamt_kwh == 0
    # Das IST bleibt davon unberührt — nur die SOLL-Seite fehlt.
    assert resp.ist_gesamt_kwh == pytest.approx(1000.0)
