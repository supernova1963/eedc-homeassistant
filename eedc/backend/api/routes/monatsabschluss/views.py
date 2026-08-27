"""
Monatsabschluss API — Read- und Vorschau-Endpoints.

GET  /{anlage_id}/{jahr}/{monat}                — Status aller Felder, Vorschläge, Warnungen
GET  /naechster/{anlage_id}                     — Nächster unvollständiger Monat
GET  /historie/{anlage_id}                      — Historie der letzten N Monatsabschlüsse

Schreib-Pfad (POST {anlage_id}/{jahr}/{monat}) liegt in wizard.py.
"""

from calendar import monthrange
from datetime import date, datetime
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.core.exceptions import not_found
from backend.api.routes.strompreise import lade_tarife_fuer_anlage
from backend.core.database import get_db
from backend.core.field_definitions import (
    OPTIONALE_FELDER,
    ZAEHLERSTAND_FELD,
    basis_feld_key,
    einheit_fuer,
    get_basis_felder,
    get_felder_fuer_investition,
    ist_zaehler_differenz_feld,
)
from backend.models.anlage import Anlage
from backend.models.investition import InvestitionMonatsdaten
from backend.models.monatsdaten import Monatsdaten
from backend.services.cloud_import.quellen import lade_quellen
from backend.services.ha_state_service import get_ha_state_service
from backend.services.mqtt_inbound_service import get_mqtt_inbound_service
from backend.services.provenance import (
    ABGELEITET_KAPAZITAET_ANTEIL,
    ABGELEITET_KWP_ANTEIL,
)
from backend.services.vorschlag_service import Vorschlag, VorschlagQuelle, VorschlagService
from backend.services.zaehlerstaende import lade_zaehlerstaende

from ._shared import (
    MONAT_NAMEN,
    _vorschlag_to_response,
    _warnung_to_response,
    logger,
)

router = APIRouter()


# =============================================================================
# Konfidenz der Connector-Vorschläge
# =============================================================================
# Ein Connector liefert EINEN Zählerstand pro Kategorie (PV gesamt, Batterie
# gesamt). Gibt es mehrere Module/Speicher, wird dieser Gesamtwert anteilig
# nach Nennleistung bzw. Kapazität zerlegt (`_distribute_by_param`) — der
# Vorschlag je Gerät ist dann KEINE Messung dieses Geräts, sondern ein Modell.
# Es ist dieselbe Einschränkung, die der Daten-Checker als „Pro-String-
# Genauigkeit eingeschränkt" meldet (services/daten_checker/energieprofil.py).
#
# Eine projektweite Konfidenz-Skala gibt es nicht; die Nachbarwerte sind:
#   95 WP-Gesamtstrom = Σ(Heizen+WW) · 92 HA-Statistik · 91 MQTT-Inbound ·
#   90 Connector-Zählerstand · 90/55 Speicher-Ladepreis · 85 Kraftstoffpreis ·
#   80 Vormonat · 70 Vorjahr / HA-Momentanwert · 60 WP-Wärme = Strom×COP ·
#   50 Ø 12 Monate · 30 Jahresfahrleistung÷12
# (services/vorschlag_service.py, strompreis_aggregator.py, views.py).
#
# Der verteilte Wert liegt deshalb unter JEDER gemessenen Quelle (90/91/92),
# aber über „Wert vom Vormonat" (80): Summe und Monat sind gemessen, nur der
# Verteilungsschlüssel ist gerechnet.
KONFIDENZ_CONNECTOR_GEMESSEN = 90
KONFIDENZ_CONNECTOR_VERTEILT = 85

# Welche Ableitungs-Marke ein zerlegter Vorschlag trägt — die Zerlegung folgt
# dem Kennwert des Geräts (#352): PV nach kWp, Speicher nach Kapazität, wie
# `_mapped_or_distribute` es rechnet.
_ABGELEITET_JE_FELD = {
    "pv_erzeugung_kwh": ABGELEITET_KWP_ANTEIL,
    "ladung_kwh": ABGELEITET_KAPAZITAET_ANTEIL,
    "entladung_kwh": ABGELEITET_KAPAZITAET_ANTEIL,
}


def _abgeleitet_marke(feld: str) -> Optional[str]:
    """Marke für ein zerlegtes Feld; ``None`` für Felder ohne Zerlegung."""
    return _ABGELEITET_JE_FELD.get(feld)


# =============================================================================
# Pydantic-Models — view-spezifisch
# =============================================================================

class FeldStatus(BaseModel):
    """Status eines einzelnen Feldes."""
    feld: str
    label: str
    einheit: str
    aktueller_wert: Optional[float] = None
    aktueller_text: Optional[str] = None  # Für Textfelder wie Beschreibung, Notizen
    quelle: Optional[str] = None  # ha_sensor, snapshot, manuell, berechnet
    vorschlaege: list = []
    warnungen: list = []
    strategie: Optional[str] = None  # Aus sensor_mapping
    sensor_id: Optional[str] = None  # Wenn strategie=sensor
    typ: str = "number"  # number oder text
    gruppe: Optional[str] = None  # zaehler, wetter, preise (für Frontend-Gruppierung)
    # PN 90128: die vom Nutzer bewusst behaltene Situation dieses Feldes —
    # {"sensor": <Vorschlagswert damals>, "wert": <behaltener Wert>} oder None.
    # Der Client zeigt „weicht ab" nicht mehr als offenen Punkt, solange beide
    # Werte noch stimmen; die Abweichung bleibt sichtbar (kein Wegklicken).
    geprueft_gegen: Optional[dict] = None


