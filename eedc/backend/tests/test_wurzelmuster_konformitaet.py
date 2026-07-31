"""Konformitäts-Wächter gegen sechs der sieben Wurzelmuster (A14/A17/A24/A25/A27/R8-4).

Hintergrund: Befund-Sweep `docs/drafts/BEFUND-SWEEP-WURZELMUSTER.md`. Elf
Commits der v4.0.1-Runde haben Fundstellen einzeln geheilt, jeder Fix erzeugte
den nächsten Fund. Diese Datei macht sechs der Muster maschinell prüfbar, damit
sie nicht neu entstehen. Sie prüft **Struktur, keine Werte** — deshalb kein
`db`-Fixture, kein I/O, kein Netz.

Bewusst hier und nicht als `check:*`-Skript: alle 23 `check:*` sind
Frontend-Node-Skripte (`eedc/frontend/scripts/check-*.mjs`, in CI unter
`.github/workflows/tests.yml`). Ein Backend-Grep-Skript daneben wäre eine zweite
Mechanik für dieselbe Aufgabe; als pytest läuft der Wächter im bestehenden
Backend-Gate mit, und die Baseline steht als Konstante im Code statt in einer
separaten Allowlist-Datei.

**Analyse per AST, nicht per Regex.** Ein Regex übersieht mehrzeilige Aufrufe
und `.get(KONSTANTE)`; beides kommt im Bestand vor.

Gewächterte Muster:

  P6 — stille Null bei JSON-Key-Zugriff. Ein falscher Schlüssel auf einem
       JSON-Feld liefert still `0`, und `0` sieht aus wie „keine Daten". So
       lebte der PVGIS-Bug (N38, `e_month_kwh` statt `e_m`) jahrelang, und so
       liest `api/routes/data_import.py:174` bis heute `parameter["leistung_kwp"]`
       — ein Schlüssel, den es in keinem Regime gibt (N59, Abfluss A17).
       Hier gewächtert: `InvestitionMonatsdaten.verbrauch_daten` /
       `Monatsdaten.verbrauch_daten` gegen die Feld-SoT `core/field_definitions`
       — seit A25 in allen drei Zugriffsformen (`.get()`, Subscript **lesend
       wie schreibend**, Dict-Literal bei Zuweisung). Die Schreibseite ist der
       schärfere Fall: ein Tippfehler dort legt einen Schlüssel an, den kein
       Leser liest, und der korrekte Leser bekommt still `0`.

  P3 — SoT-Helper umgangen. `_distribute_by_param` verteilt einen Gesamtwert
       nach kWp/Kapazität und ignoriert dabei eine explizite
       Feld→Investition-Zuordnung. Genau das war #352: der Monatsabschluss rief
       ihn direkt auf und übersprang die Zuordnung (`0a08cca6`). Zuordnungs-SoT
       ist `_mapped_or_distribute`.

  P5 — Auswahlregel der aktiven PVGIS-Prognose. Die vier Zeilen
       (`ist_aktiv == True` · `ORDER BY abgerufen_am DESC` · `LIMIT 1`) standen
       23-mal als Kopie im Repo; 6 Kopien wichen ab, auf drei verschiedene Arten
       (2× HTTP 500, 1× verdoppelte Summe, 3× älteste statt aktiver). Seit A17
       liegt die Regel in `services/prognose_auswahl.py`; dieser Wächter hält die
       Lesestellen darauf, damit keine 24. Kopie entsteht.

  P3-b — Literal-Schlüssel im `parameter`-JSON gegen den Kanon
       `core/investition_parameter.py` (A27). Dieselbe stille Null wie bei P6,
       nur auf dem anderen JSON-Feld: `inv.parameter.get("ladeleistung_kw")`
       liefert nach der v3.25.0-Migration `None`, und der Aufrufer rechnet mit
       0 weiter. Genau so waren die 7 Drift-Bugs entstanden, die v3.25.0
       aufgeräumt hat. Dazu N115: der Kanon und die ausgeführte Migration
       hingen bis A27 an nichts und wichen bereits voneinander ab.

  P3-a — Investitions-Kennwerte nur über den SoT-Helper (A24-3, die
       **#229-Klasse**). Die Nennleistung liegt je nach Herkunft in der Spalte
       `Investition.leistung_kwp` **oder** im `parameter`-JSON; wer nur die
       Spalte liest, sieht bei param-gepflegten Modulen still 0. Daraus sind N52
       (14,0 statt 10,0 kWp in der Live-Gesamtleistung), N66 (Falschmeldung des
       Daten-Checkers) und ein HTTP 400 in der PVGIS-Prognose entstanden — jedes
       einzeln geheilt, jedes Mal ohne Wächter, jedes Mal entstand die nächste
       Kopie. SoT ist `core/investition_kennwerte.py`.

  P7 — Das PV-Anlagen-Aggregat `Monatsdaten.pv_erzeugung_kwh` ist **Eingang**
       der Auflösung, kein Wert (R8-4, 2026-07-29). Drei Sichten rechneten
       daran vorbei: Cockpit und HA-Export bildeten eine rohe IMD-Summe und
       schalteten über ein globales Flag um (`19ae5f73`), die Daten-Checker-
       Karte tat dasselbe mit Aggregat-Fallback. Bei teilweise gemessenen
       Strings ging so eine **Teilsumme** in Finanzen, spezifischen Ertrag,
       Performance-Ratio und SOLL/IST-Abweichung. SoT ist
       `core/berechnungen/pv_verteilung.py`, Ladepfad `services/pv_monatswerte.py`.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Iterator

from backend.core import field_definitions as fd
from backend.core import investition_parameter as ip

# Repo-relativer Wurzelpfad des Backends (`conftest.py` legt `eedc/` in sys.path).
_BACKEND = Path(__file__).resolve().parents[1]


def _quelldateien() -> Iterator[tuple[Path, ast.Module]]:
    """Alle Produktiv-Python-Dateien des Backends als geparste AST-Bäume.

    Ausgenommen: `tests/` (Fixtures dürfen alles), `venv/`, `__pycache__`.
    """
    for pfad in sorted(_BACKEND.rglob("*.py")):
        teile = pfad.relative_to(_BACKEND).parts
        if teile[0] in ("tests", "venv") or "__pycache__" in teile:
            continue
        try:
            yield pfad, ast.parse(pfad.read_text(errors="ignore"))
        except SyntaxError:  # pragma: no cover — defekte Datei bricht schon anders
            continue


def _ort(pfad: Path, knoten: ast.AST) -> str:
    return f"backend/{pfad.relative_to(_BACKEND).as_posix()}:{knoten.lineno}"


# ============================================================================
# P6 — verbrauch_daten-Schlüssel gegen die Feld-SoT
# ============================================================================


def _kanonische_feldnamen() -> set[str]:
    """Alle gültigen Schlüssel in einem `verbrauch_daten`-JSON.

    Drei Quellen, alle aus `core/field_definitions` (der Feld-SoT):
      - `ALLE_MONATSDATEN_FELDNAMEN` — Anlage-weite Zählerfelder
      - `INVESTITION_FELDER` — Felder je Investitionstyp (rekursiv, weil
        `sonstiges` nach Kategorie verschachtelt ist)
      - `LEGACY_FELDNAMEN` — alte Schreibweisen; sie zu LESEN ist legitim
        (Rückwärtskompatibilität, vgl. `resolve_legacy_key`)
    """
    aus_investitionen: set[str] = set()

    def sammle(knoten) -> None:
        if isinstance(knoten, list):
            for eintrag in knoten:
                if isinstance(eintrag, dict) and "feld" in eintrag:
                    aus_investitionen.add(eintrag["feld"])
        elif isinstance(knoten, dict):
            for wert in knoten.values():
                sammle(wert)

    sammle(fd.INVESTITION_FELDER)
    return (
        set(fd.ALLE_MONATSDATEN_FELDNAMEN)
        | aus_investitionen
        | set(fd.LEGACY_FELDNAMEN)
    )


# Klassifizierte Baseline (A14, Reichweite erweitert A25/2026-07-27): Schlüssel,
# die bewusst NICHT in `field_definitions` stehen, weil sie keine Messfelder
# sind. Beide sind geprüft und dokumentiert — kein Bug, keine Nachziehschuld.
# Die A25-Erweiterung auf Subscript- und Dict-Literal-Form hat **keine dritte
# Ausnahme** nötig gemacht: alle 18 Schreib- und 8 Lese-Subscripts sowie alle 6
# Dict-Literal-Schlüssel im Baum stehen im Kanon, bis auf `sonstige_positionen`.
#
#   sonstige_positionen  — LISTE von Sonderposten-Dicts, kein Skalar-Feld.
#                          `field_definitions` beschreibt Eingabefelder mit
#                          Einheit/Label; eine Positionsliste hat beides nicht.
#                          Gelesen in api/routes/monatsabschluss/views.py:540f.
#                          und utils/sonstige_positionen.py:72, geschrieben in
#                          api/routes/import_export/demo_data.py:445/449/454.
#   sonderkosten_notiz   — FREITEXT zur Sonderkosten-Zeile, kein Messwert.
#                          Gelesen in utils/sonstige_positionen.py:76.
#
# Wer hier etwas hinzufügt, dokumentiert im Klartext WARUM der Schlüssel kein
# Feld ist. Ein neues Messfeld gehört nach `field_definitions`, nicht hierher
# (dort hängen Wizard, CSV-Template, Import-Mapping und Hilfetexte dran).
P6_BASELINE_AUSNAHMEN: frozenset[str] = frozenset(
    {"sonstige_positionen", "sonderkosten_notiz"}
)


def _p6_entpacke_or_leer(knoten: ast.AST) -> ast.AST:
    """`(x or {})` → `x`; alles andere unverändert.

    Die Form `(imd.verbrauch_daten or {}).get(…)` ist im Bestand häufig; ohne
    dieses Entpacken sähe der Wächter einen Großteil der Stellen nicht.
    """
    if isinstance(knoten, ast.BoolOp) and isinstance(knoten.op, ast.Or):
        if len(knoten.values) == 2:
            rechts = knoten.values[1]
            if isinstance(rechts, ast.Dict) and not rechts.keys:
                return knoten.values[0]
    return knoten


def _ist_verbrauch_daten(knoten: ast.AST) -> bool:
    """Hält dieser Ausdruck DIREKT ein `verbrauch_daten`-JSON?

    Erfasst die im Bestand vorkommenden Formen — `imd.verbrauch_daten`,
    `(imd.verbrauch_daten or {})`, die lokale Variable `verbrauch_daten` und
    die **präfigierte** lokale Variable `eauto_verbrauch_daten` (Suffix-Regel).
    Das Suffix ist nicht kosmetisch: 5 der 18 Schreibstellen des Bestands
    (`api/routes/import_export/demo_data.py:441-454`) hängen ausschließlich
    daran, das Dict wandert dort unverändert in `_add_demo_imd`.

    **Bewusst DIREKT statt Teilbaum-Suche (A25):** die Vorgänger-Fassung lief
    mit `ast.walk` über den ganzen Ausdruck vor dem `.get` und hätte damit auch
    `berechne_sonstige_summen(verbrauch_daten)["netto_euro"]`
    (`utils/sonstige_positionen.py:113`) getroffen — ein ABGELEITETES Dict mit
    eigenen Schlüsseln, kein `verbrauch_daten`. Beim `.get()`-Zweig war das
    folgenlos (beide Fassungen erfassen dort dieselben 32 Stellen, gemessen);
    mit dem neuen Subscript-Zweig wäre daraus eine Falschmeldung geworden, die
    nur eine unberechtigte dritte Baseline-Ausnahme (`netto_euro`) hätte
    stillstellen können. Dieselbe enge Empfänger-Form wie bei P3-b (E11).
    """
    entpackt = _p6_entpacke_or_leer(knoten)
    if isinstance(entpackt, ast.Attribute):
        name = entpackt.attr
    elif isinstance(entpackt, ast.Name):
        name = entpackt.id
    else:
        return False
    return name == "verbrauch_daten" or name.endswith("_verbrauch_daten")


def _verbrauch_daten_zugriffe() -> list[tuple[str, str]]:
    """Alle Literal-Schlüssel auf einem `verbrauch_daten`-JSON als `(ort, schlüssel)`.

    Drei Formen, seit A25 alle drei (vorher nur die erste):

      - `…verbrauch_daten.get("literal")` — der Lesepfad, 32 Stellen.
      - `…verbrauch_daten["literal"]` — Subscript, **Lesen und Schreiben**
        (Entscheidung E13: eine Regel statt einer Fallunterscheidung). Der alte
        ADR-Satz „beim Lesen wirft ein fehlender Schlüssel `KeyError`, also laut
        statt still `0`" trägt nur, solange die Stelle nicht in einem
        `try/except` sitzt — und das prüft niemand nach. Bestand: 18 schreibend
        (`import_export/helpers.py`, `import_export/demo_data.py`), 8 lesend
        (`custom_import/apply.py`, `monatsabschluss/views.py`,
        `utils/sonstige_positionen.py`).
      - `…verbrauch_daten = {"literal": …}` — Dict-Literal bei Zuweisung
        (Entscheidung E14). Es ist die naheliegendste Umgehung der
        Subscript-Regel; bei P3-a war genau die nicht abgedeckte Form
        (`getattr`) die Stelle, an der ein Defekt durchfiel. Bestand: 6
        Schlüssel an 2 Zuweisungen, alle im Kanon.

    Die Schreibseite ist der schärfere Fall: ein Tippfehler in
    `verbrauch_daten["typo_kwh"] = …` wirft nichts, sondern legt einen Schlüssel
    an, den kein Leser liest — der korrekt lesende Aufrufer bekommt still `0`.
    """
    treffer: list[tuple[str, str]] = []

    def nimm(pfad: Path, ort_knoten: ast.AST, schluessel_knoten: ast.AST) -> None:
        if isinstance(schluessel_knoten, ast.Constant) and isinstance(
            schluessel_knoten.value, str
        ):
            treffer.append((_ort(pfad, ort_knoten), schluessel_knoten.value))
        # `.get(KONSTANTE)` bzw. ein berechneter Schlüssel ist die gewünschte
        # Form — dort kann kein Tippfehler still durchrutschen.

    for pfad, baum in _quelldateien():
        for knoten in ast.walk(baum):
            if isinstance(knoten, ast.Call):
                funktion = knoten.func
                if not (isinstance(funktion, ast.Attribute) and funktion.attr == "get"):
                    continue
                if not knoten.args:
                    continue
                if not _ist_verbrauch_daten(funktion.value):
                    continue
                nimm(pfad, knoten, knoten.args[0])

            elif isinstance(knoten, ast.Subscript):
                # Beide `ctx` — Load wie Store (E13).
                if not _ist_verbrauch_daten(knoten.value):
                    continue
                nimm(pfad, knoten, knoten.slice)

            elif isinstance(knoten, (ast.Assign, ast.AnnAssign)):
                ziele = (
                    knoten.targets if isinstance(knoten, ast.Assign) else [knoten.target]
                )
                if not any(_ist_verbrauch_daten(ziel) for ziel in ziele):
                    continue
                wert = getattr(knoten, "value", None)
                if not isinstance(wert, ast.Dict):
                    continue
                for schluessel_knoten in wert.keys:
                    # Ort = die Schlüsselzeile, nicht die Zuweisung: mehrzeilige
                    # Dict-Literale sind der Normalfall.
                    if schluessel_knoten is not None:
                        nimm(pfad, schluessel_knoten, schluessel_knoten)

    return treffer


def test_p6_verbrauch_daten_schluessel_stehen_in_der_feld_sot():
    """Jeder Literal-Schlüssel auf `verbrauch_daten` muss ein bekanntes Feld sein.

    Verhindert den N38-/N59-Mechanismus: falscher Schlüssel → still `0` → `0`
    liest sich als „keine Daten" → der Fehler fällt jahrelang nicht auf. Seit
    A25 auf der **Schreibseite** genauso wie beim Lesen — dort ist die stille
    Null sogar zwangsläufig, weil der falsch geschriebene Schlüssel nie gelesen
    und der richtig gelesene nie geschrieben wird.
    """
    kanon = _kanonische_feldnamen()
    unbekannt = [
        (ort, schluessel)
        for ort, schluessel in _verbrauch_daten_zugriffe()
        if schluessel not in kanon and schluessel not in P6_BASELINE_AUSNAHMEN
    ]

    assert not unbekannt, (
        "Unbekannte verbrauch_daten-Schlüssel — ein Tippfehler liefert hier still 0, "
        "und 0 sieht aus wie „keine Daten“ (N38-Mechanismus):\n"
        + "\n".join(f"  {ort} → {schluessel!r}" for ort, schluessel in unbekannt)
        + "\n\nEntweder das Feld nach core/field_definitions aufnehmen (dort hängen "
        "Wizard, CSV-Template, Import-Mapping und Hilfetexte dran) — oder, wenn es "
        "kein Messfeld ist, mit Klartext-Begründung in P6_BASELINE_AUSNAHMEN."
    )


def test_p6_baseline_ausnahmen_sind_noch_belegt():
    """Die Baseline darf nicht über ihre Fundstellen hinaus wachsen.

    Wird eine Ausnahme im Produktivcode entfernt, muss sie auch hier raus —
    sonst deckt sie irgendwann einen echten neuen Treffer mit demselben Namen.
    """
    gelesen = {schluessel for _, schluessel in _verbrauch_daten_zugriffe()}
    verwaist = P6_BASELINE_AUSNAHMEN - gelesen

    assert not verwaist, (
        f"Baseline-Ausnahmen ohne Fundstelle: {sorted(verwaist)}. "
        "Der Zugriff ist weg — den Eintrag aus P6_BASELINE_AUSNAHMEN entfernen."
    )


# ============================================================================
# P3 — Zuordnungs-SoT: keine Direktaufrufe von _distribute_by_param (N48)
# ============================================================================

# `_distribute_by_param` verteilt blind nach Parameter. `_mapped_or_distribute`
# prüft davor die explizite Feld→Investition-Zuordnung und verteilt nur, wenn
# keine existiert. Beide leben in derselben Datei; ein Aufruf von außen greift
# also immer an der Zuordnung vorbei. Genau das war #352 (`0a08cca6`).
N48_DEFINITIONS_MODUL = "backend/api/routes/connector.py"

# Klassifizierte Baseline (A14, Stand 2026-07-26): **leer**. Seit `0a08cca6`
# gibt es außerhalb des Definitions-Moduls keinen Aufrufer mehr — der Wächter
# hält diesen Zustand, er dokumentiert keine Altlast.
N48_BASELINE_AUSNAHMEN: frozenset[str] = frozenset()


def test_p3_distribute_by_param_nur_ueber_die_zuordnungs_sot():
    """`_distribute_by_param` darf nur aus seinem eigenen Modul aufgerufen werden.

    Erfasst auch den Import (`from … import _distribute_by_param`), weil ein
    Aufruf über einen lokalen Alias sonst durchrutschte.
    """
    verstoesse: list[str] = []
    for pfad, baum in _quelldateien():
        modul = f"backend/{pfad.relative_to(_BACKEND).as_posix()}"
        if modul == N48_DEFINITIONS_MODUL or modul in N48_BASELINE_AUSNAHMEN:
            continue
        for knoten in ast.walk(baum):
            if isinstance(knoten, ast.Call):
                funktion = knoten.func
                name = (
                    funktion.id
                    if isinstance(funktion, ast.Name)
                    else funktion.attr
                    if isinstance(funktion, ast.Attribute)
                    else None
                )
                if name == "_distribute_by_param":
                    verstoesse.append(f"  {_ort(pfad, knoten)} — Direktaufruf")
            elif isinstance(knoten, ast.ImportFrom):
                for alias in knoten.names:
                    if alias.name == "_distribute_by_param":
                        verstoesse.append(f"  {_ort(pfad, knoten)} — Import")

    assert not verstoesse, (
        "Direktaufruf/Import von _distribute_by_param außerhalb von "
        f"{N48_DEFINITIONS_MODUL}:\n" + "\n".join(verstoesse) + "\n\n"
        "Das übergeht die explizite Feld→Investition-Zuordnung und verteilt "
        "stattdessen nach kWp/Kapazität (#352). Stattdessen "
        "_mapped_or_distribute(field_inv_map, kategorie, kandidaten, total, param_key) "
        "verwenden — die verteilt nur, wenn keine Zuordnung existiert."
    )


def test_p3_zuordnungs_sot_existiert_noch():
    """Gegenprobe: der Wächter oben wäre wertlos, wenn die SoT umbenannt würde.

    Ohne diese Prüfung wird das Gate still grün, sobald `_distribute_by_param`
    oder `_mapped_or_distribute` heißt wie etwas anderes.
    """
    quelle = (_BACKEND / "api/routes/connector.py").read_text()
    baum = ast.parse(quelle)
    definiert = {
        knoten.name
        for knoten in ast.walk(baum)
        if isinstance(knoten, (ast.FunctionDef, ast.AsyncFunctionDef))
    }

    for erwartet in ("_distribute_by_param", "_mapped_or_distribute"):
        assert erwartet in definiert, (
            f"{erwartet} existiert nicht mehr in {N48_DEFINITIONS_MODUL}. "
            "Wurde umbenannt oder verschoben? Dann diesen Wächter mitziehen — "
            "sonst prüft er ab jetzt nichts mehr."
        )


# ============================================================================
# P5 — Auswahl der aktiven PVGIS-Prognose nur über den Auswahl-SoT
# ============================================================================

# Der SoT: `services/prognose_auswahl.py`. Alles andere liest die aktive Prognose
# über `lade_aktive_prognose` / `lade_aktive_prognose_sync` /
# `lade_aktive_monatsprognosen` — nie über eine eigene Query.
P5_SOT_MODUL = "backend/services/prognose_auswahl.py"

# Klassifizierte Baseline (A17): die einzigen Module, die `ist_aktiv` legitim
# selbst anfassen. Beide SETZEN das Flag oder listen es, sie WÄHLEN keinen Wert
# damit aus — das ist die Grenze, die dieser Wächter zieht.
#
#   api/routes/pvgis.py
#       Verwaltungs-/Schreibpfad: beim Neu-Abrufen die alten deaktivieren, beim
#       Aktivieren umschalten, alle Prognosen listen. Hier ENTSTEHT der
#       Nutzerwille, den der SoT anschließend liest.
#   api/routes/import_export/json_operations.py
#       Export (alle Prognosen inkl. Flag) und Import (normalisiert die Datei auf
#       genau eine aktive, s. `tests/test_wurzelmuster_p5_invariante.py`).
#   api/routes/import_export/demo_data.py
#       Legt Demo-Prognosen an — Schreibpfad.
#
# Wer hier etwas hinzufügt, begründet im Klartext, warum die Stelle das Flag
# SETZT statt einen Wert damit AUSZUWÄHLEN. Ein Lesepfad gehört nicht hierher,
# sondern auf den Helper.
P5_BASELINE_AUSNAHMEN: frozenset[str] = frozenset({
    "backend/api/routes/pvgis.py",
    "backend/api/routes/import_export/json_operations.py",
    "backend/api/routes/import_export/demo_data.py",
})

# Der Modellname und seine im Bestand vorkommenden Import-Aliase.
_PVGIS_MODELL_NAMEN = ("PVGISPrognose", "PVGISPrognoseModel")


def _pvgis_ist_aktiv_zugriffe() -> list[str]:
    """Alle `<PVGISPrognose|Alias>.ist_aktiv`-Zugriffe außerhalb von SoT/Baseline."""
    treffer: list[str] = []
    for pfad, baum in _quelldateien():
        modul = f"backend/{pfad.relative_to(_BACKEND).as_posix()}"
        if modul == P5_SOT_MODUL or modul in P5_BASELINE_AUSNAHMEN:
            continue
        for knoten in ast.walk(baum):
            if not (isinstance(knoten, ast.Attribute) and knoten.attr == "ist_aktiv"):
                continue
            ziel = knoten.value
            name = ziel.id if isinstance(ziel, ast.Name) else None
            if name in _PVGIS_MODELL_NAMEN:
                treffer.append(_ort(pfad, knoten))
    return treffer


def test_p5_aktive_prognose_nur_ueber_den_auswahl_sot():
    """Kein Lesepfad darf die Auswahlregel selbst formulieren.

    Baseline 0 seit A17. Der Wächter verhindert nicht „irgendeine Query", sondern
    genau die Wiederholung der REGEL: sobald ein Modul `PVGISPrognose.ist_aktiv`
    in ein eigenes `select`/`filter` schreibt, entscheidet es selbst über
    Tiebreak und `limit` — und dort entstanden alle 6 Abweichungen.
    """
    verstoesse = _pvgis_ist_aktiv_zugriffe()

    assert not verstoesse, (
        "Eigene Auswahl der aktiven PVGIS-Prognose außerhalb von "
        f"{P5_SOT_MODUL}:\n" + "\n".join(f"  {ort}" for ort in verstoesse) + "\n\n"
        "Stattdessen `lade_aktive_prognose(db, anlage_id)` (async), "
        "`lade_aktive_prognose_sync(db, anlage_id)` oder — für die normalisierten "
        "Monatszeilen — `lade_aktive_monatsprognosen(db, anlage_id, monat=…)` aus "
        "backend/services/prognose_auswahl.py verwenden. Wer das Flag SETZT statt "
        "damit auszuwählen, gehört mit Begründung in P5_BASELINE_AUSNAHMEN."
    )


def test_p5_auswahl_sot_traegt_die_regel_noch():
    """Gegenprobe: der Wächter wäre wertlos, wenn der SoT die Regel verliert.

    Ohne diese Prüfung wird das Gate still grün, sobald jemand im Helper das
    `limit(1)` oder das `order_by(abgerufen_am.desc())` entfernt — dann gilt
    zwar noch „nur eine Stelle", aber nicht mehr „die richtige Regel".
    """
    quelle = (_BACKEND / "services/prognose_auswahl.py").read_text()
    baum = ast.parse(quelle)

    definiert = {
        knoten.name
        for knoten in ast.walk(baum)
        if isinstance(knoten, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    for erwartet in (
        "aktive_prognose_query",
        "lade_aktive_prognose",
        "lade_aktive_prognose_sync",
        "lade_aktive_monatsprognosen",
    ):
        assert erwartet in definiert, (
            f"{erwartet} existiert nicht mehr in {P5_SOT_MODUL} — umbenannt oder "
            "verschoben? Dann diesen Wächter mitziehen, sonst prüft er nichts mehr."
        )

    for bestandteil, bedeutung in (
        ("ist_aktiv.is_(True)", "der Aktiv-Filter (Nutzerwille)"),
        ("abgerufen_am.desc()", "der Tiebreak „zuletzt abgerufene“"),
        (".limit(1)", "die Absicherung gegen verletzte Invarianten"),
    ):
        assert bestandteil in quelle, (
            f"{bestandteil} fehlt im Auswahl-SoT — {bedeutung} ist damit weg. "
            "Genau diese drei Bestandteile sind die Regel P5; ohne sie ist der "
            "Wächter oben ein grünes Gate über einem offenen Bug."
        )


# ============================================================================
# P3-a — Investitions-Kennwerte nur über den SoT-Helper (die #229-Klasse)
# ============================================================================

# Der SoT: `core/investition_kennwerte.py` mit `get_pv_kwp` / `get_bkw_kwp` /
# `get_erzeuger_kwp`. Jeder liest erst die Spalte, dann das `parameter`-JSON.
P3A_SOT_MODUL = "backend/core/investition_kennwerte.py"

# Die bewachten Attributnamen als Konstante, nicht als Literal im Prüfcode:
# eine Erweiterung auf `neigung_grad` / `ausrichtung` ist damit ein
# Listeneintrag plus Allowlist, kein Neubau. Bewusst **nicht** in A24 gemacht —
# `get_pv_neigung` defaultet auf 35°, `get_pv_azimut` auf Süd, und beide können
# „fehlt" nicht von „gepflegt" unterscheiden. Eine blanke Migration der
# Anzeige-Stellen machte aus einem heute korrekt leeren Feld eine erfundene
# Zahl (Befund-Sweep §5.5); das braucht eine eigene Erhebung mit eigener
# Vorfrage (default-freie Helper-Variante?).
P3A_KENNWERT_ATTRIBUTE: frozenset[str] = frozenset({"leistung_kwp"})

# Empfänger-Namen, die außerhalb der Regel stehen. Keine Typinferenz — dieselbe
# bewusste Grenze, die der P5-Wächter mit seiner Modellnamen-Liste zieht.
#
#   anlage       Die ANLAGE hat kein `parameter`-JSON. Es gibt dort keinen
#                „effektiven Wert", von dem die Spalte abwiche — `anlage.leistung_kwp`
#                IST der Wert (und der Vergleichsmaßstab, gegen den die Summe der
#                Investitionen geprüft wird). 40 Zugriffe, alle außerhalb von P3-a.
#   Investition  Der Spaltenausdruck in `select()/where()/order_by()` liest keinen
#                Wert, sondern benennt eine Spalte. Heute gibt es **null** solcher
#                Stellen; der Eintrag hält die leere Kategorie offen, damit ein
#                künftiges `.where(Investition.leistung_kwp > 0)` nicht falsch
#                anschlägt.
P3A_ERLAUBTE_EMPFAENGER: frozenset[str] = frozenset({"anlage", "Investition"})

# Klassifizierte Baseline (A24-3, Stand 2026-07-27): 6 Einträge, jeder eine
# Stelle, die das Muster SETZT statt es zu verletzen (ADR-002 Pflicht Nr. 2).
# Form: `Modul::Empfängername` — feiner als die Modul-Granularität des
# P5-Wächters, weil `pvgis.py` beide Sorten enthält (10 migrierte Investitions-
# Zugriffe **und** die Response-Objekte der gespeicherten Prognose). `Modul`
# allein stellt das ganze Modul frei und ist nur für den SoT selbst zulässig.
#
# Ein Lesepfad, der den effektiven Wert braucht, gehört NIE hierher, sondern auf
# `get_pv_kwp` / `get_bkw_kwp` / `get_erzeuger_kwp`.
P3A_BASELINE_AUSNAHMEN: frozenset[str] = frozenset({
    # Spaltendefinition und `__repr__` des Anlage-Modells selbst.
    "backend/models/anlage.py::self",
    # `m` ist ein Feld der PvModul-DATACLASS (`module: list[PvModul]`), kein
    # ORM-Objekt; der Aufrufer füllt es — und zwar bereits über den Helper.
    "backend/core/berechnungen/pv_verteilung.py::m",
    # `prog_modul` läuft über `prognose.module`, also über PVModulPrognose-
    # Pydantic-Objekte einer gespeicherten Prognose, nicht über Investitionen.
    # Die Schleifenvariable heißt seit A24-2 bewusst anders als die 9
    # Investitions-Schleifen derselben Datei, damit die zwei Bedeutungen
    # auseinandergehalten werden.
    "backend/api/routes/pvgis.py::prog_modul",
    # Der Export spiegelt die ROHSPALTE: `InvestitionExport` schreibt Feld für
    # Feld, und der Import liest Feld für Feld in dieselbe Spalte zurück
    # (Z. 377 ↔ Z. 640). Der effektive Wert würde beim Re-Import in eine bis
    # dahin NULL-Spalte wandern — der Export VERÄNDERTE die Daten, statt sie zu
    # spiegeln.
    "backend/api/routes/import_export/json_operations.py::inv",
    # Typgeschützter Rohspalten-Zweig: `Investition.leistung_kwp` trägt für
    # `speicher` kWh und für `wechselrichter` kW (AC) — dort ist die PV-Semantik
    # der Helper schlicht die falsche Größe (Befund-Sweep N-G). Der Erzeuger-
    # Zweig derselben Stelle läuft über `get_erzeuger_kwp`; A24-2 hat beide
    # Builder auf je EINEN kommentierten Rohzugriff gebündelt.
    "backend/services/pdf/builders/anlagendokumentation.py::inv",
    "backend/services/pdf/builders/jahresbericht.py::i",
    # A26/N106: `self` ist hier das **Pydantic-Response-Schema**
    # `InvestitionResponse`, nicht das ORM-Objekt — genau der falsch-positive
    # Fall, den die Grenze (a) der P3-a-Zeile vorhergesagt hat („jedes neue
    # Response-Schema mit einem `leistung_kwp`-Feld"). Die Stelle IST der
    # Erzeuger dieses Kennwerts: `leistung_kwp_effektiv` liest den Rohwert, um
    # ihn bei Erzeugern über `get_erzeuger_kwp` zu heilen und bei allen anderen
    # Typen (Mehrzweckfeld N-G: Speicher = kWh, WR = kW AC) unverändert
    # durchzureichen. Ein Helper-Aufruf statt des Rohzugriffs wäre hier zirkulär.
    "backend/api/routes/investitionen/crud.py::self",
    # Der SoT selbst — er IST der Spalten-Fallback und liest sie per `getattr`.
    # Als einziger Eintrag ganzes Modul statt `Modul::Empfänger`.
    P3A_SOT_MODUL,
})


def _p3a_empfaengername(knoten: ast.AST) -> str:
    """Empfänger-Name eines Zugriffs — oder eine Typmarke, wenn es keiner ist.

    `anlagen[0].leistung_kwp`, `self.anlage.leistung_kwp` und
    `lade_inv().leistung_kwp` liefern `<Subscript>` / `<Attribute>` / `<Call>`;
    diese Marken matchen keinen Allowlist-Eintrag und gelten damit als Verstoß.
    Das ist Absicht: genau diese Formen hebelten die Namensheuristik aus. Heute
    existiert keine einzige davon (gemessen) — fail-loud kostet also nichts und
    erzwingt eine Entscheidung, statt sie stillschweigend durchzulassen.
    """
    return knoten.id if isinstance(knoten, ast.Name) else f"<{type(knoten).__name__}>"


def _p3a_fundstellen() -> list[tuple[str, str, str, str]]:
    """Alle Kennwert-Lesezugriffe als `(ort, form, modul, empfänger)`.

    Zwei Formen, weil eine allein den Wächter still grün ließe:
      - `inv.leistung_kwp`               → `ast.Attribute` mit `ast.Load`
      - `getattr(inv, "leistung_kwp")`   → `ast.Call`; der Attributname steht als
        STRING da, ein Attribut-Wächter sieht ihn gar nicht.
    """
    treffer: list[tuple[str, str, str, str]] = []
    for pfad, baum in _quelldateien():
        modul = f"backend/{pfad.relative_to(_BACKEND).as_posix()}"
        for knoten in ast.walk(baum):
            if isinstance(knoten, ast.Attribute):
                # Schreibzugriffe (`ast.Store`) sind legitim — der Schreibpfad
                # läuft über `model_dump`/`setattr` in `crud.py`. Heute existiert
                # ohnehin kein einziger (gemessen).
                if knoten.attr in P3A_KENNWERT_ATTRIBUTE and isinstance(
                    knoten.ctx, ast.Load
                ):
                    treffer.append(
                        (
                            _ort(pfad, knoten),
                            "Attributzugriff",
                            modul,
                            _p3a_empfaengername(knoten.value),
                        )
                    )
            elif isinstance(knoten, ast.Call):
                funktion = knoten.func
                if not (isinstance(funktion, ast.Name) and funktion.id == "getattr"):
                    continue
                if len(knoten.args) < 2:
                    continue
                attribut = knoten.args[1]
                if not (
                    isinstance(attribut, ast.Constant)
                    and attribut.value in P3A_KENNWERT_ATTRIBUTE
                ):
                    continue
                treffer.append(
                    (
                        _ort(pfad, knoten),
                        "getattr",
                        modul,
                        _p3a_empfaengername(knoten.args[0]),
                    )
                )
    return treffer


def _p3a_verstoesse(form: str) -> list[str]:
    """Fundstellen einer Form, die weder Allowlist noch Empfänger-Regel deckt.

    Die Meldung nennt den Allowlist-Schlüssel `modul::empfaenger` mit, damit ein
    bewusst freigestellter Fall ohne Nachschlagen eingetragen werden kann.
    """
    return [
        f"  {ort} — {form} auf {empfaenger!r}  (Allowlist-Schlüssel: {modul}::{empfaenger})"
        for ort, gefundene_form, modul, empfaenger in _p3a_fundstellen()
        if gefundene_form == form
        and modul not in P3A_BASELINE_AUSNAHMEN
        and f"{modul}::{empfaenger}" not in P3A_BASELINE_AUSNAHMEN
        and empfaenger not in P3A_ERLAUBTE_EMPFAENGER
    ]


_P3A_HINWEIS = (
    "\n\nStattdessen aus backend/core/investition_kennwerte.py lesen: "
    "`get_pv_kwp(inv)` (PV-Modul), `get_bkw_kwp(inv)` (Balkonkraftwerk) oder "
    "`get_erzeuger_kwp(inv)` (Typ-Dispatcher für Σ über beide). Die Spalte allein "
    "liefert bei einer nur im `parameter`-JSON gepflegten Nennleistung still 0 — "
    "das ist die #229-Klasse (N52, N66).\n"
    "Wer bewusst die ROHSPALTE will (Export-Spiegelung) oder gar keine Investition "
    "liest (Anlage, Dataclass, Pydantic-Response), trägt sich mit Klartext-"
    "Begründung in P3A_BASELINE_AUSNAHMEN ein — Form `modul.py::empfaenger`."
)


def test_p3a_investitions_kwp_nur_ueber_den_sot_helper():
    """Kein direkter Attributzugriff auf einen Investitions-Kennwert.

    Baseline 0 seit A24-2 (47 Zugriffe im Baum: 40 auf `anlage`, 7 in der
    Allowlist — der siebte kam mit A26 dazu, dem Response-Schema, das den
    effektiven Kennwert erzeugt). Der Wächter prüft **Form, nicht Wert** und
    kann den Empfänger nicht typisieren — ein Empfänger, der `anlage` heißt,
    aber eine Investition hält, ist per Konstruktion falsch-negativ.

    Er endet an der **API-Grenze**: was der Client mit der Antwort macht, sieht
    er nicht. Diese Hälfte deckt seit A26 `frontend/scripts/check-kennwert-roh.mjs`.
    """
    verstoesse = _p3a_verstoesse("Attributzugriff")

    assert not verstoesse, (
        "Direkter Attributzugriff auf einen Investitions-Kennwert (P3-a):\n"
        + "\n".join(verstoesse)
        + _P3A_HINWEIS
    )


def test_p3a_investitions_kwp_nicht_per_getattr_umgehen():
    """Dieselbe Regel für die `getattr`-Form — sonst ist der Wächter trivial zu
    unterlaufen.

    Kein optionaler Zweig: `core/berechnungen/co2_amortisation.py:79` las
    `getattr(inv, "leistung_kwp", None) or 0` und tauchte deshalb in **keiner**
    Erhebungszahl auf — weder im Grep noch im Attribut-AST. Ohne diesen Test
    bliebe der Wächter grün, während eine Stelle unmigriert ist; genau den
    stillen Zustand schließt ADR-002 Pflicht Nr. 3 aus. Erschwerend: `getattr`
    ist die Form, die der SoT-Helper **selbst** benutzt — wer ihn kopiert, hätte
    den Wächter lautlos umgangen.

    Baseline: 3 Fundstellen, alle gedeckt — 2× Empfänger `anlage`
    (`services/snapshot/*aggregator.py`), 1× der Helper selbst.
    """
    verstoesse = _p3a_verstoesse("getattr")

    assert not verstoesse, (
        "Investitions-Kennwert per getattr gelesen — das umgeht den "
        "Attribut-Wächter (P3-a):\n" + "\n".join(verstoesse) + _P3A_HINWEIS
    )


def test_p3a_baseline_ausnahmen_sind_noch_belegt():
    """Die Baseline darf nicht über ihre Fundstellen hinaus wachsen.

    Verschwindet ein freigestellter Zugriff, muss der Eintrag mit — sonst deckt
    er später einen echten neuen Treffer mit demselben Empfängernamen (dieselbe
    Absicherung wie `test_p6_baseline_ausnahmen_sind_noch_belegt`).
    """
    belegt = set()
    for _, _, modul, empfaenger in _p3a_fundstellen():
        belegt.add(modul)
        belegt.add(f"{modul}::{empfaenger}")
    verwaist = P3A_BASELINE_AUSNAHMEN - belegt

    assert not verwaist, (
        f"Baseline-Ausnahmen ohne Fundstelle: {sorted(verwaist)}. "
        "Der Zugriff ist weg — den Eintrag aus P3A_BASELINE_AUSNAHMEN entfernen."
    )


def test_p3a_kennwert_sot_traegt_die_regel_noch():
    """Gegenprobe: der Wächter wäre wertlos, wenn der SoT entkernt würde.

    Ohne diese Prüfung wird das Gate still grün, sobald jemand aus `get_pv_kwp`
    den `parameter`-Fallback entfernt oder den Dispatcher auf `get_pv_kwp`
    verkürzt — dann gilt zwar noch „nur eine Stelle", aber nicht mehr „die
    richtige Regel", und der Wächter bewachte eine leere Regel.
    """
    quelle = (_BACKEND / "core/investition_kennwerte.py").read_text()
    baum = ast.parse(quelle)
    funktionen = {
        knoten.name: ast.unparse(knoten)
        for knoten in ast.walk(baum)
        if isinstance(knoten, (ast.FunctionDef, ast.AsyncFunctionDef))
    }

    for name in ("get_pv_kwp", "get_bkw_kwp", "get_erzeuger_kwp"):
        assert name in funktionen, (
            f"{name} existiert nicht mehr in {P3A_SOT_MODUL} — umbenannt oder "
            "verschoben? Dann diesen Wächter mitziehen, sonst prüft er nichts mehr."
        )

    # Stufe 1+2: Spalte, dann die `parameter`-Keys aus dem Kanon.
    for bestandteil, bedeutung in (
        ("'leistung_kwp'", "die Spalten-Stufe"),
        ("KWP_PARAM_KEYS", "der `parameter`-JSON-Fallback (die #229-Datenlage)"),
    ):
        assert bestandteil in funktionen["get_pv_kwp"], (
            f"{bestandteil} fehlt in get_pv_kwp — {bedeutung} ist damit weg. "
            "Ohne beide Stufen liest der SoT dieselbe halbe Wahrheit wie die "
            "Stellen, die er ersetzt hat."
        )
    kwp_keys = ast.unparse(baum)
    for kanon_bestandteil in ("LEGACY_KWP_KEY", "PARAM_PV_MODULE['LEISTUNG_KWP']"):
        assert kanon_bestandteil in kwp_keys, (
            f"KWP_PARAM_KEYS bezieht {kanon_bestandteil} nicht mehr aus dem Kanon "
            "core/investition_parameter.py — ein Literal-Schlüssel daneben wäre "
            "genau der P3-b-Verstoß, den A24-1 aufgelöst hat."
        )

    # Stufe 3: die BKW-Formel — und zwar NACH den kWp-Stufen, sonst fällt ein
    # wie ein PV-Modul gepflegtes BKW auf 0.
    for bestandteil, bedeutung in (
        ("get_pv_kwp(", "die vorgelagerten kWp-Stufen (get_bkw_kwp ⊇ get_pv_kwp)"),
        ("PARAM_BALKONKRAFTWERK['LEISTUNG_WP']", "der Wp-Zweig"),
        ("PARAM_BALKONKRAFTWERK['ANZAHL']", "die Modul-Anzahl"),
        ("ANZAHL_LESE_DEFAULT", "der Lese-Default 1 (nicht die Formular-Vorbelegung 2)"),
    ):
        assert bestandteil in funktionen["get_bkw_kwp"], (
            f"{bestandteil} fehlt in get_bkw_kwp — {bedeutung} ist damit weg. "
            "Die acht erhobenen BKW-Varianten sind genau so entstanden."
        )

    for bestandteil in ("get_bkw_kwp(", "get_pv_kwp(", "BALKONKRAFTWERK"):
        assert bestandteil in funktionen["get_erzeuger_kwp"], (
            f"{bestandteil} fehlt in get_erzeuger_kwp — der Typ-Dispatcher "
            "unterscheidet BKW und PV-Modul nicht mehr. Dann schreibt jede "
            "Read-Site ihre eigene Fallunterscheidung, und die neunte Variante "
            "der BKW-Formel entsteht."
        )


# ============================================================================
# P3-b — Literal-Schlüssel im `parameter`-JSON gegen den Kanon (A27)
# ============================================================================

# Der Kanon: `core/investition_parameter.py`. Er wird **introspektiv** gelesen,
# nicht als Liste nachgebaut — ein neuer Schlüssel in einer `PARAM_<TYP>`-Map
# und sogar eine ganz neue `PARAM_<TYP>`-Map sind damit automatisch gültig, ohne
# dass jemand diesen Wächter anfassen muss (dasselbe Prinzip wie bei P6, der
# `field_definitions` liest statt eine Feldliste zu kopieren).
P3B_KANON_MODUL = "backend/core/investition_parameter.py"


def _p3b_kanon_maps() -> dict[str, dict[str, str]]:
    """Alle `PARAM_<TYP>`-Schlüsselmaps des Kanons (ohne die `_DEFAULTS`-Maps).

    Die `_DEFAULTS`-Maps bleiben bewusst draußen: dort stehen WERTE unter den
    kanonischen Schlüsseln, nicht Schlüsselnamen. Sie mit hineinzuziehen machte
    jeden Default-Wert zu einem gültigen Schlüssel.
    """
    return {
        name: getattr(ip, name)
        for name in dir(ip)
        if name.startswith("PARAM_")
        and not name.endswith("_DEFAULTS")
        and isinstance(getattr(ip, name), dict)
    }


def _p3b_kanon() -> set[str]:
    """Alle Schlüssel, die in einem `parameter`-JSON gelesen werden dürfen.

    Zwei Quellen:
      - die Werte aller `PARAM_<TYP>`-Maps — der gültige Kanon von heute
      - die **Schlüssel** von `LEGACY_PARAM_KEYS` — dokumentierte Altnamen.
        Sie zu LESEN ist legitim (Bestandsdaten, die die v3.25.0-Migration nicht
        erwischt hat; `kwp` wird sogar aktiv gelesen). Zu SCHREIBEN sind sie
        nicht — diese Grenze zieht dieser Wächter nicht, sie steht als Prosa im
        Kanon-Modul.
    """
    schluessel: set[str] = set()
    for karte in _p3b_kanon_maps().values():
        schluessel |= set(karte.values())
    return schluessel | set(ip.LEGACY_PARAM_KEYS)


# Klassifizierte Baseline (A27, Stand 2026-07-27): **leer**. 66 Literal-Zugriffe
# im Baum, alle 66 im Kanon — daneben 75 Zugriffe in der gewünschten
# Konstanten-Form (`.get(PARAM_SPEICHER["KAPAZITAET_KWH"])`), der Sollzustand ist
# also bereits die Mehrheit. Der Wächter hält diesen Zustand, er dokumentiert
# keine Altlast.
#
# **Vorentscheidung E12, hier bewusst NICHT als Eintrag:** `services/
# infothek_migration.py` liest `stamm_*`-Schlüssel (`stamm_notizen` u. a.), die
# nicht in den Investitions-Kanon gehören — die Map dort (Z. 22-58) bildet sie
# auf (Infothek-Kategorie, Feld) ab, es sind also MIGRATIONS-QUELLSCHLÜSSEL auf
# dem Weg ins Infothek-Modell, keine lebenden Investitions-Parameter. Sie in den
# Investitions-Kanon zu ziehen vermischte zwei Domänen in einer SoT; das Modul
# ist als benannte Zweit-SoT freigestellt. Ein Eintrag ist heute trotzdem falsch:
# die Stelle liest über `params = dict(inv.parameter)`, und die **enge**
# Alias-Form unten erfasst das nicht — der Eintrag wäre von Geburt an verwaist
# und `::test_p3b_baseline_ausnahmen_sind_noch_belegt` schlüge an. Wandert die
# Stelle je in Reichweite (z. B. `params = inv.parameter or {}`), ist
# `"backend/services/infothek_migration.py"` mit genau dieser Begründung die
# dokumentierte Antwort — als MODUL-Eintrag, nicht als ein Eintrag je Schlüssel.
#
# Wer hier etwas hinzufügt, begründet im Klartext, warum der Schlüssel kein
# Investitions-Parameter ist. Ein echter Parameter gehört in den Kanon, nicht
# hierher (dort hängen Frontend-Pendant, Defaults und die Migration dran).
P3B_BASELINE_AUSNAHMEN: frozenset[str] = frozenset()


def _p3b_entpacke_or_leer(knoten: ast.AST) -> ast.AST:
    """`(x or {})` → `x`; alles andere unverändert.

    Die Form `(inv.parameter or {}).get(…)` ist im Bestand häufiger als der
    blanke Zugriff; ohne dieses Entpacken sähe der Wächter zwei Drittel der
    Stellen nicht.
    """
    if isinstance(knoten, ast.BoolOp) and isinstance(knoten.op, ast.Or):
        if len(knoten.values) == 2:
            rechts = knoten.values[1]
            if isinstance(rechts, ast.Dict) and not rechts.keys:
                return knoten.values[0]
    return knoten


def _p3b_aliase(baum: ast.Module) -> set[str]:
    """Lokale Namen, die ein `parameter`-JSON UNVERÄNDERT halten.

    **Bewusst eng (Entscheidung E11):** nur `x = inv.parameter` und
    `x = inv.parameter or {}`. Die naheliegende weite Fassung — „irgendwo
    `.parameter` im Zuweisungsausdruck" — macht auch
    `wp_agg = _wp_aggregate(wp.parameter)` zum Alias, obwohl dort ein
    ABGELEITETES Dict mit eigenen Schlüsseln entsteht. Gemessen sind das 3 von 4
    Treffern in `core/berechnungen/alternativkosten.py`: ein Wächter, der beim
    ersten Lauf zu 75 % danebenliegt, wird abgeschaltet.

    Preis der Enge, am Code gemessen und keine Fußnote: **4 identitätswahrende
    Alias-Formen bleiben unerkannt** — `params = dict(inv.parameter)`
    (`services/infothek_migration.py:195`) und dreimal
    `x = invs[0].parameter if invs else None` (`api/routes/aktueller_monat.py`,
    `api/routes/cockpit/komponenten.py`, `api/routes/cockpit/uebersicht.py`).
    Dazu kommt die Klasse „JSON als Funktionsargument" (`get_wp_strom_kwh(daten,
    wp.parameter)`, `get_felder_fuer_investition(inv.typ, inv.parameter)`), die
    ein AST-Formwächter grundsätzlich nicht verfolgt. Dieselbe bewusste Grenze
    wie die Empfänger-Namensheuristik bei P3-a und die Modellnamen-Liste bei P5.
    """
    aliase: set[str] = set()
    for knoten in ast.walk(baum):
        if not isinstance(knoten, (ast.Assign, ast.AnnAssign, ast.NamedExpr)):
            continue
        wert = getattr(knoten, "value", None)
        if wert is None:  # `x: dict` ohne Zuweisung
            continue
        entpackt = _p3b_entpacke_or_leer(wert)
        if not (isinstance(entpackt, ast.Attribute) and entpackt.attr == "parameter"):
            continue
        ziele = knoten.targets if isinstance(knoten, ast.Assign) else [knoten.target]
        for ziel in ziele:
            if isinstance(ziel, ast.Name):
                aliase.add(ziel.id)
    return aliase


def _p3b_ist_parameter_json(knoten: ast.AST, aliase: set[str]) -> bool:
    """Hält dieser Ausdruck ein `parameter`-JSON — direkt oder über einen Alias?"""
    entpackt = _p3b_entpacke_or_leer(knoten)
    if isinstance(entpackt, ast.Attribute) and entpackt.attr == "parameter":
        return True
    return isinstance(entpackt, ast.Name) and entpackt.id in aliase


def _p3b_zugriffe() -> list[tuple[str, str, str]]:
    """Alle Literal-Zugriffe auf ein `parameter`-JSON als `(ort, modul, schlüssel)`.

    Zwei Formen:
      - `…parameter.get("literal")`  — der Bestand, 66 Stellen
      - `…parameter["literal"]`      — Subscript, Lesen **und** Schreiben. Heute
        existiert keine einzige (gemessen); der Zweig ist trotzdem drin, weil er
        sonst der lautlose Ausweg wäre, sobald der Wächter jemandem im Weg steht.
    """
    treffer: list[tuple[str, str, str]] = []
    for pfad, baum in _quelldateien():
        modul = f"backend/{pfad.relative_to(_BACKEND).as_posix()}"
        aliase = _p3b_aliase(baum)
        for knoten in ast.walk(baum):
            if isinstance(knoten, ast.Subscript):
                if not _p3b_ist_parameter_json(knoten.value, aliase):
                    continue
                schluessel_knoten = knoten.slice
            elif isinstance(knoten, ast.Call):
                funktion = knoten.func
                if not (isinstance(funktion, ast.Attribute) and funktion.attr == "get"):
                    continue
                if not knoten.args:
                    continue
                if not _p3b_ist_parameter_json(funktion.value, aliase):
                    continue
                schluessel_knoten = knoten.args[0]
            else:
                continue

            if isinstance(schluessel_knoten, ast.Constant) and isinstance(
                schluessel_knoten.value, str
            ):
                treffer.append((_ort(pfad, knoten), modul, schluessel_knoten.value))
            # `.get(PARAM_SPEICHER["KAPAZITAET_KWH"])` ist die gewünschte Form —
            # dort kann kein Tippfehler still durchrutschen, der Kanon-Zugriff
            # wirft selbst. Nichts zu prüfen.
    return treffer


def test_p3b_parameter_schluessel_stehen_im_kanon():
    """Jeder Literal-Schlüssel auf einem `parameter`-JSON muss im Kanon stehen.

    Verhindert dieselbe stille Null wie P6, nur auf dem anderen JSON-Feld:
    ein Schlüssel, den kein Schreibpfad erzeugt, liefert `None`/Default, und der
    Aufrufer rechnet mit 0 weiter. Genau das waren die 7 Drift-Bugs, die
    v3.25.0 aufgeräumt hat (E-Auto V2H, Fahrleistung, Speicher-Arbitrage,
    Wallbox-Leistung … — alle „effektiv tot", keiner laut).

    Baseline 0 (A27): 66 Literal-Zugriffe in 21 Dateien, alle im Kanon.
    """
    kanon = _p3b_kanon()
    unbekannt = [
        (ort, schluessel)
        for ort, modul, schluessel in _p3b_zugriffe()
        if schluessel not in kanon
        and modul not in P3B_BASELINE_AUSNAHMEN
    ]

    assert not unbekannt, (
        "Literal-Schlüssel auf einem parameter-JSON, die nicht im Kanon "
        f"{P3B_KANON_MODUL} stehen — ein Tippfehler liefert hier still None/0 "
        "(dieselbe Klasse wie P6/N38):\n"
        + "\n".join(f"  {ort} → {schluessel!r}" for ort, schluessel in unbekannt)
        + "\n\nEntweder den Schlüssel in die passende PARAM_<TYP>-Map in "
        f"{P3B_KANON_MODUL} aufnehmen (und im Frontend-Pendant "
        "frontend/src/lib/investitionParameter.ts mitziehen) und hier die "
        "Konstante statt des Literals lesen — oder, wenn es gar kein "
        "Investitions-Parameter ist, das Modul mit Klartext-Begründung in "
        "P3B_BASELINE_AUSNAHMEN eintragen."
    )


def test_p3b_baseline_ausnahmen_sind_noch_belegt():
    """Die Baseline darf nicht über ihre Fundstellen hinaus wachsen.

    Heute leer — der Test ist damit trivial grün und trotzdem nicht überflüssig:
    er ist die Absicherung, die einen künftigen Eintrag (etwa den in
    P3B_BASELINE_AUSNAHMEN vorbereiteten E12-Fall) wieder herausdrängt, sobald
    seine Fundstelle verschwindet. Ohne ihn deckte eine verwaiste Ausnahme
    später einen echten Treffer im selben Modul.
    """
    module_mit_treffern = {modul for _, modul, _ in _p3b_zugriffe()}
    verwaist = P3B_BASELINE_AUSNAHMEN - module_mit_treffern

    assert not verwaist, (
        f"Baseline-Ausnahmen ohne Fundstelle: {sorted(verwaist)}. "
        "Der Zugriff ist weg — den Eintrag aus P3B_BASELINE_AUSNAHMEN entfernen."
    )


def test_p3b_kanon_traegt_die_regel_noch():
    """Gegenprobe: der Wächter wäre wertlos, wenn der Kanon entkernt würde.

    Die introspektive Kanon-Bildung ist bequem und genau deshalb gefährlich —
    wird eine `PARAM_<TYP>`-Map umbenannt oder verschoben, schrumpft die
    Kanon-Menge stillschweigend, und der Wächter oben schlägt plötzlich an
    Stellen an, die korrekt sind (oder, nach einer bequemen Allowlist-Runde,
    an gar nichts mehr). Deshalb hier die Anker festgenagelt.
    """
    maps = _p3b_kanon_maps()
    for erwartet in (
        "PARAM_E_AUTO",
        "PARAM_SPEICHER",
        "PARAM_WAERMEPUMPE",
        "PARAM_WALLBOX",
        "PARAM_WECHSELRICHTER",
        "PARAM_PV_MODULE",
        "PARAM_BALKONKRAFTWERK",
        "PARAM_SONSTIGES",
    ):
        assert erwartet in maps, (
            f"{erwartet} existiert nicht mehr in {P3B_KANON_MODUL} — umbenannt "
            "oder verschoben? Dann diesen Wächter mitziehen; die introspektive "
            "Kanon-Bildung merkt den Verlust sonst nicht."
        )

    kanon = _p3b_kanon()
    for schluessel, herkunft in (
        # Die A24-1-Ergänzung: ohne sie wäre P3-b gar nicht baubar gewesen.
        ("leistung_kwp", "PARAM_PV_MODULE['LEISTUNG_KWP'] (A24-1, die #229-Datenlage)"),
        # Der einzige Legacy-Key, der aktiv gelesen wird.
        (ip.LEGACY_KWP_KEY, "LEGACY_PARAM_KEYS (aktiv gelesen, s. get_pv_kwp)"),
    ):
        assert schluessel in kanon, (
            f"{schluessel!r} fehlt im Kanon — Herkunft war {herkunft}. Ohne ihn "
            "meldet der Wächter oben eine korrekte Lesestelle als Verstoß."
        )


# ============================================================================
# N115 — der Kanon und die ausgeführte v3.25.0-Migration hängen aneinander
# ============================================================================

# `LEGACY_PARAM_KEYS` ist reine Dokumentation, `KEY_MAPPING_BY_TYP` in
# `core/database.py::_migrate_investitionen_parameter_keys_v325` ist der Umbau,
# der auf jeder Bestands-DB tatsächlich gelaufen ist. Bis A27 hingen die zwei an
# nichts — und wichen bereits ab: die Migration schrieb `ladeleistung_kw →
# max_ladeleistung_kw` (Wallbox, „community_service-Drift"), was in
# `LEGACY_PARAM_KEYS` schlicht fehlte. Eine Doku-Liste, die den ausgeführten
# Umbau unvollständig wiedergibt, ist genau die Sorte Behauptung, gegen die die
# Spalte „gesichert durch" in ADR-002 gebaut wurde.
N115_MIGRATIONS_MODUL = "backend/core/database.py"
N115_MIGRATIONS_FUNKTION = "_migrate_investitionen_parameter_keys_v325"
N115_MIGRATIONS_MAP = "KEY_MAPPING_BY_TYP"

