# Konzept: MQTT Gateway — Topic-Translator für EEDC

> Erstellt: 2026-03-20 | Aktualisiert: 2026-03-22 | Status: **Stufe 0+1 implementiert** (v3.4.5)

## Implementierungsstand

| Stufe | Status | Version | Beschreibung |
|-------|--------|---------|-------------|
| **Stufe 0** | **Implementiert** | v3.4.5 | Connector → MQTT Bridge. Konfigurierte Geräte-Connectors publishen automatisch Live-Watt auf MQTT-Inbound-Topics. 5 Connectors mit `read_live()`: Shelly 3EM, OpenDTU, Fronius, sonnenBatterie, go-eCharger. SMA/Kostal/Tasmota SML nur kWh (kein Live). |
| **Stufe 1** | **Implementiert** | v3.4.5 | Manuelles Topic-Mapping (MVP). DB-Modell, CRUD-API, Hot-Reload, Test-Topic-Endpoint, UI auf MQTT-Inbound-Seite. Payload-Transformation: Plain/JSON/Array, Faktor, Offset, Invertierung. |
| **Stufe 2** | Offen | — | Geräte-Presets (Shelly, OpenDTU, Tasmota, go-eCharger, SMA, Fronius, Zigbee2MQTT, Victron). 3 Klicks statt manueller Konfiguration. |
| **Stufe 3** | Offen | — | Topic-Discovery. Temporär auf `#` subscriben, Pattern-Erkennung, Mapping-Vorschläge. |

### Implementierte Dateien

**Backend:**
- `backend/models/mqtt_gateway_mapping.py` — DB-Modell (SQLAlchemy)
- `backend/services/mqtt_gateway_service.py` — Gateway-Service + `transform_payload()`
- `backend/services/connector_mqtt_bridge.py` — Connector-Polling-Bridge
- `backend/api/routes/mqtt_gateway.py` — 8 API-Endpoints (CRUD, Status, Test-Topic, Test-Transform)
- `backend/services/connectors/base.py` — `LiveSnapshot` Dataclass + `read_live()` Base-Methode

**Frontend:**
- `frontend/src/components/live/MqttGateway.tsx` — Gateway-UI-Komponente (Mapping-Liste, Formular, Topic-Test)
- `frontend/src/api/liveDashboard.ts` — Gateway API-Types + Endpoints

### API-Endpoints (Stufe 1)

```
GET    /api/live/mqtt/gateway/mappings          — Alle Mappings listen
POST   /api/live/mqtt/gateway/mappings          — Neues Mapping + Hot-Reload
PUT    /api/live/mqtt/gateway/mappings/{id}     — Mapping bearbeiten + Hot-Reload
DELETE /api/live/mqtt/gateway/mappings/{id}     — Mapping löschen + Hot-Reload
GET    /api/live/mqtt/gateway/status            — Status + Statistiken
POST   /api/live/mqtt/gateway/reload            — Hot-Reload
POST   /api/live/mqtt/gateway/test-topic        — Topic subscriben + Payload anzeigen
POST   /api/live/mqtt/gateway/test-transform    — Payload-Transformation testen
```

### Abweichungen vom Konzept

- **Option A (Re-Publish)** gewählt wie empfohlen — Gateway publisht transformierte Werte per MQTT, sichtbar im Broker
- **Connector-Bridge** nutzt ebenfalls Re-Publish (kein direkter Cache-Inject)
- **Preset-Registry** noch nicht implementiert (Stufe 2)
- **Wildcard-Mappings** noch nicht implementiert (exakter Topic-Match in Stufe 1)
- **Separater Broker** nicht unterstützt — Gateway nutzt denselben Broker wie MQTT-Inbound

---

## Motivation

EEDC MQTT-Inbound erwartet Daten auf fest definierten Topics (`eedc/{id}/live/...`).
Viele Nutzer haben bereits MQTT-fähige Geräte (SMA, Fronius, Shelly, Tasmota,
go-eCharger, Zigbee2MQTT, etc.), die auf **herstellerspezifischen Topics** publishen.

**Heute** muss der Nutzer eine externe Bridge aufsetzen (Node-RED, HA-Automation,
eigenes Script), um z.B. `shellies/em3/emeter/0/power` → `eedc/1/live/einspeisung_w`
zu übersetzen. Das ist die größte Einstiegshürde für Standalone-Nutzer ohne Home Assistant.

**Ziel:** Ein in EEDC integriertes MQTT-Gateway, das vorhandene Topics direkt auf
EEDC-Inbound-Topics mapped — konfigurierbar per UI, ohne externe Tools.

## Abgrenzung

| Funktion | MQTT-Inbound (existiert) | MQTT-Gateway (neu) |
|---|---|---|
| **Aufgabe** | Empfängt EEDC-formatierte Topics | Übersetzt fremde Topics → EEDC-Format |
| **Topics** | `eedc/{id}/live/...` (fix) | Beliebige Quell-Topics (konfigurierbar) |
| **Payload** | Nur Plain-Number | Plain-Number, JSON-Pfad, Array-Index |
| **Zielgruppe** | Jeder mit MQTT-Publish-Fähigkeit | Nutzer mit vorhandenen MQTT-Geräten |
| **Abhängigkeit** | Keine | Setzt MQTT-Inbound voraus (nutzt es intern) |

