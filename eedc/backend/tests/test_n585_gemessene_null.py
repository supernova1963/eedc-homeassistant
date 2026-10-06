"""N-585 — eine gemessene 0 bleibt eine 0; ein Feld ohne Messung bleibt ``None``.

**Der Fund.** Die Sammler des laufenden Monats (und des abgeschlossenen Monats ohne Monatsabschluss) ließen nur Werte
über 0 durch. Ein autarker Monat (Netzbezugs-Zähler flach) verlor Gesamtverbrauch, Autarkie, Stromrechnung und Ergebnis
und bekam den Rat „Den Zähler dieser Größe zuordnen" — obwohl der Zähler zugeordnet ist und 0 misst. Eine
Nulleinspeisung verlor Eigenverbrauch, Quote, Erlös und Netto-Ertrag.

**Die Regel** (Bauplan N-585, Fassung 2; ``KONZEPT-UNVOLLSTAENDIGE-WERTE.md`` §3): ein Feld, für das eine Quelle im Monat
**gemessen** hat, trägt deren Wert auch dann, wenn er 0 ist. Gemessen heißt bei der HA-Statistik mindestens ein
Intervall (Anker + eine Zeile oder zwei Zeilen — ``SensorMonatswert.intervalle``), bei der Tagesebene mindestens eine
Stunde mit Wert (``*_erfasst``). Eine einzelne Statistik-Zeile misst kein Intervall; ihre 0 wäre erfunden. Die 0 gilt für
Einspeisung, Netzbezug, den Anlagen-PV-Zähler und die Gerätefelder von Speicher, Balkonkraftwerk, Wallbox und E-Auto —
**nicht** für den PV-String (Halteprobe unten, Grund im Bauplan). Die Wärmepumpe folgt seit HA-Bauform E4d (Bauplan §8a,
Rest N-585): Strom 0 und Wärme 0 gemessen ist „kein Betrieb im Zeitraum".

**Datenstand wie im Betrieb** (Matrix-Bausteine, ``pv_achse_matrix.py``): HA-Langzeitstatistik im Recorder-Schema mit
dem echten ``HAStatisticsService``, Tageszeilen über den echten ``aggregate_day`` für Juni und die drei Juli-Tage — HA
UND Tagesebene zugleich, wie im Betrieb. Dazu Speicher, Wärmepumpe und Wallbox mit eigenen HA-Zählern (Bauform der
T3-Probe ``test_n624_quellen_laufender_monat.py``). Juli 2026 läuft (``JETZT`` = 04.07. 00:30), der Juni ist
abgeschlossen, aber ohne Monatsabschluss. Standalone: Zählerstände in ``sensor_snapshots``, kein HA.

Je Juli-Tag: Süd 12 · West 6 · Balkon 3 (Σ PV 21), Einspeisung 6, Netzbezug 7,2; Akku Ladung 3 / Entladung 2, WP Strom
7,2 / Wärme 21,6, Wallbox 3. Tarif 30 ct / 8 ct.
"""

from __future__ import annotations

import shutil
import tempfile
import time as _zeit
from datetime import datetime, timedelta
from typing import Optional
from unittest.mock import patch

import pytest
from sqlalchemy import select, text
from sqlalchemy.orm.attributes import flag_modified

from backend.models import Anlage, Investition
from backend.tests import ha_lts_helfer
from backend.tests import pv_achse_matrix as mx


def _null(_t):
    return 0.0


def _sonne(rate):
    return lambda t: rate if t.hour in mx.PROD_STUNDEN else 0.0


#: Weitere Geräte mit eigenen HA-Zählern — ``name: (typ, parameter, {feld: rate_fn})`` (T3-Probe).
def _zusatz(**ersetze):
    e = {
        "Akku": ("speicher", {"kapazitaet_kwh": 10.0},
                 {"ladung_kwh": _sonne(0.5), "entladung_kwh": lambda t: 0.4 if 18 <= t.hour <= 22 else 0.0}),
        "WP": ("waermepumpe", None, {"stromverbrauch_kwh": lambda t: 0.3, "waerme_kwh": lambda t: 0.9}),
        "Wallbox": ("wallbox", None, {"ladung_kwh": lambda t: 1.0 if 11 <= t.hour <= 13 else 0.0}),
    }
    e.update(ersetze)
    return e


