"""USt auf den Eigenverbrauch — Bemessungsgrundlage (N-129) und Zeitraum (N-130).

Die beiden Befunde, die dieser Test pinnt:

* **N-129** — die Bemessungsgrundlage hatte vier Formen im Baum. Vier Sichten
  setzten die Vollkosten ein, das Cockpit eine ad-hoc zusammengesetzte Summe,
  die als einzige `anschaffungskosten_alternativ` NICHT las. Dieselbe Anlage
  bekam je Sicht eine andere USt.
* **N-130** — die Selbstkosten je kWh sind eine Jahresgröße. Vier Sichten
  übergaben die Erzeugung ihres gesamten Zeitraums als „Jahres-Erzeugung"; über
  mehrere Jahre kollabierte die USt um den Faktor der Jahresanzahl.

Die Route-Ebene deckt `test_netto_ertrag_vier_wege_symmetrie.py` ab (alle vier
Sichten nennen dieselbe Zahl). Hier steht die Formel selbst.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from backend.core.berechnungen.ust_eigenverbrauch import (
    UstJahresanteil,
    bemessungsgrundlage_aus_investitionen,
    berechne_ust_eigenverbrauch,
    ust_eigenverbrauch_fuer_anlage,
)


# ═══════════════════════════════════════════════════════════════════════════
# 1. N-130 — der Zeitraum kollabiert nicht mehr
# ═══════════════════════════════════════════════════════════════════════════


def test_drei_volle_jahre_ergeben_das_dreifache_eines_jahres():
    """Der Kern von N-130: gleiche Jahre ⇒ USt skaliert linear mit ihrer Zahl.

    Vorher lief die Rechnung über die Zeitraum-Summen — 3.000 kWh Eigenverbrauch
    gegen 9.000 kWh Erzeugung bei EINER Jahres-AfA ⇒ exakt ein Drittel des
    richtigen Betrags. Rot verifiziert gegen die Vorfassung: 63,33 statt 190,00.
    """
    ein_jahr = [UstJahresanteil(jahr=2024, eigenverbrauch_kwh=1000.0, pv_kwh=3000.0)]
    drei_jahre = [
        UstJahresanteil(jahr=j, eigenverbrauch_kwh=1000.0, pv_kwh=3000.0)
        for j in (2024, 2025, 2026)
    ]
    kwargs = dict(
        bemessungsgrundlage_euro=60000.0,
        betriebskosten_jahr_euro=0.0,
        ust_satz_prozent=19.0,
    )

    einer = berechne_ust_eigenverbrauch(ein_jahr, **kwargs)
    drei = berechne_ust_eigenverbrauch(drei_jahre, **kwargs)

    # AfA 60.000/20 = 3.000 €/Jahr; Selbstkosten 3.000/3.000 kWh = 1,00 €/kWh
    # ⇒ 1.000 kWh × 1,00 € × 19 % = 190,00 € je Jahr.
    assert einer == pytest.approx(190.0, abs=0.01)
    assert drei == pytest.approx(570.0, abs=0.01)
    assert drei == pytest.approx(3 * einer, abs=0.01)


def test_jahre_mit_verschiedener_ausbeute_werden_nicht_vermischt():
    """Ein schwaches und ein starkes Jahr dürfen sich nicht wegmitteln.

    Die alte Formel bildete EINEN Quotienten über beide Jahre; damit bekam der
    Eigenverbrauch des ertragsschwachen Jahres denselben (zu niedrigen)
    Selbstkosten-Satz wie der des starken.
    """
    anteile = [
        UstJahresanteil(jahr=2024, eigenverbrauch_kwh=500.0, pv_kwh=1000.0),
        UstJahresanteil(jahr=2025, eigenverbrauch_kwh=500.0, pv_kwh=4000.0),
    ]
    ergebnis = berechne_ust_eigenverbrauch(
        anteile,
        bemessungsgrundlage_euro=20000.0,
        betriebskosten_jahr_euro=0.0,
        ust_satz_prozent=19.0,
    )

    # AfA 1.000 €/Jahr ⇒ 2024: 500 × (1000/1000) × 19 % = 95,00 €
    #                     2025: 500 × (1000/4000) × 19 % = 23,75 €
    assert ergebnis == pytest.approx(118.75, abs=0.01)
    # Die vermischte Rechnung käme auf 1.000 × (1000/5000) × 19 % = 38,00 € —
    # sie ist nicht bloß ungenau, sie ist um den Faktor 3 zu klein.
    assert ergebnis > 3 * 38.0 - 1.0


# ═══════════════════════════════════════════════════════════════════════════
# 2. Angeschnittene Jahre zählen anteilig (Entscheid Gernot 2026-08-04)
# ═══════════════════════════════════════════════════════════════════════════


def test_halbes_jahr_traegt_halbe_abschreibung():
    """Sechs Betriebsmonate ⇒ halbe AfA, nicht die volle gegen halben Ertrag."""
    anteil_halb = [UstJahresanteil(
        jahr=2024, eigenverbrauch_kwh=500.0, pv_kwh=1500.0, monate=6
    )]
    anteil_voll = [UstJahresanteil(
        jahr=2024, eigenverbrauch_kwh=500.0, pv_kwh=1500.0, monate=12
    )]
    kwargs = dict(
        bemessungsgrundlage_euro=60000.0,
        betriebskosten_jahr_euro=600.0,
        ust_satz_prozent=19.0,
    )

    halb = berechne_ust_eigenverbrauch(anteil_halb, **kwargs)
    voll = berechne_ust_eigenverbrauch(anteil_voll, **kwargs)

    assert halb == pytest.approx(voll / 2, abs=0.01)
    # (3.000 + 600) × 6/12 = 1.800 € auf 1.500 kWh = 1,20 €/kWh
    # ⇒ 500 × 1,20 × 19 % = 114,00 €
    assert halb == pytest.approx(114.0, abs=0.01)


def test_mehr_als_zwoelf_monate_werden_gekappt():
    """Ein Aufrufer, der versehentlich 13 Monate zählt, verschiebt nichts."""
    kwargs = dict(
        bemessungsgrundlage_euro=20000.0,
        betriebskosten_jahr_euro=0.0,
        ust_satz_prozent=19.0,
    )
    dreizehn = berechne_ust_eigenverbrauch(
        [UstJahresanteil(jahr=2024, eigenverbrauch_kwh=500.0, pv_kwh=1000.0, monate=13)],
        **kwargs,
    )
    zwoelf = berechne_ust_eigenverbrauch(
        [UstJahresanteil(jahr=2024, eigenverbrauch_kwh=500.0, pv_kwh=1000.0, monate=12)],
        **kwargs,
    )
    assert dreizehn == pytest.approx(zwoelf, abs=0.01)


# ═══════════════════════════════════════════════════════════════════════════
# 3. N-129 — eine Bemessungsgrundlage
# ═══════════════════════════════════════════════════════════════════════════


def _inv(gesamt: float, alternativ: float | None = None):
    return SimpleNamespace(
        anschaffungskosten_gesamt=gesamt, anschaffungskosten_alternativ=alternativ
    )


def test_bemessungsgrundlage_zieht_die_alternativkosten_ab():
    """Ein E-Auto zählt mit seinen MEHRkosten, nicht mit dem Kaufpreis.

    Genau daran lag N-129: vier Sichten setzten hier 52.000 € ein und legten
    damit den vollen Autopreis in die Selbstkosten des PV-Stroms.
    """
    invs = [_inv(15000.0), _inv(52000.0, 35000.0), _inv(18000.0, 8000.0)]
    assert bemessungsgrundlage_aus_investitionen(invs) == pytest.approx(42000.0)


def test_teurere_alternative_senkt_die_grundlage_nicht():
    """Klemmung je Position — sonst subventioniert eine Position eine andere."""
    invs = [_inv(15000.0), _inv(5000.0, 9000.0)]
    assert bemessungsgrundlage_aus_investitionen(invs) == pytest.approx(15000.0)


def test_fehlende_felder_zaehlen_als_null():
    """`None` in beiden Spalten ist der Normalfall bei Altbestand."""
    invs = [_inv(None), _inv(12000.0, None), SimpleNamespace()]
    assert bemessungsgrundlage_aus_investitionen(invs) == pytest.approx(12000.0)


# ═══════════════════════════════════════════════════════════════════════════
# 4. Die Vorprüfung des Steuerregimes
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.parametrize("behandlung", [None, "keine_ust", "kleinunternehmer"])
def test_ohne_regelbesteuerung_faellt_keine_ust_an(behandlung):
    anlage = SimpleNamespace(steuerliche_behandlung=behandlung, ust_satz_prozent=19.0)
    assert ust_eigenverbrauch_fuer_anlage(
        anlage,
        jahresanteile=[UstJahresanteil(jahr=2024, eigenverbrauch_kwh=1000.0, pv_kwh=2000.0)],
        bemessungsgrundlage_euro=20000.0,
        betriebskosten_jahr_euro=0.0,
    ) == 0.0


def test_fehlender_satz_faellt_auf_neunzehn_prozent():
    anlage = SimpleNamespace(steuerliche_behandlung="regelbesteuerung", ust_satz_prozent=None)
    mit_default = ust_eigenverbrauch_fuer_anlage(
        anlage,
        jahresanteile=[UstJahresanteil(jahr=2024, eigenverbrauch_kwh=1000.0, pv_kwh=2000.0)],
        bemessungsgrundlage_euro=20000.0,
        betriebskosten_jahr_euro=0.0,
    )
    # 1.000 × (1.000/2.000) × 19 % = 95,00 €
    assert mit_default == pytest.approx(95.0, abs=0.01)


def test_jahr_ohne_erzeugung_traegt_null_statt_zu_krachen():
    """Monate vor der Inbetriebnahme liefern echte Nullen — kein ZeroDivision."""
    anteile = [
        UstJahresanteil(jahr=2023, eigenverbrauch_kwh=0.0, pv_kwh=0.0, monate=4),
        UstJahresanteil(jahr=2024, eigenverbrauch_kwh=500.0, pv_kwh=1000.0, monate=12),
    ]
    assert berechne_ust_eigenverbrauch(
        anteile,
        bemessungsgrundlage_euro=20000.0,
        betriebskosten_jahr_euro=0.0,
        ust_satz_prozent=19.0,
    ) == pytest.approx(95.0, abs=0.01)
