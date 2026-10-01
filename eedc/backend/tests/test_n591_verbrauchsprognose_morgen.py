"""N-591 — die Verbrauchsprognose für MORGEN verlässt eedc (#420, OB73-gif).

*Wer die Batterie zur günstigsten Stunde so laden will, dass sie über die Nacht
reicht, kennt bisher nur den Verbrauch bis Mitternacht.* Der neue Sensor
``eedc_verbrauchsprognose_morgen_kwh`` rechnet **dieselbe** Rechnung wie
``…_heute`` (Modell (a), Entscheid Gernot 01.10.2026): individuelles Profil des
Wochentags von morgen, Wärmepumpen-Anteil mit der Temperaturvorhersage von
morgen (Tagesfaktor, N-593).

Proben nach Vorlage §3 A5 (P1–P9) und §4 (Degradation):

* P1 Freitag ⇒ Wochenend-Profil · P2 Temperaturen von morgen, nicht von heute ·
  P3 Länge wie geliefert (23/25) · P4 kein BDEW-Rückfall · P5 kein zusätzlicher
  Open-Meteo-Abruf hinter dem Kanon · P6 Modell mit Lücke ⇒ best_match ·
  P7 Sensor: Zustand == Σ Stundenprofil, ``datum`` = morgen · P8 steht in
  ``test_n545_neue_sensoren_bei_bestand_abgewaehlt.py`` · P9 „heute" bitgleich:
  ``test_395_*`` laufen ohne Änderung durch diesen Schnitt, dazu der Golden Master.

Keine echte Uhr (N-167): ``now`` wird übergeben bzw. das Modul bekommt eine
gestellte ``datetime``. Kein Netz: ``fetch_gti_forecast`` bzw. der HTTP-Client
darunter sind gestellt.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from zoneinfo import ZoneInfo

import pytest

from backend.services import solar_forecast_service as sfs
from backend.services.verbrauchsprognose_heute import (
    verbrauchsprognose_heute,
    verbrauchsprognose_morgen,
)
from backend.tests import factories

_BERLIN = ZoneInfo("Europe/Berlin")
_MITTWOCH = datetime(2026, 3, 18, 21, 0, tzinfo=_BERLIN)   # morgen: Donnerstag 19.03.
_FREITAG = datetime(2026, 3, 20, 21, 0, tzinfo=_BERLIN)    # morgen: Samstag 21.03.

_WERKTAG = {h: 0.5 for h in range(24)}
_WOCHENENDE = {h: 0.9 for h in range(24)}


def _profil(**extra) -> dict:
    daten = {
        "werktag": _WERKTAG, "tage_werktag": 5, "slots_werktag": 24,
        "wochenende": _WOCHENENDE, "tage_wochenende": 2, "slots_wochenende": 24,
        "quelle": "db",
    }
    daten.update(extra)
    return daten


def _antwort(tage: dict[str, list]) -> dict:
    """Eine Open-Meteo-Antwort mit ``{tag: [temperatur je Eintrag]}`` —
    ``(stunde, temperatur)``-Paare erlauben doppelte/fehlende Stunden (P3)."""
    zeiten: list[str] = []
    temps: list = []
    for tag, werte in tage.items():
        for i, w in enumerate(werte):
            stunde, temp = w if isinstance(w, tuple) else (i, w)
            zeiten.append(f"{tag}T{stunde:02d}:00")
            temps.append(temp)
    return {"hourly": {"time": zeiten, "temperature_2m": temps,
                       "global_tilted_irradiance": [0.0] * len(zeiten)}}


def _fake_fetch(antworten: dict, aufrufe: list | None = None):
    """``fetch_gti_forecast``-Ersatz: Antwort je Modell (``None`` = best_match)."""
    async def fake(latitude, longitude, neigung=35, ausrichtung=0, days=7,
                   timeout=30.0, model=None, skip_jitter=False):
        if aufrufe is not None:
            aufrufe.append({"neigung": neigung, "ausrichtung": ausrichtung, "model": model})
        return antworten.get(model)
    return fake


async def _anlage(db, **kw):
    return await factories.anlage(db, latitude=51.0, longitude=11.0, **kw)


async def _morgen(anlage, db, now, profil, antworten, aufrufe=None):
    with patch(
        "backend.services.verbrauchsprognose_heute.get_live_power_service"
    ) as svc, patch.object(sfs, "fetch_gti_forecast", new=_fake_fetch(antworten, aufrufe)):
        svc.return_value.get_verbrauchsprofil = AsyncMock(return_value=profil)
        return await verbrauchsprognose_morgen(anlage, db, now=now, skip_jitter=True)


# ── P1 Profilwahl: der Wochentag von MORGEN ─────────────────────────────────

async def test_p1_freitag_rechnet_samstag_mit_dem_wochenend_profil(db):
    anlage = await _anlage(db)
    antwort = _antwort({"2026-03-20": [10.0] * 24, "2026-03-21": [10.0] * 24})
    erg = await _morgen(anlage, db, _FREITAG, _profil(), {None: antwort})

    assert erg is not None
    assert erg.profil_typ == "individuell_wochenende"
    assert erg.summe_kwh == pytest.approx(0.9 * 24)
    assert erg.datum == "2026-03-21"


# ── P2 Temperaturen von morgen, nicht von heute ─────────────────────────────

async def test_p2_waermepumpe_rechnet_mit_der_temperatur_von_morgen(db):
    """Referenz 10 Kd; heute 0 °C (Faktor 1,5), morgen 10 °C (5 Kd ⇒ 0,5)."""
    anlage = await _anlage(db)
    wp = {h: 0.2 for h in range(24)}
    antwort = _antwort({"2026-03-18": [0.0] * 24, "2026-03-19": [10.0] * 24})
    erg = await _morgen(
        anlage, db, _MITTWOCH,
        _profil(wp_werktag=wp, referenz_hdd_kd=10.0), {None: antwort},
    )

    assert erg is not None
    assert erg.temperatur_c == [10.0] * 24
    assert erg.wp_stunden_kwh == [0.1] * 24, "0,2 kW × 0,5 — nicht × 1,5 (heute)"
    # Haus 0,3 + WP 0,2 × 0,5 = 0,4 kW je Stunde
    assert erg.summe_kwh == pytest.approx(0.4 * 24)


# ── P3 Die Länge ist die gelieferte ─────────────────────────────────────────

@pytest.mark.parametrize("eintraege", [
    [(h, 10.0) for h in range(24) if h != 2],                       # 23 Einträge
    [(h, 10.0) for h in range(3)] + [(2, 10.0)] + [(h, 10.0) for h in range(3, 24)],  # 25
])
async def test_p3_so_viele_stunden_wie_geliefert(db, eintraege):
    anlage = await _anlage(db)
    antwort = _antwort({"2026-03-19": eintraege})
    erg = await _morgen(anlage, db, _MITTWOCH, _profil(), {None: antwort})

    assert erg is not None
    assert len(erg.stunden_kwh) == len(eintraege)
    assert erg.stunden_label == [h for h, _ in eintraege]
    assert erg.summe_kwh == pytest.approx(round(0.5 * len(eintraege), 1))


# ── P4 Kein Rückfall auf das Standardprofil ─────────────────────────────────

async def test_p4_nur_werktags_profil_und_morgen_samstag_gibt_keinen_sensor(db):
    anlage = await _anlage(db)
    nur_werktag = {"werktag": _WERKTAG, "tage_werktag": 5, "slots_werktag": 24,
                   "wochenende": None, "tage_wochenende": 1, "quelle": "db"}
    aufrufe: list = []
    antwort = _antwort({"2026-03-21": [10.0] * 24})
    erg = await _morgen(anlage, db, _FREITAG, nur_werktag, {None: antwort}, aufrufe)

    assert erg is None, "N-332: ohne eigenes Profil für Samstag kein Wert, nie BDEW"
    assert aufrufe == [], "ohne Profil wird auch nichts abgerufen"


# ── P5 Kein zusätzlicher Open-Meteo-Abruf hinter dem Kanon ──────────────────

_P5_LAT, _P5_LON = 47.123, 8.456
_P5_HEUTE = date(2026, 3, 18)


class _FakeResponse:
    def __init__(self, data):
        self._data = data

    def raise_for_status(self):
        return None

    def json(self):
        return self._data


def _volle_antwort(params: dict) -> dict:
    """Eine vollständige GTI-Antwort über ``forecast_days`` Tage ab 18.03.2026."""
    tage = int(params["forecast_days"])
    zeiten = [
        f"{(_P5_HEUTE + timedelta(days=d)).isoformat()}T{h:02d}:00"
        for d in range(tage) for h in range(24)
    ]
    n = len(zeiten)
    gti = [max(0.0, 600.0 - abs(h - 12) * 100.0) for _ in range(tage) for h in range(24)]
    return {
        "hourly": {
            "time": zeiten, "global_tilted_irradiance": gti, "shortwave_radiation": gti,
            "direct_radiation": [0.0] * n, "diffuse_radiation": [0.0] * n,
            "temperature_2m": [5.0] * n, "cloud_cover": [20.0] * n,
            "precipitation": [0.0] * n, "snowfall": [0.0] * n,
            "sunshine_duration": [3600.0] * n, "weather_code": [1] * n,
        },
        "daily": {
            "time": [(_P5_HEUTE + timedelta(days=d)).isoformat() for d in range(tage)],
            "shortwave_radiation_sum": [10.0] * tage, "sunshine_duration": [30000.0] * tage,
            "temperature_2m_max": [8.0] * tage, "temperature_2m_min": [2.0] * tage,
            "precipitation_sum": [0.0] * tage, "snowfall_sum": [0.0] * tage,
            "weather_code": [1] * tage,
        },
    }


async def test_p5_morgen_trifft_den_cache_eintrag_des_kanons(db, monkeypatch):
    """Zähler auf die Cache-Fehlschläge von ``fetch_gti_forecast`` = echte
    HTTP-Abrufe. Erst der Kanon wie im Export (``days=4``), dann morgen:
    morgen darf **keinen** weiteren Abruf auslösen."""
    from backend.models import Investition
    from backend.services.korrekturprofil_lookup import _cache as korr_cache
    from backend.services.prognose_kanon import kanon_tagesprognose
    from backend.services.wetter import cache as wc
    import backend.api.routes.live_wetter as lw

    for speicher in (wc._cache, wc._error_cache):
        for k in [k for k in speicher if k.startswith(f"gti:{_P5_LAT:.2f}:{_P5_LON:.2f}")]:
            del speicher[k]
    korr_cache.clear()

    async def fake_lernfaktor(anlage_id, db, quelle="openmeteo"):
        return 1.0

    monkeypatch.setattr(lw, "_get_lernfaktor", fake_lernfaktor)

    abrufe: list[dict] = []

    class _FakeClient:
        def __init__(self, *a, **kw):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, url, params=None):
            abrufe.append(dict(params or {}))
            return _FakeResponse(_volle_antwort(params))

    monkeypatch.setattr(sfs.httpx, "AsyncClient", _FakeClient)

    anlage = await factories.anlage(db, latitude=_P5_LAT, longitude=_P5_LON)
    # Zwei Dachflächen: Ost 8 kWp (stärkste Gruppe) und West 4 kWp.
    db.add(Investition(anlage_id=anlage.id, typ="pv-module", bezeichnung="Ost",
                       anschaffungsdatum=date(2024, 1, 1), aktiv=True,
                       leistung_kwp=8.0, neigung_grad=30, parameter={"ausrichtung_grad": -90}))
    db.add(Investition(anlage_id=anlage.id, typ="pv-module", bezeichnung="West",
                       anschaffungsdatum=date(2024, 1, 1), aktiv=True,
                       leistung_kwp=4.0, neigung_grad=20, parameter={"ausrichtung_grad": 90}))
    await db.flush()

    kanon = await kanon_tagesprognose(db, anlage, days=4, skip_jitter=True, heute=_P5_HEUTE)
    assert kanon is not None
    nach_kanon = len(abrufe)
    assert nach_kanon == 2, f"ein Abruf je Orientierungsgruppe: {abrufe}"

    with patch(
        "backend.services.verbrauchsprognose_heute.get_live_power_service"
    ) as svc:
        svc.return_value.get_verbrauchsprofil = AsyncMock(return_value=_profil())
        morgen = await verbrauchsprognose_morgen(
            anlage, db, now=datetime(2026, 3, 18, 21, 0, tzinfo=_BERLIN), skip_jitter=True,
        )

    assert morgen is not None and morgen.datum == "2026-03-19", "morgen muss entstanden sein"
    assert morgen.temperatur_c == [5.0] * 24
    assert len(abrufe) == nach_kanon, (
        f"morgen hat {len(abrufe) - nach_kanon} zusätzliche Open-Meteo-Abrufe ausgelöst "
        f"— der Aufruf trifft den Cache-Eintrag des Kanons nicht: {abrufe[nach_kanon:]}"
    )


# ── P6 Lücke im Anlagenmodell ⇒ best_match ──────────────────────────────────

async def test_p6_fehlt_dem_modell_eine_stunde_gilt_best_match(db):
    anlage = await _anlage(db, wetter_modell="icon_d2")
    modell = [12.0] * 24
    modell[5] = None
    antworten = {
        "icon_d2": _antwort({"2026-03-19": modell}),
        None: _antwort({"2026-03-19": [3.0] * 24}),
    }
    aufrufe: list = []
    erg = await _morgen(anlage, db, _MITTWOCH, _profil(), antworten, aufrufe)

    assert erg is not None
    assert erg.temperatur_c == [3.0] * 24
    assert [a["model"] for a in aufrufe] == ["icon_d2", None]


async def test_p6b_vollstaendiges_modell_braucht_kein_best_match(db):
    anlage = await _anlage(db, wetter_modell="icon_d2")
    antworten = {"icon_d2": _antwort({"2026-03-19": [12.0] * 24}),
                 None: _antwort({"2026-03-19": [3.0] * 24})}
    aufrufe: list = []
    erg = await _morgen(anlage, db, _MITTWOCH, _profil(), antworten, aufrufe)

    assert erg.temperatur_c == [12.0] * 24
    assert [a["model"] for a in aufrufe] == ["icon_d2"], "kein zweiter Abruf ohne Lücke"


# ── P7 Der Sensor im Export ─────────────────────────────────────────────────

def _fake_kanon():
    tag = SimpleNamespace(
        eedc_kwh=10.0, vm_kwh=5.0, nm_kwh=5.0, profil=None,
        abregelung_om_kwh=None, abregelung_om_stundenprofil_kwh=None, grenzen_kw=None,
    )
    return SimpleNamespace(
        tage=[tag, tag, tag, tag], rest_heute_kwh=2.0, heute_rollend_kwh=10.0,
        ist_bisher_kwh=8.0, ist_bisher_bis_slot=12,
    )


async def _export_sensoren(db, anlage, monkeypatch, profil):
    import backend.services.verbrauchsprognose_heute as vph
    from backend.api.routes.ha_export import calculate_anlage_sensors
    from backend.models import Investition, Monatsdaten

    # Ohne Monatsdaten liefert der Export gar keine Sensoren (wie `_seed_pv_anlage`
    # in test_ha_export_prognose_150.py).
    db.add(Monatsdaten(anlage_id=anlage.id, jahr=2025, monat=1,
                       netzbezug_kwh=100.0, einspeisung_kwh=200.0))
    db.add(Investition(anlage_id=anlage.id, typ="pv-module", bezeichnung="Dach",
                       leistung_kwp=10.0, anschaffungsdatum=date(2024, 1, 1)))
    await db.flush()

    class _Uhr(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 3, 18, 21, 0, tzinfo=tz)

    monkeypatch.setattr(vph, "datetime", _Uhr)
    wp_heute = ({"hourly": {"time": [f"2026-03-18T{h:02d}:00" for h in range(24)],
                            "temperature_2m": [10.0] * 24}}, None, True)
    antwort = _antwort({"2026-03-18": [10.0] * 24,
                        "2026-03-19": [(h, 10.0 + h / 10) for h in range(24)]})
    with patch(
        "backend.services.prognose_kanon.kanon_tagesprognose",
        new=AsyncMock(return_value=_fake_kanon()),
    ), patch(
        "backend.services.verbrauchsprognose_heute.get_live_power_service"
    ) as svc, patch(
        "backend.api.routes.live_wetter._lade_forecast_gecached",
        new=AsyncMock(return_value=wp_heute),
    ), patch.object(sfs, "fetch_gti_forecast", new=_fake_fetch({None: antwort})), patch(
        "backend.api.routes.ha_export.anlage_sensorwerte.berechne_preis_export",
        new=AsyncMock(return_value=None),
    ):
        svc.return_value.get_verbrauchsprofil = AsyncMock(return_value=profil)
        sensors = await calculate_anlage_sensors(db, anlage, skip_jitter=True)
    return {sv.definition.key: sv for sv in sensors}


async def test_p7_sensor_zustand_ist_die_summe_und_traegt_das_datum(db, monkeypatch):
    anlage = await _anlage(db)
    wp = {h: 0.1 for h in range(24)}
    by_key = await _export_sensoren(
        db, anlage, monkeypatch, _profil(wp_werktag=wp, referenz_hdd_kd=5.0),
    )

    assert "eedc_verbrauchsprognose_morgen_kwh" in by_key
    sv = by_key["eedc_verbrauchsprognose_morgen_kwh"]
    z = sv.zusatz_attribute
    assert z["datum"] == "2026-03-19"
    assert z["profil_typ"] == "individuell_werktag"
    assert z["profil_tage"] == 5 and z["profil_slots"] == 24
    assert len(z["stundenprofil_kwh"]) == 24
    assert sv.value == pytest.approx(sum(z["stundenprofil_kwh"]), abs=0.05)
    assert len(z["wp_stundenprofil_kwh"]) == 24
    # Der Nachbar für heute bleibt da und ist eine andere Zahl (anderes Wetter).
    assert "eedc_verbrauchsprognose_heute_kwh" in by_key


async def test_p7b_ohne_profil_fuer_morgen_kein_sensor_aber_heute_bleibt(db, monkeypatch):
    """Nur ein Wochenend-Profil, Mittwoch ⇒ weder heute (Mittwoch) noch morgen
    (Donnerstag) haben ein eigenes Profil: kein Verbrauchssensor — die übrigen
    Prognose-Sensoren bleiben (der Export stirbt nicht am fehlenden morgen)."""
    anlage = await _anlage(db)
    nur_we = {"werktag": None, "tage_werktag": 1,
              "wochenende": _WOCHENENDE, "tage_wochenende": 2, "quelle": "db"}
    by_key = await _export_sensoren(db, anlage, monkeypatch, nur_we)

    assert "eedc_verbrauchsprognose_morgen_kwh" not in by_key
    assert "eedc_prognose_heute_kwh" in by_key, "die übrigen Prognose-Sensoren bleiben"


# ── Degradation (Vorlage §4) ────────────────────────────────────────────────

async def test_ohne_koordinaten_kein_wert(db):
    anlage = await factories.anlage(db)
    assert await _morgen(anlage, db, _MITTWOCH, _profil(), {}) is None


async def test_forecast_nicht_erreichbar_kein_wert(db):
    anlage = await _anlage(db)
    assert await _morgen(anlage, db, _MITTWOCH, _profil(), {None: None}) is None


async def test_keine_eintraege_fuer_morgen_kein_wert(db):
    anlage = await _anlage(db)
    nur_heute = _antwort({"2026-03-18": [10.0] * 24})
    assert await _morgen(anlage, db, _MITTWOCH, _profil(), {None: nur_heute}) is None


async def test_wp_profil_ohne_referenz_rechnet_ohne_korrektur(db):
    anlage = await _anlage(db)
    wp = {h: 0.2 for h in range(24)}
    antwort = _antwort({"2026-03-19": [-10.0] * 24})
    erg = await _morgen(anlage, db, _MITTWOCH, _profil(wp_werktag=wp), {None: antwort})

    assert erg is not None
    assert erg.summe_kwh == pytest.approx(12.0), "Faktor 1, wie heute ohne Referenz"
    assert erg.wp_stunden_kwh is None


async def test_stunde_ohne_temperatur_auch_bei_best_match_bleibt_unkorrigiert(db):
    anlage = await _anlage(db)
    wp = {h: 0.2 for h in range(24)}
    temps = [0.0] * 24
    temps[4] = None
    erg = await _morgen(
        anlage, db, _MITTWOCH,
        _profil(wp_werktag=wp, referenz_hdd_kd=10.0),
        {None: _antwort({"2026-03-19": temps})},
    )

    assert erg is not None
    assert erg.wp_stunden_kwh[4] == pytest.approx(0.2)
    assert erg.wp_stunden_kwh[5] == pytest.approx(0.3)


# ── P9 „heute" ist vom Bau für morgen nicht berührt ─────────────────────────

async def test_p9_heute_und_morgen_teilen_den_rechenkern(db):
    """Gleiches Profil, gleiche Temperaturen ⇒ gleiche Reihen (nur ``datum``
    unterscheidet sie). Die Bitgleichheit von „heute" gegen den Stand vor dem
    Bau belegen ``test_395_*`` (unverändert durch diesen Schnitt) und der GM."""
    anlage = await _anlage(db)
    wp = {h: 0.2 for h in range(24)}
    profil = _profil(wp_werktag=wp, referenz_hdd_kd=10.0)
    temps = [float(h % 7) for h in range(24)]
    wp_heute = ({"hourly": {"time": [f"2026-03-18T{h:02d}:00" for h in range(24)],
                            "temperature_2m": temps}}, None, True)
    with patch(
        "backend.services.verbrauchsprognose_heute.get_live_power_service"
    ) as svc, patch(
        "backend.api.routes.live_wetter._lade_forecast_gecached",
        new=AsyncMock(return_value=wp_heute),
    ):
        svc.return_value.get_verbrauchsprofil = AsyncMock(return_value=profil)
        heute = await verbrauchsprognose_heute(anlage, db, now=_MITTWOCH)
    morgen = await _morgen(anlage, db, _MITTWOCH, profil,
                           {None: _antwort({"2026-03-19": temps})})

    assert heute is not None and morgen is not None
    assert heute.datum is None and morgen.datum == "2026-03-19"
    assert heute.stunden_kwh == morgen.stunden_kwh
    assert heute.wp_stunden_kwh == morgen.wp_stunden_kwh
    assert heute.summe_kwh == morgen.summe_kwh
