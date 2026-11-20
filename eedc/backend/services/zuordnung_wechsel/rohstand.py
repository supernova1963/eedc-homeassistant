"""Rand-Stände aus den MQTT-Rohständen — das Laden (Sensorwechsel mit Grund, U3 Lauf b, Rechenweg G5; die Regel steht in
``core/berechnungen/rohstand_rand.py``).

Eine Wechsel-Zeile mit Grund «Fortsetzung», deren Quelle davor und danach MQTT ist (Einstieg «Zähler getauscht», «bleiben»
zwischen zwei MQTT-Quellen — Topic, Gateway-Zeile, Standard-Inbound), bekommt ``ansatz = schnitt``, ``stand_alt_ende`` (letzter
Rohstand vor ``erklaert_ts``) und ``stand_neu_null`` (erster ab ``erklaert_ts``) — wörtlich aus ``mqtt_energy_snapshots``. Wer
sie setzt, hängt davon ab, wann beide Stände vorliegen:

* der Eintrag selbst (``zaehler_getauscht.trage_ein``, ``nachtrag.trage_fortsetzung_ein``), wenn der erste Stand ab dem Wechsel
  schon gespeichert ist;
* sonst der Stundenlauf, der die Naht anwendet (``kanal/naht.zeilen_mit_naehten`` → ``rand_im_stundenlauf``) — mit denselben zwei
  Rohständen, an denen er die Periode teilt.

Ohne Rohstände (älter als 31 Tage, ``mqtt_energy_history_service.cleanup_old_snapshots``) bleibt die Zeile ohne Rand-Stände: die
Naht teilt wie vor U3 (benannte Grenze «bis 1 h»). Home Assistant ↔ MQTT bekommt keine Rand-Stände (Entscheid E5).
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import and_, select

from backend.core.berechnungen.rohstand_rand import BEZUG, Roh, sprung_der_stunde

_STUNDE = timedelta(hours=1)


def mqtt_key_der_quelle(quelle: Optional[dict], sensor_key: str) -> Optional[str]:
    """Der MQTT-Schlüssel einer Quelle ``{"art": "mqtt", …}`` (sonst ``None``)."""
    from backend.services.snapshot.keys import _sensor_key_to_mqtt_key

    if not isinstance(quelle, dict) or quelle.get("art") != "mqtt":
        return None
    return quelle.get("mqtt_key") or _sensor_key_to_mqtt_key(sensor_key)


def mqtt_paar(vorher: Optional[dict], nachher: Optional[dict], sensor_key: str) -> Optional[str]:
    """Davor und danach MQTT auf demselben Schlüssel (der Rohstand beider Quellen steht unter ihm): der Schlüssel, sonst ``None``."""
    a, b = mqtt_key_der_quelle(vorher, sensor_key), mqtt_key_der_quelle(nachher, sensor_key)
    return a if a is not None and a == b else None


async def _rohstaende(db, anlage_id: int, mqtt_key: str, von: datetime, bis: datetime) -> list[Roh]:
    from backend.models.mqtt_energy_snapshot import MqttEnergySnapshot as S

    return [(t, float(w)) for t, w in (await db.execute(select(S.timestamp, S.value_kwh).where(and_(
        S.anlage_id == anlage_id, S.energy_key == mqtt_key, S.timestamp >= von, S.timestamp < bis,
    )).order_by(S.timestamp))).all()]


async def rand_um(db, anlage_id: int, mqtt_key: str, t: datetime) -> Optional[tuple[Roh, Roh]]:
    """``(letzter Rohstand vor t, erster ab t)`` — beide nötig, sonst ``None`` (nie interpoliert)."""
    from backend.models.mqtt_energy_snapshot import MqttEnergySnapshot as S

    basis = and_(S.anlage_id == anlage_id, S.energy_key == mqtt_key)
    a = (await db.execute(select(S.timestamp, S.value_kwh).where(basis, S.timestamp < t)
                          .order_by(S.timestamp.desc()).limit(1))).one_or_none()
    b = (await db.execute(select(S.timestamp, S.value_kwh).where(basis, S.timestamp >= t)
                          .order_by(S.timestamp).limit(1))).one_or_none()
    if a is None or b is None:
        return None
    return (a[0], float(a[1])), (b[0], float(b[1]))


async def grenze_kw(db, anlage_id: int, kwh: bool = True) -> Optional[float]:
    """Die Grenze «mehr, als eine Anlage in einer Stunde leisten kann» als Leistung (U3-K, B7; dieselbe Grenze wie der Befund
    «Zählerstand springt» B2 (b)); ``None`` für einen Zähler in einer anderen Einheit als kWh."""
    from backend.core.berechnungen.zaehlerstand_sprung import grenze_unmoeglich
    from backend.services.snapshot.plausibility import schwelle_der_anlage_stunde_kwh

    return grenze_unmoeglich(await schwelle_der_anlage_stunde_kwh(db, anlage_id)) if kwh else None


async def sprung_um(db, anlage_id: int, mqtt_key: str, t: datetime, *, kwh: bool = True,
                    benannt: Optional[bool] = None) -> tuple[str, Optional[tuple[Roh, Roh]]]:
    """Wo der Zähler um ``t`` die Höhe wechselt (``rohstand_rand.sprung_der_stunde`` in der Stunde von ``t``):
    ``("sprung", (a, b))`` — die Spanne der Höhenwechsel der Stunde (U3-K, B1: letzter Stand vor dem ersten, erster nach dem
    letzten) · ``("kein_sprung", None)`` (Rohstände in der Stunde, aber kein Höhenwechsel) · ``("noch_kein_stand", None)`` (nach
    ``t`` ist noch kein Rohstand gespeichert — der Stundenlauf setzt die Rand-Stände später) · ``("ohne", None)`` (keine
    Rohstände um ``t``: älter als 31 Tage oder nie gespeichert — wie vor U3). ``kwh``: der Zähler zählt kWh (Grenze B7).
    ``benannt`` (U3-K2, P-3): nennt der Befund «Zählerstand springt (MQTT)» die Stunde? ``None`` = erst fragen, wenn die
    Leistung keinen Höhenwechsel sieht (``stunde_benannt``) — dann ist der größte Schritt nach oben der Stunde der Höhenwechsel."""
    stunde = t.replace(minute=0, second=0, microsecond=0)
    roh = await _rohstaende(db, anlage_id, mqtt_key, stunde - BEZUG, stunde + _STUNDE)
    if not roh:
        return "ohne", None
    if roh[-1][0] < t and await rand_um(db, anlage_id, mqtt_key, t) is None:
        return "noch_kein_stand", None
    grenze = await grenze_kw(db, anlage_id, kwh)
    paar = sprung_der_stunde(roh, stunde, grenze)
    if paar is None and (benannt if benannt is not None else await stunde_benannt(db, anlage_id, mqtt_key, stunde)):
        paar = sprung_der_stunde(roh, stunde, grenze, benannt=True)
    return ("sprung", paar) if paar is not None else ("kein_sprung", None)


async def stunde_benannt(db, anlage_id: int, mqtt_key: str, stunde: datetime) -> bool:
    """U3-K2 (P-3): nennt der Befund «Zählerstand springt (MQTT)» (``mqtt_standsprung.mqtt_spruenge``, Kern
    ``zaehlerstand_sprung.finde_standspruenge``) die Kanal-Stunde ``stunde`` dieses MQTT-Schlüssels?"""
    from backend.services.daten_checker.datenquelle.mqtt_standsprung import mqtt_spruenge

    ts = int(stunde.timestamp())
    return any(f.mqtt_key == mqtt_key and f.sprung.start_ts == ts for f in await mqtt_spruenge(db, anlage_id))


async def rand_der_naht(db, anlage_id: int, mqtt_key: str, e: datetime) -> Optional[tuple[Roh, Roh]]:
    """Die Rand-Stände einer Naht an ``e`` für den Stundenlauf (U3-K, B1): endet an ``e`` die Spanne der Höhenwechsel der Stunde
    (``sprung_um``: ihr erster Stand danach liegt genau an ``e``), deren zwei Rand-Stände — die Stände dazwischen zählen nicht;
    sonst der letzte Stand vor ``e`` und der erste ab ``e`` (``rand_um``)."""
    art, paar = await sprung_um(db, anlage_id, mqtt_key, e)
    if art == "sprung" and paar is not None and paar[1][0].replace(microsecond=0) == e:
        return paar
    return await rand_um(db, anlage_id, mqtt_key, e)


def setze_rand(row, paar: tuple[Roh, Roh]) -> None:
    """Rand-Stände an die Wechsel-Zeile (``ansatz = schnitt``; die Reihe hebt über ``zeitpunkt.rand_versatz``)."""
    from backend.models.zuordnung_wechsel import ANSATZ_SCHNITT

    row.ansatz, row.stand_alt_ende, row.stand_neu_null = ANSATZ_SCHNITT, paar[0][1], paar[1][1]


async def rand_im_stundenlauf(db, anlage_id: int, sensor_key: str, mqtt_key: str, erklaert: datetime,
                              paar: Optional[tuple[Roh, Roh]]) -> None:
    """Der Stundenlauf wendet die Naht an ``erklaert`` an: jede gültige Fortsetzung des Schlüssels mit dieser Sekunde, beiden
    Quellen auf diesem MQTT-Schlüssel und noch ohne Rand-Stände bekommt ``paar`` — die Rand-Stände, an denen der Lauf teilt
    (``rand_der_naht``)."""
    from backend.models.zuordnung_wechsel import GRUND_FORTSETZUNG, ZuordnungWechsel
    from backend.services.kanal import merken
    from backend.services.zuordnung_wechsel.zeitpunkt import vergiss

    zeilen = (await db.execute(select(ZuordnungWechsel).where(and_(
        ZuordnungWechsel.anlage_id == anlage_id, ZuordnungWechsel.sensor_key == sensor_key,
        ZuordnungWechsel.grund == GRUND_FORTSETZUNG, ZuordnungWechsel.aufgehoben_durch.is_(None),
        ZuordnungWechsel.erklaert_ts == erklaert, ZuordnungWechsel.ansatz.is_(None),
    )))).scalars().all()
    zeilen = [z for z in zeilen if mqtt_paar(z.vorher, z.nachher, sensor_key) == mqtt_key]
    if not zeilen:
        return
    if paar is None:
        return
    for z in zeilen:
        setze_rand(z, paar)
    await db.flush()
    vergiss(db, anlage_id)
    merken.invalidiere(anlage_id, von=erklaert.date() - timedelta(days=1), db=db)


#: Was «Bisherige Werte bleiben» tut, wenn die Quelle davor und danach MQTT ist (U3 b, G5) — der Dialog zeigt es statt des
#: allgemeinen Satzes (Prüf-Antwort ``bleiben_satz``).
SATZ_BLEIBEN_MQTT = ("Die bisherigen Werte bleiben, und der Unterschied zwischen altem und neuem Zählerstand zählt nicht als "
                     "Menge. Die Stunde des Wechsels zählt, was die bisherige Quelle bis zu ihrem letzten Zählerstand und die "
                     "neue ab ihrem ersten gemeldet hat.")
#: Home Assistant ↔ MQTT (Entscheid E5): wie bisher, und die Prüf-Antwort sagt es.
SATZ_BLEIBEN_HA_MQTT = ("Zwischen einem Sensor aus Home Assistant und MQTT rechnet eedc den Wechsel wie bisher: die bisherigen "
                        "Werte bleiben, der Unterschied zwischen altem und neuem Zählerstand zählt nicht als Menge, und wo eedc "
                        "aus den gespeicherten Zählerständen rechnet, zählt die Stunde des Wechsels keinen Zuwachs.")


def bleiben_satz(vorher: Optional[dict], nachher: Optional[dict], sensor_key: str) -> Optional[str]:
    """Der Satz zu «bleiben» für die Prüf-Antwort: MQTT → MQTT ``SATZ_BLEIBEN_MQTT``, Home Assistant ↔ MQTT
    ``SATZ_BLEIBEN_HA_MQTT``; sonst ``None`` (zwischen zwei HA-Sensoren sagt es ``bleiben``, ohne Quelle gibt es nichts)."""
    arten = {(q or {}).get("art") for q in (vorher, nachher)}
    if mqtt_paar(vorher, nachher, sensor_key) is not None:
        return SATZ_BLEIBEN_MQTT
    return SATZ_BLEIBEN_HA_MQTT if arten == {"ha", "mqtt"} else None


__all__ = ["SATZ_BLEIBEN_HA_MQTT", "SATZ_BLEIBEN_MQTT", "bleiben_satz", "grenze_kw", "mqtt_key_der_quelle", "mqtt_paar",
           "rand_der_naht", "rand_im_stundenlauf", "rand_um", "setze_rand", "sprung_um", "stunde_benannt"]
