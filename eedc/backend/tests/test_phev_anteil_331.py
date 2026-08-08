"""#331 Phase 4 — der elektrische Anteil eines Plug-in-Hybrids.

Drei Ebenen, in dieser Reihenfolge:

A. **Layer-Kontrakt** — `teile_fahrleistung` als reine Funktion: Wege-Reihenfolge
   (gemessen vor geschätzt vor heutigem Verhalten) und die Deckelung, ohne die
   negative Verbrenner-Kilometer entstünden.
B. **Beide Achsen rufen dieselbe Funktion** — IST (`eauto_wirtschaftlichkeit`)
   und Prognose (`calculations`) teilen dieselbe Fahrleistung gleich auf. Das
   ist der Punkt, an dem die Drift verhindert wird; ein Anteil, der nur in einer
   Achse wirkt, ist die Klasse, die dieses Projekt wiederholt getroffen hat.
C. **BEV-Invarianz** — ohne gepflegtes `eigener_verbrauch_l_100km` ändert sich
   **keine** Zahl gegenüber dem Stand vor #331. Das ist Entscheidung 3 und der
   Grund, warum es keinen Fahrzeugtyp und keinen Schalter gibt.

⚠ Die Fixture führt BEV **und** PHEV, mit und ohne gepflegten Fahrverbrauch —
ein Symmetrie-Test deckt nur die Achsen ab, die die Fixture variiert
([[feedback_aggregator_symmetrie]]).
"""

from __future__ import annotations

import pytest

from backend.core.berechnungen.phev_anteil import teile_fahrleistung
from backend.core.calculations import berechne_eauto_einsparung, berechne_co2_bilanz
from backend.core.investition_parameter import PARAM_E_AUTO
from backend.core.wirtschaftlichkeit_defaults import BENZIN_VERBRAUCH_DEFAULT_L_100KM
from backend.services.eauto_wirtschaftlichkeit import (
    berechne_eauto_ersparnis,
    berechne_eauto_ersparnis_periode,
    eigener_verbrauch_l_100km,
    fossil_getankte_liter,
)


# ── Parameter-Fixtures ──────────────────────────────────────────────────────

BEV = {
    PARAM_E_AUTO["VERBRAUCH_KWH_100KM"]: 18,
    PARAM_E_AUTO["VERGLEICH_VERBRAUCH_L_100KM"]: 7.5,
    PARAM_E_AUTO["BENZINPREIS_EURO"]: 1.80,
}
PHEV_GEMESSEN = {**BEV, PARAM_E_AUTO["EIGENER_VERBRAUCH_L_100KM"]: 6.0}
PHEV_GESCHAETZT = {
    **PHEV_GEMESSEN,
    PARAM_E_AUTO["ELEKTRISCHER_FAHRANTEIL_PROZENT"]: 40,
}


# ══════════════════════════════════════════════════════════════════════════
# A. Layer-Kontrakt
# ══════════════════════════════════════════════════════════════════════════

def test_gemessen_schlaegt_geschaetzt():
    """Liegt ein Fahrverbrauch vor, wird er benutzt — der Prozentwert nicht."""
    a = teile_fahrleistung(
        km_gefahren=1000, fahrverbrauch_kwh=90, verbrauch_kwh_100km=18,
        anteil_prozent=90,     # widerspricht der Messung absichtlich
    )
    assert a.quelle == "gemessen"
    assert a.km_elektrisch == pytest.approx(500.0)   # 90 kWh / 18 × 100
    assert a.km_verbrenner == pytest.approx(500.0)


def test_prozent_greift_nur_ohne_messung():
    a = teile_fahrleistung(km_gefahren=1000, anteil_prozent=40)
    assert a.quelle == "prozent"
    assert a.km_elektrisch == pytest.approx(400.0)
    assert a.km_verbrenner == pytest.approx(600.0)


def test_ohne_jede_angabe_bleibt_alles_elektrisch():
    """Heutiges Verhalten — kein erfundener Richtwert (Entscheidung 4)."""
    a = teile_fahrleistung(km_gefahren=1000)
    assert a.quelle == "unbestimmt"
    assert a.km_elektrisch == pytest.approx(1000.0)
    assert a.km_verbrenner == pytest.approx(0.0)


