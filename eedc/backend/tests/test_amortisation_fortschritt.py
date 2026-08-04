"""Layer-Formel: Amortisations-Fortschritt (N-137).

`core/berechnungen/amortisation.py` beantwortet „wie weit bin ich?" aus
GEMESSENEN Erträgen — abzugrenzen von der Amortisations*dauer*
(`core/calculations.py::berechne_roi`), die ein Modell aus einer hochgerechneten
Jahres-Einsparung ist. Beide stehen in *Auswertungen → ROI* nebeneinander und
teilen deshalb denselben Nenner; die Nenner-Gleichheit sichert
`test_amortisation_nenner_symmetrie.py`.

Hier: die Formel selbst, inklusive der Sonderfälle, in denen bewusst KEIN
Ersatzwert erfunden wird.
"""

from __future__ import annotations

from backend.core.berechnungen import berechne_amortisations_fortschritt


def test_fortschritt_und_restlaufzeit():
    r = berechne_amortisations_fortschritt(
        relevante_kosten_euro=12000.0,
        bisherige_ertraege_euro=4800.0,
        jahres_netto_ertrag_euro=1800.0,
        aktuelles_jahr=2026,
    )
    assert r.fortschritt_prozent == 40.0
    assert r.erreicht is False
    assert r.rest_betrag_euro == 7200.0
    # 7200 / (1800/12) = 48 Monate = 4 Jahre
    assert r.rest_monate == 48
    assert r.prognose_jahr == 2030


def test_erreicht_kennt_keine_restlaufzeit():
    r = berechne_amortisations_fortschritt(
        relevante_kosten_euro=10000.0,
        bisherige_ertraege_euro=12000.0,
        jahres_netto_ertrag_euro=1800.0,
        aktuelles_jahr=2026,
    )
    assert r.erreicht is True
    # Nicht bei 100 gedeckelt: eine Anlage, die sich doppelt bezahlt gemacht
    # hat, soll das sagen dürfen.
    assert r.fortschritt_prozent == 120.0
    assert r.rest_betrag_euro == 0.0
    assert r.rest_monate is None
    assert r.prognose_jahr is None


def test_ohne_relevante_kosten_kein_erfundener_fortschritt():
    """Nichts erfasst (oder jede Anschaffung günstiger als ihre Alternative):
    es gibt nichts zu amortisieren — 0 %, nicht „fertig"."""
    r = berechne_amortisations_fortschritt(
        relevante_kosten_euro=0.0,
        bisherige_ertraege_euro=500.0,
        jahres_netto_ertrag_euro=100.0,
        aktuelles_jahr=2026,
    )
    assert r.fortschritt_prozent == 0.0
    assert r.erreicht is False
    assert r.prognose_jahr is None


def test_ohne_jahresertrag_keine_prognose():
    """Ein Anlaufjahr ohne (oder mit negativem) Jahresertrag bekommt keine
    Restlaufzeit angedichtet — geraten wird hier nicht."""
    r = berechne_amortisations_fortschritt(
        relevante_kosten_euro=10000.0,
        bisherige_ertraege_euro=1000.0,
        jahres_netto_ertrag_euro=0.0,
        aktuelles_jahr=2026,
    )
    assert r.fortschritt_prozent == 10.0
    assert r.rest_betrag_euro == 9000.0
    assert r.rest_monate is None
    assert r.prognose_jahr is None


def test_negativer_bisheriger_ertrag_wird_nicht_geschoent():
    r = berechne_amortisations_fortschritt(
        relevante_kosten_euro=10000.0,
        bisherige_ertraege_euro=-250.0,
        jahres_netto_ertrag_euro=1200.0,
        aktuelles_jahr=2026,
    )
    assert r.fortschritt_prozent == -2.5
    assert r.rest_betrag_euro == 10250.0
