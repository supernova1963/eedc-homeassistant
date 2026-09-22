"""Die PVGIS-Kappungsgrenze sieht nur die HEUTE laufenden Speicher
(Nachlese 4.0.50, A3).

**Der Filter stand schon da — eine Abfrage weiter.** Beide PVGIS-Endpunkte holen
drei Mengen für `zuordne_grenzen`: Erzeuger (**mit** `aktiv_jetzt()`),
Wechselrichter und Speicher (**ohne**). Genau die dritte entscheidet über F-11:
hängt am Träger der Grenze ein **DC-gekoppelter** Speicher, liefert
`zuordne_grenzen` `(None, None)` — es wird **gar nicht gekappt**, weil der
Überschuss gleichstromseitig in den Akku läuft.

**Die Folge eines ausgebauten DC-Speichers ist deshalb ein dauerhaft zu hohes
SOLL:** 20 kWp an einem 10-kW-Wechselrichter blieben ungekappt, weil eedc einen
Akku mitrechnete, der nicht mehr im Keller steht. Das ist die unangenehme
Richtung — der SOLL/IST-Vergleich zeigt dem Anwender ein Minus, das er nicht zu
verantworten hat (dieselbe Wirkung, die #354 ausgelöst hat, nur aus einer anderen
Ursache).

Geprüft wird **am Eingang von `zuordne_grenzen`** (die Speicher-Liste, die
ankommt) **und an der Wirkung** (die Grenze, die bei `monats_kappungsfaktoren`
landet) — der Eingang allein wäre eine Aussage über eine Variable, nicht über die
Prognose.

⚠ **Feste Daten, kein `date.today()`** (`test_konformitaet_echte_uhr_in_tests.py`).
"""

from __future__ import annotations

from datetime import date

import pytest

from backend.models import Anlage, Investition

STILLGELEGT_VERGANGENHEIT = date(2021, 3, 31)
STILLGELEGT_ZUKUNFT = date(2099, 12, 31)


@pytest.fixture
def pvgis_stub(monkeypatch):
    """`_berechne_pvgis_modul` deterministisch: 1000 kWh je kWp, keine HTTP-I/O."""
    from backend.api.routes import pvgis as pvgis_mod
    from backend.api.routes.pvgis import PVGISMonthlyData

    async def _stub(*, leistung_kwp, **_):
        monate = [PVGISMonthlyData(monat=m, e_m=leistung_kwp * 1000 / 12,
                                   h_m=100.0, sd_m=10.0) for m in range(1, 13)]
        return monate, leistung_kwp * 1000, "PVGIS-SARAH3"

    monkeypatch.setattr(pvgis_mod, "_berechne_pvgis_modul", _stub)


@pytest.fixture
def mitschrift(monkeypatch):
    """Schreibt mit, welche Speicher bei `zuordne_grenzen` ankommen — und kappt nicht.

    ``zuordne_grenzen`` bleibt die **echte** Funktion: die Probe soll ihr
    Verhalten messen, nicht ersetzen.
    """
    from backend.api.routes import pvgis as pvgis_mod

    echt = pvgis_mod.zuordne_grenzen
    notiert: dict = {"speicher_ids": None, "grenzen": None, "kappungs_module": None}

    def _mit(erzeuger, wechselrichter, speicher):
        notiert["speicher_ids"] = sorted(s.id for s in speicher)
        notiert["grenzen"] = echt(erzeuger, wechselrichter, speicher)
        return notiert["grenzen"]

    async def _faktoren(*, module, **_):
        notiert["kappungs_module"] = {m.id: m.grenze_kw for m in module}
        return {}

    monkeypatch.setattr(pvgis_mod, "zuordne_grenzen", _mit)
    monkeypatch.setattr(pvgis_mod, "monats_kappungsfaktoren", _faktoren)
    return notiert


async def _anlage_mit_dc_speicher(
    db, *, aktiv: bool = True, stillgelegt: date | None = STILLGELEGT_VERGANGENHEIT,
) -> tuple[int, int, int]:
    """20 kWp an einem 10-kW-Wechselrichter, daran ein DC-gekoppelter Speicher.

    Der Speicher hängt per `parent_investition_id` am Wechselrichter — laut
    `_dc_speicher_traeger` heißt gesetzter Parent DC-Kopplung, und genau das
    setzt die Grenze außer Kraft.
    """
    anlage = Anlage(anlagenname="A3", leistung_kwp=20.0,
                    latitude=48.0, longitude=11.0)
    db.add(anlage)
    await db.flush()

    wr = Investition(
        anlage_id=anlage.id, typ="wechselrichter", bezeichnung="Fronius 10 kW",
        anschaffungsdatum=date(2015, 1, 1),
        parameter={"max_leistung_kw": 10.0},
    )
    db.add(wr)
    await db.flush()

    modul = Investition(
        anlage_id=anlage.id, typ="pv-module", bezeichnung="Dach Süd",
        anschaffungsdatum=date(2015, 1, 1), leistung_kwp=20.0,
        parent_investition_id=wr.id,
        parameter={"ausrichtung_grad": 0, "neigung_grad": 30},
    )
    db.add(modul)
    speicher = Investition(
        anlage_id=anlage.id, typ="speicher", bezeichnung="Akku (ausgebaut)",
        anschaffungsdatum=date(2015, 1, 1), parent_investition_id=wr.id,
        parameter={"kapazitaet_kwh": 10.0},
        aktiv=aktiv, stilllegungsdatum=stillgelegt,
    )
    db.add(speicher)
    await db.commit()
    return anlage.id, modul.id, speicher.id


