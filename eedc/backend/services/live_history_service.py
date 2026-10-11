"""
Live History Service - HA-History-Abfragen, Trapez-Integration, Tages-kWh.

Ausgelagert aus live_power_service.py (Schritt 3 des Refactorings).
Enthält:
  - get_history_normalized: History holen + kW→W normalisieren
  - apply_invert_to_history: Vorzeichen-Invertierung auf History
  - trapez_kwh: Energie aus Leistungsverlauf (Trapezregel)
  - get_tages_kwh: Tages-kWh aus HA-History (Kategorien + Komponenten)
  - safe_get_tages_kwh: Wrapper mit Cache + MQTT-Fallback
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from types import SimpleNamespace
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.anlage import Anlage
from backend.models.investition import Investition
from backend.utils.investition_filter import aktiv_jetzt
from backend.core.berechnungen.energie import PV_KOMPONENTEN_PREFIXE
from backend.core.berechnungen.erzeuger_traeger import (
    BKW_TYP,
    kuerze_bkw_in_werte_map,
)
from backend.services.live_sensor_config import (
    UNIT_TO_W,
    ERZEUGER_TYPEN,
    SKIP_TYPEN,
    LIVE_KEY_PREFIX,
    TAGESVERLAUF_KATEGORIE,
    extract_live_config,
)
from backend.services.snapshot.keys import (
    extract_quellen_energy,
    resolve_energy_ha_eid,
)

logger = logging.getLogger(__name__)


# ── Hilfsfunktionen (ehemals Closures in _get_tages_kwh) ─────────────

# Einheiten für Energie-Sensoren
_KWH_UNITS = {"kWh", "Wh", "MWh"}
_KWH_SCALE = {"kWh": 1.0, "Wh": 0.001, "MWh": 1000.0}

# Monatsabschluss-Sensoren: typ → (sensor_field, comp_key_prefix)
_MONATSABSCHLUSS_KWH: dict[str, tuple[str, str]] = {
    "waermepumpe": ("stromverbrauch_kwh", "waermepumpe"),
    "wallbox":     ("ladung_kwh",          "wallbox"),
}


def _feld_eid(conf: object) -> Optional[str]:
    """Extrahiert entity_id aus FeldMapping-Dict {strategie, sensor_id}."""
    if isinstance(conf, dict) and conf.get("strategie") == "sensor":
        return conf.get("sensor_id") or None
    return None


def _is_energy_sensor(eid: str, sensor_units: dict[str, str]) -> bool:
    """Prüft ob ein Sensor ein Energie-Sensor ist (kWh/Wh/MWh)."""
    return sensor_units.get(eid, "") in _KWH_UNITS


def _energy_delta_via_statistics(
    eid: str, start: datetime, end: datetime,
) -> Optional[float]:
    """Tages-kWh aus HA-Statistics `sum`-Spalte (reset-bereinigt).

    Robust gegen Counter-Drops in der state-Historie (HA-Restart,
    Sensor-Unavailable, Recorder-Lücken). Voraussetzung: Sensor hat
    `has_sum=True` in `statistics_meta` (utility_meter, total_increasing
    etc.). Liefert None wenn Statistics-DB nicht verfügbar (Standalone)
    oder Sensor kein has_sum-Sensor ist.

    Fix für #200 — analog zu #131 (Monatswert) und #184 (Snapshot).
    """
    from backend.services.ha_statistics_service import get_ha_statistics_service
    stats = get_ha_statistics_service()
    if not stats.is_available:
        return None
    val_start = stats.get_value_at(eid, start, toleranz_minuten=120)
    if val_start is None:
        return None
    # Aktueller Stand: zuerst short_term (5-Min-Slots, bis Minute genau),
    # Fallback hourly (bei Sensoren ohne short_term-Aktivierung).
    val_end = stats.get_value_at(eid, end, toleranz_minuten=15, short_term=True)
    if val_end is None:
        val_end = stats.get_value_at(eid, end, toleranz_minuten=120)
    if val_end is None:
        return None
    return max(0.0, val_end - val_start)


def _energy_delta(
    eid: str,
    history: dict[str, list[tuple[datetime, float]]],
    sensor_units: dict[str, str],
    start: Optional[datetime] = None,
    end: Optional[datetime] = None,
) -> Optional[float]:
    """Tages-kWh aus kumulativem Energie-Sensor.

    Bevorzugt HA-Statistics `sum`-Spalte (reset-bereinigt, robust gegen
    Counter-Drops bei HA-Restart oder kurzzeitigem Sensor-Unavailable).
    Fallback: state-history via `min → letzter Wert` — anfällig für
    Drops, daher nur wenn Statistics nicht greifen (Standalone-Modus,
    Sensor ohne has_sum, oder zu wenig Daten im Toleranz-Fenster).
    """
    # Power-Sensoren (W/kW) dürfen nicht als kumulative Energie gelesen werden:
    # state-Differenz wäre eine Power-Differenz, nicht kWh (#200 rcmcronny).
    # Caller fällt auf Trapez-Integration der W-Werte zurück.
    if not _is_energy_sensor(eid, sensor_units):
        return None
    # Skalierung gilt NUR für den state-history-Fallback (rohe state-Werte
    # in Sensor-Einheit). Der Statistics-Pfad geht durch
    # `ha_statistics_service.get_value_at`, das selbst bereits mit
    # `_ENERGY_UNIT_TO_KWH` auf kWh skaliert (Zeile 736-738) — eine zweite
    # Skalierung hier ergibt Faktor 1000² (NongJoWo-Befund #242, Forum
    # 2026-05-16: 8.11 kWh wurden als 8097 kWh angezeigt).
    scale = _KWH_SCALE.get(sensor_units.get(eid, "kWh"), 1.0)
    if start is not None and end is not None:
        delta = _energy_delta_via_statistics(eid, start, end)
        if delta is not None:
            return delta  # bereits in kWh aus get_value_at
    pts = history.get(eid)
    if not pts:
        return None
    val_start = min(p[1] for p in pts) * scale
    val_end = pts[-1][1] * scale
    return max(0.0, val_end - val_start)


# ── Öffentliche Funktionen ────────────────────────────────────────────

async def get_history_normalized(
    entity_ids: list[str], start: datetime, end: datetime,
) -> tuple[dict[str, list[tuple[datetime, float]]], dict[str, str]]:
    """Holt Sensor-History und normalisiert kW→W anhand der Einheit.

    Returns:
        (history, units) — history mit normalisierten W-Werten,
        units dict für nachgelagerte Einheit-Erkennung (z.B. kWh-Sensoren).
    """
    from backend.services.ha_state_service import get_ha_state_service
    ha_service = get_ha_state_service()

    units = await ha_service.get_sensor_units(entity_ids)
    history = await ha_service.get_sensor_history(entity_ids, start, end)

    for eid, points in history.items():
        factor = UNIT_TO_W.get(units.get(eid, ""), None)
        if factor is not None and factor != 1.0:
            history[eid] = [(ts, val * factor) for ts, val in points]

    return history, units


def apply_invert_to_history(
    history: dict[str, list[tuple[datetime, float]]],
    basis_live: dict[str, str],
    basis_invert: dict[str, bool],
    inv_live_map: dict[str, dict[str, str]] | None = None,
    inv_invert_map: dict[str, dict[str, bool]] | None = None,
) -> None:
    """Invertiert History-Werte für Sensoren mit Vorzeichen-Invertierung.

    Mutiert das history-Dict in-place (negiert Werte invertierter Sensoren).
    """
    invert_eids: set[str] = set()
    for key, should_invert in basis_invert.items():
        if should_invert and key in basis_live:
            invert_eids.add(basis_live[key])

    if inv_live_map and inv_invert_map:
        for inv_id, invert_flags in inv_invert_map.items():
            live = inv_live_map.get(inv_id, {})
            for key, should_invert in invert_flags.items():
                if should_invert and key in live:
                    invert_eids.add(live[key])

    for eid in invert_eids:
        if eid in history:
            history[eid] = [(ts, -val) for ts, val in history[eid]]


def trapez_kwh(points: list) -> Optional[float]:
    """Berechnet kWh aus Leistungs-History via Trapezregel."""
    if not points:
        return None
    if len(points) < 2:
        return 0.0
    energy_wh = 0.0
    for i in range(len(points) - 1):
        t1, p1 = points[i]
        t2, p2 = points[i + 1]
        dt_hours = (t2 - t1).total_seconds() / 3600
        if 0 < dt_hours < 2:  # Max 2h Lücke
            energy_wh += (p1 + p2) / 2 * dt_hours
    return energy_wh / 1000  # Wh → kWh


# ── get_tages_kwh: Phasen (RF-6, Serie „Funktion vor Datei") ─────────
#
# Die Reihenfolge der Phasen ist die der HEAD-Funktion: Typen laden → Erzeuger
# laden → Entities sammeln → Zeitfenster → History → Kategorien → Komponenten →
# BKW-Kürzung. Jede Phase schreibt in dieselben Dicts in derselben Folge wie
# vorher — die Einfügereihenfolge von `result` ist Teil der Antwort.


def _eov(
    quellen_energy: dict, sensor_key: str, eid: Optional[str],
) -> Optional[str]:
    """Energie-quellen-Override auf einen kWh-Sensor-Eid anwenden."""
    if not eid:
        return None
    eff, behalten = resolve_energy_ha_eid(quellen_energy, sensor_key, eid)
    return eff if behalten else None


async def _lade_inv_types(anlage: Anlage, db: AsyncSession) -> dict[str, str]:
    """Investitionstypen aus der DB — nur, wenn der Aufrufer sie nicht mitgibt."""
    inv_result = await db.execute(
        select(Investition.id, Investition.typ).where(
            Investition.anlage_id == anlage.id, aktiv_jetzt()
        )
    )
    return {str(row[0]): row[1] for row in inv_result.all()}


async def _lade_erzeuger(
    anlage: Anlage, db: AsyncSession, inv_types: dict[str, str],
) -> list:
    """Die Elternschaft für die BKW-Abtretung (N-536) — nur, wenn ein BKW gepflegt ist."""
    if BKW_TYP in (inv_types or {}).values():
        erz_result = await db.execute(
            select(
                Investition.id,
                Investition.typ,
                Investition.parent_investition_id,
            ).where(Investition.anlage_id == anlage.id, aktiv_jetzt())
        )
        return [
            SimpleNamespace(id=r[0], typ=r[1], parent_investition_id=r[2])
            for r in erz_result.all()
        ]
    return []


@dataclass(frozen=True)
class _TagesQuellen:
    """Welche Entity welchen Tageswert trägt — gesammelt VOR dem History-Abruf."""

    # Entity-IDs nach Kategorie gruppieren
    category_entities: dict[str, list[str]]
    # Per-Komponente Entity-IDs {component_key: entity_id}
    component_entities: dict[str, str]
    basis_kwh_sensors: dict[str, str]
    basis_pv_kwh_sensor: Optional[str]
    separate_battery_sensors: dict[str, dict[str, Optional[str]]]
    separate_kwh_sensors: dict[str, str]

    def alle_ids(self) -> list[str]:
        """Jede Entity, die ein Tageswert lesen kann — einmal."""
        # Alle Entity-IDs sammeln (dedupliziert)
        return list(set(
            [eid for eids in self.category_entities.values() for eid in eids]
            + list(self.component_entities.values())
            + [eid for sep in self.separate_battery_sensors.values()
               for eid in sep.values() if eid]
            + list(self.separate_kwh_sensors.values())
            + list(self.basis_kwh_sensors.values())
            + ([self.basis_pv_kwh_sensor] if self.basis_pv_kwh_sensor else [])
        ))


def _netz_kategorien(basis_live: dict[str, str]) -> dict[str, list[str]]:
    """Kategorien pv/einspeisung/netzbezug, Netz aus Basis (oder Kombi-Sensor)."""
    category_entities: dict[str, list[str]] = {
        "pv": [],
        "einspeisung": [],
        "netzbezug": [],
    }

    # Basis: Einspeisung + Netzbezug (oder kombinierter Netz-Sensor)
    netz_kombi_eid = basis_live.get("netz_kombi_w")
    if netz_kombi_eid and not basis_live.get("einspeisung_w") and not basis_live.get("netzbezug_w"):
        category_entities["netz_kombi"] = [netz_kombi_eid]
    else:
        netz_kombi_eid = None
        if basis_live.get("einspeisung_w"):
            category_entities["einspeisung"].append(basis_live["einspeisung_w"])
        if basis_live.get("netzbezug_w"):
            category_entities["netzbezug"].append(basis_live["netzbezug_w"])
    return category_entities


def _basis_kwh_sensoren(
    basis_map: dict, quellen_energy: dict,
) -> tuple[dict[str, str], Optional[str]]:
    """kWh-Zähler der Basis: Einspeisung, Netzbezug — und der Anlagen-PV-Zähler (F-49)."""
    basis_kwh_sensors: dict[str, str] = {}
    if (eid := _eov(quellen_energy, "basis:einspeisung", _feld_eid(basis_map.get("einspeisung", {})))):
        basis_kwh_sensors["einspeisung"] = eid
    if (eid := _eov(quellen_energy, "basis:netzbezug", _feld_eid(basis_map.get("netzbezug", {})))):
        basis_kwh_sensors["netzbezug"] = eid

    # F-49 (#388, Mathek 2026-08-19): der **anlagenweite PV-Zähler**. Er stand
    # hier bis dahin nicht — Einspeisung und Netzbezug lasen ihren Zählerstand,
    # die PV daneben wurde aus dem Leistungssensor integriert. Beim Melder
    # standen dadurch 10,0 kWh in der Live-Kachel, während sein eigener
    # HA-Zähler `sensor.energy_solar_generation_daily` 7,65 zeigte (+31 %).
    #
    # Der Widerspruch stand in der Oberfläche: bei einer Modulgruppe ohne
    # eigenen Zähler sagt der Hilfetext „Über den Anlagen-Zählerstand abgedeckt
    # — als Summe der ganzen Anlage, **auch für Tag und Stunde**". Für Tag und
    # Stunde stimmte das (Snapshot-Pfad), für die Live-Kachel nicht.
    #
    # Bewusst ein EIGENER Slot statt eines Eintrags in `basis_kwh_sensors`:
    # dort läge er VOR den Erzeuger-Einzelzählern, und die Präzedenz ist
    # umgekehrt — derselbe Hilfetext sagt „sobald einer gemessen wird, zählt
    # für Tag und Stunde nur noch, was je Erzeuger gemessen ist".
    basis_pv_kwh_sensor = _eov(
        quellen_energy, "basis:pv_gesamt", _feld_eid(basis_map.get("pv_gesamt", {}))
    )
    return basis_kwh_sensors, basis_pv_kwh_sensor


def _speicher_kwh_sensoren(
    inv_id: str, inv_live: dict, inv_felder: dict, quellen_energy: dict,
) -> Optional[dict[str, Optional[str]]]:
    """Ladung/Entladung eines Speichers: „heute"-Feld der Live-Zuordnung, sonst der Zähler."""
    ladung_eid = inv_live.get("ladung_kwh") or None
    entladung_eid = inv_live.get("entladung_kwh") or None
    if not ladung_eid:
        ladung_eid = _eov(quellen_energy, f"inv:{inv_id}:ladung_kwh",
                          _feld_eid(inv_felder.get("ladung_kwh", {})))
    if not entladung_eid:
        entladung_eid = _eov(quellen_energy, f"inv:{inv_id}:entladung_kwh",
                             _feld_eid(inv_felder.get("entladung_kwh", {})))
    if ladung_eid or entladung_eid:
        return {
            "ladung": ladung_eid,
            "entladung": entladung_eid,
        }
    return None


