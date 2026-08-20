"""F-53 — ein zugeordneter Betriebsmodus zeigt seinen Wert, statt „–".

**Der Fehler, gemeldet von kingcap1 (#263, 19.08.2026):** Er ordnete
`climate.klima_glen` als Betriebsmodus zu; HA meldete `cool`, die Fläche zeigte
„–". Ursache war eine Zeile in `_ha_states_detail`: `float(state)` warf jeden
nicht-numerischen State weg. **Ein Zustandsfeld ist per Definition nie
numerisch** — die Anzeige konnte also nie etwas zeigen, und der Anwender konnte
seine Zuordnung nicht von einem Ausfall unterscheiden.

⚠ **Warum diese Probe die Route fährt und nicht den Helfer.** Der Kanon-Helfer
`betriebsmodus_klartext` allein wäre grün gewesen, während die Fläche weiter „–"
zeigt — genau die Lücke, die F-52 im Nachbar-Bauteil hatte. Gemessen wird
deshalb, was am Endpunkt herauskommt: die Weiche `zustand` und die Antwort.
Der HA-Zugriff ist der **einzige** gemockte Teil.
"""

from __future__ import annotations

import pytest

from backend.api.routes import datenquellen as dq_modul
from backend.api.routes.datenquellen import get_datenquellen_felder
from backend.models.anlage import Anlage
from backend.models.investition import Investition
from backend.models.mqtt_gateway_mapping import MqttGatewayMapping  # noqa: F401

_MODUS_ENTITY = "climate.klima_glen"
_ENERGIE_ENTITY = "sensor.shelly_ip179_energy"


def _states(modus_state: str) -> list[dict]:
    """Genau die zwei Entities aus kingcap1s Bildern."""
    return [
        {"entity_id": _MODUS_ENTITY, "state": modus_state,
         "attributes": {"friendly_name": "Klima Glen Büro"}},
        {"entity_id": _ENERGIE_ENTITY, "state": "3194.35",
         "attributes": {"friendly_name": "KlimaSplit-IP179 Energie",
                        "unit_of_measurement": "kWh",
                        "state_class": "total_increasing"}},
    ]


async def _anlage_mit_zuordnung(db, modus_state: str, monkeypatch):
    """Klimaanlage mit zugeordnetem Modus **und** Energiezähler (die Gegenprobe)."""
    anlage = Anlage(
        anlagenname="F53", leistung_kwp=10.0,
        sensor_mapping={"investitionen": {}},
    )
    db.add(anlage)
    await db.flush()
    inv = Investition(
        anlage_id=anlage.id, typ="waermepumpe", bezeichnung="KlimaSplit Mitsubishi",
        parameter={"wp_art": "luft_luft"},
    )
    db.add(inv)
    await db.flush()
    # ⚠ **Die Form ist nicht frei gewählt**, sie ist aus einer laufenden Instanz
    # abgelesen — nach `POST …/felder/{id}/quelle`, also dem Anwender-Klick.
    # Maßgeblich für die Auflösung ist der Block `quellen`, adressiert über die
    # Feld-ID; die Spiegel unter `investitionen` schreibt die Route zusätzlich
    # für die Engine.
    #
    # ⛔ **Zwei Entwürfe dieser Probe lagen vorher daneben** (Betriebsmodus
    # unter `felder`, dann flach unter `live`) — beide Formen erzeugt die
    # Produktion nie, die Auflösung lieferte `quelle: "keine"`, und ohne die
    # Zusicherung auf `wert_text` wäre die Probe grün gewesen, ohne irgendetwas
    # zu messen. [[feedback_probe_unerreichbarer_zustand]]
    anlage.sensor_mapping = {
        "quellen": {
            f"inv_live_{inv.id}_betriebsmodus": {
                "quelle": "ha_app", "entity_id": _MODUS_ENTITY,
            },
            f"inv_energy_{inv.id}_stromverbrauch_kwh": {
                "quelle": "ha_app", "entity_id": _ENERGIE_ENTITY,
            },
        },
        "investitionen": {str(inv.id): {
            "felder": {
                "stromverbrauch_kwh": {"strategie": "sensor", "sensor_id": _ENERGIE_ENTITY},
            },
            "live": {"betriebsmodus": _MODUS_ENTITY},
        }},
    }
    db.add(anlage)
    await db.flush()

    async def _fake_detail(_db, entity_ids):
        out = {}
        for st in _states(modus_state):
            eid = st["entity_id"]
            if eid not in entity_ids:
                continue
            roh = st["state"]
            try:
                wert = float(roh)
            except (ValueError, TypeError):
                wert = None
            attrs = st["attributes"]
            out[eid] = {
                "wert": wert,
                "wert_text": str(roh) if roh is not None else None,
                "einheit": attrs.get("unit_of_measurement"),
                "state_class": attrs.get("state_class"),
                "friendly_name": attrs.get("friendly_name"),
            }
        return out

    monkeypatch.setattr(dq_modul, "_ha_states_detail", _fake_detail)
    return anlage, inv


