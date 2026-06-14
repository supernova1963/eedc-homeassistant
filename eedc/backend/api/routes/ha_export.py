"""
Home Assistant Sensor Export API.

Ermöglicht das Exportieren von EEDC-KPIs als HA-Sensoren.
Unterstützt zwei Methoden:
1. REST API - HA liest Werte über rest platform
2. MQTT Discovery - Native HA-Entitäten via MQTT Auto-Discovery
"""

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from typing import Optional, Any
from dataclasses import dataclass
import os

from backend.core.exceptions import not_found
from backend.api.deps import get_db
from backend.core.berechnungen import (
    FinanzMonatsZeile,
    berechne_bkw_alternativkosten_ersparnis,
    berechne_finanz_aggregat,
    berechne_wp_alternativkosten_ersparnis,
    berechne_spez_ertrag_annualisiert,
    gas_kosten_altanlage,
    berechne_verbrauchs_kennzahlen,
    monatsgewichte_aus_pvgis,
)
from backend.models.pvgis_prognose import PVGISPrognose
from backend.api.routes.strompreise import resolve_netzbezug_preis_cent
from backend.services.einspeise_erloes_service import get_neg_preis_einspeisung_monat
from backend.utils.sonstige_positionen import berechne_sonstige_netto
from backend.core.field_definitions import get_emob_pv_netz_kwh, get_wp_strom_kwh
from backend.services.eauto_wirtschaftlichkeit import (
    attribute_month_share,
    build_eauto_km_by_month,
    build_wb_pool_by_month,
)
from backend.models.anlage import Anlage
from backend.services.activity_service import log_activity
from backend.models.monatsdaten import Monatsdaten
from backend.models.investition import Investition, InvestitionMonatsdaten
from backend.utils.investition_filter import aktiv_jetzt
from backend.models.strompreis import Strompreis
from backend.services.ha_sensors_export import (
    SensorDefinition, SensorValue, SensorCategory,
    ANLAGE_SENSOREN, INVESTITION_SENSOREN, E_AUTO_SENSOREN,
    WAERMEPUMPE_SENSOREN, SPEICHER_SENSOREN, LETZTER_IMPORT_SENSOREN,
    PROGNOSE_SENSOREN, PREIS_SENSOREN,
    get_all_sensor_definitions
)
from backend.services.ha_export_prognose import berechne_prognose_export
from backend.services.ha_export_preis import berechne_preis_export
from backend.services.mqtt_client import MQTTClient, MQTTConfig
from backend.services.ha_mqtt_sync import resolve_mqtt_config, publish_anlage_sensors
from backend.core.investition_parameter import (
    PARAM_E_AUTO,
    PARAM_E_AUTO_DEFAULTS,
    PARAM_SPEICHER,
    PARAM_WAERMEPUMPE,
    PARAM_WAERMEPUMPE_DEFAULTS,
    ist_dienstlich,
)
from backend.core.calculations import CO2_FAKTOR_STROM_KG_KWH
from backend.core.wirtschaftlichkeit_defaults import (
    WP_PV_ANTEIL_DEFAULT,
    WP_WIRKUNGSGRAD_GAS_DEFAULT,
    WP_WIRKUNGSGRAD_OEL_DEFAULT,
)

router = APIRouter(prefix="/ha/export", tags=["HA Export"])


# =============================================================================
# Pydantic Models
# =============================================================================

class MQTTConfigRequest(BaseModel):
    """MQTT-Broker Konfiguration (Override; None-Felder fallen auf ENV zurück).

    Felder defaulten bewusst auf None statt `core-mosquitto`/1883: das Frontend
    sendet `config || {}`, ein leeres Objekt soll auf die ENV-Konfiguration
    zurückfallen — nicht auf einen festen Broker zielen (#655 Broker-Mismatch).
    """
    host: Optional[str] = None
    port: Optional[int] = None
    username: Optional[str] = None
    password: Optional[str] = None


class SensorExportItem(BaseModel):
    """Einzelner Sensor im Export."""
    key: str
    name: str
    value: Any
    unit: str
    icon: str
    category: str
    formel: str
    berechnung: Optional[str] = None
    device_class: Optional[str] = None
    state_class: Optional[str] = None


class AnlageExport(BaseModel):
    """Export für eine Anlage."""
    anlage_id: int
    anlage_name: str
    sensors: list[SensorExportItem]


class InvestitionExport(BaseModel):
    """Export für eine Investition."""
    investition_id: int
    bezeichnung: str
    typ: str
    sensors: list[SensorExportItem]


class FullExportResponse(BaseModel):
    """Vollständiger Export aller Sensoren."""
    anlagen: list[AnlageExport]
    investitionen: list[InvestitionExport]
    sensor_count: int
    mqtt_available: bool


class HAYamlSnippet(BaseModel):
    """YAML-Snippet für HA configuration.yaml."""
    yaml: str
    sensor_count: int
    hinweis: str


class MQTTConfigResponse(BaseModel):
    """MQTT-Konfiguration aus Add-on Optionen."""
    enabled: bool
    host: str
    port: int
    username: str
    password: str  # Wird als Maske zurückgegeben wenn gesetzt
    auto_publish: bool
    publish_interval_minutes: int


# =============================================================================
# Hilfsfunktionen für Berechnungen
# =============================================================================

@dataclass
class _EmobPoolCtx:
    """Phase-2a-Pool-Kontext einer Anlage für die HA-Sensor-Berechnung.

    Liegt die E-Mob-Heimladung kanonisch auf der Wallbox (evcc-Setup), sehen die
    per-E-Auto-Sensoren sonst leere IMD → PV-Anteil fehlt, Ersparnis überhöht
    (kein Netz-Strom abgezogen). Mit diesem Kontext zieht jede E-Auto-Sicht den
    km-anteiligen Wallbox-Pool — dieselbe Logik wie Cockpit/Dashboards.
    """
    use_wb_pool: bool
    wb_pool_by_month: dict
    eauto_km_by_month: dict


def _build_emob_pool_ctx(inv_daten: dict, eauto_ids: set, wallbox_ids: set) -> _EmobPoolCtx:
    """Baut den Pool-Kontext aus bereits aktiv-gefilterten IMD
    (`{(inv_id, jahr, monat): verbrauch_daten}`). `use_wb_pool` strukturell:
    True, sobald eine Wallbox Heimladung trägt (Entscheidung 1)."""
    wb_pool_by_month = build_wb_pool_by_month(
        (jahr, monat, daten)
        for (inv_id, jahr, monat), daten in inv_daten.items()
        if inv_id in wallbox_ids
    )
    eauto_km_by_month = build_eauto_km_by_month(
        (jahr, monat, daten)
        for (inv_id, jahr, monat), daten in inv_daten.items()
        if inv_id in eauto_ids
    )
    use_wb_pool = any(
        (s.pv_kwh + s.netz_kwh) > 0 for s in wb_pool_by_month.values()
    )
    return _EmobPoolCtx(use_wb_pool, wb_pool_by_month, eauto_km_by_month)


async def _load_emob_pool_ctx(db: AsyncSession, investitionen) -> Optional[_EmobPoolCtx]:
    """Lädt + filtert die Emob-IMD einer Anlage und baut den Pool-Kontext —
    für Aufrufer, die nur die Investitionsliste, aber keine IMD geladen haben
    (z. B. die per-Investition-Sensor-Schleife)."""
    emob = [
        i for i in investitionen
        if i.typ in ("e-auto", "wallbox") and not ist_dienstlich(i)
    ]
    if not emob:
        return None
    by_id = {i.id: i for i in emob}
    res = await db.execute(
        select(InvestitionMonatsdaten).where(
            InvestitionMonatsdaten.investition_id.in_([i.id for i in emob])
        )
    )
    inv_daten: dict = {}
    for md in res.scalars().all():
        inv = by_id.get(md.investition_id)
        if inv and inv.ist_aktiv_im_monat(md.jahr, md.monat):
            inv_daten[(md.investition_id, md.jahr, md.monat)] = md.verbrauch_daten or {}
    return _build_emob_pool_ctx(
        inv_daten,
        {i.id for i in emob if i.typ == "e-auto"},
        {i.id for i in emob if i.typ == "wallbox"},
    )


