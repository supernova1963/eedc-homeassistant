"""N-617 — Community-Stammdaten beschreiben die heutige Ausstattung: erst der Zeitfilter, dann der Wert.

``services/community_service.py::prepare_community_data`` filterte schon den Speicher mit
``ist_aktiv_an(heute)`` (F-24), die übrigen Ausstattungswerte nicht. Gemessen über den Einstieg
(04.10.2026): ein stillgelegter, künftiger oder deaktivierter Ost-String machte aus „30°, süd" ein
„20°, gemischt"; eine stillgelegte 22-kW-Wallbox neben der neuen 11-kW-Box ergab 22 kW; ein
stillgelegtes Balkonkraftwerk neben dem neuen 1.400 statt 800 Wp, ein erst künftig angeschafftes
schon heute 800 Wp. Der Server rechnet nichts nach — diese Werte verlassen das Haus.

Gehalten wird: Ø Neigung/Ausrichtung, ``wallbox_kw`` und ``bkw_wp`` zählen nur heute aktive
Investitionen; die heutige Ausstattung ohne Altgeräte bleibt, wie sie war. Bewusst NICHT umgestellt
(gezeigt im Baubericht): die ``hat_*``-Merkmale und ``wp_art`` — sie öffnen auf dem Server den
Vergleich der historischen Monatswerte.

Schwesterdateien: test_community_payload_f47_f48.py (Stammdaten des Payloads),
test_community_payload_monats_fakten.py (Monatswerte des Payloads).
"""

from __future__ import annotations

from datetime import date

import pytest

from backend.models import Anlage, Investition, Monatsdaten
from backend.services.community_service import prepare_community_data

D0 = date(2024, 1, 1)
STILL = date(2025, 1, 31)
KUENFTIG = date(2099, 1, 1)   # fest: liegt für jeden Lauf in der Zukunft (keine echte Uhr in der Probe)


async def _payload(db, invs: list[dict]) -> dict:
    a = Anlage(anlagenname="N617", leistung_kwp=6.0, standort_plz="10115", standort_land="DE", installationsdatum=D0)
    db.add(a)
    await db.flush()
    for kw in invs:
        db.add(Investition(anlage_id=a.id, anschaffungskosten_gesamt=1.0, **{"anschaffungsdatum": D0, **kw}))
    db.add(Monatsdaten(anlage_id=a.id, jahr=2026, monat=8, einspeisung_kwh=400.0, netzbezug_kwh=200.0,
                       pv_erzeugung_kwh=700.0))
    await db.commit()
    return await prepare_community_data(db, a.id, include_monatswerte=False)


SUED = dict(typ="pv-module", bezeichnung="Süd", leistung_kwp=6.0, neigung_grad=30, ausrichtung="Süd")
OST = dict(typ="pv-module", bezeichnung="Ost", leistung_kwp=3.0, neigung_grad=10, ausrichtung="Ost")


@pytest.mark.asyncio
@pytest.mark.parametrize("ost", [
    dict(stilllegungsdatum=STILL), dict(anschaffungsdatum=KUENFTIG), dict(aktiv=False),
], ids=["stillgelegt", "kuenftig", "deaktiviert"])
async def test_neigung_und_ausrichtung_nur_ueber_heute_aktive_erzeuger(db, ost):
    d = await _payload(db, [SUED, {**OST, **ost}])
    assert (d["neigung_grad"], d["ausrichtung"]) == (30, "süd")


@pytest.mark.asyncio
async def test_heute_aktiver_zweiter_string_zaehlt_weiter(db):
    """Gegenprobe: ohne Altgerät bleibt der Ø, wie er war (30 + 10 → 20, süd + ost → gemischt)."""
    d = await _payload(db, [SUED, OST])
    assert (d["neigung_grad"], d["ausrichtung"]) == (20, "gemischt")


@pytest.mark.asyncio
async def test_stillgelegtes_balkonkraftwerk_zaehlt_weder_im_mittel_noch_in_der_leistung(db):
    bkw = dict(typ="balkonkraftwerk", bezeichnung="Balkon", parameter={"leistung_wp": 400, "anzahl": 2},
               neigung_grad=90, ausrichtung="West", stilllegungsdatum=STILL)
    d = await _payload(db, [SUED, bkw])
    assert (d["neigung_grad"], d["ausrichtung"], d["bkw_wp"]) == (30, "süd", None)


@pytest.mark.asyncio
@pytest.mark.parametrize("alt", [dict(stilllegungsdatum=STILL), dict(aktiv=False)], ids=["stillgelegt", "deaktiviert"])
async def test_wallbox_leistung_der_heutigen_box(db, alt):
    wb_alt = dict(typ="wallbox", bezeichnung="alt", parameter={"max_ladeleistung_kw": 22.0}, **alt)
    wb_neu = dict(typ="wallbox", bezeichnung="neu", parameter={"max_ladeleistung_kw": 11.0})
    assert (await _payload(db, [SUED, wb_alt, wb_neu]))["wallbox_kw"] == 11.0


@pytest.mark.asyncio
async def test_bkw_leistung_ohne_alt_und_ohne_kuenftiges_geraet(db):
    alt = dict(typ="balkonkraftwerk", bezeichnung="alt", parameter={"leistung_wp": 300, "anzahl": 2}, stilllegungsdatum=STILL)
    neu = dict(typ="balkonkraftwerk", bezeichnung="neu", parameter={"leistung_wp": 400, "anzahl": 2})
    assert (await _payload(db, [SUED, alt, neu]))["bkw_wp"] == 800.0
    kuenftig = dict(typ="balkonkraftwerk", bezeichnung="bald", parameter={"leistung_wp": 400, "anzahl": 2},
                    anschaffungsdatum=KUENFTIG)
    assert (await _payload(db, [SUED, kuenftig]))["bkw_wp"] is None


@pytest.mark.asyncio
async def test_hat_merkmale_bleiben_wie_sie_waren(db):
    """Bewusst nicht umgestellt — die Merkmale öffnen auf dem Server den Vergleich der historischen Monatswerte.

    ``wp_art`` ist hier absichtlich nicht festgehalten: es folgt der ersten Wärmepumpe (bekannte Vereinfachung),
    ob es der heutigen folgen soll, ist eine offene Frage im Baubericht — keine Probe zementiert die Antwort.
    """
    wp_alt = dict(typ="waermepumpe", bezeichnung="alt", parameter={"wp_art": "luft_wasser"}, stilllegungsdatum=STILL)
    wp_neu = dict(typ="waermepumpe", bezeichnung="neu", parameter={"wp_art": "sole_wasser"})
    wb_alt = dict(typ="wallbox", bezeichnung="alt", parameter={"max_ladeleistung_kw": 22.0}, stilllegungsdatum=STILL)
    d = await _payload(db, [SUED, wp_alt, wp_neu, wb_alt])
    assert (d["hat_waermepumpe"], d["hat_wallbox"], d["wallbox_kw"]) == (True, True, None)
