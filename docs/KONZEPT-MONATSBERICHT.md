# Konzept — Monatsbericht (#395 Punkt 4, OB73-gif)

> **Status: GEBAUT (2026-08-30).** Abgenommen von Gernot am 30.08. (Sitzung 152), gebaut in
> Sitzung 153. Alle drei vorgelegten Punkte sind entschieden (s. §Abgenommen), dazu Gernots
> Erweiterung „ohne geparkte Elemente in der Monatsansicht".
>
> **Was der Bau gegenüber diesem Text korrigiert hat** — beides gemessen, nicht angenommen:
> * §2/Bedingung 2 nennt **elf** Park-Elemente der Monatsfläche. Das war der Stand von drei
>   Dateien (`CockpitMonatV4` · `MonatBilanz` · `MonatAuswertungBloecke`); über den ganzen
>   Baum sind es **24** `el:`-IDs (dazu kommen `kpi:`-IDs, s. u.). Der Bericht verankert
>   deshalb auch Speicher, Wärmepumpe, E-Mobilität und Finanzen. Gezählt über
>   `CockpitMonatV4` · `MonatBilanz` · `bilanzParkIds` · `MonatAuswertungBloecke` ·
>   `KomponentenSektionen` · `ZaehlerstaendeBlock` · `MonatRahmen::finanzTeaserBlock`;
>   `el:bilanz-pr` und `el:bilanz-spitzen` stehen zwar in derselben Datei, gehören aber
>   der **Tages**-Bilanz und sind hier nicht mitgezählt.
> * Die **`kpi:`-Park-IDs bekommen keinen Anker.** Sie werden zur Laufzeit aus dem
>   Kachel-*Titel* gebildet (`kpi:${title.toLowerCase()…}`) — ein Anker darauf im Backend
>   wäre bei der nächsten Umbenennung still wirkungslos. Das Konzept nennt sie nicht; der
>   Schalter lässt geparkte **Blöcke** weg, nicht einzelne Kennzahl-Kacheln.
>
> ⚑ **Dieses Dokument liegt in `docs/` (getrackt), nicht in `docs/drafts/`.** Begründung:
> **N-289** — 28 Stellen im Quellcode nennen 14 Dokumente unter `docs/drafts/` als SoT, von
> denen keines im Repo liegt. Ein fünfzehntes wäre der Fehler noch einmal.

## Was der Melder will — und was er ausdrücklich nicht will

