"""Schritt 4 der Korrektur: die betroffenen Tage im Hintergrund neu bilden (Sensorwechsel mit Grund, Bauplan B-6 (4), §7 Nr. 10).

**Zustand** je Lauf in ``settings`` unter ``korrektur_lauf:<lauf>`` (kein neues Schema): ``{anlage_id, sensor_key, tage,
erledigt, status, fehler, behalten, beginn, ende}`` — angelegt in derselben Transaktion wie die Wechsel-Zeile, fortgeschrieben
nach jedem Tag. Ein Neustart setzt einen Lauf mit ``status = laeuft`` beim nächsten Tag fort (``fortsetzen_nach_dem_start``,
``main.py``). Je Tag: ``repair_orchestrator._reparatur_aggregat`` (derselbe Weg wie «Tag neu aggregieren», ohne Neu-Einlesen
der Zählerstände — die Reihe füllt B-0 beim Lesen aus der richtigen Quelle), mit der Zuordnung zum Zeitpunkt (B-0).

**Wetter und Börsenpreis bleiben** (Bauplan §10 Nr. 32, Entscheid Gernot 17.11.2026): der Tag wird **ohne externen Abruf**
gebildet (``energie_profil._helpers.ohne_abruf`` — kein Open-Meteo, kein aWATTar; der Aggregator bleibt unverändert) und
danach tragen Tages- und Stundenzeilen in den Abruf-Spalten (``TAG_ABRUF``, ``STUNDE_ABRUF``) **genau** den Stand vorher —
der gespeicherte Wert gewinnt immer, auch ein leerer bleibt leer. **Die zwei daraus abgeleiteten Spalten folgen den neu
gebildeten Mengen:** die Einspeisung bei negativem Börsenpreis rechnet der Aggregator selbst aus den gespeicherten
Börsenpreisen der Stunden (sie gehen ihm statt des Abrufs zu) und den neuen Einspeise-Mengen; die Performance Ratio aus
der gespeicherten GTI-Summe und dem neuen PV-Ertrag über die eine Stelle für jeden Tag
(``kanal_stunden.performance_ratio_des_tages``, wie der Archiv-Nachzug) — nach einer Korrektur bleibt nichts aus dem
falschen Sensor Gerechnetes stehen (§10 Nr. 31).

**Robustheit (Sitzung 3b, Bauplan §10 Nr. 40):** höchstens **eine** Aufgabe je Lauf — auch das Fortsetzen nach dem Start geht
über ``starten`` (``_AUFGABEN``). Der **Nachlauf** der Korrektur (Kanal aus Home Assistant füllen, abhängige abgeleitete Kanäle
neu schreiben, seit 4b-1-K2 die Zählerstände der gefüllten Zeit neu lesen und speichern — Bauplan «Zu §14» Nr. 111) steht als
``fuellen`` im Zustand; solange er offen ist, gilt das Intervall der Korrektur für die Leser als Lücke (Nr. 106); scheitert er nach dem Commit, holt ihn der Lauf vor den Tagen nach — bis
dahin bleibt der Lauf ``laeuft``. Angestoßen wird ein offener Lauf **stündlich** (``offene_anstossen`` aus dem Stundenlauf,
Bauplan §11 Nr. 46), nach dem Start und wenn die Werkbank denselben Schlüssel noch einmal ausführt; der Fehler «Füllen: …»
steht je Lauf einmal (der letzte Versuch).
Fertige Läufe räumt ``aufraeumen`` nach ``AUFBEWAHREN`` weg (beim nächsten Lauf und nach dem Start). Das Diagnose-Paket führt
die Zustände unter ``EINSTELLUNGEN_PRAEFIX`` (``diagnose_paket/register.py``).
"""

from __future__ import annotations

import asyncio
import logging
from datetime import date, datetime, timedelta
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

logger = logging.getLogger(__name__)

