"""W-4 Mechanik-Wörter (Etappe E3, Bauplan §4; Konzept §3.1 R4; Gegenprüfung Ü3).

Der Knopf eines Befunds und die **eine** Vorschau-Zeile je Operation sprechen Anwender-Sprache: kein Wort aus
``handgriffe.MECHANIK_WOERTER`` (Spiegel, Kanal, LTS, Statistics, Snapshot, aggregier, Provenance, Resnap) und kein
Menüweg-Pfeil «→». Geprüft werden
* die Knopf-Texte des Katalogs (``HANDGRIFFE[*].knopf``) und je Operation (``KNOPF_JE_OPERATION``, daraus
  ``CheckErgebnis.knopf``);
* die Beschriftungen der Vorschau-Zähler, die die Operationen der Checker-Knöpfe liefern (``REPARATUR_AENDERUNG_LABELS`` in
  ``frontend/src/lib/constants.ts``) — jeder Schlüssel hat eine;
* die Satzteile der Vorschau-Zeile im Client (``frontend/src/components/datenchecker/vorschauZeile.ts``).
**Ausgenommen:** die Werkbank-Warnungen (``RepairPlan.warnings``), die der Kasten unverändert zeigt (Ü3).
**Seit E4 auch Meldung und Details** (Konzept §2 Nr 4, §3.1 R4): kein eedc-Menüweg «Bereich → …» in einem Text-Literal der
Erzeuger — der Knopf ist der Weg. Erlaubt bleiben die drei Home-Assistant-Wege (``HA_WEGE``) und Werteübergänge
(«Stand a → b», «PV x → HA y», «7130 kWh → 7130 W» — kein Bereichsname vor dem Pfeil).

Schwesterdateien: ``test_daten_checker_codes.py`` (W-1), ``test_daten_checker_ziele.py`` (W-2/W-6),
``test_daten_checker_handgriff_wirkt.py`` (W-11), ``test_repair_operationen_checker.py``.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from backend.services.daten_checker.handgriffe import HANDGRIFFE, KNOPF_JE_OPERATION, MECHANIK_WOERTER

FRONTEND = Path(__file__).resolve().parents[2] / "frontend" / "src"
KONSTANTEN = FRONTEND / "lib" / "constants.ts"
VORSCHAU = FRONTEND / "components" / "datenchecker" / "vorschauZeile.ts"

#: Die Zähler der Vorschau je Operation eines Checker-Knopfs (Vertrag mit ``estimated_changes`` der Pläne;
#: die vier neuen in ``test_repair_operationen_checker.py``, REAGGREGATE_DAY in ``test_repair_orchestrator.py``).
VORSCHAU_SCHLUESSEL = {
    "reaggregate_day": ("boundaries_changed", "slots_changed", "counter_fields_changed"),
    "reaggregate_range": ("anzahl_tage", "tage_mit_bestehender_zusammenfassung"),
    "kraftstoffpreis_backfill": ("monats_offen", "tages_offen"),
    "wetter_backfill": ("monate_gesamt", "monate_mit_werten", "monate_ohne_werte"),
    "temperatur_aus_messung": ("monate_temperatur_gefuellt", "monate_ohne_temperatur"),
    "feldwert_entfernen": ("monate_wert_entfernt",),
    "geraetewerte_loeschen": ("geraetewerte_zeilen_geloescht",),
    "spiegel_abgleich_tag": ("spiegel_kanaele", "spiegel_abschnitte", "tage_neu_aufgebaut"),
}


def _verstoesse(text: str) -> list[str]:
    klein = text.lower()
    return [w for w in MECHANIK_WOERTER if w in klein] + (["→"] if "→" in text else [])


def _labels() -> dict[str, str]:
    quelle = KONSTANTEN.read_text(encoding="utf-8")
    block = quelle.split("export const REPARATUR_AENDERUNG_LABELS", 1)[1].split("\n}\n", 1)[0]
    return dict(re.findall(r"^\s*(\w+):\s*'([^']*)'", block, re.M))


@pytest.mark.parametrize("code", sorted(c for c, h in HANDGRIFFE.items() if h.knopf))
def test_knopf_text_des_katalogs_ohne_mechanik(code):
    assert _verstoesse(HANDGRIFFE[code].knopf) == [], (code, HANDGRIFFE[code].knopf)
    # E5.7 L1: auch der Sprung-Knopf eines Aktion-Codes ohne Reparaturweg (`knopf_sprung`) und nie das alte «Beheben».
    assert _verstoesse(HANDGRIFFE[code].knopf_sprung or "") == [], (code, HANDGRIFFE[code].knopf_sprung)
    assert HANDGRIFFE[code].knopf != "Beheben"


def test_knopf_text_je_operation_ohne_mechanik_und_im_katalog():
    for op, text in KNOPF_JE_OPERATION.items():
        assert _verstoesse(text) == [], (op, text)
    aktion_knoepfe = {h.knopf for h in HANDGRIFFE.values() if h.klasse == "aktion"}
    assert aktion_knoepfe <= set(KNOPF_JE_OPERATION.values()), aktion_knoepfe - set(KNOPF_JE_OPERATION.values())


def test_jeder_vorschau_zaehler_hat_eine_beschriftung_ohne_mechanik():
    labels = _labels()
    assert set(VORSCHAU_SCHLUESSEL) == set(KNOPF_JE_OPERATION) | {"geraetewerte_loeschen"}
    for op, schluessel in VORSCHAU_SCHLUESSEL.items():
        for k in schluessel:
            assert labels.get(k), f"{op}: kein Label für {k}"
            assert _verstoesse(labels[k]) == [], (k, labels[k])


def test_satzteile_der_vorschau_zeile_ohne_mechanik():
    quelle = VORSCHAU.read_text(encoding="utf-8")
    code = re.sub(r"/\*.*?\*/|//[^\n]*", "", quelle, flags=re.S)
    texte = re.findall(r"'([^'\n]*)'|`([^`]*)`", code)
    saetze = [a or b for a, b in texte if (a or b) and re.search(r"[a-zäöü]{3} ", (a or b))]
    assert saetze, "keine Satzteile gefunden — Datei verschoben?"
    for s in saetze:
        assert _verstoesse(s) == [], s
    assert "endgültig" in quelle and "wirksam, wenn du in Home Assistant korrigiert hast" in quelle


# ── E4: Menüwege in Meldung/Details (Erhebung Teil A Aufgabe 2: 24 Wortlaute an 56 Stellen) ─────────────────────────

CHECKER = Path(__file__).resolve().parents[1] / "services" / "daten_checker"
#: Wege in der Oberfläche von Home Assistant — eedc kann dorthin nicht springen, der Text ist der Weg (M10, M23, M24).
HA_WEGE = (
    "Einstellungen → Geräte & Dienste → Helfer",
    "Entwicklerwerkzeuge → Statistik → den Sensor suchen → beim Symbol",
    "Helfer → „Integral-Sensor“",
)
#: Ein Bereich bzw. Block der eedc-Oberfläche vor einem Pfeil = Menüweg.
MENUEWEG = re.compile(
    r"(Einstellungen|Cockpit|Aussichten?|Auswertungen|Komponenten|Investitionen|Stammdaten|Anlage|Strompreise|"
    r"Solarprognose|Daten|Datenquellen|Datenverwaltung|Integration|Energieprofil(-Pflege)?|Reparatur-Werkbank|"
    r"Monatsdaten|System)\s*(→|->)"
)


def _menuewege(text: str) -> list[str]:
    for weg in HA_WEGE:
        text = text.replace(weg, "")
    return [m.group(0) for m in MENUEWEG.finditer(text)]


def _text_literale():
    """Alle Text-Literale der Erzeuger (Konstanten und f-String-Teile, ohne Docstrings und Kommentare)."""
    import ast

    for pfad in sorted(CHECKER.rglob("*.py")):
        baum = ast.parse(pfad.read_text(encoding="utf-8"))
        doc = {id(n.body[0].value) for n in ast.walk(baum)
               if isinstance(n, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)) and n.body
               and isinstance(n.body[0], ast.Expr) and isinstance(n.body[0].value, ast.Constant)}
        for n in ast.walk(baum):
            if isinstance(n, ast.JoinedStr):
                yield pfad.name, n.lineno, "".join(v.value if isinstance(v, ast.Constant) else "{}" for v in n.values)
            elif isinstance(n, ast.Constant) and isinstance(n.value, str) and id(n) not in doc:
                yield pfad.name, n.lineno, n.value


def test_meldung_und_details_ohne_menueweg():
    verstoss = [f"{d}:{z} {_menuewege(t)}" for d, z, t in _text_literale() if _menuewege(t)]
    assert not verstoss, "Menüweg im Befund-Text — der Knopf ist der Weg (Konzept §3.1 R4):\n  " + "\n  ".join(verstoss)


def test_menueweg_waechter_hat_zaehne():
    assert _menuewege("unter Einstellungen → Datenquellen zuordnen") == ["Einstellungen →"]
    assert _menuewege("Cockpit → Jahr und Aussichten → Finanzen") == ["Cockpit →", "Aussichten →"]
    assert _menuewege("in Home Assistant unter Einstellungen → Geräte & Dienste → Helfer einen Zähler") == []
    assert _menuewege("Stand 12 → 3 → zurück; 7130 kWh → 7130 W; PV {} → HA {}") == []
    assert sum(1 for _ in _text_literale()) > 500


def test_der_waechter_hat_zaehne():
    assert _verstoesse("Spiegel abgleichen") == ["spiegel"]
    assert _verstoesse("Einstellungen → Daten") == ["→"]
    assert _verstoesse("Tag neu aufbauen") == []


# ── Lösungsweg-Anker (E3, Konzept §3.5): Katalog, Client-Tabelle und Handbuch gleich ──────────────────────────────

KATEGORIEN_TS = FRONTEND / "config" / "datenCheckerKategorien.ts"
HANDBUCH = Path(__file__).resolve().parents[3] / "docs" / "HANDBUCH_DATEN_CHECKER.md"


def _ts_tabelle(name: str) -> dict[str, str]:
    quelle = KATEGORIEN_TS.read_text(encoding="utf-8")
    block = quelle.split(f"export const {name}", 1)[1].split("\n}\n", 1)[0]
    return dict(re.findall(r"^\s*(\w+):\s*'([^']*)'", block, re.M))


def _handbuch_anker() -> set[str]:
    import unicodedata

    text = HANDBUCH.read_text(encoding="utf-8")
    anker = set(re.findall(r'<a name="([^"]+)"', text))
    for titel in re.findall(r"^#{2,4} (.+)$", text, re.M):   # rehype-slug (GitHub-Slug) der Überschrift
        t = re.sub(r"<[^>]+>", "", titel).strip().lower()
        t = unicodedata.normalize("NFC", t)
        anker.add(re.sub(r"[^\w\- ]", "", t).replace(" ", "-"))
    return anker


def test_jede_kategorie_hat_einen_anker_im_handbuch():
    from backend.services.daten_checker.kategorien import CheckKategorie

    tabelle = _ts_tabelle("KATEGORIE_ANKER")
    assert set(tabelle) == {k.value for k in CheckKategorie}
    vorhanden = _handbuch_anker()
    fehlt = sorted({a for a in tabelle.values() if a not in vorhanden})
    assert not fehlt, fehlt


def test_jeder_code_hat_seinen_anker_im_handbuch():
    """E5: das Lösungsweg-Panel öffnet am Anker des Codes (`loesungswegAnker` = Code); den Abschnitt erzeugt
    `scripts/daten-checker-handbuch.py` aus `docs/daten-checker/<code>.md` (W-13)."""
    vorhanden = _handbuch_anker()
    fehlt = sorted(c for c in HANDGRIFFE if c not in vorhanden)
    assert not fehlt, fehlt