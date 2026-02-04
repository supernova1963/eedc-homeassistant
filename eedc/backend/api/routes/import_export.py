"""
Import/Export API Routes

CSV-Import und Export-Funktionen.
"""

from io import StringIO
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel
import csv

from backend.api.deps import get_db
from backend.models.anlage import Anlage
from backend.models.monatsdaten import Monatsdaten
from backend.models.investition import Investition, InvestitionMonatsdaten
from backend.models.strompreis import Strompreis


# =============================================================================
# Pydantic Schemas
# =============================================================================

class ImportResult(BaseModel):
    """Ergebnis eines CSV-Imports."""
    erfolg: bool
    importiert: int
    uebersprungen: int
    fehler: list[str]


class DemoDataResult(BaseModel):
    """Ergebnis der Demo-Daten Erstellung."""
    erfolg: bool
    anlage_id: int
    anlage_name: str
    monatsdaten_count: int
    investitionen_count: int
    strompreise_count: int
    message: str


class CSVTemplateInfo(BaseModel):
    """Info über das CSV-Template."""
    spalten: list[str]
    beschreibung: dict[str, str]


# =============================================================================
# Router
# =============================================================================

router = APIRouter()


@router.get("/template/{anlage_id}", response_model=CSVTemplateInfo)
async def get_csv_template_info(anlage_id: int, db: AsyncSession = Depends(get_db)):
    """
    Gibt Informationen über das CSV-Template für eine Anlage zurück.

    Das Template ist dynamisch und enthält zusätzliche Spalten basierend
    auf den vorhandenen Investitionen.

    Args:
        anlage_id: ID der Anlage

    Returns:
        CSVTemplateInfo: Spalten und Beschreibungen

    Raises:
        404: Anlage nicht gefunden
    """
    # Anlage prüfen
    anlage_result = await db.execute(select(Anlage).where(Anlage.id == anlage_id))
    if not anlage_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Anlage nicht gefunden")

    # Basis-Spalten
    spalten = ["Jahr", "Monat", "Einspeisung_kWh", "Netzbezug_kWh", "PV_Erzeugung_kWh"]
    beschreibung = {
        "Jahr": "Jahr (z.B. 2024)",
        "Monat": "Monat (1-12)",
        "Einspeisung_kWh": "Ins Netz eingespeiste Energie",
        "Netzbezug_kWh": "Aus dem Netz bezogene Energie",
        "PV_Erzeugung_kWh": "Gesamte PV-Erzeugung (optional, wird berechnet wenn leer)",
    }

    # Investitionen laden
    inv_result = await db.execute(
        select(Investition).where(Investition.anlage_id == anlage_id, Investition.aktiv == True)
    )
    investitionen = inv_result.scalars().all()

    # Dynamische Spalten je nach Investitionstyp
    for inv in investitionen:
        if inv.typ == "speicher":
            spalten.extend(["Batterie_Ladung_kWh", "Batterie_Entladung_kWh"])
            beschreibung["Batterie_Ladung_kWh"] = "In Batterie geladene Energie"
            beschreibung["Batterie_Entladung_kWh"] = "Aus Batterie entladene Energie"

            # Arbitrage-Spalten wenn aktiviert
            if inv.parameter and inv.parameter.get("nutzt_arbitrage"):
                spalten.extend(["Batterie_Ladung_Netz_kWh", "Batterie_Ladepreis_Cent"])
                beschreibung["Batterie_Ladung_Netz_kWh"] = "Aus Netz geladene Energie (Arbitrage)"
                beschreibung["Batterie_Ladepreis_Cent"] = "Durchschnittlicher Ladepreis"

        elif inv.typ == "e-auto":
            spalten.extend(["EAuto_km", "EAuto_Verbrauch_kWh", "EAuto_Ladung_PV_kWh", "EAuto_Ladung_Netz_kWh"])
            beschreibung["EAuto_km"] = "Gefahrene Kilometer"
            beschreibung["EAuto_Verbrauch_kWh"] = "Gesamtverbrauch"
            beschreibung["EAuto_Ladung_PV_kWh"] = "Mit PV geladen"
            beschreibung["EAuto_Ladung_Netz_kWh"] = "Mit Netzstrom geladen"

            # V2H-Spalte wenn aktiviert
            if inv.parameter and inv.parameter.get("nutzt_v2h"):
                spalten.append("EAuto_V2H_kWh")
                beschreibung["EAuto_V2H_kWh"] = "V2H Entladung ins Haus"

        elif inv.typ == "waermepumpe":
            spalten.extend(["WP_Heizung_kWh", "WP_Warmwasser_kWh", "WP_Strom_kWh"])
            beschreibung["WP_Heizung_kWh"] = "Erzeugte Heizenergie"
            beschreibung["WP_Warmwasser_kWh"] = "Erzeugte Warmwasserenergie"
            beschreibung["WP_Strom_kWh"] = "Stromverbrauch WP"

        elif inv.typ == "wallbox":
            spalten.extend(["Wallbox_Ladung_kWh", "Wallbox_Ladevorgaenge"])
            beschreibung["Wallbox_Ladung_kWh"] = "Gesamte Ladung über Wallbox"
            beschreibung["Wallbox_Ladevorgaenge"] = "Anzahl Ladevorgänge"

    # Optionale Spalten am Ende
    spalten.extend(["Globalstrahlung_kWh_m2", "Sonnenstunden", "Notizen"])
    beschreibung["Globalstrahlung_kWh_m2"] = "Globalstrahlung (optional)"
    beschreibung["Sonnenstunden"] = "Sonnenstunden (optional)"
    beschreibung["Notizen"] = "Notizen (optional)"

    # Duplikate entfernen (falls mehrere gleiche Investitionen)
    seen = set()
    unique_spalten = []
    for s in spalten:
        if s not in seen:
            seen.add(s)
            unique_spalten.append(s)

    return CSVTemplateInfo(spalten=unique_spalten, beschreibung=beschreibung)


