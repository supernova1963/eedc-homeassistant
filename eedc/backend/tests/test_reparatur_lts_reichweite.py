"""
Die Tages-Reparatur reicht so weit zurück wie HA — nicht nur 10 Tage.

Forum simon42 #89667/72 (dietmar1968): der Daten-Checker meldete 39 Tage ohne
Werte zwischen dem 16.06. und dem 30.07. und bot für jeden einen Reparatur-Knopf
an. Die Werte lagen in der HA-Langzeitstatistik — von dort las der Checker sie ja,
um die Lücke überhaupt zu melden. Die Reparatur holte die nötige
Stunden-Leistungskurve aber aus der HA-**Historie**, und die reicht nur so weit
zurück, wie der Recorder aufhebt (Default 10 Tage). `aggregate_day` stieg deshalb
aus, BEVOR es die Zähler anfasste, und meldete „keine Live-/MQTT-Daten gefunden".

Zwei Zusicherungen, beide hier gewächtert:

1. Bleibt der reguläre Weg leer, versucht die Reparatur dieselbe LTS-Kurve, die
   der Vollbackfill benutzt — und schreibt damit den Tag.
2. Kann auch die nichts holen, nennt die Meldung den ZUSTAND (keine Zuordnung /
   HA nicht erreichbar / HA hat für den Tag nichts) statt zu raten. Ein
   Reparatur-Fehler ohne Grund schickt den Anwender auf eine Fehlersuche bei sich.
"""

from __future__ import annotations

from datetime import date
from unittest.mock import AsyncMock, patch

import pytest

from backend.models.anlage import Anlage
from backend.services.energie_profil.lts_tagesverlauf import LtsTagesverlauf, grund_text
from backend.services.repair_orchestrator import _reparatur_aggregat

DATUM = date(2026, 6, 20)  # weit außerhalb jeder Recorder-Aufbewahrung


class _FakeZusammenfassung:
    stunden_verfuegbar = 24


async def _anlage(db) -> Anlage:
    a = Anlage(anlagenname="Test", leistung_kwp=10.0, standort_land="DE")
    db.add(a)
    await db.commit()
    return a


@pytest.mark.asyncio
async def test_alttag_wird_ueber_lts_repariert(db):
    anlage = await _anlage(db)
    gesehen: list[dict | None] = []

    async def fake_aggregate_day(anlage_arg, datum_arg, db_arg, **kwargs):
        prefetched = kwargs.get("prefetched_tagesverlauf")
        gesehen.append(prefetched)
        # Ohne Kurve steigt der echte Aggregator aus — genau der Fall.
        return _FakeZusammenfassung() if prefetched else None

    kurve = {"serien": [{"key": "netz"}], "punkte": [{"zeit": "10:00", "werte": {"netz": 1.2}}]}

    with patch(
        "backend.services.energie_profil_service.aggregate_day",
        new=AsyncMock(side_effect=fake_aggregate_day),
    ), patch(
        "backend.services.energie_profil.lts_tagesverlauf.lade_tagesverlauf_aus_lts",
        new=AsyncMock(return_value=LtsTagesverlauf(tage={DATUM: kurve})),
    ):
        zusammenfassung, quelle = await _reparatur_aggregat(anlage, DATUM, db)

    assert zusammenfassung is not None
    assert quelle == "lts"
    # Erst ohne Kurve (regulärer Weg), dann mit — kein zweiter Schreibpfad,
    # derselbe `aggregate_day`.
    assert gesehen == [None, kurve]


@pytest.mark.asyncio
async def test_frischer_tag_nimmt_weiter_die_historie(db):
    """Der LTS-Weg ist ein Rückfall, keine Umleitung: klappt der reguläre Weg,
    wird die Langzeitstatistik gar nicht erst gefragt."""
    anlage = await _anlage(db)
    lts = AsyncMock(return_value=LtsTagesverlauf())

    with patch(
        "backend.services.energie_profil_service.aggregate_day",
        new=AsyncMock(return_value=_FakeZusammenfassung()),
    ), patch(
        "backend.services.energie_profil.lts_tagesverlauf.lade_tagesverlauf_aus_lts",
        new=lts,
    ):
        zusammenfassung, quelle = await _reparatur_aggregat(anlage, date.today(), db)

    assert zusammenfassung is not None
    assert quelle == "historie"
    lts.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "grund", ["keine_live_zuordnung", "ha_nicht_verfuegbar", "keine_daten"],
)
async def test_der_grund_wird_durchgereicht(db, grund):
    anlage = await _anlage(db)

    with patch(
        "backend.services.energie_profil_service.aggregate_day",
        new=AsyncMock(return_value=None),
    ), patch(
        "backend.services.energie_profil.lts_tagesverlauf.lade_tagesverlauf_aus_lts",
        new=AsyncMock(return_value=LtsTagesverlauf(grund=grund)),
    ):
        zusammenfassung, quelle = await _reparatur_aggregat(anlage, DATUM, db)

    assert zusammenfassung is None
    assert quelle == grund
    # Jeder Grund trägt einen Satz für den Anwender — sonst bliebe die Meldung
    # wieder beim Raten.
    assert grund_text(quelle)


@pytest.mark.asyncio
async def test_lts_kennt_den_tag_nicht(db):
    """HA hat für den Tag schlicht nichts — das ist keine Fehlfunktion, aber es
    muss als Datenlücke ankommen, nicht als Zuordnungsproblem."""
    anlage = await _anlage(db)

    with patch(
        "backend.services.energie_profil_service.aggregate_day",
        new=AsyncMock(return_value=None),
    ), patch(
        "backend.services.energie_profil.lts_tagesverlauf.lade_tagesverlauf_aus_lts",
        new=AsyncMock(return_value=LtsTagesverlauf(tage={date(2026, 6, 21): {}})),
    ):
        _, quelle = await _reparatur_aggregat(anlage, DATUM, db)

    assert quelle == "keine_daten"
