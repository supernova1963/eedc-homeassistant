"""N-693 — HA-Export: der Ersatzpreis für Monate vor dem ersten Tarif ist EINER, der der Monats-Fakten.

Gemessen am HEAD `ee222ed7` (acht Monate 07/2025–02/2026, erster Tarif ab 09/2025; E-Auto 1000 km, 90 kWh Netz-, 60 kWh
PV-Ladung je Monat; Wärmepumpe 1000 kWh Wärme, 300 kWh Strom je Monat; Gas 12 ct, Benzin 1,80 €):

| Fall | Sensor | REST | MQTT | Cockpit (Monats-Fakten) |
| --- | --- | --- | --- | --- |
| B allg 30 ab 09 + WP 22 ab 12 | E-Auto | 720,00 | 734,40 | 720,00 |
| B | WP | 418,67 | 466,67 | 418,64 |
| C allg 35 ab 09 + WP 22 ab 12 | E-Auto | 666,00 | 689,40 | 675,00 |
| C | WP | 343,67 | 421,67 | 373,64 |
| G allg 35 ab 09 + Wallbox 25 ab 12 | E-Auto | 693,00 | 711,00 | 702,00 |
| G | WP | 226,67 | 286,67 | 256,64 |

REST nahm für die Monate ohne Tarif den HEUTIGEN Allgemeintarif, MQTT den jüngsten Eintrag JEDER Verwendung (per
Handquery, die Form vor N-200), die Monats-Fakten die Vorbelegung 30 ct. Im REST-Rechenweg kostete derselbe Monat
35 ct (Netz-Ladung) und 30 ct (PV-Ladung). Soll: alle wie die Monats-Fakten.

Die Erwartungswerte sind von Hand gerechnet (Docstring je Fall), nicht von einer Sicht abgeschrieben; die Cockpit-Zahl
der Wärmepumpe rundet je Gerätezeile auf Cent (N-609) und liegt deshalb bis zu 8 × 0,005 € daneben.

⚠ Bewusst NICHT hier: die Komponenten-Hubs (E-Auto-Hub, WP-Hub) reichen selbst den heutigen Komponenten-Tarif als
Ersatzpreis durch und weichen in C/G weiter ab — gemeldet im Baubericht, nicht Teil von N-693.

Schwesterdateien: test_n693_jahresbericht_kopf_tarif.py (derselbe Fund im PDF-Kopf), test_b5_x3_sensor_ohne_wert.py
(der Fake-Klient des MQTT-Publishers), test_n459_wp_strom_voll_belastet.py (dieselbe WP-Ersparnis in fünf Sichten).
"""

from __future__ import annotations

from datetime import date

import pytest

from backend.models import Anlage, Investition, Monatsdaten, Strompreis
from backend.models.investition import InvestitionMonatsdaten

MONATE = [(2025, m) for m in range(7, 13)] + [(2026, 1), (2026, 2)]
WP_PARAM = {"wp_art": "luft_wasser", "effizienz_modus": "gesamt_jaz", "waermebedarf_kwh": 12000.0, "jaz": 3.5,
            "alter_energietraeger": "gas", "alter_preis_cent_kwh": 12.0, "alternativ_zusatzkosten_jahr": 0.0}

#: (Tarife, E-Auto-Ersparnis, WP-Ersparnis) — von Hand:
#: E-Auto: Benzin 8000 km × 7,5 l/100 km × 1,80 € = 1080 €; Netz 90 kWh × Monatspreis; PV 60 kWh × Preis der
#:         Eigenverbrauchs-Ersparnis des Monats (Allgemeintarif bzw. 30 ct ohne Tarif).
#: WP:     alte Heizung 8 × 1000 kWh ÷ 0,9 × 12 ct = 1066,67 €; WP 300 kWh × WP-Preis des Monats.
FAELLE = {
    # Netz 90 × 8 × 0,30 = 216; PV 480 × 0,30 = 144 ⇒ 720.   WP 300 × (5 × 0,30 + 3 × 0,22) = 648 ⇒ 418,67.
    "B": ([(30.0, date(2025, 9, 1), "allgemein"), (22.0, date(2025, 12, 1), "waermepumpe")], 720.00, 418.67),
    # Netz 90 × (2 × 0,30 + 6 × 0,35) = 243; PV 60 × 2,70 = 162 ⇒ 675.   WP 300 × (2 × 0,30 + 3 × 0,35 + 3 × 0,22) = 693.
    "C": ([(35.0, date(2025, 9, 1), "allgemein"), (22.0, date(2025, 12, 1), "waermepumpe")], 675.00, 373.67),
    # Netz 90 × (2 × 0,30 + 3 × 0,35 + 3 × 0,25) = 216; PV 162 ⇒ 702.   WP 300 × (2 × 0,30 + 6 × 0,35) = 810.
    "G": ([(35.0, date(2025, 9, 1), "allgemein"), (25.0, date(2025, 12, 1), "wallbox")], 702.00, 256.67),
}


