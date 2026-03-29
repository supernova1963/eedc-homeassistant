"""
Daten-Checker Service.

Prüft Anlage-Daten systematisch auf Vollständigkeit und Plausibilität.
5 Prüfkategorien: Stammdaten, Strompreise, Investitionen,
Monatsdaten-Vollständigkeit, Monatsdaten-Plausibilität.
"""

from dataclasses import dataclass, field
from datetime import date, timedelta
from enum import Enum
from typing import Optional

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.models.anlage import Anlage
from backend.models.monatsdaten import Monatsdaten
from backend.models.investition import Investition, InvestitionMonatsdaten
from backend.models.strompreis import Strompreis
from backend.models.pvgis_prognose import PVGISPrognose


# ─── Enums & Dataclasses ────────────────────────────────────────────────────

class CheckSeverity(str, Enum):
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"
    OK = "ok"


class CheckKategorie(str, Enum):
    STAMMDATEN = "stammdaten"
    STROMPREISE = "strompreise"
    INVESTITIONEN = "investitionen"
    MONATSDATEN_VOLLSTAENDIGKEIT = "monatsdaten_vollstaendigkeit"
    MONATSDATEN_PLAUSIBILITAET = "monatsdaten_plausibilitaet"


@dataclass
class CheckErgebnis:
    kategorie: str
    schwere: str
    meldung: str
    details: Optional[str] = None
    link: Optional[str] = None


@dataclass
class MonatsdatenAbdeckung:
    vorhanden: int
    erwartet: int
    prozent: float


@dataclass
class DatenCheckResult:
    anlage_id: int
    anlage_name: str
    ergebnisse: list[CheckErgebnis]
    zusammenfassung: dict
    monatsdaten_abdeckung: Optional[MonatsdatenAbdeckung] = None


# ─── Konstanten ──────────────────────────────────────────────────────────────

# Theoretisches PV-Maximum pro kWp und Monat (kWh) für Mitteleuropa
# Großzügig bemessen um False Positives zu vermeiden – obere Grenze
# für optimale Ausrichtung und überdurchschnittliche Einstrahlung
PV_MAX_KWH_PRO_KWP = {
    1: 55, 2: 75, 3: 110, 4: 140, 5: 170, 6: 180,
    7: 180, 8: 165, 9: 140, 10: 90, 11: 55, 12: 40,
}


# ─── Service ─────────────────────────────────────────────────────────────────

