"""
Strompreis-Aggregator — Verbrauchsgewichteter Monats-Durchschnittspreis.

Berechnet aus stündlichen TagesEnergieProfil-Daten den effektiven
Durchschnitts-Strompreis für einen Monat:

    Ø_effektiv = Σ(strompreis_cent × netzbezug_kw) / Σ(netzbezug_kw)

Nutzt nur `strompreis_cent` (Endpreis aus HA-Sensor, z.B. Tibber/aWATTar),
NICHT `boersenpreis_cent` — Börsenpreis ist kein Endkundenpreis.

Wird als Vorschlag im Monatsabschluss-Wizard verwendet (Phase 2 aus
docs/archive/KONZEPT-STROMPREIS-MITSCHRIFT.md).
"""

from __future__ import annotations

import logging
from calendar import monthrange
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Optional

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.berechnungen.slot_konvention import forward_werte_je_backward_zeile
from backend.core.berechnungen.zeittarif import (
    gewichteter_arbeitspreis_cent,
    hat_zeitfenster,
    preis_je_slot,
)
from backend.models.tages_energie_profil import TagesEnergieProfil

logger = logging.getLogger(__name__)


def monats_fenster(jahr: int, monat: int) -> tuple[date, date]:
    """``[erster Tag, erster Tag des Folgemonats)`` — die Monatsgrenzen als **Bereich**.

    ⛔ **Nicht auf ``extract("year"/"month", datum)`` zurückdrehen.** Eine Funktion
    über der Spalte macht den Index ``ix_tep_anlage_datum (anlage_id, datum)`` für
    die Monatseingrenzung unbrauchbar: SQLite grenzt dann nur noch auf die *Anlage*
    ein und liest je Aufruf **alle** ihre Stundenzeilen — auch für einen Monat, der
    gar keine hat. Gemessen am 15.09.2026 an der produktiven Anlage (16.391 Zeilen):
    **117 solcher Aufrufe je ``GET /monatsdaten/aggregiert``**, zusammen rund 1,4 s
    von 2,4 s. Der Wächter dazu ist
    ``backend/tests/test_query_budget_monats_fakten.py``.
    """
    return date(jahr, monat, 1), date(jahr + (monat == 12), (monat % 12) + 1, 1)


# =============================================================================
# Die EINE Bauform der Preis-Paarung (N-387)
# =============================================================================


async def _zeilen_mit_gepaartem_preis(
    db: AsyncSession,
    anlage_id: int,
    *,
    ab: Optional[date] = None,
    bis_inklusive: Optional[date] = None,
    bis_exklusive: Optional[date] = None,
    nur_wenn_gemessen: bool = False,
) -> list[tuple]:
    """Stundenzeilen des Fensters **samt dem Preis, der zu ihrer Stunde gehört**.

    ⭐ **Die eine Bauform für alle Preis-Leser dieses Moduls und des
    Speicher-Dashboards** (N-387). Die Menge einer Zeile ``s`` (``netzbezug_kw``,
    ``pv_kw``, ``einspeisung_kw``) liegt **backward** (`[s-1, s)`), ihr
    ``strompreis_cent`` **forward** (`[s, s+1)`) — gepaart wird deshalb über
    ``slot_konvention.forward_werte_je_backward_zeile``, also mit der Vorzeile
    und über die Tagesgrenze hinweg mit Zeile 23 des Vortags.

    ⛔ **Python-Shift statt SQL-Self-Join — die Wahl ist begründet.** Ein Join
    auf ``stunde − 1`` bräuchte für die Tagesgrenze SQLite-eigene
    Datumsarithmetik (``date(datum, '-1 day')``) und für die Bestandsgrenze
    (``SLOT_PAARUNG_VORZEILE_AB``) ein ``CASE`` — die Regel stünde dann ein
    zweites Mal in SQL, und genau das soll der benannte Helfer verhindern.
    Die Zahl der Abfragen bleibt unverändert (der Wächter
    ``test_query_budget_monats_fakten.py`` zählt Abfragen, nicht Zeilen);
    geladen werden sieben **skalare** Spalten, keine JSON-Spalte.

    ⚠ **Das Fenster beginnt einen Tag früher**, damit die Zeile 0 des ersten
    Tages ihren Preis noch bekommt; diese Vorzeilen werden nicht ausgeliefert.

    ⭐ **``nur_wenn_gemessen`` ist der Vorabtest für die Monats-Aggregate.** Sie
    liefern ohne gemessenen Preis **gar kein** Ergebnis — dann lohnt es nicht,
    die Stundenzeilen überhaupt zu laden. Ein ``EXISTS`` über **dasselbe**
    Fenster (einschließlich des Vorzeilen-Tages!) beantwortet die Frage in
    einer Abfrage, die der Index bedient. **Gemessen** (23.09.2026, r28-Kopie
    mit 8 304 Stundenzeilen und **ohne** eine einzige Preiszeile, je 5 Läufe):
    **21,7 ms ohne den Vorabtest, 0,8 ms mit ihm** — der Bestand (SQL-`GROUP BY`)
    braucht dort 1,4 ms. Auf einer Kopie **mit** Preisen ändert er
    erwartungsgemäß nichts (7,5 ms Bestand, 61,6 ms mit Paarung).
    ⛔ **Für ``lade_slot_kosten_je_tag`` gilt das NICHT** — dort trägt die
    Kaskade den Tag auch ohne Messung (abgerechneter Ø, Vertragspreis), ein
    leeres Ergebnis wäre dort ein Datenverlust. Deshalb ein Schalter und keine
    eingebaute Abkürzung.

    Returns:
        ``[(zeile, preis_cent | None), …]`` in Zeitordnung — nur Zeilen im
        angefragten Fenster.
    """
    bedingungen = [TagesEnergieProfil.anlage_id == anlage_id]
    if ab is not None:
        bedingungen.append(TagesEnergieProfil.datum >= ab - timedelta(days=1))
    if bis_inklusive is not None:
        bedingungen.append(TagesEnergieProfil.datum <= bis_inklusive)
    if bis_exklusive is not None:
        bedingungen.append(TagesEnergieProfil.datum < bis_exklusive)

    if nur_wenn_gemessen:
        gemessen = await db.execute(
            select(TagesEnergieProfil.id)
            .where(and_(*bedingungen, TagesEnergieProfil.strompreis_cent.isnot(None)))
            .limit(1)
        )
        if gemessen.first() is None:
            return []

    result = await db.execute(
        select(
            TagesEnergieProfil.datum,
            TagesEnergieProfil.stunde,
            TagesEnergieProfil.netzbezug_kw,
            TagesEnergieProfil.pv_kw,
            TagesEnergieProfil.einspeisung_kw,
            TagesEnergieProfil.strompreis_cent,
            TagesEnergieProfil.created_at,
        )
        .where(and_(*bedingungen))
        .order_by(TagesEnergieProfil.datum, TagesEnergieProfil.stunde)
    )
    zeilen = result.all()
    preise = forward_werte_je_backward_zeile(zeilen, "strompreis_cent")
    return [
        (z, p) for z, p in zip(zeilen, preise)
        if ab is None or z.datum >= ab
    ]


