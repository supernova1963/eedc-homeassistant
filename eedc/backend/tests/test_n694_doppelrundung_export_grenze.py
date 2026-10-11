"""N-694 — zwei HA-Sensoren rundeten vor der Export-Grenze auf eine Stelle, die Grenze danach auf null Stellen.

Gemessen am HEAD `ee222ed7`: ein Monatsverbrauch von 3,46 kWh stand in HA als **4 kWh** (3,46 → 3,5 → 4), richtig
ist 3 (3,46 → 3). Python rundet 0,5 zur geraden Zahl, deshalb trifft es rund 5 % der Werte — immer um genau 1 kWh.
Betroffen: `sonstiges_verbrauch_monat_kwh` (je Verbraucher, `_sonstiges_sensoren`) und
`eedc_ueberschuss_prognose_heute_kwh` (anlagenweit, `anlage_steuerung.steuerungs_sensoren`).

Die Regel (B7, Rainer-PN 89905/2): der Produzent liefert ungerundet, gerundet wird einmal an der
Serialisierungsgrenze (`runde_exportwert`) — für REST und MQTT gleich. Der Wächter dazu steht in
`test_export_rundung_rest_mqtt_gleich.py::test_produzent_liefert_ungerundet` und sieht seit N-694 auch diese beiden
Funktionen.

Schwesterdateien: `test_s3_geraete_fenster.py` (P9, Aufbau des Verbrauchers), `test_s2_entscheidungs_sensoren.py`
(P2, Aufbau der Prognose), `test_export_rundung_rest_mqtt_gleich.py` (die Grenze selbst).
"""

from __future__ import annotations

import pytest

from backend.tests.test_export_rundung_rest_mqtt_gleich import _mqtt_states, _rest_states
from backend.tests import test_s2_entscheidungs_sensoren as s2
from backend.tests import test_s3_geraete_fenster as s3


@pytest.mark.asyncio
async def test_sonstiges_monatsverbrauch_3_46_steht_als_3_in_ha(db, monkeypatch):
    heute = s3.HEUTE
    anlage = await s3._anlage(db)
    inv = await s3._geraet(db, anlage, "sonstiges", {"kategorie": "verbraucher"}, {
        (heute.year, heute.month): {"verbrauch_sonstig_kwh": 3.46, "bezug_pv_kwh": 1.0, "bezug_netz_kwh": 2.46},
    })
    werte = await s3._rechne(db, inv, s3._ctx(stunde=0))
    sv = s3._sv(werte, "sonstiges_verbrauch_monat_kwh")
    assert sv is not None
    rest = _rest_states([sv])
    mqtt = await _mqtt_states(monkeypatch, [sv])
    assert rest["sonstiges_verbrauch_monat_kwh"] == "3", "3,46 kWh → 3 (am HEAD: 4)"
    assert mqtt["sonstiges_verbrauch_monat_kwh"] == "3"
    assert sv.value == pytest.approx(3.46), "der Produzent liefert ungerundet"
    # Die Attribute rundet die Grenze nicht — sie bleiben auf einer Stelle.
    assert sv.zusatz_attribute["bezug_netz_kwh"] == pytest.approx(2.5)


@pytest.mark.asyncio
async def test_ueberschuss_prognose_3_46_steht_als_3_in_ha(db, monkeypatch):
    anlage = await s2._anlage(db)
    await s2._tagesprofil(db, anlage.id, s2.HEUTE)
    # Ein einziger Überschuss-Slot: 3,96 − 0,5 = 3,46 kWh.
    pv = [0.0] * 12 + [3.96] + [0.0] * 11
    s2._stelle_quellen(monkeypatch, s2._prognose(stundenprofil_heute=pv, heute_kwh=sum(pv)), s2._preis())

    werte, _ = await s2._rechne(db, anlage)
    sv = s2._sv(werte, "eedc_ueberschuss_prognose_heute_kwh")
    assert sv is not None
    rest = _rest_states([sv])
    mqtt = await _mqtt_states(monkeypatch, [sv])
    assert rest["eedc_ueberschuss_prognose_heute_kwh"] == "3", "3,46 kWh → 3 (am HEAD: 4)"
    assert mqtt["eedc_ueberschuss_prognose_heute_kwh"] == "3"
    assert sv.value == pytest.approx(3.46), "der Produzent liefert ungerundet"
    # Das Stundenprofil ist ein Attribut und bleibt auf zwei Stellen.
    assert sv.zusatz_attribute["stundenprofil_kwh"][12] == pytest.approx(3.46)
