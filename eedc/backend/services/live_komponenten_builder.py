"""
Live Komponenten Builder — baut Komponenten + Gauges aus Live-Werten.

Ausgelagert aus live_power_service.py (Schritt 6 des Refactorings).
"""

import logging
from dataclasses import dataclass, field
from typing import Optional

from backend.models.anlage import Anlage
from backend.models.investition import Investition
from backend.core.investition_kennwerte import (
    get_erzeuger_kwp,
    get_speicher_nutzbare_kapazitaet_kwh,
)
from backend.core.investition_parameter import PARAM_E_AUTO
from datetime import date

from backend.core.betriebsmodus import (
    BETRIEBSMODUS_AKTION_LABEL,
    BETRIEBSMODUS_ICON,
    BETRIEBSMODUS_LABEL,
    BETRIEBSMODUS_LIVE_OHNE_KLARTEXT,
    HEIZEN,
    KUEHLEN,
)
from backend.core.berechnungen.anlagen_kwp import anlagen_kwp
from backend.core.berechnungen.energie import PV_KOMPONENTEN_PREFIXE
from backend.core.berechnungen.erzeuger_traeger import bkw_restwerte
from backend.core.berechnungen.temperatur import spreizung_k
from backend.services.pv_orientation import ausrichtung_label
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
    modus_map: Optional[dict[int, str]] = None,
    aktion_map: Optional[dict[int, str]] = None,
) -> dict:
    """
    Baut Komponenten-Liste, Gauges und Summen aus Live-Werten.

    ``aktion_map`` (P-433-1): die gemessene Aktion je Gerät neben dem Kanon-Wert
    (`betriebsmodus_live.lade_betriebsmodus_aktion_live`, heute nur «leerlauf») —
    reine Anzeige, keine Summe liest sie.

    Returns:
        {
            "komponenten": [...],
            "gauges": [...],
            "summe_erzeugung_kw": float,
            "summe_verbrauch_kw": float,
            "verbrauch_gesamt_kw": float | None,
            "pv_total_w": float,
            "warmwasser_temperatur_c": float | None,
            "innengeraete": [ {investition_id, innengeraet_id, bezeichnung,
                               leistung_w, soll_temperatur_c, ist_temperatur_c} ],
        }
    """
    b = _LiveBilanz()
    topo = _erhebe_topologie(investitionen, inv_values, inv_live_map)

    # Per-Investition Komponenten
    for inv_id, values in inv_values.items():
        _verbuche_investition(b, topo, inv_id, values, investitionen, inv_live_map, modus_map, aktion_map)

    # ⚠ Die Reihenfolge der Phasen ist tragend (RF-4): die Fahrzeug-Zuordnung
    # setzt `parent_key` vor dem Restverbrauch; PV gesamt erhöht `pv_total_w`
    # vor PV-Gauge und Autarkie; der Netz-Knoten zählt im Restverbrauch als
    # Quelle/Senke; die Netz-Gauge stellt sich per `insert(0, …)` vor die
    # SoC-Gauges der Schleife.
    _ordne_fahrzeuge_zu(b, inv_values, investitionen)
    _pv_gesamt_aus_basis(b, anlage, basis_values)

    einspeisung_w = basis_values.get("einspeisung_w")
    netzbezug_w = basis_values.get("netzbezug_w")
    _netz_komponente(b, einspeisung_w, netzbezug_w)
    _restverbrauch(b, einspeisung_w, netzbezug_w)
    _netz_gauge(b, einspeisung_w, netzbezug_w)
    _pv_leistung_gauge(b, anlage, investitionen)
    _autarkie_gauges(b, einspeisung_w, netzbezug_w)

    warmwasser_temperatur_c = _warmwasser_temperatur(inv_values, investitionen)

    # #263 — Innengeräte einer Split-Klimaanlage: Leistung und Raumtemperaturen.
    #
    # **Reine Anzeige, ausdrücklich ohne Auswertung** (Entscheid Gernots,
    # 2026-08-21). Die Werte gehen in keine Bilanz und in keine Summe: die
    # Leistung eines Innengeräts ist eine **Teilmenge** der Geräteleistung, die
    # oben bereits als Komponente zählt. Sie zusätzlich zu addieren wäre die
    # Doppelzählung, gegen die dieses Modul an drei Stellen absichert.
    #
    # ⚠ Eine Temperatur läuft durch `normalize_to_w` — dort bleibt sie
    # unverändert, weil °C keine bekannte Leistungs-Einheit ist (dieselbe
    # Bauform wie `warmwasser_temperatur_c` darüber, seit v3.24).
    innengeraete_live = _innengeraete_live(inv_values, investitionen)

    return {
        "komponenten": b.komponenten,
        "gauges": b.gauges,
        "summe_erzeugung_kw": round(b.summe_erzeugung, 3),
        "summe_verbrauch_kw": round(b.summe_verbrauch, 3),
        "verbrauch_gesamt_kw": (
            round(b.verbrauch_gesamt_kw, 3) if b.verbrauch_gesamt_kw is not None else None
        ),
        "pv_total_w": b.pv_total_w,
        "warmwasser_temperatur_c": warmwasser_temperatur_c,
        "innengeraete": innengeraete_live,
    }


# ── Die zwei Träger ──────────────────────────────────────────────────────────


@dataclass(frozen=True)
class _Topologie:
    """Was je Poll einmal über den Bestand feststeht — vor der Schleife erhoben, danach nur gelesen."""

    used_leistung_eids: dict[str, str]
    hat_wallbox: bool
    hat_wallbox_investition: bool
    wallbox_entlaedt: bool
    hat_v2h_auto: bool
    bkw_rest_w: dict[str, float]
    erzeuger_ids: frozenset[str]


@dataclass
class _LiveBilanz:
    """Die Akkumulatoren — in der Schleife gefüllt, danach von den Phasen gelesen und weiter beschrieben."""

    komponenten: list[dict] = field(default_factory=list)
    summe_erzeugung: float = 0.0
    summe_verbrauch: float = 0.0
    gauges: list[dict] = field(default_factory=list)
    pv_total_w: float = 0.0
    # Sonstige Erzeuger (z. B. BHKW) speisen hinter den Zähler → gehen in die
    # Netzpunkt-Bilanz (Autarkie/EV), aber NICHT in pv_total_w (PV-Leistungs-%
    # bleibt rein). Konzept Sonstiger Erzeuger 2026-06-22.
    sonstige_erzeugung_w: float = 0.0
    # §9.2: Leistung, die das Haus an Dritte abgibt — kein Eigenverbrauch.
    abgabe_w: float = 0.0
    # P-433-1 (Konzept #433 E7 a): was das Haus verbraucht — gesetzt von
    # `_restverbrauch`, `None` ohne Netzwert (keine erfundene 0, P4).
    verbrauch_gesamt_kw: Optional[float] = None
    # Die Schlüssel der Komponenten, die eine Batterie-Rolle spielen: Speicher
    # UND das V2H-fähige E-Auto (`ist_bidirektional` unten). Nur sie dürfen in
    # `bat_ladung_kw`/`bat_entladung_kw` der Netzpunkt-Bilanz einfließen.
    #
    # ⚠ Das Set ist der SoT dieser Frage — sie wird NICHT aus dem Schlüssel
    # abgeleitet (F-69): Der Filter stand auf dem Präfix `v2h_`, den niemand
    # erzeugt und nie erzeugt hat (`git log --all -S` über die ganze Historie:
    # leer). Ein V2H-Auto heißt `eauto_<id>` — und `eauto_` taugt seinerseits
    # NICHT als Filter, weil ein gewöhnliches, nicht-V2H-Auto denselben
    # Schlüssel trägt (`LIVE_KEY_PREFIX` kennt nur `wallbox`). Die
    # Unterscheidung ist der `v2h_faehig`-Parameter der Investition, nicht der
    # Name; hier weiß der Builder sie ohnehin schon.
    bidirektionale_keys: set[str] = field(default_factory=set)

    # Wallbox-Knoten (Investitions-ID → Komponente) für die E-Auto → Wallbox
    # Zuordnung nach der Schleife (`_fahrzeug_zuordnung`).
    wallbox_knoten: dict[str, dict] = field(default_factory=dict)


