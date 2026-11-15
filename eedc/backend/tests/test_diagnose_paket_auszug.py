"""Auszug des Diagnose-Pakets v4 — Speicherform (G1), Blatt-Regel (G2, W-7 b), Unlesbares (K3), eine Anlage (W-7 d), Q1/Q3/Q5.

Fixture ``voll_datei_db``: Datei-Datenbank (``create_all`` + ``MIGRATIONS_DDL``) mit **zwei** Anlagen; je ausgezogene Tabelle
(aus dem Register iteriert) eine Zeile je Anlagen-Kette, dazu die Speicherformen der Rundreise: Mikrosekunden-Zeit, bool,
Text-``null`` und SQL-NULL in derselben Spalte, JSON-Zahl (NUMERIC-Affinität), Umlaut, doppelte Schlüssel, abgeschnittenes
JSON; ``connector_config``/``sensor_mapping``/``parameter``/``details_json``/``source_provenance`` mit allen Formen der
Allowlist und Geheimnissen; Provenance mit ``__row__``, ``{"id": …}`` und Anlage 10. Zeilen werden roh per ``sqlite3``
geschrieben (die Speicherform steht so, wie sie in der Datei liegt). Keine Probe liest die Uhr.

Schwesterdateien: test_diagnose_paket.py, test_diagnose_paket_register.py, test_diagnose_paket_ha_abgleich.py.
"""
from __future__ import annotations

import importlib
import io
import json
import pkgutil
import re
import sqlite3
import zipfile
from contextlib import asynccontextmanager
from dataclasses import replace
from pathlib import Path

import pytest
from sqlalchemy import JSON, Boolean, Date, DateTime, Float, Integer, create_engine
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import backend.models as _models
from backend.core.database import Base
from backend.services.diagnose_paket import auszug as az
from backend.services.diagnose_paket import register as reg
from backend.services.diagnose_paket.bereinigung import MARKE_RE, Sammler, filtere_json

for _m in pkgutil.iter_modules(_models.__path__):
    importlib.import_module(f"backend.models.{_m.name}")

#: Erwartete Spalten je Tabelle zum Zeitpunkt des Imports (Sprengsatz «rein → raus» verändert das Register zur Laufzeit).
ERWARTET = {t: [s for s, sp in tab.spalten.items() if sp.klasse != "raus"] for t, tab in reg.REGISTER.items()}
ZEIT_MIKRO = "2026-10-03 14:05:06.123456"
SPRENG = "SPRENGSATZ"
#: Einwertung Master S1: eine fremde Oberschlüssel-Zahl bleibt nur in `investitionen.parameter` stehen.
FREMDE_ZAHL = 987654321012
PARAMETER_ZAHL = 987654321013

#: Ketten-IDs je Anlage a ∈ {1, 2}: Gerät 10+a, Kanal 20+a, Tarif 30+a, PVGIS 40+a, sonstige Zeilen 100·a + n.
EIGENE_ID = {"anlagen": lambda a: a, "investitionen": lambda a: 10 + a, "kanal": lambda a: 20 + a,
             "strompreise": lambda a: 30 + a, "pvgis_prognosen": lambda a: 40 + a}
#: Fremdschlüssel → Kette.
KETTE = {"anlage_id": lambda a: a, "investition_id": lambda a: 10 + a, "kanal_id": lambda a: 20 + a,
         "strompreis_id": lambda a: 30 + a, "prognose_id": lambda a: 40 + a, "parent_investition_id": lambda a: None}


def _platzhalter(spalte) -> object:
    typ = spalte.type
    if isinstance(typ, JSON):
        return None if spalte.nullable else "{}"
    if isinstance(typ, Boolean):
        return 1
    if isinstance(typ, Integer):
        return 7
    if isinstance(typ, Float):
        return 1.5
    if isinstance(typ, DateTime):
        return ZEIT_MIKRO
    if isinstance(typ, Date):
        return "2026-10-03"
    return "Wärme"


def _zeile(t: str, a: int, n: int = 0, **werte) -> dict:
    """Eine vollständige Zeile der Tabelle ``t`` für Anlage ``a`` (Platzhalter je Typ, Kette je Fremdschlüssel)."""
    tab = Base.metadata.tables[t]
    out = {}
    for c in tab.columns:
        if c.name in werte:
            out[c.name] = werte[c.name]
        elif c.name == "id":
            out[c.name] = EIGENE_ID[t](a) if t in EIGENE_ID else 100 * a + n
        elif c.name in KETTE:
            out[c.name] = KETTE[c.name](a)
        else:
            out[c.name] = _platzhalter(c)
    return out


def _schreibe(con: sqlite3.Connection, t: str, zeile: dict) -> None:
    namen = ", ".join(f'"{k}"' for k in zeile)
    con.execute(f'INSERT INTO "{t}" ({namen}) VALUES ({", ".join("?" * len(zeile))})', list(zeile.values()))


