"""
Tages-Ertragsformel für PV-Prognosen.

Enthält nur noch ``berechne_pv_ertrag_tag`` — die Formel, die die Aussichten-
und Prognosen-Endpoints je Vorhersagetag anwenden.

Die früher hier liegenden ``get_kurzfrist_prognose`` / ``get_langfrist_prognose``
/ ``get_trend_analyse`` waren toter Code und wurden entfernt (A24-2/N-A): die
gleichnamigen **lebenden** Endpoints liegen in ``api/routes/aussichten.py``.
"""

import logging
from typing import Optional

from backend.services.pv_orientation import DEFAULT_SYSTEM_LOSSES

logger = logging.getLogger(__name__)

# Konstanten für PV-Berechnung (DEFAULT_SYSTEM_LOSSES: zentral in pv_orientation.py)
TEMP_COEFFICIENT = 0.004  # Leistungsabnahme pro °C über 25°C


def berechne_pv_ertrag_tag(
    globalstrahlung_kwh_m2: float,
    anlagenleistung_kwp: float,
    temperatur_max_c: Optional[float] = None,
    system_losses: float = DEFAULT_SYSTEM_LOSSES,
) -> float:
    """
    Berechnet den erwarteten PV-Ertrag für einen Tag.

    Formel:
    PV_kwh = Globalstrahlung × kWp × (1 - Systemverluste) × Temperaturkorrektur

    HINWEIS Temperaturkorrektur: Nutzt Lufttemperatur direkt (kein Modul-Aufheizungsmodell).
    solar_forecast_service nutzt stündliche GTI-basierte Modultemperatur-Schätzung
    (Modultemp = Lufttemp + min(25, GTI/40)), die genauer ist, aber stündliche Daten
    erfordert, die für Tages-Aggregat-Prognosen hier nicht verfügbar sind.

    Args:
        globalstrahlung_kwh_m2: Globalstrahlung in kWh/m²
        anlagenleistung_kwp: Anlagenleistung in kWp
        temperatur_max_c: Maximaltemperatur in °C (für Temperaturkorrektur)
        system_losses: Systemverluste (0.14 = 14%)

    Returns:
        Erwarteter Ertrag in kWh
    """
    if globalstrahlung_kwh_m2 is None or globalstrahlung_kwh_m2 <= 0:
        return 0.0

    # Basisberechnung
    ertrag = globalstrahlung_kwh_m2 * anlagenleistung_kwp * (1 - system_losses)

    # Temperaturkorrektur (Module werden bei Hitze ineffizienter)
    if temperatur_max_c is not None and temperatur_max_c > 25:
        temp_verlust = (temperatur_max_c - 25) * TEMP_COEFFICIENT
        ertrag *= (1 - temp_verlust)

    return round(max(0, ertrag), 2)
