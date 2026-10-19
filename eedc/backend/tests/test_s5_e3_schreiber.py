"""Proben HA-Bauform S5, Etappe E-S5-3 (S5b Teil 1): **der Schreiber lässt die Mengen an Kanal-Tagen weg**
(Bauplan S5 §4 S5-R2, §3 (B), §10h 1–6; ``services/energie_profil/mengen_weiche.py``).

* **Weiche:** an einem Kanal-Tag (Bilanz-Gruppe mit Wahl ``kanal``) sind die TEP-Mengen der Gruppen mit Wahl ``kanal``
  leer (``None``), ``spannen`` ohne deren Achsen, TZ ``ueberschuss/defizit_kwh`` leer, ``komponenten_kwh`` ohne deren
  Schlüssel; Bahnen und die übrigen Kennzahlen bitgleich zu einem Lauf ohne Weiche (``KEINE_WEICHE`` = HEAD-Schreiber).
* **Bestandstag** (keine Kanal-Deckung) bitgleich zum Lauf ohne Weiche — Zeile für Zeile.
* **Richtung beidseitig:** am laufenden Tag mit fälliger gedeckter Stunde leer, ohne fällige Stunde wie Bestand; ein Tag,
  der seine Deckung verliert, trägt nach der nächsten Aggregation wieder Mengen.
* **Preserve:** ``MANUAL_REPAIR`` an einem Kanal-Tag holt keine alten Bilanz-Schlüssel zurück.
* **Kennzahlen** aus den Kanal-Stunden (PR, §51-Menge, Heimladungs-Anteil) = eigene Rechnung über die Mischzeilen von
  ``/stunden``; **Herkunft** ``TZ_QUELLE_KANAL`` mit Gruppen, ``tageszeile_ist_rueckwaerts`` ⇒ ``False``.
* **Invarianten** still am Kanal-Tag, am Bestandstag wie ohne Weiche.
* **Lesestelle** (§10h 6): Tagesliste/``tage-werte`` = *Cockpit → Tag* je Schlüssel an einem Kanal-Tag mit verfälschter
  Tageszeile; Überschuss/Defizit über ``ueberschuss_defizit_der_tage``; Monats-Rollup und Archiv-Nachzug.
* **Werkbank:** die Rückmeldung nennt die leer gelassenen Gruppen und meldet sie nicht als «ohne Wert».

Datenstand: ``kanal_bilanz_gleichheit.datenstand`` (Matrix-Formen, HA-Weg, Uhr der Matrix; seine Tageszeilen schreibt der Bestands-
Algorithmus — die Proben aggregieren selbst, wo sie den Schreiber wie im Produkt brauchen).

Schwesterdateien: test_s5_e2_checker_kanal_mengen.py, test_s5_e2_sichten_kanal_tage.py, test_s5_stunden_der_tage.py,
test_kanal_bestand_unberuehrt.py (Bestand bitgleich, Kanal-Tage «Mengen leer»), test_tep_mengen_leser_waechter.py.
"""

from __future__ import annotations

import logging
from contextlib import contextmanager
from datetime import date, datetime
from unittest.mock import patch

import pytest
from sqlalchemy import delete, select, text, update

from backend.models import Anlage
from backend.models.investition import Investition
from backend.models.kanal import Kanal, KanalStatistik
from backend.models.tages_energie_profil import TagesEnergieProfil, TagesZusammenfassung
from backend.services.kanal import bilanz_leser
from backend.tests import achsen_matrix as am
from backend.tests import kanal_bilanz_gleichheit as kg
from backend.tests import pv_achse_matrix as mx

TAG = date(2026, 6, 10)
BILANZ_TEP = ("pv_kw", "verbrauch_kw", "einspeisung_kw", "netzbezug_kw", "batterie_kw", "ueberschuss_kw", "defizit_kw")


@pytest.fixture
def uhr(monkeypatch):
    monkeypatch.setattr(bilanz_leser, "uhr", lambda: kg.JETZT_TS)


@contextmanager
def ohne_weiche():
    """Der Schreiber wie bis E-S5-2 (HEAD): die Weiche ohne Wirkung."""
    from backend.services.energie_profil import aggregator, mengen_weiche

    async def _keine(*_a, **_k):
        return mengen_weiche.KEINE_WEICHE

    with patch.object(aggregator, "mengen_weiche", _keine):
        yield


async def _zeilen(ds, tabelle: str, tag: date) -> list[dict]:
    spalten = [r[1] for r in (await ds.db.execute(text(f"PRAGMA table_info({tabelle})"))).all()
               if r[1] not in ("id", "created_at", "updated_at")]
    rows = (await ds.db.execute(text(f"SELECT {', '.join(spalten)} FROM {tabelle} WHERE anlage_id = :a AND datum = :d "
                                     "ORDER BY 1"), {"a": ds.aid, "d": tag.isoformat()})).all()
    return [dict(zip(spalten, r)) for r in rows]


