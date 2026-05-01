#!/bin/bash
# =============================================================================
# check-live-snapshot-5min.sh — Diagnose-Skript für Phase 1 Live-Snapshot 5-Min
#
# Ausführung im HA Add-on:
#   1. SSH/Add-on-Terminal in den eedc-Container öffnen
#   2. Script übertragen (z.B. via Add-on-File-Editor oder docker cp) oder
#      Inhalt direkt einfügen
#   3. ./check-live-snapshot-5min.sh
#
# Falls sqlite3 nicht im Container ist:
#   apk add sqlite           (Alpine, was eedc nutzt)
#
# Liefert PASS/FAIL pro Check + Datenpunkte zum mitlesen.
#
# Voraussetzungen für sinnvolle Ergebnisse:
#   - LIVE_SNAPSHOT_5MIN_ENABLED=true im Add-on-Env
#   - Add-on lief seit ≥ 24 h
#   - Mindestens ein Counter-Sensor gemappt (basis:einspeisung o. ä.)
# =============================================================================

set -uo pipefail

DB="${1:-/data/eedc.db}"
TODAY=$(date +%Y-%m-%d)
YESTERDAY=$(date -d 'yesterday' +%Y-%m-%d)
DAY_BEFORE_YESTERDAY=$(date -d '2 days ago' +%Y-%m-%d)

if [ ! -f "$DB" ]; then
    echo "FEHLER: DB nicht gefunden: $DB"
    echo "Pfad als Argument übergeben: $0 /pfad/zu/eedc.db"
    exit 1
fi

if ! command -v sqlite3 >/dev/null 2>&1; then
    echo "FEHLER: sqlite3 ist nicht installiert."
    echo "Im eedc Add-on (Alpine):  apk add sqlite"
    echo "Auf Debian/Ubuntu-Host:   apt install sqlite3"
    exit 1
fi

# Helfer: führt SQL aus, gibt Ergebnis zurück (empty-string-safe für Vergleiche)
sql() {
    sqlite3 -separator $'\t' "$DB" "$1"
}
sql_int() {
    local v
    v=$(sql "$1")
    echo "${v:-0}"
}

pass() { echo -e "  \033[0;32mPASS\033[0m  $1"; }
fail() { echo -e "  \033[0;31mFAIL\033[0m  $1"; }
warn() { echo -e "  \033[1;33mWARN\033[0m  $1"; }
info() { echo -e "        $1"; }

echo "================================================================"
echo "  Live-Snapshot 5-Min Diagnose — DB: $DB"
echo "  Heute=$TODAY  Gestern=$YESTERDAY  Vorgestern=$DAY_BEFORE_YESTERDAY"
echo "================================================================"