# Die Gegenrichtung ist erlaubt — der Kanon darf mehr Altnamen kennen als die
# Migration angefasst hat —, aber jeder solche Eintrag ist BENANNT, sonst wächst
# die Doku-Liste unbemerkt in eine zweite Wahrheit.
#
#   kwp  Bewusst nie migriert: die Nennleistung liegt primär in der SPALTE
#        `Investition.leistung_kwp`; ein Umschreiben des JSON-Schlüssels hätte
#        nichts geheilt und Bestandsdaten angefasst, die noch gelesen werden.
#        Stattdessen liest `core/investition_kennwerte.py::get_pv_kwp` ihn
#        aktiv weiter (#229/N66) — der einzige Legacy-Key mit Lesepfad.
N115_KANON_OHNE_MIGRATION: frozenset[str] = frozenset({ip.LEGACY_KWP_KEY})


def _n115_migrations_paare() -> dict[str, str]:
    """`{alter_key: neuer_key}` aus der v3.25.0-Migration, per AST gelesen.

    `KEY_MAPPING_BY_TYP` ist eine LOKALE Variable in der Migrationsfunktion —
    importierbar ist sie nicht. Der AST-Weg ist zugleich die Gegenprobe: wird
    die Funktion oder die Map umbenannt, schlägt dieser Helper fehl, statt eine
    leere Menge zu liefern und das Gate still grün zu färben.
    """
    quelle = (_BACKEND / "core/database.py").read_text()
    baum = ast.parse(quelle)

    funktion = next(
        (
            knoten
            for knoten in ast.walk(baum)
            if isinstance(knoten, (ast.FunctionDef, ast.AsyncFunctionDef))
            and knoten.name == N115_MIGRATIONS_FUNKTION
        ),
        None,
    )
    assert funktion is not None, (
        f"{N115_MIGRATIONS_FUNKTION} existiert nicht mehr in "
        f"{N115_MIGRATIONS_MODUL} — umbenannt oder verschoben? Dann diesen Test "
        "mitziehen, sonst prüft er ab jetzt nichts mehr (ADR-002 Pflicht Nr. 3)."
    )

    roh = next(
        (
            knoten.value
            for knoten in ast.walk(funktion)
            if isinstance(knoten, ast.Assign)
            and any(
                isinstance(ziel, ast.Name) and ziel.id == N115_MIGRATIONS_MAP
                for ziel in knoten.targets
            )
        ),
        None,
    )
    assert roh is not None, (
        f"{N115_MIGRATIONS_MAP} existiert nicht mehr in "
        f"{N115_MIGRATIONS_FUNKTION} — umbenannt oder in eine andere Struktur "
        "überführt? Dann diesen Test mitziehen."
    )

    paare: dict[str, str] = {}
    for karte in ast.literal_eval(roh).values():
        paare.update(karte)
    return paare


