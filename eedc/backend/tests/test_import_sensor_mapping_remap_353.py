"""JSON-Import: die Komponenten-Sensorzuordnung überlebt den Import (#353).

Bis Export-Version 1.2 verwarf der Import `sensor_mapping["investitionen"]`
komplett (`imported_sensor_mapping["investitionen"] = {}`), weil die
Investitions-IDs beim Import neu vergeben werden und die Datei die Quell-IDs
nicht trug. Für den Melder sah das wie Datenverlust aus: der Reimport der
korrigierten Datei löschte eine vorher funktionierende Speicher-Zuordnung mit.

Mit Export-Version 1.3 trägt jede Investition ihre Quell-`id`, und der Import
schreibt beide ID-tragenden Stellen um — `investitionen` UND die
`quellen`-Feld-IDs der Datenquellen-Fläche.

Der Round-Trip-Test unten ist die eigentliche Regression: er misst die Kette
Export → Import am echten Code, nicht die Remap-Funktion gegen sich selbst.
"""

from __future__ import annotations

import io
import json
from datetime import date

import pytest
from fastapi import UploadFile
from sqlalchemy import select

from backend.api.routes.import_export.json_operations import (
    _export_anlage_full_impl,
    import_json,
)
from backend.api.routes.import_export.sensor_mapping_remap import (
    remap_investitionen_ids,
)
from backend.models import Anlage, Investition


# ---------------------------------------------------------------- Remap pur

def test_remap_schreibt_investitionen_und_quellen_um():
    mapping = {
        "basis": {"einspeisung": {"strategie": "sensor", "sensor_id": "sensor.e"}},
        "investitionen": {
            "7": {"felder": {"pv_erzeugung_kwh": {"strategie": "sensor", "sensor_id": "sensor.pv"}}},
        },
        "quellen": {
            "basis_energy_einspeisung_kwh": {"quelle": "ha_app", "entity_id": "sensor.e"},
            "inv_energy_7_pv_erzeugung_kwh": {"quelle": "ha_app", "entity_id": "sensor.pv"},
            "inv_live_7_leistung_w": {"quelle": "ha_app", "entity_id": "sensor.pv_w"},
        },
    }

    bericht = remap_investitionen_ids(mapping, {7: 42})

    assert bericht.uebernommen == 1
    assert bericht.verworfen == []
    # Komponenten-Zuordnung hängt jetzt an der neuen ID …
    assert "42" in mapping["investitionen"]
    assert "7" not in mapping["investitionen"]
    assert (
        mapping["investitionen"]["42"]["felder"]["pv_erzeugung_kwh"]["sensor_id"]
        == "sensor.pv"
    )
    # … und die Feld-IDs der Fläche ebenso.
    assert "inv_energy_42_pv_erzeugung_kwh" in mapping["quellen"]
    assert "inv_live_42_leistung_w" in mapping["quellen"]
    assert "inv_energy_7_pv_erzeugung_kwh" not in mapping["quellen"]
    # Basis-Felder tragen keine ID und bleiben unangetastet.
    assert mapping["basis"]["einspeisung"]["sensor_id"] == "sensor.e"
    assert mapping["quellen"]["basis_energy_einspeisung_kwh"]["entity_id"] == "sensor.e"


def test_remap_verwirft_was_sich_nicht_aufloesen_laesst():
    """Nicht mit importierte Komponente ⇒ raus, nicht als Phantom stehenlassen.

    Ein Eintrag unter einer ID, die es nicht gibt, ist für die Aufzähl-Leser tote
    Last — und die v4.0.3-Start-Migration würde ihn aus `quellen` sogar nach
    `investitionen` materialisieren.
    """
    mapping = {
        "investitionen": {"7": {"felder": {}}, "9": {"felder": {}}},
        "quellen": {"inv_energy_9_ladung_kwh": {"quelle": "ha_app", "entity_id": "sensor.x"}},
    }

    bericht = remap_investitionen_ids(mapping, {7: 42})

    assert bericht.uebernommen == 1
    assert bericht.hat_verworfen
    assert mapping["investitionen"] == {"42": {"felder": {}}}
    assert mapping["quellen"] == {}


def test_remap_ohne_quell_ids_verwirft_nur_die_komponenten():
    """Alt-Datei (Export < 1.3): leere Map ⇒ Komponenten raus, Basis bleibt."""
    mapping = {
        "basis": {"netzbezug": {"strategie": "sensor", "sensor_id": "sensor.n"}},
        "investitionen": {"3": {"felder": {}}},
        "quellen": {"basis_live_pv_gesamt_w": {"quelle": "ha_app", "entity_id": "sensor.w"}},
    }

    bericht = remap_investitionen_ids(mapping, {})

    assert bericht.uebernommen == 0
    assert bericht.verworfen == ["Komponente #3"]
    assert mapping["investitionen"] == {}
    assert mapping["basis"]["netzbezug"]["sensor_id"] == "sensor.n"
    assert "basis_live_pv_gesamt_w" in mapping["quellen"]


