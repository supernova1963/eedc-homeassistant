"""
Cockpit PV-Strings — SOLL vs. IST Vergleich je PV-Erzeuger (Jahressicht + Gesamtlaufzeit).

**Warum „Erzeuger" und nicht „PV-Modul" (F-10).** Beide Endpunkte hier filterten
bis 2026-08-07 hart auf ``Investition.typ == "pv-module"``. Eine reine
Balkonkraftwerk-Anlage bekam damit eine **leere** Antwort — der Client schreibt
daraufhin „Keine PV-Module gefunden", obwohl das BKW alles trägt, was diese
Sicht braucht (kWp über ``get_erzeuger_kwp``, Ausrichtung und Neigung als eigene
Spalten, ein PVGIS-SOLL seit #367). Gemeldet von azywietz-web in Discussion #366,
**nachdem** #367 als erledigt geschlossen war: dessen Text sprach von „zwei
Endpunkten", es waren aber fünf — die beiden PVGIS-Routen sind seit v4.0.9
erweitert, die String-Sichten hingen an einer anderen Query. Dieselbe Klasse wie
#236: *ein Filter auf einer Schicht reicht nicht, wenn parallele Pfade
existieren.*

Die fachliche Frage dieser Sicht lautet „welche Erzeuger-Einheiten gibt es, und
wie stehen sie zu ihrem SOLL" — nicht „welche Investitionen haben den Typ
`pv-module`". Maßgeblich ist deshalb ``PV_ERZEUGER_TYPEN`` (SoT in
``core/berechnungen/spez_ertrag.py``), nicht eine lokale Typ-Liste.
"""

from datetime import date
from typing import Iterable, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel

from backend.core.exceptions import not_found
from backend.core.investition_kennwerte import get_erzeuger_kwp
from backend.api.deps import get_db
from backend.core.berechnungen import (
    PV_ERZEUGER_TYPEN,
    PV_QUELLE_GEMESSEN,
    PV_QUELLE_VERTEILT,
    PV_QUELLE_FEHLT,
)
from backend.models.anlage import Anlage
from backend.models.investition import Investition
from backend.services.prognose_auswahl import lade_aktive_prognose
from backend.services.pv_monatswerte import lade_pv_je_monat
from backend.api.routes.cockpit._shared import MONATSNAMEN

router = APIRouter()


# Ein Vergleich einzelner Strings setzt gemessene Pro-String-Werte voraus. Sind
# die Modulwerte (auch nur teilweise) aus dem Anlagen-Aggregat nach kWp
# verteilt, haben alle Module per Konstruktion denselben spezifischen Ertrag —
# eine Platzierung wäre dann eine Aussage, die die Daten nicht hergeben
# (Gernot 2026-07-26, A4/E3). Statt „bester/schwächster String" steht dieser Satz.
RANKING_NICHT_MOEGLICH = (
    "Die Werte je Modul sind nicht gemessen, sondern anteilig nach kWp aus der "
    "Gesamterzeugung verteilt. Damit hat rechnerisch jedes Modul denselben "
    "spezifischen Ertrag — ein Vergleich einzelner Strings ist mit diesen Werten "
    "nicht möglich. Dafür braucht jedes Modul einen eigenen Erzeugungs-Sensor "
    "(Einstellungen → Sensor-Zuordnung)."
)


def _rollup_quelle(quellen: Iterable[str]) -> str:
    """Fasst Monats-Quellen zu einer Jahres-/Gesamt-Quelle zusammen.

    Konservativ: ein einziger verteilter Monat macht den Zeitraum „verteilt" —
    der Zeitraumwert ist dann eben nicht durchgängig gemessen. Ohne beitragende
    Monate: ``fehlt``.
    """
    qs = [q for q in quellen]
    if not qs:
        return PV_QUELLE_FEHLT
    if any(q == PV_QUELLE_VERTEILT for q in qs):
        return PV_QUELLE_VERTEILT
    if all(q == PV_QUELLE_GEMESSEN for q in qs):
        return PV_QUELLE_GEMESSEN
    return PV_QUELLE_FEHLT


