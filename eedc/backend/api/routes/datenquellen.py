"""
Datenquellen-Zuordnung — feld-zentrische Fläche (Datenquellen-V4 / B2).

SoT: docs/KONZEPT-DATENQUELLEN-V4.md §2b.

Liefert je Anlage die vollständige, gruppierte eedc-Feldliste (Anlage-Basis +
je aktiver Investition, Live + Energie) mit dem kanonischen Standard-Inbound-
Topic pro Feld. Grundlage für die „eine Quelle pro Feld"-Zuordnung.

**B2.1 (read-only):** nur Enumeration + Standard-Topic. Der Quell-Picker
(Wechsel MQTT-Inbound/Gateway/keine · HA-Sensor) und die Persistenz folgen in
B2.2/B5. Die aktive Quelle ist daher vorerst konstant der Standard-Inbound-Pfad.
"""

import asyncio
import copy
import json as json_mod
import logging
from datetime import date, datetime, timezone

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps import get_db
from backend.services.activity_service import log_activity
from backend.services.datenquellen_mapping_sync import feld_id
from backend.core.ha_integrations_wissen import analysiere_vorschlaege
from backend.models.anlage import Anlage
from backend.models.investition import Investition
from backend.services.datenquellen_historie import (
    ist_echte_aenderung,
    vermerk_ergaenzen,
    vermerk_leeren,
    vermerk_lesen,
)
from backend.core.field_definitions import (
    basis_feld_key,
    ist_zustand_feld,
)
from backend.services.live_sensor_config import (
    entferne_legacy_invert,
    legacy_invert_aktiv,
)
from backend.services.mqtt_topic_registry import build_expected_topics
from backend.services.mqtt_broker_settings import import_aktiviert
from backend.utils.investition_filter import aktiv_am_tag, sort_investitionen_nach_typ
# Schnitt `zuordnungen_lesen` (E1, 10.11.2026): die vier lesenden /felder-Phasen samt Helfern leben im Service; hier stehen
# die Namen, die diese Route und ihre Nachbarn (`datenquellen_themen.py`, Tests) weiter von hier beziehen.
from backend.services.datenquellen_felder import (  # noqa: F401 — Re-Export für Nachbarn und Tests
    QUELLE_GATEWAY,
    QUELLE_HA_APP,
    QUELLE_HA_CONNECTOR,
    QUELLE_KEINE,
    QUELLE_STANDARD,
    QUELLEN_HA,
    QUELLEN_KEY,
    FelderKontext,
    _basis_preis_eintraege,
    _feld_id,
    _ha_states_detail,
    _quellen_map,
    _resolve_ha,
    _themen_gruppe,
    _wert_klartext,
    _zulaessige_werte,
    ohne_nicht_zuordenbare,
    zuordnungen_lesen,
)

logger = logging.getLogger(__name__)

router = APIRouter()

QUELLEN_ERLAUBT = {QUELLE_STANDARD, QUELLE_KEINE, QUELLE_GATEWAY, QUELLE_HA_APP, QUELLE_HA_CONNECTOR}


# ─── HA-Verbindung auflösen (Supervisor bevorzugt, sonst Remote-HA) ──────
def _is_int_state(v) -> bool:
    try:
        int(str(v).strip())
        return True
    except (ValueError, TypeError):
        return False


async def _mqtt_import_aktiviert(db: AsyncSession) -> bool:
    """True, wenn Daten über MQTT EMPFANGEN werden (Import-Richtung) — nur dann
    sind Gateway/Inbound als Feld-Quelle sinnvoll.

    B7-5c: fragt bewusst die **Import-Richtung** ab, nicht mehr „ist der Broker
    aktiv". Seit die Richtungen getrennt sind, kann die Verbindung allein für den
    **Export** stehen („nur Export" = Default der HA App) — dann darf die Fläche
    keine MQTT-Quellen anbieten, obwohl der Broker verbunden ist. Genau das war
    Gernots Anforderung: auf der HA App nur HA-Sensor + Keine.

    Einstellungs-, nicht prozessbasiert (ein beim Boot verbundener Service darf
    die Optionen nicht offen halten). HA-Seite analog via `resolve_ha_connection`.
    """
    return await import_aktiviert(db)


# Energie-relevanter Sensor-Filter (Symmetrie zu sensor_mapping.available-sensors).
_HA_UNITS = {
    "kWh", "Wh", "W", "kW", "km", "°C", "%",
    "EUR/kWh", "ct/kWh", "€/kWh", "EUR/MWh", "€/MWh", "€", "EUR", "ct", "Cent",
}
_HA_DEVICE_CLASSES = {"energy", "power", "battery", "temperature", "distance", "monetary"}


def _ha_sensor_relevant(
    state: dict, filter_energy: bool, zustand: bool = False, domaenen: tuple[str, ...] | None = None,
    alle: bool = False,
) -> bool:
    """Gehört diese HA-Entity in den Picker für dieses Feld?

    ⚠ **`zustand=True` ist keine Bequemlichkeit, sondern die Bedingung dafür,
    dass #263 K-2 überhaupt bedienbar ist.** Der Betriebsmodus einer
    Klimaanlage liegt in HA als eigene **`climate`**-Entität vor (Konzept D1,
    an kingcap1s MELCloud-Installation belegt) — der Domain-Test darunter hat
    sie bis dahin unbedingt verworfen, auch bei `filter_energy=false`, weil er
    **vor** dessen Auswertung steht. Ohne diese Freigabe könnte ein Anwender
    den Modus-Sensor nicht auswählen, egal wie gut der Lesepfad ist.

    `sensor.` bleibt für Zustandsfelder ausdrücklich zulässig: manche
    Integrationen (und viele selbstgebaute Template-Sensoren) liefern den Modus
    als gewöhnlichen Text-Sensor.

    Themen-Kacheln (4.2.0, G6): ``alle=True`` (Picker eines Themen-Eintrags) lässt **jede** Entität mit nicht-leerem
    State durch — kein Domain-Test, kein Energie-Filter: ein Thema zeigt, was HA liefert (Schloss, Reifendruck, Zähler).
    """
    if alle:
        return bool(str(state.get("state") or "").strip())
    eid = str(state.get("entity_id", ""))
    if zustand:
        # Zustandsfelder: `climate.` UND `sensor.`, und der Energie-Filter
        # greift nicht — ein Modus hat weder Einheit noch device_class.
        # P-433-2b K1: ein Feld mit `ha_domaenen` (Registry) nennt seine Domains selbst — der evcc-Lademodus ist ein
        # `select`, der Standort ein `device_tracker`.
        erlaubt = domaenen or ("climate", "sensor")
        return any(eid.startswith(f"{d}.") for d in erlaubt)
    if not eid.startswith("sensor."):
        return False
    if not filter_energy:
        return True
    attrs = state.get("attributes", {}) or {}
    dc = attrs.get("device_class", "")
    unit = attrs.get("unit_of_measurement", "")
    sc = attrs.get("state_class", "")
    if dc in _HA_DEVICE_CLASSES or unit in _HA_UNITS or sc in ("total_increasing", "total"):
        return True
    if sc == "measurement" and not unit:
        return True
    return not dc and not sc and not unit and _is_int_state(state.get("state"))


# ─── B3: MQTT-Topic-Discovery (#-Scan) ───────────────────────────────
# Kurzlebiger Subscribe auf den Broker-Wildcard, um Fremd-Topics (Gateway-
# Quellen) auffindbar zu machen — heute gab es nur den Einzel-Topic-Test.
# Broker-Auflösung wie in mqtt_gateway.test_topic (Gateway-svc → Inbound-svc).
# Zeit- UND mengenbegrenzt (§2b „zeit-/größenbegrenzt"), damit ein volles
# Broker-`#` nicht das Backend flutet.


