"""
SMA Sunny Portal CSV Parser.

Unterstützt:
- Sunny Portal Classic: Jahresansicht-Export (Monatswerte) und Monatsansicht (Tageswerte)
- Sunny Portal ennexOS: Analysis Pro CSV Export
- Legacy SunnyMail-Format (SUNNY-MAIL Header)

Format-Varianten:
- DE: Semikolon-getrennt, dd.mm.yyyy, Komma-Dezimal
- EN: Semikolon-getrennt, mm/dd/yyyy, Punkt-Dezimal
"""

import csv
import re
from collections import defaultdict
from datetime import datetime
from io import StringIO
from typing import Optional

from .base import PortalExportParser, ParsedMonthData, ParserInfo
from .registry import register_parser


# Spalten-Mapping: Verschiedene Bezeichnungen → internes Feld
# Reihenfolge = Priorität (erster Match gewinnt)
COLUMN_MAPPINGS: dict[str, list[str]] = {
    "pv_erzeugung_kwh": [
        "ertrag",
        "gesamtertrag",
        "gesamterzeugung",
        "total yield",
        "yield",
        "pv-erzeugung",
        "pv erzeugung",
        "erzeugung",
        "generation",
        "pv generation",
    ],
    "einspeisung_kwh": [
        "einspeisung",
        "netzeinspeisung",
        "grid feed-in",
        "grid feedin",
        "feed-in",
        "feedin",
        "einspeisezähler",
        "einspeisezaehler",
    ],
    "netzbezug_kwh": [
        "netzbezug",
        "grid consumption",
        "grid purchase",
        "bezug",
        "strombezug",
        "bezugszähler",
        "bezugszaehler",
    ],
    "eigenverbrauch_kwh": [
        "eigenverbrauch",
        "self-consumption",
        "self consumption",
        "direktverbrauch",
    ],
    "batterie_ladung_kwh": [
        "batteriesystem ladung",
        "batterieladung",
        "batterie ladung",
        "battery charge",
        "bat ladung",
        "speicher ladung",
    ],
    "batterie_entladung_kwh": [
        "batteriesystem entladung",
        "batterieentladung",
        "batterie entladung",
        "battery discharge",
        "bat entladung",
        "speicher entladung",
    ],
}

# Datum-Spalten-Bezeichnungen
DATE_COLUMNS = ["datum", "date", "zeitraum", "zeit", "time", "zeitstempel", "timestamp"]