def _ohne_at(prov):
    import json

    if prov is None:
        return None
    p = json.loads(prov) if isinstance(prov, str) else prov
    return {k: {kk: vv for kk, vv in v.items() if kk != "at"} if isinstance(v, dict) else v for k, v in p.items()}


async def _stand(ds, tag: date = TAG) -> dict:
    tep = await _zeilen(ds, "tages_energie_profil", tag)
    tz = await _zeilen(ds, "tages_zusammenfassung", tag)
    for z in tep + tz:
        z["source_provenance"] = _ohne_at(z["source_provenance"])
    return {"tep": tep, "tz": tz}


async def _aggregieren(ds, tage=(TAG,), *, source=None):
    """``aggregate_day`` in der Umgebung des Datenstands; Rückgabe die Tageszeilen der Läufe (transiente Marker)."""
    from backend.services.energie_profil.aggregator import aggregate_day
    from backend.services.energie_profil.source import Source
    from backend.services.kanal import merken

    merken.invalidiere(ds.aid)
    form = am.MATRIX_FORMEN[ds.fid]
    anlage = (await ds.db.execute(select(Anlage).where(Anlage.id == ds.aid))).scalar_one()
    out = []
    with am.umgebung(form, ds.svc):
        for t in tage:
            out.append(await aggregate_day(anlage, t, ds.db, source=source or Source.SCHEDULER,
                                           prefetched_tagesverlauf=mx._kurve(form.pvform)))
            await ds.db.commit()
    return out


async def _ohne_kanalzeilen(ds) -> None:
    ids = select(Kanal.id).where(Kanal.anlage_id == ds.aid)
    await ds.db.execute(delete(KanalStatistik).where(KanalStatistik.kanal_id.in_(ids)))
    await ds.db.commit()


# ── Die Weiche am Kanal-Tag (Bilanz + WP) und am Bestandstag ────────────────────────────────────────────────────


async def test_kanal_tag_mengen_leer_bahnen_wie_ohne_weiche(uhr):
    from backend.services.snapshot.boundary_range import TZ_QUELLE_KANAL

    async with kg.datenstand("achsen", "M05", "HA") as ds:
        # Der Datenstand aggregiert vor dem Bau der abgeleiteten WP-Kanäle (E4d) — da hatte die WP-Gruppe noch Wahl
        # `bestand`; die Wahl zum Schreibzeitpunkt entscheidet (§10h 3), also einmal neu aggregieren.
        await _aggregieren(ds)
        neu = await _stand(ds)
        with ohne_weiche():
            await _aggregieren(ds)
        alt = await _stand(ds)
    assert len(neu["tep"]) == len(alt["tep"]) == 24
    gefuellt = 0
    for zn, za in zip(neu["tep"], alt["tep"]):
        assert all(zn[s] is None for s in (*BILANZ_TEP, "waermepumpe_kw")), zn
        assert not set(zn["spannen"] or {}) & {"pv", "einspeisung", "netzbezug", "batterie", "waermepumpe"}
        gefuellt += sum(za[s] is not None for s in (*BILANZ_TEP, "waermepumpe_kw"))
        weg = {*BILANZ_TEP, "waermepumpe_kw", "spannen", "source_provenance"}
        assert {k: v for k, v in zn.items() if k not in weg} == {k: v for k, v in za.items() if k not in weg}
    assert gefuellt > 0, "der Lauf ohne Weiche schrieb keine Mengen — die Probe hätte nichts verglichen"
    (tn,), (ta,) = neu["tz"], alt["tz"]
    assert tn["ueberschuss_kwh"] is None and tn["defizit_kwh"] is None and ta["ueberschuss_kwh"] is not None
    import json

    komp_neu = json.loads(tn["komponenten_kwh"] or "null") or {}
    komp_alt = json.loads(ta["komponenten_kwh"] or "null") or {}
    assert not [k for k in komp_neu if k.startswith(("pv_", "bkw_", "waermepumpe_", "batterie_"))
                or k in ("einspeisung", "netzbezug")], komp_neu
    assert any(k.startswith("waermepumpe_") for k in komp_alt)
    weg = {"ueberschuss_kwh", "defizit_kwh", "komponenten_kwh", "verworfen", "nachtrag", "performance_ratio",
           "einspeisung_neg_preis_kwh", "emob_ladung_pv_abgeleitet_kwh", "emob_ladung_netz_abgeleitet_kwh",
           "emob_ladung_speicher_abgeleitet_kwh", "source_provenance"}
    assert {k: v for k, v in tn.items() if k not in weg} == {k: v for k, v in ta.items() if k not in weg}
    assert json.loads(tn["verworfen"]) == {}                    # die Regelmarke bleibt (R9, E7)
    eintraege = [e for e in tn["source_provenance"].values() if isinstance(e, dict)]
    assert eintraege and all(e["source"] == TZ_QUELLE_KANAL and e["gruppen"] == ["bilanz", "wp"] for e in eintraege)


