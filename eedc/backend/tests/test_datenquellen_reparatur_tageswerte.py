"""
Reproduktion des Forum-Nachlaufs zu v4.0.3 — heilt die Reparatur die Tageswerte?

Ausgangslage der Melder (pipp086 Forum #44, coolxmad #353): die Zuordnung wurde ab
v4.0.0 in der Datenquellen-Fläche gemacht und landete NUR in `sensor_mapping.quellen`.
v4.0.3 schreibt sie zusätzlich in die klassische Struktur und zieht Bestände per
Boot-Reparatur nach (`migrate_quellen_ins_mapping`).

Diese Datei prüft die Kette danach **end-to-end auf Aggregations-Ebene**, für beide
Lesepfade, die Cockpit/Tag speisen:

  LTS      — `get_hourly_kwh_by_category_lts` (HA-Add-on: der Pfad für HEUTE, weil
             der Snapshot-Fallback bewusst an `datum < today` hängt)
  Snapshot — `get_hourly_kwh_by_category` (vergangene Tage / MQTT-Pfad)

Kern-Aussage je Test: **vor** der Reparatur liefern beide Pfade für die Basis-Zähler
nichts (das war der Befund), **nach** der Reparatur die vollen Werte — ohne dass der
Anwender etwas neu zuordnet. Damit ist belegbar, ob ein Restbefund am Aggregator
liegt oder außerhalb (Sensor ohne `sum`-Spalte, Reparatur noch nicht gelaufen).
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import select

from backend.models.anlage import Anlage
from backend.models.investition import Investition
from backend.models.sensor_snapshot import SensorSnapshot
from backend.services.migrations.migrate_quellen_ins_mapping import (
    migriere_quellen_ins_mapping,
)
from backend.services.snapshot.aggregator import get_hourly_kwh_by_category
from backend.services.snapshot.lts_aggregator import get_hourly_kwh_by_category_lts

DATUM = date(2026, 7, 28)

# Sensoren wie im Forum-Fall: zwei Basis-Zähler eines Smartmeter-Readers + ein
# PV-String-Zähler (der bei pipp086 als einziger durchkam).
EID_EINSP = "sensor.smartmeter_e_out"
EID_BEZUG = "sensor.smartmeter_e_in"
EID_PV = "sensor.pv_ertrag"

# Ein voller Tag: PV 24 kWh, Einspeisung 12 kWh, Netzbezug 2,4 kWh.
DELTAS = {
    EID_PV: {h: 1.0 for h in range(24)},
    EID_EINSP: {h: 0.5 for h in range(24)},
    EID_BEZUG: {h: 0.1 for h in range(24)},
}

# v4.0.2-Zustand: die Zuordnung steht AUSSCHLIESSLICH im Store.
QUELLEN_ONLY = {
    "quellen": {
        "basis_energy_einspeisung_kwh": {"quelle": "ha_app", "entity_id": EID_EINSP},
        "basis_energy_netzbezug_kwh": {"quelle": "ha_app", "entity_id": EID_BEZUG},
        "inv_energy_3_pv_erzeugung_kwh": {"quelle": "ha_app", "entity_id": EID_PV},
    },
}


def _invs() -> dict:
    return {"3": _mit_lebenszyklus(SimpleNamespace(
        id=3, anlage_id=1, typ="pv-module", parameter={},
        parent_investition_id=None,
    ))}

def _mit_lebenszyklus(ns):
    """Gibt der Attrappe die Lebenszyklus-Felder + die ECHTE `ist_aktiv_an`.

    Seit #406 filtert `pv_tages_praezedenz.erwartete_erzeuger_ids` die Erzeuger
    am Stichtag — ein stillgelegter String darf die Anlagensumme nicht dauerhaft
    auf das Aggregat zwingen. Die Methode wird vom Modell **gebunden** statt
    nachgebaut: ein `lambda: True` hätte genau die Lücke verdeckt, für die der
    Filter da ist, und eine Kopie der drei Regeln wäre die F-56-Klasse.
    """
    from backend.models.investition import Investition

    ns.aktiv = True
    ns.anschaffungsdatum = None
    ns.stilllegungsdatum = None
    ns.ist_aktiv_an = Investition.ist_aktiv_an.__get__(ns)
    return ns



def _mock_ha_svc() -> MagicMock:
    svc = MagicMock()
    svc.is_available = True
    svc.get_hourly_kwh_deltas_for_day.side_effect = lambda ids, _d: {
        eid: DELTAS[eid] for eid in ids if eid in DELTAS
    }
    return svc


def _summe(hourly: dict, feld: str) -> float:
    return round(sum((h.get(feld) or 0.0) for h in hourly.values()), 3)


async def _seed_anlage(db) -> Anlage:
    """Anlage im v4.0.2-Zustand: Zuordnung nur im Store, `basis` leer."""
    anlage = Anlage(anlagenname="Forum-Fall", leistung_kwp=10.0,
                    sensor_mapping=dict(QUELLEN_ONLY))
    db.add(anlage)
    await db.flush()
    db.add(Investition(
        anlage_id=anlage.id, typ="pv-module", bezeichnung="Süd",
        leistung_kwp=10.0, anschaffungsdatum=date(2024, 1, 1), aktiv=True,
    ))
    await db.commit()
    return anlage


# ─── LTS-Pfad (HA-Add-on; der Pfad für HEUTE) ───────────────────────────────

@pytest.mark.asyncio
async def test_lts_pfad_liefert_basis_zaehler_erst_nach_der_reparatur(db):
    anlage = await _seed_anlage(db)

    with patch(
        "backend.services.snapshot.lts_aggregator.get_ha_statistics_service",
        return_value=_mock_ha_svc(),
    ):
        vorher = await get_hourly_kwh_by_category_lts(db, anlage, _invs(), DATUM)

    # Vor der Reparatur zählt der Aggregator NICHTS auf — auch die PV nicht.
    # Wichtig für die Melder-Diagnose: „PV da, Basis 0" kann also NICHT
    # bedeuten, dass die Reparatur nicht gelaufen ist. Dann läge alles brach.
    assert vorher == {}

    await migriere_quellen_ins_mapping(db)
    await db.commit()
    anlage = (await db.execute(
        select(Anlage).where(Anlage.id == anlage.id)
    )).scalar_one()

    with patch(
        "backend.services.snapshot.lts_aggregator.get_ha_statistics_service",
        return_value=_mock_ha_svc(),
    ):
        nachher = await get_hourly_kwh_by_category_lts(db, anlage, _invs(), DATUM)

    assert _summe(nachher, "einspeisung") == 12.0
    assert _summe(nachher, "netzbezug") == 2.4
    assert _summe(nachher, "pv") == 24.0
    # Bilanz-Verbrauch braucht alle drei — vorher unmöglich, jetzt vollständig.
    assert _summe(nachher, "verbrauch") > 0


# ─── Snapshot-Pfad (vergangene Tage / MQTT) ─────────────────────────────────

async def _seed_snapshots(db, anlage_id: int) -> None:
    """Zählerstände an allen 25 Stundengrenzen — wie der Snapshot-Writer sie
    schreibt (er honoriert den Store schon seit v4.0.0, deshalb liegen die
    Rohwerte auch bei den Meldern vor)."""
    start = datetime.combine(DATUM, datetime.min.time()) - timedelta(hours=1)
    for key, schritt in (
        ("basis:einspeisung", 0.5),
        ("basis:netzbezug", 0.1),
        ("inv:3:pv_erzeugung_kwh", 1.0),
    ):
        for i in range(26):
            db.add(SensorSnapshot(
                anlage_id=anlage_id, sensor_key=key,
                zeitpunkt=start + timedelta(hours=i), wert_kwh=100.0 + i * schritt,
                quelle="ha_statistics",
            ))
    await db.commit()


@pytest.mark.asyncio
async def test_snapshot_pfad_liefert_basis_zaehler_erst_nach_der_reparatur(db):
    anlage = await _seed_anlage(db)
    await _seed_snapshots(db, anlage.id)

    vorher = await get_hourly_kwh_by_category(
        db=db, anlage=anlage, investitionen_by_id=_invs(), datum=DATUM,
    )
    # Die Snapshots liegen vor (der Writer honoriert den Store seit v4.0.0) —
    # aufgezählt wird trotzdem nichts, weil die Aufzählung an `basis`/
    # `investitionen` hängt. Genau das war der v4.0.3-Befund.
    assert vorher == {}

    await migriere_quellen_ins_mapping(db)
    await db.commit()
    anlage = (await db.execute(
        select(Anlage).where(Anlage.id == anlage.id)
    )).scalar_one()

    nachher = await get_hourly_kwh_by_category(
        db=db, anlage=anlage, investitionen_by_id=_invs(), datum=DATUM,
    )
    assert _summe(nachher, "einspeisung") == 12.0
    assert _summe(nachher, "netzbezug") == 2.4


# ─── Abgrenzung: was die Reparatur NICHT heilen kann ────────────────────────

@pytest.mark.asyncio
async def test_zaehler_ohne_summen_spalte_bleibt_leer_trotz_reparatur(db):
    """**Das ist pipp086s Bild** (Forum #44): PV im Tag da, Basis-Zähler auf 0.

    Liefert HA für einen Zähler keine `sum`-Spalte (`state_class: measurement`
    statt `total_increasing`), überspringt `get_hourly_kwh_deltas_for_day` jede
    Zeile dieses Sensors — der Sensor fehlt im Ergebnis, der Tag bleibt leer.
    Die Reparatur ändert daran nichts, ein Reaggregations-Lauf auch nicht.

    Anders als „Reparatur nicht gelaufen" (dort wäre ALLES leer, s. o.) trifft
    dieser Fall genau einzelne Sensoren — und erklärt damit die Asymmetrie.
    """
    anlage = await _seed_anlage(db)
    await migriere_quellen_ins_mapping(db)
    await db.commit()
    anlage = (await db.execute(
        select(Anlage).where(Anlage.id == anlage.id)
    )).scalar_one()

    svc = MagicMock()
    svc.is_available = True
    # HA kennt nur den PV-Sensor — die beiden Zähler fehlen in der Statistik.
    svc.get_hourly_kwh_deltas_for_day.side_effect = lambda ids, _d: {
        eid: DELTAS[eid] for eid in ids if eid == EID_PV
    }
    with patch(
        "backend.services.snapshot.lts_aggregator.get_ha_statistics_service",
        return_value=svc,
    ):
        hourly = await get_hourly_kwh_by_category_lts(db, anlage, _invs(), DATUM)

    assert _summe(hourly, "pv") == 24.0
    assert _summe(hourly, "einspeisung") == 0.0
    assert _summe(hourly, "netzbezug") == 0.0
