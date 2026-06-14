"""Speicher- und V2H-Wirtschaftlichkeit — DB-gebundene Rekonstruktionen.

Pure/DB-Split (Schläfer-Abbau Block 4): die **reinen** Spread-/Aggregat-
Funktionen leben jetzt im Berechnungs-Layer
(`backend.core.berechnungen.speicher_wirtschaftlichkeit`, ADR-001). Dieses
Service-Modul behält nur die Funktionen mit DB-I/O (`AsyncSession`,
`db.execute`, `TagesEnergieProfil`-Queries) und re-exportiert die reinen
Symbole für Bestands-Caller (Backward-Compat).

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
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.tages_energie_profil import TagesEnergieProfil

# Re-Export der reinen Funktionen/Typen/Konstanten aus dem Berechnungs-Layer.
# Bestands-Caller importieren weiter aus diesem Service-Modul; SoT ist
# `core.berechnungen.speicher_wirtschaftlichkeit` (Pure/DB-Split Block 4).
from backend.core.berechnungen.speicher_wirtschaftlichkeit import (  # noqa: F401
    ETA_DEGRADATION_SCHWELLE_PROZENTPUNKTE,
    SOC_DRIFT_SCHWELLE_PROZENTPUNKTE,
    SPEICHER_IST_MIN_MONATE,
    SpeicherErsparnisErgebnis,
    SpeicherIstAggregat,
    aggregiere_speicher_ist,
    berechne_speicher_ersparnis,
    berechne_v2h_ersparnis,
    ist_eta_degradation_alarm,
    ist_soc_drift_signifikant,
)

logger = logging.getLogger(__name__)


# Mindest-Abdeckung Stunden-mit-Preis im TEP-Fenster, damit der
# stundengewichtete Ø-Ladepreis als belastbar gilt. Darunter signalisiert
# der Helper `quelle="datenbasis-zu-duenn"` und der Caller (UI) zeigt den
# Param-Wert mit Hinweis-Badge — kein silentes Ausblenden.
LADEPREIS_STUNDEN_ABDECKUNG_MIN: float = 0.80

# Mindest-Fenster (Monate) Inv-Monatsdaten für die η-IST-Berechnung über
# rein quotienten-basierte Aggregation. Unter dieser Schwelle wird die
# SoC-Korrektur benötigt, sonst ist das Monats-η unzuverlässig.
WIRKUNGSGRAD_FENSTER_MONATE_MIN: int = 6


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
    # Spalten-Projektion statt voller ORM-Zeilen: der Helper braucht nur diese
    # vier Float-Spalten. Volle TEP-Objekte würden pro Zeile zwei JSON-Spalten
    # (komponenten + source_provenance) deserialisieren — bei mehrjährigen
    # Anlagen sind das zehntausende Stundenzeilen und der Hauptkostenfaktor des
    # Speicher-Dashboards (#333). Filter bleibt batterie_kw IS NOT NULL (nicht
    # < 0), damit `stunden_gesamt_im_fenster` und die quelle-Unterscheidung
    # keine-tep-daten vs. keine-netzladung (UI-Badge) exakt erhalten bleiben.
    result = await db.execute(
        select(
            TagesEnergieProfil.batterie_kw,
            TagesEnergieProfil.netzbezug_kw,
            TagesEnergieProfil.strompreis_cent,
            TagesEnergieProfil.boersenpreis_cent,
        )
        .where(
            TagesEnergieProfil.anlage_id == anlage_id,
            TagesEnergieProfil.datum >= von,
            TagesEnergieProfil.datum <= bis,
            TagesEnergieProfil.batterie_kw.isnot(None),
        )
        .order_by(TagesEnergieProfil.datum, TagesEnergieProfil.stunde)
    )
    rows = result.all()

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
