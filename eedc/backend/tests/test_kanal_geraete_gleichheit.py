"""Gleichheitsprobe der E-Mob- und Sonstiges-Gruppe aus Kanälen (HA-Bauform E4c, Auftrag Punkt 5).

Zwei Aussagen an den Datenständen der Achsen-Matrix mit Wallbox/E-Auto/Sonstiges (``kanal_bilanz_gleichheit.datenstand``:
HA-Langzeitstatistik im echten Recorder-Schema, Spiegel und abgeleiteter Kanal wie im Produkt):

* **(a) == Bestand für den abgeschlossenen Monat.** Nach dem Abschluss („Aus HA laden", S1) nennen die Monats-Fakten des
  Juni mit den Kanal-Gruppen dieselben E-Mob- und Sonstiges-Zahlen wie ohne sie (Leser ``geraete_monate`` leer — der
  Bestand): gespeichert schlägt gerechnet (P8), die Aufteilung (Quote des abgeleiteten Kanals) ist an diesen
  Datenständen dieselbe wie die der Tagesebene.
* **Kanal-Monat ohne Abschluss == Wert nach dem Abschluss** (Bauplan §7 E-c). Der Juni VOR dem Abschluss (Monats-Fakten
  mit Tageswerten, Kanal-Gruppen) nennt dieselben Zahlen wie derselbe Juni NACH dem Abschluss.

Verglichen werden je Feld: Heimladung (Menge, PV, Netz, Quelle), dienstliche Ladung, je Auto, Wallbox- und E-Auto-Summe,
Sonstiges (Erzeugung, Verbrauch, Abgabe, je Gerät), Erzeugung hinter dem Zähler und die Bilanz-Kennzahlen. Toleranz
0,01 kWh (der Abschluss speichert auf zwei Stellen gerundet).

Schwesterdateien: test_kanal_bilanz_gleichheit.py (Bilanz-Gruppe), test_kanal_geraete_leser.py (Wahl der Gruppen),
test_kanal_abgeleitet.py (abgeleiteter Kanal), test_achsen_matrix.py (die Zellen als Richter).
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from backend.tests import achsen_matrix as am
from backend.tests import kanal_bilanz_gleichheit as kg
from backend.tests import pv_achse_matrix as mx

FORMEN = ("M02", "M07", "M08", "M09", "M10", "W2-E")
TOL = 0.01


def _flach(f, ids: dict[str, int]) -> dict[str, Any]:
    """Die verglichenen Felder eines Monats-Fakts, je Gerät unter seinem Namen."""
    rev = {v: k for k, v in ids.items()}
    e, s = f.emob, f.sonstiges
    out: dict[str, Any] = {
        "emob.ladung": e.ladung_kwh, "emob.pv": e.ladung_pv_kwh, "emob.netz": e.ladung_netz_kwh,
        "emob.quelle": e.quelle, "emob.dienst_pv": e.dienstlich_ladung_pv_kwh,
        "emob.dienst_netz": e.dienstlich_ladung_netz_kwh,
        "emob.wallbox_summe": e.wallbox_summe.ladung_kwh, "emob.eauto_summe": e.eauto_summe.ladung_kwh,
        "sonstiges.erzeugung": s.erzeugung_kwh, "sonstiges.verbrauch": s.verbrauch_kwh,
        "sonstiges.abgabe": s.abgabe_kwh, "erzeugung.sonstige": f.erzeugung.sonstige_erzeuger_kwh,
        "erzeugung.hinter_zaehler": f.erzeugung.hinter_zaehler_kwh,
        "kennzahlen.ev": f.kennzahlen.eigenverbrauch_kwh, "kennzahlen.gv": f.kennzahlen.gesamtverbrauch_kwh,
    }
    for inv_id, a in (e.je_auto or {}).items():
        out[f"je_auto.{rev.get(inv_id, inv_id)}"] = (round(a.pv_kwh, 3), round(a.netz_kwh, 3))
    for inv_id, g in (s.je_geraet or {}).items():
        out[f"sonstiges.{rev.get(inv_id, inv_id)}"] = (round(g.erzeugung_kwh, 3), round(g.verbrauch_kwh, 3))
    return out


def _abweichungen(a: dict, b: dict) -> list:
    out = []
    for k in sorted(set(a) | set(b)):
        x, y = a.get(k), b.get(k)
        if isinstance(x, tuple) and isinstance(y, tuple):
            gleich = all(abs(p - q) <= TOL for p, q in zip(x, y))
        elif isinstance(x, (int, float)) and isinstance(y, (int, float)) and not isinstance(x, bool):
            gleich = abs(x - y) <= TOL
        else:
            gleich = x == y
        if not gleich:
            out.append((k, x, y))
    return out


async def _juni(ds, *, tageswerte: bool):
    from backend.services.monats_fakten import lade_monats_fakten

    with am.umgebung(am.MATRIX_FORMEN[ds.fid], ds.svc):
        fk = await lade_monats_fakten(ds.db, ds.aid, von=(mx.JAHR, mx.JUNI), bis=(mx.JAHR, mx.JUNI),
                                      inkl_nur_tageswerte=tageswerte)
    assert fk, "der Juni fehlt"
    return _flach(fk[0], ds.ids)


@pytest.mark.parametrize("fid", FORMEN)
async def test_kanal_monat_ohne_abschluss_gleich_dem_wert_nach_dem_abschluss_und_a_bleibt_der_bestand(fid):
    async with kg.datenstand("achsen", fid, "HA") as ds:
        vor = await _juni(ds, tageswerte=True)
        with am.umgebung(am.MATRIX_FORMEN[fid], ds.svc):
            await am.schreibe_s1_aus_ha_laden(ds.db, am.MATRIX_FORMEN[fid], ds.aid)
        nach = await _juni(ds, tageswerte=False)
        with patch("backend.services.kanal.geraete_leser.geraete_monate", new=AsyncMock(return_value={})):
            bestand = await _juni(ds, tageswerte=False)
    assert not _abweichungen(vor, nach), _abweichungen(vor, nach)
    assert not _abweichungen(nach, bestand), _abweichungen(nach, bestand)
    # Die Probe misst etwas: die Gruppe der Form trägt einen Wert.
    form = am.MATRIX_FORMEN[fid]
    if form.typ("wallbox") or form.typ("e-auto"):
        assert (nach["emob.ladung"] or 0) + (nach["emob.dienst_pv"] or 0) > 0
    if form.typ("sonstiges"):
        assert (nach["sonstiges.erzeugung"] or 0) + (nach["sonstiges.verbrauch"] or 0) > 0


@pytest.mark.parametrize("fid", ("M02", "M07", "M09", "M10"))
async def test_ohne_ha_die_eigene_summe_nennt_denselben_monat_ohne_abschluss(fid):
    """Ohne HA (reine MQTT-Anlage, eigene Summe mit HAs Regel, abgeleiteter Kanal aus ihr) nennt der Juni ohne Abschluss
    dieselben E-Mob- und Sonstiges-Zahlen wie mit HA — die Gruppen hängen nicht an der Quelle der Kanäle."""
    async with kg.datenstand("achsen", fid, "HA") as ds:
        ha = await _juni(ds, tageswerte=True)
    async with kg.datenstand("achsen", fid, "MQTT") as ds:
        mqtt = await _juni(ds, tageswerte=True)
    assert not _abweichungen(ha, mqtt), _abweichungen(ha, mqtt)
