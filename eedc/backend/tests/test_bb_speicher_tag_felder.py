"""Päckchen BB (9.11.2026): Speicher-Bilanz, Wirkungsverluste, Solar-Anteil, Hub-Kacheln, Jahresbilanz und die
SOLL-Erreichung des Tages kommen als Felder aus dem Backend (Z-Client-Halte H1/H3). Nachlauf (Entscheid Master):
BB2/N-783 die Ladung des Tages (Zählerpfad vor Leistungspfad, privat) samt PV-Anteil, BB4 die Laufzeit-Felder der
PV-Strings («alle Jahre»).

Je Feld: (a) die Layer-Funktion (``core/berechnungen/speicher_bilanz.py``) trifft die alte Client-Formel **bitgleich**
(dieselbe Gleitkomma-Reihenfolge, dieselben ``null``-Regeln) und (b) das Antwortmodell bzw. die Route trägt sie. Die
Gleichheit auf den Demo-Kopien (r28, r27, pruef-4018: 0 Abweichungen) steht im Bericht
``opus-berichte/PAECKCHEN-BB-2026-11-09.md``.
"""
from __future__ import annotations

import random

import pytest

from backend.api.routes.aktueller_monat.schemas import AktuellerMonatResponse
from backend.api.routes.investitionen.dashboard_speicher import (
    SpeicherMonatsWert, _hub_kacheln, _jahresbilanz,
)
from backend.core.berechnungen.ergebnis import quote
from backend.core.berechnungen.speicher_bilanz import (
    speicher_bilanz_kwh, speicher_pv_ladung_kwh, speicher_solaranteil_prozent, speicher_verlust_kwh,
    speicher_wirkungsverluste,
)


# ── Die alten Client-Formeln, wörtlich (HEAD 7194a97bb; JS-Semantik `x ?? 0`, `Math.min`, links nach rechts) ──
def _client_wirkungsverluste(lad, ent, netz, eins, bez_durchschnitt, bez_tarif):
    """``KomponentenSektionen.tsx::speicherWirkungsverluste``."""
    if lad is None or ent is None or lad <= ent:
        return None
    if eins is None and bez_tarif is None:
        return None
    verlust = lad - ent
    netz_kwh = netz if netz is not None else 0
    roh = netz_kwh / lad if lad > 0 else 0
    anteil_netz = min(1, roh)
    anteil_pv = 1 - anteil_netz
    eins_p = eins if eins is not None else 0
    bez_p = bez_durchschnitt if bez_durchschnitt is not None else (bez_tarif if bez_tarif is not None else 0)
    return ((verlust * anteil_pv * eins_p) / 100 + (verlust * anteil_netz * bez_p) / 100,
            verlust * anteil_pv, verlust * anteil_netz, roh > 1)


def _client_solar(ladung, netz):
    """``JahrSpeicherTabelle.tsx::solarAnteil`` (Zeile: Ladung ``?? 0``)."""
    if netz is None or ladung <= 0:
        return None
    return max(0, (ladung - netz)) / ladung * 100


def _zahl(rng):
    return rng.choice([None, 0, 0.0, round(rng.uniform(0, 500), rng.choice([1, 2, 3])), rng.uniform(0, 50),
                       -round(rng.uniform(0, 5), 2)])


