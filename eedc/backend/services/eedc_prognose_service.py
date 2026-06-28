"""eedc-eigene PV-Prognose — dünner Adapter über den Prognose-Kanon.

Seit dem Prognose-Kanon-Fix (V3, „ein Wert überall") ist dieser Service nur
noch eine **stabile Fassade** über ``services/prognose_kanon.py``: Signatur
und Rückgabe (``EedcPrognose``/``EedcPrognoseTag``) bleiben für die
Bestandskonsumenten unverändert, die Mathematik (Multi-String-Fan-out +
eedc-Korrektur PRO ENERGIE-SLOT, Tageswert = Σ Export-Slots) liegt im Kanon.

So zeigen **alle** Pfade per Konstruktion denselben Tageswert — der Live-Pfad
(``live_wetter``), MQTT (``ha_export_prognose``) und die „eedc"-Spalte im
Prognosen-Vergleich (``api/routes/prognosen``) ziehen denselben Kanon
([[feedback_aggregator_symmetrie]] — Symmetrie-Test in
``tests/test_prognose_kanon.py`` + ``tests/test_eedc_prognose_kaskade.py``).

Konsumenten:
  - ``services/ha_export_prognose.py`` — HA-Export-Sensoren #150
  - ``api/routes/prognosen.py`` — Spalte „eedc" im Prognosen-Vergleich
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

from backend.core.berechnungen.prognose_korrektur import KorrigiertesTagesprofil
from backend.services.prognose_kanon import kanon_tagesprognose

logger = logging.getLogger(__name__)


@dataclass
class EedcPrognoseTag:
    """eedc-Prognose eines Tages (Offset ab heute)."""

    datum: str
    # Korrigiertes Stundenprofil; None wenn keine Stunden-Basis vorliegt
    # (z. B. OpenMeteo-Tagessummen-Schätzpfad ohne Hourly-Daten).
    profil: Optional[KorrigiertesTagesprofil]
    # Tageswert: aus dem Profil (= Σ Export-Slots) oder — ohne Stunden-Basis —
    # Tages-Ertrag × Skalar-Fallback (bisheriges Verhalten).
    tageswert_kwh: Optional[float]


@dataclass
class EedcPrognose:
    """eedc-Prognose über mehrere Tage. ``tage[i]`` = heute + i Tage."""

    tage: list[Optional[EedcPrognoseTag]]
    skalar_fallback: Optional[float]  # Legacy-Lernfaktor (Diagnose/Fallback)


async def berechne_eedc_prognose(
    db,
    anlage,
    days: int = 4,
    skip_jitter: bool = False,
) -> Optional[EedcPrognose]:
    """Berechnet die kaskaden-korrigierte eedc-Prognose einer Anlage.

    Quellen-Regel #150: IMMER nur die eedc-eigene Prognose (OpenMeteo-Basis),
    nie Solcast/SFML — unabhängig von der gewählten Anzeige-Quelle.

    Dünne Fassade über ``kanon_tagesprognose`` (Multi-String + eedc-Korrektur
    pro Slot). Mappt den Kanon auf die stabile ``EedcPrognose``-Form für die
    Bestandskonsumenten. ``None`` bei fehlenden Koordinaten / PV / OpenMeteo.
    """
    kanon = await kanon_tagesprognose(db, anlage, days=days, skip_jitter=skip_jitter)
    if kanon is None:
        return None

    tage: list[Optional[EedcPrognoseTag]] = [
        None if kt is None else EedcPrognoseTag(
            datum=kt.datum, profil=kt.profil, tageswert_kwh=kt.eedc_kwh,
        )
        for kt in kanon.tage
    ]
    return EedcPrognose(tage=tage, skalar_fallback=kanon.skalar_fallback)
