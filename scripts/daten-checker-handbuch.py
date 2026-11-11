#!/usr/bin/env python3
"""Handbuch «Daten-Checker» §3 und §4 erzeugen (Etappe E5 des Vorhabens «Daten-Checker: ein Handgriff je Befund»,
Konzept §3.5, Bauplan §4 W-13).

Quellen (eine je Gegenstand, keine Hand-Reste im Handbuch):
* Katalog `eedc/backend/services/daten_checker/handgriffe.py` — je Code Klasse, Knopf-Text und Abschnitt (`handbuch_anker`);
* `docs/daten-checker/<code>.md` — je Code Titel und Lösungsweg («Was eedc sieht» · «Lösungsweg» · «Was ohne Handlung gilt»);
* `docs/daten-checker/abschnitte/<nr>-<anker>.md` — je Abschnitt von §4 die Überschrift und die Einleitung (Reihenfolge = Dateiname);
* `eedc/backend/services/daten_checker/kategorien.py` — die Zahl der Kategorien (`CheckKategorie`).

Erzeugt wird zwischen den Markern `<!-- erzeugt: … Anfang -->` und `<!-- erzeugt: … Ende -->` in
`docs/HANDBUCH_DATEN_CHECKER.md`: §3 «Alle Befunde» (Zahlen und Tabelle Code · Abschnitt · Klasse · Knopf) und §4 (je Abschnitt
die Einleitung, darunter je Code sein Lösungsweg mit Anker `<a name="<code>"></a>` — dort öffnet das Lösungsweg-Panel).

    python3 scripts/daten-checker-handbuch.py            # schreibt das Handbuch
    python3 scripts/daten-checker-handbuch.py --pruefen  # Exit 1, wenn ein Lauf etwas ändern würde (Gate, W-13)

Danach `./scripts/sync-help.sh` (In-App-Hilfe) — die Website spiegelt `docs/` beim Build.
"""
from __future__ import annotations

import argparse
import importlib.util
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
HANDBUCH = REPO / "docs" / "HANDBUCH_DATEN_CHECKER.md"
QUELLE = REPO / "docs" / "daten-checker"
ABSCHNITTE = QUELLE / "abschnitte"
KATALOG = REPO / "eedc" / "backend" / "services" / "daten_checker" / "handgriffe.py"
KATEGORIEN = REPO / "eedc" / "backend" / "services" / "daten_checker" / "kategorien.py"
#: Die drei Abschnitte einer Lösungsweg-Datei, in dieser Reihenfolge (W-13).
TEILE = ("Was eedc sieht", "Lösungsweg", "Was ohne Handlung gilt")
KLASSE_TEXT = {"aktion": "Aktion", "sprung": "Sprung", "auskunft": "Auskunft", "ok": "bestanden"}


def _marke(teil: str, ende: bool) -> str:
    return f"<!-- erzeugt: scripts/daten-checker-handbuch.py {teil} {'Ende' if ende else 'Anfang'} — nicht von Hand ändern -->"


def katalog() -> dict:
    spec = importlib.util.spec_from_file_location("_handgriffe", KATALOG)
    modul = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modul)
    return modul.HANDGRIFFE


def kategorien_zahl() -> int:
    text = KATEGORIEN.read_text(encoding="utf-8")
    block = text[text.index("class CheckKategorie"):text.index("@dataclass", text.index("class CheckKategorie"))]
    return len(re.findall(r'^    [A-Z_]+ = "', block, re.M))


def abschnitte() -> list[tuple[str, str, str]]:
    """[(anker, Überschrift, Einleitung)] in Dateinamen-Reihenfolge."""
    out = []
    for pfad in sorted(ABSCHNITTE.glob("*.md")):
        zeilen = pfad.read_text(encoding="utf-8").rstrip("\n").split("\n")
        m = re.fullmatch(r"<!-- anker: (\S+) -->", zeilen[0])
        if not m or not re.match(r"^#{3,4} 4\.", zeilen[1]):
            raise SystemExit(f"{pfad.name}: erste Zeile `<!-- anker: … -->`, zweite die Überschrift «### 4.…»")
        out.append((m.group(1), zeilen[1], "\n".join(zeilen[2:]).strip("\n")))
    return out


