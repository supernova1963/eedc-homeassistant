"""
MQTT Gateway Geräte-Presets (Stufe 2).

Vordefinierte Mapping-Vorlagen für gängige MQTT-Geräte.
Der User wählt ein Preset, gibt seine Device-ID an, und alle
Mappings werden automatisch angelegt.
"""

from dataclasses import dataclass, field


@dataclass
class PresetVariable:
    """Eine Variable die der User ausfüllen muss."""
    key: str                    # z.B. "device_id"
    label: str                  # z.B. "Device-ID"
    placeholder: str = ""       # z.B. "shellyem3-AABBCC"
    hinweis: str = ""           # z.B. "Steht auf dem Gerät oder in der Shelly-App"


@dataclass
class PresetMapping:
    """Ein einzelnes Mapping innerhalb eines Presets."""
    topic_template: str         # z.B. "shellies/{device_id}/emeter/0/total_power"
    ziel_key: str               # z.B. "live/netzbezug_w"
    beschreibung: str           # z.B. "Netzleistung (Summe 3 Phasen)"
    payload_typ: str = "plain"  # plain | json | json_array
    json_pfad: str | None = None
    array_index: int | None = None
    faktor: float = 1.0
    offset: float = 0.0
    invertieren: bool = False


@dataclass
class MqttPreset:
    """Ein Geräte-Preset mit allen Mapping-Vorlagen."""
    id: str                     # z.B. "shelly_3em"
    name: str                   # z.B. "Shelly 3EM"
    hersteller: str             # z.B. "Shelly"
    gruppe: str                 # z.B. "Shelly" | "Solar / WR" | "Speicher" | "Wallbox" | "Sonstiges"
    beschreibung: str           # Kurzbeschreibung
    variablen: list[PresetVariable]
    mappings: list[PresetMapping]
    anleitung: str = ""         # Hilfetext für den User
    erfordert_investition: bool = False  # True wenn Investitions-ID für ziel_key benötigt wird


# ─── Preset-Registry ──────────────────────────────────────────────

_PRESETS: dict[str, MqttPreset] = {}


def _register(preset: MqttPreset) -> None:
    _PRESETS[preset.id] = preset


def list_presets() -> list[MqttPreset]:
    """Alle verfügbaren Presets."""
    return list(_PRESETS.values())


def get_preset(preset_id: str) -> MqttPreset | None:
    """Preset nach ID."""
    return _PRESETS.get(preset_id)


def generate_mappings(
    preset_id: str,
    anlage_id: int,
    variablen: dict[str, str],
    investition_id: int | None = None,
) -> list[dict]:
    """
    Generiert Mapping-Dicts aus einem Preset.

    Returns: Liste von Dicts kompatibel mit MappingCreate-Schema.
    Raises: ValueError wenn Preset unbekannt oder Variable fehlt.
    """
    preset = get_preset(preset_id)
    if not preset:
        raise ValueError(f"Unbekanntes Preset: {preset_id}")

    if preset.erfordert_investition and investition_id is None:
        raise ValueError("Dieses Preset erfordert die Auswahl einer Investition")

    # Prüfe ob alle Variablen ausgefüllt sind
    for var in preset.variablen:
        if var.key not in variablen or not variablen[var.key].strip():
            raise ValueError(f"Variable '{var.label}' ({var.key}) fehlt")

    result = []
    for m in preset.mappings:
        # Template-Variablen ersetzen
        topic = m.topic_template.format(**variablen)
        json_pfad = m.json_pfad.format(**variablen) if m.json_pfad else None

        # Investitions-ID in ziel_key einsetzen
        ziel_key = m.ziel_key
        if investition_id is not None:
            ziel_key = ziel_key.replace("{inv_id}", str(investition_id))

        result.append({
            "anlage_id": anlage_id,
            "quell_topic": topic,
            "ziel_key": ziel_key,
            "payload_typ": m.payload_typ,
            "json_pfad": json_pfad,
            "array_index": m.array_index,
            "faktor": m.faktor,
            "offset": m.offset,
            "invertieren": m.invertieren,
            "aktiv": True,
            "beschreibung": m.beschreibung,
            "preset_id": preset_id,
        })

    return result


# ─── Preset-Definitionen ──────────────────────────────────────────
# Gruppen: Shelly | Solar / WR | Speicher | Wallbox | Sonstiges

# ── Shelly ────────────────────────────────────────────────────────

