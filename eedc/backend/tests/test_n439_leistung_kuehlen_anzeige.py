"""N-439 — „Leistung Kühlen" wird angezeigt, nicht nur angeboten.

**Die Lage bis zum 13.09.2026.** ``leistung_kuehlen_w`` steht seit W-13
(26.08.) an **jeder** Wärmepumpe zur Zuordnung bereit (SOLL §3.2a/**R1**: der
Zähler entscheidet, nicht die Bauart), und ``docs/WAS-IST-NEU.md`` versprach es
wörtlich als *„Live-Wert"*. Gelesen hat es **eine** Stelle im ganzen Baum:
``daten_checker/datenquelle.py``, und die nur als **Beleg**, dass ein Gerät
kühlt. Zwei Anwenderlagen folgten daraus, beide am Code gemessen:

* **Nur der Kühlsensor zugeordnet** ⇒ ``live_komponenten_builder`` fand weder
  ``leistung_heizen_w`` noch ``leistung_warmwasser_w``, ``val_w`` blieb ``None``
  — die Wärmepumpe **fehlte ganz** im Live-Bild und stand im Tagesverlauf unter
  *„Nicht dargestellt (kein HA-Leistungssensor)"*, obwohl einer zugeordnet war.
* **Alle drei zugeordnet, Gerät kühlt** ⇒ die Summe kannte zwei Summanden,
  ``0 + 0`` — die Wärmepumpe stand mit **0,0 kW** im Bild, während sie 2 kW zog.

**Was der Bau macht:** das Feld läuft den Pfad seiner beiden Nachbarn, Station
für Station. Es entsteht **keine** Kennzahl und **keine** Menge aus ihm (E4 —
Kühlen hat keine bewertete Nutzenergie; „reine Anzeige" im Registry-Hinweis
bleibt wörtlich gültig): Angezeigt wird die Strom-**Leistung**, und die ist eine
Menge der Größen-Matrix (``E_kühl``).

⚠ **Warum die drei Felder summiert werden dürfen** (K1): Sie sind
Momentanwerte **disjunkter** Betriebsarten desselben Kältekreises — ein
Umschaltventil, ein Verdichter (``core/betriebsmodus.py``: dietmar1968
T89667 #225, MartyBr #230). Summiert wird ohnehin nur, wenn **keine**
Gesamtleistung zugeordnet ist; ist sie da, gewinnt sie (K1: die Gesamtmenge ist
die Wahrheit).

## Warum diese Datei die echte Uhr liest

⚠ **Eine Ablesung, in einer Konstanten, die alle Proben teilen** (``_JETZT``) —
und sie ist unvermeidbar: Beide Tagesverlauf-Pfade verankern ihr Fenster
**selbst** an ``datetime.now()`` (``get_tagesverlauf`` / ``_get_tagesverlauf_mqtt``
rechnen ``start`` aus ``now`` und ``tage_zurueck``). Ein festes Datum in der
Fixture fiele aus diesem Fenster, die Antwort wäre leer und die Probe prüfte
nichts mehr. Derselbe Fall wie ``test_prognose_vergleich_bestand_je_tag.py``
(N-317); der andere Weg wäre ein gestellter Kalender, und ``freezegun`` ist am
23.08.2026 verworfen (Gernot).

⭐ **Stundenunabhängig ist sie trotzdem:** ``tage_zurueck=1`` erhebt den
**ganzen** Vortag ([00:00, 24:00)), die Messpunkte liegen um 12:00 — sie fallen
in jeder Zeitzone und zu jeder Laufstunde in dieses Fenster. Die kWh-Probe
darunter kommt ganz ohne Uhr aus (festes Datum).

Schwesterdateien: ``test_serien_aufbau_symmetrie_m1.py`` (die Serien-Selektion
und ihr Rückweg) · ``test_live_tagesverlauf_farben_kanon.py`` (die Rollenfarbe) ·
``test_bs7_gesamtleistung_hinweis.py`` (die Verdrängung durch „Leistung gesamt").
"""

