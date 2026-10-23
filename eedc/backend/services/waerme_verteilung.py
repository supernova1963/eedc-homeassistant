"""Die Verteilung des Wärme/Klima-Stroms und ihr Verlauf (WK-16c).

**Was hier entsteht** — für *Cockpit → Tag · Monat · Jahr* dieselbe Antwort in
drei Auflösungen:

1. **Die Verteilung des Zeitraums** — der Strom je **Gerät und Funktion**, mit
   Anteil, Herkunft und **Kosten** (kWh × Tarif des Monats, ADR-002/**P8**).
2. **Der Verlauf dieser Verteilung** — dieselben Segmente je Periode (Stunden
   eines Tages · Tage eines Monats · Monate eines Jahres), dazu die
   **Ø-Außentemperatur** und, wo es sie gibt, ein **Wettersymbol**.

⭐ **Ein Antworttyp für alle drei Stufen.** Die Sicht wählt nur die Auflösung;
Segmentbildung, Kostenrechnung und Temperatur-Vorrangkette sind dieselben. Drei
Antworttypen wären drei Stellen, an denen dieselbe Regel driftet — die Klasse,
aus der W-3, W-15 und F-56 auf dieser Fläche entstanden sind.

## Woher die Zahlen kommen

===========  ==================================  ==============================
Sicht        Verteilung (Σ des Zeitraums)        Perioden
===========  ==================================  ==============================
**Jahr**     Σ der Monatszeilen                  Monate (dieselben Zeilen)
**Monat**    die Monatszeile                     Tage (Snapshot-Pfad)
**Tag**      die Tageswerte                      Stunden (Stundenform)
===========  ==================================  ==============================

⚠ **Bei Monat und Tag ist Σ der Perioden NICHT die Verteilung darüber — und das
ist richtig so.** Der Monat läuft vom Ersten 0 Uhr bis zum Letzten 24 Uhr, seine
Tagessäulen im Add-on von 23 Uhr bis 23 Uhr (Konzept Kap. 6.3); die Stunden
eines Tages tragen nur, was eine **Form** hat (der Rest wird genannt, nicht
verteilt — ADR-002/P4). Beide Differenzen stehen in der Antwort, statt still zu
bleiben. Beim **Jahr** sind es dieselben Zeilen, dort stimmt es auf die Stelle.

⛔ **Der Layer rechnet, dieser Dienst lädt.** Welche Funktion welche
Kilowattstunden bekommt, steht in ``core/berechnungen/waerme_verteilung.py``;
welche Menge ein Gerät hat, in ``core/field_definitions.py::wp_strom_aufteilung``
(Monatszeile) bzw. im Zählerpfad des Tages. Hier stehen nur die **Eingänge** —
dieselbe Arbeitsteilung wie in ``waermepumpe_kennzahlen_je_geraet.py``.
"""

from __future__ import annotations

import calendar
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date
from typing import Literal, Optional

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.berechnungen.betriebsart_gemessen import modus_strom_zeile, summanden_gelten
from backend.core.berechnungen.tages_stapel import STUNDEN, GeraeteBeitrag
from backend.core.berechnungen.waerme_verteilung import (
    FUNKTION_LABEL,
    FUNKTIONEN,
    GeraetStromEingabe,
    GeraetStromVerteilung,
    anteile_prozent,
    verteile_geraet_strom,
)
from backend.core.betriebsmodus import MODUS_ABDECKUNG_FELD
from backend.core.field_definitions import (
    get_wp_strom_kwh,
    wp_feine_summe_kwh,
    wp_nicht_aufgeteilt_kwh,
    wp_strom_aufteilung,
)
from backend.models.investition import Investition, InvestitionMonatsdaten
from backend.models.monatsdaten import Monatsdaten
from backend.models.tages_energie_profil import TagesEnergieProfil
from backend.services.mitteltemperatur import (
    lade_monatsmittel_temperatur,
    lade_tagesmittel_temperatur,
)
from backend.services.monats_fakten import lade_monats_fakten
from backend.services.wetter.utils import wetter_code_zu_symbol

Sicht = Literal["tag", "monat", "jahr"]
Stufe = Literal["stunde", "tag", "monat"]

#: Kurznamen der Monate auf der x-Achse — dieselbe Schreibweise wie im Client
#: (`MONAT_KURZ`). Sie steht hier, weil die **Beschriftung einer Periode** Teil
#: der Antwort ist: der Client soll eine Reihe zeichnen können, ohne zu wissen,
#: welche Stufe er gerade bekommen hat.
MONAT_KURZ: tuple[str, ...] = (
    "Jan", "Feb", "Mär", "Apr", "Mai", "Jun",
    "Jul", "Aug", "Sep", "Okt", "Nov", "Dez",
)


