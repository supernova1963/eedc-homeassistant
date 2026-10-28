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

⚠ **Zwei Quellen, eine Regel: Home Assistant, sonst MQTT** (HA-Bauform §9,
Standalone-Gleichstand S1, 25.10.2026). Der 5-Sekunden-Live-Pfad liefert den Modus
nicht (`live_sensor_config.py` schließt Zustandsfelder aus — dort landet jeder Wert
in `normalize_to_w(float(state))`). Gelesen wird er hier: aus HA für jedes Gerät mit
einer Modus-Entität im ``live``-Block (`_erhebe_ha`), aus dem MQTT-Inbound-Cache für
jedes **übrige** Gerät (`_erhebe_mqtt`: Topic `…/live/inv/<id>/betriebsmodus`,
Kanon-Wort oder Zahlencode). **HA gewinnt über die ``live``-Entität, nie über einen
``quellen``-Eintrag** — der B8-Stempel `mqtt_inbound_standard` liegt auf jedem Feld
ohne HA-Sensor und sagt nichts über HA. Eine ausdrückliche Wahl «keine» schließt
MQTT aus wie im Leistungspfad (C2a). Über MQTT gibt es keine Aktion (kein
«Leerlauf», E-SG-2). Wer weder HA-Modus noch MQTT-Topic hat, hat keinen Modus —
und bekommt dann auch keinen Sensor statt einer erfundenen Null.

⚠ **`hvac_action` VERFEINERT den eingestellten Modus, wo sie da ist** — dieselbe
Vorrangregel wie im Historien-Zweig. Sie schlägt ihn, wo sie eine **Richtung**
nennt; `idle` nennt keine und lässt ihn deshalb stehen (#399, 28.08.2026 — davor
verwarf es ihn, und taktende Geräte verloren ihre Aufteilung). Sie wird hier nur **mitgeführt**; angewendet
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

from backend.core import zustands_kanon
from backend.core.betriebsmodus import (
    MODUS_FELD_KEY,
    betriebsmodus_aktion,
    modus_aus_zustaenden,
    modus_quelle,
    normalisiere_betriebsmodus,
)
from backend.core.field_definitions import ZUSTAND_LIVE_FELDER, basis_feld_key, ist_text_feld
from backend.models.investition import Investition
from backend.utils.investition_filter import aktiv_jetzt

logger = logging.getLogger(__name__)

#: Der Feld-Key der Modus-Quelle, ohne Innengeräte-Suffix.

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

#: ``anlage_id → (monotone Zeit, Kanon je Gerät, Aktion je Gerät, E-Mob-Zustand je (Gerät, Feld))``. Bewusst HIER
#: und nicht beim Aufrufer: ein Caller, der den Takt selbst wählen müsste, wählt
#: ihn früher oder später falsch — und dann ist der Entscheid oben wieder offen.
#: Die Aktion (P-433-1, «Leerlauf») kommt aus DEMSELBEN Abruf: kein zweiter Takt. Seit P-433-2b K1 stehen hier auch
#: die Zustände der E-Mobilität (Ladezustand, Lademodus, Fahrzeug-Ladezustand, Standort) — im selben Takt, mit einem
#: eigenen gebündelten HA-Abruf für alle E-Mob-Felder (neben dem des Modus).
#: Seit P-433-2b K4 dazu die Zählerstände der E-Mobilität je Gerät (Kilometerstand, `lade_staende_live`).
_cache: dict[int, tuple[float, dict[int, str], dict[int, str], dict[tuple[int, str], str], dict[int, float]]] = {}