Das Gateway ersetzt MQTT-Inbound nicht — es **füttert** es. Die gesamte bestehende
Inbound-Pipeline (Cache, Energy-Snapshots, Monatsabschluss-Vorschläge) bleibt unverändert.

## Architektur

```
Externe MQTT-Geräte              MQTT Gateway (neu)              MQTT Inbound (existiert)
┌──────────────┐          ┌──────────────────────────┐          ┌──────────────────┐
│ SMA Tripower │──┐       │                          │          │                  │
│ Shelly 3EM   │──┤       │  1. Subscribe auf        │  publish │  Subscribe auf   │
│ Tasmota      │──┼──MQTT─│     konfigurierte Topics │──MQTT──→│  eedc/+/live/#   │
│ go-eCharger  │──┤       │  2. Payload extrahieren  │          │  eedc/+/energy/# │
│ Zigbee2MQTT  │──┘       │  3. Optional umrechnen   │          │                  │
│ OpenDTU      │          │  4. Auf EEDC-Topic publ. │          │  → Cache         │
└──────────────┘          └──────────────────────────┘          │  → Energy History│
                            Konfigurierbar per UI                │  → Monatsabschl. │
                                                                └──────────────────┘
```

**Interner Datenfluss (kein zweiter MQTT-Roundtrip nötig):**

Das Gateway muss die transformierten Werte nicht zwingend per MQTT re-publishen.
Es kann den `MqttInboundCache` auch **direkt** befüllen:

```python
# Option A: Re-Publish per MQTT (sichtbar im Broker, debugbar)
await client.publish(f"eedc/1/live/einspeisung_w", str(wert))

# Option B: Direkt in Cache injizieren (effizienter, kein Roundtrip)
cache.on_message(f"eedc/1/live/einspeisung_w", str(wert))
```

**Empfehlung: Option A (Re-Publish).** Die Werte sind dann im Broker sichtbar,
was das Debugging drastisch vereinfacht (`mosquitto_sub -t "eedc/#" -v`).
Der zusätzliche Overhead ist vernachlässigbar.

## Datenmodell

### Mapping-Regel (eine pro Quell-Topic)

```python
@dataclass
class MqttMapping:
    id: int                     # DB-Primary-Key
    anlage_id: int              # Ziel-Anlage
    quell_topic: str            # z.B. "shellies/em3/emeter/0/power"
    ziel_key: str               # z.B. "live/einspeisung_w" oder "live/inv/3/leistung_w"
    payload_typ: str            # "plain" | "json" | "json_array"
    json_pfad: str | None       # z.B. "power" oder "Body.Data.PAC.Value"
    array_index: int | None     # z.B. 11 (für go-eCharger nrg[11])
    faktor: float               # Default 1.0 (z.B. 1000 für kW→W)
    offset: float               # Default 0.0 (z.B. für Kalibrierung)
    invertieren: bool           # Default False (True → Wert × -1)
    aktiv: bool                 # Mapping ein/ausschalten
    preset_id: str | None       # z.B. "shelly_3em" (wenn aus Preset erstellt)
    beschreibung: str | None    # User-Notiz
```

### DB-Speicherung

Entweder als eigene Tabelle (`mqtt_gateway_mappings`) oder als JSON in der
bestehenden `settings`-Tabelle (Key `mqtt_gateway`). Empfehlung: **Eigene Tabelle**,
da die Anzahl der Mappings variabel ist und pro Anlage/Investition zugeordnet wird.

```sql
CREATE TABLE mqtt_gateway_mapping (
    id INTEGER PRIMARY KEY,
    anlage_id INTEGER NOT NULL REFERENCES anlage(id),
    quell_topic TEXT NOT NULL,
    ziel_key TEXT NOT NULL,          -- "live/einspeisung_w", "live/inv/3/leistung_w"
    payload_typ TEXT DEFAULT 'plain', -- plain, json, json_array
    json_pfad TEXT,
    array_index INTEGER,
    faktor REAL DEFAULT 1.0,
    offset REAL DEFAULT 0.0,
    invertieren BOOLEAN DEFAULT 0,
    aktiv BOOLEAN DEFAULT 1,
    preset_id TEXT,
    beschreibung TEXT,
    erstellt_am TEXT DEFAULT CURRENT_TIMESTAMP
);
```

## Payload-Transformation

### Unterstützte Formate

**1. Plain Number** (häufigster Fall)
```
Topic:   shellies/em3/emeter/0/power
Payload: 1234.5
→ Direkt als Float
```

**2. JSON mit Pfad**
```
Topic:   zigbee2mqtt/wp_stromzaehler
Payload: {"power": 2100, "energy": 15.7, "voltage": 230}
Pfad:    "power"
→ Extrahiert: 2100
```

**3. Verschachteltes JSON**
```
Topic:   fronius/powerflow
Payload: {"Body": {"Data": {"Site": {"P_PV": 4200}}}}
Pfad:    "Body.Data.Site.P_PV"
→ Extrahiert: 4200
```

**4. JSON-Array**
```
Topic:   go-echarger/abc123/nrg
Payload: [230.1, 0.9, 207, ..., 0, 2450.5]
Index:   11
→ Extrahiert: 2450.5
```

### Transformation-Pipeline

