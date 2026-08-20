"""
Geteilte Helper für das Energie-Profil-Subsystem.

Wetter-IST (Open-Meteo Historical/Forecast/Archive), SoC-History (HA-Sensor),
Strompreis-Stunden (HA-Sensor + aWATTar-Börsenpreis) und der `_tage_zurueck`-
Wrapper für `get_tagesverlauf`. Diese Funktionen werden lazy aus `aggregator.py`
und `backfill.py` importiert; sie haben keinen eigenen Schreib-Pfad.

Extrahiert aus `services/energie_profil_service.py` im 3d-Etappenabschluss-Tail
(2026-05-10). Verhalten unverändert.
"""

import logging
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.anlage import Anlage

logger = logging.getLogger(__name__)


def _tage_zurueck(datum: date) -> int:
    """Berechnet tage_zurueck Parameter für get_tagesverlauf()."""
    return (date.today() - datum).days


async def _get_wetter_ist(
    anlage: Anlage,
    datum: date,
    pv_module: Optional[list] = None,
) -> dict:
    """
    Holt Wetter-IST-Daten für einen Tag (Open-Meteo Historical).

    Zusätzlich zur horizontalen Globalstrahlung (GHI) wird — wenn PV-Module
    mit bekannter Neigung/Ausrichtung übergeben werden — die Global Tilted
    Irradiance (GTI) kWp-gewichtet über alle Orientierungsgruppen geholt.
    GTI ist die auf die Modul-Fläche projizierte Strahlung und die physikalisch
    korrekte Referenz für die Performance-Ratio-Berechnung (Issue #139).

    Args:
        anlage: Anlage-Objekt mit lat/lon
        datum: Zieltag
        pv_module: Liste von PV-Module-Investitionen (für GTI-Gruppierung).
            None/leer → nur GHI (PR bleibt dann None in der Aggregation).

    Returns:
        {stunde: {
            "temperatur_c": float,
            "globalstrahlung_wm2": float,   # horizontal, GHI
            "gti_wm2": float | None,        # modul-gewichtet, None wenn keine PV-Module
            "bewoelkung_prozent": float,    # cloud_cover 0-100
            "niederschlag_mm": float,       # precipitation in mm/h
            "wetter_code": int,             # WMO weather code
        }}
    """
    if not anlage.latitude or not anlage.longitude:
        return {}

    try:
        import asyncio
        import httpx
        from backend.core.config import settings
        from backend.api.routes.live_wetter import _get_pv_orientierungsgruppen

        gruppen = _get_pv_orientierungsgruppen(pv_module) if pv_module else []

        # Forecast-Endpoint für heute UND die letzten ARCHIVE_LAG_TAGE
        # (Open-Meteo Archive hängt 2-5 Tage hinter Echtzeit; Forecast-Endpoint
        # liefert für vergangene Tage stattdessen die Reanalyse-Approximation).
        # Archive nur für ältere Tage.
        from backend.services.wetter_backfill_service import archive_cutoff
        if datum == date.today():
            url = f"{settings.open_meteo_api_url}/forecast"
            base_params: dict = {"forecast_days": 1}
        elif datum >= archive_cutoff():
            url = f"{settings.open_meteo_api_url}/forecast"
            base_params = {
                "start_date": datum.isoformat(),
                "end_date": datum.isoformat(),
            }
        else:
            url = "https://archive-api.open-meteo.com/v1/archive"
            base_params = {
                "start_date": datum.isoformat(),
                "end_date": datum.isoformat(),
            }

        base_params.update({
            "latitude": anlage.latitude,
            "longitude": anlage.longitude,
            "timezone": "Europe/Berlin",
        })

        # Haupt-Request: Temperatur + GHI + Wetter (Bewölkung, Niederschlag, WMO-Code),
        # bei genau einer Gruppe auch GTI
        haupt_params = dict(base_params)
        hourly_vars = [
            "temperature_2m", "shortwave_radiation",
            "cloud_cover", "precipitation", "weather_code",
        ]
        if len(gruppen) == 1:
            hourly_vars.append("global_tilted_irradiance")
            haupt_params["tilt"] = gruppen[0]["neigung"]
            haupt_params["azimuth"] = gruppen[0]["ausrichtung"]
        haupt_params["hourly"] = ",".join(hourly_vars)

        multi_gti: Optional[list[float]] = None
        async with httpx.AsyncClient(timeout=15.0) as client:
            if len(gruppen) > 1:
                # Separate GTI-Calls pro Gruppe, parallel
                gti_tasks = [
                    client.get(url, params={
                        **base_params,
                        "hourly": "global_tilted_irradiance",
                        "tilt": g["neigung"],
                        "azimuth": g["ausrichtung"],
                    })
                    for g in gruppen
                ]
                haupt_resp, *gti_resps = await asyncio.gather(
                    client.get(url, params=haupt_params),
                    *gti_tasks,
                )
                # kWp-gewichtete Kombination
                kwp_gesamt = sum(g["kwp"] for g in gruppen)
                multi_gti = [0.0] * 24
                for gruppe, resp in zip(gruppen, gti_resps):
                    try:
                        resp.raise_for_status()
                        gti_vals = resp.json().get("hourly", {}).get("global_tilted_irradiance", [])
                    except Exception:
                        continue
                    if not gti_vals or kwp_gesamt <= 0:
                        continue
                    gewicht = gruppe["kwp"] / kwp_gesamt
                    for i in range(min(24, len(gti_vals))):
                        v = gti_vals[i]
                        if v is not None:
                            multi_gti[i] += v * gewicht
            else:
                haupt_resp = await client.get(url, params=haupt_params)

        haupt_resp.raise_for_status()
        data = haupt_resp.json()

        hourly = data.get("hourly", {})
        times = hourly.get("time", [])
        temps = hourly.get("temperature_2m", [])
        ghi = hourly.get("shortwave_radiation", [])
        gti_single = hourly.get("global_tilted_irradiance", [])
        cloud_cover = hourly.get("cloud_cover", [])
        precip = hourly.get("precipitation", [])
        wcode = hourly.get("weather_code", [])

        gti_values = multi_gti if multi_gti is not None else gti_single

        result = {}
        for i, t in enumerate(times):
            h = int(t[11:13])
            result[h] = {
                "temperatur_c": temps[i] if i < len(temps) else None,
                "globalstrahlung_wm2": ghi[i] if i < len(ghi) else None,
                "gti_wm2": gti_values[i] if i < len(gti_values) else None,
                "bewoelkung_prozent": cloud_cover[i] if i < len(cloud_cover) else None,
                "niederschlag_mm": precip[i] if i < len(precip) else None,
                "wetter_code": wcode[i] if i < len(wcode) else None,
            }

        return result

    except Exception as e:
        logger.debug(f"Wetter-IST für {datum}: {e}")
        return {}


