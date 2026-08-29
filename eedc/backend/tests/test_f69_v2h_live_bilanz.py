"""F-69: Ein V2H-fähiges E-Auto zählt in der Live-Bilanz als Batterie.

**Der Defekt.** `bat_ladung_kw`/`bat_entladung_kw` in
`live_komponenten_builder` filterten auf Schlüssel mit dem Präfix ``v2h_`` —
den **niemand erzeugt und nie erzeugt hat** (`git log --all -S` über die ganze
Historie: leer). Ein V2H-Auto ist im Live-Pfad bidirektional
(`ist_v2h ⇒ ist_bidirektional`), heißt dort aber ``eauto_<id>``. Es fiel damit
aus beiden Summen:

* **Laden** — fehlt in `bat_ladung_kw` ⇒ `direktverbrauch_kw` zu hoch ⇒
  **Eigenverbrauchsquote zu hoch** (gemessen: 100 % statt 33 %).
* **Entladen** — fehlt in `bat_entladung_kw` ⇒ `eigenverbrauch_kw` zu niedrig ⇒
  **Autarkie zu niedrig** (gemessen: 67 % statt 86 %).

**Warum der Filter nicht einfach auf ``eauto_`` gehoben wurde:** Denselben
Schlüssel trägt auch ein **gewöhnliches, nicht-V2H-Auto** (`LIVE_KEY_PREFIX`
kennt nur `wallbox`). Die Unterscheidung ist der `v2h_faehig`-Parameter der
Investition, nicht der Name — deshalb hält der Builder die Rolle jetzt selbst
fest (`bidirektionale_keys`), statt sie aus einem String abzuleiten.

⚠ **Zwei Gegenproben, weil zwei getrennte Bildungsstellen** (N-274/W-Z1-Bauform):
Ladung und Entladung sind zwei eigene Summen. Jede hat ihre eigene Probe, und
der Rückbau **einer** Zeile macht **genau ihre** Probe rot — nicht die andere.

⛔ **Nicht Gegenstand dieser Datei:** die Tages-/Snapshot-Ebene. Dort kennt
eedc V2H weiterhin nicht; das ist die in #110 geführte, bewusst
zurückgestellte Zeile „V2H-Lücken schließen" (vgl. N-288).
"""

from __future__ import annotations

import pytest

from backend.models import Investition
from backend.services.live_komponenten_builder import build_komponenten
from backend.tests import factories


def _anlage():
    return factories.mach_anlage(anlagenname="V2H-Live", standort_land="DE")


def _eauto(*, v2h: bool) -> Investition:
    return Investition(
        typ="e-auto",
        bezeichnung="Ioniq 5" if v2h else "Zoe",
        parameter={"v2h_faehig": True} if v2h else {},
    )


def _bilanz(*, v2h: bool, leistung_w: float, pv_w: float,
            einspeisung_w: float = 0.0, netzbezug_w: float = 0.0) -> dict:
    """Ein Auto mit `leistung_w` (positiv = lädt, negativ = entlädt) neben PV."""
    res = build_komponenten(
        _anlage(),
        {"pv_gesamt_w": pv_w, "einspeisung_w": einspeisung_w,
         "netzbezug_w": netzbezug_w},
        {"auto": {"leistung_w": leistung_w}},
        {"auto": _eauto(v2h=v2h)},
        {"auto": {"leistung_w": "sensor.auto"}},
    )
    return {g["key"]: g["wert"] for g in res["gauges"]}


# ── Gegenprobe 1: die ENTLADE-Summe (`bat_entladung_kw`) ────────────────────

def test_v2h_entladung_hebt_die_autarkie():
    """PV 1 kW, Auto entlädt 2 kW, Netzbezug 0,5 kW.

    Richtig: direkt = max(0, 1 − 0 − 0) = 1,0 · eigen = 1,0 + 2,0 = 3,0 ·
    gesamt = 3,0 + 0,5 = 3,5 ⇒ Autarkie 3,0/3,5 = **86 %**.
    Vor dem Fix fehlten die 2 kW: eigen = 1,0, gesamt = 1,5 ⇒ **67 %**.
    """
    gauges = _bilanz(v2h=True, leistung_w=-2000.0, pv_w=1000.0, netzbezug_w=500.0)
    assert gauges["autarkie"] == pytest.approx(86, abs=1)


# ── Gegenprobe 2: die LADE-Summe (`bat_ladung_kw`) ──────────────────────────

def test_v2h_ladung_senkt_die_eigenverbrauchsquote():
    """PV 3 kW, Auto lädt 2 kW, keine Einspeisung, kein Bezug.

    Richtig: direkt = max(0, 3 − 0 − 2) = 1,0 · eigen = 1,0 + 0 = 1,0 ⇒
    EV-Quote 1,0/3,0 = **33 %**. Vor dem Fix zählte die Ladung nicht als
    Batterie: direkt = 3,0 ⇒ eigen = 3,0 ⇒ **100 %**.
    """
    gauges = _bilanz(v2h=True, leistung_w=2000.0, pv_w=3000.0)
    assert gauges["eigenverbrauch"] == pytest.approx(33, abs=1)


# ── Negativprobe: ein gewöhnliches Auto bleibt ein Verbraucher ──────────────

def test_gewoehnliches_eauto_zaehlt_nicht_als_batterie():
    """Ohne `v2h_faehig` ist die Ladung **Direktverbrauch**, nicht Batterieladung.

    Dieselben Zahlen wie in Gegenprobe 2, nur ohne V2H: Das Auto ist kein
    Speicher, seine 2 kW werden nicht abgezogen ⇒ direkt = 3,0 ⇒ EV-Quote
    **100 %**. Ohne diese Probe würde ein Filter auf den Präfix `eauto_`
    (der naheliegende, falsche Fix) unbemerkt durchgehen.
    """
    gauges = _bilanz(v2h=False, leistung_w=2000.0, pv_w=3000.0)
    assert gauges["eigenverbrauch"] == pytest.approx(100, abs=1)


def test_v2h_auto_traegt_denselben_schluessel_wie_ein_gewoehnliches():
    """Der Schlüssel unterscheidet die beiden NICHT — deshalb taugt er nicht als Filter.

    Das ist die Messung hinter der Bauentscheidung: Beide Autos heißen
    `eauto_<id>`. Wer die Rolle am Namen festmacht, kann sie nicht treffen.
    """
    keys = {}
    for v2h in (True, False):
        res = build_komponenten(
            _anlage(), {"pv_gesamt_w": 3000.0, "einspeisung_w": 0.0, "netzbezug_w": 0.0},
            {"auto": {"leistung_w": 2000.0}}, {"auto": _eauto(v2h=v2h)},
            {"auto": {"leistung_w": "sensor.auto"}},
        )
        keys[v2h] = [k["key"] for k in res["komponenten"] if k["key"].endswith("_auto")]
    assert keys[True] == keys[False] == ["eauto_auto"]
