"""RF-41 Schritt 0 — `main.py::lifespan` startet und stoppt in fester Reihenfolge.

Bis zum 3.11.2026 fuhr kein Test den Start der App als Ablauf: sieben Testdateien importieren
`backend.main` nur für Routen und OpenAPI (Schwesterdatei `test_routen_baseline.py`: Routen-
und OpenAPI-Baseline derselben App; `test_n237_lts_import_ohne_supervisor.py` startet die echte
Lifespan über `TestClient`, prüft aber nur eine Route). Diese Datei ist das Gate für den Schnitt
der Lifespan in Phasen (Komplexitäts-Paket RF-40 …, Sitzung S2): **die Reihenfolge der Start-
und Stop-Schritte ist Vertrag** — der Scheduler startet erst nach der Datenbank, die
MQTT-Dienste stoppen vor dem Scheduler, die Ausgabezeilen bleiben Wort für Wort.

Vier Proben:

1. **Echt** — `async with lifespan(app)` gegen eine Wegwerf-Datenbank unter `tmp_path`
   (`backend.core.database.engine`/`async_session_maker` umgehängt), `EEDC_DISABLE_SCHEDULER=true`,
   MQTT-Import aus, kein `SUPERVISOR_TOKEN`, Netz gesperrt (conftest). Erwartet: kein Fehler,
   die Ausgabezeilen in der aufgezeichneten Reihenfolge.
2. **Gestellt** — Scheduler, Hintergrund-Aufgaben (`asyncio.create_task` am Modul `backend.main`),
   PIN-Rückweg, HA-Verbindung, Cache-Warmup, MQTT-Konfiguration sowie die Stop-Getter von
   Gateway und Bridge sind Fakes, die in EINE Ereignisliste schreiben (dazu `print` am Modul
   `backend.main`). Je Fall (Cache warm/kalt × Scheduler startet/startet nicht) ist die Liste am
   HEAD aufgezeichnet; Start und Stop des Schedulers je genau einmal, Stop nach dem `yield`.
3. **MQTT gestellt** — `_load_mqtt_config` liefert einen Broker, Inbound/Gateway/Bridge sind Fakes:
   Inbound startet nicht · Inbound mit Gateway-Mapping und Bridge-Gerät · Gateway und Bridge starten
   nicht · Inbound ohne beides.
4. **Fehlerpfade** — jeder abgesicherte Schritt wirft; der Start läuft durch, die Log-Zeilen von
   `backend.main` stehen wortgleich in der aufgezeichneten Reihenfolge (jede Phase behält ihr `try`).

Benannte Grenze: Supervisor-, Demo-Daten- und echte Broker-Zweige laufen hier nicht; ihr
Prüfstand bleibt der Lab-Start. Die Proben lesen keine echte Uhr (die Hintergrund-Aufgaben werden
nur benannt und geschlossen, nie ausgeführt).
"""

from __future__ import annotations

import asyncio
import logging

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import backend.main as main
from backend.core import database
from backend.core.database import Base


# ── aufgezeichnet 3.11.2026 am HEAD 6a2e97f3b (Lauf auf 0e0c2f9f4; `main.py` dort gleich 6a2e97f3b) ──
# Probe 4 (FEHLER_*) steht unten bei ihrem Test, aufgezeichnet im selben Lauf.

ECHT_AUSGABE = [
    "EEDC Backend startet...",
    "Datenbank initialisiert.",
    "Scheduler deaktiviert (EEDC_DISABLE_SCHEDULER=true) — statische Demo.",
    "EEDC Backend wird beendet...",
]

_START_KOPF = [
    "print:EEDC Backend startet...",
    "print:Datenbank initialisiert.",
    "ruf:pruefe_ruecksetzung",
    "ruf:aktualisiere_ha_verbindung",
    "print:HA-Verbindung für die Langzeitstatistik übernommen.",
    "ruf:warmup_l1_from_l2",
]
_STOP_OHNE_INBOUND = [
    "yield",
    "ruf:gateway.stop",
    "ruf:bridge.stop",
    "ruf:stop_scheduler",
    "print:EEDC Backend wird beendet...",
]
_HINTERGRUND = [
    "task:_nachsenden",
    "task:kraftstoffpreis_startup_recovery",
    "task:nachfuellen_nach_dem_start",
]

