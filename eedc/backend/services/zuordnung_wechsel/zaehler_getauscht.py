"""Einstieg «Zähler getauscht (gleiche Quelle)» (Sensorwechsel mit Grund, Bauplan B-2 letzter Satz, G-1, §9 Nr. 26, §11
Nr. 44/45/49; Sitzung 3b und Korrekturrunde 3b-K).

Der Anwender sagt: die Quelle bleibt dieselbe, aber der Zähler dahinter wurde getauscht — sein Stand springt. Was eedc dann tut,
hängt an der **Quelle des Kanals zur Stunde des Tauschs** (Bauplan §11 Nr. 44 — nicht an der jüngsten: wer von Home Assistant auf
MQTT gewechselt hat und einen früheren Tausch meldet, trifft die Spiegel-Zeit):

* **Spiegel aus Home Assistant** (``home_assistant``): der Kanal spiegelt HAs Summe wörtlich; die Tagesansicht liest ihn
  (Feld-Auskunft «Kanal vor Reihe», Sitzung 2). Eine hier verzeichnete Fortsetzung wirkte nur auf die Leser der Reihe und
  machte Tagesansicht und Reihe uneins (gemessen §9 Nr. 26: 2 024,0 ↔ 23,0). eedc verzeichnet deshalb **nichts** und nennt den
  Weg in Home Assistant («Summe anpassen», Lab-K H1). Das gilt auch für einen **früheren** Spiegel-Abschnitt eines heute anders
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

**Sensorwechsel U2 Lauf c (Rechenweg F13, Entscheid E2, Bauplan Nr. 139):** der Weg hängt an der **wirksamen Quelle zur Zeit
des Tauschs** (``zeitpunkt.quelle_am``; ohne späteren Wechsel die heutige). Führt zu der Zeit Home Assistant den Zähler und
spiegelt eedc ihn (Spiegel-Abschnitt; noch ohne Kanal: der Katalog führt eine Art), trägt eedc nie etwas ein — eine Quelle aus
Home Assistant wird nicht überbrückt (Grundregel «Quellentreue»). Ein **Stand-Zähler** (Gas, Wasser, Öl; Kanal-Art ``stand``)
bekommt einen eigenen Satz (``SATZ_HA_STAND``): eedc liest dort den Stand, «Summe anpassen» ändert in HA nur die Summe und wirkte
nicht; genannt werden die zwei Wege nach E2 — in Home Assistant einen neuen Sensor oder Helfer für den neuen Zähler anlegen und
ihn mit «Bisherige Werte bleiben» zuordnen, oder den neuen Zähler als eigenes Gerät führen (Handbuch Einstellungen §3.4a). Für
MQTT und für Zeiten ohne Spiegel (vor dem Kanal, Nachbau-Abschnitt, Feld ohne Kanal-Art) bleibt alles wie zuvor (Auftrag Lauf c;
die Abweichung vom Rechenweg «Übersehen Nr. 6» steht im Bericht).

**Sensorwechsel U3-K (B1):** trägt die Stunde mehrere Höhenwechsel, sind die Rand-Stände der letzte Stand vor dem ersten und der
erste nach dem letzten (``rohstand_rand.sprung_der_stunde``); ergäbe der Eintrag trotzdem eine negative Menge der Stunde, lehnt
die Prüfung ab (``negative_menge``) — eine negative Menge wird nie geschrieben.

**Sensorwechsel U3 Lauf b (Rechenweg G5, Regel «Rohstand ist die Quelle»):** gilt zur Zeit des Tauschs MQTT, sucht eedc in
den Rohständen der Stunde (``rohstand.sprung_um``) den Schritt, an dem der Zählerstand die Höhe wechselt, und trägt den Tausch
genau dort ein — mit dem letzten Rohstand davor und dem ersten danach als Rand-Ständen (``ansatz = schnitt``). Die Stunde des
Tauschs zählt dann, was in den Rohständen steht (Kanal: ``naht.nachtrag_fortsetzung`` mit ``rand``; Reihe: ``rand_versatz``),
statt keinen Zuwachs. Ist nach dem Zeitpunkt noch kein (anderer) Rohstand gespeichert, wird eingetragen und der Stundenlauf
setzt die Rand-Stände; ohne Rohstände (älter als 31 Tage) wie bisher.

**Bauplan Nr. 166 (Entscheid Gernot 20.11.2026): bei MQTT entscheidet der Anwender; die Erkennung zeigt, sie entscheidet
nicht.** Wechselt der Stand in der Stunde eindeutig die Höhe (R1), liegt der Eintrag dort. Sonst (R2) nimmt eedc den letzten
Stand vor der gewählten Zeit und den **nächsten Stand danach mit anderem Wert** (``rohstand.naechster_anderer_um``), rückt
«Getauscht am» dorthin und nennt beide Zeiten, beide Stände und die Menge, die nach dem Eintrag nicht zählt (``SATZ_SCHRITT``;
stand der Stand davor still, ``SATZ_SCHRITT_STILL``), dazu einen Hinweis: hebt sich der Schritt ab
(``rohstand.abgehoben_am``), ``SATZ_HINWEIS_UNKLAR``, sonst ``SATZ_HINWEIS_KEIN_SPRUNG``. Es gibt keine Ablehnung «kein Sprung
zu sehen» mehr (U3 b bis U3-K4); gesperrt bleiben nur eine negative Menge (``SATZ_NEGATIV``) und ein schon eingetragener Tausch
(``SATZ_SCHON``).

Zweimal dasselbe ist einmal: eine Fortsetzungs-Zeile mit gleichem ``ab_ts`` wird nicht doppelt angelegt; der Nachtrag ist
idempotent (Sitzung 2, §9 Nr. 25).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any, Optional

from sqlalchemy import func, select

from backend.models.zuordnung_wechsel import GRUND_FORTSETZUNG, HERKUNFT_WECHSEL, ZuordnungWechsel
from backend.services.zuordnung_wechsel.quelle import ART_HA, ART_KEINE, hat_eigene_werte, lade_wirksame_quellen, standard_quelle
from backend.services.zuordnung_wechsel.zeitpunkt import HEUTE, ab_ts_aus, lade_wechsel, merke_neu, quelle_am

WEG_HOME_ASSISTANT = "home_assistant"
WEG_FORTSETZUNG = "fortsetzung"
WEG_OHNE_WERTE = "ohne_werte"
WEG_KEINE_QUELLE = "keine_quelle"
WEG_VOR_ERSTEM_WERT = "vor_erstem_wert"
WEG_NICHT_MOEGLICH = "nicht_moeglich"
#: U3-K (B1): die Stunde des Tauschs zählte nach dem Eintrag eine negative Menge — nicht eingetragen.
WEG_NEGATIV = "negative_menge"

#: Wortlaute (Sitzung 3b, Korrekturrunde 3b-K; Gernot liest sie vor dem Commit).
SATZ_HA = ("Dieser Zähler kommt aus Home Assistant, und eedc übernimmt seine Summe so, wie Home Assistant sie führt. Einen "
           "Sprung beim Tausch berichtigst du dort: unter Einstellungen → Werkzeuge → Statistik (in älteren "
           "Home-Assistant-Versionen: Entwicklerwerkzeuge → Statistik) den Sensor suchen, beim Symbol „Summe anpassen“ "
           "unter „Zeitpunkt auswählen“ die Zeit des Tauschs wählen, bei „Neuer Wert“ die echte Menge eintragen und "
           "„Anpassen“ drücken. eedc übernimmt die "
           "berichtigte Statistik beim nächtlichen Abgleich; hier wird nichts eingetragen.")
#: Sensorwechsel U2 Lauf c (F13, E2): ein Stand-Zähler aus Home Assistant — eedc liest den Stand, «Summe anpassen» wirkt dort nicht.
SATZ_HA_STAND = ("Dieser Zähler kommt aus Home Assistant, und eedc rechnet mit dem Zählerstand, den der Sensor anzeigt — "
                 "„Summe anpassen“ in Home Assistant ändert daran nichts; hier wird nichts eingetragen. Damit der Tausch nicht als "
                 "Verbrauch zählt, gibt es zwei Wege: in Home Assistant für den neuen Zähler einen eigenen Sensor oder Helfer "
                 "anlegen, ihn diesem Feld zuordnen und im Dialog „Bisherige Werte bleiben“ wählen; oder den neuen Zähler als "
                 "eigenes Gerät anlegen und am alten ein Stilllegungsdatum setzen (Handbuch Einstellungen, Verbrauchszähler).")
SATZ_FORTSETZUNG = ("eedc überbrückt den Tausch am {zeit}: der Unterschied zwischen altem und neuem Zählerstand zählt nicht "
                    "als Menge. Die Werte vor und nach dem Tausch bleiben; wo eedc aus den gespeicherten Zählerständen rechnet, "
                    "zählt die Stunde des Tauschs keinen Zuwachs.")
SATZ_NACHTRAG = ("Die Stunde ab {stunde} Uhr ist schon gespeichert; sie zählt danach keinen Zuwachs — auch nicht, was in "
                 "dieser Stunde vor dem Tausch verbraucht wurde.")
SATZ_NACHTRAG_BISHER = "Bisher zählt sie {zuwachs} {einheit}."
#: Benannte Grenze «Zu §13» Nr. 87: ein fest gespeicherter Tageswert vom Tag des Tauschs bleibt (nur, wenn der Tausch nicht am
#: laufenden Tag liegt — der laufende Tag wird alle 15 Minuten neu gebildet). Sensorwechsel U3 a (Rechenweg G3, Bauplan «Zu
#: §14» Nr. 95 (4)): nur, wenn die Tageszeile dieses Tages den Wert des Felds wirklich trägt — dann mit Tag und Wert.
SATZ_TAG_FEST = ("Für den {tag} hat eedc schon einen festen Tageswert dieses Felds gespeichert ({wert} {einheit}); er bleibt, "
                 "wie er ist, und kann den Unterschied weiter enthalten.")
SATZ_OHNE_WERTE = "Dieses Feld hat noch keine eigenen Werte — es gibt keinen Sprung zu überbrücken."
SATZ_KEINE_QUELLE = "Dieses Feld hat keine Quelle — ordne zuerst eine zu."
SATZ_SCHON = "Dieser Tausch ist schon eingetragen."
SATZ_VOR_ERSTEM_WERT = ("Dieses Feld hat erst ab {zeit} Uhr eigene Werte — vor dem ersten Wert gibt es keinen Sprung zu "
                        "überbrücken; hier wird nichts eingetragen.")
#: U3 b (G5): die Rand-Stände aus den Rohständen.
SATZ_FORTSETZUNG_ROH = ("eedc trägt den Tausch am {zeit} Uhr ein: dort springt der Zählerstand von {alt} auf {neu} {einheit}. "
                        "Dieser Unterschied zählt nicht als Menge; die Stunde des Tauschs zählt, was der alte Zähler bis zu "
                        "seinem letzten Stand und der neue ab seinem ersten gezählt hat. Die Werte vor und nach dem Tausch "
                        "bleiben.")
SATZ_NACHTRAG_ROH = ("Die Stunde ab {stunde} Uhr ist schon gespeichert; eedc rechnet sie neu aus den Zählerständen vor und nach "
                     "dem Tausch: {neu} statt {bisher} {einheit}.")
#: U3-K (B1): eine negative Menge der Naht wird nie geschrieben.
SATZ_NEGATIV = ("Nach einem Eintrag um {zeit} Uhr zählte die Stunde ab {stunde} Uhr {neu} {einheit} — weniger als nichts. Die "
                "Zählerstände dieser Stunde passen nicht zu einem Tausch um diese Zeit, eedc trägt nichts ein. Wähle unter "
                "„Getauscht am“ die Zeit, zu der der Stand springt; der Daten-Checker nennt sie unter „Zählerstand springt "
                "(MQTT)“.")
#: Bauplan Nr. 166 (Wortlaut des Masters): R2 — der Stand vor der gewählten Zeit und der nächste andere danach; statt
#: ``SATZ_FORTSETZUNG_ROH``. Wurde der Stand vor dem Schritt mindestens einmal wiederholt, die stille Zeit.
SATZ_SCHRITT = ("Der Zählerstand ändert sich zwischen {von} und {bis} Uhr von {alt} auf {neu} {einheit}. Trägst du den Tausch ein, "
                "zählt eedc diese {menge} {einheit} nicht.")
SATZ_SCHRITT_STILL = ("Der Zählerstand steht von {seit} bis {bis} Uhr still und ändert sich dann von {alt} auf {neu} {einheit}. "
                      "Trägst du den Tausch ein, zählt eedc diese {menge} {einheit} nicht.")
#: Danach genau einer der Hinweise (``rohstand.abgehoben_am``: hebt sich der Schritt ab?).
SATZ_HINWEIS_UNKLAR = "Ob das ein Tausch ist oder eine gezählte Menge, erkennt eedc nicht."
SATZ_HINWEIS_KEIN_SPRUNG = "Einen Sprung sieht eedc an dieser Zeit nicht."
SATZ_NOCH_KEIN_STAND = ("Nach {zeit} Uhr ist noch kein Zählerstand gespeichert. eedc trägt den Tausch ein und nimmt den letzten "
                        "Stand davor und den ersten danach, sobald er gespeichert ist.")
#: Bauplan Nr. 166 (eigene Fassung U3-K4): nach der Zeit ist nur der still wiederholte Stand gespeichert.
SATZ_NOCH_KEIN_ANDERER = ("Nach {zeit} Uhr hat sich der Zählerstand noch nicht geändert. eedc trägt den Tausch ein und nimmt den "
                          "letzten Stand davor und den ersten anderen danach, sobald er gespeichert ist.")
#: U3 b (Entscheid E4): Live rechnet bei MQTT aus den Rohständen selbst (``mqtt_energy_history_service``) — der Eintrag ändert
#: daran nichts; nur genannt, wenn der Tausch heute oder gestern liegt.
SATZ_LIVE = ("Die Live-Anzeige rechnet direkt aus den Zählerständen: sie zeigt den Sprung am Tag des Tauschs unter „heute“ "
             "und am Tag danach unter „gestern“ weiter; Tag, Monat und Jahr zählen ihn nach dem Eintrag nicht.")
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
    #: Der Tausch liegt vor dem laufenden Tag (dann nennt die Antwort ``SATZ_TAG_FEST``, wenn ``tag_fest`` gesetzt ist).
    vor_heute: bool = False
    #: U3 a (G3): der fest gespeicherte Tageswert des Felds am Tag des Tauschs ``(Tag, Wert)`` — ``None`` = keiner.
    tag_fest: Optional[tuple[date, float]] = None
    #: Sensorwechsel U2 Lauf c (F13): ein Stand-Zähler (Kanal-Art ``stand``) — der Weg ``home_assistant`` nennt dann E2.
    stand: bool = False
    #: U3 b (G5): die Rand-Stände aus den Rohständen ``((zeit, stand) vor, (zeit, stand) ab)`` und was die Stunde danach zählt.
    rand: Optional[tuple] = None
    neu: Optional[float] = None
    #: U3 b (G5) / Bauplan Nr. 166: ``sprung`` (R1, ``rand`` ist die Spanne) · ``schritt`` (R2, ``rand`` ist der Stand davor und
    #: der nächste andere) · ``noch_kein_stand`` (eintragen, der Stundenlauf setzt die Rand-Stände) · ``ohne``.
    rohstand: Optional[str] = None
    heute: Optional[date] = None
    #: R2: seit wann der Stand davor unverändert gespeichert ist (``rohstand.still_seit``) und ob der Schritt sich abhebt.
    still_seit: Optional[datetime] = None
    abgehoben: bool = False


def _zeit(dt: Optional[datetime]) -> str:
    return dt.strftime("%d.%m.%Y %H:%M") if dt is not None else ""


async def _katalog_art(db, key: str) -> Optional[str]:
    """Die Kanal-Art des Katalogs für diesen Zähler (``sum``/``stand``; ``None`` = kein Kanal)."""
    from backend.models.investition import Investition
    from backend.services.kanal.katalog import zaehler_art

    typ = None
    if key.startswith("inv:"):
        inv = await db.get(Investition, int(key.split(":")[1]))
        typ = inv.typ if inv is not None else None
    return zaehler_art(key, typ)


async def _katalog_spiegelt(db, key: str) -> bool:
    """Noch kein Kanal: spiegelt der nächste Stundenlauf diesen Zähler aus Home Assistant (der Katalog führt eine Art)?"""
    return await _katalog_art(db, key) is not None


async def _ist_stand(db, key: str, kanal) -> bool:
    """Stand-Zähler (Kanal-Art ``stand``; ohne Kanal die Art des Katalogs)."""
    from backend.models.kanal import ART_STAND

    return (kanal.art if kanal is not None else await _katalog_art(db, key)) == ART_STAND


def _quelle_zur_zeit(wechsel, q: dict, zeitpunkt: datetime) -> dict:
    """Die wirksame Quelle zur Zeit des Tauschs (F13): ``quelle_am``; gilt die heutige oder ist sie unbekannt, die heutige."""
    am = quelle_am(wechsel, zeitpunkt)
    return am if am is not HEUTE and isinstance(am, dict) else q


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


async def naht_stunde(db, kanal, zeitpunkt: datetime) -> int:
    """Die Stunde, deren Zuwachs ein Wechsel um ``zeitpunkt`` trägt (Bauplan §13 Nr. 68) — eine Regel für Nachtrag, Einstieg
    und Vorschau. Im Stundenlauf der Mitschrift (MQTT) gehört ein Rohstand zur Stunde, in der er eintraf, und die Stände ab
    ``zeitpunkt`` beginnen die neue Periode: die Stunde, in der ``zeitpunkt`` liegt. Im **Nachbau-Abschnitt aus Home
    Assistants Ständen** (``nachfuellen._rohstaende``, Kennung ``sensor_snapshots:…``) trägt die Zeile ``Z − 1 h`` den Stand
    zur vollen Stunde ``Z``, und ein Stand ab ``ab_ts`` gehört zur neuen Quelle (wie ``nachfuellen._laeufe`` und die Leser der
    Reihe): die Stunde vor ``ab_ts``. Beide stimmen überein, außer bei einem Wechsel genau zur vollen Stunde."""
    from backend.services.kanal.angaben import quelle_zur_stunde
    from backend.services.kanal.nachfuellen import STAENDE_HA_PRAEFIX

    stunde = int(zeitpunkt.replace(minute=0, second=0, microsecond=0).timestamp())
    vor_ab = int(ab_ts_aus(zeitpunkt).timestamp()) - 3600
    if kanal is None or vor_ab == stunde:
        return stunde
    kq = await quelle_zur_stunde(db, kanal.id, vor_ab)
    nachbau = kq is not None and (kq.statistic_id or "").startswith(STAENDE_HA_PRAEFIX)
    return vor_ab if nachbau else stunde


async def _nachtrag_stunde(db, kanal, stunde: int) -> Optional[int]:
    """Die erste schon geschriebene Stunde ab ``stunde`` (``naht_stunde``), wenn dort die Mitschrift (MQTT oder der
    Nachbau-Abschnitt) gilt — nur sie trägt den Nachtrag (``kanal/naht.nachtrag_fortsetzung``)."""
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


async def lage(db, anlage, sensor_key: Optional[str], getauscht_am: datetime, *, heute: Optional[date] = None) -> Lage:
    """Welcher Weg gilt für dieses Feld zu diesem Zeitpunkt (lesend). ``heute``: der laufende Tag (Proben; sonst die Uhr)."""
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
    stunde = await naht_stunde(db, kanal, getauscht_am)
    wechsel = (await lade_wechsel(db, anlage.id)).get(sensor_key, ())
    q_zeit = _quelle_zur_zeit(wechsel, q, getauscht_am)
    weg = await _weg(db, sensor_key, q_zeit, kanal, stunde)
    if weg != WEG_FORTSETZUNG:
        stand = weg == WEG_HOME_ASSISTANT and await _ist_stand(db, sensor_key, kanal)
        return Lage(sensor_key, weg, q, getauscht_am, stand=stand)
    kwh = kanal is None or kanal.einheit in (None, "", "kWh")
    rohstand, rand = await _rohstand(db, anlage.id, sensor_key, q_zeit, getauscht_am, kwh=kwh)
    if rand is not None:                       # U3 b (G5): der Tausch liegt am Höhenwechsel der Rohstände
        getauscht_am = rand[1][0].replace(microsecond=0)
        ab = ab_ts_aus(getauscht_am)
        stunde = await naht_stunde(db, kanal, getauscht_am)   # R2: der nächste andere Stand kann in einer späteren Stunde liegen
    schon = _schon(wechsel, ab)
    nachtrag = await _nachtrag_stunde(db, kanal, stunde)
    zuwachs = await zuwachs_der_stunde(db, kanal, nachtrag) if nachtrag is not None else None
    heute = heute or date.today()
    vor_heute = getauscht_am.date() < heute
    la = Lage(sensor_key, WEG_FORTSETZUNG, q, getauscht_am, kanal.id if kanal is not None else None, nachtrag, schon,
              zuwachs=zuwachs, einheit=kanal.einheit if kanal is not None else None, vor_heute=vor_heute,
              tag_fest=await tag_fest(db, anlage, sensor_key, ab) if vor_heute else None, rand=rand, rohstand=rohstand,
              heute=heute)
    if rohstand == ROH_SCHRITT and rand is not None:
        from backend.services.zuordnung_wechsel.rohstand import abgehoben_am, mqtt_key_der_quelle, still_seit

        mk = mqtt_key_der_quelle(q_zeit, sensor_key)
        la.still_seit = await still_seit(db, anlage.id, mk, rand[0])
        la.abgehoben = await abgehoben_am(db, anlage.id, mk, rand, kwh=kwh)
    if rand is not None and nachtrag is not None:
        from backend.services.kanal.naht import menge_mit_rand

        la.neu = await menge_mit_rand(db, kanal.id, nachtrag, (rand[0][1], rand[1][1]))
        if la.neu is not None and la.neu < 0:            # U3-K (B1): nie eine negative Stunde schreiben
            la.weg = WEG_NEGATIV
    return la


def _schon(wechsel, ab: datetime) -> bool:
    """Ist an ``ab`` schon eine gültige Fortsetzung eingetragen?"""
    return any(w.grund == GRUND_FORTSETZUNG and w.aufgehoben_durch is None and w.ab_ts == ab for w in wechsel)


#: Bauplan Nr. 166: R2 — der Stand vor der Zeit und der nächste andere danach; ``noch_kein_anderer``: danach nur der wiederholte.
ROH_SCHRITT = "schritt"
ROH_NOCH_KEIN_ANDERER = "noch_kein_anderer"


async def _rohstand(db, anlage_id: int, sensor_key: str, quelle, t: datetime, *,
                   kwh: bool = True) -> tuple[Optional[str], Optional[tuple]]:
    """U3 b (G5), Bauplan Nr. 166: gilt zur Zeit des Tauschs MQTT, die Rand-Stände um ``t`` — R1 (``rohstand.sprung_um``: der
    Stand wechselt in der Stunde eindeutig die Höhe) oder R2 (``rohstand.naechster_anderer_um``: der nächste andere Stand;
    ohne ihn ``noch_kein_stand``)."""
    from backend.services.zuordnung_wechsel.rohstand import KEIN_HOEHENWECHSEL, mqtt_key_der_quelle, naechster_anderer_um, sprung_um

    mk = mqtt_key_der_quelle(quelle, sensor_key)
    if mk is None:
        return None, None
    art, paar = await sprung_um(db, anlage_id, mk, t, kwh=kwh)
    if art != KEIN_HOEHENWECHSEL:
        return art, paar
    paar = await naechster_anderer_um(db, anlage_id, mk, t)
    return (ROH_SCHRITT, paar) if paar is not None else (ROH_NOCH_KEIN_ANDERER, None)


async def tag_fest(db, anlage, sensor_key: str, ab: datetime) -> Optional[tuple[date, float]]:
    """U3 a (Rechenweg G3): der Tageswert, den eedc für den Tag der Stunde des Tauschs schon fest gespeichert hat — nur, wenn
    die Tageszeile den Schlüssel des Felds trägt (``verwerfen_vor_quellbeginn.tz_keys_der_zeile``, dieselbe Frage wie die
    Vorschau der Korrektur). Der Tag ist der Bestandstag der Stunde vor ``ab`` (``kanal/abgeleitet.tag_der_stunde``)."""
    from backend.services import verwerfen_vor_quellbeginn as vq
    from backend.services.kanal.abgeleitet import tag_der_stunde

    tag = tag_der_stunde(int(ab.timestamp()) - 3600)
    ziele = await vq.bestand_ziele(db, anlage, sensor_key)
    for row in await vq._tz_zeilen(db, anlage.id, tag, ziele, tag):
        werte = [w for k in vq.tz_keys_der_zeile(row, ziele) if (w := (row.komponenten_kwh or {}).get(k)) is not None]
        if werte:
            return tag, sum(float(w) for w in werte)
    return None


def _saetze_schritt(la: Lage) -> list[str]:
    """Bauplan Nr. 166: der Satz am Schritt (R2) — mit der stillen Zeit, wenn der Stand davor mindestens einmal wiederholt
    wurde — und genau ein Hinweis (hebt sich der Schritt ab?)."""
    from backend.core.berechnungen.rohstand_rand import menge_des_schritts
    from backend.core.zahlenformat import fmt_zahl

    werte = dict(bis=_zeit(la.rand[1][0]), alt=fmt_zahl(la.rand[0][1], 2), neu=fmt_zahl(la.rand[1][1], 2),
                 menge=fmt_zahl(menge_des_schritts(la.rand), 2), einheit=la.einheit or "kWh")
    if la.still_seit is not None and la.still_seit < la.rand[0][0]:
        satz = SATZ_SCHRITT_STILL.format(seit=_zeit(la.still_seit), **werte)
    else:
        satz = SATZ_SCHRITT.format(von=_zeit(la.rand[0][0]), **werte)
    return [satz, SATZ_HINWEIS_UNKLAR if la.abgehoben else SATZ_HINWEIS_KEIN_SPRUNG]


def _saetze_fortsetzung(la: Lage) -> list[str]:
    from backend.core.zahlenformat import fmt_zahl

    if la.rand is not None and la.rohstand == ROH_SCHRITT:
        s = _saetze_schritt(la)
    elif la.rand is not None:
        s = [SATZ_FORTSETZUNG_ROH.format(zeit=_zeit(la.getauscht_am), alt=fmt_zahl(la.rand[0][1], 1),
                                         neu=fmt_zahl(la.rand[1][1], 1), einheit=la.einheit or "kWh")]
    else:
        s = [SATZ_FORTSETZUNG.format(zeit=_zeit(la.getauscht_am))]
        if la.rohstand in ("noch_kein_stand", ROH_NOCH_KEIN_ANDERER):
            satz = SATZ_NOCH_KEIN_STAND if la.rohstand == "noch_kein_stand" else SATZ_NOCH_KEIN_ANDERER
            s.append(satz.format(zeit=_zeit(la.getauscht_am)))
    if la.nachtrag_ts is not None and la.rand is not None and la.neu is not None and la.zuwachs is not None:
        s.append(SATZ_NACHTRAG_ROH.format(stunde=_zeit(datetime.fromtimestamp(la.nachtrag_ts)), neu=fmt_zahl(la.neu, 2),
                                          bisher=fmt_zahl(la.zuwachs, 2), einheit=la.einheit or "kWh"))
    elif la.nachtrag_ts is not None:
        s.append(SATZ_NACHTRAG.format(stunde=_zeit(datetime.fromtimestamp(la.nachtrag_ts))))
        if la.zuwachs is not None:
            s.append(SATZ_NACHTRAG_BISHER.format(zuwachs=fmt_zahl(la.zuwachs, 2), einheit=la.einheit or "kWh"))
    if la.rohstand is not None and la.heute is not None and (la.heute - la.getauscht_am.date()).days <= 1:
        s.append(SATZ_LIVE)
    if la.vor_heute and la.tag_fest is not None:
        s.append(SATZ_TAG_FEST.format(tag=la.tag_fest[0].strftime("%d.%m.%Y"), wert=fmt_zahl(la.tag_fest[1], 2),
                                      einheit=la.einheit or "kWh"))
    return s


def saetze(la: Lage) -> list[str]:
    from backend.core.zahlenformat import fmt_zahl

    feste = {WEG_HOME_ASSISTANT: SATZ_HA_STAND if la.stand else SATZ_HA, WEG_OHNE_WERTE: SATZ_OHNE_WERTE,
             WEG_KEINE_QUELLE: SATZ_KEINE_QUELLE}
    if la.weg in feste:
        return [feste[la.weg]]
    if la.weg == WEG_VOR_ERSTEM_WERT:
        return [SATZ_VOR_ERSTEM_WERT.format(zeit=_zeit(la.erster_wert))]
    if la.weg == WEG_NICHT_MOEGLICH:
        return [satz_nicht_moeglich(la)]
    if la.weg == WEG_NEGATIV:
        return [SATZ_NEGATIV.format(zeit=_zeit(la.getauscht_am), stunde=_zeit(datetime.fromtimestamp(la.nachtrag_ts)),
                                    neu=fmt_zahl(la.neu, 2), einheit=la.einheit or "kWh")]
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
    from backend.services.zuordnung_wechsel.rohstand import setze_rand

    t = la.getauscht_am.replace(microsecond=0)
    row = ZuordnungWechsel(anlage_id=anlage.id, sensor_key=la.sensor_key, erklaert_ts=t, ab_ts=ab_ts_aus(t),
                           vorher=la.quelle, nachher=la.quelle, grund=GRUND_FORTSETZUNG, herkunft=HERKUNFT_WECHSEL)
    if la.rand is not None:                    # U3 b (G5): Rand-Stände aus den Rohständen
        setze_rand(row, la.rand)
    db.add(row)
    await db.flush()
    merke_neu(db, row)
    if la.nachtrag_ts is not None:
        await nachtrag_fortsetzung(db, la.kanal_id, la.nachtrag_ts,
                                   rand=None if la.rand is None else (la.rand[0][1], la.rand[1][1]))
    merken.invalidiere(anlage.id, db=db)
    return row
