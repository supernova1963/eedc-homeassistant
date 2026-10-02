"""N-596 (#422): Ein Tag ohne Leistungswerte überschreibt keinen gespeicherten Tag.

**Der Defekt** (gemeldet von OB73-gif, GitHub #422): Für einen Tag, den Home Assistant
nicht mehr im Verlauf hat (``purge_keep_days``, Standard 10 Tage), liefert der echte
``get_tagesverlauf`` keine leere Liste, sondern das volle Raster — 144 Punkte und 6
Vortagsrand-Punkte **ohne einen einzigen Leistungswert**; der Börsenpreis-Rückfall
(aWATTar, rückwirkend abrufbar) schreibt dabei ``strompreis`` in jeden Punkt.
``hole_tagesverlauf`` prüfte nur die Länge, ``aggregate_day`` schrieb den Tag neu, und
die Geräte-kWh je Stunde (``TagesEnergieProfil.komponenten``) wurden leer. Seit v4.0.47
geschah das bei jedem Speichern eines Monats (Nachlauf Schritt 1) für alle Tage älter
als die Aufbewahrung; der LTS-Rückfall der Werkbank griff dabei nie, weil
``aggregate_day`` nicht ``None`` lieferte.

**Die Regel** (``hole_tagesverlauf``, Docstring a/b/c): Trägt die Kurve keinen
Leistungswert (Overlays wie ``strompreis`` zählen nicht), dann

a) steigt die Werkbank aus und versucht die Langzeitstatistik,
b) bleibt ein Tag mit gespeicherten Gerätewerten stehen,
c) wird ein Tag ohne Gerätewerte wie bisher aus den Zählern geschrieben.

Harness wie die #422-Messprobe (``plans/proben/probe_422_echte_einstiege.py``): echte
Einstiege — Nachlauf, Werkbank-Route, ``aggregate_day``, ``get_tagesverlauf`` —, nur
Home Assistant nachgestellt. „Gepurgt" heißt: Recorder (``get_history_normalized``) und
``statistics_short_term`` (``_baue_short_term_overlays``) leer, Zustandsverlauf leer.
⛔ Keine Probe patcht ``get_tagesverlauf`` selbst auf eine leere Liste — das ist ein
Zustand, den der echte Ablauf nicht erreicht (er hat am 02.10.2026 zwei falsche Schlüsse
erzeugt). Gepatcht wird ``get_tagesverlauf`` nur für die **Ausgangslage** (ein Tag, der
aggregiert wurde, als HA ihn noch hatte) und dort mit Leistungswerten.

Vorlage: ``plans/vorlage-n596-gepurgte-tage-nicht-leer-schreiben.md`` (P1–P13).
"""

from __future__ import annotations

from contextlib import ExitStack, contextmanager
from datetime import date, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm.attributes import flag_modified

import backend.models.sensor_snapshot  # noqa: F401 — Tabelle ins Schema der In-Memory-DB
from backend.models.anlage import Anlage
from backend.models.investition import Investition, InvestitionMonatsdaten
from backend.models.mqtt_energy_snapshot import MqttEnergySnapshot
from backend.models.tages_energie_profil import TagesEnergieProfil, TagesZusammenfassung
from backend.services.energie_profil.source import Source

from . import ha_lts_helfer

TAG = date(2026, 8, 30)
#: Der Börsenpreis-Rückfall liefert auch für gepurgte Tage — gemessen 02.10.2026 am echten
#: aWATTar-Abruf (24 Stunden für den 30.08.). Jede Probe läuft deshalb MIT ihm.
BOERSE = {h: 10.0 + h for h in range(24)}


# ═══════════════════════════════════════════════════════════════════════════
#  Attrappen
# ═══════════════════════════════════════════════════════════════════════════


