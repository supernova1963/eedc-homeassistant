"""Zentrale Helper für PV-Ausrichtung (Azimut) und Neigung.

Hintergrund: Die Investition speichert PV-Parameter an zwei Stellen, die
historisch gewachsen sind:

1. Top-Level-Spalten auf der Investition-Tabelle:
   - `Investition.leistung_kwp` (Float)
   - `Investition.neigung_grad` (Float)
   - `Investition.ausrichtung` (String, z.B. "Süd")

2. Im `parameter`-JSON:
   - `kwp` (Float) — alternative Quelle für Leistung
   - `neigung_grad` / `neigung` — alternative Quelle für Neigung
   - `ausrichtung_grad` (int) — exakter Azimut aus dem PV-Modul-Formular
   - `ausrichtung` — redundanter String als Fallback

Die Prognose-Pfade (Tagesprognose, Aussichten-Kurzfristig, Prefetch) lasen
ursprünglich nur aus dem parameter-JSON und fielen dadurch stumm auf
Defaults (Neigung=35°, Azimut=0°) zurück, wenn die Werte nur in den
Top-Level-Spalten vorhanden waren.

Dieser Helper vereinheitlicht das Lesen über alle drei Pfade.
"""
from dataclasses import dataclass
from typing import Any

# Mapping für Ausrichtung-Strings → Azimut-Grad (EEDC/PVGIS-Konvention:
# 0=Süd, -90=Ost, 90=West, 180/-180=Nord).
AUSRICHTUNG_MAP = {
    "sued": 0, "süd": 0, "s": 0,
    "ost": -90, "o": -90, "e": -90,
    "west": 90, "w": 90,
    "nord": 180, "n": 180,
    "suedost": -45, "südost": -45, "so": -45, "se": -45,
    "suedwest": 45, "südwest": 45, "sw": 45,
    "nordost": -135, "no": -135, "ne": -135,
    "nordwest": 135, "nw": 135,
}


def get_pv_kwp(inv: Any) -> float:
    """Leistung in kWp. Priorität: Top-Level-Spalte → parameter.kwp → 0."""
    direct = getattr(inv, "leistung_kwp", None)
    if direct:
        return float(direct)
    params = getattr(inv, "parameter", None) or {}
    try:
        return float(params.get("kwp") or 0)
    except (TypeError, ValueError):
        return 0.0


def get_pv_neigung(inv: Any, default: int = 35) -> int:
    """Neigung in Grad. Priorität: Top-Level → parameter.neigung_grad →
    parameter.neigung → Default."""
    direct = getattr(inv, "neigung_grad", None)
    if direct is not None:
        try:
            return int(direct)
        except (TypeError, ValueError):
            pass
    params = getattr(inv, "parameter", None) or {}
    for key in ("neigung_grad", "neigung"):
        val = params.get(key)
        if val is not None:
            try:
                return int(val)
            except (TypeError, ValueError):
                continue
    return default


def get_pv_azimut(inv: Any, default: int = 0) -> int:
    """Azimut in Grad (0=Süd). Priorität: parameter.ausrichtung_grad →
    Top-Level-String → parameter.ausrichtung (String oder Zahl) → Default."""
    params = getattr(inv, "parameter", None) or {}
    val = params.get("ausrichtung_grad")
    if val is not None:
        try:
            return int(val)
        except (TypeError, ValueError):
            pass
    direct_str = getattr(inv, "ausrichtung", None)
    if isinstance(direct_str, str) and direct_str:
        mapped = AUSRICHTUNG_MAP.get(direct_str.lower())
        if mapped is not None:
            return mapped
    param_val = params.get("ausrichtung")
    if isinstance(param_val, str) and param_val:
        mapped = AUSRICHTUNG_MAP.get(param_val.lower())
        if mapped is not None:
            return mapped
    elif isinstance(param_val, (int, float)):
        return int(param_val)
    return default


@dataclass(frozen=True)
class Orientierungsgruppe:
    """Eine nach (Neigung, Ausrichtung) zusammengefasste PV-String-Gruppe."""

    neigung: int       # Grad (0=horizontal, 90=vertikal)
    ausrichtung: int   # Azimut-Grad (0=Süd, -90=Ost, 90=West, 180=Nord)
    kwp: float         # Summe der kWp aller Module dieser Orientierung


def orientierungs_gruppen(invs: Any) -> list[Orientierungsgruppe]:
    """Gruppiert aktive PV-/BKW-Investitionen nach Orientierung (SoT).

    Der Multi-String-Fan-out (live_wetter, prognose_kanon) fragt OpenMeteo pro
    Orientierungsgruppe getrennt ab und kombiniert kWp-gewichtet — eine
    Ost/West-Anlage liefert sonst (über eine gemittelte Ausrichtung) einen
    systematisch falschen Tagesgang.

    Liest kWp/Neigung/Azimut konsistent über die ``get_pv_*``-Helper (Top-Level-
    Spalte → ``parameter``-JSON → Default). Module mit kWp ≤ 0 entfallen.
    Reihenfolge: kWp-stärkste Gruppe zuerst (deterministisch, dominante Gruppe
    führt für Defaults wie Schätzpfad-Wetter).
    """
    gruppen: dict[tuple[int, int], float] = {}
    for inv in invs or []:
        kwp = get_pv_kwp(inv)
        if kwp <= 0:
            continue
        key = (int(get_pv_neigung(inv)), int(get_pv_azimut(inv)))
        gruppen[key] = gruppen.get(key, 0.0) + kwp
    return [
        Orientierungsgruppe(neigung=n, ausrichtung=a, kwp=kwp)
        for (n, a), kwp in sorted(gruppen.items(), key=lambda kv: kv[1], reverse=True)
    ]


# PVGIS-Standard-Systemverluste (Kabel, Wechselrichter, Verschmutzung).
# Fraktion, nicht Prozent — passt direkt in `ertrag * (1 - system_losses)`.
DEFAULT_SYSTEM_LOSSES = 0.14


def resolve_system_losses(pvgis: Any) -> float:
    """Systemverluste als Fraktion (0..1) aus dem aktiven PVGIS-Eintrag.

    `PVGISPrognose.system_losses` ist in Prozent gepflegt (Setup-Wert) und
    wird hier durch 100 geteilt. Fehlt der Eintrag oder ist der Wert leer/0,
    greift der PVGIS-Standard `DEFAULT_SYSTEM_LOSSES` (14 %).

    Hintergrund: diese Zeile stand als
    `pvgis.system_losses / 100 if pvgis and pvgis.system_losses else 0.14`
    an sechs Read-Sites parallel (prognose_service, prefetch_service,
    prognosen, aussichten, solar_prognose, energie_profil/views) plus die
    `0.14`-Konstante 5× definiert — bei Drift hätte ein Setup-Wert nur in
    manchen Sichten gewirkt (siehe `feedback_aggregations_drift`).
    """
    if pvgis is not None and pvgis.system_losses:
        return pvgis.system_losses / 100
    return DEFAULT_SYSTEM_LOSSES
