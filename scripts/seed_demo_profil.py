#!/usr/bin/env python3
"""
Demo-Seed: Generiert realistische TagesEnergieProfil + TagesZusammenfassung
für lokale Testumgebungen (ohne echte HA-History).

Verwendung:
  cd /home/gernot/claude/eedc-homeassistant/eedc
  python ../scripts/seed_demo_profil.py [--anlage-id 1] [--tage 60]

Muster:
  PV       — Sinuskurve über Sonnenstunden, saisonbereinigt, mit zufälligem Tagesfaktor
  Verbrauch — Grundlast + Morgen/Abendspitze (Haushalt) + WP tagsüber
  Batterie  — lädt bei PV-Überschuss, entlädt abends (10 kWh Kapazität simuliert)
  Netz      — Differenz (Bezug bei Defizit, Einspeisung bei Überschuss)
  Wetter    — saisonale Temperatur + Globalstrahlung korreliert mit PV
"""

import argparse
import math
import random
import sqlite3
import sys
from datetime import date, timedelta
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "eedc" / "data" / "eedc.db"

# Batterie-Simulation (kWh)
BATTERIE_KAPAZITAET = 10.0
BATTERIE_SOC_START = 20.0  # % am Morgen


def pv_kw(stunde: int, kwp: float, tag_im_jahr: int, tages_faktor: float) -> float:
    """Sinusförmiger PV-Ertrag. Saisonbereinigt (Sommer mehr, Winter weniger)."""
    # Sonnenstunden: 8-18 Uhr (Sommer) bis 10-16 Uhr (Winter)
    saison = 0.5 + 0.5 * math.sin(2 * math.pi * (tag_im_jahr - 80) / 365)
    sunrise = 10 - 2 * saison   # 10 Uhr (Winter) bis 8 Uhr (Sommer)
    sunset = 16 + 2 * saison    # 16 Uhr (Winter) bis 18 Uhr (Sommer)
    if stunde <= sunrise or stunde >= sunset:
        return 0.0
    winkel = math.pi * (stunde - sunrise) / (sunset - sunrise)
    # Maximale Ausbeute: 80% des kWp im Sommer, 30% im Winter
    max_faktor = 0.30 + 0.50 * saison
    return round(kwp * max_faktor * math.sin(winkel) * tages_faktor, 3)


def verbrauch_kw(stunde: int, hat_wp: bool, tages_faktor_v: float) -> float:
    """Haushaltslast + optional Wärmepumpe."""
    # Grundlast + Morgenspitze (7-9) + Abendspitze (17-22)
    basis = 0.25
    if 7 <= stunde <= 8:
        basis += 0.8
    elif stunde == 9:
        basis += 0.4
    elif 17 <= stunde <= 21:
        basis += 0.6
    elif stunde == 22:
        basis += 0.3
    basis *= tages_faktor_v
    wp = 0.0
    if hat_wp and 8 <= stunde <= 16:
        wp = 1.2 * tages_faktor_v  # WP tagsüber (nutzt PV-Überschuss)
    return round(basis + wp, 3)


def temperatur(stunde: int, tag_im_jahr: int) -> float:
    """Realistische Tagestemperatur (saisonal + tagesgang)."""
    saison_basis = 8 + 12 * math.sin(2 * math.pi * (tag_im_jahr - 80) / 365)
    tagesgang = -3 * math.cos(2 * math.pi * stunde / 24)
    return round(saison_basis + tagesgang + random.uniform(-1, 1), 1)


def globalstrahlung(stunde: int, pv: float, kwp: float) -> float:
    """Grobe Ableitung aus PV-Ertrag (W/m²)."""
    if kwp <= 0 or pv <= 0:
        return 0.0
    # Annahme: 1000 W/m² → 100% Ausbeute bei idealer Ausrichtung
    return round(pv / kwp * 1000 * 1.1 + random.uniform(-20, 20), 0)


