"""#398 — der aktuelle Betriebsmodus verlässt eedc: Sensor · Klartext · Icon.

Gemeldet von **MartyBr** (Forum simon42, Thema 89667, Beitrag 223) nach v4.0.29:
*„Schaltet das Icon WP auch bei Kühlung um?"* Die Messung dazu ergab, dass der
Modus zwar **stündlich mitgeschrieben** wird, den Zustand **jetzt** aber niemand
liest — die Live-Hälfte war gebaut und hatte null Aufrufer (N-333).

⚠ **Ehrlich zur Belegbarkeit:** Es gibt **kein Testgerät im Zugriff** — dieselbe
Lage wie bei #263 K-2. Alles hier läuft gegen eine echte SQLite-Instanz und
einen **gestellten HA-Zustandsdienst**; die Zuordnung entsteht über
`sensor_mapping`, so wie sie im Produkt entsteht.

**Worauf es ankommt — und warum jede Probe existiert:**

1. `test_innengeraet_key_wird_aufgeloest` — mit einer Innengeräte-Liste heißt der
   Key `betriebsmodus-3`. Ein Leser, der nur den nackten Namen prüft, hält eine
   vollständig zugeordnete Anlage für unzugeordnet. Genau dieser Fehler ist im
   Daten-Checker schon einmal passiert und dort namentlich vermerkt.
2. `test_ohne_zuordnung_kein_eintrag` / `test_unbekannter_zustand_faellt_weg` —
   die P4-Grenze: `None` heißt „nicht hingesehen", `unbestimmt` heißt
   „hingesehen, Seite nicht zuordenbar". Wer beides zusammenwirft, macht aus
   einer fehlenden Zuordnung eine Aussage über das Gerät.
3. `test_hvac_action_schlaegt_den_eingestellten_modus` — die Vorrangregel, deren
   Verlust am 20.08. **jedem Gerät mit Ist-Signal** die Aufteilung gekostet hat.
4. `test_sensor_erscheint_nur_mit_modus` — ein Sensor, der ohne Zuordnung mit
   „—" erschiene, lebte in der HA-Langzeitstatistik für immer weiter.
5. `test_zweiter_aufruf_kostet_keinen_ha_abruf` — der **Takt**. Er ist die
   Bedingung, unter der der frühere Entscheid gegen das Live-Lesen aufgelöst
   wurde (`live_komponenten_builder`: „Dauerabruf gegen ein Symbol"). Ohne
   diese Probe ist der 60-s-Takt eine Absichtserklärung.
"""

from __future__ import annotations

from datetime import date

import pytest

from backend.core.betriebsmodus import HEIZEN, KUEHLEN, LUEFTEN
from backend.services import betriebsmodus_live as bml


class _FakeHaService:
    """Ein HA, das genau die gestellten Zustände kennt — und mitzählt.

    ⚠ **Er zählt die Abrufe**, weil der Takt sonst nicht prüfbar wäre: „liefert
    zweimal dasselbe" beweist noch keinen Cache, das täte ein zweiter Abruf mit
    gleichem Ergebnis auch.
    """

    def __init__(self, zustaende: dict, verfuegbar: bool = True):
        self._zustaende = zustaende
        self.is_available = verfuegbar
        self.abrufe = 0

    async def get_zustand_states_batch(self, entity_ids):
        self.ab_ids = list(entity_ids)
        self.abrufe += 1
        return {eid: self._zustaende.get(eid) for eid in entity_ids}


@pytest.fixture(autouse=True)
def _takt_zuruecksetzen():
    """Jede Probe startet ohne Cache — sonst hinge sie an der Reihenfolge."""
    bml.cache_leeren()
    yield
    bml.cache_leeren()


def _stelle_ha(monkeypatch, zustaende: dict, verfuegbar: bool = True) -> _FakeHaService:
    dienst = _FakeHaService(zustaende, verfuegbar)
    monkeypatch.setattr(
        "backend.services.ha_state_service.get_ha_state_service", lambda: dienst
    )
    return dienst


