"""Tests #150 Slice A — eedc-PV-Prognose-Export nach HA.

Rest-Ertrag heute + Tagesprognose Tag+1/2/3 + „Speicher voll um" (SoC-Sim ab
aktuellem Speicherstand). Reine Sim-Logik isoliert, Verdrahtung mit gemockten
Wetter-Quellen.
"""

from __future__ import annotations

from datetime import date, timedelta
from types import SimpleNamespace

import pytest

from backend.core.berechnungen.speicher_simulation import simuliere_speicher_tag
from backend.models import Anlage, Investition, Monatsdaten


# ── Speicher-Simulation (rein) ──────────────────────────────────────────────

def test_speicher_voll_um_aus_aktuellem_soc():
    # 10 kWh Speicher, Start 50 % (=5 kWh), 1 kWh Überschuss/h ab 10 Uhr.
    pv = [0.0] * 24
    for h in range(10, 16):
        pv[h] = 1.0
    sim = simuliere_speicher_tag(pv, [0.0] * 24, speicher_kap_kwh=10.0,
                                 start_soc_prozent=50.0, start_stunde=10)
    # 5 kWh fehlen bis voll → nach 5 h (Stunden 10..14) bei 100 % → "14:00".
    assert sim.speicher_voll_um == "14:00"
    assert sim.end_soc_prozent == pytest.approx(100.0)


def test_speicher_ohne_kapazitaet_keine_sim():
    sim = simuliere_speicher_tag([1.0] * 24, [0.0] * 24, speicher_kap_kwh=0.0,
                                 start_soc_prozent=50.0)
    assert sim.speicher_voll_um is None
    assert sim.soc_pro_stunde == {}


def test_speicher_start_stunde_ueberspringt_vergangenheit():
    # Überschuss am Vormittag wird ignoriert, wenn erst ab 14 Uhr simuliert wird.
    pv = [5.0] * 12 + [0.0] * 12
    sim = simuliere_speicher_tag(pv, [0.0] * 24, speicher_kap_kwh=10.0,
                                 start_soc_prozent=50.0, start_stunde=14)
    assert sim.speicher_voll_um is None
    assert min(sim.soc_pro_stunde) == 14


# ── Verdrahtung: calculate_anlage_sensors mit gemockten Quellen ─────────────

def _fake_solar_prognose(tageswerte):
    # Σ stunden_kw == pv_ertrag_kwh (gleiche Invariante wie der echte
    # solar_forecast_service: Tagessumme = Σ Stunden-Erträge).
    heute = date.today()
    tage = [
        SimpleNamespace(
            datum=(heute + timedelta(days=i)).isoformat(),
            pv_ertrag_kwh=val,
            stunden_kw=[val / 10 if 8 <= h < 18 else 0.0 for h in range(24)],
        )
        for i, val in enumerate(tageswerte)
    ]
    return SimpleNamespace(tageswerte=tage)


@pytest.fixture
def _patch_prognose(monkeypatch):
    import backend.services.solar_forecast_service as sfs
    import backend.api.routes.live_wetter as lw
    from backend.services.korrekturprofil_lookup import _cache

    async def fake_get_solar_prognose(**kwargs):
        return _fake_solar_prognose([20.0, 18.0, 15.0, 12.0])  # heute, +1, +2, +3

    async def fake_lernfaktor(anlage_id, db, quelle="openmeteo"):
        return 0.9

    monkeypatch.setattr(sfs, "get_solar_prognose", fake_get_solar_prognose)
    monkeypatch.setattr(lw, "_get_lernfaktor", fake_lernfaktor)
    # Kaskaden-Profil-Cache ist prozessweit (anlage_id-keyed) — Leaks aus
    # anderen Tests vermeiden; ohne Profile fällt jede Stunde auf den Skalar.
    _cache.clear()


async def _seed_pv_anlage(db, prognose_quelle="eedc") -> Anlage:
    anlage = Anlage(
        anlagenname="Prognose-Test",
        leistung_kwp=10.0,
        latitude=48.8,
        longitude=9.2,
        standort_land="DE",
        prognose_quelle=prognose_quelle,
    )
    db.add(anlage)
    await db.flush()
    db.add(Monatsdaten(anlage_id=anlage.id, jahr=2025, monat=1,
                       netzbezug_kwh=100.0, einspeisung_kwh=200.0))
    db.add(Investition(anlage_id=anlage.id, typ="pv-module", bezeichnung="Dach",
                       leistung_kwp=10.0, anschaffungsdatum=date(2024, 1, 1)))
    await db.flush()
    return anlage


