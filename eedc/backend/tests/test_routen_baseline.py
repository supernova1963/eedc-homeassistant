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

⚠ **Die Baseline traegt NUR den API-Vertrag, nicht die Auslieferung.** Die drei
Routen, mit denen die App das gebaute Frontend ausliefert, haengen daran, ob
`frontend/dist` im Arbeitsbaum liegt (`main.py:1019`) -- und `dist/` ist seit N-246
nicht mehr versioniert. Eine Baseline, die auf einer Box MIT Build erhoben wurde,
misst deshalb den Build-Zustand des Arbeitsbaums mit: lokal gruen, in CI rot. Genau
das ist am 24.08. passiert (F-62, erster CI-Lauf dieses Pruefers, zwei Faelle rot).
Sie stehen darum in `AUSLIEFERUNG` und werden aus Ist UND Soll herausgerechnet.
Was dadurch nicht ungeprueft bleibt, haelt `test_auslieferungspfad_existiert_in_einer_form`
weiter unten fest.

⚠ **Sie traegt auch NICHT den Add-on-Modus.** Der App-Boot laeuft hier ohne
`SUPERVISOR_TOKEN`; die drei Router hinter `HA_INTEGRATION_AVAILABLE`
(`ha_integration`, `sensor_mapping`, `ha_statistics`-Teile) sind dabei gar nicht
erst eingehaengt und stehen deshalb in keiner Baseline-Zeile. Gemessen am
2026-08-25: 0 von 268 Zeilen. Das ist dieselbe Klasse wie der Auslieferungs-Absatz
darueber -- ein Vertrag, der von der Umgebung abhaengt --, nur eine Ebene groesser:
dort fehlten drei Routen, hier fehlt eine Betriebsart. **Bewusst nicht ausgebaut**
(Verhaeltnismaessigkeit, Gernot 24./25.08.): die Flaeche ist klein, und ein zweiter
Baseline-Lauf mit gesetztem Token waere eine zweite Datei, die veraltet. Wer
`268 Routen` liest, liest den **Standalone**-Vertrag -- nicht `alle Routen`.

⚠ **Nicht per `> routen_baseline.txt` umleiten.** Der App-Boot schreibt selbst auf
stdout (`HA-Integration: nicht verfuegbar (Standalone-Modus)`) — diese Zeile landete
am 24.08. beim Nachziehen von N-170 mitten in der Baseline und machte den Pruefer
beim naechsten Lauf aus dem falschen Grund rot. Deshalb schreibt das Rezept die
Datei selbst, statt die Ausgabe umzuleiten.
"""
from pathlib import Path

BASELINE = Path(__file__).parent / "routen_baseline.txt"

# Umgebungsabhaengig, deshalb kein Teil des Vertrags (Begruendung im Modul-Docstring):
# mit gebautem Frontend registriert main.py den Mount und den SPA-Catchall, ohne
# Frontend stattdessen den Fallback auf "/". Welche der beiden Formen gilt, sagt
# nichts ueber die App aus -- nur darueber, ob jemand `npm run build` gefahren hat.
AUSLIEFERUNG = frozenset({"- /assets", "GET /{full_path:path}", "GET /"})


def _ist_routen():
    from backend.main import app  # Import hier: der App-Boot ist Teil der Pruefung
    return {
        f"{','.join(sorted(r.methods)) if getattr(r, 'methods', None) else '-'} {r.path}"
        for r in app.routes
    } - AUSLIEFERUNG


def _soll_routen():
    return {
        z.strip() for z in BASELINE.read_text(encoding="utf-8").splitlines() if z.strip()
    } - AUSLIEFERUNG


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


def test_auslieferungspfad_existiert_in_einer_form():
    """Der Ersatz fuer das, was `AUSLIEFERUNG` aus dem Vergleich herausnimmt.

    Ohne ihn waeren die drei Routen ungeprueft -- und ein SPA-Catchall, der beim
    Umbau still verschwindet, faellt niemandem auf: die API antwortet weiter, nur
    die Oberflaeche kommt nicht mehr. Der Test schaut deshalb nicht, WELCHE Form
    aktiv ist (das entscheidet der Build-Zustand), sondern dass es GENAU EINE gibt.
    """
    from backend.main import app

    ist = {
        f"{','.join(sorted(r.methods)) if getattr(r, 'methods', None) else '-'} {r.path}"
        for r in app.routes
    }
    mit_build = {"- /assets", "GET /{full_path:path}"} <= ist
    ohne_build = "GET /" in ist

    assert mit_build != ohne_build, (
        "Der Auslieferungspfad ist weder als SPA-Zweig noch als Fallback vorhanden "
        "-- oder beides gleichzeitig.\n"
        f"  SPA-Zweig (dist vorhanden): {mit_build}\n"
        f"  Fallback 'GET /':           {ohne_build}\n"
        "main.py:1019 entscheidet das an frontend/dist. Beides zugleich oder keines "
        "von beidem heisst: der Zweig wurde umgebaut und die Oberflaeche haengt."
    )
