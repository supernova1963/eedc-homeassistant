"""Spalten-Register des Diagnose-Pakets v4 — Wächter W-7 (a) Vollständigkeit und (b) Schlüsselraum (Bauplan v4 §4).

(a) Tabellen der MetaData ∪ ``migrations`` = Register ∪ ``NIE``; Spaltenmengen gleich; ``json`` = Modelltyp; ``MIGRATIONS_DDL`` =
``core/database.py``; kein ``rein``/``text_schluessel`` auf ``SCHLUESSELWOERTER`` außer ``source_hash``, ``input_hash`` (K6).
(b) Jede ausgezogene JSON-Spalte trägt eine Blatt-Regel; ``details_json``-Oberschlüssel kommen aus dem Code (AST); die
Einstellungen kennen jeden ``settings``-Schlüssel des Codes; die Lese-Schlüssel des Codes stehen in der Parameter-Allowlist
(N-797). Sprengsätze je Regel prüfen die Prüffunktion an einer veränderten Kopie, nie am globalen Schema.

Schwesterdateien: test_diagnose_paket.py, test_diagnose_paket_auszug.py, test_diagnose_paket_ha_abgleich.py.
"""
from __future__ import annotations

import ast
import importlib
import json
import pkgutil
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

import pytest
from sqlalchemy import JSON, Column, MetaData, String

import backend.models as _models
from backend.core.database import Base
from backend.services.diagnose_paket import register as reg
from backend.tests.quellbaum import produktivbaum

for _m in pkgutil.iter_modules(_models.__path__):
    importlib.import_module(f"backend.models.{_m.name}")

BACKEND = Path(__file__).resolve().parents[1]


def _tabellen_der_metadata(tabellen=None) -> dict[str, dict[str, bool]]:
    """{Tabelle: {Spalte: ist_json}} aus der MetaData (oder einer veränderten Kopie)."""
    tabellen = tabellen if tabellen is not None else Base.metadata.tables
    return {t.name: {c.name: isinstance(c.type, JSON) for c in t.columns} for t in tabellen.values()}


def _abweichungen(schema: dict[str, dict[str, bool]], register: dict) -> list[str]:
    out = []
    model = set(schema) | {"migrations"}
    if model != set(register) | reg.NIE:
        out.append(f"Tabellen: ohne Klasse {sorted(model - set(register) - reg.NIE)}, verwaist "
                   f"{sorted((set(register) | reg.NIE) - model)}")
    for t, tab in register.items():
        if t == "migrations":
            continue
        spalten = schema.get(t, {})
        if set(spalten) != set(tab.spalten):
            out.append(f"{t}: ohne Klasse {sorted(set(spalten) - set(tab.spalten))}, verwaist "
                       f"{sorted(set(tab.spalten) - set(spalten))}")
        out += [f"{t}.{s}: Klasse {sp.klasse}" for s, sp in tab.spalten.items() if sp.klasse not in reg.KLASSEN]
    return out


def _schluesselwort_verstoesse(register: dict) -> list[str]:
    out = []
    for t, tab in register.items():
        for s, sp in tab.spalten.items():
            if sp.klasse != "raus" and reg.ist_schluesselwort(s):
                out.append(f"{t}.{s}")
            out += [f"{t}.{s}[{k}]" for k in sp.text_schluessel if k != "*" and reg.ist_schluesselwort(k)]
    return out


# ─── W-7 (a) ─────────────────────────────────────────────────────────────────────────────────────────────────────

def test_w7a_jede_tabelle_und_spalte_hat_eine_klasse():
    assert _abweichungen(_tabellen_der_metadata(), reg.REGISTER) == []
    assert len(reg.REGISTER) == 23 and len(reg.NIE) == 6
    gesamt = sum(len(c) for c in _tabellen_der_metadata().values()) + 2
    assert gesamt == 375, gesamt          # 28 Modell-Tabellen, 373 Spalten + migrations (Bauplan §3.2)


def test_w7a_sprengsatz_neue_spalte():
    md = MetaData()
    kopie = {n: t.to_metadata(md) for n, t in Base.metadata.tables.items()}
    kopie["anlagen"].append_column(Column("sprengsatz", String))
    assert any("sprengsatz" in z for z in _abweichungen(_tabellen_der_metadata(kopie), reg.REGISTER))


def test_w7a_sprengsatz_verwaiste_registerspalte():
    register = dict(reg.REGISTER)
    register["kanal"] = replace(reg.REGISTER["kanal"], spalten={**reg.REGISTER["kanal"].spalten, "gibt_es_nicht": reg.Spalte()})
    assert any("gibt_es_nicht" in z for z in _abweichungen(_tabellen_der_metadata(), register))


