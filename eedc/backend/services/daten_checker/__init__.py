"""
Daten-Checker Service.

Prüft Anlage-Daten systematisch auf Vollständigkeit und Plausibilität.
5 Prüfkategorien: Stammdaten, Strompreise, Investitionen,
Monatsdaten-Vollständigkeit, Monatsdaten-Plausibilität.

Tier-4 Achse C: Das frühere Einzelmodul `daten_checker.py` wurde in ein
Package aufgeteilt. Die Checks bleiben `self`-Methoden mit geteiltem
Instanz-State — der Split erfolgt über Mixin-Klassen je Themenfeld. Dieses
`__init__.py` re-exportiert `DatenChecker` (und die Enums/Dataclasses), damit
`from backend.services.daten_checker import DatenChecker` unverändert
funktioniert (einziger Consumer: api/routes/daten_checker.py).
"""

from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from backend.models.anlage import Anlage
from backend.models.monatsdaten import Monatsdaten
from backend.models.investition import Investition
from backend.models.pvgis_prognose import PVGISPrognose

from .kategorien import (
    CheckSeverity,
    CheckKategorie,
    CheckErgebnis,
    MonatsdatenAbdeckung,
    DatenCheckResult,
)
from ._helpers import _CheckHelpers
from .stammdaten import StammdatenChecks
from .monatsdaten import MonatsdatenChecks
from .energieprofil import EnergieprofilChecks
from .sensoren import SensorChecks
from .emob import EmobChecks
from .datenquelle import DatenquelleChecks


# ─── Service ─────────────────────────────────────────────────────────────────

class DatenChecker(
    StammdatenChecks,
    MonatsdatenChecks,
    EnergieprofilChecks,
    SensorChecks,
    EmobChecks,
    DatenquelleChecks,
    _CheckHelpers,
):
    """Prüft alle Daten einer Anlage auf Vollständigkeit und Plausibilität."""

    def __init__(self, db):
        self.db = db
        self._abdeckung: Optional[MonatsdatenAbdeckung] = None

    async def check_anlage(self, anlage_id: int) -> DatenCheckResult:
        """Führt alle Prüfungen für eine Anlage durch."""
        # Anlage mit Beziehungen laden
        result = await self.db.execute(
            select(Anlage)
            .options(
                selectinload(Anlage.investitionen).selectinload(Investition.monatsdaten),
                selectinload(Anlage.strompreise),
            )
            .where(Anlage.id == anlage_id)
        )
        anlage = result.scalar_one_or_none()
        if not anlage:
            raise ValueError(f"Anlage {anlage_id} nicht gefunden")

        # Monatsdaten separat laden (nicht über Relationship)
        md_result = await self.db.execute(
            select(Monatsdaten)
            .where(Monatsdaten.anlage_id == anlage_id)
            .order_by(Monatsdaten.jahr, Monatsdaten.monat)
        )
        monatsdaten = list(md_result.scalars().all())

        # Aktive PVGIS-Prognose laden (für Plausibilitätsprüfung)
        pvgis_result = await self.db.execute(
            select(PVGISPrognose)
            .where(PVGISPrognose.anlage_id == anlage_id, PVGISPrognose.ist_aktiv == True)
        )
        pvgis_prognose = pvgis_result.scalar_one_or_none()

        # PV-Erzeugung und PVGIS-Lookup vorab berechnen (wird mehrfach benötigt)
        pv_erzeugung_map = self._get_pv_erzeugung_map(anlage)
        pvgis_monat_map = self._get_pvgis_monat_map(pvgis_prognose)
        pr, pr_count = self._calculate_performance_ratio(
            pv_erzeugung_map, pvgis_monat_map, monatsdaten
        )

        # Alle Prüfungen durchführen
        ergebnisse: list[CheckErgebnis] = []
        ergebnisse.extend(self._check_stammdaten(anlage, pvgis_prognose, pr, pr_count))
        ergebnisse.extend(self._check_strompreise(anlage))
        ergebnisse.extend(self._check_investitionen(anlage, monatsdaten))
        ergebnisse.extend(self._check_monatsdaten_vollstaendigkeit(anlage, monatsdaten))
        ergebnisse.extend(self._check_monatsdaten_plausibilitaet(
            anlage, monatsdaten, pvgis_prognose, pv_erzeugung_map, pvgis_monat_map, pr, pr_count
        ))
        ergebnisse.extend(self._check_energieprofil_abdeckung(anlage, monatsdaten))
        ergebnisse.extend(await self._check_energieprofil_plausibilitaet(anlage))
        ergebnisse.extend(await self._check_mqtt_topic_abdeckung(anlage))
        ergebnisse.extend(await self._check_sensor_mapping_lts(anlage))
        ergebnisse.extend(await self._check_sensor_mapping_einheit(anlage))
        ergebnisse.extend(await self._check_provenance_conflicts(anlage))
        ergebnisse.extend(await self._check_datenquelle_status(anlage))
        ergebnisse.extend(await self._check_datenquelle_drift(anlage))
        ergebnisse.extend(await self._check_pv_ueber_erfassung(anlage))
        ergebnisse.extend(self._check_emob_pool_pflege(anlage))
        ergebnisse.extend(self._check_emob_sensor_doppelmapping(anlage))

        # Zusammenfassung
        zusammenfassung = {"error": 0, "warning": 0, "info": 0, "ok": 0}
        for e in ergebnisse:
            zusammenfassung[e.schwere] += 1

        return DatenCheckResult(
            anlage_id=anlage.id,
            anlage_name=anlage.anlagenname,
            ergebnisse=ergebnisse,
            zusammenfassung=zusammenfassung,
            monatsdaten_abdeckung=self._abdeckung,
        )


__all__ = [
    "DatenChecker",
    "CheckSeverity",
    "CheckKategorie",
    "CheckErgebnis",
    "MonatsdatenAbdeckung",
    "DatenCheckResult",
]
