"""Erträge je Erzeuger auf Tagesebene (#350, Rainer).

Rainers Frage („welchen Ertrag brachte mein BKW im Vorgarten, mein Süd-Ost-Dach
gestern?") beantwortet `TagWerteResponse.erzeuger_kwh`. Die drei Eigenschaften,
die dabei nicht verrutschen dürfen:

1. **Ein Gerät, eine Spalte** — obwohl dasselbe Balkonkraftwerk in den beiden
   Keyspaces `pv_<id>` (Live-Pfad) und `bkw_<id>` (Boundary-Pfad) heißt.
2. **Nichts verteilt** — ohne eigenen Sensor bleibt der Erzeuger leer, statt
   einen kWp-Anteil als Messung auszugeben (#352-Klasse).
3. **Die Bilanz bleibt unberührt** — `erzeugung`/`pv_anlage` rechnen weiter aus
   ihren eigenen Quellen; die Aufschlüsselung ist eine Auskunft, keine Summe.
"""

from __future__ import annotations

from datetime import date

import pytest

from backend.core.berechnungen import erzeuger_kwh_je_investition
from backend.models import Anlage, Investition
from backend.models.tages_energie_profil import TagesEnergieProfil, TagesZusammenfassung
from backend.services.energie_profil.tage_werte import baue_tage_werte


# ── Layer-Formel ────────────────────────────────────────────────────────────

def test_beide_keyspaces_landen_auf_derselben_investition():
    """`pv_7` und `bkw_7` sind dasselbe Gerät — sonst zwei Spalten für ein BKW."""
    assert erzeuger_kwh_je_investition({"pv_7": 4.0, "bkw_7": 1.5}) == {"7": 5.5}


def test_nur_erzeuger_praefixe_und_nur_positive_werte():
    komponenten = {
        "pv_1": 12.0,
        "bkw_2": 3.0,
        "waermepumpe_3": 8.0,   # kein Erzeuger
        "batterie_4": -2.0,     # kein Erzeuger
        "pv_5": -0.5,           # negativer Beitrag zählt nicht (wie summe_pv_bkw_kwh)
        "netzbezug": 9.0,       # Basis-Key ohne Investition
        "pv_gesamt": 15.0,      # virtuelle Summe — wäre die Summe neben ihren Summanden
    }
    assert erzeuger_kwh_je_investition(komponenten) == {"1": 12.0, "2": 3.0}


def test_leeres_json_ergibt_leeres_dict():
    assert erzeuger_kwh_je_investition(None) == {}
    assert erzeuger_kwh_je_investition({}) == {}


# ── Route/Service ───────────────────────────────────────────────────────────

async def _anlage_mit_zwei_erzeugern(db) -> tuple[int, int, int]:
    anlage = Anlage(anlagenname="ErzeugerJeTag", leistung_kwp=10.0)
    db.add(anlage)
    await db.flush()
    dach = Investition(
        anlage_id=anlage.id, typ="pv-module", bezeichnung="Dach Süd",
        leistung_kwp=8.0, anschaffungsdatum=date(2024, 1, 1),
    )
    bkw = Investition(
        anlage_id=anlage.id, typ="balkonkraftwerk", bezeichnung="BKW Vorgarten",
        leistung_kwp=0.8, anschaffungsdatum=date(2024, 1, 1),
    )
    db.add_all([dach, bkw])
    await db.flush()
    return anlage.id, dach.id, bkw.id


@pytest.mark.asyncio
async def test_tageszeile_traegt_die_erzeuger_getrennt(db):
    """Boundary-Rollup vorhanden ⇒ er ist die Quelle, je Investitions-ID."""
    aid, dach_id, bkw_id = await _anlage_mit_zwei_erzeugern(db)
    tag = date(2026, 5, 10)
    db.add(TagesEnergieProfil(
        anlage_id=aid, datum=tag, stunde=11,
        pv_kw=6.0, verbrauch_kw=2.0, einspeisung_kw=4.0, netzbezug_kw=0.0,
    ))
    db.add(TagesZusammenfassung(
        anlage_id=aid, datum=tag, stunden_verfuegbar=1,
        komponenten_kwh={f"pv_{dach_id}": 5.4, f"bkw_{bkw_id}": 0.6, "netzbezug": 0.0},
    ))
    await db.commit()

    anlage = await db.get(Anlage, aid)
    zeilen = await baue_tage_werte(db, anlage, tag, tag)

    assert len(zeilen) == 1
    assert zeilen[0].erzeuger_kwh == {str(dach_id): 5.4, str(bkw_id): 0.6}
    # Die Bilanz kommt weiter aus den Stunden-Rows, nicht aus der Aufschlüsselung.
    assert zeilen[0].erzeugung == pytest.approx(6.0)


@pytest.mark.asyncio
async def test_ohne_rollup_fallen_die_stunden_ein(db):
    """Kein Boundary-Rollup (Standalone-Betrieb) ⇒ Σ der Stunden-Komponenten.

    Dort heißt das Balkonkraftwerk `pv_<id>` — dieselbe Investition, anderer
    Keyspace. Ohne die ID-Normalisierung stünde es hier in einer anderen Spalte
    als am Vortag mit Rollup.
    """
    aid, dach_id, bkw_id = await _anlage_mit_zwei_erzeugern(db)
    tag = date(2026, 5, 12)
    db.add_all([
        TagesEnergieProfil(
            anlage_id=aid, datum=tag, stunde=10,
            pv_kw=4.0, verbrauch_kw=1.0, einspeisung_kw=3.0, netzbezug_kw=0.0,
            komponenten={f"pv_{dach_id}": 3.7, f"pv_{bkw_id}": 0.3},
        ),
        TagesEnergieProfil(
            anlage_id=aid, datum=tag, stunde=11,
            pv_kw=2.0, verbrauch_kw=1.0, einspeisung_kw=1.0, netzbezug_kw=0.0,
            komponenten={f"pv_{dach_id}": 1.8, f"pv_{bkw_id}": 0.2},
        ),
    ])
    await db.commit()

    anlage = await db.get(Anlage, aid)
    zeilen = await baue_tage_werte(db, anlage, tag, tag)

    assert zeilen[0].erzeuger_kwh == {str(dach_id): 5.5, str(bkw_id): 0.5}


@pytest.mark.asyncio
async def test_ohne_eigene_sensoren_bleibt_es_leer_statt_verteilt(db):
    """Nur ein Anlagen-Gesamtwert ⇒ kein Gerätewert. Eine kWp-Verteilung wäre
    hier eine Messung, die niemand gemessen hat (#352)."""
    aid, _dach_id, _bkw_id = await _anlage_mit_zwei_erzeugern(db)
    tag = date(2026, 5, 13)
    db.add(TagesEnergieProfil(
        anlage_id=aid, datum=tag, stunde=12,
        pv_kw=7.0, verbrauch_kw=2.0, einspeisung_kw=5.0, netzbezug_kw=0.0,
        komponenten={"pv_gesamt": 7.0},
    ))
    db.add(TagesZusammenfassung(
        anlage_id=aid, datum=tag, stunden_verfuegbar=1,
        komponenten_kwh={"netzbezug": 0.0, "einspeisung": 5.0},
    ))
    await db.commit()

    anlage = await db.get(Anlage, aid)
    zeilen = await baue_tage_werte(db, anlage, tag, tag)

    assert zeilen[0].erzeuger_kwh is None
    assert zeilen[0].erzeugung == pytest.approx(7.0)
