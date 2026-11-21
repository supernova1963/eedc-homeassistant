"""N-806 — die Jahresformel der WP-Ersparnis ist die Summe der Gerätezeilen.

Aussichten → Finanzen rechnet die bisherige Wärmepumpen-Ersparnis (und daraus die Amortisation) über
``core/berechnungen/alternativkosten.py::berechne_wp_alternativkosten_ersparnis``. Bis 21.11.2026:

- **(D)** stand der Zusatzkosten-Term hinter der Geräteschleife und zählte die Zusatzkosten ALLER Wärmepumpen über
  die VEREINIGUNG ihrer Monate — zwei Geräte nacheinander (A Januar–Juni, B Juli–Dezember, je 600 €/Jahr):
  1 466,65 € gegen Σ Gerätezeilen 866,64 €; die Zerlegung je Gerät wies die 600 € als «Rest» aus;
- **(E)** zählte ein Monat mit gemessen 0 kWh Strom und 0 kWh Wärme ein Zwölftel Zusatzkosten (55,19 € bei
  662,28 €/Jahr), die Gerätezeile (``wp_ersparnis_zeile``, ``null_ist_kein_betrieb``) 0 €.

Soll: Sammelaufruf = Summe der Einzelaufrufe = Summe der Gerätezeilen; ein Monat zählt das Zwölftel genau dann, wenn
die Gerätezeile es zählt (Messtest ``~/.claude/plans/golden-master/mess-447/test_mess_447.py``, Fälle D und E).
"""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace

import pytest

from backend.core.berechnungen.alternativkosten import berechne_wp_alternativkosten_ersparnis
from backend.services.wp_wirtschaftlichkeit import wp_ersparnis_zeile

PARAM = {"wp_art": "luft_wasser", "effizienz_modus": "gesamt_jaz", "jaz": 3.5,
         "alter_energietraeger": "gas", "alter_preis_cent_kwh": 12.13,
         "alternativ_zusatzkosten_jahr": 662.28}
PREIS = 31.69
BETRIEB = {"stromverbrauch_kwh": 100.0, "heizenergie_kwh": 400.0}


def _jf(wps, imd):
    preise = {(j, m): PREIS for (_i, j, m) in imd}
    return berechne_wp_alternativkosten_ersparnis(wps, imd, {}, preise, PREIS)


def _zeile(daten, parameter) -> float:
    z = wp_ersparnis_zeile(
        waerme_kwh=daten.get("heizenergie_kwh"), strom_kwh=daten.get("stromverbrauch_kwh"),
        strom_kuehlen_kwh=0.0, strompreis_cent=PREIS, parameter=parameter, gaspreis_cent=None,
        null_ist_kein_betrieb=True,
    )
    return z.ersparnis_euro if z is not None else 0.0


def test_d_zwei_waermepumpen_nacheinander_summe_der_geraetezeilen():
    pa = {**PARAM, "alternativ_zusatzkosten_jahr": 600.0}
    a, b = SimpleNamespace(id=1, parameter=pa), SimpleNamespace(id=2, parameter=pa)
    imd = {(1, 2026, m): BETRIEB for m in range(1, 7)} | {(2, 2026, m): BETRIEB for m in range(7, 13)}

    gesamt = _jf([a, b], imd)
    einzeln = _jf([a], imd) + _jf([b], imd)
    zeilen = sum(_zeile(d, pa) for d in imd.values())

    # Vorher 1 466,65 € (je Gerät 12 statt 6 Zwölftel); Σ Gerätezeilen gerundet je Zeile 866,64 €.
    assert gesamt == pytest.approx(einzeln, abs=1e-9)
    assert gesamt == pytest.approx(zeilen, abs=1e-9)
    assert round(gesamt, 2) == 866.65
    # Je Gerät genau sechs Zwölftel Zusatzkosten (300 €), nicht zwölf.
    ohne_zus = _jf([SimpleNamespace(id=1, parameter={**pa, "alternativ_zusatzkosten_jahr": 0.0})], imd)
    assert _jf([a], imd) - ohne_zus == pytest.approx(300.0)


