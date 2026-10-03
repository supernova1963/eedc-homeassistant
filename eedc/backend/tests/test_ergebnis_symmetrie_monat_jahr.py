"""W3 — eine Ergebnis-Leiter, alle Sichten: Monat ↔ Jahr ↔ Übersicht ↔ PDF ↔ HA-Export ↔ Monatsreihe.

Paket „Ergebnisgrößen Monat/Jahr in den Layer" (03.10.2026, Vorlage B6/W3). Ein Symmetrie-Test deckt nur die Achsen
ab, die seine Fixture variiert ([[feedback_aggregator_symmetrie]], [[feedback_symmetrie_fixture_muss_teilweise_decken]]).
Diese Fixture variiert deshalb ALLE Achsen der Leiter auf einmal, über zwölf Monate:

* **Regelbesteuerung 19 %** — die USt-Achse (die vier GM-Kopien tragen sie nicht, §10 der Vorlage).
* **EV-Anteil je Monat verschieden** (Winter hoch, Sommer niedrig) — sonst wäre Jahressatz = Monatssatz.
* **Klemm-Monat** (Januar: Einspeisung > PV) — Perioden-EV ≠ Σ Monats-EV (G1-EV-Konvention).
* **Balkonkraftwerk** mit einem **Datenlücken-Monat** (Mai: nur gemessener Eigenverbrauch, keine Erzeugung) — P9.
* **Sonstige Position** (April: Ausgabe 120 €, Juni: Ertrag 150 €).
* **Erzeuger mit eigenem Vergütungssatz** (jeden Monat ein gepflegter Erlös).
* **E-Auto ab August** mit 600 €/J Betriebskosten — N-602 (März trägt KEINE E-Auto-Betriebskosten).
* **Deaktivierte Wallbox** (``aktiv=False``) mit 1 000 € / 600 €/J — G1/E9: sie geht in keinen USt-Satz ein.

Erwartungen (a)–(e) der Vorlage: C1 deckte den Monat (a-Monat, d, e-Monat), C2 das Jahr (b), C3 die übrigen Sichten
(a, c, e). (f) — T-Konto-Hauptbuch == ``ergebnis_euro`` — ist Frontend-Code und steht als Vitest in
``frontend/src/components/finanzen/TKonto.w3f.test.ts`` — über alle zwölf Monate und das Jahr dieser Anlage
(``frontend/src/test/w3-antworten.fixture.json``, über die echten Routen erzeugt; nach einer Änderung an der Fixture hier
neu erzeugen), für das T-Konto-Hauptbuch UND die Komponenten-Tabelle (A2, 03.10.2026).

Schwesterdateien: test_ergebnis_leiter.py, test_ergebnis_monat_probe.py, test_ergebnis_leiter_nur_im_layer.py (W1),
test_netto_ertrag_vier_wege_symmetrie.py (Vorgänger mit EINER Achse je Fixture).
"""

from __future__ import annotations

from datetime import date

import pytest

from backend.api.routes.aktueller_monat import get_aktueller_monat
from backend.core.berechnungen.ust_eigenverbrauch import AFA_JAHRE
from backend.models import Anlage, Investition, Monatsdaten, Strompreis
from backend.models.investition import InvestitionMonatsdaten
from backend.services.monats_fakten import lade_monats_fakten
from backend.services.ust_satz import ust_eigenverbrauch_zeitraum

JAHR = 2025
#: (PV, Einspeisung, Netzbezug) je Monat — EV-Anteil im Winter hoch, im Sommer niedrig; Januar klemmt (Einsp. > PV).
MENGEN = {
    1: (100.0, 230.0, 600.0),
    2: (300.0, 90.0, 500.0),
    3: (600.0, 250.0, 400.0),
    4: (900.0, 500.0, 300.0),
    5: (1100.0, 750.0, 200.0),
    6: (1200.0, 880.0, 150.0),
    7: (1250.0, 930.0, 150.0),
    8: (1100.0, 780.0, 200.0),
    9: (800.0, 480.0, 250.0),
    10: (500.0, 220.0, 350.0),
    11: (250.0, 70.0, 500.0),
    12: (120.0, 20.0, 600.0),
}
BKW_ERZEUGUNG = 50.0          # je Monat, außer im Lücken-Monat
BKW_LUECKE_MONAT = 5          # nur gemessener Eigenverbrauch
BKW_LUECKE_EV = 40.0
ERZEUGER_ERLOES = 3.0         # € je Monat, eigener Satz
SONSTIGE = {4: ("ausgabe", 120.0), 6: ("ertrag", 150.0)}


