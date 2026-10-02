"""N-595 (#422): Neu-Aggregieren rettet, was nur der HA-Verlauf kannte.

**Der Defekt** (gemeldet von OB73-gif, GitHub #422): `aggregate_day` schreibt einen
Tag per Delete+Insert neu. Die Betriebsart einer Wärmepumpe/Klimaanlage
(`TagesEnergieProfil.betriebsmodus_je_wp`) kommt **nur** aus Home Assistants
Recorder-Verlauf — und den löscht HA nach `purge_keep_days` (Standard 10 Tage).
Jede Neu-Aggregation eines älteren Tages ersetzte den einzigen erhaltenen Wert
durch „kein Signal"; der Monatsabschluss tut das für den ganzen Monat, danach
stand die Aufteilung Heizen/Kühlen auf „nicht aufgeteilt". Dieselbe Klasse trifft
SoC und Endkundenpreis, wenn deren Sensor keine Langzeitstatistik hat.

**Die Regel:** die Quelle gewinnt, wo sie liefert; gerettet wird nur, was sonst
leer bliebe, und nur in Stunden, die der neue Lauf ohnehin schreibt. Vorlage:
`plans/vorlage-n595-betriebsart-rettung.md` (Proben P1–P11).

Harness wie die Tor-1-Probe: der **echte** `aggregate_day`, Home Assistant
(Zustands-Verlauf, Sensor-Verlauf, Langzeitstatistik) als Attrappe, die
Nebenquellen (Zählerpfade, Wetter, Börse, Spitzen) deterministisch gepatcht.
"""

from __future__ import annotations

from contextlib import ExitStack, contextmanager
from datetime import date, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select

from backend.core.berechnungen.slot_konvention import (
    BETRIEBSMODUS_BACKWARD_AB,
    betriebsmodus_ziel_slot,
)
from backend.core.betriebsmodus import AUS, HEIZEN, KUEHLEN, MODUS_STROM_FELD
from backend.models.anlage import Anlage
from backend.models.investition import Investition, InvestitionMonatsdaten
from backend.models.tages_energie_profil import TagesEnergieProfil
from backend.services.energie_profil.source import Source

TAG = date(2026, 8, 30)
VORTAG = TAG - timedelta(days=1)
ALT_BACKWARD = datetime(2026, 9, 20, 3, 0)    # nach N-382 geschrieben
ALT_FORWARD = datetime(2026, 9, 1, 8, 0)      # Monatsabschluss August vor N-382


# ═══════════════════════════════════════════════════════════════════════════
#  Attrappen
# ═══════════════════════════════════════════════════════════════════════════


class _HaZustand:
    """`ha_state_service` — Zustands-Verlauf (Betriebsart) und Sensor-Verlauf (SoC/Preis)."""

    is_available = True

    def __init__(self, zustand=None, sensor=None):
        self.zustand = zustand or {}     # {entity: [(ts, roh)]}
        self.sensor = sensor or {}       # {entity: [(ts, wert)]}

    async def get_zustand_history(self, entity_ids, start, end):
        out = {}
        for eid in entity_ids:
            pts = [(ts, w, None) for ts, w in self.zustand.get(eid, [])]
            davor = [p for p in pts if p[0] < start]
            im = [p for p in pts if start <= p[0] < end]
            if davor:
                im = [(start, davor[-1][1], None), *im]
            out[eid] = im
        return out

    async def get_sensor_history(self, entity_ids, start, end):
        return {e: [p for p in self.sensor.get(e, []) if start <= p[0] < end] for e in entity_ids}

    async def get_sensor_units(self, entity_ids):
        return {e: "ct/kWh" for e in entity_ids}


class _HaLts:
    """`ha_statistics_service` — Langzeitstatistik (SoC je Stunde, Preis-Mittel je Stunde)."""

    is_available = True

    def __init__(self, soc=None, preis=None):
        self.soc = soc or {}        # {entity: {h: wert}}
        self.preis = preis or {}    # {entity: {h: wert}}

    def get_hourly_sensor_data(self, entity_ids, von, bis):
        return {e: {von.isoformat(): dict(self.soc[e])} for e in entity_ids if e in self.soc}

    def get_hourly_mean_for_day(self, sensor_id, datum):
        return dict(self.preis.get(sensor_id, {})), "ct/kWh"


