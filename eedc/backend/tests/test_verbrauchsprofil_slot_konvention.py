"""Verbrauchsprofil: drei Quellen, eine Stunde, ein Profil (N-43/N-45/N-46).

Das individuelle Verbrauchsprofil hat drei Quellen — EEDC-DB, HA-History und
MQTT-Snapshots. Der DB-Pfad erbt die Backward-Konvention aus
``TagesEnergieProfil.stunde`` (Slot ``h`` = Energie ``[h-1, h)``), die beiden
Fallbacks bündelten bis v4.0.5 **forward**: die Energie aus ``[h, h+1)`` landete
unter Index ``h``. Sichtbar wurde das nur bei frischer Installation und im
Standalone-Betrieb — dort liegt die gestrichelte Verbrauchsprognose im Live-Chart
sonst eine Stunde zu früh (dritte Fundstelle derselben Klasse nach #297 und
`b8d6f2f2`).

Dieselben beiden Fallbacks rechneten die Stunde außerdem **falsch**, nicht nur
an der falschen Stelle:

* **N-45 (MQTT)** — der Zuwachs wurde zwischen dem ersten und dem letzten
  Snapshot *innerhalb* der Stunde gebildet. Das letzte Snapshot-Intervall fiel
  jede Stunde heraus: bei 5-Minuten-Takt rund 8 % zu wenig.
* **N-46 (HA)** — jede Stunde hängte eine Stichprobe an, auch wenn der Recorder
  in dieser Stunde nichts geliefert hatte. Aus *unbekannt* wurde *war nichts*,
  ein Tag ohne History drückte das Profil nach unten.

Zwei Sorten Test:
  1. **Regression je Pfad** — ein Verbrauch im Intervall ``[10:00, 11:00)``
     landet in **Slot 11**, die Tagessumme bleibt gleich; ein spät anfallender
     Zuwachs zählt voll; ein Tag ohne Daten senkt den Mittelwert nicht.
  2. **Symmetrie** — dieselbe physische Wirklichkeit, durch alle drei Quellen
     gemessen, ergibt **dasselbe Profil**. Das ist der eigentliche Wert: heute
     lieferten drei Quellen desselben Sachverhalts zwei Ergebnisse.

**Die Fixture ist der Kern.** Ein Symmetrietest deckt nur ab, was seine Fixture
variiert — die erste Fassung (v4.0.5) legte den Zuwachs früh in die Stunde und
gab jedem Tag Daten und war deshalb grün, obwohl N-45 und N-46 beide offen
waren. Sie variiert jetzt **beide** Achsen: Zuwachs am Stundenende
(``spaet=True``) und ein Tag ohne jede Messung (``ohne_tage``).

Die Slot-Zuordnung wird hier bewusst **ausgeschrieben** (``slot = h + 1``) statt
aus dem SoT geholt — ein Pinning-Test, der die Konvention aus derselben Funktion
bezieht wie der Produktionscode, prüft nur noch sich selbst.

Schwesterdatei zum selben Modul: ``test_verbrauchsprofil_abdeckung_n48.py`` — sie
prüft, dass das Ergebnis seine gemessene **Abdeckung** ausweist. Beide hängen
zusammen: weil eine unvollständige Stunde hier ausgelassen wird (N-45/N-46),
entsteht ein „Tag" aus einer einzigen Stunde, und genau das musste der Anwender
erfahren (N-48).
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


def _ausgelassener_werktag() -> date:
    """Ein Werktag des Fensters, an dem gar nichts gemessen wurde.

    Bewusst ein **Werktag**: von den sieben Fenstertagen sind fünf Werktage,
    aber nur zwei Wochenendtage. Ein ausgelassener Wochenendtag ließe
    ``_build_profil_result`` den Wochenend-Teil ganz weg (``tage < 2``) — der
    Symmetrievergleich hätte dann nichts mehr zu vergleichen und wäre grün,
    ohne etwas zu prüfen.
    """
    for i in range(TAGE):
        tag = _erster_tag() + timedelta(days=i)
        if tag.weekday() < 5:
            return tag
    raise AssertionError("sieben aufeinanderfolgende Tage ohne Werktag")


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


def _ha_history(
    verbrauch: dict[datetime, float], ohne_tage: tuple[date, ...] = ()
) -> dict[str, list]:
    """Konstante Leistung über jedes Intervall, gemessen alle 15 Minuten.

    ``ohne_tage`` lässt die Slots dieser Tage komplett aus — kein einziger
    Messpunkt, wie nach einem Recorder-Ausfall. Der Verbrauch **fand statt**,
    er wurde nur nicht aufgezeichnet; genau die Unterscheidung, die N-46 nicht
    machte.
    """
    ohne = set(ohne_tage)
    punkte: list[tuple[datetime, float]] = []
    for beginn in _intervalle():
        if _slot(beginn)[0] in ohne:
            continue
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

    # N-156: der HA-Weg hängt nicht mehr am Supervisor-Token, sondern an der
    # Erreichbarkeit des `HAStateService` — also wird der gefakt statt der
    # Umgebungs-Konstante.
    class _FakeHA:
        is_available = True

    monkeypatch.setattr(
        "backend.services.ha_state_service.get_ha_state_service",
        lambda: _FakeHA(),
    )
    monkeypatch.setattr(svc, "get_history_normalized", _fake_history)


# ─── Quelle 3: MQTT-Snapshots (kumulativer Zähler) ─────────────────────────


async def _schreibe_mqtt_snapshots(
    db: AsyncSession,
    anlage_id: int,
    verbrauch: dict[datetime, float],
    spaet: bool = False,
    ohne_tage: tuple[date, ...] = (),
) -> None:
    """Kumulativer Netzbezugs-Zähler, alle 5 Minuten abgelegt.

    ``spaet=False`` — der Zuwachs der Stunde steht schon beim zweiten Snapshot.
    ``spaet=True`` — er fällt erst im **letzten** 5-Minuten-Intervall an und ist
    darum erst am Snapshot der nächsten Stundengrenze abzulesen. Das ist die
    Achse, auf der N-45 zuschlug: wer nur die Snapshots *innerhalb* der Stunde
    ansieht, misst dann null.

    ``ohne_tage`` lässt die Snapshots dieser Tage aus. Der **Zähler läuft
    weiter** — nach der Lücke steht er auf dem korrekten Stand, nur die
    Ablesungen dazwischen fehlen.

    Am Ende steht ein Snapshot auf der letzten Stundengrenze: der Scheduler
    läuft weiter, und ohne diesen Randwert wäre die letzte Stunde
    berechtigterweise unvollständig.
    """
    ohne = set(ohne_tage)
    stand = 100.0
    intervalle = _intervalle()

    def snapshot(zeitpunkt: datetime, wert: float) -> None:
        db.add(
            MqttEnergySnapshot(
                anlage_id=anlage_id,
                timestamp=zeitpunkt,
                energy_key="netzbezug_kwh",
                value_kwh=wert,
            )
        )

    for beginn in intervalle:
        zuwachs = verbrauch.get(beginn, 0.0)
        if _slot(beginn)[0] not in ohne:
            for minute in range(0, 60, 5):
                sichtbar = stand if (spaet or minute == 0) else stand + zuwachs
                snapshot(beginn + timedelta(minutes=minute), sichtbar)
        stand += zuwachs

    snapshot(intervalle[-1] + timedelta(hours=1), stand)
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


def _tagesgang_in_slots() -> dict[int, float]:
    """Derselbe Tagesgang, in Backward-Slots gelesen: Slot ``h`` trägt Stunde ``h-1``."""
    return {h: round(0.2 + ((h - 1) % 24) * 0.1, 3) for h in range(24)}


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


# ─── 1b. Regression: die unvollständige Stunde ─────────────────────────────


async def test_mqtt_spaeter_zuwachs_zaehlt_voll(db: AsyncSession, mqtt_session):
    """MQTT: Zuwachs erst im letzten 5-Minuten-Intervall — zählt trotzdem voll (N-45).

    Vorher wurde das Delta zwischen dem ersten und dem letzten Snapshot
    *innerhalb* der Stunde gebildet; ein Zuwachs, der erst an der Stundengrenze
    sichtbar wird, ging komplett verloren. Im Alltag war das kein Totalausfall,
    sondern ein Dauerabschlag von rund 8 % — dem letzten Snapshot-Intervall.
    """
    anlage = await _anlage(db, {})
    await _schreibe_mqtt_snapshots(db, anlage.id, _nur_zehn_bis_elf(), spaet=True)

    profil = await svc._profil_from_mqtt(anlage.id)

    assert profil is not None
    for teil in (profil["werktag"], profil["wochenende"]):
        assert teil[11] == 1.0, "der späte Zuwachs gehört ganz in Slot 11"
        assert round(sum(teil.values()), 3) == 1.0


async def test_ha_tag_ohne_historie_senkt_das_profil_nicht(
    db: AsyncSession, monkeypatch
):
    """HA: ein Tag ohne Messpunkte liefert keine Stichprobe (N-46).

    Vorher hängte jede Stunde eine Stichprobe an — auch die des Ausfalltags,
    mit 0 kW. Bei fünf Werktagen im Fenster drückte ein einziger Ausfalltag
    jeden Werktags-Slot auf 4/5 des wahren Werts.
    """
    verbrauch = _tagesgang()
    luecke = _ausgelassener_werktag()
    anlage = await _anlage(db, {"basis": {"live": {"netzbezug_w": BEZUG_EID}}})
    _patche_ha(monkeypatch, _ha_history(verbrauch, ohne_tage=(luecke,)))

    profil = await svc._profil_from_ha(anlage, db)

    assert profil is not None
    assert profil["werktag"] == _tagesgang_in_slots()


async def test_mqtt_tag_ohne_snapshots_senkt_das_profil_nicht(
    db: AsyncSession, mqtt_session
):
    """MQTT: ein Tag ohne Zählerstände liefert keine Stichprobe (N-45/N-46).

    Der Zähler läuft während der Lücke weiter. Die Stunden ohne Randwert werden
    ausgelassen; die Stunden davor und danach behalten ihren vollen Betrag —
    der Nachholzuwachs darf **nicht** in die erste Stunde nach der Lücke
    rutschen.
    """
    verbrauch = _tagesgang()
    luecke = _ausgelassener_werktag()
    anlage = await _anlage(db, {})
    await _schreibe_mqtt_snapshots(db, anlage.id, verbrauch, ohne_tage=(luecke,))

    profil = await svc._profil_from_mqtt(anlage.id)

    assert profil is not None
    assert profil["werktag"] == _tagesgang_in_slots()


# ─── 2. Symmetrie über alle drei Quellen ───────────────────────────────────


async def test_drei_quellen_ein_profil(db: AsyncSession, monkeypatch, mqtt_session):
    """Gleiche Wirklichkeit, drei Messarten ⇒ ein Profil.

    Vorher lieferte der DB-Pfad ein um eine Stunde verschobenes Profil
    gegenüber HA und MQTT — je nachdem, welche Quelle greift, stand eine
    andere Kurve im Live-Chart.

    Die Fixture variiert beide Achsen, auf denen die erste Fassung dieses Tests
    blind war (s. Modul-Docstring): der MQTT-Zuwachs fällt **spät** in der
    Stunde an (N-45), und ein Werktag hat in der HA-History **keinen einzigen**
    Messpunkt (N-46). Der DB-Pfad bleibt der Kanon und kennt den Tag.
    """
    verbrauch = _tagesgang()
    luecke = _ausgelassener_werktag()
    anlage = await _anlage(
        db, {"basis": {"live": {"netzbezug_w": BEZUG_EID}}}
    )
    await _schreibe_db_profil(db, anlage.id, verbrauch)
    await _schreibe_mqtt_snapshots(db, anlage.id, verbrauch, spaet=True)
    _patche_ha(monkeypatch, _ha_history(verbrauch, ohne_tage=(luecke,)))

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
