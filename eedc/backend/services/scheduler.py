"""
EEDC Scheduler Service.

Background-Scheduler für periodische Tasks.
Verwendet APScheduler für Cron-basierte Job-Ausführung.
"""

import logging
from datetime import datetime
from typing import Optional

from backend.services.activity_service import log_activity

try:
    from apscheduler.schedulers.asyncio import AsyncIOScheduler
    from apscheduler.triggers.cron import CronTrigger
    from apscheduler.triggers.interval import IntervalTrigger
    from apscheduler.jobstores.memory import MemoryJobStore
    SCHEDULER_AVAILABLE = True
except ImportError:
    SCHEDULER_AVAILABLE = False

logger = logging.getLogger(__name__)


class EEDCScheduler:
    """
    Background-Scheduler für periodische Tasks.

    Jobs:
    - Monatswechsel-Snapshot: Am 1. jeden Monats um 00:01
    - MQTT Energy Snapshot: Alle 5 Minuten
    - MQTT Energy Cleanup: Täglich um 03:00
    - Energie-Profil Aggregation: Täglich um 00:15 (Vortag)
    """

    def __init__(self):
        self._scheduler: Optional["AsyncIOScheduler"] = None
        self._running = False

    @property
    def is_available(self) -> bool:
        """Prüft ob APScheduler verfügbar ist."""
        return SCHEDULER_AVAILABLE

    @property
    def is_running(self) -> bool:
        """Prüft ob Scheduler läuft."""
        return self._running and self._scheduler is not None

    def start(self) -> bool:
        """
        Startet den Scheduler.

        Returns:
            True wenn erfolgreich gestartet
        """
        if not SCHEDULER_AVAILABLE:
            logger.warning("APScheduler nicht installiert - Scheduler deaktiviert")
            return False

        if self._running:
            logger.info("Scheduler läuft bereits")
            return True

        try:
            self._scheduler = AsyncIOScheduler(
                jobstores={"default": MemoryJobStore()},
                timezone="Europe/Berlin",
            )

            # Monatswechsel-Snapshot: Am 1. jeden Monats um 00:01
            self._scheduler.add_job(
                monthly_snapshot_job,
                CronTrigger(day=1, hour=0, minute=1),
                id="monthly_snapshot",
                name="Monatswechsel Snapshot",
                replace_existing=True,
            )

            # MQTT Energy Snapshot: Alle 5 Minuten
            self._scheduler.add_job(
                mqtt_energy_snapshot_job,
                IntervalTrigger(minutes=5),
                id="mqtt_energy_snapshot",
                name="MQTT Energy Snapshot",
                replace_existing=True,
            )

            # MQTT Energy Cleanup: Täglich um 03:00
            self._scheduler.add_job(
                mqtt_energy_cleanup_job,
                CronTrigger(hour=3, minute=0),
                id="mqtt_energy_cleanup",
                name="MQTT Energy Cleanup",
                replace_existing=True,
            )

            # MQTT Live Snapshot: Alle 5 Minuten (W-Werte für Tagesverlauf-Chart)
            self._scheduler.add_job(
                mqtt_live_snapshot_job,
                IntervalTrigger(minutes=5),
                id="mqtt_live_snapshot",
                name="MQTT Live Snapshot",
                replace_existing=True,
            )

            # MQTT Live Cleanup: Täglich um 03:05 (15 Tage Retention)
            self._scheduler.add_job(
                mqtt_live_cleanup_job,
                CronTrigger(hour=3, minute=5),
                id="mqtt_live_cleanup",
                name="MQTT Live Cleanup",
                replace_existing=True,
            )

            # MQTT Auto-Publish: Intervall aus settings (nur wenn MQTT_AUTO_PUBLISH=true)
            from backend.core.config import settings as app_settings
            if app_settings.mqtt_auto_publish:
                interval = max(5, app_settings.mqtt_publish_interval)  # Minimum 5 Minuten
                self._scheduler.add_job(
                    mqtt_auto_publish_job,
                    IntervalTrigger(minutes=interval),
                    id="mqtt_auto_publish",
                    name=f"MQTT Auto-Publish (alle {interval} Min)",
                    replace_existing=True,
                )
                logger.info(f"MQTT Auto-Publish aktiviert: alle {interval} Minuten")

            # Sensor-Snapshots: Stündlich 5 Min nach voller Stunde (Issue #135)
            # Liest kumulative kWh-Zählerstände aus HA Statistics in sensor_snapshots.
            # 5-Min-Offset gibt HA Zeit, die Stunde zu finalisieren.
            self._scheduler.add_job(
                sensor_snapshot_job,
                CronTrigger(minute=5),
                id="sensor_snapshot",
                name="Sensor-Snapshots (Zählerstände stündlich)",
                replace_existing=True,
            )

            # Sensor-Snapshot Preview: 5 Min vor voller Stunde (Issue #146).
            # Schreibt Live-Zählerstand als Annäherung für h:00, nur wenn der
            # reguläre Snapshot noch fehlt. Sorgt dafür, dass die laufende
            # Stunde im Energieprofil sofort am Stundenende erscheint.
            self._scheduler.add_job(
                sensor_snapshot_preview_job,
                CronTrigger(minute=55),
                id="sensor_snapshot_preview",
                name="Sensor-Snapshots Preview (Live-Wert, :55)",
                replace_existing=True,
            )

            # Energie-Profil Heute: Alle 15 Minuten (rollierend, laufender Tag)
            self._scheduler.add_job(
                energie_profil_heute_job,
                IntervalTrigger(minutes=15),
                id="energie_profil_heute",
                name="Energie-Profil Heute (rollierend)",
                replace_existing=True,
            )

            # Energie-Profil Vortag: Täglich um 00:15 (Finalisierung + Cleanup)
            self._scheduler.add_job(
                energie_profil_aggregation_job,
                CronTrigger(hour=0, minute=15),
                id="energie_profil_aggregation",
                name="Energie-Profil Vortag (Finalisierung)",
                replace_existing=True,
            )

            # Prognose-Prefetch: Alle 45 Min (innerhalb des 60-Min Cache-TTL)
            self._scheduler.add_job(
                prognose_prefetch_job,
                IntervalTrigger(minutes=45),
                id="prognose_prefetch",
                name="Prognose-Prefetch",
                replace_existing=True,
            )

            # L2-Cache Cleanup: Täglich um 04:00 (abgelaufene Einträge löschen)
            self._scheduler.add_job(
                api_cache_cleanup_job,
                CronTrigger(hour=4, minute=0),
                id="api_cache_cleanup",
                name="API-Cache Cleanup",
                replace_existing=True,
            )

            # Kraftstoffpreis: Wöchentlich Dienstag 06:00 (Oil Bulletin erscheint Montag)
            self._scheduler.add_job(
                kraftstoffpreis_job,
                CronTrigger(day_of_week="tue", hour=6, minute=0),
                id="kraftstoffpreis",
                name="Kraftstoffpreis (EU Oil Bulletin)",
                replace_existing=True,
            )

            self._scheduler.start()
            self._running = True
            logger.info("EEDC Scheduler gestartet")
            return True

        except Exception as e:
            logger.error(f"Fehler beim Starten des Schedulers: {type(e).__name__}: {e}")
            return False

    def stop(self) -> None:
        """Stoppt den Scheduler."""
        if self._scheduler and self._running:
            self._scheduler.shutdown(wait=False)
            self._running = False
            logger.info("EEDC Scheduler gestoppt")

    def get_next_run(self, job_id: str) -> Optional[datetime]:
        """
        Gibt den nächsten Ausführungszeitpunkt eines Jobs zurück.

        Args:
            job_id: Job-ID (z.B. "monthly_snapshot")

        Returns:
            Datetime des nächsten Laufs oder None
        """
        if not self._scheduler:
            return None

        job = self._scheduler.get_job(job_id)
        if job:
            return job.next_run_time
        return None

    def get_status(self) -> dict:
        """
        Gibt Status des Schedulers zurück.

        Returns:
            Dict mit Status-Informationen
        """
        if not SCHEDULER_AVAILABLE:
            return {
                "available": False,
                "running": False,
                "error": "APScheduler nicht installiert (pip install apscheduler)"
            }

        if not self._scheduler:
            return {
                "available": True,
                "running": False,
                "jobs": []
            }

        jobs = []
        for job in self._scheduler.get_jobs():
            jobs.append({
                "id": job.id,
                "name": job.name,
                "next_run": job.next_run_time.isoformat() if job.next_run_time else None,
            })

        return {
            "available": True,
            "running": self._running,
            "jobs": jobs
        }

    async def trigger_monthly_snapshot(self, anlage_id: Optional[int] = None) -> dict:
        """
        Führt den Monatswechsel-Snapshot manuell aus.

        Args:
            anlage_id: Optional - nur für eine bestimmte Anlage

        Returns:
            Dict mit Ergebnis
        """
        return await monthly_snapshot_job(anlage_id=anlage_id)


