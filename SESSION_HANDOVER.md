# Session-Übergabe: Auswertungen Bereinigung

**Datum:** 2026-02-09
**Status:** Phase 1-3 ERLEDIGT, Tests ausstehend

---

## Was wurde gemacht?

### Problem: Datenquellen-Chaos
Die Cockpit-Endpoints mischten inkonsistent `Monatsdaten` und `InvestitionMonatsdaten`.
- Speicher-Daten kamen aus `Monatsdaten.batterie_*` (redundant!)
- E-Auto, WP etc. hatten keine detaillierten Auswertungen

### Lösung implementiert

#### Phase 1: Backend bereinigt
**Datei:** `eedc/backend/api/routes/cockpit.py`

1. **`get_cockpit_uebersicht`** (ab Zeile ~50):
   - Lädt jetzt ALLE InvestitionMonatsdaten in einer Query
   - Speicher-Daten aus InvestitionMonatsdaten statt Monatsdaten
   - PV-Erzeugung bevorzugt InvestitionMonatsdaten (PV-Module), Fallback auf Monatsdaten
   - Zeitraum aus InvestitionMonatsdaten abgeleitet

2. **`get_nachhaltigkeit`** (ab Zeile ~200):
   - Iteriert über InvestitionMonatsdaten statt Monatsdaten
   - Monatsdaten nur noch für Einspeisung/Netzbezug

3. **`get_komponenten_zeitreihe`** (ab Zeile ~300):
   - Neue Felder im `KomponentenMonat` Schema:
     ```python
     # Speicher
     speicher_arbitrage_kwh: float
     speicher_arbitrage_preis_cent: Optional[float]

     # E-Auto
     emob_ladung_pv_kwh: float
     emob_ladung_netz_kwh: float
     emob_ladung_extern_kwh: float
     emob_ladung_extern_euro: float
     emob_v2h_kwh: float

     # Wärmepumpe
     wp_heizung_kwh: float
     wp_warmwasser_kwh: float

     # Balkonkraftwerk
     bkw_speicher_ladung_kwh: float
     bkw_speicher_entladung_kwh: float

     # Alle
     sonderkosten_euro: float
     ```
   - Neue Feature-Flags: `hat_arbitrage`, `hat_v2h`

#### Phase 2: Frontend API-Types erweitert
**Datei:** `eedc/frontend/src/api/cockpit.ts`

- `KomponentenMonat` Interface erweitert mit allen neuen Feldern
- `KomponentenZeitreihe` Interface mit `hat_arbitrage`, `hat_v2h`

#### Phase 3: Frontend KomponentenTab erweitert
**Datei:** `eedc/frontend/src/pages/auswertung/KomponentenTab.tsx`

1. **Speicher-Sektion:**
   - Arbitrage-Badge im Header
   - Arbitrage-KPI-Karte
   - Arbitrage-Balken im Chart

2. **E-Mobilität-Sektion:**
   - V2H-Badge im Header
   - Zweite KPI-Zeile mit Ladequellen (PV/Netz/Extern)
   - V2H-Entladung mit Ersparnis
   - Gestapeltes Chart statt Gesamt-Ladung

3. **Wärmepumpe-Sektion:**
   - Zweite KPI-Zeile (Heizung vs. Warmwasser)
   - Gestapeltes Chart (Heizung + Warmwasser)

4. **Balkonkraftwerk-Sektion:**
   - "mit Speicher"-Badge
   - Speicher-KPIs (Ladung, Entladung, Effizienz)
   - Speicher-Balken im Chart

---

## Build-Status

```bash
# Frontend baut erfolgreich:
cd eedc/frontend && npm run build
# ✓ built in 3.67s
```

---

## Nächste Schritte (optional)

1. **Backend testen:**
   ```bash
   cd eedc && source backend/venv/bin/activate
   uvicorn backend.main:app --reload --port 8099
   ```

2. **Frontend testen:**
   ```bash
   cd eedc/frontend && npm run dev
   ```

3. **Zu prüfen:**
   - Funktioniert die Cockpit-Übersicht mit echten Daten?
   - Werden Arbitrage/V2H-Badges korrekt angezeigt?
   - Sind die gestapelten Charts lesbar?

4. **Offene Punkte (siehe PLAN_AUSWERTUNGEN_BEREINIGUNG.md):**
   - [ ] PV-String-Vergleich Endpoint
   - [ ] Arbitrage-Erlös berechnen
   - [ ] Sonderkosten in Finanzen-Tab

---

## Geänderte Dateien

```
Backend:
  eedc/backend/api/routes/cockpit.py          # Hauptänderungen

Frontend:
  eedc/frontend/src/api/cockpit.ts            # TypeScript Types
  eedc/frontend/src/pages/auswertung/KomponentenTab.tsx  # UI

Dokumentation:
  CLAUDE.md                                    # Projekt-Kontext aktualisiert
  PLAN_AUSWERTUNGEN_BEREINIGUNG.md            # Detaillierter Plan mit Status
  SESSION_HANDOVER.md                          # Diese Datei
```

---

## Git-Status

```bash
# Uncommitted changes - bitte vor Commit prüfen:
git status
git diff --stat
```

**Empfohlener Commit:**
```bash
git add -A
git commit -m "feat: Auswertungen Bereinigung - InvestitionMonatsdaten als primäre Quelle

- Backend: get_cockpit_uebersicht, get_nachhaltigkeit korrigiert
- Neue Felder: Arbitrage, V2H, Heizung/WW, BKW-Speicher
- Frontend: KomponentenTab mit erweiterter Darstellung
- Badges für Arbitrage, V2H, BKW-Speicher
- Gestapelte Charts für Ladequellen und Wärmeerzeugung

Dokumentation: PLAN_AUSWERTUNGEN_BEREINIGUNG.md
"
```
