"""Korrektur über ein **abgeschlossenes Stück** (Sensorwechsel mit Grund, Bauplan «Zu §14» Nr. 93–98, Entscheid Gernot 18.11.2026).

Der Befund «Zählerstände – versetzter Abschnitt» (``zaehler_versatz``) meldet ein Stück ``[Sprung, Rückgang)`` der Standreihe
mit den Ständen eines anderen Sensors; davor und danach gilt dieselbe Quelle **E**. «Grund nachtragen → Korrektur» am Befund
ist ein Auftrag des Korrektur-Dienstes (``korrektur.py``) mit ``falsch_seit`` = Sprung, ``ab`` = Rückgang, ``vorher`` =
``nachher`` = E und ``stueck``:

* **füllbar** (``ist_fuellbar``: Home Assistant erreichbar, beide Rand-Stände der Reihe — der letzte Stand vor dem Sprung und
  der Stand am Rückgang — sind HAs Rohsumme von E innerhalb ``SPIEGEL_TOLERANZ_KWH``, und HA führt E am Sprung): das Stück
  wird verworfen, der Nachlauf liest es aus E neu und speichert es (``korrektur.fuelle_staende``, 4b-1-K2) — auf demselben
  Niveau wie die Reihe davor und danach (HAs Rohsumme, wie «Zuordnung zum Zeitpunkt» B-0).
* **nicht füllbar** (ohne Home Assistant, HAs Summe verschoben, keine Geschichte): das Stück wird verworfen und bekommt eine
  Lücken-Zeile (``korrektur._luecken_zeile``, ``zeitpunkt.ist_luecke``: nicht heilen, nicht füllen); da davor und danach E
  gilt, sind ihre Ränder keine Nähte, solange keine Fortsetzung dazwischen liegt — eedc rechnet wie über jede Zählerlücke
  (``zeitpunkt.ohne_hoehenwechsel``, Bauplan Nr. 119, Nr. 127 Option A; U1).

Dieselbe Fähigkeit trägt «Korrektur im Nachhinein» am **Rückkehr-Wechsel** X → A eines verzeichneten Stücks A → X → A: die
Zeit davor, vom Wechsel A → X bis zu diesem, mit richtig A (``nachtrag.stueck_des_wechsels``, Bauplan Nr. 96, Nr. 101). Das
Stück steht fest — kein frei wählbares «Falsch seit». Die Routen am Befund prüfen das Stück gegen die Erkennung
(``finde_lauf``): kein frei wählbares Stück. Bei verschiedenen Quellen an den Rändern nennt der Kopfsatz beide
(``SATZ_STUECK_ZWEI_QUELLEN``) und die Sperre den Grund.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any, Optional

from sqlalchemy import select

from backend.models.zuordnung_wechsel import HERKUNFT_NACHTRAG

#: Wortlaute (Sitzung 4b-1; gehen vor dem Commit an Gernot).
SATZ_STUECK = ("Vom {sprung} bis {rueckgang} Uhr liegen die gespeicherten Zählerstände dieses Felds um {versatz} kWh neben denen "
               "davor und danach; davor und danach gilt {quelle}.")
#: Kopfsatz bei verschiedenen Quellen an den Rändern (Bauplan «Zu §14» Nr. 104, S5) — der Sperrsatz folgt.
SATZ_STUECK_ZWEI_QUELLEN = ("Vom {sprung} bis {rueckgang} Uhr liegen die gespeicherten Zählerstände dieses Felds um {versatz} kWh "
                            "neben denen davor und danach; davor gilt {vorher}, danach {nachher}.")
SATZ_NICHT_GEMELDET = "Dieser Abschnitt ist in den gespeicherten Zählerständen nicht (mehr) zu finden — es ist nichts zu tun."
SATZ_VERSCHIEDENE_QUELLEN = ("Vor und nach diesem Abschnitt gelten verschiedene Quellen ({vorher} und {nachher}) — eedc weiß "
                             "nicht, welche hier die richtige ist, und korrigiert ihn deshalb nicht.")


@dataclass(frozen=True)
class Rand:
    """Ein Rand-Stand der Reihe außerhalb des Stücks."""
    zeitpunkt: datetime
    stand: float


async def _rand_vor(db, anlage_id: int, key: str, sprung: datetime) -> Optional[Rand]:
    from backend.models.sensor_snapshot import SensorSnapshot

    z = (await db.execute(select(SensorSnapshot.zeitpunkt, SensorSnapshot.wert_kwh).where(
        SensorSnapshot.anlage_id == anlage_id, SensorSnapshot.sensor_key == key, SensorSnapshot.zeitpunkt < sprung,
        SensorSnapshot.wert_kwh.is_not(None)).order_by(SensorSnapshot.zeitpunkt.desc()).limit(1))).one_or_none()
    return None if z is None else Rand(z[0], float(z[1]))


async def _rand_ab(db, anlage_id: int, key: str, rueckgang: datetime) -> Optional[Rand]:
    from backend.models.sensor_snapshot import SensorSnapshot

    z = (await db.execute(select(SensorSnapshot.zeitpunkt, SensorSnapshot.wert_kwh).where(
        SensorSnapshot.anlage_id == anlage_id, SensorSnapshot.sensor_key == key, SensorSnapshot.zeitpunkt >= rueckgang,
        SensorSnapshot.wert_kwh.is_not(None)).order_by(SensorSnapshot.zeitpunkt).limit(1))).one_or_none()
    return None if z is None else Rand(z[0], float(z[1]))


async def _ha_rohsumme(ha_svc, eid: str, key: str, z: datetime) -> Optional[float]:
    """HAs Rohsumme (bei Stand-Feldern ``state``) von ``eid`` um ``z`` — derselbe Abruf wie das Heilen eines Randes
    (``snapshot/reader.py``: ``get_value_at`` mit ``als_stand``), also der Wert, den B-0 ins Stück schreiben wird."""
    from backend.services.snapshot.keys import ist_stand_sensor_key
    from backend.services.zuordnung_wechsel.korrektur import ha_abruf

    return await ha_abruf(asyncio.to_thread(ha_svc.get_value_at, eid, z, als_stand=ist_stand_sensor_key(key)))


async def ist_fuellbar(db, a, ha_svc) -> bool:
    """Füllt «Zuordnung zum Zeitpunkt» das Stück ``[a.falsch_seit, a.ab)`` aus E (``a.nachher``) auf dem Niveau der Reihe?
    Ja, wenn HA erreichbar ist, E am Sprung führt und beide Rand-Stände (der letzte Stand vor dem Sprung, der Stand am
    Rückgang) HAs Rohsumme von E sind (``SPIEGEL_TOLERANZ_KWH``; ersetzt den Vergleich mit dem Spiegel + Versatz der heute
    zugeordneten Entität, Messblatt 4b-0 c). Vorschau und Lauf fragen dieselbe Funktion. Ein Abruf-Fehler von Home Assistant
    ist ``KorrekturNichtStartbar`` (``korrektur.ha_abruf``, Bauplan «Zu §14» Nr. 116 E-K6): die Prüf-Route antwortet wie bei
    «nicht erreichbar», der Lauf startet nicht."""
    from backend.core.berechnungen.zaehler_versatz import stand_passt_zum_spiegel
    from backend.services.zuordnung_wechsel.korrektur import richtige_entitaet

    eid = richtige_entitaet(a.nachher)
    if eid is None or ha_svc is None or a.falsch_seit is None:
        return False
    vor = await _rand_vor(db, a.anlage_id, a.sensor_key, a.falsch_seit)
    ab = await _rand_ab(db, a.anlage_id, a.sensor_key, a.ab)
    if vor is None or ab is None:
        return False
    for rand in (vor, ab):
        if not stand_passt_zum_spiegel(rand.stand, await _ha_rohsumme(ha_svc, eid, a.sensor_key, rand.zeitpunkt), 0.0):
            return False
    return await _ha_rohsumme(ha_svc, eid, a.sensor_key, a.falsch_seit) is not None


# ── Quelle an den Rändern ─────────────────────────────────────────────────────


async def _kanal_quelle_am(db, anlage_id: int, key: str, z: datetime) -> Optional[dict]:
    """Die Spiegel-Quelle des Kanals, die den Stand um ``z`` trägt (Zeile ``z − 1 h``) — die Entität, deren Rohsumme die Reihe
    dort führt, auch wenn kein Wechsel verzeichnet ist (ältere Entität, Messblatt 4b-0 c)."""
    from backend.models.kanal import ART_SUM, FAMILIE_SPIEGEL, Kanal, KanalQuelle

    q = (await db.execute(select(KanalQuelle.statistic_id, KanalQuelle.familie).join(Kanal, Kanal.id == KanalQuelle.kanal_id).where(
        Kanal.anlage_id == anlage_id, Kanal.key == key, Kanal.art == ART_SUM,
        KanalQuelle.gueltig_ab <= int(z.timestamp()) - 3600).order_by(KanalQuelle.gueltig_ab.desc()).limit(1))).one_or_none()
    if q is None or q[1] != FAMILIE_SPIEGEL or not q[0]:
        return None
    return {"art": "ha", "entity_id": q[0]}


async def quelle_am_rand(db, anlage, key: str, z: datetime) -> Optional[dict]:
    """Die Quelle, deren Stände die Reihe um ``z`` führt: eine verzeichnete (``zeitpunkt.quelle_am``), sonst die Spiegel-Quelle
    des Kanals, sonst die heutige wirksame Quelle. ``None`` = unbekannt."""
    from backend.services.zuordnung_wechsel.quelle import lade_wirksame_quellen, standard_quelle
    from backend.services.zuordnung_wechsel.zeitpunkt import HEUTE, quelle_zum_zeitpunkt

    q = await quelle_zum_zeitpunkt(db, anlage.id, key, z)
    if isinstance(q, dict):
        return q
    if q is not HEUTE:
        return None
    return await _kanal_quelle_am(db, anlage.id, key, z) or (await lade_wirksame_quellen(db, anlage)).get(key) \
        or standard_quelle(key)


def _gleiche_quelle(a: Optional[dict], b: Optional[dict]) -> bool:
    if not a or not b or a.get("art") != b.get("art"):
        return False
    return a.get("entity_id") == b.get("entity_id") if a.get("art") == "ha" else a == b


# ── Das Stück am Befund ──────────────────────────────────────────────────────


def _minute(t: datetime) -> datetime:
    return t.replace(second=0, microsecond=0)


async def finde_lauf(db, anlage_id: int, key: str, sprung: datetime, rueckgang: datetime):
    """Der versetzte Abschnitt der Erkennung (``core/berechnungen/zaehler_versatz.finde_versatz_laeufe`` über die Reihe des
    Befunds) mit genau diesem Sprung und Rückgang — sonst ``None`` (kein frei wählbares Stück)."""
    from backend.core.berechnungen.zaehler_versatz import finde_versatz_laeufe
    from backend.services.daten_checker.datenquelle.versatz import lade_reihe

    for lauf in finde_versatz_laeufe(await lade_reihe(db, anlage_id, key)):
        if _minute(lauf.beginn.bis) == _minute(sprung) and _minute(lauf.ende.bis) == _minute(rueckgang):
            return lauf
    return None


@dataclass
class StueckLage:
    """Was «Grund nachtragen» an einem Stück vorfindet (lesend)."""
    sensor_key: str
    sprung: datetime
    rueckgang: datetime
    satz: str
    quelle: Optional[dict] = None
    #: Warum keine Korrektur angeboten wird (Sperre mit Satz); ``None`` = sie wird angeboten.
    korrektur_nicht: Optional[str] = None

    def auftrag(self, anlage_id: int, jetzt: datetime):
        from backend.services.zuordnung_wechsel.korrektur import Auftrag

        return Auftrag(anlage_id=anlage_id, sensor_key=self.sensor_key, falsch_seit=self.sprung, ab=self.rueckgang,
                       vorher=self.quelle, nachher=self.quelle, herkunft=HERKUNFT_NACHTRAG, erklaert=jetzt, stueck=True)


async def _sperre(db, anlage_id: int, key: str, vor: Optional[dict], ab: Optional[dict]) -> Optional[str]:
    """Die Sperren der Korrektur über ein Stück: verschiedene Quellen an den Rändern (A → X → C, Bauplan Nr. 96) und ein
    offener Korrektur-Lauf des Felds (wie die Werkbank und der Nachtrag, «Zu §13» Nr. 86)."""
    from backend.services.zuordnung_wechsel.nachtrag import quelle_text, satz_lauf_offen

    if not _gleiche_quelle(vor, ab):
        return SATZ_VERSCHIEDENE_QUELLEN.format(vorher=quelle_text(vor), nachher=quelle_text(ab))
    return await satz_lauf_offen(db, anlage_id, key)


async def lage_am_befund(db, anlage, key: str, sprung: datetime, rueckgang: datetime) -> Optional[StueckLage]:
    """Das Stück des Befunds ``zaehler_versatz`` (``None`` = die Erkennung findet es nicht oder das Feld prüft der Befund
    nicht, ``versatz.in_tagesansicht`` — die Route antwortet 404)."""
    from backend.core.zahlenformat import fmt_zahl
    from backend.services.zuordnung_wechsel.nachtrag import quelle_text

    from backend.models.investition import Investition
    from backend.services.daten_checker.datenquelle.versatz import in_tagesansicht

    invs = {str(i.id): i for i in (await db.execute(select(Investition).where(Investition.anlage_id == anlage.id))).scalars()}
    if not in_tagesansicht(invs, key):          # dieselben Felder wie der Befund (sonst wäre das Stück frei wählbar)
        return None
    lauf = await finde_lauf(db, anlage.id, key, sprung, rueckgang)
    if lauf is None:
        return None
    s, r = lauf.beginn.bis, lauf.ende.bis
    vor = await quelle_am_rand(db, anlage, key, lauf.beginn.von)
    ab = await quelle_am_rand(db, anlage, key, r)
    zeiten = dict(sprung=s.strftime("%d.%m.%Y %H:%M"), rueckgang=r.strftime("%d.%m.%Y %H:%M"), versatz=fmt_zahl(lauf.versatz_kwh, 1))
    satz = (SATZ_STUECK.format(**zeiten, quelle=quelle_text(vor)) if _gleiche_quelle(vor, ab)
            else SATZ_STUECK_ZWEI_QUELLEN.format(**zeiten, vorher=quelle_text(vor), nachher=quelle_text(ab)))
    la = StueckLage(key, s, r, satz, quelle=vor)
    la.korrektur_nicht = await _sperre(db, anlage.id, key, vor, ab)
    return la


# ── Rest fremder Stände vor «Falsch seit» (Sensorwechsel U3 a, Rechenweg G8) ───


#: Was die Prüfung nennt, wenn «Falsch seit» auf den früheren Schritt vorbelegt ist (U3 a, G8).
SATZ_REST_VORGABE = ("Die gespeicherten Zählerstände dieses Felds springen schon am {zeit} Uhr um {betrag} kWh {richtung} — "
                     "etwa so weit, wie sie am Ende zurückspringen. «Falsch seit» ist deshalb auf {zeit} Uhr vorbelegt; sonst "
                     "blieben die Stände ab dort stehen.")


async def rest_vor(db, anlage_id: int, key: str, falsch_seit: datetime, ende: datetime):
    """Der Schritt, mit dem die fremden Stände schon vor ``falsch_seit`` beginnen (``core/berechnungen/zaehler_versatz.rest_schritt``
    über die Reihe der Erkennung, ``versatz.lade_reihe``) — ``None`` = keiner. Eine Stelle für die Vorgabe «Falsch seit»
    (``nachtrag.lage``) und die Lage «Rest» am Versatz-Befund (``daten_checker/datenquelle/versatz.py``)."""
    from backend.core.berechnungen.zaehler_versatz import rest_schritt
    from backend.services.daten_checker.datenquelle.versatz import lade_reihe

    return rest_schritt(await lade_reihe(db, anlage_id, key), falsch_seit, ende)


def satz_rest_vorgabe(schritt) -> str:
    from backend.core.zahlenformat import fmt_zahl

    return SATZ_REST_VORGABE.format(zeit=schritt.bis.strftime("%d.%m.%Y %H:%M"), betrag=fmt_zahl(abs(schritt.delta_kwh), 1),
                                    richtung="nach oben" if schritt.delta_kwh > 0 else "nach unten")


# ── Tage, die eine Lücke trifft (Vorschau) ───────────────────────────────────


async def tage_der_luecke(db, anlage, key: str, von: datetime, bis: datetime) -> tuple[list[date], list[date]]:
    """Die Tage, deren Tagesfenster (``kanal/feld_leser.tagesfenster_am_tag`` — dasselbe wie die Tagesansicht; ein Bestandstag
    rückwärts beginnt um 23:00 des Vortags) in der ungemessenen Zeit liegt (dort kein Wert), und die, die sie nur teilweise
    trifft (Rand-Tage: nur der Teil außerhalb). Ungemessen ist die Lücke ``[von, bis)`` samt der Zeit vom letzten Stand davor
    bis zu ihr und von ihrem Ende bis zum ersten Stand danach — dort bildet kein Leser eine Differenz (Bauplan «Zu §14»
    Nr. 102, S7: ein Rückgang genau am Fensterende ⇒ der Tag hat keinen Wert)."""
    from backend.models.investition import Investition
    from backend.services.kanal.feld_leser import tagesfenster_am_tag

    davor, danach = await _rand_vor(db, anlage.id, key, von), await _rand_ab(db, anlage.id, key, bis)
    von = davor.zeitpunkt if davor is not None else von
    bis = danach.zeitpunkt if danach is not None else bis
    typ = None
    teile = key.split(":")
    if len(teile) == 3 and teile[0] == "inv" and teile[1].isdigit():
        typ = (await db.execute(select(Investition.typ).where(Investition.id == int(teile[1])))).scalar_one_or_none()
    ganz: list[date] = []
    rand: list[date] = []
    d = von.date() - timedelta(days=1)
    while d <= bis.date() + timedelta(days=1):
        a, b = await tagesfenster_am_tag(db, anlage.id, typ, d)
        if b > von and a < bis:
            (ganz if (a >= von and b <= bis) else rand).append(d)
        d += timedelta(days=1)
    return ganz, rand


async def tragtag_der_luecke(db, anlage, key: str, bis: datetime) -> Optional[date]:
    """Der Tag, dessen Tagesfenster (``kanal/feld_leser.tagesfenster_am_tag``, ``(a, b]``) den ersten Stand ab ``bis`` enthält —
    dort steht die Menge einer Zählerlücke (Bauplan «Zu §14» Nr. 119/120). Steht danach noch kein Stand (Dialog: die Zeit endet
    jetzt), zählt der erste, den eedc um ``bis`` schreiben wird (U1 U-5, Korrekturrunde U1-K S4 — wie ``_wie_zaehlerluecke``)."""
    from backend.models.investition import Investition
    from backend.services.kanal.feld_leser import tagesfenster_am_tag

    danach = await _rand_ab(db, anlage.id, key, bis) or Rand(bis, 0.0)
    typ = None
    teile = key.split(":")
    if len(teile) == 3 and teile[0] == "inv" and teile[1].isdigit():
        typ = (await db.execute(select(Investition.typ).where(Investition.id == int(teile[1])))).scalar_one_or_none()
    for d in (danach.zeitpunkt.date() - timedelta(days=1), danach.zeitpunkt.date(), danach.zeitpunkt.date() + timedelta(days=1)):
        a, b = await tagesfenster_am_tag(db, anlage.id, typ, d)
        if a < danach.zeitpunkt <= b:
            return d
    return None


def antwort(la: StueckLage, label: Optional[str], feld_id: Optional[str], korrektur: Optional[dict[str, Any]] = None
            ) -> dict[str, Any]:
    """Antwort der Prüf-Route am Befund — dieselben Felder wie ``nachtrag.antwort`` (derselbe Dialog), nur «Korrektur»."""
    from backend.models.zuordnung_wechsel import GRUND_KORREKTUR

    return {
        "wechsel_id": None, "sensor_key": la.sensor_key, "label": label, "feld_id": feld_id, "grund": None,
        "wechsel_satz": la.satz, "gruende": [] if la.korrektur_nicht else [GRUND_KORREKTUR],
        "korrektur_nicht": la.korrektur_nicht, "grund_erforderlich": la.korrektur_nicht is None, "verzeichnet": False,
        "erster_wert": None, "tage": 0, "stand_alt": None, "stand_neu": None,
        "vorgabe_falsch_seit": la.sprung.isoformat(), "stueck": {"sprung": la.sprung.isoformat(), "rueckgang": la.rueckgang.isoformat()},
        "korrektur": korrektur, "bleiben": None,
    }


__all__ = ["SATZ_NICHT_GEMELDET", "SATZ_REST_VORGABE", "SATZ_STUECK", "SATZ_STUECK_ZWEI_QUELLEN", "SATZ_VERSCHIEDENE_QUELLEN",
           "StueckLage", "antwort", "finde_lauf", "ist_fuellbar", "lage_am_befund", "quelle_am_rand", "rest_vor", "satz_rest_vorgabe",
           "tage_der_luecke", "tragtag_der_luecke"]
