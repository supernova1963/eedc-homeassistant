"""HA-Bauform E4f (Auftrag Punkt 3a): der Lade-Kontext je Anfrage (``services/kanal/lade_kontext.py``).

Vier Zusagen:

1. **Er ändert keine Zahl.** Die fünf Routen der Laufzeit-Grundlinie (Übersicht ohne Jahr, Cockpit → Jahr, Jahr-Liste,
   Tabelle, CO₂) und Cockpit → Monat nennen MIT dem Kontext dasselbe wie ohne ihn — an Datenständen beider
   Abnahme-Matrizen mit Kanälen aller Gruppen (Bilanz, E-Mob, Sonstiges, Wärmepumpe, Preis).
2. **Er lädt je Anfrage einmal.** Ein zweiter Fakten-Aufruf derselben Anfrage fragt ``kanal_statistik`` nicht mehr;
   die Zahl der Anweisungen gegen ``kanal_statistik`` hängt an den Gruppen, nicht an Monaten oder Stunden (Abfrage-Budget).
3. **Schreiben leert ihn**, und er überdauert die Anfrage nie (dieselbe Sitzung in einer zweiten Anfrage sieht, was
   inzwischen geschrieben wurde).
4. **Nur GET-Anfragen** bekommen ihn (Middleware ``kanal_lade_kontext``).

Schwesterdateien: test_query_budget_monats_fakten.py (Abfrage-Budget der Stundentabelle), test_kanal_kosten_gleichheit.py
(Zeitfenster-Gewichte je Zelle), test_e4f_kalendermonat_emob_sonstiges.py, test_e4f_nachlauf_nur_fehlende_tage.py.
"""

from __future__ import annotations

import dataclasses
from datetime import date, datetime

import pytest
from sqlalchemy import event, select, text

from backend.services.kanal.lade_kontext import kontext, lese_anfrage
from backend.tests import achsen_matrix as am
from backend.tests import kanal_bilanz_gleichheit as kg
from backend.tests import pv_achse_matrix as mx

#: Formen mit Kanälen in jeder Gruppe: Wallbox (abgeleiteter Anteil) + Speicher · Wärmepumpe mit Etikett (Strom je
#: Betriebsart) · Flex-Tarif mit Preissensor (Kosten-Kanäle) · BHKW + Sonstiges-Verbraucher am BKW · Dienstwagen ·
#: PV mit Strings, BKW und Kindern.
FAELLE = [("achsen", "M02"), ("achsen", "M05"), ("achsen", "M04"), ("achsen", "M10"), ("achsen", "M09"),
          ("pv", "F09a-G")]


