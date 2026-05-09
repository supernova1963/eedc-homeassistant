# Draft: GitHub Issue — PDF-Dokumentation Neustrukturierung

> **Status:** Entwurf, noch nicht gepostet. Nach Review via `gh issue create` in `supernova1963/eedc-homeassistant` anlegen.
>
> **Hintergrund:** Konzept liegt unter `/home/gernot/.claude/plans/sleepy-frolicking-cupcake.md`.
>
> **Nach dem Erstellen:**
> 1. Roadmap-Issue **#110** aktualisieren — neuer Checkbox-Eintrag in Sektion *Geplant*
> 2. `MEMORY.md` Roadmap-Sektion *PDF-Dokumentation* um Issue-Link ergänzen

---

## Titel

```text
PDF-Dokumentation: Neustrukturierung in vier schlanke Einzel-PDFs
```

## Labels

`enhancement`, `documentation`

## Body

```markdown
## Hintergrund

EEDC hat sich in den letzten Monaten rasant weiterentwickelt — die
PDF-Dokumentation ist dabei nicht mitgewachsen. Auf Wunsch aus der
Community wollen wir sie komplett überarbeiten.

## Geplante Lösung

Statt einem einzigen großen PDF soll es **vier schlanke Dokumente** geben,
die einzeln oder gebündelt als ZIP heruntergeladen werden können:

| PDF | Zweck |
|---|---|
| 📋 **Anlagenpass** | Stammdaten, Standort, Investitionen (jede auf eigener Seite), Sensor-Mapping, MaStR-IDs |
| 📊 **Jahresbericht** | Energie-KPIs, Charts, Monatsübersicht — pro Jahr wählbar |
| 💰 **Finanzbericht** | Rendite, Amortisation, Tarifhistorie, Prognose |
| 📁 **Infothek-Dossier** | Verträge, Kontakte, Vertragspartner |

Alle vier in einheitlichem Look, aufgeräumtes Layout, saubere Seitenwechsel
(u.a. jede Investition auf eigener Seite im Anlagenpass).

## Zugriff

Ein neuer **"Dokumente"-Dialog** auf der Anlagen-Seite erlaubt die Auswahl
einzelner oder mehrerer PDFs; bei Mehrfachauswahl landet das Ergebnis als
ZIP im Download-Ordner. Die bestehenden Endpoints und Buttons
(Jahresbericht-Download, Infothek-Export) bleiben als Shortcut erhalten.

## Technisches Vorgehen

- **PDF-Engine:** Wechsel von `reportlab` (aktuell zwei getrennte
  Code-Pfade mit dupliziertem Styling) auf **WeasyPrint** (HTML+CSS → PDF).
  Ergebnis: einheitlicher Look über eine zentrale `styles.css`,
  Template-Änderungen an einer einzigen Stelle.
- **Charts:** Matplotlib → PNG, eingebunden via `<img>` im Jinja-Template.
- **Migrationspfad in 5 Phasen** mit Feature-Flag `PDF_ENGINE` für
  Rollback-Fähigkeit während der Übergangszeit:
  1. Fundament (WeasyPrint + Jinja2, leeres Template, Smoke-Test-Route)
  2. Jahresbericht migrieren
  3. Infothek migrieren
  4. Neue Dokumente (Anlagenpass, Finanzbericht) + Dialog im Frontend
  5. Alte Services entfernen, Feature-Flag aufräumen

## Inhalte pro Dokument

Startpunkt für die Templates — Anregungen in den Kommentaren sind
willkommen.

### Anlagenpass

- Anlagen-Stammdaten (Name, Leistung, Standort, Koordinaten)
- Versorger + aktueller Tarif
- Investitionen, jede auf eigener Seite (technische Parameter,
  Anschaffungskosten und -datum)
- Sensor-Mapping / HA-Sensoren
- MaStR-IDs
- Optional: Foto der Anlage

### Jahresbericht

- Energie-KPIs (Erzeugung, Eigenverbrauch, Einspeisung, Netzbezug)
- Autarkie- und Eigenverbrauchsquote
- PV-Erzeugungs-Chart (Monatsverlauf)
- Energiefluss-Diagramm
- Monatsübersicht als Tabelle
- String-Vergleich SOLL/IST (PVGIS)
- Vorjahresvergleich
- CO₂-Bilanz
- Batterie-, Wärmepumpen-, E-Auto-Daten sofern vorhanden

### Finanzbericht

- Jahres-Rendite und Amortisations-Zeitstrahl
- Tarifhistorie (Netzbezug / Einspeisung)
- Einspeiseerlöse vs. Netzbezugskosten
- 20-Jahres-Prognose
- Förderungen / EEG-Daten
- Wartungs- und Betriebskosten
- Steuer-relevante Aufstellung (EÜR)

### Infothek-Dossier

- Alle Kategorien in einem Dokument, optional nach Kategorie filterbar
- Vertragspartner als eigener Block
- Vertragslaufzeiten / Kündigungstermine als Übersicht
- Liste angehängter Dateien (Name + Größe)
- Markdown-Notizen formatiert gerendert

## Feedback willkommen 💬

- **Wofür** würdet ihr die PDFs konkret einsetzen? (Versicherung,
  Steuerberater, Förderantrag, Eigenarchiv, …)
- **Was fehlt** in der aktuellen Dokumentation und sollte unbedingt rein?
- Gibt es ein **Format-Detail**, das euch besonders wichtig ist (z.B.
  EÜR-konforme Tabelle, MaStR-Auszug, Wartungsprotokoll-Vorlage)?

Auch kurze "Punkte 1, 3, 7 aus dem Anlagenpass reichen mir"-Kommentare
helfen, die Templates passgenau zu bauen 🙏
```

---

## Roadmap-Update für Issue #110

Neuer Checkbox-Eintrag in Sektion **Geplant** (nach *Flexibler Strompreis*):

```markdown
- [ ] **PDF-Dokumentation Neustrukturierung** — Vier schlanke Einzel-PDFs (Anlagenpass, Jahresbericht, Finanzbericht, Infothek-Dossier), einheitlicher Look via WeasyPrint + Jinja2, ZIP-Export, neuer "Dokumente"-Dialog auf Anlagen-Seite. Migration in 5 Phasen mit Feature-Flag. (#<ISSUE-NR>)
```

## Erstellungs-Workflow

1. Draft hier final reviewen
2. `gh issue create` im Repo `supernova1963/eedc-homeassistant` (Titel + Body aus diesem Draft, Labels `enhancement`, `documentation`)
3. **Issue-Nummer notieren** und oben in den Roadmap-Eintrag einsetzen
4. `gh issue edit 110 --body-file <tempfile>` — Roadmap um den neuen Eintrag ergänzen
5. `MEMORY.md` aktualisieren: Roadmap-Sektion *PDF-Dokumentation* um Link zum neuen Issue
6. Phase 1 der Implementierung kann unabhängig vom Feedback starten
