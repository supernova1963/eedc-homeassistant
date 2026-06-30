"""Grundlast (Nacht-Sockel) — Median der Nacht-Stunden-Leistung + Anteil am
Gesamtverbrauch.

Aggregat-Kennzahl im Sinn von ADR-001 (core/berechnungen): das *Sourcing* (die
Nacht-Stunden 0–5 Uhr aus `TagesEnergieProfil.verbrauch_kw`) bleibt Aufgabe des
Aufrufers — hier ausschließlich die Formel.

Spiegelt bewusst die Live-„Grundlast" (`api/routes/live_wetter.py`): **Median**
statt Minimum, robust gegen einzelne Ausreißer-Nächte. Auf Monat/Jahr aggregiert
ersetzt diese verbrauchsnahe Kennzahl den PVGIS-SOLL/IST-Block (R12-1, Tester
rapahl: PVGIS = „Maximum des Erreichbaren", er wünscht einen Hausverbrauchs-Bezug).

Definition:
    grundlast_kw   = Median der Nacht-Stunden-Leistung (0–5 Uhr, verbrauch_kw > 0)
    grundlast_kwh  = grundlast_kw × 24 × Tage   (Sockel läuft rund um die Uhr)
    anteil_prozent = grundlast_kwh / gesamtverbrauch_kwh × 100

`grundlast_kwh` ist bewusst **additiv** gehalten, damit die Cockpit/Jahr-Sicht
(Client-Aggregation `JahrAggregat`) die Monatswerte summieren und den Anteil aus
den Summen neu bilden kann — analog zu `soll_pv_kwh`.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class GrundlastKennzahlen:
    """Abgeleitete Grundlast-Kennzahlen (Nacht-Sockel)."""

    grundlast_kw: float | None              # Median der Nacht-Stunden-Leistung [kW]
    grundlast_kwh: float | None             # geschätzte Grundlast-Energie über den Zeitraum [kWh]
    grundlast_anteil_prozent: float | None  # Anteil am Gesamtverbrauch [%]


def _median(werte: list[float]) -> float:
    s = sorted(werte)
    n = len(s)
    mid = n // 2
    return s[mid] if n % 2 else (s[mid - 1] + s[mid]) / 2


def berechne_grundlast(
    *,
    nacht_verbrauch_kw: list[float],
    gesamtverbrauch_kwh: float | None,
    tage: int,
) -> GrundlastKennzahlen:
    """Grundlast-Kennzahlen aus den gesammelten Nacht-Stunden-Leistungen.

    `nacht_verbrauch_kw` = bereits gefilterte Stundenmittel-Leistungen der
    Nachtstunden (0–5 Uhr) über den Zeitraum; `tage` = abgedeckte Kalendertage
    (für die Energie-Hochrechnung des Sockels). Fehlen Stundendaten (leere Liste),
    ist die Grundlast nicht ermittelbar → alle Werte `None` (der Aufrufer fällt dann
    auf PVGIS-SOLL/IST zurück).
    """
    if not nacht_verbrauch_kw or tage <= 0:
        return GrundlastKennzahlen(None, None, None)
    kw = round(_median(nacht_verbrauch_kw), 2)
    kwh = round(kw * 24 * tage, 1)
    anteil = (
        round(kwh / gesamtverbrauch_kwh * 100, 1)
        if gesamtverbrauch_kwh and gesamtverbrauch_kwh > 0
        else None
    )
    return GrundlastKennzahlen(grundlast_kw=kw, grundlast_kwh=kwh, grundlast_anteil_prozent=anteil)
