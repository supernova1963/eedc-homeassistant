"""
S3 (Symmetrie) + K3 (Konformität) — Phase C v3.35.0, Issue #298.

Hintergrund (Audit-§6.2, Pattern-Klasse [[feedback_aggregator_symmetrie]]):
Der Daily-Pfad (`get_komponenten_tageskwh{,_lts}`) routet seit v3.33.0 über
`komponenten_beitraege.investition_beitraege` (Whitelist + Either-Or +
parent-Skip). Die beiden Hourly-Aggregatoren riefen dagegen bis v3.34.x
`keys._categorize_counter` ROH pro gemapptem Feld auf — die Either-Or-Auswahl
fehlte. Ein E-Auto mit BEIDEN Gesamt-Zählern (`verbrauch_kwh` UND `ladung_kwh`,
evcc/junky84 #262) wurde dadurch in der Stunden-Bilanz doppelt gezählt, im
Tages-Aggregat aber nur einfach → stille Drift zwischen Stunden- und Tagestab.

Phase C stellt beide Hourly-Aggregatoren auf dieselbe Normalisierung um
(`*_hourly_eintraege`). Diese Tests pinnen das strukturell:

  S3  — Σ über die 24 Hourly-Slots == Tages-Boundary (für jede Per-Typ-
        Konstellation). Bricht ohne die Phase-C-Migration für den
        Doppelmapping-Fall.
  K3  — Die Hourly-Normalisierung ist eine FAITHFUL PROJECTION des Daily-SoT:
        identische Feld-/Either-Or-Gruppen-Menge, parent-Skip identisch,
        kein Feld ohne Energiefluss-Kategorie. Damit kann der Hourly-Pfad nicht
        wieder gegen den Daily-Pfad driften (kein roher Kategorisierer mehr).
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import patch, MagicMock

import pytest

from backend.models.sensor_snapshot import SensorSnapshot
from backend.services.snapshot.aggregator import (
    get_hourly_kwh_by_category,
    get_komponenten_tageskwh,
)
from backend.services.snapshot.lts_aggregator import (
    get_hourly_kwh_by_category_lts,
    get_komponenten_tageskwh_lts,
)
from backend.services.snapshot.reaggregator import get_reaggregate_preview
from backend.services.snapshot.komponenten_beitraege import (
    investition_beitraege,
    investition_hourly_eintraege,
)
from backend.services.snapshot.keys import KUMULATIVE_ZAEHLER_FELDER

# Setups + Mock-Helper aus dem Daily-Symmetrie-Test wiederverwenden — exakt
# dieselben Eingangs-Konstellationen, jetzt auf den Hourly-Pfad angewandt.
from backend.tests.test_aggregator_symmetrie import (
    SETUPS,
    _make_anlage,
    _make_inv,
    _build_mock_ha_svc,
    _sensor,
    _sensor_key_for_feld,
)


# ─── Daily-Komponenten-Dict → Hourly-Energiefluss-Felder falten ─────────────


def _fold_daily_to_flow(daily: dict, invs: dict) -> dict[str, float]:
    """Faltet das Komponenten-Key-Tagesdict auf die Energiefluss-Felder, die
    der Hourly-Aggregator summiert. Anker für „Σ Hourly == Daily"."""
    flow = {
        "pv": 0.0, "einspeisung": 0.0, "netzbezug": 0.0,
        "batterie_netto": 0.0, "wp": 0.0, "wallbox": 0.0,
        "verbrauch_sonstiges": 0.0,
    }
    for key, val in daily.items():
        if key == "einspeisung":
            flow["einspeisung"] += val
        elif key == "netzbezug":
            flow["netzbezug"] += val
        elif key.startswith("pv_") or key.startswith("bkw_"):
            flow["pv"] += val
        elif key.startswith("batterie_"):
            # komponenten[batterie_*] ist Spalten-Konvention (Entladung positiv);
            # das Hourly-Flussfeld `batterie_netto` ist Bilanz-Netto (Ladung
            # positiv). Beim Falten negieren, damit Σ Hourly == Daily gilt.
            flow["batterie_netto"] += -val
        elif key.startswith("waermepumpe_"):
            flow["wp"] += val
        elif key.startswith("wallbox_") or key.startswith("eauto_"):
            flow["wallbox"] += val
        elif key.startswith("sonstige_"):
            inv_id = key.split("_", 1)[1]
            inv = invs.get(inv_id) or invs.get(str(inv_id))
            kateg = (getattr(inv, "parameter", {}) or {}).get("kategorie", "verbraucher")
            if kateg == "erzeuger":
                flow["pv"] += val          # Sonstiges-Erzeuger → pv_total
            else:
                flow["verbrauch_sonstiges"] += val
    return flow


