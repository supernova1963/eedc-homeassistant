"""N-555 Stufe 1 + N-557 — der Fahrverbrauch bleibt Fahrverbrauch.

Konzept `docs/drafts/KONZEPT-HEIMLADUNG-FAHRVERBRAUCH.md`, Fassung 7.1, Abschnitt 3 (Stufe 1),
Proben aus Anhang B (Zeilen „Stufe 1"). Gemeldet von Johnny_1993 (T89667 #363–#375): eine Wallbox
mit HA-Sensor hatte im September 0 kWh geladen, am E-Auto stand nur „Verbrauch" — und eedc zeigte
1.364 kWh „Ladung".

Gliederung nach Regel:

* **Regel 1 / 2-Ü** — die eine Funktion (`entscheide_emob_heimladung`) und ihre Leser.
* **Regel 4** — 0 ist ein Wert bei den Heimlade-Mengenfeldern (Monatsabschluss, Statistik-Import).
* **Regel 5** — die Startroutine bucht nicht mehr um; die einmalige Rückbenennung.
* **Regel 6** — der Wächter (Fahrverbrauch als Menge nur in der einen Funktion), Tag und Stunde.
* **Regel 10** — „Ladung gesamt" und kWh/100 km (N-557), Symmetrie über vier Sichten.

Schwesterdateien: test_n555_stufe2_messung_je_auto.py (Stufe 2, Messung je Auto),
test_n557_emob_effizienz_symmetrie.py.
"""

from __future__ import annotations

import ast
import json
from datetime import date, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import select, text
from sqlalchemy.orm.attributes import flag_modified

from backend.api.routes.aktueller_monat.aggregation import (
    emob_heimlade_quellen,
    emob_heimladung_pool,
)
from backend.api.routes.aktueller_monat.schemas import DatenquelleInfo
from backend.core.field_definitions import (
    HEIMLADE_FELDER,
    HEIMLADE_MENGEN_FELDER,
    get_eauto_ladung_kwh,
    get_emob_pv_netz_kwh,
)
from backend.models import Anlage, Investition, InvestitionMonatsdaten
from backend.models.monatsdaten import Monatsdaten
from backend.services.eauto_wirtschaftlichkeit import (
    QUELLE_EAUTO,
    QUELLE_LEER,
    QUELLE_NULL,
    QUELLE_SCHAETZUNG,
    QUELLE_WALLBOX,
    dienstliche_ladung_der_zeile,
    entscheide_emob_heimladung,
    get_emob_heimladung_canonical,
)

_BACKEND = Path(__file__).resolve().parents[1]
JOHNNY = {"km_gefahren": 1500.0, "verbrauch_kwh": 1364.0}


# ═════════════════════════════════════════════════════════════════════════════
# Regel 1 + Regel 2-Ü — die eine Funktion
# ═════════════════════════════════════════════════════════════════════════════


def test_johnny_wallbox_mit_0_und_nur_verbrauch_ergibt_0():
    """Regel 2-Ü Schritt 3: die Wallbox trägt einen Wert (0) ⇒ Heimladung 0, kein Fahrverbrauch."""
    e = entscheide_emob_heimladung(
        eauto_je_inv={7: dict(JOHNNY)}, wallbox_zeilen=[{"ladung_kwh": 0.0}],
    )
    assert e.quelle == QUELLE_NULL
    assert (e.pool.ladung_kwh, e.pool.pv_kwh, e.pool.netz_kwh) == (0.0, 0.0, 0.0)
    assert e.schaetzung_je_auto == {}


def test_wallbox_ueber_0_ist_die_quelle():
    e = entscheide_emob_heimladung(
        eauto_je_inv={7: dict(JOHNNY)},
        wallbox_zeilen=[{"ladung_kwh": 200.0, "ladung_pv_kwh": 120.0}],
    )
    assert e.quelle == QUELLE_WALLBOX
    assert (e.pool.ladung_kwh, e.pool.pv_kwh, e.pool.netz_kwh) == (200.0, 120.0, 80.0)


def test_steckerlader_neben_wallbox_mit_0_traegt_seine_heimfelder():
    """Regel 2-Ü Schritt 2: „Heim: PV/Netz" am Auto, Wallbox mit 0 ⇒ die Autowerte."""
    e = entscheide_emob_heimladung(
        eauto_je_inv={7: {"ladung_pv_kwh": 30.0, "ladung_netz_kwh": 20.0, "verbrauch_kwh": 90.0}},
        wallbox_zeilen=[{"ladung_kwh": 0.0}],
    )
    assert e.quelle == QUELLE_EAUTO
    assert (e.pool.ladung_kwh, e.pool.pv_kwh, e.pool.netz_kwh) == (50.0, 30.0, 20.0)


@pytest.mark.parametrize("wallbox_zeilen", [[], [{"ladung_kwh": 0.0}]])
def test_alter_gesamtwert_am_auto_zaehlt_neben_wallbox_in_betrieb_nicht(wallbox_zeilen):
    """Regel 2-Ü Schritt 2: der alte `ladung_kwh` am Auto zählt nur OHNE Wallbox in Betrieb —
    auch wenn die Wallbox im Monat gar keine Zeile hat. Er ist aber ein Wert (Schritt 3) ⇒ 0."""
    e = entscheide_emob_heimladung(
        eauto_je_inv={7: {"ladung_kwh": 100.0, "verbrauch_kwh": 120.0}},
        wallbox_zeilen=wallbox_zeilen, wallbox_in_betrieb=True,
    )
    assert e.quelle == QUELLE_NULL
    assert e.pool.ladung_kwh == 0.0


def test_alter_gesamtwert_am_auto_zaehlt_ohne_wallbox():
    e = entscheide_emob_heimladung(
        eauto_je_inv={7: {"ladung_kwh": 100.0, "verbrauch_kwh": 120.0}},
        wallbox_zeilen=[], wallbox_in_betrieb=False,
    )
    assert e.quelle == QUELLE_EAUTO
    assert (e.pool.ladung_kwh, e.pool.netz_kwh) == (100.0, 100.0)


def test_nur_heim_pv_ohne_netz_ergibt_netz_0_statt_verbrauch_minus_pv():
    """Konzept §6: „Keine Wallbox, Heim: PV erfasst, Heim: Netz fehlt" ⇒ Netz 0, Heimladung = PV."""
    e = entscheide_emob_heimladung(
        eauto_je_inv={7: {"ladung_pv_kwh": 40.0, "verbrauch_kwh": 150.0}},
        wallbox_zeilen=[], wallbox_in_betrieb=False,
    )
    assert e.quelle == QUELLE_EAUTO
    assert (e.pool.ladung_kwh, e.pool.pv_kwh, e.pool.netz_kwh) == (40.0, 40.0, 0.0)


def test_reiner_schaetzfall_ist_der_fahrverbrauch_als_schaetzung():
    """Regel 1: nichts bekannt ⇒ Fahrverbrauch je Auto, ausdrücklich „schaetzung"."""
    e = entscheide_emob_heimladung(
        eauto_je_inv={7: {"verbrauch_kwh": 216.0}, 8: {"verbrauch_kwh": 84.0}},
        wallbox_zeilen=[], wallbox_in_betrieb=False,
    )
    assert e.quelle == QUELLE_SCHAETZUNG
    assert e.pool.ladung_kwh == 300.0 and e.pool.netz_kwh == 300.0 and e.pool.pv_kwh == 0.0
    assert e.schaetzung_je_auto == {7: (0.0, 216.0), 8: (0.0, 84.0)}
    assert e.anteil_abgeleitet is False


def test_schaetzung_bekommt_die_tages_quote_wie_vorher_die_zeile():
    """Offene Frage F-1 (Bericht): dieselbe Zahl wie vor N-555, aber als Schätzung erkennbar."""
    e = entscheide_emob_heimladung(
        eauto_je_inv={7: {"verbrauch_kwh": 200.0}}, wallbox_zeilen=[], pv_quote=0.25,
    )
    assert e.quelle == QUELLE_SCHAETZUNG
    assert (e.pool.pv_kwh, e.pool.netz_kwh) == (50.0, 150.0)
    assert e.anteil_abgeleitet is True


def test_laufender_monat_mit_quelle_ergibt_0_statt_schaetzung():
    """Regel 1: im laufenden Monat genügt eine Quelle an einem Heimlade-Feld."""
    e = entscheide_emob_heimladung(
        eauto_je_inv={7: dict(JOHNNY)}, wallbox_zeilen=[{}], wallbox_in_betrieb=True,
        heimlade_quellen={(5, "ladung_kwh")},
    )
    assert e.quelle == QUELLE_NULL and e.pool.ladung_kwh == 0.0


def test_nichts_und_kein_fahrverbrauch_ist_leer():
    e = entscheide_emob_heimladung(eauto_je_inv={7: {"km_gefahren": 100.0}}, wallbox_zeilen=[])
    assert e.quelle == QUELLE_LEER and e.pool.ladung_kwh == 0.0


@pytest.mark.parametrize("zeile", [
    {"verbrauch_kwh": 80.0},
    {"verbrauch_kwh": 80.0, "ladung_pv_kwh": 30.0},
    {"ladung_kwh": 60.0, "ladung_pv_kwh": 20.0, "verbrauch_kwh": 80.0},
    {"ladung_netz_kwh": 0.0, "verbrauch_kwh": 80.0},
    {"ladung_netz_kwh": 25.0, "ladung_pv_kwh": 5.0},
    {"ladung_pv_kwh": 90.0, "verbrauch_kwh": 80.0},
    {},
])
def test_dienstwagen_menge_bleibt_bitgleich(zeile):
    """Regel 2-Ü, Dienstwagen unverändert: dieselbe Menge wie die alte Lese-Hilfe mit Ersatz."""
    pv_alt = float(zeile.get("ladung_pv_kwh") or 0)
    if zeile.get("ladung_netz_kwh") is not None:
        netz_alt = float(zeile["ladung_netz_kwh"])
    else:
        total_alt = float(zeile.get("ladung_kwh") or zeile.get("verbrauch_kwh") or 0)
        netz_alt = max(0.0, total_alt - pv_alt)
    dl = dienstliche_ladung_der_zeile(zeile)
    assert (dl.pv_kwh, dl.netz_kwh) == (pv_alt, netz_alt)
    nur_fahrverbrauch = (
        zeile.get("ladung_netz_kwh") is None and not zeile.get("ladung_kwh")
        and bool(zeile.get("verbrauch_kwh"))
    )
    if dl.pv_kwh + dl.netz_kwh > 0:
        assert dl.gemessen is not nur_fahrverbrauch


