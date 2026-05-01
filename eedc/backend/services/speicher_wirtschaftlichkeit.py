"""Speicher- und V2H-Wirtschaftlichkeit — Single Source of Truth.

Anlass: Drift-Audit Domäne A3 (`docs/drafts/INVENTUR-DRIFT-AUDIT.md`).
Zwei Modelle waren parallel im Einsatz:
- Investitionen-Detail rechnete `entladung × (bezug − einspeise)` (Spread)
- Aussichten rechnete `entladung × bezug` (Voll-Strompreis)
Bei typischem Tarif (30/8 ct) ergab das **36% Differenz** für dieselbe Anlage.

Entscheidung: **Spread-Modell** ist ökonomisch korrekt — die Speicher-Energie
hätte sonst Einspeise-Vergütung erwirtschaftet, also ist die Netto-Ersparnis
nur der Differenzbetrag (Bezug − Einspeise).

Gleiche Logik gilt für V2H: PV-Energie die ins Auto und dann via V2H zurück
ins Haus fließt, hätte sonst eingespeist werden können → Spread.

Limitierung: bei dynamischen Strompreisen / Arbitrage-Speicher ist der
„Spread" zeitabhängig — siehe `arbitrage_gewinn` als separate Berechnung.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class SpeicherErsparnisErgebnis:
    """Ergebnis Speicher- oder V2H-Ersparnis-Berechnung."""
    ersparnis_euro: float
    spread_cent_kwh: float


def berechne_speicher_ersparnis(
    *,
    entladung_kwh: float,
    bezug_preis_cent: float,
    einspeise_verg_cent: float,
) -> SpeicherErsparnisErgebnis:
    """Spread-Ersparnis: Was hätte die gespeicherte Energie sonst gebracht?

    Args:
        entladung_kwh: Aus Speicher entladene Energie in kWh
        bezug_preis_cent: Bezugspreis in ct/kWh (allgemeiner Tarif)
        einspeise_verg_cent: Einspeisevergütung in ct/kWh (alternative Verwendung)

    Returns:
        Ersparnis = entladung × (bezug − einspeise)
    """
    if entladung_kwh <= 0:
        return SpeicherErsparnisErgebnis(0.0, 0.0)
    spread = max(0.0, bezug_preis_cent - einspeise_verg_cent)
    ersparnis = entladung_kwh * spread / 100
    return SpeicherErsparnisErgebnis(ersparnis_euro=ersparnis, spread_cent_kwh=spread)


def berechne_v2h_ersparnis(
    *,
    v2h_entladung_kwh: float,
    bezug_preis_cent: float,
    einspeise_verg_cent: float,
) -> SpeicherErsparnisErgebnis:
    """V2H-Spread-Ersparnis (analog Speicher).

    V2H-Energie ersetzt Haushaltsstrom-Bezug, hätte aber alternativ
    eingespeist werden können (bei PV-Ladung) bzw. wurde zum Wallbox-Tarif
    geladen (bei Netzladung). Pragmatisch wird hier das gleiche Spread-Modell
    wie für Speicher verwendet — bei reiner PV-Quelle ist das exakt; bei
    Netz-Ladung leicht überschätzt.
    """
    return berechne_speicher_ersparnis(
        entladung_kwh=v2h_entladung_kwh,
        bezug_preis_cent=bezug_preis_cent,
        einspeise_verg_cent=einspeise_verg_cent,
    )
