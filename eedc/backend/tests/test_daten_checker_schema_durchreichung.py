"""
Schema-Durchreichungs-Test (v3.31.2 Hotfix-Beleg, E5 umgestellt):
Stellt sicher, dass alle Felder der internen `CheckErgebnis`-Dataclass
auch im Pydantic-Response-Modell `CheckErgebnisResponse` vorhanden sind.

Hintergrund: v3.31.1 hat die Felder `action_kind`/`action_params`/`action_label`
zur Dataclass hinzugefügt, aber im API-Response-Schema vergessen — Frontend
bekam dadurch leere Action-Felder, Reparatur-Knopf fiel auf den alten
'Beheben'-Link zurück. Seit E5 sind diese Altfelder entfallen (Wächter W-3); die
Aktion steht in `action`, der Knopf-Text aller Klassen in der Eigenschaft `knopf`.
"""

from __future__ import annotations

from dataclasses import fields

from backend.services.daten_checker import CheckErgebnis
from backend.api.routes.daten_checker import CheckErgebnisResponse


def test_alle_dataclass_felder_im_response_schema():
    """Jedes Feld von `CheckErgebnis` (und die abgeleitete Eigenschaft `knopf`) muss in `CheckErgebnisResponse`
    existieren — verhindert Schema-Drift zwischen Service-Dataclass und API-Response."""
    dataclass_felder = {f.name for f in fields(CheckErgebnis)} | {"knopf"}
    response_felder = set(CheckErgebnisResponse.model_fields.keys())

    fehlend = dataclass_felder - response_felder
    assert not fehlend, (
        f"Felder in CheckErgebnis aber NICHT in CheckErgebnisResponse: "
        f"{fehlend} — API filtert sie raus, Frontend bekommt sie nicht."
    )


def test_altfelder_sind_aus_der_antwort_entfernt():
    """W-3 nach E5: `link`/`action_*` stehen weder im Schema noch an der Dataclass."""
    for name in ("link", "action_kind", "action_params", "action_label"):
        assert name not in CheckErgebnisResponse.model_fields
        assert not hasattr(CheckErgebnis(kategorie="x", schwere="info", meldung="m"), name)


def test_response_schema_serialisiert_aktion_und_knopf():
    """Konkrete Smoke-Probe: Pydantic-Serialisierung mit gesetzter Aktion und Knopf."""
    resp = CheckErgebnisResponse(
        kategorie="datenquelle_drift",
        schwere="info",
        meldung="Test",
        action={"operation": "reaggregate_day", "params": {"datum": "2026-05-15"}, "label": "Tag neu aufbauen"},
        knopf="Tag neu aufbauen",
    )
    daten = resp.model_dump()
    assert daten["action"] == {"operation": "reaggregate_day", "params": {"datum": "2026-05-15"},
                               "label": "Tag neu aufbauen"}
    assert daten["knopf"] == "Tag neu aufbauen"
