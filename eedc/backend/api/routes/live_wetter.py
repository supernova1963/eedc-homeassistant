"""
Live Wetter Router — Aktuelles Wetter + PV-Prognose + Verbrauchsprofil.

Ausgelagert aus live_dashboard.py (Router-Split).
GET /api/live/{anlage_id}/wetter
"""

import asyncio
import logging
import random
from datetime import datetime, date, timedelta
from zoneinfo import ZoneInfo
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.exceptions import not_found
from backend.api.deps import get_db
from backend.core.config import settings
from backend.core.berechnungen.energie import summe_pv_bkw_kwh
from backend.core.berechnungen.heizgradtage import wp_strom_skaliert, wp_tagesfaktor
from backend.models.anlage import Anlage
from backend.models.investition import Investition
from backend.utils.investition_filter import aktiv_jetzt
from backend.models.tages_energie_profil import TagesZusammenfassung
from backend.services.live_power_service import get_live_power_service
from backend.services.wetter.utils import (
    wetter_symbol_aus_tag,
)
from backend.services.wetter.cache import (
    _cache_get, _cache_set, _error_cache_check, _error_cache_set,
    ERROR_TTL_RATE_LIMIT, ERROR_TTL_SERVER_ERROR, ERROR_TTL_NETWORK,
)
from backend.services.wetter.models import WETTER_MODELLE
from backend.services.pv_orientation import DEFAULT_SYSTEM_LOSSES
from backend.services.provenance import (
    seed_provenance,
    write_with_provenance,
)
from backend.api.routes.live_wetter_antwort import (
    _QuellenStand,
    _aktuelle_stunde,
    _antwort,
    _gti_werte,
    _ha_aussentemperatur,
    _kanon_zahlen,
    _mqtt_aussentemperatur,
    _persistenz_auftrag,
    _pq_nach_abruf,
    _prognose_quelle_tage,
    _pv_prognose_aktiv,
    _pv_stundenprofil,
    _rest_der_quelle,
    _sfml_quelle,
    _solcast_quelle,
    _sonnenstunden,
    _teilsumme_hinweis,
    _wetter_stunden,
)


# Prognose-Schreib-Pfad ist heute ein gemeinsamer Schreiber für drei
# disjunkte Quellen (OpenMeteo / Tom-HA-SFML / Solcast). Eigene Source-
# Labels statt eines Sammeleintrags — Vorgriff auf die Quellenwahl-Roadmap,
# damit ein späterer dedizierter SFML-Connector unter dem gleichen Vokabular
# weiterläuft (Konzept Risiko #3).
_OPENMETEO_SOURCE = "external:openmeteo"
_OPENMETEO_WRITER = "openmeteo_prognose"
_SFML_SOURCE = "external:tom_ha_sfml"
_SFML_WRITER = "tom_ha_sfml_sensor"
_SOLCAST_SOURCE = "external:solcast"
_SOLCAST_WRITER = "solcast_provider"


# Liste der ``TagesZusammenfassung``-Felder, die ``_speichere_prognose``
# (Day-Ahead-Forecast-Schreiber) befüllt. Muss in Sync gehalten werden mit
# den Inline-Schreibungen in der Funktion unten — sie ist Anker für den
# Konformitäts-Test K1 (test_konformitaet_prognose_felder.py), der diese
# Liste unabhängig mit `_PROGNOSE_FELDER_RETTEN` im Aggregator vergleicht.
# Drift in einer der beiden Stellen bricht den Test (Vorfall v3.31.7:
# `_PROGNOSE_FELDER_RETTEN` fehlte `pv_prognose_stundenprofil`, Korrekturprofil-
# Heatmap blieb dauerhaft leer). Die frühere dritte Liste im Backfill ist mit
# v3.34.2 Phase B entfallen (Backfill schreibt nicht mehr eigenständig in TZ).
_TZ_SCHREIBFELDER_PROGNOSE: tuple[str, ...] = (
    "pv_prognose_kwh",
    "pv_prognose_final_kwh",
    "pv_prognose_final_at",
    "sfml_prognose_kwh",
    "solcast_prognose_kwh",
    "solcast_p10_kwh",
    "solcast_p90_kwh",
    "pv_prognose_stundenprofil",
    "solcast_prognose_stundenprofil",
    "sfml_prognose_stundenprofil",
    # N-547: das Lern-SOLL (rohe, gekappte, UNkorrigierte OM-Reihe + ihre
    # Tagessumme). ⛔ Beide MÜSSEN in `_PROGNOSE_FELDER_RETTEN` mitgeführt
    # werden — `aggregate_day` legt die TZ-Zeile alle 15 Minuten neu an
    # (`energie_profil_heute_job`), und was dort nicht gerettet wird, ist
    # binnen einer Viertelstunde weg. Genau so verlor v3.31.7 den Day-Ahead-
    # Snapshot und die Korrekturprofil-Heatmap blieb monatelang leer.
    "lern_soll_stundenprofil_kwh",
    "lern_soll_kwh",
)

logger = logging.getLogger(__name__)

router = APIRouter()

# ── Wetter Models ─────────────────────────────────────────────────────────────

class WetterStunde(BaseModel):
    """Wetterdaten für eine Stunde."""
    zeit: str  # "14:00"
    temperatur_c: Optional[float] = None
    wetter_code: Optional[int] = None
    wetter_symbol: str = "unknown"
    bewoelkung_prozent: Optional[int] = None
    niederschlag_mm: Optional[float] = None
    globalstrahlung_wm2: Optional[float] = None
    #: Einstrahlung auf die Modulebene (kWp-gewichtet über die Orientierungs-
    #: gruppen, bei eedc als Quelle × Korrekturfaktor). Stand bis N-689 nur in
    #: der Rohrückgabe — das Modell strich es (kein Leser im Frontend; es gehört
    #: hierher, damit Rohrückgabe und Antwort deckungsgleich sind).
    gti_wm2: Optional[float] = None


class PrognoseQuelleTag(BaseModel):
    """Ein Tag der GEWÄHLTEN Prognosequelle (Solcast/SFML) für die Solar-Aussicht.

    ``rueckfall="eedc"``: so weit reicht die gewählte Quelle nicht — die
    Anzeige zeigt dann die eedc-Prognose und sagt es. N-689: bis 11.10.2026
    stand die Liste nur in der Rohrückgabe; ohne dieses Modell strich FastAPI
    sie aus der Antwort, und die Kachel fiel unter der Quellen-Überschrift
    stumm auf den eedc-Kanon zurück.
    """
    datum: str  # "YYYY-MM-DD"
    kwh: Optional[float] = None
    vm_kwh: Optional[float] = None
    nm_kwh: Optional[float] = None
    rueckfall: Optional[str] = None  # "eedc" oder None
    #: N-695: ``"eedc"``, wenn die gewählte Quelle für diesen Tag kein
    #: Stundenprofil hat — VM/NM der Kachel kommen dann aus dem eedc-Kanon und
    #: addieren sich nicht zur Tageszahl der Quelle; die Anzeige sagt es.
    vm_nm_rueckfall: Optional[str] = None


class VerbrauchsStunde(BaseModel):
    """Stündliches Erzeugung/Verbrauch-Profil."""
    zeit: str  # "14:00"
    pv_ertrag_kw: float
    verbrauch_kw: float
    pv_ml_prognose_kw: Optional[float] = None  # Solar Forecast ML (optional)


class LiveWetterResponse(BaseModel):
    anlage_id: int
    verfuegbar: bool
    # Grund, WENN nicht verfügbar — damit das Frontend die richtige (nicht
    # schuld-umkehrende) Meldung zeigt: "keine_koordinaten" (echte Stammdaten-
    # Lücke) vs. "abruf_fehlgeschlagen" (Koordinaten da, OpenMeteo-Abruf/Cache
    # vorübergehend down — kein User-Fehler). None, wenn verfügbar.
    grund: Optional[str] = None
    aktuell: Optional[WetterStunde] = None
    stunden: list[WetterStunde] = []
    temperatur_min_c: Optional[float] = None
    temperatur_max_c: Optional[float] = None
    sonnenstunden: Optional[float] = None
    sonnenstunden_bisher: Optional[float] = None  # Ist-Sonnenstunden bis aktuelle Stunde
    sonnenstunden_rest: Optional[float] = None    # Prognostizierte Sonnenstunden ab aktueller Stunde
    pv_prognose_kwh: Optional[float] = None
    #: Σ der Prognose-Slots ab jetzt (laufende Stunde anteilig) — der GEMESSENE
    #: Rest, nicht die Differenz zur Tagesprognose. Pendant zu
    #: `sonnenstunden_rest` (rapahl-PN 2026-08-23).
    pv_prognose_rest_kwh: Optional[float] = None
    #: IST bisher + Rest. Ergänzt `pv_prognose_kwh`, ersetzt ihn NICHT — jener
    #: bleibt der kanonische Wert, der überall dieselbe Zahl trägt.
    pv_prognose_heute_rollend_kwh: Optional[float] = None
    #: Was heute bis jetzt tatsächlich erzeugt wurde (aus dem Tagesprofil).
    pv_ist_bisher_kwh: Optional[float] = None
    #: ADR-002 P4 (N-690): gesetzt, wenn Tageswert/PV-Kurve von heute aus einem
    #: unvollständigen Multi-String-Fan-out stammen (der Kanon hat sie nicht
    #: ersetzt). Der Wert bleibt stehen — die Antwort sagt es nur selbst.
    pv_prognose_hinweis: Optional[str] = None
    grundlast_kw: Optional[float] = None
    verbrauchsprofil: list[VerbrauchsStunde] = []
    profil_typ: str = "bdew_h0"  # "individuell_werktag", "individuell_wochenende", "bdew_h0"
    profil_quelle: Optional[str] = None  # "ha", "mqtt" — woher die History kam
    profil_tage: Optional[int] = None  # Anzahl Tage die ins individuelle Profil einflossen
    #: Wie viele der 24 Stunden tragen eine echte Stichprobe (N-48). Die Freigabe des
    #: Profils zaehlt TAGE, und ein Tag entsteht schon aus einer einzigen Stunde — die
    #: uebrigen Slots kommen aus der BDEW-Standard-Grundlast. Ohne diese Zahl liest sich
    #: `profil_tage` wie die Guete des Profils.
    profil_slots: Optional[int] = None
    prognose_quelle: Optional[str] = None  # Aktive Prognosequelle: "eedc", "solcast", "sfml"
    prognose_quelle_hinweis: Optional[str] = None  # Fallback-Hinweis wenn gewünschte Quelle nicht verfügbar
    #: Tageszahlen der gewählten Quelle (None bei eedc — dann gilt der Kanon).
    #: N-689: fehlte bis 11.10.2026 im Modell und wurde aus der Antwort gestrichen.
    prognose_quelle_tage: Optional[list[PrognoseQuelleTag]] = None
    #: Hat die gewählte Quelle ein Stundenprofil? False ⇒ kein Rest (statt eines
    #: aus fremder Kurvenform geschätzten). N-689 wie oben.
    prognose_quelle_hat_profil: Optional[bool] = None
    sfml_prognose_kwh: Optional[float] = None  # Solar Forecast ML Tagesprognose
    sfml_tomorrow_kwh: Optional[float] = None  # Solar Forecast ML Morgen-Prognose
    sfml_accuracy_pct: Optional[float] = None  # Solar Forecast ML Modellgenauigkeit
    solar_noon: Optional[str] = None  # Solar Noon als "HH:MM" (z.B. "12:27")
    sunrise: Optional[str] = None  # Sonnenaufgang als "HH:MM"
    sunset: Optional[str] = None  # Sonnenuntergang als "HH:MM"


