"""W-14 «Feld am Gerätetyp» — ein Sprungziel zeigt nur auf ein Feld, das es am Gerät des Ziels gibt (Etappe E6.D D3 des
Vorhabens «Daten-Checker: ein Handgriff je Befund», Auftrag `auftrag-daten-checker-e6.md` Teil D; Bauplan §1 «Kein Knopf
ohne Wirkung»).

**Der Fall** (Lesedurchgang der Lösungswege, 11.11.2026, Code-Verdachte 1, 2, 3, 5): vier Knöpfe landeten an einem Ort, an
dem es ihr Feld nicht gibt — der Sprung (`lib/sprungFeld.ts`) wartet dann fünf Sekunden und tut nichts:

1. `emob_kennung_unbekannt` öffnete die **Wallbox** am E-Auto-Parameter «Kennung in der Steuerung»;
2. `evcc_netzladung_abweichung` zeigte an der Wallbox auf `ladung_netz_kwh` — das Feld gibt es nur an Speicher und E-Auto;
3. `wallbox_netzladung_groesser_gemeinsamer_netzbezug` zeigte **ohne Gerät** auf `ladung_netz_kwh` ⇒ die Zuordnung sprang
   zum ersten Gerät mit dem Feld (Speicher/E-Auto), nie zur Wallbox;
4. `md_batterie_ladung_fehlt`/`…_entladung_fehlt` zeigten auf «Batterie Ladung/Entladung» der Monatszeile — das Formular
   zeigt sie nur **ohne** Speicher (`MonatsdatenForm.tsx`, Abschnitt «Batterie (optional)»), der Befund setzt einen voraus.

W-2 (`test_daten_checker_ziele.py`) prüft, dass ein Feld-Schlüssel in **irgendeiner** Registry steht; W-5 prüft, dass die
Zielseite den Parameter liest. Keiner fragt, ob das Feld **an diesem Gerät** steht — genau diese Lücke schließt W-14.

**Die Regel** (Master-Entscheid E6.D):

* Ziel mit Feld **und** Gerät ⇒ das Feld gibt es für den Typ des Geräts (Datenquellen/Monat: `INVESTITION_FELDER` und die
  übrigen Registries über `feld_auswertungen.alle_registry_felder`; Komponenten-Formular: Parameter des Typs bzw. Spalte).
* Ziel mit Feld **ohne** Gerät ⇒ das Feld ist ein Basisfeld der Zielfläche oder liegt an genau einem Gerätetyp.
  Basis der Datenquellen-Fläche = die Anlagen-Felder der Registry; Basis des Monatsabschlusses = dazu die Spalten der
  Monatszeile (`Monatsdaten`), die das Formular auf Anlagen-Ebene zeigt — «Batterie Ladung/Entladung» nur ohne Speicher
  (`BASIS_NUR_OHNE_TYP`).

**Zwei Teile.** (A) **statisch über alle Aufrufstellen** der Ziel-Bauer `ziel_datenquelle`/`ziel_monat`/`ziel_monat_label`
(AST): ohne Gerät gilt die Regel für jeden aus dem Quelltext auflösbaren Feld-Schlüssel; mit Gerät muss das Feld an
mindestens einem Gerätetyp stehen. (B) **zur Laufzeit** — der Typ eines Geräts steht erst in der Datenbank: die vier Fälle
oben als Szenarien über ihre Erzeuger (Sprengsatz: vorher rot, nachher grün), geprüft mit demselben Prädikat.

⚑ **Benannte Ausnahmen** (`AUSNAHMEN`): Stellen derselben Klasse, die der Auftrag E6.D nicht nennt — sie stehen hier mit
Grund, bis der Master entscheidet; ein verwaister Eintrag ist rot (die Liste schrumpft nur).

Schwesterdateien: `test_daten_checker_ziele.py` (W-2), `test_daten_checker_beheben_links_wirken.py` (W-5),
`test_p433_2b_k2a_fahrzeug.py` (Fall 1 im Detail).
"""

from __future__ import annotations

import ast
from datetime import date
from functools import lru_cache
from pathlib import Path
from types import SimpleNamespace
from typing import Optional

