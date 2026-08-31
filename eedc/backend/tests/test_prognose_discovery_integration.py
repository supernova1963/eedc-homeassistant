"""Erkennung über die Integration statt über den Namen (Burkard #401, 31.08.2026).

**Der Fall des Melders.** Burkard hat seine Home-Assistant-Instanz auf Englisch
angelegt. Seine sechs SFML-Entitäten heißen ``sensor.none_expected_daily_
production``, ``sensor.none_forecast_today_remaining`` und so fort — sie fielen
durch die **Präfix**-Liste (kein ``sensor.solar_forecast_ml_``, kein
``sensor.prognose_``) **und** durch die **Suffix**-Liste (kein deutsches
``prognose_heute``). eedc fand null Rollen und sagte es nicht; er half sich mit
sechs Template-Sensoren, die seine Werte unter den gesuchten Namen spiegeln.

**Was hier geprüft wird** — die vier Lagen aus dem Bau-Auftrag, dazu die
Gegenprobe:

* Gernots Instanz (deutsch, gemischte Präfixe) findet weiterhin **alle** Rollen,
  jetzt über die ``unique_id``.
* Burkards Fall (englisch, ``sensor.none_*``) wird gefunden — er war vorher
  vollständig unsichtbar.
* Ein **vorangestellter Bereich** (``sensor.technik_solar_forecast_ml_…``)
  bricht die Erkennung nicht mehr; er bricht den Präfix, nicht die Integration.
* Fällt die Registry aus, trägt der **Anzeigename**; fällt auch der aus, trägt
  das **alte Muster**. ⛔ Der Rückfall ist der Kern der Zusage „niemand wird
  schlechter gestellt" — ohne ihn wäre der Bau eine Verschlechterung für jede
  HA-Version, die eine Stufe nicht liefert.
* **Gegenprobe:** Eine Entität einer *fremden* Integration mit passendem Namen
  wird **nicht** eingesammelt. Eine Mengenabgrenzung, die nur einschließt und
  nie ausschließt, ist keine.

Schwesterdateien: ``test_prognose_discovery_sfml.py`` (das Stundenprofil-Attribut
derselben Discovery), ``test_prognose_quelle_konsistenz.py`` (was der Live-Block
aus der gewählten Quelle macht) und ``test_solcast_tagesprofile_357.py`` (der
Solcast-Pfad, dessen Entity-Auflösung hier mitgeprüft wird).
"""

from __future__ import annotations

import httpx
import pytest

import backend.services.ha_integration_aufloeser as aufl
import backend.services.prognose_discovery as disc

# ── Testgerüst ───────────────────────────────────────────────────────────────


class _FakeResp:
    status_code = 200

    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload


class _FakeClient:
    def __init__(self, payload):
        self._payload = payload

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def get(self, *args, **kwargs):
        return _FakeResp(self._payload)


class _FakeHA:
    is_available = True
    api_url = "http://ha.local/api"
    token = "tok"


def _stelle_ha(monkeypatch, states, *, menge=None, registry=None):
    """Stellt HA nach: States über REST, Menge und Registry über den Auflöser.

    ``menge``/``registry`` auf ``None`` heißt **„HA beantwortet das nicht"** —
    genau die Lage, in der die Kaskade eine Stufe tiefer greifen muss.
    """
    monkeypatch.setattr(
        "backend.services.ha_state_service.get_ha_state_service", lambda: _FakeHA()
    )
    monkeypatch.setattr(httpx, "AsyncClient", lambda *a, **k: _FakeClient(states))

    async def _menge(domain):
        return menge

    async def _registry():
        return registry

    monkeypatch.setattr(aufl, "integration_entity_ids", _menge)
    monkeypatch.setattr(aufl, "entity_registry_unique_ids", _registry)
    disc.invalidate_cache()


def _sensor(entity_id, *, name="", state="1.0", unit="kWh", attrs=None):
    a = {"friendly_name": name, "unit_of_measurement": unit}
    a.update(attrs or {})
    return {"entity_id": entity_id, "state": state, "attributes": a}


# ── Gernots Instanz: deutsch, gemischte Präfixe ──────────────────────────────
# Entity-IDs und unique_ids am 2026-08-31 an der echten Instanz gemessen
# (`integration_entities` + `config/entity_registry/list`), nicht erfunden.

_ENTRY = "01KTBDJH6DE1NHV9K7P5788Y5F"

