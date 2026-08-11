"""N-156 — die HA-Wege entscheiden nach der Erreichbarkeit, nicht nach dem Add-on.

Fortsetzung von **F-26** (`test_tagesverlauf_standalone_ha_verbindung.py`). Dort
war es der Tagesverlauf; hier sind es die sieben weiteren Aufrufer, die dasselbe
Gate auf ``HA_INTEGRATION_AVAILABLE`` (= ``SUPERVISOR_TOKEN``) trugen:

* ``prognose_discovery`` — deckt der Bestandstest ``test_prognose_discovery_sfml``
  ab, seit sein Supervisor-Patch entfallen ist
* ``solcast_service`` — Abruf **und** Statustext
* ``prognose_router`` — die Verfügbarkeits-Entscheidung, ohne die die beiden
  oberen unerreichbar blieben
* ``live_history_service`` — Heute-/Gestern-kWh
* ``live_verbrauchsprofil_service`` — deckt ``test_verbrauchsprofil_slot_konvention``
  ab, seit dort der ``HAStateService`` gefakt wird statt der Umgebungs-Konstante
* ``aktueller_monat`` und ``monatsabschluss/views`` — Langzeitstatistik im Monat

**Der gemeinsame Nenner:** unter jedem dieser Gates liegt ein Dienst, der seine
Erreichbarkeit selbst prüft (``HAStateService.is_available`` = ``bool(token)``,
``ha_statistics_service.is_available`` = Recorder-DB **oder** WebSocket). Beide
kennen seit dem 05.08. auch die Remote-Verbindung per Long-Lived-Token — die
Aufrufer wurden damals nur teilweise nachgezogen.

Die Proben stellen die Melder-Konstellation her: **kein Supervisor-Token**, aber
eine gesetzte HA-Verbindung. Sie messen die Weggabelung, nicht die Zahlen
dahinter.

⚠ Der Zustand von ``HAStateService`` ist prozessweit (Singleton). Die Fixture
stellt ihn hinterher wieder her — sonst trägt sie ihre Verbindung in fremde
Tests (die N-236-Klasse).
"""

from __future__ import annotations

from datetime import date

import pytest

from backend.models.anlage import Anlage
from backend.services.ha_state_service import get_ha_state_service


@pytest.fixture
def ha_verbindung():
    """Setzt/entfernt die Remote-Verbindung am Singleton — und räumt auf."""
    svc = get_ha_state_service()
    vorher = (svc.api_url, svc.token)

    def setzen(token):
        svc.api_url = "http://ha.example:8123/api"
        svc.token = token

    yield setzen
    svc.api_url, svc.token = vorher


# ─── Prognosequelle: SFML und Solcast bleiben wählbar ─────────────────────────


def _anlage_prognose(quelle: str, solcast_key: str | None = None) -> Anlage:
    a = Anlage(id=1, anlagenname="Docker mit Token")
    a.prognose_quelle = quelle
    a.sensor_mapping = (
        {"solcast_config": {"api_key": solcast_key}} if solcast_key else {}
    )
    return a


def test_sfml_bleibt_waehlbar_wenn_ha_per_token_haengt(ha_verbindung):
    """Der Kern: ohne Supervisor, aber mit Token ist SFML erreichbar.

    Vorher lieferte diese Konstellation einen **stillen Fallback** auf die
    eedc-Prognose — mit dem Hinweis, SFML sei „nur im HA-Add-on verfügbar",
    während die Sensoren über dieselbe REST-API lesbar sind.
    """
    from backend.services.prognose_router import resolve_prognose_quelle

    ha_verbindung("langlebiger-token")

    ergebnis = resolve_prognose_quelle(_anlage_prognose("sfml"))

    assert ergebnis.quelle == "sfml"
    assert not ergebnis.ist_fallback


def test_ohne_ha_verbindung_faellt_sfml_weiter_auf_eedc(ha_verbindung):
    """Gegenprobe: ohne jede HA-Verbindung bleibt der Fallback richtig."""
    from backend.services.prognose_router import resolve_prognose_quelle

    ha_verbindung(None)

    ergebnis = resolve_prognose_quelle(_anlage_prognose("sfml"))

    assert ergebnis.quelle == "eedc"
    assert ergebnis.ist_fallback