async def test_prognose_sensoren_erscheinen(db, _patch_prognose):
    from backend.api.routes.ha_export import calculate_anlage_sensors

    anlage = await _seed_pv_anlage(db)
    sensors = await calculate_anlage_sensors(db, anlage)
    by_key = {sv.definition.key: sv for sv in sensors}

    # Tagesprognosen = Σ korrigierte Stunden-Slots; ohne Kaskaden-Profil
    # greift der Skalar-Fallback 0.9 → wie bisher pv_ertrag × 0.9
    # (Regressions-Erwartung: Anlagen OHNE Profil verhalten sich unverändert).
    assert by_key["eedc_prognose_day_plus_1_kwh"].value == pytest.approx(18.0 * 0.9, abs=0.05)
    assert by_key["eedc_prognose_day_plus_2_kwh"].value == pytest.approx(15.0 * 0.9, abs=0.05)
    assert by_key["eedc_prognose_day_plus_3_kwh"].value == pytest.approx(12.0 * 0.9, abs=0.05)
    assert "eedc_prognose_heute_kwh" in by_key
    assert "eedc_prognose_rest_today_kwh" in by_key
    # Rest ⊆ Tageswert: heute = IST bisher + Rest (Rainer-PN 2026-06-11).
    assert by_key["eedc_prognose_rest_today_kwh"].value <= by_key["eedc_prognose_heute_kwh"].value
    # Stundenprofile reisen als Attribut mit (kein eigenes Topic) — heute UND
    # Tag+1/2/3 (Geparkt-Trigger Kaskaden-Umzug, Gernot-Entscheid 2026-06-11).
    assert len(by_key["eedc_prognose_heute_kwh"].zusatz_attribute["stundenprofil_kwh"]) == 24
    for day_key in ("eedc_prognose_day_plus_1_kwh",
                    "eedc_prognose_day_plus_2_kwh",
                    "eedc_prognose_day_plus_3_kwh"):
        profil = by_key[day_key].zusatz_attribute["stundenprofil_kwh"]
        assert len(profil) == 24
        # Pflicht-Invariante: Sensor-State == Σ exportierte Stundenwerte.
        assert by_key[day_key].value == pytest.approx(sum(profil), abs=0.051)


async def test_prognose_export_oeffnet_keine_eigene_sitzung(db, _patch_prognose, monkeypatch):
    """CI-Rot nach v4.0.40 (05.09.2026): der Export lief über `get_session()` in die leere App-DB.

    `_profil_from_mqtt` öffnete — als einzige Funktion auf dem Anfragepfad — eine
    eigene Sitzung auf der App-Datenbank statt die übergebene zu nutzen. Solange nur
    die Live-Kachel sie rief, fiel das nie auf; #395 hängte sie in den Prognose-Export,
    und dessen Proben laufen gegen die Test-DB der Fixture. Auf dem CI-Runner ist die
    App-Datenbank leer (`no such table: mqtt_energy_snapshots`), der ganze Export fiel
    in sein `except` — **kein einziger Prognose-Sensor**. Lokal grün, weil `data/eedc.db`
    die Tabelle hat: ein Prüfer, den nur CI kennt.

    Die Probe stellt die CI-Lage her, ohne von einer Datei abzuhängen: Jede eigene
    Sitzung ist hier ein Fehler.
    """
    from backend.api.routes.ha_export import calculate_anlage_sensors
    import backend.core.database as database

    def _keine_eigene_sitzung():
        raise AssertionError("Anfragepfad darf keine eigene Sitzung öffnen — die übergebene `db` gilt")

    monkeypatch.setattr(database, "get_session", _keine_eigene_sitzung)
    # Der Profil-Cache ist prozessweit (anlage_id-keyed): Ohne Leeren traegt er das
    # Ergebnis der vorigen Probe derselben Datei, der MQTT-Pfad wird nie betreten —
    # und ein Sprengsatz bleibt stumm (gemessen 05.09.2026, erster Entwurf).
    from backend.services.live_power_service import get_live_power_service
    get_live_power_service()._kwh_cache._profil.clear()
    anlage = await _seed_pv_anlage(db)
    sensors = await calculate_anlage_sensors(db, anlage)
    by_key = {sv.definition.key: sv for sv in sensors}
    assert "eedc_prognose_day_plus_1_kwh" in by_key, (
        "Der Prognose-Export ist in sein `except` gefallen — irgendwo unter ihm wurde "
        "`get_session()` gerufen (die CI-Lage von v4.0.40)."
    )
    assert "eedc_prognose_rest_today_kwh" in by_key