_GERNOT_STATES = [
    _sensor("sensor.prognose_heute", name="Prognose (heute)"),
    _sensor("sensor.prognose_heute_rest", name="Prognose (heute Rest)"),
    _sensor("sensor.prognose_morgen", name="Prognose (morgen)"),
    _sensor("sensor.prognose_ubermorgen", name="Prognose Übermorgen"),
    _sensor("sensor.solar_forecast_ml_prognose_nachste_stunde",
            name="Prognose Nächste Stunde"),
    _sensor("sensor.solar_forecast_ml_o_genauigkeit_30_tage",
            name="Ø Genauigkeit 30 Tage", unit="%"),
    _sensor("sensor.planungsprognose_p10_blend", name="Planungsprognose (P10-Blend)"),
    _sensor("sensor.solar_forecast_ml_evcc_solar_prognose",
            name="evcc Solar-Prognose", attrs={"forecast": [{"value": 1}]}),
]

_GERNOT_MENGE = {s["entity_id"] for s in _GERNOT_STATES}

_GERNOT_REGISTRY = {
    "sensor.prognose_heute": f"{_ENTRY}_ml_expected_daily_production",
    "sensor.prognose_heute_rest": f"{_ENTRY}_ml_forecast_remaining",
    "sensor.prognose_morgen": f"{_ENTRY}_ml_forecast_tomorrow",
    "sensor.prognose_ubermorgen": f"{_ENTRY}_ml_forecast_day_after_tomorrow",
    "sensor.solar_forecast_ml_prognose_nachste_stunde": f"{_ENTRY}_ml_next_hour_forecast",
    "sensor.solar_forecast_ml_o_genauigkeit_30_tage": f"{_ENTRY}_ml_avg_accuracy_30d",
    "sensor.planungsprognose_p10_blend": f"{_ENTRY}_ml_conservative_planning_forecast",
    "sensor.solar_forecast_ml_evcc_solar_prognose": f"{_ENTRY}_ml_evcc_forecast",
}

_ALLE_SFML_ROLLEN = {r for _s, r in disc.SFML_PATTERNS}


async def test_gernot_alle_rollen_ueber_unique_id(monkeypatch):
    """Die bestehende (deutsche) Instanz verliert nichts — sie gewinnt den Weg."""
    _stelle_ha(monkeypatch, _GERNOT_STATES,
               menge=_GERNOT_MENGE, registry=_GERNOT_REGISTRY)

    res = await disc.discover_prognose_sensoren("sfml")

    assert set(res.sensoren) == _ALLE_SFML_ROLLEN
    assert res.menge_quelle == "integration_entities"
    assert res.rolle_quelle == "unique_id"
    # Und die Zuordnung stimmt, nicht nur die Anzahl: `_rest` darf nicht auf
    # `heute_kwh` fallen — das war der Grund für die Sortierung im alten
    # Verfahren und muss im neuen genauso halten.
    assert res.sensoren["heute_kwh"].entity_id == "sensor.prognose_heute"
    assert res.sensoren["heute_rest_kwh"].entity_id == "sensor.prognose_heute_rest"
    assert all(s.stufe == "unique_id" for s in res.sensoren.values())


# ── Burkards Fall: englische Instanz, `sensor.none_*` ────────────────────────

_BURKARD_STATES = [
    _sensor("sensor.none_expected_daily_production", name="Expected Daily Production"),
    _sensor("sensor.none_forecast_today_remaining", name="Forecast Today Remaining"),
    _sensor("sensor.none_forecast_tomorrow", name="Forecast Tomorrow"),
    _sensor("sensor.none_energy", name="Energy"),
    _sensor("sensor.solar_forecast_ml_next_hour_forecast", name="Next Hour Forecast"),
    _sensor("sensor.solar_forecast_ml_none", name="None"),
]

_BURKARD_MENGE = {s["entity_id"] for s in _BURKARD_STATES}

_BURKARD_REGISTRY = {
    "sensor.none_expected_daily_production": "01ABC_ml_expected_daily_production",
    "sensor.none_forecast_today_remaining": "01ABC_ml_forecast_remaining",
    "sensor.none_forecast_tomorrow": "01ABC_ml_forecast_tomorrow",
    "sensor.none_energy": "01ABC_ml_forecast_day_after_tomorrow",
    "sensor.solar_forecast_ml_next_hour_forecast": "01ABC_ml_next_hour_forecast",
    "sensor.solar_forecast_ml_none": "01ABC_ml_avg_accuracy_30d",
}


