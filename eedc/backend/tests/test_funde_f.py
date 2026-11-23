"""Fund-Päckchen F (23.11.2026, Entscheide Gernot 22./23.11.2026) — die Proben der drei Rechenregeln.

* **F1 (N-817):** eine Lücke zwischen zwei Zählerständen wird nicht mehr linear gefüllt — die Stunden ohne Stand bleiben leer,
  die erste Stunde danach trägt die Menge (wie HA). Schreibweg ``snapshot_tagestabelle`` (Probe in
  ``test_zaehlerluecken_snapshot.py::test_n817_…``) und Stundenform ``stunden_leser.lade_stundenformen`` (hier).
* **F2:** an Tagen ohne Stundenwerte gilt «je Feld die zugeordnete Quelle» auch für ein Feld allein über MQTT neben HA-Feldern
  (``lts_aggregator.lts_tagestabelle`` mit ``db``, ``mischform_kwargs``); reine HA-Anlagen bitgleich.
* **F3:** ein Verbraucher-Schlüssel (Wallbox, E-Auto, Wärmepumpe) trägt in der einen Mischung ``komponenten_der_tage`` über die
  Tage EINE Schreibweise (Betrag); Batterie, Sonstiges und ``haushalt`` bleiben.

Messungen: ``~/.claude/plans/golden-master/funde-f-2026-11-23/`` (MQTT-Welt mit Lücke, gemischte Welt, Lab-Kopie).
Schwesterdateien: ``test_zaehlerluecken_snapshot.py``, ``test_zaehlerluecken_lts_tabelle.py``, ``test_funde_d.py``.
"""
from __future__ import annotations

from datetime import date, timedelta
from types import SimpleNamespace

import pytest

from backend.models import Anlage, Investition  # noqa: F401  (Base.metadata)
from backend.models.mqtt_energy_snapshot import MqttEnergySnapshot
from backend.tests.test_zaehlerluecken_snapshot import (
    DATUM, INVS, T0, _lts_svc, _ohne_ha, _snapshot_db, _staende,
)


# ── F1: Stundenform je Zähler (Wärme-Verlauf) — Bündel statt Gerade ────────────────────────────────────────────────


async def test_f1_stundenform_buendel_in_der_stunde_nach_der_luecke(db):
    from backend.services.snapshot.stunden_leser import lade_stundenformen

    key = "inv:2:stromverbrauch_kwh"
    reihe = _staende(T0 - timedelta(hours=1), T0 + timedelta(hours=23), 500.0, 0.8,
                     ohne={T0 + timedelta(hours=h) for h in (9, 10, 11, 12)})
    await _snapshot_db(db, {key: reihe})
    anlage = SimpleNamespace(id=1, sensor_mapping={})
    with _ohne_ha():
        form = (await lade_stundenformen(db, anlage, DATUM, [(key, None)]))[key]
    assert form[9:13] == [None, None, None, None]                 # die Stunden ohne Stand bleiben leer
    assert form[13] == pytest.approx(4.0)                         # 08:00 → 13:00: fünf Stunden à 0,8 in der Stunde danach
    assert all(form[h] == pytest.approx(0.8) for h in range(24) if not 9 <= h <= 13)
    assert sum(v for v in form if v is not None) == pytest.approx(19.2)    # Σ Stunden = Tageswert (unverändert)


async def test_f1_stundenform_rand_bleibt_ohne_anker_leer(db):
    """Fehlt der Stand am Fensterbeginn und davor, wird nicht extrapoliert (wie bisher): die ersten Slots bleiben leer."""
    from backend.services.snapshot.stunden_leser import lade_stundenformen

    key = "inv:2:stromverbrauch_kwh"
    await _snapshot_db(db, {key: _staende(T0 + timedelta(hours=3), T0 + timedelta(hours=23), 500.0, 1.0)})
    with _ohne_ha():
        form = (await lade_stundenformen(db, SimpleNamespace(id=1, sensor_mapping={}), DATUM, [(key, None)]))[key]
    assert form[:4] == [None, None, None, None] and form[4] == pytest.approx(1.0)