@dataclass
class StrompreisAggregat:
    """Ergebnis der Monats-Strompreis-Aggregation."""
    gewichtet_cent: Optional[float]  # Verbrauchsgewichteter Ø (ct/kWh)
    arithmetisch_cent: float         # Einfacher Ø aller Stunden (ct/kWh)
    abgedeckte_stunden: int          # Stunden mit Preisdaten
    sollstunden: int                 # Theoretische Stunden im Monat
    #: Der mit dem **Eigenverbrauch** gewichtete Ø derselben Preiszeilen (SOLL
    #: Flex-Tarife **A-2**): vermiedener Bezug je Slot = max(0, PV − Einspeisung).
    #: ``None``, wenn der Monat keinen vermiedenen Bezug in Preiszeilen trägt.
    #: Bis 18.09.2026 kannte nur die Tagesebene diesen Preis
    #: (``SlotKosten.ev_mittel_cent``); Monat, Jahr, PDF und HA-Export
    #: bewerteten die Ersparnis weiter mit dem bezugsgewichteten Ø — an einem
    #: dynamischen Tarif systematisch zu hoch (Flex-Prüfung §12, Befund a).
    ev_gewichtet_cent: Optional[float] = None

    @property
    def abdeckung(self) -> float:
        """Abdeckung als Anteil (0..1)."""
        return self.abgedeckte_stunden / self.sollstunden if self.sollstunden > 0 else 0

    @property
    def konfidenz(self) -> int:
        """Konfidenz-Score basierend auf Abdeckung."""
        if self.abdeckung > 0.95:
            return 95
        if self.abdeckung > 0.70:
            return 80
        return 60


async def berechne_monats_durchschnittspreis(
    anlage_id: int, jahr: int, monat: int, db: AsyncSession
) -> Optional[StrompreisAggregat]:
    """
    Berechnet den verbrauchsgewichteten Monats-Durchschnittspreis.

    Nur Stunden mit `strompreis_cent IS NOT NULL` werden berücksichtigt.
    Negativer Netzbezug wird auf 0 geclampt (Daten-Glitches).

    ⭐ **HA-Bauform E4e:** deckt der Kosten-Kanal (``services/kanal/kosten.py``) den Monat, kommt das Aggregat aus den
    Kanal-Δ (``kanal/preis_leser.py``, Δ Kosten ÷ Δ bewertete kWh wie HAs Kostensensor) — sonst wie bisher aus den
    Stundenzeilen (Lesart 1). Dieselbe Wahl wie ``lade_preis_aggregate_je_monat``.

    Returns:
        StrompreisAggregat oder None wenn keine Preisdaten vorhanden.
    """
    from backend.services.kanal.preis_leser import preis_monat

    gedeckt, aus_kanal = await preis_monat(db, anlage_id, jahr, monat)
    if gedeckt:
        return aus_kanal
    _von, _bis = monats_fenster(jahr, monat)
    # N-387: Menge backward, Preis forward — gepaart über die Vorzeile.
    rows = [
        (preis, z.netzbezug_kw, z.pv_kw, z.einspeisung_kw)
        for z, preis in await _zeilen_mit_gepaartem_preis(
            db, anlage_id, ab=_von, bis_exklusive=_bis, nur_wenn_gemessen=True
        )
        if preis is not None
    ]

    if not rows:
        return None

    # Verbrauchsgewichteter Durchschnitt
    summe_kosten = 0.0   # ct (preis × kWh)
    summe_kwh = 0.0      # kWh
    summe_preise = 0.0   # ct (für arithmetischen Ø)
    # A-2: dieselben Preiszeilen, mit dem VERMIEDENEN Bezug gewichtet —
    # dieselbe Bildung wie `SlotKosten.ev_mittel_cent` auf der Tagesebene.
    summe_ev_kosten = 0.0
    summe_ev_kwh = 0.0

    for preis, bezug, pv, einspeisung in rows:
        if preis is None:
            continue
        kw = max(0.0, bezug or 0.0)  # Negativen Netzbezug auf 0 clampen
        summe_kosten += preis * kw    # ct × kW × 1h = ct·kWh
        summe_kwh += kw
        summe_preise += preis
        ev = max(0.0, float(pv or 0.0) - float(einspeisung or 0.0))
        summe_ev_kosten += preis * ev
        summe_ev_kwh += ev

    n = len(rows)
    tage_im_monat = monthrange(jahr, monat)[1]
    sollstunden = tage_im_monat * 24

    gewichtet = round(summe_kosten / summe_kwh, 2) if summe_kwh > 0 else None
    arithmetisch = round(summe_preise / n, 2) if n > 0 else 0.0

    return StrompreisAggregat(
        gewichtet_cent=gewichtet,
        arithmetisch_cent=arithmetisch,
        abgedeckte_stunden=n,
        sollstunden=sollstunden,
        ev_gewichtet_cent=(
            round(summe_ev_kosten / summe_ev_kwh, 2) if summe_ev_kwh > 0 else None
        ),
    )


