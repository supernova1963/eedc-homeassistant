"""
EEDC Berechnungslogik

Alle Formeln für Kennzahlen, Einsparungen und Auswertungen.
"""

from dataclasses import dataclass
from typing import Optional


# =============================================================================
# Konstanten
# =============================================================================

CO2_FAKTOR_STROM_KG_KWH = 0.38  # kg CO2 pro kWh (deutscher Strommix)
CO2_FAKTOR_BENZIN_KG_LITER = 2.37  # kg CO2 pro Liter Benzin
CO2_FAKTOR_GAS_KG_KWH = 0.201  # kg CO2 pro kWh Erdgas
CO2_FAKTOR_OEL_KG_KWH = 0.266  # kg CO2 pro kWh Heizöl

SPEICHER_ZYKLEN_PRO_JAHR = 250  # Typische Vollzyklen pro Jahr


# =============================================================================
# Datenklassen für Ergebnisse
# =============================================================================

@dataclass
class MonatsKennzahlen:
    """Berechnete Kennzahlen für einen Monat."""

    # Energie (kWh)
    direktverbrauch_kwh: float
    gesamtverbrauch_kwh: float
    eigenverbrauch_kwh: float

    # Quoten (%)
    eigenverbrauchsquote_prozent: float
    autarkiegrad_prozent: float

    # Spezifischer Ertrag
    spezifischer_ertrag_kwh_kwp: Optional[float]

    # Finanzen (Euro)
    einspeise_erloes_euro: float
    netzbezug_kosten_euro: float
    eigenverbrauch_ersparnis_euro: float
    netto_ertrag_euro: float

    # Umwelt
    co2_einsparung_kg: float


@dataclass
class SpeicherEinsparung:
    """Berechnete Einsparung für einen Speicher."""
    jahres_einsparung_euro: float
    nutzbare_speicherung_kwh: float
    pv_anteil_euro: float
    arbitrage_anteil_euro: float
    co2_einsparung_kg: float


@dataclass
class EAutoEinsparung:
    """Berechnete Einsparung für ein E-Auto."""
    jahres_einsparung_euro: float
    strom_kosten_euro: float
    benzin_kosten_alternativ_euro: float
    co2_einsparung_kg: float
    v2h_einsparung_euro: float


@dataclass
class WaermepumpeEinsparung:
    """Berechnete Einsparung für eine Wärmepumpe."""
    jahres_einsparung_euro: float
    wp_kosten_euro: float
    alte_heizung_kosten_euro: float
    co2_einsparung_kg: float


# =============================================================================
# Berechnungsfunktionen
# =============================================================================

