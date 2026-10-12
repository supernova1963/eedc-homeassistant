"""
Wächter: kein „Beheben"-Link des Daten-Checkers zeigt auf die Seite, auf der er steht.

**Der Fall** (Radiocarbonat, simon42 T89667 #268, 31.08.2026): *„Wenn ich die
Warnung beseitigen möchte und auf ‚Beheben‘ klicke, passiert nichts."*

**Die Ursache ist mechanisch.** Der Daten-Checker läuft seit dem V4-Flip als
Block IN `/einstellungen/daten` (genau eine Einbettung, `einstellungenKatalog.tsx`
→ `DatenCheckerVerwaltung`). Sein Knopf ruft
`navigate(v3RouteZuV4(link) ?? link)`. Zeigt `link` auf eine Alt-Route, die
`v3RouteZuV4` auf die Kategorie `daten` abbildet — `einstellungen/monatsdaten`,
`einstellungen/energieprofil`, `einstellungen/daten-checker`,
`einstellungen/einrichtung` —, dann navigiert der Klick auf die **aktuelle**
Route: React Router tut nichts, und der Anwender sieht nichts.

**Achtzehn Meldungen liefen so ins Leere**, verteilt über fünf Prüfer-Dateien.
Zwei bestehende Proben standen grün daneben, ohne dass eine davon falsch war:
`v3ZuV4Route.test.ts` sichert die **Map** (die stimmt), `redirects.test.tsx`
sichert, dass ein Ziel **existiert** (tut es). Keine von beiden fragt, ob die
Navigation etwas **bewirkt** — genau diese Lücke schließt dieser Test.

**Der Ausweg liegt seit dem V4-Flip bereit**, und die Regel lautet deshalb nicht
„nie auf die Daten-Fläche zeigen", sondern *nur mit einem Query, den sie liest*:

* `?block=<katalog-id>` klappt einen Katalog-Block auf (`EinstellungenV4.tsx`),
* `?erfassen=YYYY-MM` klappt den Monatsdaten-Block auf **und** öffnet die
  Erfassung dieses Monats (`MonatsdatenTeile.tsx`).

Beide ändern die URL gegenüber der aktuellen Seite, also wirkt die Navigation
auch von der Daten-Fläche auf sich selbst.

⚠ **Die Alt-Routen werden aus `v3ZuV4Route.ts` GELESEN, nicht abgeschrieben.**
Eine zweite Liste hier wäre genau die Drift, gegen die der Test gebaut ist:
Wer morgen `einstellungen/xyz` auf `daten` abbildet, bekommt die Prüfung
automatisch mit.

**Schwesterdateien:** `test_daten_checker_kategorien_erreichbar.py` (dieselbe
Bauform — Backend-Quelle gegen Frontend-Datei als Text — und die komplementäre
Frage: *kommt die Meldung überhaupt an?*, während hier steht: *bewirkt ihr
Knopf etwas?*) und `test_daten_checker_hinweise_mit_folge.py` (der Meldungstext
selbst). Kein zweiter Turm: keine der beiden prüft ein Link-Ziel.
"""

import re
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1]
CHECKER_DIR = BACKEND / "services" / "daten_checker"
V3_MAP_TS = BACKEND.parent / "frontend" / "src" / "config" / "v3ZuV4Route.ts"

# Die Kategorie, auf der der Daten-Checker selbst rendert. Ein Link dorthin ist
# eine Navigation auf die aktuelle Seite — es sei denn, er trägt einen Query,
# den die Seite liest (s. Modul-Docstring).
EIGENE_KATEGORIE = "daten"

# Query-Parameter, die `/einstellungen/daten` tatsächlich auswertet. Wer hier
# einen ergänzt, ergänzt ihn zuerst im Frontend — sonst ist der Link wieder tot.
WIRKSAME_PARAMETER = ("block=", "erfassen=")


def _alt_routen_auf_die_daten_flaeche() -> set[str]:
    """Alle Alt-Routen, die `v3RouteZuV4` auf die Kategorie `daten` abbildet."""
    quelle = V3_MAP_TS.read_text(encoding="utf-8")
    paare = re.findall(r"'(einstellungen/[a-z-]+)':\s*'([a-z]+)'", quelle)
    assert paare, f"Map in {V3_MAP_TS.name} nicht lesbar — Format geändert?"
    return {route for route, kategorie in paare if kategorie == EIGENE_KATEGORIE}