from __future__ import annotations

from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from backend.models.investition import Investition
from backend.models.mqtt_live_snapshot import MqttLiveSnapshot
from backend.services.live_komponenten_builder import build_komponenten
from backend.services.live_sensor_config import (
    LEISTUNGS_FELDER,
    baue_investitions_serien,
    inv_ids_mit_serie,
    uebersprungene_investitionen,
)
from backend.tests import factories

HEIZEN = "leistung_heizen_w"
WARMWASSER = "leistung_warmwasser_w"
KUEHLEN = "leistung_kuehlen_w"
GESAMT = "leistung_w"

_BASIS = {"pv_gesamt_w": 3000.0, "einspeisung_w": 100.0, "netzbezug_w": None}


def _live_komponente(werte: dict[str, float]) -> dict:
    """Die Wärmepumpe, wie das Live-Bild sie liefert — eine Komponente, ein Wert."""
    inv = Investition(typ="waermepumpe", bezeichnung="Winterborn WP", parameter={})
    ergebnis = build_komponenten(
        factories.mach_anlage(leistung_kwp=5.0, standort_land="DE"),
        dict(_BASIS),
        {"7": dict(werte)},
        {"7": inv},
        {"7": {k: f"sensor.wp_{k}" for k in werte}},
    )
    return next(k for k in ergebnis["komponenten"] if k["key"] == "waermepumpe_7")


# ── K1 · Das Live-Bild trägt die Kühlleistung ───────────────────────────────

def test_nur_kuehlsensor_zugeordnet_die_waermepumpe_erscheint():
    """Der erste Fund: mit **nur** diesem Sensor gab es gar keine Komponente."""
    komp = _live_komponente({KUEHLEN: 2000.0})

    assert komp["verbrauch_kw"] == 2.0
    assert komp["erzeugung_kw"] is None
    # `snowflake` ist der Kanon-Name für Kühlen (`BETRIEBSMODUS_ICON`) — Regel 0a.
    assert komp["icon"] == "snowflake"


def test_alle_drei_zugeordnet_und_das_geraet_kuehlt():
    """Der zweite Fund: 0,0 kW im Bild, während das Gerät 2 kW zieht."""
    komp = _live_komponente({HEIZEN: 0.0, WARMWASSER: 0.0, KUEHLEN: 2000.0})

    assert komp["verbrauch_kw"] == 2.0
    assert komp["icon"] == "snowflake"


def test_die_gesamtleistung_gewinnt_gegen_die_summe():
    """K1 — die Gesamtmenge ist die Wahrheit, die Aufteilung steht daneben.

    Ohne diese Probe könnte die Summe die zugeordnete Gesamtleistung
    überschreiben und aus Teilmengen eine zweite, größere „Gesamtleistung"
    machen.
    """
    komp = _live_komponente({GESAMT: 1500.0, HEIZEN: 0.0, KUEHLEN: 2000.0})

    assert komp["verbrauch_kw"] == 1.5


# ── K5 · Die Nachbarn bleiben, was sie waren ────────────────────────────────

@pytest.mark.parametrize(
    "werte, kw, icon",
    [
        ({HEIZEN: 1200.0, WARMWASSER: 800.0}, 2.0, "heater"),
        ({HEIZEN: 300.0, WARMWASSER: 900.0}, 1.2, "droplets"),
        ({HEIZEN: 1500.0}, 1.5, "heater"),
        ({WARMWASSER: 700.0}, 0.7, "droplets"),
    ],
)
def test_heizen_und_warmwasser_unveraendert(werte, kw, icon):
    """Einzelwerte, nicht Summen: derselbe Wert und dasselbe Symbol wie vor dem Bau."""
    komp = _live_komponente(werte)

    assert komp["verbrauch_kw"] == kw
    assert komp["icon"] == icon


