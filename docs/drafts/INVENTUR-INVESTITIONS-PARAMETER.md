# Inventur Investitions-Parameter — Drift-Matrix v3.25.0-Vorbereitung

> Stand: 2026-04-29 · Phase 0 des Refactor-Plans · Vorlage für SoT-Konstanten-Modul

## Was ist hier drin

Pro Investitions-Typ:

1. **Drift-Matrix** — alle Schlüssel × Schreib-/Lese-Stellen
2. **Bugs** — Stellen, wo Form-Wert stillschweigend ignoriert wird (Drift zwischen Schreib- und Lese-Key)
3. **Kanon-Vorschlag** — welcher Key künftig der eine wahre sein soll

Schreib-Stellen sind **Form** (`InvestitionForm.tsx`) und **Wizard** (`InvestitionenStep.tsx`). Lese-Stellen sind das **Backend** (Aggregations-/ROI-/Service-Code) sowie Frontend-**Render**-Stellen (Dashboards, Listen). Der vermeintliche autoritative Endpoint `/investitionen/typen` mit `parameter_schema` (in `eedc/backend/api/routes/investitionen.py:108-273`) ist **tot** — `useInvestitionTypen` ist exportiert, aber nirgends aufgerufen.

---

## E-Auto

### Drift-Matrix

| Schlüssel | Form | Wizard | Backend liest | Render |
|---|---|---|---|---|
| `batteriekapazitaet_kwh` | ✓ Z.130 | ✓ Z.394 | – (nur Top-Level) | – |
| `verbrauch_kwh_100km` | ✓ Z.131 | ✓ Z.408 | invest.py:1158 (default 18) | – |
| `jahresfahrleistung_km` | ✓ Z.132 | – | vorschlag_service.py:317 | – |
| `km_jahr` | – | – | invest.py:1157 (default 15000) | – |
| `pv_ladeanteil_prozent` | ✓ Z.133 | – | – | – |
| `pv_anteil_prozent` | – | – | invest.py:1159 (default 60) | – |
| `vergleich_verbrauch_l_100km` | ✓ Z.134 | – | aussichten.py:1102, ha_export:544, pdf_ops:447 | – |
| `benzin_verbrauch_liter_100km` | – | – | invest.py:1160 (default 7.0) | – |
| `benzinpreis_euro` | ✓ Z.135 | – | aussichten.py:1101, ha_export:543, pdf_ops:446 | – |
| `v2h_faehig` | ✓ Z.136 | ✓ Z.420 | ha_import.py:80 (defensive: oder `nutzt_v2h`) | – |
| `nutzt_v2h` | – | – | aussichten.py:1412, live_komponenten_builder.py:129, invest.py:1161 | – |
| `v2h_entladeleistung_kw` | ✓ Z.137 | – | – | – |
| `v2h_entlade_preis_cent` | – | – | invest.py:1163, 1511 | – |
| `v2h_entladung_kwh_jahr` | – | – | invest.py:1162 | – |
| `ist_dienstlich` | ✓ Z.138 | – | – | – |
| `alternativ_kosten_euro` | – | – | aussichten.py:1061 (default 8000), cockpit/uebersicht:357 | – |

### Bugs (Form/Wizard-Wert wird im Backend ignoriert)

1. **🔥 V2H 3-fach kaputt** — Form/Wizard schreiben `v2h_faehig`. Lese-Stellen lesen `nutzt_v2h` ohne Fallback:
   - `aussichten.py:1412` (Aussichten-Dashboard V2H-Berechnung)
   - `live_komponenten_builder.py:129` (Live-V2H-Komponenten-Erkennung)
   - `investitionen.py:1161` (E-Auto-ROI V2H-Schalter)
   - Nur `ha_import.py:80` hat einen defensiven Doppel-Read und funktioniert. **Konsequenz:** Alle User, die V2H im Form/Wizard aktiviert haben, sehen es im Aussichten-Tab und in Live-Komponenten als deaktiviert; auch der V2H-Anteil fließt nicht in den E-Auto-ROI ein.
2. **🔥 Jahresfahrleistung kaputt im ROI** — Form schreibt `jahresfahrleistung_km`, `investitionen.py:1157` liest `km_jahr` mit Default 15000. **Konsequenz:** ROI nutzt Default-Wert statt User-Eingabe, außer der User stimmt zufällig auf 15000.
3. **🔥 PV-Ladeanteil kaputt im ROI** — Form schreibt `pv_ladeanteil_prozent`, `investitionen.py:1159` liest `pv_anteil_prozent` mit Default 60. **Konsequenz:** Wie #2, ROI ignoriert User-Wert.
4. **🔥 Vergleichsverbrauch nur halb kaputt** — Form schreibt `vergleich_verbrauch_l_100km`. `aussichten.py`, `ha_export.py`, `pdf_operations.py` lesen den korrekten Key. **Aber:** `investitionen.py:1160` (ROI-Berechnung im Investitionen-Endpoint) liest `benzin_verbrauch_liter_100km` mit Default 7.0. **Konsequenz:** ROI weicht von Aussichten ab.

