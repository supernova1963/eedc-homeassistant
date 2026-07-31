"""Der Community-Payload nennt dieselbe Bilanz wie der Bildschirm (S6, P10).

`services/community_service.py::prepare_community_data` war bis 2026-07-31 die
letzte Sicht des Bauplans (`docs/KONZEPT-MONATS-FAKTEN.md` §5, Schritt 6), die
eine **anlagenweite** Monatszeile selbst faltete — `select(InvestitionMonatsdaten,
Investition).join(...)`, Gruppierung nach `(jahr, monat)`, rohe PV-Summe. Sie
stand dafür als einziger befristeter Eintrag in `P10_NOCH_NICHT_MIGRIERT`.

Verloren gingen dabei **drei** Achsen — die Inventur hatte diese Sicht nur auf
die erste abgeklopft:

1. **F-5, die P7-Auflösung der PV.** Eine Anlage, die ihre Erzeugung als
   Anlagen-Aggregat statt je Modul pflegt, kam auf 0 kWh — und weil ein Monat
   ohne PV übersprungen wird, blieb `monatswerte` **leer**. `/community/share`
   bricht dann mit HTTP 400 („Keine Monatsdaten vorhanden") ab: diese Anlagen
   konnten am Benchmark **gar nicht teilnehmen**. Härter als in den vier
   Finanz-Sichten, wo dieselbe Ursache „nur" 32 € statt 212 € ergab.
2. **F-1, V2H und der Erzeuger hinter dem Zähler.** Die Autarkie rechnete mit
   PV + BKW statt mit `erzeugung_hinter_zaehler_kwh` und ohne V2H — der
   Community-Server bekam also eine andere Autarkie, als das Cockpit derselben
   Anlage auf dem Bildschirm nannte.
3. **Der Dienstwagen-Filter.** `eauto_km`, `eauto_ladung_*` und `eauto_v2h_kwh`
   zählten ein als dienstlich markiertes Fahrzeug voll mit
   ([[feedback_dienstwagen_alle_checks]]: Dienstwagen sind von allen
   anlagenbezogenen Berechnungen ausgenommen).

**Was NICHT ins Poolen kippt:** der Server führt `eauto_*` und `wallbox_*` als
getrennte Felder. Die Schicht liefert dafür `emob.eauto_summe` /
`emob.wallbox_summe` (getrennt, aber über denselben SoT-Leser) — der
Heimladungs-Pool `get_emob_heimladung_canonical` wählt genau EINE Quelle und
wäre hier die falsche Antwort. Der letzte Test nagelt das fest.
"""

from __future__ import annotations

from datetime import date

import pytest

from backend.api.routes.cockpit.uebersicht import get_cockpit_uebersicht
from backend.models import Anlage, Investition, Monatsdaten
from backend.models.investition import InvestitionMonatsdaten
from backend.services.community_service import prepare_community_data
from backend.tests.test_netto_ertrag_vier_wege_symmetrie import (
    anlage_mit_v2h_und_bhkw,
    anlage_nur_mit_aggregat,
)


async def _erster_monatswert(db, anlage_id: int) -> dict | None:
    data = await prepare_community_data(db, anlage_id)
    assert data is not None
    return data["monatswerte"][0] if data["monatswerte"] else None


# ============================================================================
# Achse 1 — nur das Anlagen-Aggregat gepflegt (F-5)
# ============================================================================


@pytest.mark.asyncio
async def test_aggregat_anlage_kann_ueberhaupt_teilnehmen(db):
    """Der F-5-Beweis für den Community-Pfad: aus „gar nichts" wird ein Monat.

    Fixture: 1.000 kWh, gepflegt als `Monatsdaten.pv_erzeugung_kwh`; das PV-Modul
    hat keine eigene Zeile. Vor dem Umbau lieferte `prepare_community_data` eine
    **leere** `monatswerte`-Liste — der Share-Endpoint antwortet darauf mit
    HTTP 400, und der Auto-Share nach dem Monatsabschluss überspringt die Anlage
    stillschweigend (`monatsabschluss/wizard.py`).

        PV               = 1.000 kWh (Aggregat auf das eine Modul aufgelöst)
        Direktverbrauch  = 1.000 − 400 =   600 kWh
        Gesamtverbrauch  =   600 + 100 =   700 kWh
        Autarkie         =   600 / 700 =  85,7 %
        EV-Quote         = 600 / 1.000 =  60,0 %
    """
    anlage_id = await anlage_nur_mit_aggregat(db)

    mw = await _erster_monatswert(db, anlage_id)

    assert mw is not None, "Die Aggregat-Anlage kann immer noch nichts teilen (F-5)."
    assert mw["ertrag_kwh"] == pytest.approx(1000.0)
    assert mw["einspeisung_kwh"] == pytest.approx(400.0)
    assert mw["netzbezug_kwh"] == pytest.approx(100.0)
    assert mw["autarkie_prozent"] == pytest.approx(85.7)
    assert mw["eigenverbrauch_prozent"] == pytest.approx(60.0)