def _sensor_mapping(a: int) -> str:
    return json.dumps({
        "basis": {"pv": {"strategie": "sensor", "sensor_id": "sensor.pv", "parameter": {"faktor": 2, "notiz": SPRENG}},
                  "live": {"leistung_w": "sensor.pv_w"}},
        "investitionen": {str(10 + a): {"felder": {"x": {"strategie": "sensor", "sensor_id": "sensor.x"}},
                                        "live": {"betriebsmodus": "select.wp_modus"}}},
        "quellen": {"basis_energy_pv": {"quelle": "ha_connector", "entity_id": "sensor.pv"}},
        "invertieren": ["basis_energy_pv"], "historie_hinweis": {"felder": [{"id": "f", "label": "Feld"}], "seit": "2026-01-01"},
        "live_sensors": {"pv": "sensor.pv_w"},
        "solcast_config": {"modus": "api", "api_key": f"{SPRENG}-key", "resource_ids": [f"{SPRENG}-res"]},
        "seriennummer": FREMDE_ZAHL, "aktiv": True, "leer": None,
    })


def _connector_config() -> str:
    return json.dumps({
        "connector_id": "fronius", "field_inv_map": {"pv": 11}, "last_fetch": "2026-10-03T12:00:00",
        "meter_snapshots": {"2026-10-03T12:00:00": {"timestamp": "2026-10-03T12:00:00", "pv_erzeugung_kwh": 12.5}},
        "password": f"{SPRENG}-pw", "host": f"{SPRENG}-host", "username": f"{SPRENG}-user",
        "seriennummer": f"{SPRENG}-sn", "cloud_import": [{"quelle": "x", "credentials": {"token": f"{SPRENG}-ci"}}],
        "geraete_id": FREMDE_ZAHL,
    })


def _parameter() -> str:
    return json.dumps({
        "anzahl_module": 20, "ausrichtung_grad": 15, "neigung": 30, "ausrichtung": "Süd", "kwp": 8.0,
        "beschreibung": "Mein Dach", "innengeraete": [{"id": 1, "bezeichnung": "Wohnzimmer"}],
        "oberflaeche_url": f"https://u:{SPRENG}@wallbox.local/", "stamm_seriennummer": f"{SPRENG}-sn",
        "ansprechpartner_email": f"{SPRENG}@example.org", "hersteller": f"{SPRENG}-hersteller", "phasen": 3,
        "fremd_zahl": PARAMETER_ZAHL,
    })


def _details_json() -> str:
    return json.dumps({"plan_id": "p1", "operation": "neu_aggregieren", "params": {"datum": "2026-10-03", "dyn": "frei"},
                       "korrigiert": [{"key": "basis:pv", "ab_ts": 1, "zeilen": 3}], "host": "192.168.1.5",
                       "unbekannt": f"{SPRENG}-dj", "connector_id": "fronius"})


def _provenance() -> str:
    return json.dumps({"einspeisung_kwh": {"source": "manual:form", "writer": f"{SPRENG}@example.org",
                                           "at": "2026-10-03T12:00:00", "input_hash": "abc123", "abgeleitet": "x"}})


