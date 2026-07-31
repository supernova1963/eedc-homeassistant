# ADR-001 — Berechnungs-Layer als Single Source of Truth

**Status:** Akzeptiert (2026-05-19)
**Auslöser:** BKW-Doppelzählung in `komponenten_kwh` (Rainer-PN), gefunden bei Code-Audit nach Anwender-Drift-Meldung. Strukturelle Ursache: paralleler Schreibpfad (Live-Σ-Riemann + HA-LTS-Boundary) mit Schema-Mismatch.

## Regel

Alle Aggregat-Berechnungen über die zentralen Daten-Tabellen (`TagesEnergieProfil`, `TagesZusammenfassung`, `InvestitionMonatsdaten`) — Whitelist-Filter, Σ-Helper, Invarianten, Sub-Key-Resolver, Kennzahlen — werden in `backend/core/berechnungen/` definiert. Domain-Module (`services/`, `api/routes/`) sind ausschließlich Konsumenten.

**Pflicht ab heute:**
1. Neuer Code mit Aggregat-Berechnung wird im Berechnungs-Layer definiert. Domain-Module importieren.
2. Wenn bestehender Code mit duplizierter Aggregat-Logik aus anderem Grund angefasst wird, MUSS dieser Touch die Migration auf den Layer beinhalten.
3. Der Pytest-Konformitäts-Test `tests/test_berechnungs_layer_konformitaet.py` blockiert PRs mit neuen Whitelist-/Inline-Pattern-Definitionen außerhalb des Layers.
4. Der Aggregator (`energie_profil/aggregator.py::aggregate_day`) ruft die Pflicht-Invariante `pruefe_tep_tz_konsistenz` am Ende jedes Schreib-Laufs auf. Verletzung wird als Warning geloggt — Tag wird nicht zurückgehalten, aber Drift ist sofort sichtbar.

## Was bleibt erlaubt

- Bestehende SoT-Module (`core/calculations.py`, `core/field_definitions.py`, `snapshot/plausibility.py`, `snapshot/lts_aggregator.py`, `snapshot/aggregator.py`) bleiben funktional und werden formal als Teil des Berechnungs-Layers betrachtet — sie werden nicht zwingend umgezogen, aber Aufrufer dürfen nicht inline re-implementieren.
- Inline-Σ-Logik innerhalb eines einzelnen Moduls (z.B. lokale Hilfsvariable für eine einzige Funktion) ist OK, solange sie nicht woanders dupliziert wird.

## Was NICHT erlaubt ist

- Eigene Whitelist-Konstanten wie `_PV_PREFIXES = ("pv_", "bkw_")` außerhalb des Layers — direkt aus `backend.core.berechnungen` importieren.
- Inline-Pattern wie `k.startswith("pv_") or k.startswith("bkw_")` außerhalb des Layers — `summe_pv_bkw_kwh()` aus dem Layer benutzen.
- Parallel-Implementierungen von Σ-Berechnungen über dieselben Tabellen-Felder.

## Geteilter Helper ≠ gelöste Drift — auch die EINGABE muss zentral (Lehre #326)

Ein gemeinsamer Aggregat-Helper (z. B. `berechne_finanz_aggregat`) liefert nur dann denselben Wert über alle Read-Sites, wenn er auch **dieselben Eingaben** bekommt. In #326 nutzten zwar alle vier Finanz-Read-Sites denselben Helper, **bauten ihre Eingaben (`FinanzMonatsZeile`) aber jede selbst** — eine löste den Strompreis pro Monat (historische Tarife), zwei nahmen den neuesten Tarif für alle Jahre → ~174 € Drift, die viermal nacheinander auftauchte (jede Reparatur deckte den nächsten Parallelpfad auf). Der WeasyPrint-Jahresbericht (neu 04/2026) riss dabei einen längst gelösten Tarif-Bug wieder auf, weil neuer Code die alte Lösung nicht kannte.

