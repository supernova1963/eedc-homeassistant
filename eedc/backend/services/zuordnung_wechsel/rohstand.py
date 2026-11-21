"""Rand-Stände aus den MQTT-Rohständen — das Laden (Sensorwechsel mit Grund, U3 Lauf b, Rechenweg G5; die Regel steht in
``core/berechnungen/rohstand_rand.py``).

Eine Wechsel-Zeile mit Grund «Fortsetzung», deren Quelle davor und danach MQTT ist (Einstieg «Zähler getauscht», «bleiben»
zwischen zwei MQTT-Quellen — Topic, Gateway-Zeile, Standard-Inbound), bekommt ``ansatz = schnitt``, ``stand_alt_ende`` (letzter
Rohstand vor ``erklaert_ts``) und ``stand_neu_null`` (erster ab ``erklaert_ts``) — wörtlich aus ``mqtt_energy_snapshots``. Wer
sie setzt, hängt davon ab, wann beide Stände vorliegen:

* der Eintrag selbst (``zaehler_getauscht.trage_ein``, ``nachtrag.trage_fortsetzung_ein``), wenn der erste Stand ab dem Wechsel
  schon gespeichert ist;
* sonst der Stundenlauf, der die Naht anwendet (``kanal/naht.zeilen_mit_naehten`` → ``rand_im_stundenlauf``) — mit denselben zwei
  Rohständen, an denen er die Periode teilt; seit Sitzung 5 (Bauplan Nr. 168) nur noch für «bleiben»: «Zähler getauscht» trägt
  erst ein, wenn der neue Zähler gemeldet hat, und setzt die Rand-Stände selbst.

Ohne Rohstände (älter als 31 Tage, ``mqtt_energy_history_service.cleanup_old_snapshots``) bleibt die Zeile ohne Rand-Stände: die
Naht teilt wie vor U3 (benannte Grenze «bis 1 h»). Home Assistant ↔ MQTT bekommt keine Rand-Stände (Entscheid E5).
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import and_, select

from backend.core.berechnungen import rohstand_rand as _rr
from backend.core.berechnungen.rohstand_rand import BEZUG, Roh

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


#: Die Arten von ``sprung_um`` (Bauplan Nr. 166: die Erkennung zeigt, sie entscheidet nicht).
SPRUNG = "sprung"                       # R1: der Stand wechselt in der Stunde eindeutig die Höhe — die Spanne
KEIN_HOEHENWECHSEL = "kein_hoehenwechsel"   # Rohstände da, aber kein Höhenwechsel: Dialog R2, «bleiben» rand_um
NOCH_KEIN_STAND = "noch_kein_stand"     # nach ``t`` noch kein Rohstand («bleiben»: der Stundenlauf setzt die Stände)
OHNE = "ohne"                           # keine Rohstände um ``t`` (älter als 31 Tage): wie vor U3


async def sprung_um(db, anlage_id: int, mqtt_key: str, t: datetime, *, kwh: bool = True
                    ) -> tuple[str, Optional[tuple[Roh, Roh]]]:
    """R1 (Bauplan Nr. 166): wechselt der Zähler in der Stunde von ``t`` eindeutig die Höhe (``rohstand_rand.sprung_der_stunde``
    — Höhenwechsel nach Leistung, U3-K3 A1), ``(SPRUNG, Spanne)`` (U3-K, B1: letzter Stand vor dem ersten, erster nach dem
    letzten Höhenwechsel); sonst ``(KEIN_HOEHENWECHSEL, None)`` · ``(NOCH_KEIN_STAND, None)`` (nach ``t`` ist noch kein Rohstand
    gespeichert) · ``(OHNE, None)`` (keine Rohstände um ``t``). ``kwh``: der Zähler zählt kWh (Grenze B7)."""
    stunde = t.replace(minute=0, second=0, microsecond=0)
    roh = await _rohstaende(db, anlage_id, mqtt_key, stunde - BEZUG, stunde + _STUNDE)
    if not roh:
        return OHNE, None
    if roh[-1][0] < t and await rand_um(db, anlage_id, mqtt_key, t) is None:
        return NOCH_KEIN_STAND, None
    paar = _rr.sprung_der_stunde(roh, stunde, await grenze_kw(db, anlage_id, kwh))
    return (SPRUNG, paar) if paar is not None else (KEIN_HOEHENWECHSEL, None)


async def naechster_anderer_um(db, anlage_id: int, mqtt_key: str, t: datetime) -> Optional[tuple[Roh, Roh]]:
    """R2 (Bauplan Nr. 166/168, Dialog «Zähler getauscht»): der **nächste Rohstand ab ``t`` mit anderem Wert** als der letzte vor
    ``t`` — ohne Zeitgrenze, bis zum letzten gespeicherten Rohstand (ein still wiederholter Stand ist kein Stand des neuen
    Zählers) — und der Rohstand unmittelbar davor (dessen Wert der vor ``t`` ist). ``None``, wenn es vor ``t`` keinen Rohstand
    gibt oder danach (noch) keinen anderen."""
    from backend.models.mqtt_energy_snapshot import MqttEnergySnapshot as S

    vor = await rand_um(db, anlage_id, mqtt_key, t)
    if vor is None:
        return None
    basis = and_(S.anlage_id == anlage_id, S.energy_key == mqtt_key)
    b = (await db.execute(select(S.timestamp, S.value_kwh).where(basis, S.timestamp >= t, S.value_kwh != vor[0][1])
                          .order_by(S.timestamp).limit(1))).one_or_none()
    if b is None:
        return None
    a = (await db.execute(select(S.timestamp, S.value_kwh).where(basis, S.timestamp < b[0])
                          .order_by(S.timestamp.desc()).limit(1))).one()
    return (a[0], float(a[1])), (b[0], float(b[1]))


async def abgehoben_am(db, anlage_id: int, mqtt_key: str, paar: tuple[Roh, Roh], *, kwh: bool = True) -> bool:
    """Hebt sich der Schritt ``paar`` ab (``rohstand_rand.abgehoben`` in der Stunde seines zweiten Stands)? Nur für den Hinweis
    des Dialogs (Bauplan Nr. 166)."""
    stunde = paar[1][0].replace(minute=0, second=0, microsecond=0)
    roh = await _rohstaende(db, anlage_id, mqtt_key, stunde - BEZUG, stunde + _STUNDE)
    g = next((i for i, r in enumerate(roh) if r[0] == paar[1][0]), None)
    return g is not None and g > 0 and _rr.abgehoben(roh, g, await grenze_kw(db, anlage_id, kwh))


async def abgehoben_in_der_stunde(db, anlage_id: int, mqtt_key: str, stunde: datetime, *,
                                  kwh: bool = True) -> Optional[tuple[Roh, Roh]]:
    """Der Schritt der Stunde, der sich abhebt (``rohstand_rand.abgehobener_schritt_der_stunde``), als Paar — für den Befund
    «Zählerstand springt (MQTT)» und den Hinweis von «bleiben»; sonst ``None``."""
    roh = await _rohstaende(db, anlage_id, mqtt_key, stunde - BEZUG, stunde + _STUNDE)
    g = _rr.abgehobener_schritt_der_stunde(roh, stunde, await grenze_kw(db, anlage_id, kwh)) if roh else None
    return None if g is None else (roh[g - 1], roh[g])


async def still_seit(db, anlage_id: int, mqtt_key: str, vor: Roh) -> datetime:
    """U3-K3: seit wann der Stand ``vor`` (der letzte Rohstand vor einem Schritt) unverändert gespeichert ist — der erste
    Rohstand nach dem letzten mit einem anderen Wert (über alle gespeicherten, nicht nur die ``BEZUG``). Liegt er vor ``vor``,
    stand der Stand länger als ein Raster still (der Scheduler hat ihn wiederholt); sonst ist es ``vor`` selbst."""
    from backend.models.mqtt_energy_snapshot import MqttEnergySnapshot as S

    basis = and_(S.anlage_id == anlage_id, S.energy_key == mqtt_key, S.timestamp < vor[0])
    anders = (await db.execute(select(S.timestamp).where(basis, S.value_kwh != vor[1])
                               .order_by(S.timestamp.desc()).limit(1))).scalar_one_or_none()
    erst = select(S.timestamp).where(basis)
    if anders is not None:
        erst = erst.where(S.timestamp > anders)
    seit = (await db.execute(erst.order_by(S.timestamp).limit(1))).scalar_one_or_none()
    return vor[0] if seit is None else seit


async def paar_des_wechsels(db, anlage_id: int, mqtt_key: str, t: datetime) -> Optional[tuple[Roh, Roh]]:
    """Die Rand-Stände eines verzeichneten Wechsels «bleiben» an ``t`` (Nachtrag; Bauplan Nr. 166 R3): R1 — die Spanne der
    Höhenwechsel der Stunde; sonst die zwei Stände um ``t`` (``rand_um``, wie vor U3-K3: ein Schritt anderswo in der Stunde ist
    kein Rand)."""
    art, paar = await sprung_um(db, anlage_id, mqtt_key, t)
    if art == SPRUNG and paar is not None:
        return paar
    return await rand_um(db, anlage_id, mqtt_key, t)


async def rand_der_naht(db, anlage_id: int, mqtt_key: str, e: datetime) -> Optional[tuple[Roh, Roh]]:
    """Die Rand-Stände einer Naht an ``e`` für den Stundenlauf (U3-K, B1; Bauplan Nr. 166/168): endet an ``e`` die Spanne der
    Höhenwechsel der Stunde, deren zwei Rand-Stände — die Stände dazwischen zählen nicht; sonst der letzte Stand vor ``e`` und
    der erste ab ``e`` (``rand_um``). Ein Eintrag «Zähler getauscht» trägt seine Rand-Stände seit Nr. 168 immer selbst (der
    Dialog trägt erst ein, wenn der neue Zähler gemeldet hat); der Stundenlauf setzt sie nur noch für «bleiben»."""
    art, paar = await sprung_um(db, anlage_id, mqtt_key, e)
    if art == SPRUNG and paar is not None and paar[1][0].replace(microsecond=0) == e:
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


#: Bauplan Nr. 166 (Wortlaut des Masters): liegt in der Stunde eines Wechsels «bleiben» zwischen zwei MQTT-Quellen ein Schritt,
#: der sich abhebt, aber nicht im Paar um den Zeitpunkt, nennt die Prüf-Antwort des Nachtrags ihn.
SATZ_BLEIBEN_SCHRITT = ("In dieser Stunde ändert sich der Zählerstand um {zeit} Uhr von {alt} auf {neu} {einheit}. Mit „Bisherige "
                        "Werte bleiben“ zählt eedc diese {menge} {einheit} mit.")


async def satz_bleiben_schritt(db, anlage_id: int, vorher: Optional[dict], nachher: Optional[dict], sensor_key: str,
                               t: Optional[datetime]) -> Optional[str]:
    """``SATZ_BLEIBEN_SCHRITT``, wenn «bleiben» zwischen zwei MQTT-Quellen an ``t`` keinen Höhenwechsel findet (R1) und in der
    Stunde ein Schritt sich abhebt, der nicht im Paar um ``t`` liegt; sonst ``None``."""
    from backend.core.berechnungen.rohstand_rand import menge_des_schritts
    from backend.core.zahlenformat import fmt_zahl

    mk = mqtt_paar(vorher, nachher, sensor_key)
    if mk is None or t is None:
        return None
    art, _ = await sprung_um(db, anlage_id, mk, t)
    if art != KEIN_HOEHENWECHSEL:
        return None
    schritt = await abgehoben_in_der_stunde(db, anlage_id, mk, t.replace(minute=0, second=0, microsecond=0))
    um = await rand_um(db, anlage_id, mk, t)
    if schritt is None or (um is not None and schritt[1][0] == um[1][0]):
        return None
    from backend.services.kanal.angaben import kanal_des_schluessels

    kanal = await kanal_des_schluessels(db, anlage_id, sensor_key)          # Bauplan Nr. 167: die Einheit des Felds
    return SATZ_BLEIBEN_SCHRITT.format(zeit=schritt[1][0].strftime("%d.%m.%Y %H:%M"), alt=fmt_zahl(schritt[0][1], 2),
                                       neu=fmt_zahl(schritt[1][1], 2), menge=fmt_zahl(menge_des_schritts(schritt), 2),
                                       einheit=(kanal.einheit if kanal is not None and kanal.einheit else "kWh"))


def bleiben_satz(vorher: Optional[dict], nachher: Optional[dict], sensor_key: str) -> Optional[str]:
    """Der Satz zu «bleiben» für die Prüf-Antwort: MQTT → MQTT ``SATZ_BLEIBEN_MQTT``, Home Assistant ↔ MQTT
    ``SATZ_BLEIBEN_HA_MQTT``; sonst ``None`` (zwischen zwei HA-Sensoren sagt es ``bleiben``, ohne Quelle gibt es nichts)."""
    arten = {(q or {}).get("art") for q in (vorher, nachher)}
    if mqtt_paar(vorher, nachher, sensor_key) is not None:
        return SATZ_BLEIBEN_MQTT
    return SATZ_BLEIBEN_HA_MQTT if arten == {"ha", "mqtt"} else None


__all__ = ["KEIN_HOEHENWECHSEL", "NOCH_KEIN_STAND", "OHNE", "SATZ_BLEIBEN_HA_MQTT", "SATZ_BLEIBEN_MQTT", "SATZ_BLEIBEN_SCHRITT",
           "SPRUNG", "abgehoben_am", "abgehoben_in_der_stunde", "bleiben_satz", "grenze_kw",
           "mqtt_key_der_quelle", "mqtt_paar", "naechster_anderer_um", "paar_des_wechsels", "rand_der_naht",
           "rand_im_stundenlauf", "rand_um", "satz_bleiben_schritt", "setze_rand", "sprung_um", "still_seit"]
