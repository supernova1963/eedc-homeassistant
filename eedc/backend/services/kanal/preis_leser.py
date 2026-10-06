"""Leser des Monatspreises aus den Kosten-Kanälen (HA-Bauform E4e, Bauplan §6 U7; Auftrag Punkt 2).

**Was er liefert.** Je Monat im Monatsfenster des Bestands (``fenster.monatsfenster`` — die Grenze, nach der
``strompreis_aggregator`` die Stundenzeilen nach ``datum`` gruppiert) ein ``StrompreisAggregat`` in DERSELBEN Form wie
der heutige Leser, für Monate, die die Kosten-Kanäle (``kosten.py``) voll decken — jedes Feld ein Quotient zweier Δ:

* ``gewichtet_cent`` = Δ ``kosten_netzbezug`` × 100 ÷ Δ ``netzbezug_bewertet_kwh`` (HAs Kostensensor: Δ Kosten ÷ Δ kWh);
  ``None``, wenn im Monat kein bewerteter Bezug floss (wie der Bestand);
* ``arithmetisch_cent`` = Δ ``preis_summe`` ÷ Δ ``preis_stunden`` (Σ Preis ÷ Stunden mit Preis, wie der Bestand);
* ``abgedeckte_stunden`` = Δ ``preis_stunden``, ``sollstunden`` = Tage × 24 wie der Bestand;
* ``ev_gewichtet_cent`` = Δ ``kosten_ev_vermieden`` × 100 ÷ Δ ``ev_bewertet_kwh`` (A-2), ``None`` ohne vermiedenen Bezug.

Gerundet wie der Bestand (2 Stellen). **Eine Quellenwahl je Monat für alle Eingänge** (§3b): gedeckt ist ein Monat nur,
wenn JEDER der sechs Kosten-Kanäle ihn voll deckt (Abdeckungsregel der Lese-Schicht); sonst rechnet der heutige Leser
den ganzen Monat (Lesart 1). Der Kosten-Kanal schreibt eine Stunde erst, wenn der Preis-Kanal sie erreicht hat — hört
der Preis-Spiegel auf, endet die Deckung. Ein gedeckter Monat ohne Stunde mit Preis fehlt im Ergebnis — wie im Bestand.

**Laufzeit:** EINE Anweisung für die Ränder aller Monate (``reihe_stapel``) — keine Stundenzeile, kein Mittel je Monat
(Entscheid Fable zu E4e: bis dahin las je Monat ein ``mittel`` den Preis-Kanal, 73 ms für 12 Jahre).

Schwesterdateien: ``kosten.py`` (Schreiber), ``bilanz_leser.py`` (Uhr), ``lesen.py``.
"""

from __future__ import annotations

from calendar import monthrange
from datetime import date, datetime
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.kanal import ART_SUM
from backend.services.kanal.fenster import monate, monatsgrenzen
from backend.services.kanal.kosten import (
    EV_BEWERTET_KEY,
    KOSTEN_EV_KEY,
    KOSTEN_NETZBEZUG_KEY,
    NETZBEZUG_BEWERTET_KEY,
    PREIS_STUNDEN_KEY,
    PREIS_SUMME_KEY,
)
from backend.services.kanal.lesen import kanaele_laden, reihe_stapel, soll_ende

MonatsSchluessel = tuple[int, int]

#: Die Mengen-Kanäle, die ein Monat voll decken muss.
MENGEN_KEYS: tuple[str, ...] = (KOSTEN_NETZBEZUG_KEY, NETZBEZUG_BEWERTET_KEY, KOSTEN_EV_KEY, EV_BEWERTET_KEY,
                                PREIS_SUMME_KEY, PREIS_STUNDEN_KEY)


def uhr() -> int:
    """Die Uhr des Lesers — EINE Stelle (die Matrizen stellen sie wie ``bilanz_leser.uhr``)."""
    from backend.services.kanal import bilanz_leser

    return bilanz_leser.uhr()


def _monat_von(ts: int) -> MonatsSchluessel:
    from backend.services.kanal.abgeleitet import tag_der_stunde

    t = tag_der_stunde(ts)
    return t.year, t.month