**Regel — bei einer Kennzahl, die an ≥2 Read-Sites gebaut wird:**

1. **Gemeinsamer Eingabe-Builder**, nicht nur ein Formel-Helper. Die Konstruktion des Eingabe-Objekts (inkl. drift-anfälliger Auflösungen wie Tarif-pro-Monat) gehört in **eine** Funktion (DB-I/O → Service-Schicht, nicht core). Beispiel: `services/finanz_zeilen.py` `baue_finanz_zeile`.
2. **Statischer Wächter**, der die Konstruktion außerhalb des Builders verbietet (analog `test_finanz_monatszeile_nur_im_builder`) — so kann auch **künftiger** Code die zentrale Auflösung nicht umgehen.
3. **Symmetrie-Test**, der „Site A == Site B == …" für eine realistische Fixture beweist (inkl. der Edge-Cases, die der Default-Pfad umgeht — z. B. mehrere Jahres-Tarife OHNE Monats-Flex-Ø).
4. **Fakten-Quelle** — der Builder aus Punkt 1 bekommt seine Rohwerte selbst aus **einer** Aufbereitungs-Schicht, nicht aus einer site-eigenen Faltung. Sonst ist nur die letzte Meile zentral: in #326 nutzten alle vier Sichten denselben Aggregat-Helper, und die Drift saß eine Etage tiefer. Heute: `services/monats_fakten.py` für die Monatszeile (ADR-002/**P10**), `services/pv_monatswerte.py` für die PV darin (P7).

Symmetrie-Test allein reicht nicht (er kennt nur die eingetragenen Sites); statischer Wächter allein reicht nicht (er fängt Formel-, nicht Wert-Drift). Erst der Builder macht Drift strukturell unmöglich; Wächter + Symmetrie-Test sichern es ab.

## Eine Aufbereitungs-Schicht ist keine Formel — die Abgrenzung zu `core/berechnungen/`

Die Drift-Inventur der Lese-Sichten (2026-07-31) fand über 23 Sichten × 18 kanonische Größen **keinen einzigen Rechenfehler** im Berechnungs-Layer. Sie fand sechsmal dieselbe Struktur: *jede Sicht faltet die Rohdaten selbst zu Monatswerten*, und dabei fällt jedes Mal etwas anderes weg — mal V2H, mal der Erzeuger hinter dem Zähler, mal der Aggregat-Fallback, mal der Monatstarif, mal der Dienstwagen-Filter. Der Layer war fehlerfrei und die Zahlen trotzdem um bis zu 85 % auseinander.

Daraus folgt eine Schicht, die es vorher nicht gab, und eine klare Grenze:

| | `core/berechnungen/` | `services/monats_fakten.py`, `services/pv_monatswerte.py`, `services/finanz_zeilen.py` |
| --- | --- | --- |
| **Rolle** | die **Formel** — *wie* aus Eingaben ein Wert wird | die **Eingabe-Aufbereitung** — *welche* Rohwerte, kanonisch aufgelöst und gefiltert, überhaupt hineingehen |
| **DB-I/O** | nie (rein, testbar ohne Session) | ja — genau deshalb liegt sie in `services/` |
| **Enthält** | Σ-Helfer, Whitelists, Invarianten, Kennzahlen | Laden, Zeit-/Dienstwagen-Filter, Quellenwahl, Lückenfüllung — und **Aufrufe** in den Layer |
| **Verboten** | Session, Query, Modell-Import | eine eigene Formel. Wer hier rechnet, dupliziert den Layer |

**Praktisch:** Eine Aufbereitungs-Schicht darf keine Aggregat-Formel enthalten — sie ruft `imd_typ_beitrag`, `bkw_finanz_beitrag`, `erzeugung_hinter_zaehler_kwh`, `berechne_verbrauchs_kennzahlen`. Umgekehrt darf der Layer keine Session sehen. Fällt bei einem Umbau auf, dass eine Schicht rechnen *möchte*, ist das der Hinweis auf einen fehlenden Helfer im Layer — nicht die Erlaubnis, ihn dort nachzubauen.

