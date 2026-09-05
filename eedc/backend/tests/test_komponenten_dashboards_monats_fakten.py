"""Komponenten-Dashboards an der Monats-Fakten-Schicht (Schritt **S5**).

Zwei benannte Befunde der Drift-Inventur 2026-07-31, beide mit sichtbarer
Anwender-Zahl, dazu zwei Funde derselben Klasse, die erst beim Scharfstellen des
P10-Wächters aufgefallen sind:

- **F-4 · Die BKW-Wirtschaftlichkeit rechnete mit 30 ct fix und bewertete den
  gemessenen Eigenverbrauch.** ``strompreis_cent`` war ein Pflicht-Query mit
  Default 30,0, und **beide** Frontend-Aufrufer übergaben nie einen Preis — der
  Default griff also immer. Bewertet wurde ``eigenverbrauch_kwh``, das beim
  Balkonkraftwerk im Normalfall leer ist (Pflichtfeld ist ``pv_erzeugung_kwh``,
  und nur das können Sensor-/MQTT-Pfad schreiben). Ergebnis: **0 € Ersparnis im
  Komponenten-Hub**, während das Cockpit dieselbe Energie seit ``0faad16b``
  (ADR-002/P9) bewertet.
- **F-7 · Die E-Auto-/Wallbox-Dashboards kannten ``ist_dienstlich`` nicht.** Die
  Datei enthielt keinen einzigen Aufruf, während Cockpit, Aussichten,
  Jahresbericht-PDF und HA-Export das Flag führen. Ein dienstlich geladenes
  Fahrzeug erschien als **private** Ersparnis — in seiner eigenen Karte **und**,
  über den Pool, in der Ersparnis der privaten Fahrzeuge und jeder Wallbox.
- **N-1 · Die historische Performance Ratio** der Langfrist-/Trend-Prognose
  summierte PV roh. Ohne Pro-Modul-IMD fiel sie auf den Default **1,0** zurück.
- **N-14 · Der Prognose-vs-IST-Vergleich** tat dasselbe und stellte die Prognose
  gegen ein IST von 0.

Alle vier gehören zur selben Klasse: **nicht die Formeln driften, sondern die
Aufbereitung.** Die Fixtures sind entsprechend geschnitten — je eine Achse, die
vorher niemand variiert hat (Dienstwagen · BKW ohne gemessenen EV · Anlage ohne
Pro-Modul-IMD), denn ein Test deckt nur ab, was seine Fixture bewegt.
"""

from __future__ import annotations

from datetime import date, datetime

import pytest

from backend.api.routes.aussichten import get_langfrist_prognose, get_trend_analyse
from backend.api.routes.cockpit.prognose import get_prognose_vs_ist
from backend.api.routes.investitionen.dashboards import (
    get_balkonkraftwerk_dashboard,
    get_eauto_dashboard,
    get_wallbox_dashboard,
)
from backend.models import Anlage, Investition, Monatsdaten, Strompreis
from backend.models.investition import InvestitionMonatsdaten
from backend.models.pvgis_prognose import PVGISPrognose

ANSCHAFFUNG = date(2024, 1, 1)


async def _anlage(db, name: str, *, netzbezug_cent: float = 30.0) -> Anlage:
    anlage = Anlage(anlagenname=name, leistung_kwp=10.0)
    db.add(anlage)
    await db.flush()
    db.add(Strompreis(
        anlage_id=anlage.id, gueltig_ab=date(2023, 1, 1),
        netzbezug_arbeitspreis_cent_kwh=netzbezug_cent,
        einspeiseverguetung_cent_kwh=8.0, grundpreis_euro_monat=0.0,
    ))
    return anlage


