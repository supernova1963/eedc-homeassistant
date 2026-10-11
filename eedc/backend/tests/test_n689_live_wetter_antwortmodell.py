"""N-689: die HTTP-Antwort von ``GET /api/live/{id}/wetter`` trägt, was die Route baut.

⛔ **Der Defekt** (seit ``d11a659c``, 30.08.2026, v4.0.36): die Route baute
``prognose_quelle_tage`` (Tageszahlen der GEWÄHLTEN Prognosequelle für Heute,
Morgen, Übermorgen) und ``prognose_quelle_hat_profil`` ins Antwort-Dict — ihr
``response_model=LiveWetterResponse`` kannte beide Felder nicht, und FastAPI
streicht, was das Modell nicht kennt. Die Kachel *Cockpit → Live →
Solar-Aussicht* bekam deshalb bei SFML/Solcast nie die Zahlen ihrer Quelle und
fiel für Morgen/Übermorgen und alle VM/NM-Werte auf den eedc-Kanon zurück —
unter der Überschrift „Solar-Aussicht (SFML)" bzw. „(Solcast)" und ohne den
„eedc"-Vermerk, den sie für genau diesen Fall hat. Dazu gingen
``stunden[].gti_wm2`` und ``aktuell.gti_wm2`` verloren (kein Leser im Frontend;
sie gehören ins Modell, damit Rohrückgabe und Antwort deckungsgleich sind).

⭐ **Warum keine Probe es sah:** alle Backend-Proben dieser Route riefen die
Funktion ``get_live_wetter`` direkt — die Rohrückgabe trug die Felder ja. Der
Frontend-Test setzte das Feld selbst. Deshalb hier zwei Proben, die genau diese
Lücke schließen:

* **über HTTP** (ASGI, der echte Router mit ``response_model``) — was beim
  Anwender ankommt, nicht was die Funktion zurückgibt;
* ein **Wächter** „jeder Schlüssel der Rohrückgabe steht nach der Filterung
  durch das Antwortmodell noch da" — rekursiv (``stunden[]``, ``aktuell``,
  ``prognose_quelle_tage[]``, ``verbrauchsprofil[]``), über die Zweige eedc mit
  Kanon, SFML, Solcast, Demo und die Abbruch-Antworten.

Gestellt sind nur die Dienst-Nähte, die auch die übrigen Proben dieser Route
stellen (Forecast-Lader, Lernfaktor, Persistenz am Modul ``live_wetter``;
Kanon, Profilwahl, HA, SFML-Discovery, MQTT, Solcast an ihren Quellmodulen).
Schwesterdateien: ``test_live_wetter_erfolgspfad.py`` (Erfolgspfad stirbt
nicht), ``test_live_prognose_folgetage_quelle.py`` (Auswahl der Quellen-Tage),
Frontend ``components/live/SolarAussichtQuelle.test.tsx``.
"""
from __future__ import annotations

from datetime import date
from types import SimpleNamespace

import httpx
import pytest
from fastapi import FastAPI

from backend.api.deps import get_db
from backend.api.routes import live_wetter
from backend.api.routes.live_wetter import LiveWetterResponse, get_live_wetter
from backend.models import Anlage

pytestmark = pytest.mark.asyncio

# Ein FESTES Datum (Wächter `test_konformitaet_echte_uhr_in_tests.py`): die Route
# liest ihre Uhr selbst; keine Aussage unten hängt daran, welcher Tag „heute" ist —
# die Quellen-Tage kommen aus Tageswerten (SFML) bzw. dem Heute-Profil (Solcast).
TAG = "2026-03-10"


def _om() -> dict:
    """Eine Open-Meteo-Tagesantwort — 24 Stunden, alle gelesenen Reihen, mit GTI."""
    tag = TAG
    times = [f"{tag}T{h:02d}:00" for h in range(24)]
    n = len(times)
    return {
        "hourly": {
            "time": times,
            "temperature_2m": [12.0] * n,
            "weather_code": [1] * n,
            "cloud_cover": [30] * n,
            "precipitation": [0.0] * n,
            "shortwave_radiation": [0.0] * 6 + [300.0] * 12 + [0.0] * 6,
            "sunshine_duration": [0.0] * 6 + [3000.0] * 12 + [0.0] * 6,
            "global_tilted_irradiance": [0.0] * 6 + [400.0] * 12 + [0.0] * 6,
        },
        "daily": {
            "temperature_2m_min": [6.0], "temperature_2m_max": [15.0],
            "sunrise": [f"{tag}T06:40"], "sunset": [f"{tag}T18:10"],
        },
    }


