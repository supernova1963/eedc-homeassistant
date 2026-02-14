"""
CSV Import/Export Operations

Template-Generierung, CSV-Import und CSV-Export.
"""

import csv
from io import StringIO
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps import get_db
from backend.models.anlage import Anlage
from backend.models.monatsdaten import Monatsdaten
from backend.models.investition import Investition, InvestitionMonatsdaten
from backend.services.wetter_service import get_wetterdaten

from .schemas import ImportResult, CSVTemplateInfo
from .helpers import (
    _sanitize_column_name,
    _normalize_for_matching,
    _import_investition_monatsdaten_v09,
    _import_investition_monatsdaten_legacy,
)

router = APIRouter()


@router.get("/template/{anlage_id}", response_model=CSVTemplateInfo)
async def get_csv_template_info(anlage_id: int, db: AsyncSession = Depends(get_db)):
    """
    Gibt Informationen über das personalisierte CSV-Template für eine Anlage zurück.

    v0.9: Template basiert auf angelegten Investitionen mit deren Bezeichnungen.
    Spalten werden dynamisch generiert, z.B. "Speicher_Keller_Ladung_kWh".
    """
    # Anlage prüfen
    anlage_result = await db.execute(select(Anlage).where(Anlage.id == anlage_id))
    if not anlage_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Anlage nicht gefunden")

    # Basis-Spalten (nur Zählerwerte!)
    spalten = ["Jahr", "Monat", "Einspeisung_kWh", "Netzbezug_kWh"]
    beschreibung = {
        "Jahr": "Jahr (z.B. 2024)",
        "Monat": "Monat (1-12)",
        "Einspeisung_kWh": "Ins Netz eingespeiste Energie (Zählerwert)",
        "Netzbezug_kWh": "Aus dem Netz bezogene Energie (Zählerwert)",
    }

    # Investitionen laden, nach Typ und ID sortiert
    inv_result = await db.execute(
        select(Investition)
        .where(Investition.anlage_id == anlage_id, Investition.aktiv == True)
        .order_by(Investition.typ, Investition.id)
    )
    investitionen = inv_result.scalars().all()

    # Personalisierte Spalten je nach Investition (v0.9)
    for inv in investitionen:
        prefix = _sanitize_column_name(inv.bezeichnung)

        if inv.typ == "pv-module":
            col = f"{prefix}_kWh"
            spalten.append(col)
            beschreibung[col] = f"PV-Erzeugung {inv.bezeichnung} (kWh)"

        elif inv.typ == "speicher":
            col_ladung = f"{prefix}_Ladung_kWh"
            col_entladung = f"{prefix}_Entladung_kWh"
            spalten.extend([col_ladung, col_entladung])
            beschreibung[col_ladung] = f"Ladung {inv.bezeichnung} (kWh)"
            beschreibung[col_entladung] = f"Entladung {inv.bezeichnung} (kWh)"
            if inv.parameter and inv.parameter.get("arbitrage_faehig"):
                col_netz = f"{prefix}_Netzladung_kWh"
                col_preis = f"{prefix}_Ladepreis_Cent"
                spalten.extend([col_netz, col_preis])
                beschreibung[col_netz] = f"Netzladung {inv.bezeichnung} (kWh) - Arbitrage"
                beschreibung[col_preis] = f"Ø Ladepreis {inv.bezeichnung} (ct/kWh) - Arbitrage"

        elif inv.typ == "e-auto":
            cols = [
                (f"{prefix}_km", f"Gefahrene km {inv.bezeichnung}"),
                (f"{prefix}_Verbrauch_kWh", f"Verbrauch {inv.bezeichnung} (kWh)"),
                (f"{prefix}_Ladung_PV_kWh", f"PV-Ladung {inv.bezeichnung} (kWh)"),
                (f"{prefix}_Ladung_Netz_kWh", f"Netz-Ladung {inv.bezeichnung} (kWh)"),
                (f"{prefix}_Ladung_Extern_kWh", f"Externe Ladung {inv.bezeichnung} (kWh)"),
                (f"{prefix}_Ladung_Extern_Euro", f"Externe Ladekosten {inv.bezeichnung} (€)"),
            ]
            if inv.parameter and (inv.parameter.get("nutzt_v2h") or inv.parameter.get("v2h_faehig")):
                cols.append((f"{prefix}_V2H_kWh", f"V2H-Entladung {inv.bezeichnung} (kWh)"))
            for col, desc in cols:
                spalten.append(col)
                beschreibung[col] = desc

        elif inv.typ == "wallbox":
            cols = [
                (f"{prefix}_Ladung_kWh", f"Ladung {inv.bezeichnung} (kWh)"),
                (f"{prefix}_Ladevorgaenge", f"Ladevorgänge {inv.bezeichnung}"),
            ]
            for col, desc in cols:
                spalten.append(col)
                beschreibung[col] = desc

        elif inv.typ == "waermepumpe":
            cols = [
                (f"{prefix}_Strom_kWh", f"Stromverbrauch {inv.bezeichnung} (kWh)"),
                (f"{prefix}_Heizung_kWh", f"Heizenergie {inv.bezeichnung} (kWh)"),
                (f"{prefix}_Warmwasser_kWh", f"Warmwasser {inv.bezeichnung} (kWh)"),
            ]
            for col, desc in cols:
                spalten.append(col)
                beschreibung[col] = desc

        elif inv.typ == "balkonkraftwerk":
            col_pv = f"{prefix}_Erzeugung_kWh"
            col_ev = f"{prefix}_Eigenverbrauch_kWh"
            spalten.extend([col_pv, col_ev])
            beschreibung[col_pv] = f"PV-Erzeugung {inv.bezeichnung} (kWh)"
            beschreibung[col_ev] = f"Eigenverbrauch {inv.bezeichnung} (kWh)"
            if inv.parameter and inv.parameter.get("hat_speicher"):
                col_sp_l = f"{prefix}_Speicher_Ladung_kWh"
                col_sp_e = f"{prefix}_Speicher_Entladung_kWh"
                spalten.extend([col_sp_l, col_sp_e])
                beschreibung[col_sp_l] = f"Speicher-Ladung {inv.bezeichnung} (kWh)"
                beschreibung[col_sp_e] = f"Speicher-Entladung {inv.bezeichnung} (kWh)"

        elif inv.typ == "sonstiges":
            kategorie = inv.parameter.get("kategorie", "erzeuger") if inv.parameter else "erzeuger"
            if kategorie == "erzeuger":
                col = f"{prefix}_Erzeugung_kWh"
                spalten.append(col)
                beschreibung[col] = f"Erzeugung {inv.bezeichnung} (kWh)"
            elif kategorie == "verbraucher":
                col = f"{prefix}_Verbrauch_kWh"
                spalten.append(col)
                beschreibung[col] = f"Verbrauch {inv.bezeichnung} (kWh)"
            elif kategorie == "speicher":
                col_l = f"{prefix}_Ladung_kWh"
                col_e = f"{prefix}_Entladung_kWh"
                spalten.extend([col_l, col_e])
                beschreibung[col_l] = f"Ladung {inv.bezeichnung} (kWh)"
                beschreibung[col_e] = f"Entladung {inv.bezeichnung} (kWh)"

        # Sonderkosten für alle Investitionen (optional)
        col_sk = f"{prefix}_Sonderkosten_Euro"
        col_skn = f"{prefix}_Sonderkosten_Notiz"
        spalten.extend([col_sk, col_skn])
        beschreibung[col_sk] = f"Sonderkosten {inv.bezeichnung} (€) - Reparatur, Wartung, etc."
        beschreibung[col_skn] = f"Sonderkosten-Beschreibung {inv.bezeichnung}"

    spalten.append("Notizen")
    beschreibung["Notizen"] = "Notizen (optional)"

    return CSVTemplateInfo(spalten=spalten, beschreibung=beschreibung)


