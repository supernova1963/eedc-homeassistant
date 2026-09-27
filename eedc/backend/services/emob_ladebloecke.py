"""Ladeblöcke — welches Auto in welchen Stunden an der Wallbox geladen hat (N-555 Stufe 3).

Konzept Heimladung/Fahrverbrauch, Fassung 7.2, §5 **Regel 9** (Punkt 1–3 mit **G2**) und
**Anhang D** (W-A, D-1…D-6). Reine Rechnung, ohne Datenbank — die Ablage und der Aufruf aus
der Tagesaggregation stehen in ``emob_ladebloecke_speicher.py``.

**Die Frage.** eedc rechnet den PV-Anteil der Heimladung schon je Stunde (Phase 5,
„Einspeise-Deckung", `core/berechnungen/pv_anteil_ladung.py`). Es fehlte nur, **welches Auto**
in welcher Stunde geladen hat. Ein Heimlade-Zähler je Auto (evcc-Fahrzeug-Sensor an
„Heim: gesamt") springt am **Ende** eines Ladevorgangs um dessen ganze Menge (Regel 9 Punkt 1,
gemessen am Lab-Recorder: 08.07.2026 Wallbox 13–19 Uhr stündlich, Fahrzeug +18,602 kWh in der
letzten Stunde).

**Die Regel (Punkt 2, D-1).** Die Sprünge aller Autos werden der Zeit nach abgearbeitet. Je
Sprung geht der Block **rückwärts** über die Wallbox-Stunden und nimmt aus jeder Stunde, was
frühere Blöcke dort noch nicht genommen haben (die **Restmenge**):

* in der **eigenen Sprungstunde** höchstens den Bedarf — nach dem Sprung gehört die Stunde dem
  nächsten Vorgang (Übergabe in derselben Stunde, 05.06.2026 17:00: 0,414 / 0,376);
* in früheren Stunden höchstens **Bedarf + 0,05 kWh** — so schluckt ein Block mit Wallbox-Lücke
  keine ganze fremde Stunde;
* bis Σ ≥ Sprung − 0,05 kWh (Toleranz), **höchstens bis zur Stunde des vorigen Sprungs
  irgendeines Autos, einschließlich**. Nullstunden werden übersprungen (Anstecken über Nacht,
  W4). Standby-Drip zählt nur, soweit er zur Menge gehört.

**Die Menge (Punkt 3, G2).** Die Menge des Vorgangs ist der **Sprung** — der Fahrzeug-Zähler
misst sie direkt. Die Blockstunden liefern nur, was allein sie wissen: **wann** — den PV-Anteil
und die Verteilung auf die Monate. ``stunden_gedeckt`` = Σ Blockenergie ÷ Sprung ist ein
Kennzeichen. *Grund auf Kategorie-Ebene:* die Wallbox-Stunden sind ein zweiter Sensor mit
eigenen Lücken; eine Menge aus ihnen nachzubauen ersetzte eine Messung durch eine
Rekonstruktion (Klasse F1/F2).

**Gebündelte Wallbox-Stunde (W-A).** Seit „Zählerlücken wie HA" trägt ein Slot mit n > 1 die
Energie der Lücke (27.07.2026: 11,413 kWh, n = 49). Er zählt zur Blockenergie — dem Bündel fehlt
die **Stunde**, nicht die **Menge** — und senkt ``stunden_gedeckt`` nicht; der Block trägt
``luecke``. Einen PV-Anteil liefert das Bündel nicht (die Stunde ist unbekannt).

**Monat einer Stunde (D-3)** = Kalendermonat ihres **Beginns**. Ein Sprung ohne Blockstunde
zählt im Monat des Sprungs, ``stunden_gedeckt`` 0.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Final, Iterable, Mapping, Optional

from backend.core.berechnungen.pv_anteil_ladung import (
    leite_pv_anteil_ab,
    stunde_aus_bilanzwerten,
)

#: Regel 9 Punkt 2: ein Block ist voll, sobald Σ ≥ Sprung − Toleranz; in früheren Stunden
#: nimmt er höchstens Bedarf + Toleranz.
TOLERANZ_KWH: Final[float] = 0.05
#: D-4: Sprünge bis hierher sind Mikrosprünge (Standby-Drip des Fahrzeug-Zählers,
#: 0,001–0,004 kWh). Ihre Menge zählt; „Ladevorgang" und Kennzeichen gelten nur darüber.
KLEINSTSPRUNG_KWH: Final[float] = 0.05
#: Kennzeichen: unter diesem Deckungsgrad trägt der Block eine Wallbox-Lücke (Regel 9 Punkt 3).
GEDECKT_KENNZEICHEN: Final[float] = 0.95
#: Bildungsvorschrift, wandert in ``emob_ladebloecke.regel``.
REGEL_SPRUNG_RUECKWAERTS: Final[str] = "sprung_rueckwaerts"

_EPS: Final[float] = 1e-9

Monat = tuple[int, int]


@dataclass(frozen=True)
class WallboxStunde:
    """Eine Stunde der Wallbox-Achse (Σ der privaten Wallboxen, Regel 0).

    ``beginn``: lokaler Beginn der Stunde (Backward-Slot h von D beginnt D + (h−1) h).
    ``kwh``: Ladung der Stunde. ``n``: reale Stunden der Menge (> 1 = Bündel, W-A).
    ``pv_anteil``: PV ÷ Ladung dieser Stunde aus der Stundenrechnung, ``None`` = nicht
    ableitbar (Bündel auf wallbox/pv/netzbezug oder Eingang fehlt).
    """
    beginn: datetime
    kwh: float
    n: int = 1
    pv_anteil: Optional[float] = None
    #: N-569-Ergänzung: davon aus dem Speicher ÷ Ladung dieser Stunde (Teil von ``pv_anteil``);
    #: ``None`` = ohne Speicherzähler oder nicht ableitbar.
    speicher_anteil: Optional[float] = None


@dataclass(frozen=True)
class FahrzeugSprung:
    """Ein Sprung des Heimlade-Zählers eines Autos: am Ende der Stunde ``beginn``."""
    inv_id: int
    beginn: datetime
    kwh: float


@dataclass(frozen=True)
class BlockStunde:
    """Der Anteil eines Blocks an einer Wallbox-Stunde."""
    beginn: datetime
    kwh: float
    n: int = 1
    pv_anteil: Optional[float] = None
    speicher_anteil: Optional[float] = None


@dataclass(frozen=True)
class Ladeblock:
    """Ein Ladevorgang eines Autos (Regel 9)."""
    inv_id: int
    #: Beginn der frühesten Blockstunde (ohne Blockstunde: Beginn der Sprungstunde).
    beginn: datetime
    #: Ende der Sprungstunde — mit ``inv_id`` eindeutig (ein Zähler hat je Stunde einen Slot).
    ende: datetime
    #: Die Menge = der Sprung (G2).
    kwh: float
    #: PV-Anteil des Blocks aus den ableitbaren Blockstunden, auf den Sprung skaliert;
    #: ``None`` = keine Blockstunde ableitbar ⇒ der Leser nimmt den Wallbox-Monatsanteil.
    pv_kwh: Optional[float]
    stunden: tuple[BlockStunde, ...] = field(default_factory=tuple)
    #: Σ Blockenergie ÷ Sprung (Kennzeichen, kein Rechenwert).
    stunden_gedeckt: float = 0.0
    #: Mindestens eine Blockstunde ist ein Bündel (W-A).
    luecke: bool = False
    #: N-569-Ergänzung: davon aus dem Speicher — Teilmenge von ``pv_kwh``, gleich skaliert;
    #: ``None`` ohne Speicherzähler in den ableitbaren Blockstunden.
    speicher_kwh: Optional[float] = None

    @property
    def netz_kwh(self) -> Optional[float]:
        return None if self.pv_kwh is None else self.kwh - self.pv_kwh

    @property
    def ist_ladevorgang(self) -> bool:
        """D-4: nur ein Sprung über der Kleinstgrenze ist ein Ladevorgang."""
        return self.kwh > KLEINSTSPRUNG_KWH


def stunden_beginn(datum, slot: int) -> datetime:
    """Lokaler Beginn des Backward-Slots ``slot`` von ``datum`` (Slot 0 = Vortag 23 Uhr)."""
    return datetime(datum.year, datum.month, datum.day) + timedelta(hours=slot - 1)


def anteile_der_stunde(
    *,
    ladung: Optional[float],
    netzbezug: Optional[float],
    einspeisung: Optional[float],
    batterie_spalte: Optional[float],
    gebuendelt: bool,
) -> tuple[Optional[float], Optional[float]]:
    """``(PV ÷ Ladung, davon Speicher ÷ Ladung)`` EINER Stunde — beide aus derselben Rechnung
    (`leite_pv_anteil_ab`, N-569 Anhang E). ``(None, None)`` = nicht ableitbar."""
    if gebuendelt or ladung is None or ladung <= 0:
        return None, None
    anteil = leite_pv_anteil_ab([stunde_aus_bilanzwerten(
        ladung=ladung, netzbezug=netzbezug, einspeisung=einspeisung,
        batterie_spalte=batterie_spalte,
    )])
    if anteil is None or anteil.ladung_kwh <= 0:
        return None, None
    speicher = (
        anteil.speicher_kwh / anteil.ladung_kwh if anteil.speicher_kwh is not None else None
    )
    return anteil.pv_kwh / anteil.ladung_kwh, speicher


def bilde_ladebloecke(
    stunden: Iterable[WallboxStunde],
    spruenge: Iterable[FahrzeugSprung],
    *,
    schon_genommen: Optional[Mapping[datetime, float]] = None,
    voriger_sprung: Optional[datetime] = None,
) -> list[Ladeblock]:
    """Regel 9 Punkt 2/3 (D-1) — die Blöcke zu ``spruenge``.

    Args:
        stunden: die Wallbox-Stunden des Fensters (mehrfach genannte Stunden werden summiert).
        spruenge: die Sprünge, deren Blöcke gebildet werden sollen.
        schon_genommen: je Stundenbeginn die Energie, die bereits gespeicherte Blöcke
            (früherer Sprünge) aus dieser Stunde genommen haben — sie fehlt in der Restmenge.
        voriger_sprung: Beginn der Stunde des letzten Sprungs **vor** dem ersten der
            ``spruenge`` (irgendeines Autos); die Schranke gilt einschließlich.

    Returns:
        Die Blöcke in der Reihenfolge der Sprünge.
    """
    kwh_je: dict[datetime, float] = {}
    n_je: dict[datetime, int] = {}
    q_je: dict[datetime, Optional[float]] = {}
    sq_je: dict[datetime, Optional[float]] = {}
    for s in stunden:
        if s.kwh is None or s.kwh <= 0:
            continue
        kwh_je[s.beginn] = kwh_je.get(s.beginn, 0.0) + s.kwh
        n_je[s.beginn] = max(n_je.get(s.beginn, 1), s.n)
        q_je[s.beginn] = s.pv_anteil if s.beginn not in q_je else (
            q_je[s.beginn] if q_je[s.beginn] == s.pv_anteil else None
        )
        sq_je[s.beginn] = s.speicher_anteil if s.beginn not in sq_je else (
            sq_je[s.beginn] if sq_je[s.beginn] == s.speicher_anteil else None
        )
    rest = {b: max(0.0, k - (schon_genommen or {}).get(b, 0.0)) for b, k in kwh_je.items()}
    reihenfolge = sorted(kwh_je)

    bloecke: list[Ladeblock] = []
    schranke = voriger_sprung
    for sp in sorted(spruenge, key=lambda s: (s.beginn, s.inv_id)):
        if sp.kwh <= 0:
            continue
        bedarf = sp.kwh
        genommen: list[BlockStunde] = []
        for b in reversed(reihenfolge):
            if b > sp.beginn:
                continue
            if schranke is not None and b < schranke:
                break
            if bedarf <= TOLERANZ_KWH + _EPS and genommen:
                break
            r = rest.get(b, 0.0)
            if r <= _EPS:
                continue  # Nullstunde (oder schon vergeben) — überspringen (W4)
            grenze = bedarf if b == sp.beginn else bedarf + TOLERANZ_KWH
            take = min(r, grenze)
            if take <= _EPS:
                continue
            rest[b] = r - take
            bedarf -= take
            genommen.append(BlockStunde(b, round(take, 6), n_je[b], q_je[b], sq_je[b]))
            if bedarf <= TOLERANZ_KWH + _EPS:
                break
        genommen.reverse()
        summe = sum(g.kwh for g in genommen)
        ableitbar = [g for g in genommen if g.pv_anteil is not None and g.n == 1]
        pv: Optional[float] = None
        speicher: Optional[float] = None
        if ableitbar:
            basis = sum(g.kwh for g in ableitbar)
            if basis > _EPS:
                pv = sp.kwh * sum(g.kwh * g.pv_anteil for g in ableitbar) / basis
                if any(g.speicher_anteil is not None for g in ableitbar):
                    # Teilmenge von PV, gleich skaliert (Anhang E, Ergänzung).
                    speicher = min(pv, sp.kwh * sum(
                        g.kwh * (g.speicher_anteil or 0.0) for g in ableitbar
                    ) / basis)
        bloecke.append(Ladeblock(
            inv_id=sp.inv_id,
            beginn=genommen[0].beginn if genommen else sp.beginn,
            ende=sp.beginn + timedelta(hours=1),
            kwh=round(sp.kwh, 3),
            pv_kwh=None if pv is None else round(pv, 3),
            stunden=tuple(genommen),
            stunden_gedeckt=round(summe / sp.kwh, 4),
            luecke=any(g.n > 1 for g in genommen),
            speicher_kwh=None if speicher is None else round(speicher, 3),
        ))
        schranke = sp.beginn
    return bloecke


def monat_der_stunde(beginn: datetime) -> Monat:
    """D-3: der Kalendermonat, in dem die Stunde beginnt."""
    return (beginn.year, beginn.month)


def verteile_auf_monate(block: Ladeblock) -> dict[Monat, tuple[float, Optional[float]]]:
    """Punkt 3: ``{(jahr, monat): (kwh, pv_kwh)}`` — Sprung × Σe(Monat) ÷ Σe(Block), PV analog.

    Ohne Blockstunde (Kennzeichen 0) gehört alles dem Monat des Sprungs.
    """
    summe = sum(s.kwh for s in block.stunden)
    if summe <= _EPS:
        return {monat_der_stunde(block.ende - timedelta(hours=1)): (block.kwh, block.pv_kwh)}
    je_monat: dict[Monat, float] = {}
    for s in block.stunden:
        m = monat_der_stunde(s.beginn)
        je_monat[m] = je_monat.get(m, 0.0) + s.kwh
    return {
        m: (block.kwh * e / summe, None if block.pv_kwh is None else block.pv_kwh * e / summe)
        for m, e in je_monat.items()
    }


@dataclass
class BlockMonat:
    """Die Heimladung EINES Autos in EINEM Monat aus seinen Ladeblöcken (S3-4).

    ``kwh`` = Σ der monatsverteilten Sprünge (G2). ``pv_kwh`` ist der PV-Teil der Blöcke mit
    ableitbarem Anteil; ``kwh_ohne_pv`` die Menge der Blöcke ohne — sie teilt der Leser mit
    dem Wallbox-Monatsanteil (D-2).
    """
    kwh: float = 0.0
    pv_kwh: float = 0.0
    kwh_ohne_pv: float = 0.0
    #: N-569-Ergänzung: davon aus dem Speicher (Teil von ``pv_kwh``); ``None`` = keine Aussage.
    speicher_kwh: Optional[float] = None
    #: Ladevorgänge (Sprünge > Kleinstgrenze), deren Sprung in diesem Monat liegt.
    ladevorgaenge: int = 0
    #: Ladevorgänge mit ``stunden_gedeckt`` < 0,95 (Wallbox-Lücke, Kennzeichen).
    ladevorgaenge_ungedeckt: int = 0
    #: Ladevorgänge mit gebündelter Wallbox-Stunde (W-A).
    ladevorgaenge_mit_luecke: int = 0

    def addiere(self, kwh: float, pv: Optional[float]) -> None:
        self.kwh += kwh
        if pv is None:
            self.kwh_ohne_pv += kwh
        else:
            self.pv_kwh += pv

    def aufteilung(self, wallbox_pv_anteil: Optional[float]) -> tuple[float, float]:
        """``(pv, netz)`` — der Teil ohne Blockanteil mit dem Wallbox-Monatsanteil (D-2)."""
        pv = self.pv_kwh + self.kwh_ohne_pv * (wallbox_pv_anteil or 0.0)
        pv = min(max(pv, 0.0), self.kwh)
        return pv, self.kwh - pv


def block_monate(bloecke: Iterable[Ladeblock]) -> dict[Monat, dict[int, BlockMonat]]:
    """Faltet Blöcke je ``(jahr, monat)`` und Auto (ohne die Tages-Bedingung W-C)."""
    out: dict[Monat, dict[int, BlockMonat]] = {}
    for b in bloecke:
        for m, (kwh, pv) in verteile_auf_monate(b).items():
            bm = out.setdefault(m, {}).setdefault(b.inv_id, BlockMonat())
            bm.addiere(kwh, pv)
            if b.speicher_kwh is not None:
                anteil = kwh / b.kwh if b.kwh > _EPS else 0.0
                bm.speicher_kwh = (bm.speicher_kwh or 0.0) + b.speicher_kwh * anteil
        if b.ist_ladevorgang:
            m = monat_der_stunde(b.ende - timedelta(hours=1))
            bm = out.setdefault(m, {}).setdefault(b.inv_id, BlockMonat())
            bm.ladevorgaenge += 1
            if b.stunden_gedeckt < GEDECKT_KENNZEICHEN:
                bm.ladevorgaenge_ungedeckt += 1
            if b.luecke:
                bm.ladevorgaenge_mit_luecke += 1
    return out
