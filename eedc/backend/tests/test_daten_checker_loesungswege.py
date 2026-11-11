"""Wächter W-13 «Lösungswege» (Etappe E5 des Vorhabens «Daten-Checker: ein Handgriff je Befund», Bauplan §4, Konzept §3.5).

Jeder Code des Katalogs (`handgriffe.HANDGRIFFE`) hat eine Datei `docs/daten-checker/<code>.md` mit Titel und den drei
Abschnitten «Was eedc sieht» · «Lösungsweg» (nummerierte Schritte, der letzte «Erneut prüfen») · «Was ohne Handlung gilt»;
Melde-Situationen (`drift_*`, `ha_zaehlersprung`, `ha_zaehler_rueckgang`, `tageswerte_fehlen_*`) nennen zuletzt das
Diagnose-Paket — Kopieren vor Datei (E5.7 L6). Daraus und aus den Abschnitts-Einleitungen `docs/daten-checker/abschnitte/`
erzeugt `scripts/daten-checker-handbuch.py` das Handbuch §3/§4 — ein Lauf ändert nichts (kein Hand-Rest).

**Menüwege** (Methode Erhebung Teil A Aufgabe 2 als Test): ein Weg steht kursiv `*A → B → C*`; er beginnt mit einem der drei
Home-Assistant-Wege (HA-Allowlist) oder ist `Einstellungen → <Bereich> [→ <Block>]` mit Bereich und Block aus
`frontend/src/config/einstellungenKatalog.tsx` (Komponenten: Gerätetyp aus `lib/constants.ts::TYP_LABELS`). Ein «→» außerhalb
eines kursiven Wegs ist nur als Werteübergang erlaubt (Zahl davor und danach). **Schritte in eedc** sind Links
`[Text](eedc:/einstellungen/…)`; jeder Pfad entsteht über einen Ziel-Bauer (`ziele.py`, Feld-Schlüssel gegen die Registry).

Schwesterdateien: test_daten_checker_codes.py (W-1/W-3, Katalog), test_daten_checker_ziele.py (W-2, Ziel-Bauer),
test_daten_checker_texte.py (W-4, Anker im Handbuch).
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import parse_qsl

import pytest

from backend.services.daten_checker import ziele
from backend.services.daten_checker.handgriffe import HANDGRIFFE
from backend.services.daten_checker.kategorien import link_aus_ziel

REPO = Path(__file__).resolve().parents[3]
QUELLE = REPO / "docs" / "daten-checker"
ABSCHNITTE = QUELLE / "abschnitte"
KATALOG_TS = REPO / "eedc" / "frontend" / "src" / "config" / "einstellungenKatalog.tsx"
KONSTANTEN_TS = REPO / "eedc" / "frontend" / "src" / "lib" / "constants.ts"
TEILE = ("Was eedc sieht", "Lösungsweg", "Was ohne Handlung gilt")
#: Die drei Wege in Home Assistant (Erhebung Teil A M10, M23, M24) — Anfang eines kursiven Wegs.
HA_WEGE = (("Einstellungen", "Geräte & Dienste", "Helfer"), ("Entwicklerwerkzeuge", "Statistik"), ("Helfer",))
MELDE_CODES = tuple(c for c in HANDGRIFFE if c.startswith(("drift_", "tageswerte_fehlen_"))
                    and HANDGRIFFE[c].klasse != "ok") + ("ha_zaehlersprung", "ha_zaehler_rueckgang")
_KURSIV = re.compile(r"(?<![*\w])\*(?!\*)([^*\n]+?)(?<!\*)\*(?![*\w])")
_CODE = re.compile(r"`[^`\n]*`")
_EEDC_LINK = re.compile(r"\]\((eedc:[^)\s]+)\)")


def _text(code: str) -> str:
    return (QUELLE / f"{code}.md").read_text(encoding="utf-8")


def _quellen() -> list[Path]:
    return sorted(QUELLE.glob("*.md")) + sorted(ABSCHNITTE.glob("*.md"))


def _abschnitte(text: str) -> dict[str, str]:
    teile = re.split(r"^## (.+)$", text, flags=re.M)
    return {teile[i].strip(): teile[i + 1] for i in range(1, len(teile) - 1, 2)}


def _katalog() -> dict[str, set[str]]:
    """Bereich (Label) → Blöcke (Namen) aus dem Einstellungs-Katalog; Komponenten: die Gerätetypen."""
    ts = KATALOG_TS.read_text(encoding="utf-8")
    bereiche = dict(re.findall(r"\{ key: '([a-z]+)', label: '([^']+)'", ts))
    bloecke: dict[str, set[str]] = {label: set() for label in bereiche.values()}
    for name, kat in re.findall(r"id: '[^']+', name: '([^']+)', icon: \w+, kategorie: '([a-z]+)'", ts):
        bloecke[bereiche[kat]].add(name)
    typen = KONSTANTEN_TS.read_text(encoding="utf-8")
    block = typen[typen.index("export const TYP_LABELS"):]
    bloecke["Komponenten"] |= set(re.findall(r"^\s+'[a-z-]+': '([^']+)',", block[:block.index("}")], re.M))
    return bloecke


def _weg_gueltig(segmente: list[str], katalog: dict[str, set[str]]) -> bool:
    if any(tuple(segmente[:len(w)]) == w for w in HA_WEGE):
        return True
    if segmente[0] != "Einstellungen" or not 2 <= len(segmente) <= 3 or segmente[1] not in katalog:
        return False
    return len(segmente) == 2 or segmente[2] in katalog[segmente[1]]


def _segmente(weg: str) -> list[str]:
    return [s.strip().strip("„“«»\"") for s in weg.split("→")]


def _ziel_aus_pfad(pfad: str):
    """Das Ziel, das ein Ziel-Bauer für ``pfad`` baut (wirft, wenn keiner es kann oder ein Feld unbekannt ist)."""
    weg, _, query = pfad.partition("?")
    p = dict(parse_qsl(query))
    bereich = weg.removeprefix("/einstellungen/")
    zahl = {k: int(v) for k, v in p.items() if k in ("bearbeiten", "geraet") and v.isdigit()}
    if bereich == "datenquellen":
        return ziele.ziel_datenquelle(feld=p.get("feld"), geraet=zahl.get("geraet"))
    if bereich == "komponenten":
        return ziele.ziel_komponente(zahl.get("bearbeiten"), feld=p.get("feld"), neu=p.get("neu"))
    if bereich == "daten" and "erfassen" in p:
        jahr, monat = p["erfassen"].split("-")
        return ziele.ziel_monat(int(jahr), int(monat), geraet=zahl.get("geraet"), feld=p.get("feld"))
    if bereich == "daten" and p.get("block") == "energieprofil":
        return ziele.ziel_werkbank(p.get("karte", "werkbank"), plan=p.get("plan"))
    if bereich == "stammdaten" and p.get("block") == "anlage":
        return ziele.ziel_anlage(p["feld"])
    if bereich == "stammdaten" and p.get("block") == "strompreise":
        return ziele.ziel_tarif(feld=p.get("feld"), neu=p.get("tarif") == "neu", neu_art=p.get("art"), ab=p.get("ab"))
    return ziele.ziel_block(bereich, p["block"], karte=p.get("karte"), feld=p.get("feld"), wizard=p.get("wizard"))


# ─── je Code eine Datei ───────────────────────────────────────────────────────────────────────────────────────

def test_je_code_eine_datei_und_keine_waise():
    ist = {p.stem for p in QUELLE.glob("*.md")}
    assert set(HANDGRIFFE) - ist == set(), f"Lösungsweg fehlt: {sorted(set(HANDGRIFFE) - ist)}"
    assert ist - set(HANDGRIFFE) == set(), f"Datei ohne Code: {sorted(ist - set(HANDGRIFFE))}"
    assert len(ist) == len(HANDGRIFFE) == 182


@pytest.mark.parametrize("code", list(HANDGRIFFE))
def test_titel_drei_abschnitte_und_schritte(code):
    text = _text(code)
    assert text.startswith("# ") and text.split("\n", 1)[0][2:].strip(), f"{code}: erste Zeile «# Titel»"
    teile = _abschnitte(text)
    assert tuple(teile) == TEILE, f"{code}: Abschnitte {tuple(teile)} statt {TEILE}"
    assert all(t.strip() for t in teile.values()), f"{code}: leerer Abschnitt"
    schritte = re.findall(r"^\d+\. (.+)$", teile["Lösungsweg"], re.M)
    assert schritte, f"{code}: «Lösungsweg» ohne nummerierte Schritte"
    assert "Erneut prüfen" in schritte[-1], f"{code}: der letzte Schritt ist «Erneut prüfen»"
    if code in MELDE_CODES:
        rest = teile["Lösungsweg"]
        assert "Diagnose-Paket" in rest and re.search(r"Kopieren", rest), f"{code}: Melde-Situation ohne Diagnose-Paket"
        assert rest.index("Kopieren") < rest.index("Datei") if "Datei" in rest else True, f"{code}: Kopieren vor Datei"


def test_melde_situationen_sind_bekannt():
    assert set(MELDE_CODES) >= {"drift_tag", "drift_komponente", "ha_zaehlersprung", "ha_zaehler_rueckgang",
                                "tageswerte_fehlen_tage", "tageswerte_fehlen_tag"}


# ─── Menüwege und eedc-Schritte ───────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("pfad", _quellen(), ids=lambda p: p.name)
def test_menuewege_im_katalog_oder_ha_allowlist(pfad):
    katalog = _katalog()
    text = _CODE.sub("", pfad.read_text(encoding="utf-8"))
    falsch = [w for w in _KURSIV.findall(text) if "→" in w and not _weg_gueltig(_segmente(w), katalog)]
    assert not falsch, f"{pfad.name}: Menüweg nicht im Katalog / nicht in der HA-Allowlist: {falsch}"
    ohne_wege = _KURSIV.sub("", text)
    lose = [ohne_wege[max(0, m.start() - 25):m.end() + 25] for m in re.finditer("→", ohne_wege)
            if not (re.search(r"\d\S{0,3}\s*$", ohne_wege[:m.start()]) and re.match(r"\s*\S{0,2}[-+−]?\d", ohne_wege[m.end():]))]
    assert not lose, f"{pfad.name}: «→» außerhalb eines kursiven Menüwegs und kein Werteübergang: {lose}"


@pytest.mark.parametrize("pfad", _quellen(), ids=lambda p: p.name)
def test_eedc_schritte_ueber_den_ziel_bauer(pfad):
    for link in _EEDC_LINK.findall(pfad.read_text(encoding="utf-8")):
        weg = link.removeprefix("eedc:")
        assert link_aus_ziel(_ziel_aus_pfad(weg)) == weg, f"{pfad.name}: {link} entsteht so in keinem Ziel-Bauer"


def test_sprengsatz_menuweg_und_link():
    katalog = _katalog()
    assert not _weg_gueltig(_segmente("Einstellungen → Datenverwaltung → Import aus HA-Statistik"), katalog)
    assert not _weg_gueltig(_segmente("Cockpit → Tag"), katalog)
    assert _weg_gueltig(_segmente("Einstellungen → Daten → Energieprofil-Pflege"), katalog)
    assert _weg_gueltig(_segmente("Einstellungen → Komponenten → Wärmepumpe"), katalog)
    assert _weg_gueltig(_segmente("Entwicklerwerkzeuge → Statistik → „Wert anpassen“"), katalog)
    with pytest.raises(ValueError):
        _ziel_aus_pfad("/einstellungen/datenquellen?feld=gibt_es_nicht")


# ─── Abschnitte und Generator ─────────────────────────────────────────────────────────────────────────────────

def test_jeder_katalog_anker_hat_einen_abschnitt():
    anker = {re.match(r"<!-- anker: (\S+) -->", p.read_text(encoding="utf-8")).group(1) for p in ABSCHNITTE.glob("*.md")}
    fehlt = sorted({h.handbuch_anker for h in HANDGRIFFE.values()} - anker)
    assert not fehlt, f"Katalog-Anker ohne Abschnitt in docs/daten-checker/abschnitte/: {fehlt}"


def test_generator_aendert_nichts():
    """Kein Hand-Rest im Handbuch §3/§4: ein Lauf des Generators ändert nichts (`--pruefen`)."""
    r = subprocess.run([sys.executable, str(REPO / "scripts" / "daten-checker-handbuch.py"), "--pruefen"],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
