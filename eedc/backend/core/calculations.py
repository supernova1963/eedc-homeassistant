"""
EEDC Berechnungslogik

Alle Formeln für Kennzahlen, Einsparungen und Auswertungen.
"""

from dataclasses import dataclass
from typing import Optional

from backend.core.berechnungen import (
    alter_wirkungsgrad,
    autarkie_prozent,
    berechne_netzbezug_kosten,
    eigenverbrauchsquote_prozent,
    einspeise_erloes_euro,
    ersetzt_keine_heizung,
    gas_kosten_altanlage,
    spezifischer_ertrag_kwh_kwp,
)
from backend.core.berechnungen.phev_anteil import teile_fahrleistung
from backend.core.wirtschaftlichkeit_defaults import (
    BENZIN_VERBRAUCH_DEFAULT_L_100KM,
    EINSPEISEVERGUETUNG_DEFAULT_CENT,
    GASPREIS_DEFAULT_CENT,
    NETZBEZUG_DEFAULT_CENT,
    WP_WIRKUNGSGRAD_GAS_DEFAULT,
)


# =============================================================================
# Konstanten
# =============================================================================

CO2_FAKTOR_STROM_KG_KWH = 0.38  # kg CO2 pro kWh (deutscher Strommix)
CO2_FAKTOR_BENZIN_KG_LITER = 2.37  # kg CO2 pro Liter Benzin
CO2_FAKTOR_GAS_KG_KWH = 0.201  # kg CO2 pro kWh Erdgas
CO2_FAKTOR_OEL_KG_KWH = 0.266  # kg CO2 pro kWh Heizöl

SPEICHER_ZYKLEN_PRO_JAHR = 250  # Typische Vollzyklen pro Jahr

