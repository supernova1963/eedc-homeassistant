"""Aussichten — Trend-Analyse.

GET /api/aussichten/trend/{anlage_id} — Jahresvergleich, saisonale Muster, Degradation
"""
# Reiner Umzug aus `api/routes/aussichten.py` (18.09.2026, Vorlage 7 des Refactorings grosser Dateien):
# Code 1:1 uebernommen, kein Verhaltenswechsel. Die Fassade `__init__.py` haengt den Router ein und exportiert
# die Namen weiter, die Aufrufer und Tests bisher aus dem Modul importierten.

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from backend.api.deps import get_db
from backend.services.prognose_auswahl import lade_aktive_prognose
from backend.core.berechnungen import spezifischer_ertrag_kwh_kwp
from backend.services.monats_fakten import lade_monats_fakten
from backend.api.routes.aussichten.basis import MONATSNAMEN, _lade_anlage_mit_pv
from backend.api.routes.aussichten.schemas import DegradationSchema, JahresVergleichSchema, SaisonaleMusterSchema, TrendAnalyseResponse

router = APIRouter()


@router.get("/trend/{anlage_id}", response_model=TrendAnalyseResponse)
async def get_trend_analyse(
    anlage_id: int,
    jahre: int = Query(default=3, ge=1, le=10, description="Anzahl Jahre für Analyse"),
    db: AsyncSession = Depends(get_db),
):
    """
    Trend-Analyse basierend auf historischen Daten.

    Analysiert:
    - Jahresvergleich der PV-Erträge (PV-Module + Balkonkraftwerke)
    - Saisonale Muster (beste/schlechteste Monate)
    - Degradation (Leistungsrückgang über Zeit) mit TMY-Auffüllung für unvollständige Jahre
    """
    # RF-33 (Komplexitäts-Paket RF-29…RF-39, 23.10.2026, Bauform RF-1): die Phasen stehen als Modulfunktionen
    # unter der Route; Abfragefolge unverändert (Anlage, PVGIS, Monats-Fakten).
    from datetime import date

    anlage, pv_module, balkonkraftwerke, anlagenleistung_kwp = await _lade_anlage_mit_pv(
        db, anlage_id, require_coords=False
    )

    # Aktive PVGIS-Prognose (Auswahl-SoT, P5)
    pvgis = await lade_aktive_prognose(db, anlage_id)
    pvgis_jahresertrag = pvgis.jahresertrag_kwh if pvgis else 0

    # PVGIS Monatswerte für TMY-Auffüllung
    pvgis_monatswerte = _pvgis_monatswerte(pvgis)

    # Historische Daten (PV-Module + BKW)
    jahres_ertraege, monats_ertraege = await _historische_ertraege(db, anlage_id, pv_module, balkonkraftwerke)

    # Jahresvergleich mit Unterjährigkeits-Info
    heute = date.today()
    start_jahr = heute.year - jahre + 1
    jahres_vergleich = _jahres_vergleich(
        jahres_ertraege, start_jahr, heute, anlagenleistung_kwp, pvgis_jahresertrag,
    )

    # Saisonale Muster
    beste_monate, schlechteste_monate = _saisonale_muster(monats_ertraege)

    degradation_prozent, degradation_hinweis, degradation_methode, degradation_zuverlaessig = _degradation(
        jahres_vergleich, jahres_ertraege, pvgis_monatswerte, heute,
    )

    return TrendAnalyseResponse(
        anlage_id=anlage_id,
        anlagenname=anlage.anlagenname or f"Anlage {anlage_id}",
        anlagenleistung_kwp=anlagenleistung_kwp,
        analyse_zeitraum={"von": start_jahr, "bis": heute.year},
        jahres_vergleich=jahres_vergleich,
        saisonale_muster=SaisonaleMusterSchema(
            beste_monate=beste_monate,
            schlechteste_monate=schlechteste_monate,
        ),
        degradation=DegradationSchema(
            geschaetzt_prozent_jahr=degradation_prozent,
            hinweis=degradation_hinweis,
            methode=degradation_methode,
            zuverlaessig=degradation_zuverlaessig,
        ),
        datenquellen=["historische-daten", "pvgis-tmy"] if degradation_methode == "tmy_ergaenzt" else ["historische-daten"],
    )