PRAEFIX = "korrektur_lauf:"
LAEUFT, FERTIG = "laeuft", "fertig"
#: Wie lange ein fertiger Lauf im Zustand bleibt (die Fortschritts-Route und das Diagnose-Paket lesen ihn).
AUFBEWAHREN = timedelta(days=30)

#: Tageszeile und Stundenzeilen: die Spalten aus Abrufen (Wetter, Börsenpreis) — nach dem Neubilden wie vorher.
TAG_ABRUF = ("temperatur_min_c", "temperatur_max_c", "strahlung_summe_wh_m2", "gti_summe_wh_m2",
             "boersenpreis_avg_cent", "boersenpreis_min_cent", "negative_preis_stunden")
STUNDE_ABRUF = ("temperatur_c", "globalstrahlung_wm2", "bewoelkung_prozent", "niederschlag_mm", "wetter_code",
                "boersenpreis_cent")

#: Laufende Aufgaben je Lauf (Proben warten darauf).
_AUFGABEN: dict[str, asyncio.Task] = {}
#: Kopf des einen Fehler-Eintrags je Lauf, wenn der Nachlauf (Füllen) scheitert.
FUELLEN_PRAEFIX = "Füllen: "


async def anlegen(db: AsyncSession, lauf: str, anlage_id: int, sensor_key: str, tage: list[date],
                  fuellen: Optional[dict] = None) -> None:
    """Den Zustand anlegen (in der Transaktion der Wechsel-Zeile); ``fuellen`` = der Nachlauf (``korrektur.nachlauf_auftrag``)."""
    from backend.models.settings import Settings

    await aufraeumen(db)
    db.add(Settings(key=PRAEFIX + lauf, value={
        "anlage_id": anlage_id, "sensor_key": sensor_key, "tage": [d.isoformat() for d in tage], "erledigt": 0,
        "status": LAEUFT, "fehler": [], "behalten": 0, "beginn": datetime.now().replace(microsecond=0).isoformat(),
        "ende": None, "fuellen": fuellen}))
    await db.flush()


async def aufraeumen(db: AsyncSession, jetzt: Optional[datetime] = None) -> int:
    """Fertige Läufe, deren Ende länger als ``AUFBEWAHREN`` zurückliegt, entfernen. Returns: Zahl der entfernten Zustände."""
    from backend.models.settings import Settings

    grenze = (jetzt or datetime.now()) - AUFBEWAHREN
    n = 0
    for row in (await db.execute(select(Settings).where(Settings.key.like(PRAEFIX + "%")))).scalars().all():
        z = row.value if isinstance(row.value, dict) else {}
        ende = z.get("ende")
        if z.get("status") == FERTIG and ende and datetime.fromisoformat(ende) < grenze:
            await db.delete(row)
            n += 1
    if n:
        await db.flush()
    return n


async def offener_lauf(db: AsyncSession, anlage_id: int, sensor_key: str) -> Optional[str]:
    """Ein Lauf dieses Schlüssels, dessen Nachlauf (Füllen) noch aussteht — die Werkbank holt ihn beim nächsten Ausführen nach."""
    from backend.models.settings import Settings

    for row in (await db.execute(select(Settings).where(Settings.key.like(PRAEFIX + "%")))).scalars().all():
        z = row.value if isinstance(row.value, dict) else {}
        if (z.get("status") == LAEUFT and z.get("anlage_id") == anlage_id and z.get("sensor_key") == sensor_key
                and isinstance(z.get("fuellen"), dict) and not z["fuellen"].get("erledigt")):
            return row.key[len(PRAEFIX):]
    return None


async def offene_fuell_laeufe(db: AsyncSession, anlage_id: int) -> frozenset[str]:
    """Die Läufe der Anlage, deren Nachlauf (Füllen) noch aussteht — dieselbe Bedingung wie ``offener_lauf``. Solange gilt das
    Intervall ihrer Korrektur-Zeile für die Leser als Lücke (Bauplan «Zu §14» Nr. 106, ``zeitpunkt.gesperrte_stuecke``)."""
    from backend.models.settings import Settings

    aus = set()
    for row in (await db.execute(select(Settings).where(Settings.key.like(PRAEFIX + "%")))).scalars().all():
        z = row.value if isinstance(row.value, dict) else {}
        if (z.get("status") == LAEUFT and z.get("anlage_id") == anlage_id and isinstance(z.get("fuellen"), dict)
                and not z["fuellen"].get("erledigt")):
            aus.add(row.key[len(PRAEFIX):])
    return frozenset(aus)


def fuellen_offen(z: dict) -> bool:
    """Steht das Füllen aus, weil es **gescheitert** ist (die Fläche sagt «eedc versucht es jede Stunde …»)? Ein Nachlauf, dessen
    Kanal-Teil nach dem Commit gelaufen ist und der nur noch die Stände speichert (Bauplan «Zu §14» Nr. 111), ist ohne
    Fehler-Eintrag kein ausstehendes Füllen — er läuft («Korrektur läuft …»)."""
    f = z.get("fuellen") if isinstance(z.get("fuellen"), dict) else None
    if f is None or f.get("erledigt"):
        return False
    return not f.get("kanal_erledigt") or any(_ist_fuellen_fehler(x) for x in z.get("fehler") or [])


async def stand(db: AsyncSession, lauf: str) -> Optional[dict[str, Any]]:
    """Fortschritt eines Laufs (``None`` = unbekannt)."""
    from backend.models.settings import Settings

    row = (await db.execute(select(Settings).where(Settings.key == PRAEFIX + lauf))).scalar_one_or_none()
    return dict(row.value) if row is not None and isinstance(row.value, dict) else None


async def _tag_vorher(db: AsyncSession, anlage_id: int, tag: date) -> tuple[Optional[dict], dict[int, dict]]:
    from backend.models.tages_energie_profil import TagesEnergieProfil, TagesZusammenfassung

    tz = (await db.execute(select(TagesZusammenfassung).where(
        TagesZusammenfassung.anlage_id == anlage_id, TagesZusammenfassung.datum == tag))).scalar_one_or_none()
    zeilen = (await db.execute(select(TagesEnergieProfil).where(
        TagesEnergieProfil.anlage_id == anlage_id, TagesEnergieProfil.datum == tag))).scalars().all()
    stunden = {r.stunde: {k: getattr(r, k) for k in STUNDE_ABRUF} for r in zeilen}
    alt = {k: getattr(tz, k) for k in TAG_ABRUF} if tz is not None else None
    # Die Werte sind kopiert: die geladenen Zeilen verlassen die Sitzung, bevor der Neubau sie löscht und neu schreibt (sonst
    # trüge die Sitzung ein altes Objekt unter der Nummer einer neuen Zeile — SQLAlchemy warnt «Identity map already had …»).
    for r in (*zeilen, *((tz,) if tz is not None else ())):
        db.expunge(r)
    return alt, stunden


def _wie_vorher(row, alt: dict, spalten) -> int:
    """Die Spalten auf den Stand vorher setzen (auch leer). Returns: Zahl der Werte, die der Neubau anders hatte."""
    n = 0
    for k in spalten:
        if getattr(row, k) != alt.get(k):
            setattr(row, k, alt.get(k))
            n += 1
    return n


async def _performance_ratio(db: AsyncSession, anlage, tag: date, tz, zeilen: list) -> Optional[float]:
    """Gespeicherte GTI-Summe, neuer PV-Ertrag — dieselbe Stelle wie der Archiv-Nachzug (Kanal-Tag und Bestandstag)."""
    from backend.core.berechnungen.anlagen_kwp import anlagen_kwp
    from backend.models.investition import Investition
    from backend.services.energie_profil.archiv_nachzug import sonstige_erzeuger_ids_von
    from backend.services.energie_profil.kanal_stunden import performance_ratio_des_tages

    invs = list((await db.execute(select(Investition).where(Investition.anlage_id == anlage.id))).scalars().all())
    kwp = anlagen_kwp(invs, tag, mit_bkw=True, referenzwert=anlage.leistung_kwp)
    return await performance_ratio_des_tages(db, anlage, tag, tz.gti_summe_wh_m2, kwp, zeilen=zeilen,
                                             komponenten_kwh=tz.komponenten_kwh,
                                             sonstige_erzeuger_ids=sonstige_erzeuger_ids_von(invs))