async def _anlage_mit_wp(db, *, live: dict | None = None, typ: str = "waermepumpe"):
    """Anlage + ein Gerät, Zuordnung über `sensor_mapping` wie im Produkt."""
    from backend.models import Anlage, Investition

    anlage = Anlage(anlagenname="398", leistung_kwp=10.0,
                    installationsdatum=date(2025, 1, 1))
    db.add(anlage)
    await db.flush()
    inv = Investition(
        anlage_id=anlage.id, typ=typ, bezeichnung="Klima Wohnzimmer",
        anschaffungsdatum=date(2025, 1, 1), anschaffungskosten_gesamt=6000.0,
        parameter={"wp_art": "luft_luft"},
    )
    db.add(inv)
    await db.flush()
    if live is not None:
        anlage.sensor_mapping = {"investitionen": {str(inv.id): {"live": live}}}
    await db.commit()
    return anlage, inv


# ── 1 · Auflösung ────────────────────────────────────────────────────────────

async def test_modus_wird_gelesen(db, monkeypatch):
    anlage, inv = await _anlage_mit_wp(db, live={"betriebsmodus": "climate.wohnzimmer"})
    _stelle_ha(monkeypatch, {"climate.wohnzimmer": ("cool", None)})

    assert await bml.lade_betriebsmodus_live(db, anlage) == {inv.id: KUEHLEN}


async def test_innengeraet_key_wird_aufgeloest(db, monkeypatch):
    """`betriebsmodus-3` ist derselbe Feld-Key, nur je Innengerät.

    Gegenprobe zur Bauform, die im Daten-Checker einmal danebenlag: wer auf den
    nackten Namen prüft, findet hier **nichts** und meldet „nicht zugeordnet".
    """
    anlage, inv = await _anlage_mit_wp(db, live={"betriebsmodus-3": "climate.og"})
    _stelle_ha(monkeypatch, {"climate.og": ("heat", None)})

    assert await bml.lade_betriebsmodus_live(db, anlage) == {inv.id: HEIZEN}


async def test_zwei_innengeraete_an_einer_entitaet(db, monkeypatch):
    """Konzept D3: der Modus gehört dem Außengerät — beide Geräte tragen ihn.

    Kein Grund, das zweite zu verwerfen: in einer 2-Rohr-Anlage kann ein
    Innengerät nicht heizen, während ein anderes kühlt.
    """
    from backend.models import Investition

    anlage, inv1 = await _anlage_mit_wp(db, live={"betriebsmodus": "climate.aussen"})
    inv2 = Investition(
        anlage_id=anlage.id, typ="waermepumpe", bezeichnung="Klima Schlafzimmer",
        anschaffungsdatum=date(2025, 1, 1), anschaffungskosten_gesamt=3000.0,
        parameter={"wp_art": "luft_luft"},
    )
    db.add(inv2)
    await db.flush()
    anlage.sensor_mapping = {
        "investitionen": {
            str(inv1.id): {"live": {"betriebsmodus": "climate.aussen"}},
            str(inv2.id): {"live": {"betriebsmodus": "climate.aussen"}},
        }
    }
    await db.commit()
    _stelle_ha(monkeypatch, {"climate.aussen": ("dry", None)})

    ergebnis = await bml.lade_betriebsmodus_live(db, anlage)
    assert ergebnis == {inv1.id: "entfeuchten", inv2.id: "entfeuchten"}


# ── 2 · Die P4-Grenze: nichts erfinden ───────────────────────────────────────

async def test_ohne_zuordnung_kein_eintrag(db, monkeypatch):
    anlage, _ = await _anlage_mit_wp(db, live={})
    dienst = _stelle_ha(monkeypatch, {"climate.wohnzimmer": ("cool", None)})

    assert await bml.lade_betriebsmodus_live(db, anlage) == {}
    assert dienst.abrufe == 0, "ohne Zuordnung darf HA gar nicht erst gefragt werden"


async def test_unbekannter_zustand_faellt_weg(db, monkeypatch):
    """`unavailable` ist **kein** Modus — und wird auch nicht zu `unbestimmt`."""
    anlage, _ = await _anlage_mit_wp(db, live={"betriebsmodus": "climate.x"})
    _stelle_ha(monkeypatch, {"climate.x": ("unavailable", None)})

    assert await bml.lade_betriebsmodus_live(db, anlage) == {}


async def test_ohne_ha_kein_modus(db, monkeypatch):
    """Standalone/MQTT-only: der Modus ist dort nicht zu haben — und wird nicht
    ersatzweise behauptet."""
    anlage, _ = await _anlage_mit_wp(db, live={"betriebsmodus": "climate.x"})
    _stelle_ha(monkeypatch, {"climate.x": ("heat", None)}, verfuegbar=False)

    assert await bml.lade_betriebsmodus_live(db, anlage) == {}


