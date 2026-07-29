"""
Datenquellen-Zuordnung — feld-zentrische Fläche (Datenquellen-V4 / B2).

SoT: docs/drafts/KONZEPT-DATENQUELLEN-V4.md §2b.

Liefert je Anlage die vollständige, gruppierte eedc-Feldliste (Anlage-Basis +
je aktiver Investition, Live + Energie) mit dem kanonischen Standard-Inbound-
Topic pro Feld. Grundlage für die „eine Quelle pro Feld"-Zuordnung.

**B2.1 (read-only):** nur Enumeration + Standard-Topic. Der Quell-Picker
(Wechsel MQTT-Inbound/Gateway/keine · HA-Sensor) und die Persistenz folgen in
B2.2/B5. Die aktive Quelle ist daher vorerst konstant der Standard-Inbound-Pfad.
"""

import asyncio
import json as json_mod
import logging
from datetime import date

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps import get_db
from backend.core.ha_integrations_wissen import analysiere_vorschlaege
from backend.models.anlage import Anlage
from backend.models.investition import Investition
from backend.services.datenquellen_resolver import resolve_effektive_quelle
from backend.services.live_sensor_config import extract_live_config
from backend.services.mqtt_topic_registry import build_expected_topics
from backend.services.mqtt_broker_settings import import_aktiviert
from backend.utils.investition_filter import aktiv_am_tag, sort_investitionen_nach_typ

logger = logging.getLogger(__name__)

router = APIRouter()

# Quell-Kennungen. B2.2 bietet die aktuell verfügbaren MQTT-Optionen; HA-Sensor
# und MQTT-Gateway folgen (P2 bzw. B3-Discovery). Präferenz-SoT HA > Gateway >
# Inbound > manuell (§2d); Default (kein Eintrag) = Standard-Inbound.
QUELLE_STANDARD = "mqtt_inbound_standard"
QUELLE_KEINE = "keine"
QUELLE_GATEWAY = "mqtt_gateway"
# HA-Sensor-Quellen (Schritt B): EINE Feld-Spalte „HA-Sensor", zwei Transporte —
# ha_app = Supervisor-Token (Add-on), ha_connector = Remote-HA per LL-Token
# (ha_remote/B4a). Der Resolver (B5) liest den Wert je nach aktiver Verbindung.
QUELLE_HA_APP = "ha_app"
QUELLE_HA_CONNECTOR = "ha_connector"
QUELLEN_HA = {QUELLE_HA_APP, QUELLE_HA_CONNECTOR}
QUELLEN_ERLAUBT = {QUELLE_STANDARD, QUELLE_KEINE, QUELLE_GATEWAY, QUELLE_HA_APP, QUELLE_HA_CONNECTOR}


# ─── HA-Verbindung auflösen (Supervisor bevorzugt, sonst Remote-HA) ──────
def _is_int_state(v) -> bool:
    try:
        int(str(v).strip())
        return True
    except (ValueError, TypeError):
        return False


async def _resolve_ha(db: AsyncSession) -> tuple:
    """(api_url, token, quelle_kind) der aktiven HA-Verbindung — zentraler Helper.

    Delegiert an `services.ha_connection.resolve_ha_connection` (EINE Wahrheit,
    auch von der Live-Engine genutzt). kind = ha_app (Supervisor) | ha_connector
    (Remote-HA) | None.
    """
    from backend.services.ha_connection import resolve_ha_connection
    return await resolve_ha_connection(db)


