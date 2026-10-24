"""P-433-1 «Kompakt» (Konzept #433 Stufe 1, 24.10.2026) — die Backend-Hälfte.

Zwei Zusätze im Live-Pfad, beide **reine Anzeige**:

1. **`verbrauch_gesamt_kw`** (S1-2, Entscheid E7 a) — was das Haus jetzt
   verbraucht: ``Σ Quellen − Einspeisung − Σ Speicherladung − Abgabe``, aus
   denselben Summen wie der Restverbrauch, ohne den Erzeugungs-Guard der
   Autarkie-Gauge; ``None``, solange kein Netzwert vorliegt (P4). Proben nach
   dem Muster «Merkmale ändern keine Summe» (`test_341_live_merkmale.py`).
2. **Die gemessene Ruhe** (S1-4, Entscheid E6) — ``hvac_action: idle`` wird
   «Leerlauf» NEBEN dem Kanon-Wert. Der Kanon-Wert bleibt (#399: «heizen»
   bleibt «heizen»), und HA-Sensor/MQTT-Topic lesen ihn unverändert
   (`lade_betriebsmodus_live`). Keine Schwelle.

Schwesterdateien: ``test_398_betriebsmodus_live.py`` (Leser und Takt) ·
``test_398_live_betriebsmodus_klartext.py`` (Klartext im Live-Bild).
"""

from __future__ import annotations

from datetime import date

import pytest

from backend.api.routes.live_dashboard import (
    LiveDashboardResponse,
    LiveKomponente,
    _generate_demo_data,
)
from backend.core.betriebsmodus import (
    AUS,
    BETRIEBSMODUS_AKTION_LABEL,
    HEIZEN,
    KUEHLEN,
    LEERLAUF,
    UNBESTIMMT,
    betriebsmodus_aktion,
    normalisiere_betriebsmodus,
)
from backend.models.investition import Investition
from backend.services import betriebsmodus_live as bml
from backend.services.live_komponenten_builder import build_komponenten
from backend.services.live_power_service import LivePowerService
from backend.tests import factories


# ── Prüfstand: der Builder mit gestellten Werten ─────────────────────────────

def _inv(typ: str, **parameter) -> Investition:
    return Investition(typ=typ, bezeichnung=f"{typ} Probe", parameter=parameter)


def _baue(basis: dict, geraete: dict[str, tuple[Investition, float]], **kw) -> dict:
    """``geraete``: ``{id: (Investition, leistung_w)}`` — je Gerät ein Leistungssensor."""
    return build_komponenten(
        factories.mach_anlage(leistung_kwp=10.0, standort_land="DE"),
        basis,
        {iid: {"leistung_w": w} for iid, (_inv_, w) in geraete.items()},
        {iid: inv for iid, (inv, _w) in geraete.items()},
        {iid: {"leistung_w": f"sensor.{iid}"} for iid in geraete},
        **kw,
    )


def _ev_plus_bezug(erzeugung_kw, einspeisung_kw, ladung_kw, entladung_kw, abgabe_kw, bezug_kw) -> float:
    """Die Form (b) — Autarkie-Nenner `_autarkie_gauges`, von Hand: EV + Bezug."""
    direkt = erzeugung_kw - einspeisung_kw - ladung_kw
    return direkt + entladung_kw - abgabe_kw + bezug_kw


# ── 1 · verbrauch_gesamt_kw ──────────────────────────────────────────────────

def test_tag_gesamt_ist_ev_plus_bezug_solange_keine_klemme_greift():
    """PV 5 kW, Einspeisung 1,5, Speicher lädt 1,0, WP 1,2 ⇒ gesamt 2,5 = WP + Rest."""
    res = _baue(
        {"pv_gesamt_w": 5000.0, "einspeisung_w": 1500.0, "netzbezug_w": 0.0},
        {"3": (_inv("speicher"), 1000.0), "7": (_inv("waermepumpe"), 1200.0)},
    )
    soll = _ev_plus_bezug(5.0, 1.5, 1.0, 0.0, 0.0, 0.0)
    assert res["verbrauch_gesamt_kw"] == pytest.approx(soll) == pytest.approx(2.5)
    rest = next(k for k in res["komponenten"] if k["key"] == "haushalt")["verbrauch_kw"]
    assert res["verbrauch_gesamt_kw"] == pytest.approx(rest + 1.2)
    # Merkmal ändert keine Summe: die Bilanz-Identität des Builders bleibt.
    assert res["summe_erzeugung_kw"] == pytest.approx(res["summe_verbrauch_kw"])