def test_die_kurzform_ist_dieselbe_regel():
    """`get_emob_heimladung_canonical` ist nur noch die Kurzform der einen Funktion."""
    for ea, wb in (
        ([dict(JOHNNY)], [{"ladung_kwh": 0.0}]),
        ([{"ladung_pv_kwh": 30.0, "ladung_netz_kwh": 20.0}], [{"ladung_kwh": 0.0}]),
        ([{"verbrauch_kwh": 216.0}], []),
    ):
        kurz = get_emob_heimladung_canonical(eauto_imd_data=ea, wallbox_imd_data=wb)
        lang = entscheide_emob_heimladung(eauto_je_inv=dict(enumerate(ea)), wallbox_zeilen=wb).pool
        assert kurz == lang


def test_lese_hilfen_setzen_keinen_fahrverbrauch_mehr_ein():
    """Regel 6: `reader.py:125/:155-157` — der stille Ersatz ist weg."""
    assert get_eauto_ladung_kwh({"verbrauch_kwh": 216.0}) == 0.0
    assert get_emob_pv_netz_kwh({"verbrauch_kwh": 216.0}) == (0.0, 0.0)
    assert get_emob_pv_netz_kwh({"verbrauch_kwh": 216.0, "ladung_pv_kwh": 30.0}) == (30.0, 0.0)
    assert get_eauto_ladung_kwh({"ladung_kwh": 50.0, "verbrauch_kwh": 216.0}) == 50.0


def test_die_zwei_feldlisten_folgen_dem_konzept():
    """Regel 1 / Regel 4 (E1 eng): Heimlade-Felder und Mengenfelder — keine PV-Felder bei der 0,
    kein Wallbox-`ladung_netz_kwh` (das Feld gibt es in der Registry nicht)."""
    assert HEIMLADE_FELDER == {
        "wallbox": ("ladung_kwh", "ladung_pv_kwh"),
        "e-auto": ("ladung_pv_kwh", "ladung_netz_kwh", "ladung_kwh"),
    }
    assert HEIMLADE_MENGEN_FELDER == {
        "wallbox": ("ladung_kwh",),
        "e-auto": ("ladung_netz_kwh", "ladung_kwh"),
    }


# ─── Regel 1 im laufenden Monat: was „Quelle zugeordnet" heißt ───────────────


def _sensor(eid: str) -> dict:
    return {"strategie": "sensor", "sensor_id": eid}


def _anlage_ns(mapping: dict, quellen: dict | None = None):
    sm = {"investitionen": mapping}
    if quellen is not None:
        sm["quellen"] = quellen
    return SimpleNamespace(id=1, sensor_mapping=sm)


def _inv_ns(inv_id: int, typ: str, *, dienstlich: bool = False, ab: date = date(2024, 1, 1)):
    inv = Investition(
        id=inv_id, anlage_id=1, typ=typ, bezeichnung=f"{typ} {inv_id}",
        anschaffungsdatum=ab, aktiv=True,
        parameter={"ist_dienstlich": True} if dienstlich else {},
    )
    return inv


async def test_quelle_ha_sensor_zaehlt(db):
    anlage = _anlage_ns({"5": {"felder": {"ladung_kwh": _sensor("sensor.wb")}}})
    q = await emob_heimlade_quellen(db, anlage, [_inv_ns(5, "wallbox")], 2026, 9)
    assert q == frozenset({(5, "ladung_kwh")})


async def test_quelle_keine_zaehlt_nicht(db):
    anlage = _anlage_ns(
        {"5": {"felder": {"ladung_kwh": _sensor("sensor.wb")}}},
        quellen={"inv_energy_5_ladung_kwh": {"quelle": "keine"}},
    )
    q = await emob_heimlade_quellen(db, anlage, [_inv_ns(5, "wallbox")], 2026, 9)
    assert q == frozenset()


async def test_datenquellen_stempel_ohne_zuordnung_ist_keine_quelle(db):
    """Anhang B: der Stempel `mqtt_inbound_standard` ohne angekommene Zählerstände ⇒ Schätzung erlaubt."""
    anlage = _anlage_ns({}, quellen={"inv_energy_5_ladung_kwh": {"quelle": "mqtt_inbound_standard"}})
    q = await emob_heimlade_quellen(db, anlage, [_inv_ns(5, "wallbox")], 2026, 9)
    assert q == frozenset()


async def test_quelle_mqtt_zaehlerstaende_zaehlen(db):
    """MQTT (auch Connector-Wallboxen, dieselbe MQTT-Historie): angekommene Stände ⇒ Quelle."""
    from backend.models.mqtt_energy_snapshot import MqttEnergySnapshot

    a = Anlage(anlagenname="MQTT", leistung_kwp=5.0)
    db.add(a)
    await db.flush()
    db.add(MqttEnergySnapshot(
        anlage_id=a.id, timestamp=datetime(2026, 9, 3, 12, 0), energy_key="inv/5/ladung_kwh",
        value_kwh=1200.0,
    ))
    await db.flush()
    anlage = SimpleNamespace(id=a.id, sensor_mapping={"investitionen": {}})
    q = await emob_heimlade_quellen(db, anlage, [_inv_ns(5, "wallbox")], 2026, 9)
    assert q == frozenset({(5, "ladung_kwh")})


async def test_quelle_zaehlt_nur_privat_und_in_betrieb(db):
    mapping = {
        "5": {"felder": {"ladung_kwh": _sensor("sensor.wb")}},
        "6": {"felder": {"ladung_kwh": _sensor("sensor.wb2")}},
    }
    invs = [_inv_ns(5, "wallbox", dienstlich=True), _inv_ns(6, "wallbox", ab=date(2026, 10, 1))]
    q = await emob_heimlade_quellen(db, _anlage_ns(mapping), invs, 2026, 9)
    assert q == frozenset()


# ─── Regel 1 in Cockpit → Monat (`emob_heimladung_pool`) ─────────────────────

_LIVE = DatenquelleInfo(quelle="ha_statistics", konfidenz=92)


def test_laufender_monat_johnny_mit_quelle_ergibt_0():
    invs = [_inv_ns(5, "wallbox"), _inv_ns(7, "e-auto")]
    resolved = {"inv_7_verbrauch_kwh": (1364.0, _LIVE), "inv_7_km_gefahren": (1500.0, _LIVE)}
    out = emob_heimladung_pool(
        direct_fields=set(), investitionen=invs, jahr=2026, monat=9, resolved=resolved,
        ist_aktueller_monat=True, heimlade_quellen=frozenset({(5, "ladung_kwh")}),
    )
    assert resolved["emob_ladung_kwh"][0] == 0.0
    assert out["emob_entscheid"].quelle == QUELLE_NULL


def test_laufender_monat_ohne_quelle_bleibt_schaetzung():
    invs = [_inv_ns(7, "e-auto")]
    resolved = {"inv_7_verbrauch_kwh": (216.0, _LIVE)}
    emob_heimladung_pool(
        direct_fields=set(), investitionen=invs, jahr=2026, monat=9, resolved=resolved,
        ist_aktueller_monat=True,
    )
    assert resolved["emob_ladung_kwh"][0] == 216.0


def test_abgeschlossener_monat_ha_null_mit_daten_zaehlt_wie_gespeichert():
    """Regel 1: im abgeschlossenen Monat ohne Monatsabschluss zählt der HA-Wert der Wallbox,
    auch 0, sofern die Statistik Daten hat."""
    invs = [_inv_ns(5, "wallbox"), _inv_ns(7, "e-auto")]
    resolved = {"inv_7_verbrauch_kwh": (1364.0, _LIVE)}
    emob_heimladung_pool(
        direct_fields=set(), investitionen=invs, jahr=2026, monat=8, resolved=resolved,
        ist_aktueller_monat=False, ha_felder_mit_daten=frozenset({"inv_5_ladung_kwh"}),
    )
    assert resolved["emob_ladung_kwh"][0] == 0.0


def test_abgeschlossener_monat_ha_ohne_daten_bleibt_schaetzung():
    invs = [_inv_ns(5, "wallbox"), _inv_ns(7, "e-auto")]
    resolved = {"inv_7_verbrauch_kwh": (1364.0, _LIVE)}
    emob_heimladung_pool(
        direct_fields=set(), investitionen=invs, jahr=2026, monat=8, resolved=resolved,
        ist_aktueller_monat=False, ha_felder_mit_daten=frozenset(),
    )
    assert resolved["emob_ladung_kwh"][0] == 1364.0


def test_laufender_monat_reicht_die_externe_ladung_in_kwh_weiter():
    """N-557 / Regel 10: mit Extern-Sensor sofort, nicht erst ab dem Monatsabschluss."""
    invs = [_inv_ns(7, "e-auto")]
    resolved = {
        "inv_7_ladung_pv_kwh": (40.0, _LIVE), "inv_7_ladung_netz_kwh": (60.0, _LIVE),
        "inv_7_ladung_extern_kwh": (30.0, _LIVE), "inv_7_ladung_extern_euro": (15.0, _LIVE),
    }
    out = emob_heimladung_pool(
        direct_fields=set(), investitionen=invs, jahr=2026, monat=9, resolved=resolved,
        ist_aktueller_monat=True,
    )
    assert resolved["emob_ladung_kwh"][0] == 100.0
    assert resolved["emob_ladung_extern_kwh"][0] == 30.0
    assert out["emob_entscheid"].pool.extern_kwh == 30.0


# ─── Regel 1 über die Schicht (Monats-Fakten) und die Community ─────────────


