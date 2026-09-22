"""HA-Export — die Request-/Antwortmodelle (MQTT-Konfiguration, Sensor-Export, YAML-Snippet, Auto-Publish,
Sensor-Abwahl) und `_hinweis` (der Vorbehalt eines Sensorwerts als Text).
"""
# Reiner Umzug aus `api/routes/ha_export.py` (18.09.2026, Vorlage 8 des Refactorings grosser Dateien):
# Code 1:1 uebernommen, kein Verhaltenswechsel. Die Fassade `__init__.py` haengt den Router ein und exportiert
# die Namen weiter, die Aufrufer und Tests bisher aus dem Modul importierten.

from pydantic import BaseModel, Field, model_validator
from typing import Optional, Any
from backend.services.ha_sensors_export import SensorValue, runde_exportwert


# =============================================================================
# Pydantic Models
# =============================================================================

class MQTTConfigRequest(BaseModel):
    """MQTT-Broker Konfiguration (Override; None-Felder fallen auf ENV zurück).

    Felder defaulten bewusst auf None statt `core-mosquitto`/1883: das Frontend
    sendet `config || {}`, ein leeres Objekt soll auf die ENV-Konfiguration
    zurückfallen — nicht auf einen festen Broker zielen (#655 Broker-Mismatch).
    """
    host: Optional[str] = None
    port: Optional[int] = None
    username: Optional[str] = None
    password: Optional[str] = None

def _hinweis(sv: SensorValue) -> Optional[str]:
    """B5/X-2: Vorbehalt oder Grund eines Sensorwerts für die REST-Antwort —
    dieselben Attribute, die MQTT unter `vorbehalt`/`grund` publiziert."""
    z = sv.zusatz_attribute or {}
    return z.get("vorbehalt") or z.get("grund")

class SensorExportItem(BaseModel):
    """Einzelner Sensor im Export.

    Die Rundung sitzt HIER und nicht in den drei Routen, die das Item bauen
    (`/sensors` zweimal, `/sensors/{anlage_id}`): dieses Modell IST die
    REST-Serialisierungsgrenze — an ihm vorbei kommt kein Sensorwert nach
    außen, auch eine vierte Route nicht. Damit sagen REST und MQTT dieselbe
    Zahl; vorher lieferte REST roh weiter, was der Produzent gerundet hatte
    (kWh mit einer Nachkommastelle, wo MQTT ganzzahlig publizierte).
    """
    key: str
    name: str
    value: Any
    unit: str
    icon: str
    category: str
    formel: str
    berechnung: Optional[str] = None
    device_class: Optional[str] = None
    state_class: Optional[str] = None
    # B5/X-2 (05.09.2026): der Satz, der neben dem Wert steht — Vorbehalt
    # (Wärme geschätzt · zweiter Erzeuger) oder Grund einer Sperre. Dieselben
    # Worte wie Hub und Cockpit; MQTT trägt sie als Attribut.
    hinweis: Optional[str] = None
    # ⭐ **N-541 (22.09.2026): die Zusatz-Attribute, die MQTT längst publiziert.**
    # Bis hierher trug REST nur `hinweis` — den einen Satz, der aus
    # `zusatz_attribute` herausgezogen wurde; alles andere (Stundenreihen,
    # Fenster, Quellenangaben, `je_speicher`, `preisquelle` …) endete an dieser
    # Grenze. Zwei Folgen, beide gemessen:
    #   * **Ein HA-Anwender ohne MQTT sah sie nicht** — die Sensor-Referenz
    #     beschreibt Attribute, die über REST nie ankamen.
    #   * **Der Golden Master sah sie nicht.** Jeder Umbau, der ein Attribut
    #     ändert (S3b/B0 stellt die gesamte Zeitachse um), lief bis hierher
    #     durch ein Gate, das genau diese Hälfte des Exports nicht kennt —
    #     „26 Sichten, 0 Unterschiede" hieß „0 Unterschiede in dem, was REST
    #     zeigt". Deshalb steht dieser Schritt VOR der Achsen-Umstellung.
    # `hinweis` bleibt daneben stehen: er ist die herausgehobene Kurzform für
    # die Oberfläche, nicht dasselbe wie das Roh-Attribut.
    attribute: dict = Field(default_factory=dict)

    @classmethod
    def von_sensorwert(cls, sv: SensorValue) -> "SensorExportItem":
        """Ein `SensorValue` als REST-Item — die EINE Übersetzung.

        ⚠ **Warum als Klassenmethode und nicht dreimal ausgeschrieben.** Genau
        dieselben elf Felder wurden an drei Stellen gefüllt (`/sensors` zweimal,
        `/sensors/{id}`); ein neues Feld musste dreimal nachgetragen werden, und
        wer eine vergisst, erzeugt zwei REST-Sichten mit verschiedenem Inhalt.
        Dasselbe Argument, mit dem die Rundung schon an diesem Modell sitzt.
        """
        return cls(
            key=sv.definition.key,
            name=sv.definition.name,
            value=sv.value,
            unit=sv.definition.unit,
            icon=sv.definition.icon,
            category=sv.definition.category.value,
            formel=sv.definition.formel,
            berechnung=sv.berechnung,
            hinweis=_hinweis(sv),
            device_class=sv.definition.device_class,
            state_class=sv.definition.state_class,
            attribute=dict(sv.zusatz_attribute or {}),
        )

    @model_validator(mode="after")
    def _runde_wert(self):
        gerundet = runde_exportwert(self.value, self.unit, self.category)
        if gerundet is not self.value:
            # `model_construct`-freier Weg: Zuweisung im After-Validator läuft
            # nicht erneut durch die Validierung (Pydantic v2).
            object.__setattr__(self, "value", gerundet)
        return self