class _Lauf:
    """``async with _Lauf(form, zusatz, abweichung) as (db, aid, ids)`` — Seed, HA-Dienst, Tageszeilen Juni + Juli."""

    def __init__(self, form_id: str, zusatz: Optional[dict] = None, abweichung: Optional[dict] = None,
                 *, ohne_basis: tuple[str, ...] = (), tage=mx.TAGE_JUNI + mx.TAGE_JULI):
        self.form = mx.FORMEN[form_id]
        self.zusatz, self.abw, self.ohne_basis, self.tage = zusatz, abweichung, ohne_basis, tage

    async def __aenter__(self):
        self.verz = tempfile.mkdtemp(prefix="eedc-n585-")
        self.engine, self.db = await mx._neue_db(f"{self.verz}/x.db")
        db = self.db
        aid, ids = await mx.seed_anlage(db, self.form)
        svc = mx.seed_ha(self.form, abweichung=self.abw)
        a = (await db.execute(select(Anlage).where(Anlage.id == aid))).scalar_one()
        m = dict(a.sensor_mapping)
        inv_map = dict(m.get("investitionen") or {})
        for name, (typ, param, felder) in (self.zusatz or {}).items():
            kw = dict(anlage_id=aid, typ=typ, bezeichnung=name, anschaffungsdatum=mx.D0, anschaffungskosten_gesamt=1000.0)
            if param:
                kw["parameter"] = dict(param)
            inv = Investition(**kw)
            db.add(inv)
            await db.flush()
            ids[name] = inv.id
            fm = {}
            for feld, fn in felder.items():
                sid = f"sensor.{name.lower()}_{feld}"
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
        if self.ohne_basis:
            m["basis"] = {k: v for k, v in m["basis"].items() if k not in self.ohne_basis}
        a.sensor_mapping = m
        flag_modified(a, "sensor_mapping")
        await db.commit()
        self.st = mx._umgebung(svc)
        self.st.__enter__()
        await mx.aggregiere_tage(db, self.form, aid, self.tage)
        self.aid, self.ids = aid, ids
        return db, aid, ids

    async def __aexit__(self, *exc):
        self.st.__exit__(*exc)
        await self.db.close()
        await self.engine.dispose()
        shutil.rmtree(self.verz, ignore_errors=True)


async def _monat(db, aid, monat: int) -> dict:
    import backend.api.routes.aktueller_monat as am

    r = await am.get_aktueller_monat(anlage_id=aid, jahr=mx.JAHR, monat=monat, db=db)
    return r.model_dump(mode="json")


def _r(x, n=2):
    return None if x is None else round(float(x), n)


def _bilanz(d: dict) -> dict:
    return {
        "netz": _r(d["netzbezug_kwh"]), "einsp": _r(d["einspeisung_kwh"]), "ev": _r(d["eigenverbrauch_kwh"]),
        "quote": _r(d["eigenverbrauch_quote_prozent"], 1), "gv": _r(d["gesamtverbrauch_kwh"]),
        "autarkie": _r(d["autarkie_prozent"], 1), "kosten": _r(d["netzbezug_kosten_euro"]),
        "ergebnis": _r(d["ergebnis_euro"]), "fehlend": d["fehlende_posten"], "gruende": sorted(d["datenlage_gruende"]),
    }


# ── Bilanzfälle: Netzbezug 0 · Einspeisung 0 · Volleinspeiser · beide 0 ─────────────────────────────────────────────

