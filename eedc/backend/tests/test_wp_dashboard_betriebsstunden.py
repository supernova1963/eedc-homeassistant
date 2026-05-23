"""WP-Dashboard: Betriebsstunden-KPIs (#238 detLAN).

detLAN: 10 Starts auf 23 h Betriebszeit ist schlechter als 10 Starts auf
4 h Betriebszeit — also brauchen wir die Stunden, nicht nur die Starts.
Pattern analog zu Kompressor-Starts (v3.24.0): kumulativer total-increasing
Sensor pro WP-Investition, Tagesdelta-Aggregation, plus zwei abgeleitete
KPIs „Ø Laufzeit pro Start" und „Starts pro Betriebsstunde".

Tests sichern:
- Dashboard liefert `betriebsstunden_gesamt` aus dem Hersteller-Sensor.
- KPIs `oe_laufzeit_pro_start_h` / `starts_pro_betriebsstunde` werden
  korrekt aus Σ Stunden und Σ Starts berechnet.
- Fehlende Werte → KPIs bleiben `None` (kein Krücken-Wert).
"""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.routes.investitionen.dashboards import get_waermepumpe_dashboard
from backend.models import Anlage, Investition
from backend.models.sensor_snapshot import SensorSnapshot
from backend.models.tages_energie_profil import TagesZusammenfassung


async def _seed_anlage_mit_wp(session: AsyncSession) -> tuple[Anlage, Investition]:
    """Anlage + WP-Investition mit Sensor-Mapping für Starts und Stunden."""
    anlage = Anlage(
        anlagenname="Test",
        leistung_kwp=10.0,
        standort_land="DE",
        sensor_mapping={
            "investitionen": {},
        },
    )
    session.add(anlage)
    await session.flush()

    inv = Investition(
        anlage_id=anlage.id,
        typ="waermepumpe",
        bezeichnung="Test-WP",
        anschaffungsdatum=date(2024, 1, 1),
        parameter={},
    )
    session.add(inv)
    await session.flush()

    # Sensor-Mapping nach inv.id-Slot anlegen — get_counter_lifetime liest
    # `sensor_mapping["investitionen"][str(inv.id)]["felder"][feld]`.
    anlage.sensor_mapping = {
        "investitionen": {
            str(inv.id): {
                "felder": {
                    "wp_starts_anzahl": {
                        "strategie": "sensor",
                        "sensor_id": "sensor.test_starts",
                    },
                    "wp_betriebsstunden": {
                        "strategie": "sensor",
                        "sensor_id": "sensor.test_stunden",
                    },
                },
            },
        },
    }
    await session.flush()
    return anlage, inv


async def _set_snapshot(
    db: AsyncSession, anlage_id: int, inv_id: int, feld: str, wert: float,
) -> None:
    """Setzt einen Snapshot — `get_counter_lifetime` fällt darauf zurück
    wenn HA nicht verfügbar (Test-Umgebung)."""
    db.add(SensorSnapshot(
        anlage_id=anlage_id,
        sensor_key=f"inv:{inv_id}:{feld}",
        zeitpunkt=datetime.now(),
        wert_kwh=wert,
    ))


async def test_dashboard_zeigt_betriebsstunden_und_kpis(db):
    """End-to-End: Sensor-Snapshots liefern Σ Starts + Σ Stunden,
    Dashboard berechnet die abgeleiteten KPIs."""
    anlage, wp = await _seed_anlage_mit_wp(db)

    # Hersteller-Counter-Stände: 1000 Starts, 2500 h.
    # → Ø Laufzeit pro Start = 2.5 h, Starts pro h = 0.4.
    await _set_snapshot(db, anlage.id, wp.id, "wp_starts_anzahl", 1000.0)
    await _set_snapshot(db, anlage.id, wp.id, "wp_betriebsstunden", 2500.0)
    await db.commit()

    dashboards = await get_waermepumpe_dashboard(anlage_id=anlage.id, db=db)
    assert len(dashboards) == 1
    z = dashboards[0].zusammenfassung
    assert z["kompressor_starts_gesamt"] == 1000
    assert z["betriebsstunden_gesamt"] == 2500.0
    assert z["oe_laufzeit_pro_start_h"] == 2.5
    assert z["starts_pro_betriebsstunde"] == 0.4


async def test_max_tag_aus_komponenten_starts(db):
    """`betriebsstunden_max_tag` kommt aus TagesZusammenfassung-Tagesdeltas."""
    anlage, wp = await _seed_anlage_mit_wp(db)
    await _set_snapshot(db, anlage.id, wp.id, "wp_starts_anzahl", 500.0)
    await _set_snapshot(db, anlage.id, wp.id, "wp_betriebsstunden", 1000.0)

    # Drei Tage mit unterschiedlichen Tages-Deltas — Max = 18.5
    for tag, h in ((1, 12.0), (2, 18.5), (3, 8.0)):
        db.add(TagesZusammenfassung(
            anlage_id=anlage.id, datum=date(2026, 4, tag),
            komponenten_starts={
                "wp_betriebsstunden": {str(wp.id): h},
                "wp_starts_anzahl": {str(wp.id): 5},
            },
        ))
    await db.commit()

    dashboards = await get_waermepumpe_dashboard(anlage_id=anlage.id, db=db)
    assert dashboards[0].zusammenfassung["betriebsstunden_max_tag"] == 18.5
    assert dashboards[0].zusammenfassung["kompressor_starts_max_tag"] == 5


async def test_fehlende_betriebsstunden_kpis_bleiben_none(db):
    """Anwender pflegt nur Starts (kein Stunden-Sensor) → KPIs sind None."""
    anlage, wp = await _seed_anlage_mit_wp(db)
    # Nur Starts gemappt — Stunden-Konfig aus dem Mapping nehmen.
    anlage.sensor_mapping["investitionen"][str(wp.id)]["felder"].pop(
        "wp_betriebsstunden"
    )
    await _set_snapshot(db, anlage.id, wp.id, "wp_starts_anzahl", 1000.0)
    await db.commit()

    dashboards = await get_waermepumpe_dashboard(anlage_id=anlage.id, db=db)
    z = dashboards[0].zusammenfassung
    assert z["kompressor_starts_gesamt"] == 1000
    assert z["betriebsstunden_gesamt"] is None
    assert z["oe_laufzeit_pro_start_h"] is None
    assert z["starts_pro_betriebsstunde"] is None


async def test_nur_stunden_kein_starts_kpis_bleiben_none(db):
    """Spiegelfall: Stunden-Sensor da, Starts-Sensor fehlt → KPIs None."""
    anlage, wp = await _seed_anlage_mit_wp(db)
    anlage.sensor_mapping["investitionen"][str(wp.id)]["felder"].pop(
        "wp_starts_anzahl"
    )
    await _set_snapshot(db, anlage.id, wp.id, "wp_betriebsstunden", 2500.0)
    await db.commit()

    dashboards = await get_waermepumpe_dashboard(anlage_id=anlage.id, db=db)
    z = dashboards[0].zusammenfassung
    assert z["betriebsstunden_gesamt"] == 2500.0
    assert z["kompressor_starts_gesamt"] is None
    assert z["oe_laufzeit_pro_start_h"] is None
    assert z["starts_pro_betriebsstunde"] is None
