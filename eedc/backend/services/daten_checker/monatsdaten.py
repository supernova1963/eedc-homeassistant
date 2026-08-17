"""
Daten-Checker — Monatsdaten-Vollständigkeit & -Plausibilität (`MonatsdatenChecks`).

Reiner Move aus dem früheren Modul `daten_checker.py` (Tier-4 Achse C).
"""

from datetime import date
from typing import Optional

from backend.core.berechnungen.spez_ertrag import PV_ERZEUGER_TYPEN
from backend.core.field_definitions import get_speicher_netzladung_kwh
from backend.core.berechnungen.erzeuger_traeger import erzeuger_traeger
from backend.core.investition_kennwerte import get_erzeuger_kwp
from backend.core.monats_luecken import ermittle_start_anker
from backend.core.investition_parameter import ist_luft_luft_waermepumpe
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

    async def _tages_pv_summe_monat(
        self, anlage_id: int, jahr: int, monat: int,
    ) -> Optional[float]:
        """Σ der gespeicherten PV-Tageswerte eines Monats (TagesZusammenfassung).

        Nachlauf v4.0.3: der **Diskriminator** für „der Monat wurde nie
        nachgezogen". Nach einer Tages-Reparatur stehen die Tage voll da,
        während der Monatswert auf seinem alten (oder leeren) Stand bleibt —
        genau der Zustand, in dem Prüfung 3/3b sonst die falsche Ursache zuerst
        nennt („Sensoren vertauscht" bzw. „ungepflegte Netzladung").

        Bewusst **lazy je Monat** statt einer Vorab-Query über die ganze
        Historie: aufgerufen wird nur, wenn eine der beiden Prüfungen ohnehin
        anschlägt — in aller Regel also gar nicht.

        Returns:
            Σ kWh, oder ``None`` wenn für den Monat keine Tageszeilen
            existieren (dann gibt es nichts zu vergleichen).
        """
        from sqlalchemy import select, extract
        from backend.core.berechnungen import summe_pv_bkw_kwh
        from backend.models.tages_energie_profil import TagesZusammenfassung

        result = await self.db.execute(
            select(TagesZusammenfassung).where(
                TagesZusammenfassung.anlage_id == anlage_id,
                extract("year", TagesZusammenfassung.datum) == jahr,
                extract("month", TagesZusammenfassung.datum) == monat,
            )
        )
        zeilen = list(result.scalars().all())
        if not zeilen:
            return None
        return sum(summe_pv_bkw_kwh(tz.komponenten_kwh or {}) for tz in zeilen)

    @staticmethod
    def _nachzug_hinweis(tages_pv: Optional[float], monats_pv: Optional[float]) -> Optional[str]:
        """Detail-Vorspann, wenn die Tageswerte den Monatswert deutlich übersteigen.

        Schwelle: ≥ 20 % **und** ≥ 20 kWh über dem Monatswert. Beides zusammen,
        damit weder die normale Rundungs-/Boundary-Drift noch ein kleiner
        Wintermonat den Hinweis auslöst.
        """
        if tages_pv is None or monats_pv is None:
            return None
        if tages_pv <= max(monats_pv * 1.2, monats_pv + 20.0):
            return None
        return (
            f"Wahrscheinlichste Ursache zuerst: die Tageswerte dieses Monats "
            f"summieren sich bereits auf {tages_pv:.0f} kWh PV, der gespeicherte "
            f"Monatswert steht aber bei {monats_pv:.0f} kWh. Die Tage wurden also "
            f"nachgetragen oder repariert, der Monatswert nie nachgezogen. "
            f"Weg dorthin: Einstellungen → Integration → Statistik-Import, "
            f"„Vorschau laden“ — bereits belegte Monate stehen dort unter "
            f"„Konflikte“ und sind zum Überschreiben vorausgewählt, also vor "
            f"dem Import einmal durchsehen. "
            f"Erst wenn das nichts ändert, kommen die folgenden Ursachen infrage. "
        )

    # Ab diesem Zuwachs an installierter Erzeugerleistung gilt ein
    # Einspeise-Sprung als ausgebaut-bedingt (#362). 10 % ist die Grenze, ab
    # der ein Zubau mehr ist als eine korrigierte Nachkommastelle.
    AUSBAU_SCHWELLE = 1.10

    @staticmethod
    def _erzeugung_ausgebaut(
        anlage: Anlage, vorjahr: Monatsdaten, md: Monatsdaten
    ) -> bool:
        """Ist zwischen Vergleichsmonat und geprüftem Monat Erzeugerleistung
        dazugekommen? (#362 kingcap1)

        Dann erklärt der Ausbau einen Einspeise-Sprung, und die Prüfung setzt
        für dieses Monatspaar aus, statt die Schwelle zu skalieren. Der Grund
        ist strukturell: Die Einspeisung ist eine **Differenzgröße**
        (Erzeugung − Eigenverbrauch). Bleibt der Verbrauch gleich, landet vom
        Zubau fast alles im Netz — kingcap1s Anlage wuchs um das Vierfache,
        seine Mai-Einspeisung um das Fünfzehnfache (61 → 888 kWh). Ein aus der
        kWp abgeleiteter Erwartungsfaktor wäre damit geraten, nicht gerechnet.

        Nur Erzeuger-Typen zählen, gelesen über den SoT-Helper
        `get_erzeuger_kwp` (ADR-002/P3-a — die kWp steht je nach Herkunft in
        der Spalte oder im `parameter`-JSON). Schrumpft die Leistung
        (Stilllegung), ist es kein Ausbau: dann ist ein Sprung erst recht
        auffällig und die Prüfung greift unverändert.
        """
        erzeuger = [
            i for i in (anlage.investitionen or [])
            if i.typ in ("pv-module", "balkonkraftwerk")
        ]
        if not erzeuger:
            return False

        def _kwp(jahr: int, monat: int) -> float:
            # N-266: Selektor NACH dem Monatsfilter — ein Balkonkraftwerk mit
            # Modul-Kindern hat seine kWp abgetreten, und in Monaten VOR der
            # Anschaffung der Kinder trägt es sie noch selbst. Ohne den
            # Selektor sähe der Ausbau-Vergleich einen Sprung, den es nie gab.
            return sum(
                get_erzeuger_kwp(i)
                for i in erzeuger_traeger(
                    [i for i in erzeuger if i.ist_aktiv_im_monat(jahr, monat)]
                )
            )

        kwp_vorher = _kwp(vorjahr.jahr, vorjahr.monat)
        if kwp_vorher <= 0:
            return False
        return _kwp(md.jahr, md.monat) >= kwp_vorher * MonatsdatenChecks.AUSBAU_SCHWELLE

    # Verbraucher, deren Zubau den Netzbezug strukturell hebt. `sonstiges`
    # steht nicht in der Liste, weil der Typ beides sein kann — er kommt über
    # die Kategorie dazu (`kategorie == "verbraucher"`, dieselbe Unterscheidung
    # wie in `core/berechnungen/imd_monatsaggregat.py`).
    VERBRAUCHER_TYPEN = ("waermepumpe", "e-auto", "wallbox")

    @staticmethod
    def _verbrauch_ausgebaut(
        anlage: Anlage, vorjahr: Monatsdaten, md: Monatsdaten
    ) -> bool:
        """Ist zwischen Vergleichsmonat und geprüftem Monat ein netzbezugs-
        hebender Verbraucher dazugekommen? (Gegenstück zu `_erzeugung_ausgebaut`)

        Der Ausbau-Gedanke aus #362 galt bis dahin nur für die Einspeisung: ein
        Erzeuger-Zubau erklärt ihren Sprung, ein Verbraucher-Zubau erklärte den
        Netzbezugs-Sprung nicht — obwohl der Kommentar an der Prüfstelle ihn
        selbst benannte („er wächst mit neuen Verbrauchern"). Wer im Mai eine
        Wärmepumpe einbaut, bekommt im Folgejahr eine WARNING über eine
        Verdreifachung, die er selbst herbeigeführt hat und nicht auflösen kann;
        das Handbuch riet ihm bis dahin, sie zu „akzeptieren" — genau das, was
        ein Daten-Checker-Hinweis nicht verlangen darf
        ([[feedback_daten_checker_kein_akzeptiert]], Präzedenz #240).

        **Gezählt wird die Anzahl, nicht eine Leistung.** Verbraucher haben
        keine gemeinsame Kennzahl (WP: Heizleistung, Wallbox: kW, E-Auto:
        Akku-kWh), und aus keiner davon ließe sich ein Erwartungsfaktor
        rechnen — er wäre geraten. Die Prüfung setzt deshalb für das Monatspaar
        aus, statt die Schwelle zu skalieren; das ist dieselbe Entscheidung, die
        `_erzeugung_ausgebaut` für die kWp-Seite begründet.

        **Ein Dienstwagen zählt mit.** Der Filter, der ihn aus den Finanzen
        heraushält ([[feedback_dienstwagen_alle_checks]]), gilt hier nicht: er
        lädt physisch aus demselben Netzanschluss, und die Frage ist eine
        Mengen-, keine Kostenfrage.

        Ein Austausch ist kein Zubau (alte WP stillgelegt, neue angeschafft →
        Anzahl gleich), und eine schrumpfende Ausstattung erst recht nicht —
        dann ist ein Netzbezugs-Sprung besonders auffällig und die Prüfung
        greift unverändert.
        """
        def _ist_verbraucher(inv) -> bool:
            if inv.typ in MonatsdatenChecks.VERBRAUCHER_TYPEN:
                return True
            if inv.typ == "sonstiges":
                return (getattr(inv, "parameter", None) or {}).get("kategorie") == "verbraucher"
            return False

        verbraucher = [i for i in (anlage.investitionen or []) if _ist_verbraucher(i)]
        if not verbraucher:
            return False

        def _anzahl(jahr: int, monat: int) -> int:
            return sum(1 for i in verbraucher if i.ist_aktiv_im_monat(jahr, monat))

        return _anzahl(md.jahr, md.monat) > _anzahl(vorjahr.jahr, vorjahr.monat)

    # ─── Monatsdaten Vollständigkeit ─────────────────────────────────────

    def _check_geraetewerte_ohne_monatszeile(
        self, anlage: Anlage, monatsdaten: list[Monatsdaten]
    ) -> list[CheckErgebnis]:
        """Messwerte je Komponente für Monate ohne Zählerzeile (#349).

        **Warum das eine eigene Meldung braucht.** Ein Monat ohne
        ``Monatsdaten``-Zeile verschwindet aus jeder Liste — die hängen alle
        daran. Die Messwerte je Komponente stehen in einer anderen Tabelle und
        bleiben. Sichtbar wurde das erst beim nächsten Import, und zwar als
        Meldung über die *Wirkung* statt über die Ursache: „Felder wurden durch
        manuell gepflegte Werte geschützt". Der Melder suchte den Fehler bei
        sich.

        ⚠ **Die Meldung darf die Ursache NICHT benennen** (12.08.). Sie stand
        bis dahin auf „Der Monat wurde gelöscht" — der Zustand entsteht aber auf
        mehreren Wegen, und nachträglich sind sie nicht zu unterscheiden:

        * **Monat gelöscht, Gerätewerte behalten** — die *Vorgabe* unseres
          eigenen Lösch-Dialogs (``services/monat_loeschen.py``).
        * **HA-Statistik-Import ohne Zähler-Sensoren**: ``ha_statistics.py``
          legt die Monatszeile nur an, wenn Einspeisung oder Netzbezug
          mitimportiert werden — wer nur Erzeuger-Sensoren gemappt hat, bekommt
          Gerätewerte ohne Zeile.
        * **Cloud-Import einer Station ohne Smartmeter**: dann fehlen die
          Hauszähler-Größen, und der Import sagt es (``import_hauszaehler.py``).

        Kein Weg mehr ist der **Monatsabschluss** (legt immer zuerst die
        ``Monatsdaten``-Zeile an, ``monatsabschluss/wizard.py``) und seit
        12.08. auch nicht mehr der **Stationsimport mit** Smartmeter.

        Bewusst **WARNING statt ERROR**: die Daten sind nicht falsch, sie sind
        nur unerreichbar geworden. Der Link führt direkt in das Formular
        **dieses** Monats — Nachtragen ist der Regelfall, Löschen die Ausnahme.
        """
        ergebnisse: list[CheckErgebnis] = []
        kat = CheckKategorie.GERAETEWERTE_OHNE_MONATSZEILE

        vorhandene = {(md.jahr, md.monat) for md in monatsdaten}

        # Je verwaistem Monat: wie viele Komponenten hängen daran?
        verwaist: dict[tuple[int, int], list[str]] = {}
        for inv in anlage.investitionen:
            for imd in inv.monatsdaten:
                schluessel = (imd.jahr, imd.monat)
                if schluessel in vorhandene:
                    continue
                # Eine leere Zeile ist kein Fund — sie weist auch keinen
                # Import ab. Gemeldet wird nur, was wirklich einen Wert trägt.
                if not any(v is not None for v in (imd.verbrauch_daten or {}).values()):
                    continue
                verwaist.setdefault(schluessel, []).append(
                    inv.bezeichnung or f"#{inv.id}"
                )

        for (jahr, monat), komponenten in sorted(verwaist.items()):
            namen = ", ".join(sorted(komponenten)[:4])
            if len(komponenten) > 4:
                namen += f" (+{len(komponenten) - 4} weitere)"
            ergebnisse.append(CheckErgebnis(
                kategorie=kat, schwere=CheckSeverity.WARNING,
                meldung=(
                    f"{monat:02d}/{jahr}: Messwerte von {len(komponenten)} "
                    "Komponente(n) ohne Monatszeile"
                ),
                details=(
                    f"Für diesen Monat liegen Messwerte einzelner Geräte vor "
                    f"({namen}), aber keine Zählerzeile mit Einspeisung und "
                    "Netzbezug. Die Werte zählen in Cockpit und Auswertungen "
                    "mit, der Monat erscheint aber in keiner Liste und weist "
                    "einen erneuten Import ab. Trage den Monat nach — die "
                    "Gerätewerte gehören dann wieder dazu. Nur wenn sie gar "
                    "nicht mehr gebraucht werden, entferne sie."
                ),
                # Deep-Link auf das Formular GENAU dieses Monats (Muster
                # `?erfassen=YYYY-MM`, wie die Status-Fusszeile). Der bisherige
                # Link zeigte auf die Liste — dort steht der Monat zwar als
                # offene Zeile, der Anwender musste ihn aber selbst suchen.
                link=f"/einstellungen/daten?erfassen={jahr}-{monat:02d}",
                action_kind="geraetewerte_loeschen",
                action_params={"anlage_id": anlage.id, "jahr": jahr, "monat": monat},
                action_label="Messwerte entfernen",
            ))

        return ergebnisse

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

        # N-243: über den SoT statt einer dritten eigenen Ableitung. Bis
        # 2026-08-13 rechnete dieser Check „Anlagendatum → erste Zeile" und
        # kannte die Investitionen gar nicht, während `core/monats_luecken.py`
        # (und sein Frontend-Spiegel) „frühestes Anschaffungsdatum → …"
        # rechnete. Zwei Antworten auf dieselbe Frage: Bei van sagte der Sprung
        # „Sep 2016", der Checker etwas anderes. Jetzt eine Quelle für alle drei
        # Sichten ([[feedback_aggregations_drift]]).
        anker = ermittle_start_anker(
            anlage.installationsdatum,
            [
                inv.anschaffungsdatum for inv in anlage.investitionen
                if inv.typ in PV_ERZEUGER_TYPEN
            ],
            {(md.jahr, md.monat) for md in monatsdaten},
        )
        if anker is None:
            return ergebnisse
        start_jahr, start_monat = anker

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
            # ⚑ FEHLER, nicht Warnung (Bewertungsgrenze E4a, 2026-08-16). Einspeisung
            # und Netzbezug sind die Basis-Daten: Ohne sie gibt es keine Bilanz, und
            # ohne Bilanz weiß eedc nicht, woher der Strom eines Geräts kam. Eine
            # fehlende Einspeisung liest `direktverbrauch = max(0, PV − Einspeisung −
            # Speicherladung)` als 0 — die ganze Erzeugung gilt dann als
            # Eigenverbrauch und wird mit dem Netz- statt dem Einspeisepreis
            # bewertet. An einem echten Monat gemessen: 621,83 € statt 281,76 €.
            # Die Zahl war also nicht ungenau, sondern systematisch zu gut; deshalb
            # ist ein fehlender Monat ab dem Anker kein Schönheitsfehler.
            # Der auflösende Schritt steht im Link (P-6): der Monatsabschluss
            # genau dieses Monats.
            for jahr, monat in fehlende[:12]:
                ergebnisse.append(CheckErgebnis(
                    kategorie=kat, schwere=CheckSeverity.ERROR,
                    meldung=f"{monat:02d}/{jahr} fehlt",
                    link=f"/monatsabschluss/{anlage.id}/{jahr}/{monat}",
                ))
            if len(fehlende) > 12:
                ergebnisse.append(CheckErgebnis(
                    kategorie=kat, schwere=CheckSeverity.ERROR,
                    meldung=f"... und {len(fehlende) - 12} weitere Monate fehlen",
                    link="/einstellungen/monatsdaten",
                ))

        return ergebnisse

    # ─── Monatsdaten Plausibilität ───────────────────────────────────────

    async def _check_monatsdaten_plausibilitaet(
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
            pv_erzeugung_map = await self._get_pv_erzeugung_map(anlage)
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
        speicher_imd_netzladung: dict[tuple[int, int], float] = {}  # (jahr,monat) → Netzladung
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
                        # Netzladung (Arbitrage) getrennt mitführen: sie kommt
                        # NICHT aus der PV und darf im Verwendungs-Stapel (N51)
                        # nicht gegen die Erzeugung gerechnet werden.
                        speicher_imd_netzladung[key] = (
                            speicher_imd_netzladung.get(key, 0.0)
                            + get_speicher_netzladung_kwh(daten)
                        )
        speicher_imd_monate = set(speicher_imd_bat.keys())

        for md in monatsdaten:
            prefix = f"{md.monat:02d}/{md.jahr}"
            md_link = f"/monatsabschluss/{anlage.id}/{md.jahr}/{md.monat}"

            # PV-Erzeugung des Monats aus dem Read-time-SoT (Messwerte +
            # Aggregat-Lückenfüllung). `None` heißt „nicht auflösbar", nicht
            # „0" — die PV-abhängigen Prüfungen unten überspringen den Monat
            # dann, statt mit einer Teilsumme oder einer 0 zu rechnen.
            pv_erzeugung = pv_erzeugung_map.get((md.jahr, md.monat))

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

            # Diskriminator für 3 + 3b: stehen in den Tageswerten deutlich mehr
            # kWh als im Monatswert, wurde der Monat schlicht nie nachgezogen —
            # dann ist die sonst zuerst genannte Ursache falsch (coolxmad #353).
            # Lazy: nur berechnen, wenn eine der beiden Prüfungen anschlägt.
            nachzug: Optional[str] = None
            nachzug_geprueft = False

            async def _hole_nachzug_hinweis() -> Optional[str]:
                nonlocal nachzug, nachzug_geprueft
                if not nachzug_geprueft:
                    nachzug_geprueft = True
                    nachzug = self._nachzug_hinweis(
                        await self._tages_pv_summe_monat(anlage.id, md.jahr, md.monat),
                        pv_erzeugung,
                    )
                return nachzug

            # 3. Einspeisung > PV-Erzeugung
            if (
                pv_erzeugung is not None
                and pv_erzeugung > 0
                and md.einspeisung_kwh is not None
                and md.einspeisung_kwh > pv_erzeugung
            ):
                details_3 = (
                    "Einspeisung kann nicht höher als die Erzeugung sein. "
                    "Häufigste Ursache: Einspeisungs- und Netzbezugs-Sensor "
                    "sind im Sensor-Mapping vertauscht (oder das Vorzeichen "
                    "eines kombinierten Netz-Sensors ist invertiert)."
                )
                vorspann = await _hole_nachzug_hinweis()
                ergebnisse.append(CheckErgebnis(
                    kategorie=kat, schwere=CheckSeverity.ERROR,
                    meldung=f"{prefix}: Einspeisung ({md.einspeisung_kwh:.0f} kWh) > PV-Erzeugung ({pv_erzeugung:.0f} kWh)",
                    details=(vorspann or "") + details_3,
                    link=md_link,
                ))

            # 3b. Verwendungs-Stapel > Erzeugung (N51, Gernot 2026-07-29)
            #
            # Prüfung 3 vergleicht nur die Einspeisung mit der Erzeugung. Was
            # in den Speicher geladen wurde, kam aber ebenfalls aus der PV —
            # AUSSER dem Arbitrage-Anteil, der aus dem Netz stammt. Übersteigt
            # `Einspeisung + (Speicherladung − Netzladung)` die Erzeugung, ist
            # eine der drei Zahlen falsch.
            #
            # **Bewusst als FRAGE und als WARNING**, nicht als Fehler: der
            # häufigste Auslöser ist eine ungepflegte Netzladung — wer nachts
            # billig lädt und das nicht erfasst, bekommt hier einen ehrlichen
            # Hinweis statt einer Anschuldigung. Rein diagnostisch: die Meldung
            # ändert keine Berechnung und keine Anzeige.
            #
            # Nur wenn PV-Ladung > 0, sonst wäre es eine zweite (und schwächere)
            # Meldung über denselben Sachverhalt wie Prüfung 3.
            bat_ladung_monat, _ = speicher_imd_bat.get((md.jahr, md.monat), (0.0, 0.0))
            pv_ladung_speicher = max(
                0.0,
                bat_ladung_monat - speicher_imd_netzladung.get((md.jahr, md.monat), 0.0),
            )
            if (
                pv_erzeugung is not None
                and pv_erzeugung > 0
                and md.einspeisung_kwh is not None
                and pv_ladung_speicher > 0
            ):
                stapel = md.einspeisung_kwh + pv_ladung_speicher
                # Toleranz: Zählerstände werden je Quelle gerundet, und die drei
                # Zahlen kommen aus verschiedenen Sensoren mit eigenen Messfehlern.
                toleranz = max(5.0, pv_erzeugung * 0.02)
                if stapel > pv_erzeugung + toleranz:
                    vorspann = await _hole_nachzug_hinweis()
                    ergebnisse.append(CheckErgebnis(
                        kategorie=kat, schwere=CheckSeverity.WARNING,
                        meldung=(
                            f"{prefix}: mehr PV verwendet als erzeugt? "
                            f"Einspeisung ({md.einspeisung_kwh:.0f}) + Speicherladung aus PV "
                            f"({pv_ladung_speicher:.0f}) = {stapel:.0f} kWh, "
                            f"erzeugt wurden {pv_erzeugung:.0f} kWh"
                        ),
                        details=(vorspann or "") + (
                            "Beides kommt aus derselben Erzeugung — zusammen kann es "
                            "nicht mehr sein als die PV geliefert hat. Drei häufige "
                            "Ursachen, in dieser Reihenfolge: (1) Der Speicher wird "
                            "auch aus dem Netz geladen (Arbitrage/Notladung), aber das "
                            "Feld „Ladung aus Netz“ ist nicht gepflegt — dann ist nur "
                            "die Zuordnung unvollständig, nicht die Energie. "
                            "(2) Die Erzeugung ist zu niedrig erfasst, etwa weil ein "
                            "String-Sensor im Monat ausgesetzt hat. (3) Einspeisung "
                            "und Netzbezug sind vertauscht (dann meldet die Prüfung "
                            "darüber meist zusätzlich). Rein diagnostisch — es wird "
                            "nichts automatisch korrigiert."
                        ),
                        link=md_link,
                    ))

            # 4. Beide Kernfelder 0
            # ⚑ Der Text sagt seit 2026-08-16, was gilt, WENN MAN NICHTS TUT
            # (P-6). Vorher stand hier als vollständige Begründung
            # „Wahrscheinlich fehlende Daten" — für eine Anlage ohne
            # Netzanschluss oder einen Monat außer Betrieb ist die 0 aber
            # richtig, und der Befund war für sie durch keine Eingabe
            # abstellbar: die P-6-Falle. Dasselbe Muster wie beim
            # WP-Spezialtarif-Hinweis und bei „Tarif ohne Einspeisevergütung"
            # — der Befund bleibt stehen, sagt aber, dass er in diesem Fall
            # eine Auskunft ist und kein Mangel.
            #
            # ⚠ Bewusst KEIN Stammdaten-Schalter „Inselanlage": Er wäre die
            # richtige Bauform (Tatsachenaussage, widerlegbar über Netzbezug
            # > 0 — das N-235-Muster), zöge aber die Finanzseite nach sich
            # (eedc bewertet Eigenverbrauch als eingesparten Netzbezug; eine
            # Insel spart nichts ein) und bedient eine Gruppe, für die es
            # keinen einzigen bekannten Anwender gibt (Gernot, 16.08.).
            # Trigger für den Schalter: ein echter Melder mit Insel- oder
            # Notstromanlage, oder ein zweiter Check, der dieselbe Erklärung
            # bräuchte — ab dem zweiten Abnehmer trägt sich eine
            # Stammdaten-Angabe, für einen Textfall nicht.
            if md.einspeisung_kwh == 0 and md.netzbezug_kwh == 0:
                ergebnisse.append(CheckErgebnis(
                    kategorie=kat, schwere=CheckSeverity.WARNING,
                    meldung=f"{prefix}: Einspeisung und Netzbezug sind beide 0",
                    details=(
                        "In den allermeisten Fällen fehlen hier schlicht die "
                        "Zählerwerte — dann trag sie nach, der Link führt direkt "
                        "in diesen Monat. Sind beide Werte bei dir tatsächlich 0 "
                        "— weil die Anlage keinen Netzanschluss hat (Inselbetrieb) "
                        "oder den ganzen Monat außer Betrieb war (Umzug, Defekt) —, "
                        "dann ist 0 richtig und es ist nichts zu tun: Der Hinweis "
                        "bleibt dann als Auskunft stehen und sagt, womit eedc für "
                        "diesen Monat rechnet."
                    ),
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
                # #362 kingcap1: Eine in Stufen ausgebaute Anlage erzeugt den
                # Sprung selbst — 2024 hingen mehr Module am Netz als 2023.
                # Für die Einspeisung setzt die Prüfung dann aus (Begründung
                # in `_erzeugung_ausgebaut`). Der Netzbezug hat sein eigenes
                # Gegenstück: er sinkt mit mehr PV — der Erzeuger-Zubau wäre
                # dort die falsche Erklärung —, aber er wächst mit neuen
                # Verbrauchern (WP, E-Auto, Wallbox). Jede Seite bekommt also
                # die Ausnahme, die zu ihrer Ursache gehört.
                ausgebaut = self._erzeugung_ausgebaut(anlage, vorjahr, md)
                verbraucher_zugebaut = self._verbrauch_ausgebaut(anlage, vorjahr, md)
                for feld, wert, vj_wert in [
                    ("Einspeisung", md.einspeisung_kwh, vorjahr.einspeisung_kwh),
                    ("Netzbezug", md.netzbezug_kwh, vorjahr.netzbezug_kwh),
                ]:
                    if feld == "Einspeisung" and ausgebaut:
                        continue
                    if feld == "Netzbezug" and verbraucher_zugebaut:
                        continue
                    if vj_wert and vj_wert > 50 and wert is not None and wert > 3 * vj_wert:
                        ergebnisse.append(CheckErgebnis(
                            kategorie=kat, schwere=CheckSeverity.WARNING,
                            meldung=f"{prefix}: {feld} > 3× Vorjahr ({wert:.0f} vs. {vj_wert:.0f} kWh)",
                            details="Deutliche Abweichung zum Vorjahresmonat",
                            link=md_link,
                        ))

            # 6. Energiebilanz: Hausverbrauch = PV - Einspeisung + Netzbezug ± Batterie
            # Nur prüfbar wenn alle Kernfelder vorhanden — die PV gehört dazu.
            # `pv_erzeugung or 0` stand hier bis 2026-07-29 und machte aus einer
            # unauflösbaren PV eine 0; bei erfasster Einspeisung ergab das einen
            # negativen Hausverbrauch und damit einen ERROR über eine Bilanz,
            # die schlicht nicht prüfbar ist.
            if (
                md.einspeisung_kwh is not None
                and md.netzbezug_kwh is not None
                and pv_erzeugung is not None
            ):
                pv = pv_erzeugung
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
        # Über den SoT-Helper statt als Literal: dieselbe Unterscheidung
        # entscheidet in `energieprofil.py` über die Zusatz-Zähler, und genau
        # dort hat sie bis 02.08. gefehlt.
        ist_klima = ist_luft_luft_waermepumpe(param)

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


# ─── Konzept-Wirtschaftlichkeit §8.1 — der Erfassungsort ────────────────────
#
# Das Modell rät nichts: die **Form** der Zahl sagt, ob sie wiederkehrt
# (Jahresbetrag an der Investition) oder einmal wirkt (Position im
# Monatsabschluss). Genau deshalb gibt es hier eine Fehleingabe-Möglichkeit,
# und genau deshalb ist sie erkennbar — **an der Wiederholung**, nicht an der
# Bedeutung eines Wortes.
#
# Schwellen: §8.1 nennt „≥ 3 Monate" für die Wiederholung. Für die
# Doppelerfassung nennt es keine — dort steht „gleichnamige Monatsposition",
# was ohne Schwelle jede einzelne Reparatur neben einer gepflegten
# Versicherung melden würde (P-6: ein Hinweis, der keinen Fehler beschreibt).
# Umgesetzt ist deshalb: **≥ 2** Monate, wenn der Jahresbetrag gepflegt ist
# (dort ist bereits die zweite Buchung ein Muster), **≥ 3** sonst. Beide Regeln
# schließen sich gegenseitig aus — ein Sachverhalt, eine Meldung.
WIEDERHOLUNG_AB_MONATEN = 3
DOPPELERFASSUNG_AB_MONATEN = 2


def _de_euro(betrag: float) -> str:
    """Betrag in deutscher Schreibweise — Meldungstexte sind Anzeige.

    ⚠ `check:de-de` liest nur `frontend/src` und kann eine Backend-Meldung
    nicht sehen (N-203). Hier steht die Regel deshalb im Code.
    """
    return f"{betrag:_.2f} €".replace(".", ",").replace("_", ".")


class ErfassungsortChecks:
    """§8.1 — welche Fehleingabe das Wirtschaftlichkeits-Modell erzeugen kann."""

    def _check_erfassungsort_positionen(self, anlage: Anlage) -> list[CheckErgebnis]:
        from backend.models.investition import ERTRAGSFELD_TYPEN
        from backend.utils.sonstige_positionen import get_sonstige_positionen

        # `.value` wie alle Nachbar-Checks: `CheckErgebnis.kategorie` ist als
        # `str` deklariert, und das Response-Modell gibt sie unverändert
        # weiter. Ein Enum-Objekt vergliche sich hier zwar noch richtig
        # (str-Enum), landete aber als `CheckKategorie.…` im Payload — und
        # der Client sucht seine Kategorie über den reinen Wert.
        kat = CheckKategorie.POSITION_WIEDERKEHREND.value
        kat_doppel = CheckKategorie.POSITION_DOPPELERFASSUNG.value
        ergebnisse: list[CheckErgebnis] = []

        for inv in anlage.investitionen or []:
            # (richtung, bezeichnung-normalisiert) → Menge der Monate
            monate_je_posten: dict[tuple[str, str], set[tuple[int, int]]] = {}
            anzeige_name: dict[tuple[str, str], str] = {}
            for imd in inv.monatsdaten or []:
                for p in get_sonstige_positionen(imd.verbrauch_daten):
                    if not isinstance(p, dict):
                        continue
                    bezeichnung = str(p.get("bezeichnung", "")).strip()
                    if not bezeichnung:
                        continue
                    richtung = "ertrag" if p.get("typ") == "ertrag" else "ausgabe"
                    schluessel = (richtung, bezeichnung.casefold())
                    monate_je_posten.setdefault(schluessel, set()).add((imd.jahr, imd.monat))
                    anzeige_name.setdefault(schluessel, bezeichnung)

            for schluessel, monate in sorted(monate_je_posten.items()):
                richtung = schluessel[0]
                bezeichnung = anzeige_name[schluessel]
                anzahl = len(monate)

                if richtung == "ertrag":
                    jahresbetrag = inv.einsparung_prognose_jahr
                    feld = "Ertrag/Jahr (€)"
                    # Bauschritt 9: für einen Erzeuger gibt es seit 2026-08-10
                    # den besseren Ort — „Einspeise-Erlös (€)" nimmt den echten
                    # Monatswert aus einem HA-Sensor, statt einen Jahresbetrag
                    # zu schätzen. Der Hinweis nennt deshalb DAS Feld, sonst
                    # schickt er genau den Fall aus §9 auf den zweitbesten Weg.
                    if (inv.parameter or {}).get("kategorie") == "erzeuger":
                        feld = "Einspeise-Erlös (€)"
                    # ⚠ Kein Hinweis ohne Ort: das Ertragsfeld gibt es nur bei
                    # Wallbox und Sonstiges (`ERTRAGSFELD_TYPEN`). Bei allen
                    # anderen Typen rechnet eedc die Jahres-Einsparung selbst —
                    # dort wäre „trag es an der Komponente ein" eine Anleitung
                    # zu einem Feld, das der Anwender nicht findet (P-6).
                    if inv.typ not in ERTRAGSFELD_TYPEN and not jahresbetrag:
                        continue
                else:
                    jahresbetrag = inv.betriebskosten_jahr
                    feld = "Betriebskosten/Jahr (€)"

                if jahresbetrag and anzahl >= DOPPELERFASSUNG_AB_MONATEN:
                    ergebnisse.append(CheckErgebnis(
                        kategorie=kat_doppel, schwere=CheckSeverity.INFO.value,
                        meldung=(
                            f"{inv.bezeichnung}: „{bezeichnung}“ steht in {anzahl} Monaten "
                            f"im Monatsabschluss, obwohl {feld} gepflegt ist"
                        ),
                        details=(
                            f"{feld} ist mit {_de_euro(jahresbetrag)} hinterlegt und wirkt "
                            f"jedes Jahr. "
                            f"Im Monatsabschluss gehört nur die Abweichung vom Plan — sonst "
                            f"zählt derselbe Betrag doppelt. Entweder den Jahresbetrag anpassen "
                            f"oder die Monatspositionen entfernen."
                        ),
                        link="/einstellungen/investitionen",
                        investition_id=inv.id,
                    ))
                elif not jahresbetrag and anzahl >= WIEDERHOLUNG_AB_MONATEN:
                    ergebnisse.append(CheckErgebnis(
                        kategorie=kat, schwere=CheckSeverity.INFO.value,
                        meldung=(
                            f"{inv.bezeichnung}: „{bezeichnung}“ steht in {anzahl} Monaten "
                            f"im Monatsabschluss — das sieht wiederkehrend aus"
                        ),
                        details=(
                            f"Ein Betrag, der jedes Jahr wiederkommt, gehört als {feld} an die "
                            f"Komponente. Dort wirkt er auch in der Prognose und in der "
                            f"Amortisation; im Monatsabschluss wirkt er nur in der Bilanz des "
                            f"Monats, in dem er steht. Einmaliges bleibt richtig, wo es ist."
                        ),
                        link="/einstellungen/investitionen",
                        investition_id=inv.id,
                    ))

        return ergebnisse