def test_bei_gleichstand_gewinnt_heizen_wie_bisher():
    """Die Reihenfolge der Heuristik bleibt — Kühlen schlägt nur, wenn es führt."""
    assert _live_komponente({HEIZEN: 1000.0, KUEHLEN: 1000.0})["icon"] == "heater"
    assert _live_komponente({HEIZEN: 999.0, KUEHLEN: 1000.0})["icon"] == "snowflake"


# ── K3 · Die Serie: Auswahl, Label, Farbe, Rückweg ──────────────────────────

def _inv(inv_id="7", bezeichnung="Winterborn WP"):
    return SimpleNamespace(
        id=inv_id, typ="waermepumpe", parameter={},
        parent_investition_id=None, bezeichnung=bezeichnung,
    )


def test_serien_bauer_liefert_die_kuehl_serie():
    serien, entities = baue_investitions_serien(
        {"7": {KUEHLEN: "sensor.wp_kuehl"}}, {"7": _inv()},
    )

    assert [s.key for s in serien] == ["waermepumpe_7_kuehlen"]
    assert serien[0].suffix == "kuehlen"
    assert serien[0].seite == "senke"
    assert entities["waermepumpe_7_kuehlen"] == ["sensor.wp_kuehl"]


def test_drei_felder_drei_serien_in_fester_reihenfolge():
    serien, _ = baue_investitions_serien(
        {"7": {HEIZEN: "sensor.h", WARMWASSER: "sensor.w", KUEHLEN: "sensor.k"}},
        {"7": _inv()},
    )

    assert [s.key for s in serien] == [
        "waermepumpe_7_heizen", "waermepumpe_7_warmwasser", "waermepumpe_7_kuehlen",
    ]


def test_kuehlsensor_zaehlt_als_leistungsquelle():
    """N-447-Symmetrie: Wer gezeichnet wird, steht nicht unter „nicht dargestellt".

    ⚑ **Befund über die Probe (13.09.2026, beim Sprengsatz gemessen):** Die
    erste Fassung prüfte nur die Lage „Serie da". Ein Sprengsatz, der
    ``leistung_kuehlen_w`` aus ``LEISTUNGS_FELDER`` **entfernt**, blieb daran
    still — weil die erste Klausel (`inv_id in inv_ids_mit_serie`) das Gerät
    schon abfängt. Dieselbe gegenseitige Deckung wie bei den zwei Nachbarn, die
    ``test_serien_aufbau_symmetrie_m1.py::
    test_keine_serie_traegt_die_meldung_auch_ohne_die_zweite_klausel``
    festhält. Deshalb steht die **zweite Klausel hier allein**, mit gestellter
    erster.
    """
    inv_live = {"7": {KUEHLEN: "sensor.k"}}
    investitionen = {"7": _inv()}
    serien, _ = baue_investitions_serien(inv_live, investitionen)
    assert len(serien) == 1, "Voraussetzung: sie WIRD gezeichnet"

    assert uebersprungene_investitionen(
        investitionen, inv_ids_mit_serie(serien),
        lambda i: any((inv_live.get(i) or {}).get(f) for f in LEISTUNGS_FELDER),
    ) == []

    # Die zweite Klausel für sich: der Serien-Bauer hat nichts geliefert, der
    # Kühlsensor ist trotzdem eine Leistungsquelle ⇒ der Satz „kein
    # HA-Leistungssensor" wäre eine Falschaussage.
    ohne_serie: set[str] = set()
    assert uebersprungene_investitionen(
        investitionen, ohne_serie,
        lambda i: any((inv_live.get(i) or {}).get(f) for f in LEISTUNGS_FELDER),
    ) == []
    # Gegenprobe: ohne jede Zuordnung wird dieselbe Lage gemeldet.
    assert uebersprungene_investitionen(
        investitionen, ohne_serie, lambda i: False,
    ) == ["Winterborn WP"]


