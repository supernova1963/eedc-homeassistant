"""Phase 2a: kanonische E-Mob-Heimladungs-Quelle (strukturelle Regel).

Anlass: `docs/KONZEPT-WALLBOX-EAUTO.md` Abschnitt »Phase 2a — Umsetzungsplan«,
Etappe 1. Eine Magnituden-Heuristik (`wb.ladung_kwh >= ea.ladung_kwh`) kippt
bei verirrten Streudaten auf der E-Auto-IMD (#262 junky84). Der Helfer
`get_emob_heimladung_canonical` wählt stattdessen **strukturell**:
Wallbox vorhanden + hat Heimladung → Wallbox ist Quelle; sonst E-Auto.

Geprüft:
  1. evcc-Setup: WB hat Heimladung → Wallbox gewinnt.
  2. KERN-FIX: E-Auto-Streudaten GRÖSSER als WB → Wallbox gewinnt trotzdem
     (Magnitude hätte hier die falsche Quelle gewählt).
  3. Steckerlader/Schuko (keine WB / WB leer) → E-Auto gewinnt (Fallback).
  4. Beide leer → quelle="leer".
  5. Multi-Wallbox: alle WB-Ladepunkte werden summiert.
  6. Trias-Garantie `pv + netz == ladung_kwh` (nie feldweise gemischt).
  7. Externe Ladung orthogonal: Quelle mit höheren externen Kosten gewinnt.
"""

from __future__ import annotations

from backend.services.eauto_wirtschaftlichkeit import (
    get_emob_heimladung_canonical,
)


def test_evcc_setup_wallbox_ist_quelle():
    """WB trägt die Heimladung (evcc-Import), E-Auto nur km → Wallbox gewinnt."""
    pool = get_emob_heimladung_canonical(
        eauto_imd_data=[{"km_gefahren": 1000}],
        wallbox_imd_data=[{
            "ladung_kwh": 500, "ladung_pv_kwh": 200, "ladung_netz_kwh": 300,
        }],
    )
    assert pool.quelle == "wallbox"
    assert pool.ladung_kwh == 500
    assert pool.pv_kwh == 200
    assert pool.netz_kwh == 300


def test_eauto_streudaten_groesser_wallbox_gewinnt_trotzdem():
    """KERN der strukturellen Regel: E-Auto-IMD trägt GRÖSSERE (verirrte)
    Heimladung als die Wallbox — die strukturelle Regel wählt dennoch die
    Wallbox. Eine Magnituden-Heuristik hätte hier das E-Auto gewählt (und damit
    die Streudaten als Wahrheit genommen).
    """
    pool = get_emob_heimladung_canonical(
        eauto_imd_data=[{
            "ladung_kwh": 3300, "ladung_pv_kwh": 1000, "ladung_netz_kwh": 2300,
            "km_gefahren": 1000,
        }],
        wallbox_imd_data=[{
            "ladung_kwh": 500, "ladung_pv_kwh": 200, "ladung_netz_kwh": 300,
        }],
    )
    # ⚑ N-555 Stufe 2 (26.09.2026): die strukturelle Regel „Wallbox vorhanden ⇒ die Auto-
    # Werte zählen nicht" (Phase 2a / Entscheidung 1) ist mit Gernots Modell vom 24.09.
    # **gedreht** (Konzept Heimladung/Fahrverbrauch 7.2, Regel 2 Schritt 1 und Anhang C,
    # „Modellwechsel"): trägt das Auto „Heim: PV/Netz", ist das seine eigene Messung, auch
    # neben der Wallbox. Das #262-Risiko (Streudaten am Auto) fängt seither der
    # Daten-Checker — „Autos zusammen mehr als die Wallbox" (Regel 7, E2: weiterrechnen
    # und warnen, nicht kappen); seine Probe steht in `test_n555_stufe2_messung_je_auto.py`
    # §S2-6. Diese Probe hält jetzt fest: die Wallbox bestimmt den Monat (`quelle`), der Topf
    # ist die Messung des Autos, der Rest ist 0 (nie unter 0).
    assert pool.quelle == "wallbox"
    assert pool.ladung_kwh == 3300
    assert pool.pv_kwh == 1000
    assert pool.netz_kwh == 2300