### Kanon-Vorschlag E-Auto

Form/Wizard sind die User-Schreibseite und ihre Keys sind im Frontend-Code etabliert — diese behalten:

| Kanonisch | Backend-Drift-Variante |
|---|---|
| `jahresfahrleistung_km` | `km_jahr` |
| `pv_ladeanteil_prozent` | `pv_anteil_prozent` |
| `vergleich_verbrauch_l_100km` | `benzin_verbrauch_liter_100km` |
| `v2h_faehig` | `nutzt_v2h` |

Migration der DB nicht zwingend nötig (defensive Reads), aber sauberer wenn wir die alten Keys löschen.

---

## Speicher

### Drift-Matrix

| Schlüssel | Form | Wizard | Backend liest | Render |
|---|---|---|---|---|
| `kapazitaet_kwh` | ✓ Z.142 | ✓ Z.328 | invest.py:1014, 1132, 1809; ha_export:325; pdf_ops:237; community_service:134; aktueller_monat:811; energie_profil:1468 | PVAnlageDashboard:285 (seit v3.24.6 ✓), SpeicherDashboard |
| `nutzbare_kapazitaet_kwh` | ✓ Z.143 | – | ha_export:325 (defensive Doppel-Read) | PVAnlageDashboard:286 |
| `max_ladeleistung_kw` | ✓ Z.144 | – | – | – |
| `max_entladeleistung_kw` | ✓ Z.145 | – | – | – |
| `wirkungsgrad_prozent` | ✓ Z.146 | – | invest.py:1015, 1133 | – |
| `arbitrage_faehig` | ✓ Z.147 | ✓ Z.340 | invest.py:1810; ha_import.py:89; field_definitions.py:425 | – |
| `nutzt_arbitrage` | – | – | invest.py:1016, 1134 | – |
| `lade_durchschnittspreis_cent` | – | – | invest.py:1135 | – |
| `entlade_vermiedener_preis_cent` | – | – | invest.py:1136 | – |

### Bugs

5. **🔥 Arbitrage-ROI kaputt** — Form/Wizard schreiben `arbitrage_faehig`. `investitionen.py:1016` (DC-gekoppelter Speicher ROI) und `investitionen.py:1134` (AC-gekoppelter ROI) lesen `nutzt_arbitrage` mit Default False. Dashboard `investitionen.py:1810`, `ha_import.py:89` und `field_definitions.py:425` lesen korrekt `arbitrage_faehig`. **Konsequenz:** User aktiviert Arbitrage im Form/Wizard, ROI ignoriert die Aktivierung. Dashboard zeigt Arbitrage-Sektion korrekt — die Inkonsistenz innerhalb des Backends ist auffällig.
6. **(historisch behoben in v3.24.6)** PV-Cockpit las Speicher-Kapazität unter `batteriekapazitaet_kwh`. Drift-Beispiel #172.
7. **(unkritisch)** `nutzbare_kapazitaet_kwh` ist nur in `ha_export.py:325` als defensiver Fallback definiert. Form schreibt es, sonst keine Lese-Stelle. Funktional egal, aber semantisch unsauber: Form bietet das Feld an, Backend tut nichts damit (außer im HA-Export).

### Kanon-Vorschlag Speicher

| Kanonisch | Backend-Drift-Variante |
|---|---|
| `arbitrage_faehig` | `nutzt_arbitrage` |
| `kapazitaet_kwh` | (konsistent) |
| `nutzbare_kapazitaet_kwh` | (Frontend-only, OK) |

---

## Wärmepumpe

### Drift-Matrix

