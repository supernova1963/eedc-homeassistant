"""D3 — die vier Stellen außerhalb des Zähler-Moduls (B4 · B2b · E3 · N-64).

Jede Probe hält eine Meldung fest, die **vor** dem Bau falsch oder abwesend war.
Die Prämissen stehen als Kommentar dabei, weil sie am Code gemessen wurden und
eine spätere Sitzung sie sonst neu herleiten müsste.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from backend.models import Anlage, Investition
from backend.models.monatsdaten import Monatsdaten
from backend.models.tages_energie_profil import TagesZusammenfassung
from backend.services.daten_checker import DatenChecker
from backend.services.daten_checker.kategorien import CheckKategorie, CheckSeverity

_SENSOR = {"strategie": "sensor", "sensor_id": "sensor.gas"}


async def _geladen(db, anlage_id: int) -> Anlage:
    return (await db.execute(
        select(Anlage)
        .options(selectinload(Anlage.investitionen).selectinload(Investition.monatsdaten))
        .where(Anlage.id == anlage_id)
    )).scalar_one()


# ─── B4 / D3-b: ein Stand braucht keine Summen-Spalte ────────────────────────

class _FakeHaStats:
    is_available = True

    def __init__(self, fehlend=(), ohne_sum=()):
        self._fehlend, self._ohne_sum = set(fehlend), set(ohne_sum)

    def filter_summen_faehige_sensor_ids(self, sids):
        return (
            [s for s in sids if s not in self._fehlend and s not in self._ohne_sum],
            [s for s in sids if s in self._ohne_sum],
            [s for s in sids if s in self._fehlend],
        )


async def _anlage_mit_gassensor(db) -> Anlage:
    a = Anlage(anlagenname="Gas", leistung_kwp=10.0)
    db.add(a)
    await db.flush()
    inv = Investition(
        anlage_id=a.id, typ="sonstiges", bezeichnung="Gaszähler",
        anschaffungsdatum=date(2025, 1, 1), aktiv=True,
        parameter={"kategorie": "zaehler", "zaehler_art": "gas", "zaehler_einheit": "m³"},
    )
    db.add(inv)
    await db.flush()
    a.sensor_mapping = {
        "basis": {},
        "investitionen": {str(inv.id): {"felder": {"zaehlerstand": dict(_SENSOR)}}},
    }
    await db.flush()
    return await _geladen(db, a.id)


def _patch_ha(monkeypatch, fake):
    import backend.services.ha_statistics_service as ha_mod
    monkeypatch.setattr(ha_mod, "get_ha_statistics_service", lambda: fake)


@pytest.mark.asyncio
async def test_zaehlerstand_ohne_summen_spalte_ist_kein_befund(db, monkeypatch):
    """⛔ Die Falschmeldung, die D3 entfernt hat.

    **Prämisse, gemessen:** `zaehlerstand` steht in `KUMULATIVE_COUNTER_FELDER`
    (`snapshot/keys.py`) und lief deshalb durch den **Counter**-Zweig — der eine
    Summen-Spalte verlangt. Ein Stand braucht sie nicht: `get_value_at` liest
    ihn mit `als_stand=True` ausschließlich aus `state`
    (`_value_at_wert`, F-58). Ein Gaszähler mit `state_class: measurement`
    funktioniert vollständig und bekam trotzdem „Counter-Sensor ohne
    Summen-Spalte — Korrektur-Werkzeuge wirken nicht", samt eines Rats
    (Verbrauchszähler-Helfer), der für einen Zählerstand falsch ist.
    """
    anlage = await _anlage_mit_gassensor(db)
    _patch_ha(monkeypatch, _FakeHaStats(ohne_sum={"sensor.gas"}))

    erg = await DatenChecker(db)._check_sensor_mapping_lts(anlage)

    assert not [e for e in erg if e.schwere == CheckSeverity.WARNING], [
        e.meldung for e in erg
    ]
    ok = [e for e in erg if e.schwere == CheckSeverity.OK]
    assert len(ok) == 1 and "Zählerstand-Sensor" in ok[0].meldung, [e.meldung for e in erg]


@pytest.mark.asyncio
async def test_zaehlerstand_ohne_lts_eintrag_wird_gemeldet(db, monkeypatch):
    """Der „zweite, stille Fall" aus dem v4.0.25-CHANGELOG bleibt ein Befund.

    Ohne `statistics_meta`-Zeile liefert `get_value_at` gar nichts
    (`get_metadata` → None) — der Zähler bekommt überhaupt keinen Stand.
    """
    anlage = await _anlage_mit_gassensor(db)
    _patch_ha(monkeypatch, _FakeHaStats(fehlend={"sensor.gas"}))

    erg = await DatenChecker(db)._check_sensor_mapping_lts(anlage)

    warnungen = [e for e in erg if e.schwere == CheckSeverity.WARNING]
    assert len(warnungen) == 1, [e.meldung for e in erg]
    assert "Zählerstand-Sensor" in warnungen[0].meldung
    # Der Rat muss der richtige sein — nicht der Verbrauchszähler-Helfer.
    assert "nicht nötig" in warnungen[0].details
    assert "measurement" in warnungen[0].details


@pytest.mark.asyncio
async def test_wp_counter_behaelt_seine_summen_pruefung(db, monkeypatch):
    """Gegenprobe: der Stand-Zweig darf dem Counter-Zweig nichts wegnehmen,
    was dort richtig war. `wp_starts_anzahl` braucht die Summen-Spalte."""
    a = Anlage(anlagenname="WP", leistung_kwp=10.0)
    db.add(a)
    await db.flush()
    inv = Investition(
        anlage_id=a.id, typ="waermepumpe", bezeichnung="WP",
        anschaffungsdatum=date(2025, 1, 1), aktiv=True,
    )
    db.add(inv)
    await db.flush()
    a.sensor_mapping = {"basis": {}, "investitionen": {str(inv.id): {"felder": {
        "wp_starts_anzahl": {"strategie": "sensor", "sensor_id": "sensor.starts"},
    }}}}
    await db.flush()
    _patch_ha(monkeypatch, _FakeHaStats(ohne_sum={"sensor.starts"}))

    erg = await DatenChecker(db)._check_sensor_mapping_lts(await _geladen(db, a.id))
    warnungen = [e for e in erg if e.schwere == CheckSeverity.WARNING]
    assert len(warnungen) == 1, [e.meldung for e in erg]
    assert "Counter-Sensor" in warnungen[0].meldung


# ─── E3: kein erfundener ROI-Grund am Zähler ─────────────────────────────────

@pytest.mark.asyncio
async def test_zaehler_bekommt_keinen_roi_hinweis(db):
    """⛔ Gemessen vor dem Bau: „Gaszähler (sonstiges): Anschaffungskosten
    fehlen — Werden für ROI-Berechnung benötigt."

    `investitionen/dashboards.py` schließt den Zähler ausdrücklich aus der
    Wirtschaftlichkeit aus („ein Zähler wird ERFASST, nicht BEWERTET"). Ein
    Hinweis mit erfundenem Grund lässt sich nur durch eine Eingabe abstellen,
    die anschließend nirgends gelesen wird.
    """
    a = Anlage(
        anlagenname="Gas", leistung_kwp=10.0, installationsdatum=date(2025, 1, 1),
    )
    db.add(a)
    await db.flush()
    db.add(Investition(
        anlage_id=a.id, typ="sonstiges", bezeichnung="Gaszähler",
        anschaffungsdatum=date(2025, 1, 1), aktiv=True,
        anschaffungskosten_gesamt=None,
        parameter={"kategorie": "zaehler"},
    ))
    await db.flush()

    erg = DatenChecker(db)._check_investitionen(await _geladen(db, a.id), [])
    assert not [e for e in erg if "Anschaffungskosten" in e.meldung], [
        e.meldung for e in erg
    ]


@pytest.mark.asyncio
async def test_andere_typen_behalten_den_kosten_hinweis(db):
    """Gegenprobe — E3 darf nicht zum Blindmacher werden."""
    a = Anlage(
        anlagenname="PV", leistung_kwp=10.0, installationsdatum=date(2025, 1, 1),
    )
    db.add(a)
    await db.flush()
    db.add(Investition(
        anlage_id=a.id, typ="pv-module", bezeichnung="Dach Süd",
        anschaffungsdatum=date(2025, 1, 1), leistung_kwp=10.0,
        ausrichtung="sued", neigung_grad=30, anschaffungskosten_gesamt=None,
    ))
    await db.flush()

    erg = DatenChecker(db)._check_investitionen(await _geladen(db, a.id), [])
    assert [e for e in erg if "Anschaffungskosten" in e.meldung], [e.meldung for e in erg]


@pytest.mark.asyncio
async def test_zaehler_behaelt_die_anschaffungsdatums_pflicht(db):
    """Konzept #377 §8 Entscheid 2: das Datum bleibt Pflicht — es begrenzt den
    Zeitraum, in dem das Gerät zählt. Nur die ROI-Begründung war falsch."""
    a = Anlage(
        anlagenname="Gas", leistung_kwp=10.0, installationsdatum=date(2025, 1, 1),
    )
    db.add(a)
    await db.flush()
    db.add(Investition(
        anlage_id=a.id, typ="sonstiges", bezeichnung="Gaszähler",
        anschaffungsdatum=None, aktiv=True, parameter={"kategorie": "zaehler"},
    ))
    await db.flush()

    erg = DatenChecker(db)._check_investitionen(await _geladen(db, a.id), [])
    fehler = [e for e in erg if e.schwere == CheckSeverity.ERROR]
    assert [e for e in fehler if "Anschaffungsdatum" in e.meldung], [e.meldung for e in erg]


# ─── B2b / D3-c: Sonstiges steht im Nenner der Zähler-Abdeckung ──────────────

async def _anlage_mit_sonstiges(db, kategorie: str | None) -> Anlage:
    a = Anlage(anlagenname="S", leistung_kwp=10.0)
    db.add(a)
    await db.flush()
    inv = Investition(
        anlage_id=a.id, typ="sonstiges", bezeichnung="Sauna",
        anschaffungsdatum=date(2025, 1, 1), aktiv=True,
        parameter={"kategorie": kategorie} if kategorie else {},
    )
    db.add(inv)
    await db.flush()
    a.sensor_mapping = {
        "basis": {
            "einspeisung": {"strategie": "sensor", "sensor_id": "sensor.e"},
            "netzbezug": {"strategie": "sensor", "sensor_id": "sensor.n"},
        },
        "investitionen": {},
    }
    await db.flush()
    return await _geladen(db, a.id)


@pytest.mark.asyncio
async def test_sonstiges_verbraucher_ohne_zaehler_wird_gemeldet(db):
    """Vor D3 fiel der ganze Typ aus dieser Prüfung — er stand nicht einmal
    im Nenner von „N von M Komponenten ohne Abdeckung"."""
    anlage = await _anlage_mit_sonstiges(db, "verbraucher")

    erg = DatenChecker(db)._check_energieprofil_abdeckung(anlage, [])
    treffer = [
        e for e in erg
        if e.kategorie == CheckKategorie.ENERGIEPROFIL_ABDECKUNG
        and "ohne vollständige" in e.meldung
    ]
    assert len(treffer) == 1, [e.meldung for e in erg]
    assert "Sauna" in treffer[0].details


@pytest.mark.asyncio
async def test_sonstiges_erzeuger_ebenso(db):
    """Registry-getrieben heißt: alle Kategorien, nicht die eine gebaute."""
    anlage = await _anlage_mit_sonstiges(db, "erzeuger")

    erg = DatenChecker(db)._check_energieprofil_abdeckung(anlage, [])
    assert [e for e in erg if "ohne vollständige" in e.meldung], [e.meldung for e in erg]


@pytest.mark.asyncio
async def test_zaehler_bleibt_aus_der_energieprofil_abdeckung_heraus(db):
    """⛔ Der Punkt der Registry-Bindung, kein Versehen.

    `sonstiges_feld_reihenfolge("zaehler")` liefert `()` (#377) — ein Zählerstand
    trägt keinen `komponenten_kwh`-Beitrag und geht in kein Energieprofil ein.
    Ihn hier zu fordern hieße, einen Hinweis zu stellen, den nichts einlöst, mit
    einem Text, der für ihn nicht stimmt („Integral-Sensor aus der Leistung").
    Seine Quellenfrage stellt `_check_zaehlerstaende`.
    """
    anlage = await _anlage_mit_sonstiges(db, "zaehler")

    erg = DatenChecker(db)._check_energieprofil_abdeckung(anlage, [])
    assert not [e for e in erg if "ohne vollständige" in e.meldung], [
        e.meldung for e in erg
    ]


# ─── N-64 / D3-f: keine Phantom-Drift durch stillgelegte Komponenten ─────────

async def _anlage_mit_zwei_modulen(db, *, stillgelegt_ab: date | None) -> tuple[Anlage, int, int]:
    a = Anlage(anlagenname="PV", leistung_kwp=20.0)
    db.add(a)
    await db.flush()
    aktiv = Investition(
        anlage_id=a.id, typ="pv-module", bezeichnung="Dach Süd",
        anschaffungsdatum=date(2024, 1, 1), leistung_kwp=10.0, aktiv=True,
    )
    alt = Investition(
        anlage_id=a.id, typ="pv-module", bezeichnung="Dach Nord (alt)",
        anschaffungsdatum=date(2024, 1, 1), leistung_kwp=10.0, aktiv=True,
        stilllegungsdatum=stillgelegt_ab,
    )
    db.add_all([aktiv, alt])
    await db.flush()
    a.sensor_mapping = {"basis": {}, "investitionen": {
        str(aktiv.id): {"felder": {"pv_erzeugung_kwh": {"strategie": "sensor", "sensor_id": "sensor.sued"}}},
        str(alt.id): {"felder": {"pv_erzeugung_kwh": {"strategie": "sensor", "sensor_id": "sensor.nord"}}},
    }}
    # Der Schreiber der eedc-Seite (`aggregate_day`) filtert per `aktiv_am_tag`:
    # für das stillgelegte Modul steht in `komponenten_kwh` NICHTS.
    tag = date.today() - timedelta(days=2)
    db.add(TagesZusammenfassung(
        anlage_id=a.id, datum=tag, komponenten_kwh={f"pv_{aktiv.id}": 30.0},
    ))
    await db.flush()
    return a, aktiv.id, alt.id


def _patch_drift(monkeypatch, aktiv_id: int, alt_id: int):
    """`get_komponenten_tageskwh_lts` liest das Mapping und filtert NICHT selbst
    (gemessen, `lts_aggregator.py:227-300`) — genau deshalb muss der Aufrufer es
    tun. Das Doppel bildet dieses Verhalten nach: Es liefert einen Key je
    übergebener Investition."""
    import backend.services.ha_statistics_service as ha_mod
    import backend.services.snapshot.lts_aggregator as lts_mod

    monkeypatch.setattr(ha_mod, "get_ha_statistics_service",
                        lambda: type("F", (), {"is_available": True})())

    async def _fake(anlage, investitionen_by_id, datum):
        werte = {}
        for inv_id in investitionen_by_id:
            werte[f"pv_{inv_id}"] = 30.0 if int(inv_id) == aktiv_id else 25.0
        return werte

    monkeypatch.setattr(lts_mod, "get_komponenten_tageskwh_lts", _fake)


@pytest.mark.asyncio
async def test_stillgelegtes_modul_erzeugt_keine_phantom_drift(db, monkeypatch):
    """N-64 — der Kern.

    Das stillgelegte Modul stand auf der HA-Seite mit voller Tagesernte
    (25 kWh) und auf der eedc-Seite gar nicht: Drift 25 von 55 kWh, also
    ≥ 2 kWh **und** ≥ 5 % — Meldung samt „Tag reparieren". Der Knopf löst sie
    nicht auf, denn `aggregate_day` schreibt für diese Komponente nichts
    (N-57-Masche). Der Zwilling `_check_leere_tage_trotz_zaehler` hat den
    Tagesfilter seit v4.0.6.
    """
    gestern = date.today() - timedelta(days=30)
    a, aktiv_id, alt_id = await _anlage_mit_zwei_modulen(db, stillgelegt_ab=gestern)
    _patch_drift(monkeypatch, aktiv_id, alt_id)

    erg = await DatenChecker(db)._check_datenquelle_drift(await _geladen(db, a.id))

    # ⚠ Das Signal ist der **Reparatur-Knopf**, nicht die Schwere: die
    # Drift-Einträge sind INFO. Eine Probe auf `WARNING` wäre hier
    # gegenstandslos — sie bliebe auch ohne den Fix grün (Beweis-Familie).
    drift = [e for e in erg if e.action_kind == "reaggregate_day"]
    assert drift == [], [e.meldung for e in erg]
    assert len(erg) == 1 and erg[0].schwere == CheckSeverity.OK.value, [
        e.meldung for e in erg
    ]


@pytest.mark.asyncio
async def test_echte_drift_einer_aktiven_komponente_bleibt(db, monkeypatch):
    """Gegenprobe — der Filter darf kein Blindmacher werden.

    Beide Module aktiv, die gespeicherte Zeile kennt nur eines: das ist eine
    echte Lücke und muss gemeldet werden.
    """
    a, aktiv_id, alt_id = await _anlage_mit_zwei_modulen(db, stillgelegt_ab=None)
    _patch_drift(monkeypatch, aktiv_id, alt_id)

    erg = await DatenChecker(db)._check_datenquelle_drift(await _geladen(db, a.id))

    drift = [e for e in erg if e.action_kind == "reaggregate_day"]
    assert len(drift) == 1, [e.meldung for e in erg]
    assert "55.0" in drift[0].meldung, drift[0].meldung
