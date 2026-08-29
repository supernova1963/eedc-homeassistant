"""F-70: Ein Speicher unter „Sonstiges" zählt in der Live-Bilanz als Speicher.

**Der Defekt.** `live_komponenten_builder` hielt eine Investition nur dann für
bidirektional, wenn ihr **Typ** `speicher` war (oder das E-Auto V2H konnte).
Ein Gerät unter *Sonstiges* mit der Kategorie **Speicher** fiel damit in den
`else`-Zweig — und der kennt nur `verbrauch_kw`. Seine **Entladung** wurde als
Verbrauch gebucht statt als Erzeugung:

    sonstiges/speicher entlädt 2 kW  →  verbrauch_kw: 2.0   (falsch)
    echter Speicher    entlädt 2 kW  →  erzeugung_kw: 2.0   (richtig)
    Autarkie: 67 % statt 86 %

Dieselbe Lücke wie F-69, nur mit dem anderen Gerät — und dieselbe Wurzel: Die
Rolle einer Komponente wurde nicht dort gelesen, wo sie steht.

**Die beiden Schwesterpfade konnten es längst** (`live_sensor_config.
baue_investitions_serien` und `live_tagesverlauf_service`, je
``elif kat == "speicher"``). Der Live-Builder war der einzige Ausreißer; er
zieht damit nach, statt eine vierte Auslegung zu erfinden.

⭐ **Der Schlüssel bleibt `sonstige_<id>`** — `TAGESVERLAUF_KATEGORIE` bildet
`sonstiges` auf `"sonstige"` ab. Es wechselt allein die Seite der Bilanz; der
Vertrag zum Frontend ist unberührt.
"""

from __future__ import annotations

import pytest

from backend.models import Investition
from backend.services.live_komponenten_builder import build_komponenten
from backend.tests import factories


def _lauf(kategorie: str, leistung_w: float) -> tuple[dict, dict]:
    """PV 1 kW, Netzbezug 0,5 kW, ein `sonstiges`-Gerät mit `leistung_w`.

    Vorzeichen wie beim Speicher: positiv = lädt, negativ = entlädt.
    """
    res = build_komponenten(
        factories.mach_anlage(anlagenname="Sonstiges-Speicher", standort_land="DE"),
        {"pv_gesamt_w": 1000.0, "einspeisung_w": 0.0, "netzbezug_w": 500.0},
        {"s": {"leistung_w": leistung_w}},
        {"s": Investition(typ="sonstiges", bezeichnung="Heim-Akku",
                          parameter={"kategorie": kategorie})},
        {"s": {"leistung_w": "sensor.s"}},
    )
    komp = next(k for k in res["komponenten"] if k["key"].endswith("_s"))
    return komp, {g["key"]: g["wert"] for g in res["gauges"]}


def test_sonstiger_speicher_entlaedt_und_hebt_die_autarkie():
    """Entladung ist Erzeugung — und sie zählt in `bat_entladung_kw`.

    direkt = max(0, 1,0 − 0 − 0) = 1,0 · eigen = 1,0 + 2,0 = 3,0 ·
    gesamt = 3,0 + 0,5 = 3,5 ⇒ Autarkie **86 %**. Vor dem Fix stand die
    Entladung als Verbrauch da: eigen = 1,0, gesamt = 1,5 ⇒ **67 %**.
    """
    komp, gauges = _lauf("speicher", -2000.0)
    assert komp["erzeugung_kw"] == pytest.approx(2.0)
    assert komp["verbrauch_kw"] is None
    assert gauges["autarkie"] == pytest.approx(86, abs=1)


def test_sonstiger_speicher_laedt_und_senkt_die_eigenverbrauchsquote():
    """Die Gegenrichtung: Ladung ist Verbrauch — und zählt in `bat_ladung_kw`.

    PV 1 kW, Gerät lädt 0,4 kW ⇒ direkt = max(0, 1,0 − 0 − 0,4) = 0,6 ⇒
    EV-Quote 0,6/1,0 = **60 %**. Ohne den Fix wäre die Ladung kein
    Batterie-Vorgang: direkt = 1,0 ⇒ **100 %**.
    """
    komp, gauges = _lauf("speicher", 400.0)
    assert komp["verbrauch_kw"] == pytest.approx(0.4)
    assert komp["erzeugung_kw"] is None
    assert gauges["eigenverbrauch"] == pytest.approx(60, abs=1)


def test_sonstiger_speicher_behaelt_seinen_schluessel():
    """Der Vertrag zum Frontend ändert sich NICHT — weiter `sonstige_<id>`.

    Ohne diese Probe könnte der Fix unbemerkt auf `batterie_<id>` umschwenken;
    dort hängen im Client vier Präfix-Filter (`EnergieFluss.tsx`).
    """
    komp, _ = _lauf("speicher", -2000.0)
    assert komp["key"] == "sonstige_s"


def test_sonstiger_verbraucher_bleibt_ein_verbraucher():
    """Negativprobe: nur die Kategorie **speicher** wird bidirektional.

    Eine Pool-Pumpe unter *Sonstiges* verbraucht — sie darf durch den Fix
    nicht plötzlich in der Batterie-Summe landen. `leistung_w` ist hier
    positiv wie beim ladenden Speicher; ohne die Kategorie-Prüfung sähen
    beide Fälle gleich aus.
    """
    komp, gauges = _lauf("verbraucher", 400.0)
    assert komp["verbrauch_kw"] == pytest.approx(0.4)
    assert komp["erzeugung_kw"] is None
    # Kein Batterie-Abzug ⇒ direkt = 1,0 ⇒ EV-Quote 100 %.
    assert gauges["eigenverbrauch"] == pytest.approx(100, abs=1)