# ── Typisches Haushaltsprofil (BDEW H0) ──────────────────────────────────────

# Normierter Stundenverbrauch eines 4000 kWh/a Haushalts (kW, Werktag Übergang)
# Quelle: BDEW Standardlastprofil H0, vereinfacht auf Stundenwerte
_LASTPROFIL_KW = {
    6: 0.25, 7: 0.45, 8: 0.55, 9: 0.40, 10: 0.35,
    11: 0.38, 12: 0.50, 13: 0.45, 14: 0.35, 15: 0.33,
    16: 0.35, 17: 0.50, 18: 0.65, 19: 0.70, 20: 0.55,
}

# DEFAULT_SYSTEM_LOSSES wird aus services/pv_orientation.py importiert.
# Der Live-Pfad nutzt bewusst den Default statt des anlagenspezifischen
# PVGIS-Werts: ein abweichender Setup-Wert wird vom Korrekturprofil-
# Lernfaktor ohnehin eingefangen — siehe Memory project_pvgis_systemverluste_drift.


TEMP_COEFFICIENT = 0.004  # -0.4%/°C über 25°C (typisch Silizium)

# Die Heizgrenze stand bis zum 12.09.2026 hier als zweite, modul-lokale Zahl.
# Sie ist dieselbe wie die des wetternormierten Vergleichs im Komponenten-Hub
# und lebt seither **einmal** im Layer (`core/berechnungen/heizgradtage.py`,
# SOLL Wärme/Klima §4.1). Gewächtert von
# `test_berechnungs_layer_konformitaet.py::test_heizgrenze_nur_im_layer`.

# Die lokale Ausrichtungs-Text→Azimut-Tabelle stand hier bis A20 als zweite
# Kopie neben `pv_orientation.AUSRICHTUNG_MAP`; ihre drei englischen Schlüssel
# (`south`/`east`/`north`) sind beim Zusammenlegen in den SoT gewandert.


def _get_pv_orientierungsgruppen(pv_module: list) -> list[dict]:
    """Orientierungsgruppen als dicts — dünner Adapter auf den Gruppen-SoT.

    Die Gruppierungs-Logik selbst steht in
    ``services/pv_orientation.orientierungs_gruppen`` (geteilt mit
    ``prognose_kanon``). Diese Funktion war bis A20 eine **zweite Kopie**
    davon und ist ihr an zwei Stellen davongelaufen (P1/P3):

    1. Sie las die Leistung als ``pv.leistung_kwp`` **direkt aus der Spalte**.
       Ein Modul, dessen kWp nur im ``parameter``-JSON gepflegt ist, hatte
       damit ``kwp = 0`` und fiel **ganz aus der Gruppierung** — die Live-Seite
       rechnete GTI-Gewichte und Gesamt-kWp ohne dieses Dach. Der SoT liest
       über ``get_pv_kwp`` (Spalte → ``parameter.kwp``).
    2. Ihre Reihenfolge war die **Einfüge-Reihenfolge der DB-Query** (kein
       ``ORDER BY``). ``gruppen[0]`` — Cache-Key und, im Ein-Gruppen-Fall,
       Tilt/Azimut des Haupt-Abrufs — konnte sich damit nach einem Neustart
       ändern. Der SoT sortiert deterministisch nach kWp (stärkste Gruppe
       zuerst).

    Rückgabe-Form (Liste von dicts) bleibt, weil ``_fetch_multi_string_gti``
    und ``services/energie_profil/_helpers`` darauf lesen.
    """
    from backend.services.pv_orientation import orientierungs_gruppen

    return [
        {"neigung": g.neigung, "ausrichtung": g.ausrichtung, "kwp": g.kwp}
        for g in orientierungs_gruppen(pv_module)
    ]


# Live-Wetter-Cache: 60 Min TTL (Open-Meteo aktualisiert stündlich, ICON-D2
# 3-stündlich).
LIVE_WETTER_CACHE_TTL = 3600

# N-701: die Open-Meteo-Felder des Live-Wetter-Abrufs — EINE Liste für den
# Direktabruf (`_lade_forecast_gecached`) und den Prefetch
# (`prefetch_service._prefetch_live_wetter`), die unter denselben Schlüssel
# schreiben. Der Prefetch führte eine eigene Kopie ohne die stündliche
# `sunshine_duration`; die Route las seinen Eintrag ohne eigenen Abruf, und
# Sonnenstunden/«bisher»/«Rest» blieben bis zu 60 min leer. Bei genau einer
# Orientierungsgruppe hängen beide `global_tilted_irradiance` an.
LIVE_WETTER_HOURLY_FELDER: tuple[str, ...] = (
    "temperature_2m", "weather_code", "cloud_cover",
    "precipitation", "shortwave_radiation", "sunshine_duration",
)
LIVE_WETTER_DAILY_FELDER: tuple[str, ...] = (
    "sunshine_duration", "temperature_2m_max", "temperature_2m_min", "sunrise", "sunset",
)


def live_wetter_cache_key(
    latitude: float, longitude: float, gruppen: list[dict], wetter_modell: str,
) -> str:
    """Cache-Key des Live-Wetters — EINE Formel für Endpoint und Prefetch.

    Der Key stand als Format-String zweimal im Repo (hier und in
    `prefetch_service._prefetch_live_wetter`), mit dem Kommentar „muss exakt
    übereinstimmen" als einziger Sicherung. Jede Key-Änderung an einer Stelle
    hätte den Prefetch stumm ins Leere wärmen lassen (N56).

    Der Key trägt die **ganze** Gruppen-Signatur, nicht nur die stärkste
    Gruppe: der Eintrag enthält bei Multi-String das über ALLE Gruppen
    kWp-gewichtete GTI. Mit nur der ersten Gruppe im Key konnten zwei Anlagen
    am selben (auf 0,01° gerundeten) Standort mit gleicher stärkster, aber
    verschiedener zweiter Dachfläche denselben Eintrag benutzen.
    """
    haupt_neigung = gruppen[0]["neigung"] if gruppen else 35
    haupt_azimut = gruppen[0]["ausrichtung"] if gruppen else 0
    signatur = ";".join(
        f"{g['neigung']}/{g['ausrichtung']}/{g['kwp']:.2f}" for g in gruppen
    )
    return (
        f"live_wetter:{latitude:.2f}:{longitude:.2f}"
        f":{haupt_neigung}:{haupt_azimut}:multi={len(gruppen) > 1}"
        f":g={signatur}:m={wetter_modell}"
    )