# ── Topologie (einmal je Poll) ───────────────────────────────────────────────


def _dedup_prio(investitionen: dict[str, Investition], iid: str) -> int:
    """Sortierschlüssel des Dedup-Vorlaufs: Wallbox vor E-Auto vor allem anderen (#314/#318)."""
    inv = investitionen.get(iid)
    t = inv.typ if inv else None
    return 0 if t == "wallbox" else (1 if t == "e-auto" else 2)


def _erhebe_topologie(
    investitionen: dict[str, Investition],
    inv_values: dict[str, dict[str, float]],
    inv_live_map: dict[str, dict[str, str]],
) -> _Topologie:
    """Dedup-Vorlauf, Wallbox-/V2H-Topologie, BKW-Rest und Erzeuger-Menge — vor der Schleife."""
    # Entity-IDs tracken um Duplikate zu erkennen. WICHTIG: deterministische
    # Wallbox-Priorität (analog Tagesverlauf #318: prioritaet wallbox<eauto).
    # Teilen Wallbox + E-Auto dieselbe `leistung_w`-Entity (gleicher Stromfluss
    # aus zwei Perspektiven), muss die Wallbox die Entity zuerst beanspruchen —
    # sonst hing der Dedup an der Dict-Reihenfolge und ein E-Auto-vor-Wallbox-
    # Setup zählte beide (#314-Folge, Pool-Asymmetrie-Klasse #290/#298/#318).
    used_leistung_eids: dict[str, str] = {}
    for inv_id in sorted(inv_live_map, key=lambda iid: _dedup_prio(investitionen, iid)):
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

    # N-575 — V2H hinter der Wallbox: **die Semantik hängt an der erfassten
    # Topologie, die Buchung am Messpunkt.** Drei Fragen, getrennt erhoben:
    #
    # * `hat_wallbox_investition` — ist eine Wallbox ERFASST? `investitionen`
    #   enthält alle aktiven, auch sensorlose (`live_power_service`,
    #   `aktiv_jetzt()`). Die Semantik der Heimladung darf nicht am Uptime des
    #   Wallbox-Sensors hängen, sonst flackerte die EV-Gauge im 5-s-Takt.
    # * `wallbox_entlaedt` — meldet eine Wallbox LIVE einen negativen Wert?
    #   Dann bucht sie die V2H-Entladung, und das Auto zeigt nur.
    # * `hat_v2h_auto` — steht ein V2H-fähiges Auto im Bestand? Nur dann wird
    #   der Wallbox-Zweig vorzeichentreu (R3); jede andere Installation behält
    #   den Betrag — auch die mit invertiert angeschlossenem Sensor.
    hat_wallbox_investition = any(
        inv.typ == "wallbox" for inv in investitionen.values()
    )
    wallbox_entlaedt = any(
        (investitionen.get(iid) and investitionen.get(iid).typ == "wallbox"
         and vals.get("leistung_w") is not None and vals.get("leistung_w") < 0)
        for iid, vals in inv_values.items()
    )
    hat_v2h_auto = any(
        inv.typ == "e-auto"
        and isinstance(inv.parameter, dict)
        and bool(inv.parameter.get(PARAM_E_AUTO["V2H_FAEHIG"]))
        for inv in investitionen.values()
    )

    # N-536: Ein Balkonkraftwerk mit `pv-module`-Kindern ist Träger wie ein
    # Wechselrichter — seine Kinder tragen die Erzeugung, es selbst nur noch,
    # was sie nicht messen. `bkw_restwerte` ist der SoT dieser Kürzung
    # (ADR-001); der Rest wird hier NICHT verteilt, die kWp-Gewichtung ist eine
    # Tages-Aussage. Ohne abtretendes BKW ist die Map leer und nichts ändert
    # sich — auch nicht für die Anlage, deren BKW-Wechselrichter die einzige
    # Live-Quelle ist (dann ist der Rest sein ganzer Wert).
    bkw_rest_w = bkw_restwerte(
        list(investitionen.values()),
        {k: v.get("leistung_w") for k, v in inv_values.items()},
    )
    # ADR-002/P11: Die Stelle, die „Erzeuger" entscheidet, ruft den Selektor
    # (`bkw_restwerte` oben) — die Erzeuger-Menge wird deshalb HIER gebildet,
    # nicht im Buchungs-Dispatch der Schleife (dort fragt `_verbuche_investition`
    # nur noch die Menge). Dieselbe Form, mit der N-536 die Live-Ausnahmen aus
    # `P11_AUSNAHMEN` gestrichen hat. Verhaltensgleich zu `typ in ERZEUGER_TYPEN`,
    # weil die Schleife `inv = investitionen.get(inv_id)` mit demselben Schlüssel liest.
    erzeuger_ids = frozenset(
        iid for iid, inv in investitionen.items() if inv.typ in ERZEUGER_TYPEN
    )
    return _Topologie(
        used_leistung_eids=used_leistung_eids,
        hat_wallbox=hat_wallbox,
        hat_wallbox_investition=hat_wallbox_investition,
        wallbox_entlaedt=wallbox_entlaedt,
        hat_v2h_auto=hat_v2h_auto,
        bkw_rest_w=bkw_rest_w,
        erzeuger_ids=erzeuger_ids,
    )


# ── Je Investition (der Schleifenkörper) ─────────────────────────────────────


def _inv_id_int(inv_id: str) -> int:
    """Die Investitions-ID als Zahl — ``-1``, wenn der Schlüssel keine ist."""
    # Die Keys von `inv_values` sind Strings, `modus_map` ist nach
    # Investitions-ID (int) geschlüsselt — einmal hier wandeln statt an
    # jeder Lesestelle.
    try:
        return int(inv_id)
    except (TypeError, ValueError):
        return -1


