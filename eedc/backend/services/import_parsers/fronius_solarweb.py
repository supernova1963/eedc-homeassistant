"""
Fronius Solar.web CSV Parser.

Unterstützt den CSV-Export der Energiebilanz aus Fronius Solar.web (Classic/Premium).

Format:
- Semikolon- oder Komma-getrennt, UTF-8 (teilweise mit BOM)
- Tages- oder 5-Minuten-Werte, werden pro Monat aggregiert
- Spalten: Datum, PV-Erzeugung, Einspeisung, Netzbezug, Eigenverbrauch, Verbrauch
- Werte in Wh (werden zu kWh konvertiert)

Besonderheiten:
- Spaltenbezeichnungen können deutsch oder englisch sein
- Unterstützt Reports vom Typ "Energiebilanz" und "Energy Balance"

HINWEIS: Dieser Parser wurde anhand der Fronius-Dokumentation und
Community-Berichten erstellt, aber noch nicht mit echten Export-Dateien
verifiziert (getestet=False).
"""

import csv
from collections import defaultdict
from io import StringIO
from typing import Optional

from .base import PortalExportParser, ParsedMonthData, ParserInfo
from .registry import register_parser
from .sma_sunny_portal import _normalize, _parse_float


# Spalten-Mapping: normalisierter Name → (internes Feld, Priorität)
# Höhere Priorität gewinnt bei mehreren Treffern
COLUMN_PATTERNS: dict[str, list[str]] = {
    "pv_erzeugung": [
        "pv production", "pv-erzeugung", "gesamtenergie", "energy",
        "erzeugung", "ertrag", "produced",
    ],
    "einspeisung": [
        "energy to grid", "einspeisung", "einspeisen", "feed-in",
        "feed in", "netzeinspeisung", "eingespeist", "ins netz",
    ],
    "netzbezug": [
        "energy from grid", "netzbezug", "from grid",
        "gridbezug", "grid consumption", "netz bezogen", "vom netz",
    ],
    "eigenverbrauch": [
        "consumed directly", "eigenverbrauch", "self-consumption",
        "self consumption", "direktverbrauch", "direkt verbraucht",
    ],
    "verbrauch": [
        "consumption", "gesamtverbrauch", "total consumption", "verbrauch",
    ],
    "batterie_ladung": [
        "energy into battery", "in batterie gespeichert", "batterie ladung",
        "battery charge", "in batterie", "speicher ladung",
    ],
    "batterie_entladung": [
        "energy from battery", "aus batterie bezogen", "batterie entladung",
        "battery discharge", "aus batterie", "speicher entladung",
    ],
}


def _detect_delimiter(content: str) -> str:
    """Erkennt den Delimiter (Semikolon oder Komma) anhand der ersten Zeile."""
    first_line = content.split("\n", 1)[0]
    if first_line.count(";") > first_line.count(","):
        return ";"
    return ","


def _parse_date(val: str) -> Optional[tuple[int, int]]:
    """Parsed verschiedene Datumsformate und gibt (jahr, monat) zurück.

    Unterstützt:
    - DD.MM.YYYY (HH:MM:SS)
    - YYYY-MM-DD (HH:MM:SS)
    - MM/DD/YYYY (HH:MM:SS)
    """
    val = val.strip().split(" ")[0].split("T")[0]  # Nur Datumsteil
    if not val:
        return None

    try:
        if "." in val:
            # DD.MM.YYYY
            parts = val.split(".")
            if len(parts) >= 3:
                return int(parts[2][:4]), int(parts[1])
        elif "-" in val:
            # YYYY-MM-DD
            parts = val.split("-")
            if len(parts) >= 2:
                return int(parts[0]), int(parts[1])
        elif "/" in val:
            # MM/DD/YYYY
            parts = val.split("/")
            if len(parts) >= 3:
                return int(parts[2][:4]), int(parts[0])
    except (ValueError, IndexError):
        pass
    return None


def _wh_to_kwh(value: Optional[float], header: str, unit: str = "") -> Optional[float]:
    """Konvertiert Wh zu kWh.

    Nutzt die explizite Einheit aus der Einheitenzeile (bevorzugt).
    Fallback: Heuristik über den Spaltenheader.

    WICHTIG: Die alte Heuristik (value > 1000) ist bewusst NICHT mehr vorhanden —
    sie versagt bei kleinen Tageswerten (z.B. 97 Wh an trüben Wintertagen),
    die dann fälschlicherweise als 97 kWh importiert werden.
    """
    if value is None:
        return None

    # Explizite Einheit aus Einheitenzeile (z.B. "[Wh]" → "Wh")
    u = unit.strip().lower()
    if u == "kwh":
        return value
    if u == "wh":
        return value / 1000.0

    # Fallback: Einheit aus Spaltenheader ableiten
    h = header.lower()
    if "kwh" in h:
        return value
    # Fronius-Standard: alle Energiespalten in Wh → immer konvertieren
    return value / 1000.0


