"""SoT-Helper für Investitions-Kennwerte — die Nennleistung in kWp und die
Speicher-Kapazität in kWh.

Regel ADR-002/P3-a: die Nennleistung einer Investition wird **nur** über diese
Helper gelesen, nie als direkter Attributzugriff `inv.leistung_kwp` und nie als
Literal-Schlüssel im `parameter`-JSON. Grund ist die #229-Klasse: die kWp liegt
je nach Herkunft in der Spalte `Investition.leistung_kwp` **oder** im
`parameter`-JSON (Bestands-/Importdaten). Wer nur eine der beiden Quellen liest,
sieht bei der anderen still 0 — daraus sind N52, N66 und die Falschmeldung des
Daten-Checkers entstanden.

**Warum `core/` und nicht neben `get_pv_kwp` in `services/pv_orientation.py`:**
`core/berechnungen/spez_ertrag.py` und `core/berechnungen/co2_amortisation.py`
brauchen diese Helper, und laut ADR-001 sind `services/` und `api/` Konsumenten
von `core/`, nie umgekehrt. `core/` importiert bereits `investition_parameter`
(Kanon der `parameter`-Schlüssel) und `models/investition` (Typ-Enum, s.
`co2_amortisation.py`) — die Importrichtung ist etabliert.
`services/pv_orientation.py` **re-exportiert** `get_pv_kwp`, damit die
bestehenden Importeure unberührt bleiben; es gibt genau EINE Implementierung.

**Kanon der gelesenen Schlüssel** (`core/investition_parameter.py`):
`LEGACY_KWP_KEY` (= `kwp`, Legacy, aber aktiv gelesen) und
`PARAM_PV_MODULE["LEISTUNG_KWP"]` (= `leistung_kwp`, namensgleich mit der
Spalte und mit dem Export-Feld). Kein Schreibpfad erzeugt einen der beiden —
Formular und Setup-Wizard schreiben die Spalte.
"""

from typing import Any, Final, Optional

from backend.core.investition_parameter import (
    LEGACY_KWP_KEY,
    PARAM_BALKONKRAFTWERK,
    PARAM_PV_MODULE,
    PARAM_SPEICHER,
)
from backend.models.investition import InvestitionTyp

# Lese-Reihenfolge im `parameter`-JSON: erst der Legacy-Key `kwp` (so liegen
# die Bestandsdaten vor, die die Migration nie angefasst hat), dann der
# kanonische `leistung_kwp`.
KWP_PARAM_KEYS: Final[tuple[str, ...]] = (
    LEGACY_KWP_KEY,
    PARAM_PV_MODULE["LEISTUNG_KWP"],
)

# Lese-Default für die Modul-Anzahl eines Balkonkraftwerks. Bewusst 1 und
# NICHT die 2 aus `PARAM_BALKONKRAFTWERK_DEFAULTS` — die ist die Vorbelegung
# des Eingabeformulars. Wer `anzahl` nie gepflegt hat, bekäme sonst still die
# doppelte Leistung ausgewiesen (derselbe Fehlertyp wie ein 35°-Neigungs-
# Default, der „fehlt" nicht von „gepflegt" unterscheiden kann).
ANZAHL_LESE_DEFAULT: Final[int] = 1


def get_pv_kwp(inv: Any) -> float:
    """Leistung in kWp. Priorität: Top-Level-Spalte → parameter.kwp →
    parameter.leistung_kwp → 0.

    Die drei Konventionen sind historisch (Befund-Sweep §4.1): die Spalte ist
    SoT, `kwp` ist der Legacy-Key dieses Helpers, `leistung_kwp` der des
    Verteilungs-Helpers `utils.investition_value.get_inv_value`. Dass beide
    Helper verschiedene JSON-Keys lasen, war der Nährboden für N59 — deshalb
    liest dieser hier jetzt BEIDE. `get_pv_kwp ⊇ get_inv_value("leistung_kwp")`:
    wer eine kWp gepflegt hat, wird von beiden Wegen gefunden.
    """
    direct = getattr(inv, "leistung_kwp", None)
    # 0-Semantik (N-C) — bewusste, hier begründete Ausnahme von der Projektregel
    # „0-Werte mit `is not None` prüfen": eine Nennleistung von exakt 0 ist kein
    # Messwert, sondern „nicht gepflegt". Der Durchfall auf das `parameter`-JSON
    # kann deshalb nur gewinnen — er ersetzt eine 0 durch eine echte Zahl oder
    # liefert am Ende dieselbe 0. Mit `is not None` verlöre die #229-Datenlage
    # (Spalte 0, kWp nur im JSON) ihren einzigen brauchbaren Wert, und die
    # Zusicherung `get_pv_kwp ⊇ get_inv_value("leistung_kwp")` bräche.
    # `utils/investition_value.get_inv_value` zieht für dieses eine Feld nach.
    if direct:
        return float(direct)
    params = getattr(inv, "parameter", None) or {}
    for key in KWP_PARAM_KEYS:
        try:
            wert = float(params.get(key) or 0)
        except (TypeError, ValueError):
            continue
        if wert:
            return wert
    return 0.0


