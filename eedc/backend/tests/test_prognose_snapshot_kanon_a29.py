"""A29/E15: EIN OpenMeteo-Snapshot je (Standort, Modell) statt einer je Horizont.

Befund N20/N33: beide OpenMeteo-Cache-Keys trugen den vom Aufrufer angefragten
Horizont (``gti:lat:lon:neigung:ausrichtung:days:model`` und
``forecast:lat:lon:days:model``). Verschiedene Sichten fragen verschiedene
Horizonte — der Prognose-Kanon 4 Tage, der Prefetch 7 und 14,
``/solar-prognose`` bis 16 — also lag für DENSELBEN Tag je Sicht ein anderer
Snapshot im Cache. Die 14-Tage-Sicht und die Tagesprognose zeigten für „morgen"
zwei Zahlen aus zwei Abrufen.

Entscheidung E15, Variante (a): ``days`` im Cache-Key kommt aus
``services/wetter/cache.snapshot_days`` (Modell-Maximum, gedeckelt auf 16),
zugeschnitten wird lokal. Auflage E15-a: ``min(bedarf, max_days[model])`` —
ein pauschales 16 löste bei icon_d2 (Maximum 2 Tage) die Kaskade aus, statt den
Cache zu treffen.

Zwingende Invariante: die Tagessummen ändern sich dadurch NICHT. Das ist eine
Cache-/Abruf-Frage, keine Rechen-Frage — die Präfix-Tests unten sind der Beleg.
"""

from __future__ import annotations

import ast
from pathlib import Path

import httpx
import pytest

from backend.services import solar_forecast_service as sfs
from backend.services.wetter import cache as wetter_cache
from backend.services.wetter import open_meteo
from backend.services.wetter.cache import SNAPSHOT_HORIZONT_TAGE, snapshot_days
from backend.services.wetter.models import WETTER_MODELLE

from backend.tests.quellbaum import produktivbaum


# ── Test-Doubles ────────────────────────────────────────────────────────────


class _FakeResponse:
    def __init__(self, payload: dict):
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self._payload


class _FakeClient:
    """httpx.AsyncClient-Ersatz, der jeden Aufruf mitschreibt."""

    def __init__(self, aufrufe: list, payload_fabrik):
        self._aufrufe = aufrufe
        self._payload_fabrik = payload_fabrik

    def __call__(self, *args, **kwargs):
        return self

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def get(self, url, params=None):
        self._aufrufe.append(params or {})
        return _FakeResponse(self._payload_fabrik(params or {}))


class _HttpxShim:
    """Ersetzt nur ``AsyncClient``; Exception-Typen bleiben die echten."""

    def __init__(self, client):
        self.AsyncClient = client

    def __getattr__(self, name):
        return getattr(httpx, name)


def _gti_payload(params: dict) -> dict:
    """GTI-Antwort über ``forecast_days`` Tage — Tageswerte streng monoton."""
    tage = int(params.get("forecast_days", 1))
    zeiten, gti, ghi, temp, schnee, wolken, regen, code = [], [], [], [], [], [], [], []
    for t in range(tage):
        datum = f"2026-08-{t + 1:02d}"
        for h in range(24):
            zeiten.append(f"{datum}T{h:02d}:00")
            # Pro Tag ein eigener Pegel → ein Präfix-Fehler fiele sofort auf.
            gti.append(100.0 * (t + 1) if 8 <= h <= 16 else 0.0)
            ghi.append(80.0 * (t + 1) if 8 <= h <= 16 else 0.0)
            temp.append(18.0)
            schnee.append(0.0)
            wolken.append(20.0)
            regen.append(0.0)
            code.append(1)
    return {
        "hourly": {
            "time": zeiten,
            "global_tilted_irradiance": gti,
            "shortwave_radiation": ghi,
            "temperature_2m": temp,
            "snowfall": schnee,
            "cloud_cover": wolken,
            "precipitation": regen,
            "weather_code": code,
        },
        "daily": {
            "time": [f"2026-08-{t + 1:02d}" for t in range(tage)],
            "shortwave_radiation_sum": [10.0] * tage,
            "sunshine_duration": [36000.0] * tage,
            "temperature_2m_max": [24.0] * tage,
            "temperature_2m_min": [12.0] * tage,
            "precipitation_sum": [0.0] * tage,
            "snowfall_sum": [0.0] * tage,
            "weather_code": [1] * tage,
        },
    }


