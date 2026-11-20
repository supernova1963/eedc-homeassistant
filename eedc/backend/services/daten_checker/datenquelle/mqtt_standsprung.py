"""Daten-Checker — Zählerstand springt in einer MQTT-Reihe (Sensorwechsel mit Grund, U3 Lauf b, Rechenweg G4, Entscheide E2/E6).

**Warum es das gibt.** Bei MQTT ist der Rohstand die Quelle; eedc führt daraus je Stunde die Summe nach Home Assistants Regel
(Kanal «Eigene Summe», ``kanal/schreiber._eigene_summe``). Wird der Zähler oder das Gerät getauscht, oder sendet ein anderes Gerät
auf demselben Topic, wechselt der Stand die Höhe — und die Regel zählt den Unterschied als Menge der Stunde: einen Sprung nach
oben ganz, einen Neubeginn, der nicht bei 0 liegt, mit dem ganzen neuen Stand, einen Fall um weniger als 10 % als negative
Menge. Bisher nannte das kein Befund (``zaehler_ruecksprung`` riet bei einem Fall zum Tageszähler, beim Sprung schwieg er).

**Erkennung:** der Kern aus U2 Lauf c (``core/berechnungen/zaehlerstand_sprung.py``: Maß, Arme «Neubeginn» und «Sprung») mit dem
dritten Arm «Rückgang» je **Quell-Abschnitt** eines MQTT-Kanals (Familie Mitschrift, ``statistic_id`` = MQTT-Schlüssel — nicht
der Nachbau aus gespeicherten HA-Ständen); ein Zeilenpaar über eine Quellgrenze ist nie ein Sprung — nach dem Eintrag «Zähler
getauscht» beginnt an der Stunde eine Quellzeile und der Befund verschwindet. Fenster: der ganze Kanal (E2; der Handgriff wirkt
für jede Zeit). Ausgenommen: die Rückkehr-Stunden «kurz 0 und zurück» (``ha_sprung.rueckkehr_stunden``) und die Schritte eines
versetzten Abschnitts, den ``zaehler_versatz`` nennt (G7: Sprung und Rückgang gehören dort zusammen).

**Eine Zeile je Stunde** (W-1: diese Datei ist die Erzeuger-Stelle), Schwere Warnung (E6), Sprung «Zähler getauscht» in die
Datenquellen (``ziel_datenquelle_schluessel(…, getauscht=<Zeit>)``): der Dialog «Zähler getauscht (gleiche Quelle)» öffnet mit
«Getauscht am» auf dem ersten Rohstand nach dem Höhenwechsel (``rohstand_rand.sprung_der_stunde``; ohne Rohstände der Beginn der
Stunde).

Schwesterdateien: ``standsprung.py`` (dieselbe Frage an der HA-Statistik), ``ruecksprung.py`` (lässt einen Rückgang aus, den diese
Prüfung nennt), ``versatz.py`` (versetzter Abschnitt).
"""

from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import text

from backend.core.berechnungen.zaehlerstand_sprung import NEUBEGINN, RUECKGANG, Standsprung, finde_standspruenge
from backend.core.zahlenformat import fmt_zahl
from backend.models.anlage import Anlage
from backend.services.daten_checker.datenquelle.ha_sprung import rueckkehr_stunden
from backend.services.daten_checker.kategorien import CheckErgebnis, CheckKategorie, CheckSeverity

#: So viele Stunden nennt die Prüfung je Anlage einzeln; darüber hinaus nennt die letzte Zeile die Zahl der weiteren.
BEISPIELE = 5

# Je MQTT-Abschnitt eines Mengen- oder Stand-Kanals (Familie Mitschrift, nicht der Nachbau aus HA-Ständen) die Zeilen in Zeitfolge.
_SQL = """
WITH q AS (
    SELECT kanal_id, gueltig_ab, familie, statistic_id, verworfen_ts,
           LEAD(gueltig_ab) OVER (PARTITION BY kanal_id ORDER BY gueltig_ab) AS gueltig_bis
    FROM kanal_quelle
)
SELECT k.id, k.key, k.art, k.einheit, q.gueltig_ab, q.statistic_id, s.start_ts, s.state, s.sum
FROM kanal k
JOIN q ON q.kanal_id = k.id
JOIN kanal_statistik s ON s.kanal_id = k.id AND s.start_ts >= q.gueltig_ab
                      AND (q.gueltig_bis IS NULL OR s.start_ts < q.gueltig_bis)
WHERE k.anlage_id = :a AND k.art IN ('sum', 'stand') AND q.familie = 'mitschrift' AND s.familie = 'mitschrift'
  AND q.verworfen_ts IS NULL AND q.statistic_id IS NOT NULL AND q.statistic_id NOT LIKE 'sensor_snapshots:%'
ORDER BY k.id, q.gueltig_ab, s.start_ts
"""


