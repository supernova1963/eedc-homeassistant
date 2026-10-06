"""Der Wärme/Klima-Verlauf je Tag — die Reihe hinter *Cockpit → Monat*.

**Was hier entsteht** (Konzept Wärme/Klima §8, Bauschnitt 4): je Tag eines
Zeitraums die drei Größen, die der Verlauf zeigt —

* **Strom, nach Betriebsart gestapelt** (beide Zweige, ``falte_tages_stapel``),
* **gemessene Wärme** als Linie,
* das **Tagesmittel der Außentemperatur** als zweite Achse.

⭐ **Es ist derselbe Stapel wie in Cockpit → Tag, nicht ein zweiter.** Die
Zusammenführung der beiden Zweige (gemessene Betriebsart-Zähler schlagen den aus
dem Betriebsmodus abgeleiteten Split, je Gerät — SOLL §6.1/F4, Invariante K2)
liegt seit dem 10.09.2026 im Layer und wird hier **gerufen**, nicht nachgebaut.
Ohne das hätte eine Anlage mit Betriebsart-Zählern im Monat einen anderen Stapel
gezeigt als in Tag und Jahr daneben — die S1-Verletzung (*dieselbe Größe, überall
derselbe Wert*).

⚠ **Die Grundmenge des Stapels ist nicht der Wärmepumpen-Strom.** Sie ist die Σ
der Bezugsmengen der Geräte **mit** Aufteilung (``bezug_kwh``), und sie kommt aus
dem **Zählerpfad** (``TagesZusammenfassung.komponenten_kwh``) — nicht aus der
Stundensumme des Leistungspfads. Beide weichen ab, und genau daran hängt
**W-17b**: dietmar1968 sah 30 kWh Balken unter einer 284-kWh-Kachel. Der Verlauf
nennt die Differenz mit derselben Zeile wie der Balken darunter, statt eine
zweite Antwort zu erfinden.

⛔ **Gezeichnet wird nur GEMESSENE Wärme** (SOLL §3.3/S4). Auf Tagesebene ist das
ohnehin die einzige, die es gibt: Die abgeleitete Wärme entsteht aus
``Strom × Arbeitszahl`` an den **Monatszeilen** (``imd_monatsaggregat``), und die
kennt der Tag nicht. Ein Tag ohne Wärmemengenzähler trägt hier deshalb **nichts**
— eine Lücke in der Linie, keine Null.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import TYPE_CHECKING, Optional

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.berechnungen import waermepumpe_kwh_je_investition
from backend.core.berechnungen.tages_stapel import (
    TagesStapel,
    beitraege_des_tages,
    falte_tages_stapel,
)
from backend.core.berechnungen.waermepumpe_kennzahl import waerme_gesamt_je_geraet
from backend.models.tages_energie_profil import TagesZusammenfassung
from backend.services.energie_profil.modus_split_monat import lade_modus_split_je_tag
from backend.services.mitteltemperatur import lade_tagesmittel_temperatur
from backend.services.snapshot.aggregator import (
    TAGESDETAIL_AUSGABE,
    WAERME_AUSGABE_KEYS,
    get_betriebsart_strom_tageswerte,
    get_wp_strom_stufe_je_investition,
)
from backend.services.snapshot.bereichs_leser import lade_tageswerte_je_geraet

#: N-391: der gemeinsame Wärmemengenzähler. Er steht bewusst NICHT in
#: `WAERME_AUSGABE_KEYS` (dort wird summiert), wird aber je Tag mitgelesen —
#: die Auflösung unten ist die Vorrangregel D1, nicht eine zweite Summe.
_WAERME_GESAMT_KEY = "wp_waerme_kwh"
#: Die Wärme-Felder, die der Verlauf als Linie zeichnet — ein **Ausschnitt** aus
#: der einen Feldtabelle, keine zweite Liste.
#:
#: ⛔ Hier stand bis 11.09.2026 „Bauschnitt 6 erweitert … diese Menge". Das war
#: falsch: Kälte ist eine **eigene Rolle** (Konzept §8) und bekommt ihren
#: eigenen Ausschnitt darunter — in dieser Menge flösse sie in die Wärme-Linie.
_WAERME_FELDER = {
    schluessel: key
    for schluessel, key in TAGESDETAIL_AUSGABE.items()
    if key in WAERME_AUSGABE_KEYS or key == _WAERME_GESAMT_KEY
}
#: Die Kälte (Bauschnitt 6b) — Gerätefeld oder Σ Innengeräte, dieselbe Regel
#: wie im Tagespfad (der Bereichs-Leser löst den Suffix seit 6a auf).
_KAELTE_KEY = "wp_kaelte_kwh"
_KAELTE_FELDER = {
    schluessel: key
    for schluessel, key in TAGESDETAIL_AUSGABE.items()
    if key == _KAELTE_KEY
}
#: Die **Summanden**-Achsen (WK-16c) — derselbe Ausschnitt aus derselben
#: Feldtabelle wie oben, nur für die Verteilungs-Sicht. Sie stehen bewusst
#: NICHT in `_WAERME_FELDER`: das ist Strom, keine Nutzenergie, und die
#: Wärme-Linie dürfte ihn niemals mitzeichnen.
_ACHSEN_FELDER = {
    schluessel: key
    for schluessel, key in TAGESDETAIL_AUSGABE.items()
    if key in ("wp_strom_heizen_kwh", "wp_strom_warmwasser_kwh")
}

if TYPE_CHECKING:  # pragma: no cover — nur für die Signatur unten
    from backend.core.berechnungen.waerme_verteilung import GeraetStromEingabe


@dataclass(frozen=True)
class WaermeVerlaufTag:
    """Eine Tageszeile des Verlaufs."""

    datum: date
    stapel: TagesStapel
    #: Σ der **gemessenen** Wärme des Tages (Heizung + Warmwasser), oder
    #: ``None``: keine Aussage, keine 0.
    waerme_kwh: Optional[float]
    #: Die **gemessene Kälte** des Tages, oder ``None``. Nie Teil der Wärme.
    kaelte_kwh: Optional[float]
    #: Tagesmittel der Außentemperatur (°C), oder ``None``.
    temperatur_c: Optional[float]
    #: Der gesamte Wärmepumpen-Strom des Tages aus dem **Zählerpfad** — der
    #: Bezug für die Zeile „Aufgeteilte Menge X von Y kWh".
    strom_kwh: Optional[float]


async def lade_waerme_verlauf(
    db: AsyncSession,
    anlage,
    investitionen_by_id: dict,
    von: date,
    bis: date,
) -> list[WaermeVerlaufTag]:
    """Die Tagesreihe für ``[von, bis]`` (einschließlich), aufsteigend.

    **Vier Bereichs-Abfragen statt einer Schleife über Tage:** Modus-Split
    (zwei Queries), Zählerstrom je Tag, Temperatur, und je Wärmefeld eine
    Standreihe. Ein Tag, der nichts beiträgt, fehlt in der Liste — der Aufrufer
    entscheidet, ob er ihn als Lücke zeichnet.
    """
    splits_je_tag = await lade_modus_split_je_tag(db, anlage.id, von=von, bis=bis)
    zaehler_je_tag, rueckwaerts_tage = await _zaehlerstrom_je_tag(
        db, anlage.id, von, bis,
    )
    # N-435: die Wärme je Tag im Fenster derselben Tageszeile — sonst nennte die
    # Monatssäule eine andere Wärme als *Cockpit → Tag* für denselben Tag.
    # Bauschnitt 6b: Wärme UND Kälte in EINEM Satz Bereichsabfragen — dasselbe
    # Fenster je Tag. Getrennt wird danach nach Key, nie über die Summe.
    # N-391b: **je Gerät** geladen, nicht als Anlagensumme — D1 unten ist eine
    # Regel je Gerätezeile, und über den Summen verschlänge der Gesamtzähler
    # EINER Wärmepumpe die Aufteilung aller anderen.
    nutzenergie_je_tag = await lade_tageswerte_je_geraet(
        db, anlage, investitionen_by_id, von, bis,
        {**_WAERME_FELDER, **_KAELTE_FELDER},
        rueckwaerts_tage=rueckwaerts_tage,
    )
    temperatur_je_tag = await lade_tagesmittel_temperatur(db, anlage.id, von, bis)
    # N-462: Welche K3-Stufe trägt der Bezug je Gerät? Sie hängt an der
    # **Zuordnung**, nicht am Tag — deshalb einmal vor der Schleife, nicht
    # 28–31 mal darin (SOLL-§9-E7/Option A: „abgezogen wird nur, was im Nenner
    # steht" — und was im Nenner steht, entscheidet K3).
    stufe_je_inv = await get_wp_strom_stufe_je_investition(
        db, anlage, investitionen_by_id,
    )

    # ⚠ Zweig 1 (gemessene Betriebsart-Zähler) ist selbst snapshot-basiert und
    # hat heute nur einen Tages-Einstieg. Er wird deshalb je Tag gerufen — aber
    # **nur für Tage, die überhaupt eine Zeile haben**, statt für jeden
    # Kalendertag des Monats.
    tage = sorted(
        set(splits_je_tag) | set(zaehler_je_tag) | set(nutzenergie_je_tag)
    )

    zeilen: list[WaermeVerlaufTag] = []
    for tag in tage:
        if not (von <= tag <= bis):
            continue
        # N-434: dasselbe Fenster wie der Bezug dieses Tages — die Herkunft der
        # Tageszeile entscheidet, nicht eine Voreinstellung.
        gemessen_je_inv = await get_betriebsart_strom_tageswerte(
            db, anlage, investitionen_by_id, tag,
            rueckwaerts=tag in rueckwaerts_tage,
        )
        zaehler = zaehler_je_tag.get(tag, {})
        stapel = falte_tages_stapel(
            gemessen_je_inv,
            zaehler,
            splits_je_tag.get(tag, {}),
            investitionen_by_id,
            tag,
            stufe_je_inv=stufe_je_inv,
        )
        werte = nutzenergie_je_tag.get(tag, {})
        # ⛔ Nie `sum(werte.values())` — seit 6b steht dort auch die Kälte.
        # N-391/D1: **Gesamtwert vor Summanden.** Trägt der gemeinsame
        # Wärmemengenzähler den Tag, ist er die Wärme; sonst ist sie die Summe
        # ihrer beiden Achsen. Ihn einfach in `WAERME_AUSGABE_KEYS` zu legen
        # hieße, ihn zur Aufteilung zu ADDIEREN — dieselbe Wärme zweimal.
        #
        # ⛔ **N-391b: die Vorrangfrage steht je GERÄT.** Bis zum 14.09.2026
        # stand sie hier auf der Anlagensumme — bei zwei verschieden zählenden
        # Wärmepumpen (30 Gesamt · 20 + 5 aufgeteilt) nannte die Tagesliste
        # deshalb **30**, während der Monat für denselben Bestand **55** sagt.
        # Die Aufteilung des zweiten Geräts verschwand ohne jeden Hinweis
        # (ADR-002/P4).
        waerme_je_geraet = waerme_gesamt_je_geraet(
            werte.get(_WAERME_GESAMT_KEY),
            *(werte.get(k) for k in sorted(WAERME_AUSGABE_KEYS)),
        )
        waerme = sum(waerme_je_geraet.values()) if waerme_je_geraet else None
        _kaelte_je_geraet = werte.get(_KAELTE_KEY)
        kaelte = sum(_kaelte_je_geraet.values()) if _kaelte_je_geraet else None
        strom = sum(zaehler.values()) if zaehler else None
        if stapel.ist_leer and waerme is None and kaelte is None:
            # Ein Tag ohne Aufteilung und ohne gemessene Wärme hat für den
            # Verlauf nichts zu sagen (ADR-002/P4) — die Temperatur allein
            # macht keine Zeile.
            continue
        zeilen.append(WaermeVerlaufTag(
            datum=tag,
            stapel=stapel,
            waerme_kwh=round(waerme, 2) if waerme else None,
            kaelte_kwh=round(kaelte, 2) if kaelte else None,
            temperatur_c=temperatur_je_tag.get(tag),
            strom_kwh=round(strom, 2) if strom else None,
        ))
    return zeilen


async def lade_waerme_verlauf_beitraege(
    db: AsyncSession,
    anlage,
    investitionen_by_id: dict,
    von: date,
    bis: date,
) -> dict[date, dict[str, "GeraetStromEingabe"]]:
    """Je Tag und **je Gerät** die Eingabe der Verteilungs-Sicht (WK-16c).

    ⭐ **Dieselben Eingänge wie {@link lade_waerme_verlauf}, eine Stufe früher
    abgegriffen.** Jene Funktion faltet die Beiträge zum anlagenweiten
    ``TagesStapel``; die Verteilung braucht sie **je Gerät**, weil ein Segment
    dort *Gerät × Funktion* ist („WP Heizen" neben „Klima Heizen"). Beide lesen
    denselben Zählerpfad, denselben Zeitfilter und dieselbe K3-Stufe — es gibt
    keinen zweiten Weg zu diesen Zahlen.

    ⚠ **Die Summanden-Achsen kommen aus demselben Bereichs-Leser** wie die
    Wärme (``lade_tageswerte_je_geraet``) und damit im **Fenster der jeweiligen
    Tageszeile** (N-434/N-435). Ohne das nennte die Tagessäule einen anderen
    Heizstrom als *Cockpit → Tag* für denselben Tag.

    Returns:
        ``{datum: {inv_id: GeraetStromEingabe}}``. Ein Tag ohne jede
        Wärmepumpen-Menge fehlt (P4: keine Reihe von Nullen).
    """
    from backend.services.waerme_verteilung import eingabe_aus_tageswerten

    splits_je_tag = await lade_modus_split_je_tag(db, anlage.id, von=von, bis=bis)
    zaehler_je_tag, rueckwaerts_tage = await _zaehlerstrom_je_tag(
        db, anlage.id, von, bis,
    )
    achsen_je_tag = await lade_tageswerte_je_geraet(
        db, anlage, investitionen_by_id, von, bis, _ACHSEN_FELDER,
        rueckwaerts_tage=rueckwaerts_tage,
    )
    stufe_je_inv = await get_wp_strom_stufe_je_investition(
        db, anlage, investitionen_by_id,
    )

    ergebnis: dict[date, dict[str, "GeraetStromEingabe"]] = {}
    for tag in sorted(set(splits_je_tag) | set(zaehler_je_tag)):
        if not (von <= tag <= bis):
            continue
        zaehler = zaehler_je_tag.get(tag, {})
        if not zaehler:
            continue
        gemessen_je_inv = await get_betriebsart_strom_tageswerte(
            db, anlage, investitionen_by_id, tag,
            rueckwaerts=tag in rueckwaerts_tage,
        )
        beitraege = {
            b.inv_id: b
            for b in beitraege_des_tages(
                gemessen_je_inv, zaehler, splits_je_tag.get(tag, {}),
                investitionen_by_id, tag, stufe_je_inv=stufe_je_inv,
            )
        }
        achsen = achsen_je_tag.get(tag, {})
        je_geraet: dict[str, "GeraetStromEingabe"] = {}
        for inv_id_str, menge in zaehler.items():
            inv = investitionen_by_id.get(inv_id_str)
            # #236/#239: Der Zeitfilter gehört auch hier hin — die Beiträge
            # oben tragen ihn schon, der Zählerpfad nicht.
            if inv is None or not inv.ist_aktiv_an(tag):
                continue
            je_geraet[inv_id_str] = eingabe_aus_tageswerten(
                inv,
                menge_kwh=float(menge or 0.0),
                strom_heizen_kwh=(
                    achsen.get("wp_strom_heizen_kwh", {}).get(inv_id_str)
                ),
                strom_warmwasser_kwh=(
                    achsen.get("wp_strom_warmwasser_kwh", {}).get(inv_id_str)
                ),
                beitrag=beitraege.get(inv_id_str),
            )
        if je_geraet:
            ergebnis[tag] = je_geraet
    return ergebnis


# ── Dieselbe Tagesreihe, aber je GERÄT über den Zeitraum summiert (N-472/A-5) ──


@dataclass(frozen=True)
class WaermeMonatsMengenJeGeraet:
    """Σ der Tagesgrößen **eines Geräts** über einen Zeitraum.

    ⭐ **Rohfelder, keine aufgelöste Größe.** Hier steht, was die Zähler des
    Geräts über die Tage hergegeben haben — die Vorrangregeln fallen wie bei
    jeder anderen Quelle beim Aufrufer (K3 in ``_wp_strom_k3``, D1 in
    ``_wp_waerme_d1``). Das ist Absicht: HA-Statistik, Connector und MQTT
    liefern ebenfalls Rohfelder je Monat, und eine Quelle, die ihre Größen
    schon aufgelöst abliefert, stünde als einzige neben der Kette.

    ⚠ **Σ über Tage, keine zweite Faltung.** Gefaltet wird feldweise und
    additiv; die *Formeln* bleiben im Layer. Dieselbe Begründung, unter der
    ``monats_aus_tagen.py`` seine Σ über die Stunden eines Monats bildet.
    """

    inv_id: str
    strom_kwh: float = 0.0
    waerme_kwh: float = 0.0
    heizung_kwh: float = 0.0
    warmwasser_kwh: float = 0.0
    strom_heizen_kwh: float = 0.0
    strom_warmwasser_kwh: float = 0.0
    kaelte_kwh: float = 0.0
    modus_strom_kuehlen_kwh: float = 0.0
    funktionsfremd_abzug_kwh: float = 0.0
    #: HA-Bauform E4d (Bauplan §8a, Rest N-585): die Felder, für die mindestens ein Tag einen Wert trug — auch 0.
    #: Die Mengen darüber sind ``float`` mit 0-Default; eine gemessene 0 und „kein Zähler" sähen dort gleich aus.
    gemessen: frozenset[str] = frozenset()


#: Die Strom-Achsen je Funktion — dieselbe Ausgabe-Tabelle, anderer Ausschnitt.
_STROM_FELDER = {
    schluessel: key
    for schluessel, key in TAGESDETAIL_AUSGABE.items()
    if key in ("wp_strom_heizen_kwh", "wp_strom_warmwasser_kwh")
}


async def lade_waerme_monatsmengen_je_geraet(
    db: AsyncSession,
    anlage,
    investitionen_by_id: dict,
    von: date,
    bis: date,
) -> tuple[dict[str, WaermeMonatsMengenJeGeraet], Optional[date], Optional[date]]:
    """Die Wärme/Klima-Mengen je Gerät aus der **lokalen Tagesebene** (N-472/A-5).

    ⛔ **Derselbe Leser wie der Verlauf daneben, und das ist der ganze Punkt.**
    Der Anlass war, dass *Cockpit → Monat* leere Wärme/Klima-Kacheln über einem
    Verlauf zeigte, der dieselben Tage vollständig zeichnete. Eine zweite Quelle
    hätte zwei Zahlen erzeugt, wo eine gefragt war — deshalb ruft diese Funktion
    exakt die Leser von {@link lade_waerme_verlauf}:

    * ``_zaehlerstrom_je_tag`` (Zählerpfad, ``komponenten_kwh``) für den
      **Gesamtstrom** je Gerät — dieselbe Quelle, aus der *Cockpit → Tag* seine
      Kachel speist (``wp_strom_je_inv``),
    * ``lade_tageswerte_je_geraet`` für Wärme, Kälte und die Funktions-Achsen,
    * ``get_betriebsart_strom_tageswerte`` + ``beitraege_des_tages`` für den
      Kühlanteil und den Nenner-Abzug (**E7/Option A**, je Gerät).

    ⚠ **Nur die Mengen, keine Kennzahl.** Die drei Layer-Aufrufe bleiben bei
    ``kennzahlen_aus_mengen``; diese Funktion füllt deren Eingang.

    Returns:
        ``({inv_id: Mengen}, erster_tag, letzter_tag)`` — die beiden Ränder für
        die Abdeckungs-Angabe der Quelle (P4). Ohne Tagesspur: ``({}, None, None)``.
    """
    from backend.core.berechnungen.tages_stapel import (
        beitrag_abzug_kwh,
        beitraege_des_tages,
    )

    zaehler_je_tag, rueckwaerts_tage = await _zaehlerstrom_je_tag(db, anlage.id, von, bis)
    werte_je_tag = await lade_tageswerte_je_geraet(
        db, anlage, investitionen_by_id, von, bis,
        {**_WAERME_FELDER, **_KAELTE_FELDER, **_STROM_FELDER},
        rueckwaerts_tage=rueckwaerts_tage,
    )
    splits_je_tag = await lade_modus_split_je_tag(db, anlage.id, von=von, bis=bis)
    stufe_je_inv = await get_wp_strom_stufe_je_investition(
        db, anlage, investitionen_by_id,
    )

    tage = sorted(
        t for t in (set(zaehler_je_tag) | set(werte_je_tag) | set(splits_je_tag))
        if von <= t <= bis
    )
    if not tage:
        return {}, None, None

    roh: dict[str, dict[str, float]] = {}
    gemessen: dict[str, set[str]] = {}

    def _addiere(inv_id: str, feld: str, wert: Optional[float]) -> None:
        if wert is not None:
            gemessen.setdefault(inv_id, set()).add(feld)
            roh.setdefault(inv_id, {})
        if wert:
            roh.setdefault(inv_id, {})[feld] = roh.setdefault(inv_id, {}).get(feld, 0.0) + float(wert)

    for tag in tage:
        for inv_id, kwh in (zaehler_je_tag.get(tag) or {}).items():
            _addiere(inv_id, "strom_kwh", kwh)
        werte = werte_je_tag.get(tag) or {}
        for key, feld in (
            (_WAERME_GESAMT_KEY, "waerme_kwh"),
            ("wp_heizung_kwh", "heizung_kwh"),
            ("wp_warmwasser_kwh", "warmwasser_kwh"),
            ("wp_strom_heizen_kwh", "strom_heizen_kwh"),
            ("wp_strom_warmwasser_kwh", "strom_warmwasser_kwh"),
            (_KAELTE_KEY, "kaelte_kwh"),
        ):
            for inv_id, kwh in (werte.get(key) or {}).items():
                _addiere(inv_id, feld, kwh)
        # E7/Option A je Gerät — dieselbe Auswahl (K2, Zeitfilter) wie im Tag.
        gemessen_je_inv = await get_betriebsart_strom_tageswerte(
            db, anlage, investitionen_by_id, tag,
            rueckwaerts=tag in rueckwaerts_tage,
        )
        for b in beitraege_des_tages(
            gemessen_je_inv, zaehler_je_tag.get(tag, {}), splits_je_tag.get(tag, {}),
            investitionen_by_id, tag, stufe_je_inv=stufe_je_inv,
        ):
            _addiere(b.inv_id, "modus_strom_kuehlen_kwh", b.kuehlen_kwh)
            _addiere(b.inv_id, "funktionsfremd_abzug_kwh", beitrag_abzug_kwh(b))

    return (
        {
            inv_id: WaermeMonatsMengenJeGeraet(
                inv_id=inv_id, gemessen=frozenset(gemessen.get(inv_id, ())), **felder,
            )
            for inv_id, felder in roh.items()
        },
        tage[0],
        tage[-1],
    )


async def _zaehlerstrom_je_tag(
    db: AsyncSession, anlage_id: int, von: date, bis: date,
) -> tuple[dict[date, dict[str, float]], set[date]]:
    """Der Wärmepumpen-Tagesstrom je Gerät — und in welchem Fenster er steht.

    ⚠ **Hier stand bis 11.09.2026 „nicht die Stundensumme des Leistungspfads
    (``TagesBilanz.wp_strom_kwh``)"** — das war falsch benannt: ``waermepumpe_kw``
    kommt aus dem **Zählerpfad** im Rückwärts-Raster (``get_hourly_kwh_by_category``
    bzw. die LTS-Variante), nicht aus dem Leistungspfad. Der Unterschied zu
    ``komponenten_kwh`` ist das **Fenster** (und im Snapshot-Rückfall Lückenfüllung
    und Reset-Regel), nicht die Quelle. Die Wahl dieser Quelle bleibt richtig:
    Kachel und Aufteilung darunter rechnen mit ihr.

    ⛔ **N-434:** Im HA-Add-on ist ``komponenten_kwh`` Σ der 24 LTS-Slots, also
    [Vortag 23:00, 23:00). Deshalb meldet diese Funktion zusätzlich die Tage,
    deren Zeile dieses Fenster trägt — die Betriebsart-Zähler desselben Tages
    werden im selben Fenster gelesen.

    Returns:
        ``(je_tag, rueckwaerts_tage)``.
    """
    from backend.services.snapshot.boundary_range import tageszeile_ist_rueckwaerts

    result = await db.execute(
        select(
            TagesZusammenfassung.datum,
            TagesZusammenfassung.komponenten_kwh,
            TagesZusammenfassung.source_provenance,
            TagesZusammenfassung.verworfen,
        )
        .where(and_(
            TagesZusammenfassung.anlage_id == anlage_id,
            TagesZusammenfassung.datum >= von,
            TagesZusammenfassung.datum <= bis,
        ))
    )
    je_tag: dict[date, dict[str, float]] = {}
    rueckwaerts_tage: set[date] = set()
    for datum, komponenten, provenance, verworfen in result.all():
        if tageszeile_ist_rueckwaerts(provenance, verworfen):
            rueckwaerts_tage.add(datum)
        if komponenten:
            werte = waermepumpe_kwh_je_investition(komponenten)
            if werte:
                je_tag[datum] = werte
    return je_tag, rueckwaerts_tage
