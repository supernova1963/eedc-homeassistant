"""Symmetrie: `core/berechnungen/speicher_wirkungsgrad.py` == `lib/speicherWirkungsgrad.ts`.

Zwei Sichten bilden den Speicher-η aus Summen, die erst im Client entstehen —
*Cockpit → Jahr* (`v4/JahrAggregat.tsx`) und *Auswertungen → Tabelle*
(`pages/auswertung/types.ts`). Sie können keine Backend-Zahl lesen, also
braucht die Regel eine zweite **Heimat**. Damit daraus keine zweite
**Definition** wird (genau das war N-252), stehen die Fixtures unten wortgleich
in `frontend/src/lib/speicherWirkungsgrad.test.ts`. Driftet eine Seite, bricht
hier.

Gleiches Muster wie `test_monats_luecken_symmetrie.py` (R20-2).
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from backend.core.berechnungen.speicher_wirkungsgrad import (
    MINDEST_LADUNG_KWH,
    speicher_wirkungsgrad,
)

#: (ladung, entladung, langes_fenster_quelle, erwartet_prozent, erwartete_quelle)
#: — wortgleich in `speicherWirkungsgrad.test.ts::FIXTURES`.
FIXTURES = [
    (100.0, 88.0, None, 88.0, "roh-unkorrigiert"),
    (100.0, 88.0, "fenster_lang", 88.0, "fenster_lang"),
    # Der Kern des Befundes: über 100 % gibt es KEINEN Wert — auch nicht im
    # langen Fenster, und schon gar nicht mit bestätigendem Etikett.
    (100.0, 104.0, None, None, "nicht-ermittelbar"),
    (100.0, 104.0, "fenster_lang", None, "nicht-ermittelbar"),
    # Genau 100 % ist möglich (Grenzfall, kein Ausschluss).
    (100.0, 100.0, None, 100.0, "roh-unkorrigiert"),
    # 0 % ist eine Messung, keine Leerstelle.
    (50.0, 0.0, None, 0.0, "roh-unkorrigiert"),
    # Unterhalb der Mindest-Ladung ist der Quotient Rauschen.
    (0.0, 0.0, None, None, "keine-ladung"),
    (0.05, 4.0, None, None, "keine-ladung"),
    (0.1, 0.09, None, None, "keine-ladung"),
]

#: `parents[2]` ist das `eedc/`-Verzeichnis (tests → backend → eedc).
_FRONTEND = Path(__file__).resolve().parents[2] / "frontend/src/lib"
FRONTEND_SPIEGEL = _FRONTEND / "speicherWirkungsgrad.ts"
FRONTEND_TEST = _FRONTEND / "speicherWirkungsgrad.test.ts"


@pytest.mark.parametrize("ladung,entladung,fenster,prozent,quelle", FIXTURES)
def test_backend_haelt_die_fixtures(ladung, entladung, fenster, prozent, quelle):
    eta = speicher_wirkungsgrad(ladung, entladung, None, langes_fenster_quelle=fenster)
    assert eta.quelle == quelle
    if prozent is None:
        assert eta.prozent is None
    else:
        assert eta.prozent == pytest.approx(prozent)


def test_der_spiegel_existiert_und_traegt_dieselbe_mindestladung():
    """Eine abweichende Schwelle wäre eine stille Zweitdefinition.

    Sie fällt keinem Abwesenheits-Grep auf — die Datei importiert brav den
    Spiegel, nur rechnet er ab einer anderen Grenze. Das ist die
    Drittwert-Klasse aus N-244/S5.
    """
    assert FRONTEND_SPIEGEL.exists(), "Client-Spiegel fehlt"
    quelle = FRONTEND_SPIEGEL.read_text(encoding="utf-8")
    treffer = re.search(r"MINDEST_LADUNG_KWH\s*=\s*([0-9.]+)", quelle)
    assert treffer, "MINDEST_LADUNG_KWH nicht im Spiegel gefunden"
    assert float(treffer.group(1)) == MINDEST_LADUNG_KWH


def test_beide_seiten_kennen_dasselbe_quellen_vokabular():
    """Ein Etikett, das nur eine Seite kennt, erzeugt einen Satz ohne Regel.

    `v4/KomponentenSektionen.tsx::wirkungsgradHinweis` übersetzt die Quelle in
    einen Satz — ein Wert, für den es dort keinen `case` gibt, fällt in den
    `default` und behauptet Bestandsverhalten.
    """
    quelle = FRONTEND_SPIEGEL.read_text(encoding="utf-8")
    block = re.search(r"WirkungsgradQuelle\s*=([^\n]*(?:\n\s*\|[^\n]*)*)", quelle)
    assert block, "Typ `WirkungsgradQuelle` nicht gefunden"
    client_vokabular = set(re.findall(r"'([a-z_-]+)'", block.group(1)))

    py = (
        Path(__file__).resolve().parents[1]
        / "core/berechnungen/speicher_wirkungsgrad.py"
    ).read_text(encoding="utf-8")
    backend_vokabular = set(
        re.findall(r'SpeicherWirkungsgrad\([^,]+,\s*(?:langes_fenster_quelle\s*or\s*)?"([a-z_-]+)"', py)
    )
    # `fenster_lang` kommt im Backend nur als Argument der Aufrufer vor, nicht
    # als Literal in der Rückgabe — es gehört trotzdem zum Vokabular.
    backend_vokabular.add("fenster_lang")

    fehlt_im_client = backend_vokabular - client_vokabular
    assert not fehlt_im_client, (
        f"Der Client-Spiegel kennt diese Quellen nicht: {sorted(fehlt_im_client)}"
    )


def test_die_fixtures_stehen_wortgleich_im_client_test():
    """Der Beleg, dass „gespiegelt" nicht nur behauptet ist.

    Ohne diese Probe könnte die TS-Seite ihre Fixtures still ändern und beide
    Testdateien blieben grün — jede für sich.
    """
    assert FRONTEND_TEST.exists(), "Spiegel-Test fehlt"
    ts = FRONTEND_TEST.read_text(encoding="utf-8")
    block = re.search(r"const FIXTURES[^=]*=\s*(\[[\s\S]*?\n\])", ts)
    assert block, "FIXTURES-Block im Client-Test nicht gefunden"

    roh = block.group(1)
    roh = re.sub(r"//[^\n]*", "", roh)          # Kommentare raus
    roh = roh.replace("undefined", "null").replace("'", '"')
    roh = re.sub(r",(\s*[\]\}])", r"\1", roh)   # trailing commas
    ts_fixtures = [tuple(z) for z in json.loads(roh)]

    py_fixtures = [
        (lad, entl, fenster, prozent, quelle)
        for lad, entl, fenster, prozent, quelle in FIXTURES
    ]
    assert ts_fixtures == py_fixtures, (
        "Die Fixtures beider Seiten sind auseinandergelaufen — genau die Drift, "
        "die dieser Test verhindern soll."
    )