async def _feld(db, anlage_id, feld_key: str) -> dict:
    resp = await get_datenquellen_felder(anlage_id, db)
    for gruppe in resp["gruppen"]:
        for f in gruppe["felder"]:
            if f["feld"] == feld_key:
                return f
    raise AssertionError(f"Feld {feld_key} nicht in der Antwort")


@pytest.mark.asyncio
async def test_betriebsmodus_zeigt_klartext_und_rohwert(db, monkeypatch):
    """Der gemeldete Fall: HA sagt `cool`, die Fläche muss es zeigen."""
    anlage, _inv = await _anlage_mit_zuordnung(db, "cool", monkeypatch)
    feld = await _feld(db, anlage.id, "betriebsmodus")

    assert feld["zustand"] is True
    # `wert` bleibt leer — ein Zustand ist keine Zahl, und das ist kein Mangel.
    assert feld["wert"] is None
    assert feld["wert_text"] == "cool"
    assert feld["wert_klartext"] == "Kühlen"


@pytest.mark.asyncio
async def test_zahlenfeld_bleibt_unveraendert(db, monkeypatch):
    """Die Gegenprobe aus DEMSELBEN Batch: der Zähler zeigt weiter seine Zahl,
    und **nicht** zusätzlich denselben Wert als Text."""
    anlage, _inv = await _anlage_mit_zuordnung(db, "cool", monkeypatch)
    feld = await _feld(db, anlage.id, "stromverbrauch_kwh")

    assert feld["zustand"] is False
    assert feld["wert"] == pytest.approx(3194.35)
    assert feld["wert_text"] is None
    assert feld["wert_klartext"] is None


@pytest.mark.asyncio
async def test_unbekannte_schreibweise_heisst_unbestimmt(db, monkeypatch):
    """Der Anwender muss „verstanden" von „durchgewinkt" unterscheiden können.

    Ein Hersteller-State, den der Kanon nicht kennt, landet später in „nicht
    aufgeteilt" — hier steht er deshalb als *Unbestimmt* neben seinem Rohwert,
    statt still wie ein erkannter Modus auszusehen.
    """
    anlage, _inv = await _anlage_mit_zuordnung(db, "kuehlbetrieb_eco", monkeypatch)
    feld = await _feld(db, anlage.id, "betriebsmodus")

    assert feld["wert_text"] == "kuehlbetrieb_eco"
    assert feld["wert_klartext"] == "Unbestimmt"


@pytest.mark.asyncio
async def test_ausgefallene_entity_bleibt_leer(db, monkeypatch):
    """`unavailable` ist KEIN Modus — hier muss die Fläche weiter „–" zeigen,
    sonst verdeckt die Reparatur einen echten Ausfall."""
    anlage, _inv = await _anlage_mit_zuordnung(db, "unavailable", monkeypatch)
    feld = await _feld(db, anlage.id, "betriebsmodus")

    assert feld["wert"] is None
    assert feld["wert_klartext"] is None


def test_jeder_kanon_wert_hat_ein_label():
    """Deckungsprüfung Kanon ↔ Klartext — der Prüfer, der S10 gefangen hätte.

    Ein Sprengsatz auf den früheren `.get(..., fallback)` blieb **stumm**: der
    Fallback war strukturell unerreichbar. Gemessen gehört stattdessen, dass
    eine siebte Betriebsart nicht ohne Klartext bleibt. Dieselbe Bauform wie
    `test_feldnamen_folgen_dem_kanon` (Feldnamen ↔ `AUFGETEILTE_MODI`).
    """
    from backend.core.betriebsmodus import BETRIEBSMODUS_KANON, BETRIEBSMODUS_LABEL

    assert set(BETRIEBSMODUS_LABEL) == set(BETRIEBSMODUS_KANON)
    assert all(BETRIEBSMODUS_LABEL[m].strip() for m in BETRIEBSMODUS_KANON)
