"""
EEDC Sensor Export für Home Assistant.

Definiert alle KPIs und berechneten Werte, die an HA exportiert werden können.
Unterstützt zwei Export-Methoden:
1. REST API - HA liest Werte über rest platform
2. MQTT Discovery - Native HA-Entitäten via MQTT Auto-Discovery
"""

from dataclasses import dataclass, field
from typing import Optional, Any
from enum import Enum


class SensorCategory(str, Enum):
    """Sensor-Kategorien für Gruppierung."""
    ANLAGE = "anlage"           # PV-Anlage Gesamt
    ENERGIE = "energie"         # Energie-Werte (kWh)
    QUOTE = "quote"             # Prozent-Werte (Autarkie, EV-Quote)
    FINANZEN = "finanzen"       # Euro-Werte
    UMWELT = "umwelt"           # CO2-Werte
    INVESTITION = "investition" # Investitions-KPIs
    E_AUTO = "e_auto"           # E-Auto spezifisch
    WAERMEPUMPE = "waermepumpe" # Wärmepumpe spezifisch
    SPEICHER = "speicher"       # Speicher spezifisch
    WALLBOX = "wallbox"         # Wallbox spezifisch


@dataclass
class SensorDefinition:
    """Definition eines exportierbaren Sensors."""
    key: str                           # Eindeutiger Schlüssel (z.B. "pv_erzeugung_gesamt")
    name: str                          # Anzeigename (z.B. "PV Erzeugung Gesamt")
    unit: str                          # Einheit (z.B. "kWh", "%", "€")
    icon: str                          # MDI Icon (z.B. "mdi:solar-power")
    category: SensorCategory           # Kategorie für Gruppierung
    formel: str                        # Berechnungsformel als Text
    device_class: Optional[str] = None # HA device_class (z.B. "energy", "monetary")
    state_class: Optional[str] = None  # HA state_class (z.B. "total", "measurement")
    enabled_by_default: bool = True    # Standardmäßig aktiviert


@dataclass
class SensorValue:
    """Ein berechneter Sensorwert mit Metadaten."""
    definition: SensorDefinition
    value: Any                          # Der aktuelle Wert
    berechnung: Optional[str] = None    # Konkrete Berechnung (z.B. "3200 ÷ 4670 × 100")
    zusatz_attribute: dict = field(default_factory=dict)  # Zusätzliche Attribute