#: ``name: (form, zusatz, abweichung, {monat: {feld: soll}})`` — Soll aus dem Bauplan, Abschnitt „Erwartete Zahlen".
BILANZ = {
    "netzbezug-0": ("F06", _zusatz(), {"sensor.netz": (_null, None)}, {
        mx.JULI: {"netz": 0.0, "gv": 42.0, "autarkie": 100.0, "kosten": 0.0, "ergebnis": 16.2},
        mx.JUNI: {"netz": 0.0, "gv": 420.0, "autarkie": 100.0, "kosten": 0.0, "ergebnis": 162.0},
    }),
    "einspeisung-0": ("F06", _zusatz(), {"sensor.einsp": (_null, None)}, {
        mx.JULI: {"einsp": 0.0, "ev": 60.0, "quote": 95.2, "autarkie": 73.5, "gv": 81.6, "ergebnis": 13.68},
        mx.JUNI: {"einsp": 0.0, "ev": 600.0, "ergebnis": 136.8},
    }),
    "volleinspeiser": ("F06", None, {"sensor.netz": (_null, None), "sensor.einsp": (_sonne(3.5), None)}, {
        mx.JULI: {"netz": 0.0, "einsp": 63.0, "ev": 0.0, "gv": 0.0, "ergebnis": 5.04},
        mx.JUNI: {"netz": 0.0, "einsp": 630.0, "gv": 0.0, "ergebnis": 50.4},
    }),
    "beide-0": ("F06", _zusatz(), {"sensor.netz": (_null, None), "sensor.einsp": (_null, None)}, {
        mx.JULI: {"netz": 0.0, "einsp": 0.0, "autarkie": 100.0, "gv": 60.0, "ergebnis": 20.16},
    }),
}


@pytest.mark.parametrize("fall", list(BILANZ))
async def test_bilanz_gemessene_null(fall):
    form_id, zusatz, abw, soll = BILANZ[fall]
    async with _Lauf(form_id, zusatz, abw) as (db, aid, _ids):
        for monat, felder in soll.items():
            b = _bilanz(await _monat(db, aid, monat))
            assert {k: b[k] for k in felder} == felder, (fall, monat, b)
            # Die Ergebnis-Leiter nennt keinen Posten als fehlend, der gemessen 0 ist — und der Rat
            # „Zähler zuordnen" erscheint nicht für einen Zähler, der zugeordnet ist und liefert.
            assert "Stromrechnung" not in b["fehlend"], (fall, monat, b)
            assert "Einspeise-Erlös" not in b["fehlend"], (fall, monat, b)
            assert not {"netzbezug_kwh", "einspeisung_kwh"} & set(b["gruende"]), (fall, monat, b)


# ── Gegenproben: ohne Messung bleibt None ──────────────────────────────────────────────────────────────────────────


async def test_nicht_zugeordnet_bleibt_none_mit_grund():
    """Netzbezug nicht zugeordnet: die Tagesebene trägt 72 Stunden ohne Wert — ohne ``erfasst`` wäre es 0 / 100 %."""
    async with _Lauf("F06", _zusatz(), ohne_basis=("netzbezug",)) as (db, aid, _ids):
        for monat in (mx.JULI, mx.JUNI):
            b = _bilanz(await _monat(db, aid, monat))
            assert (b["netz"], b["gv"], b["autarkie"], b["kosten"]) == (None, None, None, None), (monat, b)
            assert "netzbezug_kwh" in b["gruende"], (monat, b)


async def test_zugeordnet_ohne_zeilen_im_abgeschlossenen_monat_bleibt_none():
    """Netz-Sensor zugeordnet, aber ab Juni ohne Statistik-Zeilen — der ABGESCHLOSSENE Juni bleibt ohne Wert.

    (Im laufenden Juli liefert die Randstunde der Tagesebene 0,4 kWh — das ist eine andere Frage, Bauplan N-585.)
    """
    ab_juni = lambda t: t >= datetime(2026, 6, 1)  # noqa: E731
    async with _Lauf("F06", None, {"sensor.netz": (None, ab_juni)}) as (db, aid, _ids):
        b = _bilanz(await _monat(db, aid, mx.JUNI))
        assert (b["netz"], b["gv"], b["autarkie"]) == (None, None, None), b
        assert "netzbezug_kwh" in b["gruende"], b