# Graue Herstellungs-Last (CO2) je Investitionstyp — Default-Richtwerte (#284,
# Mittelwerte der Discussion-#284-Tabelle, mit Safi105 abgestimmt). Werden für die
# CO2-Amortisation gegen die kumulierte Betriebs-Einsparung gerechnet. Pro Investition
# über das optionale Feld `graue_last_kg` (Herstellerdatenblatt) übersteuerbar.
# PV/Speicher: voller Herstellungs-Aufwand. WP/E-Auto: nur die DIFFERENZ zur ohnehin
# nötigen Alternative (Gas-/Öl-Heizung bzw. Verbrenner) — sonst amortisiert sich das
# Gerät klimatisch nie, obwohl es ohnehin angeschafft worden wäre.
GRAUE_LAST_PV_KG_PRO_KWP = 1000.0       # × leistung_kwp (inkl. Montage/WR)
GRAUE_LAST_SPEICHER_KG_PRO_KWH = 85.0   # × kapazitaet_kwh (LiFePO4)
GRAUE_LAST_WAERMEPUMPE_KG = 1100.0      # flat/Gerät, Differenz zu Gas/Öl
GRAUE_LAST_EAUTO_KG = 5000.0            # flat/Fahrzeug, Differenz zu Verbrenner


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
    # #331 (PHEV) — additiv ans Ende, Bestandsaufrufer bleiben gültig.
    fossile_kosten_euro: float = 0.0
    km_elektrisch: float = 0.0
    km_verbrenner: float = 0.0


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
    # Preise (Cent/kWh) — Defaults aus dem SoT, nie als Zahl kopieren
    einspeiseverguetung_cent: float = EINSPEISEVERGUETUNG_DEFAULT_CENT,
    netzbezug_preis_cent: float = NETZBEZUG_DEFAULT_CENT,
    # Grundpreis (Euro/Monat) - wird zu den Netzbezugskosten addiert
    grundpreis_euro_monat: float = 0,
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
        grundpreis_euro_monat: Monatlicher Grundpreis in Euro (wird zu Netzbezugskosten addiert)
        leistung_kwp: Anlagenleistung in kWp (für spezifischen Ertrag)

    Returns:
        MonatsKennzahlen: Alle berechneten Werte
    """
    # Energie-Berechnungen
    direktverbrauch = pv_erzeugung_kwh - einspeisung_kwh - batterie_ladung_kwh
    direktverbrauch = max(0, direktverbrauch)  # Kann nicht negativ sein

    eigenverbrauch = direktverbrauch + batterie_entladung_kwh + v2h_entladung_kwh
    gesamtverbrauch = eigenverbrauch + netzbezug_kwh

    # Quoten berechnen (SoT-Primitive, ADR-001)
    ev_quote = eigenverbrauchsquote_prozent(eigenverbrauch, pv_erzeugung_kwh)
    autarkie = autarkie_prozent(eigenverbrauch, gesamtverbrauch)

    # Spezifischer Ertrag (kWh pro kWp)
    spez_ertrag = spezifischer_ertrag_kwh_kwp(pv_erzeugung_kwh, leistung_kwp)

    # Finanzielle Berechnungen (Cent -> Euro). §51-Erlös über SoT (ADR-001, M3);
    # neg_preis_kwh = None — diese Funktion kennt keine Negativpreis-Spalte →
    # volle Einspeisung wie zuvor (verhaltensneutral).
    einspeise_erloes = einspeise_erloes_euro(
        einspeisung_kwh, None, einspeiseverguetung_cent
    ).erloes_euro
    netzbezug_kosten = berechne_netzbezug_kosten(
        netzbezug_kwh, netzbezug_preis_cent, grundpreis_euro_monat
    )
    ev_ersparnis = eigenverbrauch * netzbezug_preis_cent / 100

    # Netto-Ertrag der PV-Anlage:
    # = Einspeise-Erlös + Eigenverbrauch-Ersparnis
    # OHNE Abzug der Netzbezugskosten (diese wären auch ohne PV angefallen)
    netto_ertrag = einspeise_erloes + ev_ersparnis

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
    ist_entladung_kwh: Optional[float] = None,
    ist_ladung_netz_kwh: float = 0,
) -> SpeicherEinsparung:
    """
    Berechnet jährliche Speicher-Einsparung.

    Modi (siehe Issue #264 Etappe B):

    1. **Prognose** (`ist_entladung_kwh=None`, Default) — wie bisher:
       - Ohne Arbitrage: `Zyklen × Kapazität × η × (Bezug − Einspeisung)`
       - Mit Arbitrage: fixes 70/30-Modell aus `lade_preis_cent` / `entlade_preis_cent`

    2. **IST-basiert** (`ist_entladung_kwh` gepflegt): delegiert an den kanonischen
       Spread-Service `speicher_wirtschaftlichkeit.berechne_speicher_ersparnis()`
       — derselbe Helper, den Aussichten verwendet. Damit driften die beiden
       Berechnungspfade (Aussichten ↔ Investitionen-ROI) im IST-Pfad nicht
       mehr auseinander (Drift-Audit D). Der gemessene Netz-Anteil korrigiert
       den Spread, sodass nicht mehr implizit 100 % PV-Ladung unterstellt wird.

    Args:
        kapazitaet_kwh: Speicherkapazität in kWh (für Prognose)
        wirkungsgrad_prozent: Wirkungsgrad des Speichers (z.B. 95)
        netzbezug_preis_cent: Normaler Strompreis in Cent
        einspeiseverguetung_cent: Einspeisevergütung in Cent
        nutzt_arbitrage: True wenn dynamische Tarife genutzt werden (Prognose-Modus)
        lade_preis_cent: Ø-Ladepreis bei Arbitrage (z.B. 12 ct nachts)
        entlade_preis_cent: Vermiedener Preis bei Arbitrage (z.B. 35 ct abends)
        zyklen_pro_jahr: Anzahl Vollzyklen pro Jahr (Prognose-Modus)
        ist_entladung_kwh: Tatsächliche Jahres-Entladung (aggregiert aus IMD) —
            schaltet auf den Spread-Service-Pfad um.
        ist_ladung_netz_kwh: Tatsächliche Jahres-Netzladung (für PV/Netz-Aufteilung)

    Returns:
        SpeicherEinsparung mit gemappten pv_anteil_euro / arbitrage_anteil_euro.
    """
    # --- IST-Modus: Delegation an die kanonische Spread-Berechnung ---
    if ist_entladung_kwh is not None:
        # Lokaler Import hält calculations.py importseitig schlank (der
        # Spread-Helper wird nur im IST-Modus gebraucht).
        from backend.core.berechnungen.speicher_wirtschaftlichkeit import berechne_speicher_ersparnis

        # Im Arbitrage-Modus liefert `lade_preis_cent` den Ø-Ladepreis; sonst None →
        # Netzladung wird im Service als kostenneutral behandelt.
        ladepreis = lade_preis_cent if nutzt_arbitrage and lade_preis_cent > 0 else None

        result = berechne_speicher_ersparnis(
            entladung_kwh=ist_entladung_kwh,
            bezug_preis_cent=netzbezug_preis_cent,
            einspeise_verg_cent=einspeiseverguetung_cent,
            ladung_netz_kwh=ist_ladung_netz_kwh,
            wirkungsgrad_prozent=wirkungsgrad_prozent,
            lade_preis_cent=ladepreis,
        )
        # Der CO2-Vorteil bezieht sich auf die effektiv aus PV-Strom ersetzte
        # Netzenergie — der Netz-Anteil ist nur Tarif-Arbitrage und spart kein CO2.
        co2 = result.pv_anteil_entladung_kwh * CO2_FAKTOR_STROM_KG_KWH
        return SpeicherEinsparung(
            jahres_einsparung_euro=round(result.ersparnis_euro, 2),
            nutzbare_speicherung_kwh=round(ist_entladung_kwh, 1),
            pv_anteil_euro=round(result.pv_anteil_euro, 2),
            arbitrage_anteil_euro=round(result.netz_anteil_euro, 2),
            co2_einsparung_kg=round(co2, 1),
        )

    # --- Prognose-Modus (unverändert) ---
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
    benzin_verbrauch_liter_100km: float = BENZIN_VERBRAUCH_DEFAULT_L_100KM,
    nutzt_v2h: bool = False,
    v2h_entladung_kwh_jahr: float = 0,
    v2h_preis_cent: float = 0,
    eigener_verbrauch_l_100km: Optional[float] = None,
    elektrischer_fahranteil_prozent: Optional[float] = None,
) -> EAutoEinsparung:
    """
    Berechnet jährliche E-Auto Einsparung vs. Verbrenner.

    Args:
        km_jahr: Jährliche Fahrleistung in km
        verbrauch_kwh_100km: E-Auto Verbrauch pro 100 km
        pv_anteil_prozent: Anteil PV-Strom am Laden (z.B. 60)
        strompreis_cent: Strompreis für Netzladung in Cent
        benzinpreis_euro_liter: Benzinpreis in Euro
        benzin_verbrauch_liter_100km: Verbrenner-Verbrauch pro 100 km —
            der **fiktive Vergleichs-Benziner**. ⚠ Der Signatur-Default stand
            bis 2026-08-08 auf 7,0 und widersprach damit dem kanonischen Wert
            7,5 aus `PARAM_E_AUTO_DEFAULTS`, den das Modul-Docstring von
            `eauto_wirtschaftlichkeit.py` als Erfolg beschreibt (N-178). Er war
            tot, solange der einzige Aufrufer den Wert immer übergibt — mit
            #331 wird an dieser Funktion gebaut, also fällt er hier.
        nutzt_v2h: True wenn V2H aktiviert
        v2h_entladung_kwh_jahr: Jährliche V2H-Entladung ins Haus
        v2h_preis_cent: Vermiedener Strompreis durch V2H
        eigener_verbrauch_l_100km: **Real getankter** Verbrauch eines
            Plug-in-Hybrids (#331). `None` ⇒ BEV, jede Zahl bleibt wie vorher.
        elektrischer_fahranteil_prozent: Geschätzter elektrischer Anteil.
            Die Prognose hat keine Messung — hier ist der Prozentwert der
            **einzige** Weg, nicht nur ein Fallback (Entscheidung 4).

    Returns:
        EAutoEinsparung: Berechnete Werte
    """
    # #331: Auf der Prognose-Achse wird der Strombedarf AUS der Fahrleistung
    # abgeleitet — anders als im IST, wo die Ladung gemessen daneben liegt.
    # Deshalb muss der elektrische Anteil hier auch den Bedarf begrenzen: sonst
    # zahlte ein Plug-in-Hybrid in der ROI-Prognose Strom für alle Kilometer
    # UND zusätzlich Benzin für die verbrennergefahrenen — dieselbe Strecke
    # zweimal.
    anteil = teile_fahrleistung(
        km_gefahren=km_jahr,
        anteil_prozent=elektrischer_fahranteil_prozent,
    )

    # E-Auto Kosten
    strom_bedarf_kwh = anteil.km_elektrisch * verbrauch_kwh_100km / 100
    pv_anteil = pv_anteil_prozent / 100
    netz_anteil = 1 - pv_anteil

    # PV-Strom ist "kostenlos" (bereits bezahlt durch Anlage)
    strom_kosten = strom_bedarf_kwh * netz_anteil * strompreis_cent / 100

    # Verbrenner-Kosten zum Vergleich — über ALLE Kilometer, sonst verglichen
    # wir ein Auto mit einem halben Auto (Entscheidung 5).
    benzin_verbrauch = km_jahr * benzin_verbrauch_liter_100km / 100
    benzin_kosten = benzin_verbrauch * benzinpreis_euro_liter

    # #331: die real anfallende Tankrechnung des Verbrenner-Anteils.
    fossil_liter = (
        anteil.km_verbrenner / 100 * eigener_verbrauch_l_100km
        if eigener_verbrauch_l_100km
        else 0.0
    )
    fossile_kosten = fossil_liter * benzinpreis_euro_liter

    # V2H Einsparung
    v2h_einsparung = v2h_entladung_kwh_jahr * v2h_preis_cent / 100 if nutzt_v2h else 0

    # CO2-Einsparung
    co2_verbrenner = benzin_verbrauch * CO2_FAKTOR_BENZIN_KG_LITER
    co2_eauto = strom_bedarf_kwh * netz_anteil * CO2_FAKTOR_STROM_KG_KWH
    co2_einsparung = co2_verbrenner - co2_eauto - fossil_liter * CO2_FAKTOR_BENZIN_KG_LITER

    return EAutoEinsparung(
        jahres_einsparung_euro=round(
            benzin_kosten - strom_kosten - fossile_kosten + v2h_einsparung, 2
        ),
        strom_kosten_euro=round(strom_kosten, 2),
        benzin_kosten_alternativ_euro=round(benzin_kosten, 2),
        co2_einsparung_kg=round(co2_einsparung, 1),
        v2h_einsparung_euro=round(v2h_einsparung, 2),
        fossile_kosten_euro=round(fossile_kosten, 2),
        km_elektrisch=round(anteil.km_elektrisch, 1),
        km_verbrenner=round(anteil.km_verbrenner, 1),
    )


def berechne_waermepumpe_einsparung(
    # Für Modus "gesamt_jaz" (Standard)
    waermebedarf_kwh: float = None,
    jaz: float = None,
    # Für Modus "getrennte_cops"
    heizwaermebedarf_kwh: float = None,
    warmwasserbedarf_kwh: float = None,
    cop_heizung: float = None,
    cop_warmwasser: float = None,
    # Für Modus "scop" (EU-Label)
    scop_heizung: float = None,       # SCOP für gewählte Vorlauftemperatur
    scop_warmwasser: float = None,    # SCOP für Warmwasser (55°C)
    # Modus-Auswahl
    effizienz_modus: str = "gesamt_jaz",
    # Gemeinsame Parameter
    strompreis_cent: float = NETZBEZUG_DEFAULT_CENT,
    pv_anteil_prozent: float = 30.0,
    alter_energietraeger: str = "gas",  # "gas", "oel", "strom"
    alter_preis_cent_kwh: float = GASPREIS_DEFAULT_CENT,
    alternativ_zusatzkosten_jahr: float = 0.0,
) -> WaermepumpeEinsparung:
    """
    Berechnet jährliche Wärmepumpen-Einsparung vs. alte Heizung.

    Modi:
        - gesamt_jaz: Ein JAZ-Wert für den gesamten Wärmebedarf (Standard)
        - getrennte_cops: Separate COPs für Heizung und Warmwasser (Momentanwerte)
        - scop: EU-Label SCOP-Werte (Seasonal COP, realistischer als COP)

    Begriffserklärung:
        - COP (Coefficient of Performance): Momentane Effizienz bei definierten
          Bedingungen (z.B. A7/W35 = 7°C Außentemp, 35°C Vorlauf)
        - SCOP (Seasonal COP): EU-genormter Wert über die Heizperiode, berechnet
          aus verschiedenen Teillast-COPs. Realistischer als COP.
        - JAZ (Jahresarbeitszahl): Tatsächlich gemessene Effizienz über ein Jahr
          am konkreten Standort. Kann vom SCOP abweichen.

    Args:
        waermebedarf_kwh: Jährlicher Gesamtwärmebedarf in kWh (für gesamt_jaz)
        jaz: Jahresarbeitszahl der Wärmepumpe (für gesamt_jaz)
        heizwaermebedarf_kwh: Jährlicher Heizwärmebedarf in kWh
        warmwasserbedarf_kwh: Jährlicher Warmwasserbedarf in kWh
        cop_heizung: COP für Heizung, typisch 3.5-4.5 (für getrennte_cops)
        cop_warmwasser: COP für Warmwasser, typisch 2.5-3.5 (für getrennte_cops)
        scop_heizung: SCOP für Heizung vom EU-Label (für scop)
        scop_warmwasser: SCOP für Warmwasser vom EU-Label (für scop)
        effizienz_modus: "gesamt_jaz", "getrennte_cops" oder "scop"
        strompreis_cent: Strompreis in Cent
        pv_anteil_prozent: Anteil PV-Strom am WP-Verbrauch
        alter_energietraeger: "gas", "oel" oder "strom"
        alter_preis_cent_kwh: Preis des alten Energieträgers in Cent je kWh
            **Brennstoff** (so steht er auf der Gas-/Ölrechnung), nicht je kWh
            abgegebener Wärme — die Umrechnung macht `gas_kosten_altanlage`
            über den Wirkungsgrad der Altanlage.
        alternativ_zusatzkosten_jahr: Fixe Jahreskosten der Alt-Heizung
            (Schornsteinfeger, Wartung, Grundpreis Gaszähler etc.)

    Returns:
        WaermepumpeEinsparung: Berechnete Werte
    """
    # Wärmebedarf vorbereiten
    heiz = heizwaermebedarf_kwh if heizwaermebedarf_kwh is not None else 12000
    ww = warmwasserbedarf_kwh if warmwasserbedarf_kwh is not None else 3000

    # Berechnung je nach Modus
    if effizienz_modus == "scop":
        # SCOP-Modus: EU-Label-Werte (realistischer als momentane COPs)
        scop_h = scop_heizung if scop_heizung is not None else 4.0
        scop_w = scop_warmwasser if scop_warmwasser is not None else 2.8

        gesamt_waermebedarf = heiz + ww

        # Stromverbrauch mit SCOP berechnen
        strom_heizung = heiz / scop_h
        strom_warmwasser = ww / scop_w
        wp_strom_kwh = strom_heizung + strom_warmwasser

    elif effizienz_modus == "getrennte_cops":
        # Getrennte COPs für Heizung und Warmwasser (Momentanwerte)
        cop_h = cop_heizung if cop_heizung is not None else 3.9
        cop_w = cop_warmwasser if cop_warmwasser is not None else 3.0

        gesamt_waermebedarf = heiz + ww

        # Stromverbrauch pro Komponente
        strom_heizung = heiz / cop_h
        strom_warmwasser = ww / cop_w
        wp_strom_kwh = strom_heizung + strom_warmwasser

    else:
        # Standard: Ein JAZ für alles (gemessene Jahresarbeitszahl)
        verwendete_jaz = jaz if jaz is not None else 3.5

        # Gesamtwärmebedarf: explizit oder aus Komponenten
        if waermebedarf_kwh is not None:
            gesamt_waermebedarf = waermebedarf_kwh
        else:
            gesamt_waermebedarf = heiz + ww

        wp_strom_kwh = gesamt_waermebedarf / verwendete_jaz

    # Gemeinsame Berechnungen
    pv_anteil = pv_anteil_prozent / 100
    netz_anteil = 1 - pv_anteil

    wp_kosten = wp_strom_kwh * netz_anteil * strompreis_cent / 100

    # Alte Heizung: Brennstoffkosten über den Layer-SoT + fixe Zusatzkosten
    # (Schornsteinfeger, Wartung, Zähler-Grundpreis).
    #
    # `gesamt_waermebedarf` ist ABGEGEBENE WÄRME, keine Brennstoffmenge — das
    # belegt `wp_strom_kwh = gesamt_waermebedarf / jaz` oben (die JAZ ist als
    # Wärme/Strom definiert) ebenso wie das Formular-Label „Heizwärmebedarf
    # (kWh/Jahr) — aus Energieausweis". Ein Kessel muss dafür `wärme / η`
    # Brennstoff verfeuern; diese Rückrechnung fehlte hier und ließ die
    # ROI-Seite eine andere WP-Ersparnis nennen als Aussichten, HA-Export und
    # WP-Dashboard, die alle über `gas_kosten_altanlage` laufen.
    # N-88/F2b: Ohne ersetzte Heizung gibt es keine Altanlage — weder ihre
    # Brennstoffkosten noch ihre fixen Zusatzkosten. Der Wächter steht hier und
    # nicht in `alter_wirkungsgrad`, weil ein η von 0 die Division darunter
    # sprengen würde und ein η von 1 stillschweigend eine Stromheizung
    # unterstellte. Die Ersparnis ist dann das Negative der WP-Stromkosten —
    # das ist richtig so: Die Anlage kostet Geld und spart nichts ein, das ist
    # bei einem Neubau ohne Vorgängerheizung die wahre Aussage.
    ersetzt_nichts = ersetzt_keine_heizung(alter_energietraeger)
    wirkungsgrad = alter_wirkungsgrad(alter_energietraeger)
    alte_kosten = 0.0 if ersetzt_nichts else (
        gas_kosten_altanlage(gesamt_waermebedarf, wirkungsgrad, alter_preis_cent_kwh)
        + alternativ_zusatzkosten_jahr
    )

    # CO2-Einsparung — dieselbe η-Rückrechnung wie bei den Kosten und wie im
    # gemessenen Pfad (`co2_wp_ersparnis_kg`, DI-1): verbrannt wird der
    # Brennstoff, nicht die Nutzwärme.
    co2_faktoren = {
        "gas": CO2_FAKTOR_GAS_KG_KWH,
        "oel": CO2_FAKTOR_OEL_KG_KWH,
        "strom": CO2_FAKTOR_STROM_KG_KWH,
    }
    co2_alt = 0.0 if ersetzt_nichts else (
        gesamt_waermebedarf / wirkungsgrad * co2_faktoren.get(alter_energietraeger, 0)
    )
    co2_wp = wp_strom_kwh * netz_anteil * CO2_FAKTOR_STROM_KG_KWH
    co2_einsparung = co2_alt - co2_wp

    return WaermepumpeEinsparung(
        jahres_einsparung_euro=round(alte_kosten - wp_kosten, 2),
        wp_kosten_euro=round(wp_kosten, 2),
        alte_heizung_kosten_euro=round(alte_kosten, 2),
        co2_einsparung_kg=round(co2_einsparung, 1),
    )


def co2_wp_ersparnis_kg(
    wp_waerme_kwh: float,
    wp_strom_kwh: float,
    alter_energietraeger: Optional[str] = None,
    strom_kuehlen_kwh: float = 0.0,
) -> float:
    """Kanonische CO₂-Ersparnis einer Wärmepumpe aus GEMESSENEN Werten (kg).

    Vermiedenes Gas-CO₂ (die abgegebene Wärme über den Gas-Kessel-Wirkungsgrad
    in Brennstoff zurückgerechnet) MINUS das tatsächliche Strom-CO₂ der WP:

        wärme / η_gas × f_gas  −  strom × f_strom

    Einzige erlaubte Konstruktions-Stelle dieser Kennzahl (ADR-001, DI-1).
    Cockpit, Social-Share und der WeasyPrint-Jahresbericht rufen ausschließlich
    hier auf — sonst driftet der Wert: der Jahresbericht rechnete früher
    `wärme × f_gas` OHNE Wirkungsgrad-Umrechnung UND OHNE Strom-Abzug und wies
    die WP-CO₂-Ersparnis dadurch deutlich zu hoch aus (Demo 2025: 2280,7 → 1567,1 kg).

    Args:
        wp_waerme_kwh: Gemessene abgegebene Wärme (Heizung + Warmwasser).
        wp_strom_kwh: Gemessener Stromverbrauch der WP.
        strom_kuehlen_kwh: #263 K-2 (Entscheid E-B) — der Anteil, der in den
            **Kühlbetrieb** ging. Er wird abgezogen, **bevor** das Strom-CO₂
            gegen das vermiedene Gas gestellt wird. Default 0.0 = kein Split
            erfasst, Verhalten wie bisher.

            ⚑ **Warum, an einer Instanz gemessen:** Eine Klimaanlage mit
            26,4 kWh Heizen und 158,4 kWh Kühlen wies **−52 kg** CO₂-Ersparnis
            aus — der Kühlstrom wurde gegen die vermiedene Gasheizung
            gerechnet. Derselbe Kategorienfehler wie bei den Kosten (E-B):
            Kühlen ersetzt keine Heizung, es verursacht seine eigene Emission.
            Die zählt in der Anlagen-CO₂-Bilanz über den Stromverbrauch mit,
            aber nicht als schlechtere **Heiz**bilanz.

    Args (Fortsetzung):
        alter_energietraeger: ``Investition.parameter['alter_energietraeger']``.
            Bei ``"nichts"`` gibt es keine vermiedene Verbrennung und damit
            keine CO₂-Ersparnis (N-88/F2b). Der Parameter ist optional, damit
            Alt-Aufrufer unverändert weiterlaufen — er gehört aber übergeben:
            Diese Funktion ist die einzige erlaubte Konstruktions-Stelle, und
            ein Filter in den zwei Aufrufern wäre genau die Duplizierung, die
            DI-1 hier abgeschafft hat.

    Returns:
        CO₂-Ersparnis in kg, ungerundet. Kann bei sehr schlechter JAZ negativ
        werden; die Anzeige-Sites zeigen die Komponente roh, klammern aber die
        CO₂-Gesamtbilanz per ``max(0, …)``.
    """
    if wp_waerme_kwh <= 0:
        return 0.0
    if ersetzt_keine_heizung(alter_energietraeger):
        return 0.0
    vermiedenes_gas_co2 = (
        wp_waerme_kwh / WP_WIRKUNGSGRAD_GAS_DEFAULT * CO2_FAKTOR_GAS_KG_KWH
    )
    # E-B: nur der Strom, der die Gasheizung tatsächlich ersetzt hat.
    heiz_strom_kwh = max(0.0, wp_strom_kwh - min(max(strom_kuehlen_kwh, 0.0), max(wp_strom_kwh, 0.0)))
    wp_strom_co2 = heiz_strom_kwh * CO2_FAKTOR_STROM_KG_KWH
    return vermiedenes_gas_co2 - wp_strom_co2


def co2_emob_ersparnis_kg(
    benzin_verbrauch_liter: float,
    emob_netz_ladung_kwh: float,
    emob_km: float,
) -> float:
    """Kanonische CO₂-Ersparnis der E-Mobilität aus GEMESSENEN Werten (kg).

    Vermiedenes Verbrenner-CO₂ (Benzinverbrauch des Vergleichs-Verbrenners)
    MINUS das Netz-CO₂ der Heim-Netzladung. PV-Ladung ist bewusst CO₂-frei
    (bereits über die PV-Bilanz gutgeschrieben), daher nur der Netz-Anteil.
    Nur wenn tatsächlich Kilometer gefahren wurden (`emob_km > 0`).

    Args:
        benzin_verbrauch_liter: Σ über die Fahrzeuge von
            `km/100 × Vergleichsverbrauch_l_100km` (je Fahrzeug sein eigener Wert).
        emob_netz_ladung_kwh: Heim-Netzladung (Pool-Netz-Anteil) in kWh.
        emob_km: gefahrene Kilometer (nur als Aktiv-Schalter).

    Returns:
        CO₂-Ersparnis in kg, ungerundet (kann bei viel Netzladung negativ werden).
    """
    if emob_km <= 0:
        return 0.0
    return (
        benzin_verbrauch_liter * CO2_FAKTOR_BENZIN_KG_LITER
        - emob_netz_ladung_kwh * CO2_FAKTOR_STROM_KG_KWH
    )


@dataclass
class Co2Bilanz:
    """CO₂-Ersparnis-Bilanz aus gemessenen Werten (kg), ungerundet.

    `co2_gesamt_kg` klammert die WP- und E-Mob-Komponente per ``max(0, …)`` —
    die Einzel-Komponenten bleiben roh (können negativ sein), damit eine schlecht
    laufende WP / viel-Netz-ladendes E-Auto sichtbar bleibt, ohne die Gesamt-
    Bilanz zu drücken.
    """

    co2_pv_kg: float
    co2_wp_kg: float
    co2_emob_kg: float
    co2_gesamt_kg: float


def berechne_co2_bilanz(
    *,
    eigenverbrauch_kwh: float,
    wp_waerme_kwh: float = 0.0,
    wp_strom_kwh: float = 0.0,
    emob_km: float = 0.0,
    emob_netz_ladung_kwh: float = 0.0,
    benzin_verbrauch_liter: float = 0.0,
    fossil_getankt_liter: float = 0.0,
    wp_strom_kuehlen_kwh: float = 0.0,
) -> Co2Bilanz:
    """Kanonische CO₂-Gesamtbilanz (PV-Eigenverbrauch + WP + E-Mobilität).

    Einzige erlaubte Konstruktions-Stelle der CO₂-Gesamt-Kennzahl (ADR-001,
    DI-2). Cockpit und HA-Export rufen ausschließlich hier auf, damit der in
    Home Assistant exportierte „CO₂ Einsparung"-Sensor exakt die Cockpit-Kachel
    trägt (vorher nur `pv_erzeugung × f_strom`, WP + E-Mob fehlten ganz).

    Die Aufrufer aggregieren die Eingaben (Eigenverbrauch, WP-Wärme/-Strom,
    E-Mob-km/-Netzladung/-Benzinverbrauch) jeweils selbst — sie müssen dazu
    dieselben SoT-Helfer nutzen (`berechne_verbrauchs_kennzahlen`,
    `get_emob_heimladung_canonical`, Dienstwagen-Ausschluss), sonst driftet die
    Eingabe (Lehre #326).

    `fossil_getankt_liter` ist der **real verfahrene** Kraftstoff eines
    Plug-in-Hybrids (#331): er mindert die vermiedene Emission, statt sie zu
    schmälern, indem an der Vergleichsrechnung gedreht würde. Ohne gepflegtes
    `eigener_verbrauch_l_100km` ist er 0 und die Bilanz exakt die von vorher.
    """
    co2_pv = eigenverbrauch_kwh * CO2_FAKTOR_STROM_KG_KWH
    # #263 K-2 (E-B): Kühlstrom ersetzt keine Heizung — er zählt über den
    # Eigenverbrauch in der Bilanz mit, aber nicht als schlechtere Heizbilanz.
    co2_wp = co2_wp_ersparnis_kg(
        wp_waerme_kwh, wp_strom_kwh, strom_kuehlen_kwh=wp_strom_kuehlen_kwh
    )
    co2_emob = co2_emob_ersparnis_kg(
        benzin_verbrauch_liter, emob_netz_ladung_kwh, emob_km
    ) - max(0.0, fossil_getankt_liter) * CO2_FAKTOR_BENZIN_KG_LITER
    co2_gesamt = co2_pv + max(0.0, co2_wp) + max(0.0, co2_emob)
    return Co2Bilanz(
        co2_pv_kg=co2_pv,
        co2_wp_kg=co2_wp,
        co2_emob_kg=co2_emob,
        co2_gesamt_kg=co2_gesamt,
    )


def berechne_roi(
    anschaffungskosten: float,
    jahres_einsparung: float,
    alternativkosten: float = 0,
    betriebskosten_jahr: float = 0,
) -> dict:
    """
    Berechnet ROI und Amortisationszeit.

    Args:
        anschaffungskosten: Gesamtkosten der Investition
        jahres_einsparung: Jährliche Einsparung in Euro (brutto)
        alternativkosten: Kosten die sowieso angefallen wären (z.B. neuer Verbrenner)
        betriebskosten_jahr: Jährliche Betriebskosten (Wartung, Versicherung etc.)

    Returns:
        dict: ROI-Prozent und Amortisationszeit in Jahren
    """
    relevante_kosten = anschaffungskosten - alternativkosten
    netto_einsparung = jahres_einsparung - betriebskosten_jahr

    if relevante_kosten <= 0 or netto_einsparung <= 0:
        return {
            "roi_prozent": None,
            "amortisation_jahre": None,
        }

    roi = (netto_einsparung / relevante_kosten) * 100
    amortisation = relevante_kosten / netto_einsparung

    return {
        "roi_prozent": round(roi, 1),
        "amortisation_jahre": round(amortisation, 1),
    }


# Die USt auf den Eigenverbrauch lag bis 2026-08-04 hier — mit einer
# Bemessungsgrundlage je Aufrufer (N-129) und einem Nenner, der bei
# mehrjährigem Zeitraum gegen eine Ein-Jahres-AfA stand (N-130). Sie ist
# jetzt eine Aggregat-Formel im Berechnungs-Layer (ADR-001):
# `core/berechnungen/ust_eigenverbrauch.py`. Hier bleibt bewusst KEIN
# Spiegel stehen — ein Spiegel ohne Aufrufer ist der Anfang der nächsten
# Drift (Lehre aus N-22 / `calcEinspeiseErloes`).
