"""Aussichten == Cockpit: Finanz-Symmetrie nach der finanz_aggregat-Vollmigration.

Seit v3.41.0 (#326) rechnen Cockpit, Jahresbericht-PDF und HA-Export über den
SoT-Helper `berechne_finanz_aggregat`; `aussichten.get_finanz_prognose` rollte
seine historische Ertrags-Aggregation noch selbst. Diese Tests sichern die
Vollmigration: die „bisherigen Erträge" der Aussichten und der Cockpit-
Netto-Ertrag müssen auf einem gemeinsamen Fixture (Flex-Tarif + Speicher +
Sonstige + Dienstwagen) denselben Wert liefern ([[feedback_aggregator_symmetrie]]).

Mitgezogen (beidseitig, sonst neue Asymmetrie):
- Dienstwagen-Ladekosten-Abzug per-Monat über `resolve_netzbezug_preis_cent`
  statt statischem Tarifpreis.
- Mengen und Bewertung des Dienstwagens laufen seit 2026-07-31 über die
  Monats-Fakten (P10) und den Layer-SoT `berechne_dienstliche_ladekosten`
  (ADR-001) — inklusive `get_emob_pv_netz_kwh` (#262 evcc-Fallback) in der Schicht.

**Erwartungswerte angepasst 2026-07-31 (N-18).** Der PV-Anteil der dienstlichen
Ladung wird jetzt mit dem **Netzbezugspreis** bewertet statt mit der
Einspeisevergütung — er nimmt damit die EV-Gutschrift zurück, die
`berechne_finanz_aggregat` für dieselben kWh gutschreibt. Im Fixture unten sind
das 50 kWh im Mai zu 20 statt 8 ct: der Abzug steigt von 104,00 € auf 110,00 €,
der Netto-Ertrag fällt von 152,80 € auf 146,80 €. Die **Symmetrie**, die diese
Datei bewacht, ist davon unberührt — sie wird nur auf der neuen Zahl geprüft.
Herleitung und Messtabelle: `test_dienstliche_ladekosten_drei_sichten.py`.
"""

from __future__ import annotations

from datetime import date

import pytest

from backend.api.routes.aussichten import get_finanz_prognose
from backend.api.routes.cockpit.uebersicht import get_cockpit_uebersicht
from backend.models import Anlage, Investition, Monatsdaten, Strompreis
from backend.models.investition import InvestitionMonatsdaten


async def _anlage_flex_speicher_sonstige_dienstwagen(db) -> int:
    """Flex-Tarif + Speicher + Sonstige (THG) + Dienstwagen, zwei Monate
    gegenläufiger Flexpreis-/Last-Charakteristik.

    Mai:  pv 1000, einsp 600, netz 50, lad 100, entl 80, flex 20 ct
          EV = (1000-600-100) + 80 = 380 → 76,00 €
    Dez:  pv 100, einsp 20, netz 500, lad 10, entl 8, flex 40 ct
          EV = (100-20-10) + 8 = 78 → 31,20 €
    einspeise  = 620 · 0,08            =  49,60 €
    sonstige   = +100 (THG)
    dienstlich = (100·0,20 Netz + 50·0,20 PV) + (200·0,40 Netz) = 30 + 80 = 110,00 €
                 ↑ beide Anteile zum Monats-Flexpreis: Netz, weil es der
                   Wallbox-Preis ist (kein WB-Vertrag → Anlagentarif → Flex-Ø),
                   PV, weil der Abzug die EV-Gutschrift zurücknimmt (N-18).
    netto      = 49,60 + 107,20 + 100 − 110 = 146,80 €
    """
    anlage = Anlage(anlagenname="FinanzSymAussichten", leistung_kwp=10.0)
    db.add(anlage)
    await db.flush()

    db.add(Strompreis(
        anlage_id=anlage.id, gueltig_ab=date(2024, 1, 1),
        netzbezug_arbeitspreis_cent_kwh=30.0, einspeiseverguetung_cent_kwh=8.0,
    ))
    db.add(Monatsdaten(anlage_id=anlage.id, jahr=2026, monat=5,
                       einspeisung_kwh=600.0, netzbezug_kwh=50.0,
                       netzbezug_durchschnittspreis_cent=20.0))
    db.add(Monatsdaten(anlage_id=anlage.id, jahr=2026, monat=12,
                       einspeisung_kwh=20.0, netzbezug_kwh=500.0,
                       netzbezug_durchschnittspreis_cent=40.0))

    pv = Investition(anlage_id=anlage.id, typ="pv-module", bezeichnung="Dach",
                     leistung_kwp=10.0, anschaffungsdatum=date(2024, 1, 1),
                     anschaffungskosten_gesamt=10000.0)
    speicher = Investition(anlage_id=anlage.id, typ="speicher", bezeichnung="Akku",
                           anschaffungsdatum=date(2024, 1, 1),
                           parameter={"kapazitaet_kwh": 10.0})
    dienstwagen = Investition(anlage_id=anlage.id, typ="e-auto",
                              bezeichnung="Firmenwagen",
                              anschaffungsdatum=date(2024, 1, 1),
                              parameter={"ist_dienstlich": True})
    db.add_all([pv, speicher, dienstwagen])
    await db.flush()

    db.add(InvestitionMonatsdaten(investition_id=pv.id, jahr=2026, monat=5,
        verbrauch_daten={"pv_erzeugung_kwh": 1000.0,
                         "sonstige_positionen": [
                             {"bezeichnung": "THG-Quote", "betrag": 100.0, "typ": "ertrag"}]}))
    db.add(InvestitionMonatsdaten(investition_id=pv.id, jahr=2026, monat=12,
        verbrauch_daten={"pv_erzeugung_kwh": 100.0}))
    db.add(InvestitionMonatsdaten(investition_id=speicher.id, jahr=2026, monat=5,
        verbrauch_daten={"ladung_kwh": 100.0, "entladung_kwh": 80.0}))
    db.add(InvestitionMonatsdaten(investition_id=speicher.id, jahr=2026, monat=12,
        verbrauch_daten={"ladung_kwh": 10.0, "entladung_kwh": 8.0}))
    # Dienstwagen: Mai mit PV-Anteil, Dez reine Netzladung — die per-Monat-
    # Flexpreise (20/40 ct) unterscheiden sich klar vom statischen Tarif (30 ct).
    db.add(InvestitionMonatsdaten(investition_id=dienstwagen.id, jahr=2026, monat=5,
        verbrauch_daten={"ladung_kwh": 150.0, "ladung_pv_kwh": 50.0,
                         "ladung_netz_kwh": 100.0}))
    db.add(InvestitionMonatsdaten(investition_id=dienstwagen.id, jahr=2026, monat=12,
        verbrauch_daten={"ladung_kwh": 200.0, "ladung_pv_kwh": 0.0,
                         "ladung_netz_kwh": 200.0}))
    await db.commit()
    return anlage.id