async def _johnny_anlage(db, *, wallbox_wert=0.0, mit_wallbox_zeile=True, dienstwagen=False):
    a = Anlage(anlagenname="Johnny", leistung_kwp=10.0)
    db.add(a)
    await db.flush()
    wb = Investition(anlage_id=a.id, typ="wallbox", bezeichnung="Wallbox",
                     anschaffungsdatum=date(2024, 1, 1), aktiv=True)
    ea = Investition(anlage_id=a.id, typ="e-auto", bezeichnung="Auto",
                     anschaffungsdatum=date(2024, 1, 1), aktiv=True,
                     parameter={"ist_dienstlich": True} if dienstwagen else {})
    db.add_all([wb, ea])
    await db.flush()
    db.add(Monatsdaten(anlage_id=a.id, jahr=2025, monat=9, einspeisung_kwh=100.0,
                       netzbezug_kwh=200.0, pv_erzeugung_kwh=500.0))
    if mit_wallbox_zeile:
        db.add(InvestitionMonatsdaten(investition_id=wb.id, jahr=2025, monat=9,
                                      verbrauch_daten={"ladung_kwh": wallbox_wert}))
    db.add(InvestitionMonatsdaten(investition_id=ea.id, jahr=2025, monat=9,
                                  verbrauch_daten=dict(JOHNNY)))
    await db.commit()
    return a, wb, ea


async def test_monats_fakten_johnny_gespeicherte_0(db):
    from backend.services.monats_fakten import lade_monats_fakten

    a, _wb, _ea = await _johnny_anlage(db)
    (f,) = await lade_monats_fakten(db, a.id, von=(2025, 9), bis=(2025, 9))
    assert f.emob.quelle == QUELLE_NULL
    assert f.emob.ladung_kwh == 0.0 and f.emob.ladung_netz_kwh == 0.0
    assert f.emob.fahrverbrauch_kwh == 1364.0, "der Fahrverbrauch bleibt Fahrverbrauch"


async def test_monats_fakten_wallbox_in_betrieb_ohne_zeile(db):
    """„Wallbox in Betrieb" kommt aus der Investitionsliste, nicht aus der Existenz einer Zeile."""
    from backend.services.monats_fakten import lade_monats_fakten

    a, _wb, ea = await _johnny_anlage(db, mit_wallbox_zeile=False)
    imd = (await db.execute(select(InvestitionMonatsdaten).where(
        InvestitionMonatsdaten.investition_id == ea.id))).scalar_one()
    imd.verbrauch_daten = {"km_gefahren": 1500.0, "ladung_kwh": 400.0}
    flag_modified(imd, "verbrauch_daten")
    await db.commit()
    (f,) = await lade_monats_fakten(db, a.id, von=(2025, 9), bis=(2025, 9))
    assert f.emob.quelle == QUELLE_NULL and f.emob.ladung_kwh == 0.0


async def test_monats_fakten_dienstwagen_menge_unveraendert_und_gekennzeichnet(db):
    from backend.services.monats_fakten import lade_monats_fakten

    a, _wb, _ea = await _johnny_anlage(db, dienstwagen=True)
    (f,) = await lade_monats_fakten(db, a.id, von=(2025, 9), bis=(2025, 9))
    assert f.emob.dienstlich_ladung_netz_kwh == 1364.0, "wie bisher: Fahrverbrauch als Netz"
    assert f.emob.dienstlich_geschaetzt is True
    assert f.emob.km == 0.0, "km nur privat (unverändert)"


async def test_community_traegt_keine_geschaetzte_eauto_ladung(db):
    """Regel 6 / E3: die E-Auto-Felder der Community tragen nur Messwerte."""
    from backend.services.community_service import _monatswert
    from backend.services.monats_fakten import lade_monats_fakten

    a = Anlage(anlagenname="Schaetzfall", leistung_kwp=10.0)
    db.add(a)
    await db.flush()
    ea = Investition(anlage_id=a.id, typ="e-auto", bezeichnung="Auto",
                     anschaffungsdatum=date(2024, 1, 1), aktiv=True)
    pv = Investition(anlage_id=a.id, typ="pv-module", bezeichnung="Dach",
                     anschaffungsdatum=date(2024, 1, 1), aktiv=True, leistung_kwp=10.0)
    db.add_all([ea, pv])
    await db.flush()
    db.add(Monatsdaten(anlage_id=a.id, jahr=2025, monat=6, einspeisung_kwh=100.0,
                       netzbezug_kwh=200.0))
    db.add(InvestitionMonatsdaten(investition_id=pv.id, jahr=2025, monat=6,
                                  verbrauch_daten={"pv_erzeugung_kwh": 500.0}))
    db.add(InvestitionMonatsdaten(investition_id=ea.id, jahr=2025, monat=6,
                                  verbrauch_daten={"km_gefahren": 1000.0, "verbrauch_kwh": 180.0}))
    await db.commit()
    (f,) = await lade_monats_fakten(db, a.id, von=(2025, 6), bis=(2025, 6))
    assert f.emob.quelle == QUELLE_SCHAETZUNG and f.emob.ladung_kwh == 180.0, "in eedc unverändert"
    payload = _monatswert(f)
    assert payload is not None, "der Monat geht an die Community (Zählerzeile + PV)"
    assert "eauto_ladung_gesamt_kwh" not in payload
    assert "eauto_ladung_pv_kwh" not in payload


# ═════════════════════════════════════════════════════════════════════════════
# Regel 4 — 0 ist ein Wert bei der Heimladung (Monatsabschluss, Statistik-Import)
# ═════════════════════════════════════════════════════════════════════════════


def _vorschlaege(resp, inv_id: int, feld: str) -> list:
    for inv in resp.investitionen:
        if inv.id != inv_id:
            continue
        for f in inv.felder:
            if f.feld == feld:
                return [v if isinstance(v, dict) else v.model_dump() for v in f.vorschlaege]
    return []


async def _abschluss_anlage(db, *, mapping_wb: dict, mapping_ea: dict | None = None, mit_wallbox=True):
    a = Anlage(anlagenname="Abschluss", leistung_kwp=10.0, sensor_mapping={"basis": {}, "investitionen": {}})
    db.add(a)
    await db.flush()
    wb = None
    if mit_wallbox:
        wb = Investition(anlage_id=a.id, typ="wallbox", bezeichnung="Wallbox",
                         anschaffungsdatum=date(2024, 1, 1), aktiv=True)
        db.add(wb)
    ea = Investition(anlage_id=a.id, typ="e-auto", bezeichnung="Auto",
                     anschaffungsdatum=date(2024, 1, 1), aktiv=True)
    db.add(ea)
    await db.flush()
    if wb is not None:
        a.sensor_mapping["investitionen"][str(wb.id)] = {"felder": mapping_wb}
    if mapping_ea:
        a.sensor_mapping["investitionen"][str(ea.id)] = {"felder": mapping_ea}
    flag_modified(a, "sensor_mapping")
    await db.commit()
    return a, wb, ea


async def test_monatsabschluss_ha_null_mit_daten_wird_vorgeschlagen(db, monkeypatch):
    from backend.api.routes.monatsabschluss import views

    a, wb, _ea = await _abschluss_anlage(db, mapping_wb={
        "ladung_kwh": _sensor("sensor.wb"), "ladung_pv_kwh": _sensor("sensor.wb_pv"),
    })

    async def _ha(*_a, **_k):
        return {"sensor.wb": 0.0, "sensor.wb_pv": 0.0}

    monkeypatch.setattr(views, "lade_ha_statistik_werte", _ha)
    resp = await views.get_monatsabschluss(a.id, 2025, 9, db=db)
    ha = [v for v in _vorschlaege(resp, wb.id, "ladung_kwh") if v["quelle"] == "ha_statistics"]
    assert len(ha) == 1 and ha[0]["wert"] == 0.0
    assert ha[0]["beschreibung"] == views.NULL_VORSCHLAG_BESCHREIBUNG == "0 — kein Zuwachs"
    # Ein PV-Feld bekommt weiter keine 0 (eine 0 dort sperrte die Phase-5-Ableitung).
    assert not [v for v in _vorschlaege(resp, wb.id, "ladung_pv_kwh") if v["quelle"] == "ha_statistics"]


async def test_monatsabschluss_ha_ohne_daten_schlaegt_nichts_vor(db, monkeypatch):
    from backend.api.routes.monatsabschluss import views

    a, wb, _ea = await _abschluss_anlage(db, mapping_wb={"ladung_kwh": _sensor("sensor.wb")})

    async def _ha(*_a, **_k):
        return {}  # Sensor hat im Monat keine Statistik-Daten

    monkeypatch.setattr(views, "lade_ha_statistik_werte", _ha)
    resp = await views.get_monatsabschluss(a.id, 2025, 9, db=db)
    assert not [v for v in _vorschlaege(resp, wb.id, "ladung_kwh") if v["quelle"] == "ha_statistics"]


async def test_monatsabschluss_heim_netz_am_steckerlader_bekommt_0(db, monkeypatch):
    from backend.api.routes.monatsabschluss import views

    a, _wb, ea = await _abschluss_anlage(
        db, mapping_wb={}, mit_wallbox=False,
        mapping_ea={"ladung_netz_kwh": _sensor("sensor.ea_netz")},
    )

    async def _ha(*_a, **_k):
        return {"sensor.ea_netz": 0.0}

    monkeypatch.setattr(views, "lade_ha_statistik_werte", _ha)
    resp = await views.get_monatsabschluss(a.id, 2025, 9, db=db)
    ha = [v for v in _vorschlaege(resp, ea.id, "ladung_netz_kwh") if v["quelle"] == "ha_statistics"]
    assert [v["wert"] for v in ha] == [0.0]


