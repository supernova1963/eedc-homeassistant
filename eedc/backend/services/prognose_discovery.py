"""
Prognose-Discovery: Auto-Erkennung von SFML- und Solcast-Sensoren in HA.

Statt manueller Sensor-Zuordnung im Wizard werden die Sensoren automatisch
anhand der Integration erkannt. Der Discovery-Service fragt die HA-States-API
ab und matcht Entity-IDs gegen bekannte Patterns der Integrationen.

Unterstützte Integrationen:
  - solar_forecast_ml (SFML / Tom-HA): Integration-Prefix variiert,
    Matching über Entity-ID-Suffixe
  - solcast_solar (BJReplay): Prefix "solcast_pv_forecast_",
    Matching über Entity-ID-Suffixe
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Optional

from backend.core.config import HA_INTEGRATION_AVAILABLE

logger = logging.getLogger(__name__)


@dataclass
class DiscoveredSensor:
    """Ein erkannter Sensor mit aktuellem Wert."""
    entity_id: str
    rolle: str  # z.B. "heute_kwh", "morgen_kwh", "naechste_stunde_kwh"
    wert: Optional[float] = None
    einheit: str = ""


@dataclass
class PrognoseDiscoveryResult:
    """Ergebnis der Auto-Erkennung einer Prognose-Integration."""
    integration: str  # "sfml" | "solcast"
    gefunden: bool = False
    device_name: Optional[str] = None
    sensoren: dict[str, DiscoveredSensor] = field(default_factory=dict)
    fehler: Optional[str] = None

    def wert(self, rolle: str) -> Optional[float]:
        """Kurzform: Wert einer Rolle oder None."""
        s = self.sensoren.get(rolle)
        return s.wert if s else None


# ── Sensor-Pattern-Maps ──────────────────────────────────────────────────────
# Jeder Eintrag: (Suffix im entity_id, Rolle, Einheit-Erwartung)
# Suffixe werden case-insensitive gegen das Ende der entity_id gematcht.

SFML_PATTERNS: list[tuple[str, str]] = [
    ("prognose_heute_rest", "heute_rest_kwh"),
    ("prognose_heute", "heute_kwh"),  # NACH _rest, damit _rest nicht fälschlich matcht
    ("prognose_morgen", "morgen_kwh"),
    ("prognose_ubermorgen", "uebermorgen_kwh"),
    ("prognose_nachste_stunde", "naechste_stunde_kwh"),
    ("genauigkeit_30_tage", "genauigkeit_30d"),
    ("planungsprognose_p10_blend", "p10_blend_kwh"),
]

SOLCAST_PATTERNS: list[tuple[str, str]] = [
    ("prognose_heute", "heute_kwh"),
    ("prognose_morgen", "morgen_kwh"),
    ("prognose_tag_3", "tag_3_kwh"),
    ("prognose_tag_4", "tag_4_kwh"),
    ("prognose_tag_5", "tag_5_kwh"),
    ("prognose_tag_6", "tag_6_kwh"),
    ("prognose_tag_7", "tag_7_kwh"),
    ("prognose_aktuelle_stunde", "aktuelle_stunde_wh"),
    ("prognose_nachste_stunde", "naechste_stunde_wh"),
    ("verbleibende_leistung_heute", "heute_rest_kwh"),
    ("prognose_spitzenleistung_heute", "peak_heute_w"),
    ("prognose_spitzenleistung_morgen", "peak_morgen_w"),
    ("aktuelle_leistung", "aktuelle_leistung_w"),
]

# Integration-Prefixe: Entity-IDs die mit diesen Prefixen beginnen
# gehören zur jeweiligen Integration. Für SFML gibt es auch Entities
# ohne Prefix (z.B. sensor.prognose_heute) — die matchen nur per Suffix.
SFML_PREFIXES = ["sensor.solar_forecast_ml_", "sensor.prognose_", "sensor.beste_stunde",
                 "sensor.produktionszeit_", "sensor.max_peak_"]
SOLCAST_PREFIXES = ["sensor.solcast_pv_forecast_", "sensor.zuhause"]


# ── Cache ────────────────────────────────────────────────────────────────────
_discovery_cache: dict[str, tuple[float, PrognoseDiscoveryResult]] = {}
_CACHE_TTL = 300  # 5 Minuten — Sensoren ändern sich nicht oft


async def discover_prognose_sensoren(integration: str) -> PrognoseDiscoveryResult:
    """
    Erkennt Sensoren einer Prognose-Integration aus den HA-States.

    Args:
        integration: "sfml" oder "solcast"

    Returns:
        PrognoseDiscoveryResult mit gematchten Sensoren und aktuellen Werten.
    """
    if not HA_INTEGRATION_AVAILABLE:
        return PrognoseDiscoveryResult(
            integration=integration,
            fehler="Nur im HA-Add-on verfügbar.",
        )

    # Cache prüfen
    now = time.monotonic()
    cached = _discovery_cache.get(integration)
    if cached and (now - cached[0]) < _CACHE_TTL:
        return cached[1]

    if integration == "sfml":
        patterns = SFML_PATTERNS
        prefixes = SFML_PREFIXES
    elif integration == "solcast":
        patterns = SOLCAST_PATTERNS
        prefixes = SOLCAST_PREFIXES
    else:
        return PrognoseDiscoveryResult(
            integration=integration,
            fehler=f"Unbekannte Integration: {integration}",
        )

    try:
        from backend.services.ha_state_service import get_ha_state_service
        ha_svc = get_ha_state_service()

        if not ha_svc.is_available:
            return PrognoseDiscoveryResult(
                integration=integration,
                fehler="HA-API nicht erreichbar.",
            )

        # Alle States laden und nach Integration filtern
        import httpx
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{ha_svc.api_url}/states",
                headers={"Authorization": f"Bearer {ha_svc.token}"},
                timeout=10.0,
            )
            if response.status_code != 200:
                return PrognoseDiscoveryResult(
                    integration=integration,
                    fehler=f"HA-API Fehler: HTTP {response.status_code}",
                )

            all_states = response.json()

        # Entities filtern die zur Integration gehören
        integration_entities: list[dict] = []
        for item in all_states:
            eid = item.get("entity_id", "")
            if any(eid.startswith(p) for p in prefixes):
                integration_entities.append(item)

        if not integration_entities:
            result = PrognoseDiscoveryResult(
                integration=integration,
                fehler=f"Keine {integration.upper()}-Sensoren in HA gefunden.",
            )
            _discovery_cache[integration] = (now, result)
            return result

        # Sensoren matchen
        sensoren: dict[str, DiscoveredSensor] = {}
        for item in integration_entities:
            eid = item.get("entity_id", "")
            eid_lower = eid.lower()

            for suffix, rolle in patterns:
                if eid_lower.endswith(suffix):
                    # Exakt-Match: längster Suffix gewinnt (Patterns sind so sortiert)
                    if rolle in sensoren:
                        continue  # Erster Match gewinnt

                    state = item.get("state")
                    wert = None
                    if state not in [None, "unknown", "unavailable", ""]:
                        try:
                            wert = float(state)
                        except (ValueError, TypeError):
                            pass

                    einheit = (item.get("attributes") or {}).get("unit_of_measurement", "")
                    sensoren[rolle] = DiscoveredSensor(
                        entity_id=eid,
                        rolle=rolle,
                        wert=wert,
                        einheit=einheit,
                    )
                    break  # Nur erstes Pattern matchen

        # Device-Name aus friendly_name ableiten
        device_name = None
        if integration_entities:
            fn = (integration_entities[0].get("attributes") or {}).get("friendly_name", "")
            # "Solar Forecast ML Prognose (heute)" → "Solar Forecast ML"
            # "Solcast PV Forecast Prognose heute" → "Solcast PV Forecast"
            for known_prefix in ["Solar Forecast ML", "Solcast PV Forecast"]:
                if fn.startswith(known_prefix):
                    device_name = known_prefix
                    break

        result = PrognoseDiscoveryResult(
            integration=integration,
            gefunden=len(sensoren) > 0,
            device_name=device_name,
            sensoren=sensoren,
        )
        _discovery_cache[integration] = (now, result)

        logger.info(
            "Prognose-Discovery %s: %d Sensoren erkannt (%s)",
            integration, len(sensoren),
            ", ".join(sorted(sensoren.keys())),
        )
        return result

    except Exception as e:
        logger.warning("Prognose-Discovery %s fehlgeschlagen: %s", integration, e)
        return PrognoseDiscoveryResult(
            integration=integration,
            fehler=str(e),
        )


def invalidate_cache(integration: Optional[str] = None):
    """Cache leeren (z.B. nach Quellenwechsel)."""
    if integration:
        _discovery_cache.pop(integration, None)
    else:
        _discovery_cache.clear()
