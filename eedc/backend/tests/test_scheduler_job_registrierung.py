"""Die Scheduler-Jobs — neun standen in keinem Test namentlich (M11).

**Gemessen am 2026-08-24 per AST** über alle ``add_job(..., id=...)``-Aufrufe
des Baums: 19 Job-IDs, davon **neun** in keiner Testdatei namentlich —
``api_cache_cleanup`` · ``energie_profil_aggregation`` ·
``energie_profil_aggregation_recovery`` · ``energie_profil_heute`` ·
``korrekturprofil_aggregation`` · ``prognose_prefetch`` ·
``sensor_snapshot_5min`` · ``sensor_snapshot_5min_cleanup`` ·
``sensor_snapshot_preview``. Der Plan zu E6 nannte **acht**; die Zahl ist hier
erhoben, nicht abgeschrieben.

⚑ Eine Zahl im Titel wäre hier eine Zusicherung mit Verfallsdatum — die
Baseline unten IST die Zahl, und sie wächst mit jedem eingetragenen Job
(zuletzt ``energie_profil_archiv_nachzug``, N-388, 2026-09-04).

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
    # N-388 (2026-09-04): der Wetter-Archiv-Nachzug läuft BEDINGUNGSLOS.
    # #322 fragt an dieser Stelle „soll er das?" — hier ja: er hängt an keiner
    # Betriebsart und an keinem Schalter, und er nimmt sich selbst zurück, wo
    # nichts zu tun ist (keine Zusammenfassung für den Grenztag ⇒ `kein_tag`;
    # geschrumpfte HA-Historie ⇒ `uebersprungen`). Ein Schalter davor hieße,
    # dass eine falsche Einstrahlung je nach Konfiguration stehen bleibt.
    "energie_profil_archiv_nachzug",
    "korrekturprofil_aggregation",
    "connector_daily_poll",
    "prognose_prefetch",
    "api_cache_cleanup",
    "pvgis_aktualitaet",
    "kraftstoffpreis",
    # #395 Punkt 1 (2026-09-29): der Wetterwerte-Lückenschluss läuft
    # BEDINGUNGSLOS. #322 fragt hier „soll er das?" — ja, aus demselben Grund
    # wie der Archiv-Nachzug darüber: Er hängt an keiner Betriebsart und an
    # keinem Schalter, und er nimmt sich selbst zurück, wo nichts zu tun ist
    # (ohne Lücke fragt er keinen Anbieter — ein SELECT je Anlage und Nacht).
    # Er ist zudem die Bedingung, unter der die Vormonats-Vorbelegung der
    # Wetterfelder wegfallen durfte: ohne ihn bliebe ein Monat ohne Klick leer.
    "wetter_luecken",
    # HA-Bauform E2 (06.10.2026): der Konsistenzlauf der Kanalstatistik läuft BEDINGUNGSLOS. #322 fragt
    # „soll er das?" — ja: ohne HA nimmt er sich selbst zurück (`ha_nicht_erreichbar`, keine Abfrage), mit HA
    # kostet ein gleicher Spiegel vier Abfragen je Kanal-Abschnitt (gemessen, `test_kanal_konsistenz.py`).
    # Ein Schalter davor hieße, dass eine Korrektur in HA je nach Konfiguration nie ankommt.
    "kanal_konsistenz",
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
            ("energie_profil_archiv_nachzug", "2", "20"),
            ("korrekturprofil_aggregation", "2", "30"),
            ("kanal_konsistenz", "2", "45"),
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

    def test_der_archiv_nachzug_liegt_ZWISCHEN_heilung_und_korrekturprofil(
        self, scheduler
    ):
        """Beide Nachbarschaften sind Absicht, nicht Zufall (N-388).

        **Nach der Heilung (02:15):** beide schreiben mit `aggregate_day`, nur
        auf verschiedene Tage — laufen sie gleichzeitig, konkurrieren sie um
        denselben SQLite-Writer.
        **Vor dem Korrekturprofil (02:30):** der Nachzug berichtigt mit der
        Strahlung auch Bewölkung und Wettercode derselben Zeile, und genau die
        liest die Korrekturprofil-Aggregation. Läge er danach, käme die
        Berichtigung dort erst einen Tag später an.
        """
        heilung = self._cron(scheduler, "energie_profil_aggregation_recovery")
        nachzug = self._cron(scheduler, "energie_profil_archiv_nachzug")
        korrektur = self._cron(scheduler, "korrekturprofil_aggregation")
        as_paar = lambda f: (int(f["hour"]), int(f["minute"]))  # noqa: E731
        assert as_paar(heilung) < as_paar(nachzug) < as_paar(korrektur)

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


def _werte(feld: str, bereich: range) -> set[int]:
    """Die Werte eines Cron-Felds in den Formen, die der Scheduler nutzt: ``*``, ``n``, ``*/n``, ``a,b``.

    Eine andere Form wirft — dann ist dieser Test zu erweitern, statt still zu schweigen.
    """
    werte: set[int] = set()
    for teil in feld.split(","):
        if teil == "*":
            werte |= set(bereich)
        elif teil.startswith("*/"):
            werte |= set(bereich[:: int(teil[2:])])
        elif teil.isdigit():
            werte.add(int(teil))
        else:
            raise AssertionError(f"Cron-Form {feld!r} kennt dieser Test nicht — erweitern")
    return werte


#: Paare mit gleicher Minute, die es VOR dem Fund-Päckchen B schon gab (Auto-Publish auf :00 in der
#: Voreinstellung 60 min gegen drei tägliche Jobs auf der vollen Stunde). Nicht gemessen gestört, offen beim
#: Master (Bericht Funde B, 22.11.2026). Dieses Register schrumpft nur.
BESTAND_GLEICHE_MINUTE = {
    frozenset({"mqtt_auto_publish", "mqtt_energy_cleanup"}),   # 03:00
    frozenset({"mqtt_auto_publish", "api_cache_cleanup"}),     # 04:00
    frozenset({"mqtt_auto_publish", "kraftstoffpreis"}),       # 06:00
}


class TestKeineZweiJobsInDerselbenMinute:
    """Lab 21.11.2026 (F13): «MQTT Live Cleanup» (täglich 03:05) und der Stundenlauf (:05) starteten in derselben
    Sekunde; der Stundenlauf brach an allen Anlagen mit «database is locked» ab, die Stunde ab 02:00 fehlte bis 04:05.

    Geprüft wird die Job-Tabelle in der Voreinstellung mit MQTT-Inbound: kein Paar von Jobs mit fester Uhrzeit
    (``CronTrigger``) belegt dieselbe Stunde und Minute. Intervall-Jobs (``IntervalTrigger``) laufen ab ihrem
    Start und haben keine feste Minute — sie stehen nicht in dieser Prüfung. Konfigurierte Felder, keine Wanduhr.
    """

    @staticmethod
    def _belegung(s) -> dict[tuple[int, int], set[str]]:
        from apscheduler.triggers.cron import CronTrigger

        belegt: dict[tuple[int, int], set[str]] = {}
        for job in s._scheduler.get_jobs():
            if not isinstance(job.trigger, CronTrigger):
                continue
            felder = {f.name: str(f) for f in job.trigger.fields}
            for stunde in _werte(felder["hour"], range(24)):
                for minute in _werte(felder["minute"], range(60)):
                    belegt.setdefault((stunde, minute), set()).add(job.id)
        return belegt

    @pytest.mark.asyncio
    async def test_keine_zwei_cron_jobs_in_derselben_minute(self):
        s = EEDCScheduler()
        assert s.start() is True
        try:
            assert s.add_mqtt_snapshot_jobs() is True
            belegt = self._belegung(s)
        finally:
            s.stop()
        doppelt = {}
        for (stunde, minute), ids in belegt.items():
            paare = {frozenset({a, b}) for a in ids for b in ids if a < b}
            neu = paare - BESTAND_GLEICHE_MINUTE
            if neu:
                doppelt[f"{stunde:02d}:{minute:02d}"] = sorted(sorted(p) for p in neu)
        assert not doppelt, f"Jobs mit fester Uhrzeit in derselben Minute: {doppelt}"

    @pytest.mark.asyncio
    async def test_bestand_register_ist_nicht_verwaist(self):
        s = EEDCScheduler()
        assert s.start() is True
        try:
            assert s.add_mqtt_snapshot_jobs() is True
            belegt = self._belegung(s)
        finally:
            s.stop()
        gelebt = {frozenset({a, b}) for ids in belegt.values() for a in ids for b in ids if a < b}
        assert BESTAND_GLEICHE_MINUTE <= gelebt, sorted(sorted(p) for p in BESTAND_GLEICHE_MINUTE - gelebt)

    @pytest.mark.asyncio
    async def test_mqtt_live_cleanup_liegt_nicht_auf_einem_vielfachen_von_5(self):
        """Auto-Publish (*/5 … */60) und 5-Minuten-Snapshot (*/5) starten je nach Einstellung auf jedem Vielfachen von 5."""
        s = EEDCScheduler()
        assert s.start() is True
        try:
            assert s.add_mqtt_snapshot_jobs() is True
            felder = {f.name: str(f) for f in s._scheduler.get_job("mqtt_live_cleanup").trigger.fields}
        finally:
            s.stop()
        assert int(felder["minute"]) % 5 != 0