import pytest
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from backend.models.anlage import Anlage
from backend.models.investition import Investition, InvestitionMonatsdaten
from backend.models.monatsdaten import Monatsdaten
from backend.models.strompreis import Strompreis
from backend.services.daten_checker import DatenChecker
from backend.services.daten_checker.kategorien import Ziel

CHECKER_DIR = Path(__file__).resolve().parents[1] / "services" / "daten_checker"
#: Die Ziel-Bauer, die ein Feld der Datenquellen-Fläche bzw. des Monatsabschlusses tragen.
BAUER_MIT_FELD = ("ziel_datenquelle", "ziel_monat", "ziel_monat_label")
#: Basisfelder des Monatsabschlusses, die das Formular nur zeigt, solange kein Gerät des Typs aktiv ist
#: (`MonatsdatenForm.tsx`: `{!hatSpeicher && (<FormSection title="Batterie (optional)">…`).
BASIS_NUR_OHNE_TYP = {"batterie_ladung_kwh": "speicher", "batterie_entladung_kwh": "speicher"}
#: ⚑ Benannte Ausnahmen (datei, code) → Grund. Nur schrumpfen; ein Eintrag ohne Treffer ist rot.
AUSNAHMEN: dict[tuple[str, str], str] = {}
#: (H-E6-11 ⇒ Option A, Master 11.11.2026: die zwei Ausnahmen `tarif_mengenfeld_groesser_als_menge`/`_rest` sind entfallen —
#: sie nennen jetzt das Gerät wie Fall 3; Laufzeit-Fälle unten.)


# ─── Das Prädikat ─────────────────────────────────────────────────────────────────────────────────────────────
@lru_cache(maxsize=1)
def _typen_je_feld() -> dict[str, frozenset[str]]:
    from backend.core.feld_auswertungen import alle_registry_felder
    out: dict[str, set[str]] = {}
    for typ, feld in alle_registry_felder():
        out.setdefault(feld, set()).add(typ)
    return {f: frozenset(t) for f, t in out.items()}


@lru_cache(maxsize=1)
def _basis() -> tuple[frozenset[str], frozenset[str]]:
    """(Basis der Datenquellen-Fläche, Basis des Monatsabschlusses)."""
    from backend.core.feld_auswertungen import TYP_ANLAGE
    registry = frozenset(f for f, t in _typen_je_feld().items() if TYP_ANLAGE in t)
    monat = registry | frozenset(c.name for c in Monatsdaten.__table__.columns)
    return registry, monat


def _geraete_typen(feld: str) -> frozenset[str]:
    from backend.core.feld_auswertungen import TYP_ANLAGE
    return _typen_je_feld().get(feld, frozenset()) - {TYP_ANLAGE}


def verstoss_ohne_geraet(feld: str, *, monat: bool, aktive_typen: Optional[set[str]] = None) -> Optional[str]:
    """Ziel mit Feld ohne Gerät: Basisfeld der Fläche oder genau ein Gerätetyp — sonst der Grund."""
    from backend.core.field_definitions.keys import basis_feld_key
    b = basis_feld_key(feld)
    if b in _basis()[1 if monat else 0]:
        nur_ohne = BASIS_NUR_OHNE_TYP.get(b) if monat else None
        if nur_ohne is not None and aktive_typen is not None and nur_ohne in aktive_typen:
            return f"Feld {feld!r} zeigt das Formular nur ohne Gerät des Typs {nur_ohne!r} — die Anlage hat eines"
        return None
    typen = _geraete_typen(b)
    if len(typen) == 1:
        return None
    return f"Feld {feld!r} ohne Gerät liegt an {sorted(typen) or 'keinem Typ'} — der Sprung findet kein bestimmtes Feld"


