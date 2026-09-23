"""Sourcing für den Sizing-Simulator (#358 Phase 3).

Trennung wie in ADR-001: die **Formeln** stehen in
`core/berechnungen/speicher_sizing.py`, hier liegt allein das Beschaffen —
Stundenreihe aus `TagesEnergieProfil`, Kapazität/Wirkungsgrad, Tarif.

**Kein Persist, kein Cache.** Das Konzept nannte Phase-3-Auswertungen „teuer
(8760 h × Slider-Schritte)"; gemessen läuft die volle Kurve über 355 Tage in
**Millisekunden** (reine Python-Schleife über ~8500 Stundenzeilen je Punkt).
Ein L2-Cache wäre Vorratshaltung gegen eine Vermutung — er kommt, wenn eine
Messung ihn verlangt, nicht vorher.

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
    SocNutzung,
    kalibriere_speicher,
    messe_soc_nutzung,
    sizing_kurve,
)
from backend.core.berechnungen.speicher_potential import leer_schwelle_prozent
from backend.core.investition_kennwerte import (
    aggregiere_speicher_basis,
    get_speicher_kapazitaet_kwh,
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
    #: Welchen Ladestands-Bereich die Anlage fährt — N-238: erst damit lässt
    #: sich eine gewollte Ladegrenze von Ladeverlusten unterscheiden.
    soc_nutzung: Optional[SocNutzung]
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

    ⛔ **Hier wird der Ladestand NICHT auf die Vorzeile umgerechnet — weil die
    Paarung die Frage gar nicht entscheidet** (N-387, 23.09.2026; zweite
    Ausnahme neben `speicher_wirtschaftlichkeit._lese_soc_am_periodenrand`,
    aber aus einem anderen Grund).

    Der Nachbar nebenan (`speicher_potential_service`) **paart** einen
    Ladestand mit einer Menge derselben Stunde — dort ist die Umrechnung eine
    reine Intervall-Zuordnung und richtig. `kalibriere_speicher` dagegen bildet
    eine **Differenz zweier Stundenmittel** und stellt sie einer einzelnen
    Stundenmenge gegenüber. Eine Differenz benachbarter Intervallmittel
    beschreibt den Fluss zwischen den Intervall-**Mitten**, also je zur Hälfte
    **zwei** Stunden: ``ΔSoC(s-1 → s) ≈ ½ (b_s + b_{s+1})``, gegenübergestellt
    wird aber ``b_s`` allein. Beide Fassungen liegen damit um eine halbe Stunde
    daneben, und zwar in entgegengesetzte Richtungen.

    **Gemessen** (23.09.2026, **reine** Demo-Reihe: 4 800 Stundenzeilen, alle
    mit forward-Stundenmittel geseedet; Wahrheit im Seed 10,0 kWh je 100 % SoC
    und Roundtrip 1,00):

    ===================  ==================  ==================  ===========  ==============
    Paarung              Laden (Median)      Entladen (Median)   Roundtrip    Ergebnis
    ===================  ==================  ==================  ===========  ==============
    **Zeile (heute)**    10,03 (n 639)       11,11 (n 329)       1,108        **None**
    Vorzeile             12,44 (n 593)       13,62 (n 275)       1,095        **None**
    ===================  ==================  ==================  ===========  ==============

    **Beide verfehlen, und beide fallen aus dem Plausibilitätsband** (Roundtrip
    > ``ROUNDTRIP_MAX``) — die Funktion liefert in beiden Fassungen ``None``,
    der Aufrufer nimmt die **gepflegten** Parameter, und am Endpunkt bewegt sich
    keine Zahl. Die Paarung ist hier also nicht die Stellschraube: **keine der
    beiden ist überlegen**, die Zeilen-Paarung bleibt schlicht, weil sie der
    Bestand ist.

    ⭐ **Die Lösung ist die Formel, nicht die Paarung** — der Hub gehört gegen
    das **Mittel der zwei angrenzenden Stundenmengen** (``½ (b_s + b_{s+1})``)
    statt gegen eine. Das ist ein Layer-Eingriff (ADR-001,
    ``core/berechnungen/speicher_sizing.kalibriere_speicher``), war nicht
    Gegenstand dieses Baus und ist als **eigener Fund** vorzulegen.

    ⛔ **Was hier bis zur Nachmessung am 23.09.2026 stand, war falsch:** eine
    Tabelle „Zeile 9,99/9,99 gegen Vorzeile 11,11/9,82", erhoben auf einer
    **gemischten** Kopie (4 800 neu geseedete Zeilen neben 2 640 Altzeilen vom
    13.09.2025–31.12.2025, die noch die alte Seed-Konvention trugen). Die
    „perfekten" 9,99 waren die Altzeilen. *Eine Messung ist nur so gut wie die
    Reinheit ihrer Stichprobe.*
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


async def lade_sizing_auswertung(
    db: AsyncSession,
    anlage_id: int,
    von: Optional[date] = None,
    bis: Optional[date] = None,
    richtpreis_eur_je_kwh: Optional[float] = None,
) -> SizingAuswertung:
    """Baut die Sizing-Kurve für eine Anlage.

    Die **Kalibrierung** läuft über die gesamte geladene Reihe (ihre Bilanzprobe
    sortiert die Stunden mit invertiertem Vorzeichen selbst aus), die
    **Simulation** nur über vollständige Tage. Glückt die Kalibrierung nicht,
    wird mit den gepflegten Parametern gerechnet — und die Antwort sagt es über
    `basis_kalibriert`, damit die Sicht die Unsicherheit ausweisen kann, statt
    stillschweigend eine andere Grundlage zu verwenden.

    ``richtpreis_eur_je_kwh`` ist der Nachrüstpreis, mit dem die Amortisation
    einer gedachten Erweiterung bewertet wird. ``None`` heißt „nimm den
    Richtwert" (:data:`RICHTPREIS_EUR_JE_KWH`); ein übergebener Wert ist die
    **eigene Zahl des Anwenders** und wird nirgends gespeichert — er gehört zur
    Frage, nicht zum Gerät (Entscheid Gernot 2026-08-18, N-274: „flüchtiger Wert
    neben dem Slider"). Deshalb ist er ein Parameter und kein Feld an der
    Investition: die graue CO₂-Last ist eine **Eigenschaft** des Geräts und hat
    zu Recht ein Override-Feld, ein Was-wäre-wenn-Preis ist es nicht.
    """
    preis = RICHTPREIS_EUR_JE_KWH if richtpreis_eur_je_kwh is None else richtpreis_eur_je_kwh
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

    # ⚠ Nur die HEUTE laufenden Speicher (N-546, Radiocarbonat T89667 #358).
    # Stichtag `date.today()` aus demselben Grund wie der Tarif (Modul-Docstring
    # oben): die Frage ist nach vorn gerichtet — „lohnt sich ein größerer
    # Speicher?" steht auf dem Gerät, das der Anwender JETZT hat; die Historie
    # liefert nur das Verbrauchs- und PV-Muster. Ein abgelöstes Gerät zog sonst
    # die Kapazität hoch und — über das Minimum in `aggregiere_speicher_basis`
    # — den Wirkungsgrad dauerhaft herunter.
    heute = date.today()
    res = await db.execute(
        select(Investition).where(
            Investition.anlage_id == anlage_id,
            Investition.typ == InvestitionTyp.SPEICHER.value,
            Investition.aktiv.is_(True),
        )
    )
    speicher = [
        i for i in res.scalars().all()
        if not i.stilllegungsdatum or i.stilllegungsdatum >= heute
    ]
    gepflegte_kapazitaet, gepflegter_wirkungsgrad = aggregiere_speicher_basis(speicher)

    # Leer-Schwelle wie in Phase 2 nebenan (#379). `aggregiere_speicher_basis`
    # liefert **netto** (mit stillem Brutto-Fallback), die Brutto-Summe fehlt hier
    # noch — ohne sie stünden im selben Hub zwei Definitionen von „leer".
    summe_brutto = sum(get_speicher_kapazitaet_kwh(s) or 0 for s in speicher)
    leer_schwelle = leer_schwelle_prozent(summe_brutto or None, gepflegte_kapazitaet)

    tarife = await lade_tarife_fuer_anlage(db, anlage_id)
    bezug_cent = resolve_strompreis_for_komponente(tarife, "allgemein")
    einspeise_cent = resolve_einspeiseverguetung_cent(tarife)

    leer = SizingAuswertung(
        kurve=[], basis_kapazitaet_kwh=0.0, basis_roundtrip=0.0,
        basis_kalibriert=False, kalibrierung=None, soc_nutzung=None,
        gepflegte_kapazitaet_kwh=gepflegte_kapazitaet,
        gepflegter_wirkungsgrad_prozent=gepflegter_wirkungsgrad,
        tage_mit_daten=0, tage_simuliert=0, von=None, bis=None,
        anzahl_speicher=len(speicher),
        bezug_preis_cent=bezug_cent, einspeise_verg_cent=einspeise_cent,
        richtpreis_eur_je_kwh=preis,
    )
    if not zeilen:
        return leer

    # N-387: hier bleibt die Zeilen-Paarung — die Begründung samt Messung steht
    # im Docstring von `_als_sizing_stunde`.
    stunden = [_als_sizing_stunde(z) for z in zeilen]
    simulierbar = _vollstaendige_tage(stunden)
    tage_mit_daten = len({z.datum for z in zeilen})
    tage_simuliert = len({z.zeit.date() for z in simulierbar})

    # ⚠ **Die Aufschlüsselung nennt nur die HEUTE laufenden Geräte**
    # (Nachlese 4.0.50, A5). `TagesEnergieProfil.soc_je_speicher` trägt die
    # Ladestände **aller** Geräte, die den Tag über gemessen wurden — auch die
    # eines inzwischen ausgebauten. `messe_soc_nutzung` faltet sie ungefiltert
    # zu `median_je_speicher`, und die Sicht beschriftet daraus „Speicher <id>"
    # (`v4/SpeicherSizingIST.tsx`). Nach N-546 stand deshalb ein Widerspruch in
    # einem Block: der Hinweistext hängt an `anzahl_speicher` (gefiltert, „1
    # Speicher"), die Liste darüber zeigte zwei Zeilen — eine davon für ein
    # Gerät, das nirgends sonst mehr vorkommt.
    #
    # ⭐ **Gefiltert wird der EINGANG, nicht das Ergebnis** — der Layer
    # (`core/berechnungen/speicher_sizing.messe_soc_nutzung`) bleibt
    # unverändert: er soll auswerten, was man ihm gibt, und nicht wissen
    # müssen, welche Investition heute läuft. Dieselbe Arbeitsteilung wie bei
    # den Kapazitäten oben.
    laufende_ids = {str(s.id) for s in speicher}
    soc_je_speicher = [
        {k: v for k, v in (eintrag or {}).items() if str(k) in laufende_ids} or None
        for eintrag in (z.soc_je_speicher for z in zeilen)
    ]
    soc_nutzung = messe_soc_nutzung(stunden, soc_je_speicher, leer_schwelle)
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
               "soc_nutzung": soc_nutzung,
               "tage_mit_daten": tage_mit_daten,
               "von": zeilen[0].datum, "bis": zeilen[-1].datum}
        )

    bewertung = SizingBewertung(
        bezug_preis_cent=bezug_cent,
        einspeise_verg_cent=einspeise_cent,
        tage_im_zeitraum=tage_simuliert,
        richtpreis_eur_je_kwh=preis,
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
        soc_nutzung=soc_nutzung,
        gepflegte_kapazitaet_kwh=gepflegte_kapazitaet,
        gepflegter_wirkungsgrad_prozent=gepflegter_wirkungsgrad,
        tage_mit_daten=tage_mit_daten,
        tage_simuliert=tage_simuliert,
        von=zeilen[0].datum,
        bis=zeilen[-1].datum,
        anzahl_speicher=len(speicher),
        bezug_preis_cent=bezug_cent,
        einspeise_verg_cent=einspeise_cent,
        richtpreis_eur_je_kwh=preis,
    )


__all__ = [
    "MIN_TAGE_FUER_AUSSAGE",
    "SIZING_FAKTOREN",
    "SizingAuswertung",
    "lade_sizing_auswertung",
]