# ═══════════════════════════════════════════════════════════════════════
# F-4 — die BKW-Wirtschaftlichkeit
# ═══════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_bkw_ohne_gemessenen_eigenverbrauch_wird_bewertet(db):
    """Der F-4-Beweis — gegen die ausgerechnete Zahl, nicht gegen eine zweite Sicht.

    Ein Balkonkraftwerk, das nur sein Pflichtfeld führt (der Normalfall bei
    Sensor- und MQTT-Erfassung)::

        Erzeugung      1.000 kWh   (BKW, `pv_erzeugung_kwh`)
        Einspeisung      400 kWh   (Hauszähler)
        Netzbezug        100 kWh
        Eigenverbrauch     — nicht gemessen

    Hausbilanz: Eigenverbrauch = 1.000 − 400 = **600 kWh**. Das BKW liefert die
    gesamte Erzeugung hinter dem Zähler, sein Anteil ist damit 100 %::

        600 kWh × 0,30 €/kWh = 180,00 €

    Bis 2026-07-31 stand hier **0,00 €**, weil die Sicht den (leeren) gemessenen
    ``eigenverbrauch_kwh`` bewertet hat.
    """
    anlage = await _anlage(db, "BKW ohne EV")
    bkw = Investition(anlage_id=anlage.id, typ="balkonkraftwerk", bezeichnung="Balkon",
                      leistung_kwp=0.8, anschaffungsdatum=ANSCHAFFUNG,
                      anschaffungskosten_gesamt=800.0)
    db.add(bkw)
    await db.flush()
    db.add(Monatsdaten(anlage_id=anlage.id, jahr=2026, monat=6,
                       einspeisung_kwh=400.0, netzbezug_kwh=100.0))
    db.add(InvestitionMonatsdaten(investition_id=bkw.id, jahr=2026, monat=6,
                                  verbrauch_daten={"pv_erzeugung_kwh": 1000.0}))
    await db.commit()

    (karte,) = await get_balkonkraftwerk_dashboard(
        anlage_id=anlage.id, strompreis_cent=None, db=db)
    z = karte.zusammenfassung

    assert z["ersparnis_eigenverbrauch_euro"] == pytest.approx(180.0), (
        "F-4: das BKW liefert die ganze Erzeugung hinter dem Zähler; sein "
        "Eigenverbrauchs-Anteil ist die volle Hausbilanz von 600 kWh. "
        "0,00 € wäre der alte Wert (bewerteter gemessener EV = leer)."
    )
    assert z["gesamt_ersparnis_euro"] == pytest.approx(180.0)
    assert z["gesamt_eigenverbrauch_kwh"] == pytest.approx(600.0)
    # Der rohe Messwert bleibt daneben sichtbar — eine Pflege-Lücke darf nicht
    # dadurch verschwinden, dass die Sicht sie ableiten kann.
    assert z["eigenverbrauch_gemessen_kwh"] == pytest.approx(0.0)
    assert z["monate_nicht_bewertbar"] == 0


@pytest.mark.asyncio
async def test_bkw_anteil_bei_zusaetzlicher_dachanlage(db):
    """Mit Dachanlage daneben trägt das BKW nur SEINEN Anteil.

    Die Zuordnung ist eine Entscheidung, keine Messung (an EINEM Zähler ist
    nicht unterscheidbar, welches Modul die verbrauchte Kilowattstunde geliefert
    hat) — festgelegt in ``core/berechnungen/bkw_finanz.py`` und hier
    festgenagelt, damit sie nicht still zur Vollzuweisung wird::

        PV-Modul      900 kWh
        BKW           100 kWh   → Anteil 10 %
        Einspeisung   400 kWh   → Eigenverbrauch gesamt 600 kWh
        BKW-Anteil     60 kWh × 0,30 €/kWh = 18,00 €
    """
    anlage = await _anlage(db, "BKW neben Dach")
    dach = Investition(anlage_id=anlage.id, typ="pv-module", bezeichnung="Dach",
                       leistung_kwp=9.0, anschaffungsdatum=ANSCHAFFUNG,
                       anschaffungskosten_gesamt=12000.0)
    bkw = Investition(anlage_id=anlage.id, typ="balkonkraftwerk", bezeichnung="Balkon",
                      leistung_kwp=0.8, anschaffungsdatum=ANSCHAFFUNG,
                      anschaffungskosten_gesamt=800.0)
    db.add_all([dach, bkw])
    await db.flush()
    db.add(Monatsdaten(anlage_id=anlage.id, jahr=2026, monat=6,
                       einspeisung_kwh=400.0, netzbezug_kwh=100.0))
    db.add(InvestitionMonatsdaten(investition_id=dach.id, jahr=2026, monat=6,
                                  verbrauch_daten={"pv_erzeugung_kwh": 900.0}))
    db.add(InvestitionMonatsdaten(investition_id=bkw.id, jahr=2026, monat=6,
                                  verbrauch_daten={"pv_erzeugung_kwh": 100.0}))
    await db.commit()

    (karte,) = await get_balkonkraftwerk_dashboard(
        anlage_id=anlage.id, strompreis_cent=None, db=db)

    assert karte.zusammenfassung["gesamt_eigenverbrauch_kwh"] == pytest.approx(60.0)
    assert karte.zusammenfassung["ersparnis_eigenverbrauch_euro"] == pytest.approx(18.0)


