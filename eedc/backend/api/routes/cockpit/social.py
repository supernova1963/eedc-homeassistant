"""
Cockpit Social — Kopierfertiger Social-Media-Text für einen Monat.
"""

from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel

from backend.api.deps import get_db
from backend.models.monatsdaten import Monatsdaten
from backend.models.anlage import Anlage
from backend.models.investition import Investition, InvestitionMonatsdaten
from backend.models.pvgis_prognose import PVGISPrognose as PVGISPrognoseModel
from backend.api.routes.strompreise import lade_tarife_fuer_anlage, resolve_netzbezug_preis_cent
from backend.core.calculations import (
    CO2_FAKTOR_STROM_KG_KWH, CO2_FAKTOR_GAS_KG_KWH, CO2_FAKTOR_BENZIN_KG_LITER,
)
from backend.utils.sonstige_positionen import berechne_sonstige_summen
from backend.services.community_service import get_region_from_plz
from backend.api.routes.cockpit._shared import MONATSNAMEN

router = APIRouter()

_REGION_NAMEN = {
    "BW": "Baden-Württemberg", "BY": "Bayern", "BE": "Berlin",
    "BB": "Brandenburg", "HB": "Bremen", "HH": "Hamburg",
    "HE": "Hessen", "MV": "Mecklenburg-Vorpommern",
    "NI": "Niedersachsen", "NW": "Nordrhein-Westfalen",
    "RP": "Rheinland-Pfalz", "SL": "Saarland",
    "SN": "Sachsen", "ST": "Sachsen-Anhalt",
    "SH": "Schleswig-Holstein", "TH": "Thüringen",
    "AT": "Österreich", "CH": "Schweiz",
}


class ShareTextResponse(BaseModel):
    text: str
    variante: str