def _ketten_zeilen(con: sqlite3.Connection, a: int) -> None:
    """Je ausgezogene Tabelle eine Zeile der Anlage ``a`` (W-7 d iteriert das Register; eine fehlende Tabelle ist rot)."""
    sonder = {
        "anlagen": dict(anlagenname=f"Haus {a} Süd", standort_strasse=f"{SPRENG}-Strasse 5", mastr_id=f"{SPRENG}-mastr",
                        community_hash=f"{SPRENG}-hash", latitude=50.123456, longitude=8.654321,
                        versorger_daten=json.dumps({"strom": {"kundennummer": f"{SPRENG}-kd"}}),
                        sensor_mapping=_sensor_mapping(a), connector_config=_connector_config(),
                        horizont_daten="[1.0, 2.5]", community_auto_share=1),
        "investitionen": dict(typ="pv-module", bezeichnung="Süddach", ausrichtung="Süd", neigung_grad=30.0,
                              parameter=_parameter()),
        "activity_log": dict(details_json=_details_json(), aktion=f"Fehler token={SPRENG}-akt",
                             details=f"kontakt {SPRENG}@example.org"),
        "monatsdaten": dict(jahr=2026, monat=10, notizen="Notiz", source_provenance=_provenance(),
                            geprueft_gegen='{"a": 1, "a": 2}', sonstige_positionen='[{"bezeichnung": "Wartung", "betrag": 5}]'),
        "investition_monatsdaten": dict(verbrauch_daten='{"ladung_kwh": 12.5, "sonstige_positionen": '
                                                        '[{"bezeichnung": "Öl", "typ": "kosten"}]}',
                                        source_provenance=_provenance()),
        "tages_energie_profil": dict(datum="2026-10-03", stunde=a, betriebsmodus_je_wp='{"14": "Heizen"}',
                                     komponenten='{"pv_11": 1.25}', spannen='{"a": ', source_provenance="{}"),
        "tages_zusammenfassung": dict(datum="2026-10-03", komponenten_kwh='{"pv_11": 12.5}', verworfen="null",
                                      nachtrag=None, pv_prognose_stundenprofil="[0.0, 1.5]",
                                      source_provenance=_provenance()),
        "korrekturprofile": dict(bin_definition='{"wetterklassen": ["klar", "bewölkt"], "variante": "v2"}', faktoren=5),
        "kanal_nachfuellung": dict(ergebnis='{"grund": "fertig", "zeilen": 3}'),
        "emob_ladebloecke": dict(stunden='[{"beginn": "2026-10-03 10:00", "kwh": 1.5}]'),
        "pvgis_prognosen": dict(latitude=50.12348, longitude=8.9, monatswerte="[1.0, 2.0]"),
        "data_provenance_log": dict(row_pk_json=json.dumps({"anlage_id": a, "jahr": 2026, "monat": 10}),
                                    writer=f"{SPRENG}@example.org", input_hash="abc"),
        "kanal_statistik": dict(start_ts=1_700_000_000 + a, familie="spiegel"),
        "kanal_quelle": dict(gueltig_ab=1_700_000_000, familie="spiegel"),
        "strompreis_zeitfenster": dict(wochentage="0,1,2"),
    }
    for t in sorted(reg.REGISTER):
        if t != "migrations":
            _schreibe(con, t, _zeile(t, a, **sonder.get(t, {})))


def _sonderzeilen(con: sqlite3.Connection) -> None:
    """Speicherformen und Grenzfälle in derselben Spalte; NIE-Tabellen mit Geheimnis."""
    _schreibe(con, "activity_log", _zeile("activity_log", 1, 1, anlage_id=None, details_json="null",
                                          aktion="Scheduler: Wetter-Lauf", details=None))
    _schreibe(con, "activity_log", _zeile("activity_log", 1, 2, details_json=None, aktion="ohne json", erfolg=0))
    _schreibe(con, "data_provenance_log", _zeile("data_provenance_log", 1, 1, field_name="__row__",
                                                 row_pk_json=json.dumps({"investition_id": 11, "jahr": 2026, "monat": 9})))
    _schreibe(con, "data_provenance_log", _zeile("data_provenance_log", 1, 2, row_pk_json='{"id": 5}'))
    _schreibe(con, "data_provenance_log", _zeile("data_provenance_log", 1, 3, row_pk_json='{"anlage_id": 10}'))
    for t in ("api_cache", "anlage_foto", "infothek_eintraege", "infothek_dateien", "infothek_investition", "settings"):
        z = _zeile(t, 1) if t != "settings" else {"key": "unbekannt_x", "value": json.dumps({"x": SPRENG}),
                                                    "updated_at": ZEIT_MIKRO}
        for k, v in list(z.items()):
            if isinstance(v, str) and t != "settings":
                z[k] = f"{SPRENG}-{t}"
        _schreibe(con, t, z)
    con.executemany("INSERT INTO migrations (name, applied_at) VALUES (?, ?)",
                    [("etappe_3c_p2_counter_hourly_backward", "2026-05-01T10:00:00.123456"), ("n780_x", ZEIT_MIKRO)])


def baue_voll_datei_db(pfad: Path) -> None:
    eng = create_engine(f"sqlite:///{pfad}")
    Base.metadata.create_all(eng)
    eng.dispose()
    con = sqlite3.connect(pfad)
    con.execute(reg.MIGRATIONS_DDL)
    for a in (1, 2):
        _ketten_zeilen(con, a)
    _sonderzeilen(con)
    con.commit()
    con.close()


class VollDb:
    def __init__(self, pfad: Path, engine):
        self.pfad = pfad
        self.engine = engine
        macher = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

        @asynccontextmanager
        async def sitzungen():
            async with macher() as s:
                yield s
                await s.commit()

        self.sitzungen = sitzungen

    def roh(self) -> sqlite3.Connection:
        return sqlite3.connect(self.pfad)


@pytest.fixture
async def voll_datei_db(tmp_path):
    pfad = tmp_path / "voll.db"
    baue_voll_datei_db(pfad)
    engine = create_async_engine(f"sqlite+aiosqlite:///{pfad}")
    try:
        yield VollDb(pfad, engine)
    finally:
        await engine.dispose()


# ─── Helfer ──────────────────────────────────────────────────────────────────────────────────────────────────────

def auszug_zip(pfad, anlage_id: int = 1) -> tuple[bytes, az.AuszugErgebnis]:
    puffer = io.BytesIO()
    with zipfile.ZipFile(puffer, "w", zipfile.ZIP_DEFLATED) as zf:
        erg = az.auszug(str(pfad), anlage_id, zf)
    return puffer.getvalue(), erg


