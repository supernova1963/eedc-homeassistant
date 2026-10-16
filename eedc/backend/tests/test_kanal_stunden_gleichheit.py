"""Gleichheitsprobe Kanal-Stundentag (Adapter) gegen die Stundenzeilen des Bestands (HA-Bauform S3, Etappe E-S3-1,
Auftrag Punkte 1–4; Bauplan §4). Baustein und Klassen: ``kanal_stunden_gleichheit.py``.

**Dauerhaft, an jeder Form beider Abnahme-Matrizen** (``MATRIX_FORMEN``: 31 PV-Formen, 12 Achsen-Formen), je
Datenstand ``HA`` und ``MQTT``, an jedem Tag 01.06.–03.07. (Uhr 04.07. 00:30), je Stunde und Feld: jede Abweichung
gehört zu einer benannten Klasse in der eingefrorenen Zahl (``KLASSEN``, gemessen 15.10.2026); ``unbenannt`` ist 0.
``komponenten`` weicht in JEDER verglichenen Stunde ab: die Spalte ist der Leistungspfad und bleibt nach S3-R6
(erweitert 15.10., E-S3-1 H-1 → A) aus der Stundenzeile; der Adapter führt die Zählerform als eigenes Feld — gezählt
als 24 je Kanal-Tag, nicht verglichen.

Dazu: das Abfrage-Budget (EINE ``stunden_stapel``-Anweisung je Gruppe), der Lade-Kontext (ein Kanal-Stundentag je
Anfrage), die Felder einer Gruppe mit Wahl ``bestand`` (``None`` — der Aufrufer nimmt die Stundenzeile), die
Slot-Abbildung an den Umstellungstagen und eine Gegenprobe des Vergleichs (eine verfälschte Stundenzeile wird
``unbenannt``). Keine Probe liest die Uhr. Schwesterdateien: test_kanal_stunden_summe.py,
test_kanal_bilanz_gleichheit.py.
"""

from __future__ import annotations

from datetime import date, datetime

import pytest
from sqlalchemy import event, update

from backend.models.tages_energie_profil import TagesEnergieProfil
from backend.services.kanal import lesen
from backend.services.kanal.lade_kontext import lese_anfrage
from backend.services.kanal.lesen import Stunden, Stundenwert
from backend.services.kanal.stunden_adapter import FELDER_JE_GRUPPE, stunden_aus_kanaelen
from backend.services.kanal.stunden_leser import GRUPPEN, kanal_stundentag, slots_der_stunden
from backend.tests import achsen_matrix as am
from backend.tests import kanal_bilanz_gleichheit as kg
from backend.tests import kanal_stunden_gleichheit as ks
from backend.tests import pv_achse_matrix as mx

_FORMEN = [("achsen", f) for f in am.MATRIX_FORMEN] + [("pv", f) for f in mx.MATRIX_FORMEN]
_FAELLE = [(m, f, art) for art in ("HA", "MQTT") for m, f in _FORMEN]