def _kurve(slots, extra=None):
    """Leistungsverlauf, der genau diese Backward-Slots schreibt (Slot 0 entsteht immer).

    Ein Punkt „h:00" deckt ``[h, h+1)`` und landet in Slot ``h+1`` (N-382).
    """
    punkte = []
    for s in sorted(slots):
        if s == 0:
            continue
        werte = {"pv": 1000.0}
        werte.update(extra or {})
        punkte.append({"zeit": f"{s - 1:02d}:00", "werte": werte})
    serien = [{"key": k, "kategorie": "waermepumpe", "label": k} for k in (extra or {})]
    return {"serien": serien, "punkte": punkte, "vortagsrand": []}


@contextmanager
def _umgebung(*, zustand=None, sensor=None, lts=None, boerse=None, kurve=None):
    from backend.services.energie_profil._helpers import TagesPeaks

    stack = ExitStack()
    kurve = kurve if kurve is not None else _kurve({12, 13})
    for ziel, wert in (
        ("backend.services.live_tagesverlauf_service.get_tagesverlauf", kurve),
        ("backend.services.snapshot.aggregator.snapshot_tagestabelle", None),
        ("backend.services.snapshot.lts_aggregator.lts_tagestabelle", None),
        ("backend.services.sensor_snapshot_service.get_daily_counter_deltas_by_inv", {}),
        ("backend.services.sensor_snapshot_service.get_hourly_counter_sum_by_feld", {}),
        ("backend.services.energie_profil._helpers._get_wetter_ist", {}),
        ("backend.services.energie_profil._helpers._get_tagespeaks_aus_ha_lts",
         TagesPeaks(pv=None, netzbezug=None, einspeisung=None)),
        ("backend.services.strompreis_markt_service.get_strompreis_stunden", boerse or {}),
    ):
        stack.enter_context(patch(ziel, new=AsyncMock(return_value=wert)))
    zustand_fake = _HaZustand(zustand, sensor)
    lts_fake = lts or _HaLts()
    stack.enter_context(patch(
        "backend.services.ha_state_service.get_ha_state_service", lambda: zustand_fake,
    ))
    stack.enter_context(patch(
        "backend.services.ha_statistics_service.get_ha_statistics_service", lambda: lts_fake,
    ))
    with stack:
        yield


async def _aufbau(db, *, wps=1, speicher=False, preis=False):
    anlage = Anlage(
        anlagenname="N595", leistung_kwp=10.0, standort_plz="10115",
        standort_land="DE", wechselrichter_hersteller="generic", sensor_mapping={},
    )
    db.add(anlage)
    await db.flush()
    mapping: dict = {"investitionen": {}}
    wp_liste = []
    for i in range(wps):
        wp = Investition(
            anlage_id=anlage.id, typ="waermepumpe", bezeichnung=f"Klima {i}",
            anschaffungsdatum=date(2025, 1, 1), anschaffungskosten_gesamt=1.0,
            parameter={"wp_art": "luft_luft"},
        )
        db.add(wp)
        await db.flush()
        mapping["investitionen"][str(wp.id)] = {"live": {"betriebsmodus": f"climate.k{i}"}}
        wp_liste.append(wp)
    sp = None
    if speicher:
        sp = Investition(
            anlage_id=anlage.id, typ="speicher", bezeichnung="Akku",
            anschaffungsdatum=date(2025, 1, 1), anschaffungskosten_gesamt=1.0,
            parameter={"kapazitaet_kwh": 10.0},
        )
        db.add(sp)
        await db.flush()
        mapping["investitionen"][str(sp.id)] = {"live": {"soc": "sensor.soc"}}
    if preis:
        mapping["basis"] = {"strompreis": {"sensor_id": "sensor.preis"}}
    anlage.sensor_mapping = mapping
    await db.commit()
    return anlage, wp_liste, sp


async def _lauf(db, anlage, tag=TAG, source=Source.MONATSABSCHLUSS_BACKFILL):
    from backend.services.energie_profil.aggregator import aggregate_day

    await aggregate_day(anlage, tag, db, source=source)
    await db.commit()
    return await _zeilen(db, anlage, tag)