# ── Anlagen-Prognose ────────────────────────────────────────────────────────


async def test_ausgebauter_dc_speicher_setzt_die_kappung_nicht_mehr_aus(
    db, pvgis_stub, mitschrift,
):
    from backend.api.routes.pvgis import get_pvgis_prognose

    anlage_id, modul_id, speicher_id = await _anlage_mit_dc_speicher(db)

    await get_pvgis_prognose(anlage_id=anlage_id, db=db)

    assert mitschrift["speicher_ids"] == [], (
        "der ausgebaute Speicher darf `zuordne_grenzen` nicht mehr erreichen"
    )
    assert mitschrift["grenzen"][modul_id][0] == pytest.approx(10.0), (
        "ungefiltert stünde hier (None, None) — die Kappung fiele ganz aus"
    )
    assert mitschrift["kappungs_module"][modul_id] == pytest.approx(10.0)


async def test_abgewaehlter_dc_speicher_ohne_datum_zaehlt_auch_nicht(
    db, pvgis_stub, mitschrift,
):
    """`aktiv=False` = wie gelöscht — dieselbe Regel wie in `investition_filter`."""
    from backend.api.routes.pvgis import get_pvgis_prognose

    anlage_id, modul_id, _ = await _anlage_mit_dc_speicher(
        db, aktiv=False, stillgelegt=None,
    )

    await get_pvgis_prognose(anlage_id=anlage_id, db=db)

    assert mitschrift["speicher_ids"] == []
    assert mitschrift["grenzen"][modul_id][0] == pytest.approx(10.0)


async def test_laufender_dc_speicher_setzt_die_kappung_weiter_aus(
    db, pvgis_stub, mitschrift,
):
    """F-11 bleibt, wie es war — die Gegenrichtung.

    Ohne diesen Fall wäre nicht belegt, dass der Filter **nur** das ausgebaute
    Gerät entfernt und nicht die Regel selbst abgeschaltet hat.
    """
    from backend.api.routes.pvgis import get_pvgis_prognose

    anlage_id, modul_id, speicher_id = await _anlage_mit_dc_speicher(
        db, stillgelegt=None,
    )

    await get_pvgis_prognose(anlage_id=anlage_id, db=db)

    assert mitschrift["speicher_ids"] == [speicher_id]
    assert mitschrift["grenzen"][modul_id] == (None, None), "F-11: DC-Akku ⇒ keine Kappung"
    assert mitschrift["kappungs_module"][modul_id] is None


async def test_stilllegung_in_der_zukunft_ist_noch_kein_ausbau(
    db, pvgis_stub, mitschrift,
):
    """Der Stichtag wird gelesen, nicht die Anwesenheit eines Datums."""
    from backend.api.routes.pvgis import get_pvgis_prognose

    anlage_id, modul_id, speicher_id = await _anlage_mit_dc_speicher(
        db, stillgelegt=STILLGELEGT_ZUKUNFT,
    )

    await get_pvgis_prognose(anlage_id=anlage_id, db=db)

    assert mitschrift["speicher_ids"] == [speicher_id]
    assert mitschrift["grenzen"][modul_id] == (None, None)


# ── Einzel-Modul-Prognose (dieselbe Stelle, zweite Abfrage) ─────────────────


async def test_modul_route_filtert_den_ausgebauten_speicher_ebenso(
    db, pvgis_stub, mitschrift,
):
    from backend.api.routes.pvgis import get_pvgis_modul_prognose

    _, modul_id, _ = await _anlage_mit_dc_speicher(db)

    await get_pvgis_modul_prognose(investition_id=modul_id, db=db)

    assert mitschrift["speicher_ids"] == []
    assert mitschrift["grenzen"][modul_id][0] == pytest.approx(10.0)


async def test_modul_route_laesst_den_laufenden_speicher_wirken(
    db, pvgis_stub, mitschrift,
):
    from backend.api.routes.pvgis import get_pvgis_modul_prognose

    _, modul_id, speicher_id = await _anlage_mit_dc_speicher(db, stillgelegt=None)

    await get_pvgis_modul_prognose(investition_id=modul_id, db=db)

    assert mitschrift["speicher_ids"] == [speicher_id]
    assert mitschrift["grenzen"][modul_id] == (None, None)