#: P-433-2b K1 (Bauplan E2): die Typen, die ein Zustandsfeld haben — abgeleitet aus der Registry
#: (`ZUSTAND_LIVE_FELDER`), nicht getippt. Bis K1 stand an der Abfrage `typ == "waermepumpe"`.
_ZUSTAND_TYPEN: frozenset[str] = frozenset(typ for typ, _feld in ZUSTAND_LIVE_FELDER)
#: Die Zustandsfelder der E-Mobilität je Typ — alle außer dem Betriebsmodus (der hat seinen eigenen Pfad oben): die
#: Kanon-Felder (`zustands_kanon.ZUSTANDS_FELDER`) und seit P-433-2b K2a die Textfelder (`ist_text_feld`, heute
#: `fahrzeug_am_ladepunkt`) — derselbe Takt, derselbe gebündelte HA-Abruf, dieselbe Quellen-Regel.
_EMOB_ZUSTAENDE: dict[str, tuple[str, ...]] = {
    typ: tuple(sorted(
        feld for t, feld in ZUSTAND_LIVE_FELDER
        if t == typ and (feld in zustands_kanon.ZUSTANDS_FELDER or ist_text_feld(feld, typ))
    ))
    for typ in _ZUSTAND_TYPEN
}


def _emob_wert(feld: str, typ_text: bool, roh, *, codes: bool) -> Optional[str]:
    """Ein Rohwert der E-Mobilität → Kanon-Wert (Kanon-Feld) bzw. Text (Textfeld, ``""`` = leer), sonst ``None``.

    P-433-2b K2a (Bauplan K2 E2, W1): ein Textfeld bekommt ``""`` nur aus einer **Antwort** — der Aufrufer reicht
    ``None`` durch, wenn keine Quelle geantwortet hat (HA-State fehlt/``unavailable``, kein MQTT-Cache-Eintrag), und
    ``zustands_kanon.text(None)`` bleibt ``None``. Der Zuordnungs-Default «ohne HA-Entität ⇒ MQTT» erfindet so keinen
    leeren Text und damit keinen Gast.
    """
    if typ_text:
        return zustands_kanon.text(feld, roh)
    return zustands_kanon.normalisiere(feld, roh, codes=codes)


def cache_leeren() -> None:
    """Setzt den Takt-Cache zurück — für Proben und den Verbindungswechsel."""
    _cache.clear()


def _entity_zu_investitionen(
    sensor_mapping: Optional[dict], inv_ids: set[int]
) -> dict[str, list[int]]:
    """`climate`-Entity → die Geräte, die daran hängen.

    ⚠ **Die Auswahl der Quelle liegt in `core.betriebsmodus.modus_quelle`**,
    nicht hier — mitsamt ihrer Begründung. Sie löst den Innengeräte-Suffix auf
    (`betriebsmodus-3`, #263), behandelt mehrere Zuordnungen auf **dieselbe**
    Entität als **eine** Quelle (Konzept D3: der Modus gehört dem Außengerät)
    und liefert `None`, sobald es **verschiedene** gibt (N-340).

    ⛔ **Sie stand bis zum 27.08.2026 an zwei Stellen nebeneinander** — hier und
    im Aggregationspfad —, und die zweite kannte den Suffix nicht. Genau davor
    warnt `modus_split_monat.py` seit F-52 wörtlich: *„eine Regel, die an zwei
    Stellen nachgebaut wird, driftet."*
    """
    ergebnis: dict[str, list[int]] = {}
    for key, eintrag in ((sensor_mapping or {}).get("investitionen") or {}).items():
        try:
            inv_id = int(key)
        except (TypeError, ValueError):
            continue
        if inv_id not in inv_ids or not isinstance(eintrag, dict):
            continue
        # ⚠ **Genau EINE Quelle je Gerät** (N-340). Bis dahin landete ein
        # Gerät mit zwei verschiedenen `climate`-Entitäten unter beiden — und
        # `ergebnis[inv_id] = modus` unten liess die **letzte** gewinnen, nach
        # Einfüge-Reihenfolge des Mappings. Ein Zustand, den eedc nicht
        # bestimmen kann, wird nicht gewürfelt, sondern weggelassen: Das Gerät
        # zeigt dann sein Typ-Icon und keinen Klartext, wie ohne Zuordnung.
        quelle = modus_quelle(eintrag.get("live"))
        if quelle and inv_id not in ergebnis.setdefault(quelle, []):
            ergebnis[quelle].append(inv_id)
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
    return (await _im_takt(db, anlage))[0]


