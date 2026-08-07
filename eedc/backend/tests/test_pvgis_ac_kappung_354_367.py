"""AC-Kappung im PVGIS-SOLL und BKW im PVGIS-Fanout (#354, #367).

Zwei Meldungen, dieselbe Ursache: **das PVGIS-SOLL kennt die AC-Grenze des
Wechselrichters nicht.**

* **#354** (kingcap1): 6 × 9,68 kWp Module an 7-kW-Geräten. Sein SOLL steigt mit
  korrekt gepflegten Moduldaten um gut ein Drittel, und was der Wechselrichter
  mittags abriegelt, taucht im SOLL/IST-Vergleich als Minus auf, das er nicht zu
  verantworten hat.
* **#367** (azywietz-web): 4 × 500 Wp an einem 800-W-Mikrowechselrichter — und
  zusätzlich filterten beide PVGIS-Endpunkte hart auf `pv-module`, sodass eine
  reine Balkonkraftwerk-Anlage überhaupt kein SOLL bekam.

Der schwierige Teil ist die **geteilte** Grenze: sie gehört dem Wechselrichter,
nicht der Himmelsrichtung. Am Demo-Bestand (Süd 12 · Ost 5 · West 3 kWp an einem
10-kW-Fronius) gemessen — je String einzeln gekappt hätte **gar nichts** gekappt,
weil kein einzelner String allein 10 kW erreicht, obwohl das Gerät in Summe
1.227 kWh im Jahr nie liefern kann.
"""

from __future__ import annotations

from datetime import date, datetime

import pytest

from backend.models import Anlage, Investition
from backend.services.daten_checker import DatenChecker
from backend.services.daten_checker.kategorien import CheckSeverity
from backend.services.wetter.pvgis_kappung import (
    KappungsModul,
    monats_kappungsfaktoren,
)


# ── Faktor-Bildung (ohne Netz) ─────────────────────────────────────────────

@pytest.fixture
def seriescalc_stub(monkeypatch):
    """`_fetch_seriescalc` ohne HTTP: ein Tag, eine Spitzenstunde je Monat.

    Profil je kWp und Monat: 0,0 / 0,5 / 1,0 / 0,5 — die dritte Stunde ist die
    einzige, die an eine Grenze stoßen kann.
    """
    from backend.services.wetter import pvgis_kappung as mod

    async def _stub(latitude, longitude, peak_power, tilt, azimuth, losses,
                    user_horizon=None):
        profil = []
        for monat in range(1, 13):
            for anteil in (0.0, 0.5, 1.0, 0.5):
                profil.append((monat, peak_power * anteil))
        return profil

    monkeypatch.setattr(mod, "_fetch_seriescalc", _stub)


async def test_ohne_grenze_wird_pvgis_gar_nicht_zusaetzlich_gefragt(monkeypatch):
    """Der teure Zweitabruf darf nur laufen, wo er etwas ändert."""
    from backend.services.wetter import pvgis_kappung as mod

    async def _explodiere(*a, **kw):
        raise AssertionError("seriescalc darf hier nicht gerufen werden")

    monkeypatch.setattr(mod, "_fetch_seriescalc", _explodiere)

    faktoren = await monats_kappungsfaktoren(
        latitude=48.0, longitude=11.0, losses=14.0,
        module=[KappungsModul(id=1, kwp=8.0, grenze_kw=None, grenz_id=None,
                              abrufe=[(8.0, 30.0, 0.0)])],
    )

    assert faktoren == {}


async def test_faktor_kappt_nur_die_spitzenstunde(seriescalc_stub):
    """2 kWp an 0,8 kW: Σ roh 2×(0+1+2+1)=… je Monat, gekappt bei 0,8."""
    faktoren = await monats_kappungsfaktoren(
        latitude=48.0, longitude=11.0, losses=14.0,
        module=[KappungsModul(id=7, kwp=2.0, grenze_kw=0.8, grenz_id="inv:7",
                              abrufe=[(2.0, 30.0, 0.0)])],
    )

    # roh je Monat: 0 + 1,0 + 2,0 + 1,0 = 4,0 kWh
    # gekappt:      0 + 0,8 + 0,8 + 0,8 = 2,4 kWh
    assert faktoren[7] == pytest.approx([2.4 / 4.0] * 12)


