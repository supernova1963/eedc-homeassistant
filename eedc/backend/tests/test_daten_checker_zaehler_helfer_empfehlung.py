"""
Akzeptanztest: der Daten-Checker empfiehlt den Helfer-Weg, nicht die YAML.

Antwort-Kanon seit 2026-07-30 (Rainer-PN 90057): wer einen brauchbaren
kWh-Zähler für eedc braucht, legt in Home Assistant einen **Verbrauchszähler-
Helfer über die Oberfläche** an — **ohne Zyklus**. Bis v4.0.5 riet der
LTS-Check an drei Stellen zuerst zu `configuration.yaml`/`customize`; die YAML
ist für viele Anwender eine Fremdsprache, und ein Monatsreset trifft genau den
Snapshot-Pfad (rohe Zählerdifferenzen mit Tageszähler-Heuristik). Die **vierte**
Meldung derselben Prüfung (Counter ohne Summen-Spalte) nannte gar keinen Weg —
nachgezogen im Doku-Durchgang vor v4.0.6 (N-53).

Zwei Aussagen gehören laut Kanon in jeden solchen Text und werden hier
gewächtert: **ohne Zyklus** und **die Historie beginnt bei null** (HA sammelt
Vergangenes nicht nach). Die YAML darf nur noch als Nebensatz vorkommen.
"""

from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.models import Anlage, Investition  # noqa: F401
from backend.services.daten_checker import CheckSeverity


class _FakeHaStats:
    """HA-LTS-Doppel: jeder Sensor ist vorhanden, ohne Summe oder fehlend."""

    is_available = True

    def __init__(self, fehlend: set[str] | None = None, ohne_sum: set[str] | None = None):
        self._fehlend = fehlend or set()
        self._ohne_sum = ohne_sum or set()

    def filter_summen_faehige_sensor_ids(self, sids):
        mit_sum = [s for s in sids if s not in self._fehlend and s not in self._ohne_sum]
        return mit_sum, [s for s in sids if s in self._ohne_sum], [s for s in sids if s in self._fehlend]


async def _seed(db: AsyncSession, *, mit_counter: bool = False) -> Anlage:
    anlage = Anlage(anlagenname="Test", leistung_kwp=10.0)
    db.add(anlage)
    await db.flush()
    db.add(Investition(
        anlage_id=anlage.id,
        typ="waermepumpe" if mit_counter else "pv-module",
        bezeichnung="WP" if mit_counter else "WR Süd",
        leistung_kwp=10.0, anschaffungsdatum=date(2024, 1, 1), aktiv=True,
    ))
    await db.flush()
    inv_id = (await db.execute(select(Investition))).scalars().first().id
    felder = (
        {"wp_starts_anzahl": {"strategie": "sensor", "sensor_id": "sensor.wp_starts"}}
        if mit_counter
        else {"pv_erzeugung_kwh": {"strategie": "sensor", "sensor_id": "sensor.pv"}}
    )
    anlage.sensor_mapping = {
        "basis": {
            "einspeisung": {"strategie": "sensor", "sensor_id": "sensor.e_out"},
            "netzbezug": {"strategie": "sensor", "sensor_id": "sensor.e_in"},
        },
        "investitionen": {str(inv_id): {"felder": felder}},
    }
    await db.commit()
    return (await db.execute(
        select(Anlage).options(selectinload(Anlage.investitionen)).where(Anlage.id == anlage.id)
    )).scalar_one()


def _patch(monkeypatch, fake):
    import backend.services.ha_statistics_service as ha_mod
    monkeypatch.setattr(ha_mod, "get_ha_statistics_service", lambda: fake)


def _pruefe_kanon(details: str) -> None:
    """Die drei Pflichtaussagen des Kanons — und die YAML nur als Nebensatz."""
    assert "Verbrauchszähler" in details
    assert "Helfer" in details
    assert "ohne Zyklus" in details
    assert "beginnt bei null" in details
    # Der Helfer steht VOR der YAML — sonst liest sich der Nebensatz als Weg.
    if "customize" in details:
        assert details.index("Verbrauchszähler") < details.index("customize")
    assert "configuration.yaml" not in details


async def test_fehlender_kwh_zaehler_empfiehlt_den_helfer(db, monkeypatch):
    """kWh-Sensor ohne state_class: erster Rat ist der Helfer über die GUI."""
    from backend.services.daten_checker import DatenChecker

    anlage = await _seed(db)
    _patch(monkeypatch, _FakeHaStats(fehlend={"sensor.e_out"}))

    ergebnisse = await DatenChecker(db)._check_sensor_mapping_lts(anlage)

    warnungen = [r for r in ergebnisse if r.schwere == CheckSeverity.WARNING]
    assert len(warnungen) == 1, [r.meldung for r in ergebnisse]
    _pruefe_kanon(warnungen[0].details or "")


async def test_counter_ohne_state_class_empfiehlt_den_helfer(db, monkeypatch):
    """Counter-Sensor ohne state_class: derselbe Weg, derselbe Wortlaut-Kanon."""
    from backend.services.daten_checker import DatenChecker

    anlage = await _seed(db, mit_counter=True)
    _patch(monkeypatch, _FakeHaStats(fehlend={"sensor.wp_starts"}))

    ergebnisse = await DatenChecker(db)._check_sensor_mapping_lts(anlage)

    warnungen = [r for r in ergebnisse if r.schwere == CheckSeverity.WARNING]
    assert len(warnungen) == 1, [r.meldung for r in ergebnisse]
    _pruefe_kanon(warnungen[0].details or "")


async def test_counter_ohne_summen_spalte_empfiehlt_den_helfer(db, monkeypatch):
    """Die vierte Meldung derselben Prüfung nannte gar keinen Weg (N-53).

    Sie sagte nur „Empfohlen: `state_class: total_increasing` setzen" — wer
    sie las, wusste hinterher *was*, aber nicht *wie*. Jetzt derselbe Kanon
    wie die drei anderen.
    """
    from backend.services.daten_checker import DatenChecker

    anlage = await _seed(db, mit_counter=True)
    _patch(monkeypatch, _FakeHaStats(ohne_sum={"sensor.wp_starts"}))

    ergebnisse = await DatenChecker(db)._check_sensor_mapping_lts(anlage)

    warnungen = [r for r in ergebnisse if r.schwere == CheckSeverity.WARNING]
    assert len(warnungen) == 1, [r.meldung for r in ergebnisse]
    details = warnungen[0].details or ""
    _pruefe_kanon(details)
    # Der bisherige Handgriff bleibt lesbar — nur nicht mehr als einziger.
    assert "total_increasing" in details


async def test_zaehler_ohne_summen_spalte_empfiehlt_den_helfer(db, monkeypatch):
    """`measurement` statt `total_increasing`: Helfer zuerst, YAML im Nebensatz."""
    from backend.services.daten_checker import DatenChecker

    anlage = await _seed(db)
    _patch(monkeypatch, _FakeHaStats(ohne_sum={"sensor.e_out", "sensor.e_in"}))

    ergebnisse = await DatenChecker(db)._check_sensor_mapping_lts(anlage)

    warnungen = [r for r in ergebnisse if r.schwere == CheckSeverity.WARNING]
    assert len(warnungen) == 1, [r.meldung for r in ergebnisse]
    details = warnungen[0].details or ""
    _pruefe_kanon(details)
    # Der bisherige Handgriff bleibt lesbar (Regression zu #89667/44).
    assert "total_increasing" in details
