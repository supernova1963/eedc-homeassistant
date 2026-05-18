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

Etappe B (Issue #264): Der Spread-Service unterscheidet jetzt PV- und
Netz-Anteil der Entladung. Aus dem Netz geladene Energie hätte nicht
eingespeist werden können → die Spread-Annahme greift dort nicht. Der
Netz-Anteil bringt nur einen Vorteil, wenn der Ladepreis < Bezugspreis
ist (klassisches Arbitrage-Setup). Stundengranulare Ladepreise und
SoC-tolerante η-Bilanz folgen in Etappe C.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Optional


# Mindest-Monate IST-Historie, ab der die Routes auf das gemessene
# Aggregat statt der reinen Prognose umschalten. Unter dieser Schwelle ist
# die Stichprobe zu klein für eine belastbare Hochrechnung auf das Jahr.
SPEICHER_IST_MIN_MONATE: int = 3


@dataclass
class SpeicherIstAggregat:
    """Aus IMD aggregierte Jahres-IST-Werte für einen Speicher.

    Felder sind bereits auf das Jahr hochgerechnet — `jahres_faktor` ist
    die genutzte Skalierung (12 / anzahl_monate) und dient nur der
    Nachvollziehbarkeit im Detail-Dict / Diagnose.
    """
    entladung_kwh_jahr: float
    ladung_netz_kwh_jahr: float
    ladung_kwh_jahr: float
    anzahl_monate: int
    jahres_faktor: float


def aggregiere_speicher_ist(
    verbrauch_daten_je_monat: Iterable[dict],
) -> Optional[SpeicherIstAggregat]:
    """Aggregiert IST-Monatsdaten eines Speichers auf Jahreswerte.

    Erwartet eine Iterable von `verbrauch_daten`-Dicts (typischerweise aus
    `InvestitionMonatsdaten.verbrauch_daten`), die der Caller bereits auf
    aktive Monate des Speichers gefiltert hat (`Investition.ist_aktiv_im_monat`).

    Liefert `None`, wenn weniger als `SPEICHER_IST_MIN_MONATE` Monate
    vorliegen oder gar keine Entladung erfasst ist — der Caller fällt
    dann auf das Prognose-Modell zurück.
    """
    entladung_sum = 0.0
    ladung_netz_sum = 0.0
    ladung_sum = 0.0
    monate = 0

    for data in verbrauch_daten_je_monat:
        if not data:
            continue
        monate += 1
        entladung_sum += float(data.get("entladung_kwh") or 0)
        # `ladung_netz_kwh` ist der Kanon (siehe field_definitions.LEGACY_FELDNAMEN);
        # Legacy-Key `speicher_ladung_netz_kwh` als Fallback für historische Rows.
        ladung_netz_sum += float(
            data.get("ladung_netz_kwh") or data.get("speicher_ladung_netz_kwh") or 0
        )
        ladung_sum += float(data.get("ladung_kwh") or 0)

    if monate < SPEICHER_IST_MIN_MONATE or entladung_sum <= 0:
        return None

    # Auf 12 Monate hochrechnen — bei weniger als 12 erfassten Monaten ist das
    # eine konservative Annahme (Saison-Effekte werden geglättet). Bei ≥ 12
    # ist `jahres_faktor` < 1 und kürzt fair auf einen Jahreswert.
    jahres_faktor = 12.0 / monate

    return SpeicherIstAggregat(
        entladung_kwh_jahr=entladung_sum * jahres_faktor,
        ladung_netz_kwh_jahr=ladung_netz_sum * jahres_faktor,
        ladung_kwh_jahr=ladung_sum * jahres_faktor,
        anzahl_monate=monate,
        jahres_faktor=jahres_faktor,
    )


@dataclass
class SpeicherErsparnisErgebnis:
    """Ergebnis Speicher- oder V2H-Ersparnis-Berechnung."""
    ersparnis_euro: float
    spread_cent_kwh: float
    # Aufgliederung der Ersparnis nach Energie-Quelle (Etappe B).
    # Ohne Netzladung: pv_anteil_euro = ersparnis_euro, netz_anteil_euro = 0.
    pv_anteil_euro: float = 0.0
    netz_anteil_euro: float = 0.0
    # kWh-Aufteilung der Entladung — für Frontend-KPI / Diagnose.
    pv_anteil_entladung_kwh: float = 0.0
    netz_anteil_entladung_kwh: float = 0.0


def berechne_speicher_ersparnis(
    *,
    entladung_kwh: float,
    bezug_preis_cent: float,
    einspeise_verg_cent: float,
    ladung_netz_kwh: float = 0.0,
    wirkungsgrad_prozent: float = 95.0,
    lade_preis_cent: Optional[float] = None,
) -> SpeicherErsparnisErgebnis:
    """Spread-Ersparnis mit Netz-/PV-Aufteilung (Etappe B Issue #264).

    Ohne Netzladung (`ladung_netz_kwh=0`) entspricht das Ergebnis exakt
    dem alten Verhalten: Spread = entladung × (bezug − einspeise).

    Bei gepflegter Netzladung wird die Entladung auf zwei Quellen aufgeteilt:

      netz_anteil_entladung = min(entladung, ladung_netz × η)
      pv_anteil_entladung   = entladung − netz_anteil_entladung

    Der PV-Anteil bringt weiterhin den Spread (Energie hätte sonst eingespeist
    werden können). Der Netz-Anteil bringt nur dann einen Vorteil, wenn ein
    `lade_preis_cent` gepflegt ist und unter dem Bezugspreis liegt — sonst
    ist die Netzladung kostenneutrale Durchleitung (z. B. Backup-Vorhaltung).

    Args:
        entladung_kwh: Aus Speicher entladene Energie in kWh
        bezug_preis_cent: Bezugspreis in ct/kWh (allgemeiner Tarif)
        einspeise_verg_cent: Einspeisevergütung in ct/kWh
        ladung_netz_kwh: Gepflegte Netzladung in kWh (Default 0 — reiner PV-Speicher)
        wirkungsgrad_prozent: Speicher-Wirkungsgrad (Default 95 %)
        lade_preis_cent: Ø-Ladepreis Netz in ct/kWh (None → Bezugspreis, kein Vorteil)

    Returns:
        SpeicherErsparnisErgebnis mit pv_anteil_euro + netz_anteil_euro Aufschlüsselung.
    """
    if entladung_kwh <= 0:
        return SpeicherErsparnisErgebnis(0.0, 0.0)

    spread = max(0.0, bezug_preis_cent - einspeise_verg_cent)

    # Backwards-kompat: ohne Netzladung-Datenpunkt verhält sich die Funktion
    # genau wie vorher (PV-100%-Annahme, alleiniger Spread-Term).
    if ladung_netz_kwh <= 0:
        ersparnis = entladung_kwh * spread / 100
        return SpeicherErsparnisErgebnis(
            ersparnis_euro=ersparnis,
            spread_cent_kwh=spread,
            pv_anteil_euro=ersparnis,
            netz_anteil_euro=0.0,
            pv_anteil_entladung_kwh=entladung_kwh,
            netz_anteil_entladung_kwh=0.0,
        )

    # Netz-Anteil der Entladung = eingebrachte Netz-Energie nach Wirkungsgrad,
    # aber höchstens die tatsächlich entladene Menge (Clamp).
    wirkungsgrad = max(0.0, min(1.0, wirkungsgrad_prozent / 100.0))
    netz_anteil_entladung = min(entladung_kwh, ladung_netz_kwh * wirkungsgrad)
    pv_anteil_entladung = max(0.0, entladung_kwh - netz_anteil_entladung)

    # PV-Anteil: Spread wie bisher.
    pv_ersparnis = pv_anteil_entladung * spread / 100

    # Netz-Anteil: nur Vorteil, wenn Ladepreis < Bezugspreis (Arbitrage).
    # Ohne gepflegten Ladepreis → kostenneutrale Annahme (Bezugspreis = Ladepreis).
    ladepreis_eff = bezug_preis_cent if lade_preis_cent is None else lade_preis_cent
    netz_spread = max(0.0, bezug_preis_cent - ladepreis_eff)
    netz_ersparnis = netz_anteil_entladung * netz_spread / 100

    return SpeicherErsparnisErgebnis(
        ersparnis_euro=pv_ersparnis + netz_ersparnis,
        spread_cent_kwh=spread,
        pv_anteil_euro=pv_ersparnis,
        netz_anteil_euro=netz_ersparnis,
        pv_anteil_entladung_kwh=pv_anteil_entladung,
        netz_anteil_entladung_kwh=netz_anteil_entladung,
    )


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