@pytest.mark.asyncio
async def test_bkw_ersparnis_nimmt_den_monatstarif_nicht_die_30_cent(db):
    """F-4 (a): der Tarif der Anlage gilt, nicht der Query-Default.

    Isoliert vom Mengen-Teil: dieses BKW führt seinen Eigenverbrauch **gemessen**
    (200 kWh, keine Erzeugung — die Datenlücke aus P9), die bewertete Menge ist
    also in beiden Fassungen dieselbe. Der Unterschied ist allein der Preis::

        vorher   200 kWh × 0,30 (Query-Default)   = 60,00 €
        jetzt    200 kWh × 0,42 (Tarif der Anlage) = 84,00 €
    """
    anlage = await _anlage(db, "BKW Tarif", netzbezug_cent=42.0)
    bkw = Investition(anlage_id=anlage.id, typ="balkonkraftwerk", bezeichnung="Balkon",
                      leistung_kwp=0.8, anschaffungsdatum=ANSCHAFFUNG,
                      anschaffungskosten_gesamt=800.0)
    db.add(bkw)
    await db.flush()
    db.add(Monatsdaten(anlage_id=anlage.id, jahr=2026, monat=6,
                       einspeisung_kwh=0.0, netzbezug_kwh=300.0))
    db.add(InvestitionMonatsdaten(investition_id=bkw.id, jahr=2026, monat=6,
                                  verbrauch_daten={"eigenverbrauch_kwh": 200.0}))
    await db.commit()

    (karte,) = await get_balkonkraftwerk_dashboard(
        anlage_id=anlage.id, strompreis_cent=None, db=db)

    assert karte.zusammenfassung["ersparnis_eigenverbrauch_euro"] == pytest.approx(84.0), (
        "F-4 (a): 60,00 € wäre der Query-Default 30 ct — kein Frontend-Aufrufer "
        "übergibt je einen Preis, also griff er immer."
    )


@pytest.mark.asyncio
async def test_bkw_ohne_zaehlerzeile_ist_nicht_bewertbar_statt_null(db):
    """P4: ohne Hausbilanz ist die Ersparnis unbekannt, nicht 0.

    Ein Mieter-BKW ohne Einspeisezähler hat keine ``Monatsdaten``-Zeile. Die
    ganze Erzeugung als Eigenverbrauch auszuweisen wäre die Behauptung, die #304
    im Cockpit korrigiert hat — also wird sie nicht erhoben, und die Sicht sagt
    das, statt still 0 € zu zeigen.
    """
    anlage = await _anlage(db, "BKW ohne Zähler")
    bkw = Investition(anlage_id=anlage.id, typ="balkonkraftwerk", bezeichnung="Balkon",
                      leistung_kwp=0.8, anschaffungsdatum=ANSCHAFFUNG,
                      anschaffungskosten_gesamt=800.0)
    db.add(bkw)
    await db.flush()
    db.add(InvestitionMonatsdaten(investition_id=bkw.id, jahr=2026, monat=6,
                                  verbrauch_daten={"pv_erzeugung_kwh": 1000.0}))
    await db.commit()

    (karte,) = await get_balkonkraftwerk_dashboard(
        anlage_id=anlage.id, strompreis_cent=None, db=db)
    z = karte.zusammenfassung

    assert z["monate_nicht_bewertbar"] == 1
    assert z["ersparnis_eigenverbrauch_euro"] == pytest.approx(0.0)
    assert z["gesamt_erzeugung_kwh"] == pytest.approx(1000.0), (
        "die Erzeugung ist gemessen und bleibt stehen — nur ihre Bewertung fehlt"
    )


# ═══════════════════════════════════════════════════════════════════════
# F-7 — der Dienstwagen
# ═══════════════════════════════════════════════════════════════════════