@pytest.mark.parametrize("saat", range(5))
def test_layer_bitgleich_zur_alten_client_formel(saat):
    rng = random.Random(saat)
    for _ in range(4000):
        lad, ent, netz, eins, bez_d, bez_t = (_zahl(rng) for _ in range(6))
        wv = speicher_wirkungsverluste(lad, ent, netz, eins, bez_d if bez_d is not None else bez_t,
                                       ein_preis_bekannt=eins is not None or bez_t is not None)
        alt = _client_wirkungsverluste(lad, ent, netz, eins, bez_d, bez_t)
        assert (None if wv is None else (wv.euro, wv.verlust_pv_kwh, wv.verlust_netz_kwh, wv.gekappt)) == alt
        # Bilanz (KS:722): Entladung − Ladung, nur mit beiden Mengen.
        assert speicher_bilanz_kwh(lad, ent) == (ent - lad if lad is not None and ent is not None else None)
        # Hub (komponentenAdapter): Verlust ungeklemmt, PV-Ladung = Ladung − (Netz ?? 0).
        if lad is not None and ent is not None:
            assert speicher_verlust_kwh(lad, ent) == lad - ent
            assert speicher_verlust_kwh(lad, ent, nur_positiv=True) == max(0, lad - ent)
        if lad is not None:
            assert speicher_pv_ladung_kwh(lad, netz) == lad - (netz if netz is not None else 0)
            assert speicher_solaranteil_prozent(lad, netz) == _client_solar(lad, netz)
        # SOLL-Erreichung des Tages (TagBilanz:96): nur mit SOLL > 0 und Erzeugung.
        erwartet = (lad / ent) * 100 if lad is not None and ent is not None and ent > 0 else None
        assert quote(lad, ent, nur_positiver_nenner=True) == erwartet


def test_wirkungsverluste_kappen_und_sagen_es():
    # N-444/K2: Netzladung (brutto) größer als die Netto-Ladung ⇒ Netz-Anteil 1, gekappt, PV-Teil 0.
    wv = speicher_wirkungsverluste(10.0, 8.0, 12.0, 8.0, 30.0, ein_preis_bekannt=True)
    assert wv.gekappt is True and wv.anteil_netz == 1.0 and wv.verlust_pv_kwh == 0.0
    assert wv.euro == (2.0 * 1.0 * 30.0) / 100
    # Kein Verlust, kein Preis ⇒ keine Zeile.
    assert speicher_wirkungsverluste(8.0, 10.0, 0.0, 8.0, 30.0, ein_preis_bekannt=True) is None
    assert speicher_wirkungsverluste(10.0, 8.0, 0.0, None, None, ein_preis_bekannt=False) is None


def _monat(**werte):
    return AktuellerMonatResponse(anlage_id=1, anlage_name="A", jahr=2026, monat=6, monat_name="Juni",
                                  aktualisiert_um="2026-06-30T12:00:00", quellen={}, **werte)


def test_monat_traegt_die_speicher_felder_aus_seinen_feldern():
    m = _monat(speicher_ladung_kwh=100.0, speicher_entladung_kwh=90.0, speicher_ladung_netz_kwh=25.0,
               einspeise_preis_cent=8.0, netzbezug_preis_cent=30.0, netzbezug_durchschnittspreis_cent=28.0).model_dump()
    alt = _client_wirkungsverluste(100.0, 90.0, 25.0, 8.0, 28.0, 30.0)
    assert (m["speicher_wirkungsverluste_euro"], m["speicher_verlust_pv_kwh"], m["speicher_verlust_netz_kwh"],
            m["speicher_netzladung_anteil_gekappt"]) == alt
    assert m["speicher_bilanz_kwh"] == -10.0
    assert m["speicher_verlust_kwh"] == 10.0
    assert m["speicher_netzladung_anteil_prozent"] == 25.0
    assert m["speicher_solaranteil_prozent"] == 75.0
    leer = _monat().model_dump()
    assert all(leer[k] is None for k in (
        "speicher_bilanz_kwh", "speicher_verlust_kwh", "speicher_wirkungsverluste_euro", "speicher_solaranteil_prozent"))


def test_monat_ohne_netzladung_kein_solaranteil_und_tarif_als_preisfrage():
    # Ohne Einspeise- und Tarif-Bezugspreis keine Wirkungsverluste — auch wenn ein Ø-Bezugspreis da ist (Client-Regel).
    m = _monat(speicher_ladung_kwh=100.0, speicher_entladung_kwh=90.0, netzbezug_durchschnittspreis_cent=28.0)
    assert m.speicher_wirkungsverluste_euro is None
    assert m.speicher_solaranteil_prozent is None


