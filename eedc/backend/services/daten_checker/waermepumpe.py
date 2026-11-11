"""
Daten-Checker — gemessene Wärmepumpen-Kennzahlen (`WaermepumpeChecks`).

**Warum es diese Datei gibt (07.09.2026, Paket b).** Der Community-Server zeigte
für eine Region eine „JAZ" von **13,67**, das Anlagen-Ranking eine **13,8** —
beide Werte hatten P12, W-14 und A5 vollständig passiert. Eine Jahresarbeitszahl
von 13 gibt es nicht; eine sehr gute Sole-Wasser-Anlage erreicht rund 5.

⭐ **Der Server kann das nicht auflösen — er hat die Geräte nie gesehen.** Er kann
die Kennzahl nur sperren (das tut er seit `core/wp_jaz.py::MONATS_ARBEITSZAHL_MAX`).
**Erklären kann es nur eedc**, weil hier die Investition mit ihren Zählern steht.
Eine Sperre ohne Erklärung wäre genau das „—" ohne Grund, das SOLL §3.3/S3
verbietet — deshalb sind es zwei Hälften, und dies ist die zweite.

**Was die Meldung sagt, sagt das Konzept**, SOLL §3.2b Fall **A7**:
*„Bivalent: Gaskessel speist denselben Heizkreis, sein Strom fehlt — Q zu groß
⇒ Zahl zu hoch."* Ein Wärmemengenzähler hinter Kessel **und** Wärmepumpe misst
die Wärme beider und teilt sie durch den Strom einer.

⛔ **Kein zweiter Turm über der gepflegten JAZ.** `stammdaten.py` prüft den
**Parameter** „JAZ" (1,5–7,0) — eine Eingabe. Hier geht es um die **gemessenen**
Monatswerte, also um etwas anderes: Eine Anlage kann eine tadellose gepflegte JAZ
haben und trotzdem einen Wärmemengenzähler an der falschen Stelle. Die zwei
Meldungen können nebeneinander stehen, ohne dasselbe zu sagen.
"""

from backend.core.berechnungen.betriebsart_gemessen import (
    funktionsfremd_abzug_kwh,
    modus_strom_zeile,
)
from backend.core.berechnungen.waermepumpe_kennzahl import (
    abgrenzungs_grund,
    arbeitszahl,
    heizwaerme_kwh,
    waerme_gesamt_kwh,
)
from backend.core.investition_parameter import abgrenzung_stoerung
from backend.core.field_definitions import (
    get_wp_strom_kwh,
    get_wp_warmwasser_kwh,
    nenner_ist_feine_summe,
)
from backend.models.anlage import Anlage

from .gruppen import je_geraet_begrenzt
from .kategorien import CheckErgebnis, CheckKategorie, CheckSeverity
from .ziele import ziel_monat
from backend.core.zahlenformat import fmt_zahl