@dataclass(frozen=True)
class VerteilungSegment:
    """Ein Segment — **ein Gerät, eine Funktion** (Konzept Kap. 7/E1).

    ⚠ Die Kennzahl eines Geräts teilt sich mit keinem anderen; die **Menge**
    darf summiert werden. Deshalb steht hier eine Menge und keine Arbeitszahl.
    """

    #: ``"<investition_id>:<funktion>"`` — der Schlüssel, unter dem die Perioden
    #: ihre Werte tragen. Stabil über die ganze Antwort.
    schluessel: str
    funktion: str
    funktion_label: str
    geraet: str
    investition_id: int
    kwh: float
    #: Anteil an der **aufgeteilten** Menge (s. ``anteile_prozent``).
    anteil_prozent: float
    herkunft: str
    #: Der Arbeitspreis, mit dem gerechnet wurde (ct/kWh). Über mehrere Monate
    #: der **mengengewichtete** Mittelwert — damit ``kwh × preis = kosten`` auch
    #: im Jahr aufgeht (A6: eine Kennzahl zeigt, womit sie gerechnet hat).
    preis_cent: Optional[float]
    kosten_euro: Optional[float]


@dataclass(frozen=True)
class VerteilungPeriode:
    """Eine Periode des Verlaufs — Stunde, Tag oder Monat."""

    #: Maschinenlesbar (``"2026-06-15"``, ``"14"``, ``"6"``).
    schluessel: str
    #: Beschriftung der x-Achse.
    label: str
    #: ``{Segment-Schlüssel: kWh}`` — nur Segmente mit Menge. Eine Periode ohne
    #: Aufteilung trägt ein leeres Dict, **keine** Reihe von Nullen (P4).
    kwh_je_segment: dict[str, float]
    temperatur_c: Optional[float] = None
    #: Aus dem WMO-Code (``wetter_code_zu_symbol``). ``None``, wo kein Code
    #: vorliegt — **kein Symbol ist besser als ein erfundenes**.
    wetter_symbol: Optional[str] = None


@dataclass(frozen=True)
class VerteilungVerlauf:
    """Die ganze Antwort — Verteilung, Verlauf und die genannten Differenzen."""

    sicht: str
    stufe: str
    segmente: list[VerteilungSegment] = field(default_factory=list)
    perioden: list[VerteilungPeriode] = field(default_factory=list)
    #: Der **gesamte** Wärme/Klima-Strom des Zeitraums (K1) — auch der Geräte
    #: ohne Aufteilung.
    menge_kwh: float = 0.0
    #: Σ der Segmente. Die Differenz zu ``menge_kwh`` ist die Zeile
    #: *„Aufgeteilte Menge X von Y kWh"* (W-17b) — genannt, nicht verteilt.
    aufgeteilt_kwh: float = 0.0
    kosten_gesamt_euro: Optional[float] = None
    #: Σ **aller Perioden**. ⚠ Sie ist bei *Monat* und *Tag* nicht
    #: ``aufgeteilt_kwh``: die Tagessäulen kommen aus dem Snapshot-Pfad und
    #: kennen ein Gerät nicht, das nur monatlich gepflegt wird; die Stunden
    #: tragen nur, was eine Form hat. Der Client **nennt** die Differenz
    #: (*„Im Verlauf: X von Y kWh"*), statt sie hineinzurechnen — dieselbe
    #: Antwort, die der Balken seit W-17b auf dieselbe Frage gibt.
    verlauf_kwh: float = 0.0
    #: Nur die Stundenstufe: was sich keiner Stunde zuordnen ließ (P4).
    ohne_stundenform_kwh: Optional[float] = None


# ─────────────────────────────────────────────────────────────────────────────
# Einstieg
# ─────────────────────────────────────────────────────────────────────────────

async def lade_verteilung_verlauf(
    db: AsyncSession,
    anlage,
    *,
    sicht: Sicht,
    jahr: Optional[int] = None,
    monat: Optional[int] = None,
    datum: Optional[date] = None,
) -> VerteilungVerlauf:
    """Verteilung **und** Verlauf für eine der drei Cockpit-Sichten.

    Args:
        sicht: ``"jahr"`` (Perioden = Monate) · ``"monat"`` (= Tage) ·
            ``"tag"`` (= Stunden).
        jahr/monat/datum: der Zeitraum, je nach Sicht.
    """
    wps = await _wp_investitionen(db, anlage.id)
    if not wps:
        return VerteilungVerlauf(sicht=sicht, stufe=_stufe(sicht))

    if sicht == "jahr":
        return await _jahr(db, anlage, wps, int(jahr))
    if sicht == "monat":
        return await _monat(db, anlage, wps, int(jahr), int(monat))
    return await _tag(db, anlage, wps, datum or date.today())


