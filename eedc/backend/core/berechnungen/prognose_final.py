"""Konvergenz-Freeze des Genauigkeits-Tracking-Endwerts (Prognose-Kanon §6).

Reine Mathematik (ADR-001) — keine DB/IO. Der **Anzeige**-Wert der
PV-Tagesprognose bleibt rollend (folgt OpenMeteo intraday). Davon getrennt
trägt das Genauigkeits-Tracking einen eigenen Endwert
(``TagesZusammenfassung.pv_prognose_final_kwh``), der mitrollt, **bis** der
OpenMeteo-Tageswert für das Datum konvergiert ist — und dann eingefroren wird
(``pv_prognose_final_at``).

Drei-Größen-Modell (Bau-Vertrag ``KONZEPT-PROGNOSE-KANON.md`` §1):

* Anzeige (rollend)        → ``pv_prognose_kwh`` (Overwrite)
* Lern-Snapshot (gefroren) → ``pv_prognose_stundenprofil`` (first-write-wins)
* Tracking-Endwert (hier)  → ``pv_prognose_final_kwh`` (konvergenz-gefroren)

Konvergenz-Kriterium (abgenommen): **nach Sonnenuntergang** ist der
OpenMeteo-Tageswert faktisch fix (keine Sonne mehr → keine Forecast-Drift),
also gilt der Tag als konvergiert. Liegt zusätzlich ein OpenMeteo-**Archiv**-
Tageswert vor, wird strenger geprüft (``|forecast − archiv| ≤ ε``); ohne
Archiv genügt „Sonne unter" (der Anzeigewert rollt bis dahin ohnehin weiter).
"""

from __future__ import annotations

from typing import Optional

# Toleranz für den optionalen Archiv-Abgleich. Absolut (kWh) ODER relativ —
# es gilt die jeweils großzügigere Grenze, damit kleine Anlagen nicht an einer
# starren kWh-Schwelle hängen bleiben und große nicht an einer starren %-Schwelle.
DEFAULT_EPSILON_KWH = 0.5
DEFAULT_EPSILON_REL = 0.02  # 2 % vom Tageswert


def soll_final_einfrieren(
    *,
    forecast_kwh: Optional[float],
    sonne_unter: bool,
    archiv_kwh: Optional[float] = None,
    epsilon_kwh: float = DEFAULT_EPSILON_KWH,
    epsilon_rel: float = DEFAULT_EPSILON_REL,
) -> bool:
    """Soll der Tracking-Endwert jetzt eingefroren werden?

    Args:
        forecast_kwh: aktueller (rollender) Prognose-Tageswert. ``None`` →
            nie einfrieren (es gibt nichts zu fixieren).
        sonne_unter: True, wenn der Tag (für die Anlage) vorbei ist — Datum
            in der Vergangenheit ODER heute nach Sonnenuntergang. Vorher rollt
            der Wert immer weiter (kein Freeze).
        archiv_kwh: optionaler OpenMeteo-Archiv-Tageswert für strengeren
            Abgleich. ``None`` → Freeze allein auf Basis ``sonne_unter``.
        epsilon_kwh / epsilon_rel: Toleranz für den Archiv-Abgleich.

    Returns:
        True → ``pv_prognose_final_at`` setzen und Wert fixieren.
    """
    if forecast_kwh is None or not sonne_unter:
        return False
    if archiv_kwh is None:
        # Kein Archiv abrufbar (z. B. innerhalb des OM-Archiv-Lags): nach
        # Sonnenuntergang ist der Tages-OM-Wert fix → einfrieren.
        return True
    grenze = max(epsilon_kwh, abs(archiv_kwh) * epsilon_rel)
    return abs(forecast_kwh - archiv_kwh) <= grenze