def _berechne_verbrauchsprofil(
    stunden: list[dict],
    kwp: float,
    jahresverbrauch_kwh: float = 4000,
    individuelles_profil: Optional[dict] = None,
    wp_profil: Optional[dict] = None,
    referenz_hdd_kd: Optional[float] = None,
    wp_ww_profil: Optional[dict] = None,
    wp_kuehlen_profil: Optional[dict] = None,
) -> tuple[list[dict], Optional[float], Optional[float], bool]:
    """
    Berechnet stündliches PV-Ertrag + Verbrauchsprofil.

    PV-Ertrag: Nutzt GTI (Global Tilted Irradiance) falls verfügbar,
    sonst Fallback auf GHI (shortwave_radiation).
    Temperaturkorrektur: -0.4%/°C über 25°C Modultemperatur.

    ``stunden`` sind die Stunden **eines** Tages — die Wärmepumpen-Korrektur
    bildet daraus ihr Tagesmittel (N-593).

    Args:
        individuelles_profil: Stundenwerte {0: kW, 1: kW, ..., 23: kW} oder None
        referenz_hdd_kd: Heizgradtage der Lernwoche des Profils (Mittel der
            Tages-Heizgradtage, ``referenz_heizgradtage``) — ``None`` ⇒ keine
            Wärmepumpen-Korrektur.
        wp_ww_profil, wp_kuehlen_profil: Warmwasser- und Kühl-Anteil des
            WP-Profils (Teilmengen, N-594) — sie bleiben bei der Korrektur fest
            (``heizgradtage.wp_strom_skaliert``). ``None`` ⇒ ganze Reihe skaliert.

    Returns:
        (profil, pv_prognose_kwh, grundlast_kw, ist_individuell)
    """
    ist_individuell = individuelles_profil is not None
    tages_faktor = jahresverbrauch_kwh / 4000  # Nur für BDEW-Fallback

    # WP-Temperaturkorrektur (N-593): EIN Faktor für den ganzen Tag — die
    # Heizgradtage seines Tagesmittels gegen die der Lernwoche
    # (`wp_tagesfaktor`). Bis 01.10.2026 bekam jede Stunde ihren eigenen
    # Faktor aus ihrer eigenen Temperatur; bei unverändertem Wetter schob das
    # den Wärmepumpen-Strom in die kalten Nachtstunden.
    wp_faktor = (
        wp_tagesfaktor(referenz_hdd_kd, [s.get("temperatur_c") for s in stunden])
        if wp_profil and referenz_hdd_kd is not None
        else 1.0
    )

    profil = []
    pv_summe_kwh = 0.0

    for s in stunden:
        h = int(s["zeit"].split(":")[0])

        # GTI bevorzugen (auf Modulebene geneigt), sonst GHI-Fallback
        strahlung = s.get("gti_wm2") or s.get("globalstrahlung_wm2") or 0

        if strahlung > 0 and kwp > 0:
            # Basis-Ertrag: Strahlung/1000 × kWp × (1 - Systemverluste)
            pv_kw = strahlung * kwp * (1 - DEFAULT_SYSTEM_LOSSES) / 1000

            # Temperaturkorrektur
            temp = s.get("temperatur_c")
            if temp is not None:
                aufheizung = min(25, strahlung / 40)  # ~25°C bei 1000 W/m²
                modul_temp = temp + aufheizung
                if modul_temp > 25:
                    pv_kw *= (1 - (modul_temp - 25) * TEMP_COEFFICIENT)

            pv_kw = round(max(0, pv_kw), 2)
        else:
            pv_kw = 0.0

        pv_summe_kwh += pv_kw  # 1h x kW = kWh

        if individuelles_profil is not None:
            # Individuelles Profil: Schlüssel sind int oder str
            verbrauch_kw = round(individuelles_profil.get(h, individuelles_profil.get(str(h), 0.3)), 2)

            # WP-Temperaturkorrektur: WP-Anteil mit dem Tagesfaktor skalieren
            # (Heizgradtage des Tagesmittels / Heizgradtage der Lernwoche,
            # N-593). Eine Stunde ohne Temperatur bleibt unkorrigiert —
            # wie vor N-593 (Vorlage §4).
            if wp_profil and referenz_hdd_kd is not None:
                temp = s.get("temperatur_c")
                if temp is not None:
                    # ⭐ Seit 21.09.2026 aus dem Layer statt hier
                    # ausgeschrieben: die Plan-Sensoren P1/P7 brauchen dieselbe
                    # Skalierung fuer die erwartete WP-Stundenreihe, und zwei
                    # Nachbauten hiessen zwei Heizstrom-Zahlen unter einem Namen.
                    wp_kw = wp_profil.get(h, wp_profil.get(str(h), 0.0))
                    haus_kw = max(0.0, verbrauch_kw - wp_kw)
                    # N-594: nur der wetterabhängige Teil (ohne gemessenes
                    # Warmwasser/Kühlen) folgt dem Tagesfaktor.
                    wp_neu = wp_strom_skaliert(
                        wp_kw, wp_faktor, referenz_hdd_kd,
                        warmwasser_kw=(wp_ww_profil or {}).get(h, (wp_ww_profil or {}).get(str(h), 0.0)) or 0.0,
                        kuehlen_kw=(wp_kuehlen_profil or {}).get(h, (wp_kuehlen_profil or {}).get(str(h), 0.0)) or 0.0,
                    )
                    verbrauch_kw = round(max(0.0, haus_kw + wp_neu), 2)
        else:
            # BDEW H0 Fallback
            verbrauch_kw = round(_LASTPROFIL_KW.get(h, 0.3) * tages_faktor, 2)

        profil.append({
            "zeit": s["zeit"],
            "pv_ertrag_kw": pv_kw,
            "verbrauch_kw": verbrauch_kw,
        })

    # Grundlast: Median der Nachtstunden (0-5 Uhr) — kein PV das die Bilanz verfälscht,
    # Median ist robust gegen einzelne Ausreißer/Messfehler
    nacht_verbrauch = sorted([
        p["verbrauch_kw"] for p in profil
        if int(p["zeit"].split(":")[0]) <= 5 and p["verbrauch_kw"] > 0
    ])
    if nacht_verbrauch:
        mid = len(nacht_verbrauch) // 2
        grundlast = round(
            nacht_verbrauch[mid] if len(nacht_verbrauch) % 2
            else (nacht_verbrauch[mid - 1] + nacht_verbrauch[mid]) / 2,
            2,
        )
    else:
        grundlast = None

    return profil, round(pv_summe_kwh, 1) if pv_summe_kwh > 0 else None, grundlast, ist_individuell


# ── Wetter Demo-Daten ─────────────────────────────────────────────────────────

def _generate_demo_wetter(kwp: float = 10.0) -> dict:
    """Simuliertes Wetter für Demo-Modus."""
    now = datetime.now(ZoneInfo("Europe/Berlin"))
    alle_stunden = []  # 0-23 für Verbrauchsprofil
    stunden = []       # 6-20 für Wetter-Timeline

    for h in range(24):
        strahlung = max(0, 800 * max(0, 1 - ((h - 13) / 5) ** 2))
        strahlung *= (0.85 + random.uniform(0, 0.3))

        temp = 8 + 10 * max(0, 1 - ((h - 15) / 7) ** 2)
        temp += random.uniform(-1, 1)

        bewoelkung = max(0, min(100, int(100 - strahlung / 10 + random.randint(-10, 20))))

        if bewoelkung < 25:
            code = 0
        elif bewoelkung < 60:
            code = random.choice([1, 2])
        else:
            code = random.choice([2, 3, 61])

        niederschlag = round(random.uniform(0, 0.5), 1) if code >= 61 else 0.0

        # GTI simulieren: ~10% mehr als GHI bei optimaler Südausrichtung 35°
        gti = round(strahlung * 1.1, 0) if strahlung > 0 else 0

        stunde = {
            "zeit": f"{h:02d}:00",
            "temperatur_c": round(temp, 1),
            "wetter_code": code,
            "wetter_symbol": wetter_symbol_aus_tag(
                code, bewoelkung, niederschlag,
                niederschlag_threshold_mm=0.05,
            ),
            "bewoelkung_prozent": bewoelkung,
            "niederschlag_mm": niederschlag,
            "globalstrahlung_wm2": round(strahlung, 0),
            "gti_wm2": gti,
        }
        alle_stunden.append(stunde)
        if 6 <= h <= 20:
            stunden.append(stunde)

    aktuelle_stunde = None
    for s in alle_stunden:
        h = int(s["zeit"].split(":")[0])
        if h <= now.hour:
            aktuelle_stunde = s

    temps = [s["temperatur_c"] for s in stunden]

    # Simuliertes individuelles Profil — Gesamtverbrauch inkl. WP, Wallbox, Haushalt
    # (In Realität berechnet aus: PV + Netzbezug - Einspeisung über 14 Tage)
    ist_wochenende = now.weekday() >= 5
    demo_profil = {
        # Wochenende: später aufstehen, WP morgens/abends, mittags kochen, kein Wallbox
        0: 0.55, 1: 0.45, 2: 0.40, 3: 0.40, 4: 0.40, 5: 0.50,
        6: 1.80, 7: 2.20, 8: 2.50, 9: 1.40, 10: 0.90,
        11: 1.10, 12: 1.80, 13: 1.20, 14: 0.80, 15: 0.75,
        16: 0.85, 17: 2.30, 18: 2.80, 19: 2.50, 20: 1.20,
        21: 0.80, 22: 0.60, 23: 0.55,
    } if ist_wochenende else {
        # Werktag: WP-Spitzen 6-8 + 17-19, Wallbox 15-17, Haushalt-Grundlast
        0: 0.50, 1: 0.40, 2: 0.35, 3: 0.35, 4: 0.35, 5: 0.45,
        6: 2.10, 7: 2.80, 8: 1.60, 9: 0.70, 10: 0.55,
        11: 0.60, 12: 0.90, 13: 0.70, 14: 0.55, 15: 4.20,
        16: 4.50, 17: 2.80, 18: 2.90, 19: 2.60, 20: 1.30,
        21: 0.85, 22: 0.60, 23: 0.50,
    }

    profil, pv_prognose, grundlast, _ = _berechne_verbrauchsprofil(
        alle_stunden, kwp, individuelles_profil=demo_profil,
    )

    return {
        "anlage_id": 0,
        "verfuegbar": True,
        "aktuell": aktuelle_stunde,
        "stunden": stunden,
        "temperatur_min_c": round(min(temps), 1),
        "temperatur_max_c": round(max(temps), 1),
        "sonnenstunden": round(sum(1 for s in stunden if (s["globalstrahlung_wm2"] or 0) > 120) * 0.9, 1),
        "pv_prognose_kwh": pv_prognose,
        "grundlast_kw": grundlast,
        "verbrauchsprofil": profil,
        "profil_typ": "individuell_wochenende" if ist_wochenende else "individuell_werktag",
        "profil_quelle": "demo",
        "profil_tage": 14,
        "profil_slots": 24,
    }


