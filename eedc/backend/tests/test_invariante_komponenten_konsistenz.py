"""
Tests für die erweiterte Per-Kategorie-Invariante
`pruefe_tep_tz_komponenten_konsistenz` (v3.33.0, Issue #290).

Diese Invariante macht künftige Asymmetrien zwischen Stunden- und
Tages-Aggregator-Pfad sofort sichtbar — pro Kategorie ein Bericht.
"""

from __future__ import annotations

from types import SimpleNamespace

from backend.core.berechnungen import (
    assert_tep_tz_komponenten_konsistent,
    pruefe_tep_tz_komponenten_konsistenz,
)


def _tep_row(stunde: int, **kw):
    """Minimaler TEP-Stub. Nicht-gesetzte Felder = None."""
    defaults = {
        "stunde": stunde,
        "pv_kw": None,
        "waermepumpe_kw": None,
        "wallbox_kw": None,
        "batterie_kw": None,
        "einspeisung_kw": None,
        "netzbezug_kw": None,
    }
    defaults.update(kw)
    return SimpleNamespace(**defaults)


def test_konsistent_pv_einfach():
    """PV: Σ TEP.pv_kw == komp_kwh.pv_3 → konsistent."""
    tep = [_tep_row(h, pv_kw=1.0) for h in range(24)]  # Σ = 24
    tz = {"pv_3": 24.0}
    berichte = pruefe_tep_tz_komponenten_konsistenz(tep, tz)
    pv = next(b for b in berichte if "PV+BKW" in b.name)
    assert pv.konsistent
    assert abs(pv.erwartet - 24.0) < 0.01


def test_drift_pv_wird_erkannt():
    """Hourly Σ = 24, Daily = 30 → Drift > 0.5 → konsistent=False."""
    tep = [_tep_row(h, pv_kw=1.0) for h in range(24)]
    tz = {"pv_3": 30.0}
    berichte = pruefe_tep_tz_komponenten_konsistenz(tep, tz)
    pv = next(b for b in berichte if "PV+BKW" in b.name)
    assert not pv.konsistent
    assert pv.abweichung_kwh > 0.5


def test_drift_waermepumpe_wird_erkannt():
    """LTS-Bug-Klasse: Hourly 9.6, Daily 30 (Strom + thermisch aufaddiert)."""
    tep = [_tep_row(h, waermepumpe_kw=0.4) for h in range(24)]  # 9.6
    tz = {"waermepumpe_7": 30.0}  # buggy
    berichte = pruefe_tep_tz_komponenten_konsistenz(tep, tz)
    wp = next(b for b in berichte if "Wärmepumpe" in b.name)
    assert not wp.konsistent
    assert wp.abweichung_kwh > 20


def test_drift_wallbox_split_wird_erkannt():
    """Gernot-Bug: Hourly 14, Daily 23.24 (ladung_pv mitsummiert)."""
    tep = [_tep_row(h, wallbox_kw=14.0 / 24) for h in range(24)]
    tz = {"wallbox_2": 23.24}
    berichte = pruefe_tep_tz_komponenten_konsistenz(tep, tz)
    wb = next(b for b in berichte if "Wallbox+E-Auto" in b.name)
    assert not wb.konsistent
    assert abs(wb.abweichung_kwh - 9.24) < 0.1


def test_wallbox_und_eauto_zusammen():
    """Hourly TEP.wallbox_kw enthält Wallbox + E-Auto → komponenten muss summieren."""
    tep = [_tep_row(h, wallbox_kw=1.0) for h in range(24)]  # 24
    tz = {"wallbox_2": 10.0, "eauto_1": 14.0}  # zusammen 24
    berichte = pruefe_tep_tz_komponenten_konsistenz(tep, tz)
    wb = next(b for b in berichte if "Wallbox+E-Auto" in b.name)
    assert wb.konsistent


def test_batterie_netto_signed():
    """Batterie netto: ENTLADUNG positiv, LADUNG negativ (Spalten-Konvention,
    SoT batterie_kw_spalte) — Spalte und komponenten_kwh vorzeichen-gleich."""
    # 4h entladen (4*2=8), 6h laden (-6*1=-6) → netto +2 pro Tag (Entladung-Überhang)
    tep = []
    for h in range(24):
        if 10 <= h <= 13:
            tep.append(_tep_row(h, batterie_kw=2.0))
        elif 18 <= h <= 23:
            tep.append(_tep_row(h, batterie_kw=-1.0))
        else:
            tep.append(_tep_row(h, batterie_kw=0.0))
    tz = {"batterie_5": 2.0}
    berichte = pruefe_tep_tz_komponenten_konsistenz(tep, tz)
    batt = next(b for b in berichte if "Batterie" in b.name)
    assert batt.konsistent, str(batt)


def test_basis_einspeisung_und_netzbezug():
    tep = [_tep_row(h, einspeisung_kw=1.0, netzbezug_kw=0.5) for h in range(24)]
    tz = {"einspeisung": 24.0, "netzbezug": 12.0}
    berichte = pruefe_tep_tz_komponenten_konsistenz(tep, tz)
    einsp = next(b for b in berichte if "einspeisung_kw" in b.name)
    bezug = next(b for b in berichte if "netzbezug_kw" in b.name)
    assert einsp.konsistent
    assert bezug.konsistent


def test_kategorie_ohne_daten_uebersprungen():
    """Wenn weder TEP noch TZ Werte für eine Kategorie haben → kein Bericht."""
    tep = [_tep_row(h, pv_kw=1.0) for h in range(24)]
    tz = {"pv_3": 24.0}  # nur PV gemappt
    berichte = pruefe_tep_tz_komponenten_konsistenz(tep, tz)
    namen = [b.name for b in berichte]
    # PV kommt vor — die anderen Kategorien nicht
    assert any("PV+BKW" in n for n in namen)
    assert not any("Wärmepumpe" in n for n in namen)
    assert not any("Wallbox" in n for n in namen)
    assert not any("Batterie" in n for n in namen)


def test_assert_variant_failt_bei_drift():
    tep = [_tep_row(h, pv_kw=1.0) for h in range(24)]
    tz = {"pv_3": 30.0}
    try:
        assert_tep_tz_komponenten_konsistent(tep, tz)
        assert False, "Erwarteter AssertionError ausgeblieben"
    except AssertionError as e:
        assert "PV+BKW" in str(e)


def test_assert_variant_ok_bei_konsistenz():
    tep = [_tep_row(h, pv_kw=1.0) for h in range(24)]
    tz = {"pv_3": 24.0}
    # darf nicht werfen
    assert_tep_tz_komponenten_konsistent(tep, tz)


def test_toleranz_kwh_grenze():
    """Drift unterhalb der Toleranz ist konsistent."""
    tep = [_tep_row(h, pv_kw=1.0) for h in range(24)]
    tz = {"pv_3": 24.4}  # 0.4 kWh Drift, Toleranz 0.5
    berichte = pruefe_tep_tz_komponenten_konsistenz(tep, tz)
    pv = next(b for b in berichte if "PV+BKW" in b.name)
    assert pv.konsistent