```
Rohwert → JSON-Extraktion → × Faktor → + Offset → × (-1 wenn invertieren) → Float
```

**Implementierung:**

```python
def transform_payload(
    payload: str,
    payload_typ: str,
    json_pfad: str | None,
    array_index: int | None,
    faktor: float,
    offset: float,
    invertieren: bool,
) -> float | None:
    """Transformiert einen MQTT-Payload in einen Float-Wert."""
    try:
        if payload_typ == "plain":
            raw = float(payload)

        elif payload_typ == "json":
            data = json.loads(payload)
            for key in json_pfad.split("."):
                data = data[key]
            raw = float(data)

        elif payload_typ == "json_array":
            data = json.loads(payload)
            raw = float(data[array_index])

        else:
            return None

        result = raw * faktor + offset
        if invertieren:
            result = -result
        return result

    except (ValueError, KeyError, IndexError, TypeError, json.JSONDecodeError):
        return None
```

## Geräte-Presets

Vordefinierte Mapping-Vorlagen für gängige Geräte. Der User wählt ein Preset,
gibt seinen Topic-Prefix an, und alle Mappings werden automatisch angelegt.

### Preset-Datenstruktur

```python
@dataclass
class GatewayPreset:
    id: str                     # z.B. "shelly_3em"
    name: str                   # z.B. "Shelly 3EM"
    hersteller: str             # z.B. "Shelly"
    beschreibung: str
    topic_prefix_template: str  # z.B. "shellies/{device_id}"
    variablen: list[str]        # z.B. ["device_id"] — User muss diese ausfüllen
    mappings: list[PresetMapping]
```

```python
@dataclass
class PresetMapping:
    topic_suffix: str           # An topic_prefix angehängt
    ziel_key: str               # EEDC-Ziel (relativ: "live/einspeisung_w")
    payload_typ: str
    json_pfad: str | None
    array_index: int | None
    faktor: float
    invertieren: bool
    beschreibung: str
```

### Geplante Presets (Stufe 2)

| Preset | Hersteller | Topics | Beschreibung |
|---|---|---|---|
| `shelly_em` | Shelly | `shellies/{id}/emeter/0/power` | Shelly EM — Netz (1 Phase) |
| `shelly_3em` | Shelly | `shellies/{id}/emeter/{0,1,2}/power` | Shelly 3EM — Netz (3-phasig, Summe) |
| `shelly_plus_em` | Shelly | `{id}/status/em:0` | Shelly Plus EM (Gen2 API, JSON) |
| `tasmota_sml` | Tasmota | `tele/{id}/SENSOR` | Tasmota SML — Stromzähler (JSON) |
| `tasmota_power` | Tasmota | `tele/{id}/SENSOR` → Power | Tasmota Plug — Leistungsmessung |
| `opendtu` | OpenDTU | `solar/{serial}/0/power` | OpenDTU — Hoymiles/TSUN WR |
| `ahoy_dtu` | AhoyDTU | `ahoy/{id}/ch0/P_AC` | AhoyDTU — Hoymiles WR |
| `fronius_mqtt` | Fronius | `fronius/powerflow` | Fronius Symo/Gen24 (JSON) |
| `sma_mqtt` | SMA | `SMA/{serial}/...` | SMA via SBFspot MQTT |
| `go_echarger` | go-e | `go-eCharger/{serial}/nrg` | go-eCharger — Ladeleistung (Array) |
| `victron_mqtt` | Victron | `N/{portal_id}/...` | Victron Energy (Venus OS MQTT) |
| `kostal_mqtt` | Kostal | `kostal/{serial}/...` | Kostal Plenticore |
| `sonnen_mqtt` | sonnen | `sonnen/status` | sonnenBatterie (JSON) |
| `zigbee2mqtt` | Z2M | `zigbee2mqtt/{name}` | Zigbee2MQTT Steckdosen/Sensoren |
| `solax_mqtt` | SolaX | `solax/{serial}/...` | SolaX X1/X3 |
| `deye_mqtt` | Deye | `deye/{serial}/...` | Deye/Solarman WR |

> **Hinweis:** Die Presets überlappen teilweise mit den bestehenden Device-Connectors
> (die per HTTP/API pollten). Der Unterschied: Connectors fragen aktiv ab,
> das Gateway empfängt passiv via MQTT. Für Geräte, die bereits MQTT publishen
> (Tasmota, Zigbee2MQTT, OpenDTU, go-eCharger), ist das Gateway der natürlichere Weg.

## Service-Architektur

### MqttGatewayService

