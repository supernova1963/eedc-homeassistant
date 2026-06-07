"""
Daten-Checker — Stammdaten, Strompreise & Investitionen (`StammdatenChecks`).

Reiner Move aus dem früheren Modul `daten_checker.py` (Tier-4 Achse C).
"""

from datetime import date, timedelta
from typing import Optional

from backend.models.anlage import Anlage
from backend.models.monatsdaten import Monatsdaten
from backend.models.pvgis_prognose import PVGISPrognose
from backend.utils.investition_filter import sort_investitionen_nach_typ
from backend.core.investition_parameter import ist_dienstlich
from backend.core.berechnungen import pruefe_speicher_netzladung_kumulativ
from backend.core.field_definitions import get_speicher_netzladung_kwh

from .kategorien import CheckErgebnis, CheckKategorie, CheckSeverity


class StammdatenChecks:
    """Prüfungen für Stammdaten, Strompreise und Investitions-Stammwerte."""

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

        # Standort für Community-Vergleich
        if not anlage.standort_ort and not anlage.standort_plz:
            ergebnisse.append(CheckErgebnis(
                kategorie=kat, schwere=CheckSeverity.INFO,
                meldung="Kein Standort hinterlegt (Ort/PLZ)",
                details="Wird für den Community-Benchmark-Vergleich nach Region benötigt",
                link="/einstellungen/anlage",
            ))

        # PV-Module vorhanden. Filter respektiert Stilllegungsdatum (#608
        # MartyBr): String-Verlegung zwischen Wechselrichtern wird über
        # stilllegungsdatum-Setzen + neue Investition erfasst — der alte
        # String soll dann nicht mehr zur Σ aktiver kWp beitragen.
        heute = date.today()
        pv_module = [i for i in anlage.investitionen if i.typ == "pv-module" and i.ist_aktiv_an(heute)]
        hat_bkw = any(i.typ == "balkonkraftwerk" and i.ist_aktiv_an(heute) for i in anlage.investitionen)
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
            bkw_inv = [i for i in anlage.investitionen if i.typ == "balkonkraftwerk" and i.ist_aktiv_an(heute)]
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

        # Spezialtarife prüfen (WP / E-Auto)
        verwendungen = {s.verwendung for s in anlage.strompreise}
        heute = date.today()
        hat_wp = any(i.typ == "waermepumpe" and i.ist_aktiv_an(heute) for i in anlage.investitionen)
        hat_eauto = any(i.typ == "e-auto" and i.ist_aktiv_an(heute) for i in anlage.investitionen)
        if hat_wp and "waermepumpe" not in verwendungen:
            ergebnisse.append(CheckErgebnis(
                kategorie=kat, schwere=CheckSeverity.INFO,
                meldung="Kein WP-Spezialtarif hinterlegt",
                details="Wärmepumpe vorhanden – bei eigenem WP-Tarif (Wärmestrom) hier ergänzen",
                link="/einstellungen/strompreise",
            ))
        if hat_eauto and "e-auto" not in verwendungen:
            ergebnisse.append(CheckErgebnis(
                kategorie=kat, schwere=CheckSeverity.INFO,
                meldung="Kein E-Auto-Spezialtarif hinterlegt",
                details="E-Auto vorhanden – bei eigenem Ladetarif hier ergänzen",
                link="/einstellungen/strompreise",
            ))

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

    def _check_investitionen(self, anlage: Anlage, monatsdaten: list[Monatsdaten]) -> list[CheckErgebnis]:
        ergebnisse: list[CheckErgebnis] = []
        kat = CheckKategorie.INVESTITIONEN

        # Reihenfolge nach Typ (#214 detLAN: WP vor Wallbox), nicht DB-ID.
        # Stilllegungsdatum-Filter via `ist_aktiv_an` (#608 Sweep): stillgelegte
        # Investitionen brauchen keine Stamm-Daten-Pflege mehr — Ausrichtung,
        # kWp, Anschaffungskosten sind dann historisch fixiert oder irrelevant.
        heute = date.today()
        aktive = sort_investitionen_nach_typ(i for i in anlage.investitionen if i.ist_aktiv_an(heute))
        if not aktive:
            ergebnisse.append(CheckErgebnis(
                kategorie=kat, schwere=CheckSeverity.INFO,
                meldung="Keine aktiven Investitionen vorhanden",
                link="/einstellungen/investitionen",
            ))
            return ergebnisse

        # PV-Erzeugung anlagenweit prüfen (kWp-Verteilung-Etappe): gemessen=OK,
        # über Aggregat verteilt=INFO, Teil-Lücke=WARNING, gar keine PV-Quelle=
        # ERROR. Ersetzt die frühere Pro-Modul-„fehlt"-WARNING — ein einzelner
        # Gesamtwert (Monatsdaten.pv_erzeugung_kwh) deckt jetzt alle Strings ab.
        ergebnisse.extend(self._check_pv_erzeugung(anlage, monatsdaten))

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
                # PV-Erzeugungs-Vollständigkeit: anlagenweit in
                # _check_pv_erzeugung (kWp-Verteilung) — hier NICHT pro Modul
                # prüfen, sonst meldet jeder String „fehlt", obwohl ein
                # Gesamt-Aggregat alle deckt.

            elif inv.typ == "balkonkraftwerk":
                if not param.get("leistung_wp"):
                    ergebnisse.append(CheckErgebnis(
                        kategorie=kat, schwere=CheckSeverity.WARNING,
                        meldung=f"{name}: Leistung (Wp) fehlt",
                        link="/einstellungen/investitionen",
                    ))
                ergebnisse.extend(self._check_investition_monatsdaten(
                    inv, name, "pv_erzeugung_kwh", "PV-Erzeugung", CheckSeverity.WARNING, monatsdaten,
                ))

            elif inv.typ == "speicher":
                kap = param.get("kapazitaet_kwh")
                if not kap:
                    ergebnisse.append(CheckErgebnis(
                        kategorie=kat, schwere=CheckSeverity.WARNING,
                        meldung=f"{name}: Kapazität (kWh) fehlt",
                        link="/einstellungen/investitionen",
                    ))
                if param.get("nutzt_arbitrage"):
                    if not param.get("lade_durchschnittspreis_cent"):
                        ergebnisse.append(CheckErgebnis(
                            kategorie=kat, schwere=CheckSeverity.WARNING,
                            meldung=f"{name}: Arbitrage aktiv, aber Ø Ladepreis fehlt",
                            details="Wird für Arbitrage-Einsparungsberechnung benötigt",
                            link="/einstellungen/investitionen",
                        ))
                    if not param.get("entlade_vermiedener_preis_cent"):
                        ergebnisse.append(CheckErgebnis(
                            kategorie=kat, schwere=CheckSeverity.WARNING,
                            meldung=f"{name}: Arbitrage aktiv, aber Ø Entladepreis fehlt",
                            details="Wird für Arbitrage-Einsparungsberechnung benötigt",
                            link="/einstellungen/investitionen",
                        ))
                ergebnisse.extend(self._check_investition_monatsdaten(
                    inv, name, "ladung_kwh", "Speicher-Ladung", CheckSeverity.WARNING, monatsdaten,
                ))
                # #281 / rapahl-PN 2026-05-22: Netzladung darf die Gesamt-
                # ladung nicht übersteigen, sonst wäre der implizite PV-Anteil
                # negativ. KUMULATIV prüfen, nicht pro Monat: Netz- und Gesamt-
                # Ladungs-Zähler haben getrennte Monats-Schnappschüsse, ein
                # Ladevorgang über die Monatsgrenze (Tibber-Nachtladung) landet
                # beim einen Zähler noch im alten, beim anderen schon im neuen
                # Monat. Erst die Summe über die Historie ist aussagekräftig.
                gesamt_ladung_kwh = 0.0
                gesamt_netzladung_kwh = 0.0
                for imd in inv.monatsdaten:
                    vd = imd.verbrauch_daten or {}
                    gesamt_ladung_kwh += float(vd.get("ladung_kwh") or 0.0)
                    gesamt_netzladung_kwh += get_speicher_netzladung_kwh(vd)
                bericht = pruefe_speicher_netzladung_kumulativ(
                    gesamt_ladung_kwh, gesamt_netzladung_kwh,
                )
                if not bericht.konsistent:
                    ergebnisse.append(CheckErgebnis(
                        kategorie=kat, schwere=CheckSeverity.WARNING,
                        meldung=f"{name}: Netzladung übersteigt Gesamtladung (kumulativ)",
                        details=bericht.details,
                        link="/einstellungen/monatsdaten",
                    ))

            elif inv.typ == "e-auto":
                # Dienstwagen: keine PV-Ladungs-/ROI-Checks (kein PV-Bezug, kein Invest)
                if ist_dienstlich(param):
                    continue
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
                if param.get("nutzt_v2h") and not param.get("v2h_entlade_preis_cent"):
                    ergebnisse.append(CheckErgebnis(
                        kategorie=kat, schwere=CheckSeverity.INFO,
                        meldung=f"{name}: V2H aktiv, aber Entladepreis fehlt",
                        details="Wird für V2H-Einsparungsberechnung benötigt",
                        link="/einstellungen/investitionen",
                    ))
                ergebnisse.extend(self._check_investition_monatsdaten(
                    inv, name, "ladung_pv_kwh", "Ladung PV", CheckSeverity.INFO, monatsdaten,
                ))

            elif inv.typ == "wallbox":
                if not param.get("max_ladeleistung_kw") and not param.get("leistung_kw"):
                    ergebnisse.append(CheckErgebnis(
                        kategorie=kat, schwere=CheckSeverity.WARNING,
                        meldung=f"{name}: Ladeleistung (kW) fehlt",
                        link="/einstellungen/investitionen",
                    ))
                ergebnisse.extend(self._check_investition_monatsdaten(
                    inv, name, "ladung_kwh", "Ladung gesamt", CheckSeverity.INFO, monatsdaten,
                ))

            elif inv.typ == "wechselrichter":
                if not param.get("max_leistung_kw") and not param.get("leistung_ac_kw"):
                    ergebnisse.append(CheckErgebnis(
                        kategorie=kat, schwere=CheckSeverity.WARNING,
                        meldung=f"{name}: Leistung (kW) fehlt",
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

                # Effizienz-Parameter je nach Berechnungsmodus prüfen
                effizienz_modus = param.get("effizienz_modus", "gesamt_jaz")
                if effizienz_modus == "gesamt_jaz":
                    jaz = param.get("jaz")
                    if jaz is None:
                        ergebnisse.append(CheckErgebnis(
                            kategorie=kat, schwere=CheckSeverity.WARNING,
                            meldung=f"{name}: JAZ nicht gesetzt",
                            details="Jahresarbeitszahl wird für COP-Berechnung der Heizenergie benötigt",
                            link="/einstellungen/investitionen",
                        ))
                    elif not (1.5 <= jaz <= 7.0):
                        ergebnisse.append(CheckErgebnis(
                            kategorie=kat, schwere=CheckSeverity.WARNING,
                            meldung=f"{name}: JAZ unplausibel ({jaz:.1f})",
                            details="Typischer Bereich: 1,5–7,0 (Luft-WP ca. 2,5–4,5, Sole-WP ca. 3,5–5,5)",
                            link="/einstellungen/investitionen",
                        ))
                elif effizienz_modus == "scop":
                    scop_h = param.get("scop_heizung")
                    scop_ww = param.get("scop_warmwasser")
                    if scop_h is None or scop_ww is None:
                        ergebnisse.append(CheckErgebnis(
                            kategorie=kat, schwere=CheckSeverity.WARNING,
                            meldung=f"{name}: SCOP-Werte fehlen (Modus: EU-Label SCOP)",
                            details="SCOP Heizung und SCOP Warmwasser werden für Einsparungs-Berechnung benötigt",
                            link="/einstellungen/investitionen",
                        ))
                elif effizienz_modus == "getrennte_cops":
                    cop_h = param.get("cop_heizung")
                    cop_ww = param.get("cop_warmwasser")
                    if cop_h is None or cop_ww is None:
                        ergebnisse.append(CheckErgebnis(
                            kategorie=kat, schwere=CheckSeverity.WARNING,
                            meldung=f"{name}: COP-Werte fehlen (Modus: Getrennte COPs)",
                            details="COP Heizung und COP Warmwasser werden für Einsparungs-Berechnung benötigt",
                            link="/einstellungen/investitionen",
                        ))

                # Alter Energieträger / Preis für Vergleichsrechnung
                alter_preis = param.get("alter_preis_cent_kwh")
                if alter_preis is None:
                    ergebnisse.append(CheckErgebnis(
                        kategorie=kat, schwere=CheckSeverity.INFO,
                        meldung=f"{name}: Alter Energiepreis nicht gesetzt",
                        details="Wird für Einsparungs-Berechnung vs. Gas-/Ölheizung benötigt",
                        link="/einstellungen/investitionen",
                    ))

                # Wärmebedarf für Jahres-Einsparungsschätzung
                if not param.get("heizwaermebedarf_kwh"):
                    ergebnisse.append(CheckErgebnis(
                        kategorie=kat, schwere=CheckSeverity.INFO,
                        meldung=f"{name}: Heizwärmebedarf nicht gesetzt",
                        details="Wird für Jahres-Einsparungsschätzung verwendet (kWh/Jahr)",
                        link="/einstellungen/investitionen",
                    ))

                # Monatsdaten-Vollständigkeit der WP prüfen
                ergebnisse.extend(
                    self._check_wp_monatsdaten(inv, name, param, monatsdaten)
                )

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