@router.get("/template/{anlage_id}/download")
async def download_csv_template(anlage_id: int, db: AsyncSession = Depends(get_db)):
    """
    Lädt ein CSV-Template für eine Anlage herunter.

    Args:
        anlage_id: ID der Anlage

    Returns:
        CSV-Datei als Download
    """
    template_info = await get_csv_template_info(anlage_id, db)

    output = StringIO()
    writer = csv.writer(output, delimiter=";")
    writer.writerow(template_info.spalten)

    # Beispielzeile
    beispiel = []
    for spalte in template_info.spalten:
        if spalte == "Jahr":
            beispiel.append("2024")
        elif spalte == "Monat":
            beispiel.append("1")
        elif "kWh" in spalte:
            beispiel.append("0")
        elif spalte == "Notizen":
            beispiel.append("")
        else:
            beispiel.append("0")
    writer.writerow(beispiel)

    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=eedc_template_{anlage_id}.csv"}
    )


@router.post("/csv/{anlage_id}", response_model=ImportResult)
async def import_csv(
    anlage_id: int,
    file: UploadFile = File(...),
    ueberschreiben: bool = Query(False, description="Existierende Monate überschreiben"),
    db: AsyncSession = Depends(get_db)
):
    """
    Importiert Monatsdaten aus einer CSV-Datei.

    Args:
        anlage_id: ID der Anlage
        file: CSV-Datei
        ueberschreiben: Wenn True, werden existierende Monate überschrieben

    Returns:
        ImportResult: Ergebnis des Imports
    """
    # Anlage prüfen
    anlage_result = await db.execute(select(Anlage).where(Anlage.id == anlage_id))
    if not anlage_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Anlage nicht gefunden")

    # CSV lesen
    try:
        content = await file.read()
        text = content.decode("utf-8-sig")  # BOM handling
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Fehler beim Lesen der Datei: {e}")

    # CSV parsen - automatische Trennzeichen-Erkennung (Semikolon oder Komma)
    # Prüfe erste Zeile auf Trennzeichen
    first_line = text.split('\n')[0] if text else ''
    delimiter = ';' if ';' in first_line else ','

    reader = csv.DictReader(StringIO(text), delimiter=delimiter)

    importiert = 0
    uebersprungen = 0
    fehler = []

    for i, row in enumerate(reader, start=2):  # Zeile 2 (nach Header)
        try:
            # Pflichtfelder
            jahr = int(row.get("Jahr", "").strip())
            monat = int(row.get("Monat", "").strip())

            if not (2000 <= jahr <= 2100):
                fehler.append(f"Zeile {i}: Ungültiges Jahr {jahr}")
                continue
            if not (1 <= monat <= 12):
                fehler.append(f"Zeile {i}: Ungültiger Monat {monat}")
                continue

            # Existierenden Eintrag prüfen
            existing = await db.execute(
                select(Monatsdaten).where(
                    Monatsdaten.anlage_id == anlage_id,
                    Monatsdaten.jahr == jahr,
                    Monatsdaten.monat == monat
                )
            )
            existing_md = existing.scalar_one_or_none()

            if existing_md and not ueberschreiben:
                uebersprungen += 1
                continue

            # Werte parsen (deutsche Zahlenformate)
            def parse_float(val: str) -> Optional[float]:
                if not val or not val.strip():
                    return None
                val = val.strip().replace(",", ".")
                return float(val)

            einspeisung = parse_float(row.get("Einspeisung_kWh", "")) or 0
            netzbezug = parse_float(row.get("Netzbezug_kWh", "")) or 0
            pv_erzeugung = parse_float(row.get("PV_Erzeugung_kWh", ""))
            batterie_ladung = parse_float(row.get("Batterie_Ladung_kWh", ""))
            batterie_entladung = parse_float(row.get("Batterie_Entladung_kWh", ""))
            globalstrahlung = parse_float(row.get("Globalstrahlung_kWh_m2", ""))
            sonnenstunden = parse_float(row.get("Sonnenstunden", ""))
            notizen = row.get("Notizen", "").strip() or None

            if existing_md:
                # Update
                existing_md.einspeisung_kwh = einspeisung
                existing_md.netzbezug_kwh = netzbezug
                existing_md.pv_erzeugung_kwh = pv_erzeugung
                existing_md.batterie_ladung_kwh = batterie_ladung
                existing_md.batterie_entladung_kwh = batterie_entladung
                existing_md.globalstrahlung_kwh_m2 = globalstrahlung
                existing_md.sonnenstunden = sonnenstunden
                existing_md.notizen = notizen
                existing_md.datenquelle = "csv"
            else:
                # Neu anlegen
                md = Monatsdaten(
                    anlage_id=anlage_id,
                    jahr=jahr,
                    monat=monat,
                    einspeisung_kwh=einspeisung,
                    netzbezug_kwh=netzbezug,
                    pv_erzeugung_kwh=pv_erzeugung,
                    batterie_ladung_kwh=batterie_ladung,
                    batterie_entladung_kwh=batterie_entladung,
                    globalstrahlung_kwh_m2=globalstrahlung,
                    sonnenstunden=sonnenstunden,
                    notizen=notizen,
                    datenquelle="csv"
                )

                # Berechnete Felder
                if pv_erzeugung:
                    md.direktverbrauch_kwh = max(0, pv_erzeugung - einspeisung - (batterie_ladung or 0))
                    md.eigenverbrauch_kwh = md.direktverbrauch_kwh + (batterie_entladung or 0)
                    md.gesamtverbrauch_kwh = md.eigenverbrauch_kwh + netzbezug

                db.add(md)

            importiert += 1

        except ValueError as e:
            fehler.append(f"Zeile {i}: Ungültiger Wert - {e}")
        except Exception as e:
            fehler.append(f"Zeile {i}: Fehler - {e}")

    return ImportResult(
        erfolg=len(fehler) == 0,
        importiert=importiert,
        uebersprungen=uebersprungen,
        fehler=fehler[:20]  # Max 20 Fehler anzeigen
    )


