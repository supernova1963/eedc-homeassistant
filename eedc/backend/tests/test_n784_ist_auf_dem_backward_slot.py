"""N-784 (Päckchen CC Nachlauf, 9.11.2026): IST und Verbrauch eines Kanal-Tags liegen auf dem **Backward-Slot**.

**Defekt bis hierher.** ``stunden_der_tage`` liefert an einem Kanal-Tag Mischzeilen im Beginn-Raster (Zeile ``h`` =
``[h, h+1)``, ``raster == "beginn"``). ``prognose_adapter.ist_profil`` (Kanon und *Prognosen → Vergleich*) und die zwei
Verbrauchsprofil-Bauer (``verbrauch_prognose_service.get_verbrauch_prognose``, ``live_verbrauchsprofil_service.
_profil_from_db``) legten sie index-gleich ab und paarten sie mit Backward-Reihen (Slot ``h`` = ``[h-1, h)``): das IST
stand eine Stunde vor seiner Prognose (Produktiv gemessen 5./6.11.2026: Peak IST Index 12 gegen Prognose-Slot 13), die
N-544-Grenze ``ist_bisher_bis_slot`` endete eine Stunde zu früh (5.11. 12:30: SOLL bisher 11,04 statt 18,57 kWh,
Abweichungs-Ampel +95 % statt +16 %).

**Regel.** Eine Stelle — ``slot_konvention.backward_slot_der_zeile``: Mischzeile ⇒ ``bestandszeile_fuer_stundenbeginn``
(Slot ``h + 1``, Stunde 23 ⇒ Slot 0 des Folgetags), Bestandszeile unverändert. Dieselbe Paarung wie
``korrekturprofil_aggregator.lade_ist_wetter_stunden`` (die Referenz, jetzt über denselben Helfer).

Die Slot-Zuordnung ist hier ausgeschrieben (``h + 1``) statt aus dem Helfer geholt — ein Pinning-Test, der die Konvention
aus derselben Funktion bezieht wie der Produktcode, prüft nur sich selbst.

Schwestern: ``test_s5_stunden_der_tage.py`` (Mischzeilen am Kanal-Tag), ``test_verbrauchsprofil_slot_konvention.py``
(Backward-Profil der drei Quellen), ``test_prognose_nachfuehrung.py`` (die Grenze als Nenner der Nachführung).
"""

from __future__ import annotations

from datetime import date, timedelta
from types import SimpleNamespace

import pytest

from backend.core.berechnungen.slot_konvention import backward_slot_der_zeile
from backend.services.prognose_adapter import ist_profil

TAG = date(2026, 11, 5)
#: Produktiv-Box 5.11.2026, ``/energie-profil/1/stunden`` (Kanal-Tag, Beginn-Raster), Stunden 7…18.
IST_5_11 = {7: 0.03, 8: 1.72, 9: 4.66, 10: 6.89, 11: 8.24, 12: 8.87, 13: 8.54, 14: 7.39, 15: 5.23, 16: 1.61}
#: Sensor-Attribut ``stundenprofil_kwh`` desselben Tags (Kanon, Backward), Slots 8…17.
PROGNOSE_5_11 = [0.0] * 8 + [0.15, 1.29, 3.87, 5.73, 7.53, 8.0, 6.82, 6.33, 3.69, 1.04] + [0.0] * 6


def _misch(tag: date, stunde: int, pv: float | None = 0.0, **kw) -> SimpleNamespace:
    return SimpleNamespace(datum=tag, stunde=stunde, pv_kw=pv, raster="beginn", spannen=None, **kw)


# ── der Helfer ──────────────────────────────────────────────────────────────


def test_helfer_mischzeile_auf_den_folgeslot_bestand_unveraendert():
    assert backward_slot_der_zeile(_misch(TAG, 11)) == (TAG, 12)
    assert backward_slot_der_zeile(_misch(TAG, 0)) == (TAG, 1)
    assert backward_slot_der_zeile(_misch(TAG, 23)) == (TAG + timedelta(days=1), 0)
    bestand = SimpleNamespace(datum=TAG, stunde=11, pv_kw=1.0)
    assert backward_slot_der_zeile(bestand) == (TAG, 11)


# ── ist_profil (Kanon und Prognosen → Vergleich) ────────────────────────────


def test_ist_profil_kanal_tag_peak_auf_dem_peak_der_prognose():
    """5.11.2026: der Peak des IST liegt nach N-784 auf dem Peak-Slot der Prognose (13), nicht eine Stunde davor."""
    zeilen = [_misch(TAG, h, IST_5_11.get(h, 0.0)) for h in range(24)]
    p = ist_profil(zeilen, datum=TAG)
    slots = [v or 0.0 for v in p.slots_kw]
    assert max(range(24), key=lambda h: slots[h]) == 13 == max(range(24), key=lambda h: PROGNOSE_5_11[h])
    assert slots[8] == 0.03 and slots[17] == 1.61, "erstes/letztes Licht: Stunde h ⇒ Slot h + 1"
    assert p.slots_kw[0] is None and 0 not in p.present_stunden, "Slot 0 (gestern 23 Uhr) gehört nicht zu diesem Tag"
    assert p.tageswert_kwh == pytest.approx(sum(IST_5_11.values()))


