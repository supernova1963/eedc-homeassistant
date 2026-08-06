"""Die leere Tagessicht nennt ihren Grund — und einen Knopf nur, wo er wirkt (F-2).

Cockpit/Tag zeigte für einen Tag ohne Werte **einen Satz ohne Grund und ohne
Weg**. Der Grund kommt jetzt aus dem Backend (`baue_tag_status`), nicht aus
einer Client-eigenen Ableitung — und er ist **tagesbezogen**: der Daten-Checker
beschreibt die Anlage (letzte Tageszeile, 90-Tage-Lücken) und beantwortet die
Frage nach *diesem* Tag nicht.

Der schärfste Punkt ist die Handlung: **nicht jeder Grund hat eine Reparatur.**
Liegt der Tag vor der Inbetriebnahme, fehlt die Zuordnung, hat HA selbst nichts
oder fehlt dem Tages-Lauf die Leistungs-Zuordnung, dann gibt es nichts
nachzuaggregieren — ein Knopf verspräche dort eine Wirkung, die es nicht gibt
(Gegenstück zu #368/P-8, wo genau das passiert war).

Ein fehlgeschlagener HA-Read darf **nicht** als „HA hat nichts" durchgehen
(B0/N-93-Klasse: aus einer Lücke wird still eine 0) — dafür die eigene Probe
unten. HA-Statistics und der LTS-Read werden gestellt, der Test läuft ohne HA
([[feedback_tests_ci_hermetisch]]).
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from backend.models import Anlage, Investition
from backend.models.tages_energie_profil import TagesEnergieProfil
from backend.services.energie_profil.tag_status import baue_tag_status

GESTERN = date.today() - timedelta(days=1)
VORGESTERN = date.today() - timedelta(days=2)


def _mapping(*, basis: bool = True) -> dict:
    if not basis:
        return {"basis": {}, "investitionen": {}}
    return {
        "basis": {
            "netzbezug": {"strategie": "sensor", "sensor_id": "sensor.netz"},
            "live": {"netz_leistung": {"sensor_id": "sensor.netz_w"}},
        },
        "investitionen": {},
    }


async def _anlage(
    db,
    *,
    mapping: dict | None = None,
    installation: date | None = None,
) -> Anlage:
    anlage = Anlage(
        anlagenname="TagStatus",
        leistung_kwp=10.0,
        installationsdatum=installation or date(2024, 1, 1),
        sensor_mapping=mapping if mapping is not None else _mapping(),
    )
    db.add(anlage)
    await db.flush()
    db.add(Investition(
        anlage_id=anlage.id, typ="pv-modul", bezeichnung="Dach Süd",
        anschaffungsdatum=date(2024, 1, 1), leistung_kwp=10.0,
    ))
    await db.flush()
    return anlage


def _patch_ha(monkeypatch, *, verfuegbar: bool, werte: dict | None = None, fehler=None):
    """Stellt HA-Statistics + den LTS-Tages-Read."""
    import backend.services.ha_statistics_service as ha_mod
    import backend.services.snapshot.lts_aggregator as lts_mod

    class _Svc:
        is_available = verfuegbar

    monkeypatch.setattr(ha_mod, "get_ha_statistics_service", lambda: _Svc())

    async def _read(_anlage, _invs, _datum):
        if fehler is not None:
            raise fehler
        return werte or {}

    monkeypatch.setattr(lts_mod, "get_komponenten_tageskwh_lts", _read)


@pytest.mark.asyncio
async def test_tag_mit_werten_meldet_keinen_grund(db, monkeypatch):
    """Gegenprobe: der Endpunkt erfindet keine Lücke, wo Zeilen stehen."""
    anlage = await _anlage(db)
    db.add(TagesEnergieProfil(
        anlage_id=anlage.id, datum=VORGESTERN, stunde=12, pv_kw=5.0,
    ))
    await db.flush()
    _patch_ha(monkeypatch, verfuegbar=True)

    status = await baue_tag_status(db, anlage, VORGESTERN)
    assert status.lage == "daten_vorhanden"
    assert status.aktion_kind is None


@pytest.mark.asyncio
async def test_tag_vor_inbetriebnahme_bekommt_keinen_knopf(db, monkeypatch):
    """Vor der Inbetriebnahme gibt es nichts nachzuaggregieren — Grund ja, Knopf nein."""
    anlage = await _anlage(db, installation=date(2025, 6, 1))
    _patch_ha(monkeypatch, verfuegbar=True, werte={"netzbezug": 30.0})

    status = await baue_tag_status(db, anlage, date(2025, 5, 20))
    assert status.lage == "vor_inbetriebnahme"
    assert "2025-06-01" in status.meldung
    assert status.aktion_kind is None


@pytest.mark.asyncio
async def test_ohne_zuordnung_kein_knopf_sondern_der_weg_zu_den_datenquellen(db, monkeypatch):
    """Ohne zugeordneten Zähler entsteht nie eine Zeile — auch rückwirkend nicht."""
    anlage = await _anlage(db, mapping=_mapping(basis=False))
    _patch_ha(monkeypatch, verfuegbar=True, werte={"netzbezug": 30.0})

    status = await baue_tag_status(db, anlage, VORGESTERN)
    assert status.lage == "keine_zuordnung"
    assert status.aktion_kind is None
    assert status.link == "/einstellungen/datenquellen"


@pytest.mark.asyncio
async def test_luecke_mit_ha_werten_bietet_die_tagesreparatur_an(db, monkeypatch):
    """Der einzige Fall, in dem der Knopf wirkt — und er nennt, was HA hat."""
    anlage = await _anlage(db)
    _patch_ha(monkeypatch, verfuegbar=True, werte={"netzbezug": 12.5})

    status = await baue_tag_status(db, anlage, VORGESTERN)
    assert status.lage == "luecke_reparierbar"
    assert status.aktion_kind == "reaggregate_day"
    assert "12.5 kWh" in (status.details or "")


@pytest.mark.asyncio
async def test_ha_ohne_werte_sagt_die_absage_offen(db, monkeypatch):
    """HA hat für den Tag selbst nichts — keine Fehlfunktion, kein Knopf."""
    anlage = await _anlage(db)
    _patch_ha(monkeypatch, verfuegbar=True, werte={})

    status = await baue_tag_status(db, anlage, VORGESTERN)
    assert status.lage == "ha_ohne_werte"
    assert status.aktion_kind is None


@pytest.mark.asyncio
async def test_unter_der_schwelle_zaehlt_nicht_als_holbarer_wert(db, monkeypatch):
    """Dieselbe Schwelle wie der Lücken-Check des Daten-Checkers (1 kWh) —
    sonst stünden zwei Sichten mit zwei Aussagen nebeneinander."""
    anlage = await _anlage(db)
    _patch_ha(monkeypatch, verfuegbar=True, werte={"netzbezug": 0.4})

    status = await baue_tag_status(db, anlage, VORGESTERN)
    assert status.lage == "ha_ohne_werte"


@pytest.mark.asyncio
async def test_fehlgeschlagener_ha_read_wird_nicht_zu_ha_hat_nichts(db, monkeypatch):
    """B0/N-93-Klasse: ein Netzfehler darf nicht als Tatsache ausgegeben werden."""
    anlage = await _anlage(db)
    _patch_ha(monkeypatch, verfuegbar=True, fehler=TimeoutError("HA weg"))

    status = await baue_tag_status(db, anlage, VORGESTERN)
    assert status.lage == "keine_ha_statistik"
    assert status.aktion_kind is None


@pytest.mark.asyncio
async def test_standalone_ohne_ha_nennt_den_grund_statt_zu_schweigen(db, monkeypatch):
    anlage = await _anlage(db)
    _patch_ha(monkeypatch, verfuegbar=False)

    status = await baue_tag_status(db, anlage, VORGESTERN)
    assert status.lage == "keine_ha_statistik"


@pytest.mark.asyncio
async def test_ohne_leistungszuordnung_steht_bewusst_kein_knopf(db, monkeypatch):
    """HA hat Werte, aber `aggregate_day` könnte sie nicht holen (#368-Linie).

    Zählerstand allein genügt dem Tages-Lauf nicht; ein Knopf liefe durch und
    schriebe nichts.
    """
    mapping = {
        "basis": {"netzbezug": {"strategie": "sensor", "sensor_id": "sensor.netz"}},
        "investitionen": {},
    }
    anlage = await _anlage(db, mapping=mapping)
    _patch_ha(monkeypatch, verfuegbar=True, werte={"netzbezug": 30.0})

    status = await baue_tag_status(db, anlage, VORGESTERN)
    assert status.lage == "luecke_ohne_reparaturweg"
    assert status.aktion_kind is None
    assert "Leistungs-Zuordnung" in (status.details or "")


@pytest.mark.asyncio
async def test_heute_und_zukunft_verweisen_nicht_auf_eine_reparatur(db, monkeypatch):
    """Der laufende Tag füllt sich von selbst; ein morgiger existiert nicht."""
    anlage = await _anlage(db)
    _patch_ha(monkeypatch, verfuegbar=True, werte={"netzbezug": 30.0})

    heute = await baue_tag_status(db, anlage, date.today())
    assert heute.lage == "laeuft_noch"
    assert heute.aktion_kind is None

    morgen = await baue_tag_status(db, anlage, date.today() + timedelta(days=1))
    assert morgen.lage == "zukunft"
    assert morgen.aktion_kind is None


@pytest.mark.asyncio
async def test_route_reicht_lage_und_aktion_durch(db, monkeypatch):
    """Der Endpunkt selbst — Schema-Verdrahtung, nicht nur der Service."""
    from backend.api.routes.energie_profil.views import get_tag_status

    anlage = await _anlage(db)
    _patch_ha(monkeypatch, verfuegbar=True, werte={"netzbezug": 12.5})

    antwort = await get_tag_status(anlage.id, VORGESTERN, db)
    assert antwort.datum == VORGESTERN
    assert antwort.lage == "luecke_reparierbar"
    assert antwort.aktion_kind == "reaggregate_day"
    assert antwort.aktion_label == "Tag nachrechnen"


@pytest.mark.asyncio
async def test_komponente_erst_ab_ihrem_anschaffungsdatum_versprochen(db, monkeypatch):
    """Tagesgenaue Erwartung (N-57): eine an dem Tag noch nicht angeschaffte
    Komponente verspricht nichts — sonst meldete die Sicht eine Lücke, die der
    Lauf nicht einlösen kann."""
    mapping = {
        "basis": {},
        "investitionen": {},
    }
    anlage = await _anlage(db, mapping=mapping)
    inv = Investition(
        anlage_id=anlage.id, typ="waermepumpe", bezeichnung="WP",
        anschaffungsdatum=date.today(),
    )
    db.add(inv)
    await db.flush()
    anlage.sensor_mapping = {
        "basis": {},
        "investitionen": {
            str(inv.id): {"felder": {
                "verbrauch_kwh": {"strategie": "sensor", "sensor_id": "sensor.wp"},
            }},
        },
    }
    await db.flush()
    _patch_ha(monkeypatch, verfuegbar=True, werte={f"waermepumpe_{inv.id}": 9.0})

    status = await baue_tag_status(db, anlage, VORGESTERN)
    assert status.lage == "keine_zuordnung"