def _verbuche_investition(
    b: _LiveBilanz,
    topo: _Topologie,
    inv_id: str,
    values: dict[str, float],
    investitionen: dict[str, Investition],
    inv_live_map: dict[str, dict[str, str]],
    modus_map: Optional[dict[int, str]],
    aktion_map: Optional[dict[int, str]] = None,
) -> None:
    """Eine Investition in die Bilanz buchen: Knoten, Summen, Batterie-Rolle, SoC-Gauge."""
    inv = investitionen.get(inv_id)
    inv_id_int = _inv_id_int(inv_id)
    if not inv or inv.typ in SKIP_TYPEN:
        return

    val_w = values.get("leistung_w")

    wp_icon = None
    if inv.typ == "waermepumpe":
        val_w, wp_icon = _wp_leistung_und_icon(values, val_w, (modus_map or {}).get(inv_id_int))

    if val_w is None:
        _soc_gauge(b, inv_id, inv, inv.typ, values)
        return

    typ = inv.typ

    # Duplikat-Sensor-Erkennung
    if _e_auto_teilt_wallbox_sensor(inv, inv_id, typ, investitionen, inv_live_map, topo):
        _soc_gauge(b, inv_id, inv, typ, values)
        return

    # E-Auto mit V2H ist bidirektional (Bug #1 v3.25.0: vorher 'nutzt_v2h', Form schreibt 'v2h_faehig')
    ist_v2h = (typ == "e-auto"
               and isinstance(inv.parameter, dict)
               and inv.parameter.get(PARAM_E_AUTO["V2H_FAEHIG"]))
    # Ein Gerät unter „Sonstiges" mit der Kategorie **Speicher** ist
    # ebenfalls bidirektional — so sehen es die beiden Schwesterpfade seit
    # jeher (`live_sensor_config.baue_investitions_serien` und
    # `live_tagesverlauf_service`, je „elif kat == 'speicher'").
    #
    # ⚠ Hier fehlte er (F-70): Er fiel in den `else`-Zweig, und der kennt
    # nur `verbrauch_kw`. Eine ENTLADUNG wurde damit als Verbrauch gebucht
    # statt als Erzeugung — dieselbe 19-Punkte-Lücke wie F-69 (Autarkie
    # 67 % statt 86 % bei 2 kW Entladung), nur mit dem anderen Gerät.
    #
    # ⭐ Der Schlüssel ändert sich dadurch NICHT: `TAGESVERLAUF_KATEGORIE`
    # bildet `sonstiges` auf `"sonstige"` ab, die Komponente heißt weiter
    # `sonstige_<id>`. Es wechselt allein die Seite der Bilanz.
    ist_bidirektional = (
        typ in BIDIREKTIONAL_TYPEN or ist_v2h or _ist_sonstiges(inv, typ, "speicher")
    )

    if inv_id in topo.erzeuger_ids:
        if not _buche_erzeuger(b, inv, inv_id, typ, val_w, investitionen, topo):
            return
    elif _ist_sonstiges(inv, typ, "erzeuger"):
        _buche_sonstigen_erzeuger(b, inv, inv_id, typ, val_w)
    elif _ist_sonstiges(inv, typ, "abgabe"):
        _buche_abgabe(b, inv, inv_id, typ, val_w)
    elif ist_bidirektional:
        _buche_bidirektional(b, inv, inv_id, typ, val_w, ist_v2h, topo)
    else:
        modus = (modus_map or {}).get(inv_id_int) if typ == "waermepumpe" else None
        aktion = (aktion_map or {}).get(inv_id_int) if typ == "waermepumpe" else None
        knoten = _buche_verbraucher(b, inv, inv_id, typ, val_w, wp_icon, modus, topo, aktion)
        if typ == "waermepumpe":
            knoten.update(_wp_geraete_werte(values))

    # SoC-Gauge pro Investition
    _soc_gauge(b, inv_id, inv, typ, values)


def _wp_leistung_und_icon(
    values: dict[str, float],
    val_w: Optional[float],
    modus: Optional[str],
) -> tuple[Optional[float], Optional[str]]:
    """Wärmepumpe: Leistung (Σ der Teilsensoren nur ohne Gesamtleistung) und Icon je Betriebsart."""
    # Wärmepumpe: getrennte Leistungswerte summieren + Icon je Betriebsart.
    #
    # ⚠ **Zwei verschiedene Achsen, und sie schließen sich nicht aus** (N-282):
    #   • die **Leistungssensoren** trennen Heizen/WARMWASSER,
    #   • der **Betriebsmodus** (`climate`-Entität, #263 K-2) trennt
    #     Heizen/Kühlen/Lüften/Entfeuchten.
    # Warmwasser kennt der Modus-Kanon nicht, Kühlen kennen die
    # Leistungssensoren nicht. Deshalb gewinnt je Frage die Quelle, die sie
    # überhaupt beantworten kann (Reihenfolge unten).
    #
    # ⛔ **Hier stand bis zum 27.08., der Modus bleibe aus dem Live-Pfad
    # ausgeschlossen** — *„ihn nur für ein Icon wieder einzuschalten hieße,
    # einen Dauerabruf gegen ein Symbol zu tauschen"*. **Der Einwand war
    # richtig und ist nachgemessen** (State-Cache 3 s gegen Live-Poll 5 s).
    # Aufgelöst wurde er nicht durch Übergehen, sondern weil sich beide
    # Prämissen geändert haben: der Wert hat seit #398 **drei** Verbraucher
    # (Sensor · Klartext · Icon), und er kommt aus
    # `services/betriebsmodus_live.py` mit **eigenem 60-s-Takt** statt im
    # Live-Takt. `live_sensor_config` schließt Zustandsfelder unverändert
    # aus — der Modus läuft nie durch `normalize_to_w`.
    wp_icon = None
    heizen_w = values.get("leistung_heizen_w")
    ww_w = values.get("leistung_warmwasser_w")
    # ⭐ **Die dritte Betriebsart** (N-439, 13.09.2026). `leistung_kuehlen_w`
    # war seit W-13 zuordenbar und wurde hier nie gelesen — mit
    # ausschließlich diesem Sensor blieb `val_w` `None` und die
    # Wärmepumpe fiel ganz aus dem Live-Bild; mit allen dreien stand
    # sie im Kühlbetrieb bei **0,0 kW**, weil die Summe nur zwei
    # Summanden kannte.
    #
    # ⚠ Summiert wird weiterhin NUR, wenn keine Gesamtleistung
    # zugeordnet ist (K1: die Gesamtmenge ist die Wahrheit). Die drei
    # Felder sind disjunkte Momentanwerte desselben Kältekreises
    # (`core/betriebsmodus.py`), ihre Summe ist deshalb die
    # Momentanleistung und keine Doppelzählung.
    kuehl_w = values.get("leistung_kuehlen_w")
    if heizen_w is not None or ww_w is not None or kuehl_w is not None:
        if val_w is None:
            val_w = (heizen_w or 0) + (ww_w or 0) + (kuehl_w or 0)
        h = heizen_w or 0
        w = ww_w or 0
        k = kuehl_w or 0
        if h > 0 or w > 0 or k > 0:
            # Das Symbol folgt der stärksten Betriebsart. `snowflake`
            # ist der Kanon-Name für Kühlen (`BETRIEBSMODUS_ICON`) —
            # Regel 0a: dieselbe Rolle, dasselbe Symbol, egal ob sie
            # über den Leistungssensor oder den Betriebsmodus ins Bild
            # kommt. Bei Gleichstand gewinnt Heizen wie bisher.
            if k > h and k > w:
                wp_icon = BETRIEBSMODUS_ICON[KUEHLEN]
            else:
                wp_icon = "heater" if h >= w else "droplets"
    # Der gemessene Modus schlägt die Leistungs-Heuristik — AUSSER beim
    # Heizen: dort ist „Heizen oder Warmwasser?" die feinere Auskunft,
    # und die hat nur die Heuristik. Fehlt der Modus (keine Zuordnung,
    # `aus`, `unbestimmt`), bleibt alles wie vorher.
    if modus and modus != HEIZEN:
        wp_icon = BETRIEBSMODUS_ICON.get(modus) or wp_icon
    elif modus == HEIZEN and wp_icon is None:
        wp_icon = BETRIEBSMODUS_ICON[HEIZEN]
    return val_w, wp_icon


