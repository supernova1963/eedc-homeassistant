"""
Akzeptanztests für den PR-Plausi-Check `_check_pv_ueber_erfassung`
(rapahl-PN 2026-05-19).

Hintergrund: bei BKW-Doppelerfassung (WR-Smart-Meter zählt BKW mit + BKW-
Mapping zählt nochmal) ist Performance Ratio physikalisch > 1.0. Der neue
Check liest `TagesZusammenfassung.performance_ratio` direkt und meldet
Verdacht ab 3 Tagen ≥ 20 % der PR-Tage über Schwelle 1.05.

Spez. Tagesertrag > 7 kWh/kWp ist Zusatzmarker für Doppelerfassung selbst
ohne verfügbaren PR-Wert.
"""

from __future__ import annotations

from datetime import date, timedelta

from backend.models import Anlage
from backend.models.tages_energie_profil import TagesZusammenfassung
from backend.services.daten_checker import (
    CheckKategorie,
    CheckSeverity,
    DatenChecker,
)


async def _seed_anlage(db, *, kwp: float = 10.0) -> int:
    anlage = Anlage(anlagenname="Test", leistung_kwp=kwp, standort_land="DE")
    db.add(anlage)
    await db.flush()
    return anlage.id


async def _add_tag(
    db, anlage_id: int, datum: date,
    *, pr: float | None = None, pv_kwh: float | None = None,
) -> None:
    komponenten = {"pv_1": pv_kwh} if pv_kwh is not None else None
    db.add(TagesZusammenfassung(
        anlage_id=anlage_id, datum=datum,
        performance_ratio=pr, komponenten_kwh=komponenten,
    ))


async def _run_check(db, anlage_id: int):
    """Direkt die neue Methode aufrufen, ohne den ganzen check_anlage-Pfad."""
    from sqlalchemy import select as _select
    anlage = (await db.execute(
        _select(Anlage).where(Anlage.id == anlage_id)
    )).scalar_one()
    checker = DatenChecker(db)
    return await checker._check_pv_ueber_erfassung(anlage)


def _pv_ergebnis(ergebnisse):
    return [e for e in ergebnisse if e.kategorie == CheckKategorie.PV_UEBER_ERFASSUNG.value]


async def test_pr_unterhalb_schwelle_kein_eintrag(db):
    """PR ≤ 1.05 an allen Tagen → keine Meldung."""
    aid = await _seed_anlage(db)
    today = date.today()
    for i in range(10):
        await _add_tag(db, aid, today - timedelta(days=i), pr=0.85)
    await db.commit()

    ergebnisse = await _run_check(db, aid)
    assert _pv_ergebnis(ergebnisse) == []


async def test_pr_zu_wenig_tage_kein_eintrag(db):
    """Nur 2 Tage PR > 1.05 (unter Mindest-3-Tage-Schwelle) → keine Meldung."""
    aid = await _seed_anlage(db)
    today = date.today()
    for i, pr in enumerate([1.20, 1.18, 0.9, 0.85, 0.88, 0.9, 0.92, 0.95, 0.9, 0.88]):
        await _add_tag(db, aid, today - timedelta(days=i), pr=pr)
    await db.commit()

    ergebnisse = await _run_check(db, aid)
    assert _pv_ergebnis(ergebnisse) == []


async def test_pr_zu_geringer_anteil_kein_eintrag(db):
    """3 Tage über Schwelle bei 30 PR-Tagen = 10 % → unter 20 %-Anteil, kein Eintrag."""
    aid = await _seed_anlage(db)
    today = date.today()
    # 3 Tage drüber + 27 Tage drunter
    for i in range(3):
        await _add_tag(db, aid, today - timedelta(days=i), pr=1.18)
    for i in range(3, 30):
        await _add_tag(db, aid, today - timedelta(days=i), pr=0.85)
    await db.commit()

    ergebnisse = await _run_check(db, aid)
    assert _pv_ergebnis(ergebnisse) == []


async def test_pr_dauerhaft_drueber_warnung(db):
    """5 von 10 Tagen mit PR > 1.05 (50 %) → Warnung."""
    aid = await _seed_anlage(db)
    today = date.today()
    werte = [1.22, 1.20, 1.18, 1.15, 1.10, 0.9, 0.85, 0.92, 0.88, 0.95]
    for i, pr in enumerate(werte):
        await _add_tag(db, aid, today - timedelta(days=i), pr=pr)
    await db.commit()

    ergebnisse = await _run_check(db, aid)
    pv = _pv_ergebnis(ergebnisse)
    assert len(pv) == 1
    e = pv[0]
    assert e.schwere == CheckSeverity.WARNING.value
    assert "Doppelerfassung" in e.meldung or "Doppelerfassung" in (e.details or "")
    assert "BKW" in (e.details or "")
    # Höchstwerte in Details
    assert "1.22" in (e.details or "")