async def _zeilen(db, anlage, tag=TAG):
    zeilen = (await db.execute(
        select(TagesEnergieProfil).where(
            TagesEnergieProfil.anlage_id == anlage.id, TagesEnergieProfil.datum == tag,
        ).order_by(TagesEnergieProfil.stunde)
    )).scalars().all()
    return {z.stunde: z for z in zeilen}


def _modus(zeilen):
    return {h: z.betriebsmodus_je_wp for h, z in zeilen.items()}


def _verlauf(*eintraege):
    """Zustands-Verlauf ab dem Vortag 08:00 (der Tag beginnt im Zustand des Vortags)."""
    return list(eintraege)


async def _alte_zeile(db, anlage, tag, stunde, *, erstellt, **werte):
    db.add(TagesEnergieProfil(
        anlage_id=anlage.id, datum=tag, stunde=stunde, created_at=erstellt,
        source_provenance=werte.pop("source_provenance", {}), **werte,
    ))
    await db.commit()


# ═══════════════════════════════════════════════════════════════════════════
#  S1 — Ziel-Slot der Betriebsart (SoT `slot_konvention`)
# ═══════════════════════════════════════════════════════════════════════════


def _z(datum, stunde, erstellt):
    return SimpleNamespace(datum=datum, stunde=stunde, created_at=erstellt)


def test_s1_backward_zeile_bleibt_in_ihrem_slot():
    assert betriebsmodus_ziel_slot(_z(TAG, 12, ALT_BACKWARD)) == (TAG, 12)
    assert betriebsmodus_ziel_slot(_z(TAG, 0, ALT_BACKWARD)) == (TAG, 0)


def test_s1_forward_zeile_wandert_in_den_folge_slot():
    assert betriebsmodus_ziel_slot(_z(TAG, 12, ALT_FORWARD)) == (TAG, 13)
    # Stunde 23 = [23, 24) = Slot 0 des FOLGETAGS
    assert betriebsmodus_ziel_slot(_z(TAG, 23, ALT_FORWARD)) == (TAG + timedelta(days=1), 0)


def test_s1_grenze_ist_der_n382_tag_an_der_aggregationszeit():
    assert BETRIEBSMODUS_BACKWARD_AB == date(2026, 9, 4)
    am_tag = datetime(2026, 9, 4, 0, 0)
    tag_davor = datetime(2026, 9, 3, 23, 59)
    assert betriebsmodus_ziel_slot(_z(TAG, 5, am_tag)) == (TAG, 5)
    assert betriebsmodus_ziel_slot(_z(TAG, 5, tag_davor)) == (TAG, 6)
    # ohne Schreibzeit entscheidet das Datum der Zeile (Rückfallregel wie N-387)
    assert betriebsmodus_ziel_slot(_z(date(2026, 9, 10), 5, None)) == (date(2026, 9, 10), 5)
    assert betriebsmodus_ziel_slot(_z(TAG, 5, None)) == (TAG, 6)
    assert betriebsmodus_ziel_slot(_z(TAG, 24, ALT_BACKWARD)) is None


# ═══════════════════════════════════════════════════════════════════════════
#  P1 — der Melderfall
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
@pytest.mark.parametrize("quelle", [Source.MONATSABSCHLUSS_BACKFILL, Source.MANUAL_REPAIR])
async def test_p1_gepurgter_verlauf_loescht_die_betriebsart_nicht(db, quelle):
    anlage, (wp,), _ = await _aufbau(db)
    mit = {"climate.k0": _verlauf((datetime.combine(VORTAG, datetime.min.time())
                                   + timedelta(hours=8), "cool"))}
    with _umgebung(zustand=mit):
        vorher = _modus(await _lauf(db, anlage, source=quelle))
    assert vorher == {h: {str(wp.id): KUEHLEN} for h in (0, 12, 13)}, "Kontrolle Lauf 1"

    with _umgebung(zustand={}):                      # HA hat den Tag gepurgt
        nachher = _modus(await _lauf(db, anlage, source=quelle))
    assert nachher == vorher