_register(MqttPreset(
    id="shelly_3em",
    name="Shelly 3EM / Pro 3EM",
    hersteller="Shelly",
    gruppe="Shelly",
    beschreibung="Smartmeter für Netzbezug/Einspeisung (3-phasig, Leistungssumme). Gen1-MQTT-API.",
    anleitung="MQTT in der Shelly-App aktivieren (Settings → MQTT). Die Device-ID steht auf dem Gerät oder unter Settings → Device Info.",
    variablen=[
        PresetVariable(
            key="device_id",
            label="Device-ID",
            placeholder="shellyem3-AABBCC",
            hinweis="Steht auf dem Gerät oder in der Shelly-App unter Device Info",
        ),
    ],
    mappings=[
        PresetMapping(
            topic_template="shellies/{device_id}/emeter/0/total_power",
            ziel_key="live/netzbezug_w",
            beschreibung="Netzleistung Summe (positiv=Bezug, negativ=Einspeisung)",
            payload_typ="plain",
        ),
    ],
))

_register(MqttPreset(
    id="shelly_plus_em",
    name="Shelly Plus 1PM / Plus 2PM / Pro EM",
    hersteller="Shelly",
    gruppe="Shelly",
    beschreibung="Shelly Gen2-Geräte mit MQTT-RPC-Status. Publiziert JSON auf status-Topic.",
    anleitung="MQTT in der Shelly-App aktivieren (Settings → MQTT). Die Device-ID findet sich unter Settings → Device Info (z.B. shellyplus1pm-AABBCC).",
    variablen=[
        PresetVariable(
            key="device_id",
            label="Device-ID",
            placeholder="shellyplus1pm-AABBCC",
            hinweis="Settings → Device Info in der Shelly-App",
        ),
    ],
    mappings=[
        PresetMapping(
            topic_template="{device_id}/status/em:0",
            ziel_key="live/netzbezug_w",
            beschreibung="Netzleistung (JSON: total_act_power)",
            payload_typ="json",
            json_pfad="total_act_power",
        ),
    ],
))

_register(MqttPreset(
    id="shelly_em",
    name="Shelly EM (1-phasig)",
    hersteller="Shelly",
    gruppe="Shelly",
    beschreibung="Shelly EM Gen1 für 1-phasige Netzmessung. Typisch für Zählerschrank mit einem Stromwandler.",
    anleitung="MQTT in der Shelly-App aktivieren (Settings → MQTT). Die Device-ID steht auf dem Gerät (z.B. shellyem-AABBCC).",
    variablen=[
        PresetVariable(
            key="device_id",
            label="Device-ID",
            placeholder="shellyem-AABBCC",
            hinweis="Steht auf dem Gerät oder in der Shelly-App unter Device Info",
        ),
    ],
    mappings=[
        PresetMapping(
            topic_template="shellies/{device_id}/emeter/0/power",
            ziel_key="live/netzbezug_w",
            beschreibung="Netzleistung Phase 1 (positiv=Bezug, negativ=Einspeisung)",
            payload_typ="plain",
        ),
    ],
))

_register(MqttPreset(
    id="shelly_pm",
    name="Shelly Plus Plug S / PM Mini (Verbraucher)",
    hersteller="Shelly",
    gruppe="Shelly",
    beschreibung="Shelly Gen2 Steckdose oder PM Mini zur Leistungsmessung eines einzelnen Verbrauchers (z.B. Wärmepumpe, Klimaanlage).",
    anleitung="MQTT in der Shelly-App aktivieren. Die Device-ID findet sich unter Settings → Device Info. Bitte die zugehörige Investition auswählen.",
    erfordert_investition=True,
    variablen=[
        PresetVariable(
            key="device_id",
            label="Device-ID",
            placeholder="shellyplusplug-AABBCC",
            hinweis="Settings → Device Info in der Shelly-App",
        ),
    ],
    mappings=[
        PresetMapping(
            topic_template="{device_id}/status/switch:0",
            ziel_key="live/inv/{inv_id}/leistung_w",
            beschreibung="Verbraucher-Leistung (JSON: apower)",
            payload_typ="json",
            json_pfad="apower",
        ),
    ],
))

# ── Solar / WR ────────────────────────────────────────────────────

_register(MqttPreset(
    id="opendtu",
    name="OpenDTU (Hoymiles/TSUN)",
    hersteller="OpenDTU",
    gruppe="Solar / WR",
    beschreibung="OpenDTU Gateway für Hoymiles/TSUN Micro-Inverter. Publiziert AC-Leistung pro Wechselrichter.",
    anleitung="MQTT in der OpenDTU-Weboberfläche aktivieren (Settings → MQTT). Die Seriennummer des Wechselrichters steht unter Inverter → Serial.",
    variablen=[
        PresetVariable(
            key="serial",
            label="WR-Seriennummer",
            placeholder="116180123456",
            hinweis="12-stellig, steht in der OpenDTU-Oberfläche unter Inverter",
        ),
    ],
    mappings=[
        PresetMapping(
            topic_template="solar/{serial}/0/power",
            ziel_key="live/pv_gesamt_w",
            beschreibung="PV AC-Leistung (W)",
            payload_typ="plain",
        ),
    ],
))