def _e_auto_teilt_wallbox_sensor(
    inv: Investition,
    inv_id: str,
    typ: str,
    investitionen: dict[str, Investition],
    inv_live_map: dict[str, dict[str, str]],
    topo: _Topologie,
) -> bool:
    """True, wenn ein E-Auto seinen `leistung_w`-Sensor mit einer Wallbox teilt, die ihn zuerst beansprucht hat."""
    leistung_eid = inv_live_map.get(inv_id, {}).get("leistung_w")
    if typ != "e-auto" or not leistung_eid:
        return False
    first_user = topo.used_leistung_eids.get(leistung_eid)
    if not first_user or first_user == inv_id:
        return False
    first_inv = investitionen.get(first_user)
    if first_inv and first_inv.typ == "wallbox":
        logger.debug(
            f"E-Auto {inv.bezeichnung}: gleicher Sensor wie Wallbox "
            f"{first_inv.bezeichnung} — Leistung übersprungen"
        )
        return True
    return False


def _soc_gauge(
    b: _LiveBilanz,
    inv_id: str,
    inv: Investition,
    typ: str,
    values: dict[str, float],
) -> None:
    """Die SoC-Gauge einer Investition — nur für SoC-Typen und nur mit Wert."""
    if typ not in SOC_TYPEN:
        return
    soc_val = values.get("soc")
    if soc_val is not None:
        b.gauges.append({
            "key": f"soc_{inv_id}",
            "label": inv.bezeichnung,
            "wert": round(soc_val, 0),
            "min_wert": 0,
            "max_wert": 100,
            "einheit": "%",
        })


def _ist_sonstiges(inv: Investition, typ: str, kategorie: str) -> bool:
    """Ein `sonstiges`-Gerät mit genau dieser gepflegten Kategorie."""
    return (
        typ == "sonstiges"
        and isinstance(inv.parameter, dict)
        and inv.parameter.get("kategorie") == kategorie
    )


# ── Buchungs-Dispatch: fünf Arme ─────────────────────────────────────────────


def _buche_erzeuger(
    b: _LiveBilanz,
    inv: Investition,
    inv_id: str,
    typ: str,
    val_w: float,
    investitionen: dict[str, Investition],
    topo: _Topologie,
) -> bool:
    """PV-Modul/Balkonkraftwerk als Erzeuger-Knoten — ``False``, wenn ein abtretendes BKW keinen Rest trägt."""
    # N-536: abtretendes Balkonkraftwerk → nur noch der Rest. Messen
    # alle Kinder, ist er 0 und das Gerät bekommt keinen eigenen
    # Knoten: seine Energie steht schon in den Modul-Knoten, und ein
    # Knoten mit 0 W behauptete eine Messung, die es nicht gibt.
    if inv_id in topo.bkw_rest_w:
        val_w = topo.bkw_rest_w[inv_id]
        if val_w <= 0:
            return False
    kw = val_w / 1000
    traeger_id, traeger_label = _traeger(inv, inv_id, investitionen, topo.bkw_rest_w)
    b.komponenten.append({
        "key": f"pv_{inv_id}",
        "label": inv.bezeichnung,
        "icon": TYP_ICON.get(typ, "sun"),
        "erzeugung_kw": round(kw, 3),
        "verbrauch_kw": None,
        # kWp über den SoT-Dispatcher (ADR-002/P3-a): ohne ihn fehlte
        # bei nur im `parameter` gepflegter Nennleistung (#229) der
        # Auslastungsbalken im Live-Dashboard ersatzlos. `or None`
        # hält die Semantik „nicht ermittelbar" (statt 0 kWp) — das
        # Frontend blendet die Auslastung dann wie bisher aus.
        "leistung_kwp": get_erzeuger_kwp(inv) or None,
        # #341/#348 — Merkmale für die Gruppierung im Client. Reine
        # Anreicherung: keine Summe und kein Residual liest sie.
        "typ": typ,
        "ausrichtung_label": ausrichtung_label(inv),
        "traeger_id": traeger_id,
        # #341/#348 A1b: der Name des Trägers, damit die Gruppe im
        # Client „<Wechselrichter> (n)" heißt statt „PV-Gruppe 1".
        "traeger_label": traeger_label,
    })
    b.summe_erzeugung += kw
    b.pv_total_w += val_w
    return True


def _buche_sonstigen_erzeuger(
    b: _LiveBilanz, inv: Investition, inv_id: str, typ: str, val_w: float,
) -> None:
    """Sonstiger Erzeuger (BHKW) als eigener Erzeugungs-Knoten."""
    # Sonstiger Erzeuger (BHKW) — eigene Erzeugungs-Komponente, fließt in
    # die Netzpunkt-Bilanz (summe_erzeugung + Autarkie unten), aber NICHT
    # in pv_total_w (kein PV → keine kWp/PV-%, Achsen-Trennung).
    kw = val_w / 1000
    b.komponenten.append({
        "key": f"sonstige_{inv_id}",
        "label": inv.bezeichnung,
        "icon": TYP_ICON.get(typ, "wrench"),
        "erzeugung_kw": round(kw, 3),
        "verbrauch_kw": None,
        "leistung_kwp": None,
        "typ": typ,
        "kategorie": _sonstiges_kategorie(inv),
    })
    b.summe_erzeugung += kw
    b.sonstige_erzeugung_w += val_w


def _buche_abgabe(
    b: _LiveBilanz, inv: Investition, inv_id: str, typ: str, val_w: float,
) -> None:
    """Abgabe an Dritte (§9.2) als Verbrauchs-Knoten, der vom Eigenverbrauch wieder abgezogen wird."""
    # §9.2: Abgabe an Dritte — steht auf der Verbrauchsseite des
    # Flusses (die Energie verlässt das Haus), zählt aber NICHT als
    # Eigenverbrauch: die Bilanz unten zieht `abgabe_w` wieder ab.
    kw = abs(val_w) / 1000
    b.komponenten.append({
        "key": f"sonstige_{inv_id}",
        "label": inv.bezeichnung,
        "icon": TYP_ICON.get(typ, "wrench"),
        "erzeugung_kw": None,
        "verbrauch_kw": round(kw, 3),
        # Bewusst NICHT im Response-Modell (`LiveKomponente`) — FastAPI
        # verwirft das Feld still, und serverseitig liest es niemand
        # (`abgabe_keys` baut aus den Investitionen neu). Der
        # Buchungszweig einer Sonstigen kommt für den Client allein
        # aus `kategorie` (#341/#348).
        "abgabe": True,
        "typ": typ,
        "kategorie": _sonstiges_kategorie(inv),
    })
    b.summe_verbrauch += kw
    b.abgabe_w += abs(val_w)


