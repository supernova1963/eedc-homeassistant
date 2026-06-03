"""
Symmetrie-Test (v3.33.0, Issue #290).

Bei zwei parallelen Implementierungen derselben Aggregations-Logik müssen
beide bei identischen Eingangsdaten identische Ausgaben liefern. Wäre dieser
Test schon am 16. Mai geschrieben gewesen, hätte er den LTS-Aggregator-
Drift sofort aufgedeckt.

Für jeden Per-Typ-Setup geben wir synthetische Stunden-Deltas pro Sensor
vor und prüfen:
  - Snapshot-Variante (`get_komponenten_tageskwh`)
  - LTS-Variante (`get_komponenten_tageskwh_lts`)

liefern identische `komponenten_kwh`-Dicts.

Implementierungs-Detail: Snapshot-Pfad braucht boundary-Snapshots. Wir
mocken `get_snapshot` direkt: snap[h] = Σ deltas[0..h-1] (kumulativ),
snap[24] = Σ aller 24 Stunden. Damit ist `_diff(snap[24]-snap[0])` = Σ
deltas — exakt das, was die LTS-Variante summiert.
"""

from __future__ import annotations

from datetime import date, datetime
from types import SimpleNamespace
from unittest.mock import patch, MagicMock

import pytest

from backend.services.snapshot.aggregator import get_komponenten_tageskwh
from backend.services.snapshot.lts_aggregator import get_komponenten_tageskwh_lts


# ─── Fixture-Helper ────────────────────────────────────────────────────────


def _make_anlage(sensor_mapping: dict):
    return SimpleNamespace(
        id=1,
        anlagenname="SymTest",
        leistung_kwp=10.0,
        sensor_mapping=sensor_mapping,
    )


def _make_inv(inv_id: int, typ: str, parameter=None, parent_investition_id=None):
    return SimpleNamespace(
        id=inv_id,
        anlage_id=1,
        typ=typ,
        parameter=parameter or {},
        parent_investition_id=parent_investition_id,
    )


def _sensor(sid: str) -> dict:
    return {"strategie": "sensor", "sensor_id": sid}


def _sensor_key_for_feld(feld: str, inv_id_str: str | None = None) -> str:
    """Stellt das interne sensor_key-Schema her, das der Snapshot-Pfad nutzt."""
    if inv_id_str is None:
        return f"basis:{feld}"
    return f"inv:{inv_id_str}:{feld}"


def _build_snapshot_lookup(
    sensor_id_to_deltas: dict[str, dict[int, float]],
    sensor_key_to_sensor_id: dict[str, str],
    referenz_datum: date,
):
    """Baut eine async-Funktion für `get_snapshot`.

    snap_at_h = Σ deltas[0..h-1]. Für h=0 → 0.0. Für h=24 → Σ aller Stunden.

    Tagesfenster: `referenz_datum 00:00` (snap=0) bis
    `referenz_datum + 1 Tag 00:00` (snap=Σ aller 24 Stunden).
    """
    kumulativ: dict[str, float] = {}
    for sid, slots in sensor_id_to_deltas.items():
        kumulativ[sid] = sum(slots.get(h, 0.0) for h in range(24))

    async def fake_get_snapshot(db, anlage_id, sensor_key, sensor_id, zeitpunkt, *args, **kwargs):
        sid = sensor_key_to_sensor_id.get(sensor_key)
        if sid is None:
            return None
        # Vor/Bei Tagesbeginn → 0, am Folgetag-Beginn oder später → Tagessumme
        if zeitpunkt.date() <= referenz_datum:
            return 0.0
        return kumulativ[sid]

    return fake_get_snapshot


def _build_mock_ha_svc(deltas_per_sensor: dict[str, dict[int, float]]) -> MagicMock:
    svc = MagicMock()
    svc.is_available = True

    def _get_deltas(sensor_ids, _datum):
        return {eid: deltas_per_sensor[eid] for eid in sensor_ids if eid in deltas_per_sensor}

    svc.get_hourly_kwh_deltas_for_day.side_effect = _get_deltas
    return svc


# ─── Setup-Permutationen ───────────────────────────────────────────────────


def _setup_wp_strom_only():
    sm = {"basis": {}, "investitionen": {
        "7": {"felder": {"stromverbrauch_kwh": _sensor("sensor.wp_strom")}},
    }}
    invs = {"7": _make_inv(7, "waermepumpe")}
    deltas = {"sensor.wp_strom": {h: 0.4 for h in range(24)}}  # 9.6
    sk_map = {_sensor_key_for_feld("stromverbrauch_kwh", "7"): "sensor.wp_strom"}
    return sm, invs, deltas, sk_map


