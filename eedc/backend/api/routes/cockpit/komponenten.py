"""
Cockpit Komponenten-Zeitreihe — Monatliche Zeitreihe aller Investitions-Komponenten.
"""

from datetime import date
from typing import Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel

from backend.api.deps import get_db
from backend.models.investition import Investition
from backend.core.berechnungen import (
    berechne_netzbezug_kosten,
    eauto_effizienz_100km,
    einspeise_erloes_euro,
)
from backend.api.routes.cockpit._shared import MONATSNAMEN
from backend.services.monats_fakten import MonatsFakt, lade_monats_fakten
from backend.services.wp_wirtschaftlichkeit import berechne_wp_ersparnis

router = APIRouter()

#: Die Gerätetypen, die diese Sicht als Komponente führt. Sie entscheidet
#: mit `MetaFakten.typen_mit_zeile`, ob ein Monat überhaupt eine Zeile bekommt
#: — die Sicht zeigt seit jeher nur Monate, für die eine Komponente (oder eine
#: Finanz-Position) etwas beigetragen hat, nicht jeden Monat mit Zählerzeile.
_KOMPONENTEN_TYPEN = frozenset(
    {"speicher", "waermepumpe", "e-auto", "wallbox", "balkonkraftwerk", "sonstiges"}
)


def _hat_komponenten_zeile(fakt: MonatsFakt) -> bool:
    """Erzeugt dieser Monat eine Zeile in der Komponenten-Zeitreihe?

    Zwei Wege, beide seit jeher im Verhalten dieser Route: eine sichtbare
    IMD-Zeile eines Komponenten-Typs **oder** eine manuell gepflegte
    Finanz-Position (die hängt nicht am Typ — #310 — und kann auch auf der
    Anlage-Ebene liegen, G19-1). Ein Monat mit bloßer Zählerzeile erzeugt
    hier **keine** Zeile; das ist Cockpit → Jahr, nicht diese Sicht.
    """
    if fakt.meta.typen_mit_zeile & _KOMPONENTEN_TYPEN:
        return True
    return bool(fakt.sonstiges.ertraege_euro or fakt.sonstiges.ausgaben_euro)


class KomponentenMonat(BaseModel):
    """Monatswerte für alle Komponenten (NUR aus InvestitionMonatsdaten)."""
    jahr: int
    monat: int
    monat_name: str
    speicher_ladung_kwh: float
    speicher_entladung_kwh: float
    speicher_effizienz_prozent: Optional[float]
    speicher_arbitrage_kwh: float
    speicher_arbitrage_preis_cent: Optional[float]
    wp_waerme_kwh: float
    wp_strom_kwh: float
    wp_cop: Optional[float]
    wp_heizung_kwh: float
    wp_warmwasser_kwh: float
    wp_strom_heizen_kwh: float
    wp_strom_warmwasser_kwh: float
    # WP-Ersparnis vs. fossile Heizung — pro Monat berechnet (Drift-Audit A1).
    # Frontend muss nicht selbst rechnen → Auswertungen→Komponenten + Cockpit nutzen
    # denselben Wert wie Monatsbericht/Übersicht.
    wp_ersparnis_euro: float = 0
    emob_km: float
    emob_ladung_kwh: float
    emob_pv_anteil_prozent: Optional[float]
    emob_ladung_pv_kwh: float
    emob_ladung_netz_kwh: float
    emob_ladung_extern_kwh: float
    emob_ladung_extern_euro: float
    emob_v2h_kwh: float
    # Ø Verbrauch (kWh/100 km) zentral via core/berechnungen/emob.py — gemessener
    # verbrauch_kwh hat Vorrang, sonst Ladungs-Näherung. `quelle` ∈ gemessen|ladung|keine
    # für ehrliches UI-Label; Frontend rechnet NICHT mehr selbst (Drift-Schutz).
    emob_verbrauch_kwh: float = 0
    emob_verbrauch_100km: Optional[float] = None
    emob_verbrauch_quelle: str = "keine"
    bkw_erzeugung_kwh: float
    bkw_eigenverbrauch_kwh: float
    bkw_speicher_ladung_kwh: float
    bkw_speicher_entladung_kwh: float
    sonstiges_erzeugung_kwh: float
    sonstiges_verbrauch_kwh: float
    sonderkosten_euro: float
    sonstige_ertraege_euro: float = 0
    sonstige_ausgaben_euro: float = 0
    sonstige_netto_euro: float = 0
    # G19-1: davon Anlage-Ebene (Monatsdaten.sonstige_positionen) — reiner
    # Ausweis für die Zeile „Anlage (Sonstiges)", bereits in sonstige_* enthalten.
    anlage_sonstige_ertraege_euro: float = 0
    anlage_sonstige_ausgaben_euro: float = 0
    netzbezug_kosten_euro: float = 0
    einspeise_erloes_euro: float = 0


