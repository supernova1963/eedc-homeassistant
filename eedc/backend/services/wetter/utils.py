"""
Wetter-Utilities: Einheiten-Konvertierung und WMO-Symbol-Mapping.
"""

from typing import Optional

# Konvertierungsfaktoren
MJ_TO_KWH = 1 / 3.6  # 1 MJ = 0.2778 kWh
SECONDS_TO_HOURS = 1 / 3600


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
