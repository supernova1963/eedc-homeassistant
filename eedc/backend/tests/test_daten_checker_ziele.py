"""Wächter W-2 und W-6 (Etappe E2 «Daten-Checker: ein Handgriff je Befund», Bauplan §4; Konzept §3.1 R2, §3.4).

W-2: kein `/einstellungen/`-Literal und keine `LINK_*`-Konstante in einem Erzeuger; jedes Ziel entsteht über den
Ziel-Bauer (`ziele.py`); **jeder Feld-Schlüssel steht in der Registry** — jede Bauer-Stelle wird mit ihren Literalen
ausgeführt, ein unbekannter Schlüssel wirft (Sprengsatz S1); Block-Ids aus `BLOCK_IDS`. Das Übergangsfeld `altlink=`
trägt nur benannte Werte und hält eine schrumpfende Baseline (`daten_checker_altlink_baseline.txt`, E4 leert sie).
W-6: Auskunft ohne WARNING/ERROR — außer genau zwei Codes mit Grund (Allowlist).

Schwesterdateien: test_daten_checker_codes.py (W-1/W-3), test_daten_checker_texte_fixtures.py (W-8),
test_daten_checker_beheben_links_wirken.py (Links wirken).
"""

from __future__ import annotations

import ast
import importlib
from collections import Counter

import pytest

from backend.services.daten_checker import ziele
from backend.services.daten_checker.handgriffe import ALLOWLIST_AUSKUNFT_WARNUNG, AUSKUNFT, HANDGRIFFE
from backend.tests.werkzeug_daten_checker_stellen import (
    CHECKER_DIR, GRUENDE, altlink_schluessel, baseline_lesen, erzeuger_dateien, stellen,
)

BEFEHL = "python -m backend.tests.werkzeug_daten_checker_stellen --baseline"
BAUER = {n for n in ziele.__all__ if n.startswith("ziel_")}
#: Platzhalter für Laufzeit-Argumente, deren Wert der Bauer nicht prüft (Ids, Monate, Datum).
_PLATZHALTER = {("ziel_monat", 0): 2026, ("ziel_monat", 1): 1, ("ziel_monat_label", 0): "01/2026",
                ("ziel_komponente", 0): 1, ("ziel_tarif", 0): 1, ("ziel_datenquelle_schluessel", 0): "inv:1:aktiv"}
_UNGEPRUEFTE_KW = {"geraet": 1, "ab": "2026-01-01"}
#: Feld-Ausdrücke, die zur Laufzeit entstehen und anderswo geprüft werden (Name → Grund).
DYNAMISCH = {"pflicht_feld": "Aufrufer übergeben Literale — test_pflichtfeld_der_aufrufer_in_der_registry"}


def _module(rel: str):
    return importlib.import_module("backend.services.daten_checker." + rel[:-3].replace("/", "."))


def _kandidaten(knoten, modul) -> list:
    if isinstance(knoten, ast.Constant):
        return [knoten.value]
    if isinstance(knoten, ast.IfExp):
        return _kandidaten(knoten.body, modul) + _kandidaten(knoten.orelse, modul)
    if isinstance(knoten, ast.Name):
        if knoten.id in DYNAMISCH:
            return []
        wert = getattr(modul, knoten.id)
        assert isinstance(wert, str), knoten.id
        return [wert]
    if isinstance(knoten, ast.Subscript) and isinstance(knoten.value, ast.Name):
        return list(getattr(modul, knoten.value.id).values())
    raise AssertionError(f"Feld-Ausdruck nicht prüfbar: {ast.unparse(knoten)}")


def _bauer_aufrufe():
    for pfad in erzeuger_dateien():
        rel = pfad.relative_to(CHECKER_DIR).as_posix()
        for n in ast.walk(ast.parse(pfad.read_text(encoding="utf-8"))):
            if isinstance(n, ast.Call) and getattr(n.func, "id", None) in BAUER:
                yield rel, n


def _aufruf_varianten(name, n, modul):
    args = [a.value if isinstance(a, ast.Constant) else _PLATZHALTER[(name, i)] for i, a in enumerate(n.args)]
    feste, frei = {}, {}
    for k in n.keywords:
        if k.arg in ("feld", "parameter"):
            frei[k.arg] = _kandidaten(k.value, modul)
        elif isinstance(k.value, ast.Constant):
            feste[k.arg] = k.value.value
        else:
            feste[k.arg] = _UNGEPRUEFTE_KW[k.arg]
    if not frei:
        return [(args, feste)]
    (schluessel, werte), = frei.items()
    return [(args, {**feste, schluessel: w}) for w in werte]


