# Konsistenz-Analyse: HA-Sensoren / MQTT / Monatsdaten

> Stand: 2026-04-02 — Ergebnis einer systematischen Prüfung aller drei Datenpfade

## Überblick

Drei Datenpfade liefern Energiedaten in EEDC:
1. **HA Sensor-Mapping** → `sensor_mapping` in Anlage, gelesen in `live_power_service.py`, `monatsabschluss.py`, `ha_statistics.py`
2. **MQTT Inbound/Gateway** → Topics `eedc/{id}_{name}/live/...` und `eedc/{id}_{name}/energy/...`, verarbeitet in `mqtt_inbound_service.py`, `mqtt_energy_history_service.py`
3. **Monatsdaten/InvestitionMonatsdaten** → DB-Felder in `monatsdaten.py`, `investition.py` (verbrauch_daten JSON)

---

## Inkonsistenz 1: Key-Format-Mismatch (kritisch für Option B)

| Kontext | Format | Beispiel |
|---------|--------|----------|
| HA-Pfad (`_get_tages_kwh`) | `{typ_prefix}_{inv_id}` | `pv_14`, `batterie_15`, `wallbox_12` |
| MQTT-Pfad (`get_tages_kwh`) | `inv/{inv_id}/{field}` | `inv/14/pv_erzeugung_kwh`, `inv/15/ladung_kwh` |
| Frontend erwartet | `{typ_prefix}_{inv_id}` | `pv_14`, `batterie_15`, `wallbox_12` |

**Auswirkung:** Der MQTT-Fallback für per-Komponente kWh liefert Keys die das Frontend nicht zuordnen kann. Nur die 3 Basis-Kategorien (`pv`, `einspeisung`, `netzbezug`) funktionieren.

**Stellen im Code:**
- HA-Pfad: `live_power_service.py` Zeile 934–939 (baut `{prefix}_{inv_id}` Keys)
- MQTT-Pfad: `mqtt_energy_history_service.py` Zeile 239–252 (reicht `inv/{id}/{field}` durch)
- Prefix-Definitionen: `live_power_service.py` Zeile 81–89 (`_TAGESVERLAUF_KATEGORIE`) und Zeile 103–105 (`_LIVE_KEY_PREFIX`)

**Fix-Vorschlag:** In `_compute_deltas()` ein Mapping von `inv/{inv_id}/{field}` → `{typ_prefix}_{inv_id}` einbauen. Benötigt Investitionstyp-Information (aus DB oder durchgereicht).

---

## Inkonsistenz 2: Namens-Asymmetrie Basis-PV

| Kontext | Feldname |
|---------|----------|
| MQTT Energy Topic | `pv_gesamt_kwh` |
| Monatsdaten (DB) | `pv_erzeugung_kwh` |
| sensor_mapping (Investition) | `pv_erzeugung_kwh` |
| `_KEY_TO_CATEGORY` Mapping | `pv_gesamt_kwh` → `"pv"` |

**Auswirkung:** Funktional kein Problem (wird korrekt gemappt), aber verwirrend bei der Wartung.

---

## Inkonsistenz 3: Fehlende MQTT Energy Topics

Felder die in HA sensor_mapping und Monatsdaten existieren, aber kein MQTT Energy Topic haben:

| Feld | Inv-Typ | sensor_mapping | Monatsdaten | MQTT Energy |
|------|---------|---------------|-------------|-------------|
| `ladung_netz_kwh` | Speicher | ✓ | ✓ | ✗ |
| `ladung_pv_kwh` | E-Auto | ✓ | ✓ | ✗ (nur `ladung_kwh` Summe) |
| `ladung_netz_kwh` | E-Auto | ✓ | ✓ | ✗ (nur `ladung_kwh` Summe) |
| `ladung_extern_kwh` | E-Auto | ✓ | ✓ | ✗ |
| `verbrauch_kwh` | E-Auto | ✓ | ✓ | ✗ |
| `ladung_pv_kwh` | Wallbox | ✓ | ✓ | ✗ |
| `strom_heizen_kwh` | WP (getrennt) | ✓ | ✓ | ✗ |
| `strom_warmwasser_kwh` | WP (getrennt) | ✓ | ✓ | ✗ |

**Einschätzung:** Die fehlenden Split-Felder (PV/Netz-Aufteilung) sind kein Bug — die Aufteilung wird erst beim Monatsabschluss berechnet, nicht im Live-Kontext. Getrennte WP-Strommessung (`strom_heizen_kwh` / `strom_warmwasser_kwh`) ist ein Spezialfall (wenige Nutzer).

---

## Inkonsistenz 4: Wallbox/E-Auto Prefix-Verwirrung

Drei verschiedene Stellen definieren Kategorie-Prefixe für Wallbox:

| Stelle | Wallbox-Prefix | E-Auto-Prefix |
|--------|---------------|---------------|
| `_TAGESVERLAUF_KATEGORIE` (Zeile 81–89) | `"eauto"` ← falsch? | `"eauto"` |
| `_LIVE_KEY_PREFIX` (Zeile 103–105) | `"wallbox"` ← überschreibt | — |
| `_TV_SERIE_CONFIG` (Zeile 92–100) | `"wallbox"` | `"eauto"` |

**Auswirkung:** Funktioniert durch die Override-Kette (`_LIVE_KEY_PREFIX` hat Vorrang), aber fragil und verwirrend. In `_TAGESVERLAUF_KATEGORIE` steht Wallbox als `"eauto"` — das war vermutlich mal korrekt als Wallbox und E-Auto noch zusammengefasst waren.

---

## Konsistente Bereiche (kein Handlungsbedarf)

### Live-Wattage (W) — HA + MQTT identisch

| Basis-Feld | HA sensor_mapping | MQTT live Topic |
|------------|-------------------|-----------------|
| `einspeisung_w` | ✓ | ✓ |
| `netzbezug_w` | ✓ | ✓ |
| `pv_gesamt_w` | ✓ | ✓ |
| `netz_kombi_w` | ✓ | ✓ |

| Inv-Feld | HA sensor_mapping | MQTT live Topic |
|----------|-------------------|-----------------|
| `leistung_w` | ✓ (alle Typen) | ✓ |
| `soc` | ✓ (Speicher, E-Auto) | ✓ |
| `leistung_heizen_w` | ✓ (WP) | ✓ |
| `leistung_warmwasser_w` | ✓ (WP) | ✓ |
| `warmwasser_temperatur_c` | ✓ (WP) | ✓ |

### Basis Energy (3 Aggregat-Keys) — konsistent

| Kategorie | MQTT Energy Key | `_KEY_TO_CATEGORY` | Monatsdaten |
|-----------|----------------|-------------------|-------------|
| PV | `pv_gesamt_kwh` | → `"pv"` ✓ | `pv_erzeugung_kwh` (anderer Name) |
| Einspeisung | `einspeisung_kwh` | → `"einspeisung"` ✓ | `einspeisung_kwh` ✓ |
| Netzbezug | `netzbezug_kwh` | → `"netzbezug"` ✓ | `netzbezug_kwh` ✓ |

---

## Priorität für Fixes

1. **Key-Format-Mismatch** (Inkonsistenz 1) — Blocker für Option B Refactoring
2. **Wallbox/E-Auto Prefix** (Inkonsistenz 4) — Aufräumen bei Gelegenheit
3. **PV-Namensasymmetrie** (Inkonsistenz 2) — Kosmetik, kein funktionales Problem
4. **Fehlende MQTT Energy Topics** (Inkonsistenz 3) — Bewusste Lücke, kein sofortiger Fix nötig
