"""N-400 — die MQTT-Tages-kWh lesen über die ÜBERGEBENE Sitzung.

**Der Befund.** `mqtt_energy_history_service.get_tages_kwh` und seine beiden
Snapshot-Helfer `_get_closest_snapshot`/`_get_earliest_snapshot_after` öffneten
je ein eigenes `async with get_session()` auf der App-Datenbank — obwohl ihr
einziger Aufrufer, `live_history_service.safe_get_tages_kwh`, seine Sitzung von
`Depends(get_db)` an durchreicht (Cockpit → Live, zweimal je Abruf: heute und
gestern).

⛔ **Das ist Wort für Wort die Lage, die nach v4.0.40 den Tests-Workflow rot
gemacht hat** (N-399, `cb216e8a`): die zweite Verbindung geht auf die
*App*-Datenbank, nicht auf die Fixture-DB. Lokal grün, weil `data/eedc.db` die
Tabelle hat; auf dem CI-Runner `no such table: mqtt_energy_snapshots`. Produktiv
war es keine falsche Zahl, nur eine zweite SQLite-Verbindung im Anfragepfad.

⭐ **Warum es hier besonders leise gewesen wäre.** Der MQTT-Zweig in
`safe_get_tages_kwh` steht in einem `except Exception`, das jeden Fehler zu
einem `logger.debug` und einem leeren Ergebnis macht. Ein Programmierfehler auf
diesem Weg erzeugt keine Meldung, sondern eine fehlende Kachel.

⚠ **Vor diesen Proben war der Weg vollständig ungedeckt** — gemessen am
13.09.2026 mit einer Sonde in beiden Helfern über den ganzen Baum: **keiner der
4988 Fälle** betrat sie. Die Sonde musste dafür eine `BaseException` sein; eine
`AssertionError` hätte das `except Exception` oben geschluckt und die Messung
wäre still und wertlos geblieben. Der Register-Satz „in CI nicht rot, weil die
Proben `get_session` patchen" traf die Sache nicht: es gab keine Probe. Ein
solcher Patch hätte dieses Modul auch gar nicht erreicht — es importiert
`get_session` auf **Modulebene**, anders als `_profil_from_mqtt` vor N-399.

⚠ **Gestellte Uhr, keine echte.** `get_tages_kwh` bildet sein Fenster aus
`datetime.now()`. Die Proben stellen die Uhr des Moduls, damit sie nicht von der
Stunde ihres Laufs abhängen (die Snapshots sind naiv gespeichert, die
Prozesszone spielt damit keine Rolle — Berlin, UTC und Auckland sehen dasselbe).
"""

from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace

import pytest

import backend.services.ha_state_service as ha_state_service
import backend.services.live_history_service as lhs
import backend.services.mqtt_energy_history_service as svc
from backend.models.anlage import Anlage
from backend.models.mqtt_energy_snapshot import MqttEnergySnapshot
from backend.tests import factories as f

#: Ein Dienstag ohne Zeitumstellung in der Nähe. Alles Weitere hängt daran.
JETZT = datetime(2026, 3, 10, 14, 30)
HEUTE_MITTERNACHT = datetime(2026, 3, 10, 0, 0)
GESTERN_MITTERNACHT = datetime(2026, 3, 9, 0, 0)

#: Die Zählerstände der Fixture. Erste Spalte gestern 00:00, zweite heute 00:00,
#: dritte der aktuelle Cache-Wert. Die erwarteten Mengen stehen in den Proben
#: als Einzelwerte, nicht als nachgebildeter Ausdruck.
STAENDE: dict[str, tuple[float, float, float]] = {
    "pv_gesamt_kwh": (1000.0, 1032.5, 1050.0),
    "einspeisung_kwh": (400.0, 418.0, 425.0),
    "netzbezug_kwh": (200.0, 203.4, 205.0),
    "inv/7/pv_erzeugung_kwh": (600.0, 619.5, 630.0),
}


class _GestellteUhr(datetime):
    """`datetime` mit fester Gegenwart — der Rest der Klasse bleibt echt."""

    @classmethod
    def now(cls, tz=None):  # noqa: ARG003
        return JETZT


class _Cache:
    """Der Tages-kWh-Cache von `safe_get_tages_kwh`, leer und mitschreibend."""

    def __init__(self):
        self.werte: dict[str, dict] = {}

    def get_heute(self, _id):
        return self.werte.get("heute")

    def get_gestern(self, _id):
        return self.werte.get("gestern")

    def set_heute(self, _id, wert):
        self.werte["heute"] = wert

    def set_gestern(self, _id, wert):
        self.werte["gestern"] = wert


