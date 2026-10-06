"""Gleichheitsprobe der Bilanz-Gruppe — Adapter aus Kanälen gegen die heutigen Leser (HA-Bauform E4a, Teil 1,
Auftrag Punkt 4; Bauplan §6a). Baustein und Vergleichsregeln: ``kanal_bilanz_gleichheit.py``.

**Dauerhaft, an jeder Form beider Abnahme-Matrizen** (23 PV-Formen, 10 Achsen-Formen), je Datenstand ``HA`` und
``MQTT``, an jedem Tag (01.06.–03.07.) und Monat (Juni abgeschlossen, Juli laufend; Uhr 04.07. 00:30):

* **Fassung (a) „wie Bestand" == heutiger Leser**, Feld für Feld — ohne eine einzige Ausnahmeklasse (gemessen
  06.10.2026: 47 674 Vergleiche, 0 Abweichungen). Dafür steht keine Regel ein zweites Mal im Baum: (a) legt die
  Kanal-Zeilen dem unveränderten HA-Leser vor und rechnet den Tag mit ``baue_tagestabelle``.
* **Fassung (b) „wie HA" == (a)** überall, wo die Quellenwahl der Bilanz-Gruppe ``kanal`` nennt — außer an den
  Sprungtagen der Form M03 im HA-Datenstand (N-586, Klasse ``SPRUNG_N586``: HAs ``sum`` trägt den Sprung, (a)
  verwirft ihn wie der Bestand). Tage/Monate mit Wahl ``bestand`` sind gezählt (``ZAEHLER_OHNE_NACHTZEILEN``),
  nicht verglichen: dort rechnet in Teil 2 der heutige Leser.

Dazu: die Zielwerte von Teil 2 für M03 (Bericht E0 Punkt 5) und der Tageslauf eines Zählers ohne Nachtzeilen (F08).
Keine Probe liest die Uhr. Schwesterdateien: test_kanal_symmetrie.py, test_kanal_quellenwahl.py.
"""

from __future__ import annotations

from datetime import date, datetime

import pytest
from sqlalchemy import delete, select

from backend.core.berechnungen.verbrauch import berechne_verbrauchs_kennzahlen
from backend.models.kanal import Kanal, KanalStatistik
from backend.services.kanal.bilanz_adapter import (
    FASSUNG_WIE_BESTAND,
    FASSUNG_WIE_HA,
    monats_summen_aus_kanaelen,
    tage_aus_kanaelen,
)
from backend.services.kanal.bilanz_quellenwahl import bilanz_benoetigte_kanaele, bilanz_quellenwahl_tag
from backend.services.kanal.quellenwahl import QUELLE_BESTAND, QUELLE_KANAL
from backend.tests import achsen_matrix as am
from backend.tests import kanal_bilanz_gleichheit as kg
from backend.tests import pv_achse_matrix as mx

_FORMEN = [("achsen", f) for f in am.FORMEN] + [("pv", f) for f in mx.FORMEN]
_FAELLE = [(m, f, art) for art in ("HA", "MQTT") for m, f in _FORMEN]

#: N-586 — die einzige erlaubte Abweichung (b) gegen (a): M03 im HA-Datenstand, an den Sprungtagen 15.06. und
#: 02.07. (je 250 kWh auf Einspeisung und PV-Gesamtzähler) und in ihren beiden Monaten. Je Tag acht Felder: die zwei
#: Schlüssel, die den Sprung tragen (``einspeisung`` und der PV-Träger ohne Zähler ``pv_<West>``, kWp-Rest), die
#: Mengen PV/Einspeisung, der Gesamtverbrauch (Sprung in beiden ⇒ derselbe Wert wie ohne Sprung, der Bestand hat ihn
#: nur auf einer Seite verworfen) und EV, Autarkie, EV-Quote (der Bestand unterdrückt sie am Tag mit Befund, R7).
SPRUNG_N586 = {
    *{("tag", d, f) for d in (date(2026, 6, 15), date(2026, 7, 2)) for f in (
        "komponenten_kwh.einspeisung", "komponenten_kwh.pv_West", "erzeugung_kwh", "einspeisung_kwh",
        "gesamtverbrauch_kwh", "eigenverbrauch_kwh", "autarkie_prozent", "ev_quote_prozent")},
    *{("monat", m, f) for m in kg.MONATE for f in ("einspeisung_kwh", "pv_module_kwh")},
}