def _emob_month_share(ctx: Optional[_EmobPoolCtx], typ: str, km: float, jahr: int, monat: int):
    """km-anteiliger Wallbox-Pool-Anteil eines E-Autos für (jahr, monat) — oder
    None, wenn keine Pool-Attribution greift (kein Kontext, keine Wallbox-
    Heimladung, oder typ != e-auto). Dann verwendet der Aufrufer die eigenen
    IMD-Werte. Die Wallbox-Sicht behält immer ihre eigenen Daten (= Quelle)."""
    if ctx is None or not ctx.use_wb_pool or typ != "e-auto":
        return None
    ms = attribute_month_share(
        ctx.wb_pool_by_month.get((jahr, monat)),
        km,
        ctx.eauto_km_by_month.get((jahr, monat), 0),
    )
    return ms if (ms.pv_kwh + ms.netz_kwh) > 0 else None


async def calculate_anlage_sensors(
    db: AsyncSession,
    anlage: Anlage
) -> list[SensorValue]:
    """
    Berechnet alle Sensor-Werte für eine Anlage.

    WICHTIG: PV-Erzeugung kommt aus InvestitionMonatsdaten (pro PV-Modul),
    NICHT aus Monatsdaten.pv_erzeugung_kwh (Legacy-Feld!).
    Einspeisung/Netzbezug kommen aus Monatsdaten (Zählerwerte).
    """
    # Monatsdaten laden (für Zählerwerte: einspeisung, netzbezug)
    result = await db.execute(
        select(Monatsdaten).where(Monatsdaten.anlage_id == anlage.id)
    )
    monatsdaten = result.scalars().all()

    if not monatsdaten:
        return []

    # Strompreis laden (aktuellster)
    result = await db.execute(
        select(Strompreis)
        .where(Strompreis.anlage_id == anlage.id)
        .order_by(Strompreis.gueltig_ab.desc())
        .limit(1)
    )
    strompreis = result.scalar_one_or_none()

    # Investitionen laden für ROI-Berechnung
    result = await db.execute(
        select(Investition)
        .where(Investition.anlage_id == anlage.id)
        .where(aktiv_jetzt())
    )
    investitionen = result.scalars().all()

    # PV-Module IDs für InvestitionMonatsdaten
    pv_module_ids = [inv.id for inv in investitionen if inv.typ == "pv-module"]
    inv_by_id = {inv.id: inv for inv in investitionen}

    # PV-Erzeugung aus InvestitionMonatsdaten aggregieren
    # Drift-Audit F: nur Monate ab Anschaffungsdatum berücksichtigen.
    # #326: zusätzlich pro (jahr, monat) für die per-Monat-korrekte EV-Ersparnis.
    pv_erzeugung = 0.0
    pv_by_ym: dict[tuple[int, int], float] = {}
    if pv_module_ids:
        imd_result = await db.execute(
            select(InvestitionMonatsdaten)
            .where(InvestitionMonatsdaten.investition_id.in_(pv_module_ids))
        )
        for imd in imd_result.scalars().all():
            inv = inv_by_id.get(imd.investition_id)
            if inv and not inv.ist_aktiv_im_monat(imd.jahr, imd.monat):
                continue
            data = imd.verbrauch_daten or {}
            pv_kwh = data.get("pv_erzeugung_kwh", 0) or 0
            pv_erzeugung += pv_kwh
            pv_by_ym[(imd.jahr, imd.monat)] = pv_by_ym.get((imd.jahr, imd.monat), 0.0) + pv_kwh

    # Fallback: Falls keine InvestitionMonatsdaten vorhanden, berechne aus Einspeisung
    einspeisung = sum(m.einspeisung_kwh or 0 for m in monatsdaten)
    if pv_erzeugung == 0:
        # Schätzung: Erzeugung ≈ Einspeisung + geschätzter Eigenverbrauch
        pv_erzeugung = einspeisung + sum(m.eigenverbrauch_kwh or 0 for m in monatsdaten)

    # #304: netzbezug ist ein Zählerwert aus Monatsdaten (legitim). Eigen-/
    # Direkt-/Gesamtverbrauch NICHT aus den berechneten Legacy-Monatsdaten-
    # Feldern lesen — die bleiben bei IMD-basierten Setups leer (moderne
    # Quellen schreiben in InvestitionMonatsdaten), wodurch die Eigenverbrauchs-
    # quote zusammenbricht (2,2 % statt ~40 %). Sie werden unten zentral aus
    # PV(IMD) + Speicher(IMD) + Zählerwerten über den SoT-Helper berechnet.
    netzbezug = sum(m.netzbezug_kwh or 0 for m in monatsdaten)

    # Speicher-Summen aus InvestitionMonatsdaten (korrekt) statt Legacy Monatsdaten
    speicher_ids = [inv.id for inv in investitionen if inv.typ == "speicher"]
    batterie_ladung = 0.0
    batterie_entladung = 0.0
    sp_lad_by_ym: dict[tuple[int, int], float] = {}
    sp_entl_by_ym: dict[tuple[int, int], float] = {}
    if speicher_ids:
        sp_result = await db.execute(
            select(InvestitionMonatsdaten)
            .where(InvestitionMonatsdaten.investition_id.in_(speicher_ids))
        )
        for imd in sp_result.scalars().all():
            inv = inv_by_id.get(imd.investition_id)
            if inv and not inv.ist_aktiv_im_monat(imd.jahr, imd.monat):
                continue
            data = imd.verbrauch_daten or {}
            lad = data.get("ladung_kwh", 0) or 0
            entl = data.get("entladung_kwh", 0) or 0
            batterie_ladung += lad
            batterie_entladung += entl
            sp_lad_by_ym[(imd.jahr, imd.monat)] = sp_lad_by_ym.get((imd.jahr, imd.monat), 0.0) + lad
            sp_entl_by_ym[(imd.jahr, imd.monat)] = sp_entl_by_ym.get((imd.jahr, imd.monat), 0.0) + entl

    # Fallback auf Legacy wenn keine InvestitionMonatsdaten
    if batterie_ladung == 0 and batterie_entladung == 0:
        batterie_ladung = sum(m.batterie_ladung_kwh or 0 for m in monatsdaten)
        batterie_entladung = sum(m.batterie_entladung_kwh or 0 for m in monatsdaten)

    # V2H (E-Auto → Haus) wird wie Speicher-Entladung als Eigenverbrauch gezählt
    eauto_ids = [inv.id for inv in investitionen if inv.typ == "e-auto"]
    v2h_entladung = 0.0
    v2h_by_ym: dict[tuple[int, int], float] = {}
    if eauto_ids:
        ea_result = await db.execute(
            select(InvestitionMonatsdaten)
            .where(InvestitionMonatsdaten.investition_id.in_(eauto_ids))
        )
        for imd in ea_result.scalars().all():
            inv = inv_by_id.get(imd.investition_id)
            if inv and not inv.ist_aktiv_im_monat(imd.jahr, imd.monat):
                continue
            v2h = (imd.verbrauch_daten or {}).get("v2h_entladung_kwh", 0) or 0
            v2h_entladung += v2h
            v2h_by_ym[(imd.jahr, imd.monat)] = v2h_by_ym.get((imd.jahr, imd.monat), 0.0) + v2h

    # #304: Eigenverbrauch/Direktverbrauch/Gesamtverbrauch + Quoten zentral über
    # den SoT-Helper aus IMD-gesourcten Energiemengen (PV + Speicher + V2H) und
    # den Zählerwerten (Einspeisung/Netzbezug) — kanonische Formel, deckungs-
    # gleich mit cockpit/uebersicht.py.
    kennzahlen = berechne_verbrauchs_kennzahlen(
        pv_erzeugung_kwh=pv_erzeugung,
        einspeisung_kwh=einspeisung,
        netzbezug_kwh=netzbezug,
        speicher_ladung_kwh=batterie_ladung,
        speicher_entladung_kwh=batterie_entladung,
        v2h_entladung_kwh=v2h_entladung,
    )
    direktverbrauch = kennzahlen.direktverbrauch_kwh
    eigenverbrauch = kennzahlen.eigenverbrauch_kwh
    gesamtverbrauch = kennzahlen.gesamtverbrauch_kwh
    autarkie = kennzahlen.autarkie_prozent
    ev_quote = kennzahlen.eigenverbrauchsquote_prozent
    # Spezifischer Ertrag — annualisiert über den SoT-Helper, deckungsgleich
    # mit der Cockpit-Kachel (Rainer-PN 2026-06-11: die alte Roh-Division
    # Lebenszeit-kWh ÷ heutiges kWp lieferte einen über die Laufzeit
    # aufkumulierten Wert, ~3× Jahreswert bei 3 Jahren Historie).
    spez_covered_months = set(pv_by_ym.keys())
    if not spez_covered_months:
        # Fallback ohne PV-IMDs (reine Zähler-Setups): Monate mit Legacy-PV>0 —
        # symmetrisch zum Cockpit-Fallback in cockpit/uebersicht.py.
        spez_covered_months = {
            (m.jahr, m.monat) for m in monatsdaten if (m.pv_erzeugung_kwh or 0) > 0
        }
    spez_gewichte = None
    if spez_covered_months:
        pvgis_res = await db.execute(
            select(PVGISPrognose)
            .where(
                PVGISPrognose.anlage_id == anlage.id,
                PVGISPrognose.ist_aktiv == True,  # noqa: E712 (SQLAlchemy-Vergleich)
            )
            .order_by(PVGISPrognose.abgerufen_am.desc())
            .limit(1)
        )
        pvgis = pvgis_res.scalar_one_or_none()
        spez_gewichte = monatsgewichte_aus_pvgis(
            pvgis.monatswerte if pvgis else None
        ) or None
    spez_ertrag = berechne_spez_ertrag_annualisiert(
        pv_erzeugung_kwh=pv_erzeugung,
        covered_months=spez_covered_months,
        investitionen=investitionen,
        fallback_kwp=anlage.leistung_kwp or 0.0,
        monatsgewichte=spez_gewichte,
    )

    # Finanzen (#326) — über den SoT-Helper `berechne_finanz_aggregat`, damit
    # HA-Export dieselbe Netto-Ertrag-Zahl liefert wie Cockpit/Jahresbericht.
    # Einspeise-Erlös §51-bereinigt + EV-Ersparnis pro Monat mit dem Monats-
    # Flexpreis (`resolve_netzbezug_preis_cent` → Fallback fixer Tarif). Anwender
    # ohne Strompreis-Sensor (m_neg=None) sehen die alte ungekürzte Berechnung;
    # bei vorhandenem Tages-Aggregat wird die in Negativpreis-Stunden
    # eingespeiste kWh-Menge unvergütet. Sonstige (manuell gepflegt) wie im
    # Cockpit im Netto-Ertrag.
    sonstige_netto_gesamt = 0.0
    alle_inv_ids = [i.id for i in investitionen]
    if alle_inv_ids:
        son_result = await db.execute(
            select(InvestitionMonatsdaten)
            .where(InvestitionMonatsdaten.investition_id.in_(alle_inv_ids))
        )
        for imd in son_result.scalars().all():
            inv = inv_by_id.get(imd.investition_id)
            if inv and not inv.ist_aktiv_im_monat(imd.jahr, imd.monat):
                continue
            sonstige_netto_gesamt += berechne_sonstige_netto(imd.verbrauch_daten)

    einspeise_erloes = 0
    ev_ersparnis = 0
    netto_ertrag = sonstige_netto_gesamt
    if strompreis:
        verg_cent = strompreis.einspeiseverguetung_cent_kwh
        netz_static_cent = strompreis.netzbezug_arbeitspreis_cent_kwh
        # PV-Quelle pro Monat wie das Aggregat: IMD bevorzugt, sonst Zähler-
        # Legacy-Feld (deckungsgleich mit cockpit/uebersicht.py `use_inv_pv`).
        use_inv_pv = bool(pv_by_ym)
        finanz_zeilen: list[FinanzMonatsZeile] = []
        for m in monatsdaten:
            key = (m.jahr, m.monat)
            m_neg = (
                await get_neg_preis_einspeisung_monat(db, anlage.id, m.jahr, m.monat)
                if m.einspeisung_kwh else None
            )
            m_pv = pv_by_ym.get(key, 0.0) if use_inv_pv else (m.pv_erzeugung_kwh or 0)
            finanz_zeilen.append(FinanzMonatsZeile(
                einspeisung_kwh=m.einspeisung_kwh or 0,
                netzbezug_kwh=m.netzbezug_kwh or 0,
                pv_erzeugung_kwh=m_pv,
                speicher_ladung_kwh=sp_lad_by_ym.get(key, 0.0),
                speicher_entladung_kwh=sp_entl_by_ym.get(key, 0.0),
                v2h_entladung_kwh=v2h_by_ym.get(key, 0.0),
                netzbezug_preis_cent=resolve_netzbezug_preis_cent(m, netz_static_cent),
                einspeiseverguetung_cent=verg_cent,
                neg_preis_kwh=m_neg,
            ))
        _finanz = berechne_finanz_aggregat(
            finanz_zeilen, sonstige_netto_euro=sonstige_netto_gesamt
        )
        einspeise_erloes = _finanz.einspeise_erloes_euro
        ev_ersparnis = _finanz.ev_ersparnis_euro
        netto_ertrag = _finanz.netto_ertrag_euro

    # CO2
    co2_ersparnis = pv_erzeugung * CO2_FAKTOR_STROM_KG_KWH

    # Investitions-KPIs berechnen
    investition_gesamt = sum(i.anschaffungskosten_gesamt or 0 for i in investitionen)
    alternativ_gesamt = sum(i.anschaffungskosten_alternativ or 0 for i in investitionen)
    relevante_kosten = investition_gesamt - alternativ_gesamt
    betriebskosten_ges = sum(i.betriebskosten_jahr or 0 for i in investitionen)

    # Alternativkosten-Ersparnisse aus historischen InvestitionMonatsdaten:
    # WP vs. Gas/Öl, E-Auto vs. Benzin, BKW-Eigenverbrauch.
    # Ohne diese Komponenten wäre die Jahresersparnis nur PV-Netto-Ertrag,
    # was bei Anlagen mit WP/E-Auto zu absurd langer Amortisation führt.
    waermepumpen = [i for i in investitionen if i.typ == "waermepumpe"]
    e_autos = [
        i for i in investitionen
        if i.typ == "e-auto" and not ist_dienstlich(i)
    ]
    wallboxen = [
        i for i in investitionen
        if i.typ == "wallbox" and not ist_dienstlich(i)
    ]
    balkonkraftwerke = [i for i in investitionen if i.typ == "balkonkraftwerk"]

    # IMD vor anschaffungsdatum / nach stilllegungsdatum überspringen (#236):
    # Sonst fließen Werte in HA-Sensor-Aggregate ein, obwohl die Komponente
    # in dem Monat noch gar nicht / nicht mehr aktiv war.
    historische_inv_daten: dict[tuple[int, int, int], dict] = {}
    inv_ids = [i.id for i in investitionen]
    inv_by_id_export = {i.id: i for i in investitionen}
    if inv_ids:
        imd_alle = await db.execute(
            select(InvestitionMonatsdaten)
            .where(InvestitionMonatsdaten.investition_id.in_(inv_ids))
        )
        for imd in imd_alle.scalars().all():
            inv = inv_by_id_export.get(imd.investition_id)
            if not inv or not inv.ist_aktiv_im_monat(imd.jahr, imd.monat):
                continue
            historische_inv_daten[(imd.investition_id, imd.jahr, imd.monat)] = (
                imd.verbrauch_daten or {}
            )

    # Phase 2a: Emob-Pool-Kontext aus den bereits aktiv-gefilterten IMD bauen.
    # Liegt die Heimladung kanonisch auf der Wallbox (evcc), zieht die
    # E-Auto-Ersparnis unten den km-anteiligen Wallbox-Netz-Anteil statt des
    # (leeren) E-Auto-Netz — sonst würde `bisherige_eauto_ersparnis` keinen
    # Netzstrom abziehen und die Ersparnis überhöhen.
    emob_ctx = _build_emob_pool_ctx(
        historische_inv_daten,
        {e.id for e in e_autos},
        {w.id for w in wallboxen},
    )

    netzbezug_preis_cent = (
        strompreis.netzbezug_arbeitspreis_cent_kwh if strompreis else 30.0
    )

    # Monatsdaten-Dict für Monats-Gaspreis / -Benzinpreis
    md_by_periode = {(md.jahr, md.monat): md for md in monatsdaten}

    # WP-Alternativkosten (vs. Gas/Öl) über den Berechnungs-Layer (ADR-001):
    # per-WP-Parameter (kein last-write-wins über waermepumpen), per-Monat-
    # Gaspreis aus Monatsdaten mit Fallback auf den WP-Parameter-Default.
    bisherige_wp_ersparnis = berechne_wp_alternativkosten_ersparnis(
        waermepumpen,
        historische_inv_daten,
        {k: md.gaspreis_cent_kwh for k, md in md_by_periode.items()},
        netzbezug_preis_cent,
    )

    # Per-E-Auto-Aufschlüsselung der bisherige-Ersparnis. Vorher las eine
    # `for ea`-Schleife `benzinpreis_default` + `vergleich_l_100km` in zwei
    # globale Variablen (last-write-wins). Bei zwei E-Autos mit
    # unterschiedlichen Parametern wurden BEIDE mit den Werten des LETZTEN
    # gerechnet → `jahres_ersparnis_euro`, `roi_prozent` und
    # `amortisation_jahre`-HA-Sensoren waren falsch. Zusätzlich fehlte der
    # `md.kraftstoffpreis_euro`-Monatspreis-Fallback (EU OB) — der Anlage-
    # Sensor driftete deshalb auch gegen den per-Investition-Sensor
    # `e_auto_ersparnis_vs_benzin_euro` (Zeile 583+, der hatte den Fallback).
    bisherige_eauto_ersparnis = 0.0
    for ea in e_autos:
        params = ea.parameter or {}
        ea_benzinpreis_default = params.get(
            PARAM_E_AUTO["BENZINPREIS_EURO"], PARAM_E_AUTO_DEFAULTS["benzinpreis_euro"],
        ) or PARAM_E_AUTO_DEFAULTS["benzinpreis_euro"]
        ea_vergleich_l_100km = params.get(
            PARAM_E_AUTO["VERGLEICH_VERBRAUCH_L_100KM"],
            PARAM_E_AUTO_DEFAULTS["vergleich_verbrauch_l_100km"],
        ) or PARAM_E_AUTO_DEFAULTS["vergleich_verbrauch_l_100km"]
        for (inv_id, jahr, monat), daten in historische_inv_daten.items():
            if inv_id != ea.id:
                continue
            km = daten.get("km_gefahren", 0) or 0
            # #262: SoT-Helper konsolidiert den Netz-Read mit Fallback.
            _, netz = get_emob_pv_netz_kwh(daten)
            # Phase 2a: evcc-Setup → Netz km-anteilig aus dem Wallbox-Pool.
            share = _emob_month_share(emob_ctx, "e-auto", km, jahr, monat)
            if share is not None:
                netz = share.netz_kwh
            md = md_by_periode.get((jahr, monat))
            monats_benzinpreis = (
                md.kraftstoffpreis_euro
                if md and md.kraftstoffpreis_euro is not None
                else ea_benzinpreis_default
            )
            benzin_liter = km / 100 * ea_vergleich_l_100km
            bisherige_eauto_ersparnis += (
                benzin_liter * monats_benzinpreis - netz * netzbezug_preis_cent / 100
            )

    # BKW-Alternativkosten: Eigenverbrauch zum Netzbezugspreis (Berechnungs-Layer).
    bisherige_bkw_ersparnis = berechne_bkw_alternativkosten_ersparnis(
        balkonkraftwerke, historische_inv_daten, netzbezug_preis_cent,
    )

    historischer_netto_ertrag = (
        netto_ertrag
        + bisherige_wp_ersparnis
        + bisherige_eauto_ersparnis
        + bisherige_bkw_ersparnis
    )

    # Jahresersparnis aus Monatsdaten berechnen (annualisiert)
    anzahl_monate = len(monatsdaten)
    if anzahl_monate > 0:
        jahres_ersparnis = (historischer_netto_ertrag / anzahl_monate) * 12 - betriebskosten_ges
    else:
        jahres_ersparnis = 0

    # ROI und Amortisation
    roi_prozent = None
    amortisation_jahre = None
    if relevante_kosten > 0 and jahres_ersparnis > 0:
        roi_prozent = (jahres_ersparnis / relevante_kosten) * 100
        amortisation_jahre = relevante_kosten / jahres_ersparnis

    # Speicher-KPIs berechnen
    speicher_effizienz = None
    speicher_zyklen = None

    # Speicher-Kapazität aus Investitionen ermitteln
    speicher_kapazitaet = 0
    for inv in investitionen:
        if inv.typ == 'speicher' and inv.parameter:
            # Defensive Doppel-Read: kapazitaet_kwh ist Brutto, nutzbare_kapazitaet_kwh
            # ist optionaler User-Override (DOD-Reserve). Wenn beides leer → kein Speicher gepflegt.
            kap = inv.parameter.get(PARAM_SPEICHER["KAPAZITAET_KWH"]) or inv.parameter.get(PARAM_SPEICHER["NUTZBARE_KAPAZITAET_KWH"])
            if kap:
                speicher_kapazitaet += float(kap)

    if batterie_ladung > 0:
        speicher_effizienz = (batterie_entladung / batterie_ladung) * 100
    if speicher_kapazitaet > 0 and batterie_entladung > 0:
        speicher_zyklen = batterie_entladung / speicher_kapazitaet

    # Sensor-Werte erstellen
    sensor_values = []

    # Energie-Sensoren
    for sensor in ANLAGE_SENSOREN:
        value = None
        berechnung = None

        if sensor.key == "pv_erzeugung_gesamt_kwh":
            value = round(pv_erzeugung, 1)
            berechnung = f"Summe aus {len(monatsdaten)} Monaten"
        elif sensor.key == "direktverbrauch_gesamt_kwh":
            value = round(direktverbrauch, 1)
            berechnung = f"PV direkt verbraucht (ohne Speicher)"
        elif sensor.key == "eigenverbrauch_gesamt_kwh":
            value = round(eigenverbrauch, 1)
        elif sensor.key == "einspeisung_gesamt_kwh":
            value = round(einspeisung, 1)
        elif sensor.key == "netzbezug_gesamt_kwh":
            value = round(netzbezug, 1)
        elif sensor.key == "gesamtverbrauch_kwh":
            value = round(gesamtverbrauch, 1)
            berechnung = f"{eigenverbrauch:.0f} + {netzbezug:.0f}"
        elif sensor.key == "autarkie_prozent":
            value = round(autarkie, 1)
            berechnung = f"{eigenverbrauch:.0f} ÷ {gesamtverbrauch:.0f} × 100"
        elif sensor.key == "eigenverbrauch_quote_prozent":
            value = round(ev_quote, 1)
            berechnung = f"{eigenverbrauch:.0f} ÷ {pv_erzeugung:.0f} × 100"
        elif sensor.key == "spezifischer_ertrag_kwh_kwp":
            value = round(spez_ertrag, 0) if spez_ertrag else None
            if value is not None:
                berechnung = (
                    f"{pv_erzeugung:.0f} kWh annualisiert "
                    f"(saisonal gewichtet, wie Cockpit)"
                )
        elif sensor.key == "netto_ertrag_euro":
            value = round(netto_ertrag, 2)
            berechnung = f"{einspeise_erloes:.2f} + {ev_ersparnis:.2f} + {sonstige_netto_gesamt:.2f} (sonstige)"
        elif sensor.key == "einspeise_erloes_euro":
            value = round(einspeise_erloes, 2)
            if strompreis:
                berechnung = f"{einspeisung:.0f} × {strompreis.einspeiseverguetung_cent_kwh:.2f} ct/kWh"
        elif sensor.key == "eigenverbrauch_ersparnis_euro":
            value = round(ev_ersparnis, 2)
            if strompreis:
                berechnung = f"{eigenverbrauch:.0f} × {strompreis.netzbezug_arbeitspreis_cent_kwh:.2f} ct/kWh"
        elif sensor.key == "co2_ersparnis_kg":
            value = round(co2_ersparnis, 1)
            berechnung = f"{pv_erzeugung:.0f} × 0.38"

        if value is not None:
            sensor_values.append(SensorValue(
                definition=sensor,
                value=value,
                berechnung=berechnung
            ))

    # Investitions-Sensoren
    for sensor in INVESTITION_SENSOREN:
        value = None
        berechnung = None

        if sensor.key == "investition_gesamt_euro":
            if investition_gesamt > 0:
                value = round(investition_gesamt, 2)
                berechnung = f"Summe aus {len(investitionen)} Investitionen"
        elif sensor.key == "jahres_ersparnis_euro":
            if jahres_ersparnis > 0:
                value = round(jahres_ersparnis, 2)
                berechnung = f"({historischer_netto_ertrag:.2f} ÷ {anzahl_monate}) × 12"
        elif sensor.key == "roi_prozent":
            if roi_prozent is not None:
                value = round(roi_prozent, 1)
                berechnung = f"{jahres_ersparnis:.2f} ÷ {relevante_kosten:.2f} × 100"
        elif sensor.key == "amortisation_jahre":
            if amortisation_jahre is not None:
                value = round(amortisation_jahre, 1)
                berechnung = f"{relevante_kosten:.2f} ÷ {jahres_ersparnis:.2f}"

        if value is not None:
            sensor_values.append(SensorValue(
                definition=sensor,
                value=value,
                berechnung=berechnung
            ))

    # Speicher-Sensoren (nur wenn Speicher vorhanden)
    if speicher_kapazitaet > 0 or batterie_ladung > 0:
        for sensor in SPEICHER_SENSOREN:
            value = None
            berechnung = None

            if sensor.key == "speicher_zyklen":
                if speicher_zyklen is not None:
                    value = round(speicher_zyklen, 0)
                    berechnung = f"{batterie_entladung:.0f} ÷ {speicher_kapazitaet:.1f}"
            elif sensor.key == "speicher_effizienz_prozent":
                if speicher_effizienz is not None:
                    value = round(speicher_effizienz, 1)
                    berechnung = f"{batterie_entladung:.0f} ÷ {batterie_ladung:.0f} × 100"

            if value is not None:
                sensor_values.append(SensorValue(
                    definition=sensor,
                    value=value,
                    berechnung=berechnung
                ))

    # Letzter Import Sensoren (Status)
    if monatsdaten:
        # Finde den neuesten Monat (sortiert nach Jahr, dann Monat)
        sorted_md = sorted(monatsdaten, key=lambda m: (m.jahr, m.monat), reverse=True)
        letzter = sorted_md[0]

        # Monatsnamen
        monatsnamen = [
            "", "Januar", "Februar", "März", "April", "Mai", "Juni",
            "Juli", "August", "September", "Oktober", "November", "Dezember"
        ]
        monatsname = monatsnamen[letzter.monat] if 1 <= letzter.monat <= 12 else str(letzter.monat)

        for sensor in LETZTER_IMPORT_SENSOREN:
            value = None
            berechnung = None

            if sensor.key == "letzter_import_jahr":
                value = letzter.jahr
                berechnung = f"Neuester Datensatz: {monatsname} {letzter.jahr}"
            elif sensor.key == "letzter_import_monat":
                value = letzter.monat
                berechnung = f"Monat {letzter.monat} ({monatsname})"
            elif sensor.key == "letzter_import_monat_name":
                value = f"{monatsname} {letzter.jahr}"
                berechnung = f"Formatiert aus {letzter.monat}/{letzter.jahr}"
            elif sensor.key == "anzahl_monate_erfasst":
                value = len(monatsdaten)
                berechnung = f"Erfasste Monatsdaten in der Datenbank"

            if value is not None:
                sensor_values.append(SensorValue(
                    definition=sensor,
                    value=value,
                    berechnung=berechnung
                ))

    # #150 A: eedc-eigene PV-Prognose (OpenMeteo × Lernfaktor) — anlage-weit,
    # koordinaten-/PV-gated, netzwerk-tolerant (None → Sensoren entfallen).
    # Stundenprofil reist als Attribut mit (kein eigenes Topic).
    prognose = await berechne_prognose_export(db, anlage)
    if prognose:
        for sensor in PROGNOSE_SENSOREN:
            value = None
            zusatz: dict = {}
            if sensor.key == "eedc_prognose_heute_kwh":
                value = prognose["heute_kwh"]
                if prognose.get("stundenprofil_heute"):
                    zusatz = {"stundenprofil_kwh": prognose["stundenprofil_heute"]}
            elif sensor.key == "eedc_prognose_rest_today_kwh":
                value = prognose["rest_today_kwh"]
            elif sensor.key == "eedc_prognose_day_plus_1_kwh":
                value = prognose["day_plus_1_kwh"]
                if prognose.get("stundenprofil_day_plus_1"):
                    zusatz = {"stundenprofil_kwh": prognose["stundenprofil_day_plus_1"]}
            elif sensor.key == "eedc_prognose_day_plus_2_kwh":
                value = prognose["day_plus_2_kwh"]
                if prognose.get("stundenprofil_day_plus_2"):
                    zusatz = {"stundenprofil_kwh": prognose["stundenprofil_day_plus_2"]}
            elif sensor.key == "eedc_prognose_day_plus_3_kwh":
                value = prognose["day_plus_3_kwh"]
                if prognose.get("stundenprofil_day_plus_3"):
                    zusatz = {"stundenprofil_kwh": prognose["stundenprofil_day_plus_3"]}
            elif sensor.key == "eedc_speicher_voll_um":
                value = prognose["speicher_voll_um"]

            if value is not None:
                sensor_values.append(SensorValue(
                    definition=sensor, value=value, zusatz_attribute=zusatz
                ))

    # #150 B: Börsenpreis-Trigger (Rang je Tag-/Nacht-Fenster) — Rang-Profil als Attribut.
    preis = await berechne_preis_export(db, anlage)
    if preis:
        for sensor in PREIS_SENSOREN:
            value = None
            zusatz = {}
            if sensor.key == "eedc_preis_rang":
                value = preis["preis_rang"]
                if preis.get("rang_profil"):
                    zusatz = {"rang_profil": preis["rang_profil"]}
                if preis.get("guenstig_schwelle_cent") is not None:
                    zusatz["guenstig_schwelle_cent"] = preis["guenstig_schwelle_cent"]
            elif sensor.key == "eedc_preis_guenstige_stunden_anzahl":
                value = preis["guenstige_stunden_anzahl"]
            elif sensor.key == "eedc_preis_guenstige_stunden_tag":
                value = preis["guenstige_stunden_tag"]
            elif sensor.key == "eedc_preis_guenstige_stunden_nacht":
                value = preis["guenstige_stunden_nacht"]

            if value is not None:
                sensor_values.append(SensorValue(
                    definition=sensor, value=value, zusatz_attribute=zusatz
                ))

    return sensor_values


