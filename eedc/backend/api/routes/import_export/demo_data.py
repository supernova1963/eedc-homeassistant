"""
Demo-Daten Operations

Erstellen und Löschen von Demo-Daten für Tests und Präsentationen.
"""

from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps import get_db
from backend.models.anlage import Anlage
from backend.models.monatsdaten import Monatsdaten
from backend.models.investition import Investition, InvestitionMonatsdaten
from backend.models.strompreis import Strompreis
from backend.models.pvgis_prognose import PVGISPrognose as PVGISPrognoseModel, PVGISMonatsprognose

from .schemas import DemoDataResult

router = APIRouter()

# Demo-Monatsdaten (Juni 2023 - Dezember 2025)
# Globalstrahlung und Sonnenstunden: Typische Werte für Wien (48.2°N)
DEMO_MONATSDATEN = [
    # Jahr, Monat, Einspeisung, Netzbezug, PV_Erzeugung, Batt_Ladung, Batt_Entladung,
    # EAuto_km, EAuto_Verbrauch, EAuto_PV, EAuto_Netz, EAuto_Extern_kWh, EAuto_Extern_Euro, V2H,
    # WP_Strom, WP_Heizung, WP_Warmwasser, Globalstrahlung_kWh_m2, Sonnenstunden
    (2023, 6, 517.08, 1.84, 668.54, 70.3, 50.56, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 165.2, 248),
    (2023, 7, 1179.67, 4.43, 1571.53, 176.82, 151.21, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 172.8, 275),
    (2023, 8, 1014.27, 4.88, 1400.24, 194.34, 166.74, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 148.5, 245),
    (2023, 9, 1273.4, 4.24, 1622.29, 194.61, 167.49, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 112.3, 185),
    (2023, 10, 471.98, 38.65, 804.61, 215.27, 202.08, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 68.4, 125),
    (2023, 11, 82.14, 154.84, 294.28, 141.48, 135.77, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 32.1, 58),
    (2023, 12, 10.92, 364.96, 171.8, 85.01, 73.92, 650, 125, 10, 115, 0, 0, 0, 180, 720, 90, 22.5, 42),
    (2024, 1, 122.81, 333.59, 432.86, 165.3, 148.69, 1186, 237.27, 37, 175, 25, 12.50, 0, 320, 1280, 120, 28.3, 55),
    (2024, 2, 164.35, 261.82, 476.23, 183.07, 164.65, 959, 191.81, 91, 80, 20, 10.00, 0, 290, 1160, 110, 48.7, 85),
    (2024, 3, 461.1, 122.08, 979.25, 247.51, 233.23, 1201, 240.35, 200, 41, 0, 0, 0, 240, 960, 100, 89.2, 142),
    (2024, 4, 564.72, 25.45, 1140.2, 226.08, 214.78, 1032, 206.55, 201, 6, 0, 0, 0, 180, 720, 90, 128.5, 195),
    (2024, 5, 873.29, 22.82, 1475.49, 225.59, 212.61, 1002, 200.58, 195, 5, 0, 0, 0, 120, 480, 85, 158.3, 228),
    (2024, 6, 1036.34, 10.31, 1559.33, 199.62, 192.79, 717, 143.43, 140, 3, 0, 0, 0, 80, 320, 80, 168.7, 255),
    (2024, 7, 1120.43, 12.1, 1657.77, 194.21, 183.88, 851, 170.36, 165, 6, 0, 0, 0, 70, 280, 75, 175.4, 282),
    (2024, 8, 1228.31, 43.6, 1772.38, 195.89, 184.81, 1119, 223.8, 150, 24, 50, 27.50, 0, 75, 300, 78, 152.1, 252),
    (2024, 9, 781.13, 10.48, 1244.02, 202.86, 191.13, 659, 131.82, 100, 31, 0, 0, 0, 95, 380, 82, 108.6, 178),
    (2024, 10, 262.54, 88.54, 761.48, 271.57, 257.8, 876, 175.26, 110, 50, 15, 8.25, 0, 150, 600, 95, 65.2, 118),
    (2024, 11, 135.33, 303.18, 379.7, 134.7, 116.05, 758, 151.69, 52, 75, 25, 13.75, 25, 280, 1120, 105, 29.8, 52),
    (2024, 12, 35.29, 357.37, 227.94, 88.81, 68.01, 564, 112.86, 12, 70, 30, 16.50, 35, 350, 1400, 115, 20.1, 38),
    (2025, 1, 115.61, 373.9, 383.3, 157.3, 115.83, 974, 194.96, 24, 130, 40, 22.00, 40, 380, 1520, 125, 25.7, 48),
    (2025, 2, 319.24, 165.63, 781.89, 236.56, 184.74, 1111, 222.29, 32, 155, 35, 19.25, 45, 340, 1360, 115, 52.4, 92),
    (2025, 3, 1106.2, 114.73, 1647.26, 291.98, 236.09, 621, 124.23, 74, 50, 0, 0, 30, 280, 1120, 105, 95.8, 155),
    (2025, 4, 1115.4, 46.09, 1734.5, 256.47, 200.62, 1036, 207.35, 167, 41, 0, 0, 25, 200, 800, 95, 135.2, 205),
    (2025, 5, 1171.87, 16.82, 1837.58, 254.87, 205.58, 193, 38.66, 35, 4, 0, 0, 15, 140, 560, 85, 162.7, 238),
    (2025, 6, 1318.13, 9.43, 1884.72, 210.36, 154.59, 651, 130.25, 115, 15, 0, 0, 20, 90, 360, 80, 171.3, 262),
    (2025, 7, 1051.23, 9.73, 1642.45, 233.19, 189.15, 801, 160.38, 120, 20, 20, 11.00, 18, 75, 300, 75, 168.9, 268),
    (2025, 8, 1117.5, 10.1, 1727.63, 247.98, 193.78, 857, 171.53, 140, 21, 10, 5.50, 22, 80, 320, 78, 155.6, 258),
    (2025, 9, 721.12, 18.3, 1172.37, 242.38, 194.34, 323, 64.61, 54, 10, 0, 0, 12, 110, 440, 85, 105.2, 172),
    (2025, 10, 132.83, 229.36, 569.49, 247.04, 205.23, 1118, 223.67, 100, 89, 35, 19.25, 38, 180, 720, 98, 62.8, 112),
    (2025, 11, 173.16, 185.21, 541.48, 206.04, 165.63, 574, 114.94, 40, 55, 20, 11.00, 28, 300, 1200, 108, 31.5, 55),
    (2025, 12, 125.91, 405.5, 432.72, 168.77, 132.41, 1205, 241.17, 21, 175, 45, 24.75, 42, 370, 1480, 118, 18.9, 35),
]