def _kanon():
    from backend.services.prognose_kanon import KanonPrognose, KanonTag
    slots = [round(max(0.0, 2.6 - 0.37 * abs(h - 12.5)), 3) for h in range(24)]
    tag = KanonTag(
        datum=TAG, om_kwh=19.9, eedc_kwh=21.4, vm_kwh=9.9, nm_kwh=11.4,
        profil=SimpleNamespace(stundenprofil_export_kwh=slots),
        om_stundenprofil_kwh=slots, om_vollstaendig=True,
    )
    return KanonPrognose(
        tage=[tag], rest_heute_kwh=7.3, ist_bisher_kwh=13.2, heute_rollend_kwh=20.5,
        skalar_fallback=None,
    )


def _solcast():
    """Solcast mit Heute-Profil, ohne Folgetage (``tage_voraus`` leer)."""
    stunden = [round(max(0.0, 2.1 - 0.33 * abs(h - 12.5)), 2) for h in range(24)]
    return SimpleNamespace(
        daily_kwh=18.6, daily_p10_kwh=12.1, daily_p90_kwh=23.3, hourly_kw=stunden,
        tage_voraus=[],
    )


def _sfml():
    """SFML mit Tageswerten für alle drei Tage, ohne Stundenprofil-Attribute."""
    werte = {"heute_kwh": 17.4, "morgen_kwh": 22.2, "uebermorgen_kwh": 30.1, "genauigkeit_30d": 91.2}
    return SimpleNamespace(gefunden=True, wert=werte.get, attribut=lambda rolle: None)


@pytest.fixture
def naehte(monkeypatch):
    """Stellt die Dienst-Nähte; ``naehte["kanon"]`` etc. je Probe überschreibbar."""
    import backend.services.ha_state_service as hss
    import backend.services.mqtt_inbound_service as mis
    import backend.services.prognose_discovery as pdisc
    import backend.services.prognose_kanon as pk
    import backend.services.solcast_service as scs
    import backend.services.verbrauchsprognose_heute as vph

    stand = {"forecast": (_om(), None, True), "kanon": _kanon(), "solcast": _solcast(), "sfml": _sfml()}

    async def _lade(anlage, gruppen, cache_key):  # noqa: ARG001
        return stand["forecast"]

    async def _lern(*a, **k):  # noqa: ARG001
        return None

    async def _leer():
        return None

    async def _kanon_f(*a, **k):  # noqa: ARG001
        return stand["kanon"]

    async def _wahl(*a, **k):  # noqa: ARG001
        return vph.ProfilWahl()

    async def _solcast_f(anlage):  # noqa: ARG001
        return stand["solcast"]

    async def _disc(integration):  # noqa: ARG001
        return stand["sfml"]

    class _HA:
        is_available = True

        async def get_sensor_states_batch(self, ids):  # noqa: ARG002
            return {}

    monkeypatch.setattr(live_wetter, "_lade_forecast_gecached", _lade)
    monkeypatch.setattr(live_wetter, "_get_lernfaktor", _lern)
    monkeypatch.setattr(live_wetter, "_speichere_prognose", lambda *a, **k: _leer())
    monkeypatch.setattr(pk, "kanon_tagesprognose", _kanon_f)
    monkeypatch.setattr(vph, "waehle_verbrauchsprofil", _wahl)
    monkeypatch.setattr(hss, "get_ha_state_service", lambda: _HA())
    monkeypatch.setattr(pdisc, "discover_prognose_sensoren", _disc)
    monkeypatch.setattr(mis, "get_mqtt_inbound_service", lambda: None)
    monkeypatch.setattr(scs, "get_solcast_forecast", _solcast_f)
    return stand


async def _anlage(db, quelle: str = "eedc", **kw) -> Anlage:
    werte = dict(anlagenname="N-689", leistung_kwp=10.0, latitude=53.87, longitude=10.68)
    werte.update(kw)
    anlage = Anlage(**werte)
    anlage.prognose_quelle = quelle
    db.add(anlage)
    await db.flush()
    return anlage


async def _http(db, pfad: str) -> dict:
    app = FastAPI()
    app.include_router(live_wetter.router, prefix="/api/live")

    async def _db():
        yield db

    app.dependency_overrides[get_db] = _db
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test",
    ) as client:
        resp = await client.get(pfad)
    assert resp.status_code == 200, resp.text
    return resp.json()


# ── Probe über HTTP: was beim Anwender ankommt ───────────────────────────────


