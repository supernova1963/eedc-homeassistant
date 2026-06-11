"""Spezifischer Ertrag (kWh/kWp) — saisonal gewichtete Annualisierung.

SoT für die periodengenaue Annualisierung des spezifischen Ertrags (ADR-001).
Roh-Division ``pv_erzeugung / kWp`` ergibt bei Teiljahren einen viel zu
niedrigen und über mehrere Jahre einen aufkumulierten Wert (Rainer-PN
2026-06-11: HA-Sensor zeigte 1.955 kWh/kWp = Laufzeit-Summe). Stattdessen wird
der Nenner als Σ kWp·Jahres-Äquivalente über die tatsächlich abgedeckten
Monate gebildet:

- saisonal gewichtet über die PVGIS-Monatsverteilung (Fallback: typische
  52°N-Verteilung) — Jan–Mai sind ~30 % des Jahresertrags, nicht 42 %;
- mit der pro Monat TATSÄCHLICH aktiven PV-Leistung (Erweiterung /
  Teil-Rückbau, siehe Regressionstests in test_cockpit_spez_ertrag_periode).

Konsumenten: Cockpit-Übersicht (Kachel) + HA-Export (Sensor) — beide müssen
denselben Wert liefern (Symmetrie-Test test_ha_export_spez_ertrag_symmetrie).
"""

from __future__ import annotations

from typing import Iterable, Mapping, Optional, Sequence

# Typische 52°N-Monatsverteilung (Prozent des Jahresertrags) — Fallback,
# wenn keine PVGIS-Prognose mit Monatswerten vorliegt. Summe ≈ 100.
MONATSGEWICHTE_52N: dict[int, float] = {
    1: 2.5, 2: 4.5, 3: 8.0, 4: 11.5, 5: 13.0, 6: 13.5,
    7: 13.5, 8: 12.0, 9: 9.0, 10: 6.5, 11: 3.5, 12: 2.5,
}

PV_ERZEUGER_TYPEN = ("pv-module", "balkonkraftwerk")


def monatsgewichte_aus_pvgis(monatswerte: Optional[Iterable[Mapping]]) -> dict[int, float]:
    """PVGIS-``monatswerte`` → ``{monat: e_m}``-Gewichte; ``{}`` wenn unbrauchbar."""
    gewichte: dict[int, float] = {}
    for entry in monatswerte or []:
        try:
            m = int(entry.get("monat"))
            e = float(entry.get("e_m") or 0.0)
        except (TypeError, ValueError, AttributeError):
            continue
        if 1 <= m <= 12 and e > 0:
            gewichte[m] = e
    return gewichte


def kwp_aktiv_im_monat(investitionen: Sequence, jahr: int, monat: int) -> float:
    """Im Monat tatsächlich aktive PV-Leistung (PV-Module + Balkonkraftwerke)."""
    kwp = 0.0
    for inv in investitionen:
        if inv.typ not in PV_ERZEUGER_TYPEN:
            continue
        if not inv.ist_aktiv_im_monat(jahr, monat):
            continue
        if inv.typ == "pv-module" and inv.leistung_kwp:
            kwp += inv.leistung_kwp
        elif inv.typ == "balkonkraftwerk":
            if inv.leistung_kwp:
                kwp += inv.leistung_kwp
            else:
                params = inv.parameter or {}
                bkw_anzahl = params.get("anzahl", 1) or 1
                kwp += (params.get("leistung_wp", 0) or 0) * bkw_anzahl / 1000
    return kwp


def berechne_spez_ertrag_annualisiert(
    pv_erzeugung_kwh: float,
    covered_months: set[tuple[int, int]],
    investitionen: Sequence,
    fallback_kwp: float,
    monatsgewichte: Optional[dict[int, float]] = None,
) -> Optional[float]:
    """Annualisierter spezifischer Ertrag in kWh/kWp.

    Args:
        pv_erzeugung_kwh: Σ PV-Erzeugung über die abgedeckten Monate.
        covered_months: ``{(jahr, monat)}`` — Monate, in denen tatsächlich ein
            PV-Erzeuger aktiv war UND Daten vorliegen. Monate ohne PV
            (WP-/Zähler-Vorzeit) dürfen NICHT enthalten sein, sonst wird der
            Periodenanteil aufgebläht.
        investitionen: Investitionen der Anlage (für per-Monat-aktives kWp).
        fallback_kwp: Anlagenleistung als Fallback, wenn pro Monat kein kWp
            ermittelbar ist (Investitionen ohne Anschaffungsdatum / reine
            Zähler-Setups) — und für den Roh-Pfad ohne covered_months.
        monatsgewichte: ``{monat: Gewicht}`` (z. B. PVGIS ``e_m``);
            ``None``/leer → 52°N-Fallback-Verteilung.

    Returns:
        kWh/kWp p.a. oder ``None``, wenn keine Berechnung möglich ist.
    """
    gewichte = monatsgewichte or MONATSGEWICHTE_52N
    weight_sum_year = sum(gewichte.values())

    denom_kwp_jahre = 0.0  # Summe kWp·Jahres-Äquivalente
    if covered_months and weight_sum_year > 0:
        for (j, m) in covered_months:
            w = gewichte.get(m, 0.0) / weight_sum_year
            kwp_m = kwp_aktiv_im_monat(investitionen, j, m)
            if kwp_m <= 0:
                kwp_m = fallback_kwp
            denom_kwp_jahre += kwp_m * w

    if denom_kwp_jahre > 0 and pv_erzeugung_kwh > 0:
        return pv_erzeugung_kwh / denom_kwp_jahre
    if fallback_kwp > 0:
        return pv_erzeugung_kwh / fallback_kwp if pv_erzeugung_kwh > 0 else None
    return None