class InvestitionStatus(BaseModel):
    """Status einer Investition im Monatsabschluss."""
    id: int
    typ: str
    bezeichnung: str
    felder: list[FeldStatus]
    kategorie: Optional[str] = None          # Für Typ "sonstiges": erzeuger/verbraucher/speicher
    sonstige_positionen: list[dict] = []     # Strukturierte Erträge & Ausgaben


class MonatsabschlussResponse(BaseModel):
    """Vollständiger Status für einen Monat."""
    anlage_id: int
    anlage_name: str
    jahr: int
    monat: int
    ist_abgeschlossen: bool
    ha_mapping_konfiguriert: bool
    connector_konfiguriert: bool = False
    cloud_import_konfiguriert: bool = False
    mqtt_inbound_konfiguriert: bool = False
    portal_import_vorhanden: bool = False
    datenquelle: Optional[str] = None  # "portal_import", "cloud_import", "mqtt_inbound", "manual", etc.

    # Basis-Felder (Zählerdaten)
    basis_felder: list[FeldStatus]

    # Optionale Felder (Sonderkosten, Notizen - nicht aus HA)
    optionale_felder: list[FeldStatus] = []

    # Investition-Felder
    investitionen: list[InvestitionStatus]


class NaechsterMonatResponse(BaseModel):
    """Nächster unvollständiger Monat."""
    anlage_id: int
    anlage_name: str
    jahr: int
    monat: int
    monat_name: str
    ha_mapping_konfiguriert: bool


# =============================================================================
# Endpoints
# =============================================================================

