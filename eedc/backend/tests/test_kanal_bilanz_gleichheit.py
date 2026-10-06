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
from backend.models.investition import Investition
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


#: E4a-2 — die Abweichungen des Kanal-Lesers (Weg 2) von heute (Fassung (a)) je Datenstand und Klasse, gemessen
#: 06.10.2026. ``N-586``: der Sprung steht in Tag und Monat (Deckel fällt, Bauplan §7). ``BKW-Kinder``: die Kinder
#: ohne Zähler sind die Lücke ihres BKW (W2-R2), das BKW trägt keinen Schlüssel. ``Teiltag``: der laufende Monat reicht
#: bis zum letzten geschriebenen Stand (Uhr 00:30, eine Stunde des 04.07.). Eine neue Klasse ⇒ rot.
#: Feldsatz wie die Probe Weg 2 (Tag: Schlüssel, Marken, Bilanz samt EV-Quote; Monat: Mengen und `bkw_je_inv`/
#: `bkw_gemessen_je_inv`): Σ 1 224 = BKW-Kinder 1 144 · N-586 21 · Teiltag 59 — PROBE-WEG2 zählt 1 144 / 20 / 60, weil
#: dort die Teiltag-Stunde des M03-Juli bei „Teiltag" steht; hier fällt jede M03-HA-Abweichung unter N-586.
W2_KLASSEN: dict[tuple[str, str, str], dict[str, int]] = {
    ('achsen', 'M01', 'HA'): {'Teiltag': 1},
    ('achsen', 'M01', 'MQTT'): {'Teiltag': 1},
    ('achsen', 'M03', 'HA'): {'N-586': 21},
    ('achsen', 'M03', 'MQTT'): {'Teiltag': 1},
    ('achsen', 'M04', 'HA'): {'Teiltag': 1},
    ('achsen', 'M04', 'MQTT'): {'Teiltag': 1},
    ('achsen', 'M05', 'HA'): {'Teiltag': 1},
    ('achsen', 'M05', 'MQTT'): {'Teiltag': 1},
    ('achsen', 'M06', 'HA'): {'Teiltag': 1},
    ('achsen', 'M06', 'MQTT'): {'Teiltag': 1},
    ('achsen', 'M07', 'HA'): {'Teiltag': 1},
    ('achsen', 'M07', 'MQTT'): {'Teiltag': 1},
    ('achsen', 'M08', 'HA'): {'Teiltag': 1},
    ('achsen', 'M08', 'MQTT'): {'Teiltag': 1},
    ('achsen', 'M09', 'HA'): {'Teiltag': 1},
    ('achsen', 'M09', 'MQTT'): {'Teiltag': 1},
    ('achsen', 'M10', 'HA'): {'Teiltag': 1},
    ('achsen', 'M10', 'MQTT'): {'Teiltag': 1},
    ('pv', 'F01', 'HA'): {'Teiltag': 1},
    ('pv', 'F01', 'MQTT'): {'Teiltag': 1},
    ('pv', 'F02', 'HA'): {'Teiltag': 1},
    ('pv', 'F02', 'MQTT'): {'Teiltag': 1},
    ('pv', 'F03', 'HA'): {'Teiltag': 1},
    ('pv', 'F03', 'MQTT'): {'Teiltag': 1},
    ('pv', 'F04', 'HA'): {'Teiltag': 1},
    ('pv', 'F04', 'MQTT'): {'Teiltag': 1},
    ('pv', 'F05', 'HA'): {'Teiltag': 1},
    ('pv', 'F05', 'MQTT'): {'Teiltag': 1},
    ('pv', 'F06', 'HA'): {'Teiltag': 1},
    ('pv', 'F06', 'MQTT'): {'Teiltag': 1},
    ('pv', 'F07', 'HA'): {'Teiltag': 1},
    ('pv', 'F07', 'MQTT'): {'Teiltag': 1},
    ('pv', 'F09a-G', 'HA'): {'BKW-Kinder': 140, 'Teiltag': 1},
    ('pv', 'F09a-G', 'MQTT'): {'BKW-Kinder': 140, 'Teiltag': 1},
    ('pv', 'F09a-oG', 'HA'): {'BKW-Kinder': 140, 'Teiltag': 1},
    ('pv', 'F09a-oG', 'MQTT'): {'BKW-Kinder': 140, 'Teiltag': 1},
    ('pv', 'F09b-G', 'HA'): {'BKW-Kinder': 107, 'Teiltag': 1},
    ('pv', 'F09b-G', 'MQTT'): {'BKW-Kinder': 107, 'Teiltag': 1},
    ('pv', 'F09b-oG', 'HA'): {'BKW-Kinder': 107, 'Teiltag': 1},
    ('pv', 'F09b-oG', 'MQTT'): {'BKW-Kinder': 107, 'Teiltag': 1},
    ('pv', 'F09c-G', 'HA'): {'BKW-Kinder': 33, 'Teiltag': 1},
    ('pv', 'F09c-G', 'MQTT'): {'BKW-Kinder': 33, 'Teiltag': 1},
    ('pv', 'F09c-oG', 'HA'): {'BKW-Kinder': 33, 'Teiltag': 1},
    ('pv', 'F09c-oG', 'MQTT'): {'BKW-Kinder': 33, 'Teiltag': 1},
    ('pv', 'F10', 'HA'): {'BKW-Kinder': 12, 'Teiltag': 1},
    ('pv', 'F10', 'MQTT'): {'BKW-Kinder': 12, 'Teiltag': 1},
    ('pv', 'F11', 'HA'): {'Teiltag': 1},
    ('pv', 'F11', 'MQTT'): {'Teiltag': 1},
    ('pv', 'F12', 'HA'): {'Teiltag': 1},
    ('pv', 'F12', 'MQTT'): {'Teiltag': 1},
    ('pv', 'F13a', 'HA'): {'Teiltag': 1},
    ('pv', 'F13a', 'MQTT'): {'Teiltag': 1},
    ('pv', 'F13b', 'HA'): {'Teiltag': 1},
    ('pv', 'F13b', 'MQTT'): {'Teiltag': 1},
    ('pv', 'F14', 'HA'): {'Teiltag': 1},
    ('pv', 'F14', 'MQTT'): {'Teiltag': 1},
    ('pv', 'F15', 'HA'): {'Teiltag': 1},
    ('pv', 'F15', 'MQTT'): {'Teiltag': 1},
    ('pv', 'F16', 'HA'): {'Teiltag': 1},
    ('pv', 'F16', 'MQTT'): {'Teiltag': 1},
}