# ── Multi-String GTI-Fetch ────────────────────────────────────────────────────

async def _fetch_gti_for_gruppe(
    client: httpx.AsyncClient,
    latitude: float,
    longitude: float,
    neigung: int,
    ausrichtung: int,
) -> Optional[list]:
    """
    Holt stündliche GTI-Werte für eine Orientierungsgruppe von Open-Meteo.

    Returns:
        Liste mit 24 stündlichen GTI-Werten (W/m²) oder None bei Fehler.
    """
    params = {
        "latitude": latitude,
        "longitude": longitude,
        "hourly": "global_tilted_irradiance",
        "timezone": "Europe/Berlin",
        "forecast_days": 1,
        "tilt": neigung,
        "azimuth": ausrichtung,
    }
    try:
        resp = await client.get(
            f"{settings.open_meteo_api_url}/forecast", params=params
        )
        resp.raise_for_status()
        data = resp.json()
        return data.get("hourly", {}).get("global_tilted_irradiance", [])
    except Exception as e:
        logger.warning(f"GTI-Fetch Neigung={neigung}° Azimut={ausrichtung}°: {type(e).__name__}: {e}")
        return None


async def _fetch_multi_string_gti(
    latitude: float,
    longitude: float,
    gruppen: list[dict],
) -> tuple[list, bool]:
    """
    Berechnet gewichtete GTI-Werte für mehrere Orientierungsgruppen.

    Bei nur einer Gruppe: Einzelner API-Call (in den Haupt-Request integriert).
    Bei mehreren Gruppen: Parallele API-Calls, kWp-gewichtete Kombination.

    Returns:
        (kombiniert, vollstaendig):
        - kombiniert: Liste mit 24 kombinierten GTI-Werten (W/m²).
        - vollstaendig: False, wenn mindestens eine Orientierungsgruppe keinen
          GTI lieferte (transienter OM-Aussetzer pro parallelem /forecast-Call).
          In dem Fall fehlt das kWp-Gewicht der gescheiterten Gruppe in
          `kombiniert` → ein gegen GT·kwp_gesamt gerechneter Tageswert
          kollabiert auf die Solo-Produktion der Überlebenden (#306). Das Flag
          erlaubt dem Aufrufer, einen solchen Wert nicht als Tagesprognose
          einzufrieren („Diagnose statt stillem Cap").
    """
    kwp_gesamt = sum(g["kwp"] for g in gruppen)
    if kwp_gesamt <= 0:
        return [], True

    async with httpx.AsyncClient(timeout=15.0) as client:
        tasks = [
            _fetch_gti_for_gruppe(client, latitude, longitude, g["neigung"], g["ausrichtung"])
            for g in gruppen
        ]
        ergebnisse = await asyncio.gather(*tasks)

    # kWp-gewichtete Kombination der GTI-Werte
    n_stunden = 24
    kombiniert = [0.0] * n_stunden
    vollstaendig = True

    for gruppe, gti_values in zip(gruppen, ergebnisse):
        if not gti_values:
            vollstaendig = False
            continue
        gewicht = gruppe["kwp"] / kwp_gesamt
        for i in range(min(n_stunden, len(gti_values))):
            val = gti_values[i]
            if val is not None:
                kombiniert[i] += val * gewicht

    if not vollstaendig:
        logger.warning(
            "Multi-String-GTI unvollständig: nicht alle %d Orientierungsgruppen "
            "geliefert — kombinierter GTI ist untergewichtet (#306)",
            len(gruppen),
        )

    return kombiniert, vollstaendig


# ── Prognose-Quellen Registry ────────────────────────────────────────────────

PROGNOSE_QUELLEN = {
    "openmeteo": {
        "label": "Open-Meteo",
        "db_feld": "pv_prognose_kwh",
        "braucht_lernfaktor": True,
        "standalone": True,
    },
    "solcast": {
        "label": "Solcast",
        "db_feld": "solcast_prognose_kwh",
        "braucht_lernfaktor": True,
        "standalone": False,
    },
    # "sfml": {
    #     "label": "Solar Forecast ML",
    #     "db_feld": "sfml_prognose_kwh",
    #     "braucht_lernfaktor": False,  # ML-Modell kalibriert sich selbst
    #     "standalone": False,
    # },
}

# ── Lernfaktor (MOS-basiert, saisonale Kaskade) ─────────────────────────────

from dataclasses import dataclass


@dataclass
class LernfaktorResult:
    """Ergebnis der Lernfaktor-Berechnung mit Metadaten."""
    faktor: Optional[float]
    stufe: Optional[str] = None   # "saisonal", "quartal", "gesamt"
    label: Optional[str] = None   # z.B. "saisonal April (23 Tage)"
    tage_count: int = 0
    quelle: Optional[str] = None  # "openmeteo", "solcast"
    # O1 (Recency) + O2 (Trim-Mean) als Doppel-Variante neben Legacy.
    # Live-Pfad nutzt weiterhin `faktor`; faktor_o12 läuft parallel zu Diagnose-
    # Zwecken im Prognosen-Tab. Aktivierung als neuer Default erst nach mehrwöchiger
    # Beobachtung — siehe docs/archive/KONZEPT-KORREKTURPROFIL.md.
    faktor_o12: Optional[float] = None
    delta_o12_pct: Optional[float] = None  # 100 * (o12 - legacy) / legacy
    #: ⭐ **Der zweite Faktor — derselbe Lernstoff, andere Basis** (N-551).
    #:
    #: `faktor` steht auf der **rohen** Tagesprognose (`pv_prognose_kwh`, W1:
    #: ungekappt, unkorrigiert). Wer ihn auf eine **gekappte** Reihe anwendet —
    #: der Kanon-Fallback tut das (`prognose_kanon.py`, `korrigiere_tagesprofil`
    #: auf den bereits an der AC-Grenze gekappten Slots) —, rechnet die
    #: Abregelung ein zweites Mal heraus: an einer r28-Messkopie mit 12-kW-Grenze
    #: 0,809 statt 0,923 (**−12,4 %**).
    #:
    #: ⛔ **Ein Nenner-Tausch wäre die falsche Antwort gewesen.** Denselben Faktor
    #: lesen fünf Stellen auf der **rohen** Basis (`prognosen.py`,
    #: `prognose_genauigkeit_service`, `energie_profil/tag.py`,
    #: `energie_profil/prognose.py`, der Kanon-Schätzpfad) — mit dem gekappten
    #: Nenner lägen die um **+14,2 %** zu hoch. Deshalb **zwei** Faktoren, je
    #: Basis einer; jeder aus seinem eigenen, reinen Tage-Pool.
    #:
    #: `None`, solange weniger als `_MIN_TAGE_GEKAPPT` Tage ein `lern_soll_kwh`
    #: tragen — dann nimmt der Kanon-Fallback weiter den Roh-Faktor.
    faktor_gekappt: Optional[float] = None
    tage_count_gekappt: int = 0


_MONAT_NAMEN = {
    1: "Januar", 2: "Februar", 3: "März", 4: "April",
    5: "Mai", 6: "Juni", 7: "Juli", 8: "August",
    9: "September", 10: "Oktober", 11: "November", 12: "Dezember",
}

# Cache-Key: (anlage_id, quelle) → (datum_str, LernfaktorResult)
_lernfaktor_cache: dict[tuple[int, str], tuple[str, LernfaktorResult]] = {}


def _quartal_fuer_monat(monat: int) -> tuple[int, list[int]]:
    """Returns (quarter_number, [months_in_quarter])."""
    q = (monat - 1) // 3 + 1
    monate = list(range((q - 1) * 3 + 1, q * 3 + 1))
    return q, monate


def _filtere_tage(tage: list, db_feld: str, ist_je_tag: Optional[dict] = None) -> list[tuple[date, float, float]]:
    """
    Filtert Tage mit gültigem Prognose- und IST-Wert.

    ``ist_je_tag`` (HA-Bauform S5, §3 (A) 11–15): das PV-IST je Tag aus ``kanal_stunden.pv_ist_je_tag`` — an einem
    Kanal-Tag aus ``kanal_tage``; ohne die Abbildung (reine Aufrufer, Proben) aus ``komponenten_kwh`` der Zeile.

    Returns: Liste von (datum, ist_kwh, prognose_kwh).
    Tage mit Prognose ≤ 0.5 kWh oder IST ≤ 0.5 kWh werden ausgeschlossen
    (Nacht/Schlechtwetter ohne Aussagekraft, Sensor-Lücken).

    IST = PV-Tages-Σ über den SoT-Helper `summe_pv_bkw_kwh` (Whitelist
    `pv_`/`bkw_`). Vor 2026-05-21 summierte diese Funktion `komponenten_kwh`
    über eine 3-Element-Blacklist — dadurch zählten Batterie-, WP-, Wallbox-
    und `sonstige_`-Keys als PV-Erzeugung mit, der Lernfaktor wurde
    systematisch zu hoch (Rainer-PN). Siehe core/berechnungen/energie.py.
    """
    out: list[tuple[date, float, float]] = []
    for tag in tage:
        prognose = getattr(tag, db_feld, None)
        if not prognose or prognose <= 0.5:
            continue
        ist_kwh = summe_pv_bkw_kwh(tag.komponenten_kwh) if ist_je_tag is None else ist_je_tag.get(tag.datum)
        if ist_kwh is not None and ist_kwh > 0.5:
            out.append((tag.datum, float(ist_kwh), float(prognose)))
    return out


