
# EEDC Handbuch — Infothek

**Version 3.6** | Stand: März 2026

> Dieses Handbuch ist Teil der EEDC-Dokumentation.
> Siehe auch: [Teil I: Installation & Einrichtung](HANDBUCH_INSTALLATION.md) | [Teil II: Bedienung](HANDBUCH_BEDIENUNG.md) | [Teil III: Einstellungen](HANDBUCH_EINSTELLUNGEN.md) | [Glossar](GLOSSAR.md)

---

## Inhaltsverzeichnis

1. [Was ist die Infothek?](#1-was-ist-die-infothek)
2. [Navigation & Zugang](#2-navigation--zugang)
3. [Einträge erstellen und bearbeiten](#3-einträge-erstellen-und-bearbeiten)
4. [Kategorien und Vorlagen](#4-kategorien-und-vorlagen)
5. [Dateien: Fotos und PDFs](#5-dateien-fotos-und-pdfs)
6. [Verknüpfung mit Investitionen](#6-verknüpfung-mit-investitionen)
7. [Archivieren und Löschen](#7-archivieren-und-löschen)
8. [PDF-Export](#8-pdf-export)

---

## 1. Was ist die Infothek?

Die **Infothek** ist ein optionales Modul innerhalb von EEDC für die Verwaltung aller Verträge, Zähler, Kontakte und Dokumente rund um deine Energieversorgung.

PV-Anlagenbetreiber haben typischerweise viele Beteiligte:
- Stromanbieter und Netzbetreiber (oft unterschiedliche!)
- Einspeisevertrag mit EEG-Anlagennummer
- Gas- oder Fernwärme-Vertrag
- Wartungsvertrag für Wechselrichter oder Speicher
- Ansprechpartner beim Installateur
- Marktstammdatenregister-Eintrag

Diese Informationen sind verstreut — mal in Ordnern, mal in E-Mails, mal im Kopf. Die Infothek bringt alles an einen Ort, direkt neben deinen Energiedaten.

### Was die Infothek kann

- **14 Kategorien** mit passenden Vorlagen-Feldern (Strom, Gas, Wasser, Versicherung, ...)
- **Fotos und PDFs** pro Eintrag speichern (z.B. Zählerfotos, Vertragsscans)
- **Verknüpfung** mit EEDC-Investitionen (z.B. Wartungsvertrag → Wechselrichter)
- **PDF-Export** aller Infothek-Einträge für den Hefter
- **Archivierung** statt Löschung — alte Einträge bleiben auffindbar

### Was die Infothek nicht ist

Die Infothek ist kein Dokumentenmanagementsystem mit Volltextsuche oder Versionierung. Sie ist ein strukturierter Notizblock mit Vorlagen — pragmatisch und schnell.

---

## 2. Navigation & Zugang

### Menüpunkt

Der Menüpunkt **"Infothek"** erscheint in der Hauptnavigation, sobald du den ersten Eintrag angelegt hast. Vorher ist er ausgeblendet, um die Navigation nicht zu überfrachten.

Um die Infothek zum ersten Mal zu öffnen:
- **Einstellungen → Anlage** → Button "Infothek einrichten"
- Oder direkt über URL: `/infothek`

### Übersichtsseite

Die Infothek-Übersicht zeigt alle Einträge als Karten:

```
┌──────────────────────────────────────────────────┐
│ Infothek                         [+ Neuer Eintrag] │
│                                                    │
│ Kategorien: [Alle] [Strom] [Gas] [Wasser] [...]   │
├──────────────────────────────────────────────────┤
│ ⚡ Stadtwerke Strom (Netzbetreiber)       [✏️] [🗑️] │
│    Zähler: Inexogy #12345                          │
│    Anbieter: Octopus Energy                        │
│    → PV-Anlage Dach  |  📄 1 PDF  |  📷 2 Fotos   │
├──────────────────────────────────────────────────┤
│ 💧 Wasserzähler Keller                   [✏️] [🗑️] │
│    Digitaler Zähler, Eichdatum: 2025-12-15         │
│    📷 1 Foto                                       │
└──────────────────────────────────────────────────┘
```

### Kategorie-Filter

Oberhalb der Karten gibt es einen Filter-Bereich. Klicke auf eine Kategorie (z.B. "Strom"), um nur Einträge dieser Kategorie anzuzeigen. "Alle" zeigt wieder alle Einträge.

---

## 3. Einträge erstellen und bearbeiten

### Neuen Eintrag anlegen

Klicke auf **"+ Neuer Eintrag"** oben rechts. Ein Formular öffnet sich mit folgenden Bereichen:

#### Pflichtfelder

| Feld | Beschreibung |
|------|--------------|
| **Bezeichnung** | Freier Name des Eintrags, z.B. "Stadtwerke Strom (Netzbetreiber)" |
| **Kategorie** | Bestimmt die Vorlage mit passenden Zusatzfeldern |

#### Kategorie-spezifische Felder

Je nach gewählter Kategorie erscheinen passende Vorlagen-Felder (z.B. Zählernummer und Anbieter bei "Stromvertrag"). Diese Felder sind alle optional — fülle nur aus, was du hast.

#### Kontakt-Sektion (aufklappbar)

Für alle Kategorien verfügbar:
- Firma, Name, Telefon, E-Mail

#### Notizen

Großes Freitext-Feld für alles Weitere: Besonderheiten, Gesprächsnotizen, Links.

#### Dateien

Upload von bis zu 3 Fotos oder PDFs pro Eintrag. Siehe [§5 Dateien](#5-dateien-fotos-und-pdfs).

#### Verknüpfte Investition

Optionale Zuordnung zu einer EEDC-Investition. Siehe [§6 Verknüpfung](#6-verknüpfung-mit-investitionen).

### Bestehenden Eintrag bearbeiten

Klicke auf das **Stift-Icon** (✏️) auf der Karte. Das Formular öffnet sich mit den aktuellen Werten.

### Reihenfolge ändern

Die Karten können per **Drag & Drop** sortiert werden. Die Reihenfolge wird gespeichert.

---

## 4. Kategorien und Vorlagen

Jede Kategorie liefert passende Zusatzfelder. Alle Felder sind optional.

### Stromvertrag ⚡

| Feld | Beschreibung |
|------|--------------|
| Zählernummer | OBIS-konforme Zählpunktnummer (DE...) |
| Anbieter | Stromlieferant (z.B. "Octopus Energy") |
| Netzbetreiber | Netzbetreibergesellschaft (oft ein anderes Unternehmen!) |
| Tarif (ct/kWh) | Aktueller Arbeitspreis |
| Vertragsbeginn | Datum des Vertragsbeginns |
| Vertragslaufzeit | In Monaten |
| Kündigungsfrist | In Monaten |
| Kundennummer | Beim Stromanbieter |

> **Tipp**: Netzbetreiber und Stromanbieter sind in Deutschland häufig verschiedene Unternehmen. Lege für beide je einen eigenen Eintrag an.

### Einspeisevertrag ☀️

| Feld | Beschreibung |
|------|--------------|
| Zählernummer | Einspeisezähler-Nummer |
| Vergütung (ct/kWh) | Aktuell gültiger Einspeisetarif |
| EEG-Anlagennummer | Aus dem Marktstammdatenregister |
| Inbetriebnahmedatum | Datum der Anlageninbetriebnahme |
| Anbieter | Wer zahlt die Vergütung? |
| Kundennummer | |

### Gasvertrag 🔥

| Feld | Beschreibung |
|------|--------------|
| Zählernummer | Gaszähler-ID |
| Anbieter | Gaslieferant |
| Tarif (ct/kWh) | Arbeitspreis |
| Jahresverbrauch | In kWh (für Abschlagsberechnung) |
| Kundennummer | |
| Vertragsbeginn | |
| Kündigungsfrist | In Monaten |

### Wasservertrag 💧

| Feld | Beschreibung |
|------|--------------|
| Zählernummer | Wasserzähler-Nummer |
| Anbieter | Wasserversorger |
| Eichdatum | Letztes Eichdatum (Eichpflicht alle 6 Jahre) |
| Nächste Ablesung | Geplanter Ablesetermin |
| Kundennummer | |

### Fernwärme 🌡️

| Feld | Beschreibung |
|------|--------------|
| Zählernummer | Wärmezähler-ID |
| Anbieter | Fernwärmeversorger |
| Anschlussleistung | In kW |
| Tarif (ct/kWh) | Arbeitspreis |
| Kundennummer | |

### Brennstoff 🪵

Für Heizöl, Flüssiggas, Pellets, Holz:

| Feld | Beschreibung |
|------|--------------|
| Brennstoff-Art | Heizöl / Flüssiggas / Pellets / Holz |
| Lieferant | Name des Lieferanten |
| Tankgröße | Fassungsvermögen |
| Letzte Lieferung | Datum |
| Menge | Liter, kg oder Ster |
| Preis pro Einheit | Aktueller Preis |
| Einheit | Liter / kg / Ster |
| Kundennummer | |

### Versicherung 🛡️

| Feld | Beschreibung |
|------|--------------|
| Versicherungsnummer | Policennummer |
| Anbieter | Versicherungsgesellschaft |
| Deckungssumme | In Euro |
| Jahresbeitrag | In Euro |
| Vertragsbeginn | |
| Kündigungsfrist | In Monaten |

### Ansprechpartner 👤

| Feld | Beschreibung |
|------|--------------|
| Firma | Unternehmensname |
| Name | Ansprechpartner-Name |
| Telefon | Direkte Durchwahl |
| E-Mail | |
| Ticketsystem-URL | Support-Portal mit direktem Link |
| Kundennummer | |
| Position | Funktion (z.B. "Service-Techniker") |

### Wartungs-/Pflegevertrag 🔧

| Feld | Beschreibung |
|------|--------------|
| Anbieter | Wartungsunternehmen |
| Vertragsnummer | |
| Leistungsumfang | Was ist abgedeckt? |
| Gültig bis | Vertragsende |
| Kündigungsfrist | In Monaten |
| Jahreskosten | In Euro |

### Marktstammdatenregister 🏛️

| Feld | Beschreibung |
|------|--------------|
| MaStR-Nummer | Eindeutige MaStR-ID der Anlage |
| Anlage-Typ | PV / Speicher / WP / ... |
| Inbetriebnahmedatum | |
| Status | in Betrieb / abgemeldet / ... |
| Letzte Aktualisierung | Datum der letzten Meldung |

### Förderung 💰

| Feld | Beschreibung |
|------|--------------|
| Aktenzeichen | Behördliches Aktenzeichen |
| Förderprogramm | Name des Programms |
| Betrag | In Euro |
| Bewilligungsdatum | |
| Laufzeit | In Monaten |
| Auflagen | Freitext |

### Garantie ✅

| Feld | Beschreibung |
|------|--------------|
| Hersteller | |
| Produkt | Modellbezeichnung |
| Garantienummer | |
| Garantie bis | Ablaufdatum |
| Erweiterung | Ja / Nein (verlängerte Garantie) |
| Bedingungen | Freitext für Sonderkonditionen |

### Steuerdaten 📊

| Feld | Beschreibung |
|------|--------------|
| Finanzamt | Zuständiges Finanzamt |
| Steuernummer | |
| Abschreibungszeitraum | In Jahren |
| AfA-Typ | Linear / Degressiv |
| Restwert | In Euro |

### Sonstiges 📋

Nur Kernfelder (Bezeichnung, Notizen, Dateien). Für alles, was in keine andere Kategorie passt.

---

## 5. Dateien: Fotos und PDFs

Pro Eintrag können bis zu **3 Dateien** hochgeladen werden — Fotos und/oder PDFs.

### Unterstützte Formate

| Format | Hinweis |
|--------|---------|
| JPEG | Standard-Fotoformat |
| PNG | Screenshots, Scans |
| HEIC | iPhone-Fotos (werden automatisch zu JPEG konvertiert) |
| PDF | Vertragsscans, technische Datenblätter (max. 2 MB) |

### Upload

Im Formular findest du den Bereich **"Dateien (max. 3)"**:
1. Klicke auf "📎 Datei hochladen" oder ziehe Dateien per Drag & Drop in den Bereich
2. Bilder werden vom Server automatisch verkleinert (max. 500 KB, EXIF-Rotation wird berücksichtigt)
3. Für PDFs wird ein PDF-Icon als Platzhalter angezeigt
4. Klicke auf das Papierkorb-Icon (🗑️) an einem Vorschaubild, um eine Datei zu entfernen

### Vorschau und Lightbox

In der Karten-Übersicht werden Bild-Thumbnails direkt angezeigt. Klicke auf ein Thumbnail, um das Bild in der Lightbox (Vollbild) zu öffnen. Zwischen mehreren Bildern kann geblättert werden.

PDFs zeigen ein PDF-Icon — Klick öffnet die PDF in einem neuen Browser-Tab.

### Speicherung

Alle Dateien werden direkt in der EEDC-Datenbank gespeichert (BLOB). Das bedeutet:
- Kein separates Backup nötig — Dateien sind im normalen DB-Backup enthalten
- Bei Home Assistant: Dateien überleben Container-Neustarts
- Nachteil: Jede Datei vergrößert die Datenbank um ~500 KB (Bilder) bzw. bis zu 2 MB (PDFs)

---

## 6. Verknüpfung mit Investitionen

Ein Infothek-Eintrag kann optional mit einer EEDC-Investition verknüpft werden.

**Beispiele:**
- Wartungsvertrag → Wechselrichter
- Garantie → Speicher
- Ansprechpartner → PV-Module (Installateur)

### Verknüpfung setzen

Im Formular-Bereich **"Verknüpfte Investition"** wähle aus dem Dropdown die gewünschte Investition aus.

### Wo wird die Verknüpfung angezeigt?

- In der Infothek-Karte: Kleiner Badge "→ [Investitionsname]"
- Auf der Investitions-Seite: Sektion "Infothek-Einträge" listet alle verknüpften Einträge

### Bestehende Stammdaten migrieren

Wenn du EEDC bereits vor v3.5.0 genutzt hast und Stammdaten (Ansprechpartner, Wartungsvertrag) direkt in Investitionen eingetragen hattest: Diese Daten werden nicht automatisch migriert.

**Empfehlung:** Lege neue Infothek-Einträge an und trage die Informationen dort ein. Die alten Felder in den Investitions-Formularen kannst du danach leeren.

---

## 7. Archivieren und Löschen

### Archivieren (empfohlen)

Klicke auf das Papierkorb-Icon (🗑️) auf einer Karte und bestätige mit **"Archivieren"**. Der Eintrag verschwindet aus der normalen Ansicht, bleibt aber in der Datenbank.

Archivierte Einträge anzeigen: Aktiviere den Filter **"Archivierte anzeigen"** unterhalb der Kategorien.

**Wann archivieren?**
- Vertrag ist ausgelaufen, war aber relevant für die Geschichte der Anlage
- Zähler wurde ausgebaut, Daten aber noch interessant für Vergleiche

### Endgültig löschen

In der archivierten Ansicht erscheint zusätzlich ein **"Endgültig löschen"**-Button. Damit werden Eintrag und alle verknüpften Dateien unwiderruflich gelöscht.

---

## 8. PDF-Export

Alle Infothek-Einträge können als strukturiertes PDF exportiert werden — ideal für den klassischen Hefter oder als Backup.

### Export starten

**Pfad:** Infothek-Übersicht → Button "PDF exportieren" (oben rechts, neben "+ Neuer Eintrag")

### Inhalt des Exports

- Titelseite mit Anlagenname und Exportdatum
- Je ein Abschnitt pro Infothek-Eintrag:
  - Kategorie-Icon + Bezeichnung als Überschrift
  - Alle ausgefüllten Vorlagen-Felder als Tabelle
  - Kontakt-Daten (wenn vorhanden)
  - Notizen als Freitext
  - Dateien: Bilder als Miniaturansicht, PDFs als Verweis
- Verknüpfte Investition wird namentlich genannt

### Filter

Vor dem Export kannst du wählen:
- **Alle Einträge** (Standard)
- **Nur aktive** (archivierte ausgenommen)
- **Nach Kategorie filtern**

---

*Letzte Aktualisierung: März 2026*
