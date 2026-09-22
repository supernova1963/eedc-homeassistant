"""Der Wirkungsgrad-Grund trennt „zu wenig Monate" von „keine Entladung erfasst"
(Nachlese 4.0.50, A7).

**Ein Rückgabewert für zwei Lagen — und ein Ratschlag, der für die Hälfte falsch war.**
`aggregiere_speicher_ist` lieferte `None`, wenn weniger als
`SPEICHER_IST_MIN_MONATE` Monate vorlagen **oder** gar keine Entladung erfasst
war. Der HA-Export schrieb daraus pauschal `wirkungsgrad_messung = "zu-wenig-monate"`.

Die beiden Lagen verlangen entgegengesetzte Handgriffe:

* **zu wenig Monate** — die Anlage ist jung. Warten genügt, das wächst von allein.
* **keine Entladung erfasst** — die Monate sind da, `entladung_kwh` ist leer.
  Das geht **nie** von allein weg; der Anwender muss die Entladung erfassen
  (Quelle zuordnen oder Wert pflegen). Ihm „warte noch ein paar Monate" zu
  sagen, kostet ihn genau diese Monate.

**Kein Signaturbruch:** `aggregiere_speicher_ist` bleibt für die drei
Bestandsaufrufer (`services/speicher_wirtschaftlichkeit.py`,
`investitionen/roi_pv.py`, `investitionen/dashboard_speicher.py`); daneben steht
`speicher_ist_mit_grund` (Layer) bzw. `wirkungsgrad_ist_fuer_speicher_mit_grund`
(Service). Der vierte Aufrufer — der HA-Export — nimmt die neue Form.

⛔ **Kein Netz, kein Broker, keine echte Uhr** — dieselbe Bauform wie
`test_s3b_preise_speicher_sensoren.py`, dessen Fixtures diese Probe nachnutzt.
"""

from __future__ import annotations

from datetime import date

import pytest

from backend.core.berechnungen.speicher_wirtschaftlichkeit import (
    GRUND_KEINE_ENTLADUNG,
    GRUND_ZU_WENIG_MONATE,
    SPEICHER_IST_MIN_MONATE,
    aggregiere_speicher_ist,
    speicher_ist_mit_grund,
)
from backend.tests.test_s3b_preise_speicher_sensoren import (
    _anlage,
    _preis,
    _prognose,
    _rechne,
    _speicher,
    _stelle,
    _tarif,
)


# ── Layer: die beiden Gründe ────────────────────────────────────────────────


def test_zu_wenige_monate_heisst_zu_wenige_monate():
    zeilen = [{"ladung_kwh": 100.0, "entladung_kwh": 85.0}
              for _ in range(SPEICHER_IST_MIN_MONATE - 1)]

    aggregat, grund = speicher_ist_mit_grund(zeilen)

    assert aggregat is None
    assert grund == GRUND_ZU_WENIG_MONATE


def test_monate_genug_aber_keine_entladung_heisst_keine_entladung():
    """Der Fall, der bis zur Nachlese 4.0.50 falsch beschriftet war."""
    zeilen = [{"ladung_kwh": 100.0, "entladung_kwh": 0.0}
              for _ in range(SPEICHER_IST_MIN_MONATE + 10)]

    aggregat, grund = speicher_ist_mit_grund(zeilen)

    assert aggregat is None
    assert grund == GRUND_KEINE_ENTLADUNG


def test_entladung_fehlt_ganz_zaehlt_genauso():
    """Ein fehlender Schlüssel ist dasselbe wie eine 0 — beides „nicht erfasst"."""
    zeilen = [{"ladung_kwh": 100.0} for _ in range(SPEICHER_IST_MIN_MONATE + 10)]

    assert speicher_ist_mit_grund(zeilen)[1] == GRUND_KEINE_ENTLADUNG


def test_zu_wenige_monate_gewinnt_gegen_keine_entladung():
    """Die Reihenfolge ist festgelegt: ohne genug Monate ist über die Entladung
    noch gar nichts zu sagen."""
    zeilen = [{"ladung_kwh": 100.0, "entladung_kwh": 0.0}
              for _ in range(SPEICHER_IST_MIN_MONATE - 1)]

    assert speicher_ist_mit_grund(zeilen)[1] == GRUND_ZU_WENIG_MONATE


def test_bei_erfolg_gibt_es_keinen_grund():
    zeilen = [{"ladung_kwh": 100.0, "entladung_kwh": 85.0}
              for _ in range(SPEICHER_IST_MIN_MONATE)]

    aggregat, grund = speicher_ist_mit_grund(zeilen)

    assert grund is None
    assert aggregat is not None
    assert aggregat.anzahl_monate == SPEICHER_IST_MIN_MONATE