async def anlage_alle_achsen(db) -> int:
    anlage = Anlage(anlagenname="W3-Alle-Achsen", leistung_kwp=10.0,
                    steuerliche_behandlung="regelbesteuerung", ust_satz_prozent=19.0)
    db.add(anlage)
    await db.flush()
    db.add(Strompreis(anlage_id=anlage.id, gueltig_ab=date(2024, 1, 1), netzbezug_arbeitspreis_cent_kwh=30.0,
                      einspeiseverguetung_cent_kwh=8.0, grundpreis_euro_monat=10.0))
    pv = Investition(anlage_id=anlage.id, typ="pv-module", bezeichnung="Dach", leistung_kwp=10.0,
                     anschaffungsdatum=date(2024, 1, 1), anschaffungskosten_gesamt=12000.0, betriebskosten_jahr=120.0)
    bkw = Investition(anlage_id=anlage.id, typ="balkonkraftwerk", bezeichnung="Balkon", leistung_kwp=0.8,
                      anschaffungsdatum=date(2024, 1, 1), anschaffungskosten_gesamt=600.0)
    erzeuger = Investition(anlage_id=anlage.id, typ="sonstiges", bezeichnung="Mini-BHKW",
                           anschaffungsdatum=date(2024, 1, 1), anschaffungskosten_gesamt=0.0,
                           parameter={"kategorie": "erzeuger"})
    auto = Investition(anlage_id=anlage.id, typ="e-auto", bezeichnung="Auto", parameter={},
                       anschaffungsdatum=date(JAHR, 8, 1), anschaffungskosten_gesamt=30000.0,
                       anschaffungskosten_alternativ=25000.0, betriebskosten_jahr=600.0)
    wallbox_aus = Investition(anlage_id=anlage.id, typ="wallbox", bezeichnung="Alte Wallbox", aktiv=False,
                              anschaffungsdatum=date(2024, 1, 1), anschaffungskosten_gesamt=1000.0,
                              betriebskosten_jahr=600.0)
    db.add_all([pv, bkw, erzeuger, auto, wallbox_aus])
    await db.flush()
    for m, (pv_kwh, einsp, netz) in MENGEN.items():
        sonst = SONSTIGE.get(m)
        db.add(Monatsdaten(
            anlage_id=anlage.id, jahr=JAHR, monat=m, einspeisung_kwh=einsp, netzbezug_kwh=netz,
            sonstige_positionen=(
                [{"bezeichnung": "Position", "betrag": sonst[1], "typ": sonst[0]}] if sonst else None
            ),
        ))
        db.add(InvestitionMonatsdaten(investition_id=pv.id, jahr=JAHR, monat=m,
                                      verbrauch_daten={"pv_erzeugung_kwh": pv_kwh}))
        db.add(InvestitionMonatsdaten(
            investition_id=bkw.id, jahr=JAHR, monat=m,
            verbrauch_daten=({"eigenverbrauch_kwh": BKW_LUECKE_EV} if m == BKW_LUECKE_MONAT
                             else {"pv_erzeugung_kwh": BKW_ERZEUGUNG}),
        ))
        db.add(InvestitionMonatsdaten(investition_id=erzeuger.id, jahr=JAHR, monat=m,
                                      verbrauch_daten={"einspeise_erloes_euro": ERZEUGER_ERLOES}))
    await db.commit()
    return anlage.id


async def _monate(db, anlage_id):
    return [await get_aktueller_monat(anlage_id=anlage_id, jahr=JAHR, monat=m, db=db) for m in range(1, 13)]


