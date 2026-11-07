"""
Stunden-Leistungskurve aus HA Long-Term Statistics — für Tage außerhalb der Historie.

`aggregate_day` braucht neben den kWh-Zählerständen eine Stunden-Leistungskurve;
im Normalfall holt es sie über `live_tagesverlauf_service.get_tagesverlauf` aus der
HA-**Historie**. Die reicht nur so weit zurück, wie der Recorder aufhebt (Default
10 Tage) — für ältere Tage kommt nichts zurück, und `aggregate_day` steigt aus,
BEVOR es die Zähler auch nur anfasst.

Der Vollbackfill hat dafür seit v3.34.2 einen zweiten Weg: die Stunden-Leistungen
gebündelt aus der **Langzeitstatistik** (`get_hourly_sensor_data`), durchgereicht
als `prefetched_tagesverlauf`. Dieses Modul ist genau dieser Weg, aus
`backfill.py` herausgelöst — damit ihn auch die Reparatur-Werkbank nutzen kann.

Auslöser Forum simon42 #89667/72 (dietmar1968): der Daten-Checker prüft 90 Tage
zurück und bot für 39 Lücken einen Reparatur-Knopf an; die Reparatur hing an der
10-Tage-Historie und meldete für alles Ältere „keine Live-/MQTT-Daten gefunden".
Die Werte lagen die ganze Zeit in der Langzeitstatistik — der Checker las sie ja
von dort, um die Lücke überhaupt zu melden.

Bewusst KEIN zweiter Aggregations-Pfad: dieses Modul beschafft nur die Kurve.
Alles Weitere (Boundary-kWh, Komponenten, Peaks, Preise, Counter, Provenance,
Invariante) bleibt in `aggregate_day` — genau ein Top-Level-Schreibpfad
(Audit §6.1, Plan v3.34 E1).
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Literal, Optional

from sqlalchemy import select as sa_select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.berechnungen.erzeuger_traeger import (
    abgetretene_bkw_ids,
    kuerze_bkw_in_werte_map,
    modul_kinder,
)
from backend.models.anlage import Anlage

logger = logging.getLogger(__name__)

# Warum nichts (oder nicht alles) zurückkam. Der Aufrufer entscheidet, was er
# daraus macht — der Backfill zählt, die Reparatur sagt es dem Anwender ins
# Gesicht statt „keine Daten gefunden" zu raten.
LtsGrund = Literal["ok", "keine_live_zuordnung", "ha_nicht_verfuegbar", "keine_daten"]

_GRUND_TEXT: dict[str, str] = {
    "keine_live_zuordnung": (
        "Dieser Anlage ist kein Leistungssensor (W) zugeordnet. Der Tages-Lauf "
        "braucht neben dem Zählerstand die Stunden-Leistungskurve — zuerst unter "
        "Einstellungen → Datenquellen einen Leistungssensor zuordnen."
    ),
    "ha_nicht_verfuegbar": (
        "Die Home-Assistant-Langzeitstatistik ist gerade nicht erreichbar."
    ),
    "keine_daten": (
        "Die Home-Assistant-Langzeitstatistik hat für diesen Zeitraum keine "
        "Werte — eedc reicht nur so weit zurück wie HA selbst."
    ),
}


def grund_text(grund: LtsGrund) -> str:
    """Anwender-Satz zu einem Grund (leer bei „ok")."""
    return _GRUND_TEXT.get(grund, "")


@dataclass
class LtsTagesverlauf:
    """Ergebnis von `lade_tagesverlauf_aus_lts`.

    `tage` enthält NUR Tage mit mindestens einem Stundenwert — ein fehlender Tag
    ist bei `grund == "ok"` eine echte Lücke in HA, kein Fehler des Aufrufs.
    """

    tage: dict[date, dict] = field(default_factory=dict)
    grund: LtsGrund = "ok"


@dataclass(frozen=True)
class _BkwAbtretung:
    """N-777: die Abtretung der Balkonkraftwerke mit `pv-module`-Kindern an EINEM Tag.

    ``keys`` — die PV-Serien-Keys der abtretenden BKW mit eigener Serie und ihrer Kinder mit eigener Serie: auf genau
    diesen Werten kuerzt `_bkw_rest_einsetzen` je Stunde. ``investitionen`` — die am Tag aktiven Investitionen
    (Elternschaft fuer `kuerze_bkw_in_werte_map`).
    """

    keys: frozenset
    investitionen: tuple


def _bkw_abtretung(investitionen: dict, tages_serien: list[dict], current: date) -> Optional[_BkwAbtretung]:
    """N-777: die Abtretung des Tages ``current`` — ``None``, wenn kein am Tag aktives BKW mit eigener PV-Serie ein am Tag
    aktives Modul-Kind mit eigener PV-Serie hat (dann gibt es nichts zu kuerzen).

    Als Kind zaehlt nur ein am Tag aktives Modul (P11, N-615): ein spaeter angeschafftes Modul nimmt dem Balkonkraftwerk
    die frueheren Tage nicht.
    """
    aktiv = tuple(inv for inv in investitionen.values() if inv.ist_aktiv_an(current))
    abgetreten = abgetretene_bkw_ids(aktiv)
    if not abgetreten:
        return None
    key_je_inv = {str(s["inv_id"]): s["key"] for s in tages_serien if s["kategorie"] == "pv" and s.get("inv_id") is not None}
    keys: set[str] = set()
    for bkw_id in abgetreten:
        bkw_key = key_je_inv.get(str(bkw_id))
        if bkw_key is None:
            continue
        kinder = [key_je_inv[str(k.id)] for k in modul_kinder(bkw_id, aktiv) if str(k.id) in key_je_inv]
        if kinder:
            keys.update([bkw_key, *kinder])
    if not keys:
        return None
    return _BkwAbtretung(keys=frozenset(keys), investitionen=aktiv)


def _bkw_rest_einsetzen(bkw: _BkwAbtretung, roh_pv: dict[str, float], werte: dict[str, float]) -> None:
    """N-777: dieselbe Kuerzung wie der Live-Zwilling (`live_tagesverlauf_service._bkw_kuerzung_slot`) — ueber
    `kuerze_bkw_in_werte_map` (Werte-Regel N-536) auf den ungerundeten Stundenwerten: das BKW traegt
    ``max(0, BKW − Σ Kinder mit Wert in dieser Stunde)``; Rest 0 ⇒ der Key faellt heraus. Ein Kind ohne Wert in der Stunde
    zieht nichts ab — das BKW deckt dessen Luecke."""
    gekuerzt = kuerze_bkw_in_werte_map(roh_pv, bkw.investitionen)
    for key, roh in roh_pv.items():
        if key not in gekuerzt:
            werte.pop(key, None)
        elif gekuerzt[key] != roh:
            werte[key] = round(gekuerzt[key], 3)


def _stunden_werte(
    hourly_data: dict,
    serie_entities: dict,
    tages_serien: list[dict],
    datum_iso: str,
    stunde: int,
    netz_kombi_eid: Optional[str],
    netz_bezug_eid: Optional[str],
    netz_einspeisung_eid: Optional[str],
    bkw: Optional["_BkwAbtretung"] = None,
) -> dict[str, float]:
    """Das ``werte``-Dict EINER Stunde aus den gebuendelten LTS-Daten.

    Herausgezogen, damit der **Vortagsrand** (die Stunde 23 des Vortags, die
    den Backward-Slot 0 traegt — N-382) nach genau derselben Regel entsteht wie
    jede andere Stunde. Zwei Aufbauten fuer dieselbe Groesse waeren zwei
    Wahrheiten, sobald eine von beiden angefasst wird.

    ``bkw`` (N-777): die Abtretung der Balkonkraftwerke mit `pv-module`-Kindern an diesem Tag
    (`_bkw_abtretung`) — ein BKW traegt je Stunde nur den Rest neben den Kindern mit Wert
    (`_bkw_rest_einsetzen`, Werte-Regel des Live-Pfads). ``None`` = nichts abgetreten.

    Leeres Dict = diese Stunde hat in keiner Serie einen Wert.
    """
    werte: dict[str, float] = {}
    roh_pv: dict[str, float] = {}

    for serie in tages_serien:
        skey = serie["key"]
        if serie["kategorie"] == "netz":
            continue  # Netz separat
        entity_ids = serie_entities.get(skey, [])
        serie_sum_kw = 0.0
        has_data = False
        for entity_id in entity_ids:
            val = hourly_data.get(entity_id, {}).get(datum_iso, {}).get(stunde)
            if val is not None:
                serie_sum_kw += val
                has_data = True
        if has_data:
            if serie["bidirektional"]:
                raw_val = -serie_sum_kw
            elif serie["seite"] == "senke":
                raw_val = -abs(serie_sum_kw)
            else:
                raw_val = abs(serie_sum_kw)
            werte[skey] = round(raw_val, 3)
            if bkw is not None and skey in bkw.keys:
                roh_pv[skey] = raw_val
    if roh_pv:
        _bkw_rest_einsetzen(bkw, roh_pv, werte)

    # Netz (Kombi-Sensor oder getrennt Bezug/Einspeisung)
    bezug_kw = 0.0
    einsp_kw = 0.0
    if netz_kombi_eid:
        val = hourly_data.get(netz_kombi_eid, {}).get(datum_iso, {}).get(stunde)
        if val is not None:
            if val >= 0:
                bezug_kw = val
            else:
                einsp_kw = abs(val)
    else:
        if netz_bezug_eid:
            val = hourly_data.get(netz_bezug_eid, {}).get(datum_iso, {}).get(stunde)
            if val is not None:
                bezug_kw = max(0.0, val)
        if netz_einspeisung_eid:
            val = hourly_data.get(netz_einspeisung_eid, {}).get(datum_iso, {}).get(stunde)
            if val is not None:
                einsp_kw = max(0.0, val)
    netto_kw = bezug_kw - einsp_kw
    if bezug_kw > 0 or einsp_kw > 0 or abs(netto_kw) > 0.001:
        werte["netz"] = round(netto_kw, 3)

    return werte


def _serien_je_tag(
    inv_live_map: dict, investitionen: dict, von: date, bis: date, nur_tage: Optional[set[date]],
) -> tuple[dict[date, list[dict]], dict[str, list[str]], list[dict]]:
    """Phase 1 von `lade_tagesverlauf_aus_lts` (RF-74): die Investitions-Serien **je Tag** über die geteilte Quelle
    (`baue_investitions_serien`, #318/M1) und ihre Vereinigung → ``(serien_je_tag, serie_entities, serien)``."""
    from backend.services.live_sensor_config import baue_investitions_serien

    # ── Serien + Entity-Mapping über die geteilte Quelle (Issue #318, M1) ──────
    # Identische Selektion (inkl. Pool-Dedup #227) wie der Live-Pfad
    # (`live_tagesverlauf_service`), damit Scheduler- und LTS-Aggregation
    # desselben Tages deckungsgleiche TEP.komponenten/Peaks liefern. Hier nur die
    # Kern-Felder; Chart-Metadaten sind Live-spezifisch.
    #
    # ⭐ S2-8b (Zählerlücken wie HA, Mitnahme aus N-555 Stufe 2): „Wallbox **in
    # Betrieb**" entscheidet sich **je Tag** (Konzept Heimladung Regel 0: „im
    # betrachteten Monat oder Tag"). Bis 26.09.2026 lief die Auswahl EINMAL über
    # die ganze Range ohne `tag` — eine Wallbox, die irgendwann im Zeitraum in
    # Betrieb war, verdrängte die E-Auto-Serie auch an den Tagen VOR ihrer
    # Anschaffung (bzw. nach ihrer Stilllegung); die Ladung dieser Tage fehlte
    # im Tagesverlauf. Jetzt je Tag eine Auswahl; der gebündelte HA-Abruf holt
    # die Vereinigung aller Entities.
    serien_je_tag: dict[date, list[dict]] = {}
    serie_entities: dict[str, list[str]] = {}
    _tag = von
    while _tag <= bis:
        if nur_tage is None or _tag in nur_tage:
            _core, _entities = baue_investitions_serien(inv_live_map, investitionen, tag=_tag)
            serien_je_tag[_tag] = [
                {"key": s.key, "inv_id": s.inv_id, "kategorie": s.kategorie,
                 "seite": s.seite, "bidirektional": s.bidirektional}
                for s in _core
            ]
            serie_entities.update(_entities)
        _tag += timedelta(days=1)
    # Vereinigung aller Tages-Serien (stabile Reihenfolge) — für Fallback-/Netz-
    # Entscheidungen und das Rückgabe-Feld `serien`.
    serien: list[dict] = []
    _gesehen: set[str] = set()
    for _liste in serien_je_tag.values():
        for s in _liste:
            if s["key"] not in _gesehen:
                _gesehen.add(s["key"])
                serien.append(s)
    return serien_je_tag, serie_entities, serien


def _basis_serien(
    serien: list[dict], serie_entities: dict[str, list[str]], basis_live: dict,
) -> tuple[Optional[str], Optional[str], Optional[str]]:
    """Phase 2 (RF-74): PV Gesamt als Fallback und die Netz-Serie (Kombi nur ohne dedizierte Sensoren) — hängt an
    ``serien``/``serie_entities`` an und liefert ``(netz_kombi_eid, netz_bezug_eid, netz_einspeisung_eid)``."""
    # PV Gesamt als Fallback
    has_individual_pv = any(s["kategorie"] == "pv" for s in serien)
    if not has_individual_pv and basis_live.get("pv_gesamt_w"):
        serien.append({"key": "pv_gesamt", "kategorie": "pv", "seite": "quelle", "bidirektional": False})
        serie_entities["pv_gesamt"] = [basis_live["pv_gesamt_w"]]

    # Netz-Konfiguration
    netz_kombi_eid = basis_live.get("netz_kombi_w")
    netz_einspeisung_eid = basis_live.get("einspeisung_w")
    netz_bezug_eid = basis_live.get("netzbezug_w")
    if netz_kombi_eid and not netz_einspeisung_eid and not netz_bezug_eid:
        serien.append({"key": "netz", "kategorie": "netz", "seite": "quelle", "bidirektional": True})
    elif netz_einspeisung_eid or netz_bezug_eid:
        netz_kombi_eid = None
        serien.append({"key": "netz", "kategorie": "netz", "seite": "quelle", "bidirektional": True})
    return netz_kombi_eid, netz_bezug_eid, netz_einspeisung_eid


def _alle_entity_ids(
    serie_entities: dict[str, list[str]], netz_kombi_eid: Optional[str], netz_bezug_eid: Optional[str],
    netz_einspeisung_eid: Optional[str],
) -> set[str]:
    """Phase 3 (RF-74): alle Entity-IDs für den einen gebündelten LTS-Read."""
    # ── Alle Entity-IDs sammeln ──────────────────────────────────────────────
    all_entity_ids: set[str] = set(eid for eids in serie_entities.values() for eid in eids)
    if netz_kombi_eid:
        all_entity_ids.add(netz_kombi_eid)
    if netz_bezug_eid:
        all_entity_ids.add(netz_bezug_eid)
    if netz_einspeisung_eid:
        all_entity_ids.add(netz_einspeisung_eid)
    return all_entity_ids


def _invertieren(
    hourly_data: dict, basis_live: dict, inv_live_map: dict, basis_invert: dict, inv_invert_map: dict,
) -> None:
    """Phase 4 (RF-74): Vorzeichen-Invertierung auf den gelesenen Stunden (in place, wie `apply_invert_to_history`)."""
    # ── Vorzeichen-Invertierung anwenden (wie apply_invert_to_history) ───────
    invert_eids: set[str] = set()
    for key, should_invert in basis_invert.items():
        if should_invert and key in basis_live:
            invert_eids.add(basis_live[key])
    for inv_id, invert_flags in inv_invert_map.items():
        live = inv_live_map.get(inv_id, {})
        for key, should_invert in invert_flags.items():
            if should_invert and key in live:
                invert_eids.add(live[key])
    for eid in invert_eids:
        if eid in hourly_data:
            for datum_iso in hourly_data[eid]:
                hourly_data[eid][datum_iso] = {
                    h: -v for h, v in hourly_data[eid][datum_iso].items()
                }


@dataclass
class _KurvenBasis:
    """Was Phase 5 (`_punkte_je_tag`) je Tag braucht (RF-74)."""

    hourly_data: dict
    serie_entities: dict[str, list[str]]
    serien_je_tag: dict[date, list[dict]]
    serien: list[dict]
    investitionen: dict
    netz_kombi_eid: Optional[str]
    netz_bezug_eid: Optional[str]
    netz_einspeisung_eid: Optional[str]


def _tages_serien(k: _KurvenBasis, current: date) -> list[dict]:
    """Die Serien EINES Tages (RF-74): die Investitions-Serien dieses Tages plus die Basis-Serien, nur aktive Investitionen."""
    serien, investitionen = k.serien, k.investitionen
    # Serien filtern: nur Investitionen, die an diesem Tag aktiv waren.
    # In-Memory-Pendant zum `aktiv_am_tag`-Inv-Load in `aggregate_day`
    # (Audit §6.4) — punkte + Serien-Metadaten bleiben so tag-konsistent.
    # S2-8b: die Investitions-Serien DIESES Tages (Wallbox in Betrieb je
    # Tag), dazu die Basis-Serien (PV Gesamt, Netz) aus der Vereinigung.
    kandidaten = k.serien_je_tag.get(current, []) + [
        s for s in serien if s.get("inv_id") is None
    ]
    return [
        s for s in kandidaten
        if s.get("inv_id") is None  # Basis-Serien (PV Gesamt, Netz)
        or investitionen.get(s["inv_id"], None) is None  # Safety
        or investitionen[s["inv_id"]].ist_aktiv_an(current)
    ]


def _tag_punkte(k: _KurvenBasis, current: date) -> Optional[dict]:
    """Die Kurve EINES Tages (RF-74): Punkte je Stunde mit Daten und der Vortagsrand; ``None`` ohne einen Punkt."""
    hourly_data, serie_entities = k.hourly_data, k.serie_entities
    netz_kombi_eid, netz_bezug_eid, netz_einspeisung_eid = k.netz_kombi_eid, k.netz_bezug_eid, k.netz_einspeisung_eid
    datum_iso = current.isoformat()
    tages_serien = _tages_serien(k, current)
    bkw = _bkw_abtretung(k.investitionen, tages_serien, current)   # N-777

    # punkte (get_tagesverlauf-Form): je Stunde MIT Daten ein werte-Dict
    # {serie_key: kW}. Stunden ohne jeglichen Wert werden ausgelassen —
    # damit bleibt `stunden_verfuegbar` die Zahl der Stunden mit Daten.
    punkte: list[dict] = []
    for h in range(24):
        werte = _stunden_werte(
            hourly_data, serie_entities, tages_serien, datum_iso, h,
            netz_kombi_eid, netz_bezug_eid, netz_einspeisung_eid, bkw,
        )
        if werte:
            punkte.append({"zeit": f"{h:02d}:00", "werte": werte})

    # Vortagsrand: [Vortag 23:00, 00:00) = das Intervall des Backward-
    # Slots 0 (N-382). Dieselbe Bauform wie ein regulaerer Punkt, nur aus
    # dem Datum davor — deshalb eine eigene Liste: ein Punkt traegt seine
    # Uhrzeit, nicht sein Datum, und „23:00" von gestern waere neben
    # „23:00" von heute nicht mehr unterscheidbar.
    vortag_iso = (current - timedelta(days=1)).isoformat()
    rand_werte = _stunden_werte(
        hourly_data, serie_entities, tages_serien, vortag_iso, 23,
        netz_kombi_eid, netz_bezug_eid, netz_einspeisung_eid, bkw,
    )
    vortagsrand = (
        [{"zeit": "23:00", "werte": rand_werte}] if rand_werte else []
    )

    if punkte:
        return {
            "serien": tages_serien,
            "punkte": punkte,
            "vortagsrand": vortagsrand,
        }
    return None


def _punkte_je_tag(k: _KurvenBasis, von: date, bis: date, nur_tage: Optional[set[date]]) -> dict[date, dict]:
    """Phase 5 (RF-74): die Kurve je Tag der Range (nur ``nur_tage``, wenn gesetzt); Tage ohne Punkt fehlen."""
    # ── Punkte je Tag bauen ─────────────────────────────────────────────────
    ergebnis: dict[date, dict] = {}
    current = von
    while current <= bis:
        if nur_tage is not None and current not in nur_tage:
            current += timedelta(days=1)
            continue

        tag_kurve = _tag_punkte(k, current)
        if tag_kurve is not None:
            ergebnis[current] = tag_kurve

        current += timedelta(days=1)
    return ergebnis


async def lade_tagesverlauf_aus_lts(
    db: AsyncSession,
    anlage: Anlage,
    von: date,
    bis: date,
    nur_tage: Optional[set[date]] = None,
) -> LtsTagesverlauf:
    """
    Baut die Stunden-Leistungskurve je Tag aus HA-LTS.

    Args:
        db: DB-Session
        anlage: Die Anlage (liefert die Live-Sensor-Zuordnung)
        von/bis: Datumsbereich (inklusiv) — EIN gebündelter LTS-Read dafür
        nur_tage: optional die Teilmenge, für die Punkte gebaut werden sollen
            (der Bulk-Read umfasst trotzdem die ganze Range — er kostet
            einmal, das Punkte-Bauen kostet pro Tag). None = alle Tage.

    Returns:
        `LtsTagesverlauf` — `tage` in der Form, die
        `aggregate_day(prefetched_tagesverlauf=…)` erwartet, plus `grund`, warum
        gegebenenfalls nichts kam. Die Unterscheidung ist keine Kosmetik: „du
        hast keinen Leistungssensor zugeordnet" und „HA reicht nicht so weit
        zurück" verlangen verschiedene Handgriffe vom Anwender.

    Form (RF-74, 5.11.2026): Orchestrator (Investitionen laden, Live-Zuordnung, Wächter, der eine gebündelte LTS-Read)
    über fünf Phasen in dieser Datei — `_serien_je_tag` (geteilte Quelle `baue_investitions_serien` je Tag, S2-8b,
    und die Vereinigung) · `_basis_serien` (PV Gesamt als Fallback, Netz-Serie) · `_alle_entity_ids` · `_invertieren`
    · `_punkte_je_tag` (je Tag `_tag_punkte`: `_tages_serien`, Punkte je Stunde über `_stunden_werte`, Vortagsrand).
    Rechnet nichts: die Stundenwerte baut `_stunden_werte`, alles Weitere `aggregate_day`.
    """
    from backend.models.investition import Investition
    from backend.utils.investition_filter import aktiv_im_zeitraum
    from backend.services.live_sensor_config import extract_live_config
    from backend.services.ha_statistics_service import get_ha_statistics_service

    # Investitionen laden — alle die im Zeitraum aktiv waren (`aktiv_im_zeitraum`),
    # für den Serien-Aufbau über die Range. Die Per-Tag-Verfeinerung (genau die am
    # jeweiligen Tag aktiven) macht die `ist_aktiv_an`-Filterung unten plus der
    # `aktiv_am_tag`-Inv-Load in `aggregate_day` (Audit §6.4).
    inv_result = await db.execute(
        sa_select(Investition).where(
            Investition.anlage_id == anlage.id,
            aktiv_im_zeitraum(von, bis),
        )
    )
    investitionen: dict[str, Investition] = {
        str(inv.id): inv for inv in inv_result.scalars().all()
    }

    basis_live, inv_live_map, basis_invert, inv_invert_map = extract_live_config(anlage)

    if not basis_live and not inv_live_map:
        logger.info(f"Anlage {anlage.id}: Keine Live-Sensoren konfiguriert, LTS-Tagesverlauf übersprungen")
        return LtsTagesverlauf(grund="keine_live_zuordnung")

    serien_je_tag, serie_entities, serien = _serien_je_tag(inv_live_map, investitionen, von, bis, nur_tage)
    netz_kombi_eid, netz_bezug_eid, netz_einspeisung_eid = _basis_serien(serien, serie_entities, basis_live)
    all_entity_ids = _alle_entity_ids(serie_entities, netz_kombi_eid, netz_bezug_eid, netz_einspeisung_eid)

    # SoC wird hier NICHT vorgeholt — `aggregate_day` holt die Speicher-SoC-History
    # selbst über `_get_soc_history` (Pfad 1: HA-LTS-Hourly-Mean, dieselbe Quelle
    # wie der Bulk-Read → für historische Tage verfügbar). v3.34.2 Phase B.

    if not all_entity_ids:
        return LtsTagesverlauf(grund="keine_live_zuordnung")

    # ── HA Statistics abfragen (Executor wegen Sync-SQLAlchemy) ─────────────
    ha_service = get_ha_statistics_service()
    if not ha_service.is_available:
        logger.warning(f"Anlage {anlage.id}: HA Statistics nicht verfügbar, LTS-Tagesverlauf übersprungen")
        return LtsTagesverlauf(grund="ha_nicht_verfuegbar")

    # Einen Tag frueher beginnen: der Backward-Slot 0 eines Tages traegt
    # [Vortag 23:00, 00:00) (SoT `core/berechnungen/slot_konvention.py`). Der
    # Read ist EIN gebuendelter Aufruf ueber die Range — ein Tag mehr kostet
    # keine zusaetzliche Abfrage, nur eine geringfuegig groessere Antwort.
    hourly_data = await asyncio.to_thread(
        ha_service.get_hourly_sensor_data, list(all_entity_ids),
        von - timedelta(days=1), bis
    )

    if not hourly_data:
        logger.info(f"Anlage {anlage.id}: Keine Statistics-Daten für {von}–{bis}")
        return LtsTagesverlauf(grund="keine_daten")

    _invertieren(hourly_data, basis_live, inv_live_map, basis_invert, inv_invert_map)

    kurve = _KurvenBasis(
        hourly_data=hourly_data, serie_entities=serie_entities, serien_je_tag=serien_je_tag, serien=serien,
        investitionen=investitionen, netz_kombi_eid=netz_kombi_eid, netz_bezug_eid=netz_bezug_eid,
        netz_einspeisung_eid=netz_einspeisung_eid,
    )
    return LtsTagesverlauf(tage=_punkte_je_tag(kurve, von, bis, nur_tage))
