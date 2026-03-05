"""
SMA ECharger (Wallbox) CSV Parser.

Unterstützt CSV-Exporte aus dem SMA ennexOS Portal für die Wallbox / Ladestation.

Format:
- ennexOS Metadata-Header (10 Zeilen), dann Datenzeilen
- Semikolon-getrennt, Komma-Dezimal (DE Locale)
- Jahresansicht: "Jan. 2026", "Feb. 2026" → Monatswerte
- Monatsansicht: "01.02.2026" → Tageswerte (werden aggregiert)

Spalten:
- "Zählerstand Ladestation [kWh]" → Ladung pro Periode (Delta)
- "Zählerstand Ladestation Zählerstand [kWh]" → Kumulativer Zählerstand

Ladevorgänge: Bei Tageswerten wird die Anzahl Tage mit Ladung > 0 gezählt.
"""

import csv
from collections import defaultdict
from io import StringIO
from typing import Optional

from .base import PortalExportParser, ParsedMonthData, ParserInfo
from .registry import register_parser
from .sma_sunny_portal import _normalize, _parse_float, _parse_date


# Spalten-Erkennung für Wallbox-Ladung (Delta pro Periode)
LADUNG_PATTERNS = [
    "zaehlerstand ladestation",
    "ladestation",
    "ladung",
    "wallbox",
    "charging",
    "charge energy",
]

# Spalten die den kumulativen Zählerstand enthalten (ignorieren)
ZAEHLERSTAND_PATTERNS = [
    "zaehlerstand ladestation zaehlerstand",
    "ladestation zaehlerstand",
    "cumulative",
    "total meter",
]


def _is_cumulative_column(header: str) -> bool:
    """Prüft ob die Spalte ein kumulativer Zählerstand ist."""
    normalized = _normalize(header)
    return any(p in normalized for p in ZAEHLERSTAND_PATTERNS)


def _is_ladung_column(header: str) -> bool:
    """Prüft ob die Spalte Lade-Energie (Delta) enthält."""
    normalized = _normalize(header)
    if _is_cumulative_column(header):
        return False
    return any(p in normalized for p in LADUNG_PATTERNS)


@register_parser
class SMAEChargerParser(PortalExportParser):
    """Parser für SMA ECharger / Wallbox CSV-Exporte aus dem ennexOS Portal."""

    def info(self) -> ParserInfo:
        return ParserInfo(
            id="sma_echarger",
            name="SMA Wallbox (ECharger)",
            hersteller="SMA",
            beschreibung=(
                "Importiert CSV-Exporte der Wallbox / Ladestation aus dem SMA ennexOS Portal. "
                "Unterstützt Jahresansicht (Monatswerte) und Monatsansicht (Tageswerte). "
                "Bei Tageswerten wird die Anzahl Ladetage als Ladevorgänge gezählt."
            ),
            erwartetes_format="CSV (Semikolon-getrennt, ennexOS Portal)",
            anleitung=(
                "1. ennexOS Portal öffnen (ennexos.sunnyportal.com)\n"
                "2. Zur Seite 'Energie und Leistung' navigieren\n"
                "3. Im Dropdown 'Ladestation' auswählen\n"
                "4. Jahresansicht wählen für Monatswerte\n"
                "5. 'Details' aufklappen → 'Download' klicken\n"
                "6. Die heruntergeladene CSV-Datei hier hochladen"
            ),
            beispiel_header='Zeitraum;Zählerstand Ladestation [kWh];Zählerstand Ladestation Zählerstand [kWh]',
        )

    def can_parse(self, content: str, filename: str) -> bool:
        """Erkennt ECharger-Format: ennexOS-Header + Ladestation-Spalten."""
        lines = content.split("\n", 20)
        if not lines:
            return False

        all_text = "\n".join(lines).lower()

        # Muss ennexOS-Metadaten haben
        has_ennexos = "id der anlage" in all_text or "name der anlage" in all_text

        # Muss Ladestation/Wallbox-Spalten haben
        has_wallbox = "ladestation" in all_text or "wallbox" in all_text

        # Darf KEINE PV-typischen Spalten haben (sonst ist es ein Energie-Export)
        pv_indicators = ["gesamterzeugung", "direktverbrauch", "netzeinspeisung", "eigenverbrauch"]
        has_pv = any(ind in all_text for ind in pv_indicators)

        return has_ennexos and has_wallbox and not has_pv

    def _find_header_row(self, rows: list[list[str]]) -> int:
        """Findet die Header-Zeile mit Ladestation-Spalten."""
        for i, row in enumerate(rows):
            if not row or len(row) < 2:
                continue
            row_text = " ".join(_normalize(cell) for cell in row)
            if "ladestation" in row_text or "ladung" in row_text or "wallbox" in row_text:
                # Prüfe dass auch "zeitraum" oder eine Datum-Spalte dabei ist
                if "zeitraum" in row_text or "datum" in row_text or "zeit" in row_text:
                    return i
        # Fallback: erste Zeile nach Metadaten mit mindestens 2 Spalten
        for i, row in enumerate(rows):
            if row and len(row) >= 2 and any(cell.strip() for cell in row):
                return i
        return 0

    def _find_ladung_column(self, headers: list[str]) -> Optional[int]:
        """Findet den Index der Lade-Energie-Spalte (Delta, nicht kumulativ)."""
        for idx, header in enumerate(headers):
            if _is_ladung_column(header):
                return idx
        return None

    def parse(self, content: str) -> list[ParsedMonthData]:
        """Parsed SMA ECharger CSV und gibt Monatswerte zurück."""
        # sep=; Zeile entfernen
        lines = content.split("\n")
        if lines and lines[0].strip().lower().startswith("sep="):
            content = "\n".join(lines[1:])

        reader = csv.reader(StringIO(content), delimiter=";")
        rows = list(reader)

        if len(rows) < 2:
            return []

        header_idx = self._find_header_row(rows)
        headers = [h.strip() for h in rows[header_idx]]

        ladung_col = self._find_ladung_column(headers)
        if ladung_col is None:
            return []

        # Daten sammeln
        monthly_kwh: dict[tuple[int, int], float] = defaultdict(float)
        monthly_ladetage: dict[tuple[int, int], int] = defaultdict(int)
        monthly_rows: dict[tuple[int, int], int] = defaultdict(int)
        is_daily = False

        for row in rows[header_idx + 1:]:
            if len(row) < 2 or ladung_col >= len(row):
                continue

            # Datum parsen (erste Spalte)
            parsed_date = _parse_date(row[0].strip())
            if not parsed_date:
                continue

            jahr, monat, tag = parsed_date
            if jahr < 2000 or jahr > 2100 or monat < 1 or monat > 12:
                continue

            key = (jahr, monat)
            val = _parse_float(row[ladung_col])
            if val is None:
                val = 0.0

            monthly_kwh[key] += val
            monthly_rows[key] += 1

            # Ladetage zählen (nur bei Tageswerten: tag > 0)
            if tag > 0:
                is_daily = True
                if val > 0:
                    monthly_ladetage[key] += 1

        # ParsedMonthData erstellen
        result: list[ParsedMonthData] = []
        for (jahr, monat) in sorted(monthly_kwh.keys()):
            kwh = round(monthly_kwh[(jahr, monat)], 2)
            if kwh <= 0:
                continue

            ladevorgaenge = monthly_ladetage.get((jahr, monat)) if is_daily else None

            result.append(ParsedMonthData(
                jahr=jahr,
                monat=monat,
                wallbox_ladung_kwh=kwh,
                wallbox_ladevorgaenge=ladevorgaenge,
            ))

        return result