def _inv_kwh_sensoren(
    mapping_investitionen: dict,
    inv_types: dict[str, str],
    erzeuger_ids: frozenset,
    quellen_energy: dict,
) -> tuple[dict[str, dict[str, Optional[str]]], dict[str, str]]:
    """kWh-Zähler je Investition: Speicher (Ladung/Entladung), Erzeuger, WP/Wallbox."""
    separate_battery_sensors: dict[str, dict[str, Optional[str]]] = {}
    separate_kwh_sensors: dict[str, str] = {}
    for inv_id, inv_data in mapping_investitionen.items():
        typ = inv_types.get(inv_id) if inv_types else None
        if not isinstance(inv_data, dict):
            continue
        inv_live = inv_data.get("live", {}) or {}
        inv_felder = inv_data.get("felder", {}) or {}

        if typ == "speicher":
            sep = _speicher_kwh_sensoren(inv_id, inv_live, inv_felder, quellen_energy)
            if sep is not None:
                separate_battery_sensors[inv_id] = sep
        elif inv_id in erzeuger_ids:
            pv_eid = _eov(quellen_energy, f"inv:{inv_id}:pv_erzeugung_kwh",
                          _feld_eid(inv_felder.get("pv_erzeugung_kwh", {})))
            if pv_eid:
                separate_kwh_sensors[f"pv_{inv_id}"] = pv_eid
        elif typ in _MONATSABSCHLUSS_KWH:
            sensor_field, prefix = _MONATSABSCHLUSS_KWH[typ]
            kwh_eid = _eov(quellen_energy, f"inv:{inv_id}:{sensor_field}",
                           _feld_eid(inv_felder.get(sensor_field, {})))
            if kwh_eid:
                separate_kwh_sensors[f"{prefix}_{inv_id}"] = kwh_eid
    return separate_battery_sensors, separate_kwh_sensors