def test_solcast_auto_discovery_ohne_api_key_mit_token(ha_verbindung):
    """Mit HA-Verbindung braucht Solcast keinen eigenen API-Key.

    Die Auto-Erkennung liest die Sensoren der HA-Integration — dafür genügt
    eine erreichbare Instanz, egal auf welchem Weg.
    """
    from backend.services.prognose_router import resolve_prognose_quelle

    ha_verbindung("langlebiger-token")

    ergebnis = resolve_prognose_quelle(_anlage_prognose("solcast"))

    assert ergebnis.quelle == "solcast"
    assert not ergebnis.ist_fallback


def test_solcast_ohne_ha_und_ohne_key_faellt_zurueck(ha_verbindung):
    """Gegenprobe: ohne HA **und** ohne Token bleibt es beim Fallback."""
    from backend.services.prognose_router import resolve_prognose_quelle

    ha_verbindung(None)

    ergebnis = resolve_prognose_quelle(_anlage_prognose("solcast"))

    assert ergebnis.quelle == "eedc"
    assert ergebnis.ist_fallback


# ─── Solcast: Abruf und Statustext stellen dieselbe Frage ─────────────────────


@pytest.mark.asyncio
async def test_solcast_abruf_ohne_config_versucht_die_auto_erkennung(
    monkeypatch, ha_verbindung
):
    """Ohne eigene Config wird die HA-Integration befragt — auch ohne Supervisor."""
    from backend.services import solcast_service as sc

    ha_verbindung("langlebiger-token")
    gerufen = []

    async def fake_auto():
        gerufen.append(True)
        return None

    monkeypatch.setattr(sc, "_fetch_solcast_ha_auto", fake_auto)

    anlage = Anlage(id=1, anlagenname="Docker mit Token")
    anlage.sensor_mapping = {}

    await sc.get_solcast_forecast(anlage)

    assert gerufen, "Auto-Erkennung wurde übersprungen, obwohl HA erreichbar ist"


def test_solcast_status_folgt_derselben_frage(ha_verbindung):
    """Statustext und Abruf dürfen nicht auseinanderlaufen.

    Stünde hier weiter das Supervisor-Gate, meldete die Oberfläche „nicht
    eingerichtet", während der Abruf daneben erfolgreich Werte holt.
    """
    from backend.services.solcast_service import get_solcast_status

    anlage = Anlage(id=1, anlagenname="Docker mit Token")
    anlage.sensor_mapping = {}

    ha_verbindung("langlebiger-token")
    status_mit, _ = get_solcast_status(anlage)

    ha_verbindung(None)
    status_ohne, _ = get_solcast_status(anlage)

    assert status_mit == "ok"
    assert status_ohne == "nicht_konfiguriert"


# ─── Live: Heute-/Gestern-kWh nehmen den HA-Weg ───────────────────────────────


class _Cache:
    """Minimaler kWh-Cache — der echte hängt am Live-Dashboard."""

    def __init__(self):
        self.werte: dict[str, dict] = {}

    def get_heute(self, _id):
        return self.werte.get("heute")

    def get_gestern(self, _id):
        return self.werte.get("gestern")

    def set_heute(self, _id, wert):
        self.werte["heute"] = wert

    def set_gestern(self, _id, wert):
        self.werte["gestern"] = wert


@pytest.mark.asyncio
async def test_tages_kwh_nimmt_den_ha_weg_mit_token(db, monkeypatch, ha_verbindung):
    """``get_tages_kwh`` liest ausschließlich über Dienste, die remote können.

    Ohne den Fix wird der HA-Weg übersprungen und der MQTT-Fallback liefert die
    Zahl — bei einem Melder ohne MQTT also gar keine.
    """
    from backend.services import live_history_service as lhs

    ha_verbindung("langlebiger-token")

    async def fake_ha(anlage, db_, tage_zurueck, inv_types=None):
        return {"pv": 12.3}

    monkeypatch.setattr(lhs, "get_tages_kwh", fake_ha)

    anlage = Anlage(id=1, anlagenname="Docker mit Token")
    ergebnis = await lhs.safe_get_tages_kwh(anlage, db, 0, _Cache())

    assert ergebnis == {"pv": 12.3}