async def calculate_investition_sensors(
    db: AsyncSession,
    investition: Investition,
    strompreis: Optional[Strompreis],
    emob_ctx: Optional[_EmobPoolCtx] = None,
) -> list[SensorValue]:
    """Berechnet Sensor-Werte für eine Investition basierend auf Typ.

    `emob_ctx` (Phase 2a): liegt die Heimladung kanonisch auf der Wallbox
    (evcc), ziehen die E-Auto-Sensoren PV-Anteil + Ersparnis km-anteilig aus dem
    Wallbox-Pool statt aus der leeren E-Auto-IMD. Ohne Kontext (Default) bleibt
    das Verhalten unverändert (eigene IMD-Werte)."""
    sensor_values = []

    # InvestitionMonatsdaten laden
    imd_result = await db.execute(
        select(InvestitionMonatsdaten)
        .where(InvestitionMonatsdaten.investition_id == investition.id)
    )
    # #308: SoT-Filter auf die Laufzeit (Anschaffung→Stilllegung), symmetrisch
    # zur Schwesterfunktion `calculate_anlage_sensors` (#236). Ohne ihn flossen
    # IMD-Monate vor Anschaffung / nach Stilllegung in die per-Investition-
    # HA-Sensoren (km, Verbrauch, PV-Anteil, Ersparnis) ein.
    monatsdaten = [
        md for md in imd_result.scalars().all()
        if investition.ist_aktiv_im_monat(md.jahr, md.monat)
    ]

    params = investition.parameter or {}
    netzbezug_preis = strompreis.netzbezug_arbeitspreis_cent_kwh if strompreis else 30.0

    # ROI-Basisdaten
    if investition.anschaffungskosten_gesamt:
        for sensor in INVESTITION_SENSOREN:
            if sensor.key == "investition_gesamt_euro":
                sensor_values.append(SensorValue(
                    definition=sensor,
                    value=round(investition.anschaffungskosten_gesamt, 2),
                    berechnung=None
                ))

    # E-Auto / Wallbox Sensoren
    if investition.typ in ("e-auto", "wallbox"):
        gesamt_km = 0.0
        gesamt_verbrauch = 0.0
        gesamt_pv_ladung = 0.0
        gesamt_netz_ladung = 0.0

        for md in monatsdaten:
            d = md.verbrauch_daten or {}
            km_m = d.get("km_gefahren", 0) or 0
            gesamt_km += km_m
            gesamt_verbrauch += d.get("verbrauch_kwh", 0) or 0
            # Phase 2a: evcc-Setup → PV/Netz km-anteilig aus dem Wallbox-Pool.
            share = _emob_month_share(emob_ctx, investition.typ, km_m, md.jahr, md.monat)
            if share is not None:
                gesamt_pv_ladung += share.pv_kwh
                gesamt_netz_ladung += share.netz_kwh
            else:
                # #262: PV/Netz via SoT-Helper — bei Imports ohne expliziten
                # `ladung_netz_kwh`-Key wird aus `Total − PV` abgeleitet.
                pv, netz = get_emob_pv_netz_kwh(d)
                gesamt_pv_ladung += pv
                gesamt_netz_ladung += netz

        gesamt_ladung = gesamt_pv_ladung + gesamt_netz_ladung

        for sensor in E_AUTO_SENSOREN:
            value = None
            berechnung = None

            if sensor.key == "e_auto_km_gesamt":
                if gesamt_km > 0:
                    value = round(gesamt_km, 0)
                    berechnung = f"Summe aus {len(monatsdaten)} Monaten"
            elif sensor.key == "e_auto_verbrauch_kwh_100km":
                if gesamt_km > 0 and gesamt_verbrauch > 0:
                    value = round(gesamt_verbrauch / gesamt_km * 100, 1)
                    berechnung = f"{gesamt_verbrauch:.0f} / {gesamt_km:.0f} × 100"
            elif sensor.key == "e_auto_pv_anteil_prozent":
                if gesamt_ladung > 0:
                    value = round(gesamt_pv_ladung / gesamt_ladung * 100, 1)
                    berechnung = f"{gesamt_pv_ladung:.0f} / {gesamt_ladung:.0f} × 100"
            elif sensor.key == "e_auto_ersparnis_vs_benzin_euro":
                if gesamt_km > 0:
                    # Monatliche Kraftstoffpreise laden (Fallback: statischer Parameter)
                    fallback_benzinpreis = params.get(PARAM_E_AUTO["BENZINPREIS_EURO"], PARAM_E_AUTO_DEFAULTS["benzinpreis_euro"])
                    vergleich_l = params.get(
                        PARAM_E_AUTO["VERGLEICH_VERBRAUCH_L_100KM"],
                        PARAM_E_AUTO_DEFAULTS["vergleich_verbrauch_l_100km"],
                    )
                    anlage_md_result = await db.execute(
                        select(Monatsdaten).where(Monatsdaten.anlage_id == investition.anlage_id)
                    )
                    anlage_md_dict = {
                        (m.jahr, m.monat): m for m in anlage_md_result.scalars().all()
                    }
                    benzin_kosten = 0.0
                    strom_kosten = 0.0
                    for md in monatsdaten:
                        d = md.verbrauch_daten or {}
                        km = d.get("km_gefahren", 0) or 0
                        # #262: SoT-Helper liefert (pv, netz) mit Fallback.
                        _, netz = get_emob_pv_netz_kwh(d)
                        # Phase 2a: evcc → Netz km-anteilig aus dem Wallbox-Pool.
                        share = _emob_month_share(emob_ctx, investition.typ, km, md.jahr, md.monat)
                        if share is not None:
                            netz = share.netz_kwh
                        amd = anlage_md_dict.get((md.jahr, md.monat))
                        bp = (amd.kraftstoffpreis_euro
                              if amd and amd.kraftstoffpreis_euro is not None
                              else fallback_benzinpreis)
                        benzin_kosten += (km / 100) * vergleich_l * bp
                        strom_kosten += netz * netzbezug_preis / 100
                    value = round(benzin_kosten - strom_kosten, 2)
                    berechnung = f"{benzin_kosten:.2f} (Benzin) - {strom_kosten:.2f} (Strom)"

            if value is not None:
                sensor_values.append(SensorValue(
                    definition=sensor,
                    value=value,
                    berechnung=berechnung
                ))

    # Wärmepumpe Sensoren
    elif investition.typ == "waermepumpe":
        gesamt_strom = 0.0
        gesamt_heizung = 0.0
        gesamt_warmwasser = 0.0

        for md in monatsdaten:
            d = md.verbrauch_daten or {}
            gesamt_strom += get_wp_strom_kwh(d, investition.parameter)
            gesamt_heizung += d.get("heizenergie_kwh", 0) or 0
            gesamt_warmwasser += d.get("warmwasser_kwh", 0) or 0

        gesamt_waerme = gesamt_heizung + gesamt_warmwasser

        # Issue #238: Counter-Summen (Starts/Betriebsstunden) dieser WP aus
        # TagesZusammenfassung.komponenten_starts über die Laufzeit. Nur gesetzt,
        # wenn der jeweilige Zähler überhaupt Werte geliefert hat.
        from backend.models.tages_energie_profil import TagesZusammenfassung
        inv_id_str = str(investition.id)
        tz_res = await db.execute(
            select(TagesZusammenfassung.datum, TagesZusammenfassung.komponenten_starts)
            .where(TagesZusammenfassung.anlage_id == investition.anlage_id)
            .where(TagesZusammenfassung.komponenten_starts.is_not(None))
        )
        wp_starts_total = 0
        wp_stunden_total = 0.0
        hat_starts = hat_stunden = False
        for datum_, komp in tz_res.all():
            if not investition.ist_aktiv_im_monat(datum_.year, datum_.month):
                continue
            c = ((komp or {}).get("wp_starts_anzahl") or {}).get(inv_id_str)
            if isinstance(c, (int, float)) and c > 0:
                wp_starts_total += int(c)
                hat_starts = True
            h = ((komp or {}).get("wp_betriebsstunden") or {}).get(inv_id_str)
            if isinstance(h, (int, float)) and h > 0:
                wp_stunden_total += float(h)
                hat_stunden = True

        for sensor in WAERMEPUMPE_SENSOREN:
            value = None
            berechnung = None

            if sensor.key == "wp_cop_durchschnitt":
                if gesamt_strom > 0 and gesamt_waerme > 0:
                    value = round(gesamt_waerme / gesamt_strom, 2)
                    berechnung = f"{gesamt_waerme:.0f} / {gesamt_strom:.0f}"
            elif sensor.key == "wp_ersparnis_euro":
                if gesamt_waerme > 0:
                    fallback_alter_preis = params.get(PARAM_WAERMEPUMPE["ALTER_PREIS_CENT_KWH"], PARAM_WAERMEPUMPE_DEFAULTS["alter_preis_cent_kwh"])
                    alter_wirkungsgrad = WP_WIRKUNGSGRAD_OEL_DEFAULT if params.get(PARAM_WAERMEPUMPE["ALTER_ENERGIETRAEGER"]) == "oel" else WP_WIRKUNGSGRAD_GAS_DEFAULT
                    zusatzkosten_jahr = params.get(PARAM_WAERMEPUMPE["ALTERNATIV_ZUSATZKOSTEN_JAHR"], 0) or 0
                    # Monatliche Gaspreise laden (Fallback: statischer Parameter)
                    anlage_md_result = await db.execute(
                        select(Monatsdaten).where(Monatsdaten.anlage_id == investition.anlage_id)
                    )
                    anlage_md_dict = {
                        (m.jahr, m.monat): m for m in anlage_md_result.scalars().all()
                    }
                    alte_kosten = 0.0
                    for md in monatsdaten:
                        d = md.verbrauch_daten or {}
                        waerme = (d.get("heizenergie_kwh", 0) or 0) + (d.get("warmwasser_kwh", 0) or 0)
                        amd = anlage_md_dict.get((md.jahr, md.monat))
                        gp = (amd.gaspreis_cent_kwh
                              if amd and amd.gaspreis_cent_kwh is not None
                              else fallback_alter_preis)
                        alte_kosten += gas_kosten_altanlage(waerme, alter_wirkungsgrad, gp)
                    # Fixe Zusatzkosten anteilig
                    alte_kosten += zusatzkosten_jahr * len(monatsdaten) / 12
                    wp_kosten = gesamt_strom * netzbezug_preis / 100
                    value = round(alte_kosten - wp_kosten, 2)
                    berechnung = f"{alte_kosten:.2f} (alt) - {wp_kosten:.2f} (WP)"
            elif sensor.key == "wp_kompressor_starts":
                if hat_starts:
                    value = wp_starts_total
                    berechnung = "Σ erfasste Kompressor-Starts"
            elif sensor.key == "wp_betriebsstunden":
                if hat_stunden:
                    value = round(wp_stunden_total, 1)
                    berechnung = "Σ erfasste Betriebsstunden"

            if value is not None:
                sensor_values.append(SensorValue(
                    definition=sensor,
                    value=value,
                    berechnung=berechnung
                ))

    return sensor_values