class _Ha:
    """`ha_state_service` — Zustandsverlauf (Betriebsart); Sensorverlauf leer."""

    is_available = True

    def __init__(self, zustand):
        self.zustand = zustand

    async def get_zustand_history(self, ids, start, end):
        out = {}
        for e in ids:
            pts = [(t, w, None) for t, w in self.zustand.get(e, [])]
            davor = [p for p in pts if p[0] < start]
            im = [p for p in pts if start <= p[0] < end]
            if davor:
                im = [(start, davor[-1][1], None), *im]
            out[e] = im
        return out

    async def get_sensor_history(self, ids, start, end):
        return {}

    async def get_sensor_units(self, ids):
        return {}


def _kurve(wp_id: int, kw: float) -> dict:
    """Eine Kurve MIT Leistungswerten (Ausgangslage bzw. Langzeitstatistik)."""
    pkt = [
        {"zeit": f"{h:02d}:00", "werte": {"pv": 1.0, f"waermepumpe_{wp_id}": kw, "strompreis": 12.0}}
        for h in (11, 12)
    ]
    return {
        "serien": [
            {"key": f"waermepumpe_{wp_id}", "kategorie": "waermepumpe", "label": "Klima",
             "seite": "senke"},
            {"key": "strompreis", "kategorie": "preis", "seite": "overlay"},
        ],
        "punkte": pkt, "vortagsrand": [],
    }


def _zaehler_stunden(*stunden_netz: int) -> dict:
    """Stundenwerte des Zählerpfads: je genannter Stunde 1 kWh Netzbezug."""
    st = {h: {} for h in range(24)}
    for h in stunden_netz:
        st[h] = {"pv": 0.0, "einspeisung": 0.0, "netzbezug": 1.0, "verbrauch": 1.0,
                 "batterie_netto": 0.0}
    return st


def _neben(stack, *, boerse=BOERSE, zaehler=None):
    """Nebenquellen deterministisch. ``zaehler``: Stunden des Zählerpfads (HA-LTS) oder None."""
    from backend.services.energie_profil._helpers import TagesPeaks

    for ziel, wert in (
        ("backend.services.snapshot.aggregator.snapshot_tagestabelle", None),
        ("backend.services.snapshot.lts_aggregator.lts_tagestabelle",
         ha_lts_helfer.lts_tabelle(zaehler, {}) if zaehler else None),
        ("backend.services.sensor_snapshot_service.get_daily_counter_deltas_by_inv", {}),
        ("backend.services.sensor_snapshot_service.get_hourly_counter_sum_by_feld", {}),
        ("backend.services.energie_profil._helpers._get_wetter_ist", {}),
        ("backend.services.energie_profil._helpers._get_tagespeaks_aus_ha_lts",
         TagesPeaks(pv=None, netzbezug=None, einspeisung=None)),
        ("backend.services.strompreis_markt_service.get_strompreis_stunden", dict(boerse)),
    ):
        stack.enter_context(patch(ziel, new=AsyncMock(return_value=wert)))
    lts = MagicMock()
    lts.is_available = False
    stack.enter_context(
        patch("backend.services.ha_statistics_service.get_ha_statistics_service", lambda: lts)
    )


def _gepurgt(stack):
    """Home Assistant kennt den Tag nicht mehr: Recorder und statistics_short_term leer."""
    stack.enter_context(
        patch("backend.services.ha_state_service.get_ha_state_service", lambda: _Ha({}))
    )
    stack.enter_context(patch(
        "backend.services.live_tagesverlauf_service.get_history_normalized",
        new=AsyncMock(return_value=({}, {})),
    ))
    stack.enter_context(patch(
        "backend.services.live_tagesverlauf_service._baue_short_term_overlays",
        new=MagicMock(return_value=({}, {})),
    ))


@contextmanager
def _purge_lauf(*, boerse=BOERSE, zaehler=None, lts_kurve=None):
    """Ein Lauf auf gepurgten Tagen. ``lts_kurve``: was die Langzeitstatistik liefert — eine
    Kurve (für ``TAG``) oder ``{datum: kurve}`` (Bereichslauf)."""
    if lts_kurve is None:
        lts_tage = {}
    elif "punkte" in lts_kurve:
        lts_tage = {TAG: lts_kurve}
    else:
        lts_tage = dict(lts_kurve)

    async def _lts(db, anlage, von, bis):
        return SimpleNamespace(
            tage={d: k for d, k in lts_tage.items() if von <= d <= bis}, grund="ok",
        )

    with ExitStack() as s:
        _neben(s, boerse=boerse, zaehler=zaehler)
        _gepurgt(s)
        lts = AsyncMock(side_effect=_lts)
        s.enter_context(patch(
            "backend.services.energie_profil.lts_tagesverlauf.lade_tagesverlauf_aus_lts", new=lts,
        ))
        yield lts