**OB73-gif, [#395](https://github.com/supernova1963/eedc-homeassistant/issues/395), 2026-08-28,
wörtlich:** *„Hintergrund ist die Ablage der Monatsdaten als PDF im Stile der Cockpit Monats
Ansicht. Ich habe bisher keine Möglichkeit gefunden Monats PDF zu erstellen. Falls doch, wie
komme ich da hin? **In der Infothek muss das nicht verankert sein.**"*

⚠ **Gernots erste Lesart war „archivieren"** (den Bericht einfrieren, wie er damals aussah) und
ist am 28.08. korrigiert worden. Gemeint ist etwas Einfacheres **und** Grundsätzlicheres: einen
Monatsbericht überhaupt **erzeugen** zu können. Die Ablage ist die kleinere Hälfte.

⚠ **Der Ort ist geklärt (Gernot, 30.08.):** *„Berichte sind ja an der Anlage."* Damit deckt sich
seine Vorgabe mit dem Melderwunsch und mit dem Code — der Berichts-Hub hängt bereits an der
Anlage. **Die Infothek-Frage ist erledigt und nicht neu aufzurollen.**

## Der Bestand — gemessen am 30.08., nicht angenommen

**Es ist deutlich weniger zu bauen, als #110 vermuten lässt.** Drei Messungen:

| Was | Stand | Fundstelle |
| --- | --- | --- |
| **Die Monatsdaten** | ✅ vollständig da, **für jeden beliebigen Monat** | `api/routes/aktueller_monat.py:1270` — `jahr` und `monat` sind **bereits Parameter**, nicht nur „aktueller Monat" |
| **Der Ort** | ✅ da, an der Anlage | `components/DokumentationsDialog.tsx`, geöffnet aus `pages/AnlagenTeile.tsx:256` und `v4/EinstellungenV4.tsx:287` |
| **Die Monatsauswahl** | ✅ Muster da | derselbe Dialog trägt seit jeher eine **Jahresauswahl** für den Jahresbericht (`:189` ff.) |
| **Der Renderweg** | ✅ da | `services/pdf/engine.py::render_document` + seit `56a8d3fc` `render_html`; Auslieferung als `Response(media_type=…)` in `routes/dokumentation.py:48` ff. |
| **Die deutsche Schreibweise** | ✅ seit `56a8d3fc` | `services/pdf/formatierung.py`, in der Jinja-Umgebung registriert — ein neues Template bekommt sie geschenkt |
| **Markdown-Erzeugung** | ❌ gibt es nirgends im Backend | gemessen: 0 Treffer |

⇒ **Zu bauen sind: ein Template, ein Markdown-Renderer, zwei Routen, eine Karte im Dialog.**
Keine neue Datenschicht, kein neuer Ort, keine neue Navigation.

`AktuellerMonatResponse` trägt bereits alles, was der Bericht zeigen soll: Energiebilanz,
Speicher, Wärmepumpe (inkl. der Arbeitszahlen je Funktion), E-Mobilität, BKW, Sonstiges,
Finanzen, **Vorjahresvergleich** (`vorjahr`), **SOLL-Vergleich** (`soll_pv_*`), Grundlast — dazu
`feld_quellen` (Herkunft je Wert) und `hinweise`.

## Die drei Entscheidungen (Gernot, 30.08.)

### 1. Ein Bericht, zwei Formate — kein zweiter Bericht

**PDF zum Ablegen, Markdown zum Posten, aus EINEM Context.** Der Markdown-Renderer bekommt
denselben Context wie das PDF-Template; er formatiert ihn nur anders.

⛔ **Warum das die harte Grenze ist — der Präzedenzfall ist gemessen.** Eine
Social-Media-Textvorlage gab es schon (Issue #16, v2.5.0: zwei Varianten, bedingte Blöcke,
PVGIS-Vergleich, CO₂, Netto-Ertrag). Zurückgebaut in **v4.0.5** (`07682e14`), Entscheid Gernot
vom 31.07. wörtlich: *„nicht wieder einführen, sondern zurückbauen … es gibt niemanden, der sie
bräuchte."* Der Rückbaugrund war **Unerreichbarkeit** (sie hing am Teilen-Symbol des alten
Cockpits und lief seit v4.0.0 ohne Konsumenten) — gegen einen erreichbaren Ort trägt er nicht.

⭐ **Aber der wichtigste Satz des Rückbaus ist ein anderer:** Mit dem Endpoint fiel **N-7** weg —
der Social-Text trug eine **eigene Netto-Ertrag-Kurzformel**, ohne §51, USt, BKW-Rest und
Grundpreis. Der Fund wurde nicht behoben, er ist mit dem zweiten Text *verschwunden*.
**Genau das darf nicht wiederkommen.** Ein Markdown-Renderer, der eigene Zahlen bildet, ist die
Wiederauferstehung von N-7 — und diesmal in einem Text, der öffentlich gepostet wird.

**Prüfbar gemacht:** Eine Probe rendert denselben Monat in beide Formate und vergleicht **jede
Zahl**. Sie ist rot, sobald ein Format eine Größe anders bildet.

### 2. Auswahl statt Anonymisierung

