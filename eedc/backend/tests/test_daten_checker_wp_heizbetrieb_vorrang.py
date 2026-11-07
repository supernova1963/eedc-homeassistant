"""Daten-Checker: «Strom Heizbetrieb» und «Strom Heizen» an derselben Wärmepumpe beide zugeordnet (Triage 3.11.2026, P12).

Melderfall pipp086 #438: im Betriebsart-Feld «Strom Heizbetrieb» lag ein anderer Zähler, daneben «Strom Heizen» — eedc
zählt nach `core/berechnungen/betriebsart_gemessen.py::modus_strom_zeile` nur den Betriebsart-Zähler, Heizen zeigte den
Kühlwert, ohne dass eine Fläche den Grund nannte. Der Checker meldet jetzt die Doppelbelegung (WARNING, Kategorie
Investitionen, Handbuch Daten-Checker §4.3.7). Nur Heizen: Warmwasser hat keinen Betriebsart-Zähler, Kühlen keinen
Summanden (gemessen an `BETRIEBSART_STROM_FELD` und `FEINE_STROM_FELDER`).

Schwesterdateien: test_daten_checker_arbitrage_v2h_preise_397.py (dieselbe Einstiegsstelle `_check_investitionen`),
test_wp_klimaanlage_phase1.py.
"""

from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from backend.core.betriebsmodus import BETRIEBSART_STROM_FELD, HEIZEN
from backend.core.field_definitions.wp_strom import FEINE_STROM_FELDER
from backend.models import Anlage, Investition, Monatsdaten
from backend.services.daten_checker import DatenChecker
from backend.tests import factories

JAHR = 2026
MELDUNG = "„Strom Heizbetrieb“ und „Strom Heizen“ beide belegt"


def _s(eid: str) -> dict:
    return {"strategie": "sensor", "sensor_id": eid}


async def _meldungen(db, *, felder: dict, quellen: dict | None = None, parameter: dict | None = None,
                     meldung: str = MELDUNG) -> list:
    anlage = await factories.anlage(db, standort_land="DE")
    db.add(Monatsdaten(anlage_id=anlage.id, jahr=JAHR, monat=1))
    wp = Investition(anlage_id=anlage.id, typ="waermepumpe", bezeichnung="WP Haus",
                     anschaffungsdatum=date(JAHR - 1, 1, 1), anschaffungskosten_alternativ=0.0,
                     parameter={"getrennte_strommessung": True} if parameter is None else parameter)
    db.add(wp)
    await db.flush()
    anlage.sensor_mapping = {
        "investitionen": {str(wp.id): {"felder": felder}},
        **({"quellen": {f"inv_energy_{wp.id}_{k}": {"quelle": v} for k, v in quellen.items()}} if quellen else {}),
    }
    await db.commit()
    geladen = (await db.execute(
        select(Anlage).options(selectinload(Anlage.investitionen).selectinload(Investition.monatsdaten))
        .where(Anlage.id == anlage.id)
    )).scalar_one()
    monatsdaten = list((await db.execute(select(Monatsdaten).where(Monatsdaten.anlage_id == anlage.id))).scalars().all())
    return [e for e in DatenChecker(db)._check_investitionen(geladen, monatsdaten) if meldung in e.meldung]


def test_nur_heizen_traegt_zwei_felder_fuer_dieselbe_menge():
    """Die Reichweite des Hinweises, am Code gemessen: Betriebsart-Zähler ∩ Summanden = nur Heizen."""
    summanden_modi = {f.removeprefix("strom_").removesuffix("_kwh") for f in FEINE_STROM_FELDER}
    betriebsart_modi = set(BETRIEBSART_STROM_FELD)
    assert summanden_modi & betriebsart_modi == {HEIZEN}


async def test_beide_belegt_warning(db):
    treffer = await _meldungen(db, felder={
        BETRIEBSART_STROM_FELD[HEIZEN]: _s("sensor.wp_heizbetrieb"),
        "strom_heizen_kwh": _s("sensor.wp_heizen"),
    })
    assert len(treffer) == 1
    e = treffer[0]
    assert e.schwere == "warning"
    assert e.kategorie == "investitionen"
    assert "hat Vorrang" in e.details and "wird nicht gezählt" in e.details
    assert "lässt den Betriebsart-Zähler leer" in e.details
    assert e.investition_id is not None