async def _anlage_mit_klima(db, *, monatsstrom: float | None = 20.0):
    anlage = Anlage(
        anlagenname="N596", leistung_kwp=10.0, standort_plz="10115", standort_land="DE",
        wechselrichter_hersteller="generic", installationsdatum=date(2025, 1, 1),
        vollbackfill_durchgefuehrt=True,
    )
    db.add(anlage)
    await db.flush()
    wp = Investition(
        anlage_id=anlage.id, typ="waermepumpe", bezeichnung="Klima",
        anschaffungsdatum=date(2025, 1, 1), anschaffungskosten_gesamt=1.0,
        parameter={"wp_art": "luft_luft"},
    )
    db.add(wp)
    await db.flush()
    # Gerät NUR mit Leistungssensor (Split-Klima ohne kWh-Zähler) — der Fall aus P7.
    anlage.sensor_mapping = {"investitionen": {str(wp.id): {"live": {
        "betriebsmodus": "climate.klima", "leistung_w": "sensor.klima_w"}}}}
    vd = {"stromverbrauch_kwh": monatsstrom} if monatsstrom is not None else {}
    db.add(InvestitionMonatsdaten(investition_id=wp.id, jahr=2026, monat=8, verbrauch_daten=vd))
    await db.commit()
    return anlage, wp


async def _ausgangslage(db, anlage, wp, *, tag=TAG):
    """Der Tag wurde aggregiert, als HA ihn noch hatte: Kurve mit Werten, Betriebsart „cool"."""
    from backend.services.energie_profil.aggregator import aggregate_day

    with ExitStack() as s:
        _neben(s)
        s.enter_context(patch(
            "backend.services.live_tagesverlauf_service.get_tagesverlauf",
            new=AsyncMock(return_value=_kurve(wp.id, -5.0)),
        ))
        ha = _Ha({"climate.klima": [(datetime(2026, 8, 19, 8, 0), "cool")]})
        s.enter_context(patch("backend.services.ha_state_service.get_ha_state_service", lambda: ha))
        tz = await aggregate_day(anlage, tag, db, source=Source.SCHEDULER)
    await db.commit()
    assert tz is not None
    return await _zeilen(db, anlage, tag)


async def _zeilen(db, anlage, tag=TAG) -> list[tuple]:
    rows = (await db.execute(
        select(
            TagesEnergieProfil.id, TagesEnergieProfil.stunde, TagesEnergieProfil.komponenten,
            TagesEnergieProfil.betriebsmodus_je_wp, TagesEnergieProfil.created_at,
        ).where(TagesEnergieProfil.anlage_id == anlage.id, TagesEnergieProfil.datum == tag)
        .order_by(TagesEnergieProfil.stunde)
    )).all()
    return [tuple(r) for r in rows]


def _neu_geschrieben(vorher, nachher) -> bool:
    """Jede Zeile trägt einen neuen `created_at` — die IDs taugen dafür nicht (SQLite vergibt
    nach einem Delete dieselben wieder)."""
    return bool(nachher) and {r[4] for r in nachher}.isdisjoint({r[4] for r in vorher})


async def _netzbezug_summe(db, anlage, tag=TAG) -> float:
    werte = (await db.execute(select(TagesEnergieProfil.netzbezug_kw).where(
        TagesEnergieProfil.anlage_id == anlage.id, TagesEnergieProfil.datum == tag))).scalars()
    return round(sum(w or 0.0 for w in werte), 3)


