"""Filter-Regel für `sonstige_positionen` — rilmor-mhrs auf #286 v3.32.0.

Beim Speichern entscheidet `ist_gueltige_position`, ob ein Eintrag in die DB
geschrieben wird. Vor v3.32.1 verlangten sowohl Frontend (`MonatsabschlussWizard.tsx`)
als auch Backend (`monatsabschluss/wizard.py`) `betrag > 0` — eine 0-€-
Position mit Bezeichnung wurde stillschweigend verworfen. rilmor wollte
eine Position auf 0 € setzen (zum „Löschen") und es passierte nichts;
0,01 € war der einzige Workaround.

Die Regel ist jetzt nur noch: **nicht-leere Bezeichnung**. 0 € als Betrag
ist ein legitimer Datenpunkt.
"""

from __future__ import annotations

from backend.utils.sonstige_positionen import ist_gueltige_position


def test_position_mit_bezeichnung_und_positivem_betrag():
    assert ist_gueltige_position(
        {"bezeichnung": "THG-Quote", "betrag": 200.0, "typ": "ertrag"}
    )


def test_position_mit_bezeichnung_und_null_betrag_ist_gueltig():
    # rilmor-mhrs #286: 0 € + Bezeichnung muss durchgehen.
    assert ist_gueltige_position(
        {"bezeichnung": "Reparatur (Garantie)", "betrag": 0, "typ": "ausgabe"}
    )
    assert ist_gueltige_position(
        {"bezeichnung": "Reparatur (Garantie)", "betrag": 0.0, "typ": "ausgabe"}
    )


def test_position_mit_negativem_betrag_und_bezeichnung_ist_gueltig():
    # Negative Beträge sind selten, aber legitim (Korrektur, Stornierung).
    # Der Filter kümmert sich nicht um Vorzeichen — nur um die Bezeichnung.
    assert ist_gueltige_position(
        {"bezeichnung": "Korrektur Vormonat", "betrag": -50.0, "typ": "ertrag"}
    )


def test_position_ohne_bezeichnung_wird_verworfen():
    # Junk-Filter: leere oder nur-whitespace-Bezeichnung sind Platzhalter,
    # die das + Position-Button anlegt, aber der Anwender nie befüllt.
    assert not ist_gueltige_position({"bezeichnung": "", "betrag": 100.0})
    assert not ist_gueltige_position({"bezeichnung": "   ", "betrag": 100.0})


def test_position_ohne_bezeichnungs_key_wird_verworfen():
    assert not ist_gueltige_position({"betrag": 100.0, "typ": "ertrag"})


def test_nicht_dict_wird_verworfen():
    assert not ist_gueltige_position(None)
    assert not ist_gueltige_position("THG-Quote")
    assert not ist_gueltige_position(42)
    assert not ist_gueltige_position(["bezeichnung", 100])