# =============================================================================
# Dieselbe Messung für ALLE Monate — eine Abfrage statt einer je Monat
# =============================================================================


class PreisMessung:
    """Die gemessenen Monats-Aggregate **einer** Anlage, einmal je Anfrage geladen.

    ⭐ **Sie hält die Messung, nicht den aufgelösten Preis.** Das ist der
    Unterschied, auf den es ankommt: Stufe 2 der Kaskade („gemessen") ist von
    ``stammpreis_override`` unabhängig — derselbe gemessene Monats-Ø gilt für den
    Netzbezug **und** für die Wallbox. Ein Cache über dem *Ergebnis* konnte das
    nicht, weshalb ``wallbox_preis_effektiv_cent`` bis hierher bewusst ohne Cache
    lief und die Messung ein zweites Mal anstieß (``monats_fakten._lade_tarif``).

    Ein Monat **ohne** Preiszeilen fehlt im Dict — genau wie
    ``berechne_monats_durchschnittspreis`` dort ``None`` liefert. Die
    Unterscheidung „kein Eintrag" gegen „Eintrag ohne gewichteten Wert" bleibt
    damit erhalten (letzteres: Preise vorhanden, Netzbezug überall 0).
    """

    __slots__ = ("anlage_id", "_je_monat")

    def __init__(self, anlage_id: int, je_monat: dict[tuple[int, int], StrompreisAggregat]):
        self.anlage_id = anlage_id
        self._je_monat = je_monat

    def hole(self, jahr: int, monat: int) -> Optional[StrompreisAggregat]:
        return self._je_monat.get((jahr, monat))

    def __len__(self) -> int:  # für Proben und Protokoll
        return len(self._je_monat)


async def lade_preis_aggregate_je_monat(
    db: AsyncSession,
    anlage_id: int,
    *,
    von: Optional[date] = None,
    bis: Optional[date] = None,
) -> PreisMessung:
    """Alle Monats-Aggregate auf einmal — dieselbe Aussage wie
    ``berechne_monats_durchschnittspreis``, **ein** Query.

    Gegenstück zum Einzelmonat für Aufrufer, die eine ganze Historie aufbereiten
    (``services/monats_fakten/``): je Monat einzeln zu fragen waren an der
    produktiven Anlage **117 Abfragen** je ``GET /monatsdaten/aggregiert``.
    Bauform wie ``einspeise_erloes_service.get_neg_preis_einspeisung_je_monat``.

    ⚠ **Der Clamp trägt.** Ein negativer Netzbezug muss auf 0 **geclampt** und
    nicht verworfen werden; nimmt man ``max(…, 0)`` heraus, meldet
    ``backend/tests/test_preis_aggregat_symmetrie.py`` drei Proben rot
    (Gegenprobe 15.09.2026).

    ⭐ **Seit N-387 (23.09.2026) aggregiert diese Funktion in Python statt in
    ``GROUP BY``** — nicht aus Geschmack: der Preis einer Menge steht in der
    **Vorzeile** (Menge backward, Preis forward), und die Tagesgrenze dieser
    Paarung ließe sich in SQL nur mit dialekteigener Datumsarithmetik
    nachbauen. Die Regel steht deshalb genau einmal
    (``slot_konvention.forward_werte_je_backward_zeile``), die Abfrage bleibt
    **eine** — das Budget aus ``test_query_budget_monats_fakten.py`` zählt
    Abfragen, nicht Zeilen. Das frühere ``COALESCE`` in SQL ist damit
    gegenstandslos; ``float(… or 0.0)`` sagt dasselbe direkt.

    Die Gleichheit beider Wege hält ``backend/tests/test_preis_aggregat_symmetrie.py``
    fest.

    ⭐ **HA-Bauform E4e — die gedeckten Monate aus den Kosten-Kanälen.** Deckt der
    Kosten-Kanal (``services/kanal/kosten.py``, HAs Kostensensor-Muster) einen Monat
    voll, kommt sein Aggregat aus den Kanal-Δ (``kanal/preis_leser.preis_monate``:
    gewichtet = Δ Kosten ÷ Δ bewertete kWh, arithmetisch = Mittel des Preis-Kanals,
    abgedeckte Stunden = Stunden mit Preis, EV-Ø = Δ Kosten des vermiedenen Bezugs ÷
    Δ vermiedener Bezug) — EINE Quellenwahl je Monat für alle Eingänge (Bauplan §3b).
    Die übrigen Monate rechnet die Stundentabelle wie bisher (Lesart 1); die Zeilen
    gedeckter Monate lädt sie nicht (disjunkte Datumsbereiche). Signatur und
    Ergebnisform unverändert — alle Aufrufer bleiben, wie sie sind.
    """
    from backend.services.kanal.preis_leser import preis_monate

    aus_kanal, _ab_monat = await preis_monate(db, anlage_id, von=von, bis=bis)
    # Die Stundenzeilen nur für die Monate, die der Kanal NICHT deckt — als disjunkte Datumsbereiche
    # (dieselbe Zerlegung wie der Modus-Split der Wärmepumpe, E4d). Ohne Kanal ist das genau EIN Bereich und
    # damit die eine Abfrage von bisher (Budget `test_query_budget_monats_fakten.py`).
    from backend.services.energie_profil.modus_split_monat import _bereiche_ohne

    bereiche = _bereiche_ohne(von, bis, frozenset(aus_kanal)) if aus_kanal else [(von, bis)]
    # N-387: Menge backward, Preis forward — dieselbe Paarung wie im
    # Einzelmonat, über denselben Lader. Die Aggregation steht seither in
    # Python statt in `GROUP BY`.
    summen: dict[tuple[int, int], list[float]] = {}
    zeilen = []
    for _ab, _vor in bereiche:
        zeilen.extend(await _zeilen_mit_gepaartem_preis(
            db, anlage_id, ab=_ab, bis_exklusive=_vor, nur_wenn_gemessen=True
        ))
    for z, preis in zeilen:
        if preis is None:
            continue
        if (z.datum.year, z.datum.month) in aus_kanal:
            continue  # gedeckt — der Kanal sagt es (Quellenwahl je Monat)
        # Negativen Netzbezug auf 0 klemmen — der Clamp trägt (s. Docstring).
        kw = max(0.0, float(z.netzbezug_kw or 0.0))
        # A-2: vermiedener Bezug je Slot = max(0, PV − Einspeisung) — dieselbe
        # Bildung wie im Einzelmonat und auf der Tagesebene.
        ev = max(0.0, float(z.pv_kw or 0.0) - float(z.einspeisung_kw or 0.0))
        eintrag = summen.setdefault((z.datum.year, z.datum.month), [0.0, 0.0, 0.0, 0.0, 0.0, 0.0])
        eintrag[0] += preis * kw
        eintrag[1] += kw
        eintrag[2] += preis
        eintrag[3] += 1
        eintrag[4] += preis * ev
        eintrag[5] += ev

    je_monat: dict[tuple[int, int], StrompreisAggregat] = {}
    for (jahr, monat), (summe_kosten, summe_kwh, summe_preise, n, summe_ev_kosten, summe_ev) in summen.items():
        n = int(n)
        if n <= 0:
            continue
        je_monat[(jahr, monat)] = StrompreisAggregat(
            gewichtet_cent=round(summe_kosten / summe_kwh, 2) if summe_kwh > 0 else None,
            arithmetisch_cent=round(summe_preise / n, 2),
            abgedeckte_stunden=n,
            sollstunden=monthrange(jahr, monat)[1] * 24,
            ev_gewichtet_cent=(
                round(summe_ev_kosten / summe_ev, 2) if summe_ev > 0 else None
            ),
        )
    je_monat.update({m: a for m, a in aus_kanal.items() if a is not None})
    return PreisMessung(anlage_id, je_monat)