async def _ha_states_detail(db: AsyncSession, entity_ids: set) -> dict:
    """Detail-Batch der HA-Entities: `{eid: {"wert","einheit","state_class"}}`.

    EIN `/states`-Call gegen die aktive HA-Verbindung (Supervisor ODER Remote-HA).
    `wert` (C1, Wert-Anzeige) + `einheit`/`state_class` (§2i-Validierung: Einheiten-
    Mismatch #200, fehlendes state_class). Nur die Fläche — Engine unberührt (C2).
    Nicht erreichbar → leeres Dict (Feld amber, keine Validierungs-Fehlalarme).
    """
    if not entity_ids:
        return {}
    api_url, token, _ = await _resolve_ha(db)
    if not api_url or not token:
        return {}
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(f"{api_url}/states", headers={"Authorization": f"Bearer {token}"})
    except Exception:  # noqa: BLE001 — Netzwerk-/TLS-Fehler → keine Werte (Feld amber)
        return {}
    if resp.status_code != 200:
        return {}
    out: dict = {}
    for st in resp.json():
        eid = st.get("entity_id")
        if eid not in entity_ids:
            continue
        try:
            wert = float(st.get("state"))
        except (ValueError, TypeError):
            wert = None
        attrs = st.get("attributes") or {}
        out[eid] = {
            "wert": wert,
            "einheit": attrs.get("unit_of_measurement"),
            "state_class": attrs.get("state_class"),
            # Klarname für die Zeilen-Anzeige: die nackte entity_id sagt vielen
            # nichts, und die V3-Fläche zeigte hier den Friendly Name
            # (Rainer-PN 2026-07-25). Kommt aus demselben Batch — kein Zusatzabruf.
            "friendly_name": attrs.get("friendly_name"),
        }
    return out


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


def _ha_sensor_relevant(state: dict, filter_energy: bool) -> bool:
    if not str(state.get("entity_id", "")).startswith("sensor."):
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

# Additive Sub-Map in anlage.sensor_mapping: {field_id: {"quelle": ...}}. Stört
# die bestehende HA-Struktur (basis/investitionen) nicht; B8 führt beide zusammen.
QUELLEN_KEY = "quellen"


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
async def mqtt_discovery(data: DiscoveryRequest, db: AsyncSession = Depends(get_db)) -> DiscoveryResponse:
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
async def mqtt_level(data: LevelRequest, db: AsyncSession = Depends(get_db)) -> LevelResponse:
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


def _feld_id(match_key) -> str:
    """Stabile Feld-Kennung aus dem match_key (Zuordnungs-Schlüssel)."""
    return "_".join(str(x) for x in match_key)


async def _standard_topic_suffix(db: AsyncSession, anlage: Anlage, field_id: str) -> str | None:
    """Standard-Inbound-Topic-Suffix eines Feldes (`live/…` bzw. `energy/…`).

    C2a: Der Gateway re-publisht nach `eedc/{aid}/{ziel_key}`. Nur wenn ziel_key =
    genau dieses Suffix ist, trifft der Wert die Inbound-Subscription
    `eedc/+/live|energy/#` und fließt durch die bestehende Inbound-Maschinerie
    (Live + kWh). Ableitung aus der Topic-Registry-SoT (kein Neu-Basteln).
    """
    invs = (await db.execute(
        select(Investition).where(Investition.anlage_id == anlage.id, aktiv_am_tag(date.today()))
    )).scalars().all()
    invs = sort_investitionen_nach_typ(invs)
    for e in await build_expected_topics(db, anlage, investitionen=invs):
        if _feld_id(e["match_key"]) == field_id:
            # topic = eedc/{aid}_{slug}/live/… → Suffix ab dem 3. Segment.
            parts = e["topic"].split("/", 2)
            return parts[2] if len(parts) == 3 else None
    return None


def _quellen_map(anlage: Anlage) -> dict:
    """Liest die Feld→Quelle-Map aus anlage.sensor_mapping (leer wenn keine)."""
    mapping = anlage.sensor_mapping or {}
    q = mapping.get(QUELLEN_KEY) if isinstance(mapping, dict) else None
    return q if isinstance(q, dict) else {}


def _pick(d, *keys):
    """Toleranter Dict-Zugriff (int/str-Schlüssel-Mischung im Cache)."""
    if isinstance(d, dict):
        for k in keys:
            if k in d:
                return d[k]
    return None


