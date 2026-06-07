"""
HTTP-Exception-Factory (Tier-4 Schuldenabbau, Plan: docs/drafts/PLAN-exception-factory.md).

Helper RETURNEN die `HTTPException` — der Aufrufer schreibt `raise not_found(...)`.
Begründung: `raise` bleibt am Call-Site sichtbar (Coverage/Linter/Type-Narrowing),
`raise not_found(...) from exc` ist in except-Blöcken komponierbar, und die
Byte-Identität ist trivial testbar
(`assert not_found("Anlage", 7).detail == "Anlage 7 nicht gefunden"`).

Präzedenzfall im eigenen Code: `api/routes/monatsabschluss/wizard.py`
(`_wizard_save_fehler(exc, kontext) -> HTTPException`) lebt das Return-Pattern
bereits.

NICHT für dynamisches Detail (`str(e)`, Upstream-`.get('detail')`), dynamischen
Status (Reverse-Proxy-Passthrough), Security-Wortlaut (SSRF/Access-Gate) oder
seltene Status-Einzelfälle (410/413/422/429/…) verwenden — Liste im Plan.
"""

from __future__ import annotations

from fastapi import HTTPException, status


def not_found(entity: str, id: int | str | None = None) -> HTTPException:
    """404 mit kanonischem Wortlaut.

    `id=None` → ``"<entity> nicht gefunden"``;
    `id` gesetzt → ``"<entity> {id} nicht gefunden"``.

    Diese Regel ist load-bearing für die Byte-Identität der migrierten Sites.
    """
    detail = f"{entity} {id} nicht gefunden" if id is not None else f"{entity} nicht gefunden"
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=detail)


def bad_request(detail: str) -> HTTPException:
    """400 mit statischem Literal-Detail."""
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=detail)


def ha_db_unavailable() -> HTTPException:
    """503 — HA-Datenbank nicht verfügbar (service.is_available-Guard, 5 Sites).

    Wortlaut byte-identisch zu den `ha_statistics.py`-Guards.
    """
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="HA-Datenbank nicht verfügbar. Diese Funktion ist nur im HA-Addon nutzbar.",
    )


def ha_supervisor_unavailable() -> HTTPException:
    """503 — kein HA-Supervisor-Token (supervisor_token-Guard, 2 Sites).

    Wortlaut byte-identisch zu `ha_integration.py`/`sensor_mapping.py`.
    """
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="Keine Verbindung zu Home Assistant (kein Supervisor Token)",
    )
