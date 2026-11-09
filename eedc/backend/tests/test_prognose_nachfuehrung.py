"""Päckchen CC1 — Layer der Nachführung «Rest heute» (`core/berechnungen/prognose_nachfuehrung.py`).

Geprüft: der Faktor ``f = clip(1 + (r − 1)·√w, 0,4, 1,6)`` an den Beispielen des Auftrags, Monotonie in r, Klemme
beidseitig, die drei Schwellen (kein IST, SOLL bisher < 1 kWh, w < 10 %), ``soll_bisher_kwh`` mit der N-544-Regel
(inklusive) bitgleich zur früheren Inline-Summe der Abweichungs-Ampel (``anlage_steuerung._abweichungs_ampel``), der
gerundete Rest — und ein Tag aus der Mess-Referenz (31.10.2026, Nebeltag).

Verdrahtung im Kanon (``prognose_kanon._prognose_mit_heute`` → ``_nachfuehrung``, Nachlauf CC nach N-784): Tag mit Profil
und IST ⇒ Faktor, Rest = Modell × f, rollend = IST + Rest; ohne IST ⇒ f 1,0 und Rest = Modell; der Fixture-Tag 31.10.2026
als Mischzeilen eines Kanal-Tags (Beginn-Raster) — nach N-784 auf dem Backward-Slot, die Grenze ist Slot 11 (11:00).

Schwestern: ``test_prognose_korrektur_nutzen.py`` (Wächter derselben Prognose), ``test_prognose_kanon.py`` (Rest heute,
``rest_aus_slots``), ``test_n544_fenster_achse_backward.py`` (IST-Grenze der Abweichungs-Ampel).
"""

from __future__ import annotations

import math
from datetime import date, datetime
from types import SimpleNamespace

import pytest

