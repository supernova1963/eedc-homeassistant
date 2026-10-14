"""RF-25 Fall-Probe — Energieprofil → Monat: Schlüssel ohne Serie fallen aus Komponenten und Kategorien.

Kein bestehender Test und keine der drei DB-Kopien erreicht den Zweig `if not info: continue` der Komponenten-Phase
(gemessen: Spur über 46 Dateien und DB-Probe, `monat.py:349` am HEAD `766f4ab8`). Durch ihn laufen drei Fälle:
der V2H-Tagesschlüssel ``v2h_<id>`` (Konzept #110 §2.6, `_key_to_serie_info` gibt `None`), ein Schlüssel auf eine
fremde Investition und ein Schlüssel ohne Muster. Dazu eine Stunde ohne PV-Wert (Datenqualität #135).
"""
from __future__ import annotations

from datetime import date

from backend.api.routes.energie_profil.views import get_monatsauswertung
from backend.models.tages_energie_profil import TagesEnergieProfil, TagesZusammenfassung
from backend.tests.factories import anlage, investition

JAHR, MONAT = 2026, 6


async def test_v2h_fremder_und_kaputter_schluessel_fallen_heraus(db):
    a = await anlage(db)
    pv = await investition(db, a.id, "pv-module", leistung_kwp=5.0)
    ea = await investition(db, a.id, "e-auto", parameter={"v2h_faehig": True})
    d = date(JAHR, MONAT, 3)
    db.add(TagesEnergieProfil(anlage_id=a.id, datum=d, stunde=12, pv_kw=3.0, verbrauch_kw=1.0))
    db.add(TagesEnergieProfil(anlage_id=a.id, datum=d, stunde=13, pv_kw=None, verbrauch_kw=2.0))
    db.add(TagesZusammenfassung(anlage_id=a.id, datum=d, komponenten_kwh={
        f"pv_{pv.id}": 10.0, f"eauto_{ea.id}": 4.0, f"v2h_{ea.id}": 2.0,
        "pv_999999": 5.0, "kaputt": 1.0, "haushalt": 3.0,
    }))
    await db.commit()

    res = await get_monatsauswertung(anlage_id=a.id, jahr=JAHR, monat=MONAT, top_n=10, db=db)

    # Reihenfolge: Quelle zuerst, dann Senke, dann übrige Seiten (das E-Auto ist bidirektional)
    assert [k.key for k in res.komponenten] == [f"pv_{pv.id}", "haushalt", f"eauto_{ea.id}"]
    kat = {k.kategorie: k.kwh for k in res.kategorien}
    assert kat == {"pv_module": 10.0, "wallbox_eauto": 4.0, "haushalt": 3.0}   # V2H nicht in wallbox_eauto
    assert res.stunden_fehlend_pv == 1 and res.stunden_fehlend_verbrauch == 0


async def test_sonstiger_erzeuger_wird_ueber_sein_geraet_eingeordnet(db):
    """Die Detail-Kategorie eines Sonstiges-Geräts hängt an seinem Parameter — der Schlüssel muss aufs Gerät führen."""
    a = await anlage(db)
    so = await investition(db, a.id, "sonstiges", parameter={"kategorie": "erzeuger"})
    d = date(JAHR, MONAT, 4)
    db.add(TagesEnergieProfil(anlage_id=a.id, datum=d, stunde=12, pv_kw=3.0, verbrauch_kw=1.0))
    db.add(TagesZusammenfassung(anlage_id=a.id, datum=d, komponenten_kwh={f"sonstige_{so.id}": 2.5}))
    await db.commit()

    res = await get_monatsauswertung(anlage_id=a.id, jahr=JAHR, monat=MONAT, top_n=10, db=db)
    assert [(k.key, k.kategorie, k.seite) for k in res.komponenten] == [(f"sonstige_{so.id}", "sonstige_erzeuger", "quelle")]
    assert [k.kategorie for k in res.kategorien] == ["sonstige_erzeuger"]


async def test_wirkungsgrad_erst_ab_einer_ladung_ueber_0_1_kwh(db):
    """Unter 0,1 kWh Ladung ist der Speicher-Wirkungsgrad keine Aussage (Schwelle der Route)."""
    a = await anlage(db)
    d = date(JAHR, MONAT, 5)
    db.add(TagesEnergieProfil(anlage_id=a.id, datum=d, stunde=10, pv_kw=1.0, verbrauch_kw=0.5, batterie_kw=-0.05))
    db.add(TagesEnergieProfil(anlage_id=a.id, datum=d, stunde=20, pv_kw=0.0, verbrauch_kw=0.5, batterie_kw=0.04))
    await db.commit()

    res = await get_monatsauswertung(anlage_id=a.id, jahr=JAHR, monat=MONAT, top_n=10, db=db)
    assert res.batterie_ladung_kwh == 0.05 and res.batterie_entladung_kwh == 0.04
    assert res.batterie_wirkungsgrad is None


async def test_komponentenwert_none_ist_kein_eintrag(db):
    """`None` im Tages-Rollup heißt «nicht gemessen» — kein Schlüssel mit 0 kWh (0-Werte: `is not None`)."""
    a = await anlage(db)
    d = date(JAHR, MONAT, 6)
    db.add(TagesEnergieProfil(anlage_id=a.id, datum=d, stunde=12, pv_kw=3.0, verbrauch_kw=1.0))
    db.add(TagesZusammenfassung(anlage_id=a.id, datum=d, komponenten_kwh={"haushalt": None}))
    await db.commit()

    res = await get_monatsauswertung(anlage_id=a.id, jahr=JAHR, monat=MONAT, top_n=10, db=db)
    assert res.komponenten == [] and res.kategorien == []
