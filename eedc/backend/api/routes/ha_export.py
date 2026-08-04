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
from pydantic import BaseModel, model_validator
from typing import Optional, Any
from dataclasses import dataclass
from collections import defaultdict
import os

from backend.core.exceptions import not_found
from backend.core.investition_kennwerte import (
    get_speicher_kapazitaet_kwh,
    get_speicher_nutzbare_kapazitaet_kwh,
)
from backend.api.deps import get_db
from backend.core.berechnungen import (
    DienstlicheLadungZeile,
    FinanzMonatsZeile,
    berechne_dienstliche_ladekosten,
    berechne_finanz_aggregat,
    berechne_wp_alternativkosten_ersparnis,
    berechne_spez_ertrag_annualisiert,
    alter_wirkungsgrad,
    gas_kosten_altanlage,
    berechne_verbrauchs_kennzahlen,
    erzeugung_hinter_zaehler_kwh,
    imd_typ_beitrag,
    monatsgewichte_aus_pvgis,
    vollzyklen as berechne_vollzyklen,
)
from backend.services.prognose_auswahl import lade_aktive_prognose
from datetime import date

from backend.services.finanz_zeilen import baue_finanz_zeile
from backend.services.monats_fakten import finanz_zeile_eingabe, lade_monats_fakten
from backend.api.routes.strompreise import (
    lade_tarife_fuer_anlage,
    resolve_strompreis_for_komponente,
)
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
    get_all_sensor_definitions, runde_exportwert
)
from backend.services.ha_export_prognose import berechne_prognose_export
from backend.services.ha_export_preis import berechne_preis_export
from backend.services.mqtt_client import MQTTClient, MQTTConfig
from backend.services.ha_mqtt_sync import resolve_mqtt_config, publish_anlage_sensors
from backend.services.mqtt_broker_settings import (
    resolve_broker_config,
    broker_aktiviert,
    broker_konfiguriert,
    export_aktiviert,
    MQTT_EXPORT_SETTINGS_KEY,
)
from backend.core.investition_parameter import (
    PARAM_E_AUTO,
    PARAM_E_AUTO_DEFAULTS,
    PARAM_WAERMEPUMPE,
    PARAM_WAERMEPUMPE_DEFAULTS,
    ist_dienstlich,
)
from backend.core.calculations import berechne_co2_bilanz
from backend.core.berechnungen.ust_eigenverbrauch import (
    UstJahresanteil,
    bemessungsgrundlage_aus_investitionen,
    ust_eigenverbrauch_fuer_anlage,
)
from backend.core.wirtschaftlichkeit_defaults import (
    EINSPEISEVERGUETUNG_DEFAULT_CENT,
    NETZBEZUG_DEFAULT_CENT,
    WP_PV_ANTEIL_DEFAULT,
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
    """Einzelner Sensor im Export.

    Die Rundung sitzt HIER und nicht in den drei Routen, die das Item bauen
    (`/sensors` zweimal, `/sensors/{anlage_id}`): dieses Modell IST die
    REST-Serialisierungsgrenze — an ihm vorbei kommt kein Sensorwert nach
    außen, auch eine vierte Route nicht. Damit sagen REST und MQTT dieselbe
    Zahl; vorher lieferte REST roh weiter, was der Produzent gerundet hatte
    (kWh mit einer Nachkommastelle, wo MQTT ganzzahlig publizierte).
    """
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

    @model_validator(mode="after")
    def _runde_wert(self):
        gerundet = runde_exportwert(self.value, self.unit)
        if gerundet is not self.value:
            # `model_construct`-freier Weg: Zuweisung im After-Validator läuft
            # nicht erneut durch die Validierung (Pydantic v2).
            object.__setattr__(self, "value", gerundet)
        return self


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
    """Aufgelöste MQTT-Verbindung + Export-Richtung (B7-5/B7-5b/B7-5d)."""
    enabled: bool  # Verbindung wird genutzt = mindestens eine Richtung an
    host: str
    port: int
    username: str
    password: str  # Wird als Maske zurückgegeben wenn gesetzt
    auto_publish: bool  # Export-Toggle (Eigenwert) — nicht mit `enabled` verundet
    publish_interval_minutes: int
    # Ist überhaupt ein Broker hinterlegt? `host` allein taugt nicht als Antwort:
    # die Auflösung liefert IMMER einen (Default `core-mosquitto`). Ohne Broker
    # kann der Export nichts publizieren — die Sensoren erscheinen dann nie in HA.
    broker_konfiguriert: bool


class AutoPublishRequest(BaseModel):
    """Body für den Export-Toggle (B7-5b)."""
    enabled: bool


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

    # =====================================================================
    # MONATSZEILE AUS DEN MONATS-FAKTEN (ADR-002/P10)
    # =====================================================================
    # Bis 2026-07-31 hat diese Funktion die IMD-Zeilen in VIER getrennten
    # Queries + Schleifen selbst gefaltet (Erzeuger · Speicher · V2H · sonstige
    # Positionen), jede mit ihrer eigenen Filter-Handschrift. Die Rechnung war
    # korrekt — Befund F-5 der Drift-Inventur traf andere Sichten. Umgehängt
    # wird sie trotzdem, weil eine selbst faltende Sicht die nächste Drift-Quelle
    # ist (`docs/KONZEPT-MONATS-FAKTEN.md` §11).
    #
    # Die Schicht lädt Investitionen bewusst OHNE `aktiv`-Vorfilter und
    # entscheidet je Monat über `ist_aktiv_im_monat` (#123: historische
    # Kennzahlen dürfen später stillgelegte Komponenten nicht rückwirkend
    # ausblenden). Der `aktiv_jetzt()`-Vorfilter oben bleibt für alles, was einen
    # HEUTIGEN Zustand beschreibt (kWp, Investitionssummen, Komponenten-Listen);
    # die MENGEN kommen ab jetzt aus der Schicht. Das ist derselbe Schnitt wie
    # im Cockpit — und es ist eine bewegte Zahl für Anlagen mit stillgelegter
    # Komponente (s. Übergabe N-11).
    _tarif_cache: dict[date, dict] = {}
    fakten = await lade_monats_fakten(db, anlage.id, tarif_cache=_tarif_cache)

    # PV je Monat über den Read-time-SoT (Messwerte + Aggregat-Lückenfüllung)
    # statt einer rohen IMD-Summe. Die rohe Summe kannte das Anlagen-Aggregat
    # gar nicht: eine Anlage, deren frühe Monate nur als Gesamtwert vorliegen
    # (Umstellung auf Pro-String-Messung mitten in der Historie), verlor diese
    # Monate im PV-Sensor, im spezifischen Ertrag und in den Finanzzeilen.
    #
    # DI-2-B: Erzeuger hinter dem EINEN Hauszähler zählen in die EV-/Autarkie-/
    # CO₂-Bilanz — deckungsgleich mit dem Cockpit (Layer-SoT
    # `erzeugung_hinter_zaehler_kwh`, v3.45.4):
    #   • Balkonkraftwerk zählt als PV (Cockpit-Konvention) → in `pv_erzeugung`.
    #   • Sonstige Erzeuger (Mini-BHKW/KWK) speisen ebenfalls hinter den Zähler →
    #     zählen in EV/Autarkie, bleiben aber aus den PV-eigenen Kennzahlen
    #     (spez. Ertrag/PR) und aus der PV-Erzeugungs-Anzeige draußen.
    # Falle 1 der S1-Übergabe: `erzeugung.pv_kwh` für die PV-Achse und die
    # Finanz-Zeile, `erzeugung.hinter_zaehler_kwh` für die Bilanz.
    pv_erzeugung = sum(f.erzeugung.pv_kwh for f in fakten)
    sonstiges_erzeugung = sum(f.sonstiges.erzeugung_kwh for f in fakten)

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

    # Speicher-Summen aus den Monats-Fakten (kanonisch über `imd_typ_beitrag`)
    # statt Legacy Monatsdaten. Die frühere Handschrift las die Roh-Schlüssel
    # `ladung_kwh`/`entladung_kwh` direkt (P6-Klasse).
    batterie_ladung = sum(f.speicher.ladung_kwh for f in fakten)
    batterie_entladung = sum(f.speicher.entladung_kwh for f in fakten)

    # Fallback auf Legacy wenn keine InvestitionMonatsdaten
    if batterie_ladung == 0 and batterie_entladung == 0:
        batterie_ladung = sum(m.batterie_ladung_kwh or 0 for m in monatsdaten)
        batterie_entladung = sum(m.batterie_entladung_kwh or 0 for m in monatsdaten)

    # V2H (E-Auto → Haus) wird wie Speicher-Entladung als Eigenverbrauch gezählt.
    # Dienstwagen sind darin nicht mehr enthalten — die Schicht filtert sie,
    # die frühere Schleife hier nicht ([[feedback_dienstwagen_alle_checks]]).
    v2h_entladung = sum(f.emob.v2h_entladung_kwh for f in fakten)

    # #304: Eigenverbrauch/Direktverbrauch/Gesamtverbrauch + Quoten zentral über
    # den SoT-Helper aus IMD-gesourcten Energiemengen (PV + Speicher + V2H) und
    # den Zählerwerten (Einspeisung/Netzbezug) — kanonische Formel, deckungs-
    # gleich mit cockpit/uebersicht.py.
    # DI-2-B: Netzpunkt-Bilanz-Eingang = PV(inkl. BKW) + sonstige Erzeuger,
    # deckungsgleich mit dem Cockpit (`erzeugung_bilanz`, uebersicht.py:416).
    # `pv_erzeugung` selbst (inkl. BKW, ohne BHKW) bleibt für die PV-eigenen
    # Kennzahlen (spez. Ertrag) und die PV-Erzeugungs-Anzeige.
    erzeugung_bilanz = erzeugung_hinter_zaehler_kwh(pv_erzeugung, sonstiges_erzeugung)
    kennzahlen = berechne_verbrauchs_kennzahlen(
        pv_erzeugung_kwh=erzeugung_bilanz,
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
    # Aus derselben Quelle wie `pv_erzeugung`: jeder Monat mit aufgelöster PV
    # zählt, gemessen ODER über das Aggregat gefüllt. Der frühere
    # Zwei-Wege-Aufbau (IMD-Monate, sonst Monate mit Legacy-PV>0) ließ bei
    # gemischter Historie die Aggregat-Monate aus und machte den spezifischen
    # Ertrag dadurch zu hoch.
    spez_covered_months = {f.schluessel for f in fakten if f.erzeugung.pv_je_modul}
    spez_gewichte = None
    if spez_covered_months:
        pvgis = await lade_aktive_prognose(db, anlage.id)
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
    # Sonstige Positionen: aus den Monats-Fakten — sie falten IMD-Positionen
    # (typ-unabhängig, #310) UND die Basis-Positionen der Monatsdaten-Zeile
    # (G19-1) an einer Stelle, gleiche Netto-Faltung wie Cockpit/Jahresbericht.
    sonstige_netto_gesamt = sum(f.sonstiges.netto_euro for f in fakten)

    # Dienstliche Ladekosten — bis 2026-07-31 hat der HA-Export sie als einzige
    # der drei Sichten **gar nicht** abgezogen (N-13): der Sensor
    # `netto_ertrag_euro` stand bei Dienstwagen-Anlagen über der Cockpit-Kachel,
    # auf die er sich bezieht. Gleiche Formel, gleicher Layer-SoT
    # (ADR-001) wie Cockpit/Übersicht und Aussichten; die Mengen kommen aus den
    # Monats-Fakten (Dienstwagen-Filter + PV/Netz-Split, P10).
    sonstige_netto_gesamt -= berechne_dienstliche_ladekosten(
        DienstlicheLadungZeile(
            ladung_pv_kwh=f.emob.dienstlich_ladung_pv_kwh,
            ladung_netz_kwh=f.emob.dienstlich_ladung_netz_kwh,
            netzbezug_preis_cent=f.tarif.netzbezug_preis_cent,
            wallbox_preis_cent=f.tarif.wallbox_preis_effektiv_cent,
        )
        for f in fakten
    ).gesamt_euro

    einspeise_erloes = 0
    ev_ersparnis = 0
    netto_ertrag = sonstige_netto_gesamt
    if strompreis:
        # #326: FinanzMonatsZeile über den gemeinsamen Builder (einzige erlaubte
        # Konstruktions-Stelle, Wächter) — er löst den Tarif PRO MONAT auf
        # (historische Tarife via gueltig_ab/gueltig_bis), nicht den neuesten
        # Strompreis für alle Jahre. Deckungsgleich mit Cockpit/Jahresbericht
        # (rilmor-mhrs: Jahres-Tarife 23,90→32,80 ct). Die Eingabe entsteht aus
        # dem Monats-Fakt (P10) statt aus fünf site-eigenen Maps; `pv_kwh` darin
        # ist „Module + BKW" (P9) mit `None`-Auflösung als 0 statt als Teilsumme
        # (N42). Nur Monate MIT Zählerzeile — ohne gemessene Einspeisung/Bezug
        # gibt es keine Finanz-Zeile.
        finanz_zeilen: list[FinanzMonatsZeile] = [
            await baue_finanz_zeile(
                db, anlage.id, finanz_zeile_eingabe(f), tarif_cache=_tarif_cache
            )
            for f in fakten if f.meta.hat_zaehlerzeile
        ]
        _finanz = berechne_finanz_aggregat(
            finanz_zeilen, sonstige_netto_euro=sonstige_netto_gesamt
        )
        einspeise_erloes = _finanz.einspeise_erloes_euro
        ev_ersparnis = _finanz.ev_ersparnis_euro
        netto_ertrag = _finanz.netto_ertrag_euro

    # CO2 (DI-2): der HA-Sensor „CO2 Einsparung" trägt jetzt die volle
    # Cockpit-Bilanz (PV-Eigenverbrauch + WP + E-Mobilität) statt nur
    # `pv_erzeugung × f_strom`. Berechnung weiter unten, nachdem WP- und
    # E-Mob-Aggregate stehen (kanonischer Helper `berechne_co2_bilanz`).

    # Investitions-KPIs berechnen
    investition_gesamt = sum(i.anschaffungskosten_gesamt or 0 for i in investitionen)
    alternativ_gesamt = sum(i.anschaffungskosten_alternativ or 0 for i in investitionen)
    relevante_kosten = investition_gesamt - alternativ_gesamt
    betriebskosten_ges = sum(i.betriebskosten_jahr or 0 for i in investitionen)

    # #326-Inventur Dimension 2: USt auf Eigenverbrauch bei Regelbesteuerung.
    # Cockpit und Aussichten ziehen sie ab, der HA-Export bisher nicht — der
    # Sensor `netto_ertrag_euro` stand damit um den USt-Betrag über der Kachel,
    # auf die er sich bezieht. Vorprüfung im SoT-Helper.
    #
    # N-129 + N-130: Bemessungsgrundlage jetzt Mehrkosten statt Vollkosten, und
    # gerechnet wird je Kalenderjahr. Der Export kennt keinen Jahres-Filter — er
    # liefert IMMER den Gesamtzeitraum und war deshalb von der Zeitraum-Kollaps-
    # Klasse durchgehend betroffen, nicht nur bei gesetztem Filter.
    # Eingänge je Jahr wie die Perioden-Kennzahlen oben, inkl. derselben
    # Legacy-Fallbacks (dort periodenweit, hier je Jahr geprüft).
    monatsdaten_je_jahr: dict[int, list] = defaultdict(list)
    for _md in monatsdaten:
        monatsdaten_je_jahr[_md.jahr].append(_md)
    fakten_je_jahr: dict[int, list] = defaultdict(list)
    for _f in fakten:
        fakten_je_jahr[_f.jahr].append(_f)

    ust_jahresanteile: list[UstJahresanteil] = []
    for _jahr in sorted(set(monatsdaten_je_jahr) | set(fakten_je_jahr)):
        _f_jahr = fakten_je_jahr.get(_jahr, [])
        _md_jahr = monatsdaten_je_jahr.get(_jahr, [])
        _eins_jahr = sum(m.einspeisung_kwh or 0 for m in _md_jahr)
        _pv_jahr = sum(f.erzeugung.pv_kwh for f in _f_jahr)
        if _pv_jahr == 0:
            _pv_jahr = _eins_jahr + sum(m.eigenverbrauch_kwh or 0 for m in _md_jahr)
        _lad_jahr = sum(f.speicher.ladung_kwh for f in _f_jahr)
        _entl_jahr = sum(f.speicher.entladung_kwh for f in _f_jahr)
        if _lad_jahr == 0 and _entl_jahr == 0:
            _lad_jahr = sum(m.batterie_ladung_kwh or 0 for m in _md_jahr)
            _entl_jahr = sum(m.batterie_entladung_kwh or 0 for m in _md_jahr)
        _kz_jahr = berechne_verbrauchs_kennzahlen(
            pv_erzeugung_kwh=erzeugung_hinter_zaehler_kwh(
                _pv_jahr, sum(f.sonstiges.erzeugung_kwh for f in _f_jahr)
            ),
            einspeisung_kwh=_eins_jahr,
            netzbezug_kwh=sum(m.netzbezug_kwh or 0 for m in _md_jahr),
            speicher_ladung_kwh=_lad_jahr,
            speicher_entladung_kwh=_entl_jahr,
            v2h_entladung_kwh=sum(f.emob.v2h_entladung_kwh for f in _f_jahr),
        )
        ust_jahresanteile.append(UstJahresanteil(
            jahr=_jahr,
            eigenverbrauch_kwh=_kz_jahr.eigenverbrauch_kwh,
            pv_kwh=_pv_jahr,
            monate=max(len(_f_jahr), len(_md_jahr)),
        ))
    ust_eigenverbrauch = ust_eigenverbrauch_fuer_anlage(
        anlage,
        jahresanteile=ust_jahresanteile,
        bemessungsgrundlage_euro=bemessungsgrundlage_aus_investitionen(investitionen),
        betriebskosten_jahr_euro=betriebskosten_ges,
    )
    netto_ertrag -= ust_eigenverbrauch

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

    # DI-4: WP-Strom mit dem WP-Spezialtarif bewerten (Fallback allgemein), wie
    # in aktueller_monat.py — sonst rechnet der HA-Export die WP-Ersparnis mit
    # dem allgemeinen Netzbezugspreis, obwohl ein günstigerer WP-Tarif gepflegt ist.
    # ADR-002/P8: JE MONAT auflösen — die WP-Ersparnis summiert über die ganze
    # Historie, ein Einheitstarif hätte einen Tarifwechsel rückwirkend über alle
    # Jahre gezogen (dieselbe Klasse wie der Jahresbericht-Drift, #326).
    wp_preis_by_periode: dict[tuple[int, int], float] = {}
    for (_inv_id, _p_jahr, _p_monat) in historische_inv_daten:
        _periode = (_p_jahr, _p_monat)
        if _periode in wp_preis_by_periode:
            continue
        _p_tarife = await lade_tarife_fuer_anlage(
            db, anlage.id, target_date=date(_p_jahr, _p_monat, 1)
        )
        wp_preis_by_periode[_periode] = resolve_strompreis_for_komponente(
            _p_tarife, "waermepumpe", fallback=netzbezug_preis_cent
        )

    # Heutiger WP-Tarif: Fallback für Monate ohne Auflösung und Grundlage der
    # nach vorn gerichteten Sensor-Werte weiter unten.
    _tarife = await lade_tarife_fuer_anlage(db, anlage.id)
    wp_netzbezug_preis_cent = resolve_strompreis_for_komponente(
        _tarife, "waermepumpe", fallback=netzbezug_preis_cent
    )

    # WP-Alternativkosten (vs. Gas/Öl) über den Berechnungs-Layer (ADR-001):
    # per-WP-Parameter (kein last-write-wins über waermepumpen), per-Monat-
    # Gaspreis aus Monatsdaten mit Fallback auf den WP-Parameter-Default.
    bisherige_wp_ersparnis = berechne_wp_alternativkosten_ersparnis(
        waermepumpen,
        historische_inv_daten,
        {k: md.gaspreis_cent_kwh for k, md in md_by_periode.items()},
        wp_preis_by_periode,
        wp_netzbezug_preis_cent,
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
    # DI-2: E-Mob-CO₂-Aggregate (Dienstwagen bereits über e_autos ausgeschlossen,
    # deckungsgleich mit der Cockpit-Bilanz): gefahrene km, Heim-Netzladung und
    # der Benzin-Vergleichsverbrauch in Litern (je Fahrzeug sein eigener Wert).
    co2_emob_km = 0.0
    co2_emob_netz_kwh = 0.0
    co2_benzin_liter = 0.0
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
            # DI-2: CO₂-Aggregate mitziehen (gleicher Netz-/km-/Benzin-Pfad).
            co2_emob_km += km
            co2_emob_netz_kwh += netz
            co2_benzin_liter += benzin_liter

    # DI-2: WP-CO₂-Aggregate (gemessene Wärme/Strom) über den kanonischen
    # Zeilen-Helper `imd_typ_beitrag` — dieselbe Wärme-/Strom-Auflösung wie das
    # Cockpit (waerme_kwh-Vorrang, sonst Heizung+Warmwasser; WP-Split-Strom).
    wp_ids = {w.id for w in waermepumpen}
    co2_wp_waerme_kwh = 0.0
    co2_wp_strom_kwh = 0.0
    for (inv_id, _j, _m), daten in historische_inv_daten.items():
        if inv_id in wp_ids:
            _b = imd_typ_beitrag(inv_by_id_export[inv_id], daten)
            co2_wp_waerme_kwh += _b.wp_waerme
            co2_wp_strom_kwh += _b.wp_strom

    # DI-2: Gesamt-CO₂-Bilanz (PV-Eigenverbrauch + WP + E-Mob) über den
    # kanonischen Helper — deckungsgleich mit der Cockpit-Kachel `co2_gesamt_kg`.
    co2_ersparnis = berechne_co2_bilanz(
        eigenverbrauch_kwh=eigenverbrauch,
        wp_waerme_kwh=co2_wp_waerme_kwh,
        wp_strom_kwh=co2_wp_strom_kwh,
        emob_km=co2_emob_km,
        emob_netz_ladung_kwh=co2_emob_netz_kwh,
        benzin_verbrauch_liter=co2_benzin_liter,
    ).co2_gesamt_kg

    # BKW: KEIN eigener Posten mehr (ADR-002/P9). Die Ersparnis steckt seit
    # 2026-07-31 in `netto_ertrag` — entweder über die gemeinsame PV-Basis der
    # Finanz-Zeilen (Erzeugung erfasst) oder über deren Rest-Eigenverbrauchs-
    # Term (nicht erfasst), beides mit dem Preis DES MONATS. Der frühere
    # Zuschlag hier rechnete mit einem statischen Netzbezugspreis und tauchte
    # im Sensor `netto_ertrag_euro` gar nicht auf, nur in ROI/Amortisation.
    historischer_netto_ertrag = (
        netto_ertrag
        + bisherige_wp_ersparnis
        + bisherige_eauto_ersparnis
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
            # Zyklen-Basis ist die BRUTTO-Kapazität — dieselbe Konvention wie in
            # Monatsbericht, Speicher-Dashboard und Jahresbericht
            # (docs/BERECHNUNGEN.md §3.3). Der Kommentar behauptete hier
            # früher, `nutzbare_kapazitaet_kwh` sei ein Override; der Code liest
            # aber bewusst zuerst Brutto. Ein Dreher hätte den HA-Sensor gegen
            # den Monatsbericht laufen lassen (R22-4). `nutzbare_kapazitaet_kwh`
            # ist nur der Fallback, wenn Brutto nicht gepflegt ist; ist beides
            # leer → kein Speicher gepflegt.
            #
            # A31-2: die Lese-REIHENFOLGE bleibt genau so — dies ist der
            # Vollzyklen-Nenner, und der ist brutto (Kanon
            # `core/berechnungen/speicher.py::vollzyklen`, Entscheidung Gernot
            # 2026-07-28). Der Netto-Umstieg von A31-2 gilt für Simulation und
            # Wirtschaftlichkeits-Prognose, NICHT hier. Migriert ist nur der
            # Zugriffsweg: statt zweier Roh-Lesungen die beiden SoT-Helper —
            # `get_speicher_nutzbare_kapazitaet_kwh` greift erst, wenn brutto
            # `None` ist, und liefert dann den Netto-Wert (sein eigener
            # Brutto-Fallback läuft in diesem Fall ins Leere). Identisches
            # Verhalten, nur ohne Literal-Zugriff.
            kap = get_speicher_kapazitaet_kwh(inv) or get_speicher_nutzbare_kapazitaet_kwh(inv)
            if kap:
                speicher_kapazitaet += float(kap)

    if batterie_ladung > 0:
        speicher_effizienz = (batterie_entladung / batterie_ladung) * 100
    # Layer-SoT statt eigener Division — dieselbe Zahl wie Hub/Monat/PDF.
    speicher_zyklen = berechne_vollzyklen(batterie_entladung, speicher_kapazitaet)

    # Sensor-Werte erstellen
    sensor_values = []

    # Energie-Sensoren
    for sensor in ANLAGE_SENSOREN:
        value = None
        berechnung = None

        if sensor.key == "pv_erzeugung_gesamt_kwh":
            value = pv_erzeugung
            berechnung = f"Summe aus {len(monatsdaten)} Monaten"
        elif sensor.key == "direktverbrauch_gesamt_kwh":
            value = direktverbrauch
            berechnung = f"PV direkt verbraucht (ohne Speicher)"
        elif sensor.key == "eigenverbrauch_gesamt_kwh":
            value = eigenverbrauch
        elif sensor.key == "einspeisung_gesamt_kwh":
            value = einspeisung
        elif sensor.key == "netzbezug_gesamt_kwh":
            value = netzbezug
        elif sensor.key == "gesamtverbrauch_kwh":
            value = gesamtverbrauch
            berechnung = f"{eigenverbrauch:.0f} + {netzbezug:.0f}"
        elif sensor.key == "autarkie_prozent":
            value = autarkie
            berechnung = f"{eigenverbrauch:.0f} ÷ {gesamtverbrauch:.0f} × 100"
        elif sensor.key == "eigenverbrauch_quote_prozent":
            value = ev_quote
            # DI-2-B: Nenner = Netzpunkt-Erzeugung (PV inkl. BKW + sonstige
            # Erzeuger), deckungsgleich mit der Cockpit-EV-Quote.
            berechnung = f"{eigenverbrauch:.0f} ÷ {erzeugung_bilanz:.0f} × 100"
        elif sensor.key == "spezifischer_ertrag_kwh_kwp":
            value = spez_ertrag if spez_ertrag else None
            if value is not None:
                berechnung = (
                    f"{pv_erzeugung:.0f} kWh annualisiert "
                    f"(saisonal gewichtet, wie Cockpit)"
                )
        elif sensor.key == "netto_ertrag_euro":
            value = netto_ertrag
            berechnung = f"{einspeise_erloes:.2f} + {ev_ersparnis:.2f} + {sonstige_netto_gesamt:.2f} (sonstige)"
        elif sensor.key == "einspeise_erloes_euro":
            value = einspeise_erloes
            if strompreis:
                berechnung = f"{einspeisung:.0f} × {strompreis.einspeiseverguetung_cent_kwh:.2f} ct/kWh"
        elif sensor.key == "eigenverbrauch_ersparnis_euro":
            value = ev_ersparnis
            if strompreis:
                berechnung = f"{eigenverbrauch:.0f} × {strompreis.netzbezug_arbeitspreis_cent_kwh:.2f} ct/kWh"
        elif sensor.key == "co2_ersparnis_kg":
            value = co2_ersparnis
            berechnung = "PV-Eigenverbrauch + Wärmepumpe + E-Mobilität (vermiedenes CO₂)"

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
                value = investition_gesamt
                berechnung = f"Summe aus {len(investitionen)} Investitionen"
        elif sensor.key == "jahres_ersparnis_euro":
            if jahres_ersparnis > 0:
                value = jahres_ersparnis
                berechnung = f"({historischer_netto_ertrag:.2f} ÷ {anzahl_monate}) × 12"
        elif sensor.key == "roi_prozent":
            if roi_prozent is not None:
                value = roi_prozent
                berechnung = f"{jahres_ersparnis:.2f} ÷ {relevante_kosten:.2f} × 100"
        elif sensor.key == "amortisation_jahre":
            if amortisation_jahre is not None:
                value = amortisation_jahre
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
                    value = speicher_zyklen
                    berechnung = f"{batterie_entladung:.0f} ÷ {speicher_kapazitaet:.1f}"
            elif sensor.key == "speicher_effizienz_prozent":
                if speicher_effizienz is not None:
                    value = speicher_effizienz
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
                    value=investition.anschaffungskosten_gesamt,
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
                    value = gesamt_km
                    berechnung = f"Summe aus {len(monatsdaten)} Monaten"
            elif sensor.key == "e_auto_verbrauch_kwh_100km":
                if gesamt_km > 0 and gesamt_verbrauch > 0:
                    value = gesamt_verbrauch / gesamt_km * 100
                    berechnung = f"{gesamt_verbrauch:.0f} / {gesamt_km:.0f} × 100"
            elif sensor.key == "e_auto_pv_anteil_prozent":
                if gesamt_ladung > 0:
                    value = gesamt_pv_ladung / gesamt_ladung * 100
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
                    value = benzin_kosten - strom_kosten
                    berechnung = f"{benzin_kosten:.2f} (Benzin) - {strom_kosten:.2f} (Strom)"

            if value is not None:
                sensor_values.append(SensorValue(
                    definition=sensor,
                    value=value,
                    berechnung=berechnung
                ))

    # Wärmepumpe Sensoren
    elif investition.typ == "waermepumpe":
        # DI-4: WP-Strom mit dem WP-Spezialtarif bewerten (Fallback allgemein),
        # deckungsgleich mit aktueller_monat.py und der Anlage-Aggregation oben.
        _wp_tarife = await lade_tarife_fuer_anlage(db, investition.anlage_id)
        wp_netzbezug_preis = resolve_strompreis_for_komponente(
            _wp_tarife, "waermepumpe", fallback=netzbezug_preis
        )
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
                    value = gesamt_waerme / gesamt_strom
                    berechnung = f"{gesamt_waerme:.0f} / {gesamt_strom:.0f}"
            elif sensor.key == "wp_ersparnis_euro":
                if gesamt_waerme > 0:
                    fallback_alter_preis = params.get(PARAM_WAERMEPUMPE["ALTER_PREIS_CENT_KWH"], PARAM_WAERMEPUMPE_DEFAULTS["alter_preis_cent_kwh"])
                    wirkungsgrad_alt = alter_wirkungsgrad(params.get(PARAM_WAERMEPUMPE["ALTER_ENERGIETRAEGER"]))
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
                        alte_kosten += gas_kosten_altanlage(waerme, wirkungsgrad_alt, gp)
                    # Fixe Zusatzkosten anteilig
                    alte_kosten += zusatzkosten_jahr * len(monatsdaten) / 12
                    wp_kosten = gesamt_strom * wp_netzbezug_preis / 100
                    value = alte_kosten - wp_kosten
                    berechnung = f"{alte_kosten:.2f} (alt) - {wp_kosten:.2f} (WP)"
            elif sensor.key == "wp_kompressor_starts":
                if hat_starts:
                    value = wp_starts_total
                    berechnung = "Σ erfasste Kompressor-Starts"
            elif sensor.key == "wp_betriebsstunden":
                if hat_stunden:
                    value = wp_stunden_total
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
async def get_mqtt_config(db: AsyncSession = Depends(get_db)):
    """Gibt die aufgelöste MQTT-Broker-Konfiguration zurück.

    B7-5: Quelle ist jetzt der **gemeinsame Broker** (DB-Broker-Block → ENV-Fallback
    = Add-on-Optionen), nicht mehr ENV allein — sonst zeigt der Export-Block einen
    anderen Broker an als den, auf den er publiziert (#655-Klasse).

    B7-5b: ``auto_publish`` ist der **Eigenwert des Export-Toggles** (DB → ENV),
    bewusst NICHT mit ``enabled`` (Broker) verundet: der Switch im Block soll den
    eigenen Zustand zeigen und nicht umspringen, wenn jemand den Broker abschaltet.
    Die Und-Verknüpfung „darf jetzt publiziert werden" macht der Job selbst.
    """
    from backend.core.config import settings

    cfg = await resolve_broker_config(db)

    # Passwort als Maske zurückgeben wenn gesetzt
    password_masked = "••••••" if cfg.password else ""

    return MQTTConfigResponse(
        enabled=await broker_aktiviert(db),
        host=cfg.host,
        port=cfg.port,
        username=cfg.username or "",
        password=password_masked,
        auto_publish=await export_aktiviert(db),
        publish_interval_minutes=settings.mqtt_publish_interval,
        broker_konfiguriert=await broker_konfiguriert(db),
    )


@router.post("/mqtt/auto-publish")
async def set_auto_publish(payload: AutoPublishRequest, db: AsyncSession = Depends(get_db)):
    """Schaltet den automatischen Export (Auto-Publish) ein/aus — B7-5b.

    Schreibt den DB-Settings-Key ``mqtt_export``; ENV bleibt reiner Fallback für
    Bestandsinstallationen ohne Eintrag. Wirkt sofort — der Scheduler-Job prüft
    die Einstellung bei jedem Lauf, ein Neustart ist nicht nötig.
    """
    from backend.models.settings import Settings as SettingsModel
    from sqlalchemy.orm.attributes import flag_modified

    setting = (
        await db.execute(
            select(SettingsModel).where(SettingsModel.key == MQTT_EXPORT_SETTINGS_KEY)
        )
    ).scalar_one_or_none()

    if setting:
        setting.value = {"enabled": payload.enabled}
        flag_modified(setting, "value")
    else:
        db.add(SettingsModel(key=MQTT_EXPORT_SETTINGS_KEY, value={"enabled": payload.enabled}))
    await db.commit()

    return {"gespeichert": True, "enabled": payload.enabled}


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
async def test_mqtt_connection(
    config: Optional[MQTTConfigRequest] = None,
    db: AsyncSession = Depends(get_db),
):
    """Testet die MQTT-Verbindung zum Broker (gemeinsamer Broker, B7-5)."""
    mqtt_config = await resolve_broker_config(
        db,
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

    # Broker-Config: Override-Felder aus dem Request, sonst gemeinsamer Broker
    # (DB-Broker-Block → ENV, #655/B7-5).
    mqtt_config = await resolve_broker_config(
        db,
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

    # B7-5: baute den MQTTConfig bisher von Hand aus ENV und umging damit den
    # Resolver — genau der Broker-Mismatch aus #655 (Remove traf einen anderen
    # Broker als Publish). Jetzt der gemeinsame Weg.
    mqtt_config = await resolve_broker_config(
        db,
        config.host if config else None,
        config.port if config else None,
        config.username if config else None,
        config.password if config else None,
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