def _buche_bidirektional(
    b: _LiveBilanz,
    inv: Investition,
    inv_id: str,
    typ: str,
    val_w: float,
    ist_v2h,
    topo: _Topologie,
) -> None:
    """Speicher, V2H-Auto, Sonstiges-Speicher: Richtung, Batterie-Rolle (N-575 R1/R2), Kapazität."""
    kw = abs(val_w) / 1000
    ist_ladung = val_w > 0
    kategorie = TAGESVERLAUF_KATEGORIE.get(typ, "batterie")
    # N-575 — ein V2H-Auto hinter einer ERFASSTEN Wallbox:
    #
    # * R1 Laden: die Heimladung ist Hausverbrauch, nie Batterie-Ladung
    #   — sie wird überwiegend verfahren und kehrt nicht zurück. Liefert
    #   eine Wallbox live, bucht SIE (das Auto zeigt nur, `parent_key`
    #   unten); liefert keine, bucht das Auto als gewöhnlicher
    #   Verbraucher — derselbe Failover wie beim Nicht-V2H-Auto im
    #   `else`-Zweig.
    # * R2 Entladen: die Batterie-Rolle verdient nur die gemessene
    #   Entladung, und sie wird EINMAL gebucht — meldet die Wallbox sie
    #   (`wallbox_entlaedt`), bucht die Wallbox, und das Auto zeigt nur
    #   seine Richtung (`erzeugung_kw`, ohne Summe, ohne Rolle).
    #
    # Ohne Wallbox-Investition bleibt alles wie F-69: der
    # vorzeichenbehaftete Auto-Sensor ist dann der einzige Zugang zum
    # Ladepunkt, und das Auto ist messbar ein Speicher am Hausanschluss.
    hinter_wallbox = bool(ist_v2h) and topo.hat_wallbox_investition
    if not hinter_wallbox:
        traegt_rolle = True
    elif ist_ladung:
        traegt_rolle = False
    else:
        traegt_rolle = not topo.wallbox_entlaedt
    if traegt_rolle:
        b.bidirektionale_keys.add(f"{kategorie}_{inv_id}")
    komp_bidi = {
        "key": f"{kategorie}_{inv_id}",
        "label": inv.bezeichnung,
        "icon": TYP_ICON.get(typ, "battery"),
        "erzeugung_kw": round(kw, 3) if not ist_ladung else None,
        "verbrauch_kw": round(kw, 3) if ist_ladung else None,
        "typ": typ,
    }
    # Der Sonstiges-Speicher läuft durch diesen Zweig und heißt
    # trotzdem `sonstige_<id>` (F-70) — er trägt seine Kategorie wie
    # die drei anderen Sonstiges-Zweige.
    if typ == "sonstiges":
        komp_bidi["kategorie"] = _sonstiges_kategorie(inv)
    # Kapazität nur am echten Speicher-Knoten (`batterie_*`) — über den
    # SoT-Helper, nie `inv.leistung_kwp` (Mehrzweckfeld). Sie gewichtet
    # im Client den Gruppen-Ladestand. (Keyword-Form statt Index-
    # Zuweisung: der P3-a-Wächter `test_speicher_kapazitaet_sot` sucht
    # den Parameter-Schlüssel als Zeichenkette und hielte das
    # gleichnamige Response-Feld für einen Rohzugriff.)
    if kategorie == "batterie":
        komp_bidi.update(
            kapazitaet_kwh=get_speicher_nutzbare_kapazitaet_kwh(inv) or None,
        )
    b.komponenten.append(komp_bidi)
    if ist_ladung:
        if not (hinter_wallbox and topo.hat_wallbox):
            b.summe_verbrauch += kw
    elif traegt_rolle:
        b.summe_erzeugung += kw


def _buche_verbraucher(
    b: _LiveBilanz,
    inv: Investition,
    inv_id: str,
    typ: str,
    val_w: float,
    wp_icon: Optional[str],
    modus: Optional[str],
    topo: _Topologie,
    aktion: Optional[str] = None,
) -> dict:
    """Alle übrigen Geräte: Verbraucher-Knoten, Betriebsmodus-Klartext, Wallbox als V2H-Quelle (N-575 R2/R3).

    Gibt den gebuchten Knoten zurück (P-433-3 S1: der Aufrufer hängt die Gerätewerte einer Wärmepumpe an).
    """
    kw = abs(val_w) / 1000
    prefix = LIVE_KEY_PREFIX.get(typ, TAGESVERLAUF_KATEGORIE.get(typ, typ))
    komp_key = f"{prefix}_{inv_id}"
    # N-575 (R2/R3) — die Wallbox eines V2H-Haushalts meldet eine
    # Entladung: sie ist dann die QUELLE und bucht mit Batterie-Rolle
    # (`bat_entladung` ⇒ Eigenverbrauch). Vorzeichentreu NUR bei
    # `hat_v2h_auto`: sonst bleibt der Betrag der Schutz gegen einen
    # invertiert angeschlossenen Sensor, und jede Nicht-V2H-Anlage
    # rechnet bitgleich. Im V2H-Haushalt korrigiert ein invertierter
    # Sensor über das `invertieren`-Flag seiner Datenquelle.
    # Der Live-Tagesverlauf derselben Seite zeichnet dieselbe Entladung
    # bis auf Weiteres als Senke — `live_tagesverlauf_service.py`,
    # Senken-Betrag; bewusst nicht mitgefixt, Entscheid 28.09.
    wallbox_quelle = typ == "wallbox" and topo.hat_v2h_auto and val_w < 0
    if wallbox_quelle:
        b.bidirektionale_keys.add(komp_key)
    komp_sonst = {
        "key": komp_key,
        "label": inv.bezeichnung,
        "icon": wp_icon or TYP_ICON.get(typ, "wrench"),
        "erzeugung_kw": round(kw, 3) if wallbox_quelle else None,
        "verbrauch_kw": None if wallbox_quelle else round(kw, 3),
        # Klartext statt Kanon-Enum: die Deutung gehört in den Kanon,
        # nicht in eine zweite Tabelle im Client ([[feedback_typ_labels_pattern]]).
        # Ohne Modus steht hier `None` — kein „—", keine leere Zeile.
        #
        # ⚠ `unbestimmt` bekommt ebenfalls `None` (MartyBr, T89667 #230):
        # Die Liste dazu steht im Kanon, samt Begründung — sie ist die
        # des fehlenden Icons, eine Ebene lauter. Der ROHWERT
        # `betriebsmodus` bleibt unangetastet: Wer den Zustand
        # auswertet, soll `unbestimmt` sehen; nur die **Anzeige**
        # schweigt.
        "betriebsmodus": modus,
        "betriebsmodus_label": (
            BETRIEBSMODUS_LABEL.get(modus)
            if modus and modus not in BETRIEBSMODUS_LIVE_OHNE_KLARTEXT
            else None
        ),
        "typ": typ,
    }
    # P-433-1 (E6): die gemessene Ruhe («Leerlauf») als Zusatz neben dem
    # Kanon-Wert — nur, wo ein Klartext steht; der Kanon-Wert bleibt, wie er ist.
    # Die Schlüssel stehen nur am Gerät, das eine Aktion meldet.
    if aktion is not None and komp_sonst["betriebsmodus_label"]:
        komp_sonst["betriebsmodus_aktion"] = aktion
        komp_sonst["betriebsmodus_aktion_label"] = BETRIEBSMODUS_AKTION_LABEL[aktion]
    # Vierter Sonstiges-Zweig (Verbraucher, Zähler, fehlende oder
    # unbekannte Kategorie) — dieselbe Kategorie-Quelle wie oben.
    if typ == "sonstiges":
        komp_sonst["kategorie"] = _sonstiges_kategorie(inv)
    b.komponenten.append(komp_sonst)
    # R4 (N-575): richtungsunabhängig — sonst verlören ladende Kinder
    # bei entladender Wallbox ihren `parent_key` (Layout + Residual).
    if typ == "wallbox":
        b.wallbox_knoten[inv_id] = komp_sonst
    if wallbox_quelle:
        b.summe_erzeugung += kw
    # E-Auto nur ausschließen, wenn es tatsächlich unter eine Wallbox
    # gepoolt wird (hat_wallbox → parent_key unten). Ohne Wallbox ist es
    # ein realer Verbraucher und zählt normal (konsistent mit gesamt_senken,
    # das nur parent_key-Kinder ausschließt) — #314-Folge.
    elif not (typ == "e-auto" and topo.hat_wallbox):
        b.summe_verbrauch += kw
    return komp_sonst