def mitglieder(daten: bytes) -> dict[str, dict]:
    with zipfile.ZipFile(io.BytesIO(daten)) as zf:
        return {n[len("tabellen/"):-len(".json")]: json.loads(zf.read(n)) for n in zf.namelist() if n.startswith("tabellen/")}


def texte(daten: bytes) -> dict[str, str]:
    with zipfile.ZipFile(io.BytesIO(daten)) as zf:
        return {n: zf.read(n).decode("utf-8") for n in zf.namelist()}


def _typ(v) -> str:
    return {int: "integer", float: "real", str: "text", type(None): "null"}.get(type(v), type(v).__name__)


def rundreise(quelle: Path, daten: bytes, nachbau: Path, anlage_id: int = 1) -> list[str]:
    """Paket → leeres Schema → Einfügen → je Zelle: Filter(Quelle) = Paket = Nachbau nach Wert und Typ (G1). Spalten der
    Erwartung aus ``ERWARTET`` (Register beim Import) — eine Spalte, die das Paket nicht trägt, ist ungleich."""
    eng = create_engine(f"sqlite:///{nachbau}")
    Base.metadata.create_all(eng)
    eng.dispose()
    nb = sqlite3.connect(nachbau)
    nb.execute(reg.MIGRATIONS_DDL)
    q = sqlite3.connect(quelle)
    anlage = dict(zip(("latitude", "longitude"), q.execute("SELECT latitude, longitude FROM anlagen WHERE id = ?",
                                                           (anlage_id,)).fetchone()))
    fehler = []
    for t, m in mitglieder(daten).items():
        spalten = m["spalten"]
        if spalten != [s for s in ERWARTET[t] if s in spalten] or set(ERWARTET[t]) - set(spalten):
            fehler.append(f"{t}: Spalten {sorted(set(ERWARTET[t]) ^ set(spalten))}")
        nb.executemany(f'INSERT INTO "{t}" ({", ".join(chr(34) + s + chr(34) for s in spalten)}) '
                       f'VALUES ({", ".join("?" * len(spalten))})', m["zeilen"])
        nach = {_schl(r): r for r in nb.execute(f'SELECT {", ".join(chr(34) + s + chr(34) for s in spalten)} FROM "{t}"')}
        wandler = az._zellen_wandler(t, spalten, anlage, az.AuszugErgebnis())
        for z in m["zeilen"]:
            n = nach.get(_schl(z))
            if n is None:
                fehler.append(f"{t}: Zeile fehlt im Nachbau")
                continue
            for i, s in enumerate(spalten):
                if _typ(z[i]) != _typ(n[i]) or z[i] != n[i]:
                    fehler.append(f"{t}.{s}: Paket {_typ(z[i])} ≠ Nachbau {_typ(n[i])}")
        quell = _quellzeilen(q, t, spalten, anlage_id)
        erwartet = []
        for r in quell:
            r = list(r)
            for i, fn in wandler:
                r[i] = fn(r[i])
            erwartet.append(r)
        if sorted(map(_schl, erwartet)) != sorted(map(_schl, m["zeilen"])):
            fehler.append(f"{t}: Filter(Quelle) ≠ Paket")
    q.close()
    nb.close()
    return fehler


def _schl(z) -> tuple:
    return tuple((_typ(v), repr(v)) for v in z)


def _quellzeilen(q: sqlite3.Connection, t: str, spalten: list[str], anlage_id: int) -> list:
    """Die Zeilen der Quelle für den Vergleich — Filter unabhängig vom Auszug geschrieben (Kette der Fixture)."""
    sel = f'SELECT {", ".join(chr(34) + s + chr(34) for s in spalten)} FROM "{t}"'
    ketten = {"investitionen": 10, "kanal": 20, "strompreise": 30, "pvgis_prognosen": 40}
    art = reg.REGISTER[t].filterart
    if art == "ganz":
        return q.execute(sel).fetchall()
    if art == "anlage":
        return q.execute(sel + f' WHERE "{"id" if t == "anlagen" else "anlage_id"}" = ?', (anlage_id,)).fetchall()
    if art == "anlage_oder_null":
        return q.execute(sel + ' WHERE anlage_id = ? OR anlage_id IS NULL', (anlage_id,)).fetchall()
    if art.startswith("ueber:"):
        return q.execute(sel + f' WHERE "{reg.REGISTER[t].filterspalte}" = ?', (ketten[reg.REGISTER[t].eltern] + anlage_id,)).fetchall()
    i = spalten.index("row_pk_json")
    out = []
    for r in q.execute(sel).fetchall():
        pk = json.loads(r[i])
        if pk.get("anlage_id") == anlage_id or pk.get("investition_id") == 10 + anlage_id:
            out.append(r)
    return out