#: Die benannten Abweichungen je Datenstand (ohne ``komponenten_leistungspfad`` und die letzte Stunde
#: ``LETZTE_STUNDE_FELDER``), gemessen 15.10.2026, nach S4 E-S4-1 unverändert nachgemessen 16.10.2026 — alle übrigen
#: Datenstände: keine. ``deckel_r3``: M03-Sprungstunden (N-586 — der Kanal trägt HAs ``sum`` wörtlich, der Bestand
#: deckelt). ``luecke_ha``/``spannen_fuellung``: F08a/F08b (BKW-Zähler ohne Nachtzeilen — die Morgenstunde trägt das
#: Bündel auf der PV-Achse, R6 lässt den Stunden-Verbrauch leer; der Bestand nimmt am Aggregat-Tag die PV-Achse nur
#: aus dem Anlagenzähler), W2-L (Süd 30 h ohne Zeile), W2-E (Ersatzgruppe: der Tag wählt den Zähler ohne Zeile, wie
#: die Tageswahl W2-R4; der Bestand nimmt den mit Zeilen). ``klemm``: W2-V (Volleinspeiser, Süd gemessen über dem
#: AC-Anlagenzähler). ``rest_skaliert`` und die übrigen W2-L-Stunden: S3-R4 (berichtigt 15.10.) skaliert am 11.06. den
#: Rest des Anlagenzählers auf den Tagesrest (Faktor < 1), der Bestand verteilt ihn ungekürzt — vorher 5 Lücken-Stunden,
#: seit der Skalierung 13 + 2. Eine neue Klasse oder eine andere Zahl ⇒ rot.
KLASSEN: dict[tuple[str, str, str], dict[str, int]] = {
    ("achsen", "M03", "HA"): {"deckel_r3": 10},
    ("achsen", "W2-E", "HA"): {"luecke_ha": 48},
    ("pv", "F08a", "HA"): {"luecke_ha": 128},
    ("pv", "F08b", "HA"): {"luecke_ha": 128},
    ("pv", "F08a", "MQTT"): {"spannen_fuellung": 128},
    ("pv", "F08b", "MQTT"): {"spannen_fuellung": 128},
    ("pv", "W2-L", "HA"): {"luecke_ha": 13, "rest_skaliert": 2},
    ("pv", "W2-L", "MQTT"): {"spannen_fuellung": 13, "rest_skaliert": 2},
    ("pv", "W2-V", "HA"): {"klemm": 132},
    ("pv", "W2-V", "MQTT"): {"klemm": 132},
}


#: HA-Bauform S4 E-S4-1 (Kanal-Stunde h ≡ Bestands-Slot h+1, Stunde 23 ≡ Slot 0 des Folgetags): die Stunde 03.07. 23:00
#: des letzten Kanal-Tags hat keine Bestandszeile (Slot 0 des 04.07. — die Matrix aggregiert bis 03.07.) ⇒ jedes
#: verglichene Feld mit Kanal-Wert dieser einen Stunde ist ``bestand_ohne_zeile`` (die Bilanz-Felder 7, mit WP-Gruppe 8,
#: mit WP- und E-Mob-Gruppe 9), ``komponenten`` dort nicht verglichen. Gemessen 16.10.2026 auf allen 86 Datenständen
#: (Ablage ``e-s4-1/gleichheit_klassen.jsonl``); F08a/F08b: der 03.07. ist Bestandstag (Zähler ohne Nachtzeilen) — keine.
#: Alle übrigen Klassen (``KLASSEN``) sind dieselben wie vor S4.
LETZTE_STUNDE_FELDER: dict[tuple[str, str], int] = {
    ("achsen", "M02"): 9, **{("achsen", f): 8 for f in ("M04", "M05", "M06", "M07", "M08", "M09", "M10")},
    ("pv", "F08a"): 0, ("pv", "F08b"): 0,
}


@pytest.mark.parametrize("matrix,fid,art", _FAELLE, ids=[f"{a}-{m}-{f}" for m, f, a in _FAELLE])
async def test_kanal_stundentag_gleich_der_stundenzeile_bis_auf_benannte_klassen(matrix, fid, art):
    async with kg.datenstand(matrix, fid, art) as ds:
        b = await ks.probe_tage(ds.db, ds.aid, kg.TAGE, jetzt=kg.JETZT_TS, art=art)
    kanal_tage = b.tage["bilanz:kanal"]
    assert kanal_tage >= 32 and sum(b.verglichen.values()) > 0, dict(b.tage)
    klassen = dict(b.klassen)
    letzte = LETZTE_STUNDE_FELDER.get((matrix, fid), 7)
    assert klassen.pop("komponenten_leistungspfad", 0) == 24 * kanal_tage - (1 if letzte else 0), \
        b.beispiele.get("komponenten_leistungspfad")
    assert klassen.pop("bestand_ohne_zeile", 0) == letzte, b.beispiele.get("bestand_ohne_zeile")
    assert {(t, h) for t, h, *_ in b.beispiele.get("bestand_ohne_zeile", [])} <= {(date(2026, 7, 3), 23)}
    assert "unbenannt" not in klassen, b.beispiele.get("unbenannt")
    assert klassen == KLASSEN.get((matrix, fid, art), {}), {k: b.beispiele.get(k) for k in klassen}


