"""Das Attribut `je_speicher` des SoC-Sensors nennt nur laufende Geräte
(Nachlese 4.0.50, Nachtrag c).

**Dieselbe Klasse wie A5, nur eine Fläche weiter — im Export.**
`api/routes/ha_export/anlage_steuerung.py` nahm für das Attribut `je_speicher` von
`eedc_speicher_soc_prozent` die letzte `TagesEnergieProfil`-Zeile mit
`soc_je_speicher` und reichte sie **ungefiltert** durch. Diese Spalte trägt die
Ladestände **aller** Geräte, die an dem Tag gemessen wurden — auch die eines
inzwischen ausgebauten. In Home Assistant stand damit unter `je_speicher` eine
Investitions-Nummer, die es nicht mehr gibt; eine Automation, die das Attribut
aufschlüsselt, sah ein Gerät zu viel.

**Woher der Wert kommt, ist gemessen und nicht angenommen:**
* **Der Sensorwert** ist `prognose["speicher_soc_prozent"]` (kapazitätsgewichtet
  über die laufenden Speicher, N-239) mit Rückfall auf `zeile.soc_prozent` — ein
  historischer Messwert der **Anlage**. Er bleibt richtig, auch wenn später ein
  Gerät ausgebaut wird, und wird hier **nicht** angefasst.
* **Das Attribut** kommt aus `TagesEnergieProfil.soc_je_speicher` — Schlüssel sind
  Investitions-IDs als Zeichenkette (`energie_profil/aggregator.py`), **nicht** aus
  einer Investitionsliste. Deshalb braucht die Phase eine: `_laufende_speicher()`.

⭐ **Die Abfrage ist keine zusätzliche.** Genau dieselbe stand bis dahin in
`_arbitrage_sensor` derselben Datei; sie ist jetzt einmal in der Phase und wird
dorthin durchgereicht — die Modulregel „holt nichts, was schon geholt wurde"
gilt auch für das Modul selbst.

Schwesterdateien: `test_s2_entscheidungs_sensoren.py` (die Phase als Ganzes, deren
Fixtures diese Probe nachnutzt), `test_sizing_median_je_speicher_nur_laufende.py`
(dieselbe Klasse im Sizing-Service, A5) und
`test_n546_sizing_ohne_stillgelegte_speicher.py` (der Ursprungsfall).

⚠ **Feste Daten, keine echte Uhr** (`test_konformitaet_echte_uhr_in_tests.py`):
die Zeit kommt als Parameter (`JETZT` aus der Schwesterdatei), die Stilllegungs-
daten liegen weit vor bzw. weit nach jedem Lauftag.
"""

from __future__ import annotations

from datetime import date

from backend.models import Investition
from backend.models.tages_energie_profil import (
    TagesEnergieProfil,
    TagesZusammenfassung,
)
from backend.tests.test_s2_entscheidungs_sensoren import (
    HEUTE,
    _anlage,
    _preis,
    _prognose,
    _rechne,
    _stelle_quellen,
)

STILLGELEGT_VERGANGENHEIT = date(2021, 3, 31)
STILLGELEGT_ZUKUNFT = date(2099, 12, 31)


async def _zwei_speicher(db, anlage_id: int, *, aktiv_alt: bool = True,
                         stillgelegt: date | None = STILLGELEGT_VERGANGENHEIT):
    """Erst das alte Gerät (kleinere ID), dann das laufende."""
    alt = Investition(
        anlage_id=anlage_id, typ="speicher", bezeichnung="Speicher alt",
        anschaffungsdatum=date(2015, 1, 1),
        parameter={"kapazitaet_kwh": 5.06},
        aktiv=aktiv_alt, stilllegungsdatum=stillgelegt,
    )
    db.add(alt)
    await db.flush()
    neu = Investition(
        anlage_id=anlage_id, typ="speicher", bezeichnung="Speicher neu",
        anschaffungsdatum=date(2025, 6, 1),
        parameter={"kapazitaet_kwh": 12.8},
    )
    db.add(neu)
    await db.commit()
    return alt.id, neu.id


async def _tagesprofil_mit_zwei_geraeten(db, anlage_id: int, alt_id: int, neu_id: int):
    """Wie `_tagesprofil` der Schwesterdatei, aber mit ZWEI Geräte-Ladeständen.

    Die beiden Werte sind verschieden (30 % alt, 70 % neu), damit ein Prüfer,
    der nur die Anzahl der Einträge zählt, von dem unterschieden wird, der die
    richtige ID behält.
    """
    for h in range(13):
        db.add(TagesEnergieProfil(
            anlage_id=anlage_id, datum=HEUTE, stunde=h,
            ueberschuss_kw=2.5 if h >= 10 else 0.0,
            defizit_kw=0.0 if h >= 10 else 1.2,
            netzbezug_kw=0.0 if h >= 10 else 1.2,
            soc_prozent=55.0 + h,
            soc_je_speicher={str(alt_id): 30.0 + h, str(neu_id): 70.0 + h},
        ))
    db.add(TagesZusammenfassung(
        anlage_id=anlage_id, datum=HEUTE,
        ueberschuss_kwh=7.5, defizit_kwh=12.0, peak_netzbezug_kw=4.8,
    ))
    await db.commit()