async def lade_betriebsmodus_aktion_live(
    db: AsyncSession, anlage
) -> dict[int, str]:
    """Die gemessene Aktion je Gerät neben dem Kanon-Wert — ``{investition_id: "leerlauf"}``.

    P-433-1 (Konzept #433 E6): `idle` lässt den Kanon-Wert stehen (#399) und
    erscheint in den Live-Sichten als Zusatz «· Leerlauf». ⛔ **Nur für die
    Anzeige** — HA-Sensor und MQTT-Topic lesen `lade_betriebsmodus_live` und
    sehen den Kanon-Wert unverändert. Derselbe Abruf, derselbe 60-s-Takt.
    """
    return (await _im_takt(db, anlage))[1]


async def lade_zustaende_live(db: AsyncSession, anlage) -> dict[tuple[int, str], str]:
    """Die Zustände der E-Mobilität je ``(investition_id, feld)`` als Kanon-Wert (P-433-2b K1, Bauplan E2).

    Felder: Wallbox ``ladezustand``/``lademodus``, E-Auto ``ladezustand_fahrzeug``/``zu_hause`` (Kanon
    `core/zustands_kanon.py`). Dieselbe Regel wie beim Modus: HA über die ``live``-Entität des Felds, sonst MQTT
    (Topic ``…/live/inv/<id>/<feld>``, Kanon-Wort oder Zahlencode); ``quellen`` «keine» oder HA schließt MQTT aus.
    Ein fremder Wert, ``unknown``/``unavailable`` oder ein Gerät ohne Zuordnung **fehlt** (kein Chip, nie geraten).
    Derselbe 60-s-Takt wie der Modus, ein gebündelter HA-Abruf für alle E-Mob-Felder (benannte Grenze: der Chip ist
    bis zu 60 s alt).

    P-433-2b K2a: dazu das Textfeld Wallbox ``fahrzeug_am_ladepunkt`` als **Text** (getrimmt, ≤ 80 Zeichen;
    ``""`` heißt «die Steuerung hat geantwortet und kennt kein Fahrzeug», nie «keine Quelle»). Ohne Antwort fehlt
    der Eintrag.

    P-433-2b K2b (Option A): eine Wallbox ohne gemessenen ``ladezustand`` bekommt ihn aus den evcc-Rollen-Feldern
    ``evcc_verbunden``/``evcc_laedt``/``evcc_freigegeben`` (`_kombiniere_option_a`); ein gemessener geht vor.
    """
    return (await _im_takt(db, anlage))[2]


async def lade_staende_live(db: AsyncSession, anlage) -> dict[int, float]:
    """Der Kilometerstand je E-Auto — ``{investition_id: km}`` (P-433-2b K4, K4-1).

    Rohwert des Zählers, der am E-Auto auf ``km_gefahren`` zugeordnet ist: HA über die Entität des Felds
    (``felder.km_gefahren.sensor_id`` bzw. ``quellen``-Wahl HA, ``get_sensor_states_batch``), sonst MQTT aus dem
    Energie-Cache des Inbound (``inv/<id>/km_gefahren``); ``quellen`` «keine» schließt beides aus, ``quellen`` MQTT
    schließt HA aus. ⛔ **Nie** aus dem Monatsfeld ``km_stand`` (Handeingabe) und nie aus ``Monatsdaten``. Derselbe
    60-s-Takt wie Modus und Zustände (benannte Grenze: bis zu 60 s alt). Ein Auto ohne Zähler bzw. ohne Wert fehlt.
    """
    return (await _im_takt(db, anlage))[3]


async def _im_takt(
    db: AsyncSession, anlage,
) -> tuple[dict[int, str], dict[int, str], dict[tuple[int, str], str], dict[int, float]]:
    """Kanon, Aktion, E-Mob-Zustände und Zählerstände aus dem Takt-Cache, sonst frisch erhoben."""
    jetzt = time.monotonic()
    treffer = _cache.get(anlage.id)
    if treffer is not None and (jetzt - treffer[0]) < _TAKT_SEKUNDEN:
        return treffer[1], treffer[2], treffer[3], treffer[4]

    modi, aktionen, zustaende, staende = await _erhebe(db, anlage)
    _cache[anlage.id] = (jetzt, modi, aktionen, zustaende, staende)
    return modi, aktionen, zustaende, staende