@router.get("/template/{anlage_id}/download")
async def download_csv_template(anlage_id: int, db: AsyncSession = Depends(get_db)):
    """Lädt ein CSV-Template für eine Anlage herunter."""
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
    auto_wetter: bool = Query(True, description="Wetterdaten automatisch abrufen wenn leer"),
    db: AsyncSession = Depends(get_db)
):
    """
    Importiert Monatsdaten aus einer CSV-Datei.

    v0.9: Unterstützt personalisierte Spalten basierend auf Investitions-Bezeichnungen.
    """
    import logging
    logger = logging.getLogger(__name__)

    # Anlage prüfen und laden
    anlage_result = await db.execute(select(Anlage).where(Anlage.id == anlage_id))
    anlage = anlage_result.scalar_one_or_none()
    if not anlage:
        raise HTTPException(status_code=404, detail="Anlage nicht gefunden")

    # Investitionen laden
    inv_result = await db.execute(
        select(Investition).where(Investition.anlage_id == anlage_id, Investition.aktiv == True)
    )
    investitionen = list(inv_result.scalars().all())

    # Investitionen nach Typ gruppieren (erste aktive je Typ) - für Legacy-Import
    inv_by_type: dict[str, Investition] = {}
    for inv in investitionen:
        if inv.typ not in inv_by_type:
            inv_by_type[inv.typ] = inv

    # CSV lesen
    try:
        content = await file.read()
        text = content.decode("utf-8-sig")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Fehler beim Lesen der Datei: {e}")

    # CSV parsen
    first_line = text.split('\n')[0] if text else ''
    delimiter = ';' if ';' in first_line else ','
    reader = csv.DictReader(StringIO(text), delimiter=delimiter)

    # Prüfen ob personalisierte Spalten vorhanden
    fieldnames = reader.fieldnames or []
    has_personalized_columns = False

    for inv in investitionen:
        sanitized = _sanitize_column_name(inv.bezeichnung)
        normalized = _normalize_for_matching(inv.bezeichnung)

        for col in fieldnames:
            if sanitized in col:
                has_personalized_columns = True
                break
            col_normalized = _normalize_for_matching(col)
            if col_normalized.startswith(normalized) and len(normalized) >= 3:
                has_personalized_columns = True
                break

        if has_personalized_columns:
            break

    importiert = 0
    uebersprungen = 0
    fehler = []
    warnungen = []

    pv_module_vorhanden = any(inv.typ == "pv-module" for inv in investitionen)
    speicher_vorhanden = any(inv.typ == "speicher" for inv in investitionen)

    for i, row in enumerate(reader, start=2):
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

            # Werte parsen
            def parse_float(val: str) -> Optional[float]:
                if not val or not val.strip():
                    return None
                val = val.strip().replace(",", ".")
                return float(val)

            def parse_float_positive(val: str, feldname: str) -> Optional[float]:
                result = parse_float(val)
                if result is not None and result < 0:
                    raise ValueError(f"{feldname} darf nicht negativ sein ({result})")
                return result

            # Basis-Felder
            einspeisung_raw = parse_float_positive(row.get("Einspeisung_kWh", ""), "Einspeisung_kWh")
            netzbezug_raw = parse_float_positive(row.get("Netzbezug_kWh", ""), "Netzbezug_kWh")
            einspeisung = einspeisung_raw or 0
            netzbezug = netzbezug_raw or 0

            globalstrahlung = parse_float_positive(row.get("Globalstrahlung_kWh_m2", ""), "Globalstrahlung")
            sonnenstunden = parse_float_positive(row.get("Sonnenstunden", ""), "Sonnenstunden")
            notizen = row.get("Notizen", "").strip() or None

            # Plausibilitäts-Warnungen
            if sonnenstunden is not None and sonnenstunden > 400:
                warnungen.append(f"Zeile {i}: Sonnenstunden ({sonnenstunden}) ungewöhnlich hoch")
            if globalstrahlung is not None and globalstrahlung > 250:
                warnungen.append(f"Zeile {i}: Globalstrahlung ({globalstrahlung}) ungewöhnlich hoch")

            # Wetterdaten automatisch abrufen
            if auto_wetter and globalstrahlung is None and sonnenstunden is None:
                if anlage.latitude and anlage.longitude:
                    try:
                        wetter = await get_wetterdaten(
                            latitude=anlage.latitude,
                            longitude=anlage.longitude,
                            jahr=jahr,
                            monat=monat
                        )
                        globalstrahlung = wetter.get("globalstrahlung_kwh_m2")
                        sonnenstunden = wetter.get("sonnenstunden")
                    except Exception as e:
                        logger.warning(f"Wetterdaten für {monat}/{jahr} nicht abrufbar: {e}")

            # Personalisierte Spalten verarbeiten
            summen = {"pv_erzeugung_sum": 0.0, "batterie_ladung_sum": 0.0, "batterie_entladung_sum": 0.0}
            if has_personalized_columns and investitionen:
                summen = await _import_investition_monatsdaten_v09(
                    db, row, parse_float, investitionen, jahr, monat, ueberschreiben
                )

            # Legacy-Spalten Validierung
            pv_erzeugung_explicit = parse_float(row.get("PV_Erzeugung_kWh", ""))
            batterie_ladung_explicit = parse_float(row.get("Batterie_Ladung_kWh", ""))
            batterie_entladung_explicit = parse_float(row.get("Batterie_Entladung_kWh", ""))

            # PV-Erzeugung Validierung
            pv_erzeugung = None
            if summen["pv_erzeugung_sum"] > 0:
                pv_erzeugung = summen["pv_erzeugung_sum"]
                if pv_erzeugung_explicit is not None:
                    if abs(pv_erzeugung_explicit - pv_erzeugung) <= 0.5:
                        if "Legacy-Spalte 'PV_Erzeugung_kWh' ist redundant" not in warnungen:
                            warnungen.append(
                                "Legacy-Spalte 'PV_Erzeugung_kWh' ist redundant und wird ignoriert."
                            )
                    else:
                        fehler.append(
                            f"Zeile {i}: PV_Erzeugung_kWh ({pv_erzeugung_explicit:.1f}) weicht von "
                            f"Summe der PV-Module ({pv_erzeugung:.1f}) ab."
                        )
                        continue
            elif pv_erzeugung_explicit is not None:
                if pv_module_vorhanden:
                    fehler.append(
                        f"Zeile {i}: Spalte 'PV_Erzeugung_kWh' wird nicht mehr unterstützt. "
                        f"Bitte individuelle PV-Modul-Spalten verwenden."
                    )
                    continue
                else:
                    pv_erzeugung = pv_erzeugung_explicit
                    if "Keine PV-Module als Investitionen angelegt" not in warnungen:
                        warnungen.append(
                            "Keine PV-Module als Investitionen angelegt. "
                            "Legacy-Spalte 'PV_Erzeugung_kWh' wird akzeptiert."
                        )

            # Batterie Validierung
            batterie_ladung = None
            batterie_entladung = None

            if summen["batterie_ladung_sum"] > 0 or summen["batterie_entladung_sum"] > 0:
                if batterie_ladung_explicit is not None:
                    if abs(batterie_ladung_explicit - summen["batterie_ladung_sum"]) <= 0.5:
                        if "Legacy-Spalte 'Batterie_Ladung_kWh' ist redundant" not in warnungen:
                            warnungen.append("Legacy-Spalte 'Batterie_Ladung_kWh' ist redundant.")
                    else:
                        fehler.append(
                            f"Zeile {i}: Batterie_Ladung_kWh weicht von Summe der Speicher ab."
                        )
                        continue

                if batterie_entladung_explicit is not None:
                    if abs(batterie_entladung_explicit - summen["batterie_entladung_sum"]) <= 0.5:
                        if "Legacy-Spalte 'Batterie_Entladung_kWh' ist redundant" not in warnungen:
                            warnungen.append("Legacy-Spalte 'Batterie_Entladung_kWh' ist redundant.")
                    else:
                        fehler.append(
                            f"Zeile {i}: Batterie_Entladung_kWh weicht von Summe der Speicher ab."
                        )
                        continue

            elif batterie_ladung_explicit is not None or batterie_entladung_explicit is not None:
                if speicher_vorhanden:
                    fehler.append(
                        f"Zeile {i}: Legacy-Spalten 'Batterie_*_kWh' werden nicht mehr unterstützt."
                    )
                    continue
                else:
                    batterie_ladung = batterie_ladung_explicit
                    batterie_entladung = batterie_entladung_explicit
                    if "Keine Speicher als Investitionen angelegt" not in warnungen:
                        warnungen.append("Keine Speicher als Investitionen angelegt.")

            # Berechnungen
            batterie_ladung_for_calc = batterie_ladung if batterie_ladung is not None else summen["batterie_ladung_sum"] if summen["batterie_ladung_sum"] > 0 else 0
            batterie_entladung_for_calc = batterie_entladung if batterie_entladung is not None else summen["batterie_entladung_sum"] if summen["batterie_entladung_sum"] > 0 else 0

            direktverbrauch = None
            eigenverbrauch = None
            gesamtverbrauch = None
            if pv_erzeugung is not None:
                direktverbrauch = max(0, pv_erzeugung - einspeisung - batterie_ladung_for_calc)
                eigenverbrauch = direktverbrauch + batterie_entladung_for_calc
                gesamtverbrauch = eigenverbrauch + netzbezug
            elif einspeisung > 0 or netzbezug > 0:
                gesamtverbrauch = netzbezug + einspeisung

            if existing_md:
                # Update
                existing_md.einspeisung_kwh = einspeisung
                existing_md.netzbezug_kwh = netzbezug
                existing_md.pv_erzeugung_kwh = pv_erzeugung
                existing_md.direktverbrauch_kwh = direktverbrauch
                existing_md.eigenverbrauch_kwh = eigenverbrauch
                existing_md.gesamtverbrauch_kwh = gesamtverbrauch
                existing_md.batterie_ladung_kwh = batterie_ladung
                existing_md.batterie_entladung_kwh = batterie_entladung
                existing_md.globalstrahlung_kwh_m2 = globalstrahlung
                existing_md.sonnenstunden = sonnenstunden
                existing_md.notizen = notizen
                existing_md.datenquelle = "csv"
            else:
                md = Monatsdaten(
                    anlage_id=anlage_id,
                    jahr=jahr,
                    monat=monat,
                    einspeisung_kwh=einspeisung,
                    netzbezug_kwh=netzbezug,
                    pv_erzeugung_kwh=pv_erzeugung,
                    direktverbrauch_kwh=direktverbrauch,
                    eigenverbrauch_kwh=eigenverbrauch,
                    gesamtverbrauch_kwh=gesamtverbrauch,
                    batterie_ladung_kwh=batterie_ladung,
                    batterie_entladung_kwh=batterie_entladung,
                    globalstrahlung_kwh_m2=globalstrahlung,
                    sonnenstunden=sonnenstunden,
                    notizen=notizen,
                    datenquelle="csv"
                )
                db.add(md)

            # Legacy Investitions-Spalten
            await _import_investition_monatsdaten_legacy(
                db, row, parse_float, inv_by_type, jahr, monat, ueberschreiben
            )

            importiert += 1

        except ValueError as e:
            fehler.append(f"Zeile {i}: Ungültiger Wert - {e}")
        except Exception as e:
            fehler.append(f"Zeile {i}: Fehler - {e}")

    await db.flush()

    return ImportResult(
        erfolg=len(fehler) == 0,
        importiert=importiert,
        uebersprungen=uebersprungen,
        fehler=fehler[:20],
        warnungen=warnungen[:10]
    )