def _checker_quellen() -> list[Path]:
    # Vorlage 9 (18.09.2026): `datenquelle/` ist ein Unterpaket — rekursiv sammeln, sonst
    # fallen seine sieben Module still aus dieser Probe (gemessen: 5566 → 5565 Tests).
    dateien = sorted(p for p in CHECKER_DIR.rglob("*.py") if p.name != "__init__.py")
    assert len(dateien) >= 15, f"nur {len(dateien)} Daten-Checker-Quellen gefunden — Sammlung prüfen"
    return dateien


def _link_ziele(quelle: str) -> list[tuple[int, str]]:
    """Alle als Literal geschriebenen `link=`-Ziele mit ihrer Zeilennummer."""
    treffer: list[tuple[int, str]] = []
    for nr, zeile in enumerate(quelle.splitlines(), start=1):
        for ziel in re.findall(r'link=f?"([^"]+)"', zeile):
            treffer.append((nr, ziel))
        # Auch die Konstanten-Definitionen selbst prüfen (kategorien.py).
        for ziel in re.findall(r'^LINK_[A-Z_]+ = "([^"]+)"', zeile):
            treffer.append((nr, ziel))
    return treffer


def test_die_map_kennt_die_daten_flaeche():
    """Negativprobe für den Leser: findet er überhaupt Alt-Routen?"""
    routen = _alt_routen_auf_die_daten_flaeche()
    assert "einstellungen/monatsdaten" in routen
    assert "einstellungen/energieprofil" in routen
    # ... und er diskriminiert: Stammdaten-Ziele gehören NICHT dazu.
    assert "einstellungen/strompreise" not in routen


@pytest.mark.parametrize("datei", _checker_quellen(), ids=lambda p: str(p.relative_to(CHECKER_DIR)))
def test_kein_beheben_link_zeigt_auf_die_eigene_seite(datei: Path):
    """Kein Checker-Link landet ohne wirksamen Query auf `/einstellungen/daten`.

    Betrifft beide Formen: die Alt-Route (`/einstellungen/monatsdaten`), die
    stillschweigend dorthin umgeleitet wird, und das direkte Ziel
    (`/einstellungen/daten`) ohne Parameter.
    """
    alt_routen = _alt_routen_auf_die_daten_flaeche()
    tot: list[str] = []

    for nr, ziel in _link_ziele(datei.read_text(encoding="utf-8")):
        ohne_slash = ziel.lstrip("/")
        pfad, _, query = ohne_slash.partition("?")
        wirksam = any(p in query for p in WIRKSAME_PARAMETER)

        if pfad in alt_routen and not wirksam:
            tot.append(
                f"{datei.name}:{nr}  {ziel!r} → wird auf /einstellungen/daten "
                f"umgeleitet (Alt-Route)"
            )
        elif pfad == f"einstellungen/{EIGENE_KATEGORIE}" and not wirksam:
            tot.append(
                f"{datei.name}:{nr}  {ziel!r} → ist /einstellungen/daten "
                f"ohne wirksamen Query"
            )

    assert not tot, (
        "Diese „Beheben“-Links navigieren auf die Seite, auf der der "
        "Daten-Checker steht — der Klick tut sichtbar nichts:\n  "
        + "\n  ".join(tot)
        + "\n\nStatt dessen: LINK_MONATSDATEN / LINK_ENERGIEPROFIL "
        "(`?block=…`) oder link_monat_erfassen(\"MM/YYYY\") (`?erfassen=…`) "
        "aus `daten_checker/kategorien.py`."
    )


