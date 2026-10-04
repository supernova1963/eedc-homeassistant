"""N-609 — eine WP-Ersparnis in jeder Sicht: Σ der Gerätezeilen je Monat.

**Der Fund.** Cockpit → Monat rechnet die WP-Ersparnis seit N-605 als Σ der T-Konto-Zeilen (je Gerät mit SEINEN
Parametern), Cockpit → Jahr als Σ der Monate. Die Übersicht und die Komponenten-Zeitreihe rechneten daneben ein
Aggregat über die Summenmengen mit dem Parametersatz der ERSTEN Wärmepumpe — die Übersicht dazu mit dem HEUTIGEN Tarif
(P8) und ohne Monats-Gaspreis. Gemessen: zwei WP 50 statt 110 €; eine WP Tarifwechsel 0 statt 25 €, Gaspreis 25 statt
65 €, Zusatzkosten 85 statt 105 €, Standby-Monat 19 statt 25 €, Rundung 54,07 statt 54,05 €. Der Monat OHNE
Gerätezeile (laufend, bzw. abgeschlossen ohne Abschluss) rechnete dasselbe Aggregat: zwei WP 1,44 statt 5,76 €.

**Die Regel** (Bauplan N-609, Fassung 2): die WP-Ersparnis ist in jeder Sicht Σ der Gerätezeilen je Monat. Die
Gerätezeile ist EINE Layer-Funktion (``wp_ersparnis_zeile``): Zeile nur bei Wärme > 0 und Strom > 0, Parameter des
Geräts, WP-Preis und Gaspreis des Monats, je Zeile auf 2 Stellen gerundet. Die Mengen je Gerät kommen je Monat aus EINER
Quelle — den Monats-Fakten (``WpFakten.je_geraet``), wo der Monat eine Zeile hat; sonst der Quellen-Kaskade.

**Datenstand wie im Betrieb.** Abgeschlossene Monate über den echten Schreibweg ``create_monatsdaten`` (Datei-Datenbank,
kein HA); der Monat ohne Gerätezeile mit den Matrix-Bausteinen (HA-Statistik im Recorder-Schema, Tage über
``aggregate_day``). Der nachgetragene Kühlanteil (F-52) über Stundenzeilen mit Betriebsmodus, wie der Tageslauf sie
schreibt.
"""

from __future__ import annotations

import shutil
import tempfile
import time as _zeit
from datetime import date, timedelta

import pytest
from sqlalchemy import select, text
from sqlalchemy.orm.attributes import flag_modified

from backend.models import Anlage, Investition, Strompreis
from backend.tests import ha_lts_helfer
from backend.tests import pv_achse_matrix as mx

#: Ein Heizmonat: 900 kWh Wärme, 250 kWh Strom. Bei 30 ct und Gas 10 ct: 1000 × 0,10 − 75 = 25 €; Gas 16 ct: 85 €.
H = {"heizenergie_kwh": 900.0, "warmwasser_kwh": 0.0, "stromverbrauch_kwh": 250.0}
STANDBY = {"heizenergie_kwh": 0.0, "warmwasser_kwh": 0.0, "stromverbrauch_kwh": 20.0}
RUND = {"heizenergie_kwh": 333.3, "warmwasser_kwh": 77.7, "stromverbrauch_kwh": 111.1}
KUEHL_NACHTRAG = {"stromverbrauch_kwh": 950.0, "heizenergie_kwh": 3000.0, "warmwasser_kwh": 600.0}
KUEHL_GESPEICHERT = {**H, "betriebsart_strom_kuehlen_kwh": 100.0}


def _param(preis=10.0, **extra):
    return {"alter_energietraeger": "gas", "alter_preis_cent_kwh": preis, **extra}


