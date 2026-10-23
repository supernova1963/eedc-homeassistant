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

from dataclasses import dataclass
from datetime import date
from typing import Any, Iterable, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel

from backend.core.exceptions import not_found
from backend.core.berechnungen.erzeuger_traeger import (
    abgetretene_bkw_ids,
    erzeuger_traeger,
    selbst_tragende_bkw_ids,
    traeger_im_monat,
    soll_nenner_kwp,
    traeger_zeilen,
    verteilungsnenner_kwp,
)
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
from backend.core.berechnungen import soll_im_laufmonat
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

# N-653 (10.10.2026): der Mischfall — ein Teil der Module gemessen, der Rest
# verteilt. Der Satz oben („Die Werte je Modul sind nicht gemessen …")
# widerspricht dort den gemessenen Zeilen darüber. Die Regel bleibt (teilweise
# verteilt ⇒ kein Ranking, Entscheid 26.07.); nur der Satz sagt, was zutrifft.
RANKING_TEILWEISE_VERTEILT = (
    "Nicht alle Module haben gemessene Werte — ein Teil ist anteilig nach kWp "
    "aus der Gesamterzeugung verteilt. Ein Vergleich einzelner Strings ist "
    "damit nicht möglich. Dafür braucht jedes Modul einen eigenen "
    "Erzeugungs-Sensor (Einstellungen → Sensor-Zuordnung)."
)



# F-34: Das Monats-SOLL einer Zeile wird auf ihre Laufzeit im Anschaffungs-/
# Stilllegungsmonat gekürzt — `soll_im_laufmonat`, seit N-616 (04.10.2026) im
# Layer (`core/berechnungen/monatsfenster.py`), weil das Jahresbericht-PDF
# („String-Vergleich") dieselbe Regel braucht.


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


# N-613/N-614: Die Monatsform der Abtretung (welche BKW tragen in diesem Monat
# noch selbst, welche Menge trägt, welche Zeilen zeigt die Sicht, welcher
# kWp-Nenner) steht seit 03.10.2026 im Selektor-Modul
# `core/berechnungen/erzeuger_traeger.py` — das Jahresbericht-PDF
# („String-Vergleich") nutzt dieselben Funktionen, damit beide Sichten
# dieselben Zeilen und denselben Nenner haben.


def _ranking(
    kandidaten: list[tuple[str, Optional[float], str]],
) -> tuple[Optional[str], Optional[str], Optional[str]]:
    """Bester/schwächster String — nur bei durchgängig gemessenen IST-Werten.

    Args:
        kandidaten: ``[(bezeichnung, performance_ratio, ist_quelle), …]``.

    Returns:
        ``(bester, schlechtester, hinweis)``. Ist auch nur ein String nicht
        gemessen, bleibt die Platzierung leer und stattdessen steht der
        Erklärsatz {@link RANKING_NICHT_MOEGLICH} in ``hinweis`` — im Mischfall
        (mindestens ein String gemessen) {@link RANKING_TEILWEISE_VERTEILT} (N-653).
    """
    if len(kandidaten) <= 1:
        return None, None, None
    if any(quelle != PV_QUELLE_GEMESSEN for _, _, quelle in kandidaten):
        teilweise = any(quelle == PV_QUELLE_GEMESSEN for _, _, quelle in kandidaten)
        return None, None, RANKING_TEILWEISE_VERTEILT if teilweise else RANKING_NICHT_MOEGLICH
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


