"""Proben Quellenwahl und Monatsraster (HA-Bauform E3, Auftrag Punkte 3 und 5; Bauplan §3b, G7).

* **Quellenwahl** (``services/kanal/quellenwahl.py``): ``kanal`` nur, wenn JEDER benötigte Kanal den Zeitraum voll deckt;
  ein zugeordnetes Feld ohne Kanal zählt als „deckt nicht"; die Wahl nennt je Kanal den Grund. Reine Auskunft.
* **Monatsraster** (``services/kanal/monatsraster.py``): je Monat Δ und Abdeckung über ``reihe`` mit den
  Monatsfenstern des Bestands, je Monat EINE Quellenwahl über alle Kanäle.
* **Fenster == Bestand** auf einem Matrix-Datenstand: Δ über das Monatsfenster aus dem Spiegel ==
  ``lade_monats_summen_aus_tagen`` (die Monatssumme der Tageszeilen von ``aggregate_day``), und die Stunden des
  Tagesfensters == Slot 0…23 der Stundenzeilen.

Keine Probe liest die Uhr (``jetzt`` gesetzt). Schwesterdateien: test_kanal_lesen.py, test_kanal_lesen_fenster.py,
test_kanal_symmetrie.py.
"""

from __future__ import annotations

import shutil
import tempfile
from contextlib import asynccontextmanager

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.models.kanal import ART_MEAN, ART_SUM, Kanal
from backend.services.kanal.fenster import monatsfenster
from backend.services.kanal.lesen import (
    GRUND_BEGINNT_NACH_VON,
    GRUND_KEIN_KANAL,
    GRUND_KEINE_ZEILE,
    kanaele_laden,
    zeitraum,
)
from backend.services.kanal.monatsraster import monatsreihe
from backend.services.kanal.quellenwahl import (
    GRUND_KEINE_EINGAENGE,
    QUELLE_BESTAND,
    QUELLE_KANAL,
    quellenwahl,
    waehle_quelle,
)
from backend.tests.test_kanal_lesen import JETZT, _anlage, _kanal, h

TAG = 24


async def test_zwei_kanaele_mit_verschiedenem_beginn_waehlen_den_bestand_mit_grund(db):
    """PV-Kanal ab Tag 0, Einspeise-Kanal ab Tag 2 (Gegenprüfung W4: EV = PV aus 30 Tagen − Einspeisung aus 11)."""
    aid = await _anlage(db)
    await _kanal(db, aid, "inv:1:pv_erzeugung_kwh", ART_SUM, [(h(i), 2.0 * i) for i in range(-1, 5 * TAG)])
    await _kanal(db, aid, "basis:einspeisung", ART_SUM, [(h(i), 1.0 * i) for i in range(2 * TAG + 5, 5 * TAG)])
    keys = ["inv:1:pv_erzeugung_kwh", "basis:einspeisung"]
    w = await quellenwahl(db, aid, h(TAG), h(4 * TAG), keys, jetzt=JETZT)
    assert (w.quelle, w.gruende) == (QUELLE_BESTAND, {"basis:einspeisung": GRUND_BEGINNT_NACH_VON})
    assert w.ergebnisse["inv:1:pv_erzeugung_kwh"].voll and not w.ergebnisse["basis:einspeisung"].voll
    w0 = await quellenwahl(db, aid, h(0), h(TAG), keys, jetzt=JETZT)
    assert w0.gruende == {"basis:einspeisung": GRUND_KEINE_ZEILE}
    # ab Tag 3 decken beide ⇒ Kanal
    w3 = await quellenwahl(db, aid, h(3 * TAG), h(4 * TAG), keys, jetzt=JETZT)
    assert (w3.quelle, w3.gruende) == (QUELLE_KANAL, {})