#: Zähler ohne Nachtzeilen (F08a/F08b): der BKW-Zähler schläft 21:00–05:00 und die Reihe endet 04.07. 00:00 — sein
#: letzter Stand (03.07. 20:00) erreicht das Ende des 03.07. nicht (Regel (b) ``endet_vor_bis``, benannte
#: Eigenschaft in ``lesen.py``). Tag 03.07. und der laufende Juli nehmen den Bestand. Gemessen 06.10.2026.
ZAEHLER_OHNE_NACHTZEILEN = {"F08a": {date(2026, 7, 3), (2026, 7)}, "F08b": {date(2026, 7, 3), (2026, 7)}}


def _namen(ds) -> dict[str, str]:
    """``pv_<id>`` → ``pv_<Name>``: die Abweichungsliste mit Gerätenamen statt IDs (IDs hängen an der Anlagereihe)."""
    out = {}
    for name, inv_id in ds.ids.items():
        for p in ("pv_", "bkw_", "batterie_"):
            out[f"komponenten_kwh.{p}{inv_id}"] = f"komponenten_kwh.{p}{name}"
    return out


@pytest.mark.parametrize("matrix,fid,art", _FAELLE, ids=[f"{a}-{m}-{f}" for m, f, a in _FAELLE])
async def test_adapter_der_bilanz_gruppe_gleich_dem_heutigen_leser(matrix, fid, art):
    async with kg.datenstand(matrix, fid, art) as ds:
        ba, bb = await kg.probe(ds)
        namen = _namen(ds)
    # (a) == Bestand: jede Ebene verglichen, keine Abweichung, keine Ausnahme.
    assert ba.verglichen["tag"] > 0 and ba.verglichen["monat"] > 0
    assert (ba.verglichen["sensor"] > 0) == (art == "HA")
    assert ba.abweichungen == [], ba.abweichungen[:5]
    # Quellenwahl: überall Kanal, außer der benannten Eigenschaft „Zähler ohne Nachtzeilen".
    bestand = {k for k, w in bb.wahl.items() if w != QUELLE_KANAL}
    assert bestand == ZAEHLER_OHNE_NACHTZEILEN.get(fid, set()), bb.wahl
    assert all(w.endswith("pv_erzeugung_kwh=endet_vor_bis") for k, w in bb.wahl.items() if k in bestand)
    # (b) == (a) überall, wo die Wahl Kanal nennt — außer N-586.
    abw = {(e, w, namen.get(f, f)) for e, w, f, *_ in bb.abweichungen}
    soll = SPRUNG_N586 if (fid, art) == ("M03", "HA") else set()
    assert abw == soll, sorted(abw ^ soll, key=str)[:8]
    assert bb.verglichen["tag"] > 0 and bb.verglichen["monat"] > 0


