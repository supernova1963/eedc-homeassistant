"""Die HA-Langzeitstatistik über die WebSocket-API — der dritte Transport.

`recorder/statistics_during_period` liefert dieselben Spalten, die
`ha_statistics_service.py` sonst per SQL aus `statistics` liest. Getestet wird
deshalb **nicht**, ob HA rechnen kann, sondern dass eedc über beide Kabel zur
**selben Zahl** kommt und dass die Vorrang-Regel steht.

Live gegengeprüft am 2026-08-05 gegen eine produktive Anlage (Recorder-DB auf
dem HA-Server, WebSocket von außen, identische Zeitzone): 27 Monatswerte
(Start · Ende · Differenz je Sensor über drei Monate) und 26 Monatsanfangswerte
— **0 Abweichungen**; verfügbare Monate identisch bis auf den Tag
(2024-10-31 … 2026-07-01, 22 Monate). Diese Datei hält das gegen Regressionen.

Standalone:
    eedc/backend/venv/bin/python eedc/backend/tests/test_ha_statistics_websocket_transport.py
"""

from __future__ import annotations

import sys
import time as time_module
import traceback
from datetime import date, datetime, timedelta
from pathlib import Path

_BACKEND_ROOT = Path(__file__).resolve().parents[2]  # eedc/
sys.path.insert(0, str(_BACKEND_ROOT))

from sqlalchemy import create_engine, text  # noqa: E402

from backend.services.ha_statistics_service import HAStatisticsService  # noqa: E402
from backend.services.ha_statistics_ws import (  # noqa: E402
    HAStatisticsWebsocket,
    WsSensorMeta,
)


# ---------------------------------------------------------------- Testdoubles


class FakeWebsocket:
    """Steht für `HAStatisticsWebsocket`, ohne Netz.

    Liefert Zeilen in genau der Form, die der echte Client aus HAs Antwort baut:
    `start_ts` in Unix-Sekunden, dazu `sum`/`state`/`mean`/`min`/`max`.
    """

    def __init__(self, metadaten: dict[str, WsSensorMeta], zeilen: dict[str, list[dict]]):
        self._metadaten = metadaten
        self._zeilen = zeilen
        self.ws_url = "ws://testhost:8123/api/websocket"
        self.abfragen: list[tuple] = []
        self.erreichbar_ergebnis = True

    def metadaten(self, erneuern: bool = False):
        return self._metadaten

    def statistiken(self, sensor_ids, von, bis, period="hour", types=None):
        self.abfragen.append((tuple(sensor_ids), von, bis, period))
        ts_von, ts_bis = von.timestamp(), bis.timestamp()
        return {
            sid: [z for z in self._zeilen.get(sid, []) if ts_von <= z["start_ts"] < ts_bis]
            for sid in sensor_ids
        }

    def erreichbar(self):
        return self.erreichbar_ergebnis

    def schliessen(self):
        pass


def _zeile(ts: float, **felder) -> dict:
    basis = {"start_ts": ts, "sum": None, "state": None, "mean": None, "min": None, "max": None}
    basis.update(felder)
    return basis


def _service_mit_ws(metadaten, zeilen) -> tuple[HAStatisticsService, FakeWebsocket]:
    """Service **ohne** Recorder-Datenbank, mit vorgegebenem WS-Transport."""
    svc = HAStatisticsService()
    svc._initialized = True   # kein Datei-/URL-Suchlauf
    svc._engine = None        # keine Datenbank ⇒ WebSocket ist der Weg
    fake = FakeWebsocket(metadaten, zeilen)
    svc._ws_client = fake
    return svc, fake


def _service_mit_db() -> HAStatisticsService:
    """Service mit In-Memory-Recorder — für die Vorrang-Gegenprobe."""
    svc = HAStatisticsService()
    svc._initialized = True
    svc._engine = create_engine("sqlite:///:memory:")
    with svc._engine.connect() as conn:
        conn.execute(text(
            "CREATE TABLE statistics_meta (id INTEGER PRIMARY KEY, statistic_id TEXT, "
            "unit_of_measurement TEXT, has_sum INTEGER)"
        ))
        conn.execute(text(
            "CREATE TABLE statistics (metadata_id INTEGER, start_ts REAL, sum REAL, "
            "state REAL, mean REAL, min REAL, max REAL)"
        ))
        conn.execute(text(
            "INSERT INTO statistics_meta VALUES (1, 'sensor.zaehler', 'kWh', 1)"
        ))
        conn.commit()
    return svc


