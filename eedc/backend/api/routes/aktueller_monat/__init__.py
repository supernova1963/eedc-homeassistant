"""
Aktueller Monat API Route — Paket-Fassade.

Kombiniert Daten aus HA-Sensoren, HA-Statistics, Connectors und gespeicherten
Monatsdaten zu einer Echtzeit-Übersicht des laufenden Monats.

Seit 18.09.2026 ein Paket (Vorlage 1 des Refactorings grosser Dateien, reiner Umzug):
- ``schemas.py``   — Antwortmodelle und Konstanten
- ``vergleich.py`` — Vorjahr, PVGIS-SOLL, Nachtsockel, Tarifaufloesung
- ``tkonto.py``    — die T-Konto-Zeile je Investition
- ``quellen_leser.py`` — gespeicherter Zweig, Kanal-Leser des Kalendermonats, Regeln der gemessenen 0 (RF-12)
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
from backend.core.berechnungen.ergebnis import soll_erfuellung
from backend.core.berechnungen.pv_verteilung import eigenverbrauch_ohne_verluste_kwh, wandlungsverluste_prozent
from backend.core.berechnungen.erzeuger_traeger import abgetretene_bkw_ids
from backend.api.routes.aktueller_monat.kontext import MonatsKontext, lade_monats_kontext
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
    '_berechne_monat',
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
    emob_bloecke_des_monats as _emob_bloecke_des_monats,
    emob_heimlade_quellen,
    emob_heimladung_pool,
    extrahiere_werte,
)
from backend.api.routes.aktueller_monat.finanzen import (  # Vorlage 2
    betriebskosten_und_sonstige_positionen,
    dienstliche_ladung_ohne_fakt,
    ergebnis_des_monats,
    emob_aggregat_und_kennzahlen,
    wp_aggregat_aus_zeilen,
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
from backend.api.routes.aktueller_monat.quellen_leser import (  # RF-12 (`_collect_saved_data` auch für Tests/`__all__`)
    _collect_saved_data,
    _geraete_aus_kanaelen,
    _ha_statistik_aus_kanaelen_mit_marke,
    _null_ist_messwert,
    _sensor_to_feld,
    _wandlungsverluste_des_monats,
    _wp_aus_kanaelen,
    _wp_gemessene_null_aus_fakt,
    _wp_sicht,
)

# =============================================================================
# Datensammlung
# =============================================================================


async def _collect_ha_statistics_data(anlage: Anlage, jahr: int, monat: int) -> dict[str, tuple[float, DatenquelleInfo]]:
    """Sammelt Daten aus der HA Recorder-Statistik-DB (Konfidenz 92%).

    Liest MAX(state) - MIN(state) pro Sensor aus der HA statistics-Tabelle.
    Funktioniert für total_increasing UND measurement Sensoren (Fallback).

    ⭐ **N-585: eine gemessene 0 bleibt eine 0** — für die Felder aus ``_NULL_IST_MESSWERT_BASIS`` und die
    Gerätefelder der Typen in ``_NULL_IST_MESSWERT_TYPEN``. Gemessen heißt: mindestens ein Intervall
    (``SensorMonatswert.intervalle ≥ 1`` — Anker + eine Zeile oder zwei Zeilen); eine einzelne Zeile misst
    nichts, ihre 0 wäre erfunden (Netzbezug 0,0 und Autarkie 100 % aus einer Zeile). Alle anderen Felder kommen
    weiter nur mit Werten über 0 — eine 0 dort verdrängte fremde Felder bzw. bräuchte erst eine Darstellungsregel.
    Ein Feld ohne Zeilen im Monat fehlt im Ergebnis (``None`` in der Antwort, mit Grund).
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
    sensor_to_feld = _sensor_to_feld(anlage)

    if not sensor_to_feld:
        return {}

    from backend.services.ha_statistics_service import get_ha_statistics_service
    ha_stats = get_ha_statistics_service()
    if not ha_stats.is_available:
        return {}

    # Synchronen SQLite-Zugriff in Thread auslagern
    try:
        sensor_ids = list(sensor_to_feld.keys())
        # Zählerlücken wie HA (Vorlage §10): der Monat verwirft einen Rücksprung
        # des HA-`sum` (R4). ⭐ Kein Deckel (HA-Bauform S4-R-5): der Monat nennt
        # HAs Zahl wie Tag und Kanal-Monat — einen Phantomsprung benennt der
        # Daten-Checker `ha_zaehlersprung`. Die Investitionen (Typ eines Geräte-
        # felds, unten) hängen an der Anlage — die Route lädt sie per
        # `selectinload`. Sind sie nicht geladen, wird hier nichts nachgeladen
        # (kein Lazy-Load in der async-Sitzung).
        from sqlalchemy import inspect as _sa_inspect
        _zustand = _sa_inspect(anlage, raiseerr=False)
        _invs = (
            anlage.investitionen
            if _zustand is None or "investitionen" not in _zustand.unloaded else []
        )
        result = await asyncio.to_thread(
            ha_stats.get_monatswerte, sensor_ids, jahr, monat,
        )
    except Exception:
        logger.warning("HA Statistics DB nicht erreichbar")
        return {}

    resolved: dict[str, tuple[float, DatenquelleInfo]] = {}
    now_str = datetime.now().isoformat()
    quelle = DatenquelleInfo(quelle="ha_statistics", konfidenz=92, zeitpunkt=now_str)

    typ_je_inv = {str(i.id): i.typ for i in _invs}
    for sensor_wert in result.sensoren:
        feld_name = sensor_to_feld.get(sensor_wert.sensor_id)
        if not feld_name or sensor_wert.differenz is None:
            continue
        if sensor_wert.differenz > 0 or (
            sensor_wert.differenz == 0
            and sensor_wert.intervalle >= 1
            and _null_ist_messwert(feld_name, typ_je_inv)
        ):
            resolved[feld_name] = (sensor_wert.differenz, quelle)

    return resolved


