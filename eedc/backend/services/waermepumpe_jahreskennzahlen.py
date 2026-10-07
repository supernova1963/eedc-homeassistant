"""Die Wärmepumpen-Kennzahlen eines Zeitraums aus den Monats-Fakten — EINE Stelle.

B6/Y-2 (05.09.2026): Bis hierher rechnete `cockpit/uebersicht.py` (Cockpit → Jahr,
B4) den ganzen Kennzahl-Satz aus den Fakten — Arbeitszahl mit Grund und Hinweis,
je Funktion, Kühlen, Herkunft, Vorbehalt, Betriebsarten — und der PDF-Jahresbericht
rechnete daneben eine **eigene** Arbeitszahl und warf ihren Grund weg: „–" ohne
Grund im gedruckten Bericht (SOLL §3.3 S3), keine Kennzahl je Funktion, keine
Kühl-Arbeitszahl, keine Herkunft der Wärme, kein Vorbehalt (gemessen an F2b · F7 ·
F8 · F11 · F12). Zwei Jahres-Rechnungen für dieselbe Frage sind die Klasse, an
der die Drift-Inventur 2026-07-31 entstanden ist (ADR-001, SOLL §3.3 S1).

Hier steht die Faltung über die Monate genau einmal; Cockpit → Jahr und der
Jahresbericht lesen dasselbe Ergebnis. Die Regeln, die sie trägt:

* **R2 — Q und E derselben Abgrenzung:** getrennte Ströme und Wärmen nur aus
  Monaten MIT getrennter Messung (`hat_split`), sonst teilte man die Wärme aller
  Monate durch den Strom einiger.
* **Ein** Monat mit verletzter Abgrenzung (Fremdanteil, gemischte Bauarten,
  Geräte ohne Wärmezähler) macht die Jahreszahl zum Mischquotienten — deshalb
  `any(...)`, nicht „überwiegend".
* Die Restmenge der Betriebsarten ist die **Σ der monatlichen Layer-Reste** (E4:
  Lüften und Entfeuchten sind Mengen, keine Kennzahl), nicht eine eigene Differenz.
* Der Herkunfts-Faktor (Strom × JAZ) ist nur bei **einer** Wärmepumpe benennbar.

Die Formeln selbst stehen im Layer (`core/berechnungen/waermepumpe_kennzahl.py`);
dieses Modul faltet nur die Fakten und ruft sie.
"""

from __future__ import annotations

from dataclasses import dataclass
from collections.abc import Set as AbstractSet
from typing import Iterable, Optional, Sequence

from backend.core.berechnungen.modus_split import heiz_effizienz_gepflegt
from backend.core.berechnungen.waermepumpe_kennzahl import (
    Arbeitszahl,
    ArbeitszahlJeFunktion,
    abgrenzungs_grund,
    arbeitszahl,
    ARBEITSZAHL_FUNKTIONEN,
    abgrenzung_je_funktion,
    arbeitszahl_je_funktion,
    arbeitszahl_kuehlen,
    ersparnis_vorbehalt,
    waerme_herkunft,
)


@dataclass(frozen=True)
class WpBetriebsarten:
    """Σ der Betriebsart-Ströme über den Zeitraum — Teilmengen des WP-Stroms."""
    heizen_kwh: float
    kuehlen_kwh: float
    warmwasser_kwh: float
    lueften_kwh: float
    entfeuchten_kwh: float
    nicht_aufgeteilt_kwh: float
    abdeckung_h: float
    bezug_kwh: float
    gemessen: bool
    #: **R-C (WK-16f, N-398):** die abgegebene **Nutzenergie** derselben zwei
    #: Betriebsarten. Menge, keine Kennzahl — E4 bleibt.
    #:
    #: ⚠ **Mit Default, und deshalb am Ende:** Die Felder darüber sind ohne
    #: Default deklariert; ein Default dazwischen wäre ein ``TypeError`` beim
    #: Import. Der Default selbst ist gewollt — ein Aufrufer, der nur die
    #: Ströme kennt, soll die Klasse weiter bauen können.
    nutzenergie_lueften_kwh: float = 0.0
    nutzenergie_entfeuchten_kwh: float = 0.0