async def test_bestandstag_bitgleich_zum_lauf_ohne_weiche(uhr):
    async with kg.datenstand("achsen", "M05", "HA") as ds:
        await _ohne_kanalzeilen(ds)
        await _aggregieren(ds)
        neu = await _stand(ds)
        with ohne_weiche():
            await _aggregieren(ds)
        alt = await _stand(ds)
    assert neu == alt and any(z["pv_kw"] is not None for z in neu["tep"])


async def test_tag_verliert_deckung_naechste_aggregation_schreibt_mengen(uhr):
    from backend.services.snapshot.boundary_range import tageszeile_ist_rueckwaerts

    async with kg.datenstand("achsen", "M01", "HA") as ds:
        await _aggregieren(ds)
        vorher = await _stand(ds)
        await _ohne_kanalzeilen(ds)
        await _aggregieren(ds)
        nachher = await _stand(ds)
    assert all(z["pv_kw"] is None for z in vorher["tep"])
    assert any(z["pv_kw"] is not None for z in nachher["tep"]) and nachher["tz"][0]["ueberschuss_kwh"] is not None
    import json

    assert not tageszeile_ist_rueckwaerts(vorher["tz"][0]["source_provenance"], json.loads(vorher["tz"][0]["verworfen"]))
    assert tageszeile_ist_rueckwaerts(nachher["tz"][0]["source_provenance"], json.loads(nachher["tz"][0]["verworfen"]))


@pytest.mark.parametrize("stunde,gruppen", [(0, ()), (1, ()), (14, ("bilanz",))])
async def test_laufender_tag_wahl_bis_zur_faelligen_stunde(monkeypatch, stunde, gruppen):
    """Am laufenden Tag gilt die Wahl bis zur fälligen Stunde (Uhr der Lese-Schicht, ``SCHREIBVERZUG_S``): ohne fällige
    Stunde (00:30, 01:30) ist der Tag noch kein Kanal-Tag — die Weiche leert nichts, der Bestand schreibt; mit gedeckter
    fälliger Stunde (14:30) leert sie die Bilanz. Die Uhr steht nur für die Weiche (der Datenstand liest mit ihr)."""
    from backend.services.energie_profil.mengen_weiche import mengen_weiche

    async with kg.datenstand("achsen", "M01", "HA") as ds:
        anlage = (await ds.db.execute(select(Anlage).where(Anlage.id == ds.aid))).scalar_one()
        jetzt = int(datetime(TAG.year, TAG.month, TAG.day, stunde, 30).timestamp())
        monkeypatch.setattr(bilanz_leser, "uhr", lambda: jetzt)
        w = await mengen_weiche(ds.db, anlage, TAG)
    assert w.gruppen == gruppen


async def test_manual_repair_holt_am_kanal_tag_keine_bilanz_schluessel_zurueck(uhr):
    """Die Preserve-Logik (``MANUAL_REPAIR`` ohne frische Komponenten ⇒ alte ``komponenten_kwh``) verliert gegen die
    Weiche: an einem Kanal-Tag bleiben die Bilanz-Schlüssel leer, auch wenn die alte Zeile sie trug."""
    from backend.services.energie_profil import aggregator
    from backend.services.energie_profil.source import Source

    original = aggregator.komponenten_tagesgesamt_und_peaks

    async def _ohne_frische(*a, **k):
        marken = await original(*a, **k)
        a[5].komponenten_summen.clear()              # akku: kein frischer Tageswert ⇒ Preserve-Zweig
        return marken

    async with kg.datenstand("achsen", "M01", "HA") as ds:
        pv_id = (await ds.db.execute(select(Investition.id).where(
            Investition.anlage_id == ds.aid, Investition.typ == "pv-module"))).scalars().first()
        await ds.db.execute(update(TagesZusammenfassung).where(
            TagesZusammenfassung.anlage_id == ds.aid, TagesZusammenfassung.datum == TAG,
        ).values(komponenten_kwh={f"pv_{pv_id}": 30.0, "einspeisung": 9.0, "v2h_99": 1.5}))
        await ds.db.commit()
        with patch.object(aggregator, "komponenten_tagesgesamt_und_peaks", _ohne_frische):
            (z,) = await _aggregieren(ds, source=Source.MANUAL_REPAIR)
        tz = (await ds.db.execute(select(TagesZusammenfassung).where(
            TagesZusammenfassung.anlage_id == ds.aid, TagesZusammenfassung.datum == TAG))).scalar_one()
    assert z.komponenten_frisch is False
    assert tz.komponenten_kwh == {"v2h_99": 1.5}                # Bilanz-Schlüssel weg, V2H (ohne Kanal) bleibt


