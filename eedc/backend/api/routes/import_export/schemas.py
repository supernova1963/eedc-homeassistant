"""
Import/Export Pydantic Schemas

Alle Datenmodelle für Import/Export-Operationen.
"""

from typing import Optional
from pydantic import BaseModel


class ImportResult(BaseModel):
    """Ergebnis eines CSV-Imports."""
    erfolg: bool
    importiert: int
    uebersprungen: int
    fehler: list[str]
    warnungen: list[str] = []


class JSONImportResult(BaseModel):
    """Ergebnis eines JSON-Imports."""
    erfolg: bool
    anlage_id: Optional[int] = None
    anlage_name: Optional[str] = None
    importiert: dict = {}  # {"strompreise": 3, "investitionen": 5, ...}
    warnungen: list[str] = []
    fehler: list[str] = []


class DemoDataResult(BaseModel):
    """Ergebnis der Demo-Daten Erstellung."""
    erfolg: bool
    anlage_id: int
    anlage_name: str
    monatsdaten_count: int
    investitionen_count: int
    strompreise_count: int
    message: str


class CSVTemplateInfo(BaseModel):
    """Info über das CSV-Template."""
    spalten: list[str]
    beschreibung: dict[str, str]


# =============================================================================
# JSON Export Schemas
# =============================================================================

class InvestitionMonatsdatenExport(BaseModel):
    """Export-Schema für Investition-Monatsdaten."""
    jahr: int
    monat: int
    verbrauch_daten: dict


class InvestitionExport(BaseModel):
    """Export-Schema für eine Investition."""
    typ: str
    bezeichnung: str
    anschaffungsdatum: Optional[str] = None
    anschaffungskosten_gesamt: Optional[float] = None
    anschaffungskosten_alternativ: Optional[float] = None
    betriebskosten_jahr: Optional[float] = None
    aktiv: bool
    leistung_kwp: Optional[float] = None
    ausrichtung: Optional[str] = None
    neigung_grad: Optional[float] = None
    parameter: Optional[dict] = None
    monatsdaten: list[InvestitionMonatsdatenExport] = []
    children: list["InvestitionExport"] = []


class StrompreisExport(BaseModel):
    """Export-Schema für einen Strompreis."""
    tarifname: str
    anbieter: Optional[str] = None
    netzbezug_arbeitspreis_cent_kwh: float
    einspeiseverguetung_cent_kwh: float
    grundgebuehr_monat: float
    gueltig_von: str
    gueltig_bis: Optional[str] = None


class MonatsdatenExport(BaseModel):
    """Export-Schema für Monatsdaten."""
    jahr: int
    monat: int
    einspeisung_kwh: float
    netzbezug_kwh: float
    strompreis_id: Optional[int] = None
    sonnenstunden: Optional[float] = None
    durchschnittstemperatur: Optional[float] = None
    globalstrahlung_kwh_m2: Optional[float] = None
    niederschlag_mm: Optional[float] = None


class PVGISMonatsprognoseExport(BaseModel):
    """Export-Schema für PVGIS Monatsprognose."""
    monat: int
    e_m: float
    h_sun: float
    sd_m: float


class PVGISPrognoseExport(BaseModel):
    """Export-Schema für PVGIS Prognose."""
    jahresertrag_kwh: float
    spezifischer_ertrag_kwh_kwp: float
    monatsprognosen: list[PVGISMonatsprognoseExport] = []


class AnlageExport(BaseModel):
    """Export-Schema für Anlage-Stammdaten."""
    anlagenname: str
    leistung_kwp: float
    installationsdatum: Optional[str] = None
    standort_plz: Optional[str] = None
    standort_ort: Optional[str] = None
    standort_strasse: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    ausrichtung: Optional[str] = None
    neigung_grad: Optional[float] = None
    mastr_id: Optional[str] = None
    versorger_daten: Optional[dict] = None


class FullAnlageExport(BaseModel):
    """Vollständiges Export-Schema einer Anlage."""
    export_version: str = "1.0"
    export_datum: str
    eedc_version: str
    anlage: AnlageExport
    strompreise: list[StrompreisExport] = []
    investitionen: list[InvestitionExport] = []
    monatsdaten: list[MonatsdatenExport] = []
    pvgis_prognose: Optional[PVGISPrognoseExport] = None