def test_hub_kacheln_aus_den_gerundeten_feldern():
    z = {"gesamt_ladung_kwh": 1234.5, "gesamt_entladung_kwh": 1100.1, "arbitrage_kwh": 200.3,
         "arbitrage_avg_preis_cent": 15.2, "effektiver_ladepreis_cent": None}
    _hub_kacheln(z)
    assert z["verlust_kwh"] == 1234.5 - 1100.1
    assert z["pv_ladung_kwh"] == 1234.5 - 200.3
    # `effektiver_ladepreis_cent ?? arbitrage_avg_preis_cent` wie der Client.
    assert z["netzladung_kosten_euro"] == (200.3 * 15.2) / 100
    z2 = {"gesamt_ladung_kwh": 10.0, "gesamt_entladung_kwh": 12.0, "arbitrage_kwh": 0.0,
          "arbitrage_avg_preis_cent": None, "effektiver_ladepreis_cent": 9.87}
    _hub_kacheln(z2)
    assert z2["verlust_kwh"] == -2.0  # ungeklemmt, wie die Kachel (Durchsatz-Hinweis daneben)
    assert z2["netzladung_kosten_euro"] == 0.0
    z3 = {"gesamt_ladung_kwh": 10.0, "gesamt_entladung_kwh": 8.0, "arbitrage_kwh": 3.0, "arbitrage_avg_preis_cent": None}
    _hub_kacheln(z3)
    assert z3["netzladung_kosten_euro"] is None


def test_jahresbilanz_summiert_die_reihe_je_jahr():
    reihe = [
        SpeicherMonatsWert(jahr=2025, monat=1, ladung_kwh=100, entladung_kwh=80, netzladung_kwh=30, pv_ladung_kwh=70,
                           vollzyklen=None),
        SpeicherMonatsWert(jahr=2025, monat=2, ladung_kwh=100, entladung_kwh=90, netzladung_kwh=0, pv_ladung_kwh=100,
                           vollzyklen=None),
        SpeicherMonatsWert(jahr=2024, monat=12, ladung_kwh=50, entladung_kwh=80, netzladung_kwh=10, pv_ladung_kwh=40,
                           vollzyklen=None),
    ]
    jb = _jahresbilanz(reihe)
    assert [j.jahr for j in jb] == [2024, 2025]
    assert jb[0].verlust_kwh == 0.0  # nie negativ (SoC-Übertrag)
    j = jb[1]
    assert (j.ladung_gesamt_kwh, j.netzladung_kwh, j.pv_ladung_kwh, j.entladung_kwh, j.verlust_kwh) == (
        200, 30, 170, 170, 30)
    # Bilanz-Invariante der Säulen: Ladung = Entladung + Verlust.
    assert j.pv_ladung_kwh + j.netzladung_kwh == j.entladung_kwh + j.verlust_kwh


# ═══ Nachlauf BB2 (N-783): Ladung des Tages — Zählerpfad vor Leistungspfad, privat (Entscheid Master Option A) ═══

from datetime import date as _date  # noqa: E402
from types import SimpleNamespace  # noqa: E402

from sqlalchemy import select  # noqa: E402

from backend.models.investition import Investition  # noqa: E402
from backend.models.tages_energie_profil import TagesEnergieProfil, TagesZusammenfassung  # noqa: E402
from backend.tests import factories  # noqa: E402

TAG = _date(2026, 8, 6)


async def _emob_anlage(db, *, wallbox_dienstlich: bool = False):
    a = await factories.anlage(db, anlagenname="BB2", sensor_mapping={})
    wb = await factories.investition(db, a.id, "wallbox", bezeichnung="WB", anschaffungsdatum=_date(2024, 1, 1),
                                     parameter={"ist_dienstlich": True} if wallbox_dienstlich else {})
    auto = await factories.investition(db, a.id, "e-auto", bezeichnung="Auto", anschaffungsdatum=_date(2024, 1, 1))
    await db.commit()
    return a, wb, auto