def verstoss(ziel: Optional[Ziel], typ_je_id: dict[int, str], aktive_typen: set[str]) -> Optional[str]:
    """Der Grund, warum `ziel` auf ein Feld zeigt, das es am Ziel nicht gibt — oder ``None``."""
    from backend.core.field_definitions.keys import basis_feld_key
    from backend.services.daten_checker.ziele import _modell_spalten, _parameter_je_typ
    if ziel is None:
        return None
    p = ziel.params
    feld = p.get("feld")
    if feld is None:
        return None
    if ziel.bereich == "komponenten":
        typ = typ_je_id[int(p["bearbeiten"])]
        if (ziel.anker or "").startswith("param_"):
            ok = feld in _parameter_je_typ().get(typ, frozenset())
        else:
            ok = feld in _modell_spalten()["investition"]
        return None if ok else f"Komponenten-Formular {typ!r} kennt {feld!r} nicht"
    monat = (ziel.bereich, ziel.block) == ("daten", "monatsdaten")
    if not monat and ziel.bereich != "datenquellen":
        return None
    geraet = p.get("geraet")
    if geraet is None:
        return verstoss_ohne_geraet(feld, monat=monat, aktive_typen=aktive_typen)
    typ = typ_je_id[int(geraet)]
    return None if typ in _geraete_typen(basis_feld_key(feld)) else f"Feld {feld!r} gibt es am Typ {typ!r} nicht"


# ─── Teil A: statisch über alle Aufrufstellen ─────────────────────────────────────────────────────────────────
def _werte(knoten: ast.AST, modul: ast.Module) -> set[str]:
    """Alle Feld-Schlüssel, die ein Ausdruck annehmen kann; ``?…`` = nicht auflösbar (Laufzeit-Wert)."""
    if isinstance(knoten, ast.Constant) and isinstance(knoten.value, str):
        return {knoten.value}
    if isinstance(knoten, ast.IfExp):
        return _werte(knoten.body, modul) | _werte(knoten.orelse, modul)
    name = knoten.id if isinstance(knoten, ast.Name) else (
        knoten.value.id if isinstance(knoten, ast.Subscript) and isinstance(knoten.value, ast.Name) else None)
    for n in modul.body:
        ziele = n.targets if isinstance(n, ast.Assign) else [n.target] if isinstance(n, ast.AnnAssign) else []
        if name is not None and any(getattr(t, "id", None) == name for t in ziele) and n.value is not None:
            if isinstance(knoten, ast.Subscript) and isinstance(n.value, ast.Dict):
                return set().union(*(_werte(v, modul) for v in n.value.values))
            if isinstance(knoten, ast.Name):
                return _werte(n.value, modul)
    return {f"?{ast.unparse(knoten)}"}


def _aufrufstellen() -> list[tuple[str, int, str, Optional[str], bool, set[str]]]:
    """(datei, zeile, bauer, code, mit_geraet, feld-werte) je Aufruf eines Bauers mit `feld=`."""
    out = []
    for pfad in sorted(CHECKER_DIR.rglob("*.py")):
        if pfad.name == "ziele.py" or "__pycache__" in pfad.parts:
            continue
        rel = pfad.relative_to(CHECKER_DIR).as_posix()
        modul = ast.parse(pfad.read_text(encoding="utf-8"))
        code_je_aufruf: dict[int, str] = {}
        for n in ast.walk(modul):
            if isinstance(n, ast.Call) and getattr(n.func, "id", None) == "CheckErgebnis":
                kw = {k.arg: k.value for k in n.keywords if k.arg}
                if isinstance(kw.get("code"), ast.Constant) and "ziel" in kw:
                    for m in ast.walk(kw["ziel"]):
                        code_je_aufruf[id(m)] = kw["code"].value
        for n in ast.walk(modul):
            if isinstance(n, ast.Call) and getattr(n.func, "id", None) in BAUER_MIT_FELD:
                kw = {k.arg: k.value for k in n.keywords if k.arg}
                if "feld" in kw:
                    out.append((rel, n.lineno, n.func.id, code_je_aufruf.get(id(n)), "geraet" in kw,
                                _werte(kw["feld"], modul)))
    return out


def test_w14_statisch_ohne_geraet_basis_oder_ein_typ():
    rot, benutzt = [], set()
    for datei, zeile, bauer, code, mit_geraet, werte in _aufrufstellen():
        if mit_geraet:
            continue
        for feld in sorted(w for w in werte if not w.startswith("?")):
            grund = verstoss_ohne_geraet(feld, monat=bauer != "ziel_datenquelle")
            if grund is None:
                continue
            if (Path(datei).name, code) in AUSNAHMEN:
                benutzt.add((Path(datei).name, code))
                continue
            rot.append(f"{datei}:{zeile} {bauer} ({code}): {grund}")
    assert not rot, "W-14: Ziel mit Feld ohne Gerät, das nicht eindeutig ist:\n" + "\n".join(rot)
    assert benutzt == set(AUSNAHMEN), f"W-14: verwaiste Ausnahme(n) {sorted(set(AUSNAHMEN) - benutzt)} — streichen"