# =============================================================================
# Slot-Kosten je Tag — SOLL Flex-Tarife, F2 (2026-09-17)
# =============================================================================


@dataclass
class SlotKosten:
    """Die Kosten eines Tages als **Summe der Slot-Kosten**.

    SOLL Flex-Tarife **A-3**: *Die Kosten einer Ebene sind die Summe der
    Slot-Kosten über die Slots, die Preis und Menge tragen; ein Durchschnitt ist
    daraus abgeleitet — nie umgekehrt.*

    ⛔ **Warum nicht Ø × Tagesmenge.** Tragen 18 von 24 Slots einen Preis, aber
    alle 24 eine Menge, bekämen die sechs preislosen beim Multiplizieren
    stillschweigend den Durchschnitt — eine Interpolation nach unten (**P-4**).
    Als Summe ist der Betrag stattdessen additiv und richtungssicher zu niedrig;
    ``abdeckung_menge`` sagt daneben, wie viel davon bewertet ist.

    ``mittel_cent`` ist deshalb ein **Quotient über genau dieselbe Slot-Menge**
    wie ``kosten_euro`` — zwischen Zähler und Nenner kann kein
    Abdeckungskonflikt entstehen.
    """
    kosten_euro: float
    mittel_cent: Optional[float]
    menge_bewertet_kwh: float
    menge_gesamt_kwh: float
    #: Menge, deren Preis **gemessen** war (Rest: abgerechnet bzw. abgeleitet).
    menge_gemessen_kwh: float
    #: Menge, die mit dem **abgerechneten Monats-Ø** bewertet wurde.
    menge_abgerechnet_kwh: float = 0.0
    #: Der mit dem **Eigenverbrauch** gewichtete Ø-Preis desselben Tages.
    #:
    #: SOLL Flex-Tarife **A-2**: *Gewichtet wird mit der Menge, die bewertet
    #: wird.* Die Eigenverbrauchs-Ersparnis bewertet **vermiedenen** Bezug —
    #: und der fällt zu anderen Zeiten an als der tatsächliche Bezug.
    #: Eigenverbrauch entsteht mittags (PV), Netzbezug abends und nachts. Ein
    #: mit dem Bezug gewichteter Ø bewertet die vermiedene Menge deshalb
    #: systematisch **zu hoch**; in den Slots, in denen der Bezug vermieden
    #: wurde, gibt es gar keine gemessene Bezugsmenge.
    ev_mittel_cent: Optional[float] = None
    #: Die Menge, die ``ev_mittel_cent`` gewichtet hat (PV − Einspeisung je
    #: Slot, auf 0 geklemmt) — **Gewicht, nicht Kennzahl**: Die ausgewiesene
    #: Eigenverbrauchs-Menge bildet weiterhin
    #: ``berechne_verbrauchs_kennzahlen`` (mit Speicher, V2H und Abgabe).
    ev_menge_kwh: float = 0.0

    @property
    def abdeckung_menge(self) -> Optional[float]:
        """Anteil der Menge mit Preis (0..1) — ``None`` ohne Menge.

        ⚠ **Anteil der MENGE, nicht der Slots** (SOLL **A-1**): „68 % der
        Stunden" sagt weniger als „68 % des Bezugs" — fehlen ausgerechnet die
        verbrauchsstarken Slots, ist eine hohe Slot-Abdeckung wertlos.
        """
        if self.menge_gesamt_kwh <= 0:
            return None
        return self.menge_bewertet_kwh / self.menge_gesamt_kwh

    @property
    def herkunft(self) -> str:
        """``gemessen`` · ``gemischt`` · ``abgerechnet`` · ``vertrag`` · ``keine``.

        Entlang der bewerteten **Menge**, nicht der Slot-Zahl — aus demselben
        Grund wie bei ``abdeckung_menge``.
        """
        if self.menge_bewertet_kwh <= 0:
            return "keine"
        if self.menge_gemessen_kwh >= self.menge_bewertet_kwh:
            return "gemessen"
        if self.menge_gemessen_kwh > 0:
            return "gemischt"
        if self.menge_abgerechnet_kwh > 0:
            return "abgerechnet"
        return "vertrag"


