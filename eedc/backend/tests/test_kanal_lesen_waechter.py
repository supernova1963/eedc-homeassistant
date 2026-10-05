"""Wächter: wer die Lese-Schicht der Kanalstatistik importieren darf (HA-Bauform E3, Auftrag Punkt 6; Bauplan §5, G7).

**Regel.** Die Lese-Schicht (``services/kanal/lesen.py``, ``fenster.py``, ``quellenwahl.py``, ``monatsraster.py``)
importieren nur ``services/kanal/`` selbst, ``services/monats_fakten/`` (der eine Aufbereiter, ADR-002/P10) und
ausdrücklich benannte Tages-Leser (``BENANNTE_TAGESLESER``, mit Grund). Keine Route, keine Sicht, kein PDF, kein
Export greift direkt auf ``zeitraum``/``reihe`` zu — Zeiträume ab Monatslänge laufen über das Monatsraster mit der
P8-Überlagerung der Monats-Fakten, nie über ein direktes ``zeitraum()`` über Monatsgrenzen (Bauplan §5).

**Stand E3: außerhalb ``services/kanal/`` (und der Proben) importiert sie NIEMAND** — die Schicht ist gebaut und
geprüft, aber nicht umgehängt. ``IMPORTEURE_STAND`` hält genau das fest (Baseline 0, Gleichheit statt Obergrenze);
E4 trägt dort die Monats-Fakten und die benannten Tages-Leser ein.

**Was er findet (AST, baumweit ohne ``tests/``):** ``import backend.services.kanal.lesen``, ``from
backend.services.kanal.lesen import …``, ``from backend.services.kanal import lesen``, auch in Funktionen; relative
Importe (``from ..services.kanal.lesen import …``, ``from .kanal import lesen`` — aufgelöst über den Dateipfad);
Attributzugriff über das Paket (``import backend.services.kanal`` bzw. ``from backend.services import kanal`` und dann
``kanal.lesen.…``, auch mit Alias); den vollen Modulpfad als Zeichenkette (``importlib.import_module(
"backend.services.kanal.lesen")``, ``__import__``). Gegenprobe im Test, je Form.

**Nicht erfasst (benannt):** ``importlib.import_module`` mit relativem Namen oder zusammengesetzter Zeichenkette
(``import_module(".lesen", "backend.services.kanal")``, f-String) — eine solche Zeile zu bauen hieße, den Wächter
absichtlich zu umgehen.

Schwesterdateien: test_kanal_lesen.py, test_dead_export_services.py (ein Modul, das niemand nennt, fällt dort auf).
"""

from __future__ import annotations

import ast

from backend.tests.quellbaum import produktivbaum

PAKET = "backend.services.kanal"
SCHICHT = ("lesen", "fenster", "quellenwahl", "monatsraster")
SCHICHT_MODULE = {f"{PAKET}.{m}" for m in SCHICHT}

#: Verzeichnisse, die importieren DÜRFEN (Präfix relativ zu ``backend/``).
ERLAUBT_PRAEFIX = ("services/kanal/", "services/monats_fakten/")

#: Tages-Leser, die in E4 benannt werden (Datei → Grund). Leer in E3.
BENANNTE_TAGESLESER: dict[str, str] = {}

#: Wer heute außerhalb ``services/kanal/`` importiert — Stand E3: niemand.
IMPORTEURE_STAND: set[str] = set()


def _modul_aus_rel(rel: str) -> tuple[str, bool]:
    """``services/kanal/lesen.py`` → (``backend.services.kanal.lesen``, ist Paket-``__init__``)."""
    teile = rel[:-3].split("/") if rel.endswith(".py") else rel.split("/")
    paket = teile[-1] == "__init__"
    if paket:
        teile = teile[:-1]
    return ".".join(["backend", *teile]), paket


def _absolut(n: ast.ImportFrom, rel: str | None) -> str | None:
    """Der absolute Modulname eines ``from … import``; relativ (``level > 0``) über den Dateipfad aufgelöst."""
    if not n.level:
        return n.module
    if rel is None:
        return None
    modul, paket = _modul_aus_rel(rel)
    teile = modul.split(".") if paket else modul.split(".")[:-1]
    if n.level - 1 > len(teile):
        return None
    basis = teile[: len(teile) - (n.level - 1)]
    return ".".join(basis + ([n.module] if n.module else []))