async def test_burkard_englische_instanz_wird_gefunden(monkeypatch):
    """Der gemeldete Fall: vorher null Rollen, jetzt sechs — über die unique_id.

    ⚑ Zwei seiner Entity-IDs (`none_energy`, `ml_none`) tragen **gar keinen**
    Namen; aus der ID ist ihre Rolle nicht zu gewinnen. Genau sie belegen, dass
    die `unique_id` und nicht der Name die tragende Stufe ist.
    """
    _stelle_ha(monkeypatch, _BURKARD_STATES,
               menge=_BURKARD_MENGE, registry=_BURKARD_REGISTRY)

    res = await disc.discover_prognose_sensoren("sfml")

    assert res.sensoren["heute_kwh"].entity_id == "sensor.none_expected_daily_production"
    assert res.sensoren["heute_rest_kwh"].entity_id == "sensor.none_forecast_today_remaining"
    assert res.sensoren["morgen_kwh"].entity_id == "sensor.none_forecast_tomorrow"
    assert res.sensoren["uebermorgen_kwh"].entity_id == "sensor.none_energy"
    assert res.sensoren["genauigkeit_30d"].entity_id == "sensor.solar_forecast_ml_none"
    assert res.rolle_quelle == "unique_id"


async def test_burkard_wurde_vom_alten_verfahren_nicht_gefunden():
    """Der Negativbeweis: das ALTE Verfahren allein findet bei ihm nichts.

    ⚠ Diese Probe fährt bewusst **nur** die letzte Stufe (Präfix + Suffix), also
    genau den Stand vor dem 31.08.2026 — nicht die Kaskade mit abgeschalteten
    oberen Stufen. Ein erster Anlauf tat das und wurde rot: der neu
    hinzugekommene **Namens**-Rückfall findet „Next Hour Forecast" sehr wohl.
    Er hatte recht, und der Bau nicht unrecht — falsch war die Probe, die „ohne
    Registry" mit „wie vorher" verwechselt hat.

    Fiele sie eines Tages grün aus, wäre das kein Fortschritt: dann hätte jemand
    die deutschen Muster um englische ergänzt und damit den nächsten Melder mit
    einer dritten Sprache wieder verloren.
    """
    ergebnis = await aufl.loese_integration_auf(
        domain="solar_forecast_ml",
        praefixe=disc.SFML_PREFIXES,
        unique_kerne={},          # es gab keine unique_id-Stufe
        namens_kerne={},          # und keine Namens-Stufe
        muster=disc.SFML_PATTERNS,
        states=_BURKARD_STATES,
    )

    assert ergebnis.menge_quelle == "praefix"
    # `sensor.none_*` trifft keinen Präfix; nur die beiden mit
    # `sensor.solar_forecast_ml_` sind überhaupt in der Menge, und deren
    # Suffixe sind englisch.
    assert ergebnis.anzahl_entities == 2
    assert ergebnis.treffer == {}


# ── Format-Fall: vorangestellter Bereich ─────────────────────────────────────


async def test_vorangestellter_bereich_bricht_die_erkennung_nicht(monkeypatch):
    """HA erlaubt *Bereich · Gerät · Entität* in wählbarer Reihenfolge.

    Steht der Bereich vorn, bricht der Präfix. Über die Integration ist das
    egal — die Entität gehört ihr, wie auch immer sie heißt.
    """
    states = [
        _sensor("sensor.technik_solar_forecast_ml_prognose_heute",
                name="Technik Prognose (heute)"),
    ]
    _stelle_ha(
        monkeypatch, states,
        menge={"sensor.technik_solar_forecast_ml_prognose_heute"},
        registry={"sensor.technik_solar_forecast_ml_prognose_heute":
                  f"{_ENTRY}_ml_expected_daily_production"},
    )

    res = await disc.discover_prognose_sensoren("sfml")

    assert res.sensoren["heute_kwh"].entity_id == \
        "sensor.technik_solar_forecast_ml_prognose_heute"


# ── Die Rückfälle: niemand wird schlechter gestellt ──────────────────────────


async def test_rueckfall_name_wenn_registry_ausfaellt(monkeypatch):
    """Registry nicht lesbar (alte HA, WS gesperrt) ⇒ der Anzeigename trägt."""
    _stelle_ha(monkeypatch, _GERNOT_STATES, menge=_GERNOT_MENGE, registry=None)

    res = await disc.discover_prognose_sensoren("sfml")

    assert res.sensoren["heute_kwh"].entity_id == "sensor.prognose_heute"
    assert res.sensoren["heute_rest_kwh"].entity_id == "sensor.prognose_heute_rest"
    assert res.sensoren["heute_kwh"].stufe == "name"