async def _anlage(db, tarife):
    a = Anlage(anlagenname="N693", leistung_kwp=10.0, installationsdatum=date(2025, 7, 1),
               standort_plz="10115", latitude=48.0, longitude=11.0)
    db.add(a)
    await db.flush()
    for preis, ab, verwendung in tarife:
        db.add(Strompreis(anlage_id=a.id, netzbezug_arbeitspreis_cent_kwh=preis, einspeiseverguetung_cent_kwh=8.0,
                          gueltig_ab=ab, verwendung=verwendung, anbieter="Werk", tarifname=f"{verwendung} {preis}"))
    for j, m in MONATE:
        db.add(Monatsdaten(anlage_id=a.id, jahr=j, monat=m, einspeisung_kwh=200.0, netzbezug_kwh=150.0,
                           kraftstoffpreis_euro=1.80, gaspreis_cent_kwh=12.0))
    pv = Investition(anlage_id=a.id, typ="pv-module", bezeichnung="PV", anschaffungsdatum=date(2025, 7, 1),
                     anschaffungskosten_gesamt=12000.0, leistung_kwp=10.0)
    ea = Investition(anlage_id=a.id, typ="e-auto", bezeichnung="EA", anschaffungsdatum=date(2025, 7, 1),
                     anschaffungskosten_gesamt=35000.0, anschaffungskosten_alternativ=30000.0, parameter={})
    wp = Investition(anlage_id=a.id, typ="waermepumpe", bezeichnung="WP", anschaffungsdatum=date(2025, 7, 1),
                     anschaffungskosten_gesamt=20000.0, anschaffungskosten_alternativ=8000.0, parameter=WP_PARAM)
    db.add_all([pv, ea, wp])
    await db.flush()
    for j, m in MONATE:
        db.add(InvestitionMonatsdaten(investition_id=pv.id, jahr=j, monat=m,
                                      verbrauch_daten={"pv_erzeugung_kwh": 500.0}))
        db.add(InvestitionMonatsdaten(investition_id=ea.id, jahr=j, monat=m, verbrauch_daten={
            "km_gefahren": 1000, "verbrauch_kwh": 180.0, "ladung_pv_kwh": 60.0, "ladung_netz_kwh": 90.0}))
        db.add(InvestitionMonatsdaten(investition_id=wp.id, jahr=j, monat=m, verbrauch_daten={
            "heizenergie_kwh": 800.0, "warmwasser_kwh": 200.0, "stromverbrauch_kwh": 300.0}))
    await db.commit()
    return a, ea, wp


class _FakeMqttClient:
    """Fängt, was der MQTT-Publisher je Gerät schreiben würde — die Werte, nicht nur die Schlüssel."""

    def __init__(self):
        self.is_available = True
        self.werte: dict[tuple[int | None, str], object] = {}

    async def publish_all_sensors(self, sensor_values, anlage_id, anlage_name,
                                  investition_id=None, investition_name=None):
        for sv in sensor_values:
            self.werte[(investition_id, sv.definition.key)] = sv
        return {"total": len(sensor_values), "success": len(sensor_values), "failed": 0, "errors": []}

    async def publish_sensor_value(self, sensor_value, anlage_id, investition_id=None):
        return True


async def _mqtt(db, anlage, monkeypatch) -> _FakeMqttClient:
    from backend.services import ha_mqtt_sync

    klient = _FakeMqttClient()
    monkeypatch.setattr(ha_mqtt_sync, "MQTTClient", lambda *a, **k: klient)

    async def _broker(_db):
        return None

    monkeypatch.setattr(ha_mqtt_sync, "resolve_broker_config", _broker)
    await ha_mqtt_sync.publish_anlage_sensors(db, anlage, skip_jitter=True)
    return klient


def _ohne_netz(monkeypatch):
    """Prognose und Börsenpreis der Anlagen-Sensoren gestellt (wie `test_s2_entscheidungs_sensoren.py`) — REST und
    MQTT rechnen die Anlage mit, und die Geräte-Sensoren hier brauchen beides nicht."""
    from backend.api.routes.ha_export import anlage_sensorwerte

    async def _leer(*_a, **_k):
        return {}

    monkeypatch.setattr(anlage_sensorwerte, "berechne_prognose_export", _leer)
    monkeypatch.setattr(anlage_sensorwerte, "berechne_preis_export", _leer)


def _rest_wert(export, inv_id: int, key: str):
    for inv in export.investitionen:
        if inv.investition_id == inv_id:
            for s in inv.sensors:
                if s.key == key:
                    return s.value
    return None


def _mqtt_wert(klient: _FakeMqttClient, inv_id: int, key: str):
    from backend.services.ha_sensors_export import runde_exportwert

    sv = klient.werte.get((inv_id, key))
    return None if sv is None else runde_exportwert(sv.value, sv.definition.unit, sv.definition.category)