async def _erhebe(
    db: AsyncSession, anlage,
) -> tuple[dict[int, str], dict[int, str], dict[tuple[int, str], str], dict[int, float]]:
    """Die eigentliche Erhebung — ohne Takt, damit der Takt eine Stelle hat.

    Erst die Geräte mit HA-Modus-Entität (`_erhebe_ha`), dann die übrigen über MQTT
    (`_erhebe_mqtt`). Ein HA-Gerät fällt nie auf MQTT zurück, auch nicht ohne HA.

    P-433-2b K1: die Abfrage nimmt jede Investition eines Typs mit Zustandsfeld (`_ZUSTAND_TYPEN`); der Modus-Pfad
    bekommt davon nur die Wärmepumpen (bitgleich zu vorher), die E-Mobilität ihren eigenen (`_erhebe_emob`).
    """
    result = await db.execute(
        select(Investition.id, Investition.typ).where(
            Investition.anlage_id == anlage.id,
            Investition.typ.in_(sorted(_ZUSTAND_TYPEN)),
            aktiv_jetzt(),
        )
    )
    typ_je_id = {inv_id: typ for inv_id, typ in result.all()}
    inv_ids = {inv_id for inv_id, typ in typ_je_id.items() if typ == "waermepumpe"}
    emob = {inv_id: typ for inv_id, typ in typ_je_id.items() if _EMOB_ZUSTAENDE.get(typ)}
    zustaende = await _erhebe_emob(anlage, emob)
    staende = await _erhebe_staende(anlage, emob)
    if not inv_ids:
        return {}, {}, zustaende, staende

    entity_map = _entity_zu_investitionen(anlage.sensor_mapping, inv_ids)
    modi, aktionen = await _erhebe_ha(entity_map)
    ha_ids = {inv_id for ids in entity_map.values() for inv_id in ids}
    modi.update(_erhebe_mqtt(anlage, inv_ids - ha_ids))
    return modi, aktionen, zustaende, staende


# ── Zählerstände der E-Mobilität (P-433-2b K4, K4-1) ─────────────────────────

#: Das Zählerfeld des Kilometerstands am E-Auto (Registry ``km_gefahren``, Kanal-Art ``stand``).
_KM_FELD = "km_gefahren"


def _stand_quellen(anlage, emob: dict[int, str]) -> tuple[dict[str, list[int]], list[int]]:
    """Je E-Auto die Quelle des km-Zählers: ``(entity → [inv_id], [inv_id über MQTT])`` — die Regel von
    ``_emob_quellen`` am Energie-Feld ``inv_energy_<id>_km_gefahren``: HA-Entität vor MQTT, ``quellen`` entscheidet."""
    from backend.services.datenquellen_resolver import ha_entity_fuer_feld
    from backend.services.snapshot.keys import QUELLE_HA_ENERGY

    mapping = anlage.sensor_mapping if isinstance(anlage.sensor_mapping, dict) else {}
    quellen = mapping.get("quellen") if isinstance(mapping.get("quellen"), dict) else {}
    ha: dict[str, list[int]] = {}
    mqtt: list[int] = []
    for inv_id in sorted(i for i, typ in emob.items() if typ == "e-auto"):
        field_id = f"inv_energy_{inv_id}_{_KM_FELD}"
        eintrag = quellen.get(field_id) if isinstance(quellen.get(field_id), dict) else {}
        wahl = eintrag.get("quelle")
        entity = (eintrag.get("entity_id") if wahl in QUELLE_HA_ENERGY else None) or \
            ha_entity_fuer_feld(field_id, mapping, {}, {})
        if wahl in _QUELLEN_MQTT or (wahl is None and not entity):
            mqtt.append(inv_id)
        elif entity and (wahl is None or wahl in QUELLE_HA_ENERGY):
            ha.setdefault(entity, []).append(inv_id)
    return ha, mqtt


