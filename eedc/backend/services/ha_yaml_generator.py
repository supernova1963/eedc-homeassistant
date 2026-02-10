"""
Home Assistant YAML Generator

Generiert YAML-Konfiguration für:
- Utility Meter (monatliche Aggregation)
- REST Command (EEDC Import Endpoint)
- Automation (monatlicher Import)
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from backend.models.anlage import Anlage
    from backend.models.investition import Investition


def _sanitize_name(name: str) -> str:
    """Bereinigt einen Namen für HA Entity-IDs."""
    import re
    # Umlaute ersetzen
    replacements = {
        'ä': 'ae', 'ö': 'oe', 'ü': 'ue', 'ß': 'ss',
        'Ä': 'Ae', 'Ö': 'Oe', 'Ü': 'Ue',
    }
    for old, new in replacements.items():
        name = name.replace(old, new)
    # Nur alphanumerisch und Unterstriche
    name = re.sub(r'[^a-zA-Z0-9_]', '_', name)
    # Mehrfache Unterstriche entfernen
    name = re.sub(r'_+', '_', name)
    return name.lower().strip('_')


def _get_sensor_fields_for_type(typ: str, parameter: dict | None = None) -> list[tuple[str, str, str]]:
    """
    Gibt die Sensor-Felder für einen Investitionstyp zurück.

    Returns:
        Liste von (feld_key, label, unit)
    """
    if typ == "e-auto":
        fields = [
            ("km_gefahren", "km", "km"),
            ("verbrauch_kwh", "Verbrauch", "kWh"),
            ("ladung_pv_kwh", "Ladung PV", "kWh"),
            ("ladung_netz_kwh", "Ladung Netz", "kWh"),
        ]
        if parameter and (parameter.get("nutzt_v2h") or parameter.get("v2h_faehig")):
            fields.append(("v2h_entladung_kwh", "V2H Entladung", "kWh"))
        return fields

    elif typ == "speicher":
        fields = [
            ("ladung_kwh", "Ladung", "kWh"),
            ("entladung_kwh", "Entladung", "kWh"),
        ]
        if parameter and parameter.get("arbitrage_faehig"):
            fields.append(("speicher_ladung_netz_kwh", "Netzladung", "kWh"))
        return fields

    elif typ == "wallbox":
        return [
            ("ladung_kwh", "Ladung", "kWh"),
        ]

    elif typ == "waermepumpe":
        return [
            ("stromverbrauch_kwh", "Strom", "kWh"),
            ("heizenergie_kwh", "Heizung", "kWh"),
            ("warmwasser_kwh", "Warmwasser", "kWh"),
        ]

    elif typ == "pv-module":
        return [
            ("pv_erzeugung_kwh", "Erzeugung", "kWh"),
        ]

    elif typ == "balkonkraftwerk":
        fields = [
            ("pv_erzeugung_kwh", "Erzeugung", "kWh"),
        ]
        if parameter and parameter.get("hat_speicher"):
            fields.extend([
                ("speicher_ladung_kwh", "Speicher Ladung", "kWh"),
                ("speicher_entladung_kwh", "Speicher Entladung", "kWh"),
            ])
        return fields

    elif typ == "sonstiges":
        kategorie = parameter.get("kategorie", "erzeuger") if parameter else "erzeuger"
        if kategorie == "erzeuger":
            return [("erzeugung_kwh", "Erzeugung", "kWh")]
        elif kategorie == "verbraucher":
            return [("verbrauch_kwh", "Verbrauch", "kWh")]
        elif kategorie == "speicher":
            return [
                ("ladung_kwh", "Ladung", "kWh"),
                ("entladung_kwh", "Entladung", "kWh"),
            ]

    return []


def generate_ha_yaml(anlage: "Anlage", investitionen: list["Investition"]) -> str:
    """
    Generiert die komplette YAML-Konfiguration für Home Assistant.

    Args:
        anlage: Die Anlage
        investitionen: Liste der aktiven Investitionen

    Returns:
        YAML-String für configuration.yaml
    """
    anlage_name = _sanitize_name(anlage.anlagenname)
    lines = []

    # Header
    lines.append(f"# EEDC Import Konfiguration für {anlage.anlagenname}")
    lines.append(f"# Generiert für Anlage ID: {anlage.id}")
    lines.append("")

    # Basis-Sensoren (PV, Einspeisung, Netzbezug)
    lines.append("# =============================================================================")
    lines.append("# Utility Meter für Basis-Energiedaten")
    lines.append("# =============================================================================")
    lines.append("# Hinweis: Ersetze 'sensor.DEIN_SENSOR' mit deinen tatsächlichen Sensor-IDs")
    lines.append("")
    lines.append("utility_meter:")

    basis_sensoren = [
        ("einspeisung", "sensor.DEIN_EINSPEISUNG_SENSOR", "Einspeisung"),
        ("netzbezug", "sensor.DEIN_NETZBEZUG_SENSOR", "Netzbezug"),
        ("pv_erzeugung", "sensor.DEIN_PV_SENSOR", "PV Erzeugung"),
    ]

    for key, placeholder, label in basis_sensoren:
        sensor_name = f"eedc_{anlage_name}_{key}_monthly"
        lines.append(f"  {sensor_name}:")
        lines.append(f"    source: {placeholder}  # TODO: Anpassen!")
        lines.append(f"    name: 'EEDC {label} Monat'")
        lines.append("    cycle: monthly")
        lines.append("")

    # Investitions-Sensoren
    if investitionen:
        lines.append("# =============================================================================")
        lines.append("# Utility Meter für Investitionen")
        lines.append("# =============================================================================")
        lines.append("")

    for inv in investitionen:
        inv_name = _sanitize_name(inv.bezeichnung)
        fields = _get_sensor_fields_for_type(inv.typ, inv.parameter)

        if not fields:
            continue

        lines.append(f"  # {inv.bezeichnung} ({inv.typ})")

        for field_key, label, unit in fields:
            sensor_name = f"eedc_{anlage_name}_{inv_name}_{field_key}_monthly"
            placeholder = f"sensor.DEIN_{inv_name.upper()}_{field_key.upper()}_SENSOR"

            lines.append(f"  {sensor_name}:")
            lines.append(f"    source: {placeholder}  # TODO: Anpassen!")
            lines.append(f"    name: 'EEDC {inv.bezeichnung} {label} Monat'")
            lines.append("    cycle: monthly")
        lines.append("")

    # REST Command
    lines.append("")
    lines.append("# =============================================================================")
    lines.append("# REST Command für EEDC Import")
    lines.append("# =============================================================================")
    lines.append("")
    lines.append("rest_command:")
    lines.append(f"  eedc_import_{anlage_name}:")
    lines.append(f"    url: 'http://localhost:8099/api/ha-import/from-ha/{anlage.id}'")
    lines.append("    method: POST")
    lines.append("    headers:")
    lines.append("      Content-Type: application/json")
    lines.append("    payload: >")
    lines.append("      {")
    lines.append('        "jahr": {{ now().year }},')
    lines.append('        "monat": {{ now().month - 1 if now().day == 1 else now().month }},')

    # Basis-Daten
    lines.append(f'        "einspeisung_kwh": {{{{ states("sensor.eedc_{anlage_name}_einspeisung_monthly") | float(0) }}}},')
    lines.append(f'        "netzbezug_kwh": {{{{ states("sensor.eedc_{anlage_name}_netzbezug_monthly") | float(0) }}}},')
    lines.append(f'        "pv_erzeugung_kwh": {{{{ states("sensor.eedc_{anlage_name}_pv_erzeugung_monthly") | float(0) }}}},')

    # Investitions-Daten
    if investitionen:
        lines.append('        "investitionen": {')
        inv_entries = []
        for inv in investitionen:
            inv_name = _sanitize_name(inv.bezeichnung)
            fields = _get_sensor_fields_for_type(inv.typ, inv.parameter)
            if not fields:
                continue

            field_entries = []
            for field_key, _, _ in fields:
                sensor = f"sensor.eedc_{anlage_name}_{inv_name}_{field_key}_monthly"
                field_entries.append(f'            "{field_key}": {{{{ states("{sensor}") | float(0) }}}}')

            inv_entry = f'          "{inv.id}": {{\n' + ',\n'.join(field_entries) + '\n          }'
            inv_entries.append(inv_entry)

        lines.append(',\n'.join(inv_entries))
        lines.append('        }')

    lines.append("      }")

    # Automation
    lines.append("")
    lines.append("# =============================================================================")
    lines.append("# Automation für monatlichen Import")
    lines.append("# =============================================================================")
    lines.append("")
    lines.append("automation:")
    lines.append(f"  - alias: 'EEDC Monatsdaten Import - {anlage.anlagenname}'")
    lines.append("    description: 'Sendet monatliche Energiedaten an EEDC'")
    lines.append("    trigger:")
    lines.append("      - platform: time")
    lines.append("        at: '00:05:00'")
    lines.append("    condition:")
    lines.append("      - condition: template")
    lines.append("        value_template: '{{ now().day == 1 }}'  # Nur am 1. des Monats")
    lines.append("    action:")
    lines.append(f"      - service: rest_command.eedc_import_{anlage_name}")
    lines.append("    mode: single")

    # Hinweise am Ende
    lines.append("")
    lines.append("# =============================================================================")
    lines.append("# WICHTIGE HINWEISE")
    lines.append("# =============================================================================")
    lines.append("#")
    lines.append("# 1. Ersetze alle 'sensor.DEIN_*' Platzhalter mit deinen echten Sensor-IDs")
    lines.append("#")
    lines.append("# 2. Die Utility Meter aggregieren die Werte monatlich")
    lines.append("#    Stelle sicher, dass die Quell-Sensoren Gesamtzähler sind (state_class: total_increasing)")
    lines.append("#")
    lines.append("# 3. Die Automation wird am 1. jeden Monats um 00:05 ausgeführt")
    lines.append("#    und sendet die Daten des Vormonats an EEDC")
    lines.append("#")
    lines.append("# 4. Nach dem Einfügen in configuration.yaml: Home Assistant neu starten!")
    lines.append("#")
    lines.append(f"# 5. EEDC Anlage-ID: {anlage.id}")
    lines.append(f"#    EEDC Import-URL: http://localhost:8099/api/ha-import/from-ha/{anlage.id}")
    lines.append("#")

    return "\n".join(lines)