# ─── G1 Speicherform ─────────────────────────────────────────────────────────────────────────────────────────────

def test_g1_rundreise_wert_und_typ(voll_datei_db, tmp_path):
    daten, erg = auszug_zip(voll_datei_db.pfad)
    assert all(s.status == "ok" for s in erg.tabellen.values()), erg.tabellen
    assert rundreise(voll_datei_db.pfad, daten, tmp_path / "nachbau.db") == []
    m = mitglieder(daten)
    al = m["activity_log"]
    dj = al["spalten"].index("details_json")
    assert {r[dj] for r in al["zeilen"]} >= {"null", None}           # Text-null ≠ SQL-NULL, beide überstehen
    ts = al["spalten"].index("timestamp")
    assert ZEIT_MIKRO in {r[ts] for r in al["zeilen"]}                # Mikrosekunden, Leerzeichen statt «T»
    kp = m["korrekturprofile"]
    assert kp["zeilen"][0][kp["spalten"].index("faktoren")] == 5      # JSON-Zahl (NUMERIC-Affinität) bleibt Zahl
    gg = m["monatsdaten"]["spalten"].index("geprueft_gegen")
    assert m["monatsdaten"]["zeilen"][0][gg] == '{"a": 2}'            # doppelte Schlüssel ⇒ neu serialisiert
    an = m["anlagen"]
    assert an["zeilen"][0][an["spalten"].index("anlagenname")] == "Haus 1 Süd"


def test_g1_sprengsatz_zeit_mit_T_wird_rot(voll_datei_db, tmp_path):
    daten, _ = auszug_zip(voll_datei_db.pfad)
    m = mitglieder(daten)
    puffer = io.BytesIO()
    with zipfile.ZipFile(puffer, "w") as zf:
        for t, inhalt in m.items():
            if t == "activity_log":
                i = inhalt["spalten"].index("timestamp")
                for z in inhalt["zeilen"]:
                    z[i] = z[i].replace(" ", "T") if isinstance(z[i], str) else z[i]
            zf.writestr(f"tabellen/{t}.json", json.dumps(inhalt))
    assert any(f.startswith("activity_log: Filter(Quelle)") for f in
               rundreise(voll_datei_db.pfad, puffer.getvalue(), tmp_path / "nachbau.db"))


def test_g1_sprengsatz_rein_auf_raus_wird_rot(voll_datei_db, tmp_path, monkeypatch):
    md = reg.REGISTER["monatsdaten"]
    monkeypatch.setitem(reg.REGISTER, "monatsdaten", replace(md, spalten={**md.spalten, "notizen": reg.Spalte("raus")}))
    daten, _ = auszug_zip(voll_datei_db.pfad)
    assert any("notizen" in f for f in rundreise(voll_datei_db.pfad, daten, tmp_path / "nachbau.db"))


def test_g1_fehlende_spalte_nicht_als_wert(voll_datei_db):
    con = voll_datei_db.roh()
    con.execute("ALTER TABLE tages_zusammenfassung DROP COLUMN pv_prognose_kaskade_stundenprofil")
    con.commit()
    con.close()
    daten, erg = auszug_zip(voll_datei_db.pfad)
    tz = mitglieder(daten)["tages_zusammenfassung"]
    assert "pv_prognose_kaskade_stundenprofil" not in tz["spalten"]
    assert "pv_prognose_kaskade_stundenprofil" not in texte(daten)["tabellen/tages_zusammenfassung.json"]
    assert erg.schema["register_ohne_db"]["spalten"] == {"tages_zusammenfassung": ["pv_prognose_kaskade_stundenprofil"]}
    assert erg.tabellen["tages_zusammenfassung"].status == "ok"


def test_g1_eine_lesetransaktion(voll_datei_db, monkeypatch):
    befehle: list[str] = []
    echt = az.verbinde

    def _verbinde(p):
        con = echt(p)
        con.set_trace_callback(befehle.append)
        return con

    monkeypatch.setattr(az, "verbinde", _verbinde)
    auszug_zip(voll_datei_db.pfad)
    kern = [b.split()[0].upper() for b in befehle]
    assert kern.count("BEGIN") == 1 and kern.count("COMMIT") == 1
    assert kern[0] == "BEGIN" and kern[-1] == "COMMIT"
    assert not any(k in ("INSERT", "UPDATE", "DELETE") for k in kern)


# ─── G2 Blatt-Regel (W-7 b) ──────────────────────────────────────────────────────────────────────────────────────

def _json_spalten() -> list[tuple[str, str]]:
    return [(t, c.name) for t in sorted(reg.REGISTER) if t != "migrations"
            for c in Base.metadata.tables[t].columns if isinstance(c.type, JSON)]