def test_remap_vertraegt_fehlende_teilbaeume():
    bericht = remap_investitionen_ids({}, {7: 42})
    assert bericht.uebernommen == 0
    assert bericht.verworfen == []


# ------------------------------------------------------- Round-Trip am Code

async def _anlage_mit_zuordnung(db) -> tuple[int, int]:
    """Anlage + eine Speicher-Komponente mit Sensor-Zuordnung. → (anlage_id, inv_id)"""
    anlage = Anlage(anlagenname="Remap-Quelle", leistung_kwp=10.0)
    db.add(anlage)
    await db.flush()
    inv = Investition(
        anlage_id=anlage.id, typ="speicher", bezeichnung="Hausspeicher",
        anschaffungsdatum=date(2024, 1, 1), parameter={"kapazitaet_kwh": 10.0},
    )
    db.add(inv)
    await db.flush()

    anlage.sensor_mapping = {
        "basis": {"einspeisung": {"strategie": "sensor", "sensor_id": "sensor.einspeisung"}},
        "investitionen": {
            str(inv.id): {
                "felder": {"ladung_kwh": {"strategie": "sensor", "sensor_id": "sensor.speicher_ladung"}},
                "live": {"soc_prozent": "sensor.speicher_soc"},
            },
        },
        "quellen": {
            f"inv_energy_{inv.id}_ladung_kwh": {"quelle": "ha_app", "entity_id": "sensor.speicher_ladung"},
        },
    }
    await db.commit()
    return anlage.id, inv.id


async def _importiere(db, export_json: dict):
    datei = io.BytesIO(json.dumps(export_json).encode("utf-8"))
    return await import_json(
        file=UploadFile(filename="export.json", file=datei),
        ueberschreiben=False,
        db=db,
    )


@pytest.mark.asyncio
async def test_round_trip_zuordnung_zeigt_auf_die_neue_komponente(db):
    """Export → Import: die Speicher-Zuordnung überlebt und zeigt auf die neue ID."""
    anlage_id, alte_inv_id = await _anlage_mit_zuordnung(db)

    export = json.loads((await _export_anlage_full_impl(anlage_id, db)).body)
    assert export["export_version"] == "1.3"
    assert export["investitionen"][0]["id"] == alte_inv_id

    ergebnis = await _importiere(db, export)
    assert ergebnis.erfolg

    neue_anlage = (await db.execute(
        select(Anlage).where(Anlage.id == ergebnis.anlage_id)
    )).scalar_one()
    neue_inv = (await db.execute(
        select(Investition).where(Investition.anlage_id == ergebnis.anlage_id)
    )).scalar_one()

    mapping = neue_anlage.sensor_mapping
    assert str(neue_inv.id) in mapping["investitionen"], "Zuordnung verworfen statt umgeschrieben"
    assert (
        mapping["investitionen"][str(neue_inv.id)]["felder"]["ladung_kwh"]["sensor_id"]
        == "sensor.speicher_ladung"
    )
    assert mapping["investitionen"][str(neue_inv.id)]["live"]["soc_prozent"] == "sensor.speicher_soc"
    assert f"inv_energy_{neue_inv.id}_ladung_kwh" in mapping["quellen"]
    # Der Basis-Zähler war nie betroffen — er darf es auch jetzt nicht sein.
    assert mapping["basis"]["einspeisung"]["sensor_id"] == "sensor.einspeisung"


@pytest.mark.asyncio
async def test_round_trip_altdatei_ohne_ids_verwirft_und_sagt_es(db):
    """Export-Version 1.2 (ohne `id`): Zuordnung geht verloren — mit klarer Ansage."""
    anlage_id, _ = await _anlage_mit_zuordnung(db)

    export = json.loads((await _export_anlage_full_impl(anlage_id, db)).body)
    export["export_version"] = "1.2"
    for inv in export["investitionen"]:
        inv.pop("id", None)

    ergebnis = await _importiere(db, export)
    assert ergebnis.erfolg

    neue_anlage = (await db.execute(
        select(Anlage).where(Anlage.id == ergebnis.anlage_id)
    )).scalar_one()
    assert neue_anlage.sensor_mapping["investitionen"] == {}
    assert any("nicht übernehmen" in w for w in ergebnis.warnungen)
    assert any("vor 1.3" in w for w in ergebnis.warnungen)