async def _stunden(db, anlage_id: int, werte: dict[int, dict]) -> None:
    for stunde, komp in werte.items():
        db.add(TagesEnergieProfil(anlage_id=anlage_id, datum=TAG, stunde=stunde, komponenten=komp))
    await db.commit()


async def _emob_tag(db, a) -> dict:
    from backend.api.routes.energie_profil.tag import _emob_ladung_tag

    invs = {str(i.id): i for i in (await db.execute(
        select(Investition).where(Investition.anlage_id == a.id))).scalars().all()}
    ctx = SimpleNamespace(db=db, anlage=a, investitionen_by_id=invs, datum=TAG, emob_felder={})
    await _emob_ladung_tag(ctx)
    return ctx.emob_felder


async def test_bb2_zaehlerpfad_tag_ohne_stunden_serie(db):
    """Der Fall der Produktiv-Box (6.8.2026): Tageswert ja, Stunden-Serie nein ⇒ die Ladung steht (vorher kein Block)."""
    a, wb, _auto = await _emob_anlage(db)
    db.add(TagesZusammenfassung(anlage_id=a.id, datum=TAG, komponenten_kwh={f"wallbox_{wb.id}": -11.81}))
    await db.commit()
    f = await _emob_tag(db, a)
    assert (f["emob_ladung_kwh"], f["emob_ladung_quelle"]) == (11.81, "zaehler")


async def test_bb2_beide_pfade_der_zaehler_gewinnt(db):
    a, wb, _auto = await _emob_anlage(db)
    db.add(TagesZusammenfassung(anlage_id=a.id, datum=TAG, komponenten_kwh={f"wallbox_{wb.id}": 11.81}))
    await db.commit()
    await _stunden(db, a.id, {10: {f"wallbox_{wb.id}": -2.0}, 11: {f"wallbox_{wb.id}": -3.0}})
    f = await _emob_tag(db, a)
    assert (f["emob_ladung_kwh"], f["emob_ladung_quelle"]) == (11.81, "zaehler")


async def test_bb2_leistungspfad_rueckfall_wie_die_alte_client_summe_ohne_eauto_neben_wallbox(db):
    """Ohne Tageswert die Stunden (Σ je Serie, davon der Betrag); die E-Auto-Serie neben der Wallbox-Serie zählt
    nicht (N-555, ``emob_auto_verdraengt`` — Bestandsstunden können beide tragen)."""
    a, wb, auto = await _emob_anlage(db)
    await _stunden(db, a.id, {10: {f"wallbox_{wb.id}": -3.0, f"eauto_{auto.id}": -3.1},
                              11: {f"wallbox_{wb.id}": -2.5, f"eauto_{auto.id}": -2.4}})
    f = await _emob_tag(db, a)
    assert (f["emob_ladung_kwh"], f["emob_ladung_quelle"]) == (abs(0 + -3.0 + -2.5), "leistung")


async def test_bb2_eauto_serie_ohne_wallbox_serie_zaehlt(db):
    a, _wb, auto = await _emob_anlage(db)
    await _stunden(db, a.id, {10: {f"eauto_{auto.id}": -4.0}})
    f = await _emob_tag(db, a)
    assert (f["emob_ladung_kwh"], f["emob_ladung_quelle"]) == (4.0, "leistung")


async def test_bb2_dienstliche_wallbox_zaehlt_nicht(db):
    """Gerätemenge privat wie *Cockpit → Monat* (Heimladung) — der Dienstwagen-Lader steht nicht im Block."""
    a, wb, _auto = await _emob_anlage(db, wallbox_dienstlich=True)
    db.add(TagesZusammenfassung(anlage_id=a.id, datum=TAG, komponenten_kwh={f"wallbox_{wb.id}": 11.81}))
    await db.commit()
    await _stunden(db, a.id, {10: {f"wallbox_{wb.id}": -2.0}})
    f = await _emob_tag(db, a)
    assert (f["emob_ladung_kwh"], f["emob_ladung_quelle"]) == (None, None)


