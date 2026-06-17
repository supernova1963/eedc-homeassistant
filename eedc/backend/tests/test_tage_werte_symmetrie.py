"""Σ Tageswerte == Monatswert — Symmetrie der Tages-Werte-Embed-Sicht (IA v4 E3).

Die Tages-Werte-Zeilen (`baue_tage_werte`) und der bestehende Monats-Endpoint
(`get_monatsauswertung`) summieren dieselben stündlichen `TagesEnergieProfil`-
Rows. Dieser Test sichert, dass die additive Energie-Bilanz beider Pfade
deckungsgleich bleibt — ein paralleler Aggregator-Pfad ohne Pflicht-Test ist
die Drift-Quelle Nr. 1 ([[feedback_aggregations_drift]],
[[feedback_aggregator_symmetrie]]).

Zusätzlich: Finanz-Additivität (Σ Tages-Einspeise-Erlös == Einspeisung_Monat ×
Vergütung) und korrekte Quoten pro Tag.
"""

from __future__ import annotations

from datetime import date

import pytest

from backend.api.routes.energie_profil.views import get_monatsauswertung
from backend.models import Anlage, Strompreis
from backend.models.tages_energie_profil import TagesEnergieProfil, TagesZusammenfassung
from backend.services.energie_profil.tage_werte import baue_tage_werte


def _stunde(anlage_id: int, tag: date, h: int, pv, vb, ei, nz, batt=None, wp=None):
    return TagesEnergieProfil(
        anlage_id=anlage_id, datum=tag, stunde=h,
        pv_kw=pv, verbrauch_kw=vb, einspeisung_kw=ei, netzbezug_kw=nz,
        batterie_kw=batt, waermepumpe_kw=wp,
    )


async def _anlage_mit_tagesprofil(db) -> int:
    """3 Maitage, je 4 belegte Stunden, gemischte Bilanz inkl. NULL-Stunde,
    Batterie-Lade/Entlade und WP-Last."""
    anlage = Anlage(anlagenname="TageWerteSym", leistung_kwp=10.0)
    db.add(anlage)
    await db.flush()
    db.add(Strompreis(
        anlage_id=anlage.id, gueltig_ab=date(2024, 1, 1),
        netzbezug_arbeitspreis_cent_kwh=30.0, einspeiseverguetung_cent_kwh=8.0,
    ))

    aid = anlage.id
    rows: list[TagesEnergieProfil] = []
    # Tag 1: PV-Überschuss-Tag
    t1 = date(2026, 5, 10)
    rows += [
        _stunde(aid, t1, 10, 5.0, 1.0, 3.0, 0.0, batt=-1.0, wp=0.5),
        _stunde(aid, t1, 11, 6.0, 2.0, 3.5, 0.0, batt=-0.5, wp=0.0),
        _stunde(aid, t1, 18, 0.5, 2.0, 0.0, 1.5, batt=1.0, wp=1.0),
        _stunde(aid, t1, 20, None, None, None, None, batt=None, wp=None),  # NULL-Stunde
    ]
    # Tag 2: Defizit-Tag (Bezug)
    t2 = date(2026, 5, 11)
    rows += [
        _stunde(aid, t2, 8, 1.0, 3.0, 0.0, 2.0, batt=0.5, wp=1.5),
        _stunde(aid, t2, 19, 0.0, 4.0, 0.0, 4.0, batt=0.0, wp=2.0),
    ]
    # Tag 3: gemischt
    t3 = date(2026, 5, 12)
    rows += [
        _stunde(aid, t3, 12, 8.0, 2.0, 5.0, 0.0, batt=-1.0, wp=0.0),
        _stunde(aid, t3, 21, 0.0, 1.5, 0.0, 1.5, batt=0.0, wp=0.5),
    ]
    db.add_all(rows)

    # Eine Tageszusammenfassung mit tag-nativen Feldern (Tag 1)
    db.add(TagesZusammenfassung(
        anlage_id=aid, datum=t1, stunden_verfuegbar=4, datenquelle="ha_sensor",
        peak_pv_kw=6.0, performance_ratio=0.85, batterie_vollzyklen=0.4,
        temperatur_max_c=22.0, boersenpreis_avg_cent=9.5,
    ))
    await db.flush()
    return aid


@pytest.mark.asyncio
async def test_tage_werte_summe_gleich_monat(db):
    aid = await _anlage_mit_tagesprofil(db)
    anlage = await db.get(Anlage, aid)

    tage = await baue_tage_werte(db, anlage, date(2026, 5, 1), date(2026, 5, 31))
    monat = await get_monatsauswertung(aid, jahr=2026, monat=5, top_n=10, db=db)

    assert len(tage) == 3
    summe = lambda f: round(sum(getattr(t, f) for t in tage), 2)

    assert summe("erzeugung") == monat.pv_kwh
    assert summe("gesamtverbrauch") == monat.verbrauch_kwh
    assert summe("einspeisung") == monat.einspeisung_kwh
    assert summe("netzbezug") == monat.netzbezug_kwh
    assert summe("ueberschuss_kwh") == monat.ueberschuss_kwh
    assert summe("defizit_kwh") == monat.defizit_kwh
    # Eigenverbrauch additiv (= Σ pv − Σ einspeisung)
    assert summe("eigenverbrauch") == round(monat.pv_kwh - monat.einspeisung_kwh, 2)


@pytest.mark.asyncio
async def test_tage_werte_finanz_additiv_und_quoten(db):
    aid = await _anlage_mit_tagesprofil(db)
    anlage = await db.get(Anlage, aid)
    tage = await baue_tage_werte(db, anlage, date(2026, 5, 1), date(2026, 5, 31))

    einspeisung_summe = sum(t.einspeisung for t in tage)
    erloes_summe = round(sum(t.einspeise_erloes for t in tage), 2)
    # 8 ct/kWh Vergütung, keine §51-Negativpreis-Daten → linear
    assert erloes_summe == round(einspeisung_summe * 8.0 / 100, 2)

    # ev_ersparnis = Eigenverbrauch × 30 ct/kWh
    for t in tage:
        assert t.ev_ersparnis == round(t.eigenverbrauch * 30.0 / 100, 2)
        # netto_bilanz = einspeise_erloes + ev_ersparnis − netzbezug_kosten
        assert t.netto_bilanz == round(
            t.einspeise_erloes + t.ev_ersparnis - t.netzbezug_kosten, 2
        )

    # Tag-native Felder aus Tageszusammenfassung durchgereicht (Tag 1)
    t1 = next(t for t in tage if t.datum == date(2026, 5, 10))
    assert t1.peak_pv_kw == 6.0
    assert t1.performance_ratio == 0.85
    assert t1.spezErtrag is not None  # PV vorhanden, kWp=10
