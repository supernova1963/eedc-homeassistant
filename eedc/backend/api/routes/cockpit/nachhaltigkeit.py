"""
Cockpit Nachhaltigkeit — CO2-Bilanz Zeitreihe.
"""

from typing import Optional
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel

from backend.api.deps import get_db
from backend.models.monatsdaten import Monatsdaten
from backend.models.investition import Investition, InvestitionMonatsdaten
from backend.core.calculations import (
    CO2_FAKTOR_STROM_KG_KWH, CO2_FAKTOR_GAS_KG_KWH, CO2_FAKTOR_BENZIN_KG_LITER,
)
from backend.api.routes.cockpit._shared import MONATSNAMEN

router = APIRouter()


class NachhaltigkeitMonat(BaseModel):
    """CO2-Bilanz für einen Monat."""
    jahr: int
    monat: int
    monat_name: str
    co2_pv_kg: float
    co2_wp_kg: float
    co2_emob_kg: float
    co2_gesamt_kg: float
    co2_kumuliert_kg: float
    autarkie_prozent: float


class NachhaltigkeitResponse(BaseModel):
    """Nachhaltigkeits-Übersicht mit Zeitreihe."""
    anlage_id: int
    co2_gesamt_kg: float
    co2_pv_kg: float
    co2_wp_kg: float
    co2_emob_kg: float
    aequivalent_baeume: int
    aequivalent_auto_km: int
    aequivalent_fluege_km: int
    monatswerte: list[NachhaltigkeitMonat]
    autarkie_durchschnitt_prozent: float