def test_w14_statisch_mit_geraet_feld_an_einem_geraetetyp():
    rot = []
    for datei, zeile, bauer, code, mit_geraet, werte in _aufrufstellen():
        if not mit_geraet:
            continue
        from backend.core.field_definitions.keys import basis_feld_key
        for feld in sorted(w for w in werte if not w.startswith("?")):
            if not _geraete_typen(basis_feld_key(feld)):
                rot.append(f"{datei}:{zeile} {bauer} ({code}): {feld!r} steht an keinem Gerätetyp")
    assert not rot, "W-14: Ziel mit Gerät auf ein Feld ohne Gerätetyp:\n" + "\n".join(rot)


def test_w14_statisch_sieht_die_aufrufstellen():
    """Zähne der Sammlung: ohne die Stellen wäre Teil A still grün."""
    stellen = _aufrufstellen()
    assert len(stellen) >= 40, f"nur {len(stellen)} Aufrufstellen gefunden — Sammlung prüfen"
    assert {s[2] for s in stellen} == set(BAUER_MIT_FELD)


def test_w14_praedikat_hat_zaehne():
    typen = {1: "wallbox", 2: "e-auto", 3: "speicher"}
    rot = [
        Ziel("komponenten", None, {"bearbeiten": 1, "feld": "kennung_in_steuerung"}, anker="param_kennung_in_steuerung"),
        Ziel("datenquellen", None, {"geraet": 1, "feld": "ladung_netz_kwh"}, anker="ladung_netz_kwh"),
        Ziel("datenquellen", None, {"feld": "ladung_netz_kwh"}, anker="ladung_netz_kwh"),
        Ziel("daten", "monatsdaten", {"erfassen": "2026-01", "feld": "batterie_ladung_kwh"}, anker="batterie_ladung_kwh"),
    ]
    gruen = [
        Ziel("komponenten", None, {"bearbeiten": 2, "feld": "kennung_in_steuerung"}, anker="param_kennung_in_steuerung"),
        Ziel("datenquellen", None, {"geraet": 2, "feld": "ladung_netz_kwh"}, anker="ladung_netz_kwh"),
        Ziel("datenquellen", None, {"feld": "pv_gesamt_kwh"}, anker="pv_gesamt_kwh"),
        Ziel("daten", "monatsdaten", {"erfassen": "2026-01", "geraet": 3, "feld": "ladung_kwh"}, anker="ladung_kwh"),
    ]
    assert [verstoss(z, typen, {"speicher"}) is not None for z in rot] == [True] * 4
    assert [verstoss(z, typen, {"speicher"}) for z in gruen] == [None] * 4
    # Ohne Speicher sind «Batterie Ladung/Entladung» der Monatszeile ein gültiges Ziel.
    assert verstoss(rot[3], typen, set()) is None


# ─── Teil B: die vier Fälle zur Laufzeit (Sprengsatz) ─────────────────────────────────────────────────────────
async def _pruefe(db, anlage_id: int, ergebnisse, heute: date) -> list[str]:
    invs = (await db.execute(select(Investition).where(Investition.anlage_id == anlage_id))).scalars().all()
    typ_je_id = {i.id: i.typ for i in invs}
    aktive = {i.typ for i in invs if i.ist_aktiv_an(heute)}
    return [f"{e.code}: {g}" for e in ergebnisse if (g := verstoss(e.ziel, typ_je_id, aktive))]