def test_steckerlader_keine_wallbox_eauto_ist_quelle():
    """Schuko/Steckerlader: keine Wallbox-Investition → E-Auto bleibt Quelle
    (Fallback, kein Breaking Change für sehr häufiges Setup)."""
    pool = get_emob_heimladung_canonical(
        eauto_imd_data=[{
            "ladung_kwh": 800, "ladung_pv_kwh": 500, "ladung_netz_kwh": 300,
            "km_gefahren": 1200,
        }],
        wallbox_imd_data=[],
    )
    assert pool.quelle == "e-auto"
    assert pool.ladung_kwh == 800
    assert pool.pv_kwh == 500
    assert pool.netz_kwh == 300


def test_wallbox_ohne_heimladung_eauto_ist_quelle():
    """Wallbox-Investition existiert, hat aber im Zeitraum keine Heimladung
    → E-Auto gewinnt (Entscheidung 1: »vorhanden + HAT Heimladung«)."""
    pool = get_emob_heimladung_canonical(
        eauto_imd_data=[{
            "ladung_kwh": 400, "ladung_pv_kwh": 250, "ladung_netz_kwh": 150,
            "km_gefahren": 900,
        }],
        wallbox_imd_data=[{"ladung_kwh": 0, "ladevorgaenge": 0}],
    )
    assert pool.quelle == "e-auto"
    assert pool.ladung_kwh == 400


def test_beide_leer_quelle_leer():
    """Keine Heimladung auf beiden Seiten → quelle='leer'."""
    pool = get_emob_heimladung_canonical(
        eauto_imd_data=[{"km_gefahren": 500}],
        wallbox_imd_data=[{"ladevorgaenge": 0}],
    )
    assert pool.quelle == "leer"
    assert pool.ladung_kwh == 0


def test_multi_wallbox_summiert_alle_ladepunkte():
    """Garage + Carport = zwei Ladepunkte → Heimladung gesamt = Summe (keine
    Unterzählung durch »größte WB picken«)."""
    pool = get_emob_heimladung_canonical(
        eauto_imd_data=[{"km_gefahren": 1000}],
        wallbox_imd_data=[
            {"ladung_kwh": 500, "ladung_pv_kwh": 300, "ladung_netz_kwh": 200},
            {"ladung_kwh": 300, "ladung_pv_kwh": 100, "ladung_netz_kwh": 200},
        ],
    )
    assert pool.quelle == "wallbox"
    assert pool.ladung_kwh == 800
    assert pool.pv_kwh == 400
    assert pool.netz_kwh == 400


def test_trias_garantie_pv_plus_netz_gleich_ladung():
    """`pv + netz == ladung_kwh` — Trias kommt geschlossen aus einer Quelle,
    nie feldweise gemischt (#262-Wurzel: gemischte max()-Felder → PV-Anteil
    > 100 %). Netz wird hier aus Total − PV abgeleitet (kein netz-Key)."""
    pool = get_emob_heimladung_canonical(
        eauto_imd_data=[{"km_gefahren": 1000}],
        wallbox_imd_data=[{"ladung_kwh": 500, "ladung_pv_kwh": 200}],
    )
    assert pool.pv_kwh == 200
    assert pool.netz_kwh == 300  # 500 − 200 abgeleitet
    assert pool.pv_kwh + pool.netz_kwh == pool.ladung_kwh


def test_extern_orthogonal_hoehere_kosten_gewinnt():
    """Externe Ladung unabhängig von der Heimladungs-Quelle: das Paar (kWh, €)
    kommt aus der Seite mit den höheren externen Kosten — hier dem E-Auto,
    obwohl die Wallbox die Heimladungs-Quelle ist."""
    pool = get_emob_heimladung_canonical(
        eauto_imd_data=[{
            "km_gefahren": 1000,
            "ladung_extern_kwh": 120, "ladung_extern_euro": 60.0,
        }],
        wallbox_imd_data=[{
            "ladung_kwh": 500, "ladung_pv_kwh": 200, "ladung_netz_kwh": 300,
            "ladung_extern_kwh": 10, "ladung_extern_euro": 5.0,
        }],
    )
    assert pool.quelle == "wallbox"      # Heimladung von der WB
    assert pool.extern_kwh == 120        # extern vom E-Auto
    assert pool.extern_euro == 60.0
