"""Tests — Prognose-Kanon: EIN Wert über alle Pfade (Produktions-Fix V3).

Bau-Vertrag ``docs/drafts/KONZEPT-PROGNOSE-KANON.md`` §6. Deckt ab:

* **Symmetrie** ([[feedback_aggregator_symmetrie]]): bei fixem OM-Snapshot
  liefern Kanon-Service, ``berechne_eedc_prognose`` (eedc-Spalte/Vergleich)
  und der HA-Export (MQTT) denselben „heute"-Wert.
* **Multi-String**: 2-Orientierungs-Anlage → Σ Gruppen == Kanon-OM-Profil;
  Regression-Guard gegen ein Kollabieren auf eine gemittelte Orientierung.
* **MQTT**: „heute" == Kanon-eedc; „Rest heute" konsistent (auch bei großer
  Korrektur).
* **Rolling**: zwei OM-Snapshots → der Wert ändert sich in allen Pfaden gleich.
* **§6**: Tracking-Endwert rollt vor Sonnenuntergang, friert nach Konvergenz
  ein; das Genauigkeits-Ranking liest den Endwert (Fallback rollend).
* **Invariante**: Tageswert == Σ Export-Slots (über den Kanon).
"""

from __future__ import annotations

import contextlib
from datetime import date, datetime, time as dt_time, timedelta
from types import SimpleNamespace

import pytest

from backend.core.berechnungen.prognose_final import soll_final_einfrieren
from backend.models import Anlage, Investition, Monatsdaten


# ── Fake OpenMeteo: ausrichtungs-abhängige Kurvenform, kWp-skaliert ──────────

def _fake_slots(kwp: float, ausrichtung: int, tagesfaktor: float) -> list[float]:
    """24 kWh-Slots: Peak wandert mit der Ausrichtung (Ost früher, West später),
    Gesamtenergie = ``kwp × tagesfaktor`` (orientierungs-unabhängig normiert).
    So testet die Slot-Form den Fan-out, die Tagessumme die Energieerhaltung."""
    peak = 13 + ausrichtung / 45.0  # 0°→13, 90(W)→15, -90(O)→11
    roh = [max(0.0, 1.0 - abs(h - peak) / 5.0) if 6 <= h <= 20 else 0.0 for h in range(24)]
    s = sum(roh) or 1.0
    return [kwp * tagesfaktor * r / s for r in roh]


_TAGESFAKTOREN = [2.0, 1.8, 1.5, 1.2]  # heute, +1, +2, +3 (kWh pro kWp)


def _fake_prognose(kwp: float, ausrichtung: int):
    heute = date.today()
    tage = []
    for i, tf in enumerate(_TAGESFAKTOREN):
        slots = _fake_slots(kwp, ausrichtung, tf)
        tage.append(SimpleNamespace(
            datum=(heute + timedelta(days=i)).isoformat(),
            pv_ertrag_kwh=round(sum(slots), 3),
            stunden_kw=slots,
            stunden_bewoelkung=[0.0] * 24,
            stunden_niederschlag=[0.0] * 24,
            stunden_wetter_code=[0] * 24,
        ))
    return SimpleNamespace(tageswerte=tage)


@pytest.fixture
def _patch(monkeypatch):
    """Patcht OpenMeteo + Lernfaktor; Skalar 0.9, keine Stunden-Profile."""
    import backend.services.solar_forecast_service as sfs
    import backend.api.routes.live_wetter as lw
    from backend.services.korrekturprofil_lookup import _cache

    async def fake_get_solar_prognose(**kwargs):
        return _fake_prognose(kwargs["kwp"], kwargs["ausrichtung"])

    async def fake_lernfaktor(anlage_id, db, quelle="openmeteo"):
        return 0.9

    monkeypatch.setattr(sfs, "get_solar_prognose", fake_get_solar_prognose)
    monkeypatch.setattr(lw, "_get_lernfaktor", fake_lernfaktor)
    _cache.clear()