# ── Abfrage-Budget und Lade-Kontext ─────────────────────────────────────────


#: Ein Stück, das nur die Anweisung von ``lesen.stunden_stapel`` trägt (die Platzhalter schreibt der Treiber um).
_STUNDEN_MARKE = "FROM r LEFT JOIN kanal_statistik s ON s.kanal_id = r.kid"
assert _STUNDEN_MARKE in lesen._STUNDEN_SQL


class _Zaehler:
    """Zählt die Anweisungen über die Verbindung der Sitzung; ``stunden`` die von ``lesen.stunden_stapel``."""

    def __init__(self, db):
        self.n = self.stunden = 0
        self._engine = db.bind.sync_engine

    def _hook(self, _conn, _cur, statement, *_a, **_k):
        self.n += 1
        if _STUNDEN_MARKE in statement:
            self.stunden += 1

    def __enter__(self):
        event.listen(self._engine, "before_cursor_execute", self._hook)
        return self

    def __exit__(self, *_a):
        event.remove(self._engine, "before_cursor_execute", self._hook)


@pytest.mark.parametrize("fid,stapel", [("M07", 3), ("M02", 2), ("M01", 1)])
async def test_abfrage_budget_eine_stunden_anweisung_je_gruppe_und_lade_kontext(fid, stapel):
    """M07: Bilanz, Sonstiges, WP aus Kanälen ⇒ drei ``stunden_stapel`` (Bilanz · Geräte · WP); M02: Bilanz und E-Mob ⇒
    zwei; M01: nur Bilanz ⇒ einer. Im Lade-Kontext einer Anfrage liest der zweite Aufruf nichts."""
    tag = date(2026, 6, 15)
    async with kg.datenstand("achsen", fid, "HA") as ds:
        with _Zaehler(ds.db) as z:
            st = await kanal_stundentag(ds.db, ds.aid, tag, jetzt=kg.JETZT_TS)
        assert z.stunden == stapel, (z.stunden, sorted(st.gruppen))
        with lese_anfrage():
            erst = await kanal_stundentag(ds.db, ds.aid, tag, jetzt=kg.JETZT_TS)
            with _Zaehler(ds.db) as z2:
                zweit = await kanal_stundentag(ds.db, ds.aid, tag, jetzt=kg.JETZT_TS)
        assert z2.n == 0 and zweit is erst
        assert stunden_aus_kanaelen(zweit).zeilen == stunden_aus_kanaelen(st).zeilen


async def test_felder_einer_gruppe_mit_wahl_bestand_bleiben_leer():
    """M01: E-Mob, Sonstiges, WP nehmen den Bestand — ihre Felder fehlen in ``felder`` und stehen auf ``None``; die
    Bilanz kommt aus den Kanälen (24 Slots, Abdeckung über das ganze Tagesfenster, lückenlos)."""
    tag = date(2026, 6, 15)
    async with kg.datenstand("achsen", "M01", "HA") as ds:
        st = await kanal_stundentag(ds.db, ds.aid, tag, jetzt=kg.JETZT_TS)
    assert set(st.wahlen) == set(GRUPPEN) and set(st.gruppen) == {"bilanz"}
    ks_ = stunden_aus_kanaelen(st)
    assert {"waermepumpe_kw", "wallbox_kw"}.isdisjoint(ks_.felder)
    assert set(FELDER_JE_GRUPPE["bilanz"]) <= ks_.felder
    assert all(z.waermepumpe_kw is None and z.wallbox_kw is None for z in ks_.zeilen)
    gs = st.gruppen["bilanz"]
    assert (gs.gedeckt_von, gs.gedeckt_bis, gs.groesste_spanne) == (st.von, st.bis, 3600)
    assert all(len(m) == 24 and None not in m for m in gs.mengen.values())


