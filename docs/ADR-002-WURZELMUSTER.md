# ADR-002 — Sechs Wurzelmuster für Daten-, Zugriffs- und Aggregations-Invarianten

**Status:** Akzeptiert (2026-07-26)
**Auslöser:** Die v4.0.1-Runde heilte 19 Fundstellen einzeln — und **jeder Fix legte den nächsten frei**, weil dieselbe Ursache an mehreren Stellen unabhängig kopiert war. Der Sweep dahinter (`docs/drafts/BEFUND-SWEEP-WURZELMUSTER.md`) zählte nicht Symptome, sondern Ursachen: **sechs Muster, 44 Fundstellen**. Diese ADR schreibt die Muster als Regeln fest, damit sie nicht neu entstehen.

**Abgrenzung zu den anderen SoT-Regimen (bewusst, nicht kosmetisch):**

| Dokument | Regelt |
| --- | --- |
| `docs/KONZEPT-STYLE-GUIDE.md` (Regel 0/0a) | **Darstellung** — Farben, Komponenten, Typografie, Chart-Konventionen |
| `docs/ADR-001-BERECHNUNGS-LAYER.md` | **Schichtung** — wo eine Aggregat-Formel definiert wird (`core/berechnungen/`) |
| **ADR-002 (dieses Dokument)** | **Invarianten** — welche Aussage ein Wert überhaupt tragen darf, und woher er kommen muss |

P1–P6 sind keine Darstellungsregeln und gehören deshalb **nicht** in den Style-Guide. Sie sind auch keine Schichtungsregel: ADR-001 sagt, *wo* eine Formel steht; ADR-002 sagt, *was* sie behaupten darf.

## Form-Präzedenz: ADR + pytest-Konformitätswächter

ADR-001 hat seit Juni 2026 mit `backend/tests/test_berechnungs_layer_konformitaet.py` ein maschinelles Gegenstück. ADR-002 hat es ebenfalls — `test_wurzelmuster_konformitaet.py` plus vier Regressions-/Symmetrie-Dateien. **Das ist dasselbe Paar, kein neues Muster.**

Ein Unterschied ist erwähnenswert, aber ausdrücklich **kein** Vereinheitlichungsbedarf: der ADR-001-Wächter arbeitet per **Grep + Whitelist-Datei**, die ADR-002-Wächter per **AST**. Das Werkzeug folgt dem Muster, nicht umgekehrt — ADR-001 sucht Textmuster (`k.startswith("pv_")`), ADR-002 sucht Aufrufformen, die mehrzeilig und über Aliase laufen (`(imd.verbrauch_daten or {}).get(KEY)`). Ein Regex fände sie nicht.

**Backend-Wächter sind pytest, keine `check:*`-Skripte.** Alle 23 `check:*` sind Frontend-Node-Skripte (`eedc/frontend/scripts/check-*.mjs`). Ein Backend-Grep-Skript daneben wäre eine zweite Mechanik für dieselbe Aufgabe; als pytest läuft der Wächter im bestehenden Gate mit und die Baseline steht als Konstante im Code statt in einer separaten Allowlist-Datei.

---

## Die sechs Regeln

Die Spalte **„gesichert durch"** ist Pflicht und trägt den **ehrlichen Stand von heute**. Ohne sie ist eine ADR eine Wunschliste; mit ihr ist sie eine Landkarte, aus der man den nächsten Schritt abliest.