@router.get("/export/{anlage_id}")
async def export_csv(
    anlage_id: int,
    jahr: Optional[int] = Query(None, description="Filter nach Jahr"),
    include_investitionen: bool = Query(True, description="Investitions-Monatsdaten einschließen"),
    db: AsyncSession = Depends(get_db)
):
    """Exportiert Monatsdaten als CSV."""
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

    # Investitionen und deren Monatsdaten laden
    investitionen = []
    inv_monatsdaten_map: dict[tuple[int, int, int], dict] = {}

    if include_investitionen:
        inv_result = await db.execute(
            select(Investition)
            .where(Investition.anlage_id == anlage_id, Investition.aktiv == True)
            .order_by(Investition.typ, Investition.id)
        )
        investitionen = list(inv_result.scalars().all())

        for inv in investitionen:
            imd_query = select(InvestitionMonatsdaten).where(
                InvestitionMonatsdaten.investition_id == inv.id
            )
            if jahr:
                imd_query = imd_query.where(InvestitionMonatsdaten.jahr == jahr)

            imd_result = await db.execute(imd_query)
            for imd in imd_result.scalars().all():
                inv_monatsdaten_map[(inv.id, imd.jahr, imd.monat)] = imd.verbrauch_daten or {}

    # CSV erstellen
    output = StringIO()
    writer = csv.writer(output, delimiter=";")

    header = ["Jahr", "Monat", "Einspeisung_kWh", "Netzbezug_kWh"]
    inv_columns: list[tuple[Investition, str, str]] = []

    for inv in investitionen:
        prefix = _sanitize_column_name(inv.bezeichnung)

        if inv.typ == "pv-module":
            inv_columns.append((inv, "kWh", "pv_erzeugung_kwh"))
            header.append(f"{prefix}_kWh")

        elif inv.typ == "speicher":
            inv_columns.append((inv, "Ladung_kWh", "ladung_kwh"))
            inv_columns.append((inv, "Entladung_kWh", "entladung_kwh"))
            header.extend([f"{prefix}_Ladung_kWh", f"{prefix}_Entladung_kWh"])
            if inv.parameter and inv.parameter.get("arbitrage_faehig"):
                inv_columns.append((inv, "Netzladung_kWh", "speicher_ladung_netz_kwh"))
                inv_columns.append((inv, "Ladepreis_Cent", "speicher_ladepreis_cent"))
                header.extend([f"{prefix}_Netzladung_kWh", f"{prefix}_Ladepreis_Cent"])

        elif inv.typ == "e-auto":
            cols = [
                ("km", "km_gefahren"),
                ("Verbrauch_kWh", "verbrauch_kwh"),
                ("Ladung_PV_kWh", "ladung_pv_kwh"),
                ("Ladung_Netz_kWh", "ladung_netz_kwh"),
                ("Ladung_Extern_kWh", "ladung_extern_kwh"),
                ("Ladung_Extern_Euro", "ladung_extern_euro"),
            ]
            if inv.parameter and (inv.parameter.get("nutzt_v2h") or inv.parameter.get("v2h_faehig")):
                cols.append(("V2H_kWh", "v2h_entladung_kwh"))
            for suffix, key in cols:
                inv_columns.append((inv, suffix, key))
                header.append(f"{prefix}_{suffix}")

        elif inv.typ == "wallbox":
            inv_columns.append((inv, "Ladung_kWh", "ladung_kwh"))
            inv_columns.append((inv, "Ladevorgaenge", "ladevorgaenge"))
            header.extend([f"{prefix}_Ladung_kWh", f"{prefix}_Ladevorgaenge"])

        elif inv.typ == "waermepumpe":
            cols = [
                ("Strom_kWh", "stromverbrauch_kwh"),
                ("Heizung_kWh", "heizenergie_kwh"),
                ("Warmwasser_kWh", "warmwasser_kwh"),
            ]
            for suffix, key in cols:
                inv_columns.append((inv, suffix, key))
                header.append(f"{prefix}_{suffix}")

        elif inv.typ == "balkonkraftwerk":
            inv_columns.append((inv, "Erzeugung_kWh", "pv_erzeugung_kwh"))
            inv_columns.append((inv, "Eigenverbrauch_kWh", "eigenverbrauch_kwh"))
            header.extend([f"{prefix}_Erzeugung_kWh", f"{prefix}_Eigenverbrauch_kWh"])
            if inv.parameter and inv.parameter.get("hat_speicher"):
                inv_columns.append((inv, "Speicher_Ladung_kWh", "speicher_ladung_kwh"))
                inv_columns.append((inv, "Speicher_Entladung_kWh", "speicher_entladung_kwh"))
                header.extend([f"{prefix}_Speicher_Ladung_kWh", f"{prefix}_Speicher_Entladung_kWh"])

        elif inv.typ == "sonstiges":
            kategorie = inv.parameter.get("kategorie", "erzeuger") if inv.parameter else "erzeuger"
            if kategorie == "erzeuger":
                inv_columns.append((inv, "Erzeugung_kWh", "erzeugung_kwh"))
                header.append(f"{prefix}_Erzeugung_kWh")
            elif kategorie == "verbraucher":
                inv_columns.append((inv, "Verbrauch_kWh", "verbrauch_sonstig_kwh"))
                header.append(f"{prefix}_Verbrauch_kWh")
            elif kategorie == "speicher":
                inv_columns.append((inv, "Ladung_kWh", "ladung_kwh"))
                inv_columns.append((inv, "Entladung_kWh", "entladung_kwh"))
                header.extend([f"{prefix}_Ladung_kWh", f"{prefix}_Entladung_kWh"])

        # Sonderkosten
        inv_columns.append((inv, "Sonderkosten_Euro", "sonderkosten_euro"))
        inv_columns.append((inv, "Sonderkosten_Notiz", "sonderkosten_notiz"))
        header.extend([f"{prefix}_Sonderkosten_Euro", f"{prefix}_Sonderkosten_Notiz"])

    header.append("Notizen")
    writer.writerow(header)

    for md in monatsdaten:
        row = [
            md.jahr,
            md.monat,
            md.einspeisung_kwh,
            md.netzbezug_kwh,
        ]

        for inv, suffix, data_key in inv_columns:
            inv_data = inv_monatsdaten_map.get((inv.id, md.jahr, md.monat), {})
            value = inv_data.get(data_key, "")
            row.append(value if value != "" else "")

        row.append(md.notizen or "")
        writer.writerow(row)

    output.seek(0)
    filename = f"eedc_export_{anlage.anlagenname}_{jahr or 'alle'}.csv"

    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )
