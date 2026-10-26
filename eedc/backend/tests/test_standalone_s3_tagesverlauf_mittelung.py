"""Standalone-Gleichstand Sitzung 3 — Tagesverlauf für reine MQTT-Anlagen und eine Mittelungsregel (HA-Bauform §9).

* **S3-1 Tagesverlauf ohne ``live``-Zuordnung:** ``get_tagesverlauf`` fragt zuerst «HA-Verbindung da?» und erst im
  HA-Zweig nach der Zuordnung. Ohne HA-Token geht jede Anlage in den MQTT-Zweig — auch eine reine MQTT-Inbound-Anlage,
  deren Werte nur über die Inbound-Topics kommen; der Zweig liest nur ``mqtt_live_snapshots`` und liefert leer, wenn
  keine da sind. Mit HA-Token und leerer Zuordnung blieb es in S3 leer (kein MQTT-Abruf, kein HA-Abruf); seit S4
  (Mischform) geht auch dieser Fall in den MQTT-Zweig, HA bleibt unbefragt.
  Konsument ``aggregate_day``: die reine MQTT-Anlage wird jetzt wie die Standalone-Anlage mit ``live``-Zuordnung
  aggregiert (dieselben Stundenzeilen aus derselben Kurve).
* **S3-2 eine Gewichtung:** ``schreiber.fenster_gewicht`` ist die eine Regel für die Stunden-Verdichtung der
  5-Minuten-Zeilen — ``mittel_je_stunde`` (Mittelwerte) und ``modus_anteile_je_stunde`` (Betriebsart-Anteile) rufen
  sie. Bei regelmäßigem Takt ist das gewichtete Mittel genau das einfache (auch im letzten Bit); verschieden sind die
  alten Regeln nur bei Zeilen, die enger als ein Fenster liegen (Takt-Versatz des Snapshot-Jobs).

Schwesterdateien: test_tagesverlauf_standalone_ha_verbindung.py (Weggabelung F-26), test_408_wrapper_reicht_vortagsrand_
durch.py (``aggregate_day`` mit MQTT-Energie-Anker und Kurve), test_standalone_s1_betriebsmodus_mqtt.py (Modus-Mitschrift),
test_standalone_s2_mittelwert_mitschrift.py (Mittelwert-Mitschrift).
"""

from __future__ import annotations

import calendar
from contextlib import ExitStack
from datetime import date, datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select

from backend.models.mqtt_energy_snapshot import MqttEnergySnapshot
from backend.models.mqtt_live_snapshot import MqttLiveSnapshot
from backend.models.tages_energie_profil import TagesEnergieProfil
from backend.services import live_tagesverlauf_service as ltv
from backend.services.energie_profil.source import Source
from backend.services.ha_state_service import get_ha_state_service
from backend.services.kanal.schreiber import (
    _SNAPSHOT_FENSTER,
    _stunden_start_ts,
    fenster_gewicht,
    mittel_je_stunde,
    modus_anteile_je_stunde,
)
from backend.tests import factories

#: Ein fester Tag und eine feste Uhr am Folgetag (``tage_zurueck = 1``, der Regelfall, kein «heute bis jetzt»): die Uhr
#: des Tagesverlaufs (``live_tagesverlauf_service.datetime``) und die Tageszählung des Aggregators (``_tage_zurueck``)
#: stehen auf ``JETZT`` — keine Probe liest die Prozessuhr.
TAG = date(2026, 9, 4)
JETZT = datetime(2026, 9, 5, 12, 0, 0)
_STUNDE = 3600
T0 = calendar.timegm((2026, 6, 10, 8, 0, 0))     # volle UTC-Stunde — in Berlin · UTC · Auckland auch eine volle Ortsstunde
HEIZEN, WARMWASSER = "heizen", "warmwasser"


