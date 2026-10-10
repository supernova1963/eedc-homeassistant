"""N-663 — die Wärmepumpen-Zeile rechnet bei flexiblem Tarif mit dem gepflegten Monats-Ø, nicht mit dem Tarifpreis.

Gemessen (Analyse 10.10.2026, Wegwerf-DB): allgemeiner Tarif „dynamisch" 30 ct, Monatsabschluss mit
``netzbezug_durchschnittspreis_cent = 24`` ⇒ ``netzbezug_preis_cent`` 24, ``wallbox_preis_effektiv_cent`` 24, aber
**``wp_preis_cent`` 30**. Ursache: ``monats_fakten/tarif.py::_lade_tarif`` bildete den WP-Preis über
``_komponenten_preis``, der ohne eigenen WP-Tarif auf den Stammpreis zurückfällt und die Stufen „gepflegt" und
„gemessen" der Kaskade nie sah. Folge: WP-Ersparnis in Monats-Fakten, Hub, Jahr, HA-Export und Wärme-Verteilung mit
dem Stammpreis, *Cockpit → Monat* ohne Gerätezeile mit dem Monats-Ø — zwei Preise für dieselbe Zeile.

Gehalten wird:

1. Ohne eigenen WP-Tarif: WP-Preis = gepflegter Monats-Ø (24), wie Netzbezug und Wallbox desselben Monats.
2. Gegenprobe: ein eigener WP-Tarif ohne gepflegten Ø bleibt der WP-Preis (22) — der Tarif geht nicht verloren.
"""

from __future__ import annotations

from datetime import date

import pytest

from backend.models import Anlage, Strompreis
from backend.models.monatsdaten import Monatsdaten
from backend.services.monats_fakten import tarif_des_monats

JAHR, MONAT = 2026, 6
TARIF = 30.0
GEPFLEGT = 24.0
WP_TARIF = 22.0


async def _anlage(db, *, gepflegt: float | None, wp_tarif: float | None) -> tuple[int, Monatsdaten]:
    a = Anlage(anlagenname="N663", leistung_kwp=10.0)
    db.add(a)
    await db.flush()
    db.add(Strompreis(
        anlage_id=a.id, gueltig_ab=date(2025, 1, 1), verwendung="allgemein",
        netzbezug_arbeitspreis_cent_kwh=TARIF, einspeiseverguetung_cent_kwh=8.0, vertragsart="dynamisch",
    ))
    if wp_tarif is not None:
        db.add(Strompreis(
            anlage_id=a.id, gueltig_ab=date(2025, 1, 1), verwendung="waermepumpe",
            netzbezug_arbeitspreis_cent_kwh=wp_tarif, einspeiseverguetung_cent_kwh=8.0,
        ))
    md = Monatsdaten(anlage_id=a.id, jahr=JAHR, monat=MONAT, einspeisung_kwh=100.0, netzbezug_kwh=200.0,
                     netzbezug_durchschnittspreis_cent=gepflegt)
    db.add(md)
    await db.flush()
    return a.id, md


@pytest.mark.asyncio
async def test_ohne_wp_tarif_gilt_der_gepflegte_monatsdurchschnitt(db):
    aid, md = await _anlage(db, gepflegt=GEPFLEGT, wp_tarif=None)

    tarif = await tarif_des_monats(db, aid, JAHR, MONAT, md)

    assert tarif.netzbezug_preis_cent == pytest.approx(GEPFLEGT)
    assert tarif.wallbox_preis_effektiv_cent == pytest.approx(GEPFLEGT)
    assert tarif.wp_preis_cent == pytest.approx(GEPFLEGT)


@pytest.mark.asyncio
async def test_eigener_wp_tarif_ohne_gepflegten_oe_bleibt(db):
    aid, md = await _anlage(db, gepflegt=None, wp_tarif=WP_TARIF)

    tarif = await tarif_des_monats(db, aid, JAHR, MONAT, md)

    assert tarif.wp_preis_cent == pytest.approx(WP_TARIF)
    assert tarif.netzbezug_preis_cent == pytest.approx(TARIF)