# ── F2: MQTT-Feld neben HA-Feldern an Tagen ohne Stundenwerte ───────────────────────────────────────────────────────

_PV = {"strategie": "sensor", "sensor_id": "sensor.pv"}
MISCH = SimpleNamespace(id=1, anlagenname="F2", leistung_kwp=10.0,
                        sensor_mapping={"basis": {}, "investitionen": {"3": {"felder": {"pv_erzeugung_kwh": _PV}}}})


async def _mqtt_netz(db, reihe):
    """Netzbezug allein über MQTT: Stände in ``sensor_snapshots`` und ein angekommener MQTT-Stand (``mqtt_zaehler_keys``)."""
    await _snapshot_db(db, {"basis:netzbezug": reihe})
    db.add(MqttEnergySnapshot(anlage_id=1, timestamp=reihe[0][0], energy_key="netzbezug_kwh", value_kwh=reihe[0][1]))
    await db.commit()


async def _tabelle(sitzung, **kw):
    from unittest.mock import patch

    from backend.services.snapshot.lts_aggregator import lts_tagestabelle

    svc = _lts_svc({"sensor.pv": _staende(T0 - timedelta(hours=1), T0 + timedelta(hours=23), 500.0, 0.5)})
    with patch("backend.services.snapshot.lts_aggregator.get_ha_statistics_service", return_value=svc), _ohne_ha():
        return await lts_tagestabelle(MISCH, INVS, DATUM, **kw)


async def test_f2_mqtt_feld_neben_ha_feldern_aus_seinen_staenden(db):
    from backend.services.snapshot.lts_aggregator import mischform_kwargs

    await _mqtt_netz(db, _staende(T0 - timedelta(hours=1), T0 + timedelta(hours=23), 100.0, 0.5,
                                  ohne={T0 + timedelta(hours=h) for h in (5, 6)}))
    ohne = await _tabelle(db)
    assert "netzbezug" not in ohne.komponenten_kwh                # die HA-Sicht (Tag-Status, Drift) ohne db wie bisher
    assert await mischform_kwargs(db, 1) == {"db": db}
    mit = await _tabelle(db, **await mischform_kwargs(db, 1))
    assert mit.komponenten_kwh["netzbezug"] == pytest.approx(12.0)    # Quelle je Feld: das MQTT-Feld aus seinen Ständen
    assert mit.komponenten_kwh["pv_3"] == pytest.approx(ohne.komponenten_kwh["pv_3"]) == pytest.approx(12.0)
    assert mit.stunden[5]["netzbezug"] is None and mit.stunden[7]["netzbezug"] == pytest.approx(1.5)   # Bündel (N-817)
    assert mit.stunden[7]["spannen"] == {"netzbezug": 3}


async def test_f2_mqtt_feld_ohne_zwei_staende_bleibt_leer(db):
    await _mqtt_netz(db, [(T0 + timedelta(hours=12), 100.0)])
    from backend.services.snapshot.lts_aggregator import mischform_kwargs

    mit = await _tabelle(db, **await mischform_kwargs(db, 1))
    assert "netzbezug" not in mit.komponenten_kwh                 # nichts geschätzt: ohne zwei Stände «—»
    assert mit.komponenten_kwh["pv_3"] == pytest.approx(12.0)


async def test_f2_reine_ha_anlage_ruft_wie_bisher(db):
    from backend.services.snapshot.lts_aggregator import mischform_kwargs

    assert await mischform_kwargs(db, 1) == {}                    # keine MQTT-Stände ⇒ Aufruf wörtlich der alte
    assert (await _tabelle(db)).komponenten_kwh == {"pv_3": pytest.approx(12.0)}


# ── F3: eine Schreibweise je Verbraucher-Schlüssel über die Tage ────────────────────────────────────────────────────


