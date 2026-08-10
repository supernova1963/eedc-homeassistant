"""ROI-Dashboard: manuell gepflegte „Sonstige Erträge & Ausgaben" einrechnen — #310.

rilmor-mhrs (#310): Die per Investition/Monat erfassten `sonstige_positionen`
(z. B. Einspeise-Erträge eines zweiten Wechselrichters mit eigenem Tarif)
wurden im ROI-Dashboard (`Auswertung → Monatsberichte → Investitionen`) nie
berücksichtigt — wohl aber im Cockpit-Monatsbericht und in der Aussichten-
Finanzprognose. Dadurch stimmte der ROI in der Auswertungs-Sicht nicht.

`get_roi_dashboard` rechnet die Beträge jetzt über den SoT-Helper
`berechne_sonstige_summen` ein — für alle Typen (Standalone + PV-System +
Orphan-Modul).

⚠ **Seit F-19 (2026-08-09) auf zwei Seiten des Bruchs**, SoT
`core/berechnungen/kapitalrechnung.py`:

* **Ausgaben** (Reparatur, Wartung) gehen **kumuliert in den Nenner**. Vorher
  wurden sie annualisiert im Zähler abgezogen, wodurch eine einmalige Reparatur
  jedes Jahr aufs Neue belastete (Wärmepumpe: 8,1 → 42,6 Jahre).
* **Erträge** standen bis dahin annualisiert im **Zähler**.

⚠ **Und seit §8/3 des Wirtschaftlichkeits-Konzepts (2026-08-10) werden auch die
Erträge nicht mehr projiziert.** Eine Position im Monatsabschluss ist per Form
einmal geflossen; sie zu mitteln und fortzuschreiben unterstellt eine
Wiederholung. Für Roberts Fall — einen *wiederkehrenden* Einspeise-Erlös —
gibt es seit §8/1 das Feld **„Ertrag/Jahr"** an der Investition und seit §8/9
das €-Feld **„Einspeise-Erlös"** je Erzeuger; nur diese wirken in Prognose und
ROI-Zähler. `sonstige_netto_euro` ist seither beidseitig **kumuliert** und
damit wieder eine Aussage (vorher: annualisierter Ertrag gegen kumulierte
Ausgabe).

⚠ **Und seit Bauschritt 7 (ebenfalls 2026-08-10) stehen die Erträge im
NENNER**: sie mindern den Kapitaleinsatz, spiegelbildlich zu den Ausgaben. In
der Zeitraum-Bilanz und im Amortisations-Fortschritt bleiben sie unverändert
sichtbar.
"""

from __future__ import annotations

from datetime import date

import pytest

from backend.api.routes.investitionen.crud import get_roi_dashboard
from backend.models import Anlage, Investition, Monatsdaten
from backend.models.investition import InvestitionMonatsdaten


def _sonstige(positionen: list[dict]) -> dict:
    return {"sonstige_positionen": positionen}


async def _berechnung_fuer(result, inv_id: int):
    return next(b for b in result.berechnungen if b.investition_id == inv_id)


# ============================================================================
# Standalone (typ „sonstiges") — jahr-spezifisch
# ============================================================================


async def test_roi_standalone_sonstige_jahr_spezifisch(db):
    """jahr=2026: das ROI-Netto der Investition = Σ sonstige Netto des Jahres."""
    anlage = Anlage(anlagenname="Test", leistung_kwp=10.0)
    db.add(anlage)
    await db.flush()
    inv = Investition(
        anlage_id=anlage.id, typ="sonstiges", bezeichnung="Zweit-WR-Ertrag",
        anschaffungsdatum=date(2024, 1, 1),
        anschaffungskosten_gesamt=1000.0,
        betriebskosten_jahr=0.0,
        einsparung_prognose_jahr=0.0,
    )
    db.add(inv)
    await db.flush()
    db.add(InvestitionMonatsdaten(
        investition_id=inv.id, jahr=2026, monat=4,
        verbrauch_daten=_sonstige([{"bezeichnung": "THG", "betrag": 200.0, "typ": "ertrag"}]),
    ))
    db.add(InvestitionMonatsdaten(
        investition_id=inv.id, jahr=2026, monat=5,
        verbrauch_daten=_sonstige([{"bezeichnung": "Reparatur", "betrag": 50.0, "typ": "ausgabe"}]),
    ))
    await db.flush()

    result = await get_roi_dashboard(
        anlage_id=anlage.id, strompreis_cent=None, einspeiseverguetung_cent=None,
        benzinpreis_euro=None, jahr=2026, db=db,
    )
    b = await _berechnung_fuer(result, inv.id)
    # 200 € Ertrag − 50 € Ausgabe = 150 € netto (Anzeige-Größe, unverändert)
    assert b.detail_berechnung["sonstige_netto_euro"] == pytest.approx(150.0)
    # §8/3: der Ertrag wird nicht mehr projiziert — der Zähler bleibt leer.
    assert b.jahres_einsparung == pytest.approx(0.0)
    # F-19: die Ausgabe erhöht den Kapitaleinsatz, Bauschritt 7: der Ertrag
    # mindert ihn — 1.000 € Anschaffung + 50 € − 200 € = 850 €.
    assert b.detail_berechnung["sonstige_ausgaben_euro"] == pytest.approx(50.0)
    assert b.detail_berechnung["sonstige_ertraege_euro"] == pytest.approx(200.0)
    assert b.kapitaleinsatz == pytest.approx(850.0)


