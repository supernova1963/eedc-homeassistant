"""Speicher-SoC-Tagessimulation (#150 Slice A).

Reine Vorwärtssimulation des Batterie-Ladezustands über die Stunden eines Tages
aus PV- und Verbrauchs-Stundenprofil. Liefert u. a. die Uhrzeit, zu der der
Speicher voll bzw. leer ist.

Berechnungs-Layer (ADR-001): die Aggregat-Logik liegt hier, nicht inline in
Routes/Services. Für den HA-Export simulieren wir ab dem **aktuellen** SoC
(`start_stunde` = jetzige Stunde) — bewusst NICHT das Mitternachts-Mittel, das
der Planungs-Tab (`energie_profil/views.py`) für seine eigene, deskriptive
Ganztags-Vorschau nutzt. Die beiden Pfade sind absichtlich verschieden
parametrisiert (anderer Start-SoC, andere Start-Stunde) und damit kein
Symmetrie-Paar.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Sequence


@dataclass
class StundenBilanz:
    """Energie-Bilanz einer simulierten Stunde (kWh; SoC in %).

    `netzbezug_kwh`/`einspeisung_kwh` ergeben sich als Rest nach der Batterie:
    Überschuss, der nicht mehr in den Speicher passt → Einspeisung; Defizit, das
    der Speicher nicht mehr deckt → Netzbezug. Ohne Speicher (``soc_prozent``
    None) ist es die direkte Bilanz (Überschuss = Einspeisung, Defizit = Bezug).
    """

    stunde: int
    pv_kwh: float
    verbrauch_kwh: float
    netto_kwh: float
    netzbezug_kwh: float
    einspeisung_kwh: float
    soc_prozent: Optional[float]   # None wenn kein Speicher vorhanden


@dataclass
class SpeicherSimErgebnis:
    """Ergebnis der SoC-Tagessimulation."""

    speicher_voll_um: Optional[str]   # "HH:00" — erste Stunde mit SoC ≥ 98 %, sonst None
    speicher_leer_um: Optional[str]   # "HH:00" — erste Stunde (≥12 Uhr) mit SoC ≤ 2 %, sonst None
    end_soc_prozent: float            # SoC am Ende der Simulation
    soc_pro_stunde: dict[int, float] = field(default_factory=dict)
    stunden_bilanz: list[StundenBilanz] = field(default_factory=list)  # Pro simulierte Stunde


def simuliere_speicher_tag(
    pv_stunden: Sequence[Optional[float]],
    verbrauch_stunden: Sequence[Optional[float]],
    speicher_kap_kwh: float,
    start_soc_prozent: float,
    start_stunde: int = 0,
) -> SpeicherSimErgebnis:
    """Simuliert den Batterie-SoC stündlich von ``start_stunde`` bis 23 Uhr.

    Pro Stunde: netto = PV − Verbrauch. Überschuss lädt (bis 100 %), Defizit
    entlädt (bis 0 %). Schwellen identisch zur Planungs-Vorschau: voll = SoC
    ≥ 98 %, leer = SoC ≤ 2 % (Letzteres erst ab 12 Uhr, um morgendliche
    Niedrigstände nicht als „leer am Abend" zu melden).

    Args:
        pv_stunden: 24-Slot kWh-Profil (Backward-Slot h = [h-1, h)).
        verbrauch_stunden: 24-Slot kWh-Verbrauchsprofil.
        speicher_kap_kwh: nutzbare Speicherkapazität in kWh (≤ 0 → keine Sim).
        start_soc_prozent: SoC zu Beginn von ``start_stunde`` (0–100).
        start_stunde: erste simulierte Stunde (0–23).

    Returns:
        SpeicherSimErgebnis. Bei ``speicher_kap_kwh <= 0`` sind voll/leer None.
    """
    soc = max(0.0, min(100.0, start_soc_prozent))
    voll: Optional[str] = None
    leer: Optional[str] = None
    soc_pro_stunde: dict[int, float] = {}
    stunden_bilanz: list[StundenBilanz] = []
    hat_speicher = speicher_kap_kwh > 0

    for h in range(max(0, start_stunde), 24):
        pv = (pv_stunden[h] if h < len(pv_stunden) else 0.0) or 0.0
        vb = (verbrauch_stunden[h] if h < len(verbrauch_stunden) else 0.0) or 0.0
        netto = pv - vb
        netzbezug = 0.0
        einspeisung = 0.0
        soc_h: Optional[float] = None

        if hat_speicher:
            if netto > 0:
                lade_kapazitaet = (100.0 - soc) / 100.0 * speicher_kap_kwh
                ladung = min(netto, lade_kapazitaet)
                soc += (ladung / speicher_kap_kwh) * 100.0
                soc = min(soc, 100.0)
                einspeisung = netto - ladung
            else:
                entlade_kapazitaet = soc / 100.0 * speicher_kap_kwh
                entladung = min(abs(netto), entlade_kapazitaet)
                soc -= (entladung / speicher_kap_kwh) * 100.0
                soc = max(soc, 0.0)
                netzbezug = abs(netto) - entladung

            soc_h = round(soc, 1)
            soc_pro_stunde[h] = soc_h
            if soc >= 98.0 and voll is None:
                voll = f"{h:02d}:00"
            if soc <= 2.0 and leer is None and h >= 12:
                leer = f"{h:02d}:00"
        else:
            # Ohne Batterie: direkte Bilanz.
            if netto > 0:
                einspeisung = netto
            else:
                netzbezug = abs(netto)

        stunden_bilanz.append(StundenBilanz(
            stunde=h,
            pv_kwh=pv,
            verbrauch_kwh=vb,
            netto_kwh=netto,
            netzbezug_kwh=netzbezug,
            einspeisung_kwh=einspeisung,
            soc_prozent=soc_h,
        ))

    return SpeicherSimErgebnis(voll, leer, round(soc, 1), soc_pro_stunde, stunden_bilanz)
