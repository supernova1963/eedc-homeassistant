"""N-734 — eine Netzbezugs-/Einspeise-0 ohne Herkunft ist kein Messwert.

**Der Defekt.** ``Monatsdaten.einspeisung_kwh``/``netzbezug_kwh`` sind ``NOT NULL`` mit Default 0. Eine Monatszeile, die
ein Import ohne Netzfelder angelegt hat (Portal-Import nur mit Wallbox-Daten, eigenes Format ohne Netzspalte,
HA-Statistik-Import mit abgewähltem Netzfeld), stand mit 0/0 da — und der gespeicherte Zweig von Cockpit → Monat nahm
diese 0 mit ``is not None`` als Wert: HA-Statistik und Tagesebene waren gesperrt, der Monat zeigte Einspeisung 0,
Netzbezug 0, Autarkie 100 % (gemessen: Wallbox-Import + HA-Statistik PV 1200 / Netzbezug 250 / Einspeisung 700 ⇒
0 / 0 / 100 % statt 250 / 700 / 66,7 %). Der Daten-Checker «Netzbezug nicht erfasst» prüfte ``is None`` und konnte nie
auslösen.

**Die Regel** (``services/monats_fakten/roh.py::netzfeld_ist_erfasst``, Entscheid Master 12.10.2026, Variante A3): ein
Netzfeld ist erfasst, wenn ``source_provenance`` einen Eintrag dafür hat (auch ``legacy:unknown`` der Altzeilen) **oder**
sein Wert ≠ 0 ist. Eine gelieferte 0 bleibt ein Wert (N-707/N-714); nur die 0 ohne Herkunft ist eine Lücke.

Wächter je Fall der Analyse (``opus-berichte/ANALYSE-NEBENFUNDE-T1-T3.md`` §T3, Bericht ``L-N734-T1.md``):
G (Wallbox-only-Import), R (Rohzeile 0/0 ohne Herkunft), C (gelieferte 0), L (Altzeile ``legacy:unknown``),
R2 (Rohzeile mit Werten ohne Herkunft); dazu der Checker und Cockpit → Jahr (dieselben Zahlen wie der Monat).
Schwester: ``test_n735_formular_neuanlage_provenance.py`` (die Formular-Neuanlage trägt ihre Herkunft wieder).
"""

from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from backend.api.routes.data_import import ApplyMonthInput, ApplyRequest, apply_import
from backend.models import Anlage, Investition, Monatsdaten
from backend.services.provenance import seed_provenance
from backend.tests import factories

J, M = 2025, 7
#: HA-Statistik des Monats — Netzbezug 250, Einspeisung 700 ⇒ Eigenverbrauch 500, Autarkie 500/750 = 66,7 %.
HA = {"pv_erzeugung_kwh": 1200.0, "netzbezug_kwh": 250.0, "einspeisung_kwh": 700.0}


async def _anlage(db) -> Anlage:
    a = await factories.anlage(db)
    await factories.strompreis(db, a.id, date(2024, 1, 1),
                               netzbezug_arbeitspreis_cent_kwh=30.0, einspeiseverguetung_cent_kwh=8.0)
    await factories.investition(db, a.id, "pv-module", bezeichnung="Dach", leistung_kwp=10.0)
    await factories.investition(db, a.id, "wallbox", bezeichnung="WB")
    await db.commit()
    return a


def _ha_statistik(monkeypatch, werte: dict) -> None:
    import backend.api.routes.aktueller_monat as am

    async def _leer(*_a, **_k):
        return {}

    async def _ha(anlage, j, m):  # noqa: ARG001
        return {k: (v, am.DatenquelleInfo(quelle="ha_statistics", konfidenz=92)) for k, v in werte.items()}

    monkeypatch.setattr(am, "_collect_connector_data", _leer)
    monkeypatch.setattr(am, "_collect_ha_statistics_data", _ha)


async def _monat(db, monkeypatch, aid: int, ha: dict):
    import backend.api.routes.aktueller_monat as am

    _ha_statistik(monkeypatch, ha)
    return await am.get_aktueller_monat(anlage_id=aid, jahr=J, monat=M, db=db)


async def _rohzeile(db, aid: int, *, legacy: bool = False, **werte) -> Monatsdaten:
    md = Monatsdaten(anlage_id=aid, jahr=J, monat=M, **werte)
    db.add(md)
    await db.flush()
    if legacy:
        # So markiert die Etappe-3d-Migration jede Altzeile (`provenance_migrate.py`).
        seed_provenance(md, source="legacy:unknown", writer="initial_migration",
                        fields=["einspeisung_kwh", "netzbezug_kwh"])
    await db.commit()
    return md