# ═══════════════════════════════════════════════════════════════════════════
#  P2 — die Quelle gewinnt, wo sie liefert
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_p2_neuer_verlauf_schlaegt_die_rettung(db):
    anlage, (wp,), _ = await _aufbau(db)
    start = datetime.combine(VORTAG, datetime.min.time()) + timedelta(hours=8)
    with _umgebung(zustand={"climate.k0": [(start, "cool")]}):
        await _lauf(db, anlage)
    with _umgebung(zustand={"climate.k0": [(start, "heat")]}):
        nachher = _modus(await _lauf(db, anlage))
    assert nachher == {h: {str(wp.id): HEIZEN} for h in (0, 12, 13)}


# ═══════════════════════════════════════════════════════════════════════════
#  P3 — Randtag der Aufbewahrung: Stunde für Stunde, nicht alles oder nichts
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_p3_randtag_rettet_nur_die_gepurgten_stunden(db):
    anlage, (wp,), _ = await _aufbau(db)
    ganzer_tag = _kurve(set(range(24)))
    start = datetime.combine(VORTAG, datetime.min.time()) + timedelta(hours=8)
    with _umgebung(zustand={"climate.k0": [(start, "cool")]}, kurve=ganzer_tag):
        await _lauf(db, anlage)
    # HA kennt den Tag nur noch ab 14:00 — Slot 15 = [14, 15) ist der erste.
    ab_14 = datetime.combine(TAG, datetime.min.time()) + timedelta(hours=14)
    with _umgebung(zustand={"climate.k0": [(ab_14, "heat")]}, kurve=ganzer_tag):
        nachher = _modus(await _lauf(db, anlage))
    wp_id = str(wp.id)
    assert {h: m[wp_id] for h, m in nachher.items() if h < 15} == {h: KUEHLEN for h in range(15)}
    assert {h: m[wp_id] for h, m in nachher.items() if h >= 15} == {
        h: HEIZEN for h in range(15, 24)
    }


# ═══════════════════════════════════════════════════════════════════════════
#  P4 / P5 — je Wärmepumpe; keine Waisen einer gelöschten
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_p4_zwei_waermepumpen_verlauf_nur_fuer_eine(db):
    anlage, (wp1, wp2), _ = await _aufbau(db, wps=2)
    start = datetime.combine(VORTAG, datetime.min.time()) + timedelta(hours=8)
    with _umgebung(zustand={"climate.k0": [(start, "cool")], "climate.k1": [(start, "cool")]}):
        await _lauf(db, anlage)
    with _umgebung(zustand={"climate.k0": [(start, "heat")]}):   # k1 gepurgt
        nachher = _modus(await _lauf(db, anlage))
    assert nachher[12] == {str(wp1.id): HEIZEN, str(wp2.id): KUEHLEN}
    assert nachher[0] == {str(wp1.id): HEIZEN, str(wp2.id): KUEHLEN}


@pytest.mark.asyncio
async def test_p5_geloeschte_waermepumpe_hinterlaesst_keinen_schluessel(db):
    anlage, (wp1, wp2), _ = await _aufbau(db, wps=2)
    start = datetime.combine(VORTAG, datetime.min.time()) + timedelta(hours=8)
    with _umgebung(zustand={"climate.k0": [(start, "cool")], "climate.k1": [(start, "cool")]}):
        await _lauf(db, anlage)
    wp2_id = str(wp2.id)
    await db.delete(wp2)
    await db.commit()
    with _umgebung(zustand={}):
        nachher = _modus(await _lauf(db, anlage))
    assert nachher[12] == {str(wp1.id): KUEHLEN}
    assert all(wp2_id not in (m or {}) for m in nachher.values())


# ═══════════════════════════════════════════════════════════════════════════
#  P6 — Altbestand forward: die Betriebsart wandert mit der Slot-Konvention
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_p6_forward_altbestand_wandert_in_den_folge_slot(db):
    anlage, (wp,), _ = await _aufbau(db)
    wp_id = str(wp.id)
    await _alte_zeile(db, anlage, TAG, 12, erstellt=ALT_FORWARD,
                      betriebsmodus_je_wp={wp_id: KUEHLEN})
    await _alte_zeile(db, anlage, TAG, 13, erstellt=ALT_FORWARD,
                      betriebsmodus_je_wp={wp_id: HEIZEN})
    await _alte_zeile(db, anlage, VORTAG, 23, erstellt=ALT_FORWARD,
                      betriebsmodus_je_wp={wp_id: AUS})
    with _umgebung(zustand={}, kurve=_kurve({12, 13, 14})):
        nachher = _modus(await _lauf(db, anlage))
    assert nachher == {
        0: {wp_id: AUS},          # [Vortag 23, 00) aus der forward-Zeile 23 des Vortags
        12: None,                 # die alte Zeile 12 meinte [12, 13) = Slot 13
        13: {wp_id: KUEHLEN},
        14: {wp_id: HEIZEN},
    }


