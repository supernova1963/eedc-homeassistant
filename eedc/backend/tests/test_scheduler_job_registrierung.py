"""Die 19 Scheduler-Jobs — neun standen in keinem Test namentlich (M11).

**Gemessen am 2026-08-24 per AST** über alle ``add_job(..., id=...)``-Aufrufe
des Baums: 19 Job-IDs, davon **neun** in keiner Testdatei namentlich —
``api_cache_cleanup`` · ``energie_profil_aggregation`` ·
``energie_profil_aggregation_recovery`` · ``energie_profil_heute`` ·
``korrekturprofil_aggregation`` · ``prognose_prefetch`` ·
``sensor_snapshot_5min`` · ``sensor_snapshot_5min_cleanup`` ·
``sensor_snapshot_preview``. Der Plan zu E6 nannte **acht**; die Zahl ist hier
erhoben, nicht abgeschrieben.

Zwei Achsen:

1. **Die Registrierung als Baseline** — welche IDs entstehen beim Start, mit
   welchem Takt, und welche **bewusst nicht**. Ein Job, der still verschwindet
   oder seinen Takt wechselt, ist sonst nirgends sichtbar; genau diese Klasse
   hat #322 erzeugt (MQTT-Jobs liefen leer, weil sie bedingungslos entstanden).
2. **Der Recovery-Job** ``energie_profil_aggregation_recovery`` — er ist der
   Selbstheilungspfad aus #136 und wird nur in dem Fall gebraucht, in dem
   ohnehin schon etwas schiefgegangen ist.

⚠ **Keine Wanduhr-Behauptung.** Geprüft werden die *konfigurierten* Cron-Felder
und Intervalle, nicht ein Feuerzeitpunkt — sonst liefe die Datei in
``Europe/Berlin`` anders als in ``UTC``/``Pacific/Auckland``
(CLAUDE.md §Gates, CI-Lauf zu v4.0.14).
"""

from __future__ import annotations

import pytest
import pytest_asyncio

from backend.services.scheduler import (
    SCHEDULER_AVAILABLE,
    EEDCScheduler,
    energie_profil_aggregation_job,
    energie_profil_aggregation_recovery_job,
)

pytestmark = pytest.mark.skipif(
    not SCHEDULER_AVAILABLE, reason="APScheduler nicht installiert"
)

#: Jobs, die `start()` immer registriert — Stand 2026-08-24, erhoben per AST.
#: ⚠ `sensor_snapshot_5min` und `sensor_snapshot_5min_cleanup` hängen an
#: `settings.live_snapshot_5min_enabled` und stehen deshalb NICHT hier.
IMMER_REGISTRIERT = {
    "monthly_snapshot",
    "mqtt_auto_publish",
    "sensor_snapshot",
    "sensor_snapshot_preview",
    "energie_profil_heute",
    "energie_profil_aggregation",
    "energie_profil_aggregation_recovery",
    "korrekturprofil_aggregation",
    "connector_daily_poll",
    "prognose_prefetch",
    "api_cache_cleanup",
    "pvgis_aktualitaet",
    "kraftstoffpreis",
}

#: Erst über `add_mqtt_snapshot_jobs()` (#322).
NUR_MIT_MQTT = {
    "mqtt_energy_snapshot",
    "mqtt_energy_cleanup",
    "mqtt_live_snapshot",
    "mqtt_live_cleanup",
}

#: Nur bei `LIVE_SNAPSHOT_5MIN_ENABLED=true`.
NUR_MIT_5MIN = {"sensor_snapshot_5min", "sensor_snapshot_5min_cleanup"}


@pytest_asyncio.fixture
async def scheduler():
    s = EEDCScheduler()
    assert s.start() is True
    try:
        yield s
    finally:
        s.stop()


