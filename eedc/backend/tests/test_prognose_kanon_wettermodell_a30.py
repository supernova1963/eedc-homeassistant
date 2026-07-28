"""A30/N16: das gewählte Wettermodell erreicht den Prognose-Kanon.

Befund N16: ``services/prognose_kanon.py`` rief ``get_solar_prognose`` ohne
``wetter_modell`` auf — der Kanon rechnete also IMMER mit best_match, obwohl
Live-Wetter, 14-Tage-Wettertabelle und die OpenMeteo-Spalte von
``/solar-prognose`` das in der Anlage gewählte Modell längst nutzten. Wer
bewusst z. B. ICON-D2 eingestellt hatte, bekam den OM-Balken aus ICON-D2 und
den eedc-Wert daneben (sowie den MQTT-/HA-Sensor) aus best_match.

Zwei Ebenen, weil zwei verschiedene Dinge schiefgehen können:

* **Ankommen** — der Kanon reicht ``Anlage.wetter_modell`` unverändert an jede
  Orientierungsgruppe durch (``auto`` als Default, auch bei ``None``).
* **Nicht kollabieren** — mit dem Modell greift die modellabhängige
  Snapshot-Grenze aus A29/E15-a (``wetter/cache.snapshot_days``) im Kanon zum
  ersten Mal in echt. Bei einem Kurzhorizont-Modell (icon_d2 = 2 Tage) müssen
  die Tage jenseits des Modell-Horizonts über die best_match-Kaskade weiter
  einen Ertrag tragen; ein pauschales ``forecast_days=16`` lieferte dort leere
  Primär-Tage, die den Fallback verdrängt und Tag 3+ auf 0 kWh gezogen hätten
  (live gemessen 2026-07-28, s. ``snapshot_days``).

Kontrollprobe in beiden Ebenen: bei ``wetter_modell="auto"`` — dem Default —
ändert sich weder der Abruf noch die Zahl.
"""

from __future__ import annotations

from datetime import date, timedelta

import httpx
import pytest

from backend.models import Anlage, Investition
from backend.services import solar_forecast_service as sfs
from backend.services.prognose_kanon import kanon_tagesprognose
from backend.services.wetter import cache as wetter_cache
from backend.services.wetter.cache import SNAPSHOT_HORIZONT_TAGE
from backend.services.wetter.models import WETTER_MODELLE


# ── Seed ────────────────────────────────────────────────────────────────────


async def _seed(db, *, wetter_modell, module=((10.0, 0),)) -> Anlage:
    """Anlage mit ``wetter_modell`` und ``module`` = [(kwp, ausrichtung_grad)]."""
    anlage = Anlage(
        anlagenname="A30-Test",
        leistung_kwp=sum(m[0] for m in module),
        latitude=48.8,
        longitude=9.2,
        standort_land="DE",
        prognose_quelle="eedc",
        wetter_modell=wetter_modell,
    )
    db.add(anlage)
    await db.flush()
    for kwp, azi in module:
        db.add(Investition(
            anlage_id=anlage.id, typ="pv-module", bezeichnung=f"String {azi}",
            leistung_kwp=kwp, neigung_grad=35,
            anschaffungsdatum=date(2024, 1, 1),
            parameter={"ausrichtung_grad": azi},
        ))
    await db.flush()
    return anlage


# ── Ebene 1: kommt das Modell überhaupt an? ─────────────────────────────────


@pytest.fixture
def gemeldete_modelle(monkeypatch):
    """Schreibt das ``wetter_modell`` jedes Fan-out-Aufrufs mit."""
    modelle: list = []

    async def _spion(**kwargs):
        modelle.append(kwargs.get("wetter_modell", "<nicht übergeben>"))
        return None

    monkeypatch.setattr(sfs, "get_solar_prognose", _spion)
    return modelle