def test_d_verschiedene_zusatzkosten_und_ueberlappung():
    """A Januar–September 900 €/Jahr, B ab Juli 300 €/Jahr: je Gerät über seine Monate (675 + 150)."""
    pa = {**PARAM, "alternativ_zusatzkosten_jahr": 900.0}
    pb = {**PARAM, "alternativ_zusatzkosten_jahr": 300.0}
    a, b = SimpleNamespace(id=1, parameter=pa), SimpleNamespace(id=2, parameter=pb)
    imd = {(1, 2026, m): BETRIEB for m in range(1, 10)} | {(2, 2026, m): BETRIEB for m in range(7, 13)}
    zeilen = sum(_zeile(d, pa if i == 1 else pb) for (i, _j, _m), d in imd.items())
    assert _jf([a, b], imd) == pytest.approx(zeilen, abs=1e-9)


@pytest.mark.parametrize("daten", [
    {"stromverbrauch_kwh": 0.0, "heizenergie_kwh": 0.0},   # gemessen kein Betrieb (E4d)
    {},                                                    # nichts erfasst
    {"stromverbrauch_kwh": 20.0, "heizenergie_kwh": 0.0},  # Standby (N-670)
])
def test_e_monat_ohne_waerme_traegt_kein_zwoelftel(daten):
    wp = SimpleNamespace(id=1, parameter=PARAM)
    # Vorher 55,19 € für 0/0 und «nichts erfasst»; die Gerätezeile trägt 0 €.
    assert _jf([wp], {(1, 2026, 7): daten}) == 0.0
    assert _zeile(daten, PARAM) == 0.0


def test_einzelgeraet_mit_betrieb_unveraendert():
    """Gegenprobe: eine Wärmepumpe, Monate mit Betrieb — dieselbe Zahl wie vor N-806 (Fall #447: 146,83 €)."""
    wp = SimpleNamespace(id=1, parameter=PARAM)
    okt = {"stromverbrauch_kwh": 225.73, "heizenergie_kwh": 1210.7}
    assert round(_jf([wp], {(1, 2026, 10): okt}), 2) == 146.83
    assert round(_jf([wp], {(1, 2026, 10): okt}), 2) == round(_zeile(okt, PARAM), 2)


@pytest.mark.asyncio
async def test_aussichten_finanzen_rest_der_zerlegung_ist_null(db):
    """Über die Route: zwei Wärmepumpen nacheinander — die Zerlegung je Gerät lässt keinen WP-Rest stehen."""
    from backend.api.routes.aussichten import get_finanz_prognose
    from backend.models import Anlage, Investition, InvestitionMonatsdaten, Monatsdaten, Strompreis

    pa = {**PARAM, "alternativ_zusatzkosten_jahr": 600.0}
    anlage = Anlage(anlagenname="N-806", leistung_kwp=10.0, latitude=48.0, installationsdatum=date(2020, 1, 1))
    db.add(anlage)
    await db.flush()
    db.add(Strompreis(anlage_id=anlage.id, netzbezug_arbeitspreis_cent_kwh=PREIS,
                      einspeiseverguetung_cent_kwh=8.0, gueltig_ab=date(2020, 1, 1)))
    for m in range(1, 13):
        db.add(Monatsdaten(anlage_id=anlage.id, jahr=2025, monat=m, netzbezug_kwh=100.0, einspeisung_kwh=0.0))
    geraete = []
    for name, ab, bis, monate in (("WP A", date(2025, 1, 1), date(2025, 6, 30), range(1, 7)),
                                  ("WP B", date(2025, 7, 1), None, range(7, 13))):
        inv = Investition(anlage_id=anlage.id, typ="waermepumpe", bezeichnung=name, anschaffungsdatum=ab,
                          stilllegungsdatum=bis, anschaffungskosten_gesamt=20000.0, parameter=pa)
        db.add(inv)
        await db.flush()
        for m in monate:
            db.add(InvestitionMonatsdaten(investition_id=inv.id, jahr=2025, monat=m, verbrauch_daten=dict(BETRIEB)))
        geraete.append(inv.id)
    await db.commit()

    r = await get_finanz_prognose(anlage_id=anlage.id, monate=12, db=db)
    je_inv = {e.investition_id: e for e in r.ertraege_je_investition}
    assert set(geraete) <= set(je_inv)
    # Vorher stand die Differenz Gesamtaufruf − Σ Einzelaufrufe (≈ 600 €) hier als Rest.
    assert r.ertraege_nicht_zurechenbar_euro == pytest.approx(0.0, abs=0.01)
