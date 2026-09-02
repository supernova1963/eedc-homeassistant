"""Tests für die Achse-2-Invariante `pruefe_tep_komponenten_intern_konsistenz`
(Issue #315).

`aggregate_day` schreibt pro Stunde zwei parallele Repräsentationen:
- typisierte `*_kw`-Spalten (Zähler-/Boundary-Pfad)
- `komponenten`-JSON (Leistungspfad, W-Integration)

Im HA-LTS-Modus ist das `komponenten`-JSON sonst gegen nichts geprüft. Diese
Invariante vergleicht beide TEP-intern. Skip-Semantik: nur prüfen, wenn beide
Seiten die Kategorie führen — sonst Falsch-Positiv „Drift gegen 0".

⚑ **Die Proben hier übergeben bewusst ``None`` als Grundgesamtheit** (N-187,
2026-09-02): Ihr Gegenstand ist die **Rechenregel** — Σ-Semantik, Vorzeichen-
Angleichung, Toleranz —, nicht die Einschränkung auf zählergedeckte Geräte.
Sie prüfen damit unverändert das, wofür sie geschrieben wurden. Die
Einschränkung selbst hat eine eigene Datei:
``test_n187_achse2_gleiche_grundgesamtheit.py``.
"""

from __future__ import annotations

from types import SimpleNamespace

from backend.core.berechnungen import (
    assert_tep_komponenten_intern_konsistent,
    pruefe_tep_komponenten_intern_konsistenz,
)


def _tep_row(stunde: int, *, komponenten=None, **kw):
    """Minimaler TEP-Stub. Nicht-gesetzte *_kw-Felder = None."""
    defaults = {
        "stunde": stunde,
        "pv_kw": None,
        "waermepumpe_kw": None,
        "wallbox_kw": None,
        "batterie_kw": None,
        "einspeisung_kw": None,
        "netzbezug_kw": None,
        "komponenten": komponenten,
    }
    defaults.update(kw)
    return SimpleNamespace(**defaults)


def test_konsistent_pv():
    """Σ pv_kw (Zähler) == Σ komponenten[pv_*] (Leistung) → konsistent."""
    tep = [_tep_row(h, pv_kw=1.0, komponenten={"pv_3": 1.0}) for h in range(24)]
    berichte = pruefe_tep_komponenten_intern_konsistenz(tep, None)
    pv = next(b for b in berichte if "PV+BKW" in b.name)
    assert pv.konsistent
    assert abs(pv.erwartet - 24.0) < 0.01
    assert abs(pv.tatsaechlich - 24.0) < 0.01


def test_drift_pv_wird_erkannt():
    """Zähler-Σ = 24, Leistungs-Σ = 30 → Drift > 0.5 → konsistent=False."""
    tep = [_tep_row(h, pv_kw=1.0, komponenten={"pv_3": 1.25}) for h in range(24)]
    berichte = pruefe_tep_komponenten_intern_konsistenz(tep, None)
    pv = next(b for b in berichte if "PV+BKW" in b.name)
    assert not pv.konsistent
    assert pv.abweichung_kwh > 0.5


def test_skip_kategorie_nur_zaehler_kein_leistungs_key():
    """*_kw gesetzt, aber kein passender komponenten-Key → KEIN Bericht
    (sonst Falsch-Positiv „Drift gegen 0"). Das ist der Kern der Skip-Semantik."""
    # WP nur per Zähler, komponenten führt nur PV.
    tep = [
        _tep_row(h, pv_kw=1.0, waermepumpe_kw=0.4, komponenten={"pv_3": 1.0})
        for h in range(24)
    ]
    berichte = pruefe_tep_komponenten_intern_konsistenz(tep, None)
    namen = [b.name for b in berichte]
    assert any("PV+BKW" in n for n in namen)
    assert not any("Wärmepumpe" in n for n in namen)


def test_skip_kategorie_nur_leistung_kein_zaehler():
    """komponenten-Key vorhanden, aber *_kw nie gesetzt → KEIN Bericht."""
    tep = [_tep_row(h, komponenten={"waermepumpe_5": -0.4}) for h in range(24)]
    berichte = pruefe_tep_komponenten_intern_konsistenz(tep, None)
    assert not berichte


def test_basis_wird_nicht_geprueft():
    """einspeisung/netzbezug sind Achse 3 (#316), nicht Achse 2 — auch bei
    vorhandenen Werten darf kein Basis-Bericht entstehen."""
    tep = [
        _tep_row(
            h, einspeisung_kw=1.0, netzbezug_kw=0.5,
            komponenten={"einspeisung": 1.0, "netzbezug": 0.5},
        )
        for h in range(24)
    ]
    berichte = pruefe_tep_komponenten_intern_konsistenz(tep, None)
    assert not any("einspeisung" in b.name for b in berichte)
    assert not any("netzbezug" in b.name for b in berichte)


def test_wallbox_und_eauto_summiert():
    """TEP.wallbox_kw (Zähler: Wallbox+E-Auto) gegen Σ komponenten[wallbox_*,
    eauto_*].

    ⚠ Die Komponenten stehen **negativ** — der Leistungspfad schreibt jede
    Serie mit ``seite == "senke"`` als ``-abs(...)``
    (``live_tagesverlauf_service``), der Zählerpfad schreibt Verbrauch positiv.
    Bis 2026-08-08 setzte diese Fixture sie positiv und bildete damit die
    Produktionskonvention nicht ab: der Test war grün, während die Invariante
    an einer echten Anlage für jeden Ladetag Drift meldete (#356).
    """
    tep = [
        _tep_row(h, wallbox_kw=1.0, komponenten={"wallbox_2": -0.6, "eauto_1": -0.4})
        for h in range(24)
    ]
    berichte = pruefe_tep_komponenten_intern_konsistenz(tep, None)
    wb = next(b for b in berichte if "Wallbox+E-Auto" in b.name)
    assert wb.konsistent, str(wb)