| Schlüssel | Form | Wizard | Backend liest | Render |
|---|---|---|---|---|
| `leistung_kw` | ✓ Z.151 | ✓ Z.441 | – | WaermepumpeDashboard |
| `wp_art` | ✓ Z.153 | – | – | WaermepumpeDashboard |
| `effizienz_modus` | ✓ Z.155 | – (hardcoded `gesamt_jaz` Z.462) | invest.py:1187, vorschlag_service.py:274 | WaermepumpeDashboard |
| `jaz` | ✓ Z.157 | ✓ Z.455 | invest.py:1236, vorschlag_service.py:278, sensor_mapping.py:202 (defensive) | WaermepumpeDashboard:212, 252 |
| `scop_heizung` | ✓ Z.159 | – | invest.py:1216, vorschlag_service.py:281 | WaermepumpeDashboard |
| `scop_warmwasser` | ✓ Z.160 | – | invest.py:1217, vorschlag_service.py:283 | WaermepumpeDashboard |
| `vorlauftemperatur` | ✓ Z.161 | – | invest.py:1218 | WaermepumpeDashboard |
| `cop_heizung` | ✓ Z.163 | – | invest.py:1197, vorschlag_service.py:286, sensor_mapping.py:202 (defensive Fallback für `jaz`) | WaermepumpeDashboard:252 |
| `cop_warmwasser` | ✓ Z.164 | – | invest.py:1198, vorschlag_service.py:288 | WaermepumpeDashboard:260 |
| `getrennte_strommessung` | ✓ Z.166 (`'true'`/`'false'` als String) | – | vorschlag_service.py:259, 303 | WaermepumpeDashboard:131, 248 |
| `heizwaermebedarf_kwh` | ✓ Z.168 | – | invest.py:1192 | – |
| `warmwasserbedarf_kwh` | ✓ Z.169 | – | invest.py:1193 | – |
| `pv_anteil_prozent` | ✓ Z.171 | – | invest.py:1188 | – |
| `alter_energietraeger` | ✓ Z.172 | – | aussichten.py:1092, 1446; ha_export:242, 598; invest:1189; pdf_ops:418 | – |
| `alter_preis_cent_kwh` | ✓ Z.173 | – | aussichten.py:1091 (default **10.0**); ha_export:241 (default **10.0** auch in Z.597 als 12.0!); invest.py:1190 (default **12**); pdf_ops:417 (default **12.0**) | – |
| `alternativ_zusatzkosten_jahr` | ✓ Z.174 | – | aussichten.py:1094, ha_export:244, 599; invest:1191; pdf_ops:420 | – |
| `sg_ready` | ✓ Z.175 | – | – | – |
| `waermebedarf_kwh` | – | – | invest.py:1238 (Alternative zu Summe) | – |
| `alternativ_kosten_euro` | – | – | aussichten.py:1068 (default 35000), cockpit/uebersicht:362 | – |

### Bugs

8. **⚠ Default-Inkonsistenz `alter_preis_cent_kwh`** — `aussichten.py:1091` und `ha_export.py:241` defaulten auf 10.0, alle anderen auf 12.0. Wenn User den Wert leer lässt, bekommt er je nach Tab unterschiedliche Ersparnis-Berechnungen. Kein Drift in Schlüsseln, aber Default-Drift.
9. **(fragil)** `getrennte_strommessung` wird vom Form als String `'true'`/`'false'` gespeichert (Z.166), vom Dashboard aber als Boolean ausgewertet (Z.131). Funktioniert dank JS-Truthy für `'false'`-String (= truthy!) — d. h. **wenn User „false" wählt, bleibt Dashboard im true-Modus**. Subtiler Bug.

### Kanon-Vorschlag WP

Keys sind grundsätzlich konsistent. Zwei Aufräum-Aktionen:

- Default `alter_preis_cent_kwh` auf einheitlich **12.0** vereinheitlichen.
- `getrennte_strommessung` als echten Boolean speichern (Form anpassen).

---

## Wallbox

### Drift-Matrix

| Schlüssel | Form | Wizard | Backend liest | Render |
|---|---|---|---|---|
| `max_ladeleistung_kw` | ✓ Z.179 | ✓ Z.361 | – | WallboxDashboard:140, 153 |
| `leistung_kw` | – | – | invest.py:2016 (default 11) | – |
| `bidirektional` | ✓ Z.180 | ✓ Z.373 | – | WallboxDashboard (konditional) |
| `pv_optimiert` | ✓ Z.181 | – | – | – |
| `ist_dienstlich` | ✓ Z.182 | – | – | WallboxDashboard |

### Bugs

10. **🔥 Wallbox-Leistung kaputt im Dashboard-ROI** — Form/Wizard schreiben `max_ladeleistung_kw`, `investitionen.py:2016` liest `leistung_kw` mit Default 11. **Konsequenz:** Wallbox-Dashboard zeigt 11 kW unabhängig vom User-Setup.

### Kanon-Vorschlag Wallbox

`max_ladeleistung_kw` als Kanon (Form/Wizard-konsistent), Backend muss umgebaut werden.

---

## Wechselrichter

### Drift-Matrix