async def _wetter_und_preis_wie_vorher(db: AsyncSession, anlage, tag: date, tz_alt: Optional[dict],
                                       std_alt: dict[int, dict]) -> int:
    """Nach dem Neubilden: Abruf-Spalten wie vorher, Performance Ratio aus ihnen neu. Returns: Zahl der gesetzten Werte."""
    from backend.models.tages_energie_profil import TagesEnergieProfil, TagesZusammenfassung

    zeilen = list((await db.execute(select(TagesEnergieProfil).where(
        TagesEnergieProfil.anlage_id == anlage.id, TagesEnergieProfil.datum == tag))).scalars().all())
    n = sum(_wie_vorher(r, std_alt.get(r.stunde) or {}, STUNDE_ABRUF) for r in zeilen)
    tz = (await db.execute(select(TagesZusammenfassung).where(
        TagesZusammenfassung.anlage_id == anlage.id, TagesZusammenfassung.datum == tag))).scalar_one_or_none()
    if tz is not None:
        n += _wie_vorher(tz, tz_alt or {}, TAG_ABRUF)
        await db.flush()
        tz.performance_ratio = await _performance_ratio(db, anlage, tag, tz, zeilen)
    return n


async def _ein_tag(sitzungen, anlage_id: int, tag: date) -> int:
    from backend.models.anlage import Anlage
    from backend.services.energie_profil._helpers import ohne_abruf
    from backend.services.repair_orchestrator import _reparatur_aggregat

    async with sitzungen() as db:
        anlage = (await db.execute(select(Anlage).where(Anlage.id == anlage_id))).scalar_one_or_none()
        if anlage is None:
            raise LookupError(f"Anlage {anlage_id} gibt es nicht mehr")
        tz_alt, std_alt = await _tag_vorher(db, anlage_id, tag)
        boerse = {h: w["boersenpreis_cent"] for h, w in std_alt.items() if w.get("boersenpreis_cent") is not None}
        with ohne_abruf({tag: boerse}):
            neu, _quelle = await _reparatur_aggregat(anlage, tag, db)
        await db.flush()
        n = 0 if neu is None else await _wetter_und_preis_wie_vorher(db, anlage, tag, tz_alt, std_alt)
        await db.commit()
    return n


async def _schreibe(sitzungen, lauf: str, **werte) -> dict:
    from backend.models.settings import Settings

    async with sitzungen() as db:
        row = (await db.execute(select(Settings).where(Settings.key == PRAEFIX + lauf))).scalar_one()
        neu = {**(row.value or {}), **werte}
        row.value = neu
        flag_modified(row, "value")
        await db.commit()
    return neu


def _ist_fuellen_fehler(f: Any) -> bool:
    return isinstance(f, dict) and f.get("tag") is None and str(f.get("grund") or "").startswith(FUELLEN_PRAEFIX)