def berechne_monatskennzahlen(
    # Eingabewerte (kWh)
    einspeisung_kwh: float,
    netzbezug_kwh: float,
    pv_erzeugung_kwh: float,
    batterie_ladung_kwh: float = 0,
    batterie_entladung_kwh: float = 0,
    v2h_entladung_kwh: float = 0,
    # Preise (Cent/kWh)
    einspeiseverguetung_cent: float = 8.2,
    netzbezug_preis_cent: float = 30.0,
    # Anlage
    leistung_kwp: Optional[float] = None,
) -> MonatsKennzahlen:
    """
    Berechnet alle Kennzahlen für einen Monat.

    Formeln:
    ---------
    Direktverbrauch = PV-Erzeugung - Einspeisung - Batterieladung
    Eigenverbrauch = Direktverbrauch + Batterieentladung + V2H-Entladung
    Gesamtverbrauch = Eigenverbrauch + Netzbezug
    EV-Quote = Eigenverbrauch / PV-Erzeugung × 100
    Autarkie = Eigenverbrauch / Gesamtverbrauch × 100

    Args:
        einspeisung_kwh: Ins Netz eingespeiste Energie
        netzbezug_kwh: Aus dem Netz bezogene Energie
        pv_erzeugung_kwh: Gesamte PV-Erzeugung
        batterie_ladung_kwh: In Batterie geladene Energie
        batterie_entladung_kwh: Aus Batterie entladene Energie
        v2h_entladung_kwh: Aus E-Auto ins Haus entladene Energie (V2H)
        einspeiseverguetung_cent: Vergütung pro kWh in Cent
        netzbezug_preis_cent: Strompreis pro kWh in Cent
        leistung_kwp: Anlagenleistung in kWp (für spezifischen Ertrag)

    Returns:
        MonatsKennzahlen: Alle berechneten Werte
    """
    # Energie-Berechnungen
    direktverbrauch = pv_erzeugung_kwh - einspeisung_kwh - batterie_ladung_kwh
    direktverbrauch = max(0, direktverbrauch)  # Kann nicht negativ sein

    eigenverbrauch = direktverbrauch + batterie_entladung_kwh + v2h_entladung_kwh
    gesamtverbrauch = eigenverbrauch + netzbezug_kwh

    # Quoten berechnen
    ev_quote = (eigenverbrauch / pv_erzeugung_kwh * 100) if pv_erzeugung_kwh > 0 else 0
    autarkie = (eigenverbrauch / gesamtverbrauch * 100) if gesamtverbrauch > 0 else 0

    # Spezifischer Ertrag (kWh pro kWp)
    spez_ertrag = (pv_erzeugung_kwh / leistung_kwp) if leistung_kwp and leistung_kwp > 0 else None

    # Finanzielle Berechnungen (Cent -> Euro)
    einspeise_erloes = einspeisung_kwh * einspeiseverguetung_cent / 100
    netzbezug_kosten = netzbezug_kwh * netzbezug_preis_cent / 100
    ev_ersparnis = eigenverbrauch * netzbezug_preis_cent / 100
    netto_ertrag = einspeise_erloes + ev_ersparnis - netzbezug_kosten

    # CO2-Einsparung
    co2_einsparung = pv_erzeugung_kwh * CO2_FAKTOR_STROM_KG_KWH

    return MonatsKennzahlen(
        direktverbrauch_kwh=round(direktverbrauch, 2),
        gesamtverbrauch_kwh=round(gesamtverbrauch, 2),
        eigenverbrauch_kwh=round(eigenverbrauch, 2),
        eigenverbrauchsquote_prozent=round(ev_quote, 1),
        autarkiegrad_prozent=round(autarkie, 1),
        spezifischer_ertrag_kwh_kwp=round(spez_ertrag, 1) if spez_ertrag else None,
        einspeise_erloes_euro=round(einspeise_erloes, 2),
        netzbezug_kosten_euro=round(netzbezug_kosten, 2),
        eigenverbrauch_ersparnis_euro=round(ev_ersparnis, 2),
        netto_ertrag_euro=round(netto_ertrag, 2),
        co2_einsparung_kg=round(co2_einsparung, 1),
    )