async def test_monatsabschluss_mqtt_null_nur_bei_mengenfeld_mit_daten(db, monkeypatch):
    """MQTT: `mqtt_monats_deltas` liefert einen Key nur mit beidseitigem Stand — eine 0 heißt
    „Daten da, kein Zuwachs". Mengenfeld ⇒ Vorschlag 0; PV-Feld ⇒ keiner; ohne Daten ⇒ keiner."""
    from backend.api.routes.monatsabschluss import views
    import backend.services.mqtt_energy_history_service as hist

    a, wb, _ea = await _abschluss_anlage(db, mapping_wb={})
    fake_cache = SimpleNamespace(get_energy_data=lambda _aid: {
        f"inv/{wb.id}/ladung_kwh": 500.0, f"inv/{wb.id}/ladung_pv_kwh": 200.0,
    })
    monkeypatch.setattr(views, "get_mqtt_inbound_service", lambda: SimpleNamespace(cache=fake_cache))

    async def _deltas(*_a, **_k):
        return {f"inv/{wb.id}/ladung_kwh": 0.0, f"inv/{wb.id}/ladung_pv_kwh": 0.0}

    monkeypatch.setattr(hist, "mqtt_monats_deltas", _deltas)

    async def _ha(*_a, **_k):
        return {}

    monkeypatch.setattr(views, "lade_ha_statistik_werte", _ha)
    resp = await views.get_monatsabschluss(a.id, 2025, 9, db=db)
    mq = [v for v in _vorschlaege(resp, wb.id, "ladung_kwh") if v["quelle"] == "mqtt_inbound"]
    assert [v["wert"] for v in mq] == [0.0]
    assert mq[0]["beschreibung"] == "0 — kein Zuwachs"
    assert not [v for v in _vorschlaege(resp, wb.id, "ladung_pv_kwh") if v["quelle"] == "mqtt_inbound"]

    async def _keine(*_a, **_k):
        return {}

    monkeypatch.setattr(hist, "mqtt_monats_deltas", _keine)
    resp = await views.get_monatsabschluss(a.id, 2025, 9, db=db)
    assert not [v for v in _vorschlaege(resp, wb.id, "ladung_kwh") if v["quelle"] == "mqtt_inbound"]


class _FakeStats:
    is_available = True

    def __init__(self, werte):
        self._werte = werte

    def get_monatswerte(self, sensor_ids, jahr, monat):
        sens = [SimpleNamespace(sensor_id=s, differenz=self._werte[s]) for s in sensor_ids if s in self._werte]
        return SimpleNamespace(jahr=jahr, monat=monat, monat_name="Sep", sensoren=sens)


@pytest.mark.parametrize("ueberschreiben,erwartet", [(False, 0.0), (True, 50.0)])
async def test_statistik_import_laesst_eine_gespeicherte_0_stehen(db, monkeypatch, ueberschreiben, erwartet):
    from backend.api.routes.ha_statistics import ImportRequest, import_ha_statistics

    a, wb, _ea = await _abschluss_anlage(db, mapping_wb={"ladung_kwh": _sensor("sensor.wb")})
    db.add(InvestitionMonatsdaten(investition_id=wb.id, jahr=2025, monat=9,
                                  verbrauch_daten={"ladung_kwh": 0.0}))
    await db.commit()
    monkeypatch.setattr(
        "backend.api.routes.ha_statistics.get_ha_statistics_service",
        lambda: _FakeStats({"sensor.wb": 50.0}),
    )
    await import_ha_statistics(
        a.id, ImportRequest(monate=[{"jahr": 2025, "monat": 9}], ueberschreiben=ueberschreiben), db,
    )
    imd = (await db.execute(select(InvestitionMonatsdaten).where(
        InvestitionMonatsdaten.investition_id == wb.id))).scalar_one()
    await db.refresh(imd)
    assert imd.verbrauch_daten["ladung_kwh"] == erwartet


async def test_statistik_import_fuellt_eine_0_ausserhalb_der_heimladung_wie_bisher(db, monkeypatch):
    """E1 eng: bei allen anderen Feldern gilt die gespeicherte 0 weiter als leer."""
    from backend.api.routes.ha_statistics import ImportRequest, import_ha_statistics

    a, _wb, _ea = await _abschluss_anlage(db, mapping_wb={})
    sp = Investition(anlage_id=a.id, typ="speicher", bezeichnung="Akku",
                     anschaffungsdatum=date(2024, 1, 1), aktiv=True)
    db.add(sp)
    await db.flush()
    a.sensor_mapping["investitionen"][str(sp.id)] = {"felder": {"ladung_kwh": _sensor("sensor.sp")}}
    flag_modified(a, "sensor_mapping")
    db.add(InvestitionMonatsdaten(investition_id=sp.id, jahr=2025, monat=9,
                                  verbrauch_daten={"ladung_kwh": 0.0}))
    await db.commit()
    monkeypatch.setattr(
        "backend.api.routes.ha_statistics.get_ha_statistics_service",
        lambda: _FakeStats({"sensor.sp": 70.0}),
    )
    await import_ha_statistics(a.id, ImportRequest(monate=[{"jahr": 2025, "monat": 9}]), db)
    imd = (await db.execute(select(InvestitionMonatsdaten).where(
        InvestitionMonatsdaten.investition_id == sp.id))).scalar_one()
    await db.refresh(imd)
    assert imd.verbrauch_daten["ladung_kwh"] == 70.0


# ═════════════════════════════════════════════════════════════════════════════
# Regel 5 — Startroutine und einmalige Rückbenennung
# ═════════════════════════════════════════════════════════════════════════════


async def _rueckbenennungs_bestand(db):
    a = Anlage(anlagenname="Rueck", leistung_kwp=10.0)
    db.add(a)
    await db.flush()
    ea = Investition(anlage_id=a.id, typ="e-auto", bezeichnung="Privat",
                     anschaffungsdatum=date(2024, 1, 1), aktiv=True)
    dw = Investition(anlage_id=a.id, typ="e-auto", bezeichnung="Dienst",
                     anschaffungsdatum=date(2024, 1, 1), aktiv=True, parameter={"ist_dienstlich": True})
    wb = Investition(anlage_id=a.id, typ="wallbox", bezeichnung="WB",
                     anschaffungsdatum=date(2024, 1, 1), aktiv=True)
    db.add_all([ea, dw, wb])
    await db.flush()
    zeilen = {
        # (inv, monat, daten, provenance)
        "umgebucht": (ea, 1, {"ladung_kwh": 216.0, "km_gefahren": 900.0}, {}),
        "neu_erfasst": (ea, 2, {"ladung_kwh": 216.0, "verbrauch_kwh": 220.0},
                        {"verbrauch_daten.verbrauch_kwh": {"source": "manual:form"}}),
        "legacy": (ea, 3, {"ladung_kwh": 180.0},
                   {"verbrauch_daten.ladung_kwh": {"source": "legacy:unknown"}}),
        "echt": (ea, 4, {"ladung_kwh": 150.0},
                 {"verbrauch_daten.ladung_kwh": {"source": "external:ha_statistics"}}),
        "dienst": (dw, 1, {"ladung_kwh": 99.0}, {}),
        "wallbox": (wb, 1, {"ladung_kwh": 300.0}, {}),
    }
    ids = {}
    for name, (inv, monat, daten, prov) in zeilen.items():
        imd = InvestitionMonatsdaten(investition_id=inv.id, jahr=2026, monat=monat,
                                     verbrauch_daten=daten, source_provenance=prov)
        db.add(imd)
        await db.flush()
        ids[name] = imd.id
    await db.commit()
    return ids


async def _daten(db, imd_id):
    imd = await db.get(InvestitionMonatsdaten, imd_id)
    await db.refresh(imd)
    return imd.verbrauch_daten


async def test_rueckbenennung_alle_zweige_und_zweiter_lauf(db):
    from backend.services.migrations.migrate_eauto_fahrverbrauch_rueckbenennung import (
        migrate_eauto_fahrverbrauch_rueckbenennung as mig,
    )

    ids = await _rueckbenennungs_bestand(db)
    erg = await mig(db)
    assert erg == {"zurueckbenannt": 2, "entfernt": 1}
    assert await _daten(db, ids["umgebucht"]) == {"verbrauch_kwh": 216.0, "km_gefahren": 900.0}
    assert await _daten(db, ids["neu_erfasst"]) == {"verbrauch_kwh": 220.0}
    assert await _daten(db, ids["legacy"]) == {"ladung_kwh": 180.0}, "legacy:unknown bleibt (Grenze 09.05.)"
    assert await _daten(db, ids["echt"]) == {"ladung_kwh": 150.0}, "mit Herkunft bleibt"
    assert await _daten(db, ids["dienst"]) == {"verbrauch_kwh": 99.0}, "auch Dienstwagen"
    assert await _daten(db, ids["wallbox"]) == {"ladung_kwh": 300.0}, "Wallbox nie"
    # Zweiter Lauf: nichts mehr zu tun.
    assert await mig(db) == {"zurueckbenannt": 0, "entfernt": 0}


def test_startroutine_bucht_den_fahrverbrauch_nicht_mehr_um(tmp_path):
    """Regel 5: zweimal starten — der E-Auto-Verbrauch bleibt, die Wallbox wird weiter umbenannt."""
    import sqlite3
    from sqlalchemy import create_engine
    from backend.core.database import _migrate_verbrauch_daten_keys_v326

    pfad = tmp_path / "start.db"
    con = sqlite3.connect(pfad)
    con.executescript(
        "create table investitionen (id integer primary key, typ text);"
        "create table investition_monatsdaten (id integer primary key, investition_id int, verbrauch_daten text);"
        "insert into investitionen values (1, 'e-auto'), (2, 'wallbox');"
        "insert into investition_monatsdaten values (1, 1, '{\"verbrauch_kwh\": 216, \"ladung_kwh\": 0}');"
        "insert into investition_monatsdaten values (2, 2, '{\"verbrauch_kwh\": 300}');"
    )
    con.commit()
    con.close()
    engine = create_engine(f"sqlite:///{pfad}")
    for _ in range(2):
        with engine.begin() as conn:
            _migrate_verbrauch_daten_keys_v326(conn)
    with engine.begin() as conn:
        rows = dict(conn.execute(text("select id, verbrauch_daten from investition_monatsdaten")).all())
    assert json.loads(rows[1]) == {"verbrauch_kwh": 216, "ladung_kwh": 0}, "E-Auto unangetastet"
    assert json.loads(rows[2]) == {"ladung_kwh": 300}, "Wallbox wie bisher"


