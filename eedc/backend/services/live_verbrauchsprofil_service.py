"""
Verbrauchsprofil-Service — stündliches Verbrauchsprofil aus EEDC-DB, HA-History oder MQTT.

Ausgelagert aus live_power_service.py (Schritt 4 des Refactorings).

Priorität der Datenquellen:
  1. TagesEnergieProfil (EEDC-DB) — lokal, kein HA-Call, überlebt Neustarts
  2. HA-History — Fallback für neue Installationen ohne DB-Daten
  3. MQTT Energy Snapshots — Fallback für Standalone ohne HA

**Alle drei Quellen bündeln backward** (`core/berechnungen/slot_konvention.py`,
#144/#297): Slot ``h`` = Energie im Intervall ``[h-1, h)``. Der DB-Pfad erbt das
aus ``TagesEnergieProfil.stunde``, HA-History und MQTT bekommen es über
``_slot_fenster``. Bis v4.0.5 bündelten die beiden Fallbacks forward (Energie
``[h, h+1)`` nach Index ``h``) — die gestrichelte Verbrauchsprognose im
Live-Chart lag damit eine Stunde zu früh, sichtbar nur bei frischer Installation
und im Standalone-Betrieb, weil sonst der DB-Pfad greift.

**Und alle drei Quellen zählen eine unvollständige Stunde nicht mit** (N-45/N-46).
Der DB-Pfad tut das von jeher: eine Stunde ohne Zeile liefert keine Stichprobe.
Die beiden Fallbacks taten es bis v4.0.5 nicht —

* MQTT maß den Zuwachs zwischen dem *ersten und letzten Snapshot innerhalb* der
  Stunde; das letzte Snapshot-Intervall fiel systematisch heraus (bei 5-Minuten-
  Takt rund 8 % zu wenig). Jetzt wird über die **Intervallgrenzen** gemessen,
  und fehlt ein Randwert, gilt die Stunde als unvollständig (N-45).
* HA hängte für jede Stunde eine Stichprobe an — auch für Stunden, in denen der
  Recorder gar nichts geliefert hatte. Aus *unbekannt* wurde so *war nichts*,
  und ein Tag ohne History drückte das Profil nach unten (N-46).

Eine ausgelassene Stunde bleibt im Ergebnis leer (``_build_profil_result``
nimmt nur Slots mit Stichproben auf); der Konsument in
``api/routes/live_wetter.py::_berechne_verbrauchsprofil`` erkennt den fehlenden
Slot und setzt seine Standard-Grundlast ein, statt still 0 kW anzunehmen
(Anschluss ADR-002/P4).
"""

import logging
from bisect import bisect_right
from datetime import datetime, timedelta, date
from typing import Iterator, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.berechnungen.slot_konvention import backward_slot_aus_period_start
from backend.core.config import HA_INTEGRATION_AVAILABLE
from backend.models.anlage import Anlage
from backend.models.investition import Investition
from backend.utils.investition_filter import aktiv_jetzt
from backend.services.live_sensor_config import (
    ERZEUGER_TYPEN,
    extract_live_config,
)
from backend.services.live_history_service import (
    get_history_normalized,
    apply_invert_to_history,
)

logger = logging.getLogger(__name__)

# Profil-Fenster: die letzten 7 vollen Tage (heute ausgenommen — unvollständig).
# Identisch in allen drei Quellen: der DB-Pfad filtert `datum >= heute-7 < heute`,
# HA und MQTT laufen über `_slot_fenster(heute - 7 Tage)`.
TAGE_FENSTER = 7

# Wie alt ein Zählerstand an einer Stundengrenze höchstens sein darf, um noch als
# deren Randwert zu gelten. Der Scheduler schreibt MQTT-Snapshots alle 5 Minuten
# (`IntervalTrigger(minutes=5)`) — aber **nicht** auf die volle Stunde gerastert:
# die Phase hängt am Startzeitpunkt und verschiebt sich bei jedem Neustart. Im
# Normalbetrieb liegt der letzte Stand deshalb knapp unter 5 Minuten vor der
# Grenze; die 6. Minute ist Reserve für Scheduler-Verzug.
#
# Bewusst **nicht** großzügiger: ein ausgefallener Snapshot macht die Stunde
# unvollständig, und dann wird sie ausgelassen statt geschätzt. Die tolerierte
# Restunschärfe kostet keine Energie — benachbarte Stunden lesen denselben
# Randwert, die Tagessumme bleibt erhalten.
RAND_TOLERANZ = timedelta(minutes=6)


