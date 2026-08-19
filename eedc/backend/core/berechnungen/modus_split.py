"""Aufteilung des Wärmepumpen-Stroms nach Betriebsmodus (#263 K-2, S3).

**Was hier passiert.** Eine Split-Klimaanlage heizt und kühlt über *denselben*
Zähler. Seit S2 trägt jede Stundenzeile den Modus (``TagesEnergieProfil.
betriebsmodus_je_wp``) neben der Menge (``komponenten["waermepumpe_<id>"]``).
Diese Datei faltet beides zu ``Stunde × Modus × kWh`` — mehr braucht die
Aufteilung nicht.

**Reine Funktionen, kein I/O** (ADR-001). Die Stundenzeilen holt
``services/energie_profil/modus_split_monat.py``.

---

**Drei Eigenschaften, die keine Geschmacksfrage sind:**

1. **Das volle Kanon-Dict, nicht zwei Skalare.** Gespeichert werden nur die
   Teilmengen zu ``heizen`` und ``kuehlen`` (``AUFGETEILTE_MODI``), aber die
   Faltung liefert **alle sechs** Klassen. K-1 (SEER) braucht die Kühl-kWh und
   ``abdeckung_h`` als Zeitbasis und ist damit ein *Lesevorgang* statt eines
   Umbaus an dieser Stelle. Der Unterschied kostet heute nichts.

2. **Zwei Vorzeichen-Welten, und sie sind gegenläufig.** Der Stunden-Wert aus
   ``TagesEnergieProfil.komponenten`` kommt aus dem **Leistungs**-Pfad und ist
   für eine Wärmepumpe **negativ** (``live_tagesverlauf_service`` schreibt
   ``-abs(...)`` für alles mit ``seite: "senke"``). Die Tages-kWh aus
   ``TagesZusammenfassung.komponenten_kwh`` kommt aus dem **Zähler**-Pfad und
   ist **positiv** (``summe_waermepumpe_kwh``: „immer ≥ 0"). Wer das
   verwechselt, bekommt eine Aufteilung mit dem falschen Vorzeichen oder eine
   Normierung, die das Ergebnis spiegelt. Diese Datei rechnet durchgehend mit
   **Beträgen** und dokumentiert das an jedem Eingang.

3. **Normiert wird opportunistisch, geschützt wird durch die Invariante.**
   Wo der Zählerpfad eine Tages-kWh für dieses Gerät hat, wird die Stundenform
   darauf normiert — Präzedenz v3.45.5 (Live-Tagesverlauf: *„nur die Kurvenform
   fällt auf den Leistungssensor zurück, die Stunden-Energie bleibt
   zählertreu"*). Sie ist aber **nicht garantiert vorhanden**:
   ``get_komponenten_tageskwh`` sagt selbst, dass Investitionen ohne gemappten
   Counter gar nicht im Dict erscheinen (an der Demo-Box gemessen: über alle
   sieben vorhandenen Tageszeilen ist ``komponenten_kwh`` ``NULL``). Wo sie
   fehlt, gilt die Roh-Summe des Leistungspfads — und was die
   Teilmengen-Invariante dann hält, ist allein die Regel im Schreibpfad:
   **Σ Teilmengen > Gesamtwert ⇒ gar nicht schreiben**, nicht kappen. Die
   Normierung ist die Verbesserung, die Invariante ist der Schutz.

**Was hier NICHT passiert:** nichts wird hochgerechnet. Stunden ohne
Modus-Signal tragen zu keiner Teilmenge bei; ihre Energie erscheint beim
Anwender als *„nicht aufgeteilt" = Gesamt − Σ Teilmengen* (Konzept §4) und wird
nie gespeichert (§3.1, Folge 2).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Optional, Sequence

from backend.core.betriebsmodus import AUFGETEILTE_MODI, BETRIEBSMODUS_KANON

#: Kennung der Ableitungs-Regel „Heizwärme aus modus-aufgeteiltem Strom × JAZ".
#:
#: Sie steht **hier im Layer** und nicht in `services/provenance.py`, weil die
#: Regel hier definiert ist — `provenance` importiert sie (`ABGELEITET_JAZ_MODUS`),
#: genau wie es das für `REGEL_EINSPEISE_DECKUNG` schon tut. Abgeschrieben statt
#: importiert hinterließe eine Umbenennung zwei Wahrheiten, und die Lesestellen
#: fänden je nach Herkunft die eine Hälfte nicht.
REGEL_JAZ_MODUS_SPLIT: str = "jaz_modus_split"

#: Provenance-Schlüssel der Heizwärme in `InvestitionMonatsdaten`.
PROVENANCE_KEY_HEIZENERGIE: str = "verbrauch_daten.heizenergie_kwh"


def heizwaerme_ist_abgeleitet(source_provenance: Optional[dict]) -> bool:
    """Trägt die gespeicherte Heizwärme dieser Zeile die Ableitungs-Marke?

    **Das ist die Weiche für Konzept §3.5.** Eine abgeleitete Wärme darf
    multipliziert werden (Gaskosten, CO₂, Alternativkosten), aber nie durch den
    Strom geteilt: dort käme exakt die gepflegte JAZ heraus — eine Zahl, die
    nichts misst und trotzdem wie eine Messung aussieht.

    Bewusst **eine** Funktion und kein `if` an sieben Stellen: die Herkunft
    hängt am Wert, nicht an der Bauart des Geräts (eine Luft-Wasser-WP ohne
    Wärmemengenzähler fällt unter dieselbe Regel, eine Klimaanlage **mit**
    Zähler ist gemessen wie jede andere).
    """
    if not source_provenance:
        return False
    eintrag = source_provenance.get(PROVENANCE_KEY_HEIZENERGIE)
    if not isinstance(eintrag, dict):
        return False
    return eintrag.get("abgeleitet") == REGEL_JAZ_MODUS_SPLIT


@dataclass(frozen=True)
class ModusStunde:
    """Eine Stunde **eines** Geräts: wie viel Energie, in welchem Modus.

    ``kwh`` ist der **Betrag** der Stundenenergie (kWh). Der Aufrufer nimmt
    dafür ``abs()`` auf den Komponenten-Wert — der ist im Leistungspfad negativ
    (s. Modul-Kopf, Punkt 2).

    ``modus`` ist ein Kanon-Wert oder ``None``. ``None`` heißt **„nicht
    hingesehen"** (kein Sensor, HA-Ausfall, Tag vor der Zuordnung) und ist
    ausdrücklich nicht dasselbe wie ``"unbestimmt"`` (= „hingesehen, Seite
    nicht zuordenbar"). Nur ``None`` fehlt in der Abdeckung.
    """

    kwh: Optional[float] = None
    modus: Optional[str] = None


@dataclass(frozen=True)
class ModusSplit:
    """Das Ergebnis der Faltung für **ein** Gerät über einen Zeitraum."""

    #: kWh je Kanon-Modus — **alle sechs Klassen**, auch die, die nie
    #: gespeichert werden (s. Modul-Kopf, Punkt 1). Modi ohne Stunde fehlen.
    kwh_je_modus: dict[str, float] = field(default_factory=dict)

    #: Stunden mit gültigem Modus-Signal (auch ``unbestimmt``/``aus`` zählen —
    #: eedc hat hingesehen). Das Qualitätsmaß, nicht die Menge.
    #:
    #: ⚑ **Hier stand bis zum Bau ein zweites Feld ``stunden_ohne_signal``.** Es
    #: ist wieder raus, weil eine eigene Probe gezeigt hat, dass es im echten
    #: Pfad **strukturell immer 0** wäre: der Lader filtert Stundenzeilen ohne
    #: Modus-Spur schon in SQL weg, sie erreichen die Faltung nie. Ein Feld, das
    #: nur in einer Fixture einen Wert hat, wird später als Messwert gelesen —
    #: und die Aussage trägt ``abdeckung_h`` ohnehin (3 von 720 Stunden sagt
    #: alles, was „eedc hat kaum hingesehen“ heißen soll).
    abdeckung_h: float = 0.0


    @property
    def aufgeteilt_kwh(self) -> float:
        """Σ der Modi, für die es eine gespeicherte Teilmenge gibt."""
        return sum(self.kwh_je_modus.get(m, 0.0) for m in AUFGETEILTE_MODI)

    @property
    def erfasst_kwh(self) -> float:
        """Σ **aller** Stunden mit Modus-Signal — inkl. Lüften, Aus, Unbestimmt."""
        return sum(self.kwh_je_modus.values())

    def teilmenge_kwh(self, modus: str) -> float:
        """kWh eines einzelnen Modus (0.0, wenn er im Zeitraum nicht vorkam)."""
        return self.kwh_je_modus.get(modus, 0.0)

    @property
    def ist_leer(self) -> bool:
        """Keine einzige Stunde mit Modus-Signal — es gibt nichts auszuweisen."""
        return self.abdeckung_h <= 0


def falte_modus_split_tag(
    stunden: Sequence[ModusStunde],
    *,
    tages_kwh: Optional[float] = None,
) -> ModusSplit:
    """Faltet die Stunden **eines Tages** für ein Gerät.

    Args:
        stunden: die Stundenzeilen des Tages für dieses Gerät. Reihenfolge und
            Vollständigkeit sind egal — fehlende Stunden sind schlicht nicht
            dabei.
        tages_kwh: die zählerbasierte Tagesmenge dieses Geräts, **als Betrag**.
            Ist sie vorhanden und trägt der Tag überhaupt Energie, wird die
            Stundenform darauf normiert (Modul-Kopf, Punkt 3). ``None`` oder 0
            ⇒ keine Normierung, die Roh-Beträge gelten.

    Returns:
        Den ``ModusSplit`` dieses Tages.

    ⚠ Die Normierung skaliert **alle** Modi mit demselben Faktor. Sie verändert
    also die Aufteilung nicht, nur ihr Niveau — genau das ist gewollt: der
    Leistungspfad kennt die *Form* am besten, der Zählerpfad die *Menge*.
    """
    kwh_je_modus: dict[str, float] = {}
    abdeckung = 0.0
    roh_summe = 0.0

    for eintrag in stunden:
        # `or 0.0` ist hier korrekt und nicht die 0-Werte-Falle: eine Stunde
        # ohne Menge trägt zur Summe nichts bei, bleibt aber für die Abdeckung
        # eine erfasste Stunde (das Gerät stand — auch das ist eine Messung).
        menge = abs(float(eintrag.kwh or 0.0))
        roh_summe += menge
        if eintrag.modus is None:
            # Sie zählt weiter in `roh_summe` (und damit in den Nenner der
            # Normierung), aber zu keiner Teilmenge und nicht zur Abdeckung.
            continue
        abdeckung += 1.0
        kwh_je_modus[eintrag.modus] = kwh_je_modus.get(eintrag.modus, 0.0) + menge

    if tages_kwh is not None and roh_summe > 0:
        ziel = abs(float(tages_kwh))
        if ziel > 0:
            faktor = ziel / roh_summe
            kwh_je_modus = {m: v * faktor for m, v in kwh_je_modus.items()}

    return ModusSplit(kwh_je_modus=kwh_je_modus, abdeckung_h=abdeckung)


def summiere_modus_split(splits: Iterable[ModusSplit]) -> ModusSplit:
    """Addiert Tages-Splits zu einem Zeitraum-Split (Σ über Tage ist assoziativ).

    Bewusst getrennt von {@link falte_modus_split_tag}: die **Normierung ist
    tagesweise**, weil die Zählersumme tagesweise vorliegt. Ein Monat, den man
    in einem Rutsch faltet, würde einen Tag ohne Zählerspur mit dem Faktor
    eines anderen Tages skalieren.
    """
    kwh_je_modus: dict[str, float] = {}
    abdeckung = 0.0
    for split in splits:
        abdeckung += split.abdeckung_h
        for modus, wert in split.kwh_je_modus.items():
            kwh_je_modus[modus] = kwh_je_modus.get(modus, 0.0) + wert
    return ModusSplit(kwh_je_modus=kwh_je_modus, abdeckung_h=abdeckung)


def teilmengen_passen(
    split: ModusSplit,
    gesamt_kwh: Optional[float],
    *,
    toleranz_kwh: float = 0.5,
) -> bool:
    """Hält die Teilmengen-Invariante ``Σ Teilmengen ≤ Gesamt``? (Konzept §9)

    **Das ist der eigentliche Schutz dieses Bauteils, nicht die Normierung**
    (Modul-Kopf, Punkt 3). Der Stunden- und der Monats-Wert stammen aus zwei
    verschiedenen Pfaden; genau dieses Paar lag bei der Wallbox schon einmal um
    Faktor ≈ 2 auseinander (#356, Achse-2-Drift). Dazu kommt der ganz normale
    Fall, dass jemand den Monatswert kleiner von Hand pflegt.

    ``toleranz_kwh`` fängt Rundung ab, nicht Drift: eine halbe Kilowattstunde
    über einen Monat ist Rechengenauigkeit, alles darüber ist ein Widerspruch,
    der nicht gespeichert werden darf.

    ``gesamt_kwh is None`` ⇒ ``False``: ohne Gesamtwert gibt es nichts, wovon
    die Teilmenge eine Teilmenge wäre.
    """
    if gesamt_kwh is None:
        return False
    return split.aufgeteilt_kwh <= float(gesamt_kwh) + toleranz_kwh


def heiz_effizienz_gepflegt(parameter: Optional[dict]) -> Optional[float]:
    """Der **gepflegte** Heiz-Wirkungsgrad einer Wärmepumpe — oder ``None``.

    Aus ihm entsteht die abgeleitete Heizwärme (``strom × faktor``, Konzept
    §3.4). Welcher Parameter gilt, sagt ``effizienz_modus``:

    ==================  ==========================
    ``gesamt_jaz``      ``jaz``
    ``scop``            ``scop_heizung``
    ``getrennte_cops``  ``cop_heizung``
    ==================  ==========================

    ⚠ **Nie aus einem Default.** ``PARAM_WAERMEPUMPE_DEFAULTS`` trägt
    ``jaz: 3.5`` — wer die Defaults anwendet, erfindet für **jede** ungepflegte
    Wärmepumpe eine Wärmemenge und damit eine Ersparnis, eine CO₂-Zahl und
    einen Kostenvergleich. Genau das verbietet Konzept §3.4 („nur wenn die JAZ
    gepflegt ist"), und genau das ist die N-258-Klasse. Deshalb liest diese
    Funktion **roh** aus ``parameter`` und liefert ``None``, wenn dort nichts
    steht.

    Unplausible Werte (``≤ 0``) gelten als ungepflegt: ein Faktor 0 machte aus
    jedem Heizbetrieb 0 kWh Wärme, was schlimmer ist als keine Angabe.

    ⚑ Es gibt im Baum vier weitere Stellen, die dieselbe Fallunterscheidung von
    Hand machen (``vorschlag_service``, ``daten_checker/stammdaten``,
    ``investitionen/crud``, ``core/calculations``). Sie hier mit umzustellen
    wäre eine Auftragsausweitung — der Befund ist als Nebenfund notiert.
    """
    params = parameter or {}
    modus = params.get("effizienz_modus") or "gesamt_jaz"
    schluessel = {
        "gesamt_jaz": "jaz",
        "scop": "scop_heizung",
        "getrennte_cops": "cop_heizung",
    }.get(modus)
    if schluessel is None:
        return None
    wert = params.get(schluessel)
    if wert is None:
        return None
    try:
        faktor = float(wert)
    except (TypeError, ValueError):
        return None
    return faktor if faktor > 0 else None


def abgeleitete_heizwaerme_kwh(
    strom_heizen_kwh: Optional[float], parameter: Optional[dict]
) -> Optional[float]:
    """``strom_heizen × Heiz-Effizienz`` — oder ``None``, wenn eines von beiden fehlt.

    **Die Umkehrung einer Rechnung, die eedc seit jeher macht.**
    ``core/calculations.py`` teilt eine *geschätzte Jahres-Wärme* durch die JAZ,
    um auf den Strom zu kommen. Die Richtung hier ist die genauere: der Strom
    ist gemessen und monatsgenau, die Jahresschätzung war geraten.

    ``None`` heißt „keine Aussage" und ist nicht 0 — ohne gepflegte Effizienz
    weiß eedc die Wärmemenge schlicht nicht (ADR-002/P4).
    """
    if strom_heizen_kwh is None:
        return None
    faktor = heiz_effizienz_gepflegt(parameter)
    if faktor is None:
        return None
    return float(strom_heizen_kwh) * faktor


def unbekannte_modi(split: ModusSplit) -> set[str]:
    """Modi im Ergebnis, die nicht zum Kanon gehören — für den Wächter.

    Leer im Normalfall. Nicht leer heißt: irgendwo hat jemand einen Rohwert
    durchgereicht, statt ihn über ``normalisiere_betriebsmodus`` zu schicken.
    """
    return set(split.kwh_je_modus) - set(BETRIEBSMODUS_KANON)
