"""§51 EEG-Abzug in der Cockpit-Übersicht (rcmcronny Discussion #120).

Hintergrund: Solarpaket I hat für Neuanlagen den Vergütungsausfall in
Negativpreis-Stunden eingeführt. Daten-Fundament steht in
`TagesZusammenfassung.einspeisung_neg_preis_kwh` (aus dem Strompreis-
Mitschrift-Feature); jetzt in die Erlös-Berechnung des Cockpit-
Endpoints angeschlossen — analog zu allen weiteren Erlös-Read-Sites
über den Helper `core.berechnungen.einspeise_erloes_euro`.

§51 ist ein bewusst MANUELLER Schalter pro Anlage (`Anlage.unterliegt_eeg_51`,
Default False) — der Abzug gilt rechtlich nur für Neuanlagen ab Solarpaket I.

Tests sichern:
- Anlage mit §51-Flag, OHNE Tages-Aggregate → `nicht_vergueteter_erloes_euro`
  ist `None`, `einspeise_erloes_euro` unverändert (Σ × Vergütung).
- Anlage mit §51-Flag, MIT Tages-Aggregaten → `einspeise_erloes_euro` ist um
  `einspeisung_neg_preis_kwh × Vergütung` reduziert; KPI-Felder exponiert.
- Anlage OHNE §51-Flag (Bestandsanlage, Default), MIT Tages-Aggregaten →
  KEIN Abzug, KPI-Felder bleiben `None` (Gernot/rapahl: §51 ist Anlagen-
  abhängig, nicht „greift immer wo Börsenpreis-Daten existieren").
"""

from __future__ import annotations

from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.routes.cockpit.uebersicht import get_cockpit_uebersicht
from backend.models import Anlage, Monatsdaten
from backend.models.strompreis import Strompreis
from backend.models.tages_energie_profil import TagesZusammenfassung


async def _seed_minimal(
    db: AsyncSession,
    *,
    einspeisung_kwh: float,
    verguetung_ct: float = 8.2,
    unterliegt_eeg_51: bool = False,
) -> int:
    """Anlage mit einem Monat (April 2026) + Strompreis."""
    anlage = Anlage(
        anlagenname="Test", leistung_kwp=10.0, standort_land="DE",
        unterliegt_eeg_51=unterliegt_eeg_51,
    )
    db.add(anlage)
    await db.flush()
    db.add(Strompreis(
        anlage_id=anlage.id, verwendung="allgemein",
        gueltig_ab=date(2024, 1, 1),
        netzbezug_arbeitspreis_cent_kwh=30.0,
        einspeiseverguetung_cent_kwh=verguetung_ct,
    ))
    db.add(Monatsdaten(
        anlage_id=anlage.id, jahr=2026, monat=4,
        netzbezug_kwh=100.0, einspeisung_kwh=einspeisung_kwh,
    ))
    return anlage.id


async def test_ohne_tages_aggregate_keine_kpi_alte_berechnung(db):
    """Standalone-/Wizard-User (keine Strompreis-Mitschrift) bleibt unverändert."""
    anlage_id = await _seed_minimal(db, einspeisung_kwh=1000.0, unterliegt_eeg_51=True)
    await db.commit()

    resp = await get_cockpit_uebersicht(anlage_id=anlage_id, jahr=2026, db=db)

    # KPI-Felder bleiben None — Frontend rendert den §51-Eintrag nicht.
    assert resp.einspeise_neg_preis_kwh is None
    assert resp.nicht_vergueteter_erloes_euro is None
    # Alte Berechnung: voller Erlös = 1000 × 8.2 / 100 = 82 €.
    assert resp.einspeise_erloes_euro == 82.0


async def test_mit_tages_aggregaten_abzug_und_kpi_exponiert(db):
    """Anwender mit Strompreis-Sensor + §51-Flag: Abzug greift, KPI-Felder gefüllt."""
    anlage_id = await _seed_minimal(db, einspeisung_kwh=1000.0, unterliegt_eeg_51=True)
    # 120 kWh wurden bei negativem Börsenpreis eingespeist (zwei Tage im April).
    db.add(TagesZusammenfassung(
        anlage_id=anlage_id, datum=date(2026, 4, 10),
        einspeisung_neg_preis_kwh=70.0,
    ))
    db.add(TagesZusammenfassung(
        anlage_id=anlage_id, datum=date(2026, 4, 21),
        einspeisung_neg_preis_kwh=50.0,
    ))
    await db.commit()

    resp = await get_cockpit_uebersicht(anlage_id=anlage_id, jahr=2026, db=db)

    # KPI-Felder sind jetzt befüllt.
    assert resp.einspeise_neg_preis_kwh == 120.0
    assert resp.nicht_vergueteter_erloes_euro == round(120 * 8.2 / 100, 2)
    # Erlös ist um den §51-Anteil reduziert.
    assert resp.einspeise_erloes_euro == round((1000 - 120) * 8.2 / 100, 2)


