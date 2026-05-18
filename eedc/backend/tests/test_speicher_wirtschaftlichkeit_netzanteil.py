"""
Akzeptanztest Etappe B (Issue #264): Spread-Modell mit PV/Netz-Anteil.

Deckt drei Schichten ab:

  1. `services.speicher_wirtschaftlichkeit.berechne_speicher_ersparnis`
     mit der neuen `ladung_netz_kwh`-Signatur (Regression + Edge-Cases).
  2. `services.speicher_wirtschaftlichkeit.aggregiere_speicher_ist`
     (Jahres-Hochrechnung + Mindest-Monate-Schwelle).
  3. `core.calculations.berechne_speicher_einsparung`-Wrapper:
     - alte Signatur (Prognose) verhält sich identisch wie vor Etappe B
     - neue Signatur (`ist_entladung_kwh` gepflegt) delegiert an den
       Spread-Service und liefert identische Zahlen.

Self-contained:

    eedc/backend/venv/bin/python eedc/backend/tests/test_speicher_wirtschaftlichkeit_netzanteil.py
"""

from __future__ import annotations

import math
import sys
import traceback
from pathlib import Path

_BACKEND_ROOT = Path(__file__).resolve().parents[2]  # eedc/
sys.path.insert(0, str(_BACKEND_ROOT))

from backend.core.calculations import (  # noqa: E402
    SPEICHER_ZYKLEN_PRO_JAHR,
    berechne_speicher_einsparung,
)
from backend.services.speicher_wirtschaftlichkeit import (  # noqa: E402
    SPEICHER_IST_MIN_MONATE,
    aggregiere_speicher_ist,
    berechne_speicher_ersparnis,
)


def _approx(a: float, b: float, tol: float = 0.01) -> bool:
    return math.isclose(a, b, abs_tol=tol)


# ----------------------------------------------------------------------------
# berechne_speicher_ersparnis — Spread-Service
# ----------------------------------------------------------------------------

def test_reiner_pv_speicher_ohne_netzladung_regression() -> None:
    # ladung_netz_kwh=0 → exakt das alte Verhalten (Spread × Entladung).
    r = berechne_speicher_ersparnis(
        entladung_kwh=500,
        bezug_preis_cent=30,
        einspeise_verg_cent=8,
    )
    # 500 kWh × (30 − 8) ct = 11000 ct = 110 €
    assert _approx(r.ersparnis_euro, 110.0)
    assert _approx(r.pv_anteil_euro, 110.0)
    assert _approx(r.netz_anteil_euro, 0.0)
    assert _approx(r.pv_anteil_entladung_kwh, 500.0)
    assert _approx(r.netz_anteil_entladung_kwh, 0.0)


def test_netzladung_ohne_ladepreis_kostet_keinen_pv_vorteil() -> None:
    # 200 kWh Netzladung × η95 = 190 kWh netzgespeiste Entladung.
    # PV-Anteil = 500 − 190 = 310 kWh × 22 ct = 68.20 €
    # Netz-Anteil = 190 kWh × (30 − 30) = 0 € (kein Ladepreis → kostenneutral)
    r = berechne_speicher_ersparnis(
        entladung_kwh=500,
        bezug_preis_cent=30,
        einspeise_verg_cent=8,
        ladung_netz_kwh=200,
        wirkungsgrad_prozent=95,
    )
    assert _approx(r.netz_anteil_entladung_kwh, 190.0)
    assert _approx(r.pv_anteil_entladung_kwh, 310.0)
    assert _approx(r.pv_anteil_euro, 310 * 0.22)
    assert _approx(r.netz_anteil_euro, 0.0)
    assert _approx(r.ersparnis_euro, 310 * 0.22)