async def _erhebe_staende(anlage, emob: dict[int, str]) -> dict[int, float]:
    """Die Kilometerstände — HA (ein gebündelter Abruf), dann MQTT aus dem Energie-Cache des Inbound."""
    if not emob:
        return {}
    ha, mqtt = _stand_quellen(anlage, emob)
    ergebnis: dict[int, float] = {}
    if ha:
        from backend.services.ha_state_service import get_ha_state_service

        ha_service = get_ha_state_service()
        if ha_service.is_available:
            try:
                staende = await ha_service.get_sensor_states_batch(list(ha))
            except Exception as e:  # pragma: no cover — Soft-fail, die Karte bleibt ohne Kilometerstand
                logger.warning("Kilometerstand (live) nicht lesbar: %s", e)
                staende = {}
            for entity, ids in ha.items():
                roh = staende.get(entity)
                for inv_id in ids if roh else ():
                    ergebnis[inv_id] = float(roh[0])
    if mqtt:
        from backend.services.mqtt_inbound_service import get_mqtt_inbound_service

        svc = get_mqtt_inbound_service()
        energie = svc.cache.get_energy_data(anlage.id) if svc is not None else {}
        for inv_id in mqtt:
            wert = energie.get(f"inv/{inv_id}/{_KM_FELD}")
            if wert is not None:
                ergebnis[inv_id] = float(wert)
    return ergebnis


# ── E-Mobilität (P-433-2b K1, Bauplan E2) ────────────────────────────────────


def _emob_quellen(anlage, emob: dict[int, str]) -> tuple[dict[str, list[tuple[int, str]]], list[tuple[int, str]]]:
    """Je Zustandsfeld der E-Mobilität: HA-Entität (``live``-Block) oder MQTT — die Modus-Regel, je Feld.

    Returns:
        ``(entity → [(inv_id, feld)], [(inv_id, feld) über MQTT])``. Ein Feld mit HA-Entität liest nur HA; ohne sie
        MQTT, außer ``quellen`` wählt ausdrücklich HA oder «keine» (C2a, wie `mqtt_modus_geraete`).
    """
    from backend.services.live_sensor_config import extract_quellen_live

    _qb, quellen_inv, _ha = extract_quellen_live(anlage)
    mapping = anlage.sensor_mapping if isinstance(anlage.sensor_mapping, dict) else {}
    invs = mapping.get("investitionen") or {}
    ha: dict[str, list[tuple[int, str]]] = {}
    mqtt: list[tuple[int, str]] = []
    for inv_id, typ in sorted(emob.items()):
        eintrag = invs.get(str(inv_id))
        live = (eintrag.get("live") if isinstance(eintrag, dict) else None) or {}
        gewaehlt = quellen_inv.get(str(inv_id)) or {}
        for feld in _EMOB_ZUSTAENDE[typ]:
            entity = live.get(feld) if isinstance(live, dict) else None
            if isinstance(entity, str) and entity:
                ha.setdefault(entity, []).append((inv_id, feld))
            elif feld not in gewaehlt or gewaehlt[feld][0] in _QUELLEN_MQTT:
                mqtt.append((inv_id, feld))
    return ha, mqtt


async def _erhebe_emob(anlage, emob: dict[int, str]) -> dict[tuple[int, str], str]:
    """Die Zustände der E-Mobilität — erst HA (ein gebündelter Abruf), dann MQTT aus dem Inbound-Cache."""
    if not emob:
        return {}
    ha, mqtt = _emob_quellen(anlage, emob)
    ergebnis = await _erhebe_emob_ha(ha)
    ergebnis.update(_erhebe_emob_mqtt(anlage, mqtt))
    return _kombiniere_option_a(ergebnis)


