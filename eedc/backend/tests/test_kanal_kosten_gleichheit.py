"""Kosten-Kanäle und Preis-Leser aus Kanälen — Regel, Schreiber, Gleichheit, Kaskade (HA-Bauform E4e, Auftrag Punkt 1,
2 und 4).

* **Regel der Stunde** (``core/berechnungen/kosten_stunde.kosten_der_stunde``, rein): Bezug geklemmt, ohne Preis keine
  Bewertung, Null- und Negativpreise sind Werte (P-8), vermiedener Bezug = max(0, PV − Einspeisung) (A-2), Erlös ohne §51.
* **Gleichheit „Kanal-Monat == heutiger Preis-Leser auf denselben Stunden"** am Datenstand der Achsen-Matrix (HA-
  Langzeitstatistik im Recorder-Schema, Spiegel samt Preis-Spiegel, Kosten-Kanäle wie im Produkt, Stundenzeilen über den
  echten ``aggregate_day``; der 31.05. wird mitaggregiert, damit die erste Juni-Stunde ihre Preis-Vorzeile hat). Je Feld
  von ``StrompreisAggregat``: ``abgedeckte_stunden``/``sollstunden`` exakt; ``gewichtet``/``arithmetisch``/``ev`` bis
  **0,01 ct** — beide runden auf 2 Stellen, der Bestand rechnet aus der auf 2 Stellen gerundeten Preis-Mitschrift
  (``rund(strompreis, 2)``) und den auf 3 Stellen gerundeten Stundenmengen, der Kanal aus Spiegel-Mittel und Δ ungerundet:
  die Rundungsreste liegen unter 0,005 ct und können die zweite Stelle höchstens um eine Einheit kippen.
* **T2** (M04, Flex mit Preissensor): gewichteter Ø 25,00 ≠ arithmetischer 29,17 bleibt; **T3** (M08, gepflegter Ø):
  der gepflegte Ø gewinnt in der Kaskade, der EV-Ø kommt trotzdem aus der Messung (P-1); **T1** (M01, fester Tarif):
  kein Preis-Kanal ⇒ kein Kosten-Kanal ⇒ Bestand (Lesart 1).
* **Quellenwahl je Monat**, ``ab_monat``, Einzelmonat = Gruppe, Zeitfenster-Gewicht aus Kanälen, Einheit EUR/kWh,
  Beginn mit dem laufenden Monat (H-2), Neuaufbau bitgleich, Stundenlauf-Einstieg.
* **Dienstliche Ladekosten ohne Abschluss** (M09, ``E4E-DIENSTLICHE-LADEKOSTEN``): Cockpit → Monat zieht sie wie die
  Monats-Fakten ab.

Schwesterdateien: test_preis_aggregat_symmetrie.py (Bestand gruppiert == einzeln), test_kanal_abgeleitet.py (Vorbild),
test_achsen_matrix.py (die Zellen als Richter).
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from unittest.mock import patch

import pytest
from sqlalchemy import delete, select

from backend.core.berechnungen.kosten_stunde import kosten_der_stunde
from backend.tests import achsen_matrix as am
from backend.tests import kanal_bilanz_gleichheit as kg
from backend.tests import pv_achse_matrix as mx

TOL_CENT = 0.01
FELDER = ("gewichtet_cent", "arithmetisch_cent", "abgedeckte_stunden", "sollstunden", "ev_gewichtet_cent")


# ── Regel der Stunde (rein) ─────────────────────────────────────────────────


def test_regel_der_stunde():
    s = kosten_der_stunde(netzbezug_kwh=2.0, pv_kwh=3.0, einspeisung_kwh=1.0, preis_cent=30.0)
    assert (s.kosten_netzbezug_euro, s.netzbezug_bewertet_kwh) == (pytest.approx(0.6), 2.0)
    assert (s.kosten_ev_vermieden_euro, s.ev_bewertet_kwh) == (pytest.approx(0.6), 2.0)
    assert (s.preis_summe_cent, s.preis_stunden) == (30.0, 1.0)
    # ohne Preis: keine Bewertung und keine Preis-Stunde
    s = kosten_der_stunde(netzbezug_kwh=2.0, pv_kwh=3.0, einspeisung_kwh=1.0, preis_cent=None)
    assert (s.kosten_netzbezug_euro, s.netzbezug_bewertet_kwh, s.kosten_ev_vermieden_euro, s.ev_bewertet_kwh,
            s.preis_summe_cent, s.preis_stunden) == (0.0, 0.0, 0.0, 0.0, 0.0, 0.0)
    # negativer Bezug wird geklemmt (Glitch), PV unter Einspeisung ⇒ 0 vermieden; ein Negativpreis ist ein Wert (P-8)
    s = kosten_der_stunde(netzbezug_kwh=-1.0, pv_kwh=1.0, einspeisung_kwh=2.0, preis_cent=-5.0)
    assert (s.kosten_netzbezug_euro, s.netzbezug_bewertet_kwh, s.ev_bewertet_kwh) == (0.0, 0.0, 0.0)
    assert (s.preis_summe_cent, s.preis_stunden) == (-5.0, 1.0)
    s = kosten_der_stunde(netzbezug_kwh=1.0, pv_kwh=None, einspeisung_kwh=None, preis_cent=-5.0)
    assert (s.kosten_netzbezug_euro, s.netzbezug_bewertet_kwh) == (pytest.approx(-0.05), 1.0)
    s = kosten_der_stunde(netzbezug_kwh=1.0, pv_kwh=None, einspeisung_kwh=None, preis_cent=0.0)
    assert (s.kosten_netzbezug_euro, s.netzbezug_bewertet_kwh, s.preis_stunden) == (0.0, 1.0, 1.0)


def test_einheit_des_preis_kanals():
    from backend.services.kanal.kosten import preis_faktor
    from backend.services.kanal.preis_leser import aggregat_aus_kanaelen

    assert (preis_faktor("ct/kWh"), preis_faktor("EUR/kWh"), preis_faktor("€/kWh"), preis_faktor("EUR/MWh")) == (
        1.0, 100.0, 100.0, 0.1)
    a = aggregat_aus_kanaelen(2026, 6, kosten_euro=3.0, bewertet_kwh=12.0, ev_kosten_euro=0.0, ev_kwh=0.0,
                              preis_summe_cent=24 * 0.3 * preis_faktor("EUR/kWh"), stunden=24.0)
    assert (a.gewichtet_cent, a.arithmetisch_cent, a.abgedeckte_stunden, a.sollstunden, a.ev_gewichtet_cent) == (
        25.0, 30.0, 24, 720, None)
    assert aggregat_aus_kanaelen(2026, 6, kosten_euro=0.0, bewertet_kwh=0.0, ev_kosten_euro=0.0, ev_kwh=0.0,
                                 preis_summe_cent=0.0, stunden=0.0) is None
    # kein bewerteter Bezug: kein gewichteter Wert (wie der Bestand)
    assert aggregat_aus_kanaelen(2026, 6, kosten_euro=0.0, bewertet_kwh=0.0, ev_kosten_euro=1.0, ev_kwh=4.0,
                                 preis_summe_cent=60.0, stunden=3.0).gewichtet_cent is None


def test_mengen_der_stunde_nach_weg2_mit_erzeugern_hinter_dem_zaehler():
    """Die Mengen einer Stunde: PV = Σ Geräte samt Erzeuger hinter dem Zähler (wie ``pv_kw`` der Stundenzeile), der
    Anlagenzähler füllt nur Geräte ohne Kanal (W2-R2/R3); Netzbezug und Einspeisung als Summe ihrer Zähler."""
    from backend.core.berechnungen.pv_verteilung import PvTraeger
    from backend.services.kanal.kosten import _TagesAuswahl, mengen_der_stunde
    from backend.services.snapshot.tages_tabelle import TabellenEintrag

    e = [TabellenEintrag("inv:1:pv_erzeugung_kwh", "pv", None, "inv:1:pv_erzeugung_kwh", "pv_1", 1),
         TabellenEintrag("basis:pv_gesamt", "pv", None, "basis:pv_gesamt", "pv_gesamt", 1),
         TabellenEintrag("inv:3:erzeugung_kwh", "erzeugung_sonstiges", None, "inv:3:erzeugung_kwh", "sonstige_3", 1),
         TabellenEintrag("basis:einspeisung", "einspeisung", None, "basis:einspeisung", "einspeisung", 1),
         TabellenEintrag("basis:netzbezug", "netzbezug", None, "basis:netzbezug", "netzbezug", 1)]
    a = _TagesAuswahl(tuple(e), (PvTraeger(1, "pv-module", 5.0), PvTraeger(2, "pv-module", 5.0)))
    netz, pv, einsp = mengen_der_stunde(a, {"inv:1:pv_erzeugung_kwh": 1.0, "basis:pv_gesamt": 3.0,
                                            "inv:3:erzeugung_kwh": 0.25, "basis:einspeisung": 0.5,
                                            "basis:netzbezug": 0.0})
    # Gerät 1 gemessen 1,0; Gerät 2 ohne Kanal bekommt den Rest 3,0 − 1,0 = 2,0; dazu das BHKW 0,25
    assert (netz, pv, einsp) == (0.0, pytest.approx(3.25), 0.5)


# ── Datenstand ──────────────────────────────────────────────────────────────


async def _leer(*_a, **_k):
    return {}, None


async def _mit_mai(ds, fid):
    """Den 31.05. mitaggregieren — dann hat die Zeile 0 des 01.06. ihre Preis-Vorzeile (wie im Produkt)."""
    form = am.MATRIX_FORMEN[fid]
    with am.umgebung(form, ds.svc):
        await mx.aggregiere_tage(ds.db, form.pvform, ds.aid, [date(2026, 5, 31)])


async def _beide(ds, fid):
    from backend.services import strompreis_aggregator as sa
    from backend.services.kanal import preis_leser

    with am.umgebung(am.MATRIX_FORMEN[fid], ds.svc):
        kanal = await sa.lade_preis_aggregate_je_monat(ds.db, ds.aid)
        with patch.object(preis_leser, "preis_monate", new=_leer):
            bestand = await sa.lade_preis_aggregate_je_monat(ds.db, ds.aid)
    return kanal, bestand


#: Bitgleich verlangt (Nachzug B: Σ Preis ÷ Stunden aus zwei Δ wie der Bestand ``Σ preis / n``).
BITGLEICH = ("arithmetisch_cent", "abgedeckte_stunden", "sollstunden")


def _gleich(a, b) -> list:
    out = []
    for f in FELDER:
        x, y = getattr(a, f), getattr(b, f)
        if f in BITGLEICH:
            if x != y:
                out.append((f, x, y))
        elif isinstance(x, float) and isinstance(y, float):
            if abs(x - y) > TOL_CENT + 1e-9:
                out.append((f, x, y))
        elif x != y:
            out.append((f, x, y))
    return out


@pytest.mark.asyncio
@pytest.mark.parametrize("fid", ["M04", "M08"])
async def test_kanal_monat_gleich_bestand_auf_denselben_stunden(fid):
    """Juni (abgeschlossen, voll gedeckt): jedes Feld des Aggregats aus den Kanälen == heutiger Leser."""
    from backend.services.kanal.preis_leser import preis_monate

    async with kg.datenstand("achsen", fid, "HA") as ds:
        await _mit_mai(ds, fid)
        with am.umgebung(am.MATRIX_FORMEN[fid], ds.svc):
            je, ab = await preis_monate(ds.db, ds.aid)
        assert (2026, 6) in je and (2026, 7) in je and ab == (2026, 6), (sorted(je), ab)
        # Nachzug A: kein Einspeise-Erlös-Kanal (kein Leser, kein Neuaufbau bei Tarifänderung)
        from backend.models.kanal import Kanal

        keys = set((await ds.db.execute(select(Kanal.key).where(Kanal.anlage_id == ds.aid))).scalars().all())
        assert "abgeleitet:basis:erloes_einspeisung" not in keys
        assert {"abgeleitet:basis:preis_summe", "abgeleitet:basis:preis_stunden"} <= keys
        kanal, bestand = await _beide(ds, fid)
        k, b = kanal.hole(2026, 6), bestand.hole(2026, 6)
        assert k is not None and b is not None
        assert not _gleich(k, b), _gleich(k, b)
        # der Bestand lädt ab dem durchgehend gedeckten Ende keine Stundenzeile mehr
        from backend.services import strompreis_aggregator as sa

        gerufen = []
        echt = sa._zeilen_mit_gepaartem_preis

        async def zaehlend(*a, **kw):
            gerufen.append((kw.get("ab"), kw.get("bis_exklusive")))
            return await echt(*a, **kw)

        with am.umgebung(am.MATRIX_FORMEN[fid], ds.svc), patch.object(sa, "_zeilen_mit_gepaartem_preis", new=zaehlend):
            await sa.lade_preis_aggregate_je_monat(ds.db, ds.aid)
        assert gerufen == [(None, date(2026, 6, 1)), (date(2026, 8, 1), None)], gerufen
        # T2: der bezugsgewichtete Ø ist NICHT der arithmetische (Bezug nur in 25-ct-Stunden)
        assert (k.gewichtet_cent, k.arithmetisch_cent, k.abgedeckte_stunden) == (25.0, 29.17, 720)
        # der EV-Ø nimmt die Stunden des vermiedenen Bezugs (Sonne 10–15 Uhr, davon 11–14 Uhr zu 50 ct)
        assert k.ev_gewichtet_cent == b.ev_gewichtet_cent and k.ev_gewichtet_cent > k.gewichtet_cent


@pytest.mark.asyncio
async def test_paarung_menge_und_preis_derselben_stunde():
    """Menge und Preis derselben Stunde (N-387): der Preis der Matrix-Form ist um eine Stunde verschoben gleich (seine
    Ränder liegen in bezugsfreien Stunden) — hier ein Preis, der es NICHT ist: Preis = Uhrzeit (ct). Spiegel-Mittel der
    Stunde ``[h, h+1)`` = h, Mitschrift der Stundenzeile forward ebenso; die Kosten-Kanäle werden neu aufgebaut. Der
    Kanal-Monat ist dann nur gleich dem Bestand, wenn beide dieselbe Stunde paaren."""
    from sqlalchemy import update

    from backend.models.anlage import Anlage
    from backend.models.kanal import Kanal, KanalStatistik
    from backend.models.tages_energie_profil import TagesEnergieProfil
    from backend.services.kanal.abgeleitet import verwerfe_ab
    from backend.services.kanal.kosten import PREIS_KEY, schreibe_kosten

    async with kg.datenstand("achsen", "M04", "HA") as ds:
        await _mit_mai(ds, "M04")
        db, aid = ds.db, ds.aid
        k = (await db.execute(select(Kanal).where(Kanal.anlage_id == aid, Kanal.key == PREIS_KEY))).scalar_one()
        for z in (await db.execute(select(KanalStatistik).where(KanalStatistik.kanal_id == k.id))).scalars().all():
            z.mean = float(datetime.fromtimestamp(z.start_ts).hour)
        await db.execute(update(TagesEnergieProfil).where(TagesEnergieProfil.anlage_id == aid)
                         .values(strompreis_cent=TagesEnergieProfil.stunde * 1.0))
        await db.commit()
        assert await verwerfe_ab(db, aid, 0) > 0
        await db.commit()
        anlage = (await db.execute(select(Anlage).where(Anlage.id == aid))).scalar_one()
        with am.umgebung(am.MATRIX_FORMEN["M04"], ds.svc):
            assert await schreibe_kosten(db, anlage, mx.JETZT) > 0
            await db.commit()
        kanal, bestand = await _beide(ds, "M04")
        k6, b6 = kanal.hole(2026, 6), bestand.hole(2026, 6)
        assert not _gleich(k6, b6), _gleich(k6, b6)
        assert k6.gewichtet_cent != k6.arithmetisch_cent and k6.arithmetisch_cent == 11.5


@pytest.mark.asyncio
async def test_preis_kanal_in_euro_je_kwh():
    """Meldet der Preissensor €/kWh (der Kanal führt HAs Einheit, keine Umrechnung im Schreiber), rechnen Kosten-Kanal
    und Leser mit derselben Regel wie die Mitschrift (× 100) — der Kanal-Monat bleibt gleich dem Bestand (ct)."""
    from backend.models.anlage import Anlage
    from backend.models.kanal import Kanal, KanalStatistik
    from backend.services.kanal.abgeleitet import verwerfe_ab
    from backend.services.kanal.kosten import PREIS_KEY, schreibe_kosten

    async with kg.datenstand("achsen", "M04", "HA") as ds:
        await _mit_mai(ds, "M04")
        db, aid = ds.db, ds.aid
        k = (await db.execute(select(Kanal).where(Kanal.anlage_id == aid, Kanal.key == PREIS_KEY))).scalar_one()
        k.einheit = "EUR/kWh"
        for z in (await db.execute(select(KanalStatistik).where(KanalStatistik.kanal_id == k.id))).scalars().all():
            z.mean = z.mean / 100.0
        await db.commit()
        assert await verwerfe_ab(db, aid, 0) > 0
        await db.commit()
        anlage = (await db.execute(select(Anlage).where(Anlage.id == aid))).scalar_one()
        with am.umgebung(am.MATRIX_FORMEN["M04"], ds.svc):
            assert await schreibe_kosten(db, anlage, mx.JETZT) > 0
            await db.commit()
        kanal, bestand = await _beide(ds, "M04")
        k6, b6 = kanal.hole(2026, 6), bestand.hole(2026, 6)
        assert not _gleich(k6, b6), _gleich(k6, b6)
        assert (k6.gewichtet_cent, k6.arithmetisch_cent) == (25.0, 29.17)


@pytest.mark.asyncio
async def test_laufender_monat_eine_stunde_aktueller():
    """Juli (laufend, Uhr 04.07. 00:30): gewichtet und EV-Ø gleich; der Kanal kennt die Stunde 03.07. 23:00 schon
    (Teiltag — Klasse TEILTAG-ZWEI-MONATSGRENZEN), der Bestand erst mit der Zeile 0 des 04.07."""
    async with kg.datenstand("achsen", "M04", "HA") as ds:
        kanal, bestand = await _beide(ds, "M04")
        k, b = kanal.hole(2026, 7), bestand.hole(2026, 7)
        assert (k.gewichtet_cent, k.ev_gewichtet_cent) == (b.gewichtet_cent, b.ev_gewichtet_cent)
        assert (k.abgedeckte_stunden, b.abgedeckte_stunden) == (73, 72)


@pytest.mark.asyncio
async def test_einzelmonat_gleich_gruppe_und_kaskade_t2_t3():
    """``berechne_monats_durchschnittspreis`` (Cockpit → Monat, Monatsabschluss) nimmt dieselbe Wahl wie die Gruppe;
    T3: der gepflegte Ø gewinnt in der Kaskade, der EV-Ø kommt aus der Messung (P-1)."""
    from backend.models.monatsdaten import Monatsdaten
    from backend.services import strompreis_aggregator as sa
    from backend.services.kanal import preis_leser

    async with kg.datenstand("achsen", "M08", "HA") as ds:
        await _mit_mai(ds, "M08")
        with am.umgebung(am.MATRIX_FORMEN["M08"], ds.svc):
            einzeln = await sa.berechne_monats_durchschnittspreis(ds.aid, 2026, 6, ds.db)
            gruppe = (await sa.lade_preis_aggregate_je_monat(ds.db, ds.aid)).hole(2026, 6)
            assert einzeln == gruppe
            ds.db.add(Monatsdaten(anlage_id=ds.aid, jahr=2026, monat=6, netzbezug_durchschnittspreis_cent=33.0))
            await ds.db.commit()
            md = (await ds.db.execute(select(Monatsdaten).where(Monatsdaten.anlage_id == ds.aid))).scalar_one()
            p = await sa.aufgeloester_monatspreis(ds.db, ds.aid, 2026, 6, md, None)
            assert (p.cent, p.herkunft, p.ev_cent) == (33.0, sa.PREIS_HERKUNFT_GEPFLEGT, gruppe.ev_gewichtet_cent)
            p = await sa.aufgeloester_monatspreis(ds.db, ds.aid, 2026, 6, None, None)
            assert (p.cent, p.herkunft, p.abdeckung) == (25.0, sa.PREIS_HERKUNFT_GEMESSEN, 1.0)
            # dieselbe Kaskade ohne Kanal: dieselben Zahlen
            with patch.object(preis_leser, "preis_monate", new=_leer):
                q = await sa.aufgeloester_monatspreis(ds.db, ds.aid, 2026, 6, None, None)
            assert (q.cent, q.herkunft, q.ev_cent) == (p.cent, p.herkunft, p.ev_cent)


@pytest.mark.asyncio
async def test_t1_ohne_preis_kanal_kein_kosten_kanal():
    """Fester Tarif (M01): kein Preissensor ⇒ kein Kosten-Kanal ⇒ der heutige Leser (Lesart 1)."""
    from backend.models.kanal import Kanal
    from backend.services.kanal.preis_leser import preis_monate

    async with kg.datenstand("achsen", "M01", "HA") as ds:
        keys = set((await ds.db.execute(select(Kanal.key).where(Kanal.anlage_id == ds.aid))).scalars().all())
        assert not {k for k in keys if k.startswith("abgeleitet:basis:")} and "basis:strompreis" not in keys
        assert await preis_monate(ds.db, ds.aid) == ({}, None)


@pytest.mark.asyncio
@pytest.mark.parametrize("schluessel", ["abgeleitet:basis:kosten_ev_vermieden", "abgeleitet:basis:preis_stunden"])
async def test_quellenwahl_je_monat_luecke_im_kanal(schluessel):
    """Fehlen EINEM der sechs Kosten-Kanäle Juni-Stunden am Monatsanfang, ist der Juni nicht gedeckt — der ganze Juni
    aus dem Bestand, der Juli aus dem Kanal; der Bestand lädt den Juli nicht (``ab_monat``)."""
    from backend.models.kanal import Kanal, KanalStatistik
    from backend.services.kanal.preis_leser import preis_monate

    async with kg.datenstand("achsen", "M04", "HA") as ds:
        await _mit_mai(ds, "M04")
        k = (await ds.db.execute(select(Kanal).where(Kanal.anlage_id == ds.aid, Kanal.key == schluessel))).scalar_one()
        # Nur EIN der vier Mengen-Kanäle verliert seinen Anfang: die Wahl gilt für alle Eingänge.
        await ds.db.execute(delete(KanalStatistik).where(
            KanalStatistik.kanal_id == k.id, KanalStatistik.start_ts < int(datetime(2026, 6, 2).timestamp())))
        await ds.db.commit()
        with am.umgebung(am.MATRIX_FORMEN["M04"], ds.svc):
            je, ab = await preis_monate(ds.db, ds.aid)
        assert (2026, 6) not in je and (2026, 7) in je and ab == (2026, 7)
        kanal, bestand = await _beide(ds, "M04")
        assert kanal.hole(2026, 6) == bestand.hole(2026, 6)


@pytest.mark.asyncio
async def test_preis_luecke_wie_im_bestand():
    """Ein Tag ohne Preis (Sensor aus): die Stunden sind nicht bewertet — Kosten-Kanal und Stundenzeilen mit derselben
    Lücke nennen dasselbe, auch die Zahl der Stunden mit Preis (696 statt 720) und den arithmetischen Ø."""
    from sqlalchemy import update

    from backend.models.anlage import Anlage
    from backend.models.kanal import Kanal, KanalStatistik
    from backend.models.tages_energie_profil import TagesEnergieProfil
    from backend.services.kanal.abgeleitet import verwerfe_ab
    from backend.services.kanal.kosten import PREIS_KEY, schreibe_kosten

    async with kg.datenstand("achsen", "M04", "HA") as ds:
        await _mit_mai(ds, "M04")
        db, aid = ds.db, ds.aid
        k = (await db.execute(select(Kanal).where(Kanal.anlage_id == aid, Kanal.key == PREIS_KEY))).scalar_one()
        # Mitschrift der Zeilen des 10.06. (forward [s, s+1)) ⇔ Spiegel-Stunden 10.06. 00:00 … 23:00
        await db.execute(delete(KanalStatistik).where(
            KanalStatistik.kanal_id == k.id, KanalStatistik.start_ts >= int(datetime(2026, 6, 10).timestamp()),
            KanalStatistik.start_ts < int(datetime(2026, 6, 11).timestamp())))
        await db.execute(update(TagesEnergieProfil).where(
            TagesEnergieProfil.anlage_id == aid, TagesEnergieProfil.datum == date(2026, 6, 10)).values(strompreis_cent=None))
        await db.commit()
        assert await verwerfe_ab(db, aid, 0) > 0
        await db.commit()
        anlage = (await db.execute(select(Anlage).where(Anlage.id == aid))).scalar_one()
        with am.umgebung(am.MATRIX_FORMEN["M04"], ds.svc):
            assert await schreibe_kosten(db, anlage, mx.JETZT) > 0
            await db.commit()
        kanal, bestand = await _beide(ds, "M04")
        k6, b6 = kanal.hole(2026, 6), bestand.hole(2026, 6)
        assert not _gleich(k6, b6), _gleich(k6, b6)
        assert k6.abgedeckte_stunden == 696


@pytest.mark.asyncio
async def test_die_kanal_messung_gewinnt_in_beiden_lesern():
    """Gedeckt heißt: der Kanal sagt es — auch wenn die Stundenzeilen etwas anderes trügen. Die Preis-Mitschrift der
    Stundenzeilen wird verfälscht; Einzelmonat und Gruppe nennen weiter den Kanal, der Bestand die Verfälschung."""
    from sqlalchemy import update

    from backend.models.tages_energie_profil import TagesEnergieProfil
    from backend.services import strompreis_aggregator as sa

    async with kg.datenstand("achsen", "M04", "HA") as ds:
        await _mit_mai(ds, "M04")
        await ds.db.execute(update(TagesEnergieProfil).where(TagesEnergieProfil.anlage_id == ds.aid)
                            .values(strompreis_cent=99.0))
        await ds.db.commit()
        kanal, bestand = await _beide(ds, "M04")
        with am.umgebung(am.MATRIX_FORMEN["M04"], ds.svc):
            einzeln = await sa.berechne_monats_durchschnittspreis(ds.aid, 2026, 6, ds.db)
        assert bestand.hole(2026, 6).gewichtet_cent == 99.0
        assert kanal.hole(2026, 6).gewichtet_cent == 25.0 == einzeln.gewichtet_cent
        assert einzeln == kanal.hole(2026, 6)


@pytest.mark.asyncio
async def test_zeitfenster_gewicht_aus_den_kanaelen():
    """Stufe „Zeitfenster" (HT/NT): der Netzbezug je Stunde aus den Kanälen == aus den Stundenzeilen (M01, Netzbezug nur
    außerhalb der Sonne); NT 22–06 zu 20 ct, sonst 30 ct."""
    from backend.core.berechnungen.zeittarif import (
        gewichteter_arbeitspreis_aus_zellen, gewichteter_arbeitspreis_cent, uhrzeit_des_slots,
    )
    from backend.models.strompreis import Strompreis, StrompreisZeitfenster
    from backend.services import strompreis_aggregator as sa
    from backend.services.kanal import preis_leser

    async with kg.datenstand("achsen", "M01", "HA") as ds:
        await _mit_mai(ds, "M01")
        tarif = (await ds.db.execute(select(Strompreis).where(Strompreis.anlage_id == ds.aid))).scalar_one()
        # Fenster 08–11 Uhr: es schneidet den Sonnenbeginn (Bezug nur außerhalb 10–15 Uhr) — um eine Stunde verschoben
        # wöge es eine andere Menge (die Paarung Stunde → Slot zählt).
        ds.db.add(StrompreisZeitfenster(strompreis_id=tarif.id, von_stunde=8, bis_stunde=11, wochentage="0123456",
                                        arbeitspreis_cent_kwh=20.0))
        await ds.db.commit()
        ds.db.expire_all()           # die Fenster-Relation neu laden (selectin beim ersten Laden ohne Fenster)
        tarif = (await ds.db.execute(select(Strompreis).where(Strompreis.anlage_id == ds.aid))).scalar_one()
        assert len(tarif.zeitfenster) == 1
        with am.umgebung(am.MATRIX_FORMEN["M01"], ds.svc):
            slots = await preis_leser.netzbezug_slots_des_monats(ds.db, ds.aid, 2026, 6)
            assert slots is not None and len(slots) == 720
            # HA-Bauform E4f (Auftrag Punkt 3b): der Preis-Weg liest die Gewichte je (Wochentag, Uhrstunde) in EINER
            # Anweisung — sie sind die je Zelle summierten, auf 0 geklemmten Slots.
            zellen = await preis_leser.netzbezug_zellen_des_monats(ds.db, ds.aid, 2026, 6)
            aus_slots: dict = {}
            for d, st, kwh in slots:
                u = uhrzeit_des_slots(d, st)
                aus_slots[(u.weekday(), u.hour)] = aus_slots.get((u.weekday(), u.hour), 0.0) + max(0.0, kwh)
            assert {(w, h): round(v, 9) for w, h, v in zellen} == {k: round(v, 9) for k, v in aus_slots.items()}
            assert gewichteter_arbeitspreis_aus_zellen(tarif, zellen) == pytest.approx(
                gewichteter_arbeitspreis_cent(tarif, slots), abs=1e-9)
            kanal = await sa.wirksamer_arbeitspreis_cent(ds.db, ds.aid, 2026, 6, tarif)
            with patch.object(preis_leser, "netzbezug_zellen_des_monats", new=lambda *a, **k: _keine()):
                bestand = await sa.wirksamer_arbeitspreis_cent(ds.db, ds.aid, 2026, 6, tarif)
        assert kanal == bestand and 20.0 < kanal < 30.0, (kanal, bestand)
        # Deckt ein Netzbezugs-Kanal den Monat nicht (Anfang fehlt), kommt die Messung aus den Stundenzeilen.
        from backend.models.kanal import Kanal, KanalStatistik

        nk = (await ds.db.execute(select(Kanal).where(Kanal.anlage_id == ds.aid, Kanal.key == "basis:netzbezug"))
              ).scalar_one()
        await ds.db.execute(delete(KanalStatistik).where(
            KanalStatistik.kanal_id == nk.id, KanalStatistik.start_ts < int(datetime(2026, 6, 2).timestamp())))
        await ds.db.commit()
        with am.umgebung(am.MATRIX_FORMEN["M01"], ds.svc):
            assert await preis_leser.netzbezug_slots_des_monats(ds.db, ds.aid, 2026, 6) is None
            assert await preis_leser.netzbezug_zellen_des_monats(ds.db, ds.aid, 2026, 6) is None
            assert await sa.wirksamer_arbeitspreis_cent(ds.db, ds.aid, 2026, 6, tarif) == bestand


async def _keine():
    return None


@pytest.mark.asyncio
async def test_beginn_mit_dem_laufenden_monat_und_neuaufbau():
    """H-2: ein neuer Kosten-Kanal (ohne ``ab_ts``) beginnt eine Stunde vor dem Monatsfenster des laufenden Monats —
    der Juli ist gedeckt, der Juni nicht. Neuaufbau (``verwerfe_ab``) schreibt bitgleich neu. Ohne Preis-Kanal nichts."""
    from backend.models.anlage import Anlage
    from backend.models.kanal import Kanal, KanalQuelle, KanalStatistik
    from backend.services.kanal.abgeleitet import verwerfe_ab
    from backend.services.kanal.fenster import monatsfenster
    from backend.services.kanal.kosten import KOSTEN_KANAELE, PREIS_KEY, schreibe_kosten
    from backend.services.kanal.preis_leser import preis_monate

    async def zeilen(db, aid):
        out = {}
        for k in (await db.execute(select(Kanal).where(Kanal.anlage_id == aid, Kanal.key.in_(list(KOSTEN_KANAELE))))
                  ).scalars().all():
            out[k.key] = [(z.start_ts, z.sum) for z in (await db.execute(select(KanalStatistik).where(
                KanalStatistik.kanal_id == k.id).order_by(KanalStatistik.start_ts))).scalars().all()]
        return out

    async def entfernen(db, aid, keys):
        """Kanäle samt Zeilen und Quellen entfernen — der Zustand vor dem Update (SQLite vergibt die Kanal-Id neu)."""
        ids = list((await db.execute(select(Kanal.id).where(Kanal.anlage_id == aid, Kanal.key.in_(list(keys))))
                    ).scalars().all())
        await db.execute(delete(KanalStatistik).where(KanalStatistik.kanal_id.in_(ids)))
        await db.execute(delete(KanalQuelle).where(KanalQuelle.kanal_id.in_(ids)))
        await db.execute(delete(Kanal).where(Kanal.id.in_(ids)))
        await db.commit()

    async with kg.datenstand("achsen", "M04", "HA") as ds:
        db, aid = ds.db, ds.aid
        # Seed mit `ab_ts = REIHE_VON`: die erste Spiegel-Stunde hat keinen Vorstand — der Kanal beginnt eine Stunde später
        ks = (await db.execute(select(Kanal).where(Kanal.anlage_id == aid, Kanal.key.in_(list(KOSTEN_KANAELE))))
              ).scalars().all()
        assert {k.aufbaubar_ab for k in ks} == {int(mx.REIHE_VON.timestamp()) + 3600}
        anlage = (await db.execute(select(Anlage).where(Anlage.id == aid))).scalar_one()
        await entfernen(db, aid, KOSTEN_KANAELE)
        with am.umgebung(am.MATRIX_FORMEN["M04"], ds.svc):
            assert await schreibe_kosten(db, anlage, mx.JETZT) > 0
            await db.commit()
            ks = (await db.execute(select(Kanal).where(Kanal.anlage_id == aid, Kanal.key.in_(list(KOSTEN_KANAELE))))
                  ).scalars().all()
            assert {k.aufbaubar_ab for k in ks} == {monatsfenster(2026, 7)[0] - 3600}
            je, ab = await preis_monate(db, aid)
            assert set(je) == {(2026, 7)} and ab == (2026, 7)
            vorher = await zeilen(db, aid)
            # ein zweiter Lauf schreibt nichts (idempotent ab der letzten Zeile)
            assert await schreibe_kosten(db, anlage, mx.JETZT) == 0
            # Neuaufbau ab dem 02.07.: dieselben Zeilen
            assert await verwerfe_ab(db, aid, int(datetime(2026, 7, 2).timestamp())) > 0
            await db.commit()
            assert await schreibe_kosten(db, anlage, mx.JETZT) > 0
            await db.commit()
            assert await zeilen(db, aid) == vorher
            # ohne Preis-Kanal: kein Kosten-Kanal
            await entfernen(db, aid, [*KOSTEN_KANAELE, PREIS_KEY])
            assert await schreibe_kosten(db, anlage, mx.JETZT) == 0


@pytest.mark.asyncio
async def test_stundenlauf_schreibt_die_kosten_kanaele():
    """Der Einstieg des Stundenlaufs (``schreibe_kanaele_im_stundenlauf``) schreibt die Kosten-Kanäle nach dem Spiegel."""
    from backend.models.anlage import Anlage
    from backend.models.kanal import Kanal, KanalStatistik
    from backend.services.kanal.kosten import KOSTEN_NETZBEZUG_KEY
    from backend.services.kanal.schreiber import schreibe_kanaele_im_stundenlauf

    async with kg.datenstand("achsen", "M04", "HA") as ds:
        db, aid = ds.db, ds.aid
        k = (await db.execute(select(Kanal).where(Kanal.anlage_id == aid, Kanal.key == KOSTEN_NETZBEZUG_KEY))).scalar_one()
        grenze = int(datetime(2026, 7, 3, 12).timestamp())
        await db.execute(delete(KanalStatistik).where(KanalStatistik.kanal_id == k.id, KanalStatistik.start_ts >= grenze))
        await db.commit()
        anlage = (await db.execute(select(Anlage).where(Anlage.id == aid))).scalar_one()
        with am.umgebung(am.MATRIX_FORMEN["M04"], ds.svc):
            assert (await schreibe_kanaele_im_stundenlauf(db, anlage, mx.JETZT)) is not None
            await db.commit()
        letzte = (await db.execute(select(KanalStatistik.start_ts).where(KanalStatistik.kanal_id == k.id)
                                   .order_by(KanalStatistik.start_ts.desc()).limit(1))).scalar_one()
        assert letzte >= grenze


# ── Dienstliche Ladekosten ohne Abschluss (M09) ─────────────────────────────


@pytest.mark.asyncio
async def test_dienstliche_ladekosten_im_monat_ohne_abschluss():
    """Cockpit → Monat ohne Monats-Fakt zieht die dienstlichen Ladekosten ab wie die Monats-Fakten (N-633): derselbe
    Betrag, dieselbe Herleitung, und der Netto-Ertrag ist um ihn kleiner als ohne den Posten."""
    import backend.api.routes.aktueller_monat as amr
    from backend.api.routes.aktueller_monat import finanzen
    from backend.services.monats_fakten import lade_monats_fakten

    async with kg.datenstand("achsen", "M09", "HA") as ds:
        with am.umgebung(am.MATRIX_FORMEN["M09"], ds.svc):
            fk = (await lade_monats_fakten(ds.db, ds.aid, von=(2026, 7), bis=(2026, 7), inkl_nur_tageswerte=True))[0]
            r = await amr.get_aktueller_monat(anlage_id=ds.aid, jahr=2026, monat=7, db=ds.db)
            soll = round(fk.emob.dienstliche_ladekosten_euro, 2)
            # 3,0 kWh PV × 30 ct (Netzbezugspreis) + 3,0 kWh Netz × 30 ct (Wallbox-Preis) = 1,80 €
            assert soll == 1.8 and r.dienstliche_ladekosten_euro == soll, (r.dienstliche_ladekosten_euro, soll)
            assert r.dienstliche_ladekosten_berechnung and "kWh PV" in r.dienstliche_ladekosten_berechnung
            with patch.object(finanzen, "dienstliche_ladung_ohne_fakt", new=lambda **k: _keine()), \
                    patch.object(amr, "dienstliche_ladung_ohne_fakt", new=lambda **k: _keine()):
                ohne = await amr.get_aktueller_monat(anlage_id=ds.aid, jahr=2026, monat=7, db=ds.db)
        assert round(ohne.netto_ertrag_euro - r.netto_ertrag_euro, 2) == soll
        assert ohne.dienstliche_ladekosten_euro == 0.0
