"""N-687: ein zugeordneter Kombi-Netzsensor überschreibt die Netz-Zähler nicht mehr.

Standalone:

    eedc/backend/venv/bin/python -m pytest backend/tests/test_n687_kombi_zaehler_vorrang.py -q

**Der Befund (Analyse 11.10.2026, `ANALYSE-NEBENFUNDE-RF4-RF6.md` §8).** In
`get_tages_kwh` schrieb `_kategorien_kwh` für Einspeisung und Netzbezug zuerst den
Zählerwert (Priorität 1) — und danach überschrieb der Kombi-Netzsensor
(`netz_kombi_w`, + Bezug / − Einspeisung) beide mit dem Trapez seiner Leistung.
Der Zähler gewann also nur, wenn **kein** oder ein **getrennter** Live-Netzsensor
zugeordnet war. Cockpit → Live heute/gestern zeigte Einspeisung, Netzbezug, Eigen-
und Hausverbrauch aus der Leistungsintegration, Cockpit → Tag die Zähler —
dieselbe Zuordnung, zwei Zahlen. Die Regel seit v3.19.0 (#135): kWh aus Zählern,
nicht aus Leistungsintegration.

**Die Regel, die hier geprüft wird:** Sind Netz-Zähler zugeordnet und liefern sie,
tragen sie die Tagesmengen — gleich, in welcher Form der Live-Netzsensor
zugeordnet ist. Der Kombi-Sensor füllt nur die Richtung, für die kein Zähler
liefert, und bleibt für Leistung und Kurvenform (Tagesverlauf, LTS-Stundenkurve)
zuständig — die liefern keine Mengen und werden hier nur festgehalten.

Fakes an denselben Nähten wie der Golden Master RF-6
(`~/.claude/plans/skript-golden-master-live-tages-kwh.py`): `get_history_normalized`,
`get_ha_statistics_service`, `live_history_service.datetime`.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta

import pytest

from backend.services import live_history_service as L

JETZT = datetime(2026, 3, 10, 14, 30, 0)

KOMBI = "sensor.netz_kombi_w"
EINSP_W = "sensor.einsp_w"
BEZUG_W = "sensor.bezug_w"
EINSP_KWH = "sensor.einsp_kwh"
BEZUG_KWH = "sensor.bezug_kwh"
PV_KWH = "sensor.pv_kwh"


class _Uhr(datetime):
    @classmethod
    def now(cls, tz=None):  # noqa: ARG003
        return JETZT


class _Stats:
    """`ha_statistics_service`-Fake: Tabelle {eid: (start, ende)} oder nicht verfügbar."""

    def __init__(self, tabelle: dict | None):
        self.is_available = tabelle is not None
        self._t = tabelle or {}
        self._start: datetime | None = None

    def get_value_at(self, eid, ts, toleranz_minuten=60, short_term=False):  # noqa: ARG002
        werte = self._t.get(eid)
        if werte is None:
            return None
        if self._start is None:
            self._start = ts
        return werte[0] if ts == self._start else werte[1]


def _tagesstart(tage_zurueck: int) -> datetime:
    return (JETZT - timedelta(days=tage_zurueck)).replace(hour=0, minute=0, second=0, microsecond=0)


def _p(start: datetime, *paare):
    return [(start + timedelta(minutes=m), v) for m, v in paare]


def _history(start: datetime) -> dict:
    """Zähler: Einspeisung Δ 4,1, Netzbezug Δ 1,6, PV Δ 9,0 — das Kombi-Trapez ergibt grob 2,0 / 0,3."""
    return {
        KOMBI: _p(start, (0, 250.0), (60, -800.0), (120, -1200.0), (180, 300.0)),
        EINSP_W: _p(start, (0, 0.0), (60, 500.0), (120, 1000.0), (180, 100.0)),
        BEZUG_W: _p(start, (0, 300.0), (90, 100.0), (200, 450.0)),
        EINSP_KWH: _p(start, (0, 1000.0), (240, 1004.1)),
        BEZUG_KWH: _p(start, (0, 500.0), (240, 501.6)),
        PV_KWH: _p(start, (0, 7000.0), (240, 7009.0)),
    }


_UNITS = {KOMBI: "W", EINSP_W: "W", BEZUG_W: "W", EINSP_KWH: "kWh", BEZUG_KWH: "kWh", PV_KWH: "kWh"}


def _zaehler(*, einspeisung: bool = True, netzbezug: bool = True, pv: bool = False) -> dict:
    basis: dict = {}
    if einspeisung:
        basis["einspeisung"] = {"strategie": "sensor", "sensor_id": EINSP_KWH}
    if netzbezug:
        basis["netzbezug"] = {"strategie": "sensor", "sensor_id": BEZUG_KWH}
    if pv:
        basis["pv_gesamt"] = {"strategie": "sensor", "sensor_id": PV_KWH}
    return basis


class _Anlage:
    def __init__(self, basis: dict, live: dict):
        self.id = 1
        self.sensor_mapping = {"basis": {**basis, "live": live}, "investitionen": {}}


def _lauf(monkeypatch, anlage, *, tage: int = 0, history: dict | None = None, stats: dict | None = None):
    import backend.services.ha_statistics_service as hss

    start = _tagesstart(tage)
    h_voll = history if history is not None else _history(start)

    async def fake_hist(entity_ids, s, e):  # noqa: ARG001
        return (
            {k: list(h_voll[k]) for k in entity_ids if k in h_voll},
            {k: _UNITS[k] for k in entity_ids if k in _UNITS},
        )

    fake_stats = _Stats(stats)
    monkeypatch.setattr(L, "get_history_normalized", fake_hist)
    monkeypatch.setattr(L, "datetime", _Uhr)
    monkeypatch.setattr(hss, "get_ha_statistics_service", lambda: fake_stats)
    return asyncio.run(L.get_tages_kwh(anlage, db=None, tage_zurueck=tage, inv_types={}, erzeuger=[]))


def _kombi_trapez(start: datetime) -> tuple[float, float]:
    pts = _history(start)[KOMBI]
    bezug = L.trapez_kwh([(t, max(v, 0)) for t, v in pts])
    einsp = L.trapez_kwh([(t, abs(min(v, 0))) for t, v in pts])
    return round(einsp, 1), round(bezug, 1)


# ── get_tages_kwh (Cockpit → Live, Kacheln heute/gestern) ─────────────────────


@pytest.mark.parametrize("tage", [0, 1], ids=["heute", "gestern"])
def test_kombi_und_zaehler_der_zaehler_traegt_die_tagesmenge(monkeypatch, tage):
    """Der Defekt: Kombi + Zähler ⇒ bis N-687 kam das Kombi-Trapez (2,0 / 0,3) heraus."""
    r = _lauf(monkeypatch, _Anlage(_zaehler(), {"netz_kombi_w": KOMBI}), tage=tage)
    assert (r.get("einspeisung"), r.get("netzbezug")) == (4.1, 1.6), (
        "N-687: Netz-Zähler zugeordnet ⇒ sie liefern Einspeisung/Netzbezug, der Kombi-"
        f"Leistungssensor nicht (Kombi-Trapez wäre {_kombi_trapez(_tagesstart(tage))}). War: {r!r}"
    )


def test_kombi_und_zaehler_ueber_statistics(monkeypatch):
    """Derselbe Vorrang, wenn der Zählerwert aus HA-Statistics `sum` kommt (#200-Weg)."""
    r = _lauf(
        monkeypatch, _Anlage(_zaehler(), {"netz_kombi_w": KOMBI}),
        stats={EINSP_KWH: (1000.0, 1005.5), BEZUG_KWH: (500.0, 500.7)},
    )
    assert (r.get("einspeisung"), r.get("netzbezug")) == (5.5, 0.7), r


def test_kombi_und_nur_ein_zaehler_kombi_fuellt_die_andere_richtung(monkeypatch):
    """Nur der Bezugszähler ist zugeordnet: Bezug vom Zähler, Einspeisung weiter vom Kombi-Sensor."""
    r = _lauf(monkeypatch, _Anlage(_zaehler(einspeisung=False), {"netz_kombi_w": KOMBI}))
    einsp_kombi, _ = _kombi_trapez(_tagesstart(0))
    assert r.get("netzbezug") == 1.6, r
    assert r.get("einspeisung") == einsp_kombi, r


def test_kombi_und_zaehler_ohne_zaehlerdaten_kombi_ist_der_rueckfall(monkeypatch):
    """Zähler zugeordnet, liefert aber nichts (nicht in der History, keine Statistics) ⇒ Kombi-Trapez."""
    start = _tagesstart(0)
    h = {k: v for k, v in _history(start).items() if k not in (EINSP_KWH, BEZUG_KWH)}
    r = _lauf(monkeypatch, _Anlage(_zaehler(), {"netz_kombi_w": KOMBI}), history=h)
    assert (r.get("einspeisung"), r.get("netzbezug")) == _kombi_trapez(start), r


def test_nur_kombi_bleibt_beim_trapez(monkeypatch):
    """Positivkontrolle: ohne Zähler ändert sich am Kombi-Weg nichts."""
    r = _lauf(monkeypatch, _Anlage({}, {"netz_kombi_w": KOMBI}))
    assert (r.get("einspeisung"), r.get("netzbezug")) == _kombi_trapez(_tagesstart(0)), r


def test_nur_zaehler_ohne_live_netzsensor(monkeypatch):
    """Positivkontrolle: Zähler ohne jeden Live-Netzsensor ⇒ Zähler."""
    r = _lauf(monkeypatch, _Anlage(_zaehler(), {}))
    assert (r.get("einspeisung"), r.get("netzbezug")) == (4.1, 1.6), r


def test_getrennte_w_und_zaehler(monkeypatch):
    """Positivkontrolle: getrennte W-Sensoren + Zähler ⇒ Zähler (so war es schon vor N-687)."""
    r = _lauf(monkeypatch, _Anlage(_zaehler(), {"einspeisung_w": EINSP_W, "netzbezug_w": BEZUG_W}))
    assert (r.get("einspeisung"), r.get("netzbezug")) == (4.1, 1.6), r


def test_kombi_und_zaehler_eigen_und_hausverbrauch_aus_den_zaehlern(monkeypatch):
    """Die Folge in der Kachel: Eigen- und Hausverbrauch entstehen aus den Zählerwerten."""
    from backend.services.live_power_service import LivePowerService

    r = _lauf(monkeypatch, _Anlage(_zaehler(pv=True), {"netz_kombi_w": KOMBI}))
    ev, hv = LivePowerService._calc_tages_ev_hv(r)
    assert (ev, hv) == (round(9.0 - 4.1, 1), round(9.0 - 4.1 + 1.6, 1)), (r, ev, hv)


# ── Schwesterpfade: Kurvenform bleibt beim Leistungssensor (keine Mengen) ─────


def test_tagesverlauf_kombi_und_zaehler_kurve_bleibt_beim_kombi_sensor(monkeypatch):
    """`live_tagesverlauf_service._baue_short_term_overlays`: liefert Kurven (kW), keine kWh.

    Bei Kombi + Zähler speist der Kombi-Sensor die Kurve (Mean-Overlay); die Zähler werden
    für die Kurve nicht abgefragt — die Tagesmenge der Kacheln kommt seit N-687 trotzdem aus
    den Zählern (Tests oben).
    """
    import backend.services.ha_statistics_service as hss
    from backend.services import live_tagesverlauf_service as TV

    abgefragt: list = []

    class _St:
        is_available = True

        def get_short_term_5min_for_day(self, ids, tag, bis=None):  # noqa: ARG002
            abgefragt.extend(ids)
            return {}

    monkeypatch.setattr(hss, "get_ha_statistics_service", lambda: _St())
    anlage = _Anlage(_zaehler(), {"netz_kombi_w": KOMBI})
    start = _tagesstart(0)
    mean_ov, counter_ov = TV._baue_short_term_overlays(
        anlage, [], {}, {}, None, None, None, KOMBI, start, JETZT, {},
    )
    assert sorted(abgefragt) == [KOMBI], abgefragt
    assert (mean_ov, counter_ov) == ({}, {})


def test_lts_stundenkurve_kombi_bleibt_beim_kombi_sensor():
    """`lts_tagesverlauf._stunden_werte`: Stunden-Leistung (kW) aus dem Kombi-Sensor, keine kWh."""
    from backend.services.energie_profil.lts_tagesverlauf import _stunden_werte

    hourly = {KOMBI: {"2026-03-10": {12: -1.25}}}
    werte = _stunden_werte(hourly, {}, [], "2026-03-10", 12, KOMBI, None, None)
    assert werte == {"netz": -1.25}, werte


# ── Datenquellen-Fläche: Kombi UND Zähler ist erlaubt ─────────────────────────


def test_validierung_kombi_und_zaehler_ist_kein_hinweis():
    """Kombi + kWh-Zähler: keine Redundanz-Warnung (nur Kombi + getrennte W-Sensoren ist redundant)."""
    from backend.services.datenquellen_validierung import finde_redundante_aggregate

    felder = [
        {"id": "basis_live_netz_kombi_w", "feld": "netz_kombi_w", "typ": "basis", "belegt": True, "hat_wert": True},
        {"id": "basis_energy_einspeisung_kwh", "feld": "einspeisung_kwh", "typ": "basis",
         "belegt": True, "hat_wert": True},
        {"id": "basis_energy_netzbezug_kwh", "feld": "netzbezug_kwh", "typ": "basis",
         "belegt": True, "hat_wert": True},
        {"id": "basis_live_einspeisung_w", "feld": "einspeisung_w", "typ": "basis", "belegt": False},
        {"id": "basis_live_netzbezug_w", "feld": "netzbezug_w", "typ": "basis", "belegt": False},
    ]
    assert finde_redundante_aggregate(felder) == {}