## Eine Formel, die an drei Sichten hängt, gehört auch dann in den Layer, wenn sie kurz ist (Lehre N-12/N-13/N-18, 2026-07-31)

Die Euro-Bewertung der Dienstwagen-Ladung war zwei Zeilen lang — und stand deshalb an jeder Read-Site inline statt im Layer. Ergebnis: **drei Sichten, drei Antworten** für dieselbe Ausgabe. Cockpit bewertete den Netzanteil mit dem Wallbox-Tarif, `aussichten.get_finanz_prognose` mit dem allgemeinen Arbeitspreis (**N-12**), und `ha_export.calculate_anlage_sensors` zog den Posten **gar nicht** ab (**N-13**) — der HA-Sensor `netto_ertrag_euro` stand damit über der Kachel, auf die er sich bezieht.

Die eigentliche Lehre steckt aber in **N-18**: Beide rechnenden Sichten zogen den PV-Anteil zur *Einspeisevergütung* ab, während `berechne_finanz_aggregat` dieselben kWh als Eigenverbrauch zum *Netzbezugspreis* gutschrieb — der Eigenverbrauch ändert sich durch das Dienstwagen-Flag ja nicht. Zwei für sich richtige Halbschritte, die zusammen **+22 ct je verschenkter kWh** Gewinn stehen ließen. Keine der drei Stellen war für sich falsch zu lesen; falsch war erst ihr Zusammenspiel, und das sieht man nur, wenn beide Seiten der Buchung an **einem** Ort stehen.

**Regel:** Kürze ist kein Kriterium. Sobald eine Formel an mehr als einer Read-Site gebraucht wird **oder** die Gegenbuchung zu einer bereits zentralen Formel bildet, gehört sie in `core/berechnungen/` — mit der Begründung im Modul-Docstring, nicht nur der Formel. SoT hier: `core/berechnungen/dienstliche_ladekosten.py`, Wächter `test_berechnungs_layer_konformitaet.py::test_dienstliche_ladung_nur_im_layer_bewertet` (AST: eine `dienstlich…`-benannte Größe darf außerhalb des Helpers nicht multipliziert werden).

## Eine abgelöste Formel stirbt nicht mit dem Layer-Helper — sie stirbt mit ihrem letzten Aufrufer (Lehre F-6/N-21, 2026-07-31)

