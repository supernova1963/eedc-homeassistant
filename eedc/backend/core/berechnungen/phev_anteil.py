"""Wie viel der Fahrleistung elektrisch war — und wie viel der Verbrenner fuhr.

Single Source of Truth für die Aufteilung der Kilometer eines Plug-in-Hybrids
(#331, ``KONZEPT-WALLBOX-EAUTO.md`` Phase 4). Beide Rechenachsen des Projekts
rufen **dieselbe** Funktion:

===============================  ==========================================
Achse                            Ort
===============================  ==========================================
IST (Vergangenheit)              ``services/eauto_wirtschaftlichkeit.py``
Prognose/ROI (Zukunft)           ``core/calculations.py``
===============================  ==========================================

Ein Anteil, der nur in einer der beiden wirkt, ist die Drift-Klasse, die dieses
Projekt wiederholt getroffen hat ([[feedback_aggregations_drift]]) — deshalb
liegt die Aufteilung hier und nicht an den beiden Fundstellen.

**Die Reihenfolge der Wege ist die Aussage** (Entscheidung 1 und 4 des
Konzepts): gemessen schlägt geschätzt, und wo beides fehlt, bleibt das heutige
Verhalten stehen.

1. **Gemessen** — aus dem elektrischen Fahrverbrauch:
   ``km_elektrisch = fahrverbrauch_kwh / verbrauch_kwh_100km × 100``
2. **Geschätzt** — aus dem gepflegten ``elektrischer_fahranteil_prozent``.
3. **Nichts gepflegt** — 100 % elektrisch, exakt wie vor #331.

⚠ **Die Deckelung auf ``km_gefahren`` ist nicht kosmetisch.** Ist
``verbrauch_kwh_100km`` zu niedrig gepflegt oder der Fahrverbrauchs-Zähler zu
großzügig, kommt rechnerisch mehr elektrische Strecke heraus als überhaupt
gefahren wurde. Ohne Deckelung entstünden **negative Verbrenner-Kilometer** und
damit eine Ersparnis, die größer ist als die Wahrheit. Gedeckelt bleibt der
Fehler sichtbar (Verbrenner-Anteil 0) statt sich in einen Gewinn zu verwandeln.

⚠ **``fahrverbrauch_kwh`` ist der EXPLIZITE Wert, nie ``get_eauto_ladung_kwh``.**
Das E-Auto-Feld ``verbrauch_kwh`` ist doppelt belegt (Fahrverbrauch ∧
Legacy-Heimladung, Schwäche A des Konzepts) — der Ladungs-Leser fällt bewusst
auf dieses Feld zurück. Wer ihn hier benutzte, läse eine **Heimladung** als
Fahrverbrauch und bekäme einen elektrischen Anteil, den niemand gefahren ist.
Der Aufrufer übergibt deshalb den Fahrverbrauch, nicht die Ladung.
"""

from dataclasses import dataclass
from typing import Final, Optional

#: Fahrleistung, unterhalb derer eine Aufteilung sinnlos ist (Division/Rauschen).
_KM_EPSILON: Final[float] = 0.0


@dataclass(frozen=True)
class FahrleistungsAnteil:
    """Aufgeteilte Fahrleistung eines Zeitraums.

    ``km_elektrisch + km_verbrenner == km_gefahren`` gilt immer — die Deckelung
    verschiebt nur, wo die Kilometer landen, sie wirft keine weg.

    ``quelle`` benennt den Weg, über den der elektrische Anteil bestimmt wurde
    (``"gemessen"`` · ``"prozent"`` · ``"unbestimmt"``). Sie ist keine
    Diagnose-Zierde: der Daten-Checker unterscheidet daran, ob eedc still 100 %
    elektrisch rechnet, obwohl ein Verbrenner-Verbrauch gepflegt ist.
    """

    km_elektrisch: float
    km_verbrenner: float
    quelle: str

    @property
    def km_gesamt(self) -> float:
        return self.km_elektrisch + self.km_verbrenner


def teile_fahrleistung(
    *,
    km_gefahren: float,
    fahrverbrauch_kwh: Optional[float] = None,
    verbrauch_kwh_100km: Optional[float] = None,
    anteil_prozent: Optional[float] = None,
) -> FahrleistungsAnteil:
    """Teilt die Fahrleistung in elektrisch und verbrennergefahren auf.

    Args:
        km_gefahren: Kilometer des Zeitraums (IST) bzw. des Jahres (Prognose).
        fahrverbrauch_kwh: **Explizit** gepflegter elektrischer Fahrverbrauch
            desselben Zeitraums. ``None``/0 ⇒ Weg 1 entfällt.
        verbrauch_kwh_100km: Fahrzeug-Kennwert (``PARAM_E_AUTO``). Fehlt oder
            ist er 0, entfällt Weg 1 ebenfalls — ohne ihn ist der Fahrverbrauch
            nicht in Kilometer übersetzbar.
        anteil_prozent: Gepflegter elektrischer Fahranteil in Prozent (0–100).
            Wird auf diesen Bereich geklemmt; ``None`` ⇒ Weg 2 entfällt.

    Returns:
        FahrleistungsAnteil mit ``quelle``.
    """
    if km_gefahren <= _KM_EPSILON:
        return FahrleistungsAnteil(0.0, 0.0, "unbestimmt")

    # Weg 1 — gemessen. Beide Größen müssen echt vorliegen; ein fehlender
    # Kennwert macht den Fahrverbrauch nicht in km übersetzbar.
    if (
        fahrverbrauch_kwh is not None
        and fahrverbrauch_kwh > 0
        and verbrauch_kwh_100km is not None
        and verbrauch_kwh_100km > 0
    ):
        km_e = min(km_gefahren, fahrverbrauch_kwh / verbrauch_kwh_100km * 100)
        return FahrleistungsAnteil(km_e, km_gefahren - km_e, "gemessen")

    # Weg 2 — geschätzt aus dem gepflegten Prozentwert. Kein Zahlen-Default:
    # ein erfundener Mittelwert wäre eine Behauptung über ein fremdes Fahrzeug.
    if anteil_prozent is not None:
        anteil = max(0.0, min(100.0, float(anteil_prozent)))
        km_e = km_gefahren * anteil / 100
        return FahrleistungsAnteil(km_e, km_gefahren - km_e, "prozent")

    # Weg 3 — nichts gepflegt: heutiges Verhalten, unverändert.
    return FahrleistungsAnteil(km_gefahren, 0.0, "unbestimmt")
