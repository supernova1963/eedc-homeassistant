"""N-690 (ADR-002 P4): ein unvollständiger lokaler Fan-out sagt es — und wird nicht gecacht.

⛔ **Der Defekt:** die Live-Wetter-Route holt das GTI je Orientierungsgruppe
selbst (``_fetch_multi_string_gti``) und bekommt dazu ``multi_vollstaendig``
zurück — und las es nie. Fällt eine Gruppe aus UND liefert auch der Kanon
keinen Tageswert (er lässt einen Teil-Fan-out seit N-423 bewusst leer), bleibt
in *Cockpit → Live* der lokale Wert stehen: um die ausgefallenen Gruppen zu
klein, als ganz normale Tagesprognose („~x kWh PV", Heute-Kopfzahl der
Solar-Aussicht, PV-Kurve), ohne ein Wort dazu. Der lokale Cache hielt dieses
Ergebnis samt ``vollstaendig=False`` 3600 s.

**Was jetzt gilt** (P4 wie N77 in ``/solar-prognose``: der Wert bleibt, er wird
beschriftet — kein Ersatz, keine Kappung):

* ``pv_prognose_hinweis`` trägt den Satz, sobald die eedc-Werte von heute aus
  einem unvollständigen lokalen Fan-out stammen (der Kanon hat sie nicht
  ersetzt);
* ``_lade_forecast_gecached`` cacht ein unvollständiges Ergebnis nicht — der
  nächste Aufruf versucht es neu, statt es eine Stunde zu halten.

Gegenfälle (kein Hinweis): Kanon vollständig (dann zeigt die Kachel ihn, nicht
den lokalen Wert); lokaler Fan-out vollständig; kein lokaler Fan-out (der
Prefetch legt für Multi-String ``(data, None, False)`` ab — dort rechnet der
lokale Pfad mit der Globalstrahlung, eine Teilsumme ist das nicht).

**Der Zwilling im Energieprofil** (``services/energie_profil/_helpers.py::
_fetch_wetter``, Wetter-IST für Aggregator und Archiv-Nachzug) hatte dieselbe
Lücke, mit gespeicherter Folge: eine ausgefallene Gruppe wurde still
übersprungen, das GTI war um ihr Gewicht zu klein und die Performance Ratio
entsprechend zu hoch (gemessen 7 200 → 3 600 Wh/m², PR 0,694 → 1,389). Jetzt
gilt die Kanon-Regel (N-423): ein Teil-Fan-out liefert **kein** GTI — derselbe
Weg wie beim Ausfall aller Gruppen, also keine PR statt einer falschen. Der
Archiv-Nachzug ruft streng: dort schreibt ein Teil-Ausfall nichts und setzt
keinen Altbestand-Marker, die nächste Nacht holt den Tag nach.

Schwesterdateien: ``test_multi_string_forecast_robustness_306.py`` (Flag des
Fan-outs, Prefetch-Tupel), ``test_wurzelmuster_p4_teilsumme.py`` (P4 an
``/solar-prognose`` und der Tagesprognose), ``test_n689_live_wetter_antwortmodell.py``.
"""
from __future__ import annotations

from datetime import date
from types import SimpleNamespace

import pytest

from backend.api.routes import live_wetter
from backend.api.routes.live_wetter import LiveWetterResponse, get_live_wetter
from backend.models import Anlage, Investition

pytestmark = pytest.mark.asyncio

# Festes Datum (Wächter `test_konformitaet_echte_uhr_in_tests.py`); keine Aussage hängt am Tag.
TAG = "2026-03-10"
GTI_VOLL = [0.0] * 6 + [600.0] * 12 + [0.0] * 6
# Eine von zwei gleich großen Gruppen fehlt ⇒ das gewichtete GTI ist halb so groß.
GTI_HALB = [v * 0.5 for v in GTI_VOLL]


