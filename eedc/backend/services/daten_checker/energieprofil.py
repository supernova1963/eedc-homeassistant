"""
Daten-Checker — Energieprofil-Abdeckung, -Plausibilität & PV-Erfassung
(`EnergieprofilChecks`).

Reiner Move aus dem früheren Modul `daten_checker.py` (Tier-4 Achse C).
"""

from datetime import date
from typing import Optional

from sqlalchemy import select

from backend.models.anlage import Anlage
from backend.models.monatsdaten import Monatsdaten
from backend.utils.investition_filter import sort_investitionen_nach_typ
from backend.core.investition_parameter import ist_dienstlich
from backend.core.berechnungen import (
    summe_pv_bkw_kwh as _summe_pv_bkw_kwh,
    klassifiziere_pv_monat,
    PV_STATUS_OK,
    PV_STATUS_VERTEILT,
    PV_STATUS_TEIL_LUECKE,
    PV_STATUS_FEHLT,
)

from .kategorien import CheckErgebnis, CheckKategorie, CheckSeverity


# Datenquelle-Werte, die für eine manuell/importiert befüllte Monatsdaten-
# Historie stehen (Daten-Checker Achse B, project_datenchecker_konsistenz).
# Wenn eine Anlage so gepflegt wird, braucht eine Komponente KEINEN gemappten
# kumulativen kWh-Sensor — die Energieprofil-Abdeckung gilt dann als erfüllt
# (OK mit Quellen-Hinweis statt WARNING). Werte stammen aus den Import-/
# Wizard-Pfaden: custom_import (custom_import/apply.py), csv
# (csv_operations.py), json_import (json_operations.py), manuell/manual
# (monatsabschluss-Wizard).
MANUELLE_DATENQUELLEN: dict[str, str] = {
    "custom_import": "Custom-Import",
    "csv": "CSV-Import",
    "json_import": "JSON-Import",
    "manuell": "manuell",
    "manual": "manuell",
}


