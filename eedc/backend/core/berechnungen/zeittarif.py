"""
Zeittarif (HT/NT) — der wirksame Arbeitspreis eines Monats.

Fund **N-267**, Melder **MeinerB (Bernd)** in Discussion #380: Ein Tarif gilt in
eedc für einen Zeitraum in *Tagen* und kennt keine Uhrzeit; ein Zweipreistarif
mit festem Fenster („täglich 19:00–20:00 nur 50 % des regulären Preises") ließ
sich nirgends hinterlegen.

**Was dieses Modul tut — und was ausdrücklich nicht.** Es beantwortet zwei
Fragen, beide ohne Datenbank:

1. *Welcher Preis gilt in dieser Stunde?* → :func:`preis_je_slot`
2. *Welcher EINE Preis beschreibt diesen Monat?* → :func:`gewichteter_arbeitspreis_cent`

Es rechnet **keine** Kosten und **kein** Aggregat der Monatszeile. Die zweite
Funktion liefert einen Preis, den der Aufrufer dort einsetzt, wo heute der
Stammpreis steht — nach ADR-002/**P8** ist das die Stelle, an der ein Tarifwert
den Stichtag seines Monats bekommt.

----------------------------------------------------------------------------
⚠️  Die Backward-Konvention ist hier KEIN Detail, sondern der ganze Fund
----------------------------------------------------------------------------
``TagesEnergieProfil.stunde`` ist ein **Backward-Slot** (Issue #144, SoT
``core/berechnungen/slot_konvention.py``):

    Slot ``h`` = Energie im Intervall ``[h-1, h)``
    Slot 0     = Energie ``[Vortag 23:00, heute 00:00)``
    Slot 23    = Energie ``[heute 22:00, heute 23:00)``

Bernds Fenster **19:00–20:00 ist damit Slot 20**, nicht Slot 19 — und der
Uhr-Tag von Slot 0 ist der **Vortag**. Wer den Slot-Index für eine Uhrzeit
hält, gibt der falschen Stunde den Niedertarif: der Fehler wäre **ein Preis,
den niemand nachrechnen kann**, weil beide Zahlen für sich plausibel aussehen.

Für den bestehenden Aggregator (``services/strompreis_aggregator.py``) spielt
die Konvention keine Rolle — dort stehen Preis und Menge in **derselben Zeile**,
der Versatz kürzt sich heraus. Beim Zeittarif wird der Preis aus der **Uhr**
abgeleitet, und genau dadurch wird die Konvention zum tragenden Teil.

Deshalb gibt es :func:`uhrzeit_des_slots` als benannte Funktion statt einer
Subtraktion an der Verwendungsstelle: der Vertrag soll sichtbar und prüfbar
sein — dieselbe Begründung, mit der ``openmeteo_preceding_hour_slot`` im
Slot-SoT als Identität ausgeschrieben ist.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Iterable, Optional, Protocol, Sequence


class _Zeitfenster(Protocol):
    """Was dieses Modul von einem Fenster braucht (``StrompreisZeitfenster``)."""

    arbeitspreis_cent_kwh: float

    def deckt_uhrzeit(self, zeitpunkt: datetime) -> bool: ...


class _Tarif(Protocol):
    """Was dieses Modul von einem Tarif braucht (``Strompreis``)."""

    netzbezug_arbeitspreis_cent_kwh: float
    zeitfenster: Sequence[_Zeitfenster]


def uhrzeit_des_slots(datum: date, stunde: int) -> datetime:
    """Der **Beginn** des Uhr-Intervalls, das der Backward-Slot ``stunde`` trägt.

    Slot ``h`` deckt ``[h-1, h)`` ⇒ das Intervall beginnt ``h-1`` Stunden nach
    Mitternacht des ``datum``. Für ``stunde = 0`` liegt das eine Stunde **vor**
    Mitternacht, also am **Vortag** 23:00 — deshalb Datums-Arithmetik statt
    ``datum.replace(hour=…)``, das dort mit ``ValueError`` abbräche.

        >>> uhrzeit_des_slots(date(2026, 8, 29), 20).hour
        19
        >>> uhrzeit_des_slots(date(2026, 8, 29), 0).day
        28

    Das Intervall ist genau eine Stunde lang und liegt damit vollständig in
    **einer** Uhr-Stunde eines **einen** Kalendertages — sein Beginn entscheidet
    über Stunde und Wochentag, es gibt keinen Zwischenfall.
    """
    return datetime.combine(datum, datetime.min.time()) + timedelta(hours=stunde - 1)


def hat_zeitfenster(tarif: Optional[_Tarif]) -> bool:
    """Trägt dieser Tarif mindestens ein Zeitfenster?

    Die Bedingung, an der die Zeittarif-Pfade hängen — bewusst eine **Eigenschaft
    des Tarifs** und nicht ``vertragsart``. Dieselbe Begründung wie bei #392
    („Einspeisevergütung wechselt monatlich"): ``vertragsart == "dynamisch"``
    beschreibt den Börsenpreis-Pfad, und **fixer Bezug mit Zeitfenster** ist ein
    anderer, realer Fall — nämlich genau Bernds.
    """
    return bool(tarif is not None and getattr(tarif, "zeitfenster", None))


def preis_je_slot(tarif: _Tarif, datum: date, stunde: int) -> float:
    """Der Arbeitspreis (ct/kWh), der im Backward-Slot ``stunde`` gilt.

    Ohne passendes Fenster gilt der Stammpreis des Tarifs — der Hochtarif. Das
    **erste** deckende Fenster gewinnt; überlappende Fenster sind damit nicht
    verboten, sondern geordnet (``order_by von_stunde`` an der Beziehung).
    """
    return preis_je_uhrzeit(tarif, uhrzeit_des_slots(datum, stunde))


def preis_je_uhrzeit(tarif: _Tarif, zeitpunkt: datetime) -> float:
    """Der Arbeitspreis (ct/kWh) der Uhr-Stunde, die bei ``zeitpunkt`` beginnt — die Regel von ``preis_je_slot``
    ohne den Slot-Index."""
    for fenster in getattr(tarif, "zeitfenster", None) or ():
        if fenster.deckt_uhrzeit(zeitpunkt):
            return fenster.arbeitspreis_cent_kwh
    return tarif.netzbezug_arbeitspreis_cent_kwh


#: Ein Montag 00:00 — Bezugspunkt der Zellen (Wochentag, Stunde): ``_MONTAG + wochentag Tage + stunde Stunden``.
_MONTAG = datetime(2024, 1, 1)


def gewichteter_arbeitspreis_aus_zellen(
    tarif: _Tarif,
    zellen: Iterable[tuple[int, int, Optional[float]]],
) -> Optional[float]:
    """Dasselbe Ø wie :func:`gewichteter_arbeitspreis_cent`, aus dem Netzbezug je Zelle ``(wochentag, stunde)``.

    ``wochentag`` wie ``datetime.weekday()`` (0 = Montag), ``stunde`` = die Uhr-Stunde, in der das Intervall
    **beginnt** (``uhrzeit_des_slots`` — nicht der Slot-Index). Der Preis einer Stunde hängt nur an diesen beiden
    (``StrompreisZeitfenster.deckt_uhrzeit``: Wochentag-Maske und Uhrzeit), deshalb ist Σ(preis × kWh) über die Slots
    gleich Σ(preis × Σ kWh) über die Zellen. Die Zelle trägt die Summe der schon auf 0 geklemmten Slot-Mengen
    (HA-Bauform E4f: der Aufrufer fasst sie in EINER Anweisung über alle Monate zusammen, statt jeden Slot zu laden).

    Returns: ct/kWh — oder ``None`` ohne gemessenen Netzbezug (wie :func:`gewichteter_arbeitspreis_cent`).
    """
    summe_menge = 0.0
    summe_kosten = 0.0
    for wochentag, stunde, menge in zellen:
        if menge is None:
            continue
        kwh = max(0.0, menge)
        if kwh <= 0:
            continue
        summe_menge += kwh
        summe_kosten += kwh * preis_je_uhrzeit(tarif, _MONTAG + timedelta(days=int(wochentag), hours=int(stunde)))
    if summe_menge <= 0:
        return None
    return summe_kosten / summe_menge


def gewichteter_arbeitspreis_cent(
    tarif: _Tarif,
    slots: Iterable[tuple[date, int, Optional[float]]],
) -> Optional[float]:
    """Der über den **gemessenen Netzbezug** gewichtete Arbeitspreis des Zeitraums.

        Ø = Σ(preis_h × netzbezug_h) / Σ(netzbezug_h)

    Dieselbe Formel, die ``services/strompreis_aggregator.py`` für den
    dynamischen Tarif aus dem **Sensor**-Preis bildet — hier mit einem Preis, der
    aus dem Tarif **abgeleitet** statt gemessen wird. Das ist der ganze
    Unterschied, und deshalb entsteht daneben kein zweiter Rechenweg.

    Args:
        tarif: Tarifzeile mit ihren Fenstern.
        slots: ``(datum, stunde, netzbezug_kwh)`` je Backward-Slot. Negative
            Mengen werden auf 0 geklemmt (Zähler-Glitch, wie im Bestands-
            Aggregator); ``None`` zählt nicht mit.

    Returns:
        ct/kWh — oder ``None``, wenn im Zeitraum **kein** Netzbezug gemessen
        wurde. ``None`` heißt „nicht gewichtbar", nicht „0 ct": der Aufrufer
        fällt dann auf den Stammpreis zurück, statt eine Zahl zu erfinden.

    ⚑ Ein Monat **ohne** Fenster liefert exakt den Stammpreis zurück — jede
    Stunde trägt denselben Preis, das gewichtete Mittel ist er selbst. Die
    Umstellung bewegt dort also keine Zahl (Wächter ``W-Z3``).
    """
    summe_menge = 0.0
    summe_kosten = 0.0
    for datum, stunde, menge in slots:
        if menge is None:
            continue
        kwh = max(0.0, menge)
        if kwh <= 0:
            continue
        summe_menge += kwh
        summe_kosten += kwh * preis_je_slot(tarif, datum, stunde)
    if summe_menge <= 0:
        return None
    return summe_kosten / summe_menge


def zellen_der_slots(slots: Iterable[tuple[date, int, Optional[float]]]) -> list[tuple[int, int, float]]:
    """Backward-Slots ``(datum, stunde, kWh)`` als Zellen ``(wochentag, uhrstunde des Beginns, Σ kWh)`` — jede Menge auf 0
    geklemmt wie in :func:`gewichteter_arbeitspreis_cent` (die Zellen-Form, die :func:`gewichteter_arbeitspreis_aus_zellen`
    liest; ``uhrzeit_des_slots`` ist die eine Umrechnung)."""
    zellen: dict[tuple[int, int], float] = {}
    for datum, stunde, menge in slots:
        if menge is None:
            continue
        beginn = uhrzeit_des_slots(datum, stunde)
        zellen[(beginn.weekday(), beginn.hour)] = zellen.get((beginn.weekday(), beginn.hour), 0.0) + max(0.0, menge)
    return [(w, h, kwh) for (w, h), kwh in sorted(zellen.items())]


def gewichteter_arbeitspreis_netto_aus_zellen(
    tarif: _Tarif,
    bezug_zellen: Iterable[tuple[int, int, Optional[float]]],
    abzug_zellen: Iterable[tuple[int, int, Optional[float]]],
) -> Optional[float]:
    """Das Ø eines Zeitfenster-Tarifs über **(Netzbezug − Abzug)** je Zelle ``(wochentag, stunde)`` — N-770/N-771 F6.

    Mit gemessenem Netzbezug zum WP-/Wallbox-Tarif (Abzug = N aus dem Kanal des Felds) rechnet der Versorger den
    Haushaltstarif nur über den Rest des Netzbezugs ab; dessen HT/NT-Gewicht ist deshalb ``Netzbezug − N``, nicht der
    ganze Netzbezug:

        Ø = Σ_z (B_z − N_z) × preis_z / Σ_z (B_z − N_z)

    ``B_z`` sind die schon auf 0 geklemmten Bezugs-Zellen (wie :func:`gewichteter_arbeitspreis_aus_zellen`), ``N_z`` die
    Zellen des Abzugs. ⚠ **Kein Klemmen je Zelle:** läuft eine Zelle ins Negative (zwei Zähler, zeitversetzt gelesen),
    hielte eine Klemme Σ (B − N) × preis nicht mehr gleich der Summe der Stunden — und die Stunden der Tagessicht rechnen
    ihren Rest ebenso ungeklemmt (``strompreis_aggregator.slot_kosten_aus_zeilen``). Der Preis hängt nur an der Zelle,
    deshalb ist das Zellen-Ø gleich dem Stunden-Ø.

    Returns: ct/kWh — ``None``, wenn der Rest ``Σ (B − N) ≤ 0`` ist (nicht gewichtbar; der Aufrufer bleibt beim Ø über
    den ganzen Netzbezug)."""
    netto: dict[tuple[int, int], float] = {}
    for wochentag, stunde, menge in bezug_zellen:
        if menge is not None:
            netto[(int(wochentag), int(stunde))] = netto.get((int(wochentag), int(stunde)), 0.0) + max(0.0, menge)
    for wochentag, stunde, menge in abzug_zellen:
        if menge is not None:
            netto[(int(wochentag), int(stunde))] = netto.get((int(wochentag), int(stunde)), 0.0) - menge
    summe_menge = sum(netto.values())
    if summe_menge <= 0:
        return None
    summe_kosten = sum(
        kwh * preis_je_uhrzeit(tarif, _MONTAG + timedelta(days=w, hours=h)) for (w, h), kwh in netto.items()
    )
    return summe_kosten / summe_menge