def _setup_wp_strom_plus_thermisch():
    """detLAN-Klasse: WP mit Strom + thermischen Sensoren."""
    sm = {"basis": {}, "investitionen": {
        "7": {"felder": {
            "stromverbrauch_kwh": _sensor("sensor.wp_strom"),
            "heizenergie_kwh": _sensor("sensor.wp_thermisch_heiz"),
            "warmwasser_kwh": _sensor("sensor.wp_thermisch_ww"),
        }},
    }}
    invs = {"7": _make_inv(7, "waermepumpe")}
    deltas = {
        "sensor.wp_strom": {h: 0.4 for h in range(24)},  # 9.6
        "sensor.wp_thermisch_heiz": {h: 1.2 for h in range(24)},  # darf NICHT
        "sensor.wp_thermisch_ww": {h: 0.5 for h in range(24)},  # darf NICHT
    }
    sk_map = {
        _sensor_key_for_feld("stromverbrauch_kwh", "7"): "sensor.wp_strom",
        _sensor_key_for_feld("heizenergie_kwh", "7"): "sensor.wp_thermisch_heiz",
        _sensor_key_for_feld("warmwasser_kwh", "7"): "sensor.wp_thermisch_ww",
    }
    return sm, invs, deltas, sk_map


def _setup_wp_getrennte_strommessung():
    sm = {"basis": {}, "investitionen": {
        "7": {"felder": {
            "strom_heizen_kwh": _sensor("sensor.wp_h"),
            "strom_warmwasser_kwh": _sensor("sensor.wp_ww"),
            "stromverbrauch_kwh": _sensor("sensor.wp_gesamt"),  # ignoriert
        }},
    }}
    invs = {"7": _make_inv(7, "waermepumpe", parameter={"getrennte_strommessung": True})}
    deltas = {
        "sensor.wp_h": {h: 0.2 for h in range(24)},  # 4.8
        "sensor.wp_ww": {h: 0.1 for h in range(24)},  # 2.4
        "sensor.wp_gesamt": {h: 99 for h in range(24)},  # niemals verwendet
    }
    sk_map = {
        _sensor_key_for_feld("strom_heizen_kwh", "7"): "sensor.wp_h",
        _sensor_key_for_feld("strom_warmwasser_kwh", "7"): "sensor.wp_ww",
        _sensor_key_for_feld("stromverbrauch_kwh", "7"): "sensor.wp_gesamt",
    }
    return sm, invs, deltas, sk_map


def _setup_speicher_simple():
    sm = {"basis": {}, "investitionen": {
        "5": {"felder": {
            "ladung_kwh": _sensor("sensor.lade"),
            "entladung_kwh": _sensor("sensor.entlade"),
        }},
    }}
    invs = {"5": _make_inv(5, "speicher")}
    deltas = {
        "sensor.lade": {h: (1.0 if 10 <= h <= 13 else 0.0) for h in range(24)},  # 4.0
        "sensor.entlade": {h: (0.8 if 18 <= h <= 22 else 0.0) for h in range(24)},  # 4.0
    }
    sk_map = {
        _sensor_key_for_feld("ladung_kwh", "5"): "sensor.lade",
        _sensor_key_for_feld("entladung_kwh", "5"): "sensor.entlade",
    }
    return sm, invs, deltas, sk_map


def _setup_speicher_arbitrage():
    """Bug-Klasse: ladung_netz_kwh ist Teilmenge von ladung_kwh."""
    sm = {"basis": {}, "investitionen": {
        "5": {"felder": {
            "ladung_kwh": _sensor("sensor.lade"),
            "entladung_kwh": _sensor("sensor.entlade"),
            "ladung_netz_kwh": _sensor("sensor.lade_netz"),
        }},
    }}
    invs = {"5": _make_inv(5, "speicher", parameter={"arbitrage_faehig": True})}
    deltas = {
        "sensor.lade": {h: 0.5 for h in range(24)},  # 12.0
        "sensor.entlade": {h: 0.3 for h in range(24)},  # 7.2
        "sensor.lade_netz": {h: 0.2 for h in range(24)},  # 4.8 (Teilmenge!)
    }
    sk_map = {
        _sensor_key_for_feld("ladung_kwh", "5"): "sensor.lade",
        _sensor_key_for_feld("entladung_kwh", "5"): "sensor.entlade",
        _sensor_key_for_feld("ladung_netz_kwh", "5"): "sensor.lade_netz",
    }
    return sm, invs, deltas, sk_map