async def test_aussichten_bisherige_ertraege_gleich_cockpit_netto(db):
    """Cockpit-Netto-Ertrag == Aussichten-bisherige-Erträge == 146,80 €.

    Keine WP/kein privates E-Auto/keine Betriebskosten im Fixture — damit ist
    `bisherige_ertraege_euro` exakt das Finanz-Aggregat und direkt mit dem
    Cockpit-`netto_ertrag_euro` vergleichbar.
    """
    anlage_id = await _anlage_flex_speicher_sonstige_dienstwagen(db)
    erwartet = 146.8

    cockpit = await get_cockpit_uebersicht(anlage_id=anlage_id, jahr=None, db=db)
    aussichten = await get_finanz_prognose(anlage_id=anlage_id, monate=12, db=db)

    assert cockpit.netto_ertrag_euro == pytest.approx(erwartet, abs=0.05), (
        f"Cockpit netto {cockpit.netto_ertrag_euro} ≠ {erwartet}")
    assert aussichten.bisherige_ertraege_euro == pytest.approx(erwartet, abs=0.05), (
        f"Aussichten bisherige Erträge {aussichten.bisherige_ertraege_euro} ≠ {erwartet}")
    assert aussichten.bisherige_ertraege_euro == pytest.approx(
        cockpit.netto_ertrag_euro, abs=0.01)


async def test_dienstwagen_abzug_per_monat_flexpreis(db):
    """Der Dienstwagen-Abzug nutzt den Monats-Flexpreis, nicht den Tarifpreis.

    Per-Monat: 100·0,20 + 200·0,40 = 100,00 € Netz-Anteil (+ 10 € PV).
    Alt/statisch: 300·0,30 = 90,00 € Netz-Anteil (+ 15 € PV) → 15 € Differenz,
    die in beiden Read-Sites identisch ankommen muss.
    """
    anlage_id = await _anlage_flex_speicher_sonstige_dienstwagen(db)

    cockpit = await get_cockpit_uebersicht(anlage_id=anlage_id, jahr=None, db=db)
    # sonstige_netto = 100 (THG) − 110 (Dienstwagen) = −10
    assert cockpit.sonstige_netto_euro == pytest.approx(-10.0, abs=0.05)
    # Gegenprobe: mit statischem 30-ct-Abzug wäre sonstige_netto = 100 − 105 = −5.
    assert abs(cockpit.sonstige_netto_euro - (-5.0)) > 4.0