@pytest.mark.parametrize("matrix,fid,art", _FAELLE, ids=[f"{a}-{m}-{f}" for m, f, a in _FAELLE])
async def test_adapter_der_bilanz_gruppe_gleich_dem_heutigen_leser(matrix, fid, art):
    async with kg.datenstand(matrix, fid, art) as ds:
        ba, bb = await kg.probe(ds)
        w2_abw, w2_klassen, w2_n = await kg.probe_w2(ds)
        namen = _namen(ds)
    # E4a-2: der Kanal-Leser trifft die eingefrorene W2-Referenz (Probe-Funktion `weg2.py`) Feld für Feld …
    assert w2_n["referenz"] > 0 and w2_abw == [], w2_abw[:5]
    # … und weicht von heute nur in den benannten Klassen ab, in der gezählten Menge.
    assert dict(w2_klassen) == W2_KLASSEN.get((matrix, fid, art), {}), (matrix, fid, art, dict(w2_klassen))
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


# ── E4a-2: die drei neuen Formen (Vorlage `probe-weg2/neue_formen.py`) ────────────────────────────────────────────
#
# Fassung (a) bleibt gleich dem heutigen Leser; der Kanal-Leser trifft das unabhängig nachgerechnete W2-Soll
# (`pv_achse_matrix.soll_w2`, `achsen_matrix.w2_menge`). Die Abnahme-Matrizen führen dieselben Formen mit allen Wegen.


def _w2_tag_soll(form, tag):
    return mx.soll_tag(form, tag)