@pytest.mark.asyncio
async def test_w3_monat_traegt_alle_posten_der_leiter(db):
    anlage_id = await anlage_alle_achsen(db)
    monate = await _monate(db, anlage_id)
    for d in monate:
        posten = (d.einspeise_erloes_euro + d.ev_ersparnis_euro + (d.bkw_ersparnis_euro or 0)
                  + (d.erzeuger_erloes_euro or 0) + d.sonstige_netto_euro - (d.ust_eigenverbrauch_euro or 0))
        assert d.netto_ertrag_euro == pytest.approx(posten, abs=0.01), f"Monat {d.monat}"
        if d.eigenverbrauch_kwh > 0:
            assert d.ust_eigenverbrauch_euro > 0, f"Monat {d.monat}: USt-Anteil fehlt"
        else:  # Januar klemmt: kein Eigenverbrauch, kein USt-Anteil — aber 0, nicht „fehlt"
            assert d.ust_eigenverbrauch_euro == 0.0
        assert d.erzeuger_erloes_euro == pytest.approx(ERZEUGER_ERLOES)
    mai = monate[BKW_LUECKE_MONAT - 1]
    assert mai.bkw_ersparnis_euro == pytest.approx(BKW_LUECKE_EV * 0.30), "P9: Rest-EV der Datenlücke × Preis"
    assert all(d.bkw_ersparnis_euro is None for d in monate if d.monat != BKW_LUECKE_MONAT)
    assert monate[3].sonstige_netto_euro == pytest.approx(-120.0) and monate[5].sonstige_netto_euro == pytest.approx(150.0)


@pytest.mark.asyncio
async def test_w3_d_maerz_traegt_keine_e_auto_betriebskosten(db):
    anlage_id = await anlage_alle_achsen(db)
    maerz = await get_aktueller_monat(anlage_id=anlage_id, jahr=JAHR, monat=3, db=db)
    september = await get_aktueller_monat(anlage_id=anlage_id, jahr=JAHR, monat=9, db=db)
    assert maerz.betriebskosten_anteilig_euro == pytest.approx(10.0), "nur PV (120 €/J); kein E-Auto, keine Wallbox"
    assert september.betriebskosten_anteilig_euro == pytest.approx(60.0), "PV + E-Auto ab August"


@pytest.mark.asyncio
async def test_w3_e_ust_summe_der_monate_ist_der_jahreswert_nach_der_einen_regel(db):
    """(e) Σ Monat.ust_eigenverbrauch_euro == Jahreswert (G1) == Handrechnung nach Gernots Regel vom 05.06.2026.

    Handrechnung: Bemessung = PV 12 000 + BKW 600 + E-Auto max(0, 30 000 − 25 000) = 17 600 € (Wallbox ``aktiv=False``
    zählt NICHT); Betriebskosten = PV 120 + E-Auto 600 (im Jahr aktiv) = 720 €; zwölf abgeschlossene Monate.
    Satz = (17 600 / 20 + 720) / PV_Jahr × 19 %; EV_Jahr = Σ der Monats-EV (nicht die Perioden-EV — Januar klemmt).
    """
    anlage_id = await anlage_alle_achsen(db)
    monate = await _monate(db, anlage_id)
    anlage = await db.get(Anlage, anlage_id)
    await db.refresh(anlage, ["investitionen"])
    fakten = await lade_monats_fakten(db, anlage_id, von=(JAHR, 1), bis=(JAHR, 12))

    jahreswert = ust_eigenverbrauch_zeitraum(anlage, anlage.investitionen, fakten)
    summe_monate = sum(d.ust_eigenverbrauch_euro for d in monate)
    assert summe_monate == pytest.approx(jahreswert, abs=0.005 * 12)

    pv_jahr = sum(f.erzeugung.pv_kwh for f in fakten)
    ev_jahr = sum(f.kennzahlen.eigenverbrauch_kwh for f in fakten)
    hand = ev_jahr * ((17600.0 / AFA_JAHRE + 720.0) / pv_jahr) * 0.19
    assert jahreswert == pytest.approx(hand, rel=1e-9)
    # Gegenprobe der Achse: MIT der inaktiven Wallbox (Lesart „alle Investitionen") käme ein anderer Betrag heraus.
    mit_wallbox = ev_jahr * (((17600.0 + 1000.0) / AFA_JAHRE + 720.0 + 600.0) / pv_jahr) * 0.19
    assert abs(jahreswert - mit_wallbox) > 1.0
    # Und die EV-Achse: Perioden-EV (Summen erst addiert) ≠ Σ Monats-EV, weil der Januar klemmt.
    from backend.services.monats_fakten import kennzahlen_aus_fakten
    assert kennzahlen_aus_fakten(fakten).eigenverbrauch_kwh != pytest.approx(ev_jahr, abs=0.01)


