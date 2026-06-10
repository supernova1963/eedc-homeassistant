"""Regressionstest: `simuliere_speicher_tag` Stunden-Bilanz (Pre-IA-V4 Slice B).

Die Ganztags-Vorschau in `energie_profil/views.py` hatte die SoC-State-Machine
+ Netzbezug/Einspeisung-Rest inline dupliziert. Nach der Migration auf
`simuliere_speicher_tag(...).stunden_bilanz` pinnt dieser Test, dass der Helper
exakt das liefert, was die alte Inline-Schleife rechnete — sowohl mit als auch
ohne Speicher. Ändert sich ein Wert, ist es ein gefundener Bug (ADR-001-Sweep).
"""

from __future__ import annotations

from typing import Optional

import pytest

from backend.core.berechnungen.speicher_simulation import simuliere_speicher_tag


def _inline_referenz(
    pv_stunden: list[float],
    verbrauch_stunden: list[float],
    speicher_kap: float,
    start_soc: float,
) -> list[tuple[int, float, float, float, float, float, Optional[float]]]:
    """Wortgleiche Kopie der alten Inline-Schleife aus views.py (vor Migration)."""
    soc = start_soc
    out = []
    for h in range(24):
        pv = pv_stunden[h] if h < len(pv_stunden) else 0.0
        vb = verbrauch_stunden[h] if h < len(verbrauch_stunden) else 0.0
        netto = pv - vb
        netzbezug = 0.0
        einspeisung = 0.0
        soc_h: Optional[float] = None
        if speicher_kap > 0:
            if netto > 0:
                lade_kapazitaet = (100.0 - soc) / 100.0 * speicher_kap
                ladung = min(netto, lade_kapazitaet)
                soc += (ladung / speicher_kap) * 100.0
                soc = min(soc, 100.0)
                einspeisung = netto - ladung
            else:
                defizit = abs(netto)
                entlade_kapazitaet = soc / 100.0 * speicher_kap
                entladung = min(defizit, entlade_kapazitaet)
                soc -= (entladung / speicher_kap) * 100.0
                soc = max(soc, 0.0)
                netzbezug = defizit - entladung
            soc_h = round(soc, 1)
        else:
            if netto > 0:
                einspeisung = netto
            else:
                netzbezug = abs(netto)
        out.append((h, pv, vb, netto, netzbezug, einspeisung, soc_h))
    return out


def _assert_bilanz_gleich(pv, vb, kap, soc):
    ref = _inline_referenz(pv, vb, kap, soc)
    sim = simuliere_speicher_tag(pv, vb, speicher_kap_kwh=kap, start_soc_prozent=soc)
    assert len(sim.stunden_bilanz) == 24
    for (h, p, v, netto, nb, ein, soc_h), b in zip(ref, sim.stunden_bilanz):
        assert b.stunde == h
        assert b.pv_kwh == pytest.approx(p)
        assert b.verbrauch_kwh == pytest.approx(v)
        assert b.netto_kwh == pytest.approx(netto)
        assert b.netzbezug_kwh == pytest.approx(nb)
        assert b.einspeisung_kwh == pytest.approx(ein)
        assert b.soc_prozent == soc_h


def test_bilanz_mit_speicher_laden_entladen_ueberlauf():
    # Vormittags Überschuss (lädt + Überlauf → Einspeisung), abends Defizit
    # (entlädt + Restbezug).
    pv = [0.0] * 6 + [3.0] * 8 + [0.0] * 10
    vb = [0.5] * 24
    _assert_bilanz_gleich(pv, vb, kap=10.0, soc=20.0)


def test_bilanz_ohne_speicher_direkte_bilanz():
    pv = [0.0] * 8 + [2.0] * 6 + [0.0] * 10
    vb = [0.7] * 24
    sim = simuliere_speicher_tag(pv, vb, speicher_kap_kwh=0.0, start_soc_prozent=50.0)
    _assert_bilanz_gleich(pv, vb, kap=0.0, soc=50.0)
    # Ohne Speicher: kein SoC, soc_pro_stunde bleibt leer (HA-Export-Kontrakt).
    assert sim.soc_pro_stunde == {}
    assert all(b.soc_prozent is None for b in sim.stunden_bilanz)