async def test_w14_fall1_kennung_unbekannt_springt_zum_e_auto(db, monkeypatch):
    from backend.services import betriebsmodus_live

    anlage = Anlage(anlagenname="W-14 Fall 1", leistung_kwp=10.0, installationsdatum=date(2025, 1, 1))
    db.add(anlage)
    await db.flush()
    wb = Investition(anlage_id=anlage.id, typ="wallbox", bezeichnung="Carport", anschaffungsdatum=date(2025, 1, 1))
    ea = Investition(anlage_id=anlage.id, typ="e-auto", bezeichnung="Smart", anschaffungsdatum=date(2025, 1, 1),
                     parameter={"kennung_in_steuerung": "Smart"})
    db.add_all([wb, ea])
    await db.commit()

    async def _fremd(_anlage, ziele):
        return {(inv_id, "fahrzeug_am_ladepunkt"): "fremd" for inv_id in ziele}

    monkeypatch.setattr(betriebsmodus_live, "_erhebe_emob", _fremd)
    (m,) = await DatenChecker(db)._check_emob_kennung_unbekannt(anlage)
    assert m.code == "emob_kennung_unbekannt" and m.investition_id == wb.id
    assert await _pruefe(db, anlage.id, [m], date(2026, 1, 1)) == []
    assert m.ziel.params == {"bearbeiten": ea.id, "feld": "kennung_in_steuerung"}


#: Fall 2: zwölf abgeschlossene Monate vor Oktober 2026 (wie `test_n767_wp_eigener_tarif.py`).
_HEUTE_F2 = date(2026, 10, 24)
_FENSTER_F2 = [(2025, m) for m in (10, 11, 12)] + [(2026, m) for m in range(1, 10)]


async def test_w14_fall2_evcc_abweichung_springt_ohne_feld_zur_wallbox(db):
    anlage = Anlage(anlagenname="W-14 Fall 2", leistung_kwp=10.0, installationsdatum=date(2024, 1, 1))
    db.add(anlage)
    await db.flush()
    db.add(Strompreis(anlage_id=anlage.id, verwendung="allgemein", gueltig_ab=date(2024, 1, 1),
                      netzbezug_arbeitspreis_cent_kwh=30.0, einspeiseverguetung_cent_kwh=8.0))
    db.add(Strompreis(anlage_id=anlage.id, verwendung="wallbox", gueltig_ab=date(2024, 1, 1),
                      netzbezug_arbeitspreis_cent_kwh=20.0, einspeiseverguetung_cent_kwh=0.0))
    wb = Investition(anlage_id=anlage.id, typ="wallbox", bezeichnung="Garage", anschaffungsdatum=date(2024, 1, 1))
    db.add(wb)
    await db.flush()
    for jahr, monat in _FENSTER_F2:
        db.add(Monatsdaten(anlage_id=anlage.id, jahr=jahr, monat=monat, netzbezug_kwh=200.0, einspeisung_kwh=300.0))
        db.add(InvestitionMonatsdaten(investition_id=wb.id, jahr=jahr, monat=monat, verbrauch_daten={
            "ladung_kwh": 100.0, "ladung_pv_kwh": 40.0, "ladung_netz_kwh": 60.0, "netzbezug_eigener_tarif_kwh": 40.0}))
    await db.commit()
    anlage = (await db.execute(select(Anlage).options(selectinload(Anlage.strompreise), selectinload(Anlage.investitionen))
                               .where(Anlage.id == anlage.id))).scalar_one()
    erg = [e for e in await DatenChecker(db)._check_wp_eigener_tarif(anlage, heute=_HEUTE_F2)
           if e.code == "evcc_netzladung_abweichung"]
    assert len(erg) == 1
    assert await _pruefe(db, anlage.id, erg, _HEUTE_F2) == []
    assert erg[0].ziel.params == {"geraet": wb.id}


