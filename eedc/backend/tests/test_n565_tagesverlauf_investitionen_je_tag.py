"""N-565 — der Live-/Leistungspfad lädt für einen vergangenen Tag die Investitionen DIESES Tages.

Bis 26.09.2026 lud `live_tagesverlauf_service.get_tagesverlauf` (HA-Zweig und MQTT-Zweig) seine
Investitionen mit `aktiv_jetzt()` — auch für `tage_zurueck > 0`. Eine Wallbox, die zwischen dem
betrachteten Tag und heute stillgelegt wurde, fehlte dort ganz: sie verdrängte das E-Auto nicht
(Regel 6 des Heimlade-Konzepts, `baue_investitions_serien(tag=…)`) und stand in keiner Serie,
obwohl sie an dem Tag lud. Gemeldet im Lücken-Bau (Schnitt 10b, benannte Grenze).

Jetzt: vergangener Tag ⇒ `aktiv_am_tag(tag)`, **heute unverändert `aktiv_jetzt()`** — die beiden
Filter unterscheiden sich gerade an heute (Anschaffung in der Zukunft zählt live mit, eine
Stilllegung heute nicht); die Heute-Proben unten halten genau diese zwei Punkte fest.

⚠ **Eine Ablesung der echten Uhr (`HEUTE`), mit Ansage** (Baseline in
`test_konformitaet_echte_uhr_in_tests.py`): der Prüfling rechnet seinen Tag selbst aus
`datetime.now()` und `tage_zurueck`, ein festes Datum fiele aus seinem Fenster. Die Fixture
legt alle Daten relativ zu `HEUTE` (nur Tagesabstände, keine Uhrzeit) — wie N-439.

Schwesterdateien: test_zaehlerluecken_s2_8b_wallbox_je_tag.py (LTS-Pfad, dieselbe Frage),
test_tagesverlauf_standalone_ha_verbindung.py (Weggabelung HA/MQTT).
"""

from __future__ import annotations

from datetime import date, timedelta
from types import SimpleNamespace

import pytest

from backend.models.anlage import Anlage
from backend.models.investition import Investition
from backend.services import live_tagesverlauf_service as ltv
from backend.services.ha_state_service import get_ha_state_service

HEUTE = date.today()


@pytest.fixture
def ha_verbindung():
    svc = get_ha_state_service()
    vorher = (svc.api_url, svc.token)

    def setzen(token):
        svc.api_url = "http://ha.example:8123/api"
        svc.token = token

    yield setzen
    svc.api_url, svc.token = vorher


@pytest.fixture(autouse=True)
def _ohne_marktabruf(monkeypatch):
    from backend.services import strompreis_markt_service as sms

    async def keine_preise(land, tag):
        return {}

    monkeypatch.setattr(sms, "get_strompreis_stunden", keine_preise)


async def _anlage(db) -> tuple[Anlage, dict[str, Investition]]:
    """Wallbox (stillgelegt gestern) + E-Auto mit eigenem Leistungssensor, dazu zwei Geräte,
    an denen sich `aktiv_jetzt` und `aktiv_am_tag` für HEUTE unterscheiden."""
    a = Anlage(anlagenname="N565", leistung_kwp=10.0, sensor_mapping={})
    db.add(a)
    await db.flush()
    geraete = {
        "wb": Investition(anlage_id=a.id, typ="wallbox", bezeichnung="WB",
                          anschaffungsdatum=date(2024, 1, 1),
                          stilllegungsdatum=HEUTE - timedelta(days=1)),
        "auto": Investition(anlage_id=a.id, typ="e-auto", bezeichnung="Auto",
                            anschaffungsdatum=date(2024, 1, 1)),
        # Anschaffung morgen: live (aktiv_jetzt) dabei, am Tag (aktiv_am_tag) nicht.
        "pv_morgen": Investition(anlage_id=a.id, typ="pv-module", bezeichnung="PV morgen",
                                 anschaffungsdatum=HEUTE + timedelta(days=1)),
        # Stilllegung heute: live nicht dabei, am Tag heute schon.
        "pv_bis_heute": Investition(anlage_id=a.id, typ="pv-module", bezeichnung="PV bis heute",
                                    anschaffungsdatum=date(2024, 1, 1), stilllegungsdatum=HEUTE),
    }
    for inv in geraete.values():
        db.add(inv)
    await db.flush()
    a.sensor_mapping = {
        "basis": {"live": {"netzbezug_w": "sensor.netzbezug"}},
        "investitionen": {
            str(inv.id): {"live": {"leistung_w": f"sensor.{name}_w"}} for name, inv in geraete.items()
        },
    }
    await db.commit()
    return a, geraete


