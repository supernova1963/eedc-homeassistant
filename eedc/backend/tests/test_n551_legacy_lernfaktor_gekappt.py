"""Ein Faktor je Basis — der Legacy-Lernfaktor und die Abregelung (N-551).

**Der Befund** (Nebenfund NF-1 des N-547-Baus, von der Nachmessung
reproduziert): ``live_wetter._get_lernfaktor_detail`` lernt Σ IST / Σ
``pv_prognose_kwh``. Dieses Feld ist seit N-547 (W1) ausdrücklich **roh** —
ungekappt und unkorrigiert. An einer r28-Messkopie mit gesäter 12-kW-Grenze:
roh Σ 157,37 kWh, gekappt 137,85, Abregelung 19,52, IST 127,25 ⇒ der Faktor
steht bei **0,809** statt **0,923**.

⛔ **Ein Nenner-Tausch wäre die falsche Antwort** (Gegenprüfung 23.09.2026).
Derselbe Skalar bedient **zwei** Basen:

* den **Kanon-Fallback** (``prognose_kanon``: Rückfall für Stunden ohne
  Korrekturprofil) — der rechnet auf den **gekappten** Slots, dort lag der rohe
  Faktor **−12,4 %** zu niedrig;
* **fünf Roh-Leser** (``prognosen.py``, ``prognose_genauigkeit_service``,
  ``energie_profil/tag.py``, ``energie_profil/prognose.py``, der
  Kanon-Schätzpfad) — mit dem gekappten Nenner lägen die **+14,2 %** zu hoch.

Gebaut sind deshalb **zwei** Faktoren, jeder aus seinem eigenen reinen Pool.
Diese Datei hält beide Seiten fest: dass der gekappte Faktor aus dem gekappten
SOLL kommt, **und** dass der rohe unverändert bleibt.

⚠ **Kein Blick auf die echte Uhr** (N-167): ``_get_lernfaktor_detail`` nimmt
seit diesem Bau ein ``heute=`` entgegen — dieselbe Bauform wie
``aggregiere_korrekturprofil_anlage``.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest

import backend.api.routes.live_wetter as lw
from backend.models import Anlage, Investition
from backend.models.tages_energie_profil import TagesZusammenfassung

HEUTE = date(2026, 7, 20)
#: Zehn Tage im selben Monat: die Kaskade landet auf der Stufe „gesamt"
#: (≥ 7 Tage in den letzten 30), saisonal und Quartal verlangen 15.
TAGE = [date(2026, 7, 5) + timedelta(days=i) for i in range(10)]


@pytest.fixture(autouse=True)
def _cache_leeren():
    lw._lernfaktor_cache.clear()
    yield
    lw._lernfaktor_cache.clear()


async def _anlage(db) -> int:
    anlage = Anlage(anlagenname="N-551", leistung_kwp=10.0)
    db.add(anlage)
    await db.flush()
    return anlage.id


async def _tage(db, anlage_id: int, *, roh: float, gekappt, ist: float, anzahl: int = 10):
    """`anzahl` Tage mit Roh-SOLL, gekapptem SOLL und gemessener PV.

    `gekappt=None` heißt: die Zeile trägt kein `lern_soll_kwh` — der Zustand
    jeder Anlage vor N-547 und jeder Anlage ohne Kappung, die noch nie
    aggregiert wurde.
    """
    for tag in TAGE[:anzahl]:
        db.add(TagesZusammenfassung(
            anlage_id=anlage_id, datum=tag,
            pv_prognose_kwh=roh,
            lern_soll_kwh=gekappt,
            komponenten_kwh={"pv_1": ist},
        ))
    await db.flush()


@pytest.mark.asyncio
async def test_der_gekappte_faktor_teilt_durch_das_gekappte_soll(db):
    """⭐ Der Kern: zwei Faktoren, zwei Nenner, ein Lernstoff."""
    anlage_id = await _anlage(db)
    await _tage(db, anlage_id, roh=20.0, gekappt=17.0, ist=16.0)

    erg = await lw._get_lernfaktor_detail(anlage_id, db, heute=HEUTE)

    assert erg.faktor == pytest.approx(0.8), "16 / 20 — die rohe Basis, unverändert"
    assert erg.faktor_gekappt == pytest.approx(round(16 / 17, 3)), "16 / 17"
    assert erg.tage_count_gekappt == 10
    assert erg.faktor_gekappt > erg.faktor, (
        "auf der gekappten Basis ist die Anlage besser, als die Rohprognose glauben macht"
    )


@pytest.mark.asyncio
async def test_der_rohe_faktor_bleibt_bitgleich(db):
    """Die fünf Roh-Leser dürfen sich **nicht** bewegen — sie fragen `_get_lernfaktor`."""
    anlage_id = await _anlage(db)
    await _tage(db, anlage_id, roh=20.0, gekappt=17.0, ist=16.0)

    assert await lw._get_lernfaktor(anlage_id, db, heute=HEUTE) == pytest.approx(0.8)
    assert await lw._get_lernfaktor_gekappt(anlage_id, db, heute=HEUTE) == pytest.approx(
        round(16 / 17, 3)
    )


@pytest.mark.asyncio
async def test_ohne_kappung_sind_beide_faktoren_gleich(db):
    """Die Regression: an einer Anlage ohne AC-Grenze bewegt N-551 keine Zahl.

    `lern_soll_kwh` ist dort dasselbe wie die Rohsumme (`prognose_kanon`:
    ohne Kappung ist `om_kwh` bereits die Rohsumme).
    """
    anlage_id = await _anlage(db)
    await _tage(db, anlage_id, roh=20.0, gekappt=20.0, ist=16.0)

    erg = await lw._get_lernfaktor_detail(anlage_id, db, heute=HEUTE)

    assert erg.faktor == pytest.approx(0.8)
    assert erg.faktor_gekappt == pytest.approx(0.8)


@pytest.mark.asyncio
async def test_ohne_lern_feld_gibt_es_keinen_zweiten_faktor(db):
    """Bestand ohne `lern_soll_kwh`: `None` statt einer erfundenen Zahl —
    der Kanon-Fallback bleibt dann beim Roh-Faktor (bisheriges Verhalten)."""
    anlage_id = await _anlage(db)
    await _tage(db, anlage_id, roh=20.0, gekappt=None, ist=16.0)

    erg = await lw._get_lernfaktor_detail(anlage_id, db, heute=HEUTE)

    assert erg.faktor == pytest.approx(0.8)
    assert erg.faktor_gekappt is None
    assert erg.tage_count_gekappt == 0


@pytest.mark.asyncio
async def test_unter_dem_gate_bleibt_der_zweite_faktor_leer(db):
    """Sechs Tage mit Lern-SOLL reichen nicht — dieselbe Schwelle wie der Skalar.

    Der rohe Faktor steht auf zehn Tagen und bleibt; der gekappte entstünde aus
    sechs und entsteht deshalb gar nicht.
    """
    anlage_id = await _anlage(db)
    await _tage(db, anlage_id, roh=20.0, gekappt=None, ist=16.0)
    # Sechs der zehn Tage bekommen nachträglich ein Lern-SOLL.
    from sqlalchemy import select
    zeilen = (await db.execute(
        select(TagesZusammenfassung).where(TagesZusammenfassung.anlage_id == anlage_id)
    )).scalars().all()
    for zeile in sorted(zeilen, key=lambda z: z.datum)[:6]:
        zeile.lern_soll_kwh = 17.0
    await db.flush()

    erg = await lw._get_lernfaktor_detail(anlage_id, db, heute=HEUTE)

    assert erg.faktor == pytest.approx(0.8)
    assert erg.tage_count_gekappt == 6
    assert erg.faktor_gekappt is None, f"Gate ist {lw._MIN_TAGE_GEKAPPT} Tage"


@pytest.mark.asyncio
async def test_der_kanon_fallback_nimmt_den_gekappten_faktor(db, monkeypatch):
    """Dort, wo der Faktor auf **gekappte** Slots trifft, gilt der gekappte.

    Die beiden Zugriffe liefern hier absichtlich verschiedene Zahlen; die
    Tagesprognose muss der gekappten folgen. Der Schätzpfad daneben
    (Tagesertrag ohne Stundenprofil) bleibt beim rohen — er rechnet auf der
    rohen Basis.
    """
    from types import SimpleNamespace

    import backend.services.solar_forecast_service as sfs
    from backend.services.prognose_kanon import kanon_tagesprognose

    slots = [0.0] * 24
    for h in range(9, 16):
        slots[h] = 2.0

    async def _fake_prognose(**kwargs):
        return SimpleNamespace(
            tageswerte=[SimpleNamespace(
                datum=HEUTE.isoformat(), pv_ertrag_kwh=sum(slots), stunden_kw=list(slots),
                stunden_bewoelkung=[0.0] * 24, stunden_niederschlag=[0.0] * 24,
                stunden_wetter_code=[0] * 24,
            )],
            kwp_gesamt=kwargs.get("kwp", 10.0),
        )

    async def _roh(anlage_id, db_, quelle="openmeteo", heute=None):
        return 0.5

    async def _gekappt(anlage_id, db_, quelle="openmeteo", heute=None):
        return 1.0

    monkeypatch.setattr(sfs, "get_solar_prognose", _fake_prognose)
    monkeypatch.setattr(lw, "_get_lernfaktor", _roh)
    monkeypatch.setattr(lw, "_get_lernfaktor_gekappt", _gekappt)

    anlage = Anlage(anlagenname="Kanon N-551", leistung_kwp=10.0,
                    latitude=48.8, longitude=9.2, standort_land="DE",
                    prognose_quelle="eedc")
    db.add(anlage)
    await db.flush()
    db.add(Investition(
        anlage_id=anlage.id, typ="pv-module", bezeichnung="Süd",
        leistung_kwp=10.0, neigung_grad=35, anschaffungsdatum=date(2024, 1, 1),
        parameter={"ausrichtung_grad": 0},
    ))
    await db.flush()

    kanon = await kanon_tagesprognose(db, anlage, days=1, skip_jitter=True, heute=HEUTE)

    assert kanon is not None and kanon.tage[0].eedc_kwh is not None
    assert kanon.tage[0].eedc_kwh == pytest.approx(sum(slots), abs=0.15), (
        "mit dem gekappten Faktor 1,0 — mit dem rohen 0,5 wäre es die Hälfte"
    )
