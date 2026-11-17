"""Überführung der Wechsel aus dem Aktivitäts-Protokoll (``herkunft = altbestand``) — Auftrag Sitzung 1, Teil D.

Seit dem 25.09.2026 trägt jeder Eintrag ``kategorie = sensor_mapping`` der Feld-Route ``details_json = {field_id, vorher,
nachher}`` (die ``quellen``-Einträge vor und nach der Änderung, ``api/routes/datenquellen.py::set_feld_quelle``) mit Zeit. Jeder
Eintrag, der **sicher** eine wirksame Änderung eines Zählerschlüssels mit eigenen Werten war, wird eine Zeile (``erklaert_ts`` =
Zeit des Eintrags, ``grund`` leer) — **alle** solchen Einträge, nicht nur die Felder des Hinweis-Vermerks, damit B-0 auch die
Vergangenheit schützt.

**Nicht jeder Eintrag ist eine wirksame Änderung** (Messblatt S0 M-H): das Protokoll-``vorher`` ist der ``quellen``-Eintrag, nicht
die wirksame Quelle — leer heißt «kein Eintrag», und dahinter kann eine klassische HA-Zuordnung stehen. Ein leeres ``vorher`` wird
deshalb am Kanal aufgelöst (``kanal_quelle``, die vor der Stunde des Eintrags galt: Familie ``spiegel`` = HA-Entität, ``mitschrift``
= MQTT) und sonst an der letzten Zeile der Reihe davor (``sensor_snapshots.quelle``). Was danach nicht sicher eine wirksame
Änderung war, wird **nicht** überführt; ``ueberfuehre`` zählt je Grund (Rückgabe, Log).

Idempotent zweifach: als Start-Migration läuft sie einmal je Installation (``core/database.py::_run_data_migrations``), und sie
legt keine zweite Zeile mit gleicher Anlage, gleichem Schlüssel und gleicher Zeit an.
"""

from __future__ import annotations

import logging
from collections import Counter
from datetime import datetime
from typing import Optional

from sqlalchemy import select

from backend.models.zuordnung_wechsel import HERKUNFT_ALTBESTAND, ZuordnungWechsel
from backend.services.snapshot.keys import (
    QUELLE_HA_ENERGY,
    QUELLE_KEINE_ENERGY,
    _energy_field_id_to_sensor_key,
    _sensor_key_to_mqtt_key,
)
from backend.services.zuordnung_wechsel.quelle import ART_HA, ART_KEINE, ART_MQTT, hat_eigene_werte, standard_quelle
from backend.services.zuordnung_wechsel.zeitpunkt import ab_ts_aus, vergiss

logger = logging.getLogger(__name__)

#: Gründe, aus denen ein Protokoll-Eintrag NICHT überführt wird (Zählung im Bericht).
GRUND_KEIN_ZAEHLER = "kein_zaehlerschluessel"
GRUND_GERAET_FEHLT = "geraet_geloescht"
GRUND_UNVERAENDERT = "wirksam_unveraendert"
GRUND_UNSICHER = "vorher_unbekannt"
GRUND_OHNE_WERTE = "ohne_eigene_werte"
GRUND_SCHON_DA = "schon_ueberfuehrt"
UEBERFUEHRT = "ueberfuehrt"


def _aus_eintrag(sensor_key: str, eintrag) -> Optional[dict]:
    """Ein ``quellen``-Eintrag des Protokolls als wirksame Quelle — ``None``, wenn er sie nicht festlegt (kein Eintrag)."""
    if not isinstance(eintrag, dict) or not eintrag.get("quelle"):
        return None
    quelle = eintrag["quelle"]
    if quelle in QUELLE_HA_ENERGY:
        return {"art": ART_HA, "entity_id": eintrag.get("entity_id")} if eintrag.get("entity_id") else None
    if quelle == QUELLE_KEINE_ENERGY:
        return {"art": ART_KEINE}
    if quelle == "mqtt_gateway":
        # Topic der damaligen Gateway-Zeile unbekannt (die Zeile kann sich seither geändert haben) — der Schlüssel fehlt.
        return {"art": ART_MQTT, "mqtt_key": _sensor_key_to_mqtt_key(sensor_key)}
    return standard_quelle(sensor_key)  # mqtt_inbound_standard (Stempel der Materialisierung)


