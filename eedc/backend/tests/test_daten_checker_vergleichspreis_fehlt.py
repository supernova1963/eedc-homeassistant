"""Daten-Checker: Monatszeilen ohne Ø-Benzinpreis (Discussion #394, gruaGit).

**Der Fall.** Er fragte nach historischen Benzinpreisen für den
Amortisations-Fortschritt und bekam die Antwort, eedc trage jeden Monat ohne
Preis automatisch nach. Er sah nach: Juni 2026 leer. Die Automatik gab es —
sie lief nur **wöchentlich** (Dienstag 06:00, der einzige Wochen-Takt im
ganzen Scheduler) und hatte keinen Startlauf. Eine Monatszeile, die zwischen
zwei Läufen entsteht, blieb bis zu sieben Tage ohne Marktpreis, und der
E-Auto-Vergleich rechnete solange still mit dem Modellwert weiter.

Das Paket macht daraus zwei Hälften: der Takt ist täglich geworden und hat
einen Startlauf bekommen (`scheduler.py`), **und dieser Checker sagt es**,
wenn doch einmal ein Monat offen bleibt — mit dem Reparatur-Knopf daneben, der
seit Etappe 3d existiert, aber von nirgends aus erreichbar war.

Proben:
- Ohne E-Auto **kein** Eintrag (eine Warnung, die niemanden betrifft, wird man
  nie wieder los — die #389-Lehre).
- Mit E-Auto und gefüllten Preisen: OK-Meldung.
- Mit E-Auto und offenen Monaten: WARNING **mit** `action_kind`, weil es hier
  nichts zu raten gibt.
- Monate **vor** dem Anschaffungsdatum des E-Autos zählen nicht mit
  ([[feedback_anschaffungsdatum_grenze]]).
"""

from __future__ import annotations

from backend.tests.werkzeug_befund import befund_op, befund_params
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from backend.models import Anlage, Investition
from backend.models.monatsdaten import Monatsdaten
from backend.services.daten_checker import (
    CheckKategorie,
    CheckSeverity,
    DatenChecker,
)


async def _seed(db, *, mit_eauto: bool, anschaffung: date = date(2025, 1, 15)) -> Anlage:
    anlage = Anlage(anlagenname="Test", leistung_kwp=10.0, standort_land="AT")
    db.add(anlage)
    await db.flush()
    if mit_eauto:
        db.add(Investition(
            anlage_id=anlage.id, typ="e-auto", bezeichnung="ID.3",
            anschaffungsdatum=anschaffung, parameter={},
        ))
    await db.flush()
    return anlage


async def _add_monat(db, anlage_id: int, jahr: int, monat: int, *, preis: float | None) -> None:
    db.add(Monatsdaten(
        anlage_id=anlage_id, jahr=jahr, monat=monat,
        einspeisung_kwh=100.0, netzbezug_kwh=50.0,
        kraftstoffpreis_euro=preis,
    ))


async def _run(db, anlage: Anlage):
    geladen = (await db.execute(
        select(Anlage)
        .options(selectinload(Anlage.investitionen))
        .where(Anlage.id == anlage.id)
    )).scalar_one()
    return await DatenChecker(db)._check_vergleichspreis_fehlt(geladen)


async def test_ohne_eauto_kein_eintrag(db):
    """Ohne E-Auto ist das Feld bedeutungslos — kein Befund, auch keine OK-Zeile."""
    anlage = await _seed(db, mit_eauto=False)
    await _add_monat(db, anlage.id, 2026, 6, preis=None)
    await db.commit()

    assert await _run(db, anlage) == []


async def test_alle_monate_gepflegt_meldet_ok(db):
    anlage = await _seed(db, mit_eauto=True)
    await _add_monat(db, anlage.id, 2026, 5, preis=1.72)
    await _add_monat(db, anlage.id, 2026, 6, preis=1.69)
    await db.commit()

    ergebnisse = await _run(db, anlage)
    assert len(ergebnisse) == 1
    assert ergebnisse[0].schwere == CheckSeverity.OK.value
    assert befund_op(ergebnisse[0]) is None


async def test_offener_monat_meldet_warnung_mit_reparatur(db):
    """Der Fall des Melders: Juni ohne Preis, Mai gepflegt."""
    anlage = await _seed(db, mit_eauto=True)
    await _add_monat(db, anlage.id, 2026, 5, preis=1.72)
    await _add_monat(db, anlage.id, 2026, 6, preis=None)
    await db.commit()

    ergebnisse = await _run(db, anlage)
    assert len(ergebnisse) == 1
    e = ergebnisse[0]
    assert e.kategorie == CheckKategorie.VERGLEICHSPREIS_FEHLT.value
    assert e.schwere == CheckSeverity.WARNING.value
    assert "06/2026" in e.meldung
    # Der Knopf ist der Punkt: der Reparatur-Pfad existierte, war aber nur über
    # die Reparatur-Werkbank erreichbar.
    assert befund_op(e) == "kraftstoffpreis_backfill"
    assert befund_params(e) == {"scope": "monats"}  # E3: Plan-Parameter von KRAFTSTOFFPREIS_BACKFILL
    assert e.knopf


async def test_w11_benzinpreise_nachtragen_ueber_plan_und_ausfuehren(db, monkeypatch):
    """W-11 (E3): der Knopf «Benzinpreise nachtragen» geht über ``plan`` → ``execute`` mit den Parametern des Befunds;
    danach meldet die Prüfung den Monat nicht mehr (Wochenpreise ohne Netz)."""
    from backend.services import kraftstoff_preis_service as kps
    from backend.services.repair_orchestrator import (
        RepairOperationRequest, RepairOperationType, _reset_state_for_tests, execute, plan,
    )

    async def _preise(_land, force_refresh=False):
        return [(date(2026, 6, 1), 1.81), (date(2026, 6, 29), 1.79)]

    monkeypatch.setattr(kps, "get_kraftstoffpreise", _preise)
    _reset_state_for_tests()
    anlage = await _seed(db, mit_eauto=True)
    await _add_monat(db, anlage.id, 2026, 6, preis=None)
    await db.commit()
    (e,) = await _run(db, anlage)
    p = await plan(RepairOperationRequest(anlage_id=anlage.id, operation=RepairOperationType(befund_op(e)),
                                          params=befund_params(e)), db)
    assert p.estimated_changes == {"monats_offen": 1}
    await execute(p.plan_id, db)
    nachher = await _run(db, anlage)
    assert [x.schwere for x in nachher] == [CheckSeverity.OK.value], [x.meldung for x in nachher]


async def test_monate_vor_der_anschaffung_zaehlen_nicht(db):
    """Zwei Datums-Ebenen: gefragt ist „ab wann ist das Gerät dabei?"

    Ein Monat aus 2024 ohne Benzinpreis ist kein Mangel, wenn das E-Auto erst
    2025 angeschafft wurde — sonst fordert der Checker Preise für eine Zeit,
    in der es nichts zu vergleichen gab.
    """
    anlage = await _seed(db, mit_eauto=True, anschaffung=date(2025, 3, 10))
    await _add_monat(db, anlage.id, 2024, 11, preis=None)
    await _add_monat(db, anlage.id, 2025, 2, preis=None)
    await _add_monat(db, anlage.id, 2025, 4, preis=1.80)
    await db.commit()

    ergebnisse = await _run(db, anlage)
    assert len(ergebnisse) == 1
    assert ergebnisse[0].schwere == CheckSeverity.OK.value
