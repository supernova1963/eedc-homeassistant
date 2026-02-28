"""
EEDC Scheduler Service.

Background-Scheduler für periodische Tasks wie Monatswechsel-Snapshots.
Verwendet APScheduler für Cron-basierte Job-Ausführung.
"""

import logging
from datetime import datetime
from typing import Optional, Callable, Awaitable
from contextlib import asynccontextmanager

try:
    from apscheduler.schedulers.asyncio import AsyncIOScheduler
    from apscheduler.triggers.cron import CronTrigger
    from apscheduler.jobstores.memory import MemoryJobStore
    SCHEDULER_AVAILABLE = True
except ImportError:
    SCHEDULER_AVAILABLE = False

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from backend.core.database import async_session_maker
from backend.models.anlage import Anlage
from backend.services.ha_mqtt_sync import get_ha_mqtt_sync_service
from backend.services.ha_state_service import get_ha_state_service

logger = logging.getLogger(__name__)


class EEDCScheduler:
    """
    Background-Scheduler für periodische Tasks.

    Jobs:
    - Monatswechsel-Snapshot: Am 1. jeden Monats um 00:01
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

            self._scheduler.start()
            self._running = True
            logger.info("EEDC Scheduler gestartet")
            return True

        except Exception as e:
            logger.error(f"Fehler beim Starten des Schedulers: {e}")
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

    Ablauf:
    1. Alle Anlagen mit sensor_mapping laden
    2. Für jede Anlage: Aktuelle Zählerstände aus Mapping extrahieren
    3. Neue Startwerte auf MQTT publizieren
    4. Snapshot in DB speichern (optional)

    Args:
        anlage_id: Optional - nur für eine bestimmte Anlage

    Returns:
        Dict mit Statistiken
    """
    now = datetime.now()
    logger.info(f"Monatswechsel-Snapshot gestartet: {now.isoformat()}")

    results = {
        "timestamp": now.isoformat(),
        "anlagen_processed": 0,
        "anlagen_success": 0,
        "anlagen_failed": 0,
        "details": []
    }

    mqtt_sync = get_ha_mqtt_sync_service()
    ha_state = get_ha_state_service()

    async with async_session_maker() as db:
        # Anlagen mit sensor_mapping laden
        query = select(Anlage).where(Anlage.sensor_mapping.isnot(None))
        if anlage_id:
            query = query.where(Anlage.id == anlage_id)

        result = await db.execute(query)
        anlagen = result.scalars().all()

        for anlage in anlagen:
            results["anlagen_processed"] += 1

            try:
                # sensor_mapping enthält die Zuordnungen
                mapping = anlage.sensor_mapping or {}

                # mqtt_setup_complete prüfen
                if not mapping.get("mqtt_setup_complete"):
                    results["anlagen_failed"] += 1
                    results["details"].append({
                        "anlage_id": anlage.id,
                        "anlage_name": anlage.anlagenname,
                        "status": "mqtt_not_configured",
                        "message": "MQTT-Setup nicht abgeschlossen",
                    })
                    continue

                # Aktuelle Zählerstände aus HA lesen und als Startwerte publizieren
                zaehlerstaende: dict[str, float] = {}
                updated_fields = 0
                errors = []

                # Basis-Sensoren (Einspeisung, Netzbezug, etc.)
                basis = mapping.get("basis", {})
                for feld, config in basis.items():
                    if config and config.get("strategie") == "sensor" and config.get("sensor_id"):
                        sensor_id = config["sensor_id"]
                        # Aktuellen Wert aus HA lesen
                        wert = await ha_state.get_sensor_state(sensor_id)
                        if wert is not None:
                            zaehlerstaende[feld] = wert
                            # Startwert auf MQTT publizieren
                            start_key = f"mwd_{feld}_start"
                            success = await mqtt_sync.mqtt.update_month_start_value(
                                anlage_id=anlage.id,
                                key=start_key,
                                wert=wert,
                            )
                            if success:
                                updated_fields += 1
                            else:
                                errors.append(f"MQTT-Publish fehlgeschlagen für {feld}")
                        else:
                            errors.append(f"Sensor {sensor_id} nicht verfügbar")

                # Investitionen-Sensoren
                investitionen = mapping.get("investitionen", {})
                for inv_id, inv_config in investitionen.items():
                    if isinstance(inv_config, dict):
                        felder = inv_config.get("felder", inv_config)
                    else:
                        felder = {}
                    for feld, config in felder.items():
                        if config and config.get("strategie") == "sensor" and config.get("sensor_id"):
                            sensor_id = config["sensor_id"]
                            wert = await ha_state.get_sensor_state(sensor_id)
                            if wert is not None:
                                feld_key = f"inv{inv_id}_{feld}"
                                zaehlerstaende[feld_key] = wert
                                start_key = f"mwd_{feld_key}_start"
                                success = await mqtt_sync.mqtt.update_month_start_value(
                                    anlage_id=anlage.id,
                                    key=start_key,
                                    wert=wert,
                                )
                                if success:
                                    updated_fields += 1
                                else:
                                    errors.append(f"MQTT-Publish fehlgeschlagen für {feld_key}")

                detail = {
                    "anlage_id": anlage.id,
                    "anlage_name": anlage.anlagenname,
                    "status": "success" if not errors else "partial",
                    "updated_fields": updated_fields,
                    "zaehlerstaende": zaehlerstaende,
                    "errors": errors if errors else None,
                }

                if errors and updated_fields == 0:
                    detail["status"] = "failed"
                    results["anlagen_failed"] += 1
                else:
                    results["anlagen_success"] += 1

                results["details"].append(detail)

            except Exception as e:
                logger.error(f"Fehler bei Anlage {anlage.id}: {e}")
                results["anlagen_failed"] += 1
                results["details"].append({
                    "anlage_id": anlage.id,
                    "anlage_name": anlage.anlagenname,
                    "status": "error",
                    "message": str(e),
                })

    logger.info(
        f"Monatswechsel-Snapshot abgeschlossen: "
        f"{results['anlagen_success']}/{results['anlagen_processed']} erfolgreich"
    )

    return results


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
