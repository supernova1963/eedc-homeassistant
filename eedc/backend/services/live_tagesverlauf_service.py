"""
Tagesverlauf-Service — stündlich aggregierte Leistungsdaten für Butterfly-Chart.

Ausgelagert aus live_power_service.py (Schritt 5 des Refactorings).
"""

import logging
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.config import HA_INTEGRATION_AVAILABLE
from backend.models.anlage import Anlage
from backend.models.investition import Investition
from backend.utils.investition_filter import aktiv_jetzt
from backend.services.live_sensor_config import (
    ERZEUGER_TYPEN,
    SKIP_TYPEN,
    TV_SERIE_CONFIG,
    UNIT_TO_W,
    baue_investitions_serien,
    extract_live_config,
)
from backend.services.live_history_service import (
    _MONATSABSCHLUSS_KWH,
    _feld_eid,
    get_history_normalized,
    apply_invert_to_history,
)

logger = logging.getLogger(__name__)


def _resolve_counter_eid(
    typ: str, suffix: Optional[str], felder: dict,
) -> Optional[str]:
    """kWh-Zähler-Entity einer Investitions-Serie — deckungsgleich mit der
    Bevorzugung in ``get_tages_kwh`` (Kacheln).

    PV/BKW → ``pv_erzeugung_kwh``; WP → ``stromverbrauch_kwh``; Wallbox →
    ``ladung_kwh`` (via ``_MONATSABSCHLUSS_KWH``). WP-Split-Serien (``suffix``
    Heizen/Warmwasser) haben keinen eigenen kWh-Zähler → None (Mean-Pfad).
    Speicher ist bidirektional → bewusst kein Zähler-Pfad (None → Mean, mit
    erhaltenem Vorzeichen).
    """
    if typ in ERZEUGER_TYPEN:
        return _feld_eid(felder.get("pv_erzeugung_kwh", {}))
    if suffix is None and typ in _MONATSABSCHLUSS_KWH:
        field, _ = _MONATSABSCHLUSS_KWH[typ]
        return _feld_eid(felder.get(field, {}))
    return None