def _aggregiere_legacy(
    daten: list[tuple[date, float, float]],
) -> tuple[Optional[float], int]:
    """
    Legacy-Aggregator: Σ(IST) / Σ(Prognose), produktionsgewichtet.

    Returns (raw_faktor, count). raw_faktor ist ungeklemmt; Caller
    entscheidet über Clamp [0.5; 1.3] und Rundung.
    """
    if not daten:
        return None, 0
    sum_ist = sum(d[1] for d in daten)
    sum_prog = sum(d[2] for d in daten)
    if sum_prog < 1:
        return None, len(daten)
    return sum_ist / sum_prog, len(daten)


# O1+O2 Parameter — siehe docs/archive/KONZEPT-KORREKTURPROFIL.md
#: Gate des **gekappten** Faktors (N-551) — dieselbe Zahl wie die letzte Stufe
#: der Kaskade oben („gesamt", ≥ 7 Tage). Weniger Tage heißt: kein zweiter
#: Faktor, der Kanon-Fallback bleibt beim Roh-Faktor.
_MIN_TAGE_GEKAPPT = 7

_O1_RECENCY_DAYS = 30      # Tage jünger als N erhalten Recency-Boost
_O1_RECENCY_BOOST = 1.30   # +30 % Gewicht für junge Tage
_O2_TRIM_PCT = 0.10        # 10 % oberste/unterste Tage werden verworfen


def _aggregiere_o12(
    daten: list[tuple[date, float, float]],
    heute: date,
) -> tuple[Optional[float], int]:
    """
    O1+O2-Aggregator: Trim-Mean (O2) + Recency-Boost (O1) kombiniert.

    1. Pro Tag Quotient q_d = IST/Prognose und Gewicht w_d = Prognose × Recency
       (Recency = 1.30 wenn Tag jünger als 30 Tage, sonst 1.0)
    2. Sortiere nach q_d, trimme oberste/unterste 10 %
    3. Gewichteter Mittelwert über getrimmte Tage

    Trim-Mean entfernt Sensor-Aussetzer / Snapshot-Lücken; Recency lässt
    schleichende Veränderungen (Verschmutzung, Vegetation) schneller
    durchschlagen.

    Returns (raw_faktor, anzahl_verbleibender_tage).
    """
    if not daten:
        return None, 0

    quotienten: list[tuple[float, float]] = []
    for datum_d, ist, prog in daten:
        if prog <= 0:
            continue
        q = ist / prog
        days_ago = (heute - datum_d).days
        recency = _O1_RECENCY_BOOST if days_ago < _O1_RECENCY_DAYS else 1.0
        w = prog * recency
        quotienten.append((q, w))

    if not quotienten:
        return None, 0

    quotienten.sort(key=lambda x: x[0])
    n = len(quotienten)
    n_trim = int(n * _O2_TRIM_PCT)
    if n_trim > 0:
        quotienten = quotienten[n_trim : n - n_trim]

    if not quotienten:
        return None, 0

    sum_qw = sum(q * w for q, w in quotienten)
    sum_w = sum(w for _, w in quotienten)
    if sum_w <= 0:
        return None, len(quotienten)

    return sum_qw / sum_w, len(quotienten)


# Backwards-compat alias — manche Callsites nutzen den Namen evtl. extern,
# die Funktionssignatur weicht aber ab. Wer (sum_ist, sum_prog, count)
# braucht, kann es trivial aus _filtere_tage rekonstruieren.
def _berechne_faktor(tage: list, db_feld: str) -> tuple[float, float, int]:
    """Legacy-Signatur: Σ(IST), Σ(Prognose), Count."""
    daten = _filtere_tage(tage, db_feld)
    sum_ist = sum(d[1] for d in daten)
    sum_prog = sum(d[2] for d in daten)
    return sum_ist, sum_prog, len(daten)


async def _get_lernfaktor_detail(
    anlage_id: int, db: AsyncSession, quelle: str = "openmeteo",
    heute: Optional[date] = None,
) -> LernfaktorResult:
    """
    Berechnet einen Korrekturfaktor (MOS-basiert) aus historischen IST/Prognose-Vergleichen.

    Saisonale Kaskade:
    1. Monatsfaktor — gleicher Kalendermonat über alle Jahre (≥15 Tage)
    2. Quartalsfaktor — gleiches Quartal über alle Jahre (≥15 Tage)
    3. Gesamtfaktor — letzte 30 Tage rollierend (≥7 Tage, bisheriges Verhalten)

    Args:
        quelle: "openmeteo" oder "solcast" — bestimmt welches Prognose-Feld verglichen wird.
        heute: Stichtag der Kaskade (Pools, Recency, Cache-Schlüssel). ``None``
            heißt „die echte Uhr" — der Produktivfall. Der Parameter existiert,
            damit Proben einen **festen** Tag setzen können, statt auf die
            Stunde ihres Laufs zu wetten (N-167; dieselbe Bauform wie
            ``aggregiere_korrekturprofil_anlage(..., heute=…)``).

    Produktionsgewichtete Berechnung: Σ(IST) / Σ(Prognose).
    Ergebnis wird tageweise gecacht (ändert sich max 1x/Tag nach Tagesabschluss).
    """
    quelle_config = PROGNOSE_QUELLEN.get(quelle)
    if not quelle_config or not quelle_config["braucht_lernfaktor"]:
        return LernfaktorResult(faktor=None, tage_count=0, quelle=quelle)

    db_feld = quelle_config["db_feld"]

    # Cache prüfen (pro Anlage + Quelle)
    cache_key = (anlage_id, quelle)
    heute = heute or date.today()
    heute_str = heute.isoformat()
    if cache_key in _lernfaktor_cache:
        cached_datum, cached_result = _lernfaktor_cache[cache_key]
        if cached_datum == heute_str:
            return cached_result

    # Alle historischen Tage laden (max ~730 Rows bei 2 Jahren, performant)
    prognose_col = getattr(TagesZusammenfassung, db_feld)
    result = await db.execute(
        select(TagesZusammenfassung).where(
            TagesZusammenfassung.anlage_id == anlage_id,
            TagesZusammenfassung.datum < heute,  # Heute ausschließen (noch nicht komplett)
            prognose_col.isnot(None),
            prognose_col > 0,
        )
    )
    alle_tage = result.scalars().all()
    # ⭐ Zählerlücken wie HA (§2, Ü2): ein Tag um ein Mitternachtsbündel mit
    # Energie (D zu niedrig, D+1 zu hoch) oder mit verworfener PV ist kein
    # Einzeltag für einen Quotienten IST/Prognose — beide fallen aus dem Pool.
    from backend.services.energie_profil.vergleichstage import tage_ohne_tagesvergleich
    _ohne = await tage_ohne_tagesvergleich(db, anlage_id, "pv", bis=heute)
    if _ohne:
        alle_tage = [t for t in alle_tage if t.datum not in _ohne]
    # HA-Bauform S5 (§3 (A) 11–15): das PV-IST an der einen Stelle — an einem Kanal-Tag aus `kanal_tage`.
    from backend.services.energie_profil.kanal_stunden import pv_ist_je_tag
    ist = await pv_ist_je_tag(db, anlage_id, alle_tage)

    # Tage in Pools aufteilen
    aktueller_monat = heute.month
    q_nr, q_monate = _quartal_fuer_monat(aktueller_monat)
    vor_30_tagen = heute - timedelta(days=30)

    pool_monat = [t for t in alle_tage if t.datum.month == aktueller_monat]
    pool_quartal = [t for t in alle_tage if t.datum.month in q_monate]
    pool_gesamt = [t for t in alle_tage if t.datum >= vor_30_tagen]

    # Kaskade: saisonal → quartal → gesamt
    # Stufen-Entscheidung anhand der Datenmenge (≥15 / ≥15 / ≥7),
    # Legacy-Aggregator bestimmt den Live-Faktor; O1+O2 läuft auf den gleichen
    # Tagen parallel als Diagnose-Variante.
    stufe = None
    label = None
    daten_aktiv: list[tuple[date, float, float]] = []
    # N-551: die Stufe entscheidet der Roh-Faktor; der gekappte Faktor lernt aus
    # **derselben** Stufe, damit beide dieselbe Saison beschreiben.
    pool_aktiv: list = []

    daten = _filtere_tage(pool_monat, db_feld, ist)
    if len(daten) >= 15:
        stufe = "saisonal"
        label = f"saisonal {_MONAT_NAMEN[aktueller_monat]} ({len(daten)} Tage)"
        daten_aktiv = daten
        pool_aktiv = pool_monat
    else:
        daten = _filtere_tage(pool_quartal, db_feld, ist)
        if len(daten) >= 15:
            stufe = "quartal"
            label = f"Quartal Q{q_nr} ({len(daten)} Tage)"
            daten_aktiv = daten
            pool_aktiv = pool_quartal
        else:
            daten = _filtere_tage(pool_gesamt, db_feld, ist)
            if len(daten) >= 7:
                stufe = "gesamt"
                label = f"gesamt ({len(daten)} Tage)"
                daten_aktiv = daten
                pool_aktiv = pool_gesamt

    if stufe is None:
        lf_result = LernfaktorResult(faktor=None, tage_count=0, quelle=quelle)
        _lernfaktor_cache[cache_key] = (heute_str, lf_result)
        return lf_result

    # ⭐ **N-551: derselbe Pool, die gekappte Basis** — Σ IST / Σ `lern_soll_kwh`
    # über die Tage **dieser Stufe**, die das Feld tragen. Reiner Pool: kein Tag
    # ohne Lern-SOLL mischt sich hinein, sonst stünden in einer Summe zwei
    # verschiedene Nenner-Begriffe nebeneinander.
    daten_gekappt = _filtere_tage(pool_aktiv, "lern_soll_kwh", ist)

    raw_legacy, tage_count = _aggregiere_legacy(daten_aktiv)
    if raw_legacy is None:
        lf_result = LernfaktorResult(faktor=None, tage_count=tage_count, quelle=quelle)
        _lernfaktor_cache[cache_key] = (heute_str, lf_result)
        return lf_result

    faktor_legacy = round(max(0.5, min(1.3, raw_legacy)), 3)

    # O1+O2 (Trim-Mean + Recency-Boost) — seit v3.30 als Live-Default.
    # Legacy-Skalar bleibt als Diagnose-Vergleich im Log.
    raw_o12, _ = _aggregiere_o12(daten_aktiv, heute)
    faktor_o12: Optional[float] = None
    delta_o12_pct: Optional[float] = None
    if raw_o12 is not None:
        faktor_o12 = round(max(0.5, min(1.3, raw_o12)), 3)
        if faktor_legacy > 0:
            delta_o12_pct = round(100.0 * (faktor_o12 - faktor_legacy) / faktor_legacy, 2)

    # Live-Faktor: O12 wenn verfügbar, Legacy als Fallback
    faktor = faktor_o12 if faktor_o12 is not None else faktor_legacy

    # Der zweite Faktor, gleiche Bauform: O12 (Recency + Trim) mit Legacy als
    # Rückfall, dieselbe Klemmung, dieselbe Rundung — nur die Basis ist die
    # gekappte. Unterhalb des Gates gar kein Wert (nicht etwa der Roh-Faktor:
    # der Aufrufer soll den Unterschied sehen können).
    faktor_gekappt: Optional[float] = None
    tage_count_gekappt = len(daten_gekappt)
    if tage_count_gekappt >= _MIN_TAGE_GEKAPPT:
        raw_g_o12, _ = _aggregiere_o12(daten_gekappt, heute)
        raw_g_legacy, _ = _aggregiere_legacy(daten_gekappt)
        raw_gekappt = raw_g_o12 if raw_g_o12 is not None else raw_g_legacy
        if raw_gekappt is not None:
            faktor_gekappt = round(max(0.5, min(1.3, raw_gekappt)), 3)

    sum_ist = sum(d[1] for d in daten_aktiv)
    sum_prognose = sum(d[2] for d in daten_aktiv)
    quelle_label = quelle_config["label"]
    legacy_log = (
        f", Legacy={faktor_legacy:.3f} (Δ {delta_o12_pct:+.1f} %)"
        if delta_o12_pct is not None
        else ""
    )
    gekappt_log = (
        f", gekappte Basis={faktor_gekappt:.3f} ({tage_count_gekappt} Tage)"
        if faktor_gekappt is not None
        else (f", gekappte Basis: nur {tage_count_gekappt} Tage mit Lern-SOLL"
              if tage_count_gekappt else "")
    )
    logger.info(
        f"Lernfaktor Anlage {anlage_id} ({quelle_label}): {faktor:.3f} — {label} "
        f"(Σ IST={sum_ist:.1f} kWh / Σ Prognose={sum_prognose:.1f} kWh)"
        f"{legacy_log}{gekappt_log}"
    )

    lf_result = LernfaktorResult(
        faktor=faktor,
        stufe=stufe,
        label=label,
        tage_count=tage_count,
        quelle=quelle,
        faktor_o12=faktor_o12,
        delta_o12_pct=delta_o12_pct,
        faktor_gekappt=faktor_gekappt,
        tage_count_gekappt=tage_count_gekappt,
    )
    _lernfaktor_cache[cache_key] = (heute_str, lf_result)
    return lf_result


