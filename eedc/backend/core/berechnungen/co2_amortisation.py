"""CO2-Amortisation — graue Herstellungs-Last (CO2) der Investitionen (#284).

Single Source of Truth für die Σ der grauen Last über die Investitionen einer
Anlage. Die graue Last wird in `auswertung/CO2Tab` gegen die kumulierte CO2-
Betriebs-Einsparung gerechnet → Schnittpunkt „ab wann klimapositiv".

Spec (Discussion #284, mit Safi105 abgestimmt, in der Übergabe eingefroren):
  - PV-Module / Balkonkraftwerk: voller Herstellungs-Aufwand × kWp (inkl. WR/Montage).
  - Speicher: voller Herstellungs-Aufwand × kWh.
  - Wärmepumpe: flat/Gerät, aber nur die DIFFERENZ zur Gas-/Öl-Heizung.
  - E-Auto: flat/Fahrzeug, aber nur die DIFFERENZ zum Verbrenner.
    Dienstwagen sind ausgeschlossen ([[feedback_dienstwagen_alle_checks]]).

Richtwerte aus `core/calculations.GRAUE_LAST_*`. Pro Investition über das
optionale Feld `graue_last_kg` (Herstellerdatenblatt) übersteuerbar; leer = Default.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Optional

from backend.core.investition_parameter import PARAM_SPEICHER, ist_dienstlich
from backend.models.investition import InvestitionTyp

# Hinweis: Die GRAUE_LAST_*-Richtwerte leben in core/calculations.py (neben den
# CO2_FAKTOR_*). calculations.py importiert seinerseits aus dem berechnungen-Paket
# (einspeise_erloes) → ein Top-Level-Import hier wäre ein Import-Zyklus. Daher
# werden die Konstanten lazy in graue_last_einzeln() geladen.

# Quelle der grauen Last je Posten — für UI/Daten-Checker-Transparenz.
QUELLE_OVERRIDE = "override"   # Herstellerdatenblatt (Feld graue_last_kg)
QUELLE_DEFAULT = "default"     # Richtwert nach Typ/Größe
QUELLE_FEHLT = "fehlt"         # skaliert mit fehlender Größe (kWp/kWh = 0)
QUELLE_KEIN_DEFAULT = "kein_default"  # Typ ohne Richtwert (Wallbox, WR, Sonstiges)


@dataclass
class GraueLastPosten:
    """Graue Herstellungs-Last einer einzelnen Investition."""
    investition_id: Optional[int]
    typ: str
    bezeichnung: str
    graue_last_kg: float
    quelle: str


@dataclass
class GraueLastBericht:
    """Σ der grauen Last über die berücksichtigten Investitionen einer Anlage."""
    gesamt_kg: float
    posten: list[GraueLastPosten]


def graue_last_einzeln(inv) -> tuple[float, str]:
    """Graue Herstellungs-Last (kg CO2) einer Investition + Quelle.

    Reihenfolge: Override (`graue_last_kg`) schlägt immer den Typ-Default.
    Für skalierende Typen (PV/Speicher) ohne Größe (kWp/kWh fehlt) ist die
    Last 0 mit Quelle `fehlt`, damit der Daten-Checker das als ERROR sichtbar
    machen kann statt still 0 zu unterstellen.
    """
    override = getattr(inv, "graue_last_kg", None)
    if override is not None:
        return float(override), QUELLE_OVERRIDE

    # Lazy-Import bricht den Zyklus calculations ↔ berechnungen (s. Modul-Kopf).
    from backend.core.calculations import (
        GRAUE_LAST_EAUTO_KG,
        GRAUE_LAST_PV_KG_PRO_KWP,
        GRAUE_LAST_SPEICHER_KG_PRO_KWH,
        GRAUE_LAST_WAERMEPUMPE_KG,
    )

    typ = getattr(inv, "typ", None)

    if typ in (InvestitionTyp.PV_MODULE.value, InvestitionTyp.BALKONKRAFTWERK.value):
        kwp = getattr(inv, "leistung_kwp", None) or 0
        if kwp <= 0:
            return 0.0, QUELLE_FEHLT
        return kwp * GRAUE_LAST_PV_KG_PRO_KWP, QUELLE_DEFAULT

    if typ == InvestitionTyp.SPEICHER.value:
        params = getattr(inv, "parameter", None) or {}
        kap = params.get(PARAM_SPEICHER["KAPAZITAET_KWH"], 0) or 0
        if kap <= 0:
            return 0.0, QUELLE_FEHLT
        return kap * GRAUE_LAST_SPEICHER_KG_PRO_KWH, QUELLE_DEFAULT

    if typ == InvestitionTyp.WAERMEPUMPE.value:
        return GRAUE_LAST_WAERMEPUMPE_KG, QUELLE_DEFAULT

    if typ == InvestitionTyp.E_AUTO.value:
        return GRAUE_LAST_EAUTO_KG, QUELLE_DEFAULT

    # Wallbox, Wechselrichter (in PV-kWp enthalten), Sonstiges: kein Richtwert.
    return 0.0, QUELLE_KEIN_DEFAULT


def _ist_beruecksichtigt(inv, stichtag: Optional[date]) -> bool:
    """Filtert Investitionen, deren graue Last in die Σ einfließt.

    - aktiv=False = wie gelöscht → nirgends ([[feedback_aktiv_inaktiv_semantik]]).
    - Dienstwagen-E-Autos raus ([[feedback_dienstwagen_alle_checks]]).
    - stichtag (optional): graue Last fällt bei Anschaffung an → nur Investitionen,
      die bis zum Stichtag angeschafft wurden. Ohne Stichtag: alle aktiven.
    """
    if getattr(inv, "aktiv", True) is False:
        return False

    if getattr(inv, "typ", None) == InvestitionTyp.E_AUTO.value and ist_dienstlich(inv):
        return False

    if stichtag is not None:
        anschaffung = getattr(inv, "anschaffungsdatum", None)
        if anschaffung is not None and anschaffung > stichtag:
            return False

    return True


def summe_graue_last(
    investitionen: list,
    stichtag: Optional[date] = None,
) -> GraueLastBericht:
    """Σ der grauen Herstellungs-Last (kg CO2) über die Investitionen einer Anlage.

    Args:
        investitionen: Investition-Objekte (mit typ, leistung_kwp, parameter,
            graue_last_kg, aktiv, anschaffungsdatum).
        stichtag: optionale Anschaffungs-Grenze; ohne = alle aktiven berücksichtigen.

    Returns:
        GraueLastBericht mit gesamt_kg + Posten-Aufschlüsselung.
    """
    posten: list[GraueLastPosten] = []
    gesamt = 0.0

    for inv in investitionen:
        if not _ist_beruecksichtigt(inv, stichtag):
            continue
        last, quelle = graue_last_einzeln(inv)
        posten.append(
            GraueLastPosten(
                investition_id=getattr(inv, "id", None),
                typ=getattr(inv, "typ", ""),
                bezeichnung=getattr(inv, "bezeichnung", ""),
                graue_last_kg=round(last, 1),
                quelle=quelle,
            )
        )
        gesamt += last

    return GraueLastBericht(gesamt_kg=round(gesamt, 1), posten=posten)