def aggregat_aus_kanaelen(
    jahr: int, monat: int, *, kosten_euro: float, bewertet_kwh: float, ev_kosten_euro: float, ev_kwh: float,
    preis_summe_cent: float, stunden: float,
):
    """Das ``StrompreisAggregat`` eines gedeckten Monats aus den Δ (rein). ``None``, wenn keine Stunde einen Preis
    trug (wie der Bestand: kein Eintrag)."""
    from backend.services.strompreis_aggregator import StrompreisAggregat

    n = int(round(stunden))
    if n <= 0:
        return None
    return StrompreisAggregat(
        gewichtet_cent=round(kosten_euro * 100.0 / bewertet_kwh, 2) if bewertet_kwh > 0 else None,
        arithmetisch_cent=round(preis_summe_cent / n, 2),
        abgedeckte_stunden=n,
        sollstunden=monthrange(jahr, monat)[1] * 24,
        ev_gewichtet_cent=round(ev_kosten_euro * 100.0 / ev_kwh, 2) if ev_kwh > 0 else None,
    )


async def preis_monate(
    db: AsyncSession, anlage_id: int, *, von: Optional[date] = None, bis: Optional[date] = None,
    jetzt: Optional[int] = None,
) -> tuple[dict[MonatsSchluessel, object], Optional[MonatsSchluessel]]:
    """Die gedeckten Monate ``[von, bis)`` (Datumsgrenzen wie ``lade_preis_aggregate_je_monat``; offen = alle).

    Returns:
        ``(je_monat, ab_monat)`` — ``je_monat``: gedeckter Monat → ``StrompreisAggregat`` (``None``: gedeckt, aber
        ohne Stunde mit Preis — der Aufrufer führt ihn wie der Bestand nicht); ``ab_monat``: der früheste Monat, ab dem JEDER Monat bis zum laufenden gedeckt ist (der Bestand
        braucht ihn nicht mehr zu laden), sonst ``None``.
    """
    kanaele = await kanaele_laden(db, anlage_id, MENGEN_KEYS)
    if KOSTEN_NETZBEZUG_KEY not in kanaele:
        return {}, None
    jetzt = uhr() if jetzt is None else int(jetzt)
    se = soll_ende(jetzt)
    anfaenge = [int(k.aufbaubar_ab) for key, k in kanaele.items() if key in MENGEN_KEYS and k.aufbaubar_ab]
    if not anfaenge:
        return {}, None
    # Der Monat, in dessen Fenster die erste Zeile liegt — er selbst ist nie gedeckt (sein Anfang liegt vor dem Kanal),
    # die Regel (a) der Lese-Schicht sagt das; er wird nur mitgefragt, damit die Grenzen lückenlos bleiben.
    erster_monat = _monat_von(min(anfaenge))
    heute = datetime.fromtimestamp(jetzt).date()
    letzter_monat = (heute.year, heute.month)
    if von is not None:
        erster_monat = max(erster_monat, (von.year, von.month))
    if bis is not None:
        # `bis` ist exklusiv (der Erste des Folgemonats bzw. ein beliebiger Tag): der letzte Monat davor.
        b = date.fromordinal(bis.toordinal() - 1)
        letzter_monat = min(letzter_monat, (b.year, b.month))
    liste = monate(erster_monat, letzter_monat)
    if not liste:
        return {}, None
    grenzen = monatsgrenzen(erster_monat, letzter_monat)
    faellig = [i for i in range(len(liste)) if grenzen[i] < se]
    if not faellig:
        return {}, None
    mengen = [kanaele[k] for k in MENGEN_KEYS if k in kanaele and kanaele[k].art == ART_SUM]
    if len(mengen) != len(MENGEN_KEYS):
        return {}, None
    je = await reihe_stapel(db, mengen, grenzen, jetzt=jetzt)
    out: dict[MonatsSchluessel, object] = {}
    gedeckt: list[int] = []
    for i in faellig:
        z = {k: je[k][i] for k in MENGEN_KEYS}
        if not all(x.voll for x in z.values()):
            continue
        gedeckt.append(i)
        agg = aggregat_aus_kanaelen(
            *liste[i], kosten_euro=z[KOSTEN_NETZBEZUG_KEY].delta, bewertet_kwh=z[NETZBEZUG_BEWERTET_KEY].delta,
            ev_kosten_euro=z[KOSTEN_EV_KEY].delta, ev_kwh=z[EV_BEWERTET_KEY].delta,
            preis_summe_cent=z[PREIS_SUMME_KEY].delta, stunden=z[PREIS_STUNDEN_KEY].delta,
        )
        out[liste[i]] = agg          # auch ``None``: gedeckt, aber keine Stunde mit Preis (der Bestand sagt dann nichts)
    # Der früheste Monat, ab dem alles bis zum letzten fälligen gedeckt ist.
    ab_monat: Optional[MonatsSchluessel] = None
    for i in reversed(faellig):
        if i not in gedeckt:
            break
        ab_monat = liste[i]
    return out, ab_monat


