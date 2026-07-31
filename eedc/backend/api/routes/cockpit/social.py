"""
Cockpit Social — Kopierfertiger Social-Media-Text für einen Monat.

Wie ``nachhaltigkeit.py`` faltete dieser Endpoint bis 2026-07-31 die ganze
Monatszeile selbst (Befund **F-1**, ADR-002/**P10**) — mit derselben
nachgebauten Eigenverbrauchs-Formel und denselben Lücken: kein V2H (#304),
keine Erzeugung hinter dem Zähler (v3.45.4), kein attribuierter E-Mob-Pool
(#262), das PV-Anlagen-Aggregat roh statt über die Auflösung (P7). Das wog hier
besonders schwer, weil der Text nach **außen** geteilt wird.

Seit dem Umbau kommt die Monatszeile aus ``lade_monats_fakten`` und die
CO₂-Bilanz aus ``berechne_co2_bilanz`` (ADR-001, DI-2).
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel

from backend.core.exceptions import not_found
from backend.api.deps import get_db
from backend.models.anlage import Anlage
from backend.models.investition import Investition
from backend.services.prognose_auswahl import lade_aktive_prognose
from backend.core.investition_kennwerte import get_erzeuger_kwp
from backend.core.berechnungen import spezifischer_ertrag_kwh_kwp
from backend.core.calculations import berechne_co2_bilanz
from backend.services.eauto_wirtschaftlichkeit import km_gewichtete_eauto_params
from backend.services.monats_fakten import lade_monats_fakten
from backend.services.community_service import get_region_from_plz
from backend.api.routes.cockpit._shared import MONATSNAMEN
from backend.core.investition_parameter import ist_dienstlich

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
        raise not_found("Anlage")

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

    # P1 (N53): Der Guard vergleicht die Ausrichtungs-Labels aller Module und
    # zeigt die Ausrichtung nur, wenn sie übereinstimmen — genau die Form, die
    # P1 verlangt. Die daneben aus `pv_module[0].neigung_grad` gezogene Neigung
    # ist **ersatzlos entfallen**: sie war eine Aussage aus EINER Investition
    # ohne eigenen Guard (zwei Module beide Süd, eines 30°, eines 15°) — und in
    # keiner Karten-Variante ausgegeben (tote lokale Variable). Kommt eine
    # Neigungs-Zeile dazu, braucht sie ihren eigenen Übereinstimmungs-Beweis.
    ausrichtung_anzeigen: str | None = None
    if pv_module:
        labels = {_ausrichtung_label(m) for m in pv_module}
        if len(labels) == 1:
            ausrichtung_anzeigen = next(iter(labels))

    # kWp über den SoT-Dispatcher (ADR-002/P3-a): mit dem direkten
    # Spalten-Zugriff fehlte ein nur im `parameter` gepflegtes Modul in der
    # Summe, und der daraus gerechnete spez. Ertrag wurde zu groß. Der
    # BKW-Zweig las zusätzlich weder die Spalte noch `anzahl` — ein 2×400-Wp-BKW
    # erschien als 0,4 statt 0,8 kWp.
    kwp = sum(
        get_erzeuger_kwp(i)
        for i in investitionen
        if i.typ in ("pv-module", "balkonkraftwerk")
    )
    if kwp == 0 and anlage.leistung_kwp:
        kwp = anlage.leistung_kwp

    region_code = get_region_from_plz(anlage.standort_plz, anlage.standort_land)
    bundesland = _REGION_NAMEN.get(region_code, region_code) if region_code else None

    # Die eine Monatszeile aus der Aufbereitungs-Schicht (ADR-002/P10): P7-
    # Auflösung, Zeit- und Dienstwagen-Filter, E-Mob-Pool, V2H und der Erzeuger
    # hinter dem Zähler sind darin bereits angewandt — und der Tarif ist der
    # des Monats (P8), nicht der heutige.
    fakten = await lade_monats_fakten(
        db, anlage_id, von=(jahr, monat), bis=(jahr, monat)
    )
    fakt = next((f for f in fakten if f.meta.hat_zaehlerzeile), None)
    if fakt is None:
        raise HTTPException(status_code=404, detail=f"Keine Monatsdaten für {MONATSNAMEN[monat]} {jahr}")

    # PV-Achse rein (Module + BKW): spezifischer Ertrag und der PVGIS-Vergleich
    # dürfen kein BHKW enthalten. Die Energiebilanz darunter nimmt dagegen
    # `hinter_zaehler_kwh` — beides steckt in `fakt.kennzahlen`.
    pv_erzeugung = fakt.erzeugung.pv_kwh
    einspeisung = fakt.zaehler.einspeisung_kwh
    netzbezug = fakt.zaehler.netzbezug_kwh

    eigenverbrauch = fakt.kennzahlen.eigenverbrauch_kwh
    autarkie = fakt.kennzahlen.autarkie_prozent
    ev_quote = fakt.kennzahlen.eigenverbrauchsquote_prozent
    spez_ertrag = spezifischer_ertrag_kwh_kwp(pv_erzeugung, kwp) or 0

    speicher_ladung = fakt.speicher.ladung_kwh
    speicher_entladung = fakt.speicher.entladung_kwh
    hat_speicher = any(i.typ == "speicher" for i in investitionen)
    speicher_eff = (speicher_entladung / speicher_ladung * 100) if speicher_ladung > 0 else 0

    wp_waerme = fakt.wp.waerme_kwh
    wp_strom = fakt.wp.strom_kwh
    hat_waermepumpe = any(i.typ == "waermepumpe" for i in investitionen)
    # JAZ/COP nur wenn beide Seiten gemessen sind (siehe komponenten.py).
    wp_cop = (wp_waerme / wp_strom) if wp_strom > 0 and wp_waerme > 0 else 0

    emob_km = fakt.emob.km
    hat_emobilitaet = any(
        i.typ in ("e-auto", "wallbox") and not ist_dienstlich(i)
        for i in investitionen
    )
    emob_pv_anteil = (
        fakt.emob.ladung_pv_kwh / fakt.emob.ladung_kwh * 100
    ) if fakt.emob.ladung_kwh > 0 else 0

    # Der Vergleichs-Verbrenner mit dem gepflegten `vergleich_verbrauch_l_100km`
    # je Fahrzeug (km-gewichtet, G20-2) — bis 2026-07-31 standen hier
    # hartkodierte 7 l/100 km.
    eauto_parameter = {i.id: i.parameter for i in investitionen if i.typ == "e-auto"}
    vergleich_l_100km, _ = km_gewichtete_eauto_params(
        eauto_params_und_km=[
            (eauto_parameter.get(inv_id), km)
            for inv_id, km in fakt.emob.km_je_fahrzeug.items()
        ]
    )
    # DI-2: die EINE Konstruktions-Stelle der CO₂-Kennzahl.
    co2 = berechne_co2_bilanz(
        eigenverbrauch_kwh=eigenverbrauch,
        wp_waerme_kwh=wp_waerme,
        wp_strom_kwh=wp_strom,
        emob_km=emob_km,
        emob_netz_ladung_kwh=fakt.emob.ladung_netz_kwh,
        benzin_verbrauch_liter=emob_km / 100 * vergleich_l_100km,
    )
    co2_gesamt = co2.co2_gesamt_kg

    # Tarif DES Monats (ADR-002/P8) — inklusive des abgerechneten Flex-Ø, falls
    # gepflegt. Mit dem heutigen Tarif hätte ein Tarifwechsel jeden rückwirkend
    # geteilten Monat neu bewertet.
    netto_ertrag = (
        einspeisung * fakt.tarif.einspeiseverguetung_cent
        + eigenverbrauch * fakt.tarif.netzbezug_preis_cent
    ) / 100

    # Aktive Prognose über den Auswahl-SoT. Vorher `scalar_one_or_none()` ohne
    # `limit`: zwei aktive Prognosen → `MultipleResultsFound` → HTTP 500 statt
    # der Karte (N85/P5).
    prognose_kwh = None
    pvgis = await lade_aktive_prognose(db, anlage_id)
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
            "Erstellt mit eedc",
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
            "Erstellt mit eedc",
        ]
        text = "\n".join(lines)

    return ShareTextResponse(text=text, variante=variante)
