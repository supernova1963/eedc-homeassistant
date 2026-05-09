"""
Energie-Profil Aggregations-Service.

Berechnet und persistiert stündliche Energieprofile und Tageszusammenfassungen
aus HA-Sensor-History oder MQTT-Daten.

Wird täglich nach Mitternacht vom Scheduler ausgeführt (für den Vortag)
und kann beim Monatsabschluss rückwirkend nachberechnet werden.

Datenfluss:
  HA Sensor History / MQTT Snapshots
  → get_tagesverlauf() (LivePowerService)
  → aggregate_day() (dieser Service)
  → TagesEnergieProfil (24 Zeilen) + TagesZusammenfassung (1 Zeile)
  → monatlich: rollup_month() → Monatsdaten-Felder aktualisieren
"""

import asyncio
import logging
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Literal, Optional

from sqlalchemy import select, delete, and_, func
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.config import settings
from backend.core.database import get_session
from backend.models.anlage import Anlage
from backend.models.investition import Investition
from backend.models.monatsdaten import Monatsdaten
from backend.models.tages_energie_profil import TagesEnergieProfil, TagesZusammenfassung

logger = logging.getLogger(__name__)


# aggregate_day wurde in Etappe 3c P3 nach services/energie_profil/aggregator.py
# verschoben — Re-Export für bestehende Importer (z.B. routes/energie_profil.py).
from backend.services.energie_profil.aggregator import aggregate_day  # noqa: F401


async def rollup_month(
    anlage_id: int,
    jahr: int,
    monat: int,
    db: AsyncSession,
) -> bool:
    """
    Aggregiert TagesZusammenfassungen eines Monats in Monatsdaten-Felder.

    Args:
        anlage_id: Anlage-ID
        jahr/monat: Zeitraum

    Returns:
        True wenn Daten vorhanden und aktualisiert
    """
    # Monats-Range
    erster = date(jahr, monat, 1)
    if monat == 12:
        letzter = date(jahr + 1, 1, 1)
    else:
        letzter = date(jahr, monat + 1, 1)

    # Alle TagesZusammenfassungen im Monat
    result = await db.execute(
        select(TagesZusammenfassung).where(
            and_(
                TagesZusammenfassung.anlage_id == anlage_id,
                TagesZusammenfassung.datum >= erster,
                TagesZusammenfassung.datum < letzter,
            )
        )
    )
    tage = result.scalars().all()

    if not tage:
        return False

    # Monatsdaten laden oder erstellen
    md_result = await db.execute(
        select(Monatsdaten).where(
            and_(
                Monatsdaten.anlage_id == anlage_id,
                Monatsdaten.jahr == jahr,
                Monatsdaten.monat == monat,
            )
        )
    )
    md = md_result.scalar_one_or_none()
    if not md:
        return False  # Monatsdaten müssen existieren

    # Aggregation
    from sqlalchemy.orm.attributes import flag_modified

    ueberschuss_vals = [t.ueberschuss_kwh for t in tage if t.ueberschuss_kwh is not None]
    defizit_vals = [t.defizit_kwh for t in tage if t.defizit_kwh is not None]
    zyklen_vals = [t.batterie_vollzyklen for t in tage if t.batterie_vollzyklen is not None]
    pr_vals = [t.performance_ratio for t in tage if t.performance_ratio is not None]
    peak_bezug_vals = [t.peak_netzbezug_kw for t in tage if t.peak_netzbezug_kw is not None]

    md.ueberschuss_kwh = round(sum(ueberschuss_vals), 1) if ueberschuss_vals else None
    md.defizit_kwh = round(sum(defizit_vals), 1) if defizit_vals else None
    md.batterie_vollzyklen = round(sum(zyklen_vals), 1) if zyklen_vals else None
    md.performance_ratio = round(sum(pr_vals) / len(pr_vals), 3) if pr_vals else None
    md.peak_netzbezug_kw = round(max(peak_bezug_vals), 2) if peak_bezug_vals else None

    logger.info(
        f"Monat {jahr}/{monat:02d} Anlage {anlage_id}: "
        f"{len(tage)} Tage aggregiert, "
        f"Überschuss={md.ueberschuss_kwh}kWh, Defizit={md.defizit_kwh}kWh"
    )

    return True