def test_p3b_kanon_deckt_die_v325_migration_ab():
    """Jeder Quellschlüssel der Migration steht mit demselben Ziel im Kanon.

    Gerichtet geprüft: die Doku-Liste `LEGACY_PARAM_KEYS` darf nicht hinter dem
    zurückbleiben, was auf den DBs der Nutzer tatsächlich gelaufen ist. Die
    Gegenrichtung (Kanon kennt mehr als die Migration) ist erlaubt und in
    `N115_KANON_OHNE_MIGRATION` benannt.

    Gefunden hat diese Prüfung bei ihrer Einführung genau eine Lücke:
    `ladeleistung_kw` (Wallbox) — im selben Commit geschlossen.
    """
    fehlend: list[str] = []
    abweichend: list[str] = []
    for alt_key, neu_key in sorted(_n115_migrations_paare().items()):
        if alt_key not in ip.LEGACY_PARAM_KEYS:
            fehlend.append(f"  {alt_key!r} → {neu_key!r}")
        elif ip.LEGACY_PARAM_KEYS[alt_key] != neu_key:
            abweichend.append(
                f"  {alt_key!r}: Migration → {neu_key!r}, "
                f"Kanon → {ip.LEGACY_PARAM_KEYS[alt_key]!r}"
            )

    assert not fehlend and not abweichend, (
        "LEGACY_PARAM_KEYS gibt die ausgeführte v3.25.0-Migration nicht "
        f"vollständig wieder ({N115_MIGRATIONS_MODUL}::{N115_MIGRATIONS_FUNKTION}):\n"
        + ("Fehlt im Kanon:\n" + "\n".join(fehlend) + "\n" if fehlend else "")
        + ("Anderes Ziel:\n" + "\n".join(abweichend) + "\n" if abweichend else "")
        + "\nDie Migration ist auf den DBs der Nutzer bereits gelaufen — der "
        "alte Schlüssel kann dort also noch in unmigrierten Beständen liegen. "
        "Ein Lese-Fallback ohne Kanon-Eintrag ist ein Literal ohne SoT (P3-b); "
        "ein Kanon ohne den Eintrag ist eine Doku, die den Umbau verschweigt."
    )