class TestRegistrierungsBaseline:
    """Welche Jobs entstehen — und welche bewusst nicht."""

    async def test_alle_erwarteten_jobs_sind_da(self, scheduler):
        ids = {j.id for j in scheduler._scheduler.get_jobs()}
        fehlend = sorted(IMMER_REGISTRIERT - ids)
        assert not fehlend, (
            f"{len(fehlend)} Job(s) werden nicht mehr registriert: {fehlend}. "
            "Ein still verschwundener Job faellt sonst nirgends auf."
        )

    async def test_kein_job_ist_unbemerkt_dazugekommen(self, scheduler):
        ids = {j.id for j in scheduler._scheduler.get_jobs()}
        neu = sorted(ids - IMMER_REGISTRIERT - NUR_MIT_5MIN)
        assert not neu, (
            f"Neue Job-ID(s): {neu}. Das ist erlaubt — trag sie hier ein und "
            "entscheide dabei, ob sie bedingungslos laufen sollen (#322)."
        )

    def test_mqtt_jobs_entstehen_NICHT_beim_start(self, scheduler):
        """#322: sonst melden sie alle 5 Min Erfolg, ohne etwas zu tun."""
        ids = {j.id for j in scheduler._scheduler.get_jobs()}
        assert not (ids & NUR_MIT_MQTT)

    async def test_jeder_job_traegt_einen_namen(self, scheduler):
        """Der Name steht in den System-Logs — eine leere Zeile hilft niemandem."""
        ohne = [j.id for j in scheduler._scheduler.get_jobs() if not j.name]
        assert ohne == []

    async def test_job_ids_sind_eindeutig(self, scheduler):
        ids = [j.id for j in scheduler._scheduler.get_jobs()]
        assert len(ids) == len(set(ids))


class TestTakteDerNeunUngedecktenJobs:
    """Der Takt jedes bislang ungedeckten Jobs — als konfiguriertes Feld.

    ⚠ Kein Feuerzeitpunkt, kein ``datetime.now()`` — die Felder selbst.
    """

    @staticmethod
    def _cron(scheduler, job_id: str) -> dict:
        trigger = scheduler._scheduler.get_job(job_id).trigger
        return {f.name: str(f) for f in trigger.fields}

    @staticmethod
    def _intervall_minuten(scheduler, job_id: str) -> float:
        trigger = scheduler._scheduler.get_job(job_id).trigger
        return trigger.interval.total_seconds() / 60

    @pytest.mark.parametrize(
        "job_id,stunde,minute",
        [
            ("energie_profil_aggregation", "0", "15"),
            ("energie_profil_aggregation_recovery", "2", "15"),
            ("korrekturprofil_aggregation", "2", "30"),
            ("api_cache_cleanup", "4", "0"),
        ],
    )
    async def test_taegliche_jobs_stehen_auf_ihrer_uhrzeit(
        self, scheduler, job_id, stunde, minute
    ):
        felder = self._cron(scheduler, job_id)
        assert felder["hour"] == stunde
        assert felder["minute"] == minute

    def test_das_selfhealing_liegt_NACH_der_finalisierung(self, scheduler):
        """#136: zwei Stunden Abstand geben HA Zeit, die LTS nachzupflegen.

        Die Reihenfolge ist der ganze Zweck des Jobs — laege er davor, holte
        er dieselben fehlenden Werte ein zweites Mal nicht.
        """
        finalisierung = self._cron(scheduler, "energie_profil_aggregation")
        heilung = self._cron(scheduler, "energie_profil_aggregation_recovery")
        assert int(heilung["hour"]) > int(finalisierung["hour"])

    def test_korrekturprofil_laeuft_NACH_dem_selfhealing(self, scheduler):
        """Es liest die Stundenzeilen, die die Heilung gerade erst schreibt."""
        heilung = self._cron(scheduler, "energie_profil_aggregation_recovery")
        korrektur = self._cron(scheduler, "korrekturprofil_aggregation")
        assert (int(korrektur["hour"]), int(korrektur["minute"])) > (
            int(heilung["hour"]), int(heilung["minute"])
        )

    async def test_energie_profil_heute_laeuft_viertelstuendlich(self, scheduler):
        assert self._intervall_minuten(scheduler, "energie_profil_heute") == 15

    async def test_prognose_prefetch_bleibt_unter_der_cache_ttl(self, scheduler):
        """45 Min innerhalb des 60-Min-Cache — sonst laeuft der Cache leer."""
        minuten = self._intervall_minuten(scheduler, "prognose_prefetch")
        assert minuten == 45
        assert minuten < 60

    async def test_snapshot_preview_liegt_kurz_vor_dem_stundenende(self, scheduler):
        """#146: die laufende Stunde soll am Stundenende sichtbar sein."""
        felder = self._cron(scheduler, "sensor_snapshot_preview")
        assert felder["minute"] == "55"

    def test_der_stuendliche_snapshot_liegt_5_minuten_NACH_der_stunde(
        self, scheduler
    ):
        """#135: der Offset gibt HA Zeit, die Stunde zu finalisieren."""
        assert self._cron(scheduler, "sensor_snapshot")["minute"] == "5"


