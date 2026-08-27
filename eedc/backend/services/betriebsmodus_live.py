"""Der **aktuelle** Betriebsmodus je Wärmepumpe/Klimagerät — ein Leser, drei Nutzer.

**Warum es diese Datei gibt (#398, MartyBr).** Seit v4.0.21 schreibt eedc den
Betriebsmodus **zur Messzeit** mit und teilt den Strom danach auf. Gelesen wurde
dafür bisher ausschließlich die **Historie** (`energie_profil/_helpers.py`,
einmal je Aggregationslauf). Den Zustand **jetzt** kannte niemand — obwohl die
Live-Hälfte längst gebaut war: `ha_state_service.get_zustand_states_batch` hatte
am 27.08.2026 baumweit **null Aufrufer** (Fund N-333, entstanden mit `6fe8dcf3`,
#263 K-2 S1+S2).

Drei Sichten brauchen genau dieselbe Auskunft, und deshalb steht sie **einmal**
hier statt dreimal am Verwendungsort:

* der **HA-Sensor / das MQTT-Topic** je Gerät (#398 Stufe 1),
* der **Klartext** in Cockpit → Live und im Wärmepumpen-Hub (Stufe 2),
* das **Icon im Energiefluss-SVG** (Stufe 3).

⛔ **Was hier NICHT passiert: raten.** Ein Gerät ohne zugeordnete `climate`-Quelle,
ein nicht erreichbares Home Assistant, ein `unknown`/`unavailable` — all das
**fehlt in der Rückgabe**. Es wird nicht zu `unbestimmt`: `None` heißt „nicht
hingesehen", `unbestimmt` heißt „hingesehen, Seite nicht zuordenbar"
(`core/betriebsmodus.normalisiere_betriebsmodus`, ADR-002/P4). Wer die beiden
zusammenwirft, macht aus einer fehlenden Zuordnung eine Aussage über das Gerät.

⚠ **Der Modus kommt heute nur aus Home Assistant.** Der 5-Sekunden-Live-Pfad kann
ihn nicht liefern (`live_sensor_config.py` schließt Zustandsfelder aus — dort
landet jeder Wert in `normalize_to_w(float(state))`), und über MQTT-Inbound gibt
es ihn nicht (`mqtt_topic_registry.py`: ein Zustandsfeld bekommt bewusst **kein**
Topic, weil der Inbound-Parser `float(payload)` ist). Wer MQTT-only fährt, hat
keinen Modus — und bekommt dann auch keinen Sensor statt einer erfundenen Null.

⚠ **`hvac_action` schlägt den eingestellten Modus, wo sie da ist** — dieselbe
Vorrangregel wie im Historien-Zweig. Sie wird hier nur **mitgeführt**; angewendet
wird sie in `normalisiere_betriebsmodus(state, aktion)`. Wer sie vorher in den
State schreibt, hebelt die Regel aus (der Fehler, der am 20.08. jedem Gerät mit
Ist-Signal die gesamte Aufteilung gekostet hat).
"""

from __future__ import annotations

import logging
import time
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.betriebsmodus import normalisiere_betriebsmodus
from backend.core.field_definitions import basis_feld_key
from backend.models.investition import Investition
from backend.utils.investition_filter import aktiv_jetzt

logger = logging.getLogger(__name__)

#: Der Feld-Key der Modus-Quelle, ohne Innengeräte-Suffix.
_MODUS_KEY = "betriebsmodus"

# ── Eigener Takt, und das ist der Kern dieser Datei ──────────────────────────
#
# ⛔ **In `live_komponenten_builder.py` stand seit #263 ein begründeter Entscheid
# GEGEN das Lesen des Modus im Live-Pfad:** *„Ihn nur für ein Icon wieder
# einzuschalten hieße, einen Dauerabruf gegen ein Symbol zu tauschen — nach der
# L-1-Entlastung der HA-Datenbank die falsche Richtung."* **Der Einwand ist
# berechtigt und am 27.08. nachgemessen:** der TTL-Cache von
# `fetch_selected_states` steht auf **3 s**, die Live-Sicht pollt alle **5 s** —
# ein naiver Aufruf von hier aus wäre also wirklich ein Abruf je Poll je Gerät.
#
# ⭐ **Zwei Dinge haben sich geändert, und nur deshalb wird der Entscheid
# aufgelöst statt übergangen:**
#   1. Der Wert hat seit #398 **drei** Verbraucher (HA-Sensor/MQTT-Topic,
#      Klartext in der Oberfläche, Icon im Energiefluss). „Nur für ein Icon"
#      trifft nicht mehr zu.
#   2. Er bekommt einen **eigenen, langen Takt** statt des Live-Takts. Ein
#      Betriebsmodus wird in der Praxis **saisonal** gestellt (Kanon-Docstring,
#      D11) — 60 s Alter sind an dieser Größe unsichtbar, und aus „je 5 s" wird
#      höchstens „je 60 s": **ein Zwölftel** der Last, die der Einwand meinte.
#
# ⚠ **Was NICHT angefasst wird:** `live_sensor_config` schließt Zustandsfelder
# weiterhin aus. Der Modus läuft nie durch `normalize_to_w` und steht in keiner
# 5-Sekunden-Abrufliste. Der Ausschluss dort war richtig und bleibt.
_TAKT_SEKUNDEN = 60.0