@pytest.mark.parametrize("matrix,fid", [("pv", "W2-V"), ("pv", "W2-L"), ("achsen", "W2-E")])
async def test_neue_formen_kanal_leser_trifft_weg2_und_a_bleibt_der_bestand(matrix, fid):
    from backend.services.kanal import bilanz_leser as bl

    async with kg.datenstand(matrix, fid, "HA") as ds:
        ba, _bb = await kg.probe(ds)
        tage = await bl.kanal_tage(ds.db, ds.aid, kg.TAGE[0], kg.TAGE[-1], jetzt=kg.JETZT_TS)
        monate = await bl.kanal_monate(ds.db, ds.aid, von=kg.MONATE[0], bis=kg.MONATE[-1], jetzt=kg.JETZT_TS)
        ids = dict(ds.ids)
    assert ba.abweichungen == [], ba.abweichungen[:3]
    assert set(tage) == set(kg.TAGE), sorted(set(kg.TAGE) - set(tage))   # Lückentag (T4): auch 10./11.06. Kanal
    if matrix == "pv":
        form = mx.MATRIX_FORMEN[fid]
        for t in kg.TAGE:
            soll = mx.soll_tag(form, t)
            ist = {g.name: tage[t].komponenten_kwh.get(f"pv_{ids[g.name]}", tage[t].komponenten_kwh.get(
                f"bkw_{ids[g.name]}", 0.0)) for g in form.geraete}
            assert ist == pytest.approx({g.name: soll.je_geraet.get(g.name, 0.0) for g in form.geraete}, abs=0.006), t
            assert tage[t].bilanz.erzeugung_kwh == pytest.approx(soll.summe, abs=1e-6), t
        juni = mx.soll_monat(form, mx.TAGE_JUNI)
        assert monate[(2026, 6)].pv_kwh == pytest.approx(juni.summe, abs=1e-6)
    else:
        form = am.MATRIX_FORMEN[fid]
        g = form.geraet("BHKW")
        for t in kg.TAGE:
            soll = am.w2_menge(g.felder["erzeugung_kwh"], g.ohne.get("erzeugung_kwh"), (t,))
            assert tage[t].komponenten_kwh.get(f"sonstige_{ids['BHKW']}") == pytest.approx(soll, abs=0.006), t


async def test_lueckentag_traegt_die_luecke_wie_ha():
    """Auftrag Punkt 4 (Gegenprüfung „Übersehen", T4): Süd hat vom 10.06. 08:00 bis 11.06. 13:00 keine Zeile. Der
    10.06. nennt Süd 0 (der Zähler stand still), der 11.06. die ganze Lückenmenge 24 — wie das HA-Energie-Dashboard;
    der Anlagenzähler füllt nur die Lücke (das BKW ohne Zähler: 15 bzw. 0). Der Monat ist unverändert 360/180/90.
    Ohne T4 nähme die Quellenwahl beide Tage aus dem Bestand (Süd ``feiner_als_spanne``)."""
    from backend.services.kanal import bilanz_leser as bl

    async with kg.datenstand("pv", "W2-L", "HA") as ds:
        t = await bl.kanal_tage(ds.db, ds.aid, date(2026, 6, 10), date(2026, 6, 11), jetzt=kg.JETZT_TS)
        m = (await bl.kanal_monate(ds.db, ds.aid, von=(2026, 6), bis=(2026, 6), jetzt=kg.JETZT_TS))[(2026, 6)]
        ids = dict(ds.ids)
    sued, west, bkw = f"pv_{ids['Süd']}", f"pv_{ids['West']}", f"bkw_{ids['Balkon']}"
    assert (t[date(2026, 6, 10)].komponenten_kwh[sued], t[date(2026, 6, 10)].komponenten_kwh[bkw]) == (0.0, 15.0)
    assert (t[date(2026, 6, 11)].komponenten_kwh[sued], t[date(2026, 6, 11)].komponenten_kwh[bkw]) == (24.0, 0.0)
    assert t[date(2026, 6, 11)].komponenten_kwh[west] == 6.0
    assert (m.pv_module_kwh, m.bkw_kwh) == pytest.approx((540.0, 90.0))


