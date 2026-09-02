"""N-187 — die Achse-2-Invariante vergleicht dieselbe Grundgesamtheit.

**Der gemessene Fall** (Anlage 1, 2026-08-06, erhoben am 2026-09-02): Die
Diagnose meldete für „Wallbox+E-Auto" eine Drift von **17,323 kWh** — Zähler
12,000 gegen Leistung 29,323. Die 17,323 sind auf drei Nachkommastellen die Σ
von ``eauto_1``, einem E-Auto **mit** Leistungs-, aber **ohne** kWh-Zähler. Die
Wallbox selbst stimmte auf beiden Seiten exakt (12,00 = 12,000).

Der Zählerpfad kann ein Gerät ohne Zähler gar nicht führen (``snap_h`` wird aus
zählergedeckten Feldern gebaut, ``snapshot/aggregator.py``); der Leistungspfad
führt es. Die Invariante verglich damit **zwei verschiedene Mengen** und meldete
deren Differenz als Drift — dieselbe Klasse wie **F-58**, wo Zähler und Nenner
des spezifischen Ertrags auseinanderliefen, nur eine Kategorie weiter.

Die bestehende Skip-Semantik hatte die richtige Absicht, aber die falsche
Granularität: sie fragt je **Kategorie**, das Problem sitzt je **Gerät**.

⚠ Was hier NICHT geprüft wird: die Rechenregel selbst (Σ-Semantik, Vorzeichen,
Toleranz). Die hat ihre eigene Datei
(``test_invariante_komponenten_intern_achse2.py``) und ist unverändert.
"""

from __future__ import annotations

import inspect
from types import SimpleNamespace

import pytest

from backend.core.berechnungen import pruefe_tep_komponenten_intern_konsistenz


def _tep_row(stunde: int, *, komponenten=None, **kw):
    defaults = {
        "stunde": stunde,
        "pv_kw": None,
        "waermepumpe_kw": None,
        "wallbox_kw": None,
        "batterie_kw": None,
        "einspeisung_kw": None,
        "netzbezug_kw": None,
        "komponenten": komponenten,
    }
    defaults.update(kw)
    return SimpleNamespace(**defaults)


def _wallbox_bericht(berichte):
    return next((b for b in berichte if "Wallbox+E-Auto" in b.name), None)


# ── Der gemessene Fall, nachgestellt ────────────────────────────────────────

def _anlage_1_am_06_08():
    """Nachstellung: Wallbox mit Zähler (12,0), E-Auto nur im Leistungspfad.

    Stundenwerte gerundet auf die gemessenen Tages-Σ — 12,000 gegen
    12,00 + 17,32.
    """
    return [
        _tep_row(h, wallbox_kw=1.0,
                 komponenten={"wallbox_2": -1.0, "eauto_1": -1.4433})
        for h in range(12)
    ]


def test_geraet_ohne_zaehler_erzeugt_keine_drift():
    """Der Fall, der die Falschmeldung erzeugt hat: `eauto_1` ist nicht gedeckt.

    Nur `wallbox_2` trägt einen Zähler ⇒ der Leistungspfad wird darauf
    eingeschränkt, beide Seiten stehen bei 12,0 ⇒ konsistent.
    """
    berichte = pruefe_tep_komponenten_intern_konsistenz(
        _anlage_1_am_06_08(), {"wallbox_2"},
    )
    wb = _wallbox_bericht(berichte)
    assert wb is not None, "Kategorie darf nicht verschwinden, nur stimmen"
    assert wb.konsistent, str(wb)
    assert wb.abweichung_kwh < 0.5, str(wb)


def test_ohne_einschraenkung_meldet_derselbe_tag_weiterhin_drift():
    """Sprengsatz-Gegenprobe: mit `None` bleibt die alte Falschmeldung stehen.

    Ohne diesen Fall wäre `test_geraet_ohne_zaehler_erzeugt_keine_drift` auch
    dann grün, wenn die Invariante gar keine Drift mehr melden **könnte**.
    """
    berichte = pruefe_tep_komponenten_intern_konsistenz(
        _anlage_1_am_06_08(), None,
    )
    wb = _wallbox_bericht(berichte)
    assert wb is not None and not wb.konsistent, str(wb)
    assert wb.abweichung_kwh == pytest.approx(17.32, abs=0.05), str(wb)


# ── Die andere Regelhälfte: gedeckte Geräte bleiben scharf ─────────────────

