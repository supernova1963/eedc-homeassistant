#!/usr/bin/env python3
"""
Demo-Seed: Generiert realistische TagesEnergieProfil + TagesZusammenfassung
für lokale Testumgebungen (ohne echte HA-History).

Verwendung:
  cd /home/gernot/claude/eedc-homeassistant/eedc
  python ../scripts/seed_demo_profil.py [--anlage-id 1] [--tage 60]

Muster:
  PV        — Sinuskurve, aufgespalten auf vorhandene PV/BKW-Investitionen
  Batterie  — aufgespalten auf vorhandene Speicher-Investitionen
  WP        — tagsüber, wenn vorhanden
  Wallbox   — gelegentliches Laden morgens oder abends
  Sonstiges-Erzeuger (z.B. BHKW) — läuft bei wenig PV (Nacht/Morgen)
  Sonstiges-Verbraucher (z.B. Poolpumpe) — läuft mittags bei PV-Überschuss
  Haushalt  — Residual (Quellen - alle Senken)
  Netz      — Differenz (Bezug bei Defizit, Einspeisung bei Überschuss)
"""

import argparse
import json
import math
import random
import sqlite3
import sys
from datetime import date, timedelta
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "eedc" / "data" / "eedc.db"

BATTERIE_SOC_START = 20.0  # % am Morgen


# ─── Profil-Hilfsfunktionen ───────────────────────────────────────────────────

def _pv_profil(stunde: int, kwp: float, tag_im_jahr: int, faktor: float) -> float:
    saison = 0.5 + 0.5 * math.sin(2 * math.pi * (tag_im_jahr - 80) / 365)
    sunrise = 10 - 2 * saison
    sunset  = 16 + 2 * saison
    if stunde <= sunrise or stunde >= sunset:
        return 0.0
    winkel = math.pi * (stunde - sunrise) / (sunset - sunrise)
    max_faktor = 0.30 + 0.50 * saison
    return round(kwp * max_faktor * math.sin(winkel) * faktor, 3)


def _haushalt_profil(stunde: int, faktor: float) -> float:
    basis = 0.25
    if 7 <= stunde <= 8:   basis += 0.8
    elif stunde == 9:      basis += 0.4
    elif 17 <= stunde <= 21: basis += 0.6
    elif stunde == 22:     basis += 0.3
    return round(basis * faktor, 3)


def _temperatur(stunde: int, tag_im_jahr: int) -> float:
    saison_basis = 8 + 12 * math.sin(2 * math.pi * (tag_im_jahr - 80) / 365)
    tagesgang = -3 * math.cos(2 * math.pi * stunde / 24)
    return round(saison_basis + tagesgang + random.uniform(-1, 1), 1)


# ─── Haupt-Seed-Funktion ──────────────────────────────────────────────────────

