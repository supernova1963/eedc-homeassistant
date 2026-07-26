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
from backend.models import Anlage, Investition, Monatsdaten, TagesEnergieProfil


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


def _fake_tag(datum_iso: str, kwp: float, ausrichtung: int, tagesfaktor: float):
    """Ein Prognose-Tag mit allen Feldern, die `SolarPrognoseTag` trägt — der
    `/solar-prognose`-Endpoint (Multi-String-Aggregation) liest auch die
    Wetter-/GTI-Felder, nicht nur den Ertrag."""
    slots = _fake_slots(kwp, ausrichtung, tagesfaktor)
    return SimpleNamespace(
        datum=datum_iso,
        pv_ertrag_kwh=round(sum(slots), 3),
        stunden_kw=slots,
        stunden_bewoelkung=[0.0] * 24,
        stunden_niederschlag=[0.0] * 24,
        stunden_wetter_code=[0] * 24,
        gti_kwh_m2=round(sum(slots) / max(kwp, 0.001), 3),
        ghi_kwh_m2=0.0,
        sonnenstunden=8.0,
        temperatur_max_c=22.0,
        temperatur_min_c=12.0,
        bewoelkung_prozent=10,
        niederschlag_mm=0.0,
        schnee_cm=0.0,
        wetter_symbol="sunny",
        pv_ertrag_morgens_kwh=round(sum(slots[:13]), 3),
        pv_ertrag_nachmittags_kwh=round(sum(slots[13:]), 3),
        datenquelle="best_match",
    )


def _fake_prognose(kwp: float, ausrichtung: int, days: int | None = None):
    heute = date.today()
    faktoren = _TAGESFAKTOREN if days is None else [
        _TAGESFAKTOREN[i % len(_TAGESFAKTOREN)] for i in range(days)
    ]
    tage = [
        _fake_tag((heute + timedelta(days=i)).isoformat(), kwp, ausrichtung, tf)
        for i, tf in enumerate(faktoren)
    ]
    summe = sum(t.pv_ertrag_kwh for t in tage)
    return SimpleNamespace(
        tageswerte=tage,
        kwp_gesamt=kwp,
        neigung=35,
        ausrichtung=ausrichtung,
        system_losses_prozent=14.0,
        prognose_zeitraum={"von": tage[0].datum, "bis": tage[-1].datum},
        summe_kwh=round(summe, 1),
        durchschnitt_kwh_tag=round(summe / len(tage), 2),
        datenquelle="Best Match",
        abgerufen_am="2026-07-26T06:00:00",
    )


@pytest.fixture
def _patch(monkeypatch):
    """Patcht OpenMeteo + Lernfaktor; Skalar 0.9, keine Stunden-Profile."""
    import backend.services.solar_forecast_service as sfs
    import backend.api.routes.live_wetter as lw
    from backend.services.korrekturprofil_lookup import _cache

    async def fake_get_solar_prognose(**kwargs):
        return _fake_prognose(kwargs["kwp"], kwargs["ausrichtung"], kwargs.get("days"))

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


async def _seed_verbrauchsprofil(db, anlage_id: int, tage: int = 6) -> None:
    """24 Stundenzeilen je Tag — ohne mindestens 3 vollständige Tage antwortet
    ``/tagesprognose`` mit 422 (Verbrauchsprognose). Für den PV-Wert irrelevant."""
    heute = date.today()
    for d in range(1, tage + 1):
        for stunde in range(24):
            db.add(TagesEnergieProfil(
                anlage_id=anlage_id, datum=heute - timedelta(days=d),
                stunde=stunde, verbrauch_kw=0.4,
            ))
    await db.flush()


@pytest.fixture
def _keine_netzabrufe(monkeypatch):
    """Der Prognosen-Vergleich holt neben dem Kanon eigene OpenMeteo-/Solcast-
    Daten (Wetter-Tabelle, GTI-Roh-Kurve, Solcast-Spalte). Im Test hermetisch
    auf ``None`` — der Endpoint liefert dann die Kanon-Spalten, um die es hier
    geht, und der Test braucht kein Netz."""
    import backend.api.routes.prognosen as pr

    async def _none(*args, **kwargs):
        return None

    monkeypatch.setattr(pr, "fetch_open_meteo_forecast", _none)
    monkeypatch.setattr(pr, "fetch_gti_forecast", _none)
    monkeypatch.setattr(pr, "get_solcast_forecast", _none)