```python
class MqttGatewayService:
    """
    Subscribt auf konfigurierte Quell-Topics, transformiert Payloads
    und publisht auf EEDC-Inbound-Topics.

    Läuft als Background-Task parallel zum MqttInboundService.
    Nutzt denselben Broker (gleiche Credentials).
    """

    def __init__(self, host, port, username, password, mappings: list[MqttMapping]):
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self._mappings: dict[str, list[MqttMapping]] = {}  # topic → [mappings]
        self._client: aiomqtt.Client | None = None
        self._running = False
        self._stats = GatewayStats()
        self._load_mappings(mappings)

    def _load_mappings(self, mappings: list[MqttMapping]):
        """Gruppiert Mappings nach Quell-Topic für schnellen Lookup."""
        self._mappings.clear()
        for m in mappings:
            if m.aktiv:
                self._mappings.setdefault(m.quell_topic, []).append(m)

    async def _subscribe_loop(self):
        """Subscribe-Loop mit Auto-Reconnect."""
        while self._running:
            try:
                async with aiomqtt.Client(...) as client:
                    self._client = client

                    # Subscribe auf alle konfigurierten Quell-Topics
                    subscribed = set()
                    for topic in self._mappings:
                        # Wildcard-Support: "shellies/+/emeter/+/power"
                        await client.subscribe(topic)
                        subscribed.add(topic)

                    logger.info("MQTT-Gateway: %d Topics subscribed", len(subscribed))

                    async for message in client.messages:
                        if not self._running:
                            break
                        await self._handle_message(message)

            except asyncio.CancelledError:
                break
            except Exception as e:
                if self._running:
                    logger.warning("MQTT-Gateway: Reconnect in 10s... (%s)", e)
                    await asyncio.sleep(10)

    async def _handle_message(self, message):
        """Transformiert und re-publisht eine Nachricht."""
        topic = str(message.topic)
        payload = message.payload.decode("utf-8", errors="replace")

        # Topic-Matching (exakt + Wildcard-Expansion)
        mappings = self._find_mappings(topic)
        if not mappings:
            return

        for mapping in mappings:
            wert = transform_payload(
                payload,
                mapping.payload_typ,
                mapping.json_pfad,
                mapping.array_index,
                mapping.faktor,
                mapping.offset,
                mapping.invertieren,
            )
            if wert is None:
                self._stats.transform_errors += 1
                continue

            # Ziel-Topic zusammenbauen
            ziel_topic = f"eedc/{mapping.anlage_id}/{ mapping.ziel_key}"
            await self._client.publish(ziel_topic, str(round(wert, 2)))
            self._stats.forwarded += 1

    async def reload_mappings(self, mappings: list[MqttMapping]):
        """Hot-Reload: Mappings neu laden ohne Service-Neustart."""
        self._load_mappings(mappings)
        # Re-Subscribe nötig → Reconnect triggern
        if self._client:
            # Sauberer Reconnect über disconnect
            ...
```

### Zusammenspiel mit MqttInboundService

```
┌─────────────────────────────────────────────────────────┐
│                      main.py                            │
│                                                         │
│  1. MQTT-Config aus DB laden                            │
│  2. MqttInboundService starten (wie bisher)             │
│  3. Gateway-Mappings aus DB laden                       │
│  4. MqttGatewayService starten (wenn Mappings vorhanden)│
│                                                         │
│  Beide Services teilen:                                 │
│  - Gleichen Broker (host, port, credentials)            │
│  - Eigene MQTT-Client-Instanz (verschiedene client-IDs) │
│  - Gateway publisht → Inbound empfängt                  │
└─────────────────────────────────────────────────────────┘
```

## API-Endpoints

```
GET    /api/live/mqtt/gateway/mappings          → Alle Mappings auflisten
POST   /api/live/mqtt/gateway/mappings          → Neues Mapping anlegen
PUT    /api/live/mqtt/gateway/mappings/{id}     → Mapping bearbeiten
DELETE /api/live/mqtt/gateway/mappings/{id}     → Mapping löschen
POST   /api/live/mqtt/gateway/mappings/reload   → Hot-Reload (nach Änderungen)

GET    /api/live/mqtt/gateway/presets            → Verfügbare Geräte-Presets
POST   /api/live/mqtt/gateway/presets/apply      → Preset anwenden (erstellt Mappings)

GET    /api/live/mqtt/gateway/status             → Status + Statistiken
POST   /api/live/mqtt/gateway/test-topic         → Test: Topic subscriben + Payload anzeigen
```

### Test-Endpoint (besonders wertvoll)

```
POST /api/live/mqtt/gateway/test-topic
Body: { "topic": "shellies/em3/emeter/0/power", "timeout_s": 10 }

Response: {
    "empfangen": true,
    "payload_raw": "1234.5",
    "payload_typ_erkannt": "plain",
    "wert": 1234.5,
    "wartezeit_s": 1.2
}
```

Damit kann der User **vor** dem Anlegen eines Mappings prüfen, ob ein Topic
tatsächlich Daten liefert und welches Payload-Format es hat.

## UI-Konzept

### Integration in bestehende MQTT-Settings-Seite

Die MQTT-Gateway-Konfiguration wird als neuer Bereich **unterhalb** der bestehenden
MQTT-Inbound-Einrichtung eingebaut (gleiche Seite, neuer Abschnitt):