async def _seed(db, *, module: list[tuple[float, int]] | None = None) -> Anlage:
    """module = Liste von (kwp, ausrichtung_grad). Default: ein 10-kWp-Süd-Modul."""
    anlage = Anlage(
        anlagenname="Kanon-Test", leistung_kwp=sum(m[0] for m in (module or [(10.0, 0)])),
        latitude=48.8, longitude=9.2, standort_land="DE", prognose_quelle="eedc",
    )
    db.add(anlage)
    await db.flush()
    db.add(Monatsdaten(anlage_id=anlage.id, jahr=2025, monat=1,
                       netzbezug_kwh=100.0, einspeisung_kwh=200.0))
    for kwp, azi in (module or [(10.0, 0)]):
        db.add(Investition(
            anlage_id=anlage.id, typ="pv-module", bezeichnung=f"String {azi}",
            leistung_kwp=kwp, neigung_grad=35,
            anschaffungsdatum=date(2024, 1, 1),
            parameter={"ausrichtung_grad": azi},
        ))
    await db.flush()
    return anlage


# ── Symmetrie über alle Pfade ────────────────────────────────────────────────

async def test_symmetrie_kanon_eedc_service_mqtt(db, _patch):
    """Kanon == berechne_eedc_prognose (eedc-Spalte) == HA-Export „heute" (MQTT)."""
    from backend.services.prognose_kanon import kanon_tagesprognose
    from backend.services.eedc_prognose_service import berechne_eedc_prognose
    from backend.services.ha_export_prognose import berechne_prognose_export

    anlage = await _seed(db)
    kanon = await kanon_tagesprognose(db, anlage, days=4)
    eedc = await berechne_eedc_prognose(db, anlage, days=4)
    export = await berechne_prognose_export(db, anlage)

    assert kanon.tage[0].eedc_kwh == pytest.approx(eedc.tage[0].tageswert_kwh)
    assert export["heute_kwh"] == pytest.approx(kanon.tage[0].eedc_kwh)
    # Folgetage ebenfalls deckungsgleich.
    for off in (1, 2, 3):
        assert export[f"day_plus_{off}_kwh"] == pytest.approx(eedc.tage[off].tageswert_kwh)


async def test_eedc_ist_om_mal_skalar(db, _patch):
    """Uniformer Skalar 0.9 (keine Profile) → eedc_kwh == om_kwh × 0.9."""
    from backend.services.prognose_kanon import kanon_tagesprognose
    anlage = await _seed(db)
    kanon = await kanon_tagesprognose(db, anlage, days=4)
    t0 = kanon.tage[0]
    assert t0.om_kwh == pytest.approx(20.0, abs=0.2)  # 10 kWp × 2.0
    assert t0.eedc_kwh == pytest.approx(t0.om_kwh * 0.9, abs=0.1)


# ── Invariante Tageswert == Σ Export-Slots ───────────────────────────────────

async def test_invariante_tageswert_ist_summe_export_slots(db, _patch):
    from backend.services.prognose_kanon import kanon_tagesprognose
    anlage = await _seed(db)
    kanon = await kanon_tagesprognose(db, anlage, days=4)
    for tag in kanon.tage:
        if tag and tag.profil:
            assert tag.eedc_kwh == pytest.approx(
                sum(tag.profil.stundenprofil_export_kwh), abs=0.051
            )


# ── Multi-String Fan-out ─────────────────────────────────────────────────────

async def test_multistring_summe_der_gruppen(db, _patch):
    """2 Orientierungen (Süd 6 kWp + West 4 kWp): das Kanon-OM-Profil ist die
    slot-weise Summe der Einzel-Gruppen — NICHT eine gemittelte Orientierung."""
    from backend.services.prognose_kanon import kanon_tagesprognose
    anlage = await _seed(db, module=[(6.0, 0), (4.0, 90)])
    kanon = await kanon_tagesprognose(db, anlage, days=4)
    om = kanon.tage[0].om_stundenprofil_kwh

    erwartet = [
        round(_fake_slots(6.0, 0, 2.0)[h] + _fake_slots(4.0, 90, 2.0)[h], 3)
        for h in range(24)
    ]
    for h in range(24):
        assert om[h] == pytest.approx(erwartet[h], abs=0.01)

    # Regression-Guard: ein einzelner 10-kWp-Call @45° (gemittelte Orientierung)
    # hätte eine andere Kurvenform → der Fan-out darf NICHT kollabieren.
    single_avg = _fake_slots(10.0, 45, 2.0)
    assert any(abs(om[h] - single_avg[h]) > 0.05 for h in range(24))
    # Energieerhaltung: Tagessumme bleibt gleich (orientierungs-unabhängig).
    assert sum(om) == pytest.approx(20.0, abs=0.2)


