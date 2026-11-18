"""Korrektur eines Sensorwechsels als **ein** Lauf (Sensorwechsel mit Grund, Bauplan B-6, Konzept S-4/S-9; Sitzung 3).

Der Anwender sagt: «bisher war der falsche Sensor zugeordnet, seit ``falsch_seit``». Für das Intervall ``[falsch_seit, ab)``
gilt danach die richtige (heutige) Quelle; was die falsche dort hinterlassen hat, wird verworfen und — soweit Home Assistant
die Geschichte des richtigen Sensors führt — aus ihr neu gefüllt. Fünf Schritte:

1. **Wechsel-Zeile** (``zuordnung_wechsel``: ``grund = korrektur``, ``falsch_seit_ts``, ``ab_ts``) — mit ihr liefert
   ``zeitpunkt.quelle_am`` im Intervall ``nachher`` (B-0). Eine frühere Zeile ohne Grund, die denselben Wechsel beschreibt
   (gleiche neue Quelle, ``ab_ts`` im Intervall oder höchstens eine Stunde danach), wird aufgehoben (``aufgehoben_durch``).
2. **Im Intervall verwerfen:** Kanalzeilen nur in Abschnitten, deren Quelle nicht die richtige ist (``kanal/korrektur.py``) ·
   Zählerstände (``sensor_snapshots`` des Schlüssels) · MQTT-Rohstände des Schlüssels · Feldschlüssel der Tageszeilen nach den
   Regeln der Werkbank (``verwerfen_vor_quellbeginn.leere_bestand``; Tage, deren Fenster ganz im Intervall liegt; Monate mit
   Abschluss bleiben). Für die Reihe heißt Korrektur «verwerfen, dann füllt B-0 aus der richtigen Quelle» (§8 Nr. 16).
3. **Kanal:** die richtige Quelle beginnt mit ihrer ersten Zeile im Intervall, ein Versatz nach R2, gefüllt mit dem
   Blockleser von ``neu_spiegeln``.
4. **Tageszeilen** der Tage, deren Fenster das Intervall schneidet und deren Tageszeile einen Schlüssel des Felds trägt
   (§7 Nr. 10, ohne Blick auf seine Herkunft: §10 Nr. 35), im Hintergrund neu bilden — mit Fortschritt, fortsetzbar nach einem Neustart
   (``korrektur_lauf.py``); Wetter und Börsenpreis bleiben, wie sie gespeichert sind (kein Abruf, §10 Nr. 32).
5. **Merker** verwerfen (gemerkte Kanal-Tage, Wechsel-Merkliste der Sitzung).

**Home Assistant:** eingerichtet, aber nicht erreichbar ⇒ der Lauf startet nicht (``KorrekturNichtStartbar``). Ohne Home
Assistant (Standalone) laufen die Schritte 1, 2 und 5 — nichts wird gefüllt, kein Tag neu gebildet.
**Endgültig** (Bauplan G-2): der Rückweg ist eine Sicherung von Home Assistant bzw. ohne Home Assistant der
eedc-Datenbank; die Vorschau sagt es.

Aufrufer: die Werkbank-Operation «Werte vor dem Sensorbeginn verwerfen» (``services/verwerfen_vor_quellbeginn.fuehre_aus``,
S-9: ``falsch_seit`` offen = von Beginn an, ``ab`` = Beginn des jüngsten Sensors) und seit Sitzung 3b der Dialog beim
Sensorwechsel (``abfrage.vollziehe``: Feld-Route, Preset; ``ab`` = nächste volle Stunde, richtig ist die neue Quelle).

**Robust (Sitzung 3b, Bauplan §10 Nr. 40):** eine wiederholte gleiche Korrektur (gleicher Schlüssel, gleiche richtige Quelle,
Intervall schon von einer Korrektur-Zeile gedeckt) legt keine zweite Zeile an. Der Nachlauf nach dem Commit (Füllen, abhängige
abgeleitete Kanäle) steht als Auftrag im Zustand des Laufs (``nachlauf_auftrag``); scheitert er, holt ihn der Lauf nach.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any, Optional

from sqlalchemy import and_, delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.zuordnung_wechsel import GRUND_KORREKTUR, HERKUNFT_NACHTRAG, ZuordnungWechsel

logger = logging.getLogger(__name__)

_STUNDE = 3600


class KorrekturNichtStartbar(ValueError):
    """Home Assistant ist eingerichtet, aber nicht erreichbar — der Lauf startet nicht."""


@dataclass(frozen=True)
class Auftrag:
    anlage_id: int
    sensor_key: str
    #: Erste falsche Stunde (örtlich ohne Zone, volle Stunde); ``None`` = von Beginn an (Werkbank, S-9).
    falsch_seit: Optional[datetime]
    #: Erste Stunde der richtigen Quelle (``ab_ts``).
    ab: datetime
    vorher: Optional[dict]
    nachher: Optional[dict]
    herkunft: str = HERKUNFT_NACHTRAG
    erklaert: Optional[datetime] = None


def richtige_entitaet(nachher: Optional[dict]) -> Optional[str]:
    return nachher.get("entity_id") if isinstance(nachher, dict) and nachher.get("art") == "ha" else None


def _ts(dt: Optional[datetime]) -> Optional[int]:
    return None if dt is None else int(dt.timestamp())


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
        raise KorrekturNichtStartbar(
            "Home Assistant ist nicht erreichbar — die Korrektur startet erst, wenn eedc die Langzeitstatistik lesen kann.")
    return ha_svc


# ── Lage (lesend) ───────────────────────────────────────────────────────────


@dataclass
class Lage:
    auftrag: Auftrag
    label: str
    kanal: Any                     # kanal/korrektur.KanalLage
    zaehlerstaende: int
    rohstaende: int
    bestand: Any                   # verwerfen_vor_quellbeginn.BestandZaehlung
    ziele: Any
    abschluss: frozenset
    tage_neu: list[date] = field(default_factory=list)
    mit_ha: bool = False
    nicht_startbar: Optional[str] = None
    von2: Optional[date] = None
    bis2: Optional[date] = None

    @property
    def nichts_zu_tun(self) -> bool:
        return not (self.kanal.zeilen or self.kanal.offen or self.zaehlerstaende or self.rohstaende or self.bestand.tage)

    def abschluss_monate(self) -> list[tuple[int, int]]:
        tage = set(self.tage_neu) | set(self.bestand.abschluss_tage)
        return sorted({(d.year, d.month) for d in tage if (d.year, d.month) in self.abschluss})


def _ganze_tage(f: Optional[datetime], ab: datetime) -> tuple[Optional[date], date]:
    """Die Bestandstage (Fenster ``[Vortag 23:00, 23:00)``), deren Fenster ganz in ``[f, ab)`` liegt."""
    from backend.services.kanal.abgeleitet import tag_der_stunde

    bis = tag_der_stunde(int(ab.timestamp())) - timedelta(days=1)
    if f is None:
        return None, bis
    von = tag_der_stunde(int(f.timestamp()))
    if datetime.combine(von - timedelta(days=1), datetime.min.time()).replace(hour=23) < f:
        von += timedelta(days=1)
    return von, bis


async def _zaehle(db, modell, spalte_key, key, spalte_zeit, f, ab, anlage_id) -> int:
    bed = [modell.anlage_id == anlage_id, spalte_key == key, spalte_zeit < ab]
    if f is not None:
        bed.append(spalte_zeit >= f)
    return int((await db.execute(select(func.count()).select_from(modell).where(and_(*bed)))).scalar_one())


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


async def lage(db: AsyncSession, a: Auftrag, *, ha_svc=None) -> Lage:
    """Beide Schichten zählen, nichts schreiben. ``ha_svc``: der Dienst des Laufs (``ha_dienst``) oder ``None``."""
    from backend.models.anlage import Anlage
    from backend.models.mqtt_energy_snapshot import MqttEnergySnapshot
    from backend.models.sensor_snapshot import SensorSnapshot
    from backend.services import verwerfen_vor_quellbeginn as vq
    from backend.services.kanal.korrektur import kanal_lage
    from backend.services.snapshot.keys import _sensor_key_to_mqtt_key

    anlage = (await db.execute(select(Anlage).where(Anlage.id == a.anlage_id))).scalar_one_or_none()
    if anlage is None:
        raise LookupError(f"Anlage {a.anlage_id} nicht gefunden")
    k = await kanal_lage(db, a.anlage_id, a.sensor_key, _ts(a.falsch_seit), int(a.ab.timestamp()),
                         richtige_entitaet(a.nachher))
    ab_staende = await wirksames_ab(db, a, k.w0)
    zs = await _zaehle(db, SensorSnapshot, SensorSnapshot.sensor_key, a.sensor_key, SensorSnapshot.zeitpunkt,
                       a.falsch_seit, ab_staende, a.anlage_id)
    mk = _sensor_key_to_mqtt_key(a.sensor_key)
    rs = await _zaehle(db, MqttEnergySnapshot, MqttEnergySnapshot.energy_key, mk, MqttEnergySnapshot.timestamp,
                       a.falsch_seit, ab_staende, a.anlage_id) if mk else 0
    ziele = await vq.bestand_ziele(db, anlage, a.sensor_key)
    abschluss = await vq.abschluss_monate(db, a.anlage_id)
    von2, bis2 = _ganze_tage(a.falsch_seit, a.ab)
    bestand = await vq.zaehle_bestand(db, a.anlage_id, ziele, bis2, abschluss, von2) if (von2 is None or von2 <= bis2) \
        else vq.BestandZaehlung()
    la = Lage(a, vq.feld_label(a.sensor_key, await vq._investitionen(db, a.anlage_id)), k, zs, rs, bestand, ziele,
              abschluss, mit_ha=ha_svc is not None, von2=von2, bis2=bis2)
    if ha_svc is not None:
        la.tage_neu = await tage_neu_bilden_liste(db, a, ziele)
    return la


def _monate(monate: list[tuple[int, int]]) -> str:
    from backend.services.verwerfen_vor_quellbeginn import _monate_text

    return _monate_text(monate)


#: Die Wortlaute der Vorschau (Bauplan B-6 «Vorschau nennt», §10 Nr. 37; mit und ohne Home Assistant).
SATZ_TAGE = ("{n} Tage werden im Hintergrund neu gebildet: alle Zähler dieser Tage werden neu aus Home Assistant gelesen; "
             "Wetter und Börsenpreis bleiben.")
SATZ_STUNDENMITTEL = ("Bei älteren Tagen kommt die Leistung je Stunde danach aus der Langzeitstatistik von Home Assistant "
                      "(Stundenmittel), nicht mehr aus dem damaligen Verlauf.")
SATZ_KEIN_TAG = "Kein Tag muss neu gebildet werden; der Wert dieses Felds kommt danach aus dem richtigen Sensor."
SATZ_OHNE_HA = "Ohne Home Assistant werden die Werte nur verworfen — kein Tag wird neu gebildet."
SATZ_MONATE_NEU = ("Abgeschlossene Monate {liste}: die gespeicherten Monatswerte bleiben aus dem bisherigen Sensor; was eedc "
                   "im Monat aus den Tagen rechnet, folgt den neu gebildeten Tagen.")
SATZ_MONATE = "Abgeschlossene Monate {liste}: die gespeicherten Monatswerte bleiben aus dem bisherigen Sensor."
SATZ_RUECKWEG_HA = ("Die Korrektur lässt sich in eedc nicht rückgängig machen — der Rückweg ist eine Sicherung von Home "
                    "Assistant.")
SATZ_RUECKWEG_OHNE = ("Die Korrektur lässt sich in eedc nicht rückgängig machen — der Rückweg ist eine Sicherung der "
                      "eedc-Datenbank.")


def _saetze_monate(la: Lage) -> list[str]:
    """Abgeschlossene Monate: mit neu gebildeten Tagen folgt, was eedc im Monat aus den Tagen rechnet, den neuen Tagen."""
    neu = {(d.year, d.month) for d in la.tage_neu} if la.mit_ha else set()
    monate = la.abschluss_monate()
    s = []
    if [m for m in monate if m in neu]:
        s.append(SATZ_MONATE_NEU.format(liste=_monate([m for m in monate if m in neu])))
    if [m for m in monate if m not in neu]:
        s.append(SATZ_MONATE.format(liste=_monate([m for m in monate if m not in neu])))
    return s


def saetze(la: Lage) -> list[str]:
    """Die Vorschau in Anwender-Sprache (Bauplan B-6 «Vorschau nennt», §10 Nr. 37)."""
    from backend.core.zahlenformat import fmt_zahl

    if la.nicht_startbar:
        return [la.nicht_startbar]
    s = []
    if la.zaehlerstaende or la.rohstaende:
        s.append(f"Zählerstände dieses Felds im Zeitraum werden verworfen ({fmt_zahl(la.zaehlerstaende + la.rohstaende)}).")
    if not la.mit_ha:
        s.append(SATZ_OHNE_HA)
    elif la.tage_neu:
        s += [SATZ_TAGE.format(n=fmt_zahl(len(la.tage_neu))), SATZ_STUNDENMITTEL]
    else:
        s.append(SATZ_KEIN_TAG)
    s += _saetze_monate(la)
    s.append(SATZ_RUECKWEG_HA if la.mit_ha else SATZ_RUECKWEG_OHNE)
    return s


#: Der Kanal in der Dialog-Vorschau (Bauplan §11 Nr. 48; an der Werkbank-Vorschau ausgerichtet).
SATZ_KANAL_AB = ("Home Assistant führt die Geschichte des richtigen Sensors erst ab {zeit} Uhr — die Zeit davor hat danach "
                 "keinen Wert.")
SATZ_KANAL_OHNE_GESCHICHTE = ("Home Assistant führt für den richtigen Sensor in diesem Zeitraum keine Geschichte — das Feld hat "
                              "dort danach keinen Wert.")
SATZ_KANAL_MQTT = ("Eine MQTT-Quelle hat keine Geschichte, die eedc nachholen könnte — von «Falsch seit» bis jetzt hat das Feld "
                   "danach keinen Wert.")


async def kanal_saetze(la: Lage, ha_svc) -> list[str]:
    """Die Dialog-Vorschau nennt den Kanal (Bauplan §11 Nr. 48): ab wann Home Assistant die Geschichte des richtigen Sensors
    führt, wenn das nach dem Beginn des verworfenen Teils (``w0``) liegt, und dass eine MQTT-Quelle keine Geschichte
    nachholt. Derselbe Beginn ``h0`` wie im Lauf (``kanal/korrektur.erste_ha_zeile`` ab ``w0`` bis zum Soll-Ende) —
    Vorschau = Lauf. Ohne Home Assistant sagt ``SATZ_OHNE_HA`` genug."""
    from backend.services.kanal.korrektur import erste_ha_zeile, fuell_ende

    if la.nicht_startbar:
        return []
    eid = richtige_entitaet(la.auftrag.nachher)
    if eid is None:
        return [SATZ_KANAL_MQTT] if (la.kanal.zeilen or la.zaehlerstaende or la.rohstaende) else []
    if ha_svc is None or la.kanal.w0 is None:
        return []
    h0 = await erste_ha_zeile(ha_svc, eid, la.kanal.w0, fuell_ende(int(datetime.now().timestamp())))
    if h0 is None:
        return [SATZ_KANAL_OHNE_GESCHICHTE]
    return [SATZ_KANAL_AB.format(zeit=datetime.fromtimestamp(h0).strftime("%d.%m.%Y %H:%M"))] if h0 > la.kanal.w0 else []


def vorschau_daten(la: Lage) -> dict[str, Any]:
    return {
        "zaehlerstaende": la.zaehlerstaende, "rohstaende": la.rohstaende,
        "tage_neu": [d.isoformat() for d in la.tage_neu], "mit_home_assistant": la.mit_ha,
        "abschluss_monate": [f"{j}-{m:02d}" for j, m in la.abschluss_monate()], "startbar": la.nicht_startbar is None,
    }


# ── Ausführung ──────────────────────────────────────────────────────────────


def _beginn(a: Auftrag, w0: Optional[int]) -> datetime:
    """``falsch_seit`` der Wechsel-Zeile: wie angegeben, «von Beginn an» = Beginn des falschen Teils im Kanal (``w0``)."""
    return a.falsch_seit or (datetime.fromtimestamp(w0) if w0 is not None else a.ab)


async def _ersetzte(db: AsyncSession, a: Auftrag, f: datetime) -> list[ZuordnungWechsel]:
    """Frühere Zeilen ohne Grund für denselben Wechsel (gleiche neue Quelle, ``ab_ts`` in ``[f, ab + 1 h]``)."""
    alte = (await db.execute(select(ZuordnungWechsel).where(and_(
        ZuordnungWechsel.anlage_id == a.anlage_id, ZuordnungWechsel.sensor_key == a.sensor_key,
        ZuordnungWechsel.aufgehoben_durch.is_(None), ZuordnungWechsel.ab_ts >= f,
        ZuordnungWechsel.ab_ts <= a.ab + timedelta(hours=1))))).scalars().all()
    return [w for w in alte if w.grund != GRUND_KORREKTUR and (w.nachher or {}) == (a.nachher or {})]


async def wirksames_ab(db: AsyncSession, a: Auftrag, w0: Optional[int]) -> datetime:
    """Das ``ab_ts`` der Wechsel-Zeile: ``ab`` oder später, wenn eine aufgehobene Zeile später beginnt (§10 Nr. 36 — Vorschau
    und Lauf verwerfen die Zählerstände bis hierher)."""
    return max([a.ab] + [w.ab_ts for w in await _ersetzte(db, a, _beginn(a, w0))])


async def _gleiche_korrektur(db: AsyncSession, a: Auftrag, f: datetime, ab: datetime) -> Optional[ZuordnungWechsel]:
    """Eine Korrektur-Zeile, die dieselbe Korrektur schon trägt (gleiche richtige Quelle, Intervall ``[f, ab)`` gedeckt)."""
    zeilen = (await db.execute(select(ZuordnungWechsel).where(and_(
        ZuordnungWechsel.anlage_id == a.anlage_id, ZuordnungWechsel.sensor_key == a.sensor_key,
        ZuordnungWechsel.grund == GRUND_KORREKTUR, ZuordnungWechsel.aufgehoben_durch.is_(None),
        ZuordnungWechsel.falsch_seit_ts <= f, ZuordnungWechsel.ab_ts >= ab)).order_by(ZuordnungWechsel.id))).scalars().all()
    return next((w for w in reversed(zeilen) if (w.nachher or {}) == (a.nachher or {})), None)


async def _wechsel_zeile(db: AsyncSession, a: Auftrag, jetzt: datetime, lauf: str, w0: Optional[int]) -> ZuordnungWechsel:
    """Schritt 1 — mit Aufheben einer früheren Zeile ohne Grund für denselben Wechsel; eine wiederholte gleiche Korrektur
    nimmt ihre Zeile wieder (``lauf`` = der neue Lauf), statt eine zweite anzulegen."""
    from backend.services.zuordnung_wechsel.zeitpunkt import merke_neu, vergiss

    f = _beginn(a, w0)
    ersetzt = await _ersetzte(db, a, f)
    ab = max([a.ab] + [w.ab_ts for w in ersetzt])
    gleich = await _gleiche_korrektur(db, a, f, ab)
    if gleich is not None:
        gleich.lauf = lauf
        await db.flush()
        return gleich
    row = ZuordnungWechsel(anlage_id=a.anlage_id, sensor_key=a.sensor_key, erklaert_ts=(a.erklaert or jetzt),
                           ab_ts=ab, vorher=a.vorher, nachher=a.nachher, grund=GRUND_KORREKTUR, falsch_seit_ts=f,
                           herkunft=a.herkunft, lauf=lauf)
    db.add(row)
    await db.flush()
    for w in ersetzt:
        w.aufgehoben_durch = row.id
    vergiss(db, a.anlage_id)
    merke_neu(db, row)
    return row


async def _verwerfe_staende(db: AsyncSession, a: Auftrag, ab: datetime) -> tuple[int, int]:
    from backend.models.mqtt_energy_snapshot import MqttEnergySnapshot
    from backend.models.sensor_snapshot import SensorSnapshot
    from backend.services.snapshot.keys import _sensor_key_to_mqtt_key

    bed = [SensorSnapshot.anlage_id == a.anlage_id, SensorSnapshot.sensor_key == a.sensor_key, SensorSnapshot.zeitpunkt < ab]
    if a.falsch_seit is not None:
        bed.append(SensorSnapshot.zeitpunkt >= a.falsch_seit)
    zs = int((await db.execute(delete(SensorSnapshot).where(and_(*bed)))).rowcount or 0)
    mk = _sensor_key_to_mqtt_key(a.sensor_key)
    rs = 0
    if mk:
        bed = [MqttEnergySnapshot.anlage_id == a.anlage_id, MqttEnergySnapshot.energy_key == mk,
               MqttEnergySnapshot.timestamp < ab]
        if a.falsch_seit is not None:
            bed.append(MqttEnergySnapshot.timestamp >= a.falsch_seit)
        rs = int((await db.execute(delete(MqttEnergySnapshot).where(and_(*bed)))).rowcount or 0)
    return zs, rs


async def fuehre_aus(db: AsyncSession, a: Auftrag, *, ha_svc=None, jetzt: Optional[datetime] = None,
                     bestand_leeren: bool = True) -> dict[str, Any]:
    """Schritte 1, 2, 3 (ohne Füllen) und 5 in der Sitzung des Aufrufers, ein Commit; danach Füllen des Kanals und der
    Auftrag für Schritt 4 (``korrektur_lauf``). ``ha_svc`` = ``ha_dienst(...)`` (``None`` = ohne HA). Die Aktivität schreibt
    der Aufrufer (N-532: in dieser Sitzung, vor dem Commit — Rückgabe ``aktivitaet`` hilft ihm)."""
    from backend.core.database import get_session
    from backend.services import verwerfen_vor_quellbeginn as vq
    from backend.services.kanal import merken
    from backend.services.kanal.korrektur import fuell_ende, korrigiere_kanal
    from backend.services.zuordnung_wechsel import korrektur_lauf

    jetzt = (jetzt or datetime.now()).replace(microsecond=0)
    la = await lage(db, a, ha_svc=ha_svc)
    lauf = uuid.uuid4().hex[:12]
    bis_ts = fuell_ende(int(jetzt.timestamp()))
    kk = await korrigiere_kanal(db, a.anlage_id, a.sensor_key, _ts(a.falsch_seit), int(a.ab.timestamp()),
                                richtige_entitaet(a.nachher), ha_svc=ha_svc, jetzt_ts=int(jetzt.timestamp()), bis_ts=bis_ts)
    row = await _wechsel_zeile(db, a, jetzt, lauf, kk.w0)
    zs, rs = await _verwerfe_staende(db, a, row.ab_ts)
    bestand = {"stundenzeilen_geleert": 0, "tageszeilen_geleert": 0, "felder_geleert": 0}
    if bestand_leeren and (la.von2 is None or la.von2 <= la.bis2):
        bestand = await vq.leere_bestand(db, a.anlage_id, la.ziele, la.bis2, la.abschluss, la.von2)
    tage = la.tage_neu if ha_svc is not None else []
    nach = nachlauf_auftrag(kk, ha_svc, bis_ts, jetzt)
    if tage or nach is not None:
        await korrektur_lauf.anlegen(db, lauf, a.anlage_id, a.sensor_key, tage, fuellen=nach)
    merken.invalidiere(a.anlage_id, db=db)                         # Schritt 5
    summary = {"lauf": lauf, "wechsel_id": row.id, "kanalzeilen_geloescht": kk.geloescht,
               "abgeleitet_verworfen": kk.abgeleitet_verworfen,
               "quellen_markiert": kk.markiert, "kanal_beginn": kk.h0, "versatz": kk.versatz,
               "zaehlerstaende_geloescht": zs, "rohstaende_geloescht": rs, "tage_neu": len(tage), **bestand}
    return {"summary": summary, "kanal": kk, "lage": la, "bis_ts": bis_ts, "jetzt": jetzt,
            "sitzungen": sitzungen_wie(db, get_session)}


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


def nachlauf_auftrag(kk, ha_svc, bis_ts: int, jetzt: datetime) -> Optional[dict]:
    """Der Nachlauf nach dem Commit als Auftrag im Zustand des Laufs (``None`` = nichts zu tun): Kanal füllen (mit Home
    Assistant und einem Beginn der richtigen Quelle) und die verworfenen abhängigen abgeleiteten Kanäle neu schreiben."""
    fuellen = ha_svc is not None and kk.h0 is not None and kk.kanal_id is not None
    if not fuellen and not kk.abgeleitet_verworfen:
        return None
    return {"kanal_id": kk.kanal_id, "key": kk.key, "w0": kk.w0, "h0": kk.h0 if fuellen else None, "bis_ts": bis_ts,
            "familien": None if kk.abgeleitet_familien is None else sorted(kk.abgeleitet_familien),
            "abgeleitet_verworfen": kk.abgeleitet_verworfen, "jetzt": jetzt.isoformat(), "erledigt": False}


async def nachlauf_aus_auftrag(sitzungen, anlage_id: int, f: dict) -> dict[str, int]:
    """Den Nachlauf aus dem Auftrag ausführen (nach dem Commit oder nachgeholt vom Lauf). Returns: die Mengen."""
    from backend.services.kanal.korrektur import KanalKorrektur, fuelle_kanal, schreibe_abgeleitete_nach

    kk = KanalKorrektur(f["key"], kanal_id=f.get("kanal_id"), w0=f.get("w0"), h0=f.get("h0"),
                        abgeleitet_familien=None if f.get("familien") is None else frozenset(f["familien"]),
                        abgeleitet_verworfen=int(f.get("abgeleitet_verworfen") or 0))
    n = {"kanal_neu_gespiegelt": 0, "abgeleitet_neu": 0}
    if kk.h0 is not None:
        svc = ha_dienst(None)
        if svc is not None:
            n["kanal_neu_gespiegelt"] = await fuelle_kanal(sitzungen, anlage_id, kk, ha_svc=svc, bis_ts=int(f["bis_ts"]))
    n["abgeleitet_neu"] = await schreibe_abgeleitete_nach(sitzungen, anlage_id, kk, datetime.fromisoformat(f["jetzt"])) or 0
    return n


async def nach_dem_commit(ergebnis: dict, *, ha_svc=None, sitzungen=None, starten: bool = True) -> dict[str, Any]:
    """Nach dem Commit des Aufrufers: Kanal füllen (Schritt 3), die abhängigen abgeleiteten Kanäle neu schreiben (§10
    Nr. 34) und den Hintergrund-Lauf der Tage starten (Schritt 4). Scheitert der Nachlauf, holt ihn der Lauf nach (er steht
    als ``fuellen`` im Zustand); ``fuellen_offen`` in der Zusammenfassung sagt es dem Aufrufer."""
    from backend.services.kanal.korrektur import fuelle_kanal, schreibe_abgeleitete_nach
    from backend.services.zuordnung_wechsel import korrektur_lauf

    s = ergebnis["summary"]
    sitzungen = sitzungen or ergebnis["sitzungen"]
    anlage_id = ergebnis["lage"].auftrag.anlage_id
    hat_zustand = bool(s["tage_neu"]) or nachlauf_auftrag(ergebnis["kanal"], ha_svc, ergebnis["bis_ts"],
                                                          ergebnis["jetzt"]) is not None
    try:
        if ha_svc is not None:
            s["kanal_neu_gespiegelt"] = await fuelle_kanal(sitzungen, anlage_id, ergebnis["kanal"], ha_svc=ha_svc,
                                                           bis_ts=ergebnis["bis_ts"])
        s["abgeleitet_neu"] = await schreibe_abgeleitete_nach(sitzungen, anlage_id, ergebnis["kanal"], ergebnis["jetzt"])
    except Exception as e:  # noqa: BLE001 — der Lauf holt den Nachlauf nach (Zustand ``fuellen``)
        logger.warning("Korrektur %s: Füllen nach dem Commit gescheitert, der Lauf holt es nach: %s: %s",
                       s["lauf"], type(e).__name__, e)
        s["fuellen_offen"] = True
    else:
        if hat_zustand:
            await korrektur_lauf.nachlauf_erledigt(sitzungen, s["lauf"], s.get("kanal_neu_gespiegelt", 0),
                                                   s.get("abgeleitet_neu", 0))
    if hat_zustand and starten and (s["tage_neu"] or s.get("fuellen_offen")):
        korrektur_lauf.starten(s["lauf"], sitzungen=sitzungen)
    return s