def seed_anlage(conn: sqlite3.Connection, anlage_id: int, kwp: float,
                hat_wp: bool, tage: int) -> None:
    heute = date.today()
    gestern = heute - timedelta(days=1)

    inserted_tep = 0
    inserted_tz = 0

    for tage_zurueck in range(tage, 0, -1):
        tag = gestern - timedelta(days=tage_zurueck - 1)
        tag_im_jahr = tag.timetuple().tm_yday

        # Tages-Zufallsfaktoren (simuliert Bewölkung)
        tages_faktor_pv = random.uniform(0.3, 1.0)   # Sonniger bis bewölkter Tag
        tages_faktor_v = random.uniform(0.85, 1.15)  # Verbrauchsschwankung

        soc = BATTERIE_SOC_START
        stunden_daten = []

        for stunde in range(24):
            pv = pv_kw(stunde, kwp, tag_im_jahr, tages_faktor_pv)
            v = verbrauch_kw(stunde, hat_wp, tages_faktor_v)
            temp = temperatur(stunde, tag_im_jahr)
            strahlung = globalstrahlung(stunde, pv, kwp)

            # Batterie-Simulation
            ueberschuss_roh = pv - v
            batterie_kw = 0.0
            if ueberschuss_roh > 0 and soc < 95:
                lade_kw = min(ueberschuss_roh, BATTERIE_KAPAZITAET * 0.5)
                batterie_kw = -lade_kw  # negativ = Laden (Senke)
                soc = min(100, soc + lade_kw / BATTERIE_KAPAZITAET * 100)
            elif ueberschuss_roh < 0 and soc > 10:
                entlade_kw = min(abs(ueberschuss_roh), BATTERIE_KAPAZITAET * 0.5)
                entlade_kw = min(entlade_kw, (soc - 10) / 100 * BATTERIE_KAPAZITAET)
                batterie_kw = entlade_kw   # positiv = Entladung (Quelle)
                soc = max(10, soc - entlade_kw / BATTERIE_KAPAZITAET * 100)

            bilanz = pv + batterie_kw - v
            einspeisung = max(0.0, bilanz)
            netzbezug = max(0.0, -bilanz)
            ueberschuss = max(0.0, pv - v)
            defizit = max(0.0, v - pv)

            stunden_daten.append({
                "stunde": stunde,
                "pv_kw": pv,
                "verbrauch_kw": v,
                "einspeisung_kw": round(einspeisung, 3),
                "netzbezug_kw": round(netzbezug, 3),
                "batterie_kw": round(batterie_kw, 3),
                "waermepumpe_kw": round(1.2 * tages_faktor_v, 3) if hat_wp and 8 <= stunde <= 16 else None,
                "wallbox_kw": None,
                "ueberschuss_kw": round(ueberschuss, 3),
                "defizit_kw": round(defizit, 3),
                "temperatur_c": temp,
                "globalstrahlung_wm2": strahlung,
                "soc_prozent": round(soc, 1),
            })

        # TagesEnergieProfil schreiben (upsert via INSERT OR REPLACE)
        for d in stunden_daten:
            conn.execute("""
                INSERT OR REPLACE INTO tages_energie_profil
                  (anlage_id, datum, stunde, pv_kw, verbrauch_kw,
                   einspeisung_kw, netzbezug_kw, batterie_kw,
                   waermepumpe_kw, wallbox_kw, ueberschuss_kw, defizit_kw,
                   temperatur_c, globalstrahlung_wm2, soc_prozent, created_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,datetime('now'))
            """, (
                anlage_id, tag.isoformat(), d["stunde"],
                d["pv_kw"], d["verbrauch_kw"],
                d["einspeisung_kw"], d["netzbezug_kw"], d["batterie_kw"],
                d["waermepumpe_kw"], d["wallbox_kw"],
                d["ueberschuss_kw"], d["defizit_kw"],
                d["temperatur_c"], d["globalstrahlung_wm2"], d["soc_prozent"],
            ))
            inserted_tep += 1

        # TagesZusammenfassung berechnen
        pv_kwh = sum(d["pv_kw"] for d in stunden_daten)
        ueberschuss_kwh = sum(d["ueberschuss_kw"] for d in stunden_daten)
        defizit_kwh = sum(d["defizit_kw"] for d in stunden_daten)
        peak_pv = max((d["pv_kw"] for d in stunden_daten), default=0)
        peak_netz = max((d["netzbezug_kw"] for d in stunden_daten), default=0)
        peak_einsp = max((d["einspeisung_kw"] for d in stunden_daten), default=0)
        temp_min = min(d["temperatur_c"] for d in stunden_daten)
        temp_max = max(d["temperatur_c"] for d in stunden_daten)
        strahlung_sum = sum(d["globalstrahlung_wm2"] for d in stunden_daten)
        pr = (pv_kwh / (strahlung_sum / 1000 * kwp)) if strahlung_sum > 0 and kwp > 0 else None

        conn.execute("""
            INSERT OR REPLACE INTO tages_zusammenfassung
              (anlage_id, datum, ueberschuss_kwh, defizit_kwh,
               peak_pv_kw, peak_netzbezug_kw, peak_einspeisung_kw,
               temperatur_min_c, temperatur_max_c, strahlung_summe_wh_m2,
               performance_ratio, stunden_verfuegbar, datenquelle,
               created_at, updated_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,24,'seed',datetime('now'),datetime('now'))
        """, (
            anlage_id, tag.isoformat(),
            round(ueberschuss_kwh, 2), round(defizit_kwh, 2),
            round(peak_pv, 2), round(peak_netz, 2), round(peak_einsp, 2),
            temp_min, temp_max, round(strahlung_sum, 0),
            round(pr, 3) if pr else None,
        ))
        inserted_tz += 1

    conn.commit()
    print(f"  Anlage {anlage_id}: {inserted_tep} Stundenwerte + {inserted_tz} Tagessummen geschrieben")


def main():
    parser = argparse.ArgumentParser(description="Demo-Profildaten generieren")
    parser.add_argument("--anlage-id", type=int, default=None,
                        help="Anlage-ID (Standard: alle Anlagen)")
    parser.add_argument("--tage", type=int, default=60,
                        help="Anzahl Tage zurück (Standard: 60)")
    parser.add_argument("--wp", action="store_true",
                        help="Wärmepumpe simulieren")
    args = parser.parse_args()

    if not DB_PATH.exists():
        print(f"Fehler: DB nicht gefunden unter {DB_PATH}", file=sys.stderr)
        sys.exit(1)

    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL")

    rows = conn.execute("SELECT id, anlagenname, leistung_kwp FROM anlagen").fetchall()
    if not rows:
        print("Keine Anlagen in der DB gefunden.", file=sys.stderr)
        sys.exit(1)

    print(f"Seed Demo-Profildaten ({args.tage} Tage) in {DB_PATH}")
    random.seed(42)  # Reproduzierbar

    for anlage_id, name, kwp in rows:
        if args.anlage_id and anlage_id != args.anlage_id:
            continue
        kwp = kwp or 10.0
        print(f"  → {name} (ID {anlage_id}, {kwp} kWp)")
        seed_anlage(conn, anlage_id, kwp, hat_wp=args.wp, tage=args.tage)

    conn.close()
    print("Fertig.")


if __name__ == "__main__":
    main()