# ============================================================================
# Achse 2 — V2H + Erzeuger hinter dem Zähler (F-1)
# ============================================================================


@pytest.mark.asyncio
async def test_autarkie_ist_deckungsgleich_mit_dem_cockpit(db):
    """Der Benchmark nennt dieselbe Autarkie wie der Bildschirm daneben.

    Ein Monat, also ist die Perioden-Zahl des Cockpits exakt die Monatszahl des
    Payloads (dieselbe Schnitt-Begründung wie in
    `test_co2_autarkie_sichten_symmetrie`).

        Erzeugung hinter dem Zähler = 1.000 (PV) + 300 (BHKW) = 1.300 kWh
        Direktverbrauch             = 1.300 − 400             =   900 kWh
        Eigenverbrauch              = 900 + 100 (V2H)         = 1.000 kWh
        Autarkie                    = 1.000 / 1.100           =    90,9 %

    Vorher: 600 / 700 = 85,7 % — das BHKW fiel weg, V2H fehlte ganz.
    """
    anlage_id = await anlage_mit_v2h_und_bhkw(db, km=1000.0, name="Community-V2H-BHKW")

    cockpit = await get_cockpit_uebersicht(anlage_id=anlage_id, jahr=None, db=db)
    mw = await _erster_monatswert(db, anlage_id)

    assert mw is not None
    assert mw["autarkie_prozent"] == pytest.approx(90.9)
    assert mw["autarkie_prozent"] == pytest.approx(cockpit.autarkie_prozent, abs=0.1), (
        "Der Community-Server bekommt eine andere Autarkie als das Cockpit zeigt."
    )


@pytest.mark.asyncio
async def test_ertrag_bleibt_die_pv_achse_ohne_bhkw(db):
    """`ertrag_kwh` ist Module + BKW — **nicht** die Erzeugung hinter dem Zähler.

    Die Nicht-Bewertung von v3.45.4, hier aus einem anderen Grund als in der
    Finanz-Zeile: der Server rechnet aus `ertrag_kwh` den spezifischen Ertrag je
    kWp (`spez_ertrag_kwh_kwp`). Ein BHKW dort hineinzurechnen würde jede
    Anlage mit Brennstoff-Erzeuger im PV-Ranking nach oben schieben.

    Gegenprobe zum Test darüber: dieselbe Fixture, dieselbe Anfrage — die
    Autarkie trägt die 300 kWh BHKW, `ertrag_kwh` nicht.
    """
    anlage_id = await anlage_mit_v2h_und_bhkw(db, km=1000.0, name="Community-Ertrag")

    mw = await _erster_monatswert(db, anlage_id)

    assert mw is not None
    assert mw["ertrag_kwh"] == pytest.approx(1000.0), (
        "Das BHKW ist in den PV-Ertrag geraten — der spezifische Ertrag je kWp "
        "wäre damit für jede Anlage mit Brennstoff-Erzeuger zu hoch."
    )
    # 1.000 kWh Eigenverbrauch auf 1.300 kWh Erzeugung hinter dem Zähler.
    assert mw["eigenverbrauch_prozent"] == pytest.approx(76.9)


# ============================================================================
# Achse 3 — Dienstwagen
# ============================================================================


