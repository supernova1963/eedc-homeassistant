"""F-39 (#384 azywietz-web): Der Zähler-Check kennt die BKW-Hierarchie.

Seit v4.0.18 darf ein `pv-module` Kind eines `balkonkraftwerk` sein (N-266) —
das BKW tritt seine Erzeugungsgrößen dann an die Kinder ab, und **gemessen wird
am Modul**. Die Abdeckungs-Prüfung wusste davon nichts und forderte weiter einen
`pv_erzeugung_kwh`-Zähler am BKW selbst: ein Hinweis, den der Anwender nicht
auflösen kann (P-6), gemeldet als #384.

⚠ Der zweite Test ist der wichtigere. Ein BKW **ohne** Modul-Kinder (nur
Speicher — seit v4.0.5 möglich) trägt seine Erzeugung weiter selbst. Ein Zweig
„Typ == balkonkraftwerk ⇒ überspringen" hätte aus der Falschmeldung eine
**Nullprüfung** gemacht — genau der Beinahe-Fehler aus F-33, dort noch rechtzeitig
gefangen. Deshalb läuft die Entscheidung über den SoT
`traegt_erzeugungsgroessen_selbst` und nicht über den Typ.

Der dritte Test hält die Zeitgrenze: Ein **stillgelegtes** Modul-Kind entlastet
sein BKW nicht — sonst stünde eine Anlage ohne jede Messung als gedeckt da.
"""

from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.models import Anlage, Investition
from backend.services.daten_checker import DatenChecker, CheckSeverity

_MELDUNG = "ohne vollständige kWh-Zähler-Abdeckung"


def _sensor(sid: str) -> dict:
    return {"strategie": "sensor", "sensor_id": sid}


def _basis() -> dict:
    return {
        "einspeisung": _sensor("sensor.einspeisung"),
        "netzbezug": _sensor("sensor.netzbezug"),
    }


async def _reload(db: AsyncSession, anlage_id: int) -> Anlage:
    return (await db.execute(
        select(Anlage).options(selectinload(Anlage.investitionen))
        .where(Anlage.id == anlage_id)
    )).scalar_one()


async def _seed(
    db: AsyncSession, *, mit_modul_kind: bool, kind_stillgelegt: bool = False,
) -> Anlage:
    """BKW ohne eigenen Sensor; das Modul-Kind trägt ihn — die #384-Konstellation."""
    anlage = Anlage(anlagenname="BKW-Hierarchie", leistung_kwp=2.0)
    db.add(anlage)
    await db.flush()

    bkw = Investition(
        anlage_id=anlage.id, typ="balkonkraftwerk", bezeichnung="Toni",
        anschaffungsdatum=date(2025, 3, 1), aktiv=True,
    )
    db.add(bkw)
    await db.flush()

    mapping = {"basis": _basis(), "investitionen": {}}
    if mit_modul_kind:
        modul = Investition(
            anlage_id=anlage.id, typ="pv-module", bezeichnung="4 × 500 Wp",
            leistung_kwp=2.0, anschaffungsdatum=date(2025, 3, 1), aktiv=True,
            parent_investition_id=bkw.id,
            stilllegungsdatum=date(2025, 6, 30) if kind_stillgelegt else None,
        )
        db.add(modul)
        await db.flush()
        if not kind_stillgelegt:
            mapping["investitionen"][str(modul.id)] = {
                "felder": {"pv_erzeugung_kwh": _sensor("sensor.energy_pv_gesamt")}
            }

    anlage.sensor_mapping = mapping
    await db.commit()
    return await _reload(db, anlage.id)


def _warnungen(ergebnisse) -> list:
    return [
        r for r in ergebnisse
        if r.schwere == CheckSeverity.WARNING and _MELDUNG in r.meldung
    ]


async def test_bkw_mit_modul_kind_wird_nicht_mehr_gefordert(db):
    """Der Melder-Fall: Sensor am Kind ⇒ das BKW braucht keinen eigenen."""
    anlage = await _seed(db, mit_modul_kind=True)

    ergebnisse = DatenChecker(db)._check_energieprofil_abdeckung(anlage)

    warnungen = _warnungen(ergebnisse)
    assert not warnungen, (
        "Das BKW hat seine Erzeugungsgrößen an das Modul abgetreten — ein "
        "eigener Zähler ist dort nicht zu haben, fand:\n"
        + "\n".join(f"  {w.meldung}: {w.details}" for w in warnungen)
    )
    ok = [r for r in ergebnisse if "über die zugeordneten PV-Module gedeckt" in r.meldung]
    assert ok, (
        "E1: eigene OK-Zeile erwartet — sie ist die einzige Stelle, an der der "
        "Anwender den Grund sieht. Fand:\n"
        + "\n".join(f"  {r.schwere.value}: {r.meldung}" for r in ergebnisse)
    )
    assert ok[0].meldung.startswith("1 Balkonkraftwerk"), ok[0].meldung


async def test_bkw_ohne_modul_kind_wird_weiter_gefordert(db):
    """Die F-33-Gegenprobe: ohne Kinder trägt das BKW seine Erzeugung selbst."""
    anlage = await _seed(db, mit_modul_kind=False)

    ergebnisse = DatenChecker(db)._check_energieprofil_abdeckung(anlage)

    warnungen = _warnungen(ergebnisse)
    assert warnungen, (
        "Ein BKW ohne Modul-Kinder misst selbst — fehlt der Zähler, muss das "
        "gemeldet werden. Aus der Falschmeldung darf keine Nullprüfung werden."
    )
    assert "Toni" in (warnungen[0].details or ""), warnungen[0].details


async def test_stillgelegtes_modul_kind_entlastet_nicht(db):
    """Die Zeitgrenze: die Abtretung gilt nur für heute aktive Kinder."""
    anlage = await _seed(db, mit_modul_kind=True, kind_stillgelegt=True)

    ergebnisse = DatenChecker(db)._check_energieprofil_abdeckung(anlage)

    warnungen = _warnungen(ergebnisse)
    assert warnungen, (
        "Das Modul-Kind ist stillgelegt und misst nichts mehr — dann steht das "
        "BKW wieder allein da und braucht einen eigenen Zähler."
    )
