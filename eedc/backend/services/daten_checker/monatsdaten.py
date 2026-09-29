"""
Daten-Checker — Monatsdaten-Vollständigkeit & -Plausibilität (`MonatsdatenChecks`).

Reiner Move aus dem früheren Modul `daten_checker.py` (Tier-4 Achse C).
"""

from dataclasses import dataclass
from datetime import date
from typing import Optional

from backend.core.berechnungen.anlagen_kwp import anlagen_kwp
from backend.core.berechnungen.waermepumpe_kennzahl import heizwaerme_kwh
from backend.core.berechnungen.spez_ertrag import PV_ERZEUGER_TYPEN
from backend.core.betriebsmodus import MODUS_STROM_FELD
from backend.core.field_definitions import (
    INVESTITION_FELDER,
    basis_feld_key,
    get_feld_bedarf,
    get_speicher_netzladung_kwh,
    get_wp_strom_kwh,
    get_wp_warmwasser_kwh,
    groesse_gibt_es_am_geraet,
    wp_strom_aufteilung,
)
from backend.core.berechnungen.erzeuger_traeger import erzeuger_traeger
from backend.core.investition_kennwerte import get_erzeuger_kwp
from backend.core.monats_luecken import ermittle_start_anker
from backend.models.anlage import Anlage
from backend.models.monatsdaten import Monatsdaten
from backend.models.investition import Investition
from backend.models.pvgis_prognose import PVGISPrognose
from backend.services.zaehlerstaende import ist_zaehler_investition
from backend.services.provenance import ABGELEITET_SUMME_ACHSEN

from .kategorien import (
    CheckErgebnis,
    CheckKategorie,
    CheckSeverity,
    LINK_DATENQUELLEN,
    LINK_MONATSDATEN,
    MonatsdatenAbdeckung,
    link_monat_erfassen,
    LINK_ENERGIEPROFIL,
)
from backend.core.zahlenformat import fmt_zahl


# Theoretisches PV-Maximum pro kWp und Monat (kWh) für Mitteleuropa
# Großzügig bemessen um False Positives zu vermeiden – obere Grenze
# für optimale Ausrichtung und überdurchschnittliche Einstrahlung
PV_MAX_KWH_PRO_KWP = {
    1: 55, 2: 75, 3: 110, 4: 140, 5: 170, 6: 180,
    7: 180, 8: 165, 9: 140, 10: 90, 11: 55, 12: 40,
}