_register(MqttPreset(
    id="ahoy_dtu",
    name="AhoyDTU (Hoymiles)",
    hersteller="AhoyDTU",
    gruppe="Solar / WR",
    beschreibung="AhoyDTU Gateway für Hoymiles Micro-Inverter. Alternative zu OpenDTU mit eigenem Topic-Schema.",
    anleitung="MQTT in der AhoyDTU-Weboberfläche aktivieren (Setup → MQTT). Die Seriennummer des Inverters steht unter Inverter.",
    variablen=[
        PresetVariable(
            key="serial",
            label="Inverter-Seriennummer",
            placeholder="116180123456",
            hinweis="12-stellig, steht in der AhoyDTU-Oberfläche unter Inverter",
        ),
    ],
    mappings=[
        PresetMapping(
            topic_template="ahoy/{serial}/ch0/P_AC",
            ziel_key="live/pv_gesamt_w",
            beschreibung="PV AC-Leistung gesamt (W)",
            payload_typ="plain",
        ),
    ],
))

_register(MqttPreset(
    id="victron_venus",
    name="Victron Venus OS (MQTT)",
    hersteller="Victron",
    gruppe="Solar / WR",
    beschreibung="Victron Venus OS (Cerbo GX / Raspberry Pi) MQTT-Broker. Publiziert alle Systemwerte als JSON mit {\"value\": X}.",
    anleitung="MQTT auf dem Venus OS aktivieren (Einstellungen → Dienste → MQTT). Die VRM Portal ID steht unter Einstellungen → VRM Online Portal.",
    variablen=[
        PresetVariable(
            key="vrm_id",
            label="VRM Portal ID",
            placeholder="a1b2c3d4e5f6",
            hinweis="12-stellig, unter Einstellungen → VRM Online Portal → VRM Portal ID",
        ),
    ],
    mappings=[
        PresetMapping(
            topic_template="N/{vrm_id}/system/0/Ac/Grid/L1/Power",
            ziel_key="live/netzbezug_w",
            beschreibung="Netzleistung Phase 1 (JSON: value)",
            payload_typ="json",
            json_pfad="value",
        ),
        PresetMapping(
            topic_template="N/{vrm_id}/system/0/Dc/Pv/Power",
            ziel_key="live/pv_gesamt_w",
            beschreibung="PV DC-Leistung gesamt (JSON: value)",
            payload_typ="json",
            json_pfad="value",
        ),
    ],
))

# ── Speicher ──────────────────────────────────────────────────────

_register(MqttPreset(
    id="sonnen_mqtt",
    name="sonnenBatterie (MQTT)",
    hersteller="sonnen",
    gruppe="Speicher",
    beschreibung="sonnenBatterie Heimspeicher mit lokalem MQTT-Interface. Publiziert Lade-/Entladeleistung und Ladestand.",
    anleitung="Lokales MQTT auf der sonnenBatterie aktivieren (Softwareintegration → MQTT). Die Seriennummer steht auf dem Gerät oder im sonnen-Portal.",
    erfordert_investition=True,
    variablen=[
        PresetVariable(
            key="serial",
            label="Seriennummer",
            placeholder="12345",
            hinweis="Steht auf dem Gerät (Typenschild) oder im sonnen-Portal unter Meine Anlage",
        ),
    ],
    mappings=[
        PresetMapping(
            topic_template="sonnen/{serial}/status",
            ziel_key="live/inv/{inv_id}/leistung_w",
            beschreibung="Batterie-Leistung (positiv=Laden, negativ=Entladen) — JSON: Pac_total_W",
            payload_typ="json",
            json_pfad="Pac_total_W",
        ),
        PresetMapping(
            topic_template="sonnen/{serial}/status",
            ziel_key="live/inv/{inv_id}/soc",
            beschreibung="Ladestand in % — JSON: USOC",
            payload_typ="json",
            json_pfad="USOC",
        ),
    ],
))

# ── Wallbox ───────────────────────────────────────────────────────