@pytest.mark.parametrize("zeilen", [
    [],
    [{"ladung_kwh": 100.0, "entladung_kwh": 0.0} for _ in range(40)],
    [{"ladung_kwh": 100.0, "entladung_kwh": 85.0} for _ in range(40)],
])
def test_die_bestandsfunktion_antwortet_unveraendert(zeilen):
    """⛔ Kein Signaturbruch: `aggregiere_speicher_ist` ist der erste Wert des Tupels.

    Drei Aufrufer hängen daran; die Probe hält die Gleichheit fest, statt sie
    zu behaupten.
    """
    assert aggregiere_speicher_ist(zeilen) == speicher_ist_mit_grund(zeilen)[0]


# ── HA-Export: das Attribut, das der Anwender liest ─────────────────────────


async def test_sensor_sagt_keine_entladung_statt_zu_wenig_monate(db, monkeypatch):
    """34 Monate erfasst, `entladung_kwh` überall 0 ⇒ `keine-entladung`.

    Vorher stand hier `zu-wenig-monate` — bei 34 erfassten Monaten. Der
    Rückfall auf den gepflegten Parameter ist in beiden Fällen derselbe; nur
    der Satz daneben unterscheidet sich, und genau den verlangt
    KONZEPT-FLEX-TARIFE §8.
    """
    anlage = await _anlage(db)
    await _tarif(db, anlage.id, verguetung=9.0)
    await _speicher(db, anlage.id, eta=90.0, imd_monate=34,
                    ladung=100.0, entladung=0.0)
    _stelle(monkeypatch, _prognose(), _preis())

    sv = await _rechne(db, anlage)

    kosten = sv["eedc_speicher_strom_kosten_cent"]
    assert kosten.zusatz_attribute["wirkungsgrad_messung"] == "keine-entladung"
    assert kosten.zusatz_attribute["wirkungsgrad_quelle"] == "parameter"
    assert kosten.value == 10.0, "9,0 ÷ 0,90 — der Rückfall selbst bleibt gleich"


async def test_zu_wenig_monate_bleibt_zu_wenig_monate(db, monkeypatch):
    """Die Gegenrichtung — sonst wäre unbelegt, dass das alte Wort noch vorkommt."""
    anlage = await _anlage(db)
    await _tarif(db, anlage.id, verguetung=9.0)
    await _speicher(db, anlage.id, eta=90.0, imd_monate=0)
    _stelle(monkeypatch, _prognose(), _preis())

    sv = await _rechne(db, anlage)

    kosten = sv["eedc_speicher_strom_kosten_cent"]
    assert kosten.zusatz_attribute["wirkungsgrad_messung"] == "zu-wenig-monate"


async def test_gemessener_wirkungsgrad_traegt_weiter_seine_eigene_quelle(db, monkeypatch):
    """Kommt ein Wert heraus, gewinnt die Quelle der Rechnung — nicht der Grund.

    Ohne diesen Fall bliebe offen, ob der neue Grund den bestehenden Pfad
    überschreibt.
    """
    anlage = await _anlage(db)
    await _tarif(db, anlage.id, bezug=30.0, verguetung=8.5)
    await _speicher(db, anlage.id, eta=95.0, imd_monate=34,
                    ladung=100.0, entladung=85.0)
    _stelle(monkeypatch, _prognose(), _preis())

    sv = await _rechne(db, anlage)

    kosten = sv["eedc_speicher_strom_kosten_cent"]
    assert kosten.zusatz_attribute["wirkungsgrad_messung"] == "fenster_lang"
    assert kosten.zusatz_attribute["wirkungsgrad_quelle"] == "gemessen"
    assert kosten.zusatz_attribute["wirkungsgrad_prozent"] == 85.0


async def test_ohne_anschaffungsdatum_bleibt_es_zu_wenig_monate(db, monkeypatch):
    """`periode_von is None` ⇒ es gibt noch keinen Zeitraum, aus dem zu messen wäre.

    Der Anfangswert des Grundes ist deshalb `zu-wenig-monate` und nicht
    `keine-entladung`: die Entladung ist hier nicht das Problem.
    """
    anlage = await _anlage(db)
    await _tarif(db, anlage.id, verguetung=9.0)
    speicher = await _speicher(db, anlage.id, eta=90.0, imd_monate=34,
                               ladung=100.0, entladung=0.0)
    speicher.anschaffungsdatum = None
    await db.commit()
    _stelle(monkeypatch, _prognose(), _preis())

    sv = await _rechne(db, anlage)

    kosten = sv["eedc_speicher_strom_kosten_cent"]
    assert kosten.zusatz_attribute["wirkungsgrad_messung"] == "zu-wenig-monate"
