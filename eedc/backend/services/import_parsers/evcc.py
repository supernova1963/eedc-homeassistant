"""
EVCC (Electric Vehicle Charge Controller) CSV Parser.

Unterstützt den CSV-Export der Ladevorgänge aus EVCC.

Format:
- Semikolon-getrennt, UTF-8 mit BOM
- Eine Zeile pro Ladevorgang (Session)
- Spalten: Startzeit, Endzeit, Ladepunkt, Fahrzeug, Energie, Sonne %, Kilometerstand etc.
- Wird pro Monat aggregiert: Summe Energie, Anzahl Ladevorgänge, PV-Anteil

Besonderheiten:
- Sonne (%) ermöglicht Berechnung von ladung_pv_kwh
- Kilometerstand ermöglicht Ableitung von km_gefahren
"""

import csv
from collections import defaultdict
from io import StringIO
from typing import Optional

from .base import PortalExportParser, ParsedMonthData, ParserInfo
from .registry import register_parser
from .sma_sunny_portal import _normalize, _parse_float


def _parse_evcc_datetime(val: str) -> Optional[tuple[int, int]]:
    """Parsed EVCC Datetime und gibt (jahr, monat) zurück.

    Format: "2026-02-25 14:37:56"
    """
    val = val.strip()
    if len(val) < 10:
        return None
    try:
        jahr = int(val[:4])
        monat = int(val[5:7])
        if 2000 <= jahr <= 2100 and 1 <= monat <= 12:
            return jahr, monat
    except (ValueError, IndexError):
        pass
    return None


@register_parser
class EVCCParser(PortalExportParser):
    """Parser für EVCC Ladevorgangs-CSV-Exporte."""

    def info(self) -> ParserInfo:
        return ParserInfo(
            id="evcc",
            name="EVCC Ladevorgänge",
            hersteller="EVCC",
            beschreibung=(
                "Importiert CSV-Exporte der Ladevorgänge aus EVCC "
                "(Electric Vehicle Charge Controller). Einzelne Sessions werden "
                "pro Monat aggregiert: Gesamtenergie, Anzahl Ladevorgänge und PV-Anteil."
            ),
            erwartetes_format="CSV (Semikolon-getrennt, UTF-8)",
            anleitung=(
                "1. EVCC Web-UI öffnen (z.B. http://evcc.local:7070)\n"
                "2. Menü → 'Ladevorgänge' öffnen\n"
                "3. Gewünschten Zeitraum auswählen\n"
                "4. CSV-Download Button klicken\n"
                "5. Die heruntergeladene CSV-Datei hier hochladen"
            ),
            beispiel_header="Startzeit;Endzeit;Ladepunkt;Kennung;Fahrzeug;Kilometerstand (km);...;Energie (kWh);...;Sonne (%)",
        )

    def can_parse(self, content: str, filename: str) -> bool:
        """Erkennt EVCC-Format anhand typischer Spaltenbezeichnungen."""
        lines = content.split("\n", 5)
        if not lines:
            return False

        # Prüfe erste Zeile (Header) auf EVCC-typische Spalten
        header_line = lines[0].lower()
        if ";" not in header_line:
            return False

        evcc_indicators = ["startzeit", "ladepunkt", "energie", "sonne"]
        matches = sum(1 for ind in evcc_indicators if ind in header_line)
        return matches >= 3

    def parse(self, content: str) -> list[ParsedMonthData]:
        """Parsed EVCC CSV und aggregiert Sessions pro Monat."""
        reader = csv.reader(StringIO(content), delimiter=";")
        rows = list(reader)

        if len(rows) < 2:
            return []

        headers = [h.strip() for h in rows[0]]
        normalized_headers = [_normalize(h) for h in headers]

        # Spalten-Indizes finden
        col_startzeit = self._find_col(normalized_headers, ["startzeit", "start"])
        col_energie = self._find_col(normalized_headers, ["energie"])
        col_sonne = self._find_col(normalized_headers, ["sonne"])
        col_solarenergie = self._find_col(normalized_headers, ["solarenergie"])
        col_km = self._find_col(normalized_headers, ["kilometerstand"])

        if col_startzeit is None or col_energie is None:
            return []

        # Sessions pro Monat aggregieren
        monthly_energie: dict[tuple[int, int], float] = defaultdict(float)
        monthly_pv_kwh: dict[tuple[int, int], float] = defaultdict(float)
        monthly_sessions: dict[tuple[int, int], int] = defaultdict(int)
        monthly_km_min: dict[tuple[int, int], float] = {}
        monthly_km_max: dict[tuple[int, int], float] = {}

        for row in rows[1:]:
            if len(row) < max(col_startzeit + 1, col_energie + 1):
                continue

            # Datum parsen
            parsed = _parse_evcc_datetime(row[col_startzeit])
            if not parsed:
                continue
            key = parsed  # (jahr, monat)

            # Energie
            energie = _parse_float(row[col_energie])
            if energie is None or energie <= 0:
                continue

            monthly_energie[key] += energie
            monthly_sessions[key] += 1

            # PV-Anteil: Solarenergie (kWh) bevorzugen, Fallback auf Sonne (%)
            if col_solarenergie is not None and col_solarenergie < len(row):
                solar_kwh = _parse_float(row[col_solarenergie])
                if solar_kwh is not None:
                    monthly_pv_kwh[key] += solar_kwh
            elif col_sonne is not None and col_sonne < len(row):
                sonne_pct = _parse_float(row[col_sonne])
                if sonne_pct is not None:
                    monthly_pv_kwh[key] += energie * sonne_pct / 100.0

            # Kilometerstand tracken
            if col_km is not None and col_km < len(row):
                km = _parse_float(row[col_km])
                if km is not None and km > 0:
                    if key not in monthly_km_min or km < monthly_km_min[key]:
                        monthly_km_min[key] = km
                    if key not in monthly_km_max or km > monthly_km_max[key]:
                        monthly_km_max[key] = km

        # ParsedMonthData erstellen
        result: list[ParsedMonthData] = []
        for (jahr, monat) in sorted(monthly_energie.keys()):
            kwh = round(monthly_energie[(jahr, monat)], 2)
            if kwh <= 0:
                continue

            pv_kwh = round(monthly_pv_kwh.get((jahr, monat), 0), 2) or None

            # km gefahren = Differenz max - min Kilometerstand im Monat
            km = None
            if (jahr, monat) in monthly_km_max and (jahr, monat) in monthly_km_min:
                delta = round(monthly_km_max[(jahr, monat)] - monthly_km_min[(jahr, monat)], 1)
                if delta > 0:
                    km = delta

            result.append(ParsedMonthData(
                jahr=jahr,
                monat=monat,
                wallbox_ladung_kwh=kwh,
                wallbox_ladung_pv_kwh=pv_kwh,
                wallbox_ladevorgaenge=monthly_sessions[(jahr, monat)],
                eauto_km_gefahren=km,
            ))

        return result

    def _find_col(self, normalized_headers: list[str], patterns: list[str]) -> Optional[int]:
        """Findet den Index einer Spalte anhand von Suchbegriffen."""
        for idx, header in enumerate(normalized_headers):
            for pattern in patterns:
                if pattern in header:
                    return idx
        return None
