"""
Diagnostics API — operative Validierungs-Endpoints für interne Health-Checks.

Aktuell:
- GET /live-snapshot-5min: Phase 1 Live-Snapshot 5-Min Validierung
- POST /resnap-snapshots: Snapshots der letzten N Tage neu schreiben
  (nach Service-Bugfixes wie get_value_at off-by-one v3.25.9)

Wird vom Notebook aus per curl ausgewertet, ersetzt das Skript
scripts/check-live-snapshot-5min.sh (das bleibt als Standalone-Fallback).
"""

import logging
from datetime import date, datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps import get_db
from backend.core.config import settings
from backend.models.anlage import Anlage
from backend.services.scheduler import get_scheduler
from backend.services.sensor_snapshot_service import resnap_anlage_range

logger = logging.getLogger(__name__)

router = APIRouter()


class CheckResult(BaseModel):
    name: str
    status: str  # "pass" | "fail" | "warn" | "skip"
    detail: str
    data: Optional[dict] = None


class LiveSnapshot5MinResponse(BaseModel):
    feature_enabled: bool
    today: date
    scheduler: dict
    checks: list[CheckResult]
    summary: str


@router.get("/live-snapshot-5min", response_model=LiveSnapshot5MinResponse)
async def live_snapshot_5min_diagnostics(db: AsyncSession = Depends(get_db)):
    """
    Sechs Checks für die Phase-1-Validierung des Live-Snapshot-5-Min-Pfads.

    Aussagekraft pro Tag-nach-Aktivierung:
    - Tag 1: Checks 1, 2, 3, 6 sind aussagekräftig. Check 4 ab Tag 1 23:55+,
      Check 5 erst ab Tag 2.
    - Tag 2+: alle Checks aussagekräftig.

    Kein Auth — bewusst, weil das Add-on im LAN läuft. Bei externem Zugang
    (Reverse-Proxy / Cloudflared) muss das Routing davorhängen.
    """
    today = date.today()
    yesterday = today - timedelta(days=1)
    day_before = today - timedelta(days=2)

    sched = get_scheduler()
    sched_status = sched.get_status()
    jobs_by_id = {j["id"]: j for j in sched_status.get("jobs", [])}

    scheduler_info = {
        "running": sched_status.get("running", False),
        "sensor_snapshot_5min": jobs_by_id.get("sensor_snapshot_5min"),
        "sensor_snapshot_5min_cleanup": jobs_by_id.get("sensor_snapshot_5min_cleanup"),
    }

    checks: list[CheckResult] = []

    # ------------------------------------------------------------------------
    # Vorab-Check: Feature-Flag an?
    # ------------------------------------------------------------------------
    if not settings.live_snapshot_5min_enabled:
        checks.append(CheckResult(
            name="0_flag",
            status="fail",
            detail="LIVE_SNAPSHOT_5MIN_ENABLED ist nicht 'true'. Setze die Env-Var "
                   "im Add-on und starte neu, sonst sind alle weiteren Checks moot.",
        ))
        return LiveSnapshot5MinResponse(
            feature_enabled=False,
            today=today,
            scheduler=scheduler_info,
            checks=checks,
            summary="Flag aus — nichts zu prüfen.",
        )

    if not (scheduler_info["sensor_snapshot_5min"] and scheduler_info["sensor_snapshot_5min_cleanup"]):
        checks.append(CheckResult(
            name="0_jobs",
            status="fail",
            detail="5-Min-Cron-Jobs sind nicht im Scheduler registriert, obwohl Flag an ist. "
                   "Add-on neu starten?",
            data={"jobs_seen": list(jobs_by_id.keys())},
        ))

    # ------------------------------------------------------------------------
    # Check 1: Sub-Hour-Slots werden geschrieben
    # ------------------------------------------------------------------------
    row = (await db.execute(text("""
        SELECT COUNT(*) AS slots, COUNT(DISTINCT sensor_key) AS counters
        FROM sensor_snapshots
        WHERE strftime('%M', zeitpunkt) != '00'
          AND date(zeitpunkt) = :d
    """), {"d": today.isoformat()})).first()
    slots_today = row[0] if row else 0
    counters_today = row[1] if row else 0
    checks.append(CheckResult(
        name="1_slots_today",
        status="pass" if slots_today > 0 else "fail",
        detail=(f"{slots_today} Sub-Hour-Slots heute über {counters_today} Counter."
                if slots_today > 0 else
                "Keine Sub-Hour-Slots heute. HA short_term leer? state_class fehlt?"),
        data={"slots": slots_today, "counters": counters_today},
    ))

    # ------------------------------------------------------------------------
    # Check 2: Slot-Verteilung pro Stunde (Histogramm)
    # ------------------------------------------------------------------------
    rows = (await db.execute(text("""
        SELECT
          CAST(strftime('%H', zeitpunkt) AS INTEGER) AS stunde,
          COUNT(*) AS slots,
          COUNT(DISTINCT sensor_key) AS counters
        FROM sensor_snapshots
        WHERE date(zeitpunkt) = :d
          AND strftime('%M', zeitpunkt) != '00'
        GROUP BY stunde
        ORDER BY stunde
    """), {"d": today.isoformat()})).all()
    histogram = [{"hour": r[0], "slots": r[1], "counters": r[2]} for r in rows]
    # Erwartung: pro Stunde 11 Sub-Hour-Slots (:05..:55) × Counter
    incomplete = [h for h in histogram
                  if h["counters"] > 0 and h["slots"] < h["counters"] * 11]
    checks.append(CheckResult(
        name="2_distribution",
        status="pass" if not incomplete else "warn",
        detail=(f"{len(histogram)} Stunden mit Daten, {len(incomplete)} davon "
                f"unvollständig (< 11 Slots/Counter)."),
        data={"histogram": histogram, "incomplete_hours": [h["hour"] for h in incomplete]},
    ))

    # ------------------------------------------------------------------------
    # Check 3: Monotonie (kWh-Counter steigen monoton, Tagesreset toleriert)
    # ------------------------------------------------------------------------
    glitches = (await db.execute(text("""
        WITH ordered AS (
          SELECT
            sensor_key, zeitpunkt, wert_kwh,
            LAG(wert_kwh) OVER (PARTITION BY sensor_key ORDER BY zeitpunkt) AS prev_wert,
            LAG(zeitpunkt) OVER (PARTITION BY sensor_key ORDER BY zeitpunkt) AS prev_zp
          FROM sensor_snapshots
          WHERE date(zeitpunkt) = :d
            AND sensor_key NOT LIKE '%_starts_anzahl'
        )
        SELECT sensor_key, prev_zp, prev_wert, zeitpunkt, wert_kwh,
               round(wert_kwh - prev_wert, 3) AS delta
        FROM ordered
        WHERE prev_wert IS NOT NULL
          AND wert_kwh < prev_wert - 0.01
          AND wert_kwh > prev_wert * 0.5
        ORDER BY sensor_key, zeitpunkt
        LIMIT 20
    """), {"d": today.isoformat()})).all()
    glitch_list = [{
        "sensor_key": g[0],
        "prev_zeitpunkt": g[1],
        "prev_wert": g[2],
        "zeitpunkt": g[3],
        "wert": g[4],
        "delta": g[5],
    } for g in glitches]
    checks.append(CheckResult(
        name="3_monotonicity",
        status="pass" if not glitch_list else "fail",
        detail=(f"{len(glitch_list)} nicht-monotone Übergänge heute "
                f"(Tagesresets ausgeschlossen)."),
        data={"glitches": glitch_list},
    ))

    # ------------------------------------------------------------------------
    # Check 4: Mitternachts-Boundary (gestern 23:55 → heute 00:00 → 00:05)
    # ------------------------------------------------------------------------
    rows = (await db.execute(text("""
        WITH cnt AS (
          SELECT DISTINCT sensor_key FROM sensor_snapshots
          WHERE date(zeitpunkt) = :y
            AND strftime('%M', zeitpunkt) != '00'
        )
        SELECT
          cnt.sensor_key,
          EXISTS(SELECT 1 FROM sensor_snapshots s WHERE s.sensor_key=cnt.sensor_key
            AND datetime(s.zeitpunkt) = datetime(:y || ' 23:55:00')) AS has_2355,
          EXISTS(SELECT 1 FROM sensor_snapshots s WHERE s.sensor_key=cnt.sensor_key
            AND datetime(s.zeitpunkt) = datetime(:t || ' 00:00:00')) AS has_0000,
          EXISTS(SELECT 1 FROM sensor_snapshots s WHERE s.sensor_key=cnt.sensor_key
            AND datetime(s.zeitpunkt) = datetime(:t || ' 00:05:00')) AS has_0005
        FROM cnt
    """), {"y": yesterday.isoformat(), "t": today.isoformat()})).all()
    boundary_data = [
        {"sensor_key": r[0], "has_2355": bool(r[1]),
         "has_0000": bool(r[2]), "has_0005": bool(r[3])}
        for r in rows
    ]
    missing_0000 = [r for r in boundary_data if not r["has_0000"]]
    if not boundary_data:
        boundary_status, boundary_detail = "skip", "Gestern keine Sub-Hour-Slots — Tag 1 nach Aktivierung."
    elif not missing_0000:
        boundary_status, boundary_detail = "pass", f"{len(boundary_data)} Counter mit sauberer 23:55→00:00→00:05-Kette."
    else:
        boundary_status = "warn"
        boundary_detail = f"{len(missing_0000)} Counter ohne 00:00-Snapshot. Hourly-:05-Job läuft noch oder LTS leer."
    checks.append(CheckResult(
        name="4_midnight_boundary",
        status=boundary_status,
        detail=boundary_detail,
        data={"counters": boundary_data},
    ))

    # ------------------------------------------------------------------------
    # Check 5: Cleanup (vorgestern sollte keine Sub-Hour-Slots mehr haben)
    # ------------------------------------------------------------------------
    row = (await db.execute(text("""
        SELECT
          (SELECT COUNT(*) FROM sensor_snapshots
            WHERE strftime('%M', zeitpunkt) != '00' AND date(zeitpunkt) = :d) AS sub,
          (SELECT COUNT(*) FROM sensor_snapshots
            WHERE strftime('%M', zeitpunkt) = '00' AND date(zeitpunkt) = :d) AS hourly
    """), {"d": day_before.isoformat()})).first()
    sub_count = row[0] if row else 0
    hourly_count = row[1] if row else 0
    if sub_count == 0 and hourly_count == 0:
        cleanup_status = "skip"
        cleanup_detail = ("Vorgestern keine Daten — Tag 1 nach Aktivierung. "
                          "Re-Run morgen für Cleanup-Validierung.")
    elif sub_count == 0:
        cleanup_status = "pass"
        cleanup_detail = f"Vorgestern leer (Sub-Hour), Hourly-Slots ({hourly_count}) erhalten."
    else:
        cleanup_status = "fail"
        cleanup_detail = f"{sub_count} Sub-Hour-Slots vorgestern noch da — Cleanup-Job nicht gelaufen?"
    checks.append(CheckResult(
        name="5_cleanup",
        status=cleanup_status,
        detail=cleanup_detail,
        data={"sub_hour_left": sub_count, "hourly_kept": hourly_count},
    ))

    # ------------------------------------------------------------------------
    # Check 6: Verdichtungs-Garantie (1h-Δ aus den 5-Min-Slots rekonstruierbar)
    # ------------------------------------------------------------------------
    # Pro Counter+Stunde heute: 1h-Δ = snap[h+1:00] - snap[h:00].
    # 5-Min-MAX(wert) - MIN(wert) innerhalb [h:00..h+1:00) = MAX-MIN-Δ.
    # Bei monoton steigenden Countern muss MAX-MIN-Δ ≈ 1h-Δ sein.
    drift_rows = (await db.execute(text("""
        WITH bounds AS (
          SELECT DISTINCT
            s.sensor_key,
            CAST(strftime('%H', s.zeitpunkt) AS INTEGER) AS h
          FROM sensor_snapshots s
          WHERE date(s.zeitpunkt) = :d
            AND strftime('%M', s.zeitpunkt) != '00'
            AND s.sensor_key NOT LIKE '%_starts_anzahl'
        ),
        h_start AS (
          SELECT b.sensor_key, b.h, s.wert_kwh AS w0
          FROM bounds b
          JOIN sensor_snapshots s ON s.sensor_key = b.sensor_key
          WHERE datetime(s.zeitpunkt) = datetime(:d || ' ' || printf('%02d:00:00', b.h))
        ),
        h_end AS (
          SELECT b.sensor_key, b.h, s.wert_kwh AS w1
          FROM bounds b
          JOIN sensor_snapshots s ON s.sensor_key = b.sensor_key
          WHERE datetime(s.zeitpunkt) = datetime(:d || ' ' || printf('%02d:00:00', b.h + 1))
        ),
        five_min AS (
          SELECT b.sensor_key, b.h,
                 MAX(s.wert_kwh) - MIN(s.wert_kwh) AS sub_delta,
                 COUNT(*) AS n_slots
          FROM bounds b
          JOIN sensor_snapshots s ON s.sensor_key = b.sensor_key
          WHERE date(s.zeitpunkt) = :d
            AND CAST(strftime('%H', s.zeitpunkt) AS INTEGER) = b.h
            AND strftime('%M', s.zeitpunkt) != '00'
          GROUP BY b.sensor_key, b.h
        )
        SELECT
          h_start.sensor_key,
          h_start.h,
          round(h_end.w1 - h_start.w0, 3) AS hourly_delta,
          round(five_min.sub_delta, 3) AS five_min_range,
          round((h_end.w1 - h_start.w0) - five_min.sub_delta, 4) AS drift,
          five_min.n_slots
        FROM h_start
        JOIN h_end USING (sensor_key, h)
        JOIN five_min USING (sensor_key, h)
        WHERE five_min.n_slots = 11
        ORDER BY h_start.sensor_key, h_start.h
    """), {"d": today.isoformat()})).all()
    drift_data = [{
        "sensor_key": d[0], "hour": d[1],
        "hourly_delta": d[2], "five_min_range": d[3],
        "drift": d[4], "n_slots": d[5],
    } for d in drift_rows]
    bad_drift = [d for d in drift_data if abs(d["drift"] or 0) > 0.005]
    if not drift_data:
        drift_status, drift_detail = "skip", "Noch keine vollständigen Stunden mit hourly+5min-Boundaries."
    elif not bad_drift:
        drift_status = "pass"
        drift_detail = f"{len(drift_data)} Stunden geprüft, alle Drift < 0.005 kWh."
    else:
        drift_status = "fail"
        drift_detail = f"{len(bad_drift)}/{len(drift_data)} Stunden mit Drift ≥ 0.005 kWh."
    checks.append(CheckResult(
        name="6_drift",
        status=drift_status,
        detail=drift_detail,
        data={"per_hour": drift_data, "bad": bad_drift},
    ))

    # ------------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------------
    fails = [c for c in checks if c.status == "fail"]
    warns = [c for c in checks if c.status == "warn"]
    if fails:
        summary = f"FAIL — {len(fails)} kritische Probleme: {', '.join(c.name for c in fails)}"
    elif warns:
        summary = f"WARN — {len(warns)} Auffälligkeiten: {', '.join(c.name for c in warns)}"
    else:
        summary = ("PASS — alle aussagekräftigen Checks grün. "
                   "Frontend-Wiring kann angegangen werden.")

    return LiveSnapshot5MinResponse(
        feature_enabled=True,
        today=today,
        scheduler=scheduler_info,
        checks=checks,
        summary=summary,
    )