def test_netzladung_mit_guenstigem_ladepreis_bringt_arbitrage() -> None:
    # Wie oben, aber Ladepreis 12 ct → Netz-Spread 30−12 = 18 ct
    # Netz-Anteil: 190 × 0.18 = 34.20 €
    r = berechne_speicher_ersparnis(
        entladung_kwh=500,
        bezug_preis_cent=30,
        einspeise_verg_cent=8,
        ladung_netz_kwh=200,
        wirkungsgrad_prozent=95,
        lade_preis_cent=12,
    )
    assert _approx(r.netz_anteil_euro, 190 * 0.18)
    assert _approx(r.pv_anteil_euro, 310 * 0.22)
    assert _approx(r.ersparnis_euro, 310 * 0.22 + 190 * 0.18)


def test_netzladung_groesser_als_entladung_geclamped() -> None:
    # Wenn jemand mehr Netzladung erfasst als Entladung (z. B. Speicher füllt
    # sich im Monat, Energie wird ins nächste verschoben), darf der Netz-Anteil
    # nicht > Entladung sein. Etappe C handhabt das sauber über SoC-Bilanz,
    # Etappe B clamped pragmatisch.
    r = berechne_speicher_ersparnis(
        entladung_kwh=100,
        bezug_preis_cent=30,
        einspeise_verg_cent=8,
        ladung_netz_kwh=500,  # × 0.95 = 475 → clamped auf 100
        wirkungsgrad_prozent=95,
        lade_preis_cent=12,
    )
    assert _approx(r.netz_anteil_entladung_kwh, 100.0)
    assert _approx(r.pv_anteil_entladung_kwh, 0.0)
    assert _approx(r.netz_anteil_euro, 100 * 0.18)
    assert _approx(r.pv_anteil_euro, 0.0)


def test_bezug_unter_einspeisung_clampt_spread_auf_null() -> None:
    # Edge: degenerierte Tarif-Konstellation (Bezug < Einspeisung) ergibt
    # keinen Speicher-Vorteil — Verhalten existiert bereits, hier nur Regression.
    r = berechne_speicher_ersparnis(
        entladung_kwh=300,
        bezug_preis_cent=5,
        einspeise_verg_cent=10,
    )
    assert _approx(r.ersparnis_euro, 0.0)


def test_keine_entladung_keine_ersparnis() -> None:
    r = berechne_speicher_ersparnis(
        entladung_kwh=0,
        bezug_preis_cent=30,
        einspeise_verg_cent=8,
        ladung_netz_kwh=100,
        lade_preis_cent=10,
    )
    assert _approx(r.ersparnis_euro, 0.0)


# ----------------------------------------------------------------------------
# aggregiere_speicher_ist
# ----------------------------------------------------------------------------

def test_aggregiere_speicher_ist_hochrechnung_auf_jahr() -> None:
    # 6 Monate à 100/80 kWh + 50 kWh Netz → Jahres-Hochrechnung × 2
    daten = [
        {"ladung_kwh": 100, "entladung_kwh": 80, "ladung_netz_kwh": 50}
        for _ in range(6)
    ]
    agg = aggregiere_speicher_ist(daten)
    assert agg is not None
    assert _approx(agg.entladung_kwh_jahr, 80 * 6 * 2)
    assert _approx(agg.ladung_netz_kwh_jahr, 50 * 6 * 2)
    assert _approx(agg.ladung_kwh_jahr, 100 * 6 * 2)
    assert agg.anzahl_monate == 6
    assert _approx(agg.jahres_faktor, 2.0)


def test_aggregiere_speicher_ist_zu_wenig_monate_gibt_none() -> None:
    # SPEICHER_IST_MIN_MONATE = 3; mit 2 Monaten muss None zurückkommen.
    assert SPEICHER_IST_MIN_MONATE == 3  # contract test
    daten = [{"ladung_kwh": 100, "entladung_kwh": 80}] * 2
    assert aggregiere_speicher_ist(daten) is None


def test_aggregiere_speicher_ist_ohne_entladung_gibt_none() -> None:
    daten = [{"ladung_kwh": 100, "entladung_kwh": 0}] * 6
    assert aggregiere_speicher_ist(daten) is None