async def _import(db, aid: int, **felder) -> None:
    r = await apply_import(anlage_id=aid, data=ApplyRequest(monate=[ApplyMonthInput(jahr=J, monat=M, **felder)]),
                           ueberschreiben=False, datenquelle="portal_import", db=db)
    assert r.erfolg, r.fehler
    await db.commit()


def _netz(res) -> tuple:
    return res.netzbezug_kwh, res.einspeisung_kwh, res.autarkie_prozent


# ── Cockpit → Monat ─────────────────────────────────────────────────────────────────────────────────────────────


async def test_g_wallbox_import_sperrt_die_ha_statistik_nicht_mehr(db, monkeypatch):
    a = await _anlage(db)
    await _import(db, a.id, wallbox_ladung_kwh=150.0)
    md = (await db.execute(select(Monatsdaten).where(Monatsdaten.anlage_id == a.id))).scalar_one()
    assert (md.netzbezug_kwh, md.einspeisung_kwh, md.source_provenance) == (0.0, 0.0, {}), "Lage wie im Fund"

    res = await _monat(db, monkeypatch, a.id, HA)

    assert _netz(res) == (250.0, 700.0, pytest.approx(66.7, abs=0.05)), "vorher 0 / 0 / 100 %"
    assert res.eigenverbrauch_kwh == pytest.approx(500.0)


async def test_e_ein_feld_geliefert_das_andere_nicht(db, monkeypatch):
    a = await _anlage(db)
    await _import(db, a.id, pv_erzeugung_kwh=1200.0, einspeisung_kwh=700.0)

    res = await _monat(db, monkeypatch, a.id, {"netzbezug_kwh": 250.0})

    assert _netz(res) == (250.0, 700.0, pytest.approx(66.7, abs=0.05)), "vorher Netzbezug 0, Autarkie 100 %"


async def test_r_rohzeile_null_ohne_herkunft_ist_nicht_erfasst(db, monkeypatch):
    a = await _anlage(db)
    await _rohzeile(db, a.id, einspeisung_kwh=0.0, netzbezug_kwh=0.0)

    mit_ha = await _monat(db, monkeypatch, a.id, HA)
    ohne_ha = await _monat(db, monkeypatch, a.id, {"pv_erzeugung_kwh": 1200.0})

    assert _netz(mit_ha) == (250.0, 700.0, pytest.approx(66.7, abs=0.05))
    assert (ohne_ha.netzbezug_kwh, ohne_ha.einspeisung_kwh) == (None, None), "eine Lücke, keine erfundene 0"
    assert ohne_ha.autarkie_prozent is None


async def test_c_gelieferte_null_bleibt_ein_wert(db, monkeypatch):
    a = await _anlage(db)
    await _import(db, a.id, pv_erzeugung_kwh=1200.0, einspeisung_kwh=700.0, netzbezug_kwh=0.0)

    res = await _monat(db, monkeypatch, a.id, HA)

    assert _netz(res) == (0.0, 700.0, 100.0), "die importierte 0 ist ein Messwert (N-707) und schlägt die HA-Statistik"


async def test_l_altzeile_mit_legacy_herkunft_zaehlt_wie_bisher(db, monkeypatch):
    a = await _anlage(db)
    await _rohzeile(db, a.id, legacy=True, einspeisung_kwh=0.0, netzbezug_kwh=0.0)

    res = await _monat(db, monkeypatch, a.id, HA)

    assert _netz(res) == (0.0, 0.0, 100.0), "Bestandsschutz: die Altzeile ist ein gespeicherter Wert"


async def test_r2_rohzeile_mit_werten_ohne_herkunft_zaehlt(db, monkeypatch):
    a = await _anlage(db)
    await _rohzeile(db, a.id, einspeisung_kwh=400.0, netzbezug_kwh=300.0)

    res = await _monat(db, monkeypatch, a.id, HA)

    assert (res.netzbezug_kwh, res.einspeisung_kwh) == (300.0, 400.0), "eine Zahl ≠ 0 ist kein DB-Default"


async def test_jahr_zeigt_dieselben_zahlen_wie_der_monat(db, monkeypatch):
    from backend.api.routes.cockpit.jahr import get_cockpit_jahr

    a = await _anlage(db)
    await _import(db, a.id, wallbox_ladung_kwh=150.0)
    _ha_statistik(monkeypatch, HA)

    jahr = await get_cockpit_jahr(anlage_id=a.id, jahr=J, db=db)

    juli = next(m for m in jahr["monate"] if m["monat"] == M)
    assert (juli["netzbezug_kwh"], juli["einspeisung_kwh"]) == (250.0, 700.0)
    assert juli["autarkie_prozent"] == pytest.approx(66.7, abs=0.05)


# ── Daten-Checker ───────────────────────────────────────────────────────────────────────────────────────────────