async def test_invarianten_still_am_kanal_tag_am_bestandstag_wie_ohne_weiche(uhr, caplog):
    muster = ("Invariante verletzt", "Komponenten-Drift", "Achse-2-Komponenten-Drift")
    async with kg.datenstand("achsen", "M05", "HA") as ds:
        with caplog.at_level(logging.WARNING, logger="backend.services.energie_profil.aggregator"):
            caplog.clear()
            await _aggregieren(ds, kg.TAGE)
            kanal = [r.getMessage() for r in caplog.records if any(m in r.getMessage() for m in muster)]
            await _ohne_kanalzeilen(ds)
            caplog.clear()
            await _aggregieren(ds, kg.TAGE)
            bestand = sorted(r.getMessage() for r in caplog.records if any(m in r.getMessage() for m in muster))
            caplog.clear()
            with ohne_weiche():
                await _aggregieren(ds, kg.TAGE)
            bestand_alt = sorted(r.getMessage() for r in caplog.records if any(m in r.getMessage() for m in muster))
    assert kanal == []
    assert bestand == bestand_alt


# ── Kennzahlen aus den Kanal-Stunden ────────────────────────────────────────────────────────────────────────────


async def _misch(ds, tag: date = TAG):
    """Die Mischzeilen von ``/stunden`` (``stunden_des_tages``) und der Kanal-Stundentag."""
    from backend.services.energie_profil.kanal_stunden import kanal_stunden, stunden_des_tages

    roh = (await ds.db.execute(select(TagesEnergieProfil).where(
        TagesEnergieProfil.anlage_id == ds.aid, TagesEnergieProfil.datum.in_((tag, date(tag.year, tag.month, tag.day + 1))))
        .order_by(TagesEnergieProfil.datum, TagesEnergieProfil.stunde))).scalars().all()
    return await stunden_des_tages(ds.db, ds.aid, tag, roh), await kanal_stunden(ds.db, ds.aid, tag)


async def test_kennzahlen_aus_den_kanal_stunden_eigene_rechnung(uhr):
    from backend.core.berechnungen.performance_ratio import berechne_performance_ratio
    from backend.core.berechnungen.pv_anteil_ladung import leite_pv_anteil_ab, stunde_aus_bilanzwerten
    from backend.core.berechnungen.spannen import spanne
    from backend.services.energie_profil.kanal_stunden import (
        einspeisung_neg_preis_der_kanal_stunden, ladeanteil_der_kanal_stunden, performance_ratio_des_kanal_tags,
    )

    async with kg.datenstand("achsen", "M08", "HA") as ds:
        await _aggregieren(ds)
        misch, (tag, ks) = await _misch(ds)
        tz = (await ds.db.execute(select(TagesZusammenfassung).where(
            TagesZusammenfassung.anlage_id == ds.aid, TagesZusammenfassung.datum == TAG))).scalar_one()
    assert "emob" in tag.gruppen and len(misch) == 24
    # PR: Σ PV der Mischzeilen (ohne Sonstiges-Erzeuger — M08 hat keinen) ÷ GTI × kWp
    pv = sum(m.pv_kw for m in misch if m.pv_kw is not None)
    assert performance_ratio_des_kanal_tags(tag, ks, 5000.0, 10.0) == berechne_performance_ratio(pv, 5000.0, 10.0)
    # §51: Kanal-Stunde h × Börsenpreis h (Beginn-Raster, keine Verschiebung)
    boerse = {h: (-1.0 if h in (11, 12, 13) else 5.0) for h in range(24)}
    soll = round(sum(m.einspeisung_kw for m in misch if m.stunde in (11, 12, 13) and (m.einspeisung_kw or 0) > 0), 3)
    assert einspeisung_neg_preis_der_kanal_stunden(ks, boerse) == (soll or None)
    # Heimladung: je Mischzeile die Bilanzwerte, gebündelte Stunden «nicht gedeckt»
    stunden = []
    for m in misch:
        geb = any(spanne(m.spannen, a) > 1 for a in ("wallbox", "pv", "netzbezug"))
        stunden.append(stunde_aus_bilanzwerten(ladung=m.wallbox_kw, netzbezug=None if geb else m.netzbezug_kw,
                                               einspeisung=None if geb else m.einspeisung_kw, batterie_spalte=m.batterie_kw))
    eigen = leite_pv_anteil_ab(stunden)
    assert ladeanteil_der_kanal_stunden(ks) == eigen and eigen is not None
    # … und genau diese Zahlen stehen in der Tageszeile, die der Schreiber am Kanal-Tag schrieb
    assert (tz.emob_ladung_pv_abgeleitet_kwh, tz.emob_ladung_netz_abgeleitet_kwh) == (eigen.pv_kwh, eigen.netz_kwh)