class DiscoveryRequest(BaseModel):
    """`#`-Scan-Parameter. `praefix` grenzt den Wildcard ein (Default: alles)."""
    praefix: str = Field(default="#", max_length=200)
    timeout_s: float = Field(default=4.0, ge=0.5, le=15.0)
    max_topics: int = Field(default=300, ge=1, le=2000)
    # Idle-Early-Exit: nach dem retained-Burst (≥1 Topic) `idle_ms` ohne neue
    # Nachricht → sofort fertig, statt bis `timeout_s` zu warten. 0 = aus.
    idle_ms: int = Field(default=700, ge=0, le=5000)
    # Optional: die aktive Anlage. Ihre EIGENEN Topic-Pfade werden ausgeschlossen
    # (selbstreferenziell/Schleife). NICHT der ganze `eedc/`-Namespace — andere
    # eedc-Instanzen am selben Broker bleiben als Fremd-Quelle wählbar (Gernot).
    anlage_id: int | None = None


async def _eigene_praefixe(db: AsyncSession, anlage_id: int | None) -> list[str]:
    """Topic-Präfixe der aktiven Anlage (Inbound + Gateway-Output) — aus Discovery ausschließen."""
    if anlage_id is None:
        return []
    from backend.services.mqtt_topic_registry import _mqtt_slug
    anlage = (await db.execute(select(Anlage).where(Anlage.id == anlage_id))).scalar_one_or_none()
    if not anlage:
        return []
    aslug = _mqtt_slug(anlage.anlagenname or f"Anlage {anlage_id}")
    # Inbound `eedc/{aid}_{slug}/…` (build_expected_topics) + Gateway-Output `eedc/{aid}/…`.
    return [f"eedc/{anlage_id}_{aslug}/", f"eedc/{anlage_id}/"]


class DiscoveryTopic(BaseModel):
    topic: str
    payload_sample: str
    payload_typ: str
    wert: float | None = None


class DiscoveryResponse(BaseModel):
    topics: list[DiscoveryTopic] = []
    anzahl: int = 0
    begrenzt: bool = False
    wartezeit_s: float = 0.0
    fehler: str | None = None


def _resolve_broker() -> tuple:
    """(host, port, username, password) des aktiven Brokers — Gateway zuerst, sonst Inbound."""
    from backend.services.mqtt_gateway_service import get_mqtt_gateway_service
    from backend.services.mqtt_inbound_service import get_mqtt_inbound_service

    svc = get_mqtt_gateway_service()
    if svc:
        return (svc.host, svc.port, svc.username, svc.password)
    inbound = get_mqtt_inbound_service()
    if inbound:
        return (inbound.host, inbound.port, inbound.username, inbound.password)
    raise HTTPException(status_code=400, detail="Kein MQTT-Broker aktiv")


def _detect_payload(raw: str) -> tuple:
    """(payload_typ, wert) für ein Roh-Payload — plain/json/json_array, float wenn plain."""
    payload_typ = "plain"
    try:
        parsed = json_mod.loads(raw)
        if isinstance(parsed, list):
            payload_typ = "json_array"
        elif isinstance(parsed, dict):
            payload_typ = "json"
    except (ValueError, TypeError):
        pass
    wert = None
    if payload_typ == "plain":
        try:
            wert = float(raw.strip())
        except ValueError:
            pass
    return (payload_typ, wert)


@router.post("/mqtt/discovery", response_model=DiscoveryResponse)
async def mqtt_discovery(data: DiscoveryRequest, db: AsyncSession = Depends(get_db, scope="function")) -> DiscoveryResponse:
    """Kurzlebiger `#`-Scan des Brokers → gefundene Topics mit letztem Sample (B3.1).

    Sammelt distinkte Topics (letzter Payload gewinnt) bis `max_topics` oder
    `timeout_s`. Basis für den Gateway-Quell-Picker (§2b); die Suche/Filterung
    passiert client-seitig auf der begrenzten Menge (Symmetrie zum HA-Sensor-Picker).
    Die EIGENEN Topic-Pfade der aktiven Anlage werden ausgeschlossen (§2b, kein
    Selbstbezug) — der übrige `eedc/`-Namespace (andere Instanzen) bleibt sichtbar.
    """
    try:
        import aiomqtt
    except ImportError:
        raise HTTPException(status_code=500, detail="aiomqtt nicht installiert")

    eigene = tuple(await _eigene_praefixe(db, data.anlage_id))
    host, port, username, password = _resolve_broker()
    wildcard = data.praefix if data.praefix.endswith("#") else f"{data.praefix.rstrip('/')}/#"

    start = asyncio.get_event_loop().time()
    gesammelt: dict[str, str] = {}
    begrenzt = False
    try:
        async with aiomqtt.Client(
            hostname=host, port=port, username=username, password=password,
            identifier=f"eedc-discovery-{int(start)}",
        ) as client:
            await client.subscribe(wildcard)
            try:
                async with asyncio.timeout(data.timeout_s):
                    it = client.messages.__aiter__()
                    while True:
                        try:
                            # Vor dem ersten Topic voll warten; danach nur `idle_ms`
                            # auf Nachzügler — der retained-Burst kommt am Stück.
                            if gesammelt and data.idle_ms > 0:
                                message = await asyncio.wait_for(it.__anext__(), timeout=data.idle_ms / 1000)
                            else:
                                message = await it.__anext__()
                        except (asyncio.TimeoutError, StopAsyncIteration):
                            break  # Burst vorbei (idle) bzw. Stream zu Ende.
                        topic = str(message.topic)
                        # NUR die eigenen Pfade der aktiven Anlage überspringen (Inbound
                        # + Gateway-Output) — selbstreferenziell/Schleifen-Footgun,
                        # redundant zur Quelle „MQTT-Inbound". Andere Anlagen/Instanzen
                        # unter `eedc/` bleiben. Skip VOR dem Cap → frisst ihn nicht.
                        if eigene and topic.startswith(eigene):
                            continue
                        payload = (
                            message.payload.decode("utf-8", errors="replace")
                            if isinstance(message.payload, bytes) else str(message.payload)
                        )
                        # Bis 2000 Zeichen behalten (wie test-topic) — kürzer bricht
                        # die JSON-Typ-Erkennung/Transform-Vorschau bei großen Payloads
                        # (z. B. HomeMatic-`{"val":…,"hm":{…}}`) fälschlich auf „plain".
                        gesammelt[topic] = payload[:2000]
                        if len(gesammelt) >= data.max_topics:
                            begrenzt = True
                            break
            except asyncio.TimeoutError:
                pass
    except Exception as e:
        elapsed = asyncio.get_event_loop().time() - start
        return DiscoveryResponse(wartezeit_s=round(elapsed, 1), fehler=f"Verbindungsfehler: {e}")

    elapsed = asyncio.get_event_loop().time() - start
    topics = []
    for topic in sorted(gesammelt):
        raw = gesammelt[topic]
        payload_typ, wert = _detect_payload(raw)
        topics.append(DiscoveryTopic(topic=topic, payload_sample=raw, payload_typ=payload_typ, wert=wert))

    return DiscoveryResponse(
        topics=topics, anzahl=len(topics), begrenzt=begrenzt, wartezeit_s=round(elapsed, 1),
    )


# ─── B3: MQTT-Baum-Ebene (Durchhangeln) ──────────────────────────────
# Statt rohe Topics zurückzugeben (→ Frontend-Baum, 1000-Cap frisst späte
# Zweige) aggregiert der Server pro Anfrage NUR die direkten Kinder des Pfads.
# Liest den Zweig `praefix/#`, dedupliziert on-the-fly zu Kind-Segmenten → die
# Antwort ist winzig und die Ebene VOLLSTÄNDIG (kein Topic-Cap, nur Idle/Timeout).

# Sicherheits-Obergrenze gelesener Nachrichten (nicht gespeichert → nur Zeit-Schutz;
# der retained-Burst mit allen Zweigen kommt am Anfang, lange davor).
_LEVEL_HARD_READ = 30000


class LevelChild(BaseModel):
    segment: str
    has_children: bool = False
    # Gesetzt, wenn dieses Segment selbst ein Topic mit Payload ist (Blatt).
    leaf: DiscoveryTopic | None = None


class LevelRequest(BaseModel):
    """Eine Baum-Ebene. `praefix` = Pfad ('' = Root, 'shellies', 'shellies/em')."""
    praefix: str = Field(default="", max_length=500)
    timeout_s: float = Field(default=4.0, ge=0.5, le=15.0)
    idle_ms: int = Field(default=700, ge=0, le=5000)
    anlage_id: int | None = None


