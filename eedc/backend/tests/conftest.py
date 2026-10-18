"""Pytest-Konfiguration und gemeinsame Fixtures für Backend-Akzeptanztests.

Bündelt das pro-Datei duplizierte `_session_ctx`-Boilerplate aus den
Akzeptanztests (Aufräum-Plan E nach v3.31.5). Pytest ist seit v3.27.x
der einzige Test-Runner — der frühere Dual-Mode (Standalone-Script-
Aufruf mit `__main__`-Runner) ist abgelöst.

Auch `sys.path`-Einbindung für `from backend...`-Imports erfolgt hier
einmal zentral statt pro Test-Datei.
"""

from __future__ import annotations

import sys
from pathlib import Path

_BACKEND_ROOT = Path(__file__).resolve().parents[2]  # eedc/
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

import ipaddress
import os
import shutil
import socket
import tempfile

import pytest
import pytest_asyncio
from sqlalchemy import create_engine as _create_sync_engine
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# ── Die Produktiv-Engine zeigt im Testlauf NIE auf `data/eedc.db` (N-414 · N-532) ──
#
# `backend/core/database.py` baut seine Engine beim Import aus `DATABASE_URL`
# (Default: `eedc/data/eedc.db`, die Entwickler-Datenbank). Alles, was nicht über
# die `db`-Fixture läuft — `log_activity` mit eigener Sitzung, die echte Lifespan
# in `test_n237_…` (`init_db` + Datenmigrationen + Scheduler-Start), der
# L2-Cache-Persist des Prognose-Kanons — schrieb bis zum 19.09.2026 in genau
# diese Datei: je Lauf 12–20 echte Aktivitätszeilen („Connector-Tagesabruf",
# „E-Mob-Heimladung konsolidiert" …), und die nie disposte Pool-Verbindung
# meldete am Ende des funktionsweiten Loops „Event loop is closed" (N-414, die
# wandernde Warnung — 0/1/8/12 je Lauf, je nach Worker-Zuteilung). Gemessen mit
# `plans/n414-sonden/sonde_checkout.py`: 69 Pool-Checkouts der Produktiv-Engine
# in 15 Testdateien. Deshalb hier, VOR dem ersten Import von `backend.core.database`,
# eine Wegwerf-Datei je Worker; ihr Schema entsteht einmal synchron, damit ein
# Protokolleintrag dort landen kann statt still zu scheitern.
_TEST_DB_DIR = tempfile.mkdtemp(prefix="eedc-tests-")
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{_TEST_DB_DIR}/eedc.db"
# Die Lifespan (`main.py`) startet ohne dieses Flag Scheduler, Recovery-Task und
# Sofort-Prefetch — Hintergrundarbeit, die den Test-Loop überlebt und nichts prüft.
os.environ.setdefault("EEDC_DISABLE_SCHEDULER", "true")

from backend.core.database import Base  # noqa: E402
import backend.models  # noqa: E402,F401 — registriert alle Tabellen an `Base`

_sync_engine = _create_sync_engine(f"sqlite:///{_TEST_DB_DIR}/eedc.db")
Base.metadata.create_all(_sync_engine)
_sync_engine.dispose()


def pytest_sessionfinish(session, exitstatus):  # noqa: ARG001
    shutil.rmtree(_TEST_DB_DIR, ignore_errors=True)


@pytest.fixture(autouse=True)
def _kanal_merken_leer():
    """HA-Bauform S5 E-S5-1c: der Speicher der Kanal-Tage je Prozess (``services/kanal/merken.py``) überlebt keinen Test —
    ein Worker öffnet viele Datenbanken; die Engine-Marke trennt sie, dies hält zusätzlich jeden Test kalt am Beginn."""
    from backend.services.kanal import merken

    merken.leeren()
    yield
    merken.leeren()


@pytest.fixture(autouse=True)
def _wetter_cache_ohne_l2_persist(monkeypatch):
    """`main.py` setzt beim Lifespan-Start `wetter.cache._loop_running = True`, und
    niemand setzte es zurück — im selben Worker feuerte danach JEDER Prognose-Test
    seine L2-Persistenz per `create_task` gegen die Produktiv-Engine (N-414, Weg B:
    33 Öffnungen in 24 Prognose-Tests, wenn `test_n237_…` zuerst lief; isoliert 0).
    Modulzustand darf einen Test nicht überleben."""
    from backend.services.wetter import cache

    monkeypatch.setattr(cache, "_loop_running", False)