def test_der_key_loest_zum_label_kuehlen_zurueck():
    """Der Rückweg über `TagesEnergieProfil.komponenten` in den Tag-Stundenverlauf."""
    from backend.api.routes.energie_profil._shared import _key_to_serie_info

    inv = Investition(typ="waermepumpe", bezeichnung="Winterborn WP", parameter={})
    info = _key_to_serie_info("waermepumpe_7_kuehlen", {7: inv})

    assert info["label"] == "Winterborn WP Kühlen"
    assert info["kategorie"] == "waermepumpe"


def test_die_kuehl_stunden_zaehlen_zur_waermepumpe():
    """Der Stundenwert der Kühl-Fläche gehört derselben Investition wie Heizen."""
    from backend.core.berechnungen import waermepumpe_kwh_je_investition

    assert waermepumpe_kwh_je_investition({
        "waermepumpe_7_heizen": -1.0,
        "waermepumpe_7_kuehlen": -0.5,
    }) == {"7": 1.5}


# ── K3b · Der Live-Tagesverlauf, beide Pfade, mit Einzelwerten ──────────────

def _mapping(inv_id: int) -> dict:
    """Zuordnung aller drei Leistungsfelder — ⚠ die Investitions-ID vergibt die
    DB, nicht der Test. Ein festes „7" im Mapping trifft die Investition nicht
    und liefert klaglos **keine** Serie (gemessen 13.09.2026)."""
    return {"investitionen": {str(inv_id): {"live": {
        HEIZEN: "sensor.h", WARMWASSER: "sensor.w", KUEHLEN: "sensor.k",
    }}}}


#: ⚠ **Die EINE Ablesung der Prozessuhr in dieser Datei** — Begründung im
#: Modul-Docstring (Abschnitt „Warum diese Datei die echte Uhr liest").
#: `test_konformitaet_echte_uhr_in_tests.py::_BASELINE` führt sie mit **1**.
_JETZT: datetime = datetime.now()


def _gestern(stunde: int, minute: int = 0) -> datetime:
    """Ein Zeitpunkt am Vortag — dem Tag, den ``tage_zurueck=1`` erhebt."""
    return (_JETZT - timedelta(days=1)).replace(
        hour=stunde, minute=minute, second=0, microsecond=0,
    )


@pytest.mark.asyncio
async def test_ha_tagesverlauf_zeichnet_die_kuehlflaeche(db):
    from backend.services import live_tagesverlauf_service as tv

    anlage = await factories.anlage(db, anlagenname="Kühlprobe")
    inv = await factories.investition(
        db, anlage.id, "waermepumpe", bezeichnung="Winterborn WP",
    )
    anlage.sensor_mapping = _mapping(inv.id)
    await db.flush()

    history = {
        "sensor.h": [(_gestern(12), 0.0), (_gestern(12, 5), 0.0)],
        "sensor.w": [(_gestern(12), 0.0), (_gestern(12, 5), 0.0)],
        "sensor.k": [(_gestern(12), 2000.0), (_gestern(12, 5), 2000.0)],
    }

    with patch("backend.services.ha_state_service.get_ha_state_service",
               return_value=SimpleNamespace(is_available=True)), \
         patch.object(tv, "get_history_normalized",
                      AsyncMock(return_value=(history, {}))), \
         patch.object(tv, "_baue_short_term_overlays", return_value=({}, {})), \
         patch("backend.services.strompreis_markt_service.get_strompreis_stunden",
               AsyncMock(return_value={})):
        out = await tv.get_tagesverlauf(anlage, db, tage_zurueck=1)

    kuehl_key = f"waermepumpe_{inv.id}_kuehlen"
    farben = {s["key"]: s for s in out["serien"]}
    assert farben[kuehl_key]["label"] == "Winterborn WP Kühlen"
    # sky-500 = CHART_COLORS.modusKuehlen = ROLLEN_BG.kuehlung (Regel 0a)
    assert farben[kuehl_key]["farbe"] == "#0ea5e9"
    # ⚠ Einzelwert an der Antwort: 2000 W als Senke ⇒ −2,0 kW im 12:00-Punkt.
    punkt = next(p for p in out["punkte"] if p["zeit"] == "12:00")
    assert punkt["werte"][kuehl_key] == -2.0
    # K5 — die Nachbarn stehen unverändert daneben, in ihren eigenen Farben.
    assert farben[f"waermepumpe_{inv.id}_heizen"]["farbe"] == "#ef4444"
    assert farben[f"waermepumpe_{inv.id}_warmwasser"]["farbe"] == "#3b82f6"
    assert farben[f"waermepumpe_{inv.id}_heizen"]["label"] == "Winterborn WP Heizen"