class LevelResponse(BaseModel):
    praefix: str
    children: list[LevelChild] = []
    # Gesetzt, wenn der Pfad selbst ein Topic ist (Zweig+Wert-Knoten).
    self_leaf: DiscoveryTopic | None = None
    begrenzt: bool = False
    gelesen: int = 0
    fehler: str | None = None


@router.post("/mqtt/level", response_model=LevelResponse)
async def mqtt_level(data: LevelRequest, db: AsyncSession = Depends(get_db, scope="function")) -> LevelResponse:
    """Direkte Kinder einer Baum-Ebene (Durchhangeln) — serverseitig aggregiert.

    Vollständig für die Ebene (kein 1000-Topic-Cap): der Server liest den
    retained-Burst des Zweigs und dedupliziert zu Kind-Segmenten. Eigene
    Anlage-Pfade werden ausgeschlossen (§2b).
    """
    try:
        import aiomqtt
    except ImportError:
        raise HTTPException(status_code=500, detail="aiomqtt nicht installiert")

    eigene = tuple(await _eigene_praefixe(db, data.anlage_id))
    host, port, username, password = _resolve_broker()
    praefix = data.praefix.strip().strip("/")
    wildcard = "#" if not praefix else f"{praefix}/#"
    pre = f"{praefix}/" if praefix else ""

    start = asyncio.get_event_loop().time()
    kinder: dict[str, dict] = {}
    self_leaf_raw: tuple | None = None
    gelesen = 0
    begrenzt = False
    try:
        async with aiomqtt.Client(
            hostname=host, port=port, username=username, password=password,
            identifier=f"eedc-level-{int(start)}",
        ) as client:
            await client.subscribe(wildcard)
            try:
                async with asyncio.timeout(data.timeout_s):
                    it = client.messages.__aiter__()
                    while True:
                        try:
                            if gelesen and data.idle_ms > 0:
                                message = await asyncio.wait_for(it.__anext__(), timeout=data.idle_ms / 1000)
                            else:
                                message = await it.__anext__()
                        except (asyncio.TimeoutError, StopAsyncIteration):
                            break
                        topic = str(message.topic)
                        if eigene and topic.startswith(eigene):
                            continue
                        gelesen += 1
                        payload = (
                            message.payload.decode("utf-8", errors="replace")
                            if isinstance(message.payload, bytes) else str(message.payload)
                        )[:2000]
                        if praefix and topic == praefix:
                            self_leaf_raw = (topic, payload)
                        else:
                            rest = topic[len(pre):] if pre else topic
                            if pre and not topic.startswith(pre):
                                rest = ""
                            seg, sep, tail = rest.partition("/")
                            if seg:
                                k = kinder.get(seg)
                                if k is None:
                                    k = {"has_children": False, "leaf": None}
                                    kinder[seg] = k
                                if tail:
                                    k["has_children"] = True
                                else:
                                    k["leaf"] = (topic, payload)
                        if gelesen >= _LEVEL_HARD_READ:
                            begrenzt = True
                            break
            except asyncio.TimeoutError:
                pass
    except Exception as e:
        return LevelResponse(praefix=praefix, fehler=f"Verbindungsfehler: {e}")

    def _mk_leaf(topic: str, payload: str) -> DiscoveryTopic:
        typ, wert = _detect_payload(payload)
        return DiscoveryTopic(topic=topic, payload_sample=payload, payload_typ=typ, wert=wert)

    children = [
        LevelChild(
            segment=seg,
            has_children=kinder[seg]["has_children"],
            leaf=_mk_leaf(*kinder[seg]["leaf"]) if kinder[seg]["leaf"] else None,
        )
        for seg in sorted(kinder)
    ]
    self_leaf = _mk_leaf(*self_leaf_raw) if self_leaf_raw else None
    return LevelResponse(
        praefix=praefix, children=children, self_leaf=self_leaf, begrenzt=begrenzt, gelesen=gelesen,
    )


def _registry_feld_id(field_id: str) -> str:
    """Die Feld-ID, unter der die Topic-Registry ein Feld führt — für einen **Themen-Eintrag** (Themen-Kacheln 4.2.0)
    ``inv_thema_7_e3`` → ``inv_live_7_thema_e3`` (`match_key` ``("inv_live", "7", "thema_e3")``), sonst unverändert.

    Die Quelle eines Eintrags steht unter ``inv_thema_…`` (Bauplan §0, ein Store); das Topic, über das Inbound und
    Gateway den Wert tragen, ist ein Live-Topic des Geräts. Label (`_feld_label`) und Gateway-Ziel
    (`_standard_topic_suffix`) kommen damit aus derselben Registry-Zeile wie jedes Feld.
    """
    from backend.services.themen_store import eintrag_topic_key, eintrag_von_feld_id

    teile = eintrag_von_feld_id(field_id)
    if teile is None:
        return field_id
    return _feld_id(("inv_live", str(teile[0]), eintrag_topic_key(teile[1])))


async def _feld_label(db: AsyncSession, anlage: Anlage, field_id: str) -> str:
    """Anwendersichtbare Bezeichnung eines Feldes der Fläche.

    Dieselbe Auflösung wie `_standard_topic_suffix` — Registry + Preis-Slots,
    also genau die Menge, die die Fläche zeigt. Fällt auf die technische
    `field_id` zurück, damit ein Hinweis nie leer bleibt (ein Feld ohne Label
    wäre für den Anwender schlimmer als eine hässliche Kennung).

    Themen-Kacheln (4.2.0): ein Themen-Eintrag heißt «‹Gerät› – ‹Thema› · ‹Label›» (Registry-Zeile aus dem Store,
    `_registry_feld_id`) statt der Rohkennung ``inv_thema_…``.
    """
    return (await _feld_labels(db, anlage)).get(_registry_feld_id(field_id), field_id)


async def _feld_labels(db: AsyncSession, anlage: Anlage) -> dict[str, str]:
    """Alle Feld-Labels der Fläche auf einmal — für Aufrufer mit mehreren Feldern
    (N-556: die Energie-Übernahme protokolliert je Feld), damit die Registry nicht
    je Feld neu gebaut wird."""
    invs = (await db.execute(
        select(Investition).where(Investition.anlage_id == anlage.id, aktiv_am_tag(date.today()))
    )).scalars().all()
    invs = sort_investitionen_nach_typ(invs)
    eintraege = list(await build_expected_topics(db, anlage, investitionen=invs))
    eintraege += await _basis_preis_eintraege(db, anlage.id)
    labels: dict[str, str] = {}
    for e in eintraege:
        fid = _feld_id(e["match_key"])
        # erster Treffer gewinnt — dieselbe Reihenfolge wie die frühere Schleife
        labels.setdefault(fid, str(e.get("label") or e.get("feld_label") or fid))
    return labels


def _quelle_klartext(eintrag: dict | None, topic: str | None = None) -> str:
    """Eine Quelle, wie sie im Aktivitätsprotokoll steht (N-556).

    ``None``/``{}`` heißt „kein eigener Eintrag" = Grundeinstellung (MQTT-Inbound
    auf dem Standard-Topic) — dieselbe Lesart wie `ist_echte_aenderung`.
    """
    q = (eintrag or {}).get("quelle")
    if not q or q == QUELLE_STANDARD:
        return "Standard (MQTT-Inbound)"
    if q in QUELLEN_HA:
        return f"HA-Sensor {(eintrag or {}).get('entity_id') or ''}".strip()
    if q == QUELLE_GATEWAY:
        return f"MQTT-Gateway {topic}" if topic else "MQTT-Gateway"
    if q == QUELLE_KEINE:
        return "keine Quelle"
    return str(q)