def _forecast_payload(params: dict) -> dict:
    """GHI-/Wetter-Antwort über ``forecast_days`` Tage."""
    tage = int(params.get("forecast_days", 1))
    return {
        "daily": {
            "time": [f"2026-08-{t + 1:02d}" for t in range(tage)],
            "shortwave_radiation_sum": [10.0 * (t + 1) for t in range(tage)],
            "sunshine_duration": [36000.0] * tage,
            "temperature_2m_max": [24.0] * tage,
            "temperature_2m_min": [12.0] * tage,
            "precipitation_sum": [0.0] * tage,
            "cloud_cover_mean": [20.0] * tage,
            "weather_code": [1] * tage,
        }
    }


@pytest.fixture(autouse=True)
def _leerer_cache():
    """Jeder Test startet mit leerem L1- und Negative-Cache."""
    wetter_cache._cache.clear()
    wetter_cache._error_cache.clear()
    yield
    wetter_cache._cache.clear()
    wetter_cache._error_cache.clear()


@pytest.fixture
def gti_aufrufe(monkeypatch):
    aufrufe: list[dict] = []
    monkeypatch.setattr(sfs, "httpx", _HttpxShim(_FakeClient(aufrufe, _gti_payload)))
    return aufrufe


@pytest.fixture
def forecast_aufrufe(monkeypatch):
    aufrufe: list[dict] = []
    monkeypatch.setattr(
        open_meteo, "httpx", _HttpxShim(_FakeClient(aufrufe, _forecast_payload))
    )
    return aufrufe


# ── snapshot_days: der Horizont-SoT selbst (E15-a) ──────────────────────────


def test_snapshot_days_respektiert_jedes_modell_maximum():
    """Kein Modell wird über sein eigenes Maximum hinaus abgerufen (E15-a).

    Baumweit über ``WETTER_MODELLE`` — ein neu aufgenommenes Modell mit kurzem
    Horizont ist damit automatisch mitgedeckt.
    """
    for key, (model_name, max_days) in WETTER_MODELLE.items():
        erwartet = min(SNAPSHOT_HORIZONT_TAGE, max_days)
        assert snapshot_days(model_name) == erwartet, (
            f"{key}: Snapshot {snapshot_days(model_name)} > Modell-Maximum {max_days}"
        )


def test_snapshot_days_ist_unabhaengig_vom_aufrufer():
    """Der Kern von E15: der Horizont hängt am Modell, nicht an der Anfrage."""
    assert snapshot_days(None) == snapshot_days("auto") == SNAPSHOT_HORIZONT_TAGE
    assert snapshot_days("icon_d2") == 2
    assert snapshot_days("ecmwf_ifs04") == 10
    # Unbekanntes Modell → Vollhorizont statt stiller 0-Deckelung.
    assert snapshot_days("gibt_es_nicht") == SNAPSHOT_HORIZONT_TAGE


# ── GTI-Raum (Prognose-Kanon, /solar-prognose) ──────────────────────────────


async def test_gti_verschiedene_horizonte_ein_einziger_abruf(gti_aufrufe):
    """N20/N33: 4 und 14 Tage treffen denselben Cache-Eintrag.

    Vorher: zwei Keys, zwei API-Calls, zwei Snapshots desselben Tages.
    """
    await sfs.fetch_gti_forecast(50.0, 8.0, 30, 0, days=4, skip_jitter=True)
    await sfs.fetch_gti_forecast(50.0, 8.0, 30, 0, days=14, skip_jitter=True)
    await sfs.fetch_gti_forecast(50.0, 8.0, 30, 0, days=1, skip_jitter=True)

    assert len(gti_aufrufe) == 1, f"{len(gti_aufrufe)} Abrufe statt einem"
    assert gti_aufrufe[0]["forecast_days"] == SNAPSHOT_HORIZONT_TAGE
    assert len(wetter_cache._cache) == 1, sorted(wetter_cache._cache)


