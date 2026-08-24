"""
Datenquellen-V4 — Quellen-Wahl landet auch in der klassischen `sensor_mapping`-Struktur.

Regression zum Forum-Befund simon42 #89667/36–41 (Algie + CHI3fx117, 2026-07-28/29):
Sensoren, die in der neuen Datenquellen-Fläche bzw. über die HA-Energy-Übernahme
im Setup-Wizard zugeordnet wurden, landeten ausschließlich in
`sensor_mapping["quellen"]`. Für alle Leser ist dieser Store aber nur ein
Read-Through — die AUFZÄHLUNG läuft über `basis`/`investitionen`. Folge bei
Neuinstallationen ab v4.0.0: Fläche zeigt Sensor + Live-Wert, Daten-Checker
meldet „Kein Basis-Zähler für: Einspeisung, Netzbezug", Cockpit/Tag/Monat leer.

Gewächtert wird beides:
- **Regression** — die beiden Schreibpfade (`/quelle`, Energy-Übernahme) + die
  Reparatur-Migration schreiben die klassische Struktur mit, der Daten-Checker
  ist danach OK und die Tages-kWh-Aufzählung (`basis_beitraege`) sieht das Feld.
- **Wächter** — baumweit (AST): wer `sensor_mapping["quellen"]` schreibt, muss
  die Schreib-Schicht `datenquellen_mapping_sync` benutzen. Fängt auch eine
  Schreibstelle, die es heute noch nicht gibt ([[feedback_bypass_kombi_schreib_schicht]]).
"""

from __future__ import annotations

import ast
from datetime import date
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from backend.api.routes import datenquellen as dq
from backend.api.routes.datenquellen import (
    EnergyUebernahmeRequest, QuelleSetRequest, set_feld_quelle,
    uebernehme_energy_vorschlaege,
)
from backend.models.anlage import Anlage
from backend.models.investition import Investition
from backend.services.daten_checker import CheckSeverity, DatenChecker
from backend.services.datenquellen_mapping_sync import uebernehme_quelle_ins_mapping
from backend.services.migrations.migrate_quellen_ins_mapping import (
    migriere_quellen_ins_mapping,
)
from backend.services.snapshot.komponenten_beitraege import basis_beitraege

from backend.tests.quellbaum import produktivbaum


# ─── Schreib-Schicht (pur) ──────────────────────────────────────────────────

def test_basis_energie_ha_schreibt_sensor_eintrag():
    """HA-Quelle → `basis[feld]` bitgleich zu dem, was der V3-Wizard schriebe."""
    mapping: dict = {}
    assert uebernehme_quelle_ins_mapping(
        mapping, "basis_energy_netzbezug_kwh", "ha_app", "sensor.power_meter_consumption"
    ) is True
    assert mapping["basis"]["netzbezug"] == {
        "strategie": "sensor", "sensor_id": "sensor.power_meter_consumption",
    }


def test_alle_drei_basis_energy_felder_inklusive_pv_gesamt():
    """`pv_gesamt_kwh` hat kein Snapshot-Gegenstück, wird aber von
    `ha_statistics`/`aktueller_monat` als Anlagen-Aggregat gelesen."""
    mapping: dict = {}
    for fid, feld in (
        ("basis_energy_einspeisung_kwh", "einspeisung"),
        ("basis_energy_netzbezug_kwh", "netzbezug"),
        ("basis_energy_pv_gesamt_kwh", "pv_gesamt"),
    ):
        assert uebernehme_quelle_ins_mapping(mapping, fid, "ha_connector", f"sensor.{feld}")
        assert mapping["basis"][feld]["sensor_id"] == f"sensor.{feld}"


def test_investition_energie_und_live():
    """Investitions-Felder landen unter `investitionen[id].felder` bzw. `.live`."""
    mapping: dict = {}
    assert uebernehme_quelle_ins_mapping(
        mapping, "inv_energy_7_ladung_kwh", "ha_app", "sensor.batt_charge")
    assert uebernehme_quelle_ins_mapping(
        mapping, "inv_live_7_soc", "ha_app", "sensor.batt_soc")
    inv = mapping["investitionen"]["7"]
    assert inv["felder"]["ladung_kwh"] == {"strategie": "sensor", "sensor_id": "sensor.batt_charge"}
    assert inv["live"] == {"soc": "sensor.batt_soc"}