def test_f3_verbraucher_als_betrag_regel():
    from backend.core.berechnungen.energie import verbraucher_als_betrag

    roh = {"wallbox_4": -20.2, "eauto_5": -3.0, "waermepumpe_40": -9.9, "waermepumpe_40_heizen": -4.0,
           "batterie_3": -1.5, "sonstige_7": -2.0, "haushalt": -5.0, "pv_2": 12.0, "netzbezug": 3.0, "wallbox_9": None}
    assert verbraucher_als_betrag(roh) == {**roh, "wallbox_4": 20.2, "eauto_5": 3.0, "waermepumpe_40": 9.9,
                                           "waermepumpe_40_heizen": 4.0}
    assert verbraucher_als_betrag(None) is None and verbraucher_als_betrag({}) == {}


async def test_f3_monatssumme_rechnet_tage_nicht_gegeneinander(db):
    """Lab Winterborn November 2026 im Kleinen: ein Wallbox-Tag aus der Live-Σ (negativ), einer aus dem Zähler (positiv)."""
    from backend.api.routes.energie_profil.monat import _komponenten_summen
    from backend.services.energie_profil.kanal_stunden import komponenten_der_tage

    tage = {date(2026, 11, 10): {"wallbox_4": -20.21, "batterie_3": -1.0, "waermepumpe_40": -9.97},
            date(2026, 11, 16): {"wallbox_4": 20.02, "batterie_3": 2.0, "waermepumpe_39": 5.0}}
    gemischt = await komponenten_der_tage(db, 1, date(2026, 11, 10), date(2026, 11, 16), tage)
    assert gemischt[date(2026, 11, 10)] == {"wallbox_4": 20.21, "batterie_3": -1.0, "waermepumpe_40": 9.97}
    assert tage[date(2026, 11, 10)]["wallbox_4"] == -20.21        # die gespeicherte Zeile bleibt
    zeilen = [SimpleNamespace(datum=d, komponenten_kwh=k) for d, k in tage.items()]
    summen = await _komponenten_summen(db, 1, date(2026, 11, 10), date(2026, 11, 16), zeilen)
    assert summen["wallbox_4"] == pytest.approx(40.23) and summen["batterie_3"] == pytest.approx(1.0)
    assert summen["waermepumpe_40"] + summen["waermepumpe_39"] == pytest.approx(14.97)


# ── F6: Counter-Stunden (Starts, Betriebsstunden) ohne Reskalierung ─────────────────────────────────────────────────

_WP = {"investitionen": {"2": {"felder": {"wp_starts_anzahl": {"strategie": "sensor", "sensor_id": "sensor.wp_starts"}}}}}
_TAG6 = date(2026, 10, 28)
_T6 = T0.replace(year=2026, month=10, day=28)


def _wp_inv():
    from backend.tests.test_zaehlerluecken_snapshot import _inv

    return {"2": _inv(2, "waermepumpe")}


def _stand6(lage: str, t) -> float:
    if lage == "nacht_23":
        return 100.0 + (5.0 if t >= _T6 else 0.0)            # 5 Starts zwischen 27.10. 23:00 und 28.10. 00:00
    return 100.0 + (t - (_T6 - timedelta(days=1))).total_seconds() / 3600