def _fenster_start(start_tag: date) -> datetime:
    """Frühester physischer Zeitpunkt, den das Slot-Fenster braucht.

    Backward: Slot 0 des ersten Tages ist das Intervall ``[Vortag 23:00, 00:00)``.
    Abfragen müssen also eine Stunde vor Mitternacht beginnen, sonst bliebe
    Slot 0 des ersten Tages leer.
    """
    return datetime.combine(start_tag, datetime.min.time()) - timedelta(hours=1)


def _slot_fenster(
    start_tag: date, tage: int = TAGE_FENSTER
) -> Iterator[tuple[datetime, datetime, date, int]]:
    """Physische Stundenintervalle → Backward-Slots (#144, #297).

    **Die einzige Stelle im Modul, die Energie einer Stunde zuordnet.** Die
    Zuordnung kommt aus ``backward_slot_aus_period_start`` (SoT
    ``core/berechnungen/slot_konvention.py``) — nicht aus einer eigenen
    Rechnung. Wer hier oder in einem Aufrufer ``h + 1`` schreibt, baut die
    nächste Fundstelle derselben Klasse (#297, `b8d6f2f2`, N-43).

    Liefert ``tage × 24`` Slots von ``(start_tag, 0)`` bis
    ``(start_tag + tage - 1, 23)``, je als
    ``(h_start, h_end, slot_datum, slot_stunde)`` mit dem physischen Intervall
    ``[h_start, h_end)``, das in diesen Slot gehört.
    """
    fenster_start = _fenster_start(start_tag)
    for i in range(tage * 24):
        h_start = fenster_start + timedelta(hours=i)
        h_end = h_start + timedelta(hours=1)
        slot_datum, slot_stunde = backward_slot_aus_period_start(h_start)
        yield h_start, h_end, slot_datum, slot_stunde


async def get_verbrauchsprofil(
    anlage: Anlage, db: AsyncSession, kwh_cache,
) -> Optional[dict]:
    """
    Berechnet ein individuelles stündliches Verbrauchsprofil aus den letzten
    7 vollen Tagen, getrennt nach Werktag (Mo-Fr) und Wochenende (Sa-So).

    Datenquellen (Priorität):
      1. TagesEnergieProfil (EEDC-DB)
      2. HA-History (Leistungs-Sensoren → Stundenmittel in kW)
      3. MQTT Energy Snapshots (kumulative kWh → stündliche Deltas)

    Verbrauch pro Stunde = PV + Netzbezug - Einspeisung

    Returns:
        {
            "werktag": {0: kW, 1: kW, ..., 23: kW},   # Backward-Slots: h = [h-1, h)
            "wochenende": {0: kW, 1: kW, ..., 23: kW},
            "tage_werktag": int,
            "tage_wochenende": int,
            "quelle": "ha" | "mqtt",
        }
        oder None wenn keine History verfügbar.
    """
    # Cache prüfen (unterscheidet "nicht gecacht" von "gecacht als keine Daten")
    cache = kwh_cache.get_profil(anlage.id)
    if cache is not None:
        if cache is kwh_cache.PROFIL_UNAVAILABLE:
            logger.info("Verbrauchsprofil Anlage %s: Cache-Hit (keine Daten)", anlage.id)
            return None
        logger.info(
            "Verbrauchsprofil Anlage %s: Cache-Hit (ok, quelle=%s)",
            anlage.id, cache.get("quelle"),
        )
        return cache

    # 1. Versuche EEDC-DB (TagesEnergieProfil) — lokal, kein HA-Call
    result = await _profil_from_db(anlage.id, db)
    logger.info(
        "Verbrauchsprofil Anlage %s: DB=%s",
        anlage.id,
        "None" if result is None else f"ok(wt={result.get('tage_werktag')},we={result.get('tage_wochenende')})",
    )

    # 2. Fallback: HA-History (neue Installation, noch keine DB-Daten)
    if result is None:
        result = await _profil_from_ha(anlage, db)
        logger.info(
            "Verbrauchsprofil Anlage %s: HA=%s",
            anlage.id,
            "None" if result is None else f"ok(quelle={result.get('quelle')},wt={result.get('tage_werktag')})",
        )

    # 3. Fallback: MQTT Energy Snapshots
    if result is None:
        result = await _profil_from_mqtt(anlage.id)
        logger.info(
            "Verbrauchsprofil Anlage %s: MQTT=%s",
            anlage.id,
            "None" if result is None else f"ok(wt={result.get('tage_werktag')},we={result.get('tage_wochenende')})",
        )

    # IMMER cachen — auch None, damit der teure Timeout sich nicht wiederholt
    kwh_cache.set_profil(anlage.id, result)

    return result