async def test_gti_cache_key_traegt_den_snapshot_nicht_die_anfrage(gti_aufrufe):
    await sfs.fetch_gti_forecast(50.0, 8.0, 30, 0, days=4, skip_jitter=True)
    (key,) = wetter_cache._cache
    assert key == f"gti:50.00:8.00:30:0:{SNAPSHOT_HORIZONT_TAGE}:auto"


async def test_gti_kurzhorizont_modell_ruft_nicht_16_tage_ab(gti_aufrufe):
    """E15-a: icon_d2 kann nur 2 Tage — ein pauschales 16 verfehlte den Cache."""
    await sfs.fetch_gti_forecast(
        50.0, 8.0, 30, 0, days=4, model="icon_d2", skip_jitter=True
    )
    assert gti_aufrufe[0]["forecast_days"] == 2
    assert list(wetter_cache._cache) == ["gti:50.00:8.00:30:0:2:icon_d2"]


async def test_gti_negative_cache_gilt_fuer_alle_horizonte(monkeypatch):
    """Ein 429 sperrt den gemeinsamen Key — nicht nur den anfragenden Horizont.

    Genau die Eigenschaft, die Variante (b) in einer eigenen Schicht hätte
    nachbauen müssen (Begründung an ``snapshot_days``).
    """
    aufrufe: list[dict] = []

    class _Fehler(_FakeClient):
        async def get(self, url, params=None):
            aufrufe.append(params or {})
            raise httpx.HTTPStatusError(
                "rate limit",
                request=httpx.Request("GET", "https://example.invalid"),
                response=httpx.Response(429),
            )

    monkeypatch.setattr(
        sfs, "httpx", _HttpxShim(_Fehler(aufrufe, _gti_payload))
    )
    assert await sfs.fetch_gti_forecast(50.0, 8.0, 30, 0, days=4, skip_jitter=True) is None
    assert await sfs.fetch_gti_forecast(50.0, 8.0, 30, 0, days=14, skip_jitter=True) is None
    assert len(aufrufe) == 1, "der zweite Horizont hämmerte trotz Negative-Cache"


async def test_gti_prognose_liefert_genau_den_angefragten_horizont(gti_aufrufe):
    """Zuschnitt: für jeden Aufrufer sieht die Antwort aus wie vorher."""
    for days in (1, 2, 4, 7, 14, 16):
        prognose = await sfs.get_solar_prognose(
            50.0, 8.0, kwp=10.0, neigung=30, ausrichtung=0,
            days=days, skip_jitter=True,
        )
        assert prognose is not None
        assert len(prognose.tageswerte) == days


async def test_gti_zuschnitt_ist_ein_echtes_praefix(gti_aufrufe):
    """Die Kern-Auflage: die Vereinheitlichung ändert KEINE Tageszahl.

    Derselbe Tag muss aus dem 4-Tage- und dem 14-Tage-Zuschnitt bitgleich
    herausfallen — sonst wäre A29 eine stille Nutzerzahlen-Änderung.
    """
    kurz = await sfs.get_solar_prognose(
        50.0, 8.0, kwp=10.0, neigung=30, ausrichtung=0, days=4, skip_jitter=True
    )
    lang = await sfs.get_solar_prognose(
        50.0, 8.0, kwp=10.0, neigung=30, ausrichtung=0, days=14, skip_jitter=True
    )
    assert kurz.tageswerte == lang.tageswerte[:4]


async def test_gti_aggregate_gelten_ueber_den_zuschnitt(gti_aufrufe):
    """Summe/Ø/Zeitraum beschreiben die ausgelieferten Tage, nicht den Snapshot."""
    prognose = await sfs.get_solar_prognose(
        50.0, 8.0, kwp=10.0, neigung=30, ausrichtung=0, days=3, skip_jitter=True
    )
    erwartet = sum(t.pv_ertrag_kwh for t in prognose.tageswerte)
    assert prognose.summe_kwh == round(erwartet, 1)
    assert prognose.durchschnitt_kwh_tag == round(erwartet / 3, 2)
    assert prognose.prognose_zeitraum == {
        "von": prognose.tageswerte[0].datum,
        "bis": prognose.tageswerte[-1].datum,
    }