async def test_hvac_action_schlaegt_den_eingestellten_modus(db, monkeypatch):
    """Das Gerät steht auf `heat_cool`, tut aber nachweislich etwas Bestimmtes.

    Ohne die Vorrangregel liefe `heat_cool` in `unbestimmt` — der Fehler, der am
    20.08. jedem Gerät mit Ist-Signal die gesamte Aufteilung gekostet hat.
    """
    anlage, inv = await _anlage_mit_wp(db, live={"betriebsmodus": "climate.x"})
    _stelle_ha(monkeypatch, {"climate.x": ("heat_cool", "cooling")})

    assert await bml.lade_betriebsmodus_live(db, anlage) == {inv.id: KUEHLEN}


async def test_stillgelegtes_geraet_meldet_nichts(db, monkeypatch):
    """Ein stillgelegtes Gerät hat keinen aktuellen Betrieb — auch dann nicht,
    wenn die Zuordnung stehen geblieben ist."""
    anlage, inv = await _anlage_mit_wp(db, live={"betriebsmodus": "climate.x"})
    inv.stilllegungsdatum = date(2025, 2, 1)
    await db.commit()
    _stelle_ha(monkeypatch, {"climate.x": ("heat", None)})

    assert await bml.lade_betriebsmodus_live(db, anlage) == {}


# ── 3 · Der Takt — die Bedingung des aufgelösten Entscheids ──────────────────

async def test_zweiter_aufruf_kostet_keinen_ha_abruf(db, monkeypatch):
    """Der 60-s-Takt ist die Bedingung, unter der der frühere Entscheid gegen
    das Live-Lesen aufgelöst wurde. Ohne ihn wäre es der „Dauerabruf gegen ein
    Symbol", gegen den `live_komponenten_builder` argumentiert hat.
    """
    anlage, inv = await _anlage_mit_wp(db, live={"betriebsmodus": "climate.x"})
    dienst = _stelle_ha(monkeypatch, {"climate.x": ("fan_only", None)})

    erst = await bml.lade_betriebsmodus_live(db, anlage)
    zweit = await bml.lade_betriebsmodus_live(db, anlage)

    assert erst == zweit == {inv.id: LUEFTEN}
    assert dienst.abrufe == 1, "der zweite Aufruf muss aus dem Takt-Cache kommen"


# ── 4 · Der Sensor (E-2) ─────────────────────────────────────────────────────

async def _wp_sensor(db, inv, modus_map):
    from backend.api.routes.ha_export import calculate_investition_sensors

    sensoren = await calculate_investition_sensors(db, inv, None, None, modus_map)
    return {s.definition.key: s.value for s in sensoren}


async def test_sensor_traegt_den_klartext(db):
    anlage, inv = await _anlage_mit_wp(db, live={"betriebsmodus": "climate.x"})
    werte = await _wp_sensor(db, inv, {inv.id: KUEHLEN})
    assert werte.get("wp_betriebsmodus") == "Kühlen"


async def test_sensor_erscheint_nur_mit_modus(db):
    """Ohne Modus **kein Sensor** — kein „—", keine Entität, die in der
    HA-Langzeitstatistik für immer weiterlebt."""
    anlage, inv = await _anlage_mit_wp(db, live={})
    werte = await _wp_sensor(db, inv, {})
    assert "wp_betriebsmodus" not in werte


# ── 5 · Das Icon (E-3) ───────────────────────────────────────────────────────

def test_icon_kanon_deckt_die_messbaren_modi():
    """Ein Symbol je Betriebsart, die etwas tut — und **keins** für „aus"
    und „unbestimmt": ein Sondersymbol für „ich weiß es nicht" wäre eine
    Aussage, die eedc nicht hat.
    """
    from backend.core.betriebsmodus import (
        AUS, BETRIEBSMODUS_ICON, ENTFEUCHTEN, UNBESTIMMT,
    )

    assert set(BETRIEBSMODUS_ICON) == {HEIZEN, KUEHLEN, ENTFEUCHTEN, LUEFTEN}
    assert AUS not in BETRIEBSMODUS_ICON and UNBESTIMMT not in BETRIEBSMODUS_ICON
    # Eine Datenrolle, ein Symbol (Regel 0a): `droplets` trägt im Live-Bild
    # bereits das WARMWASSER.
    assert BETRIEBSMODUS_ICON[ENTFEUCHTEN] != "droplets"
    assert len(set(BETRIEBSMODUS_ICON.values())) == len(BETRIEBSMODUS_ICON)