@pytest.mark.asyncio
async def test_mqtt_tagesverlauf_zeichnet_die_kuehlflaeche(db):
    """Derselbe Anwenderfall ohne Home Assistant — aus den 5-Minuten-Snapshots."""
    from backend.services import live_tagesverlauf_service as tv

    anlage = await factories.anlage(db, anlagenname="Kühlprobe MQTT")
    inv = await factories.investition(
        db, anlage.id, "waermepumpe", bezeichnung="Winterborn WP",
    )
    await db.flush()

    for minute in (0, 5):
        db.add(MqttLiveSnapshot(
            anlage_id=anlage.id, timestamp=_gestern(12, minute),
            component_key=f"inv:{inv.id}:leistung_kuehlen_w", value_w=2000.0,
        ))
    await db.flush()

    with patch("backend.services.strompreis_markt_service.get_strompreis_stunden",
               AsyncMock(return_value={})):
        out = await tv._get_tagesverlauf_mqtt(anlage, db, tage_zurueck=1)

    kuehl_key = f"waermepumpe_{inv.id}_kuehlen"
    kuehl = next(s for s in out["serien"] if s["key"] == kuehl_key)
    assert kuehl["label"] == "Winterborn WP Kühlen"
    assert kuehl["farbe"] == "#0ea5e9"
    punkt = next(p for p in out["punkte"] if p["zeit"] == "12:00")
    assert punkt["werte"][kuehl_key] == -2.0


# ── K3c · Die Tages-kWh je Komponente (Tooltip im Energiefluss) ─────────────

@pytest.mark.asyncio
async def test_tages_kwh_fuehrt_die_kuehl_komponente(db):
    from backend.services import live_history_service as lh

    anlage = await factories.anlage(
        db, anlagenname="Kühlprobe kWh", sensor_mapping=_mapping(7),
    )

    # ⭐ Festes Datum: ``get_tages_kwh`` filtert die gelieferte History **nicht**
    # gegen sein Fenster (die Trapezregel läuft über die übergebenen Punkte),
    # deshalb braucht diese Probe die Prozessuhr nicht.
    stunde = datetime(2026, 3, 15, 10, 0)
    history = {
        "sensor.k": [(stunde, 2000.0), (stunde + timedelta(hours=1), 2000.0)],
    }
    with patch.object(lh, "get_history_normalized",
                      AsyncMock(return_value=(history, {}))):
        out = await lh.get_tages_kwh(anlage, db, inv_types={"7": "waermepumpe"})

    # 2000 W über eine Stunde = 2,0 kWh — Einzelwert, keine Summe.
    assert out["waermepumpe_7_kuehlen"] == 2.0


# ── K2 · Der MQTT-Live-Snapshot schreibt den Key ────────────────────────────