from backend.core.berechnungen.prognose_nachfuehrung import (
    NACHFUEHR_KLEMME,
    NACHFUEHR_MIN_ANTEIL,
    NACHFUEHR_MIN_SOLL_KWH,
    nachfuehr_faktor,
    nachfuehr_prozent,
    rest_nachgefuehrt_kwh,
    slots_nachgefuehrt,
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


def test_nachfuehr_prozent_erst_ab_fuenf_prozent():
    assert nachfuehr_prozent(None) is None
    assert nachfuehr_prozent(1.0) is None
    assert nachfuehr_prozent(1.049) is None and nachfuehr_prozent(0.951) is None
    assert nachfuehr_prozent(0.770) == -23
    assert nachfuehr_prozent(1.18) == 18


# ── Kanon (`prognose_kanon._prognose_mit_heute` → `_nachfuehrung`) ──────────

SLOTS_31_10 = [0.0] * 8 + [0.26, 1.54, 4.43, 3.81, 6.22, 5.94, 3.17, 1.85, 0.87, 0.39] + [0.0] * 6
#: IST 31.10.2026 (Beginn-Raster, Kanal-Tag): Stunden 7…10 = [7, 8) … [10, 11).
IST_31_10 = {7: 0.105, 8: 1.919, 9: 2.591, 10: 1.537}
TAG_31_10 = date(2026, 10, 31)


async def _kanon_heute(monkeypatch, zeilen, slots, jetzt: datetime):
    """``_prognose_mit_heute`` mit gestellten IST-Zeilen, gestelltem Profil und fester Uhr."""
    import backend.services.prognose_kanon as pk
    from backend.services.energie_profil import kanal_stunden as ks

    async def fake_stunden(db, anlage_id, von, bis, *, felder=None):
        return zeilen

    class _Uhr(datetime):
        @classmethod
        def now(cls, tz=None):
            return jetzt.replace(tzinfo=tz)

    monkeypatch.setattr(ks, "stunden_der_tage", fake_stunden)
    monkeypatch.setattr(pk, "datetime", _Uhr)
    tag = SimpleNamespace(profil=SimpleNamespace(stunden_kwh=list(slots)))
    return await pk._prognose_mit_heute(None, SimpleNamespace(id=1), jetzt.date(), [tag], 1.0)


async def test_kanon_messreferenz_31_10_als_kanal_tag(monkeypatch):
    """31.10.2026 11:00, Mischzeilen 0…10 (Beginn) ⇒ Grenze Slot 11, SOLL bisher 10,04, f 0,770, Rest 18,4 → 14,2,
    rollend 6,2 + 14,2 = 20,4 (statt 24,6 ohne Nachführung)."""
    zeilen = [SimpleNamespace(datum=TAG_31_10, stunde=h, pv_kw=IST_31_10.get(h, 0.0), raster="beginn", spannen=None)
              for h in range(11)]
    k = await _kanon_heute(monkeypatch, zeilen, SLOTS_31_10, datetime(2026, 10, 31, 11, 0))
    assert k.ist_bisher_bis_slot == 11
    assert k.soll_bisher_kwh == pytest.approx(10.04)
    assert k.nachfuehr_faktor == 0.770
    assert k.rest_modell_kwh == 18.4
    assert k.rest_heute_kwh == 14.2
    assert k.ist_bisher_kwh == 6.2 and k.heute_rollend_kwh == 20.4


async def test_kanon_profil_und_ist_bis_slot_10(monkeypatch):
    """Bestandstag, IST bis Slot 10 (je 1,0 kWh in Slot 6…10 = 5,0 kWh gegen SOLL 2,5): r 2, w = 2,5/20 ⇒ f > 1."""
    slots = [0.0] * 6 + [0.5] * 5 + [1.5] * 10 + [0.0] * 3   # Σ 2,5 + 15 = 17,5
    zeilen = [SimpleNamespace(datum=date(2026, 6, 1), stunde=h, pv_kw=1.0 if 6 <= h <= 10 else 0.0, spannen=None)
              for h in range(11)]
    k = await _kanon_heute(monkeypatch, zeilen, slots, datetime(2026, 6, 1, 10, 30))
    f = nachfuehr_faktor(5.0, 2.5, 17.5)
    assert k.ist_bisher_bis_slot == 10 and k.soll_bisher_kwh == 2.5
    assert k.nachfuehr_faktor == round(f, 3) and f == pytest.approx(1 + 1.0 * math.sqrt(2.5 / 17.5))
    assert k.rest_modell_kwh == round(0.5 * 1.5 + 1.5 * 9, 1)
    assert k.rest_heute_kwh == round(k.rest_modell_kwh * f, 1)
    assert k.heute_rollend_kwh == round(5.0 + k.rest_heute_kwh, 1)


async def test_kanon_ohne_ist_bleibt_das_modell(monkeypatch):
    slots = [0.0] * 6 + [0.5] * 5 + [1.5] * 10 + [0.0] * 3
    k = await _kanon_heute(monkeypatch, [], slots, datetime(2026, 6, 1, 10, 30))
    assert k.ist_bisher_bis_slot is None and k.soll_bisher_kwh is None
    assert k.nachfuehr_faktor == 1.0
    assert k.rest_heute_kwh == k.rest_modell_kwh
    assert k.heute_rollend_kwh == k.rest_heute_kwh


async def test_kanon_ohne_profil_kein_faktor(monkeypatch):
    import backend.services.prognose_kanon as pk
    from backend.services.energie_profil import kanal_stunden as ks

    async def fake_stunden(*_a, **_k):
        return []

    monkeypatch.setattr(ks, "stunden_der_tage", fake_stunden)
    k = await pk._prognose_mit_heute(None, SimpleNamespace(id=1), date(2026, 6, 1), [SimpleNamespace(profil=None)], 1.0)
    assert k.nachfuehr_faktor is None and k.rest_modell_kwh is None and k.rest_heute_kwh is None



# ── HA-Attribute an «Rest heute» und «heute (nachgeführt)» ──────────────────


def test_ha_attribute_nachfuehrung():
    from backend.api.routes.ha_export.anlage_sensorwerte import _prognose_sensorwert
    from backend.services.ha_sensors_export import PROGNOSE_SENSOREN

    je_key = {s.key: s for s in PROGNOSE_SENSOREN}
    prognose = {"rest_today_kwh": 14.2, "heute_rollend_kwh": 20.4, "nachfuehr_faktor": 0.77, "rest_modell_kwh": 18.4}
    wert, attr = _prognose_sensorwert(je_key["eedc_prognose_rest_today_kwh"], prognose)
    assert wert == 14.2 and attr == {"nachfuehr_faktor": 0.77, "rest_modell_kwh": 18.4}
    wert, attr = _prognose_sensorwert(je_key["eedc_prognose_heute_rollend_kwh"], prognose)
    assert wert == 20.4 and attr == {"nachfuehr_faktor": 0.77}
    # Ohne Profil (Kanon ohne Faktor) keine Attribute.
    _, attr = _prognose_sensorwert(je_key["eedc_prognose_rest_today_kwh"], {"rest_today_kwh": 0.0, "nachfuehr_faktor": None})
    assert attr == {}
    assert "Nachführ-Faktor" in je_key["eedc_prognose_rest_today_kwh"].formel
    assert "Nachführ-Faktor" in je_key["eedc_prognose_heute_rollend_kwh"].formel


# ── Live-Antwort: die Felder gelten dem eedc-Rest ───────────────────────────


@pytest.mark.parametrize("ist_eedc, erwartet", [(True, 0.77), (False, None)], ids=["eedc", "solcast"])
def test_live_nachfuehr_felder_nur_beim_eedc_rest(ist_eedc, erwartet):
    from backend.api.routes.live_wetter_antwort import _PrognoseZahlen, _QuellenStand, _rest_der_quelle

    zahlen = _PrognoseZahlen(None, 24.6, 14.2, 20.4, 6.2, nachfuehr_faktor=0.77, rest_modell=18.4, soll_bisher=10.04)
    stand = _QuellenStand(quelle_tagesprofile=[[0.0] * 12 + [2.0] * 6 + [0.0] * 6])
    pq = SimpleNamespace(ist_eedc=ist_eedc)
    _rest_der_quelle(pq, stand, zahlen, datetime(2026, 10, 31, 11, 0))
    assert zahlen.nachfuehr_faktor == erwartet
    assert (zahlen.rest_modell, zahlen.soll_bisher) == ((18.4, 10.04) if ist_eedc else (None, None))
    assert zahlen.rest == (14.2 if ist_eedc else 12.0), "eine fremde Quelle bildet ihren eigenen Rest"


# ── «Speicher voll um» folgt dem nachgeführten Rest (H-N2, Entscheid Master) ──


def test_slots_nachgefuehrt_faktor_eins_bitgleich():
    slots = [0.0] * 8 + [0.26, 1.54, 4.43, 3.81, 6.22, 5.94, 3.17, 1.85, 0.87, 0.39] + [0.0] * 6
    assert slots_nachgefuehrt(slots, 1.0, 11) == slots
    assert slots_nachgefuehrt(slots, None, 11) == slots
    assert slots_nachgefuehrt(slots, 0.77, None) == slots
    assert slots_nachgefuehrt(None, 0.77, 11) is None


def test_slots_nachgefuehrt_skaliert_nur_ab_dem_startslot():
    slots = [1.0] * 24
    neu = slots_nachgefuehrt(slots, 0.77, 12)
    assert neu[:12] == [1.0] * 12
    assert neu[12:] == [0.77] * 12


def test_slots_nachgefuehrt_none_slot_bleibt_none():
    slots = [None, 2.0, None, 4.0]
    assert slots_nachgefuehrt(slots, 0.5, 1) == [None, 1.0, None, 2.0]


async def test_speicher_simulation_bekommt_die_nachgefuehrten_slots(monkeypatch):
    """Export: «Speicher voll um» simuliert ab `sim_start` mit Slots × Faktor; `stundenprofil_heute` bleibt das Modell."""
    import backend.core.berechnungen.speicher_simulation as sim_mod
    import backend.services.ha_export_prognose as hep
    import backend.services.prognose_kanon as pk
    import backend.services.verbrauch_prognose_service as vps

    slots = [0.0] * 6 + [2.0] * 12 + [0.0] * 6
    tag = SimpleNamespace(profil=SimpleNamespace(stunden_kwh=list(slots), stundenprofil_export_kwh=list(slots)),
                          eedc_kwh=24.0, abregelung_om_kwh=None)
    kanon = SimpleNamespace(tage=[tag], rest_heute_kwh=10.0, heute_rollend_kwh=20.0, ist_bisher_kwh=10.0,
                            ist_bisher_bis_slot=11, nachfuehr_faktor=0.77, rest_modell_kwh=13.0)
    gesehen: dict = {}

    async def fake_kanon(*_a, **_k):
        return kanon

    async def fake_speicher(*_a, **_k):
        return 10.0, 90.0, 50.0, date(2026, 10, 31), 11

    async def fake_vp(*_a, **_k):
        return None

    def fake_sim(**kw):
        gesehen.update(kw)
        return SimpleNamespace(speicher_voll_um=None, soc_pro_stunde={}, end_soc_prozent=50.0, speicher_leer_um=None)

    monkeypatch.setattr(pk, "kanon_tagesprognose", fake_kanon)
    monkeypatch.setattr(hep, "_aktueller_speicher", fake_speicher)
    monkeypatch.setattr(hep, "_sim_start", lambda *_a: (12, 0.5))
    monkeypatch.setattr(vps, "get_verbrauch_prognose", fake_vp)
    monkeypatch.setattr(sim_mod, "simuliere_speicher_tag", fake_sim)
    try:
        await hep.berechne_prognose_export(None, SimpleNamespace(id=1, longitude=None, latitude=None))
    except Exception:  # noqa: BLE001 — nach der Simulation darf der Rest des Exports an den Platzhaltern scheitern
        pass
    assert gesehen, "die Simulation lief nicht"
    assert gesehen["pv_stunden"][:12] == slots[:12]
    assert gesehen["pv_stunden"][12:18] == [pytest.approx(1.54)] * 6
    assert tag.profil.stunden_kwh == slots, "das Modellprofil bleibt unverändert"