⛔ **„Anonymisiert" wird NICHT angeboten**, und das ist eine Entscheidung, keine Vertagung.
Ein PV-Monatsbericht enthält Standort, kWp, Ausrichtung, Ertragsprofil, Tarif und Verbrauch —
die Kombination ist praktisch eindeutig. Genau deshalb arbeitet der Community-Server mit einem
**Hash** und nicht mit „anonymisierten Berichten". Wer „anonymisiert" auf so ein Dokument
schreibt, gibt ein Versprechen, das im Forum widerlegt wird, sobald jemand aus Ertrag und
Standort die Anlage zurückrechnet — und dann steht **unsere** falsche Zusage im Thread.
Das ist die Klasse [[feedback_keine_pseudo_workarounds]].

**Stattdessen entscheidet der Anwender beim Erzeugen**, und er sieht das Ergebnis:

* **Blöcke an/aus** — Energie · Finanzen · CO₂ · Komponenten. Voreinstellung: alle an.
* **Anlagenname und Standort an/aus.** Voreinstellung: **an** (der Regelfall ist die eigene
  Ablage, nicht der Forumspost).
* **„Wie in meiner Monatsansicht"** — geparkte Anzeigen weglassen. Abgenommen von Gernot am
  30.08. als Erweiterung; die Ausgestaltung darunter ist gemessen, nicht angenommen.

#### Die Park-Erweiterung — machbar, aber mit drei Bedingungen

⭐ **Sie macht die Melder-Formulierung erst wahr.** Er wollte es *„im Stile der Cockpit Monats
Ansicht"* — mit der Erweiterung heißt das nicht „im Stil der Ansicht allgemein", sondern **im Stil
seiner Ansicht**. Das ist der stärkere Ort als vier grobe Themenschalter.

**Bedingung 1 — der Client liefert die Liste, das Backend führt keine.**
Der Park-Zustand lebt **nur im Browser-`localStorage`** (`eedc-park:v4-cockpit-monat`, Schema
`[{id,titel}]`); das Backend kann ihn nicht lesen. Der Client schickt die geparkten IDs beim
Erzeugen mit.
⛔ **Und er muss es tun, nicht das Backend nachbilden.** Die Park-Doktrin sagt es wörtlich:
*„statische Park-ID-Liste bricht, sobald ein Element konditional rendert → IDs immer aus dem
Render-Pfad ableiten, nie hart daneben."* Ein Mapping „Park-ID → Berichtsblock" im Backend wäre
genau diese statische Liste — sie driftet beim ersten neuen Element, und `check:park-leertest`
sieht sie nicht, weil sie außerhalb des Render-Pfads liegt.

**Bedingung 2 — zwei Granularitäten, bewusst getrennt.**
Die Monatsfläche trägt **elf** Park-Elemente, und es sind **Einzelanzeigen**, keine Themen:
`el:verlauf` · `el:bilanz-vergleich` · `el:bilanz-grundlast` · `el:bilanz-monatsprognose` ·
`el:bilanz-verteilung` · `el:bilanz-geraete` · `el:kategorien-erzeugung` ·
`el:kategorien-verbrauch` · `el:tagesprofil` · `el:peak-netzbezug` · `el:peak-einspeisung`
(gemessen 30.08. in `CockpitMonatV4.tsx` · `MonatBilanz.tsx` · `MonatAuswertungBloecke.tsx`).
Die vier Themenschalter bestimmen also **was für ein Bericht**, der Park-Zustand feilt **innerhalb**.
Beides zusammen ist widerspruchsfrei — aber es sind zwei Ebenen, und der Bericht darf sie nicht
vermischen.

**Bedingung 3 — ein sichtbarer Schalter, keine stille Regel. ⭐ Das ist meine Abweichung von der
naheliegenden Umsetzung, und sie hat zwei Gründe:**
* **Der Zustand ist per Browser, nicht per Anlage.** Wer am Tablet parkt und am PC den Bericht
  zieht, bekommt einen **anderen Bericht** — ohne Hinweis, ohne dass etwas kaputt ist. Ein
  stilles „übernimmt automatisch" wäre für den Anwender nicht erklärbar.