async def _tz(db, anlage, tag=TAG):
    return (await db.execute(
        select(TagesZusammenfassung).where(
            TagesZusammenfassung.anlage_id == anlage.id, TagesZusammenfassung.datum == tag,
        )
    )).scalar_one_or_none()


def _wp_komponenten(zeilen, wp_id) -> dict[int, float]:
    key = f"waermepumpe_{wp_id}"
    return {st: k[key] for _, st, k, _, _ in zeilen if k and key in k}


def _mit_betriebsart(zeilen) -> dict[int, dict]:
    return {st: m for _, st, _, m, _ in zeilen if m}


# ═══════════════════════════════════════════════════════════════════════════
#  Der Helfer selbst
# ═══════════════════════════════════════════════════════════════════════════


def test_kurve_ohne_leistung_aber_mit_boersenpreis_traegt_keine_leistung():
    from backend.services.energie_profil.aggregator import kurve_traegt_leistung

    raster = [{"zeit": f"{m // 6:02d}:{(m % 6) * 10:02d}", "werte": {"strompreis": 11.7}}
              for m in range(144)]
    rand = [{"zeit": f"23:{i * 10:02d}", "werte": {"strompreis": 9.0}} for i in range(6)]
    serien = [{"key": "strompreis", "seite": "overlay"}]
    assert kurve_traegt_leistung(raster, rand, serien) is False
    # Ein Leistungswert irgendwo — auch 0.0, auch nur im Vortagsrand — reicht.
    assert kurve_traegt_leistung(raster, [{"zeit": "23:50", "werte": {"pv": 0.0}}], serien)
    # Ein Overlay, das nur über die Serie als solches erkennbar ist, zählt nicht.
    andere = [{"zeit": "10:00", "werte": {"co2_overlay": 300.0}}]
    assert kurve_traegt_leistung(andere, [], [{"key": "co2_overlay", "seite": "overlay"}]) is False
    assert kurve_traegt_leistung([{"zeit": "10:00", "werte": {"pv": None}}], [], []) is False


# ═══════════════════════════════════════════════════════════════════════════
#  P1 · P7 — Speichern eines Monats (Nachlauf) auf einem gepurgten Tag
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_p1_nachlauf_laesst_gepurgten_tag_stehen_und_split_bleibt(db):
    from backend.core.betriebsmodus import MODUS_STROM_FELD, KUEHLEN
    from backend.services.monatsabschluss_aggregator import run_post_monatsabschluss_aggregation

    anlage, wp = await _anlage_mit_klima(db, monatsstrom=20.0)
    vorher = await _ausgangslage(db, anlage, wp)
    assert _wp_komponenten(vorher, wp.id), "Ausgangslage trägt Gerätewerte"
    assert _mit_betriebsart(vorher), "Ausgangslage trägt die Betriebsart"

    with _purge_lauf():
        await run_post_monatsabschluss_aggregation(anlage, 2026, 8, db)
    await db.commit()

    nachher = await _zeilen(db, anlage)
    assert nachher == vorher, "derselbe Tag, dieselben Zeilen (id, Gerätewerte, Betriebsart, created_at)"
    imd = (await db.execute(select(InvestitionMonatsdaten).where(
        InvestitionMonatsdaten.investition_id == wp.id))).scalar_one()
    assert (imd.verbrauch_daten or {}).get(MODUS_STROM_FELD[KUEHLEN], 0) > 0, (
        "die Aufteilung Kühlen bleibt nach dem Speichern erhalten"
    )


@pytest.mark.asyncio
async def test_p7_geraet_nur_mit_leistungssensor_behaelt_seine_tagesmenge(db):
    """Split-Klima ohne kWh-Zähler: die Tagesmenge steht nur aus der Leistungskurve."""
    from backend.services.monatsabschluss_aggregator import run_post_monatsabschluss_aggregation

    anlage, wp = await _anlage_mit_klima(db)
    await _ausgangslage(db, anlage, wp)
    tz_vorher = dict((await _tz(db, anlage)).komponenten_kwh or {})
    wp_keys = [k for k in tz_vorher if str(wp.id) in k]
    assert wp_keys, f"Ausgangslage trägt eine Tagesmenge des Geräts: {tz_vorher}"

    with _purge_lauf():
        await run_post_monatsabschluss_aggregation(anlage, 2026, 8, db)
    await db.commit()

    tz_nachher = dict((await _tz(db, anlage)).komponenten_kwh or {})
    assert {k: tz_nachher.get(k) for k in wp_keys} == {k: tz_vorher[k] for k in wp_keys}


