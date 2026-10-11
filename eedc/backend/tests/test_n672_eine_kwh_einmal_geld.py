"""N-672 — die PV-Ladung des E-Autos ist einmal Geld, nicht zweimal.

**Der Defekt.** Die Eigenverbrauchs-Ersparnis bewertet den ganzen Eigenverbrauch der
Anlage zum Strompreis — der Strom, den das E-Auto aus der Anlage lädt, steckt darin.
Die E-Auto-Ersparnis gegenüber dem Verbrenner setzte dieselbe PV-Ladung zusätzlich
„kostenlos" an. Gemessen am HEAD `aad49a34` (K6, 11.10.2026) an genau dieser Anlage:
*Auswertungen → ROI* 399,50 € (PV-System 212,00 + E-Auto 187,50), *Cockpit → Jahr*
dieselben Posten.

**Die Regel** (Entscheid Master 11.10.2026, `core/berechnungen/heimladung_kosten.py`):
die PV-Ladung trägt den Preis, zu dem die Eigenverbrauchs-Ersparnis derselben Sicht sie
gutschreibt. Gegenrechnung gegen die Referenz „ohne PV, mit Verbrenner": Erlös 32,00 +
Eigenverbrauch 600 kWh × 30 ct + Benzin 247,50 − **ganze** Ladung 400 kWh × 30 ct =
**339,50 €**, davon E-Auto 247,50 − 120,00 = **127,50 €**. Dieselbe Regel für CO₂: die
PV-CO₂ schreibt den ganzen Eigenverbrauch gut, also belastet das E-Auto die ganze Ladung
mit dem Strommix.

**Warum die Probe rot werden kann:** am HEAD vor dem Bau lieferten ROI und Cockpit → Jahr
187,50 € für die E-Auto-Zeile (K6 Etappe 1b) — jede Sicht, die die PV-Ladung wieder
kostenlos setzt, landet dort und nicht bei 127,50. Die Sichten werden gesammelt statt
einzeln assertet, damit eine Abweichung alle übrigen nicht verdeckt.
"""

from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import select

from backend.models import Anlage, Investition, Monatsdaten, Strompreis
from backend.models.investition import InvestitionMonatsdaten

JAHR = 2025
PV_KWH, EINSPEISUNG_KWH = 1000.0, 400.0
LADUNG_KWH, LADUNG_PV_KWH = 400.0, 200.0
PREIS_CENT, VERGUETUNG_CENT = 30.0, 8.0
KM, KWH_100KM, L_100KM, BENZIN_EURO = 2000.0, 20.0, 7.5, 1.65

#: Benzin 2000 km × 7,5 l/100 km × 1,65 € = 247,50 € − 400 kWh × 30 ct = 120,00 €.
EAUTO_EURO = 127.50
#: PV-System: Erlös 400 × 8 ct = 32,00 + Eigenverbrauch 600 × 30 ct = 180,00.
PV_SYSTEM_EURO = 212.00
GESAMT_EURO = 339.50
#: 150 l × 2,37 kg − 400 kWh × 0,38 kg (die GANZE Ladung, N-672) = 203,5 kg.
EAUTO_CO2_KG = 203.5


async def _anlage(db) -> tuple[int, int]:
    """Die Beispielanlage aus K6: ein Jahr, zwölf gleiche Monate, PV-Ladeanteil 50 %."""
    anlage = Anlage(
        anlagenname="N672", leistung_kwp=1.0, standort_plz="10115",
        latitude=48.0, longitude=11.0, installationsdatum=date(2024, 1, 1),
    )
    db.add(anlage)
    await db.flush()
    db.add(Strompreis(
        anlage_id=anlage.id, gueltig_ab=date(2020, 1, 1),
        netzbezug_arbeitspreis_cent_kwh=PREIS_CENT, einspeiseverguetung_cent_kwh=VERGUETUNG_CENT,
    ))
    wr = Investition(anlage_id=anlage.id, typ="wechselrichter", bezeichnung="WR",
                     anschaffungsdatum=date(2024, 1, 1), anschaffungskosten_gesamt=1000.0)
    db.add(wr)
    await db.flush()
    pv = Investition(anlage_id=anlage.id, typ="pv-module", bezeichnung="PV",
                     anschaffungsdatum=date(2024, 1, 1), anschaffungskosten_gesamt=2000.0,
                     leistung_kwp=1.0, parent_investition_id=wr.id)
    ea = Investition(
        anlage_id=anlage.id, typ="e-auto", bezeichnung="EA",
        anschaffungsdatum=date(2024, 1, 1), anschaffungskosten_gesamt=30000.0,
        parameter={
            "jahresfahrleistung_km": KM, "verbrauch_kwh_100km": KWH_100KM,
            "pv_ladeanteil_prozent": 50.0, "vergleich_verbrauch_l_100km": L_100KM,
            "benzinpreis_euro": BENZIN_EURO,
        },
    )
    db.add_all([pv, ea])
    await db.flush()
    for monat in range(1, 13):
        db.add(Monatsdaten(
            anlage_id=anlage.id, jahr=JAHR, monat=monat,
            einspeisung_kwh=EINSPEISUNG_KWH / 12,
            netzbezug_kwh=(2000.0 + LADUNG_KWH - LADUNG_PV_KWH) / 12,
        ))
        db.add(InvestitionMonatsdaten(
            investition_id=pv.id, jahr=JAHR, monat=monat,
            verbrauch_daten={"pv_erzeugung_kwh": PV_KWH / 12},
        ))
        db.add(InvestitionMonatsdaten(
            investition_id=ea.id, jahr=JAHR, monat=monat,
            verbrauch_daten={
                "ladung_kwh": LADUNG_KWH / 12, "ladung_pv_kwh": LADUNG_PV_KWH / 12,
                "ladung_netz_kwh": (LADUNG_KWH - LADUNG_PV_KWH) / 12, "km_gefahren": KM / 12,
            },
        ))
    await db.commit()
    return anlage.id, ea.id


