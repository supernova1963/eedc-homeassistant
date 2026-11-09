"""Päckchen CC1 — Layer der Nachführung «Rest heute» (`core/berechnungen/prognose_nachfuehrung.py`).

Geprüft: der Faktor ``f = clip(1 + (r − 1)·√w, 0,4, 1,6)`` an den Beispielen des Auftrags, Monotonie in r, Klemme
beidseitig, die drei Schwellen (kein IST, SOLL bisher < 1 kWh, w < 10 %), ``soll_bisher_kwh`` mit der N-544-Regel
(inklusive) bitgleich zur früheren Inline-Summe der Abweichungs-Ampel (``anlage_steuerung._abweichungs_ampel``), der
gerundete Rest — und ein Tag aus der Mess-Referenz (31.10.2026, Nebeltag).

⚠ Die Verdrahtung im Kanon (``prognose_kanon._prognose_mit_heute``) ist in diesem Päckchen **angehalten**
(Ausrichtungs-Probe: an einem Kanal-Tag liegt das IST im Beginn-Raster, das Prognose-Profil im Backward-Raster — Halt
H-CC1 im Bericht); die Kanon-Fälle des Auftrags folgen mit dem Entscheid.

Schwestern: ``test_prognose_korrektur_nutzen.py`` (Wächter derselben Prognose), ``test_prognose_kanon.py`` (Rest heute,
``rest_aus_slots``), ``test_n544_fenster_achse_backward.py`` (IST-Grenze der Abweichungs-Ampel).
"""

from __future__ import annotations

import math

import pytest

from backend.core.berechnungen.prognose_nachfuehrung import (
    NACHFUEHR_KLEMME,
    NACHFUEHR_MIN_ANTEIL,
    NACHFUEHR_MIN_SOLL_KWH,
    nachfuehr_faktor,
    rest_nachgefuehrt_kwh,
    soll_bisher_kwh,
)


def _f(r: float, w: float, soll_tag: float = 40.0) -> float:
    """Faktor aus r und w über die echten Eingänge (SOLL bisher = w × SOLL Tag, IST = r × SOLL bisher)."""
    soll_bisher = w * soll_tag
    return nachfuehr_faktor(r * soll_bisher, soll_bisher, soll_tag)


@pytest.mark.parametrize("r, w, erwartet", [
    (0.5, 0.3, 0.726),     # 1 − 0,5 · √0,3
    (1.4, 0.5, 1.283),     # 1 + 0,4 · √0,5
    (0.2, 0.9, 0.4),       # 0,241 → untere Klemme
    (1.0, 0.7, 1.0),       # der Tag trifft ⇒ kein Faktor
])
def test_beispiele_des_auftrags(r, w, erwartet):
    assert _f(r, w) == pytest.approx(erwartet, abs=5e-4)


def test_unterhalb_der_schwellen_kein_faktor():
    assert nachfuehr_faktor(None, 5.0, 40.0) == 1.0, "ohne IST-Messung"
    assert nachfuehr_faktor(0.2, 0.8, 40.0) == 1.0, "SOLL bisher 0,8 kWh < 1 kWh"
    assert nachfuehr_faktor(0.5, 2.0, 40.0) == 1.0, "w = 0,05 < 10 %"
    assert nachfuehr_faktor(3.0, 5.0, 0.0) == 1.0, "SOLL Tag 0"
    assert nachfuehr_faktor(3.0, None, 40.0) == 1.0, "ohne Profil kein SOLL"
    assert NACHFUEHR_MIN_SOLL_KWH == 1.0 and NACHFUEHR_MIN_ANTEIL == 0.10 and NACHFUEHR_KLEMME == (0.4, 1.6)


def test_gemessene_null_ist_ein_wert_und_landet_an_der_klemme():
    assert nachfuehr_faktor(0.0, 30.0, 40.0) == 0.4


def test_klemme_oben():
    assert _f(5.0, 0.9) == 1.6