@pytest.fixture
def ha_verbindung():
    """Setzt/entfernt die Remote-Verbindung am Singleton — und räumt auf (Muster F-26-Proben)."""
    svc = get_ha_state_service()
    vorher = (svc.api_url, svc.token)

    def setzen(token):
        svc.api_url = "http://ha.example:8123/api"
        svc.token = token

    yield setzen
    svc.api_url, svc.token = vorher


@pytest.fixture(autouse=True)
def _ohne_marktabruf(monkeypatch):
    """Beide Zweige holen nebenbei Börsenpreise — hier nicht der Gegenstand (und kein Netz im Test)."""
    from backend.services import strompreis_markt_service as sms

    async def keine_preise(land, tag):
        return {}

    monkeypatch.setattr(sms, "get_strompreis_stunden", keine_preise)


class _FesteUhr(datetime):
    @classmethod
    def now(cls, tz=None):
        return JETZT if tz is None else JETZT.astimezone(tz)


@pytest.fixture(autouse=True)
def _feste_uhr(monkeypatch):
    from backend.services.energie_profil import _helpers

    monkeypatch.setattr(ltv, "datetime", _FesteUhr)
    monkeypatch.setattr(_helpers, "_tage_zurueck", lambda tag: (JETZT.date() - tag).days)


def _tage_zurueck(tag: date) -> int:
    return (JETZT.date() - tag).days


async def _anlage_pv(db, mapping: dict):
    a = await factories.anlage(db, anlagenname="Nur MQTT", leistung_kwp=8.0, sensor_mapping=mapping)
    pv = await factories.investition(db, a.id, "pv-module", bezeichnung="PV Süd", anschaffungsdatum=date(2020, 1, 1))
    await db.commit()
    return a, pv


def _leistung_snaps(db, anlage_id: int, pv_id: int, tag: date) -> None:
    """10:00–12:00 alle 5 Minuten: PV 2000 W, Netzbezug 300 W (die Werte, die der MQTT-Zweig zeichnet)."""
    beginn = datetime.combine(tag, datetime.min.time()) + timedelta(hours=10)
    for i in range(24):
        ts = beginn + timedelta(minutes=5 * i)
        for key, wert in ((f"inv:{pv_id}:leistung_w", 2000.0), ("basis:netzbezug_w", 300.0)):
            db.add(MqttLiveSnapshot(anlage_id=anlage_id, timestamp=ts, component_key=key, value_w=wert,
                                    ts_unix=int(ts.timestamp())))


class _Merker:
    def __init__(self):
        self.mqtt = 0
        self.ha = 0


# ═══ S3-1 Tagesverlauf ohne `live`-Zuordnung ══════════════════════════════════

@pytest.mark.asyncio
@pytest.mark.parametrize("mapping", [
    {},
    {"basis": {}, "investitionen": {}},
    {"basis": {"live": {}}, "investitionen": {"1": {"live": {}}}},
], ids=["mapping-leer", "bloecke-leer", "live-leer"])
async def test_reine_mqtt_anlage_bekommt_ihren_tagesverlauf(db, ha_verbindung, mapping):
    """Ohne HA-Token und ohne `live`-Zuordnung: Serien und Punkte aus den Snapshots (vorher: leer vor der Weiche)."""
    ha_verbindung(None)
    a, pv = await _anlage_pv(db, mapping)
    _leistung_snaps(db, a.id, pv.id, TAG)
    await db.commit()

    erg = await ltv.get_tagesverlauf(a, db, _tage_zurueck(TAG))

    keys = {s["key"] for s in erg["serien"]}
    assert f"pv_{pv.id}" in keys and "netzbezug" in keys, keys
    mit_pv = [p for p in erg["punkte"] if p["werte"].get(f"pv_{pv.id}")]
    assert mit_pv, "die MQTT-Kurve trägt Leistung"
    assert {p["zeit"] for p in mit_pv} == {f"{h:02d}:{m:02d}" for h in (10, 11) for m in range(0, 60, 10)}
    assert all(p["werte"][f"pv_{pv.id}"] == pytest.approx(2.0) for p in mit_pv), "2000 W ⇒ 2,0 kW je Slot"