async def _get_lernfaktor(
    anlage_id: int, db: AsyncSession, quelle: str = "openmeteo",
    heute: Optional[date] = None,
) -> Optional[float]:
    """Abwärtskompatibel: gibt nur den Faktor-Wert zurück.

    ⚠ **Das ist der Faktor auf der ROHEN Basis** (`pv_prognose_kwh`, W1). Wer
    ihn auf eine an der Wechselrichter-Grenze **gekappte** Reihe anwendet,
    nimmt `_get_lernfaktor_gekappt` (N-551).
    """
    result = await _get_lernfaktor_detail(anlage_id, db, quelle=quelle, heute=heute)
    return result.faktor


async def _get_lernfaktor_gekappt(
    anlage_id: int, db: AsyncSession, quelle: str = "openmeteo",
    heute: Optional[date] = None,
) -> Optional[float]:
    """Der Lernfaktor auf der **gekappten** Basis (N-551) — `None` ohne Datenlage.

    Eigene Funktion und nicht ein Argument an `_get_lernfaktor`: die Proben
    ersetzen `_get_lernfaktor` an mehreren Stellen durch eigene Fassungen mit
    fester Signatur (`(anlage_id, db, quelle="openmeteo")`). Ein zusätzliches
    Schlüsselwort dort hätte sie reihenweise gebrochen, ohne dass es um ihren
    Gegenstand ginge. Beide teilen sich denselben Tagescache
    (`_get_lernfaktor_detail`), es kostet also keine zweite Messung.
    """
    result = await _get_lernfaktor_detail(anlage_id, db, quelle=quelle, heute=heute)
    return result.faktor_gekappt


