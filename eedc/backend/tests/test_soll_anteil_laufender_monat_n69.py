"""N-69 — die SOLL-Erfüllung misst die Anlage, nicht das Datum.

PVGIS liefert Monatssummen. Im laufenden Monat stand diese volle Summe als
Nenner über einem angefangenen Ertrag: an Gernots Anlage am 2026-08-04
**264,75 IST gegen 1.387,9 SOLL = 19 %**, während dieselbe Anlage über die
abgeschlossenen Monate Jan–Jul auf **119 %** kam. In der Jahres-Kachel (Σ der
Monatswerte) wurden daraus **104 % statt 119 %**.

Entscheid Gernot 2026-08-04: den **Nenner** kürzen (nicht den laufenden Monat
auslassen), damit die Monatssicht ihre Einordnung behält.

Die Uhr ist überall ein Parameter — kein Test hängt an `date.today()`
([[feedback_tests_ci_hermetisch]]).
"""

from __future__ import annotations

from datetime import date, datetime

from backend.core.berechnungen import Monatsfenster, anteilig, monatsfenster
from backend.models import Anlage
from backend.models.pvgis_prognose import PVGISMonatsprognose, PVGISPrognose

# Live gemessen an Gernots Anlage (Winterborn, 12,32 kWp) am 2026-08-04.
HEUTE = date(2026, 8, 4)
SOLL_AUGUST_KWH = 1387.9
IST_AUGUST_KWH = 264.75
SOLL_JAN_JUL = [396.1, 615.7, 1052.7, 1411.8, 1466.2, 1477.2, 1509.0]
IST_JAN_JUL = [330.11, 545.41, 1439.9, 1786.5, 1751.3, 1753.8, 1843.25]


# ============================================================================
# 1. Der Layer — welches Fenster ein Monat am Stichtag hat
# ============================================================================


def test_laufender_monat_zaehlt_nur_die_abgelaufenen_tage():
    """Der laufende Tag zählt VOLL mit — die konservative Richtung.

    Ihn wegzulassen machte den Nenner kleiner und die Quote höher, also genau
    die Richtung, aus der der Fehler kam (dieselbe Wahl wie „2 von 31 Tagen"
    beim Connector, #360).
    """
    f = monatsfenster(2026, 8, heute=HEUTE)
    assert (f.tage, f.tage_gesamt) == (4, 31)
    assert f.ist_angefangen is True


def test_abgeschlossener_monat_bleibt_unangetastet():
    """Historie darf sich nicht bewegen — sonst schriebe der Fix die Vergangenheit um."""
    f = monatsfenster(2026, 7, heute=HEUTE)
    assert (f.tage, f.tage_gesamt) == (31, 31)
    assert f.ist_angefangen is False
    assert anteilig(1509.0, f) == 1509.0


def test_zukunftsmonat_hat_null_tage():
    """Ein Monat, der noch nicht stattgefunden hat, bekommt kein SOLL zugerechnet.

    Die Anzeige-Sites prüfen `> 0` und lassen die Quote damit weg, statt eine
    0-%-Erfüllung für den September zu melden.
    """
    f = monatsfenster(2026, 9, heute=HEUTE)
    assert (f.tage, f.tage_gesamt) == (0, 30)
    assert anteilig(1509.0, f) == 0.0


def test_letzter_tag_des_monats_ist_voll():
    """Am 31. steht der volle Monat — kein Rest, der die Quote überzeichnet."""
    f = monatsfenster(2026, 8, heute=date(2026, 8, 31))
    assert (f.tage, f.tage_gesamt) == (31, 31)
    assert f.ist_angefangen is False


def test_fehlendes_soll_bleibt_none():
    """`None` wird nicht zu 0 — „kein SOLL" ist keine Aussage über die Menge."""
    assert anteilig(None, monatsfenster(2026, 8, heute=HEUTE)) is None


def test_gemessene_augustzahlen_werden_ehrlich():
    """Die vorgelegte Messung, gegengerechnet: 19 % → 148 %."""
    f = monatsfenster(2026, 8, heute=HEUTE)
    soll = round(anteilig(SOLL_AUGUST_KWH, f), 1)
    assert soll == 179.1
    assert round(IST_AUGUST_KWH / soll * 100) == 148
    # Die alte Rechnung zum Vergleich — sie maß das Datum.
    assert round(IST_AUGUST_KWH / SOLL_AUGUST_KWH * 100) == 19