@pytest.mark.asyncio
async def test_reine_mqtt_anlage_ohne_snapshots_bleibt_leer(db, ha_verbindung):
    ha_verbindung(None)
    a, _ = await _anlage_pv(db, {})

    assert await ltv.get_tagesverlauf(a, db, _tage_zurueck(TAG)) == {"serien": [], "punkte": []}


@pytest.mark.asyncio
async def test_mit_ha_token_und_leerer_zuordnung_mqtt_zweig_ohne_ha_abruf(db, ha_verbindung, monkeypatch):
    """Mit HA-Verbindung und leerer Zuordnung: der MQTT-Zweig, kein HA-Abruf.

    ⭐ Standalone-Gleichstand S4 (26.10.2026, Mischform) dreht diese Probe: bis dahin stand hier «leer ⇒ leer, weder
    MQTT- noch HA-Abruf — auch mit Snapshots» (die benannte Grenze von S3). Die Werte prüft
    ``test_standalone_s4_mischform.py``; hier bleibt die Weggabelung."""
    ha_verbindung("langlebiger-token")
    a, pv = await _anlage_pv(db, {})
    _leistung_snaps(db, a.id, pv.id, TAG)
    await db.commit()
    merker = _Merker()

    async def mqtt(*args, **kwargs):
        merker.mqtt += 1
        return {"serien": [], "punkte": []}

    async def ha(ids, start, end):
        merker.ha += 1
        return {}, {}

    monkeypatch.setattr(ltv, "_get_tagesverlauf_mqtt", mqtt)
    monkeypatch.setattr(ltv, "get_history_normalized", ha)

    assert await ltv.get_tagesverlauf(a, db, _tage_zurueck(TAG), mit_vortagsrand=True) == {"serien": [], "punkte": []}
    assert (merker.mqtt, merker.ha) == (1, 0)


def _nebenquellen_leer():
    """Wie test_408: Zähler-, LTS- und Preisquellen leer — verglichen wird nur, was die Kurve schreibt."""
    from backend.services.energie_profil._helpers import StrompreisStunden

    stack = ExitStack()
    for ziel, wert in (
        ("backend.services.snapshot.aggregator.snapshot_tagestabelle", None),
        ("backend.services.snapshot.lts_aggregator.lts_tagestabelle", None),
        ("backend.services.sensor_snapshot_service.get_daily_counter_deltas_by_inv", {}),
        ("backend.services.energie_profil._helpers._get_strompreis_stunden", StrompreisStunden(sensor={}, boerse={})),
    ):
        stack.enter_context(patch(ziel, new=AsyncMock(return_value=wert)))
    return stack


async def _aggregiert(db, mapping: dict) -> list[tuple]:
    from backend.services.energie_profil.aggregator import aggregate_day

    a, pv = await _anlage_pv(db, mapping(pv_id=None) if callable(mapping) else mapping)
    if callable(mapping):
        a.sensor_mapping = mapping(pv_id=pv.id)
    _leistung_snaps(db, a.id, pv.id, TAG)
    # MQTT-Energie-Anker im Fenster [Vortag, Folgetag) — ohne ihn hat die reine MQTT-Anlage keine Quelle (F-26).
    db.add(MqttEnergySnapshot(anlage_id=a.id, energy_key="netzbezug", value_kwh=100.0,
                              timestamp=datetime.combine(TAG, datetime.min.time()) - timedelta(hours=1)))
    await db.commit()
    with _nebenquellen_leer():
        erg = await aggregate_day(a, TAG, db, source=Source.SCHEDULER)
    assert erg is not None
    zeilen = (await db.execute(select(TagesEnergieProfil).where(TagesEnergieProfil.anlage_id == a.id)
                               .order_by(TagesEnergieProfil.stunde))).scalars().all()
    return [(z.stunde, z.pv_kw, z.netzbezug_kw,
             {k.replace(f"_{pv.id}", "_PV"): v for k, v in (z.komponenten or {}).items()}) for z in zeilen]