def _wp_split_entities(
    inv_id: str, live: dict[str, str], component_entities: dict[str, str],
) -> None:
    """WP ohne Gesamtleistung: jede Betriebsart als eigene Komponente."""
    heiz_eid = live.get("leistung_heizen_w")
    ww_eid = live.get("leistung_warmwasser_w")
    kuehl_eid = live.get("leistung_kuehlen_w")
    if heiz_eid:
        component_entities[f"waermepumpe_{inv_id}_heizen"] = heiz_eid
    if ww_eid:
        component_entities[f"waermepumpe_{inv_id}_warmwasser"] = ww_eid
    if kuehl_eid:
        component_entities[f"waermepumpe_{inv_id}_kuehlen"] = kuehl_eid


def _leistungs_entities(
    inv_live_map: dict[str, dict[str, str]],
    inv_types: dict[str, str],
    erzeuger_ids: frozenset,
    separate_battery_sensors: dict[str, dict[str, Optional[str]]],
    category_entities: dict[str, list[str]],
    component_entities: dict[str, str],
) -> None:
    """Leistungs-Entities je Investition in Kategorie `pv` und Komponenten-Map."""
    # Alle Investitionen mit leistung_w Sensor (oder getrennte WP-Sensoren)
    for inv_id, live in inv_live_map.items():
        typ = inv_types.get(inv_id)
        if not typ or typ in SKIP_TYPEN:
            continue

        entity_id = live.get("leistung_w")

        # WP: getrennte Leistungssensoren → jede Betriebsart als Komponente.
        # ⭐ Kühlen kam am 13.09.2026 dazu (N-439) — die Schwesterstellen
        # `live_sensor_config.baue_investitions_serien` und
        # `live_tagesverlauf_service` führen dieselben drei Suffixe.
        if not entity_id and typ == "waermepumpe":
            _wp_split_entities(inv_id, live, component_entities)
            continue

        # Speicher ohne leistung_w aber mit separaten kWh-Sensoren
        if not entity_id and typ == "speicher":
            sep = separate_battery_sensors.get(inv_id, {})
            entity_id = sep.get("ladung") or None

        if not entity_id:
            continue

        if inv_id in erzeuger_ids:
            category_entities["pv"].append(entity_id)
            component_entities[f"pv_{inv_id}"] = entity_id
        else:
            prefix = LIVE_KEY_PREFIX.get(typ, TAGESVERLAUF_KATEGORIE.get(typ, typ))
            component_entities[f"{prefix}_{inv_id}"] = entity_id


