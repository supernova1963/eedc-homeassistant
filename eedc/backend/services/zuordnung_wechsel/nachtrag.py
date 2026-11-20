"""«Grund nachtragen» an einem verzeichneten Wechsel (Sensorwechsel mit Grund, Bauplan B-7, Konzept S-6/S-10 a/c/d; Sitzung 4).

Ein Wechsel der wirksamen Quelle eines Zählers mit eigenen Werten, nach dem die Abfrage (B-2) gefragt hätte, steht ohne Grund
in ``zuordnung_wechsel`` — aus der Zeit vor der Abfrage (``altbestand``, ``wechsel`` aus Sitzung 1) oder weil der Anwender den
Grund erst später kennt. Der Befund «Zuordnung geändert, Grund fehlt» (``daten_checker/datenquelle/grund_fehlt.py``) führt
hierher; derselbe Dialog wie beim Wechsel (``SensorwechselDialog``) fragt nach dem Grund, Feld und Zeitpunkt sind vorbelegt.

**Wann** (``lage``): die Zeile ist nicht aufgehoben, ihr Grund ist leer oder «Fortsetzung», und ``abfrage.haette_gefragt``
sagt ja (die eine Prüf-Funktion, nicht nachgebaut). Grund ändern nur **Fortsetzung → Korrektur** (S-10 d) — eine Korrektur hat
Werte verworfen und lässt sich nicht zurücknehmen.

**Fortsetzung** (``trage_fortsetzung_ein``): eine neue Zeile ``herkunft = nachtrag``, ``grund = fortsetzung`` mit Zeitpunkt,
``ab_ts``, ``vorher`` und ``nachher`` der Zeile; die Zeile selbst wird aufgehoben (``aufgehoben_durch``). ``erklaert_ts`` bleibt
die Sekunde des Wechsels, nicht die des Nachtrags (E-1 der Sitzung: der MQTT-Stundenlauf teilt an ``erklaert_ts`` die Periode,
``kanal/naht.offene_naehte`` — mit der Sekunde des Nachtrags läge die Naht heute). Die Leser der Reihe überbrücken die Naht über
die Abschnitts-Regel (Sitzung 2). Im Kanal: gilt zur Stunde des Wechsels die Mitschrift (MQTT «Eigene Summe» oder der
Nachbau-Abschnitt vor der HA-Statistik), trägt ``kanal/naht.nachtrag_fortsetzung`` den Versatz an der ersten geschriebenen
Stunde nach (wie der Einstieg «Zähler getauscht», ``zaehler_getauscht._nachtrag_stunde``); ein Spiegel-Abschnitt folgt HAs
Summe, und ein Wechsel der Entität hat dort schon seine eigene Kanal-Quelle mit Versatz — nichts zu tun.

**Korrektur** (``korrektur_auftrag``): derselbe Dienst wie beim Wechsel (``korrektur.py``, Vorschau = Lauf), falsch in
``[falsch_seit, ab_ts)``, richtig ist ``nachher`` — für den **jüngsten** nicht aufgehobenen Wechsel der Quelle (ein «Zähler
getauscht», Korrektur- und Lücken-Zeilen sind keiner, ``spaetere_wechsel``), dessen ``nachher`` die heutige wirksame Quelle
ist. Seit Sitzung 4b-1 (Bauplan «Zu §14» Nr. 96, Nr. 101) zusätzlich am **Rückkehr-Wechsel** X → A eines Stücks A → X → A
(``stueck_des_wechsels``): falsch ist die Zeit **vor** diesem Wechsel, vom vorigen Wechsel A → X bis zu diesem, richtig A —
«Falsch seit» steht fest (``stueck.py``); nie die Zeit danach, und am ersten Wechsel A → X keine Korrektur über das Stück.
Bei verschiedenen Quellen (A → X → C) gibt es kein Stück; die Prüfung nennt den Grund.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Optional

from sqlalchemy import select

from backend.models.zuordnung_wechsel import GRUND_FORTSETZUNG, GRUND_KORREKTUR, HERKUNFT_NACHTRAG, ZuordnungWechsel
from backend.services.zuordnung_wechsel.abfrage import _gleich, haette_gefragt, volle_stunde

#: Wortlaute (Sitzung 4; gehen vor dem Commit an Gernot).
SATZ_WECHSEL = "Am {zeit} Uhr wechselte die Quelle von {vorher} zu {nachher}."
SATZ_KORREKTUR_NUR_JUENGSTER = ("«Bisherige Werte verwerfen» lässt sich hier nicht nachtragen: das geht am jüngsten "
                                "Wechsel dieses Felds, solange seine neue Quelle noch zugeordnet ist, und an einem Wechsel, mit "
                                "dem die Quelle zur vorigen zurückkehrte — dann gilt die Korrektur für die Zeit seit dem Wechsel "
                                "davor.")
SATZ_FALSCH_SEIT_NACH_WECHSEL = "«Falsch seit» muss vor dem Wechsel liegen ({zeit} Uhr)."
SATZ_NICHT_OFFEN = "Für diesen Wechsel ist kein Grund nachzutragen."
SATZ_KORREKTUR_ENDGUELTIG = "Eine Korrektur lässt sich nicht mehr ändern."
SATZ_GRUND_FEHLT = "Wähle, ob die bisherigen Werte bleiben oder verworfen werden."
SATZ_NUR_KORREKTUR = ("Für diesen Wechsel ist «Bisherige Werte bleiben» schon eingetragen; ändern lässt er sich nur zu "
                      "«Bisherige Werte verwerfen».")
#: Am versetzten Abschnitt (Befund ``zaehler_versatz``) gibt es nur «Korrektur» (Bauplan «Zu §14» Nr. 96).
SATZ_NUR_KORREKTUR_STUECK = "Für einen versetzten Abschnitt lässt sich nur «Bisherige Werte verwerfen» eintragen."
#: Offener Korrektur-Lauf des Felds («Zu §13» Nr. 86 — eigener Satz ohne den Werkbank-Knopf).
SATZ_LAUF_OFFEN = ("Für dieses Feld steht aus einer früheren Korrektur noch das Füllen aus Home Assistant aus — eedc holt es "
                   "jede Stunde von selbst nach. Eine weitere Korrektur lässt sich erst danach eintragen.")
#: Dasselbe, wenn der offene Lauf der eines Wechsels «bleiben» ist (U2 Lauf b, a2 E-2) — er ist keine Korrektur.
SATZ_LAUF_OFFEN_ANSETZEN = ("Für dieses Feld liest eedc nach dem Wechsel des Sensors noch Werte aus Home Assistant neu — eedc "
                            "holt das jede Stunde von selbst nach. Eine Korrektur lässt sich erst danach eintragen.")


async def satz_lauf_offen(db, anlage_id: int, sensor_key: str) -> Optional[str]:
    """Der Satz zu einem offenen Lauf des Felds (``korrektur_lauf.offener_lauf``) je nach seiner Art; ``None`` = keiner offen."""
    from backend.services.zuordnung_wechsel import korrektur_lauf

    lauf = await korrektur_lauf.offener_lauf(db, anlage_id, sensor_key)
    if lauf is None:
        return None
    ansetzen = korrektur_lauf.art(await korrektur_lauf.stand(db, lauf)) == korrektur_lauf.ART_ANSETZEN
    return SATZ_LAUF_OFFEN_ANSETZEN if ansetzen else SATZ_LAUF_OFFEN

QUELLE_UNBEKANNT = "einer unbekannten Quelle"


class NachtragAbgelehnt(ValueError):
    """Der Nachtrag ist so nicht möglich (die Route antwortet 422 mit dem Satz)."""


def quelle_text(q: Optional[dict]) -> str:
    """Eine wirksame Quelle in Anwender-Sprache (Entität, MQTT-Topic, «Keine»)."""
    if not isinstance(q, dict) or not q.get("art"):
        return QUELLE_UNBEKANNT
    if q["art"] == "ha":
        return q.get("entity_id") or "einem Home-Assistant-Sensor"
    if q["art"] == "keine":
        return "„Keine“"
    topic = q.get("topic")
    return f"MQTT ({topic})" if topic else "MQTT (Standard-Topic)"


def feld_id_aus_schluessel(sensor_key: str) -> Optional[str]:
    """``inv:2:ladung_kwh`` → ``inv_energy_2_ladung_kwh``; ``basis:einspeisung`` → ``basis_energy_einspeisung_kwh`` (die
    Umkehr von ``snapshot/keys._energy_field_id_to_sensor_key``, über dieselbe Übersetzung; ``None``, wenn sie nicht trifft)."""
    from backend.services.snapshot.keys import _energy_field_id_to_sensor_key, _sensor_key_to_mqtt_key

    mk = _sensor_key_to_mqtt_key(sensor_key)
    if not mk:
        return None
    if mk.startswith("inv/"):
        _, inv_id, feld = mk.split("/", 2)
        fid = f"inv_energy_{inv_id}_{feld}"
    else:
        fid = f"basis_energy_{mk}"
    return fid if _energy_field_id_to_sensor_key(fid) == sensor_key else None


@dataclass
class NachtragLage:
    row: ZuordnungWechsel
    gruende: list[str] = field(default_factory=list)
    #: Warum «Korrektur» nicht angeboten wird (``None`` = sie wird angeboten oder ist nach dem Grund ohnehin nicht dran).
    korrektur_nicht: Optional[str] = None
    erster_wert: Optional[datetime] = None
    tage: int = 0
    vorgabe_falsch_seit: Optional[datetime] = None
    #: «Korrektur im Nachhinein» am Rückkehr-Wechsel über das Stück A → X → A davor (``stueck_des_wechsels``, Bauplan «Zu §14»
    #: Nr. 96): ``(Sprung, Rückgang, Quelle davor und danach)`` — «Falsch seit» steht dann fest.
    stueck: Optional[tuple[datetime, datetime, dict]] = None
    #: U2 Lauf b (F10): was «bleiben» zwischen zwei HA-Sensoren tut (``bleiben.angaben``; ``bleiben_angaben``).
    bleiben: Optional[dict] = None
    #: U3 a (Rechenweg G8): «Falsch seit» ist auf den früheren Schritt fremder Stände vorbelegt — der Satz dazu.
    rest_satz: Optional[str] = None


async def _zeile(db, anlage_id: int, wechsel_id: int) -> Optional[ZuordnungWechsel]:
    return (await db.execute(select(ZuordnungWechsel).where(
        ZuordnungWechsel.id == wechsel_id, ZuordnungWechsel.anlage_id == anlage_id))).scalar_one_or_none()


async def offen(db, anlage_id: int, row) -> bool:
    """Ist für diese Zeile ein Grund nachzutragen (Befund «Grund fehlt»)? Nicht aufgehoben, Grund leer, B-2 hätte gefragt."""
    return row.aufgehoben_durch is None and row.grund is None and await haette_gefragt(db, anlage_id, row)


def ist_quellenwechsel(w) -> bool:
    """Ein Wechsel der Quelle im Sinn der Korrektur im Nachhinein: nicht aufgehoben, kein «Zähler getauscht» (``vorher =
    nachher``), keine Korrektur-Zeile (auch keine Lücken-Zeile, ``zeitpunkt.ist_luecken_zeile``) — Bauplan «Zu §14» Nr. 103."""
    return w.aufgehoben_durch is None and w.grund != GRUND_KORREKTUR and not _gleich(w.vorher, w.nachher)


async def _quellenwechsel(db, anlage_id: int, sensor_key: str) -> list:
    """Die Quellenwechsel des Schlüssels (``ist_quellenwechsel``), Reihenfolge ``ab_ts``, dann Zeilen-Nummer."""
    from backend.services.zuordnung_wechsel.zeitpunkt import lade_wechsel

    return sorted((w for w in (await lade_wechsel(db, anlage_id)).get(sensor_key, ()) if ist_quellenwechsel(w)),
                  key=lambda w: (w.ab_ts, w.id or 0))


async def korrektur_moeglich(db, anlage, row) -> bool:
    """Der jüngste Quellenwechsel des Schlüssels (``ist_quellenwechsel`` — ein späterer «Zähler getauscht», eine Korrektur
    oder eine Lücke zählt nicht, Bauplan «Zu §14» Nr. 103), und sein ``nachher`` ist die heutige wirksame Quelle."""
    from backend.services.zuordnung_wechsel.quelle import lade_wirksame_quellen, standard_quelle

    if any(w.ab_ts > row.ab_ts for w in await _quellenwechsel(db, anlage.id, row.sensor_key)):
        return False
    heute = (await lade_wirksame_quellen(db, anlage)).get(row.sensor_key) or standard_quelle(row.sensor_key)
    return _gleich(heute, row.nachher)


async def stueck_des_wechsels(db, anlage_id: int, row) -> Optional[tuple[datetime, datetime, dict]]:
    """Bauplan «Zu §14» Nr. 96, Nr. 101: ist ``row`` der **Rückkehr-Wechsel** X → A eines Stücks A → X → A (der vorige
    Quellenwechsel ging von A nach X), ist das Stück die Zeit **vor** ``row``: ``[A → X, X → A)``, richtig A (die Quelle nach
    diesem Wechsel, die zugleich vor dem vorigen galt). Nie die Zeit danach; am ersten Wechsel A → X gibt es kein Stück (der
    Grund-Text «Bisher war der falsche Sensor zugeordnet» meinte dort das Gegenteil). Ein «Zähler getauscht», Korrektur- und
    Lücken-Zeilen sind kein Wechsel der Quelle (``ist_quellenwechsel``); ein späterer Wechsel ändert am Stück nichts. Bei
    verschiedenen Quellen (A → X → C) gibt es kein Stück."""
    zeilen = await _quellenwechsel(db, anlage_id, row.sensor_key)
    i = next((k for k, w in enumerate(zeilen) if w.id == row.id), None)
    if i is None or i == 0:
        return None
    w, v = zeilen[i], zeilen[i - 1]
    if w.nachher and _gleich(v.nachher, w.vorher) and _gleich(v.vorher, w.nachher):
        return v.ab_ts, w.ab_ts, w.nachher
    return None


async def _vorgabe(db, anlage_id: int, row, kanal, erster: Optional[datetime]) -> Optional[datetime]:
    """Vorgabe «falsch seit»: Beginn der Quelle vor dem Wechsel — der Wechsel davor, der sie brachte, sonst der Beginn ihres
    Abschnitts im Kanal (nie früher als die Stunde vor dem ersten eigenen Wert — eine Quellzeile kann älter sein als jede
    Zeile, E-6 der Sitzung), sonst der erste eigene Wert (wie die Abfrage, ``abfrage._beginn_bisherige_quelle``, zum Zeitpunkt
    des Wechsels)."""
    from backend.services.kanal.angaben import beginn_quelle_vor
    from backend.services.zuordnung_wechsel.zeitpunkt import lade_wechsel

    davor = [w for w in (await lade_wechsel(db, anlage_id)).get(row.sensor_key, ())
             if w.aufgehoben_durch is None and w.ab_ts < row.ab_ts and row.vorher is not None
             and _gleich(w.nachher, row.vorher) and not _gleich(w.vorher, w.nachher)]
    if davor:
        return max(w.ab_ts for w in davor)
    if kanal is not None:
        stunde = int(row.erklaert_ts.replace(minute=0, second=0, microsecond=0).timestamp())
        beginn = await beginn_quelle_vor(db, kanal.id, stunde)
        if beginn is not None:
            frueheste = None if erster is None else erster.replace(minute=0, second=0, microsecond=0) - timedelta(hours=1)
            return beginn if frueheste is None or beginn >= frueheste else frueheste
    return None if erster is None else erster.replace(minute=0, second=0, microsecond=0)


async def lage(db, anlage, wechsel_id: int) -> Optional[NachtragLage]:
    """Was an dieser Zeile nachzutragen ist (lesend); ``None`` = keine Zeile dieser Anlage, oder eine Lücken-Zeile (kein
    Wechsel, ``zeitpunkt.ist_luecken_zeile`` — die Routen antworten 404, Bauplan «Zu §14» Nr. 105, F7 c)."""
    from backend.services.kanal.angaben import angaben, kanal_des_schluessels
    from backend.services.zuordnung_wechsel.abfrage import _reihe
    from backend.services.zuordnung_wechsel.zeitpunkt import ist_luecken_zeile

    row = await _zeile(db, anlage.id, wechsel_id)
    if row is None or ist_luecken_zeile(row):
        return None
    la = NachtragLage(row)
    if row.aufgehoben_durch is not None or row.grund == GRUND_KORREKTUR or not await haette_gefragt(db, anlage.id, row):
        return la
    if row.grund is None:
        la.gruende.append(GRUND_FORTSETZUNG)
    moeglich = await korrektur_moeglich(db, anlage, row)
    if not moeglich:
        la.stueck = await stueck_des_wechsels(db, anlage.id, row)
    if not (moeglich or la.stueck):
        la.korrektur_nicht = SATZ_KORREKTUR_NUR_JUENGSTER
    elif (offen_satz := await satz_lauf_offen(db, anlage.id, row.sensor_key)) is not None:
        # Bauplan §13 Nr. 73: wie die Werkbank (§11 Nr. 46) — ein offener Korrektur-Lauf desselben Felds wird zuerst
        # nachgeholt; Prüfung und Schreiben nennen denselben Satz (eigener Satz ohne Werkbank-Knopf, «Zu §13» Nr. 86).
        la.korrektur_nicht = offen_satz
    else:
        la.gruende.append(GRUND_KORREKTUR)
    kanal = await kanal_des_schluessels(db, anlage.id, row.sensor_key)
    la.erster_wert, la.tage = await _reihe(db, anlage.id, row.sensor_key)
    if la.erster_wert is None and kanal is not None:
        la.erster_wert, la.tage, _stand = await angaben(db, kanal)
    la.vorgabe_falsch_seit = la.stueck[0] if la.stueck else await _vorgabe(db, anlage.id, row, kanal, la.erster_wert)
    if GRUND_KORREKTUR in la.gruende and la.vorgabe_falsch_seit is not None:
        await _rest_fremder_staende(db, anlage.id, la)
    return la


async def _rest_fremder_staende(db, anlage_id: int, la: NachtragLage) -> None:
    """Sensorwechsel U3 a (Rechenweg G8): tragen die gespeicherten Zählerstände die Stände des anderen Sensors schon vor der
    Vorgabe «Falsch seit» (ein passender Schritt in den 24 Stunden davor, ``stueck.rest_vor``), beginnt die Vorgabe dort —
    beim Stück am Rückkehr-Wechsel ebenso dessen Beginn — und die Prüfung nennt es (``rest_satz``)."""
    from backend.services.zuordnung_wechsel.stueck import rest_vor, satz_rest_vorgabe

    ende = la.stueck[1] if la.stueck else la.row.ab_ts
    rest = await rest_vor(db, anlage_id, la.row.sensor_key, la.vorgabe_falsch_seit, ende)
    if rest is None:
        return
    la.vorgabe_falsch_seit = volle_stunde(rest.bis)
    if la.stueck:
        la.stueck = (la.vorgabe_falsch_seit, la.stueck[1], la.stueck[2])
    la.rest_satz = satz_rest_vorgabe(rest)


async def bleiben_angaben(db, la: NachtragLage, zaehlt_ab: Optional[datetime] = None,
                          jetzt: Optional[datetime] = None) -> Optional[dict[str, Any]]:
    """Die Angaben zu «bleiben» am verzeichneten Wechsel (F10; Vorgabe für den Schnitt ist die Stunde des Wechsels) — nur,
    wenn «bleiben» nachzutragen ist und der Wechsel zwischen zwei HA-Sensoren liegt."""
    from backend.services.zuordnung_wechsel import bleiben

    r = la.row
    if GRUND_FORTSETZUNG not in la.gruende:
        if zaehlt_ab is not None:
            raise bleiben.ZaehltAbAbgelehnt(bleiben.SATZ_NUR_BLEIBEN)
        return None
    if zaehlt_ab is not None and not bleiben.ist_ha_zu_ha(r.vorher, r.nachher):
        raise bleiben.ZaehltAbAbgelehnt(bleiben.SATZ_NUR_HA)
    return await bleiben.angaben(db, r.anlage_id, r.sensor_key, r.vorher, r.nachher, ab_ts=r.ab_ts, erklaert_ts=r.erklaert_ts,
                                 jetzt=jetzt or datetime.now().replace(microsecond=0), zaehlt_ab=zaehlt_ab)


def wechsel_satz(row) -> str:
    return SATZ_WECHSEL.format(zeit=row.erklaert_ts.strftime("%d.%m.%Y %H:%M"), vorher=quelle_text(row.vorher),
                               nachher=quelle_text(row.nachher))


def korrektur_auftrag(row, falsch_seit: Optional[datetime], jetzt: datetime,
                      stueck: Optional[tuple[datetime, datetime, dict]] = None):
    """Der Auftrag des Korrektur-Dienstes für einen nachgetragenen Grund «Korrektur»: falsch in ``[falsch_seit, ab_ts)``,
    richtig ist ``nachher`` (die heutige Quelle, ``korrektur_moeglich``). Mit ``stueck`` (am Rückkehr-Wechsel X → A eines
    Stücks A → X → A) das Stück selbst: falsch in ``[A → X, X → A)``, richtig A; ``falsch_seit`` zählt nicht."""
    from backend.services.zuordnung_wechsel.korrektur import Auftrag

    if stueck is not None:
        s, r, quelle = stueck
        return Auftrag(anlage_id=row.anlage_id, sensor_key=row.sensor_key, falsch_seit=s, ab=r, vorher=quelle,
                       nachher=quelle, herkunft=HERKUNFT_NACHTRAG, erklaert=jetzt, stueck=True)
    f = volle_stunde(falsch_seit)
    if f >= row.ab_ts:
        raise NachtragAbgelehnt(SATZ_FALSCH_SEIT_NACH_WECHSEL.format(zeit=row.ab_ts.strftime("%d.%m.%Y %H:%M")))
    return Auftrag(anlage_id=row.anlage_id, sensor_key=row.sensor_key, falsch_seit=f, ab=row.ab_ts, vorher=row.vorher,
                   nachher=row.nachher, herkunft=HERKUNFT_NACHTRAG, erklaert=jetzt)


def pruefe_grund(la: NachtragLage, grund: Optional[str]) -> None:
    """Ist ``grund`` für diese Lage zulässig? Sonst ``NachtragAbgelehnt`` mit Satz."""
    if not la.gruende:
        if grund == GRUND_KORREKTUR and la.korrektur_nicht:
            raise NachtragAbgelehnt(la.korrektur_nicht)
        raise NachtragAbgelehnt(SATZ_KORREKTUR_ENDGUELTIG if la.row.grund == GRUND_KORREKTUR else SATZ_NICHT_OFFEN)
    if grund is None:
        raise NachtragAbgelehnt(SATZ_GRUND_FEHLT)
    if grund not in la.gruende:
        if grund == GRUND_KORREKTUR and la.korrektur_nicht:
            raise NachtragAbgelehnt(la.korrektur_nicht)
        raise NachtragAbgelehnt(SATZ_NUR_KORREKTUR)


async def trage_fortsetzung_ein(db, anlage, row, zaehlt_ab: Optional[datetime] = None,
                                jetzt: Optional[datetime] = None) -> ZuordnungWechsel:
    """Fortsetzung nachtragen (in der Sitzung des Aufrufers, kein Commit). Ein Nachtrag im Kanal, den er nicht tragen kann,
    wirft ``ValueError`` (die Route antwortet 422 und rollt zurück); ebenso ein «Der neue Sensor zählt ab», das eedc nicht
    annimmt (``bleiben.setze_zaehlt_ab``, U2 Lauf b F10)."""
    from backend.services.zuordnung_wechsel.bleiben import SATZ_NUR_HA, ZaehltAbAbgelehnt, setze_zaehlt_ab
    from backend.services.kanal import merken
    from backend.services.kanal.angaben import kanal_des_schluessels
    from backend.services.kanal.naht import nachtrag_fortsetzung
    from backend.models.zuordnung_wechsel import ANSATZ_OFFEN
    from backend.services.zuordnung_wechsel.ansatz import wird_angesetzt
    from backend.services.zuordnung_wechsel.zaehler_getauscht import _nachtrag_stunde, naht_stunde
    from backend.services.zuordnung_wechsel.zeitpunkt import merke_neu, rand_versatz, vergiss

    neu = ZuordnungWechsel(anlage_id=row.anlage_id, sensor_key=row.sensor_key, erklaert_ts=row.erklaert_ts, ab_ts=row.ab_ts,
                           vorher=row.vorher, nachher=row.nachher, grund=GRUND_FORTSETZUNG, herkunft=HERKUNFT_NACHTRAG)
    if wird_angesetzt(neu):                     # U2 a2 (F10): «bleiben» zwischen zwei HA-Sensoren — nach dem Commit ansetzen
        neu.ansatz = ANSATZ_OFFEN
        if zaehlt_ab is not None:
            await setze_zaehlt_ab(db, neu, zaehlt_ab, jetzt=jetzt or datetime.now().replace(microsecond=0))
    elif zaehlt_ab is not None:
        raise ZaehltAbAbgelehnt(SATZ_NUR_HA)
    db.add(neu)
    await db.flush()
    row.aufgehoben_durch = neu.id
    await db.flush()
    vergiss(db, anlage.id)
    merke_neu(db, neu)
    kanal = await kanal_des_schluessels(db, anlage.id, row.sensor_key)
    nachtrag = await _nachtrag_stunde(db, kanal, await naht_stunde(db, kanal, row.erklaert_ts))
    if nachtrag is not None:
        await nachtrag_fortsetzung(db, kanal.id, nachtrag, rand_versatz(neu))       # U2 a1: ohne Rand-Stände None
    merken.invalidiere(anlage.id, db=db)
    return neu


def antwort(la: NachtragLage, label: Optional[str], korrektur: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    """Antwort der Prüf-Route — dieselben Felder wie ``…/quelle/pruefen`` (der Dialog ist derselbe), dazu der Wechsel."""
    r = la.row
    return {
        "wechsel_id": r.id, "sensor_key": r.sensor_key, "label": label, "feld_id": feld_id_aus_schluessel(r.sensor_key),
        "grund": r.grund, "wechsel_satz": wechsel_satz(r) + (f" {la.rest_satz}" if la.rest_satz else ""),
        "gruende": la.gruende, "korrektur_nicht": la.korrektur_nicht,
        "grund_erforderlich": bool(la.gruende), "verzeichnet": True,
        "erster_wert": None if la.erster_wert is None else la.erster_wert.replace(microsecond=0).isoformat(),
        "tage": la.tage, "stand_alt": None, "stand_neu": None,
        "vorgabe_falsch_seit": None if la.vorgabe_falsch_seit is None else la.vorgabe_falsch_seit.isoformat(),
        "stueck": None if la.stueck is None else {"sprung": la.stueck[0].isoformat(), "rueckgang": la.stueck[1].isoformat()},
        "korrektur": korrektur, "bleiben": la.bleiben,
    }
