"""
Vorschlag-Service für Monatsabschluss-Wizard.

Generiert intelligente Vorschläge für Monatsdaten basierend auf verschiedenen Quellen:
- Vormonat
- Vorjahr gleicher Monat
- Durchschnitt der letzten 12 Monate
- Berechnungen (COP, kWp-Verteilung)
- Investition-Parameter
"""

from datetime import date
from typing import Optional, Any
from dataclasses import dataclass
from enum import Enum

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_

from backend.models.monatsdaten import Monatsdaten
from backend.models.investition import Investition, InvestitionMonatsdaten


class VorschlagQuelle(str, Enum):
    """Quelle eines Vorschlags."""
    HA_SENSOR = "ha_sensor"        # Aus HA-Sensor (MQTT)
    CRON_SNAPSHOT = "cron_snapshot"  # Vom Monatswechsel-Job
    VORMONAT = "vormonat"          # Letzter Monat
    VORJAHR = "vorjahr"            # Gleicher Monat Vorjahr
    BERECHNUNG = "berechnung"      # Berechnet (COP, kWp, etc.)
    DURCHSCHNITT = "durchschnitt"  # Ø letzte 12 Monate
    PARAMETER = "parameter"        # Aus Investition-Parametern


@dataclass
class Vorschlag:
    """Ein Vorschlag für einen Feldwert."""
    wert: float
    quelle: VorschlagQuelle
    konfidenz: int  # 0-100
    beschreibung: str
    details: Optional[dict] = None


@dataclass
class PlausibilitaetsWarnung:
    """Eine Plausibilitätswarnung."""
    typ: str  # negativ, zu_hoch, zu_niedrig, sensor_unavailable
    schwere: str  # error, warning, info
    meldung: str
    details: Optional[dict] = None