async def _get_soc_history(
    anlage: Anlage,
    sensor_mapping: dict,
    datum: date,
    db: AsyncSession,
) -> dict:
    """
    Holt Batterie-SoC History für einen Tag — nur stationäre Speicher.

    E-Auto-SoC darf hier NICHT enthalten sein, sonst kontaminiert er die
    Batterie-Vollzyklen-Berechnung der PV-Anlage (E-Auto-ΔSoC ≠ Speicher-ΔSoC).

    Etappe 5 (v3.31.0): bevorzugt HA-LTS-Hourly-Mean direkt aus
    `statistics.mean` — dieselbe Quelle, aus der HA das Energy-Dashboard
    speist. State-History-Mittelung nur als Fallback wenn LTS leer (frischer
    Sensor, has_mean=False, oder Tag liegt vor LTS-Recompile).

    ⚑ **N-239 (2026-08-12): jedes Gerät zählt, nicht nur das erste.** Bis dahin
    nahmen beide Pfade den **ersten** gemappten SoC-Sensor mit Daten und brachen
    ab (`return` im LTS-Pfad, `break  # Erstes SoC-Entity reicht` im
    History-Pfad). Bei zwei Speichern trug `TagesEnergieProfil.soc_prozent`
    damit den Ladestand *eines* Geräts — welches, entschied die Reihenfolge im
    Sensor-Mapping —, während fünf Stellen im Baum „anlagenweiter Mischwert"
    behaupteten. Darauf laufen Vollzyklen, SoC-Hübe, die Potential-Heatmap und
    die Sizing-Kalibrierung.

    Returns:
        ``{stunde: {investition_id: soc_prozent}}``. Der Aufrufer bildet daraus
        den Anlagenwert über `core.berechnungen.speicher.anlagen_soc_prozent`
        (kapazitätsgewichtet) und persistiert die Aufschlüsselung daneben. Bei
        genau einem Speicher — dem Normalfall — ist das Ergebnis wertgleich mit
        dem bisherigen Verhalten.
    """
    from backend.models.investition import Investition

    # F-26: kein Gate auf `HA_INTEGRATION_AVAILABLE` (= SUPERVISOR_TOKEN) mehr.
    # Beide Quellen darunter — `ha_statistics_service` und `ha_state_service` —
    # prüfen ihre Erreichbarkeit selbst und können seit dem 05.08. auch die
    # Remote-Verbindung per Long-Lived-Token. Das Gate hier übersprang sie im
    # Docker-Betrieb, obwohl HA erreichbar war: der Speicher-SoC fehlte, und
    # damit die Vollzyklen des Tages.

    # Speicher-IDs für diese Anlage holen, dann SoC-Entities filtern
    inv_result = await db.execute(
        select(Investition.id).where(
            Investition.anlage_id == anlage.id,
            Investition.typ == "speicher",
        )
    )
    speicher_ids = {str(row) for row in inv_result.scalars().all()}

    if not speicher_ids:
        return {}

    # Entity → Investitions-ID, damit die Aufschlüsselung ihr Gerät kennt.
    # Mehrere Speicher dürfen denselben Sensor tragen (ein BMS über zwei
    # Module); dann steht derselbe Wert bei beiden, und die Gewichtung darunter
    # ist trotzdem richtig.
    entity_zu_inv: dict[str, list[int]] = {}
    for key, val in sensor_mapping.get("investitionen", {}).items():
        if str(key) not in speicher_ids:
            continue
        if isinstance(val, dict) and val.get("live", {}).get("soc"):
            entity_zu_inv.setdefault(val["live"]["soc"], []).append(int(key))

    soc_entities = list(entity_zu_inv)
    if not soc_entities:
        return {}

    def _eintragen(ziel: dict, entity_id: str, stunde: int, wert: float) -> None:
        for inv_id in entity_zu_inv[entity_id]:
            ziel.setdefault(stunde, {})[inv_id] = float(wert)

    # ── Pfad 1: HA-LTS-Hourly-Mean (Etappe 5) ────────────────────────────
    try:
        import asyncio
        from backend.services.ha_statistics_service import get_ha_statistics_service

        stats = get_ha_statistics_service()
        if stats.is_available:
            datum_iso = datum.isoformat()
            hourly = await asyncio.to_thread(
                stats.get_hourly_sensor_data, soc_entities, datum, datum
            )
            ergebnis: dict = {}
            for entity_id in soc_entities:
                slots = hourly.get(entity_id, {}).get(datum_iso, {})
                for h, v in slots.items():
                    _eintragen(ergebnis, entity_id, int(h), v)
            # Nur wenn der LTS-Pfad wirklich etwas geliefert hat — sonst greift
            # der History-Fallback, wie bisher.
            if ergebnis:
                return ergebnis
    except Exception as e:
        logger.debug(f"SoC-LTS-Hourly für {datum}: {e}")

    # ── Pfad 2: Fallback auf State-History-Mittelung ─────────────────────
    try:
        from backend.services.ha_state_service import get_ha_state_service
        ha_service = get_ha_state_service()

        start = datetime.combine(datum, datetime.min.time())
        end = start + timedelta(days=1)

        history = await ha_service.get_sensor_history(soc_entities, start, end)

        result: dict = {}
        for entity_id in soc_entities:
            points = history.get(entity_id, [])
            if not points:
                continue

            for h in range(24):
                h_start = start + timedelta(hours=h)
                h_end = h_start + timedelta(hours=1)
                h_points = [p[1] for p in points if h_start <= p[0] < h_end]
                if h_points:
                    _eintragen(result, entity_id, h, sum(h_points) / len(h_points))

        return result

    except Exception as e:
        logger.debug(f"SoC-History für {datum}: {e}")
        return {}


