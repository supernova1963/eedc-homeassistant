"""Der MQTT-Block der Monatsabschluss-Route — Basisfeld UND Investitionsfeld.

**Warum es diese Probe gibt (RF-1, §4.6 der Vorlage).** Der Golden Master für
`GET /api/monatsabschluss/…` schaltet MQTT-Inbound in seinen DB-Kopien
absichtlich ab, damit der Lauf reproduzierbar ist — `mqtt_energy` und
`mqtt_inv_energy` sind dort **immer leer**. Die Mengenbildung selbst ist in
`test_mqtt_zaehlerstand_ist_keine_monatsmenge.py` gut gedeckt (F-66/N-341), und
die Prioritätskette von *Cockpit → Monat* ebenso — **den Block DIESER Route
fuhr bis heute keine Probe.** Genau er zieht beim RF-1-Schnitt um.

Geprüft wird das, was der Umzug bewegt:

1. die Zerlegung des Cache-Schlüssels ``inv/{id}/{feld}`` auf die Investition,
2. dass die Menge (nicht der Stand) mit Konfidenz **91** am Basisfeld **und**
   am Investitionsfeld als Vorschlag steht,
3. dass ein Zähler, der im Monat nicht weitergelaufen ist, die **gemessene 0**
   vorschlägt (Wortlaut „0 — kein Zuwachs").

⭐ **Punkt 3 ist seit N-721 (12.10.2026) umgekehrt.** Bis dahin sagte er „kein
Vorschlag — 0 kWh ist keine Aussage", und die Zusage hing an
`mqtt_monats_mengen` (`menge.menge_kwh > 0`), nicht an der Route. Eine Menge mit
beiden Rändern IST aber eine Messung („Daten da, kein Zuwachs"); ohne sie belegte
das Formular das Feld mit dem Vormonat „geschätzt" vor. Ausgenommen bleiben nur
die PV-Felder (`views.NULL_KEIN_VORSCHLAG_FELDER`). Die Punkte 1 und 2 sind
scharf (Gegenprobe mit ``konfidenz=45`` meldet beide rot, gemessen 19.09.2026).

⛔ **Keine echte Uhr.** Der geprüfte Monat liegt fest in der Vergangenheit; die
Route reicht `bis=None` durch und misst den ganzen Monat
(`test_konformitaet_echte_uhr_in_tests.py`).

Schwestern: `test_mqtt_zaehlerstand_ist_keine_monatsmenge.py` (die Mengenbildung
selbst), `test_monatsabschluss_connector_zuordnung.py` und
`test_monatsabschluss_connector_verteilt_label.py` (derselbe Vorschlagspfad aus
der Connector-Quelle), `test_monatsabschluss_geprueft_gegen.py`.
"""

from __future__ import annotations

from datetime import date, datetime

import pytest

from backend.models.sensor_snapshot import SensorSnapshot
from backend.services import mqtt_inbound_service as mqtt_mod
from backend.tests import factories

# Ein Monat in der Vergangenheit — die Route fragt dann nicht nach „jetzt".
JAHR, MONAT = 2025, 3

# Basis: Netzbezug 1000,0 → 1120,5 ⇒ 120,5 kWh im Monat.
NETZ_ANFANG, NETZ_ENDE = 1000.0, 1120.5
NETZ_MENGE = 120.5
# Speicher: Ladung 4473,9 → 4700,3 ⇒ 226,4 kWh im Monat.
LAD_ANFANG, LAD_ENDE = 4473.9, 4700.3
LAD_MENGE = 226.4
# Gegenprobe: die Entladung steht still — Differenz 0, also keine Aussage.
ENTL_STAND = 88.0


@pytest.fixture(autouse=True)
def _mqtt_singleton_zuruecksetzen():
    vorher = mqtt_mod._mqtt_inbound_service
    yield
    mqtt_mod._mqtt_inbound_service = vorher


def _stelle_mqtt_cache(anlage_id: int, werte: dict[str, float]) -> None:
    """Energy-Cache über den Produktivweg füllen (Topic → Cache), nicht per Setzen.

    Dieselbe Begründung wie in `test_mqtt_zaehlerstand_ist_keine_monatsmenge.py`:
    eine Probe, die sich ihren Zustand am Produktivweg vorbei herstellt, schützt
    am Ende die Falschaussage.
    """
    svc = mqtt_mod.MqttInboundService("localhost", 1883)
    for key, wert in werte.items():
        if key.startswith("inv/"):
            _, inv_id, feld = key.split("/", 2)
            topic = f"eedc/{anlage_id}/energy/inv/{inv_id}/{feld}"
        else:
            topic = f"eedc/{anlage_id}/energy/{key}"
        svc.cache.on_message(topic, str(wert))
    mqtt_mod._mqtt_inbound_service = svc