@pytest.mark.parametrize(
    "gesetzt, erwartet",
    [
        (None, "auto"),          # Spalte nie gepflegt (Bestandsanlage)
        ("auto", "auto"),        # Default — Kontrollprobe
        ("icon_d2", "icon_d2"),  # Kurzhorizont, löst die Kaskade aus
        ("ecmwf_seamless", "ecmwf_seamless"),
    ],
)
async def test_kanon_reicht_wetter_modell_durch(db, gemeldete_modelle, gesetzt, erwartet):
    anlage = await _seed(db, wetter_modell=gesetzt)
    await kanon_tagesprognose(db, anlage, days=4, skip_jitter=True)
    assert gemeldete_modelle == [erwartet]


async def test_jede_orientierungsgruppe_bekommt_dasselbe_modell(db, gemeldete_modelle):
    """Multi-String: das Modell darf nicht nur an der ersten Gruppe hängen."""
    anlage = await _seed(db, wetter_modell="icon_eu", module=((6.0, 0), (4.0, -90)))
    await kanon_tagesprognose(db, anlage, days=4, skip_jitter=True)
    assert gemeldete_modelle == ["icon_eu", "icon_eu"]


# ── Ebene 2: Abruf + Zahlen am echten Kaskaden-Pfad ─────────────────────────


class _FakeResponse:
    def __init__(self, payload: dict):
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self._payload


class _FakeClient:
    """httpx.AsyncClient-Ersatz, der jeden Aufruf mitschreibt.

    ``tote_modelle``: für diese ``models``-Werte kommt HTTP 200 mit lauter
    ``null`` zurück — das real gemessene Verhalten von ``ecmwf_ifs04``.
    """

    def __init__(self, aufrufe: list, tote_modelle: frozenset = frozenset()):
        self._aufrufe = aufrufe
        self._tote = tote_modelle

    def __call__(self, *args, **kwargs):
        return self

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def get(self, url, params=None):
        params = params or {}
        self._aufrufe.append(params)
        leer = params.get("models") in self._tote
        return _FakeResponse(_gti_payload(params, leer=leer))


class _HttpxShim:
    """Ersetzt nur ``AsyncClient``; Exception-Typen bleiben die echten."""

    def __init__(self, client):
        self.AsyncClient = client

    def __getattr__(self, name):
        return getattr(httpx, name)


def _gti_payload(params: dict, leer: bool = False) -> dict:
    """GTI-Antwort ab HEUTE — der Kanon indiziert seine Tage nach echtem Datum.

    Das Primärmodell liefert einen doppelt so hohen Pegel wie best_match; so
    ist an den Tageswerten ablesbar, welche Quelle einen Tag getragen hat.
    ``leer=True`` liefert die Struktur mit lauter ``None`` (HTTP 200 ohne Daten).
    """
    tage = int(params.get("forecast_days", 1))
    pegel = None if leer else (200.0 if params.get("models") else 100.0)
    heute = date.today()
    daten = [(heute + timedelta(days=t)).isoformat() for t in range(tage)]

    zeiten, gti, ghi, temp, schnee, wolken, regen, code = [], [], [], [], [], [], [], []
    for datum in daten:
        for h in range(24):
            zeiten.append(f"{datum}T{h:02d}:00")
            # Im Leer-Fall ist AUCH die Nachtstunde ``None`` — so misst sich
            # ecmwf_ifs04 am 2026-07-28 (0 von 72 Werten gesetzt), nicht als 0.
            gti.append(None if leer else (pegel if 8 <= h <= 16 else 0.0))
            ghi.append(None if leer else (pegel * 0.8 if 8 <= h <= 16 else 0.0))
            temp.append(None if leer else 18.0)
            schnee.append(None if leer else 0.0)
            wolken.append(None if leer else 20.0)
            regen.append(None if leer else 0.0)
            code.append(None if leer else 1)
    leer_liste = [None] * tage
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
            "time": daten,
            "shortwave_radiation_sum": leer_liste if leer else [10.0] * tage,
            "sunshine_duration": leer_liste if leer else [36000.0] * tage,
            "temperature_2m_max": leer_liste if leer else [24.0] * tage,
            "temperature_2m_min": leer_liste if leer else [12.0] * tage,
            "precipitation_sum": leer_liste if leer else [0.0] * tage,
            "snowfall_sum": leer_liste if leer else [0.0] * tage,
            "weather_code": leer_liste if leer else [1] * tage,
        },
    }