`berechne_co2_bilanz` ist seit DI-2 die **einzige erlaubte Konstruktions-Stelle** der CO₂-Gesamt-Kennzahl; sein Docstring sagt ausdrücklich, was er ablöst („vorher nur `pv_erzeugung × f_strom`, WP + E-Mob fehlten ganz"). Der Helper stand, die Hauptpfade waren umgestellt — und **zwei Stellen rechneten weiter die alte Formel**, gemessen am 2026-07-31:

| Ort | Zeile |
| --- | --- |
| `frontend/src/pages/auswertung/types.ts` | `co2_einsparung = erzeugung * CO2_FAKTOR_KG_KWH` |
| `backend/services/energie_profil/tage_werte.py` | `co2_einsparung = bilanz.erzeugung_kwh * CO2_FAKTOR_STROM_KG_KWH` |

Ein **Spiegelpaar** — gleicher Feldname, gleiche Formel, gleicher Faktor, gleiche Position hinter dem Finanzen-Block: Monatstabelle im Client, Tagestabelle im Backend. Beide rechneten auf der **Erzeugung** statt auf dem Eigenverbrauch, schrieben also auch der eingespeisten kWh die volle Netzstrom-Vermeidung gut, und beide kannten weder WP noch E-Mobilität. Ein Anwender sah dieselbe Größe für denselben Monat mit zwei verschiedenen Zahlen.

Drei Lehren, und die dritte ist die unbequeme:

1. **Die Ablösung ist erst fertig, wenn der letzte Aufrufer weg ist.** „Der Kanon existiert" und „der Kanon gilt" sind zwei Zustände. Wer eine Formel ablöst, zählt beim Abschluss die verbliebenen Rechenstellen — sonst bleibt es eine unvollendete Migration, die sich später wie eine offene Definitionsfrage anfühlt.
2. **Eine Aggregat-Formel gehört nicht in den Client** — und der Client hat für diese Regel bis dahin **keinen** Wächter gehabt. `pages/auswertung/types.ts` war dieselbe Klasse, die `check:kennwert-roh` auf der Kennwert-Seite bewacht; die CO₂-Seite war offen. Geschlossen durch `npm run check:co2-roh` (baumweit, Baseline 0: `CO2_FAKTOR_KG_KWH` darf im Client nur noch **angezeigt** werden, `× 1000` → g/kWh). Der Wächter ist gegen den Vor-Zustand **rot verifiziert** — er meldet dort genau die vier Rechenstellen (die beiden oben, dazu die Dublette `gesamtErzeugung × Faktor` in `AuswertungenCo2V4.tsx` und den toten Export `lib/calculations.ts::calcCO2Einsparung`).
3. **Ein Teil-Umfang muss im Code stehen, nicht im Kopf.** Der Tages-Pfad kann die volle Bilanz gar nicht bilden: WP-Wärme und E-Mob-Kilometer sind Monatsgrößen, stündlich existiert nur die WP-Stromaufnahme. Er trägt deshalb bewusst nur `co2_pv_kg` — **und schreibt hin, dass Σ Tage ≠ Monatswert ist**, sobald eine WP oder ein E-Auto im Spiel ist. Eine stille Teil-Kennzahl unter dem Namen der vollen ist die nächste Drift; die Spalte heißt im Client entsprechend „CO₂-Einsparung (PV)".

**Deckung, ehrlich getrennt:** *Wächter* (baumweit) ist `check:co2-roh` für die **Client**-Hälfte. Die **Backend**-Hälfte deckt nur eine *Regression* (`tests/test_co2_tages_bezugsgroesse.py`) für den einen Pfad, der die Klasse trug. Ein baumweiter Backend-Wächter fehlt: `CO2_FAKTOR_STROM_KG_KWH` wird außerhalb von `core/` an sechs weiteren Stellen multipliziert (PDF-Jahresbericht, Komponenten-Dashboards, Investitions-ROI). Alle sechs rechnen — gemessen — auf der **richtigen** Bezugsgröße oder auf einer anderen Frage (Prognose je Investition); ein Wächter darüber verlangt ihre Klassifikation und ist deshalb ein eigener Schritt (N-23).

## Datei-Allowlists bewachen die Datei, nicht die Frage (Lehre WP-η, 2026-07-27)

Wächter der Bauart „diese Formel darf nur in Datei X stehen" (`test_inline_gas_kosten_altanlage_nur_im_layer`, `test_gas_co2_faktor_nur_im_helper`) haben einen blinden Fleck: **innerhalb** von X. Genau dort saß die WP-Alternativkosten-Drift. `core/calculations.py` beherbergt den CO₂-SoT `co2_wp_ersparnis_kg` (rechnet `wärme / η_gas × f_gas`) — und zwanzig Zeilen weiter rechnete `berechne_waermepumpe_einsparung` für dieselbe Frage `wärme × f` **ohne η**. Der Wächter-Kommentar hielt das sogar fest („liegt in derselben Datei = erlaubt"), womit die zweite Formel als geprüft *aussah*, obwohl nur ihr Ort geprüft war. Die ROI-Seite nannte dadurch eine andere WP-Ersparnis als Aussichten, HA-Export und WP-Dashboard.