# ═══════════════════════════════════════════════════════════════════════════
#  P2 · P3 · P8 · P13 — Werkbank
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_p2_werkbank_nimmt_die_langzeitstatistik(db):
    from backend.api.routes.energie_profil.repair import reaggregate_tag

    anlage, wp = await _anlage_mit_klima(db)
    vorher = await _ausgangslage(db, anlage, wp)

    with _purge_lauf(lts_kurve=_kurve(wp.id, -3.0)) as lts:
        antwort = await reaggregate_tag(anlage.id, datum=TAG, mit_resnap=False, db=db)
    await db.commit()

    assert lts.await_count == 1, "der LTS-Rückfall wurde benutzt"
    nachher = await _zeilen(db, anlage)
    assert set(_wp_komponenten(nachher, wp.id).values()) == {-3.0}, "Gerätewerte aus der LTS"
    assert _mit_betriebsart(nachher) == _mit_betriebsart(vorher), "Betriebsart gerettet (N-595)"
    assert antwort["status"] == "ok"


@pytest.mark.asyncio
async def test_p3_werkbank_ohne_lts_laesst_den_tag_stehen_und_sagt_warum(db):
    from backend.api.routes.energie_profil.repair import reaggregate_tag

    anlage, wp = await _anlage_mit_klima(db)
    vorher = await _ausgangslage(db, anlage, wp)

    with _purge_lauf(lts_kurve=None) as lts:
        with pytest.raises(HTTPException) as fehler:
            await reaggregate_tag(anlage.id, datum=TAG, mit_resnap=False, db=db)
    await db.rollback()
    await db.refresh(anlage)

    assert lts.await_count == 1
    assert "nicht neu geschrieben" in fehler.value.detail
    assert "Langzeitstatistik" in fehler.value.detail
    assert await _zeilen(db, anlage) == vorher


@pytest.mark.asyncio
async def test_p8_rueckweg_leer_geschriebener_tag_holt_geraetewerte_aus_lts(db):
    """Ein Tag, den ein früherer Nachlauf schon leer geschrieben hat (Zeilen ohne `komponenten`)."""
    from backend.api.routes.energie_profil.repair import reaggregate_tag

    anlage, wp = await _anlage_mit_klima(db)
    await _ausgangslage(db, anlage, wp)
    # Leer geschrieben, wie es v4.0.47–v4.1.0 beim Speichern eines Monats tat.
    for row in (await db.execute(select(TagesEnergieProfil).where(
            TagesEnergieProfil.anlage_id == anlage.id, TagesEnergieProfil.datum == TAG))).scalars():
        row.komponenten = {}
    await db.commit()
    assert not _wp_komponenten(await _zeilen(db, anlage), wp.id)

    with _purge_lauf(lts_kurve=_kurve(wp.id, -3.0)) as lts:
        await reaggregate_tag(anlage.id, datum=TAG, mit_resnap=False, db=db)
    await db.commit()

    assert lts.await_count == 1
    assert set(_wp_komponenten(await _zeilen(db, anlage), wp.id).values()) == {-3.0}