def test_monoton_in_r():
    werte = [_f(r / 10, 0.4) for r in range(0, 40)]
    assert all(a <= b for a, b in zip(werte, werte[1:]))


def test_daempfung_waechst_mit_dem_tagesanteil():
    """Derselbe Vormittag (r = 0,6) wirkt am Morgen schwächer als am Nachmittag."""
    assert _f(0.6, 0.15) > _f(0.6, 0.5) > _f(0.6, 0.85)


@pytest.mark.parametrize("profil", [
    [0.0] * 8 + [0.15, 1.29, 3.87, 5.73, 7.53, 8.0, 6.82, 6.33, 3.69, 1.04] + [0.0] * 6,   # 5.11.2026 Winterborn
    [None, 0.0, 0.1] + [0.333] * 18 + [None, 0.2, 0.0],                                    # Lücken
    [0.123456789 * (h % 7) for h in range(24)],                                             # krumme Zahlen
])
def test_soll_bisher_bitgleich_zur_frueheren_ampel_summe(profil):
    """Die Ampel summierte bis 9.11.2026 inline ``Σ float(v or 0) for v in profil[:bis_slot + 1]`` — dieselbe Zahl."""
    for bis_slot in range(-1, 24):
        alt = sum(float(v or 0.0) for v in profil[: max(0, bis_slot + 1)])
        assert soll_bisher_kwh(profil, bis_slot) == alt


def test_soll_bisher_ohne_grenze_oder_profil():
    assert soll_bisher_kwh([1.0] * 24, None) is None
    assert soll_bisher_kwh([], 10) is None
    assert soll_bisher_kwh(None, 10) is None


def test_rest_wird_skaliert_und_gerundet():
    assert rest_nachgefuehrt_kwh(18.44, 0.77) == 14.2
    assert rest_nachgefuehrt_kwh(None, 0.77) is None
    assert rest_nachgefuehrt_kwh(10.0, 1.0) == 10.0


def test_messreferenz_31_10_2026_um_11_uhr():
    """Nebeltag aus der Mess-Referenz (``refactoring-werkzeug/nachfuehrung-backtest-2026-11-09/``).

    Prognose: Attribut ``stundenprofil_kwh`` des Sensors «PV-Prognose heute» (HA-History 31.10.2026 11:00, Backward-Slot
    h = [h−1, h)): Slots 8…17 = 0,26 · 1,54 · 4,43 · 3,81 · 6,22 · 5,94 · 3,17 · 1,85 · 0,87 · 0,39, Σ 28,48.
    IST (``ist_stunden.json``, Beginn-Raster): bis 11:00 0,105 + 1,919 + 2,591 + 1,537 = 6,152 kWh, Tag 12,0 kWh.
    Beide Summen an derselben Uhrzeit (11:00): SOLL bisher = Slots ≤ 11 = 10,04 kWh, Rest-Modell = Slots 12…17 = 18,44.
    ⇒ r = 0,613, w = 0,353, **f = 0,770**, Rest nachgeführt **14,2 kWh** (Modell 18,44), Tagesendwert 20,4 statt 24,6 kWh
    (IST 12,0: +70 % statt +105 %).
    """
    slots = [0.0] * 8 + [0.26, 1.54, 4.43, 3.81, 6.22, 5.94, 3.17, 1.85, 0.87, 0.39] + [0.0] * 6
    ist_bisher = 0.105 + 1.919 + 2.591 + 1.537
    soll_bisher = soll_bisher_kwh(slots, 11)
    assert soll_bisher == pytest.approx(10.04)
    f = nachfuehr_faktor(ist_bisher, soll_bisher, sum(slots))
    assert f == pytest.approx(1 + (ist_bisher / 10.04 - 1) * math.sqrt(10.04 / 28.48))
    assert round(f, 3) == 0.770
    rest_modell = sum(slots[12:])
    assert rest_nachgefuehrt_kwh(rest_modell, f) == 14.2
    assert round(ist_bisher + 14.2, 1) == 20.4
