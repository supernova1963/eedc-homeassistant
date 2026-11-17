"""Wirksame Quelle je Zählerschlüssel (Grundlage Bauplan B-2) — was der Schreiber der Zählerstand-Reihe für einen Schlüssel liest.

Es gab bis hierher **keine einzelne** Funktion dafür (Messblatt Sitzung 0, M-H): der Schreiber nimmt die klassische Zuordnung,
dann ``quellen`` (HA ersetzt/ergänzt, MQTT/«keine» nimmt heraus, ``snapshot/writer._build_counter_map``), der MQTT-Schritt liest den
MQTT-Schlüssel, und eine Gateway-Zeile republiziert auf denselben Schlüssel — die Reihe sieht nur den Schlüssel. Diese Datei
legt die drei Teile zusammen, **ohne** sie neu zu entscheiden:

1. Steht der Schlüssel in ``_build_counter_map`` (ohne Stilllegungs-Filter — eine Stilllegung ist ein Geräte-Ende, kein Wechsel,
   Festlegung §7 Nr. 15) ⇒ ``{"art": "ha", "entity_id": …}``.
2. ``quellen`` sagt «keine» ⇒ ``{"art": "keine"}``.
3. sonst MQTT ⇒ ``{"art": "mqtt", "mqtt_key": …, "topic": …, "payload_typ": …, "json_pfad": …, "array_index": …, "faktor": …,
   "offset": …}`` — mit den Werten der **aktiven** Gateway-Zeile des Felds (die über ``mapping_id`` referenzierte, sonst die Zeile
   mit passendem ``ziel_key``), ohne Gateway-Zeile ``topic`` = ``None`` (Standard-Inbound).

``mapping_id`` gehört nicht in die Beschreibung (sie wechselt beim Upsert, ohne dass sich für die Werte etwas ändert); ein
Topic-Wechsel **derselben** Zeile oder ein Faktor 1 → 0,001 dagegen ändert sie. Keine Zugangsdaten — eine Gateway-Zeile trägt
keine. Die Prüf-Funktion ``aenderungen`` beantwortet «ändert diese Anfrage die wirksame Quelle eines Schlüssels mit eigenen
Werten?» (Sitzung 1: nur zum Verzeichnen; die Rückfrage kommt in Sitzung 3).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Optional

from sqlalchemy import select

from backend.services.snapshot.keys import (
    QUELLE_KEINE_ENERGY,
    _energy_field_id_to_sensor_key,
    _mqtt_key_to_sensor_key,
    _sensor_key_to_mqtt_key,
    extract_quellen_energy,
)

ART_HA = "ha"
ART_MQTT = "mqtt"
ART_KEINE = "keine"

#: Die Teile der Gateway-Zeile, die die Werte bewegen (Topic, Pfad, Faktor, Offset — Bauplan B-1).
_GATEWAY_TEILE = ("payload_typ", "json_pfad", "array_index", "faktor", "offset")


def sensor_key_aus_ziel_key(ziel_key: str) -> Optional[str]:
    """``energy/inv/2_Wallbox/ladung_kwh`` bzw. ``energy/inv/2/ladung_kwh`` → ``inv:2:ladung_kwh``; ``energy/einspeisung_kwh``
    → ``basis:einspeisung``; ein Live-Ziel → ``None``."""
    from backend.services.datenquellen_resolver import ziel_key_ohne_namen

    form = ziel_key_ohne_namen(ziel_key or "")
    if not form.startswith("energy/"):
        return None
    return _mqtt_key_to_sensor_key(form[len("energy/"):])


def _gateway_beschreibung(sensor_key: str, row) -> dict:
    aus = {"art": ART_MQTT, "mqtt_key": _sensor_key_to_mqtt_key(sensor_key), "topic": row.quell_topic}
    for teil in _GATEWAY_TEILE:
        wert = getattr(row, teil, None)
        aus[teil] = float(wert) if teil in ("faktor", "offset") and wert is not None else wert
    return aus


def _gateway_je_key(mapping: dict, gateway_zeilen) -> dict[str, object]:
    """Je Schlüssel die wirkende Gateway-Zeile: die per ``mapping_id`` referenzierte (aktiv), sonst eine aktive mit passendem
    ``ziel_key`` (sie wirkt auch ohne ``quellen``-Eintrag, W5)."""
    aktiv = [r for r in gateway_zeilen or () if getattr(r, "aktiv", True)]
    je_id = {r.id: r for r in aktiv}
    aus: dict[str, object] = {}
    for r in sorted(aktiv, key=lambda r: r.id or 0):
        sk = sensor_key_aus_ziel_key(r.ziel_key)
        if sk is not None:
            aus.setdefault(sk, r)
    quellen = mapping.get("quellen") if isinstance(mapping, dict) else None
    for field_id, eintrag in (quellen or {}).items():
        if not isinstance(eintrag, dict) or eintrag.get("quelle") != "mqtt_gateway":
            continue
        sk = _energy_field_id_to_sensor_key(field_id) if isinstance(field_id, str) else None
        row = je_id.get(eintrag.get("mapping_id"))
        if sk is not None and row is not None:
            aus[sk] = row
    return aus


def wirksame_quellen(mapping: Optional[dict], gateway_zeilen=()) -> dict[str, dict]:
    """Die wirksame Quelle je Zählerschlüssel (reine Funktion über ``sensor_mapping`` und die Gateway-Zeilen der Anlage).

    Schlüssel ohne jeden Eintrag fehlen — sie lesen den Standard-Inbound (``standard_quelle``)."""
    from backend.services.snapshot.writer import _build_counter_map

    mapping = mapping if isinstance(mapping, dict) else {}
    anlage = SimpleNamespace(sensor_mapping=mapping)
    ha = _build_counter_map(anlage)
    quellen_energy = extract_quellen_energy(anlage)
    gateway = _gateway_je_key(mapping, gateway_zeilen)
    aus: dict[str, dict] = {}
    for key in set(ha) | set(quellen_energy) | set(gateway):
        if key in ha:
            aus[key] = {"art": ART_HA, "entity_id": ha[key]}
        elif (quellen_energy.get(key) or (None, None))[0] == QUELLE_KEINE_ENERGY:
            aus[key] = {"art": ART_KEINE}
        elif key in gateway:
            aus[key] = _gateway_beschreibung(key, gateway[key])
        else:
            aus[key] = standard_quelle(key)
    return aus


def standard_quelle(sensor_key: str) -> dict:
    """Die Grundeinstellung eines Felds ohne Eintrag: MQTT-Inbound auf dem Standard-Topic."""
    return {"art": ART_MQTT, "mqtt_key": _sensor_key_to_mqtt_key(sensor_key), "topic": None}


async def lade_wirksame_quellen(db, anlage) -> dict[str, dict]:
    """``wirksame_quellen`` mit den Gateway-Zeilen der Anlage aus der Datenbank (Stand dieser Sitzung)."""
    from backend.models.mqtt_gateway_mapping import MqttGatewayMapping

    zeilen = (await db.execute(
        select(MqttGatewayMapping).where(MqttGatewayMapping.anlage_id == anlage.id)
    )).scalars().all()
    return wirksame_quellen(anlage.sensor_mapping, zeilen)


async def hat_eigene_werte(db, anlage_id: int, sensor_key: str, vor: Optional[datetime] = None) -> bool:
    """Hat der Schlüssel eigene Werte — Zählerstände der Reihe oder Kanalzeilen (vor ``vor``, örtlich ohne Zone)?"""
    from backend.models.kanal import Kanal, KanalStatistik
    from backend.models.sensor_snapshot import SensorSnapshot

    q = select(SensorSnapshot.id).where(
        SensorSnapshot.anlage_id == anlage_id, SensorSnapshot.sensor_key == sensor_key)
    if vor is not None:
        q = q.where(SensorSnapshot.zeitpunkt < vor)
    if (await db.execute(q.limit(1))).scalar_one_or_none() is not None:
        return True
    k = select(KanalStatistik.start_ts).join(Kanal, Kanal.id == KanalStatistik.kanal_id).where(
        Kanal.anlage_id == anlage_id, Kanal.key == sensor_key)
    if vor is not None:
        k = k.where(KanalStatistik.start_ts < int(vor.astimezone(timezone.utc).timestamp()))
    return (await db.execute(k.limit(1))).scalar_one_or_none() is not None


@dataclass(frozen=True)
class Aenderung:
    sensor_key: str
    vorher: Optional[dict]
    nachher: Optional[dict]
    eigene_werte: bool


def _gleich(a: Optional[dict], b: Optional[dict]) -> bool:
    return (a or {}) == (b or {})


async def aenderungen(db, anlage, vorher: dict[str, dict], nachher: dict[str, dict]) -> list[Aenderung]:
    """Die Schlüssel, deren wirksame Quelle sich zwischen ``vorher`` und ``nachher`` ändert — je mit «eigene Werte?».

    Ein Schlüssel, der auf einer Seite fehlt, liest dort den Standard-Inbound. Die Funktion nennt **jede** Änderung samt
    «eigene Werte?»; was davon verzeichnet wird, entscheidet ``verzeichnen.verzeichne`` (nur mit eigenen Werten, §8 Nr. 17)."""
    aus: list[Aenderung] = []
    for key in sorted(set(vorher) | set(nachher)):
        alt = vorher.get(key) or standard_quelle(key)
        neu = nachher.get(key) or standard_quelle(key)
        if _gleich(alt, neu):
            continue
        aus.append(Aenderung(key, alt, neu, await hat_eigene_werte(db, anlage.id, key)))
    return aus