#: ``name: (tarife [(ab, bis, ct)], {(j, m): (daten_wp, md_extra)}, wp_param_extra)`` — EINE Wärmepumpe „WP" (Gas
#: 10 ct). Die Zwei-WP-Fassung stellt „WP16" (Gas 16 ct, dieselben Mengen, ohne Zusatzkosten) daneben.
FALL = {
    "konstant": ([(date(2024, 1, 1), None, 30.0)], {(2025, m): (H, {}) for m in (1, 2, 3)}, {}),
    "tarifwechsel": ([(date(2024, 1, 1), date(2025, 8, 31), 30.0), (date(2025, 9, 1), None, 40.0)],
                     {(2025, 6): (H, {})}, {}),
    "gaspreis": ([(date(2024, 1, 1), None, 30.0)], {(2025, 6): (H, {"gaspreis_cent_kwh": 14.0})}, {}),
    "zusatzkosten": ([(date(2024, 1, 1), None, 30.0)], {(2025, m): (H, {}) for m in (1, 2, 3)},
                     {"alternativ_zusatzkosten_jahr": 120.0}),
    "standby-monat": ([(date(2024, 1, 1), None, 30.0)], {(2025, 6): (H, {}), (2025, 7): (STANDBY, {})}, {}),
    "rundung": ([(date(2024, 1, 1), None, 31.37)], {(2025, m): (RUND, {}) for m in (1, 2, 3, 4, 5)}, {}),
    "kuehlen-gespeichert": ([(date(2024, 1, 1), None, 30.0)], {(2025, 6): (KUEHL_GESPEICHERT, {})}, {}),
    # Die IMD-Zeile trägt KEINEN Modus-Split; die Stundenzeilen tragen Heizen 70 % / Kühlen 30 % (F-52-Nachtrag).
    "kuehlen-nachtrag": ([(date(2024, 1, 1), None, 30.0)], {(2025, 6): (KUEHL_NACHTRAG, {})}, {}),
}

#: Σ Monate des Jahres 2025 — eine WP: Bauplan „Erwartete Zahlen"; zwei WP: Σ der zwei Gerätezeilen je Monat
#: (WP16: dieselben Mengen mit Gas 16 ct, ohne Zusatzkosten; ohne Tagesspur im Fall „kuehlen-nachtrag").
SOLL = {
    "konstant": (75.0, 330.0),
    "tarifwechsel": (25.0, 110.0),
    "gaspreis": (65.0, 130.0),
    "zusatzkosten": (105.0, 360.0),
    "standby-monat": (25.0, 110.0),
    "rundung": (54.05, 245.10),
    "kuehlen-gespeichert": (55.0, 170.0),
    "kuehlen-nachtrag": (124.0, 479.0),
}


async def _bau(db, tarife, monate, wp_param_extra, zwei: bool, *, kuehl_nachtrag: bool):
    from backend.api.routes.monatsdaten import MonatsdatenCreate, create_monatsdaten

    a = Anlage(anlagenname="N-609", leistung_kwp=10.0, installationsdatum=date(2024, 1, 1))
    db.add(a)
    await db.flush()
    for ab, bis, ct in tarife:
        db.add(Strompreis(anlage_id=a.id, verwendung="allgemein", gueltig_ab=ab, gueltig_bis=bis,
                          netzbezug_arbeitspreis_cent_kwh=ct, einspeiseverguetung_cent_kwh=8.0))
    pv = Investition(anlage_id=a.id, typ="pv-module", bezeichnung="Dach", leistung_kwp=10.0,
                     anschaffungsdatum=date(2024, 1, 1), anschaffungskosten_gesamt=10000.0)
    db.add(pv)
    await db.flush()
    ids = {}
    wps = [("WP", _param(10.0, **wp_param_extra))] + ([("WP16", _param(16.0))] if zwei else [])
    for name, param in wps:
        w = Investition(anlage_id=a.id, typ="waermepumpe", bezeichnung=name, anschaffungsdatum=date(2024, 1, 1),
                        anschaffungskosten_gesamt=1000.0, parameter=param)
        db.add(w)
        await db.flush()
        ids[name] = w.id
    await db.commit()
    for (j, m), (daten, extra) in sorted(monate.items()):
        n = {"anlage_id": a.id, "jahr": j, "monat": m, "einspeisung_kwh": 300.0, "netzbezug_kwh": 200.0,
             "geprueft_gegen": {}, **extra,
             "investitionen_daten": {str(pv.id): {"pv_erzeugung_kwh": 800.0},
                                     **{str(i): dict(daten) for i in ids.values()}}}
        await create_monatsdaten(MonatsdatenCreate.model_validate(n), None, db)
        await db.commit()
    if kuehl_nachtrag:
        from backend.core.betriebsmodus import AUS, HEIZEN, KUEHLEN
        from backend.models.tages_energie_profil import TagesEnergieProfil, TagesZusammenfassung

        tag, wid = date(2025, 6, 10), ids["WP"]
        for stunde, (modus, kwh) in enumerate([(HEIZEN, 7.0), (KUEHLEN, 3.0), (AUS, 0.0)]):
            db.add(TagesEnergieProfil(anlage_id=a.id, datum=tag, stunde=stunde,
                                      komponenten={f"waermepumpe_{wid}": -kwh},
                                      betriebsmodus_je_wp={str(wid): modus}))
        db.add(TagesZusammenfassung(anlage_id=a.id, datum=tag, komponenten_kwh={f"waermepumpe_{wid}": 100.0}))
        await db.commit()
    return a.id, ids