def test_rueckbenennung_laeuft_einmalig_nach_der_initial_provenance():
    """Die Grenze 09.05. hängt an der Reihenfolge: Stempel zuerst, dann die Rückbenennung."""
    quelle = (_BACKEND / "core/database.py").read_text()
    i_stempel = quelle.index('"etappe_3d_p3_initial_provenance_legacy_unknown"')
    i_rueck = quelle.index('"n555_eauto_fahrverbrauch_rueckbenennung"')
    assert i_stempel < i_rueck
    assert "_apply_once(\n            \"n555_eauto_fahrverbrauch_rueckbenennung\"" in quelle


# ═════════════════════════════════════════════════════════════════════════════
# Regel 6 — der Wächter: E-Auto-`verbrauch_kwh` als Menge nur in der einen Funktion
# ═════════════════════════════════════════════════════════════════════════════

#: Jede Funktion im Backend, die `verbrauch_kwh` aus Daten LIEST (`.get`, `[…]`, `_f(…)`,
#: Feldwahl), mit ihrer Klasse. Eine neue Lesestelle macht diesen Test rot, bis sie hier
#: klassifiziert ist — genau die Klasse, die N-555 hatte (neun Aufrufer, die still ersetzten).
N555_VERBRAUCH_LESESTELLEN: dict[str, str] = {
    # ── die eine Funktion (Regel 6): die Schätzung aus dem Fahrverbrauch ──
    "backend/services/eauto_wirtschaftlichkeit.py::entscheide_emob_heimladung": "die eine Funktion",
    "backend/services/eauto_wirtschaftlichkeit.py::dienstliche_ladung_der_zeile":
        "die eine Funktion, Dienstwagen (Stufe 1 unverändert)",
    # ── Fahrverbrauch als FAHRVERBRAUCH: kWh/100 km, PHEV-Anteil, CO₂ Strommix ──
    "backend/core/berechnungen/imd_monatsaggregat.py::imd_typ_beitrag": "Fahrverbrauch → EmobFakten.fahrverbrauch_kwh",
    "backend/api/routes/aktueller_monat/tkonto.py::_baue_investition_financial": "PHEV (fahrverbrauch_kwh)",
    "backend/api/routes/aussichten/finanz_rueckblick.py::alternativkosten_rueckblick": "PHEV (fahrverbrauch_kwh)",
    "backend/api/routes/ha_export/anlage_komponenten.py::alternativkosten_und_co2": "PHEV (fahrverbrauch_kwh)",
    "backend/api/routes/ha_export/investition_sensoren.py::calculate_investition_sensors":
        "kWh/100-km-Sensor + PHEV",
    "backend/api/routes/investitionen/dashboard_eauto.py::get_eauto_dashboard": "kWh/100 km, PHEV, CO₂ Strommix",
    "backend/services/daten_checker/emob.py::_check_phev_anteil_unbestimmt": "PHEV-Checker",
    # ── Tag und Stunde: die eine Auswahl (Regel 6) ──
    "backend/services/snapshot/komponenten_beitraege.py::eauto_heimlade_felder_nach_quelle":
        "Tages-/Stunden-Schätzung nur ohne Heimlade-Quelle",
    "backend/services/snapshot/keys.py::_categorize_counter": "Kategorie (die Wahl sitzt in der Auswahl)",
    # ── Vorprüfung: lädt die Tages-Quote für die Schätzung ──
    "backend/services/emob_ladeanteil.py::_hat_schaetzbaren_fahrverbrauch": "nur Anwesenheit, keine Menge",
    # N-555 Stufe 2 (S2-4): dieselbe Vorprüfung, je Zeile.
    "backend/services/emob_ladeanteil.py::braucht_tages_quote": "nur Anwesenheit, keine Menge",
    # ── Schreib-, Import- und Migrationspfade ──
    "backend/api/routes/import_export/helpers.py::_import_investition_monatsdaten_legacy": "CSV-Import (schreibt)",
    "backend/services/migrations/migrate_eauto_fahrverbrauch_rueckbenennung.py::migrate_eauto_fahrverbrauch_rueckbenennung":
        "Regel 5 (schreibt)",
    # ── anderer Gerätetyp ──
    "backend/core/field_definitions/wp_strom.py::wp_strom_aufteilung": "Wärmepumpe, nicht E-Auto",
}


def _verbrauch_lesestellen() -> dict[str, list[int]]:
    treffer: dict[str, list[int]] = {}
    for p in sorted(_BACKEND.rglob("*.py")):
        rel = "backend/" + str(p.relative_to(_BACKEND))
        if rel.startswith("backend/tests/") or "/venv/" in rel:
            continue
        baum = ast.parse(p.read_text(encoding="utf-8"))
        eltern = {kind: knoten for knoten in ast.walk(baum) for kind in ast.iter_child_nodes(knoten)}
        for knoten in ast.walk(baum):
            if not (isinstance(knoten, ast.Constant) and knoten.value == "verbrauch_kwh"):
                continue
            par = eltern.get(knoten)
            liest = (
                (isinstance(par, ast.Call) and knoten in par.args)
                or isinstance(par, ast.Subscript)
                or isinstance(par, ast.Compare)
                or (isinstance(par, (ast.Tuple, ast.List, ast.Set)) and isinstance(eltern.get(par), ast.Compare))
            )
            if not liest:
                continue
            fn, name = knoten, "<modul>"
            while fn in eltern:
                fn = eltern[fn]
                if isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    name = fn.name
                    break
            treffer.setdefault(f"{rel}::{name}", []).append(knoten.lineno)
    return treffer


def test_waechter_fahrverbrauch_nur_an_klassifizierten_stellen():
    """Baumweit (Muster `test_wurzelmuster_konformitaet.py`), Baseline = die Liste oben."""
    ist = _verbrauch_lesestellen()
    neu = sorted(set(ist) - set(N555_VERBRAUCH_LESESTELLEN))
    assert not neu, (
        f"`verbrauch_kwh` wird an neuen Stellen gelesen: {neu}. Am E-Auto ist das der "
        "FAHRVERBRAUCH, keine Ladung — als Heimladung darf er nur über "
        "`eauto_wirtschaftlichkeit.entscheide_emob_heimladung` kommen (Konzept Regel 1 + 6). "
        "Liest die Stelle ihn als Fahrverbrauch (kWh/100 km, PHEV, CO₂) oder gehört sie zu "
        "einem anderen Typ, trag sie mit Grund in N555_VERBRAUCH_LESESTELLEN ein."
    )
    veraltet = sorted(set(N555_VERBRAUCH_LESESTELLEN) - set(ist))
    assert not veraltet, f"Klassifizierte Stellen gibt es nicht mehr: {veraltet}"


def test_lese_hilfen_kennen_den_fahrverbrauch_nicht():
    """`reader.py`: `get_eauto_ladung_kwh` und `get_emob_pv_netz_kwh` lesen kein `verbrauch_kwh`."""
    baum = ast.parse((_BACKEND / "core/field_definitions/reader.py").read_text(encoding="utf-8"))
    for fn in ast.walk(baum):
        if isinstance(fn, ast.FunctionDef) and fn.name in ("get_eauto_ladung_kwh", "get_emob_pv_netz_kwh"):
            koerper = fn.body[1:] if isinstance(fn.body[0], ast.Expr) else fn.body  # ohne Docstring
            konstanten = {
                k.value for teil in koerper for k in ast.walk(teil) if isinstance(k, ast.Constant)
            }
            assert "verbrauch_kwh" not in konstanten, fn.name


# ─── Regel 6: Tag und Stunde ─────────────────────────────────────────────────


def test_tag_auswahl_nach_quelle():
    from backend.services.snapshot.komponenten_beitraege import eauto_heimlade_felder_nach_quelle as w

    def q(*felder):
        return lambda f: f in felder

    assert w(q("ladung_pv_kwh", "ladung_netz_kwh", "ladung_kwh", "verbrauch_kwh")) == (
        "ladung_pv_kwh", "ladung_netz_kwh")
    assert w(q("ladung_netz_kwh", "verbrauch_kwh")) == ("ladung_netz_kwh",)
    assert w(q("ladung_kwh", "ladung_pv_kwh", "verbrauch_kwh")) == ("ladung_kwh",)
    assert w(q("ladung_pv_kwh", "verbrauch_kwh")) == ("ladung_pv_kwh",)
    assert w(q("verbrauch_kwh")) == ("verbrauch_kwh",)
    assert w(q()) == ()


def test_stunde_kennt_die_wallbox_regel():
    """„Verbrauch" neben einer Wallbox mit Zähler ist in KEINER Stunde Ladung — ohne Wallbox schon."""
    from backend.services.snapshot.komponenten_beitraege import investition_hourly_eintraege

    inv = SimpleNamespace(id=1, typ="e-auto", parameter={}, parent_investition_id=None)
    data = {"felder": {"verbrauch_kwh": _sensor("sensor.ea_v")}}
    assert investition_hourly_eintraege(inv, data, wallbox_deckt_ladung=True) == []
    ohne = investition_hourly_eintraege(inv, data)
    assert [(e.feld, e.kategorie) for e in ohne] == [("verbrauch_kwh", "verbrauch_eauto")]


def test_stunde_waehlt_ueber_ha_und_mqtt_gemeinsam():
    """Heim-PV/-Netz über HA, Verbrauch über MQTT: der MQTT-Durchgang darf den Fahrverbrauch
    nicht zusätzlich nehmen (gemeinsame Auswahl)."""
    from backend.services.snapshot.komponenten_beitraege import mqtt_hourly_eintraege

    inv = SimpleNamespace(id=1, typ="e-auto", parameter={}, parent_investition_id=None)
    alle = {"ladung_pv_kwh", "ladung_netz_kwh", "verbrauch_kwh"}
    eintraege = mqtt_hourly_eintraege(
        ["inv:1:verbrauch_kwh"], {"1": inv}, {},
        auswahl_je_inv=lambda _id: (lambda f: f in alle),
    )
    assert eintraege == []


def test_wallbox_zaehlt_am_tag_nur_in_betrieb():
    from backend.services.snapshot.komponenten_beitraege import wallbox_deckt_ladung_ab

    wb = Investition(id=2, anlage_id=1, typ="wallbox", bezeichnung="WB",
                     anschaffungsdatum=date(2026, 6, 1), aktiv=True)
    sm = {"investitionen": {"2": {"felder": {"ladung_kwh": _sensor("sensor.wb")}}}}
    assert wallbox_deckt_ladung_ab([wb], sm, datum=date(2026, 5, 22)) is False
    assert wallbox_deckt_ladung_ab([wb], sm, datum=date(2026, 6, 22)) is True


