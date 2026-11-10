"""
Protokollzeile der Reparatur-Werkbank (N-793, Päckchen GG 10.11.2026).

`repair_orchestrator.execute()` hält Plan und Ergebnis nur im Speicher (`_plans`/`_results`, Werkbank-Verlauf
`list_plans`) — nach einem Neustart (Add-on-Update, HA-Neustart) war nicht mehr nachweisbar, welche Reparatur ein
Anwender wann ausgeführt hat. Seitdem schreibt jeder ausgeführte Lauf hier **eine** Zeile ins Aktivitätsprotokoll
(Kategorie `repair`, Einstellungen → System → Protokolle «Reparatur»), auch die Knöpfe im Daten-Checker, die über
die Wrapper-Routen `api/routes/energie_profil/repair.py` laufen.

Die Zeile entsteht in der Sitzung des Aufrufers (`db=`, N-532): sie landet mit dessen Commit und verschwindet mit
dessen Rollback — ein Lauf, der wirft, hinterlässt keine Zeile. Eine `erfolg=False`-Zeile gibt es deshalb nicht
(benannte Grenze): in der Sitzung fiele sie mit dem Rollback weg, eine eigene Sitzung liefe in die SQLite-Sperre.

Eigenes Modul, weil `repair_orchestrator.py` an seiner Dateilängen-Grenze steht (`tests/test_dateilaenge.py`).
«Werte vor dem Sensorbeginn verwerfen» schreibt zusätzlich seine Detailzeile (`verwerfen_vor_quellbeginn.py`) —
für diese Operation stehen je Lauf zwei Zeilen; die Orchestrator-Zeile ist an `details_json["plan_id"]` erkennbar.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy.ext.asyncio import AsyncSession

from backend.services.activity_service import log_activity

if TYPE_CHECKING:
    from backend.services.repair_orchestrator import RepairPlan

#: Die Namen der Operationen wie in der Werkbank (`frontend/src/api/repair.ts::OPERATION_META`).
OPERATION_LABELS = {
    "reaggregate_day": "Tag neu aggregieren",
    "reaggregate_range": "Mehrere Tage neu aggregieren",
    "reaggregate_today": "Heutigen Tag neu aggregieren",
    "vollbackfill": "Lücken aus HA-LTS nachfüllen",
    "kraftstoffpreis_backfill": "Kraftstoffpreise nachpflegen",
    "wetter_backfill": "Wetterreihe nachziehen",
    "delete_monatsdaten": "Monatsdaten löschen",
    "reset_cloud_import": "Cloud-Import-Werte zurücksetzen",
    "verwerfen_vor_quellbeginn": "Werte vor dem Sensorbeginn verwerfen",
    # E3 Daten-Checker (`repair_operationen_checker.py`); Vitest-Spiegel `src/test/operation-labels.test.ts`.
    "temperatur_aus_messung": "Temperatur aus Messung übernehmen",
    "feldwert_entfernen": "Wert in nicht geführtem Feld entfernen",
    "geraetewerte_loeschen": "Messwerte ohne Monatszeile entfernen",
    "spiegel_abgleich_tag": "Aus Home Assistant neu übernehmen",
}


def _bereich(params: dict[str, Any]) -> str:
    """Datum oder «von – bis» aus den Parametern, sonst «—»."""
    if params.get("datum"):
        return str(params["datum"])
    if params.get("von") or params.get("bis"):
        return f"{params.get('von') or '…'} – {params.get('bis') or '…'}"
    return "—"


def _details(summary: dict[str, Any], actual: dict[str, int]) -> str:
    """Anwender-Satz der Operation (`quelle_text`; E3: `meldung` des Spiegel-Abgleichs), sonst die Zähler."""
    satz = summary.get("quelle_text") or summary.get("meldung")
    if isinstance(satz, str) and satz:
        return satz
    return "Änderungen: " + " · ".join(f"{k} {v}" for k, v in actual.items())


async def protokolliere_lauf(
    plan_obj: RepairPlan, summary: dict[str, Any], actual: dict[str, int], db: AsyncSession,
) -> None:
    """Eine Zeile `kategorie="repair"` je ausgeführtem Lauf, in der Sitzung des Aufrufers."""
    op = plan_obj.operation.value
    params = {
        k: v.isoformat() if isinstance(v, (date, datetime)) else v
        for k, v in plan_obj.operation_params.items()
    }
    await log_activity(
        kategorie="repair",
        aktion=f"Reparatur: {OPERATION_LABELS.get(op, op)} — {_bereich(params)}",
        erfolg=True,
        details=_details(summary, actual),
        details_json={
            "plan_id": str(plan_obj.plan_id),
            "operation": op,
            "params": params,
            "actual_changes": actual,
        },
        anlage_id=plan_obj.anlage_id,
        db=db,
    )
