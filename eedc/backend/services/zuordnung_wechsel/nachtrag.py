"""Quellen in Anwender-Sprache und die Feld-Kennung eines Zählerschlüssels (Sensorwechsel mit Grund; Rest nach Weg B).

«Grund nachtragen» an einem verzeichneten Wechsel (Sitzung 4, Bauplan B-7) samt Befund «Zuordnung geändert, Grund fehlt» (Weg B,
Sitzung B2) und die Korrektur am versetzten Abschnitt samt ihren Gründen und Sätzen (Sitzung B3a) sind seit Weg B entfernt
(Entscheid Gernot 21.11.2026). Hier bleiben ``quelle_text`` (Sätze zu «bleiben», ``bleiben.py``), ``feld_id_aus_schluessel``
(Routen) und ``ist_quellenwechsel`` (Ansetzen eines Wechsels «bleiben», ``ansatz.py``).
"""

from __future__ import annotations

from typing import Optional

from backend.services.zuordnung_wechsel.abfrage import _gleich


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
    """Ein Wechsel der Quelle: nicht aufgehoben, kein «Zähler getauscht» (``vorher = nachher``) — Bauplan «Zu §14» Nr. 103."""
    return w.aufgehoben_durch is None and not _gleich(w.vorher, w.nachher)


__all__ = ["QUELLE_UNBEKANNT", "feld_id_aus_schluessel", "ist_quellenwechsel", "quelle_text"]