async def _hat_aggregierte_historie(db: AsyncSession, anlage_id: int) -> bool:
    """Gibt es überhaupt schon gerechnete Tageswerte für diese Anlage?

    Ohne sie ist eine Zuordnung keine *Änderung* der Vergangenheit, sondern
    ihre Ersteinrichtung — im Setup-Wizard ordnet der Anwender ein Dutzend
    Felder zu, und ein Hinweis auf eine Historie, die es nicht gibt, wäre
    reiner Lärm.
    """
    from backend.models.tages_energie_profil import TagesZusammenfassung

    return (await db.execute(
        select(TagesZusammenfassung.id)
        .where(TagesZusammenfassung.anlage_id == anlage_id)
        .limit(1)
    )).scalar_one_or_none() is not None


async def _historie_vermerken(
    db: AsyncSession, anlage: Anlage, mapping: dict, field_id: str,
) -> None:
    """Trägt die Zuordnungsänderung in den Historie-Vermerk ein (Konzept #192 B).

    In-place auf `mapping`; der Aufrufer committet ohnehin. Fehlschläge sind
    hier folgenlos für die Zuordnung selbst — der Vermerk ist ein Hinweis, kein
    Datenpfad —, deshalb bricht ein Label-Lookup den Speichervorgang nicht ab.
    """
    if not await _hat_aggregierte_historie(db, anlage.id):
        return
    try:
        label = await _feld_label(db, anlage, field_id)
    except Exception:  # pragma: no cover — Anzeige-Detail, nie ein Blocker
        logger.warning("Label-Auflösung für Historie-Hinweis fehlgeschlagen", exc_info=True)
        label = field_id
    vermerk_ergaenzen(
        mapping,
        field_id=field_id,
        label=label,
        jetzt_iso=datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
    )


async def _standard_topic_suffix(db: AsyncSession, anlage: Anlage, field_id: str) -> str | None:
    """Standard-Inbound-Topic-Suffix eines Feldes (`live/…` bzw. `energy/…`).

    C2a: Der Gateway re-publisht nach `eedc/{aid}/{ziel_key}`. Nur wenn ziel_key =
    genau dieses Suffix ist, trifft der Wert die Inbound-Subscription
    `eedc/+/live|energy/#` und fließt durch die bestehende Inbound-Maschinerie
    (Live + kWh). Ableitung aus der Topic-Registry-SoT (kein Neu-Basteln).

    Themen-Kacheln (4.2.0, W9): ein Themen-Eintrag ``inv_thema_<id>_<e>`` bekommt ``live/inv/<id>_<slug>/thema_<e>`` —
    ohne diese Auflösung republishte das Gateway ins Leere (`_registry_feld_id`).
    """
    ziel = _registry_feld_id(field_id)
    invs = (await db.execute(
        select(Investition).where(Investition.anlage_id == anlage.id, aktiv_am_tag(date.today()))
    )).scalars().all()
    invs = sort_investitionen_nach_typ(invs)
    for e in await build_expected_topics(db, anlage, investitionen=invs):
        if _feld_id(e["match_key"]) == ziel:
            # topic = eedc/{aid}_{slug}/live/… → Suffix ab dem 3. Segment.
            parts = e["topic"].split("/", 2)
            return parts[2] if len(parts) == 3 else None
    return None


async def _ist_ohne_leser(db: AsyncSession, anlage: Anlage, field_id: str) -> bool:
    """Trägt das Feld das Flag ``ohne_leser`` der Topic-Registry (N-780)? Dieselbe Erwartungsliste wie die Fläche
    (alle Investitionen der Anlage — ein Riegel darf an einem stillgelegten Gerät nicht anders antworten)."""
    if not field_id.startswith("inv_energy_"):
        return False
    invs = (await db.execute(select(Investition).where(Investition.anlage_id == anlage.id))).scalars().all()
    return any(
        e.get("ohne_leser") for e in await build_expected_topics(db, anlage, investitionen=list(invs))
        if _feld_id(e["match_key"]) == field_id
    )


async def setze_gateway_quellen(db: AsyncSession, anlage: Anlage, zeilen) -> tuple[int, list[str]]:
    """Setzt für frisch angelegte Gateway-Zeilen (Preset-Apply, P-433-2b K4-8) die Quelle ihres Feldes auf
    ``mqtt_gateway`` — dieselbe Schreibform wie ``set_feld_quelle`` (``quellen[field_id] = {quelle, mapping_id}`` +
    ``uebernehme_quelle_ins_mapping`` + Historie-Vermerk bei echter Änderung), damit die Fläche «Gateway» mit Topic zeigt
    statt «Inbound».

    Die Feld-ID kommt **rückwärts** aus der Topic-Registry (dieselbe Quelle wie ``_standard_topic_suffix``): das Feld,
    dessen Standard-Topic-Suffix in ID-Form (``ziel_key_ohne_namen`` — der Suffix trägt den Namensteil ``{id}_{name}``,
    das Preset nicht) gleich dem ``ziel_key`` der Zeile ist (``live/inv/{id}/<feld>`` → ``inv_live_{id}_…``,
    ``energy/inv/{id}/<feld>`` → ``inv_energy_{id}_…``). Eine Zeile ohne passendes Feld behält ihre Zeile, die Quelle
    bleibt unverändert; ihr ``ziel_key`` steht in der Rückgabe.

    Returns:
        ``(gesetzte Felder, ziel_keys ohne Feld)``. ``flag_modified``/Commit macht der Aufrufer.
    """
    from backend.services.datenquellen_mapping_sync import uebernehme_quelle_ins_mapping
    from backend.services.datenquellen_resolver import ziel_key_ohne_namen

    invs = sort_investitionen_nach_typ((await db.execute(
        select(Investition).where(Investition.anlage_id == anlage.id, aktiv_am_tag(date.today()))
    )).scalars().all())
    feld_je_suffix: dict[str, str] = {}
    for e in await build_expected_topics(db, anlage, investitionen=invs):
        parts = e["topic"].split("/", 2)
        if len(parts) == 3:
            feld_je_suffix.setdefault(ziel_key_ohne_namen(parts[2]), _feld_id(e["match_key"]))
    mapping = dict(anlage.sensor_mapping or {})
    quellen = dict(mapping.get(QUELLEN_KEY) or {})
    gesetzt, ohne, geaendert = 0, [], []
    for row in zeilen:
        field_id = feld_je_suffix.get(ziel_key_ohne_namen(row.ziel_key))
        if field_id is None:
            ohne.append(row.ziel_key)
            continue
        neu = {"quelle": QUELLE_GATEWAY, "mapping_id": row.id}
        if ist_echte_aenderung(quellen.get(field_id), neu):
            geaendert.append(field_id)
        quellen[field_id] = neu
        uebernehme_quelle_ins_mapping(mapping, field_id, QUELLE_GATEWAY, None)
        gesetzt += 1
    mapping[QUELLEN_KEY] = quellen
    for field_id in geaendert:
        await _historie_vermerken(db, anlage, mapping, field_id)
    anlage.sensor_mapping = mapping
    return gesetzt, ohne


def _pruefe_themen_eintrag(mapping: dict, field_id: str) -> bool:
    """``True`` für die Kennung eines Themen-Eintrags (``inv_thema_…``); fehlt der Eintrag im Store ⇒ **404**."""
    from backend.services.themen_store import eintrag_von_feld_id, finde_eintrag

    teile = eintrag_von_feld_id(field_id)
    if teile is None:
        return False
    if finde_eintrag(mapping, teile[0], teile[1]) is None:
        raise HTTPException(status_code=404, detail="Eintrag nicht gefunden")
    return True


async def _thema_label_aus_ha(db: AsyncSession, mapping: dict, field_id: str, entity_id: str) -> None:
    """Erster HA-Pick: steht am Eintrag noch die Vorgabe «Eintrag n», übernimmt er den ``friendly_name`` (einmalig).

    Der Abruf läuft nur bei Vorgabe-Label; ohne erreichbares HA oder ohne Klarnamen bleibt das Label.
    """
    from backend.services.themen_store import (
        eintrag_label_setzen_wenn_vorgabe, eintrag_von_feld_id, finde_eintrag, ist_vorgabe_label,
    )

    inv_id, e_id = eintrag_von_feld_id(field_id)
    treffer = finde_eintrag(mapping, inv_id, e_id)
    if not entity_id or treffer is None or not ist_vorgabe_label(treffer[1]["label"]):
        return
    name = ((await _ha_states_detail(db, {entity_id})).get(entity_id) or {}).get("friendly_name")
    eintrag_label_setzen_wenn_vorgabe(mapping, inv_id, e_id, name)


