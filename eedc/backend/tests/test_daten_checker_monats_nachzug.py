"""
Akzeptanztest Nachlauf v4.0.3 — der Monats-Diskriminator.

Nach einer Tages-Reparatur stehen die Tage voll da, während der Monatswert auf
seinem alten Stand bleibt (coolxmad, #353). Prüfung 3 („Einspeisung >
PV-Erzeugung") nannte dafür bisher „Sensoren vertauscht" zuerst, Prüfung 3b die
ungepflegte Netzladung — bei diesem Melder trifft beides nicht zu. Es gibt einen
prüfbaren Diskriminator: Σ der Tageswerte des Monats ≫ Monatswert. Liegt der
vor, nennt die BESTEHENDE Meldung diese Ursache zuerst und verweist auf den
Statistik-Import — statt einer vierten Meldung über denselben Sachverhalt.

    eedc/backend/tests/test_daten_checker_monats_nachzug.py
"""

from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.models import (  # noqa: F401
    Anlage, Investition, InvestitionMonatsdaten, Monatsdaten,
)
from backend.models.tages_energie_profil import TagesZusammenfassung

_MELDUNG_3 = "> PV-Erzeugung"
_VORSPANN = "Wahrscheinlichste Ursache zuerst"


async def _seed(
    db: AsyncSession, *, pv_monat: float, einspeisung: float, tages_pv: float | None,
) -> tuple[Anlage, list[Monatsdaten]]:
    """Ein PV-String + optional Tageszeilen für Mai 2024."""
    anlage = Anlage(anlagenname="Test", leistung_kwp=10.0,
                    installationsdatum=date(2024, 1, 1))
    db.add(anlage)
    await db.flush()
    modul = Investition(
        anlage_id=anlage.id, typ="pv-module", bezeichnung="Dach", leistung_kwp=10.0,
        anschaffungsdatum=date(2024, 1, 1), aktiv=True,
    )
    db.add(modul)
    await db.flush()

    db.add(InvestitionMonatsdaten(
        investition_id=modul.id, jahr=2024, monat=5,
        verbrauch_daten={"pv_erzeugung_kwh": pv_monat},
    ))
    db.add(Monatsdaten(
        anlage_id=anlage.id, jahr=2024, monat=5,
        einspeisung_kwh=einspeisung, netzbezug_kwh=200.0,
    ))
    if tages_pv is not None:
        # 10 Tageszeilen, zusammen `tages_pv` kWh.
        for tag in range(1, 11):
            db.add(TagesZusammenfassung(
                anlage_id=anlage.id, datum=date(2024, 5, tag),
                stunden_verfuegbar=24, datenquelle="scheduler",
                komponenten_kwh={f"pv_{modul.id}": tages_pv / 10},
            ))
    await db.commit()

    anlage = (await db.execute(
        select(Anlage)
        .options(selectinload(Anlage.investitionen).selectinload(Investition.monatsdaten))
        .where(Anlage.id == anlage.id)
    )).scalar_one()
    monatsdaten = list((await db.execute(
        select(Monatsdaten).where(Monatsdaten.anlage_id == anlage.id)
    )).scalars().all())
    return anlage, monatsdaten


async def _pruefung_3(db, anlage, monatsdaten):
    from backend.services.daten_checker import DatenChecker

    ergebnisse = await DatenChecker(db)._check_monatsdaten_plausibilitaet(
        anlage, monatsdaten
    )
    return [e for e in ergebnisse if _MELDUNG_3 in (e.meldung or "")]


async def test_nachzug_ursache_steht_zuerst(db):
    """Monat 26 kWh, Tage summieren 900 kWh → „nie nachgezogen" zuerst.

    Das ist coolxmads Konstellation (#353): die Tage sind geheilt, der Monat
    nicht. „Sensoren vertauscht" wäre hier die falsche erste Antwort.
    """
    anlage, md = await _seed(db, pv_monat=26.0, einspeisung=469.0, tages_pv=900.0)

    treffer = await _pruefung_3(db, anlage, md)

    assert treffer, "Einspeisung 469 > PV 26 kWh muss weiter gemeldet werden"
    details = treffer[0].details or ""
    assert details.startswith(_VORSPANN), f"Vorspann fehlt oder steht nicht zuerst: {details}"
    assert "900 kWh" in details, details
    assert "26 kWh" in details, details
    assert "Statistik-Import" in details, details
    assert "Konflikte" in details, details
    # Die alte Ursache bleibt erhalten — sie wird nur nachgeordnet.
    assert "vertauscht" in details, details


async def test_ohne_tageswerte_bleibt_die_alte_ursache_allein(db):
    """Keine Tageszeilen → kein Diskriminator → unveränderte Meldung."""
    anlage, md = await _seed(db, pv_monat=26.0, einspeisung=469.0, tages_pv=None)

    treffer = await _pruefung_3(db, anlage, md)

    assert treffer
    details = treffer[0].details or ""
    assert _VORSPANN not in details, details
    assert details.startswith("Einspeisung kann nicht höher"), details


async def test_tageswerte_passen_zum_monat_kein_vorspann(db):
    """Tage und Monat sind sich einig → der Monat wurde nachgezogen, kein Hinweis.

    Die Gegenprobe, die den Diskriminator trägt: sonst hinge der Vorspann an
    jeder Prüfung-3-Meldung und wäre wertlos.
    """
    anlage, md = await _seed(db, pv_monat=400.0, einspeisung=469.0, tages_pv=405.0)

    treffer = await _pruefung_3(db, anlage, md)

    assert treffer
    assert _VORSPANN not in (treffer[0].details or ""), treffer[0].details


async def test_kleine_boundary_drift_loest_nicht_aus(db):
    """Tage 415 gegen Monat 400 kWh — unter beiden Schwellen (20 % UND 20 kWh)."""
    anlage, md = await _seed(db, pv_monat=400.0, einspeisung=469.0, tages_pv=415.0)

    treffer = await _pruefung_3(db, anlage, md)

    assert treffer
    assert _VORSPANN not in (treffer[0].details or ""), treffer[0].details