def _setup_wallbox_simple():
    sm = {"basis": {}, "investitionen": {
        "2": {"felder": {"ladung_kwh": _sensor("sensor.wb")}},
    }}
    invs = {"2": _make_inv(2, "wallbox")}
    deltas = {"sensor.wb": {h: (2.0 if 18 <= h <= 21 else 0.0) for h in range(24)}}  # 8.0
    sk_map = {_sensor_key_for_feld("ladung_kwh", "2"): "sensor.wb"}
    return sm, invs, deltas, sk_map


def _setup_wallbox_split():
    """Gernot-Klasse: ladung + ladung_pv + ladung_netz."""
    sm = {"basis": {}, "investitionen": {
        "2": {"felder": {
            "ladung_kwh": _sensor("sensor.wb"),
            "ladung_pv_kwh": _sensor("sensor.wb_pv"),
            "ladung_netz_kwh": _sensor("sensor.wb_netz"),
        }},
    }}
    invs = {"2": _make_inv(2, "wallbox")}
    deltas = {
        "sensor.wb": {h: 0.6 for h in range(24)},      # 14.4
        "sensor.wb_pv": {h: 0.4 for h in range(24)},   # 9.6 (Teilmenge)
        "sensor.wb_netz": {h: 0.2 for h in range(24)}, # 4.8 (Teilmenge)
    }
    sk_map = {
        _sensor_key_for_feld("ladung_kwh", "2"): "sensor.wb",
        _sensor_key_for_feld("ladung_pv_kwh", "2"): "sensor.wb_pv",
        _sensor_key_for_feld("ladung_netz_kwh", "2"): "sensor.wb_netz",
    }
    return sm, invs, deltas, sk_map


def _setup_eauto_ohne_wallbox():
    sm = {"basis": {}, "investitionen": {
        "1": {"felder": {"ladung_kwh": _sensor("sensor.ea")}},
    }}
    invs = {"1": _make_inv(1, "e-auto")}
    deltas = {"sensor.ea": {h: 1.0 for h in range(24)}}  # 24.0
    sk_map = {_sensor_key_for_feld("ladung_kwh", "1"): "sensor.ea"}
    return sm, invs, deltas, sk_map


def _setup_eauto_mit_split():
    """ladung_kwh primary, ladung_pv/ladung_netz wären Teilmengen."""
    sm = {"basis": {}, "investitionen": {
        "1": {"felder": {
            "ladung_kwh": _sensor("sensor.ea"),
            "ladung_pv_kwh": _sensor("sensor.ea_pv"),
            "ladung_netz_kwh": _sensor("sensor.ea_netz"),
        }},
    }}
    invs = {"1": _make_inv(1, "e-auto")}
    deltas = {
        "sensor.ea": {h: 1.0 for h in range(24)},      # 24
        "sensor.ea_pv": {h: 0.6 for h in range(24)},   # darf nicht aufaddiert
        "sensor.ea_netz": {h: 0.4 for h in range(24)}, # darf nicht aufaddiert
    }
    sk_map = {
        _sensor_key_for_feld("ladung_kwh", "1"): "sensor.ea",
        _sensor_key_for_feld("ladung_pv_kwh", "1"): "sensor.ea_pv",
        _sensor_key_for_feld("ladung_netz_kwh", "1"): "sensor.ea_netz",
    }
    return sm, invs, deltas, sk_map


def _setup_eauto_mit_parent_wallbox():
    sm = {"basis": {}, "investitionen": {
        "1": {"felder": {"ladung_kwh": _sensor("sensor.ea")}},
    }}
    # parent → Skip, der Wert taucht NICHT im Dict auf
    invs = {"1": _make_inv(1, "e-auto", parent_investition_id=2)}
    deltas = {"sensor.ea": {h: 1.0 for h in range(24)}}
    sk_map = {_sensor_key_for_feld("ladung_kwh", "1"): "sensor.ea"}
    return sm, invs, deltas, sk_map


def _setup_eauto_fallback_verbrauch():
    """Kein ladung_kwh gemappt → fallback auf verbrauch_kwh."""
    sm = {"basis": {}, "investitionen": {
        "1": {"felder": {"verbrauch_kwh": _sensor("sensor.ea_verbr")}},
    }}
    invs = {"1": _make_inv(1, "e-auto")}
    deltas = {"sensor.ea_verbr": {h: 0.8 for h in range(24)}}  # 19.2
    sk_map = {_sensor_key_for_feld("verbrauch_kwh", "1"): "sensor.ea_verbr"}
    return sm, invs, deltas, sk_map