def test_deckelung_verhindert_negative_verbrenner_km():
    """Zu großzügiger Zähler / zu niedriger Kennwert ⇒ Anteil bleibt bei 100 %.

    Ohne `min(...)` kämen hier 1666 elektrische von 1000 gefahrenen Kilometern
    heraus — und damit −666 Verbrenner-km, die als *Gewinn* in die Ersparnis
    liefen. Gedeckelt bleibt der Pflegefehler sichtbar (Verbrenner-Anteil 0).
    """
    a = teile_fahrleistung(
        km_gefahren=1000, fahrverbrauch_kwh=300, verbrauch_kwh_100km=18,
    )
    assert a.km_elektrisch == pytest.approx(1000.0)
    assert a.km_verbrenner == pytest.approx(0.0)
    assert a.km_gesamt == pytest.approx(1000.0)


def test_prozent_wird_geklemmt_und_summe_bleibt_erhalten():
    for p, erwartet_e in ((-20, 0.0), (140, 1000.0)):
        a = teile_fahrleistung(km_gefahren=1000, anteil_prozent=p)
        assert a.km_elektrisch == pytest.approx(erwartet_e)
        assert a.km_gesamt == pytest.approx(1000.0)


def test_ohne_kennwert_faellt_der_gemessene_weg_aus():
    """Kein `verbrauch_kwh_100km` ⇒ kWh sind nicht in km übersetzbar."""
    a = teile_fahrleistung(
        km_gefahren=1000, fahrverbrauch_kwh=90, verbrauch_kwh_100km=0,
        anteil_prozent=40,
    )
    assert a.quelle == "prozent"


def test_eigener_verbrauch_hat_keinen_default():
    """Entscheidung 3: das gesetzte Feld IST die Aussage."""
    assert eigener_verbrauch_l_100km(None) is None
    assert eigener_verbrauch_l_100km({}) is None
    assert eigener_verbrauch_l_100km(BEV) is None
    assert eigener_verbrauch_l_100km({"eigener_verbrauch_l_100km": 0}) is None
    assert eigener_verbrauch_l_100km(PHEV_GEMESSEN) == pytest.approx(6.0)


# ══════════════════════════════════════════════════════════════════════════
# B. Beide Achsen teilen gleich auf
# ══════════════════════════════════════════════════════════════════════════

def test_beide_achsen_teilen_dieselbe_fahrleistung_gleich():
    """IST und Prognose kommen bei gleichem Anteil auf dieselben km.

    Die Wege unterscheiden sich bewusst (IST misst, Prognose schätzt) — bei
    gepflegtem Prozentwert und ohne Messung müssen sie sich treffen.
    """
    ist = berechne_eauto_ersparnis(
        km_gefahren=10000,
        ladung_netz_kwh=0,
        ladung_extern_euro=0,
        wallbox_strompreis_cent=30,
        eauto_parameter=PHEV_GESCHAETZT,
        fahrverbrauch_kwh=None,          # keine Messung ⇒ Prozentweg
    )
    prognose = berechne_eauto_einsparung(
        km_jahr=10000,
        verbrauch_kwh_100km=18,
        pv_anteil_prozent=60,
        strompreis_cent=30,
        benzinpreis_euro_liter=1.80,
        benzin_verbrauch_liter_100km=7.5,
        eigener_verbrauch_l_100km=6.0,
        elektrischer_fahranteil_prozent=40,
    )
    assert ist.km_elektrisch == pytest.approx(prognose.km_elektrisch)
    assert ist.km_verbrenner == pytest.approx(prognose.km_verbrenner)


def test_prognose_belastet_nicht_zweimal_dieselbe_strecke():
    """Der Strombedarf folgt den elektrischen km, nicht allen.

    Auf der Prognose-Achse wird der Strombedarf AUS der Fahrleistung
    abgeleitet. Bliebe er bei 100 %, zahlte ein Plug-in-Hybrid Strom für alle
    Kilometer UND Benzin für die verbrennergefahrenen — dieselbe Strecke
    zweimal.
    """
    voll = berechne_eauto_einsparung(
        km_jahr=10000, verbrauch_kwh_100km=18, pv_anteil_prozent=0,
        strompreis_cent=30, benzinpreis_euro_liter=1.80,
        benzin_verbrauch_liter_100km=7.5,
    )
    halb = berechne_eauto_einsparung(
        km_jahr=10000, verbrauch_kwh_100km=18, pv_anteil_prozent=0,
        strompreis_cent=30, benzinpreis_euro_liter=1.80,
        benzin_verbrauch_liter_100km=7.5,
        eigener_verbrauch_l_100km=6.0, elektrischer_fahranteil_prozent=50,
    )
    assert halb.strom_kosten_euro == pytest.approx(voll.strom_kosten_euro / 2)
    # Der Vergleichs-Benziner bleibt über ALLE km gestellt (Entscheidung 5).
    assert halb.benzin_kosten_alternativ_euro == pytest.approx(
        voll.benzin_kosten_alternativ_euro
    )
    # 5000 km × 6 L/100 km × 1,80 €
    assert halb.fossile_kosten_euro == pytest.approx(540.0)