async def test_eine_zeile_ohne_anker_ist_keine_messung():
    """Der Netz-Sensor hat überhaupt nur EINE Statistik-Zeile (03.07. 22:00) — sie misst kein Intervall."""
    async with _Lauf("F06", None, {"sensor.netz": (None, lambda t: t != datetime(2026, 7, 3, 22))},
                     tage=mx.TAGE_JULI) as (db, aid, _ids):
        import backend.services.ha_statistics_service as hss
        w = hss._ha_statistics_service.get_monatswerte(["sensor.netz"], mx.JAHR, mx.JULI).sensoren
        assert [(x.differenz, x.intervalle) for x in w] == [(0.0, 0)]
        b = _bilanz(await _monat(db, aid, mx.JULI))
        assert (b["netz"], b["gv"], b["autarkie"]) == (None, None, None), b


# ── Cockpit → Jahr ─────────────────────────────────────────────────────────────────────────────────────────────────


async def test_jahr_kopf_autarker_monat():
    from backend.services.jahres_aggregat import baue_jahr

    async with _Lauf("F06", _zusatz(), {"sensor.netz": (_null, None)}) as (db, aid, _ids):
        j = await baue_jahr(db, aid, mx.JAHR, heute=mx.JETZT.date())
        kopf = j["kopf"] if isinstance(j["kopf"], dict) else j["kopf"].model_dump()
        ist = {k: _r(kopf.get(k), 1 if k == "autarkie_prozent" else 2)
               for k in ("netzbezug_kwh", "gesamtverbrauch_kwh", "autarkie_prozent", "ergebnis_euro")}
        assert ist == {"netzbezug_kwh": 0.0, "gesamtverbrauch_kwh": 462.0, "autarkie_prozent": 100.0,
                       "ergebnis_euro": 178.2}, ist
        assert not any("Stromrechnung" in p for p in kopf.get("fehlende_posten") or []), kopf.get("fehlende_posten")


# ── Der Korb: Speicher · Balkonkraftwerk · Wallbox · Anlagen-PV-Zähler ─────────────────────────────────────────────

#: ``name: (form, zusatz, abweichung, {feld der Antwort: soll})`` — Juli laufend, Juni ohne Abschluss = × 10.
KORB = {
    "bkw-flach": ("F06", _zusatz(), {"sensor.pv_balkon": (_null, None)},
                  {"bkw_erzeugung_kwh": 0.0, "pv_erzeugung_kwh": 54.0}),
    "speicher-flach": ("F06", _zusatz(Akku=("speicher", {"kapazitaet_kwh": 10.0},
                                            {"ladung_kwh": _null, "entladung_kwh": _null})), {},
                       {"speicher_ladung_kwh": 0.0, "speicher_entladung_kwh": 0.0, "eigenverbrauch_kwh": 45.0}),
    "wallbox-flach": ("F06", _zusatz(Wallbox=("wallbox", None, {"ladung_kwh": _null})), {},
                      {"emob_ladung_kwh": 0.0}),
    "anlagenzaehler-flach-neben-einzelzaehlern": ("F02", _zusatz(), {"sensor.pv_gesamt": (_null, None)},
                                                  {"pv_erzeugung_kwh": 63.0}),
    "nur-anlagenzaehler-flach": ("F01", _zusatz(), {"sensor.pv_gesamt": (_null, None)},
                                 {"pv_erzeugung_kwh": 0.0}),
}


@pytest.mark.parametrize("fall", list(KORB))
async def test_korb_gemessene_null(fall):
    form_id, zusatz, abw, soll = KORB[fall]
    async with _Lauf(form_id, zusatz, abw) as (db, aid, _ids):
        for monat, mal in ((mx.JULI, 1), (mx.JUNI, 10)):
            d = await _monat(db, aid, monat)
            ist = {k: _r(d[k]) for k in soll}
            assert ist == {k: round(v * mal, 2) for k, v in soll.items()}, (fall, monat, ist)


# ── Wärmepumpe: eine gemessene 0 ist erfasst (HA-Bauform E4d, Bauplan §8a, Rest N-585) ──────────────────────────────