async def _anlage_mit_snapshots(db, *, zeitpunkte: dict[datetime, int]) -> Anlage:
    """Anlage mit MqttEnergySnapshot-Zeilen, wie der Cache-Schreiber sie anlegt.

    Args:
        zeitpunkte: ``{timestamp: spalten_index in STAENDE}``.
    """
    anlage = await f.anlage(db, anlagenname="Standalone MQTT")
    await db.commit()
    for ts, spalte in zeitpunkte.items():
        for key, werte in STAENDE.items():
            db.add(MqttEnergySnapshot(
                anlage_id=anlage.id, timestamp=ts,
                energy_key=key, value_kwh=werte[spalte],
            ))
    await db.commit()
    return anlage


def _mqtt_cache_auf(monkeypatch, spalte: int) -> None:
    """Den MQTT-Inbound-Cache auf eine Spalte aus `STAENDE` stellen."""
    stand = {key: werte[spalte] for key, werte in STAENDE.items()}
    monkeypatch.setattr(
        svc, "get_mqtt_inbound_service",
        lambda: SimpleNamespace(cache=SimpleNamespace(
            get_energy_data=lambda _anlage_id: stand,
        )),
    )


# ─────────────────────────────────────────────────────────────────────────
# K1 — dieselben Zahlen, jetzt aus der übergebenen Sitzung
# ─────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_gestern_kwh_aus_der_uebergebenen_sitzung(db, monkeypatch):
    """Zwei Mitternachts-Stände, ein Tag dazwischen — Einzelwerte an der Route.

    Die Zahlen sind dieselben wie vor dem Umbau; gemessen wurde vorher gegen
    dieselbe Fixture mit einem `get_session`, das die Test-DB lieferte.
    """
    monkeypatch.setattr(svc, "datetime", _GestellteUhr)
    anlage = await _anlage_mit_snapshots(db, zeitpunkte={
        GESTERN_MITTERNACHT: 0, HEUTE_MITTERNACHT: 1,
    })

    ergebnis = await svc.get_tages_kwh(
        anlage.id, db, 1, inv_types={"7": "pv-module"},
    )

    assert ergebnis["einspeisung"] == 18.0
    assert ergebnis["netzbezug"] == 3.4
    assert ergebnis["pv_7"] == 19.5
    # N-172: die je Erzeuger GEMESSENE Summe gewinnt gegen das Anlagen-Topic
    # (dessen Delta wäre 32,5). Unverändert — hier wird nur die Sitzung getauscht.
    assert ergebnis["pv"] == 19.5


@pytest.mark.asyncio
async def test_heute_kwh_aus_der_uebergebenen_sitzung(db, monkeypatch):
    """Heute = aktueller Cache-Stand minus Mitternachts-Snapshot."""
    monkeypatch.setattr(svc, "datetime", _GestellteUhr)
    _mqtt_cache_auf(monkeypatch, 2)
    anlage = await _anlage_mit_snapshots(db, zeitpunkte={HEUTE_MITTERNACHT: 1})

    ergebnis = await svc.get_tages_kwh(
        anlage.id, db, 0, inv_types={"7": "pv-module"},
    )

    assert ergebnis["einspeisung"] == 7.0
    assert ergebnis["netzbezug"] == 1.6
    assert ergebnis["pv_7"] == 10.5
    assert ergebnis["pv"] == 10.5


@pytest.mark.asyncio
async def test_erster_tag_faellt_auf_den_fruehesten_snapshot_zurueck(db, monkeypatch):
    """Der zweite Helfer: kein Mitternachts-Snapshot, also der früheste von heute.

    Das ist der erste Tag nach der Einrichtung. Ohne diese Probe bliebe
    `_get_earliest_snapshot_after` ungedeckt — und ein Sprengsatz dort stumm.
    """
    monkeypatch.setattr(svc, "datetime", _GestellteUhr)
    _mqtt_cache_auf(monkeypatch, 2)
    # 06:00 liegt weit außerhalb des ±10-Minuten-Fensters um Mitternacht.
    anlage = await _anlage_mit_snapshots(db, zeitpunkte={
        datetime(2026, 3, 10, 6, 0): 1,
    })

    ergebnis = await svc.get_tages_kwh(
        anlage.id, db, 0, inv_types={"7": "pv-module"},
    )

    assert ergebnis["einspeisung"] == 7.0
    assert ergebnis["netzbezug"] == 1.6
    assert ergebnis["pv_7"] == 10.5