async def _stand(db, anlage_id: int, key: str, zeitpunkt: datetime, wert: float) -> None:
    db.add(SensorSnapshot(
        anlage_id=anlage_id, sensor_key=key, zeitpunkt=zeitpunkt,
        wert_kwh=wert, quelle="mqtt_inbound",
    ))


async def _anlage_mit_standreihen(db):
    """Anlage + Speicher, beide Zählerreihen über den Monatsrand hinweg."""
    anlage = await factories.anlage(db)
    speicher = await factories.investition(
        db, anlage.id, "speicher",
        anschaffungsdatum=date(2024, 1, 1), leistung_kwp=10.0,
    )
    anfang, ende = datetime(JAHR, MONAT, 1), datetime(JAHR, MONAT + 1, 1)
    await _stand(db, anlage.id, "basis:netzbezug", anfang, NETZ_ANFANG)
    await _stand(db, anlage.id, "basis:netzbezug", ende, NETZ_ENDE)
    await _stand(db, anlage.id, f"inv:{speicher.id}:ladung_kwh", anfang, LAD_ANFANG)
    await _stand(db, anlage.id, f"inv:{speicher.id}:ladung_kwh", ende, LAD_ENDE)
    await _stand(db, anlage.id, f"inv:{speicher.id}:entladung_kwh", anfang, ENTL_STAND)
    await _stand(db, anlage.id, f"inv:{speicher.id}:entladung_kwh", ende, ENTL_STAND)
    await db.commit()
    _stelle_mqtt_cache(anlage.id, {
        "netzbezug_kwh": NETZ_ENDE,
        f"inv/{speicher.id}/ladung_kwh": LAD_ENDE,
        f"inv/{speicher.id}/entladung_kwh": ENTL_STAND,
    })
    return anlage, speicher


def _mqtt_vorschlag(feld_status):
    treffer = [v for v in feld_status.vorschlaege if v.quelle == "mqtt_inbound"]
    return treffer[0] if treffer else None


async def test_basisfeld_bekommt_die_monatsmenge_mit_konfidenz_91(db):
    """`netzbezug_kwh`: 120,5 kWh — die Differenz, nicht der Stand 1120,5."""
    from backend.api.routes.monatsabschluss.views import get_monatsabschluss

    anlage, _ = await _anlage_mit_standreihen(db)

    status = await get_monatsabschluss(anlage.id, JAHR, MONAT, db)

    assert status.mqtt_inbound_konfiguriert is True
    (netz,) = [f for f in status.basis_felder if f.feld == "netzbezug_kwh"]
    v = _mqtt_vorschlag(netz)
    assert v is not None, "kein MQTT-Vorschlag am Basisfeld"
    assert v.wert == NETZ_MENGE
    assert v.wert != NETZ_ENDE
    assert v.konfidenz == 91


async def test_investitionsfeld_bekommt_seine_eigene_menge(db):
    """Der Cache-Schlüssel `inv/{id}/ladung_kwh` landet an genau dieser Investition."""
    from backend.api.routes.monatsabschluss.views import get_monatsabschluss

    anlage, speicher = await _anlage_mit_standreihen(db)

    status = await get_monatsabschluss(anlage.id, JAHR, MONAT, db)

    (inv,) = [i for i in status.investitionen if i.id == speicher.id]
    je_feld = {f.feld: f for f in inv.felder}
    v = _mqtt_vorschlag(je_feld["ladung_kwh"])
    assert v is not None, "kein MQTT-Vorschlag am Investitionsfeld"
    assert v.wert == LAD_MENGE
    assert v.wert != LAD_ENDE
    assert v.konfidenz == 91


async def test_stillstehender_zaehler_schlaegt_die_gemessene_null_vor(db):
    """Differenz 0 mit beiden Rändern ⇒ Vorschlag 0 (N-721, vorher: kein Vorschlag)."""
    from backend.api.routes.monatsabschluss.views import (
        NULL_VORSCHLAG_BESCHREIBUNG,
        get_monatsabschluss,
    )

    anlage, speicher = await _anlage_mit_standreihen(db)

    status = await get_monatsabschluss(anlage.id, JAHR, MONAT, db)

    (inv,) = [i for i in status.investitionen if i.id == speicher.id]
    je_feld = {f.feld: f for f in inv.felder}
    v = _mqtt_vorschlag(je_feld["entladung_kwh"])
    assert v is not None
    assert (v.wert, v.konfidenz, v.beschreibung) == (0.0, 91, NULL_VORSCHLAG_BESCHREIBUNG)