class ResnapResponse(BaseModel):
    von: datetime
    bis: datetime
    anlagen: int
    hourly_geschrieben: int
    fivemin_geschrieben: int
    stunden_pro_anlage: int
    slots_5min_pro_anlage: int


@router.post("/resnap-snapshots", response_model=ResnapResponse)
async def resnap_snapshots(
    days: int = Query(7, ge=1, le=14, description="Anzahl Tage rückwirkend"),
    include_5min: bool = Query(True, description="Auch Sub-Hour-Slots resnappen"),
    db: AsyncSession = Depends(get_db),
):
    """
    Schreibt Snapshots der letzten N Tage für ALLE Anlagen neu — sowohl
    hourly :00 als auch 5-Min Sub-Hour-Slots. Existierende Werte werden
    überschrieben.

    Use-Case: Nach Service-Bugfixes (z.B. get_value_at off-by-one in v3.25.9)
    bestehende Snapshot-Werte mit korrigierter Logik neu generieren, damit
    die Diagnose-Checks und Live-Tagesverlauf gegen frische Daten laufen.

    Hinweis: 5-Min-Slots können nur für die letzten ~10–14 Tage rekonstruiert
    werden (HA short_term_statistics Retention). Hourly läuft beliebig zurück.
    """
    bis = datetime.now().replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
    von = bis - timedelta(days=days)

    result = await db.execute(select(Anlage))
    anlagen = result.scalars().all()
    if not anlagen:
        raise HTTPException(status_code=404, detail="Keine Anlagen gefunden")

    total_hourly = 0
    total_5min = 0
    stunden_pro_anlage = 0
    slots_5min_pro_anlage = 0

    for anlage in anlagen:
        try:
            stats = await resnap_anlage_range(
                db, anlage, von=von, bis=bis, include_5min=include_5min
            )
            total_hourly += stats["hourly"]
            total_5min += stats["5min"]
            stunden_pro_anlage = stats["stunden"]
            slots_5min_pro_anlage = stats["slots_5min"]
        except Exception as e:
            logger.warning(
                f"Resnap Anlage {anlage.id} fehlgeschlagen: {type(e).__name__}: {e}"
            )

    return ResnapResponse(
        von=von,
        bis=bis,
        anlagen=len(anlagen),
        hourly_geschrieben=total_hourly,
        fivemin_geschrieben=total_5min,
        stunden_pro_anlage=stunden_pro_anlage,
        slots_5min_pro_anlage=slots_5min_pro_anlage,
    )
