"""F-34 / #366 — das SOLL im Anschaffungsmonat gilt nur für die gelaufenen Tage.

**Der gemeldete Schaden** (azywietz-web, 2026-08-17): Seine Anlage lief ab dem
19.03.2026. Die Sicht „SOLL/IST pro PV-String" stellte dem gemessenen März
trotzdem das **volle** PVGIS-März-SOLL gegenüber — 175,1 kWh gegen 60,8
gemessene, Performance Ratio 0,347, während dieselbe Anlage in jedem vollen
Monat über 1,0 lag (April 1,039 · Mai 1,035 · Juni 1,131 · Juli 1,139). Der
Vergleich maß das Inbetriebnahme-Datum, nicht die Anlage, und zog das
Jahres-PR von ~1,08 auf 0,973.

**Der Weg** ist derselbe wie bei N-69 für das obere Monatsende (Entscheid
Gernot, 2026-08-04): den **Nenner kürzen**, nicht den Monat auslassen. Neu ist
allein, dass die Kante aus den Stammdaten kommt statt aus dem Kalender —
deshalb `monatsfenster_investition` neben `monatsfenster` und nicht als
Parameter darin (die zwei Datums-Ebenen aus `CLAUDE.md`).
"""

from __future__ import annotations

from datetime import date

from backend.core.berechnungen import (
    anteilig,
    monatsfenster,
    monatsfenster_investition,
)


# ============================================================================
# Die Formel
# ============================================================================


def test_anschaffungsmonat_zaehlt_ab_dem_tag_inklusive():
    """19.03. bei 31 Tagen → 13 Tage (19. mitgezählt), genau wie gemeldet."""
    f = monatsfenster_investition(2026, 3, ab=date(2026, 3, 19))
    assert f.tage == 13
    assert f.tage_gesamt == 31
    assert f.ist_angefangen is True


def test_gemeldete_zahl_reproduziert():
    """175,1 kWh PVGIS-März → 73,4 kWh anteilig; PR springt von 0,35 auf 0,83."""
    f = monatsfenster_investition(2026, 3, ab=date(2026, 3, 19))
    soll = anteilig(175.1, f)
    assert round(soll, 1) == 73.4
    assert round(60.8 / soll, 2) == 0.83


def test_voller_monat_nach_anschaffung_bleibt_bitgleich():
    """April ist ganz gelaufen — kein Abschlag, kein Verhaltenswechsel."""
    f = monatsfenster_investition(2026, 4, ab=date(2026, 3, 19))
    assert f.anteil == 1.0
    assert f.ist_angefangen is False
    assert anteilig(226.4, f) == 226.4


def test_monat_vor_der_anschaffung_hat_null_tage():
    f = monatsfenster_investition(2026, 2, ab=date(2026, 3, 19))
    assert f.tage == 0
    assert anteilig(120.0, f) == 0.0


def test_stilllegungsmonat_ist_die_spiegelkante():
    """Am 10.06. stillgelegt → 10 von 30 Tagen."""
    f = monatsfenster_investition(2026, 6, bis=date(2026, 6, 10))
    assert f.tage == 10
    assert f.tage_gesamt == 30


def test_monat_nach_der_stilllegung_hat_null_tage():
    f = monatsfenster_investition(2026, 7, bis=date(2026, 6, 10))
    assert f.tage == 0


def test_beide_kanten_im_selben_monat():
    """Anschaffung und Stilllegung im selben Monat — der Schnitt zählt."""
    f = monatsfenster_investition(
        2026, 5, ab=date(2026, 5, 10), bis=date(2026, 5, 20)
    )
    assert f.tage == 11  # 10. bis 20. inklusive


def test_stilllegung_vor_anschaffung_ergibt_null_statt_negativ():
    """Widersprüchliche Stammdaten dürfen kein negatives Fenster liefern."""
    f = monatsfenster_investition(
        2026, 5, ab=date(2026, 5, 20), bis=date(2026, 5, 10)
    )
    assert f.tage == 0


def test_ohne_kanten_ist_der_monat_vollstaendig():
    """Der Normalfall — keine Stammdaten, kein Abschlag."""
    f = monatsfenster_investition(2026, 5)
    assert f.tage == 31
    assert f.anteil == 1.0


# ============================================================================
# Die Abgrenzung gegen die andere Datums-Ebene
# ============================================================================


def test_investitionsfenster_liest_NICHT_die_uhr():
    """`monatsfenster_investition` kennt kein „heute".

    Die Trennung ist der Punkt: `monatsfenster` kürzt den LAUFENDEN Monat
    (N-69), `monatsfenster_investition` den ANGESCHAFFTEN. Ein Monat weit in
    der Zukunft ist für die Investitions-Frage vollständig — sie hat mit dem
    Stichtag nichts zu tun.
    """
    weit_in_der_zukunft = monatsfenster_investition(2099, 7, ab=date(2026, 3, 19))
    assert weit_in_der_zukunft.anteil == 1.0
    # Die Kalender-Frage antwortet für denselben Monat gegenteilig.
    assert monatsfenster(2099, 7, heute=date(2026, 8, 18)).tage == 0