def test_jahressumme_trifft_die_abgeschlossenen_monate():
    """Die Gegenprobe, die den Weg trägt.

    Das Jahr summiert die Monatswerte. Mit gekürztem August liegt es bei
    119,8 % — 0,6 Prozentpunkte neben den 119,2 % aus den abgeschlossenen
    Monaten allein. Ungekürzt waren es 104,3 %.
    """
    f = monatsfenster(2026, 8, heute=HEUTE)
    ist = sum(IST_JAN_JUL) + IST_AUGUST_KWH
    neu = ist / (sum(SOLL_JAN_JUL) + anteilig(SOLL_AUGUST_KWH, f)) * 100
    alt = ist / (sum(SOLL_JAN_JUL) + SOLL_AUGUST_KWH) * 100
    nur_abgeschlossen = sum(IST_JAN_JUL) / sum(SOLL_JAN_JUL) * 100

    assert round(neu, 1) == 119.8
    assert round(alt, 1) == 104.3
    assert round(nur_abgeschlossen, 1) == 119.2
    assert abs(neu - nur_abgeschlossen) < 1.0


def test_monatsfenster_ist_direkt_konstruierbar():
    """Die Kennzahlen hängen an den zwei Feldern, nicht an einer Uhr im Rumpf."""
    assert Monatsfenster(tage=15, tage_gesamt=30).anteil == 0.5
    assert Monatsfenster(tage=0, tage_gesamt=0).anteil == 0.0  # kein ZeroDivision


# ============================================================================
# 2. Die Route — was in der Antwort steht
# ============================================================================


async def _seed_prognose(db, *, monat: int, ertrag_kwh: float) -> int:
    anlage = Anlage(anlagenname="N69", leistung_kwp=12.32)
    db.add(anlage)
    await db.flush()
    prognose = PVGISPrognose(
        anlage_id=anlage.id, latitude=50.9, longitude=7.5,
        neigung_grad=36.0, ausrichtung_grad=0.0, gesamt_leistung_kwp=12.32,
        abgerufen_am=datetime(2026, 1, 1, 12, 0),
        jahresertrag_kwh=12000.0, spezifischer_ertrag_kwh_kwp=974.0,
        ist_aktiv=True,
    )
    db.add(prognose)
    await db.flush()
    db.add(PVGISMonatsprognose(
        prognose_id=prognose.id, monat=monat,
        ertrag_kwh=ertrag_kwh, einstrahlung_kwh_m2=150.0,
    ))
    await db.commit()
    return anlage.id


async def test_route_kuerzt_das_soll_des_laufenden_monats(db):
    from backend.api.routes.aktueller_monat import _load_soll_pv

    anlage_id = await _seed_prognose(db, monat=8, ertrag_kwh=SOLL_AUGUST_KWH)
    soll = await _load_soll_pv(
        anlage_id, 2026, 8, db, monatsfenster(2026, 8, heute=HEUTE),
    )
    assert soll == 179.1


async def test_route_laesst_abgeschlossene_monate_unveraendert(db):
    """Derselbe Aufruf für den Juli liefert das volle Monats-SOLL."""
    from backend.api.routes.aktueller_monat import _load_soll_pv

    anlage_id = await _seed_prognose(db, monat=7, ertrag_kwh=1509.0)
    soll = await _load_soll_pv(
        anlage_id, 2026, 7, db, monatsfenster(2026, 7, heute=HEUTE),
    )
    assert soll == 1509.0


async def test_route_ohne_prognose_liefert_none(db):
    """Ohne aktive Prognose bleibt es bei „kein SOLL" — nicht bei 0."""
    from backend.api.routes.aktueller_monat import _load_soll_pv

    anlage = Anlage(anlagenname="N69-leer", leistung_kwp=10.0)
    db.add(anlage)
    await db.commit()
    soll = await _load_soll_pv(
        anlage.id, 2026, 8, db, monatsfenster(2026, 8, heute=HEUTE),
    )
    assert soll is None
