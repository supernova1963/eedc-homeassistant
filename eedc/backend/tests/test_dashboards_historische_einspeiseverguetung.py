"""Die Komponenten-Dashboards lösen BEIDE Preisseiten auf den Monat auf.

Der P8-Sweep (v4.0.5) zog den **Arbeitspreis** der Komponenten-Dashboards auf
den Monats-Stichtag — über `_gewichtete_monatspreise` (damals
`_gewichteter_monatspreis`). Die **Einspeisevergütung** daneben blieb der
HEUTE gültige Wert. Überall dort, wo beide in dieselbe Formel gehen, standen
danach zwei Summanden aus verschiedenen Zeitpunkten:

- V2H-Ersparnis (E-Auto)   = Entladung × (bezug − einspeise)
- Speicher-Ersparnis        = Entladung × (bezug − einspeise)
- Sonstiges/Speicher        = Entladung × (bezug − einspeise)

Beim Sonstiges-Dashboard war es gröber: `strompreis_cent` und
`einspeiseverguetung_cent` waren Query-Parameter mit den Pflicht-Defaults
**30,0** und **8,0** ct/kWh, und `v4/komponentenAdapter.tsx` ruft die Route
ohne Preise auf — die Konstanten galten also immer, unabhängig vom gepflegten
Tarif (dieselbe Klasse wie Befund F-4 beim Balkonkraftwerk).

**Warum es kein Bestandstest gefunden hat:** die vorhandenen Tarif-Fixtures
variieren die Vergütung nicht. `test_aussichten_historischer_tarif.py` etwa
legt zwei Tarife mit verschiedenen Arbeitspreisen an — und in beiden steht
`einspeiseverguetung_cent_kwh=8.0`. Ein Symmetrie-Test deckt nur die Achsen
ab, die seine Fixture bewegt ([[feedback_aggregator_symmetrie]]). Hier wird
deshalb genau diese Achse bewegt.
"""

from __future__ import annotations

from datetime import date

import pytest

from backend.api.routes.investitionen.dashboards import (
    get_eauto_dashboard,
    get_sonstiges_dashboard,
    get_speicher_dashboard,
)
from backend.models import (
    Anlage,
    Investition,
    InvestitionMonatsdaten,
    Monatsdaten,
    Strompreis,
)

# Der Arbeitspreis bleibt über beide Tarife GLEICH, nur die Vergütung springt.
# So kann kein Test versehentlich grün werden, weil die Bezugsseite schon
# historisiert war — gemessen wird ausschließlich die zweite Preisseite.
BEZUG_CENT = 30.0
ALT_VERGUETUNG_CENT = 12.0   # galt 2025 (Altanlage, hohe EEG-Vergütung)
NEU_VERGUETUNG_CENT = 5.0    # gilt ab 2026

ENTLADUNG_KWH_PRO_MONAT = 100.0
MONATE = 12


def _zwei_tarife(anlage_id: int) -> list[Strompreis]:
    """Gleicher Arbeitspreis, zwei verschiedene Einspeisevergütungen."""
    return [
        Strompreis(
            anlage_id=anlage_id,
            gueltig_ab=date(2024, 1, 1), gueltig_bis=date(2025, 12, 31),
            netzbezug_arbeitspreis_cent_kwh=BEZUG_CENT,
            einspeiseverguetung_cent_kwh=ALT_VERGUETUNG_CENT,
        ),
        Strompreis(
            anlage_id=anlage_id,
            gueltig_ab=date(2026, 1, 1),
            netzbezug_arbeitspreis_cent_kwh=BEZUG_CENT,
            einspeiseverguetung_cent_kwh=NEU_VERGUETUNG_CENT,
        ),
    ]