async def monthly_snapshot_job(anlage_id: Optional[int] = None) -> dict:
    """
    Monatswechsel-Snapshot Job.

    Wird am 1. jeden Monats um 00:01 ausgeführt oder manuell getriggert.
    Dient als Zeitstempel-Marker für den Monatswechsel.
    Monatsdaten werden über HA Statistics DB gelesen (nicht mehr über MQTT MWD).

    Args:
        anlage_id: Optional - nur für eine bestimmte Anlage

    Returns:
        Dict mit Statistiken
    """
    now = datetime.now()
    logger.info(f"Monatswechsel-Snapshot gestartet: {now.isoformat()}")

    results = {
        "timestamp": now.isoformat(),
        "message": "Monatswechsel registriert. Monatsdaten werden über HA Statistics DB gelesen.",
    }

    logger.info("Monatswechsel-Snapshot abgeschlossen")
    await log_activity(
        kategorie="scheduler",
        aktion="Monatswechsel-Snapshot",
        erfolg=True,
        details=results["message"],
    )
    return results


async def mqtt_energy_snapshot_job() -> None:
    """Snapshots MQTT Energy-Cache in SQLite (alle 5 Min)."""
    try:
        from backend.services.mqtt_energy_history_service import snapshot_energy_cache
        await snapshot_energy_cache()
    except Exception as e:
        logger.warning(f"MQTT Energy Snapshot fehlgeschlagen: {type(e).__name__}: {e}")
        await log_activity(
            kategorie="scheduler",
            aktion="MQTT Energy Snapshot fehlgeschlagen",
            erfolg=False,
            details=f"{type(e).__name__}: {e}",
        )