@pytest.mark.parametrize("lage,stunden,tageswert,fenster", [
    ("gleichmaessig", [1] * 24, 24, 24.0),
    ("nacht_23", [5] + [0] * 23, 0, 5.0),
    ("luecke", [1] * 9 + [None] * 4 + [5] + [1] * 10, 24, 24.0),
], ids=["gleichmaessig", "nacht_23", "luecke"])
async def test_f6_counter_stunden_ohne_reskalierung(db, lage, stunden, tageswert, fenster):
    """Welt der Messung (``golden-master/funde-f-2026-11-23/test_mess_f6_counter_welt.py``). Am HEAD ``ab7764ac5``
    reskalierte ``aggregate_day`` die Stunden auf den Tageswert: nacht_23 ⇒ alle 0 (die 5 Starts verschwanden aus den
    Stunden), luecke ⇒ 2,2,2,2,2 in den Stunden 0–4. Jetzt: die Stunden tragen die Stände (Lücke ⇒ Bündel in der
    Stunde 13), der Tageswert bleibt der Kalendertag, die Invariante prüft gegen die Menge im Fenster der Stunden."""
    from backend.core.berechnungen import pruefe_counter_konsistent
    from backend.models.sensor_snapshot import SensorSnapshot
    from backend.services.snapshot.aggregator import get_daily_counter_deltas_by_inv, get_hourly_counter_sum_by_feld

    t = _T6 - timedelta(days=1)
    while t <= _T6 + timedelta(days=1, hours=1):
        if not (lage == "luecke" and t.date() == _TAG6 and 9 <= t.hour <= 12):
            db.add(SensorSnapshot(anlage_id=1, sensor_key="inv:2:wp_starts_anzahl", zeitpunkt=t, wert_kwh=_stand6(lage, t),
                                  quelle="ha_statistics"))
        t += timedelta(hours=1)
    await db.commit()
    anlage = SimpleNamespace(id=1, anlagenname="F6", leistung_kwp=10.0, sensor_mapping=_WP)
    with _ohne_ha():
        h = await get_hourly_counter_sum_by_feld(db, anlage, _wp_inv(), _TAG6, "wp_starts_anzahl")
        tag = (await get_daily_counter_deltas_by_inv(db, anlage, _wp_inv(), _TAG6))["wp_starts_anzahl"]["2"]
    assert [h[x] for x in range(24)] == stunden
    assert tag == tageswert and h.fenster == fenster
    assert pruefe_counter_konsistent(h, h.fenster).konsistent


# ── H-F1: Wärme-Verlauf je Stunde — eine Quelle für alle Formen des Tages ──────────────────────────────────────────

_WP_STROM = {"investitionen": {"2": {"felder": {"stromverbrauch_kwh": {"strategie": "sensor", "sensor_id": "sensor.wp"}}}}}


def _waerme_ctx(*, wp_aus_kanal=False, mapping=None):
    from backend.api.routes.energie_profil.waerme import _WaermeStundenKontext
    from backend.tests.test_zaehlerluecken_snapshot import _inv

    anlage = SimpleNamespace(id=1, anlagenname="H-F1", leistung_kwp=10.0, sensor_mapping=mapping or _WP_STROM)
    return _WaermeStundenKontext(anlage_id=1, investitionen_by_id={"2": _inv(2, "waermepumpe")},
                                 eingaenge=SimpleNamespace(wp_aus_kanal=wp_aus_kanal), beitraege=[], detail=None,
                                 mapping=anlage.sensor_mapping["investitionen"], quellen_energy={}, mqtt_keys=set(),
                                 anlage=anlage)


async def test_hf1_gesamtstrom_aus_denselben_staenden_wie_die_summanden(db):
    """An einem Tag ohne WP-Kanal-Deckung kommt die Zählerspalte des Wärme-Verlaufs aus den Ständen (Bündel nach der
    Lücke) — nicht aus der gespeicherten Stundenzeile, deren Form anders sein kann (GM r28: «übrige» 08.04.2026 aus zwei
    Quellen 6,51 kWh). Ohne Stände eines Gesamt-Zählers, an einem WP-Kanal-Tag oder wenn die Stände einen anderen Tageswert
    ergeben als die Zählerspalte ``None`` (die Stundenzeile bleibt; getauscht wird nur die Verteilung, nie die Menge)."""
    from backend.api.routes.energie_profil.waerme import _gesamtstrom_aus_staenden

    await _snapshot_db(db, {"inv:2:stromverbrauch_kwh": _staende(T0 - timedelta(hours=1), T0 + timedelta(hours=23), 50.0,
                                                                 0.5, ohne={T0 + timedelta(hours=h) for h in (3, 4)})})
    with _ohne_ha():
        gespeichert = {h: 0.5 for h in range(24)}                  # die Stundenzeile (andere Form, derselbe Tag 12,0)
        je_slot = await _gesamtstrom_aus_staenden(db, DATUM, _waerme_ctx(), gespeichert)
        assert je_slot[3] is None and je_slot[4] is None and je_slot[5] == pytest.approx(1.5)
        assert sum(v for v in je_slot.values() if v is not None) == pytest.approx(12.0)
        assert await _gesamtstrom_aus_staenden(db, DATUM, _waerme_ctx(wp_aus_kanal=True), gespeichert) is None
        ohne_zaehler = {"investitionen": {"2": {"felder": {}}}}
        assert await _gesamtstrom_aus_staenden(db, DATUM, _waerme_ctx(mapping=ohne_zaehler), gespeichert) is None
        anderer_tag = {h: 0.6 for h in range(24)}                  # Zählerspalte ≠ Stände (andere Menge) ⇒ sie bleibt
        assert await _gesamtstrom_aus_staenden(db, DATUM, _waerme_ctx(), anderer_tag) is None


