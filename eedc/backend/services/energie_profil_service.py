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

import logging
from datetime import date, datetime, timedelta
from typing import Optional

from sqlalchemy import select, delete, and_, func
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.database import get_session
from backend.models.anlage import Anlage
from backend.models.monatsdaten import Monatsdaten
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
    from backend.services.live_power_service import get_live_power_service

    service = get_live_power_service()

    # Sensor-Mapping prüfen
    sensor_mapping = anlage.sensor_mapping or {}
    basis_live = sensor_mapping.get("basis", {}).get("live", {})
    has_inv_live = any(
        isinstance(v, dict) and v.get("live")
        for v in sensor_mapping.get("investitionen", {}).values()
    )

    if not basis_live and not has_inv_live:
        logger.debug(f"Anlage {anlage.id}: Keine Live-Sensoren konfiguriert")
        return None

    # ── Tagesverlauf-Daten holen ──────────────────────────────────────────
    try:
        tv_data = await service.get_tagesverlauf(
            anlage, db, tage_zurueck=_tage_zurueck(datum),
        )
    except Exception as e:
        logger.warning(f"Anlage {anlage.id}, {datum}: Tagesverlauf-Fehler: {type(e).__name__}: {e}")
        return None

    serien = tv_data.get("serien", [])
    punkte_raw = tv_data.get("punkte", [])

    if not punkte_raw:
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
    # Alle Schlüssel die separat behandelt werden (nicht in generischer Summe)
    _sonderschluessel = batterie_keys | v2h_keys | netz_keys | pv_keys | wp_keys | wallbox_keys

    # ── Wetter-IST-Daten holen ────────────────────────────────────────────
    wetter_stunden = await _get_wetter_ist(anlage, datum)

    # ── SoC-History holen ─────────────────────────────────────────────────
    soc_stunden = await _get_soc_history(anlage, sensor_mapping, datum)

    # ── Alte Daten für diesen Tag löschen (Upsert) ────────────────────────
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
    soc_values = []
    stunden_count = 0
    komponenten_summen: dict[str, float] = {}  # Per-Komponenten Tages-kWh

    for punkt in punkte:
        h = int(punkt["zeit"].split(":")[0])
        werte = punkt.get("werte", {})

        # Netz (Einspeisung/Netzbezug)
        netz_val = sum(werte.get(k, 0) for k in netz_keys)
        einspeisung_kw = abs(netz_val) if netz_val < 0 else 0.0
        netzbezug_kw = netz_val if netz_val > 0 else 0.0

        # Batterie: alle Speicher + V2H (vorzeichenbehaftet: positiv=Entladung, negativ=Ladung)
        batterie_kw = (
            sum(werte.get(k, 0) for k in batterie_keys) +
            sum(werte.get(k, 0) for k in v2h_keys)
        )

        # WP + Wallbox separat (Absolutwert, nur wenn negativ = Senke)
        waermepumpe_kw = sum(abs(werte.get(k, 0)) for k in wp_keys
                             if (werte.get(k) or 0) < 0)
        wallbox_kw = sum(abs(werte.get(k, 0)) for k in wallbox_keys
                         if (werte.get(k) or 0) < 0)

        # PV + Verbrauch: vorzeichenbasiert über alle übrigen Schlüssel
        # positiv = lokaler Erzeuger (PV, BKW, BHKW, Sonstiges-Erzeuger)
        # negativ = Verbraucher (Haushalt, Sonstiges-Verbraucher, WP, Wallbox)
        pv_kw = sum(v for k in pv_keys
                    if (v := werte.get(k, 0)) > 0)
        verbrauch_kw = waermepumpe_kw + wallbox_kw
        for k, v in werte.items():
            if v is None or k in _sonderschluessel:
                continue
            if v > 0:
                pv_kw += v       # BHKW, Sonstiges-Erzeuger → lokale Erzeugung
            elif v < 0:
                verbrauch_kw += abs(v)  # Haushalt, Sonstiges-Verbraucher

        # Bilanz: PV vs. Verbrauch
        ueberschuss = max(0, pv_kw - verbrauch_kw)
        defizit = max(0, verbrauch_kw - pv_kw)

        tages_ueberschuss += ueberschuss  # kW × 1h = kWh
        tages_defizit += defizit
        pv_ertrag_summe += pv_kw

        # Peaks
        peak_pv = max(peak_pv, pv_kw)
        peak_bezug = max(peak_bezug, netzbezug_kw)
        peak_einspeisung = max(peak_einspeisung, einspeisung_kw)

        # Wetter
        temperatur = wetter_stunden.get(h, {}).get("temperatur_c")
        strahlung = wetter_stunden.get(h, {}).get("globalstrahlung_wm2")
        if temperatur is not None:
            temp_values.append(temperatur)
        if strahlung is not None:
            strahlung_summe += strahlung  # W/m² × 1h = Wh/m²

        # SoC
        soc = soc_stunden.get(h)
        if soc is not None:
            soc_values.append(soc)

        # Per-Komponenten kWh akkumulieren (kW × 1h = kWh)
        if werte:
            for komp_key, komp_kw in werte.items():
                if komp_kw is not None:
                    komponenten_summen[komp_key] = komponenten_summen.get(komp_key, 0.0) + komp_kw

        # TagesEnergieProfil speichern
        profil = TagesEnergieProfil(
            anlage_id=anlage.id,
            datum=datum,
            stunde=h,
            pv_kw=round(pv_kw, 3) if pv_kw else None,
            verbrauch_kw=round(verbrauch_kw, 3) if verbrauch_kw else None,
            einspeisung_kw=round(einspeisung_kw, 3) if einspeisung_kw else None,
            netzbezug_kw=round(netzbezug_kw, 3) if netzbezug_kw else None,
            batterie_kw=round(batterie_kw, 3) if batterie_kw else None,
            waermepumpe_kw=round(waermepumpe_kw, 3) if waermepumpe_kw else None,
            wallbox_kw=round(wallbox_kw, 3) if wallbox_kw else None,
            ueberschuss_kw=round(ueberschuss, 3) if ueberschuss else None,
            defizit_kw=round(defizit, 3) if defizit else None,
            temperatur_c=round(temperatur, 1) if temperatur is not None else None,
            globalstrahlung_wm2=round(strahlung, 0) if strahlung is not None else None,
            soc_prozent=round(soc, 1) if soc is not None else None,
            komponenten=werte if werte else None,
        )
        db.add(profil)
        stunden_count += 1

    # ── Batterie-Vollzyklen berechnen ─────────────────────────────────────
    vollzyklen = None
    if len(soc_values) >= 2:
        delta_sum = sum(abs(soc_values[i] - soc_values[i - 1])
                        for i in range(1, len(soc_values)))
        # Ein Vollzyklus = ΔSoC von 100% (0→100→0 = 200% ΔSoC → 1 Zyklus)
        vollzyklen = round(delta_sum / 200.0, 2)

    # ── Performance Ratio ─────────────────────────────────────────────────
    performance_ratio = None
    kwp = anlage.leistung_kwp
    if kwp and kwp > 0 and strahlung_summe > 0:
        # Theoretischer Ertrag bei gemessener Strahlung
        theoretisch_kwh = strahlung_summe * kwp / 1000  # Wh/m² × kWp / 1000
        if theoretisch_kwh > 0:
            performance_ratio = round(pv_ertrag_summe / theoretisch_kwh, 3)

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
        komponenten_kwh=(
            {k: round(v, 2) for k, v in komponenten_summen.items()}
            if komponenten_summen else None
        ),
    )
    db.add(zusammenfassung)
    await db.flush()

    logger.info(
        f"Anlage {anlage.id}, {datum}: {stunden_count}h aggregiert, "
        f"Überschuss={tages_ueberschuss:.1f}kWh, Defizit={tages_defizit:.1f}kWh, "
        f"PR={performance_ratio or '-'}"
    )

    return zusammenfassung


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
    skip_existing: bool = True,
) -> int:
    """
    Rückwirkende Berechnung des Energieprofils aus HA Long-Term Statistics.

    Ermöglicht Befüllung der gesamten HA-History (Jahre) ohne die ~10-Tage-
    Grenze der HA-Sensor-History. Nutzt den statistics-Stundenmittelwert (mean)
    aller konfigurierten Live-Leistungssensoren.

    Args:
        anlage: Die Anlage
        von/bis: Datumsbereich (inklusiv)
        db: DB-Session
        skip_existing: Bereits vorhandene Tage überspringen

    Returns:
        Anzahl erfolgreich geschriebener Tage
    """
    import asyncio
    from sqlalchemy import select as sa_select, delete as sa_delete, and_ as sa_and

    from backend.models.investition import Investition
    from backend.utils.investition_filter import aktiv_jetzt
    from backend.services.live_sensor_config import (
        extract_live_config,
        TV_SERIE_CONFIG,
        SKIP_TYPEN,
    )
    from backend.services.ha_statistics_service import get_ha_statistics_service

    # Investitionen laden
    inv_result = await db.execute(
        sa_select(Investition).where(
            Investition.anlage_id == anlage.id,
            aktiv_jetzt(),
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
                        serien.append({"key": key, "kategorie": config["kategorie"],
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
        serien.append({"key": serie_key, "kategorie": config["kategorie"],
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

    # SoC-Entities
    soc_entity: Optional[str] = None
    for inv_id, live in inv_live_map.items():
        if live.get("soc"):
            soc_entity = live["soc"]
            all_entity_ids.add(soc_entity)
            break  # Erstes SoC-Entity reicht

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
    _sonderschluessel = batterie_keys | v2h_keys | netz_keys | pv_keys | wp_keys | wallbox_keys

    # ── Bestehende Tage ermitteln ────────────────────────────────────────────
    existing_dates: set[date] = set()
    if skip_existing:
        ex_result = await db.execute(
            sa_select(TagesZusammenfassung.datum).where(
                sa_and(
                    TagesZusammenfassung.anlage_id == anlage.id,
                    TagesZusammenfassung.datum >= von,
                    TagesZusammenfassung.datum <= bis,
                )
            )
        )
        existing_dates = {row[0] for row in ex_result}

    # ── Pro-Tag-Schleife ─────────────────────────────────────────────────────
    count = 0
    current = von
    while current <= bis:
        if current in existing_dates:
            current += timedelta(days=1)
            continue

        datum_iso = current.isoformat()

        # Wetter-IST-Daten für diesen Tag
        wetter_stunden = await _get_wetter_ist(anlage, current)

        # SoC-Werte für diesen Tag
        soc_stunden: dict[int, float] = {}
        if soc_entity and soc_entity in hourly_data:
            soc_stunden = hourly_data[soc_entity].get(datum_iso, {})

        # Stundenschleife: werte-Dict aufbauen (Butterfly-Konvention)
        tages_ueberschuss = 0.0
        tages_defizit = 0.0
        peak_pv = 0.0
        peak_bezug = 0.0
        peak_einspeisung = 0.0
        temp_values: list[float] = []
        strahlung_summe = 0.0
        pv_ertrag_summe = 0.0
        soc_values: list[float] = []
        stunden_count = 0
        komponenten_summen: dict[str, float] = {}

        # Alte Daten für diesen Tag löschen (Upsert)
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

        stunden_mit_daten = 0
        for h in range(24):
            # werte-Dict aus Statistics aufbauen (spiegelt live_tagesverlauf_service.py)
            werte: dict[str, float] = {}

            for serie in serien:
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

            # Aggregation (identisch zu aggregate_day Zeilen 160–222)
            netz_val = sum(werte.get(k, 0) for k in netz_keys)
            einspeisung_kw_h = abs(netz_val) if netz_val < 0 else 0.0
            netzbezug_kw_h = netz_val if netz_val > 0 else 0.0

            batterie_kw_h = (
                sum(werte.get(k, 0) for k in batterie_keys) +
                sum(werte.get(k, 0) for k in v2h_keys)
            )

            waermepumpe_kw_h = sum(abs(werte.get(k, 0)) for k in wp_keys
                                   if (werte.get(k) or 0) < 0)
            wallbox_kw_h = sum(abs(werte.get(k, 0)) for k in wallbox_keys
                               if (werte.get(k) or 0) < 0)

            pv_kw_h = sum(v for k in pv_keys if (v := werte.get(k, 0)) > 0)
            verbrauch_kw_h = waermepumpe_kw_h + wallbox_kw_h
            for k, v in werte.items():
                if v is None or k in _sonderschluessel:
                    continue
                if v > 0:
                    pv_kw_h += v
                elif v < 0:
                    verbrauch_kw_h += abs(v)

            ueberschuss_h = max(0, pv_kw_h - verbrauch_kw_h)
            defizit_h = max(0, verbrauch_kw_h - pv_kw_h)

            tages_ueberschuss += ueberschuss_h
            tages_defizit += defizit_h
            pv_ertrag_summe += pv_kw_h

            peak_pv = max(peak_pv, pv_kw_h)
            peak_bezug = max(peak_bezug, netzbezug_kw_h)
            peak_einspeisung = max(peak_einspeisung, einspeisung_kw_h)

            temperatur = wetter_stunden.get(h, {}).get("temperatur_c")
            strahlung = wetter_stunden.get(h, {}).get("globalstrahlung_wm2")
            if temperatur is not None:
                temp_values.append(temperatur)
            if strahlung is not None:
                strahlung_summe += strahlung

            soc = soc_stunden.get(h)
            if soc is not None:
                soc_values.append(soc)

            for komp_key, komp_kw in werte.items():
                komponenten_summen[komp_key] = komponenten_summen.get(komp_key, 0.0) + komp_kw

            db.add(TagesEnergieProfil(
                anlage_id=anlage.id,
                datum=current,
                stunde=h,
                pv_kw=round(pv_kw_h, 3) if pv_kw_h else None,
                verbrauch_kw=round(verbrauch_kw_h, 3) if verbrauch_kw_h else None,
                einspeisung_kw=round(einspeisung_kw_h, 3) if einspeisung_kw_h else None,
                netzbezug_kw=round(netzbezug_kw_h, 3) if netzbezug_kw_h else None,
                batterie_kw=round(batterie_kw_h, 3) if batterie_kw_h else None,
                waermepumpe_kw=round(waermepumpe_kw_h, 3) if waermepumpe_kw_h else None,
                wallbox_kw=round(wallbox_kw_h, 3) if wallbox_kw_h else None,
                ueberschuss_kw=round(ueberschuss_h, 3) if ueberschuss_h else None,
                defizit_kw=round(defizit_h, 3) if defizit_h else None,
                temperatur_c=round(temperatur, 1) if temperatur is not None else None,
                globalstrahlung_wm2=round(strahlung, 0) if strahlung is not None else None,
                soc_prozent=round(soc, 1) if soc is not None else None,
                komponenten=werte if werte else None,
            ))
            stunden_count += 1

        if stunden_mit_daten == 0:
            current += timedelta(days=1)
            continue

        # Batterie-Vollzyklen
        vollzyklen = None
        if len(soc_values) >= 2:
            delta_sum = sum(abs(soc_values[i] - soc_values[i - 1])
                            for i in range(1, len(soc_values)))
            vollzyklen = round(delta_sum / 200.0, 2)

        # Performance Ratio
        performance_ratio = None
        kwp = anlage.leistung_kwp
        if kwp and kwp > 0 and strahlung_summe > 0:
            theoretisch_kwh = strahlung_summe * kwp / 1000
            if theoretisch_kwh > 0:
                performance_ratio = round(pv_ertrag_summe / theoretisch_kwh, 3)

        db.add(TagesZusammenfassung(
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
        ))
        await db.flush()

        logger.info(
            f"Backfill (Statistics) Anlage {anlage.id}, {current}: "
            f"{stunden_count}h, PV={pv_ertrag_summe:.1f}kWh, PR={performance_ratio or '-'}"
        )
        count += 1
        current += timedelta(days=1)

    return count


# ── Hilfsfunktionen ──────────────────────────────────────────────────────────

def _tage_zurueck(datum: date) -> int:
    """Berechnet tage_zurueck Parameter für get_tagesverlauf()."""
    return (date.today() - datum).days


async def _get_wetter_ist(anlage: Anlage, datum: date) -> dict:
    """
    Holt Wetter-IST-Daten für einen Tag (Open-Meteo Historical).

    Returns:
        {stunde: {"temperatur_c": float, "globalstrahlung_wm2": float}}
    """
    if not anlage.latitude or not anlage.longitude:
        return {}

    try:
        import httpx
        from backend.core.config import settings

        params = {
            "latitude": anlage.latitude,
            "longitude": anlage.longitude,
            "hourly": "temperature_2m,shortwave_radiation",
            "timezone": "Europe/Berlin",
        }

        # Für den heutigen Tag: Forecast-API, sonst Historical
        if datum == date.today():
            url = f"{settings.open_meteo_api_url}/forecast"
            params["forecast_days"] = 1
        else:
            url = "https://archive-api.open-meteo.com/v1/archive"
            params["start_date"] = datum.isoformat()
            params["end_date"] = datum.isoformat()

        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url, params=params)
            resp.raise_for_status()
            data = resp.json()

        hourly = data.get("hourly", {})
        times = hourly.get("time", [])
        temps = hourly.get("temperature_2m", [])
        strahlung = hourly.get("shortwave_radiation", [])

        result = {}
        for i, t in enumerate(times):
            h = int(t[11:13])
            result[h] = {
                "temperatur_c": temps[i] if i < len(temps) else None,
                "globalstrahlung_wm2": strahlung[i] if i < len(strahlung) else None,
            }

        return result

    except Exception as e:
        logger.debug(f"Wetter-IST für {datum}: {e}")
        return {}


async def _get_soc_history(
    anlage: Anlage,
    sensor_mapping: dict,
    datum: date,
) -> dict:
    """
    Holt Batterie-SoC History für einen Tag.

    Returns:
        {stunde: float (SoC %)}
    """
    from backend.core.config import HA_INTEGRATION_AVAILABLE

    if not HA_INTEGRATION_AVAILABLE:
        return {}

    # SoC-Entity-IDs aus sensor_mapping sammeln
    soc_entities = []
    for key, val in sensor_mapping.get("investitionen", {}).items():
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