* **Geparkt heißt „nicht auf meinem Bildschirm", nicht „nicht in meinem Archiv".** Wer eine
  Anzeige wegräumt, um Platz zu schaffen, will sie im Jahresarchiv womöglich trotzdem haben.
  Ohne Schalter müsste er zum Erzeugen erst entparken und danach wieder parken.

⇒ **Ein Kontrollkästchen „Wie in meiner Monatsansicht (geparkte Anzeigen weglassen)",
voreingestellt AN** — und **gar nicht angezeigt, wenn nichts geparkt ist**: eine Frage ohne
Gegenstand ist schlechter als keine Frage.

**Der Unterschied ist Überprüfbarkeit:** Was im Text steht, sieht er. „Anonymisiert" müsste er
uns glauben.

⚑ **Ein anonymer Weg existiert bereits** und wird nicht gedoppelt: der Community-Benchmark mit
`/?anlage=HASH` (Teilen · im Browser öffnen · zurückziehen). Ein zweiter anonymer
Veröffentlichungsweg daneben wäre der zweite Turm, den der v4.0.5-Rückbau gerade beseitigt hat.

### 3. Tagesberichte: jetzt nicht — und später anders gebaut

⛔ **Nicht in diesem Paket.** Zwei Gründe, beide belegt:
* **Kein Melder.** OB73-gif fragt nach Monatsdaten.
* **Die Tagesebene trägt dokumentierte Grenzen:** Σ Tage ≠ Monat ist beim CO₂ *by design* (der
  Tageswert trägt nur `co2_pv_kg`, WP-Wärme und E-Mob-km gibt es nur monatlich), und V2H kennt
  die Tages-/Snapshot-Ebene gar nicht. Ein **veröffentlichter** Tagesbericht, dessen Summe nicht
  zum Monat passt, erzeugt genau die Forum-Rückfrage, die wir uns selbst eingebrockt hätten.

⭐ **Gernots Vorgabe für später, wörtlich (30.08.):** *„wobei ich den bewußt anders aufgebaut
sehe, wie Jahres- oder Monatsberichte."* **Ein Tagesbericht ist also kein Monatsbericht mit
anderem Zeitraum.** Wer ihn eines Tages baut, entwirft ihn eigenständig — und stößt dabei genau
auf die zwei Grenzen oben, die dann Teil des Entwurfs sind statt seine Überraschung.
**Diese Zeile ist die Vorgabe; sie ist keine Zusage und trägt keinen Termin.**

## Der Bauschnitt

| Nr. | Was | Wo |
| --- | --- | --- |
| **1** | Context-Builder `build_monatsbericht_context(db, anlage_id, jahr, monat, blöcke, mit_identität)` — ruft die **bestehende** Monats-Aufbereitung, faltet **nichts** selbst (ADR-002/P10) | `services/pdf/builders/monatsbericht.py` |
| **2** | PDF-Template im Stil der Cockpit-Monatsansicht; Formatierer kommen aus der Umgebung | `services/pdf/templates/monatsbericht.html` |
| **3** | Markdown-Renderer über **denselben** Context | `services/pdf/builders/monatsbericht_markdown.py` |
| **4** | **Eine** Route mit `?format=pdf\|md` — zwei Endpunkte hätten zwei Aufbereitungen eingeladen | `api/routes/dokumentation.py` |
| **5** | Fünfte Karte im Berichts-Hub + **Monatsauswahl** (genau EIN Monat) nach dem Muster der Jahresauswahl + die Auswahl-Schalter aus §2, **inkl. der geparkten IDs aus dem `localStorage`** | `components/DokumentationsDialog.tsx` |
| **6** | Handbuch-Abschnitt (`docs/`, `sync-help.sh`) | [[feedback_doku_und_hilfe_mitpflegen]] |

**Proben, die das Konzept tragen:**
1. **Beide Formate, jede Zahl gleich** (die N-7-Sicherung, s. §1).
2. **Ein abgewählter Block erscheint in keinem der beiden Formate** — und die Zahlen der
   übrigen ändern sich dadurch **nicht**.