async def _get_betriebsmodus_history(
    anlage: Anlage,
    sensor_mapping: dict,
    datum: date,
    db: AsyncSession,
) -> dict:
    """Holt den Betriebsmodus je Wärmepumpe und Stunde für einen Tag (#263 K-2).

    Schwester von `_get_soc_history` — **mit einem bewussten Unterschied, der
    der ganze Punkt ist**: Ein SoC ist ein Messwert, über eine Stunde wird
    gemittelt. Ein Betriebsmodus ist ein **Zustand**, und ein Zustand hat eine
    **Dauer**. Über eine Stunde gewinnt deshalb der Modus mit der längsten
    Verweildauer, nicht der Mittelwert (den es nicht gibt) und auch nicht der
    letzte Wert: Wer um 07:58 von Heizen auf Aus stellt, hat diese Stunde
    geheizt, nicht gestanden.

    ⚑ **Und die Fortschreibung gehört dazu.** Home Assistant schreibt einen
    State nur bei **Änderung**. Eine Klimaanlage, die den ganzen Winter auf
    „Heizen" steht, liefert im Januar genau einen Punkt — alle übrigen 743
    Stunden hätten ohne Fortschreibung kein Signal. Der letzte Punkt **vor**
    der Stunde trägt deshalb fort. Nur wenn es auch keinen Vorgänger gibt,
    bleibt die Stunde leer.

    ⚠ **Leer heißt leer, nicht `unbestimmt`.** Eine Stunde ohne Eintrag heißt
    „eedc hat nicht hingesehen"; `unbestimmt` heißt „hingesehen, Seite nicht
    zuordenbar" (Automatik ohne Ist-Signal, Konzept D1/D2). Genau diese zwei
    Fälle muss der Anwender später unterscheiden können — sie ineinander zu
    übersetzen wäre eine erfundene Aussage über die Datenlage (ADR-002/P4).

    ⚠ **Nur ein Pfad, anders als beim SoC.** `_get_soc_history` versucht zuerst
    HA-Long-Term-Statistics und fällt auf die State-History zurück. Für einen
    Zustand gibt es keine LTS: sie existiert nur für numerische Sensoren mit
    `state_class`, und ein `climate`-Zustand hat keine (Konzept D9). Damit
    greift auch die recorder-Purge — es gibt **kein Backfill**, die Aufteilung
    beginnt mit der Zuordnung.

    Returns:
        ``{stunde: {investition_id: modus}}`` mit Kanon-Werten aus
        `core.betriebsmodus`. Stunden ohne Signal fehlen; Geräte ohne
        zugeordneten Sensor fehlen.
    """
    from backend.core.betriebsmodus import normalisiere_betriebsmodus
    from backend.models.investition import Investition

    inv_result = await db.execute(
        select(Investition.id).where(
            Investition.anlage_id == anlage.id,
            Investition.typ == "waermepumpe",
        )
    )
    wp_ids = {str(row) for row in inv_result.scalars().all()}
    if not wp_ids:
        return {}

    # Entity → Investitions-IDs. Mehrere Innengeräte dürfen dieselbe
    # `climate`-Entität tragen: der Modus gehört dem Außengerät, nicht dem
    # Innengerät (Konzept D3 — ein Innengerät auf „Heizen" bei kühlenden
    # anderen tut in einer 2-Rohr-Anlage nichts). Dann steht derselbe Modus bei
    # beiden, und das ist richtig.
    entity_zu_inv: dict[str, list[int]] = {}
    for key, val in (sensor_mapping or {}).get("investitionen", {}).items():
        if str(key) not in wp_ids:
            continue
        if isinstance(val, dict) and (val.get("live") or {}).get("betriebsmodus"):
            entity_zu_inv.setdefault(val["live"]["betriebsmodus"], []).append(int(key))

    modus_entities = list(entity_zu_inv)
    if not modus_entities:
        return {}

    try:
        from backend.services.ha_state_service import get_ha_state_service
        ha_service = get_ha_state_service()

        start = datetime.combine(datum, datetime.min.time())
        end = start + timedelta(days=1)

        # Einen Tag Vorlauf: der letzte Punkt VOR Mitternacht ist der Zustand,
        # in dem der Tag beginnt. Ohne ihn stünde jede Anlage, die ihren Modus
        # seit Wochen nicht geändert hat, jeden Tag bis zur ersten Änderung
        # ohne Signal da — bei saisonal gestelltem Modus (D11) also fast immer.
        history = await ha_service.get_zustand_history(
            modus_entities, start - timedelta(days=1), end
        )

        ergebnis: dict = {}
        for entity_id in modus_entities:
            punkte = history.get(entity_id, [])
            if not punkte:
                continue

            for h in range(24):
                h_start = start + timedelta(hours=h)
                h_end = h_start + timedelta(hours=1)

                # Zustand zu Beginn der Stunde = letzter Punkt davor.
                # ⚠ Zustand UND Aktion wandern als Paar mit: `hvac_action` ist
                # der Ist-Betrieb und schlägt den eingestellten Modus — aber
                # nur, wenn sie `normalisiere_betriebsmodus` als **zweites**
                # Argument erreicht. Wer sie vorher in den Zustand faltet,
                # verliert sie (s. `get_zustand_history`).
                laufend: Optional[tuple[str, Optional[str]]] = None
                for ts, roh, akt in punkte:
                    if ts < h_start:
                        laufend = (roh, akt)
                    else:
                        break

                in_stunde = [
                    (ts, roh, akt) for ts, roh, akt in punkte if h_start <= ts < h_end
                ]
                if laufend is None and not in_stunde:
                    continue   # weder Vorgänger noch Punkt: nicht hingesehen.

                # Verweildauer je Kanon-Modus aufsummieren. Die Intervalle
                # laufen jeweils bis zum nächsten Wechsel, das letzte bis zum
                # Stundenende.
                dauer: dict[str, float] = {}
                cursor = h_start
                aktuell = laufend
                for ts, roh, akt in in_stunde:
                    modus = normalisiere_betriebsmodus(*aktuell) if aktuell else None
                    if modus is not None:
                        dauer[modus] = dauer.get(modus, 0.0) + (ts - cursor).total_seconds()
                    cursor, aktuell = ts, (roh, akt)
                modus = normalisiere_betriebsmodus(*aktuell) if aktuell else None
                if modus is not None:
                    dauer[modus] = dauer.get(modus, 0.0) + (h_end - cursor).total_seconds()

                if not dauer:
                    continue
                # Längste Verweildauer gewinnt; bei Gleichstand entscheidet die
                # Kanon-Reihenfolge, damit dieselbe Stunde nicht je nach
                # Dict-Laufrichtung anders ausfällt.
                gewinner = max(dauer.items(), key=lambda kv: (kv[1], -_KANON_RANG(kv[0])))[0]
                for inv_id in entity_zu_inv[entity_id]:
                    ergebnis.setdefault(h, {})[inv_id] = gewinner

        return ergebnis

    except Exception as e:
        logger.debug(f"Betriebsmodus-History für {datum}: {e}")
        return {}


