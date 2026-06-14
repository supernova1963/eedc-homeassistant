"""Charakterisierungs-Tests: live_wetter._berechne_verbrauchsprofil.

Spur 0 des Backend-Refactoring-Plans: live_wetter.py ist über ~9 Dateien breit
abgedeckt (Endpoint-Gründe, _fetch_multi_string_gti, _speichere_prognose,
Lernfaktor-Whitelist, Korrekturprofil-/eedc-Prognose-Kaskade). Symbol-Audit
zeigte eine echte Lücke: `_berechne_verbrauchsprofil` (reine Funktion, PV-Ertrag
+ Verbrauchsprofil) hatte KEINE Tests. Diese pinnen ihr Verhalten vor einer
möglichen WetterCalculator-Extraktion.

Konstanten (Stand v3.45.0): DEFAULT_SYSTEM_LOSSES=0.14, TEMP_COEFFICIENT=0.004
(−0,4 %/°C über 25 °C Modultemp), HEIZGRENZE=15,0 °C. BDEW-Lastprofil
_LASTPROFIL_KW deckt Stunden 6–20 ab, sonst 0,3 kW.

Rückgabe: (profil, pv_prognose_kwh, grundlast_kw, ist_individuell).
"""

from __future__ import annotations

from backend.api.routes.live_wetter import _berechne_verbrauchsprofil


def _stunde(zeit, *, gti=None, ghi=None, temp=None):
    s = {"zeit": zeit}
    if gti is not None:
        s["gti_wm2"] = gti
    if ghi is not None:
        s["globalstrahlung_wm2"] = ghi
    if temp is not None:
        s["temperatur_c"] = temp
    return s


def _pv_at(profil, zeit):
    return next(p["pv_ertrag_kw"] for p in profil if p["zeit"] == zeit)


def _verbrauch_at(profil, zeit):
    return next(p["verbrauch_kw"] for p in profil if p["zeit"] == zeit)


# ---------------------------------------------------------------------------
# PV-Ertrag
# ---------------------------------------------------------------------------

def test_pv_gti_basis_ohne_temperaturkorrektur():
    """GTI × kWp × (1−0,14)/1000, Modultemp ≤ 25 °C → keine Korrektur.
    400 W/m² × 10 kWp × 0,86 / 1000 = 3,44 kW."""
    profil, pv_kwh, _, ist_ind = _berechne_verbrauchsprofil(
        [_stunde("12:00", gti=400, temp=5)], kwp=10.0
    )
    assert _pv_at(profil, "12:00") == 3.44
    assert pv_kwh == 3.4  # round(3.44, 1)
    assert ist_ind is False


def test_pv_temperaturkorrektur_ueber_25_grad():
    """1000 W/m², Lufttemp 15 °C → Aufheizung 25 → Modultemp 40 °C.
    pv = 8,6 × (1 − 15×0,004) = 8,6 × 0,94 = 8,084 → 8,08."""
    profil, _, _, _ = _berechne_verbrauchsprofil(
        [_stunde("12:00", gti=1000, temp=15)], kwp=10.0
    )
    assert _pv_at(profil, "12:00") == 8.08


def test_pv_ghi_fallback_wenn_kein_gti():
    """Ohne gti_wm2 wird globalstrahlung_wm2 genutzt (gleiche Formel)."""
    profil, _, _, _ = _berechne_verbrauchsprofil(
        [_stunde("12:00", ghi=400, temp=5)], kwp=10.0
    )
    assert _pv_at(profil, "12:00") == 3.44


def test_pv_null_bei_keiner_strahlung_oder_kwp():
    profil, pv_kwh, _, _ = _berechne_verbrauchsprofil(
        [_stunde("03:00", gti=0, temp=5)], kwp=10.0
    )
    assert _pv_at(profil, "03:00") == 0.0
    assert pv_kwh is None  # pv_summe == 0 → None


# ---------------------------------------------------------------------------
# Verbrauch: BDEW-Fallback vs. individuelles Profil
# ---------------------------------------------------------------------------

def test_bdew_fallback_mit_jahresverbrauch_skalierung():
    """Kein individuelles Profil → BDEW H0 × tages_faktor (jahr/4000).
    8000 → Faktor 2: Stunde 12 = 0,50×2 = 1,0; Nachtstunde 3 = 0,3×2 = 0,6."""
    profil, _, _, ist_ind = _berechne_verbrauchsprofil(
        [_stunde("12:00", gti=0), _stunde("03:00", gti=0)],
        kwp=10.0, jahresverbrauch_kwh=8000,
    )
    assert _verbrauch_at(profil, "12:00") == 1.0
    assert _verbrauch_at(profil, "03:00") == 0.6
    assert ist_ind is False


def test_individuelles_profil_int_und_fehlende_stunde():
    """Individuelles Profil: vorhandene Stunde exakt, fehlende → Default 0,3."""
    profil, _, _, ist_ind = _berechne_verbrauchsprofil(
        [_stunde("12:00", gti=0), _stunde("13:00", gti=0)],
        kwp=10.0, individuelles_profil={12: 1.5},
    )
    assert _verbrauch_at(profil, "12:00") == 1.5
    assert _verbrauch_at(profil, "13:00") == 0.3
    assert ist_ind is True


# ---------------------------------------------------------------------------
# WP-Temperaturkorrektur (Heizgradtage)
# ---------------------------------------------------------------------------

def test_wp_hdd_proportional():
    """Referenz 5 °C, Forecast 0 °C: hdd_ref=10, hdd_fc=15 → Faktor 1,5.
    Haus 0,6 + WP 0,4×1,5 = 1,2."""
    profil, _, _, _ = _berechne_verbrauchsprofil(
        [_stunde("12:00", gti=0, temp=0)], kwp=10.0,
        individuelles_profil={12: 1.0}, wp_profil={12: 0.4}, referenz_temp_c=5.0,
    )
    assert _verbrauch_at(profil, "12:00") == 1.2


def test_wp_milde_referenz_zuschlag_geclamped():
    """Milde Referenz (14,5 °C → hdd_ref=0,5 < 1): Zuschlag 1 + 15×0,15 = 3,25,
    geclamped auf 3,0. Haus 0,6 + WP 0,4×3,0 = 1,8."""
    profil, _, _, _ = _berechne_verbrauchsprofil(
        [_stunde("12:00", gti=0, temp=0)], kwp=10.0,
        individuelles_profil={12: 1.0}, wp_profil={12: 0.4}, referenz_temp_c=14.5,
    )
    assert _verbrauch_at(profil, "12:00") == 1.8


# ---------------------------------------------------------------------------
# Grundlast: Median der Nachtstunden (0-5 Uhr, verbrauch > 0)
# ---------------------------------------------------------------------------

def test_grundlast_median_der_nachtstunden():
    """5 Nachtstunden mit verbrauch [0,2 … 0,6] → Median (ungerade) = 0,4."""
    profil_in = {0: 0.2, 1: 0.3, 2: 0.4, 3: 0.5, 4: 0.6}
    _, _, grundlast, _ = _berechne_verbrauchsprofil(
        [_stunde(f"{h:02d}:00", gti=0) for h in range(5)],
        kwp=10.0, individuelles_profil=profil_in,
    )
    assert grundlast == 0.4


def test_grundlast_none_ohne_nachtwerte():
    """Nur Tagesstunden → keine Nacht-Grundlast."""
    _, _, grundlast, _ = _berechne_verbrauchsprofil(
        [_stunde("12:00", gti=400, temp=5)], kwp=10.0,
        individuelles_profil={12: 1.0},
    )
    assert grundlast is None
