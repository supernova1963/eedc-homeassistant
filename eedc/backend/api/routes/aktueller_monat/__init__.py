"""
Aktueller Monat API Route — Paket-Fassade.

Kombiniert Daten aus HA-Sensoren, HA-Statistics, Connectors und gespeicherten
Monatsdaten zu einer Echtzeit-Übersicht des laufenden Monats.

Seit 18.09.2026 ein Paket (Vorlage 1 des Refactorings grosser Dateien, reiner Umzug):
- ``schemas.py``   — Antwortmodelle und Konstanten
- ``vergleich.py`` — Vorjahr, PVGIS-SOLL, Nachtsockel, Tarifaufloesung
- ``tkonto.py``    — die T-Konto-Zeile je Investition
- hier            — Router, die fuenf Quellen-Sammler und der Endpunkt

⚠ Endpunkt und Sammler bleiben BEWUSST in dieser Datei: 57 Testpatches setzen Attribute auf
diesem Modulobjekt (``monkeypatch.setattr(am, "datetime", …)`` und die drei Sammler). Laege der
Endpunkt in einem Untermodul, traefen die Patches ein Modul, das die Uhr nicht mehr liest —
die Tests blieben gruen und pruefen nichts. Alle Namen, die Tests und Aufrufer bisher aus dem
Modul importierten, werden hier weiter exportiert (``__all__``).
"""

import asyncio
import logging
from datetime import date, datetime, time, timedelta
from typing import Optional
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from backend.core.exceptions import not_found
from backend.api.deps import get_db
from backend.models.anlage import Anlage
from backend.models.investition import Investition
from backend.core.investition_parameter import ist_dienstlich
from backend.core.berechnungen.zeittarif import hat_zeitfenster
from backend.api.routes.connector import _calc_month_delta
from backend.core.berechnungen.waermepumpe_kennzahl import hub_hilft
from backend.core.berechnungen import (
    berechne_grundlast,
    monatsfenster,
    merge_datenquellen,
    teilzeitraum_felder,
)
from backend.core.monatswert_grund import monatswert_grund, monatswert_grund_text
from backend.services.monats_fakten import MonatsFakt, lade_monats_fakten
from backend.api.routes.aktueller_monat.schemas import (  # noqa: F401 — Re-Export fuer Tests und Aufrufer
    AktuellerMonatResponse,
    DatenquelleInfo,
    ERLOES_LABEL_EINSPEISUNG,
    InvestitionFinancialDetail,
    MONAT_NAMEN,
    SollPv,
    SonstigesGeraet,
)
from backend.api.routes.aktueller_monat.tkonto import _baue_investition_financial  # noqa: F401
from backend.api.routes.aktueller_monat.vergleich import (  # noqa: F401
    _load_grundlast_nacht_kw,
    _load_soll_pv,
    _load_vorjahr,
    _zeittarif_preis,
)

logger = logging.getLogger(__name__)

__all__ = [
    'AktuellerMonatResponse',
    'DatenquelleInfo',
    'ERLOES_LABEL_EINSPEISUNG',
    'InvestitionFinancialDetail',
    'MONAT_NAMEN',
    'SollPv',
    'SonstigesGeraet',
    '_baue_investition_financial',
    '_collect_connector_data',
    '_collect_ha_statistics_data',
    '_collect_mqtt_inbound_data',
    '_collect_saved_data',
    '_collect_tagesebene_data',
    '_load_grundlast_nacht_kw',
    '_load_soll_pv',
    '_load_vorjahr',
    '_zeittarif_preis',
    'datetime',
    'get_aktueller_monat',
    'router',
]

router = APIRouter()

from backend.api.routes.aktueller_monat.aggregation import _WP_WAERME_D1_SUFFIX  # noqa: F401 — Konstante zog nach aggregation.py (Vorlage 2)

from backend.api.routes.aktueller_monat.aggregation import _WP_STROM_K3_SUFFIX  # noqa: F401 — Konstante zog nach aggregation.py (Vorlage 2)
from backend.api.routes.aktueller_monat.aggregation import (  # Vorlage 2
    _WP_STROM_K3_SUFFIX,
    _WP_WAERME_D1_SUFFIX,
    aggregiere_typen,
    berechne_bilanzwerte,
    emob_heimlade_quellen,
    emob_heimladung_pool,
    extrahiere_werte,
)
from backend.api.routes.aktueller_monat.finanzen import (  # Vorlage 2
    betriebskosten_und_sonstige_positionen,
    emob_aggregat_und_kennzahlen,
    finanzen_des_monats,
    komponenten_ersparnis,
    t_konto_je_investition,
)
from backend.api.routes.aktueller_monat.waerme import (  # Vorlage 2
    flags_und_wp_counter,
    waerme_klima_monat,
)
from backend.api.routes.aktueller_monat.komponenten import (  # Vorlage 2
    geraete_sicht,
    komponenten_detail,
)

# =============================================================================
# Datensammlung
# =============================================================================

async def _collect_ha_statistics_data(anlage: Anlage, jahr: int, monat: int) -> dict[str, tuple[float, DatenquelleInfo]]:
    """Sammelt Daten aus der HA Recorder-Statistik-DB (Konfidenz 92%).

    Liest MAX(state) - MIN(state) pro Sensor aus der HA statistics-Tabelle.
    Funktioniert für total_increasing UND measurement Sensoren (Fallback).
    """
    # N-156/F-26: das frühere Gate auf `HA_INTEGRATION_AVAILABLE`
    # (= SUPERVISOR_TOKEN) stand unmittelbar vor der Frage, die es beantworten
    # sollte — `ha_stats.is_available` prüft die Erreichbarkeit selbst, und zwar
    # per Recorder-DB **oder** WebSocket. Im Docker-Betrieb mit Long-Lived-Token
    # sperrte es damit die Langzeitstatistik aus, obwohl sie erreichbar war.
    #
    # ⚠ Die Erreichbarkeitsfrage steht bewusst **hinter** der Sensor-Liste:
    # `is_available` baut im Zweifel eine Verbindung auf und zahlt bei nicht
    # erreichbarer HA einen vollen Timeout. Eine Anlage ohne einen einzigen
    # Sensor-Feld-Eintrag hat hier nichts zu holen — die darf das nicht kosten.
    mapping = anlage.sensor_mapping or {}
    basis = mapping.get("basis", {})
    inv_mapping = mapping.get("investitionen", {})

    # Sensor-IDs sammeln und Rückmapping erstellen: sensor_id → feld_name
    sensor_to_feld: dict[str, str] = {}

    basis_feld_map = {
        "einspeisung": "einspeisung_kwh",
        "netzbezug": "netzbezug_kwh",
        "pv_gesamt": "pv_erzeugung_kwh",
    }
    for mapping_key, feld_name in basis_feld_map.items():
        feld_mapping = basis.get(mapping_key)
        if feld_mapping and feld_mapping.get("strategie") == "sensor" and feld_mapping.get("sensor_id"):
            sensor_to_feld[feld_mapping["sensor_id"]] = feld_name

    for inv_id_str, inv_data in inv_mapping.items():
        felder = inv_data.get("felder", {})
        for feld_key, feld_config in felder.items():
            if feld_config and feld_config.get("strategie") == "sensor" and feld_config.get("sensor_id"):
                sensor_to_feld[feld_config["sensor_id"]] = f"inv_{inv_id_str}_{feld_key}"

    if not sensor_to_feld:
        return {}

    from backend.services.ha_statistics_service import get_ha_statistics_service
    ha_stats = get_ha_statistics_service()
    if not ha_stats.is_available:
        return {}

    # Synchronen SQLite-Zugriff in Thread auslagern
    try:
        sensor_ids = list(sensor_to_feld.keys())
        # Zählerlücken wie HA (Vorlage §10): der Monat verwirft, was die
        # Stunden verwerfen — Rücksprung immer, Deckel für PV/Einspeisung.
        # Die Investitionen (für die Achse eines Felds) hängen an der Anlage —
        # die Route lädt sie per `selectinload`. Sind sie nicht geladen, wird
        # hier nichts nachgeladen (kein Lazy-Load in der async-Sitzung); dann
        # deckeln nur die Basis-Felder, der Rücksprung (R4) gilt immer.
        from sqlalchemy import inspect as _sa_inspect
        from backend.services.monatswert_deckel import deckel_je_sensor
        _zustand = _sa_inspect(anlage, raiseerr=False)
        _invs = (
            anlage.investitionen
            if _zustand is None or "investitionen" not in _zustand.unloaded else []
        )
        result = await asyncio.to_thread(
            ha_stats.get_monatswerte, sensor_ids, jahr, monat,
            deckel_je_sensor(anlage, _invs),
        )
    except Exception:
        logger.warning("HA Statistics DB nicht erreichbar")
        return {}

    resolved: dict[str, tuple[float, DatenquelleInfo]] = {}
    now_str = datetime.now().isoformat()
    quelle = DatenquelleInfo(quelle="ha_statistics", konfidenz=92, zeitpunkt=now_str)

    for sensor_wert in result.sensoren:
        feld_name = sensor_to_feld.get(sensor_wert.sensor_id)
        if feld_name and sensor_wert.differenz is not None and sensor_wert.differenz > 0:
            resolved[feld_name] = (sensor_wert.differenz, quelle)

    return resolved