def _KANON_RANG(modus: str) -> int:
    """Stabile Reihenfolge für den Gleichstand-Fall in `_get_betriebsmodus_history`.

    Ohne sie entschiede die Einfügereihenfolge des Dicts, welcher von zwei
    exakt gleich langen Modi gewinnt — dieselbe Stunde könnte je nach Abrufzeit
    anders ausfallen. Ein seltener Fall, aber ein stiller.
    """
    from backend.core.betriebsmodus import BETRIEBSMODUS_KANON
    try:
        return BETRIEBSMODUS_KANON.index(modus)
    except ValueError:
        return len(BETRIEBSMODUS_KANON)


@dataclass
class StrompreisStunden:
    """Stündliche Strompreise aus zwei unabhängigen Quellen."""
    sensor: dict[int, float]   # Endpreis aus HA-Sensor (Tibber etc.), leer wenn kein Sensor
    boerse: dict[int, float]   # EPEX Day-Ahead Börsenpreis (aWATTar), immer befüllt


def _strompreis_faktor(unit: Optional[str]) -> float:
    """Faktor von Sensor-Einheit nach cent/kWh."""
    if unit in ("EUR/kWh", "€/kWh"):
        return 100.0
    if unit in ("EUR/MWh", "€/MWh"):
        return 0.1
    return 1.0