def _cache_wert(cache, aid: int, match_key) -> tuple:
    """Aktueller (wert, iso_zeit) aus dem MQTT-Inbound-Cache per match_key — sonst (None, None)."""
    if cache is None:
        return (None, None)
    live = _pick(cache._live, aid, str(aid)) or {}
    energy = _pick(cache._energy, aid, str(aid)) or {}
    kind = match_key[0]
    entry = None
    if kind == "basis_live":
        entry = (live.get("basis") or {}).get(match_key[1])
    elif kind == "basis_energy":
        entry = energy.get(match_key[1])
    elif kind == "inv_live":
        inv_map = _pick(live.get("inv") or {}, match_key[1], str(match_key[1]), int(match_key[1])) or {}
        entry = inv_map.get(match_key[2])
    elif kind == "inv_energy":
        entry = energy.get(f"inv/{match_key[1]}/{match_key[2]}")
    if not entry:
        return (None, None)
    val, ts = entry
    return (val, ts.isoformat() if hasattr(ts, "isoformat") else ts)


# ─── HA-Sensor-Discovery (Schritt B) ─────────────────────────────────
class HaSensor(BaseModel):
    entity_id: str
    friendly_name: str | None = None
    unit: str | None = None
    device_class: str | None = None
    state: str | None = None


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
    db: AsyncSession = Depends(get_db),
) -> HaSensorenResponse:
    """HA-Entities für den HA-Sensor-Picker — Supervisor ODER Remote-HA (verbindungs-transparent).

    Liest `/api/states` der aktiven HA-Verbindung und filtert energie-relevante
    Sensoren (Symmetrie zu sensor_mapping.available-sensors). `quelle` sagt dem
    Frontend, welche Quell-Kennung zu persistieren ist (ha_app/ha_connector).
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
    sensoren: list[HaSensor] = []
    for st in resp.json():
        if not _ha_sensor_relevant(st, filter_energy):
            continue
        attrs = st.get("attributes", {}) or {}
        sensoren.append(HaSensor(
            entity_id=st.get("entity_id", ""),
            friendly_name=attrs.get("friendly_name"),
            unit=attrs.get("unit_of_measurement") or None,
            device_class=attrs.get("device_class") or None,
            state=st.get("state"),
        ))
    sensoren.sort(key=lambda s: s.entity_id)
    # #343 A: Wissensbasis-Vorschlaege fuer das Ziel-Feld + Anti-Empfehlungen.
    assistenz = analysiere_vorschlaege([se.entity_id for se in sensoren], feld=feld, inv_typ=inv_typ)
    return HaSensorenResponse(
        verfuegbar=True, quelle=kind, sensoren=sensoren,
        integrationen=assistenz["integrationen"],
        vorschlaege=[HaVorschlag(**v) for v in assistenz["vorschlaege"]],
        warnungen=assistenz["warnungen"],
    )


# --- Takt-Check beim Waehlen (#343 Baustein B, D2) ---------------------------
class TaktCheckRequest(BaseModel):
    entity_id: str


class TaktCheckResponse(BaseModel):
    geprueft: bool = False
    problem: dict | None = None


@router.post("/{anlage_id}/ha/takt-check", response_model=TaktCheckResponse)
async def ha_takt_check(
    anlage_id: int, req: TaktCheckRequest, db: AsyncSession = Depends(get_db)
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


@router.get("/{anlage_id}/felder")
async def get_datenquellen_felder(anlage_id: int, db: AsyncSession = Depends(get_db)):
    """Gruppierte Feldliste (Basis + je Investition) mit Standard-Topic + aktiver Quelle."""
    anlage = (
        await db.execute(select(Anlage).where(Anlage.id == anlage_id))
    ).scalar_one_or_none()
    if not anlage:
        raise HTTPException(status_code=404, detail="Anlage nicht gefunden")

    # Regel 0a: Gruppen in kanonischer Investitionstyp-Reihenfolge (nicht DB-Order).
    # aktiv_am_tag(heute) = aktiv-Flag + Anschaffung ≤ heute ≤ Stilllegung
    # (beide Grenzen, [[feedback_anschaffungsdatum_grenze]]) — NICHT aktiv_jetzt(),
    # das die Anschaffungs-Untergrenze nicht prüft.
    invs = (await db.execute(
        select(Investition).where(Investition.anlage_id == anlage_id, aktiv_am_tag(date.today()))
    )).scalars().all()
    invs = sort_investitionen_nach_typ(invs)
    eintraege = await build_expected_topics(db, anlage, investitionen=invs)

    quellen = _quellen_map(anlage)
    # Vereinheitlichter Invert-Store (quellen-unabhängig, feld-/wert-level).
    invert_store = (anlage.sensor_mapping or {}).get("invertieren") or {}

    # Gateway-Quell-Topics dieser Anlage (mapping_id → quell_topic) für die
    # Anzeige der aktiven Gateway-Zuordnung je Feld (B3.3) + ziel_key→Row-Index
    # (nur AKTIVE Zeilen) für die B8-2-Auflösung / §2h-Deaktivierung.
    from backend.models.mqtt_gateway_mapping import MqttGatewayMapping
    gw_rows = (await db.execute(
        select(MqttGatewayMapping).where(MqttGatewayMapping.anlage_id == anlage_id)
    )).scalars().all()
    gateway_topics = {m.id: m.quell_topic for m in gw_rows}
    gw_by_zielkey = {m.ziel_key: m for m in gw_rows if getattr(m, "aktiv", True)}

    # Aktuelle Live-/Energy-Werte aus dem MQTT-Inbound-Cache (B2.3). Ohne aktiven
    # Subscriber bleibt der Cache leer → wert=None → UI zeigt „—".
    from backend.services.mqtt_inbound_service import get_mqtt_inbound_service
    svc = get_mqtt_inbound_service()
    cache = svc.cache if svc else None

    # HA-Verbindungstransport (Supervisor ODER Remote) + Live-Maps für die
    # B8-2-Auflösung noch NICHT zugeordneter Felder. Der zu PERSISTIERENDE
    # Transport nutzt denselben statischen Fallback wie die B8-1-Migration
    # (Add-on → ha_app, sonst ha_connector): ein per sensor_mapping HA-gemapptes
    # Feld ist HA-bequellt, auch wenn die Verbindung gerade nicht aktiv ist (kind
    # None) — die reale Verbindung löst der Read-Pfad ohnehin auf, das Feld zeigt
    # dann ehrlich amber statt fälschlich Inbound zu werden.
    from backend.core.config import HA_INTEGRATION_AVAILABLE
    ha_url, _ha_token, ha_kind = await _resolve_ha(db)
    ha_kind_persist = ha_kind or (QUELLE_HA_APP if HA_INTEGRATION_AVAILABLE else QUELLE_HA_CONNECTOR)
    basis_live, inv_live_map, _bi, _ii = extract_live_config(anlage)

    # Pass 1 — effektive Quelle je Feld: expliziter `quellen`-Eintrag gilt; sonst
    # 3-Stufen-Auflösung (B8-2, Gernots Regel): HA-Sensor → HA · Gateway-Topic →
    # Gateway · Inbound-mit-Wert → Inbound · sonst „keine". POSITIVE Evidenz
    # (HA/Gateway/Inbound-mit-Wert) wird additiv festgeschrieben, damit Anzeige
    # UND Read-Through (C2a/C2b) übereinstimmen (HA-first echt statt MQTT-Merge).
    # Stummes Inbound bleibt UNENTSCHIEDEN (kein Eintrag) → bei jedem Aufruf neu
    # bewertet, self-healing, kein auto-„keine"-Ballast.
    effektiv: dict[str, dict] = {}
    cache_wert: dict[str, tuple] = {}
    neu_persistieren: dict[str, dict] = {}
    gw_deaktivieren: list = []
    for e in eintraege:
        fid = _feld_id(e["match_key"])
        cw = _cache_wert(cache, anlage_id, e["match_key"])
        cache_wert[fid] = cw
        eintrag = quellen.get(fid)
        if eintrag:
            effektiv[fid] = eintrag
            continue
        display_q, persist_entry, gw_row = resolve_effektive_quelle(
            fid, e["topic"], anlage.sensor_mapping or {},
            basis_live, inv_live_map, gw_by_zielkey, ha_kind_persist, cw[0] is not None,
        )
        effektiv[fid] = persist_entry or {"quelle": display_q}
        if persist_entry is not None:
            neu_persistieren[fid] = persist_entry
            if gw_row is not None and getattr(gw_row, "aktiv", True):
                gw_deaktivieren.append(gw_row)

    # HA-zugeordnete Entities einmalig batch-lesen (explizit + neu aufgelöst):
    # Wert (C1) + Einheit/state_class (§2i-Validierung).
    ha_entities = {
        v.get("entity_id") for v in effektiv.values()
        if isinstance(v, dict) and v.get("quelle") in QUELLEN_HA and v.get("entity_id")
    }
    ha_detail = await _ha_states_detail(db, ha_entities)
    ha_werte = {eid: d.get("wert") for eid, d in ha_detail.items()}
    ha_namen = {eid: d.get("friendly_name") for eid, d in ha_detail.items()}

    # §2i — proaktive Zuordnungs-Validierung (rein diagnostisch): pro Feld eine
    # Liste `probleme`. Einheit-Mismatch (#200) + fehlendes state_class je HA-Feld;
    # Aggregat-Redundanz (PV gesamt/Netz kombi neben Komponenten); HA-Doppelmapping.
    from backend.services.datenquellen_validierung import (
        einheit_problem, state_class_problem,
        finde_redundante_aggregate, finde_doppelmappings, stufe_bedarf_ein,
    )
    feld_einheit = {_feld_id(e["match_key"]): e.get("einheit", "") for e in eintraege}
    feld_feld = {_feld_id(e["match_key"]): e.get("feld", "") for e in eintraege}
    feld_typ = {_feld_id(e["match_key"]): e.get("typ", "basis") for e in eintraege}
    feld_bedarf = {_feld_id(e["match_key"]): e.get("bedarf", "optional") for e in eintraege}
    feld_bedarf_gruppe = {_feld_id(e["match_key"]): e.get("bedarf_gruppe") for e in eintraege}
    feld_bedingung_anlage = {
        _feld_id(e["match_key"]): e.get("bedingung_anlage") for e in eintraege
    }
    vorhandene_inv_typen = {i.typ for i in invs}
    probleme_je_feld: dict[str, list] = {}

    def _add_problem(fid: str, p: dict | None) -> None:
        if p:
            probleme_je_feld.setdefault(fid, []).append(p)

    ha_zuordnungen: dict[str, str] = {}
    for fid, v in effektiv.items():
        if isinstance(v, dict) and v.get("quelle") in QUELLEN_HA and v.get("entity_id"):
            eid = v["entity_id"]
            ha_zuordnungen[fid] = eid
            d = ha_detail.get(eid)
            if d:  # nur wenn HA erreichbar (sonst keine Einheit → kein Fehlalarm)
                _add_problem(fid, einheit_problem(feld_einheit.get(fid), d.get("einheit")))
                _add_problem(fid, state_class_problem(feld_einheit.get(fid), d.get("state_class")))
    felder_belegt = [
        {"id": fid, "feld": feld_feld[fid], "typ": feld_typ[fid],
         "belegt": (effektiv.get(fid, {}).get("quelle", QUELLE_KEINE) != QUELLE_KEINE)}
        for fid in feld_feld
    ]
    for fid, p in finde_redundante_aggregate(felder_belegt).items():
        _add_problem(fid, p)
    for fid, p in finde_doppelmappings(ha_zuordnungen).items():
        _add_problem(fid, p)

    # §2i-6 — Bedarfs-Einstufung: ist ein LEERES Feld überhaupt eine Lücke?
    # Ohne sie zählte der Rollup Aggregat-, Alternativ- und Optional-Felder als
    # „ohne Quelle" und meldete auf einer korrekt eingerichteten Anlage Fehlalarm.
    _bedarf_eingabe = [
        {"id": fid,
         "feld": feld_feld[fid],
         "typ": feld_typ[fid],
         "belegt": (effektiv.get(fid, {}).get("quelle", QUELLE_KEINE) != QUELLE_KEINE),
         "bedarf": feld_bedarf.get(fid, "optional"),
         "bedarf_gruppe": feld_bedarf_gruppe.get(fid),
         "bedingung_anlage": feld_bedingung_anlage.get(fid)}
        for fid in feld_feld
    ]
    bedarf_je_feld = stufe_bedarf_ein(_bedarf_eingabe, vorhandene_inv_typen)

    # Pass 2 — Reihenfolge-erhaltend nach gruppe_id gruppieren + Response bauen.
    gruppen: list[dict] = []
    index: dict[str, dict] = {}
    for e in eintraege:
        gid = e.get("gruppe_id", "basis")
        gruppe = index.get(gid)
        if gruppe is None:
            gruppe = {
                "id": gid,
                "titel": e.get("gruppe_titel", "—"),
                "typ": e.get("typ", "basis"),
                "felder": [],
            }
            index[gid] = gruppe
            gruppen.append(gruppe)
        fid = _feld_id(e["match_key"])
        eintrag = effektiv.get(fid) or {}
        q = eintrag.get("quelle", QUELLE_KEINE)
        # Wert der TATSÄCHLICH aufgelösten Quelle lesen: HA → REST-Batch, Inbound/
        # Gateway → Cache (Gateway republisht nach C2a-Fix über das Standard-Topic
        # in denselben Inbound-Cache), keine → keiner. Amber = Ausfall sichtbar §2d.
        if q in QUELLEN_HA:
            wert, wert_zeit = ha_werte.get(eintrag.get("entity_id")), None
        elif q in (QUELLE_STANDARD, QUELLE_GATEWAY):
            wert, wert_zeit = cache_wert.get(fid, (None, None))
        else:  # keine
            wert, wert_zeit = None, None
        gruppe["felder"].append({
            "id": fid,
            "feld": e.get("feld", ""),
            # Investitionstyp der Gruppe — für die Wissensbasis-Vorschläge im
            # HA-Picker (#343 A; 'basis' für Anlagen-Felder).
            "typ": gruppe.get("typ", ""),
            "label": e.get("feld_label", e.get("label", "")),
            "einheit": e.get("einheit", ""),
            "kategorie": e.get("kategorie", "energy"),
            "hinweis": e.get("hinweis", ""),
            "standard_topic": e["topic"],
            "quelle": q,
            # Gateway-Quell-Topic (falls zugeordnet) für die UI-Anzeige.
            "gateway_topic": gateway_topics.get(eintrag.get("mapping_id")),
            # Zugeordnete HA-Entity (nur bei quelle ha_app/ha_connector).
            "ha_entity": eintrag.get("entity_id"),
            # Klarname derselben Entity (None, wenn HA sie nicht kennt).
            "ha_name": ha_namen.get(eintrag.get("entity_id")),
            # Invert-Modell (Datenquellen-V4): Vorzeichen-Flip ist quellen-
            # UNABHÄNGIG, aus dem vereinheitlichten Store gelesen (nicht aus dem
            # quellen-Eintrag), am Read-Endwert angewendet.
            "invertieren": bool(invert_store.get(fid)),
            "wert": wert,
            "wert_zeit": wert_zeit,
            # §2i: diagnostische Zuordnungs-Probleme (Einheit/state_class/Redundanz/
            # Doppelmapping) — leere Liste, wenn alles sauber.
            "probleme": probleme_je_feld.get(fid, []),
            # §2i-6: „pflicht" | "optional" | "inaktiv" (+ Begründung). Steuert
            # rot/aufgeklappt vs. leise und die Rollup-Zählung.
            "bedarf": bedarf_je_feld.get(fid, {}).get("bedarf", "optional"),
            "bedarf_grund": bedarf_je_feld.get(fid, {}).get("grund"),
            "bedarf_text": bedarf_je_feld.get(fid, {}).get("text"),
        })

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

    # Verfügbarkeit der Quell-Achsen (Schritt B Gating): HA (Supervisor ODER
    # Remote-HA) + MQTT (Broker aktiv). Steuert Aktiv/Ausgegraut der Buttons.
    verfuegbarkeit = {
        "ha": bool(ha_url),
        "ha_quelle": ha_kind,
        "mqtt": await _mqtt_import_aktiviert(db),
    }

    return {"anlage_id": anlage_id, "gruppen": gruppen, "verfuegbarkeit": verfuegbarkeit}


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
    anlage_id: int, field_id: str, body: InvertSetRequest, db: AsyncSession = Depends(get_db)
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

    mapping = dict(anlage.sensor_mapping or {})
    invert = dict(mapping.get("invertieren") or {})
    if body.invertieren:
        invert[field_id] = True
    else:
        invert.pop(field_id, None)
    mapping["invertieren"] = invert
    anlage.sensor_mapping = mapping
    flag_modified(anlage, "sensor_mapping")
    await db.commit()
    return {"field_id": field_id, "invertieren": bool(body.invertieren)}


@router.post("/{anlage_id}/felder/{field_id}/quelle")
async def set_feld_quelle(
    anlage_id: int, field_id: str, body: QuelleSetRequest, db: AsyncSession = Depends(get_db)
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

    anlage = (
        await db.execute(select(Anlage).where(Anlage.id == anlage_id))
    ).scalar_one_or_none()
    if not anlage:
        raise HTTPException(status_code=404, detail="Anlage nicht gefunden")

    mapping = dict(anlage.sensor_mapping or {})
    quellen = dict(mapping.get(QUELLEN_KEY) or {})
    vorher = quellen.get(field_id) or {}
    alt_mapping_id = vorher.get("mapping_id")

    async def _lade_mapping_row(mid):
        if mid is None:
            return None
        return (await db.execute(
            select(MqttGatewayMapping).where(MqttGatewayMapping.id == mid)
        )).scalar_one_or_none()

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
        row = await _lade_mapping_row(alt_mapping_id)
        if row is not None:
            await db.delete(row)
            await db.flush()
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
    # Klassische Struktur mitschreiben: HA → Sensor-Eintrag, sonst räumen. Ohne
    # das Räumen spränge die B8-2-Auflösung beim nächsten `/felder` über Stufe 1
    # („HA-Sensor zugeordnet") zurück auf HA und drehte die Wahl zurück.
    uebernehme_quelle_ins_mapping(
        mapping, field_id, quelle, (body.entity_id or "").strip() or None
    )
    anlage.sensor_mapping = mapping
    flag_modified(anlage, "sensor_mapping")
    await db.commit()

    # Gateway-Service hot-reloaden, damit die Subscription der Änderung folgt.
    try:
        from backend.api.routes.mqtt_gateway import _reload_gateway
        await _reload_gateway(db)
    except Exception:  # Reload ist best-effort; Persistenz ist bereits committed.
        logger.warning("Gateway-Reload nach Quelle-Änderung fehlgeschlagen", exc_info=True)

    return {"gespeichert": True, "field_id": field_id, "quelle": quelle}


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
    anlage_id: int, body: EnergyUebernahmeRequest, db: AsyncSession = Depends(get_db)
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

    # Gueltige Feld-IDs der Anlage aus der Registry (wie /felder).
    erwartete = await build_expected_topics(db, anlage)
    gueltig = {_feld_id(e["match_key"]) for e in erwartete}

    zuordnungen: list[tuple[str, str]] = []
    for feld, entity in (body.basis or {}).items():
        fid = _ENERGY_BASIS_FELD_IDS.get(feld)
        if fid and entity and fid in gueltig:
            zuordnungen.append((fid, entity))
    for inv_id, felder in (body.investitionen or {}).items():
        for feld, entity in (felder or {}).items():
            fid = f"inv_energy_{inv_id}_{feld}"
            if entity and fid in gueltig:
                zuordnungen.append((fid, entity))

    mapping = dict(anlage.sensor_mapping or {})
    quellen = dict(mapping.get(QUELLEN_KEY) or {})
    for fid, entity in zuordnungen:
        quellen[fid] = {"quelle": kind, "entity_id": entity}
        uebernehme_quelle_ins_mapping(mapping, fid, kind, entity)
    mapping[QUELLEN_KEY] = quellen
    anlage.sensor_mapping = mapping
    flag_modified(anlage, "sensor_mapping")
    await db.commit()

    return {"gespeichert": True, "anzahl": len(zuordnungen),
            "felder": [fid for fid, _ in zuordnungen]}
