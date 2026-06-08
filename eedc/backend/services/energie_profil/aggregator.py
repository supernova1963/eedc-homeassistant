"""
Tag-Aggregator (Etappe 3c P3 Refactoring-Tail).

Aggregiert Energiedaten eines Tages und persistiert sie in 24 Zeilen
TagesEnergieProfil + 1 TagesZusammenfassung. Wird vom Scheduler täglich
für den Vortag, vom Reaggregat-Endpoint manuell und vom Vollbackfill
historisch aufgerufen.

Helper liegen in `backend.services.energie_profil._helpers` (`_tage_zurueck`,
`_get_wetter_ist`, `_get_soc_history`, `_get_strompreis_stunden`) und werden
hier lazy importiert.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from typing import Optional

from sqlalchemy import and_, delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.source_priority import SOURCE_LABELS
from backend.models.anlage import Anlage
from backend.models.investition import Investition
from backend.models.tages_energie_profil import TagesEnergieProfil, TagesZusammenfassung
from backend.services.energie_profil._provenance_helpers import (
    seed_tep_provenance,
    seed_tz_provenance,
)
from backend.services.energie_profil.source import Source
from backend.services.provenance import write_with_provenance
from backend.utils.investition_filter import aktiv_am_tag

logger = logging.getLogger(__name__)


# Prognose-Felder, die der Wetter-Endpoint (`_speichere_prognose` in
# api/routes/live_wetter.py) asynchron in TagesZusammenfassung schreibt.
# `aggregate_day` macht ein Delete-and-Recreate der Tageszeile und MUSS
# diese Felder daher explizit retten — die Liste MUSS alle Prognose-Felder
# spiegeln, die `_speichere_prognose` schreibt. Sonst gehen sie still
# verloren: `pv_prognose_stundenprofil` fehlte hier bis 2026-05-21, dadurch
# wurde der Day-Ahead-Snapshot jede Nacht gelöscht und die Korrekturprofil-
# Heatmap blieb dauerhaft leer (0 Bins).
_PROGNOSE_FELDER_RETTEN: tuple[str, ...] = (
    "pv_prognose_kwh",
    "sfml_prognose_kwh",
    "solcast_prognose_kwh",
    "solcast_p10_kwh",
    "solcast_p90_kwh",
    "pv_prognose_stundenprofil",
    "solcast_prognose_stundenprofil",
    "sfml_prognose_stundenprofil",
)


# Extern-additiv befüllte TZ-Felder, die NICHT vom Wetter-Endpoint, sondern von
# einem anderen additiven Schreiber stammen und beim Delete-and-Recreate genau
# so verloren gehen wie die Prognose-Felder (#190-Verlustklasse). Sie gehören
# bewusst NICHT in `_PROGNOSE_FELDER_RETTEN`: Konformitäts-Test K1 koppelt jene
# Liste exklusiv an die Wetter-Endpoint-Schreibfelder (`_TZ_SCHREIBFELDER_PROGNOSE`),
# `kraftstoffpreis_euro` würde sie out-of-sync brechen. Eigene Liste = gleiche
# Mechanik, ehrliche Semantik. Befüllt via `kraftstoff_preis_service.fill_tagesdaten`
# (additiv, `is None`-Filter). Issue #319, PLAN §8.1, Audit §10.4
# (K2-Allowlist-Folge-Diskussion).
_EXTERN_BEFUELLT_FELDER_RETTEN: tuple[str, ...] = (
    "kraftstoffpreis_euro",
)


async def aggregate_day(
    anlage: Anlage,
    datum: date,
    db: AsyncSession,
    *,
    source: Source,
    prefetched_tagesverlauf: Optional[dict] = None,
) -> Optional[TagesZusammenfassung]:
    """
    Aggregiert Energiedaten eines Tages und speichert sie persistent.

    1. Holt Tagesverlauf-Daten (stündliche Butterfly-Daten)
    2. Holt Wetter-IST-Daten (Temperatur, Strahlung)
    3. Holt Batterie-SoC History
    4. Speichert 24 TagesEnergieProfil-Zeilen
    5. Berechnet + speichert TagesZusammenfassung

    Args:
        anlage: Die Anlage
        datum: Tag für den aggregiert wird
        db: DB-Session
        source: Trigger-Quelle dieses Aufrufs (Source-Enum, v3.34.0 Phase A).
            Steuert: (a) ``datenquelle``-Spaltenwert, (b) Provenance-Writer-
            Suffix, (c) Preserve-Logik bei manueller Reaggregation. Pflicht-
            Keyword-Parameter — kein Default, alle Aufrufer setzen ihn
            explizit (Audit §8.12, Plan v3.34 §3 Phase A E4).
        prefetched_tagesverlauf: Optionale vorgeholte Tagesverlauf-Daten in
            der ``get_tagesverlauf``-Form (``{"serien": [...], "punkte":
            [{"zeit", "werte"}]}``) für GENAU diesen Tag. Gesetzt vom
            Vollbackfill-Pfad (``backfill_from_statistics``, v3.34.2 Phase B),
            der die historischen Stunden-Leistungen gebündelt aus HA-LTS holt
            (`get_hourly_sensor_data` einmal pro Range) — `get_tagesverlauf`
            reicht nur ~10 Tage zurück, deshalb braucht der Backfill die
            Durchreichung. Wenn gesetzt, wird `get_tagesverlauf` NICHT
            aufgerufen; die kategorisierten Stunden-kWh, Boundary-kWh, Peaks,
            Strompreise usw. kommen weiterhin aus den regulären
            `aggregate_day`-Quellen (HA-LTS bevorzugt). Plan v3.34 §3 B.1 +
            B.3 (Pflicht-Mitigation gegen Per-Tag-Bulk-Read-Verlust).
            (Der Plan-Text nennt `dict[date, dict]`; da `aggregate_day`
            per-Tag arbeitet, wird die Per-Tag-Form übergeben — der Caller
            schleift über die Range.)

    Returns:
        TagesZusammenfassung oder None bei Fehler
    """
    from backend.services.energie_profil._helpers import (
        _get_soc_history,
        _get_strompreis_stunden,
        _get_wetter_ist,
        _tage_zurueck,
    )

    # Provenance-Writer codiert die Trigger-Quelle (Scheduler / Monatsabschluss /
    # manuelles Reaggregate / Vollbackfill). Source bleibt einheitlich
    # `auto:monatsabschluss` (Stufe 3) — siehe seed_tz_provenance / seed_tep_provenance.
    auto_writer = source.to_writer()

    sensor_mapping = anlage.sensor_mapping or {}

    if prefetched_tagesverlauf is not None:
        # Vollbackfill-Pfad: historische Stunden-Daten sind bereits gebündelt
        # vorgeholt. Sensor-Konfig wurde vom Caller validiert, get_tagesverlauf
        # (HA-History, ~10 Tage) würde für alte Tage ohnehin leer liefern.
        tv_data = prefetched_tagesverlauf
    else:
        from backend.services.live_power_service import get_live_power_service

        service = get_live_power_service()

        # Sensor-Mapping prüfen
        basis_live = sensor_mapping.get("basis", {}).get("live", {})
        has_inv_live = any(
            isinstance(v, dict) and v.get("live")
            for v in sensor_mapping.get("investitionen", {}).values()
        )

        # Im Standalone-/Docker-Modus sind sensor_mapping.live-Einträge oft leer
        # (MQTT liefert direkt Topics). Wir erlauben aggregate_day trotzdem zu
        # laufen, wenn MQTT-Energy-Snapshots vorliegen — der Zähler-Pfad braucht
        # kein leistung_w. Issue #135 Blocker 2.
        has_mqtt_energy = False
        if not basis_live and not has_inv_live:
            from backend.models.mqtt_energy_snapshot import MqttEnergySnapshot
            cutoff = datetime.combine(datum, datetime.min.time()) - timedelta(days=1)
            mqtt_check = await db.execute(
                select(MqttEnergySnapshot.id).where(
                    MqttEnergySnapshot.anlage_id == anlage.id,
                    MqttEnergySnapshot.timestamp >= cutoff,
                ).limit(1)
            )
            has_mqtt_energy = mqtt_check.scalar_one_or_none() is not None

            if not has_mqtt_energy:
                logger.debug(f"Anlage {anlage.id}: Keine Live-Sensoren konfiguriert")
                return None

        # ── Tagesverlauf-Daten holen ──────────────────────────────────────
        try:
            tv_data = await service.get_tagesverlauf(
                anlage, db, tage_zurueck=_tage_zurueck(datum),
            )
        except Exception as e:
            logger.warning(f"Anlage {anlage.id}, {datum}: Tagesverlauf-Fehler: {type(e).__name__}: {e}")
            tv_data = {"serien": [], "punkte": []}

    serien = tv_data.get("serien", [])
    punkte_raw = tv_data.get("punkte", [])

    # Wenn keine leistung_w-Daten vorliegen aber MQTT-Energy da ist → synthetisches
    # punkte-Array mit leeren werte-Dicts, damit die Stunden-Schleife 24x läuft
    # und die Zähler-Snapshot-Werte in TagesEnergieProfil landen können.
    # (Im Vollbackfill-Pfad mit prefetched_tagesverlauf liefert der Caller die
    # punkte bereits; `has_mqtt_energy` ist dort nicht definiert — die explizite
    # `is None`-Prüfung short-circuited davor.)
    if not punkte_raw and prefetched_tagesverlauf is None and has_mqtt_energy:
        punkte_raw = [{"zeit": f"{h:02d}:00", "werte": {}} for h in range(24)]
    elif not punkte_raw:
        logger.debug(f"Anlage {anlage.id}, {datum}: Keine Tagesverlauf-Daten")
        return None

    # Sub-stündliche Punkte (z.B. 10-Min) auf Stundenmittelwerte aggregieren
    stunden_buckets: dict[int, list[dict]] = {}
    for p in punkte_raw:
        h = int(p["zeit"].split(":")[0])
        stunden_buckets.setdefault(h, []).append(p)

    punkte = []
    for h in sorted(stunden_buckets):
        bucket = stunden_buckets[h]
        alle_keys = {k for p in bucket for k in p.get("werte", {})}
        gemittelt: dict[str, float] = {}
        for k in alle_keys:
            vals = [p["werte"][k] for p in bucket if k in p.get("werte", {})]
            if vals:
                gemittelt[k] = sum(vals) / len(vals)
        punkte.append({"zeit": f"{h:02d}:00", "werte": gemittelt})

    # Serien-Kategorien indexieren (vorzeichenbasiert, zukunftssicher)
    pv_keys = {s["key"] for s in serien if s["kategorie"] == "pv"}
    batterie_keys = {s["key"] for s in serien if s["kategorie"] == "batterie"}
    # V2H: E-Auto mit V2H-Funktion → Schlüssel starten mit "v2h_", Kategorie "eauto"
    v2h_keys = {s["key"] for s in serien if s["key"].startswith("v2h_")}
    netz_keys = {s["key"] for s in serien if s["kategorie"] == "netz"}
    wp_keys = {s["key"] for s in serien if s["kategorie"] == "waermepumpe"}
    wallbox_keys = {s["key"] for s in serien
                    if s["kategorie"] in ("wallbox", "eauto")
                    and not s["key"].startswith("v2h_")}
    sonstige_keys = {s["key"] for s in serien if s["kategorie"] == "sonstige"}
    # Alle Schlüssel die separat behandelt werden (nicht in generischer Summe)
    # "strompreis" und "haushalt" sind keine Energieflüsse und dürfen nicht in pv_kw/verbrauch_kw einfließen
    _sonderschluessel = batterie_keys | v2h_keys | netz_keys | pv_keys | wp_keys | wallbox_keys | sonstige_keys | {"strompreis", "haushalt"}

    # ── PV-Module für GTI-Gruppierung holen (Issue #139) ──────────────────
    # Nur am `datum` aktive Module — sonst verzerrt ein erst später
    # angeschafftes oder schon stillgelegtes Modul die GTI-Referenz und damit
    # die Performance Ratio (v3.34.2 Phase B: aktiv_am_tag-Schnitt, Audit §6.4;
    # zuvor lud aggregate_day ALLE Module, der Vollbackfill filterte sie per Tag).
    pv_module_result = await db.execute(
        select(Investition).where(
            and_(
                Investition.anlage_id == anlage.id,
                Investition.typ.in_(("pv-module", "balkonkraftwerk")),
                aktiv_am_tag(datum),
            )
        )
    )
    pv_module_list = list(pv_module_result.scalars().all())

    # ── Wetter-IST-Daten holen (inkl. GTI für PR-Berechnung) ──────────────
    wetter_stunden = await _get_wetter_ist(anlage, datum, pv_module=pv_module_list)

    # ── SoC-History holen ─────────────────────────────────────────────────
    soc_stunden = await _get_soc_history(anlage, sensor_mapping, datum, db)

    # ── Strompreis-Stundenwerte holen ─────────────────────────────────────
    strompreis_stunden = await _get_strompreis_stunden(anlage, sensor_mapping, datum)

    # ── Zähler-basierte Stunden-kWh (Issue #135 / Etappe 4 v3.31.0) ──────
    # Etappe 4: HA-Statistics-LTS ist Source-of-Truth, wenn verfügbar
    # (HA-Add-on oder Docker mit HA-Recorder-URL). Snapshot-Variante bleibt
    # als Standalone-Fallback (MQTT-Energy-Snapshots).
    # Provenance-Source wird je nach Pfad gesetzt (siehe seed_*_provenance
    # unten) — `external:ha_statistics:hourly` vs `auto:monatsabschluss`.
    kwh_pro_stunde: dict[int, dict[str, Optional[float]]] = {}
    kwh_source_label: str  # für seed_*_provenance
    # Nur am `datum` aktive Investitionen — Per-Tag-Aktiv-Filter (v3.34.2
    # Phase B, Audit §6.4). Vorher lud aggregate_day ALLE Investitionen der
    # Anlage; für historische Tage mit zwischenzeitlich stillgelegter
    # Investition wich das vom Vollbackfill-Pfad (`aktiv_im_zeitraum`) ab.
    # `aktiv_am_tag` ist die per-Tag-Variante und prüft auch das `aktiv`-Flag
    # (aktiv=False = wie gelöscht → nirgends, auch historisch, bis reaktiviert;
    # Gernot 2026-06-05). Bereits aggregierte Tage einer danach deaktivierten
    # Komponente per Werkbank neu rechnen, damit sie aus den Tagessummen fallen.
    # Für den Scheduler (heute/gestern) praktisch ein No-Op: am laufenden Tag
    # aktive Investitionen erfüllen den Filter ohnehin.
    inv_result = await db.execute(
        select(Investition).where(
            and_(
                Investition.anlage_id == anlage.id,
                aktiv_am_tag(datum),
            )
        )
    )
    invs = inv_result.scalars().all()
    invs_by_id = {str(inv.id): inv for inv in invs}
    try:
        from backend.services.snapshot.lts_aggregator import get_hourly_kwh_by_category_lts
        kwh_pro_stunde = await get_hourly_kwh_by_category_lts(
            db, anlage, invs_by_id, datum,
        )
    except Exception as e:
        logger.warning(
            f"Anlage {anlage.id}, {datum}: HA-LTS-Pfad fehlgeschlagen: "
            f"{type(e).__name__}: {e}"
        )
        kwh_pro_stunde = {}

    if kwh_pro_stunde:
        kwh_source_label = "external:ha_statistics:hourly"
    else:
        # Fallback auf Snapshot-Variante (MQTT-/sensor_snapshots-Pfad).
        # Gleicher Output-Vertrag — nur die Quelle ändert sich.
        try:
            from backend.services.sensor_snapshot_service import get_hourly_kwh_by_category
            kwh_pro_stunde = await get_hourly_kwh_by_category(
                db, anlage, invs_by_id, datum,
            )
        except Exception as e:
            logger.warning(
                f"Anlage {anlage.id}, {datum}: Snapshot-Fallback fehlgeschlagen: "
                f"{type(e).__name__}: {e}"
            )
            kwh_pro_stunde = {}
        kwh_source_label = "auto:monatsabschluss"

    # ── Stunden-Counter (Issue #136/#238: WP-Starts + Betriebsstunden pro Stunde) ──
    wp_starts_pro_stunde: dict[int, Optional[int]] = {}
    wp_betriebsstunden_pro_stunde: dict[int, Optional[float]] = {}
    try:
        from backend.services.sensor_snapshot_service import get_hourly_counter_sum_by_feld
        wp_starts_pro_stunde = await get_hourly_counter_sum_by_feld(
            db, anlage, invs_by_id, datum, "wp_starts_anzahl",
        )
        wp_betriebsstunden_pro_stunde = await get_hourly_counter_sum_by_feld(
            db, anlage, invs_by_id, datum, "wp_betriebsstunden",
        )
    except Exception as e:
        logger.warning(
            f"Anlage {anlage.id}, {datum}: WP-Counter-Stunden-Aggregation fehlgeschlagen: "
            f"{type(e).__name__}: {e}"
        )

    # ── Counter-Tagesdifferenzen (Issue #136: WP-Kompressor-Starts) ──────
    # Boundary-Diff über das Tagesfenster. Wird hier — vor der Stunden-Schleife —
    # geholt, weil die Stunden-Σ aus diesem Tageswert ABGELEITET wird (Counter-
    # Daily-Drift Variante 2-light, KONZEPT-COUNTER-DAILY-DRIFT.md): eine Quelle
    # pro Tag. {feld: {inv_id: wert}}, z.B. {"wp_starts_anzahl": {"5": 12}}.
    komponenten_starts: dict = {}
    try:
        from backend.services.sensor_snapshot_service import get_daily_counter_deltas_by_inv
        komponenten_starts = await get_daily_counter_deltas_by_inv(
            db, anlage, invs_by_id, datum,
        )
    except Exception as e:
        logger.warning(
            f"Anlage {anlage.id}, {datum}: Counter-Aggregation fehlgeschlagen: "
            f"{type(e).__name__}: {e}"
        )

    # Stunden-Σ aus dem Boundary-Diff ableiten (SoT pro Tag). Bei sauberen
    # Snapshots verhaltensneutral; bei NULL-Slots/Lücken wird die Stunden-Σ so
    # reskaliert, dass Σ_h == Σ_inv komponenten_starts gilt. Nur wenn der
    # Boundary-Diff für das Feld einen Wert lieferte — sonst bleibt die
    # eigenständig gerechnete Stunden-Σ als Fallback erhalten (kein Datenverlust,
    # wenn ausgerechnet die Tages-Boundary-Snapshots fehlen).
    from backend.core.berechnungen import verteile_counter_auf_stunden

    def _counter_aus_boundary(feld: str, stunden: dict, *, as_float: bool) -> dict:
        je_inv = komponenten_starts.get(feld)
        if not je_inv:
            return stunden
        return verteile_counter_auf_stunden(
            stunden, float(sum(je_inv.values())), as_float=as_float
        )

    wp_starts_pro_stunde = _counter_aus_boundary(
        "wp_starts_anzahl", wp_starts_pro_stunde, as_float=False
    )
    wp_betriebsstunden_pro_stunde = _counter_aus_boundary(
        "wp_betriebsstunden", wp_betriebsstunden_pro_stunde, as_float=True
    )

    # ── Alte Daten für diesen Tag löschen (Upsert) ────────────────────────
    # Extern befüllte Felder vor dem Delete-and-Recreate retten — sie werden
    # nicht vom Aggregator gesetzt, sondern asynchron/additiv von anderen
    # Schreibern: Prognose-Felder vom Wetter-Endpoint (_PROGNOSE_FELDER_RETTEN),
    # Kraftstoffpreis vom kraftstoff_preis_service (_EXTERN_BEFUELLT_FELDER_RETTEN,
    # #319). Ohne Rettung gingen sie bei jedem Recreate verloren (#190-Klasse).
    existing_tz = await db.execute(
        select(TagesZusammenfassung).where(
            and_(
                TagesZusammenfassung.anlage_id == anlage.id,
                TagesZusammenfassung.datum == datum,
            )
        )
    )
    existing_tz_row = existing_tz.scalar_one_or_none()
    preserved_felder = {}
    # #299: pro gerettetem Feld die Ursprungsquelle aus der alten Row-Provenance
    # mitnehmen, damit der Restore-Schreiber unten das Audit-Log mit der echten
    # Herkunft (external:openmeteo / external:fuel_price / …) statt mit einem
    # generischen Aggregator-Label füllt. Wert hier einfrieren, bevor der
    # Delete-and-Recreate die alte Row aus der Session entfernt.
    preserved_quellen: dict[str, str] = {}
    # #290 detLAN: bei manueller Reaggregation ohne Stunden-Daten retten wir
    # zusätzlich Komponenten-Aggregate, damit bestehende gute Werte nicht
    # durch eine evtl. falsche Snapshot-Boundary-Diff überschrieben werden
    # (Beispiel: HA-LTS nicht erreichbar + alte Snapshots in DB inkonsistent
    # → Boundary-Diff liefert Müll, Σ-Hourly liefert 0).
    preserved_komponenten_kwh = (
        dict(existing_tz_row.komponenten_kwh)
        if existing_tz_row and existing_tz_row.komponenten_kwh else None
    )
    preserved_komponenten_starts = (
        dict(existing_tz_row.komponenten_starts)
        if existing_tz_row and existing_tz_row.komponenten_starts else None
    )
    if existing_tz_row:
        alte_provenance = existing_tz_row.source_provenance or {}
        for field in (*_PROGNOSE_FELDER_RETTEN, *_EXTERN_BEFUELLT_FELDER_RETTEN):
            val = getattr(existing_tz_row, field, None)
            if val is not None:
                preserved_felder[field] = val
                quelle = (alte_provenance.get(field) or {}).get("source")
                if quelle in SOURCE_LABELS:
                    preserved_quellen[field] = quelle

    await db.execute(
        delete(TagesEnergieProfil).where(
            and_(
                TagesEnergieProfil.anlage_id == anlage.id,
                TagesEnergieProfil.datum == datum,
            )
        )
    )
    await db.execute(
        delete(TagesZusammenfassung).where(
            and_(
                TagesZusammenfassung.anlage_id == anlage.id,
                TagesZusammenfassung.datum == datum,
            )
        )
    )

    # ── Stundenwerte berechnen + speichern ────────────────────────────────
    tages_ueberschuss = 0.0
    tages_defizit = 0.0
    peak_pv = 0.0
    peak_bezug = 0.0
    peak_einspeisung = 0.0
    temp_values = []
    strahlung_summe = 0.0
    pv_ertrag_summe = 0.0
    gti_summe = 0.0  # kWp-gewichtete GTI (Wh/m²) über den Tag — für PR (#139)
    gti_stunden_count = 0
    soc_values = []
    stunden_count = 0
    komponenten_summen: dict[str, float] = {}  # Per-Komponenten Tages-kWh
    einspeisung_pro_stunde: dict[int, float] = {}  # h → kWh (für Negativpreis-Berechnung)

    for punkt in punkte:
        h = int(punkt["zeit"].split(":")[0])
        werte = punkt.get("werte", {})

        # ── Leistungs-Spitzen aus Tagesverlauf (W-Integration nur für Peaks) ──
        # kW-Peaks brauchen keine kWh-Präzision; Zähler liefern keine Momentanwerte.
        netz_val = sum(werte.get(k, 0) for k in netz_keys)
        einspeisung_kw_w = abs(netz_val) if netz_val < 0 else 0.0
        netzbezug_kw_w = netz_val if netz_val > 0 else 0.0

        pv_kw_w = sum(v for k in pv_keys
                      if (v := werte.get(k, 0)) > 0)
        for k, v in werte.items():
            if v is None or k in _sonderschluessel:
                continue
            if v > 0:
                pv_kw_w += v

        # ── kWh-Werte aus Zähler-Snapshots (Issue #135) ───────────────────
        # Fehlt der Zähler einer Kategorie, bleibt der Wert None.
        # Konvention für Batterie: positiv=Ladung, negativ=Entladung (netto).
        snap_h = kwh_pro_stunde.get(h, {}) if kwh_pro_stunde else {}
        pv_kw = snap_h.get("pv")
        einspeisung_kw = snap_h.get("einspeisung")
        netzbezug_kw = snap_h.get("netzbezug")
        verbrauch_kw = snap_h.get("verbrauch")
        waermepumpe_kw = snap_h.get("wp")
        wallbox_kw = snap_h.get("wallbox")
        batterie_kw = snap_h.get("batterie_netto")

        # Einspeisung pro Stunde für Negativpreis-Analyse (§51 EEG)
        if einspeisung_kw is not None and einspeisung_kw > 0:
            einspeisung_pro_stunde[h] = einspeisung_kw

        # Bilanz-Aggregate (nur wenn pv und verbrauch bekannt)
        if pv_kw is not None and verbrauch_kw is not None:
            ueberschuss = max(0.0, pv_kw - verbrauch_kw)
            defizit = max(0.0, verbrauch_kw - pv_kw)
            tages_ueberschuss += ueberschuss
            tages_defizit += defizit
        else:
            ueberschuss = None
            defizit = None

        if pv_kw is not None:
            pv_ertrag_summe += pv_kw

        peak_pv = max(peak_pv, pv_kw_w)
        peak_bezug = max(peak_bezug, netzbezug_kw_w)
        peak_einspeisung = max(peak_einspeisung, einspeisung_kw_w)

        # Wetter
        wetter_h = wetter_stunden.get(h, {})
        temperatur = wetter_h.get("temperatur_c")
        strahlung = wetter_h.get("globalstrahlung_wm2")
        gti = wetter_h.get("gti_wm2")
        bewoelkung = wetter_h.get("bewoelkung_prozent")
        niederschlag = wetter_h.get("niederschlag_mm")
        wcode = wetter_h.get("wetter_code")
        if temperatur is not None:
            temp_values.append(temperatur)
        if strahlung is not None:
            strahlung_summe += strahlung  # W/m² × 1h = Wh/m²
        if gti is not None:
            gti_summe += gti
            gti_stunden_count += 1

        # SoC
        soc = soc_stunden.get(h)
        if soc is not None:
            soc_values.append(soc)

        # Strompreis (Sensor-Endpreis + Börsenpreis getrennt)
        strompreis = strompreis_stunden.sensor.get(h)
        boersenpreis = strompreis_stunden.boerse.get(h)

        # Per-Komponenten kWh akkumulieren (kW × 1h = kWh) — Live-Σ-Riemann.
        # Nur im Standalone-Fallback (kein HA-LTS) aktiv. Im HA-Add-on-Modus
        # ist diese Akkumulation redundant zum Boundary-Pfad (boundary_kwh
        # weiter unten) und war historische Drift-Quelle: bei Schema-Mismatch
        # zwischen Live-Service-Key und Boundary-Key (z.B. balkonkraftwerk
        # → Live `pv_<id>`, Boundary `bkw_<id>`) blieben beide Keys parallel
        # in `komponenten_summen` und wurden von Whitelist-Konsumenten
        # doppelt gezählt (BKW-Bug 2026-05-19, Rainer-PN).
        if werte and kwh_source_label != "external:ha_statistics:hourly":
            for komp_key, komp_kw in werte.items():
                if komp_kw is not None and komp_key != "strompreis":
                    komponenten_summen[komp_key] = komponenten_summen.get(komp_key, 0.0) + komp_kw

        # TagesEnergieProfil speichern
        # is not None statt `if x` — echte 0-Werte (Nacht-PV) sind keine Lücke.
        profil = TagesEnergieProfil(
            anlage_id=anlage.id,
            datum=datum,
            stunde=h,
            pv_kw=round(pv_kw, 3) if pv_kw is not None else None,
            verbrauch_kw=round(verbrauch_kw, 3) if verbrauch_kw is not None else None,
            einspeisung_kw=round(einspeisung_kw, 3) if einspeisung_kw is not None else None,
            netzbezug_kw=round(netzbezug_kw, 3) if netzbezug_kw is not None else None,
            batterie_kw=round(batterie_kw, 3) if batterie_kw is not None else None,
            waermepumpe_kw=round(waermepumpe_kw, 3) if waermepumpe_kw is not None else None,
            wallbox_kw=round(wallbox_kw, 3) if wallbox_kw is not None else None,
            ueberschuss_kw=round(ueberschuss, 3) if ueberschuss is not None else None,
            defizit_kw=round(defizit, 3) if defizit is not None else None,
            temperatur_c=round(temperatur, 1) if temperatur is not None else None,
            globalstrahlung_wm2=round(strahlung, 0) if strahlung is not None else None,
            bewoelkung_prozent=round(bewoelkung, 0) if bewoelkung is not None else None,
            niederschlag_mm=round(niederschlag, 2) if niederschlag is not None else None,
            wetter_code=int(wcode) if wcode is not None else None,
            soc_prozent=round(soc, 1) if soc is not None else None,
            strompreis_cent=round(strompreis, 2) if strompreis is not None else None,
            boersenpreis_cent=round(boersenpreis, 2) if boersenpreis is not None else None,
            komponenten={k: v for k, v in werte.items() if k != "strompreis"} if werte else None,
            wp_starts_anzahl=wp_starts_pro_stunde.get(h),
            wp_betriebsstunden=wp_betriebsstunden_pro_stunde.get(h),
        )
        db.add(profil)
        seed_tep_provenance(profil, writer=auto_writer, source=kwh_source_label)
        stunden_count += 1

    # ── Börsenpreis-Tagesaggregation ────────────────────────────────────
    boersen_values = [v for v in (strompreis_stunden.boerse.get(h) for h in range(24)) if v is not None]
    boersenpreis_avg = round(sum(boersen_values) / len(boersen_values), 2) if boersen_values else None
    boersenpreis_min = round(min(boersen_values), 2) if boersen_values else None
    neg_stunden = sum(1 for v in boersen_values if v < 0) if boersen_values else None

    # Einspeisung bei negativem Börsenpreis (§51 EEG)
    einsp_neg = 0.0
    for h in range(24):
        bp = strompreis_stunden.boerse.get(h)
        if bp is not None and bp < 0:
            einsp_neg += einspeisung_pro_stunde.get(h, 0.0)
    einsp_neg_kwh = round(einsp_neg, 3) if einsp_neg > 0 else None

    # ── Batterie-Vollzyklen berechnen ─────────────────────────────────────
    vollzyklen = None
    if len(soc_values) >= 2:
        delta_sum = sum(abs(soc_values[i] - soc_values[i - 1])
                        for i in range(1, len(soc_values)))
        # Ein Vollzyklus = ΔSoC von 100% (0→100→0 = 200% ΔSoC → 1 Zyklus)
        vollzyklen = round(delta_sum / 200.0, 2)

    # ── Performance Ratio ─────────────────────────────────────────────────
    # Referenz-Einstrahlung: GTI (modul-gewichtet) statt horizontaler GHI.
    # Bei steilen Modulen + tiefstehender Wintersonne ist GTI bis 3× höher
    # als GHI — mit GHI liefen PR-Werte im Winter künstlich auf 1.5–2.8
    # (Issue #139). Ohne GTI (keine PV-Module, API-Fehler) bleibt PR = None
    # statt einen physikalisch unsinnigen Wert zu liefern.
    performance_ratio = None
    kwp = anlage.leistung_kwp
    if kwp and kwp > 0 and gti_summe > 0:
        theoretisch_kwh = gti_summe * kwp / 1000  # Wh/m² × kWp / 1000
        if theoretisch_kwh > 0:
            performance_ratio = round(pv_ertrag_summe / theoretisch_kwh, 3)

    # Counter-Tagesdifferenzen (`komponenten_starts`) wurden bereits vor der
    # Stunden-Schleife geholt — die Stunden-Σ wird daraus abgeleitet (Counter-
    # Daily-Drift Variante 2-light). Hier nur noch weiterverwenden.

    # ── Tagesgesamt pro Komponente (Etappe 3c P3 + Etappe 4 v3.31.0) ─────
    # Etappe 4: wenn der Stunden-Pfad aus HA-LTS gespeist wurde, nutzen wir
    # auch für die Tages-Komponenten-Summe den HA-LTS-Pfad — damit gilt
    # Σ Hourly == Daily per Konstruktion und die Drift zwischen
    # TagesEnergieProfil.*_kw und TagesZusammenfassung.komponenten_kwh
    # verschwindet (Rainer-PN 2026-05-16).
    # Fallback: Snapshot-Boundary-Diff (HA-konformes Tagesfenster).
    # Live-Σ aus der Stunden-Schleife (Riemann) bleibt nur für Keys, die
    # weder LTS noch Snapshot abdecken — z.B. WP-Suffix-Keys aus dem
    # Tagesverlauf-Service ohne separates Counter-Mapping.
    #
    # Zukunfts-Tage (datum > today): SKIP bleibt — keine sinnvolle
    # Aggregation möglich, weder LTS noch Snapshot haben Daten.
    #
    # Heutiger Tag (datum == today): seit B-clean v3.34.1 erlaubt für den
    # LTS-Pfad (Audit §5.1.1 / MartyBr #620 simon42). Hintergrund: bis v3.34.0
    # war der SKIP auf `datum >= today` formuliert und bildete im HA-Add-on
    # zusammen mit vier weiteren Schutzmaßnahmen einen Dead-Spot —
    # komponenten_kwh war strukturell None für den laufenden Tag, 641 Drift-
    # Warnings/Tag im Daten-Checker. Die ursprüngliche Begründung (Self-
    # Healing aus HA-history liefert für `snap[Folgetag 00:00]` den AKTUELLEN
    # Counter-Stand statt sauberen Tagesgrenz-Wert) trifft NUR die Snapshot-
    # Variante `get_komponenten_tageskwh` (Boundary-Diff `snap[Folgetag 00:00]
    # - snap[Tag 00:00]`). Die LTS-Variante `get_komponenten_tageskwh_lts`
    # ist slot-basiert: sie ruft `get_hourly_kwh_deltas_for_day` auf, das
    # pro Stunden-Slot `boundary[h+1] - boundary[h]` aus HA-Statistics-Rows
    # berechnet und für noch nicht geschriebene Boundaries `None` liefert.
    # `get_komponenten_tageskwh_lts` summiert dann nur die valide-Slots —
    # für `datum == today` ergibt sich eine saubere Teilsumme der schon
    # abgelaufenen Stunden, kein Self-Heal-Inflationsrisiko. Edge-Case
    # 00:05-Scheduler: noch keine Stunde des neuen Tages vorhanden →
    # leeres Dict → komponenten_kwh = None (unverändertes Verhalten).
    #
    # Vier andere Schutzmaßnahmen aus Audit §5.1.1 bewusst UNANGETASTET:
    #   1. BKW-Bug-Fix Live-Σ-Bypass (Z. 403) — schützt vor BKW-Schema-
    #      Mismatch-Doppelzählung (Rainer-PN 2026-05-19).
    #   2. Snapshot-Fallback bleibt an `datum < today` gekoppelt (Z. 531) —
    #      #290 Bug B Schutz für die Snapshot-Variante bleibt aktiv.
    #   3. `live_snapshot_if_missing` im HA-Add-on deaktiviert (#184).
    #   4. LTS-Statistics-Lag (Stunde verfügbar ~5 min nach voller Stunde).
    #
    # #290 Bug A (Symptompatch v3.32.4, mit v3.33.0 OBSOLET): der frühere
    # generische Skip bei `datenquelle == "manuell"` war eine Notbremse
    # gegen den LTS-Aggregator-Drift — Boundary-Diff lieferte buggy Werte
    # (alle Sensoren einer Investition aufsummiert). Mit dem strukturellen
    # Fix in `services.snapshot.komponenten_beitraege` liefert Boundary-Diff
    # jetzt die korrekten Per-Typ-Werte. Skip entfernt, damit die
    # Reparatur-Werkbank ihren eigentlichen Zweck erfüllt: User klickt
    # "Tag neu aggregieren" → komponenten_kwh wird aktualisiert.
    # Schutz für die seltene Konstellation "HA-LTS weg + Snapshots korrupt"
    # bleibt über die preserve-Logik unten (greift wenn boundary leer).
    boundary_kwh: dict[str, float] = {}
    if datum > date.today():
        logger.debug(
            f"Anlage {anlage.id}, {datum}: Boundary-Diff übersprungen für "
            f"Zukunfts-Tag — keine Daten verfügbar."
        )
    elif kwh_source_label == "external:ha_statistics:hourly":
        try:
            from backend.services.snapshot.lts_aggregator import get_komponenten_tageskwh_lts
            boundary_kwh = await get_komponenten_tageskwh_lts(
                anlage, invs_by_id, datum,
            )
        except Exception as e:
            logger.warning(
                f"Anlage {anlage.id}, {datum}: Komponenten-Tagesgesamt HA-LTS "
                f"fehlgeschlagen, Snapshot-Fallback aktiv: {type(e).__name__}: {e}"
            )
    if not boundary_kwh and datum < date.today():
        try:
            from backend.services.snapshot.aggregator import get_komponenten_tageskwh
            boundary_kwh = await get_komponenten_tageskwh(
                db, anlage, invs_by_id, datum,
            )
        except Exception as e:
            logger.warning(
                f"Anlage {anlage.id}, {datum}: Komponenten-Tagesgesamt aus Snapshots "
                f"fehlgeschlagen, Σ-Hourly-Fallback aktiv: {type(e).__name__}: {e}"
            )
    for key, val in boundary_kwh.items():
        komponenten_summen[key] = val

    # ── Peak-Werte aus HA-LTS-Min/Max (Etappe 5 v3.31.0) ─────────────────
    # HA-Recorder schreibt für has_mean=True-Sensoren die im 5-Sekunden-Bucket
    # beobachteten Extremwerte pro Stunde. Das ist die richtige Quelle für
    # Tages-Peaks — die Berechnung aus 10-Min-Mittelwerten unterschätzt sie
    # systematisch. Fallback bleibt die Tagesverlauf-Berechnung oben.
    try:
        from backend.services.energie_profil._helpers import _get_tagespeaks_aus_ha_lts
        lts_peaks = await _get_tagespeaks_aus_ha_lts(anlage, datum, db)
        if lts_peaks.pv is not None:
            peak_pv = lts_peaks.pv
        if lts_peaks.netzbezug is not None:
            peak_bezug = lts_peaks.netzbezug
        if lts_peaks.einspeisung is not None:
            peak_einspeisung = lts_peaks.einspeisung
    except Exception as e:
        logger.debug(f"Peak-HA-LTS-Override für {datum}: {e}")

    # ── TagesZusammenfassung speichern ────────────────────────────────────
    zusammenfassung = TagesZusammenfassung(
        anlage_id=anlage.id,
        datum=datum,
        ueberschuss_kwh=round(tages_ueberschuss, 2) if tages_ueberschuss > 0 else None,
        defizit_kwh=round(tages_defizit, 2) if tages_defizit > 0 else None,
        peak_pv_kw=round(peak_pv, 2) if peak_pv > 0 else None,
        peak_netzbezug_kw=round(peak_bezug, 2) if peak_bezug > 0 else None,
        peak_einspeisung_kw=round(peak_einspeisung, 2) if peak_einspeisung > 0 else None,
        batterie_vollzyklen=vollzyklen,
        temperatur_min_c=round(min(temp_values), 1) if temp_values else None,
        temperatur_max_c=round(max(temp_values), 1) if temp_values else None,
        strahlung_summe_wh_m2=round(strahlung_summe, 0) if strahlung_summe > 0 else None,
        performance_ratio=performance_ratio,
        stunden_verfuegbar=stunden_count,
        datenquelle=source.to_db_string(),
        boersenpreis_avg_cent=boersenpreis_avg,
        boersenpreis_min_cent=boersenpreis_min,
        negative_preis_stunden=neg_stunden,
        einspeisung_neg_preis_kwh=einsp_neg_kwh,
        # Preserve-Logik nur bei manueller Reaggregation — Pattern-Adaption
        # v3.32.4 (#290, Audit §4.2). Ursprung: Monatsdaten-Kontext, wo
        # manuell editierte Werte vor Scheduler-Überschreibung geschützt
        # werden. In TZ gibt es keine manuelle Werteingabe; „manuell"
        # bedeutet hier „Werkbank-Trigger" (Source.MANUAL_REPAIR). Der Schutz
        # greift GENAU im else-Zweig unten, d. h. wenn `komponenten_summen`
        # LEER ist (Σ-Hourly = 0, boundary leer) — ein versehentlicher
        # Werkbank-Klick bei nicht erreichbarem HA-LTS + fehlenden/korrupten
        # Snapshots würde sonst die alten korrekten Werte mit None
        # überschreiben. (NICHT geschützt: „Boundary-Diff liefert Müll" — Müll
        # ist nicht-leer, landet also im if-Zweig; dieses Szenario ist seit
        # v3.33.0 ohnehin strukturell entschärft, Per-Typ statt Alle-Sensoren-
        # Summe.) Der Scheduler ist absichtlich NICHT geschützt: ein legitim
        # leerer Tag (Sensor-Ausfall, Offline-Phase) soll nicht ewig die alte
        # Wahrheit weitertragen.
        #
        # Preserve-Asymmetrie-Prüfung (#318-Begleitung, 2026-06-03): geprüft, ob
        # das v3.33.0-Snapshot-Self-Healing den Schutz überflüssig macht —
        # ERGEBNIS: nein. Die Self-Healing-Kaskade in `reader.get_snapshot`
        # (DB → HA-Statistics → MQTT) heilt Stufe 2 NUR bei `ha_svc.is_available`;
        # in genau der geschützten Konstellation (HA unerreichbar) fällt sie aus,
        # und für historische Tage läuft der Scheduler nie nach → ohne Preserve
        # permanenter komponenten_kwh-Verlust eines Alttags. Bekannte Grenze:
        # der Schutz ist partiell (nur komponenten_kwh/_starts, nicht
        # ueberschuss/defizit/Peaks). Sauberere Lösung wäre, dass die Werkbank
        # quellenlose Tage überspringt statt zu überschreiben — eigener Schnitt,
        # bewusst nicht hier.
        komponenten_kwh=(
            {k: round(v, 2) for k, v in komponenten_summen.items()}
            if komponenten_summen
            else (
                preserved_komponenten_kwh
                if source.is_manual_repair()
                else None
            )
        ),
        komponenten_starts=(
            komponenten_starts
            or (
                preserved_komponenten_starts
                if source.is_manual_repair()
                else None
            )
        ),
    )

    # Etappe 4: TagesZusammenfassung-Source spiegelt die Hauptquelle der
    # Daily-Werte. Wenn die Stunden aus HA-LTS kamen, ist auch die
    # Tagessumme aus HA-LTS-Daten konsistent (Σ Hourly = Daily).
    tz_source_label = (
        "external:ha_statistics:daily"
        if kwh_source_label == "external:ha_statistics:hourly"
        else "auto:monatsabschluss"
    )
    db.add(zusammenfassung)
    seed_tz_provenance(zusammenfassung, writer=auto_writer, source=tz_source_label)

    # Gerettete extern-befüllte Felder wiederherstellen (Prognose + Kraftstoffpreis).
    # #299: bewusst NACH seed_tz_provenance und über write_with_provenance statt
    # per setattr — so entsteht ein Audit-Log-Eintrag pro Restore und die
    # Provenance trägt die echte Ursprungsquelle statt des Aggregator-Labels.
    # Die Felder sind beim Seed noch None (frische Row → der Seed-Loop überspringt
    # sie), also greift hier kein Hierarchie-Konflikt; der Restore wird angewandt.
    for field, val in preserved_felder.items():
        restore_source = preserved_quellen.get(field, "auto:preserve_restore")
        ergebnis = await write_with_provenance(
            db, zusammenfassung, field, val,
            source=restore_source, writer="aggregator-preserve",
        )
        if not ergebnis.applied:
            # Darf nicht passieren (frische Row, existing=None) — wenn doch,
            # ginge der gerettete Wert still verloren. Sichtbar machen statt
            # schlucken (feedback_silent_except_logs).
            logger.warning(
                f"Anlage {anlage.id}, {datum}: Restore von '{field}' "
                f"nicht angewandt ({ergebnis.decision}: {ergebnis.reason}) — "
                f"geretteter Wert ginge verloren."
            )
            setattr(zusammenfassung, field, val)

    await db.flush()

    # Pflicht-Invariante (ADR-001 Berechnungs-Layer):
    # Σ pv_kw aus der Stunden-Schleife muss mit Σ PV+BKW aus dem
    # Tages-JSON übereinstimmen. Seit v3.33.0 (Issue #290) auf alle
    # Komponenten-Kategorien erweitert (WP, Wallbox+E-Auto, Batterie,
    # Basis-Einspeisung/-Netzbezug) — Drift bleibt nicht mehr unentdeckt.
    # Wir loggen Warning + speichern trotzdem — Drift soll sichtbar werden,
    # aber kein Tag soll wegen einer Invariante verloren gehen.
    from backend.core.berechnungen import (
        pruefe_tep_komponenten_intern_konsistenz,
        pruefe_tep_tz_komponenten_konsistenz,
        pruefe_tep_tz_konsistenz,
    )

    # TagesEnergieProfil-Rows aus der aktuellen Session ziehen (db.add wurde
    # in der Stunden-Schleife aufgerufen, db.flush hat sie persistiert).
    tep_rows_result = await db.execute(
        select(TagesEnergieProfil).where(
            and_(
                TagesEnergieProfil.anlage_id == anlage.id,
                TagesEnergieProfil.datum == datum,
            )
        )
    )
    tep_rows = tep_rows_result.scalars().all()
    invariante = pruefe_tep_tz_konsistenz(
        tep_rows, zusammenfassung.komponenten_kwh,
    )
    if not invariante.konsistent:
        logger.warning(
            f"Anlage {anlage.id}, {datum}: Berechnungs-Layer-Invariante "
            f"verletzt — {invariante}"
        )
    for bericht in pruefe_tep_tz_komponenten_konsistenz(
        tep_rows, zusammenfassung.komponenten_kwh,
    ):
        if not bericht.konsistent:
            logger.warning(
                f"Anlage {anlage.id}, {datum}: Komponenten-Drift — {bericht}"
            )
    # Achse 2 (#315): Leistungspfad (TEP.komponenten-JSON) vs Zählerpfad
    # (TEP.*_kw-Spalten) derselben Stunden. Im HA-LTS-Modus ist das die einzige
    # Prüfung des Leistungs-JSON; im Standalone redundant zur TZ-Prüfung oben.
    # Warning-level — Step-Integrations-Drift sichtbar machen, kein Tag-Verlust.
    for bericht in pruefe_tep_komponenten_intern_konsistenz(tep_rows):
        if not bericht.konsistent:
            logger.warning(
                f"Anlage {anlage.id}, {datum}: Achse-2-Komponenten-Drift — {bericht}"
            )

    # Counter-Daily-Drift (Variante 2-light, KONZEPT-COUNTER-DAILY-DRIFT.md):
    # Σ_h TagesEnergieProfil.<feld> muss dem Tages-Boundary-Diff
    # (TagesZusammenfassung.komponenten_starts) entsprechen. Die Stunden-Σ wird
    # oben aus dem Boundary-Diff abgeleitet — diese Invariante macht eine
    # verbleibende Drift sichtbar (analog kWh-Pfad, ADR-001). Warning, kein
    # Tag-Verlust.
    from backend.core.berechnungen import pruefe_counter_konsistent

    for feld in ("wp_starts_anzahl", "wp_betriebsstunden"):
        je_inv = (zusammenfassung.komponenten_starts or {}).get(feld)
        if not je_inv:
            continue
        stunden_map = {r.stunde: getattr(r, feld, None) for r in tep_rows}
        bericht = pruefe_counter_konsistent(
            stunden_map, float(sum(je_inv.values())),
            name=f"counter:{feld}", toleranz=0.5,
        )
        if not bericht.konsistent:
            logger.warning(
                f"Anlage {anlage.id}, {datum}: Counter-Drift — {bericht}"
            )

    logger.info(
        f"Anlage {anlage.id}, {datum}: {stunden_count}h aggregiert, "
        f"Überschuss={tages_ueberschuss:.1f}kWh, Defizit={tages_defizit:.1f}kWh, "
        f"PR={performance_ratio or '-'}"
    )

    return zusammenfassung