# ============================================================================
# Die Route — ruft sie die Formel überhaupt?
# ============================================================================
#
# Die Formeltests darüber sind blind dafür, ob `pv_strings.py` sie anwendet.
# Genau diese Lücke ließ in Sitzung 60 einen von zehn Sprengsätzen stumm.

from datetime import datetime  # noqa: E402

from backend.api.routes.cockpit.pv_strings import (  # noqa: E402
    get_pv_strings,
    get_pv_strings_gesamtlaufzeit,
)
from backend.models import (  # noqa: E402
    Anlage,
    Investition,
    InvestitionMonatsdaten,
    Monatsdaten,
)
from backend.models.pvgis_prognose import PVGISPrognose  # noqa: E402


async def _anlage_ab_mitte_maerz(db, *, anschaffung: date) -> int:
    """Ein String, März + April 2026 gemessen, PVGIS 100 kWh je Monat."""
    anlage = Anlage(anlagenname="Teilmonat", leistung_kwp=2.0)
    db.add(anlage)
    await db.flush()
    for monat in (3, 4):
        db.add(Monatsdaten(anlage_id=anlage.id, jahr=2026, monat=monat,
                           einspeisung_kwh=50.0, netzbezug_kwh=100.0))
    modul = Investition(
        anlage_id=anlage.id, typ="pv-module", bezeichnung="Süd",
        anschaffungsdatum=anschaffung, leistung_kwp=2.0,
    )
    db.add(modul)
    await db.flush()
    for monat, kwh in ((3, 60.8), (4, 100.0)):
        db.add(InvestitionMonatsdaten(
            investition_id=modul.id, jahr=2026, monat=monat,
            verbrauch_daten={"pv_erzeugung_kwh": kwh},
        ))
    db.add(PVGISPrognose(
        anlage_id=anlage.id, abgerufen_am=datetime(2026, 1, 1),
        latitude=48.0, longitude=11.0, neigung_grad=30.0, ausrichtung_grad=0.0,
        jahresertrag_kwh=1200.0, spezifischer_ertrag_kwh_kwp=600.0,
        gesamt_leistung_kwp=2.0,
        monatswerte=[{"monat": m, "e_m": 100.0} for m in range(1, 13)],
    ))
    await db.commit()
    return anlage.id


async def test_route_kuerzt_das_soll_im_anschaffungsmonat(db):
    """März ab dem 19. → SOLL 100 × 13/31 = 41,9 statt 100 kWh."""
    anlage_id = await _anlage_ab_mitte_maerz(db, anschaffung=date(2026, 3, 19))

    resp = await get_pv_strings(anlage_id=anlage_id, jahr=2026, db=db)
    monate = {m.monat: m for m in resp.strings[0].monatswerte}

    assert round(monate[3].prognose_kwh, 1) == 41.9
    # Der April ist voll gelaufen und bleibt unangetastet.
    assert monate[4].prognose_kwh == 100.0
    # Und die Kennzahl, um die es dem Melder ging, folgt mit. Der Nenner ist
    # das UNGERUNDETE SOLL (100 × 13/31) — die Route rundet erst die Anzeige,
    # nicht die Rechnung.
    assert monate[3].performance_ratio == round(60.8 / (100 * 13 / 31), 3)


async def test_route_laesst_vollen_monat_bitgleich(db):
    """Gegenprobe: Anschaffung am Monatsersten → kein Abschlag."""
    anlage_id = await _anlage_ab_mitte_maerz(db, anschaffung=date(2026, 3, 1))

    resp = await get_pv_strings(anlage_id=anlage_id, jahr=2026, db=db)
    monate = {m.monat: m for m in resp.strings[0].monatswerte}
    assert monate[3].prognose_kwh == 100.0


async def test_gesamtlaufzeit_kuerzt_das_anschaffungsjahr_mit(db):
    """Auch die Laufzeit-Sicht — sonst widersprächen sich zwei Sichten."""
    anlage_id = await _anlage_ab_mitte_maerz(db, anschaffung=date(2026, 3, 19))

    resp = await get_pv_strings_gesamtlaufzeit(anlage_id=anlage_id, db=db)
    jahr = next(
        j for j in resp.strings[0].jahreswerte if j.jahr == 2026
    )
    # März 41,9 + April 100,0 statt 200,0
    assert round(jahr.prognose_kwh, 1) == 141.9