**Regel:** Der Wächter-Scope gehört an die **Frage** („was hätte die Altanlage gekostet?"), nicht an die Datei. Praktisch:

1. **Symmetrie-Test über die Pfade**, nicht nur Formel-Regex: der Parameter-/Prognose-Pfad muss für dieselbe Eingabe denselben Wert liefern wie der gemessene (`test_altkosten_identisch_zum_layer_sot`).
2. **Aufruf-Wächter statt Text-Wächter**, wo möglich: per AST prüfen, dass die Funktion den Layer-Helper *aufruft* (`test_keine_eta_freie_altkosten_formel`) — das fängt auch einen Rückbau, den keine Regex kennt.
3. **Zeilenweise Regex nur mit Gegenprobe.** Eine Regex auf `== "oel"` hätte drei von vier Duplikaten durchgelassen, weil sie `WIRKUNGSGRAD` erst in der Folgezeile nannten. Wer einen Muster-Wächter schreibt, prüft ihn gegen die realen Altfälle, bevor er ihn für Deckung hält.
4. **Restlücken benennen.** Der η-Wächter greift über die Konstanten; eine hartkodierte `0.85` fängt er nicht — das steht so in seinem Docstring, statt als Deckung durchzugehen.

## Migration bestehender Konsumenten

Step-by-step, opportunistisch beim nächsten Touch des betroffenen Codes. Übersicht der bekannten offenen Stellen: siehe Memory `project_berechnungs_layer_offen.md` und `INLINE_PATTERN_GRANDFATHERED` in `tests/test_berechnungs_layer_konformitaet.py`.

Beim Migrieren:
1. Konsument importiert aus `backend.core.berechnungen`.
2. Lokale Whitelist-Definitionen und Inline-Patterns löschen.
3. Eintrag aus `INLINE_PATTERN_GRANDFATHERED` entfernen (Test `test_grandfathered_dateien_existieren_und_enthalten_pattern` meckert sonst).
4. Test-Suite grün halten.

## Verbundene Konzepte

- `docs/KONZEPT-BERECHNUNGS-LAYER.md` — Architektur-Detail, Submodul-Schnitt, geplante Erweiterungen
- `docs/KONZEPT-MONATS-FAKTEN.md` — die Aufbereitungs-Schicht über der Monatszeile (ADR-002/P10): Kontrakt, Feldgruppen, Migrations-Schritte
- `docs/ADR-002-WURZELMUSTER.md` — die Invarianten-Seite: **P10** macht die Fakten-Quelle zur Pflicht, ADR-001 hält sie von der Formel getrennt
- `docs/archive/KONZEPT-DATENPIPELINE.md` Abschnitt 3.4 — „Zentraler Helper Pflicht"
- `docs/archive/KONZEPT-ETAPPE-4-HA-LTS-SOT.md` — Etappe-4-Auslöser, dessen unvollständiger Riemann-Pfad-Rückbau das Berechnungs-Layer-Konzept erst nötig gemacht hat
- `docs/KONZEPT-COUNTER-DAILY-DRIFT.md` — analoge Drift-Klasse für Counter-Felder, wird Teil des Berechnungs-Layers (`counter`-Submodul) wenn die Stelle angefasst wird
- `docs/KONZEPT-BERECHNUNGS-LAYER.md` §6 — Herleitungs-Transparenz: Kennzahl-Helfer liefern eine strukturierte Herleitung (Vertrag zur Style-Guide-Norm A6); Durchsetzung als separater Zukunfts-Punkt nach Projektabschluss

## Verbundene Memory-Einträge

- `feedback_aggregations_drift` — Drift-Pattern (Read-Side, jetzt erweitert um Write-Side via Berechnungs-Layer)
- `feedback_eigenen_code_zuerst` — Verhaltens-Lehre nach BKW-Vorfall: bei jeder Anwender-Drift-Meldung ZUERST eigenen Berechnungscode prüfen
- `feedback_step_by_step_berechnungs_layer` — Migrations-Disziplin für diesen Layer
