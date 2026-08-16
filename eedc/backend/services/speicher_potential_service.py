"""Lädt die Stundenreihe für die Speicher-Potentialanalyse (#358 Phase 2).

Trennung wie in ADR-001: die **Formel** steht in
`core/berechnungen/speicher_potential.py`, hier liegt allein das **Sourcing** —
Stunden aus `TagesEnergieProfil` holen, in `SpeicherStunde` übersetzen, je Monat
gruppieren.

⚠ **Der SoC in `TagesEnergieProfil` hat keine `investition_id`, ist aber seit
N-239 (2026-08-12) ein echter Anlagenwert:** `_get_soc_history` liest **jeden**
gemappten Speicher-Sensor, `core.berechnungen.speicher.anlagen_soc_prozent`
bildet daraus das **kapazitätsgewichtete** Mittel, und die Aufschlüsselung je
Gerät steht in `TagesEnergieProfil.soc_je_speicher`. Vorher gewann der erste
Sensor in der Mapping-Reihenfolge, und die Kalibrierung beschrieb still ein
einzelnes Gerät.

⚠ **Tage vor dieser Umstellung tragen weiterhin die Ein-Gerät-Zahl** (`soc_je_speicher`
ist dort `NULL`) — kein Backfill, das wäre der ausgeschlossene „große Heiler-Knopf".
Der Daten-Checker (`SOC_NUR_EIN_SPEICHER`) meldet betroffene Zeiträume und stellt
die Neu-Aggregation daneben.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.berechnungen.speicher import (
    SocSpanne,
    netz_ladung_stunde_kwh,
    soc_spanne,
    vollzyklen,
)
from backend.core.berechnungen.speicher_potential import (
    SOC_VOLL_PROZENT,
    PotentialErgebnis,
    SpeicherStunde,
    berechne_zusatzpotential,
    ist_leer,
    ist_voll,
)
from backend.models.tages_energie_profil import TagesEnergieProfil
from backend.services.monats_fakten import lade_monats_fakten


@dataclass
class MonatsPotential:
    """Ein Monat der Auswertung — die Spalte der Spannen-Grafik.

    ⚠ **Bis 2026-08-14 stand hier `soc_bins`** (zehn Stundenzähler je
    SoC-Zehntel) und die Sicht malte daraus eine Heatmap. Sie normierte die
    Deckkraft **global** über alle Monate und Bins — ein einzelner
    Winter-Extremwert im untersten Bin drückte damit alle übrigen Zellen in
    einen schmalen Deckkraftbereich, und benachbarte Monate waren nicht mehr
    unterscheidbar (Rainer, 13.08.). Das war ein Skalierungsfehler, kein
    Geschmack: Die Verteilung selbst war da, nur unlesbar. Ersetzt durch
    `spanne` (P10/P50/P90 je Monat, **ohne** Bezug auf andere Monate) plus die
    beiden Anteile an den Rändern — dieselbe Aussage, ohne gemeinsame Skala.
    """

    jahr: int
    monat: int
    nutzbares_zusatzpotential_kwh: float
    ueberschuss_kwh: float
    stunden_voll: int
    zyklen_gesamt: int
    zyklen_leergelaufen: int

    #: Stunden mit gemessenem SoC — der Nenner der beiden Anteile. Ohne ihn
    #: wäre „0 % voll" nicht von „nichts gemessen" zu unterscheiden.
    stunden_mit_soc: int
    #: P10/P50/P90 des Ladestands. `None`, wenn der Monat keinen SoC trägt.
    spanne: Optional[SocSpanne]
    #: Anteil der gemessenen Stunden ≥ `SOC_VOLL_PROZENT` bzw. ≤ `SOC_LEER_PROZENT`.
    #: `None` ohne gemessene Stunde.
    anteil_voll_prozent: Optional[float]
    anteil_leer_prozent: Optional[float]

    #: Durchsatz: Vollzyklen-Äquivalent des Monats (Entladung ÷ Kapazität).
    #: `None`, wenn keine Kapazität gepflegt ist **oder** der Monat keine
    #: Entladung in den Monats-Fakten hat — bewusst kein 0-Ersatz.
    vollzyklen: Optional[float]

    #: Ladung des Monats aus den **Stundenzeilen** und der Teil davon, der
    #: höchstens aus dem Netz kam (Layer-SoT `netz_ladung_stunde_kwh`).
    ladung_kwh: float
    netz_ladung_kwh: float

    @property
    def netz_ladung_anteil_prozent(self) -> Optional[float]:
        """Anteil der Ladung, der höchstens aus dem Netz kam. `None` ohne Ladung."""
        if self.ladung_kwh <= 0:
            return None
        return min(100.0, self.netz_ladung_kwh / self.ladung_kwh * 100.0)


@dataclass
class PotentialAuswertung:
    gesamt: PotentialErgebnis
    monate: list[MonatsPotential]
    tage_mit_daten: int
    von: Optional[date]
    bis: Optional[date]


def _als_speicher_stunde(zeile: TagesEnergieProfil) -> SpeicherStunde:
    """Stundenmittel in kW ⇒ kWh der Stunde: numerisch identisch, benannt verschieden.

    Die Spalten heißen `_kw`, tragen aber das **Stundenmittel**; über eine Stunde
    integriert ist der Zahlenwert derselbe. Der Layer rechnet ausdrücklich in kWh,
    deshalb wird hier umbenannt statt stillschweigend gemischt.
    """
    return SpeicherStunde(
        soc_prozent=zeile.soc_prozent,
        einspeisung_kwh=zeile.einspeisung_kw or 0.0,
        netzbezug_kwh=zeile.netzbezug_kw or 0.0,
    )


async def _entladung_je_monat(
    db: AsyncSession, anlage_id: int, von: date, bis: date
) -> dict[tuple[int, int], float]:
    """Monats-Entladung aus den **Monats-Fakten** (ADR-002/P10) — nicht aus den Stunden.

    ⚠ **Die Quelle ist hier keine Geschmacksfrage.** Die Vollzyklen daneben
    stehen auch im Cockpit, im HA-Sensor `speicher_zyklen` und im
    PDF-Jahresbericht — alle aus `vollzyklen(Entladung, Kapazität)` mit der
    Entladung der Monats-Fakten. Wer sie hier aus `max(0, batterie_kw)` neu
    summiert, bekommt einen leicht anderen Wert und stellt damit zwei Zahlen
    unter denselben Namen: genau die Drift-Klasse, gegen die `vollzyklen`
    gebaut wurde (Docstring dort, „10,97 vs. 8,57").

    `inkl_nur_tageswerte=True`, weil diese Sicht eine **Zeitreihe** ist: der
    laufende Monat und jeder Monat ohne Monatsabschluss haben nie eine
    IMD-Zeile und würden sonst als Lücke erscheinen, obwohl die Tagesebene sie
    trägt (Fund N-121).
    """
    fakten = await lade_monats_fakten(
        db,
        anlage_id,
        von=(von.year, von.month),
        bis=(bis.year, bis.month),
        inkl_nur_tageswerte=True,
    )
    return {
        (f.jahr, f.monat): f.speicher.entladung_kwh
        for f in fakten
        if f.speicher.entladung_kwh > 0
    }


async def lade_potential_auswertung(
    db: AsyncSession,
    anlage_id: int,
    von: Optional[date] = None,
    bis: Optional[date] = None,
    kapazitaet_brutto_kwh: Optional[float] = None,
    leer_schwelle_prozent: Optional[float] = None,
) -> PotentialAuswertung:
    """Wertet den Zeitraum aus — gesamt **und** je Monat.

    Die Gesamt-Auswertung läuft über die **durchgehende** Reihe, nicht über die
    Summe der Monatswerte: ein Zyklus, dessen Überschuss am 31. anfällt und dessen
    Nacht in den 1. reicht, würde sonst an der Monatsgrenze zerschnitten. Die
    Monatswerte sind deshalb eine Aufschlüsselung **zur Anzeige**, ihre Summe kann
    minimal von der Gesamtzahl abweichen — bewusst, und in der Sicht so benannt.

    `kapazitaet_brutto_kwh` ist der Nenner der Vollzyklen — **brutto**, weil das
    der Kanon von `vollzyklen()` ist. Nicht zu verwechseln mit der *nutzbaren*
    Kapazität, mit der die Route die Potentialzahl ausweist: die eine Sicht
    fährt den Speicher rechnerisch durch (netto), die andere zählt Zyklen wie
    der Hersteller (brutto). Fehlt der Wert, bleiben die Zyklen `None`.

    `leer_schwelle_prozent` entscheidet, ab wann eine Nacht als „aufgebraucht"
    zählt (#379). Sie kommt aus `leer_schwelle_prozent()` und gilt für **beide**
    Ebenen — Gesamtauswertung und Monatsspalten. Die zwei getrennt zu versorgen
    wäre genau die Drift, gegen die dieser Bau steht: der Monatsanteil „leer"
    und die Gesamtaussage stünden dann auf verschiedenen Definitionen.
    """
    query = (
        select(TagesEnergieProfil)
        .where(TagesEnergieProfil.anlage_id == anlage_id)
        .order_by(TagesEnergieProfil.datum, TagesEnergieProfil.stunde)
    )
    if von is not None:
        query = query.where(TagesEnergieProfil.datum >= von)
    if bis is not None:
        query = query.where(TagesEnergieProfil.datum <= bis)

    zeilen = list((await db.execute(query)).scalars().all())
    if not zeilen:
        return PotentialAuswertung(
            gesamt=berechne_zusatzpotential([], leer_schwelle_prozent),
            monate=[], tage_mit_daten=0,
            von=None, bis=None,
        )

    gesamt = berechne_zusatzpotential(
        [_als_speicher_stunde(z) for z in zeilen], leer_schwelle_prozent
    )

    nach_monat: dict[tuple[int, int], list[TagesEnergieProfil]] = {}
    for zeile in zeilen:
        nach_monat.setdefault((zeile.datum.year, zeile.datum.month), []).append(zeile)

    entladung_je_monat = await _entladung_je_monat(
        db, anlage_id, zeilen[0].datum, zeilen[-1].datum
    )

    monate: list[MonatsPotential] = []
    for (jahr, monat), monats_zeilen in sorted(nach_monat.items()):
        teil = berechne_zusatzpotential(
            [_als_speicher_stunde(z) for z in monats_zeilen], leer_schwelle_prozent
        )

        soc_werte = [z.soc_prozent for z in monats_zeilen if z.soc_prozent is not None]
        stunden_mit_soc = len(soc_werte)
        anteil_voll = anteil_leer = None
        if stunden_mit_soc:
            anteil_voll = round(
                sum(1 for w in soc_werte if ist_voll(w)) / stunden_mit_soc * 100, 1
            )
            anteil_leer = round(
                sum(1 for w in soc_werte if ist_leer(w, leer_schwelle_prozent))
                / stunden_mit_soc * 100, 1
            )

        # Ladung und Netzladung je Stunde — die Netzladung ist eine Obergrenze
        # (Layer-Docstring), deshalb summiert und nicht am Monat neu gebildet.
        ladung = 0.0
        netz_ladung = 0.0
        for zeile in monats_zeilen:
            batterie = zeile.batterie_kw
            if batterie is None or batterie >= 0:
                continue
            ladung_h = -batterie
            ladung += ladung_h
            netz_ladung += netz_ladung_stunde_kwh(ladung_h, zeile.netzbezug_kw)

        spanne: Optional[SocSpanne] = soc_spanne(soc_werte)
        zyklen = vollzyklen(entladung_je_monat.get((jahr, monat)), kapazitaet_brutto_kwh)
        monate.append(MonatsPotential(
            jahr=jahr,
            monat=monat,
            nutzbares_zusatzpotential_kwh=round(teil.nutzbares_zusatzpotential_kwh, 1),
            ueberschuss_kwh=round(teil.ueberschuss_gesamt_kwh, 1),
            stunden_voll=teil.stunden_voll,
            zyklen_gesamt=teil.zyklen_gesamt,
            zyklen_leergelaufen=teil.zyklen_leergelaufen,
            stunden_mit_soc=stunden_mit_soc,
            spanne=SocSpanne(
                p10=round(spanne.p10, 1), p50=round(spanne.p50, 1),
                p90=round(spanne.p90, 1),
            ) if spanne else None,
            anteil_voll_prozent=anteil_voll,
            anteil_leer_prozent=anteil_leer,
            vollzyklen=round(zyklen, 1) if zyklen is not None else None,
            ladung_kwh=round(ladung, 1),
            netz_ladung_kwh=round(netz_ladung, 1),
        ))

    return PotentialAuswertung(
        gesamt=gesamt,
        monate=monate,
        tage_mit_daten=len({z.datum for z in zeilen}),
        von=zeilen[0].datum,
        bis=zeilen[-1].datum,
    )


__all__ = [
    "MonatsPotential",
    "PotentialAuswertung",
    "SOC_VOLL_PROZENT",
    "lade_potential_auswertung",
]