def _wp_geraete_werte(values: dict[str, float]) -> dict:
    """Vorlauf, Rücklauf, Spreizung, Warmwasser-Temperatur und Heizstab-Leistung **dieses** Geräts (P-433-3 S1).

    Reine Anzeige für den Hub-Überblick: kein Wert fließt in eine Summe, ein Residual oder eine Gauge — die
    Heizstab-Leistung ist ein Teil der Geräteleistung, die der Knoten schon trägt. Die Schlüssel stehen nur, wo
    ein Wert kommt (Muster `betriebsmodus_aktion`); ohne Zuordnung liefert das Response-Modell `None` (P4).
    °C laufen durch `normalize_to_w` unverändert (keine Leistungs-Einheit), W sind dort schon W.

    ⚠ Das anlagenweite `warmwasser_temperatur_c` (`_warmwasser_temperatur`, erste WP mit Wert) bleibt daneben
    bestehen — es speist «Auf einen Blick» in Cockpit Live (E-P3-7).
    """
    # Registry-Feld → Schlüssel am Knoten (`LiveKomponente`), Nachkommastellen. Die Feldnamen stehen hier im Code,
    # nicht in einer Tabelle daneben — der Wächter `test_jedes_feld_hat_eine_auswertung` liest genau diesen Körper.
    vorlauf, ruecklauf = values.get("vorlauf_temperatur_c"), values.get("ruecklauf_temperatur_c")
    rund = (lambda w: None if w is None else round(w, 1))
    roh = {
        "vorlauf_c": (vorlauf, 1),
        "ruecklauf_c": (ruecklauf, 1),
        # Spreizung aus dem Layer (eine Formel, ein Ort) — aus den ANGEZEIGTEN Werten: neben «34,2 → 29,1 °C»
        # steht 5,1 K, nicht 5,2 K aus 34,23 − 29,07 (Abweichung ≤ 0,1 K, für eine Augenblicksanzeige ohne Belang).
        "spreizung_k": (spreizung_k(rund(vorlauf), rund(ruecklauf)), 1),
        "warmwasser_c": (values.get("warmwasser_temperatur_c"), 1),
        "heizstab_w": (values.get("heizstab_leistung_w"), 0),
    }
    return {schluessel: round(wert, stellen) for schluessel, (wert, stellen) in roh.items() if wert is not None}


# ── Nach der Schleife: Zuordnung, Basis, Netz, Restverbrauch, Gauges ─────────


def _ordne_fahrzeuge_zu(
    b: _LiveBilanz,
    inv_values: dict[str, dict[str, float]],
    investitionen: dict[str, Investition],
) -> None:
    """E-Autos ihren Wallboxen zuordnen: `parent_key` am Auto-Knoten, `fahrzeuge` an der Wallbox."""
    # E-Auto → Wallbox Zuordnung — EINE Quelle für `parent_key` (Layout +
    # Residual) und `fahrzeuge` (Wallbox-Kachel, #341/#348), auf
    # Investitions-Ebene statt über die Knotenliste: sie enthält auch die Autos
    # OHNE eigenen Knoten (nur Ladestand; Leistungssensor mit der Wallbox
    # geteilt). `parent_key` bekommt weiterhin genau jeder `eauto_`-Knoten,
    # sobald eine Wallbox live liefert — welcher Wallbox er zugeordnet ist,
    # ändert keine Summe und kein Residual (beide schließen JEDES Kind aus).
    if not b.wallbox_knoten:
        return
    komp_nach_key = {k["key"]: k for k in b.komponenten}
    autos = [
        iid for iid in inv_values
        if investitionen.get(iid) is not None
        and investitionen[iid].typ == "e-auto"
    ]
    zuordnung = _fahrzeug_zuordnung(list(b.wallbox_knoten), autos)
    # Eindeutig nur bei genau EINER live liefernden Wallbox. Bekannte
    # Grenze: eine zweite, gerade offline Wallbox macht die Zuordnung
    # scheinbar eindeutig (Vorlage Bau A §A1).
    zuordnung_art = "eindeutig" if len(b.wallbox_knoten) == 1 else "geschaetzt"
    for wb_komp in b.wallbox_knoten.values():
        wb_komp["fahrzeuge"] = []
        wb_komp["fahrzeuge_zuordnung"] = zuordnung_art
    for auto_id in sorted(autos, key=_id_rang):
        wb_komp = b.wallbox_knoten[zuordnung[auto_id]]
        auto_komp = komp_nach_key.get(f"eauto_{auto_id}")
        if auto_komp is not None:
            auto_komp["parent_key"] = wb_komp["key"]
        wb_komp["fahrzeuge"].append(
            _fahrzeug(investitionen[auto_id], inv_values[auto_id], auto_komp)
        )


def _ist_pv_komponente(k) -> bool:
    """Ein Knoten mit PV-Präfix aus der zentralen Liste des Berechnungs-Layers."""
    key = k.key if hasattr(k, "key") else k.get("key", "")
    return any(key.startswith(p) for p in PV_KOMPONENTEN_PREFIXE)


def _pv_gesamt_aus_basis(
    b: _LiveBilanz,
    anlage: Anlage,
    basis_values: dict[str, float],
) -> None:
    """Der Knoten „PV Gesamt" aus dem Basis-Sensor — nur ohne einzelne PV-Knoten."""
    # PV Gesamt aus Basis (wenn kein individueller PV-Sensor vorhanden).
    # Erzeuger (PV-Module + Balkonkraftwerk) tragen in diesem Live-Keyspace
    # einheitlich den `pv_`-Präfix; die Prefix-Quelle kommt zentral aus dem
    # Berechnungs-Layer (ADR-001) statt als eigenes Literal.
    has_individual_pv = any(_ist_pv_komponente(k) for k in b.komponenten)
    pv_gesamt_w_val = basis_values.get("pv_gesamt_w")
    if pv_gesamt_w_val is not None and not has_individual_pv:
        kw = pv_gesamt_w_val / 1000
        gesamt_kwp = anlage.leistung_kwp or 0
        b.komponenten.append({
            "key": "pv_gesamt",
            "label": f"PV Gesamt{f' {gesamt_kwp} kWp' if gesamt_kwp else ''}",
            "icon": "sun",
            "erzeugung_kw": round(kw, 3),
            "verbrauch_kw": None,
        })
        b.summe_erzeugung += kw
        b.pv_total_w += pv_gesamt_w_val


def _netz_komponente(
    b: _LiveBilanz,
    einspeisung_w: Optional[float],
    netzbezug_w: Optional[float],
) -> None:
    """Der Netz-Knoten: Bezug als Quelle, Einspeisung als Senke."""
    # Netz-Komponente
    if einspeisung_w is not None or netzbezug_w is not None:
        einsp_kw = (einspeisung_w or 0) / 1000
        bezug_kw = (netzbezug_w or 0) / 1000
        b.komponenten.append({
            "key": "netz",
            "label": "Stromnetz",
            "icon": "zap",
            "erzeugung_kw": round(bezug_kw, 3) if bezug_kw > 0 else None,
            "verbrauch_kw": round(einsp_kw, 3) if einsp_kw > 0 else None,
        })
        if bezug_kw > 0:
            b.summe_erzeugung += bezug_kw
        if einsp_kw > 0:
            b.summe_verbrauch += einsp_kw


