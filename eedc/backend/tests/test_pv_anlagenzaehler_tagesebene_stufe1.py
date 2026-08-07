"""Der PV-Anlagenzähler erreicht die Tagesebene (Stufe 1 zu F-7).

Forum kaba-kakao (T89667 #109, 2026-08-07): ein Summenzähler für die ganze
Anlage, mehrere Ausrichtungen, kein Zähler je String ⇒ Tages-PV 0, daraus ein
negativer Eigenverbrauch. F-7 hat die **Anzeige** ehrlich gemacht (`pv_erfasst`,
`test_tagesbilanz_pv_nicht_erfasst.py`); dieses Paket macht den **Wert**
verfügbar: `basis:pv_gesamt` ist ein Snapshot-Zähler der Kategorie `pv`.

Warum nicht einfach alle Strings zu EINER Investition zusammenfassen? Weil
`services/pv_orientation.py` je Investition nach (Neigung, Azimut) gruppiert —
sein Docstring nennt die Folge wörtlich: ein systematisch falscher Tagesgang für
den ganzen Prognose-Kanon inkl. HA-Prognose-Sensoren und PVGIS-SOLL.

Die tragende Regel ist **alles-oder-nichts**, nicht eine Verteilung: entweder
zählt die Anlagensumme, oder die Erzeuger zählen einzeln — nie beides. Genau so
hält es der Live-Pfad seit jeher (`live_tagesverlauf_service:267`,
`not has_individual_pv`). Eine kWp-Verteilung auf Tagesebene ist verworfen
(Entscheid Gernot 2026-08-07): sie erfände Messwerte.

⚠ **Die schärfste Probe hier ist nicht der Fix, sondern die Abgrenzung**
(`test_teilbelegung_verdraengt_das_aggregat`): stünde `pv_gesamt` neben `pv_7`
im flachen Keyspace von `komponenten_kwh`, summierte `summe_pv_bkw_kwh` beides
— die Anlagensumme neben ihrem eigenen Summanden, also die Doppelzähl-Klasse aus
#290/#298.
"""

from __future__ import annotations

from datetime import date, datetime
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from backend.core.berechnungen.energie import (
    erzeuger_kwh_je_investition,
    summe_pv_bkw_kwh,
)
from backend.services.snapshot.keys import (
    BASIS_ZAEHLER_FELDER,
    _categorize_counter,
    _mqtt_key_to_sensor_key,
    _sensor_key_to_mqtt_key,
)
from backend.services.snapshot.komponenten_beitraege import (
    basis_beitraege,
    basis_hourly_eintraege,
    mqtt_hourly_eintraege,
    pv_je_investition_belegt,
    pv_je_investition_in_sensor_keys,
)
from backend.services.snapshot.aggregator import get_hourly_kwh_by_category
from backend.services.snapshot.writer import _build_counter_map


def _sensor(sid: str) -> dict:
    return {"strategie": "sensor", "sensor_id": sid}


def _nur_aggregat() -> dict:
    """Stephans Lage: Summenzähler an der Basis, Strings ohne eigenen Zähler."""
    return {
        "basis": {
            "pv_gesamt": _sensor("sensor.pv_anlage_gesamt"),
            "einspeisung": _sensor("sensor.einspeisung"),
            "netzbezug": _sensor("sensor.netzbezug"),
        },
        "investitionen": {
            "1": {"felder": {}, "live": {"leistung_w": "sensor.west_w"}},
            "2": {"felder": {}, "live": {"leistung_w": "sensor.ost_w"}},
        },
    }


# ─── Schlüssel-Schema ───────────────────────────────────────────────────────

def test_pv_gesamt_ist_ein_basis_zaehler():
    assert "pv_gesamt" in BASIS_ZAEHLER_FELDER


def test_mqtt_key_uebersetzung_in_beide_richtungen():
    assert _mqtt_key_to_sensor_key("pv_gesamt_kwh") == "basis:pv_gesamt"
    assert _sensor_key_to_mqtt_key("basis:pv_gesamt") == "pv_gesamt_kwh"


def test_kategorie_ist_pv():
    """Dieselbe Kategorie wie ein Zähler je Erzeuger — sonst landete die
    Anlagensumme neben der Erzeugung statt in ihr."""
    assert _categorize_counter("pv_gesamt", None, None) == "pv"


def test_writer_sammelt_den_anlagenzaehler_ein():
    """Ohne diesen Schritt gäbe es nie einen Snapshot, aus dem ein Tagesdelta
    entstehen könnte."""
    anlage = type("A", (), {"sensor_mapping": _nur_aggregat()})()
    assert _build_counter_map(anlage)["basis:pv_gesamt"] == "sensor.pv_anlage_gesamt"