def _gepunktet(knoten: ast.AST) -> str | None:
    teile = []
    while isinstance(knoten, ast.Attribute):
        teile.append(knoten.attr)
        knoten = knoten.value
    if isinstance(knoten, ast.Name):
        return ".".join([knoten.id, *reversed(teile)])
    return None


def importe_der_schicht(baum: ast.AST, rel: str | None = None) -> list[tuple[int, str]]:
    """(Zeile, Modul) je Import eines Moduls der Lese-Schicht, in allen Formen; ``rel`` (Pfad relativ zu
    ``backend/``) löst relative Importe auf."""
    funde: list[tuple[int, str]] = []
    paket_namen = {PAKET}          # Namen, unter denen das Paket ``backend.services.kanal`` erreichbar ist
    for n in ast.walk(baum):
        if isinstance(n, ast.Import):
            for a in n.names:
                if a.name in SCHICHT_MODULE or any(a.name.startswith(m + ".") for m in SCHICHT_MODULE):
                    funde.append((n.lineno, a.name))
                elif a.name == PAKET and a.asname:
                    paket_namen.add(a.asname)
        elif isinstance(n, ast.ImportFrom):
            modul = _absolut(n, rel)
            if not modul:
                continue
            if modul in SCHICHT_MODULE or any(modul.startswith(m + ".") for m in SCHICHT_MODULE):
                funde.append((n.lineno, modul))
            elif modul == PAKET:
                funde += [(n.lineno, f"{PAKET}.{a.name}") for a in n.names if a.name in SCHICHT]
            elif modul == PAKET.rpartition(".")[0]:
                paket_namen.update(a.asname or a.name for a in n.names if a.name == PAKET.rpartition(".")[2])
        elif isinstance(n, ast.Constant) and isinstance(n.value, str) and n.value in SCHICHT_MODULE:
            funde.append((n.lineno, n.value))
    for n in ast.walk(baum):
        if isinstance(n, ast.Attribute) and n.attr in SCHICHT and _gepunktet(n.value) in paket_namen:
            funde.append((n.lineno, f"{PAKET}.{n.attr}"))
    return funde


def _importeure() -> dict[str, list[tuple[int, str]]]:
    out: dict[str, list[tuple[int, str]]] = {}
    for datei in produktivbaum():
        funde = importe_der_schicht(datei.baum, datei.rel)
        if funde:
            out[datei.rel] = funde
    return out


def test_nur_erlaubte_importeure():
    verstoesse = {rel: f for rel, f in _importeure().items()
                  if not rel.startswith(ERLAUBT_PRAEFIX) and rel not in BENANNTE_TAGESLESER}
    assert not verstoesse, (
        "Die Lese-Schicht der Kanalstatistik wird außerhalb von services/kanal/, services/monats_fakten/ und den "
        "benannten Tages-Lesern importiert:\n  "
        + "\n  ".join(f"{rel}:{z} {m}" for rel, f in sorted(verstoesse.items()) for z, m in f)
        + "\n\nSichten lesen über die Monats-Fakten (Monatsraster + P8). Ein Tages-Leser, der die Schicht wirklich "
        "braucht, gehört mit Grund in BENANNTE_TAGESLESER."
    )


def test_stand_e3_ausserhalb_von_services_kanal_importiert_niemand():
    ausserhalb = {rel for rel in _importeure() if not rel.startswith("services/kanal/")}
    assert ausserhalb == IMPORTEURE_STAND, (
        f"Importeure der Lese-Schicht außerhalb services/kanal/: {sorted(ausserhalb)} — Stand E3 ist "
        f"{sorted(IMPORTEURE_STAND)}. Wer in E4 umhängt, trägt den Leser hier (und ggf. in BENANNTE_TAGESLESER) ein."
    )


def test_die_schicht_selbst_wird_gefunden():
    """Positivkontrolle: der Wächter sieht die Importe innerhalb ``services/kanal/`` — sonst prüfte er nichts."""
    drinnen = {rel for rel in _importeure() if rel.startswith("services/kanal/")}
    assert {"services/kanal/quellenwahl.py", "services/kanal/monatsraster.py"} <= drinnen, drinnen


# ── Gegenprobe im Test: jede Importform einer Route/Sicht wird gefunden ─────

