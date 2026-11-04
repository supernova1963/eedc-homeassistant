"""N-774 — Gesamt-ROI, Gesamt-Amortisation und Kalender-Treppe ziehen die Betriebskosten NICHT bewerteter Zeilen ab.

Auswertungen → ROI. Eine Zeile, für die eedc keine Ersparnis bewertet (`detail.nicht_bewertet`: Wärmepumpe ohne
Wärmebedarf, Sonstiges ohne Ertrag/Jahr), zeigt in der Spalte *Jahres-Einsparung* «—» und trägt 0 zur Spaltensumme
bei (N-258, unverändert). Bis N-774 (4.11.2026) fehlten ihre Betriebskosten damit auch im Gesamt-ROI, in der
Gesamt-Amortisation und in der Treppe — während die Annahme-Zeile «inkl. N €/Jahr Betriebskosten» sie mitnannte
(Messung Demo r28: 24,1 J statt mit Abzug). Entscheid Gernot 4.11.2026 (Weg a): die Kosten zählen im Gesamt als
eigenes Argument von `berechne_roi` und als negative `ErsparnisZeile`; bewertete Zeilen tragen ihre Kosten schon in
ihrer Netto-Einsparung und werden nicht doppelt belastet.
"""

from __future__ import annotations

from datetime import date

import pytest

from backend.api.routes.investitionen.crud import get_roi_dashboard
from backend.core.berechnungen.kapitalrechnung import (
    ErsparnisZeile,
    KapitalEreignis,
    amortisations_verlauf,
)
from backend.models import Anlage, Investition, Monatsdaten
from backend.models.investition import InvestitionMonatsdaten

JAHR = 2023
WP_BETRIEBSKOSTEN = 200.0
SONSTIGES_BETRIEBSKOSTEN = 300.0

# Wärmepumpe mit allem außer dem Wärmebedarf ⇒ `_wp_nicht_bewertbar` (Grund 3).
WP_OHNE_BEDARF = {
    "wp_art": "luft_wasser",
    "effizienz_modus": "gesamt_jaz",
    "jaz": 3.5,
    "alter_energietraeger": "gas",
    "alter_preis_cent_kwh": 12,
}
WP_MIT_BEDARF = {**WP_OHNE_BEDARF, "heizwaermebedarf_kwh": 9000, "warmwasserbedarf_kwh": 2000}


async def _seed(db, *, bewertet: bool) -> dict:
    """PV-System (bewertet) + Wärmepumpe (200 €/Jahr) + Sonstiges (300 €/Jahr), alle im selben Jahr angeschafft.

    `bewertet=False`: WP ohne Bedarf, Sonstiges ohne Ertrag/Jahr ⇒ beide `nicht_bewertet`.
    `bewertet=True` (Gegenfall): WP mit Bedarf, Sonstiges mit Ertrag/Jahr ⇒ beide bewertet.
    """
    anlage = Anlage(anlagenname="N-774", leistung_kwp=10.0)
    db.add(anlage)
    await db.flush()
    db.add(Monatsdaten(anlage_id=anlage.id, jahr=2026, monat=5, netzbezug_kwh=100.0, einspeisung_kwh=300.0))
    wr = Investition(
        anlage_id=anlage.id, typ="wechselrichter", bezeichnung="WR",
        anschaffungsdatum=date(JAHR, 3, 1), anschaffungskosten_gesamt=2000.0,
    )
    db.add(wr)
    await db.flush()
    pv = Investition(
        anlage_id=anlage.id, typ="pv-module", bezeichnung="Dach", parent_investition_id=wr.id,
        leistung_kwp=10.0, anschaffungsdatum=date(JAHR, 3, 1), anschaffungskosten_gesamt=10000.0,
    )
    db.add(pv)
    await db.flush()
    db.add(InvestitionMonatsdaten(investition_id=pv.id, jahr=2026, monat=5,
                                  verbrauch_daten={"pv_erzeugung_kwh": 800.0}))
    wp = Investition(
        anlage_id=anlage.id, typ="waermepumpe", bezeichnung="WP",
        anschaffungsdatum=date(JAHR, 6, 1), anschaffungskosten_gesamt=8000.0,
        betriebskosten_jahr=WP_BETRIEBSKOSTEN,
        parameter=dict(WP_MIT_BEDARF if bewertet else WP_OHNE_BEDARF),
    )
    sonst = Investition(
        anlage_id=anlage.id, typ="sonstiges", bezeichnung="Mini-BHKW",
        anschaffungsdatum=date(JAHR, 9, 1), anschaffungskosten_gesamt=4000.0,
        betriebskosten_jahr=SONSTIGES_BETRIEBSKOSTEN,
        einsparung_prognose_jahr=900.0 if bewertet else None,
        parameter={"kategorie": "erzeuger"},
    )
    db.add_all([wp, sonst])
    await db.flush()
    await db.commit()
    return {"anlage_id": anlage.id, "wp": wp.id, "sonst": sonst.id}