async def test_zwei_strings_an_einem_geraet_teilen_sich_die_grenze(seriescalc_stub):
    """Der Kern von #354 — und die Gegenprobe dazu.

    Zwei 5-kWp-Strings an einem 7-kW-Gerät: einzeln erreicht keiner die Grenze
    (Spitze 5 kW), gemeinsam schon (10 kW). Wer je String kappte, käme auf
    Faktor 1,0 und hätte nichts getan.
    """
    module = [
        KappungsModul(id=1, kwp=5.0, grenze_kw=7.0, grenz_id="wr:9",
                      abrufe=[(5.0, 30.0, -90.0)]),
        KappungsModul(id=2, kwp=5.0, grenze_kw=7.0, grenz_id="wr:9",
                      abrufe=[(5.0, 30.0, 90.0)]),
    ]

    faktoren = await monats_kappungsfaktoren(
        latitude=48.0, longitude=11.0, losses=14.0, module=module,
    )

    # roh je String und Monat: 0 + 2,5 + 5,0 + 2,5 = 10,0 kWh
    # gemeinsam: Stunde 2 → 5,0 ≤ 7 (frei), Stunde 3 → 10,0 > 7 ⇒ je 3,5
    #            Stunde 4 → 5,0 ≤ 7 (frei)  ⇒ 0 + 2,5 + 3,5 + 2,5 = 8,5
    assert faktoren[1] == pytest.approx([8.5 / 10.0] * 12)
    assert faktoren[2] == pytest.approx([8.5 / 10.0] * 12)
    assert faktoren[1][0] < 1.0, "je String gekappt wäre das 1,0 — der Fehler von #354"


async def test_abrufausfall_liefert_keine_geratenen_faktoren(monkeypatch):
    """Ein ungekapptes SOLL ist eine bekannte Größe, ein halb gekapptes nicht."""
    from backend.services.wetter import pvgis_kappung as mod

    async def _kaputt(*a, **kw):
        raise RuntimeError("PVGIS nicht erreichbar")

    monkeypatch.setattr(mod, "_fetch_seriescalc", _kaputt)

    faktoren = await monats_kappungsfaktoren(
        latitude=48.0, longitude=11.0, losses=14.0,
        module=[KappungsModul(id=1, kwp=2.0, grenze_kw=0.8, grenz_id="inv:1",
                              abrufe=[(2.0, 30.0, 0.0)])],
    )

    assert faktoren == {}


# ── PVGIS-Route: das Balkonkraftwerk bekommt ein SOLL ──────────────────────

@pytest.fixture
def pvgis_stub(monkeypatch):
    """`_berechne_pvgis_modul` deterministisch: 1000 kWh je kWp, keine HTTP-I/O."""
    from backend.api.routes import pvgis as pvgis_mod
    from backend.api.routes.pvgis import PVGISMonthlyData

    async def _stub(*, leistung_kwp, **_):
        monate = [PVGISMonthlyData(monat=m, e_m=leistung_kwp * 1000 / 12,
                                   h_m=100.0, sd_m=10.0) for m in range(1, 13)]
        # Dritter Rückgabewert seit #363: der Strahlungsdatensatz.
        return monate, leistung_kwp * 1000, "PVGIS-SARAH3"

    monkeypatch.setattr(pvgis_mod, "_berechne_pvgis_modul", _stub)


@pytest.fixture
def keine_kappung(monkeypatch):
    """Kappung aus, damit die Typ-Erweiterung für sich geprüft werden kann."""
    from backend.api.routes import pvgis as pvgis_mod

    async def _stub(**_):
        return {}

    monkeypatch.setattr(pvgis_mod, "monats_kappungsfaktoren", _stub)


async def _reine_bkw_anlage(db) -> int:
    anlage = Anlage(anlagenname="Balkon", leistung_kwp=2.0,
                    latitude=48.0, longitude=11.0)
    db.add(anlage)
    await db.flush()
    db.add(Investition(
        anlage_id=anlage.id, typ="balkonkraftwerk", bezeichnung="Solarbank",
        anschaffungsdatum=date(2024, 1, 1),
        parameter={"leistung_wp": 500, "anzahl": 4,
                   "wechselrichter_leistung_w": 800,
                   "ausrichtung_grad": 0, "neigung_grad": 30},
    ))
    await db.commit()
    return anlage.id


