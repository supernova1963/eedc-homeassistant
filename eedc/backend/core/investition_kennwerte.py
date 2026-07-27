"""SoT-Helper für Investitions-Kennwerte — heute: die Nennleistung in kWp.

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

from typing import Any, Final

from backend.core.investition_parameter import (
    LEGACY_KWP_KEY,
    PARAM_BALKONKRAFTWERK,
    PARAM_PV_MODULE,
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