async def _roi(db, anlage_id: int):
    return await get_roi_dashboard(
        anlage_id=anlage_id, strompreis_cent=30.0, einspeiseverguetung_cent=8.0,
        benzinpreis_euro=None, jahr=None, db=db,
    )


def _zeile(result, inv_id: int):
    return next(b for b in result.berechnungen if b.investition_id == inv_id)


async def test_unbewertete_zeilen_bleiben_n258(db):
    """Die Zeilen selbst bleiben, wie N-258 sie gebaut hat: Einsparung 0 («—»), ROI None, Flag gesetzt."""
    ids = await _seed(db, bewertet=False)
    result = await _roi(db, ids["anlage_id"])
    for inv_id in (ids["wp"], ids["sonst"]):
        b = _zeile(result, inv_id)
        assert b.jahres_einsparung == 0.0
        assert b.roi_prozent is None
        assert b.detail_berechnung["nicht_bewertet"] is True
    # Die Spaltensumme ist die Summe der angezeigten Zeilen (ohne USt-Abzug: keine Regelbesteuerung).
    assert result.gesamt_jahres_einsparung == pytest.approx(
        round(sum(b.jahres_einsparung for b in result.berechnungen), 2), abs=0.01,
    )


async def test_gesamt_roi_und_dauer_ziehen_die_betriebskosten_unbewerteter_zeilen_ab(db):
    ids = await _seed(db, bewertet=False)
    result = await _roi(db, ids["anlage_id"])
    abzug = WP_BETRIEBSKOSTEN + SONSTIGES_BETRIEBSKOSTEN
    summe = result.gesamt_jahres_einsparung
    kapital = result.gesamt_kapitaleinsatz
    assert summe - abzug > 0, "Testaufbau: die PV-Zeile muss die 500 € tragen"
    assert result.gesamt_roi_prozent == round((summe - abzug) / kapital * 100, 1)
    assert result.gesamt_amortisation_jahre == round(kapital / (summe - abzug), 1)
    # Die Annahme-Zeile nennt dieselben 500 € — jetzt stimmt sie mit der Zahl überein.
    assert "500,00 €" in result.amortisation_annahme


async def test_treppe_und_break_even_rechnen_mit_der_negativen_zeile(db):
    ids = await _seed(db, bewertet=False)
    result = await _roi(db, ids["anlage_id"])
    abzug = WP_BETRIEBSKOSTEN + SONSTIGES_BETRIEBSKOSTEN
    summe = result.gesamt_jahres_einsparung
    kapital = result.gesamt_kapitaleinsatz
    assert result.basis_jahr == JAHR
    assert all(b.anschaffungsjahr == JAHR for b in result.berechnungen)

    # Je Jahr wächst die kumulierte Einsparung um Σ − 500 (alle Zeilen ab demselben Jahr).
    reihe = result.amortisations_verlauf
    for vor, nach in zip(reihe, reihe[1:]):
        assert nach.einsparung_kumuliert_euro - vor.einsparung_kumuliert_euro == pytest.approx(summe - abzug, abs=0.02)

    # Break-Even = der Layer mit einer Ersparnis-Zeile −500 (N-525-Muster: Layer direkt aufrufen).
    erwartet = amortisations_verlauf(
        kapital=[KapitalEreignis(JAHR, kapital)],
        ersparnis=[ErsparnisZeile(JAHR, summe), ErsparnisZeile(JAHR, -abzug)],
    ).break_even_jahr
    assert erwartet is not None
    assert result.gesamt_amortisation_jahr == erwartet
    ohne_abzug = amortisations_verlauf(
        kapital=[KapitalEreignis(JAHR, kapital)], ersparnis=[ErsparnisZeile(JAHR, summe)],
    ).break_even_jahr
    assert ohne_abzug is not None and erwartet > ohne_abzug, "Testaufbau: der Abzug muss das Jahr verschieben"


async def test_gegenfall_bewertete_zeilen_kein_doppelabzug(db):
    """Bewertete Zeilen tragen ihre Betriebskosten schon in ihrer Netto-Einsparung — der Gesamt zieht sie nicht noch einmal ab."""
    ids = await _seed(db, bewertet=True)
    result = await _roi(db, ids["anlage_id"])
    for inv_id in (ids["wp"], ids["sonst"]):
        assert not _zeile(result, inv_id).detail_berechnung.get("nicht_bewertet")
    summe = result.gesamt_jahres_einsparung
    kapital = result.gesamt_kapitaleinsatz
    assert result.gesamt_roi_prozent == round(summe / kapital * 100, 1)
    assert result.gesamt_amortisation_jahre == round(kapital / summe, 1)
    erwartet = amortisations_verlauf(
        kapital=[KapitalEreignis(JAHR, kapital)], ersparnis=[ErsparnisZeile(JAHR, summe)],
    ).break_even_jahr
    assert result.gesamt_amortisation_jahr == erwartet
    assert "500,00 €" in result.amortisation_annahme