def test_ist_profil_grenze_ist_ein_backward_index():
    """12:30 am 5.11.: geschrieben sind die Kanal-Stunden bis 11 ([11, 12)) ⇒ Grenze Slot 12; SOLL bis dorthin 18,57."""
    from backend.core.berechnungen.prognose_nachfuehrung import soll_bisher_kwh

    zeilen = [_misch(TAG, h, IST_5_11.get(h, 0.0)) for h in range(12)]
    p = ist_profil(zeilen, datum=TAG)
    bis = max(h for h, v in enumerate(p.slots_kw) if v is not None)
    assert bis == 12
    assert soll_bisher_kwh(PROGNOSE_5_11, bis) == pytest.approx(18.57)
    ist = p.tageswert_kwh
    assert ist == pytest.approx(21.54)
    # Ampel-Größe (IST gegen SOLL bis zur Grenze): +16 % statt +95 % vor N-784.
    assert round((ist / soll_bisher_kwh(PROGNOSE_5_11, bis) - 1) * 100) == 16
    assert round((ist / soll_bisher_kwh(PROGNOSE_5_11, bis - 1) - 1) * 100) == 95


def test_ist_profil_stunde_23_faellt_aus_dem_profil_zaehlt_im_tag():
    zeilen = [_misch(TAG, h, 0.5 if h in (10, 23) else 0.0) for h in range(24)]
    p = ist_profil(zeilen, datum=TAG)
    assert p.slots_kw[11] == 0.5 and 0 not in p.present_stunden
    assert p.tageswert_kwh == pytest.approx(1.0), "die Energie der Stunde 23 bleibt im Kalendertag des Kanal-Tags"


def test_ist_profil_buendel_auf_dem_backward_slot():
    zeilen = [_misch(TAG, h, 0.0) for h in range(10)] + [
        SimpleNamespace(datum=TAG, stunde=10, pv_kw=3.0, raster="beginn", spannen={"pv": 3})]
    p = ist_profil(zeilen, datum=TAG)
    assert p.buendel_stunden == (11,) and p.slots_kw[11] is None


def test_ist_profil_bestandstag_bitgleich():
    """Regression: ohne Kanal-Tag (keine Mischzeile) dieselben Slots wie bis N-784 — index-gleich."""
    zeilen = [SimpleNamespace(datum=TAG, stunde=h, pv_kw=round(0.1 * h, 2), spannen=None) for h in range(24)]
    p = ist_profil(zeilen, datum=TAG)
    assert list(p.slots_kw) == [round(0.1 * h, 2) for h in range(24)]
    assert list(p.present_stunden) == list(range(24))


# ── die zwei Verbrauchsprofil-Bauer (N1b) ───────────────────────────────────


def _verbrauchszeilen(von: date, tage: int, *, misch: bool) -> list:
    """Je Tag 24 Zeilen: 3,0 kW in der Stunde, die um 18:00 BEGINNT, sonst 0,5 kW."""
    out = []
    for i in range(tage):
        d = von + timedelta(days=i)
        for h in range(24):
            stunde = h if misch else (h + 1) % 24  # Bestand: dieselbe Wanduhr-Stunde auf ihrem Backward-Slot
            tag = d if (misch or h < 23) else d + timedelta(days=1)
            werte = dict(verbrauch_kw=3.0 if h == 18 else 0.5, waermepumpe_kw=None, temperatur_c=None,
                         betriebsmodus_je_wp=None, komponenten=None, spannen=None)
            out.append(SimpleNamespace(datum=d, stunde=h, raster="beginn", **werte) if misch
                       else SimpleNamespace(datum=tag, stunde=stunde, **werte))
    return sorted(out, key=lambda z: (z.datum, z.stunde))


@pytest.fixture
def _zeilen(monkeypatch):
    from backend.services.energie_profil import kanal_stunden as ks

    stand: dict = {}

    async def fake(db, anlage_id, von, bis, *, felder=None):
        return [z for z in stand["zeilen"] if von <= z.datum <= bis]

    monkeypatch.setattr(ks, "stunden_der_tage", fake)
    return stand


@pytest.mark.parametrize("misch", [True, False], ids=["kanal", "bestand"])
async def test_verbrauch_prognose_kanal_tag_auf_dem_backward_slot(db, _zeilen, misch):
    """Tagesprognose/«Speicher voll um»: der Verbrauch der Stunde [18, 19) liegt auf Slot 19 — an Kanal- und
    Bestandstagen gleich (bis N-784 am Kanal-Tag auf Slot 18)."""
    from backend.services.verbrauch_prognose_service import get_verbrauch_prognose

    ziel = date(2026, 11, 9)
    _zeilen["zeilen"] = _verbrauchszeilen(ziel - timedelta(weeks=8), 8 * 7, misch=misch)
    vp = await get_verbrauch_prognose(1, ziel, db)
    assert vp is not None
    assert vp["stunden_kw"][19] == 3.0 and vp["stunden_kw"][18] == 0.5


@pytest.mark.parametrize("misch", [True, False], ids=["kanal", "bestand"])
async def test_live_verbrauchsprofil_kanal_tag_auf_dem_backward_slot(db, _zeilen, monkeypatch, misch):
    """Live-Verbrauchsprofil (Live-Chart, Überschuss-Sensor, HA-Fenster): dieselbe Regel; die Stunde 23 von gestern
    (Slot 0 von heute) macht heute nicht zu einem Lerntag."""
    from backend.services import live_verbrauchsprofil_service as lvps

    class _Heute(date):
        @classmethod
        def today(cls):  # noqa: D401
            return cls(2026, 11, 9)

    monkeypatch.setattr(lvps, "date", _Heute)
    heute = date(2026, 11, 9)
    _zeilen["zeilen"] = _verbrauchszeilen(heute - timedelta(days=7), 7, misch=misch)
    profil = await lvps._profil_from_db(1, db)
    assert profil is not None
    assert profil["werktag"][19] == 3.0 and profil["werktag"][18] == 0.5
    assert profil["tage_werktag"] + profil["tage_wochenende"] == 7
