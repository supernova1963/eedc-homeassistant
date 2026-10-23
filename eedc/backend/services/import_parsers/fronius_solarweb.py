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

from .base import PortalExportParser, ParsedMonthData, ParserInfo, monat_hat_wert_ueber_null, monatswert
from .registry import register_parser
from .sma_sunny_portal import _normalize, _parse_float


# Spalten-Mapping: normalisierter Name → (internes Feld, Priorität)
# Höhere Priorität gewinnt bei mehreren Treffern
COLUMN_PATTERNS: dict[str, list[str]] = {
    "pv_erzeugung": [
        "pv production", "pv-erzeugung", "gesamtenergie", "energy",
        "erzeugung", "produced",
        # Hinweis: "Energie | [InverterModel]" (Custom Report) wird in parse()
        # per Raw-Header-Suche behandelt, da _normalize() "|" entfernt.
        # "ertrag" absichtlich NICHT hier: würde "Spezifischer Ertrag" treffen!
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
            beispiel_header="Date and time;PV production [Wh];Energy to grid [Wh];Energy from grid [Wh];Consumed directly [Wh] — oder Benutzerdefinierter Report: Datum und Uhrzeit;Energie | [Gerätemodell] [Wh];...",
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
        # RF-36 (Komplexitäts-Paket, 23.10.2026): Einheitenzeile, Spalten-Zuordnung (Felder, WR-Spalten, Wattpilot),
        # Monatssummen und Monatsdaten sind Phasen dieser Datei; die drei wortgleichen Zell-Blöcke sind `_zelle_kwh`.
        delimiter = _detect_delimiter(content)
        reader = csv.reader(StringIO(content), delimiter=delimiter)
        rows = list(reader)

        if len(rows) < 2:
            return []

        headers = [h.strip() for h in rows[0]]
        normalized = [_normalize(h) for h in headers]

        units, data_start = _einheitenzeile(rows, headers)

        col_map, used_indices = self._feld_spalten(normalized)

        # Datum-Spalte: erste Spalte ist typischerweise das Datum
        col_date = 0

        pv_col_indices = _wr_spalten(headers, col_map, used_indices)
        wattpilot_netz_idx, wattpilot_bat_idx, wattpilot_pv_idx = _wattpilot_spalten(headers, used_indices)

        # Prüfen ob wir genug Spalten haben
        if (col_map.get("pv_erzeugung") is None and not pv_col_indices
                and col_map.get("einspeisung") is None):
            return []

        monthly = _monatssummen(
            rows, data_start, col_date=col_date, col_map=col_map, pv_col_indices=pv_col_indices,
            wattpilot_netz_idx=wattpilot_netz_idx, wattpilot_bat_idx=wattpilot_bat_idx,
            wattpilot_pv_idx=wattpilot_pv_idx, headers=headers, units=units,
        )
        return _monatsdaten(monthly)

    def _feld_spalten(self, normalized: list[str]) -> tuple[dict[str, Optional[int]], set[int]]:
        """RF-36: die Spalten der Felder aus ``COLUMN_PATTERNS`` (ein Index je Feld, keiner doppelt) und die belegten
        Indizes."""
        # Spalten-Indizes finden (bereits belegte Indizes nicht doppelt vergeben)
        col_map: dict[str, Optional[int]] = {}
        used_indices: set[int] = set()
        for field, patterns in COLUMN_PATTERNS.items():
            idx = self._find_col(normalized, patterns, used_indices)
            col_map[field] = idx
            if idx is not None:
                used_indices.add(idx)
        return col_map, used_indices

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


def _einheitenzeile(rows: list[list[str]], headers: list[str]) -> tuple[list[str], int]:
    """RF-36: die Einheiten je Spalte aus der zweiten Zeile, wenn sie keine Datenzeile ist, und die erste Datenzeile."""
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
    return units, data_start


def _wr_spalten(headers: list[str], col_map: dict[str, Optional[int]], used_indices: set[int]) -> list[int]:
    """RF-36: die WR-Spalten des Custom Reports (``Energie | …``), nur ohne PV-Feld-Spalte; belegt sie in
    ``used_indices`` (in place)."""
    # Fronius Custom Report: PV-Spalten heißen "Energie | [InverterModel]"
    # _normalize() entfernt "|" → normalisierte Suche schlägt fehl → Raw-Header-Suche
    # Mehrere Wechselrichter (z.B. "Energie | Symo 4.5-3-M" + "Energie | GEN24")
    # werden alle gefunden und summiert. MPP-Spalten ("Energie MPP1 | ...") und
    # Wattpilot-Spalten ("Energie Wattpilot | ...") werden korrekt ausgeschlossen,
    # da sie nicht exakt mit "energie |" beginnen.
    pv_col_indices: list[int] = []
    if col_map.get("pv_erzeugung") is None:
        for idx, raw_h in enumerate(headers):
            if idx in used_indices:
                continue
            if raw_h.lower().startswith("energie |"):
                pv_col_indices.append(idx)
                used_indices.add(idx)
    return pv_col_indices


def _wattpilot_spalten(headers: list[str], used_indices: set[int]) -> tuple[Optional[int], Optional[int], Optional[int]]:
    """RF-36: die Wattpilot-Spalten (Netz, Batterie, PV) über den Roh-Header; belegt sie in ``used_indices`` (in place)."""
    # Wattpilot-Spalten: "Energie vom Netz an Wattpilot", "... von Batterie ...", "... von PV ..."
    # Separate Suche per Raw-Header um Konflikte mit netzbezug/batterie-Patterns zu vermeiden.
    wattpilot_netz_idx: Optional[int] = None
    wattpilot_bat_idx: Optional[int] = None
    wattpilot_pv_idx: Optional[int] = None
    for idx, raw_h in enumerate(headers):
        if idx in used_indices:
            continue
        h = raw_h.lower()
        if "wattpilot" in h:
            if "netz" in h:
                wattpilot_netz_idx = idx
                used_indices.add(idx)
            elif "batterie" in h:
                wattpilot_bat_idx = idx
                used_indices.add(idx)
            elif "pv" in h:
                wattpilot_pv_idx = idx
                used_indices.add(idx)
    return wattpilot_netz_idx, wattpilot_bat_idx, wattpilot_pv_idx


def _zelle_kwh(row: list[str], col_idx: int, headers: list[str], units: list[str]) -> Optional[float]:
    """RF-36: der Wert einer Zelle in kWh (Einheit aus der Einheitenzeile, sonst über den Header) — ``None`` ohne Zahl
    oder negativ. Die eine Regel der Feld-, WR- und Wattpilot-Spalten in ``parse``."""
    val = _parse_float(row[col_idx])
    unit = units[col_idx] if col_idx < len(units) else ""
    val = _wh_to_kwh(val, headers[col_idx], unit)
    if val is not None and val >= 0:
        return val
    return None


def _monatssummen(
    rows: list[list[str]], data_start: int, *, col_date: int, col_map: dict[str, Optional[int]],
    pv_col_indices: list[int], wattpilot_netz_idx: Optional[int], wattpilot_bat_idx: Optional[int],
    wattpilot_pv_idx: Optional[int], headers: list[str], units: list[str],
) -> dict[tuple[int, int], dict[str, float]]:
    """RF-36: die Summen je (Jahr, Monat) und Feld über die Datenzeilen (Feld-, WR- und Wattpilot-Spalten)."""
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
                val = _zelle_kwh(row, col_idx, headers, units)
                if val is not None:
                    monthly[key][field] += val

        # Fronius Custom Report: alle WR-Spalten ("Energie | WR1", "Energie | WR2", ...)
        # werden zu pv_erzeugung summiert
        for col_idx in pv_col_indices:
            if col_idx < len(row):
                val = _zelle_kwh(row, col_idx, headers, units)
                if val is not None:
                    monthly[key]["pv_erzeugung"] += val

        # Wattpilot-Ladung: Netz + Batterie + PV = Gesamt
        for wp_field, wp_idx in (
            ("wattpilot_netz", wattpilot_netz_idx),
            ("wattpilot_bat", wattpilot_bat_idx),
            ("wattpilot_pv", wattpilot_pv_idx),
        ):
            if wp_idx is not None and wp_idx < len(row):
                val = _zelle_kwh(row, wp_idx, headers, units)
                if val is not None:
                    monthly[key][wp_field] += val
    return monthly


def _monatsdaten(monthly: dict[tuple[int, int], dict[str, float]]) -> list[ParsedMonthData]:
    """RF-36: je Monat mit einem Wert über 0 ein ``ParsedMonthData`` (Eigenverbrauch direkt oder abgeleitet)."""
    # ParsedMonthData erstellen
    result: list[ParsedMonthData] = []
    for (jahr, monat) in sorted(monthly.keys()):
        data = monthly[(jahr, monat)]
        if not monat_hat_wert_ueber_null(data):
            continue

        # N-714: eine 0 in der Datei ist ein Wert, nur ein Feld ohne Zelle mit Zahl bleibt leer.
        # Eigenverbrauch: direkt (auch 0) oder — ohne Zelle — berechnet (Erzeugung - Einspeisung)
        eigenverbrauch = monatswert(data, "eigenverbrauch")
        if eigenverbrauch is None and "pv_erzeugung" in data and "einspeisung" in data:
            differenz = data["pv_erzeugung"] - data["einspeisung"]
            eigenverbrauch = round(differenz, 2) if differenz >= 0 else None

        result.append(ParsedMonthData(
            jahr=jahr,
            monat=monat,
            pv_erzeugung_kwh=monatswert(data, "pv_erzeugung"),
            einspeisung_kwh=monatswert(data, "einspeisung"),
            netzbezug_kwh=monatswert(data, "netzbezug"),
            eigenverbrauch_kwh=eigenverbrauch,
            batterie_ladung_kwh=monatswert(data, "batterie_ladung"),
            batterie_entladung_kwh=monatswert(data, "batterie_entladung"),
            # Wattpilot: Gesamt = Netz + Batterie + PV
            wallbox_ladung_kwh=monatswert(data, "wattpilot_netz", "wattpilot_bat", "wattpilot_pv"),
            wallbox_ladung_pv_kwh=monatswert(data, "wattpilot_pv"),
        ))

    return result