def test_nacht_gesamt_ist_bezug_minus_netzladung_ohne_erzeugungs_guard():
    """Erzeugung 0 — die Autarkie-Gauge rechnet nicht, das Feld schon."""
    res = _baue(
        {"pv_gesamt_w": 0.0, "einspeisung_w": 0.0, "netzbezug_w": 2500.0},
        {"3": (_inv("speicher"), 2000.0)},
    )
    assert res["verbrauch_gesamt_kw"] == pytest.approx(2.5 - 2.0)
    assert not any(g["key"] == "autarkie" for g in res["gauges"]), "die Gauge bleibt hinter ihrem Guard"
    assert res["summe_erzeugung_kw"] == pytest.approx(res["summe_verbrauch_kw"])


def test_entladung_zaehlt_als_quelle_und_bleibt_drin():
    """Speicher entlädt 1,5 kW nachts, Bezug 0,3 ⇒ gesamt 1,8 (= EV + Bezug)."""
    res = _baue(
        {"pv_gesamt_w": 0.0, "einspeisung_w": 0.0, "netzbezug_w": 300.0},
        {"3": (_inv("speicher"), -1500.0)},
    )
    assert res["verbrauch_gesamt_kw"] == pytest.approx(_ev_plus_bezug(0.0, 0.0, 0.0, 1.5, 0.0, 0.3))


def test_abgabe_an_dritte_wird_abgezogen():
    """§9.2: abgegebene Leistung verbraucht nicht das Haus."""
    res = _baue(
        {"pv_gesamt_w": 4000.0, "einspeisung_w": 0.0, "netzbezug_w": 500.0},
        {"13": (_inv("sonstiges", kategorie="abgabe"), 800.0)},
    )
    assert res["verbrauch_gesamt_kw"] == pytest.approx(_ev_plus_bezug(4.0, 0.0, 0.0, 0.0, 0.8, 0.5))
    assert res["verbrauch_gesamt_kw"] == pytest.approx(3.7)


def test_ohne_netzwert_kein_gesamtverbrauch():
    """P4: ohne Netz ist die Bilanz offen — `None`, keine erfundene 0."""
    res = _baue({"pv_gesamt_w": 3000.0}, {"7": (_inv("waermepumpe"), 900.0)})
    assert res["verbrauch_gesamt_kw"] is None


def test_messversatz_klemmt_auf_null_wie_der_restverbrauch():
    """Einspeisung über der Erzeugung (Sensoren nicht gleichzeitig) — kein negativer Hausverbrauch."""
    res = _baue({"pv_gesamt_w": 1000.0, "einspeisung_w": 1500.0, "netzbezug_w": None}, {})
    assert res["verbrauch_gesamt_kw"] == 0.0


def test_leere_antwort_und_schema_kennen_das_feld():
    """`_empty_response` → `None`; FastAPI verwirft Undeklariertes still — es muss im Modell stehen."""
    leer = LivePowerService._empty_response(LivePowerService(), factories.mach_anlage(id=1))
    assert "verbrauch_gesamt_kw" in leer and leer["verbrauch_gesamt_kw"] is None
    assert "verbrauch_gesamt_kw" in LiveDashboardResponse.model_fields


def test_demo_daten_tragen_einen_gesamtverbrauch_aus_ihren_verbrauchern():
    """Sonst zeigt die Galerie die Zeile nie — und der Wert ist die Summe der Hausverbraucher."""
    for _ in range(20):
        d = _generate_demo_data(1, "Demo")
        LiveDashboardResponse(**d)
        verbraucher = sum(
            k["verbrauch_kw"] or 0 for k in d["komponenten"]
            if not k.get("parent_key") and k["key"] not in ("netz", "batterie_3")
        )
        assert d["verbrauch_gesamt_kw"] == pytest.approx(verbraucher, abs=0.02)


# ── 2 · Leerlauf neben dem Kanon-Wert ────────────────────────────────────────

def test_idle_laesst_den_kanon_stehen_und_wird_leerlauf():
    """#399 bleibt: «heat» + idle ⇒ Kanon `heizen`; neu nur die Aktion daneben."""
    assert normalisiere_betriebsmodus("heat", "idle") == HEIZEN
    assert betriebsmodus_aktion(HEIZEN, "idle") == LEERLAUF
    assert betriebsmodus_aktion(KUEHLEN, " Idle ") == LEERLAUF
    assert BETRIEBSMODUS_AKTION_LABEL[LEERLAUF] == "Leerlauf"


@pytest.mark.parametrize("kanon,aktion", [
    (HEIZEN, "heating"),   # Richtung — steckt schon im Kanon-Wert
    (HEIZEN, None),        # keine Aktion gemeldet
    (AUS, "idle"),         # «Aus» sagt es schon
    (UNBESTIMMT, "idle"),  # kein Klartext im Live-Bild
    (None, "idle"),        # nicht hingesehen
])
def test_keine_aktion_wird_erfunden(kanon, aktion):
    assert betriebsmodus_aktion(kanon, aktion) is None


