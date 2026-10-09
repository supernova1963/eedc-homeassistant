"""Die Wärme/Klima-Kennzahlen **eines Geräts** — EINE Stelle (WK-16a).

Der Komponenten-Hub rechnet sie seit jeher (``investitionen/dashboard_waermepumpe.py::
get_waermepumpe_dashboard``): Strom, Wärme, Arbeitszahl gesamt, je Funktion und
Kühlen — je Gerät, über dessen Monatszeilen gefaltet. Das **Cockpit** hatte sie
nicht; der Block *Wärme/Klima* zeigte anlagenweite Summen und verwies für die
Gerätezahlen mit einem Link in den Hub.

⭐ **Warum das ein eigenes Modul wurde und keine zweite Schleife im Cockpit**
(Entscheid Gernot, 14.09.2026 — D-Sicht 3): Die Tabelle *„Zahlen je Gerät" im
Block* ist dieselbe Frage, die der Hub schon beantwortet. Sie dort ein zweites
Mal zu rechnen wäre die **W-3-Klasse** in Reinform — dieselbe Kennzahl an zwei
Orten, und die Vorgeschichte dieser Fläche besteht fast vollständig aus genau
dieser Bauform (W-3 · W-15 · F-56 · N-397 · N-441). Der Hub ruft dieses Modul,
das Cockpit ruft dasselbe Modul; es gibt keinen zweiten Weg.

## Zwei Mengen-Herkünfte, eine Rechenstelle

Die **Kennzahl** entsteht genau einmal ({@link kennzahlen_aus_mengen}). Woher die
**Mengen** kommen, ist eine andere Frage, und sie hat zwei Antworten:

======================  =================================================
Sicht                   Mengen aus
======================  =================================================
Hub · Monat · Jahr      ``InvestitionMonatsdaten`` ({@link mengen_aus_monatszeilen})
Cockpit → Tag           den Tages-Werten je Gerät ({@link GeraetMengen} direkt)
======================  =================================================

⚠ **Das ist kein zweiter Rechenweg, sondern eine zweite Zeitachse.** Der Tag
faltet Snapshots, nicht IMD-Zeilen — dieselbe Begründung, mit der
``KONZEPT-MONATS-FAKTEN.md`` §4 den Tagespfad als Nicht-Ziel der Monats-Schicht
führt. Beide Herkünfte münden in **dieselbe** Datenklasse und damit in dieselben
drei Layer-Aufrufe.

## Was hier NICHT steht

Geld, CO₂ und die Zählerstände (Starts, Betriebsstunden). Sie hängen an Tarifen
und an einer zweiten Tabelle und gehören nicht zur Frage *„wie effizient
arbeitet dieses Gerät?"*. Der Hub rechnet sie weiter selbst.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Optional, Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.berechnungen import (
    betriebsart_nutzenergie_kwh,
    funktionsfremd_abzug_kwh,
    modus_strom_zeile,
)
from backend.core.berechnungen.betriebsart_gemessen import (
    nutzenergie_ohne_kennzahl_kwh,
)
from backend.core.berechnungen.modus_split import heizwaerme_ist_abgeleitet
from backend.core.betriebsmodus import KUEHLEN as BM_KUEHLEN_W5
from backend.core.betriebsmodus import MODUS_ABDECKUNG_FELD
from backend.core.berechnungen.waermepumpe_kennzahl import (
    Arbeitszahl,
    ArbeitszahlJeFunktion,
    GRUND_JE_ABGRENZUNG,
    abgrenzungs_grund,
    arbeitszahl,
    arbeitszahl_je_funktion,
    arbeitszahl_kuehlen,
    heizwaerme_kwh,
    kein_betrieb_grund_der_achsen,
    waerme_gesamt_kwh,
)
from backend.core.berechnungen.imd_monatsaggregat import imd_typ_beitrag
from backend.core.field_definitions import (
    WP_WAERME_ACHSEN_BEIDE,
    get_wp_strom_kwh,
    get_wp_warmwasser_kwh,
    groesse_gibt_es_am_geraet,
    hat_wp_warmwasser_wert,
    nenner_ist_feine_summe,
    wp_waerme_achsen,
)
from backend.core.investition_parameter import abgrenzung_stoerung
from backend.models.investition import Investition, InvestitionMonatsdaten


@dataclass(frozen=True)
class GeraetMengen:
    """Die Mengen **eines** Geräts in **einem** Zeitraum — die Eingabe der Kennzahl.

    Alles, was die drei Layer-Aufrufe brauchen, und nichts darüber hinaus. Die
    Felder tragen die Namen der Größen, nicht die der Datenbankspalten: Ein
    Tagespfad füllt sie aus Snapshots, ein Monatspfad aus IMD-Zeilen, und beide
    meinen dasselbe.
    """

    inv_id: int
    name: str
    strom_kwh: float = 0.0
    #: Kanonisch aufgelöst (**D1**: Gesamtwert vor Summanden), nicht die Summe
    #: der beiden Achsen — ein gemeinsamer Wärmemengenzähler ist die Wahrheit
    #: über dieses Gerät (N-391).
    waerme_kwh: float = 0.0
    heizung_kwh: float = 0.0
    warmwasser_kwh: float = 0.0
    #: Nur aus Zeiträumen MIT getrennter Strommessung — Zähler und Nenner einer
    #: Funktions-Arbeitszahl müssen aus denselben Zeilen stammen (R2).
    strom_heizen_kwh: float = 0.0
    strom_warmwasser_kwh: float = 0.0
    heizung_getrennt_kwh: float = 0.0
    warmwasser_getrennt_kwh: float = 0.0
    hat_getrennte_strommessung: bool = False
    waerme_ist_gesamt_getrennt: bool = False
    #: Gemessene Kältemenge und der Kühlstrom, der ihr gegenübersteht.
    kaelte_kwh: float = 0.0
    modus_strom_kuehlen_kwh: float = 0.0
    #: **E7/Option A** — der ABZUG, nicht die Menge (er ist 0, wo die
    #: Aufteilung nur abgeleitet ist).
    funktionsfremd_abzug_kwh: float = 0.0
    waerme_abgeleitet: bool = False
    #: Ein Zeitraum trägt Wärme ohne Strom, ein anderer trägt Strom (N-441).
    #: Nur ein Aufrufer, der über mehrere Zeiträume faltet, kann die Lage sehen.
    perioden_versetzt: bool = False
    #: Die Anwender-Angabe am Gerät (``fremdstrom``/``fremdwaerme``).
    abgrenzung_stoerung: Optional[str] = None
    #: Gibt es die Warmwasser-Größe an diesem Gerät überhaupt? (**R1**, N-379)
    hat_warmwasser_groesse: bool = True
    #: **Welche Wärme-Achsen hat dieses Gerät?** (WK-16h/**R-1**, N-499) —
    #: ``field_definitions.wp_waerme_achsen``, also die **Registry**.
    #:
    #: ⚠ **Nicht dasselbe wie ``hat_warmwasser_groesse`` darüber, und beide
    #: werden gebraucht.** Jenes fragt ``groesse_gibt_es_am_geraet`` und
    #: entscheidet über eine **Menge** (darf ein gepflegter Warmwasser-Wert in
    #: die Wärme dieses Geräts?); dieses fragt ``feld_urteil == URTEIL_GILT``
    #: und entscheidet über eine **Kennzahl**. Der Unterschied ist die
    #: **weiche** Bedingung: Wer an seiner Brauchwasser-WP doch einen
    #: Heizzähler hat, dessen Menge zählt (jenes ``True``) — eine
    #: *Arbeitszahl Heizen* verspricht eedc ihm trotzdem nicht (dieses ohne
    #: ``heizen``). Dieselbe Trennlinie zieht ``crud.py::_achse_gilt`` seit
    #: WK-15c; ihr Docstring benennt sie.
    waerme_achsen: frozenset[str] = WP_WAERME_ACHSEN_BEIDE
    #: HA-Bauform E4d (Bauplan §8a, Rest N-585): Strom bzw. Wärme GEMESSEN, auch 0? Die Mengen darüber sind ``float``
    #: mit 0-Default — erst diese Marken trennen „kein Betrieb im Zeitraum" (beide gemessen 0) von „kein Zähler".
    strom_gemessen: bool = False
    waerme_gemessen: bool = False

    @property
    def kein_betrieb(self) -> bool:
        """Strom UND Wärme gemessen 0 — das Gerät lief im Zeitraum nicht (§8a: Stufe 3, Mengen 0)."""
        return (self.strom_gemessen and self.waerme_gemessen
                and self.strom_kwh == 0 and self.waerme_kwh == 0)

    @property
    def strom_null_waerme_fehlt(self) -> bool:
        """Gegenfall (§8a, Nachtrag aus der Nachmessung E4d): Strom gemessen 0, Wärme NICHT erfasst ⇒ Stufe 5."""
        return (self.strom_gemessen and self.strom_kwh == 0
                and not self.waerme_gemessen and self.waerme_kwh == 0)

    @property
    def hat_waermemessung(self) -> bool:
        """Steuert dieses Gerät **gemessene Wärme** zum Zähler bei? (**E1b**)

        Die Frage der Schranke: Ein Gerät mit Strom, aber ohne gemessene Wärme,
        macht die anlagenweite Zahl zu einer **unteren** Schranke — sein Strom
        steht im Nenner, seine Nutzenergie in keinem Zähler.
        """
        return self.waerme_kwh > 0 and not self.waerme_abgeleitet


@dataclass(frozen=True)
class GeraetKennzahlen:
    """Mengen **und** Kennzahlen eines Geräts — nie nur die Zahlen (S3)."""

    mengen: GeraetMengen
    gesamt: Arbeitszahl
    je_funktion: ArbeitszahlJeFunktion
    kuehlen: Arbeitszahl

    @property
    def inv_id(self) -> int:
        return self.mengen.inv_id

    @property
    def name(self) -> str:
        return self.mengen.name


@dataclass(frozen=True)
class GeraetFaltung:
    """Was der Monatszeilen-Pfad **zusätzlich** liefert.

    ⚠ Diese Größen gehören nicht zur Kennzahl, sondern zum Hub-Block darum
    herum (Betriebsart-Balken, Abdeckungs-Zeile, Saison-Vergleich). Sie stehen
    deshalb neben {@link GeraetMengen} und nicht darin — wer nur die Kennzahl
    braucht, füllt sie nicht.
    """

    modus_heizen_kwh: float = 0.0
    modus_kuehlen_kwh: float = 0.0
    modus_warmwasser_kwh: float = 0.0
    modus_lueften_kwh: float = 0.0
    modus_entfeuchten_kwh: float = 0.0
    #: **R-C (WK-16f, N-398):** die abgegebene Nutzenergie derselben zwei
    #: Betriebsarten — als **Menge** neben ihrem Strom, ohne Kennzahl (E4).
    nutzenergie_lueften_kwh: float = 0.0
    nutzenergie_entfeuchten_kwh: float = 0.0
    modus_abdeckung_h: float = 0.0
    modus_bezug_kwh: float = 0.0
    modus_gemessen: bool = False
    #: Anwesenheit statt Menge — eine gepflegte 0 ist eine Messung (N-379).
    warmwasser_je_erfasst: bool = False
    #: Die Arbeitszahl **je Monatszeile** (ADR-002/P12) für den Saison-Vergleich.
    jaz_je_monat: list[dict] = field(default_factory=list)
    #: **N-643/N-644:** die Mengen **je Monatszeile** aus denselben Lesetüren wie die Summen in
    #: {@link GeraetMengen} — Strom (``get_wp_strom_kwh``), Heizwärme (``heizwaerme_kwh``),
    #: Warmwasser (``get_wp_warmwasser_kwh``) und Wärme gesamt (``waerme_gesamt_kwh``, D1). Der
    #: Hub-Verlauf und die Aussicht lasen bis 4.1.3 die Rohfelder; Σ Zeilen = die Summen.
    monatsreihe: list[dict] = field(default_factory=list)


def kennzahlen_aus_mengen(m: GeraetMengen) -> GeraetKennzahlen:
    """Die drei Layer-Aufrufe für **ein** Gerät — die eine Rechenstelle.

    ⛔ **Hier wird nichts gerechnet, was der Layer nicht rechnet.** Diese
    Funktion wählt die Eingänge und übersetzt die Anwender-Angabe in ihren
    Grund; die Quotienten und ihre Sperren stehen in
    ``core/berechnungen/waermepumpe_kennzahl.py`` (ADR-001/ADR-002/**P12**).

    ⚠ **Die anlagenweiten Lagen gibt es hier NICHT, und das ist keine Lücke.**
    ``bauarten_gemischt`` und ``geraete_ohne_waerme`` entstehen aus dem
    Zusammenspiel **mehrerer** Geräte; ein Gerät hat eine Bauart, und meldet es
    keine Wärme, ist ``waerme_kwh`` bereits 0. Dieselbe Begründung wie im
    HA-Export-Sensor, der ebenfalls **eine** Investition faltet.
    """
    _stoerung = GRUND_JE_ABGRENZUNG.get(m.abgrenzung_stoerung or "")
    gesamt = arbeitszahl(
        # Gegenfall (§8a, Nachtrag): Strom gemessen 0, Wärme nicht erfasst ⇒ die Wärme geht als ``None`` in den Layer,
        # der nennt Stufe 5 „kein Wärmemengenzähler zugeordnet" statt Stufe 1.
        None if m.strom_null_waerme_fehlt else m.waerme_kwh, m.strom_kwh,
        # E4d (Bauplan §8a): Strom 0 und Wärme 0 GEMESSEN ⇒ Stufe 3 mit dem vorhandenen Zeitraum-Grund der Achsen.
        kein_betrieb_grund=(kein_betrieb_grund_der_achsen(m.waerme_achsen)
                            if (m.kein_betrieb or m.strom_null_waerme_fehlt) else None),
        waerme_abgeleitet_kwh=1.0 if m.waerme_abgeleitet else 0.0,
        strom_funktionsfremd_kwh=m.funktionsfremd_abzug_kwh,
        # N-441: die Perioden-Lage erreicht auch die Geräte-Gesamtzahl. Über
        # die Kette statt über `GRUND_JE_ABGRENZUNG` direkt — ein zweiter Weg
        # neben `abgrenzungs_grund` wäre der Turm, den W-15 hier schon einmal
        # abgetragen hat.
        abgrenzung_verletzt=abgrenzungs_grund(
            abgrenzung_stoerung=m.abgrenzung_stoerung,
            perioden_versetzt=m.perioden_versetzt,
        ),
    )
    je_funktion = arbeitszahl_je_funktion(
        heizung_kwh=m.heizung_getrennt_kwh,
        strom_heizen_kwh=m.strom_heizen_kwh,
        warmwasser_kwh=m.warmwasser_getrennt_kwh,
        strom_warmwasser_kwh=m.strom_warmwasser_kwh,
        hat_split=m.hat_getrennte_strommessung,
        waerme_ist_gesamt=m.waerme_ist_gesamt_getrennt,
        waerme_abgeleitet_kwh=1.0 if m.waerme_abgeleitet else 0.0,
        abgrenzung_verletzt=_stoerung,
        # **R-1 (WK-16h, N-499): die Achsen dieses Geräts entscheiden.** Eine
        # Achse, die es hier nicht gibt, trägt weder Zahl noch Grund; hat das
        # Gerät nur EINE, ist ihre Zahl die Gesamtzahl darüber — sein ganzer
        # Strom gehört per Bauart dieser Funktion. Die Antwort kommt aus der
        # Registry und steht an genau einer Stelle (`wp_waerme_achsen`).
        achsen=m.waerme_achsen,
        gesamt=gesamt,
    )
    kuehlen = arbeitszahl_kuehlen(
        m.kaelte_kwh, m.modus_strom_kuehlen_kwh,
        abgrenzung_verletzt=_stoerung,
    )
    return GeraetKennzahlen(
        mengen=m, gesamt=gesamt, je_funktion=je_funktion, kuehlen=kuehlen,
    )


def mengen_aus_monatszeilen(
    wp: Investition, monatsdaten: Sequence[Any],
) -> tuple[GeraetMengen, GeraetFaltung]:
    """Faltet die Monatszeilen **eines** Geräts zu seinen Mengen.

    ⭐ **Wortgleich aus ``get_waermepumpe_dashboard`` gehoben** (14.09.2026) —
    jede Zeile mit ihrer Begründung, damit der Hub nach dem Umhängen dieselben
    Zahlen liefert. Die Bilanz dazu steht im Bau-Bericht WK-16ab.

    Args:
        monatsdaten: die für den Zeitraum **bereits gefilterten** Zeilen
            (``ist_aktiv_im_monat``). Der Filter bleibt beim Aufrufer: Hub und
            Cockpit filtern verschieden (Lebensdauer gegen Zeitfenster), die
            Faltung selbst ist dieselbe.
    """
    # N-379: Haengt am GERAET, nicht an der Monatszeile — einmal fragen. Eine
    # Split-Klimaanlage hat keinen Warmwasserkreis (N-304).
    hat_warmwasser = groesse_gibt_es_am_geraet(
        "waermepumpe", "warmwasser_kwh", wp.parameter,
    )
    # WK-16h/R-1: ebenfalls am GERÄT, ebenfalls einmal gefragt.
    _achsen = wp_waerme_achsen(wp.parameter)
    _stoerung = abgrenzung_stoerung(wp)

    # ⚠ **Die Start-Typen sind die des Hubs (``int`` gegen ``float``), und das
    # ist kein Zufall:** ``round(0, 1)`` liefert ``0``, ``round(0.0, 1)``
    # liefert ``0.0`` — in der JSON-Antwort sind das zwei verschiedene Literale.
    # Beim Umhängen am 14.09.2026 war genau das der **einzige** Unterschied in
    # der Hub-Bilanz (``gesamt_heizenergie_kwh`` 0 gegen 0.0, gemessen an der
    # Demo r28). Wer hier aufräumt, ändert eine ausgelieferte Antwort.
    #
    # ⛔ **Auf der Heizwärme-Achse hält der int-Start seit WK-16f nicht mehr,
    # und das ist bewusst.** ``heizwaerme_kwh`` liefert ``float`` — es muss, es
    # ist eine Lesetür mit drei Quellen. Gemessen an r27 **und** r28 (14.09.):
    # genau **ein** Unterschied, ``gesamt_heizenergie_kwh`` 17500 → 17500.0 in
    # der Demo-Anlage; der **Wert** ist unverändert, das JSON-Literal nicht.
    # Ihn zu retten hieße, den Rohzugriff wieder danebenzustellen, den dieses
    # Paket gerade entfernt — ein Literal ist das nicht wert. Die **Null** bleibt
    # ``int``: Ohne Zeile mit Wert wird nie addiert.
    strom = heizung = warmwasser = 0
    strom_heizen = strom_warmwasser = 0
    waerme = 0.0
    heizung_getrennt = warmwasser_getrennt = 0.0
    hat_getrennte_strom = waerme_ist_gesamt_getrennt = False
    waerme_abgeleitet = False
    kaelte = abzug = 0.0
    f = GeraetFaltung()
    modus_heizen = modus_kuehlen = modus_warmwasser = 0.0
    modus_lueften = modus_entfeuchten = 0.0
    nutz_lueften = nutz_entfeuchten = 0.0
    modus_abdeckung = modus_bezug = 0.0
    modus_gemessen = ww_je_erfasst = False
    jaz_je_monat: list[dict] = []
    monatsreihe: list[dict] = []
    #: (Wärme, Strom) je Zeile — die Grundlage der Perioden-Lage. Sie entsteht
    #: erst ÜBER die Zeilen und ist an einer einzelnen nicht sichtbar (N-441).
    zeilen: list[tuple[float, float]] = []

    strom_gemessen = waerme_gemessen = False
    for md in monatsdaten:
        d = md.verbrauch_daten or {}
        # E4d: Strom/Wärme gemessen — dieselbe Frage wie `imd_typ_beitrag` (die eine Lesetür).
        _b = imd_typ_beitrag(wp, d, md.source_provenance)
        strom_gemessen = strom_gemessen or _b.wp_strom_gemessen
        waerme_gemessen = waerme_gemessen or _b.wp_waerme_gemessen
        # **Gemessen schlägt abgeleitet**, je Monatszeile — über den SoT, nicht
        # über eine nachgebaute Weiche (F-56).
        _zeile = modus_strom_zeile(d)
        modus_gemessen = modus_gemessen or _zeile.gemessen
        modus_heizen += _zeile.heizen_kwh
        modus_kuehlen += _zeile.kuehlen_kwh
        modus_warmwasser += _zeile.warmwasser_kwh
        modus_lueften += _zeile.lueften_kwh
        modus_entfeuchten += _zeile.entfeuchten_kwh
        # R-C/N-398: die Mengen ohne Kennzahl — ueber den Layer-SoT, damit die
        # Aufloesung Geraetefeld-vor-Innengeraeten auch hier gilt (K2).
        _nutz = nutzenergie_ohne_kennzahl_kwh(d)
        nutz_lueften += _nutz.lueften_kwh
        nutz_entfeuchten += _nutz.entfeuchten_kwh
        # ⭐ **N-462: die Lage steht NICHT vor der Schleife.** E7/Option A fragt
        # „steckt der funktionsfremde Anteil im Nenner?", und das entscheidet
        # die **Stufe der Monatszeile** (K3), nicht das Kennzeichen des Geräts.
        _zeile_abzug = funktionsfremd_abzug_kwh(
            _zeile, hat_split=nenner_ist_feine_summe(d, wp.parameter),
        )
        abzug += _zeile_abzug
        # W-5: die Kältemenge — nur gemessen, nie abgeleitet.
        kaelte += betriebsart_nutzenergie_kwh(d, BM_KUEHLEN_W5) or 0.0
        _m_abdeckung = d.get(MODUS_ABDECKUNG_FELD, 0) or 0
        modus_abdeckung += _m_abdeckung
        if _m_abdeckung > 0 or _zeile.gemessen:
            modus_bezug += get_wp_strom_kwh(d, wp.parameter)
        # W-15: **dieselbe** Strom-Definition wie in den Monats-Fakten. Bei
        # getrennter Strommessung ist die Rohspalte etwas anderes (#183).
        _zeilen_strom = get_wp_strom_kwh(d, wp.parameter)
        strom += _zeilen_strom
        # ⚠ **Der EINZELwert, nicht die Wärme des Geräts** (N-391): Er trägt die
        # Kachel *Heizwärme* und den Zähler der Heiz-Arbeitszahl.
        heizung += heizwaerme_kwh(d) or 0
        # N-379: die eine Lesetuer statt des Rohzugriffs.
        _ww = get_wp_warmwasser_kwh(d, wp.parameter)
        warmwasser += _ww
        # Anwesenheit statt Menge — eine gepflegte 0 ist eine Messung.
        ww_je_erfasst = ww_je_erfasst or hat_wp_warmwasser_wert(d, wp.parameter)
        waerme_abgeleitet = waerme_abgeleitet or heizwaerme_ist_abgeleitet(
            md.source_provenance,
        )
        # ⭐ **Die Zeile liest ihre Wärme wie der Layer (N-441, Fall K)** — mit
        # dem kanonischen Vorrang „Gesamtwert vor Summanden" (D1).
        _md_waerme = waerme_gesamt_kwh(
            d.get('waerme_kwh'), heizwaerme_kwh(d), _ww,
        )
        zeilen.append((_md_waerme, _zeilen_strom))
        # N-643/N-644: dieselben vier Werte, die oben in die Summen gehen — je Zeile, ungerundet.
        monatsreihe.append({
            'jahr': md.jahr, 'monat': md.monat,
            'strom_kwh': float(_zeilen_strom),
            'heizung_kwh': float(heizwaerme_kwh(d) or 0.0),
            'warmwasser_kwh': float(_ww),
            'waerme_kwh': float(_md_waerme),
        })
        # P12: dieselbe Rechnung wie die Gesamtzahl, nur je Zeile.
        # `waerme_abgeleitet` wird **je Monat** gefragt (nicht die kumulierte
        # Marke): ein einzelner abgeleiteter Monat darf die übrigen nicht
        # entwerten, und ein gemessener nicht von einem abgeleiteten profitieren.
        _md_az = arbeitszahl(
            _md_waerme, _zeilen_strom,
            waerme_abgeleitet_kwh=(
                1.0 if heizwaerme_ist_abgeleitet(md.source_provenance) else 0.0
            ),
            strom_funktionsfremd_kwh=_zeile_abzug,
            abgrenzung_verletzt=GRUND_JE_ABGRENZUNG.get(_stoerung or ""),
        )
        _md_az_funktion = arbeitszahl_je_funktion(
            heizung_kwh=heizwaerme_kwh(d),
            strom_heizen_kwh=d.get('strom_heizen_kwh'),
            # N-379: `None` NUR, wenn das Geraet die Groesse nicht hat.
            warmwasser_kwh=(
                d.get('warmwasser_kwh') if hat_warmwasser else None
            ),
            strom_warmwasser_kwh=d.get('strom_warmwasser_kwh'),
            # Je Zeile gefragt, nicht am Gerät: Die getrennte Strommessung kann
            # mitten in der Historie eingeschaltet worden sein.
            hat_split='strom_heizen_kwh' in d,
            # N-391, ebenfalls je Zeile: EIN gemeinsamer Wärmemengenzähler
            # liefert keine Wärme je Funktion.
            waerme_ist_gesamt=bool(d.get('waerme_kwh')),
            waerme_abgeleitet_kwh=(
                1.0 if heizwaerme_ist_abgeleitet(md.source_provenance) else 0.0
            ),
            abgrenzung_verletzt=GRUND_JE_ABGRENZUNG.get(_stoerung or ""),
            # **R-1 auch je Monatszeile** (WK-16h). Die Achsen hängen am GERÄT,
            # nicht an der Zeile — anders als `hat_split` daneben, das mitten
            # in der Historie umspringen kann. Ohne sie zeigte der
            # Saison-Vergleich einer Brauchwasser-WP eine „Heiz"-Arbeitszahl.
            achsen=_achsen,
            gesamt=_md_az,
        )
        jaz_je_monat.append({
            'jahr': md.jahr, 'monat': md.monat,
            'wert': round(_md_az.wert, 2) if _md_az.wert is not None else None,
            'grund': _md_az.grund,
            'zaehler_kwh': _md_az.zaehler_kwh,
            'nenner_kwh': _md_az.nenner_kwh,
            # Getrennte Strommessung (#191): der Saison-Zweig vergleicht dann die
            # Heiz-Arbeitszahl, nicht die Gesamtzahl.
            'heizen_zaehler_kwh': _md_az_funktion.heizen.zaehler_kwh,
            'heizen_nenner_kwh': _md_az_funktion.heizen.nenner_kwh,
            # B3/H-1b: der Stromverbrauch des Monats nach dem SoT.
            'strom_kwh': round(_zeilen_strom, 1),
        })
        # ⚠ `strom_heizen_kwh` heißt hier **getrennte Strommessung** (zwei
        # physische Zähler), NICHT der Modus-Split von #263 K-2.
        if 'strom_heizen_kwh' in d:
            hat_getrennte_strom = True
            strom_heizen += d.get('strom_heizen_kwh', 0)
            strom_warmwasser += d.get('strom_warmwasser_kwh', 0)
            # ⚠ Die EINZELwerte, nicht die Wärme des Monats (N-391).
            heizung_getrennt += heizwaerme_kwh(d) or 0
            warmwasser_getrennt += _ww
            waerme_ist_gesamt_getrennt = (
                waerme_ist_gesamt_getrennt or bool(d.get('waerme_kwh'))
            )

    # ⭐ **N-391/V-1: die SUMME liest wie die Zeile** (D1).
    waerme = sum(w for w, _ in zeilen)

    mengen = GeraetMengen(
        inv_id=wp.id,
        name=wp.bezeichnung,
        strom_kwh=strom,
        waerme_kwh=waerme,
        heizung_kwh=heizung,
        warmwasser_kwh=warmwasser,
        strom_heizen_kwh=strom_heizen,
        strom_warmwasser_kwh=strom_warmwasser,
        heizung_getrennt_kwh=heizung_getrennt,
        warmwasser_getrennt_kwh=warmwasser_getrennt,
        hat_getrennte_strommessung=hat_getrennte_strom,
        waerme_ist_gesamt_getrennt=waerme_ist_gesamt_getrennt,
        kaelte_kwh=kaelte,
        modus_strom_kuehlen_kwh=modus_kuehlen,
        funktionsfremd_abzug_kwh=abzug,
        waerme_abgeleitet=waerme_abgeleitet,
        perioden_versetzt=(
            any(w > 0 and e == 0 for w, e in zeilen)
            and any(e > 0 for _, e in zeilen)
        ),
        abgrenzung_stoerung=_stoerung,
        hat_warmwasser_groesse=hat_warmwasser,
        waerme_achsen=_achsen,
        strom_gemessen=strom_gemessen,
        waerme_gemessen=waerme_gemessen,
    )
    f = GeraetFaltung(
        modus_heizen_kwh=modus_heizen,
        modus_kuehlen_kwh=modus_kuehlen,
        modus_warmwasser_kwh=modus_warmwasser,
        modus_lueften_kwh=modus_lueften,
        modus_entfeuchten_kwh=modus_entfeuchten,
        nutzenergie_lueften_kwh=nutz_lueften,
        nutzenergie_entfeuchten_kwh=nutz_entfeuchten,
        modus_abdeckung_h=modus_abdeckung,
        modus_bezug_kwh=modus_bezug,
        modus_gemessen=modus_gemessen,
        warmwasser_je_erfasst=ww_je_erfasst,
        jaz_je_monat=jaz_je_monat,
        monatsreihe=monatsreihe,
    )
    return mengen, f


def mengen_aus_tageswerten(
    wp: Investition,
    *,
    strom_kwh: float,
    waerme_kwh: float,
    heizung_kwh: float,
    warmwasser_kwh: float,
    strom_heizen_kwh: float,
    strom_warmwasser_kwh: float,
    kaelte_kwh: float,
    modus_strom_kuehlen_kwh: float,
    funktionsfremd_abzug_kwh: float,
    waerme_ist_gesamt: bool,
    strom_gemessen: bool = False,
    waerme_gemessen: bool = False,
) -> GeraetMengen:
    """Die Mengen **eines Tages** je Gerät — die zweite Herkunft (s. Modulkopf).

    ⚠ **Die Wärme ist am Tag immer gemessen.** Nur ein zugeordneter
    Wärmemengenzähler erreicht den Tagespfad; den abgeleiteten Zweig
    (``Strom × JAZ``) gibt es dort nicht. ``waerme_abgeleitet`` bleibt deshalb
    ``False`` — dieselbe Begründung, die schon an ``wp_jaz_tag`` steht.

    ⚠ **``perioden_versetzt`` bleibt ``False`` und ist keine Lücke:** Ein Tag
    ist EINE Periode; die Lage entsteht erst über mehrere (N-441).

    ⛔ **Der Riegel ``hat_split`` ist das Kennzeichen am Gerät**
    (``getrennte_strommessung``) — nicht „der Tag trägt zufällig beide
    Stromfelder". Ohne das Kennzeichen bedeutet ``strom_heizen_kwh`` etwas
    anderes (K3), und die Funktions-Arbeitszahl hätte einen Nenner, der keine
    Funktions-Messung ist. Dieselbe Quelle wie im Monat.
    """
    hat_split = bool((wp.parameter or {}).get("getrennte_strommessung"))
    return GeraetMengen(
        inv_id=wp.id,
        name=wp.bezeichnung,
        strom_kwh=strom_kwh,
        waerme_kwh=waerme_kwh,
        heizung_kwh=heizung_kwh,
        warmwasser_kwh=warmwasser_kwh,
        strom_heizen_kwh=strom_heizen_kwh if hat_split else 0.0,
        strom_warmwasser_kwh=strom_warmwasser_kwh if hat_split else 0.0,
        heizung_getrennt_kwh=heizung_kwh if hat_split else 0.0,
        warmwasser_getrennt_kwh=warmwasser_kwh if hat_split else 0.0,
        hat_getrennte_strommessung=hat_split,
        waerme_ist_gesamt_getrennt=waerme_ist_gesamt and hat_split,
        kaelte_kwh=kaelte_kwh,
        modus_strom_kuehlen_kwh=modus_strom_kuehlen_kwh,
        funktionsfremd_abzug_kwh=funktionsfremd_abzug_kwh,
        waerme_abgeleitet=False,
        perioden_versetzt=False,
        abgrenzung_stoerung=abgrenzung_stoerung(wp),
        hat_warmwasser_groesse=groesse_gibt_es_am_geraet(
            "waermepumpe", "warmwasser_kwh", wp.parameter,
        ),
        waerme_achsen=wp_waerme_achsen(wp.parameter),
        strom_gemessen=strom_gemessen,
        waerme_gemessen=waerme_gemessen,
    )


def kennzahlen_aus_monatszeilen(
    wp: Investition, monatsdaten: Sequence[Any],
) -> tuple[GeraetKennzahlen, GeraetFaltung]:
    """{@link mengen_aus_monatszeilen} + {@link kennzahlen_aus_mengen} in einem Griff."""
    mengen, faltung = mengen_aus_monatszeilen(wp, monatsdaten)
    return kennzahlen_aus_mengen(mengen), faltung


async def lade_kennzahlen_je_geraet(
    db: AsyncSession,
    anlage_id: int,
    waermepumpen: Iterable[Investition],
    *,
    von: Optional[tuple[int, int]] = None,
    bis: Optional[tuple[int, int]] = None,
) -> list[GeraetKennzahlen]:
    """Die Kennzahlen **je Gerät** für einen Monatsbereich — für Cockpit Monat/Jahr.

    ⚠ **P10/``P10_PER_INVESTITION``: hier werden ``InvestitionMonatsdaten``
    selbst geladen, und das ist die richtige Kategorie.** Die Monats-Fakten
    (``services/monats_fakten/``) liefern die **anlagenweite** Zeile; eine
    Kennzahl JE GERÄT lässt sich daraus strukturell nicht ablesen — genau die
    Begründung, mit der ``get_waermepumpe_dashboard`` und
    ``get_hub_leer_grund`` seit jeher in dieser Liste stehen. Die Zeitfilter
    (aktiv · Anschaffung · Stilllegung) gelten unverändert: ``von``/``bis``
    schneiden den Bereich, ``ist_aktiv_im_monat`` das Gerät.

    Args:
        von, bis: ``(jahr, monat)`` einschließlich. ``None`` ⇒ ganze Laufzeit.
    """
    wps = list(waermepumpen)
    if not wps:
        return []
    ids = [w.id for w in wps]
    zeilen = (await db.execute(
        select(InvestitionMonatsdaten).where(
            InvestitionMonatsdaten.investition_id.in_(ids),
        )
    )).scalars().all()

    def _im_bereich(md: Any) -> bool:
        schluessel = (md.jahr, md.monat)
        if von is not None and schluessel < von:
            return False
        if bis is not None and schluessel > bis:
            return False
        return True

    je_inv: dict[int, list[Any]] = {w.id: [] for w in wps}
    for md in zeilen:
        if not _im_bereich(md):
            continue
        je_inv.setdefault(md.investition_id, []).append(md)

    ergebnis: list[GeraetKennzahlen] = []
    for wp in wps:
        rows = [
            md for md in sorted(je_inv.get(wp.id, []), key=lambda m: (m.jahr, m.monat))
            if wp.ist_aktiv_im_monat(md.jahr, md.monat)
        ]
        mengen, _ = mengen_aus_monatszeilen(wp, rows)
        ergebnis.append(kennzahlen_aus_mengen(mengen))
    return ergebnis