def _baue_short_term_overlays(
    anlage: Anlage,
    serien_core: list,
    serie_entities: dict[str, list[str]],
    investitionen: dict,
    pv_gesamt_eid: Optional[str],
    netz_bezug_eid: Optional[str],
    netz_einspeisung_eid: Optional[str],
    netz_kombi_eid: Optional[str],
    start: datetime,
    end: datetime,
    history: dict[str, list],
) -> tuple[dict[str, list], dict[str, list]]:
    """Baut die `statistics_short_term`-Overlays für die Add-on-Kurve.

    Pro Serie wird der Punkt-Strom unter ihrer **Power-Entity** (dem Schlüssel,
    den die Slot-Schleife liest) ersetzt durch:
      - **counter_overlay** (kWh-Zähler vorhanden): 5-Min-`sum`-Deltas → positive
        Leistung. Vorzeichenlos (Richtung kommt aus ``seite``/Netz-Logik) →
        wird NACH ``apply_invert`` eingespielt.
      - **mean_overlay** (nur Power-Sensor): `short_term.mean` → W. Gleiche
        Roh-Sensor-Semantik wie die History → wird VOR ``apply_invert``
        eingespielt (Invert gilt, Vorzeichen bleibt erhalten — wichtig für
        Speicher/Netz-Kombi).

    Liefert eine Serie keine short_term-Daten, fehlt ihre Power-Entity in beiden
    Overlays → die rohe History bleibt stehen (daten-getriebener Fallback, kein
    Feature-Flag).
    """
    from backend.services.ha_statistics_service import get_ha_statistics_service
    from backend.core.berechnungen.live_tagesverlauf_5min import (
        kurven_leistung_mit_live_fallback,
        means_zu_leistung,
    )

    stats = get_ha_statistics_service()
    if not stats.is_available:
        return {}, {}

    mapping = anlage.sensor_mapping or {}
    mapping_inv = mapping.get("investitionen", {})
    basis_map = mapping.get("basis", {})

    counter_src: dict[str, str] = {}  # power_eid → kWh-Zähler-eid
    mean_src: dict[str, str] = {}     # power_eid → power_eid (self)

    for spec in serien_core:
        eids = serie_entities.get(spec.key, [])
        if not eids:
            continue
        power_eid = eids[0]
        inv = investitionen.get(spec.inv_id)
        if inv is None:
            continue
        felder = (mapping_inv.get(spec.inv_id, {}) or {}).get("felder", {}) or {}
        counter_eid = _resolve_counter_eid(inv.typ, spec.suffix, felder)
        if counter_eid:
            counter_src[power_eid] = counter_eid
        else:
            mean_src.setdefault(power_eid, power_eid)

    # PV-Gesamt (Basis-Fallback, kein kWh-Zähler) → Mean.
    if pv_gesamt_eid:
        mean_src.setdefault(pv_gesamt_eid, pv_gesamt_eid)

    # Netz: getrennte kWh-Zähler bevorzugen (deckungsgleich mit get_tages_kwh),
    # sonst Mean des Power-Sensors. Kombi-Sensor ist bidirektional → Mean.
    if netz_bezug_eid:
        c = _feld_eid(basis_map.get("netzbezug", {}))
        if c:
            counter_src[netz_bezug_eid] = c
        else:
            mean_src.setdefault(netz_bezug_eid, netz_bezug_eid)
    if netz_einspeisung_eid:
        c = _feld_eid(basis_map.get("einspeisung", {}))
        if c:
            counter_src[netz_einspeisung_eid] = c
        else:
            mean_src.setdefault(netz_einspeisung_eid, netz_einspeisung_eid)
    if netz_kombi_eid:
        mean_src.setdefault(netz_kombi_eid, netz_kombi_eid)

    query_ids = list(set(list(counter_src.values()) + list(mean_src.values())))
    if not query_ids:
        return {}, {}

    try:
        st = stats.get_short_term_5min_for_day(query_ids, start.date(), bis=end)
    except Exception as e:  # pragma: no cover — defensiv, Fallback = rohe History
        logger.debug("short_term-Overlay übersprungen: %s", e)
        return {}, {}

    counter_overlay: dict[str, list] = {}
    grob_log: dict[str, int] = {}  # power_eid → Anzahl grober Stunden (Diagnose)
    for power_eid, counter_eid in counter_src.items():
        data = st.get(counter_eid)
        if not data or not data.get("has_sum"):
            continue
        # Live-Form derselben Serie (rohe Power-History, noch nicht invertiert —
        # der Helfer nutzt nur den Betrag) für den Grober-Zähler-Fallback.
        pts, grobe_stunden = kurven_leistung_mit_live_fallback(
            data["counter_deltas"], history.get(power_eid),
        )
        if pts:
            counter_overlay[power_eid] = pts
        if grobe_stunden:
            grob_log[power_eid] = len(grobe_stunden)

    if grob_log:
        logger.info(
            "Tagesverlauf: grober Energie-Zähler erkannt (Takt > 5 min) — "
            "Kurvenform stundenweise aus Live-Sensor, Energie aus Zähler: %s",
            ", ".join(f"{eid}={n}h" for eid, n in grob_log.items()),
        )

    mean_overlay: dict[str, list] = {}
    for power_eid in mean_src:
        data = st.get(power_eid)
        if not data:
            continue
        faktor_w = UNIT_TO_W.get(data.get("unit") or "", 1.0)
        pts = means_zu_leistung(data["means"], faktor_w)
        if pts:
            mean_overlay[power_eid] = pts

    return mean_overlay, counter_overlay