def test_p3b_kanon_eintraege_ohne_migration_sind_benannt():
    """Umgekehrt: jeder Legacy-Key ohne Migrations-Paar ist begründet.

    Ohne diese Richtung könnte `LEGACY_PARAM_KEYS` beliebig um Altnamen wachsen,
    die nie jemand umgeschrieben hat — die Liste sähe nach Migrations-Protokoll
    aus und wäre eine Sammlung. Der Test erzwingt die Entscheidung: entweder das
    Paar steht in der Migration, oder es steht mit Grund in
    N115_KANON_OHNE_MIGRATION.
    """
    migriert = set(_n115_migrations_paare())
    unbegruendet = set(ip.LEGACY_PARAM_KEYS) - migriert - N115_KANON_OHNE_MIGRATION
    verwaist = N115_KANON_OHNE_MIGRATION - set(ip.LEGACY_PARAM_KEYS)

    assert not unbegruendet, (
        f"Legacy-Keys ohne Migrations-Paar und ohne Begründung: "
        f"{sorted(unbegruendet)}. Entweder gehören sie in "
        f"{N115_MIGRATIONS_MAP} (dann läuft die Migration sie um) — oder mit "
        "Klartext-Begründung in N115_KANON_OHNE_MIGRATION, so wie `kwp`."
    )
    assert not verwaist, (
        f"Benannte Ausnahmen ohne Kanon-Eintrag: {sorted(verwaist)}. Der "
        "Legacy-Key ist aus LEGACY_PARAM_KEYS verschwunden — die Ausnahme aus "
        "N115_KANON_OHNE_MIGRATION mit entfernen, sonst deckt sie später einen "
        "gleichnamigen neuen Eintrag."
    )


