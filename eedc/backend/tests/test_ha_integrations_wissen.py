"""
#343 Baustein A (D2) — kuratierte Integrations-Wissensbasis für den HA-Picker.

Sichert: Erkennung über Entity-ID-Muster, Feld-Vorschläge nur für kuratierte
Typ×Feld-Kombinationen, Anti-Empfehlungen (Session-Ende-Statistiken), und dass
explizites Feld-Wissen die generische Warnung schlägt (evcc solar-stat_total
ist die richtige Quelle für ladung_pv_kwh).
"""

from backend.core.ha_integrations_wissen import NUR_ERKANNT_HINWEIS, analysiere_vorschlaege

EVCC_ENTITIES = [
    "sensor.evcc_garage_charged_energy",
    "sensor.evcc_stat_total_solar_k_wh_template",
    "sensor.evcc_stat_total_charged_kwh",
    "sensor.evcc_id_3_odometer",
    "sensor.sma_pv_leistung",
]


def test_evcc_erkannt_und_feld_vorschlag_wallbox_ladung():
    r = analysiere_vorschlaege(EVCC_ENTITIES, feld="ladung_kwh", inv_typ="wallbox")
    assert "evcc" in r["integrationen"]
    assert [v["entity_id"] for v in r["vorschlaege"]] == ["sensor.evcc_garage_charged_energy"]
    assert "Ladepunkt" in r["vorschlaege"][0]["hinweis"]


def test_evcc_stat_total_als_anti_empfehlung():
    r = analysiere_vorschlaege(EVCC_ENTITIES, feld="ladung_kwh", inv_typ="wallbox")
    # Beide stat_total-Sensoren tragen die Session-Ende-Warnung
    assert "sensor.evcc_stat_total_charged_kwh" in r["warnungen"]
    assert "sensor.evcc_stat_total_solar_k_wh_template" in r["warnungen"]


def test_feld_wissen_schlaegt_warnung_solar_fuer_ladung_pv():
    r = analysiere_vorschlaege(EVCC_ENTITIES, feld="ladung_pv_kwh", inv_typ="wallbox")
    vorschlags_ids = [v["entity_id"] for v in r["vorschlaege"]]
    assert "sensor.evcc_stat_total_solar_k_wh_template" in vorschlags_ids
    # Für DIESES Feld entfällt die generische stat_total-Warnung am Solar-Sensor
    assert "sensor.evcc_stat_total_solar_k_wh_template" not in r["warnungen"]
    # Der andere stat_total bleibt gewarnt
    assert "sensor.evcc_stat_total_charged_kwh" in r["warnungen"]


def test_eauto_km_vorschlag_und_fremdes_feld_leer():
    r = analysiere_vorschlaege(EVCC_ENTITIES, feld="km_gefahren", inv_typ="e-auto")
    assert [v["entity_id"] for v in r["vorschlaege"]] == ["sensor.evcc_id_3_odometer"]
    # Unkuratierte Kombination → keine Vorschläge, Erkennung bleibt
    r2 = analysiere_vorschlaege(EVCC_ENTITIES, feld="verbrauch_kwh", inv_typ="e-auto")
    assert r2["vorschlaege"] == [] and "evcc" in r2["integrationen"]


def test_nur_erkennung_ohne_feldwissen():
    r = analysiere_vorschlaege(["sensor.go_echarger_energy_total"], feld="ladung_kwh", inv_typ="wallbox")
    assert r["integrationen"] == ["go-eCharger"]
    assert r["vorschlaege"] == [] and r["warnungen"] == {}
    assert NUR_ERKANNT_HINWEIS  # Hinweistext existiert für die UI


def test_keine_integration_erkannt():
    r = analysiere_vorschlaege(["sensor.sma_pv_leistung"], feld="ladung_kwh", inv_typ="wallbox")
    assert r == {"integrationen": [], "vorschlaege": [], "warnungen": {}}