async def _speichere_prognose(
    anlage_id: int,
    datum: date,
    prognose_kwh: float,
    sfml_kwh: float | None = None,
    solcast_kwh: float | None = None,
    solcast_p10_kwh: float | None = None,
    solcast_p90_kwh: float | None = None,
    pv_stundenprofil: list[float] | None = None,
    solcast_stundenprofil: list[float] | None = None,
    sfml_stundenprofil: list[float] | None = None,
    pv_final_sonne_unter: bool = False,
    lern_stundenprofil: list[float] | None = None,
    lern_kwh: float | None = None,
):
    """
    Speichert die PV-Tagesprognose in TagesZusammenfassung (Upsert).

    Nutzt eine eigene DB-Session (fire-and-forget aus dem Request-Kontext).
    Falls der Tag schon existiert (z.B. durch Scheduler), wird nur pv_prognose_kwh aktualisiert.
    Falls nicht, wird ein minimaler Eintrag angelegt.

    Stundenprofile (`pv_stundenprofil`, `solcast_stundenprofil`): 24 Werte in
    kWh, Backward-Slot-Konvention. Pro Tag **first-write-wins** — der erste
    Snapshot bleibt als Day-Ahead-Forecast erhalten, spätere Aufrufe
    überschreiben das Profil nicht (sonst würde der nachmittagsaktualisierte
    Forecast die morgendliche Day-Ahead-Sicht verlieren).

    N-547 — `lern_stundenprofil` / `lern_kwh`: das **Lern-SOLL** des
    Korrekturprofils (rohe, gekappte, UNkorrigierte OpenMeteo-Reihe +
    ihre Tagessumme). Bewusst NICHT dasselbe wie `pv_stundenprofil`: jenes
    ist die **Vorhersage** (korrigiert + gekappt), gegen die die
    Stratifizierung die Güte misst. Der Aggregator lernte bis 22.09.2026
    gegen die Vorhersage — gegen seine eigene Ausgabe — und konvergierte
    dadurch auf √r statt r. Stundenreihe **first-write-wins** (Day-Ahead
    wie die übrigen Profile), Tageswert rollend wie `pv_prognose_kwh`.

    Prognose-Kanon §6 (`pv_prognose_final_kwh`/`_final_at`): der
    Genauigkeits-Tracking-Endwert rollt mit `prognose_kwh` mit, bis OpenMeteo
    für den Tag konvergiert ist (`pv_final_sonne_unter=True` → nach
    Sonnenuntergang fix) — dann wird `pv_prognose_final_at` gesetzt und der
    Wert nicht mehr überschrieben. Der Anzeige-Wert `pv_prognose_kwh` bleibt
    rollend (drei-Größen-Modell).
    """
    from backend.core.database import get_session
    from backend.core.berechnungen import soll_final_einfrieren

    try:
        async with get_session() as db:
            result = await db.execute(
                select(TagesZusammenfassung).where(
                    TagesZusammenfassung.anlage_id == anlage_id,
                    TagesZusammenfassung.datum == datum,
                )
            )
            tz = result.scalar_one_or_none()

            if tz:
                # UPDATE-Pfad: pro Feld via Resolver mit eigener Source-Klasse,
                # damit SFML/Solcast-spezifische Schreib-Pfade (Quellenwahl-
                # Roadmap Schritt 4) sich später disjunkt einfügen können.
                # #306: prognose_kwh kann None sein, wenn der Aufrufer den
                # OpenMeteo-Wert wegen unvollständigem Multi-String-Fan-out
                # bewusst nicht einfriert (Solcast wird trotzdem persistiert) —
                # dann den pv_prognose_kwh-Bestandswert NICHT überschreiben.
                if prognose_kwh is not None:
                    await write_with_provenance(
                        db, tz, "pv_prognose_kwh", prognose_kwh,
                        source=_OPENMETEO_SOURCE, writer=_OPENMETEO_WRITER,
                    )
                    # §6: Tracking-Endwert mitziehen, bis konvergiert (dann fix).
                    if tz.pv_prognose_final_at is None:
                        tz.pv_prognose_final_kwh = prognose_kwh
                        if soll_final_einfrieren(
                            forecast_kwh=prognose_kwh,
                            sonne_unter=pv_final_sonne_unter,
                        ):
                            tz.pv_prognose_final_at = datetime.now(
                                ZoneInfo("Europe/Berlin")
                            ).isoformat()
                if sfml_kwh is not None:
                    await write_with_provenance(
                        db, tz, "sfml_prognose_kwh", sfml_kwh,
                        source=_SFML_SOURCE, writer=_SFML_WRITER,
                    )
                if solcast_kwh is not None:
                    for feld, wert in (
                        ("solcast_prognose_kwh", solcast_kwh),
                        ("solcast_p10_kwh", solcast_p10_kwh),
                        ("solcast_p90_kwh", solcast_p90_kwh),
                    ):
                        await write_with_provenance(
                            db, tz, feld, wert,
                            source=_SOLCAST_SOURCE, writer=_SOLCAST_WRITER,
                        )
                # First-write-wins für Stundenprofile (Day-Ahead-Snapshot) —
                # bewusst kein Provenance-Anschluss: das sind interne Caches,
                # die nach festem Pattern bleiben (siehe _provenance_helpers
                # Skip-Liste).
                if pv_stundenprofil is not None and tz.pv_prognose_stundenprofil is None:
                    tz.pv_prognose_stundenprofil = pv_stundenprofil
                if solcast_stundenprofil is not None and tz.solcast_prognose_stundenprofil is None:
                    tz.solcast_prognose_stundenprofil = solcast_stundenprofil
                if sfml_stundenprofil is not None and tz.sfml_prognose_stundenprofil is None:
                    tz.sfml_prognose_stundenprofil = sfml_stundenprofil
                # N-547: Lern-SOLL. Stundenreihe first-write-wins (derselbe
                # Day-Ahead-Gedanke), Tagessumme rollend — sie ist das SOLL der
                # Skalar-Stufe und soll dem konvergierenden OM-Tageswert folgen.
                if (lern_stundenprofil is not None
                        and tz.lern_soll_stundenprofil_kwh is None):
                    tz.lern_soll_stundenprofil_kwh = lern_stundenprofil
                if lern_kwh is not None:
                    tz.lern_soll_kwh = lern_kwh
            else:
                _final_at = None
                if (prognose_kwh is not None and soll_final_einfrieren(
                        forecast_kwh=prognose_kwh, sonne_unter=pv_final_sonne_unter)):
                    _final_at = datetime.now(ZoneInfo("Europe/Berlin")).isoformat()
                tz = TagesZusammenfassung(
                    anlage_id=anlage_id,
                    datum=datum,
                    pv_prognose_kwh=prognose_kwh,
                    pv_prognose_final_kwh=prognose_kwh,
                    pv_prognose_final_at=_final_at,
                    sfml_prognose_kwh=sfml_kwh,
                    solcast_prognose_kwh=solcast_kwh,
                    solcast_p10_kwh=solcast_p10_kwh,
                    solcast_p90_kwh=solcast_p90_kwh,
                    pv_prognose_stundenprofil=pv_stundenprofil,
                    solcast_prognose_stundenprofil=solcast_stundenprofil,
                    sfml_prognose_stundenprofil=sfml_stundenprofil,
                    lern_soll_stundenprofil_kwh=lern_stundenprofil,
                    lern_soll_kwh=lern_kwh,
                    stunden_verfuegbar=0,
                    datenquelle="wetter_prognose",
                )
                db.add(tz)
                await db.flush()
                # Pro Source nur die non-None Felder markieren — sonst würde
                # eine spätere SFML/Solcast-Schreibung als Same-Source-Override
                # auf einen leeren Initial-Wert greifen statt sauber „applied".
                if prognose_kwh is not None:
                    seed_provenance(
                        tz, source=_OPENMETEO_SOURCE, writer=_OPENMETEO_WRITER,
                        fields=["pv_prognose_kwh"],
                    )
                if sfml_kwh is not None:
                    seed_provenance(
                        tz, source=_SFML_SOURCE, writer=_SFML_WRITER,
                        fields=["sfml_prognose_kwh"],
                    )
                if solcast_kwh is not None:
                    fresh_solcast = ["solcast_prognose_kwh"]
                    if solcast_p10_kwh is not None:
                        fresh_solcast.append("solcast_p10_kwh")
                    if solcast_p90_kwh is not None:
                        fresh_solcast.append("solcast_p90_kwh")
                    seed_provenance(
                        tz, source=_SOLCAST_SOURCE, writer=_SOLCAST_WRITER,
                        fields=fresh_solcast,
                    )

            await db.commit()
    except Exception as e:
        logger.warning(f"Prognose speichern fehlgeschlagen: {e}")


async def _lade_forecast_gecached(
    anlage: Anlage,
    gruppen: list[dict],
    cache_key: str,
) -> Optional[tuple]:
    """Der Open-Meteo-Tagesforecast der Anlage — aus dem Cache oder frisch.

    Herausgezogen aus `get_live_wetter`, damit **eine** Stelle den Abruf, den
    Cache und die Arität kennt: Der HA-/MQTT-Export braucht dieselben Stunden
    (Temperatur für die Wärmepumpen-Korrektur des Verbrauchsprofils), und ein
    zweiter Abruf mit eigenem Cache-Schlüssel hätte dem Sensor eine andere
    Zahl gegeben als der Anzeige daneben (#395, OB73-gif — Verbrauchsprognose
    über MQTT).

    Returns:
        ``(data, multi_gti, multi_vollstaendig)`` — oder ``None``, wenn der
        Negativ-Cache einen kürzlich gescheiterten Abruf kennt. Ein frischer
        Abruf, der scheitert, wirft; der Aufrufer entscheidet über den
        Negativ-Cache (die Route setzt ihn, der Export schluckt still).
    """
    # Haupt-Wetter-Request (Wetterdaten + GHI)
    # Bei nur einer Orientierungsgruppe: GTI direkt mit abfragen.
    # P1: `gruppen[0]` geht als Tilt/Azimut NUR in den Ein-Gruppen-Zweig unten
    # (`if not hat_multi_string`) — dort ist bewiesen, dass es genau eine
    # Orientierung gibt, die Gruppe ist also repräsentativ. Im Multi-Fall liefert
    # `_fetch_multi_string_gti` das kWp-gewichtete GTI über ALLE Gruppen.
    hat_multi_string = len(gruppen) > 1
    haupt_neigung = gruppen[0]["neigung"] if gruppen else 35
    haupt_azimut = gruppen[0]["ausrichtung"] if gruppen else 0

    cached_wetter = _cache_get(cache_key)

    # Defensiv gegen Cache-Arität-Skew über Versions-Upgrades hinweg:
    # Der persistente L2-Cache (api_cache, SQLite) kann ein Tupel falscher
    # Länge aus einer Vorversion enthalten — bis v3.36.0 legte der Prefetch
    # ein 2er-Tupel (data, None) ab. warmup_l1_from_l2 lädt es nach dem
    # Neustart in L1 zurück, und der Prefetch-Skip-Guard ("nicht über-
    # schreiben wenn vorhanden") ersetzt es nicht → das 3er-Unpack crashte
    # mit `ValueError: expected 3, got 2` → Negativ-Cache → "Keine Wetter-
    # daten verfügbar", bis der Eintrag (max. 60 Min TTL) ablief. Der reine
    # Schreiber-Fix (v3.36.1) heilt einen schon persistierten Eintrag nicht.
    # Darum: ein Nicht-3er-Tupel wie einen Cache-Miss behandeln — Neu-Abruf
    # plus _cache_set überschreibt den Alt-Eintrag (selbstheilend).
    if cached_wetter is not None and not (
        isinstance(cached_wetter, tuple) and len(cached_wetter) == 3
    ):
        logger.info(
            "Live-Wetter: Cache-Eintrag falscher Arität verworfen "
            f"(Anlage {anlage.id}, Versions-Skew im L2-Cache) — Neu-Abruf"
        )
        cached_wetter = None

    # N-698: ein UNVOLLSTÄNDIGER Eintrag wird nicht verwendet — dieselbe Regel
    # wie beim Schreiben unten (N-690). Der Prefetch legt für Multi-String
    # `(data, None, False)` unter denselben Schlüssel (er macht keinen Fan-out,
    # #306) und füllte damit genau die Lücke, die der nicht gecachte
    # unvollständige Abruf lässt: Fiel eine Gruppe aus und blieb der Kanon
    # leer, rechnete der lokale Pfad bis zu 60 min mit der Globalstrahlung statt
    # der Einstrahlung auf die Module, ohne Hinweis (gestellte Ost/West-Anlage,
    # Analyse/Bau N-698: 31,0 statt 38,8 kWh; der Teil-Abruf selbst zeigt 19,3
    # MIT Hinweis). Jetzt holt der Aufruf den Fan-out selbst; ist er
    # vollständig, überschreibt er den Eintrag.
    if cached_wetter is not None and not cached_wetter[2]:
        logger.debug(
            "Live-Wetter: unvollständiger Cache-Eintrag (ohne Multi-String-"
            f"Fan-out) für Anlage {anlage.id} — eigener Abruf"
        )
        cached_wetter = None

    if cached_wetter is not None:
        data, multi_gti, multi_vollstaendig = cached_wetter
    elif _error_cache_check(cache_key):
        return None
    else:
        hourly_vars = list(LIVE_WETTER_HOURLY_FELDER)
        if not hat_multi_string:
            hourly_vars.append("global_tilted_irradiance")

        params = {
            "latitude": anlage.latitude,
            "longitude": anlage.longitude,
            "hourly": ",".join(hourly_vars),
            "daily": ",".join(LIVE_WETTER_DAILY_FELDER),
            "timezone": "Europe/Berlin",
            "forecast_days": 1,
        }
        if not hat_multi_string:
            params["tilt"] = haupt_neigung
            params["azimuth"] = haupt_azimut

        # Wettermodell der Anlage berücksichtigen
        wetter_modell = getattr(anlage, "wetter_modell", "auto") or "auto"
        model_name, _ = WETTER_MODELLE.get(wetter_modell, (None, 16))
        if model_name:
            params["models"] = model_name

        # Bei Multi-String: paralleler GTI-Fetch + Haupt-Request gleichzeitig
        async with httpx.AsyncClient(timeout=15.0) as client:
            if hat_multi_string:
                haupt_task = client.get(
                    f"{settings.open_meteo_api_url}/forecast", params=params
                )
                gti_task = _fetch_multi_string_gti(
                    anlage.latitude, anlage.longitude, gruppen
                )
                haupt_resp, multi_result = await asyncio.gather(haupt_task, gti_task)
                haupt_resp.raise_for_status()
                data = haupt_resp.json()
                multi_gti, multi_vollstaendig = multi_result
            else:
                resp = await client.get(
                    f"{settings.open_meteo_api_url}/forecast", params=params
                )
                resp.raise_for_status()
                data = resp.json()
                multi_gti = None
                multi_vollstaendig = True  # Single-String: kein Fan-out, kein Kollaps-Risiko

        # N-690: ein unvollständiger Fan-out wird NICHT gecacht — der lokale
        # Cache hielt ihn sonst LIVE_WETTER_CACHE_TTL (1 h) samt
        # `vollstaendig=False`, während die ausgefallene Gruppe längst wieder
        # liefert. Der nächste Aufruf (Kachel alle 5 min) versucht es neu.
        if multi_vollstaendig:
            _cache_set(cache_key, (data, multi_gti, multi_vollstaendig), LIVE_WETTER_CACHE_TTL)
    return data, multi_gti, multi_vollstaendig