@pytest.mark.asyncio
async def test_dienstwagen_zaehlt_im_payload_nicht_mit(db):
    """Ein dienstliches Fahrzeug ist keine Aussage über diese Anlage.

    Dieselbe Fixture wie oben, nur mit `ist_dienstlich` — der Payload darf dann
    weder km noch Ladung noch V2H des Fahrzeugs tragen. Vorher standen dort
    1.000 km, 200 kWh Ladung und 100 kWh V2H; die Community-Gesamtsumme
    „X km elektrisch gefahren" (`CommunityImpact` auf energy.raunet.eu) zählte
    sie mit.

    Und die Bilanz folgt derselben Regel: ohne V2H bleiben
    900 kWh Eigenverbrauch auf 1.000 kWh Gesamtverbrauch → 90,0 % Autarkie.
    """
    anlage_id = await anlage_mit_v2h_und_bhkw(
        db, km=1000.0, name="Community-Dienstwagen",
        eauto_parameter={"ist_dienstlich": True},
    )

    mw = await _erster_monatswert(db, anlage_id)

    assert mw is not None
    assert "eauto_km" not in mw
    assert "eauto_ladung_gesamt_kwh" not in mw
    assert "eauto_v2h_kwh" not in mw
    assert mw["autarkie_prozent"] == pytest.approx(90.0)


# ============================================================================
# Achse 4 — Netz-Anteil ohne gepflegten Schlüssel (#262)
# ============================================================================


async def _anlage_mit_evcc_ladung(db) -> int:
    """E-Auto-Zeile im evcc-Zuschnitt: `ladung_kwh` + `ladung_pv_kwh`, kein Netz.

    Der Portal-Import liefert pro Session nur „Energie" und „Sonne (%)" (#262
    junky84) und schreibt deshalb kein `ladung_netz_kwh`. Wer die drei Felder
    roh liest, sieht Netz = 0 — und meldet damit eine zu kleine Gesamtladung.
    """
    anlage = Anlage(anlagenname="evcc", leistung_kwp=10.0)
    db.add(anlage)
    await db.flush()
    db.add(Monatsdaten(anlage_id=anlage.id, jahr=2026, monat=6,
                       einspeisung_kwh=400.0, netzbezug_kwh=100.0))
    pv = Investition(anlage_id=anlage.id, typ="pv-module", bezeichnung="Dach",
                     leistung_kwp=10.0, anschaffungsdatum=date(2024, 1, 1))
    eauto = Investition(anlage_id=anlage.id, typ="e-auto", bezeichnung="Kombi",
                        anschaffungsdatum=date(2024, 1, 1), parameter={})
    db.add_all([pv, eauto])
    await db.flush()
    db.add(InvestitionMonatsdaten(investition_id=pv.id, jahr=2026, monat=6,
                                  verbrauch_daten={"pv_erzeugung_kwh": 1000.0}))
    db.add(InvestitionMonatsdaten(
        investition_id=eauto.id, jahr=2026, monat=6,
        verbrauch_daten={"ladung_kwh": 200.0, "ladung_pv_kwh": 150.0,
                         "km_gefahren": 1000.0},
    ))
    await db.commit()
    return anlage.id


@pytest.mark.asyncio
async def test_ladung_ohne_gepflegten_netz_schluessel_ist_vollstaendig(db):
    """`eauto_ladung_gesamt_kwh` = 200 kWh, nicht 150.

    Die Schicht liest den Netz-Anteil über `get_emob_pv_netz_kwh` und leitet ihn
    bei fehlendem Schlüssel aus `Total − PV` ab. Vorher summierte diese Sicht
    `ladung_pv_kwh + ladung_netz_kwh + ladung_extern_kwh` roh und meldete
    150 kWh — 25 % zu wenig für jede evcc-importierte Anlage.
    """
    anlage_id = await _anlage_mit_evcc_ladung(db)

    mw = await _erster_monatswert(db, anlage_id)

    assert mw is not None
    assert mw["eauto_ladung_gesamt_kwh"] == pytest.approx(200.0)
    assert mw["eauto_ladung_pv_kwh"] == pytest.approx(150.0)


# ============================================================================
# Regressions-Schutz — vor dem Umbau ebenfalls grün, also KEIN Fix-Beweis
# ============================================================================