@dataclass
class TagesPeaks:
    """Tages-Peak-Werte aus HA-LTS-Min/Max pro Stunde (Etappe 5).

    Werte sind kW. None heißt: kein Peak ermittelbar (Sensor fehlt, keine
    HA-LTS-Daten, oder Aufrufer-Fallback soll greifen).
    """
    pv: Optional[float]
    netzbezug: Optional[float]
    einspeisung: Optional[float]


async def _get_tagespeaks_aus_ha_lts(
    anlage: Anlage,
    datum: date,
    db: AsyncSession,
) -> TagesPeaks:
    """
    Etappe 5 (v3.31.0): Tages-Peak-Werte für PV / Netzbezug / Einspeisung
    aus HA-LTS-Min/Max pro Stunde (`statistics.min`/`statistics.max`).

    HA-Recorder schreibt für `has_mean=True`-Sensoren je Stunde die im
    State-Bucket beobachteten Extremwerte. Das ist die richtige Quelle für
    Tages-Peak-Leistungen — eedc muss sie nicht aus 10-Min-Mittelwerten
    rekonstruieren (siehe `docs/archive/KONZEPT-ETAPPE-4-HA-LTS-SOT.md`).

    Aggregation:
      - peak_pv: max über Stunden von Σ max(pv_sensor[h]) für alle PV-Entities.
        Bei mehreren PV-Sensoren ist Σ_max eine obere Schranke (Einzelpeaks
        können unterschiedliche Minuten innerhalb der Stunde treffen) — in der
        Praxis weichen Module gleicher Anlage minutengenau wenig ab.
      - peak_einspeisung / peak_netzbezug: aus dedizierten Sensoren
        (`einspeisung_w` / `netzbezug_w`) oder dem Kombi-Sensor
        (`netz_kombi_w`): negativer Teil = Einspeisung, positiver = Bezug.
      - `live_invert`-Flags werden angewendet (min↔max getauscht + Vorzeichen).

    Returns:
        TagesPeaks; jeder Wert None wenn nicht ermittelbar (Caller-Fallback
        greift dann auf den Tagesverlauf-Pfad).
    """
    # F-26: wie `_get_soc_history` — die LTS-Abfrage unten prüft `is_available`
    # selbst und deckt Supervisor wie Long-Lived-Token ab. Mit dem alten Gate
    # blieben die Tages-Spitzenwerte im Docker-Betrieb leer, obwohl HA sie hatte.

    from backend.models.investition import Investition
    from backend.services.live_sensor_config import extract_live_config

    basis_live, inv_live_map, basis_invert, inv_invert_map = extract_live_config(anlage)

    # ── PV-Entities ermitteln ─────────────────────────────────────────────
    pv_entities: set[str] = set()
    inv_result = await db.execute(
        select(Investition.id, Investition.typ).where(Investition.anlage_id == anlage.id)
    )
    pv_typ = {"pv-module", "balkonkraftwerk"}
    for inv_id, typ in inv_result.all():
        if typ in pv_typ:
            live = inv_live_map.get(str(inv_id), {})
            eid = live.get("leistung_w")
            if eid:
                pv_entities.add(eid)

    has_individual_pv = bool(pv_entities)
    if not has_individual_pv and basis_live.get("pv_gesamt_w"):
        pv_entities.add(basis_live["pv_gesamt_w"])

    # ── Netz-Entities ermitteln ──────────────────────────────────────────
    netz_kombi = basis_live.get("netz_kombi_w")
    netz_bezug = basis_live.get("netzbezug_w")
    netz_einspeisung = basis_live.get("einspeisung_w")
    # Wenn dedizierte Bezug/Einspeisung existieren, Kombi nicht zusätzlich nutzen
    if netz_bezug or netz_einspeisung:
        netz_kombi = None

    netz_entities = {e for e in (netz_kombi, netz_bezug, netz_einspeisung) if e}

    if not pv_entities and not netz_entities:
        return TagesPeaks(None, None, None)

    # ── Invert-Set bauen ─────────────────────────────────────────────────
    invert_eids: set[str] = set()
    for key, should_invert in basis_invert.items():
        if should_invert and key in basis_live:
            invert_eids.add(basis_live[key])
    for inv_id, invert_flags in inv_invert_map.items():
        live = inv_live_map.get(inv_id, {})
        for key, should_invert in invert_flags.items():
            if should_invert and key in live:
                invert_eids.add(live[key])

    # ── HA-LTS-Min/Max lesen ─────────────────────────────────────────────
    try:
        import asyncio
        from backend.services.ha_statistics_service import get_ha_statistics_service

        stats = get_ha_statistics_service()
        if not stats.is_available:
            return TagesPeaks(None, None, None)

        all_eids = list(pv_entities | netz_entities)
        minmax = await asyncio.to_thread(
            stats.get_hourly_minmax_sensor_data, all_eids, datum, datum,
        )
    except Exception as e:
        logger.debug(f"Peak-HA-LTS für {datum}: {e}")
        return TagesPeaks(None, None, None)

    if not minmax:
        return TagesPeaks(None, None, None)

    datum_iso = datum.isoformat()

    def slot_for(eid: str, h: int) -> dict[str, float]:
        s = minmax.get(eid, {}).get(datum_iso, {}).get(h)
        if not s:
            return {}
        if eid in invert_eids:
            # invert: min wird zu -max, max wird zu -min
            return {
                "min": -s["max"] if "max" in s else None,
                "max": -s["min"] if "min" in s else None,
            }
        return s

    # ── peak_pv ──────────────────────────────────────────────────────────
    peak_pv: Optional[float] = None
    if pv_entities:
        for h in range(24):
            stundensumme = 0.0
            haben_daten = False
            for eid in pv_entities:
                s = slot_for(eid, h)
                v = s.get("max") if s else None
                if v is not None and v > 0:
                    stundensumme += v
                    haben_daten = True
            if haben_daten and (peak_pv is None or stundensumme > peak_pv):
                peak_pv = stundensumme

    # ── peak_netzbezug / peak_einspeisung ────────────────────────────────
    peak_bezug: Optional[float] = None
    peak_einsp: Optional[float] = None

    def best_max_positiv(eid: str) -> Optional[float]:
        best: Optional[float] = None
        for h in range(24):
            v = slot_for(eid, h).get("max")
            if v is not None and v > 0 and (best is None or v > best):
                best = v
        return best

    def best_betrag_negativ(eid: str) -> Optional[float]:
        """|min|, wenn min negativ — z. B. für Einspeisung aus Kombi-Sensor."""
        best: Optional[float] = None
        for h in range(24):
            v = slot_for(eid, h).get("min")
            if v is not None and v < 0:
                betrag = -v
                if best is None or betrag > best:
                    best = betrag
        return best

    if netz_bezug:
        peak_bezug = best_max_positiv(netz_bezug)
    if netz_einspeisung:
        peak_einsp = best_max_positiv(netz_einspeisung)
    if netz_kombi:
        peak_bezug = best_max_positiv(netz_kombi)
        peak_einsp = best_betrag_negativ(netz_kombi)

    return TagesPeaks(pv=peak_pv, netzbezug=peak_bezug, einspeisung=peak_einsp)