def test_basis_live_feld():
    mapping: dict = {}
    assert uebernehme_quelle_ins_mapping(
        mapping, "basis_live_netz_kombi_w", "ha_connector", "sensor.power_meter_active_power")
    assert mapping["basis"]["live"] == {"netz_kombi_w": "sensor.power_meter_active_power"}


def test_nicht_ha_raeumt_bestehenden_sensor():
    """Wegschalten auf MQTT/keine entwertet den Sensor-Eintrag — sonst spränge
    die B8-2-Auflösung (Stufe 1 „HA-Sensor zugeordnet") zurück auf HA."""
    mapping = {
        "basis": {
            "einspeisung": {"strategie": "sensor", "sensor_id": "sensor.alt"},
            "live": {"pv_gesamt_w": "sensor.alt_w"},
        },
        "investitionen": {"3": {"felder": {"pv_erzeugung_kwh": {
            "strategie": "sensor", "sensor_id": "sensor.pv"}}}},
    }
    assert uebernehme_quelle_ins_mapping(
        mapping, "basis_energy_einspeisung_kwh", "mqtt_inbound_standard", None)
    assert mapping["basis"]["einspeisung"] == {"strategie": "keine"}

    assert uebernehme_quelle_ins_mapping(mapping, "basis_live_pv_gesamt_w", "keine", None)
    assert "pv_gesamt_w" not in mapping["basis"]["live"]

    assert uebernehme_quelle_ins_mapping(
        mapping, "inv_energy_3_pv_erzeugung_kwh", "mqtt_gateway", None)
    assert mapping["investitionen"]["3"]["felder"]["pv_erzeugung_kwh"] == {"strategie": "keine"}


def test_nicht_ha_legt_nichts_an_und_ist_idempotent():
    """Ohne bestehenden Eintrag ändert eine Nicht-HA-Quelle nichts; ein
    identischer HA-Schreibvorgang meldet keine Änderung."""
    mapping: dict = {}
    assert uebernehme_quelle_ins_mapping(
        mapping, "basis_energy_einspeisung_kwh", "keine", None) is False
    assert mapping == {}

    assert uebernehme_quelle_ins_mapping(
        mapping, "basis_energy_einspeisung_kwh", "ha_app", "sensor.x") is True
    assert uebernehme_quelle_ins_mapping(
        mapping, "basis_energy_einspeisung_kwh", "ha_app", "sensor.x") is False


def test_unbekannte_feld_id_bleibt_folgenlos():
    """Die Fläche kennt Felder ohne Mapping-Gegenstück — kein Müll-Eintrag."""
    mapping: dict = {}
    for fid in ("basis_energy_strompreis_ct", "quatsch", "inv_energy_x_ladung_kwh"):
        assert uebernehme_quelle_ins_mapping(mapping, fid, "ha_app", "sensor.x") is False
    assert mapping == {}


def test_parameter_ueberlebt_sensorwechsel():
    """Zusatz-Parameter eines V3-Eintrags gehen beim Sensor-Wechsel nicht verloren."""
    mapping = {"basis": {"netzbezug": {
        "strategie": "sensor", "sensor_id": "sensor.alt", "parameter": {"faktor": 2}}}}
    assert uebernehme_quelle_ins_mapping(
        mapping, "basis_energy_netzbezug_kwh", "ha_app", "sensor.neu")
    assert mapping["basis"]["netzbezug"] == {
        "strategie": "sensor", "sensor_id": "sensor.neu", "parameter": {"faktor": 2},
    }


# ─── Schreibpfade + Daten-Checker (Regression zum Forum-Befund) ─────────────

async def _seed(db) -> Anlage:
    anlage = Anlage(anlagenname="Test", leistung_kwp=10.0, sensor_mapping={})
    db.add(anlage)
    await db.flush()
    db.add(Investition(
        anlage_id=anlage.id, typ="pv-module", bezeichnung="Süd",
        leistung_kwp=10.0, anschaffungsdatum=date(2024, 1, 1), aktiv=True,
    ))
    await db.flush()
    return anlage