GESTELLT = {
    ("warm", True): _START_KOPF + [
        "print:Cache-Warmup: 3 Einträge aus L2 geladen.",
        "ruf:start_scheduler",
        "print:Scheduler gestartet.",
        "task:sensor_snapshot_startup_recovery",
        *_HINTERGRUND,
        "ruf:_load_mqtt_config",
        "task:_initial_prefetch",
    ] + _STOP_OHNE_INBOUND,
    ("kalt", True): _START_KOPF + [
        "task:prefetch_all_prognosen",
        "print:Cache kalt — Sofort-Prefetch gestartet.",
        "ruf:start_scheduler",
        "print:Scheduler gestartet.",
        "task:sensor_snapshot_startup_recovery",
        *_HINTERGRUND,
        "ruf:_load_mqtt_config",
        "task:_initial_prefetch",
    ] + _STOP_OHNE_INBOUND,
    ("warm", False): _START_KOPF + [
        "print:Cache-Warmup: 3 Einträge aus L2 geladen.",
        "ruf:start_scheduler",
        "print:Scheduler konnte nicht gestartet werden (APScheduler nicht installiert?).",
        *_HINTERGRUND,
        "ruf:_load_mqtt_config",
        "task:_initial_prefetch",
    ] + _STOP_OHNE_INBOUND,
    ("kalt", False): _START_KOPF + [
        "task:prefetch_all_prognosen",
        "print:Cache kalt — Sofort-Prefetch gestartet.",
        "ruf:start_scheduler",
        "print:Scheduler konnte nicht gestartet werden (APScheduler nicht installiert?).",
        *_HINTERGRUND,
        "ruf:_load_mqtt_config",
        "task:_initial_prefetch",
    ] + _STOP_OHNE_INBOUND,
}

_MQTT_KOPF = _START_KOPF + [
    "print:Cache-Warmup: 3 Einträge aus L2 geladen.",
    "ruf:start_scheduler",
    "print:Scheduler gestartet.",
    "task:sensor_snapshot_startup_recovery",
    *_HINTERGRUND,
    "ruf:_load_mqtt_config",
    "ruf:init_mqtt_inbound_service(127.0.0.1:1883, user=None)",
    "ruf:inbound.start",
]
_STOP_MIT_INBOUND = ["yield", "ruf:inbound.stop"] + _STOP_OHNE_INBOUND[1:]

MQTT = {
    "inbound_startet_nicht": _MQTT_KOPF + [
        "print:  MQTT-Inbound: konnte nicht gestartet werden",
        "task:_initial_prefetch",
    ] + _STOP_MIT_INBOUND,
    "mit_mapping_und_geraet": _MQTT_KOPF + [
        "print:  MQTT-Inbound: aktiv (127.0.0.1:1883)",
        "ruf:enable_mqtt_snapshot_jobs",
        "task:_initial_snapshot",
        "ruf:init_mqtt_gateway_service(127.0.0.1:1883, user=None)",
        "ruf:gateway.load_mappings(1: haus/pv -> pv_leistung_w)",
        "ruf:gateway.start",
        "print:  MQTT-Gateway: aktiv (1 Mappings)",
        "ruf:init_connector_mqtt_bridge(127.0.0.1:1883, user=None)",
        "ruf:build_targets_from_db",
        "ruf:bridge.load_targets(1)",
        "ruf:bridge.start",
        "print:  Connector-Bridge: aktiv (1 Geräte)",
        "task:_initial_prefetch",
    ] + _STOP_MIT_INBOUND,
    "gateway_und_bridge_starten_nicht": _MQTT_KOPF + [
        "print:  MQTT-Inbound: aktiv (127.0.0.1:1883)",
        "ruf:enable_mqtt_snapshot_jobs",
        "task:_initial_snapshot",
        "ruf:init_mqtt_gateway_service(127.0.0.1:1883, user=None)",
        "ruf:gateway.load_mappings(1: haus/pv -> pv_leistung_w)",
        "ruf:gateway.start",
        "print:  MQTT-Gateway: konnte nicht gestartet werden",
        "ruf:init_connector_mqtt_bridge(127.0.0.1:1883, user=None)",
        "ruf:build_targets_from_db",
        "ruf:bridge.load_targets(1)",
        "ruf:bridge.start",
        "print:  Connector-Bridge: konnte nicht gestartet werden",
        "task:_initial_prefetch",
    ] + _STOP_MIT_INBOUND,
    "ohne_mapping_ohne_geraet": _MQTT_KOPF + [
        "print:  MQTT-Inbound: aktiv (127.0.0.1:1883)",
        "ruf:enable_mqtt_snapshot_jobs",
        "task:_initial_snapshot",
        "ruf:init_mqtt_gateway_service(127.0.0.1:1883, user=None)",
        "print:  MQTT-Gateway: keine Mappings konfiguriert",
        "ruf:init_connector_mqtt_bridge(127.0.0.1:1883, user=None)",
        "ruf:build_targets_from_db",
        "print:  Connector-Bridge: keine Connectors konfiguriert",
        "task:_initial_prefetch",
    ] + _STOP_MIT_INBOUND,
}