def _om() -> dict:
    tag = TAG
    times = [f"{tag}T{h:02d}:00" for h in range(24)]
    n = len(times)
    return {
        "hourly": {
            "time": times,
            "temperature_2m": [12.0] * n, "weather_code": [1] * n, "cloud_cover": [30] * n,
            "precipitation": [0.0] * n,
            "shortwave_radiation": [0.0] * 6 + [300.0] * 12 + [0.0] * 6,
            "sunshine_duration": [0.0] * 6 + [3000.0] * 12 + [0.0] * 6,
        },
        "daily": {"temperature_2m_min": [6.0], "temperature_2m_max": [15.0],
                  "sunrise": [f"{tag}T06:40"], "sunset": [f"{tag}T18:10"]},
    }


def _kanon(voll: bool):
    """Der Kanon in der Form, die er seit N-423 liefert — voll oder Teil-Fan-out."""
    from backend.services.prognose_kanon import KanonPrognose, KanonTag
    if voll:
        slots = [round(max(0.0, 2.6 - 0.37 * abs(h - 12.5)), 3) for h in range(24)]
        tag = KanonTag(datum=TAG, om_kwh=19.9, eedc_kwh=21.4, vm_kwh=9.9, nm_kwh=11.4,
                       profil=SimpleNamespace(stundenprofil_export_kwh=slots),
                       om_stundenprofil_kwh=slots, om_vollstaendig=True)
        return KanonPrognose(tage=[tag], rest_heute_kwh=7.3, ist_bisher_kwh=13.2,
                             heute_rollend_kwh=20.5, skalar_fallback=None)
    tag = KanonTag(datum=TAG, om_kwh=None, eedc_kwh=None, vm_kwh=None, nm_kwh=None,
                   profil=None, om_stundenprofil_kwh=None, om_vollstaendig=False)
    return KanonPrognose(tage=[tag], rest_heute_kwh=None, ist_bisher_kwh=13.2,
                         heute_rollend_kwh=None, skalar_fallback=None)


@pytest.fixture
def naehte(monkeypatch):
    import backend.services.ha_state_service as hss
    import backend.services.mqtt_inbound_service as mis
    import backend.services.prognose_kanon as pk
    import backend.services.solcast_service as scs
    import backend.services.verbrauchsprognose_heute as vph

    stand = {"forecast": None, "kanon": None}

    async def _lade(anlage, gruppen, cache_key):  # noqa: ARG001
        return stand["forecast"]

    async def _keins(*a, **k):  # noqa: ARG001
        return None

    async def _kanon_f(*a, **k):  # noqa: ARG001
        return stand["kanon"]

    async def _wahl(*a, **k):  # noqa: ARG001
        return vph.ProfilWahl()

    class _HA:
        is_available = False

    monkeypatch.setattr(live_wetter, "_lade_forecast_gecached", _lade)
    monkeypatch.setattr(live_wetter, "_get_lernfaktor", _keins)
    monkeypatch.setattr(live_wetter, "_speichere_prognose", lambda *a, **k: _keins())
    monkeypatch.setattr(pk, "kanon_tagesprognose", _kanon_f)
    monkeypatch.setattr(vph, "waehle_verbrauchsprofil", _wahl)
    monkeypatch.setattr(hss, "get_ha_state_service", lambda: _HA())
    monkeypatch.setattr(mis, "get_mqtt_inbound_service", lambda: None)
    monkeypatch.setattr(scs, "get_solcast_forecast", _keins)
    return stand


async def _anlage_zwei_dächer(db) -> Anlage:
    anlage = Anlage(anlagenname="N-690", leistung_kwp=10.0, latitude=48.0, longitude=11.0)
    db.add(anlage)
    await db.flush()
    for name, azimut in (("Ost", -90), ("West", 90)):
        db.add(Investition(
            anlage_id=anlage.id, typ="pv-module", bezeichnung=name,
            anschaffungsdatum=date(2024, 1, 1), leistung_kwp=5.0,
            neigung_grad=30.0, parameter={"ausrichtung_grad": azimut},
        ))
    await db.flush()
    return anlage