# ── Lesestelle: Tagesliste / tage-werte = Cockpit → Tag je Schlüssel ─────────────────────────────────────────────


@pytest.mark.parametrize("fid,praefix", [("M05", "waermepumpe_"), ("M08", "wallbox_"), ("M10", "sonstige_")])
async def test_tagesliste_kanal_tag_mit_verfaelschter_tageszeile_wie_cockpit_tag(uhr, fid, praefix):
    """Eine (Alt-)Tageszeile mit verfälschten Gruppen-Schlüsseln an einem Kanal-Tag: die Tagesliste (``/tage``) nennt die
    Kanal-Werte — dieselben, die *Cockpit → Tag* (``tages_eingaenge``, ``komponenten_der_tage``) liest."""
    from backend.api.routes.energie_profil.tage import get_tages_zusammenfassungen
    from backend.services.energie_profil.kanal_stunden import komponenten_der_tage, tages_eingaenge

    async with kg.datenstand("achsen", fid, "HA") as ds:
        soll = (await komponenten_der_tage(ds.db, ds.aid, TAG, TAG))[TAG]
        assert any(k.startswith(praefix) for k in soll), soll
        await ds.db.execute(update(TagesZusammenfassung).where(
            TagesZusammenfassung.anlage_id == ds.aid, TagesZusammenfassung.datum == TAG,
        ).values(komponenten_kwh={k: v * 3 for k, v in soll.items()}))
        await ds.db.commit()
        liste = {z.datum: z for z in await get_tages_zusammenfassungen(anlage_id=ds.aid, von=TAG, bis=TAG, db=ds.db)}
        anlage = (await ds.db.execute(select(Anlage).where(Anlage.id == ds.aid))).scalar_one()
        invs = {str(i.id): i for i in (await ds.db.execute(
            select(Investition).where(Investition.anlage_id == ds.aid))).scalars()}
        cockpit = await tages_eingaenge(ds.db, anlage, invs, TAG)
    assert liste[TAG].komponenten_kwh == soll
    if praefix == "waermepumpe_":
        assert {k: v for k, v in cockpit.tz_komp.items() if k.startswith(praefix)} == \
            {k: v for k, v in soll.items() if k.startswith(praefix)}


async def test_ueberschuss_defizit_der_tage_wie_tage_werte_bestand_tageszeile(uhr):
    from backend.services.energie_profil.kanal_stunden import ueberschuss_defizit_der_tage
    from backend.services.energie_profil.tage_werte import baue_tage_werte

    async with kg.datenstand("achsen", "M01", "HA") as ds:
        anlage = (await ds.db.execute(select(Anlage).where(Anlage.id == ds.aid))).scalar_one()
        tw = {z.datum: z for z in await baue_tage_werte(ds.db, anlage, TAG, TAG)}
        kanal = await ueberschuss_defizit_der_tage(ds.db, ds.aid, TAG, TAG)
        await _ohne_kanalzeilen(ds)
        await _aggregieren(ds)
        tz = (await ds.db.execute(select(TagesZusammenfassung).where(
            TagesZusammenfassung.anlage_id == ds.aid, TagesZusammenfassung.datum == TAG))).scalar_one()
        bestand = await ueberschuss_defizit_der_tage(ds.db, ds.aid, TAG, TAG)
    assert round(kanal[TAG][0], 3) == tw[TAG].ueberschuss_kwh and round(kanal[TAG][1], 3) == tw[TAG].defizit_kwh
    assert bestand[TAG] == (tz.ueberschuss_kwh, tz.defizit_kwh)


async def test_rollup_monat_liest_kanal_tage_aus_der_lesestelle(uhr):
    from backend.models.monatsdaten import Monatsdaten
    from backend.services.energie_profil.kanal_stunden import ueberschuss_defizit_der_tage
    from backend.services.energie_profil.rollup import rollup_month

    async with kg.datenstand("achsen", "M01", "HA") as ds:
        md = (await ds.db.execute(select(Monatsdaten).where(
            Monatsdaten.anlage_id == ds.aid, Monatsdaten.jahr == 2026, Monatsdaten.monat == 6))).scalar_one_or_none()
        if md is None:
            ds.db.add(Monatsdaten(anlage_id=ds.aid, jahr=2026, monat=6))
            await ds.db.commit()
        tage = await ueberschuss_defizit_der_tage(ds.db, ds.aid, date(2026, 6, 1), date(2026, 6, 30), tageszeilen_form=True)
        assert await rollup_month(ds.aid, 2026, 6, ds.db)
        await ds.db.commit()
        md = (await ds.db.execute(select(Monatsdaten).where(
            Monatsdaten.anlage_id == ds.aid, Monatsdaten.jahr == 2026, Monatsdaten.monat == 6))).scalar_one()
    assert md.ueberschuss_kwh == round(sum(u for u, _ in tage.values() if u is not None), 1) and md.ueberschuss_kwh