| Schlüssel | Form | Wizard | Backend liest | Render |
|---|---|---|---|---|
| `max_leistung_kw` | ✓ Z.186 | ✓ Z.254 | – | PVAnlageDashboard:260 |
| `leistung_ac_kw` | – | – | – (nur im toten Schema invest.py:234) | – |
| `wirkungsgrad_prozent` | ✓ Z.187 | – | – | – |
| `hybrid` | ✓ Z.188 | – | – | – |

### Bugs

Keine Bugs — Backend liest Wechselrichter-Parameter nirgends, alles passiert über Top-Level-Felder. Schema-Definition `leistung_ac_kw` in `investitionen.py:234` ist tot.

### Kanon-Vorschlag

`max_leistung_kw` (Form/Wizard) als Kanon, Schema-Eintrag `leistung_ac_kw` löschen.

---

## PV-Module

### Drift-Matrix

| Schlüssel | Form | Wizard | Backend liest | Render |
|---|---|---|---|---|
| `anzahl_module` | ✓ Z.192 | – | cockpit/uebersicht.py:273 (BKW-Pfad), live-mit-or-1 | PVAnlageDashboard:211 |
| `modul_leistung_wp` | ✓ Z.193 | – | – | – |
| `modul_typ` | ✓ Z.194 | – | – | – |
| `ausrichtung_grad` | ✓ via formData (Z.272) | – | pvgis.py:384, prognosen.py:284, live_wetter.py:161, pv_orientation.py:76 | – |
| `ausrichtung` (text) | – (über Top-Level) | – | pv_orientation.py:87, pv_strings.py:203 | – |
| `neigung_grad` | – (über Top-Level) | – | pv_orientation.py:62, live_wetter.py:155, pv_strings.py:204 | – |
| `neigung` | – | – | live_wetter.py:157 (Fallback) | – |
| `kwp` | – | – | pv_orientation.py:47 | – |
| `leistung_kwp` | – (Top-Level-Feld) | – | sensor_mapping.py:194 | PVAnlageDashboard:62 |

### Bugs

Keine Schreib-/Lese-Drift. **Aber:** Komplexe Lese-Priorität für Ausrichtung (`ausrichtung_grad` numerisch > Top-Level `ausrichtung` Text > Parameter `ausrichtung` Text > Default 0). Sollten wir bei der Vereinheitlichung dokumentieren.

### Kanon-Vorschlag PV-Module

PV-Module sind ein Sonderfall: viele Werte in Top-Level-Feldern (`leistung_kwp`, `ausrichtung`, `neigung_grad`), nur Detail-Werte in `parameter` (`anzahl_module`, `modul_leistung_wp`, `modul_typ`, `ausrichtung_grad`). Konvention beibehalten.

---

## Balkonkraftwerk

### Drift-Matrix

| Schlüssel | Form | Wizard | Backend liest | Render |
|---|---|---|---|---|
| `leistung_wp` | ✓ Z.198 | ✓ Z.485 | invest.py:2111, cockpit/uebersicht:274 | BalkonkraftwerkDashboard |
| `anzahl` | ✓ Z.199 | ✓ Z.499 | invest.py:2112, cockpit/uebersicht:273 | BalkonkraftwerkDashboard |
| `ausrichtung` | ✓ Z.200 | ✓ Z.512 | (über Top-Level) | – |
| `neigung_grad` | ✓ Z.201 | ✓ Z.531 | – | – |
| `hat_speicher` | ✓ Z.202 | ✓ Z.550 | invest.py:2113; ha_import.py:119 | BalkonkraftwerkDashboard |
| `speicher_kapazitaet_wh` | ✓ Z.203 | ✓ Z.567 | invest.py:2114 | BalkonkraftwerkDashboard |

### Bugs

Keine Drift. BKW-Block ist sauber.

---

## Sonstiges

### Drift-Matrix

| Schlüssel | Form | Wizard | Backend liest | Render |
|---|---|---|---|---|
| `kategorie` | ✓ Z.207 | – | invest:2208; ha_import:127; field_definitions:415, 480; energie_profil:79, 725; live_tagesverlauf_service:142, 498; energie_profil_service:752; cockpit/komponenten:225 | MonatsabschlussForm |
| `beschreibung` | ✓ Z.208 | – | invest.py:2209 | MonatsabschlussForm:771 |

### Bugs

Keine. Top-Konsistenz-Beispiel — `kategorie` wird an 9 Backend-Stellen mit demselben Key gelesen.

---

## Stamm-/Infothek-Keys (Migrations-Altlast)

