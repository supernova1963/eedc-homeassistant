"""N-711 — Portal-Import mit Ziel-Gerät: eine gelieferte PV 0 kommt am Ziel an (0 ist ein Wert), leer bleibt leer.

Der gerätegebundene Weg (`data_import.py::_verteile_ziel_erzeugung`, eine Quelle je Wechselrichter, #349) schrieb PV
nur bei `(pv or 0) > 0`. Eine Station, die einen ganzen Monat 0 meldet (Defekt, Schnee), bekam damit KEINE Modulzeile;
die Monatszeile trägt auf diesem Weg mit Absicht keinen PV-Wert (P7). Gemessen am HEAD `98abc801` (zwei
Wechselrichter, Station A 1 000 kWh, Station B 0,0 kWh, je mit Ziel): Modul B ohne Zeile, Monats-Fakten
`pv_kwh = 1000`, `pv_vollstaendig = False`, Daten-Checker WARNING „PV-Erzeugung unvollständig in 1 Monat(en)" — die
Zahl stimmt, das Kennzeichen nicht. Dieselbe Regel wie N-707 am anlagenweiten Weg (Entscheid Master 12.10.).

Schwesterdateien: test_n707_import_pv_null_ist_messwert.py (die Regel am anlagenweiten Weg und im eigenen Format),
test_import_ziel_investition_349.py (der Ziel-Weg).
"""

from __future__ import annotations

import pytest
from sqlalchemy import select

from backend.api.routes.data_import import ApplyMonthInput, ApplyRequest, apply_import
from backend.models.investition import InvestitionMonatsdaten
from backend.services.monats_fakten import lade_monats_fakten
from backend.tests import factories

JAHR, MONAT = 2025, 6


async def _apply(db, anlage_id: int, ziel_id: int, **werte):
    antwort = await apply_import(
        anlage_id=anlage_id,
        data=ApplyRequest(
            monate=[ApplyMonthInput(jahr=JAHR, monat=MONAT, **werte)], ziel_investition_id=ziel_id,
        ),
        ueberschreiben=False, datenquelle="portal_import", db=db,
    )
    assert antwort.erfolg, antwort.fehler
    return antwort


async def _pv_modul(db, modul_id: int):
    row = (await db.execute(select(InvestitionMonatsdaten).where(
        InvestitionMonatsdaten.investition_id == modul_id,
        InvestitionMonatsdaten.jahr == JAHR, InvestitionMonatsdaten.monat == MONAT,
    ))).scalar_one_or_none()
    return None if row is None else (row.verbrauch_daten or {}).get("pv_erzeugung_kwh")


@pytest.mark.asyncio
async def test_station_mit_pv_null_ist_vollstaendig(db):
    from backend.services.daten_checker import DatenChecker

    ids = await factories.zwei_wechselrichter(db)
    await _apply(db, ids["anlage"], ids["Sofar 2200"]["wr"], pv_erzeugung_kwh=1000.0, netzbezug_kwh=200.0)
    await _apply(db, ids["anlage"], ids["Sofar 1100"]["wr"], pv_erzeugung_kwh=0.0)

    assert await _pv_modul(db, ids["Sofar 2200"]["modul"]) == 1000.0
    assert await _pv_modul(db, ids["Sofar 1100"]["modul"]) == 0.0, "die 0 der Station kommt am Ziel an"

    fakt = (await lade_monats_fakten(db, ids["anlage"], von=(JAHR, MONAT), bis=(JAHR, MONAT)))[0]
    assert fakt.erzeugung.pv_kwh == 1000.0
    assert fakt.erzeugung.pv_vollstaendig is True

    meldungen = [e.meldung for e in (await DatenChecker(db).check_anlage(ids["anlage"])).ergebnisse]
    assert not [m for m in meldungen if m.startswith("PV-Erzeugung unvollständig")], meldungen


@pytest.mark.asyncio
async def test_station_ohne_pv_wert_bleibt_leer(db):
    """Gegenprobe: liefert die Quelle keinen PV-Wert, entsteht keine Modulzeile (leer bleibt NULL)."""
    ids = await factories.zwei_wechselrichter(db)
    await _apply(db, ids["anlage"], ids["Sofar 2200"]["wr"], pv_erzeugung_kwh=1000.0, netzbezug_kwh=200.0)
    await _apply(db, ids["anlage"], ids["Sofar 1100"]["wr"], einspeisung_kwh=10.0)

    assert await _pv_modul(db, ids["Sofar 1100"]["modul"]) is None
    fakt = (await lade_monats_fakten(db, ids["anlage"], von=(JAHR, MONAT), bis=(JAHR, MONAT)))[0]
    assert fakt.erzeugung.pv_vollstaendig is False