#: Maßgabe Master (§3.5 Nr 4): unter dynamischen Schlüsseln und in einer «*»-Spalte nur bereinigter Text.
DYNAMISCH = f"Bearer {SPRENG}-b https://u:{SPRENG}-u@h.local/ {SPRENG}-m@example.org"


def _saat(t: str, s: str) -> str:
    sp = reg.REGISTER[t].spalten[s]
    alle = "*" in sp.text_schluessel
    saat = {"unbekannt_text": DYNAMISCH if alle else SPRENG, "unbekannt_zahl": 4711}
    if (t, s) == ("activity_log", "details_json"):
        saat["params"] = {"frei": DYNAMISCH}
    if (t, s) == ("anlagen", "sensor_mapping"):
        saat.update(basis={"live": {"feld": DYNAMISCH}}, live_sensors={"feld": DYNAMISCH},
                    investitionen={"11": {"live": {"modus": DYNAMISCH}}})
    return json.dumps(saat)[:-1] + f', "a": "{SPRENG}", "a": 1' + "}"


def test_g2_je_json_spalte(voll_datei_db):
    con = voll_datei_db.roh()
    spalten = _json_spalten()
    assert len(spalten) == 35
    for t, s in spalten:
        ziel = "id" if "id" in reg.REGISTER[t].spalten else reg.REGISTER[t].filterspalte
        wert = (1 if t == "anlagen" else az_ketten_id(t, ziel))
        con.execute(f'UPDATE "{t}" SET "{s}" = ? WHERE "{ziel}" = ?', (_saat(t, s), wert))
    con.commit()
    con.close()
    daten, erg = auszug_zip(voll_datei_db.pfad)
    alles = "\n".join(texte(daten).values())
    assert SPRENG not in alles
    for t, s in spalten:
        if reg.REGISTER[t].spalten[s].klasse == "raus":
            continue
        m = mitglieder(daten)[t]
        i = m["spalten"].index(s)
        zellen = [json.loads(z[i]) for z in m["zeilen"] if isinstance(z[i], str) and "unbekannt_zahl" in z[i]]
        sp = reg.REGISTER[t].spalten[s]
        # Zahl bleibt — außer unter einem fremden Oberschlüssel einer Allowlist ohne `fremde_zahlen_bleiben` (Master S1).
        erwartet = "⟨ersetzt:zahl:4⟩" if sp.oberschluessel is not None and not sp.fremde_zahlen_bleiben else 4711
        assert zellen and zellen[0]["unbekannt_zahl"] == erwartet, (t, s)
        if "*" not in reg.REGISTER[t].spalten[s].text_schluessel:
            assert "unbekannt_text" in erg.sammler.json_unbekannt[f"{t}.{s}"], (t, s)
            assert "a" in erg.sammler.json_unbekannt[f"{t}.{s}"] or zellen[0]["a"] == 1, (t, s)


def az_ketten_id(t: str, spalte: str) -> int:
    z = _zeile(t, 1)
    return z[spalte]


def test_allowlist_fremde_zahl_nur_in_parameter(voll_datei_db, monkeypatch):
    """Einwertung Master S1: unter `connector_config`/`sensor_mapping` behält ein fremder Oberschlüssel keinen Wert, auch keine
    Zahl (Name bleibt mit Marke); unter `investitionen.parameter` bleibt die Zahl (Konzept §4.2). `null`/bool bleiben."""
    daten, erg = auszug_zip(voll_datei_db.pfad)
    alles = "\n".join(texte(daten).values())
    assert str(FREMDE_ZAHL) not in alles and str(PARAMETER_ZAHL) in alles
    an = mitglieder(daten)["anlagen"]
    sm = json.loads(an["zeilen"][0][an["spalten"].index("sensor_mapping")])
    cc = json.loads(an["zeilen"][0][an["spalten"].index("connector_config")])
    assert (sm["seriennummer"], sm["aktiv"], sm["leer"]) == ("⟨ersetzt:zahl:12⟩", True, None)
    assert cc["geraete_id"] == "⟨ersetzt:zahl:12⟩" and MARKE_RE.fullmatch(cc["geraete_id"])
    assert "seriennummer" in erg.sammler.json_unbekannt["anlagen.sensor_mapping"]
    assert "geraete_id" in erg.sammler.json_unbekannt["anlagen.connector_config"]
    # Zähne: das Feld an `connector_config` umgedreht ⇒ die Zahl steht im Paket.
    cs = reg.REGISTER["anlagen"].spalten["connector_config"]
    monkeypatch.setitem(reg.REGISTER, "anlagen", replace(reg.REGISTER["anlagen"], spalten={
        **reg.REGISTER["anlagen"].spalten, "connector_config": replace(cs, fremde_zahlen_bleiben=True)}))
    assert str(FREMDE_ZAHL) in "\n".join(texte(auszug_zip(voll_datei_db.pfad)[0]).values())


