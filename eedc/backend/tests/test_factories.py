"""Die Factories aus `factories.py` prüfen sich selbst (Etappe E4 / M6).

Eine Factory, die falsch baut, macht **jeden** Test still falsch, der sie
benutzt — sie ist damit selbst eine Wächter-Fläche und keine Bequemlichkeit.
Geprüft wird dreierlei: das Pflichtfeld kommt an, der Default steht, und
**der Aufrufer schlägt den Default** (sonst hielte die Factory einen Test grün,
der genau dieses Feld behauptet).
"""

from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import select

from backend.models import Anlage, Investition, InvestitionMonatsdaten, Monatsdaten
from backend.tests.factories import (
    anlage,
    anlage_mit_modul,
    anlage_mit_pv,
    anlage_mit_tarif,
    imd,
    investition,
    mach_anlage,
    mach_anlage_mit_mapping,
    mach_imd,
    mach_investition,
    mach_kennzahlen,
    mach_monats_fakt,
    mach_monatsdaten,
    monatsdaten,
    strompreis,
    zwei_wechselrichter,
)


# ── §1 Modell-Factories ──────────────────────────────────────────────────────

def test_mach_anlage_setzt_die_beiden_defaults():
    a = mach_anlage()
    assert a.anlagenname == "Test"
    assert a.leistung_kwp == 10.0


def test_mach_anlage_erfindet_kein_land():
    """`standort_land` steuert die Kraftstoffpreis-Herkunft — kein Default."""
    assert mach_anlage().standort_land is None


@pytest.mark.asyncio
async def test_anlage_flusht_und_vergibt_eine_id(db):
    a = await anlage(db)
    assert a.id is not None
    gelesen = (await db.execute(select(Anlage).where(Anlage.id == a.id))).scalar_one()
    assert gelesen.anlagenname == "Test"


@pytest.mark.asyncio
async def test_aufrufer_schlaegt_den_default(db):
    """Die Gegenprobe: ein übergebener Wert darf nicht vom Default verdeckt werden."""
    a = await anlage(db, anlagenname="Eigen", leistung_kwp=7.5, standort_land="AT")
    assert (a.anlagenname, a.leistung_kwp, a.standort_land) == ("Eigen", 7.5, "AT")


def test_mach_investition_faellt_mit_der_bezeichnung_auf_den_typ_zurueck():
    assert mach_investition("speicher").bezeichnung == "speicher"
    assert mach_investition("speicher", bezeichnung="Akku").bezeichnung == "Akku"


@pytest.mark.asyncio
async def test_investition_haengt_an_der_anlage(db):
    a = await anlage(db)
    inv = await investition(db, a.id, "pv-module", leistung_kwp=5.0)
    assert inv.id is not None
    assert inv.anlage_id == a.id
    assert inv.anschaffungsdatum == date(2024, 1, 1)
    assert inv.leistung_kwp == 5.0


def test_mach_imd_traegt_alle_vier_pflichtfelder():
    x = mach_imd(3, 2025, 7, {"pv_erzeugung_kwh": 42.0})
    assert (x.investition_id, x.jahr, x.monat) == (3, 2025, 7)
    assert x.verbrauch_daten == {"pv_erzeugung_kwh": 42.0}


@pytest.mark.asyncio
async def test_imd_landet_in_der_db(db):
    a = await anlage(db)
    inv = await investition(db, a.id, "waermepumpe")
    await imd(db, inv.id, 2025, 3, {"stromverbrauch_kwh": 120.0})
    await db.flush()
    gelesen = (await db.execute(
        select(InvestitionMonatsdaten)
        .where(InvestitionMonatsdaten.investition_id == inv.id)
    )).scalar_one()
    assert gelesen.verbrauch_daten["stromverbrauch_kwh"] == 120.0


def test_mach_monatsdaten_setzt_null_statt_zu_raten():
    m = mach_monatsdaten(1, 2025, 5)
    assert m.netzbezug_kwh == 0.0
    assert m.einspeisung_kwh == 0.0


@pytest.mark.asyncio
async def test_monatsdaten_landet_in_der_db(db):
    a = await anlage(db)
    await monatsdaten(db, a.id, 2025, 5, netzbezug_kwh=300.0, einspeisung_kwh=150.0)
    await db.flush()
    gelesen = (await db.execute(
        select(Monatsdaten).where(Monatsdaten.anlage_id == a.id)
    )).scalar_one()
    assert (gelesen.netzbezug_kwh, gelesen.einspeisung_kwh) == (300.0, 150.0)


@pytest.mark.asyncio
async def test_strompreis_verlangt_beide_preise(db):
    a = await anlage(db)
    p = await strompreis(
        db, a.id, date(2023, 1, 1),
        netzbezug_arbeitspreis_cent_kwh=30.0, einspeiseverguetung_cent_kwh=8.0,
    )
    await db.flush()
    assert p.netzbezug_arbeitspreis_cent_kwh == 30.0
    assert p.einspeiseverguetung_cent_kwh == 8.0


def test_strompreis_hat_keine_preis_defaults():
    """Ein erfundener Tarif wäre die P8-Klasse — die Preise sind die Aussage."""
    import inspect
    sig = inspect.signature(strompreis)
    for feld in ("netzbezug_arbeitspreis_cent_kwh", "einspeiseverguetung_cent_kwh"):
        assert sig.parameters[feld].default is inspect.Parameter.empty