async def test_archiv_nachzug_pr_am_kanal_tag_aus_den_kanal_stunden(uhr):
    from backend.core.berechnungen.anlagen_kwp import anlagen_kwp
    from backend.services.energie_profil.archiv_nachzug import _wetterzeile_schreiben
    from backend.services.energie_profil.kanal_stunden import kanal_stunden, performance_ratio_des_kanal_tags

    stunden = {h: {"temperatur_c": 20.0, "globalstrahlung_wm2": 400.0, "gti_wm2": 450.0} for h in range(6, 20)}
    async with kg.datenstand("achsen", "M01", "HA") as ds:
        anlage = (await ds.db.execute(select(Anlage).where(Anlage.id == ds.aid))).scalar_one()
        invs = list((await ds.db.execute(select(Investition).where(Investition.anlage_id == ds.aid))).scalars())
        assert await _wetterzeile_schreiben(anlage, TAG, stunden, invs, set(), ds.db)
        await ds.db.commit()
        tz = (await ds.db.execute(select(TagesZusammenfassung).where(
            TagesZusammenfassung.anlage_id == ds.aid, TagesZusammenfassung.datum == TAG))).scalar_one()
        tag, ks = await kanal_stunden(ds.db, ds.aid, TAG)
    soll = performance_ratio_des_kanal_tags(tag, ks, 450.0 * 14, anlagen_kwp(invs, TAG, mit_bkw=True,
                                                                               referenzwert=anlage.leistung_kwp))
    assert soll is not None and tz.performance_ratio == soll


# ── Werkbank: die Rückmeldung nennt die leer gelassenen Gruppen ────────────────────────────────────────────────


async def test_werkbank_rueckmeldung_nennt_kanal_gruppen(uhr):
    from backend.api.routes.energie_profil.repair import _pv_tagessumme, _stunden_mit_messdaten
    from backend.services.energie_profil.kanal_stunden import pv_ist_je_tag
    from backend.services.repair_orchestrator import _komponenten_rueckmeldung

    async with kg.datenstand("achsen", "M05", "HA") as ds:
        (z,) = await _aggregieren(ds)
        anlage = (await ds.db.execute(select(Anlage).where(Anlage.id == ds.aid))).scalar_one()
        r = await _komponenten_rueckmeldung(ds.db, anlage, TAG, z)
        stunden = await _stunden_mit_messdaten(ds.db, ds.aid, TAG)
        pv = await _pv_tagessumme(ds.db, ds.aid, TAG)
        tz = (await ds.db.execute(select(TagesZusammenfassung).where(
            TagesZusammenfassung.anlage_id == ds.aid, TagesZusammenfassung.datum == TAG))).scalar_one()
        ist = (await pv_ist_je_tag(ds.db, ds.aid, [tz]))[TAG]
    assert r["kanal_gruppen"] == ["PV, Netz und Speicher", "die Wärmepumpe"]
    assert r["komponenten_ohne_wert"] == [] and all(k["geschrieben"] for k in r["komponenten"])
    assert stunden > 0                                  # nicht «0/24 Stunden mit Messdaten»
    assert pv == round(ist, 2) and pv > 0


# ── H-1 → B (Entscheid Master 19.10.): Lesart-1-Monat mit Kanal-Tagen ─────────────────────────────────────────────


async def _rand_monat(ds) -> None:
    """Juni zum Rand-Monat machen: die Kanalzeilen vor dem 10.06. weg ⇒ Juni hat Wahl `bestand` (Lesart 1), 10.–30.06. sind
    Kanal-Tage; dann alle Tage neu schreiben wie im Produkt (Kanal-Tage ohne Mengen)."""
    from backend.services.kanal import merken

    ab = int(datetime(2026, 6, 10).timestamp())
    ids = select(Kanal.id).where(Kanal.anlage_id == ds.aid)
    await ds.db.execute(delete(KanalStatistik).where(KanalStatistik.kanal_id.in_(ids), KanalStatistik.start_ts < ab))
    await ds.db.commit()
    merken.leeren()
    await _aggregieren(ds, kg.TAGE)