@pytest.mark.asyncio
@pytest.mark.parametrize("fall", sorted(FAELLE))
async def test_rest_mqtt_und_monats_fakten_nennen_dieselbe_ersparnis(db, monkeypatch, fall):
    from backend.api.routes.cockpit.uebersicht import get_cockpit_uebersicht
    from backend.api.routes.ha_export.sensoren import get_all_sensors

    tarife, ea_soll, wp_soll = FAELLE[fall]
    anlage, ea, wp = await _anlage(db, tarife)
    _ohne_netz(monkeypatch)

    rest = await get_all_sensors(db=db)
    klient = await _mqtt(db, anlage, monkeypatch)
    cockpit = await get_cockpit_uebersicht(anlage.id, jahr=None, db=db)

    ea_rest = _rest_wert(rest, ea.id, "e_auto_ersparnis_vs_benzin_euro")
    ea_mqtt = _mqtt_wert(klient, ea.id, "e_auto_ersparnis_vs_benzin_euro")
    wp_rest = _rest_wert(rest, wp.id, "wp_ersparnis_euro")
    wp_mqtt = _mqtt_wert(klient, wp.id, "wp_ersparnis_euro")

    assert ea_mqtt == ea_rest, f"{fall}: E-Auto MQTT {ea_mqtt} ≠ REST {ea_rest}"
    assert wp_mqtt == wp_rest, f"{fall}: WP MQTT {wp_mqtt} ≠ REST {wp_rest}"
    assert ea_rest == pytest.approx(ea_soll, abs=0.005), f"{fall}: E-Auto REST {ea_rest}, von Hand {ea_soll}"
    assert wp_rest == pytest.approx(wp_soll, abs=0.005), f"{fall}: WP REST {wp_rest}, von Hand {wp_soll}"
    assert cockpit.emob_ersparnis_euro == pytest.approx(ea_soll, abs=0.005)
    # N-609: das Cockpit rundet je Gerätezeile auf Cent — acht Monate, höchstens 8 × 0,005 €.
    assert cockpit.wp_ersparnis_euro == pytest.approx(wp_soll, abs=0.04)


@pytest.mark.asyncio
async def test_rest_rechenweg_traegt_einen_preis_je_monat_ohne_tarif(db):
    """Der Rechenweg nennt für Netz- und PV-Ladung denselben Ø — am HEAD 35,00 gegen 33,75 ct (Fall C)."""
    from backend.api.routes.ha_export import calculate_investition_sensors
    from backend.api.routes.strompreise import lade_tarife_fuer_anlage

    anlage, ea, _ = await _anlage(db, FAELLE["C"][0])
    tarif = (await lade_tarife_fuer_anlage(db, anlage.id))["allgemein"]
    werte = await calculate_investition_sensors(db, ea, tarif)
    sv = next(s for s in werte if s.definition.key == "e_auto_ersparnis_vs_benzin_euro")
    assert "Strom @ 33,75 ct/kWh" in sv.berechnung, sv.berechnung
    assert "PV-Ladung @ 33,75 ct/kWh" in sv.berechnung, sv.berechnung


@pytest.mark.asyncio
async def test_infothek_vorbelegung_nimmt_den_heutigen_allgemeintarif(db):
    """Dieselbe Klasse an der Infothek: ein künftiger Tarif belegt den Vertrag nicht vor, ein WP-Tarif nicht die
    Einspeisevergütung (am HEAD: „Zukunft"/40 ct bzw. 9,0 ct aus dem künftigen Eintrag)."""
    from backend.api.routes.infothek import get_vorbelegung

    a = Anlage(anlagenname="N693-Infothek", leistung_kwp=5.0, installationsdatum=date(2020, 1, 1))
    db.add(a)
    await db.flush()
    db.add_all([
        Strompreis(anlage_id=a.id, verwendung="allgemein", anbieter="Heute", gueltig_ab=date(2020, 1, 1),
                   netzbezug_arbeitspreis_cent_kwh=30.0, einspeiseverguetung_cent_kwh=8.0),
        Strompreis(anlage_id=a.id, verwendung="waermepumpe", anbieter="WP-Werk", gueltig_ab=date(2021, 1, 1),
                   netzbezug_arbeitspreis_cent_kwh=22.0, einspeiseverguetung_cent_kwh=0.0),
        Strompreis(anlage_id=a.id, verwendung="allgemein", anbieter="Zukunft", gueltig_ab=date(2099, 1, 1),
                   netzbezug_arbeitspreis_cent_kwh=40.0, einspeiseverguetung_cent_kwh=9.0),
    ])
    await db.commit()

    strom = (await get_vorbelegung("stromvertrag", anlage_id=a.id, db=db))["parameter"]
    einsp = (await get_vorbelegung("einspeisevertrag", anlage_id=a.id, db=db))["parameter"]
    assert strom["anbieter"] == "Heute" and strom["tarif_ct_kwh"] == 30.0, strom
    assert einsp["verguetung_ct_kwh"] == 8.0, einsp