def test_w7a_json_kennzeichen_wie_modell():
    schema = _tabellen_der_metadata()
    falsch = [f"{t}.{s}" for t, tab in reg.REGISTER.items() if t != "migrations"
              for s, sp in tab.spalten.items() if sp.json != schema[t][s]]
    assert falsch == []


def test_w7a_migrations_wie_im_code():
    baum = ast.parse((BACKEND / "core" / "database.py").read_text(encoding="utf-8"))
    ddl = [n.value for n in ast.walk(baum) if isinstance(n, ast.Constant) and isinstance(n.value, str)
           and n.value.startswith("CREATE TABLE IF NOT EXISTS migrations")]
    assert ddl == [reg.MIGRATIONS_DDL]
    assert list(reg.REGISTER["migrations"].spalten) == ["name", "applied_at"]
    assert reg.REGISTER["migrations"].filterart == "ganz"


def test_w7a_kein_rein_auf_schluesselwort():
    assert _schluesselwort_verstoesse(reg.REGISTER) == []
    gefunden = {s for tab in reg.REGISTER.values() for s, sp in tab.spalten.items()
                if sp.klasse != "raus" and reg.SCHLUESSELWOERTER.search(s)}
    assert gefunden == {"source_hash", "input_hash"}


def test_w7a_sprengsatz_api_token_rein():
    register = dict(reg.REGISTER)
    register["anlagen"] = replace(reg.REGISTER["anlagen"], spalten={**reg.REGISTER["anlagen"].spalten,
                                                                    "api_token": reg.Spalte("rein")})
    assert _schluesselwort_verstoesse(register) == ["anlagen.api_token"]
    sm = reg.REGISTER["anlagen"].spalten["sensor_mapping"]
    register["anlagen"] = replace(register["anlagen"], spalten={
        **reg.REGISTER["anlagen"].spalten, "sensor_mapping": replace(sm, text_schluessel=sm.text_schluessel | {"api_key"})})
    assert _schluesselwort_verstoesse(register) == ["anlagen.sensor_mapping[api_key]"]


# ─── W-7 (b) ─────────────────────────────────────────────────────────────────────────────────────────────────────

def test_w7b_jede_json_spalte_hat_eine_blattregel():
    schema = _tabellen_der_metadata()
    json_spalten = [(t, s) for t, tab in reg.REGISTER.items() if t != "migrations" for s in tab.spalten if schema[t][s]]
    assert len(json_spalten) == 35
    klassen = [reg.REGISTER[t].spalten[s].klasse for t, s in json_spalten]
    assert {k: klassen.count(k) for k in set(klassen)} == {
        "allowlist": 3, "raus": 1, "bereinigt:struktur": 1, "bereinigt:email": 4, "rein": 26}
    for t, s in json_spalten:
        sp = reg.REGISTER[t].spalten[s]
        assert sp.json and isinstance(sp.text_schluessel, frozenset) and isinstance(sp.text_unter, frozenset), (t, s)
        if sp.klasse in ("allowlist", "bereinigt:struktur"):
            assert sp.oberschluessel, (t, s)
    mit_regel = [(t, s) for t, s in json_spalten if reg.REGISTER[t].spalten[s].text_schluessel
                 or reg.REGISTER[t].spalten[s].text_unter]
    assert len(mit_regel) == 15          # 14 (Bauplan §3.2) + `korrekturprofile.lern_basis_pro_bin` (Register-Nachtrag 15.11.)
    # Fremde Oberschlüssel-Zahlen bleiben nur in `investitionen.parameter` (Konzept §4.2, Einwertung Master S1).
    assert [(t, s) for t, s in json_spalten if reg.REGISTER[t].spalten[s].fremde_zahlen_bleiben] == [
        ("investitionen", "parameter")]
    # Jede JSON-Spalte einer ausgezogenen Tabelle steht im Register — auch unter `NIE` fällt keine aus der Prüfung.
    nie_json = [(t, s) for t, sp in schema.items() if t in reg.NIE for s, j in sp.items() if j]
    assert sorted(nie_json) == [("api_cache", "data"), ("infothek_eintraege", "parameter"), ("settings", "value")]