def test_ist_periode_trifft_ist_einzelmonat():
    """Ein Monat über die Perioden-Funktion == derselbe Monat einzeln."""
    einzel = berechne_eauto_ersparnis(
        km_gefahren=1000, ladung_netz_kwh=100, ladung_extern_euro=0,
        wallbox_strompreis_cent=30, eauto_parameter=PHEV_GEMESSEN,
        monats_benzinpreis_euro=1.90, fahrverbrauch_kwh=90,
    )
    periode = berechne_eauto_ersparnis_periode(
        km_pro_monat=[(2026, 5, 1000)],
        ladung_netz_kwh_gesamt=100, ladung_extern_euro_gesamt=0,
        wallbox_strompreis_cent=30, eauto_parameter=PHEV_GEMESSEN,
        monats_benzinpreis_lookup={(2026, 5): 1.90},
        fahrverbrauch_kwh_gesamt=90,
    )
    assert periode.fossile_kosten_euro == pytest.approx(einzel.fossile_kosten_euro)
    assert periode.ersparnis_euro == pytest.approx(einzel.ersparnis_euro)
    assert periode.km_verbrenner == pytest.approx(einzel.km_verbrenner)


def test_fossile_kosten_mindern_die_ersparnis_genau_einmal():
    ohne = berechne_eauto_ersparnis(
        km_gefahren=1000, ladung_netz_kwh=100, ladung_extern_euro=0,
        wallbox_strompreis_cent=30, eauto_parameter=BEV,
        monats_benzinpreis_euro=1.80, fahrverbrauch_kwh=90,
    )
    mit = berechne_eauto_ersparnis(
        km_gefahren=1000, ladung_netz_kwh=100, ladung_extern_euro=0,
        wallbox_strompreis_cent=30, eauto_parameter=PHEV_GEMESSEN,
        monats_benzinpreis_euro=1.80, fahrverbrauch_kwh=90,
    )
    # 500 Verbrenner-km × 6 L/100 km × 1,80 € = 54 €
    assert mit.fossile_kosten_euro == pytest.approx(54.0)
    assert mit.ersparnis_euro == pytest.approx(ohne.ersparnis_euro - 54.0)
    # Die Vergleichsrechnung selbst bleibt unangetastet.
    assert mit.benzin_kosten_euro == pytest.approx(ohne.benzin_kosten_euro)
    assert mit.strom_kosten_euro == pytest.approx(ohne.strom_kosten_euro)


def test_co2_bilanz_zieht_denselben_kraftstoff_ab():
    """Geld und CO₂ dürfen nicht zwei Wahrheiten haben."""
    liter = fossil_getankte_liter(
        km_je_fahrzeug={1: 1000},
        fahrverbrauch_je_fahrzeug={1: 90},
        params_je_fahrzeug={1: PHEV_GEMESSEN},
    )
    assert liter == pytest.approx(30.0)          # 500 km × 6 L/100 km

    ohne = berechne_co2_bilanz(
        eigenverbrauch_kwh=0, emob_km=1000, emob_netz_ladung_kwh=0,
        benzin_verbrauch_liter=75,
    )
    mit = berechne_co2_bilanz(
        eigenverbrauch_kwh=0, emob_km=1000, emob_netz_ladung_kwh=0,
        benzin_verbrauch_liter=75, fossil_getankt_liter=liter,
    )
    assert mit.co2_emob_kg < ohne.co2_emob_kg
    assert ohne.co2_emob_kg - mit.co2_emob_kg == pytest.approx(30.0 * 2.37, rel=1e-6)


