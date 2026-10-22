"""N-761 (#434, Burkard): «Wetter heute» zeichnet die Stundenreihe der GEWÄHLTEN Quelle.

Die Antwort trägt in ``verbrauchsprofil[].pv_ml_prognose_kw`` die Heute-Reihe der effektiven Quelle (nach dem
Rückfall ``_pq_nach_abruf``) — bis N-761 nur bei SFML; die Solcast-Reihe kam nie in die Antwort, die Kurve blieb
unter «Quelle: Solcast» die eedc-Kurve. ``prognose_quelle_hat_profil`` sagt, ob die Kurve ihr folgt; nach einem
Rückfall auf eedc sagt die Marke nein, auch wenn ``quelle_tagesprofile`` noch das Profil der gewünschten Quelle
trägt (⚑2 des Päckchens). Das Frontend wählt nur (``lib/prognoseAnzeige.pvPrognoseKwDerQuelle``).

Über HTTP mit den Nähten aus ``test_n695_live_wetter_vm_nm_quelle.py`` (feste Uhr des Phasenmoduls).
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from backend.services.prognose_adapter import sfml_stundenprofile_aus_forecast
from backend.tests.test_n695_live_wetter_vm_nm_quelle import (  # noqa: F401 — `naehte` ist die Fixture
    TAG,
    _http,
    _sfml_mit_forecast,
    _solcast,
    naehte,
)

pytestmark = pytest.mark.asyncio


def _reihe(res: dict) -> list:
    return [p.get("pv_ml_prognose_kw") for p in res["verbrauchsprofil"]]


async def test_solcast_mit_stundenprofil_traegt_seine_reihe_und_die_marke(db, naehte):  # noqa: F811
    res = await _http(db, "solcast")
    assert res["prognose_quelle"] == "solcast"
    assert res["prognose_quelle_hat_profil"] is True
    assert _reihe(res) == _solcast().hourly_kw


async def test_solcast_auf_eedc_zurueckgefallen_marke_nein(db, naehte):  # noqa: F811
    naehte["solcast"] = SimpleNamespace(**{**vars(_solcast()), "daily_kwh": None})
    res = await _http(db, "solcast")
    assert res["prognose_quelle"] == "eedc" and res["prognose_quelle_hinweis"]
    assert res["prognose_quelle_hat_profil"] is False
    assert all(v is None for v in _reihe(res))


async def test_sfml_mit_stundenprofil_wie_bisher(db, naehte):  # noqa: F811
    naehte["sfml"] = _sfml_mit_forecast()
    res = await _http(db, "sfml")
    assert res["prognose_quelle_hat_profil"] is True
    erwartet = sfml_stundenprofile_aus_forecast(_sfml_mit_forecast().attribut("stundenprofil"), TAG)[0]
    assert _reihe(res) == [round(v, 2) for v in erwartet]


async def test_sfml_auf_eedc_zurueckgefallen_marke_nein(db, naehte):  # noqa: F811
    """Stundenattribut da, Tageswert fehlt ⇒ Rückfall; bis N-761 meldete die Marke trotzdem ja, und die Kurve
    hätte unter «eedc-Prognose aktiv» die SFML-Reihe gezeigt."""
    sfml = _sfml_mit_forecast()
    werte = {"heute_kwh": None, "morgen_kwh": 18.0, "uebermorgen_kwh": 18.0, "genauigkeit_30d": 91.2}
    naehte["sfml"] = SimpleNamespace(gefunden=True, wert=werte.get, attribut=sfml.attribut)
    res = await _http(db, "sfml")
    assert res["prognose_quelle"] == "eedc"
    assert res["prognose_quelle_hat_profil"] is False
    assert all(v is None for v in _reihe(res))


async def test_sfml_ohne_stundenattribut_bleibt_der_gti_rueckfall_ohne_marke(db, naehte):  # noqa: F811
    res = await _http(db, "sfml")
    assert res["prognose_quelle_hat_profil"] is False
    reihe = _reihe(res)
    assert sum(v for v in reihe if v is not None) == pytest.approx(17.4, abs=0.2)


async def test_eedc_traegt_keine_reihe(db, naehte):  # noqa: F811
    res = await _http(db, "eedc")
    assert res["prognose_quelle_hat_profil"] is False
    assert all(v is None for v in _reihe(res))