def _dict_schluessel(knoten: ast.Dict) -> set[str]:
    """Literal-Schlüssel; ``**x`` (Schlüssel ``None``) wird über ``_ENTPACKT`` aufgelöst."""
    out = set()
    for k, v in zip(knoten.keys, knoten.values):
        if k is None:
            out |= _ENTPACKT[ast.unparse(v)]()
            continue
        assert isinstance(k, ast.Constant) and isinstance(k.value, str), ast.unparse(knoten)[:120]
        out.add(k.value)
    return out


def _bestand_schluessel() -> set[str]:
    """``**bestand`` in ``verwerfen_vor_quellbeginn.py``: die Dict-Literale in ``leere_bestand`` (``out = {…}``)."""
    fn = next(n for n in ast.walk(_quelle("services/verwerfen_vor_quellbeginn.py"))
              if isinstance(n, ast.AsyncFunctionDef) and n.name == "leere_bestand")
    return {k.value for d in ast.walk(fn) if isinstance(d, ast.Dict) for k in d.keys if isinstance(k, ast.Constant)}


_ENTPACKT = {"bestand": _bestand_schluessel}


def _quelle(rel: str) -> ast.Module:
    return ast.parse((BACKEND / rel).read_text(encoding="utf-8"))


def _ausdrucks_schluessel(fn: ast.AST, arg: ast.AST, rel: str) -> set[str]:
    """Schlüssel einer Ausdrucks-Quelle an einer ``details_json=``-Stelle (5 Formen am HEAD, Bauplan §9 Nr 9)."""
    if isinstance(arg, ast.Dict):
        return _dict_schluessel(arg)
    if isinstance(arg, ast.Name) and arg.id == "clean_map":
        kat = next(n for n in ast.walk(_quelle(rel)) if isinstance(n, ast.Assign)
                   and any(getattr(t, "id", "") == "_KATEGORIE_TYPEN" for t in n.targets))
        return _dict_schluessel(kat.value)
    if isinstance(arg, ast.Name):
        dicts = [n.value for n in ast.walk(fn) if isinstance(n, ast.Assign) and isinstance(n.value, ast.Dict)
                 and any(getattr(t, "id", "") == arg.id for t in n.targets)]
        assert dicts, f"{rel}: details_json={arg.id} ohne Dict-Literal — neue Ausdrucks-Form, hier ergänzen"
        return set().union(*map(_dict_schluessel, dicts))
    if isinstance(arg, ast.Call) and isinstance(arg.func, ast.Attribute) and arg.func.attr == "to_dict":
        klasse = next(n for n in ast.walk(_quelle("services/connectors/base.py"))
                      if isinstance(n, ast.ClassDef) and n.name == "MeterSnapshot")
        return {n.target.id for n in klasse.body if isinstance(n, ast.AnnAssign)}
    if isinstance(arg, ast.Call) and isinstance(arg.func, ast.Attribute) and arg.func.attr == "als_dict":
        return {k for n in ast.walk(_quelle("services/kanal/nachfuellen.py")) if isinstance(n, ast.FunctionDef)
                and n.name == "als_dict" for r in ast.walk(n) if isinstance(r, ast.Dict)
                for k in (x.value for x in r.keys if isinstance(x, ast.Constant))}
    raise AssertionError(f"{rel}: details_json-Ausdruck {ast.unparse(arg)[:80]} — neue Form, hier ergänzen")


def test_w7b_details_json_schluessel_aus_dem_code():
    gefunden: set[str] = set()
    stellen = 0
    for datei in produktivbaum():
        for fn in ast.walk(datei.baum):
            if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for n in ast.walk(fn):
                if not isinstance(n, ast.Call):
                    continue
                for kw in n.keywords:
                    if kw.arg != "details_json" or (isinstance(kw.value, ast.Name) and kw.value.id == "details_json"):
                        continue
                    stellen += 1
                    gefunden |= _ausdrucks_schluessel(fn, kw.value, datei.rel)
    assert stellen >= 19, stellen
    assert gefunden - reg.DETAILS_JSON_SCHLUESSEL == set()
    assert gefunden == reg.DETAILS_JSON_SCHLUESSEL, sorted(reg.DETAILS_JSON_SCHLUESSEL - gefunden)


def _modul_konstanten(baum: ast.Module) -> dict[str, str]:
    out = {}
    for n in baum.body:
        wert = getattr(n, "value", None)
        if isinstance(n, (ast.Assign, ast.AnnAssign)) and isinstance(wert, ast.Constant) and isinstance(wert.value, str):
            for t in (n.targets if isinstance(n, ast.Assign) else [n.target]):
                if getattr(t, "id", "").endswith("_KEY"):
                    out[t.id] = wert.value
    return out