def test_fossil_getankte_liter_ignoriert_bev_im_gemischten_haushalt():
    """Ein BEV neben einem PHEV trägt 0 bei — je Fahrzeug seine Parameter."""
    liter = fossil_getankte_liter(
        km_je_fahrzeug={1: 1000, 2: 2000},
        fahrverbrauch_je_fahrzeug={1: 90, 2: 360},
        params_je_fahrzeug={1: PHEV_GEMESSEN, 2: BEV},
    )
    assert liter == pytest.approx(30.0)


# ══════════════════════════════════════════════════════════════════════════
# C. BEV-Invarianz — ohne das Feld ändert sich keine Zahl
# ══════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("params", [None, {}, BEV])
@pytest.mark.parametrize("fahrverbrauch", [180, 90, None])
def test_bev_bleibt_zahlengleich(params, fahrverbrauch):
    """⚠ Der Fall `fahrverbrauch=90` ist der tragende.

    Bei 180 kWh / 18 kWh je 100 km erklärt die Messung die ganzen 1000 km — dann
    ist der Verbrenner-Anteil schon durch die Deckelung 0, und ein versehentlich
    eingebauter Default für `eigener_verbrauch_l_100km` bliebe unbemerkt. Genau
    das ist beim Sprengsatz-Durchlauf passiert: die erste Fassung dieses Tests
    führte nur die volle Deckung und blieb grün, als der Default eingebaut wurde.
    Mit 90 kWh sind rechnerisch 500 km elektrisch — ein Default würde die
    anderen 500 km sofort in Kraftstoffkosten übersetzen.
    """
    r = berechne_eauto_ersparnis(
        km_gefahren=1000, ladung_netz_kwh=200, ladung_extern_euro=5,
        wallbox_strompreis_cent=30, eauto_parameter=params,
        monats_benzinpreis_euro=1.80, fahrverbrauch_kwh=fahrverbrauch,
    )
    assert r.fossile_kosten_euro == 0.0
    assert r.ersparnis_euro == pytest.approx(
        r.benzin_kosten_euro - r.strom_kosten_euro
    )


@pytest.mark.parametrize("params", [None, {}, BEV])
def test_bev_prognose_bleibt_zahlengleich_auch_mit_gepflegtem_prozentwert(params):
    """Ein Prozentwert ohne Verbrenner-Verbrauch kostet nichts.

    Der Anteil teilt dann zwar die Kilometer, aber ohne
    `eigener_verbrauch_l_100km` gibt es keine Tankrechnung — und der Strombedarf
    darf dadurch **nicht** heimlich schrumpfen.
    """
    r = berechne_eauto_einsparung(
        km_jahr=10000, verbrauch_kwh_100km=18, pv_anteil_prozent=0,
        strompreis_cent=30, benzinpreis_euro_liter=1.80,
        benzin_verbrauch_liter_100km=7.5,
        eigener_verbrauch_l_100km=(params or {}).get("eigener_verbrauch_l_100km"),
    )
    assert r.fossile_kosten_euro == 0.0
    assert r.strom_kosten_euro == pytest.approx(10000 * 18 / 100 * 30 / 100)


def test_prognose_bev_bleibt_zahlengleich():
    r = berechne_eauto_einsparung(
        km_jahr=15000, verbrauch_kwh_100km=18, pv_anteil_prozent=60,
        strompreis_cent=30, benzinpreis_euro_liter=1.65,
        benzin_verbrauch_liter_100km=7.5,
    )
    assert r.fossile_kosten_euro == 0.0
    assert r.km_elektrisch == pytest.approx(15000.0)
    assert r.strom_kosten_euro == pytest.approx(15000 * 18 / 100 * 0.4 * 30 / 100, rel=1e-6)


def test_signatur_default_ist_der_kanonische_wert():
    """N-178: der Signatur-Default stand auf 7,0 gegen den Kanon 7,5.

    Er war tot, solange der einzige Aufrufer den Wert immer übergibt — mit
    Phase 4 wird an dieser Funktion gebaut, also darf er nicht widersprechen.
    """
    ohne_arg = berechne_eauto_einsparung(
        km_jahr=10000, verbrauch_kwh_100km=18, pv_anteil_prozent=0,
        strompreis_cent=0, benzinpreis_euro_liter=1.0,
    )
    assert ohne_arg.benzin_kosten_alternativ_euro == pytest.approx(
        10000 / 100 * BENZIN_VERBRAUCH_DEFAULT_L_100KM
    )
    assert BENZIN_VERBRAUCH_DEFAULT_L_100KM == 7.5