# ══════════════════════════════════════════════════════════════════════════
# P7 — Das PV-Anlagen-Aggregat ist Eingang der Auflösung, kein Wert
# ══════════════════════════════════════════════════════════════════════════
#
# `Monatsdaten.pv_erzeugung_kwh` ist der manuell erfasste bzw. importierte
# Gesamtwert eines Monats. Er darf NUR als `aggregat_kwh` in
# `core/berechnungen/pv_verteilung.resolve_pv_je_modul` gehen (Ladepfad:
# `services/pv_monatswerte.py`) — jede PV-Zahl kommt aus der Pro-Modul-Schicht
# bzw. deren Summe (Gernot 2026-07-29).
#
# **Warum eine eigene Regel und nicht P2.** P2 sichert den kWp-Schlüssel als
# Prognose-, nicht Ertragsschlüssel; P7 sichert die Herkunft des Werts. Der
# Unterschied ist nicht akademisch: die drei Fundstellen, die diese Regel
# provoziert haben, verletzten P2 gar nicht — sie verteilten nichts, sie
# rechneten am Aggregat vorbei. `19ae5f73` (Cockpit, HA-Export) und die
# Daten-Checker-Karte lasen eine ROHE IMD-Summe und fielen bei fehlender Summe
# auf das Aggregat zurück; bei teilweise gemessenen Strings ging damit eine
# Teilsumme in Finanzen, spezifischen Ertrag, Performance-Ratio und
# SOLL/IST-Abweichung.
#
# Der Wächter prüft die **Attributform** `x.pv_erzeugung_kwh` (Lesen). Er kann
# den Empfänger nicht typisieren — und der Feldname ist mehrfach belegt
# (Connector-DTO, Import-DTO, Finanz-Dataclass, das Ergebnis-Objekt
# `PvModulWert` der Auflösung selbst). Deshalb dieselbe Mechanik wie P3-a:
# jede Fundstelle ist ein Verstoß, bis sie als `modul.py::empfänger` mit
# Klartext-Begründung klassifiziert ist. Neue Stellen fallen laut auf, statt
# still durchzulaufen.
P7_SOT_MODULE: frozenset[str] = frozenset({
    # Die Formel selbst (ADR-001) …
    "backend/core/berechnungen/pv_verteilung.py",
    # … und der EINE Ladepfad davor.
    "backend/services/pv_monatswerte.py",
})

