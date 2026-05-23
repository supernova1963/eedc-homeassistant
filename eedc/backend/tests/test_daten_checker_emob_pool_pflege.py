"""Daten-Checker: evcc-Pool-Pflege-Mismatch-Warnung (Wallbox/EAuto-Konzept Phase 2a).

Trigger: junky84 #262 hatte ~3.300 kWh Streudaten auf der E-Auto-Investition
zusätzlich zur korrekten Wallbox-Pflege. Der Pool-Helper
`aggregiere_emob_ladung` wählt heuristisch die Quelle mit der größeren
Heimladung als Gewinner — bei Streudaten auf der falschen Seite kann das
still falsch sein. Diese Diagnose erkennt das Pflege-Muster und lenkt
den Anwender auf eine bewusste Entscheidung.

Tests sichern:
- Kein Eintrag wenn nur eine Quelle gepflegt (Normalfall).
- Kein Eintrag bei Krümel-Pflege (eine Quelle dominant, andere < 10 kWh).
- Kein Eintrag bei einmaliger Doppel-Pflege (< 3 Monate).
- INFO bei ≥ 3 doppelten Monaten mit ähnlichen Heimladungs-Summen.
- WARNING wenn zusätzlich PV-Inkonsistenz (> 10 % Differenz).
- `ist_dienstlich`-Filter greift ([[feedback_dienstwagen_alle_checks]]).
"""

from __future__ import annotations

from datetime import date

from backend.models import (
    Anlage,
    Investition,
    InvestitionMonatsdaten,
)
from backend.services.daten_checker import (
    CheckKategorie,
    CheckSeverity,
    DatenChecker,
)


# ── Helper ──────────────────────────────────────────────────────────────────

async def _seed_anlage(db) -> Anlage:
    anlage = Anlage(anlagenname="Test", leistung_kwp=10.0, standort_land="DE")
    db.add(anlage)
    await db.flush()
    return anlage


async def _add_inv(
    db, anlage_id: int, typ: str, *,
    parameter: dict | None = None,
) -> Investition:
    inv = Investition(
        anlage_id=anlage_id,
        typ=typ,
        bezeichnung=f"Test-{typ}",
        anschaffungsdatum=date(2024, 1, 1),
        parameter=parameter or {},
    )
    db.add(inv)
    await db.flush()
    return inv


async def _add_monat(
    db, inv_id: int, jahr: int, monat: int,
    *, ladung_kwh: float, ladung_pv_kwh: float = 0.0,
) -> None:
    db.add(InvestitionMonatsdaten(
        investition_id=inv_id, jahr=jahr, monat=monat,
        verbrauch_daten={
            "ladung_kwh": ladung_kwh,
            "ladung_pv_kwh": ladung_pv_kwh,
        },
    ))


async def _run_check(db, anlage: Anlage):
    """Liest die Anlage frisch (mit Investitionen + Monatsdaten) und ruft die
    Check-Methode direkt. Umgeht den vollen `check_anlage`-Pfad, damit der
    Test nicht von anderen Checks abhängt."""
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload

    result = await db.execute(
        select(Anlage)
        .options(selectinload(Anlage.investitionen).selectinload(Investition.monatsdaten))
        .where(Anlage.id == anlage.id)
    )
    geladen = result.scalar_one()
    checker = DatenChecker(db)
    return checker._check_emob_pool_pflege(geladen)


