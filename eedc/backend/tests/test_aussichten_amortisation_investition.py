"""Charakterisierungs-Tests: aussichten.get_finanz_prognose — Vorwärts-Pfad
(Investitions-Komposition + Amortisation).

Spur 0 des Backend-Refactoring-Plans: `get_finanz_prognose` (1023 Z.) hat ein
breites Bestandsnetz für die HISTORISCHE Aggregation/Ersparnis
(test_aussichten_*: Multi-WP/-E-Auto, EV-Quote #304, BKW-Flexpreis #326,
Finanz-Aggregat-Symmetrie, Anschaffungsdatum #651). Schwächer abgedeckt — nur
„läuft durch"-Smoke (test_speicher_dashboard_attribut_bug) — ist der
VORWÄRTS-Pfad. Diese Tests fixieren dessen DETERMINISTISCHE, PVGIS-unabhängige
Teile, bevor die Funktion zerlegt wird:

  - Investitions-Komposition: PV-System-Summe vs. WP-/E-Auto-Mehrkosten-Ansatz
    (max(0, Kosten − Alternativkosten)) vs. Sonstige (volle Kosten).
  - Amortisation: roi_fortschritt = bisherige / gesamt × 100,
    amortisation_erreicht = bisherige ≥ gesamt, sowie das Verhalten der
    Prognose-/Restlaufzeit-Felder im erreicht-Fall.

Geschwister-Dateien (HISTORISCHER Pfad, Symbol get_finanz_prognose):
  - test_aussichten_finanz_aggregat_symmetrie.py
  - test_aussichten_multi_wp.py / _multi_eauto.py
  - test_aussichten_eigenverbrauch_imd_304.py / _bkw_flexpreis_326.py
  - test_aussichten_anschaffungsdatum_grenze_651.py
"""

from __future__ import annotations

from datetime import date

import pytest

from backend.api.routes.aussichten import get_finanz_prognose
from backend.models import Anlage, Investition, Monatsdaten, Strompreis
from backend.models.investition import InvestitionMonatsdaten


async def _anlage_gemischte_investitionen(db) -> int:
    """PV 10000 + Speicher 5000 (= PV-System 15000), WP 12000 (Mehrkosten
    12000−8000=4000), E-Auto 40000 (Mehrkosten 40000−35000=5000), Sonstiges
    1000 → investition_gesamt = 25000.

    Minimaler historischer Monat, damit die Funktion sauber durchläuft."""
    anlage = Anlage(anlagenname="AmortKomposition", leistung_kwp=10.0)
    db.add(anlage)
    await db.flush()

    db.add(Strompreis(
        anlage_id=anlage.id, gueltig_ab=date(2024, 1, 1),
        netzbezug_arbeitspreis_cent_kwh=30.0, einspeiseverguetung_cent_kwh=8.0,
    ))
    db.add(Monatsdaten(anlage_id=anlage.id, jahr=2026, monat=5,
                       einspeisung_kwh=600.0, netzbezug_kwh=0.0))

    pv = Investition(anlage_id=anlage.id, typ="pv-module", bezeichnung="Dach",
                     leistung_kwp=10.0, anschaffungsdatum=date(2024, 1, 1),
                     anschaffungskosten_gesamt=10000.0)
    speicher = Investition(anlage_id=anlage.id, typ="speicher", bezeichnung="Akku",
                           anschaffungsdatum=date(2024, 1, 1),
                           anschaffungskosten_gesamt=5000.0,
                           parameter={"kapazitaet_kwh": 10.0})
    wp = Investition(anlage_id=anlage.id, typ="waermepumpe", bezeichnung="WP",
                     anschaffungsdatum=date(2024, 1, 1),
                     anschaffungskosten_gesamt=12000.0)
    eauto = Investition(anlage_id=anlage.id, typ="e-auto", bezeichnung="EV",
                        anschaffungsdatum=date(2024, 1, 1),
                        anschaffungskosten_gesamt=40000.0)
    sonstiges = Investition(anlage_id=anlage.id, typ="sonstiges", bezeichnung="Div",
                            anschaffungsdatum=date(2024, 1, 1),
                            anschaffungskosten_gesamt=1000.0)
    db.add_all([pv, speicher, wp, eauto, sonstiges])
    await db.flush()

    db.add(InvestitionMonatsdaten(investition_id=pv.id, jahr=2026, monat=5,
        verbrauch_daten={"pv_erzeugung_kwh": 600.0}))
    await db.commit()
    return anlage.id


