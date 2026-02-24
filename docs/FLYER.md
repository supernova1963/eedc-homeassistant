# EEDC – Promotional Texte

Drei Varianten für verschiedene Kanäle. Alle Texte auf Deutsch.

---

## Variante 1: Reddit (r/homeassistant, r/solar)
*Kurz, prägnant, englischer Stil – aber deutsch. Headline + Bullets + Links*

---

### 🌞 EEDC – Kostenlose PV-Analyse direkt in Home Assistant (v2.3.0)

Ich habe ein Home Assistant Add-on entwickelt, das eure PV-Anlage wirklich vollständig auswertet – komplett lokal, keine Cloud, keine Abo-Gebühren.

**Was kann es?**

- 📊 **Modernisiertes Cockpit** – Hero-KPIs mit Jahrestrend, Energie-Fluss-Diagramm, Ring-Gauges für Autarkie & Eigenverbrauch, Sparkline
- 📈 **6 Analyse-Tabs** – Energie, PV-Anlage, Komponenten, Finanzen, CO2, Investitionen
- 💰 **ROI-Berechnung** – Wann amortisiert sich die Anlage? Mit Fortschrittsbalken
- 🔋 **Multi-Komponenten** – PV, Speicher, E-Auto, Wärmepumpe, Wallbox, Balkonkraftwerk
- 🤝 **Community-Vergleich** – Anonymer Benchmark mit anderen PV-Anlagen (optional)
- 🇩🇪🇦🇹🇨🇭 **DACH-Support** – Deutschland, Österreich, Schweiz
- 📥 **HA-Statistik Import** – Historische Daten direkt aus der HA-Langzeitstatistik laden
- 🎯 **Standalone-fähig** – Läuft auch ohne Home Assistant (Docker)

**Installation:** Repository zu HA Add-ons hinzufügen:
```
https://github.com/supernova1963/eedc-homeassistant
```
Dann "EEDC" im Add-on Store suchen und installieren. Demo-Daten sind mit einem Klick geladen.

