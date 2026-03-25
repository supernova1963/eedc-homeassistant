# Konzept: Infothek — Verträge, Zähler & Dokumentation

> Erstellt: 2026-03-25 | Status: **Konzept** | Auslöser: Rainer (PN community.simon42.com #81931)

## Implementierungsstand

| Etappe | Status | Version | Beschreibung |
|--------|--------|---------|-------------|
| **Etappe 1** | Offen | — | Datenmodell, CRUD-API, Frontend-Seite (Kernfelder + Kategorien) |
| **Etappe 2** | Offen | — | Foto-Upload mit Resize, Thumbnails, Lightbox |
| **Etappe 3** | Offen | — | Verknüpfung mit Investitionen, Migration bestehender `stamm_*`-Felder |
| **Etappe 4** | Offen | — | PDF-Export, erweiterte Vorlagen |

---

## Motivation

Rainer (Inexogy-Zähler, Octopus als Lieferant, Stadtwerke als Netzbetreiber) hat das Problem:
PV-Anlagenbetreiber verwalten nicht nur Komponenten, sondern auch **Verträge, Zähler, Kontakte und Dokumente** aus verschiedenen Bereichen — Strom, Gas, Wasser, Fernwärme, Pellets, Versicherungen.

Bisher waren Stammdaten-Felder direkt an Investitionen gekoppelt (`stamm_*`, `ansprechpartner_*`, `wartung_*` im `parameter`-JSON). Das hat zwei Nachteile:

1. **Für die meisten User unnötiger Ballast** in den Investitions-Formularen
2. **Verträge ohne Investitions-Bezug** (Wasserzähler, Gasvertrag) haben keinen Platz

### Lösung

Ein separates, **optionales Modul "Infothek"** innerhalb EEDC:
- Eigene Seite, eigene Models, eigener API-Router
- Nur sichtbar wenn aktiv genutzt (kein leerer Menüpunkt)
- Optionale Verknüpfung zu Investitionen (bidirektional)
- Kernfelder für alle + kategorisierte Vorlagen mit spezifischen Feldern

---

## Naming

**Gewählt: "Infothek"**

Begründung: Kurz, deutsch, signalisiert Nachschlagewerk. Breit genug für Verträge, Zähler, Kontakte und Notizen. Nicht zu technisch, nicht zu verspielt.

Alternativen (verworfen): "Dokumentation" (klingt nach Software-Docs), "Wichtige Infos" (zu lang), "Mein Archiv" (klingt nach alt/abgelegt).

> **Naming noch nicht final** — kann sich im Dialog noch ändern.

---

## Datenmodell

### Model: `InfothekEintrag` (Tabelle: `infothek_eintraege`)

| Feld | Typ | Beschreibung |
|------|-----|-------------|
| `id` | Integer, PK | Auto-Increment |
| `anlage_id` | FK → Anlage | Zugehörige Anlage |
| `bezeichnung` | String(255) | Freitext-Überschrift ("Stadtwerke Strom", "Wasserzähler Keller") |
| `kategorie` | String(50) | Bestimmt die Vorlage (siehe Kategorien) |
| `notizen` | Text | Großes Freitext-Feld für beliebige Informationen |
| `parameter` | JSON | Kategorie-spezifische Felder (bewährtes Pattern aus Investitionen) |
| `investition_id` | FK → Investition, nullable | Optionale Verknüpfung (Etappe 3) |
| `sortierung` | Integer, default 0 | Reihenfolge in der UI |
| `aktiv` | Boolean, default True | Archivierung statt Löschung |
| `created_at` | DateTime | |
| `updated_at` | DateTime | |

### Model: `InfothekFoto` (Tabelle: `infothek_fotos`)

| Feld | Typ | Beschreibung |
|------|-----|-------------|
| `id` | Integer, PK | |
| `eintrag_id` | FK → InfothekEintrag, CASCADE | |
| `dateiname` | String(255) | Original-Dateiname |
| `daten` | LargeBinary | BLOB, serverseitig auf max 500kb resized |
| `thumbnail` | LargeBinary | Kleines Vorschaubild (~50kb) |
| `mime_type` | String(50) | image/jpeg, image/png |
| `beschreibung` | String(255), nullable | Optionale Bildbeschreibung |
| `created_at` | DateTime | |

**Constraint:** Max 3 Fotos pro Eintrag (Backend-Validierung).

---

## Kategorien: Kern + Vorlagen

### Kernfelder (immer sichtbar, unabhängig von Kategorie)

- **Bezeichnung** — Freitext-Überschrift
- **Kategorie** — Dropdown mit Vorschlägen + Freitext-Option "Sonstiges"
- **Notizen** — Großes Textarea
- **Fotos** — Upload-Bereich (Etappe 2)
- **Verknüpfte Investition** — Optionales Dropdown (Etappe 3)

### Kategorisierte Vorlagen (zusätzliche Felder im `parameter`-JSON)

| Kategorie | Icon | Spezifische Felder |
|-----------|------|-------------------|
| **Stromvertrag** | ⚡ | `zaehler_nummer`, `anbieter`, `netzbetreiber`, `tarif_ct_kwh`, `vertragsbeginn`, `vertragslaufzeit_monate`, `kuendigungsfrist_monate`, `kundennummer` |
| **Einspeisevertrag** | ☀️ | `zaehler_nummer`, `verguetung_ct_kwh`, `eeg_anlagen_nr`, `inbetriebnahme_datum`, `anbieter`, `kundennummer` |
| **Gasvertrag** | 🔥 | `zaehler_nummer`, `anbieter`, `tarif_ct_kwh`, `jahresverbrauch_kwh`, `kundennummer`, `vertragsbeginn`, `kuendigungsfrist_monate` |
| **Wasservertrag** | 💧 | `zaehler_nummer`, `anbieter`, `eichdatum`, `naechste_ablesung`, `kundennummer` |
| **Fernwärme** | 🌡️ | `zaehler_nummer`, `anbieter`, `anschlussleistung_kw`, `tarif_ct_kwh`, `kundennummer` |
| **Pellets / Flüssiggas** | 🪵 | `lieferant`, `tankgroesse_l_oder_kg`, `letzte_lieferung`, `preis_pro_einheit`, `einheit` (Liter/kg/Ster), `kundennummer` |
| **Versicherung** | 🛡️ | `versicherungsnummer`, `anbieter`, `deckungssumme_euro`, `jahresbeitrag_euro`, `vertragsbeginn`, `kuendigungsfrist_monate` |
| **Ansprechpartner** | 👤 | `firma`, `name`, `telefon`, `email`, `ticketsystem_url`, `kundennummer`, `position` |
| **Sonstiges** | 📋 | Nur Kernfelder, keine zusätzlichen Vorlagen-Felder |

> **Erweiterbar:** Neue Kategorien können jederzeit hinzugefügt werden (nur Frontend-Schema, kein DB-Change nötig dank JSON-Feld).

### Übergreifende optionale Felder (in jeder Kategorie verfügbar)

Einige Felder sind kategorie-übergreifend sinnvoll und werden als optionale Sektion angeboten:

- **Kontakt-Sektion:** `kontakt_firma`, `kontakt_name`, `kontakt_telefon`, `kontakt_email`
- **Vertrags-Sektion:** `vertragsnummer`, `vertragsbeginn`, `kuendigungsfrist_monate`

Diese erscheinen als aufklappbare Sektion unter den kategorie-spezifischen Feldern, um Redundanz zu vermeiden (nicht jeder Stromvertrag braucht einen separaten "Ansprechpartner"-Eintrag).

---

## Frontend-Design

### Menü-Integration

- Neuer Menüpunkt **"Infothek"** zwischen "Investitionen" und "Einstellungen"
- **Bedingt sichtbar:** Erscheint erst, wenn mindestens ein Eintrag existiert ODER über Settings aktiviert
- Initial: dezenter Hinweis in den Investitionen "Verträge & Zähler? → Infothek einrichten"

### Seiten-Layout

```
┌──────────────────────────────────────────────────┐
│ Infothek                         [+ Neuer Eintrag] │
│                                                    │
│ Kategorien: [Alle] [Strom] [Gas] [Wasser] [...]   │
├──────────────────────────────────────────────────┤
│                                                    │
│ ┌────────────────────────────────────────────────┐ │
│ │ ⚡ Stadtwerke Strom (Netzbetreiber)    [✏️] [🗑️] │ │
│ │ Zähler: Inexogy #12345                         │ │
│ │ Anbieter: Octopus Energy                       │ │
│ │ ──────────────────────                         │ │
│ │ Bis die alle mal miteinander reden dauert      │ │
│ │ es halt ein wenig...                           │ │
│ │                                                │ │
│ │ 📷 2 Fotos  │  → PV-Anlage Dach               │ │
│ └────────────────────────────────────────────────┘ │
│                                                    │
│ ┌────────────────────────────────────────────────┐ │
│ │ 💧 Wasserzähler Keller                [✏️] [🗑️] │ │
│ │ Digitaler Zähler seit 12/2025                  │ │
│ │ Eichdatum: 2025-12-15                          │ │
│ │                                                │ │
│ │ 📷 1 Foto                                     │ │
│ └────────────────────────────────────────────────┘ │
│                                                    │
│ ┌────────────────────────────────────────────────┐ │
│ │ 🔥 Flüssiggas Müller GmbH             [✏️] [🗑️] │ │
│ │ Tank 2.700l, Preis 0,85 €/l                   │ │
│ │ Letzte Lieferung: 2026-01-15                   │ │
│ └────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────┘
```

### Formular (Modal oder Seite)

```
┌──────────────────────────────────────────────────┐
│ Neuer Eintrag                                      │
├──────────────────────────────────────────────────┤
│                                                    │
│ Bezeichnung:  [Stadtwerke Strom (Netzbetreiber)]  │
│ Kategorie:    [Stromvertrag          ▾]            │
│                                                    │
│ ── Vertragsdaten (kategorie-spezifisch) ──        │
│ Zählernummer:      [DE00012345678              ]   │
│ Anbieter:          [Octopus Energy             ]   │
│ Netzbetreiber:     [Stadtwerke Musterstadt     ]   │
│ Tarif (ct/kWh):    [32,5                       ]   │
│ Kundennummer:      [KD-2024-12345              ]   │
│                                                    │
│ ── Kontakt (optional, aufklappbar) ──        [▸]  │
│                                                    │
│ ── Notizen ──                                      │
│ ┌────────────────────────────────────────────────┐ │
│ │ Einspeisevergütung nach langem Kampf mit       │ │
│ │ Stadtwerken bestätigt (März 2026).             │ │
│ │ Inexogy-Zähler, Octopus liefert, Stadtwerke   │ │
│ │ nur Netzbetreiber.                             │ │
│ └────────────────────────────────────────────────┘ │
│                                                    │
│ ── Fotos (max. 3) ──                              │
│ [📷 Foto hochladen]                               │
│ ┌─────┐ ┌─────┐                                   │
│ │ 📷  │ │ 📷  │                                   │
│ │thumb│ │thumb│                                   │
│ └──🗑️─┘ └──🗑️─┘                                   │
│                                                    │
│              [Abbrechen]  [Speichern]              │
└──────────────────────────────────────────────────┘
```

### Mobile-Optimierung

- Karten stacken vertikal (volle Breite)
- Foto-Thumbnails als horizontale Scroll-Leiste
- Kategorie-Filter als horizontale Pill-Leiste (scrollbar)
- Touch-freundliche Buttons (min 44px)

---

## API-Endpunkte

### Etappe 1 — CRUD

```
GET    /api/infothek/                         — Alle Einträge (mit Kategorie-Filter)
GET    /api/infothek/{id}                     — Einzelner Eintrag
POST   /api/infothek/                         — Neuer Eintrag
PUT    /api/infothek/{id}                     — Eintrag bearbeiten
DELETE /api/infothek/{id}                     — Eintrag löschen (oder archivieren)
GET    /api/infothek/kategorien               — Verfügbare Kategorien mit Feld-Schemas
PUT    /api/infothek/sortierung               — Reihenfolge aktualisieren (Batch)
```

### Etappe 2 — Fotos

```
POST   /api/infothek/{id}/fotos               — Foto hochladen (multipart/form-data)
GET    /api/infothek/{id}/fotos               — Fotos eines Eintrags listen
GET    /api/infothek/{id}/fotos/{foto_id}     — Foto abrufen (volle Auflösung)
GET    /api/infothek/{id}/fotos/{foto_id}/thumb — Thumbnail abrufen
DELETE /api/infothek/{id}/fotos/{foto_id}     — Foto löschen
```

### Etappe 3 — Verknüpfungen

```
PUT    /api/infothek/{id}/verknuepfung        — Investition verknüpfen/lösen
GET    /api/investitionen/{id}/infothek       — Infothek-Einträge einer Investition
```

---

## Roadmap / Maßnahmenplan

### Etappe 1 — Kernmodul (geschätzt: 2-3 Sessions)

**Ziel:** Funktionsfähige Infothek mit Bezeichnung, Kategorie, Vorlagen-Feldern und Notizen.

#### Backend

| # | Maßnahme | Dateien |
|---|----------|---------|
| 1.1 | **Model erstellen** — `InfothekEintrag` mit allen Kernfeldern, `parameter` JSON-Feld | `backend/models/infothek.py` (neu) |
| 1.2 | **Model registrieren** — Import in models/__init__.py, create_all | `backend/models/__init__.py` |
| 1.3 | **Pydantic-Schemas** — Create, Update, Response mit parameter-Validierung | `backend/schemas/infothek.py` (neu) |
| 1.4 | **Kategorie-Registry** — Schema-Definition pro Kategorie (Felder, Typen, Labels) | `backend/services/infothek_kategorien.py` (neu) |
| 1.5 | **CRUD-Service** — Erstellen, Lesen, Bearbeiten, Löschen, Sortierung | `backend/services/infothek_service.py` (neu) |
| 1.6 | **API-Router** — 7 Endpunkte (siehe API-Endpunkte Etappe 1) | `backend/api/routes/infothek.py` (neu) |
| 1.7 | **Router registrieren** — In main.py einbinden | `backend/main.py` |
| 1.8 | **Migration** — `run_migrations()` für neue Tabelle | `backend/core/database.py` |

#### Frontend

| # | Maßnahme | Dateien |
|---|----------|---------|
| 1.9 | **TypeScript-Types** — InfothekEintrag, Kategorie-Interfaces | `frontend/src/types/infothek.ts` (neu) |
| 1.10 | **API-Client** — Alle Etappe-1-Endpunkte | `frontend/src/api/infothek.ts` (neu) |
| 1.11 | **Kategorie-Schema** — Frontend-Spiegelung der Vorlagen-Felder (Labels, Typen, Platzhalter) | `frontend/src/config/infothekKategorien.ts` (neu) |
| 1.12 | **Seite: Infothek** — Karten-Liste mit Kategorie-Filter, Sortierung | `frontend/src/pages/Infothek.tsx` (neu) |
| 1.13 | **Komponente: InfothekForm** — Modal-Formular mit dynamischen Vorlagen-Feldern | `frontend/src/components/forms/InfothekForm.tsx` (neu) |
| 1.14 | **Komponente: InfothekKarte** — Einzelne Karte mit Kerninfos + Vorlagen-Highlights | `frontend/src/components/infothek/InfothekKarte.tsx` (neu) |
| 1.15 | **Menü-Integration** — Bedingter Menüpunkt, Route registrieren | `frontend/src/App.tsx` + Navigation |
| 1.16 | **Mobile-Optimierung** — Responsive Karten, Touch-freundlich | Bestandteil von 1.12–1.14 |

### Etappe 2 — Foto-Upload (geschätzt: 1-2 Sessions)

**Ziel:** Bis zu 3 Fotos pro Eintrag, serverseitig resized, mit Thumbnail-Vorschau und Lightbox.

#### Backend

| # | Maßnahme | Dateien |
|---|----------|---------|
| 2.1 | **Model: InfothekFoto** — BLOB-Speicherung mit Thumbnail | `backend/models/infothek.py` |
| 2.2 | **Migration** — Neue Tabelle `infothek_fotos` | `backend/core/database.py` |
| 2.3 | **Bild-Service** — Resize auf max 500kb, Thumbnail-Generierung (~50kb), EXIF-Rotation | `backend/services/infothek_foto_service.py` (neu) |
| 2.4 | **API-Endpunkte** — Upload (multipart), Abruf, Thumbnail, Löschen | `backend/api/routes/infothek.py` |
| 2.5 | **Pillow-Dependency** — Prüfen ob bereits vorhanden, sonst requirements.txt | `requirements.txt` |

#### Frontend

| # | Maßnahme | Dateien |
|---|----------|---------|
| 2.6 | **Foto-Upload-Komponente** — Drag & Drop oder Klick, Vorschau vor Upload | `frontend/src/components/infothek/FotoUpload.tsx` (neu) |
| 2.7 | **Thumbnail-Anzeige** — In InfothekKarte, Klick öffnet Lightbox | `frontend/src/components/infothek/InfothekKarte.tsx` |
| 2.8 | **Lightbox-Komponente** — Vollbild-Ansicht, Blättern, Schließen | `frontend/src/components/infothek/FotoLightbox.tsx` (neu) |
| 2.9 | **Form-Integration** — Foto-Upload im Bearbeitungs-Formular | `frontend/src/components/forms/InfothekForm.tsx` |

### Etappe 3 — Verknüpfung & Migration (geschätzt: 1-2 Sessions)

**Ziel:** Bidirektionale Verknüpfung mit Investitionen. Bestehende `stamm_*`-Felder migrieren und aus Investitionen entfernen.

| # | Maßnahme | Dateien |
|---|----------|---------|
| 3.1 | **FK + API** — `investition_id` Verknüpfung aktivieren, Endpunkte | Backend: routes + model |
| 3.2 | **Frontend: Verknüpfung** — Dropdown "Zugehörige Investition" im Formular | `InfothekForm.tsx` |
| 3.3 | **Frontend: Investitions-Seite** — "Infothek-Einträge" Sektion auf Investitions-Detail | `Investitionen.tsx` |
| 3.4 | **Migration-Tool** — Bestehende `stamm_*`/`ansprechpartner_*`/`wartung_*` aus `parameter`-JSON der Investitionen als Infothek-Einträge importieren. Pro Investition mit gefüllten Feldern wird ein verknüpfter Infothek-Eintrag erstellt (Kategorie "Ansprechpartner" für Kontaktdaten, passende Kategorie für Gerätedaten). Nach erfolgreicher Übernahme: Keys aus dem JSON löschen. | `backend/services/infothek_migration.py` (neu) |
| 3.5 | **UI-Hinweis** — "Stammdaten in Infothek übernehmen?" Button bei Investitionen mit gefüllten Stammdaten. Einmalig pro Investition, danach ausgeblendet. | Frontend |
| 3.6 | **Investitions-Formular verschlanken** — `InvestitionStammdatenSection.tsx` entfernen, Investitions-Formulare zeigen nur noch technische Felder. Link "Infothek-Eintrag anlegen" als Ersatz. | `InvestitionForm.tsx`, `InvestitionStammdatenSection.tsx` (entfernen) |

### Etappe 4 — Erweiterungen (optional, bei Bedarf)

| # | Maßnahme | Beschreibung |
|---|----------|-------------|
| 4.1 | **PDF-Export** — Infothek als PDF exportieren (alle oder gefiltert) | Für Ordner/Aktenführung |
| 4.2 | **Erweiterte Vorlagen** — Neue Kategorien nach User-Feedback | z.B. Förderungen, Genehmigungen |
| 4.3 | **Erinnerungen** — Optionale Datums-Felder mit Hinweis (Kündigungsfrist, Eichdatum) | Nur wenn nachgefragt |
| 4.4 | **Suche** — Volltextsuche über alle Einträge und Notizen | Bei vielen Einträgen |

---

## Technische Entscheidungen

### Warum BLOB statt Dateisystem für Fotos?

- **Portabilität:** DB-Backup enthält alles, keine verwaisten Dateien
- **HA-Kompatibilität:** Add-on-Container haben flüchtige Dateisysteme, nur DB ist persistent
- **Einfachheit:** Kein Pfad-Management, kein Cleanup
- **Nachteil:** DB wird größer (~1,5 MB pro Eintrag bei 3 Fotos). Akzeptabel bei erwarteter Nutzung (<50 Einträge).

### Warum `parameter` JSON statt fester Spalten?

Bewährtes Pattern aus Investitionen:
- Neue Kategorien/Felder ohne DB-Migration
- Frontend bestimmt das Schema, Backend speichert flexibel
- Kein Spalten-Wildwuchs bei vielen Kategorien

### Warum optionales Modul?

- **80% der User** nutzen EEDC für PV-Analyse, nicht für Vertragsverwaltung
- Kein zusätzlicher Menüpunkt für User die es nicht brauchen
- Aktivierung durch erste Nutzung (erster Eintrag) oder Settings-Toggle

---

## Abhängigkeiten

- **Pillow** (Python) — Für Bild-Resize und Thumbnail-Generierung (Etappe 2). Prüfen ob bereits in requirements.txt.
- **pillow-heif** (Python) — HEIC-Support für iPhone-Fotos (Etappe 2)
- **Keine neuen Frontend-Dependencies** — Lightbox mit eigenem Modal, Upload mit nativer File API

---

## Entschiedene Fragen

1. ~~Naming~~ → **"Infothek"** (vorläufig)
2. ~~`stamm_*`-Felder nach Migration~~ → **Entfernen** aus Investitionen nach Migration (Etappe 3). Felder liegen im `parameter`-JSON, kein SQLite-Schema-Problem. Migration-Tool überträgt Daten in Infothek-Einträge, löscht danach `stamm_*`/`ansprechpartner_*`/`wartung_*`-Keys aus JSON.
3. ~~Archiv vs. Löschen~~ → **Archivieren als Standard**, Endgültig-Löschen als Option im archivierten Zustand. `aktiv`-Boolean steuert Sichtbarkeit, Filter "Archivierte anzeigen" in der UI.
4. ~~Kategorie-Filter~~ → **Dropdown** mit "Alle"-Option. Flexibel erweiterbar, mobilfreundlich (Tabs werden bei >6 Kategorien unübersichtlich).
5. ~~Foto-Formate~~ → **JPEG, PNG und HEIC (iPhone)**. Backend konvertiert HEIC automatisch zu JPEG beim Resize. Extra-Dependency: `pillow-heif`.

## Offene Fragen

(derzeit keine)
