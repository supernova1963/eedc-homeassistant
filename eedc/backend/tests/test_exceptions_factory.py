"""Test-Harness für die HTTP-Exception-Factory (`core/exceptions.py`).

Tier-4 Schuldenabbau, Plan: `docs/drafts/PLAN-exception-factory.md`.

Zwei Ebenen:
1. **Helper-Tupel** — `(status_code, detail)` jeder Factory-Funktion exakt
   festnageln. Die kanonische Wortlaut-Regel von `not_found` (id=None vs.
   id gesetzt) ist load-bearing für die Byte-Identität aller migrierten
   Sites; jede Drift fällt hier durch.
2. **Pilot-Route** (`anlagen.py`) — die migrierten 404-Sites werfen über
   den Helper, mit dem auf `"Anlage {id} nicht gefunden"` normalisierten
   Wortlaut (Slice 1, bewusste Wording-Änderung weg von „Anlage mit ID …").
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi import HTTPException

_BACKEND_ROOT = Path(__file__).resolve().parents[2]  # eedc/
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

from backend.api.routes import anlagen  # noqa: E402
from backend.core.exceptions import (  # noqa: E402
    bad_request,
    ha_db_unavailable,
    ha_supervisor_unavailable,
    not_found,
)


# ---------------------------------------------------------------------------
# Helper-Tupel: (status_code, detail) byte-genau festnageln
# ---------------------------------------------------------------------------

def test_not_found_mit_id() -> None:
    exc = not_found("Anlage", 7)
    assert isinstance(exc, HTTPException)
    assert exc.status_code == 404
    assert exc.detail == "Anlage 7 nicht gefunden"
    assert exc.headers is None  # zero headers= im ganzen api/routes/


def test_not_found_mit_string_id() -> None:
    # id kann auch ein String sein (z. B. Datei-/Mapping-Schlüssel).
    assert not_found("Region", "DE-BY").detail == "Region DE-BY nicht gefunden"


def test_not_found_ohne_id() -> None:
    exc = not_found("Anlage")
    assert exc.status_code == 404
    assert exc.detail == "Anlage nicht gefunden"


def test_not_found_id_null_explizit() -> None:
    # id=None muss exakt wie der ohne-id-Fall greifen (kein "None" im Body).
    assert not_found("Anlage", None).detail == "Anlage nicht gefunden"


def test_not_found_id_null_kein_false_negative() -> None:
    # 0 ist eine gültige ID und darf nicht als „kein id" durchrutschen.
    assert not_found("Eintrag", 0).detail == "Eintrag 0 nicht gefunden"


def test_bad_request() -> None:
    exc = bad_request("Nur Bilder erlaubt (JPEG, PNG, HEIC).")
    assert exc.status_code == 400
    assert exc.detail == "Nur Bilder erlaubt (JPEG, PNG, HEIC)."


def test_ha_db_unavailable() -> None:
    exc = ha_db_unavailable()
    assert exc.status_code == 503
    assert exc.detail == "HA-Datenbank nicht verfügbar. Diese Funktion ist nur im HA-Addon nutzbar."


def test_ha_supervisor_unavailable() -> None:
    exc = ha_supervisor_unavailable()
    assert exc.status_code == 503
    assert exc.detail == "Keine Verbindung zu Home Assistant (kein Supervisor Token)"


# ---------------------------------------------------------------------------
# Pilot-Route: anlagen.py wirft über den Helper (Slice 1)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_anlage_404_normalisiert(db) -> None:
    with pytest.raises(HTTPException) as ei:
        await anlagen.get_anlage(anlage_id=999, db=db)
    assert ei.value.status_code == 404
    assert ei.value.detail == "Anlage 999 nicht gefunden"


@pytest.mark.asyncio
async def test_update_anlage_404_normalisiert(db) -> None:
    from backend.api.routes.anlagen import AnlageUpdate

    with pytest.raises(HTTPException) as ei:
        await anlagen.update_anlage(anlage_id=999, data=AnlageUpdate(), db=db)
    assert ei.value.status_code == 404
    assert ei.value.detail == "Anlage 999 nicht gefunden"


@pytest.mark.asyncio
async def test_delete_anlage_404_normalisiert(db) -> None:
    with pytest.raises(HTTPException) as ei:
        await anlagen.delete_anlage(anlage_id=999, db=db)
    assert ei.value.status_code == 404
    assert ei.value.detail == "Anlage 999 nicht gefunden"


@pytest.mark.asyncio
async def test_get_sensor_config_404_normalisiert(db) -> None:
    with pytest.raises(HTTPException) as ei:
        await anlagen.get_sensor_config(anlage_id=999, db=db)
    assert ei.value.status_code == 404
    assert ei.value.detail == "Anlage 999 nicht gefunden"
