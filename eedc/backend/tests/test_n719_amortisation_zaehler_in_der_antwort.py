"""N-719 — die Finanz-Prognose liefert den Zähler des Amortisations-Fortschritts mit (`amortisation_ertraege_euro`).

Die Kachel «Amortisations-Fortschritt» in *Auswertungen → ROI* zeigte im Tooltip `bisherige_ertraege_euro ÷
investition_gesamt_euro` — die Zeitraum-Bilanz gegen die Mehrkosten. Gerechnet ist die Quote aber aus dem Zähler ohne
beide Seiten der sonstigen Positionen und dem Kapitaleinsatz (F-19, `finanz_zerlegung.py::roi_und_fortschritt`).
Gemessen am HEAD `0c3a89fa` (Fall S aus `test_n699_…`: PV 10 000 €, 2024–25, Betriebskosten 120 €/Jahr, Reparatur
500 € als sonstige Ausgabe): Tooltip «1.276 € ÷ 10.000 €» (ergäbe 12,8 %) neben «= 16,9 %»; richtig 1.776 ÷ 10.500.
Der Server lieferte den Nenner (`kapitaleinsatz_euro`), den Zähler nicht.

Soll: der Zähler steht in der Antwort; Zähler ÷ Nenner = die ausgewiesene Quote. Die Zeitraum-Bilanz
`bisherige_ertraege_euro` bleibt (= Cockpit-Netto-Ertrag, `test_aussichten_finanz_aggregat_symmetrie.py`).

Schwesterdateien: frontend `src/components/roi/RoiAnalyse.fortschritt.test.tsx` (der Tooltip liest die Operanden),
test_n699_pdf_betriebskosten_amortisation.py (Fall S), test_kapitaleinsatz_vier_sichten_symmetrie.py.
"""

from __future__ import annotations

import pytest

from backend.tests.test_n699_pdf_betriebskosten_amortisation import _m, _seed


@pytest.mark.asyncio
@pytest.mark.parametrize("typ, bilanz, zaehler, nenner, prozent", [
    # Reparatur 500 € (Ausgabe): Bilanz 1 776 − 500 = 1 276; Zähler 1 276 + 500 = 1 776; Nenner 10 000 + 500.
    ("ausgabe", 1276.0, 1776.0, 10500.0, 16.9),
    # Förderung 500 € (Ertrag): Bilanz 1 776 + 500 = 2 276; Zähler 2 276 − 500 = 1 776; Nenner 10 000 − 500.
    ("ertrag", 2276.0, 1776.0, 9500.0, 18.7),
])
async def test_zaehler_und_nenner_der_quote_stehen_in_der_antwort(db, typ, bilanz, zaehler, nenner, prozent):
    from backend.api.routes.aussichten.finanzen import get_finanz_prognose

    aid = await _seed(db, monate=_m((2024, 2025)), pv_bk=120.0,
                      sonstige=[{"bezeichnung": "Posten", "betrag": 500.0, "typ": typ}])
    p = await get_finanz_prognose(aid, monate=12, db=db)

    assert p.bisherige_ertraege_euro == pytest.approx(bilanz), "die Zeitraum-Bilanz bleibt"
    assert p.kapitaleinsatz_euro == pytest.approx(nenner)
    assert p.amortisation_ertraege_euro == pytest.approx(zaehler)
    assert p.amortisations_fortschritt_prozent == pytest.approx(prozent)
    assert round(p.amortisation_ertraege_euro / p.kapitaleinsatz_euro * 100, 1) == p.amortisations_fortschritt_prozent