async def mqtt_energy_cleanup_job() -> None:
    """Löscht alte MQTT Energy Snapshots (täglich um 03:00)."""
    try:
        from backend.services.mqtt_energy_history_service import cleanup_old_snapshots
        await cleanup_old_snapshots()
    except Exception as e:
        logger.warning(f"MQTT Energy Cleanup fehlgeschlagen: {type(e).__name__}: {e}")
        await log_activity(
            kategorie="scheduler",
            aktion="MQTT Energy Cleanup fehlgeschlagen",
            erfolg=False,
            details=f"{type(e).__name__}: {e}",
        )


async def mqtt_live_snapshot_job() -> None:
    """Snapshots MQTT Live-W-Werte in SQLite (alle 5 Min, für Tagesverlauf-Chart)."""
    try:
        from backend.services.mqtt_live_history_service import snapshot_live_cache
        await snapshot_live_cache()
    except Exception as e:
        logger.warning(f"MQTT Live Snapshot fehlgeschlagen: {type(e).__name__}: {e}")


async def mqtt_live_cleanup_job() -> None:
    """Löscht alte MQTT Live Snapshots (täglich um 03:05, 15 Tage Retention)."""
    try:
        from backend.services.mqtt_live_history_service import cleanup_old_snapshots
        await cleanup_old_snapshots()
    except Exception as e:
        logger.warning(f"MQTT Live Cleanup fehlgeschlagen: {type(e).__name__}: {e}")


async def sensor_snapshot_job() -> None:
    """
    Schreibt stündliche Snapshots aller gemappten kumulativen kWh-Zähler
    (Issue #135). Läuft 5 Min nach voller Stunde für alle Anlagen.

    Default zeitpunkt = aktuelle Stunde auf :00 gerundet (also die gerade
    abgeschlossene Stunde zum Zeitpunkt der Ausführung).
    """
    try:
        from sqlalchemy import select
        from backend.core.database import get_session
        from backend.models.anlage import Anlage
        from backend.services.sensor_snapshot_service import snapshot_anlage

        now = datetime.now()
        # Die Stunde, die gerade abgeschlossen wurde (aktuelle volle Stunde)
        zeitpunkt = now.replace(minute=0, second=0, microsecond=0)

        total_anlagen = 0
        total_snapshots = 0

        async with get_session() as db:
            result = await db.execute(select(Anlage))
            anlagen = result.scalars().all()

            for anlage in anlagen:
                try:
                    n = await snapshot_anlage(db, anlage, zeitpunkt=zeitpunkt)
                    if n > 0:
                        total_snapshots += n
                        total_anlagen += 1
                except Exception as e:
                    logger.debug(
                        f"Snapshot für Anlage {anlage.id} fehlgeschlagen: "
                        f"{type(e).__name__}: {e}"
                    )

        if total_snapshots > 0:
            logger.info(
                f"Sensor-Snapshots geschrieben: {total_snapshots} Werte für "
                f"{total_anlagen} Anlagen @ {zeitpunkt.isoformat()}"
            )
    except Exception as e:
        logger.warning(f"Sensor-Snapshot Job fehlgeschlagen: {type(e).__name__}: {e}")
        await log_activity(
            kategorie="scheduler",
            aktion="Sensor-Snapshot fehlgeschlagen",
            erfolg=False,
            details=f"{type(e).__name__}: {e}",
        )


