"""Wächter „Σ Stunden ≡ Tag" des Kanal-Stundentags (HA-Bauform S3, Etappe E-S3-1, Auftrag Punkt 5; Bauplan §4
S3-R4). Baustein: ``kanal_stunden_gleichheit.pruefe_summen``.

**Baumweit über die Datenstände** beider Abnahme-Matrizen (``MATRIX_FORMEN``, ``HA`` und ``MQTT``, jeder Kanal-Tag
01.06.–03.07.):

* die Kategorien der Komposition je Stunde (Einspeisung, Netzbezug, Ladung, Entladung, Erzeuger hinter dem Zähler)
  gegen die Komposition des Tages — **streng** (1e-6, ungerundet; Kanal-Δ ist Σ ``change`` per Konstruktion);
* die PV-Summe (W2-R3: Σ Geräte) und die Geräte-Schlüssel der Komposition — **streng**, auch an Tagen mit Lücke
  oder Klemmung: S3-R4 (berichtigt 15.10. nach E-S3-1 H-3) skaliert den Rest des Anlagenzählers je Stunde auf den
  Tagesrest (``stunden_leser.rest_faktor``) — es gibt keine Klemm-Ausnahme;
* die Bilanz-Mengen der Adapter-Zeilen (``bilanz_aus_stundenrows``) gegen den Kanal-Tag (``bilanz_leser.als_kanaltag``)
  — streng bis auf ``speicher_netto`` (die Zeilenform verrechnet Ladung und Entladung derselben Stunde, H-2 → A);
* die Kanäle der E-Mob-, Sonstiges- und WP-Gruppe gegen ihr Tages-Δ — streng.

Eine Abweichung ⇒ rot; an den Matrix-Datenständen gibt es keine Ausnahme (``speicher_netto`` tritt nur an der
Kanal-Kopie auf — Herbst-Doppelslot, Bericht E-S3-1).
**Gegenprobe:** ein verschobener Slot (die Zeile auf ihren Beginn statt ihr Ende abgebildet — die Forward-Lesart, die
#144/N-382 abgeschafft haben) ⇒ rot.

Schwesterdateien: test_kanal_stunden_gleichheit.py, test_kanal_symmetrie.py.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from backend.services.kanal import stunden_leser
from backend.services.kanal.stunden_leser import rest_faktor
from backend.tests import achsen_matrix as am
from backend.tests import kanal_bilanz_gleichheit as kg
from backend.tests import kanal_stunden_gleichheit as ks
from backend.tests import pv_achse_matrix as mx

_FORMEN = [("achsen", f) for f in am.MATRIX_FORMEN] + [("pv", f) for f in mx.MATRIX_FORMEN]
_FAELLE = [(m, f, art) for art in ("HA", "MQTT") for m, f in _FORMEN]

#: Ausnahmen je Datenstand — seit der Tagesrest-Skalierung (S3-R4 berichtigt) keine. W2-L (Süd 30 h ohne Zeile) und
#: W2-V (Klemm-Stunden) sind die Gegenprobe: vor der Berichtigung wich W2-L am 11.06. um 10,5 kWh PV ab (40,5 gegen 30,0).
AUSNAHMEN: dict[tuple[str, str, str], dict[str, int]] = {}


@pytest.mark.parametrize("matrix,fid,art", _FAELLE, ids=[f"{a}-{m}-{f}" for m, f, a in _FAELLE])
async def test_summe_der_stunden_gleich_dem_tag(matrix, fid, art):
    async with kg.datenstand(matrix, fid, art) as ds:
        s = await ks.summen_tage(ds.db, ds.aid, kg.TAGE, jetzt=kg.JETZT_TS)
    assert s.verglichen["komposition"] >= 32 * 6, dict(s.verglichen)
    assert s.abweichungen == [], s.abweichungen[:6]
    assert {k: len(v) for k, v in s.ausnahmen.items()} == AUSNAHMEN.get((matrix, fid, art), {}), s.ausnahmen


async def test_gegenprobe_verschobener_slot_wird_rot(monkeypatch):
    """Die Zeile auf das ENDE ihrer Stunde abgebildet (das Backward-Raster vor S4) statt auf ihren Beginn: die letzte
    Zeile des Kalendertags (23:00) fällt aus dem Tag, Stunde 0 bleibt leer ⇒ Σ Stunden ≠ Tag. (Seit HA-Bauform S4
    E-S4-1 ist die Stunde ihr Beginn, ``stunden_leser.stunde_des_beginns``; die Gegenprobe verschiebt die Abbildung
    um dieselbe eine Stunde wie vorher — nur in die andere Richtung.)"""
    def backward(start_ts: int, datum) -> int:
        ende = datetime.fromtimestamp(start_ts) + timedelta(hours=1)
        return (ende.date() - datum).days * 24 + ende.hour

    monkeypatch.setattr(stunden_leser, "stunde_des_beginns", backward)
    async with kg.datenstand("achsen", "M01", "HA") as ds:
        s = await ks.summen_tage(ds.db, ds.aid, kg.TAGE[:3], jetzt=kg.JETZT_TS)
    assert s.abweichungen, "ein verschobener Slot muss den Wächter rot machen"
    assert {e[2] for e in s.abweichungen} >= {"netzbezug"}


def test_rest_faktor_skaliert_nur_nach_unten_und_meldet_den_unskalierbaren_tag():
    """S3-R4: Faktor = Rest_Tag / Σ_h rest_h; ohne Rest 1; ein Tagesrest ohne Stundenrest ist nicht skalierbar
    (``None`` — gemessen an Matrizen und Kanal-Kopie: kein solcher Tag)."""
    assert rest_faktor([2.0, 1.0, 0.0], 1.5) == pytest.approx(0.5)
    assert rest_faktor([2.0, 1.0], 3.0) == pytest.approx(1.0)
    assert rest_faktor([0.0, 0.0], 0.0) == 1.0
    assert rest_faktor([], 0.0) == 1.0
    assert rest_faktor([0.0], 1.0) is None