class VorschlagService:
    """Generiert intelligente Vorschläge für Monatsdaten."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_vorschlaege(
        self,
        anlage_id: int,
        feld: str,
        jahr: int,
        monat: int,
        investition_id: Optional[int] = None,
    ) -> list[Vorschlag]:
        """
        Generiert Vorschläge für ein Feld.

        Args:
            anlage_id: ID der Anlage
            feld: Feldname (z.B. "einspeisung_kwh", "pv_erzeugung_kwh")
            jahr: Jahr
            monat: Monat
            investition_id: Optional - ID der Investition

        Returns:
            Liste von Vorschlägen, sortiert nach Konfidenz
        """
        vorschlaege: list[Vorschlag] = []

        # 1. Vormonat
        vormonat = await self._get_vormonat_wert(
            anlage_id, feld, jahr, monat, investition_id
        )
        if vormonat is not None:
            vorschlaege.append(Vorschlag(
                wert=vormonat,
                quelle=VorschlagQuelle.VORMONAT,
                konfidenz=80,
                beschreibung=f"Wert vom Vormonat",
            ))

        # 2. Vorjahr gleicher Monat
        vorjahr = await self._get_vorjahr_wert(
            anlage_id, feld, jahr, monat, investition_id
        )
        if vorjahr is not None:
            vorschlaege.append(Vorschlag(
                wert=vorjahr,
                quelle=VorschlagQuelle.VORJAHR,
                konfidenz=70,
                beschreibung=f"Wert vom {monat:02d}/{jahr-1}",
            ))

        # 3. Durchschnitt letzte 12 Monate
        durchschnitt = await self._get_durchschnitt(
            anlage_id, feld, jahr, monat, investition_id
        )
        if durchschnitt is not None:
            vorschlaege.append(Vorschlag(
                wert=durchschnitt,
                quelle=VorschlagQuelle.DURCHSCHNITT,
                konfidenz=50,
                beschreibung="Ø letzte 12 Monate",
            ))

        # 4. Berechnungen für spezielle Felder
        if investition_id:
            berechnungen = await self._get_berechnete_werte(
                anlage_id, feld, jahr, monat, investition_id
            )
            vorschlaege.extend(berechnungen)

        # Nach Konfidenz sortieren
        vorschlaege.sort(key=lambda v: v.konfidenz, reverse=True)

        return vorschlaege

    async def _get_vormonat_wert(
        self,
        anlage_id: int,
        feld: str,
        jahr: int,
        monat: int,
        investition_id: Optional[int],
    ) -> Optional[float]:
        """Holt Wert vom Vormonat."""
        # Vormonat berechnen
        if monat == 1:
            vm_jahr, vm_monat = jahr - 1, 12
        else:
            vm_jahr, vm_monat = jahr, monat - 1

        return await self._get_feld_wert(
            anlage_id, feld, vm_jahr, vm_monat, investition_id
        )

    async def _get_vorjahr_wert(
        self,
        anlage_id: int,
        feld: str,
        jahr: int,
        monat: int,
        investition_id: Optional[int],
    ) -> Optional[float]:
        """Holt Wert vom gleichen Monat im Vorjahr."""
        return await self._get_feld_wert(
            anlage_id, feld, jahr - 1, monat, investition_id
        )

    async def _get_durchschnitt(
        self,
        anlage_id: int,
        feld: str,
        jahr: int,
        monat: int,
        investition_id: Optional[int],
    ) -> Optional[float]:
        """Berechnet Durchschnitt der letzten 12 Monate."""
        werte: list[float] = []

        # 12 Monate zurückgehen
        current_jahr, current_monat = jahr, monat
        for _ in range(12):
            # Einen Monat zurück
            if current_monat == 1:
                current_jahr -= 1
                current_monat = 12
            else:
                current_monat -= 1

            wert = await self._get_feld_wert(
                anlage_id, feld, current_jahr, current_monat, investition_id
            )
            if wert is not None:
                werte.append(wert)

        if len(werte) >= 3:  # Mindestens 3 Werte für sinnvollen Durchschnitt
            return round(sum(werte) / len(werte), 2)
        return None

    async def _get_feld_wert(
        self,
        anlage_id: int,
        feld: str,
        jahr: int,
        monat: int,
        investition_id: Optional[int],
    ) -> Optional[float]:
        """Holt einen einzelnen Feldwert aus der DB."""
        if investition_id:
            # InvestitionMonatsdaten
            result = await self.db.execute(
                select(InvestitionMonatsdaten)
                .where(and_(
                    InvestitionMonatsdaten.investition_id == investition_id,
                    InvestitionMonatsdaten.jahr == jahr,
                    InvestitionMonatsdaten.monat == monat,
                ))
            )
            imd = result.scalar_one_or_none()
            if imd and imd.verbrauch_daten:
                return imd.verbrauch_daten.get(feld)
        else:
            # Monatsdaten
            result = await self.db.execute(
                select(Monatsdaten)
                .where(and_(
                    Monatsdaten.anlage_id == anlage_id,
                    Monatsdaten.jahr == jahr,
                    Monatsdaten.monat == monat,
                ))
            )
            md = result.scalar_one_or_none()
            if md:
                return getattr(md, feld, None)

        return None

    async def _get_berechnete_werte(
        self,
        anlage_id: int,
        feld: str,
        jahr: int,
        monat: int,
        investition_id: int,
    ) -> list[Vorschlag]:
        """Generiert berechnete Vorschläge basierend auf Investitions-Parametern."""
        vorschlaege: list[Vorschlag] = []

        # Investition laden
        result = await self.db.execute(
            select(Investition).where(Investition.id == investition_id)
        )
        inv = result.scalar_one_or_none()
        if not inv:
            return vorschlaege

        params = inv.parameter or {}

        # Wärmepumpe: Heiz-/Warmwasserenergie aus COP berechnen
        if inv.typ == "waermepumpe" and feld in ["heizenergie_kwh", "warmwasser_kwh"]:
            # Stromverbrauch ermitteln
            strom = await self._get_feld_wert(
                anlage_id, "stromverbrauch_kwh", jahr, monat, investition_id
            )
            if strom is not None:
                # Effizienz-Modus prüfen
                modus = params.get("effizienz_modus", "gesamt_jaz")

                cop = None
                if modus == "gesamt_jaz":
                    cop = params.get("jaz")
                elif modus == "scop":
                    if feld == "heizenergie_kwh":
                        cop = params.get("scop_heizung")
                    else:
                        cop = params.get("scop_warmwasser")
                elif modus == "getrennte_cops":
                    if feld == "heizenergie_kwh":
                        cop = params.get("cop_heizung")
                    else:
                        cop = params.get("cop_warmwasser")

                if cop:
                    berechneter_wert = round(strom * cop, 1)
                    vorschlaege.append(Vorschlag(
                        wert=berechneter_wert,
                        quelle=VorschlagQuelle.BERECHNUNG,
                        konfidenz=60,
                        beschreibung=f"Berechnet: {strom:.0f} kWh × COP {cop}",
                        details={"stromverbrauch": strom, "cop": cop}
                    ))

        # E-Auto: km aus Jahresfahrleistung
        if inv.typ == "e-auto" and feld == "km_gefahren":
            jahresfahrleistung = params.get("jahresfahrleistung_km")
            if jahresfahrleistung:
                monats_km = round(jahresfahrleistung / 12, 0)
                vorschlaege.append(Vorschlag(
                    wert=monats_km,
                    quelle=VorschlagQuelle.PARAMETER,
                    konfidenz=30,
                    beschreibung=f"Aus Jahresfahrleistung: {jahresfahrleistung:.0f} km ÷ 12",
                    details={"jahresfahrleistung": jahresfahrleistung}
                ))

        return vorschlaege

    async def pruefe_plausibilitaet(
        self,
        anlage_id: int,
        feld: str,
        wert: float,
        jahr: int,
        monat: int,
        investition_id: Optional[int] = None,
    ) -> list[PlausibilitaetsWarnung]:
        """
        Prüft einen Wert auf Plausibilität.

        Args:
            anlage_id: ID der Anlage
            feld: Feldname
            wert: Zu prüfender Wert
            jahr: Jahr
            monat: Monat
            investition_id: Optional - ID der Investition

        Returns:
            Liste von Warnungen
        """
        warnungen: list[PlausibilitaetsWarnung] = []

        # 1. Negativwert prüfen (für Energiezähler)
        if wert < 0 and feld.endswith("_kwh"):
            warnungen.append(PlausibilitaetsWarnung(
                typ="negativ",
                schwere="error",
                meldung="Wert darf nicht negativ sein (Zähler kann nicht rückwärts laufen)",
            ))

        # 2. Vergleich mit Vorjahr
        vorjahr = await self._get_vorjahr_wert(
            anlage_id, feld, jahr, monat, investition_id
        )
        if vorjahr and vorjahr > 0:
            abweichung = (wert - vorjahr) / vorjahr * 100
            if abweichung > 100:  # Mehr als doppelt so viel
                warnungen.append(PlausibilitaetsWarnung(
                    typ="zu_hoch",
                    schwere="warning",
                    meldung=f"Deutlich höher als Vorjahr (+{abweichung:.0f}%)",
                    details={"vorjahr_wert": vorjahr, "abweichung_prozent": abweichung}
                ))
            elif abweichung < -50:  # Weniger als halb so viel
                warnungen.append(PlausibilitaetsWarnung(
                    typ="zu_niedrig",
                    schwere="warning",
                    meldung=f"Deutlich niedriger als Vorjahr ({abweichung:.0f}%)",
                    details={"vorjahr_wert": vorjahr, "abweichung_prozent": abweichung}
                ))

        # 3. Null-Wert bei üblicherweise gefüllten Feldern
        if wert == 0 and feld in ["einspeisung_kwh", "netzbezug_kwh", "pv_erzeugung_kwh"]:
            vormonat = await self._get_vormonat_wert(
                anlage_id, feld, jahr, monat, investition_id
            )
            if vormonat and vormonat > 100:  # Im Vormonat war was da
                warnungen.append(PlausibilitaetsWarnung(
                    typ="zu_niedrig",
                    schwere="info",
                    meldung=f"Wert ist 0, aber im Vormonat waren es {vormonat:.0f} kWh",
                    details={"vormonat_wert": vormonat}
                ))

        return warnungen