# ── Wetter Endpoint ──────────────────────────────────────────────────────────

@router.get("/{anlage_id}/wetter", response_model=LiveWetterResponse)
async def get_live_wetter(
    anlage_id: int,
    demo: bool = Query(False),
    db: AsyncSession = Depends(get_db),
):
    """Aktuelles Wetter + PV-Prognose + Verbrauchsprofil für heute."""
    # Orchestrator (RF-7): die Phasen stehen in `live_wetter_antwort`. Hier
    # bleiben das Laden, die Uhr und jeder Aufruf eines Namens, den Proben am
    # Modul `live_wetter` ersetzen — `_lade_forecast_gecached`,
    # `_get_lernfaktor`, `_speichere_prognose`, `_error_cache_set`. (Der
    # Docstring ist die OpenAPI-Beschreibung der Route und bleibt wörtlich.)
    result = await db.execute(select(Anlage).where(Anlage.id == anlage_id))
    anlage = result.scalar_one_or_none()
    if not anlage:
        raise not_found("Anlage")

    # PV-Module laden für Orientierung und kWp
    pv_result = await db.execute(
        select(Investition).where(
            Investition.anlage_id == anlage_id,
            Investition.typ.in_(["pv-module", "balkonkraftwerk"]),
            aktiv_jetzt(),
        )
    )
    pv_module = list(pv_result.scalars().all())
    gruppen = _get_pv_orientierungsgruppen(pv_module)
    kwp = sum(g["kwp"] for g in gruppen) if gruppen else (anlage.leistung_kwp or 10.0)

    if demo:
        data = _generate_demo_wetter(kwp)
        data["anlage_id"] = anlage.id
        return data

    if not anlage.latitude or not anlage.longitude:
        return {"anlage_id": anlage.id, "verfuegbar": False, "grund": "keine_koordinaten", "stunden": []}

    # Cache-Key aus dem geteilten Bauer (gleiche Formel im Prefetch)
    wetter_modell_key = getattr(anlage, "wetter_modell", "auto") or "auto"
    cache_key = live_wetter_cache_key(
        anlage.latitude, anlage.longitude, gruppen, wetter_modell_key
    )

    try:
        geladen = await _lade_forecast_gecached(anlage, gruppen, cache_key)
        if geladen is None:
            logger.debug(f"Live-Wetter: Negative-Cache-Hit für Anlage {anlage_id}")
            return {"anlage_id": anlage.id, "verfuegbar": False, "grund": "abruf_fehlgeschlagen", "stunden": []}
        data, multi_gti, multi_vollstaendig = geladen

        hourly = data.get("hourly", {})
        times = hourly.get("time", [])
        gti_values = _gti_werte(hourly, multi_gti)

        now = datetime.now(ZoneInfo("Europe/Berlin"))

        # Lernfaktor laden (nur bei EEDC-Quelle — bei Solcast/SFML pur, ohne Korrektur).
        # Korrekturprofil-Lookup hat Vorrang; `_get_lernfaktor` dient als Fallback,
        # solange noch keine Profile aggregiert sind (z. B. neu installierte Anlage).
        from backend.services.prognose_router import resolve_prognose_quelle
        pq = resolve_prognose_quelle(anlage)
        skalar_fallback = (
            await _get_lernfaktor(anlage_id, db) if pq.braucht_lernfaktor else None
        )

        alle_stunden, stunden = await _wetter_stunden(
            db, anlage, anlage_id, hourly, times, gti_values, pq, skalar_fallback,
        )
        aktuelle_stunde = _aktuelle_stunde(alle_stunden, now)

        daily = data.get("daily", {})

        sonne = _sonnenstunden(hourly, now)

        # Individuelles Verbrauchsprofil laden (Werktag/Wochenende) — SoT der
        # Wahl ist `verbrauchsprognose_heute.waehle_verbrauchsprofil`, damit der
        # Export-Sensor dieselbe Zahl trägt wie diese Anzeige (#395).
        from backend.services.verbrauchsprognose_heute import waehle_verbrauchsprofil
        wahl = await waehle_verbrauchsprofil(anlage, db, now)

        profil, pv_prognose, grundlast, ist_ind = _berechne_verbrauchsprofil(
            alle_stunden, kwp, individuelles_profil=wahl.ind_stunden_profil,
            wp_profil=wahl.wp_profil, referenz_hdd_kd=wahl.referenz_hdd_kd,
            wp_ww_profil=wahl.wp_ww_profil, wp_kuehlen_profil=wahl.wp_kuehlen_profil,
        )

        zahlen = await _kanon_zahlen(db, anlage, profil, pv_prognose)
        teilsumme_hinweis = _teilsumme_hinweis(multi_gti, multi_vollstaendig, zahlen.kanon_heute)

        ha_temp_found = await _ha_aussentemperatur(anlage, aktuelle_stunde)

        stand = _QuellenStand()
        await _sfml_quelle(pq, profil, stand)

        _mqtt_aussentemperatur(anlage, aktuelle_stunde, ha_temp_found)

        await _solcast_quelle(anlage, pq, stand)
        # N-696: der Rückfall der gewählten Quelle steht hinter BEIDEN Abrufen
        # (eine Regel für SFML und Solcast); `_solcast_quelle` liest `pq` nur
        # für `ist_solcast`, das ein SFML-Rückfall nicht berührt.
        pq = _pq_nach_abruf(pq, stand)

        pv_stundenprofil = _pv_stundenprofil(profil)
        pv_prognose_aktiv = _pv_prognose_aktiv(pq, zahlen.pv_prognose, stand)
        quelle_hat_profil = _rest_der_quelle(pq, stand, zahlen, now)
        prognose_quelle_tage = _prognose_quelle_tage(pq, anlage, stand, pv_prognose_aktiv)

        auftrag = _persistenz_auftrag(anlage, now, zahlen.kanon_heute, pv_stundenprofil, stand)
        if auftrag is not None:
            asyncio.create_task(
                _speichere_prognose(
                    anlage.id, date.today(), auftrag.om_prognose, stand.sfml_kwh,
                    solcast_kwh=stand.solcast_kwh,
                    solcast_p10_kwh=stand.solcast_p10,
                    solcast_p90_kwh=stand.solcast_p90,
                    pv_stundenprofil=auftrag.om_stundenprofil,
                    solcast_stundenprofil=stand.solcast_stundenprofil,
                    sfml_stundenprofil=stand.sfml_stundenprofil_heute,
                    pv_final_sonne_unter=auftrag.pv_final_sonne_unter,
                    lern_stundenprofil=auftrag.lern_stundenprofil,
                    lern_kwh=auftrag.lern_kwh,
                )
            )

        return _antwort(
            anlage, stunden, aktuelle_stunde, daily, sonne, zahlen, pv_prognose_aktiv,
            grundlast, profil, wahl, ist_ind, pq, prognose_quelle_tage, quelle_hat_profil, stand,
            teilsumme_hinweis,
        )

    except httpx.HTTPStatusError as e:
        status = e.response.status_code
        ttl = ERROR_TTL_RATE_LIMIT if status == 429 else ERROR_TTL_SERVER_ERROR
        logger.warning(f"Live-Wetter Fehler: HTTP {status}")
        _error_cache_set(cache_key, ttl)
        return {"anlage_id": anlage.id, "verfuegbar": False, "grund": "abruf_fehlgeschlagen", "stunden": []}
    except Exception as e:
        logger.warning(f"Live-Wetter Fehler: {type(e).__name__}: {e}")
        _error_cache_set(cache_key, ERROR_TTL_NETWORK)
        return {"anlage_id": anlage.id, "verfuegbar": False, "grund": "abruf_fehlgeschlagen", "stunden": []}


# ── MQTT-Inbound Status ─────────────────────────────────────────────────────