# ─── HA-Sensor-Discovery (Schritt B) ─────────────────────────────────
class HaSensor(BaseModel):
    entity_id: str
    friendly_name: str | None = None
    unit: str | None = None
    device_class: str | None = None
    state: str | None = None
    #: Themen-Kacheln (4.2.0): die HA-Domain (``lock``, ``sensor`` …) — der Picker mit ``alle`` zeigt sie an der Zeile.
    domain: str | None = None


class HaVorschlag(BaseModel):
    """Kuratierter Feld-Vorschlag aus der Integrations-Wissensbasis (#343 A)."""
    integration: str
    label: str
    entity_id: str
    hinweis: str


class HaSensorenResponse(BaseModel):
    verfuegbar: bool = False
    quelle: str | None = None  # ha_app | ha_connector
    sensoren: list[HaSensor] = []
    fehler: str | None = None
    # #343 Baustein A (D2): erkannte Integrationen + Feld-Vorschlaege + Anti-
    # Empfehlungen (entity_id -> Warntext) - Assistenz, nie Auto-Auswahl.
    integrationen: list[str] = []
    vorschlaege: list[HaVorschlag] = []
    warnungen: dict[str, str] = {}


@router.get("/{anlage_id}/ha/sensoren", response_model=HaSensorenResponse)
async def get_ha_sensoren(
    anlage_id: int,
    filter_energy: bool = True,
    feld: str | None = None,
    inv_typ: str | None = None,
    alle: bool = False,
    db: AsyncSession = Depends(get_db),
) -> HaSensorenResponse:
    """HA-Entities für den HA-Sensor-Picker — Supervisor ODER Remote-HA (verbindungs-transparent).

    Liest `/api/states` der aktiven HA-Verbindung und filtert energie-relevante
    Sensoren (Symmetrie zu sensor_mapping.available-sensors). `quelle` sagt dem
    Frontend, welche Quell-Kennung zu persistieren ist (ha_app/ha_connector).

    Themen-Kacheln (4.2.0): ``alle=True`` ⇒ jede Entität mit State (`_ha_sensor_relevant(…, alle=True)`), ohne
    Vorschläge und Warnungen der Wissensbasis (sie gelten Feldern, nicht frei gewählten Entitäten).
    """
    api_url, token, kind = await _resolve_ha(db)
    if not api_url or not token:
        return HaSensorenResponse(verfuegbar=False)
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(f"{api_url}/states", headers={"Authorization": f"Bearer {token}"})
    except Exception as e:  # noqa: BLE001 — Netzwerk-/TLS-Fehler als weicher Fehler melden
        return HaSensorenResponse(verfuegbar=True, quelle=kind, fehler=f"HA-Verbindungsfehler: {e}")
    if resp.status_code != 200:
        return HaSensorenResponse(
            verfuegbar=True, quelle=kind, fehler=f"HA-States nicht abrufbar (HTTP {resp.status_code})"
        )
    # #263 K-2: Für ein Zustandsfeld (heute: `betriebsmodus`) ist auch die
    # `climate.`-Domain zulässig — der Modus einer Klimaanlage liegt in HA
    # nirgendwo anders. Der Typ schärft die Antwort, wo er mitkommt; ohne ihn
    # entscheidet der Feld-Key allein (s. `ist_zustand_feld`).
    ist_zustand = bool(feld) and ist_zustand_feld(feld, inv_typ or None)
    domaenen = _ha_domaenen(feld, inv_typ) if ist_zustand else None
    sensoren: list[HaSensor] = []
    for st in resp.json():
        if not _ha_sensor_relevant(st, filter_energy, zustand=ist_zustand, domaenen=domaenen, alle=alle):
            continue
        attrs = st.get("attributes", {}) or {}
        sensoren.append(HaSensor(
            entity_id=st.get("entity_id", ""),
            friendly_name=attrs.get("friendly_name"),
            unit=attrs.get("unit_of_measurement") or None,
            device_class=attrs.get("device_class") or None,
            state=st.get("state"),
            domain=str(st.get("entity_id", "")).split(".", 1)[0] or None,
        ))
    sensoren.sort(key=lambda s: s.entity_id)
    # #343 A: Wissensbasis-Vorschlaege fuer das Ziel-Feld + Anti-Empfehlungen (nicht im Themen-Picker).
    assistenz = (
        {"integrationen": [], "vorschlaege": [], "warnungen": {}} if alle
        else analysiere_vorschlaege([se.entity_id for se in sensoren], feld=feld, inv_typ=inv_typ)
    )
    return HaSensorenResponse(
        verfuegbar=True, quelle=kind, sensoren=sensoren,
        integrationen=assistenz["integrationen"],
        vorschlaege=[HaVorschlag(**v) for v in assistenz["vorschlaege"]],
        warnungen=assistenz["warnungen"],
    )


def _ha_domaenen(feld: str | None, inv_typ: str | None) -> tuple[str, ...] | None:
    """Die HA-Domains eines Zustandsfelds aus der Registry (`ha_domaenen`, P-433-2b K1) — ``None`` ⇒ Standard."""
    from backend.core.field_definitions import LIVE_FELDER_INV

    basis = basis_feld_key(feld or "")
    typen = [inv_typ] if inv_typ else list(LIVE_FELDER_INV)
    for typ in typen:
        for f in LIVE_FELDER_INV.get(typ or "", []):
            if f["key"] == basis and f.get("ha_domaenen"):
                return tuple(f["ha_domaenen"])
    return None


# --- Takt-Check beim Waehlen (#343 Baustein B, D2) ---------------------------
class TaktCheckRequest(BaseModel):
    entity_id: str


class TaktCheckResponse(BaseModel):
    geprueft: bool = False
    problem: dict | None = None


@router.post("/{anlage_id}/ha/takt-check", response_model=TaktCheckResponse)
async def ha_takt_check(
    anlage_id: int, req: TaktCheckRequest, db: AsyncSession = Depends(get_db, scope="function")
) -> TaktCheckResponse:
    """On-Demand-Taktpruefung eines kWh-Kandidaten im Pick-Moment (#343).

    REST /history/period der aktiven HA-Verbindung (Supervisor ODER Remote) -
    bewusst NICHT im /felder-Batch (n x History je Seitenaufruf). Nicht
    pruefbar (keine HA, keine History) -> geprueft=false, still (v3.23.8-Muster).
    """
    from datetime import datetime, timedelta

    from backend.services.datenquellen_validierung import takt_problem

    api_url, token, _kind = await _resolve_ha(db)
    if not api_url or not token:
        return TaktCheckResponse(geprueft=False)
    start = (datetime.now() - timedelta(hours=48)).isoformat()
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(
                f"{api_url}/history/period/{start}",
                headers={"Authorization": f"Bearer {token}"},
                params={
                    "filter_entity_id": req.entity_id,
                    "minimal_response": "",
                    "no_attributes": "",
                },
            )
    except Exception:  # noqa: BLE001 - Netzwerkfehler = nicht pruefbar, still
        return TaktCheckResponse(geprueft=False)
    if resp.status_code != 200:
        return TaktCheckResponse(geprueft=False)
    reihen = resp.json() or []
    werte: list[float] = []
    for eintrag in (reihen[0] if reihen else []):
        try:
            werte.append(float(eintrag.get("state")))
        except (TypeError, ValueError):
            continue
    if len(werte) < 4:
        return TaktCheckResponse(geprueft=False)
    return TaktCheckResponse(geprueft=True, problem=takt_problem(werte))