P7_BASELINE_AUSNAHMEN: frozenset[str] = frozenset({
    # ─── Kein Monatsdaten-Empfänger: gleichnamiges Feld auf einem DTO ───
    # `PvModulWert` — das ERGEBNIS der Auflösung. Genau der Weg, den die Regel
    # vorschreibt; die Summe daraus ist die Anlagen-PV.
    "backend/api/routes/cockpit/pv_strings.py::w",
    "backend/api/routes/monatsdaten.py::w",
    # Dito, aus den Monats-Fakten (`erzeugung.pv_je_modul`) statt aus
    # `lade_pv_je_monat` direkt — dieselbe Auflösung, eine Schicht weiter oben
    # (ADR-002/P10). Trägt den String-Vergleich SOLL/IST im Jahresbericht.
    "backend/services/pdf/builders/jahresbericht.py::w",
    # Import-/Connector-/Parser-DTOs auf dem Weg IN die Datenbank. Sie tragen
    # den Wert, bevor es eine Monatsdaten-Zeile gibt — eine Auflösung wäre dort
    # gegenstandslos.
    "backend/api/routes/custom_import/preview.py::month",
    "backend/api/routes/data_import.py::monat_input",
    "backend/services/connector_mqtt_bridge.py::meters",
    "backend/services/import_parsers/base.py::self",
    # Finanz-Schicht: `FinanzZeileEingabe` (Dataclass) bzw. `FinanzMonatsZeile`.
    # Wer die Zeile FÜLLT, ist der Aufrufer — und der steht mit seinem eigenen
    # Empfänger in dieser Erhebung. `cockpit/uebersicht.py` und `ha_export.py`
    # lasen seit `19ae5f73` über `pv_monatswerte`, seit S4 (2026-07-31) über
    # `lade_monats_fakten`/`finanz_zeile_eingabe` (ADR-002/P10) — beide Wege
    # führen durch dieselbe Auflösung, nur eine Schicht weiter oben.
    "backend/services/finanz_zeilen.py::eingabe",
    "backend/core/berechnungen/finanz_aggregat.py::z",
    #
    # ─── Echte Monatsdaten-Leser, bewusst freigestellt ───
    # Der Klassifikator `klassifiziere_pv_monat` gehört zur Auflösungs-SoT und
    # NIMMT das Aggregat als Argument (`aggregat_kwh`) — dieselbe Rolle wie
    # `resolve_pv_je_modul`, nur auf der Diagnose-Seite.
    "backend/services/daten_checker/energieprofil.py::md",
    # Das Backup spiegelt die ROHSPALTE Feld für Feld; der Import schreibt sie
    # zurück. Ein aufgelöster Wert würde beim Re-Import in eine bis dahin leere
    # Spalte wandern — der Export VERÄNDERTE die Daten (dieselbe Begründung wie
    # P3A_BASELINE_AUSNAHMEN für `json_operations.py::inv`).
    "backend/api/routes/import_export/json_operations.py::md",
    # Vier Rollen in einer Datei, alle vier gedeckt (Granularität ist
    # `modul::empfänger`, feiner geht die Allowlist nicht):
    #   :446 — Eingang von `resolve_pv_je_modul`. Die Regel selbst.
    #   :500 — Legacy-Erkennung: die Meldung handelt VOM Feld („Aggregat
    #          gepflegt, aber keine Pro-Modul-Werte") — ein aufgelöster Wert
    #          beantwortete die Frage nicht mehr.
    #   :718/:863 — das Legacy-Trio (`direktverbrauch_kwh`/`eigenverbrauch_kwh`)
    #          wird aus dem MANUELL eingetragenen Aggregat fortgeschrieben.
    #          Die Felder sind deprecated (CLAUDE.md Prinzip 3); sie hier auf
    #          die Auflösung umzustellen hieße, ein totes Feld neu zu beleben.
    "backend/api/routes/monatsdaten.py::md",
    #
    # Gestrichen mit dem S3-Umbau (2026-07-31): `cockpit/social.py::md` war als
    # N110 freigestellt, weil der Endpoint keinen Konsumenten hat — mit der
    # Auflage „wird der Text angeschlossen, MUSS die Stelle auf den SoT". Die
    # Sicht liest die Monatszeile jetzt über `lade_monats_fakten` (ADR-002/P10);
    # der Rohzugriff existiert nicht mehr, die Zeile ist damit gegenstandslos.
})