async def _sichten(db, aid, ids, monate) -> dict:
    """Monat · Jahr-Kopf · Übersicht (Jahr und alle Jahre) · Komponenten-Zeitreihe · HA-Export je WP."""
    import backend.api.routes.aktueller_monat as am
    from backend.api.routes.cockpit.komponenten import get_komponenten_zeitreihe
    from backend.api.routes.cockpit.uebersicht import get_cockpit_uebersicht
    from backend.api.routes.ha_export.investition_sensoren import calculate_investition_sensors
    from backend.services.jahres_aggregat import baue_jahr

    out = {"monat": {}, "zeilen": {}, "jahr_kopf": {}, "uebersicht": {}, "rendite": {}, "komponenten": {}, "ha": {}}
    for j, m in sorted(monate):
        r = await am.get_aktueller_monat(anlage_id=aid, jahr=j, monat=m, db=db)
        out["monat"][(j, m)] = r.wp_ersparnis_euro
        out["zeilen"][(j, m)] = [z.ersparnis_euro for z in r.investitionen_financials if z.typ == "waermepumpe"]
    jahre = sorted({j for j, _ in monate})
    for j in jahre:
        jj = await baue_jahr(db, aid, j, heute=mx.JETZT.date())
        kopf = jj["kopf"] if isinstance(jj["kopf"], dict) else jj["kopf"].model_dump()
        out["jahr_kopf"][j] = kopf.get("wp_ersparnis_euro")
    for j in jahre + [None]:
        u = await get_cockpit_uebersicht(anlage_id=aid, jahr=j, db=db)
        out["uebersicht"][j] = u.wp_ersparnis_euro
        out["rendite"][j] = u.jahres_rendite_prozent
    kz = await get_komponenten_zeitreihe(anlage_id=aid, jahr=None, db=db)
    kd = kz if isinstance(kz, dict) else kz.model_dump()
    out["komponenten"] = {(w["jahr"], w["monat"]): w.get("wp_ersparnis_euro") for w in kd.get("monatswerte", [])}
    for name, wid in ids.items():
        inv = (await db.execute(select(Investition).where(Investition.id == wid))).scalar_one()
        sens = await calculate_investition_sensors(db, inv, None)
        out["ha"][name] = next((s.value for s in sens if s.definition.key == "wp_ersparnis_euro"), None)
    return out


