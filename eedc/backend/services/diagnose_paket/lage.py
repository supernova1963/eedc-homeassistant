"""Lage zur Laufzeit des Diagnose-Pakets v4 — ``lage.json`` (Bauplan §3.3, §3.7; Testpunkte 1 und 3, K4, K9).

Teile: ``kopf`` · ``daten_checker`` (dieselbe Serialisierung wie die Route, ``checker_antwort``) · ``zuordnungen``
(``zuordnungen_lesen`` ohne Festschreiben) · ``zeitplaene`` · ``log`` (Puffer, **nur Logger der Positivliste**
``LOG_POSITIVLISTE`` — bei Log-Stufe ``debug`` tragen Fremd-Logger wie ``aiosqlite`` und ``sqlalchemy.*`` die Parameter jeder
Anweisung, also Zellwerte jeder Tabelle; jede andere Zeile zählt in ``inhalt.json.log_ausgelassen``, Korrektur F1) ·
``einstellungen`` (Allowlist ``register.EINSTELLUNGEN``, Präfixe ``register.EINSTELLUNGEN_PRAEFIX``) · ``ha_abgleich``.
``schema`` setzt ``paket.py`` aus dem Auszug.

Jeder Teil mit Datenbank liest in **eigener** Sitzung (nie in der Routen-Sitzung) und rollt sie am Ende zurück — das Paket
schreibt nichts. Eine Zeitgrenze (``asyncio.wait_for``) gibt es nur um einen solchen Teil; ein Abbruch lässt die übrigen
unberührt. Ein gescheiterter Teil steht als ``{"fehler": "<Typ>: <bereinigt>"}`` bzw. ``{"fehler": "zeitgrenze"}``; das
Paket kommt trotzdem.
"""

from __future__ import annotations

import asyncio
import logging
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Awaitable, Callable, Optional

from sqlalchemy import select

from backend.services.diagnose_paket.bereinigung import bereinige_log
from backend.services.diagnose_paket.register import EINSTELLUNGEN, EINSTELLUNGEN_PRAEFIX, PROFIL_DIAGNOSE

CHECKER_ZEITGRENZE_S = 120
#: Logger, deren Zeilen ins Paket gehen (je Name selbst und seine Kinder): eedc-eigene Module (``logging.getLogger(__name__)``
#: unter ``backend``), der Server (``uvicorn``, ``uvicorn.error``, ``uvicorn.access``) und der Zeitplaner, den eedc nutzt
#: (``services/scheduler.py`` startet APScheduler; Job-Fehler meldet die Bibliothek unter ``apscheduler.*``). Alles andere —
#: ``aiosqlite`` und ``sqlalchemy.*`` (SQL samt Parametern bei Log-Stufe ``debug``), ``httpx``, unbekannte Fremd-Logger —
#: bleibt draußen (Korrektur F1; vorher nur ``sqlalchemy.*`` ausgeschlossen).
LOG_POSITIVLISTE = ("backend", "uvicorn", "apscheduler")


def logger_im_paket(name: str) -> bool:
    """Gehört die Zeile des Loggers ``name`` ins Paket (Positivliste, je Name und Kinder)?"""
    return any(name == p or name.startswith(p + ".") for p in LOG_POSITIVLISTE)


@dataclass
class LageErgebnis:
    teile: dict = field(default_factory=dict)
    status: dict = field(default_factory=dict)
    log_ausgelassen: int = 0
    befunde: int = 0
    zuordnungen_mit_quelle: int = 0
    einstellungen_unbekannt: list = field(default_factory=list)


@asynccontextmanager
async def _lesend(sitzungen):
    """Eine eigene Sitzung, am Ende zurückgerollt (das Paket schreibt nichts)."""
    async with sitzungen() as db:
        try:
            yield db
        finally:
            await db.rollback()


