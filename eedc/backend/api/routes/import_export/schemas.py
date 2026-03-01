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