@pytest.fixture
def _caches_leer():
    from backend.services.korrekturprofil_lookup import _cache as korrektur_cache

    def _leeren():
        wetter_cache._cache.clear()
        wetter_cache._error_cache.clear()
        korrektur_cache.clear()

    _leeren()
    yield
    _leeren()


@pytest.fixture
def gti_aufrufe(monkeypatch, _caches_leer):
    """Echter Kaskaden-Pfad, nur die HTTP-Schicht ersetzt."""
    aufrufe: list[dict] = []
    monkeypatch.setattr(sfs, "httpx", _HttpxShim(_FakeClient(aufrufe)))
    return aufrufe


@pytest.fixture
def gti_aufrufe_totes_modell(monkeypatch, _caches_leer):
    """Wie ``gti_aufrufe``, aber jedes Modell antwortet mit HTTP 200 ohne Werte."""
    aufrufe: list[dict] = []
    tote = frozenset(n for n, _ in WETTER_MODELLE.values() if n)
    monkeypatch.setattr(sfs, "httpx", _HttpxShim(_FakeClient(aufrufe, tote)))
    return aufrufe


async def test_kurzhorizont_modell_ruft_zwei_snapshots_ab(db, gti_aufrufe):
    """icon_d2 (2 Tage) + best_match für den Rest — die Kaskade aus A29/E15-a."""
    anlage = await _seed(db, wetter_modell="icon_d2")
    await kanon_tagesprognose(db, anlage, days=4, skip_jitter=True)

    nach_modell = {a.get("models"): a["forecast_days"] for a in gti_aufrufe}
    assert nach_modell == {"icon_d2": 2, None: SNAPSHOT_HORIZONT_TAGE}, gti_aufrufe


async def test_tage_jenseits_des_modell_horizonts_kollabieren_nicht(db, gti_aufrufe):
    """Die Regressionsbremse für genau den Fall, den A30 erstmals auslöst.

    Tag 0–1 trägt icon_d2 (hoher Pegel), Tag 2–3 best_match (halber Pegel) —
    aber KEIN Tag fällt auf 0. Genau das wäre passiert, wenn das Primärmodell
    über 16 Tage abgefragt würde und mit leeren Tagen den Fallback verdrängte.
    """
    anlage = await _seed(db, wetter_modell="icon_d2")
    kanon = await kanon_tagesprognose(db, anlage, days=4, skip_jitter=True)

    werte = [t.om_kwh for t in kanon.tage]
    assert all(w is not None and w > 0 for w in werte), werte
    assert werte[0] == werte[1] > werte[2] == werte[3], werte


async def test_auto_ruft_unveraendert_genau_einen_snapshot_ab(db, gti_aufrufe):
    """Kontrollprobe: der Default schickt keinen ``models``-Parameter."""
    anlage = await _seed(db, wetter_modell="auto")
    await kanon_tagesprognose(db, anlage, days=4, skip_jitter=True)

    assert len(gti_aufrufe) == 1, gti_aufrufe
    assert "models" not in gti_aufrufe[0]
    assert gti_aufrufe[0]["forecast_days"] == SNAPSHOT_HORIZONT_TAGE


async def test_auto_liefert_dieselben_zahlen_wie_ohne_modellwahl(db, gti_aufrufe):
    """Kontrollprobe an der Zahl: „auto" == ungepflegte Spalte == best_match."""
    auto = await _seed(db, wetter_modell="auto")
    ungepflegt = await _seed(db, wetter_modell=None)

    kanon_auto = await kanon_tagesprognose(db, auto, days=4, skip_jitter=True)
    kanon_leer = await kanon_tagesprognose(db, ungepflegt, days=4, skip_jitter=True)

    assert [t.om_kwh for t in kanon_auto.tage] == [t.om_kwh for t in kanon_leer.tage]
    assert [t.eedc_kwh for t in kanon_auto.tage] == [t.eedc_kwh for t in kanon_leer.tage]