class DatenChecker:
    """Prüft alle Daten einer Anlage auf Vollständigkeit und Plausibilität."""

    def __init__(self, db: AsyncSession):
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
        ergebnisse.extend(self._check_investitionen(anlage))
        ergebnisse.extend(self._check_monatsdaten_vollstaendigkeit(anlage, monatsdaten))
        ergebnisse.extend(self._check_monatsdaten_plausibilitaet(
            anlage, monatsdaten, pvgis_prognose, pv_erzeugung_map, pvgis_monat_map, pr, pr_count
        ))

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

    # ─── Stammdaten ──────────────────────────────────────────────────────

    def _check_stammdaten(
        self,
        anlage: Anlage,
        pvgis_prognose: Optional[PVGISPrognose] = None,
        pr: float = 1.0,
        pr_count: int = 0,
    ) -> list[CheckErgebnis]:
        ergebnisse: list[CheckErgebnis] = []
        kat = CheckKategorie.STAMMDATEN

        # Installationsdatum
        if anlage.installationsdatum is None:
            ergebnisse.append(CheckErgebnis(
                kategorie=kat, schwere=CheckSeverity.WARNING,
                meldung="Installationsdatum nicht gesetzt",
                details="Wird für Vollständigkeitsprüfung der Monatsdaten benötigt",
                link="/einstellungen/anlage",
            ))
        else:
            ergebnisse.append(CheckErgebnis(
                kategorie=kat, schwere=CheckSeverity.OK,
                meldung="Installationsdatum vorhanden",
            ))

        # Leistung kWp
        if not anlage.leistung_kwp or anlage.leistung_kwp <= 0:
            ergebnisse.append(CheckErgebnis(
                kategorie=kat, schwere=CheckSeverity.ERROR,
                meldung="Anlagenleistung fehlt oder ist 0",
                details="Leistung in kWp ist für alle Berechnungen erforderlich",
                link="/einstellungen/anlage",
            ))
        else:
            ergebnisse.append(CheckErgebnis(
                kategorie=kat, schwere=CheckSeverity.OK,
                meldung=f"Anlagenleistung: {anlage.leistung_kwp} kWp",
            ))

        # Koordinaten für PVGIS
        if anlage.latitude is None or anlage.longitude is None:
            ergebnisse.append(CheckErgebnis(
                kategorie=kat, schwere=CheckSeverity.INFO,
                meldung="Keine Koordinaten hinterlegt",
                details="Koordinaten werden für die PVGIS-Solarprognose benötigt",
                link="/einstellungen/anlage",
            ))

        # PV-Module vorhanden
        pv_module = [i for i in anlage.investitionen if i.typ == "pv-module" and i.aktiv]
        hat_bkw = any(i.typ == "balkonkraftwerk" and i.aktiv for i in anlage.investitionen)
        if not pv_module:
            if hat_bkw:
                # BKW-only Setup: kein Fehler, nur Hinweis
                ergebnisse.append(CheckErgebnis(
                    kategorie=kat, schwere=CheckSeverity.INFO,
                    meldung="Nur Balkonkraftwerk, keine PV-Module angelegt",
                    details="PVGIS-Prognose und String-Vergleich sind ohne PV-Module nicht verfügbar",
                    link="/einstellungen/investitionen",
                ))
            else:
                ergebnisse.append(CheckErgebnis(
                    kategorie=kat, schwere=CheckSeverity.ERROR,
                    meldung="Keine PV-Module als Investition angelegt",
                    details="PV-Module werden für Erzeugungs-Auswertung benötigt",
                    link="/einstellungen/investitionen",
                ))
        else:
            # kWp-Vergleich (PV-Module + BKW)
            bkw_inv = [i for i in anlage.investitionen if i.typ == "balkonkraftwerk" and i.aktiv]
            summe_kwp = sum((m.leistung_kwp or 0) for m in pv_module)
            summe_kwp += sum(
                b.leistung_kwp or ((b.parameter or {}).get("leistung_wp", 0) * ((b.parameter or {}).get("anzahl", 1) or 1) / 1000)
                for b in bkw_inv
            )
            if anlage.leistung_kwp and abs(summe_kwp - anlage.leistung_kwp) > 0.1:
                ergebnisse.append(CheckErgebnis(
                    kategorie=kat, schwere=CheckSeverity.WARNING,
                    meldung="PV-Module kWp stimmt nicht mit Anlagenleistung überein",
                    details=f"Summe PV-Module + BKW: {summe_kwp:.1f} kWp, Anlage: {anlage.leistung_kwp:.1f} kWp",
                    link="/einstellungen/investitionen",
                ))
            else:
                ergebnisse.append(CheckErgebnis(
                    kategorie=kat, schwere=CheckSeverity.OK,
                    meldung=f"PV-Module: {summe_kwp:.1f} kWp ({len(pv_module)} Modul-Gruppen{', inkl. BKW' if bkw_inv else ''})",
                ))

        # Performance Ratio Hinweis (PVGIS-Systemverluste ggf. zu hoch)
        if pr_count >= 6 and pr > 1.1 and pvgis_prognose:
            system_losses = pvgis_prognose.system_losses if pvgis_prognose.system_losses is not None else 14
            abweichung_pct = round((pr - 1) * 100)
            ergebnisse.append(CheckErgebnis(
                kategorie=kat, schwere=CheckSeverity.INFO,
                meldung=f"PVGIS-Systemverluste ggf. zu hoch ({system_losses:.0f}%)",
                details=(
                    f"Anlage produziert Ø {abweichung_pct}% mehr als die PVGIS-Prognose "
                    f"(Performance Ratio: {pr:.2f} über {pr_count} Monate). "
                    f"Systemverluste in der Solarprognose reduzieren?"
                ),
                link="/einstellungen/solarprognose",
            ))

        return ergebnisse

    # ─── Strompreise ─────────────────────────────────────────────────────

    def _check_strompreise(self, anlage: Anlage) -> list[CheckErgebnis]:
        ergebnisse: list[CheckErgebnis] = []
        kat = CheckKategorie.STROMPREISE

        # Nur allgemeine Tarife prüfen
        tarife = sorted(
            [s for s in anlage.strompreise if s.verwendung == "allgemein"],
            key=lambda s: s.gueltig_ab,
        )

        if not tarife:
            ergebnisse.append(CheckErgebnis(
                kategorie=kat, schwere=CheckSeverity.ERROR,
                meldung="Kein Strompreis vorhanden",
                details="Strompreise sind für Finanz-Auswertungen und ROI-Berechnungen erforderlich",
                link="/einstellungen/strompreise",
            ))
            return ergebnisse

        ergebnisse.append(CheckErgebnis(
            kategorie=kat, schwere=CheckSeverity.OK,
            meldung=f"{len(tarife)} Strompreis-Tarif(e) vorhanden",
        ))

        # Lücken prüfen
        if anlage.installationsdatum:
            start = anlage.installationsdatum
            for i, tarif in enumerate(tarife):
                if tarif.gueltig_ab > start:
                    ergebnisse.append(CheckErgebnis(
                        kategorie=kat, schwere=CheckSeverity.WARNING,
                        meldung=f"Strompreis-Lücke: {start.strftime('%d.%m.%Y')} bis {tarif.gueltig_ab.strftime('%d.%m.%Y')}",
                        link="/einstellungen/strompreise",
                    ))
                # Nächster erwarteter Start (Tag nach gueltig_bis)
                if tarif.gueltig_bis:
                    start = tarif.gueltig_bis + timedelta(days=1)
                else:
                    start = date.today()  # Offenes Ende = aktuell gültig

        # Plausibilität der Werte
        for tarif in tarife:
            name = tarif.tarifname or f"ab {tarif.gueltig_ab.strftime('%d.%m.%Y')}"
            preis = tarif.netzbezug_arbeitspreis_cent_kwh
            if preis is not None and (preis < 5 or preis > 80):
                ergebnisse.append(CheckErgebnis(
                    kategorie=kat, schwere=CheckSeverity.WARNING,
                    meldung=f"Arbeitspreis ungewöhnlich: {preis:.1f} ct/kWh ({name})",
                    details="Erwarteter Bereich: 5–80 ct/kWh",
                    link="/einstellungen/strompreise",
                ))

            verg = tarif.einspeiseverguetung_cent_kwh
            if verg is not None and (verg < 0 or verg > 30):
                ergebnisse.append(CheckErgebnis(
                    kategorie=kat, schwere=CheckSeverity.WARNING,
                    meldung=f"Einspeisevergütung ungewöhnlich: {verg:.1f} ct/kWh ({name})",
                    details="Erwarteter Bereich: 0–30 ct/kWh",
                    link="/einstellungen/strompreise",
                ))

        return ergebnisse

    # ─── Investitionen ───────────────────────────────────────────────────

    def _check_investitionen(self, anlage: Anlage) -> list[CheckErgebnis]:
        ergebnisse: list[CheckErgebnis] = []
        kat = CheckKategorie.INVESTITIONEN

        aktive = [i for i in anlage.investitionen if i.aktiv]
        if not aktive:
            ergebnisse.append(CheckErgebnis(
                kategorie=kat, schwere=CheckSeverity.INFO,
                meldung="Keine aktiven Investitionen vorhanden",
                link="/einstellungen/investitionen",
            ))
            return ergebnisse

        for inv in aktive:
            name = f"{inv.bezeichnung} ({inv.typ})"
            param = inv.parameter or {}

            # Typ-spezifische Prüfungen
            if inv.typ == "pv-module":
                if not inv.leistung_kwp:
                    ergebnisse.append(CheckErgebnis(
                        kategorie=kat, schwere=CheckSeverity.WARNING,
                        meldung=f"{name}: Leistung (kWp) fehlt",
                        link="/einstellungen/investitionen",
                    ))
                if not inv.ausrichtung or inv.neigung_grad is None:
                    ergebnisse.append(CheckErgebnis(
                        kategorie=kat, schwere=CheckSeverity.INFO,
                        meldung=f"{name}: Ausrichtung/Neigung fehlt",
                        details="Wird für PVGIS-Solarprognose benötigt",
                        link="/einstellungen/investitionen",
                    ))

            elif inv.typ == "speicher":
                kap = param.get("kapazitaet_kwh")
                if not kap:
                    ergebnisse.append(CheckErgebnis(
                        kategorie=kat, schwere=CheckSeverity.WARNING,
                        meldung=f"{name}: Kapazität (kWh) fehlt",
                        link="/einstellungen/investitionen",
                    ))

            elif inv.typ == "e-auto":
                if not param.get("km_jahr") and not param.get("verbrauch_kwh_100km"):
                    ergebnisse.append(CheckErgebnis(
                        kategorie=kat, schwere=CheckSeverity.INFO,
                        meldung=f"{name}: Fahrleistung/Verbrauch fehlt",
                        details="Wird für E-Auto Einsparungs-Berechnung benötigt",
                        link="/einstellungen/investitionen",
                    ))
                if inv.anschaffungskosten_alternativ is None:
                    ergebnisse.append(CheckErgebnis(
                        kategorie=kat, schwere=CheckSeverity.WARNING,
                        meldung=f"{name}: Alternativkosten (Verbrenner) fehlen",
                        details="Werden für ROI-Berechnung benötigt (Vergleich mit Verbrenner-Alternative)",
                        link="/einstellungen/investitionen",
                    ))

            elif inv.typ == "waermepumpe":
                if inv.anschaffungskosten_alternativ is None:
                    ergebnisse.append(CheckErgebnis(
                        kategorie=kat, schwere=CheckSeverity.WARNING,
                        meldung=f"{name}: Alternativkosten (Gas-/Ölheizung) fehlen",
                        details="Werden für ROI-Berechnung benötigt (Vergleich mit konventioneller Heizung)",
                        link="/einstellungen/investitionen",
                    ))

            # Allgemeine Prüfungen für alle Typen
            if inv.anschaffungsdatum is None:
                ergebnisse.append(CheckErgebnis(
                    kategorie=kat, schwere=CheckSeverity.INFO,
                    meldung=f"{name}: Anschaffungsdatum fehlt",
                    link="/einstellungen/investitionen",
                ))

            if inv.anschaffungskosten_gesamt is None:
                ergebnisse.append(CheckErgebnis(
                    kategorie=kat, schwere=CheckSeverity.INFO,
                    meldung=f"{name}: Anschaffungskosten fehlen",
                    details="Werden für ROI-Berechnung benötigt",
                    link="/einstellungen/investitionen",
                ))

        return ergebnisse

    # ─── Monatsdaten Vollständigkeit ─────────────────────────────────────

    def _check_monatsdaten_vollstaendigkeit(
        self, anlage: Anlage, monatsdaten: list[Monatsdaten]
    ) -> list[CheckErgebnis]:
        ergebnisse: list[CheckErgebnis] = []
        kat = CheckKategorie.MONATSDATEN_VOLLSTAENDIGKEIT

        if not monatsdaten:
            ergebnisse.append(CheckErgebnis(
                kategorie=kat, schwere=CheckSeverity.WARNING,
                meldung="Keine Monatsdaten vorhanden",
                link="/einstellungen/monatsdaten",
            ))
            self._abdeckung = MonatsdatenAbdeckung(vorhanden=0, erwartet=0, prozent=0)
            return ergebnisse

        # Erwarteten Bereich bestimmen (bis Vormonat – laufender Monat noch nicht abgeschlossen)
        heute = date.today()
        if heute.month == 1:
            letzter_jahr, letzter_monat = heute.year - 1, 12
        else:
            letzter_jahr, letzter_monat = heute.year, heute.month - 1

        if anlage.installationsdatum:
            start_jahr = anlage.installationsdatum.year
            start_monat = anlage.installationsdatum.month
        else:
            # Fallback: frühester Monatsdaten-Eintrag
            start_jahr = monatsdaten[0].jahr
            start_monat = monatsdaten[0].monat

        # Vorhandene Monate als Set
        vorhandene = {(md.jahr, md.monat) for md in monatsdaten}

        # Erwartete Monate durchlaufen (bis Vormonat)
        erwartete: list[tuple[int, int]] = []
        j, m = start_jahr, start_monat
        while (j, m) <= (letzter_jahr, letzter_monat):
            erwartete.append((j, m))
            m += 1
            if m > 12:
                m = 1
                j += 1

        # Fehlende Monate finden
        fehlende = [e for e in erwartete if e not in vorhandene]

        # Abdeckung berechnen
        prozent = ((len(erwartete) - len(fehlende)) / len(erwartete) * 100) if erwartete else 100
        self._abdeckung = MonatsdatenAbdeckung(
            vorhanden=len(erwartete) - len(fehlende),
            erwartet=len(erwartete),
            prozent=round(prozent, 1),
        )

        if not fehlende:
            ergebnisse.append(CheckErgebnis(
                kategorie=kat, schwere=CheckSeverity.OK,
                meldung=f"Alle {len(erwartete)} Monate vollständig",
            ))
        else:
            # Maximal 12 fehlende Monate einzeln auflisten, dann zusammenfassen
            for jahr, monat in fehlende[:12]:
                ergebnisse.append(CheckErgebnis(
                    kategorie=kat, schwere=CheckSeverity.WARNING,
                    meldung=f"{monat:02d}/{jahr} fehlt",
                    link=f"/monatsabschluss/{anlage.id}/{jahr}/{monat}",
                ))
            if len(fehlende) > 12:
                ergebnisse.append(CheckErgebnis(
                    kategorie=kat, schwere=CheckSeverity.WARNING,
                    meldung=f"... und {len(fehlende) - 12} weitere Monate fehlen",
                    link="/einstellungen/monatsdaten",
                ))

        return ergebnisse

    # ─── Monatsdaten Plausibilität ───────────────────────────────────────

    def _check_monatsdaten_plausibilitaet(
        self,
        anlage: Anlage,
        monatsdaten: list[Monatsdaten],
        pvgis_prognose: Optional[PVGISPrognose] = None,
        pv_erzeugung_map: Optional[dict] = None,
        pvgis_monat_map: Optional[dict] = None,
        pr: float = 1.0,
        pr_count: int = 0,
    ) -> list[CheckErgebnis]:
        ergebnisse: list[CheckErgebnis] = []
        kat = CheckKategorie.MONATSDATEN_PLAUSIBILITAET

        if not monatsdaten:
            return ergebnisse

        # Fallback falls nicht von außen übergeben
        if pv_erzeugung_map is None:
            pv_erzeugung_map = self._get_pv_erzeugung_map(anlage)
        if pvgis_monat_map is None:
            pvgis_monat_map = self._get_pvgis_monat_map(pvgis_prognose)

        # Vorjahres-Lookup erstellen
        md_map = {(md.jahr, md.monat): md for md in monatsdaten}
        gesamt_kwp = anlage.leistung_kwp or 0

        for md in monatsdaten:
            prefix = f"{md.monat:02d}/{md.jahr}"
            md_link = f"/monatsabschluss/{anlage.id}/{md.jahr}/{md.monat}"

            # PV-Erzeugung bestimmen (InvestitionMonatsdaten oder Legacy)
            pv_erzeugung = pv_erzeugung_map.get((md.jahr, md.monat))
            if pv_erzeugung is None and md.pv_erzeugung_kwh is not None:
                pv_erzeugung = md.pv_erzeugung_kwh

            # 1. Negative Werte
            for feld, wert in [
                ("Einspeisung", md.einspeisung_kwh),
                ("Netzbezug", md.netzbezug_kwh),
                ("PV-Erzeugung", pv_erzeugung),
                ("Batterie-Ladung", md.batterie_ladung_kwh),
                ("Batterie-Entladung", md.batterie_entladung_kwh),
            ]:
                if wert is not None and wert < 0:
                    ergebnisse.append(CheckErgebnis(
                        kategorie=kat, schwere=CheckSeverity.ERROR,
                        meldung=f"{prefix}: {feld} ist negativ ({wert:.1f} kWh)",
                        link=md_link,
                    ))

            # 2. PV-Produktion > Maximum (PVGIS + Performance Ratio oder statisch)
            if pv_erzeugung is not None and gesamt_kwp > 0:
                pvgis_soll = pvgis_monat_map.get(md.monat)
                if pvgis_soll is not None:
                    # Dynamische Obergrenze: PVGIS × Performance Ratio × 1.45
                    # Der 1.45-Faktor deckt die natürliche Monatsvariation ab
                    # (±40% um den Anlagen-Durchschnitt ist typisch)
                    # Mindestens PVGIS × 1.5 (für Anlagen ohne genug Historie)
                    pr_faktor = max(pr, 1.0) * 1.45 if pr_count >= 6 else 1.5
                    max_kwh = pvgis_soll * max(pr_faktor, 1.5)
                else:
                    # Statischer Fallback
                    max_kwh = gesamt_kwp * PV_MAX_KWH_PRO_KWP.get(md.monat, 180)

                if pv_erzeugung > max_kwh:
                    if pvgis_soll is not None:
                        details = (
                            f"PVGIS-Prognose: {pvgis_soll:.0f} kWh, "
                            f"Obergrenze (×{max_kwh / pvgis_soll:.1f}): {max_kwh:.0f} kWh"
                        )
                    else:
                        details = (
                            f"Statisches Maximum für {gesamt_kwp:.1f} kWp "
                            f"im Monat {md.monat}: ca. {max_kwh:.0f} kWh"
                        )
                    ergebnisse.append(CheckErgebnis(
                        kategorie=kat, schwere=CheckSeverity.WARNING,
                        meldung=f"{prefix}: PV-Erzeugung ungewöhnlich hoch ({pv_erzeugung:.0f} kWh)",
                        details=details,
                        link=md_link,
                    ))

            # 3. Einspeisung > PV-Erzeugung
            if (
                pv_erzeugung is not None
                and pv_erzeugung > 0
                and md.einspeisung_kwh > pv_erzeugung
            ):
                ergebnisse.append(CheckErgebnis(
                    kategorie=kat, schwere=CheckSeverity.ERROR,
                    meldung=f"{prefix}: Einspeisung ({md.einspeisung_kwh:.0f} kWh) > PV-Erzeugung ({pv_erzeugung:.0f} kWh)",
                    details="Einspeisung kann nicht höher als die Erzeugung sein",
                    link=md_link,
                ))

            # 4. Beide Werte 0
            if md.einspeisung_kwh == 0 and md.netzbezug_kwh == 0:
                ergebnisse.append(CheckErgebnis(
                    kategorie=kat, schwere=CheckSeverity.WARNING,
                    meldung=f"{prefix}: Einspeisung und Netzbezug sind beide 0",
                    details="Wahrscheinlich fehlende Daten",
                    link=md_link,
                ))

            # 5. Extreme Sprünge zum Vorjahr
            vorjahr = md_map.get((md.jahr - 1, md.monat))
            if vorjahr:
                for feld, wert, vj_wert in [
                    ("Einspeisung", md.einspeisung_kwh, vorjahr.einspeisung_kwh),
                    ("Netzbezug", md.netzbezug_kwh, vorjahr.netzbezug_kwh),
                ]:
                    if vj_wert and vj_wert > 50 and wert > 3 * vj_wert:
                        ergebnisse.append(CheckErgebnis(
                            kategorie=kat, schwere=CheckSeverity.WARNING,
                            meldung=f"{prefix}: {feld} > 3× Vorjahr ({wert:.0f} vs. {vj_wert:.0f} kWh)",
                            details="Deutliche Abweichung zum Vorjahresmonat",
                            link=md_link,
                        ))

        if not ergebnisse:
            ergebnisse.append(CheckErgebnis(
                kategorie=kat, schwere=CheckSeverity.OK,
                meldung="Keine Auffälligkeiten in den Monatsdaten",
            ))

        return ergebnisse

    # ─── Hilfsmethoden ───────────────────────────────────────────────────

    def _calculate_performance_ratio(
        self,
        pv_erzeugung_map: dict[tuple[int, int], float],
        pvgis_monat_map: dict[int, float],
        monatsdaten: list[Monatsdaten],
    ) -> tuple[float, int]:
        """Berechnet Ø Performance Ratio (IST/PVGIS).

        Nutzt die letzten 12 Monate (falls verfügbar) für ein aktuelles Bild.
        Filtert unvollständige Monate (Ratio < 0.5, z.B. Installationsmonat).

        Returns:
            (performance_ratio, anzahl_monate) – ratio 1.0 = exakt wie Prognose
        """
        alle_ratios: list[tuple[int, int, float]] = []  # (jahr, monat, ratio)

        for md in monatsdaten:
            pvgis_soll = pvgis_monat_map.get(md.monat)
            if not pvgis_soll or pvgis_soll <= 0:
                continue

            # IST-Erzeugung bestimmen
            pv_ist = pv_erzeugung_map.get((md.jahr, md.monat))
            if pv_ist is None and md.pv_erzeugung_kwh is not None:
                pv_ist = md.pv_erzeugung_kwh
            if pv_ist is None or pv_ist <= 0:
                continue

            ratio = pv_ist / pvgis_soll
            # Unvollständige Monate ausfiltern (z.B. Installationsmonat)
            if ratio >= 0.5:
                alle_ratios.append((md.jahr, md.monat, ratio))

        if not alle_ratios:
            return 1.0, 0

        # Letzten 12 Monate bevorzugen (aktuelleres Bild)
        alle_ratios.sort(key=lambda x: (x[0], x[1]))
        letzte = alle_ratios[-12:] if len(alle_ratios) > 12 else alle_ratios
        ratios = [r[2] for r in letzte]

        return sum(ratios) / len(ratios), len(ratios)

    def _get_pvgis_monat_map(self, prognose: Optional[PVGISPrognose]) -> dict[int, float]:
        """Baut Lookup Monat → erwartete kWh aus aktiver PVGIS-Prognose."""
        if not prognose or not prognose.monatswerte:
            return {}

        monat_map: dict[int, float] = {}
        for eintrag in prognose.monatswerte:
            monat = eintrag.get("monat")
            e_m = eintrag.get("e_m")
            if monat is not None and e_m is not None:
                monat_map[monat] = e_m

        return monat_map

    def _get_pv_erzeugung_map(self, anlage: Anlage) -> dict[tuple[int, int], float]:
        """Aggregiert PV-Erzeugung aus InvestitionMonatsdaten pro Monat."""
        pv_map: dict[tuple[int, int], float] = {}

        for inv in anlage.investitionen:
            if inv.typ != "pv-module" or not inv.aktiv:
                continue
            for imd in inv.monatsdaten:
                data = imd.verbrauch_daten or {}
                erzeugung = data.get("pv_erzeugung_kwh")
                if erzeugung is not None:
                    key = (imd.jahr, imd.monat)
                    pv_map[key] = pv_map.get(key, 0) + erzeugung

        return pv_map
