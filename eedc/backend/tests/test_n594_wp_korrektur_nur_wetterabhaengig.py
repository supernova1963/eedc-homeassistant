"""N-594 — die Temperaturkorrektur der Verbrauchsprognose skaliert nur, was von der Außentemperatur abhängt.

**Der Fund.** Die Prognose (Cockpit → Live, HA-/MQTT-Sensor „Verbrauchsprognose heute/morgen", die WP-Stundenreihe des
HA-Exports und sein Heizfenster) skalierte den GANZEN Wärmepumpen-Strom der Lernwoche mit dem Heizgradtag-Faktor des
Prognosetags. Ein Warmwasser-Zyklus fiel an einem warmen Übergangstag auf 10 % (2,0 ⇒ 0,2 kWh) und verdreifachte sich
an einem kalten (⇒ 6,0); Kühlstrom stieg an einem kühleren Tag um 30 %. Der milde Zweig (Lernwoche unter 1 Kd) hob
den WP-Strom bei UNVERÄNDERTEM Wetter um 7,5–13,5 %.

**Die Regel** (Bauplan N-594, Fachentscheide C-F1…C-F3):
* C-F1 — gemessenes Warmwasser und Kühlen bleiben fest; im milden Zweig bleibt nur das Kühlen fest.
* C-F2 — die Menge der Stunde ist die Zählermenge ``waermepumpe_kw``; die Trennung liefert Teilmengen: getrennte
  Leistungssensoren (``waermepumpe_<id>_warmwasser``/``_kuehlen``) oder das Betriebsmodus-Etikett der Stunde × die
  Stundenmenge des Geräts (Leistungssensor, bei genau einer WP die Zählermenge). Nie aus der Bauart (P13).
* C-F3 — milder Zweig ``1 + max(0; HDD_Tag − HDD_Ref) × 0,15``.

**Datenstand wie im Betrieb.** Die Lernwoche entsteht über den echten ``aggregate_day`` aus der HA-Langzeitstatistik im
Recorder-Schema (echter ``HAStatisticsService``, Zähler je Stunde, Matrix-Bausteine); der produktive Lerner
``_profil_from_db`` liest die Stundenzeilen, ``verbrauchsprognose_heute`` rechnet die Prognose. Gestellt wird nur,
was im Betrieb von außen kommt: Open-Meteo (Wetter der Lernwoche, Forecast des Prognosetags), der
Recorder-Zustandsverlauf des Betriebsmodus-Sensors (``_get_betriebsmodus_history`` liest ihn über die HA-API) und die
Leistungskurve des Tages (``prefetched_tagesverlauf`` von ``aggregate_day``, wie im Vollbackfill — sie trägt die
Leistungssensoren der Fälle mit ``kurve``).

**Die Uhr.** Der Lerner liest ``date.today()`` und nimmt keinen Stichtag entgegen; die Probe stellt ihn fest
(``_FesterTag`` auf ``live_verbrauchsprofil_service.date`` — dieselbe Bauform wie ``test_n593_wp_tagesfaktor.py``),
die Profilwahl bekommt ``now`` hereingereicht. Keine echte Uhr (N-167). HEUTE ist ein Mittwoch im Januar — fern jeder
Zeitumstellung in Berlin, UTC und Auckland; die Lernwoche trägt fünf Werktage und zwei Wochenendtage.

Lernprofil je Tag (eine WP): Haus 0,4 kW; Heizen 1,0 kWh in den Stunden 0–6 (7 kWh), Warmwasser-Zyklus 2,0 kWh um
14 Uhr — Σ 9,0 kWh. Lernwoche Ø 10 °C ⇒ Referenz 5 Kd.
"""

from __future__ import annotations

import shutil
import tempfile
import time as _zeit
from contextlib import ExitStack
from datetime import date, datetime, time, timedelta
from unittest.mock import AsyncMock, patch
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import select, text
from sqlalchemy.orm.attributes import flag_modified