async def test_rueckfall_muster_wenn_name_und_registry_ausfallen(monkeypatch):
    """Weder Registry noch Anzeigename ⇒ das alte Entity-ID-Muster trägt.

    Das ist die Zusage aus dem Bau-Auftrag in Reinform: wessen Sensoren heute
    gefunden werden, merkt vom Umbau nichts.
    """
    ohne_namen = [dict(s, attributes={"unit_of_measurement": "kWh"})
                  for s in _GERNOT_STATES]
    _stelle_ha(monkeypatch, ohne_namen, menge=None, registry=None)

    res = await disc.discover_prognose_sensoren("sfml")

    assert res.sensoren["heute_kwh"].entity_id == "sensor.prognose_heute"
    assert res.sensoren["heute_rest_kwh"].entity_id == "sensor.prognose_heute_rest"
    assert res.sensoren["heute_kwh"].stufe == "muster"
    assert res.menge_quelle == "praefix"


# ── Gegenprobe: die Menge muss auch ausschließen ─────────────────────────────


async def test_fremde_integration_mit_passendem_namen_wird_nicht_eingesammelt(monkeypatch):
    """Ein Template-Sensor, der SFML nachahmt, gehört nicht zu SFML.

    Genau diesen Fall gibt es beim Melder wirklich: Burkard hat sich sechs
    Template-Sensoren gebaut, die seine Werte unter den gesuchten Namen
    spiegeln. Nach diesem Bau darf eedc **seine echten** Entitäten nehmen, nicht
    die Spiegel — sonst hätte der Umbau nur die Nachahmung legalisiert.
    """
    echt = "sensor.none_expected_daily_production"
    spiegel = "sensor.prognose_heute"  # sein Template-Sensor, deutscher Name
    states = [
        _sensor(echt, name="Expected Daily Production", state="28.7"),
        _sensor(spiegel, name="Prognose (heute)", state="28.7"),
    ]
    _stelle_ha(
        monkeypatch, states,
        menge={echt},  # nur der echte gehört der Integration
        registry={echt: "01ABC_ml_expected_daily_production"},
    )

    res = await disc.discover_prognose_sensoren("sfml")

    assert res.sensoren["heute_kwh"].entity_id == echt
    assert res.anzahl_entities == 1
    assert all(s.entity_id != spiegel for s in res.sensoren.values())


# ── Solcast: dieselbe Kaskade, eigene Kerne ──────────────────────────────────


async def test_solcast_ueber_unique_id_ohne_praefix(monkeypatch):
    """Solcast vergibt die unique_id OHNE Config-Entry-Präfix — gemessen.

    Hätte der Auflöser auf ``<entry>_<kern>`` bestanden, wäre Solcast durch
    Stufe 1 gefallen und still auf das Namensmuster zurückgerutscht. ``endswith``
    deckt beide Formen ab.
    """
    states = [
        _sensor("sensor.pv_vorhersage_i_dag", name="PV Vorhersage i dag"),
        _sensor("sensor.pv_vorhersage_i_morgen", name="PV Vorhersage i morgen"),
    ]
    _stelle_ha(
        monkeypatch, states,
        menge={s["entity_id"] for s in states},
        registry={
            "sensor.pv_vorhersage_i_dag": "total_kwh_forecast_today",
            "sensor.pv_vorhersage_i_morgen": "total_kwh_forecast_tomorrow",
        },
    )

    res = await disc.discover_prognose_sensoren("solcast")

    assert res.sensoren["heute_kwh"].entity_id == "sensor.pv_vorhersage_i_dag"
    assert res.sensoren["morgen_kwh"].entity_id == "sensor.pv_vorhersage_i_morgen"
    assert res.rolle_quelle == "unique_id"


# ── Der Status sagt, auf welchem Weg ─────────────────────────────────────────


async def test_status_nennt_menge_und_stufe(monkeypatch):
    """Die Abnahme-Oberfläche (`PrognoseQuellenBefund`) braucht beides.

    Ohne diese Felder sieht ein Melder „4 von 8 gefunden" und weiß nicht, ob
    seine HA die Auskunft verweigert oder ob eedc vier Rollen nicht kennt.
    """
    _stelle_ha(monkeypatch, _GERNOT_STATES,
               menge=_GERNOT_MENGE, registry=_GERNOT_REGISTRY)

    status = await disc.discovery_status("sfml")

    assert status["menge_quelle"] == "integration_entities"
    assert status["rolle_quelle"] == "unique_id"
    assert status["anzahl_entities"] == len(_GERNOT_STATES)
    assert status["anzahl_gefunden"] == status["anzahl_gesamt"]
    assert all(r["stufe"] == "unique_id" for r in status["rollen"])