def _setup_eauto_verbrauch_und_ladung():
    """#298 (junky84/evcc): E-Auto mit BEIDEN Gesamt-Zählern `ladung_kwh` UND
    `verbrauch_kwh` gemappt. Beide mappt `_categorize_counter` auf
    `verbrauch_eauto` → der alte rohe Hourly-Pfad summierte sie doppelt,
    während der Daily-Pfad via Either-Or nur `ladung_kwh` (primary) nahm.
    Energie nur in Stunden 0..22 (h23=0), damit Σ über die Backward-Slots des
    Snapshot-Pfads window-deckungsgleich mit dem Daily-Total ist (S3-Snapshot).
    """
    sm = {"basis": {}, "investitionen": {
        "1": {"felder": {
            "ladung_kwh": _sensor("sensor.ea_ladung"),
            "verbrauch_kwh": _sensor("sensor.ea_verbrauch"),
        }},
    }}
    invs = {"1": _make_inv(1, "e-auto")}
    deltas = {
        "sensor.ea_ladung": {h: (1.0 if h < 23 else 0.0) for h in range(24)},      # 23.0 primary
        "sensor.ea_verbrauch": {h: (0.9 if h < 23 else 0.0) for h in range(24)},   # 20.7 darf NICHT addiert
    }
    sk_map = {
        _sensor_key_for_feld("ladung_kwh", "1"): "sensor.ea_ladung",
        _sensor_key_for_feld("verbrauch_kwh", "1"): "sensor.ea_verbrauch",
    }
    return sm, invs, deltas, sk_map


def _setup_sonstiges_verbraucher_doppelt():
    """Hybridgerät: erzeugung + verbrauch gemappt — nur primary zählt."""
    sm = {"basis": {}, "investitionen": {
        "13": {"felder": {
            "verbrauch_kwh": _sensor("sensor.pool_v"),
            "erzeugung_kwh": _sensor("sensor.pool_e"),
        }},
    }}
    invs = {"13": _make_inv(13, "sonstiges", parameter={"kategorie": "verbraucher"})}
    deltas = {
        "sensor.pool_v": {h: 0.2 for h in range(24)},  # 4.8 primary
        "sensor.pool_e": {h: 0.05 for h in range(24)}, # 1.2 darf NICHT subtrahiert
    }
    sk_map = {
        _sensor_key_for_feld("verbrauch_kwh", "13"): "sensor.pool_v",
        _sensor_key_for_feld("erzeugung_kwh", "13"): "sensor.pool_e",
    }
    return sm, invs, deltas, sk_map


def _setup_sonstiges_erzeuger_doppelt():
    """Erzeuger (z. B. Mini-BHKW als 'sonstiges'): erzeugung primary, verbrauch fallback."""
    sm = {"basis": {}, "investitionen": {
        "14": {"felder": {
            "erzeugung_kwh": _sensor("sensor.bhkw_e"),
            "verbrauch_kwh": _sensor("sensor.bhkw_v"),  # nicht zählen
        }},
    }}
    invs = {"14": _make_inv(14, "sonstiges", parameter={"kategorie": "erzeuger"})}
    deltas = {
        "sensor.bhkw_e": {h: 0.3 for h in range(24)},   # 7.2 primary
        "sensor.bhkw_v": {h: 0.1 for h in range(24)},   # 2.4 darf NICHT
    }
    sk_map = {
        _sensor_key_for_feld("erzeugung_kwh", "14"): "sensor.bhkw_e",
        _sensor_key_for_feld("verbrauch_kwh", "14"): "sensor.bhkw_v",
    }
    return sm, invs, deltas, sk_map


def _setup_sonstiges_erzeuger_nur_fallback():
    """Erzeuger ohne erzeugung_kwh — Helper fällt auf verbrauch_kwh zurück."""
    sm = {"basis": {}, "investitionen": {
        "14": {"felder": {
            "verbrauch_kwh": _sensor("sensor.bhkw_v"),
        }},
    }}
    invs = {"14": _make_inv(14, "sonstiges", parameter={"kategorie": "erzeuger"})}
    deltas = {"sensor.bhkw_v": {h: 0.1 for h in range(24)}}
    sk_map = {_sensor_key_for_feld("verbrauch_kwh", "14"): "sensor.bhkw_v"}
    return sm, invs, deltas, sk_map


def _setup_basis_einspeisung_und_netzbezug():
    sm = {"basis": {
        "einspeisung": _sensor("sensor.einsp"),
        "netzbezug": _sensor("sensor.bezug"),
    }, "investitionen": {}}
    invs: dict = {}
    deltas = {
        "sensor.einsp": {h: 1.5 for h in range(24)},  # 36
        "sensor.bezug": {h: 0.4 for h in range(24)},  # 9.6
    }
    sk_map = {
        _sensor_key_for_feld("einspeisung"): "sensor.einsp",
        _sensor_key_for_feld("netzbezug"): "sensor.bezug",
    }
    return sm, invs, deltas, sk_map