def _restverbrauch(
    b: _LiveBilanz,
    einspeisung_w: Optional[float],
    netzbezug_w: Optional[float],
) -> None:
    """Der Knoten „Restverbrauch" (Schlüssel `haushalt`) als Residual aller Quellen und Senken."""
    # Haushalt = Residual
    # N-575 (R2): symmetrisch zur Senken-Regel darunter — ein Kind mit
    # `parent_key`, das KEINE Batterie-Rolle trägt, zeigt nur (die V2H-
    # Entladung, die die Wallbox schon als Quelle bucht). Ohne den Ausschluss
    # zählte derselbe Fluss zweimal ins Residual.
    gesamt_quellen = sum(
        k.get("erzeugung_kw") or 0 for k in b.komponenten
        if not (k.get("parent_key") and k["key"] not in b.bidirektionale_keys)
    )
    gesamt_senken = sum(
        k.get("verbrauch_kw") or 0 for k in b.komponenten
        if not k.get("parent_key")
    )
    hat_netzwert = einspeisung_w is not None or netzbezug_w is not None
    if hat_netzwert:
        b.verbrauch_gesamt_kw = _verbrauch_gesamt(b, gesamt_quellen, einspeisung_w)
    if gesamt_quellen > 0 and hat_netzwert:
        haushalt_kw = max(0, gesamt_quellen - gesamt_senken)
        b.komponenten.append({
            "key": "haushalt",
            "label": "Restverbrauch",  # N-603 (03.10.2026): Label, der Schlüssel bleibt
            "icon": "home",
            "erzeugung_kw": None,
            "verbrauch_kw": round(haushalt_kw, 3),
        })
        b.summe_verbrauch += haushalt_kw


def _verbrauch_gesamt(
    b: _LiveBilanz, gesamt_quellen: float, einspeisung_w: Optional[float],
) -> float:
    """Was das Haus jetzt verbraucht (P-433-1, Konzept #433 E7 a), in kW.

    ``Σ Quellen − Einspeisung − Σ Speicherladung − Abgabe`` aus denselben Summen
    wie der Restverbrauch: Quellen sind dieselben wie dort, die Speicherladung
    ist die der Knoten mit Batterie-Rolle (`bidirektionale_keys`, dieselbe Menge
    wie in `_autarkie_gauges`), die Abgabe `abgabe_w`. Nachts (Erzeugung 0) ist
    das Bezug − Netzladung des Speichers.

    ⚠ **Nicht** der Autarkie-Nenner (`_autarkie_gauges`, EV + Bezug): der steht
    hinter ``erzeugung_w > 0`` und zwei Klemmen. Ohne Klemme sind beide gleich.
    Die eine Klemme hier ist die des Restverbrauchs (`max(0, …)`): ein negativer
    Hausverbrauch entsteht nur aus Messversatz zwischen den Sensoren.
    """
    speicherladung_kw = sum(
        k.get("verbrauch_kw") or 0 for k in b.komponenten
        if k["key"] in b.bidirektionale_keys
    )
    einspeisung_kw = (einspeisung_w or 0) / 1000 if (einspeisung_w or 0) > 0 else 0.0
    return max(0.0, gesamt_quellen - einspeisung_kw - speicherladung_kw - b.abgabe_w / 1000)


def _netz_gauge(
    b: _LiveBilanz,
    einspeisung_w: Optional[float],
    netzbezug_w: Optional[float],
) -> None:
    """Die Netz-Gauge — vorn in der Gauge-Liste."""
    # Netz-Gauge
    if einspeisung_w is not None or netzbezug_w is not None:
        netto_w = (netzbezug_w or 0) - (einspeisung_w or 0)
        max_val = max(abs(einspeisung_w or 0), abs(netzbezug_w or 0), 1)
        b.gauges.insert(0, {
            "key": "netz",
            "label": "Netz",
            "wert": round(netto_w, 0),
            "min_wert": -max_val,
            "max_wert": max_val,
            "einheit": "W",
        })


def _pv_leistung_gauge(
    b: _LiveBilanz,
    anlage: Anlage,
    investitionen: dict[str, Investition],
) -> None:
    """Die PV-Leistungs-Gauge in % der heute aktiven kWp (F-58)."""
    # PV-Leistung in % von kWp
    # F-58: Σ der heute aktiven Erzeuger statt des gepflegten Referenzwerts.
    # `mit_bkw=True`, weil `pv_total_w` alle PV-Komponenten summiert und ein
    # Balkonkraftwerk im Live-Keyspace zur Kategorie `pv` gehört
    # (`live_sensor_config.py`). Bei zu kleinem Nenner stand die Auslastung
    # dauerhaft am 120-%-Anschlag.
    kwp = anlagen_kwp(
        list(investitionen.values()), date.today(),
        mit_bkw=True, referenzwert=anlage.leistung_kwp,
    )
    if b.pv_total_w > 0 and kwp and kwp > 0:
        pv_pct = b.pv_total_w / 1000 / kwp * 100
        b.gauges.append({
            "key": "pv_leistung",
            "label": "PV-Leistung",
            "wert": round(min(pv_pct, 120), 0),
            "min_wert": 0,
            "max_wert": 120,
            "einheit": "% kWp",
        })


def _autarkie_gauges(
    b: _LiveBilanz,
    einspeisung_w: Optional[float],
    netzbezug_w: Optional[float],
) -> None:
    """Autarkie- und Eigenverbrauchs-Gauge aus der Netzpunkt-Bilanz (Live, kW)."""
    # Autarkie + Eigenverbrauchsquote — Netzpunkt-Bilanz nutzt die Gesamterzeugung
    # hinter dem Zähler (PV + sonstige Erzeuger wie BHKW), nicht nur PV. Die
    # PV-Leistungs-Gauge oben bleibt rein (pv_total_w). Konzept Sonstiger Erzeuger.
    erzeugung_w = b.pv_total_w + b.sonstige_erzeugung_w
    if erzeugung_w > 0 and (einspeisung_w is not None or netzbezug_w is not None):
        erzeugung_kw = erzeugung_w / 1000
        bat_ladung_kw = sum(
            k.get("verbrauch_kw") or 0 for k in b.komponenten
            if k["key"] in b.bidirektionale_keys
        )
        bat_entladung_kw = sum(
            k.get("erzeugung_kw") or 0 for k in b.komponenten
            if k["key"] in b.bidirektionale_keys
        )
        direktverbrauch_kw = max(0, erzeugung_kw - (einspeisung_w or 0) / 1000 - bat_ladung_kw)
        # §9.2: abgegebene Leistung ist kein Eigenverbrauch.
        eigenverbrauch_kw = max(0.0, direktverbrauch_kw + bat_entladung_kw - b.abgabe_w / 1000)
        gesamt_verbrauch_kw = eigenverbrauch_kw + (netzbezug_w or 0) / 1000

        if gesamt_verbrauch_kw > 0:
            autarkie = eigenverbrauch_kw / gesamt_verbrauch_kw * 100
            b.gauges.append({
                "key": "autarkie",
                "label": "Autarkie",
                "wert": round(min(autarkie, 100), 0),
                "min_wert": 0,
                "max_wert": 100,
                "einheit": "%",
            })

        if erzeugung_kw > 0:
            ev_quote = eigenverbrauch_kw / erzeugung_kw * 100
            b.gauges.append({
                "key": "eigenverbrauch",
                "label": "Eigenverbr.",
                "wert": round(min(ev_quote, 100), 0),
                "min_wert": 0,
                "max_wert": 100,
                "einheit": "%",
            })