@router.get("/export/{anlage_id}")
async def export_csv(
    anlage_id: int,
    jahr: Optional[int] = Query(None, description="Filter nach Jahr"),
    db: AsyncSession = Depends(get_db)
):
    """
    Exportiert Monatsdaten als CSV.

    Args:
        anlage_id: ID der Anlage
        jahr: Optional - nur dieses Jahr exportieren

    Returns:
        CSV-Datei als Download
    """
    # Anlage prüfen
    anlage_result = await db.execute(select(Anlage).where(Anlage.id == anlage_id))
    anlage = anlage_result.scalar_one_or_none()
    if not anlage:
        raise HTTPException(status_code=404, detail="Anlage nicht gefunden")

    # Monatsdaten laden
    query = select(Monatsdaten).where(Monatsdaten.anlage_id == anlage_id)
    if jahr:
        query = query.where(Monatsdaten.jahr == jahr)
    query = query.order_by(Monatsdaten.jahr, Monatsdaten.monat)

    result = await db.execute(query)
    monatsdaten = result.scalars().all()

    # CSV erstellen
    output = StringIO()
    writer = csv.writer(output, delimiter=";")

    # Header
    header = [
        "Jahr", "Monat", "Einspeisung_kWh", "Netzbezug_kWh", "PV_Erzeugung_kWh",
        "Direktverbrauch_kWh", "Eigenverbrauch_kWh", "Gesamtverbrauch_kWh",
        "Batterie_Ladung_kWh", "Batterie_Entladung_kWh",
        "Globalstrahlung_kWh_m2", "Sonnenstunden", "Notizen"
    ]
    writer.writerow(header)

    # Daten
    for md in monatsdaten:
        row = [
            md.jahr,
            md.monat,
            md.einspeisung_kwh,
            md.netzbezug_kwh,
            md.pv_erzeugung_kwh or "",
            md.direktverbrauch_kwh or "",
            md.eigenverbrauch_kwh or "",
            md.gesamtverbrauch_kwh or "",
            md.batterie_ladung_kwh or "",
            md.batterie_entladung_kwh or "",
            md.globalstrahlung_kwh_m2 or "",
            md.sonnenstunden or "",
            md.notizen or ""
        ]
        writer.writerow(row)

    output.seek(0)
    filename = f"eedc_export_{anlage.anlagenname}_{jahr or 'alle'}.csv"

    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