class EnergieprofilChecks:
    """Prüfungen rund um Energieprofil-Abdeckung, Counter-Spikes und PV-Erfassung."""

    # PR > 1.05 ist physikalisch unmöglich (mehr Energie raus als rein),
    # spez. Tagesertrag > kwp × 7 kWh entspricht > 7 Vollbenutzungsstunden —
    # in DE auch im Hochsommer extrem selten. Beides zusammen oder einzeln
    # über mehrere Tage = typisches Symptom Doppelerfassung (BKW im WR-Wert
    # enthalten + separates Mapping). Memory: feedback_grenze_externe_daten_diagnose.
    PR_PLAUSI_SCHWELLE = 1.05
    PR_PLAUSI_MINDESTTAGE = 3
    PR_PLAUSI_MINDEST_ANTEIL = 0.20
    PR_PLAUSI_FENSTER_TAGE = 30
    SPEZ_TAGES_ERTRAG_OBERGRENZE_KWH_PRO_KWP = 7.0

    # ─── Energieprofil-Abdeckung (Issue #135) ────────────────────────────

    def _check_energieprofil_abdeckung(
        self, anlage: Anlage, monatsdaten: Optional[list[Monatsdaten]] = None
    ) -> list[CheckErgebnis]:
        """
        Prüft welche kumulativen kWh-Zähler im sensor_mapping gesetzt sind.

        Issue #135: Ohne gemappte kumulative Zähler bleibt das Energieprofil
        für die betroffenen Kategorien leer (strikte NULL-Semantik). Der Check
        zeigt, welche Zähler fehlen und welche Energieprofil-Bereiche dadurch
        nicht funktionieren (Prognosen-IST, Heatmap, Lernfaktor, Monatsberichte).

        Achse B (project_datenchecker_konsistenz): Wer seine Monatsdaten per
        Custom-/CSV-/JSON-Import oder manuell pflegt, braucht keinen Sensor-
        Zähler. Liegt eine solche `datenquelle` in den Monatsdaten vor, gilt die
        Abdeckung als erfüllt — OK mit Quellen-Hinweis statt WARNING. Logik pro
        Komponente: (1) Sensor-Mapping → OK(Sensor), (2) sonst manuelle
        Datenquelle → OK(Quelle), (3) sonst → WARNING.
        """
        ergebnisse: list[CheckErgebnis] = []
        kat = CheckKategorie.ENERGIEPROFIL_ABDECKUNG

        sensor_mapping = anlage.sensor_mapping or {}
        basis = sensor_mapping.get("basis", {}) or {}
        inv_map = sensor_mapping.get("investitionen", {}) or {}

        # Achse B: Wird die Anlage manuell/importiert gepflegt? Erste passende
        # datenquelle liefert das Anwender-Label für den Quellen-Hinweis.
        manuelle_quelle: Optional[str] = None
        for md in (monatsdaten or []):
            label = MANUELLE_DATENQUELLEN.get((md.datenquelle or "").strip())
            if label:
                manuelle_quelle = label
                break

        def _has_zaehler(config: Optional[dict]) -> bool:
            if not isinstance(config, dict):
                return False
            return config.get("strategie") == "sensor" and bool(config.get("sensor_id"))

        # Basis: Einspeisung + Netzbezug
        fehlende_basis: list[str] = []
        if not _has_zaehler(basis.get("einspeisung")):
            fehlende_basis.append("Einspeisung")
        if not _has_zaehler(basis.get("netzbezug")):
            fehlende_basis.append("Netzbezug")

        if fehlende_basis and manuelle_quelle:
            ergebnisse.append(CheckErgebnis(
                kategorie=kat, schwere=CheckSeverity.OK,
                meldung=f"Basis-Zähler über {manuelle_quelle} befüllt",
                details=(
                    f"Einspeisung/Netzbezug ohne Sensor-Mapping, aber die "
                    f"Monatsdaten werden über {manuelle_quelle} gepflegt — "
                    f"Energieprofil-Abdeckung ist damit erfüllt."
                ),
            ))
        elif fehlende_basis:
            ergebnisse.append(CheckErgebnis(
                kategorie=kat, schwere=CheckSeverity.WARNING,
                meldung=f"Kein Basis-Zähler für: {', '.join(fehlende_basis)}",
                details=(
                    "Ohne kumulative kWh-Zähler bleibt der bilanzielle Verbrauch im "
                    "Energieprofil leer. Bitte im Sensor-Mapping-Wizard die kWh-Zähler "
                    "(nicht die leistung_w-Sensoren) eintragen."
                ),
                link="/einstellungen/sensor-mapping",
            ))
        else:
            ergebnisse.append(CheckErgebnis(
                kategorie=kat, schwere=CheckSeverity.OK,
                meldung="Basis-Zähler (Einspeisung + Netzbezug) gemappt",
            ))

        # Pro Investition prüfen.
        # Jeder Eintrag ist eine Liste von Alternativen — gemappt sein muss
        # mindestens EINE davon. Hintergrund: e-auto hat zwei akzeptierte
        # Schlüssel für den Gesamt-Ladung-Zähler (`verbrauch_kwh` aus dem
        # Field-Schema, `ladung_kwh` als kanonischer Helper-Name; beide werden
        # vom Snapshot-Service und get_eauto_ladung_kwh akzeptiert). Vorher
        # prüfte der Checker hartcodiert nur `ladung_kwh` und meldete trotz
        # korrekt gemapptem `verbrauch_kwh`-Sensor eine fehlende Abdeckung
        # (Joachim-PN 2026-05-02).
        erwartete_felder: dict[str, list[list[str]]] = {
            "pv-module": [["pv_erzeugung_kwh"]],
            "balkonkraftwerk": [["pv_erzeugung_kwh"]],
            "speicher": [["ladung_kwh"], ["entladung_kwh"]],
            "waermepumpe": [["stromverbrauch_kwh"]],
            "wallbox": [["ladung_kwh"]],
            "e-auto": [["verbrauch_kwh", "ladung_kwh"]],
        }

        fehlend_pro_komponente: list[tuple[str, str, list[str]]] = []
        gemappt_count = 0   # über Sensor-Mapping abgedeckt
        quelle_count = 0    # über manuelle/importierte Datenquelle abgedeckt

        # Reihenfolge nach Typ (#214 detLAN: WP vor Wallbox), nicht DB-ID
        heute = date.today()

        # Wallbox-Schwäche B (KONZEPT-WALLBOX-EAUTO.md »Bekannte Schwächen«):
        # Deckt eine aktive Wallbox mit gemapptem kWh-Zähler die Ladeenergie ab,
        # ist ein eigener E-Auto-kWh-Zähler redundant — Phase 2a führt die
        # Ladeenergie kanonisch an der Wallbox. Strukturelle Regel (Wallbox mit
        # Zähler vorhanden?), nicht magnitudenabhängig.
        wallbox_deckt_eauto_ladung = any(
            w.typ == "wallbox"
            and w.ist_aktiv_an(heute)
            and _has_zaehler(
                ((inv_map.get(str(w.id), {}) or {}).get("felder", {}) or {}).get("ladung_kwh")
            )
            for w in anlage.investitionen
        )

        for inv in sort_investitionen_nach_typ(anlage.investitionen):
            # Stilllegungsdatum respektieren (#608 MartyBr): stillgelegte
            # Komponente braucht keine Sensor-Mapping-Pflege mehr.
            if not inv.ist_aktiv_an(heute):
                continue
            erwartet = erwartete_felder.get(inv.typ)
            if not erwartet:
                continue  # sonstiges, wechselrichter etc. skippen

            # Dienstwagen: kein PV-Bezug, kein Verbrauchs-Tracking nötig.
            # Konsistent mit `_check_investitionen` (Zeile ~443), wo ROI-Checks
            # für Dienstwagen ebenfalls übersprungen werden. (Joachim-PN
            # 2026-05-04: ID.4 als Dienstwagen meldete trotzdem kWh-Counter
            # fehlt.)
            if inv.typ == "e-auto" and ist_dienstlich(inv):
                continue

            # Wallbox-Schwäche B: E-Auto-Ladeenergie ist bereits über den
            # Wallbox-kWh-Zähler gedeckt → kein eigener E-Auto-Zähler nötig.
            if inv.typ == "e-auto" and wallbox_deckt_eauto_ladung:
                continue

            # WP mit getrennter Strommessung (#183): hier zählen
            # `strom_heizen_kwh` und `strom_warmwasser_kwh` getrennt — das
            # Legacy-Gesamt-Feld `stromverbrauch_kwh` wird vom Aggregator
            # ohnehin ignoriert, wenn `getrennte_strommessung=True`. Ohne
            # diesen Zweig meldete der Checker bei korrekt konfiguriertem
            # Premium-Setup (dietmar1968 Forum-PN 2026-05-17) eine fehlende
            # Abdeckung trotz vollständig gemappten getrennten Sensoren.
            if inv.typ == "waermepumpe" and (inv.parameter or {}).get("getrennte_strommessung", False):
                erwartet = [["strom_heizen_kwh"], ["strom_warmwasser_kwh"]]

            inv_data = inv_map.get(str(inv.id), {}) or {}
            felder = inv_data.get("felder", {}) or {}
            fehlend = [
                " oder ".join(alts)
                for alts in erwartet
                if not any(_has_zaehler(felder.get(f)) for f in alts)
            ]

            if not fehlend:
                gemappt_count += 1
            elif manuelle_quelle:
                # Achse B: kein Sensor, aber Monatsdaten werden manuell/importiert
                # gepflegt → Abdeckung erfüllt (kein WARNING).
                quelle_count += 1
            else:
                fehlend_pro_komponente.append((inv.bezeichnung, inv.typ, fehlend))

        if fehlend_pro_komponente:
            gesamt = len(fehlend_pro_komponente) + gemappt_count + quelle_count
            details_parts = [
                f"{name} ({typ}): {', '.join(fehlend)}"
                for name, typ, fehlend in fehlend_pro_komponente
            ]
            ergebnisse.append(CheckErgebnis(
                kategorie=kat, schwere=CheckSeverity.WARNING,
                meldung=(
                    f"{len(fehlend_pro_komponente)} von {gesamt} "
                    "Komponenten ohne vollständige kWh-Zähler-Abdeckung"
                ),
                details=(
                    "Ohne kumulative Zähler bleibt das Energieprofil für diese "
                    "Komponenten leer. Betroffen sind Prognosen-IST, Heatmap, "
                    "Lernfaktor und Monatsberichte. Details: " + "; ".join(details_parts)
                ),
                link="/einstellungen/sensor-mapping",
            ))
        if gemappt_count > 0:
            # "Alle" nur wenn keine andere Quelle / kein Fehlend daneben steht
            prefix = "Alle " if (quelle_count == 0 and not fehlend_pro_komponente) else ""
            ergebnisse.append(CheckErgebnis(
                kategorie=kat, schwere=CheckSeverity.OK,
                meldung=f"{prefix}{gemappt_count} aktiven Komponenten haben kWh-Zähler gemappt",
            ))
        if quelle_count > 0:
            ergebnisse.append(CheckErgebnis(
                kategorie=kat, schwere=CheckSeverity.OK,
                meldung=f"{quelle_count} Komponente(n) über {manuelle_quelle} befüllt",
                details=(
                    f"Kein Sensor-Mapping nötig — die Monatsdaten dieser "
                    f"Komponenten werden über {manuelle_quelle} gepflegt."
                ),
            ))

        return ergebnisse

    # ─── Energieprofil-Plausibilität (Counter-Spikes) ─────────────────────

    async def _check_energieprofil_plausibilitaet(self, anlage: Anlage) -> list[CheckErgebnis]:
        """
        Erkennt Stundenwerte im TagesEnergieProfil, die physikalisch unmöglich sind
        (> Anlagenleistung × 1.5). Tritt typischerweise nach Update-Restarts auf,
        wenn der Counter-Snapshot-Service einen verzerrten kumulativen Wert speichert
        (z. B. der get_value_at-Off-by-one-Bug behoben in v3.25.10).

        Behebung: "Tag neu aggregieren" (für einzelne Tage) oder "Verlauf
        nachrechnen" mit aktiviertem Überschreiben (für längere Bereiche). Beide
        Pfade ziehen seit v3.25.x intern Resnap voran.
        """
        from backend.models.tages_energie_profil import TagesEnergieProfil
        from backend.services.snapshot.plausibility import (
            schwelle_pv_einspeisung_stunde_kwh,
        )
        from datetime import date, timedelta

        ergebnisse: list[CheckErgebnis] = []
        kat = CheckKategorie.ENERGIEPROFIL_PLAUSIBILITAET

        kwp = anlage.leistung_kwp or 0
        schwelle_kw = schwelle_pv_einspeisung_stunde_kwh(kwp)
        if schwelle_kw is None:
            # Ohne kWp keine sinnvolle Schwelle — Stammdaten-Check meldet das schon
            return ergebnisse

        # Nur die letzten 30 Tage prüfen (ältere Tage sind oft schon korrigiert
        # oder nicht mehr relevant für aktuelle Lernfaktor-Basis)
        bis = date.today()
        von = bis - timedelta(days=30)

        result = await self.db.execute(
            select(TagesEnergieProfil).where(
                TagesEnergieProfil.anlage_id == anlage.id,
                TagesEnergieProfil.datum >= von,
                TagesEnergieProfil.datum <= bis,
            ).order_by(TagesEnergieProfil.datum, TagesEnergieProfil.stunde)
        )
        zeilen = result.scalars().all()

        # Spike-Tage sammeln: Tag → list[(stunde, feld, wert)]
        spike_tage: dict[date, list[tuple[int, str, float]]] = {}
        for row in zeilen:
            for feld_name in ("pv_kw", "einspeisung_kw"):
                wert = getattr(row, feld_name, None)
                if wert is None:
                    continue
                if abs(wert) > schwelle_kw:
                    spike_tage.setdefault(row.datum, []).append(
                        (row.stunde, feld_name, wert)
                    )

        if not spike_tage:
            ergebnisse.append(CheckErgebnis(
                kategorie=kat, schwere=CheckSeverity.OK,
                meldung=f"Keine Counter-Spikes in den letzten 30 Tagen (Schwelle: {schwelle_kw:.1f} kW = {kwp:.1f} kWp × 1.5)",
            ))
            return ergebnisse

        # Pro Tag eine Warnung mit Detail-Auflistung der Spike-Stunden
        for datum_spike in sorted(spike_tage.keys(), reverse=True):
            spikes = spike_tage[datum_spike]
            details = "; ".join(
                f"{stunde:02d}:00 {feld}={wert:.1f} kW"
                for stunde, feld, wert in spikes
            )
            ergebnisse.append(CheckErgebnis(
                kategorie=kat, schwere=CheckSeverity.WARNING,
                meldung=f"Counter-Spike am {datum_spike.isoformat()}: {len(spikes)} Stundenwert(e) > {schwelle_kw:.1f} kW",
                details=(
                    f"Stunden mit physikalisch unmöglichem Wert: {details}. "
                    f"Häufige Ursache sind Update-Restarts während des Tages (Counter-Off-by-one). "
                    f"Behebung: 'Tag neu aggregieren' für genau diesen Tag (Reload-Symbol "
                    f"in der Tagesliste) — repariert SensorSnapshots + Aggregate in einem Schritt."
                ),
                link=f"/einstellungen/energieprofil?datum={datum_spike.isoformat()}",
            ))

        return ergebnisse

    def _check_pv_erzeugung(
        self, anlage: Anlage, monatsdaten: list[Monatsdaten]
    ) -> list[CheckErgebnis]:
        """Anlagenweite PV-Erzeugungs-Prüfung (kWp-Verteilung-Etappe).

        Pro erwartetem Monat wird die Quellenlage klassifiziert (SoT
        ``klassifiziere_pv_monat``): alle aktiven Module messen → OK; ein
        Gesamt-Aggregat (``Monatsdaten.pv_erzeugung_kwh``) deckt fehlende
        Strings über kWp-Verteilung ab → INFO; Teil-Lücke ohne Aggregat →
        WARNING; gar keine PV-Quelle → ERROR (Konvention Gernot 2026-06-06:
        nichts berechenbar = ERROR, konsistent mit „Kein Strompreis").

        Scope: PV-Module (Strings). Balkonkraftwerk behält die eigene Pro-
        Modul-Prüfung (eigener Einzel-Sensor, keine String-Verteilung).
        """
        ergebnisse: list[CheckErgebnis] = []
        kat = CheckKategorie.INVESTITIONEN
        heute = date.today()

        pv_module = [
            i for i in anlage.investitionen
            if i.typ == "pv-module" and i.ist_aktiv_an(heute)
        ]
        if not pv_module:
            return ergebnisse  # „keine PV-Module" meldet bereits _check_stammdaten

        # Erwartete Monate = Vereinigung der Pro-Modul-Erwartungen (jeweils ab
        # anschaffungsdatum, nur Monate mit Monatsdaten-Zeile).
        erwartete = sorted({
            m for inv in pv_module for m in self._erwartete_monate(inv, monatsdaten)
        })
        if not erwartete:
            return ergebnisse

        agg_map = {(md.jahr, md.monat): md.pv_erzeugung_kwh for md in monatsdaten}
        imd_map = {
            (inv.id, imd.jahr, imd.monat): (imd.verbrauch_daten or {})
            for inv in pv_module for imd in inv.monatsdaten
        }

        fehlt: list[str] = []
        teil_luecke: list[str] = []
        verteilt: list[str] = []
        ok_count = 0

        for (jahr, monat) in erwartete:
            aktive = [inv for inv in pv_module if inv.ist_aktiv_im_monat(jahr, monat)]
            if not aktive:
                continue
            n_gemessen = sum(
                1 for inv in aktive
                if imd_map.get((inv.id, jahr, monat), {}).get("pv_erzeugung_kwh") is not None
            )
            status = klassifiziere_pv_monat(
                n_aktive_module=len(aktive),
                n_gemessen=n_gemessen,
                aggregat_kwh=agg_map.get((jahr, monat)),
            )
            label = f"{monat:02d}/{jahr}"
            if status == PV_STATUS_OK:
                ok_count += 1
            elif status == PV_STATUS_VERTEILT:
                verteilt.append(label)
            elif status == PV_STATUS_TEIL_LUECKE:
                teil_luecke.append(label)
            else:  # PV_STATUS_FEHLT
                fehlt.append(label)

        def _monate(liste: list[str]) -> str:
            txt = ", ".join(liste[:6])
            if len(liste) > 6:
                txt += f" (+{len(liste) - 6} weitere)"
            return txt

        if fehlt:
            ergebnisse.append(CheckErgebnis(
                kategorie=kat, schwere=CheckSeverity.ERROR,
                meldung=f"PV-Erzeugung fehlt in {len(fehlt)} Monat(en)",
                details=(
                    "Keine PV-Quelle (weder Pro-Modul-Werte noch ein "
                    f"Gesamtwert): {_monate(fehlt)}"
                ),
                link="/einstellungen/monatsdaten",
            ))
        if teil_luecke:
            ergebnisse.append(CheckErgebnis(
                kategorie=kat, schwere=CheckSeverity.WARNING,
                meldung=f"PV-Erzeugung unvollständig in {len(teil_luecke)} Monat(en)",
                details=(
                    "Nur ein Teil der Strings erfasst und kein Gesamtwert zum "
                    f"Verteilen hinterlegt: {_monate(teil_luecke)}"
                ),
                link="/einstellungen/monatsdaten",
            ))
        if verteilt:
            ergebnisse.append(CheckErgebnis(
                kategorie=kat, schwere=CheckSeverity.INFO,
                meldung=f"PV-Erzeugung über kWp-Anteil geschätzt in {len(verteilt)} Monat(en)",
                details=(
                    "Gesamtwert wird anteilig nach kWp auf die Strings verteilt — "
                    f"Pro-String-Genauigkeit eingeschränkt: {_monate(verteilt)}"
                ),
                link="/einstellungen/monatsdaten",
            ))
        if not fehlt and not teil_luecke and not verteilt and ok_count:
            ergebnisse.append(CheckErgebnis(
                kategorie=kat, schwere=CheckSeverity.OK,
                meldung=f"PV-Erzeugung: Monatsdaten vollständig ({ok_count} Monate)",
            ))

        return ergebnisse

    async def _check_pv_ueber_erfassung(self, anlage: Anlage) -> list[CheckErgebnis]:
        """
        Doppelerfassungs-Verdacht aus eedc-eigenen Tageswerten.

        Zwei unabhängige Signale aus `TagesZusammenfassung` der letzten 30 Tage:
        - PR > 1.05 an ≥ 3 Tagen UND ≥ 20 % der Tage mit verfügbarem PR-Wert
        - Spez. Tagesertrag > 7 kWh/kWp an ≥ 3 Tagen

        Diagnose-Charakter, kein Cap und keine Reparatur-Action — der Anwender
        muss am Sensor-Mapping entscheiden (Memory: feedback_kein_grosser_heiler_knopf).
        """
        from datetime import date, timedelta
        from backend.models.tages_energie_profil import TagesZusammenfassung

        kat = CheckKategorie.PV_UEBER_ERFASSUNG.value
        ergebnisse: list[CheckErgebnis] = []

        kwp = anlage.leistung_kwp or 0
        if kwp <= 0:
            return ergebnisse  # Stammdaten-Check meldet das schon

        bis = date.today()
        von = bis - timedelta(days=self.PR_PLAUSI_FENSTER_TAGE)

        result = await self.db.execute(
            select(TagesZusammenfassung).where(
                TagesZusammenfassung.anlage_id == anlage.id,
                TagesZusammenfassung.datum >= von,
                TagesZusammenfassung.datum <= bis,
            )
        )
        tz_list = result.scalars().all()
        if not tz_list:
            return ergebnisse

        pr_ueberschreitungen: list[tuple[date, float]] = []
        spez_ertrag_ueberschreitungen: list[tuple[date, float]] = []
        tage_mit_pr = 0
        for tz in tz_list:
            if tz.performance_ratio is not None:
                tage_mit_pr += 1
                if tz.performance_ratio > self.PR_PLAUSI_SCHWELLE:
                    pr_ueberschreitungen.append((tz.datum, tz.performance_ratio))

            tages_pv = _summe_pv_bkw_kwh(tz.komponenten_kwh)
            if tages_pv > 0:
                spez = tages_pv / kwp
                if spez > self.SPEZ_TAGES_ERTRAG_OBERGRENZE_KWH_PRO_KWP:
                    spez_ertrag_ueberschreitungen.append((tz.datum, spez))

        anzahl_pr_drueber = len(pr_ueberschreitungen)
        anteil_pr = anzahl_pr_drueber / tage_mit_pr if tage_mit_pr > 0 else 0.0
        pr_signal = (
            anzahl_pr_drueber >= self.PR_PLAUSI_MINDESTTAGE
            and anteil_pr >= self.PR_PLAUSI_MINDEST_ANTEIL
        )
        spez_signal = len(spez_ertrag_ueberschreitungen) >= self.PR_PLAUSI_MINDESTTAGE

        if not pr_signal and not spez_signal:
            return ergebnisse

        # Auflistung der jüngsten Treffer (max 5 pro Marker)
        pr_recent = sorted(pr_ueberschreitungen, reverse=True)[:5]
        spez_recent = sorted(spez_ertrag_ueberschreitungen, reverse=True)[:5]

        marker_zeilen: list[str] = []
        if pr_signal:
            beispiele = ", ".join(f"{d.isoformat()}: PR={pr:.2f}" for d, pr in pr_recent)
            marker_zeilen.append(
                f"Performance Ratio > {self.PR_PLAUSI_SCHWELLE} an "
                f"{anzahl_pr_drueber} von {tage_mit_pr} Tagen ({beispiele})"
            )
        if spez_signal:
            beispiele = ", ".join(f"{d.isoformat()}: {s:.1f} kWh/kWp" for d, s in spez_recent)
            marker_zeilen.append(
                f"Spez. Tagesertrag > {self.SPEZ_TAGES_ERTRAG_OBERGRENZE_KWH_PRO_KWP:.0f} kWh/kWp "
                f"an {len(spez_ertrag_ueberschreitungen)} Tagen ({beispiele})"
            )

        ergebnisse.append(CheckErgebnis(
            kategorie=kat,
            schwere=CheckSeverity.WARNING.value,
            meldung="Verdacht auf PV-Doppelerfassung (PR > 1 oder spez. Ertrag zu hoch)",
            details=(
                f"Diagnose-Marker aus den letzten {self.PR_PLAUSI_FENSTER_TAGE} Tagen:\n"
                + "\n".join(f"• {zeile}" for zeile in marker_zeilen) + "\n\n"
                "Häufige Ursache: Der WR-Smart-Meter misst AC-seitig nach dem "
                "Einspeisepunkt eines Balkonkraftwerks — die BKW-Erzeugung ist "
                "im WR-Wert bereits enthalten, ein separates BKW-Mapping zählt "
                "sie nochmal.\n\n"
                "Prüfen: Sensor-Mapping unter Investitionen → BKW.\n"
                "Test-Variante: BKW-Mapping temporär abklemmen und schauen, "
                "ob PR und Tagesertrag in den physikalischen Bereich zurückkommen."
            ),
        ))

        return ergebnisse