# ─────────────────────────────────────────────────────────────────────────
# K2 — es wird KEINE zweite Sitzung geöffnet
# ─────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_kein_eigenes_get_session_auf_dem_anfragepfad(db, monkeypatch):
    """Die CI-Lage, ohne von einer Datei abzuhängen: jede eigene Sitzung ist ein Fehler.

    Gepatcht wird `get_session` **im Modul** — dort steht der Name, weil die
    Datei ihn auf Modulebene importiert. Ein Patch auf
    `backend.core.database.get_session` liefe an dieser Datei vorbei.
    """
    monkeypatch.setattr(svc, "datetime", _GestellteUhr)

    def _keine_eigene_sitzung(*args, **kwargs):  # noqa: ARG001
        raise AssertionError(
            "Anfragepfad darf keine eigene Sitzung öffnen — die übergebene `db` gilt"
        )

    monkeypatch.setattr(svc, "get_session", _keine_eigene_sitzung)
    anlage = await _anlage_mit_snapshots(db, zeitpunkte={
        GESTERN_MITTERNACHT: 0, HEUTE_MITTERNACHT: 1,
    })

    ergebnis = await svc.get_tages_kwh(
        anlage.id, db, 1, inv_types={"7": "pv-module"},
    )

    assert ergebnis["einspeisung"] == 18.0
    assert ergebnis["pv_7"] == 19.5


@pytest.mark.asyncio
async def test_fallback_zweig_oeffnet_auch_keine_eigene_sitzung(db, monkeypatch):
    """Gegenstück für `_get_earliest_snapshot_after` — er hatte seine eigene."""
    monkeypatch.setattr(svc, "datetime", _GestellteUhr)
    _mqtt_cache_auf(monkeypatch, 2)

    def _keine_eigene_sitzung(*args, **kwargs):  # noqa: ARG001
        raise AssertionError(
            "Anfragepfad darf keine eigene Sitzung öffnen — die übergebene `db` gilt"
        )

    monkeypatch.setattr(svc, "get_session", _keine_eigene_sitzung)
    anlage = await _anlage_mit_snapshots(db, zeitpunkte={
        datetime(2026, 3, 10, 6, 0): 1,
    })

    ergebnis = await svc.get_tages_kwh(
        anlage.id, db, 0, inv_types={"7": "pv-module"},
    )

    assert ergebnis["pv_7"] == 10.5


# ─────────────────────────────────────────────────────────────────────────
# K3 — der Aufrufer reicht seine Sitzung durch
# ─────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_live_pfad_reicht_seine_sitzung_durch(db, monkeypatch):
    """`safe_get_tages_kwh` gibt genau die Sitzung weiter, die es selbst bekam.

    ⚠ Die Zusicherung braucht diese eigene Probe, weil der MQTT-Zweig dort in
    einem `except Exception` steht: ein falscher Aufruf wird zu `logger.debug`
    und einem leeren Ergebnis, nicht zu einem Fehler.
    """
    gesehen: dict = {}

    async def _spion(anlage_id, db_, tage_zurueck=0, inv_types=None, erzeuger=None):
        gesehen.update(
            anlage_id=anlage_id, db=db_, tage=tage_zurueck, inv_types=inv_types,
        )
        return {"pv": 4.2}

    monkeypatch.setattr(svc, "get_tages_kwh", _spion)
    monkeypatch.setattr(
        ha_state_service, "get_ha_state_service",
        lambda: SimpleNamespace(is_available=False),
    )

    anlage = Anlage(id=1, anlagenname="nur MQTT")
    ergebnis = await lhs.safe_get_tages_kwh(
        anlage, db, 1, _Cache(), inv_types={"7": "pv-module"},
    )

    assert ergebnis == {"pv": 4.2}, (
        "Der MQTT-Zweig ist in sein `except` gefallen — der Aufruf passt nicht "
        "zur Signatur von `mqtt_energy_history_service.get_tages_kwh`."
    )
    assert gesehen["db"] is db, "die eigene Sitzung wurde nicht durchgereicht"
    assert gesehen["anlage_id"] == 1
    assert gesehen["tage"] == 1
    assert gesehen["inv_types"] == {"7": "pv-module"}
