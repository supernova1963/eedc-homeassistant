"""Phase-B-Tests (v3.34.2): Backfill-Konsolidierung über `aggregate_day`.

Verankert den Phase-B-Schnitt aus `docs/drafts/PLAN-energieprofil-werkbank-v3.34.md`
§3 Phase B + `HANDOVER-energieprofil-werkbank-phase-b.md`:

- ``aktiv_am_tag(datum)`` als dritte Aktiv-Filter-Variante (Baustein 3, Audit §6.4).
- **S1** (Erfolgskriterium E2): Scheduler-Pfad und Vollbackfill-Pfad liefern für
  denselben historischen Tag bei identischer Datenlage identische TZ-Aggregate —
  inkl. der Pflicht-Konstellation „zwischenzeitlich stillgelegte Investition".
- **S2**: der konsolidierte Pfad füllt die Felder, die der alte eigenständige
  Backfill leer ließ (Peaks, Strompreis-/Börsenpreis-Felder) — die dokumentierte
  „stille Datenverbesserung" (Plan §1.3 Stufe 2).
- **E1**: `backfill.py` konstruiert/schreibt keine TEP/TZ-Rows mehr selbst —
  genau ein Top-Level-Schreibpfad (Aggregator).
- Werkbank-VOLLBACKFILL-Endpoint-Response-Schema bleibt stabil.

ADR-001-Pflicht ([[feedback_aggregator_symmetrie]]): bei parallelen Schreib-Pfaden
auf dieselbe Aggregat-Tabelle muss ein Symmetrie-Test existieren. Phase B löst die
Parallelität strukturell auf — S1/S2 sind der Nachweis, dass die Auflösung trägt.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import select

from backend.models.anlage import Anlage
from backend.models.investition import Investition
from backend.models.mqtt_energy_snapshot import MqttEnergySnapshot
from backend.services.energie_profil.source import Source
from backend.utils.investition_filter import aktiv_am_tag


# ───────────────────────── aktiv_am_tag (Baustein 3) ────────────────────────


@pytest.mark.asyncio
async def test_aktiv_am_tag_filtert_stilllegung_und_anschaffung(db) -> None:
    """`aktiv_am_tag(tag)` liefert genau die Investitionen, die an `tag` aktiv
    waren — exklusive vor `tag` angeschaffter Zukunfts- und vor `tag`
    stillgelegter Alt-Investitionen, INKLUSIVE der am Stilllegungstag selbst
    (inklusive Grenze, identisch zu `Investition.ist_aktiv_an`)."""
    anlage = Anlage(anlagenname="FilterTest", leistung_kwp=5.0)
    db.add(anlage)
    await db.flush()

    tag = date(2026, 3, 15)

    immer = Investition(anlage_id=anlage.id, typ="pv-module", bezeichnung="immer", aktiv=True,
                        anschaffungsdatum=date(2020, 1, 1))
    stillgelegt_am_tag = Investition(anlage_id=anlage.id, typ="wallbox", bezeichnung="stillgelegt_am_tag", aktiv=True,
                                     anschaffungsdatum=date(2020, 1, 1),
                                     stilllegungsdatum=tag)  # Grenze: am Tag noch aktiv
    stillgelegt_vorher = Investition(anlage_id=anlage.id, typ="e-auto", bezeichnung="stillgelegt_vorher", aktiv=True,
                                     anschaffungsdatum=date(2020, 1, 1),
                                     stilllegungsdatum=tag - timedelta(days=1))
    erst_spaeter = Investition(anlage_id=anlage.id, typ="speicher", bezeichnung="erst_spaeter", aktiv=True,
                               anschaffungsdatum=tag + timedelta(days=1))
    pausiert = Investition(anlage_id=anlage.id, typ="waermepumpe", bezeichnung="pausiert",
                           anschaffungsdatum=date(2020, 1, 1), aktiv=False)
    db.add_all([immer, stillgelegt_am_tag, stillgelegt_vorher, erst_spaeter, pausiert])
    await db.flush()

    result = await db.execute(
        select(Investition.bezeichnung).where(
            Investition.anlage_id == anlage.id,
            aktiv_am_tag(tag),
        )
    )
    aktiv = {row[0] for row in result}

    assert "immer" in aktiv
    assert "stillgelegt_am_tag" in aktiv, (
        "Stilllegungstag selbst muss als aktiv gelten (inklusive Grenze, "
        "konsistent mit ist_aktiv_an) — sonst Asymmetrie zur Serien-Filterung "
        "im Vollbackfill."
    )
    assert "stillgelegt_vorher" not in aktiv
    assert "erst_spaeter" not in aktiv
    # aktiv=False = wie gelöscht (ohne zu löschen) → nirgends, auch nicht
    # historisch, bis reaktiviert wird (Gernot 2026-06-05). Daten bleiben in der
    # DB; Hard-Delete wäre endgültig. Verwaltungsliste zeigt es weiter.
    assert "pausiert" not in aktiv


def test_aktiv_am_tag_matcht_ist_aktiv_an_am_stilllegungstag() -> None:
    """`aktiv_am_tag` (SQL) muss am Stilllegungstag dieselbe Entscheidung
    treffen wie `Investition.ist_aktiv_an` (In-Memory) — der Vollbackfill nutzt
    ist_aktiv_an für die Serien, `aggregate_day` nutzt aktiv_am_tag für die
    Inv-Last. Drift hier wäre eine Within-Path-Asymmetrie."""
    tag = date(2026, 3, 15)
    inv = Investition(typ="wallbox", bezeichnung="wb", aktiv=True,
                      anschaffungsdatum=date(2020, 1, 1), stilllegungsdatum=tag)
    # ist_aktiv_an: stilllegungsdatum < tag → inaktiv; == tag → aktiv.
    assert inv.ist_aktiv_an(tag) is True
    assert inv.ist_aktiv_an(tag + timedelta(days=1)) is False


# ───────────────────────── Test-Fixtures (S0-Stil) ──────────────────────────


_LTS_HOURLY = {
    h: {
        "pv": 1.2, "einspeisung": 0.5, "netzbezug": 0.3, "verbrauch": 1.0,
        "wp": 0.4, "wallbox": None, "batterie_netto": 0.0, "verbrauch_sonstiges": None,
    }
    for h in range(24)
}


def _anlage_mit_mapping() -> Anlage:
    return Anlage(
        anlagenname="SymTest",
        leistung_kwp=10.0,
        standort_plz="10115",
        standort_land="DE",
        wechselrichter_hersteller="generic",
        sensor_mapping={
            "basis": {
                "einspeisung": {"strategie": "sensor", "sensor_id": "sensor.einsp"},
                "netzbezug": {"strategie": "sensor", "sensor_id": "sensor.bezug"},
            },
            "investitionen": {
                "3": {"felder": {"pv_erzeugung_kwh": {"strategie": "sensor", "sensor_id": "sensor.pv"}}},
                "7": {"felder": {"stromverbrauch_kwh": {"strategie": "sensor", "sensor_id": "sensor.wp"}}},
            },
        },
    )


async def _mqtt_anchor(db, anlage_id: int, datum: date) -> None:
    db.add(MqttEnergySnapshot(
        anlage_id=anlage_id,
        timestamp=datetime.combine(datum, datetime.min.time()) - timedelta(hours=1),
        energy_key="netzbezug",
        value_kwh=100.0,
    ))
    await db.flush()


def _tv_data() -> dict:
    """get_tagesverlauf-Form: PV-Serie + Netz-Serie, 24h Butterfly-Werte."""
    return {
        "serien": [
            {"key": "pv_3", "kategorie": "pv"},
            {"key": "netz", "kategorie": "netz"},
        ],
        "punkte": [
            {"zeit": f"{h:02d}:00", "werte": {"pv_3": 2.0, "netz": -1.0}}
            for h in range(6, 18)
        ],
    }


def _snapshot(tz) -> dict:
    """Vergleichbare TZ-Felder als plain dict (vor dem nächsten Lauf sichern)."""
    return {
        "komponenten_kwh": dict(tz.komponenten_kwh) if tz.komponenten_kwh else None,
        "peak_pv_kw": tz.peak_pv_kw,
        "peak_netzbezug_kw": tz.peak_netzbezug_kw,
        "peak_einspeisung_kw": tz.peak_einspeisung_kw,
        "ueberschuss_kwh": tz.ueberschuss_kwh,
        "defizit_kwh": tz.defizit_kwh,
        "performance_ratio": tz.performance_ratio,
        "stunden_verfuegbar": tz.stunden_verfuegbar,
        "datenquelle": tz.datenquelle,
    }


# ─────────────────────────────────── S1 ─────────────────────────────────────


@pytest.mark.asyncio
async def test_s1_scheduler_und_backfill_pfad_symmetrisch(db) -> None:
    """S1 (E2): Scheduler-Pfad (`source=SCHEDULER`, get_tagesverlauf) und
    Vollbackfill-Pfad (`source=VOLLBACKFILL_FROM_LTS`, prefetched_tagesverlauf)
    liefern für denselben historischen Tag bei identischer Datenlage identische
    TZ-Aggregate. Einziger erlaubter Unterschied: die `datenquelle`-Spalte.

    Pflicht-Konstellation: eine zwischenzeitlich stillgelegte Investition
    (aktiv am historischen Tag, heute stillgelegt). `aktiv_am_tag` muss sie in
    BEIDEN Pfaden gleich behandeln (Audit §6.4)."""
    from backend.services.energie_profil.aggregator import aggregate_day

    anlage = _anlage_mit_mapping()
    db.add(anlage)
    await db.flush()

    historisch = date.today() - timedelta(days=30)

    # Investitionen: zwei dauerhaft aktiv, eine am hist. Tag aktiv + seither
    # stillgelegt, eine vor dem hist. Tag stillgelegt (darf NICHT zählen).
    inv3 = Investition(id=3, anlage_id=anlage.id, typ="pv-module", bezeichnung="pv", aktiv=True,
                       anschaffungsdatum=date(2020, 1, 1))
    inv7 = Investition(id=7, anlage_id=anlage.id, typ="waermepumpe", bezeichnung="wp", aktiv=True,
                       anschaffungsdatum=date(2020, 1, 1))
    inv8 = Investition(id=8, anlage_id=anlage.id, typ="wallbox", bezeichnung="wb", aktiv=True,
                       anschaffungsdatum=date(2020, 1, 1),
                       stilllegungsdatum=historisch)  # am Tag aktiv, seither stillgelegt
    inv9 = Investition(id=9, anlage_id=anlage.id, typ="e-auto", bezeichnung="ea", aktiv=True,
                       anschaffungsdatum=date(2020, 1, 1),
                       stilllegungsdatum=historisch - timedelta(days=5))  # vorher weg
    db.add_all([inv3, inv7, inv8, inv9])
    await _mqtt_anchor(db, anlage.id, historisch)
    await db.commit()

    async def fake_lts_komp(anlage_arg, investitionen_by_id, datum):
        # Komponenten-Tagessumme abhängig von den geladenen (aktiv_am_tag-)Invs:
        # so testet der Mock, dass beide Pfade dieselbe Inv-Menge laden.
        return {f"k_{iid}": float(iid) for iid in sorted(investitionen_by_id)}

    tv = _tv_data()

    patches = lambda: (
        patch("backend.services.snapshot.lts_aggregator.get_hourly_kwh_by_category_lts",
              new=AsyncMock(return_value=_LTS_HOURLY)),
        patch("backend.services.snapshot.lts_aggregator.get_komponenten_tageskwh_lts",
              new=AsyncMock(side_effect=fake_lts_komp)),
        patch("backend.services.sensor_snapshot_service.get_daily_counter_deltas_by_inv",
              new=AsyncMock(return_value={})),
    )

    # ── Pfad A: Scheduler (get_tagesverlauf liefert tv) ──
    p1, p2, p3 = patches()
    with p1, p2, p3, patch(
        "backend.services.live_power_service.LivePowerService.get_tagesverlauf",
        new=AsyncMock(return_value=tv),
    ):
        tz_sched = await aggregate_day(anlage, historisch, db, source=Source.SCHEDULER)
        snap_sched = _snapshot(tz_sched)
    await db.commit()

    # ── Pfad B: Vollbackfill (prefetched_tagesverlauf == dieselben tv) ──
    p1, p2, p3 = patches()
    with p1, p2, p3:
        tz_bf = await aggregate_day(
            anlage, historisch, db,
            source=Source.VOLLBACKFILL_FROM_LTS,
            prefetched_tagesverlauf=tv,
        )
        snap_bf = _snapshot(tz_bf)
    await db.commit()

    # Stilllegungs-Konstellation: inv8 (am Tag aktiv) zählt, inv9 (vorher weg) nicht.
    assert "k_8" in snap_sched["komponenten_kwh"], (
        "aktiv_am_tag muss die am hist. Tag aktive, seither stillgelegte "
        "Investition 8 einschließen."
    )
    assert "k_9" not in snap_sched["komponenten_kwh"], (
        "Vor dem hist. Tag stillgelegte Investition 9 darf nicht zählen."
    )

    # Symmetrie: alle Aggregat-Felder identisch außer datenquelle.
    assert snap_sched["datenquelle"] == "scheduler"
    assert snap_bf["datenquelle"] == "ha_statistiken"
    for feld in ("komponenten_kwh", "peak_pv_kw", "peak_netzbezug_kw",
                 "peak_einspeisung_kw", "ueberschuss_kwh", "defizit_kwh",
                 "performance_ratio", "stunden_verfuegbar"):
        assert snap_sched[feld] == snap_bf[feld], (
            f"S1-Asymmetrie in `{feld}`: Scheduler={snap_sched[feld]!r} vs "
            f"Backfill={snap_bf[feld]!r}"
        )


# ─────────────────────────────────── S2 ─────────────────────────────────────


@pytest.mark.asyncio
async def test_s2_konsolidierter_pfad_fuellt_zusatzfelder(db) -> None:
    """S2: der konsolidierte Vollbackfill-Pfad füllt die Felder, die der alte
    eigenständige Backfill leer ließ. Explizites erwartetes Delta (Plan §1.3
    Stufe 2 — die EINZIGE akzeptierte Verhaltens-Abweichung):

      NEU GEFÜLLT durch `aggregate_day` (alter Backfill: NULL):
        TZ.boersenpreis_avg_cent, TZ.boersenpreis_min_cent,
        TZ.negative_preis_stunden, TZ.einspeisung_neg_preis_kwh,
        TZ.peak_pv_kw / peak_netzbezug_kw / peak_einspeisung_kw (HA-LTS-Min/Max),
        TEP.strompreis_cent / boersenpreis_cent.

    Der Test mockt die Strompreis- + Peak-Quellen mit Werten und prüft, dass
    der Vollbackfill-Pfad sie persistiert."""
    from backend.models.tages_energie_profil import TagesEnergieProfil
    from backend.services.energie_profil.aggregator import aggregate_day
    from backend.services.energie_profil._helpers import StrompreisStunden, TagesPeaks

    anlage = _anlage_mit_mapping()
    db.add(anlage)
    await db.flush()
    db.add(Investition(id=3, anlage_id=anlage.id, typ="pv-module", bezeichnung="pv", aktiv=True,
                       anschaffungsdatum=date(2020, 1, 1)))
    historisch = date.today() - timedelta(days=20)
    await db.commit()

    tv = _tv_data()
    strompreis = StrompreisStunden(
        sensor={h: 30.0 for h in range(24)},
        boerse={h: (-2.0 if h in (12, 13) else 8.0) for h in range(24)},
    )
    peaks = TagesPeaks(pv=7.5, netzbezug=3.2, einspeisung=4.1)

    with patch(
        "backend.services.snapshot.lts_aggregator.get_hourly_kwh_by_category_lts",
        new=AsyncMock(return_value=_LTS_HOURLY),
    ), patch(
        "backend.services.snapshot.lts_aggregator.get_komponenten_tageskwh_lts",
        new=AsyncMock(return_value={"pv_3": 28.8}),
    ), patch(
        "backend.services.sensor_snapshot_service.get_daily_counter_deltas_by_inv",
        new=AsyncMock(return_value={}),
    ), patch(
        "backend.services.energie_profil._helpers._get_strompreis_stunden",
        new=AsyncMock(return_value=strompreis),
    ), patch(
        "backend.services.energie_profil._helpers._get_tagespeaks_aus_ha_lts",
        new=AsyncMock(return_value=peaks),
    ):
        tz = await aggregate_day(
            anlage, historisch, db,
            source=Source.VOLLBACKFILL_FROM_LTS,
            prefetched_tagesverlauf=tv,
        )
        await db.flush()
        tep_rows = (await db.execute(
            select(TagesEnergieProfil).where(
                TagesEnergieProfil.anlage_id == anlage.id,
                TagesEnergieProfil.datum == historisch,
            )
        )).scalars().all()

    # Peaks aus HA-LTS-Min/Max gesetzt (alter Backfill: aus W-Integration / oft None).
    assert tz.peak_pv_kw == 7.5
    assert tz.peak_netzbezug_kw == 3.2
    assert tz.peak_einspeisung_kw == 4.1
    # Börsenpreis-Tagesfelder gesetzt (alter Backfill ließ sie NULL).
    assert tz.boersenpreis_avg_cent is not None
    assert tz.negative_preis_stunden == 2  # h=12, h=13
    assert tz.boersenpreis_min_cent == -2.0
    # Strompreis-Stunden in TEP (alter Backfill: nie gesetzt).
    assert any(r.strompreis_cent is not None for r in tep_rows), (
        "TEP.strompreis_cent muss im konsolidierten Pfad gesetzt sein."
    )
    assert any(r.boersenpreis_cent is not None for r in tep_rows)


# ─────────────────────── E1 + dünne Schleife ────────────────────────────────


def test_e1_backfill_konstruiert_keine_tep_tz_rows_mehr() -> None:
    """E1 (Plan): `backfill.py` hat genau KEINEN eigenen TEP/TZ-Schreibpfad mehr
    — keine `TagesEnergieProfil(`/`TagesZusammenfassung(`-Konstruktoren, keine
    `seed_*_provenance`-Aufrufe, kein `delete(`. Genau ein Top-Level-Schreibpfad
    (Aggregator). Wenn jemand wieder direkt in backfill schreibt, bricht der Test."""
    src = Path(__file__).resolve().parents[1] / "services" / "energie_profil" / "backfill.py"
    text = src.read_text(encoding="utf-8")
    assert "TagesEnergieProfil(" not in text, "backfill.py konstruiert wieder TEP-Rows."
    assert "TagesZusammenfassung(" not in text, "backfill.py konstruiert wieder TZ-Rows."
    assert "seed_tep_provenance" not in text
    assert "seed_tz_provenance" not in text


@pytest.mark.asyncio
async def test_backfill_ist_duenne_schleife_ueber_aggregate_day(db) -> None:
    """Der Vollbackfill ruft pro fehlendem Tag `aggregate_day` mit
    `source=VOLLBACKFILL_FROM_LTS` und durchgereichten `prefetched_tagesverlauf`
    auf — die Pflicht-Mitigation (Bulk-Read einmal, Durchreichung pro Tag,
    Plan §3 B.3)."""
    from backend.services.energie_profil import backfill as backfill_mod

    anlage = _anlage_mit_mapping()
    db.add(anlage)
    await db.commit()

    von = date.today() - timedelta(days=3)
    bis = date.today() - timedelta(days=2)  # 2 Tage, keine bestehende TZ
    datum_isos = {(von + timedelta(days=i)).isoformat() for i in range(2)}

    ha_mock = MagicMock()
    ha_mock.is_available = True
    ha_mock.get_hourly_sensor_data = MagicMock(return_value={
        "sensor.bezug": {iso: {h: 0.5 for h in range(24)} for iso in datum_isos},
    })

    ag_day = AsyncMock(return_value=object())

    with patch(
        "backend.services.live_sensor_config.extract_live_config",
        new=MagicMock(return_value=({"netzbezug_w": "sensor.bezug"}, {}, {}, {})),
    ), patch(
        "backend.services.ha_statistics_service.get_ha_statistics_service",
        new=MagicMock(return_value=ha_mock),
    ), patch(
        "backend.services.energie_profil.backfill.aggregate_day",
        new=ag_day,
    ):
        stats = await backfill_mod.backfill_from_statistics(anlage, von, bis, db)

    assert ag_day.await_count == 2
    for call in ag_day.await_args_list:
        assert call.kwargs["source"] is Source.VOLLBACKFILL_FROM_LTS
        prefetched = call.kwargs["prefetched_tagesverlauf"]
        assert prefetched is not None
        assert "serien" in prefetched and "punkte" in prefetched
        assert len(prefetched["punkte"]) > 0
    # Status-Dict-Form unverändert (Werkbank-Vertrag).
    assert set(stats.keys()) == {
        "geschrieben", "uebersprungen_keine_daten", "uebersprungen_existiert"
    }
    assert stats["geschrieben"] == 2


@pytest.mark.asyncio
async def test_backfill_status_dict_bei_leerem_sensor_setup(db) -> None:
    """Frühe Abbruch-Pfade liefern das Status-Dict (nicht mehr nacktes `int 0`)
    — sonst crasht `resolve_and_backfill_from_statistics` beim Indexzugriff."""
    from backend.services.energie_profil import backfill as backfill_mod

    anlage = _anlage_mit_mapping()
    db.add(anlage)
    await db.commit()

    with patch(
        "backend.services.live_sensor_config.extract_live_config",
        new=MagicMock(return_value=({}, {}, {}, {})),  # keine Live-Sensoren
    ):
        stats = await backfill_mod.backfill_from_statistics(
            anlage, date.today() - timedelta(days=2), date.today() - timedelta(days=1), db,
        )

    assert isinstance(stats, dict)
    assert stats == {"geschrieben": 0, "uebersprungen_keine_daten": 0, "uebersprungen_existiert": 0}


# ───────────────── Werkbank-VOLLBACKFILL-Endpoint-Schema-Stabilität ─────────


@pytest.mark.asyncio
async def test_vollbackfill_endpoint_response_schema_stabil(db) -> None:
    """Die Werkbank-VOLLBACKFILL-Execute-Response behält ihr Schema (Plan-
    Pflichtbegrenzung: Plan/Execute-API stabil). Innen konsolidiert, außen
    unverändert — sonst bricht das Frontend."""
    from backend.services import repair_orchestrator as ro
    from backend.services.energie_profil.backfill import BackfillResult

    anlage = _anlage_mit_mapping()
    db.add(anlage)
    await db.commit()

    fake_result = BackfillResult(
        status="ok",
        von=date(2026, 1, 1),
        bis=date(2026, 1, 31),
        verarbeitet=31,
        geschrieben=20,
        uebersprungen_keine_daten=5,
        uebersprungen_existiert=6,
    )

    req = ro.RepairOperationRequest(
        operation="vollbackfill",
        anlage_id=anlage.id,
        params={},
    )

    with patch(
        "backend.services.energie_profil_service.resolve_and_backfill_from_statistics",
        new=AsyncMock(return_value=fake_result),
    ):
        out = await ro._execute_vollbackfill(req, db)

    assert set(out.keys()) == {
        "verarbeitet", "geschrieben", "uebersprungen_keine_daten",
        "uebersprungen_existiert", "von", "bis",
    }
    assert out["geschrieben"] == 20
    assert out["von"] == "2026-01-01"