async def _ha_heimlade_felder_mit_daten(anlage: Anlage, investitionen, jahr: int, monat: int) -> set[str]:
    """Die Heimlade-Felder, für die die HA-Statistik im Monat **Daten** hat — auch mit 0.

    N-555, Konzept Regel 1: *„Ergänzt eine Sicht einen abgeschlossenen Monat ohne
    Monatsabschluss aus der HA-Statistik (Cockpit → Monat), zählt deren Wert wie ein
    gespeicherter, auch 0, sofern die Statistik für den Monat Daten hat."*
    ``_collect_ha_statistics_data`` führt als Quelle der Präzedenz-Kaskade nur Werte
    über 0 (eine 0 dort verdrängte fremde Felder); die Heimladung fragt deshalb
    getrennt — nur die Heimlade-Felder privater E-Autos und Wallboxen, und nur, wenn
    ihnen ein Sensor zugeordnet ist.

    Returns:
        ``{"inv_<id>_<feld>", …}``.
    """
    from backend.core.field_definitions import HEIMLADE_FELDER

    inv_mapping = (anlage.sensor_mapping or {}).get("investitionen", {}) or {}
    sensor_to_feld: dict[str, str] = {}
    for inv in investitionen:
        if inv.typ not in HEIMLADE_FELDER or ist_dienstlich(inv):
            continue
        felder = (inv_mapping.get(str(inv.id)) or {}).get("felder", {}) or {}
        for feld in HEIMLADE_FELDER[inv.typ]:
            cfg = felder.get(feld)
            if cfg and cfg.get("strategie") == "sensor" and cfg.get("sensor_id"):
                sensor_to_feld[cfg["sensor_id"]] = f"inv_{inv.id}_{feld}"
    if not sensor_to_feld:
        return set()

    from backend.services.ha_statistics_service import get_ha_statistics_service
    ha_stats = get_ha_statistics_service()
    if not ha_stats.is_available:
        return set()
    try:
        result = await asyncio.to_thread(
            ha_stats.get_monatswerte, list(sensor_to_feld), jahr, monat,
        )
    except Exception:
        logger.warning("HA Statistics DB nicht erreichbar (Heimlade-Felder)")
        return set()
    return {
        sensor_to_feld[s.sensor_id]
        for s in result.sensoren
        if s.sensor_id in sensor_to_feld and s.differenz is not None
    }


async def _collect_connector_data(anlage: Anlage, jahr: int, monat: int) -> dict[str, tuple[float, DatenquelleInfo]]:
    """Sammelt Daten aus Connector-Snapshots (Konfidenz 90%)."""
    config = anlage.connector_config
    if not config:
        return {}

    snapshots = config.get("meter_snapshots", {})
    if not snapshots:
        return {}

    delta = _calc_month_delta(snapshots, jahr, monat)
    if not delta:
        return {}

    resolved: dict[str, tuple[float, DatenquelleInfo]] = {}
    last_fetch = config.get("last_fetch")
    # Die Abdeckung wandert mit: das Delta misst `(abdeckung_von, abdeckung_bis]`,
    # nicht zwangsläufig den ganzen Monat. `merge_datenquellen` entscheidet
    # damit, ob der Connector gespeicherte Monatswerte überschreiben darf.
    quelle = DatenquelleInfo(
        quelle="local_connector",
        konfidenz=90,
        zeitpunkt=last_fetch,
        abdeckung_von=delta.abdeckung_von,
        abdeckung_bis=delta.abdeckung_bis,
    )

    feld_map = {
        "pv_erzeugung_kwh": "pv_erzeugung_kwh",
        "einspeisung_kwh": "einspeisung_kwh",
        "netzbezug_kwh": "netzbezug_kwh",
        "batterie_ladung_kwh": "speicher_ladung_kwh",
        "batterie_entladung_kwh": "speicher_entladung_kwh",
    }
    for delta_key, feld_name in feld_map.items():
        val = delta.werte.get(delta_key)
        if val is not None:
            resolved[feld_name] = (val, quelle)

    return resolved


def _collect_saved_data(
    fakt: Optional[MonatsFakt],
) -> dict[str, tuple[float, DatenquelleInfo]]:
    """Der **gespeicherte** Zweig der Quellen-Kaskade (Konfidenz 85 %).

    Faltet nichts mehr selbst: die Mengen kommen aus den Monats-Fakten
    (ADR-002/**P10**), wo Zeitfilter (``aktiv`` · Anschaffung · Stilllegung),
    Dienstwagen-Filter, P7-Auflösung der PV und der Monatstarif genau einmal
    gelten. Übrig bleibt hier die **Merge-Semantik** — und die ist bewusst
    unverändert:

    - Die ``> 0``-Gates sind keine Rechenregel, sondern die Präzedenz-Regel der
      Kaskade: ein Feld, das ``saved`` nicht setzt, darf von einer stärkeren
      Quelle (Connector · MQTT · HA-Statistics) kommen. ``is not None`` daraus
      zu machen wäre eine andere Route, nicht dieselbe mit anderer Herkunft.
    - Einspeisung/Netzbezug kommen weiter direkt von der ``Monatsdaten``-Zeile
      und **nur, wenn sie dort gesetzt sind**: ``ZaehlerFakten`` macht aus einer
      fehlenden Zahl eine 0,0, und eine 0,0 aus der schwächsten Quelle würde
      eine echte Lücke füllen, die eine stärkere Quelle noch schließen könnte.

    Zwei Zahlen ändern sich dadurch sichtbar (beide gewollt, ``C1c``):
    die PV ist **P7-aufgelöst** (das Anlagen-Aggregat füllt Modul-Lücken, statt
    dass der Monatsbericht bei reiner Aggregat-Pflege gar keine PV zeigt), und
    der BKW-Eigenverbrauch fällt ohne Messwert **nicht** mehr auf die volle
    Erzeugung zurück (der alte D5-Quirk, divergent zu Komponenten/Übersicht).
    """
    resolved: dict[str, tuple[float, DatenquelleInfo]] = {}
    if fakt is None:
        return resolved

    md = fakt.meta.monatsdaten
    quelle = DatenquelleInfo(
        quelle="gespeichert", konfidenz=85,
        zeitpunkt=(
            md.updated_at.isoformat()
            if md is not None and getattr(md, "updated_at", None) else None
        ),
    )

    if md is not None:
        for attr, feld in [
            ("einspeisung_kwh", "einspeisung_kwh"),
            ("netzbezug_kwh", "netzbezug_kwh"),
        ]:
            val = getattr(md, attr, None)
            if val is not None:
                resolved[feld] = (val, quelle)

    for feld, wert in (
        # Module (P7-aufgelöst) + BKW — die PV-Achse der Anlage.
        ("pv_erzeugung_kwh", fakt.erzeugung.pv_kwh),
        ("speicher_ladung_kwh", fakt.speicher.ladung_kwh),
        ("speicher_entladung_kwh", fakt.speicher.entladung_kwh),
        # #183: bei getrennter Strommessung ist der Gesamt-Strom bereits im
        # Resolver summiert; `waerme` = waerme_kwh oder Heiz+WW.
        ("wp_strom_kwh", fakt.wp.strom_kwh),
        ("wp_waerme_kwh", fakt.wp.waerme_kwh),
        # #263 K-2 (E-B): der Kühlanteil — Teilmenge von `wp_strom_kwh`, hier
        # nur mitgeführt, damit die Ersparnis-Rechnung ihn herausnehmen kann.
        ("wp_modus_kuehlen_kwh", fakt.wp.modus_strom_kuehlen_kwh),
        # Heimladungs-Trias aus EINER Quelle (#262) — Dienstwagen sind in der
        # Schicht bereits heraus ([[feedback_dienstwagen_alle_checks]]).
        ("emob_ladung_kwh", fakt.emob.ladung_kwh),
        ("emob_km", fakt.emob.km),
        ("emob_verbrauch_kwh", fakt.emob.fahrverbrauch_kwh),
        ("emob_pv_ladung_kwh", fakt.emob.ladung_pv_kwh),
        ("emob_ladung_extern_euro", fakt.emob.extern_euro),
        ("bkw_erzeugung_kwh", fakt.bkw.erzeugung_kwh),
        ("bkw_eigenverbrauch_kwh", fakt.bkw.eigenverbrauch_gemessen_kwh),
        # Sonstiger Erzeuger (BHKW) speist hinter den Hauszähler.
        ("sonstiges_erzeugung_kwh", fakt.sonstiges.erzeugung_kwh),
        # §9.2: Abgabe an Dritte — wird in der Bilanz unten vom Eigenverbrauch abgezogen.
        ("sonstiges_abgabe_kwh", fakt.sonstiges.abgabe_kwh),
    ):
        if wert > 0:
            resolved[feld] = (wert, quelle)

    return resolved