# -----------------------------------------------------------------------------
echo
echo "## Check 1: Sub-Hour-Slots werden überhaupt geschrieben"
# -----------------------------------------------------------------------------
COUNT_TODAY=$(sql_int "
  SELECT COUNT(*) FROM sensor_snapshots
  WHERE strftime('%M', zeitpunkt) != '00'
    AND date(zeitpunkt) = '$TODAY';
")
info "Sub-Hour-Slots heute: $COUNT_TODAY"

# Erwartung: pro Counter ~288 Slots/Tag, abzgl. Slots seit Restart/jetzt.
NUM_COUNTERS=$(sql_int "
  SELECT COUNT(DISTINCT sensor_key) FROM sensor_snapshots
  WHERE strftime('%M', zeitpunkt) != '00'
    AND date(zeitpunkt) = '$TODAY';
")
info "Verschiedene Counter mit Sub-Hour-Slots heute: $NUM_COUNTERS"

if [ "$COUNT_TODAY" -gt 0 ]; then
    pass "5-Min-Job schreibt"
else
    fail "Keine Sub-Hour-Slots heute — Flag aus, Job nicht gelaufen, oder HA short_term leer?"
    info "Prüfe: docker exec addon_<...> printenv | grep LIVE_SNAPSHOT"
fi

# -----------------------------------------------------------------------------
echo
echo "## Check 2: Slot-Verteilung über den Tag (Histogramm pro Stunde)"
# -----------------------------------------------------------------------------
# Pro Stunde sollte (bei jedem Counter) Slots :05/:10/:15/:20/:25/:30/:35/:40/:45/:50/:55 = 11 sein.
# Pro Counter * 24 = 264 Sub-Hour-Slots/Tag (+ 24 hourly-Slots = 288 inkl. :00).
sql "
  SELECT
    strftime('%H', zeitpunkt) AS stunde,
    COUNT(*) AS slots,
    COUNT(DISTINCT sensor_key) AS counter
  FROM sensor_snapshots
  WHERE date(zeitpunkt) = '$TODAY'
    AND strftime('%M', zeitpunkt) != '00'
  GROUP BY stunde
  ORDER BY stunde;
" | awk 'BEGIN{print "        Stunde | Sub-Hour-Slots | Counter"} \
        {printf "        %-6s | %-14s | %s\n", $1, $2, $3}'

# -----------------------------------------------------------------------------
echo
echo "## Check 3: Monotonie (kWh-Counter steigen monoton)"
# -----------------------------------------------------------------------------
# Wir vergleichen aufeinanderfolgende Slots — wenn ein späterer Wert kleiner
# als der vorige ist, ist das verdächtig (Glitch oder Counter-Reset).
# Tagesreset-Zähler werden tolerant behandelt: Sprung um >50% nach unten ist OK.
NON_MONO=$(sql_int "
  WITH ordered AS (
    SELECT
      sensor_key, zeitpunkt, wert_kwh,
      LAG(wert_kwh) OVER (PARTITION BY sensor_key ORDER BY zeitpunkt) AS prev_wert,
      LAG(zeitpunkt) OVER (PARTITION BY sensor_key ORDER BY zeitpunkt) AS prev_zp
    FROM sensor_snapshots
    WHERE date(zeitpunkt) = '$TODAY'
      AND sensor_key NOT LIKE '%_starts_anzahl'
  )
  SELECT COUNT(*) FROM ordered
  WHERE prev_wert IS NOT NULL
    AND wert_kwh < prev_wert - 0.01
    AND wert_kwh > prev_wert * 0.5;
")
info "Nicht-monotone Übergänge (ohne plausible Tagesresets): $NON_MONO"
if [ "$NON_MONO" -eq 0 ]; then
    pass "Counter monoton"
else
    fail "Glitches gefunden — Details:"
    sql "
      WITH ordered AS (
        SELECT
          sensor_key, zeitpunkt, wert_kwh,
          LAG(wert_kwh) OVER (PARTITION BY sensor_key ORDER BY zeitpunkt) AS prev_wert,
          LAG(zeitpunkt) OVER (PARTITION BY sensor_key ORDER BY zeitpunkt) AS prev_zp
        FROM sensor_snapshots
        WHERE date(zeitpunkt) = '$TODAY'
          AND sensor_key NOT LIKE '%_starts_anzahl'
      )
      SELECT sensor_key, prev_zp, prev_wert, zeitpunkt, wert_kwh,
             round(wert_kwh - prev_wert, 3) AS delta
      FROM ordered
      WHERE prev_wert IS NOT NULL
        AND wert_kwh < prev_wert - 0.01
        AND wert_kwh > prev_wert * 0.5
      ORDER BY sensor_key, zeitpunkt
      LIMIT 10;
    " | awk -F'\t' '{printf "        %s @ %s: %s → %s (delta %s)\n", $1, $4, $3, $5, $6}'
fi

# -----------------------------------------------------------------------------
echo
echo "## Check 4: Mitternachts-Boundary (Slot 23:55 → 00:00 → 00:05)"
# -----------------------------------------------------------------------------
# Für jeden Counter prüfen ob die drei Slots existieren am Übergang gestern→heute.
sql "
  WITH cnt AS (
    SELECT DISTINCT sensor_key FROM sensor_snapshots
    WHERE date(zeitpunkt) = '$YESTERDAY'
      AND strftime('%M', zeitpunkt) != '00'
  )
  SELECT
    cnt.sensor_key,
    EXISTS(SELECT 1 FROM sensor_snapshots s WHERE s.sensor_key=cnt.sensor_key
      AND s.zeitpunkt = datetime('$YESTERDAY' || ' 23:55:00')) AS has_2355,
    EXISTS(SELECT 1 FROM sensor_snapshots s WHERE s.sensor_key=cnt.sensor_key
      AND s.zeitpunkt = datetime('$TODAY' || ' 00:00:00')) AS has_0000,
    EXISTS(SELECT 1 FROM sensor_snapshots s WHERE s.sensor_key=cnt.sensor_key
      AND s.zeitpunkt = datetime('$TODAY' || ' 00:05:00')) AS has_0005
  FROM cnt;
" | awk -F'\t' 'BEGIN{print "        Counter | 23:55 | 00:00 | 00:05"} \
              {printf "        %s | %s | %s | %s\n", $1, $2, $3, $4}'

MISS_BOUNDARY=$(sql_int "
  WITH cnt AS (
    SELECT DISTINCT sensor_key FROM sensor_snapshots
    WHERE date(zeitpunkt) = '$YESTERDAY'
      AND strftime('%M', zeitpunkt) != '00'
  )
  SELECT COUNT(*) FROM cnt WHERE NOT EXISTS(
    SELECT 1 FROM sensor_snapshots s WHERE s.sensor_key=cnt.sensor_key
      AND s.zeitpunkt = datetime('$TODAY' || ' 00:00:00')
  );
")
if [ "$MISS_BOUNDARY" -eq 0 ]; then
    pass "Mitternachts-:00-Snapshots vollständig"
else
    warn "$MISS_BOUNDARY Counter ohne Mitternachts-:00 — hourly-Job hat noch nicht gelaufen oder LTS leer"
fi

# -----------------------------------------------------------------------------
echo
echo "## Check 5: Cleanup (vorgestern sollte keine Sub-Hour-Slots mehr haben)"
# -----------------------------------------------------------------------------
# HINWEIS: nur aussagekräftig wenn das Flag seit ≥ 2 Tagen an ist.
# Bei Tag 1 nach Aktivierung sind vorgestern's Slots ohnehin nie entstanden.
LEFT=$(sql_int "
  SELECT COUNT(*) FROM sensor_snapshots
  WHERE strftime('%M', zeitpunkt) != '00'
    AND date(zeitpunkt) = '$DAY_BEFORE_YESTERDAY';
")
info "Sub-Hour-Slots vorgestern: $LEFT"
if [ "$LEFT" -eq 0 ]; then
    pass "Cleanup hat vorgestern leer geräumt"
else
    fail "$LEFT Sub-Hour-Slots vorgestern noch da — Cleanup-Job nicht gelaufen?"
    info "Prüfe Scheduler-Status: GET /api/scheduler/status"
fi

# Hourly-Slots vorgestern müssen aber dabei BLEIBEN.
HOURLY_KEEP=$(sql_int "
  SELECT COUNT(*) FROM sensor_snapshots
  WHERE strftime('%M', zeitpunkt) = '00'
    AND date(zeitpunkt) = '$DAY_BEFORE_YESTERDAY';
")
info "Hourly-Slots vorgestern (sollten erhalten bleiben): $HOURLY_KEEP"
if [ "$HOURLY_KEEP" -gt 0 ]; then
    pass "Hourly-:00-Slots vorgestern noch vorhanden"
else
    fail "Auch hourly-Slots weg — Cleanup zu aggressiv!"
fi

# -----------------------------------------------------------------------------
echo
echo "## Check 6: Verdichtungs-Garantie (Σ 5-Min-Deltas == 1h-Delta)"
# -----------------------------------------------------------------------------
# Für jeden Counter, jede Stunde des heutigen Tages:
# Σ (s[h:05]-s[h:00] + s[h:10]-s[h:05] + ... + s[h+1:00]-s[h:55])
#   muss gleich (s[h+1:00] - s[h:00]) sein.
# Teleskopisch ist das trivial — prüft also ob Slots vollständig sind.
# Ausgabe: pro Counter+Stunde: 5-min-Σ vs 1h-Δ und Drift.
echo "        Beispiel-Drift (heute, Stunde 10:00, alle Counter mit beiden Pfaden):"
sql "
  WITH stunden AS (
    SELECT 10 AS h  -- Beispielstunde
  ),
  five_min_sum AS (
    SELECT s.sensor_key, st.h,
           MAX(s.wert_kwh) - MIN(s.wert_kwh) AS sub_delta,
           COUNT(*) AS n_slots
    FROM sensor_snapshots s, stunden st
    WHERE date(s.zeitpunkt) = '$TODAY'
      AND CAST(strftime('%H', s.zeitpunkt) AS INTEGER) = st.h
      AND strftime('%M', s.zeitpunkt) != '00'
      AND s.sensor_key NOT LIKE '%_starts_anzahl'
    GROUP BY s.sensor_key, st.h
  ),
  hourly_delta AS (
    SELECT s_end.sensor_key,
           s_end.wert_kwh - s_start.wert_kwh AS h_delta
    FROM sensor_snapshots s_start
    JOIN sensor_snapshots s_end
      ON s_start.sensor_key = s_end.sensor_key
    WHERE s_start.zeitpunkt = datetime('$TODAY' || ' 10:00:00')
      AND s_end.zeitpunkt = datetime('$TODAY' || ' 11:00:00')
  )
  SELECT
    h.sensor_key,
    round(h.h_delta, 3) AS hourly_delta,
    round(f.sub_delta, 3) AS five_min_max_minus_min,
    round(h.h_delta - f.sub_delta, 4) AS drift,
    f.n_slots
  FROM hourly_delta h
  LEFT JOIN five_min_sum f ON h.sensor_key = f.sensor_key;
" | awk -F'\t' 'BEGIN{print "        Counter | 1h-Δ | 5min-Range | Drift | Slots"} \
              {printf "        %s | %s | %s | %s | %s\n", $1, $2, $3, $4, $5}'

# -----------------------------------------------------------------------------
echo
echo "================================================================"
echo "  Fertig. Bei FAIL/Drift > 0.001 kWh: Slot-Reihen einzeln ansehen:"
echo
echo "  sqlite3 $DB \"SELECT zeitpunkt, wert_kwh FROM sensor_snapshots"
echo "                WHERE sensor_key='basis:einspeisung'"
echo "                  AND date(zeitpunkt)='$TODAY'"
echo "                ORDER BY zeitpunkt;\""
echo "================================================================"