async def test_reine_bkw_anlage_bekommt_eine_prognose_statt_400(
    db, pvgis_stub, keine_kappung,
):
    """#367: der harte Typ-Filter ließ azywietz-web mit einem 400er stehen."""
    from backend.api.routes.pvgis import get_pvgis_prognose

    prognose = await get_pvgis_prognose(anlage_id=await _reine_bkw_anlage(db), db=db)

    assert len(prognose.module) == 1
    assert prognose.gesamt_leistung_kwp == pytest.approx(2.0), (
        "kWp über get_erzeuger_kwp: 4 × 500 Wp"
    )
    assert prognose.module[0].neigung_grad == 30


async def test_das_bkw_soll_wird_an_der_ac_grenze_gekappt(db, pvgis_stub, monkeypatch):
    """Ohne Kappung wäre sein SOLL systematisch unerreichbar (2 kWp an 800 W)."""
    from backend.api.routes import pvgis as pvgis_mod
    from backend.api.routes.pvgis import get_pvgis_prognose

    async def _faktoren(*, module, **_):
        assert [m.grenze_kw for m in module] == [pytest.approx(0.8)], (
            "die eigene Grenze des BKW muss ankommen"
        )
        return {module[0].id: [0.5] * 12}

    monkeypatch.setattr(pvgis_mod, "monats_kappungsfaktoren", _faktoren)

    prognose = await get_pvgis_prognose(anlage_id=await _reine_bkw_anlage(db), db=db)

    assert prognose.jahresertrag_kwh == pytest.approx(1000.0, abs=1.0), (
        "2 kWp × 1000 kWh/kWp × Faktor 0,5"
    )


async def test_ohne_gepflegte_grenze_bleibt_das_soll_unveraendert(db, pvgis_stub, monkeypatch):
    """Der Regelfall: keine AC-Grenze ⇒ bitgleich zu vorher."""
    from backend.api.routes import pvgis as pvgis_mod
    from backend.api.routes.pvgis import get_pvgis_prognose

    gerufen: list[list] = []

    async def _faktoren(*, module, **_):
        gerufen.append(module)
        return {}

    monkeypatch.setattr(pvgis_mod, "monats_kappungsfaktoren", _faktoren)

    anlage = Anlage(anlagenname="Dach", leistung_kwp=8.0,
                    latitude=48.0, longitude=11.0)
    db.add(anlage)
    await db.flush()
    db.add(Investition(anlage_id=anlage.id, typ="pv-module", bezeichnung="Süd",
                       anschaffungsdatum=date(2024, 1, 1), leistung_kwp=8.0,
                       ausrichtung="Süd", neigung_grad=30))
    await db.commit()

    prognose = await get_pvgis_prognose(anlage_id=anlage.id, db=db)

    assert prognose.jahresertrag_kwh == pytest.approx(8000.0)
    assert [m.grenze_kw for m in gerufen[0]] == [None], (
        "ohne Wechselrichter darf keine Grenze entstehen"
    )


async def test_strings_eines_wechselrichters_kommen_mit_geteilter_kennung_an(
    db, pvgis_stub, monkeypatch,
):
    """Die Route muss die Grenze am Parent auflösen — sonst kappt nichts."""
    from backend.api.routes import pvgis as pvgis_mod
    from backend.api.routes.pvgis import get_pvgis_prognose

    gesehen: list = []

    async def _faktoren(*, module, **_):
        gesehen.extend(module)
        return {}

    monkeypatch.setattr(pvgis_mod, "monats_kappungsfaktoren", _faktoren)

    anlage = Anlage(anlagenname="Carport", leistung_kwp=20.0,
                    latitude=48.0, longitude=11.0)
    db.add(anlage)
    await db.flush()
    wr = Investition(anlage_id=anlage.id, typ="wechselrichter", bezeichnung="Fronius",
                     anschaffungsdatum=date(2024, 1, 1),
                     parameter={"max_leistung_kw": 10})
    db.add(wr)
    await db.flush()
    db.add_all([
        Investition(anlage_id=anlage.id, typ="pv-module", bezeichnung="Ost",
                    anschaffungsdatum=date(2024, 1, 1), leistung_kwp=5.0,
                    ausrichtung="Ost", neigung_grad=25,
                    parent_investition_id=wr.id),
        Investition(anlage_id=anlage.id, typ="pv-module", bezeichnung="West",
                    anschaffungsdatum=date(2024, 1, 1), leistung_kwp=3.0,
                    ausrichtung="West", neigung_grad=25,
                    parent_investition_id=wr.id),
    ])
    await db.commit()

    await get_pvgis_prognose(anlage_id=anlage.id, db=db)

    assert {m.grenz_id for m in gesehen} == {f"wr:{wr.id}"}, (
        "beide Strings gehören in denselben Kappungs-Pool"
    )
    assert all(m.grenze_kw == pytest.approx(10.0) for m in gesehen)