@pytest.mark.asyncio
async def test_w3_b_jahr_ist_die_summe_seiner_monate(db):
    """(a-Jahr, b) Jahresroute: Netto-Ertrag, Ergebnis vor Betriebskosten und Ergebnis == Σ der zwölf Monate.

    Die Monate runden ihre Posten auf Cent, das Jahr summiert diese Posten ungerundet (G8) — Toleranz 0,005 × 12.
    """
    from backend.api.routes.cockpit.jahr import get_cockpit_jahr

    anlage_id = await anlage_alle_achsen(db)
    monate = await _monate(db, anlage_id)
    jahr = await get_cockpit_jahr(anlage_id=anlage_id, jahr=JAHR, db=db)
    kopf = jahr["kopf"]
    assert jahr["monate_nr"] == list(range(1, 13))
    tol = 0.005 * 12
    assert kopf["netto_ertrag_euro"] == pytest.approx(sum(d.netto_ertrag_euro for d in monate), abs=tol)
    assert kopf["ergebnis_vor_betriebskosten_euro"] == pytest.approx(
        sum(d.ergebnis_vor_betriebskosten_euro for d in monate), abs=tol)
    assert kopf["ergebnis_euro"] == pytest.approx(sum(d.ergebnis_euro for d in monate), abs=tol)
    assert kopf["ust_eigenverbrauch_euro"] == pytest.approx(sum(d.ust_eigenverbrauch_euro for d in monate), abs=tol)
    # Die Herleitung des Jahres führt auf die Zahl daneben.
    werte = kopf["ergebnis_herleitung"]["ergebnis"]["eingesetzte_werte"]
    assert sum(w["betrag_euro"] for w in werte) == pytest.approx(kopf["ergebnis_euro"], abs=1e-9)
    # Und die Monatsantworten selbst stehen in der Antwort (G3) — dieselben wie über die Monatsroute.
    assert [m["ergebnis_euro"] for m in jahr["monate"]] == [d.ergebnis_euro for d in monate]


async def _sichten(db, anlage_id):
    """Die übrigen Sichten derselben Anlage über echte Einstiege (Funktionsaufruf wie die Vier-Wege-Symmetrie)."""
    from backend.api.routes.cockpit.uebersicht import get_cockpit_uebersicht
    from backend.api.routes.ha_export import calculate_anlage_sensors
    from backend.api.routes.monatsdaten import list_monatsdaten_aggregiert
    from backend.services.pdf.builders.jahresbericht import build_jahresbericht_context

    uebersicht = await get_cockpit_uebersicht(anlage_id=anlage_id, jahr=JAHR, db=db)
    pdf = await build_jahresbericht_context(db, anlage_id, jahr=JAHR)
    anlage = await db.get(Anlage, anlage_id)
    ha = {s.definition.key: s.value for s in await calculate_anlage_sensors(db, anlage)}
    reihe = [z if isinstance(z, dict) else z.model_dump()
             for z in await list_monatsdaten_aggregiert(anlage_id=anlage_id, jahr=JAHR, db=db)]
    return uebersicht, pdf, ha, reihe