def _pvgis_monatswerte(pvgis) -> dict:
    """RF-33 Phase: PVGIS-Monatswerte {monat: e_m} für die TMY-Auffüllung (leer ohne Prognose)."""
    pvgis_monatswerte = {}
    if pvgis and pvgis.monatswerte:
        for mw in pvgis.monatswerte:
            pvgis_monatswerte[mw.get("monat")] = mw.get("e_m", 0)
    return pvgis_monatswerte


async def _historische_ertraege(db: AsyncSession, anlage_id: int, pv_module, balkonkraftwerke) -> tuple[dict, dict]:
    """RF-33 Phase: PV-Erträge je Jahr (kWh, Monate, je Monat) und je Monat aus den Monats-Fakten (P10)."""
    pv_modul_ids = [m.id for m in pv_module]
    bkw_ids = [b.id for b in balkonkraftwerke]
    alle_pv_ids = pv_modul_ids + bkw_ids
    jahres_ertraege = {}  # {jahr: {"kwh": X, "monate": set(), "monate_daten": {monat: kwh}}}
    monats_ertraege = {}

    if alle_pv_ids:
        # Historisches IST aus den Monats-Fakten (ADR-002/**P10**) — dieselbe
        # Begründung wie in der Langfrist-Prognose oben (Register N-1): die
        # rohe IMD-Summe verlor die PV komplett, sobald die Erzeugung nur als
        # Anlagen-Aggregat gepflegt war, und der Degradations-/Jahresvergleich
        # zeigte dann leere Jahre statt der gemessenen Erträge.
        fakten = await lade_monats_fakten(db, anlage_id)

        for fakt in fakten:
            jahr = fakt.jahr
            monat = fakt.monat
            kwh = fakt.erzeugung.pv_kwh

            if kwh > 0:
                if jahr not in jahres_ertraege:
                    jahres_ertraege[jahr] = {"kwh": 0, "monate": set(), "monate_daten": {}}
                jahres_ertraege[jahr]["kwh"] += kwh
                jahres_ertraege[jahr]["monate"].add(monat)
                jahres_ertraege[jahr]["monate_daten"][monat] = jahres_ertraege[jahr]["monate_daten"].get(monat, 0) + kwh

                if monat not in monats_ertraege:
                    monats_ertraege[monat] = []
                monats_ertraege[monat].append(kwh)

    return jahres_ertraege, monats_ertraege


def _jahres_vergleich(jahres_ertraege: dict, start_jahr: int, heute, anlagenleistung_kwp, pvgis_jahresertrag) -> list:
    """RF-33 Phase: eine `JahresVergleichSchema`-Zeile je Jahr des Analysezeitraums (mit Unterjährigkeit)."""
    jahres_vergleich = []

    for jahr in range(start_jahr, heute.year + 1):
        jahr_daten = jahres_ertraege.get(jahr, {"kwh": 0, "monate": set(), "monate_daten": {}})
        gesamt_kwh = jahr_daten["kwh"]
        anzahl_monate = len(jahr_daten["monate"])

        # Aktuelles Jahr: Max mögliche Monate = aktueller Monat
        max_monate = heute.month if jahr == heute.year else 12
        ist_vollstaendig = anzahl_monate >= max_monate

        spez_ertrag = spezifischer_ertrag_kwh_kwp(gesamt_kwh, anlagenleistung_kwp) or 0
        pr = gesamt_kwh / pvgis_jahresertrag if pvgis_jahresertrag > 0 else None

        jahres_vergleich.append(JahresVergleichSchema(
            jahr=jahr,
            gesamt_kwh=round(gesamt_kwh, 1),
            spezifischer_ertrag_kwh_kwp=round(spez_ertrag, 0),
            performance_ratio=round(pr, 3) if pr else None,
            anzahl_monate=anzahl_monate,
            ist_vollstaendig=ist_vollstaendig,
        ))

    return jahres_vergleich


def _saisonale_muster(monats_ertraege: dict) -> tuple[list, list]:
    """RF-33 Phase: die drei besten und schlechtesten Monate nach Ø-Ertrag."""
    monats_durchschnitte = []
    for monat in range(1, 13):
        ertraege = monats_ertraege.get(monat, [])
        avg = sum(ertraege) / len(ertraege) if ertraege else 0
        monats_durchschnitte.append((monat, avg))

    sortiert = sorted(monats_durchschnitte, key=lambda x: x[1], reverse=True)
    beste_monate = [MONATSNAMEN[m[0]] for m in sortiert[:3] if m[1] > 0]
    schlechteste_monate = [MONATSNAMEN[m[0]] for m in sortiert[-3:] if m[1] > 0]
    return beste_monate, schlechteste_monate