def _sum_hourly_flow(hourly: dict[int, dict]) -> dict[str, float]:
    """Σ über die 24 Stunden-Dicts pro Energiefluss-Feld (None → 0)."""
    felder = ("pv", "einspeisung", "netzbezug", "batterie_netto",
              "wp", "wallbox", "verbrauch_sonstiges")
    out = {f: 0.0 for f in felder}
    for h in range(24):
        d = hourly.get(h, {})
        for f in felder:
            out[f] += d.get(f) or 0.0
    return out


# ─── S3: Σ LTS-Hourly == Daily (über ALLE Setups) ───────────────────────────
#
# Der LTS-Delta-Lieferant (`get_hourly_kwh_deltas_for_day`) ist forward
# (Slot h = Energie [H, H+1)), daher Σ der 24 Slots == Tagesfenster. Das gilt
# für alle Setups, auch ranged-deltas — anders als der Backward-Snapshot-Pfad
# (siehe S3-Snapshot unten, der window-deckungsgleiche Deltas braucht).


@pytest.mark.parametrize("setup_name", list(SETUPS.keys()))
async def test_s3_lts_hourly_summe_gleich_daily(setup_name):
    sm, invs, deltas, _sk_map = SETUPS[setup_name]()
    anlage = _make_anlage(sm)
    datum = date(2026, 5, 22)

    mock_svc = _build_mock_ha_svc(deltas)
    with patch(
        "backend.services.snapshot.lts_aggregator.get_ha_statistics_service",
        return_value=mock_svc,
    ):
        # LTS-Hourly nimmt `db` als ersten Arg (ungenutzt — Read läuft über
        # ha_svc); Daily-LTS nicht.
        hourly = await get_hourly_kwh_by_category_lts(MagicMock(), anlage, invs, datum)
        daily = await get_komponenten_tageskwh_lts(anlage, invs, datum)

    flow_hourly = _sum_hourly_flow(hourly)
    flow_daily = _fold_daily_to_flow(daily, invs)

    for f in flow_daily:
        assert abs(flow_hourly[f] - flow_daily[f]) < 0.01, (
            f"[{setup_name}] {f}: Σ Hourly-LTS={flow_hourly[f]:.3f} "
            f"vs Daily={flow_daily[f]:.3f}\n  hourly={flow_hourly}\n  daily={flow_daily}"
        )


# ─── S3-Snapshot: Doppelmapping-Fall durch den Snapshot-Hourly-Pfad ─────────
#
# Der Snapshot-Pfad liest Boundary-Snapshots (backward, Slot h = [h-1, h)).
# Mit einem kumulativen Mock und window-deckungsgleichen Deltas (Energie nur
# in Stunden 0..22, h23=0 — im Setup `eauto_verbrauch_und_ladung` erfüllt)
# gilt Σ der Backward-Slots == Tagesfenster, sodass derselbe „Σ == Daily"-
# Anker greift.


def _build_hourly_snapshot_lookup(deltas, sk_map, datum):
    """Kumulativer get_snapshot-Mock: Counter bei Boundary-Offset o (= Heute
    o:00) = Σ deltas[0..o-1]. o<=0 (Vortag 23:00 / Heute 00:00) → 0."""
    tag0 = datetime.combine(datum, datetime.min.time())

    async def fake_get_snapshot(db, anlage_id, sensor_key, sensor_id, zeitpunkt, *a, **k):
        sid = sk_map.get(sensor_key)
        if sid is None:
            return None
        D = deltas.get(sid, {})
        o = round((zeitpunkt - tag0).total_seconds() / 3600.0)
        if o <= 0:
            return 0.0
        return sum(D.get(i, 0.0) for i in range(o))

    return fake_get_snapshot


async def _empty_mqtt_db():
    """MagicMock-db, dessen mqtt_energy_snapshots-Query leer ist."""
    db = MagicMock()
    result = MagicMock()
    result.all.return_value = []
    async def _execute(*a, **k):
        return result
    db.execute = _execute
    return db


