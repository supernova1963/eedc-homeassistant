"""Energie-Bilanz aus stündlichen ``TagesEnergieProfil``-Rows (ADR-001).

Single Source of Truth für die **Σ-über-Stunden**-Bilanz eines beliebigen
Zeitfensters (ein Tag, ein Monat). Die NULL-/Summen-Semantik ist 1:1 die des
Monats-Endpoints ``get_monatsauswertung`` (energie_profil/views.py): NULL-
Stunden zählen **nicht** als 0, Überschuss/Defizit/Direktverbrauch nur wenn
PV **und** Verbrauch vorhanden, Batterie richtungsgetrennt.

Damit gilt für jedes additive Feld die Invariante

    Σ ( bilanz_aus_stundenrows(tag_n) )  ==  bilanz_aus_stundenrows(ganzer_monat)

per Konstruktion — die der Symmetrie-Test
``test_tage_werte_symmetrie`` gegen den bestehenden Monats-Endpoint absichert
([[feedback_aggregator_symmetrie]]). Die Tages-Werte-Embed-Sicht (IA v4 E3,
Cockpit/Monat) speist sich daraus, statt die Aggregat-Logik im Frontend zu
duplizieren ([[feedback_aggregations_drift]]).

DB-frei: nimmt eine Iterable beliebiger Objekte mit den Attributen
``pv_kw``/``verbrauch_kw``/``einspeisung_kw``/``netzbezug_kw``/``batterie_kw``/
``waermepumpe_kw`` (duck-typed → ORM-Rows wie Test-Stubs).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Optional, Protocol

from backend.core.berechnungen.kennzahlen import (
    autarkie_prozent,
    eigenverbrauchsquote_prozent,
)


class _StundenRow(Protocol):
    pv_kw: Optional[float]
    verbrauch_kw: Optional[float]
    einspeisung_kw: Optional[float]
    netzbezug_kw: Optional[float]
    batterie_kw: Optional[float]
    waermepumpe_kw: Optional[float]


@dataclass
class TagesBilanz:
    """Σ-über-Stunden-Bilanz eines Zeitfensters. Alle kWh additiv über Tage."""

    # Additive kWh-Summen (Σ stündlicher kW × 1 h)
    erzeugung_kwh: float            # = Σ pv_kw (registry: erzeugung)
    gesamtverbrauch_kwh: float      # = Σ verbrauch_kw
    einspeisung_kwh: float
    netzbezug_kwh: float
    ueberschuss_kwh: float          # = Σ max(0, pv − verbrauch)
    defizit_kwh: float              # = Σ max(0, verbrauch − pv)
    direktverbrauch_kwh: float      # = Σ min(pv, verbrauch)
    eigenverbrauch_kwh: float       # = erzeugung − einspeisung (PV-Eigenverbrauch)
    speicher_ladung_kwh: float      # = Σ max(0, −batterie_kw)
    speicher_entladung_kwh: float   # = Σ max(0,  batterie_kw)
    wp_strom_kwh: float             # = Σ waermepumpe_kw
    # Nicht-additive Quoten (%) — None wenn Nenner 0
    autarkie_prozent: Optional[float]
    ev_quote_prozent: Optional[float]
    speicher_effizienz_prozent: Optional[float]
    # Datenqualität
    stunden: int


def bilanz_aus_stundenrows(rows: Iterable[_StundenRow]) -> TagesBilanz:
    """Aggregiert stündliche TEP-Rows zur Energie-Bilanz (siehe Modul-Docstring)."""
    pv_sum = 0.0
    verbrauch_sum = 0.0
    einspeisung_sum = 0.0
    netzbezug_sum = 0.0
    ueberschuss_sum = 0.0
    defizit_sum = 0.0
    direkt_sum = 0.0
    batt_lade_sum = 0.0
    batt_entlade_sum = 0.0
    wp_sum = 0.0
    n = 0

    for r in rows:
        n += 1
        pv = r.pv_kw
        verbrauch = r.verbrauch_kw
        einspeisung = r.einspeisung_kw
        netzbezug = r.netzbezug_kw
        batt = r.batterie_kw
        wp = getattr(r, "waermepumpe_kw", None)

        # NULL überspringt still (statt als 0 zu zählen) — wie get_monatsauswertung.
        if pv is not None:
            pv_sum += pv
        if verbrauch is not None:
            verbrauch_sum += verbrauch
        if einspeisung is not None:
            einspeisung_sum += einspeisung
        if netzbezug is not None:
            netzbezug_sum += netzbezug
        if wp is not None:
            wp_sum += wp

        if pv is not None and verbrauch is not None:
            ueberschuss = pv - verbrauch
            if ueberschuss > 0:
                ueberschuss_sum += ueberschuss
            else:
                defizit_sum += -ueberschuss
            direkt_sum += min(pv, verbrauch)

        if batt is not None:
            if batt < 0:
                batt_lade_sum += -batt
            elif batt > 0:
                batt_entlade_sum += batt

    eigenverbrauch = pv_sum - einspeisung_sum
    # Quoten über den SoT (kennzahlen-Layer); None statt 0 wenn Nenner fehlt,
    # damit die UI '—' statt '0 %' zeigt.
    autarkie = (
        autarkie_prozent(verbrauch_sum - netzbezug_sum, verbrauch_sum)
        if verbrauch_sum > 0 else None
    )
    ev_quote = (
        eigenverbrauchsquote_prozent(eigenverbrauch, pv_sum)
        if pv_sum > 0 else None
    )
    speicher_eff = (
        batt_entlade_sum / batt_lade_sum * 100 if batt_lade_sum > 0.1 else None
    )

    return TagesBilanz(
        erzeugung_kwh=pv_sum,
        gesamtverbrauch_kwh=verbrauch_sum,
        einspeisung_kwh=einspeisung_sum,
        netzbezug_kwh=netzbezug_sum,
        ueberschuss_kwh=ueberschuss_sum,
        defizit_kwh=defizit_sum,
        direktverbrauch_kwh=direkt_sum,
        eigenverbrauch_kwh=eigenverbrauch,
        speicher_ladung_kwh=batt_lade_sum,
        speicher_entladung_kwh=batt_entlade_sum,
        wp_strom_kwh=wp_sum,
        autarkie_prozent=autarkie,
        ev_quote_prozent=ev_quote,
        speicher_effizienz_prozent=speicher_eff,
        stunden=n,
    )