def test_wallbox_senke_gemessener_tag_ist_konsistent():
    """Realfall aus der #356-Vermessung: der Betrag stimmt, nur das Vorzeichen
    war entgegengesetzt — das darf **keine** Drift mehr sein.

    Anlage 1, 2026-03-15: Zähler-Σ 29,48 kWh, Leistungs-Σ −30,42 kWh. Vor der
    Angleichung meldete die Invariante 59,90 kWh Abweichung (Faktor −1,03),
    obwohl die beiden Pfade 0,94 kWh auseinanderliegen — innerhalb dessen, was
    Riemann-/Zählerauflösung erklärt.
    """
    tep = [
        _tep_row(
            0, wallbox_kw=29.48, komponenten={"wallbox_2": -30.42}
        )
    ]
    berichte = pruefe_tep_komponenten_intern_konsistenz(tep, None, toleranz_kwh=1.0)
    wb = next(b for b in berichte if "Wallbox+E-Auto" in b.name)
    assert wb.konsistent, str(wb)
    assert wb.abweichung_kwh < 1.0, str(wb)


def test_wallbox_echte_drift_bleibt_sichtbar():
    """Die Angleichung darf die Diagnose nicht blind machen: eine doppelt
    gezählte Ladung (Wallbox **und** E-Auto messen denselben Stromfluss) muss
    weiterhin auffallen.

    Realfall Anlage 1, 2026-08-06: Zähler 12,00 kWh, Leistungspfad
    ``wallbox_2`` −12,00 **plus** ``eauto_1`` −17,32 aus einem zweiten Sensor
    für dieselben Ladestunden.
    """
    tep = [
        _tep_row(
            0, wallbox_kw=12.0, komponenten={"wallbox_2": -12.0, "eauto_1": -17.32}
        )
    ]
    berichte = pruefe_tep_komponenten_intern_konsistenz(tep, None)
    wb = next(b for b in berichte if "Wallbox+E-Auto" in b.name)
    assert not wb.konsistent, str(wb)
    assert abs(wb.abweichung_kwh - 17.32) < 0.01, str(wb)


def test_pv_wird_nicht_angeglichen():
    """Abgrenzung: PV steht auf beiden Pfaden positiv (``seite == "quelle"`` ⇒
    ``abs(...)``). Würde die Senken-Angleichung auch hier greifen, wäre ein
    konsistenter PV-Tag plötzlich eine Drift von 2× dem Ertrag."""
    tep = [_tep_row(h, pv_kw=2.0, komponenten={"pv_3": 2.0}) for h in range(24)]
    berichte = pruefe_tep_komponenten_intern_konsistenz(tep, None)
    pv = next(b for b in berichte if "PV+BKW" in b.name)
    assert pv.konsistent, str(pv)
    assert abs(pv.tatsaechlich - 48.0) < 0.01, str(pv)


def test_batterie_netto_signed():
    """Batterie netto: ENTLADUNG positiv, LADUNG negativ (Spalten-Konvention,
    SoT batterie_kw_spalte) — beide Pfade vorzeichen-gleich signed."""
    tep = []
    for h in range(24):
        if 10 <= h <= 13:
            tep.append(_tep_row(h, batterie_kw=2.0, komponenten={"batterie_5": 2.0}))
        elif 18 <= h <= 23:
            tep.append(_tep_row(h, batterie_kw=-1.0, komponenten={"batterie_5": -1.0}))
        else:
            tep.append(_tep_row(h, batterie_kw=0.0, komponenten={"batterie_5": 0.0}))
    berichte = pruefe_tep_komponenten_intern_konsistenz(tep, None)
    batt = next(b for b in berichte if "Batterie" in b.name)
    assert batt.konsistent, str(batt)


def test_toleranz_grenze():
    """Drift unterhalb der Toleranz ist konsistent."""
    # 0.4 kWh Gesamtdrift bei Toleranz 0.5
    tep = [_tep_row(h, pv_kw=1.0, komponenten={"pv_3": 1.0}) for h in range(24)]
    tep[0].komponenten = {"pv_3": 1.4}
    berichte = pruefe_tep_komponenten_intern_konsistenz(tep, None)
    pv = next(b for b in berichte if "PV+BKW" in b.name)
    assert pv.konsistent


def test_assert_variant_failt_bei_drift():
    tep = [_tep_row(h, pv_kw=1.0, komponenten={"pv_3": 1.25}) for h in range(24)]
    try:
        assert_tep_komponenten_intern_konsistent(tep, None)
        assert False, "Erwarteter AssertionError ausgeblieben"
    except AssertionError as e:
        assert "Achse2" in str(e)


def test_assert_variant_ok_bei_konsistenz():
    tep = [_tep_row(h, pv_kw=1.0, komponenten={"pv_3": 1.0}) for h in range(24)]
    assert_tep_komponenten_intern_konsistent(tep, None)  # darf nicht werfen