def test_g2_gegenprobe_text_schluessel_laesst_text_durch():
    sp = reg.REGISTER["monatsdaten"].spalten["geprueft_gegen"]
    zelle = json.dumps({"unbekannt_text": SPRENG})
    assert SPRENG not in filtere_json(sp, zelle)
    offen = replace(sp, text_schluessel=frozenset({"unbekannt_text"}))
    assert filtere_json(offen, zelle) == zelle


def test_g2_marke_ist_idempotent():
    for t, s in _json_spalten():
        sp = reg.REGISTER[t].spalten[s]
        einmal = filtere_json(sp, _saat(t, s))
        assert filtere_json(sp, einmal) == einmal, (t, s)
    sm = reg.REGISTER["anlagen"].spalten["sensor_mapping"]
    assert filtere_json(sm, filtere_json(sm, _sensor_mapping(1))) == filtere_json(sm, _sensor_mapping(1))
    assert MARKE_RE.fullmatch("⟨ersetzt:dict:4⟩")


def test_g2_schluesselwort_schluessel_geschwaerzt():
    sp = reg.REGISTER["tages_zusammenfassung"].spalten["komponenten_kwh"]
    neu = json.loads(filtere_json(sp, json.dumps({"password": 5, "api_key": {"x": 1}, "token": "abc", "pv_1": 2.5,
                                                  "input_hash": 3})))
    assert neu == {"password": "<geschwärzt>", "api_key": "<geschwärzt>", "token": "<geschwärzt>", "pv_1": 2.5,
                   "input_hash": 3}


def _treffer(zellen: list) -> list:
    return [z for z in zellen if isinstance(z, str) and SPRENG in z]


def test_k3_unlesbar_wird_marke():
    cc = reg.REGISTER["anlagen"].spalten["connector_config"]
    sm = reg.REGISTER["anlagen"].spalten["sensor_mapping"]
    faelle = [(cc, '{"password": "SPRENGSATZ"'), (cc, '"SPRENGSATZ"'),
              (sm, json.dumps(json.dumps({"solcast_config": {"api_key": SPRENG}})))]
    s = Sammler()
    aus = [filtere_json(sp, z, s, "anlagen.x") for sp, z in faelle]
    assert _treffer(aus) == [] and all(re.fullmatch(r"⟨ersetzt:unlesbar:\d+⟩", a) for a in aus)
    assert s.json_unlesbar == {"anlagen.x": 3}

    def _rueckfall(sp, zelle):
        try:
            v = json.loads(zelle)
        except ValueError:
            return zelle
        return zelle if not isinstance(v, dict) else filtere_json(sp, zelle)

    assert _treffer([_rueckfall(sp, z) for sp, z in faelle]), "Sprengsatz: Rückfall auf Rohtext muss auffallen"


# ─── W-7 (d) eine Anlage ─────────────────────────────────────────────────────────────────────────────────────────

def fremde_zeilen(daten: bytes) -> list[str]:
    """Zeilen der Kette der Anlage 2 im Paket der Anlage 1 (Ketten-ID je Tabelle, aus dem Register iteriert)."""
    out = []
    m = mitglieder(daten)
    for t in sorted(reg.REGISTER):
        if t == "migrations":
            continue
        assert t in m, f"{t}: nicht gesät oder nicht ausgezogen"
        z2 = _zeile(t, 2)
        schl = "id" if "id" in m[t]["spalten"] else m[t]["spalten"][0]
        i = m[t]["spalten"].index(schl)
        if any(r[i] == z2[schl] for r in m[t]["zeilen"]):
            out.append(t)
    return out


def test_w7d_keine_zeile_der_anderen_anlage(voll_datei_db):
    daten, erg = auszug_zip(voll_datei_db.pfad)
    assert fremde_zeilen(daten) == []
    zwei, _ = auszug_zip(voll_datei_db.pfad, 2)
    assert mitglieder(zwei)["anlagen"]["zeilen"][0][0] == 2
    # Gegenprobe: jede Tabelle trägt ihre eigene Kettenzeile (sonst hätte der Test nichts geprüft).
    m = mitglieder(daten)
    for t in reg.REGISTER:
        assert m[t]["zeilen"], t


def test_w7d_ganz_nur_migrations(voll_datei_db):
    assert [t for t, tab in reg.REGISTER.items() if tab.filterart == "ganz"] == ["migrations"]
    daten, _ = auszug_zip(voll_datei_db.pfad)
    assert len(mitglieder(daten)["migrations"]["zeilen"]) == 2


def test_w7d_sprengsatz_filter_zeitfenster_entfernt(voll_datei_db, monkeypatch):
    monkeypatch.setitem(reg.REGISTER, "strompreis_zeitfenster",
                        replace(reg.REGISTER["strompreis_zeitfenster"], filterart="ganz"))
    daten, _ = auszug_zip(voll_datei_db.pfad)
    assert fremde_zeilen(daten) == ["strompreis_zeitfenster"]