async def _nachlauf(sitzungen, lauf: str, z: dict) -> tuple[dict, bool]:
    """Der offene Nachlauf (Füllen, abhängige abgeleitete Kanäle) vor den Tagen. Returns: ``(Zustand, weiter?)`` —
    scheitert er, steht der Grund unter ``fehler`` und der Lauf bleibt ``laeuft`` (nächster Start, Werkbank)."""
    from backend.services.zuordnung_wechsel.korrektur import nachlauf_aus_auftrag

    f = z.get("fuellen")
    if not isinstance(f, dict) or f.get("erledigt"):
        return z, True
    try:
        n = await nachlauf_aus_auftrag(sitzungen, int(z["anlage_id"]), f)
    except Exception as e:  # noqa: BLE001 — der Grund steht im Zustand, der Lauf bleibt offen
        logger.warning("Korrektur %s: Füllen nicht möglich: %s: %s", lauf, type(e).__name__, e)
        # Je Lauf ein Eintrag «Füllen: …» — der letzte Versuch ersetzt den vorigen (stündlicher Anstoß, §11 Nr. 46).
        fehler = [f for f in (z.get("fehler") or []) if not _ist_fuellen_fehler(f)]
        fehler.append({"tag": None, "grund": f"{FUELLEN_PRAEFIX}{type(e).__name__}: {e}"})
        return await _schreibe(sitzungen, lauf, fehler=fehler), False
    return await _schreibe(sitzungen, lauf, fuellen={**f, "erledigt": True, **n}), True


async def nachlauf_erledigt(sitzungen, lauf: str, kanal_neu_gespiegelt: int, abgeleitet_neu: int, *,
                            staende_offen: bool = False) -> None:
    """Der Nachlauf ist gelaufen (direkt nach dem Commit); ohne Tage ist der Lauf damit fertig. ``staende_offen``: nur der
    Kanal-Teil ist gelaufen (``kanal_erledigt``), das Speichern der Stände (Bauplan «Zu §14» Nr. 111) macht der
    Hintergrund-Lauf — bis dahin bleibt der Auftrag offen und das Intervall eine Lücke (Nr. 106)."""
    async with sitzungen() as db:
        z = await stand(db, lauf)
    if z is None or not isinstance(z.get("fuellen"), dict):
        return
    werte: dict[str, Any] = {"fuellen": {**z["fuellen"], "kanal_neu_gespiegelt": kanal_neu_gespiegelt,
                                         "abgeleitet_neu": abgeleitet_neu,
                                         **({"kanal_erledigt": True} if staende_offen else {"erledigt": True})}}
    if not z.get("tage") and not staende_offen:
        werte.update(status=FERTIG, ende=datetime.now().replace(microsecond=0).isoformat())
    await _schreibe(sitzungen, lauf, **werte)


async def tage_neu_bilden(sitzungen, lauf: str) -> Optional[dict]:
    """Den Lauf vom nächsten offenen Tag an fortsetzen bis zum Ende (Fortschritt nach jedem Tag); ein offener Nachlauf zuerst."""
    from backend.services.kanal import merken

    async with sitzungen() as db:
        z = await stand(db, lauf)
    if z is None or z.get("status") != LAEUFT:
        return z
    z, weiter = await _nachlauf(sitzungen, lauf, z)
    if not weiter:
        return z
    tage = [date.fromisoformat(t) for t in z["tage"]]
    for i in range(int(z.get("erledigt") or 0), len(tage)):
        fehler, behalten = list(z.get("fehler") or []), int(z.get("behalten") or 0)
        try:
            behalten += await _ein_tag(sitzungen, int(z["anlage_id"]), tage[i])
        except Exception as e:  # noqa: BLE001 — ein Tag hält die übrigen nicht auf; der Grund steht im Zustand
            logger.warning("Korrektur %s: Tag %s nicht neu gebildet: %s: %s", lauf, tage[i], type(e).__name__, e)
            fehler.append({"tag": tage[i].isoformat(), "grund": f"{type(e).__name__}: {e}"})
        z = await _schreibe(sitzungen, lauf, erledigt=i + 1, fehler=fehler, behalten=behalten)
    merken.invalidiere(int(z["anlage_id"]))
    return await _schreibe(sitzungen, lauf, status=FERTIG, ende=datetime.now().replace(microsecond=0).isoformat())


