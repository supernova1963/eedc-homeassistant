"""
Sonnenstand-Helper für das Korrekturprofil (siehe KONZEPT-KORREKTURPROFIL.md).

Vereinfachter NOAA Solar Position Algorithm — Genauigkeit ~0.1° im Zeitraum
1950-2050, mehr als ausreichend für 10°×10° Sonnenstand-Bins. Keine externe
Astro-Dependency (kein pvlib/astropy).

Konvention:
- Azimut: 0° = Nord, 90° = Ost, 180° = Süd, 270° = West (Stunden)
- Elevation: 0° = Horizont, 90° = Zenit (negative Werte = unter Horizont, Nacht)

Bin-Definition:
- Azimut-Bin: 0..35 in 10°-Schritten ab Nord (Bin 11 = 110°-119°)
- Elevation-Bin: 0..8 in 10°-Schritten ab Horizont (Bin 3 = 30°-39°,
  negative Elevation → Bin -1 = Nacht, wird beim Lookup als unklassifizierbar
  übersprungen)
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


@dataclass(frozen=True)
class SolarPosition:
    azimut: float  # 0-360°, ab Nord nach Osten
    elevation: float  # -90..90°, über Horizont positiv


def solar_position(lat: float, lon: float, dt_utc: datetime) -> SolarPosition:
    """Sonnenstand für Beobachterposition (lat, lon) zu UTC-Zeitpunkt.

    `dt_utc` muss tz-aware mit timezone=UTC sein oder naive (wird dann als
    UTC interpretiert).
    """
    if dt_utc.tzinfo is None:
        dt_utc = dt_utc.replace(tzinfo=timezone.utc)
    else:
        dt_utc = dt_utc.astimezone(timezone.utc)

    # Julianisches Datum (NOAA: J2000.0-Referenz)
    epoch = datetime(2000, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    n = (dt_utc - epoch).total_seconds() / 86400.0  # Tage seit J2000.0

    # Mittlere Länge der Sonne (°)
    L = (280.460 + 0.9856474 * n) % 360.0
    # Mittlere Anomalie (°)
    g = math.radians((357.528 + 0.9856003 * n) % 360.0)
    # Ekliptische Länge (°)
    lambda_ = math.radians(L + 1.915 * math.sin(g) + 0.020 * math.sin(2 * g))
    # Schiefe der Ekliptik (°)
    epsilon = math.radians(23.439 - 0.0000004 * n)

    # Rektaszension und Deklination
    sin_dec = math.sin(epsilon) * math.sin(lambda_)
    dec = math.asin(sin_dec)
    ra = math.atan2(math.cos(epsilon) * math.sin(lambda_), math.cos(lambda_))

    # Greenwich Mean Sidereal Time (Stunden)
    gmst = (18.697374558 + 24.06570982441908 * n) % 24.0
    # Local Sidereal Time (Radiant)
    lst = math.radians((gmst * 15.0 + lon) % 360.0)
    # Stundenwinkel
    ha = lst - ra

    lat_rad = math.radians(lat)
    sin_alt = math.sin(lat_rad) * math.sin(dec) + math.cos(lat_rad) * math.cos(dec) * math.cos(ha)
    alt = math.asin(max(-1.0, min(1.0, sin_alt)))

    # Azimut: ab Nord, im Uhrzeigersinn
    sin_az = -math.cos(dec) * math.sin(ha)
    cos_az = math.sin(dec) * math.cos(lat_rad) - math.cos(dec) * math.sin(lat_rad) * math.cos(ha)
    az = math.degrees(math.atan2(sin_az, cos_az)) % 360.0

    return SolarPosition(azimut=az, elevation=math.degrees(alt))


# ── Bin-Helfer ─────────────────────────────────────────────────────────────

AZIMUT_BIN_BREITE_DEFAULT = 10
ELEVATION_BIN_BREITE_DEFAULT = 10


def azimut_bin(azimut: float, breite: int = AZIMUT_BIN_BREITE_DEFAULT) -> int:
    """Azimut → Bin-Index (0..35 bei Default-Breite 10°).

    `Azimut % 360` zuerst, damit auch z. B. 365° korrekt landet.
    """
    return int((azimut % 360.0) // breite)


def elevation_bin(elevation: float, breite: int = ELEVATION_BIN_BREITE_DEFAULT) -> int:
    """Elevation → Bin-Index. Negative Werte (Nacht) ergeben -1."""
    if elevation < 0:
        return -1
    return int(elevation // breite)


def bin_key(
    azimut: float,
    elevation: float,
    azimut_breite: int = AZIMUT_BIN_BREITE_DEFAULT,
    elevation_breite: int = ELEVATION_BIN_BREITE_DEFAULT,
) -> Optional[str]:
    """Schlüssel für Korrekturprofil-Faktoren-Dict, z. B. "110_30".

    Liefert `None` bei Nacht (Elevation < 0) — der Caller skippt den Slot.
    Erste Zahl = Azimut-Bin-*Untergrenze* (110 = 110-119°), zweite Zahl =
    Elevation-Bin-Untergrenze.
    """
    eb = elevation_bin(elevation, elevation_breite)
    if eb < 0:
        return None
    ab = azimut_bin(azimut, azimut_breite)
    return f"{ab * azimut_breite}_{eb * elevation_breite}"


# ── Lokalzeit-Konvertierung ────────────────────────────────────────────────


def infer_timezone(lon: float) -> ZoneInfo:
    """Anlagen-Zeitzone aus Längengrad ableiten.

    DACH und Nachbarn (lon ~ -15..30) → Europe/Berlin (CET/CEST).
    Außerhalb: lon/15° als fester UTC-Offset über `Etc/GMT±N`.
    Reicht für unsere Bin-Auflösung (10°) — präzisere Inferenz erst, wenn
    Anlagen außerhalb der CET-Zone aktiv werden.
    """
    if -15.0 <= lon <= 30.0:
        return ZoneInfo("Europe/Berlin")
    offset = round(lon / 15.0)
    if offset == 0:
        return ZoneInfo("UTC")
    # Etc/GMT-Konvention ist invertiert: Etc/GMT-3 entspricht UTC+3
    try:
        return ZoneInfo(f"Etc/GMT{-offset:+d}")
    except ZoneInfoNotFoundError:
        return ZoneInfo("UTC")


def lokal_stunde_zu_utc(
    datum: date,
    stunde: int,
    lat: float,
    lon: float,
    slot_mitte: bool = True,
) -> datetime:
    """`(datum, stunde)` aus TagesEnergieProfil → UTC-Zeitpunkt für Sonnenstand.

    `stunde` steht für das Backward-Slot-Intervall `[stunde-1, stunde)` lokal
    (Konvention TagesEnergieProfil + pv_prognose_stundenprofil). Für die
    Sonnenstand-Bewertung nehmen wir die Mitte des Slots — das ist robuster
    gegen Slot-Grenzen-Sprünge im Bin.
    """
    tz = infer_timezone(lon)
    # Slot-Mitte: 30 Minuten vor `stunde` (also `stunde-0.5`).
    # `stunde=0` ergäbe negative Slot-Mitte am Vortag → korrekt durch timedelta.
    base = datetime.combine(datum, datetime.min.time(), tzinfo=tz)
    delta_minutes = stunde * 60 - (30 if slot_mitte else 0)
    local = base + timedelta(minutes=delta_minutes)
    return local.astimezone(timezone.utc)


def solar_position_lokal(
    lat: float,
    lon: float,
    datum: date,
    stunde: int,
) -> SolarPosition:
    """Convenience: Sonnenstand für `(datum, stunde)` aus TagesEnergieProfil.

    Slot-Mitte-Konvention (siehe `lokal_stunde_zu_utc`).
    """
    return solar_position(lat, lon, lokal_stunde_zu_utc(datum, stunde, lat, lon))
