"""N-200 — der HA-Export lädt den Tarif über den SoT statt über eine Handquery.

**Der Befund.** `api/routes/ha_export.py` baute an zwei Stellen selbst::

    select(Strompreis).where(anlage_id == …).order_by(gueltig_ab.desc()).limit(1)

Diese Form verliert **zwei** Filter, die `lade_tarife_fuer_anlage` mitbringt:

* ``gueltig_bis`` — ein **ausgelaufener** Tarif gilt weiter als „aktuellster";
* ``verwendung``  — ist der zuletzt angelegte Tarif ein **WP- oder Wallbox-
  Spezialtarif**, wird er als **allgemeiner** Netzbezugspreis gelesen. Der
  §14a-WP-Tarif ist typischerweise der günstigere und der zuletzt gepflegte —
  die Kombination ist damit keine Konstruktion, sondern der Normalfall bei
  jedem, der einen Wärmepumpen-Tarif hat.

Dazu fällt ein ``gueltig_ab`` in der **Zukunft** nicht mehr auf heute durch.

**Warum es auffällt und warum nicht.** Der Wert verlässt eedc: er trägt den
Erklärungstext von ``eigenverbrauch_ersparnis_euro`` und
``einspeise_erloes_euro`` und ist der **Fallback** der WP-/Wallbox-Auflösung.
Die Monats-Summen daneben lösen längst je Monat auf (ADR-002/P8) — die
Historie war also richtig, während der Text daneben einen anderen Preis nannte.

**Was diese Datei NICHT prüft:** die P8-Auflösung selbst (dafür
``test_ha_export_wp_spezialtarif.py`` und der Wächter
``test_wurzelmuster_konformitaet.py::test_p8_*``). Hier geht es allein um die
Frage, **welcher** Tarif „der aktuelle" ist.
"""

from __future__ import annotations

from datetime import date

import pytest

from backend.api.routes.ha_export import calculate_anlage_sensors, get_all_sensors
from backend.models import Anlage, Investition, InvestitionMonatsdaten, Monatsdaten, Strompreis

# ⚠ **Keine Probe liest hier die Uhr** (N-167, Wächter
# `test_konformitaet_echte_uhr_in_tests.py`). Die Gültigkeitsfenster stehen
# deshalb als FESTE Daten weit genug von jedem Laufzeitpunkt entfernt:
# `ABGELAUFEN` endet 2021, `KUENFTIG` beginnt 2099 — beides gilt in jeder
# Zeitzone und zu jeder Stunde, in der die Suite läuft.
OFFEN_SEIT = date(2020, 1, 1)      # gültig an jedem denkbaren Testtag
ABGELAUFEN_AB = date(2021, 1, 1)   # jünger als OFFEN_SEIT — die alte Handquery
ABGELAUFEN_BIS = date(2021, 12, 31)  # … hätte diesen genommen
KUENFTIG_AB = date(2099, 1, 1)


async def _anlage_mit_tarifen(db, tarife: list[Strompreis]) -> Anlage:
    """Eine Anlage mit einem gemessenen Monat — sonst gibt es keine Finanz-Zeile."""
    anlage = Anlage(anlagenname="N-200", leistung_kwp=10.0)
    db.add(anlage)
    await db.flush()

    pv = Investition(
        anlage_id=anlage.id, typ="pv-module", bezeichnung="Süd",
        anschaffungsdatum=date(2020, 1, 1), aktiv=True, leistung_kwp=10.0,
        anschaffungskosten_gesamt=15000,
    )
    db.add(pv)
    await db.flush()
    db.add(InvestitionMonatsdaten(
        investition_id=pv.id, jahr=2025, monat=6,
        verbrauch_daten={"pv_erzeugung_kwh": 1000},
    ))
    db.add(Monatsdaten(
        anlage_id=anlage.id, jahr=2025, monat=6,
        einspeisung_kwh=600, netzbezug_kwh=200,
    ))
    for t in tarife:
        t.anlage_id = anlage.id
        db.add(t)
    await db.commit()
    return anlage


def _tarif(**kw) -> Strompreis:
    kw.setdefault("verwendung", "allgemein")
    kw.setdefault("einspeiseverguetung_cent_kwh", 8.0)
    return Strompreis(**kw)


