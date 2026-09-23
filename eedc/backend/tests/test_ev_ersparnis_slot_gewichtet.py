"""Die Eigenverbrauchs-Ersparnis wird mit der vermiedenen Menge gewichtet (F4).

Schwesterdateien: ``test_slot_kosten_tagesebene.py`` (der Slot-SoT),
``test_tage_werte_symmetrie.py`` (die Tageszeile als Ganzes),
``test_speicher_arbitrage_ladepreis.py`` (dieselbe Regel am Speicher).

**Der Befund** (SOLL Flex-Tarife **A-2**, 17.09.2026): Die EV-Ersparnis bewertet
**vermiedenen** Bezug. Bewertet wurde sie bis hierher mit dem Ø des
**tatsächlichen** Bezugs — und der fällt bei einem dynamischen Tarif zu ganz
anderen Zeiten an: Eigenverbrauch entsteht mittags (PV), Netzbezug abends und
nachts. In den Slots, in denen der Bezug vermieden wurde, gibt es gar keine
gemessene Bezugsmenge, die einen Ø gewichten könnte.

Die Richtung des Fehlers ist eindeutig: Der bezugsgewichtete Ø ist bei
Flex-Tarifen **höher** als der EV-gewichtete, weil abends teurer Strom bezogen
wird. Die Ersparnis stand damit systematisch **zu hoch**.

⚠ Dazu **P-1**: Eine Bezugs*abrechnung* sagt nichts über den Eigenverbrauch.
Für diese Größe gibt es auch auf Monatsebene keine externe Wahrheit — der
abgerechnete Ø ist hier Rückfall, nicht Vorrang.
"""

from __future__ import annotations

from datetime import date

import pytest

from backend.models import Anlage, Strompreis
from backend.tests.slot_saat import tep_zeilen
from backend.services.energie_profil.tage_werte import baue_tage_werte

TAG = date(2026, 5, 10)
STAMM_CENT = 30.0


async def _anlage_mit_tagesprofil(db) -> int:
    """Ein Tag mit billigem PV-Mittag und teurem Bezugs-Abend.

    * 12 Uhr — PV 4 kWh, davon 1 eingespeist ⇒ **3 kWh vermiedener Bezug**,
      Slot-Preis **10 ct**
    * 19 Uhr — keine PV, **2 kWh Netzbezug**, Slot-Preis **50 ct**

    Der bezugsgewichtete Ø ist damit 50 ct, der EV-gewichtete 10 ct. Die
    Ersparnis gehört zu 10 ct bewertet: Das ist der Preis, den der Anwender
    mittags **nicht** gezahlt hat.
    """
    anlage = Anlage(anlagenname="EvSlot", leistung_kwp=10.0)
    db.add(anlage)
    await db.flush()
    db.add(Strompreis(
        anlage_id=anlage.id, gueltig_ab=date(2024, 1, 1),
        netzbezug_arbeitspreis_cent_kwh=STAMM_CENT,
        einspeiseverguetung_cent_kwh=8.0,
    ))
    # ⭐ **N-387: der Stundenpreis steht in der Zeile davor** (Menge backward,
    # Preis forward) — `tep_zeilen` verteilt beides so, wie die Produktion es
    # ablegt. Die Aussage bleibt: mittags 10 ct, abends 50 ct.
    db.add_all(tep_zeilen(anlage.id, [
        {"datum": TAG, "stunde": 12,
         "pv_kw": 4.0, "verbrauch_kw": 3.0, "einspeisung_kw": 1.0, "netzbezug_kw": 0.0,
         "strompreis_cent": 10.0},
        {"datum": TAG, "stunde": 19,
         "pv_kw": 0.0, "verbrauch_kw": 2.0, "einspeisung_kw": 0.0, "netzbezug_kw": 2.0,
         "strompreis_cent": 50.0},
    ]))
    await db.commit()
    return anlage.id


async def _zeile(db, anlage_id: int):
    anlage = await db.get(Anlage, anlage_id)
    zeilen = await baue_tage_werte(db, anlage, TAG, TAG)
    return zeilen[0]


@pytest.mark.asyncio
async def test_ev_ersparnis_nimmt_den_preis_der_vermiedenen_stunden(db):
    """⭐ Der Kern: 3 kWh Eigenverbrauch zu 10 ct, nicht zu 50 ct.

    Die alte Rechnung (Eigenverbrauch × bezugsgewichteter Ø) ergäbe 1,50 € —
    das Fünffache. Sie hätte der Mittags-PV den Abendpreis gutgeschrieben.
    """
    aid = await _anlage_mit_tagesprofil(db)

    z = await _zeile(db, aid)

    assert z.eigenverbrauch == pytest.approx(3.0)
    assert z.ev_ersparnis == pytest.approx(3.0 * 10.0 / 100)
    # Die Gegenprobe im selben Test: der bezugsgewichtete Wert wäre 1,50 €.
    assert z.ev_ersparnis != pytest.approx(3.0 * 50.0 / 100)


@pytest.mark.asyncio
async def test_netzbezugskosten_bleiben_bezugsgewichtet(db):
    """Die andere Seite derselben Zeile behält ihre eigene Gewichtung.

    Beide Größen teilen sich die Slot-Preise, aber **nicht** die
    Gewichtungsmenge — genau das ist A-2. Ohne diese Probe könnte der Bau die
    EV-Gewichtung versehentlich auch auf die Kosten legen.
    """
    aid = await _anlage_mit_tagesprofil(db)

    z = await _zeile(db, aid)

    assert z.netzbezug == pytest.approx(2.0)
    assert z.netzbezug_kosten == pytest.approx(2.0 * 50.0 / 100)


@pytest.mark.asyncio
async def test_ohne_slotpreise_bleibt_es_beim_bezugspreis(db):
    """Kein Bruch für Festpreis-Anlagen (SOLL §10, Prüfstein 2).

    Ohne Mitschrift liefert der Slot-Helper keinen EV-Ø; dann gilt unverändert
    der Preis aus dem Vertrag — dieselbe Zahl wie vor diesem Bau.
    """
    anlage = Anlage(anlagenname="EvSlotFest", leistung_kwp=10.0)
    db.add(anlage)
    await db.flush()
    db.add(Strompreis(
        anlage_id=anlage.id, gueltig_ab=date(2024, 1, 1),
        netzbezug_arbeitspreis_cent_kwh=STAMM_CENT,
        einspeiseverguetung_cent_kwh=8.0,
    ))
    db.add_all(tep_zeilen(anlage.id, [
        {"datum": TAG, "stunde": 12,
         "pv_kw": 4.0, "verbrauch_kw": 3.0, "einspeisung_kw": 1.0, "netzbezug_kw": 0.0},
        {"datum": TAG, "stunde": 19,
         "pv_kw": 0.0, "verbrauch_kw": 2.0, "einspeisung_kw": 0.0, "netzbezug_kw": 2.0},
    ]))
    await db.commit()

    z = await _zeile(db, anlage.id)

    assert z.ev_ersparnis == pytest.approx(3.0 * STAMM_CENT / 100)
