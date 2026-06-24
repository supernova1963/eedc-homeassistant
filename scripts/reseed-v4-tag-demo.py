"""Reseed der Dev-Box-Demo-DB für Cockpit/Tag-Feature-Demo (Gernot 2026-06-24).

Macht aus der vorhandenen stündlichen TEP-Reihe die fehlenden Tages-Bausteine:
  1) TagesZusammenfassung.pv_prognose_kwh + komponenten_kwh(pv) je Tag
     → OM-Prognose + Lernfaktor → PV-Tages-SOLL sichtbar.
  2) sensor_mapping: WP4 heizenergie/warmwasser + Wallbox5 ladung_pv/ladung_netz
     auf (Demo-)Sensoren gemappt → get_tagesdetail_kwh erhebt sie.
  3) sensor_snapshots: kumulative Tages-Boundary-Zähler für diese Felder
     → WP-Wärme/JAZ + E-Mob PV-/Netz-Anteil je Tag.

Werte sind aus der TEP abgeleitet (pv_kw/waermepumpe_kw/wallbox_kw), damit sie zu
den IST-Energiewerten passen. /tmp ist flüchtig → nach Reboot erneut ausführen.
"""
import sqlite3
import json
from datetime import datetime, timedelta

DB = "/tmp/eedc_v4devbox.db"
ANLAGE = 1
WP_ID, WB_ID = "4", "5"

con = sqlite3.connect(DB)
cur = con.cursor()
now = "2026-06-24 00:00:00"

# ── Tagesaggregate aus der TEP ───────────────────────────────────────────────
rows = cur.execute(
    """SELECT datum,
              ROUND(SUM(COALESCE(pv_kw,0)),3),
              ROUND(SUM(COALESCE(waermepumpe_kw,0)),3),
              ROUND(SUM(COALESCE(wallbox_kw,0)),3),
              SUM(CASE WHEN COALESCE(pv_kw,0)>0 OR COALESCE(verbrauch_kw,0)>0 THEN 1 ELSE 0 END)
       FROM tages_energie_profil WHERE anlage_id=? GROUP BY datum ORDER BY datum""",
    (ANLAGE,),
).fetchall()
print(f"TEP-Tage: {len(rows)} ({rows[0][0]} .. {rows[-1][0]})")

def cop_fuer(monat: int) -> float:
    # Heizungs-COP saisonal (Winter niedriger, Übergang höher).
    return {12: 2.9, 1: 2.8, 2: 2.9, 3: 3.3, 4: 3.7, 5: 4.1, 6: 4.3,
            7: 4.3, 8: 4.2, 9: 3.9, 10: 3.4, 11: 3.1}.get(monat, 3.3)

# ── 1) TagesZusammenfassung (pv_prognose + komponenten_kwh) ──────────────────
tz_ins = tz_upd = 0
for datum, pv, wp, wb, stunden in rows:
    pv = pv or 0.0
    # OM-Prognose leicht über IST → Lernfaktor ~0.95 (IST/Prognose).
    prognose = round(pv / 0.95, 1) if pv > 0 else 0.0
    komp = json.dumps({"pv_6": round(pv, 2)})
    exists = cur.execute(
        "SELECT id FROM tages_zusammenfassung WHERE anlage_id=? AND datum=?", (ANLAGE, datum)
    ).fetchone()
    if exists:
        cur.execute(
            """UPDATE tages_zusammenfassung
               SET pv_prognose_kwh=?, komponenten_kwh=?, datenquelle=COALESCE(datenquelle,'ha_sensor'),
                   updated_at=? WHERE id=?""",
            (prognose, komp, now, exists[0]),
        )
        tz_upd += 1
    else:
        cur.execute(
            """INSERT INTO tages_zusammenfassung
               (anlage_id, datum, stunden_verfuegbar, source_provenance, created_at, updated_at,
                pv_prognose_kwh, komponenten_kwh, datenquelle)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (ANLAGE, datum, int(stunden or 24), "{}", now, now, prognose, komp, "ha_sensor"),
        )
        tz_ins += 1
print(f"TZ: {tz_ins} insert, {tz_upd} update")

# ── 2) sensor_mapping erweitern ─────────────────────────────────────────────
sm = json.loads(cur.execute("SELECT sensor_mapping FROM anlagen WHERE id=?", (ANLAGE,)).fetchone()[0])
inv = sm.setdefault("investitionen", {})
def map_feld(inv_id, feld, sensor_id):
    e = inv.setdefault(inv_id, {})
    e.setdefault("felder", {})[feld] = {"strategie": "sensor", "sensor_id": sensor_id}
map_feld(WP_ID, "heizenergie_kwh", "sensor.demo_wp_heizenergie_kwh")
map_feld(WP_ID, "warmwasser_kwh", "sensor.demo_wp_warmwasser_kwh")
map_feld(WB_ID, "ladung_pv_kwh", "sensor.demo_wallbox_ladung_pv_kwh")
map_feld(WB_ID, "ladung_netz_kwh", "sensor.demo_wallbox_ladung_netz_kwh")
cur.execute("UPDATE anlagen SET sensor_mapping=? WHERE id=?", (json.dumps(sm), ANLAGE))
print("sensor_mapping: WP4 heizenergie/warmwasser + WB5 ladung_pv/ladung_netz gemappt")

# ── 3) kumulative Boundary-Snapshots ────────────────────────────────────────
# daily increments je Sensor; Snapshot an jedem Tag 00:00 = Stand VOR dem Tag.
def daily_increments():
    for datum, pv, wp, wb, _ in rows:
        m = int(datum[5:7])
        wp = wp or 0.0; wb = wb or 0.0
        yield datum, {
            "inv:4:heizenergie_kwh": round(wp * cop_fuer(m), 3),   # thermisch Heizung
            "inv:4:warmwasser_kwh": 4.0 if wp > 0 else 2.0,         # thermisch WW ~konstant
            "inv:5:ladung_pv_kwh": round(wb * 0.6, 3),             # 60 % PV-Ladung
            "inv:5:ladung_netz_kwh": round(wb * 0.4, 3),           # 40 % Netz-Ladung
        }

bases = {"inv:4:heizenergie_kwh": 5000.0, "inv:4:warmwasser_kwh": 1500.0,
         "inv:5:ladung_pv_kwh": 800.0, "inv:5:ladung_netz_kwh": 600.0}
cum = dict(bases)
snap_rows = []
incs = list(daily_increments())
for datum, inc in incs:
    ts = f"{datum} 00:00:00"
    for key in bases:
        snap_rows.append((ANLAGE, key, ts, round(cum[key], 3), "ha_statistics"))
        cum[key] += inc[key]
# Abschluss-Boundary (Folgetag des letzten Tages 00:00) für den letzten Tages-Diff.
last = datetime.fromisoformat(incs[-1][0]) + timedelta(days=1)
for key in bases:
    snap_rows.append((ANLAGE, key, last.strftime("%Y-%m-%d 00:00:00"), round(cum[key], 3), "ha_statistics"))

cur.execute("DELETE FROM sensor_snapshots WHERE anlage_id=? AND sensor_key IN (?,?,?,?)",
            (ANLAGE, *bases.keys()))
cur.executemany(
    "INSERT OR REPLACE INTO sensor_snapshots (anlage_id, sensor_key, zeitpunkt, wert_kwh, quelle) VALUES (?,?,?,?,?)",
    snap_rows,
)
print(f"snapshots: {len(snap_rows)} Boundary-Werte ({len(bases)} Sensoren × {len(incs)+1} Grenzen)")

con.commit()
con.close()
print("Reseed fertig.")