# ── Werkzeug ──────────────────────────────────────────────────────────────────

@pytest_asyncio.fixture
async def wegwerf_db(tmp_path, monkeypatch):
    """Eine Datei-Datenbank je Test; die Produktiv-Fabrik zeigt für die Dauer des Tests darauf."""
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path}/eedc.db", future=True)
    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    monkeypatch.setattr(database, "engine", engine)
    monkeypatch.setattr(database, "async_session_maker", maker)
    yield maker
    await engine.dispose()


@pytest.fixture
def umgebung(monkeypatch):
    """Kein Supervisor, kein PIN-Rückweg, MQTT-Import aus der Umgebung aus."""
    from backend.core import sperre
    from backend.core.config import settings

    monkeypatch.delenv("SUPERVISOR_TOKEN", raising=False)
    monkeypatch.delenv(sperre.RESET_ENV, raising=False)
    monkeypatch.setattr(settings, "mqtt_enabled", False)
    return monkeypatch


class _AsyncioAmModul:
    """Steht am Modul `backend.main` für `asyncio`: benennt jede Hintergrund-Aufgabe und schließt sie ungelaufen."""

    def __init__(self, ereignisse: list[str], werfen: frozenset[str] = frozenset()):
        self._ereignisse, self._werfen = ereignisse, werfen

    def create_task(self, coro):
        name = coro.__name__
        coro.close()
        if name in self._werfen:
            self._ereignisse.append(f"task-fehler:{name}")
            raise RuntimeError(f"gestellt:{name}")
        self._ereignisse.append(f"task:{name}")
        return None

    def __getattr__(self, name):
        return getattr(asyncio, name)


class _Dienst:
    """Fake für Inbound/Gateway/Bridge: jeder Aufruf landet in der Ereignisliste."""

    def __init__(self, name: str, ereignisse: list[str], startet: bool = True):
        self._name, self._ereignisse, self._startet = name, ereignisse, startet

    async def start(self):
        self._ereignisse.append(f"ruf:{self._name}.start")
        return self._startet

    async def stop(self):
        self._ereignisse.append(f"ruf:{self._name}.stop")

    def load_mappings(self, mappings):
        teile = ", ".join(f"{m.id}: {m.quell_topic} -> {m.ziel_key}" for m in mappings)
        self._ereignisse.append(f"ruf:{self._name}.load_mappings({teile})")

    def load_targets(self, targets):
        self._ereignisse.append(f"ruf:{self._name}.load_targets({len(targets)})")


