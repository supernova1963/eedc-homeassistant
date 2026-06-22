"""
Live Komponenten Builder — baut Komponenten + Gauges aus Live-Werten.

Ausgelagert aus live_power_service.py (Schritt 6 des Refactorings).
"""

import logging
from typing import Optional

from backend.models.anlage import Anlage
from backend.models.investition import Investition
from backend.core.investition_parameter import PARAM_E_AUTO
from backend.core.berechnungen.energie import PV_KOMPONENTEN_PREFIXE
from backend.services.live_sensor_config import (
    TYP_ICON,
    ERZEUGER_TYPEN,
    BIDIREKTIONAL_TYPEN,
    SOC_TYPEN,
    SKIP_TYPEN,
    TAGESVERLAUF_KATEGORIE,
    LIVE_KEY_PREFIX,
)

logger = logging.getLogger(__name__)


def build_komponenten(
    anlage: Anlage,
    basis_values: dict[str, float],
    inv_values: dict[str, dict[str, float]],
    investitionen: dict[str, Investition],
    inv_live_map: dict[str, dict[str, str]],
) -> dict:
    """
    Baut Komponenten-Liste, Gauges und Summen aus Live-Werten.

    Returns:
        {
            "komponenten": [...],
            "gauges": [...],
            "summe_erzeugung_kw": float,
            "summe_verbrauch_kw": float,
            "pv_total_w": float,
            "warmwasser_temperatur_c": float | None,
        }
    """
    komponenten = []
    summe_erzeugung = 0.0
    summe_verbrauch = 0.0
    gauges = []
    pv_total_w = 0.0
    # Sonstige Erzeuger (z. B. BHKW) speisen hinter den Zähler → gehen in die
    # Netzpunkt-Bilanz (Autarkie/EV), aber NICHT in pv_total_w (PV-Leistungs-%
    # bleibt rein). Konzept Sonstiger Erzeuger 2026-06-22.
    sonstige_erzeugung_w = 0.0

    # Wallbox-Keys sammeln für E-Auto → Wallbox Zuordnung
    wallbox_keys: list[str] = []

    # Entity-IDs tracken um Duplikate zu erkennen. WICHTIG: deterministische
    # Wallbox-Priorität (analog Tagesverlauf #318: prioritaet wallbox<eauto).
    # Teilen Wallbox + E-Auto dieselbe `leistung_w`-Entity (gleicher Stromfluss
    # aus zwei Perspektiven), muss die Wallbox die Entity zuerst beanspruchen —
    # sonst hing der Dedup an der Dict-Reihenfolge und ein E-Auto-vor-Wallbox-
    # Setup zählte beide (#314-Folge, Pool-Asymmetrie-Klasse #290/#298/#318).
    def _dedup_prio(iid: str) -> int:
        inv = investitionen.get(iid)
        t = inv.typ if inv else None
        return 0 if t == "wallbox" else (1 if t == "e-auto" else 2)

    used_leistung_eids: dict[str, str] = {}
    for inv_id in sorted(inv_live_map, key=_dedup_prio):
        eid = inv_live_map[inv_id].get("leistung_w")
        if eid and eid not in used_leistung_eids:
            used_leistung_eids[eid] = inv_id

    # Gibt es eine Wallbox mit Live-Leistung? Dann werden E-Autos als deren
    # Kinder gepoolt (parent_key unten) — und genau dann (und nur dann) darf das
    # E-Auto NICHT separat in summe_verbrauch zählen. Ohne Wallbox (Schuko/
    # Steckerlader) ist das E-Auto ein eigenständiger Verbraucher und MUSS
    # gezählt werden, sonst untererfasst summe_verbrauch (086cf70f-Prinzip).
    hat_wallbox = any(
        (investitionen.get(iid) and investitionen.get(iid).typ == "wallbox"
         and vals.get("leistung_w") is not None)
        for iid, vals in inv_values.items()
    )

    # Per-Investition Komponenten
    for inv_id, values in inv_values.items():
        inv = investitionen.get(inv_id)
        if not inv or inv.typ in SKIP_TYPEN:
            continue

        val_w = values.get("leistung_w")

        # Wärmepumpe: getrennte Leistungswerte summieren + Icon je Betriebsmodus
        wp_icon = None
        if inv.typ == "waermepumpe":
            heizen_w = values.get("leistung_heizen_w")
            ww_w = values.get("leistung_warmwasser_w")
            if heizen_w is not None or ww_w is not None:
                if val_w is None:
                    val_w = (heizen_w or 0) + (ww_w or 0)
                h = heizen_w or 0
                w = ww_w or 0
                if h > 0 or w > 0:
                    wp_icon = "heater" if h >= w else "droplets"

        if val_w is None:
            typ = inv.typ if inv else None
            if typ in SOC_TYPEN:
                soc_val = values.get("soc")
                if soc_val is not None:
                    gauges.append({
                        "key": f"soc_{inv_id}",
                        "label": inv.bezeichnung,
                        "wert": round(soc_val, 0),
                        "min_wert": 0,
                        "max_wert": 100,
                        "einheit": "%",
                    })
            continue

        typ = inv.typ

        # Duplikat-Sensor-Erkennung
        leistung_eid = inv_live_map.get(inv_id, {}).get("leistung_w")
        if typ == "e-auto" and leistung_eid:
            first_user = used_leistung_eids.get(leistung_eid)
            if first_user and first_user != inv_id:
                first_inv = investitionen.get(first_user)
                if first_inv and first_inv.typ == "wallbox":
                    logger.debug(
                        f"E-Auto {inv.bezeichnung}: gleicher Sensor wie Wallbox "
                        f"{first_inv.bezeichnung} — Leistung übersprungen"
                    )
                    val_w = None

        if val_w is None:
            if typ in SOC_TYPEN:
                soc_val = values.get("soc")
                if soc_val is not None:
                    gauges.append({
                        "key": f"soc_{inv_id}",
                        "label": inv.bezeichnung,
                        "wert": round(soc_val, 0),
                        "min_wert": 0,
                        "max_wert": 100,
                        "einheit": "%",
                    })
            continue

        # E-Auto mit V2H ist bidirektional (Bug #1 v3.25.0: vorher 'nutzt_v2h', Form schreibt 'v2h_faehig')
        ist_v2h = (typ == "e-auto"
                   and isinstance(inv.parameter, dict)
                   and inv.parameter.get(PARAM_E_AUTO["V2H_FAEHIG"]))
        ist_bidirektional = typ in BIDIREKTIONAL_TYPEN or ist_v2h

        ist_sonstiger_erzeuger = (
            typ == "sonstiges"
            and isinstance(inv.parameter, dict)
            and inv.parameter.get("kategorie") == "erzeuger"
        )

        if typ in ERZEUGER_TYPEN:
            kw = val_w / 1000
            komponenten.append({
                "key": f"pv_{inv_id}",
                "label": inv.bezeichnung,
                "icon": TYP_ICON.get(typ, "sun"),
                "erzeugung_kw": round(kw, 3),
                "verbrauch_kw": None,
                "leistung_kwp": inv.leistung_kwp,
            })
            summe_erzeugung += kw
            pv_total_w += val_w

        elif ist_sonstiger_erzeuger:
            # Sonstiger Erzeuger (BHKW) — eigene Erzeugungs-Komponente, fließt in
            # die Netzpunkt-Bilanz (summe_erzeugung + Autarkie unten), aber NICHT
            # in pv_total_w (kein PV → keine kWp/PV-%, Achsen-Trennung).
            kw = val_w / 1000
            komponenten.append({
                "key": f"sonstige_{inv_id}",
                "label": inv.bezeichnung,
                "icon": TYP_ICON.get(typ, "wrench"),
                "erzeugung_kw": round(kw, 3),
                "verbrauch_kw": None,
                "leistung_kwp": None,
            })
            summe_erzeugung += kw
            sonstige_erzeugung_w += val_w

        elif ist_bidirektional:
            kw = abs(val_w) / 1000
            ist_ladung = val_w > 0
            kategorie = TAGESVERLAUF_KATEGORIE.get(typ, "batterie")
            komponenten.append({
                "key": f"{kategorie}_{inv_id}",
                "label": inv.bezeichnung,
                "icon": TYP_ICON.get(typ, "battery"),
                "erzeugung_kw": round(kw, 3) if not ist_ladung else None,
                "verbrauch_kw": round(kw, 3) if ist_ladung else None,
            })
            if ist_ladung:
                summe_verbrauch += kw
            else:
                summe_erzeugung += kw

        else:
            kw = abs(val_w) / 1000
            prefix = LIVE_KEY_PREFIX.get(typ, TAGESVERLAUF_KATEGORIE.get(typ, typ))
            komp_key = f"{prefix}_{inv_id}"
            komponenten.append({
                "key": komp_key,
                "label": inv.bezeichnung,
                "icon": wp_icon or TYP_ICON.get(typ, "wrench"),
                "erzeugung_kw": None,
                "verbrauch_kw": round(kw, 3),
            })
            if typ == "wallbox":
                wallbox_keys.append(komp_key)
            # E-Auto nur ausschließen, wenn es tatsächlich unter eine Wallbox
            # gepoolt wird (hat_wallbox → parent_key unten). Ohne Wallbox ist es
            # ein realer Verbraucher und zählt normal (konsistent mit gesamt_senken,
            # das nur parent_key-Kinder ausschließt) — #314-Folge.
            if not (typ == "e-auto" and hat_wallbox):
                summe_verbrauch += kw

        # SoC-Gauge pro Investition
        if typ in SOC_TYPEN:
            soc_val = values.get("soc")
            if soc_val is not None:
                gauges.append({
                    "key": f"soc_{inv_id}",
                    "label": inv.bezeichnung,
                    "wert": round(soc_val, 0),
                    "min_wert": 0,
                    "max_wert": 100,
                    "einheit": "%",
                })

    # E-Auto → Wallbox Zuordnung
    if wallbox_keys:
        wb_idx = 0
        for komp in komponenten:
            if komp["key"].startswith("eauto_"):
                komp["parent_key"] = wallbox_keys[wb_idx % len(wallbox_keys)]
                wb_idx += 1

    # PV Gesamt aus Basis (wenn kein individueller PV-Sensor vorhanden).
    # Erzeuger (PV-Module + Balkonkraftwerk) tragen in diesem Live-Keyspace
    # einheitlich den `pv_`-Präfix; die Prefix-Quelle kommt zentral aus dem
    # Berechnungs-Layer (ADR-001) statt als eigenes Literal.
    def _ist_pv_komponente(k) -> bool:
        key = k.key if hasattr(k, "key") else k.get("key", "")
        return any(key.startswith(p) for p in PV_KOMPONENTEN_PREFIXE)

    has_individual_pv = any(_ist_pv_komponente(k) for k in komponenten)
    pv_gesamt_w_val = basis_values.get("pv_gesamt_w")
    if pv_gesamt_w_val is not None and not has_individual_pv:
        kw = pv_gesamt_w_val / 1000
        gesamt_kwp = anlage.leistung_kwp or 0
        komponenten.append({
            "key": "pv_gesamt",
            "label": f"PV Gesamt{f' {gesamt_kwp} kWp' if gesamt_kwp else ''}",
            "icon": "sun",
            "erzeugung_kw": round(kw, 3),
            "verbrauch_kw": None,
        })
        summe_erzeugung += kw
        pv_total_w += pv_gesamt_w_val

    # Netz-Komponente
    einspeisung_w = basis_values.get("einspeisung_w")
    netzbezug_w = basis_values.get("netzbezug_w")

    if einspeisung_w is not None or netzbezug_w is not None:
        einsp_kw = (einspeisung_w or 0) / 1000
        bezug_kw = (netzbezug_w or 0) / 1000
        komponenten.append({
            "key": "netz",
            "label": "Stromnetz",
            "icon": "zap",
            "erzeugung_kw": round(bezug_kw, 3) if bezug_kw > 0 else None,
            "verbrauch_kw": round(einsp_kw, 3) if einsp_kw > 0 else None,
        })
        if bezug_kw > 0:
            summe_erzeugung += bezug_kw
        if einsp_kw > 0:
            summe_verbrauch += einsp_kw

    # Haushalt = Residual
    gesamt_quellen = sum(k.get("erzeugung_kw") or 0 for k in komponenten)
    gesamt_senken = sum(
        k.get("verbrauch_kw") or 0 for k in komponenten
        if not k.get("parent_key")
    )
    if gesamt_quellen > 0 and (einspeisung_w is not None or netzbezug_w is not None):
        haushalt_kw = max(0, gesamt_quellen - gesamt_senken)
        komponenten.append({
            "key": "haushalt",
            "label": "Haushalt",
            "icon": "home",
            "erzeugung_kw": None,
            "verbrauch_kw": round(haushalt_kw, 3),
        })
        summe_verbrauch += haushalt_kw

    # Netz-Gauge
    if einspeisung_w is not None or netzbezug_w is not None:
        netto_w = (netzbezug_w or 0) - (einspeisung_w or 0)
        max_val = max(abs(einspeisung_w or 0), abs(netzbezug_w or 0), 1)
        gauges.insert(0, {
            "key": "netz",
            "label": "Netz",
            "wert": round(netto_w, 0),
            "min_wert": -max_val,
            "max_wert": max_val,
            "einheit": "W",
        })

    # PV-Leistung in % von kWp
    kwp = anlage.leistung_kwp
    if pv_total_w > 0 and kwp and kwp > 0:
        pv_pct = pv_total_w / 1000 / kwp * 100
        gauges.append({
            "key": "pv_leistung",
            "label": "PV-Leistung",
            "wert": round(min(pv_pct, 120), 0),
            "min_wert": 0,
            "max_wert": 120,
            "einheit": "% kWp",
        })

    # Autarkie + Eigenverbrauchsquote — Netzpunkt-Bilanz nutzt die Gesamterzeugung
    # hinter dem Zähler (PV + sonstige Erzeuger wie BHKW), nicht nur PV. Die
    # PV-Leistungs-Gauge oben bleibt rein (pv_total_w). Konzept Sonstiger Erzeuger.
    erzeugung_w = pv_total_w + sonstige_erzeugung_w
    if erzeugung_w > 0 and (einspeisung_w is not None or netzbezug_w is not None):
        erzeugung_kw = erzeugung_w / 1000
        bat_ladung_kw = sum(
            k.get("verbrauch_kw") or 0 for k in komponenten
            if k["key"].startswith("batterie_") or k["key"].startswith("v2h_")
        )
        bat_entladung_kw = sum(
            k.get("erzeugung_kw") or 0 for k in komponenten
            if k["key"].startswith("batterie_") or k["key"].startswith("v2h_")
        )
        direktverbrauch_kw = max(0, erzeugung_kw - (einspeisung_w or 0) / 1000 - bat_ladung_kw)
        eigenverbrauch_kw = direktverbrauch_kw + bat_entladung_kw
        gesamt_verbrauch_kw = eigenverbrauch_kw + (netzbezug_w or 0) / 1000

        if gesamt_verbrauch_kw > 0:
            autarkie = eigenverbrauch_kw / gesamt_verbrauch_kw * 100
            gauges.append({
                "key": "autarkie",
                "label": "Autarkie",
                "wert": round(min(autarkie, 100), 0),
                "min_wert": 0,
                "max_wert": 100,
                "einheit": "%",
            })

        if erzeugung_kw > 0:
            ev_quote = eigenverbrauch_kw / erzeugung_kw * 100
            gauges.append({
                "key": "eigenverbrauch",
                "label": "Eigenverbr.",
                "wert": round(min(ev_quote, 100), 0),
                "min_wert": 0,
                "max_wert": 100,
                "einheit": "%",
            })

    # Warmwasser-Temperatur
    warmwasser_temperatur_c = None
    for inv_id, values in inv_values.items():
        inv = investitionen.get(inv_id)
        if inv and inv.typ == "waermepumpe":
            ww_temp = values.get("warmwasser_temperatur_c")
            if ww_temp is not None:
                warmwasser_temperatur_c = round(ww_temp, 1)
                break

    return {
        "komponenten": komponenten,
        "gauges": gauges,
        "summe_erzeugung_kw": round(summe_erzeugung, 3),
        "summe_verbrauch_kw": round(summe_verbrauch, 3),
        "pv_total_w": pv_total_w,
        "warmwasser_temperatur_c": warmwasser_temperatur_c,
    }
