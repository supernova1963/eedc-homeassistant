"""HA-Bauform E4f (Bauplan §9 B1, Konzept R-13): der Monatsabschluss-Nachlauf rechnet nur noch FEHLENDE Tage.

**Die Regel** (``monatsabschluss_aggregator``, Schritt 1 → ``backfill_range(nur_fehlende=True)``):

* ein Tag MIT Tageszeile wird nie neu gerechnet — gleich, ob Home Assistant ihn noch im Verlauf hat oder nicht
  (die Klasse #422/N-596 kann über den Nachlauf nicht wiederkehren);
* ein Tag OHNE Tageszeile wird angelegt, solange HA ihn im Verlauf hat (die Leistungskurve trägt einen Wert);
* liegt er außerhalb der Recorder-Aufbewahrung (Kurve ohne Leistungswert), wird er NICHT angelegt — auch nicht aus
  den Zählern (``aggregate_day(nur_mit_verlauf=True)``, die Grenze an derselben Stelle wie N-596);
* Schritt 3 (Auto-Vollbackfill) ist entfallen (``test_aggregatoren_und_verbrauchsprognose.py``,
  ``TestMonatsabschlussPipeline``).

Harness wie ``test_n596_gepurgte_tage_nicht_leer_schreiben.py`` (echte Einstiege, nur Home Assistant nachgestellt;
Börsenpreis-Rückfall in jedem Lauf). Jede Probe läuft über den echten Nachlauf ``run_post_monatsabschluss_aggregation``.
"""

from __future__ import annotations

from contextlib import ExitStack, contextmanager
from datetime import datetime
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select

import backend.models.mqtt_live_snapshot  # noqa: F401 — Tabelle ins Schema der In-Memory-DB (Leistungspfad)
import backend.models.sensor_snapshot  # noqa: F401
from backend.models.tages_energie_profil import TagesEnergieProfil, TagesZusammenfassung
from backend.services.energie_profil.source import Source

from .test_n596_gepurgte_tage_nicht_leer_schreiben import (
    TAG,
    _Ha,
    _anlage_mit_klima,
    _ausgangslage,
    _kurve,
    _neben,
    _purge_lauf,
    _zaehler_stunden,
    _zeilen,
)


@contextmanager
def _verlauf_da(wp_id: int, kw: float):
    """Home Assistant hat den Tag (und jeden Tag des Monats) noch im Verlauf: Kurve MIT Leistungswerten."""
    with ExitStack() as s:
        _neben(s, zaehler=_zaehler_stunden(10, 11))
        s.enter_context(patch(
            "backend.services.live_tagesverlauf_service.get_tagesverlauf",
            new=AsyncMock(return_value=_kurve(wp_id, kw)),
        ))
        ha = _Ha({"climate.klima": [(datetime(2026, 8, 19, 8, 0), "cool")]})
        s.enter_context(patch("backend.services.ha_state_service.get_ha_state_service", lambda: ha))
        yield


async def _nachlauf(db, anlage):
    from backend.services.monatsabschluss_aggregator import run_post_monatsabschluss_aggregation

    erg = await run_post_monatsabschluss_aggregation(anlage, 2026, 8, db)
    await db.commit()
    return erg


async def _tage_mit_zeile(db, anlage) -> set:
    return set((await db.execute(select(TagesZusammenfassung.datum).where(
        TagesZusammenfassung.anlage_id == anlage.id))).scalars().all())


async def _stundenzeilen(db, anlage, tag=TAG) -> int:
    return len((await db.execute(select(TagesEnergieProfil.id).where(
        TagesEnergieProfil.anlage_id == anlage.id, TagesEnergieProfil.datum == tag))).all())


@pytest.mark.asyncio
async def test_vorhandener_tag_mit_leerer_kurve_wird_nicht_ueberschrieben(db):
    """Der Tag trägt KEINE Gerätewerte (aus den Zählern geschrieben, N-596 Zweig c) — der N-596-Riegel schützt ihn also
    nicht. Bis E4f schrieb der Nachlauf ihn bei gepurgtem Verlauf neu; jetzt bleibt er Zeile für Zeile stehen."""
    from backend.services.energie_profil.aggregator import aggregate_day

    anlage, _wp = await _anlage_mit_klima(db)
    with _purge_lauf(zaehler=_zaehler_stunden(10, 11)):
        assert await aggregate_day(anlage, TAG, db, source=Source.SCHEDULER) is not None
    await db.commit()
    vorher = await _zeilen(db, anlage)
    assert vorher and not any(k for _, _, k, _, _ in vorher), "Ausgangslage: Zeilen ohne Gerätewerte"

    with _purge_lauf(zaehler=_zaehler_stunden(10, 11, 12)):
        await _nachlauf(db, anlage)

    assert await _zeilen(db, anlage) == vorher, "dieselben Zeilen (id, Werte, created_at)"


@pytest.mark.asyncio
async def test_vorhandener_tag_wird_auch_mit_verlauf_nicht_neu_gerechnet(db):
    """„Vorhandene Tage werden nie neu gerechnet" — auch nicht, wenn HA den Tag noch hat und anders nennt."""
    anlage, wp = await _anlage_mit_klima(db)
    vorher = await _ausgangslage(db, anlage, wp)          # Kurve −5 kW

    with _verlauf_da(wp.id, -7.0):                        # HA nennt jetzt −7 kW
        await _nachlauf(db, anlage)

    assert await _zeilen(db, anlage) == vorher


@pytest.mark.asyncio
async def test_fehlender_tag_innerhalb_der_aufbewahrung_wird_angelegt(db):
    anlage, wp = await _anlage_mit_klima(db)
    assert TAG not in await _tage_mit_zeile(db, anlage)

    with _verlauf_da(wp.id, -5.0):
        erg = await _nachlauf(db, anlage)

    tage = await _tage_mit_zeile(db, anlage)
    assert TAG in tage
    assert erg.backfill_count == len(tage) == 31, "jeder fehlende Tag des Augusts, den HA noch hat"
    assert await _stundenzeilen(db, anlage) > 0


@pytest.mark.asyncio
async def test_fehlender_tag_ausserhalb_der_aufbewahrung_wird_nicht_angelegt(db):
    """Kurve ohne Leistungswert (gepurgt), Zählerpfad vorhanden: bis E4f entstand der Tag aus den Zählern (N-596
    Zweig c), jetzt entsteht nichts — weder Tageszeile noch Stundenzeilen."""
    anlage, _wp = await _anlage_mit_klima(db)

    with _purge_lauf(zaehler=_zaehler_stunden(10, 11)):
        erg = await _nachlauf(db, anlage)

    assert erg.backfill_count == 0
    assert await _tage_mit_zeile(db, anlage) == set()
    assert await _stundenzeilen(db, anlage) == 0


@pytest.mark.asyncio
async def test_der_scheduler_schreibt_den_tag_ohne_verlauf_weiter_aus_den_zaehlern(db):
    """Gegenrichtung: die Grenze gilt NUR für den Nachlauf. Der Tageslauf (``Source.SCHEDULER``, ohne
    ``nur_mit_verlauf``) schreibt einen Tag ohne Gerätewerte weiter aus den Zählern (N-596 Zweig c, N-563 O1)."""
    from backend.services.energie_profil.aggregator import aggregate_day

    anlage, _wp = await _anlage_mit_klima(db)
    with _purge_lauf(zaehler=_zaehler_stunden(10, 11)):
        assert await aggregate_day(anlage, TAG, db, source=Source.SCHEDULER) is not None
    await db.commit()
    assert TAG in await _tage_mit_zeile(db, anlage)
