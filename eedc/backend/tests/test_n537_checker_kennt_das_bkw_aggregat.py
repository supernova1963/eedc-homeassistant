"""N-537 — Der Checker warnte vor Lücken, die die Rechnung längst schließt.

**Die Gegenrichtung zu N-536.** Dort zählte ein Balkonkraftwerk mit
`pv-module`-Kindern zu VIEL; hier meldet der Daten-Checker zu viel: Seine
Aggregat-Map kannte nur `Monatsdaten.pv_erzeugung_kwh` — das ANLAGEN-Aggregat.
Ein Balkonkraftwerk ist aber selbst das Aggregat seiner Kinder (N-266, Stufe 2
der P7-Präzedenz, `pv_monatswerte._lade_bkw_aggregate`). Ein Monat, in dem nur
das Gerät misst und seine Kinder nicht, galt deshalb als `teil_luecke`
(WARNING „teilgemessen, kein Aggregat") — für eine Lage, in der jede Zahl da
ist. Der Anwender konnte die Warnung nicht abstellen.

Dazu die Zuordnungs-Fläche: Sie sagt für das Anlagen-Aggregat und für die
WP-Gesamtleistung, dass ein Wert von feineren Quellen abgelöst wird — für die
Hierarchie-Ebene (Balkonkraftwerk gegen seine Kinder) sagte sie nichts.
"""

from __future__ import annotations

import pytest

from backend.core.berechnungen.pv_verteilung import (
    STATUS_OK,
    STATUS_TEIL_LUECKE,
    STATUS_VERTEILT,
    klassifiziere_pv_monat,
)
from backend.services.datenquellen_validierung import finde_bkw_fuellt_kinder_luecken


# ─── 1. Die Klassifikation, an der es hing ─────────────────────────────────

def test_ein_gedecktes_kind_zaehlt_als_abgeleitet_nicht_als_luecke():
    """Zwei Module, eines misst, das BKW deckt das andere ab.

    `n_abgeleitet` ist genau die Rolle, die #352 beschreibt: „Sie decken den
    Monat ab wie ein Aggregat." Ohne den BKW-Zweig stand hier `teil_luecke`.
    """
    assert klassifiziere_pv_monat(
        n_aktive_module=2, n_gemessen=1, aggregat_kwh=None, n_abgeleitet=0,
    ) == STATUS_TEIL_LUECKE
    assert klassifiziere_pv_monat(
        n_aktive_module=2, n_gemessen=1, aggregat_kwh=None, n_abgeleitet=1,
    ) == STATUS_VERTEILT


def test_vollstaendig_gemessen_bleibt_ok():
    """Gegenprobe: der BKW-Zweig darf eine echte Messung nicht abwerten."""
    assert klassifiziere_pv_monat(
        n_aktive_module=2, n_gemessen=2, aggregat_kwh=None, n_abgeleitet=0,
    ) == STATUS_OK


# ─── 2. Der Hinweis auf der Zuordnungs-Fläche ──────────────────────────────

def _felder(bkw_belegt: bool, kind1: bool, kind2: bool) -> list[dict]:
    return [
        {"id": "inv_energy_2_pv", "feld": "pv_erzeugung_kwh",
         "typ": "balkonkraftwerk", "inv_id": "2", "belegt": bkw_belegt},
        {"id": "inv_energy_21_pv", "feld": "pv_erzeugung_kwh",
         "typ": "pv-module", "inv_id": "21", "belegt": kind1},
        {"id": "inv_energy_22_pv", "feld": "pv_erzeugung_kwh",
         "typ": "pv-module", "inv_id": "22", "belegt": kind2},
    ]


_PARENT = {"21": "2", "22": "2"}


def test_flaeche_sagt_die_wirkung_wenn_ein_kind_misst():
    out = finde_bkw_fuellt_kinder_luecken(_felder(True, True, False), _PARENT)
    assert set(out) == {"inv_energy_2_pv"}
    p = out["inv_energy_2_pv"]
    assert p["schwere"] == "info", "kein Fehler, sondern eine Folge der Zuordnung"
    assert p["art"] == "bkw_fuellt_luecken"
    assert "füllt nur noch" in p["text"]
    assert p["wirksame_felder"] == ["inv_energy_21_pv"]


def test_flaeche_bietet_keinen_knopf_an():
    """⚠ Der Kern dieser Probe. `redundant` rendert inline „auf keine setzen" —
    bei teilweise gemessenen Modulen wäre das falscher Rat: der Wert des
    Balkonkraftwerks ist dann die einzige Quelle für das ungemessene Modul
    (gemessen in N-536: 52 → 28 Wh, also unter den Fehler)."""
    out = finde_bkw_fuellt_kinder_luecken(_felder(True, True, False), _PARENT)
    assert out["inv_energy_2_pv"]["art"] != "redundant"


def test_ohne_zuordnung_am_kind_sagt_die_flaeche_nichts():
    """Das Gerät ist dann die einzige Quelle — es gibt nichts abzutreten."""
    assert finde_bkw_fuellt_kinder_luecken(_felder(True, False, False), _PARENT) == {}


def test_ohne_zuordnung_am_bkw_sagt_die_flaeche_nichts():
    assert finde_bkw_fuellt_kinder_luecken(_felder(False, True, True), _PARENT) == {}


def test_ohne_kinder_sagt_die_flaeche_nichts():
    assert finde_bkw_fuellt_kinder_luecken(_felder(True, True, True), {}) == {}


