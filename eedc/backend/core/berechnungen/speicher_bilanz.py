"""Speicher-Bilanz eines Zeitraums — Verlust, Bilanz, Netzladeanteil, Wirkungsverluste in €, PV-Ladung, Solar-Anteil
(Päckchen BB, 9.11.2026; Z-Client-Halt H1).

Bis dahin rechnete der Client diese Größen an acht Stellen selbst (``KomponentenSektionen.tsx`` Wirkungsverluste und
Bilanz, ``komponentenAdapter.tsx`` Verlust/Netzladung-Kosten/PV-Ladung des Speicher-Hubs, ``SpeicherJahresbilanz.tsx``
Verlust je Jahr, ``JahrSpeicherTabelle.tsx`` Solar-Anteil). Jetzt steht jede Formel hier einmal; die Antwortmodelle
tragen das Ergebnis als Feld (``computed_field`` aus den eigenen Feldern bzw. von der Route gefüllt), der Client zeigt.

⚠ **Gleitkomma-Reihenfolge wie im Client.** Jede Funktion rechnet ihre Operanden in derselben Reihenfolge wie die
ersetzte Client-Formel (``a × b × c`` links nach rechts, ``÷ 100`` zuletzt) — sonst wiche die angezeigte Zahl in der
letzten Stelle ab. Die Probe «alte Client-Formel = Feld» (exakter Float-Vergleich) steht im Bericht des Päckchens.

⚠ **Drei Verlust-Gestalten, eine Funktion** (benannt, nicht vereinheitlicht — die Anzeige bleibt): die Wirkungsverluste
gibt es nur bei Ladung > Entladung (``speicher_wirkungsverluste``), die Hub-Kachel «Verlust» zeigt die rohe Differenz
(``nur_positiv=False``, kann bei vertauschten Zählern negativ sein — dazu der Hinweis «Durchsatz inkonsistent»), die
Jahresbilanz klemmt auf 0 (``nur_positiv=True``, «Ladung = Entladung + Verlust»).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from backend.core.berechnungen.ergebnis import quote


def speicher_bilanz_kwh(ladung_kwh: Optional[float], entladung_kwh: Optional[float]) -> Optional[float]:
    """Bilanz = Entladung − Ladung (negativ ist der Normalfall: Wirkungsgrad). ``None``, wenn eine Menge fehlt."""
    if ladung_kwh is None or entladung_kwh is None:
        return None
    return entladung_kwh - ladung_kwh


def speicher_verlust_kwh(
    ladung_kwh: Optional[float], entladung_kwh: Optional[float], *, nur_positiv: bool = False,
) -> Optional[float]:
    """Verlust = Ladung − Entladung; ``nur_positiv=True`` klemmt auf 0 (Jahresbilanz). ``None``, wenn eine Menge fehlt."""
    if ladung_kwh is None or entladung_kwh is None:
        return None
    verlust = ladung_kwh - entladung_kwh
    return max(0.0, verlust) if nur_positiv else verlust


def speicher_pv_ladung_kwh(ladung_kwh: Optional[float], netzladung_kwh: Optional[float]) -> Optional[float]:
    """PV-Ladung = Ladung − Netzladung (fehlende Netzladung zählt 0) — das Segment «PV-Ladung» des Speicher-Hubs.

    Ungeklemmt wie die Kachel; die Monatsreihe (``SpeicherMonatsWert.pv_ladung_kwh``) klemmt selbst auf 0."""
    if ladung_kwh is None:
        return None
    return ladung_kwh - (netzladung_kwh if netzladung_kwh is not None else 0.0)


def speicher_solaranteil_prozent(ladung_kwh: Optional[float], netzladung_kwh: Optional[float]) -> Optional[float]:
    """Solar-Anteil der Ladung in % = max(0, Ladung − Netzladung) ÷ Ladung × 100 (*Cockpit → Jahr*, Speicher je Monat).

    ``None`` ohne erfasste Netzladung (eine Anlage, die sie nicht pflegt, hat nicht «0 % Netz» — P4) oder ohne Ladung."""
    if netzladung_kwh is None or ladung_kwh is None or ladung_kwh <= 0:
        return None
    return max(0.0, ladung_kwh - netzladung_kwh) / ladung_kwh * 100


def netzladung_anteil(netzladung_kwh: Optional[float], ladung_kwh: float) -> tuple[float, bool]:
    """Netz-Anteil der Ladung 0…1 und ob er auf 1 gekappt wurde (N-444/K2).

    Fehlende Netzladung zählt 0; ohne Ladung (≤ 0) ist der Anteil 0. ⛔ Die Kappung ist keine Kosmetik: der Zähler
    ``speicher_ladung_netz_kwh`` ist eine Brutto-, die Ladung eine Netto-Menge (N-197) — läuft der Anteil über 1, wird
    das gesagt (``gekappt``), nicht still korrigiert (ADR-002/P4)."""
    roh = quote(netzladung_kwh if netzladung_kwh is not None else 0.0, ladung_kwh, 1, nur_positiver_nenner=True)
    roh = roh if roh is not None else 0.0
    return min(1.0, roh), roh > 1


@dataclass(frozen=True)
class Wirkungsverluste:
    """Opportunitätskosten des Speicher-Roundtrips eines Zeitraums."""
    verlust_kwh: float
    #: Netz-Anteil der Ladung 0…1 (gekappt)
    anteil_netz: float
    gekappt: bool
    #: Verlust × PV-Anteil — bewertet mit dem Einspeisepreis (entgangene Einspeisung)
    verlust_pv_kwh: float
    #: Verlust × Netz-Anteil — bewertet mit dem Bezugspreis
    verlust_netz_kwh: float
    euro: float


def speicher_wirkungsverluste(
    ladung_kwh: Optional[float],
    entladung_kwh: Optional[float],
    netzladung_kwh: Optional[float],
    einspeise_cent: Optional[float],
    bezug_cent: Optional[float],
    *,
    ein_preis_bekannt: bool,
) -> Optional[Wirkungsverluste]:
    """Wirkungsverluste in € = Verlust × PV-Anteil × Einspeisepreis ÷ 100 + Verlust × Netz-Anteil × Bezugspreis ÷ 100.

    ``None`` ohne Ladung/Entladung, ohne Verlust (Ladung ≤ Entladung) oder wenn kein Preis bekannt ist
    (``ein_preis_bekannt`` — der Aufrufer sagt, welche Preise er dafür fragt; die Cockpit-Sicht fragt Einspeise- und
    Tarif-Bezugspreis, rechnet aber mit dem Ø-Bezugspreis, wo es ihn gibt). Ein fehlender Preis zählt 0.
    Bis Päckchen BB stand die Rechnung im Client (``KomponentenSektionen.tsx::speicherWirkungsverluste``)."""
    if ladung_kwh is None or entladung_kwh is None or ladung_kwh <= entladung_kwh or not ein_preis_bekannt:
        return None
    verlust = speicher_verlust_kwh(ladung_kwh, entladung_kwh)
    anteil_netz, gekappt = netzladung_anteil(netzladung_kwh, ladung_kwh)
    anteil_pv = 1 - anteil_netz
    eins_p = einspeise_cent if einspeise_cent is not None else 0.0
    bez_p = bezug_cent if bezug_cent is not None else 0.0
    verlust_pv = verlust * anteil_pv
    verlust_netz = verlust * anteil_netz
    return Wirkungsverluste(
        verlust_kwh=verlust, anteil_netz=anteil_netz, gekappt=gekappt,
        verlust_pv_kwh=verlust_pv, verlust_netz_kwh=verlust_netz,
        euro=(verlust_pv * eins_p) / 100 + (verlust_netz * bez_p) / 100,
    )