def _letzte_n_monate(n: int) -> list[tuple[int, int]]:
    """Erzeugt die letzten N (jahr, monat)-Tupel — passt zum Fenster der Check-Logik."""
    heute = date.today()
    out: list[tuple[int, int]] = []
    for offset in range(n):
        jahr = heute.year + ((heute.month - 1 - offset) // 12)
        monat = ((heute.month - 1 - offset) % 12) + 1
        out.append((jahr, monat))
    return out


# ── Tests ───────────────────────────────────────────────────────────────────


async def test_nur_wallbox_kein_eintrag(db):
    """Anwender pflegt nur Wallbox — kein Pflege-Konflikt möglich."""
    anlage = await _seed_anlage(db)
    wb = await _add_inv(db, anlage.id, "wallbox")
    for j, m in _letzte_n_monate(6):
        await _add_monat(db, wb.id, j, m, ladung_kwh=200.0, ladung_pv_kwh=150.0)
    await db.commit()

    ergebnisse = await _run_check(db, anlage)
    assert ergebnisse == []


async def test_nur_eauto_kein_eintrag(db):
    """Anwender pflegt nur E-Auto — kein Pflege-Konflikt möglich."""
    anlage = await _seed_anlage(db)
    ea = await _add_inv(db, anlage.id, "e-auto")
    for j, m in _letzte_n_monate(6):
        await _add_monat(db, ea.id, j, m, ladung_kwh=200.0, ladung_pv_kwh=150.0)
    await db.commit()

    ergebnisse = await _run_check(db, anlage)
    assert ergebnisse == []


async def test_kruemel_pflege_kein_eintrag(db):
    """WB dominant, EA mit Krümeln (< 10 kWh/Monat) → kein Konflikt.

    Das passiert typisch wenn evcc-Vehicle-Topics nur sporadisch gepflegt
    werden — die Pool-Heuristik wählt klar Wallbox, kein Fehlalarm.
    """
    anlage = await _seed_anlage(db)
    wb = await _add_inv(db, anlage.id, "wallbox")
    ea = await _add_inv(db, anlage.id, "e-auto")
    for j, m in _letzte_n_monate(6):
        await _add_monat(db, wb.id, j, m, ladung_kwh=200.0, ladung_pv_kwh=150.0)
        await _add_monat(db, ea.id, j, m, ladung_kwh=5.0, ladung_pv_kwh=3.0)
    await db.commit()

    ergebnisse = await _run_check(db, anlage)
    assert ergebnisse == []


async def test_einmaliger_doppelmonat_kein_eintrag(db):
    """Eine Monatslücke (Doppel-Pflege nur in 1 Monat) → kein Pflege-Muster.

    Schwelle EMOB_POOL_MINDEST_MONATE = 3 verhindert Fehlalarm bei
    Einmal-Sondersituationen (z. B. Wechsel des Sensors mid-month).
    """
    anlage = await _seed_anlage(db)
    wb = await _add_inv(db, anlage.id, "wallbox")
    ea = await _add_inv(db, anlage.id, "e-auto")
    monate = _letzte_n_monate(6)
    # Nur im ersten Monat Doppel-Pflege.
    await _add_monat(db, wb.id, *monate[0], ladung_kwh=200.0, ladung_pv_kwh=150.0)
    await _add_monat(db, ea.id, *monate[0], ladung_kwh=200.0, ladung_pv_kwh=150.0)
    for j, m in monate[1:]:
        await _add_monat(db, wb.id, j, m, ladung_kwh=200.0, ladung_pv_kwh=150.0)
    await db.commit()

    ergebnisse = await _run_check(db, anlage)
    assert ergebnisse == []


async def test_drei_doppelmonate_konsistent_info(db):
    """≥ 3 Monate Doppel-Pflege mit übereinstimmenden PV-Werten → INFO."""
    anlage = await _seed_anlage(db)
    wb = await _add_inv(db, anlage.id, "wallbox")
    ea = await _add_inv(db, anlage.id, "e-auto")
    for j, m in _letzte_n_monate(6):
        # Identische Werte: User pflegt dieselben Zahlen doppelt → INFO, kein
        # echter Konflikt, nur Effizienz-Hinweis.
        await _add_monat(db, wb.id, j, m, ladung_kwh=200.0, ladung_pv_kwh=150.0)
        await _add_monat(db, ea.id, j, m, ladung_kwh=200.0, ladung_pv_kwh=150.0)
    await db.commit()

    ergebnisse = await _run_check(db, anlage)
    assert len(ergebnisse) == 1
    e = ergebnisse[0]
    assert e.kategorie == CheckKategorie.EMOB_POOL_PFLEGE.value
    assert e.schwere == CheckSeverity.INFO.value
    assert "parallel" in e.meldung.lower()


async def test_pv_inkonsistenz_warning(db):
    """≥ 3 Doppelmonate UND PV-Differenz > 10 % → WARNING (echter Konflikt)."""
    anlage = await _seed_anlage(db)
    wb = await _add_inv(db, anlage.id, "wallbox")
    ea = await _add_inv(db, anlage.id, "e-auto")
    for j, m in _letzte_n_monate(6):
        # WB sieht 80 % PV, EA nur 20 % — sollte derselbe Stromfluss sein,
        # ist es offensichtlich nicht. Echter Pflege-Konflikt.
        await _add_monat(db, wb.id, j, m, ladung_kwh=200.0, ladung_pv_kwh=160.0)
        await _add_monat(db, ea.id, j, m, ladung_kwh=200.0, ladung_pv_kwh=40.0)
    await db.commit()

    ergebnisse = await _run_check(db, anlage)
    assert len(ergebnisse) == 1
    e = ergebnisse[0]
    assert e.kategorie == CheckKategorie.EMOB_POOL_PFLEGE.value
    assert e.schwere == CheckSeverity.WARNING.value
    assert "Konflikt" in e.meldung


async def test_dienstwagen_wird_ignoriert(db):
    """`ist_dienstlich=True` zählt nicht zur Pool-Pflege — eigene Kosten-Logik."""
    anlage = await _seed_anlage(db)
    wb = await _add_inv(db, anlage.id, "wallbox")
    ea = await _add_inv(
        db, anlage.id, "e-auto",
        parameter={"ist_dienstlich": True},  # dienstlich → raus
    )
    for j, m in _letzte_n_monate(6):
        await _add_monat(db, wb.id, j, m, ladung_kwh=200.0, ladung_pv_kwh=150.0)
        await _add_monat(db, ea.id, j, m, ladung_kwh=200.0, ladung_pv_kwh=150.0)
    await db.commit()

    ergebnisse = await _run_check(db, anlage)
    # Dienst-EA ist raus → effektiv nur Wallbox → kein Konflikt.
    assert ergebnisse == []