def test_builder_haengt_die_aktion_nur_an_ein_geraet_mit_klartext():
    geraete = {"7": (_inv("waermepumpe"), 8.0), "8": (_inv("waermepumpe"), 0.0)}
    res = _baue(
        {"pv_gesamt_w": 0.0, "einspeisung_w": 0.0, "netzbezug_w": 100.0}, geraete,
        modus_map={7: HEIZEN, 8: UNBESTIMMT}, aktion_map={7: LEERLAUF, 8: LEERLAUF},
    )
    wp7 = next(k for k in res["komponenten"] if k["key"] == "waermepumpe_7")
    wp8 = next(k for k in res["komponenten"] if k["key"] == "waermepumpe_8")
    assert (wp7["betriebsmodus"], wp7["betriebsmodus_label"]) == (HEIZEN, "Heizen"), "Kanon unverändert"
    assert (wp7["betriebsmodus_aktion"], wp7["betriebsmodus_aktion_label"]) == (LEERLAUF, "Leerlauf")
    assert "betriebsmodus_aktion" not in wp8, "unbestimmt hat keinen Klartext — also auch keinen Zusatz"
    assert LiveKomponente(**wp7).betriebsmodus_aktion == LEERLAUF


def test_ohne_aktion_bleibt_der_knoten_wie_bisher():
    res = _baue(
        {"pv_gesamt_w": 0.0, "einspeisung_w": 0.0, "netzbezug_w": 1300.0},
        {"7": (_inv("waermepumpe"), 1200.0)}, modus_map={7: HEIZEN},
    )
    wp = next(k for k in res["komponenten"] if k["key"] == "waermepumpe_7")
    assert "betriebsmodus_aktion" not in wp and "betriebsmodus_aktion_label" not in wp


class _FakeHa:
    def __init__(self, zustaende: dict):
        self._z = zustaende
        self.is_available = True
        self.abrufe = 0

    async def get_zustand_states_batch(self, entity_ids):
        self.abrufe += 1
        return {eid: self._z.get(eid) for eid in entity_ids}


@pytest.fixture(autouse=True)
def _takt():
    bml.cache_leeren()
    yield
    bml.cache_leeren()


async def test_leser_kanon_fuer_export_aktion_fuer_anzeige_ein_abruf(db, monkeypatch):
    """Der HA-/MQTT-Export liest `lade_betriebsmodus_live` — dort steht weiter nur der Kanon-Wert."""
    from backend.models import Anlage

    dienst = _FakeHa({"climate.wp": ("heat", "idle")})
    monkeypatch.setattr("backend.services.ha_state_service.get_ha_state_service", lambda: dienst)
    anlage = Anlage(anlagenname="433-1", leistung_kwp=10.0, installationsdatum=date(2025, 1, 1))
    db.add(anlage)
    await db.flush()
    inv = Investition(anlage_id=anlage.id, typ="waermepumpe", bezeichnung="Nibe",
                      anschaffungsdatum=date(2025, 1, 1), anschaffungskosten_gesamt=1.0, parameter={})
    db.add(inv)
    await db.flush()
    anlage.sensor_mapping = {"investitionen": {str(inv.id): {"live": {"betriebsmodus": "climate.wp"}}}}
    await db.commit()

    assert await bml.lade_betriebsmodus_live(db, anlage) == {inv.id: HEIZEN}
    assert await bml.lade_betriebsmodus_aktion_live(db, anlage) == {inv.id: LEERLAUF}
    assert dienst.abrufe == 1, "die Aktion kommt aus demselben Abruf und Takt"


async def test_leser_heating_ergibt_keine_aktion(db, monkeypatch):
    from backend.models import Anlage

    monkeypatch.setattr("backend.services.ha_state_service.get_ha_state_service",
                        lambda: _FakeHa({"climate.wp": ("heat", "heating")}))
    anlage = Anlage(anlagenname="433-1b", leistung_kwp=10.0, installationsdatum=date(2025, 1, 1))
    db.add(anlage)
    await db.flush()
    inv = Investition(anlage_id=anlage.id, typ="waermepumpe", bezeichnung="Nibe",
                      anschaffungsdatum=date(2025, 1, 1), anschaffungskosten_gesamt=1.0, parameter={})
    db.add(inv)
    await db.flush()
    anlage.sensor_mapping = {"investitionen": {str(inv.id): {"live": {"betriebsmodus": "climate.wp"}}}}
    await db.commit()

    assert await bml.lade_betriebsmodus_live(db, anlage) == {inv.id: HEIZEN}
    assert await bml.lade_betriebsmodus_aktion_live(db, anlage) == {}