async def _genannter_bezugspreis(db, anlage: Anlage) -> str:
    """Der Preis, den der Erklärungstext des Eigenverbrauchs-Sensors nennt.

    Bewusst der TEXT und nicht der Betrag: der Betrag kommt aus den je Monat
    aufgelösten Finanz-Zeilen (P8) und ist von diesem Fund gar nicht berührt.
    Genau darin lag die Tücke — die Zahl stimmte, der Satz daneben nicht.
    """
    svs = await calculate_anlage_sensors(db, anlage)
    treffer = [s for s in svs if s.definition.key == "eigenverbrauch_ersparnis_euro"]
    assert treffer, "Sensor fehlt — die Probe zeigt aufs falsche Objekt"
    return treffer[0].berechnung or ""


# ── Der verlorene `verwendung`-Filter ────────────────────────────────────

async def test_wp_spezialtarif_wird_nicht_zum_allgemeinen_preis(db):
    """Der zuletzt gepflegte Tarif ist ein WP-Tarif — er darf nicht gelten.

    Alte Handquery: `order_by(gueltig_ab.desc()).limit(1)` liefert den
    WP-Tarif (2025 neuer als 2024) und damit **20 ct** als allgemeinen
    Netzbezugspreis. Richtig sind **30 ct**.
    """
    anlage = await _anlage_mit_tarifen(db, [
        _tarif(gueltig_ab=date(2024, 1, 1), netzbezug_arbeitspreis_cent_kwh=30.0),
        _tarif(gueltig_ab=date(2025, 1, 1), netzbezug_arbeitspreis_cent_kwh=20.0,
               verwendung="waermepumpe"),
    ])
    text = await _genannter_bezugspreis(db, anlage)
    assert "30.00 ct/kWh" in text, text
    assert "20.00 ct/kWh" not in text, text


async def test_wallbox_spezialtarif_ebenso(db):
    """Dieselbe Klasse auf der zweiten Spezial-Verwendung."""
    anlage = await _anlage_mit_tarifen(db, [
        _tarif(gueltig_ab=date(2024, 1, 1), netzbezug_arbeitspreis_cent_kwh=30.0),
        _tarif(gueltig_ab=date(2025, 1, 1), netzbezug_arbeitspreis_cent_kwh=22.0,
               verwendung="wallbox"),
    ])
    assert "30.00 ct/kWh" in await _genannter_bezugspreis(db, anlage)


# ── Der verlorene `gueltig_bis`-Filter ───────────────────────────────────

async def test_ausgelaufener_tarif_gilt_nicht_weiter(db):
    """Der jüngste Tarif ist abgelaufen — der offene davor gilt.

    Alte Handquery kannte `gueltig_bis` nicht und nahm die **99 ct**.
    """
    anlage = await _anlage_mit_tarifen(db, [
        _tarif(gueltig_ab=OFFEN_SEIT, netzbezug_arbeitspreis_cent_kwh=30.0),
        _tarif(gueltig_ab=ABGELAUFEN_AB, gueltig_bis=ABGELAUFEN_BIS,
               netzbezug_arbeitspreis_cent_kwh=99.0),
    ])
    text = await _genannter_bezugspreis(db, anlage)
    assert "30.00 ct/kWh" in text, text
    assert "99.00 ct/kWh" not in text, text


async def test_zukuenftiger_tarif_gilt_noch_nicht(db):
    """Eine angekündigte Preiserhöhung darf die Gegenwart nicht umschreiben."""
    anlage = await _anlage_mit_tarifen(db, [
        _tarif(gueltig_ab=OFFEN_SEIT, netzbezug_arbeitspreis_cent_kwh=30.0),
        _tarif(gueltig_ab=KUENFTIG_AB, netzbezug_arbeitspreis_cent_kwh=50.0),
    ])
    text = await _genannter_bezugspreis(db, anlage)
    assert "30.00 ct/kWh" in text, text
    assert "50.00 ct/kWh" not in text, text


# ── Gegenrichtung: der normale Fall bleibt normal ────────────────────────

async def test_juengster_gueltiger_allgemeintarif_gewinnt_weiter(db):
    """Ohne diese Hälfte liefe ein Fix „nimm immer den ältesten" grün durch."""
    anlage = await _anlage_mit_tarifen(db, [
        _tarif(gueltig_ab=date(2024, 1, 1), gueltig_bis=date(2024, 12, 31),
               netzbezug_arbeitspreis_cent_kwh=25.0),
        _tarif(gueltig_ab=date(2025, 1, 1), netzbezug_arbeitspreis_cent_kwh=32.0),
    ])
    text = await _genannter_bezugspreis(db, anlage)
    assert "32.00 ct/kWh" in text, text


# ── Die zweite Fundstelle: die Route, die alle Sensoren ausliefert ───────