async def sensor_snapshot_preview_job() -> None:
    """
    Live-Snapshot-Prüfroutine kurz vor Stundenende (Issue #146).

    Schreibt für die anstehende volle Stunde Live-Zählerstände, nur wo
    snap[h+1:00] noch nicht existiert. Damit ist die laufende Stunde im
    Energieprofil bereits am Stundenende sichtbar (kein "0.00"/"—" mehr
    bis :05 der Folgestunde).

    Beim regulären :05-Job wird der Live-Approx-Wert durch den exakten
    HA-Statistics-Wert via _upsert überschrieben.
    """
    try:
        from sqlalchemy import select
        from backend.core.database import get_session
        from backend.models.anlage import Anlage
        from backend.services.sensor_snapshot_service import live_snapshot_if_missing

        now = datetime.now()
        # Anstehende volle Stunde (z. B. now=15:55 → 16:00)
        zeitpunkt = (now + timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)

        total = 0
        async with get_session() as db:
            result = await db.execute(select(Anlage))
            anlagen = result.scalars().all()
            for anlage in anlagen:
                try:
                    n = await live_snapshot_if_missing(db, anlage, zeitpunkt=zeitpunkt)
                    total += n
                except Exception as e:
                    logger.debug(
                        f"Live-Snapshot Preview Anlage {anlage.id} fehlgeschlagen: "
                        f"{type(e).__name__}: {e}"
                    )

        if total > 0:
            logger.debug(
                f"Sensor-Snapshot Preview: {total} Live-Werte geschrieben "
                f"@ {zeitpunkt.isoformat()}"
            )
    except Exception as e:
        logger.debug(f"Sensor-Snapshot Preview Job fehlgeschlagen: {type(e).__name__}: {e}")


async def sensor_snapshot_startup_recovery() -> None:
    """
    Holt nach Addon-Restart verpasste Snapshots der letzten 6 Stunden nach.

    Hintergrund: Die Cron-Trigger :05 und :55 haben keine Misfire-Recovery.
    Wird das Addon zwischen :55 und :05 der Folgestunde neu gestartet (z. B.
    16:32 nach 15:55), fehlen für die laufende und ggf. abgeschlossene Stunde
    die Snapshots, weil:
      - HA Statistics für die laufende Stunde noch keine Hourly-Row hat
        (die wird erst am Stundenende geschrieben)
      - Der :55-Preview-Job nicht lief (Addon noch nicht da)

    Strategie:
      - Letzte 6 Stunden (≥ :00 lokal) durchgehen, je Anlage snapshot_anlage()
        rufen — idempotent dank Upsert, holt aus HA Statistics nach.
      - Für die laufende volle Stunde zusätzlich live_snapshot_if_missing(),
        damit das Energieprofil sofort einen Wert hat (Approximation aus
        Live-State, wird beim nächsten regulären :05-Lauf überschrieben).
      - Anschließend aggregate_today_all() triggern, damit Slot-Werte sofort
        in tagesenergieprofil sichtbar werden.

    Wird in main.py beim Lifespan-Startup als Hintergrund-Task gestartet,
    blockiert also den Boot nicht.
    """
    try:
        from sqlalchemy import select
        from backend.core.database import get_session
        from backend.models.anlage import Anlage
        from backend.services.sensor_snapshot_service import (
            snapshot_anlage,
            live_snapshot_if_missing,
        )

        now = datetime.now()
        aktuelle_stunde = now.replace(minute=0, second=0, microsecond=0)
        zeitpunkte = [aktuelle_stunde - timedelta(hours=h) for h in range(7)]  # 0..-6

        total_stats = 0
        total_live = 0
        async with get_session() as db:
            result = await db.execute(select(Anlage))
            anlagen = result.scalars().all()
            for anlage in anlagen:
                for zp in zeitpunkte:
                    try:
                        n = await snapshot_anlage(db, anlage, zeitpunkt=zp)
                        total_stats += n
                    except Exception as e:
                        logger.debug(
                            f"Recovery snapshot_anlage Anlage {anlage.id} {zp}: "
                            f"{type(e).__name__}: {e}"
                        )
                # Live-Approximation für laufende Stunde (HA Statistics noch leer)
                try:
                    n = await live_snapshot_if_missing(
                        db, anlage, zeitpunkt=aktuelle_stunde
                    )
                    total_live += n
                except Exception as e:
                    logger.debug(
                        f"Recovery live_snapshot Anlage {anlage.id}: "
                        f"{type(e).__name__}: {e}"
                    )

        if total_stats > 0 or total_live > 0:
            logger.info(
                f"Startup-Snapshot-Recovery: {total_stats} aus HA-Statistics "
                f"+ {total_live} Live-Werte geschrieben"
            )

        # Sofortige Aggregation, damit das Energieprofil heute befüllt ist
        try:
            from backend.services.energie_profil_service import aggregate_today_all
            await aggregate_today_all()
        except Exception as e:
            logger.debug(f"Recovery Heute-Aggregation: {type(e).__name__}: {e}")

    except Exception as e:
        logger.debug(f"Startup-Snapshot-Recovery fehlgeschlagen: {type(e).__name__}: {e}")