class Fund:
    __slots__ = ("key", "stand", "einheit", "mqtt_key", "sprung")

    def __init__(self, key: str, stand: bool, einheit: str, mqtt_key: str, sprung: Standsprung):
        self.key, self.stand, self.einheit, self.mqtt_key, self.sprung = key, stand, einheit, mqtt_key, sprung


def _kurz_tiefer(z: list[tuple]) -> set[int]:
    """Die Stunden des Musters «kurz tiefer und zurück»: der Stand fällt in einer Zeile und erreicht in der nächsten wieder
    mindestens den Stand davor — beide Stunden (der Tag zählt den Fall und die Rückkehr, in Summe nichts; ``zaehler_ruecksprung``
    nennt das Zurückfallen wie bisher). Wie «kurz 0 und zurück» (``ha_sprung.rueckkehr_stunden``) kein Wechsel der Höhe."""
    aus: set[int] = set()
    for i in range(1, len(z) - 1):
        vorher, tief, danach = z[i - 1][1], z[i][1], z[i + 1][1]
        if vorher is not None and tief is not None and danach is not None and tief < vorher and danach >= vorher:
            aus |= {int(z[i][0]), int(z[i + 1][0])}
    return aus


def finde(zeilen, ausgenommen: dict[str, set[int]] | None = None) -> list[Fund]:
    """Reine Funktion über die Zeilen der Abfrage: je Sprung ein Fund in Zeitfolge. Am Stand-Kanal zählt Δ ``state`` (die
    Zeile trägt keine Summe; der Arm «Rückgang» bleibt dort aus — einen fallenden Stand nennt ``zaehlerstand_reihe_bruch``)."""
    abschnitte: dict[tuple, list[tuple]] = {}
    for _kid, key, art, einheit, ab, sid, ts, st, su in zeilen:
        abschnitte.setdefault((key, art, einheit or "", sid, ab), []).append((int(ts), st, st if art == "stand" else su))
    funde: list[Fund] = []
    for (key, art, einheit, sid, _ab), z in abschnitte.items():
        aus = set(rueckkehr_stunden(z)) | _kurz_tiefer(z) | set((ausgenommen or {}).get(key, ()))
        stand = art == "stand"
        for sp in finde_standspruenge(z, stand=stand, ausgenommen=aus, rueckgang=not stand):
            funde.append(Fund(key, stand, einheit, sid, sp))
    funde.sort(key=lambda f: (f.sprung.start_ts, f.key))
    return funde


#: Wortlaute (Gerüst Rechenweg G4; Wortlaut-Liste im Bericht U3 b).
SATZ_MELDUNG = "{feld}: Zählerstand springt am {tag} um {uhr} Uhr"
SATZ_SPRUNG = ("Der Zählerstand zeigt plötzlich {nachher} statt {vorher} {einheit}. eedc zählt den Unterschied als Menge dieser "
               "Stunde ({menge} {einheit}) — in Tag, Monat und Jahr.")
SATZ_NEUBEGINN = ("Der Zählerstand beginnt neu bei {nachher} statt bei 0 (vorher {vorher} {einheit}). eedc zählt den ganzen neuen "
                  "Stand als Menge dieser Stunde ({menge} {einheit}) — in Tag, Monat und Jahr.")
SATZ_RUECKGANG = ("Der Zählerstand fällt von {vorher} auf {nachher} {einheit}. eedc zählt den Rückgang als negative Menge dieser "
                  "Stunde ({menge} {einheit}) — in Tag, Monat und Jahr.")
SATZ_WARUM = ("So sieht es aus, wenn der Zähler oder das Gerät getauscht wurde oder ein anderes Gerät auf demselben Topic "
              "sendet. Trag den Tausch ein: „Zähler getauscht“ öffnet in den Datenquellen den Dialog „Zähler getauscht (gleiche "
              "Quelle)“ mit der Zeit des Sprungs. Danach zählt die Stunde nur, was der alte Zähler bis zu seinem letzten und der "
              "neue ab seinem ersten Stand gezählt hat.")
#: Entscheid E4 (Bauplan Nr. 150): Live rechnet bei MQTT aus den Rohständen selbst und zeigt den Sprung weiter.
SATZ_LIVE = ("Die Live-Anzeige rechnet direkt aus den Zählerständen: sie zeigt den Sprung am Tag des Sprungs unter „heute“ und "
             "am Tag danach unter „gestern“, auch nach dem Eintrag.")
SATZ_WEITERE = ("Dazu {n} weitere Stunde(n) mit einem Sprung — sie erscheinen hier, sobald für die genannten ein Tausch "
                "eingetragen ist.")


def _satz(f: Fund) -> str:
    vorlage = {NEUBEGINN: SATZ_NEUBEGINN, RUECKGANG: SATZ_RUECKGANG}.get(f.sprung.art, SATZ_SPRUNG)
    return vorlage.format(vorher=fmt_zahl(f.sprung.stand_vorher, 1), nachher=fmt_zahl(f.sprung.stand_nachher, 1),
                          menge=fmt_zahl(f.sprung.menge, 1), einheit=f.einheit or "kWh")