async def _reload(db, anlage_id: int) -> Anlage:
    return (await db.execute(
        select(Anlage).options(selectinload(Anlage.investitionen))
        .where(Anlage.id == anlage_id)
    )).scalar_one()


@pytest.mark.asyncio
async def test_flaeche_zuordnung_ist_fuer_checker_und_aggregation_sichtbar(db):
    """Der gemeldete Fall: zwei Basis-Zähler in der Fläche zugeordnet →
    Daten-Checker OK und die Tages-kWh-Aufzählung kennt beide Felder."""
    anlage = await _seed(db)
    await db.commit()

    for fid, eid in (
        ("basis_energy_einspeisung_kwh", "sensor.power_meter_exported"),
        ("basis_energy_netzbezug_kwh", "sensor.power_meter_consumption"),
    ):
        await set_feld_quelle(
            anlage.id, fid, QuelleSetRequest(quelle="ha_app", entity_id=eid), db)

    anlage = await _reload(db, anlage.id)
    mapping = anlage.sensor_mapping
    # Beide Wahrheiten stimmen überein: Store (Herkunft) + klassische Struktur.
    assert mapping["quellen"]["basis_energy_netzbezug_kwh"]["entity_id"] == \
        "sensor.power_meter_consumption"
    assert mapping["basis"]["netzbezug"]["sensor_id"] == "sensor.power_meter_consumption"
    assert mapping["basis"]["einspeisung"]["sensor_id"] == "sensor.power_meter_exported"

    ergebnisse = DatenChecker(db)._check_energieprofil_abdeckung(anlage)
    basis_meldungen = [e for e in ergebnisse if "Basis-Zähler" in e.meldung]
    assert basis_meldungen, "Abdeckungs-Check liefert keine Basis-Meldung"
    assert all(e.schwere == CheckSeverity.OK for e in basis_meldungen), \
        [e.meldung for e in basis_meldungen]

    assert {b.feld for b in basis_beitraege(mapping)} == {"einspeisung", "netzbezug"}


@pytest.mark.asyncio
async def test_wegschalten_raeumt_auch_die_klassische_struktur(db):
    """Umschalten auf „keine" darf keinen HA-Sensor zurücklassen."""
    anlage = await _seed(db)
    await db.commit()
    await set_feld_quelle(
        anlage.id, "basis_energy_einspeisung_kwh",
        QuelleSetRequest(quelle="ha_app", entity_id="sensor.x"), db)
    await set_feld_quelle(
        anlage.id, "basis_energy_einspeisung_kwh", QuelleSetRequest(quelle="keine"), db)

    anlage = await _reload(db, anlage.id)
    assert anlage.sensor_mapping["basis"]["einspeisung"] == {"strategie": "keine"}
    assert basis_beitraege(anlage.sensor_mapping) == []


@pytest.mark.asyncio
async def test_energy_uebernahme_aus_dem_setup_wizard(db, monkeypatch):
    """Der zweite Schreibpfad (#197-Übernahme im Setup-Wizard) schreibt mit."""
    anlage = await _seed(db)
    await db.commit()
    monkeypatch.setattr(
        dq, "_resolve_ha", lambda _db: _fake_ha(), raising=True)

    await uebernehme_energy_vorschlaege(
        anlage.id,
        EnergyUebernahmeRequest(basis={
            "einspeisung": "sensor.exported", "netzbezug": "sensor.consumption",
        }),
        db,
    )
    anlage = await _reload(db, anlage.id)
    assert anlage.sensor_mapping["basis"]["einspeisung"]["sensor_id"] == "sensor.exported"
    assert anlage.sensor_mapping["basis"]["netzbezug"]["sensor_id"] == "sensor.consumption"


async def _fake_ha():
    return ("http://ha.local/api", "token", "ha_app")


# ─── Reparatur-Migration für Bestands-Installationen ────────────────────────