async def _antwort(db, naehte, *, gti, vollstaendig, kanon_voll) -> dict:
    anlage = await _anlage_zwei_dächer(db)
    naehte["forecast"] = (_om(), gti, vollstaendig)
    naehte["kanon"] = _kanon(kanon_voll)
    roh = await get_live_wetter(anlage_id=anlage.id, demo=False, db=db)
    # Was beim Anwender ankommt: durch das Antwortmodell gefiltert (wie FastAPI).
    return LiveWetterResponse.model_validate(roh).model_dump(mode="json")


async def test_beide_fanouts_unvollstaendig_sagen_es(db, naehte):
    """Der Fall aus der Analyse: lokal halb, Kanon leer ⇒ halber Wert MIT Hinweis."""
    res = await _antwort(db, naehte, gti=GTI_HALB, vollstaendig=False, kanon_voll=False)

    assert res["verfuegbar"] is True
    assert res["pv_prognose_kwh"] is not None and res["pv_prognose_kwh"] > 0
    hinweis = res.get("pv_prognose_hinweis")
    assert hinweis, (
        f"Teilsumme {res['pv_prognose_kwh']} kWh ohne Hinweis — der lokale Fan-out war "
        "unvollständig, der Kanon hat ihn nicht ersetzt, und die Antwort sagt es nicht "
        "(ADR-002 P4, N-690)."
    )
    assert "unvollständig" in hinweis


async def test_der_wert_bleibt_er_wird_nur_beschriftet(db, naehte):
    """Kein Ersatz, keine Kappung: die Zahl ist dieselbe wie ohne den Hinweis —
    halb so groß wie bei vollständigem Fan-out (eine von zwei gleichen Gruppen fehlt)."""
    halb = await _antwort(db, naehte, gti=GTI_HALB, vollstaendig=False, kanon_voll=False)
    voll = await _antwort(db, naehte, gti=GTI_VOLL, vollstaendig=True, kanon_voll=False)

    assert voll["pv_prognose_hinweis"] is None
    assert halb["pv_prognose_kwh"] == pytest.approx(voll["pv_prognose_kwh"] / 2, rel=0.05)


@pytest.mark.parametrize("gti, vollstaendig, kanon_voll, warum", [
    (GTI_HALB, False, True, "Kanon vollständig — die Kachel zeigt ihn, nicht den lokalen Wert"),
    (GTI_VOLL, True, False, "lokaler Fan-out vollständig — keine Teilsumme"),
    (None, False, False, "kein lokaler Fan-out (Prefetch-Eintrag) — Globalstrahlung, keine Teilsumme"),
])
async def test_kein_hinweis_wo_keine_teilsumme_steht(db, naehte, gti, vollstaendig, kanon_voll, warum):
    res = await _antwort(db, naehte, gti=gti, vollstaendig=vollstaendig, kanon_voll=kanon_voll)
    assert res["verfuegbar"] is True
    assert res.get("pv_prognose_hinweis") is None, warum


# ── Cache: ein unvollständiges Ergebnis wird nicht eine Stunde gehalten ─────


class _Antwort:
    def raise_for_status(self):
        return None

    def json(self):
        return _om()


class _Client:
    def __init__(self, *a, **k):  # noqa: ARG002
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def get(self, *a, **k):  # noqa: ARG002
        return _Antwort()