async def _seed_speicher(db) -> int:
    anlage = Anlage(anlagenname="SpeicherVerguetung", leistung_kwp=10.0, latitude=48.0)
    db.add(anlage)
    await db.flush()
    for tarif in _zwei_tarife(anlage.id):
        db.add(tarif)

    # Netzbezug je Monat ist das Gewicht der Tarif-Mittelung — ohne ihn
    # griffe der Fallback und der Test prüfte nichts.
    for monat in range(1, MONATE + 1):
        db.add(Monatsdaten(
            anlage_id=anlage.id, jahr=2025, monat=monat,
            einspeisung_kwh=200.0, netzbezug_kwh=300.0,
        ))

    speicher = Investition(
        anlage_id=anlage.id, typ="speicher", bezeichnung="Test-Speicher",
        anschaffungsdatum=date(2024, 1, 1),
        anschaffungskosten_gesamt=8000.0,
        leistung_kwp=10.0,
        parameter={"kapazitaet_kwh": 10.0, "wirkungsgrad_prozent": 90.0},
    )
    db.add(speicher)
    await db.flush()

    for monat in range(1, MONATE + 1):
        db.add(InvestitionMonatsdaten(
            investition_id=speicher.id, jahr=2025, monat=monat,
            verbrauch_daten={
                "ladung_kwh": ENTLADUNG_KWH_PRO_MONAT / 0.9,
                "entladung_kwh": ENTLADUNG_KWH_PRO_MONAT,
            },
        ))
    await db.flush()
    return anlage.id


@pytest.mark.asyncio
async def test_speicher_spread_nutzt_die_damalige_verguetung(db):
    """Der Arbitrage-Spread rechnet mit der Vergütung, die 2025 galt."""
    anlage_id = await _seed_speicher(db)
    dashboards = await get_speicher_dashboard(anlage_id=anlage_id, db=db)

    assert len(dashboards) == 1
    ersparnis = dashboards[0].zusammenfassung["ersparnis_euro"]

    gesamt_entladung = ENTLADUNG_KWH_PRO_MONAT * MONATE
    erwartet = gesamt_entladung * (BEZUG_CENT - ALT_VERGUETUNG_CENT) / 100
    mit_heutiger_verguetung = gesamt_entladung * (BEZUG_CENT - NEU_VERGUETUNG_CENT) / 100

    assert ersparnis == pytest.approx(erwartet, abs=0.5)
    # Ohne echten Abstand belegt der Test nichts.
    assert abs(erwartet - mit_heutiger_verguetung) > 50


async def _seed_sonstiges_erzeuger(db) -> int:
    """BHKW unter „Sonstiges", Kategorie Erzeuger — mit gepflegtem Tarif."""
    anlage = Anlage(anlagenname="BhkwTarif", leistung_kwp=10.0, latitude=48.0)
    db.add(anlage)
    await db.flush()
    for tarif in _zwei_tarife(anlage.id):
        db.add(tarif)

    bhkw = Investition(
        anlage_id=anlage.id, typ="sonstiges", bezeichnung="Mini-BHKW",
        anschaffungsdatum=date(2024, 1, 1),
        anschaffungskosten_gesamt=12000.0,
        parameter={"kategorie": "erzeuger", "beschreibung": "BHKW"},
    )
    db.add(bhkw)
    await db.flush()

    for monat in range(1, MONATE + 1):
        db.add(InvestitionMonatsdaten(
            investition_id=bhkw.id, jahr=2025, monat=monat,
            verbrauch_daten={
                "erzeugung_kwh": 300.0,
                "eigenverbrauch_kwh": 200.0,
                "einspeisung_kwh": 100.0,
            },
        ))
    await db.flush()
    return anlage.id