@pytest.mark.asyncio
async def test_migration_zieht_ha_zuordnungen_nach_ohne_zu_raeumen(db):
    """Additiv: HA-Einträge werden nachgezogen, `keine`/MQTT bleiben unberührt
    und ein bereits vorhandener abweichender Sensor-Eintrag wird nicht angefasst,
    wenn der Store dieselbe Entity nennt."""
    anlage = await _seed(db)
    anlage.sensor_mapping = {
        "basis": {"pv_gesamt": {"strategie": "sensor", "sensor_id": "sensor.pv_alt"}},
        "quellen": {
            "basis_energy_einspeisung_kwh": {
                "quelle": "ha_app", "entity_id": "sensor.exported"},
            "basis_energy_netzbezug_kwh": {
                "quelle": "ha_connector", "entity_id": "sensor.consumption"},
            "inv_energy_9_pv_erzeugung_kwh": {
                "quelle": "ha_app", "entity_id": "sensor.pv_string"},
            "basis_live_pv_gesamt_w": {"quelle": "keine"},
            "basis_energy_pv_gesamt_kwh": {"quelle": "mqtt_inbound_standard"},
        },
    }
    await db.commit()

    await migriere_quellen_ins_mapping(db)
    await db.commit()

    anlage = await _reload(db, anlage.id)
    basis = anlage.sensor_mapping["basis"]
    assert basis["einspeisung"]["sensor_id"] == "sensor.exported"
    assert basis["netzbezug"]["sensor_id"] == "sensor.consumption"
    assert anlage.sensor_mapping["investitionen"]["9"]["felder"]["pv_erzeugung_kwh"] == {
        "strategie": "sensor", "sensor_id": "sensor.pv_string"}
    # Nicht-HA-Einträge räumen NICHT (das ist der expliziten Nutzer-Wahl vorbehalten).
    assert basis["pv_gesamt"] == {"strategie": "sensor", "sensor_id": "sensor.pv_alt"}
    assert "live" not in basis


# ─── Wächter (baumweit, AST) ────────────────────────────────────────────────

# Schreiber, die den Store bewusst OHNE die Schreib-Schicht setzen:
#   b8-Materialisierung — Gegenrichtung: leitet die Quelle AUS dem Mapping ab.
#
# `services/datenquellen_wizard_sync.py` stand hier bis 2026-08-13. Er sicherte den
# Store gegen den Voll-Rewrite durch `POST /api/sensor-mapping/{id}`; mit dem
# Stilllegen dieser Route (N-241) hatte er keinen Aufrufer mehr und ist gefallen.
# Eine Ausnahme für einen toten Schreiber stellt sonst eine künftige gleichnamige
# Datei stumm frei.
_WAECHTER_AUSNAHMEN = {
    "services/migrations/migrate_datenquellen_materialisieren.py",
}
_SCHICHT = "datenquellen_mapping_sync"


def _backend_dir() -> Path:
    return Path(__file__).resolve().parent.parent


def _schreibt_quellen_store(baum: ast.AST) -> bool:
    """`<expr>["quellen"] = …` bzw. `<expr>[QUELLEN_KEY] = …` im Modul?"""
    for knoten in ast.walk(baum):
        if not isinstance(knoten, ast.Assign):
            continue
        for ziel in knoten.targets:
            if not isinstance(ziel, ast.Subscript):
                continue
            key = ziel.slice
            if isinstance(key, ast.Constant) and key.value == "quellen":
                return True
            if isinstance(key, ast.Name) and key.id == "QUELLEN_KEY":
                return True
    return False


def test_waechter_quellen_schreiber_nutzen_die_schreib_schicht():
    """Wer `sensor_mapping["quellen"]` schreibt, muss die klassische Struktur
    mitschreiben — sonst entsteht der Forum-Befund erneut an neuer Stelle."""
    verstoesse: list[str] = []
    # ⚠ Hier stand bis 2026-08-24 ein Filter, der nur `tests/` ausnahm — das
    # virtualenv lief mit. Folgenlos geblieben, weil ein `"quellen" not in
    # quelle` vorher abkürzte; falsch war es trotzdem, und die nächste
    # Erweiterung des Prüfers hätte den Kurzschluss verlieren können.
    for datei in produktivbaum():
        if datei.rel in _WAECHTER_AUSNAHMEN:
            continue
        if "quellen" not in datei.quelle:
            continue
        if not _schreibt_quellen_store(datei.baum):
            continue
        if _SCHICHT not in datei.quelle:
            verstoesse.append(datei.rel)
    assert not verstoesse, (
        "Schreibt den quellen-Store ohne Schreib-Schicht "
        f"`services/{_SCHICHT}.py`: {verstoesse}"
    )