def get_bkw_kwp(inv: Any) -> float:
    """Nennleistung eines Balkonkraftwerks in kWp.

    Priorität: Spalte `leistung_kwp` → parameter["kwp"] / ["leistung_kwp"]
             → parameter["leistung_wp"] × parameter["anzahl"] / 1000 → 0.0

    Die `parameter`-kWp-Stufe steht **vor** dem `leistung_wp`-Zweig, damit
    `get_bkw_kwp ⊇ get_pv_kwp` gilt: ein BKW, das versehentlich wie ein
    PV-Modul gepflegt wurde, fällt sonst auf 0.

    `anzahl` fehlt ⇒ 1 (`ANZAHL_LESE_DEFAULT`), nicht die Formular-Vorbelegung 2.
    """
    kwp = get_pv_kwp(inv)
    if kwp:
        return kwp
    params = getattr(inv, "parameter", None) or {}
    try:
        leistung_wp = float(params.get(PARAM_BALKONKRAFTWERK["LEISTUNG_WP"]) or 0)
        anzahl = float(
            params.get(PARAM_BALKONKRAFTWERK["ANZAHL"]) or ANZAHL_LESE_DEFAULT
        )
    except (TypeError, ValueError):
        return 0.0
    if not leistung_wp:
        return 0.0
    return leistung_wp * anzahl / 1000


def get_erzeuger_kwp(inv: Any) -> float:
    """Nennleistung eines PV-Erzeugers in kWp — Typ-Dispatcher.

    `balkonkraftwerk` → `get_bkw_kwp`, alles andere → `get_pv_kwp`.

    Existiert, weil die Σ(PV-Module + BKW)-Bildung an vielen Read-Sites steht.
    Ohne Dispatcher schreibt jede davon wieder ihre eigene
    `if typ == "balkonkraftwerk"`-Fallunterscheidung — genau daraus sind die
    acht erhobenen Varianten der BKW-Formel entstanden (Befund-Sweep §4.1).
    Der Dispatcher ist der Ort, an dem keine neunte mehr entstehen kann.

    Achtung: NUR für Erzeuger-Typen sinnvoll. `Investition.leistung_kwp` trägt
    für `speicher` kWh und für `wechselrichter` kW (AC) — dort ist die
    PV-Semantik dieser Helper falsch (s. Kanon-Kommentar in
    `investition_parameter.py`). Der Aufrufer filtert die Typen.
    """
    if getattr(inv, "typ", None) == InvestitionTyp.BALKONKRAFTWERK.value:
        return get_bkw_kwp(inv)
    return get_pv_kwp(inv)


def get_wr_grenze_kw(inv: Any) -> Optional[float]:
    """AC-Grenze des Wechselrichters in kW — oder `None`, wenn keine gepflegt ist.

    `None` heißt „nicht begrenzen", **nicht** „0". Ein Default wäre hier die
    Klasse, gegen die ADR-002 geschrieben ist: er machte aus „nicht gepflegt"
    eine Zahl, die wie eine Messung aussieht, und würde still Ertrag wegkappen.

    Heute nur für `balkonkraftwerk` gepflegt (#347): dort ist Überbelegung der
    Normalfall — 3 × 420 Wp an einem 600-W-Wechselrichter. Für PV-Module
    existiert dieselbe Physik (#354), aber noch kein Feld; sobald es eines gibt,
    kommt der Zweig hierher und nicht an die Aufrufstelle.

    Die Grenze wirkt **stündlich** (siehe `services/prognose_kanon.py`), nicht
    als kWp-Deckel: ein 600-W-Wechselrichter begrenzt die Mittagsspitze, nicht
    den Morgen. Wer die kWp deckelte, kürzte die Randstunden mit — bei starker
    Überbelegung deutlich daneben.
    """
    if getattr(inv, "typ", None) != InvestitionTyp.BALKONKRAFTWERK.value:
        return None
    params = getattr(inv, "parameter", None) or {}
    roh = params.get(PARAM_BALKONKRAFTWERK["WECHSELRICHTER_LEISTUNG_W"])
    if roh is None:
        return None
    try:
        watt = float(roh)
    except (TypeError, ValueError):
        return None
    return watt / 1000 if watt > 0 else None