async def test_roi_und_cockpit_jahr_nennen_dieselbe_zahl_ohne_doppelzaehlung(db):
    from backend.api.routes.cockpit.uebersicht import get_cockpit_uebersicht
    from backend.api.routes.investitionen.roi import get_roi_dashboard

    anlage_id, ea_id = await _anlage(db)
    roi = await get_roi_dashboard(
        anlage_id, strompreis_cent=None, einspeiseverguetung_cent=None,
        benzinpreis_euro=None, jahr=JAHR, db=db,
    )
    cockpit = await get_cockpit_uebersicht(anlage_id, jahr=JAHR, db=db)
    eauto = next(b for b in roi.berechnungen if b.investition_typ == "e-auto")
    pv_system = next(b for b in roi.berechnungen if b.investition_typ == "pv-system")

    ist = {
        "ROI gesamt": roi.gesamt_jahres_einsparung,
        "ROI E-Auto": eauto.jahres_einsparung,
        "ROI PV-System": pv_system.jahres_einsparung,
        "ROI E-Auto Stromkosten": eauto.detail_berechnung["strom_kosten_euro"],
        "Cockpit → Jahr Netto-Ertrag": cockpit.netto_ertrag_euro,
        "Cockpit → Jahr E-Mobilität": cockpit.emob_ersparnis_euro,
    }
    soll = {
        "ROI gesamt": GESAMT_EURO,
        "ROI E-Auto": EAUTO_EURO,
        "ROI PV-System": PV_SYSTEM_EURO,
        "ROI E-Auto Stromkosten": 120.00,
        "Cockpit → Jahr Netto-Ertrag": PV_SYSTEM_EURO,
        "Cockpit → Jahr E-Mobilität": EAUTO_EURO,
    }
    abweichungen = {k: (ist[k], soll[k]) for k in soll if abs(ist[k] - soll[k]) > 0.01}
    assert not abweichungen, abweichungen


async def test_roi_e_auto_co2_belastet_die_ganze_ladung(db):
    """Eine kWh ist einmal CO₂: die PV-CO₂ der Anlage schreibt die PV-Ladung schon gut."""
    from backend.api.routes.investitionen.roi import get_roi_dashboard

    anlage_id, _ = await _anlage(db)
    roi = await get_roi_dashboard(
        anlage_id, strompreis_cent=None, einspeiseverguetung_cent=None,
        benzinpreis_euro=None, jahr=JAHR, db=db,
    )
    eauto = next(b for b in roi.berechnungen if b.investition_typ == "e-auto")
    # Am HEAD vor dem Bau: 355,5 − 200 × 0,38 = 279,5 kg (nur der Netzanteil belastet).
    assert eauto.co2_einsparung_kg == pytest.approx(EAUTO_CO2_KG, abs=0.05)


