"""Regression #299: Aggregator-Preserve-Restore mit Audit-Spur.

Befund (Tier-4 Diagnose-Hygiene): Der Delete-and-Recreate-Pfad in
`aggregate_day` rettet extern-additiv befüllte TZ-Felder (Prognose-Felder
vom Wetter-Endpoint, `kraftstoffpreis_euro` vom Kraftstoff-Service) und
schrieb sie vor dem Fix direkt per `setattr` auf die frische Row zurück —
ohne `write_with_provenance`. Folge:

1. Im `data_provenance_log` fehlten die Restore-Operationen komplett, das
   Audit-Log war für die Frage „wer hat diesen Wert zuletzt geschrieben —
   Wetter-Service oder Aggregator-Restore?" nicht eindeutig lesbar.
2. `seed_tz_provenance` lief NACH dem setattr und stempelte die nun
   non-None Prognose-/Kraftstoff-Felder mit `auto:monatsabschluss` — die
   Provenance log also fälschlich „vom Aggregator berechnet".

Fix: Restore läuft jetzt NACH `seed_tz_provenance` über
`write_with_provenance`. Die Felder sind beim Seed noch None (frische Row),
der Restore schreibt sie mit ihrer ursprünglichen Quelle (aus der alten
Row-Provenance) bzw. dem Fallback-Label `auto:preserve_restore`, und es
entsteht pro Restore ein Audit-Log-Eintrag.

Kein Funktions-/Wert-Bug: die geretteten Werte sind identisch, nur die
Audit-Spur kommt hinzu.
"""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select

from backend.models.anlage import Anlage
from backend.models.data_provenance_log import DataProvenanceLog
from backend.models.mqtt_energy_snapshot import MqttEnergySnapshot
from backend.models.tages_energie_profil import TagesZusammenfassung
from backend.services.energie_profil.source import Source


async def _mqtt_anchor(db, anlage_id: int, datum: date) -> None:
    """24h-Anker, damit `aggregate_day` den synthetischen Pfad nimmt statt
    früh `return None` (analog test_aggregator_290_preserve)."""
    db.add(MqttEnergySnapshot(
        anlage_id=anlage_id,
        timestamp=datetime.combine(datum, datetime.min.time()) - timedelta(hours=1),
        energy_key="netzbezug",
        value_kwh=100.0,
    ))
    await db.flush()


@pytest.mark.asyncio
async def test_restore_schreibt_audit_log_und_erhaelt_werte(db) -> None:
    """Nach Reaggregation eines Tages mit zuvor gesetzten Prognose-/Kraftstoff-
    Feldern: (a) Werte unverändert erhalten UND (b) `data_provenance_log`
    enthält die Restore-Einträge mit der jeweils richtigen Quelle."""
    from backend.services.energie_profil.aggregator import aggregate_day

    anlage = Anlage(
        anlagenname="Test #299",
        leistung_kwp=10.0,
        standort_plz="10115",
        standort_land="DE",
        wechselrichter_hersteller="generic",
        sensor_mapping={},
    )
    db.add(anlage)
    await db.flush()

    gestern = date.today() - timedelta(days=1)
    # Alte TZ mit extern-befüllten Feldern + Provenance für zwei davon.
    # `solcast_prognose_kwh` bewusst OHNE Provenance-Eintrag → Fallback-Label.
    alte_tz = TagesZusammenfassung(
        anlage_id=anlage.id,
        datum=gestern,
        stunden_verfuegbar=24,
        datenquelle="ha_statistiken",
        pv_prognose_kwh=12.5,
        kraftstoffpreis_euro=1.789,
        solcast_prognose_kwh=11.0,
        source_provenance={
            "pv_prognose_kwh": {"source": "external:openmeteo", "writer": "wetter"},
            "kraftstoffpreis_euro": {"source": "external:fuel_price", "writer": "fuel"},
        },
    )
    db.add(alte_tz)
    await _mqtt_anchor(db, anlage.id, gestern)
    await db.commit()

    with patch(
        "backend.services.live_power_service.LivePowerService.get_tagesverlauf",
        new=AsyncMock(return_value={"serien": [], "punkte": []}),
    ), patch(
        "backend.services.snapshot.aggregator.get_komponenten_tageskwh",
        new=AsyncMock(return_value={}),
    ), patch(
        "backend.services.sensor_snapshot_service.get_daily_counter_deltas_by_inv",
        new=AsyncMock(return_value={}),
    ):
        result = await aggregate_day(anlage, gestern, db, source=Source.SCHEDULER)

    assert result is not None
    # (a) Werte unverändert erhalten
    assert result.pv_prognose_kwh == 12.5
    assert result.kraftstoffpreis_euro == 1.789
    assert result.solcast_prognose_kwh == 11.0

    # Provenance der neuen Row trägt die ECHTE Quelle, nicht auto:monatsabschluss
    prov = result.source_provenance or {}
    assert prov.get("pv_prognose_kwh", {}).get("source") == "external:openmeteo"
    assert prov.get("kraftstoffpreis_euro", {}).get("source") == "external:fuel_price"
    assert prov.get("solcast_prognose_kwh", {}).get("source") == "auto:preserve_restore"

    # (b) data_provenance_log enthält die Restore-Einträge
    logs = (await db.execute(
        select(DataProvenanceLog).where(
            DataProvenanceLog.table_name == "tages_zusammenfassung",
            DataProvenanceLog.writer == "aggregator-preserve",
        )
    )).scalars().all()
    log_nach_feld = {entry.field_name: entry for entry in logs}

    assert "pv_prognose_kwh" in log_nach_feld
    assert "kraftstoffpreis_euro" in log_nach_feld
    assert "solcast_prognose_kwh" in log_nach_feld

    pv_log = log_nach_feld["pv_prognose_kwh"]
    assert pv_log.source == "external:openmeteo"
    assert pv_log.decision == "applied"
    # Natural-Key + Wert sind im Log diagnostizierbar
    assert json.loads(pv_log.row_pk_json)["anlage_id"] == anlage.id
    assert json.loads(pv_log.new_value) == 12.5

    assert log_nach_feld["kraftstoffpreis_euro"].source == "external:fuel_price"
    # Feld ohne Ursprungs-Provenance fällt auf das dedizierte Label zurück
    assert log_nach_feld["solcast_prognose_kwh"].source == "auto:preserve_restore"