async def lade_slot_kosten_je_tag(
    db: AsyncSession,
    anlage_id: int,
    *,
    von: date,
    bis: date,
    tarif_fuer,
    abgerechnet_fuer=None,
) -> dict[date, SlotKosten]:
    """Netzbezugskosten je Tag aus Slot-Preis × Slot-Menge, für ``[von, bis]``.

    **Die Preis-Kaskade der Slot-Ebene** (SOLL **P-6**): gemessener Endpreis →
    abgerechneter Monats-Ø → Vertragspreis → *kein Wert*. Der Kern des
    Entscheids vom 17.09.2026 (*„Tage bleiben Messung, Monat bleibt
    Abrechnung"*) ist die **erste** Stufe: Wo eine Slot-Messung vorliegt, gilt
    sie — und kein Monatsmittel verdrängt sie mehr.

    ⛔ **Warum Stufe 2 trotzdem ein Monatswert ist, und warum das kein
    P-4-Verstoß ist.** P-4 verbietet, eine gröbere Quelle **statt** einer
    vorhandenen feineren zu nehmen. Existiert keine feinere, ist die gröbere die
    beste verfügbare Information — und der abgerechnete Ø ist bei einem
    dynamischen Tarif *die bezahlte Wahrheit*, während der Stammpreis dort nach
    **T-1** gar kein ableitbarer Preis ist, sondern ein Platzhalter.

    *Diese Stufe hat sich beim Bau eine rote Probe erkämpft:*
    ``test_tage_werte_symmetrie.py::test_tage_werte_nehmen_den_abgerechneten_monats_durchschnittspreis``
    (30.07.2026, Forum simon42 #89667/60) hält fest, dass Cockpit/Tag nicht 30 ct
    nennen darf, während Cockpit/Monat 18 ct rechnet. Ohne Stufe 2 wäre genau
    das zurückgekehrt — ein Rückschritt hinter eine belegte Melder-Korrektur.
    ``herkunft`` sagt deshalb ``abgerechnet`` und nicht ``gemessen``: Der Wert
    ist über den Monat **verteilt**, nicht in diesem Slot gemessen.

    ⭐ **Der Vertragspreis ist kein Rückfall auf eine gröbere Ebene.** Bei
    Festpreis und Zeitfenstern ist der Slot-Preis aus dem Vertrag **ableitbar**
    (SOLL **T-1**) — ihn zu verwenden ist die Anwendung von P-4, nicht ihre
    Verletzung. Deshalb bewegt sich bei einem Festpreis-Anwender **keine Zahl**
    gegenüber dem Zustand vor diesem Bau: Σ(Menge_s × Arbeitspreis) ist
    identisch zu Tagesmenge × Arbeitspreis (SOLL §10, Prüfstein 2).

    ⚠ **``is not None``, nicht ``> 0``** (SOLL **P-8**): Bei einem dynamischen
    Tarif sind Null- und Negativpreise Alltag. Eine Prüfung auf „größer null"
    würfe ausgerechnet die interessantesten Slots weg und bewertete sie mit dem
    Vertragspreis — also zu hoch, genau dort, wo der echte Preis null oder
    negativ war.

    Args:
        von, bis: Tagesbereich, **beide einschließlich**.
        tarif_fuer: ``(datum) -> Tarifzeile | None`` — die Quelle des
            abgeleiteten Slot-Preises. Als Callable statt als Dict, damit der
            Aufrufer die Stichtagsregel besitzt: Heute reicht jeder Aufrufer den
            Monatstarif durch; die feinere Regel (**P-7**: der Stichtag eines
            Vertragspreises ist der Beginn des Zeitraums, den die Zahl
            beschreibt — für einen Slot also sein Tag) lässt sich dann hier
            nachziehen, ohne diese Funktion zu ändern.

    Returns:
        ``{datum: SlotKosten}`` — nur für Tage mit Stundenzeilen. Ein Tag ohne
        Zeilen fehlt im Dict; er hat keine Kosten von 0, sondern keine Aussage.
    """
    # N-387: der **gemessene** Slot-Preis kommt aus der Vorzeile (Menge
    # backward, Preis forward); der abgeleitete Preis der Stufen 2 und 3 hängt
    # am Tag bzw. am Zeitfenster und bleibt, wo er war.
    gepaart = await _zeilen_mit_gepaartem_preis(
        db, anlage_id, ab=von, bis_inklusive=bis
    )

    roh: dict[date, list[float]] = {}
    for _z, preis_cent in gepaart:
        datum, stunde = _z.datum, _z.stunde
        netzbezug_kw, pv_kw, einspeisung_kw = _z.netzbezug_kw, _z.pv_kw, _z.einspeisung_kw
        # Negative Mengen klemmen (Zähler-Glitch) — dieselbe Behandlung wie im
        # Monats-Aggregat oben, damit beide Ebenen dieselbe Menge sehen.
        menge = max(0.0, float(netzbezug_kw or 0.0))
        eintrag = roh.setdefault(datum, [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0])
        eintrag[4] += menge  # Gesamtmenge — unabhängig davon, ob ein Preis existiert
        # Vermiedener Bezug dieses Slots: erzeugt und NICHT eingespeist.
        ev_menge = max(0.0, float(pv_kw or 0.0) - float(einspeisung_kw or 0.0))

        # Die Kaskade der Slot-Ebene, in dieser Reihenfolge und nur hier.
        preis: Optional[float] = None
        gemessen = preis_cent is not None
        abgerechnet = False
        if gemessen:
            preis = float(preis_cent)
        else:
            if abgerechnet_fuer is not None:
                _abg = abgerechnet_fuer(datum)
                if _abg is not None:
                    preis, abgerechnet = float(_abg), True
            if preis is None:
                tarif = tarif_fuer(datum)
                if tarif is not None:
                    preis = preis_je_slot(tarif, datum, int(stunde))

        if preis is None:
            continue
        # Derselbe Slot-Preis, andere Gewichtungsmenge (A-2).
        eintrag[5] += preis * ev_menge / 100.0
        eintrag[6] += ev_menge
        eintrag[0] += preis * menge / 100.0  # Kosten in €
        eintrag[1] += menge                  # bewertete Menge
        if gemessen:
            eintrag[2] += menge              # davon gemessen
        elif abgerechnet:
            eintrag[3] += menge              # davon aus der Abrechnung verteilt

    je_tag: dict[date, SlotKosten] = {}
    for datum, (
        kosten, bewertet, gemessen_menge, abgerechnet_menge, gesamt,
        ev_kosten, ev_menge_sum,
    ) in roh.items():
        # ⛔ **Die Rundung hier ist eine Glättung, keine Anzeige-Rundung — beide
        # Grenzen sind gemessen.** Zwei Proben haben sie eingerahmt:
        #
        # * **Nach oben** (`test_tages_wirkungsgrad_und_finanz_rundung.py::
        #   test_oe_preis_netz_bleibt_der_tarif_auch_bei_kleiner_menge`): Mit
        #   `round(kosten, 4)` ergibt 0,19 kWh × 29,53 ct rückgerechnet 29,5263
        #   statt 29,53 ct. Der Client bildet den angezeigten Ø aus Kosten ÷
        #   Menge — eine Rundung auf Anzeige-Präzision verfälscht ihn dort.
        # * **Nach unten** (`test_tage_werte_symmetrie.py::
        #   test_tage_werte_ohne_monats_durchschnitt_bleiben_beim_tarif`): Ganz
        #   ohne Rundung summieren sich vier Slots à 0,45 € zu
        #   1,7999999999999998 € — die Summe über Slots erzeugt einen
        #   Float-Rest, den die alte Rechnung (eine einzige Multiplikation)
        #   nicht hatte.
        #
        # 1e-6 € sind 1e-4 ct und liegen weit unter jeder Anzeige; die Glättung
        # entfernt den Akkumulationsrest, ohne eine Zahl zu bewegen.
        kosten = round(kosten, 6)
        je_tag[datum] = SlotKosten(
            kosten_euro=kosten,
            mittel_cent=(kosten * 100.0 / bewertet) if bewertet > 0 else None,
            menge_bewertet_kwh=bewertet,
            menge_gesamt_kwh=gesamt,
            menge_gemessen_kwh=gemessen_menge,
            menge_abgerechnet_kwh=abgerechnet_menge,
            ev_mittel_cent=(
                round(ev_kosten, 6) * 100.0 / ev_menge_sum if ev_menge_sum > 0 else None
            ),
            ev_menge_kwh=ev_menge_sum,
        )
    return je_tag