# ── Kein echtes Netz im Testlauf (N-232, Entscheid Gernot 2026-08-11) ────────
#
# **Ein Test, der ans Netz geht, ist kein Test, sondern eine Wette.** Zweimal
# ist genau diese Wette verloren gegangen — beim v4.0.7- und beim
# v4.0.12-Release fiel der CI-Tests-Workflow um, obwohl derselbe Baum lokal
# grün war. Zuletzt hing `test_solcast_tagesprofile_357.py` über den
# Prognose-Kanon (`sfs.get_solar_prognose`) am echten Open-Meteo: lokal
# antwortete die API, im CI kam „Timeout" ⇒ keine Stundenverteilung ⇒ rot.
#
# Vor dem Scharfschalten gemessen (11.08.2026): **2618 Tests laufen vollständig
# ohne Netz grün**. Der Wächter nimmt also nichts weg — er hält den Zustand
# fest und macht die nächste unbeabsichtigte Netzabhängigkeit sofort sichtbar,
# statt sie bis zum Release schlafen zu lassen.
#
# **Was er NICHT tut:** stumm bleiben. Acht Tests riefen zum Zeitpunkt des Baus
# `api.awattar.de` und fingen den Fehler selbst ab (`except Exception → None`)
# — sie fallen nicht um, hängen aber an einer fremden API. Blockieren allein
# hätte sie weiter verborgen; deshalb protokolliert der Wächter jeden Versuch
# und nennt ihn in der Zusammenfassung am Ende des Laufs (N-236).
#
# Escape-Hatch für den bewussten Live-Test gegen eine echte API:
#     EEDC_TESTS_ERLAUBEN_NETZ=1 python -m pytest …

_NETZ_ERLAUBT = os.environ.get("EEDC_TESTS_ERLAUBEN_NETZ") == "1"
_netz_versuche: list[tuple[str, str]] = []
_aktueller_test = {"nodeid": "<Sammel-/Setup-Phase>"}


class NetzZugriffImTest(RuntimeError):
    """Ein Test wollte eine echte Verbindung öffnen — siehe Kommentar oben."""


def _ist_lokal(host: object) -> bool:
    h = host.decode() if isinstance(host, bytes) else str(host)
    return h in ("", "localhost", "::1", "0.0.0.0") or h.startswith("127.")


def _ist_ip_literal(host: object) -> bool:
    """Eine IP-Adresse aufzulösen kostet kein Netz — nur Namen tun das.

    Ohne diese Unterscheidung meldet der Wächter die SSRF-Prüfung der
    HA-Remote-Route (`_validate_connector_host` auf `192.168.1.13`) als
    Netzzugriff und reißt sechs Tests um, die nie eine Verbindung öffnen.
    """
    h = host.decode() if isinstance(host, bytes) else str(host)
    try:
        ipaddress.ip_address(h)
        return True
    except ValueError:
        return False


def _blockiere(ziel: str) -> "NetzZugriffImTest":
    _netz_versuche.append((_aktueller_test["nodeid"], ziel))
    return NetzZugriffImTest(
        f"Netzzugriff im Test blockiert: {ziel}. Die Gegenstelle gehört gemockt "
        "(oder EEDC_TESTS_ERLAUBEN_NETZ=1 für einen bewussten Live-Test)."
    )


if not _NETZ_ERLAUBT:
    _orig_connect = socket.socket.connect
    _orig_connect_ex = socket.socket.connect_ex
    _orig_getaddrinfo = socket.getaddrinfo

    def _connect(self, address, *args, **kwargs):
        host = address[0] if isinstance(address, tuple) else address
        if not _ist_lokal(host):
            raise _blockiere(f"connect {address}")
        return _orig_connect(self, address, *args, **kwargs)

    def _connect_ex(self, address, *args, **kwargs):
        host = address[0] if isinstance(address, tuple) else address
        if not _ist_lokal(host):
            raise _blockiere(f"connect_ex {address}")
        return _orig_connect_ex(self, address, *args, **kwargs)

    def _getaddrinfo(host, port, *args, **kwargs):
        if not _ist_lokal(host) and not _ist_ip_literal(host):
            raise _blockiere(f"DNS {host!r}:{port}")
        return _orig_getaddrinfo(host, port, *args, **kwargs)

    socket.socket.connect = _connect
    socket.socket.connect_ex = _connect_ex
    socket.getaddrinfo = _getaddrinfo


def pytest_runtest_logstart(nodeid, location):  # noqa: ARG001
    """Ordnet einen blockierten Zugriff dem Test zu, der ihn ausgelöst hat."""
    _aktueller_test["nodeid"] = nodeid


def pytest_terminal_summary(terminalreporter, exitstatus, config):  # noqa: ARG001
    """Nennt die stillen Netz-Esser beim Namen — auch wenn der Lauf grün ist."""
    if not _netz_versuche:
        return
    je_test: dict[str, set[str]] = {}
    for nodeid, ziel in _netz_versuche:
        je_test.setdefault(nodeid, set()).add(ziel)
    terminalreporter.write_sep("-", f"blockierte Netzzugriffe ({len(je_test)} Tests)")
    for nodeid, ziele in sorted(je_test.items()):
        terminalreporter.write_line(f"  {nodeid} → {', '.join(sorted(ziele))}")


@pytest_asyncio.fixture
async def db() -> AsyncSession:
    """Frisches In-Memory-SQLite + Schema pro Test, sauberes Teardown.

    Fixture-Name `db` matcht die FastAPI-Konvention (`db: AsyncSession =
    Depends(get_db)`) und die in den Tests übliche Variable.
    """
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    Session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    session = Session()
    try:
        yield session
    finally:
        await session.close()
        await engine.dispose()