async def test_symmetrie_morgen_tagesprognose_vergleich_mqtt(db, _patch, _keine_netzabrufe):
    """„Morgen" über alle Kanon-Pfade: Σ Stundenprofil der /tagesprognose ==
    eedc-Morgenwert im Prognosen-Vergleich == MQTT ``day_plus_1_kwh``.

    Rainer-PN „Nachtrag" 2026-07-25: die Summenzeile der Stundenwerte zeigte
    einen anderen Tageswert als die übrigen Anzeigen, weil sie über einen
    eigenen Ein-Abruf-Pfad lief. Ohne diesen Test driftet „morgen" wieder weg
    ([[feedback_aggregator_symmetrie]] — bisher war nur ``tage[0]`` gedeckt).
    """
    from backend.api.routes.energie_profil.views import get_tagesprognose
    from backend.api.routes.prognosen import get_prognosen_vergleich
    from backend.api.routes.solar_prognose import get_solar_prognose_endpoint
    from backend.services.ha_export_prognose import berechne_prognose_export
    from backend.services.prognose_kanon import kanon_tagesprognose

    anlage = await _seed(db, module=[(6.0, 0), (4.0, 90)])
    await _seed_verbrauchsprofil(db, anlage.id)
    morgen = date.today() + timedelta(days=1)

    resp = await get_tagesprognose(anlage.id, datum=morgen, db=db)
    vergleich = await get_prognosen_vergleich(anlage.id, db=db)
    export = await berechne_prognose_export(db, anlage)
    kanon = await kanon_tagesprognose(db, anlage, days=4)

    morgen_kanon = kanon.tage[1].eedc_kwh
    assert vergleich.eedc_morgen_kwh == pytest.approx(morgen_kanon)
    assert export["day_plus_1_kwh"] == pytest.approx(morgen_kanon)

    # Die Summenzeile selbst (das ist die Zahl aus Rainers Meldung) — der
    # Tageswert des Kanon ist auf 1 NK gerundet, die Summenzeile auf 2.
    assert resp.pv_summe_kwh == pytest.approx(morgen_kanon, abs=0.05)
    # … und sie ist wirklich die Summe der angezeigten Stundenwerte.
    assert sum(s.pv_kw for s in resp.stunden) == pytest.approx(resp.pv_summe_kwh, abs=0.005)
    # Slot für Slot deckungsgleich mit dem MQTT-Attribut `stundenprofil_kwh`.
    assert [s.pv_kw for s in resp.stunden] == pytest.approx(export["stundenprofil_day_plus_1"])

    # Die VIERTE Zahl auf der Seite: der 14-Tage-Balken für denselben Tag
    # (Rainers eigentliche Meldung — 13 kWh im Balken gegen 10,8 kWh in der
    # Summenzeile darunter). `tageswerte[1]` ist Tag 2 = morgen.
    solar = await get_solar_prognose_endpoint(anlage.id, tage=14, db=db)
    balken_morgen = solar.tageswerte[1]
    assert balken_morgen.datum == morgen.isoformat()
    assert balken_morgen.eedc_kwh == pytest.approx(morgen_kanon)
    # Der OpenMeteo-Rohwert bleibt erhalten (Basis der Korrektur, „OpenMeteo"-
    # Spalte im Vergleich) — er wird ergänzt, nicht ersetzt, und liegt hier
    # sichtbar höher als der korrigierte Wert (Lernfaktor 0,9).
    assert balken_morgen.pv_ertrag_kwh > balken_morgen.eedc_kwh
    assert solar.anzeige_quelle == "eedc"