def test_echte_drift_eines_gedeckten_geraets_bleibt_sichtbar():
    """Beide Geräte haben einen Zähler, die Beträge passen nicht ⇒ melden.

    Diese Probe ist die Diskriminierung: Ein Fix, der die Kategorie einfach
    stumm schaltet, wird hier rot.
    """
    tep = [
        _tep_row(h, wallbox_kw=1.0,
                 komponenten={"wallbox_2": -0.6, "eauto_1": -1.4})
        for h in range(24)
    ]
    berichte = pruefe_tep_komponenten_intern_konsistenz(
        tep, {"wallbox_2", "eauto_1"},
    )
    wb = _wallbox_bericht(berichte)
    assert wb is not None and not wb.konsistent, str(wb)
    assert wb.abweichung_kwh == pytest.approx(24.0, abs=0.1), str(wb)


def test_gedecktes_geraet_das_nichts_lieferte_bleibt_eine_luecke():
    """Ein Zähler-Gerät, das an diesem Tag NICHTS geschrieben hat, wird nicht
    weggefiltert — sonst versteckte die Einschränkung eine echte Lücke.

    Genau deshalb kommt die Menge aus der **Zuordnung** und nicht aus
    `tz.komponenten_kwh` (was der Zählerpfad tatsächlich geschrieben hat).
    """
    tep = [
        _tep_row(h, wallbox_kw=1.0, komponenten={"wallbox_2": -0.4})
        for h in range(24)
    ]
    berichte = pruefe_tep_komponenten_intern_konsistenz(
        tep, {"wallbox_2", "eauto_1"},   # eauto_1 verspricht, liefert aber nicht
    )
    wb = _wallbox_bericht(berichte)
    assert wb is not None and not wb.konsistent, str(wb)


def test_leere_grundgesamtheit_ueberspringt_statt_null_zu_melden():
    """Deckt die Zuordnung gar nichts, ist nichts vergleichbar ⇒ kein Bericht.

    Andernfalls stünde „Drift gegen 0" da — das Falsch-Positiv, das die
    bestehende Skip-Semantik ausdrücklich verhindern soll.
    """
    berichte = pruefe_tep_komponenten_intern_konsistenz(
        _anlage_1_am_06_08(), set(),
    )
    assert _wallbox_bericht(berichte) is None


# ── Kein stilles Zurückfallen ──────────────────────────────────────────────

def test_die_grundgesamtheit_ist_pflicht():
    """Der Parameter hat **keinen** Default.

    Ein vergessener Aufrufer soll brechen, nicht still in das Verhalten
    zurückfallen, das die Falschmeldung erzeugt hat. Ohne diese Probe wäre ein
    später ergänzter Default unbemerkt — genau die Klasse „eine Probe, die
    still wertlos wird".
    """
    sig = inspect.signature(pruefe_tep_komponenten_intern_konsistenz)
    param = sig.parameters["zaehler_gedeckte_keys"]
    assert param.default is inspect.Parameter.empty, (
        "zaehler_gedeckte_keys darf keinen Default bekommen — sonst fällt ein "
        "Aufrufer, der ihn vergisst, still auf das alte Verhalten zurück."
    )
    with pytest.raises(TypeError):
        pruefe_tep_komponenten_intern_konsistenz(_anlage_1_am_06_08())


def test_beide_produktiv_aufrufer_uebergeben_die_grundgesamtheit():
    """Abwesenheitsbeweis: kein Produktiv-Aufruf ohne zweites Argument.

    Die Signatur-Probe oben schützt den Default; diese hier schützt die
    **Aufrufstellen** — der Aggregator und die Diagnose-Route.
    """
    import pathlib
    import re

    wurzel = pathlib.Path(__file__).resolve().parents[1]
    treffer = []
    for pfad in wurzel.rglob("*.py"):
        if "tests" in pfad.parts:
            continue
        text = pfad.read_text(encoding="utf-8")
        # Aufruf mit genau EINEM Argument in derselben Zeile
        for m in re.finditer(
            r"pruefe_tep_komponenten_intern_konsistenz\(([^),]*)\)", text
        ):
            if m.group(1).strip():
                treffer.append(f"{pfad.name}: {m.group(0)}")
    assert not treffer, (
        "Aufruf ohne Grundgesamtheit gefunden: " + "; ".join(treffer)
    )