# =============================================================================
# SENSOR-DEFINITIONEN - Anlage (PV-Gesamt)
# =============================================================================
ANLAGE_SENSOREN = [
    SensorDefinition(
        key="pv_erzeugung_gesamt_kwh",
        name="PV Erzeugung Gesamt",
        unit="kWh",
        icon="mdi:solar-power",
        category=SensorCategory.ENERGIE,
        formel="Σ PV-Erzeugung aller Monate",
        device_class="energy",
        state_class="total_increasing",
    ),
    SensorDefinition(
        key="direktverbrauch_gesamt_kwh",
        name="Direktverbrauch Gesamt",
        unit="kWh",
        icon="mdi:lightning-bolt",
        category=SensorCategory.ENERGIE,
        formel="Σ Direktverbrauch (PV direkt verbraucht ohne Speicher)",
        device_class="energy",
        state_class="total_increasing",
    ),
    SensorDefinition(
        key="eigenverbrauch_gesamt_kwh",
        name="Eigenverbrauch Gesamt",
        unit="kWh",
        icon="mdi:home-lightning-bolt",
        category=SensorCategory.ENERGIE,
        formel="Σ Eigenverbrauch aller Monate",
        device_class="energy",
        state_class="total_increasing",
    ),
    SensorDefinition(
        key="einspeisung_gesamt_kwh",
        name="Einspeisung Gesamt",
        unit="kWh",
        icon="mdi:transmission-tower-export",
        category=SensorCategory.ENERGIE,
        formel="Σ Einspeisung aller Monate",
        device_class="energy",
        state_class="total_increasing",
    ),
    SensorDefinition(
        key="netzbezug_gesamt_kwh",
        name="Netzbezug Gesamt",
        unit="kWh",
        icon="mdi:transmission-tower-import",
        category=SensorCategory.ENERGIE,
        formel="Σ Netzbezug aller Monate",
        device_class="energy",
        state_class="total_increasing",
    ),
    SensorDefinition(
        key="gesamtverbrauch_kwh",
        name="Gesamtverbrauch",
        unit="kWh",
        icon="mdi:home-lightning-bolt-outline",
        category=SensorCategory.ENERGIE,
        formel="Eigenverbrauch + Netzbezug",
        device_class="energy",
        state_class="total_increasing",
    ),
    SensorDefinition(
        key="autarkie_prozent",
        name="Autarkie",
        unit="%",
        icon="mdi:home-battery",
        category=SensorCategory.QUOTE,
        formel="Eigenverbrauch ÷ Gesamtverbrauch × 100",
        state_class="measurement",
    ),
    SensorDefinition(
        key="eigenverbrauch_quote_prozent",
        name="Eigenverbrauchsquote",
        unit="%",
        icon="mdi:percent",
        category=SensorCategory.QUOTE,
        formel="Eigenverbrauch ÷ PV-Erzeugung × 100",
        state_class="measurement",
    ),
    SensorDefinition(
        key="spezifischer_ertrag_kwh_kwp",
        name="Spezifischer Ertrag",
        unit="kWh/kWp",
        icon="mdi:solar-power-variant",
        category=SensorCategory.ANLAGE,
        formel="PV-Erzeugung ÷ Anlagenleistung",
        state_class="total",
    ),
    SensorDefinition(
        key="netto_ertrag_euro",
        name="Netto-Ertrag",
        unit="€",
        icon="mdi:cash-plus",
        category=SensorCategory.FINANZEN,
        formel="Einspeiseerlös + EV-Ersparnis",
        device_class="monetary",
        state_class="total",
    ),
    SensorDefinition(
        key="einspeise_erloes_euro",
        name="Einspeiseerlös",
        unit="€",
        icon="mdi:cash-check",
        category=SensorCategory.FINANZEN,
        formel="Einspeisung × Einspeisevergütung",
        device_class="monetary",
        state_class="total",
    ),
    SensorDefinition(
        key="eigenverbrauch_ersparnis_euro",
        name="Eigenverbrauch-Ersparnis",
        unit="€",
        icon="mdi:piggy-bank",
        category=SensorCategory.FINANZEN,
        formel="Eigenverbrauch × Netzbezugspreis",
        device_class="monetary",
        state_class="total",
    ),
    SensorDefinition(
        key="co2_ersparnis_kg",
        name="CO2 Einsparung",
        unit="kg",
        icon="mdi:molecule-co2",
        category=SensorCategory.UMWELT,
        formel="PV-Erzeugung × 0.38 kg/kWh",
        state_class="total_increasing",
    ),
]

# =============================================================================
# SENSOR-DEFINITIONEN - Investitionen (ROI)
# =============================================================================
INVESTITION_SENSOREN = [
    SensorDefinition(
        key="investition_gesamt_euro",
        name="Investition Gesamt",
        unit="€",
        icon="mdi:cash",
        category=SensorCategory.INVESTITION,
        formel="Σ Anschaffungskosten aller Investitionen",
        device_class="monetary",
        state_class="total",
    ),
    SensorDefinition(
        key="jahres_ersparnis_euro",
        name="Jahresersparnis",
        unit="€/Jahr",
        icon="mdi:cash-refund",
        category=SensorCategory.INVESTITION,
        formel="Σ Jährliche Einsparungen",
        device_class="monetary",
        state_class="measurement",
    ),
    SensorDefinition(
        key="roi_prozent",
        name="ROI",
        unit="%",
        icon="mdi:chart-line",
        category=SensorCategory.INVESTITION,
        formel="Jahresersparnis ÷ Investition × 100",
        state_class="measurement",
    ),
    SensorDefinition(
        key="amortisation_jahre",
        name="Amortisation",
        unit="Jahre",
        icon="mdi:calendar-clock",
        category=SensorCategory.INVESTITION,
        formel="Investition ÷ Jahresersparnis",
        state_class="measurement",
    ),
]