3. **Ohne Identität** stehen Anlagenname und Standort in keinem der beiden Formate.
4. **Deutsche Schreibweise** in beiden (erbt aus `formatierung.py`, aber ungeprüft ist ungeprüft).
5. **Ein Monat ohne Daten** nennt den Grund, statt Nullen zu zeigen (die F-43-Klasse).
6. **Eine geparkte Anzeige fehlt in beiden Formaten** — und die Zahlen der übrigen ändern sich
   dadurch **nicht** (ein Park-Zustand blendet aus, er rechnet nicht um).
7. **Ohne mitgeschickte Park-Liste ist der Bericht vollständig.** Das ist der Fall „anderer
   Browser" aus §2/Bedingung 3 und darf nichts weglassen.

## Abgenommen (Gernot, 2026-08-30)

1. ✅ **Vier Themenschalter** — Energie · Finanzen · CO₂ · Komponenten. **Erweitert um
   „ohne geparkte Elemente in der Monatsansicht"** (Gernots Zusatz); Ausgestaltung in §2,
   drei Bedingungen.
2. ✅ **Download UND Zwischenablage** für den Markdown-Text — wer postet, kopiert.
3. ✅ **Genau EIN ausgewählter Monat.** Keine Spanne — die ist der Jahresbericht mit anderem
   Filter, und den gibt es.

**Damit ist das Konzept inhaltlich abgenommen.** Was vor dem Bau noch fehlt, ist nur die
Freigabe des Kopfs (Status „ENTWURF" → „ABGENOMMEN") und die Entscheidung, in welchem Paket
es fährt.

### Eine Voreinstellung habe ich selbst gesetzt, statt sie vorzulegen

**Anlagenname und Standort sind voreingestellt AN**, weil der Regelfall die eigene Ablage ist
und nicht der Forumspost. Wer teilt, schaltet ab — nicht umgekehrt. Falls das falsch herum ist,
ist es eine Zeile.

## Geprüft gegen

| Quelle | Ergebnis |
| --- | --- |
| Melder-Wortlaut #395 (2026-08-28) | **hält ein** — „Infothek muss nicht" deckt sich mit Gernots Korrektur |
| #110 §Anlassbezogen, Punkt „Monatsbericht als PDF" | **hält ein** — „zuerst überhaupt erzeugen können, Ablage ist die kleinere Hälfte" |
| Commit `07682e14` (Rückbau Social-Vorlage) + **N-7** | **weicht ab von der ersten Idee** — ein zweiter Text mit eigenen Formeln ist ausgeschlossen; daher ein Context, zwei Renderer |
| Tor-3-Regel „kein zweiter Turm" (29.08.) | **angewandt** — ein zweiter Bericht wäre einer, zwei Formate eines Berichts nicht |
| `aktueller_monat.py:1270` (jahr/monat als Parameter) | **weicht ab von #110s Eindruck** — die Datenschicht ist da, es fehlt nur der Renderer |
| `DokumentationsDialog.tsx` | **hält ein** — der Ort existiert und hängt an der Anlage |
| **N-289** (Drafts als SoT) | **angewandt** — dieses Dokument geht nach der Abnahme in `docs/`, nicht in `docs/drafts/` |
| ADR-002/**P10** | **angewandt** — der Builder ruft die Monats-Aufbereitung, er faltet nicht selbst |
| **Park-Doktrin** ([[feedback_park_doktrin_atomar]]) | **angewandt** — „IDs aus dem Render-Pfad, nie hart daneben": der Client liefert die Liste, das Backend führt keine |
| `ParkContext.tsx` + `reference_park_zustand_reproduktion` | **weicht ab von der naheliegenden Umsetzung** — der Zustand lebt nur im `localStorage` und ist per Browser; deshalb ein sichtbarer Schalter statt einer stillen Regel |
| Die elf Park-IDs der Monatsfläche | **gemessen 30.08.** — Einzelanzeigen, nicht Themen ⇒ zwei Granularitäten, bewusst getrennt |