def _settings_schluessel_im_code() -> set[str]:
    """Schlüssel der Tabelle ``settings`` im Code (Bauplan §9 Nr 10: 8): in Dateien, die ``models.settings`` importieren,
    (1) die modulweiten ``*_KEY = "…"`` und (2) jedes ``<Settings>.key == X`` bzw. ``<Settings>(key=X)`` — ``X`` als Literal
    oder als ``*_KEY``-Konstante irgendeiner Datei."""
    dateien = list(produktivbaum())
    konstanten: dict[str, set[str]] = {}
    for d in dateien:
        for name, wert in _modul_konstanten(d.baum).items():
            konstanten.setdefault(name, set()).add(wert)

    def _werte(x: ast.AST) -> set[str]:
        if isinstance(x, ast.Constant) and isinstance(x.value, str):
            return {x.value}
        return konstanten.get(getattr(x, "id", ""), set())

    out: set[str] = set()
    for d in dateien:
        if "models.settings import" not in ast.unparse(d.baum):
            continue
        out |= set(_modul_konstanten(d.baum).values())
        for n in ast.walk(d.baum):
            if (isinstance(n, ast.Compare) and isinstance(n.left, ast.Attribute) and n.left.attr == "key"
                    and getattr(n.left.value, "id", "").startswith("Settings")):
                out |= set().union(*map(_werte, n.comparators))
            if isinstance(n, ast.Call) and getattr(n.func, "id", "").startswith("Settings"):
                out |= set().union(set(), *(_werte(k.value) for k in n.keywords if k.arg == "key"))
    return out


def test_w7b_einstellungen_kennen_jeden_settings_schluessel():
    im_code = _settings_schluessel_im_code()
    assert len(im_code) >= 8, sorted(im_code)
    assert im_code - set(reg.EINSTELLUNGEN) == set()


def _parameter_quelle(x: ast.AST) -> bool:
    """``X.parameter``, ``getattr(X, "parameter", …)``, jeweils auch ``… or {}`` und ``dict(…)`` — sonst nichts."""
    if isinstance(x, ast.BoolOp) and isinstance(x.op, ast.Or):
        return _parameter_quelle(x.values[0])
    if isinstance(x, ast.Call) and getattr(x.func, "id", "") == "dict" and len(x.args) == 1:
        return _parameter_quelle(x.args[0])
    if isinstance(x, ast.Attribute) and x.attr == "parameter":
        return True
    return (isinstance(x, ast.Call) and getattr(x.func, "id", "") == "getattr" and len(x.args) >= 2
            and isinstance(x.args[1], ast.Constant) and x.args[1].value == "parameter")


def _lese_schluessel_der_funktion(fn: ast.AST) -> set[str]:
    namen = {t.id for n in ast.walk(fn) if isinstance(n, ast.Assign) and _parameter_quelle(n.value)
             for t in n.targets if isinstance(t, ast.Name)}
    schleifen = {n.target.id: {e.value for e in n.iter.elts if isinstance(e, ast.Constant)}
                 for n in ast.walk(fn) if isinstance(n, ast.For) and isinstance(n.target, ast.Name)
                 and isinstance(n.iter, ast.Tuple)}

    def _ist_quelle(x: ast.AST) -> bool:
        return (isinstance(x, ast.Name) and x.id in namen) or _parameter_quelle(x)

    out: set[str] = set()
    for n in ast.walk(fn):
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == "get" and n.args \
                and _ist_quelle(n.func.value):
            a = n.args[0]
            if isinstance(a, ast.Constant) and isinstance(a.value, str):
                out.add(a.value)
            elif isinstance(a, ast.Name) and a.id in schleifen:
                out |= {v for v in schleifen[a.id] if isinstance(v, str)}
        elif isinstance(n, ast.Subscript) and _ist_quelle(n.value) and isinstance(n.slice, ast.Constant) \
                and isinstance(n.slice.value, str):
            out.add(n.slice.value)
    return out


def _lese_schluessel_im_code() -> set[str]:
    out: set[str] = set()
    for datei in produktivbaum():
        # Ausgenommen: das Paket selbst; die Demo-Daten; die Infothek-Migration (liest `stamm_*`, um sie aus `parameter`
        # HERAUS zu ziehen — sie gehören gerade nicht ins Paket, Konzept §4.2 Ü1).
        if datei.rel.startswith(("services/diagnose_paket/", "api/routes/import_export/demo_data.py",
                                 "services/infothek_migration.py")):
            continue
        for fn in ast.walk(datei.baum):
            if isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
                out |= _lese_schluessel_der_funktion(fn)
    return out