# =============================================================================
# Zeittarif (HT/NT) — N-267
# =============================================================================
#
# ⭐ Warum das HIER steht und nicht in einem eigenen Modul: Die Frage ist
# dieselbe wie oben — „welcher EINE Preis beschreibt diesen Monat?" —, und sie
# wird mit derselben Formel beantwortet (Σ Preis × Menge ÷ Σ Menge über die
# Stundenzeilen). Verschieden ist allein die **Herkunft des Stundenpreises**:
# oben gemessen (`strompreis_cent` aus dem HA-Sensor), hier aus dem Tarif
# abgeleitet. Ein zweites Modul wäre ein zweiter Turm über demselben
# Sachverhalt — die Bauform, gegen die der Daten-Checker an neun Stellen
# ausdrücklich gebaut ist.

async def wirksamer_arbeitspreis_cent(
    db: AsyncSession,
    anlage_id: int,
    jahr: int,
    monat: int,
    tarif,
    *,
    cache: Optional[dict] = None,
) -> float:
    """Der Arbeitspreis, mit dem dieser Monat zu rechnen ist (ct/kWh).

    **Ohne Zeitfenster ist das der Stammpreis** — dann wird die Datenbank gar
    nicht erst gefragt. Mit Fenstern wird der Preis über den **gemessenen**
    Netzbezug der Stundenzeilen gewichtet (ADR-002/P8: der Wert beschreibt
    diesen Monat, nicht heute).

    ⚠ **Fällt auf den Stammpreis zurück, wenn keine Stundenwerte vorliegen** —
    also bei handgetragenen Monatswerten. Das ist der Hochtarif und damit **zu
    hoch**, aber es ist der Preis, den der Anwender ohne das Fenster gezahlt
    hätte: nachvollziehbar, nie erfunden. Wer es genauer braucht, trägt den
    Monats-Ø im Monatsabschluss ein — dasselbe Feld, das der dynamische Tarif
    seit jeher benutzt (`netzbezug_durchschnittspreis_cent`), und dieses Feld
    schlägt den Wert hier ohnehin (`resolve_netzbezug_preis_cent`).

    ⛔ **Kein geschätzter NT-Anteil.** Er wäre „eine Zahl, die genauer aussieht,
    als sie ist" (Gernots Antwort an den Melder in #380) und ein Feld, das zum
    Falschausfüllen einlädt — die #392-Lehre.

    Args:
        tarif: Die Tarifzeile des Monats (``Strompreis`` oder ``None``).
        cache: Optionales ``{(tarif_id, jahr, monat): preis}`` je Anfrage —
            Cockpit → Jahr fragt sonst denselben Monat mehrfach, weil
            ``lade_monats_fakten`` und ``baue_finanz_zeile`` ihn beide brauchen.
    """
    if tarif is None:
        from backend.core.wirtschaftlichkeit_defaults import NETZBEZUG_DEFAULT_CENT
        return NETZBEZUG_DEFAULT_CENT

    stammpreis = tarif.netzbezug_arbeitspreis_cent_kwh
    if not hat_zeitfenster(tarif):
        return stammpreis

    schluessel = (tarif.id, jahr, monat)
    if cache is not None and schluessel in cache:
        return cache[schluessel]

    # HA-Bauform E4e: die Messung (der Netzbezug je Stunde) aus den Kanälen, wenn sie den Monat decken — sonst aus den
    # Stundenzeilen wie bisher (Lesart 1). Dieselbe Formel auf beiden (`gewichteter_arbeitspreis_cent`).
    from backend.services.kanal.preis_leser import netzbezug_slots_des_monats

    slots = await netzbezug_slots_des_monats(db, anlage_id, jahr, monat)
    if slots is None:
        _von, _bis = monats_fenster(jahr, monat)
        result = await db.execute(
            select(
                TagesEnergieProfil.datum,
                TagesEnergieProfil.stunde,
                TagesEnergieProfil.netzbezug_kw,
            ).where(
                and_(
                    TagesEnergieProfil.anlage_id == anlage_id,
                    TagesEnergieProfil.datum >= _von,
                    TagesEnergieProfil.datum < _bis,
                )
            )
        )
        slots = result.all()
    gewichtet = gewichteter_arbeitspreis_cent(tarif, slots)
    preis = stammpreis if gewichtet is None else round(gewichtet, 4)

    if cache is not None:
        cache[schluessel] = preis
    return preis