# ─── W-2: keine Literale, nur der Ziel-Bauer ──────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("pfad", erzeuger_dateien(), ids=lambda p: p.name)
def test_kein_link_literal_und_keine_link_konstante(pfad):
    baum = ast.parse(pfad.read_text(encoding="utf-8"))
    literale = [n.lineno for n in ast.walk(baum) if isinstance(n, ast.Constant) and isinstance(n.value, str)
                and (n.value.startswith("/einstellungen") or n.value.startswith("/monatsabschluss"))]
    konstanten = [f"{n.lineno} {getattr(n, 'id', getattr(n, 'name', ''))}" for n in ast.walk(baum)
                  if (isinstance(n, ast.Name) and n.id.startswith("LINK_"))
                  or (isinstance(n, ast.alias) and n.name.startswith("LINK_"))]
    assert not literale and not konstanten, f"{pfad.name}: Link-Literal {literale} / LINK_-Konstante {konstanten}"


def test_ziel_und_altlink_nur_benannt():
    verstoss = []
    for s in stellen():
        for kw, gut in (("ziel", _ist_bauer), ("altlink", _ist_heute)):
            if kw in s.kw and not gut(s.kw[kw]):
                verstoss.append(f"{s.datei}:{s.zeile} {kw}={s.quelle(kw)}")
    assert not verstoss, verstoss


def _ist_bauer(k) -> bool:
    if isinstance(k, ast.IfExp):
        return _ist_bauer(k.body) and (isinstance(k.orelse, ast.Constant) and k.orelse.value is None or _ist_bauer(k.orelse))
    return isinstance(k, ast.Call) and getattr(k.func, "id", None) in BAUER


def _ist_heute(k) -> bool:
    if isinstance(k, ast.IfExp):
        return _ist_heute(k.body) and _ist_heute(k.orelse)
    if isinstance(k, ast.Name):
        return k.id == "KEIN_LINK" or k.id.startswith("HEUTE_")
    return isinstance(k, ast.Call) and getattr(k.func, "id", None) == "heute_monat"


def test_jeder_feld_schluessel_steht_in_der_registry():
    """Jede Bauer-Stelle mit ihren Literalen (bzw. den Werten der benannten Konstanten) ausgeführt — wirft nie."""
    geprueft = 0
    for rel, n in _bauer_aufrufe():
        modul = _module(rel)
        for args, kwargs in _aufruf_varianten(n.func.id, n, modul):
            getattr(ziele, n.func.id)(*args, **kwargs)
            geprueft += 1
    assert geprueft > 100  # E2: 132 Varianten (Stellen × Feld-Kandidaten)


def test_pflichtfeld_der_aufrufer_in_der_registry():
    pfad = [p for p in erzeuger_dateien() if p.name == "stammdaten_investitionen.py"][0]
    felder = [n.args[2].value for n in ast.walk(ast.parse(pfad.read_text(encoding="utf-8")))
              if isinstance(n, ast.Call) and getattr(n.func, "attr", None) == "_check_investition_monatsdaten"]
    assert felder and all(isinstance(f, str) for f in felder)
    for f in felder:
        ziele.ziel_monat(2026, 1, geraet=1, feld=f)


def test_sprengsatz_s1_unbekannter_schluessel_wirft():
    with pytest.raises(ValueError):
        ziele.ziel_komponente(1, feld="modul_details")
    # E0 (5): die Erzeuger 168/171 lesen die SPALTE `anschaffungskosten_alternativ`; der gleichnamige Parameter des
    # Typs zählt für eine Spalten-Stelle nicht.
    with pytest.raises(ValueError):
        ziele.ziel_komponente(1, feld="alternativ_kosten_euro")
    ziele.ziel_komponente(1, parameter="alternativ_kosten_euro", typ="e-auto")
    with pytest.raises(ValueError):
        ziele.ziel_komponente(1, parameter="jaz", typ="wallbox")
    with pytest.raises(ValueError):
        ziele.ziel_monat(2026, 1, feld="waerme_gesamt_kwh")
    with pytest.raises(ValueError):
        ziele.ziel_anlage("standort")
    with pytest.raises(ValueError):
        ziele.ziel_tarif(1, feld="strompreis_cent")
    with pytest.raises(ValueError):
        ziele.ziel_block("system", "gibt-es-nicht")
    with pytest.raises(ValueError):
        ziele.ziel_block("system", "protokolle", feld="system_losses")