# RF-82 (5.11.2026, Bauform RF-1): die Route ist ein Orchestrator über `FelderKontext` und sechs Phasen in fester
# Reihenfolge (die SQL-Folge ist Vertrag — B8-2 schreibt VOR der MQTT-Einstellungsabfrage fest). Die ersten vier lesen
# nur und stehen seit E1 (10.11.2026) in `services/datenquellen_felder.py::zuordnungen_lesen` — dieselbe Kette ruft das
# Diagnose-Paket; geschrieben wird nur hier:
#   `_felder_laden`       Anlage (404), aktive Investitionen, Registry-Einträge + Preis-Slots, Filter, Invert-Store
#   `_quellen_aufloesen`  Gateway-Zeilen, Inbound-Cache, HA-Transport + Live-Maps, Pass 1 (B8-2), HA-Batch (C1/§2i)
#   `_praezedenzen`       §2i-Probleme (Einheit, state_class, Redundanz, Bauschnitt 7, N-537, Doppelmapping) + Bedarf je Gerät
#   `_antwort`            Pass 2: Gruppen und Felder, Themen-Kacheln
#   `_festschreiben`      B8-2 additiv festschreiben (guarded) + §2h-Deaktivierung, eigener Commit
#   `_verfuegbarkeit`     Quell-Achsen HA/MQTT
# Der Docstring der Route ist ihre OpenAPI-Beschreibung und bleibt unverändert.
@router.get("/{anlage_id}/felder")
async def get_datenquellen_felder(anlage_id: int, db: AsyncSession = Depends(get_db)):
    """Gruppierte Feldliste (Basis + je Investition) mit Standard-Topic + aktiver Quelle."""
    # Die HA-Nähte der Route (`_resolve_ha`, `_ha_states_detail`) werden durchgereicht — an ihnen setzen Tests und der
    # Golden Master `datenquellen-felder` an.
    ctx, gruppen = await zuordnungen_lesen(db, anlage_id, ha_aufloesen=_resolve_ha, ha_details=_ha_states_detail)
    await _festschreiben(db, ctx)
    verfuegbarkeit = await _verfuegbarkeit(db, ctx)
    anlage = ctx.anlage

    return {
        "anlage_id": anlage_id,
        "gruppen": gruppen,
        "verfuegbarkeit": verfuegbarkeit,
        # Konzept #192 B: offener Hinweis auf die unberührte Historie — `None`,
        # solange keine Zuordnung geändert wurde. Bewusst hier und nicht als
        # eigener Endpunkt: die Fläche lädt diese Antwort ohnehin, und ein
        # zweiter Aufruf hätte den Block nur später erscheinen lassen.
        "historie_hinweis": vermerk_lesen(anlage.sensor_mapping),
    }


async def _festschreiben(db: AsyncSession, ctx: FelderKontext) -> None:
    """Phase 5 von `/felder`: B8-2 — die positive Evidenz aus Pass 1 additiv festschreiben, mit eigenem Commit."""
    anlage, neu_persistieren, gw_deaktivieren = ctx.anlage, ctx.neu_persistieren, ctx.gw_deaktivieren

    # B8-2: aufgelöste positive Evidenz additiv festschreiben (guarded — nur bei
    # tatsächlicher Änderung; §2h: paralleles Gateway bei HA-Wahl deaktivieren,
    # nicht löschen). Stummes Inbound wurde NICHT aufgenommen → kein Ballast.
    if neu_persistieren:
        from sqlalchemy.orm.attributes import flag_modified
        mapping = dict(anlage.sensor_mapping or {})
        qmap = dict(mapping.get("quellen") or {})
        qmap.update(neu_persistieren)
        mapping["quellen"] = qmap
        anlage.sensor_mapping = mapping
        flag_modified(anlage, "sensor_mapping")
        for row in gw_deaktivieren:
            row.aktiv = False
        await db.commit()


async def _verfuegbarkeit(db: AsyncSession, ctx: FelderKontext) -> dict:
    """Phase 6 von `/felder`: Verfügbarkeit der Quell-Achsen."""
    ha_url, ha_kind = ctx.ha_url, ctx.ha_kind

    # Verfügbarkeit der Quell-Achsen (Schritt B Gating): HA (Supervisor ODER
    # Remote-HA) + MQTT (Broker aktiv). Steuert Aktiv/Ausgegraut der Buttons.
    verfuegbarkeit = {
        "ha": bool(ha_url),
        "ha_quelle": ha_kind,
        "mqtt": await _mqtt_import_aktiviert(db),
    }
    return verfuegbarkeit


class QuelleSetRequest(BaseModel):
    """Quelle eines Feldes setzen. Transform-Felder gelten nur für `mqtt_gateway`."""
    quelle: str
    # HA-Zuordnung (ha_app/ha_connector): gewählte HA-Entity.
    entity_id: str | None = None
    # Gateway-Zuordnung (§2b Quell-Picker → mqtt_gateway_mappings, ziel_key = field_id):
    quell_topic: str | None = None
    payload_typ: str = "plain"
    json_pfad: str | None = None
    array_index: int | None = None
    faktor: float = 1.0
    offset: float = 0.0
    # Invert ist NICHT mehr Teil der Quellen-Wahl (Datenquellen-V4): eigener
    # /invert-Endpoint + Store `sensor_mapping.invertieren`. Feld hier entfernt.


class InvertSetRequest(BaseModel):
    """Vorzeichen-Umkehr eines Feldes setzen — quellen-unabhängig (Wert-Eigenschaft)."""
    invertieren: bool


@router.post("/{anlage_id}/felder/{field_id}/invert")
async def set_feld_invert(
    anlage_id: int, field_id: str, body: InvertSetRequest, db: AsyncSession = Depends(get_db, scope="function")
):
    """Setzt/entfernt die Vorzeichen-Umkehr eines Feldes im vereinheitlichten Store.

    `sensor_mapping.invertieren = {field_id: true}` — QUELLEN-UNABHÄNGIG (Wert-
    Eigenschaft, egal welche Quelle das Feld liefert), am Read-Endwert angewendet
    (`live_power_service` finaler Pass + `apply_invert_to_history`). Nur True wird
    gespeichert (kein Ballast); False entfernt den Eintrag.
    """
    from sqlalchemy.orm.attributes import flag_modified

    anlage = (
        await db.execute(select(Anlage).where(Anlage.id == anlage_id))
    ).scalar_one_or_none()
    if not anlage:
        raise HTTPException(status_code=404, detail="Anlage nicht gefunden")

    mapping = copy.deepcopy(anlage.sensor_mapping or {})
    invert = dict(mapping.get("invertieren") or {})
    vorher_invertiert = bool(invert.get(field_id)) or legacy_invert_aktiv(mapping, field_id)
    if body.invertieren:
        invert[field_id] = True
    else:
        invert.pop(field_id, None)
        # N-562: Ausschalten heißt aus — auch ein Legacy-`live_invert` (vor v4)
        # geht mit, sonst hielte die Union in `extract_live_config` den Wert
        # weiter umgedreht, während der Schalter grau ist (T89667 #378).
        entferne_legacy_invert(mapping, field_id)
    mapping["invertieren"] = invert
    # Konzept #192 B: das Vorzeichen dreht die Aggregation, wirkt aber erst ab
    # dem nächsten Lauf — die gespeicherten Tage behalten ihre Richtung. Genau
    # dieser Fall war der Anlass der Speicher-Vorzeichen-Selbstkorrektur
    # (v3.45.7); der Hinweis erspart die zweite Runde.
    if vorher_invertiert != bool(body.invertieren):
        await _historie_vermerken(db, anlage, mapping, field_id)
    anlage.sensor_mapping = mapping
    flag_modified(anlage, "sensor_mapping")
    # N-556: jede Handlung auf der Fläche steht im Protokoll — in DIESER Sitzung
    # (N-532), damit die Zeile mit der Zuordnung committet oder verworfen wird.
    await log_activity(
        kategorie="sensor_mapping",
        aktion="Vorzeichen umgekehrt" if body.invertieren else "Vorzeichen-Umkehr entfernt",
        details=(
            f"{anlage.anlagenname} · {await _feld_label(db, anlage, field_id)}: "
            f"{'umgekehrt' if vorher_invertiert else 'normal'} → "
            f"{'umgekehrt' if body.invertieren else 'normal'}"
        ),
        details_json={"field_id": field_id, "vorher": vorher_invertiert,
                      "nachher": bool(body.invertieren)},
        anlage_id=anlage_id,
        db=db,
    )
    await db.commit()
    return {
        "field_id": field_id,
        "invertieren": bool(body.invertieren),
        # Der Client zeigt den Block ohne zweiten Roundtrip — ein Nachladen der
        # ganzen Feldliste je Klick wäre teuer, und ein Hinweis, der erst beim
        # nächsten Seitenaufruf erscheint, käme zu spät.
        "historie_hinweis": vermerk_lesen(mapping),
    }