def berechne_speicher_einsparung(
    kapazitaet_kwh: float,
    wirkungsgrad_prozent: float,
    netzbezug_preis_cent: float,
    einspeiseverguetung_cent: float,
    nutzt_arbitrage: bool = False,
    lade_preis_cent: float = 0,
    entlade_preis_cent: float = 0,
    zyklen_pro_jahr: int = SPEICHER_ZYKLEN_PRO_JAHR,
) -> SpeicherEinsparung:
    """
    Berechnet jährliche Speicher-Einsparung (Prognose).

    Ohne Arbitrage:
        Einsparung = Zyklen × Kapazität × Wirkungsgrad × (Netzbezug - Einspeisung)

    Mit Arbitrage (70/30 Modell):
        70% PV-Anteil: Statt Einspeisung → Eigenverbrauch
        30% Arbitrage: Netzladung mit günstigen Tarifen

    Args:
        kapazitaet_kwh: Speicherkapazität in kWh
        wirkungsgrad_prozent: Wirkungsgrad des Speichers (z.B. 95)
        netzbezug_preis_cent: Normaler Strompreis in Cent
        einspeiseverguetung_cent: Einspeisevergütung in Cent
        nutzt_arbitrage: True wenn dynamische Tarife genutzt werden
        lade_preis_cent: Typischer Ladungspreis bei Arbitrage (z.B. 12 ct nachts)
        entlade_preis_cent: Typischer vermiedener Preis (z.B. 35 ct abends)
        zyklen_pro_jahr: Anzahl Vollzyklen pro Jahr

    Returns:
        SpeicherEinsparung: Berechnete Werte
    """
    wirkungsgrad = wirkungsgrad_prozent / 100
    nutzbare_speicherung = kapazitaet_kwh * zyklen_pro_jahr * wirkungsgrad
    standard_spread = netzbezug_preis_cent - einspeiseverguetung_cent

    if not nutzt_arbitrage:
        # Standard: Eigenverbrauchsoptimierung
        jahres_einsparung = nutzbare_speicherung * standard_spread / 100
        return SpeicherEinsparung(
            jahres_einsparung_euro=round(jahres_einsparung, 2),
            nutzbare_speicherung_kwh=round(nutzbare_speicherung, 1),
            pv_anteil_euro=round(jahres_einsparung, 2),
            arbitrage_anteil_euro=0,
            co2_einsparung_kg=round(nutzbare_speicherung * CO2_FAKTOR_STROM_KG_KWH, 1),
        )

    # 70/30 Modell für Arbitrage
    pv_anteil_kwh = nutzbare_speicherung * 0.70
    arbitrage_anteil_kwh = nutzbare_speicherung * 0.30

    pv_einsparung = pv_anteil_kwh * standard_spread / 100
    arbitrage_spread = entlade_preis_cent - lade_preis_cent
    arbitrage_einsparung = arbitrage_anteil_kwh * arbitrage_spread / 100

    return SpeicherEinsparung(
        jahres_einsparung_euro=round(pv_einsparung + arbitrage_einsparung, 2),
        nutzbare_speicherung_kwh=round(nutzbare_speicherung, 1),
        pv_anteil_euro=round(pv_einsparung, 2),
        arbitrage_anteil_euro=round(arbitrage_einsparung, 2),
        co2_einsparung_kg=round(nutzbare_speicherung * CO2_FAKTOR_STROM_KG_KWH, 1),
    )


def berechne_eauto_einsparung(
    km_jahr: float,
    verbrauch_kwh_100km: float,
    pv_anteil_prozent: float,
    strompreis_cent: float,
    benzinpreis_euro_liter: float,
    benzin_verbrauch_liter_100km: float = 7.0,
    nutzt_v2h: bool = False,
    v2h_entladung_kwh_jahr: float = 0,
    v2h_preis_cent: float = 0,
) -> EAutoEinsparung:
    """
    Berechnet jährliche E-Auto Einsparung vs. Verbrenner.

    Args:
        km_jahr: Jährliche Fahrleistung in km
        verbrauch_kwh_100km: E-Auto Verbrauch pro 100 km
        pv_anteil_prozent: Anteil PV-Strom am Laden (z.B. 60)
        strompreis_cent: Strompreis für Netzladung in Cent
        benzinpreis_euro_liter: Benzinpreis in Euro
        benzin_verbrauch_liter_100km: Verbrenner-Verbrauch pro 100 km
        nutzt_v2h: True wenn V2H aktiviert
        v2h_entladung_kwh_jahr: Jährliche V2H-Entladung ins Haus
        v2h_preis_cent: Vermiedener Strompreis durch V2H

    Returns:
        EAutoEinsparung: Berechnete Werte
    """
    # E-Auto Kosten
    strom_bedarf_kwh = km_jahr * verbrauch_kwh_100km / 100
    pv_anteil = pv_anteil_prozent / 100
    netz_anteil = 1 - pv_anteil

    # PV-Strom ist "kostenlos" (bereits bezahlt durch Anlage)
    strom_kosten = strom_bedarf_kwh * netz_anteil * strompreis_cent / 100

    # Verbrenner-Kosten zum Vergleich
    benzin_verbrauch = km_jahr * benzin_verbrauch_liter_100km / 100
    benzin_kosten = benzin_verbrauch * benzinpreis_euro_liter

    # V2H Einsparung
    v2h_einsparung = v2h_entladung_kwh_jahr * v2h_preis_cent / 100 if nutzt_v2h else 0

    # CO2-Einsparung
    co2_verbrenner = benzin_verbrauch * CO2_FAKTOR_BENZIN_KG_LITER
    co2_eauto = strom_bedarf_kwh * netz_anteil * CO2_FAKTOR_STROM_KG_KWH
    co2_einsparung = co2_verbrenner - co2_eauto

    return EAutoEinsparung(
        jahres_einsparung_euro=round(benzin_kosten - strom_kosten + v2h_einsparung, 2),
        strom_kosten_euro=round(strom_kosten, 2),
        benzin_kosten_alternativ_euro=round(benzin_kosten, 2),
        co2_einsparung_kg=round(co2_einsparung, 1),
        v2h_einsparung_euro=round(v2h_einsparung, 2),
    )