@pytest.mark.asyncio
async def test_p13_werkbank_tag_ohne_geraetewerte_ohne_lts_wird_aus_zaehlern_geschrieben(db):
    """Keine Verschlechterung: ohne Gerätewerte und ohne LTS rechnet die Werkbank wie bisher
    aus den Zählern neu — und sagt, dass sie es so getan hat."""
    from backend.services.repair_orchestrator import _reparatur_aggregat

    anlage, wp = await _anlage_mit_klima(db)
    from backend.services.energie_profil.aggregator import aggregate_day

    with _purge_lauf(zaehler=_zaehler_stunden(5)):
        await aggregate_day(anlage, TAG, db, source=Source.SCHEDULER)
    await db.commit()
    vorher = await _zeilen(db, anlage)
    assert vorher and not _wp_komponenten(vorher, wp.id)

    with _purge_lauf(zaehler=_zaehler_stunden(5, 6)) as lts:
        zusammenfassung, quelle = await _reparatur_aggregat(anlage, TAG, db)
    await db.commit()

    assert lts.await_count == 1
    assert zusammenfassung is not None
    assert quelle == "zaehler"
    assert _neu_geschrieben(vorher, await _zeilen(db, anlage))
    assert await _netzbezug_summe(db, anlage) == 2.0, "die neue Zählerstunde ist drin"


# ── Bereichslauf: der Weg des Daten-Checker-Knopfs „Neu aggregieren" ──────
#
# `action_kind="reaggregate_range"` (z. B. „Zähler-Abdeckung: … Tage vor dem Umbau
# gerechnet") landet in `_execute_reaggregate_range`, und der ruft je Tag denselben
# `_reparatur_aggregat` wie der Einzeltag. Zwei aufeinanderfolgende Tage, damit der
# aufsteigende Lauf (Tag D schreibt vor Tag D+1) mitgeprüft ist. Gemeldet von OB73-gif
# (#422): genau über diesen Knopf ging sein Verlauf verloren.

VORTAG = TAG - timedelta(days=1)


@pytest.mark.asyncio
async def test_p2_bereichslauf_nimmt_je_tag_die_langzeitstatistik(db):
    from backend.api.routes.energie_profil.repair import reaggregate_bereich

    anlage, wp = await _anlage_mit_klima(db)
    vorher = {d: await _ausgangslage(db, anlage, wp, tag=d) for d in (VORTAG, TAG)}

    with _purge_lauf(lts_kurve={d: _kurve(wp.id, -3.0) for d in (VORTAG, TAG)}) as lts:
        antwort = await reaggregate_bereich(anlage.id, von=VORTAG, bis=TAG, mit_resnap=False, db=db)
    await db.commit()

    assert lts.await_count == 2, "je Tag ein LTS-Rückfall"
    assert antwort["erfolgreich"] == 2 and antwort["keine_daten"] == 0, antwort
    for d in (VORTAG, TAG):
        nachher = await _zeilen(db, anlage, d)
        assert set(_wp_komponenten(nachher, wp.id).values()) == {-3.0}, d
        assert _mit_betriebsart(nachher) == _mit_betriebsart(vorher[d]), d


@pytest.mark.asyncio
async def test_p8_bereichslauf_rueckweg_fuer_leer_geschriebene_tage(db):
    from backend.api.routes.energie_profil.repair import reaggregate_bereich

    anlage, wp = await _anlage_mit_klima(db)
    for d in (VORTAG, TAG):
        await _ausgangslage(db, anlage, wp, tag=d)
    for row in (await db.execute(select(TagesEnergieProfil).where(
            TagesEnergieProfil.anlage_id == anlage.id))).scalars():
        row.komponenten = {}
    await db.commit()

    with _purge_lauf(lts_kurve={d: _kurve(wp.id, -3.0) for d in (VORTAG, TAG)}) as lts:
        antwort = await reaggregate_bereich(anlage.id, von=VORTAG, bis=TAG, mit_resnap=False, db=db)
    await db.commit()

    assert lts.await_count == 2
    assert antwort["erfolgreich"] == 2, antwort
    for d in (VORTAG, TAG):
        assert set(_wp_komponenten(await _zeilen(db, anlage, d), wp.id).values()) == {-3.0}, d