async def energie_profil_heute_job() -> None:
    """Schreibt abgeschlossene Stunden des laufenden Tages (alle 15 Min)."""
    try:
        from backend.services.energie_profil_service import aggregate_today_all
        results = await aggregate_today_all()
        if results:
            ok = sum(1 for r in results.values() if r["status"] == "ok")
            logger.debug(f"Energie-Profil Heute: {ok}/{len(results)} Anlagen aktualisiert")
    except Exception as e:
        logger.debug(f"Energie-Profil Heute fehlgeschlagen: {type(e).__name__}: {e}")


async def energie_profil_aggregation_job() -> None:
    """Finalisiert Energieprofil des Vortags für alle Anlagen (täglich um 00:15)."""
    try:
        from backend.services.energie_profil_service import aggregate_yesterday_all
        results = await aggregate_yesterday_all()
        ok = sum(1 for r in results.values() if r["status"] == "ok")
        logger.info(f"Energie-Profil Vortag: {ok}/{len(results)} Anlagen finalisiert")
        await log_activity(
            kategorie="scheduler",
            aktion="Energie-Profil Aggregation",
            erfolg=True,
            details=f"{ok}/{len(results)} Anlagen erfolgreich",
        )
    except Exception as e:
        logger.warning(f"Energie-Profil Aggregation fehlgeschlagen: {type(e).__name__}: {e}")
        await log_activity(
            kategorie="scheduler",
            aktion="Energie-Profil Aggregation fehlgeschlagen",
            erfolg=False,
            details=f"{type(e).__name__}: {e}",
        )


async def prognose_prefetch_job() -> None:
    """Prefetcht Solar- und Wetterprognosen für alle Anlagen (alle 45 Min)."""
    try:
        from backend.services.prefetch_service import prefetch_all_prognosen
        await prefetch_all_prognosen()
    except Exception as e:
        logger.warning(f"Prognose-Prefetch fehlgeschlagen: {type(e).__name__}: {e}")


async def api_cache_cleanup_job() -> None:
    """Löscht abgelaufene L2-Cache-Einträge aus SQLite (täglich um 04:00)."""
    try:
        from backend.services.wetter.cache import cleanup_l2_cache
        count = await cleanup_l2_cache()
        if count > 0:
            await log_activity(
                kategorie="scheduler",
                aktion="API-Cache Cleanup",
                erfolg=True,
                details=f"{count} abgelaufene Einträge gelöscht",
            )
    except Exception as e:
        logger.warning(f"API-Cache Cleanup fehlgeschlagen: {type(e).__name__}: {e}")