class WaermepumpeChecks:
    """Diagnose für gemessene WP-Monatswerte."""

    #: Ab hier ist eine **Monats**-Arbeitszahl erklärungsbedürftig. Bewusst
    #: großzügig: Eine Monatszahl streut stärker als eine Jahreszahl — eine
    #: Sole-Wasser-Anlage im Übergangsmonat kann legitim über 6 liegen.
    #: ⚑ Spiegel von `wp_jaz.MONATS_ARBEITSZAHL_AUFFAELLIG` im Community-Repo;
    #: dort sperrt `MONATS_ARBEITSZAHL_MAX` (10) die Kennzahl, hier erklärt
    #: eedc schon früher, warum sie auffällig ist.
    ARBEITSZAHL_AUFFAELLIG = 7.0

    #: Höchstens so viele Einzelmonate **je Gerät** nennen — der Rest wird gezählt (E6.B N5).
    MAX_EINZEL = 6

    def _check_wp_arbeitszahl_unplausibel(self, anlage: Anlage) -> list[CheckErgebnis]:
        """Monatszeilen, deren gemessene Arbeitszahl über dem Plausiblen liegt.

        ⛔ **Die Zahl wird NICHT selbst gebildet** (ADR-002/**P12**) — sie kommt
        aus `core/berechnungen/waermepumpe_kennzahl.arbeitszahl`, demselben
        Layer, aus dem die Anzeige sie holt. Ein Checker, der seinen eigenen
        Quotienten bildet, meldet irgendwann etwas anderes, als die Kachel zeigt.

        ⚠ **Nur wo die Kennzahl überhaupt gebildet werden DARF.** Gibt der Layer
        einen Grund statt eines Werts zurück (Abgrenzung verletzt, Wärme
        gerechnet statt gemessen), ist der Fall bereits behandelt — dann wäre
        diese Meldung ein zweiter Turm über einer Sperre, die schon greift.

        ⛔ **Derselbe Layer reicht nicht — es müssen dieselben EINGÄNGE sein**
        (#411, 08.09.2026). Bis dahin rief diese Stelle ``arbeitszahl(Q, E)``
        ohne ``strom_funktionsfremd_kwh``, während Kachel und Cockpit den
        Kühl-, Lüft- und Entfeuchtungsstrom aus dem Nenner ziehen (W-14/E4).
        Bei OB73-gifs Zeile (749 kWh Wärme · 214 kWh Strom · davon 207 kWh
        Kühlbetrieb) rechnete der Checker **3,5** und schwieg, während die
        Kachel **107,0** zeigte — eine Zahl, die keine Wärmepumpe leisten kann.
        *Der Docstring darüber war schon richtig; die Umsetzung war es nicht.*

        ⭐ **Dieselbe Lehre, zweite Runde (N-450, 12.09.2026): auch die
        Lesetüren brauchen ihre ``params``.** ``get_wp_strom_kwh(daten)`` ohne
        das Parameter-Wörterbuch nimmt **immer** den nicht-getrennten Zweig und
        liest ``stromverbrauch_kwh``. An einer Anlage mit **getrennter
        Strommessung** steht dort nichts — der Strom liegt in
        ``strom_heizen_kwh`` und ``strom_warmwasser_kwh``. Rückgabe **0**,
        ``if not strom: continue``, und die Plausibilitätsprüfung sah
        **ausgerechnet die sorgfältigst eingerichteten Anlagen nie**. Dasselbe
        galt für ``get_wp_warmwasser_kwh(daten)``: Ohne ``params`` fehlt der
        Geräte-Filter aus N-379, und ein an einer Luft-Luft-Anlage gepflegter
        Warmwasser-Wert hätte hier mitgezählt. Der Docstring der Lesetür sagt
        es wörtlich — *„die Lage der Aufrufer, die keine Investition zur Hand
        haben (Import-/Schreibpfade)"* —; ein Checker hat sie zur Hand.

        ⭐ **Und der Abzug ist seit SOLL-§9-E7/Option A nicht die Menge**
        (12.09.2026): Bei getrennter Strommessung mit nur **abgeleiteter**
        Aufteilung darf der funktionsfremde Anteil den Nenner nicht kürzen. Er
        kommt deshalb aus ``funktionsfremd_abzug_kwh`` — derselben Stelle, aus
        der die Anzeige ihn holt. Ein Checker, der weiter die Rohmenge abzöge,
        rechnete an genau den Anlagen zu niedrig, die er seit N-450 überhaupt
        erst sieht.
        """
        kat = CheckKategorie.MONATSDATEN_PLAUSIBILITAET.value
        ergebnisse: list[CheckErgebnis] = []

        treffer: list[tuple[int, str, int, int, float]] = []
        for inv in anlage.investitionen:
            if inv.typ != "waermepumpe":
                continue
            name = inv.bezeichnung or f"#{inv.id}"
            # E6.D D4: die Anwender-Angabe «Abgrenzung» (Fremdstrom/Fremdwärme) geht wie in der Anzeige
            # (`waermepumpe_kennzahlen_je_geraet`, Monat je Gerät) als Grund in den Layer — dann gibt es keine Zahl,
            # und die Meldung entfällt (Docstring oben: «Abgrenzung verletzt … ist der Fall bereits behandelt»).
            abgrenzung = abgrenzungs_grund(abgrenzung_stoerung=abgrenzung_stoerung(inv))
            for imd in inv.monatsdaten:
                daten = imd.verbrauch_daten or {}
                # N-450: **mit `params`** — sonst nimmt die Lesetür den
                # nicht-getrennten Zweig und liefert an jeder F5-Anlage 0.
                params = inv.parameter or {}
                strom = get_wp_strom_kwh(daten, params)
                # R-3/N-488: **dieselbe Weiche wie die Anzeige** (D1-Stufe 3).
                # Die alte Lesetür `get_wp_heizenergie_kwh` kennt die gemessene
                # Nutzenergie Heizbetrieb nicht; an einem Gerät, das sie pflegt,
                # prüfte der Checker damit eine andere Heizwärme als Hub und
                # Cockpit zeigen — die N-450-Klasse mit Ansage (Konzept 11.5:
                # der Prüfer liest dieselben Eingänge wie die Anzeige).
                waerme_h = heizwaerme_kwh(daten) or 0.0
                waerme_w = get_wp_warmwasser_kwh(daten, params)
                if not strom:
                    continue
                # N-391: **kanonisch wie die Anzeige** (D1) — sonst sähe der
                # Prüfer an einer Wärmepumpe mit gemeinsamem Wärmemengenzähler
                # gar keine Wärme und schwiege zu jeder Auffälligkeit, während
                # Hub und Cockpit die Zahl längst zeigen.
                waerme = waerme_gesamt_kwh(
                    daten.get("waerme_kwh"), waerme_h, waerme_w,
                )
                if waerme <= 0:
                    continue
                # Derselbe Nenner-Abzug wie in der Anzeige — und zwar der
                # **Abzug** (SOLL-§9-E7/Option A), nicht die Menge:
                # `funktionsfremd_abzug_kwh` entscheidet je Gerät, ob der
                # Anteil überhaupt im Nenner steht.
                az = arbeitszahl(
                    waerme, strom,
                    strom_funktionsfremd_kwh=funktionsfremd_abzug_kwh(
                        modus_strom_zeile(daten),
                        # N-462: die **Stufe** dieser Zeile, nicht das
                        # Kennzeichen — sonst prüft der Prüfer eine andere Zahl
                        # als die Anzeige (er ist genau dafür da, dass beide
                        # dieselbe nennen).
                        hat_split=nenner_ist_feine_summe(daten, params),
                    ),
                    abgrenzung_verletzt=abgrenzung,
                )
                if az.wert is None:
                    continue
                if az.wert > self.ARBEITSZAHL_AUFFAELLIG:
                    treffer.append((inv.id, name, imd.jahr, imd.monat, az.wert))

        if not treffer:
            return ergebnisse

        # Datums-Listen absteigend (Regel 0a), Gerät als zweites Kriterium.
        treffer.sort(key=lambda t: (-t[2], -t[3], t[1]))
        # E5 V2: keine Restzeile mehr — die über der Grenze weggelassenen Monate je Gerät stehen als `weitere` an der
        # Gruppenzeile (`gruppen.py`); E6.B N5: die Grenze gilt je Gerät.
        auswahl, weitere = je_geraet_begrenzt(treffer, self.MAX_EINZEL)
        for inv_id, name, jahr, monat, wert in auswahl:
            ergebnisse.append(CheckErgebnis(
                kategorie=kat, schwere=CheckSeverity.WARNING.value, code="wp_arbeitszahl_zu_hoch",
                meldung=(
                    f"{name}: Arbeitszahl {fmt_zahl(wert, 1)} im {monat:02d}/{jahr} — "
                    "höher, als eine Wärmepumpe leisten kann"
                ),
                details=(
                    "Über etwa 7 liegt keine Wärmepumpe im Monatsmittel; über 10 "
                    "lässt eedc den Wert im Community-Vergleich ganz weg. Der "
                    "häufigste Grund ist ein Wärmemengenzähler, der mehr misst "
                    "als deine Wärmepumpe liefert: Speist ein zweiter Erzeuger "
                    "denselben Heizkreis — ein Gas- oder Ölkessel, ein Kamin mit "
                    "Wassertasche, ein Heizstab vor dem Zähler? Dann steht seine "
                    "Wärme mit im Zähler, sein Strom aber nicht in der Rechnung. "
                    "Am Gerät lässt sich das unter „Abgrenzung“ angeben; dann "
                    "zeigt eedc statt der Zahl den Grund. Die erfassten "
                    "Kilowattstunden bleiben davon unberührt — sie sind richtig "
                    "und zählen in allen Mengen weiter mit."
                ),
                ziel=ziel_monat(jahr, monat, geraet=inv_id, feld="waerme_kwh"),
                investition_id=inv_id, werte={"weitere": weitere[inv_id]} if weitere[inv_id] else None,
            ))

        return ergebnisse
