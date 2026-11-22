"""Bausteine des Nachlaufs eines Sensorwechsels (Sensorwechsel mit Grund, Bauplan B-6; seit Weg B nur noch für das Ansetzen
eines Wechsels «bleiben», ``ansatz.py``, und den Lauf ``korrektur_lauf.py``).

Die frühere **Korrektur** («verwerfen» mit «Falsch seit», Lücken-Zeilen, Korrektur am versetzten Abschnitt) ist seit Weg B
entfernt (Entscheid Gernot 21.11.2026, Bauplan Nr. 174–183; Sitzung B3a). Was hier bleibt, nutzen «bleiben» und der Lauf:

* **Home Assistant** (``ha_eingerichtet``, ``ha_dienst``, ``ha_abruf``): eingerichtet, aber nicht erreichbar ⇒
  ``KorrekturNichtStartbar`` mit ``SATZ_NICHT_ERREICHBAR`` — das Ansetzen wartet, der Lauf bleibt offen.
* **Tage neu bilden** (``tage_neu_bilden_liste``): die Tage ab dem Tag von G, deren Tageszeile einen Schlüssel des Felds trägt.
* **Nachlauf** (``nachlauf_auftrag``, ``nachlauf_aus_auftrag``, ``fuelle_staende``): Kanal aus Home Assistant füllen, die
  abhängigen abgeleiteten Kanäle neu schreiben, die Zählerstände der gefüllten Zeit neu lesen und speichern — als Auftrag im
  Zustand des Laufs, wiederholbar, bis er gelingt.
* ``sitzungen_wie``: Sitzungen an derselben Datenbank für Füllen und Hintergrund-Lauf.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

_STUNDE = 3600


class KorrekturNichtStartbar(ValueError):
    """Home Assistant ist eingerichtet, aber nicht erreichbar — der Lauf startet nicht."""


SATZ_NICHT_ERREICHBAR = ("Home Assistant ist nicht erreichbar — die Korrektur startet erst, wenn eedc die Langzeitstatistik "
                         "lesen kann.")


@dataclass(frozen=True)
class Auftrag:
    """Ein Zeitraum eines Schlüssels: ``falsch_seit`` (erste Stunde, örtlich ohne Zone; ``None`` = von Beginn an) bis ``ab``
    (erste Stunde danach) — für ``tage_neu_bilden_liste`` (Ansetzen eines Wechsels «bleiben»: ab G bis jetzt)."""
    anlage_id: int
    sensor_key: str
    falsch_seit: Optional[datetime]
    ab: datetime
    vorher: Optional[dict]
    nachher: Optional[dict]


# ── Home Assistant ──────────────────────────────────────────────────────────


def ha_eingerichtet() -> bool:
    """Ist Home Assistant für eedc eingerichtet (Add-on, Recorder-Adresse oder API-Verbindung)? Ohne: Standalone."""
    from backend.core.config import HA_INTEGRATION_AVAILABLE, settings
    from backend.services.ha_statistics_service import get_ha_statistics_service

    return bool(HA_INTEGRATION_AVAILABLE or settings.ha_recorder_db_url
                or getattr(get_ha_statistics_service(), "_ws_client", None) is not None)


def ha_dienst(ha_svc=None):
    """Der HA-Dienst des Laufs: ``ha_svc`` (Proben) oder — wenn eingerichtet — der Dienst des Prozesses; ``None`` = ohne HA.
    Eingerichtet, aber nicht erreichbar ⇒ ``KorrekturNichtStartbar``."""
    if ha_svc is None:
        if not ha_eingerichtet():
            return None
        from backend.services.ha_statistics_service import get_ha_statistics_service

        ha_svc = get_ha_statistics_service()
    if not ha_svc.is_available:
        raise KorrekturNichtStartbar(SATZ_NICHT_ERREICHBAR)
    return ha_svc


async def ha_abruf(abruf):
    """Ein Abruf aus Home Assistant (Bauplan «Zu §14» Nr. 116 E-K6): scheitert er, ist der Lauf in diesem Augenblick nicht
    startbar (``KorrekturNichtStartbar`` mit dem Satz «nicht erreichbar»), nichts wird geschrieben."""
    try:
        return await abruf
    except KorrekturNichtStartbar:
        raise
    except Exception as e:  # noqa: BLE001 — jeder Abruf-Fehler von Home Assistant
        logger.warning("Korrektur: Abruf aus Home Assistant gescheitert: %s: %s", type(e).__name__, e)
        raise KorrekturNichtStartbar(SATZ_NICHT_ERREICHBAR) from e


# ── Tage neu bilden ─────────────────────────────────────────────────────────


async def tage_neu_bilden_liste(db: AsyncSession, a: Auftrag, ziele) -> list[date]:
    """§7 Nr. 10, §10 Nr. 35: Tage, deren Fenster ``[f, ab)`` schneidet und deren Tageszeile einen Schlüssel des Felds trägt
    — **ohne Blick auf seine Herkunft**: die Marke ``auto:kanal_tag`` gilt je Zeile, nicht je Schlüssel
    (``energie_profil/mengen_weiche``), und der gespeicherte Wert wird gelesen; auch ein schon einmal neu gebildeter Tag
    gehört dazu. Auch in Monaten mit Abschluss (ihre gespeicherten Monatswerte bleiben)."""
    from backend.services.kanal.abgeleitet import tag_der_stunde
    from backend.services.verwerfen_vor_quellbeginn import _tz_zeilen, tz_keys_der_zeile

    bis = tag_der_stunde(int(a.ab.timestamp()) - _STUNDE)
    von = tag_der_stunde(int(a.falsch_seit.timestamp())) if a.falsch_seit is not None else None
    return sorted({row.datum for row in await _tz_zeilen(db, a.anlage_id, bis, ziele, von) if tz_keys_der_zeile(row, ziele)})


# ── Nachlauf ────────────────────────────────────────────────────────────────


def sitzungen_wie(db: AsyncSession, rueckfall):
    """Sitzungen an derselben Datenbank wie ``db`` (Füllen und Hintergrund-Lauf brauchen eigene, kurze Transaktionen)."""
    from contextlib import asynccontextmanager

    from sqlalchemy.ext.asyncio import async_sessionmaker

    bind = getattr(db, "bind", None)
    if bind is None:
        return rueckfall
    macher = async_sessionmaker(bind, class_=AsyncSession, expire_on_commit=False)

    @asynccontextmanager
    async def sitzungen():
        async with macher() as s:
            yield s
            await s.commit()

    return sitzungen


def nachlauf_auftrag(kk, ha_svc, bis_ts: int, jetzt: datetime, *, staende: Optional[dict] = None) -> Optional[dict]:
    """Der Nachlauf nach dem Commit als Auftrag im Zustand des Laufs (``None`` = nichts zu tun): Kanal füllen (mit Home
    Assistant und einem Beginn der neuen Quelle), die verworfenen abhängigen abgeleiteten Kanäle neu schreiben und —
    Bauplan «Zu §14» Nr. 111 — die Zählerstände der gefüllten Zeit aus Home Assistant neu lesen und speichern (``staende``)."""
    fuellen = ha_svc is not None and kk.h0 is not None and kk.kanal_id is not None
    if not fuellen and not kk.abgeleitet_verworfen and staende is None:
        return None
    return {"kanal_id": kk.kanal_id, "key": kk.key, "w0": kk.w0, "h0": kk.h0 if fuellen else None, "bis_ts": bis_ts,
            "familien": None if kk.abgeleitet_familien is None else sorted(kk.abgeleitet_familien),
            "abgeleitet_verworfen": kk.abgeleitet_verworfen, "jetzt": jetzt.isoformat(), "staende": staende,
            "erledigt": False}


async def nachlauf_aus_auftrag(sitzungen, anlage_id: int, f: dict, *, ha_svc=None) -> dict[str, int]:
    """Den Nachlauf aus dem Auftrag ausführen (nach dem Commit oder nachgeholt vom Lauf; ``ha_svc`` = der Dienst des
    Aufrufers, sonst der des Prozesses). Wiederholbar: das Füllen des Kanals spiegelt neu, das Speichern der Stände füllt nur
    fehlende Zeilen. Returns: die Mengen."""
    from backend.services.kanal.korrektur import KanalKorrektur, fuelle_kanal, schreibe_abgeleitete_nach

    kk = KanalKorrektur(f["key"], kanal_id=f.get("kanal_id"), w0=f.get("w0"), h0=f.get("h0"),
                        abgeleitet_familien=None if f.get("familien") is None else frozenset(f["familien"]),
                        abgeleitet_verworfen=int(f.get("abgeleitet_verworfen") or 0))
    n: dict[str, int] = {}
    if not f.get("kanal_erledigt"):            # nach dem Commit schon gelaufen, nur die Stände stehen aus (Nr. 111)
        n = {"kanal_neu_gespiegelt": 0, "abgeleitet_neu": 0}
        svc = (ha_svc or ha_dienst(None)) if kk.h0 is not None else None
        if svc is not None:
            n["kanal_neu_gespiegelt"] = await fuelle_kanal(sitzungen, anlage_id, kk, ha_svc=svc, bis_ts=int(f["bis_ts"]))
            if isinstance(f.get("mitruecken"), dict):       # Ansetzen eines Wechsels «bleiben» (a-K N3): F4 nachholen
                from backend.services.zuordnung_wechsel.ansatz import mitruecken

                n["verschiebung"] = await mitruecken(sitzungen, kk.kanal_id, f["mitruecken"])
        n["abgeleitet_neu"] = await schreibe_abgeleitete_nach(sitzungen, anlage_id, kk, datetime.fromisoformat(f["jetzt"]),
                                                              immer=bool(f.get("abgeleitet_immer"))) or 0
    if isinstance(f.get("staende"), dict):
        n["staende_neu"] = await fuelle_staende(sitzungen, anlage_id, f["staende"], ha_svc=ha_svc)
    return n


async def fuelle_staende(sitzungen, anlage_id: int, auftrag: dict, *, ha_svc=None) -> int:
    """Bauplan «Zu §14» Nr. 111: die Zählerstände der gefüllten Zeit ``[von, bis)`` aus Home Assistant neu lesen und
    **speichern** — der bestehende Schreiber der Stunde (``snapshot/writer.snapshot_anlage``, nur dieser Schlüssel) mit der
    Zuordnung zum Zeitpunkt; gefüllt werden nur fehlende Zeilen, ein Tag je Transaktion. Home Assistant **nicht erreichbar**
    (vorher, mittendrin oder danach) ⇒ die Funktion wirft — der Auftrag bleibt offen, der Lauf holt es stündlich und nach dem
    Start nach (``korrektur_lauf``); **nicht (mehr) eingerichtet** ⇒ nichts zu lesen, der Auftrag endet. Returns: Zahl der
    geschriebenen Stände."""
    from backend.models.anlage import Anlage
    from backend.services.kanal import merken
    from backend.services.snapshot.writer import snapshot_anlage

    svc = ha_svc or ha_dienst(None)
    von, bis = datetime.fromisoformat(auftrag["von"]), datetime.fromisoformat(auftrag["bis"])
    if svc is None:
        merken.invalidiere(anlage_id)
        return 0
    zp = ab_ts_volle_stunde(von)
    nur = frozenset({auftrag["key"]})
    n = 0
    while zp < bis:
        _erreichbar(svc)
        async with sitzungen() as db:
            anlage = (await db.execute(select(Anlage).where(Anlage.id == anlage_id))).scalar_one()
            ende = min(bis, zp + timedelta(days=1))
            while zp < ende:
                n += await snapshot_anlage(db, anlage, zeitpunkt=zp, nur_schluessel=nur, ha_svc=svc)
                zp += timedelta(hours=1)
    _erreichbar(svc)
    merken.invalidiere(anlage_id)
    return n


def ab_ts_volle_stunde(t: datetime) -> datetime:
    from backend.services.zuordnung_wechsel.zeitpunkt import ab_ts_aus

    return ab_ts_aus(t.replace(microsecond=0))


def _erreichbar(svc) -> None:
    if not svc.is_available:
        raise KorrekturNichtStartbar(SATZ_NICHT_ERREICHBAR)