# ── Der Auflöser selbst: Normalisierung ──────────────────────────────────────


@pytest.mark.parametrize(
    "roh,erwartet",
    [
        ("Prognose (heute Rest)", "prognose_heute_rest"),
        ("Ø Genauigkeit 30 Tage", "genauigkeit_30_tage"),
        ("Prognose Übermorgen", "prognose_ubermorgen"),
        ("evcc Solar-Prognose", "evcc_solar_prognose"),
        ("", ""),
    ],
)
def test_namen_normalisierung(roh, erwartet):
    """Klammern, Ø, Umlaute und Bindestriche dürfen keine Rolle kosten."""
    assert aufl._normalisiere(roh) == erwartet


# ── Der dritte Aufrufer: die zweite Solcast-Erkennung ────────────────────────


async def test_solcast_service_nutzt_denselben_aufloeser(monkeypatch):
    """`solcast_service._resolve_solcast_entities` — der zweite Turm ist weg.

    Bis zum 31.08.2026 hatte Solcast **zwei** getrennte Erkennungen: eine in
    `prognose_discovery.py`, eine hier. Beide mit eigener Suffix-Liste, beide
    sprachgebunden. Sie laufen jetzt über denselben Auflöser; unterschiedlich
    sind nur die logischen Schlüssel (`heute` statt `heute_kwh`).

    ⚠ Und der **Vorfilter** muss halten: `…_verbleibende_leistung_heute` endet
    ebenfalls auf `_heute` und darf nicht als Tages-Total durchgehen.
    """
    import backend.services.solcast_service as solc

    states = [
        _sensor("sensor.pv_vorhersage_i_dag", name="PV Vorhersage i dag"),
        _sensor("sensor.pv_vorhersage_i_morgen", name="PV Vorhersage i morgen"),
        _sensor("sensor.solcast_pv_forecast_prognose_verbleibende_leistung_heute",
                name="Prognose verbleibende Leistung heute"),
        _sensor("sensor.solcast_pv_forecast_prognose_spitzenleistung_heute",
                name="Prognose Spitzenleistung heute", unit="W"),
    ]
    _stelle_ha(
        monkeypatch, states,
        menge={s["entity_id"] for s in states},
        registry={
            "sensor.pv_vorhersage_i_dag": "total_kwh_forecast_today",
            "sensor.pv_vorhersage_i_morgen": "total_kwh_forecast_tomorrow",
            "sensor.solcast_pv_forecast_prognose_verbleibende_leistung_heute":
                "get_remaining_today",
            "sensor.solcast_pv_forecast_prognose_spitzenleistung_heute": "peak_w_today",
        },
    )
    solc._resolved_entities = {}
    solc._resolved_ts = 0.0

    aufgeloest = await solc._resolve_solcast_entities()

    assert aufgeloest["heute"] == "sensor.pv_vorhersage_i_dag"
    assert aufgeloest["morgen"] == "sensor.pv_vorhersage_i_morgen"
    # Weder der Rest-Sensor noch die Spitzenleistung sind Tages-Totale.
    assert set(aufgeloest) == {"heute", "morgen"}


async def test_solcast_vorfilter_haelt_wenn_nur_das_muster_traegt(monkeypatch):
    """Der Vorfilter ist genau dann tragend, wenn die Registry ausfällt.

    ⚠ **Eine erste Fassung dieser Probe war stumpf:** Sie stellte die Registry
    bereit, und dann besetzte Stufe 1 den Schlüssel `heute` längst, bevor die
    Muster-Stufe an `…_verbleibende_leistung_heute` überhaupt herankam — der
    Sprengsatz (Vorfilter entfernt) blieb grün. Ein Prüfer, der die Sicherung
    nicht erreicht, prüft sie nicht.

    Hier steht der Rest-Sensor deshalb **vor** dem Tageswert und die Registry
    fehlt: ohne Vorfilter griffe er sich `heute`, und eedc würde ab da die
    Restmenge als Tagesprognose lesen.
    """
    import backend.services.solcast_service as solc

    states = [
        _sensor("sensor.solcast_pv_forecast_prognose_verbleibende_leistung_heute"),
        _sensor("sensor.solcast_pv_forecast_prognose_heute"),
    ]
    _stelle_ha(monkeypatch, states, menge=None, registry=None)
    solc._resolved_entities = {}
    solc._resolved_ts = 0.0

    aufgeloest = await solc._resolve_solcast_entities()

    assert aufgeloest["heute"] == "sensor.solcast_pv_forecast_prognose_heute"
