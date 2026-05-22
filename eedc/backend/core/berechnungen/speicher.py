"""Speicher-Aggregate — Effizienz aus InvestitionMonatsdaten.

Single Source of Truth für die Speicher-Round-Trip-Effizienz.

Round-Trip-Effizienz η = Entladung / Ladung ist nur über ein geschlossenes
Fenster sinnvoll: Ein Akku ist ein *Speicher* (Bestand), Monats-Ladung und
-Entladung sind *Flüsse*. Über eine einzelne Monatsgrenze trägt der SoC einen
Übertrag — ein Monat kann legitim mehr ent- als laden, weil gespeicherte
Energie aus dem Vormonat abfließt (Carry-over). Eine naive Pro-Monats-
Effizienz zappelt dadurch und kann 100 % überschreiten (Rainer-PN 2026-05-22).

Erst über ein langes Fenster mittelt sich ΔSoC aus und entladung/ladung wird
belastbar — vgl. `speicher_wirtschaftlichkeit.WIRKUNGSGRAD_FENSTER_MONATE_MIN`
(dort wird unterhalb von 6 Monaten SoC-korrigiert gerechnet). Dieser Layer
braucht keinen SoC: `gleitende_effizienz` summiert über ein 12-Monats-Fenster,
der einzige Restfehler ist ein ΔSoC über das ganze Fenster — durch die
Kapazität gedeckelt und damit vernachlässigbar.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

# Fensterbreite, ab der entladung/ladung als belastbare Round-Trip-Effizienz
# gilt (darunter dominiert der SoC-Übertrag).
EFFIZIENZ_FENSTER_MONATE: int = 12


@dataclass
class MonatsEffizienz:
    """Gleitende Speicher-Effizienz für einen Kalendermonat."""

    jahr: int
    monat: int
    effizienz_prozent: Optional[float]
    fenster_monate: int  # Anzahl Monate, die ins gleitende Fenster eingingen


def speicher_effizienz_prozent(
    ladung_kwh: float, entladung_kwh: float
) -> Optional[float]:
    """Round-Trip-Effizienz in % über ein Fenster: entladung / ladung × 100.

    Nur belastbar über ein Fenster mit ΔSoC ≈ 0 (langes Fenster). Über eine
    einzelne Monatsgrenze ist der Wert durch den SoC-Übertrag verzerrt und
    kann 100 % überschreiten — dann KEINE Pro-Monats-Effizienz exponieren,
    sondern `gleitende_effizienz()` nutzen. Die Funktion klemmt bewusst NICHT
    (Diagnose statt stillem Cap).

    Gibt `None` zurück, wenn keine Ladung vorliegt.
    """
    if ladung_kwh <= 0:
        return None
    return entladung_kwh / ladung_kwh * 100.0


def gleitende_effizienz(
    monats_reihe: list[tuple[int, int, float, float]],
    fenster: int = EFFIZIENZ_FENSTER_MONATE,
) -> list[MonatsEffizienz]:
    """Gleitende Round-Trip-Effizienz über `fenster` Monate.

    Args:
        monats_reihe: chronologisch sortierte Tupel
            ``(jahr, monat, ladung_kwh, entladung_kwh)``.
        fenster: Fensterbreite in Monaten (Default `EFFIZIENZ_FENSTER_MONATE`).

    Für jeden Monat: Σentladung / Σladung über die letzten `fenster` Monate
    (inklusive dem Monat selbst); bei kürzerer Historie kumulativ ab Start.
    So mittelt sich der SoC-Übertrag aus — die Reihe zappelt nicht über
    100 %, wie es eine naive Pro-Monats-Effizienz täte.
    """
    ergebnis: list[MonatsEffizienz] = []
    for i, (jahr, monat, _, _) in enumerate(monats_reihe):
        start = max(0, i - fenster + 1)
        fenster_rows = monats_reihe[start : i + 1]
        sum_ladung = sum(r[2] for r in fenster_rows)
        sum_entladung = sum(r[3] for r in fenster_rows)
        ergebnis.append(
            MonatsEffizienz(
                jahr=jahr,
                monat=monat,
                effizienz_prozent=speicher_effizienz_prozent(
                    sum_ladung, sum_entladung
                ),
                fenster_monate=len(fenster_rows),
            )
        )
    return ergebnis