@pytest.mark.parametrize("setup_name,erwartet", [
    ("wallbox_und_eauto_verbrauch", {"wallbox_2": 8.0}),
    ("eauto_pv_netz_und_verbrauch", {"eauto_1": 12.0}),
    ("wallbox_nicht_in_betrieb_und_eauto", {"wallbox_2": 0.0, "eauto_1": 34.5}),
])
async def test_tageswerte_der_neuen_konstellationen(setup_name, erwartet):
    """Die Tageszahl selbst (die Σ-Stunden-=-Tag-Proben laufen über `SETUPS` in
    `test_aggregator_symmetrie.py`/`test_hourly_kategorie_symmetrie.py`)."""
    from unittest.mock import patch

    from backend.services.snapshot.lts_aggregator import get_komponenten_tageskwh_lts
    from backend.tests.test_aggregator_symmetrie import SETUPS, _build_mock_ha_svc, _make_anlage

    sm, invs, deltas, _sk = SETUPS[setup_name]()
    with patch(
        "backend.services.snapshot.lts_aggregator.get_ha_statistics_service",
        return_value=_build_mock_ha_svc(deltas),
    ):
        tag = await get_komponenten_tageskwh_lts(_make_anlage(sm), invs, date(2026, 5, 22))
    assert {k: round(v, 3) for k, v in tag.items()} == erwartet


# ═════════════════════════════════════════════════════════════════════════════
# Regel 10 (N-557) — „Ladung gesamt" und kWh/100 km in allen Sichten
# ═════════════════════════════════════════════════════════════════════════════


async def _jahres_anlage(db):
    """Ein Jahr mit Verbrauchssensor erst ab Juli, Wallbox-Heimladung und externer Ladung."""
    a = Anlage(anlagenname="Jahr", leistung_kwp=10.0)
    db.add(a)
    await db.flush()
    wb = Investition(anlage_id=a.id, typ="wallbox", bezeichnung="WB",
                     anschaffungsdatum=date(2024, 1, 1), aktiv=True)
    ea = Investition(anlage_id=a.id, typ="e-auto", bezeichnung="Auto",
                     anschaffungsdatum=date(2024, 1, 1), aktiv=True)
    db.add_all([wb, ea])
    await db.flush()
    for monat in range(1, 13):
        db.add(Monatsdaten(anlage_id=a.id, jahr=2025, monat=monat, einspeisung_kwh=100.0,
                           netzbezug_kwh=200.0, pv_erzeugung_kwh=500.0))
        db.add(InvestitionMonatsdaten(investition_id=wb.id, jahr=2025, monat=monat,
                                      verbrauch_daten={"ladung_kwh": 250.0, "ladung_pv_kwh": 100.0}))
        auto = {"km_gefahren": 1500.0, "ladung_extern_kwh": 50.0, "ladung_extern_euro": 25.0}
        if monat >= 7:
            auto["verbrauch_kwh"] = 270.0
        db.add(InvestitionMonatsdaten(investition_id=ea.id, jahr=2025, monat=monat, verbrauch_daten=auto))
    await db.commit()
    return a


async def test_ladung_gesamt_und_monatsbasis_in_cockpit_monat(db):
    from backend.api.routes.aktueller_monat import get_aktueller_monat

    a = await _jahres_anlage(db)
    maerz = await get_aktueller_monat(anlage_id=a.id, jahr=2025, monat=3, db=db)
    assert maerz.emob_ladung_kwh == 250.0, "Heimladung bleibt Heimladung"
    assert maerz.emob_ladung_gesamt_kwh == 300.0, "Ladung gesamt = Heim + Extern"
    assert maerz.emob_verbrauch_quelle == "ladung"
    assert maerz.emob_verbrauch_100km == pytest.approx(20.0), "Näherung aus Heim + Extern"
    assert maerz.emob_verbrauch_basis_kwh == 300.0
    august = await get_aktueller_monat(anlage_id=a.id, jahr=2025, monat=8, db=db)
    assert august.emob_verbrauch_quelle == "gemessen"
    assert august.emob_verbrauch_100km == pytest.approx(18.0)
    assert august.emob_verbrauch_basis_kwh == 270.0


async def test_symmetrie_kwh_pro_100km_in_uebersicht_hub_auswertungen_und_jahr(db):
    """Regel 10: dieselbe Anlage, dieselbe Jahres-kWh/100 km — Σ Monatswerte ÷ Σ km,
    „gemessen" nur, wenn jeder Monat mit km gemessen ist."""
    from backend.api.routes.aktueller_monat import get_aktueller_monat
    from backend.api.routes.cockpit.komponenten import get_komponenten_zeitreihe
    from backend.api.routes.cockpit.uebersicht import get_cockpit_uebersicht
    from backend.api.routes.investitionen import get_eauto_dashboard
    from backend.core.berechnungen import EffizienzWert, eauto_effizienz_zeitraum

    a = await _jahres_anlage(db)
    erwartet = (6 * 300.0 + 6 * 270.0) / (12 * 1500.0) * 100  # 19,0

    ueb = await get_cockpit_uebersicht(anlage_id=a.id, jahr=2025, db=db)
    hub = (await get_eauto_dashboard(anlage_id=a.id, strompreis_cent=30.0, db=db))[0].zusammenfassung
    kz = await get_komponenten_zeitreihe(anlage_id=a.id, jahr=2025, db=db)
    monate = [await get_aktueller_monat(anlage_id=a.id, jahr=2025, monat=m, db=db) for m in range(1, 13)]
    jahr = eauto_effizienz_zeitraum(
        EffizienzWert(m.emob_verbrauch_100km, m.emob_verbrauch_quelle, m.emob_verbrauch_basis_kwh,
                      m.emob_km or 0.0)
        for m in monate
    )

    assert ueb.emob_verbrauch_100km == pytest.approx(erwartet, abs=0.05)
    assert hub["durchschnitt_verbrauch_kwh_100km"] == pytest.approx(erwartet, abs=0.05)
    assert kz.emob_verbrauch_100km_gesamt == pytest.approx(erwartet, abs=0.05)
    assert jahr.wert == pytest.approx(erwartet, abs=0.05)
    for quelle in (ueb.emob_verbrauch_quelle, hub["verbrauch_quelle"], kz.emob_verbrauch_quelle_gesamt,
                   jahr.quelle):
        assert quelle == "ladung", "nicht jeder Monat mit km ist gemessen"


async def test_uebersicht_ist_die_summe_der_monate(db):
    """Regel 1: ein Zeitraum ist die Summe seiner Monate — Wallbox ab Juli, Schätzung davor."""
    from backend.api.routes.cockpit.uebersicht import get_cockpit_uebersicht

    a = Anlage(anlagenname="Gemischt", leistung_kwp=10.0)
    db.add(a)
    await db.flush()
    wb = Investition(anlage_id=a.id, typ="wallbox", bezeichnung="WB",
                     anschaffungsdatum=date(2025, 7, 1), aktiv=True)
    ea = Investition(anlage_id=a.id, typ="e-auto", bezeichnung="Auto",
                     anschaffungsdatum=date(2025, 1, 1), aktiv=True)
    db.add_all([wb, ea])
    await db.flush()
    for monat in range(1, 13):
        db.add(Monatsdaten(anlage_id=a.id, jahr=2025, monat=monat, einspeisung_kwh=100.0,
                           netzbezug_kwh=200.0, pv_erzeugung_kwh=500.0))
        db.add(InvestitionMonatsdaten(investition_id=ea.id, jahr=2025, monat=monat,
                                      verbrauch_daten={"km_gefahren": 1000.0, "verbrauch_kwh": 170.0}))
        if monat >= 7:
            db.add(InvestitionMonatsdaten(investition_id=wb.id, jahr=2025, monat=monat,
                                          verbrauch_daten={"ladung_kwh": 200.0}))
    await db.commit()
    ueb = await get_cockpit_uebersicht(anlage_id=a.id, jahr=2025, db=db)
    assert ueb.emob_ladung_kwh == pytest.approx(6 * 170.0 + 6 * 200.0, abs=0.5)


async def test_snapshot_stunde_kennt_die_wallbox_regel():
    """Σ Stunden = Tag auch im **Snapshot**-Stundenpfad (MQTT/Standalone, HA-Snapshots):
    neben einer Wallbox mit Zähler zählt der Fahrverbrauch in keiner Stunde (Sprengsatz S-9c
    blieb über die Bestandsprobe stumm — sie fährt nur das Doppelmapping ohne Wallbox)."""
    from unittest.mock import patch

    from backend.services.snapshot.aggregator import (
        get_hourly_kwh_by_category,
        get_komponenten_tageskwh,
    )
    from backend.tests.test_aggregator_symmetrie import SETUPS, _make_anlage
    from backend.tests.test_hourly_kategorie_symmetrie import (
        _build_hourly_snapshot_lookup,
        _empty_mqtt_db,
        _fold_daily_to_flow,
        _sum_hourly_flow,
    )

    sm, invs, deltas, sk_map = SETUPS["wallbox_und_eauto_verbrauch"]()
    anlage = _make_anlage(sm)
    datum = date(2026, 5, 22)
    db = await _empty_mqtt_db()
    with patch(
        "backend.services.snapshot.aggregator.get_snapshot",
        side_effect=_build_hourly_snapshot_lookup(deltas, sk_map, datum),
    ):
        stunden = await get_hourly_kwh_by_category(db=db, anlage=anlage, investitionen_by_id=invs, datum=datum)
        tag = await get_komponenten_tageskwh(db=db, anlage=anlage, investitionen_by_id=invs, datum=datum)
    assert _sum_hourly_flow(stunden)["wallbox"] == pytest.approx(8.0, abs=0.01)
    assert _fold_daily_to_flow(tag, invs)["wallbox"] == pytest.approx(8.0, abs=0.01)


# ─── Regel 1: der LAUFENDE Monat in allen Zeitraum-Sichten (gestellte Uhr) ───