# =============================================================================
# Demo-Daten
# =============================================================================

# Demo-Monatsdaten (Juni 2023 - Dezember 2025)
# Erweitert um externe Ladung (EAuto_Extern_kWh, EAuto_Extern_Euro)
DEMO_MONATSDATEN = [
    # Jahr, Monat, Einspeisung, Netzbezug, PV_Erzeugung, Batt_Ladung, Batt_Entladung,
    # EAuto_km, EAuto_Verbrauch, EAuto_PV, EAuto_Netz, EAuto_Extern_kWh, EAuto_Extern_Euro, V2H,
    # WP_Strom, WP_Heizung, WP_Warmwasser
    (2023, 6, 517.08, 1.84, 668.54, 70.3, 50.56, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0),
    (2023, 7, 1179.67, 4.43, 1571.53, 176.82, 151.21, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0),
    (2023, 8, 1014.27, 4.88, 1400.24, 194.34, 166.74, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0),
    (2023, 9, 1273.4, 4.24, 1622.29, 194.61, 167.49, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0),
    (2023, 10, 471.98, 38.65, 804.61, 215.27, 202.08, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0),
    (2023, 11, 82.14, 154.84, 294.28, 141.48, 135.77, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0),
    (2023, 12, 10.92, 364.96, 171.8, 85.01, 73.92, 650, 125, 10, 115, 0, 0, 0, 180, 720, 90),
    (2024, 1, 122.81, 333.59, 432.86, 165.3, 148.69, 1186, 237.27, 37, 175, 25, 12.50, 0, 320, 1280, 120),
    (2024, 2, 164.35, 261.82, 476.23, 183.07, 164.65, 959, 191.81, 91, 80, 20, 10.00, 0, 290, 1160, 110),
    (2024, 3, 461.1, 122.08, 979.25, 247.51, 233.23, 1201, 240.35, 200, 41, 0, 0, 0, 240, 960, 100),
    (2024, 4, 564.72, 25.45, 1140.2, 226.08, 214.78, 1032, 206.55, 201, 6, 0, 0, 0, 180, 720, 90),
    (2024, 5, 873.29, 22.82, 1475.49, 225.59, 212.61, 1002, 200.58, 195, 5, 0, 0, 0, 120, 480, 85),
    (2024, 6, 1036.34, 10.31, 1559.33, 199.62, 192.79, 717, 143.43, 140, 3, 0, 0, 0, 80, 320, 80),
    (2024, 7, 1120.43, 12.1, 1657.77, 194.21, 183.88, 851, 170.36, 165, 6, 0, 0, 0, 70, 280, 75),
    (2024, 8, 1228.31, 43.6, 1772.38, 195.89, 184.81, 1119, 223.8, 150, 24, 50, 27.50, 0, 75, 300, 78),
    (2024, 9, 781.13, 10.48, 1244.02, 202.86, 191.13, 659, 131.82, 100, 31, 0, 0, 0, 95, 380, 82),
    (2024, 10, 262.54, 88.54, 761.48, 271.57, 257.8, 876, 175.26, 110, 50, 15, 8.25, 0, 150, 600, 95),
    (2024, 11, 135.33, 303.18, 379.7, 134.7, 116.05, 758, 151.69, 52, 75, 25, 13.75, 25, 280, 1120, 105),
    (2024, 12, 35.29, 357.37, 227.94, 88.81, 68.01, 564, 112.86, 12, 70, 30, 16.50, 35, 350, 1400, 115),
    (2025, 1, 115.61, 373.9, 383.3, 157.3, 115.83, 974, 194.96, 24, 130, 40, 22.00, 40, 380, 1520, 125),
    (2025, 2, 319.24, 165.63, 781.89, 236.56, 184.74, 1111, 222.29, 32, 155, 35, 19.25, 45, 340, 1360, 115),
    (2025, 3, 1106.2, 114.73, 1647.26, 291.98, 236.09, 621, 124.23, 74, 50, 0, 0, 30, 280, 1120, 105),
    (2025, 4, 1115.4, 46.09, 1734.5, 256.47, 200.62, 1036, 207.35, 167, 41, 0, 0, 25, 200, 800, 95),
    (2025, 5, 1171.87, 16.82, 1837.58, 254.87, 205.58, 193, 38.66, 35, 4, 0, 0, 15, 140, 560, 85),
    (2025, 6, 1318.13, 9.43, 1884.72, 210.36, 154.59, 651, 130.25, 115, 15, 0, 0, 20, 90, 360, 80),
    (2025, 7, 1051.23, 9.73, 1642.45, 233.19, 189.15, 801, 160.38, 120, 20, 20, 11.00, 18, 75, 300, 75),
    (2025, 8, 1117.5, 10.1, 1727.63, 247.98, 193.78, 857, 171.53, 140, 21, 10, 5.50, 22, 80, 320, 78),
    (2025, 9, 721.12, 18.3, 1172.37, 242.38, 194.34, 323, 64.61, 54, 10, 0, 0, 12, 110, 440, 85),
    (2025, 10, 132.83, 229.36, 569.49, 247.04, 205.23, 1118, 223.67, 100, 89, 35, 19.25, 38, 180, 720, 98),
    (2025, 11, 173.16, 185.21, 541.48, 206.04, 165.63, 574, 114.94, 40, 55, 20, 11.00, 28, 300, 1200, 108),
    (2025, 12, 125.91, 405.5, 432.72, 168.77, 132.41, 1205, 241.17, 21, 175, 45, 24.75, 42, 370, 1480, 118),
]