#: WK-16d: Ab welchem Anteil der Menge stellt eedc die **Frage**, ob der
#: Gesamtzähler wirklich nur die Wärmepumpe misst?
#:
#: ⚠ **Großzügig, und das ist Absicht.** Der Rest *soll* es geben — Standby,
#: Steuerung und Umwälzpumpen laufen auf keiner der beiden Achsen; bei
#: dietmar1968 sind es 6,6 % im Jahr, im Sommer einzelner Monate deutlich mehr.
#: Ein Viertel trennt „das ist der Systemverbrauch" von „da hängt vermutlich
#: noch etwas anderes am Zähler", ohne einer normalen Anlage zwölfmal im Jahr
#: eine Frage zu stellen. Sie ist **kein Fehler** (INFO, Fragesatz): eedc weiß
#: nicht, was am Zähler hängt, und behauptet es nicht.
_REST_AUFFAELLIG_ANTEIL = 0.25


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
            f"summieren sich bereits auf {fmt_zahl(tages_pv, 0)} kWh PV, der gespeicherte "
            f"Monatswert steht aber bei {fmt_zahl(monats_pv, 0)} kWh. Die Tage wurden also "
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

        ⚠ **Ein Zählerstand ist die Ausnahme von „Löschen ist die Ausnahme"**
        (N-312). Der Satz „Nur wenn sie gar nicht mehr gebraucht werden,
        entferne sie" gilt für Mengen — für einen **Stand** sagt er das
        Gegenteil: gebraucht wird er nicht von diesem Monat, sondern vom
        **nächsten**. Die einzige Rechnung auf einem Zählerstand ist
        Ende − Anfang, und den Anfang holt ``zaehlerstaende.lade_zaehlerstaende``
        als letzten Stand **vor** dem Fenster. Fällt der Stand des Monats M weg,
        greift M+1 auf M−1 zurück und weist zwei Monate als einen aus — mit
        ``anfang_vollstaendig=True``, also ohne Hinweis. Deshalb nennt die
        Meldung die betroffenen Zähler beim Namen, statt allen Datenarten
        denselben Rat zu geben.

        ⛔ **Gesagt, nicht verboten.** Der Knopf bleibt, und er bleibt an
        derselben Stelle: eedc entscheidet nicht für den Anwender, wann ein
        Stand entbehrlich ist ([[feedback_eedc_ist_nicht_die_strom_polizei]]).
        """
        ergebnisse: list[CheckErgebnis] = []
        kat = CheckKategorie.GERAETEWERTE_OHNE_MONATSZEILE

        vorhandene = {(md.jahr, md.monat) for md in monatsdaten}

        # Je verwaistem Monat: wie viele Komponenten hängen daran?
        verwaist: dict[tuple[int, int], list[str]] = {}
        # ... und welche davon führen einen STAND statt einer Menge (N-312).
        verwaiste_zaehler: dict[tuple[int, int], list[str]] = {}
        for inv in anlage.investitionen:
            for imd in inv.monatsdaten:
                schluessel = (imd.jahr, imd.monat)
                if schluessel in vorhandene:
                    continue
                # Eine leere Zeile ist kein Fund — sie weist auch keinen
                # Import ab. Gemeldet wird nur, was wirklich einen Wert trägt.
                if not any(v is not None for v in (imd.verbrauch_daten or {}).values()):
                    continue
                name = inv.bezeichnung or f"#{inv.id}"
                verwaist.setdefault(schluessel, []).append(name)
                if ist_zaehler_investition(inv):
                    verwaiste_zaehler.setdefault(schluessel, []).append(name)

        for (jahr, monat), komponenten in sorted(verwaist.items()):
            namen = ", ".join(sorted(komponenten)[:4])
            if len(komponenten) > 4:
                namen += f" (+{len(komponenten) - 4} weitere)"
            details = (
                f"Für diesen Monat liegen Messwerte einzelner Geräte vor "
                f"({namen}), aber keine Zählerzeile mit Einspeisung und "
                "Netzbezug. Die Werte zählen in Cockpit und Auswertungen "
                "mit, der Monat erscheint aber in keiner Liste und weist "
                "einen erneuten Import ab. Trage den Monat nach — die "
                "Gerätewerte gehören dann wieder dazu. Nur wenn sie gar "
                "nicht mehr gebraucht werden, entferne sie."
            )
            zaehler = sorted(verwaiste_zaehler.get((jahr, monat), []))
            if zaehler:
                zaehler_namen = ", ".join(zaehler[:4])
                if len(zaehler) > 4:
                    zaehler_namen += f" (+{len(zaehler) - 4} weitere)"
                details += (
                    f" Achtung: Darunter sind Zählerstände ({zaehler_namen}). "
                    "Ein Zählerstand ist kein Monatswert, sondern der "
                    "Anfangsstand des Folgemonats — wird er entfernt, rechnet "
                    "der nächste Monat gegen den vorletzten Stand und weist "
                    "zwei Monate als einen aus, ohne dass es auffällt. Für "
                    "diese Geräte trage den Monat nach, statt zu entfernen."
                )
            ergebnisse.append(CheckErgebnis(
                kategorie=kat, schwere=CheckSeverity.WARNING,
                meldung=(
                    f"{monat:02d}/{jahr}: Messwerte von {len(komponenten)} "
                    "Komponente(n) ohne Monatszeile"
                ),
                details=details,
                # Deep-Link auf das Formular GENAU dieses Monats (Muster
                # `?erfassen=YYYY-MM`, wie die Status-Fusszeile). Der bisherige
                # Link zeigte auf die Liste — dort steht der Monat zwar als
                # offene Zeile, der Anwender musste ihn aber selbst suchen.
                link=f"/einstellungen/daten?erfassen={jahr}-{monat:02d}",
                action_kind="geraetewerte_loeschen",
                # `hat_zaehler` trägt die Datenart bis in die Rückfrage vor dem
                # Löschen (N-312). Der Deep-Link-Weg kennt keine
                # `Monatsdaten`-Zeile — genau die fehlt ja —, also gibt es für
                # diesen Monat auch kein `GET /{id}/geraetewerte`, aus dem der
                # Client die Auskunft holen könnte. Sie muss mitreisen.
                action_params={
                    "anlage_id": anlage.id,
                    "jahr": jahr,
                    "monat": monat,
                    "hat_zaehler": bool(zaehler),
                },
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
                link=LINK_MONATSDATEN,
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
                    # Sammelzeile über viele Monate — kein einzelner Monat, den
                    # ein `?erfassen=` sinnvoll aufschlagen könnte.
                    link=LINK_MONATSDATEN,
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
        # F-58: Obergrenze der Monatserzeugung gegen die Σ der Erzeuger, nicht
        # gegen den gepflegten Referenzwert. Ist der zu klein, meldet der
        # Checker eine „unplausible" Erzeugung, die schlicht der Anlage
        # entspricht. `mit_bkw=True`, weil `pv_erzeugung` unten die anlagenweite
        # Erzeugung ist.
        gesamt_kwp = anlagen_kwp(
            anlage.investitionen, date.today(),
            mit_bkw=True, referenzwert=anlage.leistung_kwp,
        )

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
        # (e') Ladung erfasst, Entladung fehlt — JE GERÄT, nicht aggregiert.
        #
        # ⭐ Die Warnung darunter („Batterie-Entladung nicht erfasst") gibt es
        # seit jeher, aber **nur auf dem Legacy-Pfad** (`md.batterie_*`, und
        # auch nur, solange für den Monat gar keine `InvestitionMonatsdaten`
        # vorliegen). Auf dem heutigen Erfassungsweg blieb ein Monat mit
        # `ladung_kwh > 0` und fehlender `entladung_kwh` **stumm** — derselbe
        # Fall, den der HA-Export seit A7 `keine-entladung` nennt.
        #
        # ⚠ Je Gerät, weil die Aggregation darunter (`speicher_imd_bat`) die
        # Lücke gerade verdeckt: zwei Speicher, einer davon vollständig, und
        # die Summe sieht heil aus. Der Anwender muss wissen, an welchem Gerät
        # das Feld fehlt — er füllt es dort.
        speicher_ohne_entladung: dict[tuple[int, int], list[tuple[str, float]]] = {}
        for inv in anlage.investitionen:
            if inv.typ == "speicher" and inv.aktiv:
                start = (inv.anschaffungsdatum.year, inv.anschaffungsdatum.month) if inv.anschaffungsdatum else None
                end = (inv.stilllegungsdatum.year, inv.stilllegungsdatum.month) if inv.stilllegungsdatum else None

                def _aktiv_im(key: tuple[int, int], _s=start, _e=end) -> bool:
                    """Zählt dieser Monat für DIESES Gerät? (Anschaffung/Stilllegung)"""
                    return not (
                        (_s is not None and key < _s) or (_e is not None and key > _e)
                    )

                for md in monatsdaten:
                    md_key = (md.jahr, md.monat)
                    if not _aktiv_im(md_key):
                        continue
                    speicher_aktiv_monate.add(md_key)
                for imd in inv.monatsdaten:
                    daten = imd.verbrauch_daten or {}
                    ladung = daten.get("ladung_kwh")
                    entladung = daten.get("entladung_kwh")
                    imd_key = (imd.jahr, imd.monat)
                    # `entladung == 0` ist ein WERT und kein Hinweis (ADR-002/P4):
                    # ein Speicher, der in einem Monat nichts abgegeben hat, ist
                    # erfasst. Nur `None` heißt „Feld leer".
                    if (
                        entladung is None
                        and ladung is not None
                        and float(ladung) > 0
                        and _aktiv_im(imd_key)
                    ):
                        speicher_ohne_entladung.setdefault(imd_key, []).append(
                            (inv.bezeichnung or f"#{inv.id}", float(ladung))
                        )
                    if ladung is not None or entladung is not None:
                        key = imd_key
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

            # (e') Derselbe Befund auf dem HEUTIGEN Erfassungsweg — je Gerät.
            #
            # ⛔ **Er steht bewusst AUSSERHALB des `not in speicher_imd_monate`-
            # Zweigs darüber.** Genau dieser Zweig ist der Grund, warum es den
            # Fall bisher nicht gab: sobald für den Monat irgendein
            # `InvestitionMonatsdaten`-Wert vorliegt, schweigt die
            # Legacy-Prüfung — und der neue Weg hatte gar keine. Ein Monat
            # bekommt deshalb entweder die Legacy-Warnung ODER diese hier, nie
            # beide: `speicher_ohne_entladung` ist nur befüllt, wo eine
            # IMD-Zeile mit Ladung existiert, und dann ist der Monat in
            # `speicher_imd_monate`.
            for geraet, ladung_kwh in speicher_ohne_entladung.get((md.jahr, md.monat), []):
                ergebnisse.append(CheckErgebnis(
                    kategorie=kat, schwere=CheckSeverity.WARNING,
                    meldung=(
                        f"{prefix}: {geraet}: Entladung nicht erfasst "
                        f"(Ladung {fmt_zahl(ladung_kwh, 1)} kWh vorhanden)"
                    ),
                    details=(
                        "Ohne Entladung gibt es keinen gemessenen Wirkungsgrad "
                        "und keine Speicher-Ersparnis"
                    ),
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
                        meldung=f"{prefix}: {feld} ist negativ ({fmt_zahl(wert, 1)} kWh)",
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
                            f"PVGIS-Prognose: {fmt_zahl(pvgis_soll, 0)} kWh, "
                            f"Obergrenze (×{fmt_zahl(max_kwh / pvgis_soll, 1)}): {fmt_zahl(max_kwh, 0)} kWh"
                        )
                    else:
                        details = (
                            f"Statisches Maximum für {fmt_zahl(gesamt_kwp, 1)} kWp "
                            f"im Monat {md.monat}: ca. {fmt_zahl(max_kwh, 0)} kWh"
                        )
                    ergebnisse.append(CheckErgebnis(
                        kategorie=kat, schwere=CheckSeverity.WARNING,
                        meldung=f"{prefix}: PV-Erzeugung ungewöhnlich hoch ({fmt_zahl(pv_erzeugung, 0)} kWh)",
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
                    meldung=f"{prefix}: Einspeisung ({fmt_zahl(md.einspeisung_kwh, 0)} kWh) > PV-Erzeugung ({fmt_zahl(pv_erzeugung, 0)} kWh)",
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
                            f"Einspeisung ({fmt_zahl(md.einspeisung_kwh, 0)}) + Speicherladung aus PV "
                            f"({fmt_zahl(pv_ladung_speicher, 0)}) = {fmt_zahl(stapel, 0)} kWh, "
                            f"erzeugt wurden {fmt_zahl(pv_erzeugung, 0)} kWh"
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
                            meldung=f"{prefix}: {feld} > 3× Vorjahr ({fmt_zahl(wert, 0)} vs. {fmt_zahl(vj_wert, 0)} kWh)",
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
                        meldung=f"{prefix}: Energiebilanz ergibt negativen Hausverbrauch ({fmt_zahl(hausverbrauch, 1)} kWh)",
                        details=(
                            f"PV {fmt_zahl(pv, 0)} – Einspeisung {fmt_zahl(md.einspeisung_kwh, 0)} "
                            f"+ Netzbezug {fmt_zahl(md.netzbezug_kwh, 0)} "
                            f"+ Bat.Entladung {fmt_zahl(bat_entladung, 0)} "
                            f"– Bat.Ladung {fmt_zahl(bat_ladung, 0)} = {fmt_zahl(hausverbrauch, 1)} kWh. "
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
                link=link_monat_erfassen(fehlend[0]),
            ))
        else:
            ergebnisse.append(CheckErgebnis(
                kategorie=kat, schwere=CheckSeverity.OK,
                meldung=f"{name}: Monatsdaten vollständig ({len(erwartete)} Monate)",
            ))

        return ergebnisse

    def _check_werte_in_nicht_gefuehrten_feldern(
        self, inv: Investition, name: str, param: dict
    ) -> list[CheckErgebnis]:
        """Ein gespeicherter Wert in einem Feld, das dieses Gerät nicht führt (N-393).

        **Die Klasse.** Jedes Feld mit einer harten `bedingung` (Registry
        `INVESTITION_FELDER`) verschwindet aus dem Monatsabschluss, sobald die
        Bedingung am Gerät nicht mehr erfüllt ist — Warmwasser an einer
        Split-Klimaanlage (N-304), Netzladung an einem Speicher ohne
        `laedt_aus_netz`, V2H-Entladung ohne `v2h_faehig`, getrennte Ströme nach
        Abschalten der getrennten Messung. Ein **vorher** gespeicherter Wert
        bleibt in der Zeile: der Client filtert ohne Rücksicht auf Werte, der
        Schreibpfad merged je Sub-Key. **Der Anwender kommt an ihn nicht mehr
        heran** — dietmar1968 (T89667 #295/#300) konnte 889 kWh „Warmwasser" an
        seiner Klimaanlage weder sehen noch entfernen; die bis dahin hier stehende
        N-379-INFO nannte ihm einen Weg („bis du ihn selbst umträgst"), den es
        nicht gab.

        **Deshalb eine Meldung MIT Handgriff**, in der Bauform von #349
        (`geraetewerte_loeschen`): die INFO trägt die Inline-Aktion
        `feldwert_entfernen`, der Endpunkt `DELETE /monatsdaten/investition/
        {id}/feld/{feld}` entfernt den Wert **nur** in Monaten, in denen das
        Gerät die Größe nicht führt — ein erreichbares Feld wird dort abgewiesen
        (409), es hat seinen Weg im Formular.

        ⛔ **eedc löscht und verschiebt nichts von allein** (N-379-Entscheid). Es
        weiß nicht, was der Wert ist — nur, dass er hier keine Größe dieses
        Geräts sein kann. Die wahrscheinlichste Herkunft steht als Angebot
        daneben (Klima: Kühlbetrieb), nie als Urteil.

        ⚠ **Genau EINE Meldung je Feld, nicht je Monat** — die Aktion nimmt alle
        betroffenen Monate mit und nennt sie; zwölf Meldungen für einen
        umgestellten Schalter wären Lärm, nicht Auskunft
        (`test_b5_strom_warmwasser_luft_luft.py` hält das seit N-379 fest).

        ⚠ **Nur die harte Sorte.** `groesse_gibt_es_am_geraet` fragt
        `URTEIL_NEIN`; ein *erweitertes* Feld (weiche Bedingung, R1) gilt als
        vorhanden — es ist untypisch, nicht unmöglich, und wer es gepflegt hat,
        meint es so. Ebenfalls **nicht** hier: `bedingung_anlage` (Verdrängung
        durch ein anderes Gerät, z. B. Heimladung bei vorhandener Wallbox) —
        dort gewinnt ein anderer Weg, die Größe existiert weiter.

        Eine ``0`` löst nichts aus: sie ist keine Aussage über das Gerät und
        rechnet nirgends mit.
        """
        felder = INVESTITION_FELDER.get(inv.typ)
        if not isinstance(felder, list):
            return []
        # Nur Felder mit harter Bedingung können am Gerät fehlen — alle anderen
        # spart die Lesetür unten ohnehin aus, die Vorprüfung hält den Lauf kurz.
        label_je_feld = {
            f["feld"]: f.get("label", f["feld"])
            for f in felder
            if isinstance(f, dict) and f.get("bedingung")
        }
        if not label_je_feld:
            return []

        monate_je_feld: dict[str, list[tuple[int, int]]] = {}
        for imd in sorted(inv.monatsdaten or [], key=lambda x: (x.jahr, x.monat)):
            daten = imd.verbrauch_daten or {}
            for key, wert in daten.items():
                basis = basis_feld_key(key)
                if basis not in label_je_feld:
                    continue
                if not isinstance(wert, (int, float)) or isinstance(wert, bool) or wert == 0:
                    continue
                if groesse_gibt_es_am_geraet(inv.typ, basis, param):
                    continue
                monate_je_feld.setdefault(key, []).append((imd.jahr, imd.monat))

        ergebnisse: list[CheckErgebnis] = []
        kat = CheckKategorie.INVESTITIONEN
        for key, monate in sorted(monate_je_feld.items()):
            label = label_je_feld[basis_feld_key(key)]
            labels = [f"{m:02d}/{j}" for (j, m) in monate]
            monate_str = ", ".join(labels[:6])
            if len(labels) > 6:
                monate_str += f" (+{len(labels) - 6} weitere)"

            if inv.typ == "waermepumpe" and basis_feld_key(key) == "warmwasser_kwh":
                # Der Ursprungsfall (N-379): die Klimaanlage. Der Kühlbetrieb ist
                # das wahrscheinlichste Ziel des Werts — als Angebot, nicht als Urteil.
                meldung = (
                    f"{name}: Warmwasser-Wärme in {len(labels)} Monat(en) "
                    f"gespeichert — eine Split-Klimaanlage hat keinen Warmwasserkreis"
                )
                details = (
                    f"{monate_str}. Der Wert zählt nicht als Wärme dieses Geräts: er "
                    "würde sonst eine Ersparnis gegenüber der Heizung ausweisen, die "
                    "das Gerät nie erzeugt hat. Stammt er aus dem Kühlbetrieb, gehört "
                    "er in „Nutzenergie Kuehlbetrieb“ — dann rechnet eedc daraus die "
                    "Arbeitszahl Kühlen. Im Monatsabschluss ist das Feld an einer "
                    "Klimaanlage nicht mehr erreichbar; der gespeicherte Wert bleibt "
                    "unverändert stehen, bis du ihn mit „Wert entfernen“ löschst. "
                    "eedc löscht und verschiebt nichts von allein."
                )
            else:
                meldung = (
                    f"{name}: {label} in {len(labels)} Monat(en) gespeichert — "
                    f"dieses Gerät führt das Feld nicht mehr"
                )
                details = (
                    f"{monate_str}. Das Feld ist nach den Einstellungen des Geräts "
                    "nicht mehr vorgesehen und im Monatsabschluss deshalb nicht mehr "
                    "erreichbar; der gespeicherte Wert bleibt unverändert stehen. "
                    "Stimmt die Einstellung, entferne den Wert mit „Wert entfernen“. "
                    "Soll der Wert weiter zählen, stelle die Einstellung am Gerät "
                    "zurück — dann erscheint das Feld wieder im Monatsabschluss. "
                    "eedc löscht und verschiebt nichts von allein."
                )

            ergebnisse.append(CheckErgebnis(
                kategorie=kat, schwere=CheckSeverity.INFO,
                meldung=meldung,
                details=details,
                investition_id=inv.id,
                link=link_monat_erfassen(labels[0]),
                action_kind="feldwert_entfernen",
                action_label="Wert entfernen",
                action_params={
                    "investition_id": inv.id,
                    "feld": key,
                    "label": label,
                    "monate": labels,
                },
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
        # B2 (05.09.2026, R1): Ob eedc an diesem Gerät Heizwärme ERWARTET und
        # ob es eine Warmwasser-Strom-Seite GIBT, sagt die Registry — nicht die
        # Bauart. Heizwärme ist an einer Split-Klimaanlage optional
        # (`KLIMA_OHNE_WAERMEMENGE`: kein Wärmemengenzähler möglich, die
        # Warnung wäre ein Dauer-Falschpositiv) und an einer Brauchwasser-WP
        # erweitert (A6); `strom_warmwasser_kwh` existiert an einer
        # Klimaanlage nicht (B5/N-304). ⛔ Bis B2 stand hier eine Bauart-Frage
        # (`ist_luft_luft_waermepumpe`), an drei Stellen dieser Funktion benutzt.
        heiz_erwartet = get_feld_bedarf("waermepumpe", "heizenergie_kwh", param)[0] == "pflicht"
        ww_strom_gibt_es = groesse_gibt_es_am_geraet("waermepumpe", "strom_warmwasser_kwh", param)

        # ⛔ **Hier stand bis zum 14.09.2026 eine INFO „Alter
        # Gesamt-Stromverbrauch-Sensor … ist bei aktivierter getrennter
        # Strommessung obsolet" (#183).** Sie ist mit WK-16d **ersatzlos
        # entfallen, weil der Zustand, den sie meldete, nicht mehr eintritt:**
        # Ein zugeordneter Gesamtzähler ist seither die Menge (K1) und wird
        # gelesen, auch neben einer vollständigen Achse — er ist nicht obsolet,
        # sondern die Quelle des „nicht aufgeteilt"-Rests. Eine Empfehlung, ihn
        # zu entfernen, hätte ab jetzt Standby, Steuerung und Umwälzpumpen aus
        # der Bilanz geworfen. *Dieselbe Bauform wie die F-7-Stufe-1-Warnung,
        # die mit #406 entfiel: eine Meldung ohne Defekt ist eine Falschmeldung.*
        # An ihre Stelle treten die zwei Prüfungen unter der Monats-Karte: der
        # **Widerspruch** (Gesamt < Σ Achsen) und die **Plausibilitätsfrage**
        # (Rest > 25 %).

        imd_map = {
            (imd.jahr, imd.monat): (imd.verbrauch_daten or {})
            for imd in inv.monatsdaten
        }

        # #263 K-2 (S3, Entscheid E-H): Die Aufteilung nach Betriebsmodus ist
        # eine **Teilmenge** des Gesamtstroms. Beim Schreiben wird das geprüft —
        # aber der Gesamtwert kann danach von Hand kleiner gepflegt werden, und
        # dann steht ein Widerspruch in der Zeile.
        #
        # Auflösbar, und der Weg steht dabei (P-6): entweder der Monatswert ist
        # zu klein, oder ein erneuter Monatsabschluss rechnet die Aufteilung neu.
        # Der Checker kappt nichts — eine stille Kappung machte aus einem
        # Widerspruch eine plausibel aussehende Zahl.
        #
        # Stand bis 22.08. in `_check_investition_monatsdaten`, wo nie eine
        # Wärmepumpe ankommt (nur BKW/Speicher/E-Auto/Wallbox) — und wo `param`
        # nicht existiert: der Befund konnte nie erscheinen, ein Modus-Wert
        # hätte die ganze Checker-Antwort in einen NameError laufen lassen.
        widerspruch_monate: list[str] = []
        for (jahr, monat), daten in sorted(imd_map.items()):
            teilmengen = sum(
                daten.get(feld, 0) or 0 for feld in MODUS_STROM_FELD.values()
            )
            if teilmengen <= 0:
                continue
            gesamt = get_wp_strom_kwh(daten, param)
            if teilmengen > gesamt + 0.5:
                widerspruch_monate.append(f"{monat:02d}/{jahr}")
        if widerspruch_monate:
            monate_str = ", ".join(widerspruch_monate[:6])
            if len(widerspruch_monate) > 6:
                monate_str += f" … (+{len(widerspruch_monate) - 6})"
            ergebnisse.append(CheckErgebnis(
                kategorie=kat, schwere=CheckSeverity.WARNING,
                meldung=(
                    f"{name}: Heiz- und Kühlstrom zusammen größer als der "
                    f"Gesamtverbrauch ({monate_str})"
                ),
                details=(
                    "Die Aufteilung nach Heizen und Kühlen ist ein Teil des "
                    "Gesamtverbrauchs — zusammen können beide ihn nicht "
                    "übersteigen. Das passiert, wenn der Gesamtwert nachträglich "
                    "kleiner eingetragen wurde als die bereits erfasste "
                    "Aufteilung. Zwei Wege: Prüfe den Stromverbrauch dieser "
                    "Monate im Monatsabschluss — oder schließe den Monat erneut "
                    "ab, dann rechnet eedc die Aufteilung neu und verwirft sie, "
                    "falls sie nicht passt. Die Energiebilanz ist nicht "
                    "betroffen: dort zählt immer der Gesamtwert."
                ),
                link="/monatsabschluss",
                investition_id=inv.id,
            ))

        # N-391: **dieselbe Frage auf der Wärmeseite** — eine Aufteilung kann
        # ihre Gesamtmenge nicht übersteigen. Sie steht bewusst hier, direkt
        # neben ihrem Strom-Zwilling: gleiche Zeile, gleiche Kategorie, gleicher
        # Weg, gleiche Monatsliste. Ein eigener Prüfer in
        # `daten_checker/waermepumpe.py` wäre ein zweiter Turm — dort geht es um
        # die **Kennzahl** (Arbeitszahl über 7), hier um einen **Widerspruch in
        # den Mengen** derselben Monatszeile.
        #
        # ⚠ **Nur diese eine Richtung**: `waerme_kwh` KLEINER als die Summe der
        # beiden Achsen. eedc rechnet nach D1 mit der Gesamtmenge — steht sie zu
        # niedrig, verschwindet der Unterschied lautlos aus Wärme, Arbeitszahl,
        # Ersparnis und CO₂. Der umgekehrte Fall (Gesamt größer als die Summe)
        # ist **kein** Fehler: Er ist die normale Lage, wenn nur EINE Achse
        # eigens gemessen wird und der Rest im Gesamtzähler steckt.
        #
        # ⚠ Toleranz 0,5 kWh wie beim Strom-Zwilling — Zählerstände runden.
        waerme_widerspruch: list[str] = []
        for (jahr, monat), daten in sorted(imd_map.items()):
            _gesamt_waerme = daten.get("waerme_kwh")
            if not _gesamt_waerme:
                continue
            # R-3/N-488: dieselbe Weiche wie die Anzeige (D1-Stufe 3) — sonst
            # sähe der Widerspruchs-Prüfer an einem Gerät mit Betriebsart-Wärme
            # eine kleinere Summe als der Block daneben und schwiege zu Unrecht.
            _teile = ((heizwaerme_kwh(daten) or 0.0)
                      + get_wp_warmwasser_kwh(daten, param))
            if _teile > float(_gesamt_waerme) + 0.5:
                waerme_widerspruch.append(f"{monat:02d}/{jahr}")
        if waerme_widerspruch:
            _w_monate = ", ".join(waerme_widerspruch[:6])
            if len(waerme_widerspruch) > 6:
                _w_monate += f" … (+{len(waerme_widerspruch) - 6})"
            ergebnisse.append(CheckErgebnis(
                kategorie=kat, schwere=CheckSeverity.WARNING,
                meldung=(
                    f"{name}: Gesamtwärme kleiner als Heizwärme + "
                    f"Warmwasser-Wärme ({_w_monate})"
                ),
                details=(
                    "„Wärme gesamt“ ist die Wärme des ganzen Geräts — Heizung "
                    "und Warmwasser zusammen. Steht dort weniger als in den "
                    "beiden Einzelwerten, meint einer der Werte etwas anderes "
                    "als gedacht: Häufig ist unter „Wärme gesamt“ die Heizwärme "
                    "gelandet. eedc rechnet mit der Gesamtwärme — Wärmemenge, "
                    "Arbeitszahl, Ersparnis und CO₂ dieser Monate fallen "
                    "deshalb zu niedrig aus. Prüf bitte im Monatsabschluss, "
                    "welcher Zähler welchen Wert liefert: Mit EINEM gemeinsamen "
                    "Wärmemengenzähler gehört sein Wert unter „Wärme gesamt“ "
                    "und die beiden Einzelfelder bleiben leer; mit getrennten "
                    "Zählern ist es umgekehrt."
                ),
                link=link_monat_erfassen(waerme_widerspruch[0]),
                investition_id=inv.id,
            ))

        # ── WK-16d: der Gesamt-Stromzähler und seine Achsen ──────────────────
        #
        # **Zwei Meldungen, zwei verschiedene Aussagen** — sie stehen hier, weil
        # sie dieselbe Zeile lesen wie die zwei Prüfungen darüber und dieselbe
        # Monatsliste bauen. Beide Zahlen kommen aus **einer** Auflösung
        # ({@link backend.core.field_definitions.wp_strom_aufteilung}); die
        # Toleranz und die Stufenregel liegen dort, nicht hier — ein zweiter
        # Schwellenwert wäre die F-56-Klasse (die Fläche bemängelte eine Lage,
        # die die Rechnung daneben durchgehen lässt).
        strom_widerspruch: list[str] = []
        rest_auffaellig: list[tuple[str, float, float]] = []
        # N-578 (H3, Master-Entscheid): **keine neue Meldung, eine zweite Deutung
        # an den zwei bestehenden.** Ein Gesamtwert, den das Monatsformular
        # geschrieben hat und der NICHT seine eigene Auto-Summe ist
        # (`manual:form` ohne `summe_achsen`), kann ein stehen gebliebener
        # früherer Stand sein: bis N-578 fror die Auto-Summe beim ersten
        # Speichern eines Monats ein (#416, Rainer). Genau dann nennen die
        # Meldungen den Handgriff „Feld leeren". Ein Sensor-/Import-Wert
        # (`external:*`, CSV) bekommt den Satz nicht — er ist gemessen, und die
        # 25-%-Regel darunter (WK-16d D2) bleibt, wie sie ist.
        _formular_monate: set[tuple[int, int]] = set()
        for _imd in inv.monatsdaten:
            _e = (_imd.source_provenance or {}).get("verbrauch_daten.stromverbrauch_kwh")
            if (isinstance(_e, dict) and _e.get("source") == "manual:form"
                    and _e.get("abgeleitet") != ABGELEITET_SUMME_ACHSEN):
                _formular_monate.add((_imd.jahr, _imd.monat))

        def _handgriff(monate: list[str]) -> str:
            _vielleicht = [m for m in monate
                           if (int(m[3:]), int(m[:2])) in _formular_monate]
            if not _vielleicht:
                return ""
            return (
                " Der Gesamtwert in "
                + ", ".join(_vielleicht[:6])
                + (" …" if len(_vielleicht) > 6 else "")
                + " stammt aus dem Monatsformular. Hast du den Monat früher "
                "schon einmal gespeichert, als Strom Heizen oder Strom "
                "Warmwasser noch andere Werte hatten, kann er ein stehen "
                "gebliebener alter Stand sein: Leere dann im Monatsformular das "
                "Feld „Stromverbrauch“ und speichere — eedc rechnet ihn danach "
                "selbst aus Heizen + Warmwasser. Ist er der Wert eines eigenen "
                "Gesamtzählers, lass ihn stehen."
            )

        for (jahr, monat), daten in sorted(imd_map.items()):
            _auf = wp_strom_aufteilung(daten, param)
            if _auf.gesamtzaehler_zu_klein:
                strom_widerspruch.append(f"{monat:02d}/{jahr}")
                continue
            # ⚠ **Die Frage setzt eine Aufteilung voraus, die auch etwas
            # aufteilt.** Wer nur den Gesamtzähler pflegt, hat keinen Rest,
            # sondern nur eine Menge — dass die Achsen fehlen, sagt die Meldung
            # „Strom Heizen/Warmwasser fehlt" weiter unten, und zwei Hinweise
            # auf denselben Sachverhalt wären Lärm.
            #
            # ⛔ **Und die Bedingung ist NICHT dieselbe wie die des Rests.**
            # ``wp_strom_aufteilung`` fragt *steht eine Achse in der Zeile?*
            # (``is not None`` — eine gemessene 0 ist eine Messung); hier wird
            # gefragt, ob sie auch **etwas trägt**. Eine Zeile mit nur
            # ``strom_warmwasser_kwh: 0.0`` hat einen Rest in voller Höhe der
            # Menge, aber keine Aufteilung, über die sich eine Frage lohnte.
            if _auf.feine_summe_kwh <= 0:
                continue
            if _auf.nicht_aufgeteilt_kwh > _REST_AUFFAELLIG_ANTEIL * _auf.menge_kwh:
                rest_auffaellig.append(
                    (f"{monat:02d}/{jahr}", _auf.nicht_aufgeteilt_kwh, _auf.menge_kwh)
                )
        if strom_widerspruch:
            _s_monate = ", ".join(strom_widerspruch[:6])
            if len(strom_widerspruch) > 6:
                _s_monate += f" … (+{len(strom_widerspruch) - 6})"
            ergebnisse.append(CheckErgebnis(
                kategorie=kat, schwere=CheckSeverity.WARNING,
                meldung=(
                    f"{name}: Gesamtzähler kleiner als die Summe der Achsen "
                    f"({_s_monate})"
                ),
                details=(
                    "Der Gesamt-Stromverbrauch ist der Verbrauch des ganzen "
                    "Geräts — Strom Heizen und Strom Warmwasser sind Teile "
                    "davon und können zusammen nicht mehr sein. Steht dort "
                    "weniger, meint einer der Werte etwas anderes als gedacht: "
                    "Häufig misst der Gesamtzähler nur einen Teil des Geräts "
                    "(nur das Außengerät, nur einen Stromkreis) oder eine der "
                    "beiden Achsen zählt einen fremden Verbrauch mit. eedc "
                    "rechnet in diesen Monaten mit der Summe der Achsen, damit "
                    "nichts verloren geht — prüf bitte im Monatsabschluss, "
                    "welcher Zähler welchen Wert liefert."
                    + _handgriff(strom_widerspruch)
                ),
                link=link_monat_erfassen(strom_widerspruch[0]),
                investition_id=inv.id,
            ))
        if rest_auffaellig:
            _r_monate = ", ".join(m for m, _, _ in rest_auffaellig[:6])
            if len(rest_auffaellig) > 6:
                _r_monate += f" … (+{len(rest_auffaellig) - 6})"
            _beispiel = max(rest_auffaellig, key=lambda e: e[1] / e[2])
            ergebnisse.append(CheckErgebnis(
                kategorie=kat, schwere=CheckSeverity.INFO,
                meldung=(
                    f"{name}: Der Gesamtzähler misst deutlich mehr als die "
                    f"Achsen — misst er nur die Wärmepumpe? ({_r_monate})"
                ),
                details=(
                    # P-6: der Weg steht dabei. Und **kein Fehler, eine Frage** —
                    # der Unterschied kann vollkommen richtig sein (Standby,
                    # Steuerung, Umwälzpumpen; bei einem Melder 6,6 % im Jahr).
                    # Deshalb INFO und deshalb ein Fragesatz: eedc weiß nicht,
                    # was am Zähler hängt, und behauptet es auch nicht.
                    f"In {_beispiel[0]} liegen "
                    f"{fmt_zahl(_beispiel[1], 0)} von {fmt_zahl(_beispiel[2], 0)} kWh weder auf "
                    "Strom Heizen noch auf Strom Warmwasser; eedc führt sie als "
                    "„nicht aufgeteilt“. Das ist oft richtig — Standby, "
                    "Steuerung und Umwälzpumpen laufen auf keiner der beiden "
                    "Achsen. Es kann aber auch heißen, dass am Gesamtzähler "
                    "noch etwas anderes hängt als die Wärmepumpe. Prüf das "
                    "unter Einstellungen → Datenquellen; ändern musst du "
                    "nichts, wenn der Zähler stimmt."
                    + _handgriff([m for m, _, _ in rest_auffaellig])
                ),
                link=LINK_DATENQUELLEN,
                investition_id=inv.id,
            ))

        fehlend_strom: list[str] = []
        fehlend_strom_heizen: list[str] = []
        fehlend_strom_ww: list[str] = []
        fehlend_heiz: list[str] = []

        for (jahr, monat) in erwartete:
            daten = imd_map.get((jahr, monat), {})
            label = f"{monat:02d}/{jahr}"

            if getrennte_strommessung:
                # B5 — an einer Split-Klimaanlage gibt es die Warmwasser-Seite
                # der Achse nicht (`strom_warmwasser_kwh` trägt seit dem
                # N-304-Nachzug `!luft_luft`). Sie hier weiter abzufragen hieße,
                # ein Feld zu erwarten, das der Monatsabschluss gar nicht mehr
                # anbietet — die Klasse, an der N-86 schon einmal hing:
                # dieselbe Anlage, zwei Flächen, gegenteilige Aussage.
                heizen_fehlt = daten.get("strom_heizen_kwh") is None
                ww_fehlt = (
                    ww_strom_gibt_es and daten.get("strom_warmwasser_kwh") is None
                )
                if heizen_fehlt and (ww_fehlt or not ww_strom_gibt_es):
                    # Die ganze Stromachse ist leer (an einer Klimaanlage: ihre
                    # einzige Seite) — EINE Meldung, unverändert seit je. Für
                    # den Anwender ist das EIN Sachverhalt; ihn in zwei Zeilen
                    # zu zerlegen wäre kein schärferer Hinweis, sondern Lärm.
                    fehlend_strom.append(label)
                else:
                    # ⭐ Fehlt nur EINE Seite, während die zugehörige Wärme
                    # gemessen ist, war hier bis zum 13.09.2026 **nichts** — die
                    # `and`-Verknüpfung darüber verlangte beide Leerstellen. Der
                    # Monat bekam statt dessen die OK-Zeile „Monatsdaten
                    # vollständig", und die Gesamt-Arbeitszahl rechnete die Wärme
                    # BEIDER Seiten über den Strom EINER (gemessen: Heizwärme
                    # 1800 + Heizstrom 600 + Warmwasser-Wärme 600 ohne
                    # Warmwasser-Strom ⇒ 4,0 — plausibel genug, dass auch der
                    # Plausibilitäts-Prüfer schweigt, dessen Schwelle bei 7,0
                    # liegt).
                    #
                    # ⛔ Die Bedingung hängt an der **Wärme**, nicht an der
                    # bloßen Anwesenheit des Felds: ein Monat ohne Warmwasser-
                    # Abgabe braucht keinen Warmwasser-Strom. Sonst meldete eedc
                    # jeder reinen Heiz-Anlage zwölf Lücken im Jahr — ein
                    # Hinweis, der keinen Fehler beschreibt.
                    #
                    # ⚠ Beide Lesetüren mit dem, was sie brauchen (N-450):
                    # `get_wp_warmwasser_kwh` filtert mit `param` den Wert weg,
                    # den eine Klimaanlage gar nicht abgeben kann.
                    # R-3/N-488: auch hier die Weiche — wer seine Heizwärme je
                    # Betriebsart misst, hat sehr wohl geheizt, und der fehlende
                    # Heizstrom gehört genannt.
                    if heizen_fehlt and (heizwaerme_kwh(daten) or 0.0) > 0:
                        fehlend_strom_heizen.append(label)
                    if ww_fehlt and get_wp_warmwasser_kwh(daten, param) > 0:
                        fehlend_strom_ww.append(label)
            else:
                if daten.get("stromverbrauch_kwh") is None:
                    fehlend_strom.append(label)

            # N-391: **die Gruppe zählt, nicht das eine Feld.** *Heizwärme* und
            # *Wärme gesamt* sind Alternativen derselben Größe
            # (`BEDARF_GRUPPEN_ALTERNATIV`, Gruppe `wp_waerme`) — wer seinen
            # gemeinsamen Wärmemengenzähler pflegt, hat nichts nachzutragen.
            # Ihn trotzdem anzumahnen wäre die N-86-Klasse: dieselbe Anlage,
            # zwei Flächen, gegenteilige Aussage (die Zuordnungs-Fläche sagt für
            # dieses Feld bereits „bereits zugeordnet").
            if (heiz_erwartet and daten.get("heizenergie_kwh") is None
                    and daten.get("waerme_kwh") is None):
                fehlend_heiz.append(label)

        def _monate(labels: list[str]) -> str:
            text = ", ".join(labels[:6])
            if len(labels) > 6:
                text += f" (+{len(labels) - 6} weitere)"
            return text

        if fehlend_strom:
            if not getrennte_strommessung:
                strom_label = "Stromverbrauch"
            elif not ww_strom_gibt_es:
                strom_label = "Strom Heizen"   # B5: keine Warmwasser-Seite
            else:
                strom_label = "Strom Heizen/Warmwasser"
            ergebnisse.append(CheckErgebnis(
                kategorie=kat, schwere=CheckSeverity.WARNING,
                meldung=f"{name}: {strom_label} fehlt in {len(fehlend_strom)} Monat(en)",
                details=_monate(fehlend_strom),
                link=link_monat_erfassen(fehlend_strom[0]),
            ))

        # Je Seite eine Meldung — sie können nebeneinander stehen, ohne dasselbe
        # zu sagen: die eine nennt die Heiz-, die andere die Warmwasser-Achse,
        # und ein Monat steht nie in beiden (fehlen beide, greift der Block
        # darüber). Schwere, Kategorie und Weg sind dieselben wie dort — kein
        # zweiter Turm, derselbe Melder, geschärft.
        #
        # ⭐ **Der Verweis auf die Zuordnungs-Fläche ist seit N-456 (13.09.2026)
        # dabei, und vorher wäre er falsch gewesen.** Bis dahin erklärte
        # Einstellungen → Datenquellen genau dieses Feld für „bereits zugeordnet
        # — hier ist nichts einzutragen", sobald die andere Stromseite belegt
        # war: Wer dem Hinweis folgte, landete auf einer Fläche, die ihm sagte,
        # es sei nichts zu tun (N-86-Klasse, deshalb nannte der Text zunächst
        # bewusst nur den Monatsabschluss). Seit die Belegung je Gerät und nach
        # den Registry-Bedingungen eingestuft wird, steht das Feld dort als
        # Pflicht — beide Wege sagen jetzt dasselbe.
        #
        # ⚠ **Die Reihenfolge trägt die Aussage:** Der Monatsabschluss steht
        # zuerst, weil nur er die **vergangenen** Monate füllt; eine Zuordnung
        # wirkt nach vorn. Wer beides braucht, braucht beides.
        for labels, seite, waerme_satz in (
            (fehlend_strom_heizen, "Strom Heizen",
             "Die Heizwärme dieser Monate ist erfasst, der Strom dafür nicht."),
            (fehlend_strom_ww, "Strom Warmwasser",
             "Die Warmwasser-Wärme dieser Monate ist erfasst, der Strom dafür "
             "nicht."),
        ):
            if not labels:
                continue
            ergebnisse.append(CheckErgebnis(
                kategorie=kat, schwere=CheckSeverity.WARNING,
                meldung=f"{name}: {seite} fehlt in {len(labels)} Monat(en)",
                details=(
                    f"{_monate(labels)}. {waerme_satz} eedc bildet jede "
                    "Arbeitszahl aus abgegebener Wärme ÷ eingesetztem Strom und "
                    "setzt dafür beide Seiten der getrennten Messung voraus. Die "
                    "Zeile dieser Funktion sagt es bereits („kein Stromverbrauch "
                    "erfasst“); die Gesamt-Arbeitszahl kann es nicht sagen — sie "
                    "rechnet dann mit einem unvollständigen Nenner, also die "
                    "Wärme beider Seiten über dem Strom einer, und fällt zu hoch "
                    f"aus. Trage „{seite}“ für diese Monate im Monatsabschluss "
                    "nach — die Arbeitszahlen stehen danach mit vollständigem "
                    "Nenner da, ohne dass du sonst etwas tun musst. Soll dieser "
                    "Zähler künftig von allein mitlaufen, ordne ihn zusätzlich "
                    "unter Einstellungen → Datenquellen zu."
                ),
                investition_id=inv.id,
                link=link_monat_erfassen(labels[0]),
            ))

        if fehlend_heiz:
            monate_str = _monate(fehlend_heiz)
            ergebnisse.append(CheckErgebnis(
                kategorie=kat, schwere=CheckSeverity.INFO,
                meldung=f"{name}: Heizwärme fehlt in {len(fehlend_heiz)} Monat(en)",
                details=monate_str,
                link=link_monat_erfassen(fehlend_heiz[0]),
            ))

        # N-379 stand bis 05.09.2026 HIER als Klima-Sonderfall („Warmwasser an einer
        # Split-Klimaanlage"). Er ist ein Fall der allgemeineren Klasse „Wert in
        # einem Feld, das dieses Gerät nicht führt" und steht jetzt für ALLE Typen
        # in `_check_werte_in_nicht_gefuehrten_feldern` (N-393) — aufgerufen aus
        # `stammdaten.py` im Block „Allgemeine Prüfungen für alle Typen".

        # ⛔ Die beiden Seiten-Listen gehören hier dazu. Vor dem 13.09.2026 bekam
        # ein Monat, dem genau eine Stromseite fehlte, nicht nur keine Warnung —
        # er bekam diese OK-Zeile, also eine ausdrückliche Zusage „vollständig".
        if not (fehlend_strom or fehlend_strom_heizen
                or fehlend_strom_ww or fehlend_heiz):
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
    return f"{fmt_zahl(betrag, 2)} €"


#: Anzeigename je Provenance-Label — Meldungstexte sind Anzeige, und
#: „external:brightsky" ist kein Wort, das jemand lesen will.
_ANBIETER_NAMEN = {
    "external:brightsky": "Bright Sky (DWD)",
    "external:openmeteo": "Open-Meteo",
}


class ErfassungsortChecks:
    """§8.1 — welche Fehleingabe das Wirtschaftlichkeits-Modell erzeugen kann."""

    async def _check_wetterwert_fehlt(
        self, anlage: Anlage, monatsdaten: list[Monatsdaten]
    ) -> list[CheckErgebnis]:
        """Die Kategorie trägt ihre ganze Klasse: alle DREI Wetterwerte.

        ⭐ **Erweitert am 29.09.2026** (Paket „Die Wetterreihe geradeziehen",
        #395 Punkt 1). Der eigene Kommentar der Kategorie sagte es seit N-426:
        *„Der Name nennt die Klasse, nicht das eine Feld … heute trägt die
        Kategorie nur den ersten, weil nur für ihn eine Quelle ohne Netzabruf
        existiert."* Genau diese Voraussetzung hat sich geändert — mit der
        Reparatur-Operation ``WETTER_BACKFILL`` gibt es für alle drei einen Weg.

        **Drei Zeilen, drei Fragen:**

        1. *Ø Temperatur fehlt* — unverändert, mit ihrer eigenen Aktion aus der
           Messreihe (das einzige Feld mit einer Quelle ohne Netzabruf).
        2. *Strahlung/Sonnenstunden fehlen* — bis hierher hatte kein Checker
           diese beiden Felder überhaupt gesehen.
        3. *Die Quelle ist uneinheitlich* — Monate, deren Wetterwert von einem
           anderen Anbieter stammt als die heutige Wahl. Sonnenstunden zweier
           Anbieter unterscheiden sich um Faktor 1,6–2,0; ein Jahresvergleich
           über eine gemischte Reihe ist eine Falschaussage.
        4. *Die Quelle ist nicht festgehalten* — Monate mit Strahlungswerten,
           deren Herkunft nirgends steht. **Das ist die Lage jedes Bestands**,
           und ohne diese Zeile bliebe sie stumm: Zeile 2 schweigt, weil Werte
           da sind, Zeile 3 schweigt, weil kein Label zum Vergleichen existiert
           — und der Anwender erführe nie, dass seine Reihe auf zwei Linealen
           stehen *könnte*. An einer echten Anlage gemessen (39 Monate): 0
           fehlende Werte, 0 Monate mit Anbieter-Label.

        ⛔ **Keine neue Kategorie** und ⛔ **kein Netzabruf in einer Prüfung**:
        Zeile 3 und 4 lesen ausschließlich ``source_provenance``.

        ⚠ **Zeile 3 und 4 sind überschneidungsfrei**, und das ist keine
        Kosmetik: Zwei Zahlen über dieselben Monate kann ein Anwender nicht
        zusammenzählen. Beide kommen deshalb aus **einer** Einordnung
        (`_wetterquellen_lage`), die jeden Monat genau einem Fach zuweist.
        """
        lage = self._wetterquellen_lage(anlage, monatsdaten)
        ergebnisse = await self._check_temperatur_fehlt(anlage, monatsdaten)
        ergebnisse += self._check_strahlungswerte_fehlen(anlage, monatsdaten)
        ergebnisse += self._check_wetterquelle_uneinheitlich(lage)
        ergebnisse += self._check_wetterquelle_nicht_festgehalten(lage)
        return ergebnisse

    # ── Zeile 3: die Quelle einer Reihe ─────────────────────────────────────

    def _erwartetes_wetter_label(self, anlage: Anlage) -> Optional[str]:
        """Welches Provenance-Label die heutige Wahl der Anlage erzeugen würde.

        ⚠ **Ohne einen einzigen Netzabruf.** ``nutze_brightsky`` ist eine reine
        Funktion über Land, Koordinaten-Box und Schalter — genau die Regel, die
        ``auto`` zur Laufzeit anwendet. ``None`` heißt „lässt sich hier nicht
        sagen" (keine Koordinaten), und dann gibt es keine Zeile: eine Prüfung,
        die raten muss, schweigt.
        """
        from backend.core.config import settings
        from backend.services.wetter.monatswerte import PROVENANCE_LABEL
        from backend.services.wetter.orchestrator import nutze_brightsky

        wahl = getattr(anlage, "wetter_provider", None) or "auto"
        if wahl == "brightsky":
            return PROVENANCE_LABEL["brightsky"]
        if wahl == "open-meteo":
            return PROVENANCE_LABEL["open-meteo"]
        if not anlage.latitude or not anlage.longitude:
            return None
        nutzt_dwd = (
            nutze_brightsky(anlage.latitude, anlage.longitude, anlage.standort_land)
            and settings.brightsky_enabled
        )
        return PROVENANCE_LABEL["brightsky" if nutzt_dwd else "open-meteo"]

    @dataclass
    class _WetterquellenLage:
        """Wie die Wetterwerte einer Anlage über die Quellen verteilt sind.

        Jeder abgeschlossene Monat landet in **höchstens einem** Fach — das ist
        der Grund, warum diese Einordnung einmal passiert und nicht zweimal.
        """

        erwartet: Optional[str]
        #: Trägt ein bekanntes Anbieter-Label, das NICHT die heutige Wahl ist.
        abweichend: list[Monatsdaten]
        #: Die fremden Labels, für die Meldung.
        fremde: set[str]
        #: Hat Strahlungswerte, aber zu keinem davon ein Anbieter-Label.
        ohne_label: list[Monatsdaten]

    def _wetterquellen_lage(
        self, anlage: Anlage, monatsdaten: list[Monatsdaten]
    ) -> "ErfassungsortChecks._WetterquellenLage":
        """Ordnet jeden abgeschlossenen Monat genau einem Fach zu.

        ⛔ **Die Ø Temperatur zählt für „ohne Label" NICHT mit**, und das ist
        der Unterschied zwischen einer Prüfung und einem Fehlalarm: Sie hat
        legitim keinen Anbieter. Kommt sie aus der eigenen Messreihe, stempeln
        sowohl die N-426-Aktion als auch der nächtliche Lückenschluss
        ``manual:form`` — das ist richtig und ändert sich nie. Sie
        mitzuzählen erzeugte auf **jeder gesunden Anlage** eine Meldung, die
        sich durch nichts abstellen lässt.

        Für die Abweichung (Zeile 3) zählt sie sehr wohl mit: trägt sie ein
        **bekanntes** Anbieter-Label, stammt sie aus dem Archiv, und ein
        fremdes Archiv ist dort dieselbe Aussage wie bei der Strahlung.
        """
        from backend.services.wetter.monatswerte import (
            PROVENANCE_LABEL, WETTER_MONATSFELDER,
        )

        #: Nur diese beiden tragen eine Anbieter-Pflicht — s. Docstring.
        strahlungsfelder = ("globalstrahlung_kwh_m2", "sonnenstunden")

        erwartet = self._erwartetes_wetter_label(anlage)
        bekannt = set(PROVENANCE_LABEL.values())
        heute = date.today()

        abweichend: list[Monatsdaten] = []
        fremde: set[str] = set()
        ohne_label: list[Monatsdaten] = []

        for md in monatsdaten:
            if (md.jahr, md.monat) >= (heute.year, heute.month):
                continue
            prov = md.source_provenance or {}

            gefunden: set[str] = set()
            for feld in WETTER_MONATSFELDER:
                quelle = (prov.get(feld) or {}).get("source")
                if quelle in bekannt:
                    gefunden.add(quelle)

            anders = {q for q in gefunden if erwartet is not None and q != erwartet}
            if anders:
                abweichend.append(md)
                fremde |= anders
                continue

            # Ein Feld OHNE Wert ist keine unbekannte Quelle, sondern eine
            # Lücke — die meldet Zeile 2, und zwar mit einem anderen Weg.
            hat_wert_ohne_label = any(
                getattr(md, feld, None) is not None
                and (prov.get(feld) or {}).get("source") not in bekannt
                for feld in strahlungsfelder
            )
            if hat_wert_ohne_label:
                ohne_label.append(md)

        return self._WetterquellenLage(
            erwartet=erwartet, abweichend=abweichend,
            fremde=fremde, ohne_label=ohne_label,
        )

    def _check_wetterquelle_uneinheitlich(
        self, lage: "ErfassungsortChecks._WetterquellenLage"
    ) -> list[CheckErgebnis]:
        """Monate, deren Wetterwert von einem ANDEREN Anbieter stammt.

        ⚠ **Was diese Zeile NICHT kann, und das gehört dazu:** Sie sieht nur,
        was in ``source_provenance`` steht. Ein Wert aus der Zeit vor dieser
        Lieferung trägt dort ``manual:form`` oder gar nichts — er ist damit
        **unbekannter**, nicht **anderer** Herkunft, und wird hier nicht
        gezählt. Eine Prüfung, die eine fehlende Angabe als Abweichung meldete,
        erzeugte eine Zahl, die niemand nachvollziehen kann. Für genau diese
        Monate gibt es die Schwester-Zeile `_check_wetterquelle_nicht_festgehalten`.
        """
        abweichend, erwartet = lage.abweichend, lage.erwartet
        if not abweichend or erwartet is None:
            return []

        def _mm(md: Monatsdaten) -> str:
            return f"{md.monat:02d}/{md.jahr}"

        beispiele = ", ".join(_mm(md) for md in abweichend[:6])
        if len(abweichend) > 6:
            beispiele += f" (+{len(abweichend) - 6} weitere)"
        namen = ", ".join(sorted(_ANBIETER_NAMEN.get(q, q) for q in lage.fremde))

        return [CheckErgebnis(
            kategorie=CheckKategorie.WETTERWERT_FEHLT,
            schwere=CheckSeverity.INFO,
            meldung=(
                f"{len(abweichend)} Monat(e) stammen aus einer anderen "
                "Wetterquelle als die aktuelle Wahl"
            ),
            details=(
                f"Diese Monate tragen Werte von {namen}, während eedc heute "
                f"{_ANBIETER_NAMEN.get(erwartet, erwartet)} fragt. Die beiden "
                "messen nicht gleich: bei der Globalstrahlung liegen sie 12–16 % "
                "auseinander, bei den Sonnenstunden um den Faktor 1,6–2,0. "
                "Ein Vergleich über mehrere Jahre ist damit nicht aussagekräftig — "
                "ein Jahr sähe schwach aus, weil die Quelle gewechselt hat, nicht "
                "weil die Sonne weniger schien. „Wetterreihe nachziehen“ holt "
                "alle abgeschlossenen Monate von der heute gewählten Quelle; der "
                "laufende Monat bleibt draußen, weil die Archive ihn noch nicht "
                f"vollständig haben. Betroffen: {beispiele}."
            ),
            # ⛔ Hier steht bewusst KEINE Inline-Aktion, obwohl es die Operation
            # gibt. Der Nachzug ERSETZT vorhandene Werte — und
            # `write_with_provenance` verlangt im Docstring ausdrücklich, dass
            # der Aufrufer dem Anwender vorher sagt, was ersetzt wird. Ein
            # Ein-Klick-Knopf könnte das nicht; die Vorschau der
            # Reparatur-Werkbank nennt die Zahl, bevor etwas passiert.
            link=LINK_ENERGIEPROFIL,
        )]

    # ── Zeile 3b: die Quelle steht nirgends ─────────────────────────────────

    def _check_wetterquelle_nicht_festgehalten(
        self, lage: "ErfassungsortChecks._WetterquellenLage"
    ) -> list[CheckErgebnis]:
        """Monate mit Strahlungswerten, deren Herkunft nirgends festgehalten ist.

        ⭐ **Warum es diese Zeile braucht — an einer echten Anlage gemessen
        (39 Monate, 29.09.2026):** Strahlung und Sonnenstunden fehlten in **0**
        Monaten, also schwieg Zeile 2. **Kein einziger** Monat trug ein
        Anbieter-Label, also schwieg auch Zeile 3 — sie kann nur vergleichen,
        was dasteht. Ergebnis: Die Reihe stand weiterhin auf zwei Linealen, das
        Werkzeug lag bereit, und **nichts sagte es dem Anwender**. Genau diese
        Lage schließt diese Zeile.

        ⛔ **Sie behauptet NICHT, die Reihe sei gemischt** — das weiß sie nicht
        und kann es nicht wissen. Sie sagt, dass es sich **nicht mehr sagen
        lässt**. Der Unterschied ist der ganze Punkt: eine Prüfung, die eine
        Unkenntnis als Befund ausgibt, wäre dieselbe Falschaussage, gegen die
        dieses Paket gebaut ist.

        ⛔ **Die Ø Temperatur zählt nicht mit** (Begründung in
        `_wetterquellen_lage`): sie hat legitim keinen Anbieter, und sie
        mitzunehmen ergäbe auf jeder gesunden Anlage eine Dauermeldung.

        ⭐ **Sie verstummt von selbst.** Sobald jeder Monat ein Anbieter-Label
        trägt — nach einem einmaligen Nachzug —, ist die Menge leer und die
        Zeile verschwindet. Sie ist ein Übergangsbefund für den Bestand, kein
        Dauerzustand, und niemand muss sie später „abstellen".
        """
        ohne = lage.ohne_label
        if not ohne:
            return []

        def _mm(md: Monatsdaten) -> str:
            return f"{md.monat:02d}/{md.jahr}"

        beispiele = ", ".join(_mm(md) for md in ohne[:6])
        if len(ohne) > 6:
            beispiele += f" (+{len(ohne) - 6} weitere)"

        return [CheckErgebnis(
            kategorie=CheckKategorie.WETTERWERT_FEHLT,
            schwere=CheckSeverity.INFO,
            meldung=(
                f"{len(ohne)} abgeschlossene(r) Monat(e) tragen keine "
                "festgehaltene Wetterquelle"
            ),
            details=(
                "Bei diesen Monaten steht nicht dabei, von welchem Wetterdienst "
                "Globalstrahlung und Sonnenstunden stammen. **Ob alle aus "
                "derselben Quelle kommen, lässt sich damit nicht mehr "
                "feststellen** — und das ist keine Kleinigkeit: Open-Meteo und "
                "Bright Sky (DWD) messen Sonnenstunden um den Faktor 1,6–2,0 "
                "verschieden. Stammen einzelne Monate aus der jeweils anderen "
                "Quelle, sähe ein Jahr schwach aus, weil die Quelle gewechselt "
                "hat, nicht weil die Sonne weniger schien. "
                "Ein einmaliges „Wetterreihe nachziehen“ in der "
                "Reparatur-Werkbank holt alle abgeschlossenen Monate von der an "
                "der Anlage gewählten Quelle und schreibt sie fest; danach "
                "verschwindet dieser Hinweis von selbst. Der laufende Monat "
                "bleibt dabei draußen, weil die Archive ihn noch nicht "
                f"vollständig haben. Betroffen: {beispiele}."
            ),
            # Kein Inline-Knopf, aus demselben Grund wie bei den Nachbarzeilen:
            # derselbe Lauf ersetzt, was schon dasteht.
            link=LINK_ENERGIEPROFIL,
        )]

    # ── Zeile 2: Strahlung und Sonnenstunden ────────────────────────────────

    def _check_strahlungswerte_fehlen(
        self, anlage: Anlage, monatsdaten: list[Monatsdaten]
    ) -> list[CheckErgebnis]:
        """Abgeschlossene Monate ohne Globalstrahlung oder Sonnenstunden.

        ⛔ **Der laufende Monat bleibt draußen** — dieselbe Begründung wie beim
        Nachzug: die Archive liefern ihn noch nicht vollständig, und eine Zeile,
        die eine Lücke nennt, für die es heute keinen Weg gibt, ist eine Aufgabe
        ohne Lösung.
        """
        heute = date.today()
        abgeschlossen = [
            md for md in monatsdaten
            if (md.jahr, md.monat) < (heute.year, heute.month)
        ]
        offen = [
            md for md in abgeschlossen
            if md.globalstrahlung_kwh_m2 is None or md.sonnenstunden is None
        ]
        if not offen:
            return []

        def _mm(md: Monatsdaten) -> str:
            return f"{md.monat:02d}/{md.jahr}"

        beispiele = ", ".join(_mm(md) for md in offen[:6])
        if len(offen) > 6:
            beispiele += f" (+{len(offen) - 6} weitere)"

        return [CheckErgebnis(
            kategorie=CheckKategorie.WETTERWERT_FEHLT,
            schwere=CheckSeverity.INFO,
            meldung=(
                f"Globalstrahlung oder Sonnenstunden fehlen in "
                f"{len(offen)} Monat(en)"
            ),
            details=(
                "Beide Größen sagen, wie viel Sonne ein Monat überhaupt hatte — "
                "ohne sie lässt sich ein schwaches Jahr nicht von einer "
                "schwachen Anlage unterscheiden. „Wetterreihe nachziehen“ holt "
                "sie für alle abgeschlossenen Monate von der an der Anlage "
                "gewählten Quelle. Der laufende Monat bleibt draußen — die "
                "Archive liefern ihn erst ein paar Tage nach Monatsende. "
                f"Betroffen: {beispiele}."
            ),
            # Kein Inline-Knopf, aus demselben Grund wie oben: derselbe Lauf
            # ersetzt auch, was schon dasteht.
            link=LINK_ENERGIEPROFIL,
        )]

    # ── Zeile 1: die Ø-Temperatur (N-426-Nachtrag, unverändert) ─────────────

    async def _check_temperatur_fehlt(
        self, anlage: Anlage, monatsdaten: list[Monatsdaten]
    ) -> list[CheckErgebnis]:
        """**N-426-Nachtrag** — Monate ohne Ø-Temperatur, und wie viele erreichbar sind.

        ⛔ **Warum es diese Zeile überhaupt gibt.** Der Wetter-Auto-Fill des
        Monatsformulars ist mit dem IA-V4-Flip (`243944e5`, 25.07.2026) samt der
        alten Seite verschwunden und mit WK-03 (`fe28f49e`) zurückgekehrt. Er
        wirkt **nach vorn**: Jeder seit dem V4-Flip abgeschlossene Monat trägt
        weiterhin `NULL`, und der Anwender hätte jeden einzelnen aufmachen und
        „Wetterdaten holen" drücken müssen. An der Demo-Anlage gemessen (11.09.):
        34 von 34 Monaten leer, die Messreihe erreicht 7 davon.

        ⭐ **Die Zeile nennt BEIDE Zahlen, und das ist ihre Aussage.** „n Monate
        ohne Ø Temperatur" allein wäre eine Aufgabe ohne Weg; „für m davon reicht
        die Messreihe" sagt, was der Knopf leisten kann und was nicht. Für die
        übrigen gibt es keinen Knopf — dort hilft nur der Auto-Fill im Monat
        selbst, und der holt seinen Wert aus dem Netz.

        ⚠ **Kein Netzabruf in einer Prüfung.** Die Erreichbarkeit kommt aus
        `lade_monatsmittel_temperatur` **ohne** ``gepflegt_je_monat`` — also
        Stufe 1 (Stundenmittel) und Stufe 2 (Tages-Min/Max) der Vorrangkette,
        ohne die dritte, die das gepflegte Feld selbst ist. Ein Kreislauf wäre
        es sonst, und eine Prüfung, die Provider anfragt, wäre eine Prüfung mit
        Nebenwirkung.

        ⚠ **`hat_zaehlerzeile` ist die Grundmenge, nicht der Erwartungs-Anker.**
        Gefragt wird nur nach Monaten, die es als Zeile **gibt** — ein Monat, den
        der Anwender nie abgeschlossen hat, ist keine Wetter-Lücke, sondern eine
        Monats-Lücke, und die meldet der Nachbar-Check.
        """
        kat = CheckKategorie.WETTERWERT_FEHLT
        offen = [md for md in monatsdaten if md.durchschnittstemperatur is None]
        if not offen:
            if monatsdaten:
                return [CheckErgebnis(
                    kategorie=kat, schwere=CheckSeverity.OK,
                    meldung=(
                        f"Alle {len(monatsdaten)} erfassten Monate tragen eine "
                        "Ø Temperatur"
                    ),
                )]
            return []

        from backend.services.mitteltemperatur import lade_monatsmittel_temperatur

        # Stufe 1+2 der Vorrangkette — ohne die dritte (das Feld selbst).
        messreihe = await lade_monatsmittel_temperatur(self.db, anlage.id)
        erreichbar = [md for md in offen if (md.jahr, md.monat) in messreihe]

        def _mm(md: Monatsdaten) -> str:
            return f"{md.monat:02d}/{md.jahr}"

        beispiele = ", ".join(_mm(md) for md in offen[:6])
        if len(offen) > 6:
            beispiele += f" (+{len(offen) - 6} weitere)"

        gemeinsam = (
            "Das Feld „Ø Temperatur“ im Monatsabschluss wird seit dem "
            "Oberflächen-Wechsel im Juli 2026 wieder automatisch gefüllt — das "
            "wirkt aber nur nach vorn. eedc rechnet mit dem Feld heute keine "
            "Kennzahl aus (die Außentemperatur-Linie und der Vergleich je "
            "Heizgradtag lesen die eigene Tagesreihe); es ist die gepflegte "
            "Rückfallebene für Monate, in denen diese Reihe fehlt. "
            f"Betroffen: {beispiele}."
        )

        if not erreichbar:
            return [CheckErgebnis(
                kategorie=kat, schwere=CheckSeverity.INFO,
                meldung=f"Ø Temperatur fehlt in {len(offen)} Monat(en)",
                details=(
                    f"{gemeinsam} Für keinen dieser Monate reicht die eigene "
                    "Messreihe zurück — dort hilft nur, den Monat im "
                    "Monatsabschluss zu öffnen und „Wetterdaten holen“ zu "
                    "drücken; eedc holt den Wert dann aus dem Wetter-Archiv."
                ),
                link=link_monat_erfassen(_mm(offen[0])),
            )]

        return [CheckErgebnis(
            kategorie=kat, schwere=CheckSeverity.INFO,
            meldung=(
                f"Ø Temperatur fehlt in {len(offen)} Monat(en), "
                f"für {len(erreichbar)} davon reicht die Messreihe"
            ),
            details=(
                f"{gemeinsam} „Temperatur aus Messung übernehmen“ trägt die "
                f"{len(erreichbar)} erreichbaren Monate aus deinen eigenen "
                "Messwerten nach (Stundenmittel, sonst Tages-Min/Max) — "
                "bereits gepflegte Werte bleiben unberührt. Für die "
                f"übrigen {len(offen) - len(erreichbar)} reicht die Reihe nicht "
                "zurück; dort hilft nur, den Monat im Monatsabschluss zu öffnen "
                "und „Wetterdaten holen“ zu drücken."
                if len(erreichbar) < len(offen) else
                f"{gemeinsam} „Temperatur aus Messung übernehmen“ trägt sie aus "
                "deinen eigenen Messwerten nach (Stundenmittel, sonst "
                "Tages-Min/Max) — bereits gepflegte Werte bleiben unberührt."
            ),
            link=link_monat_erfassen(_mm(offen[0])),
            action_kind="temperatur_aus_messung",
            action_label="Temperatur aus Messung übernehmen",
            action_params={
                "anlage_id": anlage.id,
                "monate": [_mm(md) for md in erreichbar],
            },
        )]

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
