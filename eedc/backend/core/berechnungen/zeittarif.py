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
    zeitpunkt = uhrzeit_des_slots(datum, stunde)
    for fenster in getattr(tarif, "zeitfenster", None) or ():
        if fenster.deckt_uhrzeit(zeitpunkt):
            return fenster.arbeitspreis_cent_kwh
    return tarif.netzbezug_arbeitspreis_cent_kwh


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
