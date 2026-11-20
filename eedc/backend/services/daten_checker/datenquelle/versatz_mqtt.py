"""Versetzter Abschnitt in einer **MQTT-Reihe** (Sensorwechsel mit Grund, U3 Lauf b, Rechenweg G7, Entscheid E1 = A) — die
Helfer des Befunds ``zaehler_versatz`` (``versatz.py`` bleibt die eine Erzeuger-Stelle, W-1).

**Lage.** Sendet eine Zeit lang ein anderes Gerät auf demselben Topic (oder wird ein Zähler getauscht und später
zurückgetauscht), springt die Reihe der MQTT-Stände um +X und fällt später um ≈ −X zurück — dieselbe Regel wie in einer Reihe
aus Home Assistant (``core/berechnungen/zaehler_versatz.py``), gelesen über die Stände mit ``quelle = mqtt_inbound``. Geprüft
wird ein Schlüssel nur, wenn eedc für ihn einen MQTT-Kanal «Eigene Summe» führt: dort wirkt der Abschnitt — der Kanal zählt den
Sprung als Menge und den Rückgang als Neubeginn bzw. negative Menge (HAs Summenregel), die Tage beider Schritte sind falsch.

**Zwei Antworten** («Grund nachtragen» am Befund, ``stueck.py``): «Bisherige Werte bleiben» trägt an Sprung und Rückgang je einen
Zählertausch ein (``zaehler_getauscht``, mit den Rand-Ständen aus den Rohständen, G5) — die Werte des Abschnitts sind Werte der
Quelle und zählen, die zwei Sprünge nicht; «Bisherige Werte verwerfen» verwirft das Stück (Korrektur über das Stück) — da davor
und danach dieselbe Quelle gilt, rechnen Kanal und Reihe über die leere Zeit wie über jede Zählerlücke.

Ein Schritt an einer verzeichneten Fortsetzung (nach «bleiben») ist ohne Wirkung — dann erscheint der Befund nicht mehr. Die
Kanal-Stunden der Schritte mit Wirkung (``mqtt_versatz_stunden``) nennt ``mqtt_standsprung`` nicht noch einmal (G7).
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Optional

from sqlalchemy import text

from backend.core.berechnungen.zaehler_versatz import Schritt, VersatzLauf, finde_versatz_laeufe

_SQL_MQTT_SCHLUESSEL = """
SELECT DISTINCT k.key FROM kanal k JOIN kanal_quelle q ON q.kanal_id = k.id
WHERE k.anlage_id = :a AND k.art IN ('sum', 'stand') AND q.familie = 'mitschrift' AND q.statistic_id IS NOT NULL
  AND q.statistic_id NOT LIKE 'sensor_snapshots:%'
  AND EXISTS (SELECT 1 FROM sensor_snapshots s WHERE s.anlage_id = :a AND s.sensor_key = k.key AND s.quelle = :q)
