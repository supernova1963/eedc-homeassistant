"""Laufzeit des Prozesses — Startzeit und Zeitzone (Diagnose-Paket v4, Testpunkt 3, Bauplan §3.6).

* ``merke_start()`` einmal je Prozess im lifespan (``main.py``, nach ``setup_log_buffer()``), ohne Ausgabe.
* ``gestartet_am()`` — der gemerkte Zeitpunkt mit Offset oder ``None`` (Prozess ohne lifespan, etwa Werkzeug).
* ``zeitzone()`` — zuerst ``TZ`` (lädt ``ZoneInfo``), sonst das Ziel von ``/etc/localtime`` unter ``zoneinfo/``, sonst
  ``None``; immer Kürzel und Offset der Prozessuhr. Gemessen in S0 (Lab, 14.11.2026): das Add-on setzt
  ``TZ=Europe/Berlin``, ``/etc/localtime`` zeigt dort auf ``Etc/UTC`` — deshalb ``TZ`` zuerst.

Nur stdlib; rechnet nichts (die Werte stehen so im Kopf des Pakets).
"""

from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path
from typing import Optional
from zoneinfo import ZoneInfo

_START: Optional[datetime] = None
#: Naht für Tests: Pfad von ``/etc/localtime``.
LOCALTIME = Path("/etc/localtime")


def merke_start(jetzt: Optional[datetime] = None) -> None:
    """Startzeit des Prozesses merken (``datetime.now().astimezone()``); ein zweiter Aufruf ersetzt sie."""
    global _START
    _START = (jetzt or datetime.now()).astimezone()


def gestartet_am() -> Optional[datetime]:
    return _START


def _iana_aus_tz(tz: Optional[str]) -> Optional[str]:
    if not tz:
        return None
    name = tz[1:] if tz.startswith(":") else tz
    try:
        ZoneInfo(name)
    except Exception:  # noqa: BLE001 — ungültiger Name oder POSIX-Form ⇒ kein IANA-Name
        return None
    return name


def _iana_aus_localtime(pfad: Path) -> Optional[str]:
    try:
        ziel = str(pfad.resolve())
    except OSError:
        return None
    marke = "zoneinfo/"
    if marke not in ziel:
        return None
    return ziel.split(marke, 1)[1] or None


def zeitzone(jetzt: Optional[datetime] = None, *, tz: Optional[str] = None, localtime: Optional[Path] = None) -> dict:
    """``{"iana", "quelle", "kuerzel", "utc_offset"}`` — ``quelle`` ist ``"TZ"``, ``"/etc/localtime"`` oder ``None``."""
    tz = os.environ.get("TZ") if tz is None else tz
    iana, quelle = _iana_aus_tz(tz), "TZ"
    if iana is None:
        iana, quelle = _iana_aus_localtime(localtime or LOCALTIME), "/etc/localtime"
    if iana is None:
        quelle = None
    lokal = (jetzt or datetime.now()).astimezone()
    offset = lokal.strftime("%z")
    return {"iana": iana, "quelle": quelle, "kuerzel": lokal.tzname(),
            "utc_offset": f"{offset[:3]}:{offset[3:]}" if offset else None}