@pytest.mark.asyncio
async def test_snapshot_schreibt_den_kuehl_key(db):
    """Ohne diesen Key gäbe es im Standalone-Betrieb keine Kühl-Kurve.

    ⭐ **Angepasst in HA-Bauform §9 (Standalone-Gleichstand S2, 25.10.2026), klassifiziert:** (1) der Snapshot liest
    die Fenster des Integrators im echten Inbound-Cache (``mittel_abschliessen``) statt eines Momentanwerts, nur bei
    lebender Verbindung und nur für Geräte der DB (die Keys je Typ aus ``mittelwert_live_keys``) — deshalb ein echter
    Cache und eine echte Wärmepumpe statt des Platzhalters; (2) die Warmwasser-Temperatur wird jetzt **mitgeschrieben**
    (Mittelwert-Mitschrift aus MQTT, S2-1) — bis S2 stand hier ``not in rows``. Die Kühl-Zusage bleibt wörtlich.
    """
    import time
    from contextlib import asynccontextmanager

    from backend.services import mqtt_live_history_service as mlh
    from backend.services.mqtt_inbound_service import MqttInboundCache

    anlage = await factories.anlage(db, anlagenname="Snapshot-Probe")
    wp = await factories.investition(db, anlage.id, "waermepumpe", bezeichnung="WP")
    await db.flush()

    cache = MqttInboundCache()
    cache.verbinden()
    t = time.time() - 120
    for key, wert in ((HEIZEN, "0"), (KUEHLEN, "2000"), ("warmwasser_temperatur_c", "48")):
        cache.on_message(f"eedc/{anlage.id}_P/live/inv/{wp.id}_WP/{key}", wert, jetzt=t)

    @asynccontextmanager
    async def _session():
        yield db

    with patch.object(mlh, "get_mqtt_inbound_service",
                      return_value=SimpleNamespace(cache=cache)), \
         patch.object(mlh, "get_session", _session):
        geschrieben = await mlh.snapshot_live_cache()

    assert geschrieben == 3
    rows = {
        r.component_key: r.value_w
        # Weites Fenster um die geteilte Ablesung: `snapshot_live_cache`
        # stempelt seine Zeilen mit der echten Uhr, die Auswahl soll sie in
        # jedem Fall finden — geprüft wird der KEY, nicht der Zeitstempel.
        for r in await mlh.get_snapshots_for_range(
            anlage.id, _JETZT - timedelta(days=1), _JETZT + timedelta(days=1), db,
        )
    }
    assert rows[f"inv:{wp.id}:leistung_kuehlen_w"] == 2000.0
    assert rows[f"inv:{wp.id}:leistung_heizen_w"] == 0.0
    assert rows[f"inv:{wp.id}:warmwasser_temperatur_c"] == 48.0, "seit S2 mitgeschrieben (Mittelwert-Mitschrift)"


# ── K3d · Die Zuordnungs-Fläche sagt es auch am dritten Feld ────────────────

def test_gesamtleistung_verdraengt_jetzt_auch_das_kuehlfeld():
    """SOLL §3.3/S3 — ein Hinweis an zwei von drei gleich behandelten Feldern
    wäre die Lücke, gegen die die Regel steht."""
    from backend.services.datenquellen_validierung import finde_gesamtleistung_verdraengt

    def _feld(feld: str):
        return {"id": f"inv_live_7_{feld}", "feld": feld, "typ": "waermepumpe",
                "inv_id": "7", "in_ha_live": True}

    out = finde_gesamtleistung_verdraengt(
        [_feld(GESAMT), _feld(HEIZEN), _feld(WARMWASSER), _feld(KUEHLEN)],
    )

    assert set(out) == {
        "inv_live_7_leistung_heizen_w",
        "inv_live_7_leistung_warmwasser_w",
        "inv_live_7_leistung_kuehlen_w",
    }
    text = out["inv_live_7_leistung_kuehlen_w"]["text"]
    assert "Leistung Kühlen" in text and "im Verlauf nicht aus" in text


def test_der_registry_hinweis_sagt_wo_das_feld_erscheint():
    """Die Zusage im Hinweis deckt genau das, was gebaut ist — nicht mehr."""
    from backend.core.field_definitions import LIVE_FELDER_INV

    feld = next(f for f in LIVE_FELDER_INV["waermepumpe"] if f["key"] == KUEHLEN)

    assert "reine Anzeige" in feld["hinweis"]
    assert "Live-Bild" in feld["hinweis"] and "Tagesverlauf" in feld["hinweis"]