def _kombiniere_option_a(ergebnis: dict[tuple[int, str], str]) -> dict[tuple[int, str], str]:
    """Option A (P-433-2b K2b, Bauplan K2 §1 K2-7): der Ladezustand einer Wallbox aus den drei evcc-Rollen-Feldern.

    Je Wallbox mit ``evcc_verbunden`` und **ohne** gemessenen ``ladezustand`` (``(inv, "ladezustand")`` fehlt — nicht
    zugeordnet, keine Antwort, ``unknown`` oder fremder Wert):

    * ``evcc_verbunden`` aus ⇒ ``kein_fahrzeug``
    * verbunden ∧ ``evcc_laedt`` an ⇒ ``laedt``
    * verbunden ∧ ``evcc_freigegeben`` aus ⇒ ``wartet``
    * sonst verbunden ⇒ ``verbunden``

    ⛔ **Ein gemessener Ladezustand geht immer vor** (Sprengsatz S7) — Option A ersetzt den Template-Sensor (Weg B),
    sie überstimmt keinen Sensor. Fehlt ``evcc_laedt`` bzw. ``evcc_freigegeben``, gibt es kein «lädt» bzw. kein
    «wartet» (benannte Grenze); ohne ``evcc_verbunden`` gibt es keinen Ladezustand, nie geraten. «Fertig» kennt Option A
    nicht. Die drei Rollen-Werte bleiben im Ergebnis (die Datenquellen-Fläche und der Checker lesen sie selbst).

    P-433-2b K3 (Bauplan K3-4): die Regel selbst steht an **einem** Ort, ``zustands_kanon.ladezustand_aus_werten`` —
    dieselbe Funktion rechnet das Fenster der MQTT-Mitschrift und die Verschränkung des HA-Verlaufs.
    """
    for inv_id in [i for i, feld in ergebnis if feld == "evcc_verbunden"]:
        if (inv_id, zustands_kanon.LADEZUSTAND) in ergebnis:
            continue
        werte = {feld: ergebnis.get((inv_id, feld)) for feld in ("evcc_verbunden", "evcc_laedt", "evcc_freigegeben")}
        zustand = zustands_kanon.ladezustand_aus_werten(werte)
        if zustand is not None:
            ergebnis[(inv_id, zustands_kanon.LADEZUSTAND)] = zustand
    return ergebnis


async def _erhebe_emob_ha(ha: dict[str, list[tuple[int, str]]]) -> dict[tuple[int, str], str]:
    """Zustände aus HA — ohne Entität kein Abruf; die Ziffer eines HA-Sensors ist kein Code (``codes=False``)."""
    if not ha:
        return {}
    from backend.services.ha_state_service import get_ha_state_service

    ha_service = get_ha_state_service()
    if not ha_service.is_available:
        return {}
    try:
        zustaende = await ha_service.get_zustand_states_batch(list(ha))
    except Exception as e:  # pragma: no cover — Soft-fail, die Sicht bleibt ohne Zustand
        logger.warning("Zustände E-Mobilität (live) nicht lesbar: %s", e)
        return {}
    ergebnis: dict[tuple[int, str], str] = {}
    for entity, ziele in ha.items():
        roh = zustaende.get(entity)
        for inv_id, feld in ziele:
            wert = _emob_wert(feld, ist_text_feld(feld), roh[0] if roh else None, codes=False)
            if wert is not None:
                ergebnis[(inv_id, feld)] = wert
    return ergebnis


def _erhebe_emob_mqtt(anlage, ziele: list[tuple[int, str]]) -> dict[tuple[int, str], str]:
    """Zustände aus dem MQTT-Inbound-Cache (roher String, `mqtt_inbound_service`), Kanon-Wort oder Zahlencode."""
    if not ziele:
        return {}
    from backend.services.mqtt_inbound_service import get_mqtt_inbound_service

    svc = get_mqtt_inbound_service()
    if svc is None:
        return {}
    werte = svc.cache.get_all_live_inv(anlage.id)
    ergebnis: dict[tuple[int, str], str] = {}
    for inv_id, feld in ziele:
        # Ein fehlender Cache-Eintrag ist ``None`` (keine Antwort), ein abgelegter leerer Text ``""`` (Antwort leer).
        wert = _emob_wert(feld, ist_text_feld(feld), (werte.get(str(inv_id)) or {}).get(feld), codes=True)
        if wert is not None:
            ergebnis[(inv_id, feld)] = wert
    return ergebnis