```
┌──────────────────────────────────────────────────┐
│  Einstellungen > MQTT-Inbound                    │
│                                                  │
│  ┌──── Broker-Verbindung (existiert) ──────────┐ │
│  │ Host: 192.168.1.100  Port: 1883             │ │
│  │ Status: ✓ Verbunden, 1.247 Nachrichten      │ │
│  └─────────────────────────────────────────────┘ │
│                                                  │
│  ┌──── EEDC Topics (existiert) ────────────────┐ │
│  │ Topic-Liste + HA Automation Generator       │ │
│  └─────────────────────────────────────────────┘ │
│                                                  │
│  ┌──── MQTT Gateway (NEU) ─────────────────────┐ │
│  │                                             │ │
│  │  [+ Geräte-Preset verwenden]  [+ Manuell]  │ │
│  │                                             │ │
│  │  ┌─ Aktive Mappings ─────────────────────┐  │ │
│  │  │                                       │  │ │
│  │  │ ► Shelly 3EM (3 Mappings)             │  │ │
│  │  │   shellies/em3/emeter/0/power         │  │ │
│  │  │     → eedc/1/live/einspeisung_w  ✓    │  │ │
│  │  │   shellies/em3/emeter/0/total         │  │ │
│  │  │     → eedc/1/energy/einsp._kwh   ✓    │  │ │
│  │  │   ...                                 │  │ │
│  │  │                                       │  │ │
│  │  │ ► go-eCharger (1 Mapping)             │  │ │
│  │  │   go-eCharger/abc123/nrg [11]         │  │ │
│  │  │     → eedc/1/live/inv/5/leist._w ✓    │  │ │
│  │  │                                       │  │ │
│  │  └───────────────────────────────────────┘  │ │
│  │                                             │ │
│  │  Status: ✓ Gateway aktiv, 892 weitergel.   │ │
│  └─────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────┘
```

### Preset-Dialog

```
┌──────────────────────────────────────────┐
│  Geräte-Preset auswählen                 │
│                                          │
│  ┌─ Shelly ──────────────────────────┐   │
│  │ ○ Shelly EM (1-phasig)           │   │
│  │ ● Shelly 3EM (3-phasig)          │   │
│  │ ○ Shelly Plus EM (Gen2)          │   │
│  └───────────────────────────────────┘   │
│  ┌─ Solar / WR ──────────────────────┐   │
│  │ ○ OpenDTU                         │   │
│  │ ○ AhoyDTU                         │   │
│  │ ○ SMA (SBFspot)                   │   │
│  │ ○ Fronius                         │   │
│  └───────────────────────────────────┘   │
│  ┌─ Wallbox / E-Auto ───────────────┐   │
│  │ ○ go-eCharger                     │   │
│  └───────────────────────────────────┘   │
│  ┌─ Sonstiges ──────────────────────┐   │
│  │ ○ Tasmota SML (Stromzähler)      │   │
│  │ ○ Tasmota Plug (Steckdose)       │   │
│  │ ○ Zigbee2MQTT                     │   │
│  └───────────────────────────────────┘   │
│                                          │
│  ── Konfiguration ──                     │
│  Device-ID/Name: [em3_____________]      │
│  Ziel-Anlage:    [▼ Meine PV (ID 1)]    │
│  Ziel-Invest.:   [▼ (nur bei WR/Batt)]  │
│                                          │
│  [Topic testen]  [Vorschau]  [Anlegen]   │
└──────────────────────────────────────────┘
```

### Manuelles Mapping (Formular)

```
┌──────────────────────────────────────────┐
│  Neues MQTT-Mapping                      │
│                                          │
│  Quell-Topic:  [sma/inv/1/pac_________]  │
│                [Topic testen ▶]          │
│                                          │
│  Payload-Typ:  ○ Plain Number            │
│                ● JSON → Pfad: [power___] │
│                ○ JSON Array → Index: [_] │
│                                          │
│  Faktor:       [1.0___]  (z.B. 1000     │
│                           für kW→W)      │
│  Invertieren:  [ ] Vorzeichen umkehren   │
│                                          │
│  Ziel-Anlage:  [▼ Meine PV (ID 1)]      │
│  Ziel-Feld:    [▼ Einspeisung (W)]      │
│                (oder: Investition wählen) │
│                                          │
│  Beschreibung: [SMA Tripower Gesamt-AC_] │
│                                          │
│  [Speichern]                             │
└──────────────────────────────────────────┘
```

## Stufenplan

### Stufe 1 — Manuelles Topic-Mapping (MVP) ✅ v3.4.5

**Scope:**
- DB-Modell `MqttGatewayMapping` (SQLAlchemy) ✅
- ~~Alembic-Migration~~ → `create_all` (neue Tabelle, keine Migration nötig) ✅
- `MqttGatewayService` mit Subscribe + Transform + Re-Publish ✅
- CRUD-API-Endpoints ✅
- Test-Topic-Endpoint ✅
- Test-Transform-Endpoint (Bonus) ✅
- Basis-UI: Mapping-Liste + Formular zum Anlegen/Bearbeiten/Löschen ✅
- Integration in `main.py` (Start neben Inbound-Service) ✅

**Ergebnis:** Nutzer können beliebige MQTT-Topics auf EEDC mappen, müssen aber
jedes Mapping manuell konfigurieren.

### Stufe 2 — Geräte-Presets

**Scope:**
- Preset-Registry (Python-Datenstruktur, keine DB)
- 8-10 initiale Presets (Shelly, Tasmota, OpenDTU, go-eCharger, SMA, Fronius, Zigbee2MQTT, Victron)
- Preset-Auswahl-Dialog in der UI
- Variablen-Eingabe (Device-ID, Serial, etc.)
- Automatisches Erstellen aller Mappings aus Preset

**Aufwand:** ~1-2 Sessions

**Ergebnis:** Für gängige Geräte reichen 3 Klicks statt manueller Konfiguration.