@dataclass(frozen=True)
class WpJahreskennzahlen:
    """Der Kennzahl-Satz eines Zeitraums, mit Gründen — nie nur die Zahlen."""
    waerme_kwh: float
    strom_kwh: float
    heizung_kwh: float
    warmwasser_kwh: float
    waerme_abgeleitet_kwh: float
    abgrenzung: Optional[str]
    #: **E1b (14.09.2026): die Gründe, die die ANLAGENWEITE Zahl weiterhin
    #: sperren** — dieselbe Kette wie ``abgrenzung``, **ohne** die beiden
    #: Glieder, die zur unteren Schranke werden (gemischte Bauarten · Geräte
    #: ohne Wärmemeldung). Beide machen den Nenner zu groß und den Quotienten
    #: damit zu klein; die übrigen kippen ihn nach oben oder in unbekannte
    #: Richtung, und eine Schranke wäre dort eine Falschaussage.
    #:
    #: ⚠ **``abgrenzung`` bleibt daneben stehen und behält seine Bedeutung** —
    #: der PDF-Jahresbericht und die Kennzahl je Funktion lesen es unverändert.
    #: Zwei Fragen, zwei Felder: *„darf es eine Geräte-Kennzahl geben?"* gegen
    #: *„darf es eine Anlagen-Schranke geben?"*
    abgrenzung_sperrt: Optional[str]
    abgrenzung_stoerung: Optional[str]
    arbeitszahl: Arbeitszahl
    hat_split: bool
    strom_heizen_kwh: float
    strom_warmwasser_kwh: float
    je_funktion: ArbeitszahlJeFunktion
    kaelte_kwh: float
    kuehlen: Arbeitszahl
    #: **E7/Option A** — Σ der monatlichen Nenner-Abzüge (Kühlen · Lüften ·
    #: Entfeuchten), genau der Wert, mit dem ``arbeitszahl`` oben gerechnet hat.
    #: Er steht hier, damit die Systemarbeitszahl denselben Abzug benutzt statt
    #: ihn nachzubauen (S1).
    funktionsfremd_abzug_kwh: float
    hat_modus: bool
    betriebsarten: WpBetriebsarten
    abgeleitet: bool
    herkunft: str
    vorbehalt: Optional[str]