#: Die ``quellen``-Wahlen, unter denen der Modus aus dem Inbound-Cache gelesen wird.
_QUELLEN_MQTT: frozenset[str] = frozenset({"mqtt_inbound_standard", "mqtt_gateway"})


def mqtt_modus_geraete(anlage, inv_ids: set[int]) -> set[int]:
    """Die Geräte unter ``inv_ids``, deren Modus aus MQTT kommen darf — die eine Regel für Live und Mitschrift.

    Ausgeschlossen: ein Gerät mit HA-Modus-Entität im ``live``-Block (`modus_quelle`, HA gewinnt) und ein Gerät,
    dessen Modus-Feld per ``quellen`` ausdrücklich auf HA oder «keine» steht (C2a, wie
    `live_power_service._apply_quellen_overrides`). Kein Eintrag oder Inbound/Gateway ⇒ MQTT.
    """
    from backend.services.live_sensor_config import extract_quellen_live

    _qb, quellen_inv, _ha = extract_quellen_live(anlage)
    mapping = anlage.sensor_mapping if isinstance(anlage.sensor_mapping, dict) else {}
    invs = mapping.get("investitionen") or {}
    out: set[int] = set()
    for inv_id in inv_ids:
        eintrag = invs.get(str(inv_id))
        if isinstance(eintrag, dict) and modus_quelle(eintrag.get("live")) is not None:
            continue
        gewaehlt = {
            tup[0] for key, tup in (quellen_inv.get(str(inv_id)) or {}).items()
            if basis_feld_key(key) == MODUS_FELD_KEY
        }
        if gewaehlt - _QUELLEN_MQTT:
            continue
        out.add(inv_id)
    return out


def _erhebe_mqtt(anlage, inv_ids: set[int]) -> dict[int, str]:
    """Der Modus der Geräte ohne HA-Modus aus dem MQTT-Inbound-Cache (HA-Bauform §9, S1-4).

    Mehrere Modus-Keys eines Geräts (Innengeräte-Suffix): gleicher Kanon-Wert ⇒ eine Aussage,
    verschiedene ⇒ das Gerät fehlt (`modus_aus_zustaenden`, N-340). Keine Aktion.
    """
    if not inv_ids:
        return {}
    from backend.services.mqtt_inbound_service import get_mqtt_inbound_service

    svc = get_mqtt_inbound_service()
    if svc is None:
        return {}
    werte = svc.cache.get_all_live_inv(anlage.id)
    ergebnis: dict[int, str] = {}
    for inv_id in mqtt_modus_geraete(anlage, inv_ids):
        modus = modus_aus_zustaenden(werte.get(str(inv_id)))
        if modus is not None:
            ergebnis[inv_id] = modus
    return ergebnis


async def _erhebe_ha(entity_map: dict[str, list[int]]) -> tuple[dict[int, str], dict[int, str]]:
    """Modus und Aktion der Geräte mit HA-Modus-Entität — ohne Entität kein HA-Abruf."""
    if not entity_map:
        return {}, {}

    from backend.services.ha_state_service import get_ha_state_service

    ha_service = get_ha_state_service()
    if not ha_service.is_available:
        return {}, {}

    try:
        zustaende = await ha_service.get_zustand_states_batch(list(entity_map))
    except Exception as e:  # pragma: no cover — Soft-fail, die Sicht bleibt ohne Modus
        logger.warning("Betriebsmodus (live) nicht lesbar: %s", e)
        return {}, {}

    ergebnis: dict[int, str] = {}
    aktionen: dict[int, str] = {}
    for entity, ids in entity_map.items():
        roh = zustaende.get(entity)
        if not roh:
            continue
        modus = normalisiere_betriebsmodus(*roh)
        if modus is None:
            continue
        aktion = betriebsmodus_aktion(modus, roh[1])
        for inv_id in ids:
            ergebnis[inv_id] = modus
            if aktion is not None:
                aktionen[inv_id] = aktion
    return ergebnis, aktionen