def _erhebe_quellen(
    anlage: Anlage,
    basis_live: dict[str, str],
    inv_live_map: dict[str, dict[str, str]],
    inv_types: dict[str, str],
    erzeuger_ids: frozenset,
) -> _TagesQuellen:
    """Alle Entities, aus denen die Tages-kWh entstehen — Kategorien, Komponenten, Zähler."""
    category_entities = _netz_kategorien(basis_live)

    # Per-Komponente Entity-IDs {component_key: entity_id}
    component_entities: dict[str, str] = {}

    # kWh-Sensoren aus Monatsabschluss-Mapping für exakte Tageswerte (#64).
    # Diese kWh-Sensoren SIND die Energie-Quellen-Sensoren (`sensor_mapping.
    # basis/felder[feld].sensor_id`), dieselben, die `_build_counter_map` und
    # die Datenquellen-Fläche nutzen → Datenquellen-V4-C2b-Read-Through greift
    # hier (kWh-Sensor-Zweig): HA → zugeordnete Entity; MQTT/keine → diesen
    # kWh-Sensor nicht verwenden (Wert kommt über den Trapez-Fallback des
    # Live-W-Sensors bzw. den MQTT-Pfad). Der W-Trapez-Fallback selbst gehört
    # zur Live-Zuordnung (C2a), nicht hierher.
    mapping_full = anlage.sensor_mapping or {}
    quellen_energy = extract_quellen_energy(anlage)

    basis_kwh_sensors, basis_pv_kwh_sensor = _basis_kwh_sensoren(
        mapping_full.get("basis", {}), quellen_energy,
    )
    separate_battery_sensors, separate_kwh_sensors = _inv_kwh_sensoren(
        mapping_full.get("investitionen", {}), inv_types, erzeuger_ids, quellen_energy,
    )
    _leistungs_entities(
        inv_live_map, inv_types, erzeuger_ids, separate_battery_sensors,
        category_entities, component_entities,
    )

    # PV Gesamt aus Basis als Fallback
    if not category_entities["pv"] and basis_live.get("pv_gesamt_w"):
        pv_gesamt_eid = basis_live["pv_gesamt_w"]
        category_entities["pv"].append(pv_gesamt_eid)
        component_entities["pv_gesamt"] = pv_gesamt_eid

    return _TagesQuellen(
        category_entities=category_entities,
        component_entities=component_entities,
        basis_kwh_sensors=basis_kwh_sensors,
        basis_pv_kwh_sensor=basis_pv_kwh_sensor,
        separate_battery_sensors=separate_battery_sensors,
        separate_kwh_sensors=separate_kwh_sensors,
    )