async def test_solar_prognose_aggregate_passen_zu_den_balken(db, _patch):
    """Σ/Ø der Response == Σ/Ø der angezeigten Tageswerte.

    Ohne das zeigte die Block-Zusammenfassung weiter die OpenMeteo-Summe,
    während die Balken darunter eedc-Werte tragen — dieselbe Widersprüchlichkeit
    wie vorher, nur an anderer Stelle.
    """
    from backend.api.routes.solar_prognose import get_solar_prognose_endpoint

    anlage = await _seed(db, module=[(6.0, 0), (4.0, 90)])
    solar = await get_solar_prognose_endpoint(anlage.id, tage=14, db=db)

    angezeigt = [t.eedc_kwh if t.eedc_kwh is not None else t.pv_ertrag_kwh
                 for t in solar.tageswerte]
    assert solar.eedc_summe_kwh == pytest.approx(sum(angezeigt), abs=0.05)
    assert solar.eedc_durchschnitt_kwh_tag == pytest.approx(
        sum(angezeigt) / len(angezeigt), abs=0.01
    )
    # Roh-Aggregate bleiben unangetastet und liegen höher (Lernfaktor 0,9).
    assert solar.summe_kwh > solar.eedc_summe_kwh
    # VM/NM ziehen mit, sonst summierten Hälften und Tageswert nicht mehr auf.
    for t in solar.tageswerte:
        if t.eedc_morgens_kwh is not None:
            assert t.eedc_morgens_kwh + t.eedc_nachmittags_kwh == pytest.approx(
                t.eedc_kwh, abs=0.15
            )


async def test_solar_prognose_faellt_auf_openmeteo_zurueck(db, monkeypatch):
    """Kein Kanon-Ergebnis → Rohwerte bleiben, `anzeige_quelle` sagt es ehrlich.

    Fallback ist erlaubt, stumm falsch beschriftet nicht: steht in der Anzeige
    der OpenMeteo-Wert, darf nicht „eedc" darüberstehen.
    """
    import backend.api.routes.solar_prognose as sp
    import backend.services.solar_forecast_service as sfs
    from backend.api.routes.solar_prognose import get_solar_prognose_endpoint

    async def fake_get_solar_prognose(**kwargs):
        return _fake_prognose(kwargs["kwp"], kwargs["ausrichtung"], kwargs.get("days"))

    async def kein_kanon(*args, **kwargs):
        return None

    monkeypatch.setattr(sfs, "get_solar_prognose", fake_get_solar_prognose)
    monkeypatch.setattr(sp, "kanon_tagesprognose", kein_kanon)

    anlage = await _seed(db, module=[(6.0, 0), (4.0, 90)])
    solar = await get_solar_prognose_endpoint(anlage.id, tage=7, db=db)

    assert solar.anzeige_quelle == "openmeteo"
    assert solar.eedc_summe_kwh is None
    assert all(t.eedc_kwh is None for t in solar.tageswerte)
    assert all(t.pv_ertrag_kwh > 0 for t in solar.tageswerte)


async def test_solar_prognose_schreibt_keinen_day_ahead_snapshot(db, _patch):
    """Nachweis: der Anzeige-Pfad fasst den Lern-Snapshot NICHT an.

    `TagesZusammenfassung.pv_prognose_kwh`/`pv_prognose_stundenprofil` sind der
    Day-Ahead-Forecast, aus dem das Korrekturprofil lernt. Ein korrigierter Wert
    dort wäre eine Rückkopplung (Korrektur lernt auf Korrektur). Geschrieben
    wird er ausschließlich im Scheduler-/Live-Pfad mit OpenMeteo-Rohwerten.
    """
    from sqlalchemy import select
    from backend.api.routes.solar_prognose import get_solar_prognose_endpoint
    from backend.models import TagesZusammenfassung

    anlage = await _seed(db, module=[(6.0, 0), (4.0, 90)])
    await get_solar_prognose_endpoint(anlage.id, tage=14, db=db)
    await db.flush()

    rows = (await db.execute(
        select(TagesZusammenfassung).where(TagesZusammenfassung.anlage_id == anlage.id)
    )).scalars().all()
    assert rows == []