@router.post("/demo", response_model=DemoDataResult)
async def create_demo_data(db: AsyncSession = Depends(get_db)):
    """
    Erstellt eine komplette Demo-Anlage mit allen Daten.

    Beinhaltet:
    - PV-Anlage (20 kWp)
    - Speicher (15 kWh)
    - E-Auto (Tesla Model 3) mit V2H
    - Wärmepumpe (Heizung + Warmwasser)
    - Wallbox (11 kW)
    - Strompreise (2023-2025)
    - 31 Monate Monatsdaten (Juni 2023 - Dezember 2025)

    Returns:
        DemoDataResult: Zusammenfassung der erstellten Daten
    """
    from datetime import date

    # Prüfen ob Demo-Anlage bereits existiert
    existing = await db.execute(
        select(Anlage).where(Anlage.anlagenname == "Demo-Anlage")
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=400,
            detail="Demo-Anlage existiert bereits. Bitte zuerst löschen."
        )

    # 1. Anlage erstellen
    anlage = Anlage(
        anlagenname="Demo-Anlage",
        leistung_kwp=20.0,
        installationsdatum=date(2023, 6, 1),
        standort_plz="1220",
        standort_ort="Wien",
        ausrichtung="Süd",
        neigung_grad=30.0,
        latitude=48.2,
        longitude=16.4,
    )
    db.add(anlage)
    await db.flush()  # ID generieren

    # 2. Strompreise erstellen
    strompreise = [
        Strompreis(
            anlage_id=anlage.id,
            netzbezug_arbeitspreis_cent_kwh=28.5,
            einspeiseverguetung_cent_kwh=7.5,
            grundpreis_euro_monat=12.0,
            gueltig_ab=date(2023, 6, 1),
            gueltig_bis=date(2024, 3, 31),
            tarifname="Standardtarif 2023",
            anbieter="Wien Energie",
        ),
        Strompreis(
            anlage_id=anlage.id,
            netzbezug_arbeitspreis_cent_kwh=32.0,
            einspeiseverguetung_cent_kwh=8.0,
            grundpreis_euro_monat=13.5,
            gueltig_ab=date(2024, 4, 1),
            gueltig_bis=date(2024, 12, 31),
            tarifname="Standardtarif 2024",
            anbieter="Wien Energie",
        ),
        Strompreis(
            anlage_id=anlage.id,
            netzbezug_arbeitspreis_cent_kwh=30.0,
            einspeiseverguetung_cent_kwh=7.0,
            grundpreis_euro_monat=14.0,
            gueltig_ab=date(2025, 1, 1),
            gueltig_bis=None,  # aktuell gültig
            tarifname="Dynamischer Tarif 2025",
            anbieter="Wien Energie",
        ),
    ]
    for sp in strompreise:
        db.add(sp)

    # 3. Investitionen erstellen
    # Speicher
    speicher = Investition(
        anlage_id=anlage.id,
        typ="speicher",
        bezeichnung="BYD HVS 15.4",
        anschaffungsdatum=date(2023, 6, 1),
        anschaffungskosten_gesamt=12000,
        parameter={
            "kapazitaet_kwh": 15.4,
            "max_ladeleistung_kw": 10,
            "max_entladeleistung_kw": 10,
            "wirkungsgrad_prozent": 95,
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
        anschaffungskosten_alternativ=35000,  # Verbrenner-Alternative
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
        anschaffungskosten_alternativ=8000,  # Gas-/Ölheizung
        betriebskosten_jahr=200,
        parameter={
            "heizlast_kw": 12,
            "cop_durchschnitt": 4.0,
            "warmwasser_anteil_prozent": 15,
            "gas_kwh_preis_cent": 12,
            "gas_verbrauch_alt_kwh": 18000,
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

    # PV-Module (für PVGIS Prognose)
    # Süddach - Hauptfläche
    pv_sued = Investition(
        anlage_id=anlage.id,
        typ="pv-module",
        bezeichnung="Süddach",
        anschaffungsdatum=date(2023, 6, 1),
        anschaffungskosten_gesamt=15000,
        leistung_kwp=12.0,
        ausrichtung="Süd",
        neigung_grad=30,
        parameter={
            "anzahl_module": 24,
            "modul_typ": "Longi Hi-MO 5",
            "modul_leistung_wp": 500,
        },
        aktiv=True,
    )
    db.add(pv_sued)

    # Ostdach
    pv_ost = Investition(
        anlage_id=anlage.id,
        typ="pv-module",
        bezeichnung="Ostdach",
        anschaffungsdatum=date(2023, 6, 1),
        anschaffungskosten_gesamt=5000,
        leistung_kwp=5.0,
        ausrichtung="Ost",
        neigung_grad=25,
        parameter={
            "anzahl_module": 10,
            "modul_typ": "Longi Hi-MO 5",
            "modul_leistung_wp": 500,
        },
        aktiv=True,
    )
    db.add(pv_ost)

    # Westdach
    pv_west = Investition(
        anlage_id=anlage.id,
        typ="pv-module",
        bezeichnung="Westdach",
        anschaffungsdatum=date(2023, 6, 1),
        anschaffungskosten_gesamt=4000,
        leistung_kwp=3.0,
        ausrichtung="West",
        neigung_grad=25,
        parameter={
            "anzahl_module": 6,
            "modul_typ": "Longi Hi-MO 5",
            "modul_leistung_wp": 500,
        },
        aktiv=True,
    )
    db.add(pv_west)

    await db.flush()

    # 4. Monatsdaten erstellen
    monatsdaten_count = 0
    for row in DEMO_MONATSDATEN:
        (jahr, monat, einspeisung, netzbezug, pv_erzeugung, batt_ladung, batt_entladung,
         eauto_km, eauto_verbrauch, eauto_pv, eauto_netz, eauto_extern_kwh, eauto_extern_euro, v2h,
         wp_strom, wp_heizung, wp_warmwasser) = row

        # Berechnete Felder
        direktverbrauch = max(0, pv_erzeugung - einspeisung - batt_ladung)
        eigenverbrauch = direktverbrauch + batt_entladung
        gesamtverbrauch = eigenverbrauch + netzbezug

        md = Monatsdaten(
            anlage_id=anlage.id,
            jahr=jahr,
            monat=monat,
            einspeisung_kwh=einspeisung,
            netzbezug_kwh=netzbezug,
            pv_erzeugung_kwh=pv_erzeugung,
            direktverbrauch_kwh=direktverbrauch,
            eigenverbrauch_kwh=eigenverbrauch,
            gesamtverbrauch_kwh=gesamtverbrauch,
            batterie_ladung_kwh=batt_ladung if batt_ladung > 0 else None,
            batterie_entladung_kwh=batt_entladung if batt_entladung > 0 else None,
            datenquelle="demo",
        )
        db.add(md)
        monatsdaten_count += 1

        # E-Auto Monatsdaten (ab Dezember 2023)
        if eauto_km > 0:
            eauto_verbrauch_daten = {
                "km_gefahren": eauto_km,
                "verbrauch_kwh": eauto_verbrauch,
                "ladung_pv_kwh": eauto_pv,
                "ladung_netz_kwh": eauto_netz,
                "v2h_entladung_kwh": v2h,
            }
            # Externe Ladung hinzufügen wenn vorhanden
            if eauto_extern_kwh > 0:
                eauto_verbrauch_daten["ladung_extern_kwh"] = eauto_extern_kwh
                eauto_verbrauch_daten["ladung_extern_euro"] = eauto_extern_euro

            eauto_md = InvestitionMonatsdaten(
                investition_id=eauto.id,
                jahr=jahr,
                monat=monat,
                verbrauch_daten=eauto_verbrauch_daten,
            )
            db.add(eauto_md)

        # Speicher Monatsdaten
        if batt_ladung > 0:
            speicher_md = InvestitionMonatsdaten(
                investition_id=speicher.id,
                jahr=jahr,
                monat=monat,
                verbrauch_daten={
                    "ladung_kwh": batt_ladung,
                    "entladung_kwh": batt_entladung,
                },
            )
            db.add(speicher_md)

        # Wärmepumpe Monatsdaten (ab April 2024)
        if wp_strom > 0:
            wp_md = InvestitionMonatsdaten(
                investition_id=waermepumpe.id,
                jahr=jahr,
                monat=monat,
                verbrauch_daten={
                    "stromverbrauch_kwh": wp_strom,
                    "heizenergie_kwh": wp_heizung,
                    "warmwasser_kwh": wp_warmwasser,
                },
            )
            db.add(wp_md)

    return DemoDataResult(
        erfolg=True,
        anlage_id=anlage.id,
        anlage_name=anlage.anlagenname,
        monatsdaten_count=monatsdaten_count,
        investitionen_count=7,  # Speicher, E-Auto, WP, Wallbox + 3 PV-Module
        strompreise_count=3,
        message=f"Demo-Anlage '{anlage.anlagenname}' mit {monatsdaten_count} Monatsdaten, 7 Investitionen (inkl. 3 PV-Module) und 3 Strompreisen erstellt.",
    )


@router.delete("/demo", response_model=dict)
async def delete_demo_data(db: AsyncSession = Depends(get_db)):
    """
    Löscht die Demo-Anlage und alle zugehörigen Daten.

    Returns:
        dict: Bestätigung der Löschung
    """
    # Demo-Anlage finden
    result = await db.execute(
        select(Anlage).where(Anlage.anlagenname == "Demo-Anlage")
    )
    anlage = result.scalar_one_or_none()

    if not anlage:
        raise HTTPException(status_code=404, detail="Demo-Anlage nicht gefunden")

    # Cascade Delete löscht alle verknüpften Daten
    await db.delete(anlage)

    return {"message": "Demo-Anlage und alle zugehörigen Daten gelöscht"}
