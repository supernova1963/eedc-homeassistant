# Konzept — Monatsbericht (#395 Punkt 4, OB73-gif)

> **Status: GEBAUT (2026-08-30), Stufe 1 + Stufe 2.**
>
> ⛔ **Drei Entscheide vom 30.08. heben Teile der Stufe-1-Abnahme wieder auf** — sie stehen
> unten in §Stufe 2 §„Was der Dialog-Durchgang zurückgenommen hat" und gelten:
> **kein Markdown-Format** · **kein Identitäts-Schalter** · **die Optionen stehen in der Karte
> des Dokuments**. Wer §Abgenommen (Stufe 1) liest, liest den Stand vom Vormittag.
>
> *(Alter Statustext:)* **Stufe 1 GEBAUT (2026-08-30) · Stufe 2 ENTWURF.** Stufe 1 abgenommen von Gernot am
> 30.08. (Sitzung 152), gebaut in Sitzung 153 — sie liefert die **Zahlen**. **Stufe 2 (unten,
> eigener Abschnitt) liefert die Aufmachung** und wartet auf Freigabe; ihre Richtung ist am
> 30.08. freigegeben (*„gerne auch ein Dokument, versuchen wir es"*).
>
> Alle drei zu Stufe 1 vorgelegten Punkte sind entschieden (s. §Abgenommen), dazu Gernots
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

`AktuellerMonatResponse` trägt die **Zahlen** der Bilanz: Energiebilanz, Speicher, Wärmepumpe
(inkl. der Arbeitszahlen je Funktion), E-Mobilität, BKW, Sonstiges, Finanzen,
**Vorjahresvergleich** (`vorjahr`), **SOLL-Vergleich** (`soll_pv_*`), Grundlast — dazu
`feld_quellen` (Herkunft je Wert) und `hinweise`.

> ⛔ **Hier stand bis 2026-08-30: „trägt bereits **alles**, was der Bericht zeigen soll."**
> **Am Code widerlegt, und der Bau ist dem Satz gefolgt.** Negativbeweis über
> `api/routes/aktueller_monat.py`: `typisches_tagesprofil` · `peak_netzbezug` ·
> `peak_einspeisung` · `kategorien` → **je 0 Treffer**. Diese Größen liegen in
> `energie_profil/views.py::get_monatsauswertung` (`:873`), die Tagesreihe des *Verlaufs* im
> Service `services/energie_profil/tage_werte.py::baue_tage_werte`. **Sechs der vierzehn
> Anzeigen der Monatsfläche speisen sich also aus zwei anderen Quellen** (fünf aus der
> Monatsauswertung, der Verlauf aus den Tageswerten) — der Bestand hat **eine** Quelle
> vermessen und daraus auf die ganze Fläche geschlossen.
>
> ⚠ *Auch dieser Korrekturabsatz stand zuerst mit „fünf" da — die Gegenlese hat nachgezählt.
> Eine Zahl in einer Korrektur ist genauso eine Behauptung wie die, die sie korrigiert.*
> *Dieselbe Klasse wie die elf/24 Park-Elemente im Kopf: eine Messung über eine Datei ist
> keine Messung über die Fläche — auch dann nicht, wenn sie im abgenommenen Konzept steht.*

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
Die Themenschalter bestimmen also **was für ein Bericht**, der Park-Zustand feilt **innerhalb**.
*(Stand Stufe 1: vier. Mit Stufe 2 kam **Community** als fünfter dazu.)*
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

---

# Stufe 2 — Grafische Aufbereitung + Community (2026-08-30)

> **Status: FREIGEGEBEN, im Bau.** Gernots Auftrag am 30.08., wörtlich: *„Lass das Thema Teilen
> komplett weg und erfülle nur den Benutzerwunsch nach einem Monatsbericht auf Basis der
> Monatsdaten als PDF aber mit grafischer Aufbereitung und inklusive Community."*
>
> ⛔ **„Teilen" ist KEIN Gegenstand dieser Stufe** — und das ist eine Entscheidung, keine
> Vertagung. Ein früherer Entwurf dieses Abschnitts führte eine Teilen-Voreinstellung, einen
> Teilen-Knopf auf *Cockpit → Monat* und daraus abgeleitete Auflagen. **Alles davon ist
> gestrichen.** Der Anlass war Gernots Bemerkung, dass künftig wohl viele Flächen etwas zu teilen
> anbieten werden — ich hatte daraus ein eigenes Vorhaben gemacht, statt beim Melderwunsch zu
> bleiben. *Aus einer Randbemerkung wird kein Arbeitspaket.*
> ⚑ Der **bestehende** Markdown-/Zwischenablage-Weg aus Stufe 1 bleibt unberührt — er ist
> gebaut, abgenommen und funktioniert; ihn zu entfernen war nie gefragt.

## Der Auslöser

Gernot nach dem ersten Test an der Dev-Box, wörtlich: *„Die Berichte sehen überhaupt nicht wie
die Seite Cockpit-Monat aus und enthält keine dort verwendet Aufbereitungen und Charts."*

**Gemessen:** Das Template kennt **genau eine** Darstellungsform — `table.werte`, Label links,
Wert rechts. Alle Abschnitte laufen durch dieselbe Schleife. Die Geschwister im selben
Verzeichnis:

| Template | `<table>` | Charts |
| --- | --- | --- |
| `jahresbericht.html` | 9 | **3** (PV-Erzeugung · Energiefluss · Autarkie, je `<img src="{{ charts.* }}">`) |
| `finanzbericht.html` | 4 | 0 |
| `anlagendokumentation.html` | 0 | 1 (Anlagenfoto) |
| **`monatsbericht.html`** | **1** | **0** |

⇒ Der Bericht ist nicht nur „nicht wie der Bildschirm", er ist **dünner als sein direktes
Geschwister**. Bauschnitt-Zeile 2 der Stufe 1 („Template **im Stil der Cockpit-Monatsansicht**")
ist nicht eingelöst worden — die Zahlen stimmen, die Aufmachung fehlt.

## Was dazukommt — und woher die Daten stammen

**Die Monatsfläche trägt 14 parkbare Anzeigen** (gemessen über die `<Parkbar>`-Aufrufe in
`CockpitMonatV4` · `MonatBilanz` · `MonatAuswertungBloecke` · `MonatRahmen`). Der Bericht deckt
heute sieben ab, und die als Tabelle. **Sechs fehlen ganz — das ist Inhalt, nicht Kosmetik:**
ein Archivstück ohne Tagesverlauf, Tagesprofil und Spitzenstunden ist unvollständig, und
„Ablage" ist der Zweck, den der Melder wörtlich genannt hat.

| Anzeige | heute | Quelle für den Bau |
| --- | --- | --- |
| KPI-Strip (7 Kacheln: PV · Eigenverbrauch · Direktverbrauch · Einspeisung · Netzbezug · Gesamtverbrauch · Autarkie) | – | `AktuellerMonatResponse` (da) |
| `el:bilanz-vergleich` · `-grundlast` · `-monatsprognose` · `-verteilung` · `-geraete` · `el:finanzen-bilanz` | Tabellenzeilen | dieselbe (da) |
| **`el:verlauf`** — Tagesbalken über den Monat | **fehlt** | `services/energie_profil/tage_werte.py::baue_tage_werte(db, anlage, von, bis)` |
| **`el:kategorien-erzeugung`** · **`el:kategorien-verbrauch`** | **fehlen** | `get_monatsauswertung` → `kategorien` |
| **`el:tagesprofil`** — 24-Stunden-Kurve | **fehlt** | `get_monatsauswertung` → `typisches_tagesprofil` |
| **`el:peak-netzbezug`** · **`el:peak-einspeisung`** | **fehlen** | `get_monatsauswertung` → `peak_*` |
| `el:finanzen-link` (Cross-Link) | – | **gehört nicht ins PDF** — ein Link ist auf Papier nichts |
| `el:community-tabelle` | – | s. eigener Abschnitt |

**Aufrufweg, gemessen:**
* `get_monatsauswertung(anlage_id, jahr, monat, top_n, db)` — die Logik liegt **in der Route**,
  es gibt keinen Service darunter. Direkt aufrufbar mit explizit gesetzten Argumenten; dasselbe
  Muster, mit dem der Builder heute schon `get_aktueller_monat(anlage_id, jahr, monat, db)` ruft
  (`monatsbericht.py:542`, Lazy-Import gegen den Zyklus).
* Für den Verlauf **nicht** die Route, sondern den Service `baue_tage_werte` — die Route
  `get_tage_werte` tut nichts weiter, als ihn nach einer Anlagenprüfung aufzurufen (Regel 7).

⇒ **Keine neue Datenschicht** — ADR-002/P10 bleibt gewahrt, der Builder ruft Aufbereitungen und
faltet nichts selbst.

## Die Charts — zwei neue, dasselbe Verfahren

`services/pdf/charts.py` liefert **Inline-SVG als `data:`-URI**, bewusst matplotlib- und
numpy-frei (Kopf-Docstring: numpy 2.x ist mit X86-V2-Baseline gebaut, HA-als-Proxmox-VM mit
`kvm64` reicht den Befehlssatz nicht durch → `RuntimeError`; #303/#121). WeasyPrint rendert SVG
nativ. Die Helfer `_axis_and_grid` · `_legend` · `_wrap` · `_nice_step` sind **generisch**.

⇒ **Zwei neue Aufrufer, kein neues Verfahren:**
1. `tagesverlauf_chart(...)` — Balken je Tag des Monats (Gegenstück zum `pv_erzeugung_chart` des
   Jahresberichts, dort 12 Monate statt ~30 Tage).
2. `tagesprofil_chart(...)` — 24-Stunden-Linie.

**Kategorien und PV-Verteilung brauchen kein Chart** — das sind Balken, also CSS. Dasselbe gilt
für KPI-Kacheln und die Grundlast-/Prognose-Kachel.

### ⚠ Die Regel, die die N-7-Sicherung am Leben hält

Markdown trägt kein SVG. Die Regel dazu lautet in zwei Teilen:

1. **Ein Chart entsteht ausschließlich im Builder aus dem Context — das Template rechnet nichts.**
   Damit kann ein Chart eine Größe gar nicht anders bilden als die Tabelle daneben; genau das ist
   die N-7-Sicherung, eine Ebene höher gezogen.
2. **Jede Zahl, die der Bericht als *Aussage* trifft, steht als Zeile — in beiden Formaten.**
   Ein Chart darf eine **Reihe zeigen**, über die der Bericht keine einzelne Zahl behauptet
   (30 Tageswerte, 24 Stundenwerte); seine Aussagen — bester Tag, schwächster Tag, Ø — stehen als
   Zeilen und werden **aus derselben Liste** gebildet, die auch das Chart zeichnet.

> ⚠ **Hier stand zuerst: „Ein Chart darf ausschließlich Zahlen zeigen, die auch als Tabellenzeile
> stehen."** Die Regel hätte die bestehende Probe
> `test_monatsbericht.py::test_beide_formate_nennen_dieselben_zahlen` gebrochen: Sie vergleicht
> die Zahlen des **gerenderten HTML-Textes** mit denen des Markdown, **der Reihe nach**. Ein
> Chart, das die Tabelle **ersetzt**, hätte die Zahlen aus dem HTML-Text entfernt ⇒ rot; ein Chart
> **neben** einer 30-Zeilen-Tagestabelle hätte beide Formate aufgebläht. *Eine Regel, die ich
> schreibe, ist eine Behauptung über die Proben, die es schon gibt — gelesen, bevor sie gilt.*

### ⚠ Die Farbfrage ist ein Regel-0a-Fall, keine Kosmetik

Zwei Farbwelten, gemessen: `charts.py` führt `_PRIMARY #1565c0` · `_ACCENT #43a047` ·
`_NETZ #e53935`; die Fläche führt `lib/colors.ts::DATENROLLE` (Eigenverbrauch violett,
Einspeisung smaragd, Netzbezug rot). **„Eine Datenrolle = eine Farbe"** ist Regel 0a. ⇒ Die
Datenrollen-Farben werden **einmal** in die PDF-Seite gezogen; die generischen Tokens
(`--color-primary` für Überschriften, das Markenband) bleiben unberührt.

### „Erkennbar eedc"

Gemessen: ein dreifarbiges Markenband in der linken Seitenmarge (`static/styles.css:105`,
`position: fixed` ⇒ WeasyPrint repliziert es auf jeder Seite), Titel, Fußzeile. **Das Logo trägt
bisher nur die Anlagendokumentation** — `builders/anlagendokumentation.py:248` base64-t
`eedc/logo.png` in den Context. ⇒ **Regel 7: das Muster existiert**, der Kopfbereich ruft es auf,
statt es nachzubauen.

## Der Community-Vergleich — und ein Fund, der das Konzept fast falsch gemacht hätte

⛔ **Auf dem Bildschirm gibt es ihn nicht.** `MonatRahmen::communityBlock` hat **null** Aufrufer
im Produktivcode (Gegenprobe: die Schwesterfunktion `finanzTeaserBlock` aus derselben Datei hat
**vier** — der Grep diskriminiert). `el:community-tabelle` wird nie gerendert.

⭐ **Und das ist kein Versehen, sondern Gernots eigener Entscheid.** `git log -S` führt auf
Commit **`748849b2`** („Gernot-Feintuning 1–4"), Punkt 2 wörtlich: *„Community-Block entfernt →
data-gated Cross-Link ‚Community: spez. Ertrag ±x % vs. Median →' zur Community-Achse. Volle
Inhalte dort."* Übrig blieb die Funktion ohne Aufrufer.

**Folge — die Begründung ändert sich, die Entscheidung nicht:**
* Der Community-Abschnitt steht im Bericht, **weil Gernot ihn dort will** (30.08.), nicht weil
  die Monatsansicht ihn hätte. Eine bewusste Abweichung vom Bildschirm, keine Übernahme.
* ⛔ **Der Bildschirm wird nicht angefasst.** Den Block dort wiederzubeleben hieße, `748849b2`
  rückgängig zu machen.
* **Quelle:** `api/routes/community.py::get_monatsbenchmark` (`:341`) — ein **httpx-Aufruf an den
  externen Community-Server**. ⚠ Harte Auflage: **Der Bericht muss ohne ihn vollständig
  rendern.** Server nicht erreichbar oder ohne Daten für den Monat ⇒ der Abschnitt entfällt und
  sagt es (ADR-002/**P4**); **kein** Abschnitt mit Strichen, und kein Fehler, der den ganzen
  Bericht kostet.
* ⛔ **Kein Stand-Datum** — Entscheid Gernot (30.08.): *„der Vergleichsmonat bleibt der gleiche
  und ob es wesentlich ist, wann der Vergleich gezogen wird, ist imo egal."* Er hat recht: Der
  Vergleichsmonat **ist** der Berichtsmonat, damit ist der Vergleich definiert. Mitgenommen wird
  allein die **Anzahl der verglichenen Anlagen** — sie steht schon in der Zusammenfassung des
  (unerreichbaren) Bildschirm-Blocks, und ein Vergleich gegen 3 Anlagen ist etwas anderes als
  gegen 300.
* **Abgrenzung:** Der Bericht zitiert vier Kennzahlen plus die Anlagenzahl. Er wird **keine**
  zweite Fläche zum Erkunden — wer mehr will, folgt dem Cross-Link, den `748849b2` dafür gebaut
  hat.

## Der Bauschnitt (Stufe 2)

| Nr. | Was | Wo |
| --- | --- | --- |
| **1** | Context um `kpis`, `verlauf`, `kategorien`, `tagesprofil`, `peaks`, `community` erweitern — über `get_monatsauswertung` + `baue_tage_werte` + `get_monatsbenchmark`, jede Größe **fertig formatiert** wie bisher | `builders/monatsbericht.py` |
| **2** | Zwei SVG-Funktionen über den bestehenden Helfern | `services/pdf/charts.py` |
| **3** | Template: Kopf mit Logo · KPI-Kachelreihe · Verteilungsbalken · Charts · Peak-Tabellen · Community-Abschnitt; Datenrollen-Farben | `templates/monatsbericht.html` + `static/styles.css` |
| **4** | Markdown-Renderer zieht die neuen Abschnitte als Tabellen mit (kein SVG) | `builders/monatsbericht_markdown.py` |
| **5** | Fünfter Themenschalter **Community** (Voreinstellung **an**) **+ Wächter für den THEMEN-Spiegel** | `routes/dokumentation.py` · `DokumentationsDialog.tsx` |
| **6** | Handbuch + Hilfe-Spiegel | `docs/HANDBUCH_EINSTELLUNGEN.md`, `sync-help.sh` |

⚠ **Zu Nr. 5 — `THEMEN` steht zweimal und ist ungedeckt.** Backend `builders/monatsbericht.py:68`
und Client `DokumentationsDialog.tsx:44` führen dieselbe Liste, verbunden nur durch einen
Kommentar („Spiegel von …"). Kein Test, und keiner der 27 `check:*` deckt einen
Backend↔Frontend-Spiegel (`check-label-maps` guckt nur auf Frontend-interne SoT-Maps). Folge bei
Drift: ein Schalter, der still nichts tut, oder ein Thema, das niemand wählen kann. **Wer eine
doppelt geführte Liste erweitert, hinterlässt sie nicht wieder unbewacht.**

⛔ **N-356 fährt NICHT mit.** Sein Trigger (*„der nächste Eingriff am Monatsbericht-Builder"*)
tritt mit Nr. 1 ein und wird im Register vermerkt — gebaut wird er nicht: Er ist ein SoT-Bau über
zwei Bildungsstellen mit einer bewusst zweiten Quote (N-69/dietmar1968); in ein
Aufmachungs-Paket gefaltet, würden aus zwei überschaubaren Änderungen eine unübersichtliche.

## Proben, die diese Stufe tragen

1. **Jede Chart-Zahl steht auch als Tabellenzeile** — die N-7-Sicherung für die neue Ebene.
2. **Community-Server nicht erreichbar ⇒ Bericht vollständig, Abschnitt entfällt mit Grund**,
   und **kein** anderer Wert ändert sich (P4).
3. **Community-Abschnitt trägt die Anlagenzahl**, sobald er da ist.
4. **Ohne den Themenschalter Community ist er in KEINEM der beiden Formate** (Stufe-1-Probe 2,
   auf den neuen Schalter gezogen).
5. **Die bestehenden Proben bleiben unverändert grün** — insbesondere „beide Formate, jede Zahl
   gleich" und „ein Monat ohne Daten nennt den Grund".
6. **Gegenrichtung:** Ein Monat **mit** Daten, aber ohne Stundenwerte (kein Tagesprofil, keine
   Peaks) lässt genau diese Abschnitte weg und rechnet die übrigen unverändert.
7. **Der THEMEN-Spiegel ist gewächtert** — eine Abweichung zwischen Backend und Client meldet rot.


## Was der Dialog-Durchgang zurückgenommen hat (Gernot, 30.08., nach dem Sichttest)

Sein Befund am fertigen Dialog: *„Das gefällt mir gar nicht mehr."* Fünf Punkte, dazu ein
sechster, den die Messung gefunden hat:

| Punkt | Entscheid |
| --- | --- |
| **Beta-Kennzeichnung** | weg — und die Feedback-Links mit: **Issue #121 ist CLOSED**, sie führten ins Leere |
| **Download-Symbol verdeckt** | Das ZIP-Kästchen lag `absolute top-2 right-2` **auf** dem Symbol. Gelöst durch einen **Modus** („Mehrere als ZIP"), nicht durch Verschieben: beide teilen sich die Ecke nie, weil es sie nie gleichzeitig gibt |
| **Monatsbericht-Optionen nicht zuordenbar** | Sie standen in einem Kasten **unter** allen Karten. ⇒ **Optionen stehen in der Karte des Dokuments** |
| ⭐ **Und derselbe Fehler am anderen Ende** (nicht gemeldet, gemessen) | Der **Jahresbericht-Zeitraum** stand in einem Kasten **über** allen Karten — dieselbe Fehlzuordnung, gespiegelt. Mit derselben Regel gelöst |
| **Identitäts-Schalter** | weg. Seine Begründung war der Forumspost („wer teilt, schaltet ab"); mit dem Entscheid gegen das Thema *Teilen* ist sie entfallen. Anlagenname und Standort stehen jetzt **immer** im Bericht |
| **Markdown-Knöpfe** | weg — **und der ganze Markdown-Weg**: Renderer, `?format=md`, Dateiname-Zweig. Sein Zweck war das Posten; ohne Knöpfe wäre er ohne Aufrufer weitergelaufen (die `communityBlock`-Lage). ⭐ **Mit einem Renderer gibt es die zweite Bildungsstelle nicht mehr, gegen die der Bericht gebaut war (N-7)** — das ist stärker als die Probe, die sie bewachte |

### ⚑ Was mit dem Markdown-Weg NICHT verschwunden ist

**Die Löschung hat eine Bilanz, keinen Sprengsatz:** `test_monatsbericht.py` trug **18 Proben
vorher und 18 nachher**. Keine ist gestrichen — jede „beide Formate"-Probe ist auf ihre
**Aussage** umgestellt worden:

* `test_beide_formate_nennen_dieselben_zahlen` → **`test_das_template_schreibt_die_werte_unveraendert`**.
  Der Renderer darf eine Zahl auf dem Weg nicht anfassen; das gilt für einen genauso wie für zwei.
* `test_ohne_identitaet_stehen_name_und_standort_nirgends` → **umgedreht** zu
  `test_der_bericht_nennt_immer_anlage_und_standort`. Ohne sie könnte der Kopf die Angaben
  verlieren, ohne dass ein Lauf rot wird.
* Die übrigen vergleichen jetzt das gerenderte Dokument statt zweier Ausgaben.

⚠ **Eine dieser Umstellungen ist im ersten Anlauf misslungen:** Die Zusicherung, dass die
Aufmachung keine Zahl hinzufügt, verglich die Zahlen des Dokuments **mit den Zahlen des
Dokuments** — sie konnte per Konstruktion nicht rot werden. Sie liest jetzt die
**Leisten-Legende** und verlangt, dass dort keine Ziffer steht (der konkrete Fehler des ersten
Entwurfs). *Eine Probe, die man beim Umstellen nicht sprengt, ist keine Probe.*