def _tagesfenster(now: datetime, tage_zurueck: int) -> tuple[datetime, datetime]:
    """[Tagesbeginn, jetzt) für heute, [Tagesbeginn, +1 Tag) für einen vergangenen Tag."""
    tag = now - timedelta(days=tage_zurueck)
    start = tag.replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + timedelta(days=1) if tage_zurueck > 0 else now
    return start, end


@dataclass(frozen=True)
class _Tagesmessung:
    """Die abgerufene History mit Einheiten und Fenster — Eingang aller kWh-Phasen."""

    history: dict[str, list[tuple[datetime, float]]]
    sensor_units: dict[str, str]
    start: datetime
    end: datetime

    def delta(self, eid: str) -> Optional[float]:
        """`_energy_delta` im Tagesfenster (Statistics `sum`, sonst State-History)."""
        return _energy_delta(eid, self.history, self.sensor_units, self.start, self.end)

    def ist_energie(self, eid: str) -> bool:
        """kWh/Wh/MWh-Sensor?"""
        return _is_energy_sensor(eid, self.sensor_units)


def _netz_kombi_kwh(
    entity_ids: list[str],
    history: dict[str, list[tuple[datetime, float]]],
    result: dict[str, Optional[float]],
) -> None:
    """Kombinierter Netz-Sensor: positiv = Bezug, negativ = Einspeisung (Trapez)."""
    for entity_id in entity_ids:
        if entity_id not in history:
            continue
        pts = history[entity_id]
        bezug_pts = [(t, max(p, 0)) for t, p in pts]
        einsp_pts = [(t, abs(min(p, 0))) for t, p in pts]
        bezug_kwh = trapez_kwh(bezug_pts)
        einsp_kwh = trapez_kwh(einsp_pts)
        if bezug_kwh is not None:
            result["netzbezug"] = round(bezug_kwh, 1)
        if einsp_kwh is not None:
            result["einspeisung"] = round(einsp_kwh, 1)


def _basis_zaehler_kwh(kwh_eid: str, mess: _Tagesmessung) -> Optional[float]:
    """Einspeisung/Netzbezug aus dem kumulierten kWh-Sensor — None ⇒ Trapez-Fallback."""
    if kwh_eid in mess.history:
        kwh = mess.delta(kwh_eid)
        if kwh is not None:
            return round(kwh, 1)
    return None