async def test_wp_kein_betrieb_strom_und_waerme_gemessen_null():
    """Strom 0 UND Wärme 0 gemessen: Mengen 0 (nicht leer), Arbeitszahl „—" mit dem Zeitraum-Grund der Kette (Stufe 3,
    „kein Heizbetrieb in diesem Zeitraum", Klasse Zeitraum), Ersparnis 0 €, die Ergebnis-Leiter führt die Zeile nicht
    als „fehlt" — im laufenden Monat und im Juni ohne Abschluss (Bauplan §8a)."""
    from backend.core.berechnungen.waermepumpe_kennzahl import GRUND_KEIN_HEIZBETRIEB, grund_klasse

    zusatz = _zusatz(WP=("waermepumpe", None, {"stromverbrauch_kwh": _null, "waerme_kwh": _null}))
    async with _Lauf("F06", zusatz) as (db, aid, _ids):
        for monat in (mx.JULI, mx.JUNI):
            d = await _monat(db, aid, monat)
            assert (d["wp_strom_kwh"], d["wp_waerme_kwh"]) == (0.0, 0.0), (monat, d["wp_strom_kwh"], d["wp_waerme_kwh"])
            assert d["wp_jaz"] is None and d["wp_jaz_grund"] == GRUND_KEIN_HEIZBETRIEB, (monat, d["wp_jaz_grund"])
            assert grund_klasse(d["wp_jaz_grund"]) == "zeitraum"
            assert d["wp_ersparnis_euro"] == 0.0, (monat, d["wp_ersparnis_euro"])
            assert not any("WP" in p for p in d["fehlende_posten"]), (monat, d["fehlende_posten"])


async def test_wp_kein_betrieb_je_geraet_und_im_abgeschlossenen_monat():
    """Dieselbe Regel je Gerät (Tabelle „Zahlen je Gerät": Zeile mit 0/0 und dem Zeitraum-Grund) und im Monat MIT
    Monatszeile (Strom 0 und Wärme 0 gespeichert): die T-Konto-Zeile nennt 0,00 €, nicht „fehlt"."""
    from backend.core.berechnungen.waermepumpe_kennzahl import GRUND_KEIN_HEIZBETRIEB
    from backend.models import InvestitionMonatsdaten

    zusatz = _zusatz(WP=("waermepumpe", None, {"stromverbrauch_kwh": _null, "waerme_kwh": _null}))
    async with _Lauf("F06", zusatz) as (db, aid, ids):
        d = await _monat(db, aid, mx.JULI)
        zeile = next(g for g in d["wp_geraete"] if g["investition_id"] == ids["WP"])
        assert (zeile["strom_kwh"], zeile["waerme_kwh"], zeile["jaz"], zeile["jaz_grund"]) == (
            0.0, 0.0, None, GRUND_KEIN_HEIZBETRIEB), zeile
        db.add(InvestitionMonatsdaten(investition_id=ids["WP"], jahr=mx.JAHR, monat=mx.JUNI,
                                      verbrauch_daten={"stromverbrauch_kwh": 0.0, "waerme_kwh": 0.0}))
        await db.commit()
        d = await _monat(db, aid, mx.JUNI)
        wp_zeile = next(f for f in d["investitionen_financials"] if f["typ"] == "waermepumpe")
        assert wp_zeile["ersparnis_euro"] == 0.0, wp_zeile
        assert (d["wp_strom_kwh"], d["wp_waerme_kwh"], d["wp_ersparnis_euro"]) == (0.0, 0.0, 0.0)
        assert not any("WP" in p for p in d["fehlende_posten"]), d["fehlende_posten"]


