"""Die Komposition je Stunde über die Vorlage der Belegung ist dieselbe wie über ``waehle_und_komponiere``
(HA-Bauform S3, Etappe E-S3-6, Gate B; Bauplan §10c Option B).

``stunden_leser._komposition_der_stunde`` ruft seit E-S3-6 die Layer-Funktion ``komponiere_bilanz_zeitraum`` direkt —
mit den Eingängen, die ``_vorlage`` je Belegung (die Kanäle mit Zeile in der Stunde) einmal bestimmt. Bis E-S3-6 baute
sie je Kanal und Stunde einen voll gedeckten ``Zeitraum`` und rief ``bilanz_leser.waehle_und_komponiere``. In einer
Stunde ist jeder belegte Kanal voll gedeckt — die Wahl steht fest; nur deshalb darf die Vorlage sie überspringen.

**Die Probe hält das fest:** jeder Aufruf des Lesers an den Datenständen der Abnahme-Matrizen (alle Formen, HA; die
W2-Formen mit Lücke und Klemmung zusätzlich MQTT) wird mit dem alten Weg nachgerechnet — gleiche Komposition bis aufs
Bit (``repr``: Werte, Schlüssel, Reihenfolge), gleiche Träger. Der Tages-Leser und der Bereichs-Leser laufen beide.
Die Tagesrest-Skalierung (S3-R4, ``az_abzug``) ist gezählt: W2-L muss sie mindestens einmal treffen.

Schwesterdateien: test_kanal_stunden_summe.py, test_kanal_stunden_gleichheit.py, test_kanal_stundentage_bereich.py.
"""

from __future__ import annotations

import pytest

from backend.models.kanal import ART_SUM
from backend.services.kanal import bilanz_leser, stunden_leser
from backend.services.kanal.lesen import Zeitraum
from backend.services.kanal.quellenwahl import QUELLE_KANAL
from backend.tests import achsen_matrix as am
from backend.tests import kanal_bilanz_gleichheit as kg
from backend.tests import pv_achse_matrix as mx

_STUNDE = 3600
_FORMEN = [("achsen", f, "HA") for f in am.MATRIX_FORMEN] + [("pv", f, "HA") for f in mx.MATRIX_FORMEN]
_FAELLE = _FORMEN + [("pv", f, "MQTT") for f in ("W2-L", "W2-V")]


def _alter_weg(gs, h, traeger, dc_grund, az_abzug):
    """Die Komposition der Stunde, wie ``_komposition_der_stunde`` sie bis E-S3-6 baute (``6527b79d``…``e1d4299a``)."""
    belegt = {key for key, m in gs.mengen.items() if m[h] is not None}
    eintraege_h = [e for e in gs.eintraege if e.schluessel in belegt]
    ergebnisse = {}
    for key in belegt:
        change = gs.mengen[key][h] - (az_abzug if key == bilanz_leser._AGGREGAT_KEY else 0.0)
        ergebnisse[key] = Zeitraum(key=key, art=ART_SUM, einheit="kWh", von=h * _STUNDE, bis=(h + 1) * _STUNDE,
                                   delta=change, teil_delta=None, gedeckt_von=h * _STUNDE,
                                   gedeckt_bis=(h + 1) * _STUNDE, rand_spanne=gs.spannen[key][h], voll=True,
                                   grund=None, laufend=False)
    traeger_h = stunden_leser._traeger_der_stunde(traeger, gs.eintraege, belegt)
    kz = bilanz_leser.waehle_und_komponiere(eintraege_h, ergebnisse, traeger_h, lueckentag=False, dc_grund=dc_grund)
    return (kz.komposition if kz.wahl.quelle == QUELLE_KANAL else None), traeger_h


class _Spion:
    """Ersetzt ``_komposition_der_stunde``: ruft den Leser und den alten Weg, zählt Stunden und Abweichungen."""

    def __init__(self, echt):
        self.echt = echt
        self.stunden = 0
        self.skaliert = 0
        self.abweichungen: list = []

    def __call__(self, gs, h, traeger, dc_grund, vorlagen, az_abzug=0.0):
        k, t = self.echt(gs, h, traeger, dc_grund, vorlagen, az_abzug)
        k_alt, t_alt = _alter_weg(gs, h, traeger, dc_grund, az_abzug)
        self.stunden += 1
        self.skaliert += az_abzug != 0.0
        if repr(k) != repr(k_alt) or repr(t) != repr(t_alt):
            self.abweichungen.append((h, az_abzug, k, k_alt))
        return k, t


@pytest.mark.parametrize("matrix,fid,art", _FAELLE, ids=[f"{a}-{m}-{f}" for m, f, a in _FAELLE])
async def test_vorlage_gleich_waehle_und_komponiere(monkeypatch, matrix, fid, art):
    spion = _Spion(stunden_leser._komposition_der_stunde)
    monkeypatch.setattr(stunden_leser, "_komposition_der_stunde", spion)
    async with kg.datenstand(matrix, fid, art) as ds:
        for d in kg.TAGE:
            await stunden_leser.kanal_stundentag(ds.db, ds.aid, d, jetzt=kg.JETZT_TS)
        await stunden_leser.kanal_stundentage(ds.db, ds.aid, kg.TAGE[0], kg.TAGE[-1], jetzt=kg.JETZT_TS)
    assert spion.abweichungen == [], spion.abweichungen[:3]
    if fid == "W2-L":
        assert spion.skaliert >= 1, "W2-L muss die Tagesrest-Skalierung treffen"
    if fid in ("M01", "F01"):
        assert spion.stunden >= 2 * 24 * 30, spion.stunden
