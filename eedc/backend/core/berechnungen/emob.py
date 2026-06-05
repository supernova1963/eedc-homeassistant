"""E-Mobilitäts-Aggregate — Ø Verbrauch (kWh/100 km).

Single Source of Truth für die „Ø Verbrauch (kWh/100 km)"-KPI des E-Autos.
Dieselbe Kennzahl erscheint im E-Auto-Dashboard, im Monatsbericht und in der
Komponenten-Auswertung — alle drei MÜSSEN diesen Helper nutzen, sonst driften
die Karten auseinander (Anlass 2026-06-05: Cockpit→E-Auto zeigte 0,0 kWh/100 km,
weil es nur den gemessenen `verbrauch_kwh` durch km teilte, während Monatsbericht
und Komponenten aus der Ladung rechneten — derselbe Wert, zwei Formeln).

Quellen-Vorrang:
  1. **Gemessener Fahrverbrauch** (`verbrauch_kwh`) — exakt, wenn ein
     Verbrauchs-/Trip-Zähler gepflegt ist.
  2. **Sonst Näherung aus der Ladung** (`ladung_kwh ÷ km`) — funktioniert ohne
     Verbrauchssensor, ÜBERSCHÄTZT aber den echten Fahrverbrauch: die an der
     Wallbox gemessene (AC-)Ladung enthält Ladeverluste (~10–15 % AC→Akku),
     blendet SoC-Drift (Akkustand Monatsanfang ≠ -ende) und nicht erfasste
     Fremdladung aus. Für reine Heim-Lader ein guter Proxy, sonst verzerrt —
     deshalb wird die Quelle mitgegeben und in der UI ehrlich gelabelt.
  3. **Keine Basis** (kein Verbrauch, keine Ladung oder km = 0) → ``None``
     („—", NICHT 0,0 — eine erfundene Null ist irreführend).

Hintergrund `verbrauch_kwh`-Überladung: docs/KONZEPT-WALLBOX-EAUTO.md §A.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

# Quellen-Marker für die UI (ehrliches Label je nach Berechnungsbasis).
QUELLE_GEMESSEN = "gemessen"
QUELLE_LADUNG = "ladung"
QUELLE_KEINE = "keine"


@dataclass
class EffizienzWert:
    """Ø Verbrauch (kWh/100 km) plus Herkunft der Berechnungsbasis."""

    wert: Optional[float]   # kWh/100 km — None, wenn keine Basis vorliegt
    quelle: str             # QUELLE_GEMESSEN | QUELLE_LADUNG | QUELLE_KEINE


def eauto_effizienz_100km(
    verbrauch_kwh: float,
    ladung_kwh: float,
    km: float,
) -> EffizienzWert:
    """Ø Verbrauch in kWh/100 km mit Quellen-Vorrang (gemessen vor Ladung).

    Args:
        verbrauch_kwh: Summe gemessener Fahrverbrauch im Zeitraum.
        ladung_kwh: Summe geladener Energie im Zeitraum (Heim + Extern).
        km: Gefahrene Kilometer im Zeitraum.

    Returns:
        EffizienzWert mit ``wert`` (kWh/100 km, ``None`` wenn keine Basis) und
        ``quelle``. Vorrang: gemessener Verbrauch > Ladungs-Näherung > keine.
        Klemmt bewusst NICHT (Diagnose statt stillem Cap).
    """
    if km <= 0:
        return EffizienzWert(None, QUELLE_KEINE)
    if verbrauch_kwh and verbrauch_kwh > 0:
        return EffizienzWert(verbrauch_kwh / km * 100.0, QUELLE_GEMESSEN)
    if ladung_kwh and ladung_kwh > 0:
        return EffizienzWert(ladung_kwh / km * 100.0, QUELLE_LADUNG)
    return EffizienzWert(None, QUELLE_KEINE)