# =============================================================================
# SENSOR-DEFINITIONEN - E-Auto
# =============================================================================
E_AUTO_SENSOREN = [
    SensorDefinition(
        key="e_auto_km_gesamt",
        name="Gefahrene km",
        unit="km",
        icon="mdi:car-electric",
        category=SensorCategory.E_AUTO,
        formel="Σ Gefahrene Kilometer",
        state_class="total_increasing",
    ),
    SensorDefinition(
        key="e_auto_verbrauch_kwh_100km",
        name="Verbrauch",
        unit="kWh/100km",
        icon="mdi:gauge",
        category=SensorCategory.E_AUTO,
        formel="Gesamtverbrauch ÷ km × 100",
        state_class="measurement",
    ),
    SensorDefinition(
        key="e_auto_pv_anteil_prozent",
        name="PV-Anteil Ladung",
        unit="%",
        icon="mdi:solar-power",
        category=SensorCategory.E_AUTO,
        formel="PV-Ladung ÷ Gesamt-Ladung × 100",
        state_class="measurement",
    ),
    SensorDefinition(
        key="e_auto_ersparnis_vs_benzin_euro",
        name="Ersparnis vs Benzin",
        unit="€",
        icon="mdi:fuel",
        category=SensorCategory.E_AUTO,
        formel="Benzinkosten (alternativ) - Stromkosten",
        device_class="monetary",
        state_class="total",
    ),
]

# =============================================================================
# SENSOR-DEFINITIONEN - Wärmepumpe
# =============================================================================
WAERMEPUMPE_SENSOREN = [
    SensorDefinition(
        key="wp_cop_durchschnitt",
        name="COP Durchschnitt",
        unit="",
        icon="mdi:heat-pump",
        category=SensorCategory.WAERMEPUMPE,
        formel="Wärmeenergie ÷ Stromverbrauch",
        state_class="measurement",
    ),
    SensorDefinition(
        key="wp_ersparnis_euro",
        name="WP Ersparnis",
        unit="€",
        icon="mdi:cash-plus",
        category=SensorCategory.WAERMEPUMPE,
        formel="Kosten alte Heizung - WP-Kosten",
        device_class="monetary",
        state_class="total",
    ),
]

# =============================================================================
# SENSOR-DEFINITIONEN - Speicher
# =============================================================================
SPEICHER_SENSOREN = [
    SensorDefinition(
        key="speicher_zyklen",
        name="Vollzyklen",
        unit="",
        icon="mdi:battery-sync",
        category=SensorCategory.SPEICHER,
        formel="Entladung ÷ Kapazität",
        state_class="total_increasing",
    ),
    SensorDefinition(
        key="speicher_effizienz_prozent",
        name="Speicher-Effizienz",
        unit="%",
        icon="mdi:battery-check",
        category=SensorCategory.SPEICHER,
        formel="Entladung ÷ Ladung × 100",
        state_class="measurement",
    ),
]

# =============================================================================
# ALLE SENSOREN ZUSAMMENGEFASST
# =============================================================================
ALL_SENSOR_DEFINITIONS = {
    "anlage": ANLAGE_SENSOREN,
    "investition": INVESTITION_SENSOREN,
    "e_auto": E_AUTO_SENSOREN,
    "waermepumpe": WAERMEPUMPE_SENSOREN,
    "speicher": SPEICHER_SENSOREN,
}


def get_sensor_definition(key: str) -> Optional[SensorDefinition]:
    """Findet eine Sensor-Definition anhand des Keys."""
    for category_sensors in ALL_SENSOR_DEFINITIONS.values():
        for sensor in category_sensors:
            if sensor.key == key:
                return sensor
    return None


def get_all_sensor_definitions() -> list[SensorDefinition]:
    """Gibt alle Sensor-Definitionen als flache Liste zurück."""
    result = []
    for category_sensors in ALL_SENSOR_DEFINITIONS.values():
        result.extend(category_sensors)
    return result