@pytest.mark.parametrize("vollstaendig, gecacht", [(False, False), (True, True)])
async def test_unvollstaendiger_fanout_wird_nicht_gecacht(monkeypatch, vollstaendig, gecacht):
    gesetzt: list = []
    gti = GTI_VOLL if vollstaendig else GTI_HALB

    async def _fanout(lat, lon, gruppen):  # noqa: ARG001
        return list(gti), vollstaendig

    monkeypatch.setattr(live_wetter, "_cache_get", lambda key: None)
    monkeypatch.setattr(live_wetter, "_error_cache_check", lambda key: False)
    monkeypatch.setattr(live_wetter, "_cache_set", lambda key, data, ttl: gesetzt.append((key, data[2], ttl)))
    monkeypatch.setattr(live_wetter, "_fetch_multi_string_gti", _fanout)
    monkeypatch.setattr(live_wetter.httpx, "AsyncClient", _Client)

    anlage = SimpleNamespace(id=1, latitude=48.0, longitude=11.0, wetter_modell="auto")
    gruppen = [{"neigung": 30, "ausrichtung": -90, "kwp": 5.0}, {"neigung": 30, "ausrichtung": 90, "kwp": 5.0}]
    data, multi_gti, voll = await live_wetter._lade_forecast_gecached(anlage, gruppen, "k")

    # Die Rückgabe ist in beiden Fällen dieselbe — nur der Cache unterscheidet sich.
    assert voll is vollstaendig and multi_gti == gti
    assert bool(gesetzt) is gecacht, (
        "Ein unvollständiger Fan-out landete im lokalen Cache und hält dort "
        f"{live_wetter.LIVE_WETTER_CACHE_TTL} s (N-690)." if not gecacht
        else "Ein vollständiger Fan-out muss weiter gecacht werden."
    )


# ── Zwilling: Wetter-IST im Energieprofil (`_helpers._fetch_wetter`) ─────────

_PR_PV_KWH, _PR_KWP = 50.0, 10.0


def _zwilling_client(ausfall_azimut=None):
    """Open-Meteo gestellt: Haupt-Abruf + je Gruppe ein GTI-Abruf; eine Gruppe kann 429 liefern."""
    import httpx

    times = [f"{TAG}T{h:02d}:00" for h in range(24)]

    class _R:
        def __init__(self, js, fail=False):
            self.js, self.fail = js, fail

        def raise_for_status(self):
            if self.fail:
                req = httpx.Request("GET", "http://om.invalid")
                raise httpx.HTTPStatusError("429", request=req, response=httpx.Response(429, request=req))

        def json(self):
            return self.js

    class _C:
        def __init__(self, *a, **k):  # noqa: ARG002
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, url, params=None):  # noqa: ARG002
            if params.get("hourly") == "global_tilted_irradiance":
                return _R({"hourly": {"time": times, "global_tilted_irradiance": GTI_VOLL}},
                          fail=params["azimuth"] == ausfall_azimut)
            return _R({"hourly": {
                "time": times, "temperature_2m": [15.0] * 24, "shortwave_radiation": [400.0] * 24,
                "cloud_cover": [20] * 24, "precipitation": [0.0] * 24, "weather_code": [1] * 24,
            }})
    return _C


def _zwei_gruppen_module():
    return [
        Investition(typ="pv-module", bezeichnung=n, leistung_kwp=5.0, neigung_grad=30.0,
                    parameter={"ausrichtung_grad": az}, anschaffungsdatum=date(2024, 1, 1))
        for n, az in (("Ost", -90), ("West", 90))
    ]


async def _zwilling(monkeypatch, ausfall_azimut, **kw):
    import httpx
    from backend.services.energie_profil import _helpers

    monkeypatch.setattr(httpx, "AsyncClient", _zwilling_client(ausfall_azimut))
    anlage = SimpleNamespace(latitude=48.0, longitude=11.0)
    je_tag = await _helpers._fetch_wetter(
        anlage, "http://om.invalid/forecast", {"forecast_days": 1}, _zwei_gruppen_module(), **kw,
    )
    return je_tag[date.fromisoformat(TAG)]


def _gti_summe_und_pr(stunden: dict):
    """Wie der Aggregator: Σ der vorhandenen GTI-Stunden, PR über die Layer-Formel."""
    from backend.core.berechnungen.performance_ratio import berechne_performance_ratio
    summe = sum(v["gti_wm2"] for v in stunden.values() if v["gti_wm2"] is not None)
    return summe, berechne_performance_ratio(_PR_PV_KWH, summe, _PR_KWP)


async def test_zwilling_vollstaendig_unveraendert(monkeypatch):
    stunden = await _zwilling(monkeypatch, ausfall_azimut=None)
    summe, pr = _gti_summe_und_pr(stunden)
    assert summe == pytest.approx(7200.0)
    assert pr == pytest.approx(0.694)