def _soc_sensor(werte):
    return next(w for w in werte if w.definition.key == "eedc_speicher_soc_prozent")


async def test_ausgebauter_speicher_steht_nicht_mehr_im_attribut(db, monkeypatch):
    anlage = await _anlage(db)
    alt_id, neu_id = await _zwei_speicher(db, anlage.id)
    await _tagesprofil_mit_zwei_geraeten(db, anlage.id, alt_id, neu_id)
    _stelle_quellen(monkeypatch, _prognose(), _preis())

    werte, _ = await _rechne(db, anlage)

    sensor = _soc_sensor(werte)
    assert sensor.zusatz_attribute["je_speicher"] == {str(neu_id): 82.0}, (
        "ungefiltert stünde hier auch das ausgebaute Gerät"
    )


async def test_abgewaehltes_geraet_ohne_datum_steht_auch_nicht_darin(db, monkeypatch):
    """`aktiv=False` = wie gelöscht — dieselbe Regel wie in `investition_filter`."""
    anlage = await _anlage(db)
    alt_id, neu_id = await _zwei_speicher(db, anlage.id, aktiv_alt=False, stillgelegt=None)
    await _tagesprofil_mit_zwei_geraeten(db, anlage.id, alt_id, neu_id)
    _stelle_quellen(monkeypatch, _prognose(), _preis())

    werte, _ = await _rechne(db, anlage)

    assert _soc_sensor(werte).zusatz_attribute["je_speicher"] == {str(neu_id): 82.0}


async def test_zwei_laufende_geraete_stehen_weiter_beide_darin(db, monkeypatch):
    """Die Gegenrichtung — sonst wäre unbelegt, dass das Attribut überhaupt füllt.

    Stilllegung in der Zukunft: angekündigt ist nicht ausgebaut, der **Stichtag**
    entscheidet und nicht die Anwesenheit eines Datums.
    """
    anlage = await _anlage(db)
    alt_id, neu_id = await _zwei_speicher(db, anlage.id, stillgelegt=STILLGELEGT_ZUKUNFT)
    await _tagesprofil_mit_zwei_geraeten(db, anlage.id, alt_id, neu_id)
    _stelle_quellen(monkeypatch, _prognose(), _preis())

    werte, _ = await _rechne(db, anlage)

    assert _soc_sensor(werte).zusatz_attribute["je_speicher"] == {
        str(alt_id): 42.0, str(neu_id): 82.0,
    }


async def test_der_sensorwert_selbst_bleibt_unberuehrt(db, monkeypatch):
    """Gefiltert wird die Aufschlüsselung, nicht der Ladestand der Anlage.

    Der Wert kommt aus der Prognose (hier gestellt: 40 %) — träfe der Filter
    auch ihn, wäre das ein stiller Eingriff in eine Messgröße.
    """
    anlage = await _anlage(db)
    alt_id, neu_id = await _zwei_speicher(db, anlage.id)
    await _tagesprofil_mit_zwei_geraeten(db, anlage.id, alt_id, neu_id)
    _stelle_quellen(monkeypatch, _prognose(), _preis())

    werte, _ = await _rechne(db, anlage)

    sensor = _soc_sensor(werte)
    assert sensor.value == 40.0
    voll = next(w for w in werte if w.definition.key == "eedc_speicher_voll")
    assert voll.zusatz_attribute["soc_prozent"] == 40.0


async def test_nur_ausgebaute_geraete_lassen_das_attribut_ganz_weg(db, monkeypatch):
    """`None` statt `{}` — ein leeres Dict hieße „aufgeschlüsselt, Ergebnis leer".

    `_anhaengen` verwirft `None`-Attribute; der Sensor selbst bleibt, weil sein
    Wert aus der Prognose kommt.
    """
    anlage = await _anlage(db)
    alt = Investition(
        anlage_id=anlage.id, typ="speicher", bezeichnung="Speicher alt",
        anschaffungsdatum=date(2015, 1, 1),
        stilllegungsdatum=STILLGELEGT_VERGANGENHEIT,
    )
    db.add(alt)
    await db.commit()
    for h in range(13):
        db.add(TagesEnergieProfil(
            anlage_id=anlage.id, datum=HEUTE, stunde=h,
            ueberschuss_kw=2.5 if h >= 10 else 0.0,
            defizit_kw=0.0 if h >= 10 else 1.2,
            netzbezug_kw=0.0 if h >= 10 else 1.2,
            soc_prozent=55.0 + h,
            soc_je_speicher={str(alt.id): 30.0 + h},
        ))
    db.add(TagesZusammenfassung(
        anlage_id=anlage.id, datum=HEUTE,
        ueberschuss_kwh=7.5, defizit_kwh=12.0, peak_netzbezug_kw=4.8,
    ))
    await db.commit()
    _stelle_quellen(monkeypatch, _prognose(), _preis())

    werte, _ = await _rechne(db, anlage)

    sensor = _soc_sensor(werte)
    assert sensor.value == 40.0
    assert "je_speicher" not in sensor.zusatz_attribute