# ── §2 Szenarien ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_anlage_mit_pv_baut_modul_und_mapping(db):
    a = await anlage_mit_pv(db, {"basis": {}})
    assert a.sensor_mapping == {"basis": {}}
    inv = (await db.execute(
        select(Investition).where(Investition.anlage_id == a.id)
    )).scalar_one()
    assert inv.typ == "pv-module"
    assert inv.anschaffungsdatum == date(2020, 1, 1)


def test_mach_anlage_mit_mapping_traegt_basis_und_investitionen():
    a = mach_anlage_mit_mapping("S0-Test")
    assert a.anlagenname == "S0-Test"
    assert a.standort_land == "DE"
    assert set(a.sensor_mapping["basis"]) == {"einspeisung", "netzbezug"}
    assert set(a.sensor_mapping["investitionen"]) == {"3", "7"}


@pytest.mark.asyncio
async def test_anlage_mit_tarif_legt_den_tarif_an(db):
    from backend.models import Strompreis
    a = await anlage_mit_tarif(db, "Tarif-Test")
    await db.flush()
    p = (await db.execute(
        select(Strompreis).where(Strompreis.anlage_id == a.id)
    )).scalar_one()
    assert (p.netzbezug_arbeitspreis_cent_kwh, p.einspeiseverguetung_cent_kwh) == (30.0, 8.0)
    assert p.grundpreis_euro_monat == 0.0


@pytest.mark.asyncio
async def test_anlage_mit_modul_reicht_bezeichnung_und_ausrichtung_durch(db):
    """Die Bezeichnung ist Parameter, weil ein Nutzer sie in der Meldung behauptet."""
    a = await anlage_mit_modul(
        db, anlagen_kwp=9.0, spalte=4.5, parameter={},
        bezeichnung="Dach Nord-West", ausrichtung="Nord-West",
    )
    assert a.leistung_kwp == 9.0
    assert [(i.bezeichnung, i.ausrichtung) for i in a.investitionen] == [
        ("Dach Nord-West", "Nord-West")
    ]


@pytest.mark.asyncio
async def test_zwei_wechselrichter_haengt_die_module_unter_die_wr(db):
    ids = await zwei_wechselrichter(db)
    assert set(ids) == {"anlage", "Sofar 2200", "Sofar 1100"}
    for name in ("Sofar 2200", "Sofar 1100"):
        modul = (await db.execute(
            select(Investition).where(Investition.id == ids[name]["modul"])
        )).scalar_one()
        assert modul.parent_investition_id == ids[name]["wr"]
        assert "speicher" not in ids[name]


@pytest.mark.asyncio
async def test_zwei_wechselrichter_mit_speicher(db):
    ids = await zwei_wechselrichter(db, mit_speicher=True)
    for name in ("Sofar 2200", "Sofar 1100"):
        sp = (await db.execute(
            select(Investition).where(Investition.id == ids[name]["speicher"])
        )).scalar_one()
        assert sp.typ == "speicher"
        assert sp.parent_investition_id == ids[name]["wr"]


# ── §3 Werte-Fakten ──────────────────────────────────────────────────────────

def test_mach_kennzahlen_setzt_alle_sieben_pflichtfelder_auf_null():
    k = mach_kennzahlen()
    assert k.eigenverbrauch_kwh == 0.0
    assert k.autarkie_prozent == 0.0
    assert k.direktverbrauchsquote_prozent == 0.0


def test_mach_kennzahlen_erfindet_keinen_wert():
    """Ein Default > 0 hielte jede CO₂-Probe still gruen."""
    k = mach_kennzahlen()
    for feld in k.__dataclass_fields__:
        assert getattr(k, feld) == 0.0, feld


def test_der_aufrufer_schlaegt_den_kennzahlen_default():
    assert mach_kennzahlen(eigenverbrauch_kwh=1234.5).eigenverbrauch_kwh == 1234.5


def test_mach_monats_fakt_fuellt_alle_acht_teil_fakten():
    f = mach_monats_fakt()
    assert (f.jahr, f.monat) == (2026, 6)
    for teil in ("zaehler", "erzeugung", "bkw", "speicher", "emob", "wp",
                 "sonstiges", "tarif", "eeg", "kennzahlen", "meta"):
        assert getattr(f, teil) is not None, teil


def test_mach_monats_fakt_traegt_ueberall_nullen():
    f = mach_monats_fakt()
    assert f.erzeugung.pv_kwh == 0.0
    assert f.wp.waerme_kwh == 0.0
    assert f.emob.km == 0.0
    assert f.kennzahlen.eigenverbrauch_kwh == 0.0


def test_der_aufrufer_schlaegt_jeden_teil_fakt():
    f = mach_monats_fakt(
        jahr=2024, monat=1,
        kennzahlen=mach_kennzahlen(eigenverbrauch_kwh=500.0),
    )
    assert (f.jahr, f.monat) == (2024, 1)
    assert f.kennzahlen.eigenverbrauch_kwh == 500.0
    assert f.wp.waerme_kwh == 0.0        # unberuehrte Teile bleiben leer