def _stufe(sicht: str) -> Stufe:
    return {"jahr": "monat", "monat": "tag", "tag": "stunde"}[sicht]  # type: ignore[return-value]


async def _wp_investitionen(db: AsyncSession, anlage_id: int) -> list[Investition]:
    """Die Wärme/Klima-Geräte der Anlage — **ohne** Zeitfilter.

    Gefiltert wird je Periode (``ist_aktiv_im_monat``/``ist_aktiv_an``): Ein
    Gerät, das im März stillgelegt wurde, gehört in den Januar-Balken und nicht
    in den Dezember (Konzept: Anschaffungs-/Stilllegungsdatum sind die Grenze).
    """
    result = await db.execute(
        select(Investition).where(
            Investition.anlage_id == anlage_id,
            Investition.typ == "waermepumpe",
        )
    )
    return list(result.scalars().all())


# ─────────────────────────────────────────────────────────────────────────────
# Der gemeinsame Zusammenbau
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class _Sammler:
    """Sammelt Segmente über Geräte und Perioden — die eine Zusammenbau-Stelle.

    ⭐ Verteilung und Verlauf entstehen aus **demselben** Strom von Beiträgen:
    Jeder Beitrag geht in die Periode *und* in die Summe. So kann die eine Zahl
    nicht von der anderen abweichen, ohne dass ein Beitrag fehlt.
    """

    #: ``{schluessel: kWh}`` der Verteilung.
    summe: dict[str, float] = field(default_factory=lambda: defaultdict(float))
    #: ``{schluessel: €}`` — je Periode mit **ihrem** Monatspreis gerechnet (P8).
    kosten: dict[str, float] = field(default_factory=lambda: defaultdict(float))
    #: ``{schluessel: (funktion, geraet, inv_id, herkunft)}``
    stamm: dict[str, tuple[str, str, int, str]] = field(default_factory=dict)
    menge_kwh: float = 0.0
    hat_preis: bool = False

    def nimm(
        self,
        inv: Investition,
        v: GeraetStromVerteilung,
        *,
        preis_cent: Optional[float],
        in_summe: bool = True,
    ) -> dict[str, float]:
        """Verbucht die Verteilung **eines** Geräts; liefert ihre Segment-Werte."""
        werte: dict[str, float] = {}
        for funktion, kwh in v.je_funktion.items():
            schluessel = f"{inv.id}:{funktion}"
            werte[schluessel] = kwh
            self.stamm.setdefault(
                schluessel,
                (
                    funktion,
                    inv.bezeichnung or f"Gerät {inv.id}",
                    int(inv.id),
                    v.herkunft_je_funktion.get(funktion, ""),
                ),
            )
            if in_summe:
                self.summe[schluessel] += kwh
                if preis_cent is not None:
                    self.hat_preis = True
                    self.kosten[schluessel] += kwh * preis_cent / 100.0
        if in_summe:
            self.menge_kwh += v.menge_kwh
        return werte

    def segmente(self) -> list[VerteilungSegment]:
        anteile = anteile_prozent(self.summe)
        zeilen: list[VerteilungSegment] = []
        for schluessel, (funktion, geraet, inv_id, herkunft) in self.stamm.items():
            kwh = self.summe.get(schluessel, 0.0)
            kosten = self.kosten.get(schluessel) if self.hat_preis else None
            zeilen.append(VerteilungSegment(
                schluessel=schluessel,
                funktion=funktion,
                funktion_label=FUNKTION_LABEL.get(funktion, funktion),
                geraet=geraet,
                investition_id=inv_id,
                kwh=round(kwh, 2),
                anteil_prozent=round(anteile.get(schluessel, 0.0), 1),
                herkunft=herkunft,
                # Der **gewichtete** Preis: über mehrere Monate ist „der Tarif"
                # keine einzelne Zahl mehr, und ein herausgegriffener Monat
                # wäre eine Behauptung über die anderen elf (P8).
                preis_cent=(
                    round(kosten / kwh * 100.0, 2)
                    if (kosten is not None and kwh > 0) else None
                ),
                kosten_euro=round(kosten, 2) if kosten is not None else None,
            ))
        # Kanonische Reihenfolge: Gerät (nach ID, wie sonst auch), darin die
        # Funktionen in ihrer festen Ordnung — nicht nach Größe. Eine Sortierung
        # nach Menge ließe die Segmente zwischen zwei Zeiträumen die Plätze
        # tauschen, und die Farbe folgt der Rolle, nicht dem Rang.
        zeilen.sort(key=lambda z: (z.investition_id, FUNKTIONEN.index(z.funktion)))
        return zeilen

    def kosten_gesamt(self) -> Optional[float]:
        if not self.hat_preis:
            return None
        return round(sum(self.kosten.values()), 2)