# ─── Alles-oder-nichts ──────────────────────────────────────────────────────

def test_aggregat_traegt_die_tagesebene_ohne_einzelzaehler():
    beitraege = basis_beitraege(_nur_aggregat())
    assert ("pv_gesamt", "pv_gesamt") in [(b.feld, b.target_key) for b in beitraege]
    kategorien = {he.feld: he.kategorie for he in basis_hourly_eintraege(_nur_aggregat())}
    assert kategorien["pv_gesamt"] == "pv"


def test_teilbelegung_verdraengt_das_aggregat():
    """EIN Erzeuger mit eigenem Zähler schaltet die Anlagensumme ab — sonst
    stünde sie neben ihrem eigenen Summanden (Doppelzählung).

    Bewusst mit ZWEI Modulen und nur EINEM Zähler geprüft: eine Either-Or-Gruppe
    (`resolve_either_or_eintraege`) ist 1-aus-n und hätte hier eines der beiden
    Module verloren. Die Regel ist n-schlägt-1, keine Gruppe."""
    mapping = _nur_aggregat()
    mapping["investitionen"]["1"]["felder"]["pv_erzeugung_kwh"] = _sensor("sensor.west_kwh")

    felder = {b.feld for b in basis_beitraege(mapping)}
    assert "pv_gesamt" not in felder
    assert felder == {"einspeisung", "netzbezug"}   # der Rest bleibt unberührt
    assert pv_je_investition_belegt(mapping) is True


def test_verdraengung_nur_durch_einen_ECHTEN_zaehler():
    """Ein Erzeuger mit Live-Leistung, aber ohne kWh-Zähler, verdrängt nichts —
    genau Stephans Lage. Und ein Eintrag ohne `sensor_id` ebensowenig: er ist
    keine Zuordnung, sondern ein leeres Feld."""
    assert pv_je_investition_belegt(_nur_aggregat()) is False

    mapping = _nur_aggregat()
    mapping["investitionen"]["1"]["felder"]["pv_erzeugung_kwh"] = {
        "strategie": "sensor", "sensor_id": None,
    }
    assert pv_je_investition_belegt(mapping) is False

    mapping["investitionen"]["1"]["felder"]["pv_erzeugung_kwh"] = {"strategie": "keine"}
    assert pv_je_investition_belegt(mapping) is False


def test_ein_anderes_feld_verdraengt_nicht():
    """Abgrenzung: nur `pv_erzeugung_kwh` ist der Gegenspieler. Ein Speicher-
    oder Wallbox-Zähler an derselben Anlage darf die PV-Summe nicht abschalten."""
    mapping = _nur_aggregat()
    mapping["investitionen"]["3"] = {"felder": {"ladung_kwh": _sensor("sensor.batt")}}
    assert pv_je_investition_belegt(mapping) is False
    assert "pv_gesamt" in {b.feld for b in basis_beitraege(mapping)}


# ─── Die Regel gilt quellen-übergreifend (MQTT) ─────────────────────────────

def test_mqtt_zaehler_je_erzeuger_verdraengt_das_aggregat():
    """Ein per MQTT publizierter String-Zähler steht NICHT im `sensor_mapping`
    (Verfügbarkeit kommt seit #317 aus den Topics). Wer die Regel nur am
    Mapping festmacht, zählt bei gemischter Installation doppelt."""
    assert pv_je_investition_in_sensor_keys(
        ["basis:pv_gesamt", "inv:1:pv_erzeugung_kwh"]
    ) is True
    assert pv_je_investition_in_sensor_keys(
        ["basis:pv_gesamt", "inv:1:ladung_kwh", "basis:einspeisung"]
    ) is False

    # Und das Flag greift durch bis zum Basis-Beitrag:
    felder = {b.feld for b in basis_beitraege(
        _nur_aggregat(), pv_je_investition_extern=True
    )}
    assert "pv_gesamt" not in felder


def test_mqtt_pfad_loest_dieselbe_regel_auf():
    inv = type("I", (), {"id": 1, "typ": "pv-module", "parameter": {},
                         "parent_investition_id": None})()

    nur_aggregat = mqtt_hourly_eintraege(["basis:pv_gesamt"], {"1": inv}, {})
    assert [(sk, kat) for sk, kat, _ in nur_aggregat] == [("basis:pv_gesamt", "pv")]

    gemischt = mqtt_hourly_eintraege(
        ["basis:pv_gesamt", "inv:1:pv_erzeugung_kwh"], {"1": inv}, {},
    )
    keys = {sk for sk, _kat, _grp in gemischt}
    assert "basis:pv_gesamt" not in keys
    assert "inv:1:pv_erzeugung_kwh" in keys


