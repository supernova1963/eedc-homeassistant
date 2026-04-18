
# EEDC Handbuch — Infothek

**Version 3.16.1** | Stand: April 2026

> Dieses Handbuch ist Teil der EEDC-Dokumentation.
> Siehe auch: [Teil I: Installation & Einrichtung](HANDBUCH_INSTALLATION.md) | [Teil II: Bedienung](HANDBUCH_BEDIENUNG.md) | [Teil III: Einstellungen](HANDBUCH_EINSTELLUNGEN.md) | [Glossar](GLOSSAR.md)

---

## Inhaltsverzeichnis

1. [Was ist die Infothek?](#1-was-ist-die-infothek)
2. [Navigation & Zugang](#2-navigation--zugang)
3. [Einträge erstellen und bearbeiten](#3-einträge-erstellen-und-bearbeiten)
4. [Kategorien und Vorlagen](#4-kategorien-und-vorlagen)
5. [Komponenten-Akte / Datenblatt](#5-komponenten-akte--datenblatt)
6. [Dateien: Fotos und PDFs](#6-dateien-fotos-und-pdfs)
7. [Verknüpfung mit Investitionen (N:M)](#7-verknüpfung-mit-investitionen-nm)
8. [Archivieren und Löschen](#8-archivieren-und-löschen)
9. [PDF-Dokumente](#9-pdf-dokumente)
10. [Best Practices](#10-best-practices)

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

- **15 Kategorien** mit passenden Vorlagen-Feldern (Strom, Gas, Wasser, Versicherung, ...)
- **Komponenten-Akte** mit technischen Daten, Seriennummern, Prüfterminen
- **Bis zu 15 Fotos und PDFs** pro Eintrag speichern (z.B. Datenblätter, Zählerfotos, Vertragsscans)
- **Mehrfach-Verknüpfung (N:M)** mit EEDC-Investitionen (z.B. ein Datenblatt für alle 6 PV-Strings)
- **Anlagendokumentation + Finanzbericht** als PDF — ziehen automatisch Infothek-Daten
- **Infothek-Dossier** als PDF-Export aller Einträge
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

Upload von bis zu 15 Fotos oder PDFs pro Eintrag (je bis zu 10 MB). Siehe [§6 Dateien](#6-dateien-fotos-und-pdfs).

#### Verknüpfte Investitionen

Mehrfach-Verknüpfung mit EEDC-Investitionen per Checkbox-Liste. Siehe [§7 Verknüpfung](#7-verknüpfung-mit-investitionen-nm).

#### In Anlagendokumentation anzeigen

Häkchen (Standard: an), das steuert ob dieser Eintrag in der Anlagendokumentation (PDF) erscheint. Das Infothek-Dossier zeigt immer alle Einträge.

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

### Komponente / Datenblatt ✅

Ehemals "Garantie" — seit v3.14.0 zum vollwertigen Datenblatt ausgebaut. Details und Best Practices: siehe [§5 Komponenten-Akte](#5-komponenten-akte--datenblatt).

| Feld | Beschreibung |
|------|--------------|
| Hersteller | |
| Produkt / Modell | Modellbezeichnung |
| Seriennummer | Geräte-Seriennummer |
| Einbau-Datum | Installationsdatum |
| Installiert von (Firma) | Installations-Unternehmen |
| Garantie-Nummer | |
| Garantie gültig bis | Ablaufdatum |
| Garantie-Erweiterung | Ja / Nein |
| Garantie-Bedingungen | Mehrzeiliger Freitext |
| Technische Daten | Mehrzeiliger Freitext (z.B. Wp, Kabelquerschnitt, COP) |
| Letzte Prüfung / Wartung | Datum |
| Nächste Prüfung / Wartung | Datum |
| Link zum Hersteller-Datenblatt | URL |
| Sonstige zugehörige Verträge / Dokumente | Mehrzeiliger Freitext |

### Steuerdaten 📊

| Feld | Beschreibung |
|------|--------------|
| Finanzamt | Zuständiges Finanzamt |
| Steuernummer | |
| Abschreibungszeitraum | In Jahren |
| AfA-Typ | Linear / Degressiv |
| Restwert | In Euro |

### Messstellenbetreiber ⚙️

| Feld | Beschreibung |
|------|--------------|
| Messstellenbetreiber | Name des MSB |
| Zählernummer | Zählpunktnummer |
| Zählertyp | Moderner/Intelligenter Messsystem |
| Kundennummer | |

### Sonstiges 📋

Nur Kernfelder (Bezeichnung, Notizen, Dateien). Für alles, was in keine andere Kategorie passt.

---

## 5. Komponenten-Akte / Datenblatt

Die Kategorie **"Komponente / Datenblatt"** ist das Herzstück der technischen Dokumentation. Hier werden Datenblätter, Seriennummern, Garantien und Prüftermine für jede Komponente deiner Anlage erfasst.

### Wozu?

- **Versicherungsfall**: Seriennummern und Garantie-Daten griffbereit
- **Wartung**: Prüftermine und Installations-Firma auf einen Blick
- **Anlagendokumentation**: Daten fließen automatisch in das PDF (siehe [§9 PDF-Dokumente](#9-pdf-dokumente))
- **Gerätewechsel**: Alte Komponente stillgelegt, neue angelegt — Dokumentation bleibt lückenlos

### Eintrag anlegen

1. Infothek → **"+ Neuer Eintrag"**
2. Kategorie: **"Komponente / Datenblatt"**
3. Bezeichnung: z.B. "Trina Vertex S 430Wp" oder "Fronius Symo GEN24 10.0"
4. Felder ausfüllen (alle optional, aber: je mehr, desto besser das PDF)
5. **Verknüpfung setzen**: Haken bei allen Investitionen, für die dieses Datenblatt gilt

### Mehrfach-Verknüpfung (N:M)

Ein Datenblatt kann **gleichzeitig mit mehreren Investitionen** verknüpft werden. Das vermeidet Duplikate:

- Ein "Trina Vertex S 430Wp"-Datenblatt gilt für Süddach, Ostdach und Garage → ein Eintrag, drei Haken
- Ein "SMA Sunny Tripower"-Datenblatt gilt nur für den einen Wechselrichter → ein Eintrag, ein Haken

### Schnellzugang über Investitions-Übersicht

In der **Investitions-Übersicht** (Cockpit → Investitionen) gibt es pro Investition einen kontextabhängigen Button:

| Situation | Button |
|-----------|--------|
| Keine Akte verknüpft | **"Komponenten-Akte anlegen"** → öffnet Quick-Create Modal |
| Genau 1 Akte verknüpft | **"Komponenten-Akte öffnen"** → öffnet direkt den Eintrag |
| Mehrere Akten verknüpft | **Dropdown** mit Direktlinks + "Weitere verknüpfen" |

---

## 6. Dateien: Fotos und PDFs

Pro Eintrag können bis zu **15 Dateien** hochgeladen werden — Fotos und/oder PDFs (je bis zu 10 MB).

### Unterstützte Formate

| Format | Hinweis |
|--------|---------|
| JPEG | Standard-Fotoformat |
| PNG | Screenshots, Scans |
| HEIC | iPhone-Fotos (werden automatisch zu JPEG konvertiert) |
| PDF | Vertragsscans, technische Datenblätter (max. 10 MB) |

### Upload

Im Formular findest du den Bereich **"Dateien (max. 15)"**:
1. Klicke auf "📎 Datei hochladen" oder ziehe Dateien per Drag & Drop in den Bereich
2. Bilder werden vom Server automatisch verkleinert (max. 500 KB, EXIF-Rotation wird berücksichtigt)
3. Pro Datei kann eine optionale **Beschreibung** eingegeben werden (z.B. "Zähler Keller links")
4. Für PDFs wird ein PDF-Icon als Platzhalter angezeigt
5. Klicke auf das Papierkorb-Icon (🗑️) an einem Vorschaubild, um eine Datei zu entfernen

### Vorschau und Lightbox

In der Karten-Übersicht werden Bild-Thumbnails direkt angezeigt. Klicke auf ein Thumbnail, um das Bild in der Lightbox (Vollbild) zu öffnen. Zwischen mehreren Bildern kann geblättert werden.

PDFs zeigen ein PDF-Icon — Klick öffnet die PDF in einem neuen Browser-Tab.

### Speicherung

Alle Dateien werden direkt in der EEDC-Datenbank gespeichert (BLOB). Das bedeutet:
- Kein separates Backup nötig — Dateien sind im normalen DB-Backup enthalten
- Bei Home Assistant: Dateien überleben Container-Neustarts
- Nachteil: Jede Datei vergrößert die Datenbank um ~500 KB (Bilder) bzw. bis zu 10 MB (PDFs)

---

## 7. Verknüpfung mit Investitionen (N:M)

Seit v3.15.2 unterstützt die Infothek **Mehrfach-Verknüpfungen**: Ein Eintrag kann mit beliebig vielen Investitionen verknüpft werden und umgekehrt.

**Beispiele:**
- Ein Datenblatt "Trina Vertex S 430Wp" → gilt für 6 PV-Strings gleichzeitig
- Ein Wartungsvertrag → verknüpft mit Wechselrichter + Speicher
- Ein Ansprechpartner (Installateur) → verknüpft mit allen PV-Modulen

### Verknüpfung setzen

Im Formular-Bereich **"Verknüpfte Investitionen"** erscheint eine **Checkbox-Liste** mit allen Investitionen der Anlage. Setze Haken bei allen zutreffenden. "Alle abwählen" entfernt alle Verknüpfungen.

### Wo wird die Verknüpfung angezeigt?

- **Infothek-Karte**: Badge(s) "→ [Investitionsname]" für jede Verknüpfung
- **Investitions-Übersicht**: Kontextabhängiger Button (siehe [§5 Komponenten-Akte](#5-komponenten-akte--datenblatt))
- **Anlagendokumentation (PDF)**: Verknüpfte Komponenten-Akten werden unter der jeweiligen Investition gerendert

### Migration von Altdaten

Bestehende 1:1-Verknüpfungen (vor v3.15.2) wurden automatisch in die neue N:M-Struktur migriert. Es ist keine manuelle Nacharbeit nötig.

---

## 8. Archivieren und Löschen

### Archivieren (empfohlen)

Klicke auf das Papierkorb-Icon (🗑️) auf einer Karte und bestätige mit **"Archivieren"**. Der Eintrag verschwindet aus der normalen Ansicht, bleibt aber in der Datenbank.

Archivierte Einträge anzeigen: Aktiviere den Filter **"Archivierte anzeigen"** unterhalb der Kategorien.

**Wann archivieren?**
- Vertrag ist ausgelaufen, war aber relevant für die Geschichte der Anlage
- Zähler wurde ausgebaut, Daten aber noch interessant für Vergleiche

### Endgültig löschen

In der archivierten Ansicht erscheint zusätzlich ein **"Endgültig löschen"**-Button. Damit werden Eintrag und alle verknüpften Dateien unwiderruflich gelöscht.

---

## 9. PDF-Dokumente

Die Infothek liefert Daten für drei verschiedene PDF-Dokumente. Alle sind über den **Dokumente-Dialog** erreichbar (Anlagen-Seite → orangefarbenes Ordner-Icon).

### Infothek-Dossier

Exportiert **alle** Infothek-Einträge als strukturiertes PDF — ideal für den klassischen Hefter oder als Backup.

**Pfad:** Dokumente-Dialog → "Infothek-Dossier"

**Inhalt:**
- Titelseite mit Anlagenname und Exportdatum
- Je ein Abschnitt pro Infothek-Eintrag:
  - Kategorie-Icon + Bezeichnung als Überschrift
  - Alle ausgefüllten Vorlagen-Felder als Tabelle
  - Kontakt-Daten (wenn vorhanden)
  - Notizen als Freitext
  - Dateien: Bilder als Miniaturansicht, PDFs als Verweis
- Verknüpfte Investitionen werden namentlich genannt

### Anlagendokumentation (Beta)

Technische Dokumentation der Anlage — für Versicherung, Nachlass, Archiv. **Enthält keine Geldbeträge.**

**Pfad:** Dokumente-Dialog → "Anlagendokumentation"

**Inhalt:**
- Titelseite mit Anlagenfoto (falls hochgeladen), Leistung, Inbetriebnahme, MaStR-Nummer
- Je eine Folgeseite pro Investitionstyp (PV-Module gruppiert, dann WR, Speicher, WP, etc.)
- Unter jeder Investition: Daten aus verknüpften **Komponenten-Akten** (Hersteller, Seriennummer, Garantie, Prüftermine, technische Daten)
- Infrastruktur-Sektion: Komponenten-Akten ohne Investment-Verknüpfung (z.B. Zähler, Verkabelung)

**Voraussetzung:** PDF-Engine muss auf **WeasyPrint** stehen (HA: Add-on-Konfiguration, Docker: Umgebungsvariable `PDF_ENGINE=weasyprint`).

**Steuerung:** Das Häkchen **"In Anlagendokumentation anzeigen"** am Infothek-Eintrag steuert, ob er ins PDF kommt (Standard: an).

### Finanzbericht (Beta)

Alle monetären Kennzahlen — Investitionskosten, Förderungen, Versicherung, Steuerdaten.

**Pfad:** Dokumente-Dialog → "Finanzbericht"

**Inhalt:**
- Investitions-Tabelle mit Kosten, Alternativkosten, Jahres-Ersparnis
- KPIs: Amortisations-Prognose, Netto-Kosten nach Förderung
- Sektionen aus Infothek-Kategorien: Förderungen, Versicherung, Steuerdaten

---

## 10. Best Practices

### Komponenten-Akte optimal pflegen

1. **Pro Komponententyp ein Datenblatt**: "Trina Vertex S 430Wp" statt "PV-Module allgemein"
2. **Mehrfach verknüpfen statt duplizieren**: Ein Datenblatt, N Haken — nicht 6 identische Einträge
3. **Seriennummer immer eintragen**: Unverzichtbar im Versicherungsfall
4. **Hersteller-Datenblatt-URL**: Direktlink zum PDF beim Hersteller — bleibt auch nach Jahren erreichbar
5. **Technische Daten**: Freiform, aber typisch: Leistung (Wp), Wirkungsgrad (%), Kabelquerschnitt, COP, Kapazität (kWh)
6. **Prüftermine pflegen**: Letzte/Nächste Prüfung hilft bei Wartungsplanung

### Optimale Anlagendokumentation

Damit die **Anlagendokumentation (PDF)** aussagekräftig wird:

1. **Anlagenfoto hochladen**: Anlagen-Stammdaten → Foto-Upload (erscheint auf der Titelseite)
2. **Jede Investition braucht eine Komponenten-Akte**: Klicke auf "Komponenten-Akte anlegen" in der Investitions-Übersicht
3. **Felder ausfüllen**: Hersteller + Produkt + Seriennummer sind das Minimum, Garantie + Prüftermine der Bonus
4. **Datenblatt-PDF anhängen**: Als Datei an die Komponenten-Akte → erscheint als Verweis im PDF
5. **Infrastruktur-Einträge**: Für Zähler, Zählerschränke oder Verkabelung: Komponenten-Akte ohne Investment-Verknüpfung anlegen → eigene Seite im PDF

### Empfohlene Reihenfolge beim Einrichten

1. Anlage mit Stammdaten und Anlagenfoto anlegen
2. Investitionen anlegen (PV-Module, Wechselrichter, Speicher, ...)
3. Pro Investition eine **Komponenten-Akte** anlegen (Quick-Create über Investitions-Übersicht)
4. Verträge (Strom, Einspeisung, Versicherung, Förderung) als eigene Infothek-Einträge
5. **Anlagendokumentation als PDF testen** → zeigt, wo noch Daten fehlen
6. **Finanzbericht testen** → prüft ob Förderungen und Versicherung korrekt erscheinen

---

*Letzte Aktualisierung: April 2026*
