"""Sonstiges als wählbare Spalte in Tages- und Monatstabelle (Melder rapahl, 14.08.2026).

Rainers Satz war: *„In den Tages- u. Monatstabellen fehlt die
Spaltenauswahlmöglichkeit für ‚Sonstiges'. Ich kann also nicht überprüfen, ob die
täglichen Werte erfasst wurden."* Die Größen lagen längst in der P10-Schicht
(``SonstigesFakten``) bzw. im Komponenten-JSON des Tages — es fehlte die
Durchreichung.

Der Kern dieser Datei ist **nicht**, dass zwei Zahlen ankommen, sondern dass die
Richtung aus der **gepflegten Kategorie** kommt und nicht aus dem Vorzeichen:
die beiden Tages-Schreibpfade sind sich beim Vorzeichen uneinig
(Leistungspfad signiert, Boundary-Pfad immer positiv), und eine Vorzeichen-Regel
hätte für denselben Tag je nach Betriebsart ein anderes Ergebnis geliefert.
"""

from __future__ import annotations

from datetime import date

import pytest

from backend.api.routes.monatsdaten import list_monatsdaten_aggregiert
from backend.core.berechnungen import sonstiges_kwh_je_richtung
from backend.models import Anlage, Investition, InvestitionMonatsdaten, Monatsdaten
from backend.models.tages_energie_profil import TagesEnergieProfil, TagesZusammenfassung
from backend.services.energie_profil.tage_werte import baue_tage_werte


# ── Layer-Helper: die Richtung kommt aus der Kategorie ──────────────────────


def test_beide_schreibpfade_liefern_dasselbe():
    """Leistungspfad (signiert) und Boundary-Pfad (immer positiv), ein Ergebnis.

    Die Zahlen stammen aus der Dev-Datenbank (14.08.): ``sonstige_10`` ist das
    Mini-BHKW (Kategorie *erzeuger*, dort **+0,97**), ``sonstige_12`` der
    Heizstab (Kategorie *verbraucher*, dort **−0,6**).
    """
    kategorien = {"10": "erzeuger", "12": "verbraucher"}
    leistungspfad = sonstiges_kwh_je_richtung(
        {"sonstige_10": 0.97, "sonstige_12": -0.6, "pv_6": 3.0}, kategorien
    )
    boundary = sonstiges_kwh_je_richtung(
        {"sonstige_10": 0.97, "sonstige_12": 0.6, "pv_6": 3.0}, kategorien
    )
    assert leistungspfad == boundary
    assert leistungspfad.erzeugung_kwh == 0.97
    assert leistungspfad.verbrauch_kwh == 0.6


def test_leere_kategorie_zaehlt_als_verbraucher():
    """Dieselbe Vorgabe, mit der beide Tages-Schreibpfade den Wert erzeugen."""
    s = sonstiges_kwh_je_richtung({"sonstige_12": -0.6}, {"12": ""})
    assert s.verbrauch_kwh == 0.6
    assert s.erzeugung_kwh is None


def test_bidirektionales_geraet_bleibt_draussen():
    """Ein Netto-Wert lässt sich keiner Richtung zuschlagen — bewusste Lücke."""
    s = sonstiges_kwh_je_richtung({"sonstige_9": 5.0}, {"9": "speicher"})
    assert s == (None, None)


def test_unbekanntes_geraet_zaehlt_nicht():
    """Wer nicht in der Kategorie-Map steht, war am Tag nicht aktiv."""
    assert sonstiges_kwh_je_richtung({"sonstige_9": 5.0}, {}) == (None, None)
    # Kein Schlüssel der Gruppe ⇒ keine Aussage, keine 0.
    assert sonstiges_kwh_je_richtung({"pv_6": 3.0}, {"9": "erzeuger"}) == (None, None)


# ── Tagesebene ──────────────────────────────────────────────────────────────


async def _anlage_mit_sonstiges(db) -> tuple[int, int, int]:
    anlage = Anlage(anlagenname="SonstigesSpalten", leistung_kwp=10.0)
    db.add(anlage)
    await db.flush()
    aid = anlage.id

    bhkw = Investition(
        anlage_id=aid, typ="sonstiges", bezeichnung="Mini-BHKW",
        anschaffungsdatum=date(2024, 1, 1), parameter={"kategorie": "erzeuger"},
    )
    heizstab = Investition(
        anlage_id=aid, typ="sonstiges", bezeichnung="Heizstab",
        anschaffungsdatum=date(2024, 1, 1), parameter={"kategorie": "verbraucher"},
    )
    db.add_all([bhkw, heizstab])
    await db.flush()

    tag = date(2026, 5, 10)
    db.add_all([
        TagesEnergieProfil(
            anlage_id=aid, datum=tag, stunde=h,
            pv_kw=2.0, verbrauch_kw=3.0, einspeisung_kw=0.0, netzbezug_kw=1.0,
            komponenten={
                f"sonstige_{bhkw.id}": 0.97,
                f"sonstige_{heizstab.id}": -0.6,
            },
        )
        for h in (10, 11)
    ])
    await db.flush()
    return aid, bhkw.id, heizstab.id