def get_speicher_kapazitaet_kwh(inv: Any) -> Optional[float]:
    """**BRUTTO**-Kapazität eines Speichers in kWh — oder `None`, wenn keine
    gepflegt ist.

    **Brutto oder netto — die Verwechslung ist der Anlass dieses Helpers.**
    Ein Speicher trägt ZWEI Kapazitäten, beide im Kanon
    (`core/investition_parameter.py::PARAM_SPEICHER`) und beide im Formular
    (`SpeicherFelder.tsx`):

    * **brutto** = `kapazitaet_kwh` — die Nennkapazität des Herstellers. Das ist
      der Wert, den dieser Helper liefert, und die Bezugsgröße für **alles**,
      was im Baum „Kapazität" heißt: Vollzyklen (`core/berechnungen/speicher.py::
      vollzyklen`, dort begründet), Speicher-ROI, graue Last, Community-Datensatz,
      HA-Sensoren, PDF-Berichte.
    * **netto** = `nutzbare_kapazitaet_kwh` — der tatsächlich nutzbare SoC-Hub
      (Entladetiefe). **Optional und bei den meisten Anlagen nicht gepflegt.**
      Er hat heute genau eine Verwendung: das η-SoC-Delta in
      `services/speicher_wirtschaftlichkeit.py`. Wer ihn irgendwo sonst in einen
      Nenner setzt, erzeugt eine Zahl, die je nach Pflegezustand der Anlage
      springt.

    Es gibt bewusst **keinen** Fallback der einen auf die andere Größe: netto
    statt brutto ist keine konservativere Schätzung, sondern eine andere Zahl
    unter demselben Namen. Ein Helper für netto entsteht getrennt (A31-2).

    **Warum `None` und nicht `0.0` (Entscheidung E16, Gernot 2026-07-28):**
    ein Speicher ohne gepflegte Kapazität ist ein *unbekannter*, kein leerer
    Speicher. Der Aufrufer entscheidet, was er damit tut — summieren (`or 0`),
    die Zahl unterdrücken oder die Rechnung auslassen —, aber er darf keine
    erfinden. Vorher stand an drei Stellen ein `.get(…, 10)`: ein ungepflegter
    Speicher bekam still 10 kWh und daraus eine Jahres-Ersparnis, die es nie
    gab (N127). Freigegeben wurde `None` unter der Bedingung, dass der fehlende
    Wert sichtbar ist — er ist es:
    `services/daten_checker/stammdaten.py` meldet für jeden Speicher ohne
    Kapazität WARNING „…: Kapazität (kWh) fehlt" mit Link auf die
    Investitionspflege.

    **Eine 0 zählt als ungepflegt** und liefert ebenfalls `None`. Das ist die
    hier begründete Ausnahme von der Projektregel „0-Werte mit `is not None`
    prüfen" (dieselbe wie bei `get_pv_kwp`): ein 0-kWh-Speicher ist keine
    Messung, sondern ein leeres Feld. Anders als bei `leistung_kwp` entsteht
    daraus **kein** N107-Widerspruch — es gibt hier nur eine einzige Quelle
    (s. u.), also keinen zweiten Helper, der dieselbe Investition anders
    beantworten könnte.

    **Nur das `parameter`-JSON, nicht die Spalte** — obwohl
    `Investition.leistung_kwp` ein Mehrzweckfeld ist und beim Speicher kWh
    trägt (`pdf/templates/jahresbericht.html` rendert genau das). Gemessen
    (A31-1): **kein Schreibpfad füllt sie beim Speicher** —
    `InvestitionForm.tsx` bietet das Spaltenfeld nur für `pv-module` an, der
    Speicher schreibt ausschließlich `param_kapazitaet_kwh`, und
    `import_export/json_operations.py` reicht die Spalte beim Roundtrip nur
    durch. Es gibt hier also keine #229-Datenlage, die einen Spalten-Fallback
    rechtfertigte; ihn einzubauen wäre keine Härtung, sondern eine
    Verhaltensänderung an jeder der 13 Lesestellen.

    Kein Typfilter (wie bei `get_erzeuger_kwp`): der Aufrufer filtert auf
    `typ == "speicher"`. Ein E-Auto trägt seine Batterie unter dem eigenen
    Schlüssel `batteriekapazitaet_kwh` und liefert hier korrekt `None`.
    """
    return _speicher_param_kwh(inv, PARAM_SPEICHER["KAPAZITAET_KWH"])


