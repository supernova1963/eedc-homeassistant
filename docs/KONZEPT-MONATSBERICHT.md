# Konzept — Monatsbericht (#395 Punkt 4, OB73-gif)

> **Status: Stufe 1 GEBAUT (2026-08-30) · Stufe 2 ENTWURF.** Stufe 1 abgenommen von Gernot am
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

---

# Stufe 2 — Der Bericht sieht aus wie eedc (Entwurf, 2026-08-30)

> **Status: ENTWURF.** Richtung freigegeben von Gernot am 30.08. (*„nein, gerne auch ein
> Dokument, versuchen wir es"*). Der **Bau** wartet auf die Freigabe dieses Abschnitts.

## Der Auslöser

Gernot nach dem ersten Test an der Dev-Box, wörtlich: *„Die Berichte sehen überhaupt nicht wie
die Seite Cockpit-Monat aus und enthält keine dort verwendet Aufbereitungen und Charts."*

**Gemessen, nicht angenommen:** Das Template kennt **genau eine** Darstellungsform —
`table.werte`, Label links, Wert rechts. Alle Abschnitte laufen durch dieselbe Schleife.
Zum Vergleich die Geschwister im selben Verzeichnis:

| Template | `<table>` | Charts |
| --- | --- | --- |
| `jahresbericht.html` | 9 | **3** (PV-Erzeugung · Energiefluss · Autarkie, je `<img src="{{ charts.* }}">`) |
| `finanzbericht.html` | 4 | 0 |
| `anlagendokumentation.html` | 0 | 1 (Anlagenfoto) |
| **`monatsbericht.html`** | **1** | **0** |

⇒ Der Bericht ist nicht nur „nicht wie der Bildschirm", er ist auch **dünner als sein direktes
Geschwister**. Bauschnitt-Zeile 2 der Stufe 1 („Template **im Stil der Cockpit-Monatsansicht**")
ist nicht eingelöst worden — die Zahlen stimmen, die Aufmachung fehlt.

## Die Entscheidung: EIN Dokument, zwei Voreinstellungen

⛔ **Kein zweites Dokument, kein drittes Renderziel.** Der zuerst erwogene Schnitt (Archiv-PDF
*und* separates Teilen-Blatt) ist verworfen — Begründung in dieser Reihenfolge:

1. **Es ist die stärkste Form von „nicht umsonst".** Der gebaute Bericht wird nicht daneben
   stehengelassen, er **wird** das Teilen-Artefakt.
2. **Das N-7-Risiko fällt strukturell auf null.** Bei zwei Dokumenten müsste eine Regel samt
   Probe verhindern, dass das zweite eigene Zahlen bildet — genau daran ist die
   Social-Media-Vorlage gestorben (§1). Bei einem Dokument gibt es die zweite Bildungsstelle
   nicht, die man bewachen müsste.
3. **Es gibt dann genau einen eedc-Monatsbericht**, in zwei Längen — wiedererkennbarer als zwei
   verschieden aussehende Dokumente über denselben Monat.

| | **Archiv** (Voreinstellung) | **Teilen** |
| --- | --- | --- |
| Umfang | alle Abschnitte | kurze Auswahl |
| Community-Vergleich | aus | **an**, mit Stand-Datum und Vergleichsgröße |
| Identität | an | Wahl des Anwenders |
| Aufmachung | KPI-Kacheln · Balken · Charts | dieselben |
| Einstieg | Berichts-Hub an der Anlage | **Schaltfläche auf *Cockpit → Monat*** |

⚑ **Der zweite Einstieg ist keine Bequemlichkeit, er ist die Lehre aus dem Rückbau.** Commit
`07682e14` nennt als Grund für den Wegfall der Social-Vorlage wörtlich: *„Teilen-Symbol und
`ShareTextModal` gibt es in v4 nicht mehr, `GET /api/cockpit/share-text/{id}` lief seither ohne
Konsumenten weiter."* **Unerreichbarkeit war der Rückbaugrund, nicht das Teilen** — derselbe
Commit hält ausdrücklich fest: *„Nicht betroffen: das Community-Teilen — eine andere Funktion,
die bleibt."* Ein Teilen-Weg, der nur im Dokumenten-Hub liegt, baut die Sackgasse nach.

### Was „erkennbar eedc" heute trägt — und was fehlt

Gemessen: ein dreifarbiges Markenband in der linken Seitenmarge (`static/styles.css:105`,
`position: fixed` ⇒ WeasyPrint repliziert es auf jeder Seite), der Titel und die Fußzeile.
**Das Logo trägt bisher nur die Anlagendokumentation** — `builders/anlagendokumentation.py:248`
base64-t `eedc/logo.png` in den Context. ⇒ **Regel 7: das Muster existiert**, der Kopfbereich
des Monatsberichts ruft es auf, statt es nachzubauen.

⛔ **Kein Bild-Export, und das ist eine Entscheidung.** Gemessen: WeasyPrint **68.1** hat kein
`write_png` (seit 53 entfernt); im Backend-venv fehlen `cairosvg` und `playwright` (`PIL` ist da,
rendert aber kein HTML); das Frontend hat 12 Abhängigkeiten, keine davon rastert. Ein Bild
kostete also eine neue Laufzeit-Abhängigkeit. **Gernots Entscheid (30.08.):** Snapshots als PNG
sind mit Bordmitteln des Anwenders ohnehin möglich und decken den gezielten Fall ab (ein
einzelnes Diagramm in einen Markdown-Post heben, weil Markdown kein SVG trägt). **Das Artefakt
ist der Bericht, nicht das Bild.** ⚠ *Hier lag mein eigener Denkfehler: Ich hatte „das Bild" zum
Ziel erklärt und den Bericht daran gemessen, ob man ihn postet. Der Maßstab ist
Wiedererkennbarkeit — und die leistet ein gebrandeter Bericht, während ein nackter Screenshot
einer Webseite sie gerade nicht leistet.*

## Was dazukommt — und woher die Daten stammen

**Die Monatsfläche trägt 14 parkbare Anzeigen** (gemessen über die `<Parkbar>`-Aufrufe in
`CockpitMonatV4` · `MonatBilanz` · `MonatAuswertungBloecke` · `MonatRahmen`). Der Bericht deckt
davon heute sieben ab, und die als Tabelle.

| Anzeige | heute im Bericht | Quelle für den Bau |
| --- | --- | --- |
| KPI-Strip (7 Kacheln: PV · Eigenverbrauch · Direktverbrauch · Einspeisung · Netzbezug · Gesamtverbrauch · Autarkie) | – | `AktuellerMonatResponse` (da) |
| `el:bilanz-vergleich` · `-grundlast` · `-monatsprognose` · `-verteilung` · `-geraete` · `el:finanzen-bilanz` | als Tabellenzeilen | dieselbe (da) |
| **`el:verlauf`** — Tagesbalken über den Monat | **fehlt** | `services/energie_profil/tage_werte.py::baue_tage_werte(db, anlage, von, bis)` |
| **`el:kategorien-erzeugung`** · **`el:kategorien-verbrauch`** | **fehlen** | `get_monatsauswertung` → `kategorien` |
| **`el:tagesprofil`** — 24-Stunden-Kurve | **fehlt** | `get_monatsauswertung` → `typisches_tagesprofil` |
| **`el:peak-netzbezug`** · **`el:peak-einspeisung`** | **fehlen** | `get_monatsauswertung` → `peak_*` |
| `el:finanzen-link` (Cross-Link) | – | **gehört nicht ins PDF** — ein Link ist auf Papier nichts |
| `el:community-tabelle` | – | s. eigener Abschnitt unten |

**Aufrufweg, gemessen:**
* `get_monatsauswertung(anlage_id, jahr, monat, top_n, db)` — die Logik liegt **in der Route**,
  es gibt keinen Service darunter. Direkt aufrufbar mit explizit gesetzten Argumenten; das ist
  dasselbe Muster, mit dem der Builder heute schon `get_aktueller_monat(anlage_id, jahr, monat,
  db)` ruft (`monatsbericht.py:542`, Lazy-Import gegen den Zyklus).
* Für den Verlauf **nicht** die Route, sondern den Service `baue_tage_werte` — die Route
  `get_tage_werte` tut nichts weiter, als ihn nach einer Anlagenprüfung aufzurufen (Regel 7).

⇒ **Weiterhin keine neue Datenschicht** — ADR-002/P10 bleibt gewahrt, der Builder ruft
Aufbereitungen und faltet nichts selbst.

## Die Charts — zwei neue, dasselbe Verfahren

`services/pdf/charts.py` liefert **Inline-SVG als `data:`-URI**, bewusst matplotlib- und
numpy-frei (Kopf-Docstring: numpy 2.x ist mit X86-V2-Baseline gebaut, HA-als-Proxmox-VM mit
`kvm64` reicht den Befehlssatz nicht durch → `RuntimeError`; #303/#121). WeasyPrint rendert SVG
nativ. Die Helfer `_axis_and_grid` · `_legend` · `_wrap` · `_nice_step` sind **generisch**.

⇒ **Zwei neue Aufrufer, kein neues Verfahren:**
1. `tagesverlauf_chart(tage)` — Balken je Tag des Monats (Gegenstück zum `pv_erzeugung_chart`
   des Jahresberichts, dort 12 Monate statt ~30 Tage).
2. `tagesprofil_chart(stunden)` — 24-Stunden-Linie.

**Kategorien und PV-Verteilung brauchen kein Chart** — das sind Balken, also CSS. Dasselbe gilt
für KPI-Kacheln und die Grundlast-/Prognose-Kachel.

### ⚠ Die Regel, die die N-7-Sicherung am Leben hält

Markdown trägt kein SVG. ⇒ **Ein Chart darf ausschließlich Zahlen zeigen, die im selben Bericht
auch als Tabellenzeile stehen.** Dann ist das PDF die reichere Darstellung derselben Zahlen, die
Probe „beide Formate, jede Zahl gleich" (Stufe 1, §1) bleibt **wahr statt zur Ausnahme zu
werden**, und der Markdown-Text bleibt vollständig. Ein Chart, das eine eigene Größe einführt,
ist N-7 in Grün.

### ⚠ Die Farbfrage ist ein Regel-0a-Fall, keine Kosmetik

Zwei Farbwelten, gemessen: `charts.py` führt `_PRIMARY #1565c0` · `_ACCENT #43a047` ·
`_NETZ #e53935`; die Fläche führt `lib/colors.ts::DATENROLLE` (Eigenverbrauch violett,
Einspeisung smaragd, Netzbezug rot). **„Eine Datenrolle = eine Farbe"** ist Regel 0a. Solange
beide Welten nebeneinander stehen, ist der Bericht auch farblich ein anderes Produkt als der
Bildschirm. ⇒ Die Datenrollen-Farben werden **einmal** in die PDF-Seite gezogen; die generischen
Tokens (`--color-primary` für Überschriften, das Markenband) bleiben unberührt.

## Der Community-Vergleich — und ein Fund, der das Konzept fast falsch gemacht hätte

Gernots Vorgabe (30.08.): *„Ich würde ihn zumindest für die Teilen-Funktion drin lassen auch wenn
später aktuellere Monatsvergleiche dabei raus kommen."*

⛔ **„Drin lassen" trifft den Zustand nicht — auf dem Bildschirm gibt es ihn nicht.**
`MonatRahmen::communityBlock` hat **null** Aufrufer im Produktivcode (Gegenprobe: die
Schwesterfunktion `finanzTeaserBlock` aus derselben Datei hat **vier** — der Grep
diskriminiert). `el:community-tabelle` wird damit **nie gerendert**.

⭐ **Und das ist kein Versehen, sondern Gernots eigener Entscheid.** `git log -S` führt auf
Commit **`748849b2`** („Gernot-Feintuning 1–4"), Punkt 2 wörtlich: *„Community-Block entfernt →
data-gated Cross-Link ‚Community: spez. Ertrag ±x % vs. Median →' zur Community-Achse. Volle
Inhalte dort."* Übrig blieb die Funktion ohne Aufrufer.

**Folge für dieses Konzept — die Begründung ändert sich, die Entscheidung nicht:**
* Der Community-Abschnitt kann **nicht** mit „im Stil der Monatsansicht" begründet werden. Er
  steht im Bericht, **weil Teilen ohne Vergleich seinen Zweck verfehlt** — und das ist eine
  bewusste Abweichung vom Bildschirm, keine Übernahme.
* ⛔ **Der Bildschirm wird nicht angefasst.** Den Block dort wiederzubeleben hieße, `748849b2`
  rückgängig zu machen.
* **Quelle:** `api/routes/community.py::get_monatsbenchmark` (`:341`) — ein **httpx-Aufruf an den
  externen Community-Server**. ⚠ Daraus folgt eine harte Auflage: **Der Bericht muss ohne ihn
  vollständig rendern.** Server nicht erreichbar oder ohne Daten für den Monat ⇒ der Abschnitt
  entfällt und sagt es (ADR-002/**P4**: unvollständige Antworten weisen sich aus); **kein**
  Abschnitt mit Strichen, und kein Fehler, der den ganzen Bericht kostet.
* **Stand-Datum und Vergleichsgröße gehören in den Abschnitt** („Stand 30.08.2026 · Vergleich
  gegen N Anlagen"). Ein geteiltes Blatt lebt im Forenthread weiter; ohne die Zeile steht dort
  in zwei Jahren ein Vergleich, den niemand zuordnen kann. Dass später aktuellere Vergleiche
  herauskommen, ist das Argument **für** die Zeile, nicht dagegen.

## Der Bauschnitt (Stufe 2)

| Nr. | Was | Wo |
| --- | --- | --- |
| **1** | Context um `kpis`, `verlauf`, `kategorien`, `tagesprofil`, `peaks`, `community` erweitern — über `get_monatsauswertung` + `baue_tage_werte` + `get_monatsbenchmark`, jede Größe **fertig formatiert** wie bisher | `builders/monatsbericht.py` |
| **2** | Zwei SVG-Funktionen über den bestehenden Helfern | `services/pdf/charts.py` |
| **3** | Template: Kopf mit Logo · KPI-Kachelreihe · Verteilungsbalken · Charts · Peak-Tabellen · Community-Abschnitt; Datenrollen-Farben | `templates/monatsbericht.html` + `static/styles.css` |
| **4** | Markdown-Renderer zieht die neuen Abschnitte als Tabellen mit (kein SVG) | `builders/monatsbericht_markdown.py` |
| **5** | Fünfter Themenschalter **Community** (Voreinstellung **aus**) + Voreinstellung „Teilen" | `routes/dokumentation.py` · `DokumentationsDialog.tsx` |
| **6** | Schaltfläche **Teilen** auf *Cockpit → Monat*, öffnet den Dialog mit der Teilen-Voreinstellung | `v4/CockpitMonatV4.tsx` |
| **7** | Handbuch + Hilfe-Spiegel | `docs/HANDBUCH_EINSTELLUNGEN.md`, `sync-help.sh` |

## Proben, die diese Stufe tragen

1. **Jede Chart-Zahl steht auch als Tabellenzeile** — die N-7-Sicherung für die neue Ebene.
2. **Community-Server nicht erreichbar ⇒ Bericht vollständig, Abschnitt entfällt mit Grund**,
   und **kein** anderer Wert ändert sich (P4).
3. **Community-Abschnitt trägt Stand-Datum und Anlagenzahl**, sobald er da ist.
4. **Teilen-Voreinstellung ≠ Archiv-Voreinstellung** — messbar am erzeugten Abschnittssatz.
5. **Ohne Themenschalter Community ist er in KEINEM der beiden Formate** (Regel aus Stufe 1,
   Probe 2, auf den neuen Schalter gezogen).
6. **Die bestehenden Proben bleiben unverändert grün** — insbesondere „beide Formate, jede Zahl
   gleich" und „ein Monat ohne Daten nennt den Grund".
7. **Gegenrichtung:** Ein Monat **mit** Daten, aber ohne Stundenwerte (kein Tagesprofil, keine
   Peaks) lässt genau diese Abschnitte weg und rechnet die übrigen unverändert.

## Offene Entscheidungen — sie gehören Gernot

1. **N-356 ist mit diesem Paket fällig geworden.** Sein Trigger lautet *„der nächste Eingriff an
   `lib/sollErfuellung.ts`, an `baueMonatKpis` oder am Monatsbericht-Builder"* — Nr. 1 des
   Bauschnitts trifft ihn. Er steht in **P6** („gerät hinten an"). **Empfehlung: nicht
   mitfahren.** Er ist ein SoT-Bau über zwei Bildungsstellen mit einer bekannten zweiten Quote
   (N-69/dietmar1968); ihn in ein Aufmachungs-Paket zu falten, macht aus zwei überschaubaren
   Änderungen eine unübersichtliche. Der Trigger wird im Register als *eingetreten* vermerkt.
2. **Umfang der Teilen-Voreinstellung** — welche Abschnitte sind „die kurze Auswahl"?
   **Empfehlung:** KPI-Kacheln · Verlauf · PV-Verteilung · Community · Finanzen-Kopfzahl.
   Alles Weitere bleibt dem Archiv.

## Gegenlese — was der Entwurf gegen sich selbst nicht halten konnte

| Geprüft | Ergebnis |
| --- | --- |
| Melder-Wortlaut #395 (*„Hintergrund ist die **Ablage**"*) | **hält ein** — der Bericht bleibt zuerst ein Archivstück; „Teilen" ist die zweite Voreinstellung, nicht der neue Zweck |
| Commit `07682e14` (Rückbau Social-Vorlage) + **N-7** | **angewandt** — Rückbaugrund war *Unerreichbarkeit*, daher der zweite Einstieg auf *Cockpit → Monat*; die eigene Zahlenbildung bleibt ausgeschlossen, jetzt auch für Charts |
| Commit **`748849b2`** (Gernot-Feintuning, Community-Block entfernt) | ⭐ **weicht ab von der ersten Fassung dieses Entwurfs** — sie wollte den bestehenden Block „wiederverwenden". Er ist **bewusst entfernt**; der Bericht führt den Vergleich aus dem *Teilen*-Zweck, nicht aus „im Stil der Monatsansicht", und der Bildschirm bleibt unberührt |
| ADR-002/**P4** | **angewandt** — der Community-Abschnitt hängt an einem externen Server; fällt er aus, entfällt der Abschnitt mit Grund, der Rest bleibt vollständig |
| ADR-002/**P10** | **hält ein** — der Builder ruft Aufbereitungen (`get_aktueller_monat` · `get_monatsauswertung` · `baue_tage_werte`), er faltet nichts selbst |
| Regel 7 (erst suchen, dann bauen) | **angewandt, dreimal** — Logo-Muster (`anlagendokumentation.py:248`), Chart-Helfer (`_axis_and_grid`/`_legend`/`_wrap`), Service statt Route (`baue_tage_werte` statt `get_tage_werte`) |
| Regel 0a (eine Datenrolle = eine Farbe) | **weicht ab** — zwei Farbwelten (`charts.py::_PRIMARY/_ACCENT/_NETZ` gegen `lib/colors.ts::DATENROLLE`); die Zusammenführung ist Teil des Bauschnitts, nicht Kosmetik |
| `scripts/sync-help.sh` (13 Einträge) · `website/scripts/sync-docs.sh` (16 Einträge) | **hält ein** — `KONZEPT-*` steht in **keiner** der beiden Listen, das Dokument bleibt intern |
| Eigene Zahl „fünf Anzeigen aus fremden Quellen" | ⛔ **an der Gegenlese gescheitert — es sind sechs.** Berichtigt samt Vermerk |
| **THEMEN-Spiegel Backend ↔ Client** | ⛔ **ungedeckt** — `builders/monatsbericht.py:68` und `DokumentationsDialog.tsx:44` führen dieselbe Liste zweimal, verbunden nur durch einen Kommentar („Spiegel von …"). Kein Test, kein `check:*` (die 27 Prüfer decken nur Frontend-interne SoT-Maps). **Stufe 2 fügt den fünften Schalter hinzu und zieht den Wächter mit** — wer eine Liste erweitert, die zweimal steht, hinterlässt sie nicht wieder unbewacht |
| Zweiter Turm über der Community-Achse? | **abgegrenzt** — der Bericht zitiert vier Kennzahlen plus Stand-Datum; er wird **keine** zweite Fläche zum Erkunden. Wer mehr will, folgt dem Cross-Link, den `748849b2` genau dafür gebaut hat |