async def test_gti_kaskade_bleibt_bei_kurzhorizont_modell(gti_aufrufe):
    """Modell-Kaskade (primary + best_match) überlebt die Vereinheitlichung.

    Der eigentliche Schaden eines pauschalen ``days=16`` wäre nicht der
    verfehlte Cache, sondern eine Zahlenänderung: ``models=icon_d2&
    forecast_days=16`` liefert 16 Tageseinträge, ab Tag 3 aber ``None``
    (live gemessen 2026-07-28). Die Kaskade füllt über ``primary_dates`` nur
    die vom Primärmodell NICHT gelieferten Tage mit best_match auf — 16 leere
    Primär-Tage hätten den Fallback vollständig verdrängt und Tag 3–7 auf
    0 kWh fallen lassen.
    """
    prognose = await sfs.get_solar_prognose(
        50.0, 8.0, kwp=10.0, neigung=30, ausrichtung=0,
        days=7, wetter_modell="icon_d2", skip_jitter=True,
    )
    assert prognose is not None
    assert len(prognose.tageswerte) == 7
    horizonte = sorted(a["forecast_days"] for a in gti_aufrufe)
    assert horizonte == [2, SNAPSHOT_HORIZONT_TAGE], horizonte

    quellen = [t.datenquelle for t in prognose.tageswerte]
    assert quellen[:2] == ["icon_d2", "icon_d2"], quellen
    assert set(quellen[2:]) == {"best_match"}, quellen
    assert all(t.pv_ertrag_kwh > 0 for t in prognose.tageswerte), (
        "Tage jenseits des Modell-Horizonts kollabiert — Fallback verdrängt"
    )


# ── GHI-Raum (Aussichten, 14-Tage-Wettertabelle) ────────────────────────────


async def test_forecast_verschiedene_horizonte_ein_einziger_abruf(forecast_aufrufe):
    for days in (7, 14, 16):
        await open_meteo.fetch_open_meteo_forecast(50.0, 8.0, days=days, skip_jitter=True)

    assert len(forecast_aufrufe) == 1, f"{len(forecast_aufrufe)} Abrufe statt einem"
    assert forecast_aufrufe[0]["forecast_days"] == SNAPSHOT_HORIZONT_TAGE
    assert list(wetter_cache._cache) == [f"forecast:50.00:8.00:{SNAPSHOT_HORIZONT_TAGE}:auto"]


async def test_forecast_liefert_genau_den_angefragten_horizont(forecast_aufrufe):
    for days in (1, 7, 14, 16):
        res = await open_meteo.fetch_open_meteo_forecast(
            50.0, 8.0, days=days, skip_jitter=True
        )
        assert len(res["tage"]) == days


async def test_forecast_zuschnitt_ist_ein_echtes_praefix(forecast_aufrufe):
    kurz = await open_meteo.fetch_open_meteo_forecast(50.0, 8.0, days=7, skip_jitter=True)
    lang = await open_meteo.fetch_open_meteo_forecast(50.0, 8.0, days=14, skip_jitter=True)
    assert kurz["tage"] == lang["tage"][:7]


async def test_forecast_kurzhorizont_modell_ruft_nicht_16_tage_ab(forecast_aufrufe):
    """E15-a auch im GHI-Raum — hier kommt das Modell heute schon an."""
    await open_meteo.fetch_open_meteo_forecast(
        50.0, 8.0, days=14, model="icon_eu", skip_jitter=True
    )
    assert forecast_aufrufe[0]["forecast_days"] == 5


# ── Prefetch: ein Abruf je Key, nicht mehrere Horizonte desselben Keys ──────


async def test_prefetch_waermt_jeden_key_genau_einmal(monkeypatch):
    """Nach der Vereinheitlichung wären mehrere Horizonte derselbe Key.

    Der Prefetch wärmte zwei GTI- und drei Wetter-Horizonte, weil jeder davon
    einen eigenen Cache-Eintrag hatte. Mit gemeinsamem Key wäre das schlicht
    doppelte API-Last auf denselben Eintrag — und da alle im selben ``gather``
    laufen, greift der Cache zwischen ihnen nicht einmal.
    """
    gti_aufrufe: list[dict] = []
    forecast_aufrufe: list[dict] = []
    monkeypatch.setattr(sfs, "httpx", _HttpxShim(_FakeClient(gti_aufrufe, _gti_payload)))
    monkeypatch.setattr(
        open_meteo, "httpx", _HttpxShim(_FakeClient(forecast_aufrufe, _forecast_payload))
    )

    await sfs.get_solar_prognose(
        50.0, 8.0, kwp=10.0, neigung=30, ausrichtung=0, days=16, skip_jitter=True
    )
    await open_meteo.fetch_open_meteo_forecast(50.0, 8.0, days=16, skip_jitter=True)

    # Genau die Aufruf-Form, die `prefetch_service` heute nutzt: ein Horizont je
    # Raum. Die frühere (7, 14)- bzw. (7, 14, 16)-Schleife ergäbe hier 2 bzw. 3.
    assert len(gti_aufrufe) == 1, gti_aufrufe
    assert len(forecast_aufrufe) == 1, forecast_aufrufe