async def test_jede_umschaltstelle_nennt_den_sprung_aus_ha_m03():
    """E4a-2, Auftrag Punkt 3: jede der vier Umschaltstellen liest die Bilanz-Gruppe aus den Kanälen — sichtbar an
    M03 (Sprung von 250 kWh auf Einspeisung und PV-Gesamtzähler am 15.06. und 02.07., der Spiegel trägt ihn wie HA):
    (1) Monats-Fakten mit Tageswerten, Juli · (2) Cockpit → Monat Tagesebene, Juli · (3) Kalendermonat je Sensor
    („Aus HA laden"), Juni · (4) Tages-Leser — Cockpit → Tag, Energieprofil Tage und Monat. Der Bestand nennt überall
    die gedeckelten Werte (Juni 179, 15.06. 5, Juli 17). Je Stelle ein Sprengsatz im Bericht E4a-2."""
    from backend.api.routes.aktueller_monat import _collect_tagesebene_data
    from backend.api.routes.energie_profil.monat import get_monatsauswertung
    from backend.api.routes.energie_profil.tage import get_tages_zusammenfassungen
    from backend.api.routes.ha_statistics import get_monatswerte
    from backend.models.anlage import Anlage
    from backend.services.energie_profil.tage_werte import baue_tage_werte
    from backend.services.monats_fakten import lade_monats_fakten

    async with kg.datenstand("achsen", "M03", "HA") as ds:
        form = am.FORMEN["M03"]
        with am.umgebung(form, ds.svc):
            fakt = (await lade_monats_fakten(ds.db, ds.aid, von=(2026, 7), bis=(2026, 7), inkl_nur_tageswerte=True))[0]
            tagesebene = await _collect_tagesebene_data(ds.db, ds.aid, 2026, 7)
            aus_ha = await get_monatswerte(ds.aid, 2026, 6, ds.db)
            anlage = (await ds.db.execute(select(Anlage).where(Anlage.id == ds.aid))).scalar_one()
            tw = {z.datum: z for z in await baue_tage_werte(ds.db, anlage, date(2026, 6, 15), date(2026, 6, 15))}
            tz = await get_tages_zusammenfassungen(ds.aid, date(2026, 6, 15), date(2026, 6, 15), ds.db)
            monat = await get_monatsauswertung(ds.aid, 2026, 6, 10, ds.db)
    assert fakt.zaehler.einspeisung_kwh == pytest.approx(268.0)                               # (1)
    assert tagesebene["einspeisung_kwh"][0] == pytest.approx(268.0)                           # (2)
    assert {b.feld: b.differenz for b in aus_ha.basis}["einspeisung_kwh"] == pytest.approx(430.0)   # (3)
    assert tw[date(2026, 6, 15)].einspeisung == pytest.approx(256.0)                         # (4) Cockpit → Tag
    assert tz[0].komponenten_kwh["einspeisung"] == pytest.approx(256.0)                      # (4) Tage
    assert monat.einspeisung_kwh == pytest.approx(430.0)                                     # (4) Monat


#: Ein Rücksprung in HAs Summe (10.06. 12:00: −2 statt +1 kWh auf der Einspeisung). Der HA-Leser verwirft ihn (R4):
#: Juni 179; der Spiegel trägt ihn wie HA: 180 − 1 − 2 = 177. Unterscheidet die Kalendermonats-Wege (M03 nicht: der
#: Monats-Deckel lässt den Sprung nach der Nacht durch — Bericht E0/E4a-1).
_RUECKSPRUNG = datetime(2026, 6, 10, 12)