async def test_lesart1_monat_mit_kanal_tagen_faltet_kanal_tage_aus_der_lesestelle(uhr):
    """Monatswert = Σ Bestandstage (Zeilen) + Σ Kanal-Tage (`tage-werte`) je Größe — der Monat verliert die Kanal-Tage nicht,
    obwohl ihre Zeilen seit S5b keine Mengen tragen."""
    from backend.services.energie_profil.monats_aus_tagen import lade_monats_summen_aus_tagen
    from backend.services.energie_profil.tage_werte import baue_tage_werte
    from backend.services.kanal.bilanz_leser import kanal_monate, kanal_tage

    async with kg.datenstand("achsen", "M01", "HA") as ds:
        await _rand_monat(ds)
        assert (2026, 6) not in await kanal_monate(ds.db, ds.aid, von=(2026, 6), bis=(2026, 6))
        kt = await kanal_tage(ds.db, ds.aid, date(2026, 6, 1), date(2026, 6, 30))
        anlage = (await ds.db.execute(select(Anlage).where(Anlage.id == ds.aid))).scalar_one()
        erster = min(kt)
        tw = await baue_tage_werte(ds.db, anlage, date(2026, 6, 1), date(2026, 6, 30))
        monat = (await lade_monats_summen_aus_tagen(ds.db, ds.aid, von=(2026, 6), bis=(2026, 6)))[(2026, 6)]
        leer = (await ds.db.execute(select(TagesEnergieProfil.pv_kw).where(
            TagesEnergieProfil.anlage_id == ds.aid, TagesEnergieProfil.datum == erster))).scalars().all()
    assert erster >= date(2026, 6, 10) and len(kt) >= 15 and leer and all(v is None for v in leer)
    assert monat.einspeisung_kwh == pytest.approx(sum(z.einspeisung or 0.0 for z in tw), abs=1e-6)
    assert monat.netzbezug_kwh == pytest.approx(sum(z.netzbezug or 0.0 for z in tw), abs=1e-6)
    assert monat.pv_module_kwh + monat.bkw_kwh == pytest.approx(sum(z.erzeugung or 0.0 for z in tw), abs=1e-6)
    assert monat.tage == 30


async def test_monat_ohne_kanal_tage_wie_bisher(uhr):
    """Ohne Kanal-Tag faltet der Monat Stunden- und Tageszeilen wie bis E-S5-2 (dieselbe Faltung über dieselben Zeilen)."""
    from backend.core.berechnungen.tagesbilanz import bilanz_aus_stundenrows
    from backend.services.energie_profil.monats_aus_tagen import TagesZeile, falte_monat, lade_monats_summen_aus_tagen

    async with kg.datenstand("achsen", "M01", "HA") as ds:
        await _ohne_kanalzeilen(ds)
        await _aggregieren(ds, kg.TAGE)
        tz = list((await ds.db.execute(select(TagesZusammenfassung).where(
            TagesZusammenfassung.anlage_id == ds.aid, TagesZusammenfassung.datum >= date(2026, 6, 1),
            TagesZusammenfassung.datum <= date(2026, 6, 30)))).scalars())
        tep = list((await ds.db.execute(select(TagesEnergieProfil).where(
            TagesEnergieProfil.anlage_id == ds.aid, TagesEnergieProfil.datum >= date(2026, 6, 1),
            TagesEnergieProfil.datum <= date(2026, 6, 30)))).scalars())
        neu = (await lade_monats_summen_aus_tagen(ds.db, ds.aid, von=(2026, 6), bis=(2026, 6)))[(2026, 6)]
    je_tag: dict = {}
    for r in tep:
        je_tag.setdefault(r.datum, []).append(r)
    verworfen = {z.datum: z.verworfen for z in tz}
    alt = falte_monat(
        stunden_tage=[(d, bilanz_aus_stundenrows(rows, verworfen=verworfen.get(d)), len(rows)) for d, rows in sorted(je_tag.items())],
        tageszeilen=[TagesZeile(datum=z.datum, komponenten_kwh=z.komponenten_kwh, source_provenance=z.source_provenance,
                                emob_ladung_pv_abgeleitet_kwh=z.emob_ladung_pv_abgeleitet_kwh,
                                emob_ladung_netz_abgeleitet_kwh=z.emob_ladung_netz_abgeleitet_kwh,
                                emob_ladung_speicher_abgeleitet_kwh=z.emob_ladung_speicher_abgeleitet_kwh) for z in tz])
    assert neu == alt and neu.einspeisung_kwh > 0


# ── H-2 → B (Entscheid Gernot 19.10.): die Bilanz-Komposition schlägt die Sonstiges-Ersatzgruppe ──────────────────


