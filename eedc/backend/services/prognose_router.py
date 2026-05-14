"""
Prognose-Router: Resolver für die aktive PV-Prognosequelle pro Anlage.

Zentrale Stelle, über die alle prognose-konsumierenden Endpoints die
effektive Quelle und ggf. deren Daten abfragen. Keine Endpoint-Logik
darf mehr direkt prognose_quelle lesen und eigene Switch-Logik bauen.

Quellen:
  - eedc:    OpenMeteo × Lernfaktor (Default, überall verfügbar)
  - solcast: Solcast pur, ohne Korrektur (HA-Sensor oder API-Token)
  - sfml:    Solar Forecast ML pur, ohne Korrektur (nur HA-Add-on)

Bei Nicht-Verfügbarkeit der gewählten Quelle: automatischer Fallback
auf eedc, mit Hinweis-Text für die Response.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional

from backend.core.config import HA_INTEGRATION_AVAILABLE

logger = logging.getLogger(__name__)


@dataclass
class PrognoseQuelleResult:
    """Ergebnis der Quellen-Auflösung."""

    # Effektive Quelle (kann von der gewählten abweichen bei Fallback)
    quelle: str  # "eedc" | "solcast" | "sfml"

    # Ob die gewünschte Quelle verfügbar war oder Fallback griff
    ist_fallback: bool = False

    # Hinweis-Text für UI (nur bei Fallback, neutral formuliert)
    hinweis: Optional[str] = None

    # Die gewünschte Quelle (vor Fallback-Logik)
    gewuenscht: Optional[str] = None

    @property
    def braucht_lernfaktor(self) -> bool:
        """Nur EEDC nutzt den Lernfaktor/Korrekturfaktor."""
        return self.quelle == "eedc"

    @property
    def ist_eedc(self) -> bool:
        return self.quelle == "eedc"

    @property
    def ist_solcast(self) -> bool:
        return self.quelle == "solcast"

    @property
    def ist_sfml(self) -> bool:
        return self.quelle == "sfml"


def resolve_prognose_quelle(anlage) -> PrognoseQuelleResult:
    """
    Löst die Prognosequelle für eine Anlage auf.

    Liest anlage.prognose_quelle, prüft Verfügbarkeit und liefert
    bei Bedarf einen Fallback auf eedc mit Hinweis.

    Synchron — keine DB-Abfrage nötig. Verfügbarkeit wird anhand
    der Umgebung (HA_INTEGRATION_AVAILABLE) und Anlage-Konfiguration
    geprüft. Die tatsächlichen Sensor-Werte werden asynchron über
    discover_prognose_sensoren() geladen (siehe prognose_discovery.py).
    """
    gewuenscht = getattr(anlage, "prognose_quelle", None) or "eedc"

    # eedc ist immer verfügbar
    if gewuenscht == "eedc":
        return PrognoseQuelleResult(quelle="eedc", gewuenscht="eedc")

    # SFML braucht HA-Integration
    if gewuenscht == "sfml":
        if not HA_INTEGRATION_AVAILABLE:
            logger.info(
                "Anlage %s: SFML gewählt, aber kein HA — Fallback auf eedc",
                getattr(anlage, "id", "?"),
            )
            return PrognoseQuelleResult(
                quelle="eedc",
                ist_fallback=True,
                hinweis="SFML ist nur im HA-Add-on verfügbar. eedc-Prognose aktiv.",
                gewuenscht="sfml",
            )
        return PrognoseQuelleResult(quelle="sfml", gewuenscht="sfml")

    # Solcast: HA-Integration (Auto-Discovery) oder API-Token (Standalone)
    if gewuenscht == "solcast":
        if HA_INTEGRATION_AVAILABLE:
            # Im HA-Add-on: Solcast wird per Auto-Discovery erkannt
            return PrognoseQuelleResult(quelle="solcast", gewuenscht="solcast")

        # Standalone: braucht API-Token in solcast_config
        sensor_mapping = getattr(anlage, "sensor_mapping", None) or {}
        solcast_config = sensor_mapping.get("solcast_config")
        if solcast_config and solcast_config.get("api_key"):
            return PrognoseQuelleResult(quelle="solcast", gewuenscht="solcast")

        logger.info(
            "Anlage %s: Solcast gewählt, aber kein API-Token — Fallback auf eedc",
            getattr(anlage, "id", "?"),
        )
        return PrognoseQuelleResult(
            quelle="eedc",
            ist_fallback=True,
            hinweis="Solcast-API-Token fehlt. eedc-Prognose aktiv.",
            gewuenscht="solcast",
        )

    # Unbekannte Quelle → eedc
    logger.warning("Anlage %s: unbekannte Quelle '%s' — Fallback auf eedc",
                   getattr(anlage, "id", "?"), gewuenscht)
    return PrognoseQuelleResult(
        quelle="eedc",
        ist_fallback=True,
        hinweis=f"Unbekannte Quelle '{gewuenscht}'. eedc-Prognose aktiv.",
        gewuenscht=gewuenscht,
    )
