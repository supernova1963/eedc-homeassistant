"""
Wetter-Utilities: Einheiten-Konvertierung und WMO-Symbol-Mapping.
"""

from typing import Literal, Optional

# Konvertierungsfaktoren
MJ_TO_KWH = 1 / 3.6  # 1 MJ = 0.2778 kWh
SECONDS_TO_HOURS = 1 / 3600

# Wetterklassen für Korrekturprofil-Stratifizierung (siehe KONZEPT-KORREKTURPROFIL.md)
Wetterklasse = Literal["klar", "diffus", "wechselhaft"]
WETTERKLASSEN: tuple[Wetterklasse, ...] = ("klar", "diffus", "wechselhaft")


def wetter_code_zu_symbol(code: Optional[int]) -> str:
    """
    Konvertiert WMO Weather Code zu einfachem Symbol-String.

    WMO Weather Codes: https://open-meteo.com/en/docs
    """
    if code is None:
        return "unknown"

    if code == 0:
        return "sunny"
    elif code == 1:
        return "mostly_sunny"
    elif code == 2:
        return "partly_cloudy"
    elif code == 3:
        return "cloudy"
    elif code in (45, 48):
        return "foggy"
    elif code in (51, 53, 55, 56, 57):
        return "drizzle"
    elif code in (61, 63, 65, 66, 67):
        return "rainy"
    elif code in (71, 73, 75, 77):
        return "snowy"
    elif code in (80, 81, 82):
        return "showers"
    elif code in (85, 86):
        return "snow_showers"
    elif code in (95, 96, 99):
        return "thunderstorm"
    else:
        return "cloudy"


def wetter_symbol_aus_tag(
    wetter_code: Optional[int],
    bewoelkung_prozent: Optional[float],
    niederschlag_mm: Optional[float],
    *,
    niederschlag_threshold_mm: float = 0.5,
) -> str:
    """
    SoT-Helper: WMO-Code → Symbol mit Plausibilisierung.

    Open-Meteo's Daily-WMO-Code biased Richtung „schlechtester Moment des Tages":
    Ein Tag mit 14 h Sonne und kurzem Schauer wird oft als „bedeckt" (3) kodiert,
    obwohl die mittlere Bewölkung deutlich darunter liegt. Diese Funktion korrigiert
    das anhand `bewoelkung_prozent`. Bei nennenswertem Niederschlag bleibt das
    Code-basierte Symbol erhalten (drizzle/rainy/snowy/showers/thunderstorm).

    Args:
        wetter_code: WMO Weather Code (None → 'unknown'-Fallback)
        bewoelkung_prozent: Mittlere Bewölkung [0–100]; None → keine Plausibilisierung
        niederschlag_mm: Niederschlag in mm; > Threshold schützt das Code-Symbol
        niederschlag_threshold_mm: Schwelle für Niederschlags-Schutz.
            0.5 für Tagessummen (default), 0.05 für Stundenwerte.
    """
    symbol = wetter_code_zu_symbol(wetter_code)

    if niederschlag_mm is not None and niederschlag_mm > niederschlag_threshold_mm:
        return symbol
    if bewoelkung_prozent is None:
        return symbol
    if bewoelkung_prozent < 20:
        return "sunny"
    if bewoelkung_prozent < 40:
        return "mostly_sunny"
    if bewoelkung_prozent < 70:
        return "partly_cloudy"
    return "cloudy"


# ── Wetter-Klassifikation für Korrekturprofil ────────────────────────────────

# Niederschlags-Marker (mm/h) ab denen eine Stunde unabhängig von Bewölkung
# als „wechselhaft" gilt — Regen/Schnee/Schauer unterbrechen den klaren oder
# diffusen Zustand systematisch.
_NIEDERSCHLAG_MARKER_MM_H = 0.2

# WMO-Codes mit Niederschlag oder Sicht-beeinträchtigender Bedingung — diese
# Stunden sind per Definition wechselhaft, unabhängig von cloud_cover.
_WMO_WECHSELHAFT = frozenset(
    {45, 48}  # Nebel
    | {51, 53, 55, 56, 57}  # Sprühregen
    | {61, 63, 65, 66, 67}  # Regen
    | {71, 73, 75, 77}  # Schnee
    | {80, 81, 82}  # Schauer
    | {85, 86}  # Schneeschauer
    | {95, 96, 99}  # Gewitter
)


def klassifiziere_stunde(
    bewoelkung_prozent: Optional[float],
    niederschlag_mm: Optional[float] = None,
    wetter_code: Optional[int] = None,
) -> Optional[Wetterklasse]:
    """
    Klassifiziert eine Stunde in `klar` / `diffus` / `wechselhaft`.

    Schwellen wurden gewählt, damit die drei Klassen je grob ein Drittel der
    Stunden auf einer typischen mitteleuropäischen Anlage abdecken:

    - **klar:** Bewölkung < 30 %, kein nennenswerter Niederschlag, keine
      WMO-Sicht-Beeinträchtigung.
    - **diffus:** Bewölkung > 70 %, kein/kaum Niederschlag — gleichmäßig
      bedeckt, GHI fast komplett aus diffuser Strahlung.
    - **wechselhaft:** dazwischen ODER Niederschlag/Schauer/Gewitter — der
      Tagesgang der Bewölkung schwankt stark, GHI-Vorhersage unsicher.

    Returns None nur bei komplett fehlenden Eingaben (alle drei None).
    """
    if (
        bewoelkung_prozent is None
        and niederschlag_mm is None
        and wetter_code is None
    ):
        return None

    # Niederschlag oder kritischer WMO-Code → wechselhaft
    if niederschlag_mm is not None and niederschlag_mm >= _NIEDERSCHLAG_MARKER_MM_H:
        return "wechselhaft"
    if wetter_code is not None and int(wetter_code) in _WMO_WECHSELHAFT:
        return "wechselhaft"

    # Ohne Bewölkungs-Wert können wir nur über WMO klassifizieren
    if bewoelkung_prozent is None:
        if wetter_code is None:
            return None
        # WMO 0-3 = klar bis bewölkt, ohne Bewölkungs-% nicht trennbar
        return "wechselhaft"

    if bewoelkung_prozent < 30:
        return "klar"
    if bewoelkung_prozent > 70:
        return "diffus"
    return "wechselhaft"