def _setup_pv_module():
    sm = {"basis": {}, "investitionen": {
        "3": {"felder": {"pv_erzeugung_kwh": _sensor("sensor.pv")}},
    }}
    invs = {"3": _make_inv(3, "pv-module")}
    deltas = {"sensor.pv": {h: 1.0 for h in range(24)}}  # 24
    sk_map = {_sensor_key_for_feld("pv_erzeugung_kwh", "3"): "sensor.pv"}
    return sm, invs, deltas, sk_map


def _setup_balkonkraftwerk():
    sm = {"basis": {}, "investitionen": {
        "11": {"felder": {"pv_erzeugung_kwh": _sensor("sensor.bkw")}},
    }}
    invs = {"11": _make_inv(11, "balkonkraftwerk")}
    deltas = {"sensor.bkw": {h: 0.3 for h in range(24)}}  # 7.2
    sk_map = {_sensor_key_for_feld("pv_erzeugung_kwh", "11"): "sensor.bkw"}
    return sm, invs, deltas, sk_map


SETUPS = {
    "pv_module": _setup_pv_module,
    "balkonkraftwerk": _setup_balkonkraftwerk,
    "wp_strom_only": _setup_wp_strom_only,
    "wp_strom_plus_thermisch": _setup_wp_strom_plus_thermisch,
    "wp_getrennte_strommessung": _setup_wp_getrennte_strommessung,
    "speicher_simple": _setup_speicher_simple,
    "speicher_arbitrage": _setup_speicher_arbitrage,
    "wallbox_simple": _setup_wallbox_simple,
    "wallbox_split": _setup_wallbox_split,
    "eauto_ohne_wallbox": _setup_eauto_ohne_wallbox,
    "eauto_mit_split": _setup_eauto_mit_split,
    "eauto_mit_parent_wallbox": _setup_eauto_mit_parent_wallbox,
    "eauto_fallback_verbrauch": _setup_eauto_fallback_verbrauch,
    "eauto_verbrauch_und_ladung": _setup_eauto_verbrauch_und_ladung,
    "sonstiges_verbraucher_doppelt": _setup_sonstiges_verbraucher_doppelt,
    "sonstiges_erzeuger_doppelt": _setup_sonstiges_erzeuger_doppelt,
    "sonstiges_erzeuger_nur_fallback": _setup_sonstiges_erzeuger_nur_fallback,
    "basis_einspeisung_und_netzbezug": _setup_basis_einspeisung_und_netzbezug,
}


@pytest.mark.parametrize("setup_name", list(SETUPS.keys()))
async def test_snapshot_und_lts_liefern_identische_komponenten_kwh(setup_name):
    """Beide Aggregator-Varianten müssen bei identischen Per-Sensor-Tagessummen
    dieselben `komponenten_kwh`-Dicts produzieren."""
    sm, invs, deltas, sk_map = SETUPS[setup_name]()
    anlage = _make_anlage(sm)
    datum = date(2026, 5, 22)

    # LTS-Pfad: HA-Statistics-Mock
    mock_svc = _build_mock_ha_svc(deltas)
    with patch(
        "backend.services.snapshot.lts_aggregator.get_ha_statistics_service",
        return_value=mock_svc,
    ):
        lts_result = await get_komponenten_tageskwh_lts(anlage, invs, datum)

    # Snapshot-Pfad: get_snapshot-Mock (kumulative Werte aus deltas)
    fake_snap = _build_snapshot_lookup(deltas, sk_map, datum)
    with patch(
        "backend.services.snapshot.aggregator.get_snapshot",
        side_effect=fake_snap,
    ):
        snap_result = await get_komponenten_tageskwh(
            db=MagicMock(), anlage=anlage, investitionen_by_id=invs, datum=datum,
        )

    # Vergleich: gleiche Keys, gleiche Werte (1 mWh Toleranz für Float-Rundung)
    assert set(snap_result.keys()) == set(lts_result.keys()), (
        f"[{setup_name}] Key-Drift Snapshot vs LTS\n"
        f"  Snapshot: {sorted(snap_result.keys())}\n"
        f"  LTS:      {sorted(lts_result.keys())}"
    )
    for key in snap_result:
        sv = snap_result[key]
        lv = lts_result[key]
        assert abs(sv - lv) < 0.01, (
            f"[{setup_name}] {key}: Snapshot={sv:.3f} vs LTS={lv:.3f}"
        )