def test_w7b_lese_schluessel_ueberstehen_den_auszug():
    gefunden = _lese_schluessel_im_code()
    assert len(gefunden) >= 12, sorted(gefunden)
    assert {"neigung", "neigung_grad", "ausrichtung", "ausrichtung_grad"} <= gefunden
    assert gefunden - reg.PARAMETER_ALLOWLIST == set(), sorted(gefunden - reg.PARAMETER_ALLOWLIST)


def test_w7b_provenance_gruppen_aus_dem_code():
    """Register-Nachtrag 15.11.: ``gruppen`` in ``_PROVENANCE_TS`` ist der Provenance-Schlüssel, den ``aggregate_day`` an
    Kanal-Tagen schreibt (``energie_profil/mengen_weiche.py``, Dict-Literal) — fällt er dort weg, ist der Eintrag verwaist."""
    baum = _quelle("services/energie_profil/mengen_weiche.py")
    schluessel = {k.value for d in ast.walk(baum) if isinstance(d, ast.Dict) for k in d.keys
                  if isinstance(k, ast.Constant) and isinstance(k.value, str)}
    assert "gruppen" in schluessel
    for t in ("investition_monatsdaten", "monatsdaten", "tages_energie_profil", "tages_zusammenfassung"):
        assert "gruppen" in reg.REGISTER[t].spalten["source_provenance"].text_schluessel, t
    sm = reg.REGISTER["anlagen"].spalten["sensor_mapping"]
    assert "updated_at" in sm.oberschluessel and "updated_at" in sm.text_schluessel
    assert "solcast_config" not in sm.oberschluessel          # bleibt Marke (Entscheid Master 15.11.)
    assert reg.REGISTER["korrekturprofile"].spalten["lern_basis_pro_bin"].text_schluessel == {"*"}
    assert "sonderkosten_notiz" not in reg.REGISTER["investition_monatsdaten"].spalten["verbrauch_daten"].text_schluessel


def test_w7b_sprengsatz_lese_schluessel():
    assert "neigung" in _lese_schluessel_im_code() - (reg.PARAMETER_ALLOWLIST - {"neigung"})


# ─── Werkzeug ────────────────────────────────────────────────────────────────────────────────────────────────────

def test_register_ist_werkzeugtauglich():
    """Das Werkzeug lädt Register und Bereinigung ohne Backend-Last (kein SQLAlchemy, kein FastAPI) — `als_json` trägt alles."""
    code = (
        "import sys, json; sys.path.insert(0, sys.argv[1]);"
        "from backend.services.diagnose_paket import register, bereinigung;"
        "schwer = sorted(m for m in sys.modules if m.split('.')[0] in ('sqlalchemy', 'fastapi', 'pydantic', 'httpx'));"
        "print(json.dumps({'schwer': schwer, 'register': json.loads(register.als_json())}))"
    )
    r = subprocess.run([sys.executable, "-I", "-c", code, str(BACKEND.parent)], capture_output=True, text=True,
                       check=True, timeout=60)
    out = json.loads(r.stdout)
    assert out["schwer"] == []
    assert out["register"] == json.loads(reg.als_json())
    tab = out["register"]["tabellen"]
    assert set(tab) == set(reg.REGISTER) and out["register"]["nie"] == sorted(reg.NIE)
    assert tab["anlagen"]["spalten"]["standort_strasse"]["klasse"] == "raus"
    assert tab["kanal_statistik"]["filterart"] == "ueber:kanal.kanal_id"
    assert tab["investitionen"]["spalten"]["parameter"]["fremde_zahlen_bleiben"] is True
    assert tab["anlagen"]["spalten"]["connector_config"]["fremde_zahlen_bleiben"] is False


@pytest.mark.parametrize("t", sorted(reg.REGISTER))
def test_w7d_filterart_je_tabelle(t):
    """W-7 (d) im Register: jede Tabelle trägt eine bekannte Filterart; ``ganz`` nur ``migrations``; die Filterspalte steht
    in der Tabelle bzw. die Elterntabelle im Register."""
    tab = reg.REGISTER[t]
    assert tab.filterart in ("anlage", "anlage_oder_null", "natural_key", "ganz") or tab.filterart.startswith("ueber:")
    assert (tab.filterart == "ganz") == (t == "migrations")
    if tab.filterspalte is not None:
        assert tab.filterspalte in tab.spalten
    if tab.eltern is not None:
        assert tab.eltern in reg.REGISTER and "id" in reg.REGISTER[tab.eltern].spalten
