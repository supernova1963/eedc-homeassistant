"""N-717 — die Kaskade des Wallbox-Preises bleibt bei ihrer Verwendung: die Zeitfenster-Stufe liest die Fenster des
Wallbox-Tarifs, nicht die des Allgemeintarifs (N-433: der Komponenten-Tarif ist Stufe 4 und geht nicht verloren).

Gemessen am HEAD `0c3a89fa` (acht Monate 07/2025–02/2026, Stundenwerte 0,5 kW Netzbezug in jeder Stunde; E-Auto 1000 km,
90 kWh Netz-, 60 kWh PV-Ladung je Monat; Benzin 1,80 €; Allgemeintarif 30 ct mit Fenster 22–06 Uhr 20 ct, Wallbox-Tarif
25 ct ohne Fenster, beide ab 07/2025): E-Auto-Ersparnis **Cockpit → Übersicht 760,00 · E-Auto-Hub 760,00 ·
HA-Anlagensensoren 760,00 · HA-Sensor je E-Auto 772,00 €**. `monats_fakten._lade_tarif` reichte den Allgemeintarif mit
dem Wallbox-Preis als `stammpreis_override` in die Kaskade; Stufe 3 prüfte die Fenster des Allgemeintarifs und ersetzte
den Wallbox-Tarif durch deren Ø (26,667 ct). Der HA-Sensor je E-Auto lief über eine zweite Kaskade
(`strompreise.monats_strompreis_lookup`, mit dem Wallbox-Tarif) und rechnete richtig.

Soll von Hand: Benzin 8000 km × 7,5 l/100 km × 1,80 € = 1080; Netz 720 kWh × 25 ct = 180 (Wallbox-Tarif); PV 480 kWh ×
26,667 ct = 128 (Preis der Eigenverbrauchs-Ersparnis: der Hauszähler mit seinem Fenster-Ø) ⇒ **772,00 €** in jeder Sicht.

Seit dem Bau gibt es EINE Kaskade: `monats_strompreis_lookup` ist entfernt, der HA-Sensor je E-Auto liest den
Monatspreis der Monats-Fakten (`tarife_der_monate` → `wallbox_preis_effektiv_cent`) wie die übrigen Sichten.

Gegenfälle (der Monatspreis der Schicht je Monat, am HEAD und nach dem Bau gleich): ohne Wallbox-Tarif (der Fenster-Ø
des Hauszählers gilt auch für die Wallbox), gemessener Monats-Ø (Stufe 2 schlägt jeden Tarif), Fenster nur am
Wallbox-Tarif (mit und ohne Stundenwerte).

Schwesterdateien: test_n712_n713_symmetrie_monatspreis.py (Monatspreis der Schicht in allen Sichten, I1),
test_flex_oe_erreicht_alle_sichten.py (gepflegter Ø schlägt den Wallbox-Tarif), test_zeittarif_ht_nt.py (Stufe 3).
"""

from __future__ import annotations

import calendar
from datetime import date

import pytest

from backend.models import Anlage, Investition, Monatsdaten, Strompreis
from backend.models.investition import InvestitionMonatsdaten
from backend.models.strompreis import StrompreisZeitfenster
from backend.models.tages_energie_profil import TagesEnergieProfil

MONATE = [(2025, m) for m in range(7, 13)] + [(2026, 1), (2026, 2)]
#: Fenster-Ø eines Tarifs 30/25 ct mit 22–06 Uhr (8 von 24 Stunden) bei gleichem Netzbezug in jeder Stunde.
OE_ALLGEMEIN = round((16 * 30.0 + 8 * 20.0) / 24, 4)    # 26,6667
OE_WALLBOX = round((16 * 25.0 + 8 * 15.0) / 24, 4)      # 21,6667


def _fenster(preis: float) -> StrompreisZeitfenster:
    return StrompreisZeitfenster(von_stunde=22, bis_stunde=6, arbeitspreis_cent_kwh=preis, wochentage="0123456")


