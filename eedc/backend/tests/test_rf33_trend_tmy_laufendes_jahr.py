"""RF-33 — benannte Probe für den TMY-Zweig des laufenden Jahres in der Trend-Analyse.

Der Golden Master ``skript-golden-master-aussichten.py`` (trend jahre 1/3/10 auf drei DB-Kopien) und die eine
Bestandsprobe (``test_komponenten_dashboards_monats_fakten.py``) erreichen in ``_degradation_tmy`` zwei Anweisungen
nie (Zeilenspur, Komplexitäts-Paket A2, 23.10.2026): die Begrenzung der fehlenden Monate auf «bis heute» und die
Hochrechnung der restlichen Monate des **laufenden** Jahres. Beide hängen an ``jahr == heute.year`` — ein Jahr, das
zugleich das laufende ist und schon sechs Monate trägt. Diese Probe baut genau das.

Aufbau (gleichmäßig, damit das SOLL nicht vom Kalendermonat abhängt): PVGIS 100 kWh je Monat; Vorjahr Juli–Dezember
je 80 kWh (PR 0,8, aufgefüllt 960 kWh); laufendes Jahr Januar–Juni je 72 kWh (PR 0,72). Für jeden Monat M ≥ 6
füllt die Rechnung Juli…M mit TMY × PR auf und rechnet M+1…12 hoch — zusammen 12 × 72 = 864 kWh, Degradation
(864 − 960) / 960 = −10,0 %/Jahr. Fehlt die Hochrechnung, stünden im Oktober 720 kWh da (−25 %); fehlt die
Begrenzung auf «bis heute», 1 008 kWh (+5 %, gekappt auf 0,0).

Vor Juni gibt es im laufenden Jahr keine sechs vergangenen Monate — der Zweig ist dann nur mit Zukunftsdaten
erreichbar; die Probe überspringt sich (kein Zeit-Fake, Entscheid «freezegun nein»).
"""

from __future__ import annotations

from datetime import date, datetime

import pytest

from backend.api.routes.aussichten import get_trend_analyse
from backend.models import Anlage, Investition, Monatsdaten, Strompreis
from backend.models.pvgis_prognose import PVGISPrognose


async def _anlage_mit_zwei_halben_jahren(db, jahr: int) -> Anlage:
    anlage = Anlage(anlagenname="RF-33 TMY laufendes Jahr", leistung_kwp=10.0, latitude=52.0, longitude=10.0)
    db.add(anlage)
    await db.flush()
    db.add(Strompreis(
        anlage_id=anlage.id, gueltig_ab=date(jahr - 2, 1, 1),
        netzbezug_arbeitspreis_cent_kwh=30.0, einspeiseverguetung_cent_kwh=8.0, grundpreis_euro_monat=0.0,
    ))
    db.add(Investition(anlage_id=anlage.id, typ="pv-module", bezeichnung="Dach", leistung_kwp=10.0,
                       anschaffungsdatum=date(jahr - 2, 1, 1), anschaffungskosten_gesamt=12000.0))
    db.add(PVGISPrognose(
        anlage_id=anlage.id, abgerufen_am=datetime(jahr - 1, 1, 1),
        latitude=52.0, longitude=10.0, neigung_grad=30.0, ausrichtung_grad=0.0,
        system_losses=14.0, jahresertrag_kwh=1200.0,
        spezifischer_ertrag_kwh_kwp=120.0, gesamt_leistung_kwp=10.0,
        monatswerte=[{"monat": m, "e_m": 100.0, "h_m": 0.0, "sd_m": 0.0} for m in range(1, 13)],
        ist_aktiv=True,
    ))
    for monat in range(7, 13):
        db.add(Monatsdaten(anlage_id=anlage.id, jahr=jahr - 1, monat=monat,
                           einspeisung_kwh=30.0, netzbezug_kwh=20.0, pv_erzeugung_kwh=80.0))
    for monat in range(1, 7):
        db.add(Monatsdaten(anlage_id=anlage.id, jahr=jahr, monat=monat,
                           einspeisung_kwh=30.0, netzbezug_kwh=20.0, pv_erzeugung_kwh=72.0))
    await db.commit()
    return anlage


@pytest.mark.asyncio
async def test_tmy_zweig_rechnet_das_laufende_jahr_bis_heute_auf_und_den_rest_hoch(db):
    heute = date.today()
    if heute.month < 6:
        pytest.skip("vor Juni trägt das laufende Jahr keine sechs vergangenen Monate (Zweig nur mit Zukunftsdaten)")
    anlage = await _anlage_mit_zwei_halben_jahren(db, heute.year)

    antwort = await get_trend_analyse(anlage_id=anlage.id, jahre=3, db=db)

    deg = antwort.degradation
    assert deg.methode == "tmy_ergaenzt", "kein vollständiges Jahr ⇒ der TMY-Zweig muss rechnen"
    assert deg.geschaetzt_prozent_jahr == pytest.approx(-10.0), (
        "laufendes Jahr = 12 × 72 = 864 kWh gegen 960 kWh im Vorjahr; −25 % hieße: Hochrechnung fehlt, "
        "0,0 (aus +5 %) hieße: fehlende Monate nicht auf «bis heute» begrenzt"
    )
    assert deg.hinweis == (
        f"TMY-ergänzt aus 2 Jahren ({heute.year - 1}: 6/12 Mon., {heute.year}: 6/12 Mon.)"
        " – Wert mit Vorsicht interpretieren (min. 3 Jahre empfohlen)"
    )
    assert deg.zuverlaessig is False
    assert antwort.datenquellen == ["historische-daten", "pvgis-tmy"]
    laufend = [j for j in antwort.jahres_vergleich if j.jahr == heute.year]
    assert laufend and laufend[0].anzahl_monate == 6 and laufend[0].gesamt_kwh == pytest.approx(432.0)