@router.delete("/{anlage_id}/historie-hinweis")
async def quittiere_historie_hinweis(anlage_id: int, db: AsyncSession = Depends(get_db, scope="function")):
    """Quittiert den Historie-Hinweis („Verstanden") — Konzept #192 B.

    Bewusst eine Quittung des **Anwenders** und kein „erledigt": ob er die
    Vergangenheit nachgezogen hat, weiß eedc nicht (die Bereichs-Reparatur
    läuft in 31-Tage-Blöcken, s. `services/datenquellen_historie.py`).
    """
    from sqlalchemy.orm.attributes import flag_modified

    anlage = (
        await db.execute(select(Anlage).where(Anlage.id == anlage_id))
    ).scalar_one_or_none()
    if not anlage:
        raise HTTPException(status_code=404, detail="Anlage nicht gefunden")

    mapping = dict(anlage.sensor_mapping or {})
    entfernt = vermerk_leeren(mapping)
    if entfernt:
        anlage.sensor_mapping = mapping
        flag_modified(anlage, "sensor_mapping")
        await db.commit()
    return {"quittiert": entfernt}


@router.post("/{anlage_id}/felder/{field_id}/quelle")
async def set_feld_quelle(
    anlage_id: int, field_id: str, body: QuelleSetRequest, db: AsyncSession = Depends(get_db, scope="function")
):
    """Setzt die Quelle eines Feldes (genau eine pro Feld, §2d) in sensor_mapping.quellen.

    Bei `mqtt_gateway` (B3.3) wird zusätzlich eine `mqtt_gateway_mappings`-Zeile
    ge-upsertet (ziel_key = field_id, §2b: eine Quelle/Feld) und ihre `mapping_id`
    in `quellen[field_id]` referenziert. Beim Wegschalten wird die Zeile **gelöscht**
    — das ist die bewusste Nutzer-Umschaltung im Picker (kein Waisen-Ballast); das
    §2h-Prinzip „deaktivieren statt löschen" gilt der **automatischen** B8-Migration
    (parallele Mappings verlustfrei rückholbar), nicht dieser expliziten Wahl.

    Die Wahl wird IMMER auch in die klassische `sensor_mapping`-Struktur
    geschrieben (`datenquellen_mapping_sync`) — `quellen` allein ist für alle
    Leser nur ein Read-Through, die Aufzählung läuft über `basis`/`investitionen`.
    """
    from sqlalchemy.orm.attributes import flag_modified
    from datetime import datetime
    from backend.models.mqtt_gateway_mapping import MqttGatewayMapping
    from backend.services.datenquellen_mapping_sync import uebernehme_quelle_ins_mapping

    quelle = (body.quelle or "").strip()
    if quelle not in QUELLEN_ERLAUBT:
        raise HTTPException(status_code=400, detail=f"Unbekannte/nicht verfügbare Quelle: {quelle}")

    # Preis-Felder werden ausschließlich als HA-Sensor gelesen (stündlicher
    # LTS-Mittelwert). Ein Gateway-/Inbound-Eintrag würde eine Quelle
    # versprechen, die kein Leser abfragt — die Fläche blendet die Knöpfe
    # deshalb aus, und hier steht der Riegel für den direkten API-Weg.
    if field_id.startswith("basis_preis_") and quelle not in (*QUELLEN_HA, QUELLE_KEINE):
        raise HTTPException(
            status_code=400,
            detail="Preis-Felder werden nur als HA-Sensor gelesen — MQTT ist hier ohne Wirkung.",
        )

    anlage = (
        await db.execute(select(Anlage).where(Anlage.id == anlage_id))
    ).scalar_one_or_none()
    if not anlage:
        raise HTTPException(status_code=404, detail="Anlage nicht gefunden")
    # N-780 (Päckchen U): dieselbe Form für ein Energie-Feld ohne Leser — eedc nähme den MQTT-Wert an, verarbeitete ihn
    # aber nicht. Die Fläche bietet Gateway/Inbound dort nicht an (`nur_ha`); hier der Riegel für den direkten API-Weg.
    if quelle in (QUELLE_STANDARD, QUELLE_GATEWAY) and await _ist_ohne_leser(db, anlage, field_id):
        raise HTTPException(
            status_code=400,
            detail="eedc liest dieses Feld nicht über MQTT — ordne einen HA-Sensor zu oder trag den Wert im "
                   "Monatsabschluss von Hand ein.",
        )

    mapping = dict(anlage.sensor_mapping or {})
    # Themen-Kacheln (4.2.0, G2-1): eine Themen-Kennung muss zu einem Eintrag gehören — sonst 404 statt stiller Ablage.
    ist_thema = _pruefe_themen_eintrag(mapping, field_id)
    quellen = dict(mapping.get(QUELLEN_KEY) or {})
    vorher = quellen.get(field_id) or {}
    alt_mapping_id = vorher.get("mapping_id")

    async def _lade_mapping_row(mid):
        if mid is None:
            return None
        return (await db.execute(
            select(MqttGatewayMapping).where(MqttGatewayMapping.id == mid)
        )).scalar_one_or_none()

    # N-556: die alte Quelle im Klartext, BEVOR die Gateway-Zeile umgeschrieben
    # oder gelöscht wird — danach trägt sie schon das neue Topic.
    _alt_row = await _lade_mapping_row(alt_mapping_id)
    alt_text = _quelle_klartext(vorher, _alt_row.quell_topic if _alt_row is not None else None)

    if quelle == QUELLE_GATEWAY:
        quell_topic = (body.quell_topic or "").strip()
        if not quell_topic:
            raise HTTPException(status_code=400, detail="mqtt_gateway erfordert ein quell_topic")
        # ziel_key = Standard-Topic-Suffix (nicht field_id!), damit der Gateway-
        # Wert via eedc/{aid}/{suffix} in den Inbound-Cache fließt (C2a). Fallback
        # field_id nur, falls das Feld nicht (mehr) in der Registry ist. VOR dem
        # db.add(row) berechnen — die Query darin würde sonst die halb-gebaute
        # Zeile (ziel_key=NULL) per Autoflush schreiben.
        ziel_key = (await _standard_topic_suffix(db, anlage, field_id)) or field_id
        # Upsert der Gateway-Zeile — bestehende dieses Feldes wiederverwenden.
        row = await _lade_mapping_row(alt_mapping_id)
        if row is None:
            row = MqttGatewayMapping(anlage_id=anlage_id, erstellt_am=datetime.utcnow())
            db.add(row)
        row.quell_topic = quell_topic
        row.ziel_key = ziel_key
        row.payload_typ = body.payload_typ
        row.json_pfad = body.json_pfad
        row.array_index = body.array_index
        row.faktor = body.faktor
        row.offset = body.offset
        # Kein Republish-Invert mehr (Datenquellen-V4): Vorzeichen liegt im
        # quellen-unabhängigen Store, angewendet am Read-Endwert.
        row.invertieren = False
        row.aktiv = True
        await db.flush()
        await db.refresh(row)
        quellen[field_id] = {"quelle": QUELLE_GATEWAY, "mapping_id": row.id}
    else:
        # Weg von Gateway → zugehörige Zeile löschen (bewusste Nutzer-Umschaltung).
        # N-561: derselbe Löschweg wie beim Löschen einer Komponente.
        from backend.api.routes.mqtt_gateway import entferne_gateway_zeile
        await entferne_gateway_zeile(db, alt_mapping_id)
        if quelle in QUELLEN_HA:
            entity = (body.entity_id or "").strip()
            if not entity:
                raise HTTPException(status_code=400, detail=f"{quelle} erfordert eine entity_id")
            quellen[field_id] = {"quelle": quelle, "entity_id": entity}
        elif quelle == QUELLE_STANDARD:
            # Inbound = Grundeinstellung → kein Eintrag nötig (B8-2 materialisiert
            # bei Bedarf). Invert ist quellen-unabhängig (eigener /invert-Endpoint).
            quellen.pop(field_id, None)
        else:  # QUELLE_KEINE
            quellen[field_id] = {"quelle": QUELLE_KEINE}

    mapping[QUELLEN_KEY] = quellen
    # Konzept #192 B: Zuordnungen wirken ab jetzt — die gespeicherten Tages- und
    # Stundenwerte tragen die Zuordnung ihres Aggregationslaufs. Vermerkt wird
    # nur eine ECHTE Änderung; ein erneutes Bestätigen derselben Wahl ist keine.
    # Themen-Kacheln (4.2.0, G2-2): ein Themen-Eintrag hat keine Historie — kein Vermerk.
    if not ist_thema and ist_echte_aenderung(vorher, quellen.get(field_id)):
        await _historie_vermerken(db, anlage, mapping, field_id)
    if ist_thema and quelle in QUELLEN_HA:
        # Beim ersten HA-Pick übernimmt ein Eintrag mit Vorgabe-Label «Eintrag n» den Klarnamen der Entität.
        await _thema_label_aus_ha(db, mapping, field_id, (body.entity_id or "").strip())
    # Klassische Struktur mitschreiben: HA → Sensor-Eintrag, sonst räumen. Ohne
    # das Räumen spränge die B8-2-Auflösung beim nächsten `/felder` über Stufe 1
    # („HA-Sensor zugeordnet") zurück auf HA und drehte die Wahl zurück.
    uebernehme_quelle_ins_mapping(
        mapping, field_id, quelle, (body.entity_id or "").strip() or None
    )
    anlage.sensor_mapping = mapping
    flag_modified(anlage, "sensor_mapping")
    # N-556: Zuordnen und Wegschalten stehen im Protokoll — in DIESER Sitzung (N-532).
    neu_text = _quelle_klartext(
        quellen.get(field_id),
        (body.quell_topic or "").strip() or None if quelle == QUELLE_GATEWAY else None,
    )
    await log_activity(
        kategorie="sensor_mapping",
        aktion=(
            "Datenquelle entfernt" if quelle == QUELLE_KEINE
            else "Datenquelle auf Standard gesetzt" if quelle == QUELLE_STANDARD
            else "Datenquelle zugeordnet"
        ),
        details=f"{anlage.anlagenname} · {await _feld_label(db, anlage, field_id)}: {alt_text} → {neu_text}",
        details_json={"field_id": field_id, "vorher": vorher or None,
                      "nachher": quellen.get(field_id)},
        anlage_id=anlage_id,
        db=db,
    )
    await db.commit()

    # Gateway-Service hot-reloaden, damit die Subscription der Änderung folgt.
    try:
        from backend.api.routes.mqtt_gateway import _reload_gateway
        await _reload_gateway(db)
    except Exception:  # Reload ist best-effort; Persistenz ist bereits committed.
        logger.warning("Gateway-Reload nach Quelle-Änderung fehlgeschlagen", exc_info=True)

    return {
        "gespeichert": True,
        "field_id": field_id,
        "quelle": quelle,
        "historie_hinweis": vermerk_lesen(mapping),
    }