async def _ha_heimlade_felder_mit_daten(anlage: Anlage, investitionen, jahr: int, monat: int) -> set[str]:
    """Die Heimlade-Felder, für die die HA-Statistik im Monat **Daten** hat — auch mit 0.

    N-555, Konzept Regel 1: *„Ergänzt eine Sicht einen abgeschlossenen Monat ohne
    Monatsabschluss aus der HA-Statistik (Cockpit → Monat), zählt deren Wert wie ein
    gespeicherter, auch 0, sofern die Statistik für den Monat Daten hat."*
    ``_collect_ha_statistics_data`` führt als Quelle der Präzedenz-Kaskade eine 0 nur für
    die Felder, deren gemessene 0 ein Wert ist (N-585: Basis-Zähler, Speicher, Balkonkraftwerk,
    Wallbox, E-Auto — und nur mit mindestens einem Intervall); die Heimladung fragt hier
    weiter getrennt — nur die Heimlade-Felder privater E-Autos und Wallboxen, und nur, wenn
    ihnen ein Sensor zugeordnet ist. Ihre Menge „hatte Daten" gilt ohne Intervall-Schranke
    (Konzept Regel 1: „sofern die Statistik für den Monat Daten hat").

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
    abgetretene_bkw: frozenset = frozenset(),
    summen: Optional[dict] = None,
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

    ``summen``: das Ergebnis von ``lade_monats_summen`` für diesen Monat, wenn der Aufrufer es schon geladen hat
    (N-750: ``_quellen_des_monats`` braucht dieselbe Summe für die Sonstiges-Erzeuger) — sonst lädt die Quelle selbst.

    Returns:
        ``{feld: (menge, DatenquelleInfo)}`` — Größen mit ``> 0``; Einspeisung und
        Netzbezug auch mit gemessener 0 (mindestens eine Stunde mit Wert, N-585).
        Keine Tagesspur ⇒ leeres Dict.
    """
    # HA-Bauform E4a-2 (Umschaltstelle 2): dieselbe Quellenwahl je Monat wie die Monats-Fakten — deckt jeder Kanal
    # der Bilanz-Gruppe den Monat, kommt er aus den Kanälen (Weg 2), sonst unverändert aus der Tagesebene.
    from backend.services.kanal.bilanz_leser import lade_monats_summen

    if summen is None:
        summen = await lade_monats_summen(db, anlage_id, von=(jahr, monat), bis=(jahr, monat))
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
        # N-628: die eigene BKW-Zeile nennt nur GEMESSENE Tageswerte — ein
        # Balkonkraftwerk ohne eigenen Zähler hat im Aggregat-Fall einen
        # `bkw_<id>`-Key mit seinem kWp-Anteil (Marke `kwp_anteil`); der gehört
        # in die PV-Achse (`pv_kwh` oben), nicht in die Zeile — wie im
        # abgeschlossenen Monat (`monats_fakten/fakten.py`).
        # N-627: ein im Monat an seine Modul-Kinder abgetretenes Balkonkraftwerk
        # nennt keine eigene Zeile — sein Tages-Key ist der E4-Rest, im Monat
        # tragen die Kinder (ADR-002/P11).
        ("bkw_erzeugung_kwh", sum(
            v for k, v in (summe.bkw_gemessen_je_inv or {}).items()
            if k not in {str(i) for i in abgetretene_bkw}
        ) if summe is not None else 0.0),
        ("speicher_ladung_kwh", getattr(summe, "speicher_ladung_kwh", 0.0)),
        ("speicher_entladung_kwh", getattr(summe, "speicher_entladung_kwh", 0.0)),
    ):
        # N-585: Einspeisung und Netzbezug tragen auch eine gemessene 0 — gemessen heißt hier: mindestens eine
        # Stunde des Monats mit Wert (`*_erfasst`). Ohne das Flag wäre ein nicht zugeordneter Zähler 0,0 kWh und
        # Autarkie 100 % (alle Stunden ohne Wert summieren sich zu 0,0). Die übrigen Größen bleiben bei „über 0".
        if wert > 0 or (
            feld in ("einspeisung_kwh", "netzbezug_kwh")
            and bool(getattr(summe, feld.replace("_kwh", "_erfasst"), False))
        ):
            resolved[feld] = (wert, _feld_quelle_tagesebene(summe, feld, quelle))

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
            # E4d (Bauplan §8a, Rest N-585): Strom und Wärme einer WP tragen auch eine gemessene 0 (mindestens ein Tag
            # mit Wert); die Funktions-Achsen und die Kälte bleiben bei „über 0" (keine Matrix-Form, keine Regel).
            if wert > 0 or (wert == 0 and feld in ("stromverbrauch_kwh", "waerme_kwh")
                            and _TAGES_WP_FELD.get(feld, feld) in getattr(m, "gemessen", frozenset())):
                resolved[f"inv_{inv_id}_{feld}"] = (wert, quelle)
    # Der Kühlanteil als Anlagensumme — Eingang der Ersparnis-Rechnung, wie im
    # DB-Zweig (`fakt.wp.modus_strom_kuehlen_kwh`). Er ist eine **Teilmenge**
    # des WP-Stroms, keine eigene Achse, und läuft deshalb nicht durch K3.
    _kuehl = sum(m.modus_strom_kuehlen_kwh for m in wp_mengen.values())
    if _kuehl > 0:
        resolved["wp_modus_kuehlen_kwh"] = (_kuehl, quelle)
    return resolved

#: Die Felder der Tagesebene (``WaermeMonatsMengenJeGeraet``) zu den Registry-Feldern der Quellen-Kaskade.
_TAGES_WP_FELD = {"stromverbrauch_kwh": "strom_kwh", "waerme_kwh": "waerme_kwh"}

#: N-726: die Basis-Zähler, deren Abdeckung je Feld die Tagesebene kennt (``TagesMonatsSumme.abdeckung_je_feld``),
#: mit dem Wort für den Hinweis und den Größen, die auf ihnen beruhen.
_TEILWERT_FELDER = {
    "netzbezug_kwh": ("netzbezug", "Der Netzbezug", "Gesamtverbrauch und Autarkie"),
    "einspeisung_kwh": ("einspeisung", "Die Einspeisung", "Eigenverbrauch und Eigenverbrauchsquote"),
}


def _feld_quelle_tagesebene(summe, feld: str, spur: DatenquelleInfo) -> DatenquelleInfo:
    """N-726: die Quelle eines Basis-Zählers aus der Tagesebene — mit SEINER Abdeckung, wenn sie kürzer ist als die Spur.

    ``*_erfasst`` genügt schon eine Stunde; die Abdeckung der Spur (``spur``) gilt allen Größen zusammen. Trägt ein Zähler
    nur einen Teil der Tage mit Stundenzeilen (Sensor zugeordnet, HA hat für ihn keine Zeilen mehr — umbenannte oder
    gelöschte Entity), bekommt das Feld eine eigene ``DatenquelleInfo`` mit dem Zeitraum, den es misst (dieselbe Bauform
    wie das MQTT-Rückfallfeld in ``_collect_mqtt_inbound_data``), und ``_tagesebene_teilwert_hinweise`` nennt es.

    ⚠ **Ein Tag Spielraum am Ende:** ein Zähler ohne Nachtzeilen (Bauplan HA-Bauform §3b, Nachtrag E3 Punkt 3) trägt
    den laufenden Tag erst ab der ersten Stunde mit Wert — in der Nacht davor endet er einen Tag vor der Spur, ohne eine
    Teilsumme zu sein (seine Lückenstunden stecken in der Folgestunde, R7). Am Anfang gibt es keinen Spielraum: beginnt
    er einen Tag nach der Spur, fehlt dieser Tag (``beginnt_nach_von``, N-678).
    """
    abdeckung = getattr(summe, "abdeckung_je_feld", None) or {}
    name = _TEILWERT_FELDER.get(feld, (None,))[0]
    gesamt, eigen = abdeckung.get("stunden"), abdeckung.get(name) if name else None
    if gesamt is None or eigen is None:
        return spur
    if eigen[0] <= gesamt[0] and eigen[1] >= gesamt[1] - timedelta(days=1):
        return spur
    return DatenquelleInfo(
        quelle=spur.quelle, konfidenz=spur.konfidenz, zeitpunkt=spur.zeitpunkt,
        abdeckung_von=datetime.combine(eigen[0], time.min),
        abdeckung_bis=datetime.combine(eigen[1], time.min) + timedelta(days=1),
    )