async def test_wp_kein_betrieb_im_jahr_uebersicht_und_cockpit_jahr():
    """H-4 (Entscheid Master, §8a gilt für alle Sichten): ein Jahr, dessen Monat mit Zeile Strom 0 und Wärme 0 trägt,
    nennt in der Übersicht und in Cockpit → Jahr den Zeitraum-Grund wie Cockpit → Monat — ohne Zeile („nicht
    erfasst") bleibt es bei Stufe 1."""
    from backend.api.routes.cockpit.uebersicht import get_cockpit_uebersicht
    from backend.core.berechnungen.waermepumpe_kennzahl import GRUND_KEIN_HEIZBETRIEB, GRUND_KEIN_STROM
    from backend.models import InvestitionMonatsdaten
    from backend.services.jahres_aggregat import baue_jahr

    zusatz = _zusatz(WP=("waermepumpe", None, {"stromverbrauch_kwh": _null, "waerme_kwh": _null}))
    async with _Lauf("F06", zusatz) as (db, aid, ids):
        u = await get_cockpit_uebersicht(anlage_id=aid, jahr=mx.JAHR, db=db)
        assert (u.wp_cop, u.wp_cop_grund) == (None, GRUND_KEIN_STROM)        # ohne Zeile: nicht erfasst
        db.add(InvestitionMonatsdaten(investition_id=ids["WP"], jahr=mx.JAHR, monat=mx.JUNI,
                                      verbrauch_daten={"stromverbrauch_kwh": 0.0, "waerme_kwh": 0.0}))
        await db.commit()
        u = await get_cockpit_uebersicht(anlage_id=aid, jahr=mx.JAHR, db=db)
        assert (u.wp_cop, u.wp_cop_grund) == (None, GRUND_KEIN_HEIZBETRIEB)
        j = await baue_jahr(db, aid, mx.JAHR, heute=mx.JETZT.date())
        kopf = j["kopf"] if isinstance(j["kopf"], dict) else j["kopf"].model_dump()
        assert (kopf["wp_jaz"], kopf["wp_jaz_grund"]) == (None, GRUND_KEIN_HEIZBETRIEB), kopf["wp_jaz_grund"]


def test_wp_strom_null_ohne_waerme_layer():
    """Gegenfall (Bauplan §8a, Nachtrag aus der Nachmessung E4d) am Layer: Strom GEMESSEN 0 und Wärme NICHT erfasst ⇒
    Stufe 5 „kein Wärmemengenzähler zugeordnet" (bzw. der Wärme-Grund des Aufrufers) — Stufe 1 trifft nur den nicht
    erfassten Strom."""
    from backend.core.berechnungen.waermepumpe_kennzahl import (
        GRUND_KEIN_HEIZBETRIEB, GRUND_KEIN_STROM, GRUND_KEINE_WAERMEMESSUNG, arbeitszahl, grund_klasse, systemarbeitszahl,
    )

    assert systemarbeitszahl(None, 0.0).grund == GRUND_KEINE_WAERMEMESSUNG
    assert systemarbeitszahl(None, 0.0, waerme_fehlt_grund="Zählerrücksprung").grund == "Zählerrücksprung"
    assert grund_klasse(GRUND_KEINE_WAERMEMESSUNG) == "ausstattung"
    # Gegenproben: Strom nicht erfasst bleibt Stufe 1, beide gemessen 0 bleibt Stufe 3, Wärme > 0 bleibt Stufe 1 (H-2)
    assert systemarbeitszahl(None, None).grund == GRUND_KEIN_STROM
    assert systemarbeitszahl(0.0, 0.0, kein_betrieb_grund=GRUND_KEIN_HEIZBETRIEB).grund == GRUND_KEIN_HEIZBETRIEB
    assert systemarbeitszahl(100.0, 0.0, kein_betrieb_grund=GRUND_KEIN_HEIZBETRIEB).grund == GRUND_KEIN_STROM
    # arbeitszahl (je Gerät, je Funktion): mit dem Riegel des Aufrufers (kein_betrieb_grund)
    assert arbeitszahl(None, 0.0, kein_betrieb_grund=GRUND_KEIN_HEIZBETRIEB).grund == GRUND_KEINE_WAERMEMESSUNG
    assert arbeitszahl(0.0, 0.0, kein_betrieb_grund=GRUND_KEIN_HEIZBETRIEB,
                       waerme_fehlt_grund="kein Wert für diesen Tag").grund == "kein Wert für diesen Tag"
    assert arbeitszahl(0.0, 0.0, kein_betrieb_grund=GRUND_KEIN_HEIZBETRIEB).grund == GRUND_KEIN_HEIZBETRIEB
    assert arbeitszahl(None, 0.0).grund == GRUND_KEIN_STROM