async def get_tagesverlauf(
    anlage: Anlage, db: AsyncSession, tage_zurueck: int = 0,
) -> dict:
    """
    Holt stündlich aggregierte Leistungsdaten für einen Tag.

    Args:
        tage_zurueck: 0=heute, 1=gestern, etc.

    Returns:
        dict mit "serien" (Beschreibung der Kurven) und "punkte" (Stundenwerte).
        Butterfly-Chart: Quellen positiv, Senken negativ.
        Bidirektionale Serien (Speicher, Netz) wechseln je nach Richtung.
    """
    basis_live, inv_live_map, basis_invert, inv_invert_map = extract_live_config(anlage)

    if not basis_live and not inv_live_map:
        return {"serien": [], "punkte": []}

    if not HA_INTEGRATION_AVAILABLE:
        return await _get_tagesverlauf_mqtt(anlage, db, tage_zurueck)

    # Investitionen aus DB laden (brauchen Bezeichnung + Typ + parent_id)
    inv_result = await db.execute(
        select(Investition).where(
            Investition.anlage_id == anlage.id,
            aktiv_jetzt(),
        )
    )
    investitionen = {str(inv.id): inv for inv in inv_result.scalars().all()}

    now = datetime.now()
    if tage_zurueck > 0:
        tag = now - timedelta(days=tage_zurueck)
        start = tag.replace(hour=0, minute=0, second=0, microsecond=0)
        end = start + timedelta(days=1)
    else:
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        end = now

    # Investments ohne leistung_w-Konfiguration sammeln (für Hinweis im Frontend)
    uebersprungen: list[str] = []
    for inv in investitionen.values():
        if inv.typ in SKIP_TYPEN or inv.typ not in TV_SERIE_CONFIG:
            continue
        inv_id_str = str(inv.id)
        live_cfg = inv_live_map.get(inv_id_str, {})
        if not live_cfg.get("leistung_w"):
            uebersprungen.append(inv.bezeichnung or inv.typ)

    # Serien-Selektion (inkl. Pool-Dedup) über die geteilte Quelle — identisch
    # zum Backfill-Pfad (Issue #318, M1). Chart-Metadaten (label/farbe/max_w)
    # rekonstruieren wir hier aus den Kern-Specs; sie sind Live-spezifisch.
    serien_core, serie_entities = baue_investitions_serien(inv_live_map, investitionen)
    serien: list[dict] = []
    _SUFFIX_LABEL = {"heizen": " Heizen", "warmwasser": " Warmwasser"}
    for spec in serien_core:
        inv = investitionen[spec.inv_id]
        config = TV_SERIE_CONFIG.get(inv.typ, {})
        if spec.suffix:  # WP-Split: eigene Farbe für Warmwasser, kein max_w
            # WP-Warmwasser: blau (= CHART_COLORS.wpWarmwasser; Gernot 2026-06-25 nach detLAN „Wasser=blau")
            farbe = "#3b82f6" if spec.suffix == "warmwasser" else config.get("farbe")
            serien.append({
                "key": spec.key,
                "label": f"{inv.bezeichnung}{_SUFFIX_LABEL.get(spec.suffix, '')}",
                "kategorie": spec.kategorie,
                "farbe": farbe,
                "seite": spec.seite,
                "bidirektional": spec.bidirektional,
            })
        else:
            serien.append({
                "key": spec.key,
                "label": inv.bezeichnung,
                "kategorie": spec.kategorie,
                "farbe": config.get("farbe"),
                "seite": spec.seite,
                "bidirektional": spec.bidirektional,
                "max_w": config.get("max_w"),
            })

    # PV Gesamt aus Basis als Fallback (wenn kein individueller PV-Sensor)
    has_individual_pv = any(s["kategorie"] == "pv" for s in serien)
    if not has_individual_pv and basis_live.get("pv_gesamt_w"):
        gesamt_kwp = anlage.leistung_kwp or 0
        serien.append({
            "key": "pv_gesamt",
            "label": f"PV Gesamt{f' {gesamt_kwp} kWp' if gesamt_kwp else ''}",
            "kategorie": "pv",
            "farbe": "#f59e0b",
            "seite": "quelle",
            "bidirektional": False,
        })
        serie_entities["pv_gesamt"] = [basis_live["pv_gesamt_w"]]

    # Netz: Netzbezug und Einspeisung als getrennte Serien
    netz_kombi_eid = basis_live.get("netz_kombi_w")
    netz_einspeisung_eid = basis_live.get("einspeisung_w")
    netz_bezug_eid = basis_live.get("netzbezug_w")
    has_netzbezug = False
    has_einspeisung = False

    if netz_kombi_eid and not netz_einspeisung_eid and not netz_bezug_eid:
        # Kombi-Sensor → beide Serien möglich
        has_netzbezug = True
        has_einspeisung = True
    elif netz_einspeisung_eid or netz_bezug_eid:
        netz_kombi_eid = None  # Getrennte Sensoren → kein Kombi
        has_netzbezug = bool(netz_bezug_eid)
        has_einspeisung = bool(netz_einspeisung_eid)

    if has_netzbezug:
        serien.append({
            "key": "netzbezug",
            "label": "Netzbezug",
            "kategorie": "netz",
            "farbe": "#b91c1c",
            "seite": "quelle",
            "bidirektional": False,
        })
    if has_einspeisung:
        serien.append({
            "key": "einspeisung",
            "label": "Einspeisung",
            "kategorie": "netz",
            "farbe": "#10b981",
            "seite": "senke",
            "bidirektional": False,
        })

    # Strompreis-Sensor (optional, für EPEX-Overlay)
    strompreis_eid = None
    basis_mapping = (anlage.sensor_mapping or {}).get("basis", {})
    sp = basis_mapping.get("strompreis")
    if isinstance(sp, dict) and sp.get("sensor_id"):
        strompreis_eid = sp["sensor_id"]
    # Börsenpreis-Fallback immer laden: deckt sowohl "kein Sensor" als auch
    # Lücken im Sensor-History (z.B. Tibber hat erst ab 01:50 Werte) ab.

    # Alle Entity-IDs für History-Abfrage sammeln
    all_ids = list(set(
        eid for eids in serie_entities.values() for eid in eids
    ))
    if has_netzbezug or has_einspeisung:
        if netz_kombi_eid:
            all_ids.append(netz_kombi_eid)
        if netz_einspeisung_eid:
            all_ids.append(netz_einspeisung_eid)
        if netz_bezug_eid:
            all_ids.append(netz_bezug_eid)
    if strompreis_eid:
        all_ids.append(strompreis_eid)
    all_ids = list(set(all_ids))

    if not all_ids:
        return {"serien": [], "punkte": []}

    history, units = await get_history_normalized(all_ids, start, end)

    # Strompreis-Einheit normalisieren → ct/kWh
    if strompreis_eid:
        sp_unit = units.get(strompreis_eid, "")
        if sp_unit in ("EUR/kWh", "€/kWh"):
            pts = history.get(strompreis_eid, [])
            history[strompreis_eid] = [(ts, val * 100) for ts, val in pts]
        elif sp_unit in ("EUR/MWh", "€/MWh"):
            pts = history.get(strompreis_eid, [])
            history[strompreis_eid] = [(ts, val * 0.1) for ts, val in pts]

    # Börsenpreis-Fallback: aWATTar API — immer laden, wird pro Slot als
    # Fallback genutzt wenn Sensor-History für den Slot leer ist.
    _boersenpreis_stunden: dict[int, float] = {}
    try:
        from backend.services.strompreis_markt_service import get_strompreis_stunden
        land = getattr(anlage, "standort_land", None)
        _boersenpreis_stunden = await get_strompreis_stunden(land, start.date())
    except Exception as e:
        logger.debug("Börsenpreis-Fallback: %s", e)

    # HA-LTS-Konsistenz: Kurve aus statistics_short_term speisen, damit
    # Kurven-Integral und Heute-kWh-Kacheln (safe_get_tages_kwh) aus derselben
    # SoT-Familie kommen (#135-Folge). Pro Serie 5-Min-sum-Deltas des kWh-Zählers
    # bzw. short_term.mean des Power-Sensors; Strompreis bleibt unberührt.
    pv_gesamt_eid = serie_entities["pv_gesamt"][0] if "pv_gesamt" in serie_entities else None
    mean_overlay, counter_overlay = _baue_short_term_overlays(
        anlage, serien_core, serie_entities, investitionen,
        pv_gesamt_eid, netz_bezug_eid, netz_einspeisung_eid, netz_kombi_eid,
        start, end, history,
    )

    # Mean-Overlay VOR Invert (gleiche Roh-Sensor-Semantik → Invert gilt,
    # Vorzeichen bleibt erhalten — wichtig für Speicher/Netz-Kombi).
    for eid, pts in mean_overlay.items():
        history[eid] = pts

    # Vorzeichen-Invertierung auf History anwenden (#58)
    apply_invert_to_history(
        history, basis_live, basis_invert, inv_live_map, inv_invert_map
    )

    # Counter-Overlay NACH Invert: Zähler-Energie ist vorzeichenlos/positiv,
    # die Richtung kommt aus serie['seite'] bzw. der Netz-Logik — kein Invert.
    for eid, pts in counter_overlay.items():
        history[eid] = pts

    # 10-Minuten-Mittelwerte berechnen
    punkte: list[dict] = []
    for m in range(144):
        h_start = start + timedelta(minutes=m * 10)
        h_end = h_start + timedelta(minutes=10)
        if h_start > end:
            break

        werte: dict[str, float] = {}
        raw_values: dict[str, float] = {}  # Ungerundet für Haushalt-Berechnung

        # Investitions-Serien
        for serie in serien:
            skey = serie["key"]
            if skey in ("netzbezug", "einspeisung"):
                continue  # Netz separat behandeln

            entity_ids = serie_entities.get(skey, [])
            serie_sum = 0.0
            has_data = False

            max_w = serie.get("max_w")
            for entity_id in entity_ids:
                points = history.get(entity_id, [])
                h_points = [p[1] for p in points if h_start <= p[0] < h_end]
                if max_w is not None:
                    h_points = [v for v in h_points if abs(v) <= max_w]
                if h_points:
                    avg_w = sum(h_points) / len(h_points)
                    serie_sum += avg_w / 1000  # W → kW
                    has_data = True

            if has_data:
                if serie["bidirektional"]:
                    raw_val = -serie_sum
                elif serie["seite"] == "senke":
                    raw_val = -abs(serie_sum)
                else:
                    raw_val = abs(serie_sum)
                raw_values[skey] = raw_val
                werte[skey] = round(raw_val, 2)

        # Netz: Bezug (positiv/Quelle) und Einspeisung (negativ/Senke)
        if has_netzbezug or has_einspeisung:
            bezug_kw = 0.0
            einsp_kw = 0.0

            if netz_kombi_eid:
                pts = history.get(netz_kombi_eid, [])
                h_pts = [p[1] for p in pts if h_start <= p[0] < h_end]
                if h_pts:
                    avg_w = sum(h_pts) / len(h_pts)
                    if avg_w >= 0:
                        bezug_kw = avg_w / 1000
                    else:
                        einsp_kw = abs(avg_w) / 1000
            else:
                if netz_bezug_eid:
                    pts = history.get(netz_bezug_eid, [])
                    h_pts = [p[1] for p in pts if h_start <= p[0] < h_end]
                    if h_pts:
                        bezug_kw = sum(h_pts) / len(h_pts) / 1000

                if netz_einspeisung_eid:
                    pts = history.get(netz_einspeisung_eid, [])
                    h_pts = [p[1] for p in pts if h_start <= p[0] < h_end]
                    if h_pts:
                        einsp_kw = sum(h_pts) / len(h_pts) / 1000

            if has_netzbezug and bezug_kw > 0.001:
                raw_values["netzbezug"] = bezug_kw
                werte["netzbezug"] = round(bezug_kw, 2)
            if has_einspeisung and einsp_kw > 0.001:
                raw_values["einspeisung"] = -einsp_kw
                werte["einspeisung"] = round(-einsp_kw, 2)

        # Haushalt aus ungerundeten Rohwerten berechnen
        quellen_sum = sum(v for v in raw_values.values() if v > 0)
        senken_sum = sum(v for v in raw_values.values() if v < 0)
        haushalt = quellen_sum + senken_sum
        if quellen_sum > 0 and haushalt > 0:
            werte["haushalt"] = round(-haushalt, 2)

        # Strompreis (optional, wird NICHT in Haushalt-Berechnung einbezogen).
        # Tibber/aWATTar/EPEX-Sensoren sind Step-Funktionen — der Preis steht
        # für 15- bzw. 60-Min-Intervalle fest und ändert sich nur an den
        # Block-Grenzen. HA-History speichert nur State-Changes, daher hat
        # mancher 10-Min-Slot keinen Punkt INNERHALB des Slots, obwohl der
        # gültige Preis bekannt ist. #267 rilmor-mhrs: vorher fiel jeder
        # 10-Min-Slot ohne Tibber-Update auf EPEX-Börsenpreis zurück → das
        # erzeugte Sprünge zwischen Endkunden-Preis (~35 ct) und Spotmarkt-
        # Preis (~10 ct). Korrekt: letzten Sensor-Wert vor Slot-Ende als
        # Carry-Forward nehmen (Step-Funktion).
        sensor_hat_wert = False
        if strompreis_eid:
            pts = history.get(strompreis_eid, [])
            # Innerhalb des Slots: bevorzugt mitteln (deckt seltenen Fall ab,
            # dass mehrere Step-Wechsel im selben 10-Min-Slot liegen).
            h_pts = [p[1] for p in pts if h_start <= p[0] < h_end]
            if h_pts:
                werte["strompreis"] = round(sum(h_pts) / len(h_pts), 2)
                sensor_hat_wert = True
            else:
                # Carry-Forward: letzter Punkt vor Slot-Ende, falls vorhanden.
                vorherige = [p[1] for p in pts if p[0] < h_end]
                if vorherige:
                    werte["strompreis"] = round(vorherige[-1], 2)
                    sensor_hat_wert = True
        if not sensor_hat_wert and _boersenpreis_stunden:
            bp = _boersenpreis_stunden.get(h_start.hour)
            if bp is not None:
                werte["strompreis"] = bp

        punkte.append({"zeit": f"{h_start.hour:02d}:{h_start.minute:02d}", "werte": werte})

    # Haushalt-Serie hinzufügen wenn Daten vorhanden
    if any("haushalt" in p["werte"] for p in punkte):
        serien.append({
            "key": "haushalt",
            "label": "Haushalt",
            "kategorie": "haushalt",
            "farbe": "#64748b",
            "seite": "senke",
            "bidirektional": False,
        })

    # Strompreis-Serie hinzufügen wenn Daten vorhanden
    if any("strompreis" in p["werte"] for p in punkte):
        label = "Strompreis" if strompreis_eid else "Börsenpreis (EPEX)"
        serien.append({
            "key": "strompreis",
            "label": label,
            "kategorie": "preis",
            "farbe": "#f472b6",
            "seite": "overlay",
            "bidirektional": False,
            "einheit": "ct/kWh",
        })

    return {"serien": serien, "punkte": punkte, "uebersprungen": uebersprungen}


