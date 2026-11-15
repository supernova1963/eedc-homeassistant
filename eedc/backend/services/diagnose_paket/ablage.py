"""Ablage des Diagnose-Pakets v4 — temporäre Datei, Marke, Ablauf (Bauplan §3.8, E9, K7; Maßgabe Master aus S0).

* Verzeichnis je Datenbank: ``<tempdir>/eedc-diagnose-<sha256(database_path)[:12]>`` (0700, Dateien 0600) — parallele
  Testprozesse und Server derselben Box stören sich nicht; ``raeume_beim_start`` leert nur das eigene. Nicht unter ``/data``
  (sonst in HA-Sicherungen); im Add-on liegt ``/tmp`` im Container (S0: beschreibbar, ≈ 41 GB frei).
* Ein Eintrag je Anlage; ein neuer ersetzt den alten (die alte Datei wird gelöscht).
* **Die Marke gilt mehrfach bis zum Ablauf** (``GUELTIG_S``) oder bis zum Ersatz; die Datei wird **nie beim Herunterladen**
  gelöscht — die Android-App ruft die Adresse zweimal (WebView bricht ab, der Download-Manager lädt vollständig, S0). Ein
  Abbruch des Clients ist kein Fehler.
* Ablauf: Zeitgeber ``loop.call_later`` + Prüfung bei jedem Abruf (Uhr-Naht ``uhr``) + Aufräumen beim Start.
* Die Marke wird als UTF-8-Bytes verglichen — eine Marke mit Nicht-ASCII-Zeichen ist ungültig (404), kein Fehler (F7).
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import secrets
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

logger = logging.getLogger(__name__)

GUELTIG_S = 900
#: Naht für Tests: ein anderes Verzeichnis (``None`` ⇒ aus ``settings.database_path``).
VERZEICHNIS: Optional[Path] = None
#: Uhr-Naht (monoton; Tests setzen eine eigene).
UHR: Callable[[], float] = time.monotonic


@dataclass
class Eintrag:
    marke: str
    pfad: Path
    dateiname: str
    erstellt: float
    felder: dict = field(default_factory=dict)
    zeitgeber: Optional[asyncio.TimerHandle] = None


_EINTRAEGE: dict[int, Eintrag] = {}
_SPERREN: dict[int, asyncio.Lock] = {}


def verzeichnis(db_pfad: Optional[str] = None) -> Path:
    if VERZEICHNIS is not None:
        return VERZEICHNIS
    if db_pfad is None:
        from backend.core.config import settings

        db_pfad = str(settings.database_path)
    kennung = hashlib.sha256(str(db_pfad).encode("utf-8")).hexdigest()[:12]
    return Path(tempfile.gettempdir()) / f"eedc-diagnose-{kennung}"


def bereit(db_pfad: Optional[str] = None) -> Path:
    v = verzeichnis(db_pfad)
    v.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(v, 0o700)
    return v


def raeume_beim_start(db_pfad: Optional[str] = None) -> None:
    """Leert nur das eigene Verzeichnis (beim Start, ohne Ausgabe); ein Fehler hält den Start nicht an."""
    _EINTRAEGE.clear()
    v = verzeichnis(db_pfad)
    try:
        for p in v.glob("*"):
            if p.is_file():
                p.unlink(missing_ok=True)
    except OSError as e:
        logger.warning("Diagnose-Paket: Ablage %s nicht geleert: %s", v, type(e).__name__)


def sperre(anlage_id: int) -> asyncio.Lock:
    return _SPERREN.setdefault(anlage_id, asyncio.Lock())


def neue_teil_datei(verz: Path, anlage_id: int) -> Path:
    pfad = verz / f"a{anlage_id}-{secrets.token_hex(8)}.zip.teil"
    fd = os.open(pfad, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    os.close(fd)
    return pfad


def _loesche(e: Eintrag) -> None:
    if e.zeitgeber is not None:
        e.zeitgeber.cancel()
    e.pfad.unlink(missing_ok=True)


def _ablaufen(anlage_id: int, marke: str) -> None:
    e = _EINTRAEGE.get(anlage_id)
    if e is not None and e.marke == marke:
        _EINTRAEGE.pop(anlage_id, None)
        _loesche(e)


def ersetze(anlage_id: int, pfad: Path, dateiname: str, felder: dict, *, uhr: Optional[Callable[[], float]] = None) -> Eintrag:
    """Neuer Eintrag der Anlage; der alte und seine Datei gehen."""
    alt = _EINTRAEGE.pop(anlage_id, None)
    if alt is not None:
        _loesche(alt)
    e = Eintrag(marke=secrets.token_urlsafe(24), pfad=pfad, dateiname=dateiname, erstellt=(uhr or UHR)(), felder=felder)
    try:
        e.zeitgeber = asyncio.get_running_loop().call_later(GUELTIG_S, _ablaufen, anlage_id, e.marke)
    except RuntimeError:
        e.zeitgeber = None          # ohne laufende Schleife (Werkzeug) gilt die Prüfung beim Abruf
    _EINTRAEGE[anlage_id] = e
    return e


def gueltig(anlage_id: int, marke: str, *, uhr: Optional[Callable[[], float]] = None) -> Optional[Eintrag]:
    """Der Eintrag, wenn die Marke gilt (gleiche Marke, nicht abgelaufen, Datei da) — sonst ``None``."""
    e = _EINTRAEGE.get(anlage_id)
    # F7: als UTF-8-Bytes vergleichen — ``compare_digest`` wirft bei Nicht-ASCII-Text (sonst 500 statt 404).
    if e is None or not marke or not secrets.compare_digest(e.marke.encode("utf-8"), marke.encode("utf-8", "replace")):
        return None
    if (uhr or UHR)() - e.erstellt > GUELTIG_S or not e.pfad.is_file():
        _ablaufen(anlage_id, e.marke)
        return None
    return e