async def aggregate_yesterday_all() -> dict:
    """
    Scheduler-Job: Finalisiert den Vortag für alle Anlagen (täglich um 00:15).

    Schreibt den Vortag final (inkl. Wetter-IST-Daten aus Archive-API),
    berechnet TagesZusammenfassung und räumt alte TagesEnergieProfil-Einträge auf.

    Retention: TagesEnergieProfil-Einträge älter als 2 Jahre werden gelöscht.
    TagesZusammenfassung bleibt dauerhaft erhalten.

    Returns:
        Dict mit Ergebnissen pro Anlage
    """
    gestern = date.today() - timedelta(days=1)
    results = {}

    async with get_session() as db:
        anlagen_result = await db.execute(select(Anlage))
        anlagen = anlagen_result.scalars().all()

        for anlage in anlagen:
            try:
                zusammenfassung = await aggregate_day(
                    anlage, gestern, db, datenquelle="scheduler",
                )
                results[anlage.id] = {
                    "status": "ok" if zusammenfassung else "keine_daten",
                    "datum": gestern.isoformat(),
                }
            except Exception as e:
                logger.error(f"Anlage {anlage.id}: Aggregation fehlgeschlagen: {type(e).__name__}: {e}")
                results[anlage.id] = {"status": "fehler", "error": str(e)}

        # Retention-Cleanup: TagesEnergieProfil älter als 2 Jahre löschen
        cutoff = date.today() - timedelta(days=730)
        result = await db.execute(
            delete(TagesEnergieProfil).where(TagesEnergieProfil.datum < cutoff)
        )
        deleted = result.rowcount
        if deleted > 0:
            logger.info(f"Energie-Profil Cleanup: {deleted} Stundenwerte älter als 2 Jahre gelöscht")
        await db.commit()

    return results


async def aggregate_today_all() -> dict:
    """
    Rollierender Job: Aggregiert den laufenden Tag für alle Anlagen.

    Läuft alle 15 Minuten. Schreibt alle abgeschlossenen Stunden des heutigen
    Tages (mit 10-Minuten-Puffer, damit HA-History die Daten garantiert hat).
    Überschreibt bestehende Stunden-Einträge (Upsert via Delete+Insert).

    Die 00:15-Aggregation des Vortags finalisiert dann die Wetter-IST-Daten
    und schreibt die TagesZusammenfassung endgültig.

    Returns:
        Dict mit Ergebnissen pro Anlage
    """
    from datetime import datetime as dt
    now = dt.now()
    heute = date.today()

    # Nur abgeschlossene Stunden mit 10-Min-Puffer schreiben
    # (Stunde H ist abgeschlossen wenn es mindestens H:10 Uhr ist)
    letzte_abgeschlossene_stunde = now.hour - 1 if now.minute < 10 else now.hour
    if letzte_abgeschlossene_stunde < 0:
        return {}  # Kurz nach Mitternacht — nichts zu tun

    results = {}

    async with get_session() as db:
        anlagen_result = await db.execute(select(Anlage))
        anlagen = anlagen_result.scalars().all()

        for anlage in anlagen:
            try:
                zusammenfassung = await aggregate_day(
                    anlage, heute, db, datenquelle="scheduler",
                )
                results[anlage.id] = {
                    "status": "ok" if zusammenfassung else "keine_daten",
                    "datum": heute.isoformat(),
                    "bis_stunde": letzte_abgeschlossene_stunde,
                }
            except Exception as e:
                logger.debug(f"Anlage {anlage.id}: Heute-Aggregation: {type(e).__name__}: {e}")
                results[anlage.id] = {"status": "fehler", "error": str(e)}

    return results


async def backfill_range(
    anlage: Anlage,
    von: date,
    bis: date,
    db: AsyncSession,
) -> int:
    """
    Nachberechnung für einen Datumsbereich (z.B. beim Monatsabschluss).

    Nur möglich wenn HA-History noch verfügbar ist (~10 Tage).

    Args:
        anlage: Die Anlage
        von/bis: Datumsbereich (inklusiv)
        db: DB-Session

    Returns:
        Anzahl erfolgreich aggregierter Tage
    """
    count = 0
    current = von
    while current <= bis:
        try:
            result = await aggregate_day(
                anlage, current, db, datenquelle="monatsabschluss",
            )
            if result:
                count += 1
        except Exception as e:
            logger.warning(f"Backfill {current}: {type(e).__name__}: {e}")
        current += timedelta(days=1)

    if count > 0:
        logger.info(f"Backfill Anlage {anlage.id}: {count} Tage von {von} bis {bis}")

    return count