def _pv_zaehler_kwh(
    quellen: _TagesQuellen, mess: _Tagesmessung, erzeuger: list,
) -> Optional[float]:
    """PV aus Zählern: Erzeuger-Einzelzähler, sonst Anlagenzähler — None ⇒ Trapez-Fallback."""
    # N-536: erst je Erzeuger sammeln, dann das abtretende
    # Balkonkraftwerk auf seinen Rest kürzen, dann summieren. Vorher
    # stand sein Gesamtzähler neben den Zählern seiner Kinder in
    # derselben Summe.
    pv_je_komponente: dict[str, float] = {}
    pv_has_kwh = False
    for comp_key, kwh_eid in quellen.separate_kwh_sensors.items():
        # Erzeuger (PV-Module + Balkonkraftwerk) werden in diesem
        # Live-Keyspace einheitlich mit `pv_`-Präfix abgelegt; die
        # Prefix-Quelle kommt zentral aus dem Berechnungs-Layer
        # (ADR-001), damit kein eigenes Literal driftet.
        if (
            any(comp_key.startswith(p) for p in PV_KOMPONENTEN_PREFIXE)
            and kwh_eid in mess.history
        ):
            kwh = mess.delta(kwh_eid)
            if kwh is not None:
                pv_je_komponente[comp_key] = kwh
                pv_has_kwh = True
    if pv_has_kwh:
        gekuerzt = kuerze_bkw_in_werte_map(pv_je_komponente, erzeuger)
        return round(sum(gekuerzt.values()), 1)
    # F-49: kein Erzeuger misst selbst → der anlagenweite PV-Zähler.
    # Erst wenn auch der fehlt, wird die Leistung integriert.
    if quellen.basis_pv_kwh_sensor and quellen.basis_pv_kwh_sensor in mess.history:
        kwh = mess.delta(quellen.basis_pv_kwh_sensor)
        if kwh is not None:
            return round(kwh, 1)
    return None


def _zaehler_kwh(
    category: str, quellen: _TagesQuellen, mess: _Tagesmessung, erzeuger: list,
) -> Optional[float]:
    """Priorität 1: kumulierter kWh-Sensor der Kategorie — None ⇒ Trapez-Fallback."""
    if category in quellen.basis_kwh_sensors:
        return _basis_zaehler_kwh(quellen.basis_kwh_sensors[category], mess)
    if category == "pv":
        return _pv_zaehler_kwh(quellen, mess, erzeuger)
    return None


def _kategorie_aus_entities(
    category: str,
    entity_ids: list[str],
    quellen: _TagesQuellen,
    mess: _Tagesmessung,
    erzeuger: list,
) -> Optional[float]:
    """Fallback der Kategorie: W-Sensoren per Trapez, kWh-Sensoren per Delta."""
    # Fallback: W-Sensoren + Trapezregel
    # N-536: Bei der PV-Kategorie tragen die Entities Erzeuger — dort wird
    # je Komponente gesammelt und das abtretende Balkonkraftwerk gekürzt,
    # bevor summiert wird. Die Zuordnung Entity → Komponenten-Key steht in
    # `component_entities`; eine Entity ohne Key (der anlagenweite Zähler)
    # bleibt unberührt und behält ihren eigenen Schlüssel.
    eid_je_key = (
        {eid: key for key, eid in quellen.component_entities.items()}
        if category == "pv" else {}
    )
    werte_je_key: dict[str, float] = {}
    has_data = False
    for idx, entity_id in enumerate(entity_ids):
        if entity_id not in mess.history:
            continue
        if mess.ist_energie(entity_id):
            kwh = mess.delta(entity_id)
        else:
            kwh = trapez_kwh(mess.history[entity_id])
        if kwh is not None:
            werte_je_key[eid_je_key.get(entity_id, f"__{idx}")] = kwh
            has_data = True
    if has_data:
        if category == "pv":
            werte_je_key = kuerze_bkw_in_werte_map(werte_je_key, erzeuger)
        return round(sum(werte_je_key.values()), 1)
    return None


def _kategorien_kwh(
    result: dict[str, Optional[float]],
    quellen: _TagesQuellen,
    mess: _Tagesmessung,
    erzeuger: list,
) -> None:
    """Kategorie-Summen in `result` schreiben."""
    # Aggregierte Kategorien (pv, einspeisung, netzbezug)
    for category, entity_ids in quellen.category_entities.items():
        if category == "netz_kombi":
            _netz_kombi_kwh(entity_ids, mess.history, result)
            continue

        # Priorität 1: kumulierter kWh-Sensor
        kwh = _zaehler_kwh(category, quellen, mess, erzeuger)
        if kwh is None:
            kwh = _kategorie_aus_entities(category, entity_ids, quellen, mess, erzeuger)
        if kwh is not None:
            result[category] = kwh