@pytest.mark.asyncio
async def test_w3_a_alle_sichten_nennen_denselben_netto_ertrag(db):
    """(a) Σ Monat.netto_ertrag == Jahr == Übersicht(jahr) == PDF-KPI == HA-Sensor == Σ Monatsreihe (±0,005 × 12).

    Die Fixture trägt nur 2025 — der HA-Sensor (Gesamtzeitraum) ist damit dasselbe Jahr.

    Die Monatsreihe (`/monatsdaten/aggregiert`, *Auswertungen → Tabelle/Finanzen*) steht seit A1 (Entscheid
    Fable-Master 03.10.2026) in der Kette: ihr `netto_ertrag_euro` trägt die Sonstigen Positionen wie jede andere
    Sicht. Vorher: Σ Reihe = Σ Monat − Σ Sonstige (1 432,46 gegen 1 462,46 €), und die Finanz-Sicht addierte die
    Sonstigen selbst.
    """
    from backend.api.routes.cockpit.jahr import get_cockpit_jahr

    anlage_id = await anlage_alle_achsen(db)
    monate = await _monate(db, anlage_id)
    jahr = await get_cockpit_jahr(anlage_id=anlage_id, jahr=JAHR, db=db)
    uebersicht, pdf, ha, reihe = await _sichten(db, anlage_id)
    summe = sum(d.netto_ertrag_euro for d in monate)
    tol = 0.005 * 12
    werte = {
        "Jahr": jahr["kopf"]["netto_ertrag_euro"],
        "Übersicht": uebersicht.netto_ertrag_euro,
        "PDF-KPI": pdf["kpis"]["netto_ertrag_euro"],
        "HA-Sensor": ha["netto_ertrag_euro"],
        "Σ Monatsreihe": sum(z["netto_ertrag_euro"] for z in reihe),
    }
    abw = {k: v for k, v in werte.items() if v != pytest.approx(summe, abs=tol)}
    assert not abw, f"Σ Monat {summe:.2f} — abweichend: {abw}"
    # Die Achsen tragen wirklich etwas bei (sonst wäre die Gleichheit billig).
    assert sum(d.ust_eigenverbrauch_euro for d in monate) > 50.0
    assert sum(d.sonstige_netto_euro for d in monate) == pytest.approx(30.0)


@pytest.mark.asyncio
async def test_w3_c_pdf_monatszeilen_summieren_auf_die_kpi(db):
    """(c) Σ PDF-Monatszeilen.netto_ertrag == PDF-KPI — im selben Dokument (E6a: vorher fehlten USt, BKW-Rest, Erzeuger)."""
    anlage_id = await anlage_alle_achsen(db)
    _u, pdf, _h, _r = await _sichten(db, anlage_id)
    zeilen = pdf["monats_zeilen"]
    assert len(zeilen) == 12
    assert sum(z["netto_ertrag_euro"] for z in zeilen) == pytest.approx(pdf["kpis"]["netto_ertrag_euro"], abs=0.005 * 12)


@pytest.mark.asyncio
async def test_w3_e_ust_monat_uebersicht_monatsreihe_gleich(db):
    """(e) Σ Monat.ust_eigenverbrauch == Übersicht == Σ Monatsreihe (§12 Nr. 1: vorher 18,90 · 20,21 · 35,96)."""
    anlage_id = await anlage_alle_achsen(db)
    monate = await _monate(db, anlage_id)
    uebersicht, _p, _h, reihe = await _sichten(db, anlage_id)
    summe = sum(d.ust_eigenverbrauch_euro for d in monate)
    tol = 0.005 * 12
    assert uebersicht.ust_eigenverbrauch_euro == pytest.approx(summe, abs=tol)
    assert sum(z["ust_eigenverbrauch_euro"] for z in reihe) == pytest.approx(summe, abs=tol)


@pytest.mark.asyncio
async def test_w3_ha_herleitung_nennt_negative_sonstige_mit_minus(db):
    """Die Herleitung des HA-Sensors setzt das Rechenzeichen nach dem Betrag: Sonstige Positionen, die netto eine
    Ausgabe sind, stehen als „− 320,00 (Sonstige Positionen)", nicht als „+ 320,00" (gefunden im HA-GM beim Bau,
    r28: „+ 530,00 (Sonstige Positionen)" für −530 €). Die Zahl war richtig, der Text nicht."""
    from sqlalchemy import select

    from backend.api.routes.ha_export import calculate_anlage_sensors

    anlage_id = await anlage_alle_achsen(db)
    juni = (await db.execute(select(Monatsdaten).where(
        Monatsdaten.anlage_id == anlage_id, Monatsdaten.jahr == JAHR, Monatsdaten.monat == 6))).scalar_one()
    juni.sonstige_positionen = [{"bezeichnung": "Reparatur", "betrag": 200.0, "typ": "ausgabe"}]
    await db.commit()
    anlage = await db.get(Anlage, anlage_id)
    sensor = next(s for s in await calculate_anlage_sensors(db, anlage) if s.definition.key == "netto_ertrag_euro")
    assert "− 320,00 (Sonstige Positionen)" in sensor.berechnung, sensor.berechnung
    assert "+ 320,00" not in sensor.berechnung
    assert "− 126," in sensor.berechnung and "(USt auf Eigenverbrauch)" in sensor.berechnung