# ── Nachtrag 2: Bündel allein auf der WP-Achse ist keine Stichprobe des WP-Stundenprofils ───────────────────────────


@pytest.mark.parametrize("raster", [None, "beginn"], ids=["bestandstag", "kanal_tag"])
async def test_n2b_wp_buendel_keine_stichprobe_im_wp_profil(db, monkeypatch, raster):
    """Hat nur der WP-Zähler eine Lücke (Bilanz lückenlos), trägt die Zeile danach ``spannen["waermepumpe"] > 1`` und die Menge
    mehrerer Stunden. Sie ist keine Stichprobe des WP-Stundenprofils (``wp_werktag``) — der Hausverbrauch derselben Zeile
    bleibt eine (seine Achsen sind ungebündelt). Messung ``test_mess_n2b_wp_buendel.py``: am HEAD Slot 13 = 1,867 statt 0,8
    (Bestandstag, HA-Kanal-Tag) bzw. 1,8 (MQTT-Kanal-Tag)."""
    import backend.services.energie_profil.kanal_stunden as ks
    import backend.services.live_verbrauchsprofil_service as lvs
    from backend.services.live_verbrauchsprofil_service import _profil_from_db

    heute = date(2026, 10, 30)                                   # fest (Donnerstag): Lernwoche 23.–29.10.

    class _Heute(date):
        @classmethod
        def today(cls):
            return heute

    monkeypatch.setattr(lvs, "date", _Heute)

    anlage = Anlage(anlagenname="N2b", leistung_kwp=5.0)
    db.add(anlage)
    await db.flush()
    db.add(Investition(anlage_id=anlage.id, typ="waermepumpe", bezeichnung="WP", anschaffungsdatum=date(2024, 1, 1)))
    await db.commit()

    werktage = [date(2026, 10, 27), date(2026, 10, 28), date(2026, 10, 29)]
    buendel_tag = werktage[1]
    # Zeile, die Slot 13 trägt: Bestandszeile 13 bzw. Mischzeile 12 (Beginn-Raster, Slot h + 1).
    zeile_13 = 13 if raster is None else 12

    def zeile(d, h):
        gebuendelt = d == buendel_tag and h == zeile_13
        return SimpleNamespace(datum=d, stunde=h, raster=raster, verbrauch_kw=1.5, temperatur_c=None,
                               betriebsmodus_je_wp=None, komponenten=None,
                               waermepumpe_kw=4.0 if gebuendelt else (None if d == buendel_tag and 8 <= h < zeile_13 else 0.8),
                               spannen={"waermepumpe": 5} if gebuendelt else None)

    async def stunden(_db, _aid, _von, _bis, felder=None):
        return [zeile(d, h) for d in werktage for h in range(24)]

    monkeypatch.setattr(ks, "stunden_der_tage", stunden)
    prof = await _profil_from_db(anlage.id, db)
    assert prof["wp_werktag"][13] == pytest.approx(0.8)          # am HEAD (0,8 + 0,8 + 4,0) / 3 = 1,867
    assert prof["werktag"][13] == pytest.approx(1.5)             # Hausverbrauch der Zeile zählt weiter
