"""
Daten-Checker — Monatsdaten-Vollständigkeit & -Plausibilität (`MonatsdatenChecks`).

Reiner Move aus dem früheren Modul `daten_checker.py` (Tier-4 Achse C).
"""

from datetime import date
from typing import Optional

from backend.models.anlage import Anlage
from backend.models.monatsdaten import Monatsdaten
from backend.models.investition import Investition
from backend.models.pvgis_prognose import PVGISPrognose

from .kategorien import (
    CheckErgebnis,
    CheckKategorie,
    CheckSeverity,
    MonatsdatenAbdeckung,
)


# Theoretisches PV-Maximum pro kWp und Monat (kWh) für Mitteleuropa
# Großzügig bemessen um False Positives zu vermeiden – obere Grenze
# für optimale Ausrichtung und überdurchschnittliche Einstrahlung
PV_MAX_KWH_PRO_KWP = {
    1: 55, 2: 75, 3: 110, 4: 140, 5: 170, 6: 180,
    7: 180, 8: 165, 9: 140, 10: 90, 11: 55, 12: 40,
}


class MonatsdatenChecks:
    """Prüfungen rund um Monatsdaten und Investition-Monatsdaten."""

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

        # Kontext: aktive Investitionstypen (für feldabhängige Checks). Stilllegung
        # respektieren — wenn der einzige Speicher stillgelegt ist, sollen
        # Speicher-spezifische Plausibilitäts-Checks nicht mehr feuern.
        heute_plaus = date.today()
        aktive_typen = {i.typ for i in anlage.investitionen if i.ist_aktiv_an(heute_plaus)}
        hat_speicher = "speicher" in aktive_typen

        # Monate mit Speicher-Daten in InvestitionMonatsdaten (neuer Weg).
        # Legacy-Felder batterie_ladung/entladung_kwh in Monatsdaten sind dann NULL –
        # das ist korrekt und darf keine Warnung auslösen.
        # Werte werden auch für die Energiebilanz gebraucht (aggregiert über alle Speicher).
        speicher_imd_bat: dict[tuple[int, int], tuple[float, float]] = {}  # (jahr,monat) → (ladung, entladung)
        # Monate, in denen mind. ein Speicher zeitlich aktiv war (Anschaffung erfolgt,
        # noch nicht stillgelegt). Verhindert Warnungen für Monate VOR der ersten
        # Batterie-Installation (Issue #226 JanKgh: PV seit 11/2021, Speicher erst
        # ab 11/2022 — der Datenchecker monierte Batterie-Daten für 11/2021).
        speicher_aktiv_monate: set[tuple[int, int]] = set()
        for inv in anlage.investitionen:
            if inv.typ == "speicher" and inv.aktiv:
                start = (inv.anschaffungsdatum.year, inv.anschaffungsdatum.month) if inv.anschaffungsdatum else None
                end = (inv.stilllegungsdatum.year, inv.stilllegungsdatum.month) if inv.stilllegungsdatum else None
                for md in monatsdaten:
                    md_key = (md.jahr, md.monat)
                    if start is not None and md_key < start:
                        continue
                    if end is not None and md_key > end:
                        continue
                    speicher_aktiv_monate.add(md_key)
                for imd in inv.monatsdaten:
                    daten = imd.verbrauch_daten or {}
                    ladung = daten.get("ladung_kwh")
                    entladung = daten.get("entladung_kwh")
                    if ladung is not None or entladung is not None:
                        key = (imd.jahr, imd.monat)
                        prev = speicher_imd_bat.get(key, (0.0, 0.0))
                        speicher_imd_bat[key] = (
                            prev[0] + (ladung or 0),
                            prev[1] + (entladung or 0),
                        )
        speicher_imd_monate = set(speicher_imd_bat.keys())

        for md in monatsdaten:
            prefix = f"{md.monat:02d}/{md.jahr}"
            md_link = f"/monatsabschluss/{anlage.id}/{md.jahr}/{md.monat}"

            # PV-Erzeugung bestimmen (InvestitionMonatsdaten oder Legacy)
            pv_erzeugung = pv_erzeugung_map.get((md.jahr, md.monat))
            if pv_erzeugung is None and md.pv_erzeugung_kwh is not None:
                pv_erzeugung = md.pv_erzeugung_kwh

            # 0. Pflichtfelder nicht befüllt
            if md.einspeisung_kwh is None:
                ergebnisse.append(CheckErgebnis(
                    kategorie=kat, schwere=CheckSeverity.ERROR,
                    meldung=f"{prefix}: Einspeisung nicht erfasst",
                    details="Kernfeld – ohne Einspeisung sind Eigenverbrauch und Autarkie nicht berechenbar",
                    link=md_link,
                ))
            if md.netzbezug_kwh is None:
                ergebnisse.append(CheckErgebnis(
                    kategorie=kat, schwere=CheckSeverity.ERROR,
                    meldung=f"{prefix}: Netzbezug nicht erfasst",
                    details="Kernfeld – ohne Netzbezug sind Hausverbrauch und Stromkosten nicht berechenbar",
                    link=md_link,
                ))
            if (
                hat_speicher
                and (md.jahr, md.monat) in speicher_aktiv_monate
                and (md.jahr, md.monat) not in speicher_imd_monate
            ):
                # Legacy-Felder nur prüfen wenn keine InvestitionMonatsdaten vorhanden
                if md.batterie_ladung_kwh is None:
                    ergebnisse.append(CheckErgebnis(
                        kategorie=kat, schwere=CheckSeverity.WARNING,
                        meldung=f"{prefix}: Batterie-Ladung nicht erfasst (Speicher vorhanden)",
                        details="Ohne Batterie-Daten wird der Hausverbrauch falsch berechnet",
                        link=md_link,
                    ))
                if md.batterie_entladung_kwh is None:
                    ergebnisse.append(CheckErgebnis(
                        kategorie=kat, schwere=CheckSeverity.WARNING,
                        meldung=f"{prefix}: Batterie-Entladung nicht erfasst (Speicher vorhanden)",
                        details="Ohne Batterie-Daten wird der Hausverbrauch falsch berechnet",
                        link=md_link,
                    ))

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
                and md.einspeisung_kwh is not None
                and md.einspeisung_kwh > pv_erzeugung
            ):
                ergebnisse.append(CheckErgebnis(
                    kategorie=kat, schwere=CheckSeverity.ERROR,
                    meldung=f"{prefix}: Einspeisung ({md.einspeisung_kwh:.0f} kWh) > PV-Erzeugung ({pv_erzeugung:.0f} kWh)",
                    details=(
                        "Einspeisung kann nicht höher als die Erzeugung sein. "
                        "Häufigste Ursache: Einspeisungs- und Netzbezugs-Sensor "
                        "sind im Sensor-Mapping vertauscht (oder das Vorzeichen "
                        "eines kombinierten Netz-Sensors ist invertiert)."
                    ),
                    link=md_link,
                ))

            # 4. Beide Kernfelder 0
            if md.einspeisung_kwh == 0 and md.netzbezug_kwh == 0:
                ergebnisse.append(CheckErgebnis(
                    kategorie=kat, schwere=CheckSeverity.WARNING,
                    meldung=f"{prefix}: Einspeisung und Netzbezug sind beide 0",
                    details="Wahrscheinlich fehlende Daten",
                    link=md_link,
                ))

            # 5. Extreme Sprünge zum Vorjahr
            # #240 NongJoWo: Wenn der Vorjahresmonat der Inbetriebnahme-Monat
            # der Anlage (oder davor) ist, sind die Werte nur Bruchteil-
            # Erfassung — keine valide Vergleichsbasis. Beispiel: Anlage seit
            # Ende März 2022 → März 2022 = ein paar Tage, der März-2023-
            # Vergleich (3× höher) ist deshalb keine Anomalie.
            vorjahr = md_map.get((md.jahr - 1, md.monat))
            inst = anlage.installationsdatum
            if (
                vorjahr
                and not (inst and (vorjahr.jahr, vorjahr.monat) <= (inst.year, inst.month))
            ):
                for feld, wert, vj_wert in [
                    ("Einspeisung", md.einspeisung_kwh, vorjahr.einspeisung_kwh),
                    ("Netzbezug", md.netzbezug_kwh, vorjahr.netzbezug_kwh),
                ]:
                    if vj_wert and vj_wert > 50 and wert is not None and wert > 3 * vj_wert:
                        ergebnisse.append(CheckErgebnis(
                            kategorie=kat, schwere=CheckSeverity.WARNING,
                            meldung=f"{prefix}: {feld} > 3× Vorjahr ({wert:.0f} vs. {vj_wert:.0f} kWh)",
                            details="Deutliche Abweichung zum Vorjahresmonat",
                            link=md_link,
                        ))

            # 6. Energiebilanz: Hausverbrauch = PV - Einspeisung + Netzbezug ± Batterie
            # Nur prüfbar wenn alle Kernfelder vorhanden
            if (
                md.einspeisung_kwh is not None
                and md.netzbezug_kwh is not None
            ):
                pv = pv_erzeugung or 0
                # Batterie: InvestitionMonatsdaten bevorzugen (neuer Weg), Legacy als Fallback
                imd_key = (md.jahr, md.monat)
                if imd_key in speicher_imd_bat:
                    bat_ladung, bat_entladung = speicher_imd_bat[imd_key]
                else:
                    bat_ladung = md.batterie_ladung_kwh or 0
                    bat_entladung = md.batterie_entladung_kwh or 0
                hausverbrauch = pv - md.einspeisung_kwh + md.netzbezug_kwh + bat_entladung - bat_ladung

                if hausverbrauch < -0.5:
                    ergebnisse.append(CheckErgebnis(
                        kategorie=kat, schwere=CheckSeverity.ERROR,
                        meldung=f"{prefix}: Energiebilanz ergibt negativen Hausverbrauch ({hausverbrauch:.1f} kWh)",
                        details=(
                            f"PV {pv:.0f} – Einspeisung {md.einspeisung_kwh:.0f} "
                            f"+ Netzbezug {md.netzbezug_kwh:.0f} "
                            f"+ Bat.Entladung {bat_entladung:.0f} "
                            f"– Bat.Ladung {bat_ladung:.0f} = {hausverbrauch:.1f} kWh. "
                            f"Häufige Ursachen: vertauschte Einspeisungs-/Netzbezugs-Sensoren "
                            f"im Mapping oder fehlende Batterie-Daten."
                        ),
                        link=md_link,
                    ))
                elif hat_speicher and (md.batterie_ladung_kwh is None or md.batterie_entladung_kwh is None):
                    # Bilanz rechnerisch positiv, aber Batterie-Daten fehlen → Warnung dass Wert unzuverlässig
                    pass  # bereits durch Check 0 abgedeckt

        if not ergebnisse:
            ergebnisse.append(CheckErgebnis(
                kategorie=kat, schwere=CheckSeverity.OK,
                meldung="Keine Auffälligkeiten in den Monatsdaten",
            ))

        return ergebnisse

    def _check_investition_monatsdaten(
        self,
        inv: Investition,
        name: str,
        pflicht_feld: str,
        feld_label: str,
        schwere: str,
        monatsdaten: list[Monatsdaten],
    ) -> list[CheckErgebnis]:
        """Prüft ob ein Pflichtfeld für alle erwarteten Monate in InvestitionMonatsdaten gefüllt ist.

        Erwartete Monate = alle Monatsdaten-Einträge ab anschaffungsdatum der Investition.
        """
        ergebnisse: list[CheckErgebnis] = []
        kat = CheckKategorie.INVESTITIONEN

        erwartete = self._erwartete_monate(inv, monatsdaten)
        if not erwartete:
            return ergebnisse

        imd_map = {
            (imd.jahr, imd.monat): (imd.verbrauch_daten or {})
            for imd in inv.monatsdaten
        }

        fehlend: list[str] = []
        for (jahr, monat) in erwartete:
            daten = imd_map.get((jahr, monat), {})
            if daten.get(pflicht_feld) is None:
                fehlend.append(f"{monat:02d}/{jahr}")

        if fehlend:
            monate_str = ", ".join(fehlend[:6])
            if len(fehlend) > 6:
                monate_str += f" (+{len(fehlend) - 6} weitere)"
            ergebnisse.append(CheckErgebnis(
                kategorie=kat, schwere=schwere,
                meldung=f"{name}: {feld_label} fehlt in {len(fehlend)} Monat(en)",
                details=monate_str,
                link="/einstellungen/monatsdaten",
            ))
        else:
            ergebnisse.append(CheckErgebnis(
                kategorie=kat, schwere=CheckSeverity.OK,
                meldung=f"{name}: Monatsdaten vollständig ({len(erwartete)} Monate)",
            ))

        return ergebnisse

    def _check_wp_monatsdaten(
        self, inv: Investition, name: str, param: dict, monatsdaten: list[Monatsdaten]
    ) -> list[CheckErgebnis]:
        """Prüft WP-Monatsdaten für alle erwarteten Monate ab anschaffungsdatum.

        Berücksichtigt getrennte_strommessung und prüft zusätzlich heizenergie_kwh.
        """
        ergebnisse: list[CheckErgebnis] = []
        kat = CheckKategorie.INVESTITIONEN

        erwartete = self._erwartete_monate(inv, monatsdaten)
        if not erwartete:
            return ergebnisse

        getrennte_strommessung = param.get("getrennte_strommessung", False)
        # Split-Klimaanlagen (wp_art="luft_luft") haben üblicherweise keinen
        # Wärmemengenzähler — die "Heizwärme fehlt"-Warnung wäre ein
        # Dauer-Falschpositiv. Stromverbrauch ist trotzdem Pflicht.
        ist_klima = param.get("wp_art") == "luft_luft"

        # #183: bei getrennter Strommessung wird der alte stromverbrauch_kwh-
        # Sensor in der Aggregation ignoriert. Wenn er trotzdem im Sensor-
        # Mapping steht, ist das überflüssig (und schreibt parallel Werte
        # in die JSON, die niemand mehr liest). INFO-Hinweis zum Entfernen.
        if getrennte_strommessung:
            anlage = getattr(inv, "anlage", None)
            sensor_mapping = (anlage.sensor_mapping if anlage else None) or {}
            inv_map = (sensor_mapping.get("investitionen") or {}).get(str(inv.id)) or {}
            felder = inv_map.get("felder") or {}
            alter_sensor = felder.get("stromverbrauch_kwh")
            if isinstance(alter_sensor, dict) and alter_sensor.get("strategie") == "sensor":
                ergebnisse.append(CheckErgebnis(
                    kategorie=kat, schwere=CheckSeverity.INFO,
                    meldung=(
                        f"{name}: Alter Gesamt-Stromverbrauch-Sensor "
                        f"({alter_sensor.get('sensor_id')}) ist bei aktivierter "
                        f"getrennter Strommessung obsolet"
                    ),
                    details=(
                        "Der Sensor wird in der Aggregation ignoriert — Gesamt-"
                        "Strom kommt aus Strom Heizen + Strom Warmwasser. Beim "
                        "nächsten Speichern des Sensor-Mappings wird der Eintrag "
                        "automatisch entfernt — kein Klick nötig."
                    ),
                ))

        imd_map = {
            (imd.jahr, imd.monat): (imd.verbrauch_daten or {})
            for imd in inv.monatsdaten
        }

        fehlend_strom: list[str] = []
        fehlend_heiz: list[str] = []

        for (jahr, monat) in erwartete:
            daten = imd_map.get((jahr, monat), {})
            label = f"{monat:02d}/{jahr}"

            if getrennte_strommessung:
                if daten.get("strom_heizen_kwh") is None and daten.get("strom_warmwasser_kwh") is None:
                    fehlend_strom.append(label)
            else:
                if daten.get("stromverbrauch_kwh") is None:
                    fehlend_strom.append(label)

            if not ist_klima and daten.get("heizenergie_kwh") is None:
                fehlend_heiz.append(label)

        if fehlend_strom:
            monate_str = ", ".join(fehlend_strom[:6])
            if len(fehlend_strom) > 6:
                monate_str += f" (+{len(fehlend_strom) - 6} weitere)"
            strom_label = "Strom Heizen/Warmwasser" if getrennte_strommessung else "Stromverbrauch"
            ergebnisse.append(CheckErgebnis(
                kategorie=kat, schwere=CheckSeverity.WARNING,
                meldung=f"{name}: {strom_label} fehlt in {len(fehlend_strom)} Monat(en)",
                details=monate_str,
                link="/einstellungen/monatsdaten",
            ))

        if fehlend_heiz:
            monate_str = ", ".join(fehlend_heiz[:6])
            if len(fehlend_heiz) > 6:
                monate_str += f" (+{len(fehlend_heiz) - 6} weitere)"
            ergebnisse.append(CheckErgebnis(
                kategorie=kat, schwere=CheckSeverity.INFO,
                meldung=f"{name}: Heizwärme fehlt in {len(fehlend_heiz)} Monat(en)",
                details=monate_str,
                link="/einstellungen/monatsdaten",
            ))

        if not fehlend_strom and not fehlend_heiz:
            ergebnisse.append(CheckErgebnis(
                kategorie=kat, schwere=CheckSeverity.OK,
                meldung=f"{name}: Monatsdaten vollständig ({len(erwartete)} Monate)",
            ))

        return ergebnisse
