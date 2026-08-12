"""Sourcing für den Sizing-Simulator (#358 Phase 3).

Trennung wie in ADR-001: die **Formeln** stehen in
`core/berechnungen/speicher_sizing.py`, hier liegt allein das Beschaffen —
Stundenreihe aus `TagesEnergieProfil`, Kapazität/Wirkungsgrad, Tarif.

**Kein Persist, kein Cache.** Das Konzept nannte Phase-3-Auswertungen „teuer
(8760 h × Slider-Schritte)"; gemessen läuft die volle Kurve über 355 Tage in
**Millisekunden** (reine Python-Schleife über ~8500 Stundenzeilen je Punkt).
Ein L2-Cache wäre Vorratshaltung gegen eine Vermutung — er kommt, wenn eine
Messung ihn verlangt, nicht vorher.

⚠ **Der SoC in `TagesEnergieProfil` ist anlagenweit, nicht je Gerät** (die
Tabelle hat `anlage_id`, keine `investition_id`) — wie schon bei Phase 2. Bei
mehreren Speichern ist die Kalibrierung ein Mischwert, und die Aussage gilt für
die Anlage als Ganzes; die Route gibt `anzahl_speicher` mit aus.

⚠ **Bewusst der HEUTE gültige Tarif** (deshalb steht dieses Modul in
`P8_BASELINE_AUSNAHMEN`): die Sicht beantwortet keine historische Frage
(„was hat der Speicher letztes Jahr gebracht?" — das ist Cockpit → Jahr),
sondern eine nach vorn gerichtete („lohnt sich ein Zukauf?"). Ein Zukauf wird
zum künftigen Preis bezahlt, nicht zum Preis des ausgewerteten Zeitraums. Die
Antwort weist den verwendeten Tarif aus, statt ihn zu verschweigen.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.routes.strompreise import (
    lade_tarife_fuer_anlage,
    resolve_einspeiseverguetung_cent,
    resolve_strompreis_for_komponente,
)
from backend.core.berechnungen.speicher_sizing import (
    RICHTPREIS_EUR_JE_KWH,
    Kalibrierung,
    SizingBewertung,
    SizingPunkt,
    SizingStunde,
    kalibriere_speicher,
    sizing_kurve,
)
from backend.core.investition_kennwerte import get_speicher_nutzbare_kapazitaet_kwh
from backend.core.investition_parameter import (
    PARAM_SPEICHER,
    PARAM_SPEICHER_DEFAULTS,
)
from backend.models.investition import Investition, InvestitionTyp
from backend.models.tages_energie_profil import TagesEnergieProfil

#: Die Punkte der Kurve: 50 % bis 200 % der heutigen Kapazität in 10er-Schritten
#: (Konzept §3). Feiner als nötig wäre teuer, gröber zwingt die Sicht zum
#: Nachladen bei jedem Slider-Schritt — 16 Punkte kommen in einer Antwort mit,
#: der Slider liest daraus und fragt nie wieder.
SIZING_FAKTOREN: tuple[float, ...] = tuple(round(0.5 + 0.1 * i, 2) for i in range(16))

#: Ab hier trägt die Aussage. Das Konzept nennt „6–12 Monate Stundendaten";
#: die Robustheitsprobe der Vorprüfung (nur Feb–Jul hochgerechnet 62 €/Jahr
#: gegen 67 €/Jahr über das volle Jahr) hat die untere Kante bestätigt.
MIN_TAGE_FUER_AUSSAGE: int = 180

#: Ein Tag geht nur vollständig in die Simulation ein — eine halbe Nacht
#: verschöbe den Speicherstand in den nächsten Tag hinein.
STUNDEN_JE_TAG: int = 24


@dataclass
class SizingAuswertung:
    """Alles, was die Sicht braucht — Kurve, Basis und ihre Herkunft."""

    kurve: list[SizingPunkt]
    #: Die Basis, mit der simuliert wurde.
    basis_kapazitaet_kwh: float
    basis_roundtrip: float
    #: `True` = aus der SoC-Bewegung gemessen, `False` = gepflegte Parameter.
    basis_kalibriert: bool
    kalibrierung: Optional[Kalibrierung]
    #: Gepflegte Werte — stehen auch bei geglückter Kalibrierung daneben, damit
    #: die Sicht den Unterschied benennen kann statt ihn zu verstecken.
    gepflegte_kapazitaet_kwh: Optional[float]
    gepflegter_wirkungsgrad_prozent: float

    tage_mit_daten: int
    tage_simuliert: int
    von: Optional[date]
    bis: Optional[date]
    anzahl_speicher: int

    bezug_preis_cent: Optional[float]
    einspeise_verg_cent: Optional[float]
    richtpreis_eur_je_kwh: float

    @property
    def historie_reicht(self) -> bool:
        return self.tage_simuliert >= MIN_TAGE_FUER_AUSSAGE


def _als_sizing_stunde(zeile: TagesEnergieProfil) -> SizingStunde:
    """Stundenmittel in kW ⇒ kWh der Stunde: numerisch identisch, anders benannt.

    Dieselbe Umbenennung wie in `speicher_potential_service.py`: die Spalten
    heißen `_kw`, tragen aber das Stundenmittel; über eine Stunde integriert ist
    der Zahlenwert derselbe. Der Layer rechnet ausdrücklich in kWh.
    """
    return SizingStunde(
        zeit=datetime.combine(zeile.datum, datetime.min.time())
        + timedelta(hours=zeile.stunde),
        pv_kwh=zeile.pv_kw,
        verbrauch_kwh=zeile.verbrauch_kw,
        soc_prozent=zeile.soc_prozent,
        batterie_kwh=zeile.batterie_kw,
        einspeisung_kwh=zeile.einspeisung_kw,
        netzbezug_kwh=zeile.netzbezug_kw,
    )


def _vollstaendige_tage(stunden: list[SizingStunde]) -> list[SizingStunde]:
    """Nur Tage mit 24 Stunden **und** durchgehendem PV-/Verbrauchswert.

    Ein angebrochener Tag ist für die Simulation schlimmer als gar keiner: der
    Speicherstand liefe über die Lücke hinweg weiter und trüge einen Ladestand
    in den nächsten Tag, den es nie gab.
    """
    nach_tag: dict[date, list[SizingStunde]] = {}
    for zeile in stunden:
        nach_tag.setdefault(zeile.zeit.date(), []).append(zeile)
    vollstaendig: list[SizingStunde] = []
    for tag in sorted(nach_tag):
        zeilen = nach_tag[tag]
        if len(zeilen) != STUNDEN_JE_TAG:
            continue
        if any(z.pv_kwh is None or z.verbrauch_kwh is None for z in zeilen):
            continue
        vollstaendig.extend(zeilen)
    return vollstaendig


def _gepflegte_basis(speicher: list[Investition]) -> tuple[Optional[float], float]:
    """(nutzbare Kapazität, Wirkungsgrad %) aus den gepflegten Parametern.

    Netto, nicht brutto — `get_speicher_nutzbare_kapazitaet_kwh` nennt genau
    diesen Fall („simuliert oder prognostiziert eine Energiemenge"). Mehrere
    Speicher werden addiert; der Wirkungsgrad ist der kleinste gepflegte, weil
    die Kette nicht besser sein kann als ihr schwächstes Glied.
    """
    kapazitaeten = [get_speicher_nutzbare_kapazitaet_kwh(s) for s in speicher]
    summe = sum(k for k in kapazitaeten if k)
    default = float(PARAM_SPEICHER_DEFAULTS["wirkungsgrad_prozent"])
    wirkungsgrade = [
        float((s.parameter or {}).get(PARAM_SPEICHER["WIRKUNGSGRAD_PROZENT"]) or default)
        for s in speicher
    ]
    return (summe or None), (min(wirkungsgrade) if wirkungsgrade else default)


async def lade_sizing_auswertung(
    db: AsyncSession,
    anlage_id: int,
    von: Optional[date] = None,
    bis: Optional[date] = None,
) -> SizingAuswertung:
    """Baut die Sizing-Kurve für eine Anlage.

    Die **Kalibrierung** läuft über die gesamte geladene Reihe (ihre Bilanzprobe
    sortiert die Stunden mit invertiertem Vorzeichen selbst aus), die
    **Simulation** nur über vollständige Tage. Glückt die Kalibrierung nicht,
    wird mit den gepflegten Parametern gerechnet — und die Antwort sagt es über
    `basis_kalibriert`, damit die Sicht die Unsicherheit ausweisen kann, statt
    stillschweigend eine andere Grundlage zu verwenden.
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

    speicher = list((await db.execute(
        select(Investition)
        .where(Investition.anlage_id == anlage_id)
        .where(Investition.typ == InvestitionTyp.SPEICHER.value)
    )).scalars().all())
    gepflegte_kapazitaet, gepflegter_wirkungsgrad = _gepflegte_basis(speicher)

    tarife = await lade_tarife_fuer_anlage(db, anlage_id)
    bezug_cent = resolve_strompreis_for_komponente(tarife, "allgemein")
    einspeise_cent = resolve_einspeiseverguetung_cent(tarife)

    leer = SizingAuswertung(
        kurve=[], basis_kapazitaet_kwh=0.0, basis_roundtrip=0.0,
        basis_kalibriert=False, kalibrierung=None,
        gepflegte_kapazitaet_kwh=gepflegte_kapazitaet,
        gepflegter_wirkungsgrad_prozent=gepflegter_wirkungsgrad,
        tage_mit_daten=0, tage_simuliert=0, von=None, bis=None,
        anzahl_speicher=len(speicher),
        bezug_preis_cent=bezug_cent, einspeise_verg_cent=einspeise_cent,
        richtpreis_eur_je_kwh=RICHTPREIS_EUR_JE_KWH,
    )
    if not zeilen:
        return leer

    stunden = [_als_sizing_stunde(z) for z in zeilen]
    simulierbar = _vollstaendige_tage(stunden)
    tage_mit_daten = len({z.datum for z in zeilen})
    tage_simuliert = len({z.zeit.date() for z in simulierbar})

    kalibrierung = kalibriere_speicher(stunden)
    if kalibrierung is not None:
        basis = kalibrierung
    elif gepflegte_kapazitaet:
        basis = Kalibrierung(
            kapazitaet_kwh=gepflegte_kapazitaet,
            ladung_je_100_prozent_kwh=gepflegte_kapazitaet
            / (gepflegter_wirkungsgrad / 100.0),
            roundtrip=gepflegter_wirkungsgrad / 100.0,
            paare_laden=0, paare_entladen=0, stunden_verworfen=0,
        )
    else:
        # Weder gemessen noch gepflegt: es gibt keine Basis, auf die sich ein
        # „50 %–200 %" beziehen könnte. Eine erfundene Default-Kapazität wäre
        # hier schlimmer als die leere Antwort, weil die Kurve echt aussieht.
        return SizingAuswertung(
            **{**vars(leer),
               "tage_mit_daten": tage_mit_daten,
               "von": zeilen[0].datum, "bis": zeilen[-1].datum}
        )

    bewertung = SizingBewertung(
        bezug_preis_cent=bezug_cent,
        einspeise_verg_cent=einspeise_cent,
        tage_im_zeitraum=tage_simuliert,
        richtpreis_eur_je_kwh=RICHTPREIS_EUR_JE_KWH,
    )
    kurve = (
        sizing_kurve(simulierbar, basis, SIZING_FAKTOREN, bewertung=bewertung)
        if simulierbar else []
    )

    return SizingAuswertung(
        kurve=kurve,
        basis_kapazitaet_kwh=basis.kapazitaet_kwh,
        basis_roundtrip=basis.roundtrip,
        basis_kalibriert=kalibrierung is not None,
        kalibrierung=kalibrierung,
        gepflegte_kapazitaet_kwh=gepflegte_kapazitaet,
        gepflegter_wirkungsgrad_prozent=gepflegter_wirkungsgrad,
        tage_mit_daten=tage_mit_daten,
        tage_simuliert=tage_simuliert,
        von=zeilen[0].datum,
        bis=zeilen[-1].datum,
        anzahl_speicher=len(speicher),
        bezug_preis_cent=bezug_cent,
        einspeise_verg_cent=einspeise_cent,
        richtpreis_eur_je_kwh=RICHTPREIS_EUR_JE_KWH,
    )


__all__ = [
    "MIN_TAGE_FUER_AUSSAGE",
    "SIZING_FAKTOREN",
    "SizingAuswertung",
    "lade_sizing_auswertung",
]