async def _anlage_mit_zwei_fahrzeugen(db) -> Anlage:
    """Ein privates und ein dienstliches E-Auto, gleiche Ladung, gleiche km.

    Gleich gebaut, damit der einzige Unterschied das Flag ist — sonst könnte
    eine abweichende Zahl auch von der Fixture kommen.
    """
    anlage = await _anlage(db, "Zwei Fahrzeuge")
    privat = Investition(
        anlage_id=anlage.id, typ="e-auto", bezeichnung="Privat",
        anschaffungsdatum=ANSCHAFFUNG, anschaffungskosten_gesamt=30000.0,
        parameter={"vergleich_verbrauch_l_100km": 7.5, "benzinpreis_euro": 1.80},
    )
    dienst = Investition(
        anlage_id=anlage.id, typ="e-auto", bezeichnung="Dienstwagen",
        anschaffungsdatum=ANSCHAFFUNG, anschaffungskosten_gesamt=30000.0,
        parameter={"vergleich_verbrauch_l_100km": 7.5, "benzinpreis_euro": 1.80,
                   "ist_dienstlich": True},
    )
    db.add_all([privat, dienst])
    await db.flush()
    for inv in (privat, dienst):
        db.add(InvestitionMonatsdaten(
            investition_id=inv.id, jahr=2026, monat=6,
            verbrauch_daten={
                "km_gefahren": 1000.0, "verbrauch_kwh": 180.0,
                "ladung_pv_kwh": 120.0, "ladung_netz_kwh": 60.0,
            },
        ))
    db.add(Monatsdaten(anlage_id=anlage.id, jahr=2026, monat=6,
                       einspeisung_kwh=400.0, netzbezug_kwh=100.0))
    await db.commit()
    return anlage


@pytest.mark.asyncio
async def test_dienstwagen_traegt_keine_private_ersparnis(db):
    """Der F-7-Beweis: gleiche Mengen, nur das Flag entscheidet über die Euro.

    Die Karte bleibt — das Fahrzeug ist registriert und seine km und kWh sind
    gemessen. Was fällt, ist die **Bewertung**: dienstlich gefahrene Kilometer
    sind keine private Ersparnis ([[feedback_dienstwagen_alle_checks]]).
    """
    anlage = await _anlage_mit_zwei_fahrzeugen(db)

    karten = {k.investition.bezeichnung: k.zusammenfassung
              for k in await get_eauto_dashboard(anlage_id=anlage.id, strompreis_cent=None, db=db)}
    assert set(karten) == {"Privat", "Dienstwagen"}, (
        "der Dienstwagen wird nicht versteckt — das wäre ein Lösch-Feature"
    )

    privat, dienst = karten["Privat"], karten["Dienstwagen"]

    # Die gemessenen Größen sind bei beiden identisch …
    assert dienst["gesamt_km"] == privat["gesamt_km"] == 1000
    assert dienst["ladung_pv_kwh"] == privat["ladung_pv_kwh"] == pytest.approx(120.0)

    # … die Bewertung nicht.
    assert privat["ersparnis_vs_benzin_euro"] > 0
    assert dienst["dienstlich"] is True
    assert privat["dienstlich"] is False
    for feld in (
        "ersparnis_vs_benzin_euro", "gesamt_ersparnis_euro",
        "wallbox_ersparnis_euro", "co2_ersparnis_kg",
    ):
        assert dienst[feld] == pytest.approx(0.0), (
            f"F-7: `{feld}` des Dienstwagens ist keine private Ersparnis"
        )