def _tage_text(von: datetime, bis: datetime) -> str:
    """``[von, bis)`` in Tagen als Text — „am 01.07." oder „vom 01.07. bis 03.07."."""
    letzter = bis - timedelta(days=1)
    if letzter.date() <= von.date():
        return f"am {von:%d.%m.}"
    return f"vom {von:%d.%m.} bis {letzter:%d.%m.}"


def _tagesebene_teilwert_hinweise(
    resolved: dict[str, tuple[float, DatenquelleInfo]],
    tagesebene: dict[str, tuple[float, DatenquelleInfo]],
) -> list[str]:
    """N-726 (ADR-002/P4): der Satz für einen Basis-Zähler, der aus der Tagesebene gewinnt und nur einen Teil der Spur misst.

    **Beschriften, nicht unterdrücken** (Entscheid wie N-678): die Zahl bleibt, die Antwort sagt, worauf sie beruht.
    Gemessen am Fall vom 04.10.2026 (Form F06, Netz-Sensor ohne HA-Zeilen im Juli): Netzbezug 0,4 kWh und Autarkie
    99,1 % statt 21,6 und 67,6 % — ohne Kennzeichen. Erkennbar an der eigenen, kürzeren ``DatenquelleInfo`` des Feldes
    (``_feld_quelle_tagesebene``) gegenüber der Spur aller übrigen Größen.
    """
    spur = [info for _, info in tagesebene.values() if info.abdeckung_von and info.abdeckung_bis]
    if not spur:
        return []
    von = min(i.abdeckung_von for i in spur)
    bis = max(i.abdeckung_bis for i in spur)
    hinweise = []
    for feld, (_name, wort, folge) in _TEILWERT_FELDER.items():
        eintrag = resolved.get(feld)
        if eintrag is None:
            continue
        info = eintrag[1]
        if info.quelle != "tagesebene" or not info.abdeckung_von or not info.abdeckung_bis:
            continue
        if info.abdeckung_von <= von and info.abdeckung_bis >= bis:
            continue
        hinweise.append(
            f"{wort} ist eine Teilsumme: Tageswerte gibt es dafür nur "
            f"{_tage_text(info.abdeckung_von, info.abdeckung_bis)}, für die übrigen Größen "
            f"{_tage_text(von, bis)} — {folge} rechnen mit diesem Teilwert."
        )
    return hinweise

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
    """Übersicht eines Monats — die Rechnung steht in `_berechne_monat` (Docstring dort).

    Die Route bleibt eine dünne Hülle mit unveränderter Signatur: ein zusätzlicher Parameter hier würde von FastAPI
    als Query-/Body-Parameter ausgelegt (Gegenprüfung G3). Die Jahresroute ruft deshalb die Innenfunktion mit einem
    Vorlade-Kontext (`kontext.py`), damit die zwölf Monate die Fakten J−1…J nur EINMAL laden.
    """
    return await _berechne_monat(anlage_id, jahr, monat, db)