async def mqtt_auto_publish_job() -> None:
    """
    Publiziert EEDC-KPIs für alle Anlagen via MQTT nach Home Assistant.

    Wird periodisch ausgeführt wenn MQTT_AUTO_PUBLISH=true gesetzt ist.
    Interval: MQTT_PUBLISH_INTERVAL Minuten (Default: 60).
    """
    try:
        from backend.core.database import get_session
        from backend.models.anlage import Anlage
        from backend.api.routes.ha_export import calculate_anlage_sensors
        from backend.services.mqtt_client import MQTTClient, MQTTConfig
        import os
        from sqlalchemy import select

        mqtt_config = MQTTConfig(
            host=os.environ.get("MQTT_HOST", "core-mosquitto"),
            port=int(os.environ.get("MQTT_PORT", "1883")),
            username=os.environ.get("MQTT_USER") or None,
            password=os.environ.get("MQTT_PASSWORD") or None,
        )
        client = MQTTClient(mqtt_config)

        if not client.is_available:
            logger.warning("MQTT Auto-Publish: aiomqtt nicht verfügbar")
            return

        published_total = 0
        anlagen_count = 0

        async with get_session() as db:
            result = await db.execute(select(Anlage))
            anlagen = result.scalars().all()

            for anlage in anlagen:
                try:
                    sensor_values = await calculate_anlage_sensors(db, anlage)
                    if not sensor_values:
                        continue
                    pub_result = await client.publish_all_sensors(
                        sensor_values, anlage.id, anlage.anlagenname
                    )
                    published_total += pub_result.get("published", 0)
                    anlagen_count += 1
                except Exception as e:
                    logger.warning(f"MQTT Auto-Publish Anlage {anlage.id}: {type(e).__name__}: {e}")

        logger.info(f"MQTT Auto-Publish: {published_total} Sensoren für {anlagen_count} Anlagen")
        await log_activity(
            kategorie="ha_export",
            aktion="MQTT Auto-Publish",
            erfolg=True,
            details=f"{published_total} Sensoren für {anlagen_count} Anlagen",
        )
    except Exception as e:
        logger.error(f"MQTT Auto-Publish fehlgeschlagen: {type(e).__name__}: {e}")
        await log_activity(
            kategorie="ha_export",
            aktion="MQTT Auto-Publish fehlgeschlagen",
            erfolg=False,
            details=f"{type(e).__name__}: {e}",
        )


# Singleton-Instanz
_scheduler: Optional[EEDCScheduler] = None


def get_scheduler() -> EEDCScheduler:
    """Gibt die Singleton-Instanz des Schedulers zurück."""
    global _scheduler
    if _scheduler is None:
        _scheduler = EEDCScheduler()
    return _scheduler


async def kraftstoffpreis_job() -> None:
    """
    Aktualisiert Kraftstoffpreise für alle Anlagen aus EU Oil Bulletin.

    Wöchentlich: Lädt aktuelle XLSX, befüllt fehlende Tage in TagesZusammenfassung
    und fehlende Monate in Monatsdaten (Monatsdurchschnitt).
    """
    try:
        from backend.core.database import get_session
        from backend.models.anlage import Anlage
        from backend.services.kraftstoff_preis_service import (
            backfill_kraftstoffpreise,
            backfill_monatsdaten_kraftstoffpreise,
        )
        from sqlalchemy import select

        async for db in get_session():
            result = await db.execute(select(Anlage))
            anlagen = result.scalars().all()

            gesamt_tage = 0
            gesamt_monate = 0
            for anlage in anlagen:
                land = anlage.standort_land or "DE"
                try:
                    info_t = await backfill_kraftstoffpreise(anlage.id, land, db)
                    gesamt_tage += info_t.get("aktualisiert", 0)
                    info_m = await backfill_monatsdaten_kraftstoffpreise(anlage.id, land, db)
                    gesamt_monate += info_m.get("aktualisiert", 0)
                except Exception as e:
                    logger.warning("Kraftstoffpreis-Backfill Anlage %d: %s", anlage.id, e)

            if gesamt_tage > 0 or gesamt_monate > 0:
                await log_activity(
                    kategorie="scheduler",
                    aktion="Kraftstoffpreis-Update",
                    erfolg=True,
                    details=f"{gesamt_tage} Tage + {gesamt_monate} Monate für {len(anlagen)} Anlagen",
                )
                logger.info("Kraftstoffpreis-Job: %d Tage, %d Monate aktualisiert",
                            gesamt_tage, gesamt_monate)
    except Exception as e:
        logger.warning("Kraftstoffpreis-Job fehlgeschlagen: %s: %s", type(e).__name__, e)


def start_scheduler() -> bool:
    """Startet den globalen Scheduler."""
    return get_scheduler().start()


def stop_scheduler() -> None:
    """Stoppt den globalen Scheduler."""
    get_scheduler().stop()
