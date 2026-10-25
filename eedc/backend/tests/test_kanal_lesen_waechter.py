"""Wächter: wer die Lese-Schicht der Kanalstatistik importieren darf (HA-Bauform E3, Auftrag Punkt 6; Bauplan §5, G7).

**Regel.** Die Lese-Schicht (``services/kanal/lesen.py``, ``fenster.py``, ``quellenwahl.py``, ``monatsraster.py`` und seit
HA-Bauform S3 der Kanal-Stundentag ``stunden_leser.py`` mit seinem Adapter ``stunden_adapter.py``) importieren nur ``services/kanal/`` selbst, ``services/monats_fakten/`` (der eine Aufbereiter, ADR-002/P10) und
ausdrücklich benannte Tages-Leser (``BENANNTE_TAGESLESER``, mit Grund). Keine Route, keine Sicht, kein PDF, kein
Export greift direkt auf ``zeitraum``/``reihe`` zu — Zeiträume ab Monatslänge laufen über das Monatsraster mit der
P8-Überlagerung der Monats-Fakten, nie über ein direktes ``zeitraum()`` über Monatsgrenzen (Bauplan §5).

**Stand E3: außerhalb ``services/kanal/`` (und der Proben) importiert sie NIEMAND** — die Schicht ist gebaut und
geprüft, aber nicht umgehängt. ``IMPORTEURE_STAND`` hält genau das fest (Gleichheit statt Obergrenze); wer umhängt,
trägt den Leser dort ein. **Stand S3 (E-S3-6):** genau ein Importeur außerhalb, der benannte Tages-Leser
``services/energie_profil/kanal_stunden.py`` (er importiert ``stunden_leser``/``stunden_adapter``; die Sichten rufen ihn).
**Stand P-433-3 S3 (Bauplan B11):** derselbe eine Importeur — er liest seither auch ``lesen.stundenmittel_stapel`` für
die Temperaturen je Gerät (``wp_temperaturen_je_stunde``); die Route ``waerme-temperaturen-stunden`` ruft ihn, nie die
Schicht. Dazu der zweite Wächter unten: **Mittelwerte je Stunde liest nur ``lesen.py``** (``KanalStatistik.mean/min/max``
außerhalb nur mit Grund in ``MITTELWERT_LESER_STAND``).

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
SCHICHT = ("lesen", "fenster", "quellenwahl", "monatsraster", "stunden_leser", "stunden_adapter")
SCHICHT_MODULE = {f"{PAKET}.{m}" for m in SCHICHT}

#: Verzeichnisse, die importieren DÜRFEN (Präfix relativ zu ``backend/``).
ERLAUBT_PRAEFIX = ("services/kanal/", "services/monats_fakten/")

#: Tages-Leser, die benannt werden (Datei → Grund). Leer in E3; HA-Bauform S3 (S3-R8): die Aufrufer des
#: Kanal-Stundentags außerhalb ``services/kanal/`` — nur Adapter, nie Routen.
BENANNTE_TAGESLESER: dict[str, str] = {
    "services/energie_profil/kanal_stunden.py": (
        "E-S3-2: der eine Tages-Leser der Stunden-Sichten (/stunden, tage-werte, monat) — Mischzeilen aus "
        "kanal/stunden_leser + stunden_adapter und der Stundenzeile; Routen rufen nur ihn. Die Wärme-Sichten "
        "(energie_profil/waerme.py, waerme_verteilung_tag.py: Stundenform und WP-Strom eines WP-Kanal-Tags) und "
        "serien.py, tage_werte.py, monat.py importieren die Schicht nicht selbst, sie rufen kanal_stunden. "
        "P-433-3 S3: dazu lesen.stundenmittel_stapel für Vorlauf/Rücklauf/Warmwasser je Gerät "
        "(wp_temperaturen_je_stunde; Route waerme-temperaturen-stunden ruft nur ihn)"
    ),
}

#: Wer heute außerhalb ``services/kanal/`` importiert — Stand E3: niemand; Stand S3 (E-S3-6, ``stunden_*`` in
#: ``SCHICHT``): nur der benannte Tages-Leser der Stunden-Sichten.
IMPORTEURE_STAND: set[str] = {"services/energie_profil/kanal_stunden.py"}


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


def test_importeure_ausserhalb_von_services_kanal_wie_der_stand():
    ausserhalb = {rel for rel in _importeure() if not rel.startswith("services/kanal/")}
    assert ausserhalb == IMPORTEURE_STAND, (
        f"Importeure der Lese-Schicht außerhalb services/kanal/: {sorted(ausserhalb)} — der Stand ist "
        f"{sorted(IMPORTEURE_STAND)}. Wer umhängt, trägt den Leser hier (und ggf. in BENANNTE_TAGESLESER) ein."
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
    "stunden-leser": "from backend.services.kanal.stunden_leser import kanal_stundentag\n",
    "stunden-adapter-paket": "from backend.services.kanal import stunden_adapter\n",
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


def test_gegenprobe_eine_route_mit_dem_kanal_stundentag_wuerde_rot(monkeypatch):
    """HA-Bauform S3 (S3-R8, E-S3-6): eine Route, die den Kanal-Stundentag selbst liest statt über
    ``energie_profil/kanal_stunden.py`` ⇒ Verstoß und Abweichung vom Stand."""
    from backend.tests import quellbaum

    echte = produktivbaum()
    route = quellbaum.Quelldatei(pfad=echte[0].pfad, rel="api/routes/energie_profil/kunst.py", quelle="",
                                 baum=ast.parse("from backend.services.kanal.stunden_leser import kanal_stundentag\n"))
    monkeypatch.setattr(f"{__name__}.produktivbaum", lambda: (*echte, route))
    funde = _importeure()
    verstoesse = {rel for rel in funde if not rel.startswith(ERLAUBT_PRAEFIX) and rel not in BENANNTE_TAGESLESER}
    assert verstoesse == {"api/routes/energie_profil/kunst.py"}
    assert {rel for rel in funde if not rel.startswith("services/kanal/")} != IMPORTEURE_STAND


# ── HA-Bauform S5 E-S5-1c (S5-R7c i): wer `kanal_statistik` schreibt, verwirft die gemerkten Kanal-Tage ──────────────
#
# Das Merken je Prozess (``services/kanal/merken.py``) hängt an jedem Schreiben von ``kanal_statistik``. Jedes Modul, das
# dort einfügt, ändert oder löscht, steht in ``SCHREIBER_KANAL_STATISTIK`` **und** ruft ``merken.invalidiere``. Gefunden
# per AST (baumweit ohne ``tests/``): ``insert``/``sqlite_insert``/``update``/``delete`` mit ``KanalStatistik`` als Argument
# (auch über eine Schleifenvariable ``for x in (…, KanalStatistik, …)``), ``KanalStatistik(...)`` als Objekt, und rohes SQL
# (``INSERT [OR …] INTO|UPDATE|DELETE FROM kanal_statistik``) in einer Zeichenkette. Die Liste ist der Stand — sie schrumpft
# nur oder wächst mit Begründung (wie ``IMPORTEURE_STAND``). Nicht erfasst (benannt): zusammengesetzte Zeichenketten
# (f-String, Verkettung) mit dem Tabellennamen.

import re as _re

#: Die Schreibstellen von ``kanal_statistik`` (E-S5-1c, Bauplan S5 §10d R7c (i)) — Datei → Stelle.
SCHREIBER_KANAL_STATISTIK: dict[str, str] = {
    "services/kanal/schreiber.py": "_zeilen_einfuegen (Spiegel, eigene Summe, Mitschrift, abgeleitet, Kosten, Modus-Strom)",
    "services/kanal/abgeleitet.py": "verwerfe_ab (Neuaufbau der abgeleiteten Kanäle)",
    "services/kanal/nachfuellen.py": "neu_spiegeln (Neu-Laden eines Spiegel-Abschnitts)",
    "services/kanal/verwerfen.py": "loesche_zeilen / markiere_quellen (Werkbank «vor dem Sensorbeginn verwerfen»)",
    "api/routes/investitionen/crud.py": "_entferne_messreihen (Investition löschen, N-668)",
}

_SCHREIB_FUNKTIONEN = {"insert", "sqlite_insert", "update", "delete"}
_SQL_SCHREIBEN = _re.compile(r"\b(INSERT\s+(OR\s+\w+\s+)?INTO|UPDATE|DELETE\s+FROM)\s+kanal_statistik\b", _re.IGNORECASE)


def _ruft_name(n: ast.Call) -> str | None:
    f = n.func
    return f.id if isinstance(f, ast.Name) else (f.attr if isinstance(f, ast.Attribute) else None)


def _schleifen_namen(baum: ast.AST) -> set[str]:
    """Namen, die eine Schleife über ein Tupel/eine Liste mit ``KanalStatistik`` bindet."""
    out = set()
    for n in ast.walk(baum):
        if isinstance(n, (ast.For, ast.AsyncFor)) and isinstance(n.target, ast.Name) \
                and isinstance(n.iter, (ast.Tuple, ast.List)) \
                and any(isinstance(e, ast.Name) and e.id == "KanalStatistik" for e in n.iter.elts):
            out.add(n.target.id)
    return out


def schreibt_kanal_statistik(baum: ast.AST) -> list[int]:
    """Die Zeilen, an denen das Modul ``kanal_statistik`` schreibt."""
    ziele = {"KanalStatistik"} | _schleifen_namen(baum)
    out = []
    for n in ast.walk(baum):
        if isinstance(n, ast.Call):
            name = _ruft_name(n)
            if name in _SCHREIB_FUNKTIONEN and n.args and isinstance(n.args[0], ast.Name) and n.args[0].id in ziele:
                out.append(n.lineno)
            elif name == "KanalStatistik":
                out.append(n.lineno)
        elif isinstance(n, ast.Constant) and isinstance(n.value, str) and _SQL_SCHREIBEN.search(n.value):
            out.append(n.lineno)
    return out


def ruft_invalidiere(baum: ast.AST) -> bool:
    """Ruft das Modul ``merken.invalidiere(...)`` (oder ein importiertes ``invalidiere``)?"""
    for n in ast.walk(baum):
        if isinstance(n, ast.Call):
            f = n.func
            if isinstance(f, ast.Attribute) and f.attr == "invalidiere" and isinstance(f.value, ast.Name) \
                    and f.value.id == "merken":
                return True
            if isinstance(f, ast.Name) and f.id == "invalidiere":
                return True
    return False


def _schreiber_kanal_statistik() -> dict[str, list[int]]:
    out = {}
    for datei in produktivbaum():
        if datei.rel.startswith("models/"):
            continue        # die Modell-Definition selbst
        z = schreibt_kanal_statistik(datei.baum)
        if z:
            out[datei.rel] = z
    return out


def test_schreiber_kanal_statistik_wie_der_stand():
    funde = _schreiber_kanal_statistik()
    assert set(funde) == set(SCHREIBER_KANAL_STATISTIK), (
        f"Module, die kanal_statistik schreiben: {sorted(funde)} — der Stand ist {sorted(SCHREIBER_KANAL_STATISTIK)}. "
        "Wer eine Schreibstelle hinzufügt, trägt sie in SCHREIBER_KANAL_STATISTIK ein UND ruft dort "
        "merken.invalidiere (services/kanal/merken.py, Bauplan S5 §10d R7c (i))."
    )


def test_jeder_schreiber_von_kanal_statistik_ruft_invalidiere():
    ohne = sorted(d.rel for d in produktivbaum() if d.rel in SCHREIBER_KANAL_STATISTIK and not ruft_invalidiere(d.baum))
    assert not ohne, f"Schreibstellen von kanal_statistik ohne merken.invalidiere: {ohne}"


def test_gegenprobe_schreiber_formen():
    """Jede Form wird gefunden; ein Modul, das nur liest, nicht."""
    formen = {
        "sqlite_insert": "sqlite_insert(KanalStatistik).on_conflict_do_nothing()\n",
        "delete": "await db.execute(delete(KanalStatistik).where(x))\n",
        "update": "await db.execute(update(KanalStatistik).values(sum=1))\n",
        "schleife": "for kind in (KanalStatistik, KanalQuelle):\n    delete(kind)\n",
        "objekt": "db.add(KanalStatistik(kanal_id=1, start_ts=0))\n",
        "sql": "text('DELETE FROM kanal_statistik WHERE kanal_id = 1')\n",
        "sql-or": "text('INSERT OR IGNORE INTO kanal_statistik VALUES (1)')\n",
    }
    for name, quelle in formen.items():
        assert schreibt_kanal_statistik(ast.parse(quelle)), name
    assert not schreibt_kanal_statistik(ast.parse("select(KanalStatistik.sum).where(KanalStatistik.kanal_id == 1)\n"
                                                  "text('SELECT * FROM kanal_statistik')\n"))
    assert ruft_invalidiere(ast.parse("merken.invalidiere(1, von=d)\n"))
    assert not ruft_invalidiere(ast.parse("merken.leeren()\n"))


def test_gegenprobe_neuer_schreiber_ohne_invalidiere_wuerde_rot(monkeypatch):
    """Der ganze Wächter: ein künstliches Modul, das kanal_statistik löscht ⇒ Abweichung vom Stand."""
    from backend.tests import quellbaum

    echte = produktivbaum()
    kunst = quellbaum.Quelldatei(pfad=echte[0].pfad, rel="services/kunst.py", quelle="",
                                 baum=ast.parse("delete(KanalStatistik)\n"))
    monkeypatch.setattr(f"{__name__}.produktivbaum", lambda: (*echte, kunst))
    assert "services/kunst.py" in _schreiber_kanal_statistik()


# ── P-433-3 S3 (Bauplan B7/W6, F-56-Klasse): Mittelwerte je Stunde liest nur `lesen.py` ──────────────────────────────
#
# ``lesen.stundenmittel_stapel`` ist der eine Stundenleser für Mittelwert-Kanäle (mean/min/max je Stunde, Abdeckung).
# Bis P-433-3 S3 las ``kosten._preise`` ``KanalStatistik.mean`` selbst — ein zweiter, roher Leser derselben Zeilen ohne
# Abdeckung. Der Wächter findet jeden Attributzugriff ``KanalStatistik.mean``/``.min``/``.max`` (AST, baumweit ohne
# ``tests/``) außerhalb von ``lesen.py``; der Bestand steht mit Grund in ``MITTELWERT_LESER_STAND`` (Gleichheit — er
# schrumpft nur oder wächst mit Begründung). Nicht erfasst (benannt): rohes SQL mit ``mean`` als Zeichenkette (das liest
# heute nur ``lesen.py``; ``ha_statistics_service`` liest HAs Tabelle ``statistics``, nicht ``kanal_statistik``).

_MITTEL_SPALTEN = {"mean", "min", "max"}

#: Wer außerhalb ``lesen.py`` die Mittelwert-Spalten von ``kanal_statistik`` anfasst — Datei → Grund.
MITTELWERT_LESER_STAND: dict[str, str] = {
    "services/kanal/kosten.py": "_letzter_preis: nur der Fortschritt des Preis-Spiegels (letzte Zeile mit Mittel), "
                                "kein Wert — die Preise je Stunde liest _preise über lesen.stundenmittel_stapel",
    "services/kanal/modus_strom.py": "_mitschrift_anteile: Anteile der Betriebsart-Mitschrift je Stunde (vorbestehend, "
                                     "Schreiber-intern; Umhängen auf stundenmittel_stapel nicht beauftragt)",
}


def liest_mittelwert_spalten(baum: ast.AST) -> list[int]:
    """Zeilen mit ``KanalStatistik.mean``/``.min``/``.max``."""
    return [n.lineno for n in ast.walk(baum)
            if isinstance(n, ast.Attribute) and n.attr in _MITTEL_SPALTEN
            and isinstance(n.value, ast.Name) and n.value.id == "KanalStatistik"]


def _mittelwert_leser() -> dict[str, list[int]]:
    out = {}
    for datei in produktivbaum():
        if datei.rel in ("services/kanal/lesen.py",) or datei.rel.startswith("models/"):
            continue
        z = liest_mittelwert_spalten(datei.baum)
        if z:
            out[datei.rel] = z
    return out


def test_mittelwerte_je_stunde_liest_nur_lesen_py():
    funde = _mittelwert_leser()
    assert set(funde) == set(MITTELWERT_LESER_STAND), (
        f"KanalStatistik.mean/min/max außerhalb lesen.py: {sorted(funde)} — der Stand ist "
        f"{sorted(MITTELWERT_LESER_STAND)}. Mittelwerte je Stunde über lesen.stundenmittel_stapel lesen."
    )


def test_kosten_preise_lesen_ueber_stundenmittel_stapel():
    """W6: ``kosten._preise`` ruft den Stundenleser der Schicht (Positivkontrolle — ohne ihn wäre der Stand oben leer
    erfüllbar, indem jemand die Spalte über einen Alias liest)."""
    import inspect

    from backend.services.kanal import kosten

    import textwrap

    baum = ast.parse(textwrap.dedent(inspect.getsource(kosten._preise)))
    gerufen = {n.func.id for n in ast.walk(baum) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}
    assert "stundenmittel_stapel" in gerufen
    assert not liest_mittelwert_spalten(baum)


def test_gegenprobe_mittelwert_leser(monkeypatch):
    from backend.tests import quellbaum

    assert liest_mittelwert_spalten(ast.parse("select(KanalStatistik.start_ts, KanalStatistik.mean)\n")) == [1]
    assert liest_mittelwert_spalten(ast.parse("x = KanalStatistik.min\ny = KanalStatistik.max\n")) == [1, 2]
    assert not liest_mittelwert_spalten(ast.parse("select(KanalStatistik.sum)\nm = sm.mean\n"))
    echte = produktivbaum()
    kunst = quellbaum.Quelldatei(pfad=echte[0].pfad, rel="api/routes/kunst.py", quelle="",
                                 baum=ast.parse("select(KanalStatistik.mean)\n"))
    monkeypatch.setattr(f"{__name__}.produktivbaum", lambda: (*echte, kunst))
    assert "api/routes/kunst.py" in _mittelwert_leser()
