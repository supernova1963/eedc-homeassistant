"""
Basis-Klassen für Portal-Export-Parser.

Jeder Hersteller-Parser implementiert PortalExportParser und wird
über den @register_parser Decorator in der Registry registriert.
"""

from abc import ABC, abstractmethod
from collections.abc import Hashable, Mapping
from dataclasses import dataclass, asdict
from typing import Optional


def monatswert(summen: Mapping[Hashable, float], *schluessel: Hashable) -> Optional[float]:
    """Monatswert eines Feldes aus den Monatssummen eines Parsers (N-714).

    Die Parser addieren eine Zelle nur, wenn `_parse_float` eine Zahl liefert —
    auch `0` oder `0,0`; eine leere Zelle, `-`, `n/a` oder Unlesbares legt
    keinen Schlüssel an. Der Schlüssel ist deshalb die Anwesenheit: mindestens
    eine Zelle mit Zahl ⇒ Wert (eine Summe 0,0 ist ein Messwert), keine ⇒ None.
    Mehrere Schlüssel (z. B. die Wattpilot-Anteile) ergeben ihre Summe, sobald
    einer vorhanden ist. Nie `or None` / `if wert` — das macht aus 0 ein «fehlt».
    """
    teile = [summen[k] for k in schluessel if k in summen]
    if not teile:
        return None
    return round(sum(teile), 2)


def monat_hat_wert_ueber_null(summen: Mapping[Hashable, float]) -> bool:
    """Monats-Tor der Parser: ein Monat erscheint nur mit mindestens einem Wert > 0.

    Ein Monat, dessen Zellen alle 0 sind, steht in keiner Vorschau (wie vor
    N-714) — innerhalb eines gezeigten Monats ist eine 0 aber ein Wert
    (`monatswert`).
    """
    return any(v > 0 for v in summen.values())


@dataclass
class ParsedMonthData:
    """Ein Monat an geparsten Energiedaten aus einem Portal-Export."""

    jahr: int
    monat: int
    pv_erzeugung_kwh: Optional[float] = None
    einspeisung_kwh: Optional[float] = None
    netzbezug_kwh: Optional[float] = None
    batterie_ladung_kwh: Optional[float] = None
    batterie_entladung_kwh: Optional[float] = None
    eigenverbrauch_kwh: Optional[float] = None
    # Wallbox / Ladestation
    wallbox_ladung_kwh: Optional[float] = None
    wallbox_ladung_pv_kwh: Optional[float] = None
    wallbox_ladevorgaenge: Optional[int] = None
    # E-Auto
    eauto_km_gefahren: Optional[float] = None

    def to_dict(self) -> dict:
        return asdict(self)

    def has_data(self) -> bool:
        """Prüft ob mindestens ein Energiewert vorhanden ist."""
        return any(
            v is not None
            for v in [
                self.pv_erzeugung_kwh,
                self.einspeisung_kwh,
                self.netzbezug_kwh,
                self.batterie_ladung_kwh,
                self.batterie_entladung_kwh,
                self.eigenverbrauch_kwh,
                self.wallbox_ladung_kwh,
                self.wallbox_ladung_pv_kwh,
                self.eauto_km_gefahren,
            ]
        )


@dataclass
class ParserInfo:
    """Metadaten eines Parsers für die UI-Anzeige."""

    id: str
    name: str
    hersteller: str
    beschreibung: str
    erwartetes_format: str
    anleitung: str
    beispiel_header: str
    getestet: bool = True

    def to_dict(self) -> dict:
        return asdict(self)


class PortalExportParser(ABC):
    """Abstrakte Basisklasse für Portal-Export-Parser."""

    @abstractmethod
    def info(self) -> ParserInfo:
        """Parser-Metadaten für die UI."""

    @abstractmethod
    def can_parse(self, content: str, filename: str) -> bool:
        """Prüft ob dieser Parser die Datei verarbeiten kann (Auto-Detect)."""

    @abstractmethod
    def parse(self, content: str) -> list[ParsedMonthData]:
        """Parsed die Datei und gibt Monatswerte zurück."""