async def test_m03_sprungtage_beide_fassungen_gegen_die_zielwerte_von_teil_2():
    """Bericht E0 Punkt 5: Monat Juni (S1/S2 I3) nach dem Umstellen PV 790 · Einspeisung 430 · Eigenverbrauch 360 ·
    Gesamtverbrauch 576 · Autarkie 62,5 % — Fassung (b) trifft sie; Fassung (a) nennt die heutigen Werte
    537 · 179 · 358 · 574 (der Sprung des 15.06. verworfen). Tag 15.06.: (a) PV 15 · Einspeisung 5 · EV/Autarkie
    „—" (R7, Befund), (b) 268 · 256 · 12 · 62,5 %."""
    async with kg.datenstand("achsen", "M03", "HA") as ds:
        werte = {}
        for f in (FASSUNG_WIE_BESTAND, FASSUNG_WIE_HA):
            m = (await monats_summen_aus_kanaelen(ds.db, ds.aid, von=(2026, 6), bis=(2026, 6), fassung=f,
                                                  jetzt=kg.JETZT_TS))[(2026, 6)]
            k = berechne_verbrauchs_kennzahlen(
                pv_erzeugung_kwh=m.pv_kwh, einspeisung_kwh=m.einspeisung_kwh, netzbezug_kwh=m.netzbezug_kwh,
                speicher_ladung_kwh=m.speicher_ladung_kwh, speicher_entladung_kwh=m.speicher_entladung_kwh)
            t = (await tage_aus_kanaelen(ds.db, ds.aid, date(2026, 6, 15), date(2026, 6, 15), fassung=f,
                                         jetzt=kg.JETZT_TS))[date(2026, 6, 15)].bilanz
            werte[f] = {"monat": (m.pv_kwh, m.einspeisung_kwh, k.eigenverbrauch_kwh, k.gesamtverbrauch_kwh,
                                  100 * (k.gesamtverbrauch_kwh - m.netzbezug_kwh) / k.gesamtverbrauch_kwh),
                        "tag": (t.erzeugung_kwh, t.einspeisung_kwh, t.eigenverbrauch_kwh, t.gesamtverbrauch_kwh,
                                t.autarkie_prozent)}
    assert werte[FASSUNG_WIE_HA]["monat"] == pytest.approx((790.0, 430.0, 360.0, 576.0, 62.5), abs=1e-6)
    assert werte[FASSUNG_WIE_BESTAND]["monat"][:4] == pytest.approx((537.0, 179.0, 358.0, 574.0), abs=1e-6)
    assert werte[FASSUNG_WIE_BESTAND]["tag"] == (pytest.approx(15.0), pytest.approx(5.0), None,
                                                 pytest.approx(17.2), None)
    assert werte[FASSUNG_WIE_HA]["tag"] == pytest.approx((268.0, 256.0, 12.0, 19.2, 62.5), abs=1e-6)


#: Der simulierte Tageslauf (Uhr absteigend, je Schritt werden die Zeilen entfernt, die der Stundenlauf um diese Zeit
#: noch nicht geschrieben hätte: ``start_ts + 1 h + 5 min > jetzt``). Spalten: Wahl für den 02.07. und den 03.07.
TAGESLAUF = (
    (datetime(2026, 7, 3, 7, 12), QUELLE_KANAL, QUELLE_KANAL),
    (datetime(2026, 7, 3, 7, 3), QUELLE_BESTAND, QUELLE_BESTAND),
    (datetime(2026, 7, 3, 0, 30), QUELLE_BESTAND, QUELLE_BESTAND),
    (datetime(2026, 7, 2, 23, 15), QUELLE_BESTAND, QUELLE_BESTAND),
    (datetime(2026, 7, 2, 23, 9), QUELLE_KANAL, QUELLE_KANAL),
)