async def _teil(erg: LageErgebnis, name: str, fn: Callable[[], Awaitable[Any]], zeitgrenze: Optional[float] = None) -> None:
    try:
        wert = await (asyncio.wait_for(fn(), timeout=zeitgrenze) if zeitgrenze else fn())
        erg.teile[name], erg.status[name] = wert, "ok"
    except asyncio.TimeoutError:
        erg.teile[name], erg.status[name] = {"fehler": "zeitgrenze"}, "zeitgrenze"
    except Exception as e:  # noqa: BLE001 — Teilfehler-Fang (G5)
        erg.teile[name], erg.status[name] = {"fehler": f"{type(e).__name__}: {bereinige_log(str(e))}"}, "fehler"


# ─── Teile ───────────────────────────────────────────────────────────────────────────────────────────────────────

def _betriebsart(info: dict) -> str:
    if info.get("addon"):
        return "addon"
    return "standalone_ha" if info.get("kind") == "ha_connector" else "standalone"


async def kopf(sitzungen, anlage_id: int, jetzt: datetime) -> dict:
    from backend.core.config import APP_VERSION
    from backend.core.laufzeit import gestartet_am, zeitzone
    from backend.services.diagnose_paket import paket

    async with _lesend(sitzungen) as db:
        info = await paket.ha_info(db)
    start = gestartet_am()
    return {
        "eedc_version": APP_VERSION, "profil": PROFIL_DIAGNOSE, "anlage_id": anlage_id, "betriebsart": _betriebsart(info),
        "ha": {"verbunden": bool(info.get("kind")), "erreichbar": bool(info.get("erreichbar")),
               "version": info.get("version"), "zeitzone": info.get("zeitzone")},
        "zeitzone": zeitzone(jetzt),
        "erzeugt_am": jetzt.astimezone().isoformat(timespec="seconds"),
        "gestartet_am": start.isoformat(timespec="seconds") if start else None,
        "log_stufe": logging.getLevelName(logging.getLogger().getEffectiveLevel()),
    }


async def daten_checker(sitzungen, anlage_id: int, erg: LageErgebnis) -> dict:
    from backend.services.daten_checker import DatenChecker
    from backend.services.daten_checker.antwort import checker_antwort

    async with _lesend(sitzungen) as db:
        result = await DatenChecker(db).check_anlage(anlage_id)
    erg.befunde = len(result.ergebnisse)
    return checker_antwort(result).model_dump(mode="json")


def _mit_quelle(gruppen: list[dict]) -> int:
    from backend.services.datenquellen_felder import QUELLE_KEINE

    n = 0
    for g in gruppen:
        n += sum(1 for f in g.get("felder") or [] if f.get("quelle") not in (None, QUELLE_KEINE))
        n += sum(1 for th in g.get("themen") or [] for e in th.get("eintraege") or []
                 if e.get("quelle") not in (None, QUELLE_KEINE))
    return n


async def zuordnungen(sitzungen, anlage_id: int, erg: LageErgebnis) -> dict:
    from backend.services.datenquellen_felder import zuordnungen_lesen

    async with _lesend(sitzungen) as db:
        ctx, gruppen = await zuordnungen_lesen(db, anlage_id)
    erg.zuordnungen_mit_quelle = _mit_quelle(gruppen)
    return {"gruppen": gruppen, "neu_aufgeloest": sorted(ctx.neu_persistieren)}


async def zeitplaene() -> dict:
    from backend.services.scheduler import get_scheduler

    return get_scheduler().get_status()


def log_zeilen(erg: LageErgebnis) -> list[dict]:
    """Der Puffer (neueste zuerst), nur Logger der Positivliste (``logger_im_paket``); jede Meldung bereinigt."""
    from backend.core.log_buffer import get_log_buffer

    puffer = get_log_buffer()
    out = []
    for e in puffer.get_entries(limit=puffer.capacity):
        name = e.get("logger_name") or ""
        if not logger_im_paket(name):
            erg.log_ausgelassen += 1
            continue
        out.append({"timestamp": e.get("timestamp"), "level": e.get("level"), "logger_name": name,
                    "module": e.get("module"), "message": bereinige_log(str(e.get("message") or ""))})
    return out