async def _eauto_ersparnis_ueber_die_route(db) -> float:
    """Baut die Lage, in der der Tarif aus `get_all_sensors` als ZAHL ankommt.

    ⚠ **Das war der zweite Anlauf, und der Grund gehört hierher.** Die erste
    Fassung dieser Probe prüfte den WP-Ersparnis-Sensor — und blieb unter dem
    Sprengsatz **grün**. `calculate_investition_sensors` lädt den WP-Tarif
    nämlich selbst (`_wp_tarife`, Z. 1524) und braucht den durchgereichten
    Strompreis nur als *Fallback*, der bei gepflegtem Allgemeintarif nie
    greift. Ein Prüfer, der das Objekt nicht erreicht, ist kein Prüfer.

    Erreichbar ist der durchgereichte Preis über den **E-Auto**-Pfad: dort geht
    er als `fallback_bezug` in `monats_strompreis_lookup` und als
    `wallbox_strompreis_cent` in die Ersparnis-Formel. Damit der Fallback
    wirklich greift, liegt der gemessene Monat **vor** jedem gepflegten Tarif.
    """
    anlage = Anlage(anlagenname="N-200 Route", leistung_kwp=10.0)
    db.add(anlage)
    await db.flush()

    eauto = Investition(
        anlage_id=anlage.id, typ="e-auto", bezeichnung="ID.3",
        # VOR dem gemessenen Monat (06/2019) — sonst filtert ihn der
        # Anschaffungsdatum-Filter heraus und der Sensor entsteht gar nicht.
        anschaffungsdatum=date(2018, 1, 1), aktiv=True,
        anschaffungskosten_gesamt=30000,
        parameter={"verbrauch_kwh_100km": 18.0, "vergleichsverbrauch_l_100km": 7.0},
    )
    db.add(eauto)
    await db.flush()
    db.add(InvestitionMonatsdaten(
        investition_id=eauto.id, jahr=2019, monat=6,
        verbrauch_daten={"km_gefahren": 1000, "ladung_netz_kwh": 180,
                         "ladung_pv_kwh": 0},
    ))
    db.add(Monatsdaten(
        anlage_id=anlage.id, jahr=2019, monat=6,
        einspeisung_kwh=0, netzbezug_kwh=180, kraftstoffpreis_euro=1.80,
    ))
    # Beide Tarife beginnen NACH dem gemessenen Monat (06/2019) ⇒ die
    # Monatsauflösung findet nichts und nimmt den Fallback. Der WP-Tarif ist
    # der jüngste:
    # die alte Handquery hätte damit 20 ct als allgemeinen Preis gelesen.
    db.add(_tarif(anlage_id=anlage.id, gueltig_ab=OFFEN_SEIT,
                  netzbezug_arbeitspreis_cent_kwh=30.0))
    db.add(_tarif(anlage_id=anlage.id, gueltig_ab=date(2020, 2, 1),
                  netzbezug_arbeitspreis_cent_kwh=20.0, verwendung="waermepumpe"))
    await db.commit()

    antwort = await get_all_sensors(db)
    werte = [
        s for e in antwort.investitionen for s in e.sensors
        if s.key == "e_auto_ersparnis_vs_benzin_euro"
    ]
    assert werte, "E-Auto-Sensor fehlt — die Probe zeigt aufs falsche Objekt"
    return werte[0].value


async def test_zweite_fundstelle_route_get_all_sensors(db):
    """`get_all_sensors` hatte dieselbe Handquery — eigener Beleg, eigener Ort.

    **Beide Zweige gemessen**, nicht hergeleitet: mit dem SoT liefert der Sensor
    **81,00 €**, mit der alten Handquery **99,00 €**. Die Differenz ist exakt
    180 kWh × (30 − 20) ct = **18,00 €** — der Betrag, um den die Ersparnis zu
    hoch ausfiel, weil der WP-Spezialtarif als allgemeiner Preis gelesen wurde.

    ⚠ Die Probe prüft den **Preis, der ankommt** — nicht die Benzin-Vergleichs-
    rechnung, die den absoluten Wert bestimmt. Ändert sich die (etwa ein anderer
    Vergleichsverbrauch-Default), wandern beide Zahlen gemeinsam; dann ist die
    Erwartung nachzumessen, nicht der Fund wieder offen.
    """
    wert = await _eauto_ersparnis_ueber_die_route(db)
    assert wert == pytest.approx(81.00, abs=0.05), wert
    assert wert != pytest.approx(99.00, abs=0.05), (
        "Der Tarif kommt mit 20 ct statt 30 ct an — die Handquery ist zurück"
    )