_register(MqttPreset(
    id="go_echarger",
    name="go-eCharger",
    hersteller="go-e",
    gruppe="Wallbox",
    beschreibung="go-eCharger Wallbox. Publiziert Energiedaten als JSON-Array (nrg-Topic).",
    anleitung="MQTT in der go-eCharger App aktivieren. Die Seriennummer steht auf dem Gerät oder in der App unter Einstellungen. Bitte die zugehörige Wallbox-Investition auswählen.",
    erfordert_investition=True,
    variablen=[
        PresetVariable(
            key="serial",
            label="Seriennummer",
            placeholder="012345",
            hinweis="6-stellig, steht auf dem Gerät oder in der go-e App",
        ),
    ],
    mappings=[
        PresetMapping(
            topic_template="go-eCharger/{serial}/nrg",
            ziel_key="live/inv/{inv_id}/leistung_w",
            beschreibung="Ladeleistung gesamt (nrg[11] = Total Power W)",
            payload_typ="json_array",
            array_index=11,
        ),
    ],
))

# ── Sonstiges ─────────────────────────────────────────────────────

_register(MqttPreset(
    id="tasmota_sml",
    name="Tasmota SML (IR-Lesekopf)",
    hersteller="Tasmota",
    gruppe="Sonstiges",
    beschreibung="Tasmota-Gerät mit SML-Script für IR-Lesekopf am Stromzähler. Publiziert OBIS-Codes als JSON.",
    anleitung="MQTT in Tasmota konfigurieren (Configuration → MQTT). Der JSON-Key für den Zähler variiert je nach SML-Script (z.B. 'SM', 'SML', 'Strom').",
    variablen=[
        PresetVariable(
            key="device_id",
            label="Tasmota Topic",
            placeholder="tasmota_AABBCC",
            hinweis="Configuration → MQTT → Topic in der Tasmota-Oberfläche",
        ),
        PresetVariable(
            key="json_key",
            label="JSON-Key des Zählers",
            placeholder="SM",
            hinweis="Der Schlüssel im SENSOR-JSON (z.B. SM, SML, Strom) — sichtbar unter Console → TelePeriod",
        ),
    ],
    mappings=[
        PresetMapping(
            topic_template="tele/{device_id}/SENSOR",
            ziel_key="live/netzbezug_w",
            beschreibung="Momentanleistung (OBIS 16.7.0)",
            payload_typ="json",
            json_pfad="{json_key}.16_7_0",
        ),
    ],
))

_register(MqttPreset(
    id="tasmota_power",
    name="Tasmota Steckdose / Schalter (Verbraucher)",
    hersteller="Tasmota",
    gruppe="Sonstiges",
    beschreibung="Tasmota-Gerät zur Leistungsmessung eines einzelnen Verbrauchers (Steckdose, Schalter mit Messung).",
    anleitung="MQTT in Tasmota konfigurieren (Configuration → MQTT). Bitte die zugehörige Investition auswählen.",
    erfordert_investition=True,
    variablen=[
        PresetVariable(
            key="device_id",
            label="Tasmota Topic",
            placeholder="tasmota_AABBCC",
            hinweis="Configuration → MQTT → Topic in der Tasmota-Oberfläche",
        ),
    ],
    mappings=[
        PresetMapping(
            topic_template="tele/{device_id}/SENSOR",
            ziel_key="live/inv/{inv_id}/leistung_w",
            beschreibung="Verbraucher-Leistung (JSON: ENERGY.Power)",
            payload_typ="json",
            json_pfad="ENERGY.Power",
        ),
    ],
))

_register(MqttPreset(
    id="zigbee2mqtt_power",
    name="Zigbee2MQTT Steckdose (Verbraucher)",
    hersteller="Zigbee2MQTT",
    gruppe="Sonstiges",
    beschreibung="Zigbee-Steckdose mit Leistungsmessung über Zigbee2MQTT (z.B. IKEA INSPELNING, Shelly Plug E, Sonoff S40).",
    anleitung="Zigbee2MQTT muss konfiguriert und aktiv sein. Der Gerätename entspricht dem Namen in der Zigbee2MQTT-Oberfläche. Bitte die zugehörige Investition auswählen.",
    erfordert_investition=True,
    variablen=[
        PresetVariable(
            key="device_name",
            label="Gerätename",
            placeholder="Wohnzimmer Steckdose",
            hinweis="Der Name des Geräts in der Zigbee2MQTT-Oberfläche",
        ),
    ],
    mappings=[
        PresetMapping(
            topic_template="zigbee2mqtt/{device_name}",
            ziel_key="live/inv/{inv_id}/leistung_w",
            beschreibung="Verbraucher-Leistung (JSON: power)",
            payload_typ="json",
            json_pfad="power",
        ),
    ],
))