`infothek_migration.py` migriert alte `stamm_*`-Keys aus dem Investitions-Parameter in die separate Infothek-Tabelle. Diese Keys sind **deprecated**, aber Migrations-Code muss sie weiter erkennen können.

| Schlüssel | Lese-Stelle |
|---|---|
| `stamm_mastr_id` | infothek_migration.py:136 |
| `stamm_notizen` | infothek_migration.py:201 |
| `stamm_*` (alle) | infothek_migration.py:161 (Iteration über `ALLE_MIGRIER_KEYS`) |

**Empfehlung:** `ALLE_MIGRIER_KEYS` aus `infothek_migration.py` als deprecated markieren, NICHT in Constants-Modul aufnehmen. Migrations-Pfad bleibt funktional bis alle DBs migriert sind.

---

## Summary: Bug-Liste für Phase 6

| # | Severity | Bereich | Was passiert |
|---|---|---|---|
| 1 | 🔥 hoch | E-Auto V2H | `nutzt_v2h` vs `v2h_faehig` — V2H-Flag im ROI / Aussichten / Live ignoriert |
| 2 | 🔥 hoch | E-Auto Fahrleistung | `km_jahr` vs `jahresfahrleistung_km` — ROI nutzt Default 15000 |
| 3 | 🔥 hoch | E-Auto PV-Anteil | `pv_anteil_prozent` vs `pv_ladeanteil_prozent` — ROI nutzt Default 60 |
| 4 | 🔥 hoch | E-Auto Vergleichsverbrauch | `benzin_verbrauch_liter_100km` (ROI) vs `vergleich_verbrauch_l_100km` (Aussichten) — ROI nutzt Default 7.0 |
| 5 | 🔥 hoch | Speicher Arbitrage | `nutzt_arbitrage` (ROI) vs `arbitrage_faehig` (Form/Wizard/Dashboard) — ROI ignoriert Form-Aktivierung |
| 6 | 🔥 hoch | Wallbox Leistung | `leistung_kw` (Dashboard) vs `max_ladeleistung_kw` (Form/Wizard) — Dashboard immer 11 kW Default |
| 7 | ⚠ mittel | WP `alter_preis_cent_kwh` | Default-Drift 10.0 (aussichten/ha_export241) vs 12.0 (rest) |
| 8 | ⚠ mittel | WP `getrennte_strommessung` | String `'false'` vs Boolean — `'false'` ist truthy in JS |
| 9 | (i) Info | Speicher `nutzbare_kapazitaet_kwh` | Form schreibt, nur ha_export.py defensive liest, sonst nirgends |

**6 echte Bugs**, davon mehrere mit User-sichtbarer ROI-/Dashboard-Verfälschung. Plus 2 Default-Konsistenz-Issues, 1 semantisches Issue.

---

## Empfehlung Phase 1+

Die Inventur bestätigt die Vermutung aus dem Plan: **das Refactoring entdeckt mehrere Production-Bugs**, die sonst weiter im Code verborgen bleiben. Einzelne dieser Bugs (V2H-Drift) hat schon ein „Pflaster" (defensiver Doppel-Read in `ha_import.py:80`), aber drei Code-Pfade (Aussichten, Live, ROI) sind ungeschützt.

**Migrations-Strategie pro Bug:**

- **Bugs 1, 5, 6:** Backend-Lese-Stellen auf Form-Kanon umstellen (Konstante + Refactor). Optionale DB-Migration, die alte Keys löscht — bestehende Anlagen haben nur den neuen Key gespeichert (Bug-Folge: alte Keys waren im Frontend-Form gar nicht sichtbar), Migration ist Reinigungs-Aktion ohne Datenverlust.
- **Bugs 2, 3, 4:** Wie 1, identisches Vorgehen.
- **Bug 7:** Default vereinheitlichen, keine Migration.
- **Bug 8:** Form auf Boolean umstellen, Migration `String → Bool`.
- **Bug 9:** Form-Feld behalten (User schätzt nutzbare Kapazität), aber dokumentieren dass es nur in HA-Export verwendet wird — oder weiter ausbauen.

Phase 6 sollte **alle 6 Hot-Bugs in einer eigenen DB-Migration** abdecken: alte Keys lesen, neue Keys schreiben, alte löschen. Für jede Anlage einmalig beim Start. Die Migration ist Voraussetzung dafür, dass das Constants-Modul den alten Key nicht mehr exportiert.

**Geschätzter Mehraufwand für Phase 6:** Plus 2-3 h auf die ursprüngliche Schätzung, weil die Migration sauber idempotent + getestet werden muss.

**Neuer Gesamtaufwand v3.25.0: 7-9 h**, plus Test-/Validierungs-Zeit nach Deployment.
