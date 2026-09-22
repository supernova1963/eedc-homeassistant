"""Speicher-/V2H-Wirtschaftlichkeit — reine Aggregat-Berechnungen.

Berechnungs-Layer-Heimat (ADR-001) für die **DB-freien** Funktionen aus der
Speicher-Wirtschaftlichkeit. Der Pure/DB-Split (Schläfer-Abbau Block 4):
hier liegen die reinen Spread-/Aggregat-Funktionen, die DB-gebundenen
Rekonstruktionen (effektiver Ladepreis, SoC-korrigierter IST-Wirkungsgrad)
bleiben in `backend.services.speicher_wirtschaftlichkeit`.

Hintergrund (Drift-Audit Domäne A3, `docs/archive/INVENTUR-DRIFT-AUDIT.md`):
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


#: Warum ein IST-Aggregat nicht zustande kam — das Vokabular von
#: `speicher_ist_mit_grund`. Beide Gründe führen zum selben Rückfall auf das
#: Prognose-Modell, aber zu **verschiedenen** Ratschlägen an den Anwender:
#: „warte noch" gegen „erfass die Entladung deines Speichers".
GRUND_ZU_WENIG_MONATE = "zu-wenig-monate"
GRUND_KEINE_ENTLADUNG = "keine-entladung"


def speicher_ist_mit_grund(
    verbrauch_daten_je_monat: Iterable[dict],
) -> tuple[Optional["SpeicherIstAggregat"], Optional[str]]:
    """Wie `aggregiere_speicher_ist` — und sagt bei `None`, **warum**.

    ⭐ **Warum es diese Funktion gibt** (Nachlese 4.0.50, A7): Bis zum
    22.09.2026 warf `aggregiere_speicher_ist` zwei völlig verschiedene Lagen in
    denselben Rückgabewert:

    * **Zu wenig Monate** — die Anlage ist jung, die Messung kommt von selbst.
    * **Keine Entladung erfasst** — die Monate sind da, aber das Feld
      `entladung_kwh` ist leer. Das geht nie von allein weg; der Anwender muss
      eine Quelle zuordnen oder den Wert pflegen.

    Der HA-Export beschriftete beide als `zu-wenig-monate` und riet damit der
    Hälfte der Betroffenen das Falsche („warte noch ein paar Monate"). Der
    Rückfall auf den gepflegten Parameter ist in beiden Fällen derselbe — nur
    der Satz daneben unterscheidet sich, und genau den verlangt
    KONZEPT-FLEX-TARIFE §8 („keine stille Ersetzung").

    Returns:
        `(aggregat, None)` wenn es zustande kam, sonst `(None, grund)` mit
        `GRUND_ZU_WENIG_MONATE` oder `GRUND_KEINE_ENTLADUNG`. **Die Reihenfolge
        ist festgelegt:** zu wenige Monate gewinnt, denn ohne genug Monate ist
        über die Entladung noch gar nichts zu sagen.
    """
    return _aggregiere(verbrauch_daten_je_monat)


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

    ⭐ Wer den **Grund** braucht, ruft `speicher_ist_mit_grund` daneben; diese
    Signatur bleibt, weil drei Aufrufer nur das Aggregat wollen
    (`services/speicher_wirtschaftlichkeit.py`, `investitionen/roi_pv.py`,
    `investitionen/dashboard_speicher.py` über den Service).
    """
    return _aggregiere(verbrauch_daten_je_monat)[0]


def _aggregiere(
    verbrauch_daten_je_monat: Iterable[dict],
) -> tuple[Optional[SpeicherIstAggregat], Optional[str]]:
    """Die eine Faltung hinter beiden Einstiegen — ein Durchlauf, eine Regel."""
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

    if monate < SPEICHER_IST_MIN_MONATE:
        return None, GRUND_ZU_WENIG_MONATE
    if entladung_sum <= 0:
        return None, GRUND_KEINE_ENTLADUNG

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
    ), None


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
    # ⭐ **Der Wirkungsgrad gehört an die MENGE, nicht an den Spread**
    # (17.09.2026, SOLL Flex-Tarife §6).
    #
    # ⛔ Hier stand `netz_anteil_entladung × (B − P)`. Ausmultipliziert ist das
    # `L·η·B − L·η·P` — die Ladekosten wurden also ebenfalls mit η verkleinert.
    # Bezahlt hat der Anwender aber die **eingespeicherte** Menge, nicht die
    # nutzbare: richtig ist `L·η·B − L·P`. Die Differenz `L·P·(1−η)` fehlte im
    # ausgewiesenen Gewinn — bei 1.000 kWh Netzladung, 20 ct und η = 90 % rund
    # 20 €/Jahr zu **hoch**.
    bezahlte_netzladung = (
        netz_anteil_entladung / wirkungsgrad if wirkungsgrad > 0
        else netz_anteil_entladung
    )
    # ⚠ Die Klemmung bei 0 bleibt vorerst: Ohne gepflegten Ladepreis ist
    # `ladepreis_eff == bezug_preis_cent`, und der Term wird dann rechnerisch
    # negativ (die Verluste kosten) — die dokumentierte Semantik ist an dieser
    # Stelle aber „kostenneutrale Durchleitung", nicht „Verlust". Ob ein
    # Arbitrage-Gewinn negativ werden **darf**, wenn ein echter Ladepreis
    # vorliegt und teurer war als der Nutzen, ist eine eigene Entscheidung und
    # hier bewusst nicht getroffen.
    netz_ersparnis = max(0.0, (
        netz_anteil_entladung * bezug_preis_cent
        - bezahlte_netzladung * ladepreis_eff
    ) / 100)

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


@dataclass
class NetzladungKosten:
    """Monats-Kosten der Speicher-Netzladung (R15-1, Rainer-Kostenkachel).

    `quelle` benennt die Preis-Herkunft in absteigender Güte:
    - "tep"         — stundengewichteter effektiver Ladepreis (#264 Etappe C)
    - "imd"         — kWh-gewichteter Ø aus manuell erfassten IMD-Ladepreisen
    - "bezugspreis" — Netzladung läuft zum normalen Bezugspreis (keine
                      Arbitrage-Erfassung; Ø-Monatspreis vor festem Tarif)
    - "keine"       — 0 kWh Netzladung: Kosten 0 €, ein Preis existiert nicht

    `preis_cent` ist bei 0 kWh Netzladung `None` — ein erfundener Nullpreis wäre
    schlechter als das Anzeige-Token „—".
    """
    kosten_euro: float
    preis_cent: Optional[float]
    quelle: str


def berechne_netzladung_kosten(
    netzladung_kwh: Optional[float],
    *,
    eff_ladepreis_cent: Optional[float] = None,
    imd_preis_cent: Optional[float] = None,
    netzbezug_preis_cent: Optional[float] = None,
) -> Optional[NetzladungKosten]:
    """Kosten der Netzladung = Netzladung × bester verfügbarer Ladepreis.

    Preis-Kette: TEP-effektiv → IMD-Ø (Monatsabschluss-Handeingabe) →
    Bezugspreis (Ø-Monatspreis bzw. Tarif).

    `netzladung_kwh is None` → `None`: es gibt keinen Speicher bzw. keine Daten,
    die Kachel bleibt aus. **0 kWh ist dagegen eine Aussage** („diesen Monat
    nichts aus dem Netz geladen") und liefert 0,00 € — sonst muss der Nutzer an
    anderer Stelle nachsehen, ob wirklich nichts gelaufen ist (Rainer-PN
    2026-07-25; korrigiert die ursprüngliche R15-1-Regel „kein 0-€-Rauschen").
    Netzladung > 0 ohne jeden ermittelbaren Preis → `None`: die Kosten sind dann
    unbekannt, nicht 0 (praktisch unerreichbar, da der Bezugspreis aus der
    Finanzzeile immer trägt).
    """
    if netzladung_kwh is None:
        return None
    if netzladung_kwh <= 0:
        return NetzladungKosten(kosten_euro=0.0, preis_cent=None, quelle="keine")
    if eff_ladepreis_cent is not None and eff_ladepreis_cent > 0:
        preis, quelle = eff_ladepreis_cent, "tep"
    elif imd_preis_cent is not None and imd_preis_cent > 0:
        preis, quelle = imd_preis_cent, "imd"
    elif netzbezug_preis_cent is not None and netzbezug_preis_cent > 0:
        preis, quelle = netzbezug_preis_cent, "bezugspreis"
    else:
        return None
    return NetzladungKosten(
        kosten_euro=round(netzladung_kwh * preis / 100, 2),
        preis_cent=round(preis, 2),
        quelle=quelle,
    )