async def test_roi_standalone_sonstige_jahr_none_kumuliert(db):
    """jahr=None: Σ sonstige Netto über alle Jahre — **kumuliert**, nicht gemittelt.

    ⚠ Bis §8/3 stand hier ein Jahres-Divisor (150 € ÷ 2 Jahre = 75 €/Jahr). Er
    diente allein dazu, den Ertrag mit den Jahres-Einsparungen im Zähler
    vergleichbar zu machen. Ohne Projektion gibt es diesen Zähler nicht mehr —
    und eine gemittelte Anzeige neben einer kumulierten Ausgabe wäre eine
    Größe, die keine Frage beantwortet.
    """
    anlage = Anlage(anlagenname="Test", leistung_kwp=10.0)
    db.add(anlage)
    await db.flush()
    # Zwei Jahre mit Monatsdaten — der Fall, in dem der frühere Divisor 2 griff.
    for j in (2025, 2026):
        db.add(Monatsdaten(anlage_id=anlage.id, jahr=j, monat=1,
                           netzbezug_kwh=100.0, einspeisung_kwh=200.0))
    inv = Investition(
        anlage_id=anlage.id, typ="sonstiges", bezeichnung="Ertrag",
        anschaffungsdatum=date(2024, 1, 1),
        anschaffungskosten_gesamt=1000.0,
        betriebskosten_jahr=0.0, einsparung_prognose_jahr=0.0,
    )
    db.add(inv)
    await db.flush()
    db.add(InvestitionMonatsdaten(
        investition_id=inv.id, jahr=2026, monat=4,
        verbrauch_daten=_sonstige([{"bezeichnung": "THG", "betrag": 150.0, "typ": "ertrag"}]),
    ))
    await db.flush()

    result = await get_roi_dashboard(
        anlage_id=anlage.id, strompreis_cent=None, einspeiseverguetung_cent=None,
        benzinpreis_euro=None, jahr=None, db=db,
    )
    b = await _berechnung_fuer(result, inv.id)
    # 150 € kumuliert — ungeteilt, über beide Jahre
    assert b.detail_berechnung["sonstige_netto_euro"] == pytest.approx(150.0)
    # … und ohne jede Wirkung auf den Zähler (§8/3)
    assert b.jahres_einsparung == pytest.approx(0.0)


async def test_roi_standalone_ohne_sonstige_bleibt_null(db):
    """Ohne sonstige Positionen: Feld 0, kein Effekt (Regressions-Schutz)."""
    anlage = Anlage(anlagenname="Test", leistung_kwp=10.0)
    db.add(anlage)
    await db.flush()
    inv = Investition(
        anlage_id=anlage.id, typ="sonstiges", bezeichnung="Leer",
        anschaffungsdatum=date(2024, 1, 1),
        anschaffungskosten_gesamt=1000.0,
        betriebskosten_jahr=0.0, einsparung_prognose_jahr=0.0,
    )
    db.add(inv)
    await db.flush()

    result = await get_roi_dashboard(
        anlage_id=anlage.id, strompreis_cent=None, einspeiseverguetung_cent=None,
        benzinpreis_euro=None, jahr=2026, db=db,
    )
    b = await _berechnung_fuer(result, inv.id)
    assert b.detail_berechnung["sonstige_netto_euro"] == pytest.approx(0.0)
    assert b.jahres_einsparung == pytest.approx(0.0)


# ============================================================================
# PV-System — Roberts Fall: Ertrag am Wechselrichter gepflegt
# ============================================================================


async def test_roi_pv_system_sonstige_am_wechselrichter(db):
    """Sonstige Erträge am WR fließen in den PV-System-ROI (Roberts Fall)."""
    anlage = Anlage(anlagenname="Test", leistung_kwp=10.0)
    db.add(anlage)
    await db.flush()
    db.add(Monatsdaten(anlage_id=anlage.id, jahr=2026, monat=5,
                       netzbezug_kwh=100.0, einspeisung_kwh=300.0))
    wr = Investition(
        anlage_id=anlage.id, typ="wechselrichter", bezeichnung="WR-2",
        anschaffungsdatum=date(2024, 1, 1), anschaffungskosten_gesamt=2000.0,
    )
    db.add(wr)
    await db.flush()
    pv = Investition(
        anlage_id=anlage.id, typ="pv-module", bezeichnung="Dach-Ost",
        parent_investition_id=wr.id, leistung_kwp=10.0,
        anschaffungsdatum=date(2024, 1, 1), anschaffungskosten_gesamt=10000.0,
    )
    db.add(pv)
    await db.flush()
    db.add(InvestitionMonatsdaten(
        investition_id=pv.id, jahr=2026, monat=5,
        verbrauch_daten={"pv_erzeugung_kwh": 800.0},
    ))
    # Ertrag am Wechselrichter (eigener Einspeisetarif) — Roberts Konstellation.
    db.add(InvestitionMonatsdaten(
        investition_id=wr.id, jahr=2026, monat=5,
        verbrauch_daten=_sonstige([{"bezeichnung": "Einspeise-Sondertarif", "betrag": 120.0, "typ": "ertrag"}]),
    ))
    await db.flush()

    result = await get_roi_dashboard(
        anlage_id=anlage.id, strompreis_cent=30.0, einspeiseverguetung_cent=8.0,
        benzinpreis_euro=None, jahr=2026, db=db,
    )
    system = next(b for b in result.berechnungen if b.investition_typ == "pv-system")
    assert system.detail_berechnung["sonstige_netto_euro"] == pytest.approx(120.0)