@pytest.mark.parametrize("setup_name", ["eauto_verbrauch_und_ladung"])
async def test_s3_snapshot_hourly_kein_doppelmapping(setup_name):
    """Der Snapshot-Hourly-Pfad zählt das doppelt gemappte E-Auto NICHT doppelt:
    Σ Hourly-`wallbox` == Daily-`eauto_<id>` (Either-Or, primary `ladung_kwh`)."""
    sm, invs, deltas, sk_map = SETUPS[setup_name]()
    anlage = _make_anlage(sm)
    datum = date(2026, 5, 22)
    db = await _empty_mqtt_db()

    fake_snap = _build_hourly_snapshot_lookup(deltas, sk_map, datum)
    with patch(
        "backend.services.snapshot.aggregator.get_snapshot",
        side_effect=fake_snap,
    ):
        hourly = await get_hourly_kwh_by_category(
            db=db, anlage=anlage, investitionen_by_id=invs, datum=datum,
        )
        daily = await get_komponenten_tageskwh(
            db=db, anlage=anlage, investitionen_by_id=invs, datum=datum,
        )

    flow_hourly = _sum_hourly_flow(hourly)
    flow_daily = _fold_daily_to_flow(daily, invs)

    # Kern-Invariante (#298): Σ Hourly-wallbox == Daily-eauto, nicht das Doppelte.
    assert abs(flow_hourly["wallbox"] - flow_daily["wallbox"]) < 0.01, (
        f"Snapshot-Hourly wallbox={flow_hourly['wallbox']:.3f} "
        f"vs Daily={flow_daily['wallbox']:.3f} (Doppelmapping nicht aufgelöst?)"
    )
    # ladung_kwh ist primary → 23.0 (nicht 23.0+20.7=43.7).
    assert abs(flow_hourly["wallbox"] - 23.0) < 0.01, flow_hourly


# ─── K3: Hourly-Normalisierung ist faithful projection des Daily-SoT ────────


def _voll_gemappte_felder(typ: str) -> dict:
    """sensor_mapping-`felder`-Dict mit ALLEN kumulativen Zähler-Feldern des
    Typs gemappt (maximale Doppelmapping-Oberfläche)."""
    felder = KUMULATIVE_ZAEHLER_FELDER.get(typ, ())
    return {feld: _sensor(f"sensor.{typ}_{feld}") for feld in felder}


# Repräsentative Parameter pro Typ (getrennte WP + beide Sonstiges-Kategorien
# erzeugen die meisten parallelen Felder).
_K3_FAELLE = [
    ("pv-module", {}, None),
    ("balkonkraftwerk", {}, None),
    ("speicher", {}, None),
    ("waermepumpe", {}, None),
    ("waermepumpe", {"getrennte_strommessung": True}, None),
    ("wallbox", {}, None),
    ("e-auto", {}, None),                       # ladung_kwh + verbrauch_kwh → Either-Or
    ("e-auto", {}, 2),                          # parent → Skip
    ("sonstiges", {"kategorie": "verbraucher"}, None),
    ("sonstiges", {"kategorie": "erzeuger"}, None),
]


@pytest.mark.parametrize("typ,parameter,parent", _K3_FAELLE)
def test_k3_hourly_ist_faithful_projection_von_daily(typ, parameter, parent):
    inv = _make_inv(1, typ, parameter=parameter, parent_investition_id=parent)
    inv_data = {"felder": _voll_gemappte_felder(typ)}

    daily = investition_beitraege(inv, inv_data)
    hourly = investition_hourly_eintraege(inv, inv_data)

    # 1. Identische Feld-/Either-Or-Gruppen-Menge — Hourly darf nicht mehr
    #    oder weniger Felder zählen als der Daily-SoT, und die Either-Or-
    #    Gruppierung muss identisch sein.
    daily_set = {(b.feld, b.fallback_gruppe) for b in daily}
    hourly_set = {(he.feld, he.fallback_gruppe) for he in hourly}
    assert hourly_set == daily_set, (
        f"[{typ} parameter={parameter} parent={parent}] Hourly-Normalisierung "
        f"weicht vom Daily-SoT ab:\n  daily={sorted(daily_set)}\n  hourly={sorted(hourly_set)}"
    )

    # 2. Jeder Hourly-Eintrag hat eine (nicht-None) Energiefluss-Kategorie.
    for he in hourly:
        assert he.kategorie, f"[{typ}] {he.feld} ohne Kategorie"