def test_w7d_filterspalte_fehlt_ist_teilfehler(voll_datei_db):
    con = voll_datei_db.roh()
    con.executescript("ALTER TABLE sensor_snapshots RENAME TO alt;"
                      "CREATE TABLE sensor_snapshots (id INTEGER PRIMARY KEY, sensor_key TEXT, zeitpunkt TEXT, "
                      "wert_kwh REAL, quelle TEXT); INSERT INTO sensor_snapshots SELECT id, sensor_key, zeitpunkt, "
                      "wert_kwh, quelle FROM alt; DROP TABLE alt;")
    con.close()
    daten, erg = auszug_zip(voll_datei_db.pfad)
    assert (erg.tabellen["sensor_snapshots"].status, erg.tabellen["sensor_snapshots"].grund) == ("fehler",
                                                                                                "filterspalte_fehlt")
    assert "tabellen/sensor_snapshots.json" not in texte(daten)
    assert all(s.status == "ok" for t, s in erg.tabellen.items() if t != "sensor_snapshots")


# ─── Q1, Q3, Q5, inhalt.json ─────────────────────────────────────────────────────────────────────────────────────

def test_q1_koordinaten_toleranz_wie_anlage(voll_datei_db):
    con = voll_datei_db.roh()
    con.execute("UPDATE anlagen SET latitude = 50.125, longitude = 8.654321 WHERE id = 1")
    # 50.12505 liegt in der Toleranz der Anlage, rundet für sich aber auf 50.13 — die Prognose bekommt den Wert der Anlage.
    con.execute("UPDATE pvgis_prognosen SET latitude = 50.12505, longitude = 8.9 WHERE id = 41")
    con.commit()
    con.close()
    m = mitglieder(auszug_zip(voll_datei_db.pfad)[0])
    an, pv = m["anlagen"], m["pvgis_prognosen"]
    lat_a = an["zeilen"][0][an["spalten"].index("latitude")]
    assert lat_a == round(50.125, 2)
    assert pv["zeilen"][0][pv["spalten"].index("latitude")] == lat_a
    assert pv["zeilen"][0][pv["spalten"].index("longitude")] == 8.9       # außerhalb der Toleranz: für sich gerundet
    assert an["zeilen"][0][an["spalten"].index("longitude")] == 8.65


def test_q3_provenance_natural_key_mit_loescheintraegen(voll_datei_db):
    daten, erg = auszug_zip(voll_datei_db.pfad)
    m = mitglieder(daten)["data_provenance_log"]
    pk = [json.loads(z[m["spalten"].index("row_pk_json")]) for z in m["zeilen"]]
    feld = [z[m["spalten"].index("field_name")] for z in m["zeilen"]]
    assert {"anlage_id": 1, "jahr": 2026, "monat": 10} in pk
    assert "__row__" in feld and {"investition_id": 11, "jahr": 2026, "monat": 9} in pk
    assert not any(p.get("anlage_id") in (2, 10) or p.get("investition_id") == 12 for p in pk)
    assert erg.ohne_anlagenbezug == {"data_provenance_log": 1}


def test_q5_aktivitaeten_mit_und_ohne_anlage(voll_datei_db):
    daten, erg = auszug_zip(voll_datei_db.pfad)
    m = mitglieder(daten)["activity_log"]
    anlagen = [z[m["spalten"].index("anlage_id")] for z in m["zeilen"]]
    assert sorted(anlagen, key=str) == sorted([1, 1, None], key=str)
    assert erg.aktivitaet_ohne_anlage == 1


async def test_inhalt_json_zuletzt_und_vollstaendig(voll_datei_db, tmp_path, monkeypatch):
    from datetime import datetime

    from backend.services.diagnose_paket import ablage, paket

    monkeypatch.setattr(ablage, "VERZEICHNIS", tmp_path / "ablage")
    felder = await paket.bereitstellen(1, db_pfad=str(voll_datei_db.pfad), sitzungen=voll_datei_db.sitzungen,
                                       jetzt=datetime(2026, 11, 15, 9, 0), ha_svc=_KeinHa())
    with zipfile.ZipFile(ablage._EINTRAEGE[1].pfad) as zf:
        namen = zf.namelist()
        inhalt = json.loads(zf.read("inhalt.json"))
    tab = [n for n in namen if n.startswith("tabellen/")]
    assert namen == sorted(tab) + ["lage.json", "inhalt.json"]
    assert inhalt["vollstaendig"] is True and inhalt["format"] == "eedc-diagnose" and inhalt["version"] == 4
    assert set(inhalt["tabellen"]) == set(reg.REGISTER)
    assert felder["dateiname"] == "eedc_diagnose_Haus-1-S-d_2026-11-15.zip"


class _KeinHa:
    is_available = False
