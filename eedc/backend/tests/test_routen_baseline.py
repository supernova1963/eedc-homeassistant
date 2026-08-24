"""Die Routen-Tafel der App gegen eine eingecheckte Baseline (M1 / Test-Inventur 22.08.).

Warum es diesen Test gibt — er ersetzt ein CI-Inline-Skript, das zwei Fehler hatte:

1. **Die Schwelle war tot.** `.github/workflows/tests.yml` trug `EXPECTED_ROUTES = 217` und
   prüfte `n < EXPECTED_ROUTES`. Gemessen am 23.08.2026: die App hat **271** Routen. Der
   Puffer betrug damit **54 Endpoints** -- ein nicht mehr eingebundener Router haette
   fuenfzig Endpunkte mitnehmen koennen, ohne dass das Gate rot wird. Eine `>=`-Schwelle,
   die niemand nachzieht, waechst sich selbst aus der Aussage heraus.

2. **Den Pruefer kannte nur CI.** Er lief als YAML-Inline-Skript, also in keinem lokalen
   Gate. Genau die Klasse, die CLAUDE.md zweimal dokumentiert: der `lint`-Befund vom
   12.08. (CI kannte ihn, die lokale Liste nicht) und N-167 in der Gegenrichtung. Als
   pytest-Datei laeuft er jetzt in allen drei Zonen mit, lokal wie in CI.

**Warum eine Liste und keine Zahl.** Eine Zahl sagt "270 statt 271" -- danach sucht
jemand. Die Liste sagt, WELCHE Route fehlt. Und die Nachfuehrung ist ein `git diff`, den
man lesen kann, statt einer Ziffer, die man hochsetzt. Das ist der Unterschied zu
N-195/N-263 (Allowlist an einer Zeilennummer, viermal nachgefuehrt): eine Zeilennummer
verschiebt sich bei jeder Formatierung, ein Endpunkt aendert sich nur, wenn ihn jemand
absichtlich aendert.

**Wenn dieser Test rot wird:** Endpoint bewusst hinzugefuegt oder entfernt? Dann die
Baseline neu erzeugen und den Diff im Commit mitschicken:

    cd eedc && python -c "
    from backend.main import app
    zeilen = sorted({(','.join(sorted(r.methods)) if getattr(r,'methods',None) else '-')+' '+r.path for r in app.routes})
    open('backend/tests/routen_baseline.txt','w').write('\\n'.join(zeilen)+'\\n')
    "

⚠ **Nicht per `> routen_baseline.txt` umleiten.** Der App-Boot schreibt selbst auf
stdout (`HA-Integration: nicht verfuegbar (Standalone-Modus)`) — diese Zeile landete
am 24.08. beim Nachziehen von N-170 mitten in der Baseline und machte den Pruefer
beim naechsten Lauf aus dem falschen Grund rot. Deshalb schreibt das Rezept die
Datei selbst, statt die Ausgabe umzuleiten.
"""
from pathlib import Path

BASELINE = Path(__file__).parent / "routen_baseline.txt"


def _ist_routen():
    from backend.main import app  # Import hier: der App-Boot ist Teil der Pruefung
    return {
        f"{','.join(sorted(r.methods)) if getattr(r, 'methods', None) else '-'} {r.path}"
        for r in app.routes
    }


def _soll_routen():
    return {z.strip() for z in BASELINE.read_text(encoding="utf-8").splitlines() if z.strip()}


def test_baseline_datei_ist_nicht_leer():
    """Gegen die N-318-Klasse: ein Pruefer, dessen Pruefmenge leer ist, meldet gruen ohne
    zu messen. Faellt die Baseline-Datei weg oder wird sie geleert, wuerde der Vergleich
    unten trivial erfuellt -- deshalb steht diese Untergrenze davor."""
    soll = _soll_routen()
    assert len(soll) > 200, (
        f"routen_baseline.txt enthaelt nur {len(soll)} Zeilen. Das ist keine Baseline, "
        f"das ist ein Datenverlust -- der Vergleich unten waere damit wertlos."
    )


def test_keine_route_ist_verschwunden():
    """Der eigentliche Zweck: ein Router, der nicht mehr eingebunden ist, nimmt seine
    Endpunkte still mit. Genau das konnte die alte >=-Schwelle nicht sehen."""
    fehlend = sorted(_soll_routen() - _ist_routen())
    assert not fehlend, (
        f"{len(fehlend)} Route(n) aus der Baseline fehlen in der App:\n  "
        + "\n  ".join(fehlend)
        + "\n\nAbsichtlich entfernt? Dann routen_baseline.txt neu erzeugen "
          "(Anleitung im Modul-Docstring) und den Diff im Commit mitschicken."
    )


def test_keine_route_ist_unangekuendigt_dazugekommen():
    """Die Gegenrichtung gehoert dazu: ein neuer Endpunkt ist eine bewusste Aenderung und
    soll im Diff sichtbar werden -- nicht stillschweigend durchlaufen wie unter `>=`."""
    neu = sorted(_ist_routen() - _soll_routen())
    assert not neu, (
        f"{len(neu)} neue Route(n), die nicht in der Baseline stehen:\n  "
        + "\n  ".join(neu)
        + "\n\nNeu gebaut? Dann routen_baseline.txt neu erzeugen "
          "(Anleitung im Modul-Docstring) und den Diff im Commit mitschicken."
    )
