"""Einstieg «Zähler getauscht (gleiche Quelle)» (Sensorwechsel mit Grund, Bauplan B-2 letzter Satz, G-1, §9 Nr. 26, §11
Nr. 44/45/49; Sitzung 3b und Korrekturrunde 3b-K).

Der Anwender sagt: die Quelle bleibt dieselbe, aber der Zähler dahinter wurde getauscht — sein Stand springt. Was eedc dann tut,
hängt an der **Quelle des Kanals zur Stunde des Tauschs** (Bauplan §11 Nr. 44 — nicht an der jüngsten: wer von Home Assistant auf
MQTT gewechselt hat und einen früheren Tausch meldet, trifft die Spiegel-Zeit):

* **Spiegel aus Home Assistant** (``home_assistant``): der Kanal spiegelt HAs Summe wörtlich; die Tagesansicht liest ihn
  (Feld-Auskunft «Kanal vor Reihe», Sitzung 2). Eine hier verzeichnete Fortsetzung wirkte nur auf die Leser der Reihe und
  machte Tagesansicht und Reihe uneins (gemessen §9 Nr. 26: 2 024,0 ↔ 23,0). eedc verzeichnet deshalb **nichts** und nennt den
  Weg in Home Assistant («Wert anpassen»). Das gilt auch für einen **früheren** Spiegel-Abschnitt eines heute anders
  zugeordneten Felds: der Konsistenzlauf gleicht jeden nicht verworfenen Spiegel-Abschnitt des Kanals gegen HA ab
  (``nachfuellen.abschnitte`` → ``konsistenz.konsistenz_anlage``) und übernimmt die berichtigte Statistik dort ebenso.
  Hat der Kanal noch keine Zeile, entscheidet der Katalog: führt er eine Kanal-Art für ein HA-Feld, spiegelt der nächste
  Stundenlauf HAs Geschichte.
* **MQTT «Eigene Summe»** (Mitschrift zur Stunde) **und die Zeit vor dem Kanal** (dort lesen die Leser die Reihe)
  (``fortsetzung``): eine Wechsel-Zeile mit Grund ``fortsetzung`` (``vorher`` = ``nachher`` = die wirksame Quelle,
  ``erklaert_ts`` = Zeitpunkt des Tauschs, ``ab_ts`` die volle Stunde danach) — die Leser der Reihe rechnen nicht über sie
  hinweg (``core/berechnungen/zaehler_naht.py``), der MQTT-Stundenlauf teilt dort die Periode (``kanal/naht.offene_naehte``);
  hat er die Stunde des Tauschs schon geschrieben, trägt ``kanal/naht.nachtrag_fortsetzung`` den Versatz nach (die Stunde
  zählt danach keinen Zuwachs — benannte Grenze B-3 «bis 1 h»; die Vorschau nennt, was sie bisher zählt, §11 Nr. 49).
* **Verworfene Zeit** (``nicht_moeglich``): zur Stunde gilt eine bei einer Korrektur verworfene Quelle — dort führt der Kanal
  keine Werte, nichts ist zu überbrücken (ebenso eine Quelle, die weder Spiegel noch Mitschrift ist).
* **Vor dem ersten eigenen Wert** (``vor_erstem_wert``, §11 Nr. 45): kein Stand davor, kein Sprung — nicht eingetragen, die
  Antwort nennt den ersten Wert. Ohne eigene Werte bzw. ohne Quelle gibt es ebenfalls nichts zu überbrücken.

Zweimal dasselbe ist einmal: eine Fortsetzungs-Zeile mit gleichem ``ab_ts`` wird nicht doppelt angelegt; der Nachtrag ist
idempotent (Sitzung 2, §9 Nr. 25).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import func, select

from backend.models.zuordnung_wechsel import GRUND_FORTSETZUNG, HERKUNFT_WECHSEL, ZuordnungWechsel
from backend.services.zuordnung_wechsel.quelle import ART_HA, ART_KEINE, hat_eigene_werte, lade_wirksame_quellen, standard_quelle
from backend.services.zuordnung_wechsel.zeitpunkt import ab_ts_aus, lade_wechsel, merke_neu

WEG_HOME_ASSISTANT = "home_assistant"
WEG_FORTSETZUNG = "fortsetzung"
WEG_OHNE_WERTE = "ohne_werte"
WEG_KEINE_QUELLE = "keine_quelle"
WEG_VOR_ERSTEM_WERT = "vor_erstem_wert"
WEG_NICHT_MOEGLICH = "nicht_moeglich"

#: Wortlaute (Sitzung 3b, Korrekturrunde 3b-K; Gernot liest sie vor dem Commit).
SATZ_HA = ("Dieser Zähler kommt aus Home Assistant, und eedc übernimmt seine Summe so, wie Home Assistant sie führt. Einen "
           "Sprung beim Tausch berichtigst du dort: unter Entwicklerwerkzeuge → Statistik den Sensor suchen, beim Symbol "
           "„Wert anpassen“ die Stunde des Tauschs wählen und den Zuwachs auf die echte Menge setzen. eedc übernimmt die "
           "berichtigte Statistik beim nächtlichen Abgleich; hier wird nichts eingetragen.")
SATZ_FORTSETZUNG = ("eedc überbrückt den Tausch am {zeit}: der Unterschied zwischen altem und neuem Zählerstand zählt nicht "
                    "als Menge. Die Werte vor und nach dem Tausch bleiben; wo eedc aus den gespeicherten Zählerständen rechnet, "
                    "zählt die Stunde des Tauschs keinen Zuwachs.")
SATZ_NACHTRAG = ("Die Stunde ab {stunde} Uhr ist schon gespeichert; sie zählt danach keinen Zuwachs — auch nicht, was in "
                 "dieser Stunde vor dem Tausch verbraucht wurde.")
SATZ_NACHTRAG_BISHER = "Bisher zählt sie {zuwachs} {einheit}."
SATZ_OHNE_WERTE = "Dieses Feld hat noch keine eigenen Werte — es gibt keinen Sprung zu überbrücken."
SATZ_KEINE_QUELLE = "Dieses Feld hat keine Quelle — ordne zuerst eine zu."
SATZ_SCHON = "Dieser Tausch ist schon eingetragen."
SATZ_VOR_ERSTEM_WERT = ("Dieses Feld hat erst ab {zeit} Uhr eigene Werte — vor dem ersten Wert gibt es keinen Sprung zu "
                        "überbrücken; hier wird nichts eingetragen.")
SATZ_NICHT_MOEGLICH = ("Für die Zeit des Tauschs ({zeit}) kann eedc hier nichts eintragen: für diese Zeit hat eedc keine Werte "
                       "dieses Zählers, die sich überbrücken lassen (etwa weil eine Korrektur sie verworfen hat).")


@dataclass
class Lage:
    sensor_key: Optional[str]
    weg: str
    quelle: Optional[dict] = None
    getauscht_am: Optional[datetime] = None
    kanal_id: Optional[int] = None
    #: Die schon geschriebene Stunde des MQTT-Kanals, die den Sprung trägt (``None`` = der Stundenlauf teilt dort selbst).
    nachtrag_ts: Optional[int] = None
    schon: bool = False
    #: Erster eigener Wert (Reihe oder Kanal) — für ``vor_erstem_wert``.
    erster_wert: Optional[datetime] = None
    #: Was die Stunde ``nachtrag_ts`` bisher zählt (Kanal-Leser) und die Einheit des Kanals.
    zuwachs: Optional[float] = None
    einheit: Optional[str] = None


def _zeit(dt: Optional[datetime]) -> str:
    return dt.strftime("%d.%m.%Y %H:%M") if dt is not None else ""


async def _katalog_spiegelt(db, key: str) -> bool:
    """Noch kein Kanal: spiegelt der nächste Stundenlauf diesen Zähler aus Home Assistant (der Katalog führt eine Art)?"""
    from backend.models.investition import Investition
    from backend.services.kanal.katalog import zaehler_art

    typ = None
    if key.startswith("inv:"):
        inv = await db.get(Investition, int(key.split(":")[1]))
        typ = inv.typ if inv is not None else None
    return zaehler_art(key, typ) is not None


async def _erster_wert(db, anlage_id: int, key: str, kanal) -> Optional[datetime]:
    """Der früheste eigene Wert: erster Zählerstand der Reihe oder erste Kanalzeile (ohne Stände — kein Reihen-Leser)."""
    from backend.models.sensor_snapshot import SensorSnapshot
    from backend.services.kanal.angaben import erste_zeile

    reihe = (await db.execute(select(func.min(SensorSnapshot.zeitpunkt)).where(
        SensorSnapshot.anlage_id == anlage_id, SensorSnapshot.sensor_key == key))).scalar_one()
    k = await erste_zeile(db, kanal.id) if kanal is not None else None
    return min((x for x in (reihe, k) if x is not None), default=None)


async def _weg(db, key: str, q: dict, kanal, stunde: int) -> str:
    """Der Weg nach der Quelle des Kanals zur Stunde des Tauschs (Bauplan §11 Nr. 44)."""
    from backend.models.kanal import FAMILIE_MITSCHRIFT, FAMILIE_SPIEGEL
    from backend.services.kanal.angaben import quelle_zur_stunde

    if kanal is None:
        return WEG_HOME_ASSISTANT if q.get("art") == ART_HA and await _katalog_spiegelt(db, key) else WEG_FORTSETZUNG
    kq = await quelle_zur_stunde(db, kanal.id, stunde)
    if kq is None:
        return WEG_FORTSETZUNG                  # vor dem Kanal: dort lesen die Leser die Reihe
    if kq.verworfen_ts is not None:
        return WEG_NICHT_MOEGLICH
    if kq.familie == FAMILIE_SPIEGEL:
        return WEG_HOME_ASSISTANT
    return WEG_FORTSETZUNG if kq.familie == FAMILIE_MITSCHRIFT else WEG_NICHT_MOEGLICH


async def _nachtrag_stunde(db, kanal, stunde: int) -> Optional[int]:
    """Die erste schon geschriebene Stunde ab der Stunde des Tauschs, wenn dort die Mitschrift (MQTT) gilt — nur sie trägt
    den Nachtrag (``kanal/naht.nachtrag_fortsetzung``)."""
    from backend.models.kanal import FAMILIE_MITSCHRIFT
    from backend.services.kanal.angaben import erste_zeile_ab, quelle_zur_stunde

    if kanal is None:
        return None
    kq = await quelle_zur_stunde(db, kanal.id, stunde)
    if kq is None or kq.familie != FAMILIE_MITSCHRIFT:
        return None
    ts = await erste_zeile_ab(db, kanal.id, stunde)
    if ts is None:
        return None
    dort = await quelle_zur_stunde(db, kanal.id, ts)
    return ts if dort is not None and dort.familie == FAMILIE_MITSCHRIFT and dort.verworfen_ts is None else None


async def lage(db, anlage, sensor_key: Optional[str], getauscht_am: datetime) -> Lage:
    """Welcher Weg gilt für dieses Feld zu diesem Zeitpunkt (lesend)."""
    from backend.services.kanal.angaben import kanal_des_schluessels, zuwachs_der_stunde

    if sensor_key is None or not await hat_eigene_werte(db, anlage.id, sensor_key):
        return Lage(sensor_key, WEG_OHNE_WERTE)
    q = (await lade_wirksame_quellen(db, anlage)).get(sensor_key) or standard_quelle(sensor_key)
    if q.get("art") == ART_KEINE:
        return Lage(sensor_key, WEG_KEINE_QUELLE, q)
    kanal = await kanal_des_schluessels(db, anlage.id, sensor_key)
    ab = ab_ts_aus(getauscht_am)
    erster = await _erster_wert(db, anlage.id, sensor_key, kanal)
    if erster is None or erster >= ab:
        return Lage(sensor_key, WEG_VOR_ERSTEM_WERT, q, getauscht_am, erster_wert=erster)
    stunde = int(getauscht_am.replace(minute=0, second=0, microsecond=0).timestamp())
    weg = await _weg(db, sensor_key, q, kanal, stunde)
    if weg != WEG_FORTSETZUNG:
        return Lage(sensor_key, weg, q, getauscht_am)
    schon = any(w.grund == GRUND_FORTSETZUNG and w.aufgehoben_durch is None and w.ab_ts == ab
                for w in (await lade_wechsel(db, anlage.id)).get(sensor_key, ()))
    nachtrag = await _nachtrag_stunde(db, kanal, stunde)
    zuwachs = await zuwachs_der_stunde(db, kanal, nachtrag) if nachtrag is not None else None
    return Lage(sensor_key, WEG_FORTSETZUNG, q, getauscht_am, kanal.id if kanal is not None else None, nachtrag, schon,
                zuwachs=zuwachs, einheit=kanal.einheit if kanal is not None else None)


def _saetze_fortsetzung(la: Lage) -> list[str]:
    from backend.core.zahlenformat import fmt_zahl

    s = [SATZ_FORTSETZUNG.format(zeit=_zeit(la.getauscht_am))]
    if la.nachtrag_ts is not None:
        s.append(SATZ_NACHTRAG.format(stunde=_zeit(datetime.fromtimestamp(la.nachtrag_ts))))
        if la.zuwachs is not None:
            s.append(SATZ_NACHTRAG_BISHER.format(zuwachs=fmt_zahl(la.zuwachs, 2), einheit=la.einheit or "kWh"))
    return s


def saetze(la: Lage) -> list[str]:
    feste = {WEG_HOME_ASSISTANT: SATZ_HA, WEG_OHNE_WERTE: SATZ_OHNE_WERTE, WEG_KEINE_QUELLE: SATZ_KEINE_QUELLE}
    if la.weg in feste:
        return [feste[la.weg]]
    if la.weg == WEG_VOR_ERSTEM_WERT:
        return [SATZ_VOR_ERSTEM_WERT.format(zeit=_zeit(la.erster_wert))]
    if la.weg == WEG_NICHT_MOEGLICH:
        return [satz_nicht_moeglich(la)]
    return [SATZ_SCHON] if la.schon else _saetze_fortsetzung(la)


def satz_nicht_moeglich(la: Lage) -> str:
    return SATZ_NICHT_MOEGLICH.format(zeit=_zeit(la.getauscht_am))


def antwort(la: Lage) -> dict[str, Any]:
    return {"weg": la.weg, "sensor_key": la.sensor_key, "saetze": saetze(la),
            "eintragen": la.weg == WEG_FORTSETZUNG and not la.schon,
            "getauscht_am": la.getauscht_am.isoformat() if la.getauscht_am else None}


async def trage_ein(db, anlage, la: Lage) -> Optional[ZuordnungWechsel]:
    """Die Fortsetzung eintragen (in der Sitzung des Aufrufers, kein Commit); nur für den Weg ``fortsetzung``. Ein Nachtrag,
    den der Kanal nicht tragen kann, wirft ``ValueError`` (die Route antwortet 422 und rollt zurück)."""
    from backend.services.kanal import merken
    from backend.services.kanal.naht import nachtrag_fortsetzung

    if la.weg != WEG_FORTSETZUNG or la.schon:
        return None
    t = la.getauscht_am.replace(microsecond=0)
    row = ZuordnungWechsel(anlage_id=anlage.id, sensor_key=la.sensor_key, erklaert_ts=t, ab_ts=ab_ts_aus(t),
                           vorher=la.quelle, nachher=la.quelle, grund=GRUND_FORTSETZUNG, herkunft=HERKUNFT_WECHSEL)
    db.add(row)
    await db.flush()
    merke_neu(db, row)
    if la.nachtrag_ts is not None:
        await nachtrag_fortsetzung(db, la.kanal_id, la.nachtrag_ts)
    merken.invalidiere(anlage.id, db=db)
    return row