# --- D2: Wizard-Uebernahme der Energy-Dashboard-Vorschlaege ------------------
class EnergyUebernahmeRequest(BaseModel):
    """Auswahl aus GET /sensor-mapping/{id}/suggest — nach Nutzer-Bestaetigung."""
    basis: dict[str, str] = {}                      # feld (einspeisung|netzbezug|pv_gesamt) -> entity_id
    investitionen: dict[str, dict[str, str]] = {}   # inv_id -> {feld -> entity_id}


# Suggest-Basis-Felder -> Datenquellen-Feld-IDs (energy-Registry).
_ENERGY_BASIS_FELD_IDS = {
    "einspeisung": "basis_energy_einspeisung_kwh",
    "netzbezug": "basis_energy_netzbezug_kwh",
    "pv_gesamt": "basis_energy_pv_gesamt_kwh",
}


@router.post("/{anlage_id}/energy-vorschlaege/uebernehmen")
async def uebernehme_energy_vorschlaege(
    anlage_id: int, body: EnergyUebernahmeRequest, db: AsyncSession = Depends(get_db, scope="function")
):
    """D2 (2026-07-18): Uebernimmt BESTAETIGTE Energy-Dashboard-Vorschlaege (#197)
    in die Datenquellen-Quellen — nie stumm, der Wizard zeigt die Auswahl vorher.

    Schreibt in denselben Store wie /felder/{fid}/quelle (HA-Transport = aktive
    Verbindung) und über dieselbe Schreib-Schicht zusätzlich in die klassische
    `sensor_mapping`-Struktur; nur Feld-IDs, die die Registry der Anlage kennt.
    """
    from sqlalchemy.orm.attributes import flag_modified
    from backend.services.datenquellen_mapping_sync import uebernehme_quelle_ins_mapping

    anlage = (
        await db.execute(select(Anlage).where(Anlage.id == anlage_id))
    ).scalar_one_or_none()
    if not anlage:
        raise HTTPException(status_code=404, detail="Anlage nicht gefunden")

    _api_url, _token, kind = await _resolve_ha(db)
    if kind not in ("ha_app", "ha_connector"):
        raise HTTPException(status_code=400, detail="Keine aktive HA-Verbindung")

    # Gueltige Feld-IDs der Anlage aus der Registry (wie /felder) — ohne die
    # `nur_manuell`-Felder: was auf der Fläche nicht zuordenbar ist, darf auch
    # der HA-Energie-Übernahmepfad nicht zuordnen (sonst entstünde eine
    # Zuordnung, die die Fläche gar nicht anbietet).
    erwartete = await build_expected_topics(db, anlage)
    gueltig = {
        _feld_id(e["match_key"]) for e in erwartete if not e.get("nur_manuell")
    }

    zuordnungen: list[tuple[str, str]] = []
    for feld, entity in (body.basis or {}).items():
        fid = _ENERGY_BASIS_FELD_IDS.get(feld)
        if fid and entity and fid in gueltig:
            zuordnungen.append((fid, entity))
    for inv_id, felder in (body.investitionen or {}).items():
        for feld, entity in (felder or {}).items():
            fid = feld_id(("inv_energy", inv_id, feld))
            if entity and fid in gueltig:
                zuordnungen.append((fid, entity))

    mapping = dict(anlage.sensor_mapping or {})
    quellen = dict(mapping.get(QUELLEN_KEY) or {})
    protokoll: list[str] = []
    labels = await _feld_labels(db, anlage) if zuordnungen else {}
    for fid, entity in zuordnungen:
        alt_text = _quelle_klartext(quellen.get(fid))
        quellen[fid] = {"quelle": kind, "entity_id": entity}
        uebernehme_quelle_ins_mapping(mapping, fid, kind, entity)
        protokoll.append(
            f"{labels.get(fid, fid)}: {alt_text} → {_quelle_klartext(quellen[fid])}"
        )
    mapping[QUELLEN_KEY] = quellen
    anlage.sensor_mapping = mapping
    flag_modified(anlage, "sensor_mapping")
    # N-556: eine Zeile für die ganze Übernahme, je Feld alt → neu — in DIESER
    # Sitzung (N-532). Ohne Zuordnung (leere Auswahl) keine Handlung, keine Zeile.
    if zuordnungen:
        await log_activity(
            kategorie="sensor_mapping",
            aktion=f"Energie-Dashboard-Vorschläge übernommen ({len(zuordnungen)})",
            details=f"{anlage.anlagenname} · " + " · ".join(protokoll),
            details_json={"felder": [fid for fid, _ in zuordnungen]},
            anlage_id=anlage_id,
            db=db,
        )
    await db.commit()

    return {"gespeichert": True, "anzahl": len(zuordnungen),
            "felder": [fid for fid, _ in zuordnungen]}