async def test_zugeordnetes_feld_ohne_kanal_deckt_nicht(db):
    """Sensor ohne HA-Statistik ⇒ kein Kanal (Entscheid „keine Mittelwert-Mitschrift") ⇒ der Zeitraum gilt für
    diese Größe als nicht gedeckt; auch ein Mittelwert-Kanal geht in dieselbe Wahl ein."""
    aid = await _anlage(db)
    await _kanal(db, aid, "basis:netzbezug", ART_SUM, [(h(i), float(i)) for i in range(-1, TAG)])
    await _kanal(db, aid, "basis:strompreis", ART_MEAN, [(h(i), 30.0, 29.0, 31.0) for i in range(0, TAG)],
                 einheit="ct/kWh")
    w = await quellenwahl(db, aid, h(0), h(TAG), ["basis:netzbezug", "basis:strompreis", "inv:4:soc"], jetzt=JETZT)
    assert (w.quelle, w.gruende) == (QUELLE_BESTAND, {"inv:4:soc": GRUND_KEIN_KANAL})
    voll = await quellenwahl(db, aid, h(0), h(TAG), ["basis:netzbezug", "basis:strompreis"], jetzt=JETZT)
    assert (voll.quelle, voll.ergebnisse["basis:strompreis"].mean) == (QUELLE_KANAL, 30.0)
    leer = await quellenwahl(db, aid, h(0), h(TAG), [], jetzt=JETZT)
    assert (leer.quelle, leer.gruende) == (QUELLE_BESTAND, {"": GRUND_KEINE_EINGAENGE})


def test_waehle_quelle_ist_die_eine_regel():
    class _E:
        def __init__(self, voll, grund=None):
            self.voll, self.grund = voll, grund

    assert waehle_quelle({"a": _E(True), "b": _E(True)}, ["a", "b"]).quelle == QUELLE_KANAL
    assert waehle_quelle({"a": _E(True), "b": _E(False, "endet_vor_bis")}, ["a", "b"]).gruende == {"b": "endet_vor_bis"}
    assert waehle_quelle({"a": _E(True)}, ["a", "b"]).gruende == {"b": GRUND_KEIN_KANAL}