def _ranking(
    kandidaten: list[tuple[str, Optional[float], str]],
) -> tuple[Optional[str], Optional[str], Optional[str]]:
    """Bester/schwächster String — nur bei durchgängig gemessenen IST-Werten.

    Args:
        kandidaten: ``[(bezeichnung, performance_ratio, ist_quelle), …]``.

    Returns:
        ``(bester, schlechtester, hinweis)``. Ist auch nur ein String nicht
        gemessen, bleibt die Platzierung leer und stattdessen steht der
        Erklärsatz {@link RANKING_NICHT_MOEGLICH} in ``hinweis``.
    """
    if len(kandidaten) <= 1:
        return None, None, None
    if any(quelle != PV_QUELLE_GEMESSEN for _, _, quelle in kandidaten):
        return None, None, RANKING_NICHT_MOEGLICH
    mit_perf = [(name, perf) for name, perf, _ in kandidaten if perf]
    if not mit_perf:
        return None, None, None
    sortiert = sorted(mit_perf, key=lambda x: x[1] or 0, reverse=True)
    schlechtester = sortiert[-1][0] if len(sortiert) > 1 else None
    return sortiert[0][0], schlechtester, None


async def _lade_ist_je_modul(
    db: AsyncSession,
    anlage_id: int,
    pv_module: list[Investition],
    jahr: Optional[int] = None,
) -> tuple[dict[int, dict[int, dict[int, float]]], dict[tuple[int, int, int], str]]:
    """IST-Erzeugung je Modul/Monat über den Read-time-SoT ``resolve_pv_je_modul``.

    Vorher las diese Sicht roh aus den IMD und kannte die Aggregat-Präzedenz
    nicht: wer nur EINEN Gesamt-Sensor hat (≥ 50 % der Multi-String-Anlagen,
    #289/#651), sah hier 0 bzw. eine leere Antwort, während
    ``/monatsdaten/aggregiert`` längst den verteilten Wert lieferte. Jetzt
    liefern beide Pfade dieselbe Zerlegung — Σ je Monat identisch
    ([[feedback_aggregator_symmetrie]]).

    Returns:
        ``(werte, quellen)`` mit ``werte[inv_id][jahr][monat] = kwh`` und
        ``quellen[(inv_id, jahr, monat)]`` = ``gemessen`` | ``verteilt``.
        Die Herkunft hängt am MODUL, nicht am Monat: ein Monat kann gemessene
        und aus dem Aggregat gefüllte Strings zugleich enthalten. Module ohne
        PV-Quelle tauchen in beiden Strukturen nicht auf.
    """
    werte: dict[int, dict[int, dict[int, float]]] = {m.id: {} for m in pv_module}
    quellen: dict[tuple[int, int, int], str] = {}

    # EIN Ladepfad für alle Monats-PV-Sichten (`services/pv_monatswerte.py`):
    # IMD-Werte + Anlagen-Aggregat laden, nach Anschaffungs-/Stilllegungsdatum
    # filtern (#236) und durch `resolve_pv_je_modul` schicken. Diese Funktion
    # trug den Ladeteil bis 2026-07-29 als dritte Kopie — dieselbe Klasse, die
    # `19ae5f73` in Cockpit und HA-Export aufgelöst hat.
    for (j, monat), aufgeloest in sorted((await lade_pv_je_monat(
        db, anlage_id, pv_module, jahr
    )).items()):
        # Herkunft JE MODUL, nicht je Monat: seit der modulweisen Präzedenz
        # (Gernot 2026-07-29) stehen in einem Monat gemessene und aus dem
        # Aggregat gefüllte Strings nebeneinander. Ein Monats-Rollup würde einen
        # echt gemessenen String als „geschätzt (kWp-Anteil)" etikettieren —
        # also genau die Unterscheidung einreißen, um die es bei der Umstellung
        # geht. Die frühere Teil-Lücken-Rückfalllogik entfällt dabei: der SoT
        # liefert den Messwert jetzt selbst, statt ihn zu verwerfen.
        for inv_id, w in aufgeloest.items():
            if w.quelle == PV_QUELLE_FEHLT:
                continue  # Lücke bleibt leer und sichtbar (Daten-Checker meldet sie)
            quellen[(inv_id, j, monat)] = w.quelle
            werte.setdefault(inv_id, {}).setdefault(j, {})[monat] = w.pv_erzeugung_kwh

    return werte, quellen