def _normalize(text: str) -> str:
    """Normalisiert Text für Vergleich: Lowercase, Umlaute, Sonderzeichen entfernen."""
    text = text.lower().strip()
    text = text.replace("ä", "ae").replace("ö", "oe").replace("ü", "ue").replace("ß", "ss")
    # Einheit in Klammern entfernen: "Ertrag [kWh]" → "Ertrag"
    text = re.sub(r"\s*\[.*?\]\s*", "", text)
    text = re.sub(r"\s*\(.*?\)\s*", "", text)
    # Sonderzeichen zu Leerzeichen
    text = re.sub(r"[^a-z0-9 ]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _parse_float(val: str) -> Optional[float]:
    """Parsed Float mit DE/EN Locale Support."""
    if not val or not val.strip():
        return None
    val = val.strip()
    # "NaN", "-", "---" etc. behandeln
    if val.lower() in ("nan", "-", "---", "n/a", ""):
        return None
    # Deutsche Locale: 1.234,56 → 1234.56
    if "," in val and "." in val:
        val = val.replace(".", "").replace(",", ".")
    elif "," in val:
        val = val.replace(",", ".")
    try:
        result = float(val)
        return result if result >= 0 else None
    except ValueError:
        return None


_MONTH_NAMES_DE: dict[str, int] = {
    "jan": 1, "januar": 1,
    "feb": 2, "februar": 2,
    "mär": 3, "maer": 3, "mrz": 3, "märz": 3, "maerz": 3,
    "apr": 4, "april": 4,
    "mai": 5,
    "jun": 6, "juni": 6,
    "jul": 7, "juli": 7,
    "aug": 8, "august": 8,
    "sep": 9, "sept": 9, "september": 9,
    "okt": 10, "oktober": 10,
    "nov": 11, "november": 11,
    "dez": 12, "dezember": 12,
}


def _parse_date(val: str) -> Optional[tuple[int, int, int]]:
    """Parsed Datum und gibt (jahr, monat, tag) zurück."""
    val = val.strip()
    # DD.MM.YYYY (deutsch)
    match = re.match(r"(\d{1,2})\.(\d{1,2})\.(\d{4})", val)
    if match:
        return int(match.group(3)), int(match.group(2)), int(match.group(1))
    # YYYY-MM-DD (ISO)
    match = re.match(r"(\d{4})-(\d{1,2})-(\d{1,2})", val)
    if match:
        return int(match.group(1)), int(match.group(2)), int(match.group(3))
    # MM/DD/YYYY (US)
    match = re.match(r"(\d{1,2})/(\d{1,2})/(\d{4})", val)
    if match:
        return int(match.group(3)), int(match.group(1)), int(match.group(2))
    # YYYY-MM (nur Jahr+Monat, für aggregierte Daten)
    match = re.match(r"(\d{4})-(\d{1,2})$", val)
    if match:
        return int(match.group(1)), int(match.group(2)), 0
    # MM.YYYY oder MM/YYYY
    match = re.match(r"(\d{1,2})[./](\d{4})$", val)
    if match:
        return int(match.group(2)), int(match.group(1)), 0
    # Deutsche Monatsnamen: "Jan. 2026", "Februar 2026", "März 2026"
    match = re.match(r"([A-Za-zäöüÄÖÜ]+)\.?\s+(\d{4})", val)
    if match:
        month_name = match.group(1).lower()
        monat = _MONTH_NAMES_DE.get(month_name)
        if monat:
            return int(match.group(2)), monat, 0
    return None


def _detect_column_mapping(headers: list[str]) -> dict[str, str]:
    """Erkennt welche CSV-Spalte welchem EEDC-Feld entspricht.

    Returns: {eedc_feld: csv_spaltenname}
    """
    mapping: dict[str, str] = {}
    used_columns: set[str] = set()

    for eedc_feld, patterns in COLUMN_MAPPINGS.items():
        for header in headers:
            if header in used_columns:
                continue
            normalized = _normalize(header)
            for pattern in patterns:
                if pattern in normalized:
                    mapping[eedc_feld] = header
                    used_columns.add(header)
                    break
            if eedc_feld in mapping:
                break

    return mapping


def _detect_date_column(headers: list[str]) -> Optional[str]:
    """Findet die Datum-Spalte."""
    for header in headers:
        normalized = _normalize(header)
        for pattern in DATE_COLUMNS:
            if pattern in normalized:
                return header
    # Fallback: Erste Spalte ist oft das Datum
    if headers:
        return headers[0]
    return None


def _skip_sunny_mail_header(content: str) -> str:
    """Überspringt den SUNNY-MAIL Header (5 Zeilen) falls vorhanden."""
    lines = content.split("\n")
    if lines and lines[0].strip().upper().startswith("SUNNY-MAIL"):
        # SUNNY-MAIL Format: 5 Header-Zeilen, dann Kommentare (#), dann Daten
        data_start = 0
        for i, line in enumerate(lines):
            if i < 5:
                continue
            stripped = line.strip()
            if stripped and not stripped.startswith("#"):
                data_start = i
                break
        return "\n".join(lines[data_start:])
    return content


@register_parser
class SMASunnyPortalParser(PortalExportParser):
    """Parser für SMA Sunny Portal CSV-Exporte."""

    def info(self) -> ParserInfo:
        return ParserInfo(
            id="sma_sunny_portal",
            name="SMA Sunny Portal",
            hersteller="SMA",
            beschreibung=(
                "Importiert CSV-Exporte aus dem SMA Sunny Portal (Classic oder ennexOS). "
                "Unterstützt Jahresübersichten (Monatswerte) und Monatsansichten (Tageswerte, "
                "werden automatisch pro Monat aggregiert)."
            ),
            erwartetes_format="CSV (Semikolon-getrennt)",
            anleitung=(
                "1. Sunny Portal öffnen (sunnyportal.com oder ennexos.sunnyportal.com)\n"
                "2. Zur Seite 'Energiebilanz' navigieren\n"
                "3. Rechts oben im Dropdown 'Energiefluss' auswählen\n"
                "4. Jahresansicht wählen (Tab 'Jahr') für Monatswerte\n"
                "5. 'Details' aufklappen → 'Download' klicken\n"
                "6. Die heruntergeladene CSV-Datei hier hochladen"
            ),
            beispiel_header="Zeitraum;Direktverbrauch [kWh];Batteriesystem-Entladung [kWh];Netzbezug [kWh];...;Gesamterzeugung [kWh]",
        )

    def can_parse(self, content: str, filename: str) -> bool:
        """Erkennt SMA-Format anhand von Semikolon + typischen Spaltennamen."""
        # SUNNY-MAIL Header?
        if content.strip().upper().startswith("SUNNY-MAIL"):
            return True

        lines = content.split("\n", 20)
        if not lines:
            return False

        # Semikolon prüfen (mindestens eine Zeile mit ;)
        has_semicolon = any(";" in line for line in lines)
        if not has_semicolon:
            return False

        # ennexOS Metadata-Header erkennen ("Id der Anlage", "Name der Anlage")
        all_text = "\n".join(lines).lower()
        if "id der anlage" in all_text or "name der anlage" in all_text:
            # Wallbox/Ladestation-CSVs ohne PV-Daten ausschließen (eigener Parser)
            has_wallbox = "ladestation" in all_text or ("wallbox" in all_text and "name des" in all_text)
            has_pv = any(ind in all_text for ind in [
                "gesamterzeugung", "direktverbrauch", "netzeinspeisung",
                "eigenverbrauch", "einspeisung", "ertrag",
            ])
            if has_wallbox and not has_pv:
                return False
            return True

        # Alle Zeilen auf SMA-typische Spaltennamen prüfen
        sma_indicators = [
            "ertrag", "eigenverbrauch", "einspeisung", "netzbezug",
            "total yield", "gesamterzeugung", "direktverbrauch",
            "batteriesystem", "netzeinspeisung",
        ]
        for line in lines:
            normalized = _normalize(line)
            matches = sum(1 for ind in sma_indicators if ind in normalized)
            if matches >= 2:
                return True

        return False

    def _find_header_row(self, rows: list[list[str]]) -> int:
        """Findet die Header-Zeile in der CSV.

        Sucht nach Zeilen mit bekannten Spaltenbezeichnungen (Datum, Zeitraum,
        Ertrag, Direktverbrauch etc.). Überspring dabei ennexOS-Metadaten.
        """
        header_indicators = [
            "datum", "zeitraum", "date", "ertrag", "direktverbrauch",
            "gesamterzeugung", "eigenverbrauch", "einspeisung", "netzbezug",
            "total yield", "netzeinspeisung",
        ]
        for i, row in enumerate(rows):
            if not row or len(row) < 2:
                continue
            # Alle Zellen der Zeile normalisiert prüfen
            normalized_row = " ".join(_normalize(cell) for cell in row)
            matches = sum(1 for ind in header_indicators if ind in normalized_row)
            if matches >= 2:
                return i
        # Fallback: erste nicht-leere Zeile
        for i, row in enumerate(rows):
            if row and any(cell.strip() for cell in row):
                return i
        return 0

    def parse(self, content: str) -> list[ParsedMonthData]:
        """Parsed SMA Sunny Portal CSV und gibt Monatswerte zurück."""
        # SUNNY-MAIL Header überspringen
        content = _skip_sunny_mail_header(content)

        # sep=; Zeile am Anfang entfernen
        lines = content.split("\n")
        if lines and lines[0].strip().lower().startswith("sep="):
            content = "\n".join(lines[1:])

        # CSV lesen
        reader = csv.reader(StringIO(content), delimiter=";")
        rows = list(reader)

        if len(rows) < 2:
            return []

        # Header-Zeile finden: Zeile mit bekannten Spaltennamen suchen
        header_idx = self._find_header_row(rows)

        headers = [h.strip() for h in rows[header_idx]]

        # Spalten-Mapping erkennen
        date_col = _detect_date_column(headers)
        col_mapping = _detect_column_mapping(headers)

        if not date_col:
            return []

        # Daten sammeln (Tageswerte pro Monat aggregieren)
        monthly_data: dict[tuple[int, int], dict[str, float]] = defaultdict(
            lambda: defaultdict(float)
        )
        monthly_counts: dict[tuple[int, int], int] = defaultdict(int)

        for row in rows[header_idx + 1 :]:
            if len(row) < 2:
                continue

            # Datum parsen
            date_idx = headers.index(date_col) if date_col in headers else 0
            if date_idx >= len(row):
                continue

            parsed_date = _parse_date(row[date_idx])
            if not parsed_date:
                continue

            jahr, monat, _tag = parsed_date
            if jahr < 2000 or jahr > 2100 or monat < 1 or monat > 12:
                continue

            key = (jahr, monat)
            monthly_counts[key] += 1

            # Energiewerte parsen und aggregieren
            for eedc_feld, csv_col in col_mapping.items():
                if csv_col in headers:
                    col_idx = headers.index(csv_col)
                    if col_idx < len(row):
                        val = _parse_float(row[col_idx])
                        if val is not None:
                            monthly_data[key][eedc_feld] += val

        # ParsedMonthData erstellen
        result: list[ParsedMonthData] = []
        for (jahr, monat) in sorted(monthly_data.keys()):
            values = monthly_data[(jahr, monat)]
            if not values:
                continue

            month = ParsedMonthData(
                jahr=jahr,
                monat=monat,
                pv_erzeugung_kwh=round(values.get("pv_erzeugung_kwh", 0), 2) or None,
                einspeisung_kwh=round(values.get("einspeisung_kwh", 0), 2) or None,
                netzbezug_kwh=round(values.get("netzbezug_kwh", 0), 2) or None,
                batterie_ladung_kwh=round(values.get("batterie_ladung_kwh", 0), 2) or None,
                batterie_entladung_kwh=round(values.get("batterie_entladung_kwh", 0), 2) or None,
                eigenverbrauch_kwh=round(values.get("eigenverbrauch_kwh", 0), 2) or None,
            )

            if month.has_data():
                result.append(month)

        return result