def test_aggregiere_speicher_ist_legacy_key_fallback() -> None:
    # Historische Rows haben `speicher_ladung_netz_kwh` statt `ladung_netz_kwh`.
    daten = [
        {"ladung_kwh": 100, "entladung_kwh": 80, "speicher_ladung_netz_kwh": 25}
        for _ in range(12)
    ]
    agg = aggregiere_speicher_ist(daten)
    assert agg is not None
    assert _approx(agg.ladung_netz_kwh_jahr, 25 * 12)


# ----------------------------------------------------------------------------
# berechne_speicher_einsparung — Wrapper (calculations.py)
# ----------------------------------------------------------------------------

def test_wrapper_prognose_modus_unveraendert_ohne_arbitrage() -> None:
    # Kein ist_entladung_kwh → alter Prognose-Pfad. Erwartete Werte ergeben
    # sich aus: Kapazität × Zyklen × η × (Bezug − Einspeise).
    r = berechne_speicher_einsparung(
        kapazitaet_kwh=10,
        wirkungsgrad_prozent=95,
        netzbezug_preis_cent=30,
        einspeiseverguetung_cent=8,
        nutzt_arbitrage=False,
    )
    nutzbar = 10 * SPEICHER_ZYKLEN_PRO_JAHR * 0.95
    erwartet = nutzbar * 0.22
    assert _approx(r.jahres_einsparung_euro, round(erwartet, 2))
    assert _approx(r.pv_anteil_euro, round(erwartet, 2))
    assert r.arbitrage_anteil_euro == 0


def test_wrapper_prognose_modus_unveraendert_mit_arbitrage_70_30() -> None:
    # 70/30-Modell mit Param-Preisen — alte Logik bleibt erhalten.
    r = berechne_speicher_einsparung(
        kapazitaet_kwh=10,
        wirkungsgrad_prozent=95,
        netzbezug_preis_cent=30,
        einspeiseverguetung_cent=8,
        nutzt_arbitrage=True,
        lade_preis_cent=12,
        entlade_preis_cent=35,
    )
    nutzbar = 10 * SPEICHER_ZYKLEN_PRO_JAHR * 0.95
    erwartet_pv = nutzbar * 0.70 * 0.22
    erwartet_arb = nutzbar * 0.30 * 0.23
    assert _approx(r.jahres_einsparung_euro, round(erwartet_pv + erwartet_arb, 2))


def test_wrapper_ist_modus_delegiert_an_spread_service() -> None:
    # ist_entladung_kwh gepflegt + Netzladung → Delegation an den
    # Spread-Service. Werte müssen mit direktem Service-Aufruf übereinstimmen.
    spread = berechne_speicher_ersparnis(
        entladung_kwh=2000,
        bezug_preis_cent=30,
        einspeise_verg_cent=8,
        ladung_netz_kwh=400,
        wirkungsgrad_prozent=95,
        lade_preis_cent=None,  # nutzt_arbitrage=False → kein Lade-Preis-Bonus
    )
    wrapper = berechne_speicher_einsparung(
        kapazitaet_kwh=10,
        wirkungsgrad_prozent=95,
        netzbezug_preis_cent=30,
        einspeiseverguetung_cent=8,
        nutzt_arbitrage=False,
        ist_entladung_kwh=2000,
        ist_ladung_netz_kwh=400,
    )
    assert _approx(wrapper.jahres_einsparung_euro, round(spread.ersparnis_euro, 2))
    assert _approx(wrapper.pv_anteil_euro, round(spread.pv_anteil_euro, 2))
    assert _approx(wrapper.arbitrage_anteil_euro, round(spread.netz_anteil_euro, 2))
    assert _approx(wrapper.nutzbare_speicherung_kwh, 2000.0)