# =============================================================================
# API Endpoints
# =============================================================================

@router.get("/mqtt/config", response_model=MQTTConfigResponse)
async def get_mqtt_config():
    """
    Gibt die MQTT-Konfiguration aus den Add-on Optionen zurück.

    Diese Werte werden in der HA Add-on Konfiguration gesetzt und
    können im Frontend für die MQTT-Einstellungen vorausgefüllt werden.
    """
    from backend.core.config import settings

    # Passwort als Maske zurückgeben wenn gesetzt
    password_masked = "••••••" if settings.mqtt_password else ""

    return MQTTConfigResponse(
        enabled=settings.mqtt_enabled,
        host=settings.mqtt_host,
        port=settings.mqtt_port,
        username=settings.mqtt_username,
        password=password_masked,
        auto_publish=settings.mqtt_auto_publish,
        publish_interval_minutes=settings.mqtt_publish_interval,
    )


@router.get("/sensors", response_model=FullExportResponse)
async def get_all_sensors(db: AsyncSession = Depends(get_db)):
    """
    Gibt alle EEDC-Sensoren mit aktuellen Werten zurück.

    Dieser Endpoint kann von HA über die `rest` Platform abgefragt werden
    oder dient als Übersicht für die MQTT-Konfiguration.
    """
    # Anlagen laden
    result = await db.execute(select(Anlage))
    anlagen = result.scalars().all()

    anlagen_exports = []
    investitionen_exports = []
    total_sensors = 0

    for anlage in anlagen:
        # Anlage-Sensoren berechnen
        sensor_values = await calculate_anlage_sensors(db, anlage)

        sensors = [
            SensorExportItem(
                key=sv.definition.key,
                name=sv.definition.name,
                value=sv.value,
                unit=sv.definition.unit,
                icon=sv.definition.icon,
                category=sv.definition.category.value,
                formel=sv.definition.formel,
                berechnung=sv.berechnung,
                device_class=sv.definition.device_class,
                state_class=sv.definition.state_class,
            )
            for sv in sensor_values
        ]

        if sensors:
            anlagen_exports.append(AnlageExport(
                anlage_id=anlage.id,
                anlage_name=anlage.anlagenname,
                sensors=sensors
            ))
            total_sensors += len(sensors)

        # Investitionen dieser Anlage laden
        result = await db.execute(
            select(Investition).where(Investition.anlage_id == anlage.id)
        )
        investitionen = result.scalars().all()

        # Strompreis für Investitions-Berechnungen
        result = await db.execute(
            select(Strompreis)
            .where(Strompreis.anlage_id == anlage.id)
            .order_by(Strompreis.gueltig_ab.desc())
            .limit(1)
        )
        strompreis = result.scalar_one_or_none()

        # Phase 2a: Emob-Pool-Kontext der Anlage einmalig bauen, damit die
        # per-Device-E-Auto-Sensoren bei evcc-Setups den km-anteiligen
        # Wallbox-Pool sehen (statt leerer E-Auto-IMD).
        emob_ctx = await _load_emob_pool_ctx(db, investitionen)

        for inv in investitionen:
            inv_sensors = await calculate_investition_sensors(db, inv, strompreis, emob_ctx)
            inv_sensor_items = [
                SensorExportItem(
                    key=sv.definition.key,
                    name=sv.definition.name,
                    value=sv.value,
                    unit=sv.definition.unit,
                    icon=sv.definition.icon,
                    category=sv.definition.category.value,
                    formel=sv.definition.formel,
                    berechnung=sv.berechnung,
                    device_class=sv.definition.device_class,
                    state_class=sv.definition.state_class,
                )
                for sv in inv_sensors
            ]

            if inv_sensor_items:
                investitionen_exports.append(InvestitionExport(
                    investition_id=inv.id,
                    bezeichnung=inv.bezeichnung,
                    typ=inv.typ,
                    sensors=inv_sensor_items
                ))
                total_sensors += len(inv_sensor_items)

    # MQTT-Verfügbarkeit prüfen
    mqtt_client = MQTTClient()

    return FullExportResponse(
        anlagen=anlagen_exports,
        investitionen=investitionen_exports,
        sensor_count=total_sensors,
        mqtt_available=mqtt_client.is_available
    )


