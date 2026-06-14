"""Speicher-/V2H-Wirtschaftlichkeit — reine Aggregat-Berechnungen.

Berechnungs-Layer-Heimat (ADR-001) für die **DB-freien** Funktionen aus der
Speicher-Wirtschaftlichkeit. Der Pure/DB-Split (Schläfer-Abbau Block 4):
hier liegen die reinen Spread-/Aggregat-Funktionen, die DB-gebundenen
Rekonstruktionen (effektiver Ladepreis, SoC-korrigierter IST-Wirkungsgrad)
bleiben in `backend.services.speicher_wirtschaftlichkeit`.

Hintergrund (Drift-Audit Domäne A3, `docs/drafts/INVENTUR-DRIFT-AUDIT.md`):
Zwei Modelle waren parallel im Einsatz —
- Investitionen-Detail rechnete `entladung × (bezug − einspeise)` (Spread)
- Aussichten rechnete `entladung × bezug` (Voll-Strompreis)
Bei typischem Tarif (30/8 ct) ergab das **36 % Differenz** für dieselbe Anlage.

Entscheidung: **Spread-Modell** ist ökonomisch korrekt — die Speicher-Energie
hätte sonst Einspeise-Vergütung erwirtschaftet, also ist die Netto-Ersparnis
nur der Differenzbetrag (Bezug − Einspeise). Gleiche Logik gilt für V2H.

Etappe B (Issue #264): Der Spread unterscheidet PV- und Netz-Anteil der
Entladung. Aus dem Netz geladene Energie hätte nicht eingespeist werden
können → die Spread-Annahme greift dort nicht; der Netz-Anteil bringt nur
einen Vorteil, wenn der Ladepreis < Bezugspreis ist (Arbitrage).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Optional


# Mindest-Monate IST-Historie, ab der die Routes auf das gemessene
# Aggregat statt der reinen Prognose umschalten. Unter dieser Schwelle ist
# die Stichprobe zu klein für eine belastbare Hochrechnung auf das Jahr.
SPEICHER_IST_MIN_MONATE: int = 3

# Schwelle für „signifikanter SoC-Drift" (Issue #264, Etappe C2):
# |soc_ende − soc_start| > 20 Prozent-Punkte ≈ ein voller Lade-/Entladezyklus
# über die Periodengrenze hinaus. In dem Fall ist der Monats-η-Quotient
# unzuverlässig und der Caller weist stattdessen den Jahres-η aus.
SOC_DRIFT_SCHWELLE_PROZENTPUNKTE: float = 20.0

# Schwelle für den Degradations-Alarm-Badge an der η-KPI (#264 C3):
# Asymmetrisch — Alarm nur bei IST < Param − 5 pp (Verschlechterung). Ein
# IST über Param ist kein Alarmgrund, sondern „Param zu konservativ".
ETA_DEGRADATION_SCHWELLE_PROZENTPUNKTE: float = 5.0


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


def ist_soc_drift_signifikant(
    *,
    soc_start_prozent: Optional[float] = None,
    soc_ende_prozent: Optional[float] = None,
    # Legacy-Signatur (Etappe-C-WIP) — bleibt unterstützt für bestehende Caller:
    delta_soc_kwh: Optional[float] = None,
    ladung_kwh: Optional[float] = None,
) -> bool:
    """True, wenn |soc_ende − soc_start| > Drift-Schwelle in Prozent-Punkten.

    Maintainer-Vorgabe Etappe C2 (Issue #264 Diskussion): „Threshold
    |ΔSoC| > 20 % für signifikant (≈ ein voller Lade-/Entladezyklus über
    Monatsgrenze hinaus)." Schwelle gilt absolut in SoC-Prozent-Punkten,
    nicht relativ zur Periode-Ladung — auch ein voller SoC-Sprung bei
    wenig Lade-Aktivität ist problematisch.

    Legacy-Signatur (`delta_soc_kwh` + `ladung_kwh`) wird weiter
    unterstützt, ist aber deprecated — der Caller sollte SoC-Werte direkt
    übergeben, sobald sie verfügbar sind.
    """
    if soc_start_prozent is not None and soc_ende_prozent is not None:
        return abs(soc_ende_prozent - soc_start_prozent) > SOC_DRIFT_SCHWELLE_PROZENTPUNKTE
    # Legacy-Pfad: kein direkter SoC-Vergleich möglich.
    if delta_soc_kwh is None or ladung_kwh is None or ladung_kwh <= 0:
        return False
    # Bei alter Signatur ohne SoC-Werte: konservativ über Anteil der Ladung,
    # mit derselben 20-pp-Schwelle (20 % der Ladung ≈ relevanter Zyklus).
    return abs(delta_soc_kwh) / ladung_kwh > SOC_DRIFT_SCHWELLE_PROZENTPUNKTE / 100.0


def ist_eta_degradation_alarm(
    *,
    ist_wirkungsgrad_prozent: float,
    param_wirkungsgrad_prozent: float,
) -> bool:
    """True wenn IST-η > 5 pp UNTER dem konfigurierten Param-Wert liegt.

    Asymmetrisch (Etappe C3, Issue #264): ein IST-η ÜBER dem Param ist
    kein Alarmgrund — der User hat den Param dann zu konservativ gepflegt,
    die Speicher-Performance ist besser als erwartet. Nur die Unter-
    schreitung deutet auf Speicher-Degradation hin (Kapazitätsverlust,
    Zellungleichgewicht, BMS-Verschleiß).

    Der Frontend-Badge an der η-KPI nutzt diesen Helper, klickbarer Link
    führt in die Speicher-Investition mit fokussiertem `wirkungsgrad_prozent`.
    """
    differenz = param_wirkungsgrad_prozent - ist_wirkungsgrad_prozent
    return differenz > ETA_DEGRADATION_SCHWELLE_PROZENTPUNKTE