def test_sonstiges_gruppe_ueberschreibt_keinen_schluessel_der_komposition():
    from backend.services.energie_profil.kanal_stunden import _ohne_bilanz

    ziele = frozenset({"sonstige_3", "pv_1", "einspeisung"})
    assert _ohne_bilanz({"sonstige_3": 5.0, "sonstige_7": 2.0}, ziele) == {"sonstige_7": 2.0}
    assert _ohne_bilanz(None, ziele) is None


async def test_tagesliste_gleich_tag_detail_am_w2_ausfalltag(uhr):
    """W2-E (Sonstiges-Erzeuger hinter dem Anlagenzähler) am Ausfalltag: Tagesliste = *Cockpit → Tag* (`tages_eingaenge`)
    — beide die Bilanz-Komposition."""
    from backend.services.energie_profil.kanal_stunden import komponenten_der_tage, tages_eingaenge

    tag = date(2026, 6, 9)
    async with kg.datenstand("achsen", "W2-E", "HA") as ds:
        anlage = (await ds.db.execute(select(Anlage).where(Anlage.id == ds.aid))).scalar_one()
        invs = {str(i.id): i for i in (await ds.db.execute(
            select(Investition).where(Investition.anlage_id == ds.aid))).scalars()}
        liste = (await komponenten_der_tage(ds.db, ds.aid, tag, tag))[tag]
        cockpit = (await tages_eingaenge(ds.db, anlage, invs, tag)).tz_komp
    sonst = {k: v for k, v in liste.items() if k.startswith("sonstige_")}
    assert sonst and sonst == {k: v for k, v in cockpit.items() if k.startswith("sonstige_")}


# ── Nachzug M-1 (Nachmessung Fable): Lade-Hinweise je Leser, WP-Bereich einmal je Anfrage ────────────────────────


def test_gruppen_der_schluessel_bilanz_immer_geraete_nach_praefix():
    from backend.services.energie_profil.kanal_stunden import (
        GRUPPE_BILANZ, GRUPPE_EMOB, GRUPPE_SONSTIGES, GRUPPE_WP, gruppen_der_schluessel,
    )

    assert gruppen_der_schluessel(()) == (GRUPPE_BILANZ,)
    assert gruppen_der_schluessel({"batterie_3", "pv_1"}) == (GRUPPE_BILANZ,)
    assert gruppen_der_schluessel({"eauto_7"}) == (GRUPPE_BILANZ, GRUPPE_EMOB)
    assert gruppen_der_schluessel({"waermepumpe_2", "sonstige_4", "wallbox_5"}) == \
        (GRUPPE_BILANZ, GRUPPE_SONSTIGES, GRUPPE_EMOB, GRUPPE_WP)


async def test_wp_bereich_im_lade_kontext_einmal_teilbereich_geschnitten(uhr):
    """Im Lade-Kontext einer Anfrage liest ``wp_komponenten_der_kanal_tage`` einen Bereich einmal; ein Teilbereich kommt
    aus dem schon gelesenen — dieselben Werte wie ohne Kontext (je Aufruf ein Bereichs-Leser)."""
    from datetime import timedelta

    from backend.services.energie_profil.kanal_stunden import wp_komponenten_der_kanal_tage
    from backend.services.kanal import stunden_leser
    from backend.services.kanal.lade_kontext import lese_anfrage

    gelesen = []
    echt = stunden_leser.kanal_stundentage

    async def _zaehlend(db, anlage_id, von, bis, **kw):
        gelesen.append((von, bis))
        return await echt(db, anlage_id, von, bis, **kw)

    async with kg.datenstand("achsen", "M05", "HA") as ds:
        weit = (TAG - timedelta(days=1), TAG + timedelta(days=1))
        with patch.object(stunden_leser, "kanal_stundentage", _zaehlend):
            with lese_anfrage():
                mit_weit = await wp_komponenten_der_kanal_tage(ds.db, ds.aid, *weit)
                mit_tag = await wp_komponenten_der_kanal_tage(ds.db, ds.aid, TAG, TAG)
                mit_tag[TAG]["waermepumpe_x"] = 1.0          # eine Kopie — das Gehaltene bleibt
                mit_tag_2 = await wp_komponenten_der_kanal_tage(ds.db, ds.aid, TAG, TAG)
            in_anfrage = list(gelesen)
            ohne_tag = await wp_komponenten_der_kanal_tage(ds.db, ds.aid, TAG, TAG)
            ohne_weit = await wp_komponenten_der_kanal_tage(ds.db, ds.aid, *weit)
    assert in_anfrage == [weit]
    assert TAG in ohne_tag and ohne_tag[TAG]
    assert mit_weit == ohne_weit and mit_tag_2 == ohne_tag
