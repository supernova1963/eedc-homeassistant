"""N-651 und N-658 — Daten-Checker und Import-Vorschau auf dem Datenstand der PV-Matrix.

Beide Funde sind an Matrix-Formen gemessen (Analyse 10.10.2026); die Proben bauen deshalb denselben Datenstand
(``pv_achse_matrix``: HA-Langzeitstatistik im echten Schema, Spiegel, Tageslauf, abgeschlossener Juni über die echten
Schreibwege S1 „Aus HA laden" · S2 Sammelimport · S3 Handeingabe ohne HA) — keine neue Form, nur je ein Einzelwert.

* **N-651** Ein Balkonkraftwerk ohne eigenen Zähler bekommt in einem Monat mit Anlagenwert seinen kWp-Anteil
  (P7/N-621). „PV-Erzeugung fehlt" an ihm war ein Fehlalarm neben der OK-Meldung der anlagenweiten PV-Prüfung
  (F04, F05, alle drei Wege). Gegenprobe ohne Anlagenwert: die Meldung bleibt.
* **N-658** Sind alle Geräte gemessen und liegt ihre Summe unter dem Messpunkt-Vertrag über dem Anlagenzähler (F13a:
  630 gegen 594), ist die Differenz Wandlungsverlust und kein Konflikt — die Vorschau nennt sie
  (``wandlungsverluste_kwh``). Liegt die Summe darunter (F13b), bleibt es ein Konflikt.
"""
from __future__ import annotations

import shutil
import tempfile
from datetime import date

import pytest
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from backend.models import Anlage, Investition
from backend.models.monatsdaten import Monatsdaten
from backend.tests import pv_achse_matrix as mx


async def _auf_dem_stand(fid: str, weg: str, messen):
    """Der Juni der Form ``fid`` nach Schreibweg ``weg``; ``messen(db, anlage_id, ids)`` läuft in der Umgebung."""
    form = mx.MATRIX_FORMEN[fid]
    verz = tempfile.mkdtemp(prefix="eedc-k2-")
    engine, db = await mx._neue_db(f"{verz}/k2.db")
    try:
        aid, ids = await mx.seed_anlage(db, form)
        if weg == "S3":
            await mx.seed_snapshots(db, form, aid, ids)
            with mx._umgebung(mx._ha_aus()):
                await mx.aggregiere_tage(db, form, aid, mx.TAGE_JUNI + mx.TAGE_JULI)
                await mx.schreibe_s3_von_hand(db, form, aid, ids)
                return await messen(db, aid, ids)
        svc = mx.seed_ha(form)
        with mx._umgebung(svc):
            await mx.fuelle_spiegel(engine, aid, svc)
            await mx.aggregiere_tage(db, form, aid, mx.TAGE_JUNI + mx.TAGE_JULI)
            if weg == "S1":
                await mx.schreibe_s1_aus_ha_laden(db, aid, form, ids)
            else:
                await mx.schreibe_s2_sammelimport(db, aid, form, ids)
            return await messen(db, aid, ids)
    finally:
        await db.close()
        await engine.dispose()
        shutil.rmtree(verz, ignore_errors=True)


async def _investitions_befunde(db, anlage_id: int):
    from backend.services.daten_checker import DatenChecker

    anlage = (await db.execute(
        select(Anlage).options(selectinload(Anlage.investitionen).selectinload(Investition.monatsdaten))
        .where(Anlage.id == anlage_id)
    )).scalar_one()
    monatsdaten = list((await db.execute(select(Monatsdaten).where(Monatsdaten.anlage_id == anlage_id))).scalars())
    return DatenChecker(db)._check_investitionen(anlage, monatsdaten)


def _pv_fehlt_am(befunde, inv_id: int) -> list:
    return [e for e in befunde if e.investition_id == inv_id and "PV-Erzeugung fehlt" in e.meldung]


# ── N-651 ───────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("weg", ["S1", "S2", "S3"])
@pytest.mark.parametrize("fid", ["F04", "F05"])
async def test_n651_bkw_ohne_zaehler_fehlt_nicht_neben_dem_anlagenwert(fid, weg):
    async def _messen(db, aid, ids):
        md = (await db.execute(select(Monatsdaten).where(
            Monatsdaten.anlage_id == aid, Monatsdaten.jahr == mx.JAHR, Monatsdaten.monat == mx.JUNI))).scalar_one()
        return md.pv_erzeugung_kwh, _pv_fehlt_am(await _investitions_befunde(db, aid), ids["Balkon"])

    anlagenwert, befunde = await _auf_dem_stand(fid, weg, _messen)

    assert anlagenwert is not None          # Vorbedingung: der Monat trägt den Anlagenwert
    assert befunde == []


async def test_n651_gegenprobe_ohne_anlagenwert_bleibt_die_meldung(db):
    """Weder eigener Wert noch Anlagenwert ⇒ das Balkonkraftwerk hat in diesem Monat keine Erzeugung — gemeldet."""
    a = Anlage(anlagenname="N-651", leistung_kwp=0.8)
    db.add(a)
    await db.flush()
    bkw = Investition(anlage_id=a.id, typ="balkonkraftwerk", bezeichnung="Balkon", leistung_kwp=0.8,
                      anschaffungsdatum=date(2024, 1, 1), parameter={"leistung_wp": 800})
    db.add(bkw)
    db.add(Monatsdaten(anlage_id=a.id, jahr=2025, monat=5, einspeisung_kwh=10.0, netzbezug_kwh=100.0))
    await db.commit()

    assert len(_pv_fehlt_am(await _investitions_befunde(db, a.id), bkw.id)) == 1


# ── N-658 ───────────────────────────────────────────────────────────────────


async def _vorschau_juni(db, aid, _ids):
    from backend.api.routes.ha_statistics import get_import_vorschau

    m = next(m for m in (await get_import_vorschau(aid, db)).monate if (m.jahr, m.monat) == (mx.JAHR, mx.JUNI))
    return m.aktion, m.wandlungsverluste_kwh, m.vorhandene_werte.get("PV Erzeugung Gesamt"), \
        m.ha_werte.get("PV Erzeugung Gesamt")


@pytest.mark.parametrize("weg", ["S1", "S2"])
async def test_n658_wandlungsverluste_sind_kein_konflikt(weg):
    aktion, verluste, lokal, ha = await _auf_dem_stand("F13a", weg, _vorschau_juni)

    assert (lokal, ha) == (pytest.approx(630.0), pytest.approx(594.0))
    assert aktion != "konflikt"
    assert verluste == pytest.approx(36.0)


@pytest.mark.parametrize("weg", ["S1", "S2"])
async def test_n658_mehr_als_die_strings_bleibt_ein_konflikt(weg):
    aktion, verluste, lokal, ha = await _auf_dem_stand("F13b", weg, _vorschau_juni)

    assert (lokal, ha) == (pytest.approx(630.0), pytest.approx(666.0))
    assert aktion == "konflikt"
    assert verluste is None
