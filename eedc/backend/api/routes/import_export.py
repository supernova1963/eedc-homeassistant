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
from backend.models.investition import Investition


# =============================================================================
# Pydantic Schemas
# =============================================================================

class ImportResult(BaseModel):
    """Ergebnis eines CSV-Imports."""
    erfolg: bool
    importiert: int
    uebersprungen: int
    fehler: list[str]


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

    # CSV parsen
    reader = csv.DictReader(StringIO(text), delimiter=";")

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
