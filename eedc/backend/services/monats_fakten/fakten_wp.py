"""Monats-Fakten — die Feldgruppe Wärmepumpe (`WpFakten`): Strom, Wärme, Funktionen, Modus-Split, Deckung und die
Deckungs-/Bauart-Properties (Konzept §3, KONZEPT-WAERME-KLIMA).
"""
# Reiner Umzug aus `services/monats_fakten.py` (19.09.2026, Vorlage 10 des Refactorings grosser Dateien):
# Code 1:1 uebernommen, kein Verhaltenswechsel. Die Fassade `__init__.py` exportiert die Namen weiter, die
# Aufrufer und Tests bisher aus dem Modul importierten (ADR-002/P10 bleibt: die Schicht ist das Paket).

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass(frozen=True)
class WpGeraetFakten:
    """Die drei Mengen EINES Geräts im Monat, aus denen seine Ersparnis-Zeile entsteht (N-605/N-609).

    Aus demselben ``ImdTypBeitrag``, der die Summen von ``WpFakten`` bildet — Strom nach K3, Wärme nach D1
    (Innengeräte eingeschlossen), Kühlanteil nach der Betriebsart-Weiche (gemessen oder abgeleitet), dazu der
    nachgetragene Modus-Split eines Monats ohne Abschluss (F-52). ⚠ ``strom_kuehlen_kwh`` ist eine **Teilmenge** von
    ``strom_kwh``, kein Summand.
    """

    strom_kwh: float = 0.0
    waerme_kwh: float = 0.0
    strom_kuehlen_kwh: float = 0.0