# ─── Einhängung: der Aggregator selbst, nicht nur seine Bausteine ───────────
#
# Die Bausteine oben sind reine Funktionen. Ob der Aggregator sie richtig
# verdrahtet — insbesondere, ob er die MQTT-Keys VOR dem Basis-Beitrag kennt —
# sagen sie nicht. Genau diese Lücke hat bei N-161 zugeschlagen (Einhängung in
# `check_anlage` ungedeckt), deshalb die beiden End-to-End-Proben hier.

_DATUM = date(2026, 5, 22)


def _db_mit_mqtt_keys(keys: list[str]):
    """MagicMock-`db`, dessen `mqtt_energy_snapshots`-Query `keys` liefert."""
    result = MagicMock()
    result.all.return_value = [(k,) for k in keys]

    async def _execute(*a, **k):
        return result

    db = MagicMock()
    db.execute = _execute
    return db


def _kumulativer_snapshot(werte_je_key: dict[str, float]):
    """`get_snapshot`-Ersatz: linear steigender Zähler, `werte_je_key` kWh/Tag.

    Die Stunden-Slots laufen **backward** (Issue #144): Slot h ist
    `snap[h] − snap[h−1]`, die Boundaries reichen von Offset −1 (Vortag 23:00)
    bis 23. Der Zähler steigt deshalb über `(o+1)/24`, damit die Σ der 24 Slots
    exakt dem Tageswert entspricht — mit `o/24` fehlte eine Stunde und die Probe
    hätte 23/24 gemessen statt eines Fehlers.
    """
    tag0 = datetime.combine(_DATUM, datetime.min.time())

    async def fake_get_snapshot(db, anlage_id, sensor_key, sensor_id, zeitpunkt, *a, **k):
        tageswert = werte_je_key.get(sensor_key)
        if tageswert is None:
            return None
        o = round((zeitpunkt - tag0).total_seconds() / 3600.0)
        return max(0.0, min(24.0, o + 1.0)) / 24.0 * tageswert

    return fake_get_snapshot


async def test_aggregator_fuellt_pv_aus_dem_anlagenzaehler():
    """Stephans Lage von Ende zu Ende: nur der Summenzähler ist zugeordnet,
    und die Stunden-Kategorie `pv` trägt trotzdem seinen Ertrag."""
    anlage = SimpleNamespace(id=1, sensor_mapping=_nur_aggregat())
    with patch(
        "backend.services.snapshot.aggregator.get_snapshot",
        _kumulativer_snapshot({"basis:pv_gesamt": 24.0}),
    ):
        hourly = await get_hourly_kwh_by_category(
            _db_mit_mqtt_keys([]), anlage, {}, _DATUM,
        )

    assert sum(hourly[h].get("pv") or 0.0 for h in range(24)) == 24.0
    assert hourly[12]["pv"] == 1.0


async def test_aggregator_zaehlt_mqtt_string_und_aggregat_nicht_doppelt():
    """Gemischte Installation: Aggregat als HA-Sensor, ein String per MQTT.

    Der String verdrängt das Aggregat — sonst stünden 24 + 10 = 34 kWh in der
    Stunden-Bilanz, obwohl die Anlage 24 erzeugt hat. Die Probe hängt an der
    Reihenfolge im Aggregator: die MQTT-Keys müssen VOR dem Basis-Beitrag
    bekannt sein."""
    inv = SimpleNamespace(id=1, typ="pv-module", parameter={},
                          parent_investition_id=None)
    anlage = SimpleNamespace(id=1, sensor_mapping=_nur_aggregat())
    with patch(
        "backend.services.snapshot.aggregator.get_snapshot",
        _kumulativer_snapshot({
            "basis:pv_gesamt": 24.0,
            "inv:1:pv_erzeugung_kwh": 10.0,
        }),
    ):
        hourly = await get_hourly_kwh_by_category(
            _db_mit_mqtt_keys(["inv/1/pv_erzeugung_kwh"]),
            anlage, {"1": inv}, _DATUM,
        )

    assert sum(hourly[h].get("pv") or 0.0 for h in range(24)) == 10.0


# ─── Achse-2-Abgrenzung: keine Geisterspalte je Erzeuger ────────────────────

def test_anlagensumme_zaehlt_als_pv_aber_nicht_als_erzeuger():
    """`pv_gesamt` matcht das Präfix `pv_` und geht deshalb in die Tages-PV ein.
    In die Spalte JE ERZEUGER darf es nicht: es benennt keine Investition und
    wäre dort eine Summe neben ihren eigenen Summanden (#350)."""
    komponenten = {"pv_gesamt": 12.5, "einspeisung": 4.0}

    assert summe_pv_bkw_kwh(komponenten) == 12.5
    assert erzeuger_kwh_je_investition(komponenten) == {}