async def test_gegenprobe_eine_verfaelschte_stundenzeile_wird_unbenannt():
    """Der Vergleich ist nicht blind: eine Stundenzeile des Bestands um 1 kWh PV verfälscht ⇒ genau diese Stunde
    (PV und die abhängigen Felder) ist ``unbenannt``."""
    tag = date(2026, 6, 15)
    async with kg.datenstand("achsen", "M01", "HA") as ds:
        await ds.db.execute(update(TagesEnergieProfil).where(
            TagesEnergieProfil.anlage_id == ds.aid, TagesEnergieProfil.datum == tag, TagesEnergieProfil.stunde == 12,
        ).values(pv_kw=TagesEnergieProfil.pv_kw + 1.0))
        await ds.db.commit()
        b = await ks.probe_tage(ds.db, ds.aid, [tag], jetzt=kg.JETZT_TS, art="HA")
    assert b.klassen["unbenannt"] >= 1
    # S4-R-3b: der Bestands-Slot 12 trägt [11, 12) — die Kanal-Stunde 11.
    assert {(t, h, f) for t, h, f, _s, _i in b.beispiele["unbenannt"]} >= {(tag, 11, "pv_kw")}


# ── Stunden-Abbildung (S4-R-3b, vorher S3-R2) ──────────────────────────────────────────────────


def _stunden(werte) -> Stunden:
    return Stunden(key="k", art="sum", einheit="kWh", von=0, bis=0, werte=werte, gedeckt_von=None, gedeckt_bis=None,
                   groesste_spanne=None, voll=True, grund=None, laufend=False)


def test_slots_beginn_luecke_und_herbst_doppelstunde():
    """S4-R-3b: Stunde h = Zeile mit Beginn h:00 (die Zeile des Vortags 23:00 gehört nicht zum Tag); eine fehlende
    Zeile lässt die Stunde leer (keine 0) und die Folgezeile trägt die Spanne; am Herbst-Umstellungstag (Berlin) fallen
    zwei Zeilen (02:00 CEST und 02:00 CET) auf die Stunde 2 und sie trägt beide."""
    tag = date(2026, 6, 15)

    def ts(stunde):
        return int(datetime(2026, 6, 14 if stunde < 0 else 15, stunde % 24).timestamp())

    werte = [Stundenwert(ts(-1), 1.0, 1.0, "spiegel", 3600), Stundenwert(ts(0), 2.0, 3.0, "spiegel", 3600),
             Stundenwert(ts(2), 5.0, 8.0, "spiegel", 7200)]
    menge, spanne = slots_der_stunden(tag, _stunden(werte))
    assert menge[:4] == (2.0, None, 5.0, None) and spanne[:4] == (3600, None, 7200, None)
    herbst = date(2026, 10, 25)
    if datetime(2026, 10, 25, 4).timestamp() - datetime(2026, 10, 25, 0).timestamp() != 5 * 3600:
        pytest.skip("Prozesszone ohne Herbst-Umstellung am 25.10.2026")
    a = int(datetime(2026, 10, 25, 2, fold=0).timestamp())       # 02:00 CEST
    w = [Stundenwert(a - 3600, 1.0, 1.0, "spiegel", 3600), Stundenwert(a, 1.0, 2.0, "spiegel", 3600),
         Stundenwert(a + 3600, 1.0, 3.0, "spiegel", 3600), Stundenwert(a + 7200, 1.0, 4.0, "spiegel", 3600)]
    menge, spanne = slots_der_stunden(herbst, _stunden(w))
    assert menge[1:4] == (1.0, 2.0, 1.0) and spanne[2] == 7200
