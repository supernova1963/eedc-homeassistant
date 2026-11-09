"""CO₂-Äquivalente im Layer (Päckchen Y, 9.11.2026) — eine Formel, ein Ort (ADR-001/DI-2).

Bis dahin zwei Faktorensätze und keiner im Layer: *Auswertungen → CO₂* rechnete im Client (12,5 kg je Baum, 0,12 kg je
km, 230 kg je Flug), ``/cockpit/nachhaltigkeit`` in der Route (``co2 / 20`` für Bäume). Jetzt bildet
``core/berechnungen/co2_aequivalente.py`` alle vier Größen; diese Datei hält die Zahlen der Auswertung fest und den
Gleichstand Route ↔ Layer.

Schwesterdateien: test_co2_autarkie_sichten_symmetrie.py (dieselbe Route, CO₂-Bilanz), test_co2_bilanz_ha_export_symmetrie.py.
"""

import pytest

from backend.core.berechnungen import CO2_FAKTOREN, co2_aequivalente


def test_tausend_kg_in_vier_anschauungsgroessen():
    a = co2_aequivalente(1000.0)
    assert a.baeume == pytest.approx(80.0)          # ÷ 12,5 kg je Baum und Jahr
    assert round(a.auto_km) == 8333                 # ÷ 0,12 kg je km
    assert round(a.fluege, 1) == 4.3                # ÷ 230 kg je Flug
    assert round(a.fluege_km) == 4348               # ÷ 0,23 kg je Flug-km


@pytest.mark.parametrize("co2", [0.0, None, -50.0])
def test_keine_oder_negative_menge_ergibt_null(co2):
    a = co2_aequivalente(co2)
    assert (a.baeume, a.auto_km, a.fluege, a.fluege_km) == (0.0, 0.0, 0.0, 0.0)


def test_die_faktoren_sind_die_heute_gezeigten_und_haengen_zusammen():
    f = co2_aequivalente(1.0).faktoren
    assert f is CO2_FAKTOREN
    assert (f.kg_co2_je_baum_jahr, f.kg_co2_je_auto_km, f.kg_co2_je_flug_km, f.km_je_kurzstreckenflug) == (
        12.5, 0.12, 0.23, 1000.0)
    # Flug und Flug-km an denselben zwei Konstanten: 1000 km × 0,23 kg/km = 230 kg (die Unterzeile «à 1000 km»).
    assert f.kg_co2_je_flug == 230.0


def test_linear_die_summe_der_monate_ist_das_aequivalent_der_summe():
    """Darauf baut der Client: er summiert die Monats-Äquivalente des gewählten Jahres wie die kg."""
    monate = [12.3, 450.0, 0.0, 987.6]
    summe = co2_aequivalente(sum(monate))
    for feld in ("baeume", "auto_km", "fluege", "fluege_km"):
        assert sum(getattr(co2_aequivalente(m), feld) for m in monate) == pytest.approx(getattr(summe, feld))


@pytest.mark.asyncio
async def test_die_route_liefert_die_aequivalente_aus_dem_layer(db):
    """``/cockpit/nachhaltigkeit``: gesamt und je Monat aus ``co2_aequivalente``, Bäume ÷ 12,5 (bis Päckchen Y ÷ 20)."""
    from backend.api.routes.cockpit.nachhaltigkeit import get_nachhaltigkeit
    from backend.tests.test_netto_ertrag_vier_wege_symmetrie import anlage_mit_v2h_und_bhkw

    anlage_id = await anlage_mit_v2h_und_bhkw(db, km=1000.0, name="CO2-Aequivalente")
    r = await get_nachhaltigkeit(anlage_id=anlage_id, db=db)
    gesamt = co2_aequivalente(r.co2_gesamt_kg)
    assert r.co2_gesamt_kg > 0 and r.monatswerte
    assert r.aequivalent_baeume == int(r.co2_gesamt_kg / 12.5) != int(r.co2_gesamt_kg / 20)
    # Gesamt rechnet die Route auf der ungerundeten Summe und schneidet ab, `co2_gesamt_kg` ist auf 0,1 kg gerundet ⇒ < 1,5.
    assert r.aequivalent_auto_km == pytest.approx(gesamt.auto_km, abs=1.5)
    assert r.aequivalent_fluege_km == pytest.approx(gesamt.fluege_km, abs=1.5)
    assert r.aequivalent_fluege == pytest.approx(gesamt.fluege, abs=0.05)
    assert r.co2_faktoren.kg_co2_je_flug == pytest.approx(230.0)
    for m in r.monatswerte:   # je Monat vom angezeigten (gerundeten) Monatswert — dem, den der Client summiert
        assert m.co2_aequivalente.baeume == pytest.approx(m.co2_gesamt_kg / 12.5)
        assert m.co2_aequivalente.fluege == pytest.approx(co2_aequivalente(m.co2_gesamt_kg).fluege)