async def preis_monat(db: AsyncSession, anlage_id: int, jahr: int, monat: int, *, jetzt: Optional[int] = None):
    """Ein Monat: ``(gedeckt, StrompreisAggregat | None)`` — ``gedeckt`` heißt „die Kanäle sagen es", auch wenn sie
    ``None`` sagen (kein Preis im Monat)."""
    erste = date(jahr, monat, 1)
    folge = date(jahr + (monat == 12), (monat % 12) + 1, 1)
    je, ab = await preis_monate(db, anlage_id, von=erste, bis=folge, jetzt=jetzt)
    return (jahr, monat) in je, je.get((jahr, monat))


async def netzbezug_slots_des_monats(
    db: AsyncSession, anlage_id: int, jahr: int, monat: int, *, jetzt: Optional[int] = None,
) -> Optional[list[tuple[date, int, float]]]:
    """Der gemessene Netzbezug des Monats je Stunde aus den Kanälen — die Messung, mit der
    ``strompreis_aggregator.wirksamer_arbeitspreis_cent`` einen Zeitfenster-Tarif (HT/NT) gewichtet.

    ``(datum, stunde, kWh)`` je Backward-Slot der Stundentabelle (Slot ``h`` = Energie ``[h-1, h)``; die Stunde mit
    ``start_ts = T`` ist Slot ``(T + 1 h).hour`` des Tages von ``T + 1 h`` — die Umkehrung von
    ``slot_konvention.slot_start_ts``), über das Monatsfenster des Bestands. Netzbezug = Σ der Netzbezugs-Zähler der
    Bilanz-Gruppe des Monats (Zählerwahl am letzten Tag wie ``bilanz_leser.monate_bilanz``, Entweder-oder: der erste
    deckende). Eine gebündelte Stunde trägt ihre Menge in der Stunde ihrer Zeile (A-6, wie die Stundenzeile).

    ``None``, wenn nicht JEDER benötigte Kanal das Monatsfenster voll deckt (Lesart 1 — der Aufrufer liest die
    Stundenzeilen wie bisher)."""
    from datetime import timedelta

    from backend.services.kanal.bilanz_leser import _letzter_tag, _stamm
    from backend.services.kanal.fenster import monatsfenster
    from backend.services.kanal.lesen import stunden_stapel, zeitraum_stapel
    from backend.services.snapshot.komponenten_beitraege import resolve_either_or_eintraege

    jetzt = uhr() if jetzt is None else int(jetzt)
    stamm = await _stamm(db, anlage_id)
    eintraege = [e for e in await stamm.eintraege(db, lambda i: i.ist_aktiv_im_monat(jahr, monat),
                                                   _letzter_tag(jahr, monat)) if e.kategorie == "netzbezug"]
    if not eintraege:
        return None
    kanaele = await kanaele_laden(db, anlage_id, {e.schluessel for e in eintraege})
    mengen = [k for k in kanaele.values() if k.art == ART_SUM]
    if not mengen:
        return None
    von, bis = monatsfenster(jahr, monat)
    if von >= soll_ende(jetzt):
        return None
    z = await zeitraum_stapel(db, mengen, von, bis, jetzt=jetzt)
    voll = {k for k, x in z.items() if x.voll}
    gewaehlt = resolve_either_or_eintraege(eintraege, gruppe_fn=lambda e: e.gruppe,
                                           hat_tagesdaten_fn=lambda e: e.schluessel in voll)
    if any(e.schluessel not in voll for e in gewaehlt):      # ein Zähler ohne Gruppe, oder eine Gruppe ohne deckenden
        return None
    st = await stunden_stapel(db, [kanaele[e.schluessel] for e in gewaehlt], von, bis, jetzt=jetzt)
    je_stunde: dict[int, float] = {}
    for e in gewaehlt:
        for w in st[e.schluessel].werte:
            if w.change is not None:
                je_stunde[w.start_ts] = je_stunde.get(w.start_ts, 0.0) + e.vorzeichen * w.change
    out: list[tuple[date, int, float]] = []
    for ts in sorted(je_stunde):
        ende = datetime.fromtimestamp(ts) + timedelta(hours=1)
        out.append((ende.date(), ende.hour, je_stunde[ts]))
    return out


__all__ = ["MENGEN_KEYS", "aggregat_aus_kanaelen", "netzbezug_slots_des_monats", "preis_monat", "preis_monate", "uhr"]