@router.get("/sensors/{anlage_id}", response_model=AnlageExport)
async def get_anlage_sensors(
    anlage_id: int,
    db: AsyncSession = Depends(get_db)
):
    """Gibt Sensoren für eine spezifische Anlage zurück."""
    result = await db.execute(
        select(Anlage).where(Anlage.id == anlage_id)
    )
    anlage = result.scalar_one_or_none()

    if not anlage:
        raise not_found("Anlage")

    sensor_values = await calculate_anlage_sensors(db, anlage)

    sensors = [
        SensorExportItem(
            key=sv.definition.key,
            name=sv.definition.name,
            value=sv.value,
            unit=sv.definition.unit,
            icon=sv.definition.icon,
            category=sv.definition.category.value,
            formel=sv.definition.formel,
            berechnung=sv.berechnung,
            device_class=sv.definition.device_class,
            state_class=sv.definition.state_class,
        )
        for sv in sensor_values
    ]

    return AnlageExport(
        anlage_id=anlage.id,
        anlage_name=anlage.anlagenname,
        sensors=sensors
    )


@router.get("/yaml/{anlage_id}", response_model=HAYamlSnippet)
async def get_ha_yaml_snippet(
    anlage_id: int,
    request: Request,
    host: Optional[str] = None,
    db: AsyncSession = Depends(get_db)
):
    """
    Generiert ein YAML-Snippet für die HA configuration.yaml.

    Dieses Snippet kann in die HA-Konfiguration kopiert werden,
    um die EEDC-Sensoren über die REST-Platform einzubinden.
    """
    result = await db.execute(
        select(Anlage).where(Anlage.id == anlage_id)
    )
    anlage = result.scalar_one_or_none()

    if not anlage:
        raise not_found("Anlage")

    sensor_values = await calculate_anlage_sensors(db, anlage)

    # Erreichbaren Host bestimmen: expliziter ?host=-Override → Request-Host
    # (direkter Aufruf, z. B. 192.168.1.10:8099) → Platzhalter. Hinter
    # HA-Ingress zeigt der Request-Host auf den HA-Proxy — der ist für die
    # rest-Integration nicht nutzbar, dort bleibt nur der Platzhalter.
    # HA wertet in `rest: resource:` KEINE Templates aus; das frühere
    # `{{ eedc_addon_host }}` erzeugte 1:1 eingefügt eine ungültige URL und
    # damit gar keine Entitäten (rapahl 2026-06-10).
    ist_ingress = "x-ingress-path" in request.headers
    request_host = request.headers.get("host", "")
    if host:
        eedc_host = host if ":" in host else f"{host}:8099"
    elif request_host and not ist_ingress:
        eedc_host = request_host
    else:
        eedc_host = "<EEDC-IP>:8099"
    host_ist_platzhalter = eedc_host.startswith("<")

    # YAML generieren
    yaml_lines = [
        "# eedc Sensoren für Home Assistant (REST-Integration)",
        "# Füge dies in deine configuration.yaml ein und starte Home Assistant neu.",
    ]
    if host_ist_platzhalter:
        yaml_lines += [
            "# WICHTIG: <EEDC-IP> unten durch die Adresse ersetzen, unter der dein",
            "#          eedc direkt erreichbar ist (z. B. 192.168.1.10:8099).",
        ]
    yaml_lines += [
        "# Add-on-Hinweis: Port 8099 muss in den Add-on-Netzwerkeinstellungen",
        "# freigegeben sein, sonst kann Home Assistant diesen Endpunkt nicht erreichen.",
        "",
        "rest:",
        f'  - resource: "http://{eedc_host}/api/ha/export/sensors/{anlage_id}"',
        "    scan_interval: 3600  # Alle Stunde aktualisieren",
        "    sensor:",
    ]

    for sv in sensor_values:
        sensor = sv.definition
        safe_name = sensor.key.replace("_", " ").title()
        yaml_lines.append(f'      - name: "eedc {safe_name}"')
        yaml_lines.append(f'        unique_id: "eedc_{anlage_id}_{sensor.key}"')
        yaml_lines.append(f'        value_template: "{{{{ value_json.sensors | selectattr(\'key\', \'eq\', \'{sensor.key}\') | map(attribute=\'value\') | first }}}}"')
        if sensor.unit:
            yaml_lines.append(f'        unit_of_measurement: "{sensor.unit}"')
        if sensor.device_class:
            yaml_lines.append(f'        device_class: "{sensor.device_class}"')
        if sensor.state_class:
            yaml_lines.append(f'        state_class: "{sensor.state_class}"')
        yaml_lines.append("")

    yaml = "\n".join(yaml_lines)

    if host_ist_platzhalter:
        hinweis = (
            "eedc läuft hinter Ingress: Bitte <EEDC-IP> durch die direkte Adresse "
            "ersetzen und im HA-Add-on Port 8099 in den Netzwerk-Einstellungen freigeben."
        )
    else:
        hinweis = (
            f"Host {eedc_host} wurde aus deiner Aufruf-Adresse übernommen. "
            "Im HA-Add-on muss Port 8099 in den Netzwerk-Einstellungen freigegeben sein."
        )

    return HAYamlSnippet(
        yaml=yaml,
        sensor_count=len(sensor_values),
        hinweis=hinweis
    )