@pytest.mark.asyncio
async def test_dienstwagen_zieht_die_private_ersparnis_nicht_hoch(db):
    """Der Pool ist eine private Größe — sonst erbt das Privatauto fremde Ladung.

    Liegt die Heimladung kanonisch auf der Wallbox (evcc-Import, #262), verteilt
    ``attribute_emob_pool_by_km`` sie km-anteilig auf die E-Autos. Steht ein
    Dienstwagen mit im Topf, bekommt das private Fahrzeug einen Teil **seiner**
    Ladung zugeschrieben und seine Ersparnis steigt::

        Wallbox-Pool      PV 400 · Netz 200 kWh
        Privat            1.000 km
        Dienstwagen       1.000 km

    Mit Dienstwagen im Topf: 50 % der Poolmenge fürs Privatauto. Ohne ihn: 100 %
    — aber der Topf enthält dann auch nur noch die private Wallbox.
    """
    anlage = await _anlage(db, "Pool mit Dienstwagen")
    privat = Investition(anlage_id=anlage.id, typ="e-auto", bezeichnung="Privat",
                         anschaffungsdatum=ANSCHAFFUNG, anschaffungskosten_gesamt=30000.0,
                         parameter={"vergleich_verbrauch_l_100km": 7.5})
    dienst = Investition(anlage_id=anlage.id, typ="e-auto", bezeichnung="Dienstwagen",
                         anschaffungsdatum=ANSCHAFFUNG, anschaffungskosten_gesamt=30000.0,
                         parameter={"ist_dienstlich": True})
    wb = Investition(anlage_id=anlage.id, typ="wallbox", bezeichnung="Wallbox",
                     anschaffungsdatum=ANSCHAFFUNG, anschaffungskosten_gesamt=1500.0)
    db.add_all([privat, dienst, wb])
    await db.flush()
    # Die Fahrzeuge führen nur km — die Ladung liegt auf der Wallbox (evcc).
    for inv in (privat, dienst):
        db.add(InvestitionMonatsdaten(investition_id=inv.id, jahr=2026, monat=6,
                                      verbrauch_daten={"km_gefahren": 1000.0}))
    db.add(InvestitionMonatsdaten(
        investition_id=wb.id, jahr=2026, monat=6,
        verbrauch_daten={"ladung_pv_kwh": 400.0, "ladung_netz_kwh": 200.0},
    ))
    db.add(Monatsdaten(anlage_id=anlage.id, jahr=2026, monat=6,
                       einspeisung_kwh=400.0, netzbezug_kwh=100.0))
    await db.commit()

    karten = {k.investition.bezeichnung: k.zusammenfassung
              for k in await get_eauto_dashboard(anlage_id=anlage.id, strompreis_cent=None, db=db)}

    # Der Dienstwagen schöpft nicht aus dem privaten Pool …
    assert karten["Dienstwagen"]["ladung_pv_kwh"] == pytest.approx(0.0)
    # … und das Privatauto bekommt den ganzen Topf, weil es das einzige private
    # Fahrzeug ist. Mit dem Dienstwagen im Nenner wären es 200 kWh gewesen.
    assert karten["Privat"]["ladung_pv_kwh"] == pytest.approx(400.0), (
        "F-7: der km-Nenner der Pool-Attribution ist privat"
    )


@pytest.mark.asyncio
async def test_wallbox_dashboard_zaehlt_dienstliche_ladung_nicht_mit(db):
    """F-7, zweite Hälfte: die Wallbox-Ersparnis ist eine anlagenweite Summe.

    Sie wird auf **jeder** Wallbox-Karte gezeigt — ein ungefiltert
    mitgerechneter Dienstwagen erschien damit doppelt als private Ersparnis.
    Erwartet ist nur noch die Ladung des privaten Fahrzeugs (120 PV + 60 Netz).
    """
    anlage = await _anlage_mit_zwei_fahrzeugen(db)
    wb = Investition(anlage_id=anlage.id, typ="wallbox", bezeichnung="Wallbox",
                     anschaffungsdatum=ANSCHAFFUNG, anschaffungskosten_gesamt=1500.0)
    db.add(wb)
    await db.commit()

    (karte,) = await get_wallbox_dashboard(anlage_id=anlage.id, strompreis_cent=None, db=db)
    z = karte.zusammenfassung

    assert z["gesamt_heim_ladung_kwh"] == pytest.approx(180.0), (
        "360 kWh wären beide Fahrzeuge — der Dienstwagen gehört nicht dazu"
    )
    assert z["ladung_pv_kwh"] == pytest.approx(120.0)
    assert z["ladung_netz_kwh"] == pytest.approx(60.0)
    assert z["dienstlich"] is False


# ═══════════════════════════════════════════════════════════════════════
# N-1 / N-14 — die Anlagen-Ebene, die der Wächter sonst gemeldet hätte
# ═══════════════════════════════════════════════════════════════════════