async def backfill_from_statistics(
    anlage: "Anlage",
    von: date,
    bis: date,
    db: AsyncSession,
) -> dict:
    """
    Additiver Energieprofil-Aufbau aus HA Long-Term Statistics.

    Ergänzt fehlende Tage. Bestehende Tage bleiben **immer** unverändert —
    ein Overwrite-Modus existiert bewusst nicht (#190): „löschen + neu
    berechnen" ist datenfeindlich, weil HA-LTS für viele Anlagen kürzer
    zurückreicht als das gepflegte Profil. Wer einen einzelnen Tag reparieren
    will, nutzt /reaggregate-tag mit Vorschau (chirurgisch, idempotent).

    Args:
        anlage: Die Anlage
        von/bis: Datumsbereich (inklusiv)
        db: DB-Session

    Returns:
        dict mit:
          - geschrieben (int): erfolgreich geschriebene Tage
          - uebersprungen_keine_daten (int): Tage ohne HA-Statistics-Werte
            (#190 Bug B: vorher stiller Skip — User dachte „79,4 % wurden
            verloren", tatsächlich hatte HA für diese Tage keine Daten)
          - uebersprungen_existiert (int): Tage mit bereits vorhandenem Profil
    """
    import asyncio
    from sqlalchemy import select as sa_select, delete as sa_delete, and_ as sa_and

    from backend.models.investition import Investition
    from backend.utils.investition_filter import aktiv_im_zeitraum
    from backend.services.live_sensor_config import (
        extract_live_config,
        TV_SERIE_CONFIG,
        SKIP_TYPEN,
    )
    from backend.services.ha_statistics_service import get_ha_statistics_service

    # Investitionen laden — alle die im Backfill-Zeitraum aktiv waren,
    # nicht nur die heute aktiven (sonst fehlen stillgelegte Investitionen
    # für historische Tage vor dem Stilllegungsdatum)
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
        logger.info(f"Anlage {anlage.id}: Keine Live-Sensoren konfiguriert, Backfill übersprungen")
        return 0

    # ── Serien + Entity-Mapping aufbauen (spiegelt live_tagesverlauf_service.py) ──
    serien: list[dict] = []
    serie_entities: dict[str, list[str]] = {}  # serie_key → [entity_id]

    for inv_id, live in inv_live_map.items():
        inv = investitionen.get(inv_id)
        if not inv:
            continue
        typ = inv.typ
        if typ in SKIP_TYPEN:
            continue

        has_leistung = live.get("leistung_w")

        # WP mit getrennter Strommessung
        if not has_leistung and typ == "waermepumpe":
            config = TV_SERIE_CONFIG.get("waermepumpe")
            if config:
                for suffix, field in (("heizen", "leistung_heizen_w"), ("warmwasser", "leistung_warmwasser_w")):
                    eid = live.get(field)
                    if eid:
                        key = f"waermepumpe_{inv_id}_{suffix}"
                        serien.append({"key": key, "inv_id": inv_id, "kategorie": config["kategorie"],
                                       "seite": config["seite"], "bidirektional": config["bidirektional"]})
                        serie_entities[key] = [eid]
            continue

        if not has_leistung:
            continue

        # E-Auto mit Parent (Wallbox) überspringen
        if typ == "e-auto" and inv.parent_investition_id is not None:
            continue

        config = TV_SERIE_CONFIG.get(typ)
        if not config:
            continue

        seite = config["seite"]
        bidirektional = config["bidirektional"]
        if typ == "sonstiges" and isinstance(inv.parameter, dict):
            kat = inv.parameter.get("kategorie", "verbraucher")
            if kat == "erzeuger":
                seite = "quelle"
            elif kat == "speicher":
                bidirektional = True

        serie_key = f"{config['kategorie']}_{inv_id}"
        serien.append({"key": serie_key, "inv_id": inv_id, "kategorie": config["kategorie"],
                       "seite": seite, "bidirektional": bidirektional})
        serie_entities[serie_key] = [live["leistung_w"]]

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

    # ── Alle Entity-IDs sammeln ──────────────────────────────────────────────
    all_entity_ids: set[str] = set(eid for eids in serie_entities.values() for eid in eids)
    if netz_kombi_eid:
        all_entity_ids.add(netz_kombi_eid)
    if netz_bezug_eid:
        all_entity_ids.add(netz_bezug_eid)
    if netz_einspeisung_eid:
        all_entity_ids.add(netz_einspeisung_eid)

    # SoC-Entities — nur stationäre Speicher, sonst kontaminiert E-Auto-SoC
    # die Vollzyklen-Berechnung der PV-Anlage.
    soc_entity: Optional[str] = None
    for inv_id, live in inv_live_map.items():
        if not live.get("soc"):
            continue
        inv = investitionen.get(inv_id)
        if inv is None or inv.typ != "speicher":
            continue
        soc_entity = live["soc"]
        all_entity_ids.add(soc_entity)
        break  # Erstes Speicher-SoC-Entity reicht

    if not all_entity_ids:
        return 0

    # ── HA Statistics abfragen (Executor wegen Sync-SQLAlchemy) ─────────────
    ha_service = get_ha_statistics_service()
    if not ha_service.is_available:
        logger.warning(f"Anlage {anlage.id}: HA Statistics nicht verfügbar, Backfill übersprungen")
        return 0

    hourly_data = await asyncio.to_thread(
        ha_service.get_hourly_sensor_data, list(all_entity_ids), von, bis
    )

    if not hourly_data:
        logger.info(f"Anlage {anlage.id}: Keine Statistics-Daten für {von}–{bis}")
        return 0

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

    # ── Kategorie-Schlüssel-Sets (identisch zu aggregate_day) ────────────────
    pv_keys = {s["key"] for s in serien if s["kategorie"] == "pv"}
    batterie_keys = {s["key"] for s in serien if s["kategorie"] == "batterie"}
    v2h_keys = {s["key"] for s in serien if s["key"].startswith("v2h_")}
    netz_keys = {s["key"] for s in serien if s["kategorie"] == "netz"}
    wp_keys = {s["key"] for s in serien if s["kategorie"] == "waermepumpe"}
    wallbox_keys = {
        s["key"] for s in serien
        if s["kategorie"] in ("wallbox", "eauto") and not s["key"].startswith("v2h_")
    }
    # Bugfix: sonstige_keys fehlten hier (führte dazu, dass "sonstiges"-Erzeuger
    # doppelt in pv_kw einflossen). Nun analog zu aggregate_day.
    sonstige_keys = {s["key"] for s in serien if s["kategorie"] == "sonstige"}
    _sonderschluessel = (
        batterie_keys | v2h_keys | netz_keys | pv_keys
        | wp_keys | wallbox_keys | sonstige_keys
    )

    # ── Bestehende Tage ermitteln (immer additiv, #190) ──────────────────────
    ex_result = await db.execute(
        sa_select(TagesZusammenfassung.datum).where(
            sa_and(
                TagesZusammenfassung.anlage_id == anlage.id,
                TagesZusammenfassung.datum >= von,
                TagesZusammenfassung.datum <= bis,
            )
        )
    )
    existing_dates: set[date] = {row[0] for row in ex_result}

    # ── Pro-Tag-Schleife ─────────────────────────────────────────────────────
    count = 0
    skipped_no_data = 0
    skipped_existing = 0
    current = von
    while current <= bis:
        if current in existing_dates:
            skipped_existing += 1
            current += timedelta(days=1)
            continue

        datum_iso = current.isoformat()

        # Wetter-IST-Daten für diesen Tag (inkl. GTI für PR — Issue #139).
        # Nur PV-Module berücksichtigen die an diesem Tag aktiv waren.
        pv_module_aktiv = [
            inv for inv in investitionen.values()
            if inv.typ in ("pv-module", "balkonkraftwerk") and inv.ist_aktiv_an(current)
        ]
        wetter_stunden = await _get_wetter_ist(anlage, current, pv_module=pv_module_aktiv)

        # SoC-Werte für diesen Tag
        soc_stunden: dict[int, float] = {}
        if soc_entity and soc_entity in hourly_data:
            soc_stunden = hourly_data[soc_entity].get(datum_iso, {})

        # Zähler-basierte kWh pro Stunde (Issue #135)
        kwh_pro_stunde_tag: dict[int, dict[str, Optional[float]]] = {}
        try:
            from backend.services.sensor_snapshot_service import get_hourly_kwh_by_category
            kwh_pro_stunde_tag = await get_hourly_kwh_by_category(
                db, anlage, investitionen, current,
            )
        except Exception as e:
            logger.warning(
                f"Anlage {anlage.id}, {current}: Zähler-Snapshot fehlgeschlagen: "
                f"{type(e).__name__}: {e}"
            )
            kwh_pro_stunde_tag = {}

        # Stundenschleife: werte-Dict aufbauen (Butterfly-Konvention)
        tages_ueberschuss = 0.0
        tages_defizit = 0.0
        peak_pv = 0.0
        peak_bezug = 0.0
        peak_einspeisung = 0.0
        temp_values: list[float] = []
        strahlung_summe = 0.0
        gti_summe = 0.0  # PR-Referenz (#139)
        pv_ertrag_summe = 0.0
        soc_values: list[float] = []
        stunden_count = 0
        komponenten_summen: dict[str, float] = {}

        # Serien filtern: nur Investitionen die an diesem Tag aktiv waren
        tages_serien = [
            s for s in serien
            if s.get("inv_id") is None  # Basis-Serien (PV Gesamt, Netz)
            or investitionen.get(s["inv_id"], None) is None  # Safety
            or investitionen[s["inv_id"]].ist_aktiv_an(current)
        ]

        stunden_mit_daten = 0
        pending_tep: list[TagesEnergieProfil] = []
        for h in range(24):
            # werte-Dict aus Statistics aufbauen (spiegelt live_tagesverlauf_service.py)
            werte: dict[str, float] = {}

            for serie in tages_serien:
                skey = serie["key"]
                if serie["kategorie"] == "netz":
                    continue  # Netz separat

                entity_ids = serie_entities.get(skey, [])
                serie_sum_kw = 0.0
                has_data = False
                for entity_id in entity_ids:
                    val = hourly_data.get(entity_id, {}).get(datum_iso, {}).get(h)
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

            # Netz
            bezug_kw = 0.0
            einsp_kw = 0.0
            if netz_kombi_eid:
                val = hourly_data.get(netz_kombi_eid, {}).get(datum_iso, {}).get(h)
                if val is not None:
                    if val >= 0:
                        bezug_kw = val
                    else:
                        einsp_kw = abs(val)
            else:
                if netz_bezug_eid:
                    val = hourly_data.get(netz_bezug_eid, {}).get(datum_iso, {}).get(h)
                    if val is not None:
                        bezug_kw = max(0.0, val)
                if netz_einspeisung_eid:
                    val = hourly_data.get(netz_einspeisung_eid, {}).get(datum_iso, {}).get(h)
                    if val is not None:
                        einsp_kw = max(0.0, val)
            netto_kw = bezug_kw - einsp_kw
            if bezug_kw > 0 or einsp_kw > 0 or abs(netto_kw) > 0.001:
                werte["netz"] = round(netto_kw, 3)

            if not werte:
                continue  # Keine Daten für diese Stunde

            stunden_mit_daten += 1

            # Leistungs-Spitzen aus W-Integration (nur für Peaks).
            netz_val = sum(werte.get(k, 0) for k in netz_keys)
            einspeisung_kw_h = abs(netz_val) if netz_val < 0 else 0.0
            netzbezug_kw_h = netz_val if netz_val > 0 else 0.0

            pv_kw_h = sum(v for k in pv_keys if (v := werte.get(k, 0)) > 0)
            for k, v in werte.items():
                if v is None or k in _sonderschluessel:
                    continue
                if v > 0:
                    pv_kw_h += v

            # kWh-Werte aus Zähler-Snapshots (Issue #135).
            # Fehlt der Zähler einer Kategorie, bleibt der Wert None.
            snap_h = kwh_pro_stunde_tag.get(h, {}) if kwh_pro_stunde_tag else {}
            pv_kw_final = snap_h.get("pv")
            einspeisung_kw_final = snap_h.get("einspeisung")
            netzbezug_kw_final = snap_h.get("netzbezug")
            verbrauch_kw_final = snap_h.get("verbrauch")
            waermepumpe_kw_final = snap_h.get("wp")
            wallbox_kw_final = snap_h.get("wallbox")
            batterie_kw_final = snap_h.get("batterie_netto")

            if pv_kw_final is not None and verbrauch_kw_final is not None:
                ueberschuss_h = max(0.0, pv_kw_final - verbrauch_kw_final)
                defizit_h = max(0.0, verbrauch_kw_final - pv_kw_final)
                tages_ueberschuss += ueberschuss_h
                tages_defizit += defizit_h
            else:
                ueberschuss_h = None
                defizit_h = None

            if pv_kw_final is not None:
                pv_ertrag_summe += pv_kw_final

            # Peaks bleiben W-basiert
            peak_pv = max(peak_pv, pv_kw_h)
            peak_bezug = max(peak_bezug, netzbezug_kw_h)
            peak_einspeisung = max(peak_einspeisung, einspeisung_kw_h)

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
                strahlung_summe += strahlung
            if gti is not None:
                gti_summe += gti

            soc = soc_stunden.get(h)
            if soc is not None:
                soc_values.append(soc)

            for komp_key, komp_kw in werte.items():
                komponenten_summen[komp_key] = komponenten_summen.get(komp_key, 0.0) + komp_kw

            pending_tep.append(TagesEnergieProfil(
                anlage_id=anlage.id,
                datum=current,
                stunde=h,
                pv_kw=round(pv_kw_final, 3) if pv_kw_final is not None else None,
                verbrauch_kw=round(verbrauch_kw_final, 3) if verbrauch_kw_final is not None else None,
                einspeisung_kw=round(einspeisung_kw_final, 3) if einspeisung_kw_final is not None else None,
                netzbezug_kw=round(netzbezug_kw_final, 3) if netzbezug_kw_final is not None else None,
                batterie_kw=round(batterie_kw_final, 3) if batterie_kw_final is not None else None,
                waermepumpe_kw=round(waermepumpe_kw_final, 3) if waermepumpe_kw_final is not None else None,
                wallbox_kw=round(wallbox_kw_final, 3) if wallbox_kw_final is not None else None,
                ueberschuss_kw=round(ueberschuss_h, 3) if ueberschuss_h is not None else None,
                defizit_kw=round(defizit_h, 3) if defizit_h is not None else None,
                temperatur_c=round(temperatur, 1) if temperatur is not None else None,
                globalstrahlung_wm2=round(strahlung, 0) if strahlung is not None else None,
                bewoelkung_prozent=round(bewoelkung, 0) if bewoelkung is not None else None,
                niederschlag_mm=round(niederschlag, 2) if niederschlag is not None else None,
                wetter_code=int(wcode) if wcode is not None else None,
                soc_prozent=round(soc, 1) if soc is not None else None,
                komponenten=werte if werte else None,
            ))
            stunden_count += 1

        if stunden_mit_daten == 0:
            skipped_no_data += 1
            current += timedelta(days=1)
            continue

        # Erst JETZT alte Daten löschen (nur wenn neue Daten vorhanden)
        # Prognose-Felder aus bestehendem Eintrag bewahren
        preserved_prognose = {}
        existing_tz = await db.execute(
            sa_select(TagesZusammenfassung).where(
                sa_and(
                    TagesZusammenfassung.anlage_id == anlage.id,
                    TagesZusammenfassung.datum == current,
                )
            )
        )
        existing_tz_row = existing_tz.scalar_one_or_none()
        if existing_tz_row:
            for field in ("pv_prognose_kwh", "sfml_prognose_kwh",
                           "solcast_prognose_kwh", "solcast_p10_kwh", "solcast_p90_kwh"):
                val = getattr(existing_tz_row, field, None)
                if val is not None:
                    preserved_prognose[field] = val

        await db.execute(
            sa_delete(TagesEnergieProfil).where(
                sa_and(
                    TagesEnergieProfil.anlage_id == anlage.id,
                    TagesEnergieProfil.datum == current,
                )
            )
        )
        await db.execute(
            sa_delete(TagesZusammenfassung).where(
                sa_and(
                    TagesZusammenfassung.anlage_id == anlage.id,
                    TagesZusammenfassung.datum == current,
                )
            )
        )

        # Gesammelte Stundendaten schreiben
        for tep in pending_tep:
            db.add(tep)

        # Batterie-Vollzyklen
        vollzyklen = None
        if len(soc_values) >= 2:
            delta_sum = sum(abs(soc_values[i] - soc_values[i - 1])
                            for i in range(1, len(soc_values)))
            vollzyklen = round(delta_sum / 200.0, 2)

        # Performance Ratio — GTI statt horizontaler GHI als Referenz (#139).
        performance_ratio = None
        kwp = anlage.leistung_kwp
        if kwp and kwp > 0 and gti_summe > 0:
            theoretisch_kwh = gti_summe * kwp / 1000
            if theoretisch_kwh > 0:
                performance_ratio = round(pv_ertrag_summe / theoretisch_kwh, 3)

        # Counter-Tagesdifferenzen (Issue #136) — Backfill via HA Statistics
        komponenten_starts: dict = {}
        try:
            from backend.services.sensor_snapshot_service import get_daily_counter_deltas_by_inv
            komponenten_starts = await get_daily_counter_deltas_by_inv(
                db, anlage, investitionen, current,
            )
        except Exception as e:
            logger.warning(
                f"Backfill (Statistics) Anlage {anlage.id}, {current}: Counter-Aggregation "
                f"fehlgeschlagen: {type(e).__name__}: {e}"
            )

        # Tagesgesamt pro Komponente aus Boundary-Diff (Etappe 3c P3, E2):
        # HA-konformes [Heute 00:00, Folgetag 00:00) statt Σ-Hourly über Backward-
        # Slots. Boundary-Werte überschreiben Σ-Hourly-Werte für übereinstimmende
        # Keys; Live-Σ bleibt nur für Keys ohne Counter-Mapping (z.B. WP-Suffix).
        try:
            from backend.services.snapshot.aggregator import get_komponenten_tageskwh
            boundary_kwh = await get_komponenten_tageskwh(
                db, anlage, investitionen, current,
            )
            for key, val in boundary_kwh.items():
                komponenten_summen[key] = val
        except Exception as e:
            logger.warning(
                f"Backfill (Statistics) Anlage {anlage.id}, {current}: "
                f"Komponenten-Tagesgesamt aus Snapshots fehlgeschlagen: "
                f"{type(e).__name__}: {e}"
            )

        tz_obj = TagesZusammenfassung(
            anlage_id=anlage.id,
            datum=current,
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
            datenquelle="ha_statistiken",
            komponenten_kwh=(
                {k: round(v, 2) for k, v in komponenten_summen.items()}
                if komponenten_summen else None
            ),
            komponenten_starts=komponenten_starts or None,
        )
        # Prognose-Felder aus gelöschtem Eintrag wiederherstellen
        for field, val in preserved_prognose.items():
            setattr(tz_obj, field, val)
        db.add(tz_obj)
        await db.flush()

        logger.info(
            f"Backfill (Statistics) Anlage {anlage.id}, {current}: "
            f"{stunden_count}h, PV={pv_ertrag_summe:.1f}kWh, PR={performance_ratio or '-'}"
        )
        count += 1
        current += timedelta(days=1)

    if skipped_no_data > 0:
        logger.info(
            f"Backfill Anlage {anlage.id}: {count} geschrieben, "
            f"{skipped_no_data} ohne HA-Daten übersprungen, "
            f"{skipped_existing} bereits vorhanden"
        )

    return {
        "geschrieben": count,
        "uebersprungen_keine_daten": skipped_no_data,
        "uebersprungen_existiert": skipped_existing,
    }