from backend.models import Anlage, Investition
from backend.tests import ha_lts_helfer
from backend.tests import pv_achse_matrix as mx

HEUTE = date(2026, 1, 21)  # Mittwoch; Lernwoche 14.–20.01. (Mi–Di)


class _FesterTag(date):
    """``date.today()`` des Lerners, festgenagelt — keine echte Uhr (N-167)."""

    @classmethod
    def today(cls):  # noqa: D102 — Verhalten steht im Klassen-Docstring
        return HEUTE


def wp_std(t):          # Heizen 00–06 Uhr je 1,0 kWh, Warmwasser-Zyklus 14 Uhr 2,0 kWh
    return 1.0 if t.hour <= 6 else (2.0 if t.hour == 14 else 0.0)


def modus_std(h):       # Backward-Slot h = Intervall [h-1, h) ⇒ Etikett der Stunde, in der die Energie floss
    return "heizen" if 1 <= h <= 7 else ("warmwasser" if h == 15 else "aus")


def wp_kuehl(t):
    return 1.5 if t.hour == 14 else 0.0


def modus_kuehl(h):
    return "kuehlen" if h == 15 else "aus"


def wp_ww_jeden_zweiten_tag(t):
    return 1.0 if t.hour <= 6 else (2.0 if (t.hour == 14 and t.day % 2 == 0) else 0.0)


def _wpb(t):
    return 0.5 if 18 <= t.hour <= 20 else 0.0


ZWEI = (("WPA", wp_std, modus_std), ("WPB", _wpb, None))


def _kurve_gesamt(ids):       # je WP EIN Leistungssensor (Gesamt) — Punkt HH:00 = Mittel der Stunde [HH, HH+1)
    fns = {"WPA": wp_std, "WPB": _wpb}
    return ([f"waermepumpe_{i}" for i in ids.values()],
            lambda h: {f"waermepumpe_{i}": -fns[n](datetime(2026, 1, 1, h)) for n, i in ids.items()})


def _kurve_getrennt(ids):     # EINE WP mit getrennten Leistungssensoren Heizen / Warmwasser
    i = ids["WP"]

    def fn(h):
        return {f"waermepumpe_{i}_heizen": -(1.0 if h <= 6 else 0.0),
                f"waermepumpe_{i}_warmwasser": -(2.0 if h == 14 else 0.0)}
    return ([f"waermepumpe_{i}_heizen", f"waermepumpe_{i}_warmwasser"], fn)


