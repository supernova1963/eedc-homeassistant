"""DI-5 (= G20-3) — Kennzahlen-Drift-Inventur: der Vorjahres-Vergleichspfad
bildet `gesamtnettoertrag_euro` mit DERSELBEN Zusammensetzung wie der aktuelle
Monat (inkl. WP- und E-Mob-Ersparnis).

Vorher rechnete `_load_vorjahr` `einspeise + ev − netzbezug` OHNE WP/E-Mob,
während der aktuelle Monat `einspeise + ev + wp + emob − netzbezug` bildet
(`aktueller_monat.py`). Das T-Konto-Δ (`TKonto.tsx`) verglich dadurch Äpfel
(Monat mit WP/eMob) mit Birnen (Vorjahr ohne) — ein methodischer Scheinsprung,
sobald WP oder E-Auto existieren.

Symmetrie-Test bei KONSTANTEM Tarif (damit die orthogonale, vorbestehende
Tarif-Stichtags-Frage — der aktuelle Monat nutzt heute-Tarife, das Vorjahr
historische — nicht mit hineinspielt): der Vorjahres-Block für Jahr J muss
denselben `gesamtnettoertrag` liefern wie der aktuelle-Monat-Pfad für J−1.
"""

from __future__ import annotations

from datetime import date

import pytest

from backend.models import (
    Anlage,
    Investition,
    InvestitionMonatsdaten,
    Monatsdaten,
    Strompreis,
)


async def _seed(db) -> int:
    anlage = Anlage(anlagenname="VJ-Symmetrie", leistung_kwp=10.0)
    db.add(anlage)
    await db.flush()

    pv = Investition(anlage_id=anlage.id, typ="pv-module", bezeichnung="PV",
                     anschaffungsdatum=date(2022, 1, 1), aktiv=True)
    wp = Investition(anlage_id=anlage.id, typ="waermepumpe", bezeichnung="WP",
                     anschaffungsdatum=date(2022, 1, 1), aktiv=True, parameter={})
    ea = Investition(anlage_id=anlage.id, typ="e-auto", bezeichnung="Auto",
                     anschaffungsdatum=date(2022, 1, 1), aktiv=True, parameter={})
    db.add_all([pv, wp, ea])
    await db.flush()

    # EIN konstanter Tarif über beide Jahre (kein Stichtags-Effekt)
    db.add(Strompreis(anlage_id=anlage.id, verwendung="allgemein",
                      gueltig_ab=date(2022, 1, 1),
                      netzbezug_arbeitspreis_cent_kwh=30.0,
                      einspeiseverguetung_cent_kwh=8.0))

    for jahr in (2024, 2025):
        db.add(Monatsdaten(anlage_id=anlage.id, jahr=jahr, monat=6,
                           einspeisung_kwh=500, netzbezug_kwh=300,
                           gaspreis_cent_kwh=10.0, kraftstoffpreis_euro=1.75))
        db.add(InvestitionMonatsdaten(
            investition_id=pv.id, jahr=jahr, monat=6,
            verbrauch_daten={"pv_erzeugung_kwh": 1200}))
        db.add(InvestitionMonatsdaten(
            investition_id=wp.id, jahr=jahr, monat=6,
            verbrauch_daten={"heizenergie_kwh": 800, "warmwasser_kwh": 200,
                             "stromverbrauch_kwh": 250}))
        db.add(InvestitionMonatsdaten(
            investition_id=ea.id, jahr=jahr, monat=6,
            verbrauch_daten={"km_gefahren": 1500, "ladung_kwh": 300,
                             "ladung_pv_kwh": 180, "ladung_netz_kwh": 120}))
    await db.commit()
    return anlage.id


async def test_vorjahr_gesamtnetto_symmetrisch_zum_aktuellen_monat(db):
    from backend.api.routes.aktueller_monat import get_aktueller_monat

    anlage_id = await _seed(db)

    r2025 = await get_aktueller_monat(anlage_id=anlage_id, jahr=2025, monat=6, db=db)
    r2024 = await get_aktueller_monat(anlage_id=anlage_id, jahr=2024, monat=6, db=db)

    vj = r2025.vorjahr or {}
    # Komposition vollständig: WP + eMob sind jetzt im Vorjahr enthalten
    assert vj.get("wp_ersparnis_euro") is not None
    assert vj.get("emob_ersparnis_euro") is not None

    # Bei konstantem Tarif == aktueller-Monat-Pfad für 2024
    assert vj.get("gesamtnettoertrag_euro") == pytest.approx(
        r2024.gesamtnettoertrag_euro, abs=0.02
    )
    # ... und die WP-/eMob-Komponenten decken sich
    assert vj.get("wp_ersparnis_euro") == pytest.approx(r2024.wp_ersparnis_euro, abs=0.02)
    assert vj.get("emob_ersparnis_euro") == pytest.approx(r2024.emob_ersparnis_euro, abs=0.02)


async def test_vorjahr_gesamtnetto_formel_ist_summe_der_komponenten(db):
    """gesamtnettoertrag == einspeise + ev + wp + emob − netzbezug (Vorjahr)."""
    from backend.api.routes.aktueller_monat import get_aktueller_monat

    anlage_id = await _seed(db)
    vj = (await get_aktueller_monat(anlage_id=anlage_id, jahr=2025, monat=6, db=db)).vorjahr

    erwartet = round(
        (vj.get("einspeise_erloes_euro") or 0)
        + (vj.get("ev_ersparnis_euro") or 0)
        + (vj.get("wp_ersparnis_euro") or 0)
        + (vj.get("emob_ersparnis_euro") or 0)
        - (vj.get("netzbezug_kosten_euro") or 0),
        2,
    )
    assert vj.get("gesamtnettoertrag_euro") == pytest.approx(erwartet, abs=0.02)


async def test_vorjahr_wp_respektiert_anschaffungsdatum(db):
    """WP-Ersparnis im Vorjahr zählt nur aktive Monate (ist_aktiv_im_monat) —
    Vor-Anschaffungs-Verbrauch fließt NICHT ein."""
    from backend.api.routes.aktueller_monat import get_aktueller_monat

    anlage = Anlage(anlagenname="VJ-WP-Anschaffung", leistung_kwp=10.0)
    db.add(anlage)
    await db.flush()
    wp = Investition(anlage_id=anlage.id, typ="waermepumpe", bezeichnung="WP",
                     anschaffungsdatum=date(2024, 6, 1), aktiv=True, parameter={})
    db.add(wp)
    await db.flush()
    db.add(Strompreis(anlage_id=anlage.id, verwendung="allgemein",
                      gueltig_ab=date(2022, 1, 1),
                      netzbezug_arbeitspreis_cent_kwh=30.0,
                      einspeiseverguetung_cent_kwh=8.0))
    # WP-Verbrauch im Januar 2024 — VOR Anschaffung (Juni 2024)
    db.add(Monatsdaten(anlage_id=anlage.id, jahr=2024, monat=1,
                       einspeisung_kwh=100, netzbezug_kwh=400, gaspreis_cent_kwh=10.0))
    db.add(InvestitionMonatsdaten(
        investition_id=wp.id, jahr=2024, monat=1,
        verbrauch_daten={"heizenergie_kwh": 1000, "warmwasser_kwh": 200,
                         "stromverbrauch_kwh": 320}))
    await db.commit()

    vj = (await get_aktueller_monat(anlage_id=anlage.id, jahr=2025, monat=1, db=db)).vorjahr
    assert vj is not None
    assert vj.get("wp_ersparnis_euro") is None  # inaktiv → keine WP-Ersparnis