def _pruefe_prognose_plausibilitaet(prognose, gesamt_kwp: float) -> Optional[str]:
    """Diagnose-Wächter für eine stale/oversize PVGIS-Prognose.

    Die SOLL-Werte stammen aus der zuletzt gespeicherten PVGIS-Prognose. Wird die
    Anlagenleistung (z.B. kWp einer Investition korrigiert) geändert, ohne die
    Prognose neu abzurufen, verteilt sich der alte Jahresertrag über die neue,
    kleinere kWp-Basis — die SOLL kann massiv driften (Sabrina #638: 357 MWh
    SOLL für ein 2,4-kWp-BKW, weil die Prognose für ~357 kWp gerechnet war).

    Bewusst KEIN stilles Capping/Skalieren der Werte: wir geben nur einen
    Hinweis-Text zurück, der Nutzer ruft die Prognose neu ab. Diagnose statt
    stillem Eingriff (feedback_grenze_externe_daten_diagnose).

    Rückgabe: Hinweis-Text bei grober kWp-Abweichung (>20 %), sonst None.
    """
    if not prognose or gesamt_kwp <= 0:
        return None

    # kWp, für die die Prognose gerechnet wurde. Ältere Prognosen ohne
    # gespeicherte gesamt_leistung_kwp aus Jahresertrag / spez. Ertrag ableiten.
    prognose_kwp = prognose.gesamt_leistung_kwp
    if not prognose_kwp and prognose.spezifischer_ertrag_kwh_kwp:
        prognose_kwp = prognose.jahresertrag_kwh / prognose.spezifischer_ertrag_kwh_kwp
    if not prognose_kwp or prognose_kwp <= 0:
        return None

    verhaeltnis = prognose_kwp / gesamt_kwp
    if 0.8 <= verhaeltnis <= 1.2:
        return None

    return (
        f"Die gespeicherte PVGIS-Prognose wurde für {prognose_kwp:.1f} kWp berechnet, "
        f"die Anlage hat aktuell {gesamt_kwp:.1f} kWp. Dadurch passen die SOLL-Werte "
        f"nicht zur Anlage. Bitte die PVGIS-Prognose neu abrufen "
        f"(Einstellungen → PVGIS), damit SOLL und IST wieder zusammenpassen."
    )


class PVStringMonat(BaseModel):
    monat: int
    monat_name: str
    prognose_kwh: float
    ist_kwh: float
    abweichung_kwh: float
    abweichung_prozent: Optional[float]
    performance_ratio: Optional[float]
    # Herkunft des IST-Werts: gemessen | verteilt | fehlt (pv_verteilung-SoT).
    ist_quelle: str = PV_QUELLE_FEHLT


class PVStringDaten(BaseModel):
    investition_id: int
    bezeichnung: str
    leistung_kwp: float
    ausrichtung: Optional[str]
    neigung_grad: Optional[int]
    wechselrichter_id: Optional[int]
    wechselrichter_name: Optional[str]
    prognose_jahr_kwh: float
    ist_jahr_kwh: float
    abweichung_jahr_kwh: float
    abweichung_jahr_prozent: Optional[float]
    performance_ratio_jahr: Optional[float]
    spezifischer_ertrag_kwh_kwp: Optional[float]
    # Herkunft der IST-Jahreswerte (Rollup über die beitragenden Monate).
    ist_quelle: str = PV_QUELLE_FEHLT
    monatswerte: list[PVStringMonat]


class PVStringsResponse(BaseModel):
    anlage_id: int
    jahr: int
    hat_prognose: bool
    # Diagnose-Hinweis bei stale/oversize PVGIS-Prognose (None = plausibel)
    prognose_warnung: Optional[str] = None
    anlagen_leistung_kwp: float
    prognose_gesamt_kwh: float
    ist_gesamt_kwh: float
    abweichung_gesamt_kwh: float
    abweichung_gesamt_prozent: Optional[float]
    strings: list[PVStringDaten]
    bester_string: Optional[str]
    schlechtester_string: Optional[str]
    # Herkunft der IST-Werte über alle Strings (Rollup) + Erklärung, warum es
    # bei verteilten Werten keine Platzierung gibt (None = Ranking gültig).
    ist_quelle: str = PV_QUELLE_FEHLT
    vergleich_hinweis: Optional[str] = None


class PVStringJahreswert(BaseModel):
    jahr: int
    prognose_kwh: float
    ist_kwh: float
    abweichung_prozent: Optional[float]
    performance_ratio: Optional[float]
    ist_quelle: str = PV_QUELLE_FEHLT


class PVStringSaisonalwert(BaseModel):
    monat: int
    monat_name: str
    prognose_kwh: float
    ist_durchschnitt_kwh: float
    ist_summe_kwh: float
    anzahl_jahre: int


class PVStringGesamtlaufzeit(BaseModel):
    investition_id: int
    bezeichnung: str
    leistung_kwp: float
    ausrichtung: Optional[str]
    neigung_grad: Optional[int]
    wechselrichter_name: Optional[str]
    prognose_gesamt_kwh: float
    ist_gesamt_kwh: float
    abweichung_gesamt_prozent: Optional[float]
    performance_ratio_gesamt: Optional[float]
    spezifischer_ertrag_kwh_kwp: Optional[float]
    # Herkunft der IST-Werte über die gesamte Laufzeit (Rollup).
    ist_quelle: str = PV_QUELLE_FEHLT
    jahreswerte: list[PVStringJahreswert]
    saisonalwerte: list[PVStringSaisonalwert]