def test_prefetch_ruft_keinen_festen_horizont_mehr_ab():
    """Statischer Beleg: im Prefetch steht kein hartkodierter Horizont mehr.

    Regression gegen das Wiedereinführen einer ``for tage in (7, 14)``-Schleife
    — die wäre nach A29 zweimal derselbe Cache-Key.
    """
    quelle = (_BACKEND / "services" / "prefetch_service.py").read_text(encoding="utf-8")
    baum = ast.parse(quelle)
    horizonte = [
        node.value
        for node in ast.walk(baum)
        if isinstance(node, ast.keyword)
        and node.arg == "days"
        and isinstance(node.value, ast.Constant)
    ]
    assert not horizonte, (
        "prefetch_service übergibt wieder einen konstanten `days`-Wert — "
        "der Horizont gehört an SNAPSHOT_HORIZONT_TAGE/snapshot_days"
    )


# ── Wächter: kein Cache-Key darf den Aufrufer-Horizont tragen ───────────────

_BACKEND = Path(__file__).resolve().parents[1]

# Funktionen, deren erstes Argument ein Cache-Key ist.
_CACHE_FUNKTIONEN = {"_cache_get", "_cache_set", "_error_cache_check", "_error_cache_set"}


def _cache_key_ausdruecke(baum: ast.AST):
    """Alle f-Strings im Modul, die als Cache-Key dienen.

    Zwei Formen, beide im Baum vorhanden: Zuweisung an ``cache_key`` und der
    direkte f-String als erstes Argument einer ``_cache_*``-Funktion.
    """
    for node in ast.walk(baum):
        if isinstance(node, ast.Assign):
            ziele = [t.id for t in node.targets if isinstance(t, ast.Name)]
            if "cache_key" in ziele and isinstance(node.value, ast.JoinedStr):
                yield node.value
        elif isinstance(node, ast.Call):
            name = getattr(node.func, "id", None) or getattr(node.func, "attr", None)
            if name in _CACHE_FUNKTIONEN and node.args:
                if isinstance(node.args[0], ast.JoinedStr):
                    yield node.args[0]


def test_kein_cache_key_traegt_den_angefragten_horizont():
    """Baumweiter Wächter (Baseline 0): ``days`` gehört nicht in einen Cache-Key.

    Fängt auch eine Stelle, die es heute noch nicht gibt — jeder künftige
    Forecast-Client, der den Aufrufer-Horizont in den Key schreibt, fragmentiert
    den Cache wieder (N20). Der Snapshot-Horizont heißt ``abruf_days`` und
    stammt aus ``cache.snapshot_days``.

    Scope-Grenze, ehrlich benannt: geprüft werden die beiden im Baum
    tatsächlich verwendeten Formen (Zuweisung an ``cache_key``, f-String direkt
    als ``_cache_*``-Argument). Ein Key, der über Umwege zusammengebaut wird,
    liegt außerhalb — dann ist der Wächter mitzuziehen.
    """
    verstoesse = []
    for datei in produktivbaum():
        pfad, baum = datei.pfad, datei.baum
        for joined in _cache_key_ausdruecke(baum):
            for teil in joined.values:
                if not isinstance(teil, ast.FormattedValue):
                    continue
                for name in ast.walk(teil.value):
                    if isinstance(name, ast.Name) and name.id == "days":
                        verstoesse.append(
                            f"{pfad.relative_to(_BACKEND)}:{joined.lineno} "
                            f"interpoliert `days` in einen Cache-Key"
                        )
    assert not verstoesse, "\n".join(verstoesse)