async def test_morgen_ohne_orientierungs_kollaps(db, monkeypatch):
    """Regression: /tagesprognose holte OpenMeteo mit EINEM Abruf über die
    Gesamt-kWp und der Orientierung der zufällig ersten Investition. Bei einer
    Anlage mit ertragsschwächerem Ost-Dach liegt dieser Wert deutlich daneben.
    """
    import backend.services.solar_forecast_service as sfs
    import backend.api.routes.live_wetter as lw
    from backend.services.korrekturprofil_lookup import _cache
    from backend.api.routes.energie_profil.views import get_tagesprognose

    async def fake_ost_schwaecher(**kwargs):
        # Ost-Dach (Azimut < 0) liefert 70 % der Süd-Energie.
        faktor = 0.7 if kwargs["ausrichtung"] < 0 else 1.0
        p = _fake_prognose(kwargs["kwp"], kwargs["ausrichtung"])
        for tag in p.tageswerte:
            tag.stunden_kw = [v * faktor for v in tag.stunden_kw]
            tag.pv_ertrag_kwh = round(sum(tag.stunden_kw), 3)
        return p

    async def fake_lernfaktor(anlage_id, db_, quelle="openmeteo"):
        return 0.9

    monkeypatch.setattr(sfs, "get_solar_prognose", fake_ost_schwaecher)
    monkeypatch.setattr(lw, "_get_lernfaktor", fake_lernfaktor)
    _cache.clear()

    anlage = await _seed(db, module=[(6.0, 0), (4.0, -90)])  # 6 Süd + 4 Ost
    await _seed_verbrauchsprofil(db, anlage.id)
    morgen = date.today() + timedelta(days=1)

    resp = await get_tagesprognose(anlage.id, datum=morgen, db=db)

    tf = _TAGESFAKTOREN[1]  # morgen
    fan_out = (6.0 * tf + 4.0 * tf * 0.7) * 0.9      # Multi-String (richtig)
    kollaps = 10.0 * tf * 0.9                        # EIN Abruf, Orientierung invs[0]
    assert resp.pv_summe_kwh == pytest.approx(fan_out, abs=0.1)
    assert abs(resp.pv_summe_kwh - kollaps) > 1.0


async def test_tagesprognose_ferner_tag_bleibt_im_kanon(db, monkeypatch):
    """Der Datums-Picker erlaubt +14 Tage. ``days`` wird aus dem Zieldatum
    abgeleitet (hier 15, OpenMeteo-Maximum ist 16) — auch ferne Tage rechnen
    kanonisch, statt still auf den Ein-Abruf-Pfad zurückzufallen. Kosten: ein
    OpenMeteo-Abruf **pro Orientierungsgruppe** (parallel, eigener Cache-Key).
    """
    import backend.services.solar_forecast_service as sfs
    import backend.api.routes.live_wetter as lw
    from backend.services.korrekturprofil_lookup import _cache
    from backend.api.routes.energie_profil.views import get_tagesprognose

    calls: list[tuple] = []

    async def fake_langer_horizont(**kwargs):
        calls.append((kwargs["kwp"], kwargs["ausrichtung"], kwargs["days"]))
        heute = date.today()
        tage = []
        for i in range(kwargs["days"]):
            slots = _fake_slots(kwargs["kwp"], kwargs["ausrichtung"], 1.5)
            tage.append(SimpleNamespace(
                datum=(heute + timedelta(days=i)).isoformat(),
                pv_ertrag_kwh=round(sum(slots), 3),
                stunden_kw=slots,
                stunden_bewoelkung=[0.0] * 24,
                stunden_niederschlag=[0.0] * 24,
                stunden_wetter_code=[0] * 24,
            ))
        return SimpleNamespace(tageswerte=tage)

    async def fake_lernfaktor(anlage_id, db_, quelle="openmeteo"):
        return 0.9

    monkeypatch.setattr(sfs, "get_solar_prognose", fake_langer_horizont)
    monkeypatch.setattr(lw, "_get_lernfaktor", fake_lernfaktor)
    _cache.clear()

    anlage = await _seed(db, module=[(6.0, 0), (4.0, 90)])
    await _seed_verbrauchsprofil(db, anlage.id)
    ziel = date.today() + timedelta(days=14)

    resp = await get_tagesprognose(anlage.id, datum=ziel, db=db)

    assert resp.pv_summe_kwh == pytest.approx(10.0 * 1.5 * 0.9, abs=0.1)
    # Zwei Orientierungsgruppen → zwei Abrufe, beide über den vollen Horizont.
    assert [c[2] for c in calls] == [15, 15]


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