async def test_zwilling_teilausfall_liefert_kein_gti_und_keine_pr(monkeypatch):
    """Eine von zwei Gruppen fällt aus ⇒ kein GTI (wie beim Totalausfall), nicht die halbe Summe."""
    stunden = await _zwilling(monkeypatch, ausfall_azimut=90)
    summe, pr = _gti_summe_und_pr(stunden)
    assert pr is None, (
        f"Teil-Fan-out: GTI-Summe {summe} Wh/m² und PR {pr} — eine Teilsumme wurde als "
        "Einstrahlung des Tages geliefert und ergäbe eine zu hohe Performance Ratio (N-690)."
    )
    assert all(v["gti_wm2"] is None for v in stunden.values())
    # Die übrigen Wetterspalten bleiben — nur das GTI fehlt.
    assert stunden[12]["temperatur_c"] == 15.0
    assert stunden[12]["globalstrahlung_wm2"] == 400.0


async def test_zwilling_streng_wirft_beim_teilausfall(monkeypatch):
    from backend.services.energie_profil import _helpers
    assert hasattr(_helpers, "GtiFanoutUnvollstaendig"), "Signal für den Archiv-Nachzug fehlt (N-690)."
    with pytest.raises(_helpers.GtiFanoutUnvollstaendig):
        await _zwilling(monkeypatch, ausfall_azimut=90, streng=True)
    # vollständig: streng ändert nichts
    stunden = await _zwilling(monkeypatch, ausfall_azimut=None, streng=True)
    assert _gti_summe_und_pr(stunden)[0] == pytest.approx(7200.0)


async def test_archiv_nachzug_schreibt_beim_teilausfall_nichts(db, monkeypatch):
    """Der Archiv-Nachzug überschreibt den Tag nicht mit einer Teilsumme (und nicht mit
    „kein GTI") — er meldet `fehler`, damit kein Altbestand-Marker gesetzt wird und die
    nächste Nacht den Tag nachholt."""
    import httpx
    from sqlalchemy import select
    from backend.models.tages_energie_profil import TagesEnergieProfil, TagesZusammenfassung
    from backend.services.energie_profil import archiv_nachzug

    anlage = Anlage(anlagenname="N-690 Archiv", leistung_kwp=10.0, latitude=48.0, longitude=11.0)
    db.add(anlage)
    await db.flush()
    for inv in _zwei_gruppen_module():
        inv.anlage_id = anlage.id
        db.add(inv)
    tag = date.fromisoformat(TAG)
    for h in range(24):
        db.add(TagesEnergieProfil(anlage_id=anlage.id, datum=tag, stunde=h,
                                  pv_kw=5.0 if 6 <= h < 16 else 0.0, verbrauch_kw=0.4))
    db.add(TagesZusammenfassung(anlage_id=anlage.id, datum=tag, stunden_verfuegbar=24,
                                gti_summe_wh_m2=6500.0, performance_ratio=0.77))
    await db.commit()

    monkeypatch.setattr(httpx, "AsyncClient", _zwilling_client(ausfall_azimut=90))
    erg = await archiv_nachzug.wetter_nachziehen_bereich(anlage, db, tag, tag)

    tz = (await db.execute(select(TagesZusammenfassung).where(
        TagesZusammenfassung.anlage_id == anlage.id, TagesZusammenfassung.datum == tag,
    ))).scalars().one()
    assert erg["status"] == "fehler", (
        f"Teil-Ausfall im Archiv-Nachzug lief als {erg['status']!r} durch — der Altbestand-"
        "Marker würde gesetzt und der Tag nie wieder nachgezogen (N-690)."
    )
    assert tz.gti_summe_wh_m2 == 6500.0 and tz.performance_ratio == 0.77, (
        f"Gespeicherter Tag überschrieben: GTI {tz.gti_summe_wh_m2}, PR {tz.performance_ratio}"
    )