def _monatsstunden(jahr: int, monat: int, sid: str, startwert: float, pro_stunde: float):
    """Ein Monat Stundenzeilen mit gleichmäßig steigendem Zähler."""
    beginn = datetime(jahr, monat, 1)
    ende = datetime(jahr + (monat // 12), (monat % 12) + 1, 1)
    zeilen, wert, t = [], startwert, beginn
    while t < ende:
        zeilen.append(_zeile(t.timestamp(), sum=round(wert, 3), state=round(wert, 3)))
        wert += pro_stunde
        t += timedelta(hours=1)
    return {sid: zeilen}


# ------------------------------------------------------------------- 1. Vorrang


def test_1_datenbank_hat_vorrang():
    """Mit Recorder-DB bleibt der WebSocket-Transport ungenutzt.

    Die Gegenprobe zum eigentlichen Bau: ein zweiter Transport darf den
    bestehenden nicht verdrängen. Wo eine Datenbank da ist, wird sie gelesen —
    synchron, ohne Netz.
    """
    svc = _service_mit_db()
    fake = FakeWebsocket({"sensor.zaehler": WsSensorMeta("kWh", True, False)}, {})
    svc._ws_client = fake

    assert svc._ws is None, "Mit Datenbank darf `_ws` niemanden liefern"
    assert svc.backend_type == "SQLite", f"backend_type={svc.backend_type}"
    assert svc.is_available is True
    assert fake.abfragen == [], "Der WS-Transport wurde trotz Datenbank befragt"
    print("  ✓ 1. Datenbank hat Vorrang, WS bleibt unbefragt")


def test_2_ohne_datenbank_traegt_der_websocket():
    """Ohne Recorder-Zugang ist die Statistik trotzdem verfügbar.

    Genau der Fall, für den gebaut wurde: eedc als eigener Container neben HA,
    ohne `/config`-Mount und ohne `HA_RECORDER_DB_URL`.
    """
    svc, fake = _service_mit_ws({"sensor.zaehler": WsSensorMeta("kWh", True, False)}, {})

    assert svc.is_available is True, "Ohne DB, aber mit WS muss die Statistik verfügbar sein"
    assert svc.backend_type == "HA-WebSocket", f"backend_type={svc.backend_type}"
    assert svc.db_path == "ws://testhost:8123/api/websocket", (
        "Die Herkunft muss benannt werden — sonst steht dort „nicht verfügbar“"
    )
    assert svc.count_statistics_sensors() == 1
    print("  ✓ 2. Ohne Datenbank trägt der WebSocket")


def test_3_ohne_beides_bleibt_es_unverfuegbar():
    """Kein Recorder, kein Token ⇒ unverfügbar. Keine stille Verfügbarkeit."""
    svc = HAStatisticsService()
    svc._initialized = True
    svc._engine = None

    assert svc.is_available is False
    assert svc.backend_type == "nicht verfügbar"
    assert svc.db_path is None
    print("  ✓ 3. Ohne beides bleibt es unverfügbar")


def test_4_nicht_erreichbare_ha_ist_nicht_verfuegbar():
    """Ein gesetzter Token allein genügt nicht — HA muss antworten.

    Gegenstück zum bekannten Fehlverhalten des SQLite-Zweigs, der sich schon
    „verfügbar" nennt, wenn die Datei existiert.
    """
    svc, fake = _service_mit_ws({"sensor.zaehler": WsSensorMeta("kWh", True, False)}, {})
    fake.erreichbar_ergebnis = False

    assert svc.is_available is False, "Token gesetzt, HA stumm ⇒ nicht verfügbar"
    assert svc.db_path is None
    print("  ✓ 4. Nicht erreichbare HA meldet sich nicht als verfügbar")


# ------------------------------------------------------------------ 2. Zahlen


def test_5_monatswert_ist_max_minus_min_der_summe():
    """Der Monatswert über WS ist MAX(sum) − MIN(sum) — wie im SQL-Pfad.

    Die Wahl von `sum` statt `state` ist die reset-bereinigte (Discussion #131);
    sie darf nicht davon abhängen, über welches Kabel die Zeilen kamen.
    """
    sid = "sensor.zaehler"
    zeilen = _monatsstunden(2026, 6, sid, startwert=1000.0, pro_stunde=0.5)
    svc, _ = _service_mit_ws({sid: WsSensorMeta("kWh", True, False)}, zeilen)

    antwort = svc.get_monatswerte([sid], 2026, 6)
    assert len(antwort.sensoren) == 1, f"{antwort.sensoren}"
    wert = antwort.sensoren[0]
    stunden = len(zeilen[sid])
    erwartet = round((stunden - 1) * 0.5, 2)
    assert wert.start_wert == 1000.0, f"start={wert.start_wert}"
    assert wert.differenz == erwartet, f"differenz={wert.differenz}, erwartet {erwartet}"
    print(f"  ✓ 5. Monatswert = MAX−MIN über {stunden} Stunden ⇒ {wert.differenz} kWh")


def test_6_monatswert_rechnet_die_einheit_um():
    """Wh-Zähler werden nach kWh skaliert — dieselbe Tabelle wie im SQL-Pfad."""
    sid = "sensor.wh_zaehler"
    zeilen = _monatsstunden(2026, 6, sid, startwert=1_000_000.0, pro_stunde=500.0)
    svc, _ = _service_mit_ws({sid: WsSensorMeta("Wh", True, False)}, zeilen)

    wert = svc.get_monatswerte([sid], 2026, 6).sensoren[0]
    stunden = len(zeilen[sid])
    assert wert.start_wert == 1000.0, f"start={wert.start_wert} (1.000.000 Wh = 1000 kWh)"
    assert wert.differenz == round((stunden - 1) * 500.0 / 1000.0, 2), f"{wert.differenz}"
    print(f"  ✓ 6. Wh → kWh umgerechnet ({wert.differenz} kWh)")


def test_7_monatsgrenze_wird_eingehalten():
    """Zeilen des Vor- und Folgemonats zählen nicht mit.

    Der schärfste Punkt beim Fensterbau: HA schließt `end_time` aus, die
    SQL-Variante filtert `>= start AND < end`. Ein Fehler um eine Stunde
    verschiebt Anfangs- **und** Endwert — und fällt bei einem Zähler, der
    nachts steht, nicht einmal auf.
    """
    sid = "sensor.zaehler"
    zeilen = _monatsstunden(2026, 6, sid, startwert=1000.0, pro_stunde=1.0)
    # Je eine Zeile davor und danach, beide mit weit abweichendem Zählerstand
    zeilen[sid].insert(0, _zeile(datetime(2026, 5, 31, 23).timestamp(), sum=1.0, state=1.0))
    zeilen[sid].append(_zeile(datetime(2026, 7, 1, 0).timestamp(), sum=99999.0, state=99999.0))
    svc, _ = _service_mit_ws({sid: WsSensorMeta("kWh", True, False)}, zeilen)

    wert = svc.get_monatswerte([sid], 2026, 6).sensoren[0]
    assert wert.start_wert == 1000.0, f"Vormonat mitgezählt: start={wert.start_wert}"
    assert wert.end_wert < 99999.0, f"Folgemonat mitgezählt: end={wert.end_wert}"
    print(f"  ✓ 7. Monatsgrenze gehalten ({wert.start_wert} … {wert.end_wert})")


def test_8_stunden_deltas_sind_backward_slots():
    """Slot h = Zähler(h) − Zähler(h−1), also Energie [h−1, h) (#144/#297).

    Die Slot-Konvention liegt **über** dem Transport: `lts_boundary_index`
    bekommt dieselben `start_ts` und darf nicht wissen, woher sie stammen.
    """
    sid = "sensor.zaehler"
    tag = date(2026, 6, 15)
    # Zeilen von 22:00 des Vortags bis 22:00 des Tages, 2 kWh je Stunde
    zeilen, wert = [], 500.0
    t = datetime(2026, 6, 14, 22)
    while t <= datetime(2026, 6, 15, 22):
        zeilen.append(_zeile(t.timestamp(), sum=round(wert, 3), state=round(wert, 3)))
        wert += 2.0
        t += timedelta(hours=1)
    svc, _ = _service_mit_ws({sid: WsSensorMeta("kWh", True, False)}, {sid: zeilen})

    slots = svc.get_hourly_kwh_deltas_for_day([sid], tag)[sid]
    belegt = {h: v for h, v in slots.items() if v is not None}
    assert len(belegt) == 24, f"nur {len(belegt)} von 24 Slots belegt: {sorted(belegt)}"
    assert all(abs(v - 2.0) < 0.001 for v in belegt.values()), f"{belegt}"
    print(f"  ✓ 8. 24 Backward-Slots à 2,0 kWh")


def test_9_value_at_nimmt_die_naechste_zeile():
    """`get_value_at` wählt die Zeile mit dem geringsten Abstand — wie `ORDER BY ABS(...)`.

    Und sie liest bei `has_sum` **ausschließlich** `sum`: `state` kann eine
    andere Größe sein (Tageswert eines utility_meter), das Mischen erzeugt
    Counter-Spitzen in Höhe des Lifetime-Werts.
    """
    sid = "sensor.zaehler"
    zeilen = [
        _zeile(datetime(2026, 6, 15, 9).timestamp(), sum=100.0, state=7.0),
        _zeile(datetime(2026, 6, 15, 10).timestamp(), sum=110.0, state=8.0),
        _zeile(datetime(2026, 6, 15, 11).timestamp(), sum=120.0, state=9.0),
    ]
    svc, _ = _service_mit_ws({sid: WsSensorMeta("kWh", True, False)}, {sid: zeilen})

    # Wert AT 12:00 ⇒ Zeile mit start_ts = 11:00 (Wert am Ende der Periode)
    wert = svc.get_value_at(sid, datetime(2026, 6, 15, 12))
    assert wert == 120.0, f"{wert} statt 120.0 (sum der 11:00-Zeile)"

    # Wert AT 11:00 ⇒ Zeile 10:00
    assert svc.get_value_at(sid, datetime(2026, 6, 15, 11)) == 110.0

    # Außerhalb der Toleranz ⇒ nichts
    assert svc.get_value_at(sid, datetime(2026, 6, 15, 20), toleranz_minuten=30) is None
    print("  ✓ 9. get_value_at nimmt die nächste Zeile und liest `sum`")


def test_10_monatsanfang_ist_das_minimum():
    sid = "sensor.zaehler"
    zeilen = _monatsstunden(2026, 6, sid, startwert=250.0, pro_stunde=0.25)
    svc, _ = _service_mit_ws({sid: WsSensorMeta("kWh", True, False)}, zeilen)

    assert svc.get_monatsanfang_wert(sid, 2026, 6) == 250.0
    print("  ✓ 10. Monatsanfang = MIN(state)")


def test_11_verfuegbare_monate_ohne_laufenden_monat():
    """Die Monatsliste entsteht aus erstem und letztem Messzeitpunkt.

    Dass der laufende Monat draußen bleibt, ist eine fachliche Festlegung und
    liegt deshalb in `_monatsliste` — gemeinsam für beide Transporte.
    """
    heute = date.today()
    erstes = date(heute.year - 1, 1, 1)
    grenzen = (
        datetime(erstes.year, erstes.month, 15).timestamp(),
        datetime(heute.year, heute.month, 5).timestamp(),
    )
    svc = HAStatisticsService()
    antwort = svc._monatsliste(*grenzen)

    monate = {(m.jahr, m.monat) for m in antwort.monate}
    assert (heute.year, heute.month) not in monate, "Der laufende Monat gehört nicht hinein"
    assert (erstes.year, erstes.month) in monate
    assert antwort.erstes_datum == date(erstes.year, erstes.month, 15)
    print(f"  ✓ 11. {antwort.anzahl_monate} Monate, laufender ausgenommen")


def test_12_summenfaehigkeit_kommt_aus_den_metadaten():
    """`has_sum` trennt Energie-Zähler von Messwert-Sensoren — auch über WS.

    Ohne `has_sum` überspringt der Delta-Leser jede Zeile; von außen ist das
    nicht von „gar nicht zugeordnet" zu unterscheiden (Forum #89667/44).
    """
    svc, _ = _service_mit_ws(
        {
            "sensor.zaehler": WsSensorMeta("kWh", True, False),
            "sensor.leistung": WsSensorMeta("W", False, True),
        },
        {},
    )
    mit, ohne, fehlend = svc.filter_summen_faehige_sensor_ids(
        ["sensor.zaehler", "sensor.leistung", "sensor.gibtsnicht"]
    )
    assert mit == ["sensor.zaehler"], mit
    assert ohne == ["sensor.leistung"], ohne
    assert fehlend == ["sensor.gibtsnicht"], fehlend
    print("  ✓ 12. Summenfähigkeit kommt aus den WS-Metadaten")


def test_13_stundenmittel_rechnet_watt_in_kilowatt():
    """Leistungs-Mittelwerte: W → kW, kWh-Zähler werden übersprungen."""
    svc, _ = _service_mit_ws(
        {
            "sensor.leistung": WsSensorMeta("W", False, True),
            "sensor.zaehler": WsSensorMeta("kWh", True, False),
        },
        {
            "sensor.leistung": [
                _zeile(datetime(2026, 6, 15, h).timestamp(), mean=3000.0) for h in range(24)
            ],
            "sensor.zaehler": [
                _zeile(datetime(2026, 6, 15, h).timestamp(), mean=99.0) for h in range(24)
            ],
        },
    )
    daten = svc.get_hourly_sensor_data(
        ["sensor.leistung", "sensor.zaehler"], date(2026, 6, 15), date(2026, 6, 15),
    )
    assert "sensor.zaehler" not in daten, "kWh-Zähler ist kein Leistungssensor"
    assert daten["sensor.leistung"]["2026-06-15"][12] == 3.0, daten["sensor.leistung"]
    print("  ✓ 13. Stundenmittel W → kW, Zähler übersprungen")


# ------------------------------------------------------------ 3. Adressen/Robustheit


def test_14_websocket_adresse():
    """Beide URL-Formen führen auf denselben Endpunkt.

    `resolve_ha_connection` liefert die URL **mit** `/api`-Suffix, die
    Supervisor-Variante zeigt auf `http://supervisor/core/api`.
    """
    faelle = [
        ("http://10.0.0.5:8123", "ws://10.0.0.5:8123/api/websocket"),
        ("http://10.0.0.5:8123/api", "ws://10.0.0.5:8123/api/websocket"),
        ("https://ha.example.com/api/", "wss://ha.example.com/api/websocket"),
        ("http://supervisor/core/api", "ws://supervisor/core/api/websocket"),
    ]
    for eingabe, erwartet in faelle:
        ergebnis = HAStatisticsWebsocket._ws_adresse(eingabe)
        assert ergebnis == erwartet, f"{eingabe} → {ergebnis}, erwartet {erwartet}"
    print("  ✓ 14. WebSocket-Adressen aus allen vier URL-Formen")


def test_15_verbindungswechsel_verwirft_den_alten_stand():
    """Ein Verbindungswechsel darf keine Werte der alten Instanz weiterreichen."""
    sid = "sensor.zaehler"
    svc, _ = _service_mit_ws({sid: WsSensorMeta("kWh", True, False)}, {})
    svc.get_metadata(None, sid)              # füllt den Metadaten-Cache
    assert sid in svc._meta_cache

    svc.setze_ha_verbindung(None, None)
    assert svc._meta_cache == {}, "Metadaten der alten Verbindung überlebt"
    assert svc._ws_client is None
    assert svc.is_available is False
    print("  ✓ 15. Verbindungswechsel verwirft Metadaten und Client")


def test_16_ws_fehler_liefert_leer_statt_zu_werfen():
    """Ein Netzfehler mitten im Lauf darf den Aufrufer nicht sprengen.

    Der Snapshot-Job läuft stündlich im Hintergrund; eine Ausnahme dort ließe
    den ganzen Lauf ausfallen statt nur diesen einen Wert.
    """
    sid = "sensor.zaehler"

    class KaputterClient(FakeWebsocket):
        def statistiken(self, *a, **k):
            raise RuntimeError("Verbindung weg")

    svc = HAStatisticsService()
    svc._initialized, svc._engine = True, None
    svc._ws_client = KaputterClient({sid: WsSensorMeta("kWh", True, False)}, {})

    assert svc.get_hourly_kwh_deltas_for_day([sid], date(2026, 6, 15)) == {}
    assert svc.get_short_term_5min_for_day([sid], date(2026, 6, 15)) == {}
    assert svc.get_hourly_sensor_data([sid], date(2026, 6, 15), date(2026, 6, 15)) == {}
    print("  ✓ 16. Netzfehler ⇒ leeres Ergebnis, keine Ausnahme")


def test_17_fuenf_minuten_ebene():
    """`period=5minute` ist das Gegenstück zu `statistics_short_term`."""
    sid = "sensor.zaehler"
    tag = date(2026, 6, 15)
    zeilen, wert = [], 500.0
    t = datetime(2026, 6, 14, 23, 55)
    while t <= datetime(2026, 6, 15, 1, 0):
        zeilen.append(_zeile(t.timestamp(), sum=round(wert, 4), mean=100.0))
        wert += 0.1
        t += timedelta(minutes=5)
    svc, fake = _service_mit_ws({sid: WsSensorMeta("kWh", True, False)}, {sid: zeilen})

    ergebnis = svc.get_short_term_5min_for_day([sid], tag, bis=datetime(2026, 6, 15, 1, 0))
    assert sid in ergebnis, ergebnis
    deltas = ergebnis[sid]["counter_deltas"]
    assert deltas, "keine 5-Min-Deltas gebildet"
    assert all(abs(v - 0.1) < 0.0001 for v in deltas.values()), f"{list(deltas.values())[:5]}"
    assert any(p == "5minute" for *_, p in fake.abfragen), (
        f"Es wurde nicht auf der 5-Minuten-Ebene gefragt: {fake.abfragen}"
    )
    print(f"  ✓ 17. 5-Minuten-Ebene: {len(deltas)} Deltas à 0,1 kWh")


def test_18_rohantwort_wird_richtig_gelesen():
    """Der echte Client gegen eine rohe HA-Antwort — Feldnamen, Einheit, Zeit.

    ⚠ Diese Probe entstand, weil eine Gegenprobe **stumm** blieb: das Vertauschen
    von `statistics_unit_of_measurement` mit `display_unit_of_measurement` ließ
    alle übrigen Tests grün, weil sie am fertigen `WsSensorMeta` ansetzen. Die
    Verwechslung ist aber teuer — HA führt für denselben Sensor eine
    **Anzeige**-Einheit (was das Frontend zeigt, z. B. MWh) neben der
    **Statistik**-Einheit (in der die Werte gespeichert sind, kWh). Wer die
    Anzeige-Einheit für eine Rechnung nimmt, liegt um den Faktor 1000 daneben.

    Läuft absichtlich durch die echte sync→async-Brücke: sie ist der einzige
    Mechanismus dieser Art im Baum und hat sonst keinen Beleg.
    """
    roh_ids = [
        {
            "statistic_id": "sensor.zaehler",
            "display_unit_of_measurement": "MWh",     # was HA anzeigen würde
            "statistics_unit_of_measurement": "kWh",  # worin gespeichert ist
            "has_sum": True,
            "has_mean": False,
            "source": "recorder",
        },
        {
            "statistic_id": "sensor.leistung",
            "display_unit_of_measurement": "kW",
            "statistics_unit_of_measurement": "W",
            "has_sum": False,
            "has_mean": True,
            "source": "recorder",
        },
    ]
    zeitpunkt = datetime(2026, 6, 15, 10)
    roh_stats = {
        "sensor.zaehler": [
            # HA liefert Millisekunden seit Epoch — die Recorder-Spalte Sekunden
            {"start": int(zeitpunkt.timestamp() * 1000),
             "end": int((zeitpunkt + timedelta(hours=1)).timestamp() * 1000),
             "sum": 123.456, "state": 77.0},
        ],
    }

    client = HAStatisticsWebsocket("http://testhost:8123/api", "geheim")

    async def _antwort(payload):
        if payload["type"] == "recorder/list_statistic_ids":
            return roh_ids
        return roh_stats

    client._befehl = _antwort  # type: ignore[assignment]

    meta = client.metadaten()
    assert meta["sensor.zaehler"].unit == "kWh", (
        f"Statistik-Einheit erwartet, bekommen: {meta['sensor.zaehler'].unit}"
    )
    assert meta["sensor.zaehler"].has_sum is True
    assert meta["sensor.leistung"].unit == "W", meta["sensor.leistung"].unit
    assert meta["sensor.leistung"].has_mean is True

    zeilen = client.statistiken(
        ["sensor.zaehler"], zeitpunkt, zeitpunkt + timedelta(hours=2),
    )["sensor.zaehler"]
    assert len(zeilen) == 1, zeilen
    assert zeilen[0]["start_ts"] == zeitpunkt.timestamp(), (
        f"Millisekunden nicht in Sekunden umgerechnet: {zeilen[0]['start_ts']}"
    )
    assert datetime.fromtimestamp(zeilen[0]["start_ts"]) == zeitpunkt
    assert zeilen[0]["sum"] == 123.456
    assert zeilen[0]["mean"] is None, "Nicht gelieferte Felder müssen None sein, nicht fehlen"
    print("  ✓ 18. Rohantwort: Statistik-Einheit, ms→s, fehlende Felder als None")


def _main() -> int:
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    print(f"\n=== HA-Statistik über WebSocket — {len(tests)} Proben ===\n")
    fehler = 0
    for t in tests:
        try:
            t()
        except Exception:
            fehler += 1
            print(f"  ✗ {t.__name__}")
            traceback.print_exc()
    print(f"\n{len(tests) - fehler}/{len(tests)} bestanden")
    return 1 if fehler else 0


if __name__ == "__main__":
    sys.exit(_main())