def _degradation(jahres_vergleich: list, jahres_ertraege: dict, pvgis_monatswerte: dict, heute):
    """RF-33 Phase: Degradation je Jahr — vollständige Jahre, sonst TMY-ergänzt; Hinweis ohne Wert; Kappung."""
    # Degradation - Strategie:
    # 1. Primär: Nur vollständige Jahre (12 Monate) verwenden
    # 2. Fallback: Unvollständige Jahre mit TMY-Daten auffüllen (wenn Performance-Ratio verfügbar)
    degradation_prozent = None
    degradation_hinweis = "Nicht genügend Daten für Schätzung"
    degradation_methode = None

    # Nur Jahre mit 12 Monaten Daten für Degradation verwenden
    vollstaendige_jahre = [(jv.jahr, jv.gesamt_kwh) for jv in jahres_vergleich if jv.anzahl_monate == 12 and jv.gesamt_kwh > 0]

    if len(vollstaendige_jahre) >= 2:
        # Primäre Methode: Nur vollständige Jahre
        erstes = vollstaendige_jahre[0]
        letztes = vollstaendige_jahre[-1]
        if erstes[1] > 0:
            jahre_diff = letztes[0] - erstes[0]
            if jahre_diff > 0:
                aenderung = (letztes[1] - erstes[1]) / erstes[1] * 100
                degradation_prozent = round(aenderung / jahre_diff, 2)
                degradation_hinweis = f"Basierend auf {len(vollstaendige_jahre)} vollständigen Jahren ({vollstaendige_jahre[0][0]}-{vollstaendige_jahre[-1][0]})"
                degradation_methode = "vollstaendig"

    # Fallback: TMY-Auffüllung wenn nicht genug vollständige Jahre
    aufgefuellte_jahre = None
    if degradation_prozent is None and pvgis_monatswerte:
        aufgefuellte_jahre, degradation_prozent, degradation_hinweis, degradation_methode = _degradation_tmy(
            jahres_ertraege, pvgis_monatswerte, heute, degradation_hinweis,
        )

    degradation_hinweis = _hinweis_ohne_degradation(
        degradation_prozent, vollstaendige_jahre, jahres_vergleich, degradation_hinweis,
    )

    degradation_prozent, degradation_hinweis, degradation_zuverlaessig = _degradation_kappen(
        degradation_prozent, degradation_hinweis, degradation_methode, vollstaendige_jahre, aufgefuellte_jahre,
    )
    return degradation_prozent, degradation_hinweis, degradation_methode, degradation_zuverlaessig


def _degradation_tmy(jahres_ertraege: dict, pvgis_monatswerte: dict, heute, degradation_hinweis: str):
    """RF-33 Phase (Fallback): unvollständige Jahre ab 6 Monaten mit TMY × PR auffüllen und daraus die Degradation.

    Läuft nur, wenn die vollständigen Jahre keinen Wert ergaben — dann sind Wert und Methode noch `None`.
    Rückgabe: `(aufgefuellte_jahre, degradation_prozent, degradation_hinweis, degradation_methode)`."""
    degradation_prozent = None
    degradation_methode = None
    # Versuche unvollständige Jahre mit TMY aufzufüllen
    # Berechne Performance-Ratio pro Jahr aus vorhandenen Monaten
    aufgefuellte_jahre = []

    for jahr, daten in jahres_ertraege.items():
        monate_mit_daten = daten["monate"]
        monate_daten = daten["monate_daten"]

        if len(monate_mit_daten) >= 6:  # Mindestens 6 Monate für sinnvolle PR
            # Performance-Ratio aus vorhandenen Monaten berechnen
            ist_summe = sum(monate_daten.values())
            soll_summe = sum(pvgis_monatswerte.get(m, 0) for m in monate_mit_daten)

            if soll_summe > 0:
                pr = ist_summe / soll_summe

                # Fehlende Monate mit TMY * PR auffüllen
                fehlende_monate = set(range(1, 13)) - monate_mit_daten
                # Aktuelles Jahr: Nur bis zum aktuellen Monat auffüllen
                if jahr == heute.year:
                    fehlende_monate = fehlende_monate & set(range(1, heute.month + 1))

                ergaenzte_kwh = sum(pvgis_monatswerte.get(m, 0) * pr for m in fehlende_monate)
                gesamt_aufgefuellt = ist_summe + ergaenzte_kwh

                # Für aktuelle Jahre: Auf Jahreswert hochrechnen
                if jahr == heute.year and heute.month < 12:
                    # Hochrechnung auf 12 Monate mit TMY-Verteilung
                    restliche_monate = set(range(heute.month + 1, 13))
                    prognose_rest = sum(pvgis_monatswerte.get(m, 0) * pr for m in restliche_monate)
                    gesamt_aufgefuellt += prognose_rest

                aufgefuellte_jahre.append((jahr, gesamt_aufgefuellt, len(monate_mit_daten)))

    if len(aufgefuellte_jahre) >= 2:
        aufgefuellte_jahre.sort(key=lambda x: x[0])
        erstes = aufgefuellte_jahre[0]
        letztes = aufgefuellte_jahre[-1]

        if erstes[1] > 0:
            jahre_diff = letztes[0] - erstes[0]
            if jahre_diff > 0:
                aenderung = (letztes[1] - erstes[1]) / erstes[1] * 100
                degradation_prozent = round(aenderung / jahre_diff, 2)
                monate_info = ", ".join([f"{j[0]}: {j[2]}/12 Mon." for j in aufgefuellte_jahre])
                degradation_hinweis = f"TMY-ergänzt aus {len(aufgefuellte_jahre)} Jahren ({monate_info})"
                degradation_methode = "tmy_ergaenzt"
    elif len(aufgefuellte_jahre) == 1:
        degradation_hinweis = f"Nur 1 Jahr mit ausreichend Daten ({aufgefuellte_jahre[0][2]}/12 Monate) - mindestens 2 Jahre nötig"

    return aufgefuellte_jahre, degradation_prozent, degradation_hinweis, degradation_methode