def _keys(ergebnis) -> set[str]:
    return {s["key"] for s in ergebnis["serien"]}


# ── HA-Zweig ────────────────────────────────────────────────────────────────

@pytest.fixture
def ha_history(monkeypatch):
    async def fake_history(ids, start, end):
        return ({eid: [(start + timedelta(hours=10), 1000.0), (start + timedelta(hours=11), 1000.0)]
                 for eid in ids}, {eid: "W" for eid in ids})
    monkeypatch.setattr(ltv, "get_history_normalized", fake_history)


@pytest.mark.asyncio
async def test_ha_vorgestern_ist_die_gestern_stillgelegte_wallbox_in_betrieb(db, ha_verbindung, ha_history):
    ha_verbindung("token")
    a, g = await _anlage(db)
    erg = await ltv.get_tagesverlauf(a, db, tage_zurueck=2)
    keys = _keys(erg)
    assert f"wallbox_{g['wb'].id}" in keys            # am Tag in Betrieb …
    assert f"eauto_{g['auto'].id}" not in keys         # … und verdrängt das Auto (Regel 6)
    # Die beiden Heute-Grenzfälle am vergangenen Tag: PV „bis heute" lief, PV „morgen" noch nicht.
    assert f"pv_{g['pv_bis_heute'].id}" in keys
    assert f"pv_{g['pv_morgen'].id}" not in keys


@pytest.mark.asyncio
async def test_ha_heute_unveraendert_die_live_menge(db, ha_verbindung, ha_history):
    """Heute = `aktiv_jetzt()`: Wallbox (seit gestern still) fehlt ⇒ das Auto zeichnet; Anschaffung
    morgen zählt mit, Stilllegung heute nicht — genau wie vor N-565."""
    ha_verbindung("token")
    a, g = await _anlage(db)
    keys = _keys(await ltv.get_tagesverlauf(a, db, tage_zurueck=0))
    assert f"wallbox_{g['wb'].id}" not in keys
    assert f"eauto_{g['auto'].id}" in keys
    assert f"pv_{g['pv_morgen'].id}" in keys
    assert f"pv_{g['pv_bis_heute'].id}" not in keys


# ── MQTT-Zweig ──────────────────────────────────────────────────────────────

@pytest.fixture
def mqtt_snapshots(monkeypatch):
    from backend.services import mqtt_live_history_service as mlh
    geraete_ids: list[int] = []

    async def fake_range(anlage_id, start, end, db):
        zeilen = []
        for inv_id in geraete_ids:
            for h in (10, 11):
                zeilen.append(SimpleNamespace(component_key=f"inv:{inv_id}:leistung_w",
                                              timestamp=start.replace(hour=h), value_w=1000.0))
        return zeilen

    monkeypatch.setattr(mlh, "get_snapshots_for_range", fake_range)
    return geraete_ids


@pytest.mark.asyncio
async def test_mqtt_vorgestern_und_heute(db, ha_verbindung, mqtt_snapshots):
    ha_verbindung(None)                                # kein Token ⇒ MQTT-Zweig
    a, g = await _anlage(db)
    mqtt_snapshots.extend(inv.id for inv in g.values())
    vorgestern = _keys(await ltv.get_tagesverlauf(a, db, tage_zurueck=2))
    assert f"wallbox_{g['wb'].id}" in vorgestern
    assert f"pv_{g['pv_bis_heute'].id}" in vorgestern
    assert f"pv_{g['pv_morgen'].id}" not in vorgestern
    heute = _keys(await ltv.get_tagesverlauf(a, db, tage_zurueck=0))
    assert f"wallbox_{g['wb'].id}" not in heute
    assert f"pv_{g['pv_morgen'].id}" in heute
    assert f"pv_{g['pv_bis_heute'].id}" not in heute


def test_filter_je_tag_heute_ist_aktiv_jetzt():
    """Der Helfer selbst: heute die Live-Menge, sonst der Tag."""
    from backend.utils.investition_filter import aktiv_am_tag, aktiv_jetzt
    tag = HEUTE - timedelta(days=3)
    assert str(ltv._investitionen_des_tages(0, HEUTE)) == str(aktiv_jetzt())
    assert str(ltv._investitionen_des_tages(3, tag)) == str(aktiv_am_tag(tag))