def _stelle(umgebung, ereignisse, *, cache_eintraege, scheduler_startet, mqtt_cfg=None):
    """Hängt die Fakes an die Stellen, die die Lifespan zur Laufzeit nachschlägt."""
    from backend.core import sperre
    from backend.services import connector_mqtt_bridge, ha_connection, mqtt_gateway_service, scheduler
    from backend.services.wetter import cache

    mp = umgebung
    mp.setenv("EEDC_DISABLE_SCHEDULER", "false")
    mp.setattr(main, "asyncio", _AsyncioAmModul(ereignisse))
    mp.setattr(main, "print", lambda *a, **k: ereignisse.append("print:" + " ".join(map(str, a))), raising=False)

    async def _pruefe(_session):
        ereignisse.append("ruf:pruefe_ruecksetzung")
        return False

    async def _ha(_session):
        ereignisse.append("ruf:aktualisiere_ha_verbindung")
        return True

    async def _warmup():
        ereignisse.append("ruf:warmup_l1_from_l2")
        return cache_eintraege

    async def _mqtt_cfg():
        ereignisse.append("ruf:_load_mqtt_config")
        return mqtt_cfg

    def _start():
        ereignisse.append("ruf:start_scheduler")
        return scheduler_startet

    mp.setattr(sperre, "pruefe_ruecksetzung", _pruefe)
    mp.setattr(ha_connection, "aktualisiere_ha_verbindung", _ha)
    mp.setattr(cache, "warmup_l1_from_l2", _warmup)
    mp.setattr(main, "_load_mqtt_config", _mqtt_cfg)
    mp.setattr(main, "start_scheduler", _start)
    mp.setattr(main, "stop_scheduler", lambda: ereignisse.append("ruf:stop_scheduler"))
    mp.setattr(mqtt_gateway_service, "get_mqtt_gateway_service", lambda: _Dienst("gateway", ereignisse))
    mp.setattr(connector_mqtt_bridge, "get_connector_mqtt_bridge", lambda: _Dienst("bridge", ereignisse))
    mp.setattr(scheduler, "enable_mqtt_snapshot_jobs", lambda: ereignisse.append("ruf:enable_mqtt_snapshot_jobs"))


async def _laufe(ereignisse: list[str]) -> None:
    async with main.lifespan(main.app):
        ereignisse.append("yield")


# ── Probe 1: echt ─────────────────────────────────────────────────────────────

async def test_start_und_stop_echt_ohne_scheduler_ohne_mqtt(wegwerf_db, umgebung, capsys, caplog):
    umgebung.setenv("EEDC_DISABLE_SCHEDULER", "true")
    caplog.set_level(logging.DEBUG, logger="backend.main")

    async with main.lifespan(main.app):
        start = capsys.readouterr().out.splitlines()
    stop = capsys.readouterr().out.splitlines()

    assert "Datenbank initialisiert." in start
    assert start + stop == ECHT_AUSGABE
    assert [r.getMessage() for r in caplog.records if r.name == "backend.main"] == []


# ── Probe 2: gestellt ─────────────────────────────────────────────────────────

@pytest.mark.parametrize("cache", ["warm", "kalt"])
@pytest.mark.parametrize("scheduler_startet", [True, False])
async def test_reihenfolge_start_stop_gestellt(wegwerf_db, umgebung, cache, scheduler_startet):
    ereignisse: list[str] = []
    _stelle(umgebung, ereignisse, cache_eintraege=3 if cache == "warm" else 0,
            scheduler_startet=scheduler_startet)

    await _laufe(ereignisse)

    assert ereignisse.count("ruf:start_scheduler") == 1
    assert ereignisse.count("ruf:stop_scheduler") == 1
    assert ereignisse.index("ruf:start_scheduler") < ereignisse.index("yield") < ereignisse.index("ruf:stop_scheduler")
    assert ereignisse == GESTELLT[(cache, scheduler_startet)]


# ── Probe 3: MQTT gestellt ────────────────────────────────────────────────────

_BROKER = {"enabled": True, "host": "127.0.0.1", "port": 1883, "username": "", "password": ""}


async def _mapping_anlegen(maker) -> None:
    from backend.models.mqtt_gateway_mapping import MqttGatewayMapping
    from backend.tests import factories

    async with maker() as s:
        conn = await s.connection()
        await conn.run_sync(Base.metadata.create_all)
        a = await factories.anlage(s, anlagenname="L")
        s.add(MqttGatewayMapping(anlage_id=a.id, quell_topic="haus/pv", ziel_key="pv_leistung_w", aktiv=True))
        await s.commit()


