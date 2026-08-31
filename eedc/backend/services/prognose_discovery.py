"""
Prognose-Discovery: Auto-Erkennung von SFML- und Solcast-Sensoren in HA.

Statt manueller Sensor-Zuordnung im Wizard werden die Sensoren automatisch
erkannt — seit dem 31.08.2026 **über die Integration**, nicht mehr über ihre
Namen. Die Menge kommt aus ``integration_entities()``, die Rolle aus der
``unique_id`` der Entity-Registry; Anzeigename und das alte Entity-ID-Muster
bleiben als Rückfälle. Kaskade, Begründung und Messungen:
``services/ha_integration_aufloeser.py``.

⚠ **Warum der Umbau:** Die Präfix- und Suffix-Listen unten sind die Abschrift
**einer einzigen Instanz** und durchgehend deutschsprachig. Wer seine HA auf
Englisch angelegt hat, fiel durch **beide** Filter — gemeldet von **Burkard**
(#401, 30.08.2026), der sich mit sechs Template-Sensoren behalf. Die Listen sind
**nicht gelöscht**: wessen Sensoren heute gefunden werden, merkt nichts.

Unterstützte Integrationen:
  - ``solar_forecast_ml`` (SFML / Tom-HA)
  - ``solcast_solar`` (BJReplay)
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class DiscoveredSensor:
    """Ein erkannter Sensor mit aktuellem Wert.

    ``attribut`` trägt — nur für Rollen mit Stundenprofil-Bedarf — die rohe
    Attribut-Payload (z.B. evcc ``forecast``-Liste oder ``hours``-Dict), damit
    nachgelagerte Parser SFMLs echtes Stundenprofil nutzen können statt nur den
    State-Skalar (Tracking #110 „A").
    """
    entity_id: str
    rolle: str  # z.B. "heute_kwh", "morgen_kwh", "naechste_stunde_kwh"
    wert: Optional[float] = None
    einheit: str = ""
    attribut: object = None
    # Welche Stufe der Kaskade diese Rolle gefunden hat: "unique_id" (die
    # Plattform-Auskunft), "name" (Anzeigename) oder "muster" (das alte
    # Entity-ID-Muster). Sie steht in der Status-Anzeige, damit ein Melder
    # nicht im Container nachsehen muss, warum eine Rolle fehlt.
    stufe: str = "muster"


@dataclass
class PrognoseDiscoveryResult:
    """Ergebnis der Auto-Erkennung einer Prognose-Integration."""
    integration: str  # "sfml" | "solcast"
    gefunden: bool = False
    sensoren: dict[str, DiscoveredSensor] = field(default_factory=dict)
    fehler: Optional[str] = None
    # Auf welchem Weg die Entitäten der Integration gefunden wurden und auf
    # welchem ihre Rollen — für die Status-Anzeige. „praefix"/„muster" heißt:
    # der alte Weg hat getragen, die Plattform-Auskunft war nicht zu holen.
    menge_quelle: str = "praefix"
    rolle_quelle: str = "muster"
    anzahl_entities: int = 0

    def wert(self, rolle: str) -> Optional[float]:
        """Kurzform: Wert einer Rolle oder None."""
        s = self.sensoren.get(rolle)
        return s.wert if s else None

    def attribut(self, rolle: str):
        """Kurzform: rohe Attribut-Payload einer Rolle (z.B. evcc ``forecast``)
        oder None."""
        s = self.sensoren.get(rolle)
        return s.attribut if s else None


# ── Sensor-Pattern-Maps ──────────────────────────────────────────────────────
# Jeder Eintrag: (Suffix im entity_id, Rolle, Einheit-Erwartung)
# Suffixe werden case-insensitive gegen das Ende der entity_id gematcht.

SFML_PATTERNS: list[tuple[str, str]] = [
    # evcc-Sensor mit echtem Mehrtages-Stundenprofil im `forecast`-Attribut —
    # vor `prognose_heute`/`_morgen` matchen ist unkritisch (eigener Suffix).
    ("evcc_solar_prognose", "stundenprofil"),
    ("prognose_heute_rest", "heute_rest_kwh"),
    ("prognose_heute", "heute_kwh"),  # NACH _rest, damit _rest nicht fälschlich matcht
    ("prognose_morgen", "morgen_kwh"),
    ("prognose_ubermorgen", "uebermorgen_kwh"),
    ("prognose_nachste_stunde", "naechste_stunde_kwh"),
    ("genauigkeit_30_tage", "genauigkeit_30d"),
    ("planungsprognose_p10_blend", "p10_blend_kwh"),
]

# Rollen, deren HA-**Attribut** (nicht nur State) für das Stundenprofil
# gebraucht wird. rolle → Attribut-Namen in Prioritätsreihenfolge.
#   stundenprofil (evcc): `forecast` = [{start, end, value(Wh)}], 3 Tage stündlich
#   heute_kwh   (prognose_heute):  `hours` = {"HH:00": kWh}, 24 h — Fallback
SFML_ATTRIBUT_ROLLEN: dict[str, tuple[str, ...]] = {
    "stundenprofil": ("forecast",),
    "heute_kwh": ("hours",),
}

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

# Klartext-Namen der Rollen für die Status-Anzeige. Ohne sie stand in der
# Oberfläche nur „gefunden" oder ein Fehler — DASS vier von sechs Rollen fehlen,
# war nirgends sichtbar. Burkard (#401, 2026-08-30) musste dafür in den Add-on-
# Container sehen; seine sechs SFML-Entities heißen `sensor.none_*`, weil eine
# frühe SFML-Fassung den Gerätenamen nicht setzte, und fielen deshalb durch
# Präfix- UND Suffix-Filter.
ROLLEN_LABELS: dict[str, str] = {
    "stundenprofil": "Stundenprofil (Mehrtages-Verlauf)",
    "heute_kwh": "Prognose heute",
    "heute_rest_kwh": "Prognose Rest heute",
    "morgen_kwh": "Prognose morgen",
    "uebermorgen_kwh": "Prognose übermorgen",
    "naechste_stunde_kwh": "Prognose nächste Stunde",
    "genauigkeit_30d": "Genauigkeit 30 Tage",
    "p10_blend_kwh": "Planungsprognose P10",
    "tag_3_kwh": "Prognose Tag 3", "tag_4_kwh": "Prognose Tag 4",
    "tag_5_kwh": "Prognose Tag 5", "tag_6_kwh": "Prognose Tag 6",
    "tag_7_kwh": "Prognose Tag 7",
    "aktuelle_stunde_wh": "Prognose aktuelle Stunde",
    "naechste_stunde_wh": "Prognose nächste Stunde (Wh)",
    "verbleibende_leistung_heute": "Verbleibende Leistung heute",
    "peak_heute_w": "Spitzenleistung heute", "peak_morgen_w": "Spitzenleistung morgen",
    "aktuelle_leistung_w": "Aktuelle Leistung",
}

# Rollen, ohne die die Live-Anzeige einer Quelle unvollständig bleibt. Fehlt
# eine davon, ist das kein Schönheitsfehler: ohne `stundenprofil`/`heute_kwh`
# gibt es für diese Quelle keinen nachgeführten Rest.
ROLLEN_WESENTLICH: dict[str, tuple[str, ...]] = {
    "sfml": ("heute_kwh", "morgen_kwh", "stundenprofil"),
    "solcast": ("heute_kwh", "morgen_kwh"),
}

SFML_PREFIXES = ["sensor.solar_forecast_ml_", "sensor.prognose_", "sensor.beste_stunde",
                 "sensor.produktionszeit_", "sensor.max_peak_"]
SOLCAST_PREFIXES = ["sensor.solcast_pv_forecast_", "sensor.zuhause"]

# ── Integration statt Namensmuster (Burkard #401, 2026-08-31) ────────────────
# Die beiden Präfix-Listen oben sind die Abschrift EINER Instanz: `sensor.
# prognose_`, `sensor.beste_stunde` & Co. sind Gernots präfixlose SFML-Ausreißer,
# `sensor.zuhause` ist sein Solcast-Anlagenname. Sie stehen weiter da, aber nur
# noch als letzter Rückfall — die Menge kommt jetzt aus `integration_entities()`,
# die Rolle aus der `unique_id`. Warum die Entity-ID dafür nie taugte, steht in
# `services/ha_integration_aufloeser.py`.
INTEGRATION_DOMAIN: dict[str, str] = {
    "sfml": "solar_forecast_ml",
    "solcast": "solcast_solar",
}

# unique_id-Kern → Rolle. ⚑ Am 31.08.2026 an Gernots Instanz GEMESSEN
# (`config/entity_registry/list`), nicht aus den Entity-IDs erschlossen: SFML
# schreibt `<config-entry-id>_ml_<kern>`, Solcast schreibt den Kern ohne jeden
# Präfix. Gematcht wird deshalb mit `endswith`, längster Kern zuerst.
SFML_UNIQUE_KERNE: dict[str, str] = {
    "ml_evcc_forecast": "stundenprofil",
    "ml_forecast_remaining": "heute_rest_kwh",
    "ml_expected_daily_production": "heute_kwh",
    "ml_forecast_tomorrow": "morgen_kwh",
    "ml_forecast_day_after_tomorrow": "uebermorgen_kwh",
    "ml_next_hour_forecast": "naechste_stunde_kwh",
    "ml_avg_accuracy_30d": "genauigkeit_30d",
    "ml_conservative_planning_forecast": "p10_blend_kwh",
}

SOLCAST_UNIQUE_KERNE: dict[str, str] = {
    "total_kwh_forecast_today": "heute_kwh",
    "total_kwh_forecast_tomorrow": "morgen_kwh",
    "total_kwh_forecast_d3": "tag_3_kwh",
    "total_kwh_forecast_d4": "tag_4_kwh",
    "total_kwh_forecast_d5": "tag_5_kwh",
    "total_kwh_forecast_d6": "tag_6_kwh",
    "total_kwh_forecast_d7": "tag_7_kwh",
    "forecast_this_hour": "aktuelle_stunde_wh",
    "forecast_next_hour": "naechste_stunde_wh",
    "get_remaining_today": "heute_rest_kwh",
    "peak_w_today": "peak_heute_w",
    "peak_w_tomorrow": "peak_morgen_w",
    "power_now": "aktuelle_leistung_w",
}

# Normalisierter Anzeigename → Rolle. Zweiter Rückfall, falls die Entity-
# Registry nicht lesbar ist (alte HA-Version, WebSocket gesperrt). Deutsche
# Kerne von Gernots Instanz, englische aus Burkards Meldung (#401) — beide
# gemessen. ⛔ Keine weiteren Sprachen erfinden: ein nicht gemessener Kern
# behauptet eine Namensgebung, die niemand gesehen hat.
SFML_NAMENS_KERNE: dict[str, str] = {
    "evcc_solar_prognose": "stundenprofil",
    "prognose_heute_rest": "heute_rest_kwh",
    "forecast_today_remaining": "heute_rest_kwh",
    "prognose_heute": "heute_kwh",
    "expected_daily_production": "heute_kwh",
    "prognose_morgen": "morgen_kwh",
    "forecast_tomorrow": "morgen_kwh",
    "prognose_ubermorgen": "uebermorgen_kwh",
    "prognose_nachste_stunde": "naechste_stunde_kwh",
    "next_hour_forecast": "naechste_stunde_kwh",
    "genauigkeit_30_tage": "genauigkeit_30d",
    "planungsprognose_p10_blend": "p10_blend_kwh",
}

SOLCAST_NAMENS_KERNE: dict[str, str] = {
    "prognose_heute": "heute_kwh",
    "forecast_today": "heute_kwh",
    "prognose_morgen": "morgen_kwh",
    "forecast_tomorrow": "morgen_kwh",
    "prognose_tag_3": "tag_3_kwh", "forecast_day_3": "tag_3_kwh",
    "prognose_tag_4": "tag_4_kwh", "forecast_day_4": "tag_4_kwh",
    "prognose_tag_5": "tag_5_kwh", "forecast_day_5": "tag_5_kwh",
    "prognose_tag_6": "tag_6_kwh", "forecast_day_6": "tag_6_kwh",
    "prognose_tag_7": "tag_7_kwh", "forecast_day_7": "tag_7_kwh",
    "prognose_aktuelle_stunde": "aktuelle_stunde_wh",
    "forecast_this_hour": "aktuelle_stunde_wh",
    "prognose_nachste_stunde": "naechste_stunde_wh",
    "forecast_next_hour": "naechste_stunde_wh",
    "prognose_verbleibende_leistung_heute": "heute_rest_kwh",
    "forecast_remaining_today": "heute_rest_kwh",
    "prognose_spitzenleistung_heute": "peak_heute_w",
    "forecast_peak_power_today": "peak_heute_w",
    "prognose_spitzenleistung_morgen": "peak_morgen_w",
    "forecast_peak_power_tomorrow": "peak_morgen_w",
    "aktuelle_leistung": "aktuelle_leistung_w",
    "power_now": "aktuelle_leistung_w",
}


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
    # N-156/F-26: kein Gate auf `HA_INTEGRATION_AVAILABLE` (= SUPERVISOR_TOKEN)
    # mehr. Die Erreichbarkeit prüft weiter unten `HAStateService.is_available`
    # selbst — und der deckt seit dem 05.08. **beide** Wege ab (Supervisor im
    # Add-on, Long-Lived-Token im Standalone). Das Gate hier sagte einem per
    # Token angebundenen Docker-Betrieb „Nur im HA-Add-on verfügbar", obwohl
    # seine SFML-/Solcast-Sensoren über dieselbe API lesbar sind.

    # Cache prüfen
    now = time.monotonic()
    cached = _discovery_cache.get(integration)
    if cached and (now - cached[0]) < _CACHE_TTL:
        return cached[1]

    if integration == "sfml":
        patterns = SFML_PATTERNS
        prefixes = SFML_PREFIXES
        unique_kerne = SFML_UNIQUE_KERNE
        namens_kerne = SFML_NAMENS_KERNE
    elif integration == "solcast":
        patterns = SOLCAST_PATTERNS
        prefixes = SOLCAST_PREFIXES
        unique_kerne = SOLCAST_UNIQUE_KERNE
        namens_kerne = SOLCAST_NAMENS_KERNE
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

        # Menge + Rolle über die Integration statt über Namensmuster — die
        # Präfix-/Suffix-Listen bleiben als letzter Rückfall in der Kaskade.
        from backend.services.ha_integration_aufloeser import loese_integration_auf

        aufl = await loese_integration_auf(
            domain=INTEGRATION_DOMAIN[integration],
            praefixe=prefixes,
            unique_kerne=unique_kerne,
            namens_kerne=namens_kerne,
            muster=patterns,
            states=all_states,
        )

        if not aufl.anzahl_entities:
            result = PrognoseDiscoveryResult(
                integration=integration,
                fehler=f"Keine {integration.upper()}-Sensoren in HA gefunden.",
                menge_quelle=aufl.menge_quelle,
            )
            _discovery_cache[integration] = (now, result)
            return result

        sensoren: dict[str, DiscoveredSensor] = {}
        for rolle, tr in aufl.treffer.items():
            item = tr.item
            state = item.get("state")
            wert = None
            if state not in [None, "unknown", "unavailable", ""]:
                try:
                    wert = float(state)
                except (ValueError, TypeError):
                    pass

            attrs = item.get("attributes") or {}
            einheit = attrs.get("unit_of_measurement", "")

            # Stundenprofil-tragendes Attribut mitnehmen (nur SFML-Rollen).
            attribut = None
            for attr_name in SFML_ATTRIBUT_ROLLEN.get(rolle, ()):
                if attrs.get(attr_name) is not None:
                    attribut = attrs[attr_name]
                    break

            sensoren[rolle] = DiscoveredSensor(
                entity_id=tr.entity_id,
                rolle=rolle,
                wert=wert,
                einheit=einheit,
                attribut=attribut,
                stufe=tr.stufe,
            )

        result = PrognoseDiscoveryResult(
            integration=integration,
            gefunden=len(sensoren) > 0,
            sensoren=sensoren,
            menge_quelle=aufl.menge_quelle,
            rolle_quelle=aufl.rolle_quelle,
            anzahl_entities=aufl.anzahl_entities,
        )
        _discovery_cache[integration] = (now, result)

        logger.info(
            "Prognose-Discovery %s: %d Sensoren erkannt aus %d Entities "
            "(Menge: %s, Rolle: %s) — %s",
            integration, len(sensoren), aufl.anzahl_entities,
            aufl.menge_quelle, aufl.rolle_quelle,
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
    """Cache leeren (z.B. nach Quellenwechsel).

    Leert **auch** die Caches des Auflösers (Integrations-Menge und
    Entity-Registry). Ohne das hätte eine frisch eingerichtete Integration bis
    zu 15 Minuten lang keine Rollen — der Discovery-Cache wäre leer, die Menge
    davor noch die alte.
    """
    if integration:
        _discovery_cache.pop(integration, None)
    else:
        _discovery_cache.clear()
    from backend.services.ha_integration_aufloeser import (
        invalidate_cache as _aufloeser_cache_leeren,
    )
    _aufloeser_cache_leeren()


async def discovery_status(integration: str) -> dict:
    """Was die Auto-Erkennung je Rolle gefunden hat — für die Anzeige.

    Die Erkennung matcht Entity-IDs über Präfix und Suffix. Beides sind
    Konventionen des Integrationsautors, keine Garantien: Die Entity-ID entsteht
    in Home Assistant beim ersten Anlegen und wandert später nicht mit, wenn die
    Integration ihre Namen ändert. Wessen Sensoren anders heißen, bekommt heute
    stillschweigend weniger Werte — diese Funktion macht das sichtbar, statt es
    dem Anwender zu überlassen, es im Container nachzusehen.
    """
    res = await discover_prognose_sensoren(integration)
    patterns = SFML_PATTERNS if integration == "sfml" else SOLCAST_PATTERNS
    wesentlich = ROLLEN_WESENTLICH.get(integration, ())
    rollen = []
    for _suffix, rolle in patterns:
        s = res.sensoren.get(rolle)
        rollen.append({
            "rolle": rolle,
            "label": ROLLEN_LABELS.get(rolle, rolle),
            "gefunden": s is not None,
            "entity_id": s.entity_id if s else None,
            "wert": s.wert if s else None,
            "wesentlich": rolle in wesentlich,
            # Auf welcher Stufe der Kaskade diese Rolle gefunden wurde.
            "stufe": s.stufe if s else None,
        })
    fehlend_wesentlich = [r["label"] for r in rollen
                          if r["wesentlich"] and not r["gefunden"]]
    return {
        "integration": integration,
        "gefunden": res.gefunden,
        "fehler": res.fehler,
        "rollen": rollen,
        "anzahl_gefunden": sum(1 for r in rollen if r["gefunden"]),
        "anzahl_gesamt": len(rollen),
        "fehlend_wesentlich": fehlend_wesentlich,
        # Wie die Entitäten der Integration überhaupt eingesammelt wurden.
        # „praefix" heißt: HA hat `integration_entities()` nicht beantwortet
        # (alte Version, Endpunkt gesperrt) — dann greift wieder die alte,
        # sprachabhängige Liste, und das gehört sichtbar dazu.
        "menge_quelle": res.menge_quelle,
        "rolle_quelle": res.rolle_quelle,
        "anzahl_entities": res.anzahl_entities,
    }