async def test_http_antwort_traegt_die_tage_der_gewaehlten_quelle_sfml(db, naehte):
    """SFML gewählt: die Kachel bekommt Heute/Morgen/Übermorgen aus SFML."""
    anlage = await _anlage(db, "sfml")

    res = await _http(db, f"/api/live/{anlage.id}/wetter")

    assert res["prognose_quelle"] == "sfml"
    tage = res.get("prognose_quelle_tage")
    assert tage is not None, (
        "Die HTTP-Antwort trägt `prognose_quelle_tage` nicht — das Antwortmodell "
        "streicht das Feld, und die Solar-Aussicht zeigt unter der SFML-"
        "Überschrift die eedc-Zahlen (N-689)."
    )
    assert [t["kwh"] for t in tage] == [17.4, 22.2, 30.1]
    assert [t["rueckfall"] for t in tage] == [None, None, None]
    # Drei aufeinanderfolgende Tage, ab dem Tag der Route.
    tage_d = [date.fromisoformat(t["datum"]) for t in tage]
    assert [(b - a).days for a, b in zip(tage_d, tage_d[1:])] == [1, 1]
    # Ohne Stundenprofil kein Rest und keine VM/NM — und das sagt das Feld.
    assert res.get("prognose_quelle_hat_profil") is False
    assert tage[0]["vm_kwh"] is None


async def test_http_antwort_traegt_rueckfall_und_profil_solcast(db, naehte):
    """Solcast gewählt, ohne Folgetage: Heute aus Solcast (mit VM/NM aus seinem
    Profil), Morgen/Übermorgen ausgewiesen als Rückfall auf eedc."""
    anlage = await _anlage(db, "solcast")

    res = await _http(db, f"/api/live/{anlage.id}/wetter")

    tage = res.get("prognose_quelle_tage")
    assert tage is not None, "`prognose_quelle_tage` fehlt in der HTTP-Antwort (N-689)."
    assert [t["kwh"] for t in tage] == [18.6, None, None]
    assert [t["rueckfall"] for t in tage] == [None, "eedc", "eedc"]
    assert tage[0]["vm_kwh"] is not None and tage[0]["nm_kwh"] is not None
    assert res.get("prognose_quelle_hat_profil") is True


async def test_http_antwort_traegt_gti_je_stunde(db, naehte):
    """``gti_wm2`` steht in der Rohrückgabe je Stunde — die Antwort trägt es mit."""
    anlage = await _anlage(db, "eedc")

    res = await _http(db, f"/api/live/{anlage.id}/wetter")

    assert res["verfuegbar"] is True
    assert "gti_wm2" in res["stunden"][0]
    assert res["stunden"][6]["gti_wm2"] == pytest.approx(400.0)
    assert "gti_wm2" in res["aktuell"]
    # eedc: keine Quellen-Tage (der Kanon gilt), Feld da und null.
    assert "prognose_quelle_tage" in res and res["prognose_quelle_tage"] is None


# ── Wächter: Rohrückgabe ⊆ Antwortmodell ─────────────────────────────────────


def _verlorene_pfade(roh, gefiltert, pfad: str = "") -> set[str]:
    """Jeder Schlüssel-Pfad der Rohrückgabe, den die Filterung verliert."""
    weg: set[str] = set()
    if isinstance(roh, dict):
        if not isinstance(gefiltert, dict):
            return {pfad or "<wurzel>"}
        for k, v in roh.items():
            unter = f"{pfad}.{k}" if pfad else k
            if k not in gefiltert:
                weg.add(unter)
            else:
                weg |= _verlorene_pfade(v, gefiltert[k], unter)
    elif isinstance(roh, list) and isinstance(gefiltert, list):
        for r, g in zip(roh, gefiltert):
            weg |= _verlorene_pfade(r, g, f"{pfad}[]")
    return weg


@pytest.mark.parametrize("fall", [
    "eedc_mit_kanon", "eedc_ohne_kanon", "sfml", "solcast", "demo",
    "keine_koordinaten", "negativ_cache",
])
async def test_rohrueckgabe_ist_teilmenge_des_antwortmodells(db, naehte, fall):
    """Was die Route baut, kommt beim Anwender an — kein Feld fällt still weg."""
    quelle = {"sfml": "sfml", "solcast": "solcast"}.get(fall, "eedc")
    kw = {"latitude": None} if fall == "keine_koordinaten" else {}
    anlage = await _anlage(db, quelle, **kw)
    if fall == "eedc_ohne_kanon":
        naehte["kanon"] = None
    if fall == "negativ_cache":
        naehte["forecast"] = None

    roh = await get_live_wetter(anlage_id=anlage.id, demo=(fall == "demo"), db=db)
    gefiltert = LiveWetterResponse.model_validate(roh).model_dump(mode="json")

    weg = _verlorene_pfade(roh, gefiltert)
    assert not weg, (
        f"Fall {fall}: das Antwortmodell `LiveWetterResponse` streicht "
        f"{sorted(weg)} — die Route baut sie, der Anwender bekommt sie nicht. "
        "Feld ins Modell aufnehmen (typisiert) oder aus der Rückgabe nehmen."
    )