@pytest.mark.parametrize("felder", [
    {BETRIEBSART_STROM_FELD[HEIZEN]: _s("sensor.wp_heizbetrieb")},
    {"strom_heizen_kwh": _s("sensor.wp_heizen"), "strom_warmwasser_kwh": _s("sensor.wp_ww")},
], ids=["nur-betriebsart", "nur-summanden"])
async def test_nur_eines_belegt_kein_hinweis(db, felder):
    assert await _meldungen(db, felder=felder) == []


async def test_quellenwahl_keine_schlaegt_alte_ha_zuordnung(db):
    """Datenquellen-Fläche «keine» am Betriebsart-Feld ⇒ nicht zugeordnet, auch wenn im Mapping noch ein Sensor steht."""
    treffer = await _meldungen(
        db,
        felder={BETRIEBSART_STROM_FELD[HEIZEN]: _s("sensor.alt"), "strom_heizen_kwh": _s("sensor.wp_heizen")},
        quellen={BETRIEBSART_STROM_FELD[HEIZEN]: "keine"},
    )
    assert treffer == []


async def test_mqtt_quelle_zaehlt_als_zugeordnet(db):
    treffer = await _meldungen(
        db, felder={"strom_heizen_kwh": _s("sensor.wp_heizen")},
        quellen={BETRIEBSART_STROM_FELD[HEIZEN]: "mqtt_inbound_standard"},
    )
    assert len(treffer) == 1


# ── Päckchen R (Melder pipp086 #463): «Strom Heizen/Warmwasser» zugeordnet, Schalter «Getrennte Strommessung» aus ──

OHNE_SCHALTER = "Strom Heizen/Warmwasser zugeordnet, aber „Getrennte Strommessung“ ist aus"


async def test_summanden_zugeordnet_schalter_aus_warning(db):
    treffer = await _meldungen(db, felder={"strom_heizen_kwh": _s("sensor.wp_heizen"),
                                           "strom_warmwasser_kwh": _s("sensor.wp_ww")},
                               parameter={}, meldung=OHNE_SCHALTER)
    assert len(treffer) == 1
    e = treffer[0]
    assert e.schwere == "warning" and e.kategorie == "investitionen"
    assert e.meldung.startswith("WP Haus")
    assert "„Strom Heizen“ und „Strom Warmwasser“" in e.details
    assert "Einstellungen → Komponenten → WP Haus → bearbeiten" in e.details
    assert "nicht aufgeteilt" in e.details
    assert e.investition_id is not None


async def test_nur_warmwasser_zugeordnet_schalter_aus_warning(db):
    treffer = await _meldungen(db, felder={"strom_warmwasser_kwh": _s("sensor.wp_ww")},
                               parameter={"getrennte_strommessung": False}, meldung=OHNE_SCHALTER)
    assert len(treffer) == 1 and "Zugeordnet: „Strom Warmwasser“." in treffer[0].details


async def test_schalter_an_kein_hinweis(db):
    assert await _meldungen(db, felder={"strom_heizen_kwh": _s("sensor.wp_heizen")},
                            meldung=OHNE_SCHALTER) == []


async def test_ohne_zuordnung_kein_hinweis(db):
    """Schalter aus, nur der Gesamtzähler zugeordnet (der Normalfall) ⇒ keine Meldung; «keine» als Quellenwahl ebenso."""
    assert await _meldungen(db, felder={"stromverbrauch_kwh": _s("sensor.wp_gesamt")},
                            parameter={}, meldung=OHNE_SCHALTER) == []
    assert await _meldungen(db, felder={"strom_heizen_kwh": _s("sensor.alt")}, quellen={"strom_heizen_kwh": "keine"},
                            parameter={}, meldung=OHNE_SCHALTER) == []