class _Lernwoche:
    """``async with _Lernwoche(...) as lw`` — Anlage F15 + Wärmepumpen mit HA-Zählern, 7 Tage über ``aggregate_day``."""

    def __init__(self, *, lern_temp, wps=(("WP", wp_std, modus_std),), mit_modus=True, kurve=None):
        self.lern_temp, self.wps, self.mit_modus, self.kurve_fn = lern_temp, wps, mit_modus, kurve

    async def __aenter__(self):
        from backend.services.live_power_service import get_live_power_service
        import backend.services.live_verbrauchsprofil_service as lvps

        get_live_power_service()._kwh_cache._profil.clear()
        form = mx.FORMEN["F15"]
        self.verz = tempfile.mkdtemp(prefix="eedc-n594-")
        self.engine, self.db = await mx._neue_db(f"{self.verz}/x.db")
        db = self.db
        von = datetime.combine(HEUTE - timedelta(days=8), time(18))
        bis = datetime.combine(HEUTE, time(0))
        self.st = ExitStack()
        self.st.enter_context(patch.object(mx, "REIHE_VON", von))
        self.st.enter_context(patch.object(mx, "REIHE_BIS", bis))
        self.st.enter_context(patch.object(lvps, "date", _FesterTag))
        aid, _ids = await mx.seed_anlage(db, form)

        def _netz(t):  # der Netzbezug trägt den WP-Strom mit (sonst wäre der Hausverbrauch kleiner als die WP)
            return (0.0 if t.hour in mx.PROD_STUNDEN else mx.NETZ_NACHT) + sum(r(t) for _n, r, _m in self.wps)
        svc = mx.seed_ha(form, abweichung={"sensor.netz": (_netz, None)})
        a = (await db.execute(select(Anlage).where(Anlage.id == aid))).scalar_one()
        a.latitude, a.longitude = 50.0, 8.0
        m = dict(a.sensor_mapping)
        inv_map = dict(m.get("investitionen") or {})
        self.wp_ids = {}
        for name, rate, modus in self.wps:
            inv = Investition(anlage_id=aid, typ="waermepumpe", bezeichnung=name, anschaffungsdatum=mx.D0,
                              anschaffungskosten_gesamt=1000.0)
            db.add(inv)
            await db.flush()
            self.wp_ids[name] = inv.id
            sid = f"sensor.{name.lower()}_strom"
            mid = ha_lts_helfer.sensor(svc, sid, "kWh", has_sum=True)
            stand, zeilen, t = 500.0, [], von
            while t < bis:
                stand += rate(t)
                zeilen.append({"m": mid, "t": _zeit.mktime(t.timetuple()), "w": round(stand, 4)})
                t += timedelta(hours=1)
            with svc._engine.begin() as conn:
                conn.execute(text("INSERT INTO statistics (metadata_id, start_ts, state, sum) "
                                  "VALUES (:m, :t, :w, :w)"), zeilen)
            eintrag = {"felder": {"stromverbrauch_kwh": {"strategie": "sensor", "sensor_id": sid}}}
            if self.mit_modus and modus is not None:
                eintrag["live"] = {"betriebsmodus": f"climate.{name.lower()}"}
            inv_map[str(inv.id)] = eintrag
        m["investitionen"] = inv_map
        a.sensor_mapping = m
        flag_modified(a, "sensor_mapping")
        await db.commit()
        self.anlage = a

        async def _wetter(anlage, datum, pv_module=None):
            return {h: {"temperatur_c": self.lern_temp, "globalstrahlung_wm2": 0.0, "gti_wm2": None,
                        "bewoelkung_prozent": 50.0, "niederschlag_mm": 0.0, "wetter_code": 3} for h in range(24)}

        async def _modus(anlage, sensor_mapping, datum, db_):
            if not self.mit_modus:
                return {}
            return {h: {self.wp_ids[n]: fn(h) for n, _r, fn in self.wps if fn is not None} for h in range(24)}

        self.st.enter_context(patch("backend.services.energie_profil._helpers._get_wetter_ist", new=_wetter))
        self.st.enter_context(patch("backend.services.energie_profil._helpers._get_betriebsmodus_history",
                                    new=_modus))
        self.st.enter_context(mx._umgebung(svc))
        from backend.services.energie_profil.aggregator import aggregate_day
        from backend.services.energie_profil.source import Source

        kurve = mx._kurve(form)
        if self.kurve_fn is not None:
            keys, fn = self.kurve_fn(self.wp_ids)
            kurve = {"serien": [{"key": k, "kategorie": "waermepumpe", "seite": "senke", "bidirektional": False}
                                for k in keys],
                     "punkte": [{"zeit": f"{h:02d}:00", "werte": fn(h)} for h in range(24)],
                     "vortagsrand": [{"zeit": "23:00", "werte": fn(23)}]}
        for d in range(7, 0, -1):
            await aggregate_day(a, HEUTE - timedelta(days=d), db, source=Source.SCHEDULER,
                                prefetched_tagesverlauf=kurve)
            await db.commit()
        return self

    async def __aexit__(self, *exc):
        from backend.services.live_power_service import get_live_power_service

        get_live_power_service()._kwh_cache._profil.clear()
        self.st.close()
        await self.db.close()
        await self.engine.dispose()
        shutil.rmtree(self.verz, ignore_errors=True)

    async def profil(self) -> dict:
        from backend.services.live_power_service import get_live_power_service

        return await get_live_power_service().get_verbrauchsprofil(self.anlage, self.db)

    async def prognose(self, prog_temp: float, *, werktag: bool):
        """Prognose für den nächsten Werktag bzw. Wochenendtag nach HEUTE (Profilwahl über ``now``)."""
        from backend.services.verbrauchsprognose_heute import verbrauchsprognose_heute

        tag = HEUTE
        while (tag.weekday() < 5) != werktag:
            tag += timedelta(days=1)
        now = datetime.combine(tag, time(12), tzinfo=ZoneInfo("Europe/Berlin"))
        data = {"hourly": {"time": [f"{tag.isoformat()}T{h:02d}:00" for h in range(24)],
                           "temperature_2m": [prog_temp] * 24}}
        with patch("backend.api.routes.live_wetter._lade_forecast_gecached",
                   new=AsyncMock(return_value=(data, None, True))):
            return await verbrauchsprognose_heute(self.anlage, self.db, now)