### Stufe 3 — Topic-Discovery (optional, Komfort)

**Scope:**
- Temporär auf `#` subscriben (zeitbegrenzt, z.B. 30s)
- Empfangene Topics + Payloads anzeigen
- Pattern-Erkennung: "Das sieht aus wie ein Shelly 3EM"
- Vorschläge zum Mapping generieren
- User bestätigt → Mappings werden angelegt

**Aufwand:** ~1 Session

**Risiko:** `#`-Subscribe auf einem aktiven Broker kann sehr viele Nachrichten
produzieren. Muss zeitbegrenzt und mit Message-Limit laufen.

## Stufe 0 — Connector → MQTT Bridge (Architektur-Vereinheitlichung) ✅ v3.4.5

### Problem: Connector-Daten ~~sind~~ waren eine Sackgasse

~~Heute~~ Vor v3.4.5 existierten drei voneinander unabhängige Wege, wie Daten ins System kommen:

```
Pfad 1: HA State Service → LivePowerService._collect_values() → Live-Dashboard
Pfad 2: MQTT Inbound     → MqttInboundCache → LivePowerService + Energy Snapshots
Pfad 3: Connectors       → MeterSnapshot (kWh) → NUR Monatsabschluss-Vorschläge  ← gelöst in v3.4.5
                            ╰── JETZT auch im Live-Dashboard (via MQTT Bridge)
                            ╰── JETZT auch in Energy History
                            ╰── JETZT auch im Tagesverlauf
```

Pfad 1 (HA State Service) und Pfad 2 (MQTT Inbound) **bleiben beide bestehen** —
im HA Add-on ist der HA State Service der natürlichste Weg (läuft im selben Container,
kein Broker nötig, direkte Sensor-Abfrage über die HA Supervisor API). Das funktioniert
unabhängig vom Recorder-Backend (SQLite, MariaDB, PostgreSQL) — der Service liest
Live-States, nicht die Datenbank. Würde man den HA-Pfad entfernen und alles über MQTT
zwingen, müsste jeder HA-Nutzer zusätzlich einen MQTT-Broker aufsetzen und Automationen
schreiben. Die MQTT-Priorität (Prio 1 > Prio 2) ermöglicht es, gezielt einzelne
Werte per MQTT zu überschreiben, wo nötig.

**Das eigentliche Problem ist nur Pfad 3:** Connector-Nutzer sehen ihre Daten
**nie** im Live-Dashboard, Energiefluss oder Tagesverlauf — obwohl die Geräte-API
oft auch Live-Watt-Werte liefert (z.B. Shelly `total_power`, OpenDTU `Power.v`).

### Lösung: Connectors publishen auf MQTT-Inbound

Wenn ein Connector seine gepoliten Werte zusätzlich auf `eedc/...`-Topics publisht,
fließen sie automatisch durch die gesamte bestehende MQTT-Inbound-Pipeline:

```
                                    MQTT Broker
                                        │
Connector (pollt Gerät per HTTP)        │        MQTT Inbound (existiert)
┌──────────────────────┐                │        ┌───────────────────────┐
│ ShellyEMConnector    │── publish ─────┤        │ Subscribe eedc/#     │
│  read_meters()       │                │        │ → Cache              │
│  + read_live()  NEU  │                ├───────→│ → Energy Snapshots   │
│                      │                │        │ → Monatsabschluss    │
│ OpenDTUConnector     │── publish ─────┤        │ → Live-Dashboard     │
│  read_meters()       │                │        │ → Tagesverlauf       │
│  + read_live()  NEU  │                │        │ → Energiefluss       │
└──────────────────────┘                │        └───────────────────────┘
                                        │
Externe Geräte (publishen direkt)       │
┌──────────────────────┐                │
│ Tasmota, Zigbee2MQTT │── publish ─────┘
│ go-eCharger, etc.    │   (via Gateway, Stufe 1)
└──────────────────────┘
```

### Was sich ändert

**DeviceConnector Basisklasse erweitern:**

```python
class DeviceConnector(ABC):
    """Abstrakte Basisklasse für Geräte-Connectoren."""

    @abstractmethod
    def info(self) -> ConnectorInfo: ...

    @abstractmethod
    async def test_connection(self, host, username, password) -> ConnectionTestResult: ...

    @abstractmethod
    async def read_meters(self, host, username, password) -> MeterSnapshot: ...

    # NEU: Optionale Live-Werte (Watt, SoC)
    async def read_live(self, host, username, password) -> LiveSnapshot | None:
        """Liest aktuelle Live-Leistungswerte vom Gerät (optional).

        Connectors die das unterstützen, überschreiben diese Methode.
        Default: None (nur kWh-Zähler verfügbar).
        """
        return None
```

```python
@dataclass
class LiveSnapshot:
    """Aktuelle Leistungswerte eines Geräts."""
    timestamp: str
    leistung_w: float | None = None       # Aktuelle Leistung in Watt
    soc: float | None = None              # State of Charge (%) — nur Speicher
    einspeisung_w: float | None = None    # Grid Export (nur Smart Meter)
    netzbezug_w: float | None = None      # Grid Import (nur Smart Meter)
```

**Connector-Polling-Loop publisht auf MQTT:**