@pytest.mark.asyncio
async def test_eauto_und_wallbox_bleiben_getrennt(db):
    """**Regressions-Schutz**, nicht Beweis: er war vor dem Umbau grün.

    Er schützt eine Entscheidung, die S6 erst getroffen hat: die beiden Quellen
    kommen aus `emob.eauto_summe`/`emob.wallbox_summe`, nicht aus dem
    Heimladungs-Pool. Der Pool wählt EINE Quelle (hier: die Wallbox) — hätte man
    ihn auf beide Felder gelegt, stünden 350 kWh sowohl unter `eauto_*` als auch
    unter `wallbox_*`, und der Server hätte denselben Fluss doppelt.
    """
    anlage = Anlage(anlagenname="Getrennt", leistung_kwp=10.0)
    db.add(anlage)
    await db.flush()
    db.add(Monatsdaten(anlage_id=anlage.id, jahr=2026, monat=6,
                       einspeisung_kwh=400.0, netzbezug_kwh=100.0))
    pv = Investition(anlage_id=anlage.id, typ="pv-module", bezeichnung="Dach",
                     leistung_kwp=10.0, anschaffungsdatum=date(2024, 1, 1))
    eauto = Investition(anlage_id=anlage.id, typ="e-auto", bezeichnung="Kombi",
                        anschaffungsdatum=date(2024, 1, 1), parameter={})
    wallbox = Investition(anlage_id=anlage.id, typ="wallbox", bezeichnung="WB",
                          anschaffungsdatum=date(2024, 1, 1), parameter={})
    db.add_all([pv, eauto, wallbox])
    await db.flush()
    db.add_all([
        InvestitionMonatsdaten(investition_id=pv.id, jahr=2026, monat=6,
                               verbrauch_daten={"pv_erzeugung_kwh": 1000.0}),
        InvestitionMonatsdaten(
            investition_id=eauto.id, jahr=2026, monat=6,
            verbrauch_daten={"km_gefahren": 500.0, "ladung_pv_kwh": 100.0,
                             "ladung_netz_kwh": 50.0},
        ),
        InvestitionMonatsdaten(
            investition_id=wallbox.id, jahr=2026, monat=6,
            verbrauch_daten={"ladung_kwh": 350.0, "ladung_pv_kwh": 300.0,
                             "ladevorgaenge": 12},
        ),
    ])
    await db.commit()

    mw = await _erster_monatswert(db, anlage.id)

    assert mw is not None
    assert mw["eauto_ladung_gesamt_kwh"] == pytest.approx(150.0)
    assert mw["wallbox_ladung_kwh"] == pytest.approx(350.0)
    assert mw["wallbox_ladevorgaenge"] == 12


@pytest.mark.asyncio
async def test_monat_ohne_zaehlerzeile_wird_nicht_geteilt(db):
    """**Regressions-Schutz**, nicht Beweis: er war vor dem Umbau grün.

    Vorher lief die Schleife über die `Monatsdaten`-Zeilen und hatte den Filter
    dadurch implizit. Die Schicht liefert dagegen **jeden** Monat mit einer Spur
    — auch einen, für den es nur eine IMD-Zeile gibt. Ohne gemessene Einspeisung
    wäre die ganze Erzeugung Eigenverbrauch und die Anlage stünde mit 100 %
    Autarkie im Benchmark (P4: eine Lücke wird ausgewiesen, nicht gefüllt).
    """
    anlage = Anlage(anlagenname="Ohne-Zaehler", leistung_kwp=10.0)
    db.add(anlage)
    await db.flush()
    db.add(Monatsdaten(anlage_id=anlage.id, jahr=2026, monat=6,
                       einspeisung_kwh=400.0, netzbezug_kwh=100.0))
    pv = Investition(anlage_id=anlage.id, typ="pv-module", bezeichnung="Dach",
                     leistung_kwp=10.0, anschaffungsdatum=date(2024, 1, 1))
    db.add(pv)
    await db.flush()
    db.add_all([
        InvestitionMonatsdaten(investition_id=pv.id, jahr=2026, monat=6,
                               verbrauch_daten={"pv_erzeugung_kwh": 1000.0}),
        # Mai hat PV, aber keine Zählerzeile.
        InvestitionMonatsdaten(investition_id=pv.id, jahr=2026, monat=5,
                               verbrauch_daten={"pv_erzeugung_kwh": 800.0}),
    ])
    await db.commit()

    data = await prepare_community_data(db, anlage.id)

    assert [(m["jahr"], m["monat"]) for m in data["monatswerte"]] == [(2026, 6)]
