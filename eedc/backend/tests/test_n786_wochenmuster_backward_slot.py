"""N-786 (Päckchen DD, 10.11.2026): das Wochenmuster legt jede Zeile auf ihren Backward-Slot.

``GET /energie-profil/{id}/wochenmuster`` mittelte je (Wochentag, ``zeile.stunde``). An einem Kanal-Tag ist die Zeile
eine Mischzeile im Beginn-Raster (Zeile ``h`` = ``[h, h+1)``), an einem Bestandstag die Stundenzeile im Backward-Raster
(Slot ``h`` = ``[h-1, h)``): trug das Fenster beide Tagesarten, mischte eine Zelle zwei verschiedene Wanduhr-Stunden.
Jetzt legt ``slot_konvention.backward_slot_der_zeile`` (die eine Paarungsstelle seit N-784) jede Zeile ab; Stunde 23
eines Kanal-Tags ist Slot 0 des Folgetags.

Harness: ``test_s5_e2_sichten_kanal_tage._wochenmuster`` (``stunden_der_tage`` als Fake, die Route echt).
"""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace

from backend.tests.test_s5_e2_sichten_kanal_tage import _wochenmuster


def _zeile(d: date, stunde: int, pv: float, raster=None):
    z = SimpleNamespace(datum=d, stunde=stunde, pv_kw=pv, verbrauch_kw=None, netzbezug_kw=None,
                        einspeisung_kw=None, batterie_kw=None, spannen=None)
    if raster is not None:
        z.raster = raster
    return z


MO_KANAL = date(2026, 6, 1)       # Montag
MO_BESTAND = date(2026, 6, 8)     # Montag


async def test_kanal_tag_und_bestandstag_mit_gleichem_peak_in_derselben_zelle(db, monkeypatch):
    """Peak beider Montage in der Wanduhr-Stunde [12, 13): Kanal-Zeile 12 (Beginn), Bestandszeile 13 (Backward)."""
    zeilen = [_zeile(MO_KANAL, 12, 5.0, raster="beginn"), _zeile(MO_BESTAND, 13, 3.0)]
    punkte = await _wochenmuster(db, monkeypatch, zeilen)
    assert [(p.wochentag, p.stunde, p.pv_kw, p.anzahl_tage) for p in punkte] == [(0, 13, 4.0, 2)]


async def test_stunde_23_eines_kanal_tags_ist_slot_0_des_folgetags(db, monkeypatch):
    """Sonntag 7.6. 23:00–24:00 ⇒ Montag 8.6. Slot 0 — der Wochentag wechselt."""
    punkte = await _wochenmuster(db, monkeypatch, [_zeile(date(2026, 6, 7), 23, 0.5, raster="beginn")])
    assert [(p.wochentag, p.stunde, p.pv_kw, p.anzahl_tage) for p in punkte] == [(0, 0, 0.5, 1)]


async def test_stunde_23_des_letzten_kanal_tags_faellt_aus_dem_fenster(db, monkeypatch):
    """Fenster bis 30.6.: die Stunde 30.6. 23:00 gehört zu Slot 0 des 1.7. — außerhalb, wie die Bestandszeile dort."""
    zeilen = [_zeile(date(2026, 6, 30), 23, 0.2, raster="beginn"), _zeile(date(2026, 6, 30), 10, 2.0, raster="beginn")]
    punkte = await _wochenmuster(db, monkeypatch, zeilen)
    assert [(p.wochentag, p.stunde, p.pv_kw) for p in punkte] == [(1, 11, 2.0)]


async def test_bestandstage_unveraendert(db, monkeypatch):
    zeilen = [_zeile(MO_BESTAND, 13, 3.0), _zeile(date(2026, 6, 15), 13, 1.0), _zeile(date(2026, 6, 15), 0, 0.0)]
    punkte = await _wochenmuster(db, monkeypatch, zeilen)
    assert [(p.wochentag, p.stunde, p.pv_kw, p.anzahl_tage) for p in punkte] == [(0, 0, 0.0, 1), (0, 13, 2.0, 2)]