```python
class ConnectorMqttBridge:
    """Pollt konfigurierte Connectors und publisht Werte auf MQTT-Inbound-Topics."""

    def __init__(self, mqtt_client, poll_interval_s: int = 10):
        self._client = mqtt_client
        self._interval = poll_interval_s

    async def poll_and_publish(self, connector, config, anlage_id, inv_id=None):
        """Ein Poll-Zyklus für einen Connector."""
        # Live-Werte (Watt) — alle 10s
        live = await connector.read_live(config.host, config.user, config.password)
        if live:
            prefix = f"eedc/{anlage_id}"
            if inv_id:
                if live.leistung_w is not None:
                    await self._client.publish(
                        f"{prefix}/live/inv/{inv_id}/leistung_w",
                        str(round(live.leistung_w, 1))
                    )
                if live.soc is not None:
                    await self._client.publish(
                        f"{prefix}/live/inv/{inv_id}/soc",
                        str(round(live.soc, 1))
                    )
            else:
                # Basis-Topics (Smart Meter)
                if live.einspeisung_w is not None:
                    await self._client.publish(
                        f"{prefix}/live/einspeisung_w",
                        str(round(live.einspeisung_w, 1))
                    )
                if live.netzbezug_w is not None:
                    await self._client.publish(
                        f"{prefix}/live/netzbezug_w",
                        str(round(live.netzbezug_w, 1))
                    )

        # Energy-Werte (kWh) — weniger häufig (alle 5 min)
        meters = await connector.read_meters(config.host, config.user, config.password)
        if meters and inv_id:
            prefix = f"eedc/{anlage_id}/energy/inv/{inv_id}"
            if meters.pv_erzeugung_kwh is not None:
                await self._client.publish(
                    f"{prefix}/pv_erzeugung_kwh",
                    str(round(meters.pv_erzeugung_kwh, 3))
                )
            # ... analog für andere kWh-Felder
```

### Welche Connectors können Live-Watt liefern?

| Connector | `read_live()` | Quelle | Status |
|---|---|---|---|
| **Shelly 3EM** | ✅ Implementiert | `total_power` (Gen1), `total_act_power` (Gen2) | v3.4.5 |
| **OpenDTU / AhoyDTU** | ✅ Implementiert | `livedata/status → total.Power.v` | v3.4.5 |
| **Fronius Solar API** | ✅ Implementiert | `GetPowerFlowRealtimeData → P_PV, P_Grid, P_Akku` | v3.4.5 |
| **sonnenBatterie** | ✅ Implementiert | `/api/v2/status → Production_W, GridFeedIn_W, Pac_total_W, USOC` | v3.4.5 |
| **go-eCharger** | ✅ Implementiert | `/api/status → nrg[11]` (Watt) | v3.4.5 |
| **SMA WebConnect** | ❌ Offen | `getValues → 6100_40263F00 (Pac)` — braucht pysma-plus Session |
| **SMA ennexOS** | ❌ Offen | `measurements/live → Pac` — braucht pysma-plus Session |
| **Kostal Plenticore** | ❌ Offen | `processdata → devices:local:Pac` — braucht pysma-plus Session |
| **Tasmota SML** | ❌ Offen | Abhängig vom Zähler-Readout |

**Ergebnis:** 5 von 9 Connectors haben `read_live()` implementiert. Die SMA/Kostal-Connectors
brauchen pysma-plus Auth/Session-Management, das aufwändiger zu integrieren ist.

### Vorteile dieser Vereinheitlichung

1. **Live-Dashboard für Connector-Nutzer:** Wer heute einen SMA- oder Fronius-Connector
   konfiguriert hat, bekommt erstmals Live-Gauges, Energiefluss und Tagesverlauf
2. **Zwei Pfade statt drei:** HA State Service bleibt für HA-Nutzer (Prio 2),
   MQTT-Inbound (Prio 1) wird zum universellen Pfad für alles andere —
   Connectors, Gateway, externe Systeme. Der tote Connector-Pfad verschwindet.
3. **Externe Konsumenten:** Andere Tools (Grafana, Node-RED) können die Connector-Daten
   direkt vom MQTT-Broker lesen
4. **Debugging:** Alle Live-Daten per `mosquitto_sub -t "eedc/#" -v` sichtbar
5. **Energy History:** Connector-kWh-Werte fließen in die MQTT Energy Snapshots →
   automatische Heute/Gestern-kWh ohne HA

### Einordnung im Stufenplan

Diese Connector-Bridge ist **unabhängig** vom Gateway (Topic-Translator) und kann
parallel oder vorher umgesetzt werden:

```
Stufe 0: Connector → MQTT Bridge  (bestehende Connectors publishen auf MQTT)
Stufe 1: MQTT Gateway MVP          (fremde Topics → EEDC-Topics)
Stufe 2: Geräte-Presets            (vordefinierte Mapping-Templates)
Stufe 3: Topic-Discovery           (automatische Erkennung)
```

Stufe 0 hat den charmanten Effekt, dass Connector-Nutzer **sofort** profitieren,
ohne etwas an ihrer Konfiguration zu ändern. Voraussetzung ist nur, dass MQTT-Inbound
mit einem Broker konfiguriert ist.

### Migration: Connector → Gateway (langfristig)