# ── Daten-Checker: Überbelegung ist der Normalfall ─────────────────────────

async def _anlage_mit_wr(db, *, modul_kwp: float, wr_kw: float) -> Anlage:
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload

    anlage = Anlage(anlagenname="Test", leistung_kwp=modul_kwp,
                    installationsdatum=date(2024, 1, 1))
    db.add(anlage)
    await db.flush()
    wr = Investition(anlage_id=anlage.id, typ="wechselrichter", bezeichnung="WR",
                     anschaffungsdatum=date(2024, 1, 1),
                     parameter={"max_leistung_kw": wr_kw})
    db.add(wr)
    await db.flush()
    db.add(Investition(anlage_id=anlage.id, typ="pv-module", bezeichnung="Dach",
                       anschaffungsdatum=date(2024, 1, 1), leistung_kwp=modul_kwp,
                       ausrichtung="Süd", neigung_grad=30,
                       parent_investition_id=wr.id))
    await db.commit()
    return (await db.execute(
        select(Anlage)
        .options(selectinload(Anlage.investitionen).selectinload(Investition.monatsdaten))
        .where(Anlage.id == anlage.id)
    )).scalar_one()


async def test_ueberbelegung_wird_nicht_angemeckert(db):
    """#354: 9,68 kWp an 7 kW = 1,38 — normale Auslegung, kein Befund.

    Ein Check, der das meldet, erzieht den Anwender dazu, falsche Zahlen
    einzutragen, damit Ruhe ist.
    """
    anlage = await _anlage_mit_wr(db, modul_kwp=9.68, wr_kw=7.0)

    ergebnisse = DatenChecker(db)._check_stammdaten(anlage)

    assert not [r for r in ergebnisse if "Wechselrichter-Leistung" in r.meldung], (
        f"Überbelegung ist normal: {[r.meldung for r in ergebnisse]}"
    )


async def test_absurdes_verhaeltnis_meldet_und_nennt_die_wahrscheinliche_ursache(db):
    """Oberhalb 2,0 ist ein Pflegefehler wahrscheinlicher als eine Auslegung."""
    anlage = await _anlage_mit_wr(db, modul_kwp=20.0, wr_kw=5.0)

    ergebnisse = DatenChecker(db)._check_stammdaten(anlage)

    treffer = [r for r in ergebnisse if "Wechselrichter-Leistung" in r.meldung]
    assert len(treffer) == 1, f"Befund erwartet: {[r.meldung for r in ergebnisse]}"
    assert treffer[0].schwere == CheckSeverity.WARNING
    assert "4.00" in treffer[0].details
    assert "Leistung (kWp)" in treffer[0].details, "der Anwender braucht den Weg"


async def test_ohne_gepflegte_wr_leistung_wird_nichts_behauptet(db):
    """`None` heißt „nicht gepflegt", nicht „0" — kein Verhältnis, keine Meldung."""
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload

    anlage = Anlage(anlagenname="Test", leistung_kwp=20.0,
                    installationsdatum=date(2024, 1, 1))
    db.add(anlage)
    await db.flush()
    wr = Investition(anlage_id=anlage.id, typ="wechselrichter", bezeichnung="WR",
                     anschaffungsdatum=date(2024, 1, 1), parameter={})
    db.add(wr)
    await db.flush()
    db.add(Investition(anlage_id=anlage.id, typ="pv-module", bezeichnung="Dach",
                       anschaffungsdatum=date(2024, 1, 1), leistung_kwp=20.0,
                       ausrichtung="Süd", neigung_grad=30,
                       parent_investition_id=wr.id))
    await db.commit()
    anlage = (await db.execute(
        select(Anlage)
        .options(selectinload(Anlage.investitionen).selectinload(Investition.monatsdaten))
        .where(Anlage.id == anlage.id)
    )).scalar_one()

    ergebnisse = DatenChecker(db)._check_stammdaten(anlage)

    assert not [r for r in ergebnisse if "Wechselrichter-Leistung" in r.meldung]