def starten(lauf: str, *, sitzungen=None) -> Optional[asyncio.Task]:
    """Den Lauf als Hintergrund-Aufgabe starten (höchstens eine je Lauf)."""
    alt = _AUFGABEN.get(lauf)
    if alt is not None and not alt.done():
        return None

    async def _lauf() -> None:
        from backend.core.database import get_session

        try:
            await tage_neu_bilden(sitzungen or get_session, lauf)
        except Exception as e:  # noqa: BLE001 — eine Hintergrund-Aufgabe darf den Prozess nicht stören
            logger.warning("Korrektur %s abgebrochen: %s: %s", lauf, type(e).__name__, e)

    _AUFGABEN[lauf] = asyncio.get_running_loop().create_task(_lauf())
    return _AUFGABEN[lauf]


async def offene_laeufe(db: AsyncSession) -> list[str]:
    from backend.models.settings import Settings

    return [row.key[len(PRAEFIX):] for row in (await db.execute(
        select(Settings).where(Settings.key.like(PRAEFIX + "%")))).scalars().all()
        if isinstance(row.value, dict) and row.value.get("status") == LAEUFT]


async def laufende_der_anlage(db: AsyncSession, anlage_id: int) -> list[dict[str, Any]]:
    """Die Läufe einer Anlage mit ``status = laeuft`` (Lese-Route der Datenquellen-Fläche, Bauplan §11 Nr. 50): ``lauf``,
    ``sensor_key``, ``beginn`` — ältester zuerst. Auch ein Lauf, der nur noch auf das Füllen wartet (Nr. 46)."""
    from backend.models.settings import Settings

    out = []
    for row in (await db.execute(select(Settings).where(Settings.key.like(PRAEFIX + "%")))).scalars().all():
        z = row.value if isinstance(row.value, dict) else {}
        if z.get("status") == LAEUFT and z.get("anlage_id") == anlage_id:
            out.append({"lauf": row.key[len(PRAEFIX):], "sensor_key": z.get("sensor_key"), "beginn": z.get("beginn")})
    return sorted(out, key=lambda e: (str(e["beginn"] or ""), e["lauf"]))


def offene_anstossen(*, sitzungen=None) -> asyncio.Task:
    """Vom Stundenlauf gerufen (``scheduler.sensor_snapshot_job``, Bauplan §11 Nr. 46): jeden Lauf mit ``status = laeuft``
    neu anstoßen — über ``starten``, also nie neben einer Aufgabe, die ihn schon bearbeitet. So holt eedc ein gescheitertes
    Füllen nach, sobald Home Assistant wieder erreichbar ist, und setzt einen unterbrochenen Lauf fort. Returns die Aufgabe
    des Anstoßes (Proben warten darauf)."""

    async def _anstoss() -> list[str]:
        from backend.core.database import get_session

        try:
            async with (sitzungen or get_session)() as db:
                laeufe = await offene_laeufe(db)
            return [lauf for lauf in laeufe if starten(lauf, sitzungen=sitzungen) is not None]
        except Exception as e:  # noqa: BLE001 — eine Hintergrund-Aufgabe darf den Stundenlauf nicht stören
            logger.warning("Korrektur-Läufe anstoßen: %s: %s", type(e).__name__, e)
            return []

    return asyncio.get_running_loop().create_task(_anstoss())


async def fortsetzen_nach_dem_start(*, warte_s: float = 150.0, sitzungen=None) -> list[str]:
    """Nach dem Start (``main.py``): jeder unterbrochene Lauf setzt beim nächsten Tag fort — über ``starten``, also nie
    neben einer Aufgabe, die denselben Lauf schon bearbeitet (``_AUFGABEN``). Fertige alte Läufe werden aufgeräumt."""
    from backend.core.database import get_session

    try:
        await asyncio.sleep(warte_s)
        async with (sitzungen or get_session)() as db:
            await aufraeumen(db)
            await db.commit()
            laeufe = await offene_laeufe(db)
        for lauf in laeufe:
            aufgabe = starten(lauf, sitzungen=sitzungen)
            if aufgabe is not None:
                await aufgabe
        return laeufe
    except Exception as e:  # noqa: BLE001
        logger.warning("Korrektur-Läufe nach dem Start: %s: %s", type(e).__name__, e)
        return []
