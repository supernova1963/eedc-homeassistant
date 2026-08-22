"""
Daten-Checker — Verbrauchszähler unter *Sonstiges* (`ZaehlerChecks`).

**Warum ein eigenes Modul (D3, 22.08.2026).** Ein Gas-, Wasser- oder Ölzähler
ist seit v4.0.23 (#377 / N-294) eine eigene Datenart: er führt **einen
Zählerstand**, die einzige Rechnung darauf ist *Ende − Anfang*, und er geht in
**keine** Bewertung ein — nicht in Energiebilanz, Autarkie, Wirtschaftlichkeit,
CO₂ oder den Community-Datensatz. Die Fragen, die man an ihn stellt, sind
deshalb andere als die an einen Stromzähler, und die Antworten der bestehenden
Kategorien passen nicht auf ihn.

Der Zuschnitt folgt `emob.py`: ein Mixin je Geräte-Domäne, keine neue
Paketstruktur.

**Drei Fragen, alle datengetrieben:**

1. *Kommt überhaupt ein Stand an?* — nicht „ist ein HA-Sensor zugeordnet?".
   Ein Stand kann aus dem stündlichen Snapshot kommen (HA **oder** MQTT) oder
   von Hand im Monatsabschluss gepflegt sein; beide Wege sind gleichwertig
   (Konzept #377: *„Manuelle Pflege ist gewollt"*). Wer die Konfiguration
   prüfte statt der Daten, meldete den Standalone-/MQTT-Anwender und den
   Ableser als „ohne Quelle" — die P-6-Falle.
2. *Läuft die Reihe rückwärts?* — der Bruch, den v4.0.25 selbst erzeugt.
3. *Ist das Gerät auf inaktiv gesetzt, obwohl es Ablesungen trägt?* — der
   Fallstrick, vor dem der v4.0.23-CHANGELOG in Prosa warnt und die Anwendung
   bisher schwieg.

⛔ **Keine Reparatur-Action in diesem Modul.** eedc kann einen Reihenbruch
nicht heilen, ohne zu raten, welcher der beiden Stände gilt — und die
Entscheidung „Zähler gewechselt" gehört dem Anwender. **Erklären und den Weg
danebenstellen, nicht heilen** ([[feedback_kein_grosser_heiler_knopf]] ·
[[feedback_daten_checker_kein_akzeptiert]]).
"""

from __future__ import annotations

from datetime import datetime

from backend.models.anlage import Anlage
from backend.services.zaehlerstaende import (
    finde_reihen_brueche,
    lade_zaehler_investitionen,
    lade_zaehler_verlaeufe,
    zaehler_einheit,
)

from .kategorien import CheckErgebnis, CheckKategorie, CheckSeverity, LINK_DATENQUELLEN

#: Wie viele Brüche je Gerät namentlich genannt werden, bevor gezählt wird.
#: Drei reichen, um das Muster zu erkennen; eine lange Liste hilft niemandem.
MAX_GENANNTE_BRUECHE = 3