# ── Ausgefallenes Modell: HTTP 200 ohne Werte ───────────────────────────────
#
# Beim Vermessen von A30 aufgefallen (2026-07-28, München): drei der sieben
# wählbaren Modelle liefern über Open-Meteo KEINE Prognose mehr —
# `ecmwf_ifs04` antwortet mit HTTP 200 und 0 von 72 Stundenwerten,
# `ecmwf_seamless`/`meteoswiss_seamless` sind gar keine gültigen Modellnamen
# mehr (HTTP-Fehler). Ohne Auffangnetz hätte A30 diesen Nutzern nicht die
# Modellwahl, sondern die komplette Prognose genommen (Kanon → None → MQTT-
# Sensoren weg). Die Modell-Liste selbst zu korrigieren ist eine
# Produktentscheidung und NICHT Teil von A30.


def test_hat_nutzbares_gti_erkennt_die_leere_antwort():
    assert sfs._hat_nutzbares_gti(None) is False
    assert sfs._hat_nutzbares_gti({}) is False
    assert sfs._hat_nutzbares_gti({"hourly": {}}) is False
    assert sfs._hat_nutzbares_gti(
        {"hourly": {"global_tilted_irradiance": [None, None]}}
    ) is False
    assert sfs._hat_nutzbares_gti(
        {"hourly": {"global_tilted_irradiance": [None, 0.0]}}
    ) is True


async def test_totes_modell_faellt_auf_best_match_statt_auf_nichts(
    db, gti_aufrufe_totes_modell
):
    """Das Auffangnetz: ohne es wäre ``kanon`` hier ``None`` — MQTT-Sensoren weg."""
    anlage = await _seed(db, wetter_modell="ecmwf_ifs04")
    kanon = await kanon_tagesprognose(db, anlage, days=4, skip_jitter=True)

    assert kanon is not None
    werte = [t.eedc_kwh for t in kanon.tage]
    assert all(w is not None and w > 0 for w in werte), werte
    # Zweiter Abruf ohne ``models`` = best_match.
    assert [a.get("models") for a in gti_aufrufe_totes_modell] == ["ecmwf_ifs04", None]


async def test_totes_modell_liefert_exakt_die_best_match_zahlen(
    db, gti_aufrufe_totes_modell
):
    """Was der Nutzer sieht, ist genau das, was er vor A30 sah.

    Dasselbe Double bedient beide Anlagen: für ``models=<Modell>`` leer, für
    best_match (``models`` fehlt) wie immer.
    """
    tot = await _seed(db, wetter_modell="ecmwf_ifs04")
    auto = await _seed(db, wetter_modell="auto")

    kanon_tot = await kanon_tagesprognose(db, tot, days=4, skip_jitter=True)
    kanon_auto = await kanon_tagesprognose(db, auto, days=4, skip_jitter=True)

    assert [t.eedc_kwh for t in kanon_tot.tage] == [t.eedc_kwh for t in kanon_auto.tage]


async def test_kaskade_verwirft_ein_leeres_primaermodell(db, gti_aufrufe_totes_modell):
    """Kurzhorizont-Modell (Kaskaden-Zweig) + leere Primärantwort → best_match.

    Anderer Code-Zweig als oben: hier greift ``if not primary_data`` in
    ``_solar_prognose_snapshot``, nicht der Einzel-Abruf-Zweig.
    """
    anlage = await _seed(db, wetter_modell="icon_d2")
    kanon = await kanon_tagesprognose(db, anlage, days=4, skip_jitter=True)

    assert kanon is not None
    werte = [t.eedc_kwh for t in kanon.tage]
    assert all(w is not None and w > 0 for w in werte), werte
    # Alle vier Tage aus derselben (best_match-)Quelle → gleicher Pegel-Verlauf.
    assert len(set(werte)) == 1, werte