@pytest.mark.parametrize("fid", ["F08a", "F08b"])
async def test_zaehler_ohne_nachtzeilen_tageslauf_der_quellenwahl(fid):
    """Auftrag Punkt 4, letzter Absatz (Bauplan Nachtrag E3 (3)): nachts (gemessen 23:15 bis 07:03) nimmt die
    Bilanz-Gruppe für den eben beendeten 02.07. und den laufenden 03.07. den Bestand, ab der Morgenzeile (07:12)
    wieder die Kanäle; um 23:09 ist der 02.07. noch laufend und gedeckt (Soll-Ende 22:00). Wann immer die Wahl
    Kanal nennt, nennt der Kanal für den 02.07. dieselbe Zahl wie der Bestand — beide Fassungen."""
    tag = date(2026, 7, 2)
    async with kg.datenstand("pv", fid, "HA") as ds:
        bestand = (await kg.bestand_tage(ds.db, ds.aid))[tag]
        kids = select(Kanal.id).where(Kanal.anlage_id == ds.aid)
        benoetigt = await bilanz_benoetigte_kanaele(ds.db, ds.aid, tag)
        assert "inv:" + str(ds.ids["Balkon"]) + ":pv_erzeugung_kwh" in benoetigt
        for jetzt, soll_02, soll_03 in TAGESLAUF:
            ts = int(jetzt.timestamp())
            await ds.db.execute(delete(KanalStatistik).where(
                KanalStatistik.kanal_id.in_(kids), KanalStatistik.start_ts + 3600 + 300 > ts))
            await ds.db.commit()
            w02 = await bilanz_quellenwahl_tag(ds.db, ds.aid, tag, jetzt=ts)
            w03 = await bilanz_quellenwahl_tag(ds.db, ds.aid, date(2026, 7, 3), jetzt=ts)
            assert (w02.quelle, w03.quelle) == (soll_02, soll_03), (jetzt, w02.gruende, w03.gruende)
            if w02.quelle == QUELLE_KANAL and not w02.ergebnisse[benoetigt[0]].laufend:
                for f in (FASSUNG_WIE_BESTAND, FASSUNG_WIE_HA):
                    k = (await tage_aus_kanaelen(ds.db, ds.aid, tag, tag, fassung=f, jetzt=ts))[tag]
                    assert k.komponenten_kwh == pytest.approx(bestand.komponenten_kwh, abs=kg.TOL_KOMP), (jetzt, f)
                    assert k.bilanz.erzeugung_kwh == pytest.approx(bestand.bilanz.erzeugung_kwh, abs=kg.TOL_B_TAG)


#: H1 (Bericht E4a-1): eine innere Lücke eines Einzelzählers am Tag — seine HA-Zeile 10.06. 12:00 fehlt, die Energie
#: steht in der Folgestunde. Zwei Regeln fragen je Stunde: die PV-Tages-Präzedenz (F02: alle Erzeuger mit Zähler und
#: Anlagenzähler ⇒ der Tag fällt auf das Aggregat) und N-623 (F05: Süd ist nicht „gemessen" ⇒ kWp-Anteil). Fassung (b)
#: ruft beide unverändert mit den Stunden der Kanäle — ohne Sprung gleich (a) und gleich dem Bestand. Ein Pseudo-Slot
#: (die Regel auf dem Tages-Δ) gäbe hier eine andere Zahl (Sprengsätze S11, S13).
_LUECKE = datetime(2026, 6, 10, 12)


@pytest.mark.parametrize("fid", ["F02", "F05"])
async def test_innere_luecke_eines_einzelzaehlers_b_gleich_a(fid):
    abw = {"sensor.pv_sued": (None, lambda t: t == _LUECKE)}
    async with kg.datenstand("pv", fid, "HA", ha_abweichung=abw) as ds:
        ba, bb = await kg.probe(ds)
        a = (await tage_aus_kanaelen(ds.db, ds.aid, _LUECKE.date(), _LUECKE.date(), fassung=FASSUNG_WIE_BESTAND,
                                     jetzt=kg.JETZT_TS))[_LUECKE.date()]
    assert ba.abweichungen == [] and bb.abweichungen == [], (ba.abweichungen[:3], bb.abweichungen[:3])
    # Die Lücke wirkt wirklich: am Tag trägt Süd den kWp-Anteil des Aggregats (Marke), nicht seine Messung.
    assert a.pv_marken.get(f"pv_{ds.ids['Süd']}") == "kwp_anteil", a.pv_marken


async def test_adapter_lesen_keine_mittelwert_kanaele_und_kennen_nur_zwei_fassungen(db):
    """Die Bilanz-Gruppe kennt nur Mengen-Kanäle; eine unbekannte Fassung ist ein Fehler, kein stiller Rückfall."""
    with pytest.raises(ValueError):
        await tage_aus_kanaelen(db, 1, date(2026, 6, 1), date(2026, 6, 1), fassung="irgendwie", jetzt=kg.JETZT_TS)
