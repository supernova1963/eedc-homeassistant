"""Konformitäts-Wächter gegen drei der sechs Wurzelmuster (A14/A17).

Hintergrund: Befund-Sweep `docs/drafts/BEFUND-SWEEP-WURZELMUSTER.md`. Elf
Commits der v4.0.1-Runde haben Fundstellen einzeln geheilt, jeder Fix erzeugte
den nächsten Fund. Diese Datei macht drei der Muster maschinell prüfbar, damit
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
       `Monatsdaten.verbrauch_daten` gegen die Feld-SoT `core/field_definitions`.

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
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Iterator

from backend.core import field_definitions as fd

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


# Klassifizierte Baseline (A14, Stand 2026-07-26): Schlüssel, die bewusst NICHT
# in `field_definitions` stehen, weil sie keine Messfelder sind. Beide sind
# geprüft und dokumentiert — kein Bug, keine Nachziehschuld.
#
#   sonstige_positionen  — LISTE von Sonderposten-Dicts, kein Skalar-Feld.
#                          `field_definitions` beschreibt Eingabefelder mit
#                          Einheit/Label; eine Positionsliste hat beides nicht.
#                          Gelesen in api/routes/monatsabschluss/views.py:540.
#   sonderkosten_notiz   — FREITEXT zur Sonderkosten-Zeile, kein Messwert.
#                          Gelesen in utils/sonstige_positionen.py:76.
#
# Wer hier etwas hinzufügt, dokumentiert im Klartext WARUM der Schlüssel kein
# Feld ist. Ein neues Messfeld gehört nach `field_definitions`, nicht hierher
# (dort hängen Wizard, CSV-Template, Import-Mapping und Hilfetexte dran).
P6_BASELINE_AUSNAHMEN: frozenset[str] = frozenset(
    {"sonstige_positionen", "sonderkosten_notiz"}
)


def _nennt_verbrauch_daten(knoten: ast.AST) -> bool:
    """Greift der Ausdruck auf ein `verbrauch_daten`-Feld zu?

    Erfasst die im Bestand vorkommenden Formen — `imd.verbrauch_daten.get(...)`,
    `(imd.verbrauch_daten or {}).get(...)` und die lokale Variable
    `verbrauch_daten.get(...)` — indem der Teilbaum vor dem `.get` nach dem
    Namen durchsucht wird, statt eine feste Aufrufform zu erwarten.
    """
    for teil in ast.walk(knoten):
        if isinstance(teil, ast.Attribute) and teil.attr == "verbrauch_daten":
            return True
        if isinstance(teil, ast.Name) and teil.id == "verbrauch_daten":
            return True
    return False


def _verbrauch_daten_zugriffe() -> list[tuple[str, str]]:
    """Alle `verbrauch_daten…get("literal")`-Zugriffe als `(ort, schlüssel)`."""
    treffer: list[tuple[str, str]] = []
    for pfad, baum in _quelldateien():
        for knoten in ast.walk(baum):
            if not isinstance(knoten, ast.Call):
                continue
            funktion = knoten.func
            if not (isinstance(funktion, ast.Attribute) and funktion.attr == "get"):
                continue
            if not _nennt_verbrauch_daten(funktion.value):
                continue
            if not knoten.args:
                continue
            erstes = knoten.args[0]
            if not (isinstance(erstes, ast.Constant) and isinstance(erstes.value, str)):
                # `.get(KONSTANTE)` ist die gewünschte Form — nichts zu prüfen.
                continue
            treffer.append((_ort(pfad, knoten), erstes.value))
    return treffer


def test_p6_verbrauch_daten_schluessel_stehen_in_der_feld_sot():
    """Jeder Literal-Schlüssel auf `verbrauch_daten` muss ein bekanntes Feld sein.

    Verhindert den N38-/N59-Mechanismus: falscher Schlüssel → still `0` → `0`
    liest sich als „keine Daten" → der Fehler fällt jahrelang nicht auf.
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