async def _anlage(db, *, allg_fenster: bool, wallbox: str | None, stunden: bool = True,
                  stundenpreis: float | None = None, mit_eauto: bool = True):
    """``wallbox``: None (kein Wallbox-Tarif) · "ohne" (25 ct) · "fenster" (25 ct, 22–06 Uhr 15 ct)."""
    a = Anlage(anlagenname="N717", leistung_kwp=10.0, installationsdatum=date(2025, 7, 1),
               standort_plz="10115", latitude=48.0, longitude=11.0)
    db.add(a)
    await db.flush()
    allg = Strompreis(anlage_id=a.id, netzbezug_arbeitspreis_cent_kwh=30.0, einspeiseverguetung_cent_kwh=8.0,
                      gueltig_ab=date(2025, 7, 1), verwendung="allgemein", anbieter="Werk", tarifname="HT/NT")
    allg.zeitfenster = [_fenster(20.0)] if allg_fenster else []
    db.add(allg)
    if wallbox is not None:
        wb = Strompreis(anlage_id=a.id, netzbezug_arbeitspreis_cent_kwh=25.0, einspeiseverguetung_cent_kwh=8.0,
                        gueltig_ab=date(2025, 7, 1), verwendung="wallbox", anbieter="Werk", tarifname="Wallbox")
        wb.zeitfenster = [_fenster(15.0)] if wallbox == "fenster" else []
        db.add(wb)
    for j, m in MONATE:
        db.add(Monatsdaten(anlage_id=a.id, jahr=j, monat=m, einspeisung_kwh=200.0, netzbezug_kwh=150.0,
                           kraftstoffpreis_euro=1.80))
        if stunden:
            for tag in range(1, calendar.monthrange(j, m)[1] + 1):
                for slot in range(24):
                    db.add(TagesEnergieProfil(anlage_id=a.id, datum=date(j, m, tag), stunde=slot,
                                              netzbezug_kw=0.5, strompreis_cent=stundenpreis))
    ea = None
    if mit_eauto:
        pv = Investition(anlage_id=a.id, typ="pv-module", bezeichnung="PV", anschaffungsdatum=date(2025, 7, 1),
                         anschaffungskosten_gesamt=12000.0, leistung_kwp=10.0)
        ea = Investition(anlage_id=a.id, typ="e-auto", bezeichnung="EA", anschaffungsdatum=date(2025, 7, 1),
                         anschaffungskosten_gesamt=35000.0, anschaffungskosten_alternativ=30000.0, parameter={})
        db.add_all([pv, ea])
        await db.flush()
        for j, m in MONATE:
            db.add(InvestitionMonatsdaten(investition_id=pv.id, jahr=j, monat=m,
                                          verbrauch_daten={"pv_erzeugung_kwh": 500.0}))
            db.add(InvestitionMonatsdaten(investition_id=ea.id, jahr=j, monat=m, verbrauch_daten={
                "km_gefahren": 1000, "verbrauch_kwh": 180.0, "ladung_pv_kwh": 60.0, "ladung_netz_kwh": 90.0}))
    await db.commit()
    return a, ea


#: (Fenster am Allgemeintarif, Wallbox-Tarif, Stundenwerte, Stundenpreis) → Wallbox-Preis der Schicht je Monat (ct).
#: Die ersten zwei sind der Fund (HEAD: 26,6667), die übrigen die Gegenfälle (HEAD = Bau).
WALLBOX_PREIS = {
    "allg_fenster_wallbox_ohne": ((True, "ohne", True, None), 25.0),
    "allg_fenster_wallbox_fenster": ((True, "fenster", True, None), OE_WALLBOX),
    "gegen_ohne_wallbox_tarif": ((True, None, True, None), OE_ALLGEMEIN),
    "gegen_gemessener_oe": ((True, "ohne", True, 22.0), 22.0),
    "gegen_fenster_nur_wallbox": ((False, "fenster", True, None), OE_WALLBOX),
    "gegen_fenster_nur_wallbox_ohne_stunden": ((False, "fenster", False, None), 25.0),
}


@pytest.mark.asyncio
@pytest.mark.parametrize("fall", sorted(WALLBOX_PREIS))
async def test_wallbox_preis_der_schicht_je_verwendung(db, fall):
    from backend.api.routes.investitionen.dashboard_basis import _gewichtete_monatspreise
    from backend.services.monats_fakten import lade_monats_fakten, tarife_der_monate

    (allg_fenster, wallbox, stunden, stundenpreis), soll = WALLBOX_PREIS[fall]
    a, _ = await _anlage(db, allg_fenster=allg_fenster, wallbox=wallbox, stunden=stunden,
                         stundenpreis=stundenpreis, mit_eauto=False)
    t = await tarife_der_monate(db, a.id, MONATE)
    fakten = {(f.jahr, f.monat): f for f in await lade_monats_fakten(db, a.id)}
    hub = await _gewichtete_monatspreise(db, a.id, "wallbox", {k: 1.0 for k in MONATE},
                                         fallback_bezug=99.0, fallback_einspeise=99.0)
    for k in MONATE:
        ist = (t[k].wallbox_preis_effektiv_cent, fakten[k].tarif.wallbox_preis_effektiv_cent, hub.bezug_lookup[k])
        assert ist == (pytest.approx(soll),) * 3, (fall, k, ist)


