"""B1 (R17/Verlauf-Vergleich): neue Serien im `/aggregiert`-Endpoint + Layer-Split.

- PV-Anlage/BKW-Split partitioniert `summe_pv_bkw_kwh` (Σ-Invariante).
- Endpoint: pv_anlage_kwh + bkw_kwh == pv_erzeugung_kwh.
- §51-Abzug-Volumen je Monat = Σ der Tages-`einspeisung_neg_preis_kwh` (Weg 1),
  gegatet über `Anlage.unterliegt_eeg_51`.
[[feedback_aggregator_symmetrie]], ADR-001.
"""

from __future__ import annotations

from datetime import date

import pytest

from backend.api.routes.monatsdaten import list_monatsdaten_aggregiert
from backend.core.berechnungen import (
    summe_bkw_kwh,
    summe_pv_anlage_kwh,
    summe_pv_bkw_kwh,
)
from backend.models import Anlage, Investition, InvestitionMonatsdaten, Monatsdaten
from backend.models.tages_energie_profil import TagesZusammenfassung


# ── Layer: PV/BKW-Partition (pure) ───────────────────────────────────────────

@pytest.mark.parametrize("komp", [
    {"pv_1": 10.0, "pv_2": 5.0, "bkw_1": 3.0},
    {"pv_1": 10.0, "bkw_1": 3.0, "waermepumpe_1": -4.0, "batterie_1": -2.0},
    {},
    None,
])
def test_pv_bkw_partition_summe(komp):
    """pv_anlage + bkw == pv_bkw für beliebige komponenten_kwh."""
    assert summe_pv_anlage_kwh(komp) + summe_bkw_kwh(komp) == pytest.approx(
        summe_pv_bkw_kwh(komp)
    )


def test_split_trennt_praefixe():
    komp = {"pv_1": 10.0, "bkw_1": 3.0, "bkw_2": 2.0}
    assert summe_pv_anlage_kwh(komp) == pytest.approx(10.0)
    assert summe_bkw_kwh(komp) == pytest.approx(5.0)


# ── Endpoint: PV/BKW-Split ───────────────────────────────────────────────────

async def test_pv_anlage_bkw_split_summiert_auf_pv_erzeugung(db):
    anlage = Anlage(anlagenname="PV+BKW", leistung_kwp=10.0)
    db.add(anlage)
    await db.flush()
    db.add(Monatsdaten(anlage_id=anlage.id, jahr=2026, monat=5,
                       einspeisung_kwh=100.0, netzbezug_kwh=50.0,
                       pv_erzeugung_kwh=800.0))
    pv = Investition(anlage_id=anlage.id, typ="pv-module", bezeichnung="Dach",
                     anschaffungsdatum=date(2024, 1, 1), leistung_kwp=10.0)
    bkw = Investition(anlage_id=anlage.id, typ="balkonkraftwerk", bezeichnung="Balkon",
                      anschaffungsdatum=date(2024, 1, 1))
    db.add_all([pv, bkw])
    await db.flush()
    db.add(InvestitionMonatsdaten(investition_id=bkw.id, jahr=2026, monat=5,
                                  verbrauch_daten={"pv_erzeugung_kwh": 120.0}))
    await db.commit()

    rows = await list_monatsdaten_aggregiert(anlage_id=anlage.id, jahr=2026, db=db)
    mai = next(r for r in rows if r.monat == 5)
    assert mai.bkw_kwh == pytest.approx(120.0)
    # Partition: pv_anlage + bkw == pv_erzeugung (Gesamt)
    assert mai.pv_anlage_kwh + mai.bkw_kwh == pytest.approx(mai.pv_erzeugung_kwh)


# ── Endpoint: §51-Abzug-Volumen je Monat (Weg 1) ─────────────────────────────

async def _anlage_51(db, *, unterliegt: bool) -> int:
    anlage = Anlage(anlagenname="§51", leistung_kwp=10.0, unterliegt_eeg_51=unterliegt)
    db.add(anlage)
    await db.flush()
    db.add(Monatsdaten(anlage_id=anlage.id, jahr=2026, monat=5,
                       einspeisung_kwh=100.0, netzbezug_kwh=50.0))
    # Zwei Tage im Mai mit Einspeisung bei negativem Börsenpreis (Tages-Summary).
    db.add_all([
        TagesZusammenfassung(anlage_id=anlage.id, datum=date(2026, 5, 10),
                             einspeisung_neg_preis_kwh=4.0),
        TagesZusammenfassung(anlage_id=anlage.id, datum=date(2026, 5, 20),
                             einspeisung_neg_preis_kwh=6.0),
    ])
    await db.commit()
    return anlage.id


async def test_par51_monat_ist_summe_der_tage(db):
    anlage_id = await _anlage_51(db, unterliegt=True)
    rows = await list_monatsdaten_aggregiert(anlage_id=anlage_id, jahr=2026, db=db)
    mai = next(r for r in rows if r.monat == 5)
    assert mai.einspeisung_neg_preis_kwh == pytest.approx(10.0)


async def test_par51_none_wenn_anlage_nicht_unterliegt(db):
    anlage_id = await _anlage_51(db, unterliegt=False)
    rows = await list_monatsdaten_aggregiert(anlage_id=anlage_id, jahr=2026, db=db)
    mai = next(r for r in rows if r.monat == 5)
    assert mai.einspeisung_neg_preis_kwh is None