def test_heutige_lesart_des_links():
    from backend.services.daten_checker.kategorien import LINK_ENERGIEPROFIL, LINK_MONATSDATEN, link_aus_ziel
    assert link_aus_ziel(ziele.ziel_werkbank()) == LINK_ENERGIEPROFIL
    assert link_aus_ziel(ziele.ziel_block("daten", "monatsdaten")) == LINK_MONATSDATEN
    assert link_aus_ziel(ziele.ziel_monat_label("Mai 2026", feld="ladung_kwh")) == LINK_MONATSDATEN
    assert link_aus_ziel(ziele.ziel_monat_label("05/2026", geraet=4, feld="ladung_kwh")) == "/einstellungen/daten?erfassen=2026-05"
    assert link_aus_ziel(ziele.ziel_datenquelle(geraet=4, feld="betriebsmodus-3")) == "/einstellungen/datenquellen"
    assert link_aus_ziel(ziele.ziel_komponente(9, parameter="jaz", typ="waermepumpe")) == "/einstellungen/komponenten?bearbeiten=9"
    assert link_aus_ziel(ziele.ziel_tarif(neu_art="allgemein", ab="2026-01-01")) == "/einstellungen/stammdaten?block=strompreise"
    assert link_aus_ziel(ziele.ziel_block("system", "protokolle")) == "/einstellungen/system?block=protokolle"
    assert link_aus_ziel(ziele.ziel_komponente(5, typ="speicher", jahresbilanz=True)) == "/komponenten/speicher?geraet=5"
    # Ein gespeicherter Schlüssel mit Alt-Namen verliert nur das Feld (Laufzeit-Rohwert, H-E2-1).
    assert ziele.ziel_datenquelle_schluessel("inv:5:kein_feld_xyz").params == {"geraet": 5}


# ─── Übergangsfeld altlink: schrumpfende Baseline ─────────────────────────────────────────────────────────────

def test_altlink_kein_neuer_eintrag():
    neu = altlink_schluessel(stellen()) - baseline_lesen()
    assert not neu, (f"Neue altlink-Stelle(n) — das Teil-B-Ziel muss den Link selbst ergeben:\n  " + "\n  ".join(sorted(neu)))


def test_altlink_baseline_ohne_waise():
    verwaist = baseline_lesen() - altlink_schluessel(stellen())
    assert not verwaist, f"Baseline schrumpft im Commit (`{BEFEHL}`):\n  " + "\n  ".join(sorted(verwaist))


def test_altlink_gruende_benannt():
    assert {z.split("\t")[2] for z in baseline_lesen()} <= set(GRUENDE)


# ─── W-6: Auskunft ohne WARNING/ERROR ────────────────────────────────────────────────────────────────────────

def _auskunft_verstoesse(handgriffe, alle) -> list[str]:
    out = [f"Allowlist-Grund ohne Allowlist: {c}" for c, h in handgriffe.items()
           if h.allowlist_grund and c not in ALLOWLIST_AUSKUNFT_WARNUNG]
    out += [f"Allowlist ohne Grund: {c}" for c in ALLOWLIST_AUSKUNFT_WARNUNG if not handgriffe[c].allowlist_grund]
    for s in alle:
        h = handgriffe.get(s.code)
        if h is None or h.klasse != AUSKUNFT:
            continue
        schwere = ast.unparse(s.kw["schwere"])
        if "INFO" not in schwere and s.code not in ALLOWLIST_AUSKUNFT_WARNUNG:
            out.append(f"{s.datei}:{s.zeile} {s.code} {schwere}")
    return out


def test_w6_auskunft_nur_info_ausser_zwei():
    assert ALLOWLIST_AUSKUNFT_WARNUNG == ("pv_zaehler_steht", "zaehlerstand_reihe_bruch")
    assert _auskunft_verstoesse(HANDGRIFFE, stellen()) == []


def test_w6_ein_dritter_eintrag_waere_rot():
    from dataclasses import replace
    probe = dict(HANDGRIFFE)
    probe["kein_ladetarif"] = replace(probe["kein_ladetarif"], allowlist_grund="Probe")
    probe["zaehler_ruecksprung"] = replace(probe["zaehler_ruecksprung"], klasse=AUSKUNFT)
    v = _auskunft_verstoesse(probe, stellen())
    assert any("kein_ladetarif" in x for x in v) and any("zaehler_ruecksprung" in x for x in v)


def test_ziel_und_aktion_zugleich_gezaehlt():
    """In E2 behalten die Erzeuger ihr heutiges Verhalten; «nie `action` und `ziel`» greift erst mit E3/E4.
    Heute trägt genau eine Stelle beides (Nr 73 `geraetewerte_ohne_monatszeile`: Monat erfassen + Werkbank-Löschen)."""
    beide = Counter(s.code for s in stellen() if "ziel" in s.kw and "action" in s.kw)
    assert beide == {"geraetewerte_ohne_monatszeile": 1}