| # | Regel | gesichert durch (Stand 2026-07-26, nach A20) |
|---|---|---|
| **P1** | **Ein Anlagen-Kennwert darf nie aus EINER einzelnen Investition abgeleitet werden** — außer der Aufrufer hat vorher bewiesen, dass alle Investitionen in diesem Kennwert übereinstimmen (Guard im Code, nicht im Kommentar). | `tests/test_wurzelmuster_p1_orientierung.py` — **8 Tests** über eine ausgeglichene Ost/West-Fixture, die den Kollaps auf eine Orientierung sichtbar macht (Kanon-Pfad, Fallback-Pfad, Teilsummen-Meldung, `solar_prognose`, Live-Wetter-GTI, kWp über den SoT, `parameter`-gepflegte Module, Prefetch-Key). Ein Grep-Wächter ist **nicht möglich** (s. u.). |
| **P2** | **Der kWp-Anteil ist ein Prognose-Schlüssel, kein Ertragsschlüssel.** Auf der IST-Seite verteilt er nur, wenn kein Messwert existiert — und dann **gekennzeichnet**. | `tests/test_wurzelmuster_p2_symmetrie.py` — Σ Pro-Modul (`/cockpit/pv-strings-gesamtlaufzeit`) == Σ Anlagen-Summe (`/monatsdaten/aggregiert.pv_module_kwh`) über **5 Konstellationen** (nur Aggregat · alle gemessen · Messwerte schlagen Aggregat · Teil-Lücke **mit** Aggregat · gar keine Quelle), **Baseline 0**. Dazu `test_pv_verteilung_helper.py`, `test_aggregiert_kwp_verteilung.py`, `test_pv_strings_kwp_verteilung.py`. |
| **P2-A** | **Benannte Ausnahme N42 — Teil der Regel, nicht ihr Gegner.** Bei einer **Teil-Lücke ohne Aggregat** (ein Modul gemessen, das andere nicht, kein Anlagen-Gesamtwert) behält die **Pro-Modul-Sicht** ihre Messwerte, während die **Anlagen-Summe bewusst nichts zeigt**: eine Teilsumme als „Gesamt-PV" auszuweisen wäre irreführend, einen Messwert wegzuwerfen wäre Datenverlust. **`Σ pv_strings ≠ Σ /aggregiert` ist dort gewollt und kein Aggregations-Drift.** | Festgeschrieben in `04ac50bc`: Docstring an `core/berechnungen/pv_verteilung.py::resolve_pv_je_modul` + am Test `test_pv_strings_kwp_verteilung.py::test_teilluecke_ohne_aggregat_behaelt_messwert`. Der Symmetrie-Wächter nimmt den Fall über `_N42_TEILLUECKE` **ausdrücklich aus** und prüft ihn stattdessen auf seine eigene, asymmetrische Erwartung (`test_n42_teilluecke_ohne_aggregat_ist_bewusst_asymmetrisch`). **Jeder künftige Symmetrie-Wächter muss den Fall ebenso ausnehmen** — sonst „repariert" der nächste Durchgang die Regel weg. |
| **P3** | **Investitions-Kennwerte werden ausschließlich über den SoT-Helper gelesen** (`get_inv_value` / `get_pv_kwp` / `get_pv_neigung` / `get_pv_azimut`). Ein Literal-Schlüssel im `parameter`-JSON ist nur gültig, wenn er im Kanon `core/investition_parameter.py` bzw. `lib/investitionParameter.ts` steht. | AST-Wächter aus `04ac50bc`: `test_wurzelmuster_konformitaet.py::test_p3_distribute_by_param_nur_ueber_die_zuordnungs_sot` — **Baseline 0** (`N48_BASELINE_AUSNAHMEN` ist leer), erfasst Aufruf **und** Import; dazu die Gegenprobe `::test_p3_zuordnungs_sot_existiert_noch`, damit das Gate nicht still grün wird, wenn die SoT umbenannt wird. Helper-Verhalten: `test_inv_value_spalten_fallback.py`. |
| **P4** | **Ein Wert-Pfad darf nie eine Null oder eine Teilsumme als gültiges Ergebnis ausliefern, ohne dass die Antwort selbst es sagt.** Die Unvollständigkeit gehört in die **Response** (`hinweise`/Provenance), nicht ins Log. | Response-Vertrag + Anzeige seit A17 (`f1720cc0`), geprüft in `tests/test_wurzelmuster_p4_teilsumme.py`: `vollstaendig=False ⇒ nichtleeres hinweise`, der **Wert wird nicht ersetzt, nur beschriftet**, vollständiger Fan-out bleibt still, 24 Nullen ohne Prognose sagen es, Solcast-Profil-von-heute wird als Näherung ausgewiesen. Ein Grep-Wächter ist **nicht möglich** (s. u.). Referenzform: `live_wetter.py` (`verfuegbar` + `grund`). |
| **P5** | **Die aktive PVGIS-Prognose ist genau `ist_aktiv == True`, `ORDER BY abgerufen_am DESC`, `LIMIT 1`.** `ist_aktiv` ist **Nutzerwille** (eine ältere Prognose zu aktivieren ist erlaubt) — „die neueste" wäre stumme Übersteuerung, „irgendeine aktive" ein Zufallswert. | SoT `backend/services/prognose_auswahl.py`; **alle 23 Lesestellen** darauf umgestellt (`c6bbb079`). AST-Wächter `test_wurzelmuster_konformitaet.py::test_p5_aktive_prognose_nur_ueber_den_auswahl_sot` — Baseline 0, mit **3 klassifizierten Flag-Setzern** in `P5_BASELINE_AUSNAHMEN` (`pvgis.py` Verwaltung · `json_operations.py` Export/Import-Normalisierung · `demo_data.py` Schreibpfad); Gegenprobe `::test_p5_auswahl_sot_traegt_die_regel_noch` prüft, dass `limit(1)` und `order_by(abgerufen_am.desc())` im Helper stehen. **DB-seitig zusätzlich ein partieller Unique-Index** (`INDEX_EINE_AKTIVE_PROGNOSE`, `sqlite_where=ist_aktiv = 1`) — die Invariante hängt nicht an der Disziplin der Schreibpfade. Verhalten in `tests/test_wurzelmuster_p5_invariante.py` (Index greift · Bestandsbereinigung **deaktiviert statt löscht** · Import normalisiert auf genau eine aktive und respektiert eine bewusst aktivierte ältere · keine 500er in Daten-Checker/Social-Karte · kein doppelter SOLL im Monatsbericht). |
| **P6** | **Ein Literal-Schlüssel auf einem JSON-Feld braucht eine Schlüssel-SoT.** Ein Zugriff, dessen Tippfehler still `0` liefert (und `0` sieht aus wie „keine Daten"), ist nur zulässig, wenn ein Wächter den Schlüssel gegen die SoT prüft. | AST-Wächter aus `04ac50bc`: `test_wurzelmuster_konformitaet.py::test_p6_verbrauch_daten_schluessel_stehen_in_der_feld_sot` gegen `core/field_definitions.py` — **Baseline 2, klassifiziert** (`sonderkosten_notiz` = Freitext, `sonstige_positionen` = Liste, beide keine Messfelder); `::test_p6_baseline_ausnahmen_sind_noch_belegt` verhindert, dass eine verwaiste Ausnahme später einen echten Treffer deckt. |

**Als Landkarte gelesen:** vier der sechs Muster (P1, P2, P4, P5) sind heute durch **Verhaltenstests** gesichert, zwei (P3, P6) durch **Struktur-Wächter**. Offen bleiben die in §„Was noch nicht gewächtert ist" genannten Punkte.

---

## Warum für P1 und P4 kein Grep-Wächter existiert

Das ist eine Entscheidung, keine Lücke.

- **P1:** `[0]` auf einer Investitions-Liste ist in geguardeten Fällen **korrekt** — `len(pv_module) == 1`, `len(unique_orientations) == 1`. Der Guard steht in einer **anderen Zeile** als der Zugriff. Ein Grep-Wächter behandelte die sauberen Fälle (`prefetch_service`, `solar_prognose`, `community_service`, `social.py` Ausrichtungs-Label) wie die Verstöße. Stattdessen: ein Regressionstest, der eine Multi-Orientierungs-Anlage durch **jeden** Pfad schickt und zählt, wie viele Orientierungsgruppen beim Wetter-Abruf ankommen.
- **P4:** `except → return 0/None` ist im **Connector-/Wetter-Layer die richtige** Form (~40 Stellen: Provider antwortet nicht → `None` → der Aufrufer schreibt gar nichts) und im **Wert-Pfad die falsche**. Der Unterschied liegt nicht im Ausdruck, sondern darin, ob der Aufrufer den Wert **ausliefert**. Stattdessen: ein Response-Vertrags-Test, der am HTTP-Ergebnis prüft, nicht im Log.

---

## Was noch nicht gewächtert ist (bewusst offen)

| Punkt | Warum offen | Voraussetzung |
| --- | --- | --- |
| `parameter`-Schlüssel gegen `investition_parameter.py` (P3, Regex-Baseline 3) | Der Kanon kennt für die PV-Leistung **keinen** Eintrag; ein Wächter müsste heute eine Ausnahme eintragen, wo eine Kanon-Ergänzung gehört. | `PARAM_PV_MODULE` um den geltenden kWp-Schlüssel ergänzen, Legacy-Keys als solche dokumentieren. |
| kWp-Helper-Pflicht in `services/` + `api/routes/` (P3) | Baseline war 13 Stellen; ein Teil davon ist mit A20 gefallen, der Rest ist Fallback-Nenner ohne sichtbaren Fehler. | Baseline neu erheben, dann Regex-Wächter mit klassifizierter Restmenge. |
| PVGIS-`monatswerte`-Schlüssel `e_m`/`h_m`/`sd_m`/`monat` (P6, 17 Literal-Stellen) | Es gibt **gar keine** Schlüssel-SoT — nur einen Kommentar am Model. Erst Konstanten bauen, dann wächtern. | `PVGIS_MW_*`-Konstanten (oder ein Pydantic-`PVGISMonatswert`) in `models/pvgis_prognose.py`. |
| Dead-Export-Wächter (jede öffentliche `async def` in `services/` braucht einen Importeur) | Der Wächter griffe weit über den Anlass hinaus; ohne vorher erhobene Baseline wäre er ein Aufräum-Paket, kein Wächter. | Baseline erheben (P0b-Dead-Code). |

**`e_m` ist gefährlicher, als es aussieht:** dieselbe Größe heißt im gespeicherten JSON `e_m`, in der normalisierten Tabelle `PVGISMonatsprognose.ertrag_kwh` und im Export noch anders. Drei Namen über drei Schichten — die Voraussetzung dafür, dass der ursprüngliche Tippfehler-Bug (`e_month_kwh`) jahrelang unentdeckt blieb.

---

## Korrekturen gegenüber dem Sweep-Bericht

`docs/drafts/BEFUND-SWEEP-WURZELMUSTER.md` beschreibt den Stand **vor** den A17-/A20-Paketen. Fünf Stellen sind überholt; hier gilt die korrigierte Fassung, damit diese ADR nicht einen falschen Status zementiert:

1. **§1 „gesichert durch: nichts"** — gilt für **P1, P2, P4 und P5 nicht mehr.** Alle vier haben inzwischen Tests (Tabelle oben).
2. **§2, Wirkung von N52 und N53 war am Code falsch beschrieben.**
   - **N52** war *nicht* der Orientierungs-Kollaps: im Multi-String-Fall gehen Neigung und Azimut **gar nicht** an OpenMeteo. Der echte Fehler war eine **direkt aus der Spalte gelesene kWp** — ein Modul, dessen Nennleistung nur im `parameter`-JSON gepflegt war, fiel damit **ganz aus der Gruppierung und aus der Live-Gesamtleistung** (14,0 statt 10,0 kWp).
   - **N53** war eine **tote lokale Variable** und wurde **entfernt**, nicht korrigiert.
3. **§3.3 und die §9-Tabelle: N61 war schon vor A17 geschlossen** (`f06a993f`) — die Vorschlags-Beschriftung im Monatsabschluss trug bereits die ehrliche Herkunft.
4. **§4.1 „drei Konventionen"** gilt nicht mehr: `get_pv_kwp` liest inzwischen **beide** Legacy-Keys (`parameter["kwp"]` **und** `parameter["leistung_kwp"]`), damit `get_pv_kwp ⊇ get_inv_value("leistung_kwp")`. Wer eine kWp gepflegt hat, wird von beiden Wegen gefunden. Offen bleibt allein der fehlende **Kanon-Eintrag** (s. Tabelle oben).
5. **§8: die dort vorgeschlagenen Testdateinamen stimmen nicht mit den gebauten überein.** Verbindlich sind:

   | Muster | gebaute Datei |
   | --- | --- |
   | P3 · P5 · P6 (Struktur) | `backend/tests/test_wurzelmuster_konformitaet.py` |
   | P1 | `backend/tests/test_wurzelmuster_p1_orientierung.py` |
   | P2 | `backend/tests/test_wurzelmuster_p2_symmetrie.py` |
   | P4 | `backend/tests/test_wurzelmuster_p4_teilsumme.py` |
   | P5 (Verhalten) | `backend/tests/test_wurzelmuster_p5_invariante.py` |

---

## Pflicht ab heute

1. **Neuer Code, der einen Anlagen-Kennwert bildet, eine IST-Größe verteilt, einen Investitions-Kennwert liest, eine unvollständige Antwort ausliefert, die aktive Prognose wählt oder einen JSON-Literal-Key liest**, hält P1–P6 ein.
2. **Wer eine Baseline-Ausnahme hinzufügt, begründet sie im Klartext neben dem Eintrag** — warum die Stelle das Muster *setzt* statt es zu *verletzen*. Ein Lesepfad gehört nie in eine Baseline.
3. **Wer eine SoT umbenennt oder verschiebt, zieht den zugehörigen Gegenproben-Test mit.** Ohne ihn wird das Gate still grün und prüft ab da nichts mehr.
4. **Wer einen neuen Symmetrie-Wächter baut, nimmt N42 explizit aus** (P2-A).

## Verbundene Dokumente

- `docs/ADR-001-BERECHNUNGS-LAYER.md` — Schichtentscheidung und ihr Konformitätswächter (Form-Präzedenz)
- `docs/KONZEPT-BERECHNUNGS-LAYER.md` — Submodul-Schnitt des Berechnungs-Layers
- `docs/drafts/BEFUND-SWEEP-WURZELMUSTER.md` — der Sweep, aus dem diese Regeln stammen (Stand vor A17/A20, s. Korrekturen oben)
- `docs/KONZEPT-STYLE-GUIDE.md` — das **andere** SoT-Regime (Darstellung); die zwei werden nicht vermischt

## Verbundene Memory-Einträge

- `feedback_aggregations_drift` — die Drift-Klasse, aus der P2 und P5 stammen
- `feedback_regelsaetze_eigene_adr` — warum Regelsätze aus Sweeps eine eigene ADR bekommen und nicht in den Style-Guide wandern
- `feedback_keine_regel_behaupten_ohne_code_beleg` — der Grund für die Pflicht-Spalte „gesichert durch"