@router.get("/nachhaltigkeit/{anlage_id}", response_model=NachhaltigkeitResponse)
async def get_nachhaltigkeit(
    anlage_id: int,
    db: AsyncSession = Depends(get_db)
):
    """Nachhaltigkeits-Übersicht mit CO2-Zeitreihe."""
    # KEIN aktiv-Filter (Issue #123): CO2-Zeitreihe historisch, Stilllegung
    # darf vergangene Einsparungen nicht rückwirkend entfernen.
    inv_result = await db.execute(
        select(Investition)
        .where(Investition.anlage_id == anlage_id)
    )
    investitionen = inv_result.scalars().all()
    inv_by_id = {i.id: i for i in investitionen}

    all_inv_ids = [i.id for i in investitionen]
    all_imd = []
    if all_inv_ids:
        imd_result = await db.execute(
            select(InvestitionMonatsdaten)
            .where(InvestitionMonatsdaten.investition_id.in_(all_inv_ids))
            .order_by(InvestitionMonatsdaten.jahr, InvestitionMonatsdaten.monat)
        )
        all_imd = imd_result.scalars().all()

    data_by_month: dict[tuple[int, int], dict] = {}

    for imd in all_imd:
        key = (imd.jahr, imd.monat)
        if key not in data_by_month:
            data_by_month[key] = {
                "pv_erzeugung": 0, "speicher_ladung": 0, "speicher_entladung": 0,
                "wp_waerme": 0, "wp_strom": 0,
                "emob_km": 0, "emob_ladung": 0, "emob_pv_ladung": 0,
            }

        inv = inv_by_id.get(imd.investition_id)
        if not inv:
            continue

        data = imd.verbrauch_daten or {}

        if inv.typ == "pv-module":
            data_by_month[key]["pv_erzeugung"] += data.get("pv_erzeugung_kwh", 0) or 0
        elif inv.typ == "speicher":
            data_by_month[key]["speicher_ladung"] += data.get("ladung_kwh", 0) or 0
            data_by_month[key]["speicher_entladung"] += data.get("entladung_kwh", 0) or 0
        elif inv.typ == "balkonkraftwerk":
            data_by_month[key]["pv_erzeugung"] += data.get("pv_erzeugung_kwh", 0) or data.get("erzeugung_kwh", 0) or 0
        elif inv.typ == "waermepumpe":
            data_by_month[key]["wp_waerme"] += (
                data.get("waerme_kwh", 0) or
                (data.get("heizenergie_kwh", 0) or data.get("heizung_kwh", 0)) +
                (data.get("warmwasser_kwh", 0) or 0)
            )
            data_by_month[key]["wp_strom"] += (
                data.get("stromverbrauch_kwh", 0) or
                data.get("strom_kwh", 0) or
                data.get("verbrauch_kwh", 0) or 0
            )
        elif inv.typ in ("e-auto", "wallbox"):
            data_by_month[key]["emob_km"] += data.get("km_gefahren", 0) or 0
            data_by_month[key]["emob_ladung"] += (
                data.get("ladung_kwh", 0) or data.get("verbrauch_kwh", 0) or 0
            )
            data_by_month[key]["emob_pv_ladung"] += data.get("ladung_pv_kwh", 0) or 0

    md_result = await db.execute(
        select(Monatsdaten)
        .where(Monatsdaten.anlage_id == anlage_id)
        .order_by(Monatsdaten.jahr, Monatsdaten.monat)
    )
    monatsdaten_list = md_result.scalars().all()
    md_by_month = {(m.jahr, m.monat): m for m in monatsdaten_list}

    monatswerte = []
    co2_kumuliert = 0.0
    co2_pv_total = 0.0
    co2_wp_total = 0.0
    co2_emob_total = 0.0
    autarkie_summe = 0.0
    autarkie_count = 0

    for key in sorted(data_by_month.keys()):
        jahr, monat = key
        d = data_by_month[key]

        md = md_by_month.get(key)
        einspeisung = md.einspeisung_kwh or 0 if md else 0
        netzbezug = md.netzbezug_kwh or 0 if md else 0

        pv_erzeugung = d["pv_erzeugung"]
        direktverbrauch = max(0, pv_erzeugung - einspeisung - d["speicher_ladung"])
        eigenverbrauch = direktverbrauch + d["speicher_entladung"]
        gesamtverbrauch = eigenverbrauch + netzbezug

        co2_pv = eigenverbrauch * CO2_FAKTOR_STROM_KG_KWH

        wp_waerme = d["wp_waerme"]
        wp_strom = d["wp_strom"]
        co2_wp = (wp_waerme / 0.9 * CO2_FAKTOR_GAS_KG_KWH) - (wp_strom * CO2_FAKTOR_STROM_KG_KWH) if wp_waerme > 0 else 0
        co2_wp = max(0, co2_wp)

        emob_km = d["emob_km"]
        emob_ladung = d["emob_ladung"]
        emob_pv = d["emob_pv_ladung"]
        benzin_verbrauch = emob_km * 7 / 100
        co2_emob = (benzin_verbrauch * CO2_FAKTOR_BENZIN_KG_LITER) - ((emob_ladung - emob_pv) * CO2_FAKTOR_STROM_KG_KWH) if emob_km > 0 else 0
        co2_emob = max(0, co2_emob)

        co2_monat = co2_pv + co2_wp + co2_emob
        co2_kumuliert += co2_monat

        autarkie = (eigenverbrauch / gesamtverbrauch * 100) if gesamtverbrauch > 0 else 0
        autarkie_summe += autarkie
        autarkie_count += 1

        monatswerte.append(NachhaltigkeitMonat(
            jahr=jahr,
            monat=monat,
            monat_name=MONATSNAMEN[monat],
            co2_pv_kg=round(co2_pv, 1),
            co2_wp_kg=round(co2_wp, 1),
            co2_emob_kg=round(co2_emob, 1),
            co2_gesamt_kg=round(co2_monat, 1),
            co2_kumuliert_kg=round(co2_kumuliert, 1),
            autarkie_prozent=round(autarkie, 1),
        ))

        co2_pv_total += co2_pv
        co2_wp_total += co2_wp
        co2_emob_total += co2_emob

    co2_gesamt = co2_pv_total + co2_wp_total + co2_emob_total
    autarkie_avg = autarkie_summe / autarkie_count if autarkie_count > 0 else 0

    return NachhaltigkeitResponse(
        anlage_id=anlage_id,
        co2_gesamt_kg=round(co2_gesamt, 1),
        co2_pv_kg=round(co2_pv_total, 1),
        co2_wp_kg=round(co2_wp_total, 1),
        co2_emob_kg=round(co2_emob_total, 1),
        aequivalent_baeume=int(co2_gesamt / 20),
        aequivalent_auto_km=int(co2_gesamt / 0.12),
        aequivalent_fluege_km=int(co2_gesamt / 0.25),
        monatswerte=monatswerte,
        autarkie_durchschnitt_prozent=round(autarkie_avg, 1),
    )