async def _berechne_monat(
    anlage_id: int,
    jahr: Optional[int],
    monat: Optional[int],
    db: AsyncSession,
    *,
    kontext: Optional[MonatsKontext] = None,
    ohne_vorjahr: bool = False,
) -> AktuellerMonatResponse:
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
    werden — bei Einspeisung und Netzbezug nur, wenn die 0 nicht geliefert
    ist (`netzfeld_ist_erfasst`, N-734: ohne Herkunftseintrag). Begründung im
    Docstring dort.

    ⭐ **Eine gemessene 0 der Quellen HA-Statistik und Tagesebene ist ein Wert**
    (N-585, ``KONZEPT-UNVOLLSTAENDIGE-WERTE.md`` §3) — für Einspeisung,
    Netzbezug und den Anlagen-PV-Zähler, bei der HA-Statistik auch für die
    Gerätefelder von Speicher, Balkonkraftwerk, Wallbox und E-Auto. Gemessen
    heißt: mindestens ein Intervall (HA) bzw. eine Stunde mit Wert (Tagesebene).
    Ein autarker Monat zeigt damit Netzbezug 0, Autarkie 100 % und eine
    Stromrechnung von 0,00 € statt „kein Wert"; ein Feld ohne Messung bleibt
    ``None`` mit Grund. Wärmepumpe und PV-String bleiben bei „über 0"
    (Begründung an ``_NULL_IST_MESSWERT_TYPEN``).

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
    # RF-12 (Serie „Funktion vor Datei"): die verzweigten Abschnitte Kopf, Quellen und Übersicht stehen als Phasen unter
    # dieser Funktion. Die Vorlage-2-Phasen binden jeden ihrer Rückgabe-Namen auf jedem Weg — ausgepackt wird deshalb
    # ohne `if … in _out`; die eine Ausnahme ist `speicher_ersparnis` aus dem T-Konto (nur mit Speicher-Zeile).
    _out = await _kopf_des_monats(db, anlage_id, jahr, monat)
    anlage = _out["anlage"]
    jahr = _out["jahr"]
    monat = _out["monat"]
    now = _out["now"]
    ist_aktueller_monat = _out["ist_aktueller_monat"]
    fenster = _out["fenster"]
    investitionen = _out["investitionen"]
    _out = await _quellen_des_monats(db, anlage, anlage_id, investitionen, jahr, monat, ist_aktueller_monat, kontext)
    kontext = _out["kontext"]
    monats_fakt = _out["monats_fakt"]
    saved = _out["saved"]
    connector = _out["connector"]
    mqtt_energy = _out["mqtt_energy"]
    ha_stats = _out["ha_stats"]
    _emob_kanal = _out["_emob_kanal"]
    _sonstiges_kanal = _out["_sonstiges_kanal"]
    _wp_kanal = _out["_wp_kanal"]
    _wp_kanal_zeilen = _out["_wp_kanal_zeilen"]
    ha_felder_mit_daten = _out["ha_felder_mit_daten"]
    _tages_wp_mengen = _out["_tages_wp_mengen"]
    tagesebene = _out["tagesebene"]
    resolved = _out["resolved"]
    teilzeitraum = _out["teilzeitraum"]

    # ── aggregiere_typen (Vorlage 2: Abschnitt in aggregation.py, Schnittstelle 5 ein / 1 aus) ──
    _out = aggregiere_typen(investitionen=investitionen, jahr=jahr, monat=monat, resolved=resolved, teilzeitraum=teilzeitraum)
    direct_fields = _out["direct_fields"]
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
        # N-555 Stufe 3: die geltenden Ladeblöcke des Monats (W-C geprüft) — dieselbe
        # Messung je Auto wie in den Monats-Fakten, auch wenn hier entschieden wird.
        bloecke=await _emob_bloecke_des_monats(db, anlage.id, investitionen, jahr, monat),
        # HA-Bauform E4c (N-631): der PV-Anteil aus dem abgeleiteten Kanal, wenn die E-Mob-Gruppe den Monat deckt.
        kanal_quote=_emob_kanal,
    )
    emob_entscheid = _out.get("emob_entscheid")
    # HA-Bauform E4d: die gemessene WP-0 der Monatszeile als letzte Quelle (Docstring dort).
    _wp_gemessene_null_aus_fakt(resolved, monats_fakt)
    # ── extrahiere_werte (Vorlage 2: Abschnitt in aggregation.py, Schnittstelle 2 ein / 10 aus) ──
    _out = extrahiere_werte(monats_fakt=monats_fakt, resolved=resolved)
    abgabe_dritte = _out["abgabe_dritte"]
    einspeisung = _out["einspeisung"]
    erzeugung_bilanz = _out["erzeugung_bilanz"]
    get_val = _out["get_val"]
    hinweise = _out["hinweise"]
    # N-726: ein Basis-Zähler aus der Tagesebene, der nur einen Teil der Tage misst, sagt es (P4).
    hinweise = [*hinweise, *_tagesebene_teilwert_hinweise(resolved, tagesebene)]
    netzbezug = _out["netzbezug"]
    pv = _out["pv"]
    sonstiges_erz_bilanz = _out["sonstiges_erz_bilanz"]
    speicher_entladung = _out["speicher_entladung"]
    speicher_ladung = _out["speicher_ladung"]
    # ── berechne_bilanzwerte (Vorlage 2: Abschnitt in aggregation.py, Schnittstelle 8 ein / 5 aus) ──
    _out = berechne_bilanzwerte(abgabe_dritte=abgabe_dritte, einspeisung=einspeisung, erzeugung_bilanz=erzeugung_bilanz, netzbezug=netzbezug, pv=pv, sonstiges_erz_bilanz=sonstiges_erz_bilanz, speicher_entladung=speicher_entladung, speicher_ladung=speicher_ladung, v2h_entladung=(monats_fakt.emob.v2h_entladung_kwh if monats_fakt is not None else 0.0))
    autarkie = _out["autarkie"]
    direktverbrauch = _out["direktverbrauch"]
    eigenverbrauch = _out["eigenverbrauch"]
    ev_quote = _out["ev_quote"]
    gesamtverbrauch = _out["gesamtverbrauch"]
    # N-588: Wandlungsverluste VOR den Finanzen — Ersparnis und USt bewerten den Eigenverbrauch ohne sie, wenn der
    # Messpunkt-Vertrag hält (`eigenverbrauch_ohne_verluste_kwh`, P15); die Bilanz oben bleibt.
    _verluste, _verluste_bezug, _verluste_grund = await _wandlungsverluste_des_monats(
        db, anlage_id, jahr, monat, monats_fakt)
    eigenverbrauch_ohne_verluste = (
        None if eigenverbrauch is None
        else eigenverbrauch_ohne_verluste_kwh(eigenverbrauch, _verluste, _verluste_grund)
    )
    # ── finanzen_des_monats (Vorlage 2: Abschnitt in finanzen.py, Schnittstelle 8 ein / 19 aus) ──
    _out = await finanzen_des_monats(_zt_cache=_zt_cache, anlage_id=anlage_id, db=db, eigenverbrauch=eigenverbrauch_ohne_verluste, einspeisung=einspeisung, jahr=jahr, monat=monat, netzbezug=netzbezug)
    allgemein_tarif = _out["allgemein_tarif"]
    einspeise_cent = _out["einspeise_cent"]
    einspeise_erloes = _out["einspeise_erloes"]
    einspeisung_neg_preis = _out["einspeisung_neg_preis"]
    ev_ersparnis = _out["ev_ersparnis"]
    grundgebuehr = _out["grundgebuehr"]
    monats_benzinpreis = _out["monats_benzinpreis"]
    monats_gaspreis = _out["monats_gaspreis"]
    netzbezug_arbeitspreis_kosten = _out["netzbezug_arbeitspreis_kosten"]
    netzbezug_durchschnittspreis = _out["netzbezug_durchschnittspreis"]
    netzbezug_kosten = _out["netzbezug_kosten"]
    netzbezug_preis_abdeckung = _out["netzbezug_preis_abdeckung"]
    netzbezug_preis_cent = _out["netzbezug_preis_cent"]
    netzbezug_preis_effektiv_cent = _out["netzbezug_preis_effektiv_cent"]
    netzbezug_preis_herkunft = _out["netzbezug_preis_herkunft"]
    ev_preis_cent = _out.get("ev_preis_cent")
    ev_preis_herkunft = _out.get("ev_preis_herkunft")
    nicht_vergueteter_erloes = _out["nicht_vergueteter_erloes"]
    tarife = _out["tarife"]
    zaehlergebuehr_jahr = _out["zaehlergebuehr_jahr"]
    # ── komponenten_ersparnis (Vorlage 2: Abschnitt in finanzen.py, Schnittstelle 1 ein / 5 aus) ──
    _out = komponenten_ersparnis(get_val=get_val)
    emob_ersparnis = _out["emob_ersparnis"]
    wp_ersparnis = _out["wp_ersparnis"]
    wp_ersparnis_berechnung_text = _out["wp_ersparnis_berechnung_text"]
    wp_strom = _out["wp_strom"]
    wp_waerme = _out["wp_waerme"]
    # ── waerme_klima_monat (Vorlage 2: Abschnitt in waerme.py, Schnittstelle 16 ein / 10 aus) ──
    _out = await waerme_klima_monat(resolved=resolved, _tages_wp_mengen=_tages_wp_mengen, kanal_wp_zeilen=_wp_kanal_zeilen, _zt_cache=_zt_cache, allgemein_tarif=allgemein_tarif, anlage_id=anlage_id, db=db, get_val=get_val, investitionen=investitionen, jahr=jahr, monat=monat, monats_fakt=_wp_sicht(monats_fakt, _wp_kanal), monats_gaspreis=monats_gaspreis, netzbezug_preis_effektiv_cent=netzbezug_preis_effektiv_cent, tarife=tarife, teilzeitraum=teilzeitraum, wp_strom=wp_strom, wp_waerme=wp_waerme)
    _wp_abgrenzung_je_funktion = _out["_wp_abgrenzung_je_funktion"]
    _wp_funktion = _out["_wp_funktion"]
    _wp_kennzahlen_je_geraet = _out["_wp_kennzahlen_je_geraet"]
    wp_abgrenzung_verletzt = _out["wp_abgrenzung_verletzt"]
    wp_arbeitszahl = _out["wp_arbeitszahl"]
    wp_ersparnis = _out["wp_ersparnis"]
    wp_ersparnis_berechnung_text = _out["wp_ersparnis_berechnung_text"]
    wp_ersparnis_vorbehalt = _out["wp_ersparnis_vorbehalt"]
    wp_waerme_abgeleitet_kwh = _out["wp_waerme_abgeleitet_kwh"]
    wp_waerme_herkunft = _out["wp_waerme_herkunft"]
    # ── betriebskosten_und_sonstige_positionen (Vorlage 2: Abschnitt in finanzen.py, Schnittstelle 2 ein / 9 aus) ──
    _out = betriebskosten_und_sonstige_positionen(investitionen=investitionen, monats_fakt=monats_fakt, jahr=jahr, monat=monat)
    anlage_sonstige_ausgaben = _out["anlage_sonstige_ausgaben"]
    anlage_sonstige_ertraege = _out["anlage_sonstige_ertraege"]
    betriebskosten_anteilig = _out["betriebskosten_anteilig"]
    betriebskosten_anteilig_anzahl = _out["betriebskosten_anteilig_anzahl"]
    betriebskosten_anteilig_jahr = _out["betriebskosten_anteilig_jahr"]
    sonstige_ausgaben_total = _out["sonstige_ausgaben_total"]
    sonstige_ertraege_total = _out["sonstige_ertraege_total"]
    sonstige_netto_total = _out["sonstige_netto_total"]
    # ── komponenten_detail (Vorlage 2: Abschnitt in komponenten.py, Schnittstelle 15 ein / 33 aus) ──
    _out = await komponenten_detail(_wp_abgrenzung_je_funktion=_wp_abgrenzung_je_funktion, _wp_funktion=_wp_funktion, _wp_kennzahlen_je_geraet=_wp_kennzahlen_je_geraet, anlage_id=anlage_id, db=db, fenster=fenster, investitionen=investitionen, jahr=jahr, monat=monat, monats_fakt=monats_fakt, wp_fakten=_wp_kanal, speicher_entladung=speicher_entladung, speicher_ladung=speicher_ladung, wp_abgrenzung_verletzt=wp_abgrenzung_verletzt, wp_arbeitszahl=wp_arbeitszahl, wp_waerme_abgeleitet_kwh=wp_waerme_abgeleitet_kwh, anlage=anlage, ist_aktueller_monat=ist_aktueller_monat, heute=now.date())
    mf_bkw = _out["mf_bkw"]
    mf_emob = _out["mf_emob"]
    mf_sonstiges = _out["mf_sonstiges"]
    if _sonstiges_kanal is not None:
        mf_sonstiges = _sonstiges_kanal      # E4c: der Monat ohne Sonstiges-Zeile aus den Kanälen
    mf_wp = _out["mf_wp"]
    speicher_auslastung = _out["speicher_auslastung"]
    speicher_auslastungs_basis = _out["speicher_auslastungs_basis"]
    speicher_eff_ladepreis = _out["speicher_eff_ladepreis"]
    speicher_eff_ladepreis_quelle = _out["speicher_eff_ladepreis_quelle"]
    speicher_ersparnis = _out["speicher_ersparnis"]
    speicher_imd_ladepreis = _out["speicher_imd_ladepreis"]
    speicher_kapazitaet = _out["speicher_kapazitaet"]
    speicher_ladung_netz = _out["speicher_ladung_netz"]
    speicher_ladung_netz_herkunft = _out["speicher_ladung_netz_herkunft"]
    speicher_soc_drift_flag = _out["speicher_soc_drift_flag"]
    speicher_vollzyklen = _out["speicher_vollzyklen"]
    speicher_wirkungsgrad = _out["speicher_wirkungsgrad"]
    speicher_wirkungsgrad_quelle = _out["speicher_wirkungsgrad_quelle"]
    wp_az_funktion = _out["wp_az_funktion"]
    wp_az_kuehlen = _out["wp_az_kuehlen"]
    wp_heizung = _out["wp_heizung"]
    wp_modus_abdeckung = _out["wp_modus_abdeckung"]
    wp_modus_bezug = _out["wp_modus_bezug"]
    wp_modus_entfeuchten = _out["wp_modus_entfeuchten"]
    wp_modus_gemessen = _out["wp_modus_gemessen"]
    wp_modus_heizen = _out["wp_modus_heizen"]
    wp_modus_kuehlen = _out["wp_modus_kuehlen"]
    wp_modus_lueften = _out["wp_modus_lueften"]
    wp_modus_rest = _out["wp_modus_rest"]
    wp_modus_warmwasser = _out["wp_modus_warmwasser"]
    wp_nutz_entfeuchten = _out["wp_nutz_entfeuchten"]
    wp_nutz_lueften = _out["wp_nutz_lueften"]
    wp_strom_heizen = _out["wp_strom_heizen"]
    wp_strom_warmwasser = _out["wp_strom_warmwasser"]
    wp_warmwasser = _out["wp_warmwasser"]
    # ── geraete_sicht (Vorlage 2: Abschnitt in komponenten.py, Schnittstelle 13 ein / 15 aus) ──
    _out = geraete_sicht(_wp_kennzahlen_je_geraet=_wp_kennzahlen_je_geraet, emob_entscheid=emob_entscheid, get_val=get_val, investitionen=investitionen, mf_bkw=mf_bkw, mf_emob=mf_emob, mf_sonstiges=mf_sonstiges, netzbezug_preis_effektiv_cent=netzbezug_preis_effektiv_cent, speicher_eff_ladepreis=speicher_eff_ladepreis, speicher_imd_ladepreis=speicher_imd_ladepreis, speicher_ladung_netz=speicher_ladung_netz, wp_arbeitszahl=wp_arbeitszahl, wp_az_funktion=wp_az_funktion, wp_az_kuehlen=wp_az_kuehlen)
    bkw_eigenverbrauch = _out["bkw_eigenverbrauch"]
    emob_ladung_extern = _out["emob_ladung_extern"]
    emob_ladung_netz = _out["emob_ladung_netz"]
    emob_pv = _out["emob_pv"]
    emob_v2h = _out["emob_v2h"]
    netzladung_kosten = _out["netzladung_kosten"]
    sonstiges_bezug_netz = _out["sonstiges_bezug_netz"]
    sonstiges_bezug_pv = _out["sonstiges_bezug_pv"]
    sonstiges_eigenverbrauch = _out["sonstiges_eigenverbrauch"]
    sonstiges_einspeisung = _out["sonstiges_einspeisung"]
    sonstiges_erzeugung = _out["sonstiges_erzeugung"]
    sonstiges_geraete = _out["sonstiges_geraete"]
    sonstiges_verbrauch = _out["sonstiges_verbrauch"]
    wp_block_geraete = _out["wp_block_geraete"]
    wp_block_moeglich = _out["wp_block_moeglich"]
    # ── flags_und_wp_counter (Vorlage 2: Abschnitt in waerme.py, Schnittstelle 5 ein / 9 aus) ──
    _out = await flags_und_wp_counter(anlage_id=anlage_id, db=db, investitionen=investitionen, jahr=jahr, monat=monat)
    hat_balkonkraftwerk = _out["hat_balkonkraftwerk"]
    hat_emobilitaet = _out["hat_emobilitaet"]
    hat_sonstiges = _out["hat_sonstiges"]
    hat_speicher = _out["hat_speicher"]
    hat_waermepumpe = _out["hat_waermepumpe"]
    wp_betriebsstunden_max_tag = _out["wp_betriebsstunden_max_tag"]
    wp_betriebsstunden_summe_monat = _out["wp_betriebsstunden_summe_monat"]
    wp_starts_max_tag = _out["wp_starts_max_tag"]
    wp_starts_summe_monat = _out["wp_starts_summe_monat"]
    # ── Vergleichsdaten ──
    # N-610 (03.10.2026): der Vorjahresmonat ist derselbe Monat, über diese Funktion gerechnet (`_load_vorjahr` ruft
    # `_berechne_monat(jahr−1, ohne_vorjahr=True)`). `ohne_vorjahr` schneidet die Rekursion ab und spart der Jahresroute
    # zwölf Vorjahresmonate, die sie nicht braucht.
    vorjahr = None if ohne_vorjahr else await _load_vorjahr(
        anlage_id, investitionen, jahr, monat, db,
        fakt=kontext.fakten.get((jahr - 1, monat)), ust_satz=kontext.ust_satz_vj,
        tarif_cache=kontext.tarif_cache, kontext=kontext, hinweise=hinweise,
    )
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

    _out = _uebersicht_des_monats(
        saved=saved, connector=connector, mqtt_energy=mqtt_energy, ha_stats=ha_stats, tagesebene=tagesebene,
        ist_aktueller_monat=ist_aktueller_monat, resolved=resolved, get_val=get_val, investitionen=investitionen,
        jahr=jahr, monat=monat,
    )
    quellen = _out["quellen"]
    datenlage_gruende = _out["datenlage_gruende"]
    feld_quellen = _out["feld_quellen"]
    komponenten_geraete = _out["komponenten_geraete"]

    # ── t_konto_je_investition (Vorlage 2: Abschnitt in finanzen.py, Schnittstelle 12 ein / 2 aus) ──
    _out = await t_konto_je_investition(monats_fakt=monats_fakt, _zt_cache=_zt_cache, allgemein_tarif=allgemein_tarif, anlage_id=anlage_id, db=db, einspeise_cent=einspeise_cent, investitionen=investitionen, jahr=jahr, monat=monat, monats_benzinpreis=monats_benzinpreis, monats_gaspreis=monats_gaspreis, netzbezug_preis_effektiv_cent=netzbezug_preis_effektiv_cent, tarife=tarife, ev_preis_cent=ev_preis_cent)
    investitionen_financials = _out["investitionen_financials"]
    if "speicher_ersparnis" in _out: speicher_ersparnis = _out["speicher_ersparnis"]
    # N-605: WP-Ersparnis = Σ der WP-Zeilen des T-Kontos (Bauform G20-2), vor Kachel und Ergebnis-Leiter.
    wp_ersparnis, wp_ersparnis_berechnung_text = wp_aggregat_aus_zeilen(
        investitionen_financials, wp_ersparnis, wp_ersparnis_berechnung_text,
    )
    # ── emob_aggregat_und_kennzahlen (Vorlage 2: Abschnitt in finanzen.py, Schnittstelle 12 ein / 4 aus) ──
    _out = emob_aggregat_und_kennzahlen(anlage=anlage, emob_ladung_extern=emob_ladung_extern, einspeise_erloes=einspeise_erloes, emob_ersparnis=emob_ersparnis, ev_ersparnis=ev_ersparnis, get_val=get_val, investitionen=investitionen, investitionen_financials=investitionen_financials, jahr=jahr, monat=monat, netzbezug_kosten=netzbezug_kosten, pv=pv, wp_ersparnis=wp_ersparnis)
    emob_eff = _out["emob_eff"]
    emob_ladung_gesamt = _out["emob_ladung_gesamt"]
    emob_ersparnis_berechnung = _out.get("emob_ersparnis_berechnung")
    emob_ersparnis = _out["emob_ersparnis"]
    spez_ertrag = _out["spez_ertrag"]
    # ── Ergebnis-Leiter (Paket „Ergebnisgrößen", 03.10.2026): Netto-Ertrag, Ergebnis, Herleitung aus dem Layer ──
    # HA-Bauform E4e (N-633): ohne Monats-Fakt die dienstlichen Ladekosten wie die Fakten — Mengen der Entscheidung oben,
    # Tarif und Bewertung der Schicht.
    _dienstlich = (
        await dienstliche_ladung_ohne_fakt(db=db, anlage_id=anlage_id, jahr=jahr, monat=monat,
                                           emob_entscheid=emob_entscheid)
        if monats_fakt is None else None
    )
    _erg = ergebnis_des_monats(
        # N-588 (F4): die USt bemisst den Eigenverbrauch ohne Wandlungsverluste — dieselbe Menge wie die Ersparnis.
        eigenverbrauch=eigenverbrauch_ohne_verluste, einspeise_erloes=einspeise_erloes, ev_ersparnis=ev_ersparnis,
        monats_fakt=monats_fakt, ev_preis_cent=ev_preis_cent,
        sonstige_netto=sonstige_netto_total, wp_ersparnis=wp_ersparnis, emob_ersparnis=emob_ersparnis,
        netzbezug_kosten=netzbezug_kosten, betriebskosten=betriebskosten_anteilig, ust_satz=kontext.ust_satz,
        hat_waermepumpe=hat_waermepumpe, hat_emobilitaet=hat_emobilitaet, dienstlich_ohne_fakt=_dienstlich,
    )
    # SOLL-Erfüllung aus dem Layer (N-356) — aus genau den Werten, die die Antwort trägt.
    _soll_pv_tage = fenster.tage if soll_pv.anteilig is not None else None
    _soll_pv_tage_gesamt = fenster.tage_gesamt if soll_pv.anteilig is not None else None
    _soll = soll_erfuellung(pv, soll_pv.anteilig, _soll_pv_tage, _soll_pv_tage_gesamt, soll_pv.monat)
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
        wandlungsverluste_kwh=_verluste,
        wandlungsverluste_bezug_kwh=_verluste_bezug,
        wandlungsverluste_prozent=wandlungsverluste_prozent(_verluste, _verluste_bezug),
        eigenverbrauch_ohne_verluste_kwh=eigenverbrauch_ohne_verluste,
        verluste_grund=_verluste_grund,
        autarkie_prozent=autarkie,
        eigenverbrauch_quote_prozent=ev_quote,
        spez_ertrag=round(spez_ertrag, 1) if spez_ertrag is not None else None,
        # Komponenten — Speicher
        speicher_ladung_kwh=speicher_ladung,
        speicher_entladung_kwh=speicher_entladung,
        speicher_ladung_netz_kwh=speicher_ladung_netz,
        speicher_ladung_netz_herkunft=speicher_ladung_netz_herkunft,
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
        netto_ertrag_euro=_erg["netto_ertrag"],
        ust_eigenverbrauch_euro=_erg["ust_anteil"],
        ust_herleitung=_erg["ust_herleitung"],
        bkw_ersparnis_euro=_erg["bkw_ersparnis"],
        bkw_ersparnis_berechnung=_erg["bkw_ersparnis_berechnung"],
        erzeuger_erloes_euro=_erg["erzeuger_erloes"],
        dienstliche_ladekosten_euro=_erg["dienstliche_ladekosten"],
        dienstliche_ladekosten_berechnung=_erg["dienstliche_ladekosten_berechnung"],
        ergebnis_vor_betriebskosten_euro=_erg["ergebnis_vor_betriebskosten"],
        ergebnis_euro=_erg["ergebnis"],
        ergebnis_herleitung=_erg["ergebnis_herleitung"],
        fehlende_posten=_erg["fehlende_posten"],
        wp_ersparnis_euro=wp_ersparnis,
        emob_ersparnis_euro=emob_ersparnis,
        emob_ersparnis_berechnung=emob_ersparnis_berechnung,
        sonstige_ertraege_euro=sonstige_ertraege_total,
        sonstige_ausgaben_euro=sonstige_ausgaben_total,
        sonstige_netto_euro=sonstige_netto_total,
        anlage_sonstige_ertraege_euro=anlage_sonstige_ertraege,
        anlage_sonstige_ausgaben_euro=anlage_sonstige_ausgaben,
        betriebskosten_anteilig_euro=betriebskosten_anteilig,
        betriebskosten_anteilig_jahr_euro=betriebskosten_anteilig_jahr,
        betriebskosten_anteilig_anzahl=betriebskosten_anteilig_anzahl,
        # Tarif-Info
        # N-712: auch ohne Tarif zum Stichtag — dann die Vorbelegung, mit der der Monat rechnet (Herkunft `vorbelegung`).
        netzbezug_preis_cent=netzbezug_preis_cent,
        # Der Wert zu `_herkunft`/`_abdeckung` — ohne ihn beschreiben die beiden
        # eine Zahl, die die Antwort nicht enthält (SOLL Flex-Tarife H-2).
        netzbezug_preis_effektiv_cent=netzbezug_preis_effektiv_cent,
        netzbezug_preis_herkunft=netzbezug_preis_herkunft,
        ev_preis_cent=ev_preis_cent,
        ev_preis_herkunft=ev_preis_herkunft,
        netzbezug_preis_abdeckung=netzbezug_preis_abdeckung,
        # N-267: sagt der Anzeige, dass der Preis daneben gewichtet ist.
        netzbezug_preis_zeittarif=hat_zeitfenster(allgemein_tarif),
        einspeise_preis_cent=einspeise_cent,
        netzbezug_durchschnittspreis_cent=netzbezug_durchschnittspreis,
        # N-610: bis dahin nur im Vorjahres-Block — der gepflegte Monatswert (#392), NICHT der aufgelöste Satz
        # `einspeise_preis_cent` (Gegenstück zu `netzbezug_durchschnittspreis_cent` neben `netzbezug_preis_cent`).
        einspeise_durchschnittspreis_cent=(
            monats_fakt.meta.monatsdaten.einspeise_durchschnittspreis_cent
            if monats_fakt is not None and monats_fakt.meta.monatsdaten is not None else None
        ),
        grundgebuehr_euro=grundgebuehr,
        zaehlergebuehr_euro_jahr=zaehlergebuehr_jahr,
        # Vergleiche
        vorjahr=vorjahr,
        soll_pv_kwh=soll_pv.anteilig,
        soll_pv_tage=_soll_pv_tage,
        soll_pv_tage_gesamt=_soll_pv_tage_gesamt,
        soll_pv_kwh_monat=soll_pv.monat,
        soll_erfuellung_prozent=_soll.prozent,
        soll_erfuellung_monat_prozent=_soll.monat_prozent,
        soll_fenster_text=_soll.fenster_text,
        grundlast_kw=grundlast.grundlast_kw,
        grundlast_kwh=grundlast.grundlast_kwh,
        grundlast_anteil_prozent=grundlast.grundlast_anteil_prozent,
        # Per-Investition Finanzdetails
        investitionen_financials=investitionen_financials,
        komponenten_geraete=komponenten_geraete,
        # Quellen
        feld_quellen=feld_quellen,
    )