def _hinweis_ohne_degradation(degradation_prozent, vollstaendige_jahre: list, jahres_vergleich: list, degradation_hinweis: str) -> str:
    """RF-33 Phase: der Hinweis, warum es keinen Degradationswert gibt (unverändert, wenn es einen gibt)."""
    if degradation_prozent is None and len(vollstaendige_jahre) == 1:
        degradation_hinweis = "Nur 1 vollständiges Jahr vorhanden - mindestens 2 Jahre für Degradations-Berechnung nötig"
    elif degradation_prozent is None:
        # Prüfe ob es unvollständige Jahre gibt
        unvollstaendige = [jv for jv in jahres_vergleich if jv.anzahl_monate < 12 and jv.gesamt_kwh > 0]
        if unvollstaendige:
            min_monate = min(j.anzahl_monate for j in unvollstaendige)
            max_monate = max(j.anzahl_monate for j in unvollstaendige)
            if min_monate < 6:
                degradation_hinweis = f"Unvollständige Jahre mit nur {min_monate}-{max_monate} Monaten - mindestens 6 Monate pro Jahr für TMY-Ergänzung nötig"
            else:
                degradation_hinweis = f"Noch kein vollständiges Jahr - aktuell nur unvollständige Jahre mit {min_monate}-{max_monate} Monaten"
    return degradation_hinweis


def _degradation_kappen(
    degradation_prozent, degradation_hinweis: str, degradation_methode, vollstaendige_jahre: list, aufgefuellte_jahre,
):
    """RF-33 Phase: positive Degradation auf 0 kappen und die Zuverlässigkeit (ab 3 Datenjahren) setzen.

    `aufgefuellte_jahre` ist `None`, wenn der TMY-Zweig nicht lief — dieselbe Bedingung, die der Ausdruck
    `'aufgefuellte_jahre' in dir()` im Route-Körper prüfte (bis RF-33)."""
    # Positive Degradation kappen (physikalisch nicht möglich, sondern Wetterschwankung)
    degradation_zuverlaessig = False
    if degradation_prozent is not None:
        anzahl_datenjahre = len(vollstaendige_jahre) if degradation_methode == "vollstaendig" else len(aufgefuellte_jahre) if aufgefuellte_jahre is not None else 0
        if degradation_prozent > 0:
            degradation_prozent = 0.0
            degradation_hinweis += " – Ertragssteigerung durch Wetterschwankungen, keine messbare Degradation"
        if anzahl_datenjahre >= 3:
            degradation_zuverlaessig = True
        else:
            degradation_hinweis += " – Wert mit Vorsicht interpretieren (min. 3 Jahre empfohlen)"
    return degradation_prozent, degradation_hinweis, degradation_zuverlaessig