@router.get("/definitions")
async def get_sensor_definitions():
    """Gibt alle verfügbaren Sensor-Definitionen zurück."""
    definitions = get_all_sensor_definitions()

    return {
        "count": len(definitions),
        "sensors": [
            {
                "key": s.key,
                "name": s.name,
                "unit": s.unit,
                "icon": s.icon,
                "category": s.category.value,
                "formel": s.formel,
                "device_class": s.device_class,
                "state_class": s.state_class,
                "enabled_by_default": s.enabled_by_default,
            }
            for s in definitions
        ]
    }


# =============================================================================
# MQTT Endpoints
# =============================================================================

@router.post("/mqtt/test")
async def test_mqtt_connection(config: Optional[MQTTConfigRequest] = None):
    """Testet die MQTT-Verbindung zum Broker."""
    mqtt_config = resolve_mqtt_config(
        config.host if config else None,
        config.port if config else None,
        config.username if config else None,
        config.password if config else None,
    )

    client = MQTTClient(mqtt_config)
    result = await client.test_connection()

    return result


@router.post("/mqtt/publish/{anlage_id}")
async def publish_sensors_mqtt(
    anlage_id: int,
    config: Optional[MQTTConfigRequest] = None,
    db: AsyncSession = Depends(get_db)
):
    """
    Publiziert alle Sensoren einer Anlage via MQTT Discovery.

    Die Sensoren erscheinen automatisch in Home Assistant unter
    dem Device "eedc - {Anlagenname}".
    """
    # Anlage laden
    result = await db.execute(
        select(Anlage).where(Anlage.id == anlage_id)
    )
    anlage = result.scalar_one_or_none()

    if not anlage:
        raise not_found("Anlage")

    # Broker-Config: Override-Felder aus dem Request, sonst ENV (#655).
    mqtt_config = resolve_mqtt_config(
        config.host if config else None,
        config.port if config else None,
        config.username if config else None,
        config.password if config else None,
    )

    # Zentraler Outbound-Pfad — identisch zum Auto-Publish (#655).
    pub = await publish_anlage_sensors(db, anlage, mqtt_config)

    if not pub["available"]:
        raise HTTPException(
            status_code=503,
            detail="MQTT nicht verfügbar. Bitte aiomqtt installieren: pip install aiomqtt"
        )
    if pub["no_data"]:
        raise HTTPException(
            status_code=404,
            detail="Keine Monatsdaten vorhanden"
        )

    fehl = f", {pub['failed']} fehlgeschlagen" if pub["failed"] else ""
    # Fehlergründe in die Activity aufnehmen (#655: „X fehlgeschlagen" ohne Grund hilft nicht).
    grund = f" — z. B. {'; '.join(pub['errors'])}" if pub.get("errors") else ""
    await log_activity(
        kategorie="ha_export",
        aktion="MQTT-Sensoren publiziert",
        erfolg=pub["failed"] == 0,
        details=f"{pub['success']}/{pub['total']} Sensoren für {anlage.anlagenname}{fehl}{grund}",
        anlage_id=anlage.id,
    )

    return {
        "message": f"Sensoren für {anlage.anlagenname} publiziert",
        "anlage_id": anlage.id,
        "total": pub["total"],
        "success": pub["success"],
        "failed": pub["failed"],
        "errors": pub["errors"],
    }