@pytest.mark.asyncio
async def test_aggregate_day_reine_mqtt_anlage_wie_mit_live_zuordnung(db, ha_verbindung):
    """Der Konsument der Antwort: dieselben Stundenzeilen wie die Standalone-Anlage mit `live`-Zuordnung (deren
    Kurve schon vorher aus dem MQTT-Zweig kam) — die reine MQTT-Anlage schrieb vorher nur die synthetischen Slots."""
    ha_verbindung(None)
    rein = await _aggregiert(db, {})
    mit_live = await _aggregiert(db, lambda pv_id: {
        "basis": {"live": {"netzbezug_w": "sensor.netzbezug"}},
        "investitionen": {str(pv_id): {"live": {"leistung_w": "sensor.pv"}}} if pv_id is not None else {},
    })

    assert rein == mit_live
    assert [s for s, _pv, _netz, k in rein if k.get("pv_PV")] == [11, 12], "Leistung 10–12 Uhr ⇒ Slots 11 und 12"


# ═══ S3-2 eine Mittelungsregel ════════════════════════════════════════════════

def test_fenster_gewicht_regel():
    assert fenster_gewicht(T0, None) == 1.0
    assert fenster_gewicht(T0 + 300, T0) == 1.0
    assert fenster_gewicht(T0 + 1800, T0) == 1.0, "eine Lücke davor zählt nicht als gemessene Zeit"
    assert fenster_gewicht(T0 + 270, T0) == pytest.approx(0.9)
    assert fenster_gewicht(T0, T0) == 0.0


def _modus_zeilen(fenster: dict[int, dict[str, float]], inv_id: int = 7) -> list[tuple]:
    return [(ts, f"inv:{inv_id}:betriebsmodus:{m}", a) for ts, je in fenster.items() for m, a in je.items()]


def _einfach(fenster: dict[int, dict[str, float]]) -> dict[str, float]:
    """Die Regel bis S3: einfaches Mittel der Fenster (Modus ohne Zeile zählt 0)."""
    summe: dict[str, float] = {}
    for je in fenster.values():
        for m, a in je.items():
            summe[m] = summe.get(m, 0.0) + a
    return {m: v / len(fenster) for m, v in summe.items()}


def test_volltakt_modus_gleich_dem_einfachen_mittel_bitgenau():
    """12 Fenster im 5-min-Takt ⇒ jedes Gewicht 1.0 ⇒ dieselben Zahlen wie das einfache Mittel (keine Zahländerung)."""
    anteile = [0.0, 0.2, 1.0, 0.7, 0.3333333333333333, 1.0, 0.1, 0.0, 0.9, 0.45, 0.6, 0.05]
    fenster = {T0 + 300 * i - 1: {HEIZEN: a, WARMWASSER: 1.0 - a} for i, a in enumerate(anteile, start=1)}
    fenster[T0 + 300 * 12 - 1] = {HEIZEN: 0.05}                       # Warmwasser ohne Zeile ⇒ 0 in diesem Fenster

    stunde, werte = modus_anteile_je_stunde(_modus_zeilen(fenster))[7][0]

    assert stunde == _stunden_start_ts(datetime.fromtimestamp(T0)) == T0
    assert werte == _einfach(fenster), "bitgleich, nicht nur ungefähr"


def test_volltakt_werte_gleich_dem_einfachen_mittel_bitgenau():
    werte = [1000.0, 0.0, 2000.0, 1234.567, 0.1, 333.3, 999.99, 5.0, 0.0, 1750.25, 2000.0, 12.5]
    zeilen = [(T0 + 300 * i - 1, w, None, None) for i, w in enumerate(werte, start=1)]

    (_s, mittel, lo, hi), = [z for z in mittel_je_stunde(zeilen) if z[0] == T0]

    assert mittel == sum(werte) / len(werte)
    assert (lo, hi) == (0.0, 2000.0)