def seed_anlage(conn: sqlite3.Connection, anlage_id: int, kwp: float, tage: int) -> None:
    # Investitionen laden
    invs = conn.execute(
        "SELECT id, typ, bezeichnung, parameter FROM investitionen "
        "WHERE anlage_id=? AND aktiv=1", (anlage_id,)
    ).fetchall()

    def _invs(typ):
        return [(r[0], r[1], r[2], json.loads(r[3]) if r[3] else {})
                for r in invs if r[1] == typ]

    pv_invs       = _invs('pv-module') + _invs('balkonkraftwerk') + _invs('wechselrichter')
    # Wechselrichter SKIP — nur echte Erzeuger
    pv_invs       = _invs('pv-module') + _invs('balkonkraftwerk')
    speicher_invs = _invs('speicher')
    wp_invs       = _invs('waermepumpe')
    wb_invs       = _invs('wallbox') + _invs('e-auto')
    sonstige_invs = _invs('sonstiges')

    # PV-Aufteilung: gleichmäßig mit leichter Zufallsvariation pro Investition
    n_pv = len(pv_invs) or 1
    # Batteire-Kapazitäten (Schätzwert: 10 kWh pro Speicher)
    n_sp = len(speicher_invs) or 1
    bat_kap_gesamt = 10.0 * n_sp

    heute = date.today()
    gestern = heute - timedelta(days=1)

    inserted_tep = 0
    inserted_tz = 0

    for tage_zurueck in range(tage, 0, -1):
        tag = gestern - timedelta(days=tage_zurueck - 1)
        tag_im_jahr = tag.timetuple().tm_yday

        faktor_pv = random.uniform(0.3, 1.0)
        faktor_v  = random.uniform(0.85, 1.15)
        # Wallbox: 30% der Tage morgens laden, 20% abends
        wb_morgen = random.random() < 0.30
        wb_abend  = random.random() < 0.20
        wb_kw     = round(random.uniform(3.5, 7.0), 1) if (wb_morgen or wb_abend) else 0.0

        # BHKW-Variante: läuft an ~40% der Tage 6h (Nacht/früh morgens)
        bhkw_invs = [(i, t, b, p) for i, t, b, p in sonstige_invs
                     if p.get('kategorie') == 'erzeuger']
        bhkw_aktiv = random.random() < 0.40
        bhkw_start = random.randint(0, 4)   # startet 0–4 Uhr
        bhkw_kw    = round(random.uniform(0.8, 2.0), 2) if bhkw_aktiv else 0.0

        # Pool-Variante: läuft an ~60% der Tage 3–5h mittags
        pool_invs = [(i, t, b, p) for i, t, b, p in sonstige_invs
                     if p.get('kategorie') == 'verbraucher']
        pool_aktiv = random.random() < 0.60
        pool_start = random.randint(10, 13)
        pool_dauer = random.randint(3, 5)
        pool_kw    = round(random.uniform(0.6, 1.2), 2) if pool_aktiv else 0.0

        soc = BATTERIE_SOC_START
        stunden_daten = []

        for stunde in range(24):
            # ── PV gesamt ──────────────────────────────────────────────────
            pv_gesamt = _pv_profil(stunde, kwp, tag_im_jahr, faktor_pv)

            # PV aufteilen: BKW bekommt max 5% (klein), Rest auf PV-Module
            bkw_invs_h  = [(i, t, b, p) for i, t, b, p in pv_invs if t == 'balkonkraftwerk']
            pvmod_invs_h = [(i, t, b, p) for i, t, b, p in pv_invs if t == 'pv-module']
            bkw_anteil  = 0.05 * len(bkw_invs_h)
            bkw_gesamt  = pv_gesamt * bkw_anteil
            pvmod_gesamt = pv_gesamt - bkw_gesamt

            # Zufällige Aufteilung auf PV-Module (z.B. Süd > Ost/West)
            if pvmod_invs_h:
                gewichte = [random.uniform(0.5, 1.5) for _ in pvmod_invs_h]
                summe_g  = sum(gewichte)
                pv_komp  = {str(inv[0]): round(pvmod_gesamt * w / summe_g, 3)
                            for inv, w in zip(pvmod_invs_h, gewichte)}
            else:
                pv_komp = {}

            if bkw_invs_h:
                bkw_anteil_e = bkw_gesamt / len(bkw_invs_h)
                for inv in bkw_invs_h:
                    pv_komp[str(inv[0])] = round(bkw_anteil_e, 3)

            # ── BHKW (Sonstiges-Erzeuger) ──────────────────────────────────
            bhkw_stunde = bhkw_kw if (bhkw_aktiv and bhkw_start <= stunde < bhkw_start + 6) else 0.0
            bhkw_komp   = {str(inv[0]): round(bhkw_stunde, 3) for inv in bhkw_invs} if bhkw_invs else {}

            # ── WP ─────────────────────────────────────────────────────────
            wp_kw = round(1.2 * faktor_v, 3) if (wp_invs and 8 <= stunde <= 16) else 0.0
            wp_komp = {str(inv[0]): -wp_kw for inv in wp_invs} if wp_invs and wp_kw > 0 else {}

            # ── Wallbox ────────────────────────────────────────────────────
            wb_aktiv_h = ((wb_morgen and 7 <= stunde <= 9) or
                          (wb_abend  and 18 <= stunde <= 20))
            wb_h = wb_kw if wb_aktiv_h else 0.0
            wb_komp = {str(inv[0]): -wb_h for inv in wb_invs} if wb_invs and wb_h > 0 else {}

            # ── Pool (Sonstiges-Verbraucher) ───────────────────────────────
            pool_h = (pool_kw if (pool_aktiv and pool_start <= stunde < pool_start + pool_dauer)
                      else 0.0)
            pool_komp = {str(inv[0]): -pool_h for inv in pool_invs} if pool_invs and pool_h > 0 else {}

            # ── Haushalt-Grundlast ─────────────────────────────────────────
            haushalt_kw = _haushalt_profil(stunde, faktor_v)

            # ── Gesamte Erzeugung und Verbrauch ────────────────────────────
            pv_total  = pv_gesamt + bhkw_stunde
            vbr_total = haushalt_kw + wp_kw + wb_h + pool_h

            # ── Batterie-Simulation ────────────────────────────────────────
            ueberschuss_roh = pv_total - vbr_total
            bat_kw = 0.0
            if ueberschuss_roh > 0 and soc < 95:
                lade = min(ueberschuss_roh, bat_kap_gesamt * 0.5)
                bat_kw = -lade
                soc = min(100, soc + lade / bat_kap_gesamt * 100)
            elif ueberschuss_roh < 0 and soc > 10:
                entl = min(abs(ueberschuss_roh), bat_kap_gesamt * 0.5)
                entl = min(entl, (soc - 10) / 100 * bat_kap_gesamt)
                bat_kw = entl
                soc = max(10, soc - entl / bat_kap_gesamt * 100)

            # Batterie auf Speicher aufteilen
            bat_komp = {}
            if speicher_invs and bat_kw != 0:
                bat_anteil = bat_kw / n_sp
                for inv in speicher_invs:
                    bat_komp[str(inv[0])] = round(bat_anteil, 3)

            # ── Netz ───────────────────────────────────────────────────────
            bilanz    = pv_total + bat_kw - vbr_total
            einsp     = max(0.0, bilanz)
            netzbezug = max(0.0, -bilanz)

            # ── Haushalt-Residual für komponenten ──────────────────────────
            quellen = pv_total + max(0, bat_kw) + netzbezug
            senken  = vbr_total + max(0, -bat_kw) + einsp
            haushalt_residual = round(quellen - senken - haushalt_kw, 3)
            # Haushalt in komponenten = tatsächlicher unmodellierter Rest
            haushalt_komp = haushalt_kw + haushalt_residual

            # ── komponenten zusammenbauen ──────────────────────────────────
            komp: dict[str, float] = {}
            # PV-Serien (positiv)
            for inv_id_str, v in pv_komp.items():
                if v > 0: komp[f"pv_{inv_id_str}"] = v
            # BHKW (positiv = Erzeuger)
            for inv_id_str, v in bhkw_komp.items():
                if v > 0: komp[f"sonstige_{inv_id_str}"] = v
            # Batterie
            for inv_id_str, v in bat_komp.items():
                komp[f"batterie_{inv_id_str}"] = v
            # WP
            for inv_id_str, v in wp_komp.items():
                komp[f"waermepumpe_{inv_id_str}"] = v
            # Wallbox
            for inv_id_str, v in wb_komp.items():
                komp[f"wallbox_{inv_id_str}"] = v
            # Pool (negativ = Verbraucher)
            for inv_id_str, v in pool_komp.items():
                if v < 0: komp[f"sonstige_{inv_id_str}"] = v
            # Netz
            netz_val = round(netzbezug - einsp, 3)
            if abs(netz_val) > 0.001: komp["netz"] = netz_val
            # Haushalt-Residual
            if haushalt_komp > 0.01: komp["haushalt"] = round(-haushalt_komp, 3)

            stunden_daten.append({
                "stunde":            stunde,
                "pv_kw":             round(pv_total, 3),
                "verbrauch_kw":      round(vbr_total, 3),
                "einspeisung_kw":    round(einsp, 3),
                "netzbezug_kw":      round(netzbezug, 3),
                "batterie_kw":       round(bat_kw, 3),
                "waermepumpe_kw":    round(wp_kw, 3) if wp_kw else None,
                "wallbox_kw":        round(wb_h, 3) if wb_h else None,
                "ueberschuss_kw":    round(max(0, pv_total - vbr_total), 3),
                "defizit_kw":        round(max(0, vbr_total - pv_total), 3),
                "temperatur_c":      _temperatur(stunde, tag_im_jahr),
                "globalstrahlung_wm2": round(pv_gesamt / kwp * 1000 * 1.1 + random.uniform(-20, 20), 0) if kwp > 0 and pv_gesamt > 0 else 0.0,
                "soc_prozent":       round(soc, 1),
                "komponenten":       komp if komp else None,
            })

        # TagesEnergieProfil schreiben
        for d in stunden_daten:
            conn.execute("""
                INSERT OR REPLACE INTO tages_energie_profil
                  (anlage_id, datum, stunde, pv_kw, verbrauch_kw,
                   einspeisung_kw, netzbezug_kw, batterie_kw,
                   waermepumpe_kw, wallbox_kw, ueberschuss_kw, defizit_kw,
                   temperatur_c, globalstrahlung_wm2, soc_prozent,
                   komponenten, created_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,datetime('now'))
            """, (
                anlage_id, tag.isoformat(), d["stunde"],
                d["pv_kw"], d["verbrauch_kw"],
                d["einspeisung_kw"], d["netzbezug_kw"], d["batterie_kw"],
                d["waermepumpe_kw"], d["wallbox_kw"],
                d["ueberschuss_kw"], d["defizit_kw"],
                d["temperatur_c"], d["globalstrahlung_wm2"], d["soc_prozent"],
                json.dumps(d["komponenten"]) if d["komponenten"] else None,
            ))
            inserted_tep += 1

        # TagesZusammenfassung
        pv_kwh  = sum(d["pv_kw"] for d in stunden_daten)
        u_kwh   = sum(d["ueberschuss_kw"] for d in stunden_daten)
        d_kwh   = sum(d["defizit_kw"] for d in stunden_daten)
        peak_pv = max((d["pv_kw"] for d in stunden_daten), default=0)
        peak_nz = max((d["netzbezug_kw"] for d in stunden_daten), default=0)
        peak_ei = max((d["einspeisung_kw"] for d in stunden_daten), default=0)
        t_min   = min(d["temperatur_c"] for d in stunden_daten)
        t_max   = max(d["temperatur_c"] for d in stunden_daten)
        s_sum   = sum(d["globalstrahlung_wm2"] for d in stunden_daten)
        pr      = round(pv_kwh / (s_sum / 1000 * kwp), 3) if s_sum > 0 and kwp > 0 else None

        # komponenten_kwh: Tagessummen aus stündlichen komponenten
        komp_kwh: dict[str, float] = {}
        for d in stunden_daten:
            for k, v in (d["komponenten"] or {}).items():
                komp_kwh[k] = round(komp_kwh.get(k, 0) + v, 3)

        conn.execute("""
            INSERT OR REPLACE INTO tages_zusammenfassung
              (anlage_id, datum, ueberschuss_kwh, defizit_kwh,
               peak_pv_kw, peak_netzbezug_kw, peak_einspeisung_kw,
               temperatur_min_c, temperatur_max_c, strahlung_summe_wh_m2,
               performance_ratio, stunden_verfuegbar, datenquelle,
               komponenten_kwh, created_at, updated_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,24,'seed',?,datetime('now'),datetime('now'))
        """, (
            anlage_id, tag.isoformat(),
            round(u_kwh, 2), round(d_kwh, 2),
            round(peak_pv, 2), round(peak_nz, 2), round(peak_ei, 2),
            t_min, t_max, round(s_sum, 0),
            pr,
            json.dumps(komp_kwh) if komp_kwh else None,
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
    random.seed(42)

    for anlage_id, name, kwp in rows:
        if args.anlage_id and anlage_id != args.anlage_id:
            continue
        kwp = kwp or 10.0
        print(f"  → {name} (ID {anlage_id}, {kwp} kWp)")
        seed_anlage(conn, anlage_id, kwp, tage=args.tage)

    conn.close()
    print("Fertig.")


if __name__ == "__main__":
    main()