async def test_mit_tages_aggregaten_aber_null_negativpreis_zeigt_null(db):
    """Anwender mit Sensor, aber keine Negativpreis-Stunde im Zeitraum.

    KPI-Felder werden 0.0 (statt None) — eine echte Aussage „kein Verlust",
    Anwender sieht: „Strompreis-Mitschrift greift, war aber nicht
    teuer für mich". Erlös bleibt unverändert.
    """
    anlage_id = await _seed_minimal(db, einspeisung_kwh=1000.0, unterliegt_eeg_51=True)
    db.add(TagesZusammenfassung(
        anlage_id=anlage_id, datum=date(2026, 4, 10),
        einspeisung_neg_preis_kwh=0.0,
    ))
    await db.commit()

    resp = await get_cockpit_uebersicht(anlage_id=anlage_id, jahr=2026, db=db)

    assert resp.einspeise_neg_preis_kwh == 0.0
    assert resp.nicht_vergueteter_erloes_euro == 0.0
    assert resp.einspeise_erloes_euro == 82.0


async def test_ohne_eeg51_flag_kein_abzug_trotz_tages_aggregaten(db):
    """Bestandsanlage ohne §51-Flag (Default): KEIN Abzug, auch mit Börsenpreis-Daten.

    Genau der von Gernot/rapahl gemeldete Fall: Der aWATTar-Börsenpreis-Fallback
    füllt `einspeisung_neg_preis_kwh` für fast jede Anlage — der §51-Abzug darf
    aber nur greifen, wenn die Anlage rechtlich betroffen ist (manueller Schalter).
    """
    anlage_id = await _seed_minimal(db, einspeisung_kwh=1000.0, unterliegt_eeg_51=False)
    db.add(TagesZusammenfassung(
        anlage_id=anlage_id, datum=date(2026, 4, 10),
        einspeisung_neg_preis_kwh=70.0,
    ))
    await db.commit()

    resp = await get_cockpit_uebersicht(anlage_id=anlage_id, jahr=2026, db=db)

    # Flag aus → §51 wird ignoriert: KPI bleibt None, voller Erlös.
    assert resp.einspeise_neg_preis_kwh is None
    assert resp.nicht_vergueteter_erloes_euro is None
    assert resp.einspeise_erloes_euro == 82.0


# ── Monats-Endpoint: derselbe Ausweis, damit das T-Konto den Abzug zeigen kann ──


async def test_monats_endpoint_exponiert_51_abzug(db):
    """`/aktueller-monat` gibt Abzugsvolumen + entgangenen Erlös mit aus.

    Bis v4.0.0 rechnete der Endpoint den Abzug zwar (der Erlös war gekürzt),
    warf die Diagnose-Werte aber weg — das T-Konto zeigte deshalb als Herleitung
    die volle Einspeisung, und der im Anlage-Formular versprochene Ausweis des
    „§51-Verlusts" existierte nirgends.
    """
    from backend.api.routes.aktueller_monat import get_aktueller_monat

    anlage_id = await _seed_minimal(db, einspeisung_kwh=1000.0, unterliegt_eeg_51=True)
    db.add(TagesZusammenfassung(
        anlage_id=anlage_id, datum=date(2026, 4, 10),
        einspeisung_neg_preis_kwh=120.0,
    ))
    await db.commit()

    resp = await get_aktueller_monat(anlage_id=anlage_id, jahr=2026, monat=4, db=db)

    assert resp.einspeisung_neg_preis_kwh == 120.0
    assert resp.nicht_vergueteter_erloes_euro == round(120 * 8.2 / 100, 2)
    assert resp.einspeise_erloes_euro == round((1000 - 120) * 8.2 / 100, 2)


async def test_monats_endpoint_ohne_eeg51_flag_keine_diagnose(db):
    """Ohne §51-Flag bleiben die Felder None — die Kachel erscheint gar nicht."""
    from backend.api.routes.aktueller_monat import get_aktueller_monat

    anlage_id = await _seed_minimal(db, einspeisung_kwh=1000.0, unterliegt_eeg_51=False)
    db.add(TagesZusammenfassung(
        anlage_id=anlage_id, datum=date(2026, 4, 10),
        einspeisung_neg_preis_kwh=120.0,
    ))
    await db.commit()

    resp = await get_aktueller_monat(anlage_id=anlage_id, jahr=2026, monat=4, db=db)

    assert resp.einspeisung_neg_preis_kwh is None
    assert resp.nicht_vergueteter_erloes_euro is None
    assert resp.einspeise_erloes_euro == 82.0