class ZaehlerChecks:
    """Prüfungen für *Sonstiges*-Geräte der Kategorie ``zaehler`` (#377)."""

    async def _check_zaehlerstaende(self, anlage: Anlage) -> list[CheckErgebnis]:
        """Quelle, Reihenbruch und Inaktiv-Falle je Verbrauchszähler.

        **Ein Lauf, drei Aussagen** — sie teilen sich die teure Arbeit: die
        Punktreihe je Gerät wird einmal geladen und dreimal befragt.

        Die Reihe kommt über `lade_zaehler_verlaeufe`, also über **denselben**
        Weg wie die vier Anzeigen (`lade_zaehlerstaende` benutzt ihn seit D3
        ebenfalls). Eine eigene Abfrage hier wäre eine zweite Lesart derselben
        Daten — die N-259-Klasse.

        ⚠ **`nur_aktive=False`-Äquivalent, mit Absicht:** geladen werden die
        Zähler **ohne** Zeitfenster-Filter. Ein stillgelegter Zähler soll seinen
        Bruch weiterhin erklärt bekommen — er steht ja weiter in den
        historischen Sichten, und der Bruch liegt oft genau am Wechsel. Die
        `aktiv=False`-Prüfung braucht ihn ohnehin.
        """
        ergebnisse: list[CheckErgebnis] = []
        kat = CheckKategorie.ZAEHLERSTAND_REIHE

        zaehler = await lade_zaehler_investitionen(self.db, anlage.id)
        if not zaehler:
            return []  # Kein Verbrauchszähler eingerichtet ⇒ kein Befund.

        verlaeufe = await lade_zaehler_verlaeufe(
            self.db, anlage.id, [inv.id for inv in zaehler], bis=datetime.now(),
        )

        for inv in zaehler:
            name = inv.bezeichnung or f"Zähler {inv.id}"
            einheit = zaehler_einheit(inv)
            punkte = verlaeufe.get(inv.id) or []
            _start = len(ergebnisse)

            ergebnisse.extend(self._zaehler_inaktiv_hinweis(inv, name, punkte, kat))
            ergebnisse.extend(self._zaehler_quelle(inv, name, punkte, kat))
            ergebnisse.extend(self._zaehler_reihenbruch(name, einheit, punkte, kat))

            # Wie in `_check_investitionen`: alle Befunde dieses Geräts ihm
            # zuordnen, damit der Komponenten-Hub sie filtern kann (IA-V4 #243).
            for _e in ergebnisse[_start:]:
                _e.investition_id = inv.id

        return ergebnisse

    # ─── 1. Kommt überhaupt ein Stand an? ────────────────────────────────

    def _zaehler_quelle(self, inv, name: str, punkte: list, kat) -> list[CheckErgebnis]:
        """Ohne einen einzigen Stand zeigt das Gerät überall „—".

        **Datensignal, nicht Konfiguration** — s. Modul-Docstring Punkt 1.
        Ein einziger Punkt genügt als Beleg, dass der Weg trägt; ob er reicht,
        um eine Differenz zu bilden, sagt die Anzeige selbst (P4:
        `anfang_vollstaendig`).
        """
        if punkte:
            return [CheckErgebnis(
                kategorie=kat, schwere=CheckSeverity.OK,
                meldung=f"{name}: {len(punkte)} Zählerstand-Ablesung(en) erfasst",
            )]

        # `aktiv=False` hat seinen eigenen, genaueren Hinweis — hier nicht
        # zusätzlich „keine Quelle" melden, das wäre zweimal dieselbe Nachricht
        # mit zwei verschiedenen Ursachen.
        if inv.aktiv is False:
            return []

        return [CheckErgebnis(
            kategorie=kat, schwere=CheckSeverity.WARNING,
            meldung=f"{name}: kein Zählerstand erfasst",
            details=(
                "Für diesen Zähler liegt kein einziger Stand vor — weder aus "
                "einem Sensor noch von Hand. In Cockpit, Komponenten und den "
                "Tabellen steht deshalb überall „—“. "
                "Zwei Wege führen heraus, beide sind gleichwertig: einen Sensor "
                "unter Einstellungen → Datenquellen zuordnen (dann schreibt eedc "
                "den Stand stündlich mit), oder den Zählerstand beim "
                "Monatsabschluss ablesen und im Feld „Zählerstand“ eintragen. "
                "Für einen Gas- oder Wasserzähler ohne Fernauslesung ist der "
                "zweite Weg der vorgesehene."
            ),
            link=LINK_DATENQUELLEN,
        )]

    # ─── 2. Läuft die Reihe rückwärts? ───────────────────────────────────

    def _zaehler_reihenbruch(
        self, name: str, einheit: str, punkte: list, kat,
    ) -> list[CheckErgebnis]:
        """Ein gefallener Stand — erklärt, nicht geheilt (Konzept #377 §4).

        ⚑ **Der F-58-Übergang steht ausdrücklich im Text.** Bis v4.0.24 trug
        der Snapshot HAs `sum` (eine Menge), seit v4.0.25 den `state` (den
        Stand). Wo die Summe größer war als der Stand, fällt die Reihe an
        **genau dieser einen Stelle** — bei jedem Bestandsanwender, der einen
        Sensor zugeordnet hat, und ohne dass er etwas falsch gemacht hätte.
        Diese Meldung ohne den Hinweis auszuliefern hieße, der Zielgruppe des
        letzten Releases einen Fehler zuzuschreiben, den wir selbst erzeugt
        haben — dieselbe Klasse wie F-60 (v4.0.24).
        """
        brueche = finde_reihen_brueche(punkte)
        if not brueche:
            return []

        einheit_suffix = f" {einheit}" if einheit else ""
        genannt = [
            f"{b.zeitpunkt.strftime('%d.%m.%Y')}: "
            f"{b.stand_vorher:.3f}{einheit_suffix} → {b.stand_nachher:.3f}{einheit_suffix}"
            for b in brueche[:MAX_GENANNTE_BRUECHE]
        ]
        liste = "; ".join(genannt)
        if len(brueche) > MAX_GENANNTE_BRUECHE:
            liste += f" (+{len(brueche) - MAX_GENANNTE_BRUECHE} weitere)"

        return [CheckErgebnis(
            kategorie=kat, schwere=CheckSeverity.WARNING,
            meldung=(
                f"{name}: der Stand ist {len(brueche)}-mal gefallen — "
                "die Reihe hat einen Bruch"
            ),
            details=(
                f"Betroffen: {liste}. "
                "Ein Zählerstand läuft nicht rückwärts. Für den Zeitraum über "
                "eine solche Stelle hinweg zeigt eedc deshalb keine Differenz — "
                "eine negative Menge auszuweisen wäre die schlechtere Antwort. "
                "Drei Ursachen kommen in Frage: "
                "(1) **Zähler gewechselt.** Dann ist der Weg: am alten Gerät ein "
                "Stilllegungsdatum setzen und ein neues anlegen — den Haken "
                "„aktiv“ dabei stehen lassen, sonst verschwindet die alte "
                "Historie aus allen Auswertungen. Der Verbrauch über den Wechsel "
                "ist danach die Summe beider Differenzen. "
                "(2) **Sensor getauscht oder Zählerstand von Hand korrigiert**, "
                "und der neue Wert liegt unter dem alten. "
                "(3) **Der Umstieg auf eedc 4.0.25**: bis dahin schrieb eedc für "
                "Zähler die Verbrauchssumme von Home Assistant mit statt des "
                "Zählerstands. Lag die Summe höher, fällt die Reihe an genau "
                "einer Stelle — an der Umstellung, einmalig, und es ist nichts "
                "kaputt. Über Einstellungen → Daten → „Tag neu berechnen“ zieht "
                "eedc die Historie nach, soweit Home Assistant sie noch hat."
            ),
            link="/einstellungen/komponenten",
        )]

    # ─── 3. Auf inaktiv gesetzt, obwohl Ablesungen da sind ───────────────

    def _zaehler_inaktiv_hinweis(
        self, inv, name: str, punkte: list, kat,
    ) -> list[CheckErgebnis]:
        """`aktiv=False` blendet die Ablesungen auch **rückwirkend** aus.

        Der v4.0.23-CHANGELOG warnt davor in Prosa, die Anwendung schwieg. Der
        Weg für einen Zählerwechsel ist das **Stilllegungsdatum**; wer statt
        dessen den Haken entfernt, hat laut `Investition.ist_aktiv_im_zeitraum`
        „wie gelöscht“ gewählt — und sieht seine Historie nirgends mehr.

        ⚠ **Nur für Zähler, und nur mit vorhandenen Ablesungen.** Bei anderen
        Gerätetypen ist `aktiv=False` eine bewusst gewählte Einstellung; ein
        allgemeiner Hinweis darauf wäre Nörgeln an einer Entscheidung, die der
        Anwender getroffen hat. Hier trägt ihn die Verwechslungsgefahr mit dem
        dokumentierten Wechsel-Weg — und ohne Ablesungen gibt es nichts zu
        verlieren, dann schweigt der Hinweis.
        """
        if inv.aktiv is not False or not punkte:
            return []

        return [CheckErgebnis(
            kategorie=kat, schwere=CheckSeverity.INFO,
            meldung=f"{name}: auf „nicht aktiv“ gesetzt — {len(punkte)} Ablesung(en) ausgeblendet",
            details=(
                "Der Haken „aktiv“ ist entfernt. In eedc heißt das „wie "
                "gelöscht“: die Ablesungen dieses Zählers erscheinen nirgends "
                "mehr — **auch nicht für die Vergangenheit**, in der er gemessen "
                "hat. "
                "War das ein Zählerwechsel, ist der vorgesehene Weg ein anderer: "
                "am alten Gerät ein **Stilllegungsdatum** setzen und „aktiv“ "
                "stehen lassen. Dann bleibt seine Historie in jedem Zeitraum "
                "erhalten, in den er hineingemessen hat, und der neue Zähler "
                "läuft als eigenes Gerät daneben weiter. "
                "Ist das Gerät dagegen bewusst stillgelegt und soll auch "
                "historisch verschwinden, ist alles in Ordnung — dann bleibt "
                "dieser Hinweis stehen, ohne dass etwas zu tun ist."
            ),
            link=f"/einstellungen/komponenten?bearbeiten={inv.id}",
        )]
