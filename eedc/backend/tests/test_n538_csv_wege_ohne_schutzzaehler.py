"""N-538 — die beiden CSV-Wege fuehren keinen Schutz-Zaehler, weil sie nie einen brauchten.

`import_export/csv_operations.py::import_csv` (Backup-Restore, `manual:csv_backup`) und
`custom_import/apply.py::apply_custom_import` (CSV-Wizard, `manual:csv_import`) trugen bis
20.09.2026 denselben Zaehler wie der Portal-Import (`data_import.py`): `geschuetzt_count`,
`geschuetzte_felder`, den Wizard-Hinweis „X Felder wurden durch manuell gepflegte Werte
geschuetzt" und zwei `_record_upsert`-Sammler. Gemessen (20.09.2026, Master-Session):

* Ohne Haken ueberspringen beide Wege einen bestehenden Monat, BEVOR sie schreiben.
* Mit Haken schreiben sie mit einer `manual:*`-Quelle — und eine manuelle Quelle wird seit
  #251 (`f0b45bcc`, 16.05.2026) NIE abgewiesen (`provenance._decide`: „manual override —
  user-driven write always applied"). Der Zaehler kam am 09.05. (`99f4ee80`) und war damit
  sieben Tage lang theoretisch scharf (gegen `repair`), seither tot.

Diese Datei haelt den Grund fest, nicht die Abwesenheit: Probe 1 schreibt mit beiden
CSV-Quellen gegen eine `repair`-Provenance (die einzige Stufe ueber MANUAL) und erwartet
`applied` — genau der Fall, in dem der Zaehler haette zaehlen muessen. Wer die Regel aus
#251 kippt, sieht sie rot und weiss, dass die CSV-Wege dann wieder einen Zaehler brauchen.
Probe 2 haelt fest, dass die beiden Antworten das Feld nicht mehr fuehren (Regression).
"""
from __future__ import annotations

import pytest

from backend.api.routes.custom_import.apply import ApplyResponse
from backend.api.routes.import_export.schemas import ImportResult
from backend.models.anlage import Anlage
from backend.models.monatsdaten import Monatsdaten
from backend.services.provenance import write_with_provenance

CSV_QUELLEN = [
    ("manual:csv_backup", "csv_backup_restore"),
    ("manual:csv_import", "csv_wizard"),
]


async def _monatszeile_mit_repair_provenance(db) -> Monatsdaten:
    anlage = Anlage(anlagenname="N-538", leistung_kwp=10.0, standort_land="DE")
    db.add(anlage)
    await db.flush()
    md = Monatsdaten(
        anlage_id=anlage.id, jahr=2026, monat=5,
        einspeisung_kwh=0.0, netzbezug_kwh=0.0, source_provenance={},
    )
    db.add(md)
    await db.flush()
    res = await write_with_provenance(
        db, md, "einspeisung_kwh", 500.0,
        source="manual:form", writer="reparatur", force_override=True,
    )
    assert res.decision == "applied"
    assert md.source_provenance["einspeisung_kwh"]["source"] == "repair"
    return md


@pytest.mark.parametrize("source,writer", CSV_QUELLEN)
async def test_manuelle_csv_quelle_schreibt_auch_gegen_repair(db, source, writer):
    """Die hoechste Stufe der Hierarchie (`repair`) weist eine CSV-Quelle nicht ab —
    deshalb konnte `rejected_lower_priority` auf den CSV-Wegen nie eintreten."""
    md = await _monatszeile_mit_repair_provenance(db)

    res = await write_with_provenance(
        db, md, "einspeisung_kwh", 123.0, source=source, writer=writer,
    )

    assert res.decision == "applied", res.decision_reason
    assert md.einspeisung_kwh == 123.0
    assert md.source_provenance["einspeisung_kwh"]["source"] == source


def test_csv_antworten_fuehren_keinen_schutzzaehler():
    """Regression: die beiden Antwort-Schemas tragen die toten Felder nicht mehr;
    der Portal-Import (`data_import.ApplyResponse`) behaelt seine."""
    from backend.api.routes.data_import import ApplyResponse as PortalApplyResponse

    for schema in (ImportResult, ApplyResponse):
        assert "geschuetzt_count" not in schema.model_fields, schema.__name__
        assert "geschuetzte_felder" not in schema.model_fields, schema.__name__
    assert "geschuetzt_count" in PortalApplyResponse.model_fields