@pytest.mark.parametrize("fall", ["inbound_startet_nicht", "mit_mapping_und_geraet", "gateway_und_bridge_starten_nicht",
                                  "ohne_mapping_ohne_geraet"])
async def test_reihenfolge_mqtt_gestellt(wegwerf_db, umgebung, fall):
    from backend.services import connector_mqtt_bridge, mqtt_gateway_service, mqtt_inbound_service

    ereignisse: list[str] = []
    _stelle(umgebung, ereignisse, cache_eintraege=3, scheduler_startet=True, mqtt_cfg=dict(_BROKER))
    mit = fall in ("mit_mapping_und_geraet", "gateway_und_bridge_starten_nicht")
    dienste_starten = fall != "gateway_und_bridge_starten_nicht"
    if mit:
        await _mapping_anlegen(wegwerf_db)

    def _fabrik(name, dienst):
        def _init(*_a, **k):
            host = k.get("host", k.get("mqtt_host"))
            port = k.get("port", k.get("mqtt_port"))
            user = k.get("username", k.get("mqtt_username"))
            ereignisse.append(f"ruf:{name}({host}:{port}, user={user})")
            return dienst
        return _init

    async def _targets(_session):
        ereignisse.append("ruf:build_targets_from_db")
        return ["geraet"] if mit else []

    umgebung.setattr(mqtt_inbound_service, "init_mqtt_inbound_service", _fabrik(
        "init_mqtt_inbound_service", _Dienst("inbound", ereignisse, startet=fall != "inbound_startet_nicht")))
    umgebung.setattr(mqtt_gateway_service, "init_mqtt_gateway_service", _fabrik(
        "init_mqtt_gateway_service", _Dienst("gateway", ereignisse, startet=dienste_starten)))
    umgebung.setattr(connector_mqtt_bridge, "init_connector_mqtt_bridge", _fabrik(
        "init_connector_mqtt_bridge", _Dienst("bridge", ereignisse, startet=dienste_starten)))
    umgebung.setattr(connector_mqtt_bridge, "build_targets_from_db", _targets)

    await _laufe(ereignisse)

    assert ereignisse == MQTT[fall]


# ── Probe 4: jeder abgesicherte Schritt wirft ─────────────────────────────────
#
# Jede Phase behält ihr eigenes `try/except`: ein Fehler in einem Schritt hält den Start nicht an, die Meldung
# geht in das Log von `backend.main`. Die beiden `create_task` ohne `try` (`_initial_snapshot`, `_initial_prefetch`)
# werfen hier bewusst nicht — sie sind heute nicht abgesichert, und die Probe hält den Stand fest, nicht ein Ideal.

FEHLER_EREIGNISSE = [
    "print:EEDC Backend startet...",
    "print:Datenbank initialisiert.",
    "ruf:pruefe_ruecksetzung",
    "ruf:aktualisiere_ha_verbindung",
    "ruf:warmup_l1_from_l2",
    "task-fehler:prefetch_all_prognosen",
    "ruf:start_scheduler",
    "print:Scheduler gestartet.",
    "task-fehler:sensor_snapshot_startup_recovery",
    "task-fehler:_nachsenden",
    "task-fehler:kraftstoffpreis_startup_recovery",
    "task-fehler:nachfuellen_nach_dem_start",
    "ruf:_load_mqtt_config",
    "ruf:init_mqtt_inbound_service(127.0.0.1:1883, user=None)",
    "ruf:inbound.start",
    "print:  MQTT-Inbound: aktiv (127.0.0.1:1883)",
    "ruf:enable_mqtt_snapshot_jobs",
    "task:_initial_snapshot",
    "ruf:init_mqtt_gateway_service",
    "ruf:init_connector_mqtt_bridge",
    "task:_initial_prefetch",
    "yield",
    "ruf:inbound.stop",
    "ruf:get_mqtt_gateway_service",
    "ruf:get_connector_mqtt_bridge",
    "ruf:stop_scheduler",
    "print:EEDC Backend wird beendet...",
]
FEHLER_LOG = [
    "DEBUG:PIN-Rücksetzung nicht prüfbar: gestellt:pruefe_ruecksetzung",
    "DEBUG:HA-Verbindung für Statistik nicht ermittelbar: gestellt:aktualisiere_ha_verbindung",
    "DEBUG:Cache-Warmup fehlgeschlagen: gestellt:warmup_l1_from_l2",
    "DEBUG:Sofort-Prefetch fehlgeschlagen: gestellt:prefetch_all_prognosen",
    "DEBUG:Snapshot-Recovery konnte nicht gestartet werden: gestellt:sensor_snapshot_startup_recovery",
    "DEBUG:Community-Nachsendung nicht gestartet: gestellt:_nachsenden",
    "DEBUG:Kraftstoffpreis-Startlauf nicht gestartet: gestellt:kraftstoffpreis_startup_recovery",
    "DEBUG:Kanal-Nachfüllen nicht gestartet: gestellt:nachfuellen_nach_dem_start",
    "DEBUG:MQTT-Snapshot-Jobs konnten nicht aktiviert werden: gestellt:enable_mqtt_snapshot_jobs",
    "WARNING:MQTT-Gateway: Fehler beim Starten: gestellt:init_mqtt_gateway_service",
    "WARNING:Connector-Bridge: Fehler beim Starten: gestellt:init_connector_mqtt_bridge",
]