"""

#: Lage des Befunds an einer MQTT-Reihe (``werte.lage``): «Grund nachtragen» bietet beide Antworten.
LAGE_MQTT = "mqtt"

#: Wortlaute (U3 b; Wortlaut-Liste im Bericht).
SATZ_DETAILS = ("Vom {von} bis {bis} liegen die Zählerstände dieses Felds um {versatz} kWh neben denen davor und danach — so sieht "
                "es aus, wenn eine Zeit lang ein anderes Gerät auf demselben Topic gesendet hat oder ein Zähler getauscht und "
                "später zurückgetauscht wurde. eedc zählt den Sprung und den Rückgang als Menge der Stunde: {folgen}. Gespeicherte "
                "Monatswerte ändert das nicht. ")
SATZ_FOLGE = "am {tage} ist der Tageswert deshalb falsch"
SATZ_LAGE = ("„Grund nachtragen“ bietet zwei Antworten: „Bisherige Werte bleiben“ trägt am Sprung und am Rückgang je einen "
             "Zählertausch ein — die Werte des Abschnitts zählen, die zwei Sprünge nicht. „Bisherige Werte verwerfen“ verwirft "
             "die Zählerstände des Abschnitts; da davor und danach dieselbe Quelle gilt, rechnet eedc über die leere Zeit wie "
             "über jede Zählerlücke: die Menge des Abschnitts steht an dem Tag, an dem er endet.")


async def lade_mqtt_reihe(db, anlage_id: int, key: str) -> list[tuple[datetime, float]]:
    """Die Reihe der MQTT-Stände eines Schlüssels (``quelle = mqtt_inbound``), aufsteigend."""
    from backend.services.daten_checker.datenquelle.versatz import lade_reihe
    from backend.services.snapshot.source import SnapshotSource

    return await lade_reihe(db, anlage_id, key, SnapshotSource.MQTT_INBOUND)


async def mqtt_schluessel(db, anlage_id: int) -> list[str]:
    """Die Schlüssel mit MQTT-Ständen in der Reihe und einem MQTT-Kanal «Eigene Summe»."""
    from backend.services.snapshot.source import SnapshotSource

    return sorted((await db.execute(text(_SQL_MQTT_SCHLUESSEL), {"a": anlage_id, "q": SnapshotSource.MQTT_INBOUND}))
                  .scalars().all())


def _tag(s: Schritt) -> date:
    return s.tag


async def wirkende_schritte(db, anlage_id: int, key: str, lauf: VersatzLauf) -> list[Schritt]:
    """Die Schritte des Abschnitts (Sprünge und Rückgänge), über die kein verzeichneter Wechsel führt — dort zählt der Kanal den
    Schritt als Menge."""
    from backend.core.berechnungen.zaehler_naht import ueber_naht
    from backend.services.zuordnung_wechsel.zeitpunkt import fortsetzungs_naehte

    naehte = await fortsetzungs_naehte(db, anlage_id, key)
    return [s for s in (*lauf.spruenge, *lauf.rueckgaenge) if not ueber_naht(s.von, s.bis, naehte)]


async def mqtt_laeufe(db, anlage_id: int) -> list[tuple[str, VersatzLauf, list[Schritt]]]:
    """Je MQTT-Schlüssel die versetzten Abschnitte mit wirkenden Schritten ``(schlüssel, lauf, schritte)``."""
    out = []
    for key in await mqtt_schluessel(db, anlage_id):
        for lauf in finde_versatz_laeufe(await lade_mqtt_reihe(db, anlage_id, key)):
            schritte = await wirkende_schritte(db, anlage_id, key, lauf)
            if schritte:
                out.append((key, lauf, schritte))
    return out


async def mqtt_versatz_stunden(db, anlage_id: int) -> dict[str, set[int]]:
    """Je Schlüssel die Kanal-Stunden der wirkenden Schritte (``[von, bis]`` des Schritts, stündlich) — ``mqtt_standsprung``
    und ``zaehler_ruecksprung`` nennen sie nicht noch einmal (G7)."""
    aus: dict[str, set[int]] = {}
    for key, _lauf, schritte in await mqtt_laeufe(db, anlage_id):
        for s in schritte:
            h = s.von.replace(minute=0, second=0, microsecond=0)
            while h <= s.bis:
                aus.setdefault(key, set()).add(int(h.timestamp()))
                h += timedelta(hours=1)
    return aus


def texte(name: str, lauf: VersatzLauf, schritte: list[Schritt]) -> tuple[str, str, list[date]]:
    """Meldung, Details (ohne den Satz der Lage) und die Tage mit falschem Tageswert."""
    from backend.services.daten_checker.datenquelle.versatz import _datum, _tage_text

    from backend.core.zahlenformat import fmt_zahl

    von, bis = lauf.beginn.bis.date(), lauf.ende.von.date()
    tage = sorted({_tag(s) for s in schritte})
    versatz = fmt_zahl(lauf.versatz_kwh, 1)
    meldung = f"{name}: Zählerstände vom {_datum(von)} bis {_datum(bis)} um {versatz} kWh versetzt — Tageswerte an den Rändern falsch"
    details = SATZ_DETAILS.format(von=_datum(von), bis=_datum(bis), versatz=versatz,
                                  folgen=SATZ_FOLGE.format(tage=_tage_text(tage)))
    return meldung, details, tage


async def ist_mqtt_stueck(db, anlage_id: int, key: str) -> bool:
    """Prüft der Befund diesen Schlüssel über die MQTT-Reihe (``mqtt_schluessel``)?"""
    return key in await mqtt_schluessel(db, anlage_id)


def feld_name(invs: dict, key: str) -> str:
    """Name des Felds wie in Vorschau und Auswahl («Anlage · Netzbezug», «{Gerät} · {Feld}»)."""
    from backend.services.verwerfen_vor_quellbeginn import feld_label

    return feld_label(key, {int(k): v for k, v in invs.items()})


def lauf_zum_stueck(laeufe: list[VersatzLauf], sprung: datetime, rueckgang: datetime) -> Optional[VersatzLauf]:
    def minute(t: datetime) -> datetime:
        return t.replace(second=0, microsecond=0)

    return next((x for x in laeufe if minute(x.beginn.bis) == minute(sprung) and minute(x.ende.bis) == minute(rueckgang)), None)


__all__ = ["LAGE_MQTT", "SATZ_LAGE", "feld_name", "ist_mqtt_stueck", "lade_mqtt_reihe", "lauf_zum_stueck", "mqtt_laeufe",
           "mqtt_schluessel", "mqtt_versatz_stunden", "texte", "wirkende_schritte"]
