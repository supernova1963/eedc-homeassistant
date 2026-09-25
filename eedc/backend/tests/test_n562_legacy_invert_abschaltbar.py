"""N-562 — eine vor v4 gesetzte Vorzeichen-Umkehr lässt sich abschalten (T89667 #378).

Bis v4 lag die Umkehr als `sensor_mapping.basis.live_invert` bzw.
`investitionen[id].live_invert`. Die Startup-Migration hat sie einmal in den
Store `sensor_mapping.invertieren` gefaltet, das Legacy-Flag aber stehen lassen,
und `extract_live_config` vereinigt beide. Der Schalter der Datenquellen-Fläche
entfernte beim Ausschalten nur den Store-Eintrag ⇒ grauer Schalter, Wert weiter
umgedreht. Dasselbe nach einem Restore eines v3-Backups: das Legacy-Flag wirkt,
der Store kennt es nicht, der Schalter stand grau.

Geprüft wird die **Wirkung** am Trichter `extract_live_config`, den alle
Konsumenten lesen (Live-Power, Tagesverlauf, Verbrauchsprofil, History).
"""

from __future__ import annotations

from datetime import date

from backend.api.routes.datenquellen import (
    InvertSetRequest,
    get_datenquellen_felder,
    set_feld_invert,
)
from backend.models.anlage import Anlage
from backend.models.investition import Investition
from backend.models.mqtt_gateway_mapping import MqttGatewayMapping  # noqa: F401 — Tabelle für die Feldliste
from backend.services.live_sensor_config import (
    entferne_legacy_invert,
    extract_live_config,
    legacy_invert_aktiv,
)


async def _anlage_mit_speicher(db, sensor_mapping_fn) -> tuple[Anlage, int]:
    a = Anlage(anlagenname="Invert", leistung_kwp=10.0, sensor_mapping={})
    db.add(a)
    await db.flush()
    sp = Investition(
        anlage_id=a.id, typ="speicher", bezeichnung="Batteriespeicher",
        anschaffungsdatum=date(2020, 1, 1), parameter={"kapazitaet_kwh": 10},
    )
    db.add(sp)
    await db.flush()
    a.sensor_mapping = sensor_mapping_fn(sp.id)
    await db.flush()
    return a, sp.id


def _nur_legacy(inv_id: int) -> dict:
    return {
        "investitionen": {
            str(inv_id): {
                "live": {"leistung_w": "sensor.battery_power"},
                "live_invert": {"leistung_w": True},
            },
        },
        "invertieren": {},
    }


def _legacy_und_store(inv_id: int) -> dict:
    """Der Zustand nach der Startup-Migration: beide Ablagen tragen das Flag."""
    m = _nur_legacy(inv_id)
    m["invertieren"] = {f"inv_live_{inv_id}_leistung_w": True}
    return m


async def test_ausschalten_hebt_die_umkehr_wirklich_auf(db):
    a, inv_id = await _anlage_mit_speicher(db, _legacy_und_store)
    fid = f"inv_live_{inv_id}_leistung_w"
    assert extract_live_config(a)[3].get(str(inv_id), {}).get("leistung_w") is True, \
        "Vorbedingung: die Umkehr wirkt"

    antwort = await set_feld_invert(a.id, fid, InvertSetRequest(invertieren=False), db)

    assert antwort["invertieren"] is False
    assert extract_live_config(a)[3] == {}, "grauer Schalter muss heißen: nicht umgekehrt"
    assert "leistung_w" not in a.sensor_mapping["investitionen"][str(inv_id)]["live_invert"]


async def test_restore_ohne_store_zeigt_den_schalter_aktiv_und_schaltet_ab(db):
    """v3-Backup nach der Migration eingespielt: nur das Legacy-Flag ist da."""
    a, inv_id = await _anlage_mit_speicher(db, _nur_legacy)
    fid = f"inv_live_{inv_id}_leistung_w"

    felder = await get_datenquellen_felder(a.id, db)
    zeile = next(
        f for g in felder["gruppen"] for f in g["felder"] if f["id"] == fid
    )
    assert zeile["invertieren"] is True, "der Schalter zeigt, was wirkt"

    await set_feld_invert(a.id, fid, InvertSetRequest(invertieren=False), db)
    assert extract_live_config(a)[3] == {}


def test_basis_feld_legacy_wird_erkannt_und_entfernt():
    m = {"basis": {"live_invert": {"einspeisung_w": True, "netzbezug_w": True}}}
    assert legacy_invert_aktiv(m, "basis_live_einspeisung_w") is True
    assert entferne_legacy_invert(m, "basis_live_einspeisung_w") is True
    assert m["basis"]["live_invert"] == {"netzbezug_w": True}, "nur das eine Feld"
    assert legacy_invert_aktiv(m, "basis_live_einspeisung_w") is False


def test_investitions_id_praefix_trifft_nicht_die_nachbarin():
    """`inv_live_7_…` darf nicht `inv_live_70_…` treffen (Zerlegung wie im Trichter)."""
    m = {"investitionen": {"70": {"live_invert": {"leistung_w": True}}}}
    assert legacy_invert_aktiv(m, "inv_live_7_leistung_w") is False
    assert entferne_legacy_invert(m, "inv_live_7_leistung_w") is False
    assert legacy_invert_aktiv(m, "inv_live_70_leistung_w") is True


def test_ohne_legacy_nichts_zu_tun():
    assert legacy_invert_aktiv({}, "inv_live_1_leistung_w") is False
    assert entferne_legacy_invert({}, "basis_live_einspeisung_w") is False
    assert legacy_invert_aktiv({"basis": {}}, "basis_energy_einspeisung_kwh") is False