async def test_rest_heute_ist_echter_rest(db, _patch_prognose, monkeypatch):
    """Prognose-Kanon „ein Wert überall": „heute" = kanonischer eedc-Tageswert
    (volle Tagesprognose, identisch mit Anzeige/Persistenz/Vergleich-eedc),
    „Rest heute" = NUR Σ verbleibende Stunden — beide aus demselben Kanon."""
    from datetime import datetime as real_datetime, time as dt_time
    import backend.services.prognose_kanon as kanon
    from backend.api.routes.ha_export import calculate_anlage_sensors

    class _FixedNoon(real_datetime):
        @classmethod
        def now(cls, tz=None):
            return real_datetime.combine(date.today(), dt_time(12, 0), tzinfo=tz)

    # „now" für rest_heute lebt jetzt im Kanon-Service.
    monkeypatch.setattr(kanon, "datetime", _FixedNoon)

    anlage = await _seed_pv_anlage(db)
    sensors = await calculate_anlage_sensors(db, anlage)
    by_key = {sv.definition.key: sv for sv in sensors}

    # Profil heute: 2.0 kWh in Stunden 8–17 (roh 20), Skalar 0.9 → 1.8/Slot,
    # Tageswert 18.0. „heute" = volle Tagesprognose = 18.0 (NEU: kanonischer
    # Wert, NICHT mehr IST+Rest). Um 12:00 sind die Rest-Slots 13..17 →
    # 5 × 1.8 = 9.0 kWh. Zur vollen Stunde (Minute 0) geht die laufende Stunde
    # vollständig ein, der #339-frac-Term ändert diesen Wert also nicht.
    assert by_key["eedc_prognose_rest_today_kwh"].value == pytest.approx(9.0, abs=0.05)
    assert by_key["eedc_prognose_heute_kwh"].value == pytest.approx(18.0, abs=0.05)


@pytest.mark.parametrize(
    "minute,erwartet",
    [
        (0, 9.0),    # laufende Stunde (Slot 13) voll: 1.8 + 4 × 1.8
        (30, 8.1),   # halbe Stunde verstrichen: 0.5 × 1.8 + 7.2
        (55, 7.4),   # 5 Minuten Rest: (5/60) × 1.8 + 7.2 = 7.35, auf 1 Dezimale gerundet
    ],
)
async def test_rest_heute_laufende_stunde_anteilig(db, _patch_prognose, monkeypatch, minute, erwartet):
    """#339: Der Rest sinkt innerhalb der Stunde gleichmäßig statt in EINEM Sprung.

    Backward-Konvention (#144): um 12:xx ist Slot 12 abgelaufen, Slot 13 die
    laufende Stunde. Rest = Restanteil von Slot 13 + Slots 14..17.
    """
    from datetime import datetime as real_datetime, time as dt_time
    import backend.services.prognose_kanon as kanon
    from backend.api.routes.ha_export import calculate_anlage_sensors

    class _Fixed(real_datetime):
        @classmethod
        def now(cls, tz=None):
            return real_datetime.combine(date.today(), dt_time(12, minute), tzinfo=tz)

    monkeypatch.setattr(kanon, "datetime", _Fixed)

    anlage = await _seed_pv_anlage(db)
    sensors = await calculate_anlage_sensors(db, anlage)
    by_key = {sv.definition.key: sv for sv in sensors}

    assert by_key["eedc_prognose_rest_today_kwh"].value == pytest.approx(erwartet, abs=0.05)
    # Die Tagesprognose bleibt davon unberührt — sie rollt nur mit OpenMeteo.
    assert by_key["eedc_prognose_heute_kwh"].value == pytest.approx(18.0, abs=0.05)


async def test_rest_heute_letzte_tagesstunde_ohne_indexfehler(db, _patch_prognose, monkeypatch):
    """23:xx: es gibt keinen Slot 24 mehr — der Rest ist 0, kein IndexError."""
    from datetime import datetime as real_datetime, time as dt_time
    import backend.services.prognose_kanon as kanon
    from backend.api.routes.ha_export import calculate_anlage_sensors

    class _FixedNacht(real_datetime):
        @classmethod
        def now(cls, tz=None):
            return real_datetime.combine(date.today(), dt_time(23, 40), tzinfo=tz)

    monkeypatch.setattr(kanon, "datetime", _FixedNacht)

    anlage = await _seed_pv_anlage(db)
    sensors = await calculate_anlage_sensors(db, anlage)
    by_key = {sv.definition.key: sv for sv in sensors}

    assert by_key["eedc_prognose_rest_today_kwh"].value == pytest.approx(0.0, abs=0.05)