@pytest.mark.asyncio
async def test_p3_bereichslauf_ohne_lts_laesst_die_tage_stehen_und_nennt_den_grund(db):
    from backend.api.routes.energie_profil.repair import reaggregate_bereich

    anlage, wp = await _anlage_mit_klima(db)
    vorher = {d: await _ausgangslage(db, anlage, wp, tag=d) for d in (VORTAG, TAG)}

    with _purge_lauf(lts_kurve=None):
        antwort = await reaggregate_bereich(anlage.id, von=VORTAG, bis=TAG, mit_resnap=False, db=db)
    await db.commit()

    assert antwort["erfolgreich"] == 0 and antwort["keine_daten"] == 2, antwort
    assert {f["grund"] for f in antwort["fehler_details"]} == {"unveraendert:keine_daten"}
    for d in (VORTAG, TAG):
        assert await _zeilen(db, anlage, d) == vorher[d], d


# ═══════════════════════════════════════════════════════════════════════════
#  P4 · P5 · P6 · P12 — was bleibt wie bisher
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_p4_tag_ohne_zeilen_wird_aus_zaehlern_geschrieben(db):
    from backend.services.energie_profil.aggregator import aggregate_day

    anlage, _ = await _anlage_mit_klima(db)
    with _purge_lauf(zaehler=_zaehler_stunden(5, 6)):
        tz = await aggregate_day(anlage, TAG, db, source=Source.MONATSABSCHLUSS_BACKFILL)
    await db.commit()

    assert tz is not None
    assert {st for _, st, *_ in await _zeilen(db, anlage)} >= {5, 6}


@pytest.mark.asyncio
async def test_p5_tag_mit_leistungskurve_wird_neu_geschrieben(db):
    from backend.services.energie_profil.aggregator import aggregate_day

    anlage, wp = await _anlage_mit_klima(db)
    vorher = await _ausgangslage(db, anlage, wp)
    with ExitStack() as s:
        _neben(s)
        s.enter_context(patch(
            "backend.services.live_tagesverlauf_service.get_tagesverlauf",
            new=AsyncMock(return_value=_kurve(wp.id, -2.0)),
        ))
        s.enter_context(patch("backend.services.ha_state_service.get_ha_state_service",
                              lambda: _Ha({})))
        tz = await aggregate_day(anlage, TAG, db, source=Source.MONATSABSCHLUSS_BACKFILL)
    await db.commit()

    assert tz is not None
    nachher = await _zeilen(db, anlage)
    assert _neu_geschrieben(vorher, nachher)
    assert set(_wp_komponenten(nachher, wp.id).values()) == {-2.0}


@pytest.mark.asyncio
async def test_p6_mqtt_anlage_ohne_leistungszuordnung_schreibt_wie_bisher(db):
    """Reine MQTT-Energie, keine Leistungszuordnung: synthetische Slots, jeder Lauf schreibt neu —
    auch wenn der Tag (aus einem früheren Weg) Gerätewerte trägt."""
    from backend.services.energie_profil.aggregator import aggregate_day

    anlage = Anlage(anlagenname="MQTT", leistung_kwp=10.0, standort_land="DE",
                    installationsdatum=date(2025, 1, 1), sensor_mapping={})
    db.add(anlage)
    await db.flush()
    db.add(MqttEnergySnapshot(
        anlage_id=anlage.id, timestamp=datetime.combine(TAG, datetime.min.time()),
        energy_key="netzbezug", value_kwh=100.0,
    ))
    db.add(TagesEnergieProfil(anlage_id=anlage.id, datum=TAG, stunde=12,
                              komponenten={"pv_gesamt": 1.5}))
    await db.commit()
    vorher = await _zeilen(db, anlage)

    with ExitStack() as s:
        _neben(s, zaehler=_zaehler_stunden(5))
        _gepurgt(s)
        tz = await aggregate_day(anlage, TAG, db, source=Source.MONATSABSCHLUSS_BACKFILL)
    await db.commit()

    assert tz is not None
    assert _neu_geschrieben(vorher, await _zeilen(db, anlage))