def test_icons_sind_im_client_registriert():
    """Ein Symbolname, den der Client nicht kennt, rendert nichts — und das
    fiele erst an der laufenden Box auf.

    Deshalb die Kanon-Namen gegen die `ICON_MAP` des Energiefluss-SVG. Sie ist
    die **einzige** Fläche, auf der der Wechsel stattfindet (Entscheid
    Maintainer 27.08.); `lib/komponentenStyle.ts` bleibt bewusst unberührt.
    """
    from pathlib import Path

    from backend.core.betriebsmodus import BETRIEBSMODUS_ICON

    quelle = (
        Path(__file__).resolve().parents[2]
        / "frontend/src/components/live/EnergieFluss.tsx"
    ).read_text(encoding="utf-8")
    block = quelle.split("const ICON_MAP", 1)[1].split("}", 1)[0]
    for name in BETRIEBSMODUS_ICON.values():
        assert f"{name}:" in block, f"ICON_MAP kennt den Namen {name} nicht"


# ── 6 · Der Weg nach draußen: MQTT ───────────────────────────────────────────

class _FakeMqttClient:
    """Ein Broker, der mitschreibt, WAS unter WELCHEM Gerät publiziert wurde."""

    def __init__(self):
        self.is_available = True
        self.laeufe: list[tuple[int | None, list[str]]] = []

    async def publish_all_sensors(self, sensor_values, anlage_id, anlage_name,
                                  investition_id=None, investition_name=None):
        self.laeufe.append((investition_id, [s.definition.key for s in sensor_values]))
        return {"total": len(sensor_values), "success": len(sensor_values),
                "failed": 0, "errors": []}


async def test_geraete_sensoren_erreichen_den_broker(db, monkeypatch):
    """⛔ **Bis zum 27.08. erreichten sie ihn nicht** — und damit stand #398
    Stufe 1 („als HA-Sensor und MQTT-Topic") nur auf dem Papier.

    Gemessen: `publish_anlage_sensors` war der EINZIGE MQTT-Publisher und kannte
    ausschließlich `calculate_anlage_sensors`. Alles, was je **Gerät** entsteht
    — Wärmepumpe, E-Auto, Investition — existierte nur im REST-Export. Für eine
    Add-on-Installation über MQTT-Discovery gab es diese Sensoren nicht.

    ⭐ **Der Apparat war vollständig gebaut und wurde nie gerufen:**
    `publish_all_sensors` nimmt seit jeher `investition_id`/`investition_name`
    und legt darunter ein eigenes HA-Gerät an. Dieselbe Klasse wie N-333.

    Diese Probe hält beides fest: dass je Gerät publiziert wird **und** dass es
    unter der Geräte-ID landet — ohne die zweite Hälfte lägen alle Geräte-
    Sensoren unter der Anlage und kollidierten bei zwei gleichartigen Geräten.
    """
    from backend.models import Monatsdaten
    from backend.services import ha_mqtt_sync

    anlage, inv = await _anlage_mit_wp(db, live={"betriebsmodus": "climate.x"})
    db.add(Monatsdaten(anlage_id=anlage.id, jahr=2025, monat=6,
                       einspeisung_kwh=100.0, netzbezug_kwh=50.0))
    await db.commit()
    _stelle_ha(monkeypatch, {"climate.x": ("cool", None)})

    klient = _FakeMqttClient()
    monkeypatch.setattr(ha_mqtt_sync, "MQTTClient", lambda *a, **k: klient)

    async def _broker(_db):
        return None

    monkeypatch.setattr(ha_mqtt_sync, "resolve_broker_config", _broker)

    ergebnis = await ha_mqtt_sync.publish_anlage_sensors(db, anlage)

    geraete_laeufe = [lauf for lauf in klient.laeufe if lauf[0] == inv.id]
    assert geraete_laeufe, "die Geräte-Sensoren wurden nicht publiziert"
    assert "wp_betriebsmodus" in geraete_laeufe[0][1]
    # Die Anlagen-Sensoren bleiben, wo sie waren — der Anschluss ist ein
    # Zuwachs, kein Umbau.
    assert any(lauf[0] is None for lauf in klient.laeufe)
    assert ergebnis["success"] == sum(len(k) for _, k in klient.laeufe)