async def test_quellen_regel_nur_eedc_kein_solcast_sfml(db, _patch_prognose):
    """Auch bei gewählter Solcast-Quelle exportiert eedc NUR eigene Prognose-Werte."""
    from backend.api.routes.ha_export import calculate_anlage_sensors

    anlage = await _seed_pv_anlage(db, prognose_quelle="solcast")
    sensors = await calculate_anlage_sensors(db, anlage)
    keys = {sv.definition.key for sv in sensors}

    assert any(k.startswith("eedc_prognose_") for k in keys)
    assert not any("solcast" in k or "sfml" in k for k in keys)


# ── N-392: „Speicher voll um" nennt seine Verbrauchsannahme ─────────────────

#: Ein fester Mittwoch — die Proben unten lesen KEINE Uhr (N-167): der Export
#: bekommt dieses Datum über `_fixiere_export_uhr` gestellt, das Seeding rechnet
#: gegen dieselbe Konstante. Derselbe Tag wie `_MITTWOCH` in test_395.
_N392_HEUTE = date(2026, 6, 17)


async def _seed_speicher_mit_soc(db, anlage, *, mit_historie: bool) -> None:
    """Ein 10-kWh-Speicher mit SoC 50 % in der Zeile `gestern, stunde 23` — seit
    V1 (22.09.2026) ist das der Backward-Slot 0 von heute: die Simulation
    startet bei Slot 0 mit Anteil 0,5 und rechnet den ganzen Tag, nicht ab der
    gestellten Uhr. Wahlweise dazu drei vollständige Tage desselben Wochentags
    in den letzten acht Wochen (die Kaskadenstufe „gleicher_wochentag" braucht
    MIN_TAGE_GLEICHER_WT = 3)."""
    from backend.models.tages_energie_profil import TagesEnergieProfil

    heute = _N392_HEUTE
    db.add(Investition(
        anlage_id=anlage.id, typ="speicher", bezeichnung="Akku",
        anschaffungsdatum=date(2024, 1, 1),
        parameter={"kapazitaet_kwh": 10.0, "wirkungsgrad_prozent": 100},
    ))
    if mit_historie:
        for wochen in (1, 2, 3):
            tag = heute - timedelta(weeks=wochen)
            for stunde in range(24):
                db.add(TagesEnergieProfil(
                    anlage_id=anlage.id, datum=tag, stunde=stunde, verbrauch_kw=0.5,
                ))
    db.add(TagesEnergieProfil(
        anlage_id=anlage.id, datum=heute - timedelta(days=1), stunde=23, soc_prozent=50.0,
    ))
    await db.flush()


def _fixiere_export_uhr(monkeypatch, stunde: int) -> None:
    """Stellt dem Export Datum UND Uhrzeit: `_N392_HEUTE` um `stunde`:00.

    Die Simulation startet bei `now.hour` — mit der echten Uhr wäre der Speicher
    abends nie mehr voll und der Sensor entfiele (N-167: vier von 24 Stunden rot).
    Das Datum wird mitgestellt, damit Seeding (Historie, gestriger SoC) und
    Prüfling denselben Tag meinen, ohne dass einer von beiden die Uhr liest.
    """
    from datetime import date as real_date, datetime as real_datetime, time as dt_time
    import backend.services.ha_export_prognose as hep

    class _FixedDate(real_date):
        @classmethod
        def today(cls):
            return _N392_HEUTE

    class _Fixed(real_datetime):
        @classmethod
        def now(cls, tz=None):
            return real_datetime.combine(_N392_HEUTE, dt_time(stunde, 0), tzinfo=tz)

    monkeypatch.setattr(hep, "date", _FixedDate)
    monkeypatch.setattr(hep, "datetime", _Fixed)