async def _anlage_pv_only(db, *, anschaffungskosten: float,
                          einspeisung_kwh: float) -> int:
    """Reine PV-Anlage ohne Eigenverbrauch (pv == einspeisung) → keine
    EV-Ersparnis, bisherige Erträge = Einspeise-Erlös = einspeisung × 0,08 €.
    Macht den Amortisations-Quotienten gut nachrechenbar."""
    anlage = Anlage(anlagenname="AmortPVonly", leistung_kwp=10.0)
    db.add(anlage)
    await db.flush()

    db.add(Strompreis(
        anlage_id=anlage.id, gueltig_ab=date(2024, 1, 1),
        netzbezug_arbeitspreis_cent_kwh=30.0, einspeiseverguetung_cent_kwh=8.0,
    ))
    db.add(Monatsdaten(anlage_id=anlage.id, jahr=2026, monat=5,
                       einspeisung_kwh=einspeisung_kwh, netzbezug_kwh=0.0))

    pv = Investition(anlage_id=anlage.id, typ="pv-module", bezeichnung="Dach",
                     leistung_kwp=10.0, anschaffungsdatum=date(2024, 1, 1),
                     anschaffungskosten_gesamt=anschaffungskosten)
    db.add(pv)
    await db.flush()
    db.add(InvestitionMonatsdaten(investition_id=pv.id, jahr=2026, monat=5,
        verbrauch_daten={"pv_erzeugung_kwh": einspeisung_kwh}))
    await db.commit()
    return anlage.id


async def test_investition_komposition_mehrkosten_ansatz(db):
    """PV-System voll, WP/E-Auto nur Mehrkosten, Sonstiges voll.

    Deckt zugleich die Regression ab: das E-Auto im Fixture hat KEINE
    historischen km-Daten — vor dem Fix crashte get_finanz_prognose hier mit
    KeyError 'jahres_ersparnis' (Block setzt den Schlüssel nur bei
    gesamt_km > 0). Siehe test_eauto_ohne_km_kein_crash für den Fokus-Test."""
    anlage_id = await _anlage_gemischte_investitionen(db)
    res = await get_finanz_prognose(anlage_id=anlage_id, monate=12, db=db)

    assert res.investition_pv_system_euro == pytest.approx(15000.0)  # PV + Speicher
    assert res.investition_wp_mehrkosten_euro == pytest.approx(4000.0)   # 12000 − 8000
    assert res.investition_eauto_mehrkosten_euro == pytest.approx(5000.0)  # 40000 − 35000
    assert res.investition_sonstige_euro == pytest.approx(1000.0)
    assert res.investition_gesamt_euro == pytest.approx(25000.0)


async def test_eauto_ohne_km_kein_crash(db):
    """Regression: E-Auto-Investition ohne jegliche historische km-Daten darf
    die Aussichten-Finanzprognose nicht abstürzen lassen (KeyError
    'jahres_ersparnis' → 500). Erwartung: läuft durch, E-Auto-Alternativ-
    Ersparnis = 0."""
    anlage = Anlage(anlagenname="EVohneDaten", leistung_kwp=10.0)
    db.add(anlage)
    await db.flush()
    db.add(Strompreis(
        anlage_id=anlage.id, gueltig_ab=date(2024, 1, 1),
        netzbezug_arbeitspreis_cent_kwh=30.0, einspeiseverguetung_cent_kwh=8.0,
    ))
    pv = Investition(anlage_id=anlage.id, typ="pv-module", bezeichnung="Dach",
                     leistung_kwp=10.0, anschaffungsdatum=date(2024, 1, 1),
                     anschaffungskosten_gesamt=10000.0)
    eauto = Investition(anlage_id=anlage.id, typ="e-auto", bezeichnung="Neuwagen",
                        anschaffungsdatum=date(2024, 1, 1),
                        anschaffungskosten_gesamt=40000.0)
    db.add_all([pv, eauto])
    await db.commit()

    res = await get_finanz_prognose(anlage_id=anlage.id, monate=12, db=db)
    assert res.eauto_alternativ_ersparnis_euro == 0.0


async def test_amortisation_fortschritt_invariante(db):
    """roi_fortschritt == bisherige / gesamt × 100 (auf 1 Nachkommastelle),
    amortisation NICHT erreicht bei kleinen Erträgen vs. großer Investition."""
    anlage_id = await _anlage_pv_only(db, anschaffungskosten=10000.0,
                                      einspeisung_kwh=600.0)
    res = await get_finanz_prognose(anlage_id=anlage_id, monate=12, db=db)

    assert res.investition_gesamt_euro == pytest.approx(10000.0)
    assert res.amortisation_erreicht is False
    erwartet = round(res.bisherige_ertraege_euro / res.investition_gesamt_euro * 100, 1)
    assert res.amortisations_fortschritt_prozent == pytest.approx(erwartet)
    # Sanity: bei 600 kWh × 0,08 € = 48 € Einspeise-Erlös, kein Eigenverbrauch
    assert res.bisherige_ertraege_euro == pytest.approx(48.0, abs=0.5)


async def test_amortisation_erreicht_bei_hohen_ertraegen(db):
    """bisherige ≥ gesamt → erreicht True, Prognose-/Restlaufzeit-Felder None."""
    # Mini-Investition (10 €), hohe Einspeisung → Erträge weit über Kosten.
    anlage_id = await _anlage_pv_only(db, anschaffungskosten=10.0,
                                      einspeisung_kwh=600.0)
    res = await get_finanz_prognose(anlage_id=anlage_id, monate=12, db=db)

    assert res.amortisation_erreicht is True
    assert res.amortisations_fortschritt_prozent > 100.0
    assert res.amortisation_prognose_jahr is None
    assert res.restlaufzeit_bis_amortisation_monate is None