async def _johnny_laufend(db, monkeypatch):
    """Johnny im laufenden Monat (Uhr gestellt auf 2025-09): Wallbox mit HA-Sensor, noch ohne
    Zeile, am Auto nur „Verbrauch"."""
    import backend.services.emob_heimlade_quellen as quellen_modul

    monkeypatch.setattr(quellen_modul, "laufender_monat", lambda: (2025, 9))
    a, wb, ea = await _johnny_anlage(db, mit_wallbox_zeile=False)
    a.sensor_mapping = {"basis": {}, "investitionen": {
        str(wb.id): {"felder": {"ladung_kwh": _sensor("sensor.wallbox")}}}}
    await db.commit()
    return a


async def test_laufender_monat_monats_fakten_fragen_die_quelle(db, monkeypatch):
    from backend.services.monats_fakten import lade_monats_fakten

    a = await _johnny_laufend(db, monkeypatch)
    (f,) = await lade_monats_fakten(db, a.id, von=(2025, 9), bis=(2025, 9))
    assert f.emob.quelle == QUELLE_NULL and f.emob.ladung_kwh == 0.0


async def test_laufender_monat_ohne_quelle_bleibt_die_schaetzung_in_den_fakten(db, monkeypatch):
    """Gegenprobe: ohne zugeordnete Quelle ist nichts bekannt ⇒ Schätzung."""
    import backend.services.emob_heimlade_quellen as quellen_modul
    from backend.services.monats_fakten import lade_monats_fakten

    monkeypatch.setattr(quellen_modul, "laufender_monat", lambda: (2025, 9))
    a, _wb, _ea = await _johnny_anlage(db, mit_wallbox_zeile=False)
    (f,) = await lade_monats_fakten(db, a.id, von=(2025, 9), bis=(2025, 9))
    assert f.emob.quelle == QUELLE_SCHAETZUNG and f.emob.ladung_kwh == 1364.0


async def test_laufender_monat_hubs_aussichten_und_ha_export_folgen(db, monkeypatch):
    """Die Sichten, die die Zeilen selbst laden, entscheiden den laufenden Monat genauso."""
    from backend.api.routes.investitionen import get_eauto_dashboard, get_wallbox_dashboard
    from backend.api.routes.ha_export.emob import _load_emob_pool_ctx
    from backend.services.eauto_wirtschaftlichkeit import emob_heimladung_im_monat

    a = await _johnny_laufend(db, monkeypatch)
    hub = (await get_eauto_dashboard(anlage_id=a.id, strompreis_cent=30.0, db=db))[0].zusammenfassung
    assert hub["ladung_heim_kwh"] == 0.0
    wbh = (await get_wallbox_dashboard(anlage_id=a.id, strompreis_cent=30.0, db=db))[0].zusammenfassung
    assert wbh["gesamt_heim_ladung_kwh"] == 0.0
    invs = (await db.execute(select(Investition).where(Investition.anlage_id == a.id))).scalars().all()
    ctx = await _load_emob_pool_ctx(db, invs)
    ea = next(i for i in invs if i.typ == "e-auto")
    assert emob_heimladung_im_monat(ctx, ea.id, 1500.0, 2025, 9, dict(JOHNNY)) == (0.0, 0.0)


# ═════════════════════════════════════════════════════════════════════════════
# Folgeauftrag 25.09. (§10 des Berichts): F-3 · F-5 · Nebenfunde 1–3
# ═════════════════════════════════════════════════════════════════════════════


async def test_f3_ha_sensor_kwh_pro_100km_folgt_der_app_regel(db):
    """F-3: `e_auto_verbrauch_kwh_100km` = Σ Monatswerte ÷ Σ km, Quelle als Attribut —
    dieselbe Zahl wie Übersicht/Hub/Auswertungen/Jahr (19,0 „ladung")."""
    from backend.api.routes.ha_export import calculate_investition_sensors
    from backend.api.routes.ha_export.emob import _load_emob_pool_ctx

    a = await _jahres_anlage(db)
    invs = (await db.execute(select(Investition).where(Investition.anlage_id == a.id))).scalars().all()
    ea = next(i for i in invs if i.typ == "e-auto")
    ctx = await _load_emob_pool_ctx(db, invs)
    werte = await calculate_investition_sensors(db, ea, None, emob_ctx=ctx)
    sv = next(v for v in werte if v.definition.key == "e_auto_verbrauch_kwh_100km")
    assert sv.value == pytest.approx(19.0)
    assert sv.zusatz_attribute == {"quelle": "ladung"}


async def test_f5_hub_extern_nach_der_topf_regel(db):
    """F-5: im Wallbox-Fall trägt der Hub das Extern des Autos (höhere Kosten gewinnen),
    nicht den Extern-Anteil der Wallbox (die keins hat)."""
    from backend.api.routes.investitionen import get_eauto_dashboard

    a = await _jahres_anlage(db)
    z = (await get_eauto_dashboard(anlage_id=a.id, strompreis_cent=30.0, db=db))[0].zusammenfassung
    assert z["ladung_extern_kwh"] == pytest.approx(600.0)
    assert z["strom_kosten_extern_euro"] == pytest.approx(300.0)
    assert z["gesamt_ladung_kwh"] == pytest.approx(3600.0)


def test_f5_tkonto_zeile_zieht_das_extern_des_autos_ab():
    """F-5, dieselbe Klasse im T-Konto: Wallbox-Fall, Extern nur am Auto ⇒ 25 € Kosten."""
    from backend.api.routes.aktueller_monat.tkonto import _baue_investition_financial
    from backend.services.eauto_wirtschaftlichkeit import compute_emob_pool_attribution

    inv = Investition(id=7, anlage_id=1, typ="e-auto", bezeichnung="Auto",
                      anschaffungsdatum=date(2024, 1, 1), aktiv=True, parameter={})
    attr = compute_emob_pool_attribution(
        eauto_imd_data=[{"km_gefahren": 1500.0}],
        wallbox_imd_data=[{"ladung_kwh": 250.0, "ladung_pv_kwh": 100.0}],
    )
    kw = dict(netz_p=30.0, einsp_p=8.0, wp_p=30.0, wb_p=30.0, monats_gaspreis=None,
              monats_benzinpreis=1.8, emob_pool_attr=attr)
    mit = _baue_investition_financial(inv, {"km_gefahren": 1500.0, "ladung_extern_kwh": 50.0,
                                            "ladung_extern_euro": 25.0}, **kw)
    ohne = _baue_investition_financial(inv, {"km_gefahren": 1500.0}, **kw)
    assert ohne.ersparnis_euro - mit.ersparnis_euro == pytest.approx(25.0)


def test_f5_topf_und_leser_nutzen_dieselbe_extern_regel():
    from backend.services.eauto_wirtschaftlichkeit import waehle_extern_paar

    assert waehle_extern_paar(0.0, 0.0, 50.0, 25.0) == (50.0, 25.0)
    assert waehle_extern_paar(30.0, 30.0, 50.0, 25.0) == (30.0, 30.0)
    assert waehle_extern_paar(10.0, 5.0, 20.0, 5.0) == (10.0, 5.0), "Gleichstand: Wallbox"
    e = entscheide_emob_heimladung(
        eauto_je_inv={7: {"ladung_extern_kwh": 50.0, "ladung_extern_euro": 25.0}},
        wallbox_zeilen=[{"ladung_kwh": 250.0}],
    )
    assert (e.pool.extern_kwh, e.pool.extern_euro) == (50.0, 25.0)


async def test_nebenfund1_jahresbericht_co2_emob_gleich_cockpit(db):
    """Die E-Mob-CO₂ im Jahresbericht ist dieselbe Zahl wie im Cockpit-CO₂-Block
    (Σ der Monatswerte von `/cockpit/nachhaltigkeit` im Berichtsjahr)."""
    from backend.api.routes.cockpit.nachhaltigkeit import get_nachhaltigkeit
    from backend.services.pdf.builders.jahresbericht import build_jahresbericht_context

    a = await _jahres_anlage(db)
    ctx = await build_jahresbericht_context(db, a.id, 2025)
    cockpit = await get_nachhaltigkeit(anlage_id=a.id, db=db)
    summe = sum(m.co2_emob_kg for m in cockpit.monatswerte if m.jahr == 2025)
    assert ctx["co2"]["emob_kg"] == pytest.approx(summe, abs=0.1 * 12)
    assert ctx["co2"]["emob_kg"] != pytest.approx(18000 * 0.12), "nicht mehr km × 0,12"


async def test_nebenfund2_emob_ersparnis_berechnung_aus_dem_backend(db):
    """Der Rechenweg der eMob-Ersparnis kommt mit den eingesetzten Werten aus dem Backend."""
    from backend.api.routes.aktueller_monat import get_aktueller_monat

    from backend.models.strompreis import Strompreis

    a = await _jahres_anlage(db)
    db.add(Strompreis(anlage_id=a.id, netzbezug_arbeitspreis_cent_kwh=30.0,
                      einspeiseverguetung_cent_kwh=8.0, gueltig_ab=date(2020, 1, 1)))
    await db.commit()
    r = await get_aktueller_monat(anlage_id=a.id, jahr=2025, monat=3, db=db)
    assert r.emob_ersparnis_euro is not None
    assert r.emob_ersparnis_berechnung and "L/100 km" in r.emob_ersparnis_berechnung
    assert "7/100" not in r.emob_ersparnis_berechnung


# ═════════════════════════════════════════════════════════════════════════════
# Zweiter Folgeauftrag 25.09. (§11): HA-Ersparnis mit Extern · deutsches Zahlenformat
# ═════════════════════════════════════════════════════════════════════════════


