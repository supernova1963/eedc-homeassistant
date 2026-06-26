#!/usr/bin/env bash
#
# build-demo-db.sh — Kanonische Demo-DB für Dev-/Guest-Box aus EINER Quelle bauen.
#
# Hintergrund: Die Demo-DB entsteht aus dem Master (eedc/data/eedc.db) PLUS zwei
# Seeds, die bisher nur verstreut/manuell liefen → die Guest-Box driftete weg
# (Tag-/Aussicht-Seeds fehlten). Dieses Script bündelt den kompletten Aufbau
# idempotent an einer Stelle, damit Dev- und Guest-Box reproduzierbar identisch
# befüllt sind.
#
# Pipeline:
#   1) Master kopieren  (eedc/data/eedc.db — enthält bereits die P1-Komponenten
#      VW ID.3 + Heizstab, Invest 11/12).
#   2) Aussicht-Historie: TEP 2025-10-15..2025-12-30 um +175 Tage geschoben
#      (→ 2026-04-08..2026-06-23) für die Stunden-Prognose/Tag-Sichten in 2026.
#   3) Tag-Reseed (scripts/reseed-v4-tag-demo.py): TZ pv_prognose/SOLL,
#      sensor_mapping WP4/WB5, kumulative sensor_snapshots (WP-Wärme/JAZ, E-Mob).
#   4) Optional: leere Test-Anlage „Ferienhaus Süd" (Sammel-Screen/Leerzustand)
#      aus einer vorhandenen DB übernehmen.
#   5) Laufzeit-Cruft (api_cache, Streu-Zeilen jenseits der Seed-Daten) leeren.
#
# Aufruf:
#   scripts/build-demo-db.sh OUTPUT.db [--extra-anlage-from DB.db]
# Default OUTPUT: ./scratch-demo.db
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$SCRIPT_DIR/.." && pwd)"
MASTER="$REPO/eedc/data/eedc.db"

OUT="${1:-$REPO/scratch-demo.db}"
EXTRA_ANLAGE_DB=""
if [ "${2:-}" = "--extra-anlage-from" ]; then
  EXTRA_ANLAGE_DB="${3:?--extra-anlage-from braucht eine DB}"
fi

[ -f "$MASTER" ] || { echo "FEHLER: Master-DB fehlt: $MASTER"; exit 1; }

# Letzter geseedeter Tag = Obergrenze; alles darüber ist Laufzeit-Cruft.
SEED_BIS="2026-06-23"

echo "==> [1/6] Master → $OUT"
cp "$MASTER" "$OUT"
rm -f "$OUT-wal" "$OUT-shm"

echo "==> [2/6] Aussicht-Historie: TEP +175 Tage (2025-10-15..12-30 → 2026)"
TEP_COLS="anlage_id,datum,stunde,pv_kw,verbrauch_kw,einspeisung_kw,netzbezug_kw,batterie_kw,waermepumpe_kw,wallbox_kw,wp_starts_anzahl,ueberschuss_kw,defizit_kw,temperatur_c,globalstrahlung_wm2,bewoelkung_prozent,niederschlag_mm,wetter_code,soc_prozent,strompreis_cent,boersenpreis_cent,komponenten,source_provenance,created_at,wp_betriebsstunden"
TEP_SEL="anlage_id,date(datum,'+175 days'),stunde,pv_kw,verbrauch_kw,einspeisung_kw,netzbezug_kw,batterie_kw,waermepumpe_kw,wallbox_kw,wp_starts_anzahl,ueberschuss_kw,defizit_kw,temperatur_c,globalstrahlung_wm2,bewoelkung_prozent,niederschlag_mm,wetter_code,soc_prozent,strompreis_cent,boersenpreis_cent,komponenten,source_provenance,created_at,wp_betriebsstunden"
sqlite3 "$OUT" "
  DELETE FROM tages_energie_profil
   WHERE datum BETWEEN date('2025-10-15','+175 days') AND date('2025-12-30','+175 days');
  INSERT INTO tages_energie_profil ($TEP_COLS)
  SELECT $TEP_SEL FROM tages_energie_profil
   WHERE datum BETWEEN '2025-10-15' AND '2025-12-30';
"

echo "==> [3/6] Tag-Reseed (TZ-Prognose, sensor_mapping, snapshots)"
# Master hat sensor_mapping = NULL; der Reseed erwartet gültiges JSON.
sqlite3 "$OUT" "UPDATE anlagen SET sensor_mapping='{}' WHERE sensor_mapping IS NULL OR sensor_mapping='';"
EEDC_RESEED_DB="$OUT" python3 "$SCRIPT_DIR/reseed-v4-tag-demo.py"

echo "==> [4/6] Sommer-Reseed Apr–Jun 2026 (plausible PV/Einspeisung/Temp + PR-Aggregate)"
# Korrigiert die saisonale Rückwärts-Abbildung des +175-Seeds (Dezember auf Juni)
# und füllt die TZ-Aggregate (PR/Spitzen/Temp), die der Tag-Reseed nicht erzeugt.
EEDC_RESEED_DB="$OUT" python3 "$SCRIPT_DIR/seed-v4-sommer-2026.py"

