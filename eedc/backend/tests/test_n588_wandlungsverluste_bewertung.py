"""N-588 — Wandlungsverluste in Geld, USt und CO₂ nicht bewerten (Messpunkt-Vertrag), Vorlage Fassung 2, 10.10.2026.

Proben der Schicht unterhalb der Abnahme-Matrix (die Matrix misst die Sichten: `test_pv_achse_matrix.py`, Zellen
`geld:*`, `checker:messpunkt` der Formen F13a/F13b/F15/W2-V/W2-D/W2-B/W2-B7):

* die Primitive `eigenverbrauch_ohne_verluste_kwh` und der Vertrag `wandlungsverluste_grund` (iii)–(v) samt der
  Untergrenze am Klemmtag (W1) und ohne Grund „Teil-Deckung" (Entscheid Master 10.10.2026);
* das Finanz-Aggregat zieht nur am `ev`-Posten ab, der BKW-Rest bleibt (Sprengsatz (3) der Vorlage);
* der DC-Grund des Kanal-Lesers (gepflegt / angenommen / AC);
* die Daten-Checker-Kategorie „Messpunkt" (F5) Regel für Regel, (d) Volleinspeisung inklusive;
* die USt folgt dem bereinigten Eigenverbrauch in Monat, Übersicht, Tabelle und ROI (Sprengsatz (4), F4).
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from backend.core.berechnungen import FinanzMonatsZeile, berechne_finanz_aggregat
from backend.core.berechnungen.pv_verteilung import (
    VERLUSTE_GRUENDE,
    PvTraeger,
    PvZeitraum,
    eigenverbrauch_ohne_verluste_kwh,
    loese_pv_zeitraum_auf,
    verluste_grund_zeitraum,
    wandlungsverluste_grund,
)

# ── Primitive und Vertrag ─────────────────────────────────────────────────────


def test_primitive_zieht_die_verluste_unter_dem_vertrag_ab():
    assert eigenverbrauch_ohne_verluste_kwh(450.0, 36.0, None) == pytest.approx(414.0)


@pytest.mark.parametrize("verluste, grund", [(None, None), (0.0, None), (36.0, "dc_speicher"),
                                             (36.0, "ueber_schwelle"), (36.0, "bkw_ausserhalb")])
def test_primitive_ohne_vertrag_ist_bitgleich(verluste, grund):
    ev = 450.123456789
    assert eigenverbrauch_ohne_verluste_kwh(ev, verluste, grund) is ev


def test_primitive_klemmt_bei_null():
    assert eigenverbrauch_ohne_verluste_kwh(10.0, 36.0, None) == 0.0


def test_vertrag_gruende_reihenfolge_und_kein_teil_deckungs_grund():
    assert VERLUSTE_GRUENDE == ("dc_speicher", "dc_speicher_angenommen", "ueber_schwelle", "bkw_ausserhalb")
    # F13a: 36 von 630 (5,7 %), BKW 90 ⇒ bewertet
    assert wandlungsverluste_grund(verluste_kwh=36.0, strings_kwh=630.0, bkw_kwh=90.0) is None
    # (iii) vor allem anderen
    assert wandlungsverluste_grund(verluste_kwh=200.0, strings_kwh=630.0, bkw_kwh=10.0,
                                   dc_grund="dc_speicher_angenommen") == "dc_speicher_angenommen"
    # (iv) 17,7 % (W2-B) — vor (v), obwohl auch (v) erfüllt wäre
    assert wandlungsverluste_grund(verluste_kwh=111.6, strings_kwh=630.0, bkw_kwh=90.0) == "ueber_schwelle"
    # (v) Vorlage F5 (a'): 15 kWp + 600 Wp — 1 500 + 65 kWh, Anlagenzähler 0,97 × 1 500 ⇒ 110 kWh = 7,0 %
    assert wandlungsverluste_grund(verluste_kwh=110.0, strings_kwh=1565.0, bkw_kwh=65.0) == "bkw_ausserhalb"
    # ohne Verluste kein Grund
    assert wandlungsverluste_grund(verluste_kwh=0.0, strings_kwh=630.0, dc_grund="dc_speicher") is None


def test_klemmtag_des_volleinspeisers_wird_bewertet_untergrenze():
    """W2-V am Schattentag: Süd 12,6 gemessen, West ohne Zähler, Anlagenzähler 12,096 ⇒ West bekommt 0, Verluste
    0,504 — eine Untergrenze der echten Verluste, also bewertet (Entscheid W1). Am Sonnentag Rest > 0 ⇒ Verluste 0."""
    t = [PvTraeger(1, "pv-module", 6.0), PvTraeger(2, "pv-module", 4.0)]
    schatten = loese_pv_zeitraum_auf(traeger=t, eigen={1: 12.6}, anlagenzaehler_kwh=12.096)
    assert schatten.wandlungsverluste_kwh == pytest.approx(0.504)
    assert schatten.verluste_grund is None and schatten.verteilter_rest_kwh == 0.0
    assert eigenverbrauch_ohne_verluste_kwh(0.504, schatten.wandlungsverluste_kwh, None) == pytest.approx(0.0)
    sonne = loese_pv_zeitraum_auf(traeger=t, eigen={1: 12.6}, anlagenzaehler_kwh=17.28)
    assert sonne.wandlungsverluste_kwh == pytest.approx(0.0) and sonne.verteilter_rest_kwh > 0


def test_grund_des_zeitraums_ist_der_mit_den_meisten_nicht_bewerteten_verlusten():
    assert verluste_grund_zeitraum([(36.0, None), (10.0, None)]) is None
    assert verluste_grund_zeitraum([(5.0, "ueber_schwelle"), (20.0, "dc_speicher"), (36.0, None)]) == "dc_speicher"
    assert verluste_grund_zeitraum([(None, None), (0.0, "dc_speicher")]) is None


# ── Finanz-Aggregat: nur der `ev`-Posten (Vorlage Sprengsatz (3)) ─────────────


def test_finanz_aggregat_zieht_nur_am_ev_posten_ab():
    """`FinanzMonatsZeile(bkw_eigenverbrauch_kwh=50, wandlungsverluste_kwh=10, Preis 30)`: der BKW-Rest bleibt
    15,00 € (eine AC-Messung am Gerät, kein String), der `ev`-Posten sinkt um 10 × 30 ct = 3,00 €."""
    basis = dict(pv_erzeugung_kwh=630.0, einspeisung_kwh=180.0, bkw_eigenverbrauch_kwh=50.0, netzbezug_preis_cent=30.0)
    ohne = berechne_finanz_aggregat([FinanzMonatsZeile(**basis)])
    mit = berechne_finanz_aggregat([FinanzMonatsZeile(**basis, wandlungsverluste_kwh=10.0)])
    assert mit.bkw_ersparnis_euro == pytest.approx(15.0) == ohne.bkw_ersparnis_euro
    assert ohne.ev_ersparnis_euro - mit.ev_ersparnis_euro == pytest.approx(3.0)
    assert mit.eigenverbrauch_kwh == ohne.eigenverbrauch_kwh == pytest.approx(450.0)    # F2: Bilanz bleibt
    assert mit.eigenverbrauch_ohne_verluste_kwh == pytest.approx(440.0)
    assert mit.wandlungsverluste_kwh == pytest.approx(10.0)
    # Vertrag fällt ⇒ bitgleich
    dc = berechne_finanz_aggregat([FinanzMonatsZeile(**basis, wandlungsverluste_kwh=10.0, verluste_grund="dc_speicher")])
    assert dc.ev_ersparnis_euro == ohne.ev_ersparnis_euro and dc.wandlungsverluste_kwh == 0.0


# ── DC-Grund des Kanal-Lesers (Vertrag (iii)) ────────────────────────────────


def _speicher(parameter=None, parent=None, aktiv=True):
    return SimpleNamespace(typ="speicher", parameter=parameter or {}, parent_investition_id=parent, _aktiv=aktiv)


@pytest.mark.parametrize("speicher, soll", [
    (_speicher({"kopplung": "dc"}), "dc_speicher"),
    (_speicher({}, parent=7), "dc_speicher_angenommen"),
    (_speicher({"kopplung": ""}, parent=7), "dc_speicher_angenommen"),
    (_speicher({"kopplung": "ac"}, parent=7), None),
    (_speicher({}), None),
    (_speicher({"kopplung": "dc"}, aktiv=False), None),
])
def test_dc_grund_des_kanal_lesers(speicher, soll):
    from backend.services.kanal.bilanz_leser import _dc_grund

    assert _dc_grund([speicher, SimpleNamespace(typ="pv-module", parameter={})], lambda i: i._aktiv
                     if hasattr(i, "_aktiv") else True) == soll


# ── Daten-Checker „Messpunkt" (F5) Regel für Regel ───────────────────────────


def _monat(*, strings, az, bkw=0.0, rest=0.0, dc=None, einsp=None, fehlt=frozenset()):
    verluste = None if az is None else max(0.0, strings - az)
    grund = wandlungsverluste_grund(verluste_kwh=verluste, strings_kwh=strings, bkw_kwh=bkw, dc_grund=dc)
    pv = PvZeitraum({}, frozenset(), fehlt, strings, strings, verluste, grund, az, bkw, rest, dc)
    bilanz = SimpleNamespace(einspeisung_kwh=einsp or 0.0, einspeisung_erfasst=einsp is not None)
    return SimpleNamespace(pv=pv, bilanz=bilanz)


async def _messpunkt(monkeypatch, monate: dict, *, anlagenzaehler: bool = True) -> list[str]:
    from datetime import datetime

    from backend.services.daten_checker import DatenChecker
    from backend.services.kanal import bilanz_leser
    from backend.tests.pv_achse_matrix import MESSPUNKT_REGELN

    async def _kompositionen(_db, _aid, *, bis, jetzt=None):
        return {m: k for m, k in monate.items() if m <= bis}

    async def _hat(_db, _aid):
        return anlagenzaehler

    monkeypatch.setattr(bilanz_leser, "kanal_kompositionen", _kompositionen)
    monkeypatch.setattr(bilanz_leser, "hat_anlagenzaehler_kanal", _hat)
    monkeypatch.setattr(bilanz_leser, "uhr", lambda: int(datetime(2026, 7, 4).timestamp()))
    erg = await DatenChecker(None)._check_messpunkt(SimpleNamespace(id=1))
    return sorted(k for e in erg for k, anfang in MESSPUNKT_REGELN if e.meldung.startswith(anfang))


async def test_checker_ohne_befund_bei_bewerteten_verlusten(monkeypatch):
    assert await _messpunkt(monkeypatch, {(2026, 6): _monat(strings=630, az=594, bkw=90)}) == []


async def test_checker_a_und_a_strich(monkeypatch):
    assert await _messpunkt(monkeypatch, {(2026, 6): _monat(strings=630, az=518.4, bkw=90)}) == ["a", "a'"]
    assert await _messpunkt(monkeypatch, {(2026, 6): _monat(strings=1565, az=1455, bkw=65)}) == ["a'"]


async def test_checker_b_nur_ohne_dc_speicher(monkeypatch):
    """F13b meldet (b); mit DC-Speicher (gepflegt oder angenommen) nicht — Demo-Anlage 10–12/2014 (+5,3 %):
    die Netzladung der Batterie läuft durch den Wechselrichter (Entscheid Master 10.10.2026)."""
    assert await _messpunkt(monkeypatch, {(2026, 6): _monat(strings=630, az=666)}) == ["b"]
    for dc in ("dc_speicher", "dc_speicher_angenommen"):
        assert await _messpunkt(monkeypatch, {(2026, 6): _monat(strings=630, az=663.4, dc=dc)}) == []


async def test_checker_c_strich_nennt_den_kopplungs_handgriff_nur_bei_angenommener_kopplung(monkeypatch):
    from datetime import datetime

    from backend.services.daten_checker import DatenChecker
    from backend.services.kanal import bilanz_leser

    for dc, handgriff in (("dc_speicher_angenommen", True), ("dc_speicher", False)):
        monate = {(2026, 6): _monat(strings=630, az=594, dc=dc)}

        async def _k(_db, _aid, *, bis, jetzt=None, monate=monate):
            return monate

        async def _hat(_db, _aid):
            return True

        monkeypatch.setattr(bilanz_leser, "kanal_kompositionen", _k)
        monkeypatch.setattr(bilanz_leser, "hat_anlagenzaehler_kanal", _hat)
        monkeypatch.setattr(bilanz_leser, "uhr", lambda: int(datetime(2026, 7, 4).timestamp()))
        erg = await DatenChecker(None)._check_messpunkt(SimpleNamespace(id=1))
        assert len(erg) == 1 and erg[0].meldung.startswith("Bei DC-gekoppeltem Speicher")
        assert ("trage die Kopplung am Speicher" in erg[0].details) is handgriff


async def test_checker_d_volleinspeisung_ohne_anlagenzaehler(monkeypatch):
    voll = {(2026, m): _monat(strings=600, az=None, einsp=576) for m in (4, 5, 6)}
    assert await _messpunkt(monkeypatch, voll, anlagenzaehler=False) == ["d"]
    # mit Anlagenzähler-Kanal kein Hinweis (dann kennt eedc die Verluste)
    assert await _messpunkt(monkeypatch, voll, anlagenzaehler=True) == []
    # nur zwei Monate, oder einer mit echtem Eigenverbrauch ⇒ kein Hinweis
    assert await _messpunkt(monkeypatch, {m: k for m, k in voll.items() if m[1] > 4}, anlagenzaehler=False) == []
    gemischt = dict(voll)
    gemischt[(2026, 5)] = _monat(strings=600, az=None, einsp=400)
    assert await _messpunkt(monkeypatch, gemischt, anlagenzaehler=False) == []


async def test_checker_d_text_nennt_den_ac_ertragszaehler(monkeypatch):
    from datetime import datetime

    from backend.services.daten_checker import DatenChecker
    from backend.services.kanal import bilanz_leser

    voll = {(2026, m): _monat(strings=600, az=None, einsp=576) for m in (4, 5, 6)}

    async def _k(_db, _aid, *, bis, jetzt=None):
        return voll

    async def _hat(_db, _aid):
        return False

    monkeypatch.setattr(bilanz_leser, "kanal_kompositionen", _k)
    monkeypatch.setattr(bilanz_leser, "hat_anlagenzaehler_kanal", _hat)
    monkeypatch.setattr(bilanz_leser, "uhr", lambda: int(datetime(2026, 7, 4).timestamp()))
    erg = await DatenChecker(None)._check_messpunkt(SimpleNamespace(id=1))
    assert "AC-Ertragszähler deines Wechselrichters (Gesamtertrag nach dem Wechselrichter)" in erg[0].details
    assert "dann kennt eedc die Wandlungsverluste" in erg[0].details


# ── USt folgt dem bereinigten Eigenverbrauch (F4, Vorlage Sprengsatz (4)) ─────


async def test_ust_rechnet_auf_dem_eigenverbrauch_ohne_wandlungsverluste():
    """F13a nach „Aus HA laden", Regelbesteuerung: Monat, Übersicht und Tabelle nennen die USt auf 414 kWh (450 − 36),
    nicht auf 450 — und der ROI rechnet seine Jahres-USt auf der hochgerechneten bereinigten Menge (3 888 statt 4 320)."""
    from sqlalchemy import select

    from backend.api.routes.cockpit.uebersicht import get_cockpit_uebersicht
    from backend.api.routes.investitionen.roi import get_roi_dashboard
    from backend.api.routes.monatsdaten import list_monatsdaten_aggregiert
    from backend.core.berechnungen.ust_eigenverbrauch import UstJahresanteil, berechne_ust_eigenverbrauch
    from backend.models import Anlage, Investition
    from backend.services.ust_satz import kosten_des_jahres, ust_hochrechnung
    from backend.tests import kanal_bilanz_gleichheit as kg
    from backend.tests import pv_achse_matrix as mx
    from backend.tests.test_wandlungsverluste_anzeige import _monat as monat_route

    async with kg.datenstand("pv", "F13a", "HA") as ds:
        with mx._umgebung(ds.svc):
            await mx.schreibe_s1_aus_ha_laden(ds.db, ds.aid)
            roi_ohne = await get_roi_dashboard(anlage_id=ds.aid, strompreis_cent=None, einspeiseverguetung_cent=None,
                                               benzinpreis_euro=None, jahr=2026, db=ds.db)
            anlage = (await ds.db.execute(select(Anlage).where(Anlage.id == ds.aid))).scalar_one()
            anlage.steuerliche_behandlung = "regelbesteuerung"
            anlage.ust_satz_prozent = 19.0
            await ds.db.commit()
            invs = list((await ds.db.execute(select(Investition).where(Investition.anlage_id == ds.aid))).scalars())
            monat = await monat_route(ds.db, ds.aid, (2026, 6))
            uebersicht = await get_cockpit_uebersicht(anlage_id=ds.aid, jahr=2026, db=ds.db)
            zeile = next(z for z in await list_monatsdaten_aggregiert(
                anlage_id=ds.aid, jahr=2026, inkl_ohne_zaehlerzeile=False, inkl_nur_tageswerte=False, db=ds.db)
                if z.monat == 6)
            roi_mit = await get_roi_dashboard(anlage_id=ds.aid, strompreis_cent=None, einspeiseverguetung_cent=None,
                                              benzinpreis_euro=None, jahr=2026, db=ds.db)

    bemessung, bk = kosten_des_jahres(invs, 2026)

    def ust(ev):
        return berechne_ust_eigenverbrauch([UstJahresanteil(jahr=2026, eigenverbrauch_kwh=ev, pv_kwh=630.0, monate=1)],
                                           bemessungsgrundlage_euro=bemessung, betriebskosten_jahr_euro=bk,
                                           ust_satz_prozent=19.0)

    soll, alt = ust(414.0), ust(450.0)
    assert soll > 0 and round(soll, 2) != round(alt, 2)
    assert monat.ust_eigenverbrauch_euro == pytest.approx(soll, abs=0.01)
    assert uebersicht.ust_eigenverbrauch_euro == pytest.approx(soll, abs=0.01)
    assert zeile.ust_eigenverbrauch_euro == pytest.approx(soll, abs=0.01)
    pv = next(b for b in roi_ohne.berechnungen if b.investition_typ == "pv-module").detail_berechnung
    assert pv["eigenverbrauch_ohne_verluste_kwh_jahr"] == pytest.approx(3888.0)
    soll_roi = ust_hochrechnung(anlage, invs, 2026, pv["eigenverbrauch_ohne_verluste_kwh_jahr"], pv["erzeugung_kwh_jahr"])
    assert roi_ohne.gesamt_jahres_einsparung - roi_mit.gesamt_jahres_einsparung == pytest.approx(soll_roi, abs=0.02)