def _einstellung(key: str, v: Any, anlage_id: int) -> dict:
    d = v if isinstance(v, dict) else {}
    if key == "ha_remote":
        return {"eingerichtet": bool(d.get("base_url")), "enabled": d.get("enabled")}
    if key == "einstellungen_pin":
        return {"gesetzt": bool(d.get("hash"))}
    if key == "sperre_secret":
        return {"vorhanden": bool(d.get("wert"))}
    if key == "custom_import_templates":
        return {"anzahl": len(d)}
    if key == "wetter_altbestand_nachzug":
        return {str(anlage_id): d.get(str(anlage_id))}
    return {f: d.get(f) for f in EINSTELLUNGEN[key]}


async def einstellungen(sitzungen, anlage_id: int, erg: LageErgebnis) -> dict:
    from backend.models.settings import Settings

    async with _lesend(sitzungen) as db:
        zeilen = (await db.execute(select(Settings.key, Settings.value))).all()
    out = {}
    for key, wert in sorted(zeilen):
        praefix = next((p for p in EINSTELLUNGEN_PRAEFIX if key.startswith(p)), None)
        if key in EINSTELLUNGEN:
            out[key] = _einstellung(key, wert, anlage_id)
        elif praefix is not None:
            zeile = _einstellung_praefix(praefix, wert, anlage_id)
            if zeile is not None:
                out[key] = zeile
        else:
            erg.einstellungen_unbekannt.append(key)
    return out


def _einstellung_praefix(praefix: str, v: Any, anlage_id: int) -> Optional[dict]:
    """Ein Zustand mit Präfix (``EINSTELLUNGEN_PRAEFIX``): nur der Anlage des Pakets; Listen als Anzahl, ein Auftrag als
    «erledigt?» (keine Kennungen, keine Fehlertexte)."""
    d = v if isinstance(v, dict) else {}
    if d.get("anlage_id") != anlage_id:
        return None
    out: dict[str, Any] = {}
    for f in EINSTELLUNGEN_PRAEFIX[praefix]:
        w = d.get(f)
        out[f] = len(w) if isinstance(w, list) else ({"erledigt": bool(w.get("erledigt"))} if isinstance(w, dict) else w)
    return out


async def baue_lage(anlage_id: int, *, sitzungen, jetzt: datetime, ha_svc=None,
                    uhr: Callable[[], float] = time.monotonic, messung: Optional[dict] = None) -> LageErgebnis:
    """Alle Teile der Lage ohne ``schema``; ``messung`` bekommt die Dauer je Teil in ms (S1-Gate)."""
    from backend.services.diagnose_paket.ha_abgleich import ha_abgleich

    erg = LageErgebnis()
    schritte: list[tuple[str, Callable[[], Awaitable[Any]], Optional[float]]] = [
        ("kopf", lambda: kopf(sitzungen, anlage_id, jetzt), None),
        ("daten_checker", lambda: daten_checker(sitzungen, anlage_id, erg), CHECKER_ZEITGRENZE_S),
        ("zuordnungen", lambda: zuordnungen(sitzungen, anlage_id, erg), None),
        ("zeitplaene", zeitplaene, None),
        ("einstellungen", lambda: einstellungen(sitzungen, anlage_id, erg), None),
        ("ha_abgleich", lambda: ha_abgleich(sitzungen, anlage_id, ha_svc=ha_svc, uhr=uhr), None),
    ]
    for name, fn, grenze in schritte:
        t0 = uhr()
        await _teil(erg, name, fn, grenze)
        if messung is not None:
            messung[name] = int(round((uhr() - t0) * 1000))
    if isinstance(erg.teile.get("ha_abgleich"), dict) and erg.teile["ha_abgleich"].get("status") == "zeitgrenze":
        erg.status["ha_abgleich"] = "zeitgrenze"
    erg.teile["log"] = log_zeilen(erg)
    erg.status["log"] = "ok"
    return erg
