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
ist (klassisches Arbitrage-Setup).

Etappe C (Issue #264): Stundengranularer effektiver Ladepreis aus
`TagesEnergieProfil` (Tibber/aWATTar-Setups bekommen den echten
Mittel-Ladepreis aus den HA-LTS-Stundenwerten), plus SoC-korrigierte
IST-Wirkungsgrad-Bilanz (löst den 110%-Effekt bei Voll-zu-Leer-
Übergängen über die Monatsgrenze).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date
from typing import Iterable, Optional, TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.tages_energie_profil import TagesEnergieProfil

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


# Mindest-Monate IST-Historie, ab der die Routes auf das gemessene
# Aggregat statt der reinen Prognose umschalten. Unter dieser Schwelle ist
# die Stichprobe zu klein für eine belastbare Hochrechnung auf das Jahr.
SPEICHER_IST_MIN_MONATE: int = 3

# Mindest-Abdeckung Stunden-mit-Preis im TEP-Fenster, damit der
# stundengewichtete Ø-Ladepreis als belastbar gilt. Darunter signalisiert
# der Helper `quelle="datenbasis-zu-duenn"` und der Caller (UI) zeigt den
# Param-Wert mit Hinweis-Badge — kein silentes Ausblenden.
LADEPREIS_STUNDEN_ABDECKUNG_MIN: float = 0.80

# Mindest-Fenster (Monate) Inv-Monatsdaten für die η-IST-Berechnung über
# rein quotienten-basierte Aggregation. Unter dieser Schwelle wird die
# SoC-Korrektur benötigt, sonst ist das Monats-η unzuverlässig.
WIRKUNGSGRAD_FENSTER_MONATE_MIN: int = 6

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


# ============================================================================
# Etappe C (Issue #264): Stundengranulare Ladepreis-Rekonstruktion aus TEP
# ============================================================================


@dataclass
class EffektiverLadepreisErgebnis:
    """Stundengewichteter Ø-Ladepreis für Speicher-Netzladung.

    Etappe C1 (Issue #264 Diskussion): Helper liefert immer ein Ergebnis —
    kein silentes None mehr. `quelle` macht für das Frontend transparent,
    woher der Wert kommt bzw. warum keiner verfügbar ist:

    - `"dyn-tarif"`: Endkundenpreis aus dem HA-Sensor (z. B. Tibber) —
      mindestens eine Stunde hatte `strompreis_cent`. Belastbarster Wert.
    - `"boersenpreis"`: EPEX Day-Ahead aus aWATTar-API (kein dyn. Endkunden-
      tarif konfiguriert). Tarif-Aufschläge fehlen, aber stündliche Verteilung.
    - `"datenbasis-zu-duenn"`: TEP-Stunden vorhanden, aber Preis-Abdeckung
      unter `LADEPREIS_STUNDEN_ABDECKUNG_MIN`. Wert wird trotzdem geliefert,
      darf vom Caller aber nur informativ behandelt werden — das UI zeigt
      Param-Wert plus „Datenbasis zu dünn (m % Abdeckung)"-Badge.
    - `"keine-netzladung"`: TEP-Stunden vorhanden, aber gar keine Netz-Lade-
      Stunde (Speicher rein PV-geladen oder nur entladen). Kein Ladepreis
      ermittelbar — UI zeigt KPI-Box mit Hinweis.
    - `"keine-tep-daten"`: keine TEP-Zeilen im Zeitraum (Anlage frisch
      installiert, HA-LTS noch nicht aggregiert). `effektiver_ladepreis_cent`
      ist `None`; UI fällt auf Param-Wert oder blendet KPI aus.
    """
    quelle: str
    # None bei `"keine-netzladung"` und `"keine-tep-daten"` — UI muss damit
    # umgehen können.
    effektiver_ladepreis_cent: Optional[float]
    netz_lade_kwh: float
    netzlade_stunden_mit_preis: int
    netzlade_stunden_gesamt: int  # Stunden mit echter Netz-Ladung (mit/ohne Preis)
    stunden_gesamt_im_fenster: int  # alle TEP-Stunden im Fenster (Diagnose)

    @property
    def abdeckung_prozent(self) -> float:
        """Anteil der Netzlade-Stunden mit Preis (0..100). Diagnose-Wert
        für das Frontend-Badge bei `quelle="datenbasis-zu-duenn"`."""
        if self.netzlade_stunden_gesamt <= 0:
            return 0.0
        return self.netzlade_stunden_mit_preis / self.netzlade_stunden_gesamt * 100.0


async def berechne_effektiver_ladepreis(
    db: AsyncSession,
    *,
    anlage_id: int,
    von: date,
    bis: date,
) -> EffektiverLadepreisErgebnis:
    """Rekonstruiert den stundengewichteten Ø-Ladepreis der Netzladung.

    Iteriert die TEP-Stundenzeilen im Zeitraum [von, bis] und summiert pro
    Ladestunde:

        ladung_kwh_h = max(0, -batterie_kw_h)        # nur Ladung
        netz_kwh_h   = max(0, netzbezug_kw_h)        # Netzbezug der Stunde
        netz_lade_h  = min(ladung_kwh_h, netz_kwh_h) # NICHT aus PV-Überschuss
        preis_h      = strompreis_cent_h or boersenpreis_cent_h
        kosten_h     = netz_lade_h × preis_h / 100

    Liefert immer ein Ergebnis (Etappe C1) — die `quelle` sagt, was draus
    folgt: Werte mit Quelle `dyn-tarif`/`boersenpreis` sind belastbar,
    `datenbasis-zu-duenn`/`keine-netzladung`/`keine-tep-daten` sind
    informativ für das UI-Badge.
    """
    result = await db.execute(
        select(TagesEnergieProfil)
        .where(
            TagesEnergieProfil.anlage_id == anlage_id,
            TagesEnergieProfil.datum >= von,
            TagesEnergieProfil.datum <= bis,
            TagesEnergieProfil.batterie_kw.isnot(None),
        )
        .order_by(TagesEnergieProfil.datum, TagesEnergieProfil.stunde)
    )
    rows = result.scalars().all()

    if not rows:
        return EffektiverLadepreisErgebnis(
            quelle="keine-tep-daten",
            effektiver_ladepreis_cent=None,
            netz_lade_kwh=0.0,
            netzlade_stunden_mit_preis=0,
            netzlade_stunden_gesamt=0,
            stunden_gesamt_im_fenster=0,
        )

    netz_lade_summe = 0.0
    kosten_summe = 0.0
    stunden_mit_preis = 0
    netzlade_stunden_gesamt = 0  # alle Stunden mit netz_lade > 0 (mit oder ohne Preis)
    hat_endkundenpreis = False

    for row in rows:
        batterie = row.batterie_kw or 0
        if batterie >= 0:
            continue  # nur Ladestunden
        ladung_h = -batterie  # kW × 1 h ≈ kWh (Stundenraster)

        netz = max(0.0, row.netzbezug_kw or 0)
        # Anteil der Ladung, der wirklich aus dem Netz kommt — der Rest
        # ist PV-Überschuss und kostet keinen Ladepreis.
        netz_lade_h = min(ladung_h, netz)
        if netz_lade_h <= 0:
            continue  # PV-only-Ladung — keine Netz-Ladekosten

        netzlade_stunden_gesamt += 1

        preis = row.strompreis_cent if row.strompreis_cent is not None else row.boersenpreis_cent
        if preis is None:
            continue
        if row.strompreis_cent is not None:
            hat_endkundenpreis = True

        netz_lade_summe += netz_lade_h
        kosten_summe += netz_lade_h * preis / 100
        stunden_mit_preis += 1

    # Keine Netz-Ladestunden im Fenster (reiner PV-Speicher oder nur Entladung).
    if netzlade_stunden_gesamt == 0:
        return EffektiverLadepreisErgebnis(
            quelle="keine-netzladung",
            effektiver_ladepreis_cent=None,
            netz_lade_kwh=0.0,
            netzlade_stunden_mit_preis=0,
            netzlade_stunden_gesamt=0,
            stunden_gesamt_im_fenster=len(rows),
        )

    abdeckung = stunden_mit_preis / netzlade_stunden_gesamt
    if abdeckung < LADEPREIS_STUNDEN_ABDECKUNG_MIN:
        # Wert wird trotzdem berechnet (informativ) — das UI kann die Zahl
        # zusammen mit der Abdeckungs-Diagnose anzeigen oder ignorieren.
        logger.info(
            "berechne_effektiver_ladepreis: Netzlade-Stunden-Abdeckung %.0f%% "
            "< Schwelle %.0f%% (anlage=%d, %s..%s)",
            abdeckung * 100, LADEPREIS_STUNDEN_ABDECKUNG_MIN * 100,
            anlage_id, von, bis,
        )
        eff_preis = kosten_summe / netz_lade_summe * 100 if netz_lade_summe > 0 else None
        return EffektiverLadepreisErgebnis(
            quelle="datenbasis-zu-duenn",
            effektiver_ladepreis_cent=eff_preis,
            netz_lade_kwh=netz_lade_summe,
            netzlade_stunden_mit_preis=stunden_mit_preis,
            netzlade_stunden_gesamt=netzlade_stunden_gesamt,
            stunden_gesamt_im_fenster=len(rows),
        )

    return EffektiverLadepreisErgebnis(
        quelle="dyn-tarif" if hat_endkundenpreis else "boersenpreis",
        effektiver_ladepreis_cent=kosten_summe / netz_lade_summe * 100,
        netz_lade_kwh=netz_lade_summe,
        netzlade_stunden_mit_preis=stunden_mit_preis,
        netzlade_stunden_gesamt=netzlade_stunden_gesamt,
        stunden_gesamt_im_fenster=len(rows),
    )


# ============================================================================
# Etappe C (Issue #264): SoC-korrigierte IST-Wirkungsgrad-Bilanz
# ============================================================================


@dataclass
class WirkungsgradErgebnis:
    """SoC-korrigierter IST-Wirkungsgrad eines Speichers.

    Etappe C1 (Issue #264 Diskussion): Helper liefert immer ein Ergebnis.
    `quelle` macht für das Frontend transparent, welcher Pfad genutzt
    wurde bzw. warum kein Wert verfügbar ist:

    - `"fenster_lang"`: rein quotienten-basiert über ein langes Fenster
      (≥ `WIRKUNGSGRAD_FENSTER_MONATE_MIN` Monate) — SoC-Drift mittelt
      sich aus. Belastbarster Wert; UI nutzt diesen für die η-KPI auf
      dem SpeicherDashboard.
    - `"soc_korrigiert"`: kurzes Fenster, dafür mit ΔSoC-Energiebilanz:
      η = (entladung + ΔSoC_kwh) / ladung. Löst den 110%-Effekt.
    - `"fenster-zu-kurz"`: kein langes Fenster UND keine SoC-Werte am
      Periodenrand verfügbar (Anlage frisch, SoC-Sensor nicht konfiguriert).
      `wirkungsgrad_prozent` ist `None`; UI fällt auf Param-η zurück.
    - `"keine-ladung"`: gar keine Lade-Aktivität im Fenster — keine
      η-Berechnung möglich. UI fällt auf Param-η zurück.
    """
    quelle: str
    wirkungsgrad_prozent: Optional[float]
    fenster_monate: int
    ladung_kwh: float
    entladung_kwh: float
    delta_soc_kwh: float


async def berechne_ist_wirkungsgrad(
    db: AsyncSession,
    *,
    anlage_id: int,
    von: date,
    bis: date,
    ladung_kwh: float,
    entladung_kwh: float,
    nutzbare_kapazitaet_kwh: float,
    fenster_monate: int,
) -> WirkungsgradErgebnis:
    """IST-Wirkungsgrad mit SoC-Drift-Korrektur (Etappe C, Issue #264).

    Zwei Berechnungspfade (siehe Maintainer-Klärung C2):

    1. **Langes Fenster** (≥ `WIRKUNGSGRAD_FENSTER_MONATE_MIN` Monate):
       reines `entladung/ladung` — ΔSoC zwischen Anfang und Ende mittelt
       sich aus. Bevorzugt, weil SoC-Werte am Periodenrand nicht immer
       verfügbar sind (Anlage frisch installiert, kein SoC-Sensor in HA).

    2. **SoC-Korrektur**: kurzes Fenster, SoC-Werte aus TEP am Anfang
       und am Ende lesen. Energieerhaltung:

           ladung × η = entladung + ΔSoC_energie
           η_ist     = (entladung + ΔSoC_kwh) / ladung

       Löst den 110%-Effekt bei Voll-zu-Leer-Übergängen.

    Liefert immer ein Ergebnis (Etappe C1) — bei fehlender Datenbasis
    setzt `quelle="fenster-zu-kurz"` und `wirkungsgrad_prozent=None`,
    der Caller fällt auf den Param-η zurück und das UI zeigt einen
    Hinweis-Badge an der η-KPI.
    """
    if ladung_kwh <= 0:
        return WirkungsgradErgebnis(
            quelle="keine-ladung",
            wirkungsgrad_prozent=None,
            fenster_monate=fenster_monate,
            ladung_kwh=ladung_kwh,
            entladung_kwh=entladung_kwh,
            delta_soc_kwh=0.0,
        )

    # Pfad 1: langes Fenster, ΔSoC vernachlässigbar (mittelt sich aus).
    if fenster_monate >= WIRKUNGSGRAD_FENSTER_MONATE_MIN:
        wirkungsgrad = min(1.0, entladung_kwh / ladung_kwh)
        return WirkungsgradErgebnis(
            quelle="fenster_lang",
            wirkungsgrad_prozent=wirkungsgrad * 100,
            fenster_monate=fenster_monate,
            ladung_kwh=ladung_kwh,
            entladung_kwh=entladung_kwh,
            delta_soc_kwh=0.0,
        )

    # Pfad 2: SoC-Korrektur — TEP-Werte am Periodenrand lesen.
    soc_start = await _lese_soc_am_periodenrand(db, anlage_id=anlage_id, datum=von, richtung="erste")
    soc_ende = await _lese_soc_am_periodenrand(db, anlage_id=anlage_id, datum=bis, richtung="letzte")

    if soc_start is None or soc_ende is None or nutzbare_kapazitaet_kwh <= 0:
        # Weder lang genug noch SoC-Werte verfügbar — Caller nimmt Param-η.
        return WirkungsgradErgebnis(
            quelle="fenster-zu-kurz",
            wirkungsgrad_prozent=None,
            fenster_monate=fenster_monate,
            ladung_kwh=ladung_kwh,
            entladung_kwh=entladung_kwh,
            delta_soc_kwh=0.0,
        )

    delta_soc_kwh = (soc_ende - soc_start) / 100.0 * nutzbare_kapazitaet_kwh
    # η = (entladung + verbleibende Energie im Speicher) / Ladung
    wirkungsgrad = (entladung_kwh + delta_soc_kwh) / ladung_kwh
    # Clamp auf physikalisch plausiblen Bereich — bei Messfehlern oder
    # Rest-SoC-Drift kann der Quotient kurzzeitig über 1.0 schießen.
    wirkungsgrad = max(0.0, min(1.0, wirkungsgrad))

    return WirkungsgradErgebnis(
        quelle="soc_korrigiert",
        wirkungsgrad_prozent=wirkungsgrad * 100,
        fenster_monate=fenster_monate,
        ladung_kwh=ladung_kwh,
        entladung_kwh=entladung_kwh,
        delta_soc_kwh=delta_soc_kwh,
    )


async def _lese_soc_am_periodenrand(
    db: AsyncSession,
    *,
    anlage_id: int,
    datum: date,
    richtung: str,  # "erste" | "letzte"
) -> Optional[float]:
    """Liest den SoC-Wert am Periodenrand aus TEP.

    `richtung="erste"`: erste Stunde am `datum` mit `soc_prozent IS NOT NULL`.
    `richtung="letzte"`: letzte Stunde am `datum` mit `soc_prozent IS NOT NULL`.

    Fallback: wenn am exakten `datum` keine SoC-Werte verfügbar sind,
    werden bis zu 3 Tage in die jeweilige Richtung weitergesucht.
    """
    from datetime import timedelta

    for offset in range(4):  # 0,1,2,3
        d = datum + timedelta(days=offset if richtung == "erste" else -offset)
        order = TagesEnergieProfil.stunde.asc() if richtung == "erste" else TagesEnergieProfil.stunde.desc()
        result = await db.execute(
            select(TagesEnergieProfil.soc_prozent)
            .where(
                TagesEnergieProfil.anlage_id == anlage_id,
                TagesEnergieProfil.datum == d,
                TagesEnergieProfil.soc_prozent.isnot(None),
            )
            .order_by(order)
            .limit(1)
        )
        soc = result.scalar_one_or_none()
        if soc is not None:
            return float(soc)
    return None


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
