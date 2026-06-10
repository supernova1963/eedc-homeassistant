"""Aussichten: BKW-Ersparnis bei Flex-Tarif per-Monat — #326 (Restposten).

Der #326-Sweep (f6208686 + 7439d7d6) zog Cockpit, Jahresbericht-PDF und
HA-Export auf per-Monat-Flexpreise; die BKW-Zeile in `get_finanz_prognose`
rechnete weiter `Σ(eigenverbrauch_m) × statischer Tarifpreis`. Die E-Auto-
Schleife direkt darüber nutzt `resolve_netzbezug_preis_cent` längst per-Monat —
bei Flex-Tarifen (Tibber/aWATTar/EPEX) drifteten BKW-Anlagen dadurch in den
Aussichten gegen das Cockpit ([[feedback_aggregations_drift]]).

Fix: BKW-Ersparnis pro Monat über `resolve_netzbezug_preis_cent(md, fallback)`
— dasselbe Muster wie die E-Auto-Zeile.
"""

from __future__ import annotations

from datetime import date

import pytest

from backend.api.routes.aussichten import get_finanz_prognose
from backend.core.wirtschaftlichkeit_defaults import NETZBEZUG_DEFAULT_CENT
from backend.models import Anlage, Investition, Monatsdaten
from backend.models.investition import InvestitionMonatsdaten


async def _anlage_mit_bkw(db) -> int:
    """Reine BKW-Anlage (keine PV-Module, keine Einspeisung) mit zwei Monaten
    gegenläufiger Flexpreis-/EV-Charakteristik — so ist `bisherige_ertraege_euro`
    exakt die BKW-Ersparnis und per-Monat vs. statisch klar unterscheidbar."""
    anlage = Anlage(anlagenname="BKW-Flex326", leistung_kwp=0.8)
    db.add(anlage)
    await db.flush()

    # Mai: viel BKW-EV, NIEDRIGER Flexpreis 20 ct
    db.add(Monatsdaten(anlage_id=anlage.id, jahr=2026, monat=5,
                       netzbezug_kwh=100.0, netzbezug_durchschnittspreis_cent=20.0))
    # Dez: wenig BKW-EV, HOHER Flexpreis 40 ct
    db.add(Monatsdaten(anlage_id=anlage.id, jahr=2026, monat=12,
                       netzbezug_kwh=300.0, netzbezug_durchschnittspreis_cent=40.0))

    bkw = Investition(
        anlage_id=anlage.id, typ="balkonkraftwerk", bezeichnung="BKW Süd",
        anschaffungsdatum=date(2024, 1, 1), anschaffungskosten_gesamt=600.0,
    )
    db.add(bkw)
    await db.flush()
    db.add(InvestitionMonatsdaten(investition_id=bkw.id, jahr=2026, monat=5,
                                  verbrauch_daten={"eigenverbrauch_kwh": 200.0}))
    db.add(InvestitionMonatsdaten(investition_id=bkw.id, jahr=2026, monat=12,
                                  verbrauch_daten={"eigenverbrauch_kwh": 100.0}))
    await db.commit()
    return anlage.id


async def test_bkw_ersparnis_per_monat_flexpreis(db):
    """BKW-Ersparnis = Σ(eigenverbrauch_m × flexpreis_m), NICHT × Tarif-Default.

    Korrekt (per-Monat):  200·0,20 + 100·0,40 = 40 + 40 = 80,00 €
    Alt/buggy (statisch): 300 kWh · 0,30 (NETZBEZUG_DEFAULT_CENT) = 90,00 €
    """
    anlage_id = await _anlage_mit_bkw(db)
    res = await get_finanz_prognose(anlage_id=anlage_id, monate=12, db=db)

    assert res.bisherige_ertraege_euro == pytest.approx(80.0, abs=0.01)
    # Gegenprobe: nicht der statische Default-Preis-Wert.
    statisch_alt = 300.0 * NETZBEZUG_DEFAULT_CENT / 100
    assert abs(res.bisherige_ertraege_euro - statisch_alt) > 5.0


async def test_bkw_ersparnis_fallback_ohne_flexpreis(db):
    """Monate OHNE Flexpreis-Mitschrift fallen auf den Tarifpreis zurück —
    der Fix darf Fix-Tarif-Anlagen nicht verändern."""
    anlage = Anlage(anlagenname="BKW-Fix326", leistung_kwp=0.8)
    db.add(anlage)
    await db.flush()
    db.add(Monatsdaten(anlage_id=anlage.id, jahr=2026, monat=5, netzbezug_kwh=100.0))
    bkw = Investition(
        anlage_id=anlage.id, typ="balkonkraftwerk", bezeichnung="BKW",
        anschaffungsdatum=date(2024, 1, 1), anschaffungskosten_gesamt=600.0,
    )
    db.add(bkw)
    await db.flush()
    db.add(InvestitionMonatsdaten(investition_id=bkw.id, jahr=2026, monat=5,
                                  verbrauch_daten={"eigenverbrauch_kwh": 200.0}))
    await db.commit()

    res = await get_finanz_prognose(anlage_id=anlage.id, monate=12, db=db)
    assert res.bisherige_ertraege_euro == pytest.approx(
        200.0 * NETZBEZUG_DEFAULT_CENT / 100, abs=0.01
    )