#: ``anlage_id → (monotone Zeit, Ergebnis)``. Bewusst HIER und nicht beim
#: Aufrufer: ein Caller, der den Takt selbst wählen müsste, wählt ihn früher
#: oder später falsch — und dann ist der Entscheid oben wieder offen.
_cache: dict[int, tuple[float, dict[int, str]]] = {}


def cache_leeren() -> None:
    """Setzt den Takt-Cache zurück — für Proben und den Verbindungswechsel."""
    _cache.clear()


def _entity_zu_investitionen(
    sensor_mapping: Optional[dict], inv_ids: set[int]
) -> dict[str, list[int]]:
    """`climate`-Entity → die Geräte, die daran hängen.

    ⚠ **Nicht `live["betriebsmodus"]` allein** (#263): Mit einer
    Innengeräte-Liste heißt der Key `betriebsmodus-3`. Wer nur den nackten Namen
    prüft, hält eine Anlage für unzugeordnet, an der alle drei Innengeräte
    zugeordnet sind — derselbe Fehler, den der Daten-Checker in
    `datenquelle.py::_hat_modus` ausdrücklich benennt. Deshalb `basis_feld_key`.

    ⚠ **Mehrere Innengeräte dürfen dieselbe Entität tragen** (Konzept D3): der
    Modus gehört dem Außengerät. Dann steht derselbe Modus bei beiden, und das
    ist richtig — kein Grund, den zweiten zu verwerfen.
    """
    ergebnis: dict[str, list[int]] = {}
    for key, eintrag in ((sensor_mapping or {}).get("investitionen") or {}).items():
        try:
            inv_id = int(key)
        except (TypeError, ValueError):
            continue
        if inv_id not in inv_ids or not isinstance(eintrag, dict):
            continue
        for feld, entity in (eintrag.get("live") or {}).items():
            if entity and basis_feld_key(feld) == _MODUS_KEY:
                if inv_id not in ergebnis.setdefault(entity, []):
                    ergebnis[entity].append(inv_id)
    return ergebnis


async def lade_betriebsmodus_live(
    db: AsyncSession, anlage
) -> dict[int, str]:
    """Der aktuelle Modus je Gerät — ``{investition_id: kanon}``.

    Geräte ohne Zuordnung, ohne Signal oder ohne erreichbares HA **fehlen** in
    der Map (siehe Modul-Docstring). Ein leeres Ergebnis ist der Normalfall für
    jede Anlage ohne Klimagerät und kostet einen DB-Zugriff, keinen HA-Abruf.

    ⚠ **Das Ergebnis ist bis zu 60 s alt** (siehe `_TAKT_SEKUNDEN`). Wer den
    Momentanwert braucht, ruft `cache_leeren()` davor — das tut heute niemand,
    und das ist Absicht.

    Returns:
        ``{investition_id: Kanon-Wert}`` aus `BETRIEBSMODUS_KANON`.
    """
    jetzt = time.monotonic()
    treffer = _cache.get(anlage.id)
    if treffer is not None and (jetzt - treffer[0]) < _TAKT_SEKUNDEN:
        return treffer[1]

    ergebnis = await _erhebe(db, anlage)
    _cache[anlage.id] = (jetzt, ergebnis)
    return ergebnis


async def _erhebe(db: AsyncSession, anlage) -> dict[int, str]:
    """Die eigentliche Erhebung — ohne Takt, damit der Takt eine Stelle hat."""
    result = await db.execute(
        select(Investition.id).where(
            Investition.anlage_id == anlage.id,
            Investition.typ == "waermepumpe",
            aktiv_jetzt(),
        )
    )
    inv_ids = set(result.scalars().all())
    if not inv_ids:
        return {}

    entity_map = _entity_zu_investitionen(anlage.sensor_mapping, inv_ids)
    if not entity_map:
        return {}

    from backend.services.ha_state_service import get_ha_state_service

    ha_service = get_ha_state_service()
    if not ha_service.is_available:
        return {}

    try:
        zustaende = await ha_service.get_zustand_states_batch(list(entity_map))
    except Exception as e:  # pragma: no cover — Soft-fail, die Sicht bleibt ohne Modus
        logger.warning("Betriebsmodus (live) nicht lesbar: %s", e)
        return {}

    ergebnis: dict[int, str] = {}
    for entity, ids in entity_map.items():
        roh = zustaende.get(entity)
        if not roh:
            continue
        modus = normalisiere_betriebsmodus(*roh)
        if modus is None:
            continue
        for inv_id in ids:
            ergebnis[inv_id] = modus
    return ergebnis