class KomponentenZeitreiheResponse(BaseModel):
    """Zeitreihe aller Komponenten für Auswertungen."""
    anlage_id: int
    hat_speicher: bool
    hat_waermepumpe: bool
    hat_emobilitaet: bool
    hat_balkonkraftwerk: bool
    hat_sonstiges: bool
    hat_arbitrage: bool
    hat_v2h: bool
    monatswerte: list[KomponentenMonat]
    anzahl_monate: int
    # Aggregat über alle Monate via Helper (Σverbrauch/Σladung/Σkm) — Bild „Auswertungen
    # → Komponenten" zeigt diesen Wert, statt im Frontend zu summieren+teilen.
    emob_verbrauch_100km_gesamt: Optional[float] = None
    emob_verbrauch_quelle_gesamt: str = "keine"


@router.get("/komponenten-zeitreihe/{anlage_id}", response_model=KomponentenZeitreiheResponse)
async def get_komponenten_zeitreihe(
    anlage_id: int,
    jahr: Optional[int] = Query(None, description="Jahr filtern (None = alle Jahre)"),
    db: AsyncSession = Depends(get_db)
):
    """Zeitreihe aller Komponenten für Auswertungen."""
    # Die Investitionen werden hier NUR noch für die `hat_*`-Blockschalter und
    # den WP-Referenz-Parameter geladen — die Monatswerte kommen aus der Schicht.
    # Issue #123: historische Zeitreihe — kein aktiv-Filter, damit spätere
    # Stilllegungen Vergangenheitsdaten nicht rückwirkend entfernen. Der
    # `aktiv_im_jahr`-Vorfilter entscheidet, ob ein Block überhaupt erscheint
    # (eine erst 2026 angeschaffte Wärmepumpe blendet den WP-Block in 2025 aus);
    # die Monatswerte filtert die Schicht feiner, nämlich je Monat.
    inv_stmt = select(Investition).where(Investition.anlage_id == anlage_id)
    if jahr is not None:
        from backend.utils.investition_filter import aktiv_im_jahr
        inv_stmt = inv_stmt.where(aktiv_im_jahr(jahr))
    inv_result = await db.execute(inv_stmt)
    investitionen = inv_result.scalars().all()

    hat_speicher = any(i.typ == "speicher" for i in investitionen)
    hat_waermepumpe = any(i.typ == "waermepumpe" for i in investitionen)
    hat_emobilitaet = any(i.typ in ("e-auto", "wallbox") for i in investitionen)
    hat_balkonkraftwerk = any(i.typ == "balkonkraftwerk" for i in investitionen)
    hat_sonstiges = any(i.typ == "sonstiges" for i in investitionen)

    # KEIN Early-Return — auch nicht bei GAR keiner Investition. Bei reinen
    # PV-/WR-Anlagen liefe sonst die Sonstige-Aggregation nicht (#310), und seit
    # G19-1 existieren Basis-Positionen (Anlage-Ebene) auch komplett ohne
    # Investitionen. `lade_monats_fakten` deckt beides ab.
    #
    # ADR-002/P10: die Monatszeile wird GENAU EINMAL aufbereitet — in
    # `services/monats_fakten.py`. Diese Route faltet `InvestitionMonatsdaten`
    # nicht mehr selbst; Zeitfilter (`aktiv` · Anschaffung · Stilllegung),
    # Dienstwagen-Ausschluss, E-Mob-Pool (#262), mengengewichteter Arbitrage-Ø,
    # der getrennt gehaltene BKW-Akku, die typunabhängigen Finanz-Positionen
    # (#310 + G19-1) und der Monatstarif (P8) stecken alle in der Schicht.
    # Der Tarif-Cache wird mitgereicht, damit der Stichtag nur einmal auflöst.
    tarif_cache: dict[date, dict] = {}
    fakten = await lade_monats_fakten(
        db,
        anlage_id,
        von=(jahr, 1) if jahr is not None else None,
        bis=(jahr, 12) if jahr is not None else None,
        tarif_cache=tarif_cache,
    )
    sichtbar = [f for f in fakten if _hat_komponenten_zeile(f)]

    # Flags über ALLE Monate des Zeitraums (nicht je Monat) — dieselbe Aussage
    # wie die frühere Schleifen-Variable, nur aus den Fakten abgeleitet.
    hat_arbitrage = any(f.speicher.netzladung_kwh > 0 for f in sichtbar)
    hat_v2h = any(f.emob.v2h_entladung_kwh > 0 for f in sichtbar)

    monatswerte = []
    # E-Mobilität: Σ über alle Monate für das Komponenten-Aggregat (Ø Verbrauch
    # via Helper über die Summen — nicht das Mittel der Monats-Prozente).
    agg_emob_verbrauch = 0.0
    agg_emob_ladung = 0.0
    agg_emob_km = 0.0

    for f in sichtbar:
        jahr, monat = f.jahr, f.monat
        speicher, emob, wp, sonstiges, tarif = (
            f.speicher, f.emob, f.wp, f.sonstiges, f.tarif
        )

        speicher_effizienz = (
            speicher.entladung_kwh / speicher.ladung_kwh * 100
        ) if speicher.ladung_kwh > 0 else None

        # Mengengewichteter Ø Ladepreis (nur Zeilen mit gepflegtem Preis).
        speicher_arbitrage_preis = speicher.netzladung_preis_cent

        # JAZ/COP nur wenn beide Seiten gemessen sind (siehe uebersicht.py
        # für Erklärung — bei Split-Klimaanlagen kein Wärmemengenzähler).
        wp_cop = (
            wp.waerme_kwh / wp.strom_kwh
        ) if wp.strom_kwh > 0 and wp.waerme_kwh > 0 else None

        emob_pv_anteil = (
            emob.ladung_pv_kwh / emob.ladung_kwh * 100
        ) if emob.ladung_kwh > 0 else None
        # Ø Verbrauch pro Monat via zentralem Helper (gemessen > Ladungs-Näherung).
        eff_m = eauto_effizienz_100km(
            emob.fahrverbrauch_kwh, emob.ladung_kwh, emob.km
        )
        agg_emob_verbrauch += emob.fahrverbrauch_kwh
        agg_emob_ladung += emob.ladung_kwh
        agg_emob_km += emob.km

        if f.meta.hat_zaehlerzeile:
            m_netzbezug_kosten = berechne_netzbezug_kosten(
                f.zaehler.netzbezug_kwh,
                tarif.netzbezug_preis_cent,
                tarif.grundpreis_euro_monat,
            )
            # §51 EEG: Einspeisung in Negativpreis-Stunden ist unvergütet.
            # Ohne Tages-Aggregat (neg_preis_kwh=None) greift die alte Berechnung.
            m_erloes_calc = einspeise_erloes_euro(
                einspeisung_kwh=f.zaehler.einspeisung_kwh,
                neg_preis_kwh=f.eeg.neg_preis_kwh,
                verguetung_ct_kwh=tarif.einspeiseverguetung_cent,
            )
            m_einspeise_erloes = m_erloes_calc.erloes_euro
        else:
            m_netzbezug_kosten = 0.0
            m_einspeise_erloes = 0.0

        # WP-Ersparnis pro Monat (Drift-Audit A1, Issue #178).
        # Aggregat über alle WPs, Parameter aus erster aktiver WP als Referenz.
        m_wp_ersparnis = 0.0
        if wp.waerme_kwh > 0:
            wp_invs_in_monat = [
                i for i in investitionen
                if i.typ == "waermepumpe" and i.ist_aktiv_im_monat(jahr, monat)
            ]
            wp_ref_param = wp_invs_in_monat[0].parameter if wp_invs_in_monat else None
            wp_result = berechne_wp_ersparnis(
                wp_waerme_kwh=wp.waerme_kwh,
                wp_strom_kwh=wp.strom_kwh,
                wp_strompreis_cent=tarif.wp_preis_cent,
                wp_parameter=wp_ref_param,
                monats_gaspreis_cent=tarif.gaspreis_cent_kwh,
            )
            m_wp_ersparnis = wp_result.ersparnis_euro

        monatswerte.append(KomponentenMonat(
            jahr=jahr, monat=monat, monat_name=MONATSNAMEN[monat],
            speicher_ladung_kwh=round(speicher.ladung_kwh, 1),
            speicher_entladung_kwh=round(speicher.entladung_kwh, 1),
            speicher_effizienz_prozent=round(speicher_effizienz, 1) if speicher_effizienz else None,
            speicher_arbitrage_kwh=round(speicher.netzladung_kwh, 1),
            speicher_arbitrage_preis_cent=round(speicher_arbitrage_preis, 2) if speicher_arbitrage_preis else None,
            wp_waerme_kwh=round(wp.waerme_kwh, 1),
            wp_strom_kwh=round(wp.strom_kwh, 1),
            wp_cop=round(wp_cop, 2) if wp_cop else None,
            wp_heizung_kwh=round(wp.heizung_kwh, 1),
            wp_warmwasser_kwh=round(wp.warmwasser_kwh, 1),
            wp_strom_heizen_kwh=round(wp.strom_heizen_kwh, 1),
            wp_strom_warmwasser_kwh=round(wp.strom_warmwasser_kwh, 1),
            wp_ersparnis_euro=round(m_wp_ersparnis, 2),
            emob_km=round(emob.km, 0),
            emob_ladung_kwh=round(emob.ladung_kwh, 1),
            emob_pv_anteil_prozent=round(emob_pv_anteil, 1) if emob_pv_anteil else None,
            emob_ladung_pv_kwh=round(emob.ladung_pv_kwh, 1),
            emob_ladung_netz_kwh=round(emob.ladung_netz_kwh, 1),
            emob_ladung_extern_kwh=round(emob.extern_kwh, 1),
            emob_ladung_extern_euro=round(emob.extern_euro, 2),
            emob_v2h_kwh=round(emob.v2h_entladung_kwh, 1),
            emob_verbrauch_kwh=round(emob.fahrverbrauch_kwh, 1),
            emob_verbrauch_100km=round(eff_m.wert, 1) if eff_m.wert is not None else None,
            emob_verbrauch_quelle=eff_m.quelle,
            bkw_erzeugung_kwh=round(f.bkw.erzeugung_kwh, 1),
            bkw_eigenverbrauch_kwh=round(f.bkw.eigenverbrauch_gemessen_kwh, 1),
            bkw_speicher_ladung_kwh=round(f.bkw.speicher_ladung_kwh, 1),
            bkw_speicher_entladung_kwh=round(f.bkw.speicher_entladung_kwh, 1),
            sonstiges_erzeugung_kwh=round(sonstiges.erzeugung_kwh, 1),
            sonstiges_verbrauch_kwh=round(sonstiges.verbrauch_kwh, 1),
            sonderkosten_euro=sonstiges.ausgaben_euro,
            sonstige_ertraege_euro=sonstiges.ertraege_euro,
            sonstige_ausgaben_euro=sonstiges.ausgaben_euro,
            sonstige_netto_euro=sonstiges.netto_euro,
            anlage_sonstige_ertraege_euro=sonstiges.anlage_ertraege_euro,
            anlage_sonstige_ausgaben_euro=sonstiges.anlage_ausgaben_euro,
            netzbezug_kosten_euro=round(m_netzbezug_kosten, 2),
            einspeise_erloes_euro=round(m_einspeise_erloes, 2),
        ))

    # Aggregat-Effizienz via Helper über die Summen (gemessen > Ladungs-Näherung).
    eff_gesamt = eauto_effizienz_100km(agg_emob_verbrauch, agg_emob_ladung, agg_emob_km)

    return KomponentenZeitreiheResponse(
        anlage_id=anlage_id,
        hat_speicher=hat_speicher, hat_waermepumpe=hat_waermepumpe,
        hat_emobilitaet=hat_emobilitaet, hat_balkonkraftwerk=hat_balkonkraftwerk,
        hat_sonstiges=hat_sonstiges, hat_arbitrage=hat_arbitrage, hat_v2h=hat_v2h,
        monatswerte=monatswerte, anzahl_monate=len(monatswerte),
        emob_verbrauch_100km_gesamt=round(eff_gesamt.wert, 1) if eff_gesamt.wert is not None else None,
        emob_verbrauch_quelle_gesamt=eff_gesamt.quelle,
    )
