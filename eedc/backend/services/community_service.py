"""
EEDC Community Service

Bereitet Anlagendaten für die anonyme Übertragung an den Community-Server vor.
"""

import hashlib
from datetime import datetime
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import Anlage, Monatsdaten, Investition, InvestitionMonatsdaten
from backend.core.config import settings


# Community Server URL
COMMUNITY_SERVER_URL = "https://energy.raunet.eu"


def get_region_from_plz(plz: str | None) -> str | None:
    """
    Ermittelt das Bundesland aus der PLZ.
    Gibt das 2-Buchstaben-Kürzel zurück.
    """
    if not plz or len(plz) < 2:
        return None

    # PLZ-Bereiche für deutsche Bundesländer (vereinfacht)
    plz_prefix = plz[:2]
    plz_num = int(plz_prefix)

    plz_regions = {
        range(1, 10): "SN",   # 01-09: Sachsen (Dresden, Leipzig, Chemnitz)
        range(10, 15): "BE",  # 10-14: Berlin
        range(15, 20): "BB",  # 15-19: Brandenburg
        range(20, 22): "HH",  # 20-21: Hamburg
        range(22, 26): "SH",  # 22-25: Schleswig-Holstein
        range(26, 28): "NI",  # 26-27: Niedersachsen (Oldenburg)
        range(28, 29): "HB",  # 28: Bremen
        range(29, 32): "NI",  # 29-31: Niedersachsen
        range(32, 34): "NW",  # 32-33: NRW (Ostwestfalen)
        range(34, 37): "HE",  # 34-36: Hessen (Kassel)
        range(37, 38): "NI",  # 37: Niedersachsen (Göttingen)
        range(38, 40): "NI",  # 38-39: Niedersachsen (Braunschweig)
        range(40, 48): "NW",  # 40-47: NRW (Düsseldorf, Köln)
        range(48, 50): "NW",  # 48-49: NRW (Münster)
        range(50, 54): "NW",  # 50-53: NRW (Köln, Bonn)
        range(54, 57): "RP",  # 54-56: Rheinland-Pfalz (Trier, Koblenz)
        range(57, 60): "NW",  # 57-59: NRW (Siegen, Hagen)
        range(60, 66): "HE",  # 60-65: Hessen (Frankfurt, Wiesbaden)
        range(66, 67): "SL",  # 66: Saarland
        range(67, 70): "RP",  # 67-69: Rheinland-Pfalz (Ludwigshafen, Mainz)
        range(70, 77): "BW",  # 70-76: Baden-Württemberg (Stuttgart, Karlsruhe)
        range(77, 80): "BW",  # 77-79: Baden-Württemberg (Freiburg)
        range(80, 88): "BY",  # 80-87: Bayern (München, Augsburg)
        range(88, 90): "BW",  # 88-89: Baden-Württemberg (Bodensee, Ulm)
        range(90, 97): "BY",  # 90-96: Bayern (Nürnberg, Würzburg)
        range(97, 98): "BY",  # 97: Bayern (Würzburg)
        range(98, 100): "TH", # 98-99: Thüringen
    }

    for plz_range, region in plz_regions.items():
        if plz_num in plz_range:
            return region

    return None


def generate_anlage_hash(anlage: Anlage, secret: str) -> str:
    """
    Generiert einen eindeutigen aber anonymen Hash für eine Anlage.
    """
    raw = f"{anlage.leistung_kwp:.1f}:{anlage.installationsdatum}:{anlage.standort_plz[:2] if anlage.standort_plz else 'XX'}:{secret}"
    return hashlib.sha256(raw.encode()).hexdigest()