async def _kopf_des_monats(
    db: AsyncSession, anlage_id: int, jahr: Optional[int], monat: Optional[int],
) -> dict:
    """RF-12 — Kopf von ``_berechne_monat``: die Anlage mit Investitionen (sonst ``not_found``), der Monat (ohne Angabe
    der laufende), ob er läuft, sein gemessenes Fenster und die aktiven Investitionen.

    Steht in dieser Datei, weil die Tests die Uhr an diesem Modul tauschen (``datetime``, Modul-Docstring)."""
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
    return {
        "anlage": anlage, "jahr": jahr, "monat": monat, "now": now, "ist_aktueller_monat": ist_aktueller_monat,
        "fenster": fenster, "investitionen": investitionen,
    }


def _herkunft_lokal() -> DatenquelleInfo:
    """Die Herkunft der Kanal-Gruppen ohne antwortende HA-Statistik: die lokalen Daten (N-750, N-758) — dieselbe Marke
    wie die fünfte Quelle (``tagesebene``, 80 %). Steht hier, weil sie die Uhr liest (Modul-Docstring)."""
    return DatenquelleInfo(quelle="tagesebene", konfidenz=80, zeitpunkt=datetime.now().isoformat())


async def _summen_der_tagesebene(
    db: AsyncSession, anlage_id: int, jahr: int, monat: int, *, ist_aktueller_monat: bool, ha_geliefert: bool,
) -> Optional[dict]:
    """Gilt die fünfte Quelle (N-472) für diesen Monat — und wenn ja, ihre Summe (``lade_monats_summen``, Weg 2).

    Im **laufenden** Monat immer (N-472, unverändert). ⭐ **N-758 (17.10.2026, Konzept R-11/E6):** in einem
    **vergangenen** Monat dann, wenn die HA-Statistik in dieser Anfrage nicht geliefert hat UND die Kanäle der
    Bilanz-Gruppe den Kalendermonat voll decken (``kanal_monate`` nennt ihn) — dieselbe Wahl wie die Monats-Fakten
    (``monats_fakten/laden.py``), also auch für eine Anlage ohne HA-Zuordnung (Eigene Summe aus MQTT). Die Begründung
    von N-472 („in einem abgeschlossenen Monat wäre eine Teilmenge der Tage eine stille Untertreibung") trägt dort
    nicht: ein voll gedeckter Kanal-Monat ist EIN Δ über den ganzen Monat, keine Teilmenge. Ohne Deckung ``None`` —
    der Monat bleibt, wie er war (Antwort: der Monatsabschluss). Mit HA-Antwort ``None`` — der HA-Weg ersetzt die
    Bilanz-Gruppe schon aus den Kanälen (E4a-2)."""
    from backend.services.kanal.bilanz_leser import kanal_monate, lade_monats_summen

    m = (jahr, monat)
    if not ist_aktueller_monat and (ha_geliefert or m not in await kanal_monate(db, anlage_id, von=m, bis=m)):
        return None
    return await lade_monats_summen(db, anlage_id, von=m, bis=m)