async def _vorher_aus_kanal(db, anlage_id: int, sensor_key: str, ts: datetime) -> Optional[dict]:
    """Die Quelle des Kanals **vor** dem Eintrag: größtes ``gueltig_ab`` vor der Stunde von ``ts`` (Bauplan §8 Nr. 21 — die
    neue Quelle trägt die Stunde des Wechsels selbst: Änderung 10:47 ⇒ ``gueltig_ab`` 10:00)."""
    from backend.models.kanal import FAMILIE_MITSCHRIFT, FAMILIE_SPIEGEL, Kanal, KanalQuelle

    stunde = ts.replace(minute=0, second=0, microsecond=0)
    row = (await db.execute(
        select(KanalQuelle.familie, KanalQuelle.statistic_id)
        .join(Kanal, Kanal.id == KanalQuelle.kanal_id)
        .where(Kanal.anlage_id == anlage_id, Kanal.key == sensor_key, KanalQuelle.gueltig_ab < int(stunde.timestamp()))
        .order_by(KanalQuelle.gueltig_ab.desc()).limit(1)
    )).first()
    if row is None:
        return None
    familie, statistic_id = row
    if familie == FAMILIE_SPIEGEL and statistic_id:
        return {"art": ART_HA, "entity_id": statistic_id}
    if familie == FAMILIE_MITSCHRIFT:
        return {"art": ART_MQTT, "mqtt_key": _sensor_key_to_mqtt_key(sensor_key)}
    return None


async def _vorher_aus_reihe(db, anlage_id: int, sensor_key: str, ts: datetime) -> Optional[dict]:
    """Die Art der letzten Zeile der Reihe vor ``ts`` (Entität unbekannt)."""
    from backend.models.sensor_snapshot import SensorSnapshot

    quelle = (await db.execute(
        select(SensorSnapshot.quelle)
        .where(SensorSnapshot.anlage_id == anlage_id, SensorSnapshot.sensor_key == sensor_key,
               SensorSnapshot.zeitpunkt < ts)
        .order_by(SensorSnapshot.zeitpunkt.desc()).limit(1)
    )).scalar_one_or_none()
    if quelle == "ha_statistics":
        return {"art": ART_HA}
    if quelle in ("mqtt_inbound", "mqtt_live"):
        return {"art": ART_MQTT, "mqtt_key": _sensor_key_to_mqtt_key(sensor_key)}
    return None


def _sicher_verschieden(alt: dict, neu: dict) -> Optional[bool]:
    """``True`` sicher verschieden, ``False`` sicher gleich, ``None`` nicht entscheidbar (Entität oder Topic fehlt)."""
    if alt.get("art") != neu.get("art"):
        return True
    if alt["art"] == ART_KEINE:
        return False
    if alt["art"] == ART_HA:
        if not alt.get("entity_id") or not neu.get("entity_id"):
            return None
        return alt["entity_id"] != neu["entity_id"]
    if "topic" not in alt or "topic" not in neu:
        return None
    return alt.get("topic") != neu.get("topic")