def _teil_le_reihe(p: dict) -> bool:
    for tt in ("werktag", "wochenende"):
        wp = p.get(f"wp_{tt}") or {}
        ww, ku = p.get(f"wp_ww_{tt}") or {}, p.get(f"wp_kuehlen_{tt}") or {}
        if any(ww.get(h, 0.0) + ku.get(h, 0.0) > wp.get(h, 0.0) + 1e-9 for h in range(24)):
            return False
    return True


#: ``name: (Lernwoche-Argumente, Σ WP-Profil je Tag, {Prognose-Temperatur: WP-Tag Soll})`` — Bauplan „Erwartete Zahlen".
FAELLE = {
    "eine-wp-etikett": (dict(lern_temp=10.0), 9.0, {10.0: 9.0, 16.0: 2.7, 0.0: 23.0, 5.0: 16.0}),
    "eine-wp-ohne-modus": (dict(lern_temp=10.0, mit_modus=False), 9.0, {10.0: 9.0, 16.0: 0.9, 0.0: 27.0}),
    "mild-0,5": (dict(lern_temp=14.5), 9.0, {14.5: 9.0, 20.0: 9.0, 5.0: 21.79, 0.0: 27.0}),
    "mild-0,5-ohne-modus": (dict(lern_temp=14.5, mit_modus=False), 9.0, {14.5: 9.0, 5.0: 21.79, 0.0: 27.0}),
    "mild-0,9": (dict(lern_temp=14.1), 9.0, {14.1: 9.0, 5.0: 21.32}),
    "grenze-1,0": (dict(lern_temp=14.0), 9.0, {14.0: 9.0, 5.0: 23.0}),
    "kuehlwoche": (dict(lern_temp=24.0, wps=(("WP", wp_kuehl, modus_kuehl),)), 1.5, {24.0: 1.5, 13.0: 1.5, 30.0: 1.5}),
    "kuehlwoche-ohne-modus": (dict(lern_temp=24.0, wps=(("WP", wp_kuehl, modus_kuehl),), mit_modus=False), 1.5,
                              {13.0: 1.95}),
    "zwei-wp-nur-zaehler": (dict(lern_temp=10.0, wps=ZWEI), 10.5, {10.0: 10.5, 16.0: 1.05, 0.0: 31.5}),
    "zwei-wp-leistungssensoren": (dict(lern_temp=10.0, wps=ZWEI, kurve=_kurve_gesamt), 10.5,
                                  {10.0: 10.5, 16.0: 2.85, 0.0: 27.5}),
    "getrennte-leistungssensoren": (dict(lern_temp=10.0, mit_modus=False, kurve=_kurve_getrennt), 9.0,
                                    {10.0: 9.0, 16.0: 2.7, 0.0: 23.0}),
}