class MqttZaehlerstandSpringtChecks:
    """Prüfung: der Zählerstand einer MQTT-Reihe springt (Gerätetausch, anderes Gerät auf demselben Topic)."""

    async def _check_mqtt_zaehlerstand_springt(self, anlage: Anlage) -> list[CheckErgebnis]:
        """Je Stunde mit Sprung eine Zeile (höchstens ``BEISPIELE``) mit dem Sprung «Zähler getauscht». Ohne MQTT-Kanal kein
        Befund."""
        funde = await mqtt_spruenge(self.db, anlage.id)
        if not funde:
            return []
        namen = await self._standsprung_namen(anlage.id, {f.key for f in funde})
        out = []
        for i, f in enumerate(funde[:BEISPIELE]):
            zeit = await zeit_des_sprungs(self.db, anlage.id, f)
            teile = [_satz(f), SATZ_WARUM, SATZ_LIVE]
            if i == BEISPIELE - 1 and len(funde) > BEISPIELE:
                teile.append(SATZ_WEITERE.format(n=len(funde) - BEISPIELE))
            out.append(_zeile(namen.get(f.key, f.key), f, zeit, " ".join(teile)))
        return out


def _zeile(name: str, f: Fund, zeit: datetime, details: str) -> CheckErgebnis:
    """Die eine Erzeuger-Stelle des Codes (W-1)."""
    from backend.services.daten_checker.ziele import ziel_datenquelle_schluessel

    return CheckErgebnis(
        kategorie=CheckKategorie.MQTT_ZAEHLERSTAND_SPRINGT.value,
        schwere=CheckSeverity.WARNING,
        meldung=SATZ_MELDUNG.format(feld=name, tag=zeit.strftime("%d.%m.%Y"), uhr=zeit.strftime("%H:%M")),
        details=details,
        code="mqtt_zaehlerstand_springt",
        werte={"feld": f.key, "mqtt_key": f.mqtt_key, "art": f.sprung.art,
               "stunde": datetime.fromtimestamp(f.sprung.start_ts).isoformat(timespec="minutes"),
               "getauscht": zeit.isoformat(timespec="minutes"), "menge": round(f.sprung.menge, 3), "einheit": f.einheit,
               "stand_vorher": f.sprung.stand_vorher, "stand_nachher": f.sprung.stand_nachher,
               "mass": round(f.sprung.mass, 1)},
        ziel=ziel_datenquelle_schluessel(f.key, getauscht=zeit.isoformat(timespec="minutes")),
    )


async def mqtt_spruenge(db, anlage_id: int) -> list[Fund]:
    """Die Funde der Anlage (eine Abfrage über alle MQTT-Abschnitte), ohne die Schritte versetzter Abschnitte (G7) — auch
    für ``zaehler_ruecksprung`` (ein Rückgang, den diese Prüfung nennt, steht dort nicht noch einmal)."""
    from backend.services.daten_checker.datenquelle.versatz_mqtt import mqtt_versatz_stunden

    zeilen = (await db.execute(text(_SQL), {"a": anlage_id})).all()
    if not zeilen:
        return []
    return finde(zeilen, await mqtt_versatz_stunden(db, anlage_id))


async def benannte_stunden(db, anlage_id: int) -> dict[str, set[int]]:
    """Die Kanal-Stunden je Schlüssel, deren Rückgang ein Befund dieses Laufs nennt: «Zählerstand springt» mit fallendem Stand
    (Arme «Neubeginn» und «Rückgang») und die Schritte eines versetzten Abschnitts (``versatz.mqtt_versatz_stunden``) — für
    ``zaehler_ruecksprung`` (ein Befund je Ursache)."""
    from backend.services.daten_checker.datenquelle.versatz_mqtt import mqtt_versatz_stunden

    aus = {k: set(v) for k, v in (await mqtt_versatz_stunden(db, anlage_id)).items()}
    for f in await mqtt_spruenge(db, anlage_id):
        if f.sprung.art in (NEUBEGINN, RUECKGANG):
            aus.setdefault(f.key, set()).add(f.sprung.start_ts)
    return aus


async def zeit_des_sprungs(db, anlage_id: int, f: Fund) -> datetime:
    """Der erste Rohstand nach dem Höhenwechsel in der Stunde des Funds (``rohstand.sprung_um``); ohne Rohstände (älter als
    31 Tage) der Beginn der Stunde."""
    from backend.services.zuordnung_wechsel.rohstand import sprung_um

    stunde = datetime.fromtimestamp(f.sprung.start_ts)
    art, paar = await sprung_um(db, anlage_id, f.mqtt_key, stunde + timedelta(minutes=59, seconds=59))
    return paar[1][0].replace(microsecond=0) if art == "sprung" and paar is not None else stunde


__all__ = ["BEISPIELE", "Fund", "MqttZaehlerstandSpringtChecks", "benannte_stunden", "finde", "mqtt_spruenge",
           "zeit_des_sprungs"]
