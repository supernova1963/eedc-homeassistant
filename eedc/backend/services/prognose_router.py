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

    Synchron — keine DB-Abfrage nötig. Verfügbarkeit wird anhand der
    HA-Erreichbarkeit und der Anlage-Konfiguration geprüft. Die tatsächlichen
    Sensor-Werte werden asynchron über discover_prognose_sensoren() geladen
    (siehe prognose_discovery.py).

    ⚠ **N-156/F-26 — „HA erreichbar", nicht „Add-on":** bis 2026-08-11 fragten
    beide Zweige `HA_INTEGRATION_AVAILABLE` (= SUPERVISOR_TOKEN). Wer eedc im
    Docker betreibt und HA per Long-Lived-Token angebunden hat, bekam damit
    einen **stillen Fallback auf die eedc-Prognose** — mit dem Hinweis, SFML sei
    „nur im HA-Add-on verfügbar", während seine Sensoren über dieselbe REST-API
    lesbar sind. Die Discovery darunter kann diesen Fall seit N-156; ohne diese
    Zeile hier bliebe sie unerreichbar.
    """
    from backend.services.ha_state_service import get_ha_state_service

    ha_erreichbar = get_ha_state_service().is_available

    gewuenscht = getattr(anlage, "prognose_quelle", None) or "eedc"

    # eedc ist immer verfügbar
    if gewuenscht == "eedc":
        return PrognoseQuelleResult(quelle="eedc", gewuenscht="eedc")

    # SFML braucht eine erreichbare HA-Instanz (Add-on ODER Token)
    if gewuenscht == "sfml":
        if not ha_erreichbar:
            logger.info(
                "Anlage %s: SFML gewählt, aber kein HA — Fallback auf eedc",
                getattr(anlage, "id", "?"),
            )
            return PrognoseQuelleResult(
                quelle="eedc",
                ist_fallback=True,
                hinweis="SFML braucht eine verbundene Home-Assistant-Instanz. "
                        "eedc-Prognose aktiv.",
                gewuenscht="sfml",
            )
        return PrognoseQuelleResult(quelle="sfml", gewuenscht="sfml")

    # Solcast: HA-Integration (Auto-Discovery) oder API-Token (ohne HA)
    if gewuenscht == "solcast":
        if ha_erreichbar:
            # Mit HA-Verbindung: Solcast wird per Auto-Discovery erkannt
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
