
# eedc Benutzerhandbuch

**Version 4.0** | Stand: 2026-07-25

---

## Über diese Hilfe

Du liest gerade das **eedc-Benutzerhandbuch** — die Übersicht über die ganze Dokumentation. Wenn du die Seite über den Menüpunkt **Hilfe** geöffnet hast, läuft sie als **In-App-Hilfe** direkt in eedc: alle Inhalte werden lokal gerendert, ohne externen Browser-Tab und ohne Login-Stolpersteine in der HA-Companion-App.

**Bedienung der Hilfe-Seite:**
- **Sidebar (Desktop) / Dropdown (Mobile)** links: Auswahl des Dokuments aus drei Kategorien — *Einstieg*, *Handbuch*, *Referenz*.
- **URL-Parameter `?doc=<slug>`**: Direktlinks sind teilbar. Beispiel `?doc=bedienung#25-aussicht` öffnet das Bedienungs-Handbuch und scrollt direkt zur Aussicht.
- **Markdown-Links** zwischen den Hilfe-Dokumenten werden intern aufgelöst; externe `.md`-Verweise (z. B. auf Konzept-Dokumente) leiten zur GitHub-Quelle weiter.

**Synchronisation:** Single Source of Truth ist `docs/` im Projekt-Repo. Beim Release-Build kopiert `scripts/sync-help.sh` die kuratierten Dokumente nach `eedc/frontend/public/help/`. Damit ist die In-App-Hilfe immer auf dem Stand der laufenden Version. Die Web-Version unter [supernova1963.github.io/eedc-homeassistant](https://supernova1963.github.io/eedc-homeassistant/) (Astro Starlight) wird parallel aus denselben Quellen erzeugt.

---

## Empfohlene Nutzung

eedc ist eine **datendichte Analyse-App** — viele Kennzahlen nebeneinander, feinachsige Diagramme, Tabellen mit vielen Spalten. Optimal nutzbar auf **Desktop**. Am Smartphone funktionieren Live, Cockpit-Monat und die Komponenten-Sichten gut; für die datendichten Bereiche (Auswertungen → Tabelle, Cockpit → Aussicht) ist ein größerer Bildschirm oder Querformat sinnvoll.

Bei stark erhöhtem Anzeigezoom (iOS „Größerer Text", HA-Companion-Seitenzoom über Standard) können einzelne Layouts eng werden — eine bewusste Designentscheidung statt Layout-Patches, die den datendichten Charakter aufweichen würden.

---

## Die Oberfläche auf einen Blick

eedc ist um **drei Analyse-Achsen** und den **Community-Bereich** herum aufgebaut; alles Einrichten und Datenpflegen liegt gebündelt in den **Einstellungen**. Statt vieler nebeneinander stehender Tabs beantwortet jede Achse eine andere Frage über dieselbe Anlage:

| Bereich | Frage | Was du dort findest |
|---|---|---|
| **Cockpit** | **Wann?** | Dieselben Kennzahlen auf fünf Zeit-Ebenen: Live, Tag, Monat, Jahr/Gesamt, Aussicht |
| **Komponenten** | **Was?** | Detailsicht je Gerätetyp: PV-Anlage, Speicher, Wärmepumpe, Wallbox, E-Auto, Balkonkraftwerk, Sonstiges |
| **Auswertungen** | **Wie?** | Auswertende Sichten quer über die Zeit: Finanzen, ROI, Prognose-Genauigkeit, CO₂, Tabelle |
| **Community** | **Im Vergleich?** | Anonymer Benchmark mit anderen Anlagen |

Daneben stehen die Meta-Einträge **Hilfe** (diese Seite) und **Einstellungen** (Kachel-Raster mit allen Konfigurations-Bereichen). Der vollständige Bedienungs-Leitfaden inklusive Block-Modell (klappen, fokussieren, umsortieren, parken) und Status-Fußzeile steht in [Teil II: Bedienung](HANDBUCH_BEDIENUNG.md).

> **Von einer älteren Version umgestiegen?** Die Tabelle **[„Wo ist X hin?"](HANDBUCH_BEDIENUNG.md#8-anhang-wo-ist-x-hin)** zeigt für jeden vertrauten Bereich seine neue Heimat.

---

## Inhalt

Die Doku ist in vier Teile, zwei Referenzen und ein Glossar gegliedert:

### Einstieg

- **Diese Übersicht** — was wo zu finden ist.
- **[Was ist neu](WAS-IST-NEU.md)** — pro Version, was sich für Anwender geändert hat (inkl. der neuen Oberfläche v4.0 und der „Wo ist X hin?"-Tabelle).

### Handbuch (Teile I–IV)

| Teil | Inhalt | Link |
|---|---|---|
| **Teil I: Installation & Einrichtung** | Installations-Optionen (HA Add-on / Docker / Dev), der **Setup-Wizard** (Erst-Einrichtung inkl. Anlage, Komponenten, Integration und Datenquellen), Fehlerbehebung. | [HANDBUCH_INSTALLATION.md](HANDBUCH_INSTALLATION.md) |
| **Teil II: Bedienung** | Navigation & Block-Modell, die drei Analyse-Achsen — **Cockpit** (Live/Tag/Monat/Jahr/Aussicht), **Komponenten** (ein Reiter je Gerätetyp), **Auswertungen** (Finanzen/ROI/Prognose/CO₂/Tabelle) —, **Community**, Hilfe und die Status-Fußzeile. | [HANDBUCH_BEDIENUNG.md](HANDBUCH_BEDIENUNG.md) |
| **Teil III: Einstellungen** | Das Kachel-Raster mit sieben Kategorien: Stammdaten, Komponenten, Infothek, **Daten** (Monatsdaten/Monatsabschluss, Energieprofil-Pflege, Daten-Checker), **Integration** (MQTT-Broker, HA-Verbindung, Export, Statistik-Import), **Datenquellen** (feld-zentrische Zuordnung) und System. Enthält das Hintergrund-Kapitel zur Energieprofil- & Snapshot-Architektur. | [HANDBUCH_EINSTELLUNGEN.md](HANDBUCH_EINSTELLUNGEN.md) |
| **Teil IV: Infothek** | Verträge, Zähler, Kontakte und Dokumente rund um die Energieversorgung verwalten. Kategorien mit Vorlagen, Datei-Upload (Fotos & PDFs), N:M-Verknüpfung mit Komponenten, PDF-Export. | [HANDBUCH_INFOTHEK.md](HANDBUCH_INFOTHEK.md) |

**Themen-Handbücher** (vertiefen einzelne Bereiche):

| Dokument | Inhalt | Link |
|---|---|---|
| **Daten-Checker** | Datenqualität prüfen: Kategorien, Befund-Tabellen, Reparatur-Werkbank und Behebungs-Workflows. | [HANDBUCH_DATEN_CHECKER.md](HANDBUCH_DATEN_CHECKER.md) |
| **Energieprofil** | Was das Energieprofil (Stunden-/Tageswerte) ist und **wo es in v4 zu finden ist** — Anzeige über die Cockpit-Achsen, Pflege in den Einstellungen. | [HANDBUCH_ENERGIEPROFIL.md](HANDBUCH_ENERGIEPROFIL.md) |
| **Prognosen** | Wetter- und Ertragsprognosen, Genauigkeits-Tracking (OpenMeteo / eedc kalibriert / Solcast / IST), Lernfaktor. | [HANDBUCH_PROGNOSEN.md](HANDBUCH_PROGNOSEN.md) |

### Referenz

| Dokument | Inhalt | Link |
|---|---|---|
| **Berechnungen & Kennzahlen** | Datenmodell und Berechnungs-Formeln pro Thema (Energie-Bilanz, Finanzen, Speicher, E-Auto, Wärmepumpe, ROI, USt, CO₂, PV-SOLL-IST, Sonstige Positionen), Prognosen inkl. Lernfaktor / MOS-Kaskade / MAE/MBE, Tarif-System, Energieprofil-Berechnungen mit Snapshot-Architektur und Backward-Slot. | [BERECHNUNGEN.md](BERECHNUNGEN.md) |
| **Sensor-Referenz** | Feldnamen, Einheiten und Anforderungen pro Komponente. Counter- vs. kWh-Trennung, LTS-Verfügbarkeit, Solcast-Anbindung, Vorzeichen-Konvention. | [SENSOR-REFERENZ.md](SENSOR-REFERENZ.md) |

### Glossar

| Dokument | Inhalt | Link |
|---|---|---|
| **Glossar & Support** | Begriffserklärungen in thematischen Gruppen (Energie & Bilanzen, Strahlung & Wetter, Prognosen, Komponenten, Strompreise, Snapshots, Integration, Sonstiges) und Support-Anlaufstellen. | [GLOSSAR.md](GLOSSAR.md) |

---

## Was ist neu seit v3.16?

Wer mit einer älteren eedc-Version vertraut ist und einen schnellen Überblick sucht: Die wichtigste Neuerung ist die **grundlegend überarbeitete Oberfläche (v4.0)** — die frühere Tab-Landschaft ist zu drei Analyse-Achsen (Cockpit, Komponenten, Auswertungen) plus Community verdichtet. Wo ein vertrauter Bereich jetzt liegt, zeigt die Tabelle **[„Wo ist X hin?"](HANDBUCH_BEDIENUNG.md#8-anhang-wo-ist-x-hin)**.

Eine **detaillierte, pro Version gegliederte Beschreibung** aller Änderungen — auch die zwischen v3.16 und v4.0 — findest du auf der eigenen Seite **[Was ist neu](WAS-IST-NEU.md)**. Die folgende Schnellübersicht nennt nur die für Anwender sichtbaren Eckpunkte:

| Bereich | Änderung | Ab Version |
|---|---|---|
| **Oberfläche** | Neue Informationsarchitektur: drei Analyse-Achsen + Community statt vieler Einzel-Tabs; Blöcke klapp-/fokussier-/parkbar | v4.0 |
| **Cockpit → Monat** | Monats-Analysen des alten Energieprofils gehoben: Performance Ratio (Ø Monat), Kategorien-Anteile, typisches Tagesprofil, Top-Stunden, §51-Negativpreis | v4.0 |
| **Datenquellen** | Feld-zentrische Zuordnung (eine Quelle je Feld) löst die alten Sensor-Mapping-/MQTT-Assistenten ab | v4.0 |
| **Monatsabschluss** | Ein Formular unter Einstellungen → Daten → Monatsdaten statt eigenem Assistenten | v4.0 |
| **Prognosen** | Genauigkeits-Vergleich mehrerer Quellen (OpenMeteo / eedc kalibriert / Solcast / IST), MAE + Bias getrennt | v3.16.4 → v3.23.3 |
| **Energieprofil** | Stunden-kWh aus kumulativen Zähler-Snapshots statt Leistungs-Integration; Backward-Slot-Konvention | v3.19.0 → v3.20.0 |
| **Wärmepumpe** | Alternativ-Zusatzkosten und Monats-Gaspreis für realistische Ersparnis; optionaler Kompressor-Starts-Counter | v3.21.0 / v3.24.0 |
| **E-Auto** | Echte monatliche Kraftstoffpreise aus dem EU Weekly Oil Bulletin statt statischem Parameter | v3.17.0 |

---

## Hilfe & Support

Bei Fragen oder Problemen:

1. **Diese Hilfe-Seite** durchsuchen — die meisten Bedienfragen sind in [Teil II: Bedienung](HANDBUCH_BEDIENUNG.md) beschrieben, die meisten Fehler in [Teil I: Fehlerbehebung](HANDBUCH_INSTALLATION.md).
2. **Daten-Checker** (Einstellungen → Daten → Daten-Checker) — prüft die Datenqualität und verlinkt direkt zur Behebung.
3. **Protokolle** (Einstellungen → System → Protokolle) — Debug-Modus aktivieren, Logs kopieren, in ein GitHub-Issue einfügen.
4. **GitHub Issues** — [github.com/supernova1963/eedc-homeassistant/issues](https://github.com/supernova1963/eedc-homeassistant/issues)

---

*Letzte Aktualisierung: 2026-07-25 (v4.0)*
