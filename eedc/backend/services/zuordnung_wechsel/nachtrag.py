"""Quellen in Anwender-Sprache, die Feld-Kennung eines Zählerschlüssels und die Sätze am versetzten Abschnitt (Sensorwechsel mit
Grund; Rest nach Weg B, Sitzung B2).

«Grund nachtragen» an einem verzeichneten Wechsel (Sitzung 4, Bauplan B-7) samt Befund «Zuordnung geändert, Grund fehlt» ist seit
Weg B entfernt (Entscheid Gernot 21.11.2026). Hier bleiben ``quelle_text`` (Sätze zu «bleiben», ``bleiben.py``),
``feld_id_aus_schluessel`` (Routen), ``ist_quellenwechsel`` (Ansetzen eines Wechsels «bleiben», ``ansatz.py``) und — bis zum
Entscheid über die Korrektur am versetzten Abschnitt (``stueck.py``, Routen ``…/zaehler-versatz``) — deren Gründe und Sätze
(``GRUENDE_NACHTRAG``, ``SATZ_GRUND_FEHLT``, ``SATZ_NUR_KORREKTUR_STUECK``, ``satz_lauf_offen``).
"""

from __future__ import annotations

from typing import Optional

from backend.models.zuordnung_wechsel import GRUND_FORTSETZUNG, GRUND_KORREKTUR
from backend.services.zuordnung_wechsel.abfrage import _gleich

#: Die Gründe, die die Korrektur über ein Stück annimmt (an einer MQTT-Reihe auch «bleiben»); beim Wechsel selbst gelten seit B1
#: ``abfrage.GRUENDE`` («bleiben», «löschen»).
GRUENDE_NACHTRAG = (GRUND_FORTSETZUNG, GRUND_KORREKTUR)
SATZ_GRUND_FEHLT = "Wähle, ob die bisherigen Werte bleiben oder verworfen werden."
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


def ist_quellenwechsel(w) -> bool:
    """Ein Wechsel der Quelle: nicht aufgehoben, kein «Zähler getauscht» (``vorher = nachher``), keine Korrektur-Zeile (auch
    keine Lücken-Zeile, ``zeitpunkt.ist_luecken_zeile``) — Bauplan «Zu §14» Nr. 103."""
    return w.aufgehoben_durch is None and w.grund != GRUND_KORREKTUR and not _gleich(w.vorher, w.nachher)


__all__ = ["GRUENDE_NACHTRAG", "QUELLE_UNBEKANNT", "SATZ_GRUND_FEHLT", "SATZ_LAUF_OFFEN", "SATZ_LAUF_OFFEN_ANSETZEN",
           "SATZ_NUR_KORREKTUR_STUECK", "feld_id_aus_schluessel", "ist_quellenwechsel", "quelle_text", "satz_lauf_offen"]