#: Unterhalb dieser Menge ist ein Segment eine **Rundungsfrage**, keine Aussage.
#:
#: ⚠ Sie trifft in der Praxis genau einen Fall: den Zähler-Rest eines Geräts,
#: dessen Gesamtzähler exakt auf der Summe seiner Achsen steht (die Demo-Daikin:
#: 380 = 343,3 + 36,7). Die Differenz ist dort ein Fließkomma-Rest von 1e-13 —
#: als Segment „System/Standby 0,0 kWh" stünde eine Größe im Bild, die es nicht
#: gibt. Dieselbe Schwelle, mit der der Client seine Rest-Zeilen filtert.
_SEGMENT_SCHWELLE_KWH = 0.02


def _fertig(
    sammler: _Sammler,
    perioden: list[VerteilungPeriode],
    *,
    sicht: str,
    ohne_stundenform_kwh: Optional[float] = None,
) -> VerteilungVerlauf:
    segmente = sammler.segmente()
    # Ein Segment zählt, wenn es **irgendwo** eine Menge hat — im Zeitraum oder
    # im Verlauf. Nur wenn beides unter der Schwelle bleibt, fällt es ganz weg;
    # halb (Balken ja, Stapel nein) wäre die schlechtere Antwort.
    im_verlauf: dict[str, float] = defaultdict(float)
    for p in perioden:
        for schluessel, kwh in p.kwh_je_segment.items():
            im_verlauf[schluessel] += kwh
    behalten = {
        z.schluessel for z in segmente
        if z.kwh >= _SEGMENT_SCHWELLE_KWH
        or im_verlauf.get(z.schluessel, 0.0) >= _SEGMENT_SCHWELLE_KWH
    }
    segmente = [z for z in segmente if z.schluessel in behalten]
    perioden = [
        VerteilungPeriode(
            schluessel=p.schluessel,
            label=p.label,
            kwh_je_segment={
                k: v for k, v in p.kwh_je_segment.items() if k in behalten
            },
            temperatur_c=p.temperatur_c,
            wetter_symbol=p.wetter_symbol,
        )
        for p in perioden
    ]
    return VerteilungVerlauf(
        sicht=sicht,
        stufe=_stufe(sicht),
        segmente=segmente,
        perioden=perioden,
        menge_kwh=round(sammler.menge_kwh, 2),
        aufgeteilt_kwh=round(sum(z.kwh for z in segmente), 2),
        # Σ der **gezeigten** Segmente — sonst nennte die Summenzeile einen
        # Betrag, den keine Tabellenzeile trägt.
        kosten_gesamt_euro=(
            round(sum(z.kosten_euro or 0.0 for z in segmente), 2)
            if sammler.hat_preis else None
        ),
        verlauf_kwh=round(
            sum(sum(p.kwh_je_segment.values()) for p in perioden), 2,
        ),
        ohne_stundenform_kwh=ohne_stundenform_kwh,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Monatszeilen — die Eingabe für Jahr (Perioden) und Monat (Verteilung)
# ─────────────────────────────────────────────────────────────────────────────

def _eingabe_aus_monatszeile(inv: Investition, daten: dict) -> GeraetStromEingabe:
    """Eine ``InvestitionMonatsdaten``-Zeile → die Eingabe des Layers.

    ⛔ **Menge und Zähler-Rest kommen aus dem SoT**, nicht aus einer eigenen
    Summe: ``wp_strom_aufteilung`` ist die eine Stelle, an der die K3-Stufenregel
    steht (F-56). Diese Funktion **wählt** nur die Eingänge.
    """
    params = inv.parameter or {}
    auf = wp_strom_aufteilung(daten, params)
    zeile = modus_strom_zeile(daten, summanden_zaehlen=summanden_gelten(params))  # N-766
    abdeckung = float(daten.get(MODUS_ABDECKUNG_FELD) or 0.0)
    return GeraetStromEingabe(
        menge_kwh=auf.menge_kwh,
        hat_getrennte_strommessung=bool(params.get("getrennte_strommessung")),
        strom_heizen_kwh=daten.get("strom_heizen_kwh"),
        strom_warmwasser_kwh=daten.get("strom_warmwasser_kwh"),
        nicht_aufgeteilt_kwh=auf.nicht_aufgeteilt_kwh,
        modus_heizen_kwh=zeile.heizen_kwh,
        modus_warmwasser_kwh=zeile.warmwasser_kwh,
        modus_kuehlen_kwh=zeile.kuehlen_kwh,
        modus_lueften_kwh=zeile.lueften_kwh,
        modus_entfeuchten_kwh=zeile.entfeuchten_kwh,
        modus_gemessen=zeile.gemessen,
        # Dieselbe Bedingung wie `ImdTypBeitrag.wp_modus_strom_bezug`: ein Gerät
        # ohne Modus-Erkenntnis steuert keine Grundmenge bei (W-17b).
        modus_bezug_kwh=(
            get_wp_strom_kwh(daten, params)
            if (abdeckung > 0 or zeile.gemessen) else 0.0
        ),
    )


async def _monatszeilen(
    db: AsyncSession,
    wps: list[Investition],
    von: tuple[int, int],
    bis: tuple[int, int],
) -> dict[tuple[int, int], dict[int, dict]]:
    """``{(jahr, monat): {inv_id: verbrauch_daten}}`` im Fenster, zeitgefiltert."""
    ids = [inv.id for inv in wps]
    if not ids:
        return {}
    rows = (await db.execute(
        select(InvestitionMonatsdaten).where(
            InvestitionMonatsdaten.investition_id.in_(ids),
            InvestitionMonatsdaten.jahr >= von[0],
            InvestitionMonatsdaten.jahr <= bis[0],
        )
    )).scalars().all()
    inv_by_id = {inv.id: inv for inv in wps}
    je_monat: dict[tuple[int, int], dict[int, dict]] = defaultdict(dict)
    for md in rows:
        schluessel = (md.jahr, md.monat)
        if not (von <= schluessel <= bis):
            continue
        inv = inv_by_id.get(md.investition_id)
        # #236/#239: Anschaffungs- und Stilllegungsdatum sind die Grenze — eine
        # Zeile außerhalb der Lebensdauer gehört in keinen Balken.
        if inv is None or not inv.ist_aktiv_im_monat(*schluessel):
            continue
        je_monat[schluessel][md.investition_id] = md.verbrauch_daten or {}
    return je_monat


async def _wp_preise_je_monat(
    db: AsyncSession, anlage_id: int, von: tuple[int, int], bis: tuple[int, int],
) -> dict[tuple[int, int], float]:
    """Der Wärmepumpen-Arbeitspreis je Monat (ct/kWh) — aus den Monats-Fakten.

    ⭐ **Nicht selbst aufgelöst** (ADR-002/**P8**): ``TarifFakten.wp_preis_cent``
    ist die ganze Kaskade — Wärmepumpen-Sondertarif → allgemeiner Tarif →
    Zeitfenster (HT/NT) → Default, je zum **Monatsersten**. Der Tagespfad rechnet
    mit demselben Wert (*„Tagestarif = Monatstarif je Tag"*,
    ``energie_profil/tag.py::get_tag_detail``), und genau deshalb steht hier eine Quelle und
    nicht zwei.
    """
    fakten = await lade_monats_fakten(db, anlage_id, von=von, bis=bis)
    return {(f.jahr, f.monat): f.tarif.wp_preis_cent for f in fakten}


# ─────────────────────────────────────────────────────────────────────────────
# Sicht: Jahr (Perioden = Monate)
# ─────────────────────────────────────────────────────────────────────────────

async def _jahr(
    db: AsyncSession, anlage, wps: list[Investition], jahr: int,
) -> VerteilungVerlauf:
    von, bis = (jahr, 1), (jahr, 12)
    je_monat = await _monatszeilen(db, wps, von, bis)
    preise = await _wp_preise_je_monat(db, anlage.id, von, bis)
    temperatur = await _monats_temperaturen(db, anlage.id, jahr)
    wetter = await _wetter_je_monat(db, anlage.id, jahr)
    inv_by_id = {inv.id: inv for inv in wps}

    sammler = _Sammler()
    perioden: list[VerteilungPeriode] = []
    for monat in range(1, 13):
        werte: dict[str, float] = {}
        for inv_id, daten in sorted(je_monat.get((jahr, monat), {}).items()):
            inv = inv_by_id[inv_id]
            v = verteile_geraet_strom(_eingabe_aus_monatszeile(inv, daten))
            werte.update(sammler.nimm(inv, v, preis_cent=preise.get((jahr, monat))))
        perioden.append(VerteilungPeriode(
            schluessel=str(monat),
            label=MONAT_KURZ[monat - 1],
            kwh_je_segment={k: round(v, 3) for k, v in werte.items() if v > 0},
            temperatur_c=temperatur.get((jahr, monat)),
            wetter_symbol=wetter.get(monat),
        ))
    return _fertig(sammler, perioden, sicht="jahr")


# ─────────────────────────────────────────────────────────────────────────────
# Sicht: Monat (Verteilung aus der Monatszeile, Perioden = Tage)
# ─────────────────────────────────────────────────────────────────────────────

async def _monat(
    db: AsyncSession, anlage, wps: list[Investition], jahr: int, monat: int,
) -> VerteilungVerlauf:
    schluessel = (jahr, monat)
    je_monat = await _monatszeilen(db, wps, schluessel, schluessel)
    preis = (await _wp_preise_je_monat(db, anlage.id, schluessel, schluessel)).get(
        schluessel,
    )
    inv_by_id = {inv.id: inv for inv in wps}

    sammler = _Sammler()
    for inv_id, daten in sorted(je_monat.get(schluessel, {}).items()):
        inv = inv_by_id[inv_id]
        sammler.nimm(
            inv,
            verteile_geraet_strom(_eingabe_aus_monatszeile(inv, daten)),
            preis_cent=preis,
        )

    # ── Die Perioden: die Tage desselben Monats ───────────────────────────
    #
    # ⚠ **Sie gehen NICHT in die Verteilung ein** (`in_summe=False`). Die
    # Verteilung ist die Monatszeile — dieselbe Quelle wie die Kacheln darüber.
    # Die Tagessäulen stehen im Add-on in einem um eine Stunde versetzten
    # Fenster (Konzept Kap. 6.3) und tragen nur, was der Snapshot-Pfad kennt;
    # sie als Summe zu nehmen hieße, zwei verschiedene Zahlen für dieselbe Größe
    # zu führen (die W-17b-Klasse).
    erster = date(jahr, monat, 1)
    letzter = date(jahr, monat, calendar.monthrange(jahr, monat)[1])
    perioden = await _tages_perioden(db, anlage, wps, erster, letzter, sammler)
    return _fertig(sammler, perioden, sicht="monat")


async def _tages_perioden(
    db: AsyncSession,
    anlage,
    wps: list[Investition],
    von: date,
    bis: date,
    sammler: _Sammler,
) -> list[VerteilungPeriode]:
    """Je Tag die Segmente — aus demselben Snapshot-Pfad wie *Cockpit → Tag*."""
    from backend.services.energie_profil.waerme_verlauf import (
        lade_waerme_verlauf_beitraege,
    )

    inv_by_id = {str(inv.id): inv for inv in wps}
    je_tag = await lade_waerme_verlauf_beitraege(db, anlage, inv_by_id, von, bis)
    temperatur = await lade_tagesmittel_temperatur(db, anlage.id, von, bis)
    wetter = await _wetter_je_tag(db, anlage.id, von, bis)

    perioden: list[VerteilungPeriode] = []
    for tag in sorted(je_tag):
        werte: dict[str, float] = {}
        zeile = je_tag[tag]
        for inv_id_str, eingabe in sorted(zeile.items()):
            inv = inv_by_id.get(inv_id_str)
            if inv is None:
                continue
            werte.update(sammler.nimm(
                inv, verteile_geraet_strom(eingabe),
                preis_cent=None, in_summe=False,
            ))
        perioden.append(VerteilungPeriode(
            schluessel=tag.isoformat(),
            label=str(tag.day),
            kwh_je_segment={k: round(v, 3) for k, v in werte.items() if v > 0},
            temperatur_c=(
                round(temperatur[tag], 1) if tag in temperatur else None
            ),
            wetter_symbol=wetter.get(tag),
        ))
    return perioden


# ─────────────────────────────────────────────────────────────────────────────
# Sicht: Tag (Verteilung aus den Tageswerten, Perioden = Stunden)
# ─────────────────────────────────────────────────────────────────────────────

async def _tag(
    db: AsyncSession, anlage, wps: list[Investition], datum: date,
) -> VerteilungVerlauf:
    from backend.services.energie_profil.waerme_verteilung_tag import (
        lade_tages_verteilung,
    )

    inv_by_id = {str(inv.id): inv for inv in wps}
    tag = await lade_tages_verteilung(db, anlage, inv_by_id, datum)
    monat = (datum.year, datum.month)
    preis = (await _wp_preise_je_monat(db, anlage.id, monat, monat)).get(monat)
    temperatur, wetter = await _stunden_wetter(db, anlage.id, datum)

    sammler = _Sammler()
    verteilungen: dict[str, GeraetStromVerteilung] = {}
    for inv_id_str, eingabe in sorted(tag.je_geraet.items()):
        inv = inv_by_id.get(inv_id_str)
        if inv is None:
            continue
        v = verteile_geraet_strom(eingabe)
        verteilungen[inv_id_str] = v
        sammler.nimm(inv, v, preis_cent=preis)

    perioden: list[VerteilungPeriode] = []
    for h in range(STUNDEN):
        werte: dict[str, float] = {}
        for inv_id_str, je_funktion in tag.stunden_je_geraet.items():
            for funktion, reihe in je_funktion.items():
                wert = reihe[h]
                if wert > 0:
                    werte[f"{inv_by_id[inv_id_str].id}:{funktion}"] = round(wert, 4)
        perioden.append(VerteilungPeriode(
            schluessel=str(h),
            # Slot h = Energie [h−1, h) — dieselbe Beschriftung wie im
            # Stunden-Verlauf daneben.
            label=f"{h}",
            kwh_je_segment=werte,
            temperatur_c=temperatur.get(h),
            wetter_symbol=wetter.get(h),
        ))
    return _fertig(
        sammler, perioden, sicht="tag",
        ohne_stundenform_kwh=(
            round(tag.ohne_stundenform_kwh, 2)
            if tag.ohne_stundenform_kwh > 0.005 else None
        ),
    )


# ─────────────────────────────────────────────────────────────────────────────
# Temperatur und Wetter
# ─────────────────────────────────────────────────────────────────────────────

async def _monats_temperaturen(
    db: AsyncSession, anlage_id: int, jahr: int,
) -> dict[tuple[int, int], float]:
    """Monatsmittel über die Vorrangkette — Stundenwerte, Min/Max, gepflegt."""
    gepflegt = {
        (j, m): t
        for j, m, t in (await db.execute(
            select(
                Monatsdaten.jahr, Monatsdaten.monat,
                Monatsdaten.durchschnittstemperatur,
            ).where(
                Monatsdaten.anlage_id == anlage_id,
                Monatsdaten.jahr == jahr,
            )
        )).all()
    }
    return await lade_monatsmittel_temperatur(
        db, anlage_id, gepflegt,
        von=date(jahr, 1, 1), bis=date(jahr, 12, 31),
    )


async def _wetter_codes_je_stunde(
    db: AsyncSession, anlage_id: int, von: date, bis: date,
) -> dict[date, list[tuple[int, int]]]:
    """``{datum: [(stunde, wetter_code)]}`` — die Rohreihe für alle drei Stufen."""
    rows = (await db.execute(
        select(
            TagesEnergieProfil.datum,
            TagesEnergieProfil.stunde,
            TagesEnergieProfil.wetter_code,
        ).where(and_(
            TagesEnergieProfil.anlage_id == anlage_id,
            TagesEnergieProfil.datum >= von,
            TagesEnergieProfil.datum <= bis,
            TagesEnergieProfil.wetter_code.is_not(None),
        ))
    )).all()
    je_tag: dict[date, list[tuple[int, int]]] = defaultdict(list)
    for datum, stunde, code in rows:
        je_tag[datum].append((int(stunde), int(code)))
    return je_tag


def _haeufigster(codes: list[int]) -> Optional[int]:
    """Der häufigste Code — bei Gleichstand der **kleinere** (der klarere).

    ⚠ Nicht der „schlechteste Moment": Ein Tag mit vierzehn Sonnenstunden und
    einem Schauer ist ein sonniger Tag. Genau diese Verzerrung korrigiert
    ``wetter_symbol_aus_tag`` auf dem Prognosepfad über die Bewölkung; hier
    liegen alle Stunden vor, und der **Modus** der Reihe ist die einfachere und
    ehrlichere Antwort auf dieselbe Frage.
    """
    if not codes:
        return None
    zaehler = Counter(codes)
    hoechste = max(zaehler.values())
    return min(code for code, n in zaehler.items() if n == hoechste)


async def _wetter_je_tag(
    db: AsyncSession, anlage_id: int, von: date, bis: date,
) -> dict[date, str]:
    je_tag = await _wetter_codes_je_stunde(db, anlage_id, von, bis)
    ergebnis: dict[date, str] = {}
    for datum, paare in je_tag.items():
        code = _haeufigster([c for _, c in paare])
        if code is not None:
            ergebnis[datum] = wetter_code_zu_symbol(code)
    return ergebnis


async def _wetter_je_monat(
    db: AsyncSession, anlage_id: int, jahr: int,
) -> dict[int, str]:
    """Monatssymbol = häufigster **Tages**code (nicht häufigster Stundencode).

    ⚠ Der Unterschied ist keine Feinheit: Über den Stunden gewichtete ein Monat
    mit wenigen, aber lang erfassten Regentagen dieselben Tage mehrfach. Über die
    Tagescodes zählt jeder Tag einmal — dieselbe Begründung, mit der
    ``lade_monatsmittel_temperatur`` über Tagesmittel mittelt und nicht über
    Stunden.
    """
    je_tag = await _wetter_codes_je_stunde(
        db, anlage_id, date(jahr, 1, 1), date(jahr, 12, 31),
    )
    codes_je_monat: dict[int, list[int]] = defaultdict(list)
    for datum, paare in je_tag.items():
        code = _haeufigster([c for _, c in paare])
        if code is not None:
            codes_je_monat[datum.month].append(code)
    ergebnis: dict[int, str] = {}
    for monat, codes in codes_je_monat.items():
        code = _haeufigster(codes)
        if code is not None:
            ergebnis[monat] = wetter_code_zu_symbol(code)
    return ergebnis


async def _stunden_wetter(
    db: AsyncSession, anlage_id: int, datum: date,
) -> tuple[dict[int, float], dict[int, str]]:
    """Temperatur und Symbol je Stunde — direkt aus der Stundenzeile."""
    rows = (await db.execute(
        select(
            TagesEnergieProfil.stunde,
            TagesEnergieProfil.temperatur_c,
            TagesEnergieProfil.wetter_code,
        ).where(
            TagesEnergieProfil.anlage_id == anlage_id,
            TagesEnergieProfil.datum == datum,
        )
    )).all()
    temperatur: dict[int, float] = {}
    symbole: dict[int, str] = {}
    for stunde, temp, code in rows:
        if temp is not None:
            temperatur[int(stunde)] = round(float(temp), 1)
        if code is not None:
            symbole[int(stunde)] = wetter_code_zu_symbol(int(code))
    return temperatur, symbole


# ─────────────────────────────────────────────────────────────────────────────
# Die Tages-Eingabe (von zwei Stufen gebraucht: Monat→Tage und Tag→Verteilung)
# ─────────────────────────────────────────────────────────────────────────────

def eingabe_aus_tageswerten(
    inv: Investition,
    *,
    menge_kwh: float,
    strom_heizen_kwh: Optional[float],
    strom_warmwasser_kwh: Optional[float],
    beitrag: Optional[GeraeteBeitrag],
) -> GeraetStromEingabe:
    """Die Tageswerte **eines** Geräts → die Eingabe des Layers.

    ⭐ **Die zweite Mengen-Herkunft** (s. Modulkopf): Der Tag faltet Snapshots,
    nicht ``InvestitionMonatsdaten``. Was er **nicht** hat, ist eine
    ``verbrauch_daten``-Zeile — und deshalb ruft er nicht
    ``wp_strom_aufteilung``, sondern dessen beide Formeln einzeln
    (``wp_feine_summe_kwh`` · ``wp_nicht_aufgeteilt_kwh``). **Die Formel steht
    an einer Stelle, die Eingänge dürfen sich unterscheiden** (F-56/N-450).

    ⚠ **Die Menge kommt aus dem Zählerpfad** (``komponenten_kwh``), nicht aus
    der Stufenregel: Auf Tagesebene hat sie der Aggregator bereits angewandt
    (``komponenten_beitraege.py``). Sie hier ein zweites Mal zu stellen hieße,
    dieselbe Frage zweimal zu beantworten.
    """
    params = inv.parameter or {}
    gemessen = bool(beitrag and beitrag.gemessen)
    funktionsfremd = (
        (beitrag.kuehlen_kwh + beitrag.lueften_kwh + beitrag.entfeuchten_kwh)
        if (beitrag and gemessen) else 0.0
    )
    feine_summe = wp_feine_summe_kwh(
        strom_heizen_kwh, strom_warmwasser_kwh, funktionsfremd,
        betriebsart_gemessen=gemessen,
    )
    # Dieselbe Bedingung wie in `wp_strom_aufteilung`: `is not None`, nicht
    # truthy — ein Warmwasser-Strom von 0,0 im Sommer ist eine Messung.
    hat_aufteilung = (
        strom_heizen_kwh is not None or strom_warmwasser_kwh is not None
        or (gemessen and funktionsfremd > 0)
    )
    return GeraetStromEingabe(
        menge_kwh=float(menge_kwh or 0.0),
        hat_getrennte_strommessung=bool(params.get("getrennte_strommessung")),
        strom_heizen_kwh=strom_heizen_kwh,
        strom_warmwasser_kwh=strom_warmwasser_kwh,
        nicht_aufgeteilt_kwh=wp_nicht_aufgeteilt_kwh(
            float(menge_kwh or 0.0), feine_summe, hat_aufteilung=hat_aufteilung,
        ),
        modus_heizen_kwh=beitrag.heizen_kwh if beitrag else 0.0,
        modus_warmwasser_kwh=beitrag.warmwasser_kwh if beitrag else 0.0,
        modus_kuehlen_kwh=beitrag.kuehlen_kwh if beitrag else 0.0,
        modus_lueften_kwh=beitrag.lueften_kwh if beitrag else 0.0,
        modus_entfeuchten_kwh=beitrag.entfeuchten_kwh if beitrag else 0.0,
        modus_gemessen=gemessen,
        modus_bezug_kwh=beitrag.bezug_kwh if beitrag else 0.0,
    )


__all__ = [
    "VerteilungSegment",
    "VerteilungPeriode",
    "VerteilungVerlauf",
    "lade_verteilung_verlauf",
    "eingabe_aus_tageswerten",
]