def test_k3_parent_skip_identisch_daily_und_hourly():
    """E-Auto mit parent_investition_id → KEINE Einträge in beiden Pfaden
    (Wallbox misst bereits; spiegelt Live-/Daily-Pfad)."""
    inv = _make_inv(1, "e-auto", parent_investition_id=2)
    inv_data = {"felder": _voll_gemappte_felder("e-auto")}
    assert investition_beitraege(inv, inv_data) == []
    assert investition_hourly_eintraege(inv, inv_data) == []


async def test_s3_reaggregator_preview_kein_doppelmapping(db):
    """#298 dritter Roh-Konsument: die Reload-Vorschau (`get_reaggregate_preview`,
    „Tag neu berechnen") summierte ein doppelt gemapptes E-Auto verdoppelt in
    `tagesumme_alt`/`_neu`. Nach der Phase-C-Migration löst die Either-Or-
    Auflösung pro Spalte das auf — der Vorschau-Wert ist deckungsgleich mit dem
    späteren Reload-Schreibwert (sonst „Vorschau sagt 69, Ergebnis 39")."""
    datum = date(2026, 5, 22)
    tag0 = datetime.combine(datum, datetime.min.time())

    # Kumulative DB-Snapshots (alt-Spalte): ladung_kwh primary 2.0/h, verbrauch
    # 1.0/h, beide nur Stunden 0..22 (h23=0). C(h) = Σ delta[0..h-1].
    dl = {i: (2.0 if i < 23 else 0.0) for i in range(24)}
    dv = {i: (1.0 if i < 23 else 0.0) for i in range(24)}
    for sk, deltas in (("inv:1:ladung_kwh", dl), ("inv:1:verbrauch_kwh", dv)):
        for h in range(-1, 24):
            c = sum(deltas[i] for i in range(0, h)) if h > 0 else 0.0
            db.add(SensorSnapshot(
                anlage_id=1, sensor_key=sk, zeitpunkt=tag0 + timedelta(hours=h),
                wert_kwh=c, quelle="test",
            ))
    await db.commit()

    anlage = SimpleNamespace(
        id=1, anlagenname="Reagg298", leistung_kwp=1000.0,
        sensor_mapping={"basis": {}, "investitionen": {"1": {"felder": {
            "ladung_kwh": _sensor("sensor.ea_l"),
            "verbrauch_kwh": _sensor("sensor.ea_v"),
        }}}},
    )
    invs = {"1": _make_inv(1, "e-auto")}

    svc = MagicMock()
    svc.is_available = False  # neu-Spalte leer → Fokus auf alt-Spalte
    with patch(
        "backend.services.snapshot.reaggregator.get_ha_statistics_service",
        return_value=svc,
    ):
        prev = await get_reaggregate_preview(db, anlage, invs, datum)

    # ladung_kwh ist primary → 46.0 (= 23 × 2.0), NICHT 46+23=69 (doppelt).
    eauto_alt = prev["tagesumme_alt"].get("verbrauch_eauto", 0.0)
    assert abs(eauto_alt - 46.0) < 0.01, (
        f"Reaggregator-Vorschau verbrauch_eauto={eauto_alt} (Doppelmapping nicht aufgelöst?)"
    )


def test_k3_eauto_doppelmapping_teilt_eine_either_or_gruppe():
    """#298-Bug-Klasse explizit: ein E-Auto mit `verbrauch_kwh` UND
    `ladung_kwh` darf NICHT zwei ungruppierte Einträge in `verbrauch_eauto`
    erzeugen (= Doppelzählung), sondern genau eine Either-Or-Gruppe."""
    inv = _make_inv(1, "e-auto")
    inv_data = {"felder": {
        "ladung_kwh": _sensor("sensor.ea_l"),
        "verbrauch_kwh": _sensor("sensor.ea_v"),
    }}
    hourly = investition_hourly_eintraege(inv, inv_data)

    eauto_entries = [he for he in hourly if he.kategorie == "verbrauch_eauto"]
    assert len(eauto_entries) == 2, eauto_entries
    gruppen = {he.fallback_gruppe for he in eauto_entries}
    assert gruppen == {f"eauto_either_or_1"}, (
        f"Doppelt gemappte E-Auto-Felder müssen EINE Either-Or-Gruppe teilen, "
        f"sonst Doppelzählung — gefunden: {gruppen}"
    )