def get_ausrichtung_label(azimut: int | None) -> str:
    """Konvertiert Azimut-Winkel in Ausrichtungs-Label."""
    if azimut is None:
        return "unbekannt"

    # Normalisiere auf 0-360
    azimut = azimut % 360

    if 337.5 <= azimut or azimut < 22.5:
        return "nord"
    elif 22.5 <= azimut < 67.5:
        return "nord-ost"
    elif 67.5 <= azimut < 112.5:
        return "ost"
    elif 112.5 <= azimut < 157.5:
        return "süd-ost"
    elif 157.5 <= azimut < 202.5:
        return "süd"
    elif 202.5 <= azimut < 247.5:
        return "süd-west"
    elif 247.5 <= azimut < 292.5:
        return "west"
    elif 292.5 <= azimut < 337.5:
        return "nord-west"

    return "gemischt"


async def prepare_community_data(
    db: AsyncSession,
    anlage_id: int,
    include_monatswerte: bool = True,
) -> dict | None:
    """
    Bereitet die Anlagendaten für die Community-Übertragung vor.

    Returns:
        dict mit anonymisierten Daten oder None wenn Anlage nicht gefunden
    """
    # Anlage laden
    result = await db.execute(select(Anlage).where(Anlage.id == anlage_id))
    anlage = result.scalar_one_or_none()

    if not anlage:
        return None

    # Region aus PLZ ermitteln
    region = get_region_from_plz(anlage.standort_plz)
    if not region:
        region = "XX"  # Unbekannt

    # Investitionen laden für Ausstattung
    result = await db.execute(
        select(Investition).where(Investition.anlage_id == anlage_id)
    )
    investitionen = result.scalars().all()

    # Ausstattung ermitteln (Typ-Namen aus InvestitionTyp Enum)
    hat_speicher = any(inv.typ == "speicher" for inv in investitionen)
    hat_waermepumpe = any(inv.typ == "waermepumpe" for inv in investitionen)
    hat_eauto = any(inv.typ == "e-auto" for inv in investitionen)
    hat_wallbox = any(inv.typ == "wallbox" for inv in investitionen)
    hat_balkonkraftwerk = any(inv.typ == "balkonkraftwerk" for inv in investitionen)
    hat_sonstiges = any(inv.typ == "sonstiges" for inv in investitionen)

    # Speicherkapazität summieren
    speicher_kwh = sum(
        (inv.parameter or {}).get("kapazitaet_kwh", 0) or 0
        for inv in investitionen
        if inv.typ == "speicher"
    )

    # Wallbox Ladeleistung
    wallbox_kw = None
    wallboxen = [inv for inv in investitionen if inv.typ == "wallbox"]
    if wallboxen:
        wallbox_kw = max(
            (inv.parameter or {}).get("ladeleistung_kw", 0) or 0
            for inv in wallboxen
        )
        if wallbox_kw == 0:
            wallbox_kw = None

    # Balkonkraftwerk Leistung
    bkw_wp = None
    bkws = [inv for inv in investitionen if inv.typ == "balkonkraftwerk"]
    if bkws:
        bkw_wp = sum(
            (inv.parameter or {}).get("leistung_wp", 0) or 0
            for inv in bkws
        )
        if bkw_wp == 0:
            bkw_wp = None

    # Sonstiges Bezeichnung
    sonstiges_bezeichnung = None
    sonstige = [inv for inv in investitionen if inv.typ == "sonstiges"]
    if sonstige:
        bezeichnungen = [inv.bezeichnung for inv in sonstige if inv.bezeichnung]
        sonstiges_bezeichnung = ", ".join(bezeichnungen[:3]) if bezeichnungen else None

    # Durchschnittliche Neigung und Ausrichtung aus PV-Modulen
    pv_module = [inv for inv in investitionen if inv.typ == "pv-module"]
    if pv_module:
        neigungen = [
            (inv.parameter or {}).get("neigung_grad", 30) or 30
            for inv in pv_module
        ]
        neigung_grad = int(sum(neigungen) / len(neigungen))

        azimute = [
            (inv.parameter or {}).get("ausrichtung_grad", 180) or 180
            for inv in pv_module
        ]
        # Prüfen ob gemischt (z.B. Ost-West)
        if max(azimute) - min(azimute) > 45:
            ausrichtung = "ost-west" if any(60 <= a <= 120 for a in azimute) and any(240 <= a <= 300 for a in azimute) else "gemischt"
        else:
            ausrichtung = get_ausrichtung_label(int(sum(azimute) / len(azimute)))
    else:
        neigung_grad = 30
        ausrichtung = "süd"

    # Installation Jahr
    if anlage.installationsdatum:
        installation_jahr = anlage.installationsdatum.year
    else:
        installation_jahr = datetime.now().year

    # Basis-Daten
    data = {
        "region": region,
        "kwp": round(anlage.leistung_kwp or 0, 1),
        "ausrichtung": ausrichtung,
        "neigung_grad": neigung_grad,
        "speicher_kwh": round(speicher_kwh, 1) if speicher_kwh > 0 else None,
        "installation_jahr": installation_jahr,
        "hat_waermepumpe": hat_waermepumpe,
        "hat_eauto": hat_eauto,
        "hat_wallbox": hat_wallbox,
        "hat_balkonkraftwerk": hat_balkonkraftwerk,
        "hat_sonstiges": hat_sonstiges,
        "wallbox_kw": wallbox_kw,
        "bkw_wp": bkw_wp,
        "sonstiges_bezeichnung": sonstiges_bezeichnung,
        "monatswerte": [],
    }

    # Monatswerte laden wenn gewünscht
    if include_monatswerte:
        result = await db.execute(
            select(Monatsdaten)
            .where(Monatsdaten.anlage_id == anlage_id)
            .order_by(Monatsdaten.jahr, Monatsdaten.monat)
        )
        monatsdaten = result.scalars().all()

        # InvestitionMonatsdaten für alle Komponenten vorladen
        inv_md_result = await db.execute(
            select(InvestitionMonatsdaten, Investition.typ)
            .join(Investition)
            .where(Investition.anlage_id == anlage_id)
        )
        inv_monatsdaten = inv_md_result.all()

        # Nach Jahr/Monat gruppieren
        inv_by_month: dict[tuple[int, int], list[tuple]] = {}
        for inv_md, inv_typ in inv_monatsdaten:
            key = (inv_md.jahr, inv_md.monat)
            if key not in inv_by_month:
                inv_by_month[key] = []
            inv_by_month[key].append((inv_md, inv_typ))

        for md in monatsdaten:
            key = (md.jahr, md.monat)
            month_inv_data = inv_by_month.get(key, [])

            # PV-Erzeugung aggregieren
            pv_erzeugung = sum(
                (inv_md.verbrauch_daten or {}).get("pv_erzeugung_kwh", 0) or 0
                for inv_md, typ in month_inv_data if typ == "pv-module"
            )

            # Speicher-KPIs aggregieren
            speicher_ladung = sum(
                (inv_md.verbrauch_daten or {}).get("ladung_kwh", 0) or 0
                for inv_md, typ in month_inv_data if typ == "speicher"
            )
            speicher_entladung = sum(
                (inv_md.verbrauch_daten or {}).get("entladung_kwh", 0) or 0
                for inv_md, typ in month_inv_data if typ == "speicher"
            )
            speicher_ladung_netz = sum(
                (inv_md.verbrauch_daten or {}).get("ladung_netz_kwh", 0) or 0
                for inv_md, typ in month_inv_data if typ == "speicher"
            )

            # Wärmepumpe-KPIs aggregieren
            wp_stromverbrauch = sum(
                (inv_md.verbrauch_daten or {}).get("stromverbrauch_kwh", 0) or 0
                for inv_md, typ in month_inv_data if typ == "waermepumpe"
            )
            wp_heizwaerme = sum(
                (inv_md.verbrauch_daten or {}).get("heizenergie_kwh", 0) or 0
                for inv_md, typ in month_inv_data if typ == "waermepumpe"
            )
            wp_warmwasser = sum(
                (inv_md.verbrauch_daten or {}).get("warmwasser_kwh", 0) or 0
                for inv_md, typ in month_inv_data if typ == "waermepumpe"
            )

            # E-Auto-KPIs aggregieren
            eauto_ladung_pv = sum(
                (inv_md.verbrauch_daten or {}).get("ladung_pv_kwh", 0) or 0
                for inv_md, typ in month_inv_data if typ == "e-auto"
            )
            eauto_ladung_netz = sum(
                (inv_md.verbrauch_daten or {}).get("ladung_netz_kwh", 0) or 0
                for inv_md, typ in month_inv_data if typ == "e-auto"
            )
            eauto_ladung_extern = sum(
                (inv_md.verbrauch_daten or {}).get("ladung_extern_kwh", 0) or 0
                for inv_md, typ in month_inv_data if typ == "e-auto"
            )
            eauto_km = sum(
                (inv_md.verbrauch_daten or {}).get("km_gefahren", 0) or 0
                for inv_md, typ in month_inv_data if typ == "e-auto"
            )
            eauto_v2h = sum(
                (inv_md.verbrauch_daten or {}).get("v2h_entladung_kwh", 0) or 0
                for inv_md, typ in month_inv_data if typ == "e-auto"
            )
            eauto_ladung_gesamt = eauto_ladung_pv + eauto_ladung_netz + eauto_ladung_extern

            # Wallbox-KPIs aggregieren
            wallbox_ladung = sum(
                (inv_md.verbrauch_daten or {}).get("ladung_kwh", 0) or 0
                for inv_md, typ in month_inv_data if typ == "wallbox"
            )
            wallbox_ladung_pv = sum(
                (inv_md.verbrauch_daten or {}).get("ladung_pv_kwh", 0) or 0
                for inv_md, typ in month_inv_data if typ == "wallbox"
            )
            wallbox_ladevorgaenge = sum(
                (inv_md.verbrauch_daten or {}).get("ladevorgaenge", 0) or 0
                for inv_md, typ in month_inv_data if typ == "wallbox"
            )

            # Balkonkraftwerk-KPIs aggregieren
            bkw_erzeugung = sum(
                (inv_md.verbrauch_daten or {}).get("pv_erzeugung_kwh", 0) or 0
                for inv_md, typ in month_inv_data if typ == "balkonkraftwerk"
            )
            bkw_eigenverbrauch = sum(
                (inv_md.verbrauch_daten or {}).get("eigenverbrauch_kwh", 0) or 0
                for inv_md, typ in month_inv_data if typ == "balkonkraftwerk"
            )
            bkw_speicher_ladung = sum(
                (inv_md.verbrauch_daten or {}).get("speicher_ladung_kwh", 0) or 0
                for inv_md, typ in month_inv_data if typ == "balkonkraftwerk"
            )
            bkw_speicher_entladung = sum(
                (inv_md.verbrauch_daten or {}).get("speicher_entladung_kwh", 0) or 0
                for inv_md, typ in month_inv_data if typ == "balkonkraftwerk"
            )

            # Sonstiges-KPIs aggregieren
            sonstiges_verbrauch = sum(
                (inv_md.verbrauch_daten or {}).get("stromverbrauch_kwh", 0) or 0
                for inv_md, typ in month_inv_data if typ == "sonstiges"
            )

            # Autarkie und Eigenverbrauch berechnen
            einspeisung = md.einspeisung_kwh or 0
            netzbezug = md.netzbezug_kwh or 0
            eigenverbrauch = pv_erzeugung - einspeisung if pv_erzeugung > 0 else 0
            gesamtverbrauch = eigenverbrauch + netzbezug

            autarkie = (eigenverbrauch / gesamtverbrauch * 100) if gesamtverbrauch > 0 else None
            ev_quote = (eigenverbrauch / pv_erzeugung * 100) if pv_erzeugung > 0 else None

            if pv_erzeugung > 0 or einspeisung > 0 or netzbezug > 0:
                monatswert_data = {
                    "jahr": md.jahr,
                    "monat": md.monat,
                    "ertrag_kwh": round(pv_erzeugung, 1),
                    "einspeisung_kwh": round(einspeisung, 1) if einspeisung else None,
                    "netzbezug_kwh": round(netzbezug, 1) if netzbezug else None,
                    "autarkie_prozent": round(autarkie, 1) if autarkie is not None else None,
                    "eigenverbrauch_prozent": round(ev_quote, 1) if ev_quote is not None else None,
                }

                # Speicher-KPIs (nur wenn vorhanden)
                if speicher_ladung > 0 or speicher_entladung > 0:
                    monatswert_data["speicher_ladung_kwh"] = round(speicher_ladung, 1)
                    monatswert_data["speicher_entladung_kwh"] = round(speicher_entladung, 1)
                    if speicher_ladung_netz > 0:
                        monatswert_data["speicher_ladung_netz_kwh"] = round(speicher_ladung_netz, 1)

                # Wärmepumpe-KPIs (nur wenn vorhanden)
                if wp_stromverbrauch > 0:
                    monatswert_data["wp_stromverbrauch_kwh"] = round(wp_stromverbrauch, 1)
                    if wp_heizwaerme > 0:
                        monatswert_data["wp_heizwaerme_kwh"] = round(wp_heizwaerme, 1)
                    if wp_warmwasser > 0:
                        monatswert_data["wp_warmwasser_kwh"] = round(wp_warmwasser, 1)

                # E-Auto-KPIs (nur wenn vorhanden)
                if eauto_ladung_gesamt > 0:
                    monatswert_data["eauto_ladung_gesamt_kwh"] = round(eauto_ladung_gesamt, 1)
                    if eauto_ladung_pv > 0:
                        monatswert_data["eauto_ladung_pv_kwh"] = round(eauto_ladung_pv, 1)
                    if eauto_ladung_extern > 0:
                        monatswert_data["eauto_ladung_extern_kwh"] = round(eauto_ladung_extern, 1)
                    if eauto_km > 0:
                        monatswert_data["eauto_km"] = round(eauto_km, 1)
                    if eauto_v2h > 0:
                        monatswert_data["eauto_v2h_kwh"] = round(eauto_v2h, 1)

                # Wallbox-KPIs (nur wenn vorhanden)
                if wallbox_ladung > 0:
                    monatswert_data["wallbox_ladung_kwh"] = round(wallbox_ladung, 1)
                    if wallbox_ladung_pv > 0:
                        monatswert_data["wallbox_ladung_pv_kwh"] = round(wallbox_ladung_pv, 1)
                    if wallbox_ladevorgaenge > 0:
                        monatswert_data["wallbox_ladevorgaenge"] = wallbox_ladevorgaenge

                # Balkonkraftwerk-KPIs (nur wenn vorhanden)
                if bkw_erzeugung > 0:
                    monatswert_data["bkw_erzeugung_kwh"] = round(bkw_erzeugung, 1)
                    if bkw_eigenverbrauch > 0:
                        monatswert_data["bkw_eigenverbrauch_kwh"] = round(bkw_eigenverbrauch, 1)
                    if bkw_speicher_ladung > 0:
                        monatswert_data["bkw_speicher_ladung_kwh"] = round(bkw_speicher_ladung, 1)
                    if bkw_speicher_entladung > 0:
                        monatswert_data["bkw_speicher_entladung_kwh"] = round(bkw_speicher_entladung, 1)

                # Sonstiges-KPIs (nur wenn vorhanden)
                if sonstiges_verbrauch > 0:
                    monatswert_data["sonstiges_verbrauch_kwh"] = round(sonstiges_verbrauch, 1)

                data["monatswerte"].append(monatswert_data)

    return data


async def get_community_preview(db: AsyncSession, anlage_id: int) -> dict | None:
    """
    Gibt eine Vorschau der zu teilenden Daten zurück.
    """
    data = await prepare_community_data(db, anlage_id)
    if not data:
        return None

    return {
        "vorschau": data,
        "anzahl_monate": len(data.get("monatswerte", [])),
        "community_url": COMMUNITY_SERVER_URL,
    }
