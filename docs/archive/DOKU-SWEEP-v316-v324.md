# Doku-Sweep v3.16 → v3.24 — Feature-Delta vs. In-App-Hilfe

> **Zweck:** Arbeitsdokument für den Doku-Sweep nach Aktivierung der In-App-Hilfe (#130, v3.24.0).
> **Stand:** 2026-04-28. Basis: CHANGELOG.md v3.16.0–v3.24.1 vs. die 8 in `scripts/sync-help.sh` kuratierten Dokumente.

## Schnell-Befund

| Hilfe-Dokument | Aktualität | Größte Lücken |
|---|---|---|
| `BENUTZERHANDBUCH.md` | Versionsstempel v3.24.1, Inhalt v3.x-Kompendium | Lifecycle-Block (in-App-Hilfe selbst), neue Auswertungs-/Aussichten-Tabs |
| `HANDBUCH_INSTALLATION.md` | Versionsstempel v3.24.1 | Empfohlene-Nutzung-Hinweis fehlt im Installations-Teil; SFML/Solcast-Setup nicht beschrieben |
| `HANDBUCH_BEDIENUNG.md` | Footer „März 2026" — aus dem letzten Großupdate hängengeblieben | Aussichten-Tab „Prognosen" (Solcast/MAE/Asymmetrie) komplett fehlt; Auswertung→Energieprofile nicht beschrieben; Cockpit-Reihenfolge v3.23.4-Umsortierung; ROI-Seite-Aufräum (#140); In-App-Hilfe nicht erwähnt |
| `HANDBUCH_EINSTELLUNGEN.md` | Hat 16 Treffer für „MAE/MBE" — vermutlich abschnittsweise frisch | Kapitel 1.6 „Allgemein" ist entkernt → neue **Energieprofil-Seite** + Datenverwaltungs-Bündel; Sensor-Mapping Solcast-Toggle, Strompreis-Sensor, JAZ-Wording, „ohne Statistik"-Badge, Fallback-Link „alle Sensoren"; Daten-Checker neue Kategorien |
| `HANDBUCH_INFOTHEK.md` | Versionsstempel v3.24.1, Etappe 3.6 dokumentiert | Aktuell stabil — kein Sweep-Bedarf erkennbar |
| `BERECHNUNGEN.md` | Solcast/Strompreis/Kraftstoffpreis/JAZ erwähnt | Lernfaktor-MOS-Kaskade (saisonal) nicht beschrieben; Backward-Slot-Konvention; PR-Formel auf GTI; Asymmetrie-Diagnostik |
| `SENSOR-REFERENZ.md` | — | Strompreis-Sensor, Solcast-Sensor (BJReplay), WP-Kompressor-Starts (Counter, kein kWh!), `state_class`/LTS-Logik (Sichtbarkeit ohne LTS) |
| `GLOSSAR.md` | JAZ + Kraftstoffpreis erwähnt | Lernfaktor, MAE/MBE, Bias, GTI vs. GHI, Snapshot/Backward-Slot, §51 Negativpreis, Day-Ahead, Asymmetrie |

## Inventur der Features (v3.16 → v3.24)

> **Legende:** ✅ vorhanden · ⚠ teilweise · ❌ fehlt · 💬 nur erwähnt, kein Detail

### Cluster 1 — Prognosen (Solcast / Genauigkeit / Lernfaktor)

| Feature | Release | Welches Hilfe-Dok? | Stand |
|---|---|---|---|
| Aussichten-Tab **„Prognosen"** (OM / EEDC / Solcast / IST) | v3.16.4–v3.16.6 | HANDBUCH_BEDIENUNG §7 | ❌ |
| **Solcast** Anbindung (API + HA-Sensor BJReplay), Wizard-Toggle | v3.16.4–v3.16.6 | HANDBUCH_EINSTELLUNGEN §3 | ❌ |
| **EEDC-Lernfaktor** (kalibrierter OM-Wert) | v3.16 | HANDBUCH_BEDIENUNG §7 + BERECHNUNGEN | ❌ |
| **Saisonale MOS-Kaskade** (Monat → Quartal → 30-Tage) | v3.16.15 | BERECHNUNGEN | ❌ |
| **MAE + MBE getrennt** + 3 Quellen (#151) | v3.22.0 | HANDBUCH_BEDIENUNG §7 + BERECHNUNGEN + GLOSSAR | ⚠ EINSTELLUNGEN hat 16 Treffer — Position prüfen |
| **Asymmetrie-Diagnostik** (Variante B, Toggle Kompakt/Diagnostisch) | v3.23.3 | HANDBUCH_BEDIENUNG §7 + GLOSSAR | ❌ |
| **VM/NM-Split an Solar Noon** (statt 12:00 hart) | v3.22.0 | BERECHNUNGEN | ❌ |
| **Banner Restzeit Lernfaktor** („3 von 7 Tagen, noch 4 Tage") | v3.22.0 | HANDBUCH_BEDIENUNG §7 | ❌ |
| **Klickbarer Reparatur-Popover** bei IST-Datenlücke (⚠ →) | v3.23.0 | HANDBUCH_BEDIENUNG §7 | ❌ |
| **Backward-Slot-Konvention** (alle Quellen [N-1, N)) | v3.20.0 (#144) | BERECHNUNGEN + GLOSSAR | ❌ |

### Cluster 2 — Energieprofil (Etappe 3 + Snapshot-Architektur + Tagesreport)

| Feature | Release | Welches Hilfe-Dok? | Stand |
|---|---|---|---|
| **kWh aus Zähler-Snapshots** (statt W-Integration, #135) | v3.19.0 | BERECHNUNGEN + HANDBUCH_BEDIENUNG | ❌ |
| **Phase D Cleanup** (W-Fallback weg, Feature-Flag entfernt) | v3.21.0 | nur intern relevant | – |
| **Strikte NULL-Semantik** + ⚠ Badge bei Datenlücken | v3.19.0 | HANDBUCH_BEDIENUNG §5/§7 | ❌ |
| **Snapshot-Restart-Recovery** (verpasste :05/:55) | v3.23.0 | HANDBUCH_INSTALLATION §6 (Fehlerbehebung) | ❌ |
| **Snapshot-Lücken-Interpolation** (#145) | v3.20.0 | nur intern | – |
| **:55-Live-Preview** (laufende Stunde sofort sichtbar) | v3.21.0 (#146) | HANDBUCH_BEDIENUNG §5 | ❌ |
| **Pro-Tag-Reaggregation per Knopf** | v3.21.0 (#146) | HANDBUCH_EINSTELLUNGEN §1.6 / Energieprofil-Seite | ❌ |
| **Tage-Tabelle** im Auswertungs-Monat-Tab (#148) | v3.21.0 | HANDBUCH_BEDIENUNG §5 (Energieprofile-Tab) | ❌ |
| **CollapsibleSection** in Energieprofil-Monat | v3.21.0 | HANDBUCH_BEDIENUNG §5 | ❌ |
| **Verbrauchsprognose** (Sub-Tab Prognose, Etappe 3b) | v3.16.16 | HANDBUCH_BEDIENUNG §5 | ❌ |
| **Tagesreset-Heuristik** für utility_meter daily cycle | v3.23.0 | HANDBUCH_INSTALLATION §6 / HANDBUCH_EINSTELLUNGEN §3.3 | ❌ |
| **WP-Kompressor-Starts-KPI** (Stunde/Tag/Monat, #136) | v3.24.0 | HANDBUCH_BEDIENUNG §5 + HANDBUCH_EINSTELLUNGEN §3 + SENSOR-REFERENZ | ❌ |

### Cluster 3 — Navigation / Datenverwaltung

| Feature | Release | Welches Hilfe-Dok? | Stand |
|---|---|---|---|
| **Eigene Energieprofil-Seite** (Daten-Tab, #133) | v3.18.0 | HANDBUCH_EINSTELLUNGEN §1 — neuer Abschnitt | ❌ |
| **Tab-Konsolidierung** (Monatsabschluss-Tab raus, Energieprofil-Tab rein) | v3.18.0 | HANDBUCH_EINSTELLUNGEN §1 | ❌ |
| **Allgemein-Tab entkernt** (Datenbestand-Block raus) | v3.18.0 | HANDBUCH_EINSTELLUNGEN §1.6 | ⚠ Beschreibt evtl. noch alten Stand |
| **Vollbackfill / Daten-löschen anlage-spezifisch** | v3.18.0 | HANDBUCH_EINSTELLUNGEN §1.6 / Energieprofil | ❌ |
| **Kraftstoffpreis-Backfill** (separate Tages/Monats-Endpoints) | v3.18.0 | HANDBUCH_EINSTELLUNGEN | ❌ |
| **In-App-Hilfe-Seite** (#130) — Selbstreferenz | v3.24.0 | BENUTZERHANDBUCH (Übersicht) | ❌ |
| **„Empfohlene Nutzung"-Hinweis** (datendichte App, Desktop) | v3.23.7 (README) + v3.24.1 (Handbuch) | BENUTZERHANDBUCH ✅ + HANDBUCH_INSTALLATION §1 fehlt | ⚠ |

### Cluster 4 — Strompreis / Finanzen / ROI

| Feature | Release | Welches Hilfe-Dok? | Stand |
|---|---|---|---|
| **Strompreis-Sensor** (Tibber/aWATTar/EPEX) im Sensor-Mapping | v3.16.0 | HANDBUCH_EINSTELLUNGEN §3.1 + SENSOR-REFERENZ | ⚠ erwähnt, nicht detailliert |
| **EPEX-Börsenpreis-Overlay** (Tagesverlauf, Live + auch ohne Sensor) | v3.16.0, v3.20.1 | HANDBUCH_BEDIENUNG §2 (Live-Dashboard) | ⚠ |
| **§51 EEG Negativpreis-KPIs** | v3.16.0 | BERECHNUNGEN + GLOSSAR | ⚠ in BERECHNUNGEN |
| **Stündliche Strompreis-Mitschrift** | v3.16.0 | BERECHNUNGEN | ⚠ |
| **Kraftstoffpreis (EU Oil Bulletin)** | v3.16.16 → v3.17.0 | BERECHNUNGEN ✅ + HANDBUCH_BEDIENUNG (Aussichten) | ⚠ |
| **WP-Alternativ-Zusatzkosten** + **Monats-Gaspreis** (#141) | v3.21.0 | HANDBUCH_INSTALLATION §3.6 (WP-Setup) + HANDBUCH_EINSTELLUNGEN §1.4 | ❌ |
| **WP-Anschaffungsdatum-Filter** (#153) — historische Aggregate | v3.23.0 → v3.23.1 | BERECHNUNGEN (WP-Sektion) | ❌ |
| **ROI-Seite Aufräum** (Cockpit + Investitionen, 2 Amortisations-Sichten, #140) | v3.21.0 | HANDBUCH_BEDIENUNG §5.6 + BERECHNUNGEN | ⚠ alte Beschreibung |
| **WP-/E-Auto-/BKW-Ersparnisse in MQTT-Jahresersparnis** | v3.19.1 | HANDBUCH_EINSTELLUNGEN §5 (MQTT) | ⚠ |
| **„Sicht"-Tooltip** in allen ROI-Anzeigen | v3.19.1 | HANDBUCH_BEDIENUNG §3 / §5.6 | ❌ |

### Cluster 5 — Sensor-Mapping / Daten-Checker / HA

| Feature | Release | Welches Hilfe-Dok? | Stand |
|---|---|---|---|
| **JAZ statt COP** durchgängig (Sensor-Mapping, Wizard, KPIs) | v3.23.4 → v3.23.8 | HANDBUCH_EINSTELLUNGEN §3.4 + GLOSSAR ✅ | ⚠ Wording im Handbuch checken |
| **Sensor-Filter aufgeweicht** + „ohne Statistik"-Badge + Fallback-Link | v3.24.1 | HANDBUCH_EINSTELLUNGEN §3.3 | ❌ |
| **Setup-Wizard ↔ InvestitionForm Key-Drift Fix** (#167) | v3.23.8 | nur intern | – |
| **Daten-Checker MQTT-Topic-Abdeckung** (#134) | v3.23.7 | HANDBUCH_EINSTELLUNGEN (Daten-Checker-Sektion fehlt evtl. ganz) | ❌ |
| **Daten-Checker Sensor-Mapping HA-Statistics** (LTS-Verfügbarkeit) | v3.24.1 | HANDBUCH_EINSTELLUNGEN | ❌ |
| **Daten-Checker Energieprofil-Zähler-Abdeckung** | v3.19.0 | HANDBUCH_EINSTELLUNGEN | ❌ |
| **HA-Statistics-Monatswert nutzt sum-Spalte** (Tagesreset-Bug) | v3.23.8 | nur intern (oder Hinweis in Fehlerbehebung) | – |
| **Konsolidierte Download-Helper** (HA-Companion-iOS-401) | v3.23.2 | HANDBUCH_INSTALLATION §6 (Fehlerbehebung) | ❌ |

### Cluster 6 — UI / Kosmetik (meist nicht handbuch-relevant, hier nur als Sammlung)

| Feature | Release | Doku? |
|---|---|---|
| Mobile-Hinweis Prognosen-Tab (#165) | v3.23.8 | – |
| `h-screen` → `h-dvh` (#161) | v3.23.6 | – |
| Scroll-to-Top zentral | v3.23.6 | – |
| Cockpit-Tab-Reihenfolge umsortiert (#156) | v3.23.4 | HANDBUCH_BEDIENUNG §3 — Reihenfolge prüfen |
| Live-Heute Bilanz-Sortierung + EV-Cap (#157) | v3.23.5 | HANDBUCH_BEDIENUNG §2 | ⚠ |
| Stunden-Aggregation IST von „last" auf „mean" | v3.23.6 | BERECHNUNGEN | – |
| Card-Border-Radius-Clipping | v3.23.0–v3.23.7 | – |
| Sunset/Alps-Effekt-Layer Clipping | v3.23.7–v3.23.8 | – |

## Querschnittsthemen — getrennt vom Sweep

### A) „What's new"-Banner nach Update — offen aus Discussion #130
Safi105 (Folge-Reply 2026-04-24): Banner nach Update mit Klick auf neue Funktion. **Status:** nicht zugesagt, nicht in Roadmap #110. Naheliegend nach dem Doku-Sweep, weil ein guter Banner einen guten Changelog-Auszug braucht. → Eigenes Konzept-Dokument vorschlagen, wenn der Sweep durch ist.

### B) BFSG-Wording-Regel
Bei allen Anzeigezoom-/Mobile-Passagen technische App-Eigenschaft formulieren („datendichte Analyse-App, Desktop empfohlen") — keine Aussagen zu Barrierefreiheit / Accessibility. Vorlage: README v3.23.7-Block.

### C) Wo „Empfohlene Nutzung" noch fehlt
- ✅ `README.md` (Root)
- ✅ `eedc/README.md` (Standalone)
- ✅ `BENUTZERHANDBUCH.md`
- ❌ `HANDBUCH_INSTALLATION.md` — wäre dort als „1.x Empfohlene Hardware/Nutzung" ein guter Platz, weil neue Nutzer hier zuerst landen.

### D) Footer-Datum hängt
`HANDBUCH_BEDIENUNG.md` hat den Footer „Letzte Aktualisierung: März 2026" trotz Versionsstempel v3.24.1. Beim Sweep mit-aktualisieren.

## Empfohlene Reihenfolge des Sweeps

Drei Pakete in dieser Reihenfolge — jedes ist in sich abgeschlossen, kann committet und die Hilfe neu synct werden:

1. **Bedienung-Sweep** (`HANDBUCH_BEDIENUNG.md`) — größter Impact, weil das die Tester am häufigsten lesen. Aussichten §7 + Auswertung §5 (Energieprofile-Tab) + Cockpit §3 (Reihenfolge) + Live §2 (Sortierung/EV-Cap-Wording). Footer-Datum mit aktualisieren.

2. **Einstellungen-Sweep** (`HANDBUCH_EINSTELLUNGEN.md`) — neue Energieprofil-Seite, Datenverwaltungs-Bündel, Daten-Checker-Kategorien, Sensor-Mapping-Wizard inkl. Solcast-Toggle/Strompreis/JAZ/„ohne Statistik"-Badge.

3. **Referenz-Sweep** (`BERECHNUNGEN.md` + `SENSOR-REFERENZ.md` + `GLOSSAR.md`) — Lernfaktor-MOS-Kaskade, GTI-PR, Backward-Slot, MAE/MBE/Asymmetrie, JAZ, §51 Negativpreis. SENSOR-REFERENZ um Strompreis-/Solcast-/WP-Kompressor-Sensor erweitern. GLOSSAR-Begriffe ergänzen.

4. **Installation-Patch** (`HANDBUCH_INSTALLATION.md`) — kleiner: „Empfohlene Nutzung"-Block + zwei Fehlerbehebungs-Einträge (Snapshot-Restart, HA-Companion-Download).

5. **Übersicht-Patch** (`BENUTZERHANDBUCH.md`) — Lifecycle-Block der In-App-Hilfe selbst (kurze Selbstbeschreibung), Verweise auf neue Sektionen der Detail-Handbücher.

## Was dieser Sweep NICHT umfasst

- `KONZEPT-*.md` Dokumente — interne Architektur-Skizzen, sind nicht in der In-App-Hilfe.
- `ARCHITEKTUR.md`, `DEVELOPMENT.md`, `SETUP_DEVMACHINE.md`, `RELEASE-WORKFLOW.md` — Entwickler-Doku.
- `MQTT_INBOUND.md` — referenziert, aber nicht in der Hilfe-Liste; gehört zu Sensor-/HA-Sektion.
- `KONSISTENZ-ANALYSE-DATENPFADE.md` — interner Audit.