async def _collect_mqtt_inbound_data(
    db: AsyncSession,
    anlage: Anlage,
    investitionen: list[Investition],
    jahr: int,
    monat: int,
    bis: Optional[datetime] = None,
) -> dict[str, tuple[float, DatenquelleInfo]]:
    """Sammelt Monatsmengen aus den MQTT-Zählerständen (Konfidenz 91%).

    ⛔ **Hier stand bis zum 2026-08-27: „Liest kumulierte Monatswerte aus dem
    MQTT-Cache."** Der Docstring war falsch, und weil `merge_datenquellen` das
    Ergebnis per ``resolved.update(mqtt_energy)`` anwendet, war es kein
    Anzeige-, sondern ein **Zahlenfehler**: Im laufenden Monat überschrieb der
    Lebenszählerstand den gespeicherten Monatswert. Bei einer Anlage ohne HA —
    also genau der Standalone-MQTT-Aufstellung, für die dieser Pfad gebaut ist
    — gewann er gegen alles außer den HA-Statistiken, die es dort nicht gibt.

    Der Cache trägt den zuletzt empfangenen **Stand**; so verlangt es die
    Topic-Registry (*„Kumulierter kWh-Zählerstand"*). Gemeldet von **gruaGit**
    (Discussion #396) an der Schwesterstelle im Monatsabschluss (F-66).

    Die Menge kommt jetzt aus der mitgeschriebenen Standreihe. Fehlt ein Rand
    oder sprang der Zähler zurück, fehlt das Feld im Ergebnis — dann bleibt der
    **gespeicherte** Wert stehen, statt von einem Stand verdrängt zu werden.

    ⭐ **Seit N-472 mit Rückfall auf den ersten Stand des Monats.** Fehlt der
    Stand am Monatsersten — die Lage jeder Anlage, die mitten im Monat
    eingerichtet wurde —, misst die Menge ab dem ersten mitgeschriebenen Stand,
    und die ``DatenquelleInfo`` dieses Feldes trägt dann ``abdeckung_von``/
    ``abdeckung_bis``. Der Slot ist derselbe, den der Connector seit #361 für
    genau diese Aussage benutzt; die Provenanz-Zeile beschriftet ihn bereits
    (*„MQTT (ab 14.09.)"*). Ein Feld **ohne** ``abdeckung_von`` hat den
    Monatsersten als linken Rand — daran erkennt der Aufrufer die Teilzeiträume,
    ohne dass diese Funktion eine zweite Liste zurückgeben muss.
    """
    from backend.services.mqtt_energy_history_service import mqtt_monats_mengen
    from backend.services.mqtt_inbound_service import get_mqtt_inbound_service
    from backend.services.snapshot.keys import extract_quellen_energy

    svc = get_mqtt_inbound_service()
    if not svc:
        return {}

    energy = svc.cache.get_energy_data(anlage.id)
    if not energy:
        return {}

    # Der Aufrufer ruft diesen Pfad nur für den laufenden Monat — die obere
    # Grenze ist deshalb das Jetzt und nicht das Monatsende (ein Stand in der
    # Zukunft existiert nicht).
    #
    # ⚠ `bis` ist ein PARAMETER, kein `datetime.now()` mitten im Rumpf: Eine
    # Probe, die die Prozessuhr liest, wettet auf die Stunde ihres Laufs (N-167)
    # — und die Suite fährt in drei Zeitzonen. Der Wächter
    # `test_konformitaet_echte_uhr_in_tests.py` hat genau das beim Bau dieser
    # Zeile gemeldet; die Naht ist die Antwort darauf und gehört ohnehin hierher.
    mengen = await mqtt_monats_mengen(
        db, anlage.id, jahr, monat, list(energy.keys()),
        quellen_energy=extract_quellen_energy(anlage),
        bis=bis if bis is not None else datetime.now(),
        rueckfall_erster_stand=True,
    )
    if not mengen:
        return {}

    resolved: dict[str, tuple[float, DatenquelleInfo]] = {}
    now_str = datetime.now().isoformat()
    quelle = DatenquelleInfo(quelle="mqtt_inbound", konfidenz=91, zeitpunkt=now_str)

    def _quelle(menge) -> DatenquelleInfo:
        """Die gemeinsame Quelle — oder eine eigene, wenn der Monatsanfang fehlt.

        Ein Feld ab Monatsbeginn bekommt die geteilte Instanz **ohne**
        Abdeckung (bitgleich zu vor N-472). Nur das Rückfall-Feld trägt seinen
        gemessenen Zeitraum, damit Provenanz-Zeile und Kachel-Hinweis ihn
        nennen können — und nur seinen eigenen, nicht den eines Nachbarn.
        """
        if menge.ab_fenster_beginn:
            return quelle
        return DatenquelleInfo(
            quelle="mqtt_inbound", konfidenz=91, zeitpunkt=now_str,
            abdeckung_von=menge.seit, abdeckung_bis=menge.bis,
        )

    # Basis-Felder
    basis_map = {
        "pv_gesamt_kwh": "pv_erzeugung_kwh",
        "einspeisung_kwh": "einspeisung_kwh",
        "netzbezug_kwh": "netzbezug_kwh",
    }
    for mqtt_key, feld_name in basis_map.items():
        menge = mengen.get(mqtt_key)
        if menge is not None and menge.menge_kwh > 0:
            resolved[feld_name] = (menge.menge_kwh, _quelle(menge))

    # Investitions-Felder: inv/{inv_id}/{key} → inv_{inv_id}_{key}
    # (passt zum Aggregations-Pattern in der Prioritätskette)
    inv_ids = {str(i.id) for i in investitionen}
    for mqtt_key, menge in mengen.items():
        if not mqtt_key.startswith("inv/") or menge.menge_kwh <= 0:
            continue
        parts = mqtt_key.split("/", 2)  # ["inv", "3", "ladung_kwh"]
        if len(parts) == 3 and parts[1] in inv_ids:
            resolved[f"inv_{parts[1]}_{parts[2]}"] = (menge.menge_kwh, _quelle(menge))

    return resolved


async def _collect_tagesebene_data(
    db: AsyncSession,
    anlage_id: int,
    jahr: int,
    monat: int,
    wp_mengen: Optional[dict] = None,
    wp_von: Optional[date] = None,
    wp_bis: Optional[date] = None,
) -> dict[str, tuple[float, DatenquelleInfo]]:
    """Die **fünfte** Quelle: die lokale Tagesebene (Konfidenz 80 %, N-472).

    ⛔ **Der Anlass.** Eine Anlage mit vollständig aggregierter Tagesebene sah
    in *Cockpit → Monat* leere Kacheln, solange keine der vier direkten Quellen
    antwortete: einen automatischen Monatsabschluss gibt es nicht, der laufende
    Monat hat also nie eine ``Monatsdaten``-Zeile, und wer weder HA-Statistik
    noch Connector noch MQTT-Zählerreihe hat, bekam gar nichts. **Der Verlauf
    daneben zeigte dieselben Tage vollständig** (gemessen an der
    Prüfstand-Anlage der Demo-DB r28: 13 September-Tage, PV 265,3 kWh,
    Einspeisung 191,9, Netzbezug 101,3 — und drei leere Kacheln darüber).

    Die Quelle ist dieselbe, die N-121 für die **Zeitreihen** geöffnet hat
    (``services/energie_profil/monats_aus_tagen.py``); hier wird sie direkt
    gelesen statt über ``lade_monats_fakten(inkl_nur_tageswerte=True)``, und
    zwar aus einem Grund: Über die Fakten-Schicht käme sie als ``gespeichert``
    heraus und behauptete eine Herkunft, die sie nicht hat. Die Marke
    ``quellen.tagesebene`` und die eigene ``DatenquelleInfo`` sind der Punkt.

    ⭐ **Zwei Leser, eine Quelle.** Die anlagenweite Strom-Bilanz kommt aus
    ``monats_aus_tagen`` (Zähler · PV · BKW · Speicher). Die **Wärme/Klima**-
    Größen reicht der Aufrufer als ``wp_mengen`` herein — aus
    ``waerme_verlauf.lade_waerme_monatsmengen_je_geraet``, **demselben Leser,
    den der Verlauf daneben für seine Tage benutzt**. Das ist keine
    Bequemlichkeit: Genau dieses Nebeneinander war der Anlass (*„der Verlauf
    zeigt dieselben Tage, die Kacheln nicht"*), und eine zweite Quelle hätte
    zwei Zahlen erzeugt, wo eine gefragt war (S1).

    ⚠ **Sie werden hereingereicht statt hier geholt**, weil der Aufrufer sie ein
    zweites Mal braucht: für die Tabelle *Zahlen je Gerät*, deren Monatszeilen
    es im laufenden Monat noch nicht gibt. Zweimal zu lesen wäre dieselbe
    Abfrage zweimal.

    ⚠ **Die WP-Größen kommen als Rohfelder je Gerät** (``inv_<id>_…``), nicht
    aufgelöst — K3 und D1 fallen anschließend in ``_wp_strom_k3`` bzw.
    ``_wp_waerme_d1`` wie bei jeder anderen Nicht-DB-Quelle. Eine Quelle, die
    ihre Größen vorab auflöst, stünde als einzige neben der Kette.

    ⚠ **Kein HA-Zugriff.** Die Tagesebene liegt lokal; das war die Auflage, unter
    der N-121 entschieden wurde, und sie gilt hier genauso.

    Returns:
        ``{feld: (menge, DatenquelleInfo)}`` — nur Größen mit ``> 0``, wie in
        allen vier Collectoren. Keine Tagesspur ⇒ leeres Dict.
    """
    from backend.services.energie_profil.monats_aus_tagen import (
        lade_monats_summen_aus_tagen,
    )

    summen = await lade_monats_summen_aus_tagen(
        db, anlage_id, von=(jahr, monat), bis=(jahr, monat)
    )
    summe = summen.get((jahr, monat))
    wp_mengen = wp_mengen or {}

    if (summe is None or summe.tage <= 0) and not wp_mengen:
        return {}

    # Die Abdeckung gehört dazu (P4): Beginnt die Tagesspur erst mitten im
    # Monat — später eingerichtetes Add-on, Vollbackfill, der nicht zurückreicht
    # —, sagt die Provenanz-Zeile es (*„Tageswerte (ab 05.09.)"*). Derselbe
    # Slot, dieselbe Beschriftung wie beim Connector seit #361; beginnt sie am
    # Monatsersten, schweigt sie von selbst (`connector_deckt_monatsanfang`).
    # ⚠ Die Ränder der **beiden** Leser zusammen — die Wärme-Spur kann früher
    # beginnen als die Bilanz-Spur und umgekehrt.
    _erste = [t for t in (getattr(summe, "erster_tag", None), wp_von) if t]
    _letzte = [t for t in (getattr(summe, "letzter_tag", None), wp_bis) if t]
    quelle = DatenquelleInfo(
        quelle="tagesebene", konfidenz=80, zeitpunkt=datetime.now().isoformat(),
        abdeckung_von=datetime.combine(min(_erste), time.min) if _erste else None,
        abdeckung_bis=(
            datetime.combine(max(_letzte), time.min) + timedelta(days=1)
            if _letzte else None
        ),
    )
    resolved: dict[str, tuple[float, DatenquelleInfo]] = {}
    for feld, wert in (
        ("einspeisung_kwh", getattr(summe, "einspeisung_kwh", 0.0)),
        ("netzbezug_kwh", getattr(summe, "netzbezug_kwh", 0.0)),
        # `pv_kwh` ist Module + BKW — dieselbe PV-Achse wie im DB-Zweig.
        ("pv_erzeugung_kwh", summe.pv_kwh if summe is not None else 0.0),
        ("bkw_erzeugung_kwh", getattr(summe, "bkw_kwh", 0.0)),
        ("speicher_ladung_kwh", getattr(summe, "speicher_ladung_kwh", 0.0)),
        ("speicher_entladung_kwh", getattr(summe, "speicher_entladung_kwh", 0.0)),
    ):
        if wert > 0:
            resolved[feld] = (wert, quelle)

    # ── Wärme/Klima je Gerät (A-5) ──
    # Die Feldnamen sind die der **Registry**, nicht die der Tagesebene — genau
    # die Keys, die `_wp_strom_k3` und `_wp_waerme_d1` unten lesen. Damit läuft
    # die bestehende Kette (K3 · D1 · `typ_aggregation` · Systemarbeitszahl),
    # statt daneben eine zweite zu entstehen.
    for inv_id, m in wp_mengen.items():
        for feld, wert in (
            ("stromverbrauch_kwh", m.strom_kwh),
            ("waerme_kwh", m.waerme_kwh),
            ("heizenergie_kwh", m.heizung_kwh),
            ("warmwasser_kwh", m.warmwasser_kwh),
            ("strom_heizen_kwh", m.strom_heizen_kwh),
            ("strom_warmwasser_kwh", m.strom_warmwasser_kwh),
            ("kaelte_kwh", m.kaelte_kwh),
        ):
            if wert > 0:
                resolved[f"inv_{inv_id}_{feld}"] = (wert, quelle)
    # Der Kühlanteil als Anlagensumme — Eingang der Ersparnis-Rechnung, wie im
    # DB-Zweig (`fakt.wp.modus_strom_kuehlen_kwh`). Er ist eine **Teilmenge**
    # des WP-Stroms, keine eigene Achse, und läuft deshalb nicht durch K3.
    _kuehl = sum(m.modus_strom_kuehlen_kwh for m in wp_mengen.values())
    if _kuehl > 0:
        resolved["wp_modus_kuehlen_kwh"] = (_kuehl, quelle)
    return resolved

