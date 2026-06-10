"""5-Minuten-Aggregat-Helfer für die Live-Tagesverlauf-Kurve (Berechnungs-Layer, ADR-001).

Reine, DB-freie Umrechnung der `statistics_short_term`-Bausteine in
Leistungs-Punkte für die Butterfly-Kurve. Die DB-Roh-Abfrage (Boundary →
5-Min-kWh-Delta bzw. `mean`) liegt in
`ha_statistics_service.get_short_term_5min_for_day`; **hier** lebt nur die
deterministische Konvertierung — so ist sie ohne HA-DB unit-testbar.

Hintergrund (Live-Tagesverlauf-HA-LTS-Konsistenz, #135-Folge): die Kurve soll
im Add-on-Modus aus derselben SoT-Familie wie die Heute-kWh-Kacheln
(`safe_get_tages_kwh`) kommen. Für einen kWh-Zähler gilt dann exakt
``Σ Kurven-Slot-Energie == Tages-Zähler-Delta``, weil jede 5-Min-Slot-Leistung
aus genau dem Zähler-Delta dieses Intervalls rekonstruiert wird.

Punkte werden am **Slot-Beginn** ``t`` emittiert (Intervall ``[t, t+5min)``).
Das 10-Min-Slot-Raster der Kurve (`h_start <= p < h_end`) fängt damit pro
10-Min-Fenster genau die zwei 5-Min-Punkte ein; deren Mittel ist die korrekte
10-Min-Leistung, und ``Mittel * 10/60 h == ΔkWh₁ + ΔkWh₂``.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

# 5-Min-Slot. kWh über 5 Min → mittlere Leistung in W:
#   P[W] = ΔkWh / (5/60 h) * 1000 = ΔkWh * 12000.
SLOT_MINUTEN = 5
_KWH_PRO_SLOT_ZU_W = 1000.0 / (SLOT_MINUTEN / 60.0)  # = 12000.0


def counter_deltas_zu_leistung(
    kwh_deltas: dict[datetime, Optional[float]],
) -> list[tuple[datetime, float]]:
    """5-Min-kWh-Deltas eines Zählers → Leistungs-Punkte (W) am Slot-Beginn.

    ``P[W] = ΔkWh * 12000`` (mittlere Leistung über das 5-Min-Intervall).

    Negative oder ``None``-Deltas (Counter-Reset / Recompile-Lücke / fehlende
    Boundary) werden **übersprungen** — der Slot fällt damit auf die
    Nachbar-Mittelung bzw. (wenn die ganze Serie leer bleibt) auf den
    History-Pfad zurück. `sum` ist HAs reset-bereinigte Lifetime-Summe, daher
    sollte ein negatives Delta nur bei Recompile-Artefakten auftreten
    ([[feedback_ha_statistics_aggregation]] — Tagesreset-Falle).
    """
    punkte: list[tuple[datetime, float]] = []
    for t, delta in sorted(kwh_deltas.items()):
        if delta is None or delta < 0:
            continue
        punkte.append((t, delta * _KWH_PRO_SLOT_ZU_W))
    return punkte


def means_zu_leistung(
    means: dict[datetime, Optional[float]],
    faktor_w: float,
) -> list[tuple[datetime, float]]:
    """`statistics_short_term.mean`-Werte eines Power-Sensors → W-Punkte am Slot-Beginn.

    Der Mean steht in der Statistics-Einheit (`unit_of_measurement` aus
    `statistics_meta`, i. d. R. W/kW); der Aufrufer löst den `UNIT_TO_W`-Faktor
    auf (SoT in `live_sensor_config`) und reicht ihn als `faktor_w` herein —
    so bleibt dieser Layer dependency-frei. Unbekannte Einheiten → Faktor 1.0.
    """
    return [(t, v * faktor_w) for t, v in sorted(means.items()) if v is not None]