def waermepumpe_jahreskennzahlen(
    fakten: Sequence, wp_invs: Iterable,
    *, waerme_achsen: Optional[AbstractSet[str]] = None,
) -> WpJahreskennzahlen:
    """Faltet die Monats-Fakten eines Zeitraums zu den WP-Kennzahlen.

    ``fakten``: die Monats-Fakten der Anlage (ADR-002/P10). ``wp_invs``: die
    Wärmepumpen-Investitionen, die für den Zeitraum zählen — nur ihre Anzahl und
    (bei genau einer) ihre Parameter werden gelesen (Herkunfts-Faktor).

    Args:
        waerme_achsen: **die anlagenweiten Wärme-Achsen** (WK-16h/**R-2**), aus
            ``waerme_klima_block.achsen_der_anlage`` — dieselbe Frage, die Monat
            und Tag stellen. ``None`` heißt „beide" und ist bitgleich zum Stand
            vor WK-16h.

            ⚠ **Die Ein-Achsen-Regel nimmt hier ``az``**, die Gesamt-Arbeitszahl
            dieser Faltung — nicht die **System**zahl, die die Route erst
            danach daraus bildet. Sie wäre auch nicht zu bekommen (sie braucht
            diese Faltung als Eingang), und sie wäre auch nicht besser: Wo die
            Systemzahl einen Wert trägt, den ``az`` sperrt, ist sie eine
            **Schranke** — und eine Schranke wird nie zur Funktions-Arbeitszahl
            ({@link als_arbeitszahl} liefert dort ``None``). Die Regel lautet in
            allen drei Sichten gleich: *die veröffentlichte Gesamt-Arbeitszahl
            der Sicht, niemals ein „≥".*
    """
    wp_invs = list(wp_invs)
    waerme = sum(f.wp.waerme_kwh for f in fakten)
    strom = sum(f.wp.strom_kwh for f in fakten)
    heizung = sum(f.wp.heizung_kwh for f in fakten)
    warmwasser = sum(f.wp.warmwasser_kwh for f in fakten)
    waerme_abgeleitet = sum(f.wp.waerme_abgeleitet_kwh for f in fakten)
    stoerung = next(
        (f.wp.abgrenzung_stoerung for f in fakten if f.wp.abgrenzung_stoerung), None,
    )
    # ── N-441: die Block-Lagen des JAHRES, drei Faltungen statt einer ──────
    #
    # ⛔ **Die je-Monat-Faltung allein sieht zwei Lagen strukturell nicht.**
    # Sie fragt jeden Monat einzeln und verodert; was erst **über** Monate
    # entsteht, kann sie nicht kennen:
    #
    # * **Perioden-Versatz** — ein Monat traegt Waerme ohne Strom, ein anderer
    #   traegt Strom. Jeder Monat fuer sich ist unauffaellig, die Jahressumme
    #   nimmt beide Seiten mit: gemessen **6,0** statt 3,0, und zwar ohne jeden
    #   Grund daneben. Dieselbe Zwei-Lagen-Unterscheidung (Geraete gegen Monate),
    #   die `_perioden_lage` unten fuer die Funktions-Ebene trifft (N-438).
    # * **Geraete-Kreuzung ueber Monate** — Waerme von Geraet 1 im Maerz, Strom
    #   von Geraet 2 im Juli. Kein einzelner Monat traegt beide Seiten, die
    #   VEREINIGUNGEN tun es: gemessen **4,0** ohne Grund. Ohne die
    #   Vereinigungs-Faltung stuende hier „aus verschiedenen Monaten" — richtig
    #   gesperrt, aber mit der harmloseren Haelfte begruendet.
    #
    # ⚠ **Die je-Monat-Faltung bleibt daneben noetig**: Zwei Monate mit
    # vertauschten Geraeten haben dieselben Vereinigungen und faellen der
    # Vereinigungs-Regel nicht auf.
    _strom_jahr: frozenset[int] = frozenset().union(
        *(f.wp.geraete_mit_strom for f in fakten)
    ) if fakten else frozenset()
    _waerme_jahr: frozenset[int] = frozenset().union(
        *(f.wp.geraete_mit_waerme for f in fakten)
    ) if fakten else frozenset()
    _geraete_ohne_waerme_jahr = any(
        f.wp.waerme_deckt_nicht_alle_geraete for f in fakten
    ) or bool(_waerme_jahr and _waerme_jahr < _strom_jahr)
    _geraete_verschieden_jahr = any(
        f.wp.geraete_verschieden for f in fakten
    ) or bool(
        _strom_jahr and _waerme_jahr and not _waerme_jahr <= _strom_jahr
    )
    _perioden_versetzt_jahr = any(
        not f.wp.geraete_mit_strom and f.wp.geraete_mit_waerme for f in fakten
    ) and any(f.wp.geraete_mit_strom for f in fakten)
    abgrenzung = abgrenzungs_grund(
        abgrenzung_stoerung=stoerung,
        bauarten_gemischt=any(f.wp.bauarten_gemischt for f in fakten),
        geraete_ohne_waerme=_geraete_ohne_waerme_jahr,
        geraete_verschieden=_geraete_verschieden_jahr,
        perioden_versetzt=_perioden_versetzt_jahr,
    )
    # SOLL §3.2b je Funktion — ueber das JAHR gefaltet.
    #
    # ⚠ **Nicht `all(...)` ueber alle Monate.** Ein Sommermonat hat keinen
    # Heizbetrieb; `funktion_sauber_abgegrenzt` ist dort False, weil es die
    # Funktion nicht gibt — nicht, weil sie vermischt waere. Wer das nicht
    # trennt, sperrt die Jahres-Heizzahl an jedem Juli. Gefragt werden deshalb
    # nur die Monate, die die Funktion ueberhaupt tragen.
    def _deckung_im_jahr(funktion: str) -> Optional[bool]:
        """Jeder Monat, der zur Jahressumme beitraegt, muss sich decken.

        ⛔ **Nicht die Geraetezahlen des Jahres vergleichen.** Sie sehen den
        entscheidenden Fall nicht: Ein Monat mit Waerme, aber ohne den Strom
        derselben Funktion, schiebt seine Waerme in die Jahressumme und seinen
        Strom nicht. Die Zahl der beteiligten Geraete ist in beiden Monaten
        gleich — die Summe ist es nicht. **Gemessen: 3,75 statt 3,0.**

        ⚠ Monate ohne Aussage (``None``) zaehlen nicht mit: ein Sommermonat
        ohne Heizbetrieb ist kein Abgrenzungsfehler.
        """
        urteile = [
            u for u in (f.wp.deckung_je_funktion(funktion) for f in fakten)
            if u is not None
        ]
        return all(urteile) if urteile else None

    def _perioden_lage(funktion: str) -> bool:
        """Liegt die verletzte Deckung an der ZEIT statt an den Geraeten? (**N-438**)

        Beide Lagen ergeben dasselbe Urteil `False` — gemessen:
        ``deckung_aus_geraeten(∅, {1})`` und ``({1}, {1, 2})`` liefern beides
        `False`. Der Grund darf sie trotzdem nicht verwechseln: Bei EINEM
        Geraet, dessen Strom erst ab einem spaeteren Monat erfasst ist, sprach
        der Satz von „verschiedenen Geraeten".

        ⛔ **Die beiden Pruefungen sind DISJUNKT, und genau daran ist ein erster
        Entwurf gescheitert:** „Perioden-Lage, aber bei verschiedenen
        Geraetezahlen gewinnt die Geraete-Lage" haette den eigenen Ausloeser
        geschluckt — ein Monat mit ``e = ∅ ∧ q ≠ ∅`` hat **immer** ``e != q``.
        Die Geraete-Lage fragt deshalb nur Monate, die ueberhaupt Strom tragen.

        ⭐ **Und nur Monate, die auch Nutzenergie tragen (N-441, sechste Lage
        des N-438-Baus).** ``q`` leer heisst Standby: Strom ohne Nutzenergie.
        ``_deckung_im_jahr`` klammert solche Monate schon als ``None`` aus,
        `_perioden_lage` tat es nicht — bei EINEM Geraet mit einem Sommer-Monat
        ohne Waerme und einem Monat ohne Strom stand deshalb „von verschiedenen
        Geraeten", wo es nur eines gibt.

        Liegen beide vor, gewinnt die **Geraete**-Lage: Sie ist die
        grundsaetzlichere Stoerung — verschiedene Geraete decken sich auch dann
        nicht, wenn jeder Monat vollstaendig waere.
        """
        paare = [
            (getattr(fk.wp, f"geraete_e_{funktion}"), getattr(fk.wp, f"geraete_q_{funktion}"))
            for fk in fakten
        ]
        if any(e and q and e != q for e, q in paare):
            return False
        return (
            any(not e and q for e, q in paare)
            and any(e for e, _ in paare)
        )

    _deckung_je_funktion = {f: _deckung_im_jahr(f) for f in ARBEITSZAHL_FUNKTIONEN}
    _je_funktion_grund = abgrenzung_je_funktion(
        abgrenzung_stoerung=stoerung,
        bauarten_gemischt=any(f.wp.bauarten_gemischt for f in fakten),
        geraete_ohne_waerme=any(f.wp.waerme_deckt_nicht_alle_geraete for f in fakten),
        deckung_je_funktion=_deckung_je_funktion,
        perioden_je_funktion={f: _perioden_lage(f) for f in ARBEITSZAHL_FUNKTIONEN},
    )
    # E1b: dieselbe Kette ohne die beiden Glieder, die zur Schranke werden.
    abgrenzung_sperrt = abgrenzungs_grund(
        abgrenzung_stoerung=stoerung,
        geraete_verschieden=_geraete_verschieden_jahr,
        perioden_versetzt=_perioden_versetzt_jahr,
    )
    # SOLL-§9-E7/Option A: der **Abzug**, nicht die Menge — die Monats-Fakten
    # haben ihn je Gerät entschieden (F5 + abgeleiteter Split ⇒ 0).
    funktionsfremd_abzug = sum(
        f.wp.modus_strom_funktionsfremd_abzug_kwh for f in fakten
    )
    az = arbeitszahl(
        waerme, strom,
        waerme_abgeleitet_kwh=waerme_abgeleitet,
        strom_funktionsfremd_kwh=funktionsfremd_abzug,
        abgrenzung_verletzt=abgrenzung,
    )
    hat_split = any(f.wp.hat_split for f in fakten)
    strom_heizen = sum(f.wp.strom_heizen_kwh for f in fakten if f.wp.hat_split)
    strom_ww = sum(f.wp.strom_warmwasser_kwh for f in fakten if f.wp.hat_split)
    je_funktion = arbeitszahl_je_funktion(
        heizung_kwh=sum(f.wp.heizung_kwh for f in fakten if f.wp.hat_split),
        strom_heizen_kwh=strom_heizen,
        warmwasser_kwh=sum(f.wp.warmwasser_kwh for f in fakten if f.wp.hat_split),
        strom_warmwasser_kwh=strom_ww,
        hat_split=hat_split,
        # **N-479: das Jahr darf denselben Zeitraum-Grund führen wie der Tag.**
        # ⚠ Derselbe Filter wie bei den Mengen darüber (``if f.wp.hat_split``) —
        # eine Marke aus einem Monat, dessen Menge gar nicht eingeht, wäre eine
        # Aussage über Zahlen, die in diesem Quotienten nicht stehen.
        # ``any``, weil ein einziger gemessener Monat die Funktion für den
        # Zeitraum messbar macht: „im Sommer nicht geheizt" ist dann die richtige
        # Auskunft, „kein Zähler zugeordnet" die falsche.
        # ⚠ **BEIDE Seiten** (N-438/S3): siehe die Begründung im Monat.
        # H-3 zu E4f: die gemessene Gesamtwärme zählt als „Wärme gemessen" (wie im Monat, ``komponenten.py``).
        null_ist_gemessen_heizen=any(
            (f.wp.heizung_gemessen or f.wp.waerme_ist_gesamt) and f.wp.strom_heizen_gemessen
            for f in fakten if f.wp.hat_split
        ),
        null_ist_gemessen_warmwasser=any(
            (f.wp.warmwasser_gemessen or f.wp.waerme_ist_gesamt) and f.wp.strom_warmwasser_gemessen
            for f in fakten if f.wp.hat_split
        ),
        # N-391: gefragt sind dieselben Monate wie oben — nur die mit getrennter
        # Strommessung tragen die Funktions-Quotienten. Ein Monat mit gemeinsamem
        # Wärmemengenzähler liefert für sie keinen Zähler, sondern einen Grund.
        waerme_ist_gesamt=any(
            f.wp.waerme_ist_gesamt for f in fakten if f.wp.hat_split
        ),
        waerme_abgeleitet_kwh=waerme_abgeleitet,
        abgrenzung_verletzt=abgrenzung,
        abgrenzung_je_funktion_grund=_je_funktion_grund,
        # R-2 (WK-16h): dieselbe Achsen-Frage wie im Monat und am Tag.
        achsen=waerme_achsen,
        gesamt=az,
    )
    kaelte = sum(f.wp.nutzenergie_kuehlen_kwh for f in fakten)
    modus_kuehlen = sum(f.wp.modus_strom_kuehlen_kwh for f in fakten)
    kuehlen = arbeitszahl_kuehlen(
        kaelte, modus_kuehlen,
        abgrenzung_verletzt=_je_funktion_grund["kuehlen"],
    )
    betriebsarten = WpBetriebsarten(
        heizen_kwh=sum(f.wp.modus_strom_heizen_kwh for f in fakten),
        kuehlen_kwh=modus_kuehlen,
        warmwasser_kwh=sum(f.wp.modus_strom_warmwasser_kwh for f in fakten),
        lueften_kwh=sum(f.wp.modus_strom_lueften_kwh for f in fakten),
        entfeuchten_kwh=sum(f.wp.modus_strom_entfeuchten_kwh for f in fakten),
        nutzenergie_lueften_kwh=sum(f.wp.nutzenergie_lueften_kwh for f in fakten),
        nutzenergie_entfeuchten_kwh=sum(
            f.wp.nutzenergie_entfeuchten_kwh for f in fakten),
        nicht_aufgeteilt_kwh=sum(f.wp.modus_nicht_aufgeteilt_kwh for f in fakten),
        abdeckung_h=sum(f.wp.modus_abdeckung_h for f in fakten),
        bezug_kwh=sum(f.wp.modus_strom_bezug_kwh for f in fakten),
        gemessen=any(f.wp.modus_gemessen for f in fakten),
    )
    abgeleitet = waerme_abgeleitet > 0
    ref_param = wp_invs[0].parameter if len(wp_invs) == 1 else None
    herkunft = waerme_herkunft(
        abgeleitet,
        heiz_effizienz_gepflegt(ref_param) if (abgeleitet and ref_param) else None,
    )
    return WpJahreskennzahlen(
        waerme_kwh=waerme,
        strom_kwh=strom,
        heizung_kwh=heizung,
        warmwasser_kwh=warmwasser,
        waerme_abgeleitet_kwh=waerme_abgeleitet,
        abgrenzung=abgrenzung,
        abgrenzung_sperrt=abgrenzung_sperrt,
        abgrenzung_stoerung=stoerung,
        arbeitszahl=az,
        hat_split=hat_split,
        strom_heizen_kwh=strom_heizen,
        strom_warmwasser_kwh=strom_ww,
        je_funktion=je_funktion,
        kaelte_kwh=kaelte,
        kuehlen=kuehlen,
        funktionsfremd_abzug_kwh=funktionsfremd_abzug,
        hat_modus=any(f.wp.hat_modus_split for f in fakten),
        betriebsarten=betriebsarten,
        abgeleitet=abgeleitet,
        herkunft=herkunft,
        vorbehalt=ersparnis_vorbehalt(waerme_abgeleitet=abgeleitet, abgrenzung=stoerung),
    )