@pytest.mark.asyncio
async def test_p6_backward_zeile_23_des_vortags_fuellt_slot_0_nicht(db):
    anlage, (wp,), _ = await _aufbau(db)
    wp_id = str(wp.id)
    # backward: Zeile 23 des Vortags meint [22, 23) — nicht Slot 0 dieses Tages
    await _alte_zeile(db, anlage, VORTAG, 23, erstellt=ALT_BACKWARD,
                      betriebsmodus_je_wp={wp_id: AUS})
    with _umgebung(zustand={}):
        nachher = _modus(await _lauf(db, anlage))
    assert nachher[0] is None


# ═══════════════════════════════════════════════════════════════════════════
#  P7 — keine Zeile erfinden
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_p7_rettung_legt_keine_zeile_an(db):
    anlage, (wp,), _ = await _aufbau(db)
    await _alte_zeile(db, anlage, TAG, 5, erstellt=ALT_BACKWARD,
                      betriebsmodus_je_wp={str(wp.id): KUEHLEN}, soc_prozent=50.0,
                      strompreis_cent=30.0)
    with _umgebung(zustand={}):
        nachher = await _lauf(db, anlage)
    assert sorted(nachher) == [0, 12, 13]


# ═══════════════════════════════════════════════════════════════════════════
#  P8 / P9 — SoC und Endkundenpreis ohne Langzeitstatistik
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_p8_soc_ohne_lts_bleibt_mit_lts_gewinnt_die_quelle(db):
    anlage, _, sp = await _aufbau(db, speicher=True)
    sp_id = str(sp.id)
    with _umgebung(lts=_HaLts(soc={"sensor.soc": {0: 40.0, 12: 55.0, 13: 60.0}})):
        vorher = await _lauf(db, anlage)
    assert vorher[12].soc_prozent == 55.0 and vorher[12].soc_je_speicher == {sp_id: 55.0}

    with _umgebung(lts=_HaLts()):                    # LTS leer, Verlauf leer
        ohne = await _lauf(db, anlage)
    assert {h: z.soc_prozent for h, z in ohne.items()} == {0: 40.0, 12: 55.0, 13: 60.0}
    assert ohne[13].soc_je_speicher == {sp_id: 60.0}

    with _umgebung(lts=_HaLts(soc={"sensor.soc": {12: 70.0}})):   # Quelle liefert Slot 12
        mit = await _lauf(db, anlage)
    assert mit[12].soc_prozent == 70.0 and mit[12].soc_je_speicher == {sp_id: 70.0}
    assert mit[13].soc_prozent == 60.0                # Slot 13 liefert sie nicht


@pytest.mark.asyncio
async def test_p9_endkundenpreis_bleibt_boerse_folgt_der_quelle(db):
    anlage, _, _ = await _aufbau(db, preis=True)
    with _umgebung(lts=_HaLts(preis={"sensor.preis": {12: 31.5, 13: 33.0}}),
                   boerse={12: 9.1, 13: 10.2}):
        vorher = await _lauf(db, anlage)
    assert vorher[12].strompreis_cent == 31.5 and vorher[12].boersenpreis_cent == 9.1

    with _umgebung(lts=_HaLts(), boerse={}):          # Sensor gepurgt, Börse leer
        ohne = await _lauf(db, anlage)
    assert {h: z.strompreis_cent for h, z in ohne.items()} == {0: None, 12: 31.5, 13: 33.0}
    assert all(z.boersenpreis_cent is None for z in ohne.values())

    with _umgebung(lts=_HaLts(), boerse={12: 11.0, 13: 12.0}):
        neu = await _lauf(db, anlage)
    assert neu[12].boersenpreis_cent == 11.0 and neu[12].strompreis_cent == 31.5