async def test_multistring_unvollstaendig_markiert(db, _patch, monkeypatch):
    """#306: liefert eine Orientierungsgruppe keinen Forecast, ist der Tag als
    om_vollstaendig=False markiert (Persist-Pfad friert ihn dann nicht ein)."""
    import backend.services.solar_forecast_service as sfs

    async def fake_partial(**kwargs):
        # West-Gruppe (4 kWp) fällt aus → None.
        if kwargs["kwp"] == pytest.approx(4.0):
            return None
        return _fake_prognose(kwargs["kwp"], kwargs["ausrichtung"])

    monkeypatch.setattr(sfs, "get_solar_prognose", fake_partial)
    from backend.services.prognose_kanon import kanon_tagesprognose
    anlage = await _seed(db, module=[(6.0, 0), (4.0, 90)])
    kanon = await kanon_tagesprognose(db, anlage, days=4)
    assert kanon.tage[0].om_vollstaendig is False


# ── MQTT „Rest heute" ────────────────────────────────────────────────────────

async def test_mqtt_rest_heute_aus_kanon(db, _patch, monkeypatch):
    """„Rest heute" = Σ korrigierte Rest-Slots aus demselben Kanon wie „heute"."""
    import backend.services.prognose_kanon as kanon_mod

    class _FixedNoon(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime.combine(date.today(), dt_time(12, 0), tzinfo=tz)

    monkeypatch.setattr(kanon_mod, "datetime", _FixedNoon)
    from backend.services.ha_export_prognose import berechne_prognose_export
    anlage = await _seed(db)
    export = await berechne_prognose_export(db, anlage)

    # heute = volle Tagesprognose; rest = nur die Stunden nach 12:00 (>0, <heute).
    assert export["heute_kwh"] == pytest.approx(18.0, abs=0.3)
    assert 0.0 < export["rest_today_kwh"] < export["heute_kwh"]


# ── Rolling: zwei OM-Snapshots → alle Pfade ändern sich gleich ───────────────

async def test_rolling_zwei_snapshots(db, monkeypatch):
    import backend.services.solar_forecast_service as sfs
    import backend.api.routes.live_wetter as lw
    from backend.services.korrekturprofil_lookup import _cache
    from backend.services.prognose_kanon import kanon_tagesprognose
    from backend.services.ha_export_prognose import berechne_prognose_export

    async def fake_lernfaktor(anlage_id, db_, quelle="openmeteo"):
        return 0.9
    monkeypatch.setattr(lw, "_get_lernfaktor", fake_lernfaktor)

    anlage = await _seed(db)

    async def snapshot(faktor):
        async def fake(**kwargs):
            p = _fake_prognose(kwargs["kwp"], kwargs["ausrichtung"])
            for tag in p.tageswerte:
                tag.stunden_kw = [v * faktor for v in tag.stunden_kw]
                tag.pv_ertrag_kwh = round(sum(tag.stunden_kw), 3)
            return p
        monkeypatch.setattr(sfs, "get_solar_prognose", fake)
        _cache.clear()
        k = await kanon_tagesprognose(db, anlage, days=4)
        e = await berechne_prognose_export(db, anlage)
        return k.tage[0].eedc_kwh, e["heute_kwh"]

    a_kanon, a_mqtt = await snapshot(1.0)
    b_kanon, b_mqtt = await snapshot(1.3)  # OM steigt 30 %

    assert b_kanon > a_kanon
    # In jedem Snapshot ziehen Kanon und MQTT denselben Wert.
    assert a_mqtt == pytest.approx(a_kanon)
    assert b_mqtt == pytest.approx(b_kanon)
    # Und sie rollen GLEICH mit (≈ +30 %).
    assert b_kanon / a_kanon == pytest.approx(1.3, abs=0.02)


# ── §6 Konvergenz-Freeze ─────────────────────────────────────────────────────

def test_soll_final_einfrieren_pure():
    # Vor Sonnenuntergang: nie einfrieren (rollt).
    assert soll_final_einfrieren(forecast_kwh=20.0, sonne_unter=False) is False
    # Nach Sonnenuntergang ohne Archiv: einfrieren.
    assert soll_final_einfrieren(forecast_kwh=20.0, sonne_unter=True) is True
    # Mit Archiv: nur einfrieren, wenn konvergiert (|forecast − archiv| ≤ ε).
    assert soll_final_einfrieren(forecast_kwh=20.0, sonne_unter=True, archiv_kwh=20.3) is True
    assert soll_final_einfrieren(forecast_kwh=20.0, sonne_unter=True, archiv_kwh=30.0) is False
    # Kein Forecast → nichts zu fixieren.
    assert soll_final_einfrieren(forecast_kwh=None, sonne_unter=True) is False


async def test_persist_final_rollt_dann_gefroren(db, monkeypatch):
    """_speichere_prognose: final_kwh rollt vor SU mit, friert nach SU ein."""
    import backend.api.routes.live_wetter as lw
    from backend.models import TagesZusammenfassung
    from sqlalchemy import select

    @contextlib.asynccontextmanager
    async def fake_session():
        yield db
    monkeypatch.setattr("backend.core.database.get_session", fake_session)

    anlage = await _seed(db)
    heute = date.today()

    async def _tz():
        res = await db.execute(select(TagesZusammenfassung).where(
            TagesZusammenfassung.anlage_id == anlage.id,
            TagesZusammenfassung.datum == heute,
        ))
        return res.scalar_one()

    # 1) Vormittag: final rollt mit (noch nicht fix).
    await lw._speichere_prognose(anlage.id, heute, 18.0, pv_final_sonne_unter=False)
    tz = await _tz()
    assert tz.pv_prognose_final_kwh == pytest.approx(18.0)
    assert tz.pv_prognose_final_at is None

    # 2) Nachmittag-Korrektur (immer noch Tag): final zieht mit.
    await lw._speichere_prognose(anlage.id, heute, 21.0, pv_final_sonne_unter=False)
    tz = await _tz()
    assert tz.pv_prognose_final_kwh == pytest.approx(21.0)
    assert tz.pv_prognose_final_at is None

    # 3) Nach Sonnenuntergang: einfrieren.
    await lw._speichere_prognose(anlage.id, heute, 22.5, pv_final_sonne_unter=True)
    tz = await _tz()
    assert tz.pv_prognose_final_kwh == pytest.approx(22.5)
    assert tz.pv_prognose_final_at is not None

    # 4) Weiterer Abruf: final bleibt gefroren, Anzeige-Wert rollt weiter.
    await lw._speichere_prognose(anlage.id, heute, 30.0, pv_final_sonne_unter=True)
    tz = await _tz()
    assert tz.pv_prognose_final_kwh == pytest.approx(22.5)   # gefroren
    assert tz.pv_prognose_kwh == pytest.approx(30.0)         # Anzeige rollt


async def test_genauigkeit_liest_final_wert(db, _patch):
    """Genauigkeits-Ranking nutzt pv_prognose_final_kwh (Fallback rollend)."""
    from backend.models import TagesZusammenfassung
    from backend.api.routes.prognosen import get_prognosen_genauigkeit

    anlage = await _seed(db)
    vortag = date.today() - timedelta(days=2)
    db.add(TagesZusammenfassung(
        anlage_id=anlage.id, datum=vortag,
        pv_prognose_kwh=10.0,           # rollender Zwischenstand
        pv_prognose_final_kwh=14.0,     # konvergenz-gefrorener Endwert
        pv_prognose_final_at="2026-06-26T21:00:00+02:00",
        komponenten_kwh={"pv_1": 15.0},  # IST
    ))
    await db.flush()

    resp = await get_prognosen_genauigkeit(anlage.id, tage=30, db=db)
    eintrag = next(e for e in resp.tage if e.datum == vortag.isoformat())
    # openmeteo_kwh spiegelt den Endwert (14.0), NICHT den rollenden 10.0.
    assert eintrag.openmeteo_kwh == pytest.approx(14.0)
    assert eintrag.ist_kwh == pytest.approx(15.0)