@pytest.mark.parametrize("zwei", [False, True], ids=["eine-wp", "zwei-wp"])
@pytest.mark.parametrize("fall", list(FALL))
async def test_eine_ersparnis_in_jeder_sicht(fall, zwei):
    tarife, monate, extra = FALL[fall]
    verz = tempfile.mkdtemp(prefix="eedc-n609-")
    try:
        engine, db = await mx._neue_db(f"{verz}/x.db")
        try:
            with mx._umgebung(mx._ha_aus()):
                aid, ids = await _bau(db, tarife, monate, extra, zwei, kuehl_nachtrag=fall == "kuehlen-nachtrag")
                s = await _sichten(db, aid, ids, monate)
        finally:
            await db.close()
            await engine.dispose()
    finally:
        shutil.rmtree(verz, ignore_errors=True)

    soll = SOLL[fall][1 if zwei else 0]
    # Der Monat ist Σ seiner Gerätezeilen (N-605) — je Zeile auf 2 Stellen.
    for k, v in s["monat"].items():
        zeilen = s["zeilen"][k]
        assert v == (round(sum(zeilen), 2) if zeilen else None), (fall, k, v, zeilen)
    summe = round(sum(v or 0.0 for v in s["monat"].values()), 2)
    assert summe == soll, (fall, zwei, summe, s)
    assert round(s["jahr_kopf"][2025], 2) == soll, (fall, zwei, s["jahr_kopf"])
    assert round(s["uebersicht"][2025], 2) == soll, (fall, zwei, s["uebersicht"])
    assert round(s["uebersicht"][None], 2) == soll, (fall, zwei, s["uebersicht"])
    assert round(sum(s["komponenten"].values()), 2) == soll, (fall, zwei, s["komponenten"])
    for k, v in s["monat"].items():
        assert round(s["komponenten"][k], 2) == (v or 0.0), (fall, zwei, k, s["komponenten"], s["monat"])
    # HA-Export daneben (unverändert, je Gerät kumuliert): dieselbe Zahl bis auf die Rundung je Zeile — außer im
    # Standby-Monat, wo er den Strom ohne Wärme belastet (benannte Grenze, Bauplan N-609).
    if fall != "standby-monat":
        n_zeilen = sum(len(z) for z in s["zeilen"].values())
        assert abs(sum(s["ha"].values()) - soll) <= 0.005 * n_zeilen + 1e-9, (fall, zwei, s["ha"], soll)


async def test_zwei_wp_zwei_jahre_rendite():
    """Bauplan: zwei WP (Gas 10 bzw. 16 ct), Juni 2024 und Juni 2025 — Monat 110 = Jahr-Kopf = Übersicht = Komponenten,
    alle Jahre 220; die Jahres-Rendite der Übersicht folgt (1,9 ⇒ 2,4 %)."""
    monate = {(2024, 6): (H, {}), (2025, 6): (H, {})}
    verz = tempfile.mkdtemp(prefix="eedc-n609-")
    try:
        engine, db = await mx._neue_db(f"{verz}/x.db")
        try:
            with mx._umgebung(mx._ha_aus()):
                aid, ids = await _bau(db, [(date(2024, 1, 1), None, 30.0)], monate, {}, True, kuehl_nachtrag=False)
                s = await _sichten(db, aid, ids, monate)
        finally:
            await db.close()
            await engine.dispose()
    finally:
        shutil.rmtree(verz, ignore_errors=True)
    assert s["monat"] == {(2024, 6): 110.0, (2025, 6): 110.0}, s["monat"]
    assert s["zeilen"][(2025, 6)] == [25.0, 85.0], s["zeilen"]
    assert s["jahr_kopf"] == {2024: 110.0, 2025: 110.0}, s["jahr_kopf"]
    assert s["uebersicht"] == {2024: 110.0, 2025: 110.0, None: 220.0}, s["uebersicht"]
    assert s["komponenten"] == {(2024, 6): 110.0, (2025, 6): 110.0}, s["komponenten"]
    assert s["rendite"][2025] == 2.4, s["rendite"]
    assert s["ha"] == {"WP": 50.0, "WP16": 170.0}, s["ha"]


# ── Monat OHNE Gerätezeile: HA-Statistik + Tageszeilen (Matrix-Bausteine) ──────────────────────────────────────────


def _wp(preis):
    return ("waermepumpe", _param(preis), {"stromverbrauch_kwh": lambda t: 0.3, "waerme_kwh": lambda t: 0.9})


