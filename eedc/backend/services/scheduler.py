"""
EEDC Scheduler Service.

Background-Scheduler für periodische Tasks.
Verwendet APScheduler für Cron-basierte Job-Ausführung.
"""

import logging
from datetime import datetime, timedelta
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


def publish_takt_trigger(interval_minuten: int):
    """Trigger für den MQTT-Auto-Publish — an der **Uhr** ausgerichtet, nicht am Start.

    **Warum das eine eigene Funktion ist (F-29, rapahl-PN 2026-08-11):** Bis
    hierher hing der Publish an einem ``IntervalTrigger`` mit
    ``next_run_time = Start + 2 min``. Sein Takt lief damit ab dem Boot-Zeitpunkt
    des Add-ons durch — bei der Voreinstellung von 60 Minuten also **einmal je
    Stunde mit einem Versatz, den allein der letzte Neustart bestimmt**. Der
    Börsenpreis wechselt aber zur vollen Stunde: gemeldet und an zwei
    HA-Verläufen belegt wechselte der Sensor um **09:12:56** und — nach einem
    Update-Neustart — um **11:08:02**, beide Male mit dem *richtigen* Wert der
    laufenden Stunde. Wer Laden oder Entladen daran hängt, steuert nach jedem
    Stundenwechsel im Mittel eine halbe Stunde mit den Werten der Vorstunde.

    Ausgerichtet wird, wo das Intervall zur Uhr passt; sonst bleibt es beim
    bisherigen Verhalten, statt einen krummen Takt zurechtzubiegen:

    * Intervall teilt eine Stunde (5 · 10 · 15 · 20 · 30 · 60) ⇒ zur Minute 0,
      15, … der Stunde.
    * Intervall ist ein voller Stundenschritt und teilt den Tag (120 · 180 ·
      240 · 360 · 720 · 1440) ⇒ zur vollen Stunde im passenden Raster.
    * alles andere (z. B. 25 oder 90) ⇒ ``IntervalTrigger`` wie bisher.

    Die fünf Sekunden Versatz sind kein Warten auf Daten — der Preis der neuen
    Stunde steht längst in der DB —, sondern halten die Stundenbestimmung des
    Jobs (``datetime.now().hour``) sicher auf der neuen Stunde.
    """
    if 60 % interval_minuten == 0:
        minute = "0" if interval_minuten == 60 else f"*/{interval_minuten}"
        return CronTrigger(minute=minute, second=5)
    if interval_minuten % 60 == 0 and 1440 % interval_minuten == 0:
        stunden = interval_minuten // 60
        # 24 h ist kein Schrittwert im Stundenfeld (0–23), sondern schlicht Mitternacht.
        stunden_ausdruck = "0" if stunden >= 24 else f"*/{stunden}"
        return CronTrigger(hour=stunden_ausdruck, minute=0, second=5)
    return IntervalTrigger(minutes=interval_minuten)


