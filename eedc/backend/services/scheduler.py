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


def start_scheduler() -> bool:
    """Startet den globalen Scheduler."""
    return get_scheduler().start()


def stop_scheduler() -> None:
    """Stoppt den globalen Scheduler."""
    get_scheduler().stop()