def _ohne_netz(monkeypatch):
    """Prognose und Börsenpreis der Anlagen-Sensoren gestellt (wie `test_n712_n713_…`) — sie brauchen das Netz."""
    from backend.api.routes.ha_export import anlage_sensorwerte

    async def _leer(*_a, **_k):
        return {}

    monkeypatch.setattr(anlage_sensorwerte, "berechne_prognose_export", _leer)
    monkeypatch.setattr(anlage_sensorwerte, "berechne_preis_export", _leer)


def _spion(monkeypatch, modul, name):
    """Fängt die Rückgabe einer Phase (`_out`-Dict) am echten Aufrufweg ab (wie `test_n712_n713_…`)."""
    import inspect

    original = getattr(modul, name)
    gefangen: dict = {}

    def _sync(*a, **k):
        out = original(*a, **k)
        gefangen.update(out)
        return out

    async def _async(*a, **k):
        out = await original(*a, **k)
        gefangen.update(out)
        return out

    monkeypatch.setattr(modul, name, _async if inspect.iscoroutinefunction(original) else _sync)
    return gefangen


@pytest.mark.asyncio
@pytest.mark.parametrize("fall, soll", [("allg_fenster_wallbox_ohne", 772.00), ("gegen_ohne_wallbox_tarif", 760.00)])
async def test_jede_sicht_nennt_die_eauto_ersparnis_mit_dem_wallbox_tarif(db, monkeypatch, fall, soll):
    """Fund: 772,00 € in jeder Sicht (HEAD: 760,00 außer dem HA-Sensor je E-Auto). Gegenfall ohne Wallbox-Tarif:
    Netz 720 × 26,667 = 192 + PV 128 ⇒ 760,00 € in jeder Sicht (HEAD gleich)."""
    from backend.api.routes import aktueller_monat as amr
    from backend.api.routes.aussichten import finanzen as aussichten_finanzen
    from backend.api.routes.aussichten import get_finanz_prognose
    from backend.api.routes.cockpit.uebersicht import get_cockpit_uebersicht
    from backend.api.routes.ha_export import anlage_sensoren, calculate_investition_sensors
    from backend.api.routes.investitionen.dashboard_eauto import get_eauto_dashboard
    from backend.api.routes.strompreise import lade_tarife_fuer_anlage
    from backend.services.jahres_aggregat import baue_jahr

    (allg_fenster, wallbox, stunden, stundenpreis), _ = WALLBOX_PREIS[fall]
    a, ea = await _anlage(db, allg_fenster=allg_fenster, wallbox=wallbox, stunden=stunden, stundenpreis=stundenpreis)
    _ohne_netz(monkeypatch)
    ha_anlage = _spion(monkeypatch, anlage_sensoren, "alternativkosten_und_co2")
    aussichten = _spion(monkeypatch, aussichten_finanzen, "alternativkosten_rueckblick")

    cockpit = await get_cockpit_uebersicht(a.id, jahr=None, db=db)
    eauto_hub = (await get_eauto_dashboard(a.id, strompreis_cent=None, db=db))[0].zusammenfassung
    tarif = (await lade_tarife_fuer_anlage(db, a.id))["allgemein"]
    ha_ea = next(s.value for s in await calculate_investition_sensors(db, ea, tarif)
                 if s.definition.key == "e_auto_ersparnis_vs_benzin_euro")
    await anlage_sensoren.calculate_anlage_sensors(db, a, skip_jitter=True)
    await get_finanz_prognose(anlage_id=a.id, monate=12, db=db)
    koepfe = [(await baue_jahr(db, a.id, jahr))["kopf"] for jahr in (2025, 2026)]
    koepfe = [k if isinstance(k, dict) else k.model_dump() for k in koepfe]
    tkonto = 0.0
    for j, m in MONATE:
        r = await amr.get_aktueller_monat(anlage_id=a.id, jahr=j, monat=m, db=db)
        tkonto += r.emob_ersparnis_euro or 0.0

    ist = {
        "Cockpit Übersicht": cockpit.emob_ersparnis_euro,
        "Cockpit Jahr": round(sum(k["emob_ersparnis_euro"] for k in koepfe), 2),
        "Cockpit Monat Σ": round(tkonto, 2),
        "E-Auto-Hub": eauto_hub["ersparnis_vs_benzin_euro"],
        "HA-Sensor je E-Auto": round(ha_ea, 2),
        "HA-Anlage": round(ha_anlage["bisherige_eauto_ersparnis"], 2),
        "Aussichten": round(aussichten["bisherige_eauto_ersparnis"], 2),
    }
    abweichend = {k: v for k, v in ist.items() if v is None or v != pytest.approx(soll, abs=0.005)}
    assert not abweichend, f"{fall}: Sicht ≠ {soll}: {abweichend}"