def loesungsweg(code: str) -> tuple[str, str]:
    """(Titel, Rumpf) der Datei eines Codes; die Abschnitte «## …» werden fette Absatz-Köpfe."""
    pfad = QUELLE / f"{code}.md"
    if not pfad.exists():
        raise SystemExit(f"Lösungsweg fehlt: docs/daten-checker/{code}.md")
    zeilen = pfad.read_text(encoding="utf-8").rstrip("\n").split("\n")
    if not zeilen[0].startswith("# "):
        raise SystemExit(f"{pfad.name}: erste Zeile «# Titel»")
    rumpf = []
    for z in zeilen[1:]:
        m = re.fullmatch(r"## (.+)", z)
        rumpf.append(f"**{m.group(1)}**" if m else z)
    return zeilen[0][2:].strip(), "\n".join(rumpf).strip("\n")


def teil3(hg: dict, abschn: list) -> str:
    nummer = {a: re.match(r"^#{3,4} (4\.[0-9a-z.]+)", u).group(1) for a, u, _e in abschn}
    zeilen = [
        f"eedc prüft **{kategorien_zahl()} Kategorien** mit **{len(hg)} Befunden** (gezählt an `CheckKategorie` und am Katalog "
        "der Handgriffe). Jeder Befund trägt genau einen Handgriff: eine **Aktion** mit Vorschau, einen **Sprung** an die Stelle, "
        "wo du ihn behebst, oder die **Auskunft** «Was gilt»; bestandene Prüfungen stehen gefaltet im Kopf ihrer Kategorie.",
        "",
        "| Befund | Abschnitt | Klasse | Knopf |",
        "| --- | --- | --- | --- |",
    ]
    for code, h in hg.items():
        titel, _ = loesungsweg(code)
        zeilen.append(f"| [{titel}](#{code}) `{code}` | §{nummer[h.handbuch_anker]} | {KLASSE_TEXT[h.klasse]} | "
                      f"{h.knopf or '—'} |")
    return "\n".join(zeilen)


def teil4(hg: dict, abschn: list) -> str:
    bekannt = {a for a, _u, _e in abschn}
    fremd = sorted(c for c, h in hg.items() if h.handbuch_anker not in bekannt)
    if fremd:
        raise SystemExit(f"Codes ohne Abschnitt in docs/daten-checker/abschnitte/: {fremd}")
    teile = ["## 4. Kategorien im Detail", ""]
    for anker, ueberschrift, einleitung in abschn:
        ebene = len(ueberschrift.split(" ", 1)[0]) + 1
        teile += [ueberschrift, ""]
        if einleitung:
            teile += [einleitung, ""]
        for code, h in hg.items():
            if h.handbuch_anker != anker:
                continue
            titel, rumpf = loesungsweg(code)
            teile += [f"{'#' * ebene} {titel} <a name=\"{code}\"></a>", "", rumpf, ""]
    return "\n".join(teile).rstrip("\n")


def ersetzen(text: str, teil: str, inhalt: str) -> str:
    a, e = _marke(teil, False), _marke(teil, True)
    if text.count(a) != 1 or text.count(e) != 1:
        raise SystemExit(f"Handbuch: Marker für {teil} fehlen oder doppelt")
    kopf, rest = text.split(a)
    _alt, fuss = rest.split(e)
    return f"{kopf}{a}\n{inhalt}\n{e}{fuss}"


def erzeugt() -> str:
    hg = katalog()
    abschn = abschnitte()
    text = HANDBUCH.read_text(encoding="utf-8")
    text = ersetzen(text, "§3", teil3(hg, abschn))
    return ersetzen(text, "§4", teil4(hg, abschn))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--pruefen", action="store_true", help="nur prüfen: Exit 1, wenn ein Lauf etwas ändern würde")
    args = ap.parse_args()
    neu = erzeugt()
    alt = HANDBUCH.read_text(encoding="utf-8")
    if args.pruefen:
        if neu != alt:
            print("✗ HANDBUCH_DATEN_CHECKER.md ist nicht aktuell — python3 scripts/daten-checker-handbuch.py", file=sys.stderr)
            return 1
        print("✓ HANDBUCH_DATEN_CHECKER.md §3/§4 aktuell (0 Änderungen)")
        return 0
    if neu != alt:
        HANDBUCH.write_text(neu, encoding="utf-8")
        print("HANDBUCH_DATEN_CHECKER.md §3/§4 neu geschrieben")
    else:
        print("HANDBUCH_DATEN_CHECKER.md §3/§4 unverändert")
    return 0


if __name__ == "__main__":
    sys.exit(main())