@pytest.mark.asyncio
async def test_ohne_ha_verbindung_bleibt_es_beim_mqtt_fallback(
    db, monkeypatch, ha_verbindung
):
    """Gegenprobe: der reine MQTT-Betrieb ist unberührt."""
    from backend.services import live_history_service as lhs

    ha_verbindung(None)
    ha_gerufen = []

    async def fake_ha(anlage, db_, tage_zurueck, inv_types=None):
        ha_gerufen.append(True)
        return {"pv": 12.3}

    monkeypatch.setattr(lhs, "get_tages_kwh", fake_ha)

    anlage = Anlage(id=1, anlagenname="nur MQTT")
    await lhs.safe_get_tages_kwh(anlage, db, 0, _Cache())

    assert not ha_gerufen, "HA-Weg versucht, obwohl keine Verbindung besteht"


# ─── Monat: die Langzeitstatistik ist erreichbar, also wird sie gelesen ───────


class _FakeSensorwert:
    def __init__(self, sensor_id: str, differenz: float):
        self.sensor_id = sensor_id
        self.differenz = differenz


class _FakeStats:
    """LTS-Dienst, der sich selbst für erreichbar hält — der Remote-Fall."""

    is_available = True

    def __init__(self, werte: dict[str, float]):
        self._werte = werte

    def get_monatswerte(self, sensor_ids, jahr, monat):
        class _Antwort:
            pass

        antwort = _Antwort()
        antwort.sensoren = [
            _FakeSensorwert(sid, self._werte[sid])
            for sid in sensor_ids
            if sid in self._werte
        ]
        return antwort


@pytest.mark.asyncio
async def test_cockpit_monat_liest_lts_ohne_supervisor(monkeypatch):
    """*Cockpit → Monat* holt seine LTS-Werte, sobald die Statistik erreichbar ist."""
    from backend.api.routes import aktueller_monat as am

    monkeypatch.setattr(
        "backend.services.ha_statistics_service.get_ha_statistics_service",
        lambda: _FakeStats({"sensor.netzbezug": 250.0}),
    )

    anlage = Anlage(id=1, anlagenname="Docker mit Token")
    anlage.sensor_mapping = {
        "basis": {"netzbezug": {"strategie": "sensor", "sensor_id": "sensor.netzbezug"}}
    }

    ergebnis = await am._collect_ha_statistics_data(anlage, 2026, 7)

    assert "netzbezug_kwh" in ergebnis
    wert, quelle = ergebnis["netzbezug_kwh"]
    assert wert == 250.0
    assert quelle.quelle == "ha_statistics"


@pytest.mark.asyncio
async def test_monatsabschluss_schlaegt_lts_wert_vor_ohne_supervisor(db, monkeypatch):
    """Der Monatsabschluss bietet den gemessenen Wert an, statt leer zu bleiben.

    Vorher sah ein per Token angebundener Betrieb hier **keinen** Vorschlag aus
    der Langzeitstatistik — er musste jeden Wert von Hand eintragen, obwohl HA
    ihn kannte.
    """
    from backend.api.routes.monatsabschluss.views import get_monatsabschluss

    anlage = Anlage(
        anlagenname="Docker mit Token", leistung_kwp=10.0,
        standort_plz="10115", latitude=48.0, longitude=11.0,
        installationsdatum=date(2025, 1, 1),
        sensor_mapping={
            "basis": {
                "netzbezug": {"strategie": "sensor", "sensor_id": "sensor.netzbezug"}
            }
        },
    )
    db.add(anlage)
    await db.flush()

    monkeypatch.setattr(
        "backend.services.ha_statistics_service.get_ha_statistics_service",
        lambda: _FakeStats({"sensor.netzbezug": 250.0}),
    )

    antwort = await get_monatsabschluss(anlage.id, 2026, 7, db=db)

    felder = {f.feld: f for f in antwort.basis_felder}
    assert "netzbezug_kwh" in felder, f"Feld fehlt, vorhanden: {list(felder)}"
    lts = [
        v for v in felder["netzbezug_kwh"].vorschlaege
        if "ha_statistic" in str(v.quelle)
    ]
    assert lts, (
        "kein LTS-Vorschlag, nur "
        f"{[str(v.quelle) for v in felder['netzbezug_kwh'].vorschlaege]}"
    )
    assert lts[0].wert == 250.0