# ─────────────────────────────────────────────────────────────────────────────
# Die vollständige Auflösung des Monats-Netzbezugspreises (#412, 11.09.2026)
# ─────────────────────────────────────────────────────────────────────────────

#: Woher der Preis eines Monats stammt — vier disjunkte Fälle, die Kaskade
#: nimmt immer genau einen.
#:
#: ⭐ **Warum die Herkunft mitgeliefert wird und nicht nur die Zahl** (P4: *die
#: Antwort sagt, was sie ist*): Bis 11.09.2026 lieferte Cockpit → Monat zwei
#: Felder — den gepflegten Ø und „den verwendeten Tarif" — und der Client bildete
#: daraus `durchschnitt ?? tarif`. Ein **zeitgewichteter** Preis (HT/NT) war
#: darin von einem reinen Stammpreis nicht zu unterscheiden; die Formel-Zeile
#: der Kachel nannte beide „Arbeitspreis aus dem Strompreis-Tarif". Mit einem
#: dritten Fall (gemessen) wäre aus der Halbwahrheit eine ganze geworden.
PREIS_HERKUNFT_GEPFLEGT = "gepflegt"
PREIS_HERKUNFT_GEMESSEN = "gemessen"
PREIS_HERKUNFT_ZEITFENSTER = "zeitfenster"
PREIS_HERKUNFT_STAMM = "stamm"


@dataclass(frozen=True)
class MonatsPreis:
    """Der Preis eines Monats **mit** seiner Herkunft."""

    cent: float
    herkunft: str
    #: Anteil der Monatsstunden mit Preisdaten (0..1) — **nur** bei
    #: ``gemessen``, sonst ``None``. ⚠ Herkunft und Güte sind zwei
    #: verschiedene Dinge: Ein Ø aus 40 % der Stunden hat dieselbe Herkunft
    #: wie einer aus 98 %, aber nicht dieselbe Belastbarkeit.
    abdeckung: Optional[float] = None
    #: Der **EV-gewichtete** Ø der gemessenen Stundenpreise dieses Monats (A-2),
    #: ``None`` ohne Messung. ⚠ Er hängt NICHT an ``herkunft``: Auch ein Monat
    #: mit gepflegtem (abgerechnetem) Bezugs-Ø trägt ihn, denn nach **P-1** ist
    #: die Bezugsabrechnung für die Ersparnis nur der Rückfall — unterhalb der
    #: Abrechnung gilt die Messung (P-2), genau wie auf der Tagesebene, wo der
    #: gemessene Slot-Preis den abgerechneten Ø schlägt.
    ev_cent: Optional[float] = None

    @property
    def ist_gemessen(self) -> bool:
        return self.herkunft == PREIS_HERKUNFT_GEMESSEN


