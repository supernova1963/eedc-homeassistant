"""Verbrauchsprofil: alle drei Quellen bündeln backward (N-43, #144/#297).

Das individuelle Verbrauchsprofil hat drei Quellen — EEDC-DB, HA-History und
MQTT-Snapshots. Der DB-Pfad erbt die Backward-Konvention aus
``TagesEnergieProfil.stunde`` (Slot ``h`` = Energie ``[h-1, h)``), die beiden
Fallbacks bündelten bis v4.0.5 **forward**: die Energie aus ``[h, h+1)`` landete
unter Index ``h``. Sichtbar wurde das nur bei frischer Installation und im
Standalone-Betrieb — dort liegt die gestrichelte Verbrauchsprognose im Live-Chart
sonst eine Stunde zu früh (dritte Fundstelle derselben Klasse nach #297 und
`b8d6f2f2`).

Zwei Sorten Test:
  1. **Regression je Pfad** — ein Verbrauch im Intervall ``[10:00, 11:00)``
     landet in **Slot 11**, die Tagessumme bleibt gleich.
  2. **Symmetrie** — dieselbe physische Wirklichkeit, durch alle drei Quellen
     gemessen, ergibt **dasselbe Profil**. Das ist der eigentliche Wert: heute
     lieferten drei Quellen desselben Sachverhalts zwei Ergebnisse.

Die Slot-Zuordnung wird hier bewusst **ausgeschrieben** (``slot = h + 1``) statt
aus dem SoT geholt — ein Pinning-Test, der die Konvention aus derselben Funktion
bezieht wie der Produktionscode, prüft nur noch sich selbst.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import date, datetime, time, timedelta

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.anlage import Anlage
from backend.models.mqtt_energy_snapshot import MqttEnergySnapshot
from backend.models.tages_energie_profil import TagesEnergieProfil
from backend.services import live_verbrauchsprofil_service as svc

pytestmark = pytest.mark.asyncio

TAGE = svc.TAGE_FENSTER  # 7 volle Tage, heute ausgenommen

BEZUG_EID = "sensor.netzbezug_w"


# ─── Physische Wirklichkeit ────────────────────────────────────────────────
#
# Alle Generatoren unten bekommen dieselbe Abbildung
# „Intervall-Beginn → Verbrauch in kW" und übersetzen sie in das Rohformat
# ihrer Quelle. Was sich unterscheiden darf, ist die Messart — nicht das
# Ergebnis.


def _erster_tag() -> date:
    return date.today() - timedelta(days=TAGE)


def _intervalle() -> list[datetime]:
    """Alle physischen Stundenintervall-Anfänge des Profil-Fensters.

    Beginnt um 23:00 des Vortags: dieses Intervall ist Slot 0 des ersten Tages.
    """
    start = datetime.combine(_erster_tag(), time()) - timedelta(hours=1)
    return [start + timedelta(hours=i) for i in range(TAGE * 24)]


def _slot(intervall_beginn: datetime) -> tuple[date, int]:
    """Backward-Slot eines Intervalls ``[t, t+1h)`` — ausgeschrieben.

    ``[10:00, 11:00)`` → Slot 11 desselben Tages,
    ``[23:00, 00:00)`` → Slot 0 des **Folgetags**.
    """
    stunde = intervall_beginn.hour + 1
    if stunde == 24:
        return intervall_beginn.date() + timedelta(days=1), 0
    return intervall_beginn.date(), stunde


async def _anlage(db: AsyncSession, mapping: dict) -> Anlage:
    anlage = Anlage(
        anlagenname="Slot-Konvention",
        leistung_kwp=10.0,
        standort_plz="10115",
        standort_land="DE",
        wechselrichter_hersteller="generic",
        sensor_mapping=mapping,
    )
    db.add(anlage)
    await db.flush()
    return anlage


# ─── Quelle 1: EEDC-DB ─────────────────────────────────────────────────────


async def _schreibe_db_profil(
    db: AsyncSession, anlage_id: int, verbrauch: dict[datetime, float]
) -> None:
    """TagesEnergieProfil-Zeilen — der Aggregator schreibt bereits Backward-Slots."""
    for beginn in _intervalle():
        datum, stunde = _slot(beginn)
        if datum >= date.today():
            continue  # heute ist unvollständig und wird nicht gelesen
        db.add(
            TagesEnergieProfil(
                anlage_id=anlage_id,
                datum=datum,
                stunde=stunde,
                verbrauch_kw=verbrauch.get(beginn, 0.0),
            )
        )
    await db.flush()


# ─── Quelle 2: HA-History (Leistungspunkte) ────────────────────────────────


def _ha_history(verbrauch: dict[datetime, float]) -> dict[str, list]:
    """Konstante Leistung über jedes Intervall, gemessen alle 15 Minuten."""
    punkte: list[tuple[datetime, float]] = []
    for beginn in _intervalle():
        watt = verbrauch.get(beginn, 0.0) * 1000
        for minute in (0, 15, 30, 45):
            punkte.append((beginn + timedelta(minutes=minute), watt))
    return {BEZUG_EID: punkte}


def _patche_ha(monkeypatch, history: dict[str, list]) -> None:
    async def _fake_history(entity_ids, start, end):
        gefiltert = {
            eid: [(ts, val) for ts, val in punkte if start <= ts <= end]
            for eid, punkte in history.items()
            if eid in entity_ids
        }
        return gefiltert, {}

    monkeypatch.setattr(svc, "HA_INTEGRATION_AVAILABLE", True)
    monkeypatch.setattr(svc, "get_history_normalized", _fake_history)


# ─── Quelle 3: MQTT-Snapshots (kumulativer Zähler) ─────────────────────────


async def _schreibe_mqtt_snapshots(
    db: AsyncSession, anlage_id: int, verbrauch: dict[datetime, float]
) -> None:
    """Kumulativer Netzbezugs-Zähler, alle 5 Minuten abgelegt.

    Der Zuwachs einer Stunde ist beim zweiten Snapshot vollständig da — sonst
    misst der Pfad (Delta erster→letzter Snapshot **innerhalb** der Stunde)
    systematisch das letzte Snapshot-Intervall nicht mit; das ist eine eigene
    Baustelle (Nebenfund N-45) und nicht die Zuordnungsfrage dieses Tests.
    """
    stand = 100.0
    for beginn in _intervalle():
        zuwachs = verbrauch.get(beginn, 0.0)
        for minute in range(0, 60, 5):
            db.add(
                MqttEnergySnapshot(
                    anlage_id=anlage_id,
                    timestamp=beginn + timedelta(minutes=minute),
                    energy_key="netzbezug_kwh",
                    value_kwh=stand if minute == 0 else stand + zuwachs,
                )
            )
        stand += zuwachs
    await db.flush()


@pytest_asyncio.fixture
def mqtt_session(monkeypatch, db: AsyncSession):
    """`_profil_from_mqtt` öffnet eine eigene Session — auf die Test-DB lenken."""

    @asynccontextmanager
    async def _fake_get_session():
        yield db

    monkeypatch.setattr("backend.core.database.get_session", _fake_get_session)
    return db


# ─── Testdaten ─────────────────────────────────────────────────────────────


def _nur_zehn_bis_elf() -> dict[datetime, float]:
    """1 kW ausschließlich im Intervall [10:00, 11:00), an jedem Tag."""
    return {b: 1.0 for b in _intervalle() if b.hour == 10}


def _tagesgang() -> dict[datetime, float]:
    """Ein voller Tagesgang, auf jedem Tag identisch (0,2 … 2,5 kW)."""
    return {b: round(0.2 + b.hour * 0.1, 3) for b in _intervalle()}


def _profil_teil(profil: dict, wochentag: date) -> dict[int, float]:
    schluessel = "wochenende" if wochentag.weekday() >= 5 else "werktag"
    return profil[schluessel]


# ─── 1. Regression je Pfad ─────────────────────────────────────────────────


async def test_ha_pfad_bündelt_backward(db: AsyncSession, monkeypatch):
    """HA-History: Verbrauch in [10:00, 11:00) → Slot 11, Tagessumme unverändert."""
    anlage = await _anlage(
        db, {"basis": {"live": {"netzbezug_w": BEZUG_EID}}}
    )
    _patche_ha(monkeypatch, _ha_history(_nur_zehn_bis_elf()))

    profil = await svc._profil_from_ha(anlage, db)

    assert profil is not None
    for teil in (profil["werktag"], profil["wochenende"]):
        assert teil[11] == 1.0, "Slot 11 trägt das Intervall [10:00, 11:00)"
        assert teil[10] == 0.0, "Slot 10 wäre die alte Forward-Bündelung"
        assert round(sum(teil.values()), 3) == 1.0, "nur die Zuordnung ändert sich"


async def test_mqtt_pfad_bündelt_backward(db: AsyncSession, mqtt_session):
    """MQTT-Snapshots: Zuwachs in [10:00, 11:00) → Slot 11, Tagessumme unverändert."""
    anlage = await _anlage(db, {})
    await _schreibe_mqtt_snapshots(db, anlage.id, _nur_zehn_bis_elf())

    profil = await svc._profil_from_mqtt(anlage.id)

    assert profil is not None
    for teil in (profil["werktag"], profil["wochenende"]):
        assert teil[11] == 1.0
        assert teil[10] == 0.0
        assert round(sum(teil.values()), 3) == 1.0


async def test_tagesgrenze_landet_im_slot_null_des_folgetags(
    db: AsyncSession, monkeypatch
):
    """[Vortag 23:00, 00:00) ist Slot 0 des Folgetags — und wird auch geholt.

    Das Fenster muss dafür eine Stunde vor Mitternacht des ersten Tages
    beginnen; sonst bliebe dessen Slot 0 dauerhaft leer.
    """
    erster_tag = _erster_tag()
    vorabend = datetime.combine(erster_tag, time()) - timedelta(hours=1)
    anlage = await _anlage(
        db, {"basis": {"live": {"netzbezug_w": BEZUG_EID}}}
    )
    _patche_ha(monkeypatch, _ha_history({vorabend: 2.0}))

    profil = await svc._profil_from_ha(anlage, db)

    assert profil is not None
    teil = _profil_teil(profil, erster_tag)
    # Der Vorabend-Verbrauch ist einer von mehreren Tagen in diesem Slot-Mittel;
    # entscheidend ist, dass er überhaupt ankommt — und nicht in Slot 23.
    assert teil[0] > 0.0, "Slot 0 des ersten Tages kommt vom Vorabend"
    assert teil[23] == 0.0


# ─── 2. Symmetrie über alle drei Quellen ───────────────────────────────────


async def test_drei_quellen_ein_profil(db: AsyncSession, monkeypatch, mqtt_session):
    """Gleiche Wirklichkeit, drei Messarten ⇒ ein Profil.

    Vorher lieferte der DB-Pfad ein um eine Stunde verschobenes Profil
    gegenüber HA und MQTT — je nachdem, welche Quelle greift, stand eine
    andere Kurve im Live-Chart.
    """
    verbrauch = _tagesgang()
    anlage = await _anlage(
        db, {"basis": {"live": {"netzbezug_w": BEZUG_EID}}}
    )
    await _schreibe_db_profil(db, anlage.id, verbrauch)
    await _schreibe_mqtt_snapshots(db, anlage.id, verbrauch)
    _patche_ha(monkeypatch, _ha_history(verbrauch))

    aus_db = await svc._profil_from_db(anlage.id, db)
    aus_ha = await svc._profil_from_ha(anlage, db)
    aus_mqtt = await svc._profil_from_mqtt(anlage.id)

    assert aus_db is not None and aus_ha is not None and aus_mqtt is not None
    for teil in ("werktag", "wochenende"):
        assert aus_ha[teil] == aus_db[teil], f"HA weicht vom DB-Kanon ab ({teil})"
        assert aus_mqtt[teil] == aus_db[teil], f"MQTT weicht vom DB-Kanon ab ({teil})"

    # Und die Zuordnung selbst: [10:00, 11:00) trägt 1,2 kW → Slot 11.
    assert aus_db["werktag"][11] == 1.2
    # Tagessumme = Summe des Tagesgangs, in jeder Quelle.
    erwartet = round(sum(round(0.2 + h * 0.1, 3) for h in range(24)), 3)
    for profil in (aus_db, aus_ha, aus_mqtt):
        assert round(sum(profil["werktag"].values()), 3) == erwartet