async def test_spez_ertrag_signal_ohne_pr(db):
    """3 Tage spez. Tagesertrag > 7 kWh/kWp, PR nicht gesetzt → Warnung."""
    aid = await _seed_anlage(db, kwp=10.0)
    today = date.today()
    # 3 Tage mit 75 kWh = 7.5 kWh/kWp + 5 unauffällige Tage
    for i in range(3):
        await _add_tag(db, aid, today - timedelta(days=i), pv_kwh=75.0)
    for i in range(3, 8):
        await _add_tag(db, aid, today - timedelta(days=i), pv_kwh=40.0)
    await db.commit()

    ergebnisse = await _run_check(db, aid)
    pv = _pv_ergebnis(ergebnisse)
    assert len(pv) == 1
    assert "7" in (pv[0].details or "")
    assert "kWh/kWp" in (pv[0].details or "")


async def test_keine_anlage_kwp_kein_check(db):
    """leistung_kwp=0 → Check übersprungen, Stammdaten meldet das schon."""
    aid = await _seed_anlage(db, kwp=0)
    today = date.today()
    for i in range(5):
        await _add_tag(db, aid, today - timedelta(days=i), pr=1.20)
    await db.commit()

    ergebnisse = await _run_check(db, aid)
    assert _pv_ergebnis(ergebnisse) == []


async def test_keine_tages_zusammenfassung_kein_check(db):
    """Frische Anlage ohne Tagesdaten → kein Eintrag (kein Vergleichsmaterial)."""
    aid = await _seed_anlage(db)
    await db.commit()

    ergebnisse = await _run_check(db, aid)
    assert _pv_ergebnis(ergebnisse) == []


async def test_rapahl_szenario_pr_grenze_genau_eingehalten(db):
    """PR = 1.05 (Grenze) gilt nicht als Überschreitung — Toleranz für
    Mess-Rauschen, sonst False Positives bei sauberen Anlagen."""
    aid = await _seed_anlage(db)
    today = date.today()
    for i in range(10):
        await _add_tag(db, aid, today - timedelta(days=i), pr=1.05)
    await db.commit()

    ergebnisse = await _run_check(db, aid)
    assert _pv_ergebnis(ergebnisse) == []


async def test_beide_signale_gleichzeitig_eine_meldung(db):
    """PR-Signal + Spez-Ertrag-Signal gemeinsam → ein Eintrag mit beiden
    Marker-Zeilen verkettet, nicht zwei separate Warnings."""
    aid = await _seed_anlage(db, kwp=10.0)
    today = date.today()
    # 5 Tage mit PR=1.18 UND pv=75 kWh (= 7.5 kWh/kWp) + 5 unauffällig
    for i in range(5):
        await _add_tag(db, aid, today - timedelta(days=i), pr=1.18, pv_kwh=75.0)
    for i in range(5, 10):
        await _add_tag(db, aid, today - timedelta(days=i), pr=0.9, pv_kwh=40.0)
    await db.commit()

    ergebnisse = await _run_check(db, aid)
    pv = _pv_ergebnis(ergebnisse)
    assert len(pv) == 1
    details = pv[0].details or ""
    assert "Performance Ratio" in details
    assert "kWh/kWp" in details


async def test_komponenten_kwh_mit_nicht_numerischen_werten(db):
    """JSON-Feld kann auch String- oder None-Werte enthalten (Drift aus
    älteren Versionen, externe Importer). isinstance-Guard im Helper muss
    sie überspringen, nicht crashen."""
    aid = await _seed_anlage(db, kwp=10.0)
    today = date.today()
    db.add(TagesZusammenfassung(
        anlage_id=aid, datum=today,
        performance_ratio=0.85,
        komponenten_kwh={"pv_1": 40.0, "pv_2": None, "pv_bad": "n/a", "bkw_1": 5.0},
    ))
    await db.commit()

    ergebnisse = await _run_check(db, aid)
    # 45 kWh / 10 kWp = 4.5 kWh/kWp → unter Schwelle, keine Warnung,
    # aber wichtig: kein Crash beim Lesen non-numeric Werte.
    assert _pv_ergebnis(ergebnisse) == []
