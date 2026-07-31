"""Dienstliche Ladekosten — der Gegenposten zur Arbeitgeber-Erstattung.

Single Source of Truth für die Euro-Bewertung der Ladung eines **Dienstwagens**
(``ist_dienstlich``). Die Mengen liefert die Monats-Fakten-Schicht getrennt
ausgewiesen (``EmobFakten.dienstlich_ladung_pv_kwh`` /
``dienstlich_ladung_netz_kwh``); die Bewertung liegt hier, weil sie den
Monatstarif braucht und weil sie an **drei** Sichten hängt (Cockpit/Übersicht,
Aussichten/Finanz-Prognose, HA-Export) — ADR-001, Pflicht 1: eine Formel, ein
Ort.

Warum es diesen Posten überhaupt gibt
-------------------------------------
Die Erstattung des Arbeitgebers wird als **Ertrag** in den Sonstige-Positionen
erfasst. Damit gehört die Gegenseite als **Ausgabe** sichtbar daneben; erst der
Saldo ist der echte Vorteil der Anlage. Ausgewiesen bleibt beides: die
EV-Ersparnis in voller Höhe **und** dieser Kostenposten.

Die beiden Preise, und warum sie verschieden sind (N-18, Gernot 2026-07-31)
--------------------------------------------------------------------------
::

    ladekosten = Σ_m ( netz_kwh_m × wallbox_preis_cent_m
                     + pv_kwh_m   × netzbezug_preis_cent_m ) / 100

- **Netzanteil × Wallbox-Preis.** Der Strom ist am Netz gekauft worden; er kostet
  den Wallbox-Tarif, wenn es einen gibt, sonst den Anlagentarif (die Kaskade löst
  ``resolve_strompreis_for_komponente`` auf, den Flex-Ø des Monats
  ``resolve_netzbezug_preis_cent`` — beides steckt schon in
  ``TarifFakten.wallbox_preis_effektiv_cent``). Bis 2026-07-31 nahm das Cockpit
  diesen Preis, die Aussichten den allgemeinen Arbeitspreis — dieselbe Ausgabe,
  zwei Zahlen (N-12).
- **PV-Anteil × NETZBEZUGS-Preis, nicht Einspeisevergütung.** Das ist der Kern
  von N-18 und der unintuitive Teil: ``berechne_finanz_aggregat`` schreibt
  ``ev_ersparnis = Eigenverbrauch × netzbezug_preis_cent`` gut, und der
  Eigenverbrauch ändert sich durch das Dienstwagen-Flag **nicht** — die dienstlich
  geladenen kWh sind energetisch Eigenverbrauch hinter dem Zähler. Der Haushalt
  hat durch sie aber **nichts** gespart: der Strom ist weggefahren. Der Abzug zum
  Netzbezugspreis nimmt genau diese Gutschrift zurück.

  Die *entgangene Einspeisevergütung* braucht dagegen **keinen** Buchungssatz —
  sie steckt bereits in der niedrigeren **gemessenen** Einspeisung. Genau das war
  bis 2026-07-31 andersherum gebucht (Abzug zur Vergütung, Gutschrift zum
  Netzbezugspreis) und brachte netto **+22 ct je verschenkter kWh**:

  ==========================================  ==============  ============
  PV 1.000 · Einspeisung 400 · Bezug 100          Eigenverbr.   Netto-Ertrag
  30/8 ct · 200 kWh PV in den Wagen
  ==========================================  ==============  ============
  gar kein Auto (200 kWh eingespeist)              400 kWh        168,00 €
  Privatwagen                                      600 kWh        212,00 €
  Dienstwagen — bis 2026-07-31                     600 kWh        196,00 €
  Dienstwagen — seither                            600 kWh        152,00 €
  ==========================================  ==============  ============

**Die Energiebilanz bleibt unangetastet.** Eigenverbrauchs-kWh, EV-Quote und
Autarkie ändern sich durch diesen Posten nicht und dürfen es nicht — energetisch
IST die Ladung Eigenverbrauch. Korrigiert wird ausschließlich die **Bewertung**
(Gernot 2026-07-31; Register-Eintrag N-18/N-12/N-13).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class DienstlicheLadungZeile:
    """Ein Monat dienstlicher Ladung mit den Preisen **dieses** Monats (P8).

    Mengen in kWh, Preise in ct/kWh. ``netzbezug_preis_cent`` und
    ``wallbox_preis_cent`` sind die bereits aufgelösten **effektiven**
    Monatspreise (Flex-Ø vor Stammdaten-Arbeitspreis) — die Auflösung bleibt
    beim Caller bzw. in ``TarifFakten``, weil sie ein ``Monatsdaten``-Objekt
    braucht (ADR-001: Layer DB-frei).
    """

    ladung_pv_kwh: float = 0.0
    ladung_netz_kwh: float = 0.0
    netzbezug_preis_cent: float = 0.0
    wallbox_preis_cent: float = 0.0


@dataclass(frozen=True)
class DienstlicheLadekosten:
    """Der Kostenposten, getrennt nach Herkunft der kWh."""

    gesamt_euro: float
    """Σ beider Anteile — was von den Sonstige-Positionen abgeht."""

    pv_anteil_euro: float
    """Rücknahme der EV-Gutschrift für dienstlich geladene PV."""

    netz_anteil_euro: float
    """Am Netz gekaufter Strom, der dienstlich weggefahren wurde."""

    pv_kwh: float
    netz_kwh: float


def berechne_dienstliche_ladekosten(
    zeilen: Iterable[DienstlicheLadungZeile],
) -> DienstlicheLadekosten:
    """Bewertet dienstliche Ladung per-Monat und summiert.

    Args:
        zeilen: pro Monat eine ``DienstlicheLadungZeile``, bereits auf sichtbare
            Monate und auf Dienstwagen gefiltert (das tut die Monats-Fakten-
            Schicht — dieser Helper kennt keine Investition und filtert nicht).

    Returns:
        ``DienstlicheLadekosten``; ``gesamt_euro`` ist der Betrag, den die
        Read-Site von ihren Sonstige-Positionen abzieht.
    """
    pv_euro = 0.0
    netz_euro = 0.0
    pv_kwh = 0.0
    netz_kwh = 0.0

    for z in zeilen:
        _pv = z.ladung_pv_kwh or 0.0
        _netz = z.ladung_netz_kwh or 0.0
        pv_kwh += _pv
        netz_kwh += _netz
        # PV-Anteil zum NETZBEZUGSPREIS — nimmt die EV-Gutschrift zurück
        # (nicht zur Einspeisevergütung, s. Modul-Docstring).
        pv_euro += _pv * (z.netzbezug_preis_cent or 0.0) / 100
        netz_euro += _netz * (z.wallbox_preis_cent or 0.0) / 100

    return DienstlicheLadekosten(
        gesamt_euro=pv_euro + netz_euro,
        pv_anteil_euro=pv_euro,
        netz_anteil_euro=netz_euro,
        pv_kwh=pv_kwh,
        netz_kwh=netz_kwh,
    )
