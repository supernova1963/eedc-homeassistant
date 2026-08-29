"""N-346 — der Daten-Checker sagt, warum der Stundenverbrauch leer bleibt.

Der Fix zu N-346 macht aus einer falschen Zahl ein „unbekannt": Fehlt bei einer
Anlage mit aktivem Speicher eine Batterie-Richtung, bleibt der stündliche
Hausverbrauch leer statt still auf den reinen Netzbezug zu fallen. **Das allein
lässt den Anwender vor einem Strich ohne Grund stehen** — genau die P-6-Falle.
Deshalb gehört dieser Hinweis in dasselbe Paket wie der Fix.

Geprüft wird beides: dass er meldet, *und* dass er unterscheidet.

Schwesterdateien: ``test_daten_checker_klima_betriebsart.py`` (dieselbe Bauform —
ein Gerät ohne Zuordnung, zwei Ablagen `felder`/`quellen`) und
``test_346_stundenbilanz_batterie.py``, das die andere Hälfte desselben Fundes
trägt: dort die Rechnung, hier ihre Erklärung.
"""

from datetime import date

import pytest

from backend.models import Anlage, Investition
from backend.services.daten_checker import DatenChecker
from backend.services.daten_checker.kategorien import CheckKategorie, CheckSeverity

pytestmark = pytest.mark.asyncio

KAT = CheckKategorie.SPEICHER_ZAEHLER_RICHTUNGEN.value


def _sensor(sid: str) -> dict:
    return {"strategie": "sensor", "sensor_id": sid}


async def _anlage_mit_speicher(db, *, felder=None, quellen=None, **inv_kw):
    anlage = Anlage(
        anlagenname="Speicher-Probe", leistung_kwp=10.0,
        installationsdatum=date(2025, 1, 1),
    )
    db.add(anlage)
    await db.flush()
    daten = dict(
        anlage_id=anlage.id, typ="speicher", bezeichnung="Hausakku",
        anschaffungsdatum=date(2025, 1, 1), anschaffungskosten_gesamt=8000.0,
    )
    daten.update(inv_kw)
    inv = Investition(**daten)
    db.add(inv)
    await db.flush()
    mapping: dict = {"basis": {}, "investitionen": {}}
    if felder is not None:
        mapping["investitionen"][str(inv.id)] = {"felder": felder}
    if quellen is not None:
        mapping["quellen"] = {
            f"inv_energy_{inv.id}_{feld}": eintrag
            for feld, eintrag in quellen.items()
        }
    anlage.sensor_mapping = mapping
    await db.commit()
    return anlage, inv


async def _meldungen(db, anlage):
    return await DatenChecker(db)._check_speicher_zaehler_richtungen(anlage)


async def test_gar_kein_zaehler_wird_gemeldet(db):
    anlage, _ = await _anlage_mit_speicher(db, felder={})
    meldungen = await _meldungen(db, anlage)
    assert len(meldungen) == 1
    assert meldungen[0].kategorie == KAT
    assert meldungen[0].schwere == CheckSeverity.WARNING
    assert "Weder Ladung noch Entladung" in meldungen[0].details


async def test_nur_ladung_wird_gemeldet_und_nennt_die_nacht(db):
    """Der Melderfall: die fehlende Richtung ist die, die nachts läuft."""
    anlage, _ = await _anlage_mit_speicher(
        db, felder={"ladung_kwh": _sensor("sensor.lade")},
    )
    meldungen = await _meldungen(db, anlage)
    assert len(meldungen) == 1
    assert "die nachts läuft" in meldungen[0].details


async def test_beide_zaehler_melden_nichts(db):
    anlage, _ = await _anlage_mit_speicher(db, felder={
        "ladung_kwh": _sensor("sensor.lade"),
        "entladung_kwh": _sensor("sensor.entlade"),
    })
    assert await _meldungen(db, anlage) == []


async def test_mqtt_zuordnung_zaehlt_ebenso(db):
    """Zwei Ablagen, beide gelten — nur `felder` zu prüfen hieße, jeden
    MQTT-Nutzer falsch zu melden (derselbe Fehler wie einmal beim Klima-Check)."""
    anlage, _ = await _anlage_mit_speicher(
        db,
        felder={},
        quellen={
            "ladung_kwh": {"quelle": "mqtt"},
            "entladung_kwh": {"quelle": "mqtt"},
        },
    )
    assert await _meldungen(db, anlage) == []


async def test_ausdrueckliches_keine_ist_keine_zuordnung(db):
    """„keine" ist eine Absage, kein Zähler — sonst schweigt der Hinweis
    ausgerechnet dort, wo die Bilanz sicher nicht bildbar ist."""
    anlage, _ = await _anlage_mit_speicher(
        db,
        felder={"ladung_kwh": _sensor("sensor.lade")},
        quellen={"entladung_kwh": {"quelle": "keine"}},
    )
    assert len(await _meldungen(db, anlage)) == 1


async def test_stillgelegter_speicher_fordert_nichts_ein(db):
    """`ist_aktiv_an` statt `aktiv` allein — N-64/N-313-Klasse."""
    anlage, _ = await _anlage_mit_speicher(
        db, felder={}, stilllegungsdatum=date(2025, 6, 30),
    )
    assert await _meldungen(db, anlage) == []


async def test_anlage_ohne_speicher_meldet_nichts(db):
    anlage = Anlage(
        anlagenname="Ohne Speicher", leistung_kwp=10.0,
        installationsdatum=date(2025, 1, 1), sensor_mapping={},
    )
    db.add(anlage)
    await db.commit()
    assert await _meldungen(db, anlage) == []