class TestFuenfMinutenJobsHaengenAmSchalter:
    """`LIVE_SNAPSHOT_5MIN_ENABLED` — beide Richtungen gemessen."""

    async def _mit_schalter(self, monkeypatch, wert: bool):
        from backend.core.config import settings

        monkeypatch.setattr(settings, "live_snapshot_5min_enabled", wert)
        s = EEDCScheduler()
        assert s.start() is True
        try:
            return {j.id for j in s._scheduler.get_jobs()}
        finally:
            s.stop()

    async def test_abgeschaltet_fehlen_beide(self, monkeypatch):
        ids = await self._mit_schalter(monkeypatch, False)
        assert not (ids & NUR_MIT_5MIN)

    async def test_eingeschaltet_sind_beide_da(self, monkeypatch):
        ids = await self._mit_schalter(monkeypatch, True)
        assert NUR_MIT_5MIN <= ids


class TestRecoveryJob:
    """Der Selbstheilungspfad aus #136 — er läuft, wenn schon etwas kaputt ist."""

    @pytest.fixture
    def lauf(self, monkeypatch):
        """Ersetzt `aggregate_yesterday_all` und protokolliert die Aufrufe."""
        aufrufe: list[str] = []
        zustand = {"ergebnis": {1: {"status": "ok"}}, "wirft": None}

        async def _aggregate():
            aufrufe.append("aggregate_yesterday_all")
            if zustand["wirft"]:
                raise zustand["wirft"]
            return zustand["ergebnis"]

        monkeypatch.setattr(
            "backend.services.energie_profil_service.aggregate_yesterday_all",
            _aggregate,
        )

        protokoll: list[dict] = []

        async def _log(**kwargs):
            protokoll.append(kwargs)

        monkeypatch.setattr("backend.services.scheduler.log_activity", _log)
        return aufrufe, zustand, protokoll

    @pytest.mark.asyncio
    async def test_der_recovery_job_faltet_denselben_vortag(self, lauf):
        """Kein zweiter Pfad — dieselbe Aggregation, `aggregate_day` ist idempotent."""
        aufrufe, _zustand, _protokoll = lauf
        await energie_profil_aggregation_recovery_job()
        assert aufrufe == ["aggregate_yesterday_all"]

    @pytest.mark.asyncio
    async def test_er_meldet_sich_als_SELF_HEALING_im_aktivitaetslog(self, lauf):
        """Sonst stehen zwei ununterscheidbare Zeilen im Protokoll des Anwenders."""
        _aufrufe, _zustand, protokoll = lauf
        await energie_profil_aggregation_recovery_job()
        await energie_profil_aggregation_job()
        aktionen = [e["aktion"] for e in protokoll]
        assert aktionen == [
            "Energie-Profil Self-Healing",
            "Energie-Profil Aggregation",
        ]

    @pytest.mark.asyncio
    async def test_ein_fehler_reisst_den_scheduler_NICHT_mit(self, lauf):
        """Ein werfender Job wuerde sonst den APScheduler-Lauf abbrechen.

        ⚠ Und er schweigt nicht: der Fehlschlag steht mit ``erfolg=False`` im
        Aktivitaetslog. Ein still verschluckter Selbstheilungslauf waere für
        den Anwender nicht von einem gelungenen zu unterscheiden.
        """
        _aufrufe, zustand, protokoll = lauf
        zustand["wirft"] = RuntimeError("HA nicht erreichbar")
        await energie_profil_aggregation_recovery_job()   # darf nicht werfen
        assert len(protokoll) == 1
        assert protokoll[0]["erfolg"] is False
        assert protokoll[0]["aktion"] == "Energie-Profil Self-Healing fehlgeschlagen"
        assert "HA nicht erreichbar" in protokoll[0]["details"]

    @pytest.mark.asyncio
    async def test_ohne_anlagen_meldet_er_null_von_null(self, lauf):
        _aufrufe, zustand, protokoll = lauf
        zustand["ergebnis"] = {}
        await energie_profil_aggregation_recovery_job()
        assert protokoll[0]["details"] == "0/0 Anlagen erfolgreich"

    @pytest.mark.asyncio
    async def test_gescheiterte_anlagen_zaehlen_nicht_als_erfolg(self, lauf):
        _aufrufe, zustand, protokoll = lauf
        zustand["ergebnis"] = {
            1: {"status": "ok"},
            2: {"status": "fehler"},
            3: {"status": "keine_daten"},
        }
        await energie_profil_aggregation_recovery_job()
        assert protokoll[0]["details"] == "1/3 Anlagen erfolgreich"