async def _get_tagesverlauf_mqtt(
    anlage: Anlage, db: AsyncSession, tage_zurueck: int = 0,
) -> dict:
    """
    MQTT-Fallback für Tagesverlauf: liest aus MqttLiveSnapshot statt HA-History.

    Wird aufgerufen wenn HA_INTEGRATION_AVAILABLE == False (Docker-Standalone).
    Erwartet dass mqtt_live_history_service alle 5 Min Snapshots schreibt.
    """
    from backend.services.mqtt_live_history_service import get_snapshots_for_range

    now = datetime.now()
    if tage_zurueck > 0:
        tag = now - timedelta(days=tage_zurueck)
        start = tag.replace(hour=0, minute=0, second=0, microsecond=0)
        end = start + timedelta(days=1)
    else:
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        end = now

    # Börsenpreis-Fallback holen — per-Slot-Fallback bei Lücken im MQTT-Sensor
    _mqtt_boersenpreis: dict[int, float] = {}
    try:
        from backend.services.strompreis_markt_service import get_strompreis_stunden
        land = getattr(anlage, "standort_land", None)
        _mqtt_boersenpreis = await get_strompreis_stunden(land, start.date())
    except Exception:
        pass

    rows = await get_snapshots_for_range(anlage.id, start, end, db)
    if not rows:
        return {"serien": [], "punkte": []}

    # History aufbauen: {component_key: [(timestamp, value_w)]}
    history: dict[str, list[tuple[datetime, float]]] = {}
    for row in rows:
        history.setdefault(row.component_key, []).append((row.timestamp, row.value_w))

    available_keys = set(history.keys())

    # Investitionen laden
    inv_result = await db.execute(
        select(Investition).where(
            Investition.anlage_id == anlage.id,
            aktiv_jetzt(),
        )
    )
    investitionen = {str(inv.id): inv for inv in inv_result.scalars().all()}

    serien: list[dict] = []
    serie_comp_keys: dict[str, list[str]] = {}
    uebersprungen: list[str] = []

    # WP mit getrennter Strommessung
    for inv_id, inv in investitionen.items():
        if inv.typ != "waermepumpe":
            continue
        config = TV_SERIE_CONFIG.get("waermepumpe")
        if not config:
            continue
        heiz_key = f"inv:{inv_id}:leistung_heizen_w"
        ww_key = f"inv:{inv_id}:leistung_warmwasser_w"
        gesamt_key = f"inv:{inv_id}:leistung_w"
        if gesamt_key in available_keys:
            continue  # Gesamtleistung vorhanden → wird unten verarbeitet
        if heiz_key in available_keys:
            key_h = f"waermepumpe_{inv_id}_heizen"
            serien.append({
                "key": key_h,
                "label": f"{inv.bezeichnung} Heizen",
                "kategorie": config["kategorie"],
                "farbe": config["farbe"],
                "seite": config["seite"],
                "bidirektional": config["bidirektional"],
            })
            serie_comp_keys[key_h] = [heiz_key]
        if ww_key in available_keys:
            key_w = f"waermepumpe_{inv_id}_warmwasser"
            serien.append({
                "key": key_w,
                "label": f"{inv.bezeichnung} Warmwasser",
                "kategorie": config["kategorie"],
                "farbe": "#3b82f6",  # WP-Warmwasser blau (= CHART_COLORS.wpWarmwasser; Gernot 2026-06-25 nach detLAN)
                "seite": config["seite"],
                "bidirektional": config["bidirektional"],
            })
            serie_comp_keys[key_w] = [ww_key]

    # Investitions-Serien (alle außer WP die bereits oben verarbeitet wurden)
    for inv_id, inv in investitionen.items():
        typ = inv.typ
        if typ in SKIP_TYPEN or typ not in TV_SERIE_CONFIG:
            continue
        # WP: nur wenn Gesamtleistung vorhanden (getrennte Messung wurde oben behandelt)
        comp_key = f"inv:{inv_id}:leistung_w"
        if comp_key not in available_keys:
            if typ != "waermepumpe":
                uebersprungen.append(inv.bezeichnung or typ)
            continue

        # E-Auto mit Parent (Wallbox) überspringen
        if typ == "e-auto" and inv.parent_investition_id is not None:
            continue

        config = TV_SERIE_CONFIG[typ]
        seite = config["seite"]
        bidirektional = config["bidirektional"]
        if typ == "sonstiges" and isinstance(inv.parameter, dict):
            kat = inv.parameter.get("kategorie", "verbraucher")
            if kat == "erzeuger":
                seite = "quelle"
            elif kat == "speicher":
                bidirektional = True

        serie_key = f"{config['kategorie']}_{inv_id}"
        serien.append({
            "key": serie_key,
            "label": inv.bezeichnung,
            "kategorie": config["kategorie"],
            "farbe": config["farbe"],
            "seite": seite,
            "bidirektional": bidirektional,
            "max_w": config.get("max_w"),
        })
        serie_comp_keys[serie_key] = [comp_key]

    # PV Gesamt als Fallback (wenn keine individuellen PV-Sensoren)
    has_individual_pv = any(s["kategorie"] == "pv" for s in serien)
    if not has_individual_pv and "basis:pv_gesamt_w" in available_keys:
        gesamt_kwp = anlage.leistung_kwp or 0
        serien.append({
            "key": "pv_gesamt",
            "label": f"PV Gesamt{f' {gesamt_kwp} kWp' if gesamt_kwp else ''}",
            "kategorie": "pv",
            "farbe": "#f59e0b",
            "seite": "quelle",
            "bidirektional": False,
        })
        serie_comp_keys["pv_gesamt"] = ["basis:pv_gesamt_w"]

    # Netz: Netzbezug und Einspeisung als getrennte Serien
    has_netz_kombi = "basis:netz_kombi_w" in available_keys
    has_einsp = "basis:einspeisung_w" in available_keys
    has_bezug = "basis:netzbezug_w" in available_keys
    has_netzbezug = has_netz_kombi or has_bezug
    has_einspeisung = has_netz_kombi or has_einsp

    if has_netzbezug:
        serien.append({
            "key": "netzbezug",
            "label": "Netzbezug",
            "kategorie": "netz",
            "farbe": "#b91c1c",
            "seite": "quelle",
            "bidirektional": False,
        })
    if has_einspeisung:
        serien.append({
            "key": "einspeisung",
            "label": "Einspeisung",
            "kategorie": "netz",
            "farbe": "#10b981",
            "seite": "senke",
            "bidirektional": False,
        })

    if not serien:
        return {"serien": [], "punkte": []}

    # 10-Minuten-Mittelwerte berechnen (144 Intervalle pro Tag)
    punkte: list[dict] = []
    for m in range(144):
        h_start = start + timedelta(minutes=m * 10)
        h_end = h_start + timedelta(minutes=10)
        if h_start >= end:
            break

        werte: dict[str, float] = {}
        raw_values: dict[str, float] = {}

        for serie in serien:
            skey = serie["key"]
            if skey in ("netzbezug", "einspeisung"):
                continue
            comp_keys = serie_comp_keys.get(skey, [])
            serie_sum = 0.0
            has_data = False
            max_w = serie.get("max_w")
            for ckey in comp_keys:
                pts = [v for ts, v in history.get(ckey, []) if h_start <= ts < h_end]
                if max_w is not None:
                    pts = [v for v in pts if abs(v) <= max_w]
                if pts:
                    serie_sum += sum(pts) / len(pts) / 1000  # W → kW
                    has_data = True
            if has_data:
                if serie["bidirektional"]:
                    raw_val = -serie_sum
                elif serie["seite"] == "senke":
                    raw_val = -abs(serie_sum)
                else:
                    raw_val = abs(serie_sum)
                raw_values[skey] = raw_val
                werte[skey] = round(raw_val, 2)

        # Netz: Bezug (positiv/Quelle) und Einspeisung (negativ/Senke)
        if has_netzbezug or has_einspeisung:
            bezug_kw = 0.0
            einsp_kw = 0.0
            if has_netz_kombi and not has_einsp and not has_bezug:
                pts = [v for ts, v in history.get("basis:netz_kombi_w", []) if h_start <= ts < h_end]
                if pts:
                    avg = sum(pts) / len(pts) / 1000
                    if avg >= 0:
                        bezug_kw = avg
                    else:
                        einsp_kw = abs(avg)
            else:
                pts = [v for ts, v in history.get("basis:netzbezug_w", []) if h_start <= ts < h_end]
                if pts:
                    bezug_kw = sum(pts) / len(pts) / 1000
                pts = [v for ts, v in history.get("basis:einspeisung_w", []) if h_start <= ts < h_end]
                if pts:
                    einsp_kw = sum(pts) / len(pts) / 1000

            if has_netzbezug and bezug_kw > 0.001:
                raw_values["netzbezug"] = bezug_kw
                werte["netzbezug"] = round(bezug_kw, 2)
            if has_einspeisung and einsp_kw > 0.001:
                raw_values["einspeisung"] = -einsp_kw
                werte["einspeisung"] = round(-einsp_kw, 2)

        # Haushalt berechnen
        quellen_sum = sum(v for v in raw_values.values() if v > 0)
        senken_sum = sum(v for v in raw_values.values() if v < 0)
        haushalt = quellen_sum + senken_sum
        if quellen_sum > 0 and haushalt > 0:
            werte["haushalt"] = round(-haushalt, 2)

        # Strompreis (optional, MQTT-Key: strompreis_ct oder Börsenpreis-Fallback).
        # Sensor-Wert hat Vorrang, EPEX ist per-Slot-Fallback für Lücken (MQTT
        # kann nach Nacht-Downtime Daten erst ab 01:50 haben).
        sp_pts = [v for ts, v in history.get("basis:strompreis_ct", []) if h_start <= ts < h_end]
        if sp_pts:
            werte["strompreis"] = round(sum(sp_pts) / len(sp_pts), 2)
        elif _mqtt_boersenpreis:
            bp = _mqtt_boersenpreis.get(h_start.hour)
            if bp is not None:
                werte["strompreis"] = bp

        punkte.append({"zeit": f"{h_start.hour:02d}:{h_start.minute:02d}", "werte": werte})

    # Haushalt-Serie ergänzen wenn Daten vorhanden
    if any("haushalt" in p["werte"] for p in punkte):
        serien.append({
            "key": "haushalt",
            "label": "Haushalt",
            "kategorie": "haushalt",
            "farbe": "#64748b",
            "seite": "senke",
            "bidirektional": False,
        })

    # Strompreis-Serie ergänzen wenn Daten vorhanden
    has_mqtt_strompreis = "basis:strompreis_ct" in available_keys
    if any("strompreis" in p["werte"] for p in punkte):
        label = "Strompreis" if has_mqtt_strompreis else "Börsenpreis (EPEX)"
        serien.append({
            "key": "strompreis",
            "label": label,
            "kategorie": "preis",
            "farbe": "#f472b6",
            "seite": "overlay",
            "bidirektional": False,
            "einheit": "ct/kWh",
        })

    return {"serien": serien, "punkte": punkte, "uebersprungen": uebersprungen}