async def aufgeloester_monatspreis(
    db: AsyncSession,
    anlage_id: int,
    jahr: int,
    monat: int,
    monatsdaten,
    tarif,
    *,
    stammpreis_override: Optional[float] = None,
    cache: Optional[dict] = None,
    messung: Optional[PreisMessung] = None,
) -> MonatsPreis:
    """Der Netzbezugspreis, mit dem dieser Monat zu rechnen ist — **die ganze Kaskade**.

    **Die Reihenfolge und ihre Begründung:**

    1. **gepflegt** — ``Monatsdaten.netzbezug_durchschnittspreis_cent``. Er kommt
       aus der **Abrechnung** und schlägt jede Messung: eedc misst, was durch den
       Zähler ging, der Versorger stellt in Rechnung, was er berechnet.
    2. **gemessen** — der verbrauchsgewichtete Ø der mitgeschriebenen
       Stundenpreise. ⭐ **Neu seit #412** (OB73-gif): Bis dahin endete die
       Kaskade hier und fiel auf den Stammpreis. Wer einen dynamischen Tarif
       hat, sah deshalb in *Cockpit → Tag* und im **laufenden** Monat den festen
       Tarifpreis — obwohl eedc die echten Stundenpreise längst mitschrieb und
       im Monatsabschluss sogar daraus einen Vorschlag rechnete. Die Zahl war
       nicht falsch gerechnet, aber sie war die schlechtere von zwei
       verfügbaren.
    3. **zeitfenster** — bei HT/NT der über den gemessenen Netzbezug gewichtete
       Tarifpreis (N-267).
    4. **stamm** — die Tarifspalte.

    ⚠ **Stufe 2 kommt VOR Stufe 3, und das ist eine Aussage:** Der gemessene
    Endpreis ist der **bezahlte** Preis; ein aus Tarif-Zeitfenstern abgeleiteter
    ist eine Rechnung über den Tarif. Wo beides vorliegt — ein Anwender mit
    HT/NT-Fenstern **und** zugeordnetem Preissensor, vom Datenmodell nicht
    ausgeschlossen —, gewinnt die Messung.

    ⛔ **Keine Mindestabdeckung, und das ist gemessen statt vermutet.** Der
    erste Entwurf sah eine vor. Sie hätte genau den Fall ausgeschlossen, für den
    sie gedacht war: ``StrompreisAggregat.abdeckung`` misst gegen den **vollen**
    Monat (``sollstunden = tage_im_monat * 24``), am 11. eines 30-Tage-Monats
    sind also höchstens 36 % erreichbar — jede Schwelle ab 50 % hätte den
    laufenden Monat bis nach Monatsmitte auf den Stammpreis zurückgeworfen.
    Stattdessen wird die Abdeckung **mitgeliefert** statt den Wert zu ersetzen;
    das ist die P4-Linie (*„der Wert wird nicht ersetzt, nur beschriftet"*) und
    dieselbe Wahl, die ``live_dashboard._monats_durchschnitt_cent`` trifft:
    „den Monat, soweit er da ist".

    Args:
        stammpreis_override: Stufe 4 mit einem **anderen** Stammpreis als der
            Tarifspalte — für die **Komponenten**-Tarife (Wallbox, Wärmepumpe).
            Ihre eigene Kaskade (Komponente → allgemein → Default) löst
            ``resolve_strompreis_for_komponente`` auf; was sie liefert, ist für
            diese Funktion der Stammpreis. ⚠ Die Stufen 1 und 2 bleiben davon
            unberührt und schlagen ihn — genau so, wie
            ``wallbox_preis_effektiv_cent`` es in den Monats-Fakten tut: *„Der
            Flex-Ø gilt für den ganzen Zähler — auch für die Wallbox."*
        cache: optionales ``{(jahr, monat): MonatsPreis}`` je Anfrage — Cockpit →
            Jahr fragt sonst denselben Monat mehrfach. ⛔ **Nur setzen, wo der
            Stammpreis über die Monate derselbe ist** — mit
            ``stammpreis_override`` je Komponente braucht jede Verwendung ihren
            eigenen Cache.

    Returns:
        ``MonatsPreis`` — Zahl **und** Herkunft, nie nur die Zahl.
    """
    schluessel = (jahr, monat)
    if cache is not None and schluessel in cache:
        return cache[schluessel]

    ergebnis = await _aufgeloester_monatspreis_ungecacht(
        db, anlage_id, jahr, monat, monatsdaten, tarif, stammpreis_override,
        messung=messung,
    )
    if cache is not None:
        cache[schluessel] = ergebnis
    return ergebnis


async def _aufgeloester_monatspreis_ungecacht(
    db: AsyncSession, anlage_id: int, jahr: int, monat: int, monatsdaten, tarif,
    stammpreis_override: Optional[float] = None,
    *,
    messung: Optional[PreisMessung] = None,
) -> MonatsPreis:
    # 1 — gepflegt. ⚠ `is not None`, nicht truthy: ein Monats-Ø von 0,0 ct ist
    # bei dynamischem Tarif real (viele Negativpreis-Stunden) und wäre als
    # falsy stillschweigend durchgefallen — die 0-Werte-Falle.
    gepflegt = getattr(monatsdaten, "netzbezug_durchschnittspreis_cent", None)

    # ⚠ **Alle Tarif-Attribute VOR dem ersten Datenbank-Roundtrip lesen.** Ein
    # ORM-Objekt kann danach abgelaufen sein, und ein Nachladen im falschen
    # Kontext endet in `MissingGreenlet` statt in einem Wert. Beim Bau genau so
    # aufgetreten — die Reihenfolge ist hier kein Stil, sondern Funktion.
    stammpreis = stammpreis_override
    if stammpreis is None:
        stammpreis = (
            tarif.netzbezug_arbeitspreis_cent_kwh
            if tarif is not None and tarif.netzbezug_arbeitspreis_cent_kwh is not None
            else None
        )
    tarif_hat_zeitfenster = tarif is not None and hat_zeitfenster(tarif)

    # 2 — gemessen. Liegt die Messung der ganzen Anfrage vor, steht der Monat
    # schon darin (EINE gruppierte Abfrage statt einer je Monat und Aufrufer);
    # sonst der Einzelmonat wie bisher.
    # ⭐ **Die Messung wird auch bei gepflegtem Ø gelesen** (seit 18.09.2026):
    # sie trägt den EV-gewichteten Preis (A-2), und der gilt für die Ersparnis
    # unabhängig davon, welche Stufe den Bezugspreis stellt (P-1: die
    # Bezugsabrechnung ist für die Ersparnis nur der Rückfall).
    aggregat = (
        messung.hole(jahr, monat)
        if messung is not None
        else await berechne_monats_durchschnittspreis(anlage_id, jahr, monat, db)
    )
    ev_cent = aggregat.ev_gewichtet_cent if aggregat is not None else None

    if gepflegt is not None:
        return MonatsPreis(cent=gepflegt, herkunft=PREIS_HERKUNFT_GEPFLEGT, ev_cent=ev_cent)

    if aggregat is not None and aggregat.gewichtet_cent is not None:
        return MonatsPreis(
            cent=aggregat.gewichtet_cent,
            herkunft=PREIS_HERKUNFT_GEMESSEN,
            abdeckung=round(aggregat.abdeckung, 3),
            ev_cent=ev_cent,
        )

    if stammpreis is None:
        from backend.core.wirtschaftlichkeit_defaults import NETZBEZUG_DEFAULT_CENT
        return MonatsPreis(
            cent=NETZBEZUG_DEFAULT_CENT, herkunft=PREIS_HERKUNFT_STAMM, ev_cent=ev_cent,
        )

    # 3 — Zeitfenster (HT/NT).
    if tarif_hat_zeitfenster:
        gewichtet = await wirksamer_arbeitspreis_cent(db, anlage_id, jahr, monat, tarif)
        if gewichtet != stammpreis:
            return MonatsPreis(
                cent=gewichtet, herkunft=PREIS_HERKUNFT_ZEITFENSTER, ev_cent=ev_cent,
            )

    # 4 — Stammpreis.
    return MonatsPreis(cent=stammpreis, herkunft=PREIS_HERKUNFT_STAMM, ev_cent=ev_cent)