async def _quellen_des_monats(
    db: AsyncSession, anlage: Anlage, anlage_id: int, investitionen: list[Investition], jahr: int, monat: int,
    ist_aktueller_monat: bool, kontext: Optional[MonatsKontext],
) -> dict:
    """RF-12 — die Quellen des Monats: Vorlade-Kontext und Monats-Fakt, die Sammler, die Kanal-Gruppen des HA-Wegs
    (E4a-2/E4c/E4d), die Heimlade-Felder (N-555), die Tagesebene (N-472), dann ``merge_datenquellen`` und die
    Teilzeitraum-Felder. Jede Entscheidung „nur im laufenden Monat" bzw. „nur im abgeschlossenen" steht hier.

    Steht in dieser Datei, weil die Tests die Sammler an diesem Modul tauschen (Modul-Docstring)."""
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
    #
    # Paket „Ergebnisgrößen" (03.10.2026, B2): EIN Fakten-Bereich `(jahr−1, 1)…(jahr, 12)` statt des einen Monats —
    # der USt-Anteil des Monats braucht den Satz des Jahres (E1/G1), der Vorjahresmonat den Satz SEINES Jahres (G5).
    # Die Jahresroute reicht den Kontext an alle zwölf Monate durch (`kontext.py`).
    if kontext is None or kontext.jahr != jahr:
        kontext = await lade_monats_kontext(db, anlage, jahr)
    monats_fakt = kontext.fakten.get((jahr, monat))

    saved = _collect_saved_data(monats_fakt)
    connector = await _collect_connector_data(anlage, jahr, monat)
    mqtt_energy = (
        await _collect_mqtt_inbound_data(db, anlage, investitionen, jahr, monat)
        if ist_aktueller_monat else {}
    )
    ha_stats = await _collect_ha_statistics_data(anlage, jahr, monat)
    ha_geliefert = bool(ha_stats)
    ha_stats, _bilanz_aus_kanaelen = await _ha_statistik_aus_kanaelen_mit_marke(
        db, anlage, investitionen, jahr, monat, ha_stats)
    # ⭐ N-750 (16.10.2026): die Kanal-Gruppen hängen an der Kanal-Deckung, nicht an der Antwort der HA-Statistik in
    # dieser Anfrage (ADR-002 P14, wie die Monats-Fakten). Ohne HA-Statistik tragen sie im LAUFENDEN Monat dieselbe
    # Präzedenz wie auf dem HA-Weg — sie stehen im Platz der HA-Statistik und überschreiben MQTT und die fünfte Quelle
    # für ihre Schlüssel (gemessen: MQTT trägt dieselben Schlüssel mit denselben Werten aus derselben Standreihe,
    # keine Addition; Bericht FUND-N750-N751 Etappe 1); die Herkunft ist die der lokalen Daten, die Marke
    # `quellen.ha_statistics` bleibt die des HA-Sammlers. Die Bilanz trägt dann die fünfte Quelle (`lade_monats_summen`,
    # Weg 2), und aus DERSELBEN Summe kommen die Sonstiges-Erzeuger (`sonstige_erzeuger_je_inv`).
    # ⭐ N-758 (17.10.2026): dasselbe für einen VERGANGENEN Monat ohne HA-Antwort, dessen Bilanz-Kanäle ihn voll decken
    # (`_summen_der_tagesebene`, Wahl der Monats-Fakten); ohne Deckung trägt dort weiter keine Quelle die Bilanz.
    _summen_laufend = await _summen_der_tagesebene(
        db, anlage_id, jahr, monat, ist_aktueller_monat=ist_aktueller_monat, ha_geliefert=ha_geliefert)
    _ohne_ha = _herkunft_lokal() if _summen_laufend is not None and not ha_geliefert else None
    _erzeuger_ohne_ha = (
        getattr(_summen_laufend.get((jahr, monat)), "sonstige_erzeuger_je_inv", None)
        if _ohne_ha is not None else None
    )
    # HA-Bauform E4c: E-Mob- und Sonstiges-Gruppe des Kalendermonats aus den Kanälen (Docstring dort).
    ha_stats, _emob_kanal, _sonstiges_kanal = await _geraete_aus_kanaelen(
        db, anlage, investitionen, jahr, monat, ha_stats,
        monats_fakt=monats_fakt, bilanz_ersetzt=_bilanz_aus_kanaelen,
        sonstige_erzeuger=_erzeuger_ohne_ha, ohne_ha=_ohne_ha,
    )
    # HA-Bauform E4d: die WP-Gruppe des Kalendermonats aus den Kanälen (Docstring dort, N-630).
    ha_stats, _wp_kanal, _wp_kanal_zeilen = await _wp_aus_kanaelen(
        db, anlage, investitionen, jahr, monat, ha_stats, monats_fakt=monats_fakt, ohne_ha=_ohne_ha,
    )
    # N-555: welche Heimlade-Felder hat die HA-Statistik in einem ABGESCHLOSSENEN
    # Monat überhaupt (auch mit 0)? Im laufenden Monat genügt die Quelle.
    ha_felder_mit_daten: set[str] = (
        await _ha_heimlade_felder_mit_daten(anlage, investitionen, jahr, monat)
        if not ist_aktueller_monat else set()
    )
    # Fünfte Quelle (N-472) — im laufenden Monat (seit N-758 auch im vergangenen voll gedeckten Kanal-Monat ohne
    # HA-Antwort, `_summen_der_tagesebene`; der Absatz hier begründet den laufenden), und das ist eine Aussage
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
            abgetretene_bkw=abgetretene_bkw_ids([
                i for i in investitionen
                if i.typ in ("pv-module", "balkonkraftwerk") and i.ist_aktiv_im_monat(jahr, monat)
            ]),
            summen=_summen_laufend,
        )
        if _summen_laufend is not None else {}
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
    return {
        "kontext": kontext, "monats_fakt": monats_fakt, "saved": saved, "connector": connector,
        # N-750: für die Quellen-Übersicht nur, was die HA-Statistik geliefert hat (ohne sie: die Kanal-Gruppen allein).
        "mqtt_energy": mqtt_energy, "ha_stats": ha_stats if ha_geliefert else {}, "_emob_kanal": _emob_kanal,
        "_sonstiges_kanal": _sonstiges_kanal, "_wp_kanal": _wp_kanal, "_wp_kanal_zeilen": _wp_kanal_zeilen,
        "ha_felder_mit_daten": ha_felder_mit_daten, "_tages_wp_mengen": _tages_wp_mengen, "tagesebene": tagesebene,
        "resolved": resolved, "teilzeitraum": teilzeitraum,
    }


def _uebersicht_des_monats(
    *, saved, connector, mqtt_energy, ha_stats, tagesebene, ist_aktueller_monat: bool, resolved, get_val,
    investitionen: list[Investition], jahr: int, monat: int,
) -> dict:
    """RF-12 — die Begleitangaben der Antwort: welche Quelle geliefert hat, der Grund statt Leere (N-472), die Herkunft
    je Feld und die aktiven Geräte je Typ. Rechnet keine Größe."""
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
    return {
        "quellen": quellen, "datenlage_gruende": datenlage_gruende, "feld_quellen": feld_quellen,
        "komponenten_geraete": komponenten_geraete,
    }