async def test_w14_fall3_gemeinsamer_zaehler_springt_zur_waermepumpe(db):
    """Gemeinsamer Tarif WP + Wallbox (F12): Juni 2025, N_g 50 an der WP, Netzladung der Wallbox 80 ⇒ «N_wb > N_g»."""
    from backend.services.provenance import seed_provenance

    feld = "netzbezug_eigener_tarif_kwh"
    anlage = Anlage(anlagenname="W-14 Fall 3", leistung_kwp=10.0, installationsdatum=date(2024, 1, 1))
    db.add(anlage)
    await db.flush()
    db.add(Strompreis(anlage_id=anlage.id, verwendung="allgemein", gueltig_ab=date(2024, 1, 1),
                      netzbezug_arbeitspreis_cent_kwh=30.0, einspeiseverguetung_cent_kwh=8.0, grundpreis_euro_monat=14.0))
    db.add(Strompreis(anlage_id=anlage.id, verwendung="waermepumpe_wallbox", gueltig_ab=date(2024, 1, 1),
                      netzbezug_arbeitspreis_cent_kwh=22.0, einspeiseverguetung_cent_kwh=0.0, grundpreis_euro_monat=10.0))
    pv = Investition(anlage_id=anlage.id, typ="pv-module", bezeichnung="Dach", leistung_kwp=10.0,
                     anschaffungsdatum=date(2024, 1, 1))
    wp = Investition(anlage_id=anlage.id, typ="waermepumpe", bezeichnung="WP", anschaffungsdatum=date(2024, 1, 1),
                     parameter={"effizienz_modus": "gesamt_jaz", "jaz": 3.5, "wp_art": "luft_wasser"})
    wb = Investition(anlage_id=anlage.id, typ="wallbox", bezeichnung="Garage", anschaffungsdatum=date(2024, 1, 1))
    db.add_all([pv, wp, wb])
    await db.flush()
    db.add(InvestitionMonatsdaten(investition_id=pv.id, jahr=2025, monat=6, verbrauch_daten={"pv_erzeugung_kwh": 600.0}))
    db.add(InvestitionMonatsdaten(investition_id=wp.id, jahr=2025, monat=6,
                                  verbrauch_daten={"stromverbrauch_kwh": 300.0, "heizenergie_kwh": 1050.0, feld: 50.0}))
    db.add(InvestitionMonatsdaten(investition_id=wb.id, jahr=2025, monat=6,
                                  verbrauch_daten={"ladung_kwh": 200.0, "ladung_pv_kwh": 120.0, "ladung_netz_kwh": 80.0}))
    md = Monatsdaten(anlage_id=anlage.id, jahr=2025, monat=6, netzbezug_kwh=400.0, einspeisung_kwh=100.0)
    db.add(md)
    await db.flush()
    seed_provenance(md, source="manual:form", writer="test", fields=["einspeisung_kwh", "netzbezug_kwh"])
    await db.commit()
    anlage = (await db.execute(select(Anlage).options(selectinload(Anlage.strompreise), selectinload(Anlage.investitionen))
                               .where(Anlage.id == anlage.id))).scalar_one()
    heute = date(2025, 7, 15)
    erg = [e for e in await DatenChecker(db)._check_wp_eigener_tarif(anlage, heute=heute)
           if e.code == "wallbox_netzladung_groesser_gemeinsamer_netzbezug"]
    assert len(erg) == 1
    assert await _pruefe(db, anlage.id, erg, heute) == []
    assert erg[0].ziel.params == {"geraet": wp.id, "feld": feld}


