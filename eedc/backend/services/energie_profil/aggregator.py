"""
Tag-Aggregator (Etappe 3c P3 Refactoring-Tail).

Aggregiert Energiedaten eines Tages und persistiert sie in 24 Zeilen
TagesEnergieProfil + 1 TagesZusammenfassung. Wird vom Scheduler täglich
für den Vortag, vom Reaggregat-Endpoint manuell und vom Vollbackfill
historisch aufgerufen.

Helper bleiben in `backend.services.energie_profil_service` (`_tage_zurueck`,
`_get_wetter_ist`, `_get_soc_history`, `_get_strompreis_stunden`) und werden
hier lazy importiert, weil das alte Modul gleichzeitig `aggregate_day`
re-exportiert (zirkulärer Top-Level-Import vermieden).
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from typing import Optional

from sqlalchemy import and_, delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.anlage import Anlage
from backend.models.investition import Investition
from backend.models.tages_energie_profil import TagesEnergieProfil, TagesZusammenfassung

logger = logging.getLogger(__name__)


async def aggregate_day(
    anlage: Anlage,
    datum: date,
    db: AsyncSession,
    datenquelle: str = "scheduler",
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
        datenquelle: "scheduler", "monatsabschluss", "manuell"

    Returns:
        TagesZusammenfassung oder None bei Fehler
    """
    # Lazy imports — vermeiden zirkulären Top-Level-Import zu energie_profil_service,
    # das diesen aggregator gleichzeitig re-exportiert.
    from backend.services.energie_profil_service import (
        _get_soc_history,
        _get_strompreis_stunden,
        _get_wetter_ist,
        _tage_zurueck,
    )
    from backend.services.live_power_service import get_live_power_service

    service = get_live_power_service()

    # Sensor-Mapping prüfen
    sensor_mapping = anlage.sensor_mapping or {}
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

    # ── Tagesverlauf-Daten holen ──────────────────────────────────────────
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
    if not punkte_raw and has_mqtt_energy:
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
    pv_module_result = await db.execute(
        select(Investition).where(
            and_(
                Investition.anlage_id == anlage.id,
                Investition.typ.in_(("pv-module", "balkonkraftwerk")),
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

    # ── Zähler-basierte Stunden-kWh (Issue #135) ─────────────────────────
    # Stunden-kWh werden aus kumulativen Snapshot-Deltas berechnet.
    # Fehlt der Zähler einer Kategorie, bleibt der Wert None (kein W-Fallback).
    kwh_pro_stunde: dict[int, dict[str, Optional[float]]] = {}
    try:
        from backend.services.sensor_snapshot_service import get_hourly_kwh_by_category
        inv_result = await db.execute(
            select(Investition).where(Investition.anlage_id == anlage.id)
        )
        invs = inv_result.scalars().all()
        invs_by_id = {str(inv.id): inv for inv in invs}
        kwh_pro_stunde = await get_hourly_kwh_by_category(
            db, anlage, invs_by_id, datum,
        )
    except Exception as e:
        logger.warning(
            f"Anlage {anlage.id}, {datum}: Zähler-Snapshot-Pfad fehlgeschlagen: "
            f"{type(e).__name__}: {e}"
        )
        kwh_pro_stunde = {}

    # ── Stunden-Counter (Issue #136: WP-Starts pro Stunde) ────────────────
    wp_starts_pro_stunde: dict[int, Optional[int]] = {}
    try:
        from backend.services.sensor_snapshot_service import get_hourly_counter_sum_by_feld
        wp_starts_pro_stunde = await get_hourly_counter_sum_by_feld(
            db, anlage, invs_by_id, datum, "wp_starts_anzahl",
        )
    except Exception as e:
        logger.warning(
            f"Anlage {anlage.id}, {datum}: WP-Starts-Stunden-Aggregation fehlgeschlagen: "
            f"{type(e).__name__}: {e}"
        )

    # ── Alte Daten für diesen Tag löschen (Upsert) ────────────────────────
    # Prognose-Felder aus bestehender TagesZusammenfassung retten,
    # da diese asynchron vom Wetter-Endpoint geschrieben werden.
    existing_tz = await db.execute(
        select(TagesZusammenfassung).where(
            and_(
                TagesZusammenfassung.anlage_id == anlage.id,
                TagesZusammenfassung.datum == datum,
            )
        )
    )
    existing_tz_row = existing_tz.scalar_one_or_none()
    preserved_prognose = {}
    if existing_tz_row:
        for field in ("pv_prognose_kwh", "sfml_prognose_kwh",
                       "solcast_prognose_kwh", "solcast_p10_kwh", "solcast_p90_kwh"):
            val = getattr(existing_tz_row, field, None)
            if val is not None:
                preserved_prognose[field] = val

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

        # Per-Komponenten kWh akkumulieren (kW × 1h = kWh)
        # strompreis ist kein Energiefluss → ausschließen
        if werte:
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
        )
        db.add(profil)
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

    # ── Counter-Tagesdifferenzen (Issue #136: WP-Kompressor-Starts) ──────
    # Werte aus reinen Counter-Sensoren (KUMULATIVE_COUNTER_FELDER), die NICHT
    # in die Energie-Bilanz fließen, sondern als KPI pro Tag gespeichert werden.
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

    # ── Tagesgesamt pro Komponente aus Boundary-Diff (Etappe 3c P3, E2) ──
    # HA-konformes Tagesfenster [Heute 00:00, Folgetag 00:00) statt Σ-Hourly
    # über Backward-Slots (Vortag 23 → Heute 23 = um eine Stunde verschoben).
    # Boundary-Werte überschreiben Live-Σ-Werte für übereinstimmende Keys —
    # Live-Σ bleibt nur für Keys, die der Helper nicht abdeckt (z.B. WP-Suffix
    # `waermepumpe_<id>_heizen` aus Live ohne separates heizenergie_kwh-Mapping).
    try:
        from backend.services.snapshot.aggregator import get_komponenten_tageskwh
        boundary_kwh = await get_komponenten_tageskwh(
            db, anlage, invs_by_id, datum,
        )
        for key, val in boundary_kwh.items():
            komponenten_summen[key] = val
    except Exception as e:
        logger.warning(
            f"Anlage {anlage.id}, {datum}: Komponenten-Tagesgesamt aus Snapshots "
            f"fehlgeschlagen, Σ-Hourly-Fallback aktiv: {type(e).__name__}: {e}"
        )

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
        datenquelle=datenquelle,
        boersenpreis_avg_cent=boersenpreis_avg,
        boersenpreis_min_cent=boersenpreis_min,
        negative_preis_stunden=neg_stunden,
        einspeisung_neg_preis_kwh=einsp_neg_kwh,
        komponenten_kwh=(
            {k: round(v, 2) for k, v in komponenten_summen.items()}
            if komponenten_summen else None
        ),
        komponenten_starts=komponenten_starts or None,
    )
    # Gerettete Prognose-Felder wiederherstellen
    for field, val in preserved_prognose.items():
        setattr(zusammenfassung, field, val)

    db.add(zusammenfassung)
    await db.flush()

    logger.info(
        f"Anlage {anlage.id}, {datum}: {stunden_count}h aggregiert, "
        f"Überschuss={tages_ueberschuss:.1f}kWh, Defizit={tages_defizit:.1f}kWh, "
        f"PR={performance_ratio or '-'}"
    )

    return zusammenfassung