def berechne_waermepumpe_einsparung(
    waermebedarf_kwh: float,
    jaz: float,
    strompreis_cent: float,
    pv_anteil_prozent: float,
    alter_energietraeger: str,  # "gas", "oel", "strom"
    alter_preis_cent_kwh: float,
) -> WaermepumpeEinsparung:
    """
    Berechnet jährliche Wärmepumpen-Einsparung vs. alte Heizung.

    Args:
        waermebedarf_kwh: Jährlicher Wärmebedarf in kWh
        jaz: Jahresarbeitszahl der Wärmepumpe
        strompreis_cent: Strompreis in Cent
        pv_anteil_prozent: Anteil PV-Strom am WP-Verbrauch
        alter_energietraeger: "gas", "oel" oder "strom"
        alter_preis_cent_kwh: Preis des alten Energieträgers in Cent/kWh

    Returns:
        WaermepumpeEinsparung: Berechnete Werte
    """
    # WP-Stromverbrauch
    wp_strom_kwh = waermebedarf_kwh / jaz
    pv_anteil = pv_anteil_prozent / 100
    netz_anteil = 1 - pv_anteil

    wp_kosten = wp_strom_kwh * netz_anteil * strompreis_cent / 100

    # Alte Heizung Kosten
    alte_kosten = waermebedarf_kwh * alter_preis_cent_kwh / 100

    # CO2-Einsparung
    co2_faktoren = {
        "gas": CO2_FAKTOR_GAS_KG_KWH,
        "oel": CO2_FAKTOR_OEL_KG_KWH,
        "strom": CO2_FAKTOR_STROM_KG_KWH,
    }
    co2_alt = waermebedarf_kwh * co2_faktoren.get(alter_energietraeger, 0)
    co2_wp = wp_strom_kwh * netz_anteil * CO2_FAKTOR_STROM_KG_KWH
    co2_einsparung = co2_alt - co2_wp

    return WaermepumpeEinsparung(
        jahres_einsparung_euro=round(alte_kosten - wp_kosten, 2),
        wp_kosten_euro=round(wp_kosten, 2),
        alte_heizung_kosten_euro=round(alte_kosten, 2),
        co2_einsparung_kg=round(co2_einsparung, 1),
    )


def berechne_roi(
    anschaffungskosten: float,
    jahres_einsparung: float,
    alternativkosten: float = 0,
) -> dict:
    """
    Berechnet ROI und Amortisationszeit.

    Args:
        anschaffungskosten: Gesamtkosten der Investition
        jahres_einsparung: Jährliche Einsparung in Euro
        alternativkosten: Kosten die sowieso angefallen wären (z.B. neuer Verbrenner)

    Returns:
        dict: ROI-Prozent und Amortisationszeit in Jahren
    """
    relevante_kosten = anschaffungskosten - alternativkosten

    if relevante_kosten <= 0 or jahres_einsparung <= 0:
        return {
            "roi_prozent": None,
            "amortisation_jahre": None,
        }

    roi = (jahres_einsparung / relevante_kosten) * 100
    amortisation = relevante_kosten / jahres_einsparung

    return {
        "roi_prozent": round(roi, 1),
        "amortisation_jahre": round(amortisation, 1),
    }