async def _bewerte(db, eintrag, sensor_key: str) -> tuple[str, Optional[dict], Optional[dict]]:
    dj = eintrag.details_json
    neu = _aus_eintrag(sensor_key, dj.get("nachher")) or standard_quelle(sensor_key)
    alt = _aus_eintrag(sensor_key, dj.get("vorher"))
    if alt is None:  # kein `quellen`-Eintrag vorher: am Kanal bzw. an der Reihe auflösen
        alt = (await _vorher_aus_kanal(db, eintrag.anlage_id, sensor_key, eintrag.timestamp)
               or await _vorher_aus_reihe(db, eintrag.anlage_id, sensor_key, eintrag.timestamp))
    if alt is None:
        return GRUND_UNSICHER, None, neu
    verschieden = _sicher_verschieden(alt, neu)
    if verschieden is None:
        return GRUND_UNSICHER, alt, neu
    if not verschieden:
        return GRUND_UNVERAENDERT, alt, neu
    stunde = eintrag.timestamp.replace(minute=0, second=0, microsecond=0)
    if not await hat_eigene_werte(db, eintrag.anlage_id, sensor_key, vor=stunde):
        return GRUND_OHNE_WERTE, alt, neu
    return UEBERFUEHRT, alt, neu


async def _geraet_da(db, anlage_id: int, sensor_key: str) -> bool:
    from backend.models.investition import Investition

    if not sensor_key.startswith("inv:"):
        return True
    inv_id = sensor_key.split(":")[1]
    return inv_id.isdigit() and (await db.execute(select(Investition.id).where(
        Investition.id == int(inv_id), Investition.anlage_id == anlage_id))).scalar_one_or_none() is not None


async def ueberfuehre(db) -> Counter:
    """Überführt die Protokoll-Einträge (``flush``, kein Commit). Rückgabe: Zählung je Ergebnis (``ueberfuehrt`` oder Grund)."""
    from backend.models.activity_log import ActivityLog

    zaehlung: Counter = Counter()
    eintraege = (await db.execute(
        select(ActivityLog).where(ActivityLog.kategorie == "sensor_mapping", ActivityLog.anlage_id.isnot(None))
        .order_by(ActivityLog.timestamp, ActivityLog.id)
    )).scalars().all()
    for e in eintraege:
        dj = e.details_json if isinstance(e.details_json, dict) else {}
        field_id = dj.get("field_id")
        if not isinstance(field_id, str) or "vorher" not in dj or isinstance(dj.get("vorher"), bool) \
                or isinstance(dj.get("nachher"), bool):
            continue  # kein Quellen-Eintrag (Vorzeichen, Sammelzeile der Energie-Vorschläge)
        sensor_key = _energy_field_id_to_sensor_key(field_id)
        if sensor_key is None:
            ergebnis, alt, neu = GRUND_KEIN_ZAEHLER, None, None
        elif not await _geraet_da(db, e.anlage_id, sensor_key):
            ergebnis, alt, neu = GRUND_GERAET_FEHLT, None, None   # sonst erbte die nächste Investition dieser ID den Wechsel
        else:
            ergebnis, alt, neu = await _bewerte(db, e, sensor_key)
        if ergebnis == UEBERFUEHRT and (await db.execute(select(ZuordnungWechsel.id).where(
                ZuordnungWechsel.anlage_id == e.anlage_id, ZuordnungWechsel.sensor_key == sensor_key,
                ZuordnungWechsel.erklaert_ts == e.timestamp.replace(microsecond=0)))).first() is not None:
            ergebnis = GRUND_SCHON_DA
        zaehlung[ergebnis] += 1
        if ergebnis != UEBERFUEHRT:
            logger.debug("Überführung: Protokoll %s (%s, %s) nicht überführt: %s", e.id, field_id, e.timestamp, ergebnis)
            continue
        erklaert = e.timestamp.replace(microsecond=0)
        db.add(ZuordnungWechsel(
            anlage_id=e.anlage_id, sensor_key=sensor_key, erklaert_ts=erklaert, ab_ts=ab_ts_aus(erklaert),
            vorher=alt, nachher=neu, grund=None, herkunft=HERKUNFT_ALTBESTAND,
        ))
        await db.flush()
    vergiss(db)
    logger.info("Sensorwechsel: Überführung aus dem Protokoll — %s", dict(sorted(zaehlung.items())))
    return zaehlung


async def ueberfuehre_altbestand(session) -> None:
    """Start-Migration (``_apply_once``): Commit macht der Aufrufer."""
    await ueberfuehre(session)