@pytest.mark.asyncio
async def test_p12_leistungssensor_ohne_historie_friert_den_tag_nicht_ein(db):
    """Leistungszuordnung, aber der Sensor hat keine Historie (Recorder-Ausschluss,
    umbenannte Entity) — die Zähler laufen. Der zweite Lauf desselben Tages schreibt neu."""
    from backend.services.energie_profil.aggregator import aggregate_day

    anlage, _ = await _anlage_mit_klima(db)
    with _purge_lauf(zaehler=_zaehler_stunden(5)):
        await aggregate_day(anlage, TAG, db, source=Source.SCHEDULER)
    await db.commit()
    erster = await _zeilen(db, anlage)

    with _purge_lauf(zaehler=_zaehler_stunden(5, 6)):
        tz = await aggregate_day(anlage, TAG, db, source=Source.SCHEDULER)
    await db.commit()

    assert tz is not None
    assert _neu_geschrieben(erster, await _zeilen(db, anlage))
    assert await _netzbezug_summe(db, anlage) == 2.0, "die neue Zählerstunde ist drin"


# ═══════════════════════════════════════════════════════════════════════════
#  P9 — N-597: der Daten-Checker meldet eine nicht gespeicherte Aufteilung
# ═══════════════════════════════════════════════════════════════════════════


async def _meldungen_aufteilung(db, anlage) -> list:
    from backend.services.daten_checker import DatenChecker

    ergebnis = await DatenChecker(db).check_anlage(anlage.id)
    return [e for e in ergebnis.ergebnisse if "Aufteilung nach Betriebsart nicht gespeichert" in e.meldung]


async def _speichern(db, anlage, wp, monatsstrom: float | None):
    from backend.services.monatsabschluss_aggregator import run_post_monatsabschluss_aggregation

    imd = (await db.execute(select(InvestitionMonatsdaten).where(
        InvestitionMonatsdaten.investition_id == wp.id))).scalar_one()
    vd = dict(imd.verbrauch_daten or {})
    if monatsstrom is None:
        vd.pop("stromverbrauch_kwh", None)
    else:
        vd["stromverbrauch_kwh"] = monatsstrom
    imd.verbrauch_daten = vd
    flag_modified(imd, "verbrauch_daten")
    await db.commit()
    with _purge_lauf():
        await run_post_monatsabschluss_aggregation(anlage, 2026, 8, db)
    await db.commit()


@pytest.mark.asyncio
@pytest.mark.parametrize("monatsstrom, erwartet", [
    (5.0, "Monatsstrom 5,0 kWh"),      # B1: Σ Teilmengen 10 > 5
    (None, "Monatsstrom fehlt"),       # B2
])
async def test_p9_checker_meldet_nicht_gespeicherte_aufteilung(db, monatsstrom, erwartet):
    anlage, wp = await _anlage_mit_klima(db)
    await _ausgangslage(db, anlage, wp)
    await _speichern(db, anlage, wp, monatsstrom)

    treffer = await _meldungen_aufteilung(db, anlage)
    assert len(treffer) == 1, [t.meldung for t in treffer]
    m = treffer[0]
    assert m.schwere == "warning"
    assert "08/2026" in m.meldung and "zusammen 10,0 kWh" in m.meldung and erwartet in m.meldung
    assert m.link == "/monatsabschluss"
    assert m.investition_id == wp.id


@pytest.mark.asyncio
async def test_p9_checker_schweigt_wenn_die_aufteilung_passt_oder_gespeichert_ist(db):
    anlage, wp = await _anlage_mit_klima(db)
    await _ausgangslage(db, anlage, wp)
    await _speichern(db, anlage, wp, 20.0)       # passt ⇒ gespeichert
    assert await _meldungen_aufteilung(db, anlage) == []

    # Gespeicherter Split, Monatsstrom danach kleiner gepflegt: zuständig ist der Zwilling
    # („Heiz- und Kühlstrom zusammen größer als der Gesamtverbrauch"), nicht diese Meldung.
    imd = (await db.execute(select(InvestitionMonatsdaten).where(
        InvestitionMonatsdaten.investition_id == wp.id))).scalar_one()
    vd = dict(imd.verbrauch_daten)
    vd["stromverbrauch_kwh"] = 5.0
    imd.verbrauch_daten = vd
    flag_modified(imd, "verbrauch_daten")
    await db.commit()
    assert await _meldungen_aufteilung(db, anlage) == []
