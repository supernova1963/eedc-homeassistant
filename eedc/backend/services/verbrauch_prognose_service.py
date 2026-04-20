"""
Verbrauchsprognose-Service.

Berechnet ein typisches Stunden-Verbrauchsprofil aus historischen
TagesEnergieProfil-Daten für einen gegebenen Ziel-Tag.

Algorithmus:
  1. Ziel-Wochentag bestimmen (Werktag vs. Wochenende)
  2. Letzte 4–8 Wochen TagesEnergieProfil laden
  3. Fallback-Kaskade: gleicher Wochentag → Werktag/WE → alle Tage
  4. Gewichteter Mittelwert pro Stunde (jüngere Wochen stärker)
"""

import logging
from collections import defaultdict
from datetime import date, timedelta
from typing import Optional

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.tages_energie_profil import TagesEnergieProfil

logger = logging.getLogger(__name__)

# Mindestanzahl Tage für eine brauchbare Prognose
MIN_TAGE_GLEICHER_WT = 3   # z.B. 3 Montage
MIN_TAGE_TAGESTYP = 5      # z.B. 5 Werktage
MIN_TAGE_FALLBACK = 3      # 3 beliebige Tage

# Gewichtung: Alter in Tagen → Gewicht (exponentiell abfallend)
HALBWERTSZEIT_TAGE = 14.0


def _gewicht(alter_tage: int) -> float:
    """Exponentiell abfallendes Gewicht basierend auf Alter."""
    return 0.5 ** (alter_tage / HALBWERTSZEIT_TAGE)


def _ist_werktag(d: date) -> bool:
    return d.weekday() < 5


async def get_verbrauch_prognose(
    anlage_id: int,
    ziel_datum: date,
    db: AsyncSession,
    wochen_zurueck: int = 8,
) -> Optional[dict]:
    """
    Berechnet ein stündliches Verbrauchsprofil für den Ziel-Tag.

    Returns:
        dict mit:
          - stunden_kw: list[float] (24 Werte, kW pro Stunde)
          - basis: str ("gleicher_wochentag", "tagestyp", "alle")
          - daten_tage: int (Anzahl Tage die einflossen)
          - zeitraum_von: date
          - zeitraum_bis: date
        oder None wenn zu wenig Daten
    """
    von = ziel_datum - timedelta(weeks=wochen_zurueck)
    bis = ziel_datum - timedelta(days=1)  # Gestern als letzter Tag

    result = await db.execute(
        select(TagesEnergieProfil)
        .where(
            TagesEnergieProfil.anlage_id == anlage_id,
            TagesEnergieProfil.datum >= von,
            TagesEnergieProfil.datum <= bis,
            TagesEnergieProfil.verbrauch_kw.isnot(None),
        )
        .order_by(TagesEnergieProfil.datum, TagesEnergieProfil.stunde)
    )
    rows = result.scalars().all()

    if not rows:
        logger.warning("Keine Energieprofil-Daten für Anlage %d im Zeitraum %s–%s",
                        anlage_id, von, bis)
        return None

    ziel_wt = ziel_datum.weekday()
    ziel_ist_werktag = ziel_wt < 5

    # Gruppiere nach Datum → {datum: {stunde: verbrauch_kw}}
    tage: dict[date, dict[int, float]] = defaultdict(dict)
    for r in rows:
        tage[r.datum][r.stunde] = r.verbrauch_kw

    # Filtere nur Tage mit >= 20 Stunden (Qualitätsfilter)
    vollstaendige_tage = {d: stunden for d, stunden in tage.items() if len(stunden) >= 20}

    # Kaskade: 1) gleicher Wochentag, 2) gleicher Tagestyp, 3) alle
    gleicher_wt = {d: s for d, s in vollstaendige_tage.items() if d.weekday() == ziel_wt}
    gleicher_typ = {d: s for d, s in vollstaendige_tage.items()
                    if _ist_werktag(d) == ziel_ist_werktag}

    if len(gleicher_wt) >= MIN_TAGE_GLEICHER_WT:
        auswahl = gleicher_wt
        basis = "gleicher_wochentag"
    elif len(gleicher_typ) >= MIN_TAGE_TAGESTYP:
        auswahl = gleicher_typ
        basis = "tagestyp"
    elif len(vollstaendige_tage) >= MIN_TAGE_FALLBACK:
        auswahl = vollstaendige_tage
        basis = "alle"
    else:
        logger.info("Zu wenig Daten für Verbrauchsprognose Anlage %d: "
                     "%d vollständige Tage", anlage_id, len(vollstaendige_tage))
        return None

    # Gewichteter Mittelwert pro Stunde
    stunden_kw: list[float] = []
    for stunde in range(24):
        gewichtete_summe = 0.0
        gewicht_summe = 0.0
        for d, stunden_dict in auswahl.items():
            if stunde in stunden_dict:
                alter = (ziel_datum - d).days
                g = _gewicht(alter)
                gewichtete_summe += stunden_dict[stunde] * g
                gewicht_summe += g
        if gewicht_summe > 0:
            stunden_kw.append(round(gewichtete_summe / gewicht_summe, 3))
        else:
            stunden_kw.append(0.0)

    return {
        "stunden_kw": stunden_kw,
        "basis": basis,
        "daten_tage": len(auswahl),
        "zeitraum_von": von,
        "zeitraum_bis": bis,
    }