async def test_kalendermonats_wege_nehmen_das_kanal_delta_ohne_rueckspruch_verwurf():
    """E4a-2, Umschaltstelle 3 (B-2): „Aus HA laden", alle Monatswerte, Import-Vorschau, Sammelimport,
    Monatsabschluss-Vorschlag und der HA-Weg von Cockpit → Monat nennen für den Kalendermonat das Kanal-Δ, wenn die
    Spiegel aller Bilanz-Sensoren ihn voll decken — ohne Rücksprung-Verwurf und Deckel."""
    from backend.api.routes import aktueller_monat as amr
    from backend.api.routes.ha_statistics import (
        ImportRequest, MonatFeldAuswahl, get_alle_monatswerte, get_import_vorschau, get_monatswerte,
        import_ha_statistics,
    )
    from backend.api.routes.monatsabschluss.views import lade_ha_statistik_werte
    from backend.models.anlage import Anlage
    from backend.models.monatsdaten import Monatsdaten
    from backend.services.monatswert_deckel import deckel_je_sensor

    def _einsp(t):
        return -2.0 if t == _RUECKSPRUNG else (1.0 if t.hour in mx.PROD_STUNDEN else 0.0)

    async with kg.datenstand("pv", "F01", "HA", ha_abweichung={"sensor.einsp": (_einsp, None)}) as ds:
        with mx._umgebung(ds.svc):
            ha_leser = {w.sensor_id: w.differenz for w in ds.svc.get_monatswerte(["sensor.einsp"], 2026, 6).sensoren}
            route = {b.feld: b.differenz for b in (await get_monatswerte(ds.aid, 2026, 6, ds.db)).basis}
            alle = {(r.jahr, r.monat): {b.feld: b.differenz for b in r.basis}
                    for r in await get_alle_monatswerte(ds.aid, None, None, ds.db)}
            vorschau = next(m for m in (await get_import_vorschau(ds.aid, ds.db)).monate if (m.jahr, m.monat) == (2026, 6))
            anlage = (await ds.db.execute(select(Anlage).where(Anlage.id == ds.aid))).scalar_one()
            invs = (await ds.db.execute(select(Investition).where(Investition.anlage_id == ds.aid))).scalars().all()
            vorschlag = await lade_ha_statistik_werte(
                anlage.sensor_mapping["basis"], anlage.sensor_mapping["investitionen"], 2026, 6,
                deckel_je_sensor=deckel_je_sensor(anlage, invs), db=ds.db, anlage_id=ds.aid)
            cockpit = await amr.get_aktueller_monat(anlage_id=ds.aid, jahr=2026, monat=6, db=ds.db)
            await import_ha_statistics(ds.aid, ImportRequest(monate=[MonatFeldAuswahl(jahr=2026, monat=6)]), ds.db)
            await ds.db.commit()
            gespeichert = (await ds.db.execute(select(Monatsdaten).where(
                Monatsdaten.anlage_id == ds.aid, Monatsdaten.jahr == 2026, Monatsdaten.monat == 6))).scalar_one()
    assert ha_leser["sensor.einsp"] == pytest.approx(179.0)          # der HA-Leser verwirft den Rücksprung
    assert route["einspeisung_kwh"] == pytest.approx(177.0)          # „Aus HA laden"
    assert alle[(2026, 6)]["einspeisung_kwh"] == pytest.approx(177.0)
    assert 177.0 in [round(v, 2) for v in (vorschau.ha_werte or {}).values() if isinstance(v, (int, float))]
    assert vorschlag["sensor.einsp"] == pytest.approx(177.0)          # Monatsabschluss-Vorschlag
    assert cockpit.einspeisung_kwh == pytest.approx(177.0)            # Cockpit → Monat, HA-Weg
    assert gespeichert.einspeisung_kwh == pytest.approx(177.0)        # Sammelimport (D3: gespeichert, wie HA)


async def test_kalendermonat_ohne_volle_deckung_bleibt_der_ha_leser():
    """F08a, laufender Juli: der BKW-Zähler schläft nachts und erreicht das Soll-Ende nicht (`endet_vor_bis`) — der
    Kalendermonat bleibt beim HA-Leser, für ALLE Bilanz-Sensoren (eine Wahl)."""
    from backend.api.routes.ha_statistics import get_monatswerte

    async with kg.datenstand("pv", "F08a", "HA") as ds:
        with mx._umgebung(ds.svc):
            route = (await get_monatswerte(ds.aid, 2026, 7, ds.db))
            sids, deckel = await kg.zaehler_sensoren(ds.db, ds.aid)
            leser = {w.sensor_id: w for w in ds.svc.get_monatswerte(sids, 2026, 7, deckel_je_sensor=deckel).sensoren}
    for b in route.basis:
        if b.sensor_id in leser:
            assert b.differenz == pytest.approx(leser[b.sensor_id].differenz), b.feld