async def test_speicher_voll_um_nennt_seine_verbrauchsannahme(db, _patch_prognose, monkeypatch):
    """N-392: zwei Verbrauchsmodelle im selben Export — jeder Sensor sagt, welches.

    `eedc_verbrauchsprognose_heute_kwh` rechnet das 7-Tage-Profil der Live-Kachel,
    die Simulation hinter `eedc_speicher_voll_um` das gewichtete 8-Wochen-Profil.
    Bis 18.09.2026 trug nur der Nachbar seine Grundlage als Attribut; eine
    Automation, die beide verrechnet, mischte zwei Modelle, ohne dass ein
    Attribut es sagte. Der Punkt der Probe ist deshalb der letzte Vergleich:
    die beiden `profil_typ` sind verschieden.
    """
    from unittest.mock import AsyncMock, patch
    from backend.api.routes.ha_export import calculate_anlage_sensors
    from backend.services.verbrauch_prognose_service import HALBWERTSZEIT_TAGE

    _fixiere_export_uhr(monkeypatch, 8)
    anlage = await _seed_pv_anlage(db)
    await _seed_speicher_mit_soc(db, anlage, mit_historie=True)

    # Der Nachbar braucht ein individuelles Profil + Forecast (wie test_395).
    # Werktag UND Wochenende, damit er an jedem Tag des Laufs entsteht.
    profil = {h: 0.5 for h in range(24)}
    daten = {
        "werktag": profil, "tage_werktag": 7, "slots_werktag": 24,
        "wochenende": profil, "tage_wochenende": 2, "slots_wochenende": 24,
    }
    forecast = (
        {"hourly": {"time": [f"2026-06-17T{h:02d}:00" for h in range(24)],
                    "temperature_2m": [15.0] * 24}},
        None, True,
    )
    with patch(
        "backend.services.verbrauchsprognose_heute.get_live_power_service"
    ) as svc, patch(
        "backend.api.routes.live_wetter._lade_forecast_gecached",
        new=AsyncMock(return_value=forecast),
    ):
        svc.return_value.get_verbrauchsprofil = AsyncMock(return_value=daten)
        sensors = await calculate_anlage_sensors(db, anlage)
    by_key = {sv.definition.key: sv for sv in sensors}

    assert "eedc_speicher_voll_um" in by_key, "ab 8 Uhr mit 18 kWh PV wird ein 10-kWh-Speicher voll"
    z = by_key["eedc_speicher_voll_um"].zusatz_attribute
    assert z["profil_typ"] == "gewichtet_8_wochen"
    assert z["profil_wochen"] == 8
    assert z["profil_halbwertszeit_tage"] == HALBWERTSZEIT_TAGE
    assert z["profil_stufe"] == "gleicher_wochentag"
    assert z["profil_tage"] == 3
    # 24 h × 0,5 kW — die Σ genau der Liste, die die Simulation bekommen hat.
    assert z["verbrauch_annahme_kwh"] == pytest.approx(12.0)

    nachbar = by_key["eedc_verbrauchsprognose_heute_kwh"].zusatz_attribute
    assert nachbar["profil_typ"].startswith("individuell_")
    assert z["profil_typ"] != nachbar["profil_typ"], (
        "Zwei Sensoren, zwei Verbrauchsmodelle — und beide nennen dasselbe Profil? "
        "Dann kann eine Automation sie nicht mehr auseinanderhalten (N-392)."
    )


async def test_speicher_voll_um_ohne_profil_sagt_null_verbrauch(db, _patch_prognose, monkeypatch):
    """Ohne brauchbare Historie simuliert eedc mit 0 kWh Verbrauch — die Annahme
    mit der größten Überraschung, sie darf am wenigsten stumm bleiben."""
    from unittest.mock import AsyncMock, patch
    from backend.api.routes.ha_export import calculate_anlage_sensors

    _fixiere_export_uhr(monkeypatch, 8)
    anlage = await _seed_pv_anlage(db)
    await _seed_speicher_mit_soc(db, anlage, mit_historie=False)

    with patch(
        "backend.services.verbrauchsprognose_heute.get_live_power_service"
    ) as svc:
        svc.return_value.get_verbrauchsprofil = AsyncMock(return_value=None)
        sensors = await calculate_anlage_sensors(db, anlage)
    by_key = {sv.definition.key: sv for sv in sensors}

    z = by_key["eedc_speicher_voll_um"].zusatz_attribute
    assert z["profil_typ"] == "kein_profil"
    assert z["verbrauch_annahme_kwh"] == 0.0
    assert z["profil_stufe"] is None and z["profil_tage"] is None
    # N-332-Regel beim Nachbarn: ohne individuelles Profil kein Sensor.
    assert "eedc_verbrauchsprognose_heute_kwh" not in by_key