async def _checker(db, aid: int) -> list[str]:
    from backend.services.daten_checker import DatenChecker

    anlage = (await db.execute(
        select(Anlage).options(selectinload(Anlage.investitionen).selectinload(Investition.monatsdaten))
        .where(Anlage.id == aid)
    )).scalar_one()
    mds = list((await db.execute(select(Monatsdaten).where(Monatsdaten.anlage_id == aid))).scalars().all())
    erg = await DatenChecker(db)._check_monatsdaten_plausibilitaet(anlage, mds)
    return [f"{e.schwere.value if hasattr(e.schwere, 'value') else e.schwere}|{e.meldung}" for e in erg]


def _netz_meldungen(meldungen: list[str]) -> list[str]:
    return [m for m in meldungen if "nicht erfasst" in m or "beide 0" in m]


async def test_checker_meldet_netzfelder_ohne_herkunft(db):
    a = await _anlage(db)
    await _import(db, a.id, wallbox_ladung_kwh=150.0)

    m = _netz_meldungen(await _checker(db, a.id))

    assert sorted(m) == sorted([
        "error|07/2025: Einspeisung nicht erfasst",
        "error|07/2025: Netzbezug nicht erfasst",
    ]), m


async def test_checker_ein_feld_ohne_herkunft(db):
    a = await _anlage(db)
    await _import(db, a.id, pv_erzeugung_kwh=1200.0, einspeisung_kwh=700.0)

    assert _netz_meldungen(await _checker(db, a.id)) == ["error|07/2025: Netzbezug nicht erfasst"]


async def test_checker_schweigt_bei_gelieferten_werten(db):
    a = await _anlage(db)
    await _import(db, a.id, pv_erzeugung_kwh=1200.0, einspeisung_kwh=700.0, netzbezug_kwh=250.0)

    assert _netz_meldungen(await _checker(db, a.id)) == []


async def test_checker_zwei_erfasste_nullen_nur_die_warnung(db):
    a = await _anlage(db)
    await _import(db, a.id, pv_erzeugung_kwh=1200.0, einspeisung_kwh=0.0, netzbezug_kwh=0.0)

    assert _netz_meldungen(await _checker(db, a.id)) == ["warning|07/2025: Einspeisung und Netzbezug sind beide 0"]


async def test_checker_meldungstext_nennt_voraussetzung_und_handgriff(db):
    from backend.services.daten_checker import DatenChecker

    a = await _anlage(db)
    await _import(db, a.id, wallbox_ladung_kwh=150.0)
    anlage = (await db.execute(
        select(Anlage).options(selectinload(Anlage.investitionen).selectinload(Investition.monatsdaten))
        .where(Anlage.id == a.id)
    )).scalar_one()
    mds = list((await db.execute(select(Monatsdaten).where(Monatsdaten.anlage_id == a.id))).scalars().all())
    erg = await DatenChecker(db)._check_monatsdaten_plausibilitaet(anlage, mds)

    netz = next(e for e in erg if e.meldung.endswith("Netzbezug nicht erfasst"))
    assert "auch 0 ist ein Wert" in netz.details
    assert "Monatsabschluss" in netz.details and "HA-Statistik-Import" in netz.details
    # N-739 (c): erst der Import (holt den Messwert), dann der Monatsabschluss — dort ist das Feld leer, nicht 0.
    assert netz.details.index("HA-Statistik-Import") < netz.details.index("Monatsabschluss")
    assert "ein leeres Feld ist keine 0" in netz.details
    # N-739 (a): `/monatsabschluss/…` öffnete im v4-Frontend den Monat nicht.
    assert netz.link == f"/einstellungen/daten?erfassen={J}-{M:02d}"


# ── Der Helfer selbst ───────────────────────────────────────────────────────────────────────────────────────────


def test_helfer_regel():
    from backend.services.monats_fakten import netzfeld_ist_erfasst

    def _md(wert, prov):
        return Monatsdaten(anlage_id=1, jahr=J, monat=M, netzbezug_kwh=wert, source_provenance=prov)

    eintrag = {"netzbezug_kwh": {"source": "manual:form"}}
    assert netzfeld_ist_erfasst(_md(0.0, eintrag), "netzbezug_kwh") is True
    assert netzfeld_ist_erfasst(_md(0.0, {"netzbezug_kwh": {"source": "legacy:unknown"}}), "netzbezug_kwh") is True
    assert netzfeld_ist_erfasst(_md(0.0, {}), "netzbezug_kwh") is False
    assert netzfeld_ist_erfasst(_md(0.0, {"pv_erzeugung_kwh": {}}), "netzbezug_kwh") is False
    assert netzfeld_ist_erfasst(_md(12.5, {}), "netzbezug_kwh") is True
    assert netzfeld_ist_erfasst(None, "netzbezug_kwh") is False