def _wirft(name, ereignisse):
    def _f(*_a, **_k):
        ereignisse.append(f"ruf:{name}")
        raise RuntimeError(f"gestellt:{name}")
    return _f


def _wirft_async(name, ereignisse):
    async def _f(*_a, **_k):
        ereignisse.append(f"ruf:{name}")
        raise RuntimeError(f"gestellt:{name}")
    return _f


async def test_fehler_je_schritt_halten_den_start_nicht_an(wegwerf_db, umgebung, caplog):
    from backend.core import sperre
    from backend.services import (
        connector_mqtt_bridge, ha_connection, mqtt_gateway_service, mqtt_inbound_service, scheduler,
    )
    from backend.services.wetter import cache

    ereignisse: list[str] = []
    _stelle(umgebung, ereignisse, cache_eintraege=0, scheduler_startet=True, mqtt_cfg=dict(_BROKER))
    mp = umgebung
    mp.setattr(main, "asyncio", _AsyncioAmModul(ereignisse, werfen=frozenset({
        "prefetch_all_prognosen", "sensor_snapshot_startup_recovery", "_nachsenden",
        "kraftstoffpreis_startup_recovery", "nachfuellen_nach_dem_start",
    })))
    mp.setattr(sperre, "pruefe_ruecksetzung", _wirft_async("pruefe_ruecksetzung", ereignisse))
    mp.setattr(ha_connection, "aktualisiere_ha_verbindung", _wirft_async("aktualisiere_ha_verbindung", ereignisse))
    mp.setattr(cache, "warmup_l1_from_l2", _wirft_async("warmup_l1_from_l2", ereignisse))
    mp.setattr(scheduler, "enable_mqtt_snapshot_jobs", _wirft("enable_mqtt_snapshot_jobs", ereignisse))

    def _inbound(*_a, **k):
        ereignisse.append(f"ruf:init_mqtt_inbound_service({k['host']}:{k['port']}, user={k['username']})")
        return _Dienst("inbound", ereignisse)

    mp.setattr(mqtt_inbound_service, "init_mqtt_inbound_service", _inbound)
    mp.setattr(mqtt_gateway_service, "init_mqtt_gateway_service", _wirft("init_mqtt_gateway_service", ereignisse))
    mp.setattr(connector_mqtt_bridge, "init_connector_mqtt_bridge", _wirft("init_connector_mqtt_bridge", ereignisse))
    mp.setattr(mqtt_gateway_service, "get_mqtt_gateway_service", _wirft("get_mqtt_gateway_service", ereignisse))
    mp.setattr(connector_mqtt_bridge, "get_connector_mqtt_bridge", _wirft("get_connector_mqtt_bridge", ereignisse))
    caplog.set_level(logging.DEBUG, logger="backend.main")

    await _laufe(ereignisse)

    assert ereignisse == FEHLER_EREIGNISSE
    assert [f"{r.levelname}:{r.getMessage()}" for r in caplog.records if r.name == "backend.main"] == FEHLER_LOG