def test_die_wechselrichter_grenze_wird_nicht_gemeldet():
    """Ein Balkonkraftwerk tritt seine AC-Grenze NICHT ab (N-266/E6) — sie
    gehört dem Gerät, nicht den Modulen."""
    felder = _felder(True, True, False) + [
        {"id": "inv_param_2_wr", "feld": "wechselrichter_leistung_w",
         "typ": "balkonkraftwerk", "inv_id": "2", "belegt": True},
    ]
    out = finde_bkw_fuellt_kinder_luecken(felder, _PARENT)
    assert "inv_param_2_wr" not in out


# ─── 3. Die Einhängung, nicht nur die Formel ───────────────────────────────
#
# ⚠ Diese Probe gibt es, weil bei N-536 genau das gefehlt hat: die Werte-Probe
# rief die Formel selbst auf und blieb grün, während ihr Aufruf im Produktcode
# entschärft war. Hier läuft der echte Checker gegen eine echte Anlage.

from datetime import date  # noqa: E402

from sqlalchemy import select  # noqa: E402
from sqlalchemy.orm import selectinload  # noqa: E402

from backend.models import Anlage, Investition, InvestitionMonatsdaten, Monatsdaten  # noqa: E402
from backend.services.daten_checker import DatenChecker  # noqa: E402


async def _seed_bkw(db, *, bkw_wert, kind1_wert=None):
    """BKW mit zwei Modul-Kindern, Mai 2026; kein Anlagen-Aggregat."""
    anlage = Anlage(anlagenname="BKW-Check", leistung_kwp=1.1)
    db.add(anlage)
    await db.flush()
    db.add(Monatsdaten(anlage_id=anlage.id, jahr=2026, monat=5,
                       einspeisung_kwh=10.0, netzbezug_kwh=20.0))
    bkw = Investition(anlage_id=anlage.id, typ="balkonkraftwerk", bezeichnung="Balkon",
                      anschaffungsdatum=date(2024, 1, 1), leistung_kwp=1.1)
    db.add(bkw)
    await db.flush()
    kinder = []
    for name in ("Modul Ost", "Modul West"):
        m = Investition(anlage_id=anlage.id, typ="pv-module", bezeichnung=name,
                        anschaffungsdatum=date(2024, 1, 1), leistung_kwp=0.55,
                        parent_investition_id=bkw.id)
        db.add(m)
        kinder.append(m)
    await db.flush()
    if bkw_wert is not None:
        db.add(InvestitionMonatsdaten(investition_id=bkw.id, jahr=2026, monat=5,
                                      verbrauch_daten={"pv_erzeugung_kwh": bkw_wert}))
    if kind1_wert is not None:
        db.add(InvestitionMonatsdaten(investition_id=kinder[0].id, jahr=2026, monat=5,
                                      verbrauch_daten={"pv_erzeugung_kwh": kind1_wert}))
    await db.commit()
    return (await db.execute(
        select(Anlage)
        .options(
            selectinload(Anlage.investitionen).selectinload(Investition.monatsdaten),
            selectinload(Anlage.monatsdaten),
        )
        .where(Anlage.id == anlage.id)
    )).scalars().first()


async def _pv_meldungen(db, anlage):
    checker = DatenChecker(db)
    return checker._check_pv_erzeugung(anlage, list(anlage.monatsdaten))


async def test_checker_meldet_keine_luecke_die_das_bkw_schliesst(db):
    """Der Melder-Fall: ein Modul misst, das Balkonkraftwerk deckt das andere.

    ⚠ Geprüft wird der WORTLAUT, den der Checker wirklich liefert — nicht die
    Abwesenheit eines geratenen Begriffs. Der erste Entwurf dieser Probe suchte
    „teilgemessen"; das Wort kommt in keiner Meldung vor, und sie blieb deshalb
    auch mit entschärftem Fix grün (gemessen 20.09.2026, Sprengsatz-Gegenprobe).
    Gemessen lauten die beiden Lagen:
      mit Fix  → INFO    „PV-Erzeugung über kWp-Anteil geschätzt in 1 Monat(en)"
      ohne Fix → WARNING „PV-Erzeugung unvollständig in 1 Monat(en) — Nur ein
                 Teil der Strings erfasst und kein Gesamtwert zum Verteilen"
    """
    anlage = await _seed_bkw(db, bkw_wert=90.0, kind1_wert=50.0)
    ergebnisse = await _pv_meldungen(db, anlage)
    assert len(ergebnisse) == 1
    e = ergebnisse[0]
    assert "geschätzt" in e.meldung, e.meldung
    assert "unvollständig" not in e.meldung, (
        "der Monat ist über den Wert des Balkonkraftwerks gedeckt — die Rechnung "
        "schließt ihn, der Checker darf ihn nicht als Lücke melden"
    )
    assert str(e.schwere).endswith("INFO"), e.schwere


async def test_checker_meldet_weiter_wenn_niemand_den_monat_traegt(db):
    """⚠ Gegenprobe: ohne BKW-Wert und ohne Anlagen-Aggregat bleibt die echte
    Lücke stehen — der Fix darf keine Meldung stillstellen, die stimmt."""
    anlage = await _seed_bkw(db, bkw_wert=None, kind1_wert=50.0)
    ergebnisse = await _pv_meldungen(db, anlage)
    assert len(ergebnisse) == 1
    assert "unvollständig" in ergebnisse[0].meldung, ergebnisse[0].meldung
    assert str(ergebnisse[0].schwere).endswith("WARNING"), ergebnisse[0].schwere