@pytest.mark.parametrize("fall", list(FAELLE))
async def test_prognose_skaliert_nur_den_wetterabhaengigen_teil(fall):
    kw, wp_tag_soll, soll = FAELLE[fall]
    async with _Lernwoche(**kw) as lw:
        p = await lw.profil()
        assert p["quelle"] == "db", p.get("quelle")
        for tt in ("werktag", "wochenende"):
            # `wp_<tagtyp>` bleibt die ganze Zählermenge — die Teilmengen stehen daneben, nie davon abgezogen.
            assert round(sum(p[f"wp_{tt}"].values()), 3) == wp_tag_soll, (tt, p[f"wp_{tt}"])
        assert _teil_le_reihe(p), p
        basis = {}
        for werktag in (True, False):
            for temp, wp_soll in soll.items():
                r = await lw.prognose(temp, werktag=werktag)
                assert r.profil_typ == ("individuell_werktag" if werktag else "individuell_wochenende"), r.profil_typ
                wp_ist = round(sum(r.wp_stunden_kwh), 2)
                assert wp_ist == wp_soll, (fall, werktag, temp, wp_ist, r.wp_stunden_kwh)
                # Kachel (live_wetter, `summe_kwh`) und WP-Stundenreihe (HA-Export) bewegen sich gleich: der Teil
                # ohne Wärmepumpe ist von der Temperatur unberührt (bis auf die Rundung je Stunde).
                rest = round(r.summe_kwh - wp_ist, 2)
                basis.setdefault(werktag, rest)
                assert abs(rest - basis[werktag]) <= 0.15, (fall, werktag, temp, rest, basis[werktag])


async def test_warmwasser_jeden_zweiten_tag_gleicher_nenner():
    """Die Teilmengen mitteln über DIESELBEN Stichproben wie die Reihe — eine Stunde ohne Warmwasser trägt 0 bei.

    Mittelte man nur die Stunden mit Wert, wäre die Teilmenge (2,0) größer als die Reihe (1,2) und der warme Tag hielte
    mehr Warmwasser fest, als die Woche je Tag hatte.
    """
    async with _Lernwoche(lern_temp=10.0, wps=(("WP", wp_ww_jeden_zweiten_tag, modus_std),)) as lw:
        p = await lw.profil()
        assert _teil_le_reihe(p), p
        # Werktage 14.–20.01.: gerade sind 14, 16, 20 (3 von 5) ⇒ 1,2; Wochenende 17/18: nur 18 ⇒ 1,0.
        assert (p["wp_werktag"][15], p["wp_ww_werktag"][15]) == (1.2, 1.2), p
        assert (p["wp_wochenende"][15], p["wp_ww_wochenende"][15]) == (1.0, 1.0), p
        r = await lw.prognose(16.0, werktag=True)
        assert r.wp_stunden_kwh[15] == 1.2, r.wp_stunden_kwh


@pytest.mark.parametrize("fall", ["eine-wp-ohne-modus", "zwei-wp-nur-zaehler"])
async def test_halteprobe_ohne_trennung_jede_stunde_bitgleich(fall):
    """Ohne Trennung (kein Modus, kein getrennter Sensor) und außerhalb des milden Zweigs ist jede Prognosestunde
    die Skalierung vor N-594, ``wp_profil × Tagesfaktor`` — bitgleich, Stunde für Stunde. Zwei Wärmepumpen nur mit
    Zählern: die Zählermenge lässt sich keinem Gerät zuordnen, also keine Trennung (benannte Grenze)."""
    from backend.core.berechnungen.heizgradtage import wp_tagesfaktor

    kw, _wp_tag, soll = FAELLE[fall]
    async with _Lernwoche(**kw) as lw:
        p = await lw.profil()
        assert not any(k.startswith(("wp_ww_", "wp_kuehlen_")) for k in p), sorted(p)
        for werktag in (True, False):
            wp = p["wp_werktag" if werktag else "wp_wochenende"]
            for temp in soll:
                r = await lw.prognose(temp, werktag=werktag)
                faktor = wp_tagesfaktor(p["referenz_hdd_kd"], [temp] * 24)
                alt = [round(float(wp.get(h, 0.0)) * faktor, 2) for h in range(24)]
                assert r.wp_stunden_kwh == alt, (fall, werktag, temp, r.wp_stunden_kwh, alt)
