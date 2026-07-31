"""`GET /monatsdaten/{id}` löst den Tarif über den SoT-Helper auf.

Der Endpoint baute seine Tarif-Query von Hand und ließ dabei zwei Bedingungen
weg, die `lade_tarife_fuer_anlage` mitbringt:

- **kein `gueltig_bis`** → ein beendeter Tarif galt weiter.
- **kein `verwendung`-Filter** → über `ORDER BY gueltig_ab DESC` gewann ein
  später angelegter WP-/Wallbox-**Spezialtarif** den Platz des allgemeinen und
  wurde zum Arbeitspreis der ganzen Anlage.

Beides ist genau die Klasse, die ADR-002/P3-a für Kennwerte beschreibt: die
Rohquelle statt des SoT-Helpers zu lesen (Forum simon42 #89667/60).
"""

from __future__ import annotations

from datetime import date

import pytest

from backend.api.routes.monatsdaten import get_monatsdaten
from backend.models import Anlage, Monatsdaten, Strompreis


async def _anlage_mit_monat(db) -> tuple[int, int]:
    anlage = Anlage(anlagenname="TarifAufloesung", leistung_kwp=10.0)
    db.add(anlage)
    await db.flush()
    md = Monatsdaten(
        anlage_id=anlage.id, jahr=2025, monat=6,
        einspeisung_kwh=100.0, netzbezug_kwh=200.0,
    )
    db.add(md)
    await db.flush()
    return anlage.id, md.id


@pytest.mark.asyncio
async def test_wp_spezialtarif_verdraengt_den_allgemeinen_nicht(db):
    """Der WP-Tarif ist teurer und jünger — er darf die Anlage nicht umrechnen."""
    anlage_id, md_id = await _anlage_mit_monat(db)
    db.add(Strompreis(
        anlage_id=anlage_id, gueltig_ab=date(2024, 1, 1),
        netzbezug_arbeitspreis_cent_kwh=30.0, einspeiseverguetung_cent_kwh=8.0,
        verwendung="allgemein",
    ))
    db.add(Strompreis(
        anlage_id=anlage_id, gueltig_ab=date(2025, 1, 1),
        netzbezug_arbeitspreis_cent_kwh=22.0, einspeiseverguetung_cent_kwh=8.0,
        verwendung="waermepumpe",
    ))
    await db.flush()

    response = await get_monatsdaten(monatsdaten_id=md_id, db=db)

    # 200 kWh × 30 ct = 60 € — mit dem WP-Tarif wären es 44 €.
    assert response.kennzahlen.netzbezug_kosten_euro == pytest.approx(60.0, abs=0.01)


@pytest.mark.asyncio
async def test_beendeter_tarif_gilt_nicht_weiter(db):
    """Läuft ein Tarif vor dem Monat aus und existiert kein Nachfolger,
    rechnet eedc mit der Vorbelegung — nicht mit dem abgelaufenen Preis."""
    anlage_id, md_id = await _anlage_mit_monat(db)
    db.add(Strompreis(
        anlage_id=anlage_id,
        gueltig_ab=date(2024, 1, 1), gueltig_bis=date(2024, 12, 31),
        netzbezug_arbeitspreis_cent_kwh=15.0, einspeiseverguetung_cent_kwh=8.0,
    ))
    await db.flush()

    response = await get_monatsdaten(monatsdaten_id=md_id, db=db)

    # Vorbelegung 30 ct (NETZBEZUG_DEFAULT_CENT) statt der abgelaufenen 15 ct.
    assert response.kennzahlen.netzbezug_kosten_euro == pytest.approx(60.0, abs=0.01)


@pytest.mark.asyncio
async def test_flex_durchschnittspreis_schlaegt_den_tarif(db):
    """Der abgerechnete Monats-Ø hat Vorrang — wie in allen anderen Sichten."""
    anlage_id, md_id = await _anlage_mit_monat(db)
    db.add(Strompreis(
        anlage_id=anlage_id, gueltig_ab=date(2024, 1, 1),
        netzbezug_arbeitspreis_cent_kwh=30.0, einspeiseverguetung_cent_kwh=8.0,
    ))
    md = await db.get(Monatsdaten, md_id)
    md.netzbezug_durchschnittspreis_cent = 18.0
    await db.flush()

    response = await get_monatsdaten(monatsdaten_id=md_id, db=db)

    assert response.kennzahlen.netzbezug_kosten_euro == pytest.approx(36.0, abs=0.01)
