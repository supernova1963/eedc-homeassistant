"""Abgabe an Dritte (§9.2) — Tag und Live folgen dem Monats-Layer.

Der Monat zieht die Abgabe vom Eigenverbrauch ab (Commit 1). Der Tag sieht am
Netzpunkt dieselbe Physik: PV − Einspeisung enthält, was an Dritte ging. Ohne
Abzug stünde der Tages-Eigenverbrauch zu hoch, die Live-Autarkie ebenso — die
Klasse, an der N-378 aufging (Robert: 92 %).

Schwesterdateien: test_abgabe_an_dritte_vier_sichten.py (Monat/Jahr/Export),
test_n250_sonstiges_richtung.py (Tages-Richtung), test_f70_sonstiger_speicher_live_bilanz.py
(Live-Builder-Muster), test_co2_tages_bezugsgroesse.py (Tageswerte-Muster).
"""

from __future__ import annotations

from datetime import date

import pytest

from backend.models import Anlage, Investition
from backend.models.mqtt_gateway_mapping import MqttGatewayMapping  # noqa: F401
from backend.models.sensor_snapshot import SensorSnapshot  # noqa: F401
from backend.models.tages_energie_profil import TagesEnergieProfil, TagesZusammenfassung

TAG = date(2025, 7, 15)


def test_tages_richtung_kennt_die_abgabe():
    from backend.core.berechnungen.energie import sonstiges_kwh_je_richtung
    s = sonstiges_kwh_je_richtung(
        {"sonstige_1": 3.0, "sonstige_2": -1.5, "sonstige_3": 4.0},
        {"1": "erzeuger", "2": "verbraucher", "3": "abgabe"},
    )
    assert (s.erzeugung_kwh, s.verbrauch_kwh, s.abgabe_kwh) == (3.0, 1.5, 4.0)
    leer = sonstiges_kwh_je_richtung({"sonstige_3": 4.0}, {"3": "erzeuger"})
    assert leer.abgabe_kwh is None


@pytest.mark.asyncio
async def test_tageswert_zieht_die_abgabe_vom_eigenverbrauch_ab(db):
    """24 h × (PV 1,0 · Einspeisung 0,2 · Netzbezug 0,3 · Verbrauch 1,1 kW):
    Stunden-Bilanz EV 19,2 kWh. Abgabe-Zähler des Tages 4,0 kWh ⇒ EV 15,2,
    Autarkie 15,2 / (15,2 + 7,2) = 67,9 %, Quote 15,2 / 24 = 63,3 %."""
    from backend.services.energie_profil.tage_werte import baue_tage_werte

    a = Anlage(anlagenname="tag", leistung_kwp=10.0, installationsdatum=date(2025, 1, 1))
    db.add(a)
    await db.flush()
    so = Investition(anlage_id=a.id, typ="sonstiges", bezeichnung="Victron-EG",
                     anschaffungsdatum=date(2025, 1, 1), anschaffungskosten_gesamt=1000.0,
                     parameter={"kategorie": "abgabe"})
    db.add(so)
    await db.flush()
    for h in range(24):
        db.add(TagesEnergieProfil(anlage_id=a.id, datum=TAG, stunde=h, pv_kw=1.0,
                                  einspeisung_kw=0.2, netzbezug_kw=0.3, verbrauch_kw=1.1))
    db.add(TagesZusammenfassung(anlage_id=a.id, datum=TAG, komponenten_kwh={f"sonstige_{so.id}": 4.0}))
    await db.commit()
    t = (await baue_tage_werte(db, a, TAG, TAG))[0]
    assert t.sonstiges_abgabe == pytest.approx(4.0)
    assert t.eigenverbrauch == pytest.approx(15.2, abs=0.01)
    assert t.autarkie == pytest.approx(67.9, abs=0.1)
    assert t.evQuote == pytest.approx(63.3, abs=0.1)


def test_live_builder_zieht_die_abgabe_aus_der_bilanz():
    """Live: PV 5 kW, Einspeisung 1 kW, Netzbezug 0, Abgabe-Gerät 2 kW ⇒
    Eigenverbrauch 2 kW (nicht 4), Autarkie 100 %, EV-Quote 40 % (nicht 80)."""
    from backend.services.live_komponenten_builder import build_komponenten

    class _Inv:
        def __init__(self, id_, typ, parameter=None, bezeichnung="x"):
            self.id, self.typ, self.parameter, self.bezeichnung = id_, typ, parameter, bezeichnung
            self.parent_investition_id = None
            self.leistung_kwp = 10.0

        def ist_aktiv_an(self, _tag):
            return True

    class _Anlage:
        id = 1
        anlagenname = "live"
        leistung_kwp = 10.0

    pv = _Inv(1, "pv-module", {}, "PV")
    ab = _Inv(2, "sonstiges", {"kategorie": "abgabe"}, "Victron-EG")
    res = build_komponenten(
        _Anlage(), {"einspeisung_w": 1000.0, "netzbezug_w": 0.0},
        {"1": {"leistung_w": 5000.0}, "2": {"leistung_w": 2000.0}},
        {"1": pv, "2": ab}, {},
    )
    komp = next(k for k in res["komponenten"] if k["key"] == "sonstige_2")
    assert komp["verbrauch_kw"] == pytest.approx(2.0) and komp.get("abgabe") is True
    gauges = {g["key"]: g["wert"] for g in res["gauges"]}
    assert gauges["eigenverbrauch"] == pytest.approx(40, abs=1)
    assert gauges["autarkie"] == pytest.approx(100, abs=1)


def test_live_tages_kwh_ohne_abgabe():
    from backend.services.live_power_service import LivePowerService
    svc = LivePowerService.__new__(LivePowerService)
    kwh = {"pv": 10.0, "einspeisung": 2.0, "netzbezug": 3.0, "sonstige_7": 3.0}
    ev, hv = svc._calc_tages_ev_hv(kwh, frozenset({"sonstige_7"}))
    assert (ev, hv) == (5.0, 8.0)
    ev2, _ = svc._calc_tages_ev_hv(kwh)
    assert ev2 == 8.0, "ohne Abgabe-Schlüssel wie bisher"
