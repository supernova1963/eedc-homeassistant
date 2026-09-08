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

from backend.core.berechnungen.betriebsart_gemessen import modus_strom_zeile
from backend.core.berechnungen.waermepumpe_kennzahl import arbeitszahl
from backend.core.field_definitions import (
    get_wp_heizenergie_kwh,
    get_wp_strom_kwh,
    get_wp_warmwasser_kwh,
)
from backend.models.anlage import Anlage

from .kategorien import CheckErgebnis, CheckKategorie, CheckSeverity


class WaermepumpeChecks:
    """Diagnose für gemessene WP-Monatswerte."""

    #: Ab hier ist eine **Monats**-Arbeitszahl erklärungsbedürftig. Bewusst
    #: großzügig: Eine Monatszahl streut stärker als eine Jahreszahl — eine
    #: Sole-Wasser-Anlage im Übergangsmonat kann legitim über 6 liegen.
    #: ⚑ Spiegel von `wp_jaz.MONATS_ARBEITSZAHL_AUFFAELLIG` im Community-Repo;
    #: dort sperrt `MONATS_ARBEITSZAHL_MAX` (10) die Kennzahl, hier erklärt
    #: eedc schon früher, warum sie auffällig ist.
    ARBEITSZAHL_AUFFAELLIG = 7.0

    #: Höchstens so viele Einzelmonate nennen — der Rest wird gezählt.
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
        """
        kat = CheckKategorie.MONATSDATEN_PLAUSIBILITAET.value
        ergebnisse: list[CheckErgebnis] = []

        treffer: list[tuple[int, str, int, int, float]] = []
        for inv in anlage.investitionen:
            if inv.typ != "waermepumpe":
                continue
            name = inv.bezeichnung or f"#{inv.id}"
            for imd in inv.monatsdaten:
                daten = imd.verbrauch_daten or {}
                strom = get_wp_strom_kwh(daten)
                waerme_h = get_wp_heizenergie_kwh(daten)
                waerme_w = get_wp_warmwasser_kwh(daten)
                if not strom:
                    continue
                waerme = (waerme_h or 0) + (waerme_w or 0)
                if waerme <= 0:
                    continue
                # Derselbe Nenner-Abzug wie in der Anzeige — `funktionsfremd_kwh`
                # ist die eine Stelle, die sagt, was funktionsfremd heißt, und
                # `modus_strom_zeile` liefert ihn aus beiden Aufteilungswegen.
                az = arbeitszahl(
                    waerme, strom,
                    strom_funktionsfremd_kwh=modus_strom_zeile(daten).funktionsfremd_kwh,
                )
                if az.wert is None:
                    continue
                if az.wert > self.ARBEITSZAHL_AUFFAELLIG:
                    treffer.append((inv.id, name, imd.jahr, imd.monat, az.wert))

        if not treffer:
            return ergebnisse

        # Datums-Listen absteigend (Regel 0a), Gerät als zweites Kriterium.
        treffer.sort(key=lambda t: (-t[2], -t[3], t[1]))
        for inv_id, name, jahr, monat, wert in treffer[: self.MAX_EINZEL]:
            ergebnisse.append(CheckErgebnis(
                kategorie=kat, schwere=CheckSeverity.WARNING.value,
                meldung=(
                    f"{name}: Arbeitszahl {wert:.1f} im {monat:02d}/{jahr} — "
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
                link="/einstellungen/investitionen",
                investition_id=inv_id,
            ))

        if len(treffer) > self.MAX_EINZEL:
            rest = len(treffer) - self.MAX_EINZEL
            ergebnisse.append(CheckErgebnis(
                kategorie=kat, schwere=CheckSeverity.INFO.value,
                meldung=f"… plus {rest} weitere(r) Monat(e) mit derselben Auffälligkeit",
            ))

        return ergebnisse