def _p7_fundstellen() -> list[tuple[str, str, str]]:
    """Alle Lesezugriffe `x.pv_erzeugung_kwh` als `(ort, modul, empfänger)`."""
    treffer: list[tuple[str, str, str]] = []
    for pfad, baum in _quelldateien():
        modul = f"backend/{pfad.relative_to(_BACKEND).as_posix()}"
        for knoten in ast.walk(baum):
            if not isinstance(knoten, ast.Attribute):
                continue
            if knoten.attr != "pv_erzeugung_kwh" or not isinstance(knoten.ctx, ast.Load):
                continue
            treffer.append((_ort(pfad, knoten), modul, _p3a_empfaengername(knoten.value)))
    return treffer


def _p7_verstoesse() -> list[str]:
    return [
        f"  {ort} — Lesezugriff auf {empfaenger!r}  (Allowlist-Schlüssel: {modul}::{empfaenger})"
        for ort, modul, empfaenger in _p7_fundstellen()
        if modul not in P7_SOT_MODULE
        and f"{modul}::{empfaenger}" not in P7_BASELINE_AUSNAHMEN
    ]


def test_p7_pv_aggregat_nur_als_eingang_der_aufloesung():
    """Das PV-Anlagen-Aggregat wird nirgends direkt verrechnet.

    Baseline 0 (26 Zugriffe im Baum, 3 in den SoT-Modulen, 12 klassifizierte
    Allowlist-Schlüssel — nachgezählt beim S3-Umbau 2026-07-31, die Zahlen
    standen auf einem älteren Stand).
    **Grenzen, beide gemessen und keine Fußnote:** (a) kein Typwissen — ein
    Empfänger, der wie ein DTO heißt, aber eine Monatsdaten-Zeile hält, ist
    falsch-negativ per Konstruktion (dieselbe Grenze wie P3-a); (b) nur die
    Attributform — ein `row["pv_erzeugung_kwh"]` auf einem Dict wäre
    P6-Territorium und ist heute nirgends im Baum.
    """
    verstoesse = _p7_verstoesse()

    assert not verstoesse, (
        "Direkter Lesezugriff auf das PV-Anlagen-Aggregat (P7):\n"
        + "\n".join(verstoesse)
        + "\n\nStattdessen über `backend/services/pv_monatswerte.py` laden: "
        "`lade_pv_je_monat` (Pro-Modul-Sicht) bzw. `pv_summe_je_monat` "
        "(Anlagensumme, `None` bei Unvollständigkeit). Das Aggregat füllt nur "
        "die Lücken der Module OHNE eigenen Wert — direkt gelesen ist es "
        "entweder eine Teilsumme oder es überschreibt Messungen.\n"
        "Wer bewusst die Rohspalte braucht (Export-Spiegelung, Diagnose ÜBER "
        "das Feld) oder gar keine Monatsdaten-Zeile liest (Import-DTO, "
        "Connector-DTO, `PvModulWert`), trägt sich mit Klartext-Begründung in "
        "P7_BASELINE_AUSNAHMEN ein — Form `modul.py::empfaenger`."
    )


def test_p7_baseline_ausnahmen_sind_noch_belegt():
    """Keine verwaiste Ausnahme — sonst deckt sie später einen echten Treffer.

    Dieselbe Pflicht wie bei P3-a/P5/P6 (ADR-002 Pflicht Nr. 2): eine Allowlist,
    die nicht mitschrumpft, wird zur Sammlung und der Wächter zur Fassade.
    """
    vorhanden = {f"{modul}::{empfaenger}" for _, modul, empfaenger in _p7_fundstellen()}
    verwaist = P7_BASELINE_AUSNAHMEN - vorhanden
    verwaiste_module = P7_SOT_MODULE - {modul for _, modul, _ in _p7_fundstellen()}

    assert not verwaist, (
        f"P7-Ausnahmen ohne Fundstelle: {sorted(verwaist)} — die Stelle ist weg "
        "oder migriert; Eintrag streichen."
    )
    assert not verwaiste_module, (
        f"P7-SoT-Module ohne Fundstelle: {sorted(verwaiste_module)} — liest der "
        "Ladepfad das Aggregat nicht mehr, ist die Regel gegenstandslos "
        "geworden oder der SoT ist umgezogen."
    )


# ============================================================================
# P8 — Tarif-Werte tragen den Stichtag ihres Monats
# ============================================================================
#
# `lade_tarife_fuer_anlage(db, anlage_id)` ohne `target_date` liefert den HEUTE
# gültigen Tarif. Für die Sicht nach vorn (ROI, Prognose, „aktueller Tarif",
# Feld-/Spaltenstruktur nach Vertragsart) ist das richtig — für jeden Wert, der
# einen vergangenen Monat beschreibt, ist es falsch: eine Preiserhöhung schreibt
# dann die gesamte Historie um.
#
# Die Klasse ist teuer geworden. Sie kostete den Jahresbericht-Drift (#326,
# ~174 € bei vier Tibber-Jahrestarifen), danach dieselbe Form in `aussichten`,
# `ha_export`, `cockpit/uebersicht`, `aktueller_monat`, `social`, allen vier
# Komponenten-Dashboards und als Handquery in `monatsdaten.py`. Jeder Fund wurde
# einzeln geheilt, jeder Fix erzeugte den nächsten (Forum simon42 #89667/60).
#
# Zweite Form derselben Sache: `FinanzZeileEingabe` ohne `monatsdaten`. Der
# Builder setzt den abgerechneten Flex-Ø des Monats VOR den Stammdaten-Tarif
# (`resolve_netzbezug_preis_cent`) — wer die Zeile nicht durchreicht, verliert
# den Override STILL. So rechnete Cockpit/Tag mit dem Referenzpreis, während
# Monat und Jahr den Ø nahmen: Σ Tage ≠ Monat.

