"""
EVCC (Electric Vehicle Charge Controller) CSV Parser.

Unterstützt den CSV-Export der Ladevorgänge aus EVCC.

Format:
- Komma- oder Semikolon-getrennt, UTF-8 mit BOM
- Eine Zeile pro Ladevorgang (Session)
- Spalten (DE): Startzeit, Endzeit, Ladepunkt, Fahrzeug, Energie, Sonne %, Kilometerstand etc.
- Spalten (EN): Created, Finished, Charging point, Vehicle, Energy, Solar %, Mileage etc.
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


def _detect_delimiter(header_line: str) -> str:
    """Wählt Delimiter anhand der ersten Zeile: häufigeres Zeichen gewinnt, Default ','."""
    if header_line.count(";") > header_line.count(","):
        return ";"
    return ","


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
            erwartetes_format="CSV (Komma- oder Semikolon-getrennt, UTF-8)",
            anleitung=(
                "1. EVCC Web-UI öffnen (z.B. http://evcc.local:7070)\n"
                "2. Menü → 'Ladevorgänge' / 'Sessions' öffnen\n"
                "3. Gewünschten Zeitraum auswählen\n"
                "4. CSV-Download Button klicken\n"
                "5. Die heruntergeladene CSV-Datei hier hochladen"
            ),
            beispiel_header="Created,Finished,Charging point,Vehicle,Mileage (km),Energy (kWh),Solar (%) — oder DE-Variante mit Startzeit;Energie;Sonne",
        )

    def can_parse(self, content: str, filename: str) -> bool:
        """Erkennt EVCC-Format anhand typischer Spaltenbezeichnungen (DE + EN).

        Andere EVCC-UI-Sprachen werden hier bewusst NICHT erkannt — bei manueller
        EVCC-Auswahl liefert parse() dann eine klare Sprach-Hinweis-Fehlermeldung
        statt False Positives gegen andere Wallbox-Exporte zu riskieren.
        """
        lines = content.split("\n", 5)
        if not lines:
            return False

        header_line = lines[0].lower()
        if "," not in header_line and ";" not in header_line:
            return False

        evcc_indicators = [
            # DE
            "startzeit", "ladepunkt", "energie", "sonne", "kilometerstand", "fahrzeug",
            # EN
            "created", "finished", "charging point", "energy", "solar", "mileage", "vehicle",
        ]
        matches = sum(1 for ind in evcc_indicators if ind in header_line)
        return matches >= 3

    def parse(self, content: str) -> list[ParsedMonthData]:
        """Parsed EVCC CSV und aggregiert Sessions pro Monat."""
        first_line = content.split("\n", 1)[0]
        delimiter = _detect_delimiter(first_line)
        reader = csv.reader(StringIO(content), delimiter=delimiter)
        rows = list(reader)

        if len(rows) < 2:
            return []

        headers = [h.strip() for h in rows[0]]
        normalized_headers = [_normalize(h) for h in headers]

        # Spalten-Indizes finden (DE + EN). Reihenfolge der Patterns ist egal —
        # _find_col scannt spaltenweise und gibt den ersten Treffer zurück.
        # Wichtig: "start" allein würde "meter start" matchen → bewusst weggelassen.
        col_startzeit = self._find_col(
            normalized_headers, ["startzeit", "created", "start time", "begin"]
        )
        col_energie = self._find_col(normalized_headers, ["energie", "energy"])
        col_sonne = self._find_col(normalized_headers, ["sonne", "solar", "sun"])
        col_solarenergie = self._find_col(
            normalized_headers, ["solarenergie", "solar energy"]
        )
        col_km = self._find_col(normalized_headers, ["kilometerstand", "mileage"])

        if col_startzeit is None or col_energie is None:
            # Header in einer anderen Sprache als DE/EN — EVCC lokalisiert die
            # Spaltennamen anhand der UI-Sprache. Klare Anweisung statt
            # generischem "keine Monatsdaten gefunden".
            raise ValueError(
                "EVCC-Spalten konnten nicht erkannt werden. Der Parser unterstützt "
                "bisher nur deutsche und englische EVCC-Exporte. Bitte in EVCC "
                "die UI-Sprache auf Deutsch oder Englisch umstellen "
                "(Einstellungen → Sprache) und die CSV-Datei erneut exportieren. "
                f"Erkannte Spalten: {', '.join(headers[:8])}…"
            )

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