class EEDCScheduler:
    """
    Background-Scheduler für periodische Tasks.

    Jobs:
    - Monatswechsel-Snapshot: Am 1. jeden Monats um 00:01
    - Energie-Profil Aggregation: Täglich um 00:15 (Vortag)
    - MQTT Energy/Live Snapshot + Cleanup: nur wenn MQTT-Inbound aktiv ist
      (add_mqtt_snapshot_jobs(), aus main.py nach erfolgreichem Inbound-Start)
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
            # N-123 (geprueft 2026-09-01): Der Job rechnet nichts — er schreibt
            # einen Log- und einen Aktivitaets-Eintrag („Monatswechsel
            # registriert"). Das war einmal mehr; die Monatsdaten kommen seit
            # Langem aus der HA-Statistik. BEWUSST NICHT ENTFERNT: der
            # Aktivitaets-Eintrag ist die einzige Stelle, an der ein Anwender im
            # Protokoll sieht, dass eedc den Monatswechsel bemerkt hat. Er kostet
            # nichts und ist ein Lebenszeichen — Entscheid Gernot.
            self._scheduler.add_job(
                monthly_snapshot_job,
                CronTrigger(day=1, hour=0, minute=1),
                id="monthly_snapshot",
                name="Monatswechsel Snapshot",
                replace_existing=True,
            )

            # MQTT Energy/Live Snapshot + Cleanup werden NICHT hier registriert,
            # sondern erst wenn MQTT-Inbound tatsächlich aktiv ist
            # (add_mqtt_snapshot_jobs(), aufgerufen aus main.py). Ohne MQTT liefen
            # die 5-Min-Jobs sonst dauerhaft leer und füllten die System-Logs mit
            # „executed successfully" — irreführend für Anwender ohne MQTT-Setup
            # (#322 detLAN). MQTT-Inbound ist Vorbedingung für Gateway UND
            # Connector-Bridge (beide in main.py darin verschachtelt), daher
            # erfasst dieser Schalter alle MQTT-Pfade inkl. Standalone/Connectoren.

            # MQTT Auto-Publish: Job wird IMMER registriert, der Aktiv-Check läuft
            # IM Job (`auto_publish_aktiv` = Broker-Toggle UND Export-Toggle).
            # B7-5b: Der Export-Toggle liegt seit Datenquellen-V4 in der DB, der
            # Scheduler startet aber nur beim Boot — hinge die Registrierung an der
            # Einstellung, wirkte der Schalter erst nach einem Neustart.
            # M-B-Entscheid Gernot 2026-06-10 („Export an ⇒ Auto-Publish an") lebt
            # im ENV-Fallback von `export_aktiviert` weiter (Bestandsschutz).
            from backend.core.config import settings as app_settings
            interval = max(5, app_settings.mqtt_publish_interval)  # Minimum 5 Minuten
            self._scheduler.add_job(
                mqtt_auto_publish_job,
                publish_takt_trigger(interval),
                id="mqtt_auto_publish",
                name=f"MQTT Auto-Publish (alle {interval} Min)",
                replace_existing=True,
                # Start-Publish: der Takt feuert sonst erst zum nächsten Rasterpunkt
                # — neue Sensor-Definitionen wären nach einem Add-on-Update bis zu
                # 60 min unsichtbar (Rainer/Gernot 2026-06-10). Dieser eine Lauf
                # liegt bewusst NEBEN dem Raster; ab dem zweiten gilt wieder die Uhr
                # (F-29), denn `next_run_time` verschiebt nur den ersten Lauf.
                next_run_time=datetime.now() + timedelta(minutes=2),
            )
            logger.info(f"MQTT Auto-Publish registriert: alle {interval} Minuten (Aktiv-Check je Lauf)")

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

            # Live-Snapshot 5-Min (Phase 1, KONZEPT-LIVE-SNAPSHOT-5MIN.md).
            # Liest alle 5 Min Counter aus HA short_term_statistics in
            # sensor_snapshots. Cleanup täglich um 00:30 löscht Sub-Hour-Slots
            # > 24h. Nur aktiv wenn LIVE_SNAPSHOT_5MIN_ENABLED=true.
            #
            # CronTrigger '*/5:30': 30s nach jedem 5-Min-Boundary, gibt HA
            # Zeit, den short_term-Eintrag zu schreiben. Ohne den Offset
            # würden wir Latenz-Jitter direkt sehen.
            if app_settings.live_snapshot_5min_enabled:
                self._scheduler.add_job(
                    sensor_snapshot_5min_job,
                    CronTrigger(minute="*/5", second=30),
                    id="sensor_snapshot_5min",
                    name="Sensor-Snapshots 5-Min (Live-Heute)",
                    replace_existing=True,
                )
                self._scheduler.add_job(
                    sensor_snapshot_5min_cleanup_job,
                    CronTrigger(hour=0, minute=30),
                    id="sensor_snapshot_5min_cleanup",
                    name="Sensor-Snapshots 5-Min Cleanup (>24h)",
                    replace_existing=True,
                )
                logger.info("Live-Snapshot 5-Min aktiviert (Cron */5:30 + Cleanup 00:30)")

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

            # Energie-Profil Vortag Self-Healing: Täglich um 02:15 (Issue #136).
            # Wenn HA Long-Term-Statistics für 00:00 verspätet liefert (Counter
            # ohne state_class), fehlt beim 00:15-Run der Folgetags-Snapshot,
            # damit auch Slot 23 + Tageswerte. Zweiter Versuch nach 2h gibt HA
            # Zeit nachzupflegen; aggregate_day ist idempotent (Delete+Insert)
            # und get_snapshot zieht über HA-Statistics-Fallback nach.
            self._scheduler.add_job(
                energie_profil_aggregation_recovery_job,
                CronTrigger(hour=2, minute=15),
                id="energie_profil_aggregation_recovery",
                name="Energie-Profil Vortag Self-Healing (02:15)",
                replace_existing=True,
            )

            # Archiv-Nachzug Wetter: Täglich um 02:20 (N-388).
            # Die Einstrahlung der letzten fünf Tage ist ein VORLÄUFIGER
            # Forecast-Wert (Archiv/ERA5 hinkt 2-5 Tage nach) und wurde bisher
            # nie ersetzt — an bewölkten Tagen bis Faktor 8,7 zu klein, mit
            # Folgen für PR, Einstrahlungs-Spalte und den Doppelerfassungs-
            # Verdacht des Daten-Checkers. Der Job aggregiert je Anlage den
            # EINEN Tag neu, der die Cutoff-Grenze in dieser Nacht passiert hat;
            # `_get_wetter_ist` zieht dann von selbst das Archiv.
            # Lage im Takt ist Absicht: NACH dem Self-Healing (02:15), damit die
            # beiden nicht denselben Tag gleichzeitig schreiben, und VOR der
            # Korrekturprofil-Aggregation (02:30), damit die berichtigte
            # Bewölkung noch in derselben Nacht dort ankommt.
            self._scheduler.add_job(
                energie_profil_archiv_nachzug_job,
                CronTrigger(hour=2, minute=20),
                id="energie_profil_archiv_nachzug",
                name="Wetter-Archiv-Nachzug Grenztag (02:20)",
                replace_existing=True,
            )

            # Korrekturprofil-Aggregation: Täglich um 02:30 (nach Energie-Profil-Recovery 02:15).
            # Aggregator schreibt sonnenstand_wetter / sonnenstand / skalar-Profile pro Anlage,
            # invalidiert Live-Cache automatisch (siehe korrekturprofil_lookup.invalidate_cache).
            self._scheduler.add_job(
                korrekturprofil_aggregation_job,
                CronTrigger(hour=2, minute=30),
                id="korrekturprofil_aggregation",
                name="Korrekturprofil-Aggregation (Sonnenstand × Wetter)",
                replace_existing=True,
            )

            # Connector-Tagesabruf: Täglich um 03:30 (#300). Bewusst hier und
            # NICHT in add_mqtt_snapshot_jobs(): die Connector-Bridge pollt nur
            # bei aktivem MQTT-Inbound — ohne MQTT blieben Connector-Anlagen
            # sonst komplett ohne automatische Zählerstände (Safi105).
            # Loggt nur, wenn mindestens ein Connector konfiguriert ist (#322).
            self._scheduler.add_job(
                connector_daily_poll_job,
                CronTrigger(hour=3, minute=30),
                id="connector_daily_poll",
                name="Connector-Tagesabruf (Zählerstände)",
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

            # Solarprognose-Aktualität: Täglich um 04:30, nach dem Cache-Cleanup
            # (#363). Prüft je Anlage, ob die gespeicherte PVGIS-Prognose noch
            # zur Anlage passt, und ruft nur bei Abweichung neu ab — PVGIS
            # rechnet auf einem festen Klimamittel, ein Turnus-Abruf wäre Last
            # ohne Wirkung. Ohne Abweichung geht kein einziger Request raus.
            self._scheduler.add_job(
                pvgis_aktualitaet_job,
                CronTrigger(hour=4, minute=30),
                id="pvgis_aktualitaet",
                name="Solarprognose-Aktualität (Neuabruf bei Anlagenänderung)",
                replace_existing=True,
            )

            # Kraftstoffpreis: TÄGLICH 06:00 (das Oil Bulletin selbst erscheint
            # montags — der Takt hier richtet sich nicht nach der Quelle,
            # sondern danach, wann eine Monatszeile ENTSTEHT).
            #
            # ⚠ Bis 2026-08-23 lief er ``day_of_week="tue"`` — als einziger
            # Wochen-Takt im ganzen Scheduler, alle anderen Jobs laufen
            # täglich oder öfter, die Tagesaggregation hat sogar einen eigenen
            # Recovery-Lauf. Eine Monatszeile, die zwischen zwei Dienstagen
            # entsteht (Monatsabschluss, Import, Erst-Einrichtung), blieb damit
            # bis zu SIEBEN TAGE ohne Marktpreis, und der E-Auto-Vergleich
            # rechnete solange still mit dem Modellwert (1,65 €/L) statt mit
            # dem Preis des Monats. Gemeldet von gruaGit (Discussion #394,
            # 23.08.): „Für Juni wird ein leeres Feld bei Vergleichspreise
            # angezeigt" — auf die ausdrückliche Einladung hin nachzusehen.
            #
            # Täglich kostet nichts: beide Backfills steigen ohne offene Zeile
            # aus, BEVOR die 4,25-MB-XLSX geladen wird.
            self._scheduler.add_job(
                kraftstoffpreis_job,
                CronTrigger(hour=6, minute=0),
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

    def add_mqtt_snapshot_jobs(self) -> bool:
        """Registriert die MQTT-Snapshot/Cleanup-Jobs (alle 5 Min + täglich).

        Erst aufgerufen, wenn MQTT-Inbound aktiv ist (main.py). Ohne MQTT laufen
        diese Jobs sonst dauerhaft leer und protokollieren irreführend (#322).
        Idempotent via replace_existing — ein Reconnect registriert nicht doppelt.
        """
        if not self.is_running:
            logger.warning("add_mqtt_snapshot_jobs: Scheduler läuft nicht")
            return False

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
        logger.info("MQTT-Snapshot-Jobs registriert (Inbound aktiv)")
        return True

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


async def sensor_snapshot_5min_job() -> None:
    """
    Schreibt 5-Min-Snapshots aller gemappten Counter aus HA short_term_statistics
    (Phase 1, KONZEPT-LIVE-SNAPSHOT-5MIN.md). Läuft */5:30 für alle Anlagen.

    zeitpunkt = floor(now, 5min) — der Slot, den HA gerade in
    statistics_short_term geschrieben hat. Idempotent über UniqueConstraint;
    der hourly :05-Job überschreibt :00-Slots nicht (snapshot_anlage_5min
    skippt belegte Slots).
    """
    try:
        from sqlalchemy import select
        from backend.core.database import get_session
        from backend.models.anlage import Anlage
        from backend.services.sensor_snapshot_service import snapshot_anlage_5min

        now = datetime.now()
        minute_floor = (now.minute // 5) * 5
        zeitpunkt = now.replace(minute=minute_floor, second=0, microsecond=0)

        total_anlagen = 0
        total_snapshots = 0

        async with get_session() as db:
            result = await db.execute(select(Anlage))
            anlagen = result.scalars().all()
            for anlage in anlagen:
                try:
                    n = await snapshot_anlage_5min(db, anlage, zeitpunkt=zeitpunkt)
                    if n > 0:
                        total_snapshots += n
                        total_anlagen += 1
                except Exception as e:
                    logger.debug(
                        f"5-Min-Snapshot Anlage {anlage.id} fehlgeschlagen: "
                        f"{type(e).__name__}: {e}"
                    )

        if total_snapshots > 0:
            logger.debug(
                f"5-Min-Snapshots: {total_snapshots} Werte für {total_anlagen} "
                f"Anlagen @ {zeitpunkt.isoformat()}"
            )
    except Exception as e:
        logger.debug(f"5-Min-Snapshot Job fehlgeschlagen: {type(e).__name__}: {e}")


async def sensor_snapshot_5min_cleanup_job() -> None:
    """
    Löscht Sub-Hour-Slots (zeitpunkt.minute != 0) älter als 24h
    (Phase 1, täglich 00:30).

    Variante A: hourly :00-Snapshots bleiben dauerhaft, 5-Min-Slots werden
    nach einem Tag entsorgt — Steady-State ~288 transiente Rows pro Anlage.
    """
    try:
        from backend.core.database import get_session
        from backend.services.sensor_snapshot_service import cleanup_5min_snapshots

        async with get_session() as db:
            count = await cleanup_5min_snapshots(db)
            if count > 0:
                logger.info(f"5-Min-Snapshot Cleanup: {count} Sub-Hour-Slots gelöscht")
                await log_activity(
                    kategorie="scheduler",
                    aktion="5-Min-Snapshot Cleanup",
                    erfolg=True,
                    details=f"{count} Sub-Hour-Slots > 24h gelöscht",
                )
    except Exception as e:
        logger.warning(f"5-Min-Snapshot Cleanup fehlgeschlagen: {type(e).__name__}: {e}")


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
        from backend.core.config import settings as app_settings
        from backend.core.database import get_session
        from backend.models.anlage import Anlage
        from backend.services.sensor_snapshot_service import (
            snapshot_anlage,
            snapshot_anlage_5min,
            live_snapshot_if_missing,
        )

        now = datetime.now()
        aktuelle_stunde = now.replace(minute=0, second=0, microsecond=0)
        zeitpunkte = [aktuelle_stunde - timedelta(hours=h) for h in range(7)]  # 0..-6

        # 5-Min-Slots seit 00:00 heute (Phase 1, nur wenn Feature aktiv).
        # HA short_term_statistics hält ~10–14 Tage; ein Tag ist kein Stress.
        # Slots :00 werden vom hourly-Pfad bereits abgedeckt → überspringen.
        five_min_slots: list[datetime] = []
        if app_settings.live_snapshot_5min_enabled:
            tag_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
            slot = tag_start
            while slot <= now:
                if slot.minute != 0:  # :00 macht der hourly-Pfad
                    five_min_slots.append(slot)
                slot += timedelta(minutes=5)

        total_stats = 0
        total_live = 0
        total_5min = 0
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
                # 5-Min-Slots des heutigen Tages aus HA short_term nachholen
                for zp in five_min_slots:
                    try:
                        n = await snapshot_anlage_5min(db, anlage, zeitpunkt=zp)
                        total_5min += n
                    except Exception as e:
                        logger.debug(
                            f"Recovery 5min Anlage {anlage.id} {zp}: "
                            f"{type(e).__name__}: {e}"
                        )

        if total_stats > 0 or total_live > 0 or total_5min > 0:
            logger.info(
                f"Startup-Snapshot-Recovery: {total_stats} aus HA-Statistics "
                f"+ {total_live} Live-Werte + {total_5min} 5-Min-Slots geschrieben"
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
    await _run_yesterday_aggregation(label="Aggregation")


async def energie_profil_aggregation_recovery_job() -> None:
    """Self-Healing-Wiederholung des Vortags um 02:15 (Issue #136).

    Holt Tage nach, bei denen HA-LTS für 00:00 erst nach dem 00:15-Lauf
    nachgepflegt wurde. aggregate_day ist idempotent.
    """
    await _run_yesterday_aggregation(label="Self-Healing")


async def _run_yesterday_aggregation(label: str) -> None:
    try:
        from backend.services.energie_profil_service import aggregate_yesterday_all
        results = await aggregate_yesterday_all()
        ok = sum(1 for r in results.values() if r["status"] == "ok")
        logger.info(f"Energie-Profil Vortag ({label}): {ok}/{len(results)} Anlagen finalisiert")
        await log_activity(
            kategorie="scheduler",
            aktion=f"Energie-Profil {label}",
            erfolg=True,
            details=f"{ok}/{len(results)} Anlagen erfolgreich",
        )
    except Exception as e:
        logger.warning(f"Energie-Profil {label} fehlgeschlagen: {type(e).__name__}: {e}")
        await log_activity(
            kategorie="scheduler",
            aktion=f"Energie-Profil {label} fehlgeschlagen",
            erfolg=False,
            details=f"{type(e).__name__}: {e}",
        )


async def energie_profil_archiv_nachzug_job() -> None:
    """Zieht den Wetter-Grenztag aus dem Archiv nach (täglich um 02:20, N-388).

    Details, Messung und der Grund für den Vorflug stehen im Modul-Docstring
    von ``services/energie_profil/archiv_nachzug.py``.
    """
    try:
        from backend.services.energie_profil.archiv_nachzug import (
            archiv_grenztag,
            archiv_nachzug_all,
        )

        datum = archiv_grenztag()
        results = await archiv_nachzug_all()
        ok = sum(1 for r in results.values() if r["status"] == "ok")
        uebersprungen = sum(
            1 for r in results.values() if r["status"] == "uebersprungen"
        )
        logger.info(
            "Wetter-Archiv-Nachzug %s: %d/%d Anlagen nachgezogen, %d übersprungen",
            datum, ok, len(results), uebersprungen,
        )
        await log_activity(
            kategorie="scheduler",
            aktion="Wetter-Archiv-Nachzug",
            erfolg=True,
            details=(
                f"{datum}: {ok}/{len(results)} Anlagen nachgezogen"
                + (f", {uebersprungen} übersprungen" if uebersprungen else "")
            ),
        )
    except Exception as e:
        logger.warning(
            "Wetter-Archiv-Nachzug fehlgeschlagen: %s: %s", type(e).__name__, e
        )
        await log_activity(
            kategorie="scheduler",
            aktion="Wetter-Archiv-Nachzug fehlgeschlagen",
            erfolg=False,
            details=f"{type(e).__name__}: {e}",
        )


async def korrekturprofil_aggregation_job() -> None:
    """Aggregiert das Korrekturprofil pro Anlage (täglich um 02:30).

    Iteriert über alle Anlagen mit Koordinaten und ruft den Aggregator auf.
    Idempotent — bestehende Profile werden überschrieben, der Live-Cache via
    Lookup-Service automatisch invalidiert.
    """
    try:
        from sqlalchemy import select

        from backend.core.database import get_session
        from backend.models.anlage import Anlage
        from backend.services.korrekturprofil_aggregator import (
            aggregiere_korrekturprofil_anlage,
        )

        ok = 0
        skipped = 0
        async with get_session() as db:
            anlagen_result = await db.execute(
                select(Anlage).where(
                    Anlage.latitude.isnot(None),
                    Anlage.longitude.isnot(None),
                )
            )
            anlagen = list(anlagen_result.scalars().all())
            for anlage in anlagen:
                try:
                    res = await aggregiere_korrekturprofil_anlage(anlage, db)
                    if res.get("status") == "ok":
                        ok += 1
                    else:
                        skipped += 1
                except Exception as ex:
                    logger.warning(
                        "Korrekturprofil-Aggregation Anlage %s fehlgeschlagen: %s: %s",
                        anlage.id,
                        type(ex).__name__,
                        ex,
                    )
        logger.info(
            "Korrekturprofil-Aggregation: %d ok, %d übersprungen", ok, skipped
        )
        await log_activity(
            kategorie="scheduler",
            aktion="Korrekturprofil-Aggregation",
            erfolg=True,
            details=f"{ok} ok, {skipped} übersprungen",
        )
    except Exception as e:
        logger.warning(
            "Korrekturprofil-Aggregation fehlgeschlagen: %s: %s",
            type(e).__name__,
            e,
        )
        await log_activity(
            kategorie="scheduler",
            aktion="Korrekturprofil-Aggregation fehlgeschlagen",
            erfolg=False,
            details=f"{type(e).__name__}: {e}",
        )


async def connector_daily_poll_job() -> None:
    """Täglicher Connector-Poll (#300): Zählerstände aller Connector-Anlagen.

    Liest einmal täglich (03:30) die kumulativen kWh-Zählerstände über den
    gemeinsamen Fetch-Pfad (`fetch_and_store_snapshot` — gleiche Logik wie
    der manuelle „Aktuelle Daten anfordern"-Endpoint) und speichert sie als
    Snapshot. Läuft unabhängig vom MQTT-Inbound.

    Damit füllen sich Monatsabschluss-Vorschlag und /connectors/monatswerte
    (beide rechnen die Monats-Differenz read-seitig aus den Snapshots) auch
    ohne MQTT-Setup. Koexistenz mit der Connector-MQTT-Bridge ist harmlos:
    die Bridge publisht nur auf MQTT-Topics und schreibt keine
    meter_snapshots; zusätzliche Snapshots ändern die Monats-Differenz nicht
    (sie nutzt die Randwerte des Monats).
    """
    try:
        from sqlalchemy import select
        from backend.core.database import get_session
        from backend.models.anlage import Anlage
        from backend.services.connectors.fetch_service import (
            fetch_and_store_snapshot,
            hat_geraete_connector,
        )

        ok = 0
        fehler = 0
        fehler_beispiele: list[str] = []

        async with get_session() as db:
            result = await db.execute(select(Anlage))
            anlagen = result.scalars().all()

            for anlage in anlagen:
                if not hat_geraete_connector(anlage.connector_config):
                    continue
                try:
                    await fetch_and_store_snapshot(anlage)
                    ok += 1
                except Exception as e:
                    # Lesefehler ist im Service bereits als Activity geloggt —
                    # hier nur zählen, damit eine Anlage die Schleife nicht abbricht.
                    fehler += 1
                    if len(fehler_beispiele) < 3:
                        fehler_beispiele.append(
                            f"Anlage {anlage.id}: {type(e).__name__}: {e}"
                        )

        if ok or fehler:
            fehl = f", {fehler} fehlgeschlagen" if fehler else ""
            grund = f" — z. B. {'; '.join(fehler_beispiele)}" if fehler_beispiele else ""
            logger.info(f"Connector-Tagesabruf: {ok} Anlagen ok{fehl}{grund}")
            await log_activity(
                kategorie="scheduler",
                aktion="Connector-Tagesabruf",
                erfolg=fehler == 0,
                details=f"{ok} Anlagen ok{fehl}{grund}",
            )
    except Exception as e:
        logger.warning(f"Connector-Tagesabruf fehlgeschlagen: {type(e).__name__}: {e}")
        await log_activity(
            kategorie="scheduler",
            aktion="Connector-Tagesabruf fehlgeschlagen",
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

    Der Job ist immer registriert und prüft bei JEDEM Lauf selbst, ob er laufen
    darf (B7-5b): Broker-Verbindung aktiviert UND Export-Toggle an. Nur so wirkt
    der DB-Toggle sofort statt erst nach einem Neustart.
    Interval: MQTT_PUBLISH_INTERVAL Minuten (Default: 60).
    """
    try:
        from backend.core.database import get_session
        from backend.models.anlage import Anlage
        from backend.services.ha_mqtt_sync import publish_anlage_sensors
        from backend.services.mqtt_broker_settings import auto_publish_aktiv
        from sqlalchemy import select

        published_total = 0
        failed_total = 0
        anlagen_count = 0
        fehler_beispiele: list[str] = []

        async with get_session() as db:
            if not await auto_publish_aktiv(db):
                logger.debug("MQTT Auto-Publish übersprungen: Broker oder Export deaktiviert")
                return

            result = await db.execute(select(Anlage))
            anlagen = result.scalars().all()

            for anlage in anlagen:
                try:
                    # Zentraler Outbound-Pfad (#655): liefert echte success/failed-Zahlen.
                    pub = await publish_anlage_sensors(db, anlage)
                    if not pub["available"]:
                        logger.warning("MQTT Auto-Publish: aiomqtt nicht verfügbar")
                        return
                    if pub["no_data"]:
                        continue
                    published_total += pub["success"]
                    failed_total += pub["failed"]
                    anlagen_count += 1
                    for e in pub.get("errors", []):
                        if len(fehler_beispiele) < 3:
                            fehler_beispiele.append(f"Anlage {anlage.id} {e}")
                except Exception as e:
                    logger.warning(f"MQTT Auto-Publish Anlage {anlage.id}: {type(e).__name__}: {e}")

        fehl = f", {failed_total} fehlgeschlagen" if failed_total else ""
        # Fehlergründe mitloggen — sonst ist „X fehlgeschlagen" wieder nichtssagend (#655).
        grund = f" — z. B. {'; '.join(fehler_beispiele)}" if fehler_beispiele else ""
        logger.info(f"MQTT Auto-Publish: {published_total} Sensoren für {anlagen_count} Anlagen{fehl}{grund}")
        await log_activity(
            kategorie="ha_export",
            aktion="MQTT Auto-Publish",
            erfolg=failed_total == 0,
            details=f"{published_total} Sensoren für {anlagen_count} Anlagen{fehl}{grund}",
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


async def pvgis_aktualitaet_job() -> None:
    """Zieht die Solarprognose nach, wenn sie nicht mehr zur Anlage passt (#363).

    Ausgelöst wird ausschließlich durch eine ABWEICHUNG (Nennleistung,
    Ausrichtung, Neigung, Standort, Horizontprofil, Strahlungsdatensatz) —
    bewusst nicht durch das Alter der Prognose: PVGIS rechnet auf einem festen
    Klimamittel, ein turnusmäßiger Abruf liefert dieselbe Zahl. Die Regel steht
    als SoT in `services/pvgis_aktualitaet.py`, dort auch die Messung.

    Die eingestellten Systemverluste werden übernommen, nicht auf den Default
    zurückgesetzt. Die alte Prognose bleibt als inaktive Zeile in der Historie
    und ist über die Einstellungs-Seite wieder aktivierbar — ein Neuabruf
    verwirft nichts.

    Läuft täglich statt beim Start: ein blockierender HTTP-Aufruf im Startpfad
    hat das Add-on schon einmal in eine Neustart-Schleife gebracht (v3.45.7).
    """
    try:
        from backend.api.routes.pvgis import speichere_pvgis_prognose
        from backend.core.database import get_session
        from backend.models.anlage import Anlage
        from backend.services.pvgis_aktualitaet import pruefe_prognose
        from sqlalchemy import select

        async with get_session() as db:
            anlagen = (await db.execute(select(Anlage))).scalars().all()

            for anlage in anlagen:
                try:
                    abweichung = await pruefe_prognose(db, anlage.id)
                    if abweichung is None:
                        continue

                    await speichere_pvgis_prognose(
                        anlage_id=anlage.id,
                        system_losses=abweichung.system_losses,
                        db=db,
                    )
                    await db.commit()

                    # Eine automatisch geänderte SOLL-Zahl muss nachvollziehbar
                    # bleiben — der Grund steht im Aktivitätsprotokoll, nicht nur
                    # im Log (#363).
                    await log_activity(
                        kategorie="scheduler",
                        aktion="Solarprognose aktualisiert",
                        erfolg=True,
                        details=f"Anlage {anlage.id}: {abweichung.text}",
                    )
                    logger.info(
                        "PVGIS-Aktualität: Anlage %d neu abgerufen (%s)",
                        anlage.id, abweichung.text,
                    )
                except Exception as e:
                    # Ein nicht erreichbares PVGIS darf den Lauf nicht abbrechen:
                    # die bestehende Prognose bleibt gültig, der nächste Tag
                    # versucht es erneut.
                    logger.warning(
                        "PVGIS-Aktualität Anlage %d: %s: %s",
                        anlage.id, type(e).__name__, e,
                    )
    except Exception as e:
        logger.warning("PVGIS-Aktualitäts-Job fehlgeschlagen: %s: %s", type(e).__name__, e)


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

        async with get_session() as db:
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


async def kraftstoffpreis_startup_recovery() -> None:
    """Holt beim Start einen verpassten Kraftstoffpreis-Lauf nach.

    **Warum es das braucht (Discussion #394, gruaGit, 2026-08-23):** Der
    Cron-Trigger hat keine Misfire-Recovery. Läuft die Box um 06:00 nicht —
    Update, Neustart, abgeschaltete Nacht —, fällt der Lauf ersatzlos aus, und
    eine Monatszeile ohne Marktpreis bleibt bis zum nächsten Morgen leer. Beim
    Wochen-Takt davor war das eine Woche. Derselbe Grund wie bei
    ``sensor_snapshot_startup_recovery``, nur eine Zeitebene höher.

    **Bewusst NICHT im ``start_scheduler()``-Zweig aufgerufen** (main.py): ohne
    APScheduler gibt es überhaupt keinen Cron, dann ist der Startlauf der
    einzige Weg. Dieselbe Begründung wie beim Community-Nachsenden.

    Kostet ohne offene Zeilen keinen einzigen Request — beide Backfills zählen
    erst und laden dann.
    """
    import asyncio

    try:
        await asyncio.sleep(90)  # dem Start nicht in die Quere kommen
        await kraftstoffpreis_job()
    except Exception as e:
        logger.debug("Kraftstoffpreis-Startlauf fehlgeschlagen: %s: %s", type(e).__name__, e)


def start_scheduler() -> bool:
    """Startet den globalen Scheduler."""
    return get_scheduler().start()


def stop_scheduler() -> None:
    """Stoppt den globalen Scheduler."""
    get_scheduler().stop()


def enable_mqtt_snapshot_jobs() -> bool:
    """Aktiviert die MQTT-Snapshot/Cleanup-Jobs (nur wenn MQTT-Inbound läuft)."""
    return get_scheduler().add_mqtt_snapshot_jobs()
