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
    beschreibung: str           # Kurzbeschreibung
    variablen: list[PresetVariable]
    mappings: list[PresetMapping]
    anleitung: str = ""         # Hilfetext für den User


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
) -> list[dict]:
    """
    Generiert Mapping-Dicts aus einem Preset.

    Returns: Liste von Dicts kompatibel mit MappingCreate-Schema.
    Raises: ValueError wenn Preset unbekannt oder Variable fehlt.
    """
    preset = get_preset(preset_id)
    if not preset:
        raise ValueError(f"Unbekanntes Preset: {preset_id}")

    # Prüfe ob alle Variablen ausgefüllt sind
    for var in preset.variablen:
        if var.key not in variablen or not variablen[var.key].strip():
            raise ValueError(f"Variable '{var.label}' ({var.key}) fehlt")

    result = []
    for m in preset.mappings:
        # Template-Variablen ersetzen
        topic = m.topic_template.format(**variablen)
        json_pfad = m.json_pfad.format(**variablen) if m.json_pfad else None

        result.append({
            "anlage_id": anlage_id,
            "quell_topic": topic,
            "ziel_key": m.ziel_key,
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

_register(MqttPreset(
    id="shelly_3em",
    name="Shelly 3EM / Pro 3EM",
    hersteller="Shelly",
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
    id="opendtu",
    name="OpenDTU (Hoymiles/TSUN)",
    hersteller="OpenDTU",
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
    id="tasmota_sml",
    name="Tasmota SML (IR-Lesekopf)",
    hersteller="Tasmota",
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
    id="go_echarger",
    name="go-eCharger",
    hersteller="go-e",
    beschreibung="go-eCharger Wallbox. Publiziert Energiedaten als JSON-Array (nrg-Topic).",
    anleitung="MQTT in der go-eCharger App aktivieren. Die Seriennummer steht auf dem Gerät oder in der App unter Einstellungen.",
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
            ziel_key="live/wallbox_w",
            beschreibung="Ladeleistung gesamt (nrg[11] = Total Power W)",
            payload_typ="json_array",
            array_index=11,
        ),
    ],
))