async def test_wp_strom_null_ohne_waermezaehler_monat_geraet_und_jahr():
    """Gegenfall in den Sichten: eine Wärmepumpe mit Stromzähler (gemessen 0) und OHNE Wärmemengenzähler nennt in
    Cockpit → Monat (laufend und Juni ohne Abschluss), in der Übersicht und im Kopf von Cockpit → Jahr „kein
    Wärmemengenzähler zugeordnet" — vorher „kein Stromverbrauch erfasst". (Die Tabelle „Zahlen je Gerät" führt ein Gerät
    ohne Menge über 0 nur bei „kein Betrieb" — unverändert; die Geräte-Kennzahl prüft die Probe darunter.)"""
    from backend.api.routes.cockpit.uebersicht import get_cockpit_uebersicht
    from backend.core.berechnungen.waermepumpe_kennzahl import GRUND_KEINE_WAERMEMESSUNG
    from backend.models import InvestitionMonatsdaten
    from backend.services.jahres_aggregat import baue_jahr

    zusatz = _zusatz(WP=("waermepumpe", None, {"stromverbrauch_kwh": _null}))
    async with _Lauf("F06", zusatz) as (db, aid, ids):
        for monat in (mx.JULI, mx.JUNI):
            d = await _monat(db, aid, monat)
            assert (d["wp_strom_kwh"], d["wp_waerme_kwh"]) == (0.0, None), (monat, d["wp_strom_kwh"], d["wp_waerme_kwh"])
            assert (d["wp_jaz"], d["wp_jaz_grund"]) == (None, GRUND_KEINE_WAERMEMESSUNG), (monat, d["wp_jaz_grund"])
        db.add(InvestitionMonatsdaten(investition_id=ids["WP"], jahr=mx.JAHR, monat=mx.JUNI,
                                      verbrauch_daten={"stromverbrauch_kwh": 0.0}))
        await db.commit()
        u = await get_cockpit_uebersicht(anlage_id=aid, jahr=mx.JAHR, db=db)
        assert (u.wp_cop, u.wp_cop_grund) == (None, GRUND_KEINE_WAERMEMESSUNG)
        j = await baue_jahr(db, aid, mx.JAHR, heute=mx.JETZT.date())
        kopf = j["kopf"] if isinstance(j["kopf"], dict) else j["kopf"].model_dump()
        assert (kopf["wp_jaz"], kopf["wp_jaz_grund"]) == (None, GRUND_KEINE_WAERMEMESSUNG), kopf["wp_jaz_grund"]


def test_wp_strom_null_ohne_waerme_je_geraet():
    """Gegenfall je Gerät (`kennzahlen_aus_mengen`, die eine Rechenstelle für Hub, Tabelle und Monat): Strom gemessen 0,
    Wärme nicht erfasst ⇒ „kein Wärmemengenzähler zugeordnet"; beide gemessen 0 ⇒ „kein Heizbetrieb …"; ohne Marke
    bleibt Stufe 1."""
    from backend.core.berechnungen.waermepumpe_kennzahl import (
        GRUND_KEIN_HEIZBETRIEB, GRUND_KEIN_STROM, GRUND_KEINE_WAERMEMESSUNG,
    )
    from backend.services.waermepumpe_kennzahlen_je_geraet import GeraetMengen, kennzahlen_aus_mengen

    def _g(**kw):
        return kennzahlen_aus_mengen(GeraetMengen(inv_id=1, name="WP", **kw)).gesamt.grund

    assert _g(strom_gemessen=True) == GRUND_KEINE_WAERMEMESSUNG
    assert _g(strom_gemessen=True, waerme_gemessen=True) == GRUND_KEIN_HEIZBETRIEB
    assert _g() == GRUND_KEIN_STROM
    assert _g(waerme_gemessen=True) == GRUND_KEIN_STROM