def get_speicher_nutzbare_kapazitaet_kwh(inv: Any) -> Optional[float]:
    """**NETTO**-Kapazität eines Speichers in kWh — der real fahrbare SoC-Hub,
    mit stillem Brutto-Fallback. `None`, wenn keine der beiden gepflegt ist.

    Das Gegenstück zu `get_speicher_kapazitaet_kwh` (dort steht die
    Brutto/Netto-Abgrenzung ausführlich). Kurz: `kapazitaet_kwh` ist die
    Nennkapazität des Herstellers, `nutzbare_kapazitaet_kwh` das, was nach
    Entladetiefe und Reserve tatsächlich durch den Speicher geht.

    **Wofür der Netto-Wert gilt** — überall dort, wo eine Rechnung den Speicher
    *durchfährt*, also eine Energiemenge simuliert oder prognostiziert:

    * die Tages-Vorschau „Speicher voll um …"
      (`core/berechnungen/speicher_simulation.py`, Planungs-Tab und HA-Sensor
      `eedc_speicher_voll_um`) — sie lädt von 0 auf 100 % der übergebenen
      Kapazität; mit Brutto ist der Speicher rechnerisch später voll als real;
    * die Wirtschaftlichkeits-**Prognose** ohne IST-Aggregat
      (`core/calculations.py::berechne_speicher_einsparung`, Kapazität × 250
      Zyklen × η) — mit Brutto ist die Jahres-Ersparnis zu hoch;
    * das η-SoC-Delta (`services/speicher_wirtschaftlichkeit.py`), die einzige
      Verwendung, die es schon vor A31-2 gab.

    **Wofür er ausdrücklich NICHT gilt:** die **Vollzyklen**. Deren Nenner ist
    und bleibt brutto — begründet im Kanon `core/berechnungen/speicher.py::
    vollzyklen` (Entscheidung Gernot 2026-07-28, Commit `f1644cc8`) und in
    `docs/BERECHNUNGEN.md` §3.3. Wer hier „vereinheitlicht", macht die
    Zyklenzahl derselben Anlage davon abhängig, ob jemand ein optionales Feld
    ausgefüllt hat.

    **Warum der Brutto-Fallback still ist (Entscheidung E17, Gernot
    2026-07-28):** `nutzbare_kapazitaet_kwh` ist optional und bei den meisten
    Anlagen nicht gepflegt. Ohne den Fallback müssten die drei Rechnungen oben
    dort aussetzen — obwohl die Brutto-Zahl keine *unvollständige* Angabe ist,
    sondern die andere gültige Lesart derselben Größe. Deshalb ist das
    **bewusst kein P4-Fall**: kein `hinweise`-Eintrag, keine Kennzeichnung in
    der Antwort, keine Badge. Der Effekt ist gewollt: die Zahlenänderung aus
    A31-2 trifft ausschließlich Anlagen, die das Feld bewusst gepflegt haben —
    wer es nie angefasst hat, sieht keinen Sprung und braucht keine Erklärung.

    Anders als beim Brutto-Helper ist ein Fallback hier also nicht die
    verbotene Verwechslung, sondern die Entscheidung: die Leserichtung geht
    **nur** netto → brutto und **nie** zurück.

    Eine 0 zählt auch hier als ungepflegt (s. Brutto-Helper). Kein Typfilter —
    der Aufrufer filtert auf `typ == "speicher"`.
    """
    netto = _speicher_param_kwh(inv, PARAM_SPEICHER["NUTZBARE_KAPAZITAET_KWH"])
    if netto is not None:
        return netto
    return get_speicher_kapazitaet_kwh(inv)


def _speicher_param_kwh(inv: Any, schluessel: str) -> Optional[float]:
    """Ein kWh-Wert aus dem `parameter`-JSON — `None` bei fehlend, 0 oder Müll.

    Gemeinsamer Körper der beiden Speicher-Kapazitäts-Helper; die Semantik
    (E16: keine erfundene Zahl) steht in deren Docstrings.
    """
    params = getattr(inv, "parameter", None) or {}
    try:
        wert = float(params.get(schluessel) or 0)
    except (TypeError, ValueError):
        return None
    return wert or None