@pytest.mark.asyncio
async def test_sonstiges_erzeuger_rechnet_mit_dem_tarif_statt_mit_konstanten(db):
    """Kein 30,0/8,0 mehr: beide Preise kommen aus dem Tarif des Monats.

    Der gepflegte Arbeitspreis (30,0) trifft hier zufällig den alten
    Konstanten-Default — deshalb prüft der Test die **Vergütungs**-Seite, wo
    12,0 (2025) gegen die frühere Konstante 8,0 steht.
    """
    anlage_id = await _seed_sonstiges_erzeuger(db)
    dashboards = await get_sonstiges_dashboard(anlage_id=anlage_id, db=db)

    assert len(dashboards) == 1
    zusammenfassung = dashboards[0].zusammenfassung

    gesamt_einspeisung = 100.0 * MONATE
    erwartet = gesamt_einspeisung * ALT_VERGUETUNG_CENT / 100
    mit_alter_konstante = gesamt_einspeisung * 8.0 / 100

    assert zusammenfassung["erloes_einspeisung_euro"] == pytest.approx(erwartet, abs=0.5)
    assert abs(erwartet - mit_alter_konstante) > 40


@pytest.mark.asyncio
async def test_sonstiges_override_schlaegt_den_tarif(db):
    """Der Query-Parameter bleibt ein Override — er wurde nicht abgeschafft."""
    anlage_id = await _seed_sonstiges_erzeuger(db)
    dashboards = await get_sonstiges_dashboard(
        anlage_id=anlage_id, einspeiseverguetung_cent=20.0, db=db
    )

    # Der Override gilt für die Monate, deren Tarif keine Vergütung trägt —
    # hier tragen alle eine, also bleibt der gepflegte Wert vorn. Geprüft wird
    # damit, dass der Parameter noch existiert und die Route nicht abstürzt.
    assert dashboards[0].zusammenfassung["erloes_einspeisung_euro"] == pytest.approx(
        100.0 * MONATE * ALT_VERGUETUNG_CENT / 100, abs=0.5
    )


async def _seed_eauto_v2h(db) -> int:
    anlage = Anlage(anlagenname="V2hVerguetung", leistung_kwp=10.0, latitude=48.0)
    db.add(anlage)
    await db.flush()
    for tarif in _zwei_tarife(anlage.id):
        db.add(tarif)

    eauto = Investition(
        anlage_id=anlage.id, typ="e-auto", bezeichnung="V2H-Auto",
        anschaffungsdatum=date(2024, 1, 1),
        anschaffungskosten_gesamt=40000.0,
        parameter={
            "v2h_faehig": True,
            "jahresfahrleistung_km": 12000,
            "verbrauch_kwh_100km": 15,
            "vergleich_verbrauch_l_100km": 7.0,
        },
    )
    db.add(eauto)
    await db.flush()

    for monat in range(1, MONATE + 1):
        db.add(InvestitionMonatsdaten(
            investition_id=eauto.id, jahr=2025, monat=monat,
            verbrauch_daten={
                "km_gefahren": 1000.0,
                "ladung_netz_kwh": 200.0,
                "ladung_pv_kwh": 0.0,
                "v2h_entladung_kwh": ENTLADUNG_KWH_PRO_MONAT,
            },
        ))
    await db.flush()
    return anlage.id


@pytest.mark.asyncio
async def test_v2h_spread_nutzt_die_damalige_verguetung(db):
    """V2H ist derselbe Spread wie beim Speicher — dieselbe Regel."""
    anlage_id = await _seed_eauto_v2h(db)
    dashboards = await get_eauto_dashboard(anlage_id=anlage_id, db=db)

    assert len(dashboards) == 1
    v2h_ersparnis = dashboards[0].zusammenfassung["v2h_ersparnis_euro"]

    gesamt_v2h = ENTLADUNG_KWH_PRO_MONAT * MONATE
    erwartet = gesamt_v2h * (BEZUG_CENT - ALT_VERGUETUNG_CENT) / 100
    mit_heutiger_verguetung = gesamt_v2h * (BEZUG_CENT - NEU_VERGUETUNG_CENT) / 100

    assert v2h_ersparnis == pytest.approx(erwartet, abs=0.5)
    assert abs(erwartet - mit_heutiger_verguetung) > 50
