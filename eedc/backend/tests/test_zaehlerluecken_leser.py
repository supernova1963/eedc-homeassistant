"""Zählerlücken wie HA — Schnitt 7: die Leser aus §2, je Leser eine Probe (P6/P17).

Vorlage `plans/vorlage-zaehlerluecken-ha-weg.md` Fassung 7 §2. Grundsatz: **die
Energie zählt in jeder Summe**; wer **Stunde gegen Stunde** stellt, lässt Zeilen
mit ``spannen[achse] > 1`` aus; wer **Tag gegen Tag** stellt, lässt **beide** Tage
um ein Mitternachtsbündel mit Energie aus (D und D+1), dazu Tage mit
``verworfen[achse]``. Ein 0-Bündel lässt beide drin, ein inneres Bündel den Tag.

⚠ **Vier Stellen lesen die echte Uhr** (`date.today()`, Baseline in
`test_konformitaet_echte_uhr_in_tests.py`): die Prüflinge
`stratifizierung_endpoint`, `get_prognosen_genauigkeit`,
`_check_pv_ueber_erfassung` und `_profil_from_db` bilden ihr Fenster selbst aus
`date.today()` und nehmen keinen Stichtag entgegen. Die Proben legen ihre Tage
deshalb relativ zu heute — die Zusicherungen hängen an keiner Uhrzeit (nur an
Tagesabständen), in allen drei Zonen gleich.

Schwesterdateien: test_zaehlerluecken_tagesregel.py (Tag/Monat),
test_zaehlerluecken_snapshot.py (Fensterschalter, Vorschau),
test_korrekturprofil_stunde_variante_a.py (Korrekturprofil-Fixture).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from types import SimpleNamespace
from typing import Optional
from unittest.mock import AsyncMock, patch

import pytest

from backend.core.berechnungen.spannen import (
    tage_um_mitternachtsbuendel,
    zeile_traegt_vortagsenergie,
)
from backend.models.anlage import Anlage
from backend.models.tages_energie_profil import TagesEnergieProfil, TagesZusammenfassung

JETZT = datetime(2026, 9, 26)


def _tep(aid, d, h, **kw):
    kw.setdefault("source_provenance", {})
    return TagesEnergieProfil(anlage_id=aid, datum=d, stunde=h, **kw)


def _tz(aid, d, **kw):
    kw.setdefault("source_provenance", {})
    return TagesZusammenfassung(anlage_id=aid, datum=d, created_at=JETZT, updated_at=JETZT, **kw)


async def _anlage(db, **kw) -> Anlage:
    a = Anlage(anlagenname="Leser", leistung_kwp=kw.pop("kwp", 10.0), **kw)
    db.add(a)
    await db.flush()
    return a


# ── Die Helfer selbst (P6-Kern): D und D+1, 0-Bündel, inneres Bündel ──────


@dataclass
class _R:
    datum: date
    stunde: int
    pv_kw: Optional[float]
    spannen: Optional[dict]


def test_p6_helfer_mitternachtsbuendel_nimmt_d_und_d_plus_1():
    d1 = date(2026, 5, 15)
    rows = {d1: [_R(d1, 1, 3.0, {"pv": 5})]}                  # 21:00 D → 01:00 D+1
    assert tage_um_mitternachtsbuendel(rows, "pv") == {d1, d1 - timedelta(days=1)}


def test_p6_helfer_null_buendel_und_inneres_buendel_lassen_die_tage_drin():
    d1 = date(2026, 5, 15)
    assert tage_um_mitternachtsbuendel({d1: [_R(d1, 1, 0.0, {"pv": 5})]}, "pv") == set()
    assert tage_um_mitternachtsbuendel({d1: [_R(d1, 14, 6.0, {"pv": 3})]}, "pv") == set()


def test_u4_vortagsenergie_ist_dst_fest(monkeypatch):
    """Herbst-Umstellungstag: vom Fensterbeginn (Vortag 23:00 CEST) bis zum Ende
    von Slot 3 (03:00 CET) sind es **fünf** reale Stunden. n = 5 ist also noch
    keine Vortagsenergie — die Schwelle ``n > h + 1 = 4`` hätte sie behauptet (Ü4)."""
    import os, time as _t
    alt = os.environ.get("TZ")
    os.environ["TZ"] = "Europe/Berlin"; _t.tzset()
    try:
        d = date(2025, 10, 26)
        assert zeile_traegt_vortagsenergie(_R(d, 3, 1.0, {"pv": 2}), "pv") is False
        assert zeile_traegt_vortagsenergie(_R(d, 3, 1.0, {"pv": 5}), "pv") is False
        assert zeile_traegt_vortagsenergie(_R(d, 3, 1.0, {"pv": 6}), "pv") is True
    finally:
        if alt is None:
            os.environ.pop("TZ", None)
        else:
            os.environ["TZ"] = alt
        _t.tzset()


# ── vergleichstage (DB) ──────────────────────────────────────────────────


async def test_vergleichstage_bundel_und_verworfen(db):
    from backend.services.energie_profil.vergleichstage import tage_ohne_tagesvergleich

    a = await _anlage(db)
    d = date(2026, 5, 15)
    db.add(_tep(a.id, d, 0, pv_kw=0.0, spannen={"pv": 9}))          # 0-Bündel
    db.add(_tep(a.id, d + timedelta(days=3), 2, pv_kw=4.0, spannen={"pv": 8}))
    db.add(_tz(a.id, d + timedelta(days=6), verworfen={"pv": 31368.0}))
    db.add(_tz(a.id, d + timedelta(days=7), verworfen={"wallbox": 5.0}))
    await db.commit()
    tage = await tage_ohne_tagesvergleich(db, a.id, "pv")
    assert tage == {d + timedelta(days=2), d + timedelta(days=3), d + timedelta(days=6)}


# ── Korrekturprofil (Aggregator + Route) ──────────────────────────────────


async def test_korrekturprofil_aggregator_laesst_die_gebuendelte_stunde_aus(db):
    from sqlalchemy import select
    from backend.models.korrekturprofil import PROFIL_TYP_STUNDE, Korrekturprofil
    from backend.services.korrekturprofil_aggregator import aggregiere_korrekturprofil_anlage

    a = await _anlage(db, latitude=48.1, longitude=11.6)
    for tag in range(1, 17):
        d = date(2026, 5, tag)
        profil = [0.0] * 24
        profil[9] = 2.5
        profil[11] = 2.5
        db.add(_tz(a.id, d, lern_soll_stundenprofil_kwh=profil, stunden_verfuegbar=24))
        db.add(_tep(a.id, d, 9, pv_kw=2.0))
        db.add(_tep(a.id, d, 11, pv_kw=30.0, spannen={"pv": 3}))   # Energie einer Lücke
    await db.commit()
    await aggregiere_korrekturprofil_anlage(a, db, heute=date(2026, 6, 1))
    p = (await db.execute(select(Korrekturprofil).where(
        Korrekturprofil.anlage_id == a.id, Korrekturprofil.profil_typ == PROFIL_TYP_STUNDE,
    ))).scalar_one()
    assert p.faktoren["5"]["9"] == pytest.approx(0.8)
    assert "11" not in p.faktoren["5"]


async def test_korrekturprofil_route_laesst_die_gebuendelte_stunde_aus(db):
    from backend.api.routes.korrekturprofil import stratifizierung_endpoint

    a = await _anlage(db)
    d = date.today() - timedelta(days=2)
    profil = [0.0] * 24
    profil[10] = 2.0
    profil[12] = 2.0
    db.add(_tz(a.id, d, pv_prognose_stundenprofil=profil))
    db.add(_tep(a.id, d, 10, pv_kw=2.0, bewoelkung_prozent=10.0, niederschlag_mm=0.0))
    db.add(_tep(a.id, d, 12, pv_kw=9.0, bewoelkung_prozent=10.0, niederschlag_mm=0.0,
                spannen={"pv": 4}))
    await db.commit()
    r = await stratifizierung_endpoint(a.id, tage=30, db=db)
    assert r.stunden_klassifiziert == 1


# ── Prognose-vs-IST je Stunde (ist_profil) ───────────────────────────────


def test_ist_profil_buendel_aus_dem_stundenvergleich_energie_in_der_summe():
    from backend.services.prognose_adapter import ist_profil

    d = date(2026, 5, 15)
    rows = [_R(d, 9, 1.0, None), _R(d, 12, 6.0, {"pv": 3}), _R(d, 13, 2.0, None)]
    p = ist_profil(rows, jetzt_stunde=20, datum=d)
    assert p.slots_kw[12] is None and p.buendel_stunden == (12,)
    assert p.tageswert_kwh == 9.0
    assert p.unvollstaendig is False                         # inneres Bündel
    mitternacht = [_R(d, 2, 3.0, {"pv": 6})] + rows
    assert ist_profil(mitternacht, jetzt_stunde=20, datum=d).unvollstaendig is True
    assert ist_profil(rows, jetzt_stunde=20, datum=d, verworfen={"pv": 5.0}).unvollstaendig is True


# ── Lernfaktor · Genauigkeit (Service + Route) · Checker PR ──────────────


async def _seed_prognose_tage(db, aid, heute, *, buendel_tag: date):
    """10 Tage IST = Prognose = 10 kWh; am `buendel_tag` + Folgetag trägt der
    Folgetag 5 kWh Vortagsenergie (D: 5, D+1: 15)."""
    for i in range(1, 11):
        d = heute - timedelta(days=i)
        ist = 10.0
        if d == buendel_tag:
            ist = 5.0
        if d == buendel_tag + timedelta(days=1):
            ist = 15.0
            db.add(_tep(aid, d, 1, pv_kw=5.0, spannen={"pv": 5}))
        db.add(_tz(aid, d, pv_prognose_kwh=10.0, komponenten_kwh={"pv_1": ist}))
    await db.commit()


async def test_lernfaktor_laesst_d_und_d_plus_1_aus(db):
    from backend.api.routes.live_wetter import _get_lernfaktor_detail, _lernfaktor_cache

    a = await _anlage(db)
    heute = date(2026, 5, 20)
    await _seed_prognose_tage(db, a.id, heute, buendel_tag=heute - timedelta(days=5))
    _lernfaktor_cache.clear()
    r = await _get_lernfaktor_detail(a.id, db, quelle="openmeteo", heute=heute)
    assert r.tage_count == 8
    assert r.faktor == pytest.approx(1.0)


async def test_genauigkeit_service_laesst_d_und_d_plus_1_aus(db):
    from backend.services.prognose_genauigkeit_service import eedc_mae_prozent

    a = await _anlage(db)
    heute = date(2026, 5, 20)
    await _seed_prognose_tage(db, a.id, heute, buendel_tag=heute - timedelta(days=5))
    with patch("backend.api.routes.live_wetter._get_lernfaktor", new=AsyncMock(return_value=1.0)):
        mae, n = await eedc_mae_prozent(db, a.id, heute=heute, tage=30)
    assert (mae, n) == (0.0, 8)


async def test_genauigkeit_route_laesst_d_und_d_plus_1_aus_der_mae(db):
    from backend.api.routes.prognosen import get_prognosen_genauigkeit

    a = await _anlage(db)
    heute = date.today()
    await _seed_prognose_tage(db, a.id, heute, buendel_tag=heute - timedelta(days=5))
    with patch("backend.api.routes.prognosen._get_lernfaktor", new=AsyncMock(return_value=None)):
        r = await get_prognosen_genauigkeit(a.id, tage=30, ausreisser_ausblenden=False, db=db)
    assert r.openmeteo_mae_prozent == 0.0
    assert r.anzahl_tage == 10                               # die Tage bleiben sichtbar


async def test_checker_pv_ueber_erfassung_laesst_d_plus_1_aus(db):
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload
    from backend.services.daten_checker import CheckKategorie, CheckSeverity, DatenChecker

    a = await _anlage(db)
    heute = date.today()
    # drei Folgetage je mit 60 kWh Vortagsenergie (8 kWh/kWp > 7) ⇒ ohne Regel ein Verdacht
    for i in (3, 6, 9):
        d = heute - timedelta(days=i)
        db.add(_tz(a.id, d, komponenten_kwh={"pv_1": 80.0}))
        db.add(_tep(a.id, d, 2, pv_kw=60.0, spannen={"pv": 30}))
    await db.commit()
    anlage = (await db.execute(select(Anlage).options(selectinload(Anlage.investitionen))
                               .where(Anlage.id == a.id))).scalar_one()
    erg = await DatenChecker(db)._check_pv_ueber_erfassung(anlage)
    assert not [e for e in erg if e.kategorie == CheckKategorie.PV_UEBER_ERFASSUNG.value
                and e.schwere in (CheckSeverity.WARNING.value, CheckSeverity.ERROR.value)]


# ── Spike-Checker: Schwelle × Spanne (R3) ────────────────────────────────


async def test_spike_checker_schwelle_mal_spanne(db):
    from backend.services.daten_checker import DatenChecker

    a = await _anlage(db)
    d = date(2026, 5, 10)
    db.add(_tep(a.id, d, 12, pv_kw=30.0, spannen={"pv": 3}))      # 30 ≤ 15 × 3
    db.add(_tep(a.id, d, 14, pv_kw=30.0))                          # 30 > 15
    await db.commit()
    spikes = await DatenChecker(db)._spike_tage(a, d, d, 10.0)
    assert spikes == {d: [(14, "pv_kw", 30.0)]}


# ── Monats-Spitzen, Profil, Grundbedarf (monat.py) ───────────────────────


async def test_monat_spitzen_und_grundbedarf_ohne_gebuendelte_zeile(db):
    from backend.api.routes.energie_profil.views import get_monatsauswertung

    a = await _anlage(db)
    d = date(2026, 5, 10)
    db.add(_tep(a.id, d, 2, pv_kw=0.0, verbrauch_kw=0.3, netzbezug_kw=0.3, einspeisung_kw=0.0))
    db.add(_tep(a.id, d, 4, pv_kw=0.0, verbrauch_kw=2.4, netzbezug_kw=2.4, einspeisung_kw=0.0,
                spannen={"pv": 3, "netzbezug": 3, "einspeisung": 3}))
    db.add(_tep(a.id, d, 13, pv_kw=40.0, einspeisung_kw=35.0, netzbezug_kw=0.0, verbrauch_kw=5.0,
                spannen={"pv": 4, "einspeisung": 4, "netzbezug": 4}))
    db.add(_tep(a.id, d, 14, pv_kw=8.0, einspeisung_kw=6.0, netzbezug_kw=0.0, verbrauch_kw=2.0))
    await db.commit()
    m = await get_monatsauswertung(a.id, jahr=2026, monat=5, top_n=10, db=db)
    assert m.peak_pv.wert_kw == 8.0
    assert [p.wert_kw for p in m.peak_einspeisung] == [6.0]
    assert [p.wert_kw for p in m.peak_netzbezug] == [0.3]
    assert m.grundbedarf_kw == 0.3
    assert m.pv_kwh == 48.0                                  # Energie bleibt in der Summe


# ── Grundlast Cockpit/Monat + HA-Sensor (vergleich.py, Ü3) ───────────────


async def test_grundlast_nachtstunden_ohne_gebuendelte_zeile(db):
    from backend.api.routes.aktueller_monat.vergleich import _load_grundlast_nacht_kw

    a = await _anlage(db)
    d = date(2026, 5, 10)
    db.add(_tep(a.id, d, 1, verbrauch_kw=0.4))
    db.add(_tep(a.id, d, 3, verbrauch_kw=1.2, spannen={"pv": 3, "netzbezug": 3, "einspeisung": 3}))
    await db.commit()
    assert await _load_grundlast_nacht_kw(a.id, 2026, 5, db) == [0.4]


# ── Verbrauchsprofil + Verbrauchsprognose ────────────────────────────────


async def test_verbrauchsprofil_ohne_gebuendelte_zeile(db):
    from backend.services.live_verbrauchsprofil_service import _profil_from_db

    a = await _anlage(db)
    for i in range(1, 8):
        d = date.today() - timedelta(days=i)
        for h in range(24):
            sp = {"pv": 3, "netzbezug": 3, "einspeisung": 3} if h == 5 else None
            db.add(_tep(a.id, d, h, verbrauch_kw=(9.0 if h == 5 else 0.5), spannen=sp))
    await db.commit()
    p = await _profil_from_db(a.id, db)
    # Stunde 5 trägt keine Stichprobe mehr ⇒ kein Mittel von 9,0 im Profil
    assert p is not None
    assert all(abs(v - 9.0) > 1e-6 for v in _alle_zahlen(p))


def _alle_zahlen(o):
    if isinstance(o, dict):
        for v in o.values():
            yield from _alle_zahlen(v)
    elif isinstance(o, (list, tuple)):
        for v in o:
            yield from _alle_zahlen(v)
    elif isinstance(o, (int, float)) and not isinstance(o, bool):
        yield float(o)


async def test_verbrauchsprognose_ohne_gebuendelte_zeile(db):
    from backend.services.verbrauch_prognose_service import get_verbrauch_prognose

    a = await _anlage(db)
    ziel = date(2026, 6, 1)
    for i in range(1, 57):
        d = ziel - timedelta(days=i)
        for h in range(24):
            sp = {"pv": 3, "netzbezug": 3, "einspeisung": 3} if h == 7 else None
            db.add(_tep(a.id, d, h, verbrauch_kw=(9.0 if h == 7 else 0.5), spannen=sp))
    await db.commit()
    r = await get_verbrauch_prognose(a.id, ziel, db)
    assert r is not None
    assert r["stunden_kw"][7] != pytest.approx(9.0)


# ── Speicher: Wirtschaftlichkeit, Sizing, Potential ──────────────────────


async def test_speicher_ladepreis_laesst_gebuendelte_zeile_aus(db):
    from backend.services.speicher_wirtschaftlichkeit import berechne_effektiver_ladepreis

    a = await _anlage(db)
    d = date(2026, 5, 10)
    db.add(_tep(a.id, d, 3, batterie_kw=-3.0, netzbezug_kw=3.0, strompreis_cent=None,
                spannen={"batterie": 3, "netzbezug": 3}))
    await db.commit()
    r = await berechne_effektiver_ladepreis(db, anlage_id=a.id, von=d, bis=d)
    assert r.quelle == "keine-tep-daten"


def test_speicher_sizing_und_potential_behandeln_buendel_wie_none():
    from backend.services.speicher_potential_service import _als_speicher_stunde
    from backend.services.speicher_sizing_service import _als_sizing_stunde

    z = SimpleNamespace(datum=date(2026, 5, 10), stunde=3, pv_kw=0.0, verbrauch_kw=None,
                        soc_prozent=50.0, batterie_kw=-3.0, einspeisung_kw=2.0,
                        netzbezug_kw=3.0, spannen={"batterie": 3, "netzbezug": 3, "einspeisung": 3},
                        created_at=datetime(2026, 9, 26))
    s = _als_sizing_stunde(z)
    assert s.batterie_kwh is None and s.netzbezug_kwh is None
    p = _als_speicher_stunde(z, 50.0)
    assert p.netzbezug_kwh == 0.0 and p.einspeisung_kwh == 0.0


# ── PV-Anteil der Heimladung je Stunde ───────────────────────────────────


def test_pv_anteil_heimladung_leitet_gebuendelte_stunde_nicht_ab():
    from backend.core.berechnungen.pv_anteil_ladung import leite_pv_anteil_ab
    from backend.services.energie_profil.aggregator import (
        StundenKontext, TagesAkkumulator, Wetterstunde, Zaehlerstunde, verrechne_stunde,
    )

    kontext = StundenKontext(
        anlage=SimpleNamespace(id=1), datum=date(2026, 5, 10), netz_keys=set(), pv_keys=set(),
        sonderschluessel=set(), kwh_pro_stunde={}, kwh_source_label="x", wetter_stunden={},
        soc_stunden={}, soc_je_stunde={}, betriebsmodus_je_stunde={},
        strompreis_stunden=SimpleNamespace(sensor={}, boerse={}),
        wp_starts_pro_stunde={}, wp_betriebsstunden_pro_stunde={},
    )
    wetter = Wetterstunde(None, None, None, None, None, None)
    akku = TagesAkkumulator()
    for h, sp in ((12, None), (13, {"wallbox": 3})):
        z = Zaehlerstunde(pv_kw=5.0, sonstige_erz_kw=None, einspeisung_kw=2.0, netzbezug_kw=0.0,
                          verbrauch_kw=None, waermepumpe_kw=None, wallbox_kw=3.0,
                          batterie_kw=None, spannen=sp)
        verrechne_stunde(h, z, wetter, kontext, akku)
    anteil = leite_pv_anteil_ab(akku.lade_stunden)
    assert anteil.vollstaendig is False                       # Stunde 13 nicht abgeleitet


# ── Achse-2-Invariante toleriert gebündelte Tage ─────────────────────────


def test_achse2_invariante_toleriert_gebuendelten_tag():
    from backend.core.berechnungen.invarianten import pruefe_tep_komponenten_intern_konsistenz

    def row(wb, komp, sp=None):
        return SimpleNamespace(pv_kw=None, waermepumpe_kw=None, batterie_kw=None,
                               wallbox_kw=wb, komponenten=komp, spannen=sp)
    ohne = [row(5.0, {"wallbox_3": -0.0}), row(0.0, {"wallbox_3": -0.0})]
    mit = [row(5.0, {"wallbox_3": -0.0}, {"wallbox": 6}), row(0.0, {"wallbox_3": -0.0})]
    b1 = pruefe_tep_komponenten_intern_konsistenz(ohne, None)
    b2 = pruefe_tep_komponenten_intern_konsistenz(mit, None)
    assert [b.konsistent for b in b1] == [False]
    assert [b.konsistent for b in b2] == [True] and "gebündelter Tag" in b2[0].details


# ── Repair-Vorschau Δ: „aus Lücke" ───────────────────────────────────────


async def test_repair_pv_aus_luecke(db):
    from backend.api.routes.energie_profil.repair import _pv_aus_luecke

    a = await _anlage(db)
    d = date(2026, 11, 5)
    db.add(_tep(a.id, d, 19, pv_kw=118.0, spannen={"pv": 129}))
    db.add(_tep(a.id, d, 20, pv_kw=1.0))
    await db.commit()
    assert await _pv_aus_luecke(db, a.id, d) == 118.0
    assert await _pv_aus_luecke(db, a.id, d + timedelta(days=1)) is None