GEGENPROBEN = {
    "from-modul": "from backend.services.kanal.lesen import zeitraum\n",
    "from-paket": "from backend.services.kanal import monatsraster, schreiber\n",
    "import": "import backend.services.kanal.quellenwahl as q\n",
    "in-funktion": "async def f():\n    from backend.services.kanal.fenster import tagesfenster\n",
    "zeichenkette": "import importlib\nm = importlib.import_module('backend.services.kanal.lesen')\n",
    "dunder-import": "m = __import__('backend.services.kanal.lesen')\n",
    "paket-attribut": "import backend.services.kanal\nx = backend.services.kanal.lesen.zeitraum\n",
    "paket-attribut-alias": "import backend.services.kanal as kk\nx = kk.reihe if False else kk.monatsraster.monatsreihe\n",
    "paket-from-services": "from backend.services import kanal\nx = kanal.lesen.zeitraum\n",
    "paket-from-services-alias": "from backend.services import kanal as kn\nx = kn.quellenwahl.quellenwahl\n",
}

#: Relative Importe — (Quelle, Datei relativ zu ``backend/``).
GEGENPROBEN_RELATIV = {
    "relativ-2": ("from ..services.kanal.lesen import zeitraum\n", "api/cockpit.py"),
    "relativ-1-paket": ("from .kanal import lesen\n", "services/sicht.py"),
    "relativ-1-modul": ("from .kanal.lesen import zeitraum\n", "services/sicht.py"),
    "relativ-aus-init": ("from .kanal.fenster import tagesfenster\n", "services/__init__.py"),
    "relativ-3": ("from ...services.kanal import monatsraster\n", "api/routes/kunst.py"),
}


def test_gegenprobe_jede_importform_wird_gefunden():
    for name, quelle in GEGENPROBEN.items():
        assert importe_der_schicht(ast.parse(quelle)), f"Importform „{name}“ nicht erkannt: {quelle!r}"
    # Eine Route mit dieser Zeile wäre ein Verstoß, ein Schreiber-Import nicht.
    assert importe_der_schicht(ast.parse(GEGENPROBEN["from-paket"])) == [(1, "backend.services.kanal.monatsraster")]
    assert not importe_der_schicht(ast.parse("from backend.services.kanal.schreiber import schreibe_spiegel\n"))
    assert not importe_der_schicht(ast.parse("from backend.services.kanal import schreiber, nachfuellen\n"))
    # keine Fehlmeldung: das Paket ohne Schicht-Modul, ein fremdes `.lesen`, ein relativer Schreiber-Import
    assert not importe_der_schicht(ast.parse("import backend.services.kanal\nx = backend.services.kanal.schreiber\n"))
    assert not importe_der_schicht(ast.parse("x = buch.lesen\nkanal = k\ny = kanal.key\n"))
    assert not importe_der_schicht(ast.parse("from .kanal import schreiber\n"), "services/x.py")


def test_gegenprobe_relative_importe_werden_ueber_den_dateipfad_aufgeloest():
    for name, (quelle, rel) in GEGENPROBEN_RELATIV.items():
        assert importe_der_schicht(ast.parse(quelle), rel), f"relative Importform „{name}“ ({rel}) nicht erkannt"
    # innerhalb von services/kanal/ (erlaubt) wird dieselbe Form ebenfalls gefunden — die Positivkontrolle
    assert importe_der_schicht(ast.parse("from .lesen import zeitraum\n"), "services/kanal/monatsraster.py") == [
        (1, "backend.services.kanal.lesen")]


def test_gegenprobe_eine_route_mit_import_wuerde_rot(monkeypatch):
    """Der ganze Wächter, nicht nur der Finder: eine künstliche Route im Baum ⇒ beide Tests melden sie."""
    from backend.tests import quellbaum

    echte = produktivbaum()
    route = quellbaum.Quelldatei(pfad=echte[0].pfad, rel="api/routes/cockpit/kunst.py", quelle="",
                                 baum=ast.parse("from backend.services.kanal.lesen import zeitraum\n"))
    monkeypatch.setattr(f"{__name__}.produktivbaum", lambda: (*echte, route))
    funde = _importeure()
    assert "api/routes/cockpit/kunst.py" in funde
    verstoesse = {rel for rel in funde if not rel.startswith(ERLAUBT_PRAEFIX) and rel not in BENANNTE_TAGESLESER}
    assert verstoesse == {"api/routes/cockpit/kunst.py"}
