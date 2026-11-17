"""B-0 an den Schreibern der Zählerstand-Reihe: **kein Schreiber setzt für einen Zeitpunkt den Stand einer anderen Quelle**, und
gilt um den Zeitpunkt nicht die heutige Quelle, **füllt er nur fehlende Zeilen** — eine vorhandene wird weder überschrieben noch
gelöscht (Bauplan §8 Nr. 16; die Bedingung steht in ``snapshot/writer.py``, die Werkbank-Vorschau zeigt dasselbe, ``vorschau_quelle``).

Eingehängt (Auftrag Sitzung 1, Teil E): ``snapshot/writer.py`` (``_build_counter_map(…, zeitpunkt=, wechsel=)``,
``snapshot_anlage`` samt MQTT-Schritt, ``snapshot_anlage_5min``) — darüber ``reaggregator.resnap_anlage_range`` («Tag neu
aggregieren», Bereich, Diagnose-Resnap) und die Startup-Recovery (``scheduler.sensor_snapshot_startup_recovery``) —,
``snapshot/reader.get_snapshot`` (Heilen eines fehlenden Randes), ``snapshot/fallback.live_snapshot_if_missing`` und
``snapshot/lts_aggregator.lts_tagestabelle`` (je Tag, über ``aggregate_day``).

Ohne verzeichneten Wechsel liefern alle Funktionen hier «wie heute» — die heutige Zuordnung gilt für jeden Zeitpunkt.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Optional

from backend.services.zuordnung_wechsel.quelle import ART_HA, ART_MQTT
from backend.services.zuordnung_wechsel.zeitpunkt import HEUTE, UNBEKANNT, Antwort, Wechsel, quelle_am, zuordnung_am


def counter_map_zum_zeitpunkt(
    heute: dict[str, str], wechsel: Optional[dict[str, list[Wechsel]]], zeitpunkt: datetime, stillgelegt: set[str],
) -> dict[str, str]:
    """Die HA-Schreib-Map für ``zeitpunkt``: je Schlüssel mit einer anderen Quelle als heute deren HA-Entität — oder der
    Schlüssel fällt heraus (Quelle MQTT, «keine» oder unbekannt). In-place auf ``heute`` und zurückgegeben."""
    for key, antwort in zuordnung_am(wechsel, zeitpunkt).items():
        if key.startswith("inv:") and key.split(":")[1] in stillgelegt:
            continue
        if isinstance(antwort, dict) and antwort.get("art") == ART_HA and antwort.get("entity_id"):
            heute[key] = antwort["entity_id"]
        else:
            heute.pop(key, None)
    return heute


def mqtt_zum_zeitpunkt(antwort: Antwort) -> Optional[bool]:
    """MQTT-Schritt eines Schlüssels: ``None`` = heutige Regel anwenden; ``True`` = galt MQTT, schreiben erlaubt; ``False`` =
    eine andere oder unbekannte Quelle galt ⇒ nicht aus MQTT schreiben."""
    if antwort is HEUTE:
        return None
    return isinstance(antwort, dict) and antwort.get("art") == ART_MQTT


def heil_quelle(antwort: Antwort, sensor_id: Optional[str]) -> tuple[bool, Optional[str], bool]:
    """Wie ein fehlender Rand geheilt werden darf: ``(heilen, ha_entitaet, mqtt_erlaubt)``.

    ``HEUTE`` ⇒ wie bisher (``sensor_id`` und der MQTT-Rückfall). Eine andere Quelle ⇒ nur aus ihr: HA-Entität ohne
    MQTT-Rückfall, MQTT ohne HA. Unbekannt oder «keine» ⇒ nicht heilen."""
    if antwort is HEUTE:
        return True, sensor_id, True
    if antwort is UNBEKANNT or not isinstance(antwort, dict):
        return False, None, False
    if antwort.get("art") == ART_HA and antwort.get("entity_id"):
        return True, antwort["entity_id"], False
    if antwort.get("art") == ART_MQTT:
        return True, None, True
    return False, None, False


def vorschau_quelle(antwort: Antwort, heute_eid: Optional[str], alt: Optional[float]) -> tuple[bool, Optional[str]]:
    """Werkbank-Vorschau = Lauf (Bauplan §8 Nr. 19): ``(bleibt, ha_entitaet)`` für eine Stunden-Grenze.

    ``HEUTE`` ⇒ ``(False, heute_eid)`` wie bisher. Sonst (vor einem verzeichneten Wechsel, §8 Nr. 16): eine vorhandene Zeile
    bleibt (``True``); eine fehlende füllt der Lauf aus einer früheren HA-Entität, aus MQTT, «keine» oder unbekannt nicht aus HA."""
    if antwort is HEUTE:
        return False, heute_eid
    if alt is not None:
        return True, None
    if isinstance(antwort, dict) and antwort.get("art") == ART_HA and antwort.get("entity_id"):
        return False, antwort["entity_id"]
    return False, None


def entitaet_je_slot(
    liste: Optional[list[Wechsel]], heute_eid: str, datum: date, slots,
) -> Optional[dict[int, str]]:
    """LTS-Tag: je Slot ``h`` (Stand um ``datum`` + ``h`` Stunden) die HA-Entität der Quelle zu diesem Stand.

    ``{}`` = alle Slots heute (nichts zu tun); ``None`` = ein Slot gehört einer Quelle, die nicht aus HA kommt oder unbekannt
    ist ⇒ der Tag liest nicht aus HA (Rückfall auf den Snapshot-Pfad, dessen Reihe B-0 schützt)."""
    if not liste:
        return {}
    null = datetime.combine(datum, datetime.min.time())
    aus: dict[int, str] = {}
    for h in slots:
        antwort = quelle_am(liste, null + timedelta(hours=h))
        if antwort is HEUTE:
            continue
        if not (isinstance(antwort, dict) and antwort.get("art") == ART_HA and antwort.get("entity_id")):
            return None
        if antwort["entity_id"] != heute_eid:
            aus[h] = antwort["entity_id"]
    return aus