def _dump(x):
    if hasattr(x, "model_dump"):
        return _dump(x.model_dump(mode="json"))
    if dataclasses.is_dataclass(x) and not isinstance(x, type):
        return _dump(dataclasses.asdict(x))
    if isinstance(x, dict):
        return {str(k): _dump(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [_dump(v) for v in x]
    return x


async def _routen(db, aid) -> dict:
    from backend.api.routes.aktueller_monat import get_aktueller_monat
    from backend.api.routes.cockpit.jahr import get_cockpit_jahr
    from backend.api.routes.cockpit.nachhaltigkeit import get_nachhaltigkeit
    from backend.api.routes.cockpit.uebersicht import get_cockpit_uebersicht
    from backend.api.routes.monatsdaten import list_monatsdaten_aggregiert

    return {
        "uebersicht": _dump(await get_cockpit_uebersicht(anlage_id=aid, jahr=None, db=db)),
        "jahr": _dump(await get_cockpit_jahr(anlage_id=aid, jahr=2026, db=db)),
        "jahr_liste": _dump(await list_monatsdaten_aggregiert(
            anlage_id=aid, jahr=None, inkl_ohne_zaehlerzeile=True, inkl_nur_tageswerte=True, db=db)),
        "tabelle": _dump(await list_monatsdaten_aggregiert(
            anlage_id=aid, jahr=None, inkl_ohne_zaehlerzeile=False, inkl_nur_tageswerte=False, db=db)),
        "co2": _dump(await get_nachhaltigkeit(anlage_id=aid, db=db)),
        "monat_juli": _dump(await get_aktueller_monat(anlage_id=aid, jahr=2026, monat=7, db=db)),
    }


def _umgebung(matrix, fid, svc):
    return am.umgebung(am.MATRIX_FORMEN[fid], svc) if matrix == "achsen" else mx._umgebung(svc)


class _Zaehler:
    def __init__(self):
        self.kanal = 0
        self.alle = 0
        self.sql: list[str] = []

    def __call__(self, conn, cursor, statement, parameters, context, executemany):
        self.alle += 1
        self.sql.append(statement)
        if "kanal_statistik" in statement:
            self.kanal += 1


@pytest.mark.parametrize("matrix, fid", FAELLE)
async def test_mit_und_ohne_kontext_dieselben_zahlen(matrix, fid):
    async with kg.datenstand(matrix, fid, "HA") as ds:
        with _umgebung(matrix, fid, ds.svc):
            ohne = await _routen(ds.db, ds.aid)
            with lese_anfrage():
                assert kontext(ds.db) is not None
                mit = await _routen(ds.db, ds.aid)
            assert kontext(ds.db) is None
    for sicht in ohne:
        assert mit[sicht] == ohne[sicht], sicht


async def test_der_zweite_fakten_aufruf_einer_anfrage_fragt_die_kanaele_nicht_mehr():
    from backend.services.monats_fakten import lade_monats_fakten

    async with kg.datenstand("achsen", "M02", "HA") as ds:
        z = _Zaehler()
        with am.umgebung(am.MATRIX_FORMEN["M02"], ds.svc):
            event.listen(ds.db.bind.sync_engine, "before_cursor_execute", z)
            try:
                with lese_anfrage():
                    erster = await lade_monats_fakten(ds.db, ds.aid, inkl_nur_tageswerte=True)
                    nach_erstem = z.kanal
                    rand_erster = sum(1 for q in z.sql if "g(j, t) AS" in q)
                    zweiter = await lade_monats_fakten(ds.db, ds.aid, inkl_nur_tageswerte=True)
                    nach_zweitem = z.kanal
                ohne_vorher = z.kanal
                await lade_monats_fakten(ds.db, ds.aid, inkl_nur_tageswerte=True)
                ohne = z.kanal - ohne_vorher
            finally:
                event.remove(ds.db.bind.sync_engine, "before_cursor_execute", z)
    assert _dump(erster) == _dump(zweiter)
    assert nach_erstem > 0
    assert 1 <= rand_erster <= 4, f"höchstens eine Randstände-Anweisung je Gruppe, gemessen {rand_erster}"
    assert nach_zweitem == nach_erstem, f"der zweite Aufruf fragte {nach_zweitem - nach_erstem}× kanal_statistik"
    assert nach_erstem <= ohne, f"ohne Kontext {ohne}, im ersten Aufruf mit Kontext {nach_erstem}"


async def test_ein_weiteres_fenster_liest_nur_die_raender_die_die_anfrage_noch_nicht_kennt():
    """Die Monatsreihe je Anfrage einmal: ein Randstand hängt nur an Kanal und Zeitpunkt. Liest die Anfrage erst Juni
    und dann Juni + Juli, fragt der zweite Aufruf nur den einen neuen Zeitpunkt (das Ende des Juli) — und das Ergebnis
    für Juni ist dasselbe."""
    import json

    from backend.services.kanal.bilanz_leser import monate_bilanz
    from backend.services.kanal.fenster import monatsfenster

    async with kg.datenstand("achsen", "M01", "HA") as ds:
        params = []

        def _mit(conn, cursor, statement, parameters, context, executemany):
            if "g(j, t) AS" in statement:
                params.append(parameters)

        with am.umgebung(am.MATRIX_FORMEN["M01"], ds.svc):
            event.listen(ds.db.bind.sync_engine, "before_cursor_execute", _mit)
            try:
                with lese_anfrage():
                    juni = await monate_bilanz(ds.db, ds.aid, (2026, 6), (2026, 6))
                    beide = await monate_bilanz(ds.db, ds.aid, (2026, 6), (2026, 7))
            finally:
                event.remove(ds.db.bind.sync_engine, "before_cursor_execute", _mit)
    assert len(params) == 2, len(params)
    zweite = json.loads(params[1][1] if isinstance(params[1], (list, tuple)) else params[1]["grenzen"])
    assert monatsfenster(2026, 6)[0] not in zweite and monatsfenster(2026, 6)[1] not in zweite, zweite
    assert beide[(2026, 6)].komposition.bilanz == juni[(2026, 6)].komposition.bilanz


async def test_schreiben_leert_den_kontext():
    """Ein ``execute`` ohne SELECT (der Konsistenzlauf, eine Korrektur) in derselben Sitzung: das nächste Lesen sieht
    die neue Zahl. Ebenso ``commit``."""
    from backend.services.kanal.bilanz_leser import monate_bilanz

    async with kg.datenstand("achsen", "M01", "HA") as ds:
        with am.umgebung(am.MATRIX_FORMEN["M01"], ds.svc):
            with lese_anfrage():
                vorher = (await monate_bilanz(ds.db, ds.aid, (2026, 6), (2026, 6)))[(2026, 6)]
                await ds.db.execute(text(
                    "UPDATE kanal_statistik SET sum = sum + 5, state = state + 5 WHERE start_ts >= :t AND kanal_id = "
                    "(SELECT id FROM kanal WHERE anlage_id = :a AND key = 'basis:einspeisung')"),
                    {"t": int(datetime(2026, 6, 15, 12).timestamp()), "a": ds.aid})
                nachher = (await monate_bilanz(ds.db, ds.aid, (2026, 6), (2026, 6)))[(2026, 6)]
                await ds.db.commit()
                nach_commit = (await monate_bilanz(ds.db, ds.aid, (2026, 6), (2026, 6)))[(2026, 6)]
    e0 = vorher.komposition.bilanz.einspeisung_kwh
    assert nachher.komposition.bilanz.einspeisung_kwh == pytest.approx(e0 + 5)
    assert nach_commit.komposition.bilanz.einspeisung_kwh == pytest.approx(e0 + 5)


async def test_der_kontext_ueberdauert_die_anfrage_nicht():
    """Dieselbe Sitzung in einer zweiten Anfrage; geschrieben hat dazwischen eine ANDERE Verbindung (der Stundenlauf)
    — die zweite Anfrage sieht es."""
    import sqlite3

    from backend.services.kanal.bilanz_leser import monate_bilanz

    async with kg.datenstand("achsen", "M01", "HA") as ds:
        pfad = ds.db.bind.url.database
        with am.umgebung(am.MATRIX_FORMEN["M01"], ds.svc):
            with lese_anfrage():
                vorher = (await monate_bilanz(ds.db, ds.aid, (2026, 6), (2026, 6)))[(2026, 6)]
            await ds.db.rollback()          # die Lese-Transaktion endet mit der Anfrage
            con = sqlite3.connect(pfad)
            con.execute("UPDATE kanal_statistik SET sum = sum + 7, state = state + 7 WHERE start_ts >= ? AND kanal_id = "
                        "(SELECT id FROM kanal WHERE anlage_id = ? AND key = 'basis:einspeisung')",
                        (int(datetime(2026, 6, 15, 12).timestamp()), ds.aid))
            con.commit()
            con.close()
            with lese_anfrage():
                nachher = (await monate_bilanz(ds.db, ds.aid, (2026, 6), (2026, 6)))[(2026, 6)]
    assert nachher.komposition.bilanz.einspeisung_kwh == pytest.approx(
        vorher.komposition.bilanz.einspeisung_kwh + 7)


async def test_commit_in_derselben_anfrage_leert_den_kontext():
    """Innerhalb EINER Anfrage: gelesen, Transaktion beendet (``rollback``), eine andere Verbindung schreibt — das nächste
    Lesen derselben Anfrage sieht es (``after_rollback``/``after_commit`` leeren)."""
    import sqlite3

    from backend.services.kanal.bilanz_leser import monate_bilanz

    async with kg.datenstand("achsen", "M01", "HA") as ds:
        pfad = ds.db.bind.url.database
        with am.umgebung(am.MATRIX_FORMEN["M01"], ds.svc):
            with lese_anfrage():
                vorher = (await monate_bilanz(ds.db, ds.aid, (2026, 6), (2026, 6)))[(2026, 6)]
                await ds.db.rollback()
                con = sqlite3.connect(pfad)
                con.execute("UPDATE kanal_statistik SET sum = sum + 3, state = state + 3 WHERE start_ts >= ? AND "
                            "kanal_id = (SELECT id FROM kanal WHERE anlage_id = ? AND key = 'basis:einspeisung')",
                            (int(datetime(2026, 6, 15, 12).timestamp()), ds.aid))
                con.commit()
                con.close()
                nachher = (await monate_bilanz(ds.db, ds.aid, (2026, 6), (2026, 6)))[(2026, 6)]
    assert nachher.komposition.bilanz.einspeisung_kwh == pytest.approx(
        vorher.komposition.bilanz.einspeisung_kwh + 3)


async def test_eine_neue_anfrage_uebernimmt_nichts_aus_der_vorigen(db):
    with lese_anfrage():
        kontext(db).werte["marke"] = 1
    with lese_anfrage():
        assert "marke" not in kontext(db).werte


async def test_ein_ergebnis_das_ein_schreiben_ueberholt_wird_nicht_gehalten(db):
    from backend.services.kanal.lade_kontext import gemerkt

    laeufe = []

    async def _fabrik():
        laeufe.append(1)
        kontext(db).leeren()          # „währenddessen wurde geschrieben"
        return len(laeufe)

    with lese_anfrage():
        assert await gemerkt(db, "x", _fabrik) == 1
        assert await gemerkt(db, "x", _fabrik) == 2


async def test_die_uhr_steht_in_der_anfrage_still():
    from backend.services.kanal.lade_kontext import uhr_der_anfrage

    ticks = iter(range(1000, 2000))
    with lese_anfrage():
        a = uhr_der_anfrage(lambda: next(ticks))
        b = uhr_der_anfrage(lambda: next(ticks))
    c = uhr_der_anfrage(lambda: next(ticks))
    assert a == b == 1000 and c == 1001


@pytest.mark.parametrize("methode, erwartet", [("GET", True), ("POST", False), ("PUT", False), ("DELETE", False)])
async def test_nur_get_anfragen_bekommen_den_kontext(methode, erwartet):
    from starlette.requests import Request

    from backend.main import kanal_lade_kontext
    from backend.services.kanal import lade_kontext as lk

    gesehen = []

    async def call_next(_req):
        gesehen.append(lk._ANFRAGE.get() is not None)
        return "antwort"

    req = Request({"type": "http", "method": methode, "path": "/api/x", "headers": [], "query_string": b""})
    assert await kanal_lade_kontext(req, call_next) == "antwort"
    assert gesehen == [erwartet]
    assert lk._ANFRAGE.get() is None


# ── Abfrage-Budget: Anweisungen je Route ∝ Gruppen, nicht ∝ Monate oder Stunden ──────────────────────────────────


async def _anlage_mit_kanaelen(db, monate: int) -> int:
    """Netz-Zähler als Spiegel über ``monate`` Monate (jede Stunde eine Zeile), dazu je Monat eine Zählerzeile."""
    from backend.models import Anlage
    from backend.models.kanal import Kanal, KanalQuelle
    from backend.models.monatsdaten import Monatsdaten

    a = Anlage(anlagenname="Budget-Kanal", leistung_kwp=10.0)
    db.add(a)
    await db.flush()
    a.sensor_mapping = {"basis": {"einspeisung": {"strategie": "sensor", "sensor_id": "sensor.e"},
                                  "netzbezug": {"strategie": "sensor", "sensor_id": "sensor.n"}}, "investitionen": {}}
    von = int(datetime(2023, 1, 1).timestamp()) - 3600
    j, m = 2023, 1
    for _ in range(monate):
        db.add(Monatsdaten(anlage_id=a.id, jahr=j, monat=m, einspeisung_kwh=100.0, netzbezug_kwh=200.0))
        j, m = (j + 1, 1) if m == 12 else (j, m + 1)
    bis = int(datetime(j, m, 1).timestamp())
    for key, sid in (("basis:einspeisung", "sensor.e"), ("basis:netzbezug", "sensor.n")):
        k = Kanal(anlage_id=a.id, key=key, einheit="kWh", art="sum")
        db.add(k)
        await db.flush()
        db.add(KanalQuelle(kanal_id=k.id, gueltig_ab=von - 3600, familie="spiegel", statistic_id=sid, offset=0.0))
        await db.flush()
        await db.execute(text(
            "WITH RECURSIVE h(i) AS (SELECT 0 UNION ALL SELECT i + 1 FROM h WHERE i < :n) "
            "INSERT INTO kanal_statistik (kanal_id, start_ts, sum, state, familie) "
            "SELECT :kid, :von + i * 3600, i * 0.5, i * 0.5, 'spiegel' FROM h"),
            {"n": (bis - von) // 3600, "kid": k.id, "von": von})
    await db.flush()
    return a.id


#: Die Übersicht liest an dieser Anlage keine Kanäle (ohne Wallbox lädt sie die Tagesebene nicht) — sie steht deshalb
#: nicht hier; ihr Budget misst die Laufzeit-Zählung (Bericht E4f, Etappe Laufzeit).
@pytest.mark.parametrize("routen_name", ["fakten", "tabelle"])
async def test_abfrage_budget_waechst_nicht_mit_monaten_oder_stunden(db, routen_name):
    from backend.api.routes.monatsdaten import list_monatsdaten_aggregiert
    from backend.services.monats_fakten import lade_monats_fakten

    async def _lauf(aid):
        if routen_name == "fakten":
            return await lade_monats_fakten(db, aid, inkl_nur_tageswerte=True)
        return await list_monatsdaten_aggregiert(anlage_id=aid, jahr=None, inkl_ohne_zaehlerzeile=True,
                                                 inkl_nur_tageswerte=True, db=db)

    zahlen = {}
    for monate in (12, 24):
        aid = await _anlage_mit_kanaelen(db, monate)
        await db.commit()
        z = _Zaehler()
        event.listen(db.bind.sync_engine, "before_cursor_execute", z)
        try:
            with lese_anfrage():
                await _lauf(aid)
        finally:
            event.remove(db.bind.sync_engine, "before_cursor_execute", z)
        zahlen[monate] = (z.kanal, z.alle)
    assert zahlen[12][0] > 0, f"die Probe muss die Kanäle überhaupt lesen: {zahlen}"
    assert zahlen[12][0] == zahlen[24][0], f"Anweisungen gegen kanal_statistik: {zahlen}"
    assert zahlen[24][1] <= zahlen[12][1] + 24, (
        f"alle Anweisungen: {zahlen} — höchstens eine je zusätzlichem Monat, nie eine je Stunde")


async def test_zeitfenster_gewichte_aller_monate_einer_anfrage_in_einer_anweisung():
    """Auftrag Punkt 3b: im Lade-Kontext holt der erste Abruf die Netzbezugs-Gewichte ALLER vorgemerkten Monate in
    EINER Anweisung; der Preis je Monat ist derselbe wie ohne Kontext (je Monat geladen) — auch mit Wochentag-Maske
    (Mo–Fr 08–11 Uhr, schneidet den Sonnenbeginn)."""
    from backend.models.strompreis import Strompreis, StrompreisZeitfenster
    from backend.services import strompreis_aggregator as sa
    from backend.services.kanal import preis_leser

    async with kg.datenstand("achsen", "M01", "HA") as ds:
        tarif = (await ds.db.execute(select(Strompreis).where(Strompreis.anlage_id == ds.aid))).scalar_one()
        ds.db.add(StrompreisZeitfenster(strompreis_id=tarif.id, von_stunde=8, bis_stunde=11, wochentage="01234",
                                        arbeitspreis_cent_kwh=20.0))
        await ds.db.commit()
        ds.db.expire_all()
        tarif = (await ds.db.execute(select(Strompreis).where(Strompreis.anlage_id == ds.aid))).scalar_one()
        z = _Zaehler()
        with am.umgebung(am.MATRIX_FORMEN["M01"], ds.svc):
            ohne = {m: await sa.wirksamer_arbeitspreis_cent(ds.db, ds.aid, 2026, m, tarif) for m in (6, 7)}
            event.listen(ds.db.bind.sync_engine, "before_cursor_execute", z)
            try:
                with lese_anfrage():
                    preis_leser.netzbezug_vormerken(ds.db, ds.aid, [(2026, 6), (2026, 7)])
                    mit = {m: await sa.wirksamer_arbeitspreis_cent(ds.db, ds.aid, 2026, m, tarif) for m in (6, 7)}
            finally:
                event.remove(ds.db.bind.sync_engine, "before_cursor_execute", z)
    zellen_anweisungen = [q for q in z.sql if "strftime('%w'" in q]
    assert mit == ohne and all(20.0 < p < 30.0 for p in mit.values()), (mit, ohne)
    assert len(zellen_anweisungen) == 1, len(zellen_anweisungen)