async def test_bb2_ohne_ladung_kein_wert(db):
    """Ein Tag mit Schlüssel, aber ohne Ladung (0) trägt keine Zahl — der Block erscheint nicht (wie bisher ``pos()``)."""
    a, wb, _auto = await _emob_anlage(db)
    db.add(TagesZusammenfassung(anlage_id=a.id, datum=TAG, komponenten_kwh={f"wallbox_{wb.id}": 0.0}))
    await db.commit()
    f = await _emob_tag(db, a)
    assert (f["emob_ladung_kwh"], f["emob_ladung_quelle"], f["emob_km"]) == (None, None, None)


def _client_pv_anteil(pv, ladung):
    """``KomponentenSektionen.tsx`` bis BB2: ``hat(pv) && ladung ? (pv / ladung) * 100 : null``."""
    return (pv / ladung) * 100 if pv is not None and ladung else None


@pytest.mark.parametrize("saat", range(3))
def test_bb2_pv_anteil_feld_bitgleich_zur_alten_client_formel(saat):
    from backend.api.routes.energie_profil._shared import TagDetailResponse

    rng = random.Random(100 + saat)
    for _ in range(4000):
        pv, ladung = _zahl(rng), _zahl(rng)
        if ladung is not None and ladung < 0:
            continue  # eine negative Ladung gibt es in keiner Antwort (Betrag/Zähler); Layer: None
        erwartet = _client_pv_anteil(pv, ladung)
        assert _monat(emob_ladung_pv_kwh=pv, emob_ladung_kwh=ladung).emob_pv_anteil_prozent == erwartet
        tag = TagDetailResponse.model_construct(emob_ladung_pv_kwh=pv, emob_ladung_kwh=ladung)
        assert tag.emob_pv_anteil_prozent == erwartet


# ═══ Nachlauf BB4: PV-Strings «alle Jahre» aus der Laufzeit-Route (Entscheid Master Option B) ═══

async def test_bb4_laufzeit_traegt_monatssummen_und_abweichung_wie_die_jahressicht(db):
    """Je String: Σ der Jahres-Monatswerte (SOLL wie die Jahressicht, F-34/Monate mit IST — nicht das Saisonal-
    Mittel) und IST − SOLL; dazu der spezifische Ertrag der Jahressicht als Feld."""
    from backend.api.routes.cockpit.pv_strings import get_pv_strings, get_pv_strings_gesamtlaufzeit
    from backend.tests.test_rf31_pv_strings_modul_prognose import _seed_modulprognose

    aid = await _seed_modulprognose(db)
    lz = await get_pv_strings_gesamtlaufzeit(anlage_id=aid, db=db)
    jahre = {j: await get_pv_strings(anlage_id=aid, jahr=j, db=db) for j in (2025, 2026)}
    for s in lz.strings:
        assert s.abweichung_gesamt_kwh == round(s.ist_gesamt_kwh - s.prognose_gesamt_kwh, 1)
        for m in s.monatswerte_summe:
            je_jahr = [next(x for x in r.strings if x.investition_id == s.investition_id).monatswerte[m.monat - 1]
                       for r in jahre.values()]
            assert m.prognose_summe_kwh == pytest.approx(sum(x.prognose_kwh for x in je_jahr))
            assert m.ist_summe_kwh == pytest.approx(sum(x.ist_kwh for x in je_jahr))
        assert sum(m.prognose_summe_kwh for m in s.monatswerte_summe) == pytest.approx(s.prognose_gesamt_kwh)
    r = jahre[2025]
    assert r.spezifischer_ertrag_kwh_kwp == r.ist_gesamt_kwh / r.anlagen_leistung_kwp