async def _ohne_zeile(fall: str) -> dict:
    """F06 + Wärmepumpen mit eigenen HA-Zählern (je Juli-Tag Strom 7,2 / Wärme 21,6) — Juli laufend, Juni ohne
    Abschluss. ``fall``: zwei-wp · tage-ab-0207 (Tagesspur erst ab 02.07.) · gespeichert-tag2 · eine-wp."""
    import backend.api.routes.aktueller_monat as am

    form = mx.FORMEN["F06"]
    extra = {"WP A": _wp(10.0)} if fall == "eine-wp" else {"WP A": _wp(10.0), "WP B": _wp(16.0)}
    verz = tempfile.mkdtemp(prefix="eedc-n609-lm-")
    try:
        engine, db = await mx._neue_db(f"{verz}/x.db")
        try:
            aid, ids = await mx.seed_anlage(db, form)
            svc = mx.seed_ha(form)
            a = (await db.execute(select(Anlage).where(Anlage.id == aid))).scalar_one()
            m = dict(a.sensor_mapping)
            inv_map = dict(m.get("investitionen") or {})
            for name, (typ, param, felder) in extra.items():
                inv = Investition(anlage_id=aid, typ=typ, bezeichnung=name, anschaffungsdatum=mx.D0,
                                  anschaffungskosten_gesamt=1000.0, parameter=param)
                db.add(inv)
                await db.flush()
                ids[name] = inv.id
                fm = {}
                for feld, fn in felder.items():
                    sid = f"sensor.{name.lower().replace(' ', '_')}_{feld}"
                    fm[feld] = {"strategie": "sensor", "sensor_id": sid}
                    mid = ha_lts_helfer.sensor(svc, sid, "kWh", has_sum=True)
                    stand, zeilen, t = 500.0, [], mx.REIHE_VON
                    while t < mx.REIHE_BIS:
                        stand += fn(t)
                        zeilen.append({"m": mid, "t": _zeit.mktime(t.timetuple()), "w": round(stand, 4)})
                        t += timedelta(hours=1)
                    with svc._engine.begin() as conn:
                        conn.execute(text("INSERT INTO statistics (metadata_id, start_ts, state, sum) "
                                          "VALUES (:m, :t, :w, :w)"), zeilen)
                inv_map[str(inv.id)] = {"felder": fm}
            m["investitionen"] = inv_map
            a.sensor_mapping = m
            flag_modified(a, "sensor_mapping")
            await db.commit()
            with mx._umgebung(svc):
                tage = mx.TAGE_JULI[1:] if fall == "tage-ab-0207" else mx.TAGE_JULI
                await mx.aggregiere_tage(db, form, aid, tage)
                if fall == "gespeichert-tag2":
                    from backend.api.routes.monatsdaten import MonatsdatenCreate, create_monatsdaten
                    n = {"anlage_id": aid, "jahr": mx.JAHR, "monat": mx.JULI, "einspeisung_kwh": 12.0,
                         "netzbezug_kwh": 14.4, "geprueft_gegen": {},
                         "investitionen_daten": {str(ids[k]): {"stromverbrauch_kwh": 14.4, "waerme_kwh": 43.2}
                                                 for k in extra}}
                    await create_monatsdaten(MonatsdatenCreate.model_validate(n), None, db)
                    await db.commit()
                out = {}
                for monat in (mx.JULI, mx.JUNI):
                    r = await am.get_aktueller_monat(anlage_id=aid, jahr=mx.JAHR, monat=monat, db=db)
                    out[monat] = (r.wp_ersparnis_euro, r.wp_ersparnis_berechnung)
                return out
        finally:
            await db.close()
            await engine.dispose()
    finally:
        shutil.rmtree(verz, ignore_errors=True)


@pytest.mark.parametrize("fall,juli,juni", [
    ("zwei-wp", 5.76, 57.6),            # je Gerät 0,72 + 5,04 — vorher Aggregat mit WP A: 1,44 / 14,40
    ("tage-ab-0207", 5.76, 57.6),       # Mengen aus der Kaskade (HA-Statistik), nicht aus `wp_geraete` (10,08)
    ("gespeichert-tag2", 3.84, 57.6),   # Juli: die T-Konto-Zeilen der gespeicherten Zeile gewinnen (0,48 + 3,36)
    ("eine-wp", 0.72, 7.2),             # eine WP: bitgleich zum Aggregat
])
async def test_monat_ohne_geraetezeile(fall, juli, juni):
    out = await _ohne_zeile(fall)
    assert (out[mx.JULI][0], out[mx.JUNI][0]) == (juli, juni), out
    if fall in ("zwei-wp", "tage-ab-0207"):
        # Die Herleitung nennt jedes Gerät.
        assert out[mx.JULI][1].startswith("WP A: ") and "\nWP B: " in out[mx.JULI][1], out[mx.JULI][1]
