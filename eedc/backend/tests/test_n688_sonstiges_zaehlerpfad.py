"""N-688: Sonstiges-Geräte — die Live-Tagesmenge (Energiefluss-Tooltip) liest den Zähler.

Standalone:

    eedc/backend/venv/bin/python -m pytest backend/tests/test_n688_sonstiges_zaehlerpfad.py -q

**Der Befund (Analyse 11.10.2026, `ANALYSE-NEBENFUNDE-RF4-RF6.md` §9).** Die
Zählerpfad-Tabelle `_MONATSABSCHLUSS_KWH` in `live_history_service` kannte nur
Wärmepumpe und Wallbox. Ein *Sonstiges*-Gerät mit Leistungssensor und kWh-Zähler
bekam in `get_tages_kwh` die **integrierte** Leistung (Trapez) — im Energiefluss-
Tooltip „heute X kWh", bei Abgabe-Geräten auch im Eigenverbrauch heute. Der
Tagesverlauf derselben Seite nahm seit N-261 den Zähler (`_resolve_counter_eid`),
dessen Docstring „deckungsgleich mit der Bevorzugung in `get_tages_kwh`" verspricht.

**Die Regel, die hier geprüft wird:** gleiche Impulskurve (2 × 15 min × 6 kW, Zähler-Δ
3,0 kWh) — Sonstiges = Zähler wie Wallbox; und je Kategorie nimmt `get_tages_kwh`
genau den Zähler, den `_resolve_counter_eid` für die Kurve nimmt.

Fakes an denselben Nähten wie der Golden Master RF-6: `get_history_normalized`,
`get_ha_statistics_service`, `live_history_service.datetime`; DB = In-Memory-SQLite
(`db`-Fixture), weil die Kategorie eines Sonstiges-Geräts in `Investition.parameter` steht.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from backend.services import live_history_service as L
from backend.services.live_tagesverlauf_service import _resolve_counter_eid
from backend.tests import factories

JETZT = datetime(2026, 3, 10, 14, 30, 0)

SO_W = "sensor.heizstab_w"
WB_W = "sensor.wallbox_w"
WB_KWH = "sensor.wallbox_kwh"
PV_KWH = "sensor.pv_kwh"
EINSP_KWH = "sensor.einsp_kwh"

#: je Sonstiges-Energiefeld ein eigener Zähler mit eigenem Tages-Δ — so ist sichtbar, WELCHER gelesen wurde
ZAEHLER = {
    "verbrauch_sonstig_kwh": ("sensor.so_verbrauch_kwh", 3.0),
    "verbrauch_kwh": ("sensor.so_legacy_kwh", 2.0),
    "erzeugung_kwh": ("sensor.so_erzeugung_kwh", 1.5),
    "abgabe_kwh": ("sensor.so_abgabe_kwh", 2.5),
}


class _Uhr(datetime):
    @classmethod
    def now(cls, tz=None):  # noqa: ARG003
        return JETZT


class _KeineStats:
    is_available = False


def _start() -> datetime:
    return JETZT.replace(hour=0, minute=0, second=0, microsecond=0)


def _p(*paare):
    return [(_start() + timedelta(minutes=m), v) for m, v in paare]


#: Impulslast: zwei 15-min-Impulse à 6 kW, der Sensor meldet nur Zustandswechsel —
#: das Trapez rampt über die Lücken und ergibt 6,75 kWh, gemessen sind 3,0.
IMPULS = _p((0, 0.0), (60, 6000.0), (75, 0.0), (120, 6000.0), (135, 0.0), (180, 0.0))


def _history() -> dict:
    h = {
        SO_W: list(IMPULS),
        WB_W: list(IMPULS),
        WB_KWH: _p((0, 10.0), (180, 13.0)),
        PV_KWH: _p((0, 7000.0), (240, 7009.0)),
        EINSP_KWH: _p((0, 1000.0), (240, 1004.0)),
    }
    for eid, delta in ZAEHLER.values():
        h[eid] = _p((0, 100.0), (180, 100.0 + delta))
    return h


def _units(eid: str) -> str:
    return "kWh" if eid.endswith("_kwh") else "W"


def _s(eid: str) -> dict:
    return {"strategie": "sensor", "sensor_id": eid}


@pytest.fixture
def fakes(monkeypatch):
    import backend.services.ha_statistics_service as hss

    h_voll = _history()

    async def fake_hist(entity_ids, s, e):  # noqa: ARG001
        return (
            {k: list(h_voll[k]) for k in entity_ids if k in h_voll},
            {k: _units(k) for k in entity_ids},
        )

    monkeypatch.setattr(L, "get_history_normalized", fake_hist)
    monkeypatch.setattr(L, "datetime", _Uhr)
    monkeypatch.setattr(hss, "get_ha_statistics_service", lambda: _KeineStats())


async def _anlage_mit_sonstiges(db, *, kategorie, felder: tuple[str, ...], quellen: dict | None = None):
    a = await factories.anlage(db, sensor_mapping={})
    so = await factories.investition(
        db, a.id, "sonstiges", bezeichnung="Heizstab",
        parameter=({"kategorie": kategorie} if kategorie is not None else {}),
    )
    wb = await factories.investition(db, a.id, "wallbox", bezeichnung="Wallbox")
    mapping = {
        "basis": {"pv_gesamt": _s(PV_KWH), "einspeisung": _s(EINSP_KWH)},
        "investitionen": {
            str(so.id): {"live": {"leistung_w": SO_W},
                         "felder": {f: _s(ZAEHLER[f][0]) for f in felder}},
            str(wb.id): {"live": {"leistung_w": WB_W}, "felder": {"ladung_kwh": _s(WB_KWH)}},
        },
    }
    if quellen:
        mapping["quellen"] = quellen
    a.sensor_mapping = mapping
    await db.flush()
    return a, so, wb


def _trapez() -> float:
    return round(L.trapez_kwh(list(IMPULS)), 1)


# ── Gleiche Impulskurve: Sonstiges = Zähler wie Wallbox ───────────────────────


async def test_sonstiges_mit_zaehler_wie_wallbox(db, fakes):
    """Der Defekt: Sonstiges bekam das Trapez (6,75), die Wallbox daneben den Zähler (3,0)."""
    a, so, wb = await _anlage_mit_sonstiges(db, kategorie="verbraucher", felder=("verbrauch_sonstig_kwh",))
    r = await L.get_tages_kwh(a, db, 0)
    assert r.get(f"wallbox_{wb.id}") == 3.0, r
    assert r.get(f"sonstige_{so.id}") == 3.0, (
        f"N-688: Zähler zugeordnet ⇒ Sonstiges liest ihn wie die Wallbox (Trapez wäre {_trapez()}). War: {r!r}"
    )


async def test_sonstiges_mit_durchgereichten_typen_und_investitionen(db, fakes):
    """Produktionsweg (`live_power_service`): Typen und Investitionen kommen vom Aufrufer."""
    a, so, wb = await _anlage_mit_sonstiges(db, kategorie="verbraucher", felder=("verbrauch_sonstig_kwh",))
    invs = [so, wb]
    r = await L.get_tages_kwh(
        a, db, 0, inv_types={str(i.id): i.typ for i in invs}, erzeuger=invs,
    )
    assert r.get(f"sonstige_{so.id}") == 3.0, r


async def test_sonstiges_gestern(db, fakes):
    a, so, _ = await _anlage_mit_sonstiges(db, kategorie=None, felder=("verbrauch_sonstig_kwh",))
    r = await L.get_tages_kwh(a, db, 1)
    assert r.get(f"sonstige_{so.id}") == 3.0, r


# ── Deckungsgleich mit `_resolve_counter_eid` (Kurve) je Kategorie ─────────────


@pytest.mark.parametrize(
    "kategorie, felder",
    [
        ("verbraucher", ("verbrauch_sonstig_kwh", "verbrauch_kwh", "erzeugung_kwh")),
        (None, ("verbrauch_sonstig_kwh", "verbrauch_kwh", "erzeugung_kwh")),
        (None, ("verbrauch_kwh",)),                         # Legacy-Zwilling allein
        ("erzeuger", ("verbrauch_sonstig_kwh", "erzeugung_kwh")),
        ("abgabe", ("abgabe_kwh", "verbrauch_sonstig_kwh")),
        ("zaehler", ("verbrauch_sonstig_kwh",)),            # Zähler-Kategorie: keine Energie-Felder
    ],
    ids=["verbraucher", "ohne-kategorie", "legacy", "erzeuger", "abgabe", "zaehler-kategorie"],
)
async def test_gleicher_zaehler_wie_die_kurve(db, fakes, kategorie, felder):
    a, so, _ = await _anlage_mit_sonstiges(db, kategorie=kategorie, felder=felder)
    inv_felder = a.sensor_mapping["investitionen"][str(so.id)]["felder"]
    kurven_eid = _resolve_counter_eid("sonstiges", None, inv_felder, so.parameter)
    erwartet = (
        next(d for eid, d in ZAEHLER.values() if eid == kurven_eid) if kurven_eid is not None else _trapez()
    )
    r = await L.get_tages_kwh(a, db, 0)
    assert r.get(f"sonstige_{so.id}") == erwartet, (
        f"Kachel und Kurve lesen verschiedene Quellen: Kurve {kurven_eid!r} (Δ {erwartet}), Kachel {r!r}"
    )


# ── Folge im Eigenverbrauch, Rückfälle ───────────────────────────────────────


async def test_abgabe_geraet_eigenverbrauch_heute_aus_dem_zaehler(db, fakes):
    """Abgabe-Geräte gehen vom Eigenverbrauch ab — mit der gezählten Menge, nicht der integrierten."""
    from backend.services.live_power_service import LivePowerService

    a, so, _ = await _anlage_mit_sonstiges(db, kategorie="abgabe", felder=("abgabe_kwh",))
    r = await L.get_tages_kwh(a, db, 0)
    ev, _hv = LivePowerService._calc_tages_ev_hv(r, frozenset({f"sonstige_{so.id}"}))
    assert ev == round(9.0 - 4.0 - 2.5, 1), (r, ev)


async def test_sonstiges_ohne_zaehler_bleibt_beim_trapez(db, fakes):
    """Positivkontrolle: nur Leistung ⇒ Trapez wie bisher."""
    a, so, _ = await _anlage_mit_sonstiges(db, kategorie="verbraucher", felder=())
    r = await L.get_tages_kwh(a, db, 0)
    assert r.get(f"sonstige_{so.id}") == _trapez(), r


async def test_sonstiges_zaehler_mit_quelle_keine_bleibt_beim_trapez(db, fakes):
    """C2b: steht die Energie-Quelle des Zählers auf „keine", wird er nicht gelesen (wie bei WP/Wallbox)."""
    a, so, _ = await _anlage_mit_sonstiges(db, kategorie="verbraucher", felder=("verbrauch_sonstig_kwh",))
    a.sensor_mapping = {
        **a.sensor_mapping,
        "quellen": {f"inv_energy_{so.id}_verbrauch_sonstig_kwh": {"quelle": "keine"}},
    }
    r = await L.get_tages_kwh(a, db, 0)
    assert r.get(f"sonstige_{so.id}") == _trapez(), r
