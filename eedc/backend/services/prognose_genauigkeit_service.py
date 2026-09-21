"""Der mittlere Prognosefehler der letzten N Tage — als Zahl, nicht als Antwort.

Die Auswertung *Prognosen → Genauigkeit* liefert diese Größe seit jeher, aber
nur als Teil einer Route (``api/routes/prognosen.py::get_prognosen_genauigkeit``
mit Wettersymbolen, Ausreißerzählung und drei Quellen). Die Abweichungs-Ampel
des HA-Exports (S3/P6) braucht **nur** den mittleren Fehler der eedc-Quelle und
braucht ihn im Export-Pfad. Dieser Dienst holt genau ihn; gerechnet wird im
Layer (``core/berechnungen/prognose_genauigkeit.py``), damit beide Sichten
dieselbe Zahl nennen.

⚠ **Die eedc-Quelle ist OpenMeteo × Lernfaktor** — derselbe Weg wie in der
Auswertung (``_get_lernfaktor(quelle="openmeteo")``). Ohne Lernfaktor gibt es
keine eedc-Reihe und damit **keine Schwelle**; dann entsteht auch kein
Ampel-Sensor (ADR-002/P4).
"""

from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Optional

from sqlalchemy import select

from backend.core.berechnungen import summe_pv_bkw_kwh
from backend.core.berechnungen.prognose_genauigkeit import (
    mae_prozent,
    relativer_tagesfehler_prozent,
)
from backend.models.tages_energie_profil import TagesZusammenfassung

logger = logging.getLogger(__name__)


async def eedc_mae_prozent(
    db, anlage_id: int, *, heute: date, tage: int = 30
) -> tuple[Optional[float], int]:
    """``(MAE in %, Anzahl ausgewerteter Tage)`` der eedc-Prognose.

    ``heute`` ist ein **Parameter** und kein ``date.today()`` in dieser
    Funktion — dasselbe Muster wie ``grundlast_sensorwert``: sonst müsste jede
    Probe die Prozessuhr lesen und auf die Stunde ihres Laufs wetten (N-167).

    Returns:
        ``(None, 0)``, wenn kein Lernfaktor vorliegt oder kein Tag eine
        brauchbare Grundlage hat.
    """
    try:
        from backend.api.routes.live_wetter import _get_lernfaktor

        lernfaktor = await _get_lernfaktor(anlage_id, db, quelle="openmeteo")
        if lernfaktor is None:
            return None, 0

        von = heute - timedelta(days=tage)
        res = await db.execute(
            select(TagesZusammenfassung).where(
                TagesZusammenfassung.anlage_id == anlage_id,
                TagesZusammenfassung.datum >= von,
                TagesZusammenfassung.datum < heute,
            )
        )
        fehler: list[float] = []
        for tz in res.scalars().all():
            ist = summe_pv_bkw_kwh(tz.komponenten_kwh) if tz.komponenten_kwh else None
            # Prognose-Kanon §6: der konvergenz-gefrorene Wert hat Vorrang —
            # dieselbe Vorrangregel wie in der Auswertung, damit die Schwelle
            # nicht aus einem Mid-Correction-Snapshot entsteht.
            roh = (
                tz.pv_prognose_final_kwh
                if tz.pv_prognose_final_kwh is not None
                else tz.pv_prognose_kwh
            )
            eedc = roh * lernfaktor if roh and roh > 0 else None
            abweichung = relativer_tagesfehler_prozent(eedc, ist)
            if abweichung is not None:
                fehler.append(abweichung)

        return mae_prozent(fehler), len(fehler)
    except Exception as e:  # der Export darf an der Genauigkeit nicht sterben
        logger.warning(
            "MAE-Ermittlung fehlgeschlagen (Anlage %s): %s: %s",
            anlage_id, type(e).__name__, e,
        )
        return None, 0