async def test_s11_ha_ersparnis_gleich_hub_mit_externen_kosten(db):
    """Symmetrie: die Ersparnis im HA-Sensor (Fahrzeug und Anlage) gleicht der im Hub —
    beide ziehen die externen Ladekosten nach der Topf-Regel ab."""
    from backend.api.routes.ha_export import calculate_investition_sensors
    from backend.api.routes.ha_export.emob import _load_emob_pool_ctx
    from backend.api.routes.investitionen import get_eauto_dashboard

    a = await _jahres_anlage(db)
    invs = (await db.execute(select(Investition).where(Investition.anlage_id == a.id))).scalars().all()
    ea = next(i for i in invs if i.typ == "e-auto")
    hub = (await get_eauto_dashboard(anlage_id=a.id, strompreis_cent=None, db=db))[0].zusammenfassung
    ctx = await _load_emob_pool_ctx(db, invs)
    werte = await calculate_investition_sensors(db, ea, None, emob_ctx=ctx)
    sensor = next(v for v in werte if v.definition.key == "e_auto_ersparnis_vs_benzin_euro")
    assert hub["strom_kosten_extern_euro"] == pytest.approx(300.0)
    assert sensor.value == pytest.approx(hub["ersparnis_vs_benzin_euro"], abs=0.01)
    # Der Rechenweg nennt die externen Kosten getrennt, nicht unter dem Heimpreis.
    assert "- 300,00 (extern geladen)" in (sensor.berechnung or ""), sensor.berechnung


async def test_s11_ha_anlagen_sensor_zieht_extern_ab(db):
    """Der Anlagen-Posten „E-Auto …" der Jahres-Ersparnis trägt die externen Kosten —
    die Anlage trägt nur diesen einen Posten über zwölf Monate, `jahres_ersparnis_euro`
    ist damit genau die Hub-Ersparnis."""
    from backend.api.routes.ha_export import calculate_anlage_sensors
    from backend.api.routes.investitionen import get_eauto_dashboard
    a = await _jahres_anlage(db)
    hub = (await get_eauto_dashboard(anlage_id=a.id, strompreis_cent=None, db=db))[0].zusammenfassung
    werte = await calculate_anlage_sensors(db, a, skip_jitter=True)
    wert = next(v for v in werte if v.definition.key == "jahres_ersparnis_euro")
    assert "[E-Auto Auto]" in (wert.berechnung or ""), wert.berechnung
    assert wert.value == pytest.approx(hub["ersparnis_vs_benzin_euro"], abs=0.01)


async def test_s11_ha_ersparnis_extern_am_wallbox_topf(db):
    """Topf-Regel: steht die externe Ladung am Wallbox-Topf (nicht am Auto), zieht der
    HA-Sensor sie genauso ab wie der Hub — über `waehle_extern_paar`, keine dritte Kopie."""
    from backend.api.routes.ha_export import calculate_investition_sensors
    from backend.api.routes.ha_export.emob import _load_emob_pool_ctx
    from backend.api.routes.investitionen import get_eauto_dashboard

    a = Anlage(anlagenname="Topf", leistung_kwp=10.0)
    db.add(a)
    await db.flush()
    wb = Investition(anlage_id=a.id, typ="wallbox", bezeichnung="WB",
                     anschaffungsdatum=date(2024, 1, 1), aktiv=True)
    ea = Investition(anlage_id=a.id, typ="e-auto", bezeichnung="Auto",
                     anschaffungsdatum=date(2024, 1, 1), aktiv=True)
    db.add_all([wb, ea])
    await db.flush()
    for monat in range(1, 13):
        db.add(Monatsdaten(anlage_id=a.id, jahr=2025, monat=monat, einspeisung_kwh=100.0,
                           netzbezug_kwh=200.0, pv_erzeugung_kwh=500.0))
        db.add(InvestitionMonatsdaten(investition_id=wb.id, jahr=2025, monat=monat, verbrauch_daten={
            "ladung_kwh": 250.0, "ladung_pv_kwh": 100.0,
            "ladung_extern_kwh": 40.0, "ladung_extern_euro": 20.0}))
        db.add(InvestitionMonatsdaten(investition_id=ea.id, jahr=2025, monat=monat,
                                      verbrauch_daten={"km_gefahren": 1500.0}))
    await db.commit()
    invs = [wb, ea]
    hub = (await get_eauto_dashboard(anlage_id=a.id, strompreis_cent=None, db=db))[0].zusammenfassung
    ctx = await _load_emob_pool_ctx(db, invs)
    werte = await calculate_investition_sensors(db, ea, None, emob_ctx=ctx)
    sensor = next(v for v in werte if v.definition.key == "e_auto_ersparnis_vs_benzin_euro")
    assert hub["strom_kosten_extern_euro"] == pytest.approx(240.0)
    assert sensor.value == pytest.approx(hub["ersparnis_vs_benzin_euro"], abs=0.01)


def test_s11_rechenweg_in_deutscher_schreibweise():
    """Der Rechenweg der Fahrzeugzeile: „1.500 km × 7,5 L/100 km × 1,65 €"."""
    from backend.api.routes.aktueller_monat.tkonto import _baue_investition_financial
    from backend.services.eauto_wirtschaftlichkeit import compute_emob_pool_attribution

    inv = Investition(id=7, anlage_id=1, typ="e-auto", bezeichnung="Auto",
                      anschaffungsdatum=date(2024, 1, 1), aktiv=True, parameter={})
    attr = compute_emob_pool_attribution(eauto_imd_data=[], wallbox_imd_data=[])
    d = _baue_investition_financial(
        inv, {"km_gefahren": 1500.0, "ladung_pv_kwh": 20.0, "ladung_netz_kwh": 30.0},
        netz_p=30.0, einsp_p=8.0, wp_p=30.0, wb_p=30.0, monats_gaspreis=None,
        monats_benzinpreis=1.65, emob_pool_attr=attr,
    )
    assert d.berechnung == "1.500 km × 7,5 L/100 km × 1,65 €"


# ═════════════════════════════════════════════════════════════════════════════
# Dritter Folgeauftrag 25.09. (§12): Aussichten mit externen Ladekosten
# ═════════════════════════════════════════════════════════════════════════════


async def _s12_topf_anlage(db):
    """Extern am Wallbox-Topf, Auto ohne eigenes Extern-Paar (Topf-Regel)."""
    a = Anlage(anlagenname="Topf", leistung_kwp=10.0)
    db.add(a)
    await db.flush()
    wb = Investition(anlage_id=a.id, typ="wallbox", bezeichnung="WB",
                     anschaffungsdatum=date(2024, 1, 1), aktiv=True)
    ea = Investition(anlage_id=a.id, typ="e-auto", bezeichnung="Auto",
                     anschaffungsdatum=date(2024, 1, 1), aktiv=True)
    db.add_all([wb, ea])
    await db.flush()
    for monat in range(1, 13):
        db.add(Monatsdaten(anlage_id=a.id, jahr=2025, monat=monat, einspeisung_kwh=100.0,
                           netzbezug_kwh=200.0, pv_erzeugung_kwh=500.0))
        db.add(InvestitionMonatsdaten(investition_id=wb.id, jahr=2025, monat=monat, verbrauch_daten={
            "ladung_kwh": 250.0, "ladung_pv_kwh": 100.0,
            "ladung_extern_kwh": 40.0, "ladung_extern_euro": 20.0}))
        db.add(InvestitionMonatsdaten(investition_id=ea.id, jahr=2025, monat=monat,
                                      verbrauch_daten={"km_gefahren": 1500.0}))
    await db.commit()
    return a


@pytest.mark.parametrize("bau", ["auto", "topf"])
async def test_s12_aussichten_ersparnis_gleich_hub_und_ha(db, bau):
    """Symmetrie: die bisherige E-Auto-Ersparnis der Aussichten (Zeile des Fahrzeugs im
    ROI-Fortschritt) gleicht Hub und HA-Sensor — alle drei ziehen die externen Kosten ab."""
    from backend.api.routes.aussichten import get_finanz_prognose
    from backend.api.routes.ha_export import calculate_investition_sensors
    from backend.api.routes.ha_export.emob import _load_emob_pool_ctx
    from backend.api.routes.investitionen import get_eauto_dashboard

    a = await (_jahres_anlage(db) if bau == "auto" else _s12_topf_anlage(db))
    invs = (await db.execute(select(Investition).where(Investition.anlage_id == a.id))).scalars().all()
    ea = next(i for i in invs if i.typ == "e-auto")
    hub = (await get_eauto_dashboard(anlage_id=a.id, strompreis_cent=None, db=db))[0].zusammenfassung
    ctx = await _load_emob_pool_ctx(db, invs)
    ha = next(v for v in await calculate_investition_sensors(db, ea, None, emob_ctx=ctx)
              if v.definition.key == "e_auto_ersparnis_vs_benzin_euro")
    prog = await get_finanz_prognose(anlage_id=a.id, monate=12, db=db)
    zeile = next(z for z in prog.ertraege_je_investition if z.investition_id == ea.id)
    assert hub["strom_kosten_extern_euro"] == pytest.approx(300.0 if bau == "auto" else 240.0)
    assert ha.value == pytest.approx(hub["ersparnis_vs_benzin_euro"], abs=0.01)
    assert zeile.bisherige_ertraege_euro == pytest.approx(hub["ersparnis_vs_benzin_euro"], abs=0.01)


async def test_s12_ha_rechenwege_in_deutscher_schreibweise(db):
    """Kein HA-Rechenweg dieser Anlage trägt einen Dezimalpunkt (`1387.50`); die
    Jahresersparnis steht als „(1.387,50 ÷ 12) × 12 [E-Auto Auto]"."""
    import re

    from backend.api.routes.ha_export import calculate_anlage_sensors, calculate_investition_sensors
    from backend.api.routes.ha_export.emob import _load_emob_pool_ctx

    a = await _jahres_anlage(db)
    invs = (await db.execute(select(Investition).where(Investition.anlage_id == a.id))).scalars().all()
    ctx = await _load_emob_pool_ctx(db, invs)
    werte = list(await calculate_anlage_sensors(db, a, skip_jitter=True))
    for inv in invs:
        werte += await calculate_investition_sensors(db, inv, None, emob_ctx=ctx)
    texte = {v.definition.key: v.berechnung for v in werte if v.berechnung}
    assert texte["jahres_ersparnis_euro"] == "(1.387,50 ÷ 12) × 12 [E-Auto Auto]"
    punkt = {k: t for k, t in texte.items() if re.search(r"\d\.\d{1,2}(?!\d)", t)}
    assert not punkt, punkt
    assert len(texte) >= 5, texte