def test_wrapper_ist_modus_mit_arbitrage_nimmt_lade_preis_mit() -> None:
    spread = berechne_speicher_ersparnis(
        entladung_kwh=2000,
        bezug_preis_cent=30,
        einspeise_verg_cent=8,
        ladung_netz_kwh=400,
        wirkungsgrad_prozent=95,
        lade_preis_cent=12,
    )
    wrapper = berechne_speicher_einsparung(
        kapazitaet_kwh=10,
        wirkungsgrad_prozent=95,
        netzbezug_preis_cent=30,
        einspeiseverguetung_cent=8,
        nutzt_arbitrage=True,
        lade_preis_cent=12,
        entlade_preis_cent=35,  # im IST-Modus irrelevant
        ist_entladung_kwh=2000,
        ist_ladung_netz_kwh=400,
    )
    assert _approx(wrapper.jahres_einsparung_euro, round(spread.ersparnis_euro, 2))
    assert wrapper.arbitrage_anteil_euro > 0  # Netz-Anteil-Vorteil sichtbar


def test_wrapper_ist_modus_co2_basiert_auf_pv_anteil() -> None:
    # CO2-Vorteil bezieht sich auf den PV-Anteil — der Netz-Anteil
    # ersetzt zwar Bezugskosten, aber nicht den Strommix.
    wrapper = berechne_speicher_einsparung(
        kapazitaet_kwh=10,
        wirkungsgrad_prozent=95,
        netzbezug_preis_cent=30,
        einspeiseverguetung_cent=8,
        ist_entladung_kwh=1000,
        ist_ladung_netz_kwh=0,
    )
    # Reiner PV: 1000 kWh × 0.38 = 380 kg
    assert _approx(wrapper.co2_einsparung_kg, 380.0)

    wrapper_mit_netz = berechne_speicher_einsparung(
        kapazitaet_kwh=10,
        wirkungsgrad_prozent=95,
        netzbezug_preis_cent=30,
        einspeiseverguetung_cent=8,
        ist_entladung_kwh=1000,
        ist_ladung_netz_kwh=500,  # × 0.95 = 475 → 525 PV-Anteil
    )
    assert _approx(wrapper_mit_netz.co2_einsparung_kg, round(525 * 0.38, 1))


# ----------------------------------------------------------------------------
# Runner
# ----------------------------------------------------------------------------

ALLE_TESTS = [
    test_reiner_pv_speicher_ohne_netzladung_regression,
    test_netzladung_ohne_ladepreis_kostet_keinen_pv_vorteil,
    test_netzladung_mit_guenstigem_ladepreis_bringt_arbitrage,
    test_netzladung_groesser_als_entladung_geclamped,
    test_bezug_unter_einspeisung_clampt_spread_auf_null,
    test_keine_entladung_keine_ersparnis,
    test_aggregiere_speicher_ist_hochrechnung_auf_jahr,
    test_aggregiere_speicher_ist_zu_wenig_monate_gibt_none,
    test_aggregiere_speicher_ist_ohne_entladung_gibt_none,
    test_aggregiere_speicher_ist_legacy_key_fallback,
    test_wrapper_prognose_modus_unveraendert_ohne_arbitrage,
    test_wrapper_prognose_modus_unveraendert_mit_arbitrage_70_30,
    test_wrapper_ist_modus_delegiert_an_spread_service,
    test_wrapper_ist_modus_mit_arbitrage_nimmt_lade_preis_mit,
    test_wrapper_ist_modus_co2_basiert_auf_pv_anteil,
]


def main() -> int:
    fehler = 0
    for fn in ALLE_TESTS:
        try:
            fn()
            print(f"PASS  {fn.__name__}")
        except Exception:  # noqa: BLE001
            fehler += 1
            print(f"FAIL  {fn.__name__}")
            traceback.print_exc()
    if fehler:
        print(f"\n{fehler} Tests fehlgeschlagen.")
        return 1
    print(f"\nAlle {len(ALLE_TESTS)} Tests grün.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
