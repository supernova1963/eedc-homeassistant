"""
Backfill-Pfade (Etappe 3d P3 Refactoring-Tail).

Drei Funktionen extrahiert aus `services/energie_profil_service.py`:

- `backfill_range(anlage, von, bis, db)` ruft `aggregate_day` für einen
  Datumsbereich (Live-Sensoren via `live_power_service`).
- `backfill_from_statistics(anlage, von, bis, db)` baut Energieprofile
  additiv aus HA Long-Term Statistics auf — Schreib-Pfad auf
  `TagesZusammenfassung` + `TagesEnergieProfil`, im P3-Architektur-Commit
  unter Source `external:ha_statistics` an Provenance angeschlossen.
- `resolve_and_backfill_from_statistics(anlage, db, von, bis)` orchestriert
  den additiven Vollbackfill (resolve Live-Sensoren, ermittele Range).

`_get_wetter_ist` liegt in `backend.services.energie_profil._helpers` und
wird lazy importiert.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Literal, Optional

from sqlalchemy import and_ as sa_and
from sqlalchemy import delete as sa_delete
from sqlalchemy import select as sa_select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.anlage import Anlage
from backend.models.tages_energie_profil import TagesEnergieProfil, TagesZusammenfassung
from backend.services.energie_profil._provenance_helpers import (
    seed_tep_provenance,
    seed_tz_provenance,
)
from backend.services.energie_profil.aggregator import aggregate_day

logger = logging.getLogger(__name__)

# Backfill aus HA Long-Term Statistics ist eine externe autoritative
# Datenquelle (Source `external:ha_statistics`, Stufe 2). Manuelle Form-
# Werte (Stufe 1) gewinnen weiterhin; gegen Auto-Aggregation/Fallback/
# Legacy gewinnt der HA-Stats-Backfill.
_HA_STATS_SOURCE = "external:ha_statistics"
_HA_STATS_WRITER = "ha_statistics_backfill"


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
    from backend.models.investition import Investition
    from backend.utils.investition_filter import aktiv_im_zeitraum
    from backend.services.live_sensor_config import (
        SKIP_TYPEN,
        TV_SERIE_CONFIG,
        extract_live_config,
    )
    from backend.services.ha_statistics_service import get_ha_statistics_service
    from backend.services.energie_profil._helpers import _get_wetter_ist

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

        # Stunden-Counter (Issue #136 / Forum #259 detLAN): WP-Kompressor-Starts
        # pro Stunde. Im Backfill bisher nicht mit-aggregiert → Tagesdetail-
        # Tabelle zeigte leere wp_starts_anzahl-Spalten für nachgefüllte Tage.
        wp_starts_pro_stunde: dict[int, Optional[int]] = {}
        try:
            from backend.services.sensor_snapshot_service import get_hourly_counter_sum_by_feld
            wp_starts_pro_stunde = await get_hourly_counter_sum_by_feld(
                db, anlage, investitionen, current, "wp_starts_anzahl",
            )
        except Exception as e:
            logger.warning(
                f"Anlage {anlage.id}, {current}: WP-Starts-Aggregation "
                f"fehlgeschlagen: {type(e).__name__}: {e}"
            )

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
                wp_starts_anzahl=wp_starts_pro_stunde.get(h),
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

        # Gesammelte Stundendaten schreiben + Provenance setzen.
        # delete+insert oben hat eventuelle bestehende Provenance entfernt;
        # wir markieren die neuen Rows mit `external:ha_statistics`.
        for tep in pending_tep:
            db.add(tep)
            seed_tep_provenance(tep, source=_HA_STATS_SOURCE, writer=_HA_STATS_WRITER)

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
        seed_tz_provenance(tz_obj, source=_HA_STATS_SOURCE, writer=_HA_STATS_WRITER)
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
