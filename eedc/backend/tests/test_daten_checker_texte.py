"""W-4 Mechanik-Wörter (Etappe E3, Bauplan §4; Konzept §3.1 R4; Gegenprüfung Ü3).

Der Knopf eines Befunds und die **eine** Vorschau-Zeile je Operation sprechen Anwender-Sprache: kein Wort aus
``handgriffe.MECHANIK_WOERTER`` (Spiegel, Kanal, LTS, Statistics, Snapshot, aggregier, Provenance, Resnap) und kein
Menüweg-Pfeil «→». Geprüft werden
* die Knopf-Texte des Katalogs (``HANDGRIFFE[*].knopf``) und je Operation (``KNOPF_JE_OPERATION``, daraus
  ``CheckErgebnis.action_label``);
* die Beschriftungen der Vorschau-Zähler, die die Operationen der Checker-Knöpfe liefern (``REPARATUR_AENDERUNG_LABELS`` in
  ``frontend/src/lib/constants.ts``) — jeder Schlüssel hat eine;
* die Satzteile der Vorschau-Zeile im Client (``frontend/src/components/datenchecker/vorschauZeile.ts``).
**Ausgenommen:** die Werkbank-Warnungen (``RepairPlan.warnings``), die der Kasten unverändert zeigt (Ü3). Meldungen und
Details folgen in E4 (Menüwege raus; Allowlist der acht Werteübergänge, Erhebung Teil A Aufgabe 2).

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
    fehlt = sorted({a for a in (*tabelle.values(), *_ts_tabelle("CODE_ANKER").values()) if a not in vorhanden})
    assert not fehlt, fehlt


def test_katalog_anker_stehen_in_der_client_tabelle():
    """Jeder Anker des Katalogs ist ein Kategorie-Anker der Client-Tabelle oder ein benannter Code-Anker (bis E5)."""
    erlaubt = set(_ts_tabelle("KATEGORIE_ANKER").values())
    code_anker = _ts_tabelle("CODE_ANKER")
    for code, h in HANDGRIFFE.items():
        if code in code_anker:
            assert h.handbuch_anker == code_anker[code], code
        elif h.handbuch_anker:
            assert h.handbuch_anker in erlaubt, (code, h.handbuch_anker)