echo "==> [4b] Monats-Aggregate 2026 (Apr–Jun) additiv aus 2025-H1"
# R5-1/2/3 (Rainer simon42): monatsdaten/IMD enden im Master 2025-12, während die
# TEP/TZ-Tagesdaten via +175-Shift bis 2026-06-23 reichen → Cockpit/Monat sprang auf
# „Dez 2025", Cockpit/Jahr kannte 2026 gar nicht (Monat/Jahr wählen „neuester mit
# Daten"). Wir spiegeln genau die DREI Monate MIT 2026-Tagesdaten (Apr/Mai/Jun) als
# Monats-Aggregate aus 2025-H1 (reale, plausible Werte; Juni ≈ Sommer-Seed-Einspeisung)
# → Monat-Default = Jun 2026, Jahr kennt 2026 als Teiljahr. Additiv (Master unberührt),
# nur Monate mit Tagesdaten (keine leeren Aggregat-Geister). pv_erzeugung_kwh ist
# bewusst Legacy/NULL (PV kommt aus IMD der PV-Module).
sqlite3 "$OUT" "
  INSERT INTO monatsdaten (anlage_id,jahr,monat,einspeisung_kwh,netzbezug_kwh,pv_erzeugung_kwh,direktverbrauch_kwh,eigenverbrauch_kwh,gesamtverbrauch_kwh,batterie_ladung_kwh,batterie_entladung_kwh,batterie_ladung_netz_kwh,batterie_ladepreis_cent,netzbezug_durchschnittspreis_cent,kraftstoffpreis_euro,gaspreis_cent_kwh,globalstrahlung_kwh_m2,sonnenstunden,durchschnittstemperatur,ueberschuss_kwh,defizit_kwh,batterie_vollzyklen,performance_ratio,peak_netzbezug_kw,sonderkosten_euro,sonderkosten_beschreibung,datenquelle,notizen,source_provenance,source_hash,created_at,updated_at)
  SELECT anlage_id,2026,monat,einspeisung_kwh,netzbezug_kwh,pv_erzeugung_kwh,direktverbrauch_kwh,eigenverbrauch_kwh,gesamtverbrauch_kwh,batterie_ladung_kwh,batterie_entladung_kwh,batterie_ladung_netz_kwh,batterie_ladepreis_cent,netzbezug_durchschnittspreis_cent,kraftstoffpreis_euro,gaspreis_cent_kwh,globalstrahlung_kwh_m2,sonnenstunden,durchschnittstemperatur,ueberschuss_kwh,defizit_kwh,batterie_vollzyklen,performance_ratio,peak_netzbezug_kw,sonderkosten_euro,sonderkosten_beschreibung,datenquelle,notizen,source_provenance,source_hash,created_at,updated_at
  FROM monatsdaten WHERE jahr=2025 AND monat IN (4,5,6);
  INSERT INTO investition_monatsdaten (investition_id,jahr,monat,verbrauch_daten,einsparung_monat_euro,co2_einsparung_kg,source_provenance,source_hash,created_at,updated_at)
  SELECT investition_id,2026,monat,verbrauch_daten,einsparung_monat_euro,co2_einsparung_kg,source_provenance,source_hash,created_at,updated_at
  FROM investition_monatsdaten WHERE jahr=2025 AND monat IN (4,5,6);
"

if [ -n "$EXTRA_ANLAGE_DB" ]; then
  echo "==> [5/6] Leere Test-Anlage Ferienhaus Sued (Sammel-Screen) aus $EXTRA_ANLAGE_DB uebernehmen"
  sqlite3 "$OUT" "ATTACH '$EXTRA_ANLAGE_DB' AS src;
    INSERT OR IGNORE INTO anlagen SELECT * FROM src.anlagen WHERE id=2;
    DETACH src;"
else
  echo "==> [5/6] (keine Extra-Anlage)"
fi

echo "==> [6/6] Laufzeit-Cruft leeren (api_cache + Streu-Zeilen > $SEED_BIS)"
sqlite3 "$OUT" "
  DELETE FROM api_cache;
  DELETE FROM tages_zusammenfassung WHERE datum > '$SEED_BIS';
  DELETE FROM tages_energie_profil  WHERE datum > '$SEED_BIS';
"
sqlite3 "$OUT" "VACUUM;"
rm -f "$OUT-wal" "$OUT-shm"

n_anlagen=$(sqlite3 "$OUT" 'SELECT COUNT(*) FROM anlagen;')
n_invest=$(sqlite3 "$OUT" 'SELECT COUNT(*) FROM investitionen;')
n_tep=$(sqlite3 "$OUT" 'SELECT COUNT(*) FROM tages_energie_profil;')
n_tz=$(sqlite3 "$OUT" 'SELECT COUNT(*) FROM tages_zusammenfassung;')
n_snap=$(sqlite3 "$OUT" 'SELECT COUNT(*) FROM sensor_snapshots;')
echo "==> Fertig: $OUT"
echo "    anlagen=$n_anlagen invest=$n_invest TEP=$n_tep TZ=$n_tz snapshots=$n_snap"