@router.get("/{anlage_id}/{jahr}/{monat}", response_model=MonatsabschlussResponse)
async def get_monatsabschluss(
    anlage_id: int,
    jahr: int,
    monat: int,
    db: AsyncSession = Depends(get_db),
):
    """
    Gibt Status aller Felder für einen Monat zurück.

    Enthält:
    - Aktuelle Werte (falls vorhanden)
    - Vorschläge für fehlende/leere Felder
    - Plausibilitätswarnungen
    - Mapping-Informationen
    """
    # Anlage laden
    result = await db.execute(
        select(Anlage)
        .options(selectinload(Anlage.investitionen))
        .where(Anlage.id == anlage_id)
    )
    anlage = result.scalar_one_or_none()
    if not anlage:
        raise not_found("Anlage")

    vorschlag_service = VorschlagService(db)
    sensor_mapping = anlage.sensor_mapping or {}
    basis_mapping = sensor_mapping.get("basis", {})
    inv_mappings = sensor_mapping.get("investitionen", {})

    # Connector-Status und Monatswerte berechnen
    connector_config = anlage.connector_config
    connector_konfiguriert = bool(connector_config and connector_config.get("connector_id"))
    # N-229: Seit mehrere Quellen speicherbar sind, steht dort eine Liste —
    # `lade_quellen` liest beide Formen. Ein roher `.get("provider_id")` wäre
    # an der neuen Form ein AttributeError.
    cloud_import_konfiguriert = bool(lade_quellen(connector_config))
    connector_delta: Optional[dict] = None
    connector_inv_verteilung: dict[int, dict[str, float]] = {}
    # Felder, deren Vorschlagswert ein ZERLEGTER Anlagen-Gesamtwert ist (mehr als
    # ein Empfänger): {inv_id: {feld: Beschreibung}}. Steuert Beschriftung und
    # Konfidenz — bei genau einem Modul/Speicher geht der Zählerstand
    # unverändert dorthin, das ist eine Messung und bleibt als solche etikettiert.
    connector_inv_verteilt_hinweis: dict[int, dict[str, str]] = {}

    if connector_konfiguriert:
        from backend.api.routes.connector import _calc_month_delta, _mapped_or_distribute
        snapshots = connector_config.get("meter_snapshots", {})
        # Explizite Kategorie→Investition-Zuordnung — dieselbe SoT wie die
        # Connector-Vorschau (`api/routes/connector.py:484`) und die
        # MQTT-Energie-Bridge. Wer sein Wechselrichter-Feld einem Modul
        # zugeordnet hat, bekommt dessen Wert und keine kWp-Zerlegung.
        field_inv_map = connector_config.get("field_inv_map") or {}
        if snapshots:
            _delta = _calc_month_delta(snapshots, jahr, monat)
            connector_delta = _delta.werte if _delta else None
            # PV auf Module verteilen
            if connector_delta:
                pv_kwh = connector_delta.get("pv_erzeugung_kwh")
                if pv_kwh is not None and pv_kwh > 0:
                    pv_module = [i for i in anlage.investitionen if i.typ == "pv-module"]
                    if pv_module:
                        verteilung = _mapped_or_distribute(
                            field_inv_map, "pv", pv_module, pv_kwh, "leistung_kwp"
                        )
                        # Genau ein Empfänger = der Zählerstand geht unverzerrt
                        # dorthin (ein Modul, oder eine explizite Zuordnung).
                        ist_verteilt = len(verteilung) > 1
                        for inv, anteil in verteilung:
                            connector_inv_verteilung.setdefault(inv.id, {})["pv_erzeugung_kwh"] = anteil
                            if ist_verteilt:
                                connector_inv_verteilt_hinweis.setdefault(inv.id, {})["pv_erzeugung_kwh"] = (
                                    "anteilig nach kWp auf die Strings verteilt — "
                                    "Pro-String-Genauigkeit eingeschränkt"
                                )
                # Batterie auf Speicher verteilen
                for bat_feld, inv_feld in [
                    ("batterie_ladung_kwh", "ladung_kwh"),
                    ("batterie_entladung_kwh", "entladung_kwh"),
                ]:
                    bat_val = connector_delta.get(bat_feld)
                    if bat_val is not None and bat_val > 0:
                        speicher = [i for i in anlage.investitionen if i.typ == "speicher"]
                        if speicher:
                            verteilung = _mapped_or_distribute(
                                field_inv_map, "speicher", speicher, bat_val, "kapazitaet_kwh"
                            )
                            ist_verteilt = len(verteilung) > 1
                            for inv, anteil in verteilung:
                                connector_inv_verteilung.setdefault(inv.id, {})[inv_feld] = anteil
                                if ist_verteilt:
                                    connector_inv_verteilt_hinweis.setdefault(inv.id, {})[inv_feld] = (
                                        "anteilig nach Kapazität auf die Speicher verteilt — "
                                        "Pro-Speicher-Genauigkeit eingeschränkt"
                                    )

    # MQTT Inbound Energy-Daten sammeln
    mqtt_energy: dict[str, float] = {}
    mqtt_inv_energy: dict[int, dict[str, float]] = {}  # inv_id → {feld: wert}
    mqtt_svc = get_mqtt_inbound_service()
    if mqtt_svc:
        energy = mqtt_svc.cache.get_energy_data(anlage.id)
        if energy:
            # ⛔ F-66 (gruaGit, Discussion #396): Der Cache trägt den zuletzt
            # empfangenen **Zählerstand**, nicht die Monatsmenge — so sagt es die
            # Topic-Registry, und so schreibt der Absender. Bis zum 27.08. wurde
            # dieser Stand hier ungerechnet als „Monatswert" mit Konfidenz 91
            # angeboten: elf Felder meldeten „weicht ab" (6675,3 gegen 552,75),
            # und „Sensorwert übernehmen" daneben hätte den Lebensstand als
            # Monatsmenge gespeichert. Jetzt wird die **Menge des angefragten
            # Monats** aus den mitgeschriebenen Ständen gebildet.
            #
            # ⭐ Der Monatsbezug ist der zweite Teil des Fehlers und wiegt ebenso
            # schwer: Der Cache kennt nur das Jetzt. Für einen Monat aus dem
            # Frühjahr stand hier der heutige Stand — ein Vorschlag, der die
            # Frage gar nicht gehört hat, die er beantwortet.
            from backend.services.mqtt_energy_history_service import mqtt_monats_deltas
            from backend.services.snapshot.keys import extract_quellen_energy

            # Laufender Monat: bis jetzt, nicht bis zum Monatsende — ein Stand in
            # der Zukunft existiert nicht, und `delta` lieferte sonst None.
            _jetzt = datetime.now()
            _bis = _jetzt if (jahr, monat) == (_jetzt.year, _jetzt.month) else None
            monats_mengen = await mqtt_monats_deltas(
                db, anlage.id, jahr, monat, list(energy.keys()),
                quellen_energy=extract_quellen_energy(anlage), bis=_bis,
            )

            # Basis-Felder
            basis_map = {
                "einspeisung_kwh": "einspeisung_kwh",
                "netzbezug_kwh": "netzbezug_kwh",
            }
            for mqtt_key, feld_name in basis_map.items():
                val = monats_mengen.get(mqtt_key)
                if val is not None and val > 0:
                    mqtt_energy[feld_name] = val

            # Investitions-Felder: inv/{inv_id}/{key}
            for mqtt_key, val in monats_mengen.items():
                if not mqtt_key.startswith("inv/") or val is None or val <= 0:
                    continue
                parts = mqtt_key.split("/", 2)  # ["inv", "3", "ladung_kwh"]
                if len(parts) == 3:
                    try:
                        inv_id = int(parts[1])
                        mqtt_inv_energy.setdefault(inv_id, {})[parts[2]] = val
                    except ValueError:
                        pass

    # Bestehende Monatsdaten laden
    md_result = await db.execute(
        select(Monatsdaten)
        .where(and_(
            Monatsdaten.anlage_id == anlage_id,
            Monatsdaten.jahr == jahr,
            Monatsdaten.monat == monat,
        ))
    )
    monatsdaten = md_result.scalar_one_or_none()

    # HA Statistics Service für Sensor-Vorschläge
    ha_stats_werte: dict[str, float] = {}  # sensor_id → differenz
    # N-156/F-26: kein vorgeschaltetes `HA_INTEGRATION_AVAILABLE`
    # (= SUPERVISOR_TOKEN) mehr — `is_available` in der nächsten Zeile stellt
    # dieselbe Frage und beantwortet sie für beide Wege (Recorder-DB oder
    # WebSocket). Wer HA per Long-Lived-Token angebunden hat, bekam bis
    # 2026-08-11 im Monatsabschluss **keine** Sensor-Vorschläge, obwohl die
    # Langzeitstatistik erreichbar war.
    import asyncio

    # Alle sensor_ids aus dem Mapping sammeln — **vor** der Erreichbarkeitsfrage:
    # `is_available` baut im Zweifel eine Verbindung auf und zahlt bei nicht
    # erreichbarer HA einen vollen Timeout. Ohne einen einzigen Sensor-Eintrag
    # gibt es hier nichts zu holen, und ein Betrieb ganz ohne HA darf für diese
    # Antwort nicht warten.
    all_sensor_ids = []
    for cfg in basis_mapping.values():
        if cfg and cfg.get("strategie") == "sensor" and cfg.get("sensor_id"):
            all_sensor_ids.append(cfg["sensor_id"])
    for inv_cfg in inv_mappings.values():
        if isinstance(inv_cfg, dict):
            for fcfg in inv_cfg.get("felder", inv_cfg).values():
                if isinstance(fcfg, dict) and fcfg.get("strategie") == "sensor" and fcfg.get("sensor_id"):
                    all_sensor_ids.append(fcfg["sensor_id"])

    if all_sensor_ids:
        from backend.services.ha_statistics_service import get_ha_statistics_service
        ha_stats_svc = get_ha_statistics_service()
        if ha_stats_svc.is_available:
            try:
                stats_result = await asyncio.to_thread(ha_stats_svc.get_monatswerte, all_sensor_ids, jahr, monat)
                ha_stats_werte = {s.sensor_id: s.differenz for s in stats_result.sensoren if s.differenz is not None}
            except Exception:
                logger.warning("HA Statistics DB nicht erreichbar für Monatsabschluss-Vorschläge")

    # Datenquelle des Monats ermitteln
    datenquelle = getattr(monatsdaten, "datenquelle", None) if monatsdaten else None
    # PN 90128: bewusst behaltene Abweichungen (Basis-Felder) — je Feld
    # {"sensor": …, "wert": …}; leer, solange nichts bestätigt wurde.
    basis_geprueft = (getattr(monatsdaten, "geprueft_gegen", None) or {}) if monatsdaten else {}

    # Bedingungen für bedingte Basis-Felder ermitteln. Stichtag ist der Monat,
    # der abgeschlossen wird — sonst entscheidet die HEUTIGE Vertragsart, ob das
    # Feld „Ø Strompreis" erscheint: nach einem Wechsel dynamisch → fest käme man
    # an den abgerechneten Ø eines Altmonats nicht mehr heran.
    tarife = await lade_tarife_fuer_anlage(db, anlage_id, target_date=date(jahr, monat, 1))
    allgemein_tarif = tarife.get("allgemein")
    hat_dynamischen_tarif = bool(allgemein_tarif and allgemein_tarif.vertragsart == "dynamisch")
    # #392: dieselbe Stichtags-Logik für die variable Einspeisevergütung —
    # entscheidend ist der Tarif des abzuschließenden Monats, nicht der heutige.
    hat_variable_einspeisung = bool(
        allgemein_tarif and getattr(allgemein_tarif, "einspeisung_variabel", False)
    )
    aktive_inv_typen = {i.typ for i in anlage.investitionen if not i.stilllegungsdatum}

    # Alle Basis-Felder aus Registry (inkl. aufgelöster bedingter Felder)
    alle_basis_felder = get_basis_felder(
        hat_dynamischen_tarif=hat_dynamischen_tarif,
        aktive_inv_typen=aktive_inv_typen,
        hat_variable_einspeisung=hat_variable_einspeisung,
    )

    # Basis-Felder aufbereiten
    basis_felder: list[FeldStatus] = []
    for feld_config in alle_basis_felder:
        feld = feld_config["feld"]
        aktueller_wert = getattr(monatsdaten, feld, None) if monatsdaten else None

        # Mapping-Info - verwende mapping_key aus der Konfiguration
        mapping_key = feld_config.get("mapping_key", feld)
        mapping_info = basis_mapping.get(mapping_key, {})
        strategie = mapping_info.get("strategie") if mapping_info else None
        sensor_id = mapping_info.get("sensor_id") if mapping_info else None

        # Quelle bestimmen
        quelle = None
        if aktueller_wert is not None:
            quelle = datenquelle if datenquelle else "manuell"

        # Vorschläge holen (historische Daten) — nur für Standard-Basis-Felder
        vorschlaege = await vorschlag_service.get_vorschlaege(
            anlage_id, feld, jahr, monat
        )

        # Bei konfiguriertem Sensor: HA Statistics Wert als Vorschlag hinzufügen
        if strategie == "sensor" and sensor_id and sensor_id in ha_stats_werte:
            stats_wert = ha_stats_werte[sensor_id]
            if stats_wert > 0:
                vorschlaege.insert(0, Vorschlag(
                    wert=round(stats_wert, 1),
                    quelle=VorschlagQuelle.HA_STATISTICS,
                    konfidenz=92,
                    beschreibung="Aus HA-Statistik (Recorder-DB)",
                ))

        # Connector-Vorschlag einfügen
        if connector_delta and feld in connector_delta:
            conn_wert = connector_delta[feld]
            if conn_wert is not None and conn_wert > 0:
                vorschlaege.insert(0, Vorschlag(
                    wert=round(conn_wert, 1),
                    quelle=VorschlagQuelle.LOCAL_CONNECTOR,
                    # Basis-Feld = anlagenweiter Zählerstand, nichts verteilt.
                    konfidenz=KONFIDENZ_CONNECTOR_GEMESSEN,
                    beschreibung="Vom Wechselrichter (Zählerstand-Differenz)",
                ))

        # MQTT Inbound-Vorschlag einfügen (Konfidenz 91)
        if feld in mqtt_energy:
            vorschlaege.insert(0, Vorschlag(
                wert=mqtt_energy[feld],
                quelle=VorschlagQuelle.MQTT_INBOUND,
                konfidenz=91,
                beschreibung="Aus MQTT-Zählerständen (Differenz über den Monat)",
            ))

        # ── Feld-spezifische Vorschläge (bedingte Felder) ──────────────────
        if feld == "netzbezug_durchschnittspreis_cent":
            # 1. Verbrauchsgewichteter Ø aus Energieprofil-Stundendaten (höchste Qualität)
            from backend.services.strompreis_aggregator import berechne_monats_durchschnittspreis
            aggr = await berechne_monats_durchschnittspreis(anlage_id, jahr, monat, db)
            if aggr and aggr.gewichtet_cent is not None:
                abdeckung_pct = round(aggr.abdeckung * 100)
                vorschlaege.insert(0, Vorschlag(
                    wert=aggr.gewichtet_cent,
                    quelle=VorschlagQuelle.BERECHNUNG,
                    konfidenz=aggr.konfidenz,
                    beschreibung=(
                        f"Verbrauchsgewichteter Ø aus {aggr.abgedeckte_stunden} "
                        f"Stundenpreisen ({abdeckung_pct} % Abdeckung)"
                    ),
                ))
            # 2. HA-Sensor-Vorschlag als Fallback (Momentanwert, weniger genau)
            if strategie == "sensor" and sensor_id:
                ha_state_svc = get_ha_state_service()
                sensor_wert = await ha_state_svc.get_sensor_state(sensor_id)
                if sensor_wert is not None:
                    vorschlaege.append(Vorschlag(
                        wert=round(sensor_wert, 2),
                        quelle=VorschlagQuelle.HA_SENSOR,
                        konfidenz=70,
                        beschreibung="Aktueller HA-Sensor-Wert (Momentanpreis, kein Monatsmittel)",
                    ))
        elif feld == "kraftstoffpreis_euro":
            # Vorschlag aus TagesZusammenfassung-Durchschnitt
            from backend.services.kraftstoff_preis_service import get_monatsdurchschnitt
            avg_preis = await get_monatsdurchschnitt(anlage_id, jahr, monat, db)
            if avg_preis is not None:
                vorschlaege.insert(0, Vorschlag(
                    wert=avg_preis,
                    quelle=VorschlagQuelle.BERECHNUNG,
                    konfidenz=85,
                    beschreibung="Monatsdurchschnitt aus EU Weekly Oil Bulletin",
                ))

        # Warnungen prüfen (nur wenn Wert vorhanden)
        warnungen = []
        if aktueller_wert is not None:
            warnungen = await vorschlag_service.pruefe_plausibilitaet(
                anlage_id, feld, aktueller_wert, jahr, monat
            )

        basis_felder.append(FeldStatus(
            feld=feld,
            label=feld_config["label"],
            einheit=feld_config["einheit"],
            aktueller_wert=aktueller_wert,
            quelle=quelle,
            vorschlaege=[_vorschlag_to_response(v) for v in vorschlaege],
            warnungen=[_warnung_to_response(w) for w in warnungen],
            strategie=strategie,
            sensor_id=sensor_id,
            gruppe=feld_config.get("gruppe"),
            geprueft_gegen=basis_geprueft.get(feld),
        ))

    # Zählerstände zum Monatsende (#377). **Ein eigener Weg, und zwar mit
    # Absicht:** Jeder andere Vorschlag oben ist eine MENGE — eine
    # Zählerdifferenz, ein Monatsverbrauch. Der Zählerstand ist ein STAND, und
    # `ist_zaehler_differenz_feld` liefert für ihn bewusst `False`: würde er
    # denselben Pfad nehmen, käme `MAX − MIN` heraus, also der **Verbrauch des
    # Monats** — genau die Zahl, die der Anwender hier NICHT eintragen soll.
    # Vorgeschlagen wird deshalb der letzte mitgeschriebene Stand des Monats.
    zaehler_ende: dict[int, float] = {}
    try:
        _letzter_tag = monthrange(jahr, monat)[1]
        for _zf in await lade_zaehlerstaende(
            db, anlage_id,
            datetime(jahr, monat, 1),
            datetime(jahr, monat, _letzter_tag, 23, 59, 59),
            mit_verlauf=False, nur_aktive=False,
        ):
            if _zf.stand_ende is not None:
                zaehler_ende[_zf.investition_id] = _zf.stand_ende
    except Exception:  # pragma: no cover - Vorschläge dürfen nie die Seite kippen
        logger.exception("Zählerstände für den Monatsabschluss nicht ladbar")

    # Investitionen aufbereiten
    investitionen_status: list[InvestitionStatus] = []
    for inv in anlage.investitionen:
        # InvestitionMonatsdaten laden
        imd_result = await db.execute(
            select(InvestitionMonatsdaten)
            .where(and_(
                InvestitionMonatsdaten.investition_id == inv.id,
                InvestitionMonatsdaten.jahr == jahr,
                InvestitionMonatsdaten.monat == monat,
            ))
        )
        imd = imd_result.scalar_one_or_none()
        verbrauch_daten = imd.verbrauch_daten if imd else {}
        # PN 90128: bewusst behaltene Abweichungen dieser Investition.
        inv_geprueft = (getattr(imd, "geprueft_gegen", None) or {}) if imd else {}

        # Mapping für diese Investition - beachte die verschachtelte Struktur {"felder": {...}}
        inv_mapping_raw = inv_mappings.get(str(inv.id), {})
        inv_mapping = inv_mapping_raw.get("felder", inv_mapping_raw) if isinstance(inv_mapping_raw, dict) else {}

        # R1 (SOLL Wärme/Klima §3.2a): **erweiterte** Felder erscheinen hier nur,
        # wenn es sie an diesem Gerät belegbar gibt — *„was ein Gerät liefern
        # kann, sagt der zugeordnete Zähler, nicht seine Bauart."* Belegt heißt:
        # ein gepflegter Wert in diesem Monat **oder** eine Zuordnung.
        #
        # ⚠ **Beides, nicht nur eines.** Nur die Zuordnung zu prüfen verlöre den
        # Anwender, der seinen Kühlwert von Hand einträgt; nur den Wert zu prüfen
        # verlöre den ersten Monat einer frischen Zuordnung — dann stünde das
        # Feld genau in dem Moment nicht da, in dem es gebraucht wird.
        #
        # ⚠ **Die IMD-Zeile wird deshalb VOR der Feldliste geladen.** Bis zum
        # 26.08.2026 stand die Feldliste oben und die Zeile darunter; die
        # Reihenfolge trug keine Absicht, nur Gewohnheit.
        belegte_felder = {
            basis_feld_key(k) for k, v in (verbrauch_daten or {}).items()
            if v is not None
        } | {basis_feld_key(k) for k in inv_mapping}

        # Felder für diese Investition auflösen (Bedingungen berücksichtigen)
        felder_config = get_felder_fuer_investition(
            inv.typ, inv.parameter,
            anlage_investitionen=anlage.investitionen,
            belegte_felder=belegte_felder,
        )
        if not felder_config:
            continue

        felder: list[FeldStatus] = []
        for feld_config in felder_config:
            feld = feld_config["feld"]
            aktueller_wert = verbrauch_daten.get(feld)

            # Mapping-Info
            feld_mapping = inv_mapping.get(feld, {})
            strategie = feld_mapping.get("strategie") if feld_mapping else None
            sensor_id = feld_mapping.get("sensor_id") if feld_mapping else None

            # Vorschläge holen (historische Daten)
            vorschlaege = await vorschlag_service.get_vorschlaege(
                anlage_id, feld, jahr, monat, investition_id=inv.id
            )

            # Bei konfiguriertem Sensor: HA Statistics Wert als Vorschlag hinzufügen.
            # Nur für Zählerfelder — der Wert ist eine Zählerdifferenz
            # (MAX−MIN), bei einem Preis-Feld also die Monats-Spreizung. Ohne
            # den Filter stand die mit Konfidenz 92 ÜBER dem korrekt
            # gerechneten Vorschlag (s. `ist_zaehler_differenz_feld`).
            if (
                strategie == "sensor" and sensor_id and sensor_id in ha_stats_werte
                and ist_zaehler_differenz_feld(feld)
            ):
                stats_wert = ha_stats_werte[sensor_id]
                if stats_wert > 0:
                    vorschlaege.insert(0, Vorschlag(
                        wert=round(stats_wert, 1),
                        quelle=VorschlagQuelle.HA_STATISTICS,
                        konfidenz=92,
                        beschreibung="Aus HA-Statistik (Recorder-DB)",
                    ))

            # Zählerstand (#377) — der mitgeschriebene Stand, keine Differenz.
            # Er steht ganz vorn: für dieses Feld gibt es keinen zweiten Weg,
            # und ein Vormonats-/Durchschnittswert wäre hier sogar schädlich
            # (der Stand eines Gaszählers hat keinen Mittelwert).
            if feld == ZAEHLERSTAND_FELD and inv.id in zaehler_ende:
                vorschlaege.insert(0, Vorschlag(
                    wert=zaehler_ende[inv.id],
                    quelle=VorschlagQuelle.ZAEHLERSTAND,
                    konfidenz=95,
                    beschreibung="Mitgeschriebener Stand am Monatsende",
                ))

            # Connector-Vorschlag einfügen — bei mehreren Modulen/Speichern ist
            # der Wert der ZERLEGTE Anlagen-Gesamtwert und wird als solcher
            # beschriftet (A3/a2: keine Anzeige behauptet, gemessen zu sein).
            inv_conn_values = connector_inv_verteilung.get(inv.id, {})
            if feld in inv_conn_values:
                conn_wert = inv_conn_values[feld]
                if conn_wert > 0:
                    verteilt_hinweis = connector_inv_verteilt_hinweis.get(inv.id, {}).get(feld)
                    vorschlaege.insert(0, Vorschlag(
                        wert=round(conn_wert, 1),
                        quelle=VorschlagQuelle.LOCAL_CONNECTOR,
                        konfidenz=(
                            KONFIDENZ_CONNECTOR_VERTEILT if verteilt_hinweis
                            else KONFIDENZ_CONNECTOR_GEMESSEN
                        ),
                        beschreibung=(
                            f"Vom Wechselrichter — Gesamtwert, {verteilt_hinweis}"
                            if verteilt_hinweis
                            else "Vom Wechselrichter (Zählerstand-Differenz)"
                        ),
                        # #352: der Client meldet die Marke beim Speichern
                        # zurück, damit der zerlegte Wert in der Provenance
                        # nicht als Gerätemessung landet.
                        abgeleitet=(
                            _abgeleitet_marke(feld) if verteilt_hinweis else None
                        ),
                    ))

            # MQTT Inbound-Vorschlag einfügen (Konfidenz 91)
            mqtt_inv_values = mqtt_inv_energy.get(inv.id, {})
            if feld in mqtt_inv_values:
                vorschlaege.insert(0, Vorschlag(
                    wert=mqtt_inv_values[feld],
                    quelle=VorschlagQuelle.MQTT_INBOUND,
                    konfidenz=91,
                    beschreibung="Aus MQTT-Zählerständen (Differenz über den Monat)",
                ))

            # Warnungen prüfen
            warnungen = []
            if aktueller_wert is not None:
                warnungen = await vorschlag_service.pruefe_plausibilitaet(
                    anlage_id, feld, aktueller_wert, jahr, monat, inv.id
                )

            felder.append(FeldStatus(
                feld=feld,
                label=feld_config["label"],
                # #377: Die Einheit kann am GERÄT hängen (Zählerstand: m³/l/…)
                # statt am Feld. Ein Leser für alle (S5) — sonst stünde im
                # Monatsformular nichts neben der Zahl.
                einheit=einheit_fuer(feld, inv),
                aktueller_wert=aktueller_wert,
                quelle=(datenquelle or "manuell") if aktueller_wert is not None else None,
                vorschlaege=[_vorschlag_to_response(v) for v in vorschlaege],
                warnungen=[_warnung_to_response(w) for w in warnungen],
                strategie=strategie,
                sensor_id=sensor_id,
                geprueft_gegen=inv_geprueft.get(feld),
            ))

        # sonstige_positionen aus verbrauch_daten lesen (für alle Typen)
        inv_sonstige_pos = []
        if verbrauch_daten and isinstance(verbrauch_daten.get("sonstige_positionen"), list):
            inv_sonstige_pos = verbrauch_daten["sonstige_positionen"]

        # Kategorie nur für Typ "sonstiges" relevant
        inv_kategorie = (inv.parameter or {}).get("kategorie") if inv.typ == "sonstiges" else None

        investitionen_status.append(InvestitionStatus(
            id=inv.id,
            typ=inv.typ,
            bezeichnung=inv.bezeichnung,
            felder=felder,
            kategorie=inv_kategorie,
            sonstige_positionen=inv_sonstige_pos,
        ))

    # Optionale Felder aufbereiten (manuelle Eingaben, nicht aus HA)
    optionale_felder: list[FeldStatus] = []
    for feld_config in OPTIONALE_FELDER:
        feld = feld_config["feld"]
        feld_typ = feld_config.get("typ", "number")

        if feld_typ == "text":
            aktueller_text = getattr(monatsdaten, feld, None) if monatsdaten else None
            optionale_felder.append(FeldStatus(
                feld=feld,
                label=feld_config["label"],
                einheit=feld_config["einheit"],
                aktueller_text=aktueller_text,
                quelle="manuell" if aktueller_text else None,
                typ="text",
            ))
        else:
            aktueller_wert = getattr(monatsdaten, feld, None) if monatsdaten else None
            optionale_felder.append(FeldStatus(
                feld=feld,
                label=feld_config["label"],
                einheit=feld_config["einheit"],
                aktueller_wert=aktueller_wert,
                quelle="manuell" if aktueller_wert is not None else None,
                typ="number",
            ))

    return MonatsabschlussResponse(
        anlage_id=anlage_id,
        anlage_name=anlage.anlagenname,
        jahr=jahr,
        monat=monat,
        ist_abgeschlossen=monatsdaten is not None,
        ha_mapping_konfiguriert=bool(sensor_mapping),
        connector_konfiguriert=connector_konfiguriert,
        cloud_import_konfiguriert=cloud_import_konfiguriert,
        mqtt_inbound_konfiguriert=bool(mqtt_energy or mqtt_inv_energy),
        portal_import_vorhanden=datenquelle == "portal_import",
        datenquelle=datenquelle,
        basis_felder=basis_felder,
        optionale_felder=optionale_felder,
        investitionen=investitionen_status,
    )


