"""Akzeptanztest: Lernfaktor-IST nutzt die PV-Whitelist, nicht eine Blacklist.

Bug (Rainer-PN 2026-05-21): `live_wetter._filtere_tage` summierte den
Lernfaktor-IST über eine 3-Element-Blacklist
`_NICHT_PV = {strompreis, netzbezug, einspeisung}`. Jeder positive
Nicht-PV-Key in `komponenten_kwh` — Batterie-Entladung, Wärmepumpe,
Wallbox, `sonstige_`, `netz_` — wurde dadurch als PV-Erzeugung
mitgezählt. Folge: Σ(IST) systematisch zu hoch → Lernfaktor zu groß
(auf Gernots Anlage +14 %, auf Rainers Anlage bis an den Clamp 1.30).

Fix: `_filtere_tage` nutzt jetzt den SoT-Helper `summe_pv_bkw_kwh`
(Whitelist `pv_`/`bkw_`, core/berechnungen/energie.py).
"""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace

from backend.api.routes.live_wetter import _aggregiere_legacy, _filtere_tage


def _tag(datum: date, komponenten_kwh: dict, pv_prognose_kwh: float):
    """Minimal-Stub einer TagesZusammenfassung-Zeile."""
    return SimpleNamespace(
        datum=datum,
        komponenten_kwh=komponenten_kwh,
        pv_prognose_kwh=pv_prognose_kwh,
    )


def test_filtere_tage_zaehlt_nur_pv_und_bkw():
    """Nicht-PV-Keys (WP, Batterie, Wallbox, sonstige, netz) fließen NICHT
    in den IST-Wert ein — nur `pv_`/`bkw_`."""
    tage = [
        _tag(date(2026, 5, 20), {
            "pv_1": 20.0,
            "bkw_5": 2.5,
            "wp_3": 8.0,          # Wärmepumpe-Verbrauch — kein PV
            "batterie_2": 5.0,    # Batterie-Entladung — kein PV
            "wallbox_4": 6.0,     # Wallbox-Verbrauch — kein PV
            "sonstige_9": 3.0,    # sonstiger Verbraucher — kein PV
            "netz_1": 4.0,        # Netz-Komponente — kein PV
        }, pv_prognose_kwh=21.0),
    ]

    daten = _filtere_tage(tage, "pv_prognose_kwh")

    assert len(daten) == 1
    _, ist_kwh, prognose_kwh = daten[0]
    # NUR pv_1 + bkw_5 = 22.5 — nicht 48.5 (alte Blacklist-Summe).
    assert ist_kwh == 22.5
    assert prognose_kwh == 21.0


def test_negative_verbraucher_keys_ignoriert():
    """Verbraucher-Sub-Keys mit negativem Vorzeichen zählen ohnehin nicht
    — Whitelist greift unabhängig vom Vorzeichen sauber."""
    tage = [
        _tag(date(2026, 5, 19), {
            "pv_1": 30.0,
            "wp_1": -12.0,        # negativ notierter Verbrauch
            "netz_1": -4.0,
        }, pv_prognose_kwh=29.0),
    ]

    daten = _filtere_tage(tage, "pv_prognose_kwh")

    assert len(daten) == 1
    assert daten[0][1] == 30.0


def test_lernfaktor_nicht_durch_verbraucher_aufgeblaeht():
    """Regression: Faktor ≈ 1.0 wenn IST(PV) ≈ Prognose, auch wenn parallel
    hohe Verbraucher-Keys in komponenten_kwh stehen.

    Mit der alten Blacklist hätte IST = 52 kWh/Tag (30 PV + 12 WP + 10
    Wallbox) ergeben → Faktor 1.73 statt 1.0.
    """
    tage = [
        _tag(date(2026, 5, 1 + i), {
            "pv_1": 30.0,
            "wp_1": 12.0,        # großer WP-Verbrauch jeden Tag
            "wallbox_1": 10.0,   # großer Wallbox-Verbrauch jeden Tag
        }, pv_prognose_kwh=30.0)
        for i in range(10)
    ]

    daten = _filtere_tage(tage, "pv_prognose_kwh")
    raw_faktor, count = _aggregiere_legacy(daten)

    assert count == 10
    assert raw_faktor == 1.0


def test_reine_pv_anlage_unveraendert():
    """Anlage ohne Verbraucher-Komponenten: Verhalten identisch zu vorher
    — der Fix darf saubere Anlagen nicht verändern."""
    tage = [
        _tag(date(2026, 5, 15), {"pv_1": 18.0, "pv_2": 12.0},
             pv_prognose_kwh=33.0),
    ]

    daten = _filtere_tage(tage, "pv_prognose_kwh")

    assert len(daten) == 1
    assert daten[0][1] == 30.0


def test_tag_ohne_komponenten_uebersprungen():
    """Tag ohne komponenten_kwh (IST ≤ 0.5) wird ausgeschlossen."""
    tage = [
        _tag(date(2026, 5, 14), None, pv_prognose_kwh=25.0),
        _tag(date(2026, 5, 13), {}, pv_prognose_kwh=25.0),
    ]

    assert _filtere_tage(tage, "pv_prognose_kwh") == []