async def test_halteprobe_wp_strom_flach_bei_waerme():
    """WP-Strom gemessen 0 bei gemessener Wärme: die 0 ist erfasst (F-5, Bauplan §8a) und wird gezeigt — eine Ersparnis
    entsteht nicht (die eine Zeilenregel `wp_ersparnis_zeile`: Strom > 0 und Wärme > 0).

    ⚑ **Halteprobe, kein Soll:** für Strom 0 bei Wärme > 0 (physikalisch eine fehlerhafte Messung) gibt es keine
    Darstellungsregel — §8a regelt nur Strom 0 UND Wärme 0. Bis E4d stand hier `wp_strom_kwh is None` (vor N-609
    entstand über den damaligen Aggregat-Zweig zusätzlich eine Phantom-Ersparnis von 8,64 / 86,40 €). Offen im
    Bericht E4d; der Grund der Arbeitszahl bleibt Stufe 1 („kein Stromverbrauch erfasst")."""
    zusatz = _zusatz(WP=("waermepumpe", None, {"stromverbrauch_kwh": _null, "waerme_kwh": lambda t: 0.9}))
    async with _Lauf("F06", zusatz) as (db, aid, _ids):
        for monat in (mx.JULI, mx.JUNI):
            d = await _monat(db, aid, monat)
            assert d["wp_strom_kwh"] == 0.0, (monat, d["wp_strom_kwh"])
            assert d["wp_ersparnis_euro"] is None, (monat, d["wp_ersparnis_euro"])


async def test_halteprobe_string_flach_neben_anlagenzaehler():
    """Ein String gemessen 0 neben dem Anlagenzähler nimmt ihm nicht seinen Rest (PV bleibt 63, nicht 27)."""
    async with _Lauf("F02", _zusatz(), {"sensor.pv_sued": (_null, None)}) as (db, aid, _ids):
        d = await _monat(db, aid, mx.JULI)
        assert _r(d["pv_erzeugung_kwh"]) == 63.0, d["pv_erzeugung_kwh"]


# ── Standalone: Tagesebene aus Zählerständen, kein HA ──────────────────────────────────────────────────────────────


@pytest.mark.parametrize("fall,soll", [
    ("netzbezug-0", {"netz": 0.0, "autarkie": 100.0, "ergebnis": 14.94}),
    ("nicht-zugeordnet", {"netz": None, "gv": None, "autarkie": None}),
    ("zugeordnet-ohne-staende", {"netz": None, "gv": None, "autarkie": None}),
])
async def test_standalone_tagesebene(fall, soll):
    form = mx.FORMEN["F06"]
    echte = mx._reihen

    def reihen(f):
        r = dict(echte(f))
        if fall == "netzbezug-0":
            r["sensor.netz"] = (_null, r["sensor.netz"][1], r["sensor.netz"][2])
        else:
            r.pop("sensor.netz")
        return r

    verz = tempfile.mkdtemp(prefix="eedc-n585-sa-")
    try:
        engine, db = await mx._neue_db(f"{verz}/sa.db")
        try:
            aid, ids = await mx.seed_anlage(db, form)
            if fall == "nicht-zugeordnet":
                a = (await db.execute(select(Anlage).where(Anlage.id == aid))).scalar_one()
                m = dict(a.sensor_mapping)
                m["basis"] = {k: v for k, v in m["basis"].items() if k != "netzbezug"}
                a.sensor_mapping = m
                flag_modified(a, "sensor_mapping")
                await db.commit()
            with patch.object(mx, "_reihen", reihen):
                await mx.seed_snapshots(db, form, aid, ids)
            with mx._umgebung(mx._ha_aus()):
                await mx.aggregiere_tage(db, form, aid, mx.TAGE_JULI)
                b = _bilanz(await _monat(db, aid, mx.JULI))
            assert {k: b[k] for k in soll} == soll, (fall, b)
            if soll["netz"] is None:
                assert "netzbezug_kwh" in b["gruende"], (fall, b)
            else:
                assert "Stromrechnung" not in b["fehlend"] and "netzbezug_kwh" not in b["gruende"], (fall, b)
        finally:
            await db.close()
            await engine.dispose()
    finally:
        shutil.rmtree(verz, ignore_errors=True)