class PVStringsGesamtlaufzeitResponse(BaseModel):
    anlage_id: int
    hat_prognose: bool
    # Diagnose-Hinweis bei stale/oversize PVGIS-Prognose (None = plausibel)
    prognose_warnung: Optional[str] = None
    anlagen_leistung_kwp: float
    erstes_jahr: int
    letztes_jahr: int
    anzahl_jahre: int
    anzahl_monate: int
    prognose_gesamt_kwh: float
    ist_gesamt_kwh: float
    abweichung_gesamt_kwh: float
    abweichung_gesamt_prozent: Optional[float]
    strings: list[PVStringGesamtlaufzeit]
    saisonal_aggregiert: list[PVStringSaisonalwert]
    bester_string: Optional[str]
    schlechtester_string: Optional[str]
    ist_quelle: str = PV_QUELLE_FEHLT
    vergleich_hinweis: Optional[str] = None


@router.get("/pv-strings/{anlage_id}", response_model=PVStringsResponse)
async def get_pv_strings(
    anlage_id: int,
    jahr: int = Query(default=None, description="Jahr (Default: aktuelles Jahr)"),
    db: AsyncSession = Depends(get_db)
):
    """SOLL vs. IST je PV-Erzeuger (PV-Modulfeld **oder** Balkonkraftwerk)."""
    if jahr is None:
        jahr = date.today().year

    result = await db.execute(select(Anlage).where(Anlage.id == anlage_id))
    anlage = result.scalar_one_or_none()
    if not anlage:
        raise not_found("Anlage", anlage_id)

    # KEIN aktiv-Filter (Issue #123): historische PV-String-Auswertung darf
    # später stillgelegte Strings nicht aus Vergangenheits-Vergleichen ausblenden.
    # Typ-Filter über den SoT `PV_ERZEUGER_TYPEN` (F-10) — ein Balkonkraftwerk
    # ist hier eine Erzeuger-Zeile wie ein String, kein Sonderfall.
    result = await db.execute(
        select(Investition)
        .where(Investition.anlage_id == anlage_id)
        .where(Investition.typ.in_(PV_ERZEUGER_TYPEN))
    )
    pv_module = result.scalars().all()

    if not pv_module:
        return PVStringsResponse(
            anlage_id=anlage_id, jahr=jahr, hat_prognose=False,
            anlagen_leistung_kwp=anlage.leistung_kwp or 0,
            prognose_gesamt_kwh=0, ist_gesamt_kwh=0, abweichung_gesamt_kwh=0,
            abweichung_gesamt_prozent=None, strings=[],
            bester_string=None, schlechtester_string=None,
        )

    wr_ids = [m.parent_investition_id for m in pv_module if m.parent_investition_id]
    wechselrichter_map = {}
    if wr_ids:
        result = await db.execute(select(Investition).where(Investition.id.in_(wr_ids)))
        for wr in result.scalars().all():
            wechselrichter_map[wr.id] = wr.bezeichnung

    # Die AKTIVE Prognose (b2025e0e) über den Auswahl-SoT
    # `services/prognose_auswahl.py` — dort steht die Regel samt Begründung
    # (`ist_aktiv` ist Nutzerwille, „neueste" wäre stumme Übersteuerung).
    prognose = await lade_aktive_prognose(db, anlage_id)
    hat_prognose = prognose is not None

    prognose_monate = {}
    if prognose and prognose.monatswerte:
        for mw in prognose.monatswerte:
            prognose_monate[mw["monat"]] = mw.get("e_m", 0)

    prognose_per_modul: dict[int, dict[int, float]] = {}
    if prognose and prognose.module_monatswerte:
        for inv_id_str, monatsdaten in prognose.module_monatswerte.items():
            try:
                inv_id = int(inv_id_str)
                prognose_per_modul[inv_id] = {mw["monat"]: mw.get("e_m", 0) for mw in monatsdaten}
            except (ValueError, TypeError):
                pass

    # kWp über den SoT-Dispatcher (ADR-002/P3-a): ein nur im `parameter`
    # gepflegtes Modul (#229) zählte hier 0 — damit war der Nenner zu klein und
    # ALLE übrigen Strings bekamen zu viel SOLL zugerechnet. `get_erzeuger_kwp`
    # statt `get_pv_kwp`, weil das Balkonkraftwerk seine kWp aus
    # `leistung_wp × anzahl` bezieht (F-10) und sonst mit 0 im Nenner stünde.
    gesamt_kwp = sum(get_erzeuger_kwp(m) for m in pv_module)
    if gesamt_kwp == 0:
        gesamt_kwp = anlage.leistung_kwp or 1

    # IST je Modul über den Read-time-SoT (A4/b1) statt roh aus den IMD.
    werte_je_modul, ist_quellen = await _lade_ist_je_modul(db, anlage_id, pv_module, jahr=jahr)
    md_by_inv: dict[int, dict[int, float]] = {
        m.id: werte_je_modul.get(m.id, {}).get(jahr, {}) for m in pv_module
    }

    strings_data = []
    prognose_gesamt = 0
    ist_gesamt = 0

    for modul in pv_module:
        modul_kwp = get_erzeuger_kwp(modul)
        kwp_anteil = modul_kwp / gesamt_kwp if gesamt_kwp > 0 else 0
        params = modul.parameter or {}
        ausrichtung = modul.ausrichtung or params.get("ausrichtung")
        neigung = modul.neigung_grad or params.get("neigung_grad")
        monatswerte = []
        prognose_jahr = 0
        ist_jahr = 0
        modul_prognose = prognose_per_modul.get(modul.id)
        months_with_data = set(md_by_inv.get(modul.id, {}).keys())

        for monat in range(1, 13):
            if monat in months_with_data:
                if modul_prognose is not None:
                    prog_monat = modul_prognose.get(monat, 0)
                else:
                    prog_monat = prognose_monate.get(monat, 0) * kwp_anteil
            else:
                prog_monat = 0.0
            ist_monat = md_by_inv.get(modul.id, {}).get(monat, 0)
            abweichung = ist_monat - prog_monat
            abweichung_pct = (abweichung / prog_monat * 100) if prog_monat > 0 else None
            perf_ratio = (ist_monat / prog_monat) if prog_monat > 0 else None
            monatswerte.append(PVStringMonat(
                monat=monat, monat_name=MONATSNAMEN[monat],
                prognose_kwh=round(prog_monat, 1), ist_kwh=round(ist_monat, 1),
                abweichung_kwh=round(abweichung, 1),
                abweichung_prozent=round(abweichung_pct, 1) if abweichung_pct is not None else None,
                performance_ratio=round(perf_ratio, 3) if perf_ratio is not None else None,
                ist_quelle=ist_quellen.get((modul.id, jahr, monat), PV_QUELLE_FEHLT),
            ))
            prognose_jahr += prog_monat
            ist_jahr += ist_monat

        modul_quelle = _rollup_quelle(
            ist_quellen[(modul.id, jahr, m)]
            for m in sorted(months_with_data) if (modul.id, jahr, m) in ist_quellen
        )
        abweichung_jahr = ist_jahr - prognose_jahr
        abweichung_jahr_pct = (abweichung_jahr / prognose_jahr * 100) if prognose_jahr > 0 else None
        perf_ratio_jahr = (ist_jahr / prognose_jahr) if prognose_jahr > 0 else None
        spez_ertrag = (ist_jahr / modul_kwp) if modul_kwp > 0 else None

        strings_data.append(PVStringDaten(
            investition_id=modul.id, bezeichnung=modul.bezeichnung,
            leistung_kwp=modul_kwp, ausrichtung=ausrichtung, neigung_grad=neigung,
            wechselrichter_id=modul.parent_investition_id,
            wechselrichter_name=wechselrichter_map.get(modul.parent_investition_id) if modul.parent_investition_id else None,
            prognose_jahr_kwh=round(prognose_jahr, 1), ist_jahr_kwh=round(ist_jahr, 1),
            abweichung_jahr_kwh=round(abweichung_jahr, 1),
            abweichung_jahr_prozent=round(abweichung_jahr_pct, 1) if abweichung_jahr_pct is not None else None,
            performance_ratio_jahr=round(perf_ratio_jahr, 3) if perf_ratio_jahr is not None else None,
            spezifischer_ertrag_kwh_kwp=round(spez_ertrag, 0) if spez_ertrag is not None else None,
            ist_quelle=modul_quelle,
            monatswerte=monatswerte,
        ))
        prognose_gesamt += prognose_jahr
        ist_gesamt += ist_jahr

    abweichung_gesamt = ist_gesamt - prognose_gesamt
    abweichung_gesamt_pct = (abweichung_gesamt / prognose_gesamt * 100) if prognose_gesamt > 0 else None
    bester_string, schlechtester_string, vergleich_hinweis = _ranking(
        [(s.bezeichnung, s.performance_ratio_jahr, s.ist_quelle) for s in strings_data]
    )

    return PVStringsResponse(
        anlage_id=anlage_id, jahr=jahr, hat_prognose=hat_prognose,
        prognose_warnung=_pruefe_prognose_plausibilitaet(prognose, gesamt_kwp),
        anlagen_leistung_kwp=gesamt_kwp,
        prognose_gesamt_kwh=round(prognose_gesamt, 1),
        ist_gesamt_kwh=round(ist_gesamt, 1),
        abweichung_gesamt_kwh=round(abweichung_gesamt, 1),
        abweichung_gesamt_prozent=round(abweichung_gesamt_pct, 1) if abweichung_gesamt_pct is not None else None,
        strings=strings_data, bester_string=bester_string, schlechtester_string=schlechtester_string,
        ist_quelle=_rollup_quelle([s.ist_quelle for s in strings_data]),
        vergleich_hinweis=vergleich_hinweis,
    )