@pytest.mark.asyncio
async def test_tageszeile_traegt_beide_richtungen(db):
    aid, _, _ = await _anlage_mit_sonstiges(db)
    anlage = await db.get(Anlage, aid)

    tage = await baue_tage_werte(db, anlage, date(2026, 5, 1), date(2026, 5, 31))

    assert len(tage) == 1
    # 2 Stunden × 0,97 bzw. 0,6
    assert tage[0].sonstiges_erzeugung == 1.94
    assert tage[0].sonstiges_verbrauch == 1.2


@pytest.mark.asyncio
async def test_tageszeile_nimmt_den_boundary_rollup_zuerst(db):
    """Wie bei den Erzeuger-Spalten: der Rollup schlägt die Σ der Stunden."""
    aid, bhkw_id, heizstab_id = await _anlage_mit_sonstiges(db)
    db.add(TagesZusammenfassung(
        anlage_id=aid, datum=date(2026, 5, 10), stunden_verfuegbar=2,
        komponenten_kwh={
            f"sonstige_{bhkw_id}": 4.0,      # Boundary-Pfad: immer positiv
            f"sonstige_{heizstab_id}": 2.5,
        },
    ))
    await db.flush()
    anlage = await db.get(Anlage, aid)

    tage = await baue_tage_werte(db, anlage, date(2026, 5, 1), date(2026, 5, 31))

    assert tage[0].sonstiges_erzeugung == 4.0
    assert tage[0].sonstiges_verbrauch == 2.5


@pytest.mark.asyncio
async def test_stillgelegtes_geraet_faellt_aus_der_tageszeile(db):
    """Die Laufzeitgrenze gilt je Tag, nicht je Zeitraum."""
    aid, _, heizstab_id = await _anlage_mit_sonstiges(db)
    heizstab = await db.get(Investition, heizstab_id)
    heizstab.stilllegungsdatum = date(2025, 12, 31)
    await db.flush()
    anlage = await db.get(Anlage, aid)

    tage = await baue_tage_werte(db, anlage, date(2026, 5, 1), date(2026, 5, 31))

    assert tage[0].sonstiges_erzeugung == 1.94
    assert tage[0].sonstiges_verbrauch is None


# ── Monatsebene ─────────────────────────────────────────────────────────────


async def _monat_mit_sonstiges(db, *, mit_heizstab: bool) -> int:
    anlage = Anlage(anlagenname="SonstigesMonat", leistung_kwp=10.0)
    db.add(anlage)
    await db.flush()
    aid = anlage.id
    db.add(Monatsdaten(
        anlage_id=aid, jahr=2026, monat=5,
        einspeisung_kwh=100.0, netzbezug_kwh=200.0,
    ))
    bhkw = Investition(
        anlage_id=aid, typ="sonstiges", bezeichnung="Mini-BHKW",
        anschaffungsdatum=date(2024, 1, 1), parameter={"kategorie": "erzeuger"},
    )
    db.add(bhkw)
    invs = [bhkw]
    if mit_heizstab:
        heizstab = Investition(
            anlage_id=aid, typ="sonstiges", bezeichnung="Heizstab",
            anschaffungsdatum=date(2024, 1, 1),
            parameter={"kategorie": "verbraucher"},
        )
        db.add(heizstab)
        invs.append(heizstab)
    await db.flush()

    db.add(InvestitionMonatsdaten(
        investition_id=bhkw.id, jahr=2026, monat=5,
        verbrauch_daten={"erzeugung_kwh": 300.0},
    ))
    if mit_heizstab:
        db.add(InvestitionMonatsdaten(
            investition_id=invs[1].id, jahr=2026, monat=5,
            verbrauch_daten={"verbrauch_kwh": 45.0},
        ))
    await db.flush()
    return aid


@pytest.mark.asyncio
async def test_monatszeile_traegt_den_sonstigen_verbrauch(db):
    aid = await _monat_mit_sonstiges(db, mit_heizstab=True)

    zeilen = await list_monatsdaten_aggregiert(anlage_id=aid, jahr=2026, db=db)

    assert len(zeilen) == 1
    assert zeilen[0].sonstige_erzeugung_kwh == 300.0
    assert zeilen[0].sonstige_verbrauch_kwh == 45.0


@pytest.mark.asyncio
async def test_ohne_verbraucher_schweigt_die_spalte(db):
    """P4: ohne solches Gerät bleibt das Feld leer statt 0 zu behaupten."""
    aid = await _monat_mit_sonstiges(db, mit_heizstab=False)

    zeilen = await list_monatsdaten_aggregiert(anlage_id=aid, jahr=2026, db=db)

    assert zeilen[0].sonstige_erzeugung_kwh == 300.0
    assert zeilen[0].sonstige_verbrauch_kwh is None