async def test_stilllegung_im_horizont_wirkt_ab_dem_tag(db, _patch):
    """N31: Anschaffung/Stilllegung werden gegen das jeweilige TAGESDATUM
    geprüft, nicht gegen heute.

    Vorher filterte der Kanon einmalig gegen `heute` — ein am Tag +2
    stillgelegter String zählte im ganzen Prognosehorizont weiter mit und die
    Prognose lag ab diesem Tag zu hoch. Betroffen sind ausschließlich Anlagen
    mit einem Stilllegungs-/Anschaffungsdatum in der Zukunft; der Fix sitzt im
    Kanon und wirkt damit auch auf den HA-/MQTT-Export.
    """
    from backend.services.prognose_kanon import kanon_tagesprognose
    from backend.models import Investition

    heute = date.today()
    anlage = await _seed(db, module=[(6.0, 0)])
    # Zweiter String, stillgelegt am Tag +2 (inklusiv: an diesem Tag noch aktiv).
    db.add(Investition(
        anlage_id=anlage.id, typ="pv-module", bezeichnung="West (Rückbau)",
        leistung_kwp=4.0, neigung_grad=35,
        anschaffungsdatum=date(2024, 1, 1),
        stilllegungsdatum=heute + timedelta(days=2),
        parameter={"ausrichtung_grad": 90},
    ))
    await db.flush()

    kanon = await kanon_tagesprognose(db, anlage, days=4)

    # Tag 0..2: beide Strings (10 kWp) — Tag 3: nur noch Süd (6 kWp).
    for offset in (0, 1, 2):
        assert kanon.tage[offset].om_kwh == pytest.approx(
            10.0 * _TAGESFAKTOREN[offset], abs=0.2
        ), f"Tag {offset} sollte beide Strings tragen"
    assert kanon.tage[3].om_kwh == pytest.approx(6.0 * _TAGESFAKTOREN[3], abs=0.2)
    # Der Tageswert ist echt gesunken (nicht nur gerundet).
    assert kanon.tage[3].om_kwh < 10.0 * _TAGESFAKTOREN[3] - 1.0
    # Auch das Stundenprofil trägt nur noch den Süd-String.
    assert sum(kanon.tage[3].om_stundenprofil_kwh) == pytest.approx(
        6.0 * _TAGESFAKTOREN[3], abs=0.2
    )


async def test_anschaffung_im_horizont_zaehlt_erst_ab_dem_tag(db, _patch):
    """Gegenstück zu N31: ein erst in zwei Tagen angeschaffter String zählt
    heute noch nicht mit (vorher prüfte der Kanon das Anschaffungsdatum gar
    nicht — [[feedback_anschaffungsdatum_grenze]])."""
    from backend.services.prognose_kanon import kanon_tagesprognose
    from backend.models import Investition

    heute = date.today()
    anlage = await _seed(db, module=[(6.0, 0)])
    db.add(Investition(
        anlage_id=anlage.id, typ="pv-module", bezeichnung="West (Erweiterung)",
        leistung_kwp=4.0, neigung_grad=35,
        anschaffungsdatum=heute + timedelta(days=2),
        parameter={"ausrichtung_grad": 90},
    ))
    await db.flush()

    kanon = await kanon_tagesprognose(db, anlage, days=4)

    assert kanon.tage[0].om_kwh == pytest.approx(6.0 * _TAGESFAKTOREN[0], abs=0.2)
    assert kanon.tage[1].om_kwh == pytest.approx(6.0 * _TAGESFAKTOREN[1], abs=0.2)
    assert kanon.tage[2].om_kwh == pytest.approx(10.0 * _TAGESFAKTOREN[2], abs=0.2)
    assert kanon.tage[3].om_kwh == pytest.approx(10.0 * _TAGESFAKTOREN[3], abs=0.2)


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
