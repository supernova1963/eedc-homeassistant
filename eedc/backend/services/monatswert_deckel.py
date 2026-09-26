"""R3-Deckel für den Monatswert eines Zählers — Zählerlücken wie HA (Vorlage §10, W-R10).

Ein Monatswert ist eine Summe von Stunden; was die Stunden verwerfen, verwirft
der Monat. Der Tagespfad (`snapshot/tages_tabelle.py`) deckelt je Sensor-Slot
die Achsen **PV** (inkl. Sonstiges-Erzeuger) und **Einspeisung** mit
`plausibility.schwelle_pv_einspeisung_stunde_kwh(kwp) × n` — mit der kWp der
**Anlage** (`anlage.leistung_kwp`), wie dort. Diese Funktion liefert dieselbe
Schwelle je Sensor-ID für `HAStatisticsService.get_monatswerte(…,
deckel_je_sensor=…)`. Alle übrigen Felder rechnen ohne Deckel (nur R4).

Die Zuordnung Feld → Achse ist dieselbe wie im Tagespfad:
`snapshot/keys._categorize_counter` → `core/berechnungen/spannen.achse_der_kategorie`.
"""
from __future__ import annotations

from typing import Any, Iterable, Mapping, Optional

from backend.core.berechnungen.spannen import ACHSEN_MIT_DECKEL, achse_der_kategorie
from backend.services.snapshot.keys import _categorize_counter
from backend.services.snapshot.plausibility import schwelle_pv_einspeisung_stunde_kwh


def _sensor_id(cfg: Any) -> Optional[str]:
    if isinstance(cfg, Mapping) and cfg.get("strategie", "sensor") == "sensor":
        sid = cfg.get("sensor_id")
        return sid if sid else None
    return None


def deckel_je_sensor(anlage: Any, investitionen: Iterable[Any]) -> dict[str, float]:
    """Sensor-ID → Stunden-Schwelle (kWh) für alle gemappten Zähler, deren
    Feld auf eine gedeckelte Achse (PV, Einspeisung) fällt. Leer, wenn die
    Anlage keine kWp kennt (dann deckelt auch der Tag nicht)."""
    schwelle = schwelle_pv_einspeisung_stunde_kwh(getattr(anlage, "leistung_kwp", None))
    if schwelle is None:
        return {}
    mapping = getattr(anlage, "sensor_mapping", None) or {}
    invs = {str(i.id): i for i in investitionen}
    out: dict[str, float] = {}

    def _nimm(feld: str, cfg: Any, inv: Any) -> None:
        sid = _sensor_id(cfg)
        if sid is None:
            return
        kat = _categorize_counter(
            feld, getattr(inv, "typ", None) if inv is not None else None,
            getattr(inv, "parameter", None) if inv is not None else None,
        )
        if achse_der_kategorie(kat) in ACHSEN_MIT_DECKEL:
            out[sid] = schwelle

    for feld, cfg in (mapping.get("basis") or {}).items():
        _nimm(feld, cfg, None)
    for inv_id, inv_cfg in (mapping.get("investitionen") or {}).items():
        inv = invs.get(str(inv_id))
        if inv is None:
            continue
        for feld, cfg in ((inv_cfg or {}).get("felder") or {}).items():
            _nimm(feld, cfg, inv)
    return out