@dataclass(frozen=True)
class WpFakten:
    """Wärmepumpe des Monats — kanonisch gelesen (D1, ``imd_typ_beitrag``)."""

    strom_kwh: float = 0.0
    waerme_kwh: float = 0.0
    #: **Teilmengen** von ``strom_kwh``/``waerme_kwh`` — nur die Geräte, die laut
    #: Pflege eine Heizung **ersetzt** haben (N-256). Sie sind die Grundmenge
    #: jedes **fossilen Vergleichs**: was hätte diese Wärme mit Gas/Öl gekostet,
    #: und wieviel CO₂ hätte sie verursacht?
    #:
    #: ⭐ **Warum zwei Summen und keine Aufteilung je Gerät.** Eine Split-Klima\
    #: anlage neben einer Wärmepumpe ist der Normalfall, nicht die Ausnahme —
    #: und sie trägt typischerweise „nichts ersetzt". Ohne diese Trennung wurde
    #: **ihre** Wärme als vermiedenes Gas gebucht: eine Ersparnis, die es nie
    #: gab. Eine Zuordnung je Gerät wäre der falsche Weg dorthin (Entscheid
    #: 27.08.: die gemeinsame Kennzahl wird nicht umgebaut) und auch gar nicht
    #: nötig — für eine **Menge** genügt die Teilsumme. Kennzahlen trennen wir
    #: je Bauart, Mengen summieren wir (Konzept Wärme/Klima, E1).
    #:
    #: ⚠ **Nie zu ``strom_kwh``/``waerme_kwh`` addieren** — dieselbe Zusicherung
    #: wie bei ``modus_strom_*`` weiter unten. Die Anlage verbraucht und liefert
    #: weiterhin die vollen Mengen; nur der Vergleich hat eine kleinere Basis.
    strom_mit_ersatz_kwh: float = 0.0
    waerme_mit_ersatz_kwh: float = 0.0
    heizung_kwh: float = 0.0
    warmwasser_kwh: float = 0.0
    strom_heizen_kwh: float = 0.0
    strom_warmwasser_kwh: float = 0.0
    #: **N-479 — „gemessen" je Funktion.** Hat mindestens ein aktives Gerät des
    #: Zeitraums die Größe gemessen, auch wenn dabei 0 herauskam? Die Summen
    #: oben können das nicht sagen: Eine gemessene Null und ein fehlender Zähler
    #: tragen beide 0.0 bei. Erst damit dürfen Monat und Jahr denselben
    #: Zeitraum-Grund führen wie der Tag (``null_ist_gemessen``) — vorher
    #: meldeten sie im Sommer „kein Wärmemengenzähler zugeordnet", obwohl beide
    #: Zähler hingen (simon42 T89667, dietmar1968, 16.09.2026).
    heizung_gemessen: bool = False
    warmwasser_gemessen: bool = False
    strom_heizen_gemessen: bool = False
    strom_warmwasser_gemessen: bool = False
    #: True, sobald **eine** aktive WP getrennte Strommessung führt.
    hat_split: bool = False
    #: N-391: True, sobald **eine** aktive WP ihre Wärme mit EINEM gemeinsamen
    #: Wärmemengenzähler misst (Feld ``waerme_kwh``). Die MENGE steht in
    #: ``waerme_kwh`` oben; dies ist ihre Herkunft — und die entscheidet, ob es
    #: eine Arbeitszahl **je Funktion** geben kann
    #: ({@link backend.core.berechnungen.waermepumpe_kennzahl.arbeitszahl_je_funktion}).
    waerme_ist_gesamt: bool = False

    # ── Modus-Split (#263 K-2) ───────────────────────────────────────────────
    #: **Teilmengen** von ``strom_kwh``, keine Summanden — nie addieren
    #: (Präzedenz: ``ladung_pv_kwh`` bei der Wallbox, Konzept §3.1).
    modus_strom_heizen_kwh: float = 0.0
    modus_strom_kuehlen_kwh: float = 0.0
    #: N-336 (27.08.): Nur aus dem **abgeleiteten** Split — für Warmwasser gibt
    #: es keinen Betriebsart-Zähler (Begründung bei ``MESSBARE_MODI``). Die
    #: Gegenrichtung zu ``modus_strom_lueften_kwh`` darunter.
    #: ⛔ Zählt **nicht** in {@link modus_strom_funktionsfremd_kwh}: Warmwasser
    #: hat eine bewertete Nutzenergie, die im Zähler desselben Quotienten steht.
    modus_strom_warmwasser_kwh: float = 0.0
    #: E4 (Konzept §2.3, gebaut 26.08.): *erfassbar, aber keine bewertete
    #: Funktion.* Nur aus **gemessenen** Betriebsart-Zählern — der aus dem
    #: Modus-Signal abgeleitete Split kann sie nicht (``AUFGETEILTE_MODI``,
    #: D11) und lässt sie bei 0. **Das ist die Aussage, keine Lücke.**
    #: Vorher fielen sie stumm unter „nicht aufgeteilt", obwohl die Registry
    #: die Felder anbietet.
    modus_strom_lueften_kwh: float = 0.0
    modus_strom_entfeuchten_kwh: float = 0.0
    #: **SOLL-§9-E7 / Ergänzung (Option A, 12.09.2026): der Teil des
    #: funktionsfremden Stroms, der vom Nenner abgezogen werden DARF.**
    #:
    #: ⛔ **Bewusst ein Feld und keine Property neben**
    #: {@link modus_strom_funktionsfremd_kwh}. Die Regel *„abgezogen wird nur,
    #: was im Nenner steht"* hängt an ``getrennte_strommessung`` — also an
    #: **einem Gerät**. Hier oben ist ``hat_split`` bereits ein ``any(...)``
    #: über alle Wärmepumpen der Anlage; eine Property könnte die Frage für
    #: eine Mischanlage (F5-Gerät neben nicht-F5-Gerät) nicht mehr richtig
    #: beantworten. Die Entscheidung fällt deshalb je Zeile in
    #: {@link imd_monatsaggregat.imd_typ_beitrag} und wird hierher **summiert**.
    #:
    #: ⚠ {@link modus_strom_funktionsfremd_kwh} bleibt daneben stehen und
    #: bleibt die **Menge** — für Anzeige, Balken und Restmenge (K1). Wer einen
    #: **Nenner** bildet, liest dieses Feld.
    modus_strom_funktionsfremd_abzug_kwh: float = 0.0
    #: W-5 (SOLL §4.1): abgegebene **Kälte**menge im Kühlbetrieb — der Zähler
    #: der Arbeitszahl Kühlen. **Nur gemessen**: einen Weg, sie abzuleiten, gibt
    #: es nicht, und eine geschätzte Kältemenge wäre eine Zahl, die genauer
    #: aussieht als sie ist.
    nutzenergie_kuehlen_kwh: float = 0.0
    #: **R-C (WK-16f, N-398):** die abgegebene Nutzenergie im **Lüft**- bzw.
    #: **Entfeuchtungs**betrieb — dieselbe Familie wie die Kältemenge darüber,
    #: nur ohne Kennzahl. **E4 bleibt:** Sie erscheinen als *Menge* neben
    #: ``modus_strom_lueften_kwh``/``…_entfeuchten_kwh``, nie als Quotient.
    #: Bis zum 14.09.2026 hatte kein Leser diese zwei Registry-Felder.
    nutzenergie_lueften_kwh: float = 0.0
    nutzenergie_entfeuchten_kwh: float = 0.0
    #: Stunden mit gültigem Modus-Signal — das Qualitätsmaß neben den Mengen.
    modus_abdeckung_h: float = 0.0
    #: #263 — die Aufteilung ist **gemessen** (Betriebsart-Zähler) statt aus
    #: dem Betriebsmodus abgeleitet. Ein Zähler hat keine „Stunden mit Signal",
    #: deshalb kann ``modus_abdeckung_h`` dabei 0 sein, ohne dass etwas fehlt.
    modus_gemessen: bool = False
    #: Gesamtstrom **nur der Geräte mit Modus-Split** — die Bezugsgröße für
    #: {@link modus_nicht_aufgeteilt_kwh}. Auf Anlagenebene ist `strom_kwh` der
    #: falsche Bezug: er trägt auch Wärmepumpen ohne Modus-Sensor.
    modus_strom_bezug_kwh: float = 0.0
    #: **WK-16d/K5 — der Rest der SUMMANDEN-Aufteilung** (Heizen/Warmwasser),
    #: summiert über die Geräte: was ein Gesamtzähler **mehr** misst als seine
    #: Achsen zusammen. Standby, Steuerung, Umwälzpumpen — dietmar1968s
    #: „Systemverbrauch", bei ihm 145 von 2193 kWh im Jahr.
    #:
    #: ⛔ **Der ZWEITE Rest, und er ist nicht {@link
    #: modus_nicht_aufgeteilt_kwh}.** Dieselbe Menge wird auf **zwei** Weisen
    #: aufgeteilt, und jede lässt ihren eigenen Rest übrig:
    #:
    #: | Aufteilung | Rest | Herkunft des Rests |
    #: | --- | --- | --- |
    #: | Summanden (Strom Heizen + Strom Warmwasser) | **dieses Feld** | der Gesamtzähler misst mehr als die Achsen |
    #: | Teilmengen (Betriebsart bzw. Modus-Split) | ``modus_nicht_aufgeteilt_kwh`` | Stunden ohne Modus-Signal, nicht gemessene Betriebsarten |
    #:
    #: Sie zu addieren wäre Doppelzählung; sie zu verwechseln hieße, in einer
    #: Sicht den falschen Rest zu zeigen. Beide sind ≥ 0 und beide sind K5.
    strom_nicht_aufgeteilt_kwh: float = 0.0
    #: Anteil von ``waerme_kwh``, der aus ``Strom × JAZ`` stammt statt aus
    #: einem Wärmemengenzähler. **Trägt die JAZ-Sperre aus Konzept §3.5** —
    #: siehe {@link jaz_belastbar}.
    waerme_abgeleitet_kwh: float = 0.0

    # ── R2/Gerät: dieselbe Abgrenzung im Zähler wie im Nenner? ──────────────
    #: **Welche** Wärmepumpen des Monats stehen mit ihrem Strom im **Nenner**
    #: der Gesamtzahl — als Menge von ``Investition.id``.
    #:
    #: ⭐ **Gezählt wird NACH dem Abzug des funktionsfremden Stroms** (N-441,
    #: Fall J): ``arbeitszahl`` zieht Kühl-, Lüftungs- und Entfeuchtungsstrom
    #: vom Nenner ab (W-14/E4). Ein Zweitgerät, das **nur** kühlt, steht damit
    #: gar nicht im Nenner — es darf die Gesamtzahl auch nicht sperren. Gemessen:
    #: 2400 ÷ 800 = 3,0 existiert, wurde aber mit „nicht alle Geräte melden
    #: Wärme" unterdrückt. Die Bauart-Zähler {@link geraete_luft_luft} /
    #: {@link geraete_luft_wasser} bleiben bewusst bei „Strom > 0": sie zählen
    #: Stammdaten, nicht den Nenner.
    geraete_mit_strom: frozenset[int] = frozenset()
    #: … und **welche** steuern **Wärme** bei? Ist das eine echte Teilmenge,
    #: mischt der Block den Strom mehrerer Geräte mit der Wärme von weniger
    #: ({@link waerme_deckt_nicht_alle_geraete}); liegt ein Gerät **außerhalb**,
    #: stammen Zähler und Nenner von verschiedenen Geräten
    #: ({@link geraete_verschieden}).
    #:
    #: ⛔ **Mengen, keine Anzahlen** (N-441): „ein Gerät hier, ein Gerät dort"
    #: ergab ``1 == 1`` und galt als deckungsgleich — der Anlassfall (Wärme von
    #: A, Strom von B) lieferte 3,0 **ohne jeden Grund**.
    geraete_mit_waerme: frozenset[int] = frozenset()

    # ── R2/Bauart: dieselbe Geräteart im Zähler wie im Nenner? ──────────────
    #: Wie viele der stromtragenden Geräte sind **Split-Klimaanlagen**
    #: (`wp_art="luft_luft"`) …
    geraete_luft_luft: int = 0
    #: … und wie viele **klassische Wärmepumpen**? Beide > 0 heißt: der Block
    #: trägt zwei Bauarten, und dann gibt es keine gemeinsame Kennzahl
    #: ({@link bauarten_gemischt}).
    geraete_luft_wasser: int = 0

    #: **R2/W-7 + R2/F12** — die vom Anwender gemeldete Abgrenzungs-Störung:
    #: ``"fremdstrom"`` (Heizstab-Strom auf dem WP-Zähler, seine Wärme fehlt),
    #: ``"fremdwaerme"`` (bivalent: zweiter Erzeuger am selben Kreis) oder
    #: ``None``.
    #:
    #: ⭐ **Warum eine Anwender-Angabe und keine Erkennung.** Von den Lagen des
    #: SOLL §4.2/§5 erkennt eedc **zwei** aus eigener Kenntnis
    #: ({@link waerme_deckt_nicht_alle_geraete} aus den Daten,
    #: {@link bauarten_gemischt} aus den Stammdaten). Ob ein Heizstab auf demselben
    #: Zähler liegt oder ein Gaskessel denselben Kreis speist, steht in **keiner**
    #: Messreihe — es gibt keinen Wert, aus dem es folgen könnte.
    #:
    #: ⛔ **`None` heißt „keine bekannte Abweichung", nicht „geprüft".**
    abgrenzung_stoerung: Optional[str] = None

    # ── R2 JE FUNKTION (10.09.2026, SOLL §3.2b) ────────────────────────────
    #: **Welche** Geräte den **Strom** (``e``) bzw. die **Nutzenergie** (``q``)
    #: je Funktion beisteuern — Mengen von ``Investition.id``. Grundlage von
    #: {@link funktion_sauber_abgegrenzt} und {@link deckung_je_funktion}.
    #:
    #: ⛔ **Mengen statt Anzahlen (N-441, 12.09.2026).** Bis dahin standen hier
    #: ``int``, und ``(1, 1)`` hieß „deckt sich" — auch dann, wenn der Strom von
    #: Gerät A und die Wärme von Gerät B kam. Die Regel prüft seither
    #: **Identität** (``e == q``), nicht Gleichmächtigkeit.
    geraete_e_heizen: frozenset[int] = frozenset()
    geraete_q_heizen: frozenset[int] = frozenset()
    geraete_e_warmwasser: frozenset[int] = frozenset()
    geraete_q_warmwasser: frozenset[int] = frozenset()
    geraete_e_kuehlen: frozenset[int] = frozenset()
    geraete_q_kuehlen: frozenset[int] = frozenset()
    #: **N-609 — die Mengen je Gerät**, gekeyt nach ``Investition.id``. ⭐ Die WP-Ersparnis einer Anlage ist in jeder
    #: Sicht die Σ der Gerätezeilen je Monat (N-605): zwei Wärmepumpen haben keine gemeinsame Referenz-WP, ihre
    #: Parameter (Altheizung, Wirkungsgrad, Zusatzkosten) gelten je Gerät. Bis 04.10.2026 rechneten Übersicht und
    #: Komponenten-Zeitreihe ein Aggregat mit dem Parametersatz der ERSTEN Wärmepumpe (gemessen 50 statt 110 €).
    #: Die Ersparnis selbst rechnet ``services/wp_wirtschaftlichkeit.py::wp_ersparnis_monat`` — hier stehen nur Mengen.
    je_geraet: dict[int, WpGeraetFakten] = field(default_factory=dict)

    def funktion_sauber_abgegrenzt(self, funktion: str) -> bool:
        """Tragen dieselben Geräte Zähler **und** Nenner dieser Funktion? (**R2**)

        **SOLL §3.2b: die Trennlinie ist die Abgrenzung, nicht die Bauart.** Ein
        Block darf als Ganzes gemischt sein und trotzdem einzelne Funktionen
        sauber abgrenzen — dann erscheint deren Kennzahl.

        ⭐ **Der belegte Fall (dietmar1968, Fixture A5):** Wärmepumpe mit
        getrennter Strommessung neben einer Split-Klimaanlage. Die Klimaanlage
        trägt ihre 200 kWh in ``stromverbrauch_kwh`` — das gehört zu **keiner**
        Funktion und steht in keinem der beiden Quotienten. Heizen und
        Warmwasser sind damit reine Wärmepumpen-Größen; ihre Arbeitszahlen
        (3,0 und 2,5) waren bis hierher gesperrt, obwohl sie stimmen.

        ⛔ **Beidseitig, und das ist nicht verhandelbar.** Eine einseitige Regel
        („jedes Gerät mit Strom liefert auch Wärme") fängt nur den **Nenner**.
        Der Zähler kippt genauso, und zwar in die teurere Richtung:

        * ``heizenergie_kwh`` trägt nur ``!brauchwasser``
          (``field_definitions/registry.py::INVESTITION_FELDER``) — eine Split-Klimaanlage **darf**
          Heizwärme melden. Tut sie es ohne Heizstrom, wäre die Heiz-Arbeitszahl
          zu **hoch**: an der A8-Bauform 4,25 statt 3,75.
        * ``strom_warmwasser_kwh`` wird **ungefiltert** gelesen
          (``imd_monatsaggregat.py:276``, mit ausdrücklicher Begründung), und
          bis zum 22.08.2026 wurde das Feld einer Klimaanlage mit getrennter
          Strommessung angeboten. Altbestand ohne Wärme daneben ergäbe eine zu
          **niedrige** Zahl.

        ⚠ **Eine zu Unrecht gezeigte Kennzahl ist teurer als eine zu Unrecht
        gesperrte** — deshalb Gleichheit und nicht „≥".

        ⭐ **Das löst zugleich einen Fehler, der heute schon falsche Zahlen
        zeigt:** Eine **Brauchwasser-Wärmepumpe** neben einer Wärmepumpe mit
        getrennter Strommessung fällt in keine der bisherigen Sperren — sie
        zählt als Luft-Wasser-Gerät und meldet Wärme, also greifen weder
        {@link bauarten_gemischt} noch {@link waerme_deckt_nicht_alle_geraete}.
        Ihre Warmwasser-Wärme landet im Zähler, ihr Strom (ungeteilt) in
        keinem Nenner ⇒ die Warmwasser-Arbeitszahl war zu hoch, **ohne Grund
        daneben**. 8ear hat genau diese Konstellation.

        ⛔ **Null Geräte auf beiden Seiten ist NICHT „sauber".** Dann gibt es
        die Funktion in diesem Monat gar nicht; die Kennzahl entsteht ohnehin
        nicht, und „sauber" zu melden hieße, eine Abwesenheit für eine
        Zusicherung auszugeben.
        """
        return self.deckung_je_funktion(funktion) is True

    def deckung_je_funktion(self, funktion: str) -> Optional[bool]:
        """Deckt sich der Geräte-Kreis von Zähler und Nenner dieser Funktion?

        ``True`` = ja · ``False`` = nein · ``None`` = **die Frage stellt sich
        nicht**, und das ist der wichtigste der drei Werte.

        ⚠ **Zwei Lagen ergeben ``None``, und in beiden wäre eine Sperre die
        schlechtere Auskunft:**

        * ``q`` leer, ``e`` leer — die Funktion gab es in diesem Monat nicht.
          Ein Sommermonat ohne Heizbetrieb ist nicht „unsauber abgegrenzt".
        * ``q`` leer, ``e`` nicht — Strom ja, Wärme nein. Dafür hat
          ``arbeitszahl`` den genaueren Satz („kein Wärmemengenzähler
          zugeordnet"); ihn gegen einen allgemeinen Abgrenzungs-Grund zu
          tauschen verstieße gegen S3.

        ⛔ ``e`` leer bei nicht leerem ``q`` ist dagegen **False**: Wärme ohne
        den Strom derselben Funktion. Für den Monat selbst folgt daraus nichts
        (ohne Nenner gibt es keinen Quotienten) — **für das Jahr sehr wohl**:
        Dort wandert die Wärme dieses Monats in die Summe, sein fehlender Strom
        nicht. Gemessen an einem Zweimonats-Fall: **3,75 statt 3,0.**

        ⛔ **Verglichen werden GERÄTE, nicht Anzahlen (N-441, 12.09.2026).**
        Bis dahin standen hier zwei ``int``, und „ein Gerät auf jeder Seite"
        hieß deckungsgleich — auch dann, wenn es zwei **verschiedene** Geräte
        waren. Der Anlassfall (Wärme 2400 kWh von A, Heizstrom 800 kWh von B)
        zeigte **3,0 ohne jeden Grund**.
        """
        # Die Regel steht seit Bauschnitt 6 im Layer — der Tag ruft sie auch.
        from backend.core.berechnungen.waermepumpe_kennzahl import (
            deckung_aus_geraeten,
        )

        e, q = self._funktions_paar(funktion)
        return deckung_aus_geraeten(e, q)

    def _funktions_paar(
        self, funktion: str,
    ) -> tuple[frozenset[int], frozenset[int]]:
        return {
            "heizen": (self.geraete_e_heizen, self.geraete_q_heizen),
            "warmwasser": (self.geraete_e_warmwasser, self.geraete_q_warmwasser),
            "kuehlen": (self.geraete_e_kuehlen, self.geraete_q_kuehlen),
        }[funktion]

    @property
    def waerme_deckt_nicht_alle_geraete(self) -> bool:
        """Trägt der Block Strom von Geräten, deren Wärme fehlt? (**R2**)

        SOLL §4.2 Fall 1: *„Wenn der Zähler mehr enthält als das Gerät."* Die
        anlagenweite Arbeitszahl ist dann systematisch zu niedrig — im Nenner
        steht der Strom von n Geräten, im Zähler die Wärme von weniger.

        **Melder dietmar1968**, sein eigener Screenshot nennt die Ursache:
        *„Aggregiert aus: Wärmepumpe · Klimaanlage"* bei einer JAZ von 0,92.
        ⚠ Ob genau diese Vermischung **seine** Zahl erzeugt, ist damit **nicht**
        bewiesen — der Heizstab ist die sparsamere Erklärung (SOLL §2.2.1/H-B,
        beides ungemessen, §7/A2). Die Regel steht unabhängig davon: Ein
        Quotient aus zwei verschieden abgegrenzten Mengen ist keine Kennzahl,
        egal welche Erklärung im Einzelfall zutrifft.

        ⛔ **Hier stand bis zum 28.08.2026: „Von den vier Lagen des §4.2 ist das
        die einzige, die eedc aus den Daten selbst erkennt."** Das gilt nicht
        mehr — {@link bauarten_gemischt} erkennt eine zweite, und zwar aus den
        **Stammdaten** statt aus einer Messreihe. Heizstab am Zähler und
        bivalenter Zweiterzeuger bleiben von außen unsichtbar und brauchen die
        Angabe des Anwenders (`abgrenzung_stoerung`); der Zeitraum-Versatz ist
        nur dort erkennbar, wo die Herkunft je Größe bekannt ist.

        ⭐ **Zwei Präzisierungen aus N-441 (12.09.2026), beide gemessen:**

        * **Echte Teilmenge statt „weniger".** Verglichen werden die **Mengen**
          der Geräte, nicht ihre Anzahlen. Zwei Geräte, von denen jedes genau
          eine Seite trägt, sind gleich viele — und trotzdem verschiedene; diese
          Lage trägt jetzt {@link geraete_verschieden}.
        * **``w = ∅`` ist keine Geräte-Lage mehr.** Ein Monat ganz **ohne**
          Wärme sagt nichts über Geräte aus; dafür hat ``arbeitszahl`` den
          genaueren Satz „kein Wärmemengenzähler zugeordnet" (er gewinnt ohnehin,
          weil ``q ≤ 0`` **vor** der Abgrenzung geprüft wird). Sichtbar wird der
          Unterschied erst im **Jahr**, und dort heilt er eine Übersperre: Eine
          Anlage mit EINEM Gerät, das im Juli 0 kWh Wärme meldet (gemessene
          Sommer-Null) und 50 kWh Standby-Strom zieht, verlor bis hierher ihre
          **Gesamt**-Arbeitszahl mit dem Satz „nicht alle Geräte melden Wärme" —
          während direkt daneben die Heiz-Arbeitszahl 2,77 stand (Verstoß gegen
          SOLL §3.3/**S1**).
        """
        return bool(self.geraete_mit_waerme) and (
            self.geraete_mit_waerme < self.geraete_mit_strom
        )

    @property
    def geraete_verschieden(self) -> bool:
        """Steuert ein Gerät Wärme bei, dessen Strom **nicht** im Nenner steht?

        ⭐ **Die Gegenrichtung zu {@link waerme_deckt_nicht_alle_geraete}**
        (N-441, SOLL §3.2b/**R2**: *„Gezählt wird BEIDSEITIG, und das ist nicht
        verhandelbar"*). Jene Property fängt nur den Nenner (Strom von mehr
        Geräten als Wärme); der **Zähler** kippt genauso, und zwar in die
        teurere Richtung — dort erscheint eine zu **hohe** Zahl statt gar keiner.

        **Gemessen, beides ausgeliefert (v4.0.44):**

        * Wärme 2400 kWh von Gerät A, Heizstrom 800 kWh von Gerät B ⇒ **3,0**
          im Cockpit (Jahr **und** Monat), an die Community als *belastbar*.
        * Gerät A vollständig (2400/800), Gerät B **nur** 600 kWh Wärme ⇒
          **3,75** statt 3,0 — mit ``w = {A, B} ⊋ s = {A}`` sah die einseitige
          Regel nichts.

        ⛔ **Disjunkt zur Teilmengen-Lage, und das ist Absicht.** ``w ⊊ s``
        trägt den gerichteten Satz („im Nenner der Strom von allen, im Zähler
        die Wärme von weniger", Handbuch §4) mit seinem Handgriff; alles andere
        Ungleiche trägt den neutralen. Zusammen decken beide genau
        ``s ≠ ∅ ∧ w ≠ ∅ ∧ w ≠ s`` ab.
        """
        return (
            bool(self.geraete_mit_strom)
            and bool(self.geraete_mit_waerme)
            and not (self.geraete_mit_waerme <= self.geraete_mit_strom)
        )

    @property
    def bauarten_gemischt(self) -> bool:
        """Trägt der Block **zwei Bauarten** in einer Zahl? (**R2**, SOLL §5)

        *„Geräte verschiedener Bauart werden nicht zu einer Kennzahl
        zusammengefasst. Eine Luft-Wasser-WP und eine Split-Klimaanlage haben
        verschiedene Funktionen, verschiedene Nutzenergie und verschiedene
        Vergleichsmaßstäbe. Mengen dürfen nebeneinander stehen, eine
        gemeinsame JAZ nicht."* — so steht es im Konzept, und bis zum
        28.08.2026 hielt sich der Code nicht daran.

        ⭐ **Die zweite Lage, die eedc aus den Daten selbst erkennt.** Bis
        hierher galt {@link waerme_deckt_nicht_alle_geraete} als *„die einzige"*
        — das stimmt seit dieser Eigenschaft nicht mehr, und der Unterschied ist
        keine Feinheit: Die Bauart steht in den **Stammdaten**, nicht in einer
        Messreihe. Sie ist deshalb auch dann bekannt, wenn noch gar nichts
        gemessen wurde.

        ⚠ **Warum das nicht dasselbe ist wie „nicht alle Geräte melden Wärme".**
        Beide treffen bei dietmar1968 zu, aber sie sagen Verschiedenes: Der
        allgemeinere Satz beschreibt einen **behebbaren** Zustand („ordne einen
        Wärmemengenzähler zu"). Eine Split-Klimaanlage hat bauartbedingt keinen
        — das Investitionsformular sagt dem Anwender ausdrücklich zu, es genüge
        der Stromverbrauchs-Sensor. Ihr Strom stünde damit **dauerhaft** im
        Nenner ohne Aussicht auf einen Zähler, und der Rat wäre einer ins Leere.
        Genau diese Klasse Fehlberatung hat ihn schon einmal getroffen
        (Forum #89667/87, behoben mit `ist_luft_luft_waermepumpe`).

        ⭐ **Und sie beantwortet eine Frage, die er selbst gestellt hat**
        (T89667 #201): *„Ist es nicht sinnvoller, die Luft-Wasser-Wärmepumpe
        von der Luft-Luft-Klimaanlage komplett zu trennen?"* Für die Kennzahl:
        ja, zwingend. Für die **Mengen** nicht — die Balken bleiben gemeinsam,
        sie nennen jetzt nur ihre Geräte (`komponenten_geraete`, auch im Tag).
        """
        return self.geraete_luft_luft > 0 and self.geraete_luft_wasser > 0

    @property
    def jaz_belastbar(self) -> bool:
        """Darf aus diesen Zahlen eine JAZ/COP gebildet werden? (Konzept §3.5)

        ``False``, sobald **irgendein** Teil der Wärme abgeleitet ist. Nicht
        „den abgeleiteten Teil abziehen": dann teilte man gemessene Wärme durch
        den **Gesamt**strom und bekäme eine zu kleine JAZ — falsch statt
        unbekannt. Die Kachel bleibt „—", bis ein Wärmemengenzähler da ist.
        """
        return self.waerme_abgeleitet_kwh <= 0

    @property
    def modus_nicht_aufgeteilt_kwh(self) -> float:
        """``Gesamt − Σ Teilmengen`` — Standby, Unbestimmt, und was nicht gemessen ist.

        **Wird nie gespeichert** (Konzept §3.1, Folge 2) und ist deshalb immer
        vollständig: für Altmonate, Ausfälle, Importe und manuelle Pflege
        gleichermaßen. Auf 0 geklemmt — die Invariante hält das schon im
        Schreibpfad, aber eine negative „Restmenge" wäre auf jeder Fläche
        Unsinn.

        ⚠ Bezug ist {@link modus_strom_bezug_kwh}, **nicht** ``strom_kwh``:
        anlagenweit trägt letzteres auch Wärmepumpen ohne Modus-Sensor, deren
        Verbrauch dann als „nicht aufgeteilt" der Klimaanlage erschiene
        (an einer Instanz gemessen: 96,4 statt 6,4 kWh).

        ⭐ **E4 (26.08.): Lüften und Entfeuchten werden abgezogen, sobald sie
        GEMESSEN sind.** Bis dahin nannte dieser Docstring sie ausdrücklich als
        Inhalt der Restmenge — richtig, solange es für sie keine eigene Zeile
        gab. Jetzt gilt beides nebeneinander, und genau das ist die Aussage:
        **Wer einen Lüftungs-Zähler zugeordnet hat, sieht seine Kilowattstunden
        als eigene Zeile; wer keinen hat, findet sie weiterhin hier.** Ohne den
        Abzug stünde dieselbe Menge zweimal — die Doppelzählungs-Klasse.
        """
        return max(
            0.0,
            self.modus_strom_bezug_kwh
            - self.modus_strom_heizen_kwh
            - self.modus_strom_kuehlen_kwh
            - self.modus_strom_warmwasser_kwh
            - self.modus_strom_lueften_kwh
            - self.modus_strom_entfeuchten_kwh,
        )

    @property
    def modus_strom_funktionsfremd_kwh(self) -> float:
        """Strom in Funktionen **ohne bewertete Nutzenergie** — der JAZ-Nenner-Abzug.

        Kühlen (**W-14**) plus Lüften und Entfeuchten (**E4**). Alle drei
        erzeugen keine Wärme, die in einem Wärmemengenzähler landet; stünde ihr
        Strom im Nenner, drückte er die Arbeitszahl aus demselben Grund.

        ⭐ **Die anlagenweite Entsprechung zu**
        {@link ModusStromZeile.funktionsfremd_kwh} — dieselbe Definition, eine
        Ebene höher. Sie steht hier, damit die vier ``arbeitszahl``-Aufrufer
        **eine** Größe lesen statt drei zu addieren: Genau so ist W-14
        entstanden, als der Kühlstrom an einer von drei Größen nicht nachgezogen
        wurde.

        ⚠ **Abgezogen, nicht gesperrt** — die Mengen bleiben in jeder Bilanz.
        """
        return (
            self.modus_strom_kuehlen_kwh
            + self.modus_strom_lueften_kwh
            + self.modus_strom_entfeuchten_kwh
        )

    @property
    def hat_modus_split(self) -> bool:
        """Gibt es überhaupt eine Aufteilung zu zeigen?

        ⚠ **Zwei Wege, ein Ergebnis** (#263): abgeleitet aus dem Betriebsmodus
        (dann gibt es Abdeckungs-Stunden) **oder** gemessen aus
        Betriebsart-Zählern (dann gibt es keine — ein Zähler zählt kWh, keine
        Stunden mit Signal). Nur die Abdeckung zu prüfen hieße, eine gemessene
        Aufteilung nirgends zu zeigen.
        """
        return self.modus_abdeckung_h > 0 or self.modus_gemessen
