"""N-635 — eine Eigenverbrauchs-Formel auf jeder Zeitebene (05.10.2026).

**Regel (ADR-001, eine Formel an einem Ort):** Eigenverbrauch = Direktverbrauch +
Speicher-Entladung, gebildet von ``core/berechnungen/verbrauch.py::
berechne_verbrauchs_kennzahlen``. Das ist auch die Formel des HA-Energie-Dashboards
(``src/data/energy.ts::computeConsumptionSingle``: ``used_solar`` + ``used_battery``).
Bis 05.10.2026 rechneten der Tag und der Monat-aus-Tagen (``core/berechnungen/
tagesbilanz.py``) ``PV − Einspeisung``: mit Speicher zählte das die **Ladung** statt
der **Entladung** — der Tag lag über seinem Gesamtverbrauch, Σ Tage ≠ Monat.

Die Abnahme-Matrix (``test_achsen_matrix.py``, Formen M02 · M04 · M10) misst die
Sichten; diese Datei hält die Regel an kleinen, von Hand nachrechenbaren Fällen fest,
dazu die **benannte Rest-Abweichung** (Zwei-Tage-Fall der Gegenprüfung
``plans/gegenpruefung-ha-bauform-2026-10-05.md``, W1 Punkt a).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import pytest

from backend.core.berechnungen.tagesbilanz import bilanz_aus_stundenrows, monatsbilanz_aus_tagen

#: Regelmarke der Tageszeile (R9): ``{}`` = Zählerlücken-Regel R7 ohne Befund.
MARKE: dict = {}
#: Altbestand ohne Regelmarke (N-92-Zweig).
ALTBESTAND = None


@dataclass
class _R:
    pv_kw: Optional[float] = None
    verbrauch_kw: Optional[float] = None
    einspeisung_kw: Optional[float] = None
    netzbezug_kw: Optional[float] = None
    batterie_kw: Optional[float] = None   # < 0 Ladung, > 0 Entladung
    waermepumpe_kw: Optional[float] = None


def _tag(*, pv, einsp, netz, ladung=0.0, entladung=0.0, verworfen=MARKE):
    """Ein Tag aus zwei Stunden: eine trägt PV/Einspeisung/Netz und die Ladung, die
    zweite die Entladung (die Batterie ist je Stunde netto)."""
    rows = [_R(pv_kw=pv, einspeisung_kw=einsp, netzbezug_kw=netz,
               batterie_kw=(-ladung if ladung else None))]
    if entladung:
        rows.append(_R(pv_kw=0.0, einspeisung_kw=0.0, netzbezug_kw=0.0, batterie_kw=entladung))
    return bilanz_aus_stundenrows(rows, verworfen=verworfen)


# ── Regel ───────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("verworfen", [MARKE, ALTBESTAND], ids=["R7", "Altbestand"])
def test_ohne_speicher_bleibt_pv_minus_einspeisung(verworfen):
    """Ohne Speicher sind beide Formeln gleich — keine Zahl ändert sich."""
    b = _tag(pv=18.0, einsp=6.0, netz=2.0, verworfen=verworfen)
    assert b.eigenverbrauch_kwh == pytest.approx(12.0)


def test_mit_speicher_direktverbrauch_plus_entladung():
    """Form M02 der Matrix an einem Tag: PV 18, Einspeisung 6, Ladung 3, Entladung 2.

    Alt: 18 − 6 = 12 (Ladung als Eigenverbrauch) — und damit über dem
    Gesamtverbrauch 11. Neu: (18 − 6 − 3) + 2 = 11."""
    b = _tag(pv=18.0, einsp=6.0, netz=0.0, ladung=3.0, entladung=2.0)
    assert b.eigenverbrauch_kwh == pytest.approx(11.0)
    assert b.gesamtverbrauch_kwh == pytest.approx(11.0)


def test_tag_ev_passt_zum_gesamtverbrauch():
    """Auftrag: EV ≤ Gesamtverbrauch und EV + Netzbezug = Gesamtverbrauch, wo beide
    gebildet werden (Tag ohne Netzladung)."""
    b = _tag(pv=10.0, einsp=2.0, netz=1.0, ladung=1.0, entladung=5.0)
    assert b.eigenverbrauch_kwh == pytest.approx(12.0)
    assert b.gesamtverbrauch_kwh == pytest.approx(13.0)
    assert b.eigenverbrauch_kwh <= b.gesamtverbrauch_kwh
    assert b.eigenverbrauch_kwh + b.netzbezug_kwh == pytest.approx(b.gesamtverbrauch_kwh)


@pytest.mark.parametrize("verworfen", [MARKE, ALTBESTAND], ids=["R7", "Altbestand"])
def test_beide_zweige_rechnen_dieselbe_formel(verworfen):
    b = _tag(pv=18.0, einsp=6.0, netz=0.0, ladung=3.0, entladung=2.0, verworfen=verworfen)
    assert b.eigenverbrauch_kwh == pytest.approx(11.0)


def test_verworfene_batterie_sperrt_den_eigenverbrauch_nicht():
    """Batterie-Regel = die des Gesamtverbrauchs daneben: ``verworfen.batterie`` sperrt
    nur die Autarkie, nicht Gesamtverbrauch und Eigenverbrauch."""
    b = _tag(pv=18.0, einsp=6.0, netz=0.0, ladung=3.0, entladung=2.0, verworfen={"batterie": 5.0})
    assert b.gesamtverbrauch_kwh == pytest.approx(11.0)
    assert b.eigenverbrauch_kwh == pytest.approx(11.0)
    assert b.autarkie_prozent is None


def test_sperren_bleiben_unveraendert():
    """Total-Fall und ``verworfen`` auf pv/einspeisung sperren weiter."""
    ohne_einsp = bilanz_aus_stundenrows([_R(pv_kw=5.0, netzbezug_kw=1.0, batterie_kw=-1.0)], verworfen=MARKE)
    assert ohne_einsp.eigenverbrauch_kwh is None
    for achse in ("pv", "einspeisung"):
        b = _tag(pv=18.0, einsp=6.0, netz=0.0, ladung=3.0, entladung=2.0, verworfen={achse: 1.0})
        assert b.eigenverbrauch_kwh is None


def test_altbestand_klemmt_wie_der_layer():
    """Einzige Zahl, die sich OHNE Speicher bewegt (benannt im Bericht): ein
    Altbestandstag mit mehr Einspeisung als PV nannte −2, die Layer-Formel klemmt
    bei 0 — wie R7 und der Monat seit Vorlage §10."""
    b = _tag(pv=1.0, einsp=3.0, netz=0.0, verworfen=ALTBESTAND)
    assert b.eigenverbrauch_kwh == pytest.approx(0.0)


# ── Monat aus Tagen ───────────────────────────────────────────────────────────


def test_monat_aus_tagen_dieselbe_formel_sigma_tage_gleich_monat():
    """Drei Tage wie M02: Σ Tage = Monat = 33 (alt Tag 12, Σ 36, Monat 33)."""
    tage = [_tag(pv=18.0, einsp=6.0, netz=0.0, ladung=3.0, entladung=2.0) for _ in range(3)]
    m = monatsbilanz_aus_tagen(tage)
    assert sum(t.eigenverbrauch_kwh for t in tage) == pytest.approx(33.0)
    assert m.eigenverbrauch_kwh == pytest.approx(33.0)


def test_rest_abweichung_netzladung_zwei_tage():
    """Die **benannte Rest-Abweichung** (Gegenprüfung W1, Punkt a).

    Tag 1: PV 1, Netzbezug 10, Ladung 5 — der Speicher nimmt mehr auf, als PV nach
    der Einspeisung übrig ist (Netzladung). Der Tag klemmt den Direktverbrauch bei
    0 ⇒ EV 0. Tag 2: PV 10, Einspeisung 2, Netzbezug 1, Ladung 1, Entladung 5 ⇒
    EV (10 − 2 − 1) + 5 = 12. **Σ Tage 12.**

    Der Monat rechnet dieselbe Formel aus den Summen (PV 11, Einspeisung 2,
    Ladung 6, Entladung 5): (11 − 2 − 6) + 5 = **8** — er verrechnet die 4 kWh
    Netzladung von Tag 1 mit dem PV-Direktverbrauch von Tag 2. Σ Tage ≠ Monat
    an Tagen mit Netzladung ist erlaubt und in ``docs/BERECHNUNGEN.md`` benannt.
    """
    t1 = _tag(pv=1.0, einsp=0.0, netz=10.0, ladung=5.0)
    t2 = _tag(pv=10.0, einsp=2.0, netz=1.0, ladung=1.0, entladung=5.0)
    assert t1.eigenverbrauch_kwh == pytest.approx(0.0)
    assert t2.eigenverbrauch_kwh == pytest.approx(12.0)
    m = monatsbilanz_aus_tagen([t1, t2])
    assert m.eigenverbrauch_kwh == pytest.approx(8.0)
    assert t1.eigenverbrauch_kwh + t2.eigenverbrauch_kwh - m.eigenverbrauch_kwh == pytest.approx(4.0)
    # Am Netzlade-Tag selbst gilt EV ≤ Gesamtverbrauch weiter (0 ≤ 6), nur
    # EV + Netzbezug = Gesamtverbrauch nicht (die Netzladung steckt im Bezug).
    assert t1.gesamtverbrauch_kwh == pytest.approx(6.0)
    assert t1.eigenverbrauch_kwh <= t1.gesamtverbrauch_kwh