async def test_die_ist_sichten_belasten_die_pv_ladung_gleich(db):
    """Cockpit → Monat (Σ zwölf T-Konten), E-Auto-Hub, HA-Export und Aussichten — dieselbe Regel."""
    from backend.api.routes.aktueller_monat import get_aktueller_monat
    from backend.api.routes.aussichten import get_finanz_prognose
    from backend.api.routes.ha_export import calculate_anlage_sensors, calculate_investition_sensors
    from backend.api.routes.ha_export.emob import _load_emob_pool_ctx
    from backend.api.routes.investitionen import get_eauto_dashboard

    anlage_id, ea_id = await _anlage(db)
    monate = [
        await get_aktueller_monat(anlage_id=anlage_id, jahr=JAHR, monat=m, db=db)
        for m in range(1, 13)
    ]
    hub = await get_eauto_dashboard(anlage_id=anlage_id, db=db)
    invs = (await db.execute(
        select(Investition).where(Investition.anlage_id == anlage_id)
    )).scalars().all()
    ea = next(i for i in invs if i.id == ea_id)
    ctx = await _load_emob_pool_ctx(db, invs)
    sensor = next(
        s.value for s in await calculate_investition_sensors(db, ea, None, emob_ctx=ctx)
        if s.definition.key == "e_auto_ersparnis_vs_benzin_euro"
    )
    anlage = await db.get(Anlage, anlage_id)
    anlage_sensoren = {s.definition.key: s for s in await calculate_anlage_sensors(db, anlage, skip_jitter=True)}
    aussichten = await get_finanz_prognose(anlage_id=anlage_id, monate=12, db=db)

    ist = {
        "Cockpit → Monat Σ": round(sum(m.emob_ersparnis_euro or 0 for m in monate), 2),
        "Hub": hub[0].zusammenfassung["ersparnis_vs_benzin_euro"],
        "Hub Stromkosten PV": hub[0].zusammenfassung["strom_kosten_pv_euro"],
        "HA-Export Fahrzeug": sensor,
        "HA-Export Anlage (Rechenweg)": anlage_sensoren["jahres_ersparnis_euro"].berechnung,
        "Aussichten E-Auto-Beitrag": next(
            k.beitrag_euro_jahr for k in aussichten.komponenten_beitraege if k.typ == "e-auto-benzin"
        ),
    }
    soll = {
        "Cockpit → Monat Σ": EAUTO_EURO,
        "Hub": EAUTO_EURO,
        "Hub Stromkosten PV": 60.00,
        "HA-Export Fahrzeug": EAUTO_EURO,
        "HA-Export Anlage (Rechenweg)": None,  # unten: der E-Auto-Posten im Rechenweg
        "Aussichten E-Auto-Beitrag": EAUTO_EURO,
    }
    # Cockpit → Monat rundet jeden Monat auf Cent (10,625 → 10,62); zwölf Monate liegen bis zu 12 ct neben dem
    # Jahreswert — eine Rundung, keine Regel.
    toleranz = {"Cockpit → Monat Σ": 0.12}
    abweichungen = {
        k: (ist[k], soll[k]) for k in soll
        if soll[k] is not None and abs(ist[k] - soll[k]) > toleranz.get(k, 0.01)
    }
    assert not abweichungen, abweichungen
    assert "127,50" in ist["HA-Export Anlage (Rechenweg)"], ist["HA-Export Anlage (Rechenweg)"]


async def test_gemessenes_co2_belastet_die_ganze_heimladung_in_drei_sichten(db):
    """Eine kWh ist einmal CO₂ (N-672, Entscheid Master 11.10.2026): Übersicht, Nachhaltigkeit und HA-Sensor.

    E-Mobilität: 150 l × 2,37 kg − 400 kWh × 0,38 kg = **203,5 kg** (vorher nur die 200 kWh Netz: 279,5 kg).
    PV: Eigenverbrauch 600 kWh × 0,38 kg = 228,0 kg ⇒ Gesamt **431,5 kg** (vorher 507,5 kg).
    """
    from backend.api.routes.cockpit.nachhaltigkeit import get_nachhaltigkeit
    from backend.api.routes.cockpit.uebersicht import get_cockpit_uebersicht
    from backend.api.routes.ha_export import calculate_anlage_sensors

    anlage_id, _ = await _anlage(db)
    uebersicht = await get_cockpit_uebersicht(anlage_id, jahr=JAHR, db=db)
    nachhaltigkeit = await get_nachhaltigkeit(anlage_id=anlage_id, db=db)  # ganze Historie = das eine Jahr
    anlage = await db.get(Anlage, anlage_id)
    ha = next(
        s.value for s in await calculate_anlage_sensors(db, anlage, skip_jitter=True)
        if s.definition.key == "co2_ersparnis_kg"
    )
    ist = {
        "Übersicht E-Mob": uebersicht.co2_emob_kg,
        "Nachhaltigkeit E-Mob": nachhaltigkeit.co2_emob_kg,
        "Übersicht gesamt": uebersicht.co2_gesamt_kg,
        "Nachhaltigkeit gesamt": nachhaltigkeit.co2_gesamt_kg,
        "HA-Sensor gesamt": ha,
    }
    soll = {
        "Übersicht E-Mob": 203.5, "Nachhaltigkeit E-Mob": 203.5,
        "Übersicht gesamt": 431.5, "Nachhaltigkeit gesamt": 431.5, "HA-Sensor gesamt": 431.5,
    }
    abweichungen = {k: (ist[k], soll[k]) for k in soll if abs(ist[k] - soll[k]) > 0.05}
    assert not abweichungen, abweichungen