async def _profil_from_db(
    anlage_id: int, db: AsyncSession
) -> Optional[dict]:
    """
    Verbrauchsprofil aus TagesEnergieProfil (EEDC-DB).

    Kein HA-Call, kein Netzwerk — reine DB-Abfrage. Überlebt jeden Neustart.
    Liefert Daten ab dem Moment, wo der Scheduler täglich aggregiert hat.

    ``TagesEnergieProfil.stunde`` ist bereits ein Backward-Slot (der Aggregator
    schreibt ihn über ``lts_boundary_index``) — hier wird nichts umgerechnet.
    """
    from backend.models.tages_energie_profil import TagesEnergieProfil

    heute = date.today()
    start_date = heute - timedelta(days=TAGE_FENSTER)

    result = await db.execute(
        select(
            TagesEnergieProfil.datum,
            TagesEnergieProfil.stunde,
            TagesEnergieProfil.verbrauch_kw,
            TagesEnergieProfil.waermepumpe_kw,
            TagesEnergieProfil.temperatur_c,
        ).where(
            TagesEnergieProfil.anlage_id == anlage_id,
            TagesEnergieProfil.datum >= start_date,
            TagesEnergieProfil.datum < heute,  # Heute ausschließen (noch unvollständig)
        )
    )
    rows = result.all()

    if not rows:
        return None

    # Plausibilitätsprüfung: Erkennt falsch gespeicherte Werte (z.B. W statt kW,
    # oder kumulative Wh-Zähler). Typischer Haushalts-Peak: 0.1–20 kW.
    # Median > 100 = unplausibel → None zurückgeben, Fallback auf HA-History.
    alle_verbrauch = [r[2] for r in rows if r[2] is not None]
    if alle_verbrauch:
        sorted_v = sorted(alle_verbrauch)
        median_v = sorted_v[len(sorted_v) // 2]
        if median_v > 100:
            logger.warning(
                "Anlage %s: TagesEnergieProfil verbrauch_kw-Median %.1f > 100 kW — "
                "DB-Daten unplausibel (falsch gemappter Sensor?), Fallback auf HA-History.",
                anlage_id, median_v,
            )
            return None

    werktag_sums: dict[int, list[float]] = {h: [] for h in range(24)}
    wochenende_sums: dict[int, list[float]] = {h: [] for h in range(24)}
    wp_werktag_sums: dict[int, list[float]] = {h: [] for h in range(24)}
    wp_wochenende_sums: dict[int, list[float]] = {h: [] for h in range(24)}
    werktage_set: set[str] = set()
    wochenende_set: set[str] = set()
    temp_werte: list[float] = []
    hat_wp = False

    for datum, stunde, verbrauch_kw, waermepumpe_kw, temperatur_c in rows:
        if verbrauch_kw is None:
            continue

        ist_wochenende = datum.weekday() >= 5
        tag_str = datum.isoformat()

        if ist_wochenende:
            wochenende_sums[stunde].append(verbrauch_kw)
            wochenende_set.add(tag_str)
            if waermepumpe_kw is not None:
                wp_wochenende_sums[stunde].append(waermepumpe_kw)
                hat_wp = True
        else:
            werktag_sums[stunde].append(verbrauch_kw)
            werktage_set.add(tag_str)
            if waermepumpe_kw is not None:
                wp_werktag_sums[stunde].append(waermepumpe_kw)
                hat_wp = True

        if temperatur_c is not None:
            temp_werte.append(temperatur_c)

    referenz_temp_c = round(sum(temp_werte) / len(temp_werte), 1) if temp_werte else None

    return _build_profil_result(
        werktag_sums, wochenende_sums, werktage_set, wochenende_set, "db",
        wp_werktag_sums=wp_werktag_sums if hat_wp else None,
        wp_wochenende_sums=wp_wochenende_sums if hat_wp else None,
        referenz_temp_c=referenz_temp_c,
    )


async def _profil_from_ha(
    anlage: Anlage, db: AsyncSession
) -> Optional[dict]:
    """Verbrauchsprofil aus HA-History (Leistungs-Sensoren, kW-Mittelwerte).

    Das Stundenmittel über ``[h_start, h_end)`` landet im Backward-Slot, den
    ``_slot_fenster`` dafür nennt — dieselbe Zuordnung wie im DB-Pfad.

    Eine Stunde ohne Messpunkte am Netzanschluss liefert **keine** Stichprobe
    (N-46, s. Modul-Docstring).
    """
    if not HA_INTEGRATION_AVAILABLE:
        return None

    basis_live, inv_live_map, basis_invert, inv_invert_map = extract_live_config(anlage)

    einsp_eid = basis_live.get("einspeisung_w")
    bezug_eid = basis_live.get("netzbezug_w")
    kombi_eid = basis_live.get("netz_kombi_w")
    # Kombinierter Sensor als Fallback
    if not einsp_eid and not bezug_eid and kombi_eid:
        pass  # Kombi-Sensor wird unten behandelt
    elif not einsp_eid and not bezug_eid:
        return None

    # PV-Entity-IDs
    inv_result = await db.execute(
        select(Investition.id, Investition.typ).where(
            Investition.anlage_id == anlage.id, aktiv_jetzt()
        )
    )
    inv_types = {str(row[0]): row[1] for row in inv_result.all()}

    pv_eids: list[str] = []
    wp_eids: list[str] = []
    for inv_id, live in inv_live_map.items():
        typ = inv_types.get(inv_id)
        if typ in ERZEUGER_TYPEN and live.get("leistung_w"):
            pv_eids.append(live["leistung_w"])
        elif typ == "waermepumpe" and live.get("leistung_w"):
            wp_eids.append(live["leistung_w"])

    # PV Gesamt aus Basis als Fallback
    if not pv_eids and basis_live.get("pv_gesamt_w"):
        pv_eids.append(basis_live["pv_gesamt_w"])

    temp_eid = basis_live.get("aussentemperatur_c")

    now = datetime.now()
    start_tag = now.date() - timedelta(days=TAGE_FENSTER)

    all_ids = list(set(filter(None, [einsp_eid, bezug_eid, kombi_eid] + pv_eids + wp_eids + ([temp_eid] if temp_eid else []))))
    history, _ = await get_history_normalized(all_ids, _fenster_start(start_tag), now)

    # Vorzeichen-Invertierung auf History anwenden (#58)
    apply_invert_to_history(
        history, basis_live, basis_invert, inv_live_map, inv_invert_map
    )

    if not history:
        return None

    # ── Beleg dafür, dass eine Stunde überhaupt beobachtet wurde (N-46) ──
    #
    # Genommen werden die Netz-Sensoren: ohne sie ist „Verbrauch" gar nicht
    # bestimmbar, und sie belegen, dass der Recorder in dieser Stunde lief.
    # PV- und WP-Sensoren taugen nicht als Beleg — sie melden nachts bzw. im
    # Stillstand stundenlang keine Zustandsänderung, obwohl nichts fehlt.
    # Umgekehrt ist ``any`` statt ``all`` richtig: nachts steht der
    # Einspeise-Sensor konstant auf 0 (keine Zustandsänderung), mittags der
    # Bezugs-Sensor — einer von beiden bewegt sich immer.
    nutzt_kombi = bool(kombi_eid and not bezug_eid and not einsp_eid)
    netz_eids = [kombi_eid] if nutzt_kombi else [e for e in (bezug_eid, einsp_eid) if e]
    beleg_eids = [eid for eid in netz_eids if history.get(eid)]
    if not beleg_eids:
        logger.info(
            "Verbrauchsprofil Anlage %s: kein Netz-Sensor mit History im Fenster — "
            "ohne Netzmessung gäbe es nur die PV-Kurve als vermeintlichen Verbrauch.",
            anlage.id,
        )
        return None

    werktag_sums: dict[int, list[float]] = {h: [] for h in range(24)}
    wochenende_sums: dict[int, list[float]] = {h: [] for h in range(24)}
    wp_werktag_sums: dict[int, list[float]] = {h: [] for h in range(24)}
    wp_wochenende_sums: dict[int, list[float]] = {h: [] for h in range(24)}
    werktage_set: set[str] = set()
    wochenende_set: set[str] = set()
    temp_werte: list[float] = []
    unbeobachtet = 0

    for h_start, h_end, slot_datum, h in _slot_fenster(start_tag):
        if h_end > now:
            break

        if not any(
            any(h_start <= ts < h_end for ts, _ in history.get(eid, ()))
            for eid in beleg_eids
        ):
            unbeobachtet += 1
            continue  # nicht beobachtet ⇒ keine Stichprobe (N-46)

        tag_str = slot_datum.isoformat()
        ist_wochenende = slot_datum.weekday() >= 5

        pv_kw = 0.0
        for eid in pv_eids:
            pts = history.get(eid, [])
            h_pts = [p[1] for p in pts if h_start <= p[0] < h_end]
            if h_pts:
                pv_kw += sum(h_pts) / len(h_pts) / 1000

        bezug_kw = 0.0
        einsp_kw = 0.0
        if kombi_eid and not bezug_eid and not einsp_eid:
            pts = history.get(kombi_eid, [])
            h_pts = [p[1] for p in pts if h_start <= p[0] < h_end]
            if h_pts:
                avg_w = sum(h_pts) / len(h_pts)
                if avg_w >= 0:
                    bezug_kw = avg_w / 1000
                else:
                    einsp_kw = abs(avg_w) / 1000
        else:
            if bezug_eid:
                pts = history.get(bezug_eid, [])
                h_pts = [p[1] for p in pts if h_start <= p[0] < h_end]
                if h_pts:
                    bezug_kw = sum(h_pts) / len(h_pts) / 1000

            if einsp_eid:
                pts = history.get(einsp_eid, [])
                h_pts = [p[1] for p in pts if h_start <= p[0] < h_end]
                if h_pts:
                    einsp_kw = sum(h_pts) / len(h_pts) / 1000

        verbrauch_kw = max(0, pv_kw + bezug_kw - einsp_kw)

        wp_kw = 0.0
        for eid in wp_eids:
            pts = history.get(eid, [])
            h_pts = [p[1] for p in pts if h_start <= p[0] < h_end]
            if h_pts:
                wp_kw += abs(sum(h_pts) / len(h_pts)) / 1000

        if temp_eid:
            pts = history.get(temp_eid, [])
            h_pts = [p[1] for p in pts if h_start <= p[0] < h_end]
            if h_pts:
                temp_werte.append(sum(h_pts) / len(h_pts))

        if ist_wochenende:
            wochenende_sums[h].append(verbrauch_kw)
            wp_wochenende_sums[h].append(wp_kw)
            wochenende_set.add(tag_str)
        else:
            werktag_sums[h].append(verbrauch_kw)
            wp_werktag_sums[h].append(wp_kw)
            werktage_set.add(tag_str)

    if unbeobachtet:
        logger.info(
            "Verbrauchsprofil Anlage %s: %d von %d Stunden ohne Netz-History — "
            "ausgelassen statt als 0 kW gezählt.",
            anlage.id, unbeobachtet, TAGE_FENSTER * 24,
        )

    referenz_temp_c = round(sum(temp_werte) / len(temp_werte), 1) if temp_werte else None

    return _build_profil_result(
        werktag_sums, wochenende_sums, werktage_set, wochenende_set, "ha",
        wp_werktag_sums=wp_werktag_sums if wp_eids else None,
        wp_wochenende_sums=wp_wochenende_sums if wp_eids else None,
        referenz_temp_c=referenz_temp_c,
    )


def _rand_stand(
    zeiten: list[datetime], staende: list[float], grenze: datetime
) -> Optional[float]:
    """Zählerstand an einer Stundengrenze — oder ``None``, wenn keiner vorliegt.

    Genommen wird der letzte Stand **bei oder vor** ``grenze``. Zwei
    aufeinanderfolgende Stunden greifen damit auf denselben Randwert zu: an der
    Grenze geht weder Energie verloren noch wird welche doppelt gezählt, die
    Tagessumme bleibt erhalten. Liegt der letzte Stand weiter als
    ``RAND_TOLERANZ`` zurück, wurde an dieser Grenze nicht gemessen.
    """
    i = bisect_right(zeiten, grenze) - 1
    if i < 0 or grenze - zeiten[i] > RAND_TOLERANZ:
        return None
    return staende[i]


def _stunden_zuwaechse(
    reihen: dict[str, tuple[list[datetime], list[float]]],
    h_start: datetime,
    h_end: datetime,
) -> Optional[dict[str, float]]:
    """Zuwachs jedes Zählers über ``[h_start, h_end)`` — oder ``None``.

    ``None`` heißt: mindestens ein Zähler hat an einer der beiden
    Intervallgrenzen keinen Stand. Die Stunde ist dann **unvollständig** und
    liefert keine Stichprobe, statt zu niedrig zu zählen (N-45).

    Bis v4.0.5 wurde stattdessen der Zuwachs zwischen dem ersten und dem letzten
    Snapshot *innerhalb* der Stunde gebildet — das letzte Snapshot-Intervall fiel
    dabei jede Stunde heraus, bei 5-Minuten-Takt rund 8 % zu wenig.
    """
    zuwaechse: dict[str, float] = {}
    for key, (zeiten, staende) in reihen.items():
        v_start = _rand_stand(zeiten, staende, h_start)
        v_end = _rand_stand(zeiten, staende, h_end)
        if v_start is None or v_end is None:
            return None
        # Negatives Delta = Counter-Reset → als 0 werten (unverändert seit v3)
        zuwaechse[key] = max(0.0, v_end - v_start)
    return zuwaechse


async def _profil_from_mqtt(anlage_id: int) -> Optional[dict]:
    """
    Verbrauchsprofil aus MQTT Energy Snapshots (kumulative kWh → stündliche Deltas).

    Die Snapshots enthalten kumulative Monatswerte (pv_gesamt_kwh, einspeisung_kwh,
    netzbezug_kwh) alle 5 Minuten. Für jede Stunde berechnen wir das Delta und
    daraus den durchschnittlichen Verbrauch in kW (= kWh/h).

    Das Delta über ``[h_start, h_end)`` landet im Backward-Slot, den
    ``_slot_fenster`` dafür nennt — dieselbe Zuordnung wie im DB-Pfad. Gemessen
    wird über die **Intervallgrenzen** (``_stunden_zuwaechse``), nicht über die
    zufällig darin liegenden Snapshots; fehlt ein Randwert, liefert die Stunde
    keine Stichprobe (N-45).
    """
    from backend.core.database import get_session
    from backend.models.mqtt_energy_snapshot import MqttEnergySnapshot

    now = datetime.now()
    start_tag = now.date() - timedelta(days=TAGE_FENSTER)
    start = _fenster_start(start_tag)

    # Alle Snapshots der letzten 7 Tage laden. Die Toleranz gehört mit ins
    # Fenster: der Randwert der allerersten Stundengrenze liegt davor, sonst
    # fiele diese Stunde ohne Grund als unvollständig heraus.
    async with get_session() as session:
        result = await session.execute(
            select(
                MqttEnergySnapshot.timestamp,
                MqttEnergySnapshot.energy_key,
                MqttEnergySnapshot.value_kwh,
            ).where(
                MqttEnergySnapshot.anlage_id == anlage_id,
                MqttEnergySnapshot.timestamp >= start - RAND_TOLERANZ,
            ).order_by(MqttEnergySnapshot.timestamp)
        )
        rows = result.all()

    if not rows:
        return None

    # Relevante Keys
    pv_key = "pv_gesamt_kwh"
    einsp_key = "einspeisung_kwh"
    bezug_key = "netzbezug_kwh"

    # Je Zähler eine eigene Zeitreihe. Die Keys treffen nicht zwingend im selben
    # Snapshot-Zeitpunkt ein, und der Randwert wird je Zähler gesucht — eine
    # gemeinsame Zeitachse würde einen Zähler an der Grenze des anderen ablesen.
    # `rows` kommt bereits nach timestamp sortiert (ORDER BY), das braucht
    # `_rand_stand` für die Binärsuche.
    reihen: dict[str, tuple[list[datetime], list[float]]] = {}
    for ts, key, val in rows:
        if key not in (pv_key, einsp_key, bezug_key):
            continue
        zeiten, staende = reihen.setdefault(key, ([], []))
        zeiten.append(ts)
        staende.append(val)

    if not reihen:
        return None

    werktag_sums: dict[int, list[float]] = {h: [] for h in range(24)}
    wochenende_sums: dict[int, list[float]] = {h: [] for h in range(24)}
    werktage_set: set[str] = set()
    wochenende_set: set[str] = set()
    unvollstaendig = 0

    for h_start, h_end, slot_datum, h in _slot_fenster(start_tag):
        if h_end > now:
            break

        zuwaechse = _stunden_zuwaechse(reihen, h_start, h_end)
        if zuwaechse is None:
            unvollstaendig += 1
            continue  # Randwert fehlt ⇒ keine Stichprobe (N-45)

        tag_str = slot_datum.isoformat()
        ist_wochenende = slot_datum.weekday() >= 5

        # Verbrauch in kWh für diese Stunde, ≈ kW (da 1h Intervall)
        verbrauch_kw = max(
            0.0,
            zuwaechse.get(pv_key, 0.0)
            + zuwaechse.get(bezug_key, 0.0)
            - zuwaechse.get(einsp_key, 0.0),
        )

        if ist_wochenende:
            wochenende_sums[h].append(verbrauch_kw)
            wochenende_set.add(tag_str)
        else:
            werktag_sums[h].append(verbrauch_kw)
            werktage_set.add(tag_str)

    if unvollstaendig:
        logger.info(
            "Verbrauchsprofil Anlage %s: %d von %d Stunden ohne Zählerstand an der "
            "Intervallgrenze — ausgelassen statt zu niedrig gezählt.",
            anlage_id, unvollstaendig, TAGE_FENSTER * 24,
        )

    return _build_profil_result(
        werktag_sums, wochenende_sums, werktage_set, wochenende_set, "mqtt"
    )


def _build_profil_result(
    werktag_sums: dict[int, list[float]],
    wochenende_sums: dict[int, list[float]],
    werktage_set: set[str],
    wochenende_set: set[str],
    quelle: str,
    wp_werktag_sums: Optional[dict[int, list[float]]] = None,
    wp_wochenende_sums: Optional[dict[int, list[float]]] = None,
    referenz_temp_c: Optional[float] = None,
) -> Optional[dict]:
    """Baut das Profil-Ergebnis aus den gesammelten Stundenwerten."""
    tage_wt = len(werktage_set)
    tage_we = len(wochenende_set)

    if tage_wt < 2 and tage_we < 2:
        return None

    def avg(values: list[float]) -> float:
        return round(sum(values) / len(values), 3) if values else 0.0

    # Nur Stunden mit echten Daten aufnehmen (keine 0.0 für fehlende History)
    def build_profil(sums: dict[int, list[float]]) -> dict[int, float]:
        return {h: avg(sums[h]) for h in range(24) if sums[h]}

    result: dict = {
        "werktag": build_profil(werktag_sums) if tage_wt >= 2 else None,
        "wochenende": build_profil(wochenende_sums) if tage_we >= 2 else None,
        "tage_werktag": tage_wt,
        "tage_wochenende": tage_we,
        "quelle": quelle,
    }

    if wp_werktag_sums is not None:
        result["wp_werktag"] = build_profil(wp_werktag_sums) if tage_wt >= 2 else None
        result["wp_wochenende"] = build_profil(wp_wochenende_sums) if tage_we >= 2 else None

    if referenz_temp_c is not None:
        result["referenz_temp_c"] = referenz_temp_c

    return result