async def test_sammelimport_ist_ein_schreibweg_und_ueberschreibt_nur_mit_dem_flag():
    """Nachmessung E4a-2, Punkt 4: der Sammelimport SCHREIBT (anders als „Aus HA laden" und die Vorschau, die nur
    vorschlagen). E4a-2 tauscht nur seine Wertquelle (Kanal-Δ 177 statt HA-Leser 179); die Logik von HEAD bleibt:
    ein gespeicherter Monat bleibt ohne `ueberschreiben` unverändert und wird nur mit dem Flag ersetzt."""
    from backend.api.routes.ha_statistics import ImportRequest, MonatFeldAuswahl, import_ha_statistics
    from backend.models.monatsdaten import Monatsdaten

    def _einsp(t):
        return -2.0 if t == _RUECKSPRUNG else (1.0 if t.hour in mx.PROD_STUNDEN else 0.0)

    async with kg.datenstand("pv", "F01", "HA", ha_abweichung={"sensor.einsp": (_einsp, None)}) as ds:
        ds.db.add(Monatsdaten(anlage_id=ds.aid, jahr=2026, monat=6, einspeisung_kwh=999.0, netzbezug_kwh=888.0))
        await ds.db.commit()
        werte = []
        with mx._umgebung(ds.svc):
            for flag in (False, True):
                await import_ha_statistics(ds.aid, ImportRequest(
                    monate=[MonatFeldAuswahl(jahr=2026, monat=6)], ueberschreiben=flag), ds.db)
                await ds.db.commit()
                md = (await ds.db.execute(select(Monatsdaten).where(
                    Monatsdaten.anlage_id == ds.aid, Monatsdaten.jahr == 2026, Monatsdaten.monat == 6))).scalar_one()
                await ds.db.refresh(md)
                werte.append((md.einspeisung_kwh, md.netzbezug_kwh))
    assert werte[0] == (999.0, 888.0)                                 # ohne Flag: der Vorbestand bleibt
    assert werte[1] == (pytest.approx(177.0), pytest.approx(216.0))  # mit Flag: das Kanal-Δ (ohne Rücksprung-Verwurf)


async def test_kalendermonat_sensormenge_folgt_anschaffung_und_stilllegung_des_monats():
    """Nachmessung E4a-2, Punkt 5: die Bilanz-Sensoren eines Kalendermonats gelten nach den Filtern aktiv · Anschaffung ·
    Stilllegung DIESES Monats (P10), nicht nach dem heutigen Tag.

    * West wird am 01.07. angeschafft, sein Zähler liefert ab dem 30.06. 22:00 — der Juni verlangt ihn nicht und nimmt
      die Kanäle (mit dem Stichtag „heute" verlangte er ihn, fand keinen Stand vor dem Monat und fiel ganz auf den
      HA-Leser zurück).
    * Das Balkonkraftwerk wird am 30.06. stillgelegt, sein Zähler endet mit dem Juni — der Juni verlangt und ersetzt
      ihn (mit „heute" fehlte er im Juni und blieb beim HA-Leser), der Juli verlangt ihn nicht."""
    from backend.services.kanal.bilanz_leser import kanal_kalendermonate

    abw = {"sensor.pv_west": (None, lambda t: t < datetime(2026, 6, 30, 22)),
           "sensor.pv_balkon": (None, lambda t: t >= datetime(2026, 7, 1))}
    async with kg.datenstand("pv", "F02", "HA", ha_abweichung=abw) as ds:
        for name, feld, wert in (("West", "anschaffungsdatum", date(2026, 7, 1)),
                                 ("Balkon", "stilllegungsdatum", date(2026, 6, 30))):
            inv = (await ds.db.execute(select(Investition).where(Investition.id == ds.ids[name]))).scalar_one()
            setattr(inv, feld, wert)
        await ds.db.commit()
        ersatz = await kanal_kalendermonate(ds.db, ds.aid, [(2026, 6), (2026, 7)], jetzt=kg.JETZT_TS)
    assert set(ersatz) == {(2026, 6), (2026, 7)}, sorted(ersatz)
    assert "sensor.pv_west" not in ersatz[(2026, 6)] and "sensor.pv_west" in ersatz[(2026, 7)]
    assert "sensor.pv_balkon" in ersatz[(2026, 6)] and "sensor.pv_balkon" not in ersatz[(2026, 7)]
    assert ersatz[(2026, 6)]["sensor.pv_balkon"].differenz == pytest.approx(90.0)
