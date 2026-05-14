
# eedc Benutzerhandbuch

**Version 3.24.1** | Stand: April 2026

---

## Über diese Hilfe

Du liest gerade das **eedc-Benutzerhandbuch** — die Übersicht über die ganze Dokumentation. Wenn du die Seite über den Hauptmenü-Punkt **Hilfe** geöffnet hast (eingeführt in v3.24.2, Discussion #130), läuft sie als In-App-Hilfe direkt in eedc: alle Inhalte werden lokal gerendert, ohne externen Browser-Tab und ohne Ingress-Login-Stolpersteine in der HA-Companion-App.

**Bedienung der Hilfe-Seite:**
- **Sidebar (Desktop) / Dropdown (Mobile)** links: Auswahl des Dokuments aus drei Kategorien — *Einstieg*, *Handbuch*, *Referenz*.
- **URL-Parameter `?doc=<slug>`**: Direktlinks teilbar. Beispiel `?doc=bedienung#7-aussichten-prognosen` öffnet die Bedienungs-Seite und scrollt direkt zum Prognosen-Tab.
- **Markdown-Links** zwischen den Hilfe-Dokumenten werden intern aufgelöst, externe `.md`-Verweise (z. B. zu Konzept-Dokumenten) leiten zur GitHub-Quelle weiter.

**Synchronisation:** Single Source of Truth ist `docs/` im Projekt-Repo. Beim Release-Build kopiert `scripts/sync-help.sh` die kuratierten Dokumente nach `eedc/frontend/public/help/`. Damit ist die in-App-Hilfe immer auf dem Stand der laufenden Version. Die Web-Version unter [supernova1963.github.io/eedc-homeassistant](https://supernova1963.github.io/eedc-homeassistant/) (Astro Starlight) wird parallel aus denselben Quellen erzeugt.

---

## Empfohlene Nutzung

eedc ist eine **datendichte Analyse-App** — viele KPIs nebeneinander, feinachsige Charts, Tabellen mit vielen Spalten. Optimal nutzbar auf **Desktop**. Smartphone in Standard-Anzeigegröße funktioniert für Live-Dashboard, Cockpit und Monatsberichte; für die datendichten Auswertungs-Bereiche (Auswertung → Energieprofil, Aussichten → Prognosen) ist ein größerer Bildschirm sinnvoll. Im Hochformat zeigt eedc für die drei datendichten Tabellen im Prognosen-Tab statt überlappender Spalten einen Hinweis „Querformat oder Desktop nutzen".

Bei stark erhöhtem Anzeigezoom (iOS „Größerer Text", HA-Companion-Seitenzoom über Standard) können einzelne Layouts eng werden — bewusste Designentscheidung statt Layout-Patches, die den datendichten Charakter aufweichen würden.

---

## Inhalt

Die Doku ist in vier Teile, ein Zusatz-Modul, zwei Referenzen und ein Glossar gegliedert:

### Einstieg

- **Diese Übersicht** — was wo zu finden ist.

### Handbuch (Teile I–IV)

| Teil | Inhalt | Link |
|---|---|---|
| **Teil I: Installation & Einrichtung** | Einführung, „Empfohlene Nutzung", Installations-Optionen (HA Add-on / Docker / Dev), Setup-Wizard, Monatsabschluss-Wizard, Fehlerbehebung. | [HANDBUCH_INSTALLATION.md](HANDBUCH_INSTALLATION.md) |
| **Teil II: Bedienung** | Navigation, Live Dashboard mit Bilanz-Sortierung, Cockpit-Dashboards (Übersicht + 8 Komponenten-Tabs), Monatsberichte (ehemals „Aktueller Monat", seit v3.12.0), Auswertungen (8 Tabs inkl. Energieprofil-Beta), Community, Aussichten (5 Tabs inkl. Prognosen-Vergleich), Infothek, Hilfe. | [HANDBUCH_BEDIENUNG.md](HANDBUCH_BEDIENUNG.md) |
| **Teil III: Einstellungen & Sensormapping** | Einstellungen-Tabs (Anlage, Strompreise, Investitionen, Monatsdaten, Solarprognose, Energieprofil-Seite, Allgemein), Datenerfassung, Sensor-Mapping mit Solcast-Toggle und Strompreis-Sensor, HA-Statistik-Import, MQTT-Inbound + Gateway, Daten-Checker mit 8 Kategorien (inkl. MQTT-Topic-Abdeckung und HA-Statistics-Sensor-Mapping), Protokolle, Energieprofile-Hintergrund (Snapshot-Architektur, Backward-Slot-Konvention, Restart-Recovery). | [HANDBUCH_EINSTELLUNGEN.md](HANDBUCH_EINSTELLUNGEN.md) |
| **Modul: Infothek** | Verträge, Zähler, Kontakte und Dokumente rund um die Energieversorgung verwalten. 14 Kategorien mit Vorlagen, Datei-Upload (Fotos & PDFs), N:M-Verknüpfung mit Investitionen, PDF-Export. | [HANDBUCH_INFOTHEK.md](HANDBUCH_INFOTHEK.md) |

### Referenz

| Dokument | Inhalt | Link |
|---|---|---|
| **Berechnungen & Kennzahlen** | Datenmodell, Berechnungs-Formeln pro Thema (Energie-Bilanz, Finanzen, Speicher, E-Auto, Wärmepumpe inkl. Alternativ-Zusatzkosten und Monats-Gaspreis, ROI, USt, CO2, PV-SOLL-IST, Sonstige Positionen), Prognosen inkl. **Lernfaktor / MOS-Kaskade / MAE/MBE / Asymmetrie** (§4.1c), Tarif-System, Energieprofil-Berechnungen mit Snapshot-Architektur und Backward-Slot, Debugging-Leitfaden. | [BERECHNUNGEN.md](BERECHNUNGEN.md) |
| **Sensor-Referenz** | Feldnamen, Einheiten und Anforderungen pro Komponente. Counter vs. kWh-Trennung, LTS-Verfügbarkeit, Solcast-Anbindung, Vorzeichen-Konvention. | [SENSOR-REFERENZ.md](SENSOR-REFERENZ.md) |

### Glossar

| Dokument | Inhalt | Link |
|---|---|---|
| **Glossar & Support** | Begriffserklärungen in 8 thematischen Gruppen (Energie & Bilanzen, Strahlung & Wetter, Prognosen, Komponenten, Strompreise, Snapshots, Integration, Sonstiges) und Support-Anlaufstellen. | [GLOSSAR.md](GLOSSAR.md) |

---

## Was ist neu seit v3.16?

Wer mit einer älteren eedc-Version vertraut ist und einen schnellen Überblick über die wichtigsten Änderungen sucht: dieser Abschnitt fasst die für Anwender sichtbaren Neuerungen der letzten Monate als Schnellübersicht zusammen. Eine **detaillierte, pro-Version gegliederte Beschreibung** mit kurzen Erklärungs-Absätzen findest du auf der eigenen Seite [Was ist neu](WAS-IST-NEU.md).

| Bereich | Änderung | Ab Version | Wo dokumentiert |
|---|---|---|---|
| Hilfe | In-App-Hilfe-Seite (`/hilfe`) mit kuratierter Doku | v3.24.2 | Diese Seite |
| Aussichten | Neuer Tab **„Prognosen"** (OpenMeteo / eedc kalibriert / Solcast / IST), MAE+MBE getrennt, Asymmetrie-Diagnostik, Reparatur-Popover bei IST-Lücken | v3.16.4 → v3.23.3 | [Bedienung §7.2](HANDBUCH_BEDIENUNG.md#72-prognosen) |
| Auswertung | Neuer Tab **„Energieprofil"** (Beta) mit Tagesdetail / Monat (CollapsibleSection, Tage-Tabelle) / Verbrauchsprognose | v3.16.16 → v3.21.0 | [Bedienung §5.8](HANDBUCH_BEDIENUNG.md#58-energieprofil-tab-beta) |
| Cockpit | Reihenfolge der Sub-Tabs umsortiert (Erzeuger oben, Speicher in der Mitte, Verbraucher unten); WP-KPIs in fester Reihenfolge JAZ → Wärme → Strom → Ersparnis; Anlagenname als h1 | v3.23.4 | [Bedienung §3](HANDBUCH_BEDIENUNG.md#3-cockpit-dashboards) |
| Cockpit | Aggregate ignorieren Monatsdaten **vor dem Anschaffungsdatum** der Komponente | v3.23.0 → v3.23.1 | [Bedienung §3.6 / §3.5](HANDBUCH_BEDIENUNG.md#36-wärmepumpe-dashboard) |
| Live | Bilanz-Sortierung der Tageswerte; Eigenverbrauchs-Quote auf 100 % gecappt; EPEX-Börsenpreis-Overlay automatisch | v3.16.0 → v3.23.5 | [Bedienung §2](HANDBUCH_BEDIENUNG.md#2-live-dashboard) |
| Sensor-Mapping | Strompreis-Sensor (dynamische Tarife), Solcast-Toggle, JAZ-Wording, „ohne Statistik"-Badge, Fallback-Link „alle Sensoren" | v3.16.0 → v3.24.1 | [Einstellungen §3](HANDBUCH_EINSTELLUNGEN.md#3-sensor-mapping) |
| Energieprofil | Stunden-kWh aus kumulativen **Zähler-Snapshots** statt 10-Min-Leistungs-Integration (Genauigkeit ~0,1 % statt ~9 % Drift) | v3.19.0 | [Einstellungen §10](HANDBUCH_EINSTELLUNGEN.md#10-energieprofile--hintergrund) |
| Energieprofil | **Backward-Slot-Konvention** für alle Energie-Quellen (Industriestandard) | v3.20.0 | [Berechnungen §6b](BERECHNUNGEN.md#6b-energieprofil-berechnungen-tages-aggregation) |
| Energieprofil | Eigene **Energieprofil-Seite** unter Einstellungen → Daten mit Tages-Tabelle, Pro-Tag-Reaggregation, Vollbackfill, Datenverwaltung pro Anlage | v3.18.0 | [Einstellungen §1.6](HANDBUCH_EINSTELLUNGEN.md#16-energieprofil-seite) |
| Wärmepumpe | **Alternativ-Zusatzkosten** (Schornsteinfeger / Wartung / Gas-Grundpreis) und **Monats-Gaspreis** (`gaspreis_cent_kwh`) für realistische Ersparnis-Berechnung | v3.21.0 | [Berechnungen §3.5 / §4.4](BERECHNUNGEN.md#35-wärmepumpe-einsparung) |
| E-Auto | **Echte monatliche Benzinpreise** aus dem EU Weekly Oil Bulletin statt statischem Parameter | v3.17.0 | [Einstellungen §1.4](HANDBUCH_EINSTELLUNGEN.md#14-monatsdaten) |
| Wärmepumpe | Optionaler **Kompressor-Starts-Counter** als Stunden-/Tages-/Monats-KPI (Nibe & Co.) | v3.24.0 | [Sensor-Referenz §4 / §9](SENSOR-REFERENZ.md) |
| Daten-Checker | 5 → **8 Kategorien**: Energieprofil-Zähler-Abdeckung, MQTT-Topic-Abdeckung, Sensor-Mapping HA-Statistics neu | v3.19.0 → v3.24.1 | [Einstellungen §8](HANDBUCH_EINSTELLUNGEN.md#8-daten-checker) |
| Investitionen | Stilllegungsdatum als Endmarker; Stammdaten (Geräte/Ansprechpartner/Wartung) wandern in die Infothek | v3.14.0 / v3.16.2 | [Einstellungen §1.3](HANDBUCH_EINSTELLUNGEN.md#13-investitionen) |

---

## Hilfe & Support

Bei Fragen oder Problemen:

1. **Diese Hilfe-Seite** durchsuchen — die meisten Bedienfragen sind in [Teil II Bedienung](HANDBUCH_BEDIENUNG.md) beschrieben, die meisten Fehler in [Teil I §6 Fehlerbehebung](HANDBUCH_INSTALLATION.md#6-fehlerbehebung)
2. **Daten-Checker** (Einstellungen → System → Daten-Checker) — prüft die Datenqualität in 8 Kategorien und verlinkt direkt zur Behebung
3. **Protokolle** (Einstellungen → System → Protokolle) — Debug-Modus aktivieren, Logs kopieren, in GitHub-Issue einfügen
4. **GitHub Issues** — [github.com/supernova1963/eedc-homeassistant/issues](https://github.com/supernova1963/eedc-homeassistant/issues)

---

*Letzte Aktualisierung: April 2026 (v3.24.1)*