async def test_monatsraster_je_monat_delta_abdeckung_und_eine_quellenwahl(db):
    """Drei Monate; der zweite Kanal beginnt Mitte Februar. Je Monat: Δ = ``zeitraum`` über das Monatsfenster,
    Σ Monate = Δ über alles, und EINE Wahl für beide Kanäle."""
    aid = await _anlage(db)
    anfang, ende = monatsfenster(2026, 1)[0], monatsfenster(2026, 3)[1]
    mitte_feb = monatsfenster(2026, 2)[0] + 14 * 86400
    stunden = range((anfang - 2 * 3600 - h(0)) // 3600, (ende - h(0)) // 3600)
    a = await _kanal(db, aid, "basis:einspeisung", ART_SUM, [(h(i), 0.25 * i) for i in stunden])
    b = await _kanal(db, aid, "basis:netzbezug", ART_SUM, [(h(i), 0.5 * i) for i in stunden if h(i) >= mitte_feb])
    r = await monatsreihe(db, aid, [a.key, b.key], (2026, 1), (2026, 3), jetzt=JETZT)
    assert [(m.jahr, m.monat) for m in r] == [(2026, 1), (2026, 2), (2026, 3)]
    assert [m.wahl.quelle for m in r] == [QUELLE_BESTAND, QUELLE_BESTAND, QUELLE_KANAL]
    assert [m.wahl.gruende for m in r] == [{"basis:netzbezug": GRUND_KEINE_ZEILE},
                                          {"basis:netzbezug": GRUND_BEGINNT_NACH_VON}, {}]
    for m in r:
        assert (m.von, m.bis) == monatsfenster(m.jahr, m.monat)
        einzeln = await zeitraum(db, a, m.von, m.bis, jetzt=JETZT)
        assert m.werte["basis:einspeisung"] == einzeln
        assert m.werte["basis:einspeisung"].delta == pytest.approx(0.25 * (m.bis - m.von) / 3600)
    gesamt = await zeitraum(db, a, anfang, ende, jetzt=JETZT)
    assert sum(m.werte["basis:einspeisung"].delta for m in r) == pytest.approx(gesamt.delta)
    assert await monatsreihe(db, aid, [a.key], (2026, 4), (2026, 3), jetzt=JETZT) == []


async def test_monatsraster_waehlt_wie_der_tag_feld_ohne_kanal_leere_eingabe_mittelwert(db):
    """Dieselbe Regel wie ``quellenwahl()`` (Nachmessung E3, Punkt 3): ein benötigter Schlüssel ohne Kanal ⇒ der Monat
    nimmt den Bestand (``kein_kanal``); keine benötigten Schlüssel ⇒ je Monat ``bestand``; ein Mittelwert-Kanal ⇒
    benannter Grund, kein Fehler."""
    from backend.services.kanal.monatsraster import GRUND_MITTELWERT_KEIN_DELTA

    aid = await _anlage(db)
    anfang, ende = monatsfenster(2026, 1)[0], monatsfenster(2026, 2)[1]
    stunden = range((anfang - 2 * 3600 - h(0)) // 3600, (ende - h(0)) // 3600)
    a = await _kanal(db, aid, "basis:einspeisung", ART_SUM, [(h(i), 0.25 * i) for i in stunden])
    await _kanal(db, aid, "basis:strompreis", ART_MEAN, [(h(i), 30.0, 30.0, 30.0) for i in stunden], einheit="ct/kWh")
    mit_luecke = await monatsreihe(db, aid, [a.key, "inv:4:soc"], (2026, 1), (2026, 2), jetzt=JETZT)
    assert [(m.wahl.quelle, m.wahl.gruende) for m in mit_luecke] == [(QUELLE_BESTAND, {"inv:4:soc": GRUND_KEIN_KANAL})] * 2
    assert all(m.werte[a.key].voll for m in mit_luecke)
    allein = await monatsreihe(db, aid, [a.key], (2026, 1), (2026, 2), jetzt=JETZT)
    assert [m.wahl.quelle for m in allein] == [QUELLE_KANAL, QUELLE_KANAL]
    leer = await monatsreihe(db, aid, [], (2026, 1), (2026, 2), jetzt=JETZT)
    assert [(m.jahr, m.monat, m.wahl.quelle, m.wahl.gruende, m.werte) for m in leer] == [
        (2026, 1, QUELLE_BESTAND, {"": GRUND_KEINE_EINGAENGE}, {}),
        (2026, 2, QUELLE_BESTAND, {"": GRUND_KEINE_EINGAENGE}, {})]
    preis = await monatsreihe(db, aid, [a.key, "basis:strompreis"], (2026, 1), (2026, 2), jetzt=JETZT)
    assert [(m.wahl.quelle, m.wahl.gruende) for m in preis] == [
        (QUELLE_BESTAND, {"basis:strompreis": GRUND_MITTELWERT_KEIN_DELTA})] * 2
    assert set(preis[0].werte) == {a.key}


# ── Monatsfenster == Bestand auf einem Matrix-Datenstand ────────────────────


@pytest.mark.parametrize("fid", ["M01", "M04"])
async def test_fenster_treffen_den_bestand_monat_und_stunde(fid):
    """Spiegel aus HA nachgefüllt, Tages- und Stundenzeilen über den echten ``aggregate_day`` (01.06.–03.07.), dann:

    * Δ über das Monatsfenster Juni (Lese-Schicht) == ``lade_monats_summen_aus_tagen`` Juni (Monatssumme der Tageszeilen);
    * je Tag die belegten Stunden des Tagesfensters (``stunden``) == Slot 0…23 der Stundenzeilen des Bestands
      (``TagesEnergieProfil``), Stunde für Stunde — das bindet die Lage des Fensters an den Bestand: eine Verschiebung um
      eine Stunde fiele bei Tages- und Monatssummen dieser Datenstände nicht auf (nachts gleiche Rate), hier schon
      (Sprengsatz S16 im Bericht E3)."""
    from backend.models.tages_energie_profil import TagesEnergieProfil
    from backend.services.energie_profil.monats_aus_tagen import lade_monats_summen_aus_tagen
    from backend.services.kanal.fenster import tagesfenster
    from backend.services.kanal.lesen import stunden_stapel
    from backend.services.kanal.nachfuellen import nachfuellen_spiegel
    from backend.tests import achsen_matrix as am
    from backend.tests import pv_achse_matrix as mx

    verz = tempfile.mkdtemp(prefix="eedc-kanal-monat-")
    try:
        engine, db = await mx._neue_db(f"{verz}/x.db")
        macher = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

        @asynccontextmanager
        async def sitzungen():
            async with macher() as s:
                yield s
                await s.commit()

        try:
            form = am.FORMEN[fid]
            svc = am.seed_ha(form)
            aid, _ids = await am.seed_anlage(db, form)
            with am.umgebung(form, svc):
                await nachfuellen_spiegel(sitzungen, aid, jetzt=mx.JETZT, ha_svc=svc)
                await mx.aggregiere_tage(db, form.pvform, aid, mx.TAGE_JUNI + mx.TAGE_JULI)
            kanaele = await kanaele_laden(db, aid, ["basis:einspeisung", "basis:netzbezug"])
            assert set(kanaele) == {"basis:einspeisung", "basis:netzbezug"}
            juni = (await monatsreihe(db, aid, list(kanaele), (2026, 6), (2026, 6), jetzt=JETZT))[0]
            bestand = (await lade_monats_summen_aus_tagen(db, aid, von=(2026, 6), bis=(2026, 6)))[(2026, 6)]
            assert juni.wahl.quelle == QUELLE_KANAL
            assert juni.werte["basis:einspeisung"].delta == pytest.approx(bestand.einspeisung_kwh, abs=0.005)
            assert juni.werte["basis:netzbezug"].delta == pytest.approx(bestand.netzbezug_kwh, abs=0.005)
            assert bestand.einspeisung_kwh > 0 and bestand.netzbezug_kwh > 0
            verglichen = 0
            for tag in mx.TAGE_JUNI:
                je = await stunden_stapel(db, list(kanaele.values()), *tagesfenster(tag), jetzt=JETZT)
                slots = {z.stunde: z for z in (await db.execute(select(TagesEnergieProfil).where(
                    TagesEnergieProfil.anlage_id == aid, TagesEnergieProfil.datum == tag))).scalars().all()}
                for key, spalte in (("basis:einspeisung", "einspeisung_kw"), ("basis:netzbezug", "netzbezug_kw")):
                    werte = je[key].werte
                    assert je[key].voll and len(werte) == 24, (tag, key, len(werte))
                    for slot, w in enumerate(werte):
                        assert w.change == pytest.approx(getattr(slots[slot], spalte) or 0.0, abs=0.0005), (tag, key, slot)
                        verglichen += 1
            assert verglichen == 2 * 24 * len(mx.TAGE_JUNI)
        finally:
            await db.close()
            await engine.dispose()
    finally:
        shutil.rmtree(verz, ignore_errors=True)


async def test_kanaele_laden_nennt_nur_vorhandene(db):
    aid = await _anlage(db)
    await _kanal(db, aid, "basis:einspeisung", ART_SUM, [(h(0), 1.0)])
    got = await kanaele_laden(db, aid, ["basis:einspeisung", "basis:fehlt", "basis:einspeisung"])
    assert list(got) == ["basis:einspeisung"] and isinstance(got["basis:einspeisung"], Kanal)
    assert await kanaele_laden(db, aid, []) == {}
    assert (await db.execute(select(Kanal.key).where(Kanal.anlage_id == aid))).scalars().all() == ["basis:einspeisung"]
