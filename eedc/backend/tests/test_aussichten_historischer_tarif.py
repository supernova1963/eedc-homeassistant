"""Rückblickende Aussichten-Schleifen rechnen mit dem Tarif DES MONATS.

`get_finanz_prognose` löst zwei Rollen aus derselben Tarif-Tabelle:

- **nach vorn** (Jahres-Hochrechnung, Komponenten-Karten, ausgewiesener
  Tarif der Response) → der HEUTE gültige Preis ist richtig.
- **rückblickend** (`bisherige_eauto_ersparnis`, dienstliche Ladekosten) → es
  gilt der Preis, der im jeweiligen Monat galt.

Bis 2026-07-30 lud der Endpoint die Tarife EINMAL ohne Stichtag
(`lade_tarife_fuer_anlage(db, anlage_id)`) und rechnete auch die Historie mit
dem heutigen Preis. Eine Preiserhöhung schrieb damit die gesamte E-Auto-
Historie um, während die Finanz-Zeilen daneben korrekt je Monat auflösten —
dieselbe Klasse wie der Jahresbericht-Drift (Forum simon42 #89667/60,
[[feedback_aggregations_drift]]).
"""

from __future__ import annotations

from datetime import date

import pytest

from backend.api.routes.aussichten import get_finanz_prognose
from backend.models import (
    Anlage,
    Investition,
    InvestitionMonatsdaten,
    Monatsdaten,
    Strompreis,
)

# Historie: 12 Monate 2025, je 1.000 km und 100 kWh Netzladung.
# Benzin-Vergleich 10 L/100km × 2,00 €/L = 200 €/Monat.
# → Ersparnis/Monat = 200 € − (100 kWh × Arbeitspreis).
NETZ_KWH_PRO_MONAT = 100.0
BENZIN_EURO_PRO_MONAT = 200.0
ALT_PREIS_CENT = 20.0   # galt 2025
NEU_PREIS_CENT = 50.0   # gilt ab 2026


async def _seed_eauto_mit_tarifwechsel(db) -> int:
    anlage = Anlage(anlagenname="TarifHistorie", leistung_kwp=10.0, latitude=48.0)
    db.add(anlage)
    await db.flush()

    # Zwei Tarife mit sauber getrennten Zeiträumen.
    db.add(Strompreis(
        anlage_id=anlage.id,
        gueltig_ab=date(2024, 1, 1), gueltig_bis=date(2025, 12, 31),
        netzbezug_arbeitspreis_cent_kwh=ALT_PREIS_CENT,
        einspeiseverguetung_cent_kwh=8.0,
    ))
    db.add(Strompreis(
        anlage_id=anlage.id,
        gueltig_ab=date(2026, 1, 1),
        netzbezug_arbeitspreis_cent_kwh=NEU_PREIS_CENT,
        einspeiseverguetung_cent_kwh=8.0,
    ))

    # Monatsdaten ohne Energie und ohne Flex-Ø: die Finanz-Zeilen tragen 0 bei,
    # `bisherige_ertraege_euro` besteht damit allein aus der E-Auto-Ersparnis.
    for monat in range(1, 13):
        db.add(Monatsdaten(
            anlage_id=anlage.id, jahr=2025, monat=monat,
            einspeisung_kwh=0.0, netzbezug_kwh=0.0,
        ))

    eauto = Investition(
        anlage_id=anlage.id, typ="e-auto", bezeichnung="Test-EV",
        anschaffungsdatum=date(2024, 1, 1),
        anschaffungskosten_gesamt=30000.0,
        parameter={
            "jahresfahrleistung_km": 12000,
            "verbrauch_kwh_100km": 15,
            "pv_ladeanteil_prozent": 0,
            "vergleich_verbrauch_l_100km": 10.0,
            "benzinpreis_euro": 2.00,
        },
    )
    db.add(eauto)
    await db.flush()

    for monat in range(1, 13):
        db.add(InvestitionMonatsdaten(
            investition_id=eauto.id, jahr=2025, monat=monat,
            verbrauch_daten={
                "km_gefahren": 1000.0,
                "ladung_netz_kwh": NETZ_KWH_PRO_MONAT,
                "ladung_pv_kwh": 0.0,
                "verbrauch_kwh": NETZ_KWH_PRO_MONAT,
            },
        ))

    await db.flush()
    return anlage.id


@pytest.mark.asyncio
async def test_bisherige_eauto_ersparnis_nutzt_den_damaligen_arbeitspreis(db):
    anlage_id = await _seed_eauto_mit_tarifwechsel(db)
    result = await get_finanz_prognose(anlage_id=anlage_id, monate=12, db=db)

    erwartet = 12 * (BENZIN_EURO_PRO_MONAT - NETZ_KWH_PRO_MONAT * ALT_PREIS_CENT / 100)
    mit_heutigem_preis = 12 * (
        BENZIN_EURO_PRO_MONAT - NETZ_KWH_PRO_MONAT * NEU_PREIS_CENT / 100
    )

    assert result.bisherige_ertraege_euro == pytest.approx(erwartet, abs=0.5)
    # Der frühere Wert muss deutlich danebenliegen, sonst prüft der Test nichts.
    assert abs(erwartet - mit_heutigem_preis) > 300


@pytest.mark.asyncio
async def test_ausgewiesener_tarif_bleibt_der_heutige(db):
    """Gegenprobe: die Historisierung darf die Sicht nach vorn nicht umbiegen.

    Der in der Response ausgewiesene Arbeitspreis und die Jahres-Hochrechnung
    beschreiben die Zukunft — dort ist der aktuell gültige Tarif der richtige.
    """
    anlage_id = await _seed_eauto_mit_tarifwechsel(db)
    result = await get_finanz_prognose(anlage_id=anlage_id, monate=12, db=db)

    assert result.netzbezug_preis_cent_kwh == NEU_PREIS_CENT
