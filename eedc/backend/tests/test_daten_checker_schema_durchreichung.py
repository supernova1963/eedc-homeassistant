"""
Schema-Durchreichungs-Test (v3.31.2 Hotfix-Beleg):
Stellt sicher, dass alle Felder der internen `CheckErgebnis`-Dataclass
auch im Pydantic-Response-Modell `CheckErgebnisResponse` vorhanden sind.

Hintergrund: v3.31.1 hat die Felder `action_kind`/`action_params`/`action_label`
zur Dataclass hinzugefügt, aber im API-Response-Schema vergessen — Frontend
bekam dadurch leere Action-Felder, Reparatur-Knopf fiel auf den alten
'Beheben'-Link zurück.

Self-contained:

    eedc/backend/venv/bin/python eedc/backend/tests/test_daten_checker_schema_durchreichung.py
"""

from __future__ import annotations

import sys
import traceback
from dataclasses import fields
from pathlib import Path

_BACKEND_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_BACKEND_ROOT))

from backend.services.daten_checker import CheckErgebnis  # noqa: E402
from backend.api.routes.daten_checker import CheckErgebnisResponse  # noqa: E402


def test_alle_dataclass_felder_im_response_schema():
    """Jedes Feld von `CheckErgebnis` muss in `CheckErgebnisResponse` exisitieren.

    Verhindert Wiederholung des v3.31.1-Bugs (Schema-Drift zwischen
    Service-Dataclass und API-Response).
    """
    dataclass_felder = {f.name for f in fields(CheckErgebnis)}
    response_felder = set(CheckErgebnisResponse.model_fields.keys())

    fehlend = dataclass_felder - response_felder
    assert not fehlend, (
        f"Felder in CheckErgebnis aber NICHT in CheckErgebnisResponse: "
        f"{fehlend} — API filtert sie raus, Frontend bekommt sie nicht."
    )


def test_response_schema_serialisiert_action_felder():
    """Konkrete Smoke-Probe: Pydantic-Serialisierung mit gesetzten Action-Feldern."""
    resp = CheckErgebnisResponse(
        kategorie="datenquelle_drift",
        schwere="info",
        meldung="Test",
        action_kind="reaggregate_day",
        action_params={"anlage_id": 1, "datum": "2026-05-15"},
        action_label="Tag reparieren",
    )
    daten = resp.model_dump()
    assert daten["action_kind"] == "reaggregate_day"
    assert daten["action_params"] == {"anlage_id": 1, "datum": "2026-05-15"}
    assert daten["action_label"] == "Tag reparieren"


_TESTS = [
    test_alle_dataclass_felder_im_response_schema,
    test_response_schema_serialisiert_action_felder,
]


def _run_all() -> int:
    failures = 0
    for test in _TESTS:
        try:
            test()
            print(f"OK   {test.__name__}")
        except AssertionError as e:
            failures += 1
            print(f"FAIL {test.__name__}\n     {e}")
        except Exception:
            failures += 1
            print(f"ERR  {test.__name__}")
            traceback.print_exc()
    return failures


if __name__ == "__main__":
    failures = _run_all()
    if failures:
        print(f"\n{failures} von {len(_TESTS)} Tests fehlgeschlagen.")
        sys.exit(1)
    print(f"\nAlle {len(_TESTS)} Tests grün.")