👉 [GitHub](https://github.com/supernova1963/eedc-homeassistant) | [Releases](https://github.com/supernova1963/eedc-homeassistant/releases) | [Community Server](https://energy.raunet.eu)

---

## Variante 2: Home Assistant Community Forum
*Ausführlicher, strukturiert, mit Abschnittstiteln. Typischer Forum-Post-Stil.*

---

### EEDC – Energie Effizienz Data Center | PV-Analyse Add-on für Home Assistant

Hallo zusammen,

ich möchte euch mein selbst entwickeltes Home Assistant Add-on vorstellen: **EEDC** (Energie Effizienz Data Center) – eine vollständige Auswertungs- und Wirtschaftlichkeitsplattform für Photovoltaik-Anlagen.

**Kernprinzipien:**
- 🔒 **Alles lokal** – Keine Cloud, keine Registrierung, alle Daten bleiben bei euch
- 🏠 **Standalone-fähig** – Funktioniert mit oder ohne Home Assistant
- 📅 **Monatliche Granularität** – Ideal für Jahresauswertungen und ROI-Tracking

---

#### 🎛️ Das Cockpit (v2.3.0 – frisch überarbeitet)

Das Dashboard zeigt jetzt auf einen Blick:
- **Hero-Leiste** mit den 3 wichtigsten KPIs und Trend-Vergleich zum Vorjahr (▲/▼)
- **Energie-Fluss-Diagramm**: Wohin fließt euer PV-Strom? Woher kommt euer Hausverbrauch?
- **Ring-Gauges** für Autarkie und Eigenverbrauchsquote
- **Sparkline** mit monatlichen PV-Erträgen über den gesamten Zeitraum
- **Amortisations-Fortschrittsbalken** mit geschätztem Amortisationsjahr

---

#### 📊 Auswertungen (6 Tabs)

| Tab | Inhalt |
|-----|--------|
| **Energie** | Monats-Charts, Jahresvergleich, Delta-Indikatoren |
| **PV-Anlage** | String-Performance, SOLL-IST vs. PVGIS, Degradation |
| **Komponenten** | Speicher-Effizienz, WP-JAZ, E-Auto-Quellen, Wallbox, BKW |
| **Finanzen** | Einspeisung, Einsparungen, Netto-Ertrag, Amortisation |
| **CO2** | Vermiedene Emissionen, Vergleich zu Netzbezug |
| **Investitionen** | ROI pro Komponente, Jahres-Rendite p.a. |

---

#### 🤝 Community-Vergleich (optional)

Wer möchte, kann seine anonymisierten Daten mit der Community teilen:
- Nur Bundesland/Land wird übertragen – keine Adresse, keine PLZ
- **6 Analyse-Tabs**: Übersicht, PV-Ertrag, Komponenten, Regional, Trends, Statistiken
- **Achievements** (z.B. Autarkiemeister, Solarprofi) und Rang-Badges (Top 10%)
- **Choropleth-Karte** mit Bundesland-Vergleich
- Jederzeit löschbar

Community-Server: [energy.raunet.eu](https://energy.raunet.eu)

---

#### ⚡ Unterstützte Komponenten

PV-Anlage (inkl. String-Vergleich) • Batteriespeicher (AC & DC) • E-Auto (V2H-fähig) • Wärmepumpe (JAZ/SCOP/COP) • Wallbox • Balkonkraftwerk • Sonstiges

---

#### 🚀 Installation

1. HA → Einstellungen → Add-ons → Add-on Store → ⋮ → Repositories
2. URL hinzufügen: `https://github.com/supernova1963/eedc-homeassistant`
3. "EEDC" installieren, starten, in Sidebar anzeigen aktivieren
4. Demo-Daten laden (ein Klick) – sofort alle Features ausprobieren

Alternativ als **Docker-Container** ohne HA:
```bash
docker run -p 8099:8099 -v $(pwd)/data:/data supernova1963/eedc:latest
```

---

#### 📦 Tech Stack

Backend: FastAPI + SQLAlchemy + SQLite | Frontend: React + TypeScript + Tailwind + Recharts

---

Feedback, Feature-Wünsche und Fehlerberichte gerne als [GitHub Issue](https://github.com/supernova1963/eedc-homeassistant/issues) oder direkt hier im Thread.

**Links:**
- 🐙 GitHub: https://github.com/supernova1963/eedc-homeassistant
- 📋 Changelog: https://github.com/supernova1963/eedc-homeassistant/blob/main/CHANGELOG.md
- 🌍 Community: https://energy.raunet.eu

---

## Variante 3: Deutsche PV-Foren & Facebook-Gruppen
*Freundlicher, persönlicher Ton, weniger technisch, mehr Nutzen im Vordergrund*

---

### 🌞 Kostenlose PV-Auswertungs-Software – auch für Home Assistant

Hallo in die Runde!

Ich habe ein Tool entwickelt, das mich selbst bei meiner eigenen PV-Anlage begeistert – und vielleicht hilft es auch euch weiter.

**EEDC** wertet eure Photovoltaik-Anlage komplett aus: Energiebilanz, Wirtschaftlichkeit, Amortisation, CO2 – alles auf einen Blick, und das komplett kostenlos und ohne Cloud.

---

**Was bringt EEDC konkret?**

✅ **Wann ist meine Anlage abbezahlt?** – Ein Fortschrittsbalken zeigt, wie viel Prozent der Investition bereits zurückgeflossen sind, und schätzt das Amortisationsjahr

✅ **Wie autark bin ich wirklich?** – Autarkie und Eigenverbrauchsquote als anschauliche Ringdiagramme, nicht nur als Zahl

✅ **Wohin fließt mein PV-Strom?** – Ein Energie-Fluss-Diagramm zeigt Direktverbrauch, Speichernutzung und Einspeisung auf einen Blick

✅ **Lohnt sich der Speicher?** – Effizienz, Vollzyklen, PV-Anteil und mehr

✅ **Wie gut ist meine Wärmepumpe?** – JAZ-Berechnung und Vergleich mit der Community

✅ **Wie fährt mein E-Auto?** – PV-Anteil der Ladungen, Kostenersparnis, V2H-Auswertung

✅ **Bin ich gut im Vergleich?** – Optionaler anonymer Community-Vergleich mit anderen Anlagen in Deutschland, Österreich und der Schweiz

---

**Für wen ist das?**

- Home Assistant Nutzer → als Add-on mit einem Klick installierbar
- Alle anderen → läuft auch standalone als Docker-Container oder lokal
- Neu: 🇦🇹🇨🇭 **Auch für Österreich und die Schweiz!**

---

**Daten eingeben geht ganz einfach:**
- Manuell über ein geführtes Formular (Monatsabschluss-Wizard)
- Per CSV-Import (auch mit eigenen Spaltenbezeichnungen)
- Automatisch aus der Home Assistant Langzeitstatistik (Bulk-Import)
- Demo-Daten zum Ausprobieren – ein Klick, und alles ist befüllt

---

**Kostet nichts, läuft lokal, keine Registrierung.**

👉 Zum Projekt: https://github.com/supernova1963/eedc-homeassistant

Fragen und Feedback sind herzlich willkommen! 😊

---

## Kurz-Version (für Kommentare / Kurzbeschreibungen)

> **EEDC** ist ein kostenloses, lokal laufendes PV-Analyse-Tool für Home Assistant (auch standalone). Modernisiertes Cockpit mit Energie-Fluss, ROI-Tracking, Speicher/WP/E-Auto-Auswertung, optionalem Community-Vergleich und HA-Statistik-Import. DACH-Support (DE/AT/CH). Demo-Daten inklusive.
> 👉 https://github.com/supernova1963/eedc-homeassistant