def test_teilstunde_nach_neustart_modus_und_wert_mit_derselben_gewichtung():
    """Fenster 08:00–08:30 fehlen (eedc lief nicht), danach Volltakt: die Stunde ist das gewichtete Mittel der
    vorhandenen Fenster — für Modus und Wert mit denselben Gewichten (``fenster_gewicht``)."""
    vorhanden = [T0 + 1800 + 300 * i - 1 for i in range(1, 7)]        # Abschluss 08:34:59 … 08:59:59, sechs Fenster
    heizen = [1.0, 1.0, 0.5, 0.0, 0.0, 1.0]
    leistung = [2000.0, 2000.0, 1000.0, 0.0, 0.0, 2000.0]

    _s, modus = modus_anteile_je_stunde(_modus_zeilen({t: {HEIZEN: h} for t, h in zip(vorhanden, heizen)}))[7][0]
    (_s2, mittel, _lo, _hi), = [z for z in mittel_je_stunde([(t, w, None, None) for t, w in zip(vorhanden, leistung)])
                                if z[0] == T0]

    gewichte = [fenster_gewicht(t, v) for t, v in zip(vorhanden, [None] + vorhanden[:-1])]
    assert gewichte == [1.0] * 6, "nach der Lücke zählt jedes vorhandene Fenster voll, die Lücke selbst nicht"
    assert modus[HEIZEN] == pytest.approx(3.5 / 6)
    assert mittel == pytest.approx(7000.0 / 6)
    assert mittel / 2000.0 == pytest.approx(modus[HEIZEN]), "dieselbe Gewichtung für Modus und Wert"


def test_versetzter_takt_modus_jetzt_laengengewichtet_wie_die_werte():
    """Der Fall, in dem die beiden Regeln bis S3 auseinanderliefen: ein Snapshot läuft 30 s zu spät (der nächste
    wieder im Takt) — sein Nachfolger deckt nur 270 s. Modus und Wert gewichten ihn jetzt beide mit 0,9."""
    ts = [T0 + 300, T0 + 630, T0 + 900]                              # 08:05 · 08:10:30 · 08:15 (Abstand 300/330/270)
    heizen = [1.0, 1.0, 0.0]
    leistung = [2000.0, 2000.0, 0.0]

    _s, modus = modus_anteile_je_stunde(_modus_zeilen({t: {HEIZEN: h} for t, h in zip(ts, heizen)}))[7][0]
    (_s2, mittel, _lo, _hi), = [z for z in mittel_je_stunde([(t, w, None, None) for t, w in zip(ts, leistung)])
                                if z[0] == T0]

    assert fenster_gewicht(ts[2], ts[1]) == pytest.approx(270 / _SNAPSHOT_FENSTER)
    assert modus[HEIZEN] == pytest.approx(2.0 / 2.9), "längengewichtet (vorher einfach: 2/3)"
    assert mittel == pytest.approx(4000.0 / 2.9)
    assert mittel / 2000.0 == pytest.approx(modus[HEIZEN])


def test_vorgaenger_aus_der_vorstunde_traegt_die_gewichtung_ueber_den_stundenrand():
    """Die Fensterfolge eines Geräts läuft über die Stundengrenze — wie die Wertreihe eines Keys."""
    ts = [T0 + _STUNDE - 120, T0 + _STUNDE + 60]                      # 08:58 · 09:01 (Abstand 180 s)
    je = modus_anteile_je_stunde(_modus_zeilen({ts[0]: {HEIZEN: 1.0}, ts[1]: {HEIZEN: 0.0, WARMWASSER: 1.0}}))[7]
    werte = mittel_je_stunde([(ts[0], 1.0, None, None), (ts[1], 0.0, None, None)])

    assert [s for s, _ in je] == [s for s, *_ in werte] == [T0, T0 + _STUNDE]
    assert je[1][1] == {HEIZEN: 0.0, WARMWASSER: 1.0}
