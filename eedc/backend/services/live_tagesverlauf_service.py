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
    SKIP_TYPEN,
    TV_SERIE_CONFIG,
    extract_live_config,
)
from backend.services.live_history_service import (
    get_history_normalized,
    apply_invert_to_history,
)

logger = logging.getLogger(__name__)


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

    # Serien aufbauen + Entity-IDs sammeln
    serien: list[dict] = []
    # Mapping: serie_key → list[entity_id] (für Multi-Sensor-Aggregation)
    serie_entities: dict[str, list[str]] = {}

    # Investments ohne leistung_w-Konfiguration sammeln (für Hinweis im Frontend)
    uebersprungen: list[str] = []
    for inv in investitionen.values():
        if inv.typ in SKIP_TYPEN or inv.typ not in TV_SERIE_CONFIG:
            continue
        inv_id_str = str(inv.id)
        live_cfg = inv_live_map.get(inv_id_str, {})
        if not live_cfg.get("leistung_w"):
            uebersprungen.append(inv.bezeichnung or inv.typ)

    # Investitionen → Serien
    for inv_id, live in inv_live_map.items():
        inv = investitionen.get(inv_id)
        if not inv:
            continue
        typ = inv.typ
        if typ in SKIP_TYPEN:
            continue

        has_leistung = live.get("leistung_w")

        # WP mit getrennter Strommessung → zwei Serien statt einer
        if not has_leistung and typ == "waermepumpe":
            heiz_eid = live.get("leistung_heizen_w")
            ww_eid = live.get("leistung_warmwasser_w")
            config = TV_SERIE_CONFIG.get("waermepumpe")
            if config and (heiz_eid or ww_eid):
                if heiz_eid:
                    key_h = f"waermepumpe_{inv_id}_heizen"
                    serien.append({
                        "key": key_h,
                        "label": f"{inv.bezeichnung} Heizen",
                        "kategorie": config["kategorie"],
                        "farbe": config["farbe"],
                        "seite": config["seite"],
                        "bidirektional": config["bidirektional"],
                    })
                    serie_entities[key_h] = [heiz_eid]
                if ww_eid:
                    key_w = f"waermepumpe_{inv_id}_warmwasser"
                    serien.append({
                        "key": key_w,
                        "label": f"{inv.bezeichnung} Warmwasser",
                        "kategorie": config["kategorie"],
                        "farbe": "#f59e0b",  # Amber für Warmwasser
                        "seite": config["seite"],
                        "bidirektional": config["bidirektional"],
                    })
                    serie_entities[key_w] = [ww_eid]
            continue

        if not has_leistung:
            continue

        # E-Auto mit Parent (Wallbox) überspringen — Wallbox misst bereits
        if typ == "e-auto" and inv.parent_investition_id is not None:
            continue

        config = TV_SERIE_CONFIG.get(typ)
        if not config:
            continue

        # Sonstiges: Seite aus parameter.kategorie ableiten
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
        serie_entities[serie_key] = [live["leistung_w"]]

    # PV Gesamt aus Basis als Fallback (wenn kein individueller PV-Sensor)
    has_individual_pv = any(s["kategorie"] == "pv" for s in serien)
    if not has_individual_pv and basis_live.get("pv_gesamt_w"):
        gesamt_kwp = anlage.leistung_kwp or 0
        serien.append({
            "key": "pv_gesamt",
            "label": f"PV Gesamt{f' {gesamt_kwp} kWp' if gesamt_kwp else ''}",
            "kategorie": "pv",
            "farbe": "#eab308",
            "seite": "quelle",
            "bidirektional": False,
        })
        serie_entities["pv_gesamt"] = [basis_live["pv_gesamt_w"]]

    # Netz (Einspeisung + Netzbezug als eine bidirektionale Serie)
    has_netz = False
    netz_kombi_eid = basis_live.get("netz_kombi_w")
    netz_einspeisung_eid = basis_live.get("einspeisung_w")
    netz_bezug_eid = basis_live.get("netzbezug_w")
    # Kombinierter Sensor hat Vorrang wenn keine getrennten Sensoren
    if netz_kombi_eid and not netz_einspeisung_eid and not netz_bezug_eid:
        has_netz = True
        serien.append({
            "key": "netz",
            "label": "Stromnetz",
            "kategorie": "netz",
            "farbe": "#ef4444",
            "seite": "quelle",
            "bidirektional": True,
        })
    elif netz_einspeisung_eid or netz_bezug_eid:
        netz_kombi_eid = None  # Getrennte Sensoren → kein Kombi
        has_netz = True
        serien.append({
            "key": "netz",
            "label": "Stromnetz",
            "kategorie": "netz",
            "farbe": "#ef4444",
            "seite": "quelle",
            "bidirektional": True,
        })

    # Alle Entity-IDs für History-Abfrage sammeln
    all_ids = list(set(
        eid for eids in serie_entities.values() for eid in eids
    ))
    if netz_kombi_eid:
        all_ids.append(netz_kombi_eid)
    if netz_einspeisung_eid:
        all_ids.append(netz_einspeisung_eid)
    if netz_bezug_eid:
        all_ids.append(netz_bezug_eid)
    all_ids = list(set(all_ids))

    if not all_ids:
        return {"serien": [], "punkte": []}

    history, _ = await get_history_normalized(all_ids, start, end)

    # Vorzeichen-Invertierung auf History anwenden (#58)
    apply_invert_to_history(
        history, basis_live, basis_invert, inv_live_map, inv_invert_map
    )

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
            if skey == "netz":
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

        # Netz: Bezug (positiv/Quelle) - Einspeisung (negativ/Senke)
        if has_netz:
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

            netto = bezug_kw - einsp_kw
            if abs(netto) > 0.001:
                raw_values["netz"] = netto
                werte["netz"] = round(netto, 2)

        # Haushalt aus ungerundeten Rohwerten berechnen
        quellen_sum = sum(v for v in raw_values.values() if v > 0)
        senken_sum = sum(v for v in raw_values.values() if v < 0)
        haushalt = quellen_sum + senken_sum
        if quellen_sum > 0 and haushalt > 0:
            werte["haushalt"] = round(-haushalt, 2)

        punkte.append({"zeit": f"{h_start.hour:02d}:{h_start.minute:02d}", "werte": werte})

    # Haushalt-Serie hinzufügen wenn Daten vorhanden
    if any("haushalt" in p["werte"] for p in punkte):
        serien.append({
            "key": "haushalt",
            "label": "Haushalt",
            "kategorie": "haushalt",
            "farbe": "#10b981",
            "seite": "senke",
            "bidirektional": False,
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
                "farbe": "#f59e0b",
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
            "farbe": "#eab308",
            "seite": "quelle",
            "bidirektional": False,
        })
        serie_comp_keys["pv_gesamt"] = ["basis:pv_gesamt_w"]

    # Netz
    has_netz_kombi = "basis:netz_kombi_w" in available_keys
    has_einsp = "basis:einspeisung_w" in available_keys
    has_bezug = "basis:netzbezug_w" in available_keys
    has_netz = has_netz_kombi or has_einsp or has_bezug
    if has_netz:
        serien.append({
            "key": "netz",
            "label": "Stromnetz",
            "kategorie": "netz",
            "farbe": "#ef4444",
            "seite": "quelle",
            "bidirektional": True,
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
            if skey == "netz":
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

        # Netz: Bezug (positiv) - Einspeisung (negativ)
        if has_netz:
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
            netto = bezug_kw - einsp_kw
            if abs(netto) > 0.001:
                raw_values["netz"] = netto
                werte["netz"] = round(netto, 2)

        # Haushalt berechnen
        quellen_sum = sum(v for v in raw_values.values() if v > 0)
        senken_sum = sum(v for v in raw_values.values() if v < 0)
        haushalt = quellen_sum + senken_sum
        if quellen_sum > 0 and haushalt > 0:
            werte["haushalt"] = round(-haushalt, 2)

        punkte.append({"zeit": f"{h_start.hour:02d}:{h_start.minute:02d}", "werte": werte})

    # Haushalt-Serie ergänzen wenn Daten vorhanden
    if any("haushalt" in p["werte"] for p in punkte):
        serien.append({
            "key": "haushalt",
            "label": "Haushalt",
            "kategorie": "haushalt",
            "farbe": "#10b981",
            "seite": "senke",
            "bidirektional": False,
        })

    return {"serien": serien, "punkte": punkte, "uebersprungen": uebersprungen}