@router.get("/share-text/{anlage_id}", response_model=ShareTextResponse)
async def get_share_text(
    anlage_id: int,
    monat: int = Query(..., ge=1, le=12, description="Monat (1-12)"),
    jahr: int = Query(..., description="Jahr"),
    variante: str = Query("kompakt", description="kompakt oder ausfuehrlich"),
    db: AsyncSession = Depends(get_db)
):
    """Generiert kopierfertigen Social-Media-Text für einen Monat."""
    anlage_result = await db.execute(select(Anlage).where(Anlage.id == anlage_id))
    anlage = anlage_result.scalar_one_or_none()
    if not anlage:
        raise HTTPException(status_code=404, detail="Anlage nicht gefunden")

    # KEIN aktiv-Filter (Issue #123): historischer Monatstext.
    inv_result = await db.execute(
        select(Investition).where(Investition.anlage_id == anlage_id)
    )
    investitionen = inv_result.scalars().all()

    pv_module = [i for i in investitionen if i.typ == "pv-module"]

    def _ausrichtung_label(inv) -> str:
        grad = (inv.parameter or {}).get("ausrichtung_grad")
        if grad is not None:
            try:
                return f"{float(grad):+.0f}°"
            except (TypeError, ValueError):
                pass
        return inv.ausrichtung or "Süd"

    ausrichtung_anzeigen: str | None = None
    neigung = 30
    if len(pv_module) == 1:
        ausrichtung_anzeigen = _ausrichtung_label(pv_module[0])
        neigung = pv_module[0].neigung_grad if pv_module[0].neigung_grad is not None else 30
    elif len(pv_module) > 1:
        labels = [_ausrichtung_label(m) for m in pv_module]
        if len(set(labels)) == 1:
            ausrichtung_anzeigen = labels[0]
            neigung = pv_module[0].neigung_grad if pv_module[0].neigung_grad is not None else 30

    kwp = sum(i.leistung_kwp or 0 for i in investitionen if i.typ == "pv-module")
    for i in investitionen:
        if i.typ == "balkonkraftwerk":
            kwp += (i.parameter or {}).get("leistung_wp", 0) / 1000
    if kwp == 0 and anlage.leistung_kwp:
        kwp = anlage.leistung_kwp

    region_code = get_region_from_plz(anlage.standort_plz, anlage.standort_land)
    bundesland = _REGION_NAMEN.get(region_code, region_code) if region_code else None

    md_result = await db.execute(
        select(Monatsdaten).where(
            Monatsdaten.anlage_id == anlage_id,
            Monatsdaten.jahr == jahr,
            Monatsdaten.monat == monat,
        )
    )
    md = md_result.scalar_one_or_none()
    if not md:
        raise HTTPException(status_code=404, detail=f"Keine Monatsdaten für {MONATSNAMEN[monat]} {jahr}")

    inv_ids = [i.id for i in investitionen]
    imd_list = []
    if inv_ids:
        imd_result = await db.execute(
            select(InvestitionMonatsdaten).where(
                InvestitionMonatsdaten.investition_id.in_(inv_ids),
                InvestitionMonatsdaten.jahr == jahr,
                InvestitionMonatsdaten.monat == monat,
            )
        )
        imd_list = imd_result.scalars().all()

    inv_by_id = {i.id: i for i in investitionen}

    pv_erzeugung = 0.0
    speicher_ladung = 0.0
    speicher_entladung = 0.0
    wp_waerme = 0.0
    wp_strom = 0.0
    emob_km = 0.0
    emob_ladung = 0.0
    emob_pv_ladung = 0.0

    for imd in imd_list:
        inv = inv_by_id.get(imd.investition_id)
        if not inv:
            continue
        data = imd.verbrauch_daten or {}
        if inv.typ in ("pv-module", "balkonkraftwerk"):
            pv_erzeugung += (data.get("pv_erzeugung_kwh", 0) or data.get("erzeugung_kwh", 0) or 0)
        if inv.typ == "speicher":
            speicher_ladung += data.get("ladung_kwh", 0) or 0
            speicher_entladung += data.get("entladung_kwh", 0) or 0
        elif inv.typ == "waermepumpe":
            wp_waerme += (
                data.get("waerme_kwh", 0) or
                (data.get("heizenergie_kwh", 0) or data.get("heizung_kwh", 0)) +
                (data.get("warmwasser_kwh", 0) or 0)
            )
            wp_strom += (
                data.get("stromverbrauch_kwh", 0) or
                data.get("strom_kwh", 0) or
                data.get("verbrauch_kwh", 0) or 0
            )
        elif inv.typ in ("e-auto", "wallbox") and not (inv.parameter or {}).get("ist_dienstlich", False):
            emob_km += data.get("km_gefahren", 0) or 0
            emob_ladung += data.get("ladung_kwh", 0) or data.get("verbrauch_kwh", 0) or 0
            emob_pv_ladung += data.get("ladung_pv_kwh", 0) or 0

    if pv_erzeugung == 0:
        pv_erzeugung = md.pv_erzeugung_kwh or 0

    einspeisung = md.einspeisung_kwh or 0
    netzbezug = md.netzbezug_kwh or 0

    direktverbrauch = max(0, pv_erzeugung - einspeisung - speicher_ladung) if pv_erzeugung > 0 else 0
    eigenverbrauch = direktverbrauch + speicher_entladung
    gesamtverbrauch = eigenverbrauch + netzbezug
    autarkie = (eigenverbrauch / gesamtverbrauch * 100) if gesamtverbrauch > 0 else 0
    ev_quote = min(eigenverbrauch / pv_erzeugung * 100, 100) if pv_erzeugung > 0 else 0
    spez_ertrag = pv_erzeugung / kwp if kwp > 0 else 0

    hat_speicher = any(i.typ == "speicher" for i in investitionen)
    speicher_eff = (speicher_entladung / speicher_ladung * 100) if speicher_ladung > 0 else 0

    hat_waermepumpe = any(i.typ == "waermepumpe" for i in investitionen)
    wp_cop = (wp_waerme / wp_strom) if wp_strom > 0 else 0

    hat_emobilitaet = any(
        i.typ in ("e-auto", "wallbox") and not (i.parameter or {}).get("ist_dienstlich", False)
        for i in investitionen
    )
    emob_pv_anteil = (emob_pv_ladung / emob_ladung * 100) if emob_ladung > 0 else 0

    co2_pv = eigenverbrauch * CO2_FAKTOR_STROM_KG_KWH
    co2_wp = (wp_waerme / 0.9 * CO2_FAKTOR_GAS_KG_KWH) - (wp_strom * CO2_FAKTOR_STROM_KG_KWH) if wp_waerme > 0 else 0
    benzin_verbrauch = emob_km * 7 / 100
    co2_emob = (benzin_verbrauch * CO2_FAKTOR_BENZIN_KG_LITER) - ((emob_ladung - emob_pv_ladung) * CO2_FAKTOR_STROM_KG_KWH) if emob_km > 0 else 0
    co2_gesamt = co2_pv + max(0, co2_wp) + max(0, co2_emob)

    tarife = await lade_tarife_fuer_anlage(db, anlage_id)
    allgemein_tarif = tarife.get("allgemein")
    einspeise_cent = allgemein_tarif.einspeiseverguetung_cent_kwh if allgemein_tarif else 8.2
    netzbezug_cent = resolve_netzbezug_preis_cent(md, allgemein_tarif.netzbezug_arbeitspreis_cent_kwh if allgemein_tarif else 30.0)
    netto_ertrag = (einspeisung * einspeise_cent + eigenverbrauch * netzbezug_cent) / 100

    prognose_kwh = None
    pvgis_result = await db.execute(
        select(PVGISPrognoseModel).where(
            PVGISPrognoseModel.anlage_id == anlage_id,
            PVGISPrognoseModel.ist_aktiv == True,
        )
    )
    pvgis = pvgis_result.scalar_one_or_none()
    if pvgis and pvgis.monatswerte:
        for mw in pvgis.monatswerte:
            if mw.get("monat") == monat:
                prognose_kwh = mw.get("e_m", 0)
                break

    def f(val: float, decimals: int = 0) -> str:
        if decimals == 0:
            return f"{val:,.0f}".replace(",", ".")
        return f"{val:,.{decimals}f}".replace(",", "X").replace(".", ",").replace("X", ".")

    monat_name = MONATSNAMEN[monat]
    standort = f" | {bundesland}" if bundesland else ""
    ausrichtung_str = f" | {ausrichtung_anzeigen}" if ausrichtung_anzeigen else ""

    if variante == "ausfuehrlich":
        lines = [
            f"☀️ PV-Monatsreport {monat_name} {jahr}",
            "",
            f"🔧 Anlage: {f(kwp, 1)} kWp{ausrichtung_str}{standort}",
            f"⚡ Erzeugung: {f(pv_erzeugung)} kWh ({f(spez_ertrag, 1)} kWh/kWp)",
        ]
        if prognose_kwh and prognose_kwh > 0:
            abw = (pv_erzeugung - prognose_kwh) / prognose_kwh * 100
            emoji = "🎉" if abw >= 0 else ""
            lines.append(f"📊 PVGIS-Prognose: {f(prognose_kwh)} kWh → {'+' if abw >= 0 else ''}{f(abw, 1)}% {emoji}")
        lines.extend([
            f"🏠 Autarkiegrad: {f(autarkie)}%",
            f"♻️ Eigenverbrauchsquote: {f(ev_quote)}%",
            f"🔌 Einspeisung: {f(einspeisung)} kWh | Netzbezug: {f(netzbezug)} kWh",
        ])
        if hat_speicher and speicher_ladung > 0:
            lines.append("")
            lines.append(f"🔋 Speicher: {f(speicher_ladung)} kWh geladen, {f(speicher_entladung)} kWh entladen ({f(speicher_eff)}% Effizienz)")
        if hat_emobilitaet and emob_km > 0:
            lines.append(f"🚗 E-Auto: {f(emob_km)} km, davon {f(emob_pv_anteil)}% mit PV geladen")
        if hat_waermepumpe and wp_waerme > 0:
            lines.append(f"🌡️ Wärmepumpe: COP {f(wp_cop, 1)} | {f(wp_waerme)} kWh Wärme")
        lines.extend([
            "",
            f"💰 Netto-Ertrag: {f(netto_ertrag, 2)} €",
            f"🌍 CO₂ gespart: {f(co2_gesamt)} kg",
            "",
            "Erstellt mit EEDC",
        ])
        text = "\n".join(lines)
    else:
        lines = [
            f"☀️ PV-Bilanz {monat_name} {jahr} | {f(kwp, 1)} kWp{ausrichtung_str}{standort}",
            "",
            f"Erzeugung: {f(pv_erzeugung)} kWh ({f(spez_ertrag, 1)} kWh/kWp)",
            f"Autarkie: {f(autarkie)}% | Eigenverbrauch: {f(ev_quote)}%",
            f"Einspeisung: {f(einspeisung)} kWh | Netzbezug: {f(netzbezug)} kWh",
            f"CO₂ gespart: {f(co2_gesamt)} kg",
            "",
            "#Photovoltaik #PV #Energiewende",
        ]
        text = "\n".join(lines)

    return ShareTextResponse(text=text, variante=variante)