def test_der_helfer_baut_einen_wirksamen_deep_link():
    """`link_monat_erfassen` dreht `MM/YYYY` und fällt sicher zurück."""
    from backend.services.daten_checker.kategorien import (
        LINK_MONATSDATEN,
        link_monat_erfassen,
    )

    # Radiocarbonats Fall: „Speicher-Ladung fehlt … 05/2026, 06/2026, 07/2026"
    assert link_monat_erfassen("05/2026") == "/einstellungen/daten?erfassen=2026-05"
    assert link_monat_erfassen("12/2025") == "/einstellungen/daten?erfassen=2025-12"
    # Unerwartete Form ⇒ Block statt Absturz. Ein Link, der die Fläche zeigt,
    # ist immer noch besser als einer, der nichts tut.
    for murks in ("", "Mai 2026", "2026-05", None):
        assert link_monat_erfassen(murks) == LINK_MONATSDATEN


# ── N-739 (a): `/monatsabschluss/…` öffnet den Monat nicht ──────────────────────────────────────────────────────
#
# Der v4-Router fängt die Alt-Route `monatsabschluss/*` mit einem `<Navigate>` auf die Daten-Fläche — ohne
# `?erfassen=` (`App.tsx`). Ein Checker-Link dorthin landet also auf der Seite, auf der der Checker steht, und der
# Monat öffnet sich nicht. Der N-734-ERROR «nicht erfasst» und die übrigen Monats-Prüfungen setzten ihn über die
# Variable `md_link` — die `link=f"…"`-Erhebung oben sieht Variablen nicht, deshalb hier jedes Literal.
APP_TSX = BACKEND.parent / "frontend" / "src" / "App.tsx"


def _monatsabschluss_leitet_auf_die_daten_flaeche() -> bool:
    quelle = APP_TSX.read_text(encoding="utf-8")
    treffer = re.search(r'path="monatsabschluss/\*"\s+element=\{<Navigate to="([^"]+)"', quelle)
    assert treffer, f"Splat-Fänger `monatsabschluss/*` in {APP_TSX.name} nicht gefunden — Format geändert?"
    pfad, _, query = treffer.group(1).lstrip("/").partition("?")
    return pfad == f"einstellungen/{EIGENE_KATEGORIE}" and not any(p in query for p in WIRKSAME_PARAMETER)


def test_kein_checker_link_auf_den_alten_monatsabschluss():
    """Kein Literal `/monatsabschluss/…` in den Checker-Quellen, solange der Router es ohne Query umleitet."""
    if not _monatsabschluss_leitet_auf_die_daten_flaeche():
        pytest.skip("`monatsabschluss/*` leitet nicht mehr auf die Daten-Fläche ohne Query — Regel neu prüfen")
    tot = [
        f"{datei.relative_to(CHECKER_DIR)}:{nr}  {zeile.strip()[:100]}"
        for datei in _checker_quellen()
        for nr, zeile in enumerate(datei.read_text(encoding="utf-8").splitlines(), start=1)
        if re.search(r'f?"/monatsabschluss/', zeile)
    ]
    assert not tot, (
        "Diese Checker-Links öffnen den Monat nicht (Umleitung auf /einstellungen/daten ohne `?erfassen=`):\n  "
        + "\n  ".join(tot) + "\n\nStatt dessen: link_monat_erfassen(\"MM/YYYY\") aus `daten_checker/kategorien.py`."
    )


async def test_n734_fehler_verlinken_die_erfassung_des_monats(db):
    """Der ERROR «… nicht erfasst» trägt den Deep-Link `?erfassen=JJJJ-MM` (N-739 a)."""
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload

    from backend.models import Anlage, Investition, Monatsdaten
    from backend.services.daten_checker import DatenChecker
    from backend.tests.test_n734_netzfeld_ohne_herkunft import J, M, _anlage, _import

    a = await _anlage(db)
    await _import(db, a.id, wallbox_ladung_kwh=150.0)
    anlage = (await db.execute(
        select(Anlage).options(selectinload(Anlage.investitionen).selectinload(Investition.monatsdaten))
        .where(Anlage.id == a.id)
    )).scalar_one()
    mds = list((await db.execute(select(Monatsdaten).where(Monatsdaten.anlage_id == a.id))).scalars().all())
    erg = await DatenChecker(db)._check_monatsdaten_plausibilitaet(anlage, mds)
    netz = [e for e in erg if "nicht erfasst" in e.meldung]

    assert len(netz) == 2
    assert {e.link for e in netz} == {f"/einstellungen/daten?erfassen={J}-{M:02d}"}