def _heute_aktive_kwp(alle: list, referenzwert: Optional[float], heute: Optional[date] = None) -> float:
    """Σ kWp der Träger, die HEUTE aktiv sind — die Anlagenleistung, mit der eine Prognose verglichen wird (N-684).

    Erst der Zeitfilter (``ist_aktiv_an``), dann der Selektor (``erzeuger_traeger``) — dieselbe Reihenfolge wie je
    Monat (N-613, ADR-002/P11). ⛔ Bis 11.10.2026 verglich die Warnung „Prognose passt nicht" gegen ``gesamt_kwp``, die
    Σ ALLER je vorhandenen Träger: nach einer Stilllegung (Ost 5 kWp still, Prognose richtig für 10 kWp) stand dort
    „die Anlage hat aktuell 15,0 kWp", und der Rat „neu abrufen" lieferte dieselbe Prognose. Ein Zubau ohne neuen
    Abruf warnt weiter zu Recht.
    """
    heute = heute or date.today()
    return verteilungsnenner_kwp(erzeuger_traeger([i for i in alle if i.ist_aktiv_an(heute)]), referenzwert)


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

    ``gesamt_kwp`` sind die HEUTE aktiven kWp (``_heute_aktive_kwp``, N-684) — der Text sagt „aktuell".

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
    # N-266: `erzeuger_traeger` — ein Balkonkraftwerk mit `pv-module`-Kindern
    # ist keine eigene String-Zeile mehr, seine Kinder sind es (genau der
    # Melder-Wunsch: zwei Ausrichtungen an einem BKW). Bliebe es drin, wäre es
    # eine Zeile zu viel UND der Verteilungsnenner `gesamt_kwp` doppelt, sodass
    # jeder String zu wenig SOLL bekäme.
    # ⛔ N-613: Das gilt je MONAT, nicht für die Anlage. Bis 03.10.2026 stand
    # der Selektor hier einmal über alle Investitionen — ein BKW, dem später
    # Module zugeordnet wurden, hatte damit in KEINEM Monat eine Zeile, und in
    # den Monaten davor fehlte seine Erzeugung in der Summe (gemessen: 930 gegen
    # 1860 kWh der Monats-Fakten). Jetzt: `struktur` ist die heutige Zuordnung
    # (Anlagen-Nenner, Plausibilität), die Monate entscheiden selbst
    # (`selbst_tragende_bkw_ids`), und die IST-Werte lädt `lade_pv_je_monat` mit
    # ALLEN Erzeugern — dort läuft der Selektor schon je Monat nach dem
    # Zeitfilter (ADR-002/P11).
    alle = list(result.scalars().all())
    struktur = erzeuger_traeger(alle)

    if not alle:
        return PVStringsResponse(
            anlage_id=anlage_id, jahr=jahr, hat_prognose=False,
            anlagen_leistung_kwp=anlage.leistung_kwp or 0,
            prognose_gesamt_kwh=0, ist_gesamt_kwh=0, abweichung_gesamt_kwh=0,
            abweichung_gesamt_prozent=None, strings=[],
            bester_string=None, schlechtester_string=None,
        )

    selbst_je_monat = {m: selbst_tragende_bkw_ids(alle, jahr, m) for m in range(1, 13)}
    pv_module = traeger_zeilen(alle, struktur, frozenset().union(*selbst_je_monat.values()))

    wechselrichter_map = await _wechselrichter_namen(db, pv_module)

    # Die AKTIVE Prognose (b2025e0e) über den Auswahl-SoT
    # `services/prognose_auswahl.py` — dort steht die Regel samt Begründung
    # (`ist_aktiv` ist Nutzerwille, „neueste" wäre stumme Übersteuerung).
    prognose = await lade_aktive_prognose(db, anlage_id)
    hat_prognose = prognose is not None

    prognose_monate, prognose_per_modul = _prognose_monatswerte(prognose)

    # Anlagen-Nenner der heutigen Zuordnung (`anlagen_leistung_kwp`; die Plausibilität
    # vergleicht seit N-684 gegen die HEUTE aktiven Träger, `_heute_aktive_kwp`).
    # ⭐ N-661 (Weg C, Gernot 11.10.2026): der SOLL-Nenner je String sind die kWp,
    # für die die aktive Prognose gerechnet ist — dieselbe Regel wie im
    # Jahresbericht-PDF (`soll_nenner_kwp`). Bis dahin stand hier die Σ ALLER
    # Träger: ein stillgelegter String drückte das SOLL der übrigen (gemessen
    # −33 %). Ohne Prognose-kWp gilt der frühere Nenner, je Monat der Menge,
    # die in diesem Monat trägt (N-613).
    gesamt_kwp = verteilungsnenner_kwp(struktur, anlage.leistung_kwp)
    nenner_je_monat = {
        m: soll_nenner_kwp(
            prognose,
            gesamt_kwp if not selbst
            else verteilungsnenner_kwp(traeger_im_monat(alle, struktur, selbst), anlage.leistung_kwp),
        )
        for m, selbst in selbst_je_monat.items()
    }

    # IST je Modul über den Read-time-SoT (A4/b1) statt roh aus den IMD — mit
    # ALLEN Erzeugern; die Abtretung entscheidet der Ladepfad je Monat (N-613).
    werte_je_modul, ist_quellen = await _lade_ist_je_modul(db, anlage_id, alle, jahr=jahr)
    md_by_inv: dict[int, dict[int, float]] = {
        m.id: werte_je_modul.get(m.id, {}).get(jahr, {}) for m in pv_module
    }

    strings_data = []
    prognose_gesamt = 0
    ist_gesamt = 0

    for modul in pv_module:
        modul_kwp = get_erzeuger_kwp(modul)
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
                    nenner = nenner_je_monat[monat]
                    kwp_anteil = modul_kwp / nenner if nenner > 0 else 0
                    prog_monat = prognose_monate.get(monat, 0) * kwp_anteil
                # F-34: im Anschaffungs-/Stilllegungsmonat lief das Modul nur
                # einen Teil des Monats — das SOLL wird darauf gekürzt.
                prog_monat = soll_im_laufmonat(prog_monat, modul, jahr, monat)
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
        prognose_warnung=_pruefe_prognose_plausibilitaet(prognose, _heute_aktive_kwp(alle, anlage.leistung_kwp)),
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
    # RF-31 (23.10.2026, Bauform RF-1): die Phasen stehen als Modulfunktionen unter der Route — `_laufzeit_mengen`
    # (Monats-Mengen, Nenner, aktive Träger), je String `_string_gesamtlaufzeit` mit `_string_jahreswert` und
    # `_string_saisonalwerte`, danach `_saisonal_aggregiert`; die mit der Jahressicht wortgleichen Teile stehen in
    # `_prognose_monatswerte` und `_wechselrichter_namen`. Reihenfolge der Abfragen und Antwortform unverändert.
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
    # N-266: `erzeuger_traeger` — ein Balkonkraftwerk mit `pv-module`-Kindern
    # ist keine eigene String-Zeile mehr, seine Kinder sind es (genau der
    # Melder-Wunsch: zwei Ausrichtungen an einem BKW). Bliebe es drin, wäre es
    # eine Zeile zu viel UND der Verteilungsnenner `gesamt_kwp` doppelt, sodass
    # jeder String zu wenig SOLL bekäme.
    # ⛔ N-613: je Monat, nicht für die Anlage — siehe `get_pv_strings`.
    alle = list(result.scalars().all())
    struktur = erzeuger_traeger(alle)

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
    if not alle:
        return _empty

    # Dieselbe Auswahlregel wie in der Jahressicht darüber — beide über den
    # Auswahl-SoT, damit zwei Sichten derselben Anlage nicht auf
    # verschiedenen Prognosen stehen können.
    prognose = await lade_aktive_prognose(db, anlage_id)
    hat_prognose = prognose is not None

    prognose_monate, prognose_per_modul = _prognose_monatswerte(prognose)

    gesamt_kwp = verteilungsnenner_kwp(struktur, anlage.leistung_kwp)

    # IST je Modul über den Read-time-SoT (A4/b1) statt roh aus den IMD: die
    # Laufzeit-Jahre entstehen jetzt aus allen Monaten MIT PV-Quelle — also auch
    # aus reinen Aggregat-Monaten, die vorher zu einer leeren Antwort führten.
    # Mit ALLEN Erzeugern: die Abtretung entscheidet der Ladepfad je Monat (N-613).
    md_by_inv, ist_quellen = await _lade_ist_je_modul(db, anlage_id, alle)

    jahre = sorted({j for (_, j, _) in ist_quellen})
    if not jahre:
        return _empty

    pv_module, nenner_je_monat, aktiv_im_monat = _laufzeit_mengen(
        alle, struktur, jahre, prognose, gesamt_kwp, anlage.leistung_kwp,
    )
    # Anlagen-SOLL des typischen Monats: je Jahr Σ der in (Jahr, Monat) aktiven
    # Träger, dann über die Jahre gemittelt.
    sammler = _SaisonalSammler(
        saisonal_soll_je_jahr={m: {} for m in range(1, 13)},
        saisonal_agg={m: {"ist_summe": 0, "anzahl": 0} for m in range(1, 13)},
        saisonal_jahre={m: {} for m in range(1, 13)},
    )
    # Eine „Familie" für die Jahreszahl des saisonalen Mittels: ein abtretendes
    # BKW und seine Kinder sind EIN Erzeuger, der den Träger gewechselt hat —
    # die Jahre der BKW-Zeile und die der Kinder-Zeilen zählen zusammen, sonst
    # teilte das Mittel zwei Jahre Erzeugung durch eins.
    abgetreten = abgetretene_bkw_ids(alle)

    wechselrichter_map = await _wechselrichter_namen(db, pv_module)

    erstes_jahr = jahre[0]
    letztes_jahr = jahre[-1]
    anzahl_jahre = len(jahre)
    # Distinct (Jahr, Monat) — die Schlüssel tragen seit der modulweisen
    # Provenance zusätzlich die Investitions-ID und würden sonst je Modul zählen.
    anzahl_monate = len({(j, m) for (_, j, m) in ist_quellen})

    ctx = _LaufzeitKontext(
        jahre=jahre, md_by_inv=md_by_inv, ist_quellen=ist_quellen, prognose_monate=prognose_monate,
        prognose_per_modul=prognose_per_modul, nenner_je_monat=nenner_je_monat, aktiv_im_monat=aktiv_im_monat,
        abgetreten=abgetreten, wechselrichter_map=wechselrichter_map,
    )
    strings_data = []
    prognose_gesamt_total = 0
    ist_gesamt_total = 0

    for modul in pv_module:
        string_daten, prognose_string_gesamt, ist_string_gesamt = _string_gesamtlaufzeit(ctx, sammler, modul)
        strings_data.append(string_daten)
        prognose_gesamt_total += prognose_string_gesamt
        ist_gesamt_total += ist_string_gesamt

    saisonal_aggregiert = _saisonal_aggregiert(sammler)

    abweichung_gesamt = ist_gesamt_total - prognose_gesamt_total
    abweichung_gesamt_pct = (abweichung_gesamt / prognose_gesamt_total * 100) if prognose_gesamt_total > 0 else None
    bester_string, schlechtester_string, vergleich_hinweis = _ranking(
        [(s.bezeichnung, s.performance_ratio_gesamt, s.ist_quelle) for s in strings_data]
    )

    return PVStringsGesamtlaufzeitResponse(
        anlage_id=anlage_id, hat_prognose=hat_prognose,
        prognose_warnung=_pruefe_prognose_plausibilitaet(prognose, _heute_aktive_kwp(alle, anlage.leistung_kwp)),
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


@dataclass(frozen=True)
class _LaufzeitKontext:
    """Die geteilten, nur gelesenen Eingänge der Gesamtlaufzeit je String (RF-31)."""
    jahre: list[int]
    md_by_inv: dict
    ist_quellen: dict
    prognose_monate: dict
    prognose_per_modul: dict
    nenner_je_monat: dict
    aktiv_im_monat: dict
    abgetreten: Any
    wechselrichter_map: dict


@dataclass
class _SaisonalSammler:
    """Die über alle Strings laufenden Saisonal-Akkumulatoren (RF-31) — von den String-Phasen fortgeschrieben."""
    saisonal_soll_je_jahr: dict[int, dict[int, float]]
    saisonal_agg: dict[int, dict]
    saisonal_jahre: dict[int, dict[Any, set]]


def _prognose_monatswerte(prognose) -> tuple[dict, dict[int, dict[int, float]]]:
    """PVGIS-Monatswerte der Anlage und je Modul aus der aktiven Prognose (RF-31: in beiden Sichten wortgleich).

    Rückgabe ``(prognose_monate, prognose_per_modul)``.
    """
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
    return prognose_monate, prognose_per_modul


async def _wechselrichter_namen(db: AsyncSession, pv_module: list) -> dict:
    """Bezeichnung der Wechselrichter der Zeilen, ``{wr_id: bezeichnung}`` (RF-31: in beiden Sichten wortgleich)."""
    wr_ids = [m.parent_investition_id for m in pv_module if m.parent_investition_id]
    wechselrichter_map = {}
    if wr_ids:
        result = await db.execute(select(Investition).where(Investition.id.in_(wr_ids)))
        for wr in result.scalars().all():
            wechselrichter_map[wr.id] = wr.bezeichnung
    return wechselrichter_map


def _laufzeit_mengen(alle, struktur, jahre, prognose, gesamt_kwp, leistung_kwp) -> tuple[list, dict, dict]:
    """Zeilen, SOLL-Nenner und aktive Träger je (Jahr, Monat) der Gesamtlaufzeit (RF-31, aus der Route).

    Rückgabe ``(pv_module, nenner_je_monat, aktiv_im_monat)``.
    """
    # N-613: Zeilen und Monats-Nenner aus derselben Menge wie die IST-Werte.
    selbst_je_monat = {
        (j, m): selbst_tragende_bkw_ids(alle, j, m) for j in jahre for m in range(1, 13)
    }
    pv_module = traeger_zeilen(alle, struktur, frozenset().union(*selbst_je_monat.values()))
    # N-661 (Weg C): je Monat die kWp der aktiven Prognose — wie die Jahressicht
    # darüber und das PDF; ohne Prognose-kWp der frühere Nenner (N-613).
    nenner_je_monat = {
        jm: soll_nenner_kwp(
            prognose,
            gesamt_kwp if not selbst
            else verteilungsnenner_kwp(traeger_im_monat(alle, struktur, selbst), leistung_kwp),
        )
        for jm, selbst in selbst_je_monat.items()
    }
    # N-683 (Fachentscheid Master, 11.10.2026): das saisonale Mittel zählt je Monat
    # nur die Träger, die in DIESEM Monat tragen und aktiv sind (Anschaffung,
    # Stilllegung, `aktiv`) — dieselbe Menge, über die die Jahreswerte darüber ihr
    # SOLL bilden (`nenner_je_monat`, N-661 Weg C).
    aktiv_im_monat = {
        jm: frozenset(i.id for i in traeger_im_monat(alle, struktur, selbst) if i.ist_aktiv_im_monat(*jm))
        for jm, selbst in selbst_je_monat.items()
    }
    return pv_module, nenner_je_monat, aktiv_im_monat


def _familie(inv: Any, abgetreten) -> Any:
    if inv.typ == "pv-module" and inv.parent_investition_id in abgetreten:
        return inv.parent_investition_id
    return inv.id


def _string_gesamtlaufzeit(ctx: _LaufzeitKontext, sammler: _SaisonalSammler, modul):
    """Die Gesamtlaufzeit-Zeile EINES Strings (RF-31: der Schleifenkörper der Route).

    Rückgabe ``(PVStringGesamtlaufzeit, prognose_string_gesamt, ist_string_gesamt)``; schreibt ``sammler`` fort.
    """
    modul_kwp = get_erzeuger_kwp(modul)
    params = modul.parameter or {}
    ausrichtung = modul.ausrichtung or params.get("ausrichtung")
    neigung = modul.neigung_grad or params.get("neigung_grad")
    jahreswerte = []
    prognose_string_gesamt = 0
    ist_string_gesamt = 0
    string_saisonal: dict[int, dict] = {m: {"ist_summe": 0, "anzahl": 0} for m in range(1, 13)}
    modul_prognose = ctx.prognose_per_modul.get(modul.id)
    modul_quellen: list[str] = []

    for jahr in ctx.jahre:
        jahreswert, prognose_jahr, ist_jahr = _string_jahreswert(
            ctx, sammler, modul, modul_kwp, modul_prognose, jahr, string_saisonal,
        )
        jahreswerte.append(jahreswert)
        # Jahre ohne PV-Quelle zählen für den Modul-Rollup nicht mit (sonst
        # zöge ein leeres Jahr die Herkunft der Laufzeit auf „fehlt").
        if jahreswert.ist_quelle != PV_QUELLE_FEHLT:
            modul_quellen.append(jahreswert.ist_quelle)
        prognose_string_gesamt += prognose_jahr
        ist_string_gesamt += ist_jahr

    saisonalwerte = _string_saisonalwerte(ctx, sammler, modul, modul_kwp, modul_prognose, string_saisonal)

    abweichung_gesamt_pct = ((ist_string_gesamt - prognose_string_gesamt) / prognose_string_gesamt * 100) if prognose_string_gesamt > 0 else None
    perf_ratio_gesamt = (ist_string_gesamt / prognose_string_gesamt) if prognose_string_gesamt > 0 else None
    spez_ertrag = (ist_string_gesamt / modul_kwp) if modul_kwp > 0 else None
    return PVStringGesamtlaufzeit(
        investition_id=modul.id, bezeichnung=modul.bezeichnung,
        leistung_kwp=modul_kwp, ausrichtung=ausrichtung, neigung_grad=neigung,
        wechselrichter_name=ctx.wechselrichter_map.get(modul.parent_investition_id) if modul.parent_investition_id else None,
        prognose_gesamt_kwh=round(prognose_string_gesamt, 1),
        ist_gesamt_kwh=round(ist_string_gesamt, 1),
        abweichung_gesamt_prozent=round(abweichung_gesamt_pct, 1) if abweichung_gesamt_pct is not None else None,
        performance_ratio_gesamt=round(perf_ratio_gesamt, 3) if perf_ratio_gesamt is not None else None,
        spezifischer_ertrag_kwh_kwp=round(spez_ertrag, 0) if spez_ertrag is not None else None,
        ist_quelle=_rollup_quelle(modul_quellen),
        jahreswerte=jahreswerte, saisonalwerte=saisonalwerte,
    ), prognose_string_gesamt, ist_string_gesamt


def _string_jahreswert(ctx: _LaufzeitKontext, sammler: _SaisonalSammler, modul, modul_kwp, modul_prognose, jahr,
                       string_saisonal: dict[int, dict]):
    """Ein Jahr eines Strings: SOLL, IST, Herkunft und die Saisonal-Zählung (RF-31).

    Rückgabe ``(PVStringJahreswert, prognose_jahr, ist_jahr)``; schreibt ``string_saisonal`` und
    ``sammler.saisonal_jahre`` fort.
    """
    md_by_inv, ist_quellen, nenner_je_monat = ctx.md_by_inv, ctx.ist_quellen, ctx.nenner_je_monat
    months_with_data_year = set(md_by_inv.get(modul.id, {}).get(jahr, {}).keys())
    # F-34: jeder Monat einzeln auf die Laufzeit des Moduls gekürzt,
    # dann summiert — sonst trüge das Anschaffungsjahr denselben
    # schiefen Vergleich wie die Monatssicht.
    if modul_prognose is not None:
        prognose_jahr = sum(
            soll_im_laufmonat(modul_prognose.get(m, 0), modul, jahr, m)
            for m in months_with_data_year
        )
    else:
        # N-613: je Monat der Nenner der Menge, die in diesem Monat trägt.
        prognose_jahr = sum(
            soll_im_laufmonat(
                ctx.prognose_monate.get(m, 0) * (
                    modul_kwp / nenner_je_monat[(jahr, m)]
                    if nenner_je_monat[(jahr, m)] > 0 else 0
                ),
                modul, jahr, m,
            )
            for m in months_with_data_year
        )
    ist_jahr = sum(md_by_inv.get(modul.id, {}).get(jahr, {}).get(m, 0) for m in range(1, 13))
    abweichung_pct = ((ist_jahr - prognose_jahr) / prognose_jahr * 100) if prognose_jahr > 0 else None
    perf_ratio = (ist_jahr / prognose_jahr) if prognose_jahr > 0 else None
    jahr_quelle = _rollup_quelle(
        ist_quellen[(modul.id, jahr, m)]
        for m in sorted(months_with_data_year) if (modul.id, jahr, m) in ist_quellen
    )
    jahreswert = PVStringJahreswert(
        jahr=jahr, prognose_kwh=round(prognose_jahr, 1), ist_kwh=round(ist_jahr, 1),
        abweichung_prozent=round(abweichung_pct, 1) if abweichung_pct is not None else None,
        performance_ratio=round(perf_ratio, 3) if perf_ratio is not None else None,
        ist_quelle=jahr_quelle,
    )
    for monat in range(1, 13):
        ist_monat = md_by_inv.get(modul.id, {}).get(jahr, {}).get(monat, 0)
        if ist_monat > 0 or monat in md_by_inv.get(modul.id, {}).get(jahr, {}):
            string_saisonal[monat]["ist_summe"] += ist_monat
            string_saisonal[monat]["anzahl"] += 1
            sammler.saisonal_jahre[monat].setdefault(_familie(modul, ctx.abgetreten), set()).add(jahr)
    return jahreswert, prognose_jahr, ist_jahr


def _string_saisonalwerte(ctx: _LaufzeitKontext, sammler: _SaisonalSammler, modul, modul_kwp, modul_prognose,
                          string_saisonal: dict[int, dict]) -> list[PVStringSaisonalwert]:
    """Die zwölf Saisonal-Zeilen eines Strings (RF-31); schreibt ``sammler.saisonal_soll_je_jahr``/``saisonal_agg`` fort."""
    nenner_je_monat = ctx.nenner_je_monat
    saisonalwerte = []
    for monat in range(1, 13):
        # F-34 gilt hier BEWUSST NICHT: die saisonale Zeile stellt einen
        # IST-Durchschnitt über mehrere Jahre einem Klimamittel gegenüber
        # und fragt „wie fällt der Mai typischerweise aus". Ein einzelner
        # angebrochener Anschaffungsmonat darf dieses Mittel nicht kürzen —
        # er verzerrt bereits den IST-Durchschnitt (`anzahl` zählt ihn voll
        # mit), und beide Seiten zu kürzen hieße, ihn doppelt zu bestrafen.
        #
        # ⭐ N-683 (Fachentscheid Master, 11.10.2026): das Saisonal-SOLL („wie fällt
        # der Mai typischerweise aus") ist das Mittel des Monats-SOLL über die
        # Jahre, in denen der String in diesem Monat aktiv war — mit demselben
        # Nenner wie seine Jahreswerte (`nenner_je_monat`). ⛔ Bis dahin stand
        # hier `PVGIS × kWp / gesamt_kwp`, die Σ ALLER je vorhandenen Träger:
        # nach einer Stilllegung (Ost 5 kWp still, Prognose für 10 kWp) bekam
        # Süd im Juni 282,7 statt 424,0 kWh, während seine Jahreswerte in
        # derselben Sicht stimmten. Ein String ohne aktiven Monat hat kein
        # Saisonal-SOLL (0, wie sein IST-Mittel).
        soll_je_jahr = {
            j: (
                modul_prognose.get(monat, 0) if modul_prognose is not None
                else ctx.prognose_monate.get(monat, 0) * (
                    modul_kwp / nenner_je_monat[(j, monat)] if nenner_je_monat[(j, monat)] > 0 else 0
                )
            )
            for j in ctx.jahre if modul.id in ctx.aktiv_im_monat[(j, monat)]
        }
        prognose_monat = sum(soll_je_jahr.values()) / len(soll_je_jahr) if soll_je_jahr else 0.0
        for j, wert in soll_je_jahr.items():
            sammler.saisonal_soll_je_jahr[monat][j] = sammler.saisonal_soll_je_jahr[monat].get(j, 0.0) + wert
        ist_summe = string_saisonal[monat]["ist_summe"]
        anzahl = string_saisonal[monat]["anzahl"]
        ist_durchschnitt = ist_summe / anzahl if anzahl > 0 else 0
        saisonalwerte.append(PVStringSaisonalwert(
            monat=monat, monat_name=MONATSNAMEN[monat],
            prognose_kwh=round(prognose_monat, 1),
            ist_durchschnitt_kwh=round(ist_durchschnitt, 1),
            ist_summe_kwh=round(ist_summe, 1), anzahl_jahre=anzahl,
        ))
        # Das Anlagen-SOLL des typischen Monats steht in `saisonal_soll_je_jahr`
        # (N-683): je Jahr die in diesem Monat aktiven Träger — ein BKW zählt in
        # den Monaten, in denen es selbst trägt, seine Kinder in den übrigen
        # (`traeger_im_monat`), nie beide zugleich.
        sammler.saisonal_agg[monat]["ist_summe"] += ist_summe
    return saisonalwerte


def _saisonal_aggregiert(sammler: _SaisonalSammler) -> list[PVStringSaisonalwert]:
    """Die Anlagen-Saisonal-Zeilen über alle Strings (RF-31, aus der Route)."""
    saisonal_aggregiert = []
    for monat in range(1, 13):
        # N-683: Mittel über die Jahre der Σ der im jeweiligen Monat aktiven Träger —
        # nach einer Stilllegung nicht mehr der volle PVGIS-Monat samt stillgelegtem String.
        soll_jahre = sammler.saisonal_soll_je_jahr[monat]
        prognose_s = sum(soll_jahre.values()) / len(soll_jahre) if soll_jahre else 0.0
        ist_summe = sammler.saisonal_agg[monat]["ist_summe"]
        # Jahre je Erzeuger-Familie, davon das Maximum — ohne abtretendes BKW ist
        # jede Familie eine Zeile und die Zahl dieselbe wie bisher (max der Zeilen).
        anzahl = max((len(j) for j in sammler.saisonal_jahre[monat].values()), default=0)
        ist_durchschnitt = ist_summe / anzahl if anzahl > 0 else 0
        saisonal_aggregiert.append(PVStringSaisonalwert(
            monat=monat, monat_name=MONATSNAMEN[monat],
            prognose_kwh=round(prognose_s, 1),
            ist_durchschnitt_kwh=round(ist_durchschnitt, 1),
            ist_summe_kwh=round(ist_summe, 1), anzahl_jahre=anzahl,
        ))
    return saisonal_aggregiert