@register_parser
class FroniusSolarwebParser(PortalExportParser):
    """Parser für Fronius Solar.web Energiebilanz-CSV-Exporte."""

    def info(self) -> ParserInfo:
        return ParserInfo(
            id="fronius_solarweb",
            name="Fronius Solar.web",
            hersteller="Fronius",
            beschreibung=(
                "Importiert CSV-Exporte der Energiebilanz aus Fronius Solar.web "
                "(Classic oder Premium). Tages- oder Intervall-Daten werden pro "
                "Monat aggregiert."
            ),
            erwartetes_format="CSV (Semikolon- oder Komma-getrennt, UTF-8)",
            anleitung=(
                "1. Fronius Solar.web öffnen (solarweb.com)\n"
                "2. Berichte → Neuen Bericht erstellen\n"
                "3. Typ 'Energiebilanz' wählen, gewünschten Zeitraum einstellen\n"
                "4. Als CSV herunterladen\n"
                "5. Die heruntergeladene CSV-Datei hier hochladen"
            ),
            beispiel_header="Date and time;PV production [Wh];Energy to grid [Wh];Energy from grid [Wh];Consumed directly [Wh]",
            getestet=True,
        )

    def can_parse(self, content: str, filename: str) -> bool:
        """Erkennt Fronius-Format anhand typischer Spaltenbezeichnungen."""
        lines = content.split("\n", 5)
        if not lines:
            return False

        header_line = _normalize(lines[0])

        # Fronius-spezifische Indikatoren
        fronius_indicators = [
            "pv production", "energy to grid", "energy from grid",
            "consumed directly", "fronius",
            "gesamtenergie", "netzeinspeisung", "netzbezug",
            "gesamt erzeugung", "eingespeist", "netz bezogen",
        ]
        matches = sum(1 for ind in fronius_indicators if ind in header_line)
        return matches >= 2

    def parse(self, content: str) -> list[ParsedMonthData]:
        """Parsed Fronius CSV und aggregiert Werte pro Monat."""
        delimiter = _detect_delimiter(content)
        reader = csv.reader(StringIO(content), delimiter=delimiter)
        rows = list(reader)

        if len(rows) < 2:
            return []

        headers = [h.strip() for h in rows[0]]
        normalized = [_normalize(h) for h in headers]

        # Einheitenzeile erkennen: Fronius schreibt z.B.
        # "[dd.MM.yyyy],[Wh],[Wh],[Wh],[Wh],[Wh]" als zweite Zeile.
        # _parse_date schlägt auf "[dd.MM.yyyy]" fehl → die Zeile wurde bisher
        # still übersprungen und die Einheiten gingen verloren.
        units: list[str] = [""] * len(headers)
        data_start = 1
        if len(rows) >= 2:
            candidate = rows[1]
            # Einheitenzeile: erste Zelle kein gültiges Datum, Rest in [...]-Notation
            if candidate and not _parse_date(candidate[0]):
                parsed_units = [c.strip().strip("[]") for c in candidate]
                units = parsed_units + [""] * (len(headers) - len(parsed_units))
                data_start = 2

        # Spalten-Indizes finden (bereits belegte Indizes nicht doppelt vergeben)
        col_map: dict[str, Optional[int]] = {}
        used_indices: set[int] = set()
        for field, patterns in COLUMN_PATTERNS.items():
            idx = self._find_col(normalized, patterns, used_indices)
            col_map[field] = idx
            if idx is not None:
                used_indices.add(idx)

        # Datum-Spalte: erste Spalte ist typischerweise das Datum
        col_date = 0

        # Prüfen ob wir genug Spalten haben
        if col_map.get("pv_erzeugung") is None and col_map.get("einspeisung") is None:
            return []

        # Werte pro Monat aggregieren
        monthly: dict[tuple[int, int], dict[str, float]] = defaultdict(
            lambda: defaultdict(float)
        )

        for row in rows[data_start:]:
            if not row or len(row) <= col_date:
                continue

            # Leere Zeilen oder Header-Wiederholungen überspringen
            if not row[col_date].strip():
                continue

            parsed = _parse_date(row[col_date])
            if not parsed:
                continue
            key = parsed

            for field, col_idx in col_map.items():
                if col_idx is not None and col_idx < len(row):
                    val = _parse_float(row[col_idx])
                    unit = units[col_idx] if col_idx < len(units) else ""
                    val = _wh_to_kwh(val, headers[col_idx], unit)
                    if val is not None and val >= 0:
                        monthly[key][field] += val

        # ParsedMonthData erstellen
        result: list[ParsedMonthData] = []
        for (jahr, monat) in sorted(monthly.keys()):
            data = monthly[(jahr, monat)]
            if not any(v > 0 for v in data.values()):
                continue

            # Eigenverbrauch: direkt oder berechnet (Erzeugung - Einspeisung)
            eigenverbrauch = data.get("eigenverbrauch")
            if not eigenverbrauch and data.get("pv_erzeugung") and data.get("einspeisung"):
                eigenverbrauch = data["pv_erzeugung"] - data["einspeisung"]
                if eigenverbrauch < 0:
                    eigenverbrauch = None

            result.append(ParsedMonthData(
                jahr=jahr,
                monat=monat,
                pv_erzeugung_kwh=round(data["pv_erzeugung"], 2) if data.get("pv_erzeugung") else None,
                einspeisung_kwh=round(data["einspeisung"], 2) if data.get("einspeisung") else None,
                netzbezug_kwh=round(data["netzbezug"], 2) if data.get("netzbezug") else None,
                eigenverbrauch_kwh=round(eigenverbrauch, 2) if eigenverbrauch else None,
                batterie_ladung_kwh=round(data["batterie_ladung"], 2) if data.get("batterie_ladung") else None,
                batterie_entladung_kwh=round(data["batterie_entladung"], 2) if data.get("batterie_entladung") else None,
            ))

        return result

    def _find_col(self, normalized_headers: list[str], patterns: list[str],
                  used: set[int] | None = None) -> Optional[int]:
        """Findet den Index einer Spalte anhand von Suchbegriffen."""
        for idx, header in enumerate(normalized_headers):
            if used and idx in used:
                continue
            for pattern in patterns:
                if pattern in header:
                    return idx
        return None