@router.get("/pv-strings-gesamtlaufzeit/{anlage_id}", response_model=PVStringsGesamtlaufzeitResponse)
async def get_pv_strings_gesamtlaufzeit(
    anlage_id: int,
    db: AsyncSession = Depends(get_db)
):
    """SOLL vs. IST je PV-Erzeuger über die gesamte Laufzeit (s. Modul-Kopf, F-10)."""
    result = await db.execute(select(Anlage).where(Anlage.id == anlage_id))
    anlage = result.scalar_one_or_none()
    if not anlage:
        raise not_found("Anlage", anlage_id)

    # KEIN aktiv-Filter (Issue #123): historische PV-String-Auswertung darf
    # später stillgelegte Strings nicht aus Vergangenheits-Vergleichen ausblenden.
    # Typ-Filter über den SoT `PV_ERZEUGER_TYPEN` (F-10) — ein Balkonkraftwerk
    # ist hier eine Erzeuger-Zeile wie ein String, kein Sonderfall.
    result = await db.execute(
        select(Investition)
        .where(Investition.anlage_id == anlage_id)
        .where(Investition.typ.in_(PV_ERZEUGER_TYPEN))
    )
    pv_module = result.scalars().all()

    _empty = PVStringsGesamtlaufzeitResponse(
        anlage_id=anlage_id, hat_prognose=False,
        anlagen_leistung_kwp=anlage.leistung_kwp or 0,
        erstes_jahr=date.today().year, letztes_jahr=date.today().year,
        anzahl_jahre=0, anzahl_monate=0,
        prognose_gesamt_kwh=0, ist_gesamt_kwh=0,
        abweichung_gesamt_kwh=0, abweichung_gesamt_prozent=None,
        strings=[], saisonal_aggregiert=[],
        bester_string=None, schlechtester_string=None,
    )
    if not pv_module:
        return _empty

    wr_ids = [m.parent_investition_id for m in pv_module if m.parent_investition_id]
    wechselrichter_map = {}
    if wr_ids:
        result = await db.execute(select(Investition).where(Investition.id.in_(wr_ids)))
        for wr in result.scalars().all():
            wechselrichter_map[wr.id] = wr.bezeichnung

    # Dieselbe Auswahlregel wie in der Jahressicht darüber — beide über den
    # Auswahl-SoT, damit zwei Sichten derselben Anlage nicht auf
    # verschiedenen Prognosen stehen können.
    prognose = await lade_aktive_prognose(db, anlage_id)
    hat_prognose = prognose is not None

    prognose_monate = {}
    if prognose and prognose.monatswerte:
        for mw in prognose.monatswerte:
            prognose_monate[mw["monat"]] = mw.get("e_m", 0)

    prognose_per_modul: dict[int, dict[int, float]] = {}
    if prognose and prognose.module_monatswerte:
        for inv_id_str, monatsdaten in prognose.module_monatswerte.items():
            try:
                inv_id = int(inv_id_str)
                prognose_per_modul[inv_id] = {mw["monat"]: mw.get("e_m", 0) for mw in monatsdaten}
            except (ValueError, TypeError):
                pass

    # kWp über den SoT-Dispatcher (ADR-002/P3-a): ein nur im `parameter`
    # gepflegtes Modul (#229) zählte hier 0 — damit war der Nenner zu klein und
    # ALLE übrigen Strings bekamen zu viel SOLL zugerechnet. `get_erzeuger_kwp`
    # statt `get_pv_kwp`, weil das Balkonkraftwerk seine kWp aus
    # `leistung_wp × anzahl` bezieht (F-10) und sonst mit 0 im Nenner stünde.
    gesamt_kwp = sum(get_erzeuger_kwp(m) for m in pv_module)
    if gesamt_kwp == 0:
        gesamt_kwp = anlage.leistung_kwp or 1

    # IST je Modul über den Read-time-SoT (A4/b1) statt roh aus den IMD: die
    # Laufzeit-Jahre entstehen jetzt aus allen Monaten MIT PV-Quelle — also auch
    # aus reinen Aggregat-Monaten, die vorher zu einer leeren Antwort führten.
    md_by_inv, ist_quellen = await _lade_ist_je_modul(db, anlage_id, pv_module)

    jahre = sorted({j for (_, j, _) in ist_quellen})
    if not jahre:
        return _empty

    erstes_jahr = jahre[0]
    letztes_jahr = jahre[-1]
    anzahl_jahre = len(jahre)
    # Distinct (Jahr, Monat) — die Schlüssel tragen seit der modulweisen
    # Provenance zusätzlich die Investitions-ID und würden sonst je Modul zählen.
    anzahl_monate = len({(j, m) for (_, j, m) in ist_quellen})

    strings_data = []
    prognose_gesamt_total = 0
    ist_gesamt_total = 0
    saisonal_agg: dict[int, dict] = {m: {"prognose": 0, "ist_summe": 0, "anzahl": 0} for m in range(1, 13)}

    for modul in pv_module:
        modul_kwp = get_erzeuger_kwp(modul)
        kwp_anteil = modul_kwp / gesamt_kwp if gesamt_kwp > 0 else 0
        params = modul.parameter or {}
        ausrichtung = modul.ausrichtung or params.get("ausrichtung")
        neigung = modul.neigung_grad or params.get("neigung_grad")
        jahreswerte = []
        prognose_string_gesamt = 0
        ist_string_gesamt = 0
        string_saisonal: dict[int, dict] = {m: {"ist_summe": 0, "anzahl": 0} for m in range(1, 13)}
        modul_prognose = prognose_per_modul.get(modul.id)
        modul_quellen: list[str] = []

        for jahr in jahre:
            months_with_data_year = set(md_by_inv.get(modul.id, {}).get(jahr, {}).keys())
            if modul_prognose is not None:
                prognose_jahr = sum(modul_prognose.get(m, 0) for m in months_with_data_year)
            else:
                prognose_jahr = sum(prognose_monate.get(m, 0) for m in months_with_data_year) * kwp_anteil
            ist_jahr = sum(md_by_inv.get(modul.id, {}).get(jahr, {}).get(m, 0) for m in range(1, 13))
            abweichung_pct = ((ist_jahr - prognose_jahr) / prognose_jahr * 100) if prognose_jahr > 0 else None
            perf_ratio = (ist_jahr / prognose_jahr) if prognose_jahr > 0 else None
            jahr_quelle = _rollup_quelle(
                ist_quellen[(modul.id, jahr, m)]
                for m in sorted(months_with_data_year) if (modul.id, jahr, m) in ist_quellen
            )
            jahreswerte.append(PVStringJahreswert(
                jahr=jahr, prognose_kwh=round(prognose_jahr, 1), ist_kwh=round(ist_jahr, 1),
                abweichung_prozent=round(abweichung_pct, 1) if abweichung_pct is not None else None,
                performance_ratio=round(perf_ratio, 3) if perf_ratio is not None else None,
                ist_quelle=jahr_quelle,
            ))
            # Jahre ohne PV-Quelle zählen für den Modul-Rollup nicht mit (sonst
            # zöge ein leeres Jahr die Herkunft der Laufzeit auf „fehlt").
            if jahr_quelle != PV_QUELLE_FEHLT:
                modul_quellen.append(jahr_quelle)
            prognose_string_gesamt += prognose_jahr
            ist_string_gesamt += ist_jahr
            for monat in range(1, 13):
                ist_monat = md_by_inv.get(modul.id, {}).get(jahr, {}).get(monat, 0)
                if ist_monat > 0 or monat in md_by_inv.get(modul.id, {}).get(jahr, {}):
                    string_saisonal[monat]["ist_summe"] += ist_monat
                    string_saisonal[monat]["anzahl"] += 1

        saisonalwerte = []
        for monat in range(1, 13):
            if modul_prognose is not None:
                prognose_monat = modul_prognose.get(monat, 0)
            else:
                prognose_monat = prognose_monate.get(monat, 0) * kwp_anteil
            ist_summe = string_saisonal[monat]["ist_summe"]
            anzahl = string_saisonal[monat]["anzahl"]
            ist_durchschnitt = ist_summe / anzahl if anzahl > 0 else 0
            saisonalwerte.append(PVStringSaisonalwert(
                monat=monat, monat_name=MONATSNAMEN[monat],
                prognose_kwh=round(prognose_monat, 1),
                ist_durchschnitt_kwh=round(ist_durchschnitt, 1),
                ist_summe_kwh=round(ist_summe, 1), anzahl_jahre=anzahl,
            ))
            saisonal_agg[monat]["prognose"] += prognose_monat
            saisonal_agg[monat]["ist_summe"] += ist_summe
            saisonal_agg[monat]["anzahl"] = max(saisonal_agg[monat]["anzahl"], anzahl)

        abweichung_gesamt_pct = ((ist_string_gesamt - prognose_string_gesamt) / prognose_string_gesamt * 100) if prognose_string_gesamt > 0 else None
        perf_ratio_gesamt = (ist_string_gesamt / prognose_string_gesamt) if prognose_string_gesamt > 0 else None
        spez_ertrag = (ist_string_gesamt / modul_kwp) if modul_kwp > 0 else None
        strings_data.append(PVStringGesamtlaufzeit(
            investition_id=modul.id, bezeichnung=modul.bezeichnung,
            leistung_kwp=modul_kwp, ausrichtung=ausrichtung, neigung_grad=neigung,
            wechselrichter_name=wechselrichter_map.get(modul.parent_investition_id) if modul.parent_investition_id else None,
            prognose_gesamt_kwh=round(prognose_string_gesamt, 1),
            ist_gesamt_kwh=round(ist_string_gesamt, 1),
            abweichung_gesamt_prozent=round(abweichung_gesamt_pct, 1) if abweichung_gesamt_pct is not None else None,
            performance_ratio_gesamt=round(perf_ratio_gesamt, 3) if perf_ratio_gesamt is not None else None,
            spezifischer_ertrag_kwh_kwp=round(spez_ertrag, 0) if spez_ertrag is not None else None,
            ist_quelle=_rollup_quelle(modul_quellen),
            jahreswerte=jahreswerte, saisonalwerte=saisonalwerte,
        ))
        prognose_gesamt_total += prognose_string_gesamt
        ist_gesamt_total += ist_string_gesamt

    saisonal_aggregiert = []
    for monat in range(1, 13):
        prognose_s = saisonal_agg[monat]["prognose"]
        ist_summe = saisonal_agg[monat]["ist_summe"]
        anzahl = saisonal_agg[monat]["anzahl"]
        ist_durchschnitt = ist_summe / anzahl if anzahl > 0 else 0
        saisonal_aggregiert.append(PVStringSaisonalwert(
            monat=monat, monat_name=MONATSNAMEN[monat],
            prognose_kwh=round(prognose_s, 1),
            ist_durchschnitt_kwh=round(ist_durchschnitt, 1),
            ist_summe_kwh=round(ist_summe, 1), anzahl_jahre=anzahl,
        ))

    abweichung_gesamt = ist_gesamt_total - prognose_gesamt_total
    abweichung_gesamt_pct = (abweichung_gesamt / prognose_gesamt_total * 100) if prognose_gesamt_total > 0 else None
    bester_string, schlechtester_string, vergleich_hinweis = _ranking(
        [(s.bezeichnung, s.performance_ratio_gesamt, s.ist_quelle) for s in strings_data]
    )

    return PVStringsGesamtlaufzeitResponse(
        anlage_id=anlage_id, hat_prognose=hat_prognose,
        prognose_warnung=_pruefe_prognose_plausibilitaet(prognose, gesamt_kwp),
        anlagen_leistung_kwp=gesamt_kwp,
        erstes_jahr=erstes_jahr, letztes_jahr=letztes_jahr,
        anzahl_jahre=anzahl_jahre, anzahl_monate=anzahl_monate,
        prognose_gesamt_kwh=round(prognose_gesamt_total, 1),
        ist_gesamt_kwh=round(ist_gesamt_total, 1),
        abweichung_gesamt_kwh=round(abweichung_gesamt, 1),
        abweichung_gesamt_prozent=round(abweichung_gesamt_pct, 1) if abweichung_gesamt_pct is not None else None,
        strings=strings_data, saisonal_aggregiert=saisonal_aggregiert,
        bester_string=bester_string, schlechtester_string=schlechtester_string,
        ist_quelle=_rollup_quelle([s.ist_quelle for s in strings_data]),
        vergleich_hinweis=vergleich_hinweis,
    )