async def _anlage_mit_tarifwechsel_und_dienstwagen(db) -> int:
    """Zwei Monate in ZWEI Tarifperioden, bewusst OHNE Flex-Ø.

    Die Fixture oben gibt jedem Monat einen `netzbezug_durchschnittspreis_cent`
    — damit übersteuert der Flex-Ø den Stammdaten-Tarif, und die Achse
    „historischer Basistarif" wird nie geprüft. Genau diese blinde Achse hat
    2026-07-30 zugelassen, dass `aussichten` auf den Monats-Stichtag gezogen
    wurde, während Cockpit weiter mit dem heutigen Tarif rechnete
    (ADR-002/P8, [[feedback_aggregator_symmetrie]]).

    Tarif bis 2025: 20 ct Bezug / 10 ct Einspeisung. Ab 2026: 40 / 6.

    2025-06: einsp 100 → 10,00 € · EV (200−100) × 0,20 → 20,00 €
    2026-06: einsp  50 →  3,00 € · EV (100− 50) × 0,40 → 20,00 €
    Dienstwagen: 100 kWh Netz je Monat → 100×0,20 + 100×0,40 = 60,00 € Abzug
    netto = 10 + 20 + 3 + 20 − 60 = −7,00 €
    (mit dem HEUTIGEN Tarif für alles wären es 53 − 80 = −27,00 €)
    """
    anlage = Anlage(anlagenname="P8Symmetrie", leistung_kwp=10.0)
    db.add(anlage)
    await db.flush()

    db.add(Strompreis(
        anlage_id=anlage.id,
        gueltig_ab=date(2024, 1, 1), gueltig_bis=date(2025, 12, 31),
        netzbezug_arbeitspreis_cent_kwh=20.0, einspeiseverguetung_cent_kwh=10.0,
    ))
    db.add(Strompreis(
        anlage_id=anlage.id, gueltig_ab=date(2026, 1, 1),
        netzbezug_arbeitspreis_cent_kwh=40.0, einspeiseverguetung_cent_kwh=6.0,
    ))
    db.add(Monatsdaten(anlage_id=anlage.id, jahr=2025, monat=6,
                       einspeisung_kwh=100.0, netzbezug_kwh=0.0))
    db.add(Monatsdaten(anlage_id=anlage.id, jahr=2026, monat=6,
                       einspeisung_kwh=50.0, netzbezug_kwh=0.0))

    pv = Investition(anlage_id=anlage.id, typ="pv-module", bezeichnung="Dach",
                     leistung_kwp=10.0, anschaffungsdatum=date(2024, 1, 1),
                     anschaffungskosten_gesamt=10000.0)
    dienstwagen = Investition(anlage_id=anlage.id, typ="e-auto",
                              bezeichnung="Firmenwagen",
                              anschaffungsdatum=date(2024, 1, 1),
                              parameter={"ist_dienstlich": True})
    db.add_all([pv, dienstwagen])
    await db.flush()

    db.add(InvestitionMonatsdaten(investition_id=pv.id, jahr=2025, monat=6,
        verbrauch_daten={"pv_erzeugung_kwh": 200.0}))
    db.add(InvestitionMonatsdaten(investition_id=pv.id, jahr=2026, monat=6,
        verbrauch_daten={"pv_erzeugung_kwh": 100.0}))
    for j in (2025, 2026):
        db.add(InvestitionMonatsdaten(investition_id=dienstwagen.id, jahr=j, monat=6,
            verbrauch_daten={"ladung_kwh": 100.0, "ladung_pv_kwh": 0.0,
                             "ladung_netz_kwh": 100.0}))
    await db.commit()
    return anlage.id


async def test_historischer_basistarif_beidseitig_gleich(db):
    """ADR-002/P8: Cockpit und Aussichten nehmen denselben Monats-Basistarif."""
    anlage_id = await _anlage_mit_tarifwechsel_und_dienstwagen(db)
    erwartet = -7.0

    cockpit = await get_cockpit_uebersicht(anlage_id=anlage_id, jahr=None, db=db)
    aussichten = await get_finanz_prognose(anlage_id=anlage_id, monate=12, db=db)

    assert cockpit.netto_ertrag_euro == pytest.approx(erwartet, abs=0.05)
    assert aussichten.bisherige_ertraege_euro == pytest.approx(erwartet, abs=0.05)
    assert aussichten.bisherige_ertraege_euro == pytest.approx(
        cockpit.netto_ertrag_euro, abs=0.01)
    # Gegenprobe: mit dem heutigen Tarif für alles wären es −27 €.
    assert abs(cockpit.netto_ertrag_euro - (-27.0)) > 15.0