async def _anlage_nur_mit_aggregat_und_prognose(db) -> Anlage:
    """PV-Anlage ohne Pro-Modul-IMD, mit aktiver PVGIS-Prognose.

    Die Erzeugung steht **nur** in ``Monatsdaten.pv_erzeugung_kwh`` — der
    dokumentierte Fall bei manueller Pflege und bei Importen mit einem einzigen
    Gesamt-PV-Sensor. Genau die Konstellation, an der F-5 hing und an der die
    beiden Prognose-Pfade bis S5 vorbeiliefen.

    PVGIS nennt für jeden Monat 500 kWh; gemessen sind 250 kWh — die historische
    Performance Ratio ist damit **0,5**, nicht der Default 1,0.
    """
    anlage = await _anlage(db, "NurAggregat mit Prognose")
    anlage.latitude, anlage.longitude = 52.0, 10.0
    db.add(Investition(anlage_id=anlage.id, typ="pv-module", bezeichnung="Dach",
                       leistung_kwp=10.0, anschaffungsdatum=ANSCHAFFUNG,
                       anschaffungskosten_gesamt=12000.0))
    db.add(PVGISPrognose(
        anlage_id=anlage.id, abgerufen_am=datetime(2025, 12, 1),
        latitude=52.0, longitude=10.0, neigung_grad=30.0, ausrichtung_grad=0.0,
        system_losses=14.0, jahresertrag_kwh=6000.0,
        spezifischer_ertrag_kwh_kwp=600.0, gesamt_leistung_kwp=10.0,
        monatswerte=[{"monat": m, "e_m": 500.0, "h_m": 0.0, "sd_m": 0.0}
                     for m in range(1, 13)],
        ist_aktiv=True,
    ))
    for monat in range(1, 13):
        db.add(Monatsdaten(anlage_id=anlage.id, jahr=2025, monat=monat,
                           einspeisung_kwh=100.0, netzbezug_kwh=50.0,
                           pv_erzeugung_kwh=250.0))
    await db.commit()
    return anlage


@pytest.mark.asyncio
async def test_langfrist_prognose_findet_die_historische_performance_ratio(db):
    """N-1: ohne Pro-Modul-IMD fiel die PR auf den Default 1,0 zurück.

    Damit rechnete die Langfrist-Prognose ungebremst mit dem PVGIS-SOLL statt
    mit der gemessenen Anlagen-Güte — bei einer Anlage, die real die Hälfte
    liefert, ist das die doppelte Jahresprognose.
    """
    anlage = await _anlage_nur_mit_aggregat_und_prognose(db)

    antwort = await get_langfrist_prognose(anlage_id=anlage.id, monate=12, db=db)

    assert antwort.trend_analyse.durchschnittliche_performance_ratio == pytest.approx(0.5), (
        "N-1: 1,0 ist der Default fuer 'keine historischen Daten gefunden' — "
        "die Daten sind da, sie standen nur im Anlagen-Aggregat"
    )
    assert antwort.trend_analyse.datenbasis_monate == 12
    assert antwort.jahresprognose_kwh == pytest.approx(3000.0), (
        "12 × 500 kWh SOLL × PR 0,5 — mit dem Default-PR wären es 6.000 kWh"
    )


@pytest.mark.asyncio
async def test_trend_analyse_sieht_die_jahreserträge_ohne_pro_modul_imd(db):
    """N-1, zweiter Pfad: der Jahresvergleich stand auf 0 kWh."""
    anlage = await _anlage_nur_mit_aggregat_und_prognose(db)

    antwort = await get_trend_analyse(anlage_id=anlage.id, jahre=3, db=db)

    jahr_2025 = [j for j in antwort.jahres_vergleich if j.jahr == 2025]
    assert jahr_2025, "2025 fehlt im Jahresvergleich"
    assert jahr_2025[0].gesamt_kwh == pytest.approx(3000.0), (
        "N-1: 0 kWh war der alte Wert — die rohe IMD-Summe fand nichts"
    )


@pytest.mark.asyncio
async def test_prognose_vs_ist_zeigt_das_ist_ohne_pro_modul_imd(db):
    """N-14: der Vergleich stellte die Prognose gegen ein IST von 0.

    Ergebnis war eine ausgewiesene Abweichung von −100 % für jeden Monat, bei
    einer Anlage, die tatsächlich 250 von 500 kWh geliefert hat.
    """
    anlage = await _anlage_nur_mit_aggregat_und_prognose(db)

    antwort = await get_prognose_vs_ist(anlage_id=anlage.id, jahr=2025, db=db)

    assert antwort.ist_jahresertrag_kwh == pytest.approx(3000.0), (
        "N-14: 0 kWh war der alte Wert"
    )
    assert antwort.performance_ratio == pytest.approx(0.5)
    juni = [m for m in antwort.monatswerte if m.monat == 6][0]
    assert juni.ist_kwh == pytest.approx(250.0)
    assert juni.abweichung_prozent == pytest.approx(-50.0), (
        "−100 % war der alte Wert — er sah aus wie ein Totalausfall der Anlage"
    )