Mittelfristig könnten die HTTP-Polling-Connectors durch MQTT-Gateway-Presets ersetzt
werden — für Geräte, die selbst MQTT publishen (Tasmota, OpenDTU, go-eCharger).
Connectors bleiben aber relevant für Geräte, die **nur** eine HTTP-API haben
(SMA WebConnect, Fronius Solar API, Kostal).

```
eedc-homeassistant (HA Add-on):
  HA State Service  ──→ LivePowerService (Prio 2)   ← bleibt, natürlichster Weg im HA
  MQTT Inbound      ──→ LivePowerService (Prio 1)   ← bleibt, überschreibt gezielt
  Connectors        ──→ MQTT Inbound (NEU)           ← statt toter Sackgasse

eedc-standalone (ohne HA):
  MQTT Inbound      ──→ LivePowerService              ← einziger Pfad
  Connectors        ──→ MQTT Inbound (NEU)
  Gateway           ──→ MQTT Inbound (NEU, Stufe 1)

Phase 1 (jetzt):  Connector pollt HTTP → publisht auf MQTT
Phase 2 (später): Für MQTT-fähige Geräte → Gateway-Preset statt Connector
                  Für HTTP-only Geräte → Connector bleibt, publisht weiter auf MQTT
```

## Offene Fragen

1. **Wildcard-Mappings:** Soll der User MQTT-Wildcards (`+`, `#`) in Quell-Topics
   verwenden dürfen? Beispiel: `shellies/+/emeter/+/power` matched alle Shelly-EMs.
   → Erfordert Topic-Pattern-Matching statt exaktem Lookup. Sinnvoll für Stufe 2.

2. **Mehrere Quell-Topics → ein Ziel:** z.B. Shelly 3EM mit 3 Phasen-Topics,
   die zu einer Summe addiert werden sollen. → Aggregation (sum/avg/max) als
   optionale Funktion? Oder erst mal: User soll 3-Phasen-Summe extern berechnen
   bzw. Shelly-eigenes Total-Topic nutzen.

3. **Energy-Topics:** Braucht das Gateway auch Energy-Mapping (kWh-Monatswerte)?
   → Ja, aber die meisten externen Geräte liefern kumulative Zähler, nicht
   Monatswerte. Das passt zum bestehenden Energy-Snapshot-System.

4. **Gleicher oder separater Broker?** Manche Nutzer haben ihren Geräte-Broker
   getrennt vom EEDC-Broker. → Stufe 1: Gleicher Broker (einfach). Später optional
   zweiter Broker konfigurierbar.

5. **Naming:** "MQTT Gateway" vs "MQTT Bridge" vs "Topic-Translator"?
   → **Gateway** ist am verständlichsten und grenzt sich von "MQTT Bridge"
   (Mosquitto-Feature für Broker-zu-Broker) ab.

6. **Connector-Polling ohne MQTT-Broker:** Was wenn ein Connector-Nutzer keinen
   MQTT-Broker hat? → Fallback: `ConnectorMqttBridge` kann Werte auch direkt
   in den `MqttInboundCache` injizieren (ohne Broker-Roundtrip). Der Broker
   ist dann optional, aber empfohlen (Debugging, externe Konsumenten).

7. **Poll-Intervall Connectors:** 10s für Live-Watt ist für die meisten HTTP-APIs
   vertretbar, aber manche Geräte (SMA WebConnect) haben Rate-Limits.
   → Konfigurierbares Intervall pro Connector (Default 10s, min 5s).

## Beispiel-Szenarien

### Szenario 1: Shelly 3EM als Netzzähler

Vorher (ohne Gateway):
```bash
# User muss Node-RED oder HA-Automation aufsetzen
# um shellies/em3/emeter/0/power → eedc/1/live/einspeisung_w zu bridgen
```

Nachher (mit Gateway):
```
1. MQTT Gateway → "Geräte-Preset" → "Shelly 3EM"
2. Device-ID eingeben: "em3"
3. Ziel: Anlage "Meine PV", Einspeisung/Netzbezug
4. → 2 Mappings automatisch erstellt (power + total)
```

### Szenario 2: OpenDTU + Tasmota SML (Standalone ohne HA)

```
Geräte:
- OpenDTU mit Hoymiles HM-800 (publisht auf solar/114100000000/0/power)
- Tasmota SML auf Stromzähler (publisht auf tele/sml_zaehler/SENSOR)

Gateway-Mappings:
1. solar/114100000000/0/power → eedc/1/live/inv/2/leistung_w  (plain, faktor 1)
2. tele/sml_zaehler/SENSOR    → eedc/1/live/einspeisung_w     (json, "SML.Einspeisung")
3. tele/sml_zaehler/SENSOR    → eedc/1/live/netzbezug_w       (json, "SML.Bezug")

Ergebnis: Live-Dashboard + Energiefluss funktionieren komplett ohne HA
```

### Szenario 3: go-eCharger Ladeleistung

```
go-eCharger publisht: go-eCharger/abc123/nrg
Payload: [231.4, 0, 0, 0, 2.1, 0, 0, 0, 0, 0, 0, 483.5, 0, 0, 0, 0]
                                                       ↑ Index 11 = Watt

Mapping:
- Quell-Topic: go-eCharger/abc123/nrg
- Payload-Typ: JSON-Array
- Array-Index: 11
- Ziel: eedc/1/live/inv/5/leistung_w
```
