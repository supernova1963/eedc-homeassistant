"""N-346: Die Zähler-Abdeckungs-Meldungen nennen ihre teuerste Folge.

Melder OB73-gif (#395). Die Meldungen zählten als Folgen „Prognosen-IST,
Heatmap, Lernfaktor und Monatsberichte" auf — nicht den **bilanziellen
Hausverbrauch** und die daraus gebildete **Grundlast**. Wer das liest, hält den
fehlenden Zähler für entbehrlich, während seine Grundlast still zu niedrig steht.
Zusage Gernots im Schließ-Kommentar zu #395 (31.08.2026).

⚠ **Diese Datei prüft den TEXT, nicht die Rechnung** — und das ist Absicht.
Dass ein fehlender Batterie-Beitrag als 0 zählt, hält bereits
``test_stundenbilanz_sot.py::test_fehlende_batterie_zaehlt_als_null_das_ist_der_bestand``
fest. Eine zweite Verhaltensprobe daneben wäre der zweite Turm, den der
Daten-Checker an drei Stellen ausdrücklich meidet. Hier steht die andere Hälfte:
dass die Meldung sagt, was dort passiert.

⛔ **Die Bedingung gehört zur Aussage.** Nur **Speicher** und **PV-Erzeugung**
stehen in ``PV + Netzbezug − Einspeisung − Speicher``; Wärmepumpe, Wallbox und
E-Auto sind Teil des Hausverbrauchs, keine Bilanzgröße daneben (gemessen an
``snapshot/keys.py::_categorize_counter``). Ein Satz, der die Folge
**unbedingt** behauptet, wäre für die Mehrzahl der Fälle falsch — deshalb hält
der dritte Test die Bedingung fest und nicht nur das Reizwort.
"""

from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.models import Anlage, Investition
from backend.services.daten_checker import DatenChecker, CheckSeverity

_KOMPONENTEN_MELDUNG = "ohne vollständige kWh-Zähler-Abdeckung"
_BASIS_MELDUNG = "Kein Basis-Zähler für"


def _sensor(sid: str) -> dict:
    return {"strategie": "sensor", "sensor_id": sid}


async def _reload(db: AsyncSession, anlage_id: int) -> Anlage:
    return (await db.execute(
        select(Anlage).options(selectinload(Anlage.investitionen))
        .where(Anlage.id == anlage_id)
    )).scalar_one()


async def _seed(db: AsyncSession, *, mit_basis: bool) -> Anlage:
    """Anlage mit einem Speicher ohne Zähler — die Melder-Konstellation."""
    anlage = Anlage(anlagenname="N-346", leistung_kwp=10.0)
    db.add(anlage)
    await db.flush()

    speicher = Investition(
        anlage_id=anlage.id, typ="speicher", bezeichnung="Akku",
        anschaffungsdatum=date(2025, 1, 1), aktiv=True,
    )
    db.add(speicher)
    await db.flush()

    basis = {
        "einspeisung": _sensor("sensor.einspeisung"),
        "netzbezug": _sensor("sensor.netzbezug"),
    } if mit_basis else {}
    anlage.sensor_mapping = {"basis": basis, "investitionen": {}}
    await db.commit()
    return await _reload(db, anlage.id)


def _mit(ergebnisse, teil: str) -> list:
    return [
        r for r in ergebnisse
        if r.schwere == CheckSeverity.WARNING and teil in r.meldung
    ]


async def test_komponenten_meldung_nennt_hausverbrauch_und_grundlast(db):
    """Der Fund selbst: die Meldung über fehlende Komponenten-Zähler."""
    anlage = await _seed(db, mit_basis=True)

    ergebnisse = DatenChecker(db)._check_energieprofil_abdeckung(anlage)

    warnungen = _mit(ergebnisse, _KOMPONENTEN_MELDUNG)
    assert warnungen, (
        "Ein Speicher ohne beide Zähler muss gemeldet werden — sonst prüft "
        "dieser Test den falschen Zustand."
    )
    details = warnungen[0].details or ""
    for wort in ("Hausverbrauch", "Grundlast"):
        assert wort in details, (
            f"N-346: Die Meldung nennt „{wort}“ nicht. Wer nur "
            "„Prognosen-IST, Heatmap, Lernfaktor, Monatsberichte“ liest, hält "
            "den Zähler für entbehrlich — während seine Grundlast zu niedrig "
            f"steht. Fand:\n{details}"
        )


async def test_basis_meldung_nennt_die_grundlast_mit(db):
    """Die Schwester-Meldung drei Zeilen darüber trug dieselbe Lücke.

    Sie nannte den leeren Hausverbrauch, aber nicht, dass damit auch die
    Grundlast verschwindet — halbe Klasse repariert wäre keine.
    """
    anlage = await _seed(db, mit_basis=False)

    ergebnisse = DatenChecker(db)._check_energieprofil_abdeckung(anlage)

    warnungen = _mit(ergebnisse, _BASIS_MELDUNG)
    assert warnungen, "Ohne Basis-Zähler muss die Meldung kommen."
    details = warnungen[0].details or ""
    assert "Grundlast" in details, (
        "N-346: Fehlt der Basis-Zähler, bleibt der Hausverbrauch leer — und "
        f"damit auch die Grundlast. Der Satz sagt es nicht. Fand:\n{details}"
    )


async def test_die_folge_wird_an_die_bedingung_gebunden(db):
    """⛔ Die Gegenprobe: der Satz darf die Folge nicht UNBEDINGT behaupten.

    In ``PV + Netzbezug − Einspeisung − Speicher`` stehen nur zwei
    Komponententypen. Ein Satz ohne diese Bedingung wäre bei einer Wallbox oder
    Wärmepumpe ohne Zähler schlicht falsch — und genau so würde er beim
    „Kürzen“ entstehen. Deshalb hält diese Probe die Bedingung, nicht das Wort.
    """
    anlage = await _seed(db, mit_basis=True)

    ergebnisse = DatenChecker(db)._check_energieprofil_abdeckung(anlage)

    details = (_mit(ergebnisse, _KOMPONENTEN_MELDUNG)[0].details or "")
    assert "Speicher oder" in details and "PV-Erzeugung" in details, (
        "N-346: Die Folge muss an Speicher/PV gebunden bleiben. Wärmepumpe, "
        "Wallbox und E-Auto stehen nicht in der Bilanzformel — für sie wäre "
        f"die Aussage falsch. Fand:\n{details}"
    )