def _batterie_richtungen_kwh(
    entity_id: str,
    pts: list,
    ladung_eid: Optional[str],
    entladung_eid: Optional[str],
    mess: _Tagesmessung,
) -> tuple[Optional[float], Optional[float]]:
    """Ladung und Entladung: eigener kWh-Sensor, sonst kWh-Leistungs-Entity, sonst Trapez je Vorzeichen."""
    if ladung_eid and ladung_eid in mess.history:
        ladung_kwh = mess.delta(ladung_eid)
    elif mess.ist_energie(entity_id):
        ladung_kwh = mess.delta(entity_id)
    else:
        ladung_pts = [(t, max(p, 0)) for t, p in pts]
        ladung_kwh = trapez_kwh(ladung_pts)

    if entladung_eid and entladung_eid in mess.history:
        entladung_kwh = mess.delta(entladung_eid)
    elif not mess.ist_energie(entity_id):
        entladung_pts = [(t, abs(min(p, 0))) for t, p in pts]
        entladung_kwh = trapez_kwh(entladung_pts)
    else:
        entladung_kwh = None
    return ladung_kwh, entladung_kwh


def _batterie_kwh(
    result: dict[str, Optional[float]],
    comp_key: str,
    entity_id: str,
    pts: list,
    separate_battery_sensors: dict[str, dict[str, Optional[str]]],
    mess: _Tagesmessung,
) -> None:
    """Batterie: Ladung/Entladung getrennt, dazu die Gesamtaktivität."""
    inv_id = comp_key[len("batterie_"):]
    sep = separate_battery_sensors.get(inv_id, {})
    ladung_eid = sep.get("ladung")
    entladung_eid = sep.get("entladung")

    ladung_kwh, entladung_kwh = _batterie_richtungen_kwh(
        entity_id, pts, ladung_eid, entladung_eid, mess,
    )

    if ladung_kwh is not None:
        result[f"{comp_key}_ladung"] = round(ladung_kwh, 1)
    if entladung_kwh is not None:
        result[f"{comp_key}_entladung"] = round(entladung_kwh, 1)

    # Gesamtaktivität
    if ladung_eid or entladung_eid:
        total = (ladung_kwh or 0) + (entladung_kwh or 0)
        if total > 0:
            result[comp_key] = round(total, 1)
    elif mess.ist_energie(entity_id):
        kwh = mess.delta(entity_id)
        if kwh is not None:
            result[comp_key] = round(abs(kwh), 1)
    else:
        kwh = trapez_kwh(pts)
        if kwh is not None:
            result[comp_key] = round(abs(kwh), 1)


def _verbraucher_kwh(
    comp_key: str,
    entity_id: str,
    pts: list,
    separate_kwh_sensors: dict[str, str],
    mess: _Tagesmessung,
) -> Optional[float]:
    """WP/Wallbox/übrige Komponente: Zähler, sonst kWh-Entity, sonst Trapez."""
    # WP/Wallbox: kWh-Sensor aus Monatsabschluss bevorzugen (#64 Follow-up)
    sep_eid = separate_kwh_sensors.get(comp_key)
    if sep_eid and sep_eid in mess.history:
        kwh = mess.delta(sep_eid)
    elif mess.ist_energie(entity_id):
        kwh = mess.delta(entity_id)
    else:
        kwh = trapez_kwh(pts)
    return kwh


def _komponenten_kwh(
    result: dict[str, Optional[float]],
    quellen: _TagesQuellen,
    mess: _Tagesmessung,
) -> None:
    """Komponenten-Werte in `result` schreiben."""
    # Per-Komponente kWh (für Tooltips)
    for comp_key, entity_id in quellen.component_entities.items():
        if entity_id not in mess.history:
            continue
        pts = mess.history[entity_id]

        # Batterie: Ladung/Entladung getrennt berechnen
        if comp_key.startswith("batterie_"):
            _batterie_kwh(
                result, comp_key, entity_id, pts,
                quellen.separate_battery_sensors, mess,
            )
        else:
            kwh = _verbraucher_kwh(
                comp_key, entity_id, pts, quellen.separate_kwh_sensors, mess,
            )
            if kwh is not None:
                result[comp_key] = round(abs(kwh), 1)