# Aufrufe, die bewusst den HEUTIGEN Tarif brauchen. Wer hier etwas hinzufügt,
# begründet im Klartext, warum die Stelle NICHTS über einen vergangenen Monat
# aussagt. Ein Wert, der in einer Monats- oder Historien-Summe landet, gehört
# nicht hierher, sondern auf den Stichtag.
#
#   strompreise.py            — Endpoint `/aktuell/{anlage_id}`: „aktuell" IST
#                               die Frage; ein Stichtag wäre sinnlos.
#   datenquellen.py           — entscheidet, ob die Preis-Felder angeboten
#                               werden (Vertragsart heute). Konfigurations-
#                               Sicht, kein Messwert.
#   import_export/csv_operations.py
#                             — Spaltenstruktur von Vorlage und Export nach
#                               heutiger Vertragsart. Der Zahlenwert je Zeile
#                               kommt aus den Monatsdaten, nicht von hier.
#   investitionen/crud.py     — ROI-/Wirtschaftlichkeits-Prognose NACH VORN.
#   investitionen/dashboards.py
#                             — Query-Param-Default + Fallback der
#                               `_gewichteter_monatspreis`-Mittelung; die
#                               historischen Beträge laufen über den Helper.
#   ha_export.py              — heutiger WP-Tarif als Fallback des
#                               Perioden-Mappings und für die nach vorn
#                               gerichteten Sensor-Werte.
#   cockpit/uebersicht.py     — Anzeige des aktuellen Tarifs + Komponenten-
#                               Kennwerte; alle Monats-Summen laufen seit S4
#                               über `fakt.tarif` bzw. `baue_finanz_zeile`,
#                               beide mit dem Monats-Stichtag (ADR-002/P10).
#   aussichten.py             — Hochrechnung + ausgewiesener Tarif der
#                               Response; die Historie läuft über
#                               `_tarife_fuer_stichtag`.
P8_BASELINE_AUSNAHMEN: frozenset[str] = frozenset({
    "backend/api/routes/strompreise.py",
    "backend/api/routes/datenquellen.py",
    "backend/api/routes/import_export/csv_operations.py",
    "backend/api/routes/investitionen/crud.py",
    "backend/api/routes/investitionen/dashboards.py",
    "backend/api/routes/ha_export.py",
    "backend/api/routes/cockpit/uebersicht.py",
    "backend/api/routes/aussichten.py",
})

_P8_TARIF_LADER = "lade_tarife_fuer_anlage"
_P8_EINGABE = "FinanzZeileEingabe"


def _p8_lader_ohne_stichtag() -> list[str]:
    """Alle `lade_tarife_fuer_anlage`-Aufrufe ohne Stichtag außerhalb der Baseline.

    Der Stichtag darf als Keyword (`target_date=`) oder als dritte Position
    stehen — `speicher_wirtschaftlichkeit.py` nutzt die positionale Form.
    """
    treffer: list[str] = []
    for pfad, baum in _quelldateien():
        modul = f"backend/{pfad.relative_to(_BACKEND).as_posix()}"
        if modul in P8_BASELINE_AUSNAHMEN:
            continue
        for knoten in ast.walk(baum):
            if not isinstance(knoten, ast.Call):
                continue
            name = getattr(knoten.func, "id", None) or getattr(knoten.func, "attr", None)
            if name != _P8_TARIF_LADER:
                continue
            hat_keyword = any(kw.arg == "target_date" for kw in knoten.keywords)
            hat_positional = len(knoten.args) >= 3
            if not (hat_keyword or hat_positional):
                treffer.append(_ort(pfad, knoten))
    return treffer


def _p8_eingaben_ohne_monatsdaten() -> list[str]:
    """Alle `FinanzZeileEingabe(...)` ohne `monatsdaten=`."""
    treffer: list[str] = []
    for pfad, baum in _quelldateien():
        for knoten in ast.walk(baum):
            if not isinstance(knoten, ast.Call):
                continue
            name = getattr(knoten.func, "id", None) or getattr(knoten.func, "attr", None)
            if name != _P8_EINGABE:
                continue
            if not any(kw.arg == "monatsdaten" for kw in knoten.keywords):
                treffer.append(_ort(pfad, knoten))
    return treffer


def test_p8_tarif_wird_mit_dem_stichtag_des_monats_geladen():
    offen = _p8_lader_ohne_stichtag()

    assert offen == [], (
        f"{len(offen)} Tarif-Ladevorgang/-vorgänge ohne Stichtag: {offen}\n"
        "`lade_tarife_fuer_anlage(db, anlage_id)` liefert den HEUTE gültigen "
        "Tarif. Jeder Wert, der einen vergangenen Monat beschreibt, braucht "
        "`target_date=date(jahr, monat, 1)` — sonst rechnet eine Preiserhöhung "
        "die Historie um (#326: ~174 € im Jahresbericht).\n"
        "Wer bewusst den heutigen Tarif braucht (Prognose, „aktueller Tarif“, "
        "Feld-/Spaltenstruktur), trägt sich mit Klartext-Begründung in "
        "P8_BASELINE_AUSNAHMEN ein."
    )


def test_p8_finanz_zeile_bekommt_die_monatsdaten_zeile():
    offen = _p8_eingaben_ohne_monatsdaten()

    assert offen == [], (
        f"{len(offen)} `FinanzZeileEingabe` ohne `monatsdaten=`: {offen}\n"
        "Der Builder setzt den abgerechneten Monats-Ø eines dynamischen Tarifs "
        "VOR den Stammdaten-Arbeitspreis. Ohne die Zeile fällt dieser Override "
        "STILL weg — so nannten Cockpit/Tag und Cockpit/Monat verschiedene "
        "Preise für denselben Zeitraum. `monatsdaten=None` ist erlaubt, aber "
        "explizit hinzuschreiben."
    )


def test_p8_baseline_ausnahmen_sind_noch_belegt():
    """Keine verwaiste Ausnahme — dieselbe Pflicht wie bei P3-a/P5/P6/P7."""
    module_mit_lader: set[str] = set()
    for pfad, baum in _quelldateien():
        for knoten in ast.walk(baum):
            if isinstance(knoten, ast.Call) and (
                getattr(knoten.func, "id", None) or getattr(knoten.func, "attr", None)
            ) == _P8_TARIF_LADER:
                module_mit_lader.add(f"backend/{pfad.relative_to(_BACKEND).as_posix()}")

    verwaist = P8_BASELINE_AUSNAHMEN - module_mit_lader

    assert not verwaist, (
        f"P8-Ausnahmen ohne Fundstelle: {sorted(verwaist)} — die Stelle lädt "
        "keine Tarife mehr; Eintrag streichen."
    )


# ============================================================================
# P9 — ein Energiefluss trägt genau einmal zum Finanz-Netto bei
# ============================================================================
#
# Die Finanz-Zeile hat zwei BKW-Eingänge, die sich BEDINGT überlappen:
# `pv_erzeugung_kwh` (Erzeugung hinter dem Hauszähler — Module UND BKW) und
# `bkw_eigenverbrauch_kwh`. Wessen BKW die Erzeugung mitschreibt, dessen
# Eigenverbrauch steckt bereits in der Ableitung aus dem ersten Eingang; der
# zweite darf dann nur noch 0 tragen. Wer die Entscheidung selbst trifft,
# trifft sie irgendwann anders als die Nachbar-Sicht — genau so standen vier
# Read-Sites mit vier verschiedenen Kombinationen im Baum (#326-Inventur:
# Aussichten zählten doppelt, Cockpit und PDF verloren die Datenlücken-Zeile,
# der HA-Export trug sie nur im ROI-Pfad und dort mit statischem Preis).
#
# Der Wächter greift auf der SCHREIB-Seite: jeder Wert, der als
# `bkw_eigenverbrauch_kwh=` in eine Finanz-Zeile geht, muss sichtbar aus
# `bkw_finanz_beitrag` stammen. Er fängt damit auch eine fünfte Sicht, die es
# heute noch nicht gibt.
_P9_ZEILEN_KONSTRUKTOREN = ("FinanzZeileEingabe", "FinanzMonatsZeile")
_P9_FELD = "bkw_eigenverbrauch_kwh"
# Belege im Wert-Ausdruck, die den Helper nachweisen. `rest_ev` ist die
# Namenskonvention der vier Faltungen (`bkw_rest_ev_by_ym` & Co.),
# `bkw_finanz_beitrag` der direkte Aufruf.
_P9_HELFER_BELEGE = ("bkw_finanz_beitrag", "rest_ev", "rest_eigenverbrauch")
# Der Builder selbst reicht den bereits entschiedenen Wert nur durch.
P9_DURCHREICHER: frozenset[str] = frozenset({
    "backend/services/finanz_zeilen.py",
})


def _p9_roh_uebergebene_bkw_werte() -> list[str]:
    """Alle `bkw_eigenverbrauch_kwh=`-Argumente ohne Helper-Beleg im Ausdruck."""
    treffer: list[str] = []
    for pfad, baum in _quelldateien():
        modul = f"backend/{pfad.relative_to(_BACKEND).as_posix()}"
        if modul in P9_DURCHREICHER:
            continue
        quelltext = pfad.read_text(errors="ignore")
        for knoten in ast.walk(baum):
            if not isinstance(knoten, ast.Call):
                continue
            name = getattr(knoten.func, "id", None) or getattr(knoten.func, "attr", None)
            if name not in _P9_ZEILEN_KONSTRUKTOREN:
                continue
            for kw in knoten.keywords:
                if kw.arg != _P9_FELD:
                    continue
                ausdruck = ast.get_source_segment(quelltext, kw.value) or ""
                if not any(beleg in ausdruck for beleg in _P9_HELFER_BELEGE):
                    treffer.append(f"{_ort(pfad, kw.value)} → {ausdruck}")
    return treffer


def test_p9_bkw_eigenverbrauch_kommt_aus_dem_helper():
    offen = _p9_roh_uebergebene_bkw_werte()

    assert offen == [], (
        f"{len(offen)} roh übergebene BKW-Eigenverbrauchswerte: {offen}\n"
        "`bkw_eigenverbrauch_kwh` der Finanz-Zeile ist KEIN Zusatzposten, "
        "sondern der Ersatzträger für BKW-Monate OHNE erfasste Erzeugung. "
        "Wer den gemessenen Eigenverbrauch roh übergibt, zählt ihn bei jedem "
        "BKW mit Erzeugung doppelt — er steckt dann schon in der Ableitung aus "
        "`pv_erzeugung_kwh`. Die Aufteilung entscheidet `bkw_finanz_beitrag` "
        "je (BKW, Monat)."
    )


def test_p9_durchreicher_sind_noch_belegt():
    """Keine verwaiste Ausnahme — dieselbe Pflicht wie bei P3-a/P5/P6/P7/P8."""
    module_mit_feld: set[str] = set()
    for pfad, baum in _quelldateien():
        for knoten in ast.walk(baum):
            if isinstance(knoten, ast.Call) and any(
                kw.arg == _P9_FELD for kw in knoten.keywords
            ):
                module_mit_feld.add(f"backend/{pfad.relative_to(_BACKEND).as_posix()}")

    verwaist = P9_DURCHREICHER - module_mit_feld

    assert not verwaist, (
        f"P9-Durchreicher ohne Fundstelle: {sorted(verwaist)} — die Stelle "
        "baut keine Finanz-Zeile mehr; Eintrag streichen."
    )
