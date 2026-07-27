"""Konformitäts-Wächter gegen vier der sechs Wurzelmuster (A14/A17/A24).

Hintergrund: Befund-Sweep `docs/drafts/BEFUND-SWEEP-WURZELMUSTER.md`. Elf
Commits der v4.0.1-Runde haben Fundstellen einzeln geheilt, jeder Fix erzeugte
den nächsten Fund. Diese Datei macht vier der Muster maschinell prüfbar, damit
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

  P3-a — Investitions-Kennwerte nur über den SoT-Helper (A24-3, die
       **#229-Klasse**). Die Nennleistung liegt je nach Herkunft in der Spalte
       `Investition.leistung_kwp` **oder** im `parameter`-JSON; wer nur die
       Spalte liest, sieht bei param-gepflegten Modulen still 0. Daraus sind N52
       (14,0 statt 10,0 kWp in der Live-Gesamtleistung), N66 (Falschmeldung des
       Daten-Checkers) und ein HTTP 400 in der PVGIS-Prognose entstanden — jedes
       einzeln geheilt, jedes Mal ohne Wächter, jedes Mal entstand die nächste
       Kopie. SoT ist `core/investition_kennwerte.py`.
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

    Baseline 0 seit A24-2 (46 Zugriffe im Baum: 40 auf `anlage`, 6 in der
    Allowlist). Der Wächter prüft **Form, nicht Wert** und kann den Empfänger
    nicht typisieren — ein Empfänger, der `anlage` heißt, aber eine Investition
    hält, ist per Konstruktion falsch-negativ.
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