@router.get("/naechster/{anlage_id}", response_model=Optional[NaechsterMonatResponse])
async def get_naechster_monat(
    anlage_id: int,
    db: AsyncSession = Depends(get_db),
):
    """
    Findet den frühesten offenen (fehlenden/unvollständigen) Monat.

    Deckungsgleich mit der Frontend-Ableitung (`lib/monatsLuecken.ts`): derselbe
    Bereich [Anschaffungs-Anker … Vormonat(heute)], dieselbe Lücken-Logik — damit
    Status-Fusszeile und Monatsdaten-Block NICHT auseinanderdriften (§7 „eine
    Quelle"). Der frühere naive „letzter Monat + 1"-Sprung war blind für
    Binnen-Lücken (R20-2, [[feedback_aggregations_drift]]).

    Rückgabe: der früheste offene Monat, oder ``None`` bei lückenlosem Bereich.
    """
    from backend.core.monats_luecken import naechster_offener_monat_fuer
    from backend.core.berechnungen.spez_ertrag import PV_ERZEUGER_TYPEN

    # Anlage inkl. Investitionen laden — die Erzeuger stellen den Fallback-Anker,
    # wenn die Anlage kein Installationsdatum trägt (N-243).
    result = await db.execute(
        select(Anlage)
        .where(Anlage.id == anlage_id)
        .options(selectinload(Anlage.investitionen))
    )
    anlage = result.scalar_one_or_none()
    if not anlage:
        raise not_found("Anlage")

    # Vorhandene Monate = alle Monatsdaten-Zeilen (jahr, monat). Entspricht dem,
    # was das Frontend aus `listAggregiert` als `vorhandene` sieht.
    md_result = await db.execute(
        select(Monatsdaten.jahr, Monatsdaten.monat)
        .where(Monatsdaten.anlage_id == anlage_id)
    )
    vorhandene: set[tuple[int, int]] = {(jahr, monat) for jahr, monat in md_result.all()}

    offen = naechster_offener_monat_fuer(
        vorhandene=vorhandene,
        erzeuger_anschaffungsdaten=[
            inv.anschaffungsdatum for inv in anlage.investitionen
            if inv.typ in PV_ERZEUGER_TYPEN
        ],
        anlage_installationsdatum=anlage.installationsdatum,
        heute=date.today(),
    )
    if offen is None:
        return None

    naechster_jahr, naechster_monat = offen
    sensor_mapping = anlage.sensor_mapping or {}

    return NaechsterMonatResponse(
        anlage_id=anlage_id,
        anlage_name=anlage.anlagenname,
        jahr=naechster_jahr,
        monat=naechster_monat,
        monat_name=MONAT_NAMEN[naechster_monat],
        ha_mapping_konfiguriert=bool(sensor_mapping),
    )


@router.get("/historie/{anlage_id}")
async def get_monatsabschluss_historie(
    anlage_id: int,
    limit: int = 12,
    db: AsyncSession = Depends(get_db),
):
    """
    Gibt Historie der letzten Monatsabschlüsse zurück.

    Returns:
        Liste der letzten {limit} Monatsdaten
    """
    result = await db.execute(
        select(Monatsdaten)
        .where(Monatsdaten.anlage_id == anlage_id)
        .order_by(Monatsdaten.jahr.desc(), Monatsdaten.monat.desc())
        .limit(limit)
    )
    monatsdaten = result.scalars().all()

    return [
        {
            "id": md.id,
            "jahr": md.jahr,
            "monat": md.monat,
            "monat_name": MONAT_NAMEN[md.monat],
            "einspeisung_kwh": md.einspeisung_kwh,
            "netzbezug_kwh": md.netzbezug_kwh,
        }
        for md in monatsdaten
    ]