async def get_tages_kwh(
    anlage: Anlage, db: AsyncSession, tage_zurueck: int = 0,
    inv_types: dict[str, str] | None = None,
    erzeuger: list | None = None,
) -> dict[str, Optional[float]]:
    """
    Berechnet Tages-kWh aus HA-History (Leistungssensoren → Energie via Trapezregel).

    Aggregiert in Kategorien (pv, einspeisung, netzbezug) UND per-Komponente
    (z.B. pv_3, wallbox_6, batterie_2) für Tooltips im Energiefluss.
    """
    basis_live, inv_live_map, basis_invert, inv_invert_map = extract_live_config(anlage)

    # Investitionstypen: durchgereicht oder aus DB laden
    if inv_types is None:
        inv_types = await _lade_inv_types(anlage, db)

    # N-536: Für die Abtretung eines Balkonkraftwerks an seine `pv-module`-
    # Kinder reicht der Typ nicht — es braucht die Elternschaft. Der Aufrufer
    # gibt sie mit, wenn er die Investitionen ohnehin geladen hat
    # (`live_power_service`); sonst kostet sie EINE kleine Query, und nur dann,
    # wenn überhaupt ein Balkonkraftwerk gepflegt ist.
    if erzeuger is None:
        erzeuger = await _lade_erzeuger(anlage, db, inv_types)

    # P11 (N-536): Welche Investition ein Erzeuger ist, entscheidet die Funktion,
    # die auch die Abtretung anwendet (`kuerze_bkw_in_werte_map` unten) — die
    # Phasen bekommen die fertige Menge und prüfen keinen Typ selbst (RF-6).
    erzeuger_ids = frozenset(
        inv_id for inv_id, typ in inv_types.items() if typ in ERZEUGER_TYPEN
    )

    quellen = _erhebe_quellen(anlage, basis_live, inv_live_map, inv_types, erzeuger_ids)
    all_ids = quellen.alle_ids()
    if not all_ids:
        return {}

    start, end = _tagesfenster(datetime.now(), tage_zurueck)

    history, sensor_units = await get_history_normalized(all_ids, start, end)

    # Vorzeichen-Invertierung auf History anwenden (#58)
    apply_invert_to_history(
        history, basis_live, basis_invert, inv_live_map, inv_invert_map
    )

    mess = _Tagesmessung(history, sensor_units, start, end)
    result: dict[str, Optional[float]] = {}
    _kategorien_kwh(result, quellen, mess, erzeuger)
    _komponenten_kwh(result, quellen, mess)

    # N-536: Auch die Werte JE KOMPONENTE (Energiefluss-Tooltips) tragen das
    # abtretende Balkonkraftwerk nur noch mit seinem Rest — sonst stünde im
    # Tooltip neben den Modulen ein Gerät mit derselben Energie. Die
    # Kategorie-Summe `result["pv"]` ist oben bereits gekürzt und wird hier
    # nicht berührt (sie trägt kein `_<id>`-Suffix).
    result = kuerze_bkw_in_werte_map(result, erzeuger)

    return result


async def safe_get_tages_kwh(
    anlage: Anlage, db: AsyncSession, tage_zurueck: int,
    kwh_cache,
    inv_types: dict[str, str] | None = None,
    erzeuger: list | None = None,
) -> dict[str, Optional[float]]:
    """Wrapper mit Fehlerbehandlung für get_tages_kwh (HA + MQTT Fallback).

    Heute-kWh: 60s TTL-Cache (verhindert HA-History-Flood bei jedem Live-Refresh).
    Gestern-kWh: Tages-Cache (ändert sich nach Mitternacht nicht mehr).
    """
    # Cache prüfen
    if tage_zurueck == 0:
        cached = kwh_cache.get_heute(anlage.id)
        if cached is not None:
            return cached
    elif tage_zurueck >= 1:
        cached = kwh_cache.get_gestern(anlage.id)
        if cached is not None:
            return cached

    # 1. Versuche HA-History (Trapezregel)
    #
    # N-156/F-26: die ZUORDNUNG entscheidet, nicht die Umgebung. Bis
    # 2026-08-11 stand hier `HA_INTEGRATION_AVAILABLE` (= SUPERVISOR_TOKEN),
    # obwohl `get_tages_kwh` darunter ausschließlich über `HAStateService` und
    # `ha_statistics_service` liest — beide seit dem 05.08. remote-fähig, beide
    # prüfen ihre Erreichbarkeit selbst. Der Docstring des `HAStateService`
    # nennt diesen Dienst sogar namentlich als Leidtragenden. Ohne HA-Token
    # bleibt es beim MQTT-Fallback darunter, unverändert.
    from backend.services.ha_state_service import get_ha_state_service

    if get_ha_state_service().is_available:
        try:
            result = await get_tages_kwh(
                anlage, db, tage_zurueck, inv_types=inv_types, erzeuger=erzeuger,
            )
            if result:
                if tage_zurueck == 0:
                    kwh_cache.set_heute(anlage.id, result)
                else:
                    kwh_cache.set_gestern(anlage.id, result)
                return result
        except Exception as e:
            label = "Heute" if tage_zurueck == 0 else "Gestern"
            logger.warning(f"Fehler bei {label}-kWh Berechnung (HA): {type(e).__name__}: {e}")

    # 2. Fallback: MQTT Energy Snapshots
    #
    # ⛔ **Die eigene Sitzung wird durchgereicht** (N-400, 13.09.2026). Bis dahin
    # öffnete der MQTT-Zweig darunter je eine EIGENE Sitzung auf der App-Datenbank,
    # obwohl diese Funktion `db` von `Depends(get_db)` an hält — dieselbe Bauform,
    # die nach v4.0.40 den Tests-Workflow rot gemacht hat (N-399). ⚠ Und sie fiele
    # hier besonders leise aus: das `except Exception` unten macht aus jedem Fehler
    # ein `logger.debug` und ein leeres Ergebnis.
    try:
        from backend.services.mqtt_energy_history_service import get_tages_kwh as mqtt_get_tages_kwh
        result = await mqtt_get_tages_kwh(
            anlage.id, db, tage_zurueck, inv_types=inv_types, erzeuger=erzeuger,
        )
        if result:
            if tage_zurueck == 0:
                kwh_cache.set_heute(anlage.id, result)
            else:
                kwh_cache.set_gestern(anlage.id, result)
            return result
    except Exception as e:
        label = "Heute" if tage_zurueck == 0 else "Gestern"
        logger.debug(f"MQTT Energy History nicht verfügbar für {label}: {e}")

    return {}