# ── Hilfsfunktionen ──────────────────────────────────────────────────────────

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

    Returns:
        {stunde: float (SoC %)}
    """
    from backend.core.config import HA_INTEGRATION_AVAILABLE
    from backend.models.investition import Investition

    if not HA_INTEGRATION_AVAILABLE:
        return {}

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

    soc_entities = []
    for key, val in sensor_mapping.get("investitionen", {}).items():
        if str(key) not in speicher_ids:
            continue
        if isinstance(val, dict) and val.get("live", {}).get("soc"):
            soc_entities.append(val["live"]["soc"])

    if not soc_entities:
        return {}

    try:
        from backend.services.ha_state_service import get_ha_state_service
        ha_service = get_ha_state_service()

        start = datetime.combine(datum, datetime.min.time())
        end = start + timedelta(days=1)

        history = await ha_service.get_sensor_history(soc_entities, start, end)

        # Stundenmittel berechnen (erstes SoC-Entity verwenden)
        result = {}
        for entity_id in soc_entities:
            points = history.get(entity_id, [])
            if not points:
                continue

            for h in range(24):
                h_start = start + timedelta(hours=h)
                h_end = h_start + timedelta(hours=1)
                h_points = [p[1] for p in points if h_start <= p[0] < h_end]
                if h_points and h not in result:
                    result[h] = sum(h_points) / len(h_points)

            break  # Erstes SoC-Entity reicht

        return result

    except Exception as e:
        logger.debug(f"SoC-History für {datum}: {e}")
        return {}


@dataclass
class StrompreisStunden:
    """Stündliche Strompreise aus zwei unabhängigen Quellen."""
    sensor: dict[int, float]   # Endpreis aus HA-Sensor (Tibber etc.), leer wenn kein Sensor
    boerse: dict[int, float]   # EPEX Day-Ahead Börsenpreis (aWATTar), immer befüllt


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
        try:
            from backend.core.config import HA_INTEGRATION_AVAILABLE
            if HA_INTEGRATION_AVAILABLE:
                from backend.services.ha_state_service import get_ha_state_service
                ha_service = get_ha_state_service()

                start = datetime.combine(datum, datetime.min.time())
                end = start + timedelta(days=1)
                history = await ha_service.get_sensor_history([sensor_id], start, end)
                units = await ha_service.get_sensor_units([sensor_id])

                points = history.get(sensor_id, [])
                if points:
                    unit = units.get(sensor_id, "")
                    faktor = 1.0
                    if unit in ("EUR/kWh", "€/kWh"):
                        faktor = 100.0
                    elif unit in ("EUR/MWh", "€/MWh"):
                        faktor = 0.1

                    for h in range(24):
                        h_start = start + timedelta(hours=h)
                        h_end = h_start + timedelta(hours=1)
                        h_pts = [p[1] * faktor for p in points if h_start <= p[0] < h_end]
                        if h_pts:
                            sensor_preise[h] = sum(h_pts) / len(h_pts)

                    if sensor_preise:
                        logger.debug("Strompreis %s: %d Stunden aus HA-Sensor %s",
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


BackfillStatus = Literal[
    "ok",
    "ha_unavailable",
    "no_sensors",
    "no_valid_sensors",
    "earliest_unknown",
    "empty_range",
]


@dataclass
class BackfillResult:
    """Ergebnis von resolve_and_backfill_from_statistics()."""
    status: BackfillStatus
    von: Optional[date] = None
    bis: Optional[date] = None
    verarbeitet: int = 0
    geschrieben: int = 0
    # #190 Bug B: Skip-Transparenz statt stillem 79,4%-Cap
    uebersprungen_keine_daten: int = 0
    uebersprungen_existiert: int = 0
    missing_eids: list[str] = None
    detail: str = ""

    def __post_init__(self):
        if self.missing_eids is None:
            self.missing_eids = []


async def resolve_and_backfill_from_statistics(
    anlage: Anlage,
    db: AsyncSession,
    *,
    von: Optional[date] = None,
    bis: Optional[date] = None,
) -> BackfillResult:
    """
    Orchestriert den additiven Vollbackfill aus HA Long-Term Statistics:

    - resolved Live-Sensoren der Anlage
    - filtert ungültige Sensor-IDs
    - ermittelt frühestes Datum aus HA Statistics (falls `von` None)
    - default `bis` = gestern
    - ruft backfill_from_statistics() mit dem ermittelten Zeitraum auf

    Wird vom manuellen Wizard-Endpoint und vom Auto-Vollbackfill im
    Monatsabschluss-Background-Task geteilt — gleiche Logik, unterschiedliche
    Fehlerbehandlung im Caller (HTTPException vs. Log). Bestehende Tage
    bleiben **immer** unverändert (#190).
    """
    from backend.services.ha_statistics_service import get_ha_statistics_service
    from backend.services.live_sensor_config import extract_live_config

    ha_service = get_ha_statistics_service()
    if not ha_service.is_available:
        return BackfillResult(status="ha_unavailable", detail="HA Statistics Datenbank nicht verfügbar")

    basis_live, inv_live_map, _, _ = extract_live_config(anlage)
    all_eids = list(set(
        list(basis_live.values()) +
        [eid for live in inv_live_map.values() for eid in live.values() if eid]
    ))
    if not all_eids:
        return BackfillResult(status="no_sensors", detail="Keine Live-Sensoren konfiguriert")

    valid_eids, missing_eids = await asyncio.to_thread(ha_service.filter_valid_sensor_ids, all_eids)
    if not valid_eids:
        return BackfillResult(
            status="no_valid_sensors",
            missing_eids=missing_eids,
            detail=(
                f"Keiner der konfigurierten Live-Sensoren wurde in der HA-Datenbank gefunden: "
                f"{all_eids}. Bitte Sensor-Zuordnung im Wizard prüfen und veraltete Sensoren entfernen."
            ),
        )

    if bis is None:
        bis = date.today() - timedelta(days=1)

    if von is None:
        try:
            verfuegbar = await asyncio.to_thread(ha_service.get_verfuegbare_monate, valid_eids)
            von = verfuegbar.erstes_datum
        except Exception as e:
            return BackfillResult(
                status="earliest_unknown",
                missing_eids=missing_eids,
                detail=f"Konnte frühestes Datum nicht ermitteln: {e}",
            )

    if von > bis:
        return BackfillResult(
            status="empty_range",
            von=von,
            bis=bis,
            missing_eids=missing_eids,
            detail=f"von ({von}) > bis ({bis})",
        )

    verarbeitet = (bis - von).days + 1
    stats = await backfill_from_statistics(anlage, von, bis, db)

    return BackfillResult(
        status="ok",
        von=von,
        bis=bis,
        verarbeitet=verarbeitet,
        geschrieben=stats["geschrieben"],
        uebersprungen_keine_daten=stats["uebersprungen_keine_daten"],
        uebersprungen_existiert=stats["uebersprungen_existiert"],
        missing_eids=missing_eids,
    )