@router.post("/demo", response_model=DemoDataResult)
async def create_demo_data(db: AsyncSession = Depends(get_db)):
    """
    Erstellt eine komplette Demo-Anlage mit allen Daten.

    Beinhaltet:
    - PV-Anlage (20 kWp, 3 Strings)
    - Speicher (15 kWh)
    - E-Auto (Tesla Model 3) mit V2H
    - Wärmepumpe (Heizung + Warmwasser)
    - Wallbox (11 kW)
    - Balkonkraftwerk (800 Wp mit Speicher)
    - Sonstiges: Mini-BHKW (Erzeuger)
    - Strompreise (2023-2025)
    - 31 Monate Monatsdaten (Juni 2023 - Dezember 2025)
    """
    # Prüfen ob Demo-Anlage bereits existiert
    existing = await db.execute(
        select(Anlage).where(Anlage.anlagenname == "Demo-Anlage")
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=400,
            detail="Demo-Anlage existiert bereits. Bitte zuerst löschen."
        )

    # 1. Anlage erstellen (Standort: München - für DWD/Bright Sky Verfügbarkeit)
    anlage = Anlage(
        anlagenname="Demo-Anlage",
        leistung_kwp=20.0,
        installationsdatum=date(2023, 6, 1),
        standort_plz="80331",
        standort_ort="München",
        standort_strasse="Marienplatz 1",
        ausrichtung="Süd",
        neigung_grad=30.0,
        latitude=48.137,  # München Zentrum
        longitude=11.575,
        wetter_provider="auto",  # Wird automatisch Bright Sky (DWD) wählen
    )
    db.add(anlage)
    await db.flush()

    # 2. Strompreise erstellen
    strompreise = [
        Strompreis(
            anlage_id=anlage.id,
            netzbezug_arbeitspreis_cent_kwh=28.5,
            einspeiseverguetung_cent_kwh=8.2,  # EEG-Vergütung für Anlagen <10kWp
            grundpreis_euro_monat=12.0,
            gueltig_ab=date(2023, 6, 1),
            gueltig_bis=date(2024, 3, 31),
            tarifname="Standardtarif 2023",
            anbieter="Stadtwerke München",
        ),
        Strompreis(
            anlage_id=anlage.id,
            netzbezug_arbeitspreis_cent_kwh=32.0,
            einspeiseverguetung_cent_kwh=8.2,
            grundpreis_euro_monat=13.5,
            gueltig_ab=date(2024, 4, 1),
            gueltig_bis=date(2024, 12, 31),
            tarifname="Standardtarif 2024",
            anbieter="Stadtwerke München",
        ),
        Strompreis(
            anlage_id=anlage.id,
            netzbezug_arbeitspreis_cent_kwh=30.0,
            einspeiseverguetung_cent_kwh=8.1,
            grundpreis_euro_monat=14.0,
            gueltig_ab=date(2025, 1, 1),
            gueltig_bis=None,
            tarifname="M-Strom Privat",
            anbieter="Stadtwerke München",
        ),
    ]
    for sp in strompreise:
        db.add(sp)

    # 3. Investitionen erstellen
    # Wechselrichter
    wechselrichter = Investition(
        anlage_id=anlage.id,
        typ="wechselrichter",
        bezeichnung="Fronius Symo GEN24 10.0 Plus",
        anschaffungsdatum=date(2023, 6, 1),
        anschaffungskosten_gesamt=3500,
        parameter={
            "hersteller": "fronius",
            "max_leistung_kw": 10,
            "hybrid": True,
            "notstromfaehig": True,
            "phasen": 3,
        },
        aktiv=True,
    )
    db.add(wechselrichter)
    await db.flush()

    # DC-Speicher
    speicher = Investition(
        anlage_id=anlage.id,
        typ="speicher",
        bezeichnung="BYD HVS 15.4",
        anschaffungsdatum=date(2023, 6, 1),
        anschaffungskosten_gesamt=12000,
        parent_investition_id=wechselrichter.id,
        parameter={
            "kapazitaet_kwh": 15.4,
            "max_ladeleistung_kw": 10,
            "max_entladeleistung_kw": 10,
            "wirkungsgrad_prozent": 95,
            "typ": "dc",
            "arbitrage_faehig": True,
        },
        aktiv=True,
    )
    db.add(speicher)

    # E-Auto
    eauto = Investition(
        anlage_id=anlage.id,
        typ="e-auto",
        bezeichnung="Tesla Model 3 LR",
        anschaffungsdatum=date(2023, 12, 1),
        anschaffungskosten_gesamt=52000,
        anschaffungskosten_alternativ=35000,
        parameter={
            "km_jahr": 12000,
            "verbrauch_kwh_100km": 18,
            "pv_anteil_prozent": 60,
            "benzinpreis_euro": 1.65,
            "vergleich_verbrauch_l_100km": 7.5,
            "nutzt_v2h": True,
            "v2h_entlade_preis_cent": 25,
            "batterie_kapazitaet_kwh": 75,
        },
        aktiv=True,
    )
    db.add(eauto)

    # Wärmepumpe
    waermepumpe = Investition(
        anlage_id=anlage.id,
        typ="waermepumpe",
        bezeichnung="Daikin Altherma 3 H HT",
        anschaffungsdatum=date(2024, 4, 1),
        anschaffungskosten_gesamt=18000,
        anschaffungskosten_alternativ=8000,
        betriebskosten_jahr=200,
        parameter={
            "leistung_kw": 12,
            "effizienz_modus": "getrennte_cops",
            "cop_heizung": 3.9,
            "cop_warmwasser": 3.0,
            "heizwaermebedarf_kwh": 12000,
            "warmwasserbedarf_kwh": 3000,
            "pv_anteil_prozent": 35,
            "alter_energietraeger": "gas",
            "alter_preis_cent_kwh": 12,
            "sg_ready": True,
        },
        aktiv=True,
    )
    db.add(waermepumpe)

    # Wallbox
    wallbox = Investition(
        anlage_id=anlage.id,
        typ="wallbox",
        bezeichnung="go-eCharger HOMEfix 11kW",
        anschaffungsdatum=date(2023, 12, 1),
        anschaffungskosten_gesamt=800,
        parameter={
            "ladeleistung_kw": 11,
            "phasen": 3,
        },
        aktiv=True,
    )
    db.add(wallbox)

    # PV-Module (3 Strings)
    pv_sued = Investition(
        anlage_id=anlage.id,
        typ="pv-module",
        bezeichnung="Süddach",
        anschaffungsdatum=date(2023, 6, 1),
        anschaffungskosten_gesamt=15000,
        leistung_kwp=12.0,
        ausrichtung="Süd",
        neigung_grad=30,
        parent_investition_id=wechselrichter.id,
        parameter={
            "anzahl_module": 24,
            "modul_typ": "Longi Hi-MO 5",
            "modul_leistung_wp": 500,
            "ausrichtung_grad": 0,    # Süd = 0° für GTI
            "neigung_grad": 30,
        },
        aktiv=True,
    )
    db.add(pv_sued)

    pv_ost = Investition(
        anlage_id=anlage.id,
        typ="pv-module",
        bezeichnung="Ostdach",
        anschaffungsdatum=date(2023, 6, 1),
        anschaffungskosten_gesamt=5000,
        leistung_kwp=5.0,
        ausrichtung="Ost",
        neigung_grad=25,
        parent_investition_id=wechselrichter.id,
        parameter={
            "anzahl_module": 10,
            "modul_typ": "Longi Hi-MO 5",
            "modul_leistung_wp": 500,
            "ausrichtung_grad": -90,  # Ost = -90° für GTI
            "neigung_grad": 25,
        },
        aktiv=True,
    )
    db.add(pv_ost)

    pv_west = Investition(
        anlage_id=anlage.id,
        typ="pv-module",
        bezeichnung="Westdach",
        anschaffungsdatum=date(2023, 6, 1),
        anschaffungskosten_gesamt=4000,
        leistung_kwp=3.0,
        ausrichtung="West",
        neigung_grad=25,
        parent_investition_id=wechselrichter.id,
        parameter={
            "anzahl_module": 6,
            "modul_typ": "Longi Hi-MO 5",
            "modul_leistung_wp": 500,
            "ausrichtung_grad": 90,   # West = 90° für GTI
            "neigung_grad": 25,
        },
        aktiv=True,
    )
    db.add(pv_west)

    # Balkonkraftwerk
    balkonkraftwerk = Investition(
        anlage_id=anlage.id,
        typ="balkonkraftwerk",
        bezeichnung="Balkon Süd",
        anschaffungsdatum=date(2024, 3, 1),
        anschaffungskosten_gesamt=1200,
        leistung_kwp=0.8,  # 2x 400Wp = 800Wp = 0.8 kWp
        parameter={
            "leistung_wp": 400,
            "anzahl": 2,
            "ausrichtung_grad": 0,    # Süd = 0° für GTI-Berechnung
            "neigung_grad": 35,
            "hat_speicher": True,
            "speicher_kapazitaet_wh": 1024,
        },
        aktiv=True,
    )
    db.add(balkonkraftwerk)

    # Mini-BHKW
    mini_bhkw = Investition(
        anlage_id=anlage.id,
        typ="sonstiges",
        bezeichnung="Mini-BHKW",
        anschaffungsdatum=date(2024, 10, 1),
        anschaffungskosten_gesamt=8000,
        betriebskosten_jahr=300,
        parameter={
            "kategorie": "erzeuger",
            "beschreibung": "Blockheizkraftwerk für Strom und Wärme, Erdgas-betrieben",
        },
        aktiv=True,
    )
    db.add(mini_bhkw)

    await db.flush()

    # 4. Monatsdaten erstellen
    monatsdaten_count = 0
    for row in DEMO_MONATSDATEN:
        (jahr, monat, einspeisung, netzbezug, pv_erzeugung, batt_ladung, batt_entladung,
         eauto_km, eauto_verbrauch, eauto_pv, eauto_netz, eauto_extern_kwh, eauto_extern_euro, v2h,
         wp_strom, wp_heizung, wp_warmwasser, globalstrahlung, sonnenstunden) = row

        # Monatsdaten (nur Zählerwerte - PV-Erzeugung kommt aus InvestitionMonatsdaten)
        md = Monatsdaten(
            anlage_id=anlage.id,
            jahr=jahr,
            monat=monat,
            einspeisung_kwh=einspeisung,
            netzbezug_kwh=netzbezug,
            globalstrahlung_kwh_m2=globalstrahlung,
            sonnenstunden=sonnenstunden,
            datenquelle="demo",
        )
        db.add(md)
        monatsdaten_count += 1

        # E-Auto Monatsdaten
        if eauto_km > 0:
            eauto_verbrauch_daten = {
                "km_gefahren": eauto_km,
                "verbrauch_kwh": eauto_verbrauch,
                "ladung_pv_kwh": eauto_pv,
                "ladung_netz_kwh": eauto_netz,
                "v2h_entladung_kwh": v2h,
            }
            if eauto_extern_kwh > 0:
                eauto_verbrauch_daten["ladung_extern_kwh"] = eauto_extern_kwh
                eauto_verbrauch_daten["ladung_extern_euro"] = eauto_extern_euro

            if monat == 4:
                eauto_verbrauch_daten["sonderkosten_euro"] = 120.0
                eauto_verbrauch_daten["sonderkosten_notiz"] = "Reifenwechsel Sommer"
            elif monat == 11 and jahr == 2024:
                eauto_verbrauch_daten["sonderkosten_euro"] = 250.0
                eauto_verbrauch_daten["sonderkosten_notiz"] = "Jahresservice"

            db.add(InvestitionMonatsdaten(
                investition_id=eauto.id,
                jahr=jahr,
                monat=monat,
                verbrauch_daten=eauto_verbrauch_daten,
            ))

        # Speicher Monatsdaten
        if batt_ladung > 0:
            speicher_daten = {
                "ladung_kwh": batt_ladung,
                "entladung_kwh": batt_entladung,
            }
            if jahr >= 2025:
                arbitrage_anteil = 0.15 + (monat % 3) * 0.05
                speicher_daten["speicher_ladung_netz_kwh"] = round(batt_ladung * arbitrage_anteil, 1)
                speicher_daten["speicher_ladepreis_cent"] = round(18 + (monat % 4) * 2, 1)

            if jahr == 2025 and monat == 3:
                speicher_daten["sonderkosten_euro"] = 95.0
                speicher_daten["sonderkosten_notiz"] = "Firmware-Update"

            db.add(InvestitionMonatsdaten(
                investition_id=speicher.id,
                jahr=jahr,
                monat=monat,
                verbrauch_daten=speicher_daten,
            ))

        # Wärmepumpe Monatsdaten
        if wp_strom > 0:
            wp_daten = {
                "stromverbrauch_kwh": wp_strom,
                "heizenergie_kwh": wp_heizung,
                "warmwasser_kwh": wp_warmwasser,
            }
            if monat == 10:
                wp_daten["sonderkosten_euro"] = 180.0
                wp_daten["sonderkosten_notiz"] = "Jahreswartung"

            db.add(InvestitionMonatsdaten(
                investition_id=waermepumpe.id,
                jahr=jahr,
                monat=monat,
                verbrauch_daten=wp_daten,
            ))

        # Balkonkraftwerk Monatsdaten
        if jahr > 2024 or (jahr == 2024 and monat >= 3):
            bkw_skalierung = 0.04
            bkw_erzeugung = round(pv_erzeugung * bkw_skalierung, 1)
            bkw_eigenverbrauch = round(bkw_erzeugung * 0.95, 1)
            bkw_speicher_ladung = round(bkw_erzeugung * 0.3, 1)
            bkw_speicher_entladung = round(bkw_speicher_ladung * 0.92, 1)

            db.add(InvestitionMonatsdaten(
                investition_id=balkonkraftwerk.id,
                jahr=jahr,
                monat=monat,
                verbrauch_daten={
                    "pv_erzeugung_kwh": bkw_erzeugung,
                    "eigenverbrauch_kwh": bkw_eigenverbrauch,
                    "speicher_ladung_kwh": bkw_speicher_ladung,
                    "speicher_entladung_kwh": bkw_speicher_entladung,
                },
            ))

        # Mini-BHKW Monatsdaten
        if (jahr == 2024 and monat >= 10) or jahr > 2024:
            if monat in [1, 2, 3, 10, 11, 12]:
                bhkw_erzeugung = 120 + (monat % 3) * 30
            else:
                bhkw_erzeugung = 30 + (monat % 2) * 10

            db.add(InvestitionMonatsdaten(
                investition_id=mini_bhkw.id,
                jahr=jahr,
                monat=monat,
                verbrauch_daten={"erzeugung_kwh": bhkw_erzeugung},
            ))

        # PV-Module InvestitionMonatsdaten
        if pv_erzeugung > 0:
            if monat in [5, 6, 7]:
                sued_anteil, ost_anteil, west_anteil = 0.55, 0.27, 0.18
            elif monat in [11, 12, 1, 2]:
                sued_anteil, ost_anteil, west_anteil = 0.70, 0.18, 0.12
            else:
                sued_anteil, ost_anteil, west_anteil = 0.60, 0.24, 0.16

            for pv_inv, anteil in [(pv_sued, sued_anteil), (pv_ost, ost_anteil), (pv_west, west_anteil)]:
                db.add(InvestitionMonatsdaten(
                    investition_id=pv_inv.id,
                    jahr=jahr,
                    monat=monat,
                    verbrauch_daten={"pv_erzeugung_kwh": round(pv_erzeugung * anteil, 1)},
                ))

        # Wallbox Monatsdaten
        if eauto_km > 0:
            heimladung = eauto_pv + eauto_netz
            db.add(InvestitionMonatsdaten(
                investition_id=wallbox.id,
                jahr=jahr,
                monat=monat,
                verbrauch_daten={
                    "ladung_kwh": heimladung,
                    "ladevorgaenge": max(4, int(heimladung / 25)),
                },
            ))

    # 5. PVGIS Prognose
    pvgis_monatswerte = [
        {"monat": 1, "e_m": 680, "h_m": 32.5, "sd_m": 85},
        {"monat": 2, "e_m": 1020, "h_m": 52.8, "sd_m": 115},
        {"monat": 3, "e_m": 1650, "h_m": 95.2, "sd_m": 145},
        {"monat": 4, "e_m": 2150, "h_m": 128.5, "sd_m": 165},
        {"monat": 5, "e_m": 2480, "h_m": 158.2, "sd_m": 175},
        {"monat": 6, "e_m": 2620, "h_m": 168.5, "sd_m": 155},
        {"monat": 7, "e_m": 2750, "h_m": 175.8, "sd_m": 160},
        {"monat": 8, "e_m": 2450, "h_m": 152.5, "sd_m": 145},
        {"monat": 9, "e_m": 1850, "h_m": 112.8, "sd_m": 125},
        {"monat": 10, "e_m": 1180, "h_m": 68.5, "sd_m": 105},
        {"monat": 11, "e_m": 680, "h_m": 35.2, "sd_m": 75},
        {"monat": 12, "e_m": 490, "h_m": 25.5, "sd_m": 65},
    ]
    jahresertrag = sum(m["e_m"] for m in pvgis_monatswerte)
    spezifischer_ertrag = jahresertrag / 20.0

    pvgis_prognose = PVGISPrognoseModel(
        anlage_id=anlage.id,
        latitude=48.2,
        longitude=16.4,
        neigung_grad=28.0,
        ausrichtung_grad=-10.0,
        system_losses=14.0,
        jahresertrag_kwh=jahresertrag,
        spezifischer_ertrag_kwh_kwp=spezifischer_ertrag,
        monatswerte=pvgis_monatswerte,
        ist_aktiv=True,
    )
    db.add(pvgis_prognose)
    await db.flush()

    for m in pvgis_monatswerte:
        db.add(PVGISMonatsprognose(
            prognose_id=pvgis_prognose.id,
            monat=m["monat"],
            ertrag_kwh=m["e_m"],
            einstrahlung_kwh_m2=m["h_m"],
            standardabweichung_kwh=m["sd_m"],
        ))

    return DemoDataResult(
        erfolg=True,
        anlage_id=anlage.id,
        anlage_name=anlage.anlagenname,
        monatsdaten_count=monatsdaten_count,
        investitionen_count=10,
        strompreise_count=3,
        message=f"Demo-Anlage mit {monatsdaten_count} Monatsdaten, 10 Investitionen und 3 Strompreisen erstellt.",
    )


@router.delete("/demo", response_model=dict)
async def delete_demo_data(db: AsyncSession = Depends(get_db)):
    """Löscht die Demo-Anlage und alle zugehörigen Daten."""
    result = await db.execute(
        select(Anlage).where(Anlage.anlagenname == "Demo-Anlage")
    )
    anlage = result.scalar_one_or_none()

    if not anlage:
        raise HTTPException(status_code=404, detail="Demo-Anlage nicht gefunden")

    await db.delete(anlage)
    await db.commit()

    return {"message": "Demo-Anlage und alle zugehörigen Daten gelöscht"}