async def _get_strompreis_stunden(
    anlage: Anlage,
    sensor_mapping: dict,
    datum: date,
) -> StrompreisStunden:
    """
    Holt stündliche Strompreise für einen Tag aus zwei Quellen.

    1. HA-Sensor (Endpreis, nur wenn konfiguriert) → strompreis_cent
    2. Börsenpreis (aWATTar API, immer) → boersenpreis_cent

    Returns:
        StrompreisStunden mit sensor- und boerse-Dicts
    """
    sensor_preise: dict[int, float] = {}
    boersen_preise: dict[int, float] = {}

    # ── HA-Sensor (Endpreis, wenn konfiguriert) ──────────────────────────
    basis = sensor_mapping.get("basis", {})
    sp = basis.get("strompreis")
    sensor_id = sp.get("sensor_id") if isinstance(sp, dict) else None

    if sensor_id:
        # F-26: dritte Stelle derselben Klasse. Der Zugriff hängt an einer
        # erreichbaren HA-Verbindung, nicht am Supervisor — sonst verschweigt
        # der Docker-Betrieb den eigenen Strompreis-Sensor und fällt still auf
        # den Börsenpreis zurück. `is_available` ist `bool(token)` und deckt
        # beide Wege ab; ohne HA (reiner MQTT-Betrieb) bleibt es beim Börsenpreis.
        from backend.services.ha_state_service import get_ha_state_service
        if get_ha_state_service().is_available:
            # ── Pfad 1: HA-LTS-Hourly-Mean (Etappe 5) ────────────────────
            try:
                import asyncio
                from backend.services.ha_statistics_service import get_ha_statistics_service

                stats = get_ha_statistics_service()
                if stats.is_available:
                    slots, unit = await asyncio.to_thread(
                        stats.get_hourly_mean_for_day, sensor_id, datum,
                    )
                    if slots:
                        faktor = _strompreis_faktor(unit)
                        for h, mean in slots.items():
                            sensor_preise[h] = mean * faktor
                        logger.debug(
                            "Strompreis %s: %d Stunden aus HA-LTS-Hourly %s (Einheit %s)",
                            datum, len(sensor_preise), sensor_id, unit,
                        )
            except Exception as e:
                logger.debug("Strompreis LTS %s für %s: %s", sensor_id, datum, e)

            # ── Pfad 2: Fallback State-History-Mittelung ─────────────────
            if not sensor_preise:
                try:
                    from backend.services.ha_state_service import get_ha_state_service
                    ha_service = get_ha_state_service()

                    start = datetime.combine(datum, datetime.min.time())
                    end = start + timedelta(days=1)
                    history = await ha_service.get_sensor_history([sensor_id], start, end)
                    units = await ha_service.get_sensor_units([sensor_id])

                    points = history.get(sensor_id, [])
                    if points:
                        unit = units.get(sensor_id, "")
                        faktor = _strompreis_faktor(unit)

                        for h in range(24):
                            h_start = start + timedelta(hours=h)
                            h_end = h_start + timedelta(hours=1)
                            h_pts = [p[1] * faktor for p in points if h_start <= p[0] < h_end]
                            if h_pts:
                                sensor_preise[h] = sum(h_pts) / len(h_pts)

                        if sensor_preise:
                            logger.debug("Strompreis %s: %d Stunden aus HA-Sensor %s (Fallback)",
                                         datum, len(sensor_preise), sensor_id)
                except Exception as e:
                    logger.debug("Strompreis HA-Sensor %s für %s: %s", sensor_id, datum, e)

    # ── Börsenpreis (aWATTar/EPEX, immer) ────────────────────────────────
    try:
        from backend.services.strompreis_markt_service import get_strompreis_stunden
        land = getattr(anlage, "standort_land", None)
        boersen_preise = await get_strompreis_stunden(land, datum)
        if boersen_preise:
            logger.debug("Börsenpreis %s: %d Stunden (%s)",
                         datum, len(boersen_preise), land or "DE")
    except Exception as e:
        logger.debug("Börsenpreis für %s: %s", datum, e)

    return StrompreisStunden(sensor=sensor_preise, boerse=boersen_preise)


async def _speicher_investitionen(db: AsyncSession, anlage_id: int) -> list:
    """Alle Speicher einer Anlage — Gewichtungs-Grundlage des Anlagen-SoC (N-239).

    Bewusst **ohne** Aktiv-/Stilllegungs-Filter: ein Gerät, das an diesem Tag
    noch einen Ladestand gemeldet hat, gehört auch in seine Gewichtung. Wer hier
    filterte, würde die Summe im Nenner kleiner machen als die Geräte im Zähler
    und den Anlagen-Ladestand nach oben verzerren.
    """
    from backend.models.investition import Investition

    result = await db.execute(
        select(Investition).where(
            Investition.anlage_id == anlage_id,
            Investition.typ == "speicher",
        )
    )
    return list(result.scalars().all())
