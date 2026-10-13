"""RF-17 — vier Fälle des Wärmepumpen-Hubs, die weder die übrige Suite noch die Golden-Master-Bestände erreichen.

Der Schnitt von ``get_waermepumpe_dashboard`` (RF-17, Serie „Funktion vor Datei", 13.10.2026) ist ein reiner Umzug. Die Vorlage
(§4.6/§4.7) hat gemessen, dass drei Zweige sonst ungedeckt bleiben (Sprengsätze S7, S8, S15 der Vorlage still):

* **F1** — ein kaputter und ein fremder Geräteschlüssel in ``komponenten_starts`` werden übersprungen
  (``_starts_des_tages``/``_stunden_des_tages``: ``except ⇒ continue``, ``wp is None``); die Verhältnisse kommen aus
  den richtigen Summen.
* **F2** — ein Monat ohne Wärme und ohne Strom trägt keinen Vergleich: ohne andere Monate bleibt die Ersparnis
  „nicht bewertet" (F-42, ``_bewertung``).
* **F2b** — ``<= 0``, nicht ``== 0``: ein Korrekturmonat mit negativem Strom und ohne Wärme fließt nicht in die Kosten.
* **F3** — ein gepflegter Gaspreis des Monats (Anlagen-Monat) hat Vorrang vor dem Geräte-Parameter (``_bewertung``).

Schwesterdateien: test_wp_dashboard_betriebsstunden.py (Starts/Betriebsstunden, #238), test_f41_f42_klima_bewertbarkeit.py
(F-42 „nicht bewertet"), test_n712_n713_symmetrie_monatspreis.py (Monatspreis der Monats-Fakten), test_rf16_eauto_dashboard_faelle.py
(dieselbe Fall-Probe für den E-Auto-Hub).
"""
from datetime import date

from backend.api.routes.investitionen.dashboard_waermepumpe import get_waermepumpe_dashboard
from backend.models import Anlage, Investition, Monatsdaten
from backend.models.investition import InvestitionMonatsdaten
from backend.models.tages_energie_profil import TagesZusammenfassung

_GAS = {"wp_art": "luft_wasser", "effizienz_modus": "gesamt_jaz",
        "alter_energietraeger": "gas", "alter_preis_cent_kwh": 10}


async def _wp(db, daten_je_monat: dict[int, dict]) -> tuple[Anlage, Investition]:
    a = Anlage(anlagenname="RF-17", leistung_kwp=10.0, installationsdatum=date(2025, 1, 1))
    db.add(a)
    await db.flush()
    wp = Investition(anlage_id=a.id, typ="waermepumpe", bezeichnung="WP", anschaffungsdatum=date(2025, 1, 1),
                     anschaffungskosten_gesamt=12000.0, parameter=dict(_GAS))
    db.add(wp)
    await db.flush()
    for monat, daten in daten_je_monat.items():
        db.add(InvestitionMonatsdaten(investition_id=wp.id, jahr=2025, monat=monat, verbrauch_daten=daten))
    await db.flush()
    return a, wp


async def test_f1_kaputter_und_fremder_schluessel_im_tageszaehler_werden_uebersprungen(db):
    a, wp = await _wp(db, {7: {"stromverbrauch_kwh": 100.0, "heizenergie_kwh": 300.0}})
    db.add(TagesZusammenfassung(anlage_id=a.id, datum=date(2025, 7, 2), komponenten_starts={
        "wp_starts_anzahl": {"kaputt": 9, "999999": 11, str(wp.id): 7},
        "wp_betriebsstunden": {"kaputt": 9.0, "999999": 11.0, str(wp.id): 2.5},
    }))
    await db.flush()
    z = (await get_waermepumpe_dashboard(a.id, strompreis_cent=None, db=db))[0].zusammenfassung
    assert z["kompressor_starts_summe_erfasst"] == 7
    assert z["betriebsstunden_summe_erfasst"] == 2.5
    assert z["oe_laufzeit_pro_start_h"] == round(2.5 / 7, 2)


async def test_f2_monat_ohne_waerme_und_strom_traegt_keinen_vergleich(db):
    a, _ = await _wp(db, {7: {"stromverbrauch_kwh": 0.0, "heizenergie_kwh": 0.0}})
    z = (await get_waermepumpe_dashboard(a.id, strompreis_cent=None, db=db))[0].zusammenfassung
    assert z["wp_kosten_euro"] == 0.0
    assert z["ersparnis_euro"] is None
    assert z["alte_heizung_kosten_euro"] is None
    assert z["co2_ersparnis_kg"] is None


async def test_f3_gepflegter_gaspreis_des_monats_gilt_vor_dem_parameter(db):
    a, _ = await _wp(db, {7: {"stromverbrauch_kwh": 100.0, "heizenergie_kwh": 300.0}})
    db.add(Monatsdaten(anlage_id=a.id, jahr=2025, monat=7, einspeisung_kwh=0, netzbezug_kwh=0, gaspreis_cent_kwh=20.0))
    await db.flush()
    mit = (await get_waermepumpe_dashboard(a.id, strompreis_cent=None, db=db))[0].zusammenfassung
    md = (await db.execute(__import__("sqlalchemy").select(Monatsdaten).where(Monatsdaten.anlage_id == a.id))).scalar_one()
    md.gaspreis_cent_kwh = None
    await db.flush()
    ohne = (await get_waermepumpe_dashboard(a.id, strompreis_cent=None, db=db))[0].zusammenfassung
    # 20 ct statt 10 ct: die Alt-Kosten verdoppeln sich (Wirkungsgrad und Zusatzkosten stehen in beiden gleich).
    assert mit["alte_heizung_kosten_euro"] is not None and ohne["alte_heizung_kosten_euro"] is not None
    assert mit["alte_heizung_kosten_euro"] > ohne["alte_heizung_kosten_euro"]
    assert mit["wp_kosten_euro"] == ohne["wp_kosten_euro"]


async def test_f2b_negativer_korrekturmonat_ohne_waerme_wird_nicht_bewertet(db):
    """`<= 0`, nicht `== 0`: ein Monat mit negativem Strom und ohne Wärme (Zähler-Korrektur) fließt nicht in die Kosten."""
    a, _ = await _wp(db, {6: {"stromverbrauch_kwh": 100.0, "heizenergie_kwh": 300.0},
                         7: {"stromverbrauch_kwh": -10.0, "heizenergie_kwh": 0.0}})
    nur_juni = (await get_waermepumpe_dashboard(a.id, strompreis_cent=None, db=db))[0].zusammenfassung
    a2, _ = await _wp(db, {6: {"stromverbrauch_kwh": 100.0, "heizenergie_kwh": 300.0}})
    referenz = (await get_waermepumpe_dashboard(a2.id, strompreis_cent=None, db=db))[0].zusammenfassung
    assert nur_juni["wp_kosten_euro"] == referenz["wp_kosten_euro"]
    assert nur_juni["ersparnis_euro"] == referenz["ersparnis_euro"]