# ═══════════════════════════════════════════════════════════════════════════
#  P10 — Herkunft
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_p10_gerettetes_feld_traegt_die_alte_herkunft(db):
    anlage, (wp,), sp = await _aufbau(db, speicher=True, preis=True)
    start = datetime.combine(VORTAG, datetime.min.time()) + timedelta(hours=8)
    with _umgebung(zustand={"climate.k0": [(start, "cool")]},
                   lts=_HaLts(soc={"sensor.soc": {12: 55.0}},
                              preis={"sensor.preis": {12: 31.5}})):
        vorher = await _lauf(db, anlage, source=Source.SCHEDULER)
    alt = vorher[12].source_provenance
    assert alt["betriebsmodus_je_wp"]["writer"] == Source.SCHEDULER.to_writer()

    with _umgebung(zustand={}, lts=_HaLts()):
        nachher = await _lauf(db, anlage, source=Source.MANUAL_REPAIR)
    neu = nachher[12].source_provenance
    for feld in ("betriebsmodus_je_wp", "soc_prozent", "soc_je_speicher", "strompreis_cent"):
        assert neu[feld] == alt[feld], feld
    # Kontrolle: was der Lauf neu geschrieben hat, trägt den neuen Writer
    assert neu["komponenten.pv"]["writer"] == Source.MANUAL_REPAIR.to_writer()


@pytest.mark.asyncio
async def test_p10_ohne_alte_herkunft_steht_preserve_restore(db):
    anlage, (wp,), _ = await _aufbau(db)
    await _alte_zeile(db, anlage, TAG, 12, erstellt=ALT_BACKWARD,
                      betriebsmodus_je_wp={str(wp.id): KUEHLEN}, source_provenance={})
    with _umgebung(zustand={}):
        nachher = await _lauf(db, anlage)
    eintrag = nachher[12].source_provenance["betriebsmodus_je_wp"]
    assert eintrag["source"] == "auto:preserve_restore"
    assert eintrag["writer"] == "aggregator-preserve"


# ═══════════════════════════════════════════════════════════════════════════
#  P11 — Monatsabschluss Ende zu Ende
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_p11_monatsabschluss_mit_gepurgtem_verlauf_behaelt_die_aufteilung(db):
    from backend.services.energie_profil.modus_split_monat import lade_modus_split_monat
    from backend.services.monatsabschluss_aggregator import (
        run_post_monatsabschluss_aggregation,
    )

    anlage, (wp,), _ = await _aufbau(db)
    anlage.vollbackfill_durchgefuehrt = True          # Schritt 3 gehört nicht hierher
    db.add(InvestitionMonatsdaten(
        investition_id=wp.id, jahr=2026, monat=8,
        verbrauch_daten={"stromverbrauch_kwh": 500.0},
    ))
    await db.commit()
    kurve = _kurve({12, 13}, extra={f"waermepumpe_{wp.id}": -0.2})
    start = datetime(2026, 7, 31, 8, 0)
    feld = MODUS_STROM_FELD[KUEHLEN]

    async def _abschluss(zustand):
        with _umgebung(zustand=zustand, kurve=kurve):
            await run_post_monatsabschluss_aggregation(anlage, 2026, 8, db)
        split = (await lade_modus_split_monat(db, anlage.id, 2026, 8)).get(str(wp.id))
        imd = (await db.execute(select(InvestitionMonatsdaten).where(
            InvestitionMonatsdaten.investition_id == wp.id,
        ))).scalar_one()
        await db.refresh(imd)
        return split, (imd.verbrauch_daten or {}).get(feld)

    split_1, imd_1 = await _abschluss({"climate.k0": [(start, "cool")]})
    assert split_1 is not None and split_1.teilmenge_kwh(KUEHLEN) > 0, "Kontrolle Abschluss 1"

    split_2, imd_2 = await _abschluss({})             # Abschluss nach dem Purge
    assert split_2 is not None, "Aufteilung fiel auf „nicht aufgeteilt“"
    assert split_2.teilmenge_kwh(KUEHLEN) == split_1.teilmenge_kwh(KUEHLEN)
    assert imd_2 == imd_1 and imd_2 > 0