def _warmwasser_temperatur(
    inv_values: dict[str, dict[str, float]],
    investitionen: dict[str, Investition],
) -> Optional[float]:
    """Die Warmwasser-Temperatur der ersten Wärmepumpe, die eine meldet."""
    # Warmwasser-Temperatur
    for inv_id, values in inv_values.items():
        inv = investitionen.get(inv_id)
        if inv and inv.typ == "waermepumpe":
            ww_temp = values.get("warmwasser_temperatur_c")
            if ww_temp is not None:
                return round(ww_temp, 1)
    return None


# ── Merkmale je Knoten (#341/#348) ──────────────────────────────────────────
#
# Reine Anreicherung für die Gruppierung im Client (Vorlage Bau A §A1): keine
# dieser Funktionen fließt in eine Summe, ein Residual oder eine Gauge. Jedes
# Feld ist im Response-Modell `LiveKomponente` deklariert — sonst verwürfe
# FastAPI es still (die Falle, in der `abgabe` bis heute steckt).

#: Parent-Typen, die für PV-Knoten „Träger" sind: der Wechselrichter und — seit
#: N-536 — das Balkonkraftwerk mit `pv-module`-Kindern.
_TRAEGER_TYPEN = frozenset({"wechselrichter", "balkonkraftwerk"})


def _id_rang(inv_id: str) -> tuple:
    """Sortierschlüssel nach Investitions-ID — numerisch, wo sie eine Zahl ist.

    Die Keys von `inv_values`/`investitionen` sind `str(inv.id)`; lexikalisch
    stünde „10" vor „9".
    """
    try:
        return (0, int(inv_id), "")
    except (TypeError, ValueError):
        return (1, 0, str(inv_id))


def _fahrzeug_zuordnung(wallbox_ids: list[str], auto_ids: list[str]) -> dict[str, str]:
    """Auto → Wallbox, deterministisch: beide Seiten nach ID sortiert, reihum.

    Das Datenmodell kennt keine Zuordnung Auto → Wallbox
    (`ERLAUBTE_PARENT_TYPEN` hat keinen E-Auto-Eintrag); bei genau einer
    Wallbox ist sie trotzdem eindeutig, bei mehreren eine Schätzung, die der
    Client als solche ausweist (`fahrzeuge_zuordnung`). Deterministisch heißt:
    unabhängig von der Reihenfolge, in der die Live-Werte ankommen — dieselbe
    Anlage liefert bei jedem Poll dieselbe Zuordnung.
    """
    wallboxen = sorted(wallbox_ids, key=_id_rang)
    return {
        auto_id: wallboxen[i % len(wallboxen)]
        for i, auto_id in enumerate(sorted(auto_ids, key=_id_rang))
    }


def _fahrzeug(inv: Investition, werte: dict[str, float], knoten: Optional[dict]) -> dict:
    """Ein Auto in der Wallbox-Kachel: Name, Ladestand, Leistung, V2H.

    ``kw`` ist **vorzeichenbehaftet** — positiv lädt das Auto, negativ gibt es
    ab (V2H) — und kommt aus seinem eigenen Knoten. Ohne Knoten (nur Ladestand;
    Leistungssensor mit der Wallbox geteilt) ist es ``None``: die Leistung des
    Autos ist dann nicht getrennt gemessen, nicht 0 (ADR-002/P4).
    """
    kw: Optional[float] = None
    if knoten is not None:
        if knoten.get("verbrauch_kw") is not None:
            kw = knoten["verbrauch_kw"]
        elif knoten.get("erzeugung_kw") is not None:
            kw = -knoten["erzeugung_kw"]
    soc = werte.get("soc")
    return {
        "investition_id": inv.id,
        "label": inv.bezeichnung,
        # Dieselbe Rundung wie die SoC-Gauge desselben Autos.
        "soc": round(soc, 0) if soc is not None else None,
        "kw": kw,
        "v2h": bool(
            isinstance(inv.parameter, dict)
            and inv.parameter.get(PARAM_E_AUTO["V2H_FAEHIG"])
        ),
    }


def _sonstiges_kategorie(inv: Investition) -> Optional[str]:
    """Die gepflegte Kategorie eines `sonstiges`-Geräts — roh, ``None`` ohne Pflege.

    Der Client leitet daraus den Buchungszweig ab (erzeuger · abgabe · speicher
    · alles andere als Verbraucher), genau wie die vier Zweige oben.
    """
    param = inv.parameter
    if isinstance(param, dict):
        kat = param.get("kategorie")
        if isinstance(kat, str) and kat:
            return kat
    return None


def _traeger(
    inv: Investition,
    inv_id: str,
    investitionen: dict[str, Investition],
    bkw_rest_w: dict[str, float],
) -> tuple[Optional[int], Optional[str]]:
    """Der Träger eines PV-Knotens: Wechselrichter oder Balkonkraftwerk — ID und Name.

    * Ein `pv-module` mit Parent vom Typ WR oder BKW trägt dessen ID und
      Bezeichnung.
    * Der **Rest-Knoten** eines abtretenden Balkonkraftwerks (N-536) trägt
      seine **eigene** ID und Bezeichnung — sonst landete der Rest getrennt
      von seinen Modulen.
    * ⛔ Nie über `parent_key`: das Feld zeichnet im Client eine Linie zum
      Parent statt zum Haus.
    * Ein Parent, der nicht in `investitionen` steht (stillgelegt), liefert
      ``(None, None)`` — die Kachel degradiert definiert auf die letzte Stufe.

    ⭐ ID und Name kommen aus EINER Entscheidung (#341/#348 A1b): das Label ist
    genau dann gesetzt, wenn die ID es ist — eine Gruppe mit ID, aber ohne
    Namen, oder ein Name ohne Gruppe, kann so nicht entstehen.
    """
    if inv_id in bkw_rest_w:
        return inv.id, inv.bezeichnung
    parent_id = inv.parent_investition_id
    if parent_id is None:
        return None, None
    parent = investitionen.get(str(parent_id))
    if parent is not None and parent.typ in _TRAEGER_TYPEN:
        return parent_id, parent.bezeichnung
    return None, None


def _innengeraete_live(
    inv_values: dict[str, dict[str, float]],
    investitionen: dict[str, Investition],
) -> list[dict]:
    """Die Live-Werte je Innengerät — Bezeichnung, Leistung, Raum-Ist/Soll.

    Nur Geräte, für die tatsächlich ein Wert ankommt: ohne zugeordneten Sensor
    steht dort nichts, nicht eine Null (ADR-002/P4). Ein Innengerät ohne jeden
    Wert erscheint deshalb gar nicht.
    """
    from backend.core.field_definitions import feld_je_innengeraet
    from backend.core.investition_parameter import lade_innengeraete

    out: list[dict] = []
    for inv_id, values in inv_values.items():
        inv = investitionen.get(inv_id)
        if not inv or inv.typ != "waermepumpe":
            continue
        for geraet in lade_innengeraete(inv):
            gid = geraet["id"]
            leistung = values.get(feld_je_innengeraet("leistung_w", gid))
            soll = values.get(feld_je_innengeraet("soll_temperatur_c", gid))
            ist = values.get(feld_je_innengeraet("ist_temperatur_c", gid))
            if leistung is None and soll is None and ist is None:
                continue
            out.append({
                "investition_id": int(inv_id),
                "innengeraet_id": gid,
                "bezeichnung": geraet["bezeichnung"],
                "leistung_w": round(leistung, 0) if leistung is not None else None,
                "soll_temperatur_c": round(soll, 1) if soll is not None else None,
                "ist_temperatur_c": round(ist, 1) if ist is not None else None,
            })
    return out