@router.delete("/mqtt/remove/{anlage_id}")
async def remove_sensors_mqtt(
    anlage_id: int,
    config: Optional[MQTTConfigRequest] = None,
    db: AsyncSession = Depends(get_db)
):
    """
    Entfernt alle EEDC-Sensoren einer Anlage aus Home Assistant.

    Die Sensoren werden aus dem MQTT Discovery entfernt und
    verschwinden aus HA.
    """
    # Anlage laden
    result = await db.execute(
        select(Anlage).where(Anlage.id == anlage_id)
    )
    anlage = result.scalar_one_or_none()

    if not anlage:
        raise not_found("Anlage")

    # MQTT Client konfigurieren
    mqtt_config = MQTTConfig(
        host=config.host if config else os.environ.get("MQTT_HOST", "core-mosquitto"),
        port=config.port if config else int(os.environ.get("MQTT_PORT", "1883")),
        username=config.username if config else os.environ.get("MQTT_USER"),
        password=config.password if config else os.environ.get("MQTT_PASSWORD"),
    )

    client = MQTTClient(mqtt_config)

    if not client.is_available:
        raise HTTPException(
            status_code=503,
            detail="MQTT nicht verfügbar"
        )

    # Alle Anlage-Sensoren entfernen (inkl. #150-Prognose-/Preis-Sensoren)
    removed = 0
    for sensor in ANLAGE_SENSOREN + PROGNOSE_SENSOREN + PREIS_SENSOREN:
        if await client.remove_sensor(sensor, anlage.id):
            removed += 1

    await log_activity(
        kategorie="ha_export",
        aktion="MQTT-Sensoren entfernt",
        erfolg=True,
        details=f"{removed} Sensoren für {anlage.anlagenname}",
        anlage_id=anlage.id,
    )

    return {
        "message": f"Sensoren für {anlage.anlagenname} entfernt",
        "anlage_id": anlage.id,
        "removed": removed
    }