@pytest.mark.parametrize("code, strom, n, netz", [
    ("tarif_mengenfeld_groesser_als_menge", 100.0, 150.0, 400.0),   # N über dem WP-Strom (Toleranz 2 %)
    ("tarif_mengenfeld_groesser_als_rest", 300.0, 250.0, 200.0),    # N über dem Netzbezug der Anlage
])
async def test_w14_h_e6_11_tarif_mengenfeld_springt_zur_waermepumpe(db, code, strom, n, netz):
    """H-E6-11 ⇒ Option A: «Netzbezug zum WP-Tarif» tragen Wärmepumpe UND Wallbox — ohne Gerät sprang die Zuordnung zum
    ersten Gerät mit dem Feld. Jetzt das Gerät der Verwendung (hier die Wärmepumpe) am Feld."""
    from backend.services.provenance import seed_provenance

    feld = "netzbezug_eigener_tarif_kwh"
    anlage = Anlage(anlagenname=f"W-14 {code}", leistung_kwp=10.0, installationsdatum=date(2024, 1, 1))
    db.add(anlage)
    await db.flush()
    db.add(Strompreis(anlage_id=anlage.id, verwendung="allgemein", gueltig_ab=date(2024, 1, 1),
                      netzbezug_arbeitspreis_cent_kwh=30.0, einspeiseverguetung_cent_kwh=8.0))
    db.add(Strompreis(anlage_id=anlage.id, verwendung="waermepumpe", gueltig_ab=date(2024, 1, 1),
                      netzbezug_arbeitspreis_cent_kwh=20.0, einspeiseverguetung_cent_kwh=0.0))
    wp = Investition(anlage_id=anlage.id, typ="waermepumpe", bezeichnung="WP", anschaffungsdatum=date(2024, 1, 1),
                     parameter={"wp_art": "luft_wasser"})
    wb = Investition(anlage_id=anlage.id, typ="wallbox", bezeichnung="Garage", anschaffungsdatum=date(2024, 1, 1))
    db.add_all([wp, wb])
    await db.flush()
    db.add(InvestitionMonatsdaten(investition_id=wp.id, jahr=2026, monat=9,
                                  verbrauch_daten={"stromverbrauch_kwh": strom, feld: n}))
    md = Monatsdaten(anlage_id=anlage.id, jahr=2026, monat=9, netzbezug_kwh=netz, einspeisung_kwh=300.0)
    db.add(md)
    await db.flush()
    seed_provenance(md, source="manual:form", writer="test", fields=["einspeisung_kwh", "netzbezug_kwh"])
    await db.commit()
    anlage = (await db.execute(select(Anlage).options(selectinload(Anlage.strompreise), selectinload(Anlage.investitionen))
                               .where(Anlage.id == anlage.id))).scalar_one()
    erg = [e for e in await DatenChecker(db)._check_wp_eigener_tarif(anlage, heute=_HEUTE_F2) if e.code == code]
    assert len(erg) == 1
    assert await _pruefe(db, anlage.id, erg, _HEUTE_F2) == []
    assert erg[0].ziel.params == {"geraet": wp.id, "feld": feld}


def test_w14_fall4_batterie_legacy_springt_in_die_geraetezeile():
    """Speicher aktiv, Monat ohne Gerätezeile, «Batterie Ladung/Entladung» der Monatszeile leer ⇒ die zwei Legacy-Befunde
    springen in die Gerätezeile des Speichers (das Formular zeigt die Batterie-Felder der Monatszeile mit Speicher nicht)."""
    from backend.services.daten_checker.monatsdaten_plausibilitaet import _batterie_legacy_fehlt, _speicher_index

    sp = SimpleNamespace(id=5, typ="speicher", aktiv=True, anschaffungsdatum=date(2025, 1, 1), stilllegungsdatum=None,
                         monatsdaten=[], parameter={})
    md = SimpleNamespace(jahr=2025, monat=3, batterie_ladung_kwh=None, batterie_entladung_kwh=None)
    bat, _netz, aktiv_monate, _ohne = _speicher_index(SimpleNamespace(investitionen=[sp]), [md])
    erg = _batterie_legacy_fehlt("monatsdaten", "03/2025", md, hat_speicher=True,
                                 speicher_aktiv_monate=aktiv_monate, speicher_imd_monate=set(bat))
    assert [e.code for e in erg] == ["md_batterie_ladung_fehlt", "md_batterie_entladung_fehlt"]
    gruende = [g for e in erg if (g := verstoss(e.ziel, {5: "speicher"}, {"speicher"}))]
    assert gruende == [], gruende
    assert [e.ziel.params for e in erg] == [{"erfassen": "2025-03", "geraet": 5, "feld": "ladung_kwh"},
                                            {"erfassen": "2025-03", "geraet": 5, "feld": "entladung_kwh"}]


@pytest.mark.parametrize("code", ["emob_kennung_unbekannt", "evcc_netzladung_abweichung",
                                  "wallbox_netzladung_groesser_gemeinsamer_netzbezug", "md_batterie_ladung_fehlt"])
def test_w14_die_vier_codes_sind_sprung_codes(code):
    """Der Knopf bleibt ein Sprung (Katalog unverändert) — W-14 ändert das Ziel, nicht die Klasse."""
    from backend.services.daten_checker.handgriffe import HANDGRIFFE, SPRUNG
    assert HANDGRIFFE[code].klasse == SPRUNG
