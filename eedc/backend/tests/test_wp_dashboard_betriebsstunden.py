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
    """End-to-End (#238/#290): Hauptwert = seit Anschaffung erfasste Summe der
    Tagesinkremente; Lebensdauer-Zählerstand bleibt separat (Tooltip). Die
    abgeleiteten KPIs rechnen mit den seit-Anschaffung erfassten Summen."""
    anlage, wp = await _seed_anlage_mit_wp(db)

    # Hersteller-Counter-Stände (Lebensdauer / Zählerstand): 1000 Starts, 2500 h
    # — inkl. Betrieb vor Anschaffung, daher NICHT der Kachel-Hauptwert.
    await _set_snapshot(db, anlage.id, wp.id, "wp_starts_anzahl", 1000.0)
    await _set_snapshot(db, anlage.id, wp.id, "wp_betriebsstunden", 2500.0)
    # eedc-erfasste Tagesinkremente seit Anschaffung: Σ 20 Starts / 50 h
    # → Ø Laufzeit pro Start = 2.5 h, Starts pro h = 0.4.
    for tag in (1, 2):
        db.add(TagesZusammenfassung(
            anlage_id=anlage.id, datum=date(2026, 4, tag),
            komponenten_starts={
                "wp_starts_anzahl": {str(wp.id): 10},
                "wp_betriebsstunden": {str(wp.id): 25.0},
            },
        ))
    await db.commit()

    dashboards = await get_waermepumpe_dashboard(anlage_id=anlage.id, db=db)
    assert len(dashboards) == 1
    z = dashboards[0].zusammenfassung
    # Lebensdauer-Zählerstand (Tooltip) bleibt der rohe Hersteller-Counter.
    assert z["kompressor_starts_gesamt"] == 1000
    assert z["betriebsstunden_gesamt"] == 2500.0
    # Hauptwert = seit Anschaffung erfasste Summe.
    assert z["kompressor_starts_summe_erfasst"] == 20
    assert z["betriebsstunden_summe_erfasst"] == 50.0
    # Ratios aus den seit-Anschaffung erfassten Summen (nicht aus Lebensdauer).
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


async def test_counter_summe_respektiert_anschaffungs_und_stilllegungsdatum(db):
    """#308 (detLAN): Die Counter-Tagesinkremente dürfen nur Tage INNERHALB der
    WP-Laufzeit summieren — symmetrisch zum Monatsdaten-Filter.

    Regression: Ohne Anschaffungsdatum-Scope summierte `summe_erfasst` die
    gesamte erfasste Sensor-Historie (Backfill-Tage vor Anschaffung inkl.) und
    lief gegen den Lebensdauer-Zählerstand — `Σ seit Anschaffung > Lebensdauer`,
    physikalisch unmöglich. Hier: ein Tag vor Anschaffung + ein Tag nach
    Stilllegung tragen je einen Spuk-Wert bei, der NICHT in Summe/Max landen darf.
    """
    anlage, wp = await _seed_anlage_mit_wp(db)
    # Laufzeit-Fenster der WP: 2024-01-01 .. 2026-04-30.
    wp.stilllegungsdatum = date(2026, 4, 30)
    await _set_snapshot(db, anlage.id, wp.id, "wp_starts_anzahl", 1000.0)
    await _set_snapshot(db, anlage.id, wp.id, "wp_betriebsstunden", 2500.0)

    # Spuk-Tag VOR Anschaffung (Backfill der Sensor-Historie) — muss raus.
    db.add(TagesZusammenfassung(
        anlage_id=anlage.id, datum=date(2023, 12, 15),
        komponenten_starts={
            "wp_starts_anzahl": {str(wp.id): 900},
            "wp_betriebsstunden": {str(wp.id): 2400.0},
        },
    ))
    # Zwei gültige Tage IM Fenster — nur diese zählen (Σ 20 Starts / 50 h).
    for tag in (1, 2):
        db.add(TagesZusammenfassung(
            anlage_id=anlage.id, datum=date(2026, 4, tag),
            komponenten_starts={
                "wp_starts_anzahl": {str(wp.id): 10},
                "wp_betriebsstunden": {str(wp.id): 25.0},
            },
        ))
    # Spuk-Tag NACH Stilllegung — muss ebenfalls raus.
    db.add(TagesZusammenfassung(
        anlage_id=anlage.id, datum=date(2026, 5, 3),
        komponenten_starts={
            "wp_starts_anzahl": {str(wp.id): 30},
            "wp_betriebsstunden": {str(wp.id): 24.0},
        },
    ))
    await db.commit()

    dashboards = await get_waermepumpe_dashboard(anlage_id=anlage.id, db=db)
    z = dashboards[0].zusammenfassung
    # Nur die zwei In-Fenster-Tage: Σ 20 Starts / 50 h, Max/Tag 10 / 25 h.
    assert z["kompressor_starts_summe_erfasst"] == 20
    assert z["betriebsstunden_summe_erfasst"] == 50.0
    assert z["kompressor_starts_max_tag"] == 10
    assert z["betriebsstunden_max_tag"] == 25.0
    # Kern-Invariante: seit Anschaffung erfasst ≤ Lebensdauer-Zählerstand.
    assert z["betriebsstunden_summe_erfasst"] <= z["betriebsstunden_gesamt"]
    assert z["kompressor_starts_summe_erfasst"] <= z["kompressor_starts_gesamt"]