class AnlageExport(BaseModel):
    """Export für eine Anlage."""
    anlage_id: int
    anlage_name: str
    sensors: list[SensorExportItem]

class InvestitionExport(BaseModel):
    """Export für eine Investition."""
    investition_id: int
    bezeichnung: str
    typ: str
    sensors: list[SensorExportItem]

class FullExportResponse(BaseModel):
    """Vollständiger Export aller Sensoren."""
    anlagen: list[AnlageExport]
    investitionen: list[InvestitionExport]
    sensor_count: int
    mqtt_available: bool

class HAYamlSnippet(BaseModel):
    """YAML-Snippet für HA configuration.yaml."""
    yaml: str
    sensor_count: int
    hinweis: str

class MQTTConfigResponse(BaseModel):
    """Aufgelöste MQTT-Verbindung + Export-Richtung (B7-5/B7-5b/B7-5d)."""
    enabled: bool  # Verbindung wird genutzt = mindestens eine Richtung an
    host: str
    port: int
    username: str
    password: str  # Wird als Maske zurückgegeben wenn gesetzt
    auto_publish: bool  # Export-Toggle (Eigenwert) — nicht mit `enabled` verundet
    publish_interval_minutes: int
    # Ist überhaupt ein Broker hinterlegt? `host` allein taugt nicht als Antwort:
    # die Auflösung liefert IMMER einen (Default `core-mosquitto`). Ohne Broker
    # kann der Export nichts publizieren — die Sensoren erscheinen dann nie in HA.
    broker_konfiguriert: bool

class AutoPublishRequest(BaseModel):
    """Body für den Export-Toggle (B7-5b)."""
    enabled: bool

class AbwahlRequest(BaseModel):
    """Body für die Sensor-Abwahl (#400).

    Die **vollständige** Liste der abgewählten Schlüssel, nicht ein Delta — die
    Oberfläche kennt den Gesamtzustand ihrer Häkchen und schickt ihn. Ein Delta
    („diesen einen dazu") wäre gegenüber einer zweiten offenen Sitzung nicht
    entscheidbar.
    """
    abgewaehlt: list[str]