# =============================================================================
# Endpoint
# =============================================================================

@router.get("/{anlage_id}", response_model=AktuellerMonatResponse)
async def get_aktueller_monat(
    anlage_id: int,
    jahr: Optional[int] = None,
    monat: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
):
    """
    Übersicht eines Monats mit Daten aus allen verfügbaren Quellen.

    Reihenfolge der vier Quellen (spätere überschreiben frühere):
    1. Gespeicherte Monatsdaten (85%) — DB
    2. Connector (90%) — Geräte-Snapshot-Delta
    3. MQTT-Inbound (91%) — Energy-Topics aus Smarthome (nur aktueller Monat)
    4. HA Statistics (92%) — Recorder-DB

    **Die Konfidenz allein entscheidet nicht** — überschreiben darf eine
    frischere Quelle nur im **laufenden** Monat (Live-Vorschau). Im
    abgeschlossenen Monat sind die gespeicherten Werte authoritativ: Connector
    (#325 detlefh68) und HA-Statistics (#118 Safi105) füllen dort nur
    **fehlende** Felder (`setdefault`), MQTT wird gar nicht erst gesammelt.
    Ein importierter Monatswert (Cloud-/Portal-/CSV-Import) wird von einem
    zugeordneten HA-Sensor hier also **nicht** verdrängt — die Zuordnung
    stehen zu lassen kostet ihn nichts.

    Was „fehlend" heißt, entscheiden die `> 0`-Gates in `_collect_saved_data`:
    eine gespeicherte 0,0 gilt der Kaskade nicht als Wert und darf gefüllt
    werden. Begründung im Docstring dort.

    **Nur diese Route.** Auf der **Schreib**-Seite gilt die Aussage nicht:
    `external:portal_import` (Cloud-/Portal-Import) und `external:ha_statistics`
    stehen auf derselben Hierarchie-Stufe (`core/source_priority.py`), gleiche
    Stufe ist Last-Writer-Wins. Ein HA-Statistik-Import mit gesetztem
    `ueberschreiben` überschreibt einen Cloud-Wert dauerhaft in der DB. Wer
    den Wert wirklich festnageln will, pflegt ihn im Formular (`manual:form`,
    Stufe 1 — die einzige, die beide schlägt).

    Der Connector überschreibt zusätzlich nur mit belegter Monatsabdeckung
    (#361), sonst ist sein Delta ein Teilzeitraum.

    Die Regeln selbst stehen in `core/berechnungen/datenquellen.py`
    (ADR-001) — hier steht nur, was diese Route hineinreicht.
    """
    # N-267: Zeittarif-Cache dieser Anfrage (SIEBEN Bildungsstellen in dieser
    # Route lesen ihn) — Begruendung im Block ueber `_zeittarif_preis`.
    _zt_cache: dict = {}
    # Anlage mit Investitionen laden
    result = await db.execute(
        select(Anlage)
        .options(selectinload(Anlage.investitionen))
        .where(Anlage.id == anlage_id)
    )
    anlage = result.scalar_one_or_none()
    if not anlage:
        raise not_found("Anlage")

    now = datetime.now()
    if jahr is None:
        jahr = now.year
    if monat is None:
        monat = now.month
    ist_aktueller_monat = (jahr == now.year and monat == now.month)
    # Das gemessene Fenster des Monats — EIN Anker für alle Größen, die im
    # laufenden Monat mit den abgelaufenen Tagen wachsen (SOLL · Grundlast ·
    # Speicher-Auslastung). Vorher zählte jede dieser drei Stellen ihre Tage
    # selbst, mit drei Kopien derselben `min(heute.day, tage_im_monat)`-Zeile.
    fenster = monatsfenster(jahr, monat, heute=now.date())
    investitionen = [i for i in anlage.investitionen if i.aktiv]

    # ── Daten sammeln (I/O) — Zusammenführung nach Präzedenz im SoT-Helper ──
    # Sammeln bleibt hier (DB/HA-Zugriff); die Merge-/Override-Regeln leben in
    # core/berechnungen/datenquellen.merge_datenquellen (ADR-001) — eine Stelle,
    # symmetrie-getestet, ohne Drift zwischen den Quellen-Zweigen.
    # MQTT wird für abgeschlossene Monate gar nicht erst gesammelt.
    #
    # ADR-002/**P10**: die Monatszeile wird genau einmal aufbereitet. Diese
    # Route mischt vier Quellen, von denen die Schicht ausdrücklich nur EINE
    # kennt (die DB — Live/Connector sind Nicht-Ziel, KONZEPT-MONATS-FAKTEN §4).
    # Also kommt der DB-Zweig aus den Fakten, die Präzedenz bleibt hier.
    monats_fakten = await lade_monats_fakten(
        db, anlage_id, von=(jahr, monat), bis=(jahr, monat)
    )
    monats_fakt = monats_fakten[0] if monats_fakten else None

    saved = _collect_saved_data(monats_fakt)
    connector = await _collect_connector_data(anlage, jahr, monat)
    mqtt_energy = (
        await _collect_mqtt_inbound_data(db, anlage, investitionen, jahr, monat)
        if ist_aktueller_monat else {}
    )
    ha_stats = await _collect_ha_statistics_data(anlage, jahr, monat)
    # N-555: welche Heimlade-Felder hat die HA-Statistik in einem ABGESCHLOSSENEN
    # Monat überhaupt (auch mit 0)? Im laufenden Monat genügt die Quelle.
    ha_felder_mit_daten: set[str] = (
        await _ha_heimlade_felder_mit_daten(anlage, investitionen, jahr, monat)
        if not ist_aktueller_monat else set()
    )
    # Fünfte Quelle (N-472) — nur im laufenden Monat, und das ist eine Aussage
    # über die Kategorie, nicht über den Aufwand: Im laufenden Monat IST eine
    # Teilmenge der Tage die vollständige Auskunft über das bisher Geschehene,
    # und alle vier Quellen darüber messen dort ebenfalls nur bis jetzt. In
    # einem abgeschlossenen Monat wäre dieselbe Teilmenge eine stille
    # Untertreibung eines Monatswertes — dort ist die Antwort der
    # Monatsabschluss, auf den der Daten-Checker ohnehin zeigt
    # (`daten_checker/monatsdaten.py`, MONATSDATEN_VOLLSTAENDIGKEIT).
    # Die Wärme/Klima-Mengen der Tagesebene — EINMAL gelesen, zweimal gebraucht:
    # für die Kacheln (über den Collector) und für die Tabelle *Zahlen je Gerät*
    # weiter unten, deren Monatszeilen es im laufenden Monat noch nicht gibt.
    _tages_wp_mengen: dict = {}
    _tages_wp_von = _tages_wp_bis = None
    if ist_aktueller_monat and investitionen:
        from calendar import monthrange

        from backend.services.energie_profil.waerme_verlauf import (
            lade_waerme_monatsmengen_je_geraet,
        )
        _tages_wp_mengen, _tages_wp_von, _tages_wp_bis = (
            await lade_waerme_monatsmengen_je_geraet(
                db, anlage, {str(i.id): i for i in investitionen},
                date(jahr, monat, 1), date(jahr, monat, monthrange(jahr, monat)[1]),
            )
        )
    tagesebene = (
        await _collect_tagesebene_data(
            db, anlage_id, jahr, monat,
            wp_mengen=_tages_wp_mengen, wp_von=_tages_wp_von, wp_bis=_tages_wp_bis,
        )
        if ist_aktueller_monat else {}
    )

    # Abdeckung des Connector-Deltas — sie steht in jedem seiner
    # DatenquelleInfo (eine Instanz für alle Felder), der erste Eintrag genügt.
    # Naive Zeitstempel wie in `_calc_month_delta`, daher direkt mit dem
    # naiven Monatsanfang vergleichbar.
    connector_abdeckung_von = next(
        (info.abdeckung_von for _, info in connector.values() if info.abdeckung_von),
        None,
    )

    quellen_args = dict(
        saved=saved,
        connector=connector,
        mqtt_energy=mqtt_energy,
        ha_stats=ha_stats,
        ist_aktueller_monat=ist_aktueller_monat,
        connector_abdeckung_von=connector_abdeckung_von,
        monat_start=datetime(jahr, monat, 1),
        tagesebene=tagesebene,
    )
    resolved: dict[str, tuple[float, DatenquelleInfo]] = merge_datenquellen(**quellen_args)

    # Felder, die nur einen Teilzeitraum messen — sie dürfen die Aggregation der
    # Komponenten-Werte nicht unterdrücken, siehe `direct_fields` unten (#361).
    # Drei Herkünfte: Connector-Delta ohne Abdeckung des Monatsanfangs, MQTT mit
    # Rückfall auf den ersten Stand (N-472) und die Tagesebene. Woran ein
    # MQTT-Feld als Rückfall erkennbar ist, steht in `_collect_mqtt_inbound_data`:
    # an der gesetzten `abdeckung_von` seiner eigenen `DatenquelleInfo`.
    teilzeitraum = teilzeitraum_felder(
        **quellen_args,
        mqtt_ab_monatsbeginn={
            k for k, (_, info) in mqtt_energy.items() if info.abdeckung_von is None
        },
    )

    # ── aggregiere_typen (Vorlage 2: Abschnitt in aggregation.py, Schnittstelle 5 ein / 1 aus) ──
    _out = aggregiere_typen(investitionen=investitionen, jahr=jahr, monat=monat, resolved=resolved, teilzeitraum=teilzeitraum)
    if "direct_fields" in _out: direct_fields = _out["direct_fields"]
    # ── emob_heimladung_pool (Vorlage 2: Abschnitt in aggregation.py, Schnittstelle 5 ein / 0 aus) ──
    # N-555: dazu die Heimlade-Quellen (nur laufender Monat), die gespeicherte
    # Zeile des Monats und die HA-Felder mit Daten — die eine Funktion entscheidet.
    _out = emob_heimladung_pool(
        direct_fields=direct_fields, investitionen=investitionen, jahr=jahr, monat=monat, resolved=resolved,
        monats_fakt=monats_fakt, ist_aktueller_monat=ist_aktueller_monat,
        heimlade_quellen=(
            await emob_heimlade_quellen(db, anlage, investitionen, jahr, monat)
            if ist_aktueller_monat else frozenset()
        ),
        ha_felder_mit_daten=ha_felder_mit_daten,
    )
    emob_entscheid = _out.get("emob_entscheid")
    # ── extrahiere_werte (Vorlage 2: Abschnitt in aggregation.py, Schnittstelle 2 ein / 10 aus) ──
    _out = extrahiere_werte(monats_fakt=monats_fakt, resolved=resolved)
    if "abgabe_dritte" in _out: abgabe_dritte = _out["abgabe_dritte"]
    if "einspeisung" in _out: einspeisung = _out["einspeisung"]
    if "erzeugung_bilanz" in _out: erzeugung_bilanz = _out["erzeugung_bilanz"]
    if "get_val" in _out: get_val = _out["get_val"]
    if "hinweise" in _out: hinweise = _out["hinweise"]
    if "netzbezug" in _out: netzbezug = _out["netzbezug"]
    if "pv" in _out: pv = _out["pv"]
    if "sonstiges_erz_bilanz" in _out: sonstiges_erz_bilanz = _out["sonstiges_erz_bilanz"]
    if "speicher_entladung" in _out: speicher_entladung = _out["speicher_entladung"]
    if "speicher_ladung" in _out: speicher_ladung = _out["speicher_ladung"]
    # ── berechne_bilanzwerte (Vorlage 2: Abschnitt in aggregation.py, Schnittstelle 8 ein / 5 aus) ──
    _out = berechne_bilanzwerte(abgabe_dritte=abgabe_dritte, einspeisung=einspeisung, erzeugung_bilanz=erzeugung_bilanz, netzbezug=netzbezug, pv=pv, sonstiges_erz_bilanz=sonstiges_erz_bilanz, speicher_entladung=speicher_entladung, speicher_ladung=speicher_ladung)
    if "autarkie" in _out: autarkie = _out["autarkie"]
    if "direktverbrauch" in _out: direktverbrauch = _out["direktverbrauch"]
    if "eigenverbrauch" in _out: eigenverbrauch = _out["eigenverbrauch"]
    if "ev_quote" in _out: ev_quote = _out["ev_quote"]
    if "gesamtverbrauch" in _out: gesamtverbrauch = _out["gesamtverbrauch"]
    # ── finanzen_des_monats (Vorlage 2: Abschnitt in finanzen.py, Schnittstelle 8 ein / 19 aus) ──
    _out = await finanzen_des_monats(_zt_cache=_zt_cache, anlage_id=anlage_id, db=db, eigenverbrauch=eigenverbrauch, einspeisung=einspeisung, jahr=jahr, monat=monat, netzbezug=netzbezug)
    if "allgemein_tarif" in _out: allgemein_tarif = _out["allgemein_tarif"]
    if "einspeise_cent" in _out: einspeise_cent = _out["einspeise_cent"]
    if "einspeise_erloes" in _out: einspeise_erloes = _out["einspeise_erloes"]
    if "einspeisung_neg_preis" in _out: einspeisung_neg_preis = _out["einspeisung_neg_preis"]
    if "ev_ersparnis" in _out: ev_ersparnis = _out["ev_ersparnis"]
    if "grundgebuehr" in _out: grundgebuehr = _out["grundgebuehr"]
    if "monats_benzinpreis" in _out: monats_benzinpreis = _out["monats_benzinpreis"]
    if "monats_gaspreis" in _out: monats_gaspreis = _out["monats_gaspreis"]
    if "netto_ertrag" in _out: netto_ertrag = _out["netto_ertrag"]
    if "netzbezug_arbeitspreis_kosten" in _out: netzbezug_arbeitspreis_kosten = _out["netzbezug_arbeitspreis_kosten"]
    if "netzbezug_durchschnittspreis" in _out: netzbezug_durchschnittspreis = _out["netzbezug_durchschnittspreis"]
    if "netzbezug_kosten" in _out: netzbezug_kosten = _out["netzbezug_kosten"]
    if "netzbezug_preis_abdeckung" in _out: netzbezug_preis_abdeckung = _out["netzbezug_preis_abdeckung"]
    if "netzbezug_preis_cent" in _out: netzbezug_preis_cent = _out["netzbezug_preis_cent"]
    if "netzbezug_preis_effektiv_cent" in _out: netzbezug_preis_effektiv_cent = _out["netzbezug_preis_effektiv_cent"]
    if "netzbezug_preis_herkunft" in _out: netzbezug_preis_herkunft = _out["netzbezug_preis_herkunft"]
    if "nicht_vergueteter_erloes" in _out: nicht_vergueteter_erloes = _out["nicht_vergueteter_erloes"]
    if "tarife" in _out: tarife = _out["tarife"]
    if "zaehlergebuehr_jahr" in _out: zaehlergebuehr_jahr = _out["zaehlergebuehr_jahr"]
    # ── komponenten_ersparnis (Vorlage 2: Abschnitt in finanzen.py, Schnittstelle 1 ein / 5 aus) ──
    _out = komponenten_ersparnis(get_val=get_val)
    if "emob_ersparnis" in _out: emob_ersparnis = _out["emob_ersparnis"]
    if "wp_ersparnis" in _out: wp_ersparnis = _out["wp_ersparnis"]
    if "wp_ersparnis_berechnung_text" in _out: wp_ersparnis_berechnung_text = _out["wp_ersparnis_berechnung_text"]
    if "wp_strom" in _out: wp_strom = _out["wp_strom"]
    if "wp_waerme" in _out: wp_waerme = _out["wp_waerme"]
    # ── waerme_klima_monat (Vorlage 2: Abschnitt in waerme.py, Schnittstelle 16 ein / 10 aus) ──
    _out = await waerme_klima_monat(_tages_wp_mengen=_tages_wp_mengen, _zt_cache=_zt_cache, allgemein_tarif=allgemein_tarif, anlage_id=anlage_id, db=db, get_val=get_val, investitionen=investitionen, jahr=jahr, monat=monat, monats_fakt=monats_fakt, monats_gaspreis=monats_gaspreis, netzbezug_preis_effektiv_cent=netzbezug_preis_effektiv_cent, tarife=tarife, teilzeitraum=teilzeitraum, wp_strom=wp_strom, wp_waerme=wp_waerme)
    if "_wp_abgrenzung_je_funktion" in _out: _wp_abgrenzung_je_funktion = _out["_wp_abgrenzung_je_funktion"]
    if "_wp_funktion" in _out: _wp_funktion = _out["_wp_funktion"]
    if "_wp_kennzahlen_je_geraet" in _out: _wp_kennzahlen_je_geraet = _out["_wp_kennzahlen_je_geraet"]
    if "wp_abgrenzung_verletzt" in _out: wp_abgrenzung_verletzt = _out["wp_abgrenzung_verletzt"]
    if "wp_arbeitszahl" in _out: wp_arbeitszahl = _out["wp_arbeitszahl"]
    if "wp_ersparnis" in _out: wp_ersparnis = _out["wp_ersparnis"]
    if "wp_ersparnis_berechnung_text" in _out: wp_ersparnis_berechnung_text = _out["wp_ersparnis_berechnung_text"]
    if "wp_ersparnis_vorbehalt" in _out: wp_ersparnis_vorbehalt = _out["wp_ersparnis_vorbehalt"]
    if "wp_waerme_abgeleitet_kwh" in _out: wp_waerme_abgeleitet_kwh = _out["wp_waerme_abgeleitet_kwh"]
    if "wp_waerme_herkunft" in _out: wp_waerme_herkunft = _out["wp_waerme_herkunft"]
    # ── betriebskosten_und_sonstige_positionen (Vorlage 2: Abschnitt in finanzen.py, Schnittstelle 2 ein / 9 aus) ──
    _out = betriebskosten_und_sonstige_positionen(investitionen=investitionen, monats_fakt=monats_fakt)
    if "anlage_sonstige_ausgaben" in _out: anlage_sonstige_ausgaben = _out["anlage_sonstige_ausgaben"]
    if "anlage_sonstige_ertraege" in _out: anlage_sonstige_ertraege = _out["anlage_sonstige_ertraege"]
    if "betriebskosten_anteilig" in _out: betriebskosten_anteilig = _out["betriebskosten_anteilig"]
    if "betriebskosten_anteilig_anzahl" in _out: betriebskosten_anteilig_anzahl = _out["betriebskosten_anteilig_anzahl"]
    if "betriebskosten_anteilig_jahr" in _out: betriebskosten_anteilig_jahr = _out["betriebskosten_anteilig_jahr"]
    if "gesamtnettoertrag" in _out: gesamtnettoertrag = _out["gesamtnettoertrag"]
    if "sonstige_ausgaben_total" in _out: sonstige_ausgaben_total = _out["sonstige_ausgaben_total"]
    if "sonstige_ertraege_total" in _out: sonstige_ertraege_total = _out["sonstige_ertraege_total"]
    if "sonstige_netto_total" in _out: sonstige_netto_total = _out["sonstige_netto_total"]
    # ── komponenten_detail (Vorlage 2: Abschnitt in komponenten.py, Schnittstelle 15 ein / 33 aus) ──
    _out = await komponenten_detail(_wp_abgrenzung_je_funktion=_wp_abgrenzung_je_funktion, _wp_funktion=_wp_funktion, _wp_kennzahlen_je_geraet=_wp_kennzahlen_je_geraet, anlage_id=anlage_id, db=db, fenster=fenster, investitionen=investitionen, jahr=jahr, monat=monat, monats_fakt=monats_fakt, speicher_entladung=speicher_entladung, speicher_ladung=speicher_ladung, wp_abgrenzung_verletzt=wp_abgrenzung_verletzt, wp_arbeitszahl=wp_arbeitszahl, wp_waerme_abgeleitet_kwh=wp_waerme_abgeleitet_kwh)
    if "mf_bkw" in _out: mf_bkw = _out["mf_bkw"]
    if "mf_emob" in _out: mf_emob = _out["mf_emob"]
    if "mf_sonstiges" in _out: mf_sonstiges = _out["mf_sonstiges"]
    if "mf_wp" in _out: mf_wp = _out["mf_wp"]
    if "speicher_auslastung" in _out: speicher_auslastung = _out["speicher_auslastung"]
    if "speicher_auslastungs_basis" in _out: speicher_auslastungs_basis = _out["speicher_auslastungs_basis"]
    if "speicher_eff_ladepreis" in _out: speicher_eff_ladepreis = _out["speicher_eff_ladepreis"]
    if "speicher_eff_ladepreis_quelle" in _out: speicher_eff_ladepreis_quelle = _out["speicher_eff_ladepreis_quelle"]
    if "speicher_ersparnis" in _out: speicher_ersparnis = _out["speicher_ersparnis"]
    if "speicher_imd_ladepreis" in _out: speicher_imd_ladepreis = _out["speicher_imd_ladepreis"]
    if "speicher_kapazitaet" in _out: speicher_kapazitaet = _out["speicher_kapazitaet"]
    if "speicher_ladung_netz" in _out: speicher_ladung_netz = _out["speicher_ladung_netz"]
    if "speicher_soc_drift_flag" in _out: speicher_soc_drift_flag = _out["speicher_soc_drift_flag"]
    if "speicher_vollzyklen" in _out: speicher_vollzyklen = _out["speicher_vollzyklen"]
    if "speicher_wirkungsgrad" in _out: speicher_wirkungsgrad = _out["speicher_wirkungsgrad"]
    if "speicher_wirkungsgrad_quelle" in _out: speicher_wirkungsgrad_quelle = _out["speicher_wirkungsgrad_quelle"]
    if "wp_az_funktion" in _out: wp_az_funktion = _out["wp_az_funktion"]
    if "wp_az_kuehlen" in _out: wp_az_kuehlen = _out["wp_az_kuehlen"]
    if "wp_heizung" in _out: wp_heizung = _out["wp_heizung"]
    if "wp_modus_abdeckung" in _out: wp_modus_abdeckung = _out["wp_modus_abdeckung"]
    if "wp_modus_bezug" in _out: wp_modus_bezug = _out["wp_modus_bezug"]
    if "wp_modus_entfeuchten" in _out: wp_modus_entfeuchten = _out["wp_modus_entfeuchten"]
    if "wp_modus_gemessen" in _out: wp_modus_gemessen = _out["wp_modus_gemessen"]
    if "wp_modus_heizen" in _out: wp_modus_heizen = _out["wp_modus_heizen"]
    if "wp_modus_kuehlen" in _out: wp_modus_kuehlen = _out["wp_modus_kuehlen"]
    if "wp_modus_lueften" in _out: wp_modus_lueften = _out["wp_modus_lueften"]
    if "wp_modus_rest" in _out: wp_modus_rest = _out["wp_modus_rest"]
    if "wp_modus_warmwasser" in _out: wp_modus_warmwasser = _out["wp_modus_warmwasser"]
    if "wp_nutz_entfeuchten" in _out: wp_nutz_entfeuchten = _out["wp_nutz_entfeuchten"]
    if "wp_nutz_lueften" in _out: wp_nutz_lueften = _out["wp_nutz_lueften"]
    if "wp_strom_heizen" in _out: wp_strom_heizen = _out["wp_strom_heizen"]
    if "wp_strom_warmwasser" in _out: wp_strom_warmwasser = _out["wp_strom_warmwasser"]
    if "wp_warmwasser" in _out: wp_warmwasser = _out["wp_warmwasser"]
    # ── geraete_sicht (Vorlage 2: Abschnitt in komponenten.py, Schnittstelle 13 ein / 15 aus) ──
    _out = geraete_sicht(_wp_kennzahlen_je_geraet=_wp_kennzahlen_je_geraet, emob_entscheid=emob_entscheid, get_val=get_val, investitionen=investitionen, mf_bkw=mf_bkw, mf_emob=mf_emob, mf_sonstiges=mf_sonstiges, netzbezug_preis_effektiv_cent=netzbezug_preis_effektiv_cent, speicher_eff_ladepreis=speicher_eff_ladepreis, speicher_imd_ladepreis=speicher_imd_ladepreis, speicher_ladung_netz=speicher_ladung_netz, wp_arbeitszahl=wp_arbeitszahl, wp_az_funktion=wp_az_funktion, wp_az_kuehlen=wp_az_kuehlen)
    if "bkw_eigenverbrauch" in _out: bkw_eigenverbrauch = _out["bkw_eigenverbrauch"]
    if "emob_ladung_extern" in _out: emob_ladung_extern = _out["emob_ladung_extern"]
    if "emob_ladung_netz" in _out: emob_ladung_netz = _out["emob_ladung_netz"]
    if "emob_pv" in _out: emob_pv = _out["emob_pv"]
    if "emob_v2h" in _out: emob_v2h = _out["emob_v2h"]
    if "netzladung_kosten" in _out: netzladung_kosten = _out["netzladung_kosten"]
    if "sonstiges_bezug_netz" in _out: sonstiges_bezug_netz = _out["sonstiges_bezug_netz"]
    if "sonstiges_bezug_pv" in _out: sonstiges_bezug_pv = _out["sonstiges_bezug_pv"]
    if "sonstiges_eigenverbrauch" in _out: sonstiges_eigenverbrauch = _out["sonstiges_eigenverbrauch"]
    if "sonstiges_einspeisung" in _out: sonstiges_einspeisung = _out["sonstiges_einspeisung"]
    if "sonstiges_erzeugung" in _out: sonstiges_erzeugung = _out["sonstiges_erzeugung"]
    if "sonstiges_geraete" in _out: sonstiges_geraete = _out["sonstiges_geraete"]
    if "sonstiges_verbrauch" in _out: sonstiges_verbrauch = _out["sonstiges_verbrauch"]
    if "wp_block_geraete" in _out: wp_block_geraete = _out["wp_block_geraete"]
    if "wp_block_moeglich" in _out: wp_block_moeglich = _out["wp_block_moeglich"]
    # ── flags_und_wp_counter (Vorlage 2: Abschnitt in waerme.py, Schnittstelle 5 ein / 9 aus) ──
    _out = await flags_und_wp_counter(anlage_id=anlage_id, db=db, investitionen=investitionen, jahr=jahr, monat=monat)
    if "hat_balkonkraftwerk" in _out: hat_balkonkraftwerk = _out["hat_balkonkraftwerk"]
    if "hat_emobilitaet" in _out: hat_emobilitaet = _out["hat_emobilitaet"]
    if "hat_sonstiges" in _out: hat_sonstiges = _out["hat_sonstiges"]
    if "hat_speicher" in _out: hat_speicher = _out["hat_speicher"]
    if "hat_waermepumpe" in _out: hat_waermepumpe = _out["hat_waermepumpe"]
    if "wp_betriebsstunden_max_tag" in _out: wp_betriebsstunden_max_tag = _out["wp_betriebsstunden_max_tag"]
    if "wp_betriebsstunden_summe_monat" in _out: wp_betriebsstunden_summe_monat = _out["wp_betriebsstunden_summe_monat"]
    if "wp_starts_max_tag" in _out: wp_starts_max_tag = _out["wp_starts_max_tag"]
    if "wp_starts_summe_monat" in _out: wp_starts_summe_monat = _out["wp_starts_summe_monat"]
    # ── Vergleichsdaten ──
    vorjahr = await _load_vorjahr(anlage_id, investitionen, jahr, monat, db)
    soll_pv = await _load_soll_pv(anlage_id, jahr, monat, db, fenster)

    # ── Grundlast (Nacht-Sockel, R12-1: ersetzt PVGIS-SOLL/IST in Cockpit/Monat
    # + Jahr; Formel im Berechnungs-Layer, Median wie der Live-Wert). Im aktuellen
    # Monat nur die bisherigen Tage hochrechnen, sonst alle Kalendertage. ──
    grundlast_tage = fenster.tage
    grundlast = berechne_grundlast(
        nacht_verbrauch_kw=await _load_grundlast_nacht_kw(anlage_id, jahr, monat, db),
        gesamtverbrauch_kwh=gesamtverbrauch,
        tage=grundlast_tage,
    )

    # ── Quellen-Übersicht ──
    # `tagesebene` steht **als eigene Marke** daneben und wird nicht unter
    # „gespeichert" verbucht (N-472): Sie ist nicht gepflegt, sondern abgeleitet
    # — wer sie für einen Monatsabschluss hält, sucht eine Zeile, die es nicht
    # gibt.
    quellen = {
        "ha_statistics": bool(ha_stats),
        "mqtt_inbound": bool(mqtt_energy) if ist_aktueller_monat else False,
        "connector": bool(connector),
        "gespeichert": bool(saved),
        "tagesebene": bool(tagesebene),
    }

    # ── Grund statt Leere (N-472) ──
    # Die Regel und der Wortlaut stehen in `core/monatswert_grund.py`; hier wird
    # nur die eine Frage beantwortet, die diese Route beantworten kann: Hat für
    # diesen Monat überhaupt irgendeine Quelle irgendetwas geliefert?
    _grund = monatswert_grund_text(monatswert_grund(bool(resolved)))
    datenlage_gruende: dict[str, str] = (
        {
            feld: _grund
            for feld in ("pv_erzeugung_kwh", "einspeisung_kwh", "netzbezug_kwh")
            if get_val(feld) is None
        }
        if _grund else {}
    )

    # ── Feld-Quellen extrahieren ──
    feld_quellen = {
        feld: info
        for feld, (_, info) in resolved.items()
        if not feld.startswith("inv_")  # Investitions-Detail-Felder ausblenden
    }

    # ── Aktive Geräte je Typ (Namen) für die „aggregiert aus …"-Hinweise ──
    komponenten_geraete: dict[str, list[str]] = {}
    for _inv in investitionen:
        if _inv.ist_aktiv_im_monat(jahr, monat):
            komponenten_geraete.setdefault(_inv.typ, []).append(_inv.bezeichnung)

    # ── t_konto_je_investition (Vorlage 2: Abschnitt in finanzen.py, Schnittstelle 12 ein / 2 aus) ──
    _out = await t_konto_je_investition(_zt_cache=_zt_cache, allgemein_tarif=allgemein_tarif, anlage_id=anlage_id, db=db, einspeise_cent=einspeise_cent, investitionen=investitionen, jahr=jahr, monat=monat, monats_benzinpreis=monats_benzinpreis, monats_gaspreis=monats_gaspreis, netzbezug_preis_effektiv_cent=netzbezug_preis_effektiv_cent, tarife=tarife)
    if "investitionen_financials" in _out: investitionen_financials = _out["investitionen_financials"]
    if "speicher_ersparnis" in _out: speicher_ersparnis = _out["speicher_ersparnis"]
    # ── emob_aggregat_und_kennzahlen (Vorlage 2: Abschnitt in finanzen.py, Schnittstelle 12 ein / 4 aus) ──
    _out = emob_aggregat_und_kennzahlen(anlage=anlage, emob_ladung_extern=emob_ladung_extern, einspeise_erloes=einspeise_erloes, emob_ersparnis=emob_ersparnis, ev_ersparnis=ev_ersparnis, get_val=get_val, investitionen=investitionen, investitionen_financials=investitionen_financials, jahr=jahr, monat=monat, netzbezug_kosten=netzbezug_kosten, pv=pv, wp_ersparnis=wp_ersparnis)
    if "emob_eff" in _out: emob_eff = _out["emob_eff"]
    if "emob_ladung_gesamt" in _out: emob_ladung_gesamt = _out["emob_ladung_gesamt"]
    emob_ersparnis_berechnung = _out.get("emob_ersparnis_berechnung")
    if "emob_ersparnis" in _out: emob_ersparnis = _out["emob_ersparnis"]
    if "gesamtnettoertrag" in _out: gesamtnettoertrag = _out["gesamtnettoertrag"]
    if "spez_ertrag" in _out: spez_ertrag = _out["spez_ertrag"]
    # ── Antwort ──
    return AktuellerMonatResponse(
        anlage_id=anlage.id,
        anlage_name=anlage.anlagenname,
        jahr=jahr,
        monat=monat,
        monat_name=MONAT_NAMEN[monat],
        aktualisiert_um=now.isoformat(),
        quellen=quellen,
        hinweise=hinweise,
        datenlage_gruende=datenlage_gruende,
        # Energie
        pv_erzeugung_kwh=pv,
        einspeisung_kwh=einspeisung,
        netzbezug_kwh=netzbezug,
        eigenverbrauch_kwh=eigenverbrauch,
        direktverbrauch_kwh=direktverbrauch,
        gesamtverbrauch_kwh=gesamtverbrauch,
        autarkie_prozent=autarkie,
        eigenverbrauch_quote_prozent=ev_quote,
        spez_ertrag=round(spez_ertrag, 1) if spez_ertrag is not None else None,
        # Komponenten — Speicher
        speicher_ladung_kwh=speicher_ladung,
        speicher_entladung_kwh=speicher_entladung,
        speicher_ladung_netz_kwh=speicher_ladung_netz,
        speicher_wirkungsgrad_prozent=speicher_wirkungsgrad,
        speicher_wirkungsgrad_quelle=speicher_wirkungsgrad_quelle,
        speicher_vollzyklen=speicher_vollzyklen,
        speicher_kapazitaet_kwh=speicher_kapazitaet,
        speicher_soc_drift_signifikant=speicher_soc_drift_flag,
        speicher_auslastungs_basis_kwh=speicher_auslastungs_basis,
        speicher_auslastung_prozent=speicher_auslastung,
        speicher_ersparnis_euro=speicher_ersparnis,
        speicher_effektiver_ladepreis_cent=speicher_eff_ladepreis,
        speicher_effektiver_ladepreis_quelle=speicher_eff_ladepreis_quelle,
        speicher_ladung_netz_kosten_euro=netzladung_kosten.kosten_euro if netzladung_kosten else None,
        speicher_ladung_netz_preis_cent=netzladung_kosten.preis_cent if netzladung_kosten else None,
        speicher_ladung_netz_preis_quelle=netzladung_kosten.quelle if netzladung_kosten else None,
        hat_speicher=hat_speicher,
        # Komponenten — WP
        wp_strom_kwh=get_val("wp_strom_kwh"),
        wp_waerme_kwh=get_val("wp_waerme_kwh"),
        wp_heizung_kwh=wp_heizung,
        wp_warmwasser_kwh=wp_warmwasser,
        wp_jaz=wp_arbeitszahl.wert,
        wp_jaz_grund=wp_arbeitszahl.grund,
        wp_jaz_hinweis=wp_arbeitszahl.hinweis,
        wp_jaz_zaehler_kwh=wp_arbeitszahl.zaehler_kwh,
        wp_jaz_nenner_kwh=wp_arbeitszahl.nenner_kwh,
        wp_waerme_abgeleitet=wp_waerme_abgeleitet_kwh > 0,
        # Alle Gründe des Blocks in EINE Frage — der Link ist ein Element des
        # Blocks, keine Zeile je Kennzahl.
        wp_hub_hilft=hub_hilft(
            wp_arbeitszahl.grund,
            wp_az_funktion.heizen.grund,
            wp_az_funktion.warmwasser.grund,
            wp_az_kuehlen.grund,
            ist_schranke=wp_arbeitszahl.ist_schranke,
        ),
        # Die Menge nur, wo es überhaupt Wärme gibt — sonst stünde eine 0
        # neben einem „—" und sähe aus wie „nichts gerechnet" statt „nichts
        # gemessen". Gleiche Rundung wie `wp_waerme_kwh` daneben.
        wp_waerme_abgeleitet_kwh=(
            round(wp_waerme_abgeleitet_kwh, 2) if wp_waerme is not None else None
        ),
        wp_waerme_herkunft=wp_waerme_herkunft,
        wp_ersparnis_vorbehalt=wp_ersparnis_vorbehalt,
        wp_ersparnis_berechnung=wp_ersparnis_berechnung_text,
        wp_strom_heizen_kwh=wp_strom_heizen,
        wp_strom_warmwasser_kwh=wp_strom_warmwasser,
        wp_modus_strom_heizen_kwh=wp_modus_heizen,
        wp_modus_strom_kuehlen_kwh=wp_modus_kuehlen,
        wp_modus_strom_warmwasser_kwh=wp_modus_warmwasser,
        wp_jaz_heizen=wp_az_funktion.heizen.wert,
        wp_jaz_heizen_grund=wp_az_funktion.heizen.grund,
        wp_jaz_warmwasser=wp_az_funktion.warmwasser.wert,
        wp_jaz_warmwasser_grund=wp_az_funktion.warmwasser.grund,
        wp_jaz_kuehlen=wp_az_kuehlen.wert,
        wp_jaz_kuehlen_grund=wp_az_kuehlen.grund,
        wp_jaz_ist_schranke=wp_arbeitszahl.ist_schranke,
        wp_jaz_schranke_hinweis=wp_arbeitszahl.schranke_hinweis,
        wp_geraete=wp_block_geraete,
        wp_moeglich=wp_block_moeglich,
        wp_kaelte_kwh=(
            round(mf_wp.nutzenergie_kuehlen_kwh, 2)
            if mf_wp is not None and mf_wp.nutzenergie_kuehlen_kwh > 0 else None
        ),
        wp_modus_strom_lueften_kwh=wp_modus_lueften,
        wp_modus_strom_entfeuchten_kwh=wp_modus_entfeuchten,
        wp_modus_nutzenergie_lueften_kwh=wp_nutz_lueften,
        wp_modus_nutzenergie_entfeuchten_kwh=wp_nutz_entfeuchten,
        wp_modus_nicht_aufgeteilt_kwh=wp_modus_rest,
        wp_modus_abdeckung_h=wp_modus_abdeckung,
        wp_modus_strom_bezug_kwh=wp_modus_bezug,
        wp_modus_gemessen=wp_modus_gemessen,
        wp_starts_max_tag=wp_starts_max_tag,
        wp_starts_summe_monat=wp_starts_summe_monat,
        wp_betriebsstunden_max_tag=wp_betriebsstunden_max_tag,
        wp_betriebsstunden_summe_monat=wp_betriebsstunden_summe_monat,
        hat_waermepumpe=hat_waermepumpe,
        # Komponenten — E-Mobilität
        emob_ladung_kwh=get_val("emob_ladung_kwh"),
        emob_km=get_val("emob_km"),
        emob_verbrauch_100km=round(emob_eff.wert, 1) if emob_eff.wert is not None else None,
        emob_verbrauch_quelle=emob_eff.quelle,
        emob_ladung_pv_kwh=emob_pv if emob_pv else None,
        emob_ladung_netz_kwh=emob_ladung_netz,
        emob_ladung_extern_kwh=emob_ladung_extern,
        emob_v2h_kwh=emob_v2h,
        emob_ladung_gesamt_kwh=emob_ladung_gesamt,
        emob_verbrauch_basis_kwh=(
            round(emob_eff.basis_kwh, 2) if emob_eff.basis_kwh is not None else None
        ),
        hat_emobilitaet=hat_emobilitaet,
        # Komponenten — BKW
        bkw_erzeugung_kwh=get_val("bkw_erzeugung_kwh"),
        bkw_eigenverbrauch_kwh=bkw_eigenverbrauch,
        hat_balkonkraftwerk=hat_balkonkraftwerk,
        # Komponenten — Sonstiges
        sonstiges_erzeugung_kwh=sonstiges_erzeugung,
        abgabe_dritte_kwh=round(abgabe_dritte, 2) if abgabe_dritte > 0 else None,
        sonstiges_eigenverbrauch_kwh=sonstiges_eigenverbrauch,
        sonstiges_einspeisung_kwh=sonstiges_einspeisung,
        sonstiges_verbrauch_kwh=sonstiges_verbrauch,
        sonstiges_bezug_pv_kwh=sonstiges_bezug_pv,
        sonstiges_bezug_netz_kwh=sonstiges_bezug_netz,
        sonstiges_geraete=sonstiges_geraete,
        hat_sonstiges=hat_sonstiges,
        # Finanzen
        einspeise_erloes_euro=einspeise_erloes,
        einspeisung_neg_preis_kwh=einspeisung_neg_preis,
        nicht_vergueteter_erloes_euro=nicht_vergueteter_erloes,
        netzbezug_kosten_euro=netzbezug_kosten,
        netzbezug_arbeitspreis_kosten_euro=netzbezug_arbeitspreis_kosten,
        ev_ersparnis_euro=ev_ersparnis,
        netto_ertrag_euro=netto_ertrag,
        wp_ersparnis_euro=wp_ersparnis,
        emob_ersparnis_euro=emob_ersparnis,
        emob_ersparnis_berechnung=emob_ersparnis_berechnung,
        sonstige_ertraege_euro=sonstige_ertraege_total,
        sonstige_ausgaben_euro=sonstige_ausgaben_total,
        sonstige_netto_euro=sonstige_netto_total,
        anlage_sonstige_ertraege_euro=anlage_sonstige_ertraege,
        anlage_sonstige_ausgaben_euro=anlage_sonstige_ausgaben,
        gesamtnettoertrag_euro=gesamtnettoertrag,
        betriebskosten_anteilig_euro=betriebskosten_anteilig,
        betriebskosten_anteilig_jahr_euro=betriebskosten_anteilig_jahr,
        betriebskosten_anteilig_anzahl=betriebskosten_anteilig_anzahl,
        # Tarif-Info
        netzbezug_preis_cent=netzbezug_preis_cent if allgemein_tarif else None,
        # Der Wert zu `_herkunft`/`_abdeckung` — ohne ihn beschreiben die beiden
        # eine Zahl, die die Antwort nicht enthält (SOLL Flex-Tarife H-2).
        netzbezug_preis_effektiv_cent=netzbezug_preis_effektiv_cent,
        netzbezug_preis_herkunft=netzbezug_preis_herkunft,
        netzbezug_preis_abdeckung=netzbezug_preis_abdeckung,
        # N-267: sagt der Anzeige, dass der Preis daneben gewichtet ist.
        netzbezug_preis_zeittarif=hat_zeitfenster(allgemein_tarif),
        einspeise_preis_cent=einspeise_cent if allgemein_tarif else None,
        netzbezug_durchschnittspreis_cent=netzbezug_durchschnittspreis,
        grundgebuehr_euro=grundgebuehr,
        zaehlergebuehr_euro_jahr=zaehlergebuehr_jahr,
        # Vergleiche
        vorjahr=vorjahr,
        soll_pv_kwh=soll_pv.anteilig,
        soll_pv_tage=fenster.tage if soll_pv.anteilig is not None else None,
        soll_pv_tage_gesamt=fenster.tage_gesamt if soll_pv.anteilig is not None else None,
        soll_pv_kwh_monat=soll_pv.monat,
        grundlast_kw=grundlast.grundlast_kw,
        grundlast_kwh=grundlast.grundlast_kwh,
        grundlast_anteil_prozent=grundlast.grundlast_anteil_prozent,
        # Per-Investition Finanzdetails
        investitionen_financials=investitionen_financials,
        komponenten_geraete=komponenten_geraete,
        # Quellen
        feld_quellen=feld_quellen,
    )
