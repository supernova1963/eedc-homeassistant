# Was ist neu

> **Stand:** August 2026 (v4.0.12)
> **Diese Seite** zeigt pro Version, was sich für dich als Anwender geändert hat — kürzer als der technische [CHANGELOG](https://github.com/supernova1963/eedc-homeassistant/blob/main/CHANGELOG.md), ausführlicher als die Schnellübersicht-Tabelle in der [Übersicht](BENUTZERHANDBUCH.md#was-ist-neu-seit-v316).
>
> **Kein Banner, kein Pop-up:** eedc zeigt diese Liste nicht ungefragt an. HA-App-Nutzer sehen den Changelog ohnehin schon im Add-on-Store, GitHub-Releases haben einen eigenen. Wer wissen will, was neu ist, schaut hier rein — Pull statt Push.
>
> **Lesehinweis:** Die jüngsten Versionen stehen oben. Jeder Punkt verlinkt entweder auf die zuständige Hilfe-Sektion oder direkt auf die App-Funktion (sofern erreichbar). Anker-URLs (`?doc=was-ist-neu`) sind teilbar.

---

## In Arbeit (noch nicht veröffentlicht)

### „Wie viel billiger als der Schnitt?" — jetzt auch in Cent

**Betrifft dich das?** Wenn du einen dynamischen Stromtarif hast und mit den Börsenpreis-Sensoren Automationen baust.

eedc sagt dir bisher in **Prozent**, wie weit der aktuelle Börsenpreis vom Tagesmittel entfernt ist. Diese Zahl ist tückisch, sobald du sie auf deinen **echten** Preis überträgst: Du zahlst ja nicht den Börsenpreis, sondern Börsenpreis plus feste Bestandteile — Netzentgelt, Abgaben, Marge deines Anbieters. Dieser Aufschlag verschiebt den Stundenpreis und das Tagesmittel um denselben Betrag. Der **Abstand in Cent bleibt damit gleich, der Prozentwert nicht.**

An einem echten Tag: Die billigste Stunde lag **9,93 ct unter dem Tagesmittel** — auf der Börsenkurve genauso wie auf dem Endpreis. In Prozent sind das einmal −100 %, einmal −33 %. Eine Prozentzahl, die für beides dasselbe bedeutet, kann es nicht geben.

Deshalb gibt es jetzt den Sensor **„Börsenpreis-Abstand zum Ø (ct)"** (`sensor.eedc_preis_abstand_cent`). Damit lassen sich Regeln formulieren, die zu deinem Tarif passen: „lade den Akku, solange der Strom mindestens 5 ct unter dem Schnitt liegt", oder schlicht „unter dem Schnitt" (Wert kleiner 0). Im Attribut `rang_profil` des Rang-Sensors steht der Abstand zusätzlich **für jede Stunde des Tages** — du kannst deine eigene Grenze also über den ganzen Tag auswerten. In *Cockpit → Live* steht der Wert als vierte Kachel bei den Börsenpreisen.

**Dein bestehender Prozent-Sensor ändert sich nicht** — laufende Automationen bleiben, wie sie sind. Der neue Wert kommt daneben.

### Die fünf günstigsten Stunden stehen jetzt im Diagramm

**Betrifft dich das?** Wenn du den Börsenpreis-Block in *Cockpit → Live* nutzt.

Bisher zeigte die Kurve grün, welche Stunden unter deiner Günstig-Schwelle liegen — an einem billigen Tag können das auch zehn sein. Jetzt tragen die günstigsten Stunden zusätzlich die Ziffern **1 bis 5**, jeweils getrennt für Tag und Nacht. Es ist derselbe Rang, den der Sensor `eedc_preis_rang` in Home Assistant meldet.

**Die grüne Fläche bleibt, wie sie war.** Sie beantwortet eine andere Frage: „liegt diese Stunde unter der Schwelle?" — und diese Zahl wird in Automationen als Teiler gebraucht, sie darf deshalb nicht bei fünf abgeschnitten werden. Zwei Fragen, zwei Antworten, ein Diagramm.

### Eine Speicher-Kapazität in Wh fällt jetzt auf

**Betrifft dich das?** Wenn du ein Balkonkraftwerk mit Akku hast und den Speicher als eigene Komponente führst.

Das Balkonkraftwerk fragt die Kapazität seines Akkus in **Wh** ab — so steht sie auf dem Gerät und in der Hersteller-App (z. B. 5.376 Wh). Die Speicher-Komponente daneben fragt in **kWh**. Wer den Zahlenwert einfach überträgt, hat einen Speicher, der tausendmal größer ist als in Wirklichkeit — und merkt es nicht: Vollzyklen, Auslastung und Wirtschaftlichkeit rechnen dann gegen eine Kapazität, die es nicht gibt.

Der [Daten-Checker](HANDBUCH_DATEN_CHECKER.md#433-speicher) meldet das jetzt und nennt die Zahl, die richtig wäre. Er meckert dabei **keine großen Speicher an**: Gemeldet wird nur der Widerspruch, dass zwei Felder desselben Geräts denselben Zahlenwert in zwei verschiedenen Einheiten tragen.

### Ein ersetzter Speicher zählt nicht mehr doppelt

**Betrifft dich das?** Wenn du deinen Speicher getauscht oder erweitert und dabei die alte Komponente stillgelegt hast.

eedc führte die Kapazität deiner Anlage dann als **Summe aus altem und neuem Gerät** — an einem echten Bestand 46,2 statt 30,8 kWh. Betroffen waren *Cockpit → Monat*, der Jahresbericht und der anonyme Community-Vergleich. Gerade dort war es teuer: Deine Anlage stand in einer Größenklasse, die es nie gab.

Gezählt wird jetzt der Speicher, den du zum jeweiligen Zeitpunkt wirklich hattest. Wenn du deine Daten mit der Community teilst, kommt die Korrektur beim nächsten vollständigen Übertragen an.

### Docker mit HA-Token: die Tageswerte kommen jetzt an

**Betrifft dich das?** Wenn du eedc als eigenen Docker-Container betreibst und Home Assistant über einen **langlebigen Zugriffstoken** angebunden hast (nicht als HA-Add-on, nicht über MQTT).

In *Cockpit → Tag* stand bei dir dauerhaft „—" mit der Quelle „Prognose", während die Live-Ansicht normal lief und ein von Hand nachgezogener Tag vollständig war. Das war kein Konfigurationsfehler: eedc kannte für den Tagesverlauf nur zwei Fälle — „HA-Add-on" oder „MQTT". Deine Konstellation ist die dritte, und sie landete beim MQTT-Weg, wo nichts ankam. Damit brach die Tagesaggregation ab, bevor sie deine Zählerstände überhaupt gelesen hat.

Jetzt entscheidet die **Zuordnung** darüber, woher die Werte kommen, nicht die Betriebsart: Wo HA-Sensoren zugeordnet und erreichbar sind, liest eedc aus Home Assistant. Wer MQTT nutzt, behält den MQTT-Weg — und wenn der HA-Weg einmal leer bleibt, springt MQTT weiterhin ein.

Dieselbe Ursache hat dir außerdem den **Speicher-Ladestand** (und damit die Vollzyklen), die **Tages-Spitzenwerte** und deinen eigenen **Strompreis-Sensor** vorenthalten — auch das läuft jetzt.

⚠ **Zurückliegende Tage füllen sich nicht von selbst.** Die holst du über den [Daten-Checker](HANDBUCH_DATEN_CHECKER.md) mit „Zeitraum neu aggregieren" — bis zu 31 Tage je Lauf.

### Community: das Performance-Profil zeigt wieder den aktuellen Monat

**Betrifft dich das?** Wenn du deine Daten mit der Community teilst und dort das Radar-Diagramm „Performance-Profil" ansiehst.

Autarkie und Eigenverbrauch standen dort auf den Werten deines **allerersten** geteilten Monats. War das ein Wintermonat, zeigte das Radar knapp 5 %, während dein Cockpit für denselben Zeitraum 100 % meldete — verständlicherweise verwirrend. Dieselbe Verwechslung traf die Auszeichnungen „Autarkiemeister" und „Dauerbrenner".

Jetzt steht dort der jüngste Monat, den du geteilt hast. Die Ansichten *PV-Ertrag* und *Trends* waren nie betroffen.

### Kleinigkeit: die Prognose-Tabelle steht wieder gerade

In *Auswertungen → Prognose* standen die Zahlen der Spalte „PVGIS Prognose" und die Gesamt-Zeile nicht unter ihren Überschriften. Im großen Fenster lief die Tabelle dadurch sichtbar auseinander. Danke fürs Melden.

---

## v4.0.12 — Nutzerwünsche und notwendige Korrekturen (August 2026)

### Der Speicher-Wirkungsgrad steht jetzt da, wo bisher „—" stand

**Betrifft dich das?** Alle mit einem Speicher — besonders, wenn dir leere Monate oder ein Wert über 100 % aufgefallen sind.

Der Wirkungsgrad eines Monats ist nicht einfach „Entladung ÷ Ladung". Was am Monatsende im Akku steht, wird erst im nächsten Monat entladen — über die Monatsgrenze verrutscht also Energie. Ein Monat kann dadurch scheinbar über 100 % kommen, ein anderer zu niedrig aussehen.

eedc hat das erkannt, aber die falsche Konsequenz gezogen: Bei größeren Sprüngen des Ladestands erschien **„—"**, sonst der ungenaue Rohwert. **Ausgerechnet wurde es nie**, obwohl eedc den Ladestand kennt und herausrechnen kann.

Das ist jetzt anders — an unserer Demo-Anlage nachgerechnet:

- Der November 2025 zeigte „—". Richtig sind **81,6 %**.
- Der Oktober zeigte 83,1 %. Richtig sind **82,4 %**.
- Über 27 Monate steht jetzt in **jedem** eine Zahl.

**Was du siehst:** Unter der Kachel steht künftig, worauf der Wert beruht. „Ladestand am Rand herausgerechnet" ist der Normalfall. Zeichnet deine Anlage keinen Ladestand auf, steht der einfache Wert da — aber ehrlich beschriftet mit **„ohne Ladestand gerechnet — ungenau"**. Und wo wirklich keine sinnvolle Zahl möglich ist, steht der Grund dabei statt nur ein Strich.

In *Cockpit → Jahr* verschwindet die Warnung ganz: Über ein volles Jahr gleicht sich der Übertrag aus. Bisher stand sie dort sogar **neben einer Zahl**, sobald ein einziger Monat betroffen war.

**Neu im Daten-Checker:** Gibt dein Speicher über die gesamte Historie mehr ab, als er aufgenommen hat, sagt eedc das jetzt — das kann physikalisch nicht sein und deutet auf einen Erfassungsfehler. **Der häufigste:** Ins Feld **„Ladung" gehört die Gesamtladung inklusive Netz.** Die Netzladung ist ein *Teil* davon, kein zweiter Posten daneben. Passend dazu heißt die Zeile in der Monatsansicht jetzt **„davon aus dem Netz"** — vorher standen dort zwei Zeilen, die man versehentlich addieren konnte.

*(Gefunden dank rapahl, der es zum zweiten Mal gemeldet hat. Beim ersten Mal wurde die Lösung gebaut — sie erreichte die Ansicht nur nie.)*

### Der Community-Vergleich zeigte 128,6 % Wirkungsgrad — das ging nicht mit rechten Dingen zu

**Betrifft dich das?** Alle, die *Community → Komponenten* nutzen.

Ein Speicher kann nicht mehr abgeben, als er aufgenommen hat. Der Wert war unser Fehler, nicht der einer Anlage: eedc überträgt **gar keinen Wirkungsgrad** an den Community-Server, sondern nur die reinen kWh — der Prozentwert entstand erst dort, und zwar ohne jede Prüfung.

Schlimmer: Er lief über **alles je Eingereichte**, während die Zyklen direkt daneben auf zwölf Monate gerechnet waren und mindestens ein halbes Jahr Daten verlangten. Zwei verschiedene Zeiträume in einer Tabellenzeile — und ein einziger fehlerhafter Datensatz reichte, um das Klassenmittel um fast 40 Prozentpunkte zu verschieben.

Jetzt gilt für den Wirkungsgrad dasselbe wie für die Zyklen daneben: gleicher Zeitraum, gleiche Mindest-Laufzeit. Unmögliche Werte fließen nicht mehr ein — sie werden **übersprungen, nicht gestutzt**, denn ein auf 100 % gekappter Wert sähe aus wie ein perfekter Speicher. Und statt des Durchschnitts steht der **Median**, den ein einzelner Ausreißer nicht mehr kippt.

**Außerdem:** Es gibt jetzt eine Klasse **bis 5 kWh** — kleine Speicher fehlten in dieser Auswertung bisher komplett, weshalb auch die Zahl der verglichenen Anlagen zu niedrig war. Und wenn dein Speicher größer als 15 kWh ist, wird deine Zeile endlich als **„(Du)"** markiert.

### Jede Komponente sagt jetzt, wie weit sie ist

**Betrifft dich das?** Alle, die *Auswertungen → ROI* benutzen.

Die Tabelle dort nannte je Komponente zwei Zahlen, und beide waren Rechnungen über die Zukunft: „so viel Prozent pro Jahr" und „so viele Jahre bis zur Amortisation". Was fehlte, war die einfachste Frage: **wie viel ist von dieser Anschaffung eigentlich schon zurückgekommen?**

Genau das steht jetzt in der neuen Spalte **„Fortschritt"** — die tatsächlich erzielten Erträge gegen den Betrag, den du für diese Komponente eingesetzt hast. Diese Zahl unterstellt nichts über die Zukunft; sie kann deshalb auch nicht zu optimistisch sein. Beide Sichten stehen bewusst nebeneinander: die Dauer sagt dir, wohin es geht, der Fortschritt sagt dir, wo du bist.

Zwei Dinge, die dir auffallen könnten:

- **Manche Zeilen zeigen „—".** Das heißt nicht „null Euro", sondern „lässt sich dieser Komponente nicht zuordnen". Eine Förderung, die du im Monatsabschluss für die ganze Anlage gebucht hast, gehört zu keinem einzelnen Gerät — sie zählt weiterhin in der Gesamtzahl, aber eedc verteilt sie nicht auf gut Glück.
- **Ein Wert kann negativ sein.** Dann hat die Komponente in der bisherigen Laufzeit mehr Betriebskosten verursacht als Ertrag gebracht. Auch das ist eine Aussage — sie wird nicht auf 0 geschönt.

### Zweiter Erzeuger, eigener Einspeisetarif — ohne monatliches Nachtragen

**Betrifft dich das?** Alle, die einen zweiten Erzeuger mit einer **anderen Einspeisevergütung** betreiben — etwa einen später dazugekommenen Wechselrichter mit eigenem EEG-Satz.

eedc kennt genau **einen** Einspeisesatz pro Anlage. Deinen zweiten kann es deshalb nicht ausrechnen — bisher blieb nur, den Erlös jeden Monat von Hand als sonstigen Ertrag zu buchen.

Jetzt gibt es einen besseren Weg: Eine Komponente vom Typ *Sonstiges* mit Kategorie **Erzeuger** hat das neue Feld **„Einspeise-Erlös (€)"**. Du kannst es unter *Einstellungen → Datenquellen* einem Sensor aus Home Assistant zuordnen — einem Helfer, der den Erlös mit deinem Satz aufsummiert. Dann steht der Betrag beim Monatsabschluss als Vorschlag da, monatsgenau und ohne Tippen.

**So richtest du es ein:** In Home Assistant einen Helfer anlegen, der den Erlös aufsummiert — **ohne Zyklus**, also nie zurücksetzen; eedc bildet die Monatswerte selbst aus der Differenz. In eedc die Komponente anlegen, das Feld zuordnen, fertig. Wenn du den Erlös bisher von Hand gebucht hast: ab dem Umstiegsmonat weglassen, sonst zählt er doppelt. Deine bisherigen Buchungen bleiben erhalten.

### Der Daten-Checker sagt dir, wenn ein Betrag am falschen Ort steht

**Betrifft dich das?** Alle, die unter *Sonstige Positionen* im Monatsabschluss regelmäßig denselben Posten buchen — Wartung, Versicherung, den Einspeise-Erlös eines zweiten Erzeugers.

eedc fragt dich nie, ob ein Betrag einmalig oder wiederkehrend ist. Es liest das am **Ort**: Ein Jahresbetrag an der Komponente kommt jedes Jahr wieder (und steht damit in der Prognose), eine Position im Monatsabschluss ist einmal geflossen. Das ist bequem — und genau deshalb kann man sich dort vertun, ohne es zu merken.

Zwei neue Hinweise im Daten-Checker:

- **„‚Wartung' steht in 4 Monaten im Monatsabschluss."** Sieht wiederkehrend aus? Dann gehört der Betrag als **Kosten/Jahr** (oder **Ertrag/Jahr**) an die Komponente — dort wirkt er auch in Prognose und Amortisation. Einmaliges bleibt richtig, wo es ist.
- **„… obwohl Kosten/Jahr gepflegt ist."** Dann steht derselbe Betrag zweimal in der Rechnung. In den Monatsabschluss gehört nur die **Abweichung** vom Plan — die Nachzahlung, nicht die ganze Rechnung.

**Beides sind Hinweise, keine Fehler**, und beide sagen, was zu tun ist. eedc liest dabei **nur die Wiederholung**, nie die Bedeutung deiner Bezeichnung: aus „Restwert" oder „Förderung" etwas zu schließen wäre geraten.

### Im PDF-Bericht stand bei der Amortisation dauerhaft „—"

**Betrifft dich das?** Alle, die den **Finanzbericht als PDF** erzeugen.

Die Zeile „Amortisation" konnte dort gar keine Zahl zeigen: Das PDF rechnete mit einem Feld, das sich nirgends eintragen ließ — und deshalb bei jeder Komponente leer war. Jetzt nimmt es dieselbe Kennzahl wie *Auswertungen → ROI* und die HA-Sensoren. Eine Zahl, drei Orte.

### Zwei Prüf-Ergebnisse deiner E-Mobilität waren unsichtbar

**Betrifft dich das?** Alle mit **Wallbox und E-Auto** — und alle mit einem **Plug-in-Hybrid**.

Der Daten-Checker prüft seit der letzten Version zwei Dinge, deren Ergebnis auf der Seite *Einstellungen → Daten-Checker* nie erschienen ist. Nicht „stand weiter unten", sondern **gar nicht**: Die Liste kannte diese beiden Prüfungen nicht und ließ sie beim Anzeigen weg.

- **„Doppelt gezählte Ladetage."** Wenn dieselbe Ladung an der Wallbox *und* am Auto gemessen wird, steht sie an manchen Tagen zweimal in den Tageswerten. Der Befund nennt die betroffenen Tage und hat einen Knopf daneben: **„Zeitraum neu aggregieren"**. Der ist damit erstmals erreichbar.
- **„Elektrischer Anteil unbestimmt"** beim Plug-in-Hybrid — der Hinweis, dass eedc für Monate ohne Fahrverbrauch mit 100 % elektrisch rechnet und deine Ersparnis dadurch zu gut aussieht.

**Was du tun musst:** Einmal in *Einstellungen → Daten-Checker* schauen. Wenn dort jetzt ein Hinweis steht, ist er nicht neu entstanden — er war nur nie sichtbar.

### Eine Buchung „für die ganze Anlage" kommt jetzt überall an

**Betrifft dich das?** Alle, die im Monatsabschluss unter *Sonstige Positionen* etwas **ohne** Komponente buchen — eine Förderung für die Anlage, eine Versicherung fürs Ganze, eine Reparatur, die zu keinem einzelnen Gerät gehört.

Solche Buchungen wirkten bisher nur in einem Teil der Sichten: Der HA-Sensor rechnete sie mit, *Auswertungen → ROI* und die *Aussichten* ließen sie weg. Zwei Sichten auf dieselbe Anlage nannten deshalb verschiedene Beträge, und eine anlagenweit gebuchte Förderung tauchte in der Wirtschaftlichkeit überhaupt nicht auf.

Jetzt zählen sie in **allen** Sichten mit demselben Betrag: *Auswertungen → ROI*, *Aussichten*, PDF-Finanzbericht und HA-Sensoren. Auf einer einzelnen ROI-**Zeile** stehen sie weiterhin nicht — sie gehören zu keinem Gerät; dort steht „—", und der Betrag ist in der Gesamtzahl enthalten. **Du musst nichts umbuchen.**

### „15,8 Jahre" — und unter welcher Annahme

**Betrifft dich das?** Alle, die irgendwo eine Amortisationsdauer lesen.

Eine Dauer ist keine Messung. Sie ist eine Rechnung, die etwas über die Zukunft unterstellen **muss** — und eedc unterstellt: *es geht nie wieder etwas kaputt*. Das ist die optimistische Variante, und sie ist bewusst gewählt (die Alternative wäre, aus ein bis zwei Reparaturen eine Reparatur-Rate hochzurechnen, die jedes Jahr anders aussieht). Nur stand sie bisher nirgends.

Jetzt steht sie neben jeder Dauer: an der Kachel und der Break-Even-Kurve in *Auswertungen → ROI*, je Zeile in der Tabelle, im Komponenten-Hub der Wallbox, im PDF-Finanzbericht und im Rechenweg des HA-Sensors `amortisation_jahre`.

**Und sie richtet sich nach dem, was du gepflegt hast.** Hast du an einer Komponente *Kosten/Jahr* eingetragen, liest du dort „inkl. 200,00 €/Jahr Betriebskosten, ohne weitere Instandhaltung" — dieser Betrag ist in der Zahl bereits enthalten. Wer mit künftiger Instandhaltung rechnen möchte, trägt sie genau dort als Jahresbetrag ein; die Dauer sagt dann selbst, dass sie damit rechnet.

**Es ändert sich keine Zahl** — nur das, was danebensteht.

### Betriebskosten zählen nur, solange das Gerät läuft

**Betrifft dich das?** Alle, die bei einer Komponente **Kosten/Jahr** gepflegt haben und sie **später** angeschafft oder inzwischen stillgelegt haben.

Bisher hat eedc die Jahres-Betriebskosten über deinen **gesamten** Auswertungszeitraum abgezogen — auch für Monate, in denen es das Gerät noch gar nicht gab. Eine 2024 gekaufte Wärmepumpe hat damit rückwirkend ab 2023 Versicherung gezahlt, und eine stillgelegte Komponente hat deine Amortisation dauerhaft verlängert, obwohl sie längst keine Kosten mehr verursacht.

Das ist korrigiert: Jede Komponente trägt ihre Kosten nur für die Zeit, in der sie tatsächlich lief. **Dein Amortisations-Fortschritt wird dadurch etwas besser** — an der Demo-Anlage von 10,8 % auf 11,4 %. Du musst nichts tun.

### Deine Amortisation wird kürzer — fünf HA-Sensoren springen einmalig

**Betrifft dich das?** Alle, die unter *Sonstige Positionen* schon einmal eine **Ausgabe** gebucht haben (Reparatur, Ersatzteil, Wartung) — und alle, die eine Komponente **später** angeschafft haben als die Anlage selbst.

Eine einmalige Reparatur wurde bisher wie eine jährlich wiederkehrende Belastung behandelt: Sie wurde von der Ersparnis **jedes Jahres** abgezogen. Eine Reparatur von 3.000 € an einer Wärmepumpe verlängerte die Amortisation dadurch von 8,1 auf **42,6 Jahre** — und die Zahl wurde jedes Folgejahr schlechter, ohne dass etwas passiert wäre. Jetzt zählt sie als das, was sie ist: **einmal ausgegebenes Geld**, das sich zurückverdienen muss. Dasselbe Beispiel ergibt **10,5 Jahre**.

Zweite Korrektur an derselben Rechnung: Jede Ersparnis wird jetzt mit **ihrer eigenen** Laufzeit hochgerechnet. Eine Wärmepumpe, die erst seit 25 von 31 erfassten Monaten läuft, wurde vorher auf die Anlagen-Laufzeit verdünnt — ihre Kosten zählten aber voll dagegen.

**Was sich sichtbar ändert:** `sensor.*_amortisation_jahre`, `sensor.*_roi_prozent` und `sensor.*_jahres_ersparnis_euro` sowie die Amortisations-Anzeigen in *Auswertungen → ROI* und in den *Aussichten*. An der Demo-Anlage: **26,4 → 18,5 Jahre**. In der Langzeitstatistik ist das ein Sprung an einem Tag — es gehen keine Daten verloren. **Dein Netto-Ertrag bleibt unverändert:** Was ein Monat gekostet und eingebracht hat, rechnet eedc weiter genauso.

### Einmalige Erträge werden nicht mehr in die Zukunft hochgerechnet

**Betrifft dich das?** Alle, die unter *Sonstige Positionen* einen **Ertrag** gebucht haben — THG-Quote, eine Förderung, einen einmaligen Erlös.

Dieselbe Idee wie oben, nur auf der anderen Seite: Ein Betrag, den du in **einem** Monat eingetragen hast, wurde bisher in **jedes** Prognosejahr weitergeschrieben. Das unterstellt eine Wiederholung, die du nie behauptet hast.

Der Betrag zählt weiterhin dort, wo er tatsächlich geflossen ist — in der **Monatsbilanz**. Aus der **Vorhersage** verschwindet er. An der Demo-Anlage sinkt der prognostizierte Jahres-Netto-Ertrag dadurch von 5.794 auf **5.618 €**, die Amortisation in *Auswertungen → ROI* geht von 15,4 auf **15,8 Jahre**.

### Eine Förderung senkt dein eingesetztes Geld

**Betrifft dich das?** Dieselben wie oben: alle, die unter *Sonstige Positionen* einen **Ertrag** gebucht haben.

Wo gehört so ein Betrag hin, wenn nicht in die Vorhersage? In den **Kapitaleinsatz** — also in die Summe, die sich zurückverdienen muss. Eine Förderung oder eine THG-Quote ist Geld, das du **nie ausgeben musstest**; es muss auch nicht wieder hereinkommen. Damit ist die Rechnung rund: Eine **Ausgabe** im Monatsabschluss erhöht deinen Kapitaleinsatz, ein **Ertrag** mindert ihn — beides genau einmal.

**Was du siehst:** Deine Amortisation wird **kürzer**, und der ⓘ-Tooltip in *Auswertungen → ROI* schreibt den Abzug aus („90.900 € + 1.015 € sonstige Ausgaben − 455 € sonstige Erträge"). Das gilt für die Gesamtzahl **und je Zeile**, für die *Aussichten*, den PDF-Finanzbericht und die HA-Sensoren `amortisation_jahre` und `roi_prozent`. An der Demo-Anlage: eingesetzter Betrag 91.915 → **91.460 €**, das Fahrzeug 14,3 → **14,0 Jahre**.

**In der Monatsbilanz ändert sich nichts** — dort bleibt die Förderung ein Ertrag des Monats, in dem sie kam. Und der **Amortisations-Fortschritt** sinkt leicht (11,4 → 10,9 % an der Demo-Anlage): Der Betrag zählt nicht mehr als „zurückgekommen", weil er gar nicht erst eingesetzt wurde. Beide Zahlen beschreiben dasselbe Geld, nur von der jeweils richtigen Seite.

> ⚑ **Wenn der Erlös jedes Jahr wiederkommt**, gehört er nicht in den Monatsabschluss, sondern an die Komponente — als **„Ertrag/Jahr (€)"** oder, beim zweiten Erzeuger, als **„Einspeise-Erlös (€)"** (beides weiter oben). **Umstellen musst du nichts:** deine bisherigen Buchungen bleiben erhalten und sichtbar, und der Daten-Checker sagt dir, wenn ein Posten dauerhaft am unpassenden Ort steht.

### Neu: „Ertrag/Jahr (€)" — für alles, was jedes Jahr wiederkommt

**Betrifft dich das?** Alle mit einem wiederkehrenden Erlös, den eedc nicht selbst ausrechnen kann — der Klassiker ist ein **zweiter Erzeuger mit eigenem Einspeisetarif** (eedc kennt genau einen Einspeisesatz je Anlage).

Bisher blieb dafür nur die monatliche Handbuchung. Jetzt trägst du den Betrag **einmal** bei der Komponente ein: *Bearbeiten → Weitere Angaben & Kosten →* **„Ertrag/Jahr (€)"**. Das ist das Gegenstück zum Feld „Betriebskosten/Jahr" direkt daneben, und es wirkt in der Finanz-Prognose, in *Auswertungen → ROI* und in den HA-Sensoren.

Das Feld gibt es bei **Wallbox** und **Sonstiges**. Bei PV, Speicher, Wärmepumpe, E-Auto und Balkonkraftwerk rechnet eedc die Jahres-Einsparung aus deinen Daten selbst — dort wäre ein eigener Betrag nur eine zweite Meinung.

> ⚠ **Nicht beides pflegen.** Wer den Erlös künftig als Jahresbetrag führt, sollte die monatlichen Handbuchungen ab dem Umstellungsmonat einstellen — sonst zählt derselbe Erlös zweimal. Die bereits gebuchten Monate bleiben unverändert richtig; sie beschreiben die Vergangenheit.

### Zwei Wechselrichter in der Hersteller-Wolke? Beide kommen jetzt an

**Betrifft dich das?** Alle, deren Hersteller-Portal **mehrere „Stationen"** führt — meist eine je Wechselrichter. Bei Solarman ist das der Normalfall.

**Erst die Frage, die dahintersteckt: eine Anlage oder zwei?** In eedc ist eine Anlage ein **Standort mit einem Hausanschluss**, kein einzelnes Gerät. Netzbezug, Einspeisung, Eigenverbrauch, Autarkie und die ganze Wirtschaftlichkeit gibt es dort nur **einmal**. Zwei Anlagen für ein Haus anzulegen würde all das in zwei Hälften zerlegen, von denen keine stimmt. Richtig ist: **eine** Anlage, darin **je Gerät ein Wechselrichter**, und an jedem hängen seine PV-Module und ggf. sein Speicher.

**Und jetzt der Teil, der nicht funktioniert hat.** Der Cloud-Import schrieb bisher immer auf die **ganze Anlage**. Beim zweiten Wechselrichter blieben deshalb nur zwei schlechte Ausgänge: ohne Haken wurde der ganze Monat übersprungen — der zweite kam gar nicht an; mit Haken „überschreiben" wurde sein Ertrag anteilig auf **alle** Stränge verteilt und die Hauszähler-Werte des ersten ersetzt. Beides ohne einen Hinweis.

In der Vorschau steht jetzt eine neue Auswahl: **„Diese Quelle misst"**. Voreingestellt ist *die ganze Anlage* — wer nur ein Gerät hat, merkt von der Neuerung nichts. Wählst du einen **Wechselrichter**, dann gilt:

- die Erträge gehen an **seine** PV-Module und **seinen** Speicher, nicht an alle;
- **Netzbezug, Einspeisung und Eigenverbrauch werden nicht übernommen** — das sind Größen des ganzen Hauses, und eedc sagt dir das nach dem Import auch;
- ein bereits erfasster Monat blockiert die zweite Quelle **nicht** mehr.

So importierst du Station 1 und Station 2 nacheinander für denselben Zeitraum, und keine verdrängt die andere.

**Und du musst die Zugangsdaten nur einmal eintippen.** eedc merkte sich bisher **ein** Cloud-Konto je Anlage; jedes Speichern überschrieb das vorige. Jetzt speicherst du je Gerät eines — und der **monatliche Abruf im Monatsabschluss holt alle**. Jede Station liefert die Werte ihres Wechselrichters, und wenn eine davon gerade klemmt, kommen die anderen trotzdem durch; eedc schreibt dann dazu, welche gefehlt hat. Eine halbe Erzeugung soll nicht wie die ganze aussehen.

> **Woher kommen Netzbezug und Einspeisung?** Nur aus einer Quelle **ohne** Geräte-Zuordnung. Das ist Absicht: Ein Wechselrichter meldet den Netzbezug, den *er* sieht — bei zwei Geräten am selben Hausanschluss wäre das entweder doppelt gezählt oder nur ein Teil. Misst keine deiner Quellen das Haus, bleiben die beiden Felder leer, und eedc sagt dir das. Du pflegst sie dann aus dem Zähler oder aus deinen HA-Sensoren.

An deiner bestehenden Einrichtung musst du nichts ändern — ein bereits gespeichertes Konto wird übernommen und gilt wie bisher für die ganze Anlage.

> ⚑ **Wenn du das schon einmal versucht hast:** Sieh dir die Monatswerte deiner PV-Module an (*Komponenten → PV-Modul → Monatswerte*). Ein früherer Import mit „überschreiben" hat dort den Ertrag der **zuletzt** importierten Station nach Nennleistung verteilt stehen lassen. Ein erneuter Import je Wechselrichter mit der neuen Zuordnung setzt beide Stränge wieder auf ihre eigene Messung.

*Gefunden hat das OliS2811, der zwei Sofar-Wechselrichter betreibt ([#349](https://github.com/supernova1963/eedc-homeassistant/issues/349)).*

---

## v4.0.11 — Nichts raten, wo sich messen lässt (August 2026)

### Plug-in-Hybrid: der Benzin-Anteil zählt jetzt mit

**Betrifft dich das?** Alle, deren Fahrzeug **auch** einen Verbrenner hat. Fährst du rein elektrisch, ändert sich für dich **nichts** — keine einzige Zahl.

eedc hat bei einer Fahrzeug-Investition bisher unterstellt, dass **alle** Kilometer elektrisch gefahren wurden. Bei einem Plug-in-Hybrid stimmt das nicht, und der Fehler ging immer in dieselbe Richtung: Der getankte Kraftstoff tauchte **weder als Kosten noch als Emission** auf. Ersparnis und CO₂-Bilanz sahen besser aus als die Realität.

**Was du tun musst:** In der Fahrzeug-Komponente unter *Vergleich & Betrieb* das neue Feld **„Eigener Verbrauch (L/100 km)"** ausfüllen — das ist, was dein Fahrzeug im Verbrenner-Betrieb wirklich verbraucht. Nicht zu verwechseln mit dem Feld darüber: **„Verbrenner-Verbrauch"** beschreibt weiterhin das *hypothetische* Vergleichsfahrzeug, das du *nicht* gekauft hast. Zwei Bedeutungen, zwei Felder — deshalb wurde das alte Feld nicht umgedeutet.

Ein „Fahrzeugtyp: Plug-in-Hybrid" gibt es bewusst nicht. **Das ausgefüllte Feld ist die Aussage.** Bleibt es leer, rechnet eedc wie bisher.

**Woher eedc den elektrischen Anteil nimmt** — in dieser Reihenfolge:

1. **Gemessen**, wenn du den monatlichen **Fahrverbrauch in kWh** erfasst: daraus und aus deinem kWh/100 km folgt, wie weit du elektrisch gekommen bist. Mehr als die gefahrenen Kilometer können es dabei nie werden.
2. **Geschätzt**, wenn du stattdessen den **elektrischen Fahranteil in %** einträgst.
3. **Gar nicht** — dann bleibt es beim alten Verhalten, und der [Daten-Checker](HANDBUCH_DATEN_CHECKER.md) sagt dir, dass die Angabe fehlt. Einen Richtwert („so 40–60 % sind üblich") setzt eedc **nicht** ein: das wäre eine Behauptung über dein Auto, keine Rechnung.

   > ⚠ **Nachträglich richtiggestellt (August 2026):** Der Hinweis wurde zwar erzeugt, erschien auf der Seite *Einstellungen → Daten-Checker* aber nicht — nur im Komponenten-Hub des Fahrzeugs. Die Anzeige-Liste kannte die Kategorie nicht und ließ sie beim Aufbau der Seite weg. Behoben; seither steht der Hinweis an beiden Orten. Wer ihn damals vermisst hat, hatte recht.

**Was du danach siehst:** Im Komponenten-Hub stehen unter *Umwelt* zwei neue Werte — **Verbrenner-Anteil** in km und **Kraftstoffkosten** in Euro, mit dem Hinweis, ob sie gemessen oder geschätzt sind. Die Ersparnis vs. Verbrenner sinkt entsprechend, ebenso die CO₂-Einsparung. Der Vergleich mit dem Benziner bleibt dabei über **alle** Kilometer stehen — sonst würdest du dein Auto mit einem halben vergleichen.

> **Deine geladene Energie wird nicht angetastet.** Sie ist gemessen, und ein Hybrid lädt ohnehin weniger. Sie zusätzlich zu kürzen hieße, denselben Anteil zweimal abzuziehen.

### Wie viel deiner Autoladung kam aus der eigenen Sonne? eedc schätzt es jetzt

**Betrifft dich das?** Alle, die zu Hause laden und **keinen eigenen Sensor** für den PV-Anteil haben. Wer den Anteil pflegt — etwa über evcc —, sieht **keine einzige veränderte Zahl**.

Eine Wallbox zählt Kilowattstunden, nicht deren Herkunft. Fehlte die Angabe, hat eedc bisher die **komplette** Heimladung als Netzstrom verbucht: 0 % Sonne im Komponenten-Hub, die volle Ladung als Netzbezug in der CO₂-Bilanz, eine entsprechend zu kleine Ersparnis. Das war keine Messung, sondern eine Annahme — und die ungünstigste von allen.

Jetzt leitet eedc den Anteil aus deinen eigenen Stundenwerten ab, nach derselben Idee wie evcc: Was in einer Ladestunde weder aus dem Netz noch aus dem Speicher kam, kann nur aus deiner PV gekommen sein — und was du in dieser Stunde eingespeist hast, hätte stattdessen laden können.

**Wie gut das trifft, ist gemessen und nicht behauptet:** An einer echten Anlage mit evcc als Referenz (963 kWh Heimladung über sieben Monate) kam evcc auf **67,9 %** Sonnenanteil, eedcs Rechnung auf **64,7 %**. Sie untertreibt also eher, als dir zu schmeicheln. Der Wert ist in der Datenherkunft ausdrücklich als **abgeleitet** gekennzeichnet; wo nicht jede Ladestunde auswertbar war, steht das dabei.

**Was du tun musst: nichts.** Deine Zahlen werden größer — die E-Auto-Netzladung sinkt, die ausgewiesene Ersparnis steigt, und zwar **überall dieselbe**: Komponenten-Hub (E-Auto und Wallbox), *Cockpit → Monat* und *→ Jahr*, *Auswertungen → Komponenten*, Aussichten, Jahresbericht-PDF, Monats-Tabelle und CO₂-Bilanz.

> ⚠ **Der Sensor `sensor.…_e_auto_pv_anteil_prozent` springt einmalig.** Er meldete bisher 0 % und zeigt künftig den abgeleiteten Anteil. In der Langzeitstatistik ist das ein Sprung an einem Tag — es gehen keine Daten verloren. Betroffen ist nur, wer keinen eigenen PV-Ladesensor pflegt.

> **Ein selbst gepflegter Wert wird nie überschrieben** — auch eine bewusst eingetragene **0** nicht. Und **rückwirkend passiert nichts**: Die Schätzung entsteht beim Aggregieren eines Tages, abgeschlossene Zeiträume bleiben, wie sie sind.

Auch die **ROI-Prognose rät nicht mehr**: Sie rechnete bisher mit 60 % PV-Anteil, während dieselbe Anlage im IST 0 % zeigte — zwei Zahlen für dieselbe Größe. Jetzt nimmt sie den tatsächlich erreichten Anteil, solange am Fahrzeug keiner gepflegt ist. Dein eigener Wert im Feld *PV-Ladeanteil (%)* hat weiterhin Vorrang.

> **Der Community-Vergleich bleibt bei gemessenen Werten.** Dorthin geht weiterhin nur, was wirklich gezählt wurde — dein geteilter Datensatz ändert sich durch diese Neuerung nicht.

### Hast du deinen Stromtarif einmal gewechselt? Dann stimmte die E-Auto-Ersparnis nicht

**Betrifft dich das?** Alle mit E-Auto, die **den Tarif schon einmal gewechselt** haben. Wer immer denselben Arbeitspreis hatte, sieht **keine veränderte Zahl** — der Durchschnitt eines einzigen Tarifs ist dieser Tarif.

*Cockpit → Jahr* und die HA-Sensoren haben deine **gesamte** Ladehistorie mit dem **heutigen** Arbeitspreis bewertet — auch Ladungen von vor drei Jahren. Der Komponenten-Hub rechnete gleichzeitig mit den Preisen, die damals galten. Dieselbe Größe, zwei verschiedene Zahlen: An einer Anlage mit vier Tarifstufen (40 → 32 → 34 → 31,5 ct) waren das **41,10 €** Unterschied bei identischer kWh-Basis.

Insgesamt gab es **vier** verschiedene Preisformen für einen Wert; zwei Sichten nahmen zusätzlich deinen allgemeinen Tarif statt eines gepflegten **Wallbox-Tarifs**. Jetzt bewertet jede Sicht die Ladung eines Monats mit dem Tarif dieses Monats — bei dynamischen Tarifen mit dem abgerechneten Durchschnitt.

> ⚠ **Vier HA-Sensoren springen dadurch einmalig:** `e_auto_ersparnis_vs_benzin_euro`, `netto_ertrag_euro`, `roi_prozent` und `amortisation_jahre`. Ein Sprung an einem Tag in der Langzeitstatistik, kein Datenverlust.

**Was du tun musst:** nichts. Wichtig ist nur, dass deine früheren Tarife mit ihrem Gültigkeitszeitraum gepflegt sind — dann rechnet jeder Monat mit seinem eigenen Preis.

### Lädst du über evcc? In den Aussichten fehlten die Stromkosten deines Autos komplett

**Betrifft dich das?** Alle, deren Ladung an der **Wallbox** erfasst wird statt am Fahrzeug — der Normalfall bei evcc.

*Auswertungen → Aussichten* war die einzige Sicht, die ihre Ladedaten ausschließlich an der Fahrzeug-Komponente gesucht hat. Liegen sie an der Wallbox, fand sie **gar nichts**. Folge: Die ausgewiesene bisherige Ersparnis war um die **kompletten Netzstromkosten** zu hoch, und die Prognose rechnete mangels Daten mit geratenen 50 % Netzanteil.

An einer echten Anlage gemessen (März–Juli 2026, ausschließlich Sensordaten): **0 statt 126 kWh** Netzladung und **0 statt 620 kWh** PV-Ladung. Diese Sicht zieht jetzt dieselbe Ladung heran wie Cockpit, Komponenten-Hub und HA-Export.

**Was du tun musst:** nichts — deine Aussichten-Zahlen fallen beim nächsten Aufruf niedriger und richtiger aus.

### Derselbe Ladevorgang konnte im Tagesverlauf zweimal auftauchen

**Betrifft dich das?** Alle, bei denen **Wallbox und E-Auto je einen eigenen kWh-Zähler** haben und das Fahrzeug der Wallbox **nicht ausdrücklich zugeordnet** ist.

In dieser Konstellation hat eedc dieselbe Ladung doppelt gezählt. Jetzt gilt in allen Pfaden dieselbe Regel: **Trägt eine Wallbox die Ladeenergie, ist sie die Quelle** — das Fahrzeug wird dann nicht zusätzlich addiert.

**Was du tun musst:** Bereits gespeicherte Tage bleiben zunächst unverändert. Der [Daten-Checker](HANDBUCH_DATEN_CHECKER.md) meldet sie dir jetzt und bietet **„Zeitraum neu aggregieren"** an. Das ist bewusst ein Knopf und kein automatischer Lauf beim Start: Die Reparatur überschreibt vorhandene Tageswerte, und diese Entscheidung gehört dir.

> ⚠ **Nachträglich richtiggestellt (August 2026):** Diese Meldung war zwar gebaut, auf der Seite *Einstellungen → Daten-Checker* aber **nicht sichtbar** — die Anzeige-Liste kannte die Kategorie nicht, und damit war auch der Knopf „Zeitraum neu aggregieren" nicht erreichbar. Behoben; die Meldung erscheint jetzt samt Reparatur-Knopf. Wer die doppelt gezählten Tage bisher nicht heilen konnte, findet den Weg dort ab sofort.

> **Reichweite des Knopfes:** Er heilt **Tag und Stunde**, nicht den Monatswert. Der Hinweis nennt dir den Zeitraum, den ein Lauf abdeckt.

### Einspeisevergütung: eedc schlägt keinen Satz mehr vor — und sagt, wie es rechnet

**Betrifft dich das?** Alle, die einen **neuen** Stromtarif anlegen, und alle, die den Satz seinerzeit aus dem Setup-Wizard übernommen haben. **Bestehende Tarife sind unberührt.**

Aus dem simon42-Forum kam die Frage, ob eedc flat mit der eingetragenen Zahl rechnet oder im Hintergrund einen Mischsatz aus der Anlagengröße ermittelt. Die Oberfläche gab darauf keine Antwort — das Feld hieß an beiden Eingabestellen nur „Einspeisevergütung (ct/kWh)". Jetzt steht daneben und in der Hilfe: **eedc rechnet flat mit deinem Satz.** Bei gestaffelter EEG-Vergütung gehört der nach kWp gewichtete **Mischsatz** ins Feld.

> ⚠ **Bitte einmal deinen Vergütungsbescheid prüfen.** Der Setup-Wizard trug bisher den Satz der *erreichten* Stufe ein (bis 10 kWp 8,2 ct, bis 40 kWp 7,1 ct, darüber 5,8 ct). Das EEG staffelt aber nach **installierter Leistung**, nicht nach eingespeister Menge: Für die Gesamtanlage gilt der gewichtete Mischsatz, und der liegt **höher** — bei 20 kWp etwa 7,65 statt 7,1 ct. Wer den Vorschlag übernommen hat, rechnet seinen Einspeise-Erlös **zu niedrig**.

Die Tabelle wurde nicht korrigiert, sondern **entfernt**: Die Sätze ändern sich laufend, und welcher für deine Anlage gilt, weißt nur du. Ein neuer Tarif startet deshalb mit **0** — eine geschätzte Zahl sähe aus wie eine gepflegte.

**Was du tun musst:** Beim Anlegen eines neuen Tarifs den Satz aus deinem Bescheid eintragen. Bleibt die 0 stehen, sagen dir beide Formulare, was das bedeutet (kein Einspeise-Erlös), und der Daten-Checker meldet es — aber nur, wenn im Gültigkeitszeitraum des Tarifs tatsächlich Einspeisung erfasst ist. Bei Volleinspeisung ohne Vergütung oder ausgelaufener Förderung ist 0 richtig und nichts zu tun.

### Eine eingetragene 0 ct Einspeisevergütung wurde an drei Stellen still zu 8,2 ct

**Betrifft dich das?** Alle, die bewusst **0** eingetragen haben — etwa bei unvergüteter Einspeisung.

An drei Stellen hat eedc die gepflegte Null nicht von „nichts eingetragen" unterscheiden können und ersatzweise mit **8,2 ct** gerechnet: im **Vorjahresvergleich** in *Cockpit → Monat*, im **T-Konto je Investition** und in der **Wirtschaftlichkeit je Komponente**. Dort stand ein Erlös, den es nie gab — während Jahresbericht, Aussichten und HA-Export im selben Moment korrekt mit 0 rechneten.

**Was du tun musst:** nichts. Alle Sichten nennen jetzt dieselbe Zahl; die betroffenen Werte sinken auf den Betrag, den die übrigen Sichten schon immer zeigten.

### MQTT-Export: „0 von 0 Sensoren publiziert" war eine Fehlermeldung

**Betrifft dich das?** Alle, die den Sensor-Export nach Home Assistant einrichten — besonders kurz nach der Installation.

Die Fläche zeigte „**0 von 0 Sensoren publiziert**" mit einem grünen Häkchen und darunter „Verfügbare Sensoren (0)". Das sah nach *hat geklappt, es gibt eben nichts* aus. Tatsächlich war es das Gegenteil: eedc **hatte** einen Grund genannt, und die Oberfläche hat ihn verschluckt.

Der Grund ist fast immer derselbe: **alle Export-Sensoren werden aus abgeschlossenen Monatsdaten gerechnet.** Live-Werte und Tagesdaten genügen dafür nicht — ROI, Einspeisevergütung und die übrigen Kennzahlen brauchen einen fertigen Monat. Solange keiner vorliegt, gibt es nichts zu publizieren.

Zwei Dinge sind jetzt anders: Ein gescheiterter Publish zeigt **den Grund**, in Rot, statt einer Erfolgsmeldung. Und die leere Sensorliste sagt selbst, worauf sie wartet — statt kommentarlos leer zu bleiben, während die Discovery-Box daneben verspricht, die Sensoren erschienen automatisch in Home Assistant.

> **Du musst nichts umstellen.** Schließe deinen ersten Monat ab (*Cockpit → Monat*), danach erscheinen die Sensoren hier und werden mit dem nächsten Durchlauf publiziert.

### Deye/Solarman: der Cloud-Import holt jetzt wirklich Daten

**Betrifft dich das?** Alle, die ihre Historie über **Deye / Solarman** aus der Hersteller-Cloud importieren wollen.

Der Import kam bisher genau bis zur Anmeldung. Die meldete Erfolg — und danach kam er ohne eine einzige Zahl zurück, weil die Hersteller-Schnittstelle den Datenabruf mit `invalid param` abwies. Der Grund war ein Detail im Zeitraum: eedc fragte die Monatswerte mit einem **Tagesdatum** ab (`2025-01-01`), Solarman will dafür einen **Monatsstempel** (`2025-01`).

Das ist jetzt gemessen statt vermutet: **OliS2811** hat vier Probeaufrufe gegen seine beiden echten Anlagen gefahren — darunter eine Kontrolle, die den Fehler zuverlässig auslöst. Erst dadurch stand fest, welches der beiden Formate die Schnittstelle akzeptiert.

> **Der Provider trägt weiterhin den Hinweis „nicht mit echten Geräten getestet".** Er verschwindet, sobald ein vollständiger Import bei einem Anwender durchgelaufen ist — bis dahin bleibt der Hinweis stehen, auch wenn jeder bekannte Defekt behoben ist.

### Speicher hinter der Wechselrichter-Grenze: dein SOLL war zu niedrig

**Betrifft dich das?** Alle mit **Balkonkraftwerk + Akku** und alle mit **Hybrid-Wechselrichter** (Speicher gleichstromseitig am Wechselrichter).

Seit v4.0.9 begrenzt eedc dein SOLL an der eingetragenen Wechselrichter-Leistung. Das ist richtig, solange der Überschuss über dieser Grenze wirklich verloren geht. Hängt aber ein **DC-gekoppelter Speicher** dahinter, ist er das nicht: er lädt den Akku, ohne durch den Wechselrichter zu müssen. eedc hat ihn trotzdem abgeschnitten.

Sichtbar war das als **zu niedriges SOLL** — dein SOLL/IST-Vergleich sah besser aus, als deine Anlage ist, und die Performance Ratio lag zu hoch. Beim Balkonkraftwerk mit Speicher traf es die Mittagsspitze praktisch täglich.

> **Deine SOLL-Zahlen steigen dadurch.** Deine gemessenen Erträge ändern sich **nicht** — nur die Erwartung, gegen die sie gehalten werden, wird wieder realistisch. Bei **AC**-gekoppeltem Speicher bleibt alles wie bisher: dort läuft die Energie tatsächlich durch den Wechselrichter, die Begrenzung ist dann richtig.

> **Prüf einmal die Kopplung deines Speichers** (*Einstellungen → Komponenten → Speicher → Kopplung*). Sie war bisher eine reine Beschreibung und hat keine Zahl bewegt — ab jetzt entscheidet sie mit, ob dein SOLL begrenzt wird. Die Vorbelegung *Automatisch* trifft den Normalfall (Speicher am Wechselrichter ⇒ DC).

### Balkonkraftwerk: der String-Vergleich zeigt dich jetzt auch

**Betrifft dich das?** Alle, die **nur ein Balkonkraftwerk** haben — und alle mit Balkonkraftwerk **neben** einer Dachanlage.

Seit v4.0.9 bekommt ein Balkonkraftwerk ein PVGIS-SOLL. Zwei Blöcke daneben blieben aber leer und schrieben weiterhin *„Keine PV-Module gefunden"*: **SOLL/IST pro PV-String** und **Mehrjahres-Performance** in *Auswertungen → Prognose*. Genauso fehlte der String-Abschnitt im **Jahresbericht-PDF**. Der Grund: diese Sichten fragen über eine andere Abfrage nach den Komponenten, und die kannte nur den Typ *PV-Modulfeld*.

Sie fragen jetzt nach dem **PV-Erzeuger**. Dein Balkonkraftwerk ist dort eine Zeile wie ein Dach-String — mit seiner Nennleistung (aus *Leistung je Modul × Anzahl*), seinem SOLL und seinem gemessenen Ertrag.

> **Was sich dadurch nicht ändert:** Deine Energiebilanz, dein Eigenverbrauch, deine Wirtschaftlichkeit und die ROI-Sicht bleiben Zahl für Zahl gleich. Das Balkonkraftwerk bekommt **keinen zweiten Erfassungsweg** — es bleibt eine Investition, und seine Erzeugung zählt weiterhin genau einmal.

### Community-Vergleich: deine echte Ausrichtung statt „Süd, 30°"

**Betrifft dich das?** Nur wer **ausschließlich ein Balkonkraftwerk** hat **und** am Community-Vergleich teilnimmt.

Beim Teilen hat eedc Neigung und Ausrichtung bisher nur aus Komponenten vom Typ *PV-Modulfeld* gebildet. Gab es keine, wurden ersatzweise **30° und „Süd"** übermittelt — auch wenn dein Balkonkraftwerk an einer **Westfassade** hängt. Der Community-Server rechnet nichts nach, deine Anlage wurde also mit einer Gruppe verglichen, zu der sie nicht gehört.

Jetzt zählt dein Balkonkraftwerk mit seinen tatsächlich gepflegten Werten. **Bestehende Einträge korrigieren sich beim nächsten vollständigen Teilen** — du musst nichts löschen.

### Deine Solarprognose merkt selbst, wenn sie nicht mehr zu deiner Anlage passt

Eine PVGIS-Prognose wird beim Abruf eingefroren. Baust du danach um — ein String kommt dazu, ein Balkonkraftwerk ersetzt die alte Anlage, das Dach wird anders belegt —, dann vergleicht eedc deine Erträge weiter mit der **alten** Anlage. In einem gemeldeten Fall stand für ein 2,4-kWp-Balkonkraftwerk ein Jahres-SOLL von **357 MWh**, weil die gespeicherte Prognose zu einem viel größeren System gehörte.

Ab jetzt prüft eedc jede Nacht, ob die aktive Prognose noch passt, und holt bei Bedarf eine neue — **mit deinen eingestellten Systemverlusten**, nicht mit dem Standardwert. Nachgezogen wird bei geänderter **Nennleistung, Ausrichtung, Neigung**, geändertem **Standort** oder einem hinzugekommenen bzw. gelöschten **Horizontprofil**. Deine bisherige Prognose bleibt in der Historie und lässt sich jederzeit wieder aktivieren — es geht nichts verloren.

**Die Warnung „Letzter Abruf vor N Tagen" ist weg**, und das ist Absicht: PVGIS rechnet mit einem Mittel über viele Jahre. Eine ein Jahr alte Prognose liefert für dieselbe Anlage dieselbe Zahl wie eine von heute — sie war nie „zu alt". Die Kachel *Einstellungen → Solarprognose* sagt dir stattdessen, **was** nicht mehr passt, zum Beispiel „Nennleistung 9,80 → 2,40 kWp".

> ⚠ **Deine SOLL-Zahlen steigen mit diesem Update einmalig um rund 2 %.** eedc nutzt jetzt den neueren PVGIS-Strahlungsdatensatz (SARAH3 mit den Messjahren 2005–2023 statt SARAH2 mit 2005–2020). Deine bestehende Prognose wird dafür einmal automatisch neu abgerufen. Sichtbar wird das in *Auswertungen → Prognose vs. IST*, im Monatsbericht und beim Performance-Ratio-Hinweis des Daten-Checkers. Deine gemessenen Erträge ändern sich dadurch **nicht** — nur die Erwartung, gegen die sie gehalten werden.

### Zeigte deine Ost- oder West-Anlage dauerhaft zu wenig Ertrag?

Dann lag das womöglich an uns. Wenn die Ausrichtung deiner Module nur als **Wort** gespeichert war („Ost", „West", „Südwest" …) und nicht zusätzlich als Gradzahl, hat eedc sie beim Prognose-Abruf falsch übersetzt: **Ost, West und alle Zwischenrichtungen wurden wie Süd gerechnet**, Nord wie Ost. Deine Anlage wurde damit an einer Süd-Erwartung gemessen, die sie gar nicht erfüllen kann.

Betroffen waren vor allem **ältere Bestände und wiederhergestellte Sicherungen**. Wer seine Komponenten im heutigen Formular gespeichert hat, hatte die Gradzahl hinterlegt — bei ihm stimmte die Prognose. Der Fehler ist behoben, und betroffene Prognosen werden durch die neue nächtliche Prüfung automatisch nachgezogen.

### Ein PV-Zähler für die ganze Anlage reicht jetzt auch für die Tagessicht

Wenn deine PV **nur** über den Anlagen-Zählerstand gepflegt ist (*Einstellungen → Datenquellen → Anlage (Basis) → PV-Erzeugung Zählerstand*) — typisch, wenn dein Wechselrichter nur eine Summe über mehrere Dachseiten liefert —, stimmten bisher nur deine **Monatswerte**. In *Cockpit → Tag* stand `0 kWh` PV neben deiner gemessenen Einspeisung, und daraus wurde ein **negativer Eigenverbrauch**, eine Performance Ratio von 0 % und eine negative CO₂-Einsparung.

Jetzt versorgt dieser eine Zähler **Monat, Tag und Stunde** — als Summe deiner ganzen Anlage. Tagesbilanz, Eigenverbrauch, spezifischer Ertrag, Performance Ratio, CO₂ und der Stundenverlauf füllen sich, **auch rückwirkend** und ohne dass du etwas einrichten musst.

**Was der eine Zähler nicht kann, ist die Aufschlüsselung je Dachseite.** Dafür braucht jeder Erzeuger einen eigenen Zähler — und dann **alle**: Sobald ein einziger selbst misst, zählt für Tag und Stunde nur noch, was je Erzeuger gemessen ist, und der Anlagenwert ist dort aus. Sonst würde die Anlagensumme neben ihren eigenen Bestandteilen stehen und alles doppelt gezählt. **Entweder alle oder keiner** — deine Monatswerte bleiben in jedem Fall vollständig. Machst du es halb, sagt es dir die Datenquellen-Seite.

**Was du tun kannst, wenn dein Wechselrichter je String nur Leistung liefert:** In Home Assistant unter *Helfer → Helfer erstellen → „Integral-Sensor"* (Riemannsche Summe) **für jeden** String einen kWh-Zähler bauen — Methode **„Linke Riemann-Summe"**, **maximales Teilintervall 1 Minute**, Präfix **k**, Zeiteinheit **Stunden**, kein Zyklus — und diese beim jeweiligen Erzeuger zuordnen. Beachte: Ein neuer Helfer **beginnt bei null**, Tageswerte entstehen ab dem Anlegen; für die Vergangenheit bleibt der Anlagen-Zählerstand die bessere Quelle.

> ⚠ **Korrektur vom 08.08.2026:** An dieser Stelle stand bis dahin die Methode **Trapez** — das war falsch, und der Hinweis kam von einem Anwender im Forum. Home Assistant speichert keine Wiederholung gleicher Werte; über die Nachtlücke zieht die Trapezregel deshalb eine gerade Linie und verbucht Erzeugung, die es nie gab (gemessen: rund 60 Wh pro Nacht, proportional zum ersten Morgenwert — bei einem Wechselrichter mit gröberer Meldeschwelle entsprechend mehr). **Wer den Helfer schon mit Trapez angelegt hat**, stellt die Methode in den Helfer-Optionen um; der Zählerstand läuft weiter. Der bereits aufgelaufene Wert korrigiert sich dabei nicht rückwirkend. Ausführlich im [Handbuch Daten-Checker §5.2](HANDBUCH_DATEN_CHECKER.md#52-fehlende-kwh-zähler-in-der-datenquellen-zuordnung-ergänzen).

> ⚠ **Fasse deine Dachseiten nicht zu einer Anlage zusammen, nur um Tageswerte zu bekommen.** eedc rechnet Prognose und SOLL je Ausrichtung — eine zusammengelegte Anlage bekäme über den ganzen Tag falsche Erwartungswerte, auch in den Prognose-Sensoren für Home Assistant.

### Börsenpreis-Block: „über dem Durchschnitt" ist jetzt rot statt dunkellila

Die drei Preisstufen im Block *Börsenpreis heute & morgen* waren zwei Lila-Töne und ein Grün — und die beiden Lila-Töne unterschieden sich nur in der Helligkeit. Auf vielen Monitoren waren sie damit nicht auseinanderzuhalten, in der kleinen Legende erst recht nicht.

Jetzt liest sich die Skala von selbst: **grün** unter deiner Günstig-Schwelle, **lila** dazwischen, **rot** über dem Tagesdurchschnitt. An den Zahlen ändert sich nichts — nur an ihrer Farbe.

Danke an *Radiocarbonat*, der es gemeldet hat.

### Cockpit → Tag behauptet keine PV-Zahlen mehr, die nicht gemessen sind

Hat eine Anlage **gar keinen** kumulativen PV-Zähler — weder je Erzeuger noch für die Anlage —, steht in der Tagessicht jetzt „—" statt einer 0: nicht gemessen ist nicht dasselbe wie null. **Eine echte Null bleibt sichtbar** — eine verschneite Anlage hat 0 kWh erzeugt, und das ist eine Aussage.

---

## v4.0.10 — Jede Stunde trägt ihren eigenen Preis · jeder Tag sein eigenes Datum (August 2026)

### Börsenpreis heute *und morgen* — als eigener Block auf der Live-Seite

Bisher lief der Börsenpreis auf der Live-Seite als dünne Linie über dem Tagesverlauf mit: für **heute**, einfarbig, ohne jeden Hinweis darauf, welche Stunde eigentlich die günstige ist. Wer wissen wollte, wann morgen der billige Block liegt, musste dafür zu seinem Stromanbieter wechseln.

Jetzt gibt es dafür einen **eigenen Block: „Börsenpreis heute & morgen"**. Er zeigt beide Tage auf **einer durchgehenden Zeitachse**, und die Linie ist **nach Preisniveau eingefärbt** — grün, wo der Strom unter deiner Günstig-Schwelle liegt, und zusätzlich mit einer hinterlegten Fläche, damit die günstigen Blöcke schon aus dem Augenwinkel zu erkennen sind.

Darüber stehen drei Zahlen für heute: der **aktuelle Preis**, der **Durchschnitt ohne die drei teuersten Stunden** und deine **Günstig-Schwelle** samt der Anzahl von Stunden, die heute darunter liegen. Es sind dieselben Zahlen, die auch als Sensoren in Home Assistant ankommen — der Block und deine Automation sprechen also über dasselbe.

**Was du wissen solltest:**

- Die Preise für morgen gibt die Auktion erst **gegen 13 Uhr** frei. Vorher siehst du nur heute — und darunter steht, warum.
- **Jeder Tag hat seine eigene Schwelle.** Ein gemeinsamer Durchschnitt über beide Tage hätte an einem teuren Tag gar keine günstige Stunde ausgewiesen.
- Es sind **Börsenpreise, netto** — ohne Steuern, Abgaben und Netzentgelte. Dein Lieferant rechnet andere Beträge ab; für die Frage, *welche* Stunde die günstige ist, zählt der Verlauf.
- Der Block braucht **keine eingerichteten Sensoren**. Er erscheint auch, wenn die Live-Seite sonst noch „Keine Live-Daten verfügbar" meldet — nur die Koordinaten deiner Anlage müssen gepflegt sein.
- Die **Günstig-Schwelle** stellst du selbst ein (Standard: 10 % unter dem Durchschnitt). ⚠ **0 % schaltet sie nicht ab**, sondern legt sie genau auf den Durchschnitt.

> eedc zeigt dir die Preise — **was du damit machst, bleibt deine Entscheidung**. Ladefenster, Entlade-Sperren und Batterie-Strategien baust du weiterhin selbst in Home Assistant.

### Cockpit → Tag zeigt den Ladezustand des Speichers

Im Speicher-Block der Tagessicht standen bisher Ladung, Entladung, Wirkungsgrad und Vollzyklen — aber nicht der **Ladezustand**. Den gab es nur, wenn man ihn sich in der Stundenwerte-Tabelle als Spalte „SoC" einblendete.

Jetzt steht er als eigene Kachel im Block: der Stand am **Ende** des Tages, darunter die **Spanne**, zwischen der der Speicher an diesem Tag geschwungen ist — also etwa „64 %, Spanne 12–98 %". Am laufenden Tag ist „Ende" die zuletzt aufgezeichnete Stunde; fehlen die letzten Stunden noch, wird daraus **kein** Ladestand von 0 % gemacht.

Den Ladezustand gibt es bewusst **nur in der Tagessicht**: Er ist ein Bestand, kein Fluss. Über einen Monat gemittelt ergäbe er keine sinnvolle Aussage, deshalb taucht er in *Monat* und *Jahr* nicht auf.

> **Der Block ist eingeklappt** und steht unter den Kennzahlen. Seine Kopfzeile nennt schon ohne Aufklappen geladene kWh, Vollzyklen und Wirkungsgrad. *(Anregung aus dem Forum-Thread zu v4.0.0)*

### Cockpit → Monat geht auf dem laufenden Monat auf

Bisher stand beim Aufschlagen der Monats-Sicht immer der neueste Monat da, für den es einen gepflegten Abschluss gibt — bei laufender Pflege also der **Vormonat**. Wer wissen wollte, wie der aktuelle Monat steht, musste ihn jedes Mal selbst in der Monatsleiste anklicken. *Cockpit → Tag* und *Cockpit → Jahr* öffnen längst auf dem Aktuellen; die Monats-Sicht war die Ausnahme.

Jetzt öffnet auch sie den **laufenden** Monat — mit einer Einschränkung, und die ist Absicht:

- **Ist noch ein Monatsabschluss offen**, bleibt alles beim Alten: die Sicht geht auf dem jüngsten Monat auf, für den Werte gepflegt sind. Dort beginnt der Weg zum offenen Abschluss, und der Knopf „Abschluss starten" steht direkt daneben. Es wäre wenig hilfreich, in den laufenden Monat zu springen und den offenen Abschluss aus dem Blick zu verlieren.
- **In einen Monat nach dem laufenden** springt die Sicht nie.

Bei der Gelegenheit wurde die Frage „ist überhaupt noch etwas offen?" richtiggestellt: Sie hieß in dieser Sicht bisher „ist der jüngste gepflegte Monat älter als der Vormonat?" — ein **fehlender Monat mitten in der Historie** fiel damit durch, obwohl der Hinweis unten in der Statusleiste ihn längst nennt. Beide antworten jetzt gleich. Merken wirst du das nur, wenn du eine solche Lücke hast: dann steht der Knopf „Abschluss starten" da, wo er vorher fehlte.

> Über die Monatsleiste erreichst du weiterhin jeden Monat; ein Direktsprung aus *Cockpit → Jahr* landet unverändert auf dem angeklickten Monat. *(coolxmad, [#353](https://github.com/supernova1963/eedc-homeassistant/issues/353))*

### Die Börsenpreise der Nachtstunden gehörten dem falschen Tag — behoben

Wenn du dir auf der Live-Seite den Tagesverlauf mit der Strompreis-Linie angesehen hast, ist dir vielleicht aufgefallen, dass die Preislinie erst **um 2 Uhr** beginnt. Und wer nachts genauer hingeschaut hat, sah dort ab dem frühen Nachmittag Zahlen stehen, die gar nicht zu diesem Tag gehörten — es waren die des **nächsten** Tages.

**Woran es lag:** eedc holt die Börsenpreise stundenweise ab und hat dabei einen Tag angefragt, der von Mitternacht bis Mitternacht **UTC** läuft — also von 2 Uhr bis 2 Uhr deiner Zeit. Die Antwort hat es aber nach deiner Uhr einsortiert. Die ersten ein bis zwei Stunden des Tages fielen damit heraus, und ihre Plätze belegten die ersten Stunden von morgen. Weil am Ende trotzdem 24 Werte dastanden, sah alles vollständig aus.

**Das betraf mehr als die Anzeige.** Auf derselben Preisreihe stehen die HA-Sensoren für Preis-Rang, günstige Stunden, aktuellen Preis und Abstand zum Durchschnitt — und die stündliche Mitschrift, aus der später der Tagesdurchschnitt und der effektive Ladepreis deines Speichers entstehen.

**Jetzt gilt: ein Tag ist der Tag der Strommarkt-Zeitzone.** Abfrage und Zuordnung kommen aus derselben Uhr — unabhängig davon, in welcher Zeitzone dein Container läuft. Auch die beiden Umstellungstage stimmen: Ende März hat der Tag 23 Stundenpreise, Ende Oktober behält er die erste seiner beiden Zwei-Uhr-Stunden.

⚠ **Was sich an deinen Sensorwerten ändert:** Rang, Anzahl günstiger Stunden, aktueller Preis und Abstand zum Durchschnitt rechnen ab jetzt mit den richtigen Nachtpreisen. Da Durchschnitt und Günstig-Schwelle über alle Stunden eines Tages gebildet werden, kann sich dadurch auch die Bewertung einzelner Tagesstunden verschieben. Wer nachts zwischen 0 und 2 Uhr auf den aktuellen Preis reagiert, bekommt jetzt den Preis der Stunde, in der er tatsächlich ist.

**Schon gespeicherte Tage bleiben, wie sie sind.** eedc fasst deine Historie nicht von selbst an. Wenn du sie berichtigen möchtest, rechne die betroffenen Tage unter *Einstellungen → Daten* mit **„Mehrere Tage neu aggregieren"** neu (in Schüben zu je höchstens 31 Tagen).

### Meine Tageswerte fangen erst bei der Installation an — jetzt holt eedc die Historie selbst

Wenn du eedc als eigenen Container betreibst und über einen Long-Lived-Token mit Home Assistant verbunden bist, gab es bisher eine unsichtbare Grenze: eedc kam **nicht** an die Langzeitstatistik von HA. Tageswerte baute es sich deshalb nur aus eigenen Messungen im 5-Minuten-Takt — also ab dem Tag der Installation vorwärts. *Cockpit → Tag* blieb für alles davor leer, der Voll-Backfill war gesperrt, und „Lücken aus HA-LTS nachfüllen" in der Reparatur-Werkbank ging nicht.

Der bisherige Rat war, das HA-Konfigurationsverzeichnis in den eedc-Container einzuhängen. Das setzt aber voraus, dass beide auf **demselben Rechner** laufen und HA gerade läuft — und wer MariaDB als Recorder nutzt, kam damit gar nicht weiter.

**Jetzt holt eedc die Statistik über dieselbe Verbindung, über die es ohnehin schon die aktuellen Sensorwerte liest.** Du musst dafür nichts einrichten: Ist deine HA-Verbindung eingetragen, ist die Historie da. Läuft eedc als Add-on oder hast du die Datenbank eingehängt, bleibt alles wie bisher — dieser Weg ist etwas schneller und wird weiter bevorzugt.

**An deinen Zahlen ändert sich nichts.** Es sind dieselben Werte aus derselben Statistik, nur anders abgeholt; wir haben beide Wege an einer echten Anlage nebeneinander gemessen und keinen einzigen Unterschied gefunden.

**Ein Punkt bleibt:** Weiter zurück als Home Assistant selbst kann auch dieser Weg nicht. Die Langzeitstatistik beginnt, wenn du den Sensor einrichtest. Für die Jahre davor ist der Datei-Import (CSV/Excel) der richtige Weg.

### Läuft eedc in einer anderen Zeitzone als Home Assistant? Der Daten-Checker sagt es dir

Ein Docker-Container läuft auf **UTC**, wenn man ihm nichts anderes sagt — egal, wie der Rechner eingestellt ist. Für eedc heißt das: Der Tag endet um 22:00 statt um Mitternacht, und die letzten beiden Stunden landen im nächsten Tag. Das betrifft alle Tageswerte, von *Cockpit → Tag* bis zum Tagesabschluss.

Das Tückische daran: Man sieht es nicht. Die Zahlen wirken plausibel, sie stehen nur am falschen Tag.

**Der Daten-Checker prüft das jetzt** und meldet eine Abweichung unter *Zeitzone – Abweichung zu Home Assistant*. Er vergleicht dabei den Zeitabstand, nicht den Namen der Zeitzone — wer in Wien oder Zürich wohnt, bekommt keine Meldung, obwohl seine Zeitzone anders heißt als Berlin.

Was zu tun ist, steht im Befund: **Als Add-on** übernimmt eedc die Zeitzone von Home Assistant, ein Neustart des Add-ons genügt. **Im eigenen Container** setzt du `TZ=Europe/Berlin` (bzw. deine Zeitzone) und startest ihn neu — in der mitgelieferten `docker-compose.yml` ist das bereits eingetragen. Ohne Home-Assistant-Verbindung meldet sich die Prüfung nicht: Dann gibt es nichts zu vergleichen.

Bereits gespeicherte Tage repariert das nicht von selbst — die kannst du danach über *Einstellungen → Datenverwaltung* neu berechnen lassen.

### Nachts zeigte eedc den falschen Tag — behoben

Wer zwischen Mitternacht und 2 Uhr in den **Prognosen-Vergleich** geschaut hat, sah dort zwei Kalendertage mit **exakt denselben Zahlen** — in allen drei Spalten, OpenMeteo, eedc und Solcast. Die Zeile für „heute" trug das Datum von gestern, aber die Werte von heute, und der heutige Tag stand daneben gleich noch einmal.

**Woran es lag:** Der Browser hat das Datum in der Weltzeit UTC gebildet statt in deiner Zeitzone. In Mitteleuropa ist das zwischen 00:00 und 02:00 Uhr (im Winter 00:00–01:00) noch der Vortag — während eedc im Hintergrund längst mit dem neuen Tag rechnet. Ab 2 Uhr stimmten beide wieder überein, und tagsüber war nichts zu sehen. Genau deshalb hat es so lange gedauert, das zu finden.

**Es betraf mehr als diese eine Ansicht.** In demselben Zeitfenster:

- Der Knopf **„Tag neu berechnen"** hat *gestern* neu berechnet — und die Rückmeldung „0 von 24 Stunden mit Daten" bezog sich dann auf den falschen Tag.
- Die **Tagesleiste** markierte den Vortag als „heute".
- **Cockpit → Tag** öffnete auf gestern.
- Eine Komponente, die du **zum heutigen Tag stillgelegt** hast, galt noch als aktiv.
- Ein **Stromtarif, der heute beginnt**, galt noch nicht — der abgelöste noch.

Alle zehn Stellen rechnen jetzt mit deiner lokalen Uhr, über eine gemeinsame Funktion. Ein neuer Prüflauf in unserem Entwicklungs-Werkzeug sorgt dafür, dass die nächste Stelle diesen Fehler nicht wiederholen kann.

> **Danke fürs Dranbleiben.** Der Fehler ist zweimal gemeldet worden — beim ersten Mal haben wir ihn für einen harmlosen Zufall gehalten. Erst die Screenshots aus der Nacht haben gezeigt, dass es keiner war.

### Börsenpreis: „ist der Strom gerade teurer als der Tagesschnitt?" ist jetzt ein Sensor

Wer eine Batterie an einem dynamischen Tarif fährt, will oft genau eine Auskunft: **liegt der Preis dieser Stunde über oder unter dem Tagesdurchschnitt?** Nur entladen, wenn Strom teuer ist, und billige Stunden zum Nachladen nehmen — das spart die Verluste des Umwegs über die Batterie.

Diese Auskunft gab eedc bisher nicht heraus. Der Export lieferte nur die fertige Bewertung: den Rang der laufenden Stunde und die Anzahl günstiger Stunden. Der **Preis selbst** und der **optimierte Durchschnitt**, auf den sich die Günstig-Schwelle bezieht, blieben drinnen — obwohl eedc beide längst ausrechnet.

**Drei neue Sensoren liefern sie jetzt:**

| Sensor | Was er sagt |
|---|---|
| *Börsenpreis aktuell* | Der Day-Ahead-Preis dieser Stunde in ct/kWh |
| *Börsenpreis Ø ohne Peaks* | Der Tagesdurchschnitt ohne die 3 teuersten Stunden — die Bezugsgröße der Günstig-Schwelle |
| *Börsenpreis-Abstand zum Ø* | Wie weit der aktuelle Preis davon entfernt ist: **negativ = billiger**, positiv = teurer |

Damit ist „nur entladen, wenn der Strom teurer ist als der Schnitt" eine Bedingung auf einen Zahlenwert (`> 0`) — kein Template nötig. Und wer feiner steuern will, staffelt nach der Stärke: erst ab +20 % entladen, unter −20 % nachladen.

Dazu trägt das Rang-Profil am Sensor *Börsenpreis-Rang* jetzt auch die **Stundenpreise** selbst. Bisher stand dort je Stunde nur ein Rang — eine eigene Schwelle oder ein eigenes Zeitfenster ließ sich daraus nicht rechnen, obwohl die Sensor-Referenz das anbot.

> **eedc gibt weiterhin keine Lade-Strategie vor.** Es liefert die Werte, auf die deine Automation hört — was damit geschieht, entscheidest du.

### ⚠ „Günstige Stunden" zählt jetzt richtig — bitte einmal deine Automationen prüfen

Die Sensoren *Günstige Stunden*, *… Tag* und *… Nacht* waren bei **5 je Fenster gedeckelt**. Lagen sieben Nachtstunden unter der Günstig-Schwelle, meldeten sie trotzdem fünf.

Als Anzeige ging das durch. Als **Divisor** nicht: Wer seine Ladeleistung aus „Energiemenge ÷ günstige Stunden" rechnet, bekam einen zu kleinen Nenner und damit eine zu hohe Leistung.

**Ab jetzt zählen die drei Sensoren, was ihr Name sagt** — jede Stunde unter der Schwelle. Der Sensor *Börsenpreis-Rang* bleibt unverändert bei 1–5 bzw. 99, denn er beantwortet eine andere Frage („gehört diese Stunde zu den fünf billigsten ihres Fensters?").

**Was du tun solltest:** Wenn du einen der drei Zähler in einer Automation verwendest, sieh dir deine Schwellenwerte einmal an. Im Verlauf in Home Assistant wirst du an der Umstellung einen einmaligen Sprung nach oben sehen — das ist die Korrektur, kein Messfehler.

Nebenbei richtiggestellt: Bei einer Günstig-Schwelle von **0 %** stand in der Oberfläche „schaltet die Schwelle ab, dann zählen wieder die 5 günstigsten". Das hat eedc nie getan — bei 0 % liegt die Schwelle **genau auf** dem Tagesdurchschnitt, günstig ist alles darunter. Der alte Deckel hat den Unterschied verdeckt.

### Deye/Solarman-Import: jetzt geht er wirklich

Mit v4.0.9 hatten wir zwei Ursachen behoben, an denen der Deye/Solarman-Cloud-Import scheiterte — die fehlende Auswahl der Server-Region und einen falsch aufgebauten Autorisierungs-Kopf. Beides war richtig, und der Import ging trotzdem nicht.

Der Melder hat daraufhin den Anmelde-Aufruf selbst gegen Solarman gefahren und uns die Antwort danebengelegt. Damit war die Sache klar: **Die Anmeldung klappt, eedc hat den Zugriffsschlüssel in der Antwort nur an der falschen Stelle gesucht** — eine Ebene zu tief. Herausgekommen ist die Meldung „Antwort enthielt keinen access_token", obwohl er sehr wohl da war.

Und weil dieser Schlüssel für jeden weiteren Aufruf gebraucht wird, konnten auch die beiden Korrekturen aus v4.0.9 nie greifen. Sie waren nicht falsch — sie kamen nie an die Reihe.

**Wenn du Deye/Solarman nutzt:** Trag deine Zugangsdaten wie gewohnt ein und starte den Verbindungstest neu. Änderungen an deiner Konfiguration sind nicht nötig.

### Live-Verlauf, Solcast und der kW/kWh-Test waren im Container stumm

Fünf Funktionen waren fest an den Add-on-Betrieb gebunden und meldeten sich bei einer Token-Verbindung einfach als „nicht verfügbar", obwohl die Verbindung stand: der **Live-Tagesverlauf**, die **Solcast-Anbindung**, die Prognose-Erkennung, die **Ladestands-Historie deines Speichers** und die Prüfung des Daten-Checkers auf **vertauschte Leistungs- und Energie-Sensoren**.

Der letzte Punkt war der ärgerlichste: Genau die Verwechslung, kW statt kWh zuzuordnen, wurde ausgerechnet dort nicht geprüft, wo sie am häufigsten passiert. Alle fünf arbeiten jetzt auch mit einer Remote-Verbindung.

### „Die TagesZusammenfassung vom ? aus unbekannt" — diese Meldung gibt es nicht mehr

Wer eedc frisch eingerichtet hatte, bekam im Daten-Checker einen Hinweis mit **Fragezeichen und „unbekannt"** darin. Er war für einen anderen Zustand gedacht — nämlich dafür, dass schon aggregierte Tage noch aus einer älteren Quelle stammen. Wenn es überhaupt noch **keine** Tageswerte gab, passte er nicht und schickte dich auf die Suche nach einer falschen Datenquelle.

Jetzt steht dort **„Noch keine Tageswerte aggregiert"** — mit dem, was tatsächlich hilft: kurz abwarten (die Aggregation läuft stündlich), die **kWh-Zeilen** unter *Einstellungen → Datenquellen* belegen (nicht nur die Watt-Zeilen), oder zurückliegende Tage über *„Lücken aus HA-LTS nachfüllen"* in der Reparatur-Werkbank holen.

### Meine Monatsleiste zeigte nur den laufenden Monat — jetzt stehen alle drin

Wer eedc mit **Monatsabschlüssen oder importierter Historie** pflegt und keine Tagesdaten aus Home Assistant hat, bekam in *Cockpit → Monat* links nur einen einzigen Eintrag angeboten: den laufenden Monat. Die Sicht daneben zeigte trotzdem einen abgeschlossenen Monat mit allen Werten — der Monat, den man gerade ansah, war in seiner eigenen Auswahlliste nicht zu finden.

Grund war, dass die Leiste ihre Liste aus einer **anderen Quelle** las als die Sicht: sie kannte nur Monate mit **Tagesdaten**, nicht deine gepflegten **Monatsdaten**. Jetzt liest sie beides und zeigt alles, was es gibt — egal ob ein Monat aus dem Monatsabschluss, aus einem Import oder ausschließlich aus Tageswerten stammt.

**An deinen Zahlen ändert sich nichts**, nur die Auswahl ist vollständig. Und der Umweg über *Auswertungen → Tabelle*, um ältere Monate überhaupt zu erreichen, entfällt.

*Gemeldet von kaba-kakao im Forum.*

### „Keine Daten für diesen Tag" — jetzt steht dabei, warum

In *Cockpit → Tag* stand für einen Tag ohne Werte ein einziger Satz: „Für diesen Tag liegen keine Daten vor. Wähle einen Tag mit Messwerten." Das half nicht weiter — und klang so, als hättest du dich beim Tag vertan. Meistens hattest du das nicht: Die Datumsauswahl gibt schon ab dem ersten Tag deines ältesten Monats frei, deine Tageswerte fangen aber oft später an. An einer echten Anlage sind das 30 Tage, die sich anwählen lassen und immer leer bleiben.

**Jetzt sagt die Sicht, was los ist** — je nach Fall: Der Tag liegt **vor der Inbetriebnahme** deiner Anlage · an ihm war **kein kWh-Zähler zugeordnet** · der Tag **wurde nie ausgewertet, Home Assistant hat die Werte aber noch** · **auch Home Assistant hat für diesen Tag nichts** · der Tag **läuft noch**.

**Der Knopf „Tag nachrechnen" erscheint nur da, wo er auch etwas holt** — also im dritten Fall. Liegt der Tag vor deiner Inbetriebnahme oder hat Home Assistant selbst nichts aufgezeichnet, gibt es nichts nachzurechnen; dann steht das offen da, statt dir einen Knopf hinzustellen, der nichts bewirkt. Fehlt eine Zuordnung, führt der Weg direkt zu *Einstellungen → Datenquellen*.

Kleiner Nebeneffekt: Hast du in der Tagessicht **alle** Anzeigen geparkt, stand dort ebenfalls „Keine Daten für diesen Tag" — obwohl die Daten da sind und nur im Papierkorb liegen. Auch das sagt eedc jetzt richtig.

---

## v4.0.9 — Der laufende Monat zählt nur seine Tage · jede PV-Zahl nennt ihre Herkunft (August 2026)

### Wo kann ich die Kopplung meines Speichers einstellen? Ab jetzt: in der Investitionspflege

**Betrifft dich das?** Alle mit einem **Batteriespeicher**, besonders wenn er **AC-gekoppelt an
einem Hybrid-Wechselrichter** hängt oder **DC-gekoppelt ohne** dass du den Wechselrichter als
eigene Komponente erfasst hast.

Bis hierher hat eedc die Kopplung nicht *gewusst*, sondern *geraten* — und zwar an genau einer
Angabe: Ist dem Speicher ein Wechselrichter zugeordnet? Dann DC. Sonst AC. Für die meisten Anlagen
trifft das zu; für zwei ganz normale Bauformen nicht:

- **AC-Speicher am Hybrid-Wechselrichter** — sobald du ihn zuordnest, galt er als DC-gekoppelt.
- **DC-Speicher ohne erfassten Wechselrichter** — er galt als AC-gekoppelt.

**Was neu ist:** In *Einstellungen → Investitionen → Speicher bearbeiten* steht das Feld
**„Kopplung"** mit drei Möglichkeiten:

| Auswahl | Bedeutung |
| --- | --- |
| **Automatisch (aus der Zuordnung)** | Vorbelegung — eedc leitet ab wie bisher und schreibt dir dazu, **was** dabei herauskommt |
| **AC-gekoppelt** | Der Speicher hat einen eigenen Batterie-Wechselrichter |
| **DC-gekoppelt** | Der Speicher hängt gleichstromseitig am (Hybrid-)Wechselrichter |

Im **Komponenten-Hub** steht die Kopplung als eigene Zeile neben der Zuordnung — und wenn du nichts
gepflegt hast, sagt sie das auch, statt eine Angabe zu behaupten.

**Ändert das meine Zahlen?** Nein, und das ist Absicht. Ob dein Speicher in der Wirtschaftlichkeit
**als Teil des PV-Systems** oder **eigenständig** gerechnet wird, entscheidet weiterhin allein die
**Zuordnung** zum Wechselrichter — die Ersparnis selbst rechnet eedc für beide Bauformen gleich.
Du kannst einen AC-Speicher also korrekt eintragen, **ohne** dass er aus deinem PV-System fällt.

**Wofür die Angabe gut ist:** Sie sagt, **wo** Ladung und Entladung gemessen werden. Das stand
bisher nirgends — und deshalb waren ein Zähler direkt an der Batterie (DC) und einer hinter dem
Batterie-Wechselrichter (AC) **beide** richtig, obwohl sie verschiedene Zahlen liefern:
dazwischen liegt der Wandlungsverlust. Wer Ladung von der einen und Entladung von der anderen
Seite erfasst — bei Cloud-Werten mancher Hersteller ist das der Normalfall —, bekommt einen
Wirkungsgrad, der die Messstelle beschreibt und nicht den Speicher. Die Feldbeschreibungen von
**Ladung** und **Entladung** nennen die Messstelle jetzt und verlangen für beide **dieselbe Seite**.

*(#351 — gemeldet von JayJay im Forum-Thread zu v4.0.0)*

### Ein gerechneter PV-Wert gibt sich nicht mehr als Messung aus

**Betrifft dich das?** Alle mit **mehreren PV-Strings oder mehreren Speichern**, die ihre
Monatswerte über einen **Import** (CSV-Backup, Portal, eigener Import) oder über den
**Monatsabschluss mit Geräte-Connector bzw. Cloud-Import** pflegen.

Hat eedc für einen Monat nur den **Gesamtwert** der Anlage, teilt es ihn nach Nennleistung auf die
Strings auf — beim Anzeigen, gekennzeichnet als „geschätzt (kWp-Anteil)". Das ist so gewollt.
Zwei Wege haben eine solche Aufteilung aber **gespeichert**, und danach war sie von einer echten
Messung nicht mehr zu unterscheiden.

**Was das anrichtete:**

- Die String-Sichten kürten einen **„besten" und einen „schwächsten String"** — aus Zahlen, die
  rechnerisch immer im Verhältnis der Nennleistung stehen. Die Rangfolge sagte also nichts über
  die Dächer aus. Die Sperre, die genau das verhindern soll, sah keinen Grund einzugreifen.
- Der **Daten-Checker meldete den Monat grün** („PV-Erzeugung vollständig gemessen"), obwohl kein
  einziger String gemessen hatte.

Bei ungleich ausgerichteten oder verschatteten Dächern liegt so eine Aufteilung schnell zweistellig
neben der Wirklichkeit — und wanderte unmarkiert in Auswertungen, Berichte und den
Community-Vergleich.

**Jetzt** merkt sich eedc am Wert, dass er gerechnet ist. Die Anzeige stuft ihn als **verteilt**
ein: kein Ranking, Kennzeichnung „geschätzt (kWp-Anteil)", und der Daten-Checker sagt „über
kWp-Anteil geschätzt" statt „vollständig gemessen".

**Was sich nicht ändert:**

- **Die Zahl bleibt, wie sie ist** — es geht um ihre Herkunft, nicht um ihren Wert.
- Wer **einen** String bzw. **einen** Speicher hat, merkt nichts: dort geht der Gesamtwert
  unverzerrt an ein Gerät, und das ist eine Messung.
- **Rückwirkend** lässt sich das nicht heilen: bei bereits gespeicherten Werten steht dieselbe
  Herkunft für „echt gemessen" und „verteilt", die beiden sind nachträglich nicht trennbar. Die
  Kennzeichnung greift ab dem nächsten Import bzw. Monatsabschluss.

Dasselbe gilt für **Speicher**, deren Lade- und Entladewerte nach Kapazität aufgeteilt werden.

---

### Solarman-Cloud-Import: die Server-Region ist wählbar — und Fehler sagen, was los ist

**Betrifft dich das?** Alle mit einem **Deye**-Wechselrichter, die historische Monatsdaten über
den **Solarman**-Cloud-Import holen wollen.

Solarman betreibt **zwei getrennte Wolken**: eine chinesische und eine internationale. Wer sich
unter `globalhome.solarmanpv.com` anmeldet, hat sein Konto auf der internationalen — und genau die
hat eedc bisher nie gefragt. Die Adresse stand fest im Code, und zwar auf der chinesischen Seite;
ein europäisches Konto existiert dort schlicht nicht, der Verbindungstest brach ab. **Olli
(OliS2811) hat das gemeldet und die Ursache gleich mitgeliefert.**

Jetzt gibt es im Cloud-Import ein Feld **„Server-Region"** mit „Global / Europa" (Vorauswahl) und
„China" — dasselbe Feld, das Anker, EcoFlow, Sungrow und Huawei längst haben.

**Zwei Dinge kamen beim Nachmessen dazu:**

- Der **Anmelde-Nachweis** ging in einer Form raus, die Solarman nicht akzeptiert (ein fehlendes
  Schlüsselwort im Kopf der Anfrage). Der Zugang wurde also korrekt geholt und jeder Abruf danach
  trotzdem abgelehnt — **auf beiden Regionen**. Wer den Solarman-Import bisher erfolglos versucht
  hat, war nicht falsch eingerichtet.
- **Fehlermeldungen nennen jetzt den Grund.** Bisher stand bei jedem Problem derselbe Satz
  („Bitte appId, appSecret, E-Mail und Passwort prüfen"), egal ob der Server nicht erreichbar war,
  die Anlagen-ID nicht passte oder das Konto auf der anderen Region lag. Jetzt steht die Antwort
  von Solarman im Klartext dabei, samt angesprochener Adresse — und bricht ein Import ab, bevor
  ein einziger Monat geholt ist, sagt er das, statt „keine Daten gefunden" zu melden.

**Noch nicht mit einem echten Konto bestätigt** — der Provider bleibt als „ungetestet"
gekennzeichnet, bis eine erfolgreiche Einrichtung zurückgemeldet ist.

→ [Einstellungen-Handbuch](HANDBUCH_EINSTELLUNGEN.md) · *(#349)*

### Solcast: der Verlauf für morgen ist der von morgen

**Betrifft dich das?** Alle, die **Solcast** als Prognosequelle nutzen — über die HA-Integration
oder mit eigenem API-Key.

Die **Tagesmengen** von Solcast stimmten immer. Was fehlte, war die **Form** des Tages: Der
Stundenverlauf für morgen (*Cockpit → Aussicht*) war in Wahrheit der von **heute**, hochgerechnet
auf die morgige Tagesmenge. Ein Tag mit Nebel am Morgen und Sonne am Nachmittag sah damit aus wie
der Vortag — nur höher oder flacher. eedc hat das nie behauptet zu wissen (ein Hinweis stand
darunter), nötig war es aber auch nicht: **Rainer hat belegt**, dass die HA-Integration für morgen
ein **eigenes** Detailprofil mitliefert, und der API-Zugang liefert ohnehin sieben Tage am Stück.

Jetzt bekommt **jeder Tag, für den Solcast Stundenwerte liefert, seinen eigenen Verlauf**. Wo die
Quelle nur die Tagesmenge kennt (je nach Integration die weiter entfernten Tage), bleibt es bei der
Näherung — und der Hinweis steht dann auch nur noch **dort**. Ein zusätzlicher Abruf entsteht
nicht; die Daten waren schon in der Antwort.

Zweite sichtbare Stelle: In *Auswertungen → Prognose* stammen die **Vormittag/Nachmittag**-Werte
der Solcast-Spalte für morgen jetzt aus Solcast selbst. Vorher wurden sie aus der
**OpenMeteo**-Verteilung geschätzt — die Solcast-Spalte trug an dieser Stelle also die Form einer
anderen Quelle.

→ [Prognosen-Handbuch](HANDBUCH_PROGNOSEN.md) · *(#357)*

### Prognosen-Vergleich auf dem Handy: Karten statt „bitte Desktop verwenden"

**Betrifft dich das?** Alle, die *Auswertungen → Prognose* auf dem Smartphone öffnen.

Drei der vier Tabellen dort — die Kopf-Matrix mit Heute/Morgen/Übermorgen, das
**Genauigkeits-Tracking** und der **7-Tage-Vergleich** — zeigten auf schmalen Bildschirmen **keine
Daten**, sondern die Aufforderung, das Gerät zu drehen oder einen Desktop zu benutzen. Beim Drehen
kam der nächste Hinweis: „Auflösung zu gering". Die Zahlen waren am Telefon also gar nicht
erreichbar.

Jetzt steht dort **je Tag eine Karte** mit den Quellen untereinander — dieselbe Darstellung, die
die String-Übersicht, das T-Konto und die Komponenten-Finanzen auf schmalen Bildschirmen schon
lange nutzen. **Auf dem Desktop ändert sich nichts.**

Kleinigkeit am Rande: Die relative Abweichung ist nach oben begrenzt. An einem Ausfalltag
(0,2 kWh gemessen gegen 5,0 kWh Prognose) stand dort „2400 %"; jetzt steht „> 999 %" — die
kWh-Zahl daneben sagt ohnehin, wie groß der Fehler war.

### Erträge je Dachfläche und je Balkonkraftwerk — jetzt auch tagesgenau

**Betrifft dich das?** Alle mit **mehreren** PV-Strings oder mehreren Balkonkraftwerken, bei denen
jedes Gerät einen **eigenen Ertragssensor** hat.

Monats- und Jahreswerte je String gab es schon (*Auswertungen → Prognose*, Komponenten-Hub,
Jahresbericht). Für einen **einzelnen Tag** ließ sich die Erzeugung dagegen nicht auftrennen —
obwohl eedc die Werte je Gerät stündlich mitschreibt. Rainer hat gefragt: „welchen Ertrag hat mein
BKW im Vorgarten, mein Süd-Ost-Dach, mein Nord-West-Dach **täglich** gebracht?" Zwei Stellen
beantworten das jetzt:

- ***Cockpit → Tag*** — der **Stundenverlauf** teilt die PV-Fläche in ihre Geräte auf (statt eines
  Blocks), und die **Stundenwerte**-Tabelle bekommt je Gerät eine Spalte hinter „PV".
- ***Auswertungen → Tabelle → Energieprofile*** — je Gerät eine Spalte **je Tag**, im
  Spalten-Picker unter **„Je Erzeuger"**. Mit Summenzeile, Vorjahresvergleich und CSV-Export wie
  jede andere Spalte; über einen Monat oder ein Jahr gelesen ergibt das die Tages-Historie je Dach.

Aufgeteilt wird **ab zwei Geräten** — bei einem einzigen wäre die Gerätespalte die Anlagenspalte.

**Und wenn ein Gerät keinen eigenen Sensor hat?** Dann bekommt es **keine** Spalte, sondern du
bekommst einen Hinweis, welches Gerät fehlt und wo du den Sensor zuordnest
(*Einstellungen → Datenquellen*). Auf Monatsebene füllt eedc solche Lücken notfalls nach
kWp-Anteil auf und schreibt „geschätzt" dazu — auf Tagesebene bewusst nicht: eine gerechnete Zahl
unter der Überschrift „Dach Süd" sähe aus wie eine Messung. Im Stundenverlauf steht der
ungedeckte Rest als eigene Fläche **„PV (übrige)"**, damit die Kurve weiter deine ganze Erzeugung
zeigt.

### Die String-Sicht zeigt deine Erträge auch ohne PVGIS-Prognose

**Betrifft dich das?** Alle, die *Auswertungen → Prognose* öffnen, **ohne** eine PVGIS-Prognose
abgerufen zu haben.

Bisher stand dort nur der Satz „Keine PVGIS-Prognose vorhanden" — und mit ihm verschwanden auch
alle Zahlen, die gar keine Prognose brauchen: deine **gemessenen** Erträge je String, ihr Anteil am
Gesamtertrag und der spezifische Ertrag in **kWh/kWp**, also genau die Kennzahl, mit der man zwei
Dächer vergleicht.

Jetzt steht die Sicht. Weg bleibt nur, was ohne Prognose keine Aussage hat: **SOLL, Abweichung und
Performance**. Der Hinweis bleibt oben stehen und sagt dir, wo du die Prognose abrufst
(*Einstellungen → PVGIS*). Wer eine Prognose hinterlegt hat, sieht keinen Unterschied.

### Im laufenden Monat vergleicht das SOLL nur die Tage, die schon vorbei sind

**Betrifft dich das?** Alle, die *Cockpit → Monat* oder *Cockpit → Jahr* im **laufenden** Monat
ansehen.

Die SOLL-Erfüllung setzt deinen Ertrag ins Verhältnis zu dem, was PVGIS für den Zeitraum erwartet.
PVGIS rechnet in **Monatssummen** — und die stand bisher auch dann voll im Nenner, wenn der Monat
gerade erst angefangen hatte. Am 4. August sah das an Gernots Anlage so aus:

| | zeigte | tatsächlich |
| --- | --- | --- |
| Cockpit → Monat (August) | **19 %** | 148 % — 264,8 kWh gegen die 179,1 kWh, die bis zum 4. zu erwarten waren |
| Cockpit → Jahr | **104 %** | 120 % — dieselbe Anlage kommt über Jan–Jul auf 119 % |

Am Monatsersten stand dort also praktisch eine Null für eine völlig gesunde Anlage — und in der
Jahres-Kachel zog der volle August-Nenner das ganze Jahr nach unten.

Ab jetzt zählt das SOLL im laufenden Monat nur die **abgelaufenen Tage**. Damit du die kleinere
kWh-Zahl richtig liest, schreibt eedc das Fenster dazu: **„anteilig · 4 von 31 Tagen"** — im
Tooltip der PV-Kachel und in der Kopfzeile des Bilanz-Blocks. Mit dem Monatsabschluss steht dort
wieder der volle Monat.

**Was sich nicht ändert:** abgeschlossene Monate, deine Historie und jedes Jahr, das nicht mehr
läuft. Dort waren Zähler und Nenner ohnehin deckungsgleich. Neu ist außerdem, dass ein Monat in
der **Zukunft** gar keine Erfüllungsquote mehr zeigt statt 0 % — er hat noch nicht stattgefunden.

### Überbelegung ist normal — und dein SOLL weiß das jetzt

**Betrifft dich das?** Alle, die **mehr Modulleistung als Wechselrichter-Leistung** installiert
haben — beim Balkonkraftwerk fast immer, auf dem Dach sehr häufig.

Mehr kWp Module an einen kleineren Wechselrichter zu hängen ist kein Fehler, sondern gängige
Auslegung: Du tauschst Ertrag in der Mittagsspitze gegen Ertrag am Morgen und am Abend. Die
PVGIS-Prognose rechnete bisher aber nur aus der **Modulleistung** und wusste von der Grenze deines
Geräts nichts. Was der Wechselrichter mittags abriegelt, stand trotzdem in deinem SOLL — und
tauchte im Vergleich mit dem IST als Minus auf, für das du nichts konntest.

Ab jetzt kappt eedc das SOLL **stündlich** an der Grenze deines Wechselrichters, so wie es die
Tagesprognose beim Balkonkraftwerk schon seit v4.0.4 tut. Die Grenze steht längst in deinen Daten:
beim Wechselrichter im Feld **„Max. Leistung (kW)"**.

**Wichtig, wenn mehrere Strings an einem Gerät hängen:** die Grenze gilt für ihre **Summe**, nicht
für jeden einzeln. Genau daran hing der ganze Effekt — an der Demo-Anlage (Süd 12 · Ost 5 ·
West 3 kWp an einem 10-kW-Gerät) erreicht **kein einzelner String** allein 10 kW, gemeinsam sind es
aber 1.227 kWh im Jahr, die das Gerät nie abgeben kann.

**Was du siehst:** Dein SOLL sinkt (an der Demo-Anlage −5,9 % im Jahr, im April −10 %, im Winter
gar nicht), SOLL-Erfüllung und Performance Ratio steigen entsprechend. **Deine IST-Werte ändern
sich nicht.** Hast du keine Wechselrichter-Leistung gepflegt, bleibt alles wie bisher — ohne
gepflegte Grenze kappt eedc nichts.

> ⚠️ **Du musst die Prognose einmal neu abrufen.** Deine gespeicherte PVGIS-Prognose ist ein
> Datensatz aus der Vergangenheit — eedc rechnet sie nicht nachträglich um, sonst würde sich eine
> gespeicherte Zahl still ändern. Unter *Einstellungen → Solarprognose* einmal **„Neue Prognose
> abrufen" → „Speichern & Aktivieren"**, dann trägt dein SOLL die Kappung. Deine bisherige
> Prognose bleibt in der Historie und lässt sich jederzeit wieder aktivieren.

> **Nebenbei:** Wenn du **nur ein Balkonkraftwerk** hast, bekommst du überhaupt zum ersten Mal ein
> PVGIS-SOLL. Bisher antwortete die Prognose mit „Keine PV-Module gefunden", obwohl dein BKW alles
> mitbringt, was PVGIS braucht. *(#354, #367)*
>
> **Nachtrag (August 2026):** Das galt nur für den **Jahresvergleich** gegen PVGIS. Die Blöcke
> *SOLL/IST pro PV-String* und *Mehrjahres-Performance* sowie der String-Abschnitt im
> Jahresbericht-PDF blieben leer und zeigten weiterhin „Keine PV-Module gefunden" — sie hängen an
> anderen Abfragen, die damals übersehen wurden. Ein Anwender hat das gemeldet; **behoben** im
> Abschnitt weiter oben auf dieser Seite.

### Daten-Checker: zwei Meldungen weniger, eine bessere

**Betrifft dich das?** Alle mit **Balkonkraftwerk** — und alle, die schon einmal über die Meldung
„PV-Module kWp stimmt nicht mit Anlagenleistung überein" gestolpert sind.

Diese Prüfung zählte das **Balkonkraftwerk in die Anlagenleistung** hinein. Ein BKW ist aber eine
eigene Anlage mit eigener MaStR-Registrierung und gehört dort nicht hinein — die Folge war eine
Warnung bei jedem BKW-Besitzer, ohne dass irgendetwas falsch gepflegt gewesen wäre. Und sie kannte
Überbelegung nicht, konnte dich also nur dazu bringen, falsche Zahlen einzutragen, damit Ruhe ist.

Sie ist ersetzt: eedc sieht sich jetzt das **Verhältnis von Modulleistung zu
Wechselrichter-Leistung** an und meldet erst, wenn es **mehr als das Doppelte** ist. Bis dahin ist
Überbelegung eine Entwurfsentscheidung (üblich 1,1–1,3, bei Ost/West bis etwa 1,5). Darüber ist
meist ein Tippfehler die Ursache — und die Meldung sagt dir, welcher: Steht in einem
„Leistung (kWp)"-Feld versehentlich die Leistung deines Wechselrichters?

**Merkregel:** Ins Feld **Anlagenleistung** und in die kWp-Felder deiner Strings gehört die
**Modulleistung** (Anzahl × Wp). Die Geräteleistung gehört zum Wechselrichter. *(#354)*

### Cockpit → Jahr: der Speicher bekommt eine eigene Auswertung

**Betrifft dich das?** Alle mit **Batteriespeicher**.

Bisher standen zum Speicher vier Kacheln da — Ladung, Entladung, Wirkungsgrad, Vollzyklen — und
für alles Weitere musstest du die Monate einzeln durchklicken. Unter dem Speicher-Abschnitt in
*Cockpit → Jahr* findest du jetzt den Block **„Speicher im Jahr"**: eine Zeile je Monat mit

| Monat | Ladung | Entladung | Vollzyklen | Solar-Anteil | Auslastung | Netto-Nutzen |
|---|---|---|---|---|---|---|

dazu eine Gesamtzeile und einen Vergleich **Sommer (Jun–Aug) gegen Winter (Nov–Feb)**.

**Zwei Spalten sind neu.** Die **Auslastung** setzt deine Entladung ins Verhältnis zu dem, was der
Speicher im Zeitraum überhaupt hergäbe (Kapazität × Tage). Anders als die Vollzyklen kannst du
sie zwischen Februar und Juli direkt vergleichen. Im laufenden Monat zählen dabei nur die schon
abgelaufenen Tage — sonst stünde am 3. eine Zahl, die mehr über das Datum sagt als über deinen
Speicher. Der **Netto-Nutzen** ist genau der Betrag, der auch im T-Konto desselben Monats steht.

**Wenn Felder leer bleiben.** Ohne gepflegte **Kapazität** stehen Vollzyklen und Auslastung auf
„—" statt auf 0: ein Speicher ohne Kapazitätsangabe ist ein *unbekannter*, kein ungenutzter. Der
Daten-Checker weist dich darauf hin. Trägst du deine **Netzladung** nicht ein, bleibt auch der
Solar-Anteil leer — eedc behauptet dann nicht einfach 100 % Sonne.

Das ist Phase 1 von [#358](https://github.com/supernova1963/eedc-homeassistant/issues/358). Die
Tiefe — SoC-Heatmap „hätte mehr Kapazität geholfen?" und der Sizing-Rechner — kommt später und
gehört dann in den Komponenten-Hub.

### Speicher: der Nutzen in Euro stimmt jetzt überall überein

**Betrifft dich das?** Alle mit Speicher — besonders, wenn du **aus dem Netz lädst** (Arbitrage).

Was dir dein Speicher einbringt, stand je nach Seite unterschiedlich da. Richtig ist der
**Spread**: die entladene Kilowattstunde ersetzt Netzbezug, hätte aber sonst Einspeisevergütung
gebracht — es zählt die Differenz. Das **T-Konto** in *Cockpit → Monat* und *→ Jahr* rechnete
dagegen mit dem vollen Strompreis und lag damit bei einem typischen Tarif (30/8 ct) **rund ein
Drittel zu hoch**; die ROI-Seite nannte für dieselbe Anlage die kleinere Zahl.

Im **Komponenten-Hub → Speicher** kam ein zweiter Punkt dazu: „Eigenverbrauchs-Ersparnis" und
„Arbitrage-Gewinn" werden dort addiert — der erste Posten enthielt aber auch die aus dem Netz
geladene Energie, die im zweiten noch einmal auftauchte. Dieselbe Kilowattstunde zählte doppelt.

Beides läuft jetzt über eine Rechnung, die deine Entladung nach Herkunft trennt. **Du siehst im
T-Konto einen niedrigeren, dafür stimmigen Beitrag** — er passt jetzt zur ROI-Seite. Lädst du
nicht aus dem Netz, ändert sich im Hub nichts.

Und: die **Vollzyklen** in der Cockpit-Übersicht zählten intern die Ladung statt der Entladung
(bei 80 % Wirkungsgrad 10,0 statt 8,0). Gesehen hat das bisher niemand — der Wert wurde nirgends
angezeigt. Mit der neuen Speicher-Tabelle wäre er sichtbar geworden, deshalb ist er mit korrigiert.

### Auswertungen → ROI: „wie weit bin ich?" steht wieder da

**Betrifft dich das?** Alle — besonders, wenn du eine **Wärmepumpe oder ein E-Auto** hast.

Die ROI-Seite sagte dir bisher nur, wie lange es *rechnerisch* noch dauert: „Amortisation in
9,2 Jahren", hochgerechnet aus einer prognostizierten Jahres-Einsparung. Die andere Hälfte der
Frage — **wie viel hat deine Anlage tatsächlich schon eingespielt?** — stand am Bildschirm
nirgends. Sie ist jetzt als zweite Kachel daneben:

> **Amortisations-Fortschritt · 40,0 %**
> noch 7.200 € · voraussichtlich 2030

Der Unterschied ist wichtig: Die linke Kachel ist ein **Modell**, die rechte eine **Messung** aus
deinen tatsächlich erfassten Erträgen. Welche du gerade liest, sagt dir das ⓘ-Symbol an der
Kachel.

**Was sich an deinen Zahlen ändern kann.** Beide Kacheln rechnen gegen deine **Mehrkosten** —
also gegen das, was eine Anschaffung *gegenüber ihrer Alternative* gekostet hat. Für die
Wärmepumpe und das E-Auto setzte eedc dafür bisher pauschale Annahmen ein: 8.000 € für eine
Gasheizung, 35.000 € für einen vergleichbaren Verbrenner — **auch dann, wenn du unter
„Anschaffungskosten Alternative" längst etwas anderes eingetragen hattest**. Genau dieses Feld
mahnt der Daten-Checker an. Ab jetzt wird es gelesen:

- **Du hast das Feld gepflegt** → deine Zahl zählt, nicht die Pauschale.
- **Du hast es nicht gepflegt** → es zählen die vollen Anschaffungskosten. eedc rät nicht mehr an
  deiner Stelle. Deine Amortisation sieht dadurch länger aus als vorher — sie entspricht jetzt
  den Daten, die tatsächlich da sind. Wenn dir das zu streng ist: das Feld nachtragen, dann
  stimmt es wieder.
- **PV, Speicher, Wechselrichter, Wallbox** → unverändert. Dort gibt es keine Alternative.

**Warum es diesen Block eine Weile nicht gab:** Er war beim Umbau auf die neue Oberfläche bewusst
weggelassen worden, weil zwei Amortisations-Zahlen nebeneinander leicht widersprüchlich wirken.
Beim Nachmessen zeigte sich, dass die eigentliche Ursache tiefer lag — es gab **drei**
verschiedene Investitionssummen im Programm, je nachdem welche Seite man aufschlug. Die sind
jetzt eine, und erst dadurch dürfen die beiden Kacheln nebeneinander stehen.


### Cockpit → Monat: der Netz-Ladeanteil zählte doppelt, wenn du Auto und Wallbox pflegst

**Betrifft dich das?** Wenn du **sowohl ein E-Fahrzeug als auch eine Wallbox** in eedc erfasst
hast. Wer nur eines von beidem pflegt, sieht keinen Unterschied.

Deine Wallbox misst den Strom **am Ladepunkt**, dein Auto meldet dieselbe Ladung **aus
Fahrzeugsicht**. Pflegst du beides, hast du **eine** Ladung mit zwei Messgeräten dokumentiert —
nicht zwei Ladungen. eedc weiß das und wählt überall genau eine der beiden Quellen aus (die
Wallbox, wenn sie Heimladung meldet, sonst das Fahrzeug).

An einer Stelle fehlte diese Regel: die Zeile **„Ladung · Netz-Anteil"** im Komponenten-Block
von *Cockpit → Monat* addierte beide Seiten einfach zusammen. Die Zahl lief von dort weiter in
die Jahres-Summe und — das ist der teure Teil — ins **T-Konto**, wo sie mit deinem Arbeitspreis
multipliziert als Kostenposition steht.

Am Demo-Datenbestand nachgestellt: über 25 Monate **5.976 statt 3.831 kWh**, also **56 % zu
viel**, in *jedem* Monat mit Ladung.

**Was du siehst:** einen niedrigeren, richtigen Netz-Anteil und entsprechend niedrigere
Ladekosten im T-Konto — dieselbe Zahl, die ROI-Sicht, Aussichten und die HA-Sensoren schon
vorher genannt haben.


### Werte aus der Zeit vor der Anschaffung zählen nicht mehr mit

**Betrifft dich das?** Wenn du Monatswerte **rückwirkend importiert oder nachgepflegt** hast —
etwa über den HA-Statistik-Import, der so weit zurückreicht, wie deine Langzeitstatistik geht.

Alle Auswertungen in eedc achten auf **Anschaffungs- und Stilllegungsdatum**: eine Wärmepumpe,
die du im April gekauft hast, taucht in den Monaten davor nicht auf. Der Komponenten-Block in
*Cockpit → Monat* war die letzte Stelle, an der dieser Filter fehlte — er nahm jede erfasste
Zeile seines Gerätetyps, ganz gleich ob das Gerät damals schon existierte.

Am Demo-Datenbestand standen dadurch vier Monate lang Heizwärme und Warmwasser einer
Wärmepumpe, die es zu der Zeit noch gar nicht gab; **3.400 kWh davon zählte die Jahres-Sicht ins
Jahr 2024**.

**Was du siehst:** In Monaten vor der Anschaffung (und nach einer Stilllegung) steht bei der
betroffenen Komponente jetzt „—" statt einer Zahl, und die Jahressumme fällt entsprechend
niedriger — und richtiger — aus. Hast du **kein** Anschaffungsdatum gepflegt, gilt das Gerät
unverändert als von Anfang an vorhanden; das ist dann der richtige Anlass, das Datum
nachzutragen.


### Keine Warnung mehr für den Stromverbrauch, den du selbst dazugebaut hast

**Betrifft dich das?** Wenn du eine **Wärmepumpe, ein E-Fahrzeug oder eine Wallbox**
angeschafft hast und der Daten-Checker dir seither erzählt, dein Netzbezug sei
verdächtig hoch.

Der Daten-Checker vergleicht jeden Monat mit demselben Monat im Vorjahr und meldet ab
dem Dreifachen. Für die **Einspeisung** kennt er dabei längst eine Ausnahme: hast du
zwischendurch PV zugebaut, erklärt der Ausbau den Sprung und die Prüfung setzt aus.
Für den **Netzbezug** fehlte dieses Gegenstück — dabei ist der Fall genauso eindeutig:
Wer im September eine Wärmepumpe einbaut, heizt im Januar mit Strom und sieht seinen
Netzbezug planmäßig auf ein Mehrfaches steigen. Der Daten-Checker meldete das Monat für
Monat, und es gab nichts zu korrigieren.

Jetzt gilt: **Ist zwischen den beiden verglichenen Monaten ein Verbraucher dazugekommen,
schweigt die Netzbezugs-Prüfung für dieses Monatspaar.** Als Verbraucher zählen
Wärmepumpe, E-Fahrzeug, Wallbox und alles unter *Sonstiges*, dem du die Kategorie
*Verbraucher* gegeben hast.

Drei Dinge, die dabei bewusst so bleiben:

- **Die Einspeisung wird davon nicht mit entschuldigt.** Ein Verbraucher-Zubau erklärt
  den Netzbezug, ein PV-Ausbau die Einspeisung — springt die jeweils andere Größe, wird
  sie unverändert gemeldet.
- **Ein Austausch ist kein Zubau.** Alte Wärmepumpe stillgelegt, neue angeschafft: die
  Anzahl bleibt gleich, also erklärt nichts den Sprung und die Warnung kommt weiterhin.
- **Ohne Anschaffungsdatum passiert nichts.** eedc kann den Zubau nur erkennen, wenn du
  bei der Komponente ein Anschaffungsdatum gepflegt hast. Steht dort nichts, gilt sie als
  von Anfang an vorhanden — dann ist die Meldung der richtige Hinweis, das Datum unter
  *Einstellungen → Investitionen* nachzutragen.

*Warum das kein Wegklick-Knopf geworden ist:* Ein Hinweis, den du nur noch abnicken
kannst, verstellt später den Blick auf einen echten Fehler. Wenn eedc eine Auffälligkeit
selbst erklären kann, gehört sie gar nicht erst gemeldet — genauso wurde 2026 schon der
Inbetriebnahme-Monat als Vergleichsbasis ausgeschlossen.

### Die Umsatzsteuer auf den Eigenverbrauch stimmt jetzt — und ist überall dieselbe

**Betrifft dich das?** Nur wenn du unter *Einstellungen → Stammdaten* die
**Regelbesteuerung** eingestellt hast. Bei „Keine USt-Auswirkung" (der Normalfall)
ändert sich für dich nichts.

eedc leitet diese Steuer aus den **Selbstkosten je Kilowattstunde** ab: die
Jahresabschreibung deiner Anlage plus laufende Kosten, geteilt durch den **Jahres**-Ertrag.
Zwei Dinge stimmten daran nicht:

- **Über mehrere Jahre war sie viel zu niedrig.** Sobald eine Sicht einen längeren Zeitraum
  zeigte — Cockpit ohne Jahresfilter, der Anlagenbericht über den Gesamtzeitraum, die
  bisherigen Erträge in *Aussichten*, die HA-Sensoren —, wurde die Erzeugung **des ganzen
  Zeitraums** gegen eine **einzelne** Jahresabschreibung gerechnet. Bei drei Jahren kam so
  rund ein Drittel des richtigen Betrags heraus. Dein Netto-Ertrag stand entsprechend zu
  hoch, und weil der ROI-Fortschritt darauf aufsetzt, sah auch die Amortisation zu gut aus.
- **Jede Sicht rechnete mit einer anderen Grundlage.** Die meisten setzten die vollen
  Anschaffungskosten an — beim E-Auto also den ganzen Kaufpreis —, das Cockpit eine eigene
  Summe mit festen Annahmen (35.000 € fürs Auto, 8.000 € für die Heizung), die deine
  gepflegten **Alternativkosten** gar nicht las. Cockpit-Kachel und HA-Sensor lagen dadurch
  auseinander, obwohl der Sensor genau diese Kachel abbilden soll.

Beides läuft jetzt über **eine** Berechnung. Grundlage sind die **Mehrkosten** — was eine
Anschaffung gegenüber ihrer Alternative gekostet hat, aus dem Feld, das du in der
Investition ohnehin pflegst —, und gerechnet wird Jahr für Jahr. **Ein angefangenes Jahr
zählt anteilig**: gehst du im Juni in Betrieb, trägt dieses Jahr sieben Zwölftel
Abschreibung statt zwölf gegen sieben Monate Ertrag.

**Was du siehst:** Die Beträge bewegen sich **in beide Richtungen**. Über einen mehrjährigen
Zeitraum steigt die USt spürbar und der Netto-Ertrag sinkt; für ein einzelnes Jahr sinkt sie
meist leicht. Cockpit und HA-Sensor stimmen danach auf den Cent überein.

**Muss ich etwas tun?** Nein. Es lohnt sich aber, bei E-Auto und Wärmepumpe die
**Alternativkosten** zu pflegen (*Investitionen → Bearbeiten*) — sie bestimmen jetzt
mit, wie hoch die Steuer ausfällt.

### Auswertungen und Cockpit nennen dieselben Euro-Beträge

**Betrifft dich das?** Wenn du *Auswertungen → Finanzen* oder die Finanzspalten in
*Auswertungen → Tabelle* nutzt — besonders, wenn du **regelbesteuert** bist oder einen
**Erzeuger unter „Sonstiges"** mit Brennstoff betreibst (z. B. ein Mini-BHKW).

Die Finanzwerte dieser Seite wurden bisher **in deinem Browser** gerechnet, mit einer eigenen
Formel neben der, die eedc für Cockpit, Monatsbericht-PDF, HA-Export und Aussichten benutzt.
Jetzt kommen sie aus derselben Quelle wie überall sonst. Drei Beträge ändern sich dadurch:

- **Ein Brennstoff-Erzeuger bringt keine Strompreis-Ersparnis mehr.** Sein Strom wurde bisher
  bewertet, als wäre er gratis. In deiner **Energiebilanz** zählt er weiter voll mit
  (Eigenverbrauch, Autarkie, EV-Quote) — nur wirtschaftlich bewertet eedc ihn bewusst nicht,
  weil der Brennstoff auf der anderen Seite Geld kostet.
- **Bei Regelbesteuerung wird die USt auf den Eigenverbrauch abgezogen**, wie im Cockpit. Damit
  die kleinere Zahl erklärbar bleibt, gibt es in der Werte-Tabelle die neue Spalte
  **„USt Eigenverbrauch"** (über den Spalten-Wähler einblendbar). Bist du nicht regelbesteuert,
  ändert sich hier nichts.
- **Ein Balkonkraftwerk, bei dem nur der Eigenverbrauch gepflegt ist**, zählt jetzt mit statt
  gar nicht.

**Muss ich etwas tun?** Nein. Wenn dir eine Zahl kleiner vorkommt als früher: sie stimmt jetzt
mit dem Cockpit überein. **Ein Hinweis für Regelbesteuerte:** Die Summe der Tageszeilen ergibt
beim Netto-Ertrag nicht mehr genau den Monatswert — die USt ist eine Jahresgröße und lässt sich
keinem einzelnen Tag zuordnen.

### SFML steht jetzt im Prognosen-Vergleich

**Betrifft dich das?** Wenn du unter *Einstellungen → Stammdaten* **Solar Forecast ML (SFML)**
als Prognosequelle gewählt hast.

Unter *Auswertungen → Prognose* standen bisher OpenMeteo, eedc, Solcast und dein IST — die
Quelle, mit der eedc bei dir tatsächlich rechnet, fehlte ausgerechnet dort. Sie erscheint jetzt
als eigene **SFML**-Spalte im Stundenvergleich und im 7-Tage-Vergleich, und als eigene Kurve im
Tagesverlauf.

**Bewertet wird SFML weiterhin nicht:** Es bekommt keine Δ-Spalte, und im Genauigkeits-Tracking
(MAE/Bias) taucht es nicht auf. eedc stellt eine spezialisierte fremde Prognosequelle nicht
benotend gegen die eigene. Für vergangene Tage steht in der SFML-Spalte deshalb „—" — eedc führt
darüber keine Mitschrift; gefüllt sind heute und morgen.

**Muss ich etwas tun?** Nein. Ohne gewählte SFML-Quelle ändert sich für dich nichts.

### Prognosen-Vergleich: eine Abweichung, eine Sprache — und eine eigene Spalte

**Betrifft dich das?** Wenn du unter *Auswertungen → Prognose* die drei Tabellen vergleichst.

Bisher beantworteten sie dieselbe Frage in zwei Sprachen: das **Genauigkeits-Tracking** nannte
nur den Prozentwert („+16 %"), **Stundenvergleich** und **7-Tage-Vergleich** nur die kWh
(„▲ 9,7"). Weil die 7-Tage-Tabelle ihre Vergangenheits-Tage aus derselben Liste zieht wie das
Tracking, standen die letzten vier Tage doppelt auf der Seite — mit zwei verschiedenen Zahlen
für dieselbe Abweichung.

Ab jetzt steht überall **beides**: „▲ 9,7 (16 %)". Beide Angaben sagen etwas Eigenes — 0,3 kWh
Abweichung sind mittags ein Treffer und morgens um sieben eine Fehlprognose.

Damit die Prozentangabe die Zahlen nicht mehr verschiebt, hat jede Quelle jetzt **zwei
Spalten**: links ihr Wert, rechts daneben unter **Δ** die Einwertung. So fluchten die Werte
wieder untereinander, und du kannst die Δ-Spalte für sich lesen.

Nebenbei verschwinden drei Ungereimtheiten: Eine kleine Morgenstunde bekam in der einen Tabelle
gar keine Bewertung und in der anderen eine **rote**; der Rotton war in beiden leicht
verschieden; und der 7-Tage-Vergleich verschwieg als einziger die Abweichung abgeschlossener
Tage, wenn sie sehr klein war.

**Muss ich etwas tun?** Nein.

### Der Jahres-Verlauf zeigt auch den laufenden Monat

**Betrifft dich das?** Wenn du in *Cockpit → Jahr* schaust und dort oben mehr Monate gezählt
werden, als der Verlauf darunter Balken zeichnet.

Ganz oben stand zum Beispiel „Jan–Aug · 9.653 kWh", der Verlauf darunter zeigte sechs Balken.
Der Grund: eedc kannte einen Monat für den Verlauf nur dann, wenn er **irgendetwas** in der
Datenbank stehen hatte — einen Monatsabschluss oder mindestens eine Komponenten-Zeile. Einen
**automatischen Monatsabschluss gibt es nicht**, deshalb fehlte immer mindestens der gerade
laufende Monat. Und wer den Vormonat noch nicht abgeschlossen hatte, verlor auch den — im
Zweifel den ertragsstärksten des Jahres.

Ab jetzt rechnet eedc solche Monate aus den **Tageswerten**, die es ohnehin täglich mitschreibt.
Im Tooltip steht dann „aus Tageswerten", damit du siehst, woher die Zahl kommt.

**Muss ich etwas tun?** Nein. Und es kostet deine Home-Assistant-Box **keine einzige zusätzliche
Abfrage** — die Tageswerte liegen bereits bei eedc.

**Was sich nicht ändert:** Gepflegte Zahlen bleiben unangetastet — die Tageswerte füllen nur
Lücken, sie überschreiben nichts. *Auswertungen → Tabelle* zeigt weiterhin nur echte Datensätze,
also nichts, was du dort nicht bearbeiten könntest. Monatsbericht, HA-Sensoren und die
Community-Übertragung bleiben ebenfalls, wie sie waren. Dass ein Monatsabschluss fehlt, meldet
dir weiterhin der [Daten-Checker](HANDBUCH_EINSTELLUNGEN.md) — mit Link direkt auf den Abschluss.

### Ein Geräte-Connector sagt jetzt, welchen Zeitraum er gemessen hat

**Betrifft dich das?** Nur wenn du unter *Einstellungen → Datenquellen* einen
**Geräte-Connector** eingerichtet hast (Wechselrichter, Speicher o. ä. mit direktem Abruf).

Ein Connector-Wert ist immer die **Differenz zweier Zählerstände**. Richtest du ihn mitten im
Monat ein, kennt er die Tage davor nicht — der Wert für diesen Monat ist dann ein Bruchstück.
Bei einem Anwender waren das fünf Zählerstände vom 28.–30. Juli, angezeigt als **Juli-Wert von
51 kWh**, während seine Anlage in dem Monat rund **996 kWh** erzeugt hatte. Dass so ein Wert
keinen von dir gepflegten Monatswert mehr verdrängt, ist seit v4.0.5 erledigt — **beschriftet
war er trotzdem nicht**, und wenn keine andere Quelle da war, stand er einfach da.

In *Cockpit → Monat* trägt das Quellen-Etikett jetzt den gemessenen Zeitraum:
**„Connector (28.–30.07.2025)"**. Fährst du mit der Maus darüber, steht dort ausgeschrieben,
wie viele Tage des Monats das sind. Deckt dein Connector den Monat ab dem Ersten ab — der
Normalfall, sobald er ein paar Wochen läuft —, **ändert sich für dich nichts**.

Und wenn dein Connector für den laufenden Monat **gar keinen** Wert bilden kann, weil ein
Zählerstand fehlt, sagt dir das jetzt der [Daten-Checker](HANDBUCH_DATEN_CHECKER.md#411-geraete-connector-ohne-monatswert)
— vorher merkte man davon nichts, in der Monats-Sicht stand einfach eine Quelle weniger.
Am 1. eines Monats meldet er nichts, solange der tägliche Abruf läuft: dort fehlt der
Zählerstand *im* neuen Monat naturgemäß, bis der Abruf einmal durch ist.

**Muss ich etwas tun?** Nein — außer der Daten-Checker meldet den Connector; dann lohnt der
Blick, ob der **tägliche Abruf** eingeschaltet und das Gerät erreichbar ist.

---

## v4.0.8 — Nach einem Neustart stimmen die Einheiten sofort (August 2026)

### Die erste Stunde nach einem Neustart der Box rechnete mit fehlenden Einheiten

**Betrifft dich das?** Wenn du in der ersten Stunde nach einem **Neustart deiner Home-Assistant-Box**
(Update, Stromausfall, Reboot) in eedc hineingeschaut hast — und dort Sensoren nutzt, die ihre
Leistung in **kW** melden statt in Watt.

eedc merkt sich zu jedem zugeordneten Sensor, in welcher Einheit er misst — daraus folgt, ob ein
Wert noch umgerechnet werden muss. Dieser Merkzettel wurde stündlich aufgefrischt, und um zu
entscheiden, ob eine Auffrischung fällig ist, hat eedc auf die **Laufzeit des Systems** geschaut.
Direkt nach einem Neustart ist die kleiner als eine Stunde — und damit galt der noch **völlig
leere** Merkzettel als „gerade eben aufgefrischt". eedc hat die Einheiten also gar nicht erst
abgefragt und eine Stunde lang so getan, als kenne es keine.

Sichtbar wurde das dort, wo aus der Einheit eine Umrechnung folgt: Ein Sensor, der **kW** liefert,
wurde im **Live-Tagesverlauf** in dieser ersten Stunde nicht in Watt umgerechnet und stand damit um
den Faktor 1000 daneben. Ebenso betroffen waren die Einheiten-Prüfung des **Daten-Checkers**
(die kW nicht mehr von kWh unterscheiden konnte) und die Auswertung im **Energieprofil**.

Nach einer Stunde Laufzeit verschwand der Effekt von selbst und kam erst beim nächsten Neustart
wieder — wer seine Box durchlaufen lässt, hat davon nie etwas gemerkt. Jetzt prüft eedc, ob ein
Sensor **überhaupt schon einmal** abgefragt wurde, statt zu rechnen, wie lange die Box läuft.

**Was du tun musst: nichts.** Gespeicherte Monats- und Tageswerte sind nicht betroffen — es ging um
die Anzeige und um die Prüfung, nicht um deine erfassten Daten. Der Fehler kam mit v4.0.7 herein.

---

## v4.0.7 — Nichts kleinrechnen, nichts behaupten (August 2026)

### eedc geht sparsamer mit Home Assistant um

**Betrifft dich das?** Wenn du eedc als **Add-on** in Home Assistant betreibst — vor allem auf einem
Raspberry Pi oder einer anderen kleinen Box, und erst recht mit vielen Geräten in HA.

Aus der Community kamen Berichte, die HA-Oberfläche werde träge oder hänge, seit eedc als Add-on
läuft; als separate Docker-Installation sei alles normal. Wir haben nachgemessen, und es stimmte.

Die *Live*-Ansicht von eedc hat alle fünf Sekunden **den kompletten Zustand aller HA-Geräte**
angefordert, um daraus die paar zugeordneten Sensoren herauszusuchen. Auf einer Anlage mit rund
3500 Geräten sind das etwa **2,4 Megabyte pro Abruf** — Daten, die Home Assistant selbst
zusammenbauen muss, und zwar in genau dem Programmteil, der auch die Oberfläche bedient. Jetzt holt
eedc **nur noch die Sensoren, die es wirklich benutzt**.

Dazu kommen zwei Dinge, die du nicht siehst, aber merkst:

- **Ein Tab im Hintergrund fragt nichts mehr ab.** Ein vergessenes Browser-Fenster oder ein
  Wandtablet im Standby hat bisher rund um die Uhr weitergepollt. Kehrst du zurück, ist die Anzeige
  sofort wieder aktuell.
- **Die Abfragen an die HA-Datenbank sind deutlich schlanker geworden.** Bei großen Historien —
  besonders mit MariaDB — musste die Datenbank bisher die gesamte Aufzeichnung eines Sensors
  durchlesen, um einen einzigen Zählerstand zu holen. Das war der Teil, den die Community
  vermutet hatte; er war real, aber nicht der größte.

**Eine Zahl kann sich dabei ändern**, und zwar nur in einem Sonderfall: Wenn deine MariaDB in einer
anderen Zeitzone läuft als eedc (typisch: Datenbank auf UTC, eedc auf Europe/Berlin), war der
Monatsschnitt bisher um den Zeitunterschied verschoben. Jetzt gilt durchgehend die Zeitzone von
eedc. Bei der Standard-Installation mit SQLite und bei gleicher Zeitzone ändert sich nichts.

**Was du tun musst: nichts.** Wenn dir HA seit eedc träge vorkam, sollte das mit diesem Update
besser sein — und wenn nicht, melde dich bitte, dann fehlt noch etwas.

### Auswertungen und Jahr: die E-Auto-Ladung ist wieder vollständig

**Betrifft dich das?** Wenn du bei deinem E-Auto oder deiner Wallbox die **Gesamt-Ladung** und den
**PV-Anteil** pflegst, aber keinen eigenen Wert für die Netzladung — bei evcc-Importen ist das der
Normalfall.

In *Auswertungen → Tabelle* und in den Jahres-Kacheln hat eedc die Ladung bisher aus PV-Anteil
**plus** Netzanteil zusammengezählt. Fehlte der Netzanteil als eigener Wert, blieb er weg: von
200 geladenen Kilowattstunden standen dann nur die 150 PV-Kilowattstunden in der Tabelle. Der
Netzanteil wird jetzt aus *Gesamt minus PV* abgeleitet — so, wie es die übrigen Ansichten längst
tun.

**Die Zahl wird also größer, und die alte war zu klein.** Wenn du beide Werte gepflegt hast, ändert
sich nichts.

Zusätzlich: die Spalte **„Einspeisung bei neg. Preis"** zeigt „—" statt `0,0`, wenn für den Monat
keine Börsenpreis-Daten vorliegen. Das betrifft nur Anlagen mit gesetztem §51-Schalter — eine 0
hätte dort behauptet, es habe keine Negativpreis-Stunden gegeben, obwohl schlicht nichts
aufgezeichnet wurde.

**Unverändert:** die Zeilen der Tabelle (nur Monate mit erfassten Zählerständen, neueste zuerst),
alle übrigen Spalten, und „—" bleibt „—", wo ein Gerät für den Monat nichts gemeldet hat. Eine
**gemessene** Null bleibt eine Null: eine Wärmepumpe, die im Sommer 0 kWh geheizt hat, zeigt
weiterhin `0,0`.

**Was du tun musst: nichts.**

---

### Cockpit → Monat: die PV ist da, wo bisher nichts stand — und der Vorjahresvergleich stimmt

**Betrifft dich das?** Fünf Punkte, jeder mit eigener Voraussetzung — die ersten beiden im
laufenden Monat, die letzten drei im Vergleich mit dem Vorjahr.

**1. Deine PV erscheint, auch ohne Sensor je String.** Wenn du die **Gesamterzeugung deiner
Anlage** pflegst, aber keinen eigenen Wert je Modulfeld, zeigte *Cockpit → Monat* bisher
**gar keine PV** — während dieselbe Zahl unter *Cockpit → Übersicht* korrekt stand. Der
Monatsbericht liest jetzt genauso auf wie alle anderen Ansichten: gemessene Werte je Modulfeld
haben Vorrang, die Gesamterzeugung füllt die Lücken.

**2. Beim Balkonkraftwerk wird kein Eigenverbrauch mehr erfunden.** Hast du für dein
Balkonkraftwerk die Erzeugung gepflegt, den Eigenverbrauch aber nicht, setzte eedc hier die
**volle Erzeugung** als Eigenverbrauch ein — als hätte das Gerät alles selbst verbraucht. Der
Komponenten-Hub zeigte daneben nichts. Jetzt bleibt das Feld leer, bis du es füllst oder ein
Sensor es misst.

**3. Der Vorjahresvergleich löst die PV genauso auf** wie der laufende Monat. Wenn du nur die
Gesamterzeugung pflegst, stand im Vorjahr eine 0 — **die Vorjahres-PV steigt also**.

**4. Rückspeisung aus dem E-Auto zählt jetzt auch im Vorjahr.** Wer sein Auto ins Haus entladen
kann (V2H), sah diese Kilowattstunden im laufenden Monat im Eigenverbrauch, im Vorjahr nicht —
das Jahres-Delta zeigte dadurch einen Sprung, den es nie gab. **Vorjahres-Eigenverbrauch und
-Autarkie steigen.**

**5. Öffentliches Laden zählt im Vorjahr nicht mehr als Heimladung.** Wenn du **E-Auto und
Wallbox** gepflegt hast, nahm der Vorjahresvergleich pro Feld den jeweils größeren Wert — und
damit bei der Gesamt-Ladung des Autos auch den Strom, den du **an einer öffentlichen Ladesäule**
gezogen hast. Beispiel aus dem Demo-Bestand: 223,8 kWh im Vorjahr, davon 50 kWh extern, während
derselbe Monat als laufender Monat längst die richtigen 174 kWh zeigte. **Die Vorjahres-Ladung
kann dadurch sinken** — sie war vorher zu hoch. Die extern geladenen Kilowattstunden und ihre
Kosten gehen nicht verloren, sie stehen weiter in ihrer eigenen Zeile.

**Unverändert:** dienstlich genutzte Fahrzeuge bleiben in beiden Ansichten außen vor, Komponenten
zählen weiterhin erst ab ihrem Anschaffungsdatum, und ein Vorjahresmonat ohne erfasste
Zählerstände blendet den Vergleich wie bisher aus. Alle übrigen Werte des Monatsberichts sind
gegen den Demo-Bestand geprüft und identisch geblieben.

**Was du tun musst: nichts.** Die Werte werden bei jedem Aufruf neu gerechnet.

---

### Komponenten: keine Monatszeile mehr aus lauter Nullen für den Firmenwagen

**Betrifft dich das?** Nur wenn du ein Fahrzeug als **dienstlich** markiert hast und es in
einzelnen Monaten die einzige Komponente ist, für die du Werte gepflegt hast.

*Auswertungen → Komponenten* wertet dienstlich genutzte Fahrzeuge bewusst nicht mit aus — ihr Strom
gehört in die dienstlichen Ladekosten, nicht in die E-Mobilitäts-Bilanz deines Hauses. In einem
Monat, in dem **ausschließlich** ein solches Fahrzeug gepflegt war, erschien trotzdem eine Zeile:
mit lauter Nullen. Das las sich wie „in diesem Monat wurde nichts geladen", obwohl in Wahrheit
etwas geladen wurde, das diese Ansicht nur nicht auswertet. **Die Zeile entfällt jetzt.**

**Unverändert:** Sobald in dem Monat noch irgendetwas anderes erfasst ist — eine zweite Komponente
oder eine gebuchte Einnahme bzw. Ausgabe —, steht die Zeile wie bisher, der Dienstwagen bleibt
darin wie bisher außen vor. **Und seine Kosten zählen weiter:** eine Reparatur, die du an dem
Fahrzeug gebucht hast, erscheint unverändert unter *Sonstiges* und trägt den Monat auch allein.

**Was du tun musst: nichts.**

---

### Komponenten: Speicher, V2H und „Sonstiges" rechnen mit deiner Einspeisevergütung

**Betrifft dich das?** Wenn du unter *Einstellungen → Strompreise* **mehr als einen Eintrag** hast
und sich darin die Einspeisevergütung unterscheidet — oder wenn du überhaupt eine Komponente unter
**Sonstiges** erfasst hast (Mini-BHKW, Pelletofen und Ähnliches).

Mit v4.0.5 haben wir dafür gesorgt, dass eine Preiserhöhung nicht rückwirkend deine ganze Historie
umschreibt: Jeder Monat wird seither mit dem **Strompreis bewertet, der damals galt**. Die
**Einspeisevergütung** daneben ist dabei stehen geblieben — sie war weiterhin die von heute.

Das fällt überall dort auf, wo eedc **beide** Preise in dieselbe Rechnung nimmt. Wenn dein Speicher
abends Strom ins Haus abgibt, ist dein Gewinn die *Differenz*: Du sparst den Netzbezug und
verzichtest im Gegenzug auf die Einspeisevergütung. Genauso rechnet die **V2H-Ersparnis** deines
E-Autos und die Speicher-Kategorie unter *Sonstiges*. Standen die beiden Preise aus verschiedenen
Jahren nebeneinander, wurde die Differenz zu groß oder zu klein. In einem nachgestellten Fall — 12
Cent Vergütung damals, 5 Cent heute, 1.200 kWh Rückspeisung — zeigte eedc **300 € statt 216 €**.

Bei **Komponenten → Sonstiges** war es deutlicher: Diese Sicht rechnete mit zwei festen Zahlen,
**30 Cent** Strompreis und **8 Cent** Einspeisevergütung, ganz gleich was in deinen Strompreisen
stand. Ein BHKW bekam also 8 Cent je eingespeister Kilowattstunde gutgeschrieben, auch wenn dein
Vertrag 12 Cent hergibt.

**Beide Preise kommen jetzt aus dem Tarif, der im jeweiligen Monat galt.**

**Unverändert:** Hast du nur **einen** Strompreis-Eintrag — der Normalfall —, ändert sich für dich
nichts, denn „der Tarif des Monats" ist dann derselbe wie „der Tarif von heute". Ebenfalls
unverändert bleiben das **Wallbox-** und das **Wärmepumpen-Dashboard** (dort gibt es keine solche
Differenz), das **Balkonkraftwerk** (dessen Einspeisung ist unvergütet) und die **ROI-Auswertung**:
Sie bildet bewusst einen Durchschnitts-Jahreswert, um die Amortisation nach vorn zu rechnen — dafür
ist der heutige Tarif der richtige.

**Was du tun musst: nichts.** Wenn du deine Einspeisevergütung bisher gar nicht gepflegt hast,
lohnt jetzt aber ein Blick unter *Einstellungen → Strompreise* — die Zahlen der drei genannten
Sichten hängen daran.

---

### Tag: der Einspeiseerlös wird nicht mehr gekürzt, wenn dich §51 gar nicht betrifft

**Betrifft dich das?** Wenn deine Anlage **keine** §51-Anlage ist (das ist der Normalfall bei
Bestandsanlagen — der Schalter unter *Einstellungen → Anlage* steht standardmäßig auf **aus**) und
eedc gleichzeitig deine **Börsenpreise mitschreibt**, etwa über einen dynamischen Tarif.

Seit dem Solarpaket I bekommen **Neuanlagen** in Stunden mit negativem Börsenpreis keine
Einspeisevergütung. Für alle anderen gilt das nicht — deshalb ist es ein Schalter, den du selbst
setzt. In *Cockpit → Tag* wurde dieser Abzug bisher trotzdem gerechnet, sobald überhaupt negative
Preise mitgeschrieben waren: an einem sonnigen Sonntag mit **45 kWh Einspeisung** standen dort
**1,86 €** statt der rund 3,70 €, die dir zustehen.

Was du jetzt siehst:

- **Der Tages-Einspeiseerlös ist wieder vollständig** — und mit ihm die Kachel **Netto-Ertrag** und
  der Finanzen-Block darunter. Die Zahlen werden also **größer**; die alten waren zu klein.
- Die Spalte **„Einspeisung bei neg. Preis"** bleibt bei dir leer, so wie in der Monatstabelle
  auch — dort war sie schon immer leer.
- **Die Anzahl der negativen Preisstunden bleibt sichtbar.** Das ist eine Marktinformation und
  kein Abzug — interessant fürs Laden, unabhängig von §51.

**Unverändert:** Hast du den §51-Schalter **gesetzt**, weil deine Anlage betroffen ist, rechnet
eedc exakt wie bisher weiter. Monats-, Jahres- und Cockpit-Ansichten waren nie betroffen — dort hat
der Schalter immer korrekt gewirkt. Rückwirkend musst du nichts anstoßen: die Beträge werden bei
jedem Aufruf neu gerechnet, alte Tage stimmen ab sofort mit.

**Was du tun musst: nichts.** Wenn du unsicher bist, ob der Schalter bei dir richtig steht: er
heißt **„Unterliegt §51 EEG"** und gehört nur dann an, wenn deine Anlage nach dem Solarpaket I in
Betrieb ging und dein Netzbetreiber dir die Negativpreis-Stunden tatsächlich nicht vergütet.

---

### Live: ein Hausverbrauch, der nicht mehr so tut, als wäre er vollständig

**Betrifft dich das?** Wenn in *Cockpit → Live* für einen Tag **kein Netzbezug** ankommt — kein
Zähler zugeordnet, Home Assistant zeitweise nicht erreichbar, MQTT still.

Die „Heute"-Kachel **Hausverbrauch** ist Eigenverbrauch **plus** Netzbezug. Fehlte der Netzbezug,
hat eedc die Lücke bisher als **0** eingesetzt und die Kachel trotzdem gefüllt — mit einer Zahl, die
um genau den fehlenden Netzbezug zu niedrig war und von einem gemessenen Wert nicht zu unterscheiden.

Was du jetzt siehst:

- **Die Kachel bleibt leer**, solange ein Teil des Hausverbrauchs unbekannt ist — so wie die
  Nachbar-Kacheln es bei fehlender Quelle schon immer gemacht haben.
- **Der Eigenverbrauch bleibt stehen**, wenn nur der Netzbezug fehlt: er braucht ihn nicht.
- **Eine gemessene 0 bleibt eine 0.** Ein Tag ohne Netzbezug oder eine Batterie, die nichts getan
  hat, sind Aussagen — keine Lücken. Da steht weiterhin `0,0`, nicht „—".

**Unverändert:** Fehlt die **PV** oder die **Einspeisung**, schweigen Eigenverbrauch und
Hausverbrauch wie bisher. Ob der Wert ohne diesen Sensor zu hoch oder zu niedrig wäre, hängt davon
ab, welcher fehlt — und eine Zahl, deren Fehlerrichtung niemand kennt, ist schlechter als eine Lücke.

**Was du tun musst: nichts.** Wenn dir eine Kachel dauerhaft fehlt, sagt dir der
[Handbuch → Einstellungen §5.3 Daten-Checker](HANDBUCH_EINSTELLUNGEN.md#53-daten-checker), welcher
Zähler nicht zugeordnet ist.

### Tag: die Stundentabelle schreibt keine 0,00 mehr, wo sie nichts weiß

**Betrifft dich das?** Wenn in *Cockpit → Tag* einzelne Stunden Lücken haben — typischerweise
nachts, wenn ein Zähler ausfällt, oder wenn du gar keinen vollständigen Zählersatz hast.

In der Stundenwerte-Tabelle standen zwei benachbarte Spalten im Widerspruch: **Gesamtverbrauch**
zeigte für eine unbekannte Stunde „—", **Hausverbrauch** dagegen **0,00 kW**. Aufgefallen ist es an
einem Tag, an dem in den Stunden 0–7 die PV-Zeile leer war, Batterie und Netz aber weiter maßen —
rund 0,28 kW flossen, angezeigt war 0,00.

Der Hausverbrauch ist eine Differenz: *Gesamtverbrauch minus Wärmepumpe, Wallbox und weitere
Verbraucher*. Kennt eedc den Gesamtverbrauch einer Stunde nicht, kennt es auch den Hausverbrauch
nicht — dort steht jetzt **„—"**.

- **Die Σ-Zeile (kWh/Tag) ändert sich nicht.** Die betroffenen Stunden trugen ohnehin 0,00 bei.
- **Der CSV-Export trägt dieselben Zahlen** wie die Tabelle, an den betroffenen Stellen eine leere
  Zelle.
- **Eine gemessene 0 bleibt 0,00.** Eine Stunde, in der dein Haus nichts verbraucht hat, ist eine
  Aussage — keine Lücke.

**Wenn du keinen Gesamtverbrauch messen kannst**, ist die Spalte jetzt durchgehend leer statt
durchgehend 0,00. Woran es liegt, sagt dir der
[Daten-Checker](HANDBUCH_EINSTELLUNGEN.md#53-daten-checker): für die Stunden-Bilanz braucht eedc
PV, Einspeisung und Netzbezug.

### Klimaanlagen: keine Ersparnis mehr gegen eine Heizung, die es nie gab

**Betrifft dich das?** Wenn du eine **Split-Klimaanlage** als Wärmepumpe mit der Art
*Luft-Luft (Klimaanlage)* erfasst hast.

*Auswertungen → ROI* hat deiner Klimaanlage bisher einen Heizwärme- und Warmwasserbedarf
angerechnet — **12.000 und 3.000 kWh pro Jahr**, Standardwerte, die du nie eingetragen hast. Daraus
wurde eine Ersparnis von rund **1.100 € und 2.210 kg CO₂ im Jahr** gegenüber einer Gasheizung, die
bei dir gar nicht ersetzt wurde. Ein Split-Gerät hat nicht einmal einen Warmwasserkreis. Die Beträge
blieben außerdem nicht in ihrer Zeile: sie steckten auch in Gesamt-Ersparnis, ROI, Amortisation und
Gesamt-CO₂ deiner Anlage.

Was du jetzt siehst:

- **Deine Klimaanlage steht weiter in der ROI-Tabelle** — mit ihren Anschaffungskosten. In den
  Wert-Spalten steht **„—"** und daneben *nicht bewertet* statt einer erfundenen Zahl.
- **Die Gesamtzahlen deiner Anlage werden dadurch kleiner** und stimmen jetzt mit dem überein, was
  *Cockpit → Nachhaltigkeit* schon immer gezeigt hat (dort stand für dasselbe Gerät 0).
- **Heizwärme- und Warmwasserbedarf werden nicht mehr abgefragt**, wenn die Wärmepumpenart auf
  *Luft-Luft (Klimaanlage)* steht — und der Daten-Checker verlangt sie auch nicht mehr.

**Was weiterhin voll funktioniert:** Stromverbrauch je Stunde/Tag/Monat/Jahr, der Anteil an
Hausverbrauch, Eigenverbrauch und Autarkie, die Stromkosten (auch mit eigenem Wärmestrom-Tarif),
Live-Anzeige und Tagesverlauf.

**Was du tun musst: nichts.** Deine gespeicherten Werte bleiben erhalten — es wird nichts gelöscht.
**Klassische Wärmepumpen rechnen unverändert.** Die Auswertung von Klimaanlagen wird
weiterentwickelt; das Thema läuft als offenes Issue
[#263](https://github.com/supernova1963/eedc-homeassistant/issues/263).
→ [Handbuch → Komponenten](HANDBUCH_BEDIENUNG.md)

### Das laufende Jahr wird nicht mehr mit einem vollen Vorjahr verglichen

**Betrifft dich das?** Wenn du **Cockpit → Jahr/Gesamt** für das **laufende** Jahr ansiehst — oder
für ein Jahr, in dem einzelne Monate fehlen.

Die Spalten **Vorjahr** und **Ø Jahre** summierten bisher immer das **ganze** Jahr. Im laufenden Jahr
standen damit die bisher gelaufenen Monate gegen zwölf volle: auf einer echten Anlage im August
7.703 kWh gegen 14.221 kWh, also **„▼ 46 %"**. Diese Zahl maß im Wesentlichen den Kalender und
hätte sich bis Dezember von selbst zurückgebildet.

Was du jetzt siehst:

- **Alle Spalten rechnen über dieselben Monate** — die **abgeschlossenen** des angezeigten Jahres,
  auf der IST-Seite genauso wie beim Vorjahr. Der laufende Monat bleibt außen vor; zwei Augusttage
  gegen einen vollen August wären derselbe Fehler noch einmal, nur kleiner. Dieselbe Anlage wie oben
  zeigt jetzt 9.450 kWh gegen 9.912 kWh und **„▼ 5 %"**.
- **Das Fenster steht dran**, sobald dort weniger als ein volles Jahr summiert ist — über der
  IST-Spalte, am Spaltenkopf des Vergleichs, an den Kennzahl-Kacheln (`VJ (Jan–Jul): 6.198 kWh`)
  und als Satz unter der Tabelle:
  „Vergleich beschnitten auf die gemeinsamen Monate: Jan–Jul".
- **In den Ø geht nur ein Jahr ein, das dieses Fenster ganz abdeckt.** Ist deine Anlage z. B. im Juni
  2023 gestartet, trüge 2023 zu einem Vergleich über Jan–Jun nur einen einzigen Monat bei — das Jahr
  bleibt draußen, und die Zeile darunter zählt ehrlich („Ø aus 2 Jahren" statt 3).
- **Gibt es gar keinen gemeinsamen Monat**, entfällt die Vergleichsspalte („—") statt 0 anzuzeigen.
- **Eine Lücke mitten im Jahr wirkt genauso** — verglichen werden immer *dieselben* Monate, nicht
  „die ersten N".

**Abgeschlossene Jahre ändern sich nicht:** Steht auf beiden Seiten ein volles Jahr, ist die
Beschneidung wirkungslos und es wird auch nichts beschriftet.

**Was du tun musst: nichts.** Wenn deine Vorjahres- und Ø-Spalten kleiner geworden sind und die
Δ-Prozente viel moderater ausfallen, ist das die Korrektur — deine Anlage hat sich nicht verändert.
→ [Handbuch → Cockpit → Jahr/Gesamt](HANDBUCH_BEDIENUNG.md#24-jahrgesamt)

### Ein Monat ohne Monatsabschluss fehlt der Jahreszahl nicht mehr

**Betrifft dich das?** Wenn du **Cockpit → Jahr/Gesamt** ansiehst und den Monatsabschluss nicht
sofort nach Monatsende machst — also fast alle.

Bisher zählte ein Monat erst zum Jahr, wenn du ihn **abgeschlossen** hattest. Die Messwerte deiner
Komponenten liegen aber längst vor; nur die Zählerstände trägst du oft Wochen später nach. In der
Zwischenzeit fehlte dieser Monat der Jahreszahl **vollständig** — auf einer echten Anlage am
2. August 2026 war das der volle Juli mit 1.843 kWh, also **knapp ein Viertel** der angezeigten
Jahresernte, und ausgerechnet der stärkste Monat.

Was du jetzt siehst:

- **Ein Monat zählt, sobald er Daten trägt** — nicht erst nach dem Monatsabschluss. Dieselbe Anlage
  zeigt statt 7.703 kWh jetzt **9.547 kWh**. Autarkie, spezifischer Ertrag, SOLL-Erfüllung, die
  Komponenten-Kennzahlen und die Finanz-Zahlen des Jahres ziehen mit.
- **Auch mehrere offene Monate** werden gefunden, ebenso eine Lücke mitten im Jahr.
- **Der Block-Kopf nennt das Fenster**, sobald es kein volles Jahr ist: `Jan–Aug · 5 Energie-…`.
- **Kachel und Vergleichstabelle sind bewusst nicht dieselbe Zahl.** Die Kachel zählt das Jahr **bis
  heute**, die Tabelle bis zum letzten abgeschlossenen Monat — beide sagen, worauf sie sich
  beziehen, und der Satz unter der Tabelle nennt den Unterschied („… · Kennzahlen oben: Jan–Aug").

**Was du tun musst: nichts.** Wenn deine Jahres-Erzeugung sichtbar **gestiegen** ist, ist das die
Korrektur — die alte Zahl war zu klein, deine Anlage ist unverändert. Den offenen Monatsabschluss
meldet eedc weiterhin: als Symbol in der Statusleiste unten und als Befund im Daten-Checker.
→ [Handbuch → Cockpit → Jahr/Gesamt](HANDBUCH_BEDIENUNG.md#24-jahrgesamt)

### … und der Verlauf darunter zeigt diesen Monat jetzt auch

**Betrifft dich das?** Dieselbe Lage wie eben — offener Monatsabschluss, **Cockpit → Jahr/Gesamt**.

Die Kachel oben zählte den offenen Monat also mit, der **Verlauf-Chart** darunter aber nicht: acht
Monate in der Kennzahl, **sechs Balken** im Diagramm. Auch der Mini-Balken des Jahres im
Zeitstrahl links fiel dadurch zu kurz aus. Beides holt sich seine Monate jetzt aus derselben
Quelle wie die Kachel.

Was du jetzt siehst:

- **Der Verlauf hat einen Balken je Monat mit Daten** — auch für den, den du noch nicht
  abgeschlossen hast. Erzeugung, Verbrauch und Autarkie stehen darin vollständig.
- **Die Balken im Zeitstrahl** (links, bzw. der Schieber auf dem Handy) vergleichen die Jahre
  wieder in ihrer wirklichen Größe. Bei einem **abgeschlossenen** Jahr mit offenem Monat war dort
  auch die kWh-Zahl zu klein — sie stimmt jetzt.
- **Die Spalten „Vorjahr" und „Ø Jahre"** in der Energie-Bilanz lasen dieselbe Quelle und ziehen mit.

**Ein Monat ohne Zählerstände bleibt einer.** Im Balken fehlen Einspeisung und Netzbezug — die
misst der Zähler, und den trägst du beim Monatsabschluss nach. Was deine Komponenten gemessen
haben (PV, Speicher, Wärmepumpe, E-Auto), ist vollständig da. Monate, in denen gar nichts erfasst
wurde, tauchen weiterhin **nicht** auf — ein Balken aus lauter Nullen wäre keine Auskunft.

**Unverändert:** *Auswertungen → Tabelle* zeigt weiterhin nur Monate mit Monatsabschluss. Das ist
eine Liste zum **Bearbeiten**, und einen Monat ohne Zählerstände gibt es dort nicht zu bearbeiten.

**Was du tun musst: nichts.**
→ [Handbuch → Cockpit → Jahr/Gesamt](HANDBUCH_BEDIENUNG.md#24-jahrgesamt)

### Der Reparatur-Knopf erscheint nicht mehr für Zeiträume, die eedc gar nicht rechnen darf

**Betrifft dich das?** Wenn du eine Komponente auf **inaktiv** gesetzt hast, ein
**Anschaffungsdatum** in der Zukunft trägst oder eine Komponente **stillgelegt** hast — und der
Daten-Checker dir für die Zeit davor bzw. danach „Zähler zugeordnet, Tageswerte fehlen" gemeldet
hat.

Der Befund verglich die gespeicherten Tage mit **allen** Komponenten der Anlage. Die Reparatur
nimmt für jeden Tag aber nur die Komponenten, die an **diesem** Tag gelaufen sind. Wo beides
auseinanderlief, stand eine Lücke samt Knopf **„Tag reparieren"** da — und nach dem Klick stand sie
unverändert weiter da, weil der Lauf für diese Komponente nichts schreiben durfte.

Was du jetzt siehst:

- **Für Zeiträume, in denen eine Komponente noch nicht oder nicht mehr aktiv war, wird nichts mehr
  gemeldet.** Dasselbe gilt für Zeit vor dem Inbetriebnahme-Datum der Anlage.
- **Echte Lücken aktiver Komponenten meldet der Checker unverändert** — der Fix macht ihn nicht
  blind, er nimmt ihm nur die Meldungen ohne Deckung.

**Was du tun musst: nichts.** Beim nächsten Prüf-Lauf verschwinden die betroffenen Meldungen.
→ [Handbuch → Daten-Checker §4.10](HANDBUCH_DATEN_CHECKER.md#410-energieprofil--fehlende-tageswerte)
*(gemeldet von dietmar1968)*

### Die Reparatur sagt jetzt, für welche Komponente sie nichts schreiben konnte

**Betrifft dich das?** Wenn du in der Reparatur-Werkbank oder am Daten-Checker-Befund einen
**einzelnen Tag** neu aggregierst.

Bisher meldete dieser Lauf immer Erfolg und zeigte nur den PV-Wert vor und nach dem Lauf. Ob er für
deine Wärmepumpe oder die Wallbox überhaupt etwas geholt hat, stand nirgends — solange sich die PV
bewegte, sah ein halber Lauf aus wie ein ganzer.

Was du jetzt siehst:

- **Alles geschrieben:** die gewohnte Erfolgsmeldung, ergänzt um „Alle N zugeordneten Komponenten
  tragen einen Wert."
- **Teilweise:** „2 von 3 Komponenten neu geschrieben — ohne Wert blieb: Wärmepumpe."
- **Gar nichts:** ein **Hinweis** statt eines Erfolgs, mit der häufigsten Ursache daneben — kein
  Leistungssensor zugeordnet, oder die Home-Assistant-Historie reicht nicht so weit zurück.

Die PV-Angabe („PV 0,0 → 30,0 kWh" bzw. „blieb unverändert") bleibt erhalten; die Komponenten-Aussage
kommt dazu. Der Bereichs-Lauf sagt dasselbe schon länger je Tag — jetzt sprechen beide dieselbe
Sprache.

**Was du tun musst: nichts.** → [Handbuch → Energieprofil §4](HANDBUCH_ENERGIEPROFIL.md#4-reparatur--pflege)
*(gemeldet von dietmar1968)*

### Die Kachel „Ø-Preis Netz" geht jetzt auf

**Betrifft dich das?** Wenn du in **Cockpit → Monat** auf die Kachel **Ø-Preis Netz** schaust — vor
allem, wenn dein Tarif einen **Grundpreis** hat.

Unter dem Ø-Preis standen bisher die **Gesamtkosten inklusive Grundpreis**. Wer die beiden Zahlen
der Unterzeile durcheinander teilte — und das ist die naheliegendste Probe der Welt —, landete
zwangsläufig daneben: **559 kWh · 210,45 € ergaben 37,6 ct**, während oben 33 ct stand. Der Hinweis
„Kosten inkl. Grundpreis" stand zwar im Tipp-Text, wird aber erst gelesen, wenn man schon
gestolpert ist.

Was du jetzt siehst:

- **Die Unterzeile zeigt die Arbeitspreis-Kosten** (`Netzbezug × Ø-Preis`), im Beispiel also
  184,47 € statt 210,45 €. Teilst du sie durch die kWh, kommen die 33 ct heraus.
- **Der Grundpreis ist nicht verschwunden**, sondern steht in der Herleitung der Kachel
  (Hover/Tipp): „= 184,47 € · + 25,98 € Grundpreis = 210,45 € gesamt".
- **Die Stromrechnung bleibt vollständig** — im Finanzen-Block darunter stehen weiterhin die
  gesamten Netzbezug-Kosten. Es kommt kein Posten weg, er steht nur nicht mehr dort, wo er zur
  falschen Division einlädt.

**Dazu ein Rechenfehler, der beim Nachprüfen auffiel:** Wer einen **flexiblen Tarif** fährt
(Tibber, aWATTar, EPEX), bekam im **laufenden** Monat Kosten und Eigenverbrauchs-Ersparnis mit dem
**festen Arbeitspreis** des Tarifs berechnet statt mit dem tatsächlichen Monatsdurchschnitt — der
Vorjahres-Vergleich und die Detailzeilen je Komponente rechneten längst richtig. Derselbe Monat
trug damit je nach Sicht zwei verschiedene Beträge. **Ab jetzt gilt überall der
verbrauchsgewichtete Monatsdurchschnitt.** Betroffene Monate ändern ihre Euro-Beträge sichtbar —
sie waren vorher falsch.

**Was du tun musst: nichts.** → [Handbuch → Cockpit/Monat](HANDBUCH_BEDIENUNG.md#23-monat)
*(gemeldet von Algie im simon42-Forum)*

### Die exportierten Sensoren zeigen über REST dieselben Zahlen wie über MQTT

**Betrifft dich das?** Nur wenn du eedc-Sensoren per **REST-Plattform** in Home Assistant eingebunden
hast (das YAML-Snippet aus **Einstellungen → Integration → MQTT-Export**). Wer MQTT nutzt, sieht
keine Änderung — dort gilt die Regel seit v4.0.6.

Mit v4.0.6 wurden die Export-Werte auf handliche Längen gebracht: kWh ganzzahlig, Geld auf Cent,
Prozent auf eine Stelle. Diese Regel griff bisher aber nur beim MQTT-Export. Derselbe Sensor kam
über REST weiter mit einer Nachkommastelle an — dieselbe Jahressumme also einmal als `39692` und
einmal als `39692,4`.

Was du jetzt siehst:

- **Beide Wege liefern dieselbe Zahl.** Auf der Demo-Anlage betrifft das 16 von 54 Sensoren; alle
  übrigen waren ohnehin schon gleich. Die Werte werden dabei **kürzer**, nicht anders: aus
  39.692,4 kWh wird 39.692 kWh.
- **Eine Ausnahme wird länger:** die **Vollzyklen** des Speichers standen als glatte `380` im
  Export und tragen jetzt `380,19` — dieselben zwei Nachkommastellen, die dir die Speicher-Kachel
  in eedc längst zeigt.
- **Deine HA-Konfiguration bleibt gültig.** Sensor-Namen, Einheiten und die Anzahl der Entitäten
  ändern sich nicht, das YAML-Snippet auch nicht. Die aufgezeichnete Historie zurückliegender
  Zeitpunkte bleibt stehen, wie sie ist — nur ab jetzt kommen die kürzeren Werte an.

**Was du tun musst: nichts.** Wenn eine deiner Automationen auf eine Nachkommastelle angewiesen war,
lohnt ein Blick — die Größenordnung ändert sich nie, nur die Stellen dahinter.
→ [Sensor-Referenz → Export-Sensoren](SENSOR-REFERENZ.md)

### Der Daten-Checker verlangt von einer Klimaanlage keinen Wärmemengenzähler mehr

**Betrifft dich das?** Wenn du eine **Split-Klimaanlage** als Wärmepumpe der Art *Luft-Luft*
angelegt hast.

Der Daten-Checker meldete dauerhaft „1 Komponente(n) ohne Zusatz-Zähler für Tageswerte — Offen:
Klimaanlage: Heizwärme, Warmwasser". Beide Werte kommen aus einem **Wärmemengenzähler**, und einen
Warmwasserkreis hat ein Split-Gerät gar nicht — der Hinweis war also **nicht auflösbar**. Er
widersprach obendrein dem, was eedc dir beim Anlegen der Komponente selbst zusagt: „Es genügt der
Stromverbrauchs-Sensor."

Der Hinweis erscheint für Luft-Luft-Geräte nicht mehr. **Für klassische Wärmepumpen bleibt er** — er
ist dort ein echter Zuordnungs-Hinweis. Eine Wärmepumpe **ohne** eingetragene Art gilt weiter als
klassische Wärmepumpe; wenn du also eine Klimaanlage hast und den Hinweis noch siehst, trage unter
*Einstellungen → Komponenten* die Wärmepumpenart **Luft-Luft (Klimaanlage)** ein.

**Was du tun musst: nichts** (außer im gerade genannten Fall).
→ [Handbuch → Daten-Checker](HANDBUCH_DATEN_CHECKER.md)

### Zwei Hinweise erklären jetzt, was passiert, wenn du nichts tust

**Betrifft dich das?** Wenn du eine **Wärmepumpe ohne eigenen Wärmestrom-Tarif** hast, oder wenn dir
der Daten-Checker **„PVGIS-Systemverluste ggf. zu hoch"** anzeigt.

Beide Hinweise standen dauerhaft und ließen sich durch keine Eingabe abstellen. Ein Häkchen zum
Wegklicken wird es dafür bewusst nicht geben — ein Hinweis, den man wegklicken kann, ist einer, den
man bald gar nicht mehr liest. Stattdessen sagen die beiden jetzt, was sie eigentlich meinen:

- **„Wärmepumpe rechnet mit dem allgemeinen Tarif"** (bisher „Kein WP-Spezialtarif hinterlegt"):
  Ohne eigenen Wärmestrom-Tarif bewertet eedc den WP-Strom mit deinem allgemeinen Arbeitspreis.
  Hast du einen Einheitstarif, ist das **richtig so und du musst nichts tun** — der Hinweis bleibt
  dann als Information stehen. Hast du einen §14a-Wärmestrom-Tarif, trägst du ihn hier nach.
- **„PVGIS-Systemverluste ggf. zu hoch"**: Der Text sagt jetzt dazu, dass die 14 % eine **Annahme**
  der Prognose sind und keine Messung — und vor allem, **was passiert, wenn du sie senkst**: Deine
  Prognose (das SOLL) steigt, deshalb sinken Performance Ratio und SOLL-Erfüllung in
  *Auswertungen → Prognose vs. IST* und im Jahresbericht. **Deine gemessenen Werte ändern sich
  nicht.** Wirksam wird die Änderung erst, wenn du unter *Solarprognose* eine **neue Prognose
  abrufst** und speicherst; die bisherige bleibt als Historie erhalten und lässt sich jederzeit
  wieder aktivieren. Du darfst die Prognose auch bewusst als konservative Untergrenze stehen lassen.

**Es erscheint und verschwindet dadurch kein Befund** — es ändert sich der Text.
→ [Handbuch → Daten-Checker](HANDBUCH_DATEN_CHECKER.md)

---

## v4.0.6 — Vergleichbares vergleichen, Gemessenes behalten (August 2026)

> **Der Schwerpunkt dieser Version:** An etlichen Stellen stellte eedc zwei Zahlen nebeneinander, die
> gar nicht zueinander gehörten — ein Monat neben dem falschen Vorjahrgang, ein halber Tag neben einem
> ganzen, ein Durchschnitt neben Summen, eine gemessene Stunde neben der Prognose der Stunde davor.
> Diese Version zieht das gerade. **Drei Zahlen bewegen sich dabei sichtbar:** die gestrichelte
> Verbrauchs-Kurve im Live-Chart rückt **nach oben** (sie lag zu tief — das trifft jede frische
> Installation und jeden Betrieb ohne Home Assistant), die Vergleichs-Zelle der Summenzeile wird
> **kleiner**, und der Jahres-Ø-Preis passt sich den kWh und Euro darunter an.
>
> Dazu zwei Reparaturen, bei denen es nicht um Darstellung ging: ein frisch verbundener Connector
> **löschte** den Monatswert, und die Tagesreparatur bot einen Knopf an, der für ältere Tage nicht
> funktionieren konnte. Bei jedem Punkt steht, wen es betrifft und was zu tun ist.

### Werte-Tabelle: über mehrere Jahre stand die falsche Vergleichszahl daneben

**Betrifft dich das?** Wenn du unter **Auswertungen → Tabelle** den Vergleich einschaltest und
dabei einen Zeitraum wählst, der **mehr als ein Jahr** umfasst — insbesondere den Chip
**„Alle Jahre"**. Im Einzeljahr-Modus war nichts davon sichtbar.

Über einen mehrjährigen Zeitraum lagen mehrere Jahrgänge desselben Monats nebeneinander, und eedc
hat sie verwechselt: **jede Zeile bekam den jüngsten davon als „Vorjahr"**. Der Dezember 2025 stand
damit sich selbst gegenüber — zweimal dieselbe Zahl, Δ 0,0 % —, ältere Dezember bekamen einen
Jahrgang aus der Zukunft vorgesetzt. Dasselbe galt für Tageszeilen.

Was du jetzt siehst:

- **Jede Zeile steht ihrem eigenen Vorjahresmonat gegenüber** (Dezember 2025 dem Dezember 2024),
  unabhängig davon, wie lang der gewählte Zeitraum ist.
- **Gibt es diesen Vorjahresmonat nicht**, weil deine Aufzeichnung später beginnt, bleibt die
  Vergleichsspalte **leer („—")**. Es wird kein Ersatzwert eingesetzt und kein Δ von 0,0 % erfunden.
- **Der CSV-Export trägt dieselben Werte wie die Tabelle** — beide beantworten die Frage „womit
  vergleicht sich diese Zeile" jetzt an derselben Stelle im Code.

### Die Summenzeile stellt keine ungleich langen Zeiträume mehr gegenüber

**Betrifft dich das?** Denselben Bereich — und zusätzlich das **laufende Jahr**, dort war es
ebenfalls falsch.

Die unterste Zeile der Tabelle summiert die Spalte über ihr. Ihre **Vergleichs**-Zelle summierte
bisher schlicht alles, was im Vergleichsfenster lag — auch wenn das eine ganz andere Zeitspanne
war: über „Alle Jahre" 37 Monate neben 31, im laufenden Jahr die bisher gelaufenen Monate neben die
vollen zwölf des Vorjahrs. Das las sich als „+23,1 % gegenüber dem Vorjahr" und war keine Aussage
über deine Anlage, sondern über die unterschiedliche Anzahl der Monate.

Jetzt gilt: **die Summenzeile vergleicht nur, wenn jede angezeigte Zeile ein Gegenstück hat.**

- Im **laufenden Jahr** vergleicht sie damit sechs Monate mit denselben sechs Monaten des
  Vorjahrs — die Zahl in der Vergleichs-Zelle wird dadurch **sichtbar kleiner**, und sie stimmt.
- Über **„Alle Jahre"** bleibt die Vergleichs-Zelle leer, weil die ersten Monate deiner
  Aufzeichnung kein Vorjahr haben. **Damit das nicht wie ein Fehler aussieht, steht der Grund
  jetzt unter der Tabelle** — mit der Angabe, wie viele Monate bzw. Tage ohne Gegenstück sind.
  Die Δ-Werte der einzelnen Zeilen stehen unverändert vollständig darüber.
- Die **„aktuell"-Zelle** ist und bleibt die Summe der Spalte über ihr — daran ändert sich nichts.

**Was du tun musst: nichts.** Es ändern sich nur angezeigte Vergleichswerte, keine erfassten Daten.
→ [Handbuch → Bedienung §4.5 Tabelle](HANDBUCH_BEDIENUNG.md#45-tabelle-werte-werkbank) *(gemeldet von Rainer)*

### Monatsabschluss: „weicht ab" meckert nicht mehr die zweite Nachkommastelle an

**Betrifft dich das?** Wenn du im Monatsabschluss (**Einstellungen → Daten → Monatsdaten**) Felder
mit zugeordneter Datenquelle pflegst und dort fast überall der orange Hinweis „Sensor meldet X ·
gespeichert Y" stand — auch nach dem Speichern immer wieder an denselben Stellen.

Die Ursache war eine feste Vergleichsschwelle. Der Sensorwert kommt auf **eine** Nachkommastelle
gerundet an, der gespeicherte Wert trägt zwei — und schon galten **2,3** und **2,33** als
unterschiedlich, obwohl es dieselbe Messung ist. Weil sich daran durch Speichern nichts ändert,
kam der Hinweis nach jedem Öffnen wieder.

Was du jetzt siehst:

- **Verglichen wird mit der Genauigkeit des Sensorwerts.** Eine Nachkommastelle vom Sensor heißt:
  es wird auf eine Nachkommastelle verglichen. Liefert er mehr, wird auf höchstens drei Stellen
  verglichen. Reine Rundungsunterschiede melden sich damit nicht mehr.
- **Echte Unterschiede bleiben markiert.** Stehen z. B. 453,7 gegen 454,74, ist das keine Rundung,
  sondern gut eine Kilowattstunde Differenz — der Hinweis bleibt und ist berechtigt.
- Auch die Liste „andere Quelle" bietet einen Vorschlag nicht mehr an, der dem eingetragenen Wert
  im Rahmen dieser Genauigkeit ohnehin entspricht.

**Was du tun musst: nichts.** Es ändert sich nur, wann der Hinweis erscheint — keine erfassten Werte.
→ [Handbuch → Einstellungen §5.1 Monatsdaten & Monatsabschluss](HANDBUCH_EINSTELLUNGEN.md#51-monatsdaten--monatsabschluss) *(gemeldet von Rainer)*

### Monatsabschluss: „gespeicherten behalten" hält jetzt auch nach dem Speichern

**Betrifft dich das?** Wenn ein Zähler und dein gespeicherter Wert **wirklich** auseinanderlaufen —
also nicht bloß gerundet. Bisher konntest du „gespeicherten behalten" klicken, aber nach dem
Speichern und erneutem Öffnen stand derselbe orange Hinweis wieder da.

Das war mehr als lästig: „weicht ab" zählt in der Kopf-Ampel als **„prüfen"**. Ein Monat mit einer
echten Zähler-Differenz konnte damit nie „alles fertig" erreichen — ein Zustand, aus dem es keinen
Ausweg gab, obwohl der Knopf genau diesen Ausweg versprach.

Was du jetzt siehst:

- **Deine Entscheidung wird gespeichert.** Das Feld gilt als *geprüft* und zählt in der Kopf-Ampel
  als fertig — der Monat lässt sich abschließen.
- **Die Abweichung bleibt trotzdem sichtbar.** Das Etikett sagt „geprüft (weicht vom Sensor ab)",
  darunter steht weiter „Sensor meldet X · gespeichert Y · von dir behalten". Nichts wird
  weggeklickt: wer später wissen will, warum die Zahlen auseinandergehen, sieht es immer noch.
  „Sensorwert übernehmen" bleibt als Rückweg stehen.
- **Gemerkt wird, wogegen du bestätigt hast** — nicht bloß „bestätigt". Meldet der Zähler später
  einen anderen Wert, oder änderst du den gespeicherten Wert, ist die Bestätigung hinfällig und das
  Feld meldet sich wieder. Eine alte Entscheidung kann also keine neue Abweichung verdecken.

Das gilt für die Zählerfelder der Anlage **und** für die Felder deiner Komponenten (PV-Strings,
Speicher, Wärmepumpe, E-Auto, Wallbox …) — sonst hinge der Monat weiter an einer einzelnen
Komponente fest.

**Was du tun musst: nichts.** Bestehende Monate bleiben unverändert; die Bestätigung entsteht erst,
wenn du sie klickst.
→ [Handbuch → Einstellungen §5.1 Monatsdaten & Monatsabschluss](HANDBUCH_EINSTELLUNGEN.md#51-monatsdaten--monatsabschluss) *(gemeldet von Rainer)*

### Ein frisch verbundener Connector setzt den Monatswert nicht mehr auf 0

**Betrifft dich das?** Wenn du einen **Geräte-Connector** einrichtest (Hersteller-Cloud oder Gateway)
und deine PV-Erzeugung gleichzeitig **je Komponente** aus Home Assistant kommt — also der empfohlene
Fall, sobald du PV-Module als Komponenten führst. **Hier ging ein Wert verloren.**

Jedes Feld hat in eedc genau eine maßgebliche Quelle. Meldet eine Quelle die **Anlage als Ganzes**,
sperrt dieser Wert die Summe der Komponenten-Werte — sonst zählte dieselbe Erzeugung zweimal. Genau
das tat ein frisch verbundener Connector: Er meldet einen Anlagen-Gesamtwert, und der ist am Anfang
nur die Differenz zwischen zwei seiner Abrufe. Abends eingerichtet sind das **0,0 kWh** — und dieses
Bruchstück verdrängte die vollständige Summe aus Home Assistant. Der laufende Monat sprang auf 0.

Jetzt unterscheidet eedc, ob ein Wert den **ganzen Monat** abdeckt oder nur ein Stück davon. Ein
Wert, der erst seit heute Abend zählt, sperrt die Komponenten-Summe nicht mehr und wird vom ersten
vollständigen Beitrag ersetzt statt zu ihm addiert — die Doppelzählung, gegen die die Sperre steht,
bleibt damit verhindert. Deckt dein Connector den Monat ab, ändert sich nichts.

**Was du tun musst:** Der **laufende** Monat rechnet sich beim nächsten Aufruf von selbst richtig.
Hast du den 0-Wert damals über den **Monatsabschluss gespeichert**, steht er weiter in deinen
Monatsdaten — den einen Monat einmal öffnen und den Vorschlag übernehmen.
→ [Handbuch → Einstellungen §7 Datenquellen](HANDBUCH_EINSTELLUNGEN.md#7-datenquellen--feld-zentrische-zuordnung) *(#361, aufgefallen bei der Bearbeitung von coolxmads Befund #353)*

### Live „Wetter heute": IST-Kurve und Prognose liegen wieder auf derselben Stunde

**Betrifft dich das?** Wenn du im **Cockpit → Live** den Block **„Wetter heute"** benutzt — also den
Verlauf von PV-Ertrag und Verbrauch mit der gestrichelten Prognose darüber.

Eine Stunde steht in eedc für die Zeit **davor**: Der Punkt bei **11** trägt, was zwischen 10:00 und
11:00 passiert ist — so wie ein Zählerstand um 11:00 die Stunde davor abschließt. Alle
Prognose-Quellen, das Energieprofil und die Auswertungen halten das so. Dieser eine Block hielt sich
nicht daran: Er schrieb im Tooltip „11:00–12:00 Uhr" und legte gleichzeitig seine **gemessene**
PV-Kurve eine Spalte zu früh ab. Wer beide Sichten offen hatte, las für dieselbe Stunde zwei
verschiedene Zeitspannen — und die Prognose sah aus, als käme sie eine Stunde zu spät.

Was du jetzt siehst:

- **Der Tooltip nennt überall dieselbe Zeitspanne** („10:00–11:00 Uhr" am 11-Uhr-Punkt), im Cockpit
  wie unter Auswertungen → Prognose.
- **Die gemessene Kurve liegt Spalte für Spalte neben der Prognose** derselben Stunde. Die
  Abweichung, die du siehst, ist ab jetzt die echte Prognose-Abweichung und kein Zeitversatz.
- **Die laufende Stunde erscheint nicht mehr als Einbruch.** Bisher wurde die gerade erst
  angefangene Stunde als vollständiger Mittelwert gezeichnet; jetzt endet die IST-Kurve mit der
  letzten vollständigen Stunde.
- **Sonnenauf-/-untergang, Sonnenhöchststand und das hervorgehobene Wettersymbol** stehen in der
  Stunde, die den Zeitpunkt wirklich enthält (05:56 Uhr gehört zu 05:00–06:00).

**Frisch eingerichtet oder ohne Home Assistant: auch die gestrichelte Verbrauchs-Kurve lag eine
Stunde zu früh.** eedc lernt dein typisches Verbrauchsprofil aus den letzten sieben Tagen. Solange
es dafür noch keine eigenen Aufzeichnungen hat, nimmt es die Werte direkt aus Home Assistant oder —
im Standalone-Betrieb — aus den MQTT-Daten, und diese beiden Wege ordneten die Stunden vorwärts zu.
Nach ein paar Tagen Aufzeichnung stimmte die Kurve von selbst; jetzt stimmt sie ab der ersten
Stunde. **Bestehende Anlagen waren nie betroffen.**

**Dieselben beiden Wege rechneten die Stunde außerdem zu niedrig — hier bewegt sich die Kurve
sichtbar.** Im Standalone-Betrieb wurde nur der Verbrauch zwischen dem ersten und dem letzten
Messpunkt **innerhalb** der Stunde gezählt; das letzte Stück bis zum Stundenschlag fiel jedes Mal
heraus, bei einem Messpunkt alle fünf Minuten rund **8 %**. Und beim Weg über Home Assistant zählte
eine Stunde, für die gar keine Aufzeichnung vorlag, als **gemessene Null** und zog den Durchschnitt
nach unten — ein einziger Tag ohne Daten drückte jede Werktags-Stunde auf vier Fünftel. Beides ist
behoben: Gemessen wird jetzt von Stundengrenze zu Stundengrenze, und **eine Stunde ohne Messung
wird ausgelassen statt als Null gezählt**. Bleibt für eine Stunde gar nichts übrig, setzt eedc dort
seinen Standardwert ein und behauptet nicht, du hättest nichts verbraucht. **Deine gestrichelte
Verbrauchs-Kurve liegt dadurch höher als vorher — sie lag zu tief.**

**An deinen erfassten Daten ändert sich nichts.** Tagessummen, Kacheln und alle Auswertungen
bleiben, wie sie waren; betroffen ist allein die gelernte Verbrauchs-Prognose im Live-Chart.
→ [Handbuch → Prognosen §3 Wo die Prognosen erscheinen](HANDBUCH_PROGNOSEN.md#3-wo-die-prognosen-in-der-app-erscheinen) *(gemeldet von Rainer)*

### Stundenvergleich: die Σ-Zeile vergleicht nur noch den bisher gelaufenen Tag

**Betrifft dich das?** Wenn du unter **Auswertungen → Prognose** in die Tabelle
**„Stundenvergleich heute"** schaust. **Hier ändert sich eine angezeigte Zahl.**

Ganz unten in der Tabelle steht die Σ-Zeile. Sie summierte bisher die Prognose des **ganzen** Tages
und stellte sie dem IST **bis jetzt** gegenüber. Mittags las sich das an einer Beispielanlage als
`Σ 78,1 ▲ 52,0` gegen `IST 26,1` — eine Abweichung von 52 kWh, die vor allem aussagte, dass der Tag
noch nicht vorbei war. Am Abend schrumpfte dieselbe „Abweichung" von allein wieder zusammen.

Jetzt vergleicht die Zeile **dieselben Stunden auf beiden Seiten** — bis zur letzten Stunde, für die
eine Messung vorliegt. Aus denselben Daten wird damit `Σ 30,2 ▲ 4,1 (16 %)` gegen `IST 26,1`, und
darunter steht, worauf sich das bezieht: **`bis 13:00`**. Die **prozentuale** Abweichung ist neu.

- **Die Σ-Zeile ist damit nicht mehr die Tagesprognose** — die steht unverändert in den Kacheln
  oben („Heute"), zusammen mit „Verbleibend".
- **Ist der Tag durch**, entfällt die Kennzeichnung und die Zeile zeigt wieder die vollen
  Tagessummen — wie bisher.
- **Für einen Tag ohne jede Messung** steht dort die Prognosesumme und **keine** Abweichung. Ein
  „0 %" gegen ein IST, das es noch gar nicht gibt, wäre eine Behauptung.

**Und die Abweichungen in den Stundenzeilen darüber sind jetzt vollständig.** Bisher blendete eedc
sie aus, wenn sie sehr klein waren — das traf je Spalte unterschiedlich zu, und in derselben Zeile
trugen OpenMeteo und Solcast eine Abweichung, die eedc-Spalte daneben nicht. Das sah aus, als fehlte
ein Wert. **Sobald für eine Stunde ein IST vorliegt, steht die Abweichung in jeder Prognosespalte** —
ein Volltreffer heißt jetzt sichtbar `± 0,0`. Bleibt eine Spalte leer, heißt das eindeutig: für
diese Stunde gibt es noch keine Messung.

**Was du tun musst: nichts.** Es ändert sich nur, was verglichen wird — an deinen erfassten Daten
und an allen anderen Kennzahlen ändert sich nichts.
→ [Handbuch → Prognosen §3 Stundenvergleich heute](HANDBUCH_PROGNOSEN.md#stundenvergleich-heute--was-die-abweichungen-sagen) *(gemeldet von Rainer)*

### Cockpit → Jahr: der Ø-Preis passt wieder zu den kWh und Euro darunter

**Betrifft dich das?** Wenn deine Strompreise über das Jahr geschwankt haben — durch einen
Tarifwechsel oder einen dynamischen Tarif — und du im **Cockpit → Jahr** auf die Kachel
**„Ø-Preis Netz"** (bzw. die Einspeisevergütung daneben) schaust. **Hier ändert sich eine
angezeigte Zahl.**

In einem gemeldeten Fall stand in derselben Kachel oben **28,0 ct** und darunter
**„559 kWh · 210,45 €"** — das sind rechnerisch 37,6 ct. Zwei Zahlen, eine Kachel. Die Ursache: Der
Jahresdurchschnitt war das **ungewichtete Mittel der zwölf Monatspreise**, während kWh und Euro
darunter Summen sind. Ein teurer Januar mit 400 kWh wog damit genauso viel wie ein billiger Juli mit
20 kWh.

Jetzt zählt jeder Monat **mit der Menge, die in ihm geflossen ist**. Der Durchschnitt oben und die
Summen darunter beschreiben damit dieselbe Rechnung. Monate ohne Menge fallen aus beiden Summen
heraus. Dasselbe gilt für den Ø-Wert der Einspeisevergütung.

**Und das grüne „Aktuell"-Badge markiert wieder genau einen Tarif.** Unter **Einstellungen →
Strompreise** trug es bisher **jeder** Tarif ohne Enddatum — bei drei aufeinander folgenden Tarifen
also dreimal. Es zeigt jetzt den Tarif, mit dem eedc heute tatsächlich rechnet: gültig am heutigen
Tag und je Verwendung der jüngste. **Standard- und Spezialtarif** (Wärmepumpe, Wallbox) können
weiterhin gleichzeitig aktuell sein — das sind verschiedene Verwendungen.

**Was du tun musst: nichts.** Beides ist reine Anzeige — deine Kosten, Erträge und der Netto-Ertrag
wurden nie aus dieser Kachel gerechnet und ändern sich nicht.
→ [Handbuch → Einstellungen §2.2 Strompreise](HANDBUCH_EINSTELLUNGEN.md#22-strompreise) *(gemeldet im Forum von Algie)*

### Datenquellen: das Speicher-Feld „Ladung" heißt auch dort, wie es gemeint ist

**Betrifft dich das?** Wenn du einen **Speicher** hast, dessen Wechselrichter die Ladung getrennt
nach PV-Anteil und Netzanteil meldet (z. B. Kostal Plenticore mit `charge_from_pv` und
`charge_from_grid`). **Hier kann eine Zahl falsch erfasst worden sein.**

Auf der Zuordnungs-Fläche standen **„Ladung"** und **„Netzladung"** untereinander — das liest sich
wie zwei Hälften, die man zusammensetzt. Gemeint ist es anders: **„Ladung" ist die Gesamtmenge,
Netzladung eingeschlossen**, und „Netzladung" sagt nur, wie viel *davon* aus dem Netz kam. Wer den
PV-Anteil auf „Ladung" legte, verlor die Netzladung in der Gesamtmenge und zählte sie zugleich
doppelt (im gemeldeten Fall 421 statt der gemessenen 494 kWh).

Das eindeutige Label **„Ladung (gesamt, inkl. Netz)"** gibt es im Monatsabschluss schon länger — die
Datenquellen-Fläche zeigte es nur nicht an. Jetzt sagen beide Flächen dasselbe.

**Zweitens: „Ø Ladepreis" wird nicht mehr als zuordenbares Feld angeboten.** Es ist ein Monatswert in
ct/kWh, für den es gar keinen Sensor- oder Topic-Weg gibt — ein zugeordneter Sensor bewirkte nichts,
löste aber eine Daten-Checker-Meldung aus. Erfassen kannst du ihn weiterhin im **Monatsabschluss**,
per **CSV-Import** und über den **errechneten Vorschlag** bei dynamischem Tarif. Hast du heute eine
Quelle darauf gesetzt, siehst du das Feld weiter und kannst sie über **Keine** entfernen.

**Was du tun musst:** Wenn auf „Ladung" nur dein **PV-Ladezähler** liegt, stell das Feld auf einen
Zähler um, der **PV und Netz zusammen** führt. Liefert dein Gerät die beiden nur getrennt, addierst
du sie in Home Assistant zu einem Helfer und ordnest diesen zu. **Bestehende Zuordnungen ändert eedc
nicht von selbst** — sonst verschwände eine Einstellung, die du bewusst gesetzt hast.
→ [Handbuch → Einstellungen §7.3 Was muss zugeordnet werden](HANDBUCH_EINSTELLUNGEN.md#73-was-muss-zugeordnet-werden--und-was-nicht) *(gemeldet im Forum von MartyBr)*

### „Tag neu aggregieren" reicht jetzt so weit zurück wie Home Assistant

**Betrifft dich das?** Wenn der Daten-Checker Tage ohne Werte meldet, die **länger als rund zehn Tage**
zurückliegen, und der angebotene Reparatur-Knopf mit *„keine Live-/MQTT-Daten gefunden"* abbrach.

Der Daten-Checker prüft 90 Tage weit zurück und findet die Lücken in der HA-**Langzeitstatistik**.
Die Reparatur holte ihre Stundenkurve aber aus der HA-**Historie** — und die hebt Home Assistant
standardmäßig nur zehn Tage lang auf. Für ältere Tage stieg der Lauf aus, **bevor** er die Zähler
überhaupt anfasste. Im gemeldeten Fall: 39 Tage zwischen dem 16.06. und dem 30.07., jeder mit einem
Knopf, der nicht funktionieren konnte. **Falsch war das Angebot, nicht deine Bedienung.**

Findet die Reparatur auf dem regulären Weg nichts, holt sie dieselbe Stundenkurve jetzt aus der
**Langzeitstatistik** — demselben Weg, den „Lücken aus HA-LTS nachfüllen" seit jeher nutzt. Das gilt
für **„Tag neu aggregieren"** und für **„Mehrere Tage neu aggregieren"**.

**Und wenn es trotzdem nicht geht, sagt die Meldung, woran es liegt** — statt pauschal „keine Daten":

- **keine Leistungs-Zuordnung** — dann führt der Weg zu Datenquellen, dort fehlt eine Quelle;
- **Home Assistant nicht erreichbar** — ein Verbindungsproblem, später erneut versuchen;
- **Home Assistant hat für diesen Tag selbst nichts** — dann lässt sich der Tag nicht füllen. Das ist
  keine Fehlfunktion: was HA nie aufgezeichnet hat, kann eedc nicht nachholen.

**Was du tun musst:** Wenn du gemeldete Lücken bisher vergeblich zu reparieren versucht hast — probier
es noch einmal. **„Lücken aus HA-LTS nachfüllen" verhält sich unverändert** und bleibt strikt
additiv: bestehende Tage werden nicht überschrieben.
→ [Handbuch → Energieprofil §4 Reparatur & Pflege](HANDBUCH_ENERGIEPROFIL.md#4-reparatur--pflege) *(gemeldet im Forum von dietmar1968)*

### Daten-Checker: ein Anlagen-Ausbau ist keine Einspeise-Anomalie

**Betrifft dich das?** Wenn du deine Anlage **in Stufen erweitert** hast und der Daten-Checker seither
meldet: *„Einspeisung > 3× Vorjahr"*.

Diese Prüfung vergleicht jeden Monat mit demselben Monat des Vorjahrs — dahinter steht der Verdacht
auf einen Eingabefehler (Faktor 10) oder einen Zählertausch ohne Reset. Wer 2024 aber mehr Module am
Netz hatte als 2023, erzeugt den Sprung selbst. Und weil der Vergleich an den Monatsdaten hängt und
nicht an einem Zeitfenster, wären diese Meldungen **nie von allein verschwunden**: im gemeldeten Fall
drei Stück, die niemand beheben konnte.

Die Prüfung setzt für ein Monatspaar jetzt aus, wenn die **installierte Erzeugerleistung** zwischen
den beiden Monaten um mindestens **10 %** gewachsen ist.

**Warum aussetzen statt die Schwelle mitwachsen zu lassen:** Die Einspeisung ist eine Differenz —
Erzeugung minus Eigenverbrauch. Bleibt dein Verbrauch gleich, landet vom Zubau fast alles im Netz. Im
gemeldeten Fall wuchs die Anlage auf das Vierfache, die Mai-Einspeisung auf das Fünfzehnfache
(61 → 888 kWh). Eine aus der kWp abgeleitete Schwelle wäre geraten und hätte genau diesen Fall auch
nicht gefangen.

**Nur für die Einspeisung.** Beim **Netzbezug** wäre ein PV-Zubau die falsche Erklärung: der sinkt mit
mehr PV und steigt mit neuen Verbrauchern (Wärmepumpe, E-Auto, Wallbox). Dort bleibt die Meldung.

**Was du tun musst: nichts** — die Meldungen verschwinden beim nächsten Prüflauf.
→ [Handbuch → Daten-Checker §4.5 Monatsdaten – Plausibilität](HANDBUCH_DATEN_CHECKER.md#45-monatsdaten--plausibilitaet) *(gemeldet von kingcap1, #354)*

### Daten-Checker: fehlt einem Zähler die Statistik, führt der Weg jetzt über die HA-Oberfläche

**Betrifft dich das?** Wenn der Daten-Checker meldet, dass ein zugeordneter Zähler **nicht in der
Home-Assistant-Langzeitstatistik** steht oder **keine Summen-Spalte** führt.

Bisher riet der Hinweistext zuerst dazu, die `configuration.yaml` zu öffnen und dort `state_class`
nachzutragen. Das setzt voraus, dass du Textdateien in Home Assistant pflegst — und viele tun das
bewusst nicht.

Was du jetzt liest: Der empfohlene Weg ist ein **Verbrauchszähler-Helfer über die Oberfläche**
(**Einstellungen → Geräte & Dienste → Helfer**) auf den vorhandenen Sensor — **ohne Zyklus**, also
mit Zurücksetzen „nie". Der Helfer bringt die nötigen Angaben von sich aus mit, und sein Name bleibt
derselbe, wenn du später das Gerät tauschst; du wechselst dann nur die Quelle. Der YAML-Weg steht
weiterhin da, aber als Nebensatz für alle, die ihn ohnehin gehen.

**Ein Hinweis gehört dazu:** Ein neuer Helfer **beginnt bei null** — vergangene Monate sammelt Home
Assistant nicht nach. Das ist keine Eigenart des Helfers, das gilt für jeden Weg.

**Das gilt jetzt für alle vier Meldungen dieser Prüfung.** Eine davon nannte bisher überhaupt keinen
Weg, sondern nur das Ziel („`state_class: total_increasing` setzen") — wer sie las, wusste hinterher,
*was* fehlt, aber nicht, *wie* man es behebt. Und die beiden Meldungen zur fehlenden Summen-Spalte
standen bis jetzt gar nicht im Handbuch; die Melde-Tabelle ist vollständig.

**Was du tun musst: nichts.** Es ändert sich nur der Text im Daten-Checker, keine Zahl und keine
Zuordnung.
→ [Handbuch → Daten-Checker §5.1 state_class-Probleme beheben](HANDBUCH_DATEN_CHECKER.md#51-state_class-probleme-bei-ha-sensoren-beheben) *(gemeldet von Rainer)*

### HA-Export: kurze Zahlen statt Nachkommastellen für jede Größe

**Betrifft dich das?** Wenn du die eedc-Sensoren per **MQTT** an Home Assistant übergibst
(**Einstellungen → Integration → MQTT-Export**).

Bisher bekam jeder Sensor dieselben zwei Nachkommastellen — auch dort, wo sie nichts aussagen: bei
einer Jahres-Erzeugung von 12.345,67 kWh sind die beiden letzten Stellen reine Anzeige-Länge.

Was du jetzt siehst — gerundet wird **nach Größenart**:

- **Energie und Mengen** (kWh, kWh/kWp, km, kg CO₂) — **ganze Zahlen**.
- **Geld** (€) — zwei Stellen, also auf den Cent.
- **Prozent** — eine Stelle.
- **Leistung** (kW) und die übrigen Kennwerte (COP, Zyklen, Rang) — zwei Stellen.

**Kleine Werte verschwinden dabei nicht.** Ein Wert, der beim Runden auf 0 fiele, obwohl er nicht 0
ist, bekommt so viele Stellen wie nötig — aus 0,35 kW wird keine 0, und die Rest-Prognose am Abend
bleibt sichtbar.

**Was du tun musst: nichts.** Sensor-Namen, Einheiten und die Anzahl der Entitäten sind unverändert;
es ändert sich nur die Länge der Zahl. Deine bisherige HA-Historie bleibt, wie sie ist.
→ [Sensor-Referenz §11 Export-Sensoren](SENSOR-REFERENZ.md#11-export-sensoren-eedc--ha) *(gemeldet von Rainer)*

---

## v4.0.5 — Eine Zahl je Kennwert: Preise je Monat, CO₂ auf dem Eigenverbrauch (Juli 2026)

> **Der Schwerpunkt dieser Version:** An mehreren Stellen nannten zwei Sichten dieselbe Größe und
> zeigten trotzdem zwei verschiedene Zahlen — beim Netto-Ertrag, bei der CO₂-Einsparung, beim
> Strompreis eines vergangenen Monats. Diese Version zieht sie zusammen. **Einige Zahlen bewegen
> sich dadurch sichtbar.** Bei jedem Punkt steht, wen es betrifft und in welche Richtung es geht.

### Strompreise: jeder Monat rechnet mit dem Tarif, der damals galt

**Betrifft dich das?** Wenn du deinen Tarif **nach** dem Import deiner Historie angelegt hast oder
seither eine **Preiserhöhung** eingetragen hast.

An mehreren Stellen nahm eedc bisher den **heute** gültigen Tarif und rechnete damit auch die
Vergangenheit. Eine Preiserhöhung schrieb so rückwirkend die ganze Historie um. Jetzt gilt für jeden
Monat der Tarif, der in diesem Monat gültig war.

Was du davon merkst:

- **Monatsbericht sowie die Wärmepumpen- und Speicher-Karte** rechnen je Monat. Die
  Wärmepumpen-Karte hat bisher die Energien der gesamten Laufzeit summiert und einmal mit dem
  heutigen Preis multipliziert.
- **Cockpit → Tag** nutzt jetzt denselben abgerechneten Monatsdurchschnitt wie Monat und Jahr. Wer
  einen dynamischen Tarif hat und diesen Durchschnitt pflegt, sah dort bisher den Referenzpreis —
  die Summe der Tage passte nicht zum Monat, und „Ø-Preis Netz" nannte je Ebene eine andere Zahl.
- **Auswertungen → Aussichten** bewerten die zurückliegenden Monate ebenfalls mit dem damaligen
  Preis, die entgangene Einspeisevergütung eingeschlossen. Die Hochrechnung nach vorn bleibt beim
  heutigen Tarif — dort ist er richtig.

Und damit der Fall gar nicht erst entsteht:

- **Beim ersten Tarif einer Anlage** schlägt „Gültig ab" jetzt das **Inbetriebnahme-Datum** vor statt
  „heute" — so macht es der Einrichtungs-Assistent seit jeher. Ab dem zweiten Tarif bleibt „heute"
  richtig, das ist ein Tarifwechsel. Am Feld steht der Hinweis, dass frühere Monate mit dieser
  Vorbelegung rechnen.
- **Der Daten-Checker meldet Monate ohne Tarif-Abdeckung** — mit ihrer Anzahl und dem Hinweis, dass
  eedc dort mit der 30-ct-Vorbelegung rechnet. Die Prüfung gab es schon, sie hing aber am
  Inbetriebnahme-Datum der Anlage und wurde bei frischen Installationen still übersprungen.
- **Das Feld „Ø Strompreis" im Monatsabschluss** richtete sich nach deiner **heutigen** Vertragsart.
  Wer von dynamisch auf fest gewechselt ist, kam an den abgerechneten Durchschnitt eines Altmonats
  nicht mehr heran. Jetzt entscheidet der Monat, um den es geht.

**Was du tun musst: nichts.** Deine gepflegte Tarif-Historie wirkt ab jetzt rückwärts mit.

### Speicher: der Börsenpreis ist kein Ladepreis

**Betrifft dich das?** Wenn du einen Speicher hast, ihn aus dem Netz lädst und **keinen Preis-Sensor**
dafür zugeordnet hast.

Die Kachel **„Batterieladung Netz"** zeigte in einem gemeldeten Fall 6,4 ct/kWh, während der Betreiber
28,67 ct zahlt. Ohne zugeordneten Preis-Sensor sprang der **EPEX-Börsenpreis** als Stundenpreis ein —
gedacht als Näherung für dynamische Tarife, bei einem Festpreis aber schlicht der falsche Preis. Er
gewann zudem gegen den von Hand eingetragenen Wert.

Der Börsenpreis kommt jetzt nur noch bei **ausdrücklich dynamischem Tarif** zum Einsatz; sonst rechnet
eedc mit deinem gepflegten Ladepreis und ersatzweise mit dem Arbeitspreis. **Deine ausgewiesenen
Ladekosten steigen dadurch auf den Wert, den du tatsächlich zahlst.**

**Wenn du einen dynamischen Tarif hast**, trag ihn unter **Einstellungen → Strompreise** mit der
Vertragsart **„Dynamischer Tarif"** ein — sonst rechnet eedc ab jetzt mit deinem
Referenz-Arbeitspreis statt mit dem Börsenpreis. Das Feld ist ein optionales Auswahlfeld und bei
vielen Anlagen leer.

Dazu passend: Die Kachel behauptete pauschal „aus der Strompreis-Mitschrift", auch wo der Preis aus
dem Tarif kam. Sie nennt jetzt die tatsächliche Herkunft — und sagt „Herkunft unbekannt", statt zu
raten.

### Der Strompreis-Sensor lässt sich wieder zuordnen

**Betrifft dich das?** Wenn du einen **dynamischen Tarif** (Tibber, aWATTar, EPEX) hast und den
stündlichen Preis aus Home Assistant mitschreiben willst.

Bis v3 gab es dafür im Sensor-Mapping-Wizard einen Slot „Strompreis". Mit der neuen Oberfläche ist er
ersatzlos entfallen — das Backend las ihn weiter, neu zuordnen ging aber nicht mehr. Unter
**Einstellungen → Datenquellen** steht er jetzt wieder zur Verfügung. **Bestehende Zuordnungen aus v3
waren nie betroffen** und tauchen mit dem Slot wieder auf.

Drei Dinge dazu:

- Er erscheint **nur bei dynamischem Tarif**. Bei einem Festpreis gehört der Preis in die Stammdaten;
  ein angebotener Preis-Slot verleitet sonst dazu, sich einen Konstanten-Sensor zu bauen.
- Er ist **nur über Home Assistant** belegbar. Über MQTT kommt kein Preis herein, und ein erwartetes
  Topic, das niemand bedient, hätte in der Abdeckungs-Prüfung eine Lücke gemeldet, die sich nicht
  schließen lässt.
- Er speist die **Strompreis-Mitschrift**: den Ø-Bezugspreis und den Ø-Ladepreis der
  Speicher-Netzladung.

### Netto-Ertrag: vier Sichten, eine Zahl

**Betrifft dich das?** Zwei Gruppen: Anlagen mit **Regelbesteuerung** und Anlagen mit einem
**Balkonkraftwerk**.

**Bei Regelbesteuerung** zogen bisher nur das Cockpit und die Jahres-Prognose der Aussichten die
Umsatzsteuer auf den Eigenverbrauch ab. **Jahresbericht-PDF, der HA-Sensor `netto_ertrag_euro` und die
bisherigen Erträge der Aussichten** taten es nicht — diese drei Zahlen lagen um den vollen USt-Betrag
zu hoch (im Testfall 68,40 € auf 212 €). Sie **sinken** jetzt auf den Wert, den das Cockpit schon
vorher nannte. Weil die bisherigen Erträge den ROI-Fortschritt tragen, bewegen sich Amortisation und
Break-Even-Jahr mit.

**Beim Balkonkraftwerk** hatte jede der vier Sichten die beiden Erfassungswege anders kombiniert: die
Aussichten zählten den Eigenverbrauch doppelt, Cockpit und PDF ließen ein Balkonkraftwerk **ohne**
erfasste Erzeugung ganz weg, und der HA-Sensor trug die BKW-Ersparnis gar nicht. Jetzt entscheidet
eedc je Gerät und Monat, welcher der beiden Werte trägt. **Die Richtung hängt an deiner Erfassung:**
wer Erzeugung **und** Eigenverbrauch pflegt, sieht in den Aussichten weniger — die Doppelzählung ist
weg; wer nur den Eigenverbrauch pflegt, sieht in Cockpit, PDF und HA-Sensor mehr.

**Anlagen ohne Regelbesteuerung und ohne Balkonkraftwerk sind unverändert.**

### Dienstwagen: der Firmenwagen bringt der Anlage keinen Gewinn mehr

**Betrifft dich das?** Nur wenn du ein **E-Auto als Firmenwagen** oder eine Wallbox mit
**„ausschließlich dienstliches Laden"** erfasst hast. Alle anderen Anlagen sind unberührt.

Wer PV-Strom in einen Firmenwagen lud, bekam ihn bisher als eingesparten Netzbezug gutgeschrieben
(30 ct) und zahlte nur die entgangene Einspeisevergütung dagegen (8 ct) — netto 22 ct Gewinn je
Kilowattstunde, die das Haus nie verbraucht hat. In der Beispielrechnung stand die Anlage **mit**
Dienstwagen damit über derselben Anlage ohne Auto: verschenkter Strom war profitabler als verkaufter.

Der dienstlich geladene Strom wird jetzt mit dem Netzbezugspreis gegengerechnet. Im gemessenen
Beispiel fällt der Netto-Ertrag von 196 € auf 152 €; die Anlage ohne Auto liegt mit 168 € dazwischen,
wo sie hingehört. Die Erstattung deines Arbeitgebers steht weiterhin als Ertrag daneben — erst der
**Saldo** ist dein Vorteil.

**Eigenverbrauch, Eigenverbrauchsquote und Autarkie bleiben exakt gleich.** Der Strom ist hinter dem
Zähler verbraucht worden, daran rüttelt niemand — korrigiert ist ausschließlich die Bewertung in Euro.

Dieselbe Korrektur greift an drei weiteren Stellen, die das Kennzeichen bisher übersahen:

- **Komponenten → E-Auto und → Wallbox** wiesen den Dienstwagen voll als private Ersparnis aus — in
  seiner eigenen Karte und, weil die Ladung anteilig verteilt wird, zusätzlich in der Ersparnis der
  privaten Fahrzeuge und jeder Wallbox. Das Fahrzeug bleibt mit allen gemessenen Größen sichtbar
  (Kilometer, Ladung, PV-Anteil); nur seine Euro- und CO₂-Ersparnis steht auf 0 und ist als dienstlich
  gekennzeichnet.
- **Der HA-Sensor `netto_ertrag_euro`** zog die dienstlichen Ladekosten gar nicht ab, während Cockpit
  und Aussichten es taten. Er nennt jetzt dieselbe Zahl wie die Kachel daneben.
- **Ein dienstliches Fahrzeug, das ins Haus entlädt** (V2H), zählte in den HA-Sensoren als privater
  Eigenverbrauch.

**Was du tun musst: nichts.** Die Korrektur wirkt beim nächsten Aufruf.

### CO₂: eine neue Sicht — und die alte Zahl daneben war zu hoch

**Neu in Cockpit → Jahr/Gesamt: der Block „CO₂-Bilanz".** Er zeigt Monat für Monat, wie viel CO₂ deine
Anlage vermieden hat, getrennt nach den drei Quellen: **PV-Eigenverbrauch** (vermiedener Netzstrom),
**Wärmepumpe** (vermiedene fossile Wärme) und **E-Mobilität** (vermiedener Kraftstoff). Die Autarkie
desselben Monats läuft als Linie mit. Wie jeder Block lässt er sich auf Vollbild stellen, dort auf
**Tabelle** umschalten und als CSV exportieren. Darüber stehen zwei Kennwerte: „CO₂ eingespart" ist
die Summe des **gewählten Jahres**, „CO₂ kumuliert" die **gesamte Historie**.

**Nicht zu verwechseln mit der CO₂-Amortisation** unter Auswertungen → CO₂: die beantwortet, wann die
Herstellungs-CO₂ deiner Komponenten wieder eingespielt ist, und rechnet immer über die ganze Laufzeit.
Der neue Block beantwortet, wann du wie viel gespart hast.

**Und damit zur Korrektur — sie betrifft jede Anlage:** *Gespart ist, was du selbst verbraucht hast.*
Eingespeister Strom spart bei dir kein CO₂; er verdrängt Netzstrom beim Abnehmer, nicht in deinem
Haus. Die Seite **Auswertungen → CO₂** und die Spalte **CO₂-Einsparung** in **Auswertungen → Tabelle**
rechneten bisher auf der **gesamten Erzeugung** und schrieben damit auch der eingespeisten
Kilowattstunde die volle Vermeidung gut.

**Die Zahl dort wird kleiner** — bei einer Anlage, die etwa die Hälfte einspeist, ungefähr um die
Hälfte. **Das ist eine Korrektur, keine Verschlechterung: deine Anlage hat nicht weniger gespart, sie
hat nie so viel gespart, wie dort stand.** Gleichzeitig kommt etwas dazu: **Wärmepumpe und
E-Mobilität zählen auf dieser Seite jetzt mit** — sie fehlten dort bisher ganz. Wer beides hat, sieht
die Differenz entsprechend kleiner ausfallen.

**Was sich nicht ändert:** Eigenverbrauch, Autarkie, alle Euro-Werte — und der **CO₂-Sensor in Home
Assistant**. Der rechnete schon vorher richtig; er war es, von dem die Seite abwich. Auswertungen →
CO₂, der neue Block in Cockpit → Jahr und der HA-Sensor nennen ab jetzt dieselbe Zahl. Vorher waren es
drei.

**Eine Feinheit für die Tabelle:** Die Spalte heißt jetzt **„CO₂-Einsparung (PV)"** und zeigt bewusst
nur den PV-Anteil — für Monate wie für Tage, damit sich Tageszeilen zum Monat aufaddieren. Erzeugte
Wärme und gefahrene Kilometer erfasst eedc nur monatlich; sie lassen sich nicht auf einzelne Tage
herunterbrechen. Die vollständige Bilanz steht auf der CO₂-Seite.

### Balkonkraftwerk mit Akku: ein Weg, und der steht jetzt in der App

**Betrifft dich das?** Nur wenn dein Balkonkraftwerk einen Akku hat (Zendure, Anker SOLIX und
Verwandte).

**Der Akku gehört als eigene Komponente erfasst:** neu anlegen, Typ **Speicher**, und unter **Gehört
zu** das Balkonkraftwerk wählen. Dann hat er alles, was ein Hausspeicher auch hat — Live-Leistung,
Ladestand, einen eigenen Knoten im Energiefluss sowie Tages- und Stundenwerte. **Das ging immer schon
so**; neu ist, dass eedc es sagt und dass der **Einrichtungs-Assistent** diese Zuordnung jetzt
ebenfalls anbietet. Bisher fand man sie nur, wenn man später eine Komponente bearbeitete.

**Die beiden Felder „Speicher Ladung/Entladung" direkt am Balkonkraftwerk bleiben, lassen sich aber
nicht mehr auf einen Sensor legen.** Sie kannten nur einen Monatswert; für Tagesverlauf und
Energiefluss hat das nie gereicht. **Gepflegte Werte bleiben vollständig erhalten** und im
Monatsabschluss wie im CSV-Import weiter änderbar — es verschwindet nichts. Wer sie benutzt hat,
findet im **Daten-Checker** einen Hinweis mit dem Umstellungsweg.

**Ein Fehler bei MQTT ist behoben** — die einzige Stelle, an der eine Zahl falsch war: Wer den
BKW-**Eigenverbrauch** per MQTT veröffentlicht hat, bekam ihn auf denselben Kanal gelegt wie die
**Erzeugung**. In der „Heute"-Kachel stand dann der Eigenverbrauch statt der Erzeugung — aus 10 kWh
Erzeugung wurden 4 kWh. Ab dem Update steht die Kachel wieder richtig. **Über Home Assistant
zugeordnete Sensoren waren nie betroffen.**

**Zum Feld „Eigenverbrauch" beim Balkonkraftwerk, damit niemand sucht:** dafür gibt es weiterhin nur
den Monatswert, keinen Tages- oder Live-Wert. Das ist Absicht — normalerweise leitet eedc den
BKW-Eigenverbrauch aus Erzeugung minus Einspeisung ab; das Feld ist die optionale Verfeinerung für
den Fall, dass jemand ihn direkt misst.

### Balkonkraftwerk: die Komponenten-Karte zeigt endlich eine Ersparnis

**Betrifft dich das?** Wenn du ein Balkonkraftwerk hast und — wie vorgesehen — nur seine **Erzeugung**
erfasst.

Unter **Komponenten → Balkonkraftwerk** standen dort bisher **0 € Ersparnis**: die Auswertung
bewertete ausschließlich einen separat gepflegten Eigenverbrauch, und den schreibt weder der Sensor-
noch der MQTT-Pfad. Das Cockpit hat dieselbe Energie auf der Nachbarseite immer bewertet. Jetzt leitet
die Karte den Eigenverbrauch aus der Hausbilanz ab — bei 1.000 kWh Erzeugung und 400 kWh Einspeisung
sind das **180 € statt 0 €**. Steht neben dem Balkonkraftwerk eine Dachanlage, bekommt es seinen
**Anteil** an der Erzeugung: an einem Hauszähler ist nicht messbar, welches Modul die verbrauchte
Kilowattstunde geliefert hat.

**Und sie rechnet mit deinem Strompreis.** Dieselbe Karte hat bisher fest mit **30 ct/kWh** gerechnet,
unabhängig vom gepflegten Tarif und über die ganze Historie mit einem einzigen Preis. Jetzt gilt für
jeden Monat der Tarif, der damals galt. Wer über oder unter 30 ct liegt, sieht die Ersparnis
entsprechend steigen oder fallen.

**Ohne Einspeisezähler sagt die Karte das jetzt.** Ein Balkonkraftwerk ohne Hauszähler-Erfassung
(typisch in der Mietwohnung) hat keine Bilanz, aus der sich ein Eigenverbrauch ableiten ließe. Statt
still **0 €** zu zeigen, weist die Karte diese Monate als **nicht bewertbar** aus. Die Erzeugung steht
unverändert da — nur ihre Bewertung fehlt, und das ist jetzt sichtbar statt geraten.

### PV als ein Gesamtwert gepflegt: Aussichten, Jahresbericht, ROI und Prognose stimmen wieder

**Betrifft dich das?** Wenn du deine PV-Erzeugung als **einen Gesamtwert** pflegst — von Hand
eingetragen oder über einen einzigen PV-Sensor importiert — statt je Modul.

Mehrere Sichten haben diesen Gesamtwert nicht gefunden und mit 0 kWh weitergerechnet:

- **Auswertungen → Aussichten, das Jahresbericht-PDF und der ROI je Investition** zeigten viel zu
  kleine Zahlen, weil die Eigenverbrauchs-Ersparnis dort ganz fehlte. Im Beispiel einer Anlage mit
  1.000 kWh Erzeugung standen **32 € statt 212 €**; der Jahresbericht wies sogar **0 kWh Erzeugung**
  aus und der String-Vergleich eine Abweichung von −100 % gegen die Prognose.
- **Auswertungen → Prognose vs. IST** zeigte für jeden Monat ein IST von **0 kWh** und −100 %
  Abweichung — das sah aus wie ein Totalausfall der Anlage.
- **Die Langfrist-Prognose** fiel ohne gefundene Messwerte auf ihren Standardwert zurück und sagte
  für eine Anlage, die real die Hälfte des PVGIS-Solls liefert, die **volle** Prognose voraus (im
  Testfall 6.000 statt 3.000 kWh im Jahr).

Alle diese Sichten rechnen jetzt mit den tatsächlichen Werten. **Sichtbar steigen** ROI-Fortschritt,
Amortisation, Break-Even-Jahr und der gesamte Jahresbericht. **Cockpit und HA-Sensoren waren nie
betroffen**; wer seine Module einzeln misst, sieht keine Änderung.

**Ein Fall geht nach unten:** Wer **mehrere Module** hat, davon nur einen **Teil** misst und **keinen**
Gesamtwert pflegt, sah in Aussichten und PDF bisher diese Teilsumme als Erzeugung der ganzen Anlage —
im Testfall 92 € statt 32 €. Cockpit und HA-Sensoren haben diesen Fall nie mitgerechnet; die vier
Sichten sagen jetzt dasselbe. **Abhilfe:** entweder alle Module messen oder den Gesamtwert pflegen —
dann zählt wieder alles.

### Community-Vergleich: teilnehmen können jetzt alle, und die geteilte Autarkie stimmt

**Anlagen mit einem PV-Gesamtwert konnten bisher gar nicht teilen.** eedc fand für sie keine Erzeugung,
schickte eine leere Monatsliste los und bekam vom Community-Server „Keine Monatsdaten vorhanden. Bitte
zuerst Daten erfassen." zurück — auch dann, wenn jahrelang gepflegte Werte vorlagen. Beim automatischen
Teilen nach dem Monatsabschluss passierte dasselbe stillschweigend. Dieselbe Ursache wie im Punkt
darüber; jetzt sind diese Anlagen im Benchmark dabei.

**Die geteilte Autarkie stimmt wieder mit dem Bildschirm überein.** Wer ein E-Auto mit **V2H**
(Entladung ins Haus) oder einen **weiteren Erzeuger** hinter dem Hauszähler (BHKW, Mini-KWK) hat, hat
eine **zu niedrige** Autarkie übertragen — im Beispiel 85,7 % statt 90,9 % —, während das Cockpit auf
derselben Seite die richtige Zahl nannte. Und ein als **dienstlich** markiertes Fahrzeug zählte im
Benchmark voll mit. Wer weder BHKW noch V2H noch Dienstwagen hat, sieht keine Änderung.

**Bereits übertragene Monate behalten ihre alten Werte**, bis deine Anlage das nächste Mal teilt —
manuell über „Teilen" oder automatisch nach dem nächsten Monatsabschluss. Dann wird der komplette
Verlauf überschrieben.

### HA-Sensoren: stillgelegte Komponenten behalten ihre Historie

**Betrifft dich das?** Wenn du eine Komponente (Speicher, Wärmepumpe, E-Auto …) mit einem
**Stilllegungsdatum** versehen hast.

Die Sensoren in Home Assistant hatten deren Vergangenheit vergessen: Eigenverbrauch, Autarkie,
Netto-Ertrag und die Speicher-Sensoren rechneten so, als hätte es die Komponente nie gegeben. Das
Cockpit hat dieselbe Anlage immer richtig gerechnet — die Sensoren behaupteten also etwas anderes als
der Bildschirm daneben. **Sichtbar ändern sich diese Sensorwerte.** Ein stillgelegtes Gerät zählt
jetzt bis zu seinem Stilllegungsdatum in der Historie mit, danach nicht mehr; deaktivierte Komponenten
(„aktiv: nein") bleiben wie bisher überall ausgeblendet.

### Daten-Checker, Import und Datenquellen: weniger Fehlalarm, keine falschen Werte

- **Preis- und Zählfelder sind keine kWh-Sensoren.** Der Daten-Checker meldete „kWh-Sensor(en) ohne
  Summen-Spalte" für den Ø Ladepreis eines Speichers. Ein Preis-Sensor hat naturgemäß keine
  Summen-Spalte — die Meldung schickte auf eine Fehlersuche, die es nicht gab. Ebenso betroffen waren
  gefahrene Kilometer, Ladevorgänge, die Kosten für externes Laden, der Ladestand und die
  Warmwasser-Temperatur.
- **Der Ladetarif-Hinweis war nicht abstellbar.** Bei vorhandenem E-Auto fragte der Checker nach einem
  Strompreis mit der Verwendung „E-Auto" — die es gar nicht gibt (es gibt allgemein, Wärmepumpe und
  Wallbox). Der Hinweis stand damit dauerhaft bei jedem E-Auto-Besitzer, ohne dass irgendeine Eingabe
  ihn hätte abstellen können. Gemeint war der **Wallbox-Tarif**: die Prüfung zielt jetzt dorthin,
  löst auch bei einer Wallbox ohne E-Auto aus und sagt, womit eedc ohne ihn rechnet.
- **Aus der Home-Assistant-Statistik werden nur noch Zählerfelder gelesen.** Die Monatswert-Pfade
  nahmen jedes zugeordnete Feld als Zählerstand und bildeten „Höchststand minus Tiefststand". Für
  einen Zähler ist das richtig, für ein Preis-Feld ist es die Monats-Spreizung — der Monatsabschluss
  bot diesen Wert sogar mit höherer Konfidenz an als den korrekt gerechneten Vorschlag, und der
  Statistik-Import schrieb ihn dauerhaft weg.
- **Ein frisch eingerichteter Connector überschreibt keinen Monatswert mehr.** Beginnt seine Messung
  mitten im Monat, deckt sie nur einen Teilzeitraum ab — sie überschrieb den gespeicherten Monatswert
  trotzdem und zeigte damit still zu wenig. Im laufenden Monat überschreibt der Connector jetzt nur
  noch, wenn seine Messung am Monatsanfang beginnt; sonst füllt er nur, was ohnehin fehlt. Betroffen
  ist genau der Monat, in dem die Messung anfängt — ab dem Folgemonat rechnet sich alles von selbst.

### Die Social-Media-Textvorlage entfällt

Der kopierfertige Monatstext für Beiträge in Foren oder sozialen Netzwerken („PV-Bilanz Juni 2026 …")
hing am Teilen-Symbol im Kopf des alten Cockpits. Mit der neuen Oberfläche in v4.0.0 ist dieses Symbol
weggefallen und die Funktion war seither nicht mehr erreichbar; jetzt ist sie auch im Programm
entfernt, und das Handbuch beschreibt sie nicht länger.

**Das Teilen mit der Community bleibt vollständig erhalten** — anonymen Benchmark teilen, im Browser
öffnen, wieder zurückziehen: unverändert. Das sind zwei verschiedene Dinge, die beide „teilen" heißen.
**Was du tun musst: nichts.**

---

## v4.0.4 — Lücken nachholen, Balkonkraftwerk, Import und PV je String (Juli 2026)

> **Der Schwerpunkt dieser Version:** eedc sagt jetzt, **warum** eine Sicht leer ist — und stellt,
> wo es geht, den Knopf zum Nachholen daneben. Bisher sah eine Anlage in solchen Fällen von außen
> gesund aus, während Cockpit und Tagesansicht nichts zeigten.

### Leere Tageswerte trotz „alles grün": eedc sagt jetzt, woran es liegt

**Betrifft dich das?** Wenn dein **Live-Dashboard Werte zeigt**, aber **Cockpit → Tag und die
Stundenwerte auf 0 stehen** — und der Daten-Checker trotzdem nichts bemängelt.

Dahinter steckt fast immer eine Kleinigkeit am Sensor: Ein kWh-Zähler braucht in Home Assistant
`state_class: total_increasing`. Steht dort **`measurement`**, merkt sich HA für ihn nur Mittel-,
Min- und Max-Werte — **keine Zählerstände**. eedc kann daraus keine Tages- und Stundenwerte bilden.
Die Live-Ansicht merkt davon nichts, weil sie aus den Watt-Sensoren rechnet; genau deshalb sieht so
eine Anlage von außen gesund aus.

Bisher hat der Daten-Checker nur gefragt, ob der Sensor **überhaupt** in der Langzeitstatistik
auftaucht — und das tut er in diesem Zustand. Jetzt unterscheidet er beide Fälle, nennt die
betroffenen Zähler beim Namen und sagt, was zu tun ist. **Nach der Umstellung** die Tage einmal über
**Einstellungen → Energieprofil-Pflege → Reparatur-Werkbank** neu berechnen — Home Assistant sammelt
die Zählerstände erst ab dem Moment, in dem `state_class` richtig steht.

Besonders häufig betrifft das Zähler, bei denen man `state_class` von Hand nachträgt — die
bitShake-/Tasmota-Lesekopf-Familie setzt von sich aus keines. Für Counter wie die
WP-Kompressor-Starts gibt es eine eigene Meldung: die laufen weiter, nur die Reparatur-Werkzeuge
greifen auf ihnen nicht.

**Wer die `configuration.yaml` nicht anfassen will**, kommt auch ohne sie zu einem brauchbaren
Zähler: In Home Assistant unter **Einstellungen → Geräte & Dienste → Helfer** einen
**Verbrauchszähler** auf den vorhandenen Sensor anlegen — **ohne Zyklus**, also ohne
Zurücksetzen. Der bringt die richtigen Attribute von sich aus mit, und sein Name bleibt auch
dann derselbe, wenn du später das Gerät tauschst (du änderst nur die Quelle). Einen **Zyklus**
(täglich/monatlich) solltest du für eedc **nicht** wählen — bei jedem Zurücksetzen muss eedc den
Sprung erkennen, und das ist eine Fehlerquelle, die du geschenkt bekommst, wenn der Zähler
einfach durchläuft. Ein Hinweis noch: Ein neuer Helfer fängt bei null an, seine Historie beginnt
also mit ihm. *(Danke an Rainer für den Tipp.)*

### Zähler zugeordnet, Tage trotzdem leer: jetzt mit Knopf zum Nachholen

**Betrifft dich das?** Wenn du auf v4.0.3 aktualisiert hast und deine Zuordnung seither wieder
greift — die **zurückliegenden Tage** aber leer geblieben sind.

Das ist kein neuer Fehler, sondern die Nachwirkung: Solange die Zuordnung unsichtbar war, hat für
diese Tage nie eine Auswertung stattgefunden. Der Daten-Checker sagte dazu „Zähler-Abdeckung: OK" —
stimmt ja auch, der Zähler **ist** zugeordnet. Nur half das niemandem weiter.

Jetzt vergleicht eedc die gespeicherten Tage der letzten 90 Tage mit dem, was die
**Home-Assistant-Langzeitstatistik** für dieselben Tage hergibt. Wo HA etwas hat und eedc nichts,
steht im Daten-Checker eine Meldung — **mit dem Knopf gleich daneben**: „Zeitraum neu aggregieren"
für die ganze Lücke (bis 31 Tage pro Durchgang, größere Lücken einfach mehrfach) oder „Tag
reparieren" für einzelne Tage.

Zwei Dinge sagt die Meldung ausdrücklich dazu:

- **Wie weit es zurückreicht.** eedc kann nur holen, was Home Assistant noch hat. Ist die Lücke
  älter als deine HA-Historie, meldet eedc das als Tatsache — und bietet keinen Knopf an, der
  nichts holen könnte.
- **Was repariert wird.** Die Tagesreparatur füllt **Tages- und Stundenwerte**, nicht die
  **Monatswerte**. Für abgeschlossene Monate ist der Weg **Einstellungen → Integration →
  Statistik-Import**: „Vorschau laden" — schon belegte Monate stehen dort unter **„Konflikte"**
  und sind zum **Überschreiben vorausgewählt**. Vor dem Import einmal durchsehen: was hier
  ausgewählt bleibt, wird überschrieben.

Nichts davon läuft beim Start von allein. eedc erkennt es, sagt es — auslösen tust du es.

**Und der Knopf sagt jetzt die Wahrheit über sich selbst.** „Mehrere Tage neu aggregieren" meldete
bisher immer Erfolg, auch wenn kein einziger Tag nachgerechnet werden konnte. Der Lauf braucht
nämlich mehr als den Zählerstand: ohne zugeordneten **Leistungssensor (W)** und ohne
Home-Assistant-Historie für den Zeitraum findet er keine Kurvendaten. Jetzt steht dort, was
tatsächlich passiert ist — und wenn deiner Anlage der Leistungssensor fehlt, erscheint der Knopf
gar nicht mehr, sondern der Hinweis, ihn erst unter **Einstellungen → Datenquellen** zuzuordnen.

**Dazu passend:** Meldet der Daten-Checker „Einspeisung größer als PV-Erzeugung" für einen Monat,
riet er bisher zuerst zu vertauschten Sensoren. Stehen die **Tage** dieses Monats aber schon voll da
und nur der Monatswert nicht, nennt die Meldung jetzt **diese** Ursache zuerst und den Weg zum
Statistik-Import dazu.

### Cockpit → Tag: „Eigenverbrauch" hieß dort etwas anderes

Wenn du Live „Heute" und Cockpit → Tag nebeneinandergelegt hast, standen dort für den
Eigenverbrauch zwei verschiedene Zahlen. Beide waren richtig — sie meinten nur nicht dasselbe:

- **Live, Monat, Jahr und die Wirtschaftlichkeit** meinen den **PV-gedeckten Hausverbrauch**
  (Direktverbrauch + was der Speicher wieder abgibt).
- **Cockpit → Tag** rechnet **PV-Erzeugung − Einspeisung** — da steckt auch die **Speicherladung**
  drin, also Energie, die noch gar nicht verbraucht wurde.

Die Differenz ist genau das, was an dem Tag netto in den Speicher gewandert ist. Beides ist eine
sinnvolle Größe, nur hießen sie gleich. **Die Zahlen bleiben, der Name ändert sich:** Die
Tages-Kachel heißt jetzt **„PV-Eigenverbrauch"** und sagt „inkl. Speicherladung" dazu. Der
unqualifizierte Begriff „Eigenverbrauch" gehört ab jetzt überall der ersten Größe.

Zwei Kleinigkeiten aus demselben Winkel:

- **Am laufenden Tag** steht die Tages-Sicht auf den **abgeschlossenen** Stunden, Live „Heute"
  zählt die laufende schon mit — deshalb steht dort jetzt **„Stand: n von 24 Std. · laufende
  Stunde fehlt"**. Das erklärt die kleine Differenz, die es am heutigen Tag immer gab.
- **Der Rechenweg hinter der Autarkie-Kachel** (Tag) zeigte eine Formel, die seit v4.0.2 nicht mehr
  zur angezeigten Zahl passte — vorgerechnet kamen an manchen Tagen über 100 % heraus. Der
  angezeigte Prozentwert war die ganze Zeit richtig; jetzt stimmt die Erklärung dazu.

### Balkonkraftwerk: die Prognose passt jetzt zum Gerät

Ein Balkonkraftwerk ist fast immer überbelegt — drei Module à 420 Wp ergeben 1,26 kWp, der
Wechselrichter gibt aber nur 600 oder 800 W ab. Zwei Dinge ändern sich:

- Unter **Einstellungen → Investitionen** gibt es beim Balkonkraftwerk das Feld
  **Wechselrichter-Leistung (W)**. Ist es gepflegt, kappt eedc die Prognose **stundenweise** —
  die Mittagsspitze wird begrenzt, Morgen und Abend bleiben voll. **Bleibt das Feld leer, wird
  nichts gekappt**; einen Standardwert gibt es bewusst nicht. Wer es ausfüllt, sieht seine
  Prognose an sonnigen Tagen sinken — das ist die Korrektur.
- **Balkonkraftwerke zählten in der Tagesprognose bisher gar nicht mit.** In der 14-Tage-Aussicht
  schon — dieselbe Anlage hatte damit zwei Zahlen für denselben Tag. Wenn du ein
  Balkonkraftwerk erfasst hast, steigen Tagesprognose, Stundenprofil, Live-Wetter und die
  Prognose-Sensoren in Home Assistant jetzt um dessen Anteil. **Anlagen ohne Balkonkraftwerk sind
  unverändert.**

### JSON-Import: die Sensor-Zuordnung überlebt den Umzug

Beim Einspielen einer JSON-Datei ging bisher die Zuordnung **aller Komponenten** verloren —
Speicher, Wallbox, PV-Strings, Wärmepumpe. Sichtbar wurde das erst daran, dass Stundenwerte,
Prognose-IST und Monatsbericht für diese Komponenten leer blieben. Jetzt trägt die Datei die
nötigen Nummern mit und der Import schreibt die Zuordnung um.

**Ältere Dateien** (vor diesem Update erzeugt) lassen sich nicht heilen — ihnen fehlen die Nummern.
Der Import sagt es jetzt ausdrücklich und nennt, was neu zuzuordnen ist. Die Basis-Zähler
(Einspeisung, Netzbezug, PV gesamt) waren nie betroffen.

> **Zur Erinnerung:** Der JSON-Export ist **kein Datenbank-Backup**, sondern der Weg für Umzug oder
> Neuanfang. Für die vollständige Wiederherstellung: **HA-Backup** (Add-on) bzw. Sicherung des
> `eedc`-Verzeichnisses (Standalone).

### PV je String: gemessen bleibt gemessen

**Betrifft dich das?** Ja, wenn du **mehrere Strings** hast und **nicht alle** davon einen eigenen
Erzeugungs-Sensor haben — nach einem Sensor-Ausfall, nach dem Anlegen eines neuen Strings, oder in
den Monaten vor deiner Umstellung auf Pro-String-Messung.

Bisher galt: sobald **ein** Modul für einen Monat keinen eigenen Wert hatte, wurde der
Monats-Gesamtwert nach Nennleistung über **alle** Module verteilt — die echten Messwerte der
anderen Strings waren für diesen Monat weg. Jetzt gilt die Regel **je Modul:** ein Messwert zählt
immer, verteilt wird nur der **Rest** auf die Module ohne eigenen Wert. Deine **Anlagensumme
ändert sich dadurch nicht** — nur die Aufteilung auf die Dächer wird ehrlich.

**Das Zielbild:** alle Strings erfassen und die Zuordnung **PV gesamt** auf „keine" setzen.
Zusammenfassen höchstens je Ausrichtung/Neigung — sonst kann eedc für Anlagen mit mehreren
Ausrichtungen nicht mehr getrennt prognostizieren. Die anteilige Verteilung ist ein Übergang, kein
Dauerzustand.

**Wenn du mitten in der Historie umgestellt hast**, kommt deine Vorgeschichte zurück: sobald
irgendein Monat Pro-Modul-Werte hatte, standen alle früheren Monate in **Erzeugungs-Kachel,
spezifischem Ertrag und Finanzen** auf 0. Jahres-Erzeugung und Netto-Ertrag steigen dort jetzt auf
die tatsächlichen Werte.

### Daten-Checker und Datenquellen: weniger Fehlalarm

- Der Hinweis „die Gesamt-Zuordnung wird ignoriert, auf ‚keine' setzen" erschien für **PV gesamt
  (kWh)** schon, sobald ein einziger String einen eigenen Zähler hatte. Wer dem folgte, stand für
  die ganze Anlage auf 0. Der Hinweis kommt jetzt erst, wenn **jede** PV-Quelle einen eigenen
  Zähler hat. Für **PV gesamt (W)** (Live-Dashboard) bleibt es beim bisherigen Verhalten.
- **Ø Performance Ratio**, die **SOLL/IST-Abweichung** und die Plausibilitätsprüfungen rechneten in
  Monaten mit teilweise gemessenen Strings mit einer Teilsumme — und meldeten einen
  Ertragseinbruch, den es nicht gab. Ebenso weg: der Fehlalarm „Energiebilanz ergibt negativen
  Hausverbrauch", wenn die PV eines Monats gar nicht auflösbar war.
- Neu geprüft wird der **PV-Gesamtzähler** auf Langzeitstatistik: ohne `state_class` liefert er für
  die Monatswerte still nichts.
- Neu ist auch eine **Frage** statt einer Anschuldigung: Ist „Einspeisung + Speicherladung aus PV"
  größer als die Erzeugung des Monats, fragt der Checker nach. Meist fehlt dann nur das Feld
  **Ladung aus Netz** (wer nachts günstig lädt) — dann stimmt die Energie, nur die Zuordnung nicht.

- Zusätzlich meldet der Daten-Checker ein **überbelegtes Balkonkraftwerk ohne gepflegte
  Wechselrichter-Grenze** (ab 800 W Modulleistung) und nennt die **Wärmepumpen-Felder
  Heizenergie/Warmwasser** sowie **PV-Ladung** beim Namen, statt sie stumm zu übergehen.

---

## v4.0.3 — Zugeordnete Sensoren wirken überall (Juli 2026)

> Ein Fehler mit einem verwirrenden Gesicht: Die Datenquellen-Fläche zeigte deinen Sensor **samt
> aktuellem Zählerstand**, das Live-Dashboard lief — und trotzdem blieb das Cockpit leer, während
> der Daten-Checker genau die Zähler vermisste, die eine Zeile darüber mit ihrem Wert standen.

### Betrifft dich das?

**Ja, wenn du deine Sensoren ab v4.0.0 zugeordnet hast** — also über **Einstellungen →
Datenquellen** oder im Setup-Assistenten über „Energiekonfiguration aus Home Assistant
übernehmen". Das trifft vor allem **neue Installationen**, aber auch jeden, der seither eine
Zuordnung **geändert oder ergänzt** hat, etwa für eine neu angelegte Komponente.

**Nicht betroffen bist du**, wenn du von v3 aktualisiert und deine Zuordnung nicht angefasst hast
— sie stammt dann noch aus dem alten Assistenten. Ebenso wenig betroffen sind Anlagen ohne Home
Assistant (MQTT/Standalone).

So sah es aus, wenn es dich getroffen hat:

- **Cockpit → Tag/Monat/Jahr** und das **Energieprofil** blieben leer, obwohl Zähler zugeordnet waren.
- Der **Daten-Checker** meldete „Kein Basis-Zähler für: Einspeisung, Netzbezug".
- Der **Monatsabschluss** machte keine Vorschläge, der **Import aus der HA-Statistik** fand keine Sensoren.
- Nur das **Live-Dashboard** lief — was den Eindruck verstärkte, die Zuordnung sei in Ordnung.

**Der Grund in einem Satz:** Die neue Fläche merkte sich nur, *woher* ein Wert kommt („aus Home
Assistant, Entität X"), aber nicht, *dass* dieses Feld überhaupt einen Zähler hat — und genau
danach fragen die Auswertungen. Ab jetzt wird beides zusammen gespeichert.

### Was du tun musst: nichts

Beim Update zieht eedc die bestehenden Zuordnungen **selbsttätig** nach. Es muss nichts neu
zugeordnet werden, es geht nichts verloren, und wer eine Quelle bewusst auf „keine" oder MQTT
gestellt hat, behält diese Wahl.

**Deine vergangenen Tage sind nicht verloren:** Die Zählerstände wurden die ganze Zeit
mitgeschrieben — sie waren nur nicht verrechnet. Unter **Einstellungen → Energieprofil-Pflege**
holst du sie mit „Tag neu berechnen" bzw. „Mehrere Tage neu aggregieren" nach. Neue Tage rechnen
ab dem Update von selbst richtig.

### Zwei kleinere Korrekturen

- **Der Daten-Checker weist wieder den richtigen Weg.** Sechs Meldungen schickten noch zum
  **Sensor-Mapping-Assistenten**, den v4.0.0 durch die **Datenquellen**-Fläche ersetzt hat. Sie
  zeigen jetzt dorthin. Außerdem nennen die Hinweise Feld-Bezeichnungen statt interner Kürzel.
- **„Alles in Ordnung" sagt jetzt, wie weit es reicht.** Wer seine Monatsdaten importiert oder von
  Hand pflegt, bekam die grüne Meldung „Basis-Zähler über … befüllt". Sie gilt für die
  **Monatsauswertungen** — Tages- und Stundenwerte brauchen weiterhin kumulative kWh-Zähler. Das
  steht jetzt dabei; grün bleibt es trotzdem, eine gepflegte Anlage soll keine Dauerwarnung
  bekommen.
- **Cockpit → Aussicht:** Solange für heute noch kein gemessener PV-Wert vorliegt, entfällt die
  Zeile „verbl." — vorher wurde „unbekannt" als 0 gelesen und die **volle** Tagesprognose als noch
  ausstehend behauptet.

---

## v4.0.2 — Die Nennleistung zählt überall mit (Juli 2026)

> Ein Nachzügler zu v4.0.1, und wieder derselbe Satz dahinter: **eine Größe darf nicht an zwei
> Stellen zwei verschiedene Zahlen haben.** Diesmal geht es um die **Nennleistung deiner
> PV-Komponenten** — und um drei Fehler, die dabei ans Licht kamen.

### Betrifft dich das?

Die Nennleistung kann in eedc an zwei Stellen stehen: im Feld **Leistung (kWp)** der Komponente
oder in ihren **Detail-Feldern**. Fast alle Auswertungen lasen bisher nur das Leistungsfeld und
sahen dort still eine 0.

**Wer seine Komponenten im Formular oder im Setup-Assistenten angelegt hat, ist nicht betroffen** —
beide schreiben die Leistung ins Leistungsfeld, und kein heutiger Eingabeweg erzeugt den anderen
Zustand. Betroffen sind **importierte und sehr alte Bestände**. Wenn du dazugehörst, ändern sich
Zahlen — nach oben, weil vorher etwas fehlte:

- **PVGIS-Prognose:** Ein betroffenes Modulfeld fiel bisher **komplett** aus der Prognose. Jetzt
  zählt es mit — Jahresertrag, Monatswerte und Gesamtleistung steigen entsprechend.
- **PVGIS für ein einzelnes Modul** meldete den Fehler „PV-Modul hat keine Leistung (kWp)
  definiert" für ein Modul, dessen Leistung gepflegt ist. Das ist weg.
- **PV-Strings-Vergleich:** Der betroffene String hatte SOLL 0 und damit −100 % Abweichung, **alle
  anderen bekamen zu viel**. Die Werte stimmen jetzt.
- **Cockpit:** Die Kachel „Anlagenleistung" steigt, der **spezifische Ertrag sinkt** entsprechend —
  sein Nenner war zu klein. Der Home-Assistant-Sensor ändert sich mit.
- **ROI und CO₂ je Komponente:** Das betroffene Modul bekam 0 € Einsparung und 0 kg CO₂.
- **Live-Dashboard, PDFs und Daten-Checker** zeigten die Leistung an einzelnen Stellen gar nicht
  oder meldeten eine Abweichung, die keine war.

**Das sind Korrekturen, keine Fehler:** Die Leistung war immer gepflegt, sie kam nur nicht überall
an. Wer bisher schon überall dieselben Werte sah, merkt nichts.

### Drei Fehler, die dabei aufgefallen sind

- **ROI-Auswertung brach ab.** Hatte auch nur **ein** PV-Modul keine Leistung hinterlegt, während
  ein anderes eine hatte, lief die gesamte ROI-Seite auf einen Serverfehler — nicht nur die eine
  Zeile. Jetzt bleibt die Seite stehen: das Modul ohne Leistung bekommt 0 % Anteil, alle anderen
  ihren korrekten.
- **Balkonkraftwerk-Dashboard rechnete mit zwei Modulen.** Wer die **Anzahl** nicht gepflegt hat,
  bekam dort stillschweigend zwei Module unterstellt — doppelte Leistung, halber spezifischer
  Ertrag. Alle anderen Sichten rechnen in dem Fall mit einem. **Für betroffene Balkonkraftwerke
  halbiert sich die angezeigte Leistung** und der spezifische Ertrag verdoppelt sich.
- **PDF-Anlagendokumentation:** Speicher und Wechselrichter waren mit „Nennleistung … kWp"
  beschriftet, obwohl dort die Kapazität in kWh bzw. die AC-Leistung in kW steht. Jetzt richtig.

### Kleinigkeit am Rande

Unter **Komponenten → Einstellungen** stand die Nennleistung bei betroffenen Komponenten doppelt —
einmal sauber beschriftet, einmal als rohes Detail-Feld. Die Dublette ist weg. Außerdem rundete
diese Liste alle Werte auf ganze Zahlen: ein Wirkungsgrad von 20,75 % stand dort als „21". Das
betrifft **alle** Anlagen, nicht nur Import-Bestände.

### Speicher: eine Zyklenzahl statt drei

**Wenn du einen Speicher hast, ändert sich hier eine Zahl.** Die Kachel **„Vollzyklen"** rechnete
je nach Sicht verschieden: im Tages-Cockpit zählte sie Ladestands-Bewegungen, im Monat und im
Komponenten-Bereich die **geladene** Energie, der Home-Assistant-Sensor die **entladene**. Drei
Antworten auf dieselbe Frage — und die Tageswerte summierten sich nie auf den Monat.

Ab jetzt gilt überall dasselbe: **Vollzyklen = entladene Energie ÷ Kapazität**. Das ist die Größe,
auf die auch Hersteller-Garantien zielen.

- **Was du siehst:** In **Komponenten → Speicher**, **Cockpit → Monat/Jahr** und im
  **PDF-Jahresbericht** sinkt die Zyklenzahl um den Wirkungsgradverlust — typisch 5–10 %.
  **Der Home-Assistant-Sensor bleibt unverändert**, er rechnete schon immer so.
- **Die Ladestands-Bewegungen sind nicht weg**, sie heißen jetzt **„SoC-Hübe"** (Energieprofil,
  Tages-Tabelle, Spalte einblendbar). Sie sind die einzige Zahl, die eine schonende Fahrweise
  abbildet: Wer den Speicher zwischen 10 und 90 % fährt, sieht dort 0,8 statt 1,0 pro Hub. Dafür
  braucht es einen SoC-Sensor.

> **Und der gewünschte Ladestand?** eedc nimmt keinen an. Zyklen und Wirkungsgrad kommen aus deinen
> **gemessenen** Lade- und Entlademengen — eine schonende Fahrweise steckt dort schon drin.
> Geschätzt wird nur, wo noch nichts gemessen ist: in der Wirtschaftlichkeits-Vorschau und in der
> Tagesvorschau „Speicher voll um …". Beide rechnen jetzt mit deiner **nutzbaren** Kapazität —
> siehe den nächsten Abschnitt.

### Speicher: die nutzbare Kapazität zählt jetzt mit

**Nur wenn du beim Speicher das Feld „nutzbare Kapazität (kWh)" ausgefüllt hast.** Es ist
freiwillig — wer es nie angefasst hat, sieht hier **keine einzige veränderte Zahl**.

Dein Speicher hat zwei Kapazitäten: die vom **Typenschild** und die, die nach Entladetiefe und
Reserve wirklich durch ihn hindurchgeht. Zwei Rechnungen meinen eindeutig die zweite, benutzten
aber die erste:

- Die Vorschau **„Speicher voll um …"** lud von 0 auf 100 % der Typenschild-Zahl. Wer bei 90 %
  abriegelt, ist real früher voll — und genau das zeigt sie jetzt.
- Die **Wirtschaftlichkeits-Vorschau** rechnete mit der Typenschild-Zahl mal 250 Zyklen. Durch den
  Speicher geht aber nur der nutzbare Teil.

**Was du siehst** (Demo-Anlage, 15,4 kWh Typenschild gegen 13,9 kWh nutzbar, sechs Prognosetage):

- In **Cockpit → Aussicht** und **Auswertungen → Prognose** rückt die Kachel **„Speicher voll"** an
  einem der sechs Tage von 11:00 auf 10:00. An den anderen bleibt sie gleich — die Vorschau rechnet
  in ganzen Stunden. Unter dem Chart steht jetzt „13,9 kWh nutzbar".
- **Mit der Uhrzeit ändern sich die Nachbar-Kacheln desselben Tages:** ein kleinerer Puffer nimmt
  weniger Überschuss auf. **Einspeisung rund 1 kWh höher**, **Eigenverbrauch entsprechend
  niedriger**. Das ist die Korrektur — vorher unterstellte die Vorschau deinem Speicher eine
  Aufnahme, die er nicht leistet. An Tagen, an denen der Speicher abends früher leer ist, kann
  auch die **Autarkie** etwas niedriger ausfallen; an Tagen ganz ohne Netzbezug bleibt sie
  unverändert bei 100 %.
- **Die Autarkie der Tages-Vorschau zeigte an sonnigen Tagen mehr als 100 %** — gemessen bis 125 %.
  Das ist behoben: sie rechnet jetzt wie überall sonst „Verbrauch minus Netzbezug, geteilt durch
  Verbrauch". Vorher zählte die Vorschau die **Speicherladung** zum Eigenverbrauch des Tages, und an
  einem Tag mit viel Sonne und wenig Last wurde der Zähler größer als der Nenner. Die Werte sinken
  dadurch auf plausible Größen; an Tagen ohne Netzbezug stehen weiter 100 %. **Monat, Jahr und Live
  waren nie betroffen.**
- Der Home-Assistant-Sensor **`eedc_speicher_voll_um`** zieht mit. Er zeigt dieselbe Vorschau und
  darf keine zweite Uhrzeit nennen.
- In **Auswertungen → ROI** sinkt die jährliche Einsparung des Speichers — **aber nur, solange du
  keine Lade- und Entladewerte erfasst hast.** Bei der Demo-Anlage ohne Messdaten: 431,59 € →
  389,55 € im Jahr. **Sobald Messdaten da sind — der Regelfall —, ändert sich nichts**, denn dann
  rechnet eedc ohnehin aus deinen gemessenen Werten und braucht die Kapazität gar nicht.

**Die Vollzyklen bleiben, wie sie sind** — sie rechnen weiter gegen die Typenschild-Kapazität.
Sonst hinge diese Zahl davon ab, ob jemand ein freiwilliges Feld ausgefüllt hat, und deine Anlage
wäre nicht mehr mit sich selbst vergleichbar.

**Die angezeigte Kapazität deiner Komponente bleibt ebenfalls die Typenschild-Zahl** — sie
beschreibt das Gerät und ist keine Rechengröße.

### Wettermodell: die Prognose folgt jetzt deiner Wahl

**Nur wenn du in den Anlagen-Einstellungen ein anderes Wettermodell als „Automatisch" gewählt
hast — sonst ändert sich hier gar nichts.**

Das Live-Wetter und die 14-Tage-Wettertabelle nutzten dein Modell längst. Die **eedc-eigene
Tagesprognose** nicht: sie rechnete überall mit „Automatisch". Auf **Cockpit → Aussicht** standen
dadurch der OpenMeteo-Balken aus deinem Modell und der eedc-Wert daneben aus einem anderen — und
die Prognose-Sensoren in Home Assistant folgten dem eedc-Wert. Das ist jetzt eine Rechnung.

- **Was du siehst:** Tagesprognose für heute/morgen/übermorgen, das Stundenprofil, die Vorschau
  „Speicher voll um …" und die Prognose-Sensoren in Home Assistant springen **einmalig** auf dein
  Modell. An der Demo-Anlage nachgemessen (München, 20,8 kWp): mit **ICON-EU** heute 1,7 kWh
  weniger und morgen 14,0 kWh weniger, mit **MeteoSwiss ICON-CH2** in beide Richtungen bis zu
  12 kWh. Wie stark es bei dir ausfällt, hängt vom Standort und vom Wetter des Tages ab.
- **Modelle mit kurzem Horizont** (ICON-D2 reicht 2 Tage, ICON-EU 5) decken weiterhin nur ihre
  eigenen Tage ab — die weiter entfernten kommen wie bisher aus „Automatisch".
- **Drei Modelle sind nicht mehr da.** Für **ECMWF Seamless**, **MeteoSwiss Seamless** und
  **ECMWF IFS (9 km)** liefert Open-Meteo keine Strahlungsdaten mehr. eedc merkt das und rechnet
  dort weiter mit „Automatisch" — du bekommst also dieselben Zahlen wie bisher, deine Modellwahl
  greift nur nicht. Wenn du eines davon eingestellt hast, wähle am besten **ICON Seamless** (für
  Deutschland) oder **MeteoSwiss ICON-CH2** (Alpenraum). Die Auswahlliste wird noch aufgeräumt.

### Rund um die PV-Module

- **Komponenten-Liste:** Bei PV-Modulen blieb die graue Zeile mit den Eckdaten leer, während jeder
  andere Gerätetyp seine Werte zeigte. Jetzt steht dort „12,0 kWp • 24 Module • 500 Wp".
- **Vertippt beim Anlegen?** Wenn du Modulanzahl und Wattzahl pflegst, vergleicht eedc das Ergebnis
  jetzt mit der eingetragenen Leistung und sagt es dir **direkt im Formular**. Der Daten-Checker
  nennt außerdem den **betroffenen String beim Namen**, statt nur zu melden, dass die Anlagensumme
  nicht passt. Die Modul-Details bleiben freiwillig — maßgeblich ist weiter das Feld „Leistung (kWp)".
- **String-Vergleich verständlicher:** Über der Tabelle steht jetzt, was **Performance** eigentlich
  misst — jeden String gegen **seine eigene** Prognose, in der Ausrichtung und Neigung schon
  stecken. Ein Nordwest-Dach mit 100 % ist damit nicht so gut wie ein Süd-Dach mit 100 %. Für den
  Vergleich der Dächer untereinander zählt **kWh/kWp**. Neu daneben: die Spalte **Anteil** (Gewicht
  am Gesamtertrag) und eine **Summenzeile** mit Gesamt-kWp, SOLL und IST.
- **Stundenwerte mit IST:** Steht der Tag in **Cockpit → Aussicht → Stundenwerte** auf **heute**,
  zeigt die Tabelle neben der Prognose die bereits gemessenen Stunden. Kein Wechsel mehr in die
  Auswertungen für einen Blick auf „wie lief es bisher".
- **Günstig-Schwelle:** Der Wert **0 %** war schon immer erlaubt, schaltet die Schwelle aber ab —
  dann zählen wieder allein die 5 günstigsten Stunden je Fenster. Das steht jetzt am Feld. Der
  Standard war und ist 10 %.

  > ⚠ **Nachträglich richtiggestellt (August 2026):** Der Satz oben stimmt nicht. **0 % schaltet
  > die Schwelle nicht ab** — sie liegt dann genau **auf** dem Durchschnitt, und günstig ist alles
  > darunter. Der damalige Deckel auf 5 Stunden je Fenster hat den Unterschied verdeckt; seit er
  > weg ist, ist er sichtbar. Am Rechenweg hat sich dadurch nichts geändert, nur an dem, was hier
  > und in der Oberfläche darüber stand.

- **Neu installiert?** Die Tagesprognose zeigt dir jetzt vom ersten Tag an die **PV-Vorschau**,
  statt die ganze Ansicht mit „zu wenig historische Daten" zu verweigern. Verbrauch, Netzbezug und
  die Speicher-Vorschau bleiben dabei leer („—"), bis drei Tage aufgezeichnet sind — sie kommen
  dann von selbst dazu.

---

## v4.0.1 — Dieselbe Zahl an jeder Stelle (Juli 2026)

> Die erste Rückmelde-Runde nach der neuen Oberfläche. Fast alles hier geht auf einen Satz zurück:
> **eine Größe darf nicht an zwei Stellen zwei verschiedene Zahlen haben.** Prognosen, Modulwerte und
> die Bilanz im PDF sind deshalb an mehreren Stellen zusammengeführt worden — **und deine Zahlen
> ändern sich dadurch sichtbar.** Der nächste Abschnitt erklärt, wo und warum. Besonderer Dank an
> Rainer (rapahl) für die genauen Meldungen.

### Deine Zahlen können sich ändern — das sind Korrekturen, keine Fehler

- **Die Prognose-Balken und -Kacheln sind kleiner geworden.** In Cockpit → Aussicht zeigen der
  14-Tage-Balken, die Tabelle darunter und die Kacheln „Morgen", „Summe" und „Ø_Tag" jetzt die
  **kalibrierte eedc-Prognose** — dieselbe Zahl, die schon immer im Prognosen-Vergleich und in den
  Home-Assistant-Sensoren stand. Vorher stand dort die **rohe Wetterdienst-Zahl**, während die
  Stundenwerte auf derselben Seite bereits kalibriert rechneten: zwei Zahlen für denselben Tag,
  nebeneinander. Typisch sinken die Werte um **5–15 %**, je nachdem, was eedc über deine Anlage
  gelernt hat. **Die Prognose ist nicht schlechter geworden — sie sagt jetzt überall dasselbe.**
  Liegt für deine Anlage noch keine Korrektur vor, bleibt der Wetterdienst-Wert stehen und die
  Kopfzeile sagt es. Die HA-Sensoren ändern sich **nicht** — sie rechneten schon vorher so.
- **Die Werte je PV-Modul sind gemessen statt gerechnet.** Wer seine Dachflächen einzeln erfasst,
  sieht im Komponenten-Hub → PV endlich die **eigenen Messwerte** je Modul; bisher zerlegte der Block
  „Verlauf" die Gesamterzeugung stur nach Nennleistung, sodass ein verschatteter oder abgeschalteter
  String unsichtbar blieb und alle Module rechnerisch gleich gut dastanden. **Die Modul-Balken
  verschieben sich dadurch** (an der Demo-Anlage gewinnt das bisher zu schwach gerechnete Westdach
  9 %). Wer **nur einen Gesamt-Sensor** hat, sieht dort erstmals Werte, wo vorher 0 stand — die
  Gesamterzeugung anteilig verteilt und sichtbar als **„geschätzt (kWp-Anteil)"** gekennzeichnet. Die
  0 war die unehrlichere Anzeige. Solange die Werte verteilt sind, nennt eedc bewusst **keinen besten
  oder schwächsten String** mehr — eine Platzierung wäre dort nur die Reihenfolge der
  Nennleistungen. Wer sie zurück will, gibt jedem Modul einen eigenen Erzeugungs-Sensor
  (Einstellungen → Datenquellen).
- **Eigenverbrauch und Autarkie im PDF-Jahresbericht steigen — bei Anlagen mit einem weiteren
  Erzeuger.** Hast du neben der PV z. B. ein Mini-BHKW (erfasst als „Sonstiges" mit Kategorie
  *Erzeuger*), rechnete der Bericht Eigenverbrauch, Autarkie und EV-Quote allein aus der
  PV-Erzeugung, während der Einspeise-Zähler daneben die Summe **aller** Erzeuger misst. Cockpit,
  HA-Sensoren und Live-Ansicht rechnen das seit v3.45.4 richtig; der Bericht war nicht mit
  umgestellt. Beispiel-Anlage: Eigenverbrauch 700 → 1.100 kWh, Autarkie 77,8 → 84,6 %. Die
  PV-eigenen Kennzahlen (spezifischer Ertrag, SOLL/IST, String-Vergleich) bleiben unverändert rein
  PV — ein Brennstoff-Erzeuger gehört nicht in eine PV-Kennzahl. Ohne sonstigen Erzeuger ändert sich
  nichts.
- **Eine frühere Version hat bei manchen Anlagen den monatlichen PV-Gesamtwert entfernt.** Betroffen:
  wer die PV-Erzeugung als **einen Gesamtwert** pro Monat pflegt **und** zusätzlich ein
  Balkonkraftwerk mit eigenem Sensor hat. Beim Start von eedc verschwand der Gesamtwert für jeden
  Monat, in dem Balkonkraftwerk-Daten vorlagen; die Dachflächen stehen in diesen Monaten seither ohne
  Erzeugung da. **Das war ein Fehler, keine gewollte Bereinigung** — und **eedc kann diese Werte
  nicht zurückholen**, es gibt keinen alten Stand. Ab jetzt wird der Gesamtwert nur noch entfernt,
  wenn er exakt der Summe der einzeln erfassten Komponenten entspricht und wirklich nichts mehr
  trägt, was nicht woanders steht; im Zweifel bleibt er stehen. **Was du tun kannst:** Der
  Daten-Checker listet die betroffenen Monate („PV-Erzeugung fehlt in N Monat(en)"). Wo ein PV-Sensor
  zugeordnet ist, lassen sie sich über **Einstellungen → Datenverwaltung → Import aus HA-Statistik**
  oder den **Monatsabschluss** des jeweiligen Monats neu befüllen — beide schreiben die Werte je
  Modul. **Von Hand erfasste Werte sind verloren** und müssen von Hand nachgetragen werden.
- **Import-Wizard: die Aufteilung auf mehrere Module war immer 50/50.** Der Schritt „Zuordnung" soll
  die importierten Monatswerte **proportional zur Nennleistung** vorschlagen — er tat es nie, weil er
  die kWp unter einem Namen suchte, den eedc gar nicht kennt. Bei 12 kWp Süddach + 3 kWp Garage also
  50/50 statt 80/20. **Wer bereits importiert und den Vorschlag übernommen hat, sollte die Aufteilung
  prüfen** (Komponenten → PV-Modul → Monatswerte); ein erneuter Import mit korrigierten Anteilen
  überschreibt die Werte. Gleiches gilt für Speicher mit der Kapazität.
- **Kleinere Zahlen-Korrekturen:** Bei Anlagen mit **mehreren Ausrichtungen** rechnen jetzt auch die
  letzten Prognose-Anzeigen jede Dachfläche getrennt (Stundenwerte, Roh-Kurve im Prognosen-Vergleich,
  Ersatz-Rechenweg bei Ausfall) — die Stundenwerte und Tagessummen dieser Anzeigen verschieben sich
  spürbar. Die Spalte **„GTI Modulfläche"** ist jetzt nach Nennleistung gewichtet. Ist der
  **§51-Schalter** aktiv, zieht auch der Kennwert „Einspeiseerlös" in Auswertungen → Finanzen die
  Negativpreis-Stunden ab (bisher nur das T-Konto darunter). Und wer eine **ältere PVGIS-Prognose**
  bewusst aktiviert hat, sieht sie jetzt auch im PV-String-Vergleich und im PDF-Jahresbericht.

### Damit Prognosen nicht mehr schweigen, wenn etwas fehlt

- **Unvollständige Wetter-Abrufe werden ausgewiesen.** Bei mehreren Dachflächen holt eedc die
  Prognose für jede Ausrichtung getrennt. Fiel einer dieser Abrufe aus, enthielten Summe, Ø_Tag und
  alle Tagesbalken nur die Flächen, die geantwortet hatten — bei vier Flächen und einem Aussetzer
  fehlte grob ein Viertel, und **nichts sagte es**. Die Zahlen werden weiterhin weder hochgerechnet
  noch gekappt, aber die Anzeige trägt jetzt einen Hinweis, wie viele Teilanlagen geliefert haben.
  Ein Neuladen später ist die Prognose meist vollständig.
- **24 Nullen sind keine Prognose.** Fällt jede Prognosequelle aus, zeigte der Stunden-Tagesverlauf
  24 Nullen wie eine echte Prognose „0 kWh" — samt Speicher-Vorschau, die daraus „Speicher lädt
  nicht" ableitete. Auch das steht jetzt dran.
- **Solcast-Nutzer erfahren, dass der Stundenverlauf für morgen eine Näherung ist:** Solcast liefert
  eedc ein Stundenprofil nur für **heute**; für einen anderen Tag zeigt eedc das heutige Profil, und
  die Tagessumme kann davon abweichen.
- **Mehrere aktive PVGIS-Prognosen brechen nichts mehr.** Wer eine Sicherung wiederhergestellt hat,
  deren Datei den Aktiv-Zustand nicht mitbrachte, hatte danach **alle** Prognosen aktiv — mit drei
  Folgen: der SOLL-PV-Wert im Monatsbericht war verdoppelt, und **Daten-Checker sowie Social-Karte
  zeigten eine Fehlerseite** statt ihres Inhalts. Ab jetzt ist immer genau eine aktiv; Bestände
  werden beim nächsten Start einmalig bereinigt (die übrigen werden **deaktiviert, nicht gelöscht**),
  und beim Wiederherstellen sagt der Import, was er normalisiert hat.
- **Beide Prognose-Blöcke nennen ihren Tag.** „Stunden-Prognose" und „Stundenwerte" zeigen
  standardmäßig morgen; der Datumswähler saß aber nur im einen Block. Jetzt trägt jede Kopfzeile
  Datum und Prognosequelle.
- **Geplante Rückbauten und Erweiterungen wirken in der Prognose.** Ein PV-String mit
  Stilllegungsdatum in der Zukunft zählte über den ganzen 14-Tage-Horizont mit, ein erst später
  angeschaffter noch gar nicht.

### Was sich sonst noch ändert

- **Neu: Amortisation mit Kalenderjahr** (Forum-Wunsch Radiocarbonat). Unter Auswertungen → ROI steht
  neben der Dauer jetzt auch das voraussichtliche **Break-Even-Jahr** — in der Kachel, unter der Kurve
  und als Beschriftung der Zeitachse. Anker ist dein frühestes Anschaffungsjahr.
- **Neu: Sensor-Auswahl auf passende Einheiten verengen** (Forum-Wunsch fridolin22). Eine Checkbox
  „Nur passende Einheit" im Sensor-Picker blendet abweichende Sensoren aus und nennt deren Anzahl —
  **standardmäßig aus**, damit du bei fehlendem passenden Sensor die vorhandenen siehst und daraus in
  Home Assistant einen Helfer bauen kannst.
- **Das Anschaffungsdatum ist Pflicht.** Es ist die Grenze jeder Auswertung — ohne Datum zählt eine
  Komponente auch für Zeiträume vor ihrer Anschaffung mit — und der Nullpunkt der
  Amortisationskurve. Neue Komponenten brauchen es; für vorhandene meldet es der Daten-Checker jetzt
  als **Fehler** und springt per Klick direkt in das Formular.
- **Ein Klick auf die aktive Datenquelle löscht sie nicht mehr.** Bisher bedeutete derselbe Knopf
  zweierlei — bei inaktiver Quelle „auswählen", bei aktiver „Zuordnung verwerfen", ohne Rückfrage.
  Jetzt öffnet der Klick immer die Zuordnung; entfernt wird ausschließlich über „Keine". Die Zeile
  zeigt außerdem wieder den **Klarnamen** des Sensors neben der Entity-ID.
- **Optionale Felder lassen sich wieder leeren.** Eine einmal gesetzte Wechselrichter-Zuordnung, ein
  Anschaffungs- oder Stilllegungsdatum, alternative Kosten — das Formular meldete Erfolg, der alte
  Wert blieb aber stehen.
- **AC-gekoppelte Speicher sind kein Fehlerzustand mehr.** Der Hinweis „Speicher ohne
  Wechselrichter-Zuordnung" erschien auch dort, wo gar keine Zuordnung nötig ist — und verleitete
  dazu, eine falsche anzulegen. Speicher ohne Zuordnung heißen jetzt neutral „Eigenständige
  Speicher"; gewarnt wird nur noch bei PV-Modulen. Auch die Beschriftung „DC-gekoppelt" ist weg — sie
  war **geraten** (eedc kennt kein Kopplungs-Feld); die Zeile heißt jetzt „Zuordnung" und nennt den
  Wechselrichter beim Namen.
- **§51-Verlust wird wieder ausgewiesen.** Das Anlage-Formular verspricht am §51-Schalter, den
  entgangenen Erlös im Cockpit zu zeigen — seit der neuen Oberfläche tat es das nirgends. Jetzt gibt
  es eine Kachel „§51-Verlust" (€) unter Cockpit → Monat und einen Hinweis an der Einspeise-Zeile des
  T-Kontos.
- **Kennzahlen zeigen 0-Werte wieder an** — die Kachel „Batterieladung Netz" verschwand bei 0 kWh
  ganz, sodass man in Home Assistant nachsehen musste, ob wirklich nichts geladen wurde.
- **PDF-Jahresbericht: die Spalte „PVGIS-Prognose" war immer leer** und die SOLL-Linie im PV-Diagramm
  fehlte deshalb ganz — der Bericht suchte den Monatswert unter einem Namen, den die gespeicherte
  Prognose gar nicht kennt. Die Zahlen sind nicht neu berechnet, sie waren nur nie angekommen. Im
  String-Vergleich desselben PDFs nutzt der Bericht jetzt außerdem die für **jede Dachfläche
  gespeicherte** Prognose statt einer kWp-Verteilung; bei Ost-West-Dächern lagen die SOLL-Werte je
  String dadurch um ~20–25 % daneben.
- **Der spezifische Ertrag im PDF heißt jetzt „Spez. Ertrag (Zeitraum)".** Unter demselben Namen
  standen zwei verschiedene Größen: Cockpit und HA-Sensor rechnen den Wert aufs Jahr hoch, das PDF
  teilt schlicht die Erzeugung des Berichtszeitraums durch die Nennleistung — über die
  Gesamtlaufzeit summiert sich das auf. **Die Rechnung ist unverändert, nur die Beschriftung sagt
  jetzt, welche der beiden Größen dasteht.**
- **PV-Rest heute sinkt gleichmäßig** (#339): Der Sensor `eedc_prognose_rest_today_kwh` zählte die
  laufende Stunde immer voll mit und fiel deshalb nur einmal je Stunde in einem Sprung. Die laufende
  Stunde geht jetzt anteilig nach den verbleibenden Minuten ein.
- **Ab vier Modulfeldern waren zwei Balken gleich eingefärbt** — die vierte Modul-Farbe war exakt die
  Farbe des Balkonkraftwerks. Betroffen war die Kombination „mehrere Dachsegmente + Balkonkraftwerk".
  Es ändert sich nur die Farbe, keine Zahl.
- **Warum weicht mein Gesamtverbrauch vom Herstellerportal ab?** Diese häufige Frage ist jetzt
  beantwortet — mit Rechenrezept zum Nachprüfen: Misst dein Hybrid-Wechselrichter PV und Speicher
  DC-seitig, das Netz aber AC-seitig, stecken die Wandlungsverluste im bilanzierten Gesamtverbrauch
  (typisch 3–5 % der Erzeugung). Beide Werte sind richtig, sie beantworten verschiedene Fragen —
  siehe [Berechnungen §3.1](BERECHNUNGEN.md#31-energie-bilanz-monatskennzahlen).
- **Netzbezugspreis bei dynamischem Tarif erklärt:** Das Feld bleibt Pflicht — es ist der
  Referenzwert für Monate ohne Preis-Mitschrift und für ROI-Rechnungen. Vorrang hat weiterhin der
  stündlich mitgeschriebene Preis.

---

## v4.0.0 — Neue Oberfläche: Cockpit · Komponenten · Auswertungen (Juli 2026)

> eedc hat eine neue Menüstruktur. **Alle Funktionen und alle deine Daten bleiben erhalten** — sie sind nur neu sortiert, nach drei einfachen Fragen: **Wann?** (Cockpit), **Was?** (Komponenten), **Wie ausgewertet?** (Auswertungen). Alte Lesezeichen-Links leiten automatisch auf die neue Heimat um. Die Tabelle „Wo ist was hin?" unten beantwortet die häufigsten Such-Fälle.
>
> Diese Version bringt außerdem einige **Berechnungs-Korrekturen** bei Finanzen und CO₂ mit — **deine Zahlen können sich nach dem Update ändern.** Das ist gewollt: Bitte lies den Abschnitt „Deine Zahlen können sich ändern" weiter unten, bevor du eine Abweichung für einen Fehler hältst.

### Die neue Struktur in 60 Sekunden

- **Cockpit** = die Zeit-Achse: **Live · Tag · Monat · Jahr/Gesamt · Aussicht**. Jede Sicht hat denselben Aufbau (Kennzahlen oben, Verlauf/Energiefluss in der Mitte, Komponenten-Sektionen darunter). **Neu: die Tag-Sicht** — jeden einzelnen Tag mit Stundenverlauf und Tagesbilanz durchblättern.
- **Komponenten** = deine Geräte: PV-Anlage, Speicher, Wärme/Klima, E-Auto, Wallbox, Balkonkraftwerk, Sonstiges — jede mit fester Struktur **Status → Verlauf → Vergleich → Wirtschaftlichkeit**. Die bisherigen Cockpit-Dashboards und Auswertungs-Tabs pro Gerät sind hier zusammengeführt: eine Zahl, eine Heimat. (Die Zukunfts-Prognose je Gerät liegt gebündelt unter Cockpit → Aussicht.)
- **Auswertungen** = analytische Schnitte über die ganze Anlage: **Finanzen · ROI · Prognose-vs-IST · CO₂ · Tabelle**. Das Finanz-T-Konto aus dem Monatsabschluss lebt jetzt hier — mit wählbarem Zeitraum.
- **Einstellungen** = Kachel-Übersicht mit Suche statt langem Dropdown; jede Kachel zeigt ihren Status.
- **Überall:** Blöcke lassen sich verschieben, einklappen und auf Vollbild fokussieren — und einzelne Anzeigen auf einen „Parkplatz" legen (s. u.).

### Du gestaltest jede Sicht selbst

Neu in v4: Du bestimmst, was wo steht — eedc merkt sich deine Anordnung pro Sicht.

- **Blöcke verschieben:** Jeder Block lässt sich per ↑/↓ nach oben oder unten sortieren — das Wichtigste nach vorn.
- **Fokus/Vollbild:** Per ⤢ öffnet ein Block bildschirmfüllend — ideal, um einen Chart oder eine Tabelle groß zu lesen.
- **Einklappen:** Selten Gebrauchtes per ⌄ zuklappen.
- **Parkplatz:** Anzeigen, die du gar nicht brauchst, per Langdruck (bzw. Rechtsklick) auf den „Parkplatz" am Seitenende legen — dort gesammelt und jederzeit zurückholbar. Nichts geht verloren, du blendest nur aus, was dich nicht interessiert.

### Wo ist was hin?

| Gesucht | Neue Heimat |
|---|---|
| Live-Dashboard | Cockpit → Live (weiterhin die Startseite) |
| Aussichten (Prognosen) | Cockpit → Aussicht |
| Übersicht (Cockpit) | Cockpit → Jahr/Gesamt |
| Monatsabschluss-Wizard | Einstellungen → Daten → Monatsdaten — **ein Formular statt Wizard** (s. u.) |
| Finanz-T-Konto des Monats | Auswertungen → Finanzen (Zeitraum wählbar) |
| Geräte-Dashboards (PV, Speicher, WP, …) | Komponenten → ‹Gerät› |
| Sensor-Mapping- & MQTT-Inbound-Wizard | Einstellungen → Datenquellen (s. u.) |
| Energieprofil (Beta-Tab) | Tagessicht → Cockpit → Tag · Tabelle → Auswertungen → Tabelle · Pflege → Einstellungen → Daten |
| Infothek | Einstellungen → Infothek |

*(Vollständige Tabelle: Hilfe → „Was ist neu".)*

### Monatsabschluss: ein Formular statt sieben Wizard-Schritten

Der Monatsabschluss-Wizard ist Geschichte. Monatswerte erfasst und korrigierst du jetzt in **einem** Formular (Einstellungen → Daten → Monatsdaten) — dasselbe Formular für Neuanlage und Korrektur, mit Status-Anzeige je Monat, den bekannten Datenquellen (HA-Statistik, Connector, MQTT, manuell) und dem T-Konto als Gegenprobe in den Auswertungen.

### Datenquellen: eine Fläche statt zwei Wizards

Sensor-Zuordnung neu gedacht: Unter **Einstellungen → Datenquellen** ordnest du **jedem Feld genau eine Quelle** zu — HA-Sensor, MQTT-Topic oder Geräte-Connector. Mit Sensor-Suche, Themen-Baum, Vorzeichen-Invertierung und einer Prüfung je Feld, die Probleme (falsche Einheit, fehlende Statistik …) direkt anzeigt. Die alten Wizards (Sensor-Mapping, MQTT-Inbound) sind damit abgelöst; **bestehende Zuordnungen wurden automatisch übernommen.** Die Richtungs-Schalter (Empfangen + Export über **einen** Broker) findest du unter Einstellungen → Integration.

### Erste Einrichtung im neuen Gewand

Der Setup-Wizard beim ersten Start führt in neuer Optik durch Anlage, Tarif, PV-System und die Verbindung zu Home Assistant — inklusive Schnellstart-Karte und Sensor-Vorschlägen aus dem HA-Energie-Dashboard. (Bestehende Installationen sehen ihn nicht.)

### Deine Zahlen können sich ändern — das sind Korrekturen, keine Fehler

> Mehrere Berechnungen sind in dieser Version genauer geworden. Wenn eine Kennzahl nach dem Update anders aussieht als vorher, war sie **vorher unvollständig** — jetzt stimmt sie.

- **Sonstige Erträge & Ausgaben rechnen jetzt mit.** Monatliche Sonderposten (z. B. Versicherung, Reparatur, THG-Prämie), die du beim Monatsabschluss als „Sonderkosten" erfasst hast, wurden bisher **nirgends** in den Finanz-Summen berücksichtigt. Jetzt fließen sie ins T-Konto und in alle Finanz-Auswertungen ein — und du kannst pro Monat mehrere benannte Positionen erfassen, jeweils als Ertrag **oder** Ausgabe. Bestehende Sonderkosten-Einträge werden beim ersten Start einmalig übernommen.
- **Grundgebühr & Zählergebühr getrennt:** Die Zählergebühr ist jetzt ein eigenes Feld im Stromtarif und wird neben der Grundgebühr separat ausgewiesen (Cockpit Monat/Jahr).
- **CO₂-Ersparnis der Wärmepumpe wird genauer berechnet** — sie kann dadurch **niedriger** ausfallen. Bisher wurde nur das vermiedene Gas grob angesetzt; jetzt zählt der Wirkungsgrad des ersetzten Gaskessels **und** der Stromverbrauch der Wärmepumpe wird gegengerechnet. Cockpit, PDF-Jahresbericht und das WP-Dashboard zeigen jetzt überall denselben Wert.
- **E-Auto-Ersparnis bei mehreren Fahrzeugen korrekt.** Hattest du mehr als ein E-Auto, wurde die Ersparnis aller Fahrzeuge am Vergleichsverbrauch des ersten Autos gemessen. Jetzt rechnet jedes Fahrzeug mit seinem eigenen Vergleichswert — die Gesamt-Ersparnis kann sich dadurch ändern.
- **Dienstwagen zählen nicht in die E-Mobilitäts-Bilanz** (konsistent mit dem Cockpit): Ein als dienstlich markiertes Fahrzeug fließt nicht mehr in Ersparnis-/CO₂-Summen ein.
- **Vorjahres-Vergleich sauberer:** Der Vergleich mit dem Vorjahr berücksichtigt jetzt bei Wärmepumpe, E-Mobilität **und** Energie das Anschaffungs- und Stilllegungsdatum — Geräte, die es im Vorjahr noch nicht (oder nicht mehr) gab, verfälschen den Vergleich nicht länger.
- **Finanz-Block im Cockpit als Komponenten-Tabelle:** Der Finanz-Überblick in Cockpit → Monat/Jahr zeigt jetzt eine Zeile je Komponente (Erträge · Einsparungen · Aufwendungen · Saldo) mit Summenzeile, plus eine Zeile „Ergebnis nach Stromrechnung". Das ersetzt den bisherigen verkürzten Teaser, der optisch eine andere Summe suggerieren konnte.
- **Ältere Jahre werden mit ihrem damaligen Strompreis bewertet** (nachgetragen): Der PDF-Anlagenbericht und die HA-Sensoren rechneten die Eigenverbrauchs-Ersparnis vergangener Jahre mit dem **heutigen** Tarif statt mit dem damals gültigen — bei vier Tarif-Jahren im gemeldeten Fall rund 174 € Abweichung. Cockpit, Auswertungen, Bericht und HA-Export zeigen jetzt denselben Netto-Ertrag.

### Weitere Verbesserungen

- **Chart-Legenden sind klickbar:** In Diagrammen mit mehreren Serien blendet ein Klick auf einen Legenden-Eintrag die Serie aus und wieder ein — die Achsen skalieren mit. Praktisch, um eine dominante Serie auszublenden und die kleinen zu vergleichen.
- **Diagramme als Tabelle ablesen:** In der Vollbild-Ansicht (⤢) lässt sich ein Diagramm per Umschalter als Tabelle anzeigen und als CSV exportieren (zunächst in Cockpit-Monat/-Jahr-Verlauf und Live-Tagesverlauf).
- **Netzbezug hat eine neue Farbe** (dunkles Rot statt Signal-Rot) — Signal-Rot ist jetzt exklusiv für Kosten und Fehler reserviert. Einheitlich in allen Charts.
- **Community: rückwirkend entfernte Monate verschwinden jetzt auch auf dem Server.** Hast du Monatsdaten lokal gelöscht (z. B. eine Fehlbuchung), blieben sie im Community-Vergleich bisher stehen — ab jetzt räumt die nächste Übertragung sie auch dort weg.
- **Speicher: Netzladung wieder überall sichtbar** (das Dashboard las den Wert unter einem veralteten Schlüssel), Ø-Netz-Ladepreis-Vorschlag im Speicher-Formular und Ausweis der Netzladung-Kosten im T-Konto.
- **Live & Aussicht laden gleichmäßiger:** Eine interne Zufalls-Wartezeit beim Prognose-Abruf ist aus dem interaktiven Pfad entfernt — sie gehörte nur in Hintergrund-Jobs. Dazu weniger doppelte Datenabrufe beim Navigieren.
- **Ein Feld, eine Quelle:** Ist dasselbe Feld über HA-Sensor **und** MQTT beliefert, gilt ab jetzt fest der HA-Sensor (bisher überschrieb der MQTT-Wert den HA-Wert). Fällt der HA-Sensor aus, springt nicht mehr still der MQTT-Wert ein — prüfe bei Live-Lücken also zuerst den HA-Sensor.
- **Kleinere Politur:** einheitliche „Abbrechen"-Knöpfe, bessere Dialog-Abstände auf Mobilgeräten, Vergleichspreise als eigene Untergruppe im Monatsdaten-Formular, und die Fußzeile findet jetzt auch übersprungene Monate mitten in der Historie.

### Für HA-Add-on-Nutzer

- Das Update ist als **Breaking Change** markiert (neue Menüstruktur) — der Add-on-Store zeigt deshalb einen Hinweis vor dem Update. Es gehen **keine Daten verloren**; „Breaking" heißt hier: die Oberfläche sieht anders aus, Links/Lesezeichen werden umgeleitet.
- **MQTT intern aufgeräumt:** eine Broker-Verbindung für beide Richtungen (Empfangen + Export), bestehende Einstellungen werden automatisch übernommen. **Sobald eine HA-Verbindung und ein Broker vorhanden sind, veröffentlicht eedc seine HA-Sensoren jetzt standardmäßig automatisch** (vorher nur bei aktiver MQTT-Option) — es können also neue eedc-Entitäten in HA auftauchen. Nicht gewünscht? Einstellungen → HA-Export → Auto-Publish ausschalten.
- **Die exportierten HA-Sensoren rechnen jetzt vollständiger:** Der CO₂-Ersparnis-Sensor trägt die **volle** Bilanz (PV-Eigenverbrauch inkl. Balkonkraftwerk und sonstiger Erzeuger + Wärmepumpe + E-Mobilität) statt nur des PV-Anteils; Autarkie und Eigenverbrauchsquote enthalten jetzt auch Erzeuger hinter dem Hauszähler — beide sind damit deckungsgleich mit dem Cockpit. **Hinweis:** Weil sich der Wert des CO₂-Sensors dadurch einmalig ändert, kann die HA-Langzeitstatistik an der Update-Stelle einen einmaligen Sprung zeigen.

---


## v3.45.9 — Speicher-Vergangenheit selbst geradeziehen (Juni 2026)

> Der Speicher-Vorzeichen-Fix aus v3.45.7 wirkt ab dem Update auf neue Tage. **Ältere Tage** (vor dem Update gerechnet) können in den Auswertungen noch die alte, vertauschte Lade-/Entlade-Richtung zeigen. Diese Version macht das **sichtbar** und gibt dir einen **Knopf**, um die betroffenen Tage gezielt neu zu rechnen — bewusst auf deinen Klick hin, **nicht** automatisch beim Start (das hatte in v3.45.7 die Neustart-Schleife ausgelöst).

### Was sich für dich ändert

- **Neuer Eintrag im Daten-Checker: „Batterie – Vorzeichen-Historie".** Er erkennt Tage, an denen das Speicher-Vorzeichen noch verdreht gespeichert ist (Vergleich mit den HA-Statistics), und listet sie auf. Nur relevant, wenn du einen Hausspeicher hast und im HA-Add-on-Modus läufst.
- **Zwei Reparatur-Knöpfe:** **„Zeitraum neu aggregieren"** rechnet mehrere Tage auf einmal neu (bis zu 31 Tage pro Lauf — bei mehr einfach erneut anstoßen), **„Tag reparieren"** einen einzelnen. Nach dem Lauf verschwindet der Eintrag, sobald die Richtung stimmt.
- **Nichts passiert ungefragt:** Die Korrektur läuft nur, wenn du sie auslöst (Pull statt Push). Dein Add-on startet weiterhin sofort.
- **Live-Dashboard war und ist korrekt** — es ging nie um die Live-Ansicht, nur um gespeicherte Vergangenheitswerte.

---

## v3.45.8 — Hotfix: Add-on startet wieder (Juni 2026)

> Falls dein Add-on nach dem Update auf **v3.45.7** in eine **Neustart-Schleife** geraten ist und nicht mehr erreichbar war: Das behebt diese Version. Ursache war die in v3.45.7 eingeführte einmalige Neuberechnung aller Verlaufstage — sie lief beim Start zu lange (viele externe Abrufe) und der HA-Supervisor brach den Start ab. Diese Neuberechnung wurde **entfernt**.

### Was sich für dich ändert

- **Add-on startet wieder normal** — direkt nach dem Update auf v3.45.8.
- **Der Speicher-Vorzeichen-Fix aus v3.45.7 bleibt aktiv:** neue/laufende Tage werden korrekt dargestellt. Bereits gespeicherte **Vergangenheitstage** können noch die alte (vertauschte) Speicher-Richtung zeigen — sie korrigieren sich, sobald ein Tag neu berechnet wird (automatisch über die Zeit oder gezielt per „Tag neu berechnen" im Energieprofil). Eine schonende automatische Nachkorrektur kommt separat.

---

## v3.45.7 — Speicher: Laden/Entladen in den Auswertungen richtig herum (Juni 2026)

> In mehreren Auswertungs-Sichten war beim Hausspeicher die Lade-/Entlade-Richtung vertauscht — das **Laden** wurde z. B. im Energieprofil-Tagesverlauf als **Erzeugung** dargestellt. Das ist behoben. (Das **Live-Dashboard war korrekt** — dort fiel es nicht auf.)

### Was sich für dich ändert

- **Energieprofil-Tagesverlauf:** Batterie-**Laden** erscheint jetzt korrekt als Verbrauch (▼ unten) statt als Erzeugung (▲ oben), und die „verfügbare Energie"-Linie zählt es nicht mehr mit.
- **Tageswerte & Speicher-Wirtschaftlichkeit:** Lade-/Entlade-Mengen und die Netz-Ladekosten werden jetzt der richtigen Richtung zugeordnet.
- **Einmalige Neuberechnung:** Beim ersten Start nach dem Update werden deine Verlaufstage einmalig neu gerechnet (bei viel Historie ein paar Minuten) — danach stimmen auch die Vergangenheitswerte.

---

## v3.45.6 — „Solarprognose heute" ist jetzt überall derselbe Wert (Juni 2026)

> Je nach Seite zeigte eedc für „Solarprognose heute" leicht unterschiedliche Werte — Cockpit, Kurzfrist-Karte, die Vergleichstabelle und der MQTT-Sensor rechneten den Wert jeweils eigenständig. Das ist behoben.

### Was sich für dich ändert

- **Ein Wert überall:** Die PV-Tagesprognose (heute, Rest heute, morgen/übermorgen, Vor-/Nachmittag, Stundenprofil) kommt jetzt aus **einem** Rechenweg und ist auf allen Sichten identisch — Cockpit/Live, Aussicht, Kurzfrist-Karte, Auswertungen, die „eedc"-Spalte im Prognosen-Vergleich **und** die HA-/MQTT-Sensoren. Der Wert aktualisiert sich über den Tag (er „rollt" mit dem Wetter mit), aber überall gleich.
- **Mehrere Dachflächen genauer:** Bei Ost/West- oder Mehrfach-Ausrichtung wird jede Fläche getrennt gerechnet und dann summiert — der „heute"-Wert kann sich dadurch leicht von früher unterscheiden (genauer).
- **MQTT „PV-Prognose heute":** trägt jetzt den vollen Tagesprognose-Wert (wie die App). Wer den verbleibenden Rest braucht, nutzt „PV-Prognose Rest heute".
- **Genauigkeits-Tagesabschluss stabiler:** Der Vergleich Prognose↔IST nutzt den fertigen Tageswert (nach Sonnenuntergang festgeschrieben) statt eines Zwischenstands vom Nachmittag.

---

## v3.45.5 — Live-Tagesverlauf ohne falsche Leistungs-Spitzen (Juni 2026)

> Bei Wechselrichtern oder Zählern mit grober kWh-Auflösung (oder seltener Cloud-Aktualisierung) zeigte der Live-Tagesverlauf gelegentlich einzelne, physikalisch unmögliche Leistungs-Nadeln — die Tagessumme stimmte, nur die Kurve sah „zackig" aus.

### Was sich für dich ändert

- **Saubere Live-Kurve auch bei grobem Zähler:** Erkennt eedc, dass dein Zähler zu selten meldet, glättet es nur die **Kurvenform** anhand deines Live-Leistungssensors — die **Energiewerte (Stunde/Tag) bleiben unverändert exakt**. Bei einem feinen Zähler ändert sich nichts.

> Standalone-/MQTT-Installationen waren nie betroffen (sie rechnen ohnehin leistungsbasiert).

---

## v3.45.4 — Sonstige Erzeuger (z. B. BHKW) zählen in die Bilanz (Juni 2026)

> Wer einen eigenen Stromerzeuger außer PV oder Balkonkraftwerk gepflegt hat — etwa ein **Mini-BHKW** — unter „Sonstiges", sah dessen Erzeugung bisher nur isoliert. In Eigenverbrauch und Autarkie floss sie nicht ein. Weil dein Einspeise- und Netzbezugszähler aber den Strom **aller** Erzeuger im Haus messen, wurde deine Autarkie dadurch zu niedrig angezeigt.

### Was sich für dich ändert

- **Sonstige Erzeuger zählen jetzt überall mit** — im Monatsbericht, in der Cockpit-Übersicht, in den Auswertungen und im Live-Dashboard. Eigenverbrauch und Autarkie stimmen damit auch, wenn neben der PV noch ein weiterer Erzeuger einspeist.
- **PV-Kennzahlen bleiben sauber getrennt:** spezifischer Ertrag und Performance-Ratio bewerten weiterhin nur die PV-Anlage — ein BHKW verfälscht sie nicht mehr.
- **Bewusst noch offen:** CO₂-Einsparung und Wirtschaftlichkeit eines brennstoffbetriebenen Erzeugers (Brennstoffkosten, Emissionen) werden noch nicht bewertet — das folgt mit einem eigenen Modell.

> Inselanlagen ohne Netzanschluss sind davon nicht betroffen.

---

## v3.45.3 — Daten-Checker erkennt vertauschte Leistungs-/Energie-Sensoren (Juni 2026)

> Wenn beim Sensor-Mapping ein **kWh-Zählerstand** versehentlich in einem **Leistungs-Slot (W)** landet — oder umgekehrt ein **Leistungssensor** in einem kWh-Slot — fiel das bisher kaum auf: typisch klemmte der live berechnete Hausverbrauch auf 0, während die Monatswerte normal aussahen.

### Was sich für dich ändert

- **Der Daten-Checker findet diese Verwechslung jetzt von selbst.** Er prüft alle gemappten Sensoren (Live + Zähler, Anlage + Investitionen): ein kWh-Sensor im Leistungs-Slot wird als **Fehler** gemeldet, ein Leistungssensor im kWh-Slot als **Warnung**. So siehst du direkt, welcher Sensor zu korrigieren ist.
- **Bessere Ursachen-Hinweise:** Die Prüfungen „Einspeisung größer als PV-Erzeugung" und „negativer Hausverbrauch" weisen jetzt auf vertauschte Netz-Sensoren als wahrscheinliche Ursache hin.

> Ohne Home-Assistant-Anbindung (Standalone-Betrieb) wird dieser Check still übersprungen.

---

## v3.45.2 — Hotfix: Add-on startet wieder vollständig (Juni 2026)

> Falls du **v3.45.1** installiert hattest und viele Seiten/Funktionen nicht erreichbar waren, behebt diese Version das. Ursache war eine am selben Tag erschienene Fremd-Bibliothek (fastapi 0.137.0), die beim Add-on-Start fast alle API-Routen verschluckte — wir haben sie auf die funktionierende Version festgenagelt. Inhaltlich identisch zu v3.45.1 (keine weiteren Änderungen).

---

## v3.45.1 — Korrektere Detail-Werte & schnelleres Speicher-Cockpit (Juni 2026)

> Diese Version bringt vor allem **unter der Haube** Aufräumarbeiten: Der Berechnungs-Kern wurde an vielen Stellen auf eine gemeinsame Quelle zusammengeführt, damit dieselbe Kennzahl überall denselben Wert zeigt. **An den Funktionen ändert sich nichts** — ein paar Detail-Werte werden dadurch korrekter.

### Was sich für dich ändert

- **Eigenverbrauchsquote bleibt bei höchstens 100 %.** In der Aussichten-Prognose und im PDF-Jahresbericht konnte die Eigenverbrauchsquote rechnerisch über 100 % springen, wenn Mess- und Importdaten leicht auseinanderliefen. Sie wird jetzt überall sauber auf 100 % begrenzt.
- **Finanz-Prognose stürzt bei E-Autos ohne Kilometerstand nicht mehr ab.** Wer ein E-Auto ohne gepflegte km-Daten hat, bekam in den Aussichten teils gar keine Finanzprognose mehr (Fehler) — behoben.
- **Speicher-Cockpit lädt schneller.** Die Speicher-Wirtschaftlichkeit wird mit weniger Datenbankaufwand geladen.
- **Monatsansicht genauer bei Alt-/Importdaten und Dienstwagen.** In der aggregierten Monatsansicht wurde Wärmepumpen-Heizenergie aus älteren Importen teils nicht mitgezählt, und dienstliche E-Autos/Wallboxen rutschten in die Eigen-Bilanz. Beides ist jetzt an die übrigen Auswertungen angeglichen.

> Hintergrund für Technik-Interessierte: Komponenten-Aggregation, Netzbezugskosten, Autarkie/Eigenverbrauch/spez. Ertrag und die Speicher-Wirtschaftlichkeit laufen jetzt über einen zentralen Berechnungs-Layer — das verhindert künftige Abweichungen zwischen Cockpit, Auswertungen, Monatsbericht, HA-Export und PDF.

---

## v3.45.0 — Einheitliches Design: Farben, Tooltips, KPI-Karten & direkt verlinkbare Reiter (Juni 2026)

> Diese Version ist die sichtbare **Design-Grundlage** für die kommende neue Menüstruktur (4.0.0): überall dieselben Farben, Tooltips, Kennzahl-Kacheln und Schreibweisen. **An den Funktionen ändert sich nichts** — nur das Erscheinungsbild wird einheitlich. (Eine klickbare Vorschau der neuen Menüstruktur kommt separat.)

### Was sich für dich ändert

- **Eine Farbe = eine Bedeutung.** Farben bedeuten jetzt app-weit dasselbe: **Netzbezug ist überall Dunkelrot** (das helle Rot bleibt für Kosten, Minuswerte und Fehler), PV/Solar einheitlich gelb, Speicher Ladung = Grün / Entladung = Blau, und „deine Anlage" im Community-Vergleich immer Blau. Vorher unterschieden sich diese Farben je nach Seite.
- **Dunkelmodus besser lesbar.** Gedämpfte Texte/Hinweise und die Diagramm-Achsen/Gitterlinien passen sich jetzt sauber dem Dunkelmodus an (vorher teils zu grell oder fest hell).
- **Einheitliche Tooltips.** Alle Tooltips (Diagramm-Werte, Berechnungs-Herleitungen, Kurzhinweise) sehen jetzt gleich aus (dunkel, abgerundet) und liegen zuverlässig über Dialogen.
- **Komponenten immer in derselben Reihenfolge.** In allen Listen, Diagrammen und Berichten erscheinen die Komponenten-Typen jetzt in einer einheitlichen Reihenfolge (vorher teils alphabetisch, z. B. Balkonkraftwerk fälschlich zuerst).
- **Einheitliche Schreibweisen.** Prozentwerte mit Leerzeichen („84,2 %"), und „eedc" wird jetzt auch in den PDF-Berichten und auf der Website klein geschrieben.
- **Kennzahl-Kacheln aus einem Guss.** Die Kacheln in Cockpit, Auswertungen und den Dashboards haben jetzt überall gleiche Schriftgrößen, Icon-Positionen und Einheiten-Abstände.
- **Reiter direkt verlinkbar.** In **Auswertungen**, **Aussichten** und **Community** hat jeder Reiter jetzt eine eigene Adresse (z. B. `…/#/auswertungen/finanzen`). Lesezeichen und die Zurück-Taste landen wieder beim richtigen Reiter. Bedienung und Aussehen der Reiter bleiben gleich.

---

## v3.44.0 — Einstellbare Günstig-Schwelle, schlauere Mehrtages-Prognose & Stundenprofile (Juni 2026)

### Was sich für dich ändert

- **Dokumente-ZIP funktioniert auch ohne Infothek-Einträge.** Wer alle Berichte fürs ZIP ankreuzte, aber keine Infothek gepflegt hat, bekam einen Fehler — und gar kein ZIP. Jetzt zeigt die Infothek-Dossier-Karte direkt „Keine Einträge vorhanden" und ist gar nicht erst wählbar; die übrigen Berichte laden normal.

### Für HA-Export-Nutzer (Sensoren nach Home Assistant)

- **Günstig-Schwelle selbst festlegen.** Ab wann eine Stunde als „günstig" gilt (Standard: mindestens 10 % unter dem Tagesdurchschnitt ohne die 3 teuersten Stunden), stellst du jetzt oben auf der MQTT-Export-Seite je Anlage ein (0–50 %). Damit steuerst du selbst, wie viele günstige Stunden deine Automationen bekommen — z. B. 7,5 % für den verbreiteten Faktor Ø×0,925.
- **Mehrtages-Prognose nutzt dein gelerntes Korrekturprofil.** „PV-Prognose morgen/übermorgen/Tag+3" (und die Spalte „eedc" im Prognosen-Vergleich) korrigieren OpenMeteo jetzt pro Stunde mit deinem Korrekturprofil — saisonale Verschattung fließt also auch in die Folgetage ein, nicht nur in den Live-Tagesverlauf. Sensor und Prognosen-Vergleich zeigen denselben Wert. Ohne gelerntes Profil ändert sich nichts. Kleiner Hinweis: Die Folgetag-Werte können sich jetzt auch über Nacht ändern, wenn das Korrekturprofil dazulernt — das ist gewollt.
- **Stundenprofile an allen Prognose-Sensoren.** Auch morgen/übermorgen/Tag+3 tragen jetzt das komplette 24-Stunden-Profil als Attribut — damit lassen sich Lade- und Verbrauchsplanungen für morgen direkt als HA-Template bauen (Beispiel in der [Sensor-Referenz](SENSOR-REFERENZ.md)). Es gilt immer: Sensor-Tageswert = Summe des Stundenprofils.
- **Status-Sensoren aufgeräumt.** „Letzter Import" und „Erfasste Monate" erscheinen bei neuen Installationen im Diagnose-Bereich des eedc-Geräts statt in der normalen Sensor-Liste (bestehende Entitäten behalten ihren Platz).
- **Alle Export-Sensoren jetzt in der Hilfe dokumentiert** — neuer Abschnitt „Export-Sensoren (eedc → HA)" in der [Sensor-Referenz](SENSOR-REFERENZ.md) mit Bedeutung, Zeitbezug und den Prognose-/Preis-Details.

---

## v3.43.0 — HA-Export-Feinschliff, Cloud-Import ohne Timeout & Anker SOLIX bestätigt (Juni 2026)

### Was sich für dich ändert

- **Cloud-Import bricht nicht mehr mit „Failed to fetch" ab.** Wer historische Daten aus einer Hersteller-Cloud importiert (Anker, EcoFlow, Sungrow …), bekam bei längeren Zeiträumen manchmal die Fehlermeldung „Failed to fetch", obwohl der Import im Hintergrund noch lief. Der Abruf läuft jetzt sauber im Hintergrund — der Wizard zeigt „Abruf läuft im Hintergrund … (Sekunden)" und wartet zuverlässig, egal wie lange es dauert. Gilt für alle Cloud-Provider.
- **Anker SOLIX vollständig importiert + bestätigt.** Der Anker-SOLIX-Import füllt jetzt auch Netzbezug und Batterie-Werte korrekt (sie kamen aus den falschen Datenbereichen) und ist gegen die gelegentliche Drosselung der Anker-Cloud abgesichert. Nach erfolgreichem Gerätetest ist der Import nicht mehr als „in Erprobung" gekennzeichnet.

### Für HA-Export-Nutzer (Sensoren nach Home Assistant)

- **„PV-Prognose heute" neu + „Rest heute" korrigiert.** „PV-Prognose Rest heute" zeigt jetzt wirklich nur die Prognose der **verbleibenden** Stunden (wie viel PV kommt noch) — vorher war versehentlich der ganze Tageswert drin. Der neue Sensor **„PV-Prognose heute"** liefert den rollenden Tageswert (bisher erzeugt + Rest).
- **„Günstige Stunden" mit echter Preis-Schwelle.** Bisher waren immer die 5 billigsten Stunden je Tag/Nacht „günstig" (also fast konstant 10). Jetzt zählt nur als günstig, was auch **spürbar unter dem Tagesschnitt** liegt — getrennt als **„Günstige Stunden Tag"** und **„Günstige Stunden Nacht"**. Besser geeignet, um Verbraucher oder Speicherladung gezielt zu schalten.
- **„Spezifischer Ertrag" aufs Jahr normiert.** Der Sensor zeigte die Summe über die gesamte Laufzeit geteilt durch die heutige Leistung — bei mehreren Jahren ein Vielfaches des gewohnten Werts. Jetzt entspricht er dem Jahreswert aus dem Cockpit.

---

## v3.42.1 — Korrekturen aus euren Rückmeldungen (Juni 2026)

### Was sich für dich ändert

- **Anlagen-/Jahresbericht: „Sonstige Erträge & Ausgaben" jetzt vollständig.** Im PDF-Bericht waren die manuell gepflegten sonstigen Positionen nur teilweise berücksichtigt — ein Monat mit einer größeren Sonderausgabe konnte fälschlich positiv erscheinen, und die Monatszeilen summierten sich nicht sauber auf den Jahres-Netto-Ertrag. Jetzt landet jede Position im richtigen Monat (negative Monate werden auch negativ dargestellt), und die Finanz-Übersicht zeigt „Sonstige Erträge/Ausgaben" als eigene Zeile. Cockpit, Auswertung und Bericht passen damit durchgängig zusammen.
- **Anker-SOLIX-Import: Netzbezug und Batterie-Werte korrekt.** Beim Import fehlte bisher der Netzbezug ganz, und die Batterie-Lade/Entlade-Werte stimmten nicht. eedc fragt jetzt die richtigen Datenbereiche der Anker-Cloud ab und füllt alle Werte korrekt. (Der Import bleibt vorerst als „in Erprobung" markiert, bis ein weiterer Gerätetest das bestätigt.)

### Gut zu wissen

- **Standalone/Docker: PDF-Export repariert.** Wer eedc als eigenständige Docker-Variante betreibt, konnte seit Umstellung auf die neue PDF-Engine keine Berichte mehr erzeugen (Fehlermeldung zu einer fehlenden System-Bibliothek). Dem Standalone-Image fehlten ein paar Schriften-/Grafik-Bibliotheken — die sind jetzt dabei. **Das HA-Add-on war nie betroffen.** Nach dem Update einmal `docker compose pull && docker compose up -d`.
- **HA-Export: Port klarer beschriftet.** Der für den REST-Export benötigte Port 8099 trägt in den Add-on-Netzwerkeinstellungen jetzt eine Beschreibung, die erklärt, dass er nur für den REST-Sensor-Export gebraucht wird (für die normale Nutzung und MQTT bleibt er aus).

---

## v3.42.0 — Prognose lernt saisonale Verschattung, Anker-SOLIX repariert & Berichte als ZIP (Juni 2026)

### Was sich für dich ändert

- **Die PV-Prognose lernt jetzt saisonale Verschattung.** Wenn Bäume oder Gebäude deine Anlage je nach Jahreszeit unterschiedlich beschatten (belaubt vs. kahl), konnte die bisherige Korrektur das nicht auseinanderhalten — gleicher Sonnenstand wurde über die Jahreszeiten gemittelt. Jetzt lernt eedc einen eigenen Korrekturfaktor **pro Monat und Stunde** aus deinen vorhandenen Daten. Aktiv wird ein Monat, sobald genug Messpunkte da sind (~50 Stunden); bis dahin gilt die bisherige Korrektur weiter. Was eedc gelernt hat, siehst du im neuen Heatmap-Tab **„Saison (Monat × Std.)"** beim Korrekturprofil. Gilt für die eedc-Prognose — Solcast/SFML bleiben unverändert.
- **Anker-SOLIX-Cloud-Import repariert.** Anker hat das Anmelde-Verfahren seiner Cloud umgestellt; eedc spricht jetzt das aktuelle Schema, und auch der Datenabruf läuft über den aktuellen Endpunkt. Falls beim Login etwas hakt, nennt die Fehlermeldung jetzt den konkreten Grund (falsches Passwort, Verifizierung nötig, zu viele Anfragen).
- **Mehrere PDF-Berichte als ein ZIP.** In Einstellungen → Stammdaten → Anlage → Dokumente kannst du Berichte ankreuzen und ab zwei Stück gesammelt als ZIP herunterladen.

- **HA-Export ohne Stolpersteine.** Das YAML-Snippet für den REST-Export enthält jetzt automatisch die richtige Adresse deines eedc (vorher stand dort ein Platzhalter, der unbemerkt dazu führte, dass in HA gar keine Entitäten entstanden) — inklusive Hinweis, dass im Add-on Port 8099 freigegeben sein muss. Und der MQTT-Auto-Publish schickt die Sensoren jetzt schon ~2 Minuten nach dem Start, statt erst nach einer Stunde — neue Sensoren erscheinen nach einem Update sofort in HA.

### Gut zu wissen

- **Aussichten und Cockpit rechnen jetzt auch im Detail identisch** — die Aussichten nutzen dieselbe gemeinsame Finanzberechnung wie Cockpit und Berichte (Monat für Monat mit dem jeweiligen Monatspreis, auch beim Dienstwagen-Abzug). Bei dynamischen Tarifen können sich einzelne Aussichten-Werte dadurch leicht ändern — sie sind jetzt die korrekten.
- **MQTT-Auto-Publish läuft jetzt automatisch mit, sobald der MQTT-Export aktiviert ist** (`mqtt.enabled: true` in der Add-on-Konfiguration). Bisher brauchte es zusätzlich die separate Option `mqtt.auto_publish` (Standard: aus) — wer die nicht kannte, bekam Sensor-Updates nur beim manuellen Klick „Sensoren publizieren". Die Option bleibt gültig, ist aber nicht mehr nötig.

---

## v3.41.0 — Überall dieselben Finanzwerte & täglicher Connector-Abruf (Juni 2026)

### Was sich für dich ändert

- **Cockpit, Auswertungen und Anlagenbericht zeigen jetzt dieselben Finanzwerte.** Bei dynamischen Stromtarifen (Tibber, aWATTar, EPEX) konnten Eigenverbrauchs-Ersparnis, Netto-Ertrag und Amortisation je nach Ansicht unterschiedlich ausfallen, weil jede Sicht ihre eigene Rechnung hatte. Jetzt rechnen alle über **eine gemeinsame Berechnung** — Monat für Monat mit dem jeweiligen Monatspreis, inklusive Speicher-/V2H-Anteil und deiner „Sonstigen Erträge & Ausgaben". Was du im Cockpit siehst, steht genauso im PDF und im HA-Export.
- **Der Geräte-Connector holt deine Zählerstände jetzt einmal täglich automatisch** — auch ohne aktivierten MQTT-Inbound. Bisher füllte sich der Monatsabschluss-Vorschlag ohne MQTT nur, wenn du manuell „Aktuelle Daten anfordern" geklickt hast.
- **Anlagenbericht: Batteriespeicher jetzt in der Analyse.** Der Bericht enthält eine eigene Speicher-Sektion mit Kapazität, Ladung/Entladung, Vollzyklen und Wirkungsgrad.

### Gut zu wissen

- **Die alte PDF-Engine (reportlab) ist entfernt** — alle Berichte kommen jetzt aus derselben Engine (WeasyPrint), die seit v3.37.0 ohnehin der Standard war. Die Add-on-Option `pdf_engine` ist damit ohne Funktion; bestehende Konfigurationen bleiben gültig, der Wert wird einfach ignoriert.

---

## v3.40.0 — eedc-Prognose & günstige Stunden als HA-Sensoren (Juni 2026)

### Was sich für dich ändert

- **eedc schickt jetzt seine eigene PV-Prognose nach Home Assistant.** Bisher exportierte eedc vor allem Monatswerte; jetzt gibt es Sensoren für die **eigene** Vorhersage: Rest-Ertrag heute, die Erträge für morgen/übermorgen/in drei Tagen und einen „Speicher voll um"-Zeitpunkt (gerechnet ab deinem **aktuellen** Speicherstand, also automatisierungstauglich). Bewusst nur die eedc-eigene Prognose (OpenMeteo + Lernfaktor) — Solcast/SFML liegen, falls du sie nutzt, über ihre eigene HA-Integration ohnehin schon vor.
- **Börsenpreis-Trigger für dynamische Tarife.** Ein neuer Sensor sagt dir, wie günstig die **aktuelle Stunde** im Tagesverlauf ist (Rang 1–5 = eine der fünf günstigsten Stunden, sonst „teuer"), und das **getrennt für Tag und Nacht** (die Fenster wandern saisonal mit Sonnenauf-/-untergang). Damit kannst du in HA eigene Automatisierungen bauen — Wallbox laden, Speicher takten, Verbraucher schalten. **eedc liefert nur das Signal, die Strategie baust du selbst** — bewusst kein fertiger Auto-Pilot.
- Alle Werte kommen wie gewohnt **doppelt**: als HA-Sensor (Add-on) und als MQTT-Topic, gruppiert unter dem eedc-Gerät deiner Anlage. Stunden-Profile (Prognose- und Preis-Verlauf) hängen als Sensor-Attribut dran, statt den HA-Verlauf mit 24 Einzel-Sensoren zu fluten.

### Gut zu wissen

- **Geräte-Connector liefert kWh jetzt auch bei älteren Einrichtungen.** Wenn du den Connector vor v3.39.0 eingerichtet hattest, blieben PV-/Speicher-/Wallbox-Energiewerte trotz Update leer — eine automatische Reparatur beim Start ordnet die Messungen jetzt nachträglich den richtigen Komponenten zu (#300).

---

## v3.39.2 — Internes Aufräumen (Juni 2026)

### Was sich für dich ändert

- **Für dich ändert sich praktisch nichts** — diese Version ist eine interne Aufräum-Runde vor dem nächsten größeren Umbau: einheitlichere Fehler-Antworten im Hintergrund, eine korrigierte Daten-Herkunfts-Spur (Diagnose) und aktualisierte Bau-Werkzeuge. Einzig sichtbar: einige Fehlermeldungen sind im Wortlaut leicht vereinheitlicht (z. B. „Anlage 5 nicht gefunden" statt „Anlage mit ID 5 nicht gefunden"). Keine Funktion ändert ihr Verhalten.

---

## v3.39.1 — §51-Schalter pro Anlage & MQTT-Sensoren nach HA (Juni 2026)

### Was sich für dich ändert

- **§51 EEG ist jetzt ein Schalter pro Anlage.** Der „§51-Verlust" (entgangener Erlös, wenn du bei negativem Börsenpreis einspeist) wurde bisher automatisch für jede Anlage berechnet, sobald Börsenpreis-Daten vorlagen — auch wenn deine Anlage §51 gar nicht unterliegt. §51 EEG gilt rechtlich nur für **Neuanlagen** (ab Solarpaket I, Inbetriebnahme i. d. R. ab dem 25.02.2025). Neu gibt es deshalb in den **Anlagen-Stammdaten** (unter *Steuerliche Behandlung*) die Checkbox **„Anlage unterliegt §51 EEG"**. Sie ist **standardmäßig aus** — der §51-Verlust erscheint nur, wenn du sie aktiv setzt. Bestehende Anlagen ändern sich also nach dem Update nicht, bis du den Haken bewusst setzt. Anlass: rapahl.
- **MQTT-Sensoren landen wieder zuverlässig in Home Assistant.** Wenn du eedc-Werte per MQTT an HA schickst, konnten die Sensoren stehenbleiben, während das Log „erfolgreich, keine Fehler" meldete. Zwei Ursachen sind behoben: ein Broker-Mismatch (automatischer und manueller Versand konnten auf verschiedene Broker zielen) und eine geschönte Erfolgsmeldung. Jetzt nutzen automatischer Versand, manuelle Schaltfläche und Test denselben Weg, und das Log zeigt echte Zahlen und konkrete Fehlergründe (z. B. „Connection refused"). Danke an JayJayX.

---

## v3.39.0 — Connector liefert kWh, Amortisation ab Anschaffungsdatum (Juni 2026)

### Was sich für dich ändert

- **Geräte-Connector erfasst jetzt auch die Energiewerte (kWh) automatisch.** Bisher zeigte der Connector nur die Live-Leistung in Watt — „Heute" und die Monatswerte blieben leer, obwohl die Kachel „Automatische Zählerstandserfassung" das versprach. Jetzt liest eedc alle 5 Minuten die Zählerstände aus und füllt damit Tagesverlauf und Monatsabschluss. **Neu im Connector-Setup:** die Karte „Zuordnung zu Investitionen" — ordne pro gemessener Kategorie (PV, Speicher, Wallbox …) die passende Komponente zu, dann landen die Werte am richtigen Ort (z. B. ein EcoFlow, der PV **und** Speicher misst).
- **Amortisation und ROI rechnen jetzt erst ab dem Anschaffungsdatum.** Bisher wurde der PV-Ertrag über alle vorhandenen Monate summiert — auch über Zeiträume vor der Anschaffung deiner Anlage. Dadurch sah die Amortisation etwas zu günstig aus. Jetzt zählen nur die Monate, in denen deine PV tatsächlich in Betrieb war. (Greift nur, wenn ein Anschaffungsdatum gesetzt ist.)
- **Setup-Wizard: Sensor-Zuordnung übersichtlicher.** Jedes Feld bietet nur noch „HA-Sensor" oder „Kein Sensor". Die früheren Optionen „kWp-Verteilung", „EV-Quote", „COP-Berechnung", „Manuell" waren eine Falle — sie sahen wählbar aus, lieferten aber nie Daten. Diese Logik passiert ohnehin automatisch in der Auswertung. Bestehende Einstellungen werden beim Update automatisch umgestellt.

### Gut zu wissen

- Interne Aufräumarbeiten am Daten-Checker (Modul-Struktur, ein maskierter Fehler im Drift-Check behoben) — keine sichtbare Änderung, aber wartbarer und robuster.

---

## v3.38.0 — CO₂-Amortisation, String-Verteilung & Negativpreise (Juni 2026)

### Was sich für dich ändert

- **Neu: „Ab wann ist meine Anlage klimapositiv?"** Der CO2-Tab der Auswertung stellt deiner laufenden CO₂-Einsparung jetzt die graue Herstellungs-Last deiner Komponenten gegenüber und zeigt den Punkt, ab dem sich beides ausgleicht — erreicht oder hochgerechnet. Für PV und Speicher zählt die volle Herstellungs-Last, für Wärmepumpe und E-Auto nur die Differenz zur Alternative (Gasheizung bzw. Verbrenner), weil eedc auch die laufende Einsparung schon als Differenz rechnet. Die Richtwerte (z. B. 1000 kg CO₂/kWp PV) kannst du pro Investition mit einem Herstellerwert übersteuern.
- **Multi-String-Anlagen mit nur einem PV-Sensor: Auswertung je Dachseite funktioniert jetzt.** Wenn du mehrere Strings (z. B. Ost + West) hast, aber nur einen Gesamt-PV-Zähler, verteilt eedc die Erzeugung jetzt anteilig nach kWp auf die einzelnen Strings. Damit greifen Per-String-Auswertungen, die vorher leer blieben. Im Daten-Checker siehst du, ob ein String **gemessen** (eigener Sensor) oder **verteilt** (nach kWp) ist.
- **Negative Börsenpreise werden korrekt behandelt.** Hast du einen Einspeise-Tarif mit Börsenpreis-Bezug, wird Einspeisung in Stunden mit negativem Preis jetzt nicht mehr als Erlös gezählt — in allen Auswertungen (Cockpit, Aussichten, ROI, PDF).
- **Flex-Stromtarif: Auswertung und Cockpit zeigen jetzt denselben Wert.** Bei dynamischem Tarif (z. B. Tibber) nutzt die Finanz-Auswertung jetzt deinen aufgezeichneten Monats-Durchschnittspreis — vorher konnte die Eigenverbrauchs-Ersparnis dort vom Cockpit abweichen. Danke an rilmor.

### Gut zu wissen

- **Daten-Checker meckert weniger zu Unrecht:** Komponenten, die du per CSV-/Custom-Import oder manuell pflegst (ohne Sensor-Mapping), gelten jetzt als in Ordnung mit Quellen-Hinweis. Und bei Wallbox + E-Auto verschwinden zwei Fehlalarme (Pflege-Konflikt bzw. „E-Auto-Zähler fehlt", obwohl die Wallbox die Ladeenergie schon misst).

---

## v3.37.1 — Prognosen-Seite, WP-Betriebsstunden & SFML-Stundenprofil (Juni 2026)

### Was sich für dich ändert

- **Wählst du „Solar Forecast ML" (SFML) als Prognosequelle, zeigt eedc jetzt dessen echtes Stundenprofil über drei Tage.** Bisher wurde nur SFMLs Tagessumme auf die OpenMeteo-Kurve verteilt — jetzt nutzt eedc die anlagengelernte Stundenform direkt (auch für „Speicher voll um …" und den Verbleibend-Wert).
- **Wärmepumpen-Betriebsstunden sind jetzt überall sichtbar.** Neben den Kompressor-Starts erscheinen die Betriebsstunden im Monatsbericht (Kachel), im Energieprofil (zuschaltbare Spalte in Tages- und Stunden-Tabelle), im PDF-Jahresbericht und beim HA-Sensor-Export. Erst das Verhältnis von Starts zu Betriebsstunden zeigt, ob die WP gut eingestellt ist.
- **Jahresbericht: Jahr wählbar.** Im Dokumente-Dialog kannst du beim Jahresbericht jetzt ein einzelnes Jahr oder den Gesamtzeitraum auswählen.
- **Prognosen-Seite überarbeitet:** Der heutige Tag steht jetzt mit in der 7-Tage-Tabelle, vergangene Tage zeigen ihr Wettersymbol, und beim Genauigkeits-Tracking kannst du den Zeitraum (7/10/30 Tage) wählen. Der „Verbleibend"-Wert rechnet jetzt einheitlich und passend zur gewählten Quelle.
- **Ausreißer-Tage werden markiert statt versteckt.** Ein Tag mit großer Prognose-Abweichung wird im Genauigkeits-Tracking gekennzeichnet (und ist auf Wunsch ausblendbar) — er verschwindet nicht still aus der Statistik, denn gerade solche Tage sind aufschlussreich.

### Gut zu wissen

- **WeasyPrint ist jetzt auch im Home-Assistant-Add-on die Standard-Engine für PDF-Berichte** (bei Neuinstallationen). Bestehende Installationen behalten ihre Einstellung; die alte Engine bleibt als Rückfalloption.
- Kleinere Korrekturen: „Sonstige Erträge & Ausgaben" fließen jetzt in die Netto-Ertrag-Kachel im Cockpit ein; die Eigenverbrauchsquote stimmt in weiteren Auswertungen (inkl. V2H).

---

## v3.37.0 — Jahresbericht-PDF rundum erneuert (Juni 2026)

### Was sich für dich ändert

- **Der PDF-Jahresbericht sieht jetzt aus wie die anderen Berichte** (Anlagendokumentation, Finanzbericht, Infothek) — einheitliches Layout, klar lesbare Diagramme zu PV-Erzeugung, Energiefluss und Autarkie.
- **Der Jahresbericht läuft jetzt auch auf Home Assistant in Proxmox-VMs mit CPU-Typ `kvm64`.** Dort konnte die PDF-Erstellung bisher abstürzen — wegen der alten Diagramm-Bibliothek. Die ist ersetzt; die Diagramme werden jetzt gestochen scharf (vektorbasiert) und ohne diese Abhängigkeit erzeugt.
- **Community-Vergleich: Autarkie bei Speicher-Anlagen stimmt jetzt.** Wenn du einen Batteriespeicher hast, war dein im Community-Vergleich gezeigter Autarkiegrad bisher zu niedrig — der Speicher wurde beim Hochladen nicht mitgerechnet (besonders bei Netzladung). Das ist behoben; deine **Cockpit-Werte waren immer korrekt**. Mit deinem nächsten Monats-Upload korrigieren sich auch die bereits hochgeladenen Werte. Danke an kingcap1.
- **Finanz-Prognose: Eigenverbrauchsquote stimmt bei modernen Datenquellen.** Bei Anlagen, deren Werte je Komponente erfasst werden, konnte die Prognose-Seite („Aussichten") eine zu niedrige Eigenverbrauchsquote zeigen (sie fiel auf einen Standardwert von ~30 % zurück). Jetzt rechnet sie mit denselben Werten wie das Cockpit.
- **Eigenverbrauch und Autarkie zählen V2H jetzt überall mit.** Speist dein E-Auto ins Haus zurück (Vehicle-to-Home), wird diese Energie nun in allen Auswertungen als Eigenverbrauch gewertet — genau wie die Entladung eines Hausspeichers. Vorher war das je nach Ansicht uneinheitlich.

### Gut zu wissen

- **WeasyPrint ist jetzt die Standard-Engine für PDF-Berichte.** Damit nutzen alle vier Berichte dasselbe moderne Layout. Die bisherige PDF-Engine bleibt als Rückfalloption erhalten.

---

## v3.36.2 — Live-Wetter endgültig behoben (Juni 2026)

### Was sich für dich ändert

- **Live-Wetter zeigt jetzt zuverlässig Daten — auch direkt nach dem Update.** Der Fix aus v3.36.1 griff bei manchen Anlagen erst nach bis zu einer Stunde, weil ein veralteter interner Zwischenspeicher-Eintrag aus der Vorversion das Neuladen blockierte. eedc erkennt solche Alt-Einträge jetzt und ruft das Wetter sofort frisch ab. Danke an rapahl.

---

## v3.36.1 — Sonstige Erträge, Sichtbarkeit & Live-Wetter (Juni 2026)

### Was sich für dich ändert

- **Sonstige Erträge fließen jetzt überall in die Finanzen ein — auch wenn sie am Wechselrichter oder PV-Modul gepflegt sind.** Wer z. B. den Einspeise-Ertrag eines zweiten Zählers als „Sonstige Position" an seiner PV-/Wechselrichter-Komponente einträgt, sieht ihn jetzt korrekt im **Netto-Ertrag** der Auswertung „Finanzen" — vorher fehlte er dort. Danke an rilmor.
- **„Inaktiv" bedeutet jetzt wirklich „überall ausgeblendet".** Setzt du eine Komponente auf **inaktiv**, verschwindet sie ab sofort aus **allen** Auswertungen — auch aus der Vergangenheit —, bis du sie wieder aktivierst. Bisher tauchte sie in historischen Auswertungen noch auf. **Deine Daten gehen dabei nicht verloren** (es ist nur ausgeblendet, jederzeit umkehrbar). Zur Einordnung der drei Wege: **inaktiv** = vorübergehend ausblenden (reversibel) · **Stilllegungsdatum** = Komponente ist ab dann ausgemustert · **Löschen** = endgültig weg.
- **E-Auto-Verbrauch (kWh/100 km) ist überall gleich.** E-Auto-Dashboard, Monatsbericht und Komponenten-Auswertung zeigen jetzt denselben Ø-Verbrauch. Liegt ein gemessener Verbrauch vor, wird er genutzt; sonst nähert eedc den Wert ehrlich aus der geladenen Energie an (und sagt das dazu). Das frühere irreführende „0,0 kWh/100 km" ohne Verbrauchssensor entfällt.

### Außerdem in dieser Version

- **Sensor-Zuordnung mit Erklärungen:** Im Zuordnungs-Assistenten steht jetzt unter jedem Feld ein kurzer Hinweis, welcher Wert bzw. Sensortyp dort erwartet wird.
- **Live-Wetter zeigt wieder zuverlässig Daten.** Es konnte vorkommen, dass die Live-Wetteransicht bis zu einer Stunde „Keine Wetterdaten verfügbar" zeigte, obwohl alles korrekt eingerichtet war — ein interner Zwischenspeicher-Fehler. Behoben. Und falls der Wetterdienst mal kurz nicht erreichbar ist, steht jetzt ehrlich „momentan nicht verfügbar — wird automatisch erneut versucht" statt einer falschen Aufforderung, Koordinaten zu hinterlegen. Danke an rapahl.
- **PV-Prognose: kein Festhängen an veralteten Werten mehr.** Nach einer Änderung der Anlagengröße konnte die Jahresprognose auf einem alten Stand „kleben". Ein Wächter erkennt das jetzt; im Zweifel hilft „Prognose neu abrufen" im PVGIS-Abschnitt. Danke an Sabrina.
- **„Monat einfügen" ist freier geworden:** Du kannst einen Monat auch dann nachtragen, wenn er nicht in der Auswahlliste steht.

---

## v3.36.0 — Heimladung sauber an der Wallbox geführt (Juni 2026)

### Was sich für dich ändert

- **Wer eine Wallbox hat, pflegt die Ladestrom-Daten nur noch dort.** Bisher konnte dieselbe zu Hause geladene Energie an zwei Stellen liegen — an der Wallbox *und* am E-Auto. Das führte zu widersprüchlichen Zahlen (z. B. einem PV-Anteil über 100 % oder doppelt gezähltem Ladestrom). Ab sofort ist die Heimladung (gesamt / aus PV / aus Netz) eindeutig an der **Wallbox** zu Hause: Sie misst den Strom am Ladepunkt. Das **E-Auto** trägt nur noch, was wirklich zum Fahrzeug gehört — gefahrene km, Verbrauch, externe Ladung unterwegs und V2H. Im E-Auto-Eingabeformular blendet eedc die Heimladungs-Felder „Heim: PV"/„Heim: Netz" deshalb aus, sobald eine Wallbox vorhanden ist.
- **Ohne Wallbox ändert sich nichts.** Wer per Steckerlader/Schuko lädt und keine Wallbox als Investition angelegt hat, erfasst die Heimladung weiterhin direkt am E-Auto.
- **Deine bestehenden Daten werden automatisch umgezogen.** Beim Update verschiebt eedc vorhandene Heimladungs-Werte einmalig vom E-Auto in den Wallbox-Slot (pro Monat gewinnt der höhere, vollständigere Wert). Fälle, die sich nicht eindeutig zusammenführen lassen, bleiben unverändert stehen und werden im **Daten-Checker** als Pflege-Hinweis angezeigt — dort kannst du in Ruhe entscheiden, welche Quelle stimmt. **Tipp:** Vor dem Update wie immer ein Backup der Daten anlegen.
- **Auswertungen bleiben gleich aussehend.** E-Auto- und Wallbox-Dashboard zeigen die Ladequellen weiter wie gewohnt — die Zahlen stammen nur jetzt aus einer eindeutigen Quelle statt aus zwei konkurrierenden.

### Außerdem in dieser Version

- **Prognosen-Vergleich: der gemessene Ist-Ertrag startet wieder zur richtigen Stunde.** Im „Stundenvergleich heute" (Aussichten → Prognosen) lag die IST-Spalte bei HA-Add-on-Nutzern eine Stunde vor den Prognosen. Das ist behoben — alle Spalten liegen jetzt auf demselben Stundenraster. Tages- und Monatssummen waren nie betroffen; ältere Tage kannst du bei Bedarf über „Mehrere Tage neu aggregieren" nachziehen. Danke an rapahl.
- **Speicher & Co. lassen sich wieder mit Dezimalwerten speichern.** Eine Kapazität wie 5,12 kWh wurde beim Bearbeiten still abgewiesen, „Speichern" tat dann nichts. Jetzt akzeptieren die Zahlenfelder beliebige Werte. Und im Einrichtungs-Assistenten erscheint beim Bezeichnungs-Feld keine kryptische Fehlermeldung mehr. Danke an Sabrina.
- **Finanzen: „Netto-Ertrag" berücksichtigt jetzt auch Sonstige Erträge.** Bisher wurden nur Sonstige Ausgaben abgezogen, Sonstige Erträge aber nicht addiert. Danke an rilmor.
- **Monatsbericht: abgeschlossene Monate zeigen die Einspeisung wieder korrekt.** Bei manchen Cloud-Anbindungen ohne eigene Einspeise-Messung stand fälschlich 0 — die bereits gespeicherten Werte werden nicht mehr überschrieben. Deine Daten waren korrekt, nur die Anzeige. Danke an detlefh68.
- **Live-Energiefluss hebt die Solarleistung bei mehreren PV-Strings hervor.** Danke an kingcap1.

## v3.35.2 — Live-Energiefluss schärfer + kleine Tooltip-Verbesserungen (Juni 2026)

### Was sich für dich ändert

- **Live-Energiefluss-Diagramm zeigt in der Mitte das richtige Haus-Residual.** Im Live-Dashboard stand in der Mitte des Energieflusses bisher die Summe aller Verbraucher — jetzt erscheint dort der tatsächliche Haus-Rest (Gesamtverbrauch abzüglich der separat ausgewiesenen Verbraucher wie Wärmepumpe, Wallbox, E-Auto). Auch der Tooltip überschreibt den „Gesamtverbrauch" nicht mehr. Anlass: #314.
- **E-Auto-Ersparnis: der verwendete Benzinpreis steht jetzt im Tooltip.** Beim Tooltip zur Kraftstoff-Ersparnis siehst du jetzt, welcher durchschnittliche Benzinpreis des Zeitraums der Rechnung zugrunde liegt. Danke an NongJoWo.
- **Daten-Checker erklärt Quellen-Konflikte konkreter.** Wenn zwei Datenquellen denselben Wert befüllen, nennt die Warnung jetzt das betroffene Feld, den Zeitraum und die beteiligten Quellen — statt nur „Konflikt erkannt". Außerdem warnt der Daten-Checker, wenn derselbe HA-Sensor versehentlich Wallbox **und** E-Auto zugeordnet ist. Anlass: Safi105, #314.

## v3.35.1 — Qualitäts-Härtung (Juni 2026)

### Was sich für dich ändert

- **Stabilitäts-Release ohne neue Funktionen.** Diese Version schließt eine Reihe interner Aufräum- und Absicherungsarbeiten ab, die hinter den letzten Aggregator-Verbesserungen noch offen waren. Für die allermeisten Anlagen ändert sich nichts Sichtbares — die Werte bleiben gleich, nur abgesichert gegen seltene Drift-Fälle.
- **Energieprofil-Geräteliste: „Stromnetz" erscheint wieder zuverlässig.** Auf der Energieprofil-Seite konnte die Netz-Zeile in der Geräte-/Diagnoseliste für neuere Tage fehlen (seit der Umstellung auf getrennten Netzbezug/Einspeisung). Sie wird jetzt für alte und neue Tage einheitlich angezeigt. Die Kennzahlen oben (Autarkie, Einspeisung, Netzbezug) waren nie betroffen.
- **MQTT-/Standalone-Betrieb: E-Auto-Doppelzählung in der Stunden-Ansicht behoben.** Die in v3.35.0 für HA-Setups behobene E-Auto-Doppelzählung (Zähler über zwei Felder) greift jetzt auch im MQTT-/Docker-Betrieb. Betrifft nur diese spezielle Doppel-Konfiguration.

## v3.35.0 — E-Auto-Stundenwerte bei doppelt erfasstem Zähler korrigiert (Juni 2026)

### Was sich für dich ändert

- **Stunden-Ansicht: E-Auto-Werte werden nicht mehr doppelt gezählt.** Wenn dein E-Auto-Ladezähler über **zwei** Felder gleichzeitig ankommt (`Ladung` *und* `Verbrauch` — typisch bei evcc-Importen), waren die **stündlichen** Werte deines E-Autos bisher zu hoch: die Stundentabelle und Heatmap zeigten die Lademenge doppelt, und der daraus abgeleitete stündliche Eigenverbrauch lag entsprechend daneben. Die **Tages- und Monatswerte waren nie betroffen** — nur die Stunden-Sicht. Das ist jetzt strukturell behoben (es zählt genau ein Feld). Betroffene Anlagen sehen ihre Stunden-Werte beim nächsten Aggregat-Lauf korrigiert; auch die Reload-Vorschau („Tag neu berechnen") zeigt jetzt direkt den richtigen Wert. Anlass: junky84 (#262).

## v3.34.7 — E-Auto-Monatstabelle + EcoFlow-Import (Juni 2026)

### Was sich für dich ändert

- **E-Auto „Monatsdaten anzeigen": die geladene Energie pro Monat erscheint wieder.** Wer das Laden über eine Wallbox (z. B. mit evcc) erfasst, sah in der E-Auto-Monatstabelle bisher nur die gefahrenen Kilometer — die Ladespalten blieben leer, weil die Lademenge auf der Wallbox liegt. eedc rechnet jetzt für jeden Monat den passenden Anteil aus dem Wallbox-Pool (PV/Netz/gesamt) in die Tabelle, genau wie es die Kacheln schon tun. Danke an junky84 (#262).
- **EcoFlow-Cloud-Import: Monatswerte stimmen wieder.** Beim Import aus dem EcoFlow-Portal wurden Tage an Monats-/Block-Grenzen doppelt gezählt — die Monatssummen lagen spürbar über den Werten der EcoFlow-Webseite. Das ist behoben: jeder Tag zählt jetzt genau einmal. Danke an Dirk.

## v3.34.6 — Einrichtung am Handy und Tablet (Juni 2026)

### Was sich für dich ändert

- **Die Setup-Startseite lässt sich am Handy und Tablet wieder scrollen.** Wer eedc neu einrichtet — oder die Anlage gelöscht hat und von vorne beginnt — kam am Smartphone teils nicht weiter: Die Willkommensseite ließ sich nicht scrollen, sodass der Button „Einrichtung starten" außerhalb des sichtbaren Bereichs lag. Drehen ins Querformat oder die App neu zu installieren half nicht. Das ist behoben — die Seite scrollt jetzt auf allen Bildschirmgrößen. Danke an Sabrina.

## v3.34.5 — MQTT-„Heute"-PV + Setup auf kleinen Bildschirmen (Mai 2026)

### Was sich für dich ändert

- **MQTT-Betrieb: „Heute"-PV aus mehreren Wechselrichtern wird wieder korrekt angezeigt.** Wer eedc im Standalone-/MQTT-Modus mit einem PV-Topic pro Wechselrichter versorgt, sah in der „Heute"-Kachel 0,0 kWh, obwohl die Daten ankamen. eedc summiert die einzelnen Wechselrichter jetzt zur Gesamt-PV — der daraus abgeleitete Eigenverbrauch erscheint damit ebenfalls wieder. (Tages- und Monatswerte waren nie betroffen.)
- **Einrichtungs-Assistent auf kleinen Monitoren.** Auf Netbooks, älteren Laptops und der HA-Companion-Sidebar ist das Layout jetzt kompakter — der Button „Einrichtung starten" passt ohne langes Scrollen. Danke an Stefan (stlorenz).

## v3.34.4 — Anschaffungsdatum gilt jetzt überall (Mai 2026)

### Was sich für dich ändert

- **Wärmepumpen-Kacheln „Kompressor-Starts" und „Betriebsstunden"** zählen jetzt erst ab dem eingestellten Anschaffungsdatum. Vorher summierten sie die gesamte vom Sensor gelieferte Historie — dadurch konnte der „seit Anschaffung"-Wert sogar über dem Lebensdauer-Zählerstand liegen, und ein geändertes Anschaffungs-/Stilllegungsdatum wurde von diesen Kacheln ignoriert. Jetzt folgen sie dem eingestellten Zeitraum.
- **Sonstige Investitionen** (Mini-BHKW, Pelletofen …): die Gesamt-Auswertung (Erzeugung, Verbrauch, Ersparnis, CO₂) berücksichtigt jetzt ebenfalls nur die tatsächliche Laufzeit.
- **HA-Sensor-Export:** die je Investition exportierten Sensoren (E-Auto, Wallbox, Wärmepumpe) rechnen nur noch mit Monaten innerhalb der Laufzeit.

### Mit Dank an

- detLAN für den präzisen Bug-Report und den Gegentest.

## v3.34.3 — Sammelrelease: acht Verbesserungen aus dem Backlog (Mai 2026)

### Was sich für dich ändert

- **Lange Bearbeiten-Dialoge** (z. B. „Monatsdaten bearbeiten") lassen sich wieder vollständig bedienen — der Inhalt scrollt jetzt innerhalb des Fensters, die Speichern-Buttons sind immer erreichbar.
- **Daten-Checker:** Der Hinweis „Daten-Quellen – Konflikte" ist jetzt ehrlich (neutrale Info statt Warnung, kein irreführender „Beheben"-Knopf), und der PV-Doppelerfassungs-Text ist lesbarer.
- **PV-Tagesprognose bei mehreren Dachausrichtungen** (Multi-String / Balkonkraftwerk) bleibt auch bei kurzen Wetterdienst-Aussetzern verlässlich — kollabierte Werte werden nicht mehr als Tagesprognose eingefroren.
- **Fronius Gen24:** Die PV-Erzeugung wird wieder gelesen, auch wenn der bisher genutzte Gesamtzähler auf neuerer Firmware leer bleibt. *(Auf echtem Gen24 noch nicht final gegengeprüft.)*
- **HA-Export:** Die Eigenverbrauchsquote stimmt bei Setups mit Investitions-Monatsdaten wieder (vorher z. B. 2 % statt ~40 %).
- **„Ersparnis vs. Benziner"** zeigt im Cockpit denselben Wert wie Monatsberichte und E-Auto-Dashboard — der echte monatliche Kraftstoffpreis wird verwendet.
- **Wärmepumpen-Kacheln** (Kompressor-Starts / Betriebsstunden) zeigen den seit Anschaffung erfassten Wert; der volle Lebensdauer-Zählerstand steht im Tooltip.

### Mit Dank an

- Dirk, Radiocarbonat, Rainer (rapahl), Safi105, NongJoWo und detLAN für die Bug-Reports, Re-Tests und Vorschläge.

## v3.34.2 — Vollbackfill vervollständigt nachgefüllte Tage (Mai 2026)

### Was sich für dich ändert

- **Der Vollbackfill (Werkbank → „Vollbackfill" / „Tag(e) neu aggregieren") läuft jetzt über denselben Weg wie die tägliche Auswertung.** Für Tage, die per Vollbackfill aus den Home-Assistant-Langzeitstatistiken nachgefüllt werden, fehlten bisher die **Leistungsspitzen** (Peak PV / Netzbezug / Einspeisung) und die **Strompreis- bzw. Börsenpreis-Felder**. Diese werden jetzt automatisch mitgefüllt — der nachgefüllte Tag sieht damit genauso vollständig aus wie ein normal vom Scheduler ausgewerteter Tag.
- **Bestehende Werte bleiben unverändert.** Die Verbesserung greift nur, wenn du einen Tag selbst neu aggregierst oder neu nachfüllst. Schon vorhandene Tage werden nicht angefasst (der Vollbackfill ist weiterhin rein additiv).
- **Hintergrund (technisch, ohne Handlungsbedarf):** der bisher eigenständige Nachfüll-Pfad war eine Code-Kopie der täglichen Auswertung und lief ihr über die Zeit strukturell hinterher — eine wiederkehrende Quelle für kleine Abweichungen zwischen Tages- und Stundenwerten. Beide Pfade sind jetzt zu einem zusammengeführt.

### Was wir für v3.35.0 ankündigen

- Phase C des v3.34-Refactors: strukturelle Korrektur der Stunden-Auswertung bei E-Auto-Sensoren mit mehreren Mess-Feldern (analog zur in v3.33.0 sanierten Tages-Symmetrie). Eigener Sichtungs- und Tester-Zyklus.

---

## v3.34.1 — Wert für „heute" in der Komponenten-Aufschlüsselung wieder sichtbar (Mai 2026)

### Was sich für dich ändert

- **Komponenten-Tageswerte für den laufenden Tag werden im HA-Add-on wieder gefüllt** (Befund #620 MartyBr aus dem simon42-Forum). Bisher zeigten Cockpit und Komponenten-Hub für „heute" in der Komponenten-Aufschlüsselung (PV / Wärmepumpe / Wallbox / E-Auto / Batterie) Lücken, und der Daten-Checker meldete viele Drift-Warnings pro Tag. Ursache war eine strukturelle Lücke im Aggregator, die mehrere unabhängige Schutzmaßnahmen zusammen verursacht haben. Chirurgisch geheilt, ohne eine dieser Schutzmaßnahmen abzuschalten. Anwender mit dem Befund müssen nichts tun — neu aggregierte Tage füllen sich automatisch beim nächsten Scheduler-Lauf.

### Was wir für v3.34.2 ankündigen

- Phase B des v3.34-Refactors (Konsolidierung des Vollbackfill-Pfads, vorher für v3.34.1 vorgesehen) wandert durch diesen Hotfix auf v3.34.2 — die Inhalts-Beschreibung aus dem v3.34.0-Eintrag bleibt unverändert.

### Mit Dank an

- MartyBr für den klaren Bug-Report mit Screenshot.

---

## v3.34.0 — Drift-Erkennung scharf gestellt (Mai 2026, Vorarbeit)

### Was sich für dich ändert

- **Funktional nichts** — diese Version ist die erste Etappe des in v3.33.0 angekündigten Refactors von Energieprofil und Reparatur-Werkbank. Sie schärft hinter den Kulissen die Drift-Erkennung auf den Tageswerten, damit künftige Aggregat-Fehler durch automatische Tests auffallen, nicht durch Anwenderberichte. Bestehende Werte und Anzeigen ändern sich nicht.

### Was wir für die nächsten Etappen ankündigen

- **v3.34.1** — Konsolidierung des Vollbackfill-Pfads. Der Vollbackfill und der tägliche Aggregat-Lauf laufen heute auf zwei eigenständigen Code-Pfaden; sie werden auf einen gemeinsamen Pfad zusammengeführt. Stille Verbesserung als Nebeneffekt: für Tage, die du per Vollbackfill geschrieben hast, fehlen heute Peak-Werte, Strompreis-Stunden und Börsenpreis-Felder — diese werden bei erneuter Aggregation (Werkbank → „Tag(e) neu aggregieren" oder „Vollbackfill") nun automatisch befüllt. Bestehende Werte bleiben unverändert, bis du selbst re-aggregierst.
- **v3.35.0** — Analoge strukturelle Auflösung für die Stunden-Aggregation (entspricht der in v3.33.0 für die Tages-Aggregation geleisteten Arbeit). Wenn dein E-Auto-Sensor mehrere Mess-Felder hat (`verbrauch_kwh` + `ladung_kwh`), waren Hourly-Werte bisher latent doppelt gezählt — das wird in v3.35 strukturell behoben. Vorab läuft ein Daten-Checker-Scan über Tester-Anlagen, ob das Muster überhaupt vorkommt; falls ja, gibt es eine 1-Tag-Vorlauf-Notification statt einer stillen Korrektur.

### Mit Dank an

- Alle, die die letzten Patch-Wellen geduldig begleitet haben — die jetzt eingebauten Drift-Tests sind das direkte Resultat aus den Lehren von #190, #290 und der Aggregator-Drift-Serie der letzten Wochen.

---

## v3.33.0 — Tageswerte-Korrektur + Reparatur-Werkbank wirksam (Mai 2026)

### Was sich für dich ändert — automatische Korrektur deiner Tageswerte

- **Die in v3.32.4 angekündigte Reaggregation läuft beim ersten Start automatisch**: alle Tageszusammenfassungen ab dem 16.5.2026 werden für jede Anlage mit Sensor-Mapping neu berechnet. Du brauchst nichts zu klicken. Im Activity-Log siehst du, wenn der Lauf startet und wenn er fertig ist. Für die Mehrzahl der Anwender dauert das wenige Sekunden bis Minuten, abhängig von der Anzahl betroffener Tage.
- **Konkret betroffen sind die Spalten in der „Tage"-Tabelle (Daten → Energieprofil)** und die Komponenten-Aufschlüsselung pro Monat (Auswertungen → Energieprofil) — dort werden die Werte für Wärmepumpe, Speicher, Wallbox, E-Auto und Sonstiges für die genannten Tage kleiner und realistischer, wenn du eine der in v3.32.4 beschriebenen Mapping-Konstellationen hast. Cockpit-Übersicht, Live-Dashboard, ROI/Wirtschaftlichkeits-Berechnungen und der Monatsabschluss ändern sich nicht — sie lesen aus einer anderen Datenquelle.

### Was sich für dich ändert — Reparatur-Werkbank

- **„Tag neu aggregieren" wirkt jetzt wieder auf die Komponenten-Werte**: In v3.32.4 war der Knopf als Übergangsschutz so eingestellt, dass er die Komponenten-Tageswerte unverändert lässt (weil der damalige Aggregator falsche Werte geliefert hätte). Mit der strukturellen Korrektur in v3.33.0 läuft der Knopf wieder durch und korrigiert die Werte — er erfüllt also wieder seinen eigentlichen Zweck.
- **Wenn du den Knopf in den letzten Tagen erfolglos getestet hast**: nach dem Update wird derselbe Klick die Werte tatsächlich aktualisieren. Das wirkt wie „die Zahlen springen wieder" — es ist die nachgeholte Korrektur, kein neuer Bug.

### Was wir für v3.34 ankündigen

- **Strukturelle Vereinfachung von Energieprofil und Reparatur-Werkbank**: Beide Bereiche sind über mehrere Releases organisch gewachsen, mit mehreren parallelen Datenpfaden, Übergangs-Patches und Sonderfällen für Einzel-Anwendungsfälle. Das hat in den letzten Wochen zu der Häufung von Korrekturen geführt, die du gesehen hast. Für v3.34 planen wir einen konsolidierten Aufbau: ein zentraler Datenpfad mit klar getrennten Quellen-Adaptern, die Per-Typ-Logik im zentralen Berechnungs-Layer, weniger Sonderfälle. Ziel ist weniger Wartungsaufwand für uns und eine vorhersagbarere Auswertungs-Sicht für dich.
- **Während der Konzept- und Audit-Phase** sammeln wir neue Beobachtungen und Beiträge zu diesen Bereichen und adressieren sie im Zuge des Refactors, statt sie einzeln zu patchen. Der Cockpit-, Monatsabschluss- und Cloud-Import-Bereich ist davon nicht betroffen — Bug-Reports dort werden wie gewohnt zeitnah behandelt.
- **Für das aktuelle v3.33.0 bleibt die Reparatur-Werkbank in der UI verfügbar.**

### Mit Dank an

- Alle geduldigen Testerinnen und Tester, die die letzten Patch-Wellen begleitet haben.

---

## v3.32.4 — Reaggregations-Hardening + Datenbank-Locks behoben (Mai 2026)

### Was sich für dich ändert — Stabilität & Datenqualität

- **Datenbank-Locks beim Cloud-Re-Import behoben**: Beim großflächigen Re-Import vergangener Monate (z. B. Victron VRM) konnte das Speichern eines Monatsabschlusses parallel mit `database is locked` scheitern, weil der Hintergrund-Aggregator eine sehr lange Schreibtransaktion offen hielt. eedc committet jetzt pro Tag bzw. pro Anlage — das Lock-Fenster ist immer nur ~15-20 Sekunden offen, der Monatsabschluss kommt sauber dazwischen. Falls es trotz allem mal eng wird: statt eines SQL-Dumps siehst du eine kurze freundliche Meldung „Datenbank gerade belegt, bitte in 10-20 Sekunden erneut speichern". Mit Dank an kingcap1 für das saubere Log.
- **„Tag neu aggregieren" verschlimmbessert keine Tage mehr**: Wenn HA-LTS für den gewählten Tag keine Daten mehr hat (z. B. weil HA-Recorder Lücken hat) und auch keine guten Snapshots in der eedc-DB stehen, schrieb der Reparatur-Knopf bisher trotzdem eine neue Tageszusammenfassung mit häufig falschen, selbst-geheilten Werten. Jetzt bleiben die alten Werte unverändert, wenn keine frischen Daten gefunden werden. Plus: die Diagnose-Meldung „X von 24 Stunden mit Messdaten" stimmt jetzt wieder — bisher zeigte sie wegen eines verlorenen Response-Feldes immer „0/24", auch bei erfolgreichen Reaggregationen.
- **Wärmepumpe-Spalte im „Tage"-Tab driftet nicht mehr gegen den „TD"-Tab**: Für den laufenden Tag rechnete eedc die Tageswerte aus dem kumulativen Zähler hoch, wobei der Snapshot zur Tagesgrenze (= Mitternacht morgen) noch in der Zukunft lag — das Self-Healing zog dann einen unpassenden Ersatzwert. Im Ergebnis konnte die Wärmepumpe-Tagessumme im „Tage"-Tab um ein Vielfaches abweichen vom „TD"-Tab. eedc nutzt für heute jetzt dieselbe Stunden-Integration wie alle anderen Heute-Sichten — beide Tabs zeigen denselben Wert. Mit Dank an detLAN für die Drift-Reproduktion.

### Was sich für dich ändert — Bedienung

- **Wärmepumpe-Dashboard: KPI-Kacheln mit „(Lebensdauer)"-Suffix**: Die Karten „Kompressor-Starts" und „Betriebsstunden" zeigen die kumulativen Werte aus deinem Hersteller-Sensor (Lebensdauer-Counter), nicht ein Monatsaggregat. Der Bezug stand bisher nur im Tooltip — jetzt steht „(Lebensdauer)" auch im Kachel-Titel.
- **Tage-Tabelle: Einheiten im Spalten-Header**: Die Spalten im „Tage"-Tab unter Daten → Energieprofil tragen jetzt sichtbar die Einheit hinter dem Label („kWh", „kW", „Starts" usw.) — konsistent zum „TD"-Tab.

### Achtung — angekündigter Folge-Fix mit v3.33.0

Im Zuge der detLAN-Diagnose ist eine **strukturelle Drift in den Tageswerten** aufgedeckt worden, die alle HA-Add-on-Anwender mit Multi-Sensor-Mappings seit Mitte Mai betrifft:

- Wenn deine **Wärmepumpe** zusätzlich zum Strom-Sensor auch thermische Sensoren (`heizenergie_kwh`, `warmwasser_kwh`) gemappt hat, summiert eedc seit v3.31.0 alle drei unter der Wärmepumpe-Spalte — statt korrekt nur den Strom. Faktor ~5-10×.
- Wenn dein **Speicher** für Arbitrage einen `ladung_netz_kwh`-Sensor gemappt hat, wird er doppelt zur Gesamtladung gezählt.
- Wenn deine **Wallbox** oder dein **E-Auto** zusätzlich zum Gesamt-Ladezähler PV-/Netz-Split-Sensoren gemappt haben, werden diese Teilmengen nochmal addiert. Drift bis ca. +50-100 %.
- Wenn eine **„Sonstige Position"** sowohl als Erzeuger als auch als Verbraucher gemappt ist, kann die Anzeige kippen.

Sichtbar wird das vor allem in der „Tage"-Tabelle (Daten → Energieprofil) und der per-Monat-Komponenten-Aufschlüsselung (Auswertungen → Energieprofil). Cockpit-Übersicht, Live-Dashboard und ROI/Wirtschaftlichkeits-Berechnungen sind **nicht** betroffen — sie nutzen andere Datenquellen.

v3.32.4 entschärft die zwei akut sichtbaren Folgen (heute-Drift, Reaggregations-Verschlimmbesserung) als Übergangsschutz. **Die vollständige strukturelle Bereinigung kommt mit v3.33.0** und beinhaltet auch eine einmalige automatische Reaggregation aller betroffenen Tage seit dem 16.5. — du brauchst danach nichts manuell anzuwerfen, und eine HA-Notification informiert dich über den Lauf.

---

## v3.32.3 — Doku-Nachreichung zu v3.32.2 (Mai 2026)

Bei v3.32.2 wurde diese Seite versehentlich noch mit dem v3.32.1-Stand ausgeliefert — die Inhalte zu Sungrow, EcoFlow, Victron, WP-Betriebsstunden und IA-Konzept (siehe nächster Block unten) sind jetzt auch in der In-App-Hilfe sichtbar. Keine funktionalen Änderungen.

---

## v3.32.2 — Cloud-Import-Hardening + WP-Betriebsstunden + IA-Konzept (Mai 2026)

### Was sich für dich ändert — Cloud-Import

- **Sungrow iSolarCloud lädt wieder**: Sungrow hat den API-Schlüssel rotiert, dadurch lehnte der Cloud-Import mit „Illegal c-access-key" ab. Schlüssel ist aktualisiert — der Import läuft wieder durch. Zusätzlich gibt es ein neues optionales Feld „App-Key" in der Setup-Maske: falls Sungrow den Schlüssel künftig wieder rotiert, kannst du einen aktuellen Wert (z. B. aus dem GoSungrow-Projekt) selbst eintragen, ohne auf das nächste eedc-Release zu warten. Mit Dank an detlefh68 für die saubere Fehlermeldung.
- **EcoFlow PowerOcean / PowerStream liefert wieder Werte**: Der Import blieb leer, weil EcoFlow andere `indexName`s in der Cloud-API verwendet, als eedc bisher kannte. Die Diagnose-Logs aus v3.32.0 haben die tatsächlichen Namen offengelegt — das Mapping ist jetzt vollständig. Mit Dank an Dirk für die Logs.
- **Victron VRM ist freigegeben**: Nach erfolgreicher Verifizierung gegen ein echtes Konto fällt der „nicht getestet"-Banner weg. Der Provider ist damit vollständig produktiv. Mit Dank an kingcap1.

### Was sich für dich ändert — Wärmepumpe

- **Neue Auswertung: Betriebsstunden + Ø Laufzeit pro Start** (#238): Wenn deine Wärmepumpe einen Betriebsstunden-Zähler liefert, kannst du ihn jetzt in der Sensor-Zuordnung eintragen (`total_increasing`, in Stunden). Daraus berechnet eedc die Tages-Betriebsstunden, die durchschnittliche Laufzeit pro Start und kombiniert das mit dem schon vorhandenen Kompressor-Starts-Zähler. Aussagekräftiger als Starts allein — 10 Starts bei 23 h Laufzeit zeigen etwas anderes an als 10 Starts bei 4 h. Neue KPI-Kacheln im Monatsbericht und im WP-Dashboard. Mit Dank an detLAN.

### Was sich für dich ändert — Daten-Qualität

- **Daten-Checker erkennt evcc-Pool-Mismatch**: Wenn du Wallbox oder E-Auto hinzufügst, nachdem der zentrale evcc-Pool-Sensor schon eingerichtet ist, kann der Pool nicht-aktualisiert sein und Werte unvollständig liefern. Der Daten-Checker meldet das jetzt mit einem Hinweis und Link zur Reparatur. Kein Auto-Heal — der Fix bleibt bewusst beim Anwender, damit nichts überschrieben wird.

### Was sich für dich ändert — Erlös bei negativen Börsenpreisen (§51 EEG)

- **Abzug konsistent in mehr Sichten** (Phase 2): Nach Aussichten und Monatsabschluss in v3.31.x wird der §51-Abzug bei negativen Börsenpreisen jetzt auch in Cockpit-Übersicht, ROI-Dashboard, PDF-Jahresbericht, HA-Sensor-Export und in den Auswertungen-Tabs „Energie" und „Finanzen" durchgängig angewendet. Falls du Direktvermarktung mit Negativpreis-Klausel hast: alle Kennzahlen rechnen jetzt mit demselben Erlös-Wert.

### Was sich für dich ändert — Bedienung

- **Investitionen löschen: Hinweis wenn der Button blockiert ist** (#288): Im Lösch-Dialog ist der „Endgültig löschen"-Button bewusst gesperrt, bis du entweder ein Backup erstellt oder „Ohne Backup fortfahren" geklickt hast. Bisher war das nicht erkennbar — der Cursor zeigte nur „verboten", der Grund blieb verborgen. Jetzt steht links neben den Buttons „Bitte oben eine Backup-Option wählen" und ein Tooltip am Button erklärt es zusätzlich. Mit Dank an NongJoWo für die Meldung.

### Konzept zur Diskussion — neue Menüstruktur für v4.0.0

- **eedc bekommt mit der nächsten großen Version eine grundlegend neue Menüstruktur und ein modernes Designsystem.** Drei klare Achsen statt der heutigen Vermischung: Cockpit (Zeit — Live, Heute, Monatsbericht, Jahr, Aussicht), Komponenten (eine eigene Seite pro Speicher / Wärmepumpe / E-Auto / …), Auswertungen (Finanzen, CO₂, ROI, Tabelle, Prognose-vs-IST). Plus Hell/Dunkel-Mode und ein eigenes Mobile-Konzept für die HA-Companion-App.
- **Die Konzept-Dokumente sind öffentlich** — [Menüstruktur](https://github.com/supernova1963/eedc-homeassistant/blob/main/docs/KONZEPT-IA-V4.md), [Designsystem](https://github.com/supernova1963/eedc-homeassistant/blob/main/docs/KONZEPT-STYLE-GUIDE.md), [Mobile-Konzept](https://github.com/supernova1963/eedc-homeassistant/blob/main/docs/KONZEPT-MOBILE.md) — und Feedback ist ausdrücklich willkommen, **bevor** die Umsetzung startet. Zentrale Anlaufstelle: [Issue #243](https://github.com/supernova1963/eedc-homeassistant/issues/243). Bekanntmachungen laufen parallel in den Foren ([simon42](https://community.simon42.com/t/eedc-energie-effizienz-data-center/77723/618), [community-smarthome.com](https://community-smarthome.com/t/eedc-energie-effizienz-data-center/10057/72)).

---

## v3.32.1 — Wirtschaftlichkeit bei mehreren Geräten + Tester-Fixes (Mai 2026)

### Was sich für dich ändert — Wirtschaftlichkeits-Berechnungen

- **Bei mehreren E-Autos oder Wärmepumpen jetzt mit jedem Gerät korrekt gerechnet**: Auf Anlagen mit zwei E-Autos (z. B. Klein-EV + SUV-EV) oder zwei Wärmepumpen (z. B. Gas-Ersatz + Öl-Ersatz) hat eedc bisher die gepflegten Parameter (Vergleichsverbrauch, Vergleichspreis, Wirkungsgrad, Energieträger) des **zuletzt eingetragenen** Geräts auf alle anderen angewendet. Aussichten, ROI-Dashboard, PDF-Jahresbericht und HA-Sensor-Export sind durchgängig auf eine geräte-spezifische Rechnung umgestellt. Bei Anlagen mit nur einem E-Auto bzw. einer WP ändert sich nichts.
- **ROI-Dashboard schlägt den aktuellen Marktpreis vor**: Der Benzinpreis-Regler im ROI-Dashboard startete bisher fest bei 1,85 €/L und überschrieb damit den per-E-Auto gepflegten Wert. Jetzt: leer = pro E-Auto wird der gepflegte Wert bzw. der aktuelle Marktpreis aus den Monatsdaten verwendet; der Regler ist nur noch ein Override für Wenn-dann-Spiele.
- **E-Auto-Dashboard nutzt monatliche Benzinpreise** (#260): Die „Ersparnis vs. Benziner"-Zahl im E-Auto-Dashboard zog bisher den festen 1,65 €/L heran und wich dadurch von der Cockpit-Übersicht ab (die längst mit den monatlichen Werten aus dem EU-Oil-Bulletin rechnet). Die beiden Sichten zeigen jetzt denselben Wert. Mit Dank an NongJoWo für die Meldung.

### Was sich für dich ändert — Monatsabschluss

- **Sonstige Positionen lassen sich auch über die Monatsdaten-Tabelle löschen** (#286): Der Fix in v3.32.0 hat nur den Monatsabschluss-Wizard erreicht — wenn du die Einträge stattdessen über die Monatsdaten-Tabelle bearbeitet hast, kamen sie nach dem Speichern wieder. Behoben — Lösch-Signale gehen in beiden Wegen sauber durch. Mit Dank an rcmcronny für die Hartnäckigkeit.
- **0-€-Positionen werden gespeichert** (#286): Im Monatsabschluss verwarf eedc bisher Positionen mit Betrag 0 € stillschweigend — Workaround war „0,01 €". Jetzt zählt nur noch die Bezeichnung; 0 € und auch negative Beträge (für Korrekturen) gehen sauber durch. Mit Dank an Robert (rilmor-mhrs) für die Meldung.
- **Wizard: kein doppeltes „Sonstiges" mehr**: Bei einer Sonstiges-Investition (z. B. „SmartGrid"-Heizstab) tauchte „Sonstiges" zweimal in der Schritt-Leiste auf — einmal als Investitionstyp, einmal als Sammel-Schritt für Sonderkosten und Notizen. Der hintere Schritt heißt jetzt „Allgemein"; bei genau einer Sonstiges-Investition wird deren Bezeichnung als Titel verwendet. Mit Dank an Rainer für den Hinweis.

### Was sich für dich ändert — PDF-Jahresbericht & Auswertung

- **Anschaffungs- und Stilllegungsdaten konsequent berücksichtigt**: Wer historische Energiedaten per Custom-Import vor das eedc-Anschaffungsdatum eingespielt hat, sah im PDF-Jahresbericht Pre-Anschaffungs-Phantomwerte (PV-Erzeugung, Speicher-Ladung, WP-Wärme, E-Mobilitäts-Aggregate). Das PDF rechnet jetzt — wie alle anderen Auswertungs-Sichten seit v3.29 — nur mit Daten aus der tatsächlichen Lebenszeit der Investition.

### Was sich für dich ändert — Cloud-Import

- **Victron VRM gegen die echte API**: Der Victron-VRM-Provider in v3.32.0 war ein erster Wurf — er ist jetzt gegen die offizielle VRM-API v2 mit korrekter Endpoint-Discovery und passender Datenfeld-Zuordnung neu gebaut. Erstes echtes Feedback ist willkommen. Mit Dank an kingcap1 und FrodoVDR.
- **EcoFlow-Import: Diagnose-Log**: Wenn der EcoFlow-Cloud-Import keine Daten findet, schreibt eedc jetzt die tatsächlichen Feldnamen aus der API-Antwort ins Log — das macht die Zuordnung künftiger PowerOcean/PowerStream-Modelle einfacher. Mit Dank an Dirk.

---

## v3.32.0 — Victron-VRM-Cloud-Import + Fehlerbehebungen (Mai 2026)

### Was sich für dich ändert — Cloud-Import

- **Neu: Victron VRM Cloud-Import** (#255): eedc kann historische Energiedaten jetzt auch direkt aus dem Victron VRM Portal holen — praktisch, um Daten aus der Zeit vor der HA-Anbindung nachzutragen. Du brauchst nur einen Access-Token (im VRM-Portal unter Preferences → Integrations erstellt) und deine Installation-ID; kein Passwort, kein Admin-Recht. Der Live-Betrieb über Home Assistant bleibt davon unberührt. Hinweis: der neue Provider ist noch nicht final mit echten Konten getestet — Rückmeldungen sind willkommen. Mit Dank an kingcap1 und FrodoVDR für die Anregung.

### Was sich für dich ändert — Cockpit & Speicher

- **ROI-Dashboard öffnet wieder** (#285): das ROI-Dashboard zeigte „Ein Fehler ist aufgetreten" — derselbe Fehlertyp wie zuvor bei der Speicher-Rubrik. Behoben und mit automatischen Tests abgesichert. Mit Dank an Klausnn für die Meldung.
- **Speicher-Effizienz realistischer dargestellt**: die Effizienz-Anzeige im Speicher-Dashboard konnte für einzelne Monate über 100 % springen. Sie zeigt jetzt einen gleitenden 12-Monats-Wert, der diesen Monatsgrenzen-Effekt herausrechnet. Mit Dank an Rainer für die Meldung.

### Was sich für dich ändert — Daten-Checker

- **Kein Fehlalarm mehr bei der Netzladung**: der Daten-Checker meldete „Netzladung übersteigt Gesamtladung", obwohl es nur eine harmlose Differenz an der Monatsgrenze war (z. B. Akku-Nachtladung über Mitternacht). Die Prüfung läuft jetzt über die gesamte Historie — echte Erfassungsfehler werden weiterhin erkannt. Mit Dank an Rainer für die Meldung.

### Was sich für dich ändert — Monatsabschluss & weitere Korrekturen

- **Sonstige Positionen wieder löschbar** (#286): im Monatsabschluss ließen sich sonstige Kostenpositionen nicht mehr entfernen — behoben. Mit Dank an rcmcronny für die Meldung.
- **Nächtlicher Hintergrund-Job repariert** (#286): ein Job brach nachts mit einem Fehler ab — behoben.
- **EcoFlow-Import: längere Zeiträume**: der Cloud-Import aus dem EcoFlow-Konto brach bei bestimmten Zeiträumen ab. eedc fragt die Daten jetzt in kleineren Blöcken ab; historische Daten beliebigen Alters lassen sich importieren. Mit Dank an Dirk für die Meldung.

---

## v3.31.8 — Speicher-Rubrik repariert, EcoFlow-Import, WP-Saisonvergleich (Mai 2026)

### Was sich für dich ändert — Cockpit

- **Speicher-Rubrik öffnet wieder**: Die Rubrik „Speicher" im Cockpit zeigte seit v3.31.7 „Ein Fehler ist aufgetreten" und ließ sich nicht mehr öffnen. Der Fehler ist behoben — und ein neuer automatischer Test sorgt dafür, dass er nicht zurückkommt. Mit Dank an Rainer für die Meldung.

### Was sich für dich ändert — Wärmepumpe

- **Saisonvergleich genauer und übersichtlicher**: Bei getrennter Strommessung von Heizung und Warmwasser rechnet der Saisonvergleich jetzt nur noch die Heizung — Warmwasser läuft ganzjährig und gehört nicht in einen Heizperioden-Vergleich. Eine neue Fußzeile nennt das Saisonfenster und die Anzahl der berücksichtigten Monate. Dazu: die störenden vertikalen Hilfslinien sind entfernt, die Summen über den Balken sind größer und in hell wie dunkel gut lesbar. Mit Dank an Rainer für das ausführliche Feedback.

### Was sich für dich ändert — Cloud-Import

- **EcoFlow PowerOcean: Cloud-Import repariert**: Der Datenimport aus dem EcoFlow-Konto scheiterte mit einem Signaturfehler. Die Ursache ist behoben, der Cloud-Import funktioniert wieder. Mit Dank an Dirk für die Meldung.

---

## v3.31.7 — Bündel-Release: Prognose-Korrektur, klare Community-Fehlermeldungen, Backup-Abfrage (Mai 2026)

### Was sich für dich ändert — Prognose

- **Prognose-Korrektur überprüft und nachgezogen**: Der eedc-Korrekturfaktor (Lernfaktor) und die wetterabhängige Korrektur wurden im Code überprüft, analysiert und aktualisiert; zusätzliche automatische Tests sichern die Berechnung jetzt ab. Die eedc-Prognose-Werte sind dadurch zuverlässiger.

### Was sich für dich ändert — Community & Teilen

- **Klare Fehlermeldung statt nur „Fehler 422"** (#282): Schlägt das Teilen der Anlagendaten mit dem Community-Server fehl, zeigt eedc jetzt die konkrete Ursache an — welches Feld beanstandet wurde und warum — statt einer generischen Fehlernummer. Mit Dank an SlapJackNpNp für die Meldung.

### Was sich für dich ändert — Bedienung

- **Backup-Hinweis vor dem Löschen** (#283): Vor dem Löschen einer Anlage oder Komponente erscheint jetzt eine Sicherheitsabfrage mit Erinnerung an ein Backup. Schlägt das Löschen fehl, wird der Grund direkt im Dialog angezeigt. Mit Dank an stlorenz für den Beitrag.

### Was sich für dich ändert — Auswertung & Speicher

- **Speicher-Wirtschaftlichkeit: neue Kennzahlen sichtbar** (#264): Die in v3.31.6 angekündigten Cockpit-Kacheln zur Speicher-Netzladung — dynamischer Ladepreis und SoC-korrigierter Wirkungsgrad — sind jetzt im Speicher-Dashboard sichtbar.
- **Speicher-Monatsabschluss: Label „Ladung" eindeutiger** (#281): Bei Speichern, die auch aus dem Netz laden, war die Beschriftung „Ladung" missverständlich — sie unterscheidet jetzt klar zwischen PV- und Netzladung.

### Was sich für dich ändert — Daten-Checker

- **Kleinere Korrekturen**: Ein „Beheben"-Link, der ins Leere führte, ist repariert. Ein Fehlalarm für Tage, die noch in der Zukunft liegen, entfällt.

---

## v3.31.6 — Bündel-Release: E-Mobilitäts-Zahlen konsistent, Saison-Vergleich, Daten-Checker (Mai 2026)

### Was sich für dich ändert — E-Mobilität

> Wenn dir bei Wallbox, E-Auto und Auswertungen unterschiedliche Lade-Zahlen aufgefallen sind: hier ist die Erklärung.

- **Wallbox, E-Auto, Komponenten und Cockpit-Übersicht zeigen jetzt durchgängig dieselben Lade-Zahlen** (#262): Bisher konnte dieselbe Ladung in vier Menüs vier verschiedene Werte ergeben — beim evcc-Import war der Netz-Anteil im Wallbox-Dashboard und in *Auswertungen → Komponenten* zu hoch, in Extremfällen ergab sich ein PV-Anteil über 100 % (Komponenten zeigte z. B. 48 % PV + 85 % Netz). Ursache: die Sichten führten PV-, Netz- und Gesamt-Ladung getrennt zusammen, sodass die Anteile aus verschiedenen Quellen stammen konnten. Jetzt führen alle Sichten die Lade-Daten geschlossen aus einer Quelle zusammen — PV + Netz ergeben immer die Gesamtladung, und das *Cockpit → E-Auto* (das schon vorher stimmte) ist der gemeinsame Bezugswert. Mit Dank an junky84 für den genauen Re-Test mit Screenshots.

### Was sich für dich ändert — Auswertung & Cockpit

- **Wärmepumpe: Saison-Vergleich im Monatsvergleich** (#195): Im WP-Cockpit kannst du den Monatsvergleich jetzt auf Saison-Fenster umstellen — Winter (Nov–Feb), Heizperiode (Okt–Apr) oder Sommer (Jun–Aug) — statt nur einzelner Monate. So lassen sich Heizsaisons über mehrere Jahre direkt vergleichen.
- **Vergleichsjahr als Absolutwert in der Auswertungs-Tabelle** (#195): Die Auswertungs-Tabelle zeigt das Vergleichsjahr jetzt zusätzlich als absoluten kWh-/€-Wert, nicht nur als Differenz zum aktuellen Jahr.
- **Energieprofil-Tagestabelle: Komponenten-Spalten**: Die Tages-Tabelle im Energieprofil hat zusätzliche Spalten für die einzelnen Komponenten (Speicher, Wärmepumpe, E-Mobilität …).
- **Label-Korrektur IST/SOLL**: Kleine Korrektur einer Spalten-Beschriftung, die SOLL und IST vertauscht hatte (rapahl-Hinweis).

### Was sich für dich ändert — Daten-Checker

- **Stillgelegte Investition wird nicht mehr als „Sensor fehlt in HA-Statistik" gemeldet** (#613): Der LTS-Check mahnte den kWh-Sensor einer stillgelegten Investition weiter an, obwohl sie ein Stilllegungs-Datum hat. Der Stilllegungs-Sweep aus v3.31.5 (#608) hatte diesen einen Prüf-Pfad übersehen. Behoben. Mit Dank an MartyBr für die Forum-Meldung.

### Unter der Haube — für Mitwirkende

- **Speicher-Wirtschaftlichkeit — Etappe C-Backend** (#264, stlorenz): Die Berechnung der Speicher-Netzladung nutzt jetzt den dynamischen Ladepreis aus den Stundenwerten (TEP) und einen SoC-korrigierten Wirkungsgrad statt eines Parameter-Durchschnitts. Die zugehörigen Cockpit-Kacheln folgen in einem Nachgang-Release.
- **PVGIS-Systemverluste zentralisiert**: Die Systemverluste-Konstante (14 %) und ihre Auflösung aus dem anlagenspezifischen PVGIS-Setup waren über mehrere Dateien dupliziert — jetzt ein zentraler Helper. Rein intern, keine Verhaltensänderung.

---

## v3.31.5 — Bündel-Release: BKW-Doppelzählung weg, Prognosen-Tab erweitert, Daten-Checker präziser (Mai 2026)

### Was sich für dich ändert — PV-Werte und IST

> Schwerpunkt der Tester-Feedback-Runde von Rainer und Steffen2 — wenn deine Anzeige bisher höher war als erwartet, sind hier die Erklärungen.

- **PV-IST-Wert beim Balkonkraftwerk wird nicht mehr doppelt gezählt**: Wer ein Balkonkraftwerk neben „normalen" PV-Modulen in eedc als eigene Investition geführt hat, sah in den Tages-, Wochen- und Monats-Auswertungen einen IST-Wert, der die BKW-Erzeugung doppelt enthielt — einmal über die Zähler-Tagesgesamtwerte und ein zweites Mal über die Live-Tagesverlauf-Daten. Die Differenz war je nach BKW-Größe spürbar (bei einem typischen 600-800-Watt-BKW etwa 1-2 kWh pro Tag, kumuliert deutlich). Mit diesem Release stimmen die IST-Werte wieder. **Bestehende Tage werden nicht automatisch neu gerechnet** — wenn du Wert auf saubere historische Werte legst, repariere die betroffenen Tage über *Einstellungen → Daten → Energieprofil → Reparatur-Werkbank → Mehrere Tage neu berechnen*. Künftige Tage sind automatisch korrekt. Mit Dank an Rainer (rapahl) für die genaue Diagnose.
- **PV-Über-Erfassung wird im Daten-Checker erkannt**: Neuer Plausibilitäts-Check meldet, wenn die Performance Ratio (Verhältnis IST zu PVGIS-Soll) an mindestens drei Tagen über 1,05 liegt oder der spezifische Tagesertrag auf >7 kWh/kWp steigt. Beides sind typische Hinweise auf Doppelerfassung (z. B. wenn ein BKW-Sensor im Wechselrichter-Wert schon enthalten ist und zusätzlich extra gemappt wurde). Hinweis-Charakter, keine automatische Reparatur — du siehst die Treffer der letzten 30 Tage als Diagnose-Eintrag und entscheidest selbst.

### Was sich für dich ändert — Prognosen

- **Prognose-Vergleichs-Tab: 4 Tage zurück + 3 Tage vorwärts**: Die 7-Tages-Tabelle im Prognosen-Tab zeigte bisher nur die kommenden 7 Tage. Rainer-Hinweis: Niemand schreibt sich vergangene Prognose-Werte auf, sie verschwinden sonst spurlos. Die Tabelle zeigt jetzt 4 historische Tage (mit echtem IST und den damals gespeicherten Prognosen aus OpenMeteo, eedc-kalibriert und Solcast) plus 3 zukünftige Tage. Eine Trennlinie trennt Vergangenheit und Zukunft; historische Zeilen blenden Wetter-Icons und Solcast-Konfidenzband aus, weil die im Rückblick keinen Mehrwert haben.

### Was sich für dich ändert — Daten-Checker

- **Stilllegungs-Filter greift jetzt auch in der kWp-Summe + Sensor-Mapping-Prüfung** (#608): Wenn du eine Anlage stillgelegt hast (z. B. alte PV-Module durch eine neue Aufteilung Nord/Süd ersetzt mit Stilllegungs-Datum), wurde die stillgelegte Anlage trotz Datum noch in zwei Daten-Checker-Sichten mitgerechnet: in der Summe der Modul-kWp und im Sensor-Mapping-Vollständigkeits-Check. Beide ignorieren das Stilllegungs-Datum jetzt korrekt. Inbetriebnahme-Monat (also der Monat *vor* dem Stilllegungs-Datum) wurde versehentlich als „fehlend" gemeldet — auch behoben. Mit Dank an Steffen2 für die Befund-Liste.
- **Reparatur-Werkbank-Link in den Datenquellen-Konflikten**: Bei „14 Felder mit mehreren Quellen…" gab es bisher zwar einen Hinweis auf die Reparatur-Werkbank, aber keinen Knopf, der dich direkt dorthin bringt. Jetzt liegt der „Beheben"-Link direkt im Eintrag und geht auf die richtige Stelle (vorher zeigten drei Daten-Checker-Links auf eine veraltete Route, die zu „Seite nicht gefunden" führte — auch korrigiert).

### Was sich für dich ändert — E-Mobilität, Custom-Import, Cloud-Import

- **E-Mobilitäts-Ersparnis bei evcc: Pool-Drift zwischen Cockpit-Komponenten und Aktueller-Monat-Sicht** (#260 Folge): Im Cockpit-Komponenten-Sicht und in der Aktueller-Monat-Sicht zeigten dasselbe E-Auto unterschiedliche Ersparnisse, wenn evcc mehrere Wallbox-Sessions im Monat hatte. Ursache war eine Inkonsistenz in der Pool-Aggregation — bereits gefixt.
- **Custom-Import: Einheits-Konvertierung + Legacy-Top-Level-Targets** (#229 JanKgh-Folge): Wer per CSV-Import Werte in Wh oder MWh statt kWh hochlädt, wird jetzt automatisch in kWh konvertiert. Außerdem akzeptiert der Import auch ältere Top-Level-Spalten-Namen aus früheren eedc-Versionen, ohne dass du sie umbenennen musst.
- **Cloud-Import: Fehlermeldungen sichtbar im Wizard** (Dirk-PN): Wenn ein Verbindungstest fehlschlug, sahst du bisher nur „Verbindung fehlgeschlagen" — die konkrete API-Antwort vom Anbieter (z. B. „Invalid signature", „Access key not found") wurde verschluckt. Jetzt zeigt der Wizard die volle Fehlermeldung direkt unter dem Status-Indikator. Beim EcoFlow-PowerOcean-Connector zusätzlich ausführlicheres Logging im Backend zur Diagnose (Provider ist als „nicht mit echtem Gerät getestet" markiert — falls du ihn nutzt, sind die neuen Meldungen das Sprungbrett für eine gemeinsame Fehlersuche).

### Unter der Haube — für Mitwirkende

- **Berechnungs-Layer als Single Source of Truth** ([ADR-001](https://github.com/supernova1963/eedc-homeassistant/blob/main/docs/ADR-001-BERECHNUNGS-LAYER.md)): Aggregat-Funktionen (Whitelist-Filter für PV-Erzeugung, Σ-Helper, Invarianten) liegen jetzt in `backend/core/berechnungen/` — bisher waren sie über mehrere Domain-Module verteilt, was zur BKW-Doppelzählung beigetragen hat. Pytest-Konformitäts-Test blockiert künftig PRs mit dupliziertem Pattern, und der Tages-Aggregator (`aggregate_day`) prüft am Ende jedes Schreib-Laufs eine Konsistenz-Invariante zwischen Stunden- und Tages-Werten — Drift wird sofort im Log sichtbar statt erst Wochen später durch Anwender-Meldungen.
- **Etappe 4 (HA-Statistics-LTS als Source-of-Truth) zu Ende geführt**: Im HA-Add-on-Modus ist der Live-Σ-Riemann-Pfad in der Tages-Aggregation jetzt vollständig deaktiviert — HA-Long-Term-Statistics ist alleinige Datenquelle für Tages-Komponenten-Summen. Im Standalone-Modus ohne HA-Anbindung bleibt der Live-Pfad als Fallback aktiv.

---

## v3.31.4 — Bündel-Release: Sicherheits-Härtung + Speicher-Etappe A/B + Tester-Beiträge (Mai 2026)

### Sicherheits-Härtung als Schwerpunkt *(v3.31.4)*

> 🔐 **Drei Schichten gegen typische Angriffsvektoren** — und gleichzeitig zwei Etappen aus Stefans Speicher-Konzept, eine klarere README für den Standalone-Modus, und ein Pool-Drift-Fix für die E-Mobilitäts-Auswertung beim evcc-Import. Beitragend: stlorenz (sieben PRs aus #264 + Folge-Fixes), Forum-Tester (junky84 #262).

#### Was sich für dich ändert — Sicherheit

- **Credential-Maskierung jetzt deny-by-default**: API-Keys, Tokens und Passwörter, die du in den Connector-Test oder das Setup eingibst, werden vor jeder Log-Ausgabe oder Debug-Anzeige maskiert. Bisher war das eine Allow-List für bekannte Feld-Namen — jetzt sind alle Passwort-Felder und sensibel benannte Token-Felder automatisch erfasst, ohne dass jemand eine neue Liste pflegen muss.
- **SSRF-Schutz im Connector-Test**: Wenn du eine fremde URL in den Cloud-Import-Test eingibst, prüft eedc jetzt vor dem Verbindungsaufbau, ob die Ziel-IP-Adresse zu einem geschützten Bereich gehört (Loopback, Link-Local, Multicast, IPv4/IPv6-Mapped, private Bereiche). DNS-Rebinding-Angriffe werden durch erneutes Auflösen direkt vor dem Connect verhindert. Heißt: ein eingegebener Hostname kann eedc nicht dazu bringen, intern auf 127.0.0.1 oder andere Ressourcen im eigenen Netz zuzugreifen.
- **Setup-Anleitung ohne `curl | bash`**: Wer eedc lokal als Entwicklungsumgebung aufsetzt, sah bisher das übliche `curl … | bash`-Pattern. Das ist raus — die Anleitung zeigt jetzt explizit `curl → less → bash` mit Sicherheitshinweis: erst das Skript herunterladen, sichten, dann ausführen. Pipe-to-shell wird nirgendwo mehr empfohlen.
- **Setup-Skript ohne automatische Maintainer-Identität**: Falls du das Setup-Skript ohne gesetzte Git-Identität ausgeführt hast, setzte es bisher Platzhalter-Werte des Maintainers (`supernova1963`) ein. Das ist raus — das Skript gibt jetzt nur einen Hinweis mit Platzhalter-Anleitung aus, jeder trägt seine eigene Identität ein.

#### Was sich für dich ändert — Standalone-Modus (außerhalb HA)

- **README präzisiert: LAN-Only-Setup**: Die Standalone-Variante von eedc (Docker ohne Home Assistant) ist als LAN-Only-Setup konzipiert. Wer die App über das Internet erreichbar machen will, findet jetzt in der README eine kompakte Übersicht zu etabliertem Standard-Tooling für Authentifizierung: nginx + Basic-Auth, OAuth2-Proxy, Cloudflare Access, Tailscale Funnel. Ein eigener Auth-Layer im Container ist bewusst *nicht* geplant — diese Werkzeuge lösen das Problem nachweislich besser. Im HA-Add-on-Modus liegt der Auth-Layer ohnehin bei Home Assistant, da ändert sich nichts.

#### Was sich für dich ändert — Speicher-Wirtschaftlichkeit

- **Neuer Schalter „Speicher lädt aus dem Netz"** (Etappe A, stlorenz #269): Wenn du einen Speicher hast, der gezielt aus dem Netz lädt (z. B. bei Tibber-/aWATTar-Tarif-Optimierung zur Niedrig-Preis-Zeit), kannst du das jetzt pro Speicher-Investition ankreuzen. Vorbereitung für die nächste Etappe — die Wirtschaftlichkeits-Berechnung bekommt damit den ehrlichen Bezugspreis-Anker.
- **ROI berücksichtigt PV-/Netz-Anteil der Speicher-Ladung** (Etappe B, stlorenz #271): Bisher wurden alle Speicher-Ladungen pauschal mit Bezugspreis bewertet. Bei rein PV-geladenen Speichern war die Rechnung systematisch zu negativ. Jetzt unterscheidet eedc nach PV-Anteil und Netz-Anteil — bei rein-PV-Speichern fällt der Netz-Bezugspreis weg, bei Tibber-Lade-Speichern bleibt er drin. Die Trennung läuft konsistent über alle ROI-Sichten (Cockpit-Übersicht, Investitions-Details, Aussichten).
- **Etappe C kommt im nächsten Release**: TEP-Stunden-Lookup für den realen Ø-Ladepreis bei dynamischen Tarifen, plus SoC-korrigierter Wirkungsgrad-Helper. Backend + Frontend werden zusammen ausgeliefert, damit du den ganzen Block in der UI siehst.

#### Was sich für dich ändert — E-Mobilität und Dashboards

- **Wallbox-/E-Auto-Dashboards: Netzladung beim evcc-Import korrekt erfasst** (#262 junky84-Folge nach v3.31.3): Wer evcc-Portal-Daten importiert, sah in v3.31.3 in Wallbox-Dashboard PV-Anteil 100 % und Netzladung 0 kWh trotz vorhandenem Netzbezug. evcc-CSV liefert nur Gesamt-Ladung und PV-Prozent — eedc berechnet jetzt die Netzladung als `Gesamt − PV` und schreibt sie ins Feld `ladung_netz_kwh`. Acht Auswertungs-Stellen (Cockpit-Übersicht, Cockpit-Komponenten, Aktueller Monat, Investitionen, HA-Export, PDF-Jahresbericht) lesen denselben Helper und zeigen jetzt konsistente Werte. Mathematik dreifach validiert gegen die offiziellen evcc-HA-Template-Helper und reale CSV-Exports.
- **EVCC-Import erkennt englische CSV-Header** (PR #268 stlorenz): Wer evcc auf englischer Sprache betreibt, konnte den CSV-Export bisher nicht importieren — der Parser kannte nur die deutschen Spalten-Überschriften. Beide Sprachen werden jetzt erkannt; bei dritter Sprache erscheint ein klarer Hinweis im Import-Dialog statt einer kryptischen Fehlermeldung.
- **Dienstwagen-Schalter konsistent gelesen** (PR #270 stlorenz): Der „Dienstwagen"-Boolean wurde teils als String, teils als echter Bool gelesen. Bei Mischzuständen konnte die Ersparnis-Berechnung falsche Werte zeigen. Helper normalisiert beide Repräsentationen.
- **Daten-Checker-NameError beim Aufruf gefixt** (PR #274 Eigentor-Hotfix): Beim Merge des Dienstwagen-Refactors gegen v3.31.3 schlug der Daten-Checker mit NameError fehl (500-Fehler bei jedem `/api/check`-Aufruf, in der App: leere Daten-Checker-Liste). Gefixt + neuer Test, der den gesamten Check-Pfad durchläuft.

#### Was sich für dich ändert — Cockpit

- **Spezifischer Ertrag bei „alle Jahre" + nachträglichen Erweiterungen** (PR #273 stlorenz): Wer die Anlage über die Jahre erweitert hat (Modul hinzu, Speicher hinzu, Wallbox dazu), sah im Cockpit-Filter „alle Jahre" beim spezifischen Ertrag eine verzerrte Anzeige — die Berechnung mittelte über die aktuelle Anlagenleistung, nicht über die zum jeweiligen Zeitpunkt installierte. Jetzt periodengenau pro Jahr gewichtet — historische Jahre bekommen ihre damalige Leistung als Bezug.

#### Aufgeräumt im Repository

- **`eedc/eedc.db` und Backup-Begleitdateien gitignoret**: Die SQLite-Stub-Datei aus älteren Releases wird nicht mehr getrackt; `*.db` / `*.sqlite` / `*.sqlite3` plus WAL/SHM-Backup-Begleitdateien (`*.db-wal`, `*.db-shm`, PR #272 stlorenz) global ignoriert. Für dich als Anwender unsichtbar — relevant nur für Mitwirkende mit lokalem Klon.
- **Archiviertes Konzept-Dokument korrigiert**: `docs/archive/KONZEPT-ML-PROGNOSE.md` enthielt zwei falsche Aussagen zur Plattform-Unterstützung von SFML Stats. Korrigiert mit Korrektur-Block am Dateianfang (Hinweis-Quelle: SFML-Entwickler Tom-HA / Zara-Toorox).

#### Hinweis für Anwender mit lokalem Klon des GitHub-Repos

Im Laufe des Tages wurden Artefakte aus älteren Releases (alte 0-Byte-DB-Stubs und interne Notiz-Drafts) auch aus der Git-History entfernt — Force-Push auf `main` und alle Tags. Lokale Klone divergieren dadurch und sollten neu gepullt werden:

```bash
git fetch origin
git reset --hard origin/main
```

Für HACS-Add-on-Nutzer ohne lokalen Klon ändert sich nichts — das Update zieht den aktuellen Tag-Inhalt.

---

## v3.31.3 — Bündel-Release: Sieben Bugfixes + Pfad-Hinweise (Mai 2026)

### Bündel-Release nach Etappen-Tagen *(v3.31.3)*

> 🛠 **Bündel statt Einzel-Patches.** Aus Forum und Issues sind sieben kleinere Bugfixes aufgelaufen — jeder für sich kein Release wert, gemeinsam aber der saubere Abschluss. Schwerpunkt: drei Aggregations-Drifts (E-Mobilität, Strompreis, Wallbox-Dashboards), zwei Robustheits-Fixes (Cloud-Import, getrennte WP-Strommessung), zwei stlorenz-Beiträge zur Genauigkeit.

#### Was sich für dich ändert

- **E-Mobilität-Ersparnis stimmt jetzt überall** (#260 NongJoWo): Die Cockpit-Übersicht zeigte ~273 € weniger Ersparnis als das E-Auto-Dashboard. Drei Cockpit-Pfade hatten externe Lade-Kosten hartcodiert auf 0 € — sie ziehen jetzt denselben Wert wie das Dashboard.
- **Cloud-Import-Credentials werden automatisch getrimmt** (#261 FrodoVDR): API-Keys werden beim Einfügen aus Hersteller-Portalen oft mit Leerzeichen kopiert, was SolarEdge mit HTTP 403 quittierte. Frontend + Backend trimmen jetzt User-Eingaben vor dem API-Call.
- **Daten-Checker meldet WP mit getrennter Strommessung nicht mehr als „fehlend"** (Forum dietmar1968): Wer seit v3.25.x Strom Heizen und Strom Warmwasser getrennt erfasst, bekam unter Daten-Checker fälschlich „WP-Stromverbrauch fehlt" angezeigt. Die Prüfung respektiert jetzt den getrennten Pfad.
- **Live-Tagesverlauf: glatte Strompreis-Treppe statt EPEX-Sprünge** (#267 rilmor-mhrs): Bei Tibber liefert HA alle 15 Minuten ein Step-Update, die Live-Tagesverlauf-Logik prüfte aber pro 10-Min-Slot — leere Slots fielen auf den EPEX-Börsenpreis zurück (~8 ct statt ~35 ct), die Kurve sah wie ein Sägezahn aus. Jetzt: leerer Slot übernimmt zuerst den letzten Tibber-Wert (Step-Funktion-Semantik), EPEX nur noch als finaler Fallback ohne jeden Tagespunkt.
- **Wallbox- und E-Auto-Dashboards mit Pool-Daten gefüllt** (#262 junky84): Wer evcc-Portal-Import nutzt, sah die Ladedaten in der Cockpit-Übersicht korrekt, aber Wallbox- und E-Auto-Dashboards standen leer. Architektur-Grund: evcc-CSV schreibt Ladedaten in die Wallbox-Investition, beide Dashboards lasen aber nur ihren eigenen Pfad. Sie greifen jetzt analog zur Cockpit-Übersicht auf den Pool zurück; das E-Auto-Dashboard verteilt das Wallbox-Aggregat km-anteilig auf die E-Autos.
- **Spezifischer Ertrag periodengenau** (PR #265 stlorenz): Bei Anlagen mit nachträglicher Erweiterung (Modul oder Speicher hinzu) wird der spezifische Ertrag jetzt periodengenau monatsweise gewichtet bestimmt, nicht auf Stichtag-Leistung.
- **HA-Backup-Konsistenz** (PR #266 stlorenz): WAL-Checkpoint vor jedem Snapshot-Export — verhindert die Race-Condition, in der ein HA-Backup eine inkonsistente eedc-DB aufnehmen konnte.
- **Daten-Checker „Tag reparieren": konkrete Rückmeldung** (Feedback dietmar1968): Bisher kam pauschal „Tag aus HA-Statistics neu aggregiert" zurück — auch wenn der Wert sich tatsächlich nicht geändert hat. Der Toast zeigt jetzt drei Varianten: tatsächliche Reparatur („PV 71,8 → 67,6 kWh"), unveränderter Wert mit Hinweis aufs Sensor-Mapping (HA-LTS deckt einen Sensor möglicherweise nicht ab), oder Fallback ohne Vorher-Wert. Damit erkennst du beim mehrfachen Klicken auf einen Schlag, ob die Reparatur greift oder nicht.

#### Außerdem: UI-Pfad-Hinweise konsistent korrigiert

Hinweistexte in der App (Monatsabschluss-Wizard, Daten-Checker-Drift-Liste) und in den Release-Notes verwiesen auf einen nicht existierenden Menüpunkt „Wartung". Der korrekte Pfad lautet **Einstellungen → Daten → Energieprofil → Reparatur-Werkbank**. Elf Stellen in einem Rutsch gefixt — App + In-App-Hilfe + Release-Notes durchgängig stimmig.

---

## v3.31.1 — Drift zu HA-Statistics sichtbar machen und tagesweise reparieren (Mai 2026)

### Welche Tage weichen vom HA-Statistics-Wert ab? *(v3.31.1)*

> 🔍 **Direkt nach dem Update auf v3.31.0 standen deine bestehenden Tage noch auf ihren alten Werten** — der Auto-Vollbackfill beim Monatsabschluss füllt nur Lücken, ersetzt keine vorhandenen Werte. v3.31.1 macht jetzt im Daten-Checker sichtbar, welche Tage signifikant vom HA-Energy-Dashboard abweichen, und legt einen *Tag reparieren*-Knopf direkt neben jeden Eintrag.

#### Was du tun kannst

1. Öffne **Einstellungen → Daten-Checker**
2. Schau nach der neuen Kategorie **„Datenquelle – Drift zu HA-Statistics"**
3. Pro Eintrag siehst du Datum, eedc-Wert, HA-Statistics-Wert und Differenz in kWh und %
4. Ein Klick auf *„Tag reparieren"* — eedc holt die Werte direkt aus HA-Statistics und schreibt sie in deine Tages-Zusammenfassung
5. Liste leer → alles sauber, kein Handlungsbedarf

#### Schwelle bewusst hoch

Angezeigt werden nur Tage, die *gleichzeitig* mindestens **2 kWh** und mindestens **5 %** vom HA-Statistics-Wert abweichen. Kleine Boundary-Rauschen (Counter-Reset um Mitternacht, Sub-Stunden-Snapshot-Versatz) wird damit unterdrückt — die Liste bleibt fokussiert auf das, was wirklich Bedeutung hat.

Außerdem: maximal 20 Tage werden angezeigt, sortiert nach der absoluten Abweichung. Wenn mehr Tage betroffen sind, erscheint ein zusätzlicher Hinweis-Eintrag „… plus X weitere Tage".

#### Mehrere Tage auf einmal

Wenn du z. B. einen ganzen Monat reparieren willst, ist *Einstellungen → Daten → Energieprofil → Reparatur-Werkbank → Bereich neu aggregieren* der schnellere Weg. **Bewusst nicht als Massen-Knopf in der Diff-Liste** — Massen-Aktionen sollen aktiv gewählt werden, nicht versehentlich passieren.

#### Was passiert beim Klick auf „Tag reparieren"

eedc liest die Stunden-kWh des Tages frisch aus HA-Statistics, baut die TagesEnergieProfil-Zeilen und die TagesZusammenfassung neu auf — exakt mit den Werten, die HA selbst für diesen Tag in der Statistik hat. Die alten eedc-Werte werden überschrieben. Manuell überschriebene Werte (Provenance `manual:*`) bleiben unverändert — die Schutzhierarchie aus v3.30.3 gilt weiter.

*(Direkt-Konsequenz aus Etappe 4 — die Architektur ist sauber, jetzt bekommen Anwender auch das Werkzeug, sie für bestehende Tage zu nutzen.)*

---

## v3.31.0 — Energie-Aggregate konsistent aus HA-Statistics (Mai 2026)

### Eine Quelle für PV, Verbrauch, Einspeisung — und auch Peak-Werte *(v3.31.0)*

> 🎯 **Schluss mit „drei verschiedenen Zahlen für denselben Tag".** Im Genauigkeits-Tracking, in der Tages-Energieprofile-Tabelle und in der Stunden-Σ-Zeile im Monatsbericht konnten bisher leicht abweichende Werte für die PV-Erzeugung auftauchen — bei manchen Anlagen ein paar Prozent, bei einzelnen Konstellationen sogar zehn Prozent. Ursache: zwei parallele Rechenpfade (Live-Tagesverlauf-Integration plus Sensor-Snapshot-Diff) mit leicht unterschiedlichen Aggregationsfenstern. Ab v3.31.0 lesen alle Sichten aus derselben HA-Statistics-Quelle — und auch die Tages-Peaks (höchste PV-Leistung, Netzbezug-Spitze, Einspeise-Spitze) sowie Speicher-SoC und Strompreis-Stundenmittel kommen jetzt direkt aus HA-Statistics, nicht mehr aus eigener Berechnung.

#### Was sich für dich ändert

- **Identische Werte über alle Sichten**: Tages-Energieprofile-Tabelle „PV-Ertrag", Σ der 24 Stundenwerte im Monatsbericht-Energieprofil und Genauigkeits-Tracking-IST sind ab v3.31.0 immer gleich — per Konstruktion, nicht per Zufall. Das gilt analog für Einspeisung, Netzbezug, Wärmepumpen-Strom, Wallbox-Ladung und Speicher-Netto.
- **Identisch zum HA-Energy-Dashboard**: Die kanonische Tagessumme stimmt jetzt durchgängig mit dem überein, was du im HA-Energy-Dashboard für denselben Tag siehst. Wer beide Apps offen hat, kann sich auf jedes Wert verlassen.
- **Genauigkeits-Tracking-Bug nebenbei gefixt**: Der IST-Wert summierte bisher auch Batterie-Netto-Ladung mit ein (wenn die Batterie über den Tag mehr geladen als entladen hatte). Bei einer ~5-kWh-Netto-Ladung pro Tag waren das ~5 kWh künstliche IST-Überschätzung — Prognose-MAE wurde dadurch geschönt. Jetzt zählt nur noch echte PV- und Balkonkraftwerk-Erzeugung als IST.
- **Tages-Peak-Werte ohne Unterschätzung**: Die höchste PV-Leistung, die Netzbezug-Spitze und die Einspeise-Spitze eines Tages wurden bisher aus 10-Minuten-Mittelwerten geschätzt — kurze Spitzen verschwanden dabei systematisch in der Mittelung. Ab v3.31.0 liest eedc diese Werte direkt aus den Stunden-Min/Max-Spalten der HA-Statistics — denselben Werten, die HA-Recorder im 5-Sekunden-Bucket beobachtet hat. Das ergibt die physikalisch korrekte Tagesspitze.
- **Speicher-SoC und Strompreis-Stunden aus HA-Statistics**: Die stündlichen Speicher-SoC-Mittelwerte und Tibber/aWATTar-Strompreise im Tages-Energieprofil lesen jetzt direkt aus `statistics.mean` statt selbst aus der State-History gemittelt zu werden — gleiche Quelle wie das HA-Energy-Dashboard, gleiche Recompile-Logik. Fällt HA-Statistics für einen Sensor aus, greift der bisherige Mittelungs-Pfad als Fallback.

#### Was passiert beim Update — und was du selbst tun kannst

**Neue Tage (ab dem Update-Zeitpunkt)** werden automatisch aus HA-Statistics aggregiert — du musst nichts tun, der Scheduler greift den neuen Pfad sofort.

**Bestehende Tage (vor dem Update)** bleiben zunächst auf ihrem alten Wert. Der Auto-Vollbackfill beim nächsten Monatsabschluss füllt nur *fehlende* Tage nach (er ist bewusst additiv, damit manuell korrigierte Werte nicht überschrieben werden). Wenn du gezielt einen bestehenden Tag auf die saubere HA-Statistics-Quelle umstellen willst, hast du zwei Wege:

1. **Einzelner Tag** (z. B. der Tag mit der bekannten Drift): `Auswertungen → Energieprofil → Tagestabelle → Reload-Knopf (↻)` beim betreffenden Tag — du bekommst eine Vorschau (alt vs. neu) vor der Übernahme.
2. **Zeitraum** (z. B. ein Monat): `Einstellungen → Daten → Energieprofil → Reparatur-Werkbank → Bereich neu aggregieren` mit Von-/Bis-Datum.

#### Wo siehst du, dass es funktioniert

Im Daten-Checker (Einstellungen → Daten-Checker) gibt es eine neue Kategorie **„Datenquelle – aktiver Pfad"**. Drei mögliche Stati:

1. **HA-Statistics als Source-of-Truth aktiv** (grünes Häkchen) — die letzte Tages-Aggregation lief aus HA-LTS, neue Tage sind sauber
2. **HA-Statistics-Pfad bereit, Aggregate aus älterer Quelle** (blauer Info-Hinweis) — frisch nach Update, vor dem ersten neuen Aggregations-Lauf; löst sich von selbst spätestens beim nächsten Tageswechsel
3. **Standalone-Modus aktiv (kein HA-LTS)** (blauer Info-Hinweis) — gilt für Anwender ohne HA-Add-on; eedc nutzt 5-Minuten-Sensor-Snapshots als Fallback, mit leicht eingeschränkter Genauigkeit

#### Hintergrund

Detaillierte Architektur-Beschreibung (für technisch Interessierte): das Aggregat-System ist ab v3.31.0 ein Cache von HA-Statistics-Long-Term, nicht mehr eine eigenständige Berechnung parallel dazu. Damit gilt automatisch: was im HA-Energy-Dashboard steht, steht auch in eedc. Vollständiges Konzept in `docs/KONZEPT-ETAPPE-4-HA-LTS-SOT.md` im Repo.

*(Aus dem Forum + PNs als Anwender-Beobachtung über mehrere Wochen — Konsistenz-Drift war eine echte Vertrauenslücke.)*

---

## v3.30.x — Prognosequellen-Wahl, Strompreis-Vorschlag, Counter-Spike-Schutz, Klimaanlagen (Mai 2026)

### Split-Klimaanlagen sind jetzt Wärmepumpen *(v3.30.3)*

> ❄️ **Klimaanlage = Luft-Luft-Wärmepumpe.** Wer eine Split-Klimaanlage in eedc abbilden will, kann sie ab v3.30.3 direkt als Wärmepumpe vom Typ „Luft-Luft (Klimaanlage)" anlegen — sie landet damit im Cockpit-Wärmepumpenbereich und in der Komponenten-Auswertung, statt bisher unsichtbar unter „Sonstiges" zu bleiben.

#### Was sich für dich ändert

- **Wärmepumpenart „Luft-Luft (Klimaanlage)" voll unterstützt**: bei Anlage-/Investitions-Bearbeitung den Subtyp wählen, eedc erwartet dann nur den Stromverbrauchs-Sensor. Die JAZ-Kachel bleibt sauber leer („—") statt einen irreführenden Wert „0.0" zu zeigen — Klimaanlagen haben üblicherweise keinen Wärmemengenzähler, das ist physikalisch korrekt so.
- **Daten-Checker meldet keine „Heizwärme fehlt"-Warnung mehr** für Luft-Luft-WPs. Bei klassischen Luft-Wasser-/Sole-Wasser-/Grundwasser-WPs bleibt die Warnung erhalten (sie haben in der Regel einen Wärmemengenzähler).
- **WP-Wizard zeigt einen Hinweis** beim Wählen von „Luft-Luft (Klimaanlage)": kurze Erklärung, dass Stromverbrauch ausreicht.

#### Migrations-Tipp für Bestandsanwender

Wenn deine Klimaanlage bisher als „Sonstiges" geführt wird:
1. Neue Investition vom Typ „Wärmepumpe" anlegen, Wärmepumpenart **„Luft-Luft (Klimaanlage)"** wählen
2. Denselben Stromverbrauchs-Sensor zuweisen
3. Alte „Sonstiges"-Investition löschen

Die Klima taucht danach im Cockpit-Wärmepumpenbereich auf, in der Komponenten-Auswertung und in der Community (gruppiert mit anderen Luft-Luft-Klimas).

#### Was Phase 1 *nicht* enthält

Eigene Kühlenergie-Erfassung, EER für den Kühlbetrieb und Modus-Erkennung (heizt jetzt / kühlt jetzt) über Thermostat-Entitäten — das sind Themen für eine spätere Phase 2, anlassbezogen.

#### Bonus: Sonstiges-Sektion im Cockpit-Hauptbild

Wer „Sonstiges" für andere Verbraucher (Pool, Sauna, Werkstatt) oder Erzeuger nutzt, sah die Werte bisher in der Monatsübersicht und im Detail-Dashboard — aber **nicht** in der Cockpit-Übersicht (Hauptseite). Ab v3.30.3 erscheint dort eine eigene Sonstiges-Sektion mit Erzeugungs- und/oder Verbrauchs-KPI-Kacheln (je nachdem, was du gepflegt hast).

*(alex_s9027, Forum-Beitrag #548 vom 2026-05-15.)*

---

### Manuelle Eingaben gewinnen immer *(v3.30.3)*

> ✏️ **Wenn du auf „Speichern" klickst, wird gespeichert.** Es konnte vorkommen, dass eine im Wizard oder Monatsformular eingegebene Zahl nach dem Speichern verschwand, weil der interne Quellen-Konflikt-Schutz aus einer früheren Reparatur-Aktion noch wirkte. Ab v3.30.3 gewinnt jede explizite User-Eingabe — egal, welche Quelle das Feld vorher beschrieben hat.

#### Was sich für dich ändert

- **Im Monatsabschluss-Wizard und im Monatsformular** kannst du jedes Feld jederzeit überschreiben. Auch wenn das Feld früher per Reparatur-Operation gesetzt wurde, gilt jetzt: explizite Eingabe schlägt alles.
- **Schutzrichtung umgekehrt** wirkt weiter wie bisher: Hintergrund-Vorgänge (Cloud-Sync, HA-Statistics-Backfill, Aggregator-Roll-up) können einen manuell gepflegten Wert nicht überschreiben. Diese Schutzrichtung war schon immer korrekt — neu ist, dass es keinen Schlupfloch-Fall mehr gibt, in dem manuelle Eingabe still abgewiesen wird.

*(FrodoVDR, GitHub-Issue #251.)*

---

### PV-Counter-Spike-Cap *(v3.30.2)*

> 🛡️ **Schluss mit „die Reparatur ändert nichts".** Wenn der HA-PV-Zähler nach einem Neustart einen unsinnigen Stunden-Sprung hatte (z. B. +109 kWh in einer Stunde bei einer 11-kWp-Anlage), wurde dieser Spike bisher vom Daten-Checker zwar *erkannt*, aber „Tag neu aggregieren" hat ihn nicht geheilt — Reaggregation lieferte denselben falschen Wert. Ab v3.30.2 cappt der Aggregator solche Stundenwerte präventiv.

#### Was sich für dich ändert

- **Stundenwerte > kWp × 1,5 werden zur Datenlücke**. Beispiel bei einer 11,2 kWp-Anlage: alles über 16,8 kWh in einer einzelnen Stunde gilt als Counter-Off-by-one und wird in `TagesEnergieProfil` als Lücke (—) gespeichert statt als Spike. Heatmap, Lernfaktor und Monatsbericht zeigen die Lücke ehrlich statt einen physikalisch unmöglichen Wert mitzuschleppen.
- **„Tag neu aggregieren" funktioniert jetzt auch bei Counter-Spikes**. Wer einen Spike in der Vergangenheit hat: **Einstellungen → Daten → Energieprofil → Reparatur-Werkbank → Tag neu aggregieren** für den betroffenen Tag — die Werkbank zeigt jetzt eine echte Änderung statt „0 Slots geändert".
- **Anlagen ohne hinterlegte PV-Leistung** sind nicht betroffen — ohne kWp-Angabe kann eedc keine sinnvolle Schwelle ableiten. Der Stammdaten-Check erinnert ohnehin separat daran.

*(Forum-Beitrag #529, dietmar1968.)*

---

### Prognosequellen-Wahl pro Anlage *(v3.30.0 / v3.30.1)*

> ☀️ **Drei PV-Prognosequellen zur Auswahl.** Jede Anlage kann jetzt entscheiden, welche Quelle sie als Tagesprognose hernimmt — und Auto-Discovery erkennt die installierten Integrationen automatisch.

#### Was sich für dich ändert

- **Drei Optionen in den Anlagen-Einstellungen**:
    - **eedc-optimiert** (Standard, Empfehlung): OpenMeteo × anlagenspezifischer Lernfaktor — funktioniert überall, auch standalone, lernt mit der Zeit aus deinen eigenen IST-Werten.
    - **Solcast** (pur): Satellitenbasierte Prognose direkt, ohne eedc-Korrektur. Ideal für alle, die Solcast schon nutzen und der Quelle vertrauen.
    - **Solar Forecast ML** (pur): ML-basierte Prognose direkt aus der HA-Integration, ohne eedc-Korrektur. Nur im HA-Add-on verfügbar.
- **Auto-Discovery**: Wenn du Solcast oder Solar Forecast ML in HA installiert hast, erkennt eedc die Sensoren automatisch — kein Sensor-Mapping mehr im Wizard nötig.
- **Solcast Standalone**: Wer eedc als Docker-Container ohne HA betreibt, kann den Solcast-API-Token + Resource-IDs direkt im Sensor-Mapping-Wizard eintragen.
- **Quellen-Hinweis im Dashboard**: WetterWidget und Live-Dashboard zeigen die aktive Quelle an (nur bei Nicht-Default-Wahl). Wenn die gewählte Quelle ausfällt (Solcast-Quota leer, SFML-Sensor unbekannt), erscheint ein Amber-Hinweis und eedc fällt automatisch auf den eedc-Standard zurück.
- **Lernfaktor O12 ist jetzt der Live-Default** statt einer Diagnose-Option: Der verbesserte Lernfaktor mit Recency-Boost und Trim-Mean (über extreme Tage drüber). Der alte Legacy-Skalar dient nur noch als Fallback und Vergleichs-Wert im Log.
- **Migration alter Einstellungen**: Wer früher `prognose_basis=solcast` gesetzt hatte (Solcast als eedc-Basis), wird automatisch auf `prognose_quelle=solcast` (Solcast pur) migriert.

#### Was sich *nicht* ändert

- **Wer nichts ändert, bekommt eedc-optimiert** — die bewährte Standardwahl mit Lernfaktor. Keine Aktion nötig.
- **Kein Quellenvergleich mehr in Aussichten → Prognosen**: Die alte SFML-Vergleichs-Tabelle/Chart-Spalte entfällt zugunsten der direkten Wahl. Prognosen-Tab bleibt als reine eedc-Diagnose-Sicht (OpenMeteo vs. eedc-kalibriert vs. Solcast vs. IST).

---

### Verbrauchsgewichteter Ø-Strompreis im Monatsabschluss *(v3.30.1)*

> 💶 **Bei dynamischen Tarifen rechnet eedc jetzt mit.** Wer Tibber, aWATTar oder einen anderen stündlich variablen Tarif nutzt: Der Wizard schlägt im Monatsabschluss ab jetzt den verbrauchsgewichteten Monats-Durchschnittspreis vor — aus den über den Monat gesammelten Stundendaten.

#### Was sich für dich ändert

- **Im Monatsabschluss-Wizard**: bei dynamischen Tarifen erscheint der vorgeschlagene Wert direkt mit einer **Konfidenz-Staffelung** (je nachdem, wie viele Stunden im Monat mit Preisdaten abgedeckt sind — voll, teilweise, dünn).
- **Berechnung**: `Σ(strompreis_cent × netzbezug_kWh)` ÷ `Σ(netzbezug_kWh)` über den Monat — also nicht der arithmetische Stundenmittelwert, sondern der tatsächlich-bezahlte Schnitt. Wer abends viel bezieht, sieht den Abendpreis stärker gewichtet.
- **Fallback bleibt**: Wer keine Stunden-Mitschrift hat (kein Strompreis-Sensor gemappt), bekommt wie bisher den aktuellen HA-Sensor-Momentanwert — nur mit reduzierter Konfidenz und einem Hinweis.

*(stlorenz + Joachim-xo, Issue #250 + #122 vandecook.)*

---

### „Database is locked"-Reparatur *(v3.30.1)*

> 🔓 **SQLite-Journal auf WAL umgestellt.** Wer parallel zur Add-on-UI noch andere Schreibvorgänge laufen hatte (MQTT-Inbound, Background-Aggregator, Wizard), bekam gelegentlich „database is locked"-Fehler. Mit Write-Ahead-Logging + 10-Sekunden-Timeout warten parallele Writer jetzt aufeinander statt sofort abzubrechen.

*(PR #248, @stlorenz.)*

---

## v3.29.x — Aggregations- und UX-Bündel (Mai 2026)

### Vorab-Fixes vor Menüstruktur-Konzept *(v3.29.2)*

> 🧹 **Stall ausmisten vor dem großen Konzept.** Kleine UX-Fehler und Schreibweisen-Drift, die nicht auf das künftige Menüstruktur-Konzept warten sollten. Kein neuer Funktionsumfang.

#### Was sich für dich ändert

- **Komponenten-Beiträge zur Finanzierung — Reihenfolge und Icons konsistent**. In **Aussichten → Finanzen** stehen die Komponenten-Beiträge ab jetzt in derselben Reihenfolge wie überall in der App: Speicher → Wärmepumpe → Wallbox/E-Auto-Cluster → Sonstiges. Vorher stand die Wärmepumpe hinter dem E-Auto, und drei Beitragstypen („WP-PV-Nutzung", „WP-Ersparnis vs. Gas/Öl", „E-Auto vs. Benziner") zeigten als Icon einen Batterie-Fallback — jetzt das passende WP-Flammen- bzw. Tank-Icon. Die kleine 4-Kacheln-Zusammenfassung darunter (Speicher EV+ / V2H / E-Auto-PV-Ladung / WP-PV-Direkt) folgt derselben Reihenfolge. *(detLAN, Issue #210.)*
- **Auswertungen: dekoratives Kalender-Icon vor dem Jahres-Filter entfernt**. Genau das gleiche Phänomen, das schon im Cockpit-Banner gefixt war: ein nicht-klickbares Kalender-Icon stand direkt neben dem Jahres-Dropdown — verwirrt, weil's aussieht wie ein Knopf, ist aber keiner. Weniger ist mehr. *(detLAN, Issue #206 P2-Folge.)*
- **Schreibweise „eedc" jetzt durchgängig kleingeschrieben** — passend zum Logo und zur seit v3.26.7 angefangenen Linie:
    - **In der App**: Browser-Tab-Titel, „Erstellt mit eedc"-Footer in Share-Texten, PDF-Bericht-Titel („eedc Anlagenbericht …"), Neustart-Bestätigungs-Meldung, HA-Verbindungsfehler.
    - **In MQTT-Discovery**: HA-Devices erscheinen ab jetzt unter „eedc - <Anlagenname>" statt „EEDC - <Anlagenname>". Entity-IDs bleiben gleich (`sensor.eedc_*`) — keine Daten-Migration nötig, kein Re-Mapping in Dashboards.
    - **Im HA-Sensor-Export-YAML**: die generierten Sensor-Friendly-Names heißen ab jetzt „eedc <SensorName>" statt „EEDC <SensorName>". Wer das Snippet manuell in seine `configuration.yaml` übernommen hat: Nichts brennt, aber für Konsistenz das Snippet aus *Einstellungen → HA-Export* neu kopieren.
    - **In allen Hilfe-Dokumenten**: ~130 Stellen Inline-Erwähnungen umgestellt. Formel-Variablen (z. B. `EEDC_Prognose` in den Berechnungs-Formeln) und historische Env-Var-Namen bleiben in Code-Form unangetastet.

  *(detLAN, Issue #206 P4 — Hilfe-Sweep der noch ausstand seit v3.26.7.)*

#### Was sich *nicht* ändert

- **Funktional ändert sich nichts.** Reine Reparatur-/Polish-Welle.
- **Keine ID-Migration bei MQTT- oder Sensor-Export-Nutzern.** Nur Anzeige-Namen.
- **Code-Identifier und Formel-Variablen** wie `EEDC_ENERGIEPROFIL_QUELLE` (historisches Feature-Flag) oder `EEDC_Abweichung` (Berechnungs-Variable) bleiben — das sind keine Marken-Erwähnungen.

---

### Anschaffungsdatum-Komplettierung + UX-Cluster *(v3.29.1)*

> 🪛 **Tester-Welle vom 13./14. Mai gebündelt geschlossen.** detLAN-Folge zu #236 mit zwei zusätzlichen Pfaden, JanKgh-Multi-String-Verteilungsbug, fünf UX-Verbesserungen. Kein neuer Funktionsumfang.

#### Was sich für dich ändert

- **Wärmepumpe / Speicher / E-Mobilität / Balkonkraftwerk / Sonstiges**: in Monaten vor Anschaffungsdatum wird die Sektion im Monatsbericht jetzt komplett ausgeblendet — kein leerer Block mehr mit „—" überall. Zwei zusätzliche Pfade zu v3.29.0 wurden geschlossen: Sektions-Sichtbarkeit + HA-Sensor-Aggregation respektieren jetzt ebenfalls das Anschaffungsdatum. *(detLAN, Issue #239.)*
- **„—" einheitlich für leere Felder**: an manchen Stellen wurde „---" (drei Bindestriche), an anderen „—" gezeigt — jetzt überall einheitlich „—". *(detLAN, Issue #239.)*
- **Modul-Verteilung bei SolarEdge-Multi-String-Setups**: Wer mehrere PV-Modul-Investitionen mit unterschiedlicher kWp pflegt (z. B. Ost/West-Aufteilung) und die Anlagengesamterzeugung aus einem Wechselrichter-Sensor importiert, sah bisher eine Gleichverteilung (1/N je Modul) statt anteilig nach Modulleistung. Der Verteilungs-Algorithmus liest die kWp jetzt primär aus der Tabellen-Spalte (sauberer Source of Truth) und fällt nur als Fallback auf das Parameter-JSON zurück. Wirkt im CSV-Import und im HA-Live-Datenstrom gleichermaßen. *(JanKgh, Diskussion #229.)*
- **Einstellungen → Allgemein und Protokolle**: zwei weitere überflüssige Page-Überschriften entfernt. In den Protokollen sitzen „Debug" und „Neustart" jetzt in der gleichen Reihe wie die Sub-Sub-Tabs „System-Logs / Aktivitäten" — eine gemeinsame Toolbar statt zwei getrennter Header-Zeilen. Bonus für alle Einstellungs-Seiten: gleichmäßiger Abstand zwischen Sub-Tabs und erstem Inhalt (vorher war der zu eng). *(detLAN, Issue #233.)*
- **Cockpit → Wärmepumpe: kWh-Einheiten überall**. Tabellen-Header („Strom (kWh)" usw.), Wärme-Verteilung Summary und der Wärmeerzeugung-pro-Monat-Chart (Y-Achsen-Beschriftung + Tooltip-Einheit) zeigen jetzt durchgehend die Einheit. *(detLAN, Issue #237.)*
- **Daten-Checker: keine „3× Vorjahr"-Warnung mehr, wenn die Anlage im Vorjahresmonat erst in Betrieb genommen wurde**. Beispiel: Anlage seit Ende März 2022 → März 2022 hat nur ein paar Tage Daten, der März-2023-Vergleich (3× höher) ist deshalb kein Anomaliefall. *(NongJoWo, Issue #240.)*
- **Cockpit → Übersicht → Energie-Bilanz → PV-Monatserträge**: der Mouseover-Tooltip zeigt jetzt den Monatsnamen („Mär 22" / „Jan 26") statt der fortlaufenden Nummer. *(NongJoWo, Issue #241.)*

---

### Fünf Reparaturen + ein UX-Fix in der Vorschau *(v3.29.0)*

> 🪛 **Tester-Welle vom 12./13. Mai gebündelt geschlossen.** Fünf Bugfixes aus detLAN- und NongJoWo-Meldungen plus ein UX-Fix in „Eigene Dateien". Kein neuer Funktionsumfang.

#### Was sich für dich ändert

- **Anschaffungs- und Stilllegungsdatum greifen jetzt überall in den Auswertungen.** Wer für eine Investition (z. B. Wärmepumpe, Speicher, Wallbox) ein Anschaffungsdatum hinterlegt hat, sah trotzdem in einigen Auswertungs-Ansichten Werte aus Monaten *vor* der Anschaffung — typischerweise wegen versehentlich erfasster Vor-Anschaffungs-Sensordaten. Der Filter wirkt jetzt einheitlich über 13 Read-Sites (Cockpit-Übersicht, Komponenten-Tab, Aktueller Monat, Aussichten, Investitionen-Dashboards, Aggregierte Monatsdaten, HA-Sensor-Export, PDF-Jahresbericht, PV-Strings, Nachhaltigkeit, Sozial-Bilanz). Außerdem unterscheidet die API jetzt sauber zwischen `0` (Komponente aktiv, Wert echt 0 — z. B. Wärmepumpe im Sommer) und `—` (Komponente in dem Monat nicht aktiv). Bonus: die JAZ-Kachel im Wärmepumpen-Dashboard zeigt jetzt den tatsächlichen WP-Datenbereich („2025-2026") statt den Anlagen-weiten Zeitraum. *(detLAN, Issue #236.)*
- **Live-Heute zeigt korrekte Werte, wenn dein Energiezähler in Wh meldet.** Wer einen Energiesensor mit Einheit `Wh` statt `kWh` gemappt hatte, sah heute morgen in den Live-Heute-Kacheln Werte mit Faktor 1000 zu hoch (z. B. 87.000 statt 87 kWh) — der Wh→kWh-Konverter fehlte in einem Statistics-Pfad. Behoben — der gleiche `_is_energy_sensor`-Check, der schon im Sensor-Mapping-Wizard und im Live-Pfad greift, ist jetzt auch im Statistics-Fallback aktiv. *(NongJoWo, Issue #232.)*
- **Wallbox + E-Auto: keine Doppelzählung mehr in Auswertungen → Komponenten.** Wenn du eine Wallbox und ein E-Auto unabhängig in eedc führst und beide denselben Stromfluss aus unterschiedlichen Perspektiven messen (Loadpoint-Seite + Vehicle-Seite), wurden die Werte bisher in „Auswertungen → Komponenten" addiert — PV-Anteil konnte > 100 % anzeigen. Backend führt jetzt eine Max-Pool-Logik pro Monat (analog zu „Aktueller Monat") — die größere Quelle gewinnt, Dienstwagen werden ohnehin ausgeschlossen. Km und V2H bleiben vom E-Auto, Wallbox kennt das nicht. *(NongJoWo, Issue #231.)*
- **Reparatur-Werkbank: „Plan erstellen" verschwindet nicht mehr nach erfolgreichem Lauf.** Nach einem Tag- oder Range-Lauf wurden die Steuerelemente in der Werkbank weiter ausgeblendet — neuer Plan war nur mit Modal-Schließen-Öffnen erreichbar. Der UI-State setzt sich jetzt nach Abschluss eines Laufs sauber zurück. *(detLAN, Issues #234 + #235.)*
- **„Eigene Dateien" — Vorschau zeigt die automatisch erkannten Investitions-Spalten als Tabellen-Spalten.** Wer eine CSV mit ausschließlich Investitions-Spalten (z. B. nur E-Auto-Ladewerte) importieren wollte, sah in der Vorschau eine Tabelle voller „—" — die Spalten wurden korrekt erkannt, aber die Werte tauchten in der Vorschau-Tabelle nicht auf, sondern erst nach dem eigentlichen Import. Jetzt rendert die Tabelle die Investitions-Spalten zusätzlich zu den fünf Standard-Spalten dynamisch — der „nicht sichtbar"-Banner-Text entfällt. *(NongJoWo, Issue #222.)*

#### Was sich *nicht* ändert

- **Reine Reparatur-/Polish-Welle.** Keine neuen Konzepte, keine Schema-Updates über das `AggregierteMonatsdatenResponse`-Nullable hinaus.
- **Bestehende Workflows bleiben gleich.** Wer keinen der genannten Pfade nutzt, merkt nichts vom Release.
- **Vollbackfill bleibt additiv** (siehe v3.25.3) — kein Massenheiler-Knopf hier dazugekommen.

---

## v3.28.x — Mehrere Tage neu aggregieren (Mai 2026)

### Reparatur-Werkbank: Zeitbereich-Reaggregation *(v3.28.0)*

> 🪛 **Neue Reparatur-Operation für mehrere Tage am Stück.** Bisher konnte die Reparatur-Werkbank Tagesprofile nur Tag für Tag neu aggregieren — für einen größeren Zeitraum hieß das viele Einzelklicks. Jetzt gibt es eine Mehrere-Tage-Variante mit Datums-Bereich und Pflicht-Bestätigung, weil pauschale Reparatur-Knöpfe mit Datenverlust-Risiken einhergehen können und das transparent kommuniziert werden soll. Auslöser war Martins Anregung in #230.

#### Was sich für dich ändert

- **Neue Operation „Mehrere Tage neu aggregieren" in der Reparatur-Werkbank.** Du wählst Start- und Enddatum (max. 31 Tage pro Lauf), entscheidest ob Snapshots pro Tag frisch aus HA-Statistics gezogen werden sollen (Default an), und haakst die Pflicht-Bestätigung. Die Operation läuft seriell pro Tag — bei Abbruch (Netz, Browser zu, Worker-Restart) sind die bereits verarbeiteten Tage drin, der Rest unverändert.
- **31 Tage als Maximum pro Lauf** — bewusst eng gesetzt: ein längerer Lauf wäre Black-Box-Verhalten ohne Zwischen-Feedback, ein Abbruch in Stunde 5 weniger ärgerlich als in Stunde 1. Für größere Zeiträume (z. B. komplettes Vorjahr) einfach mehrere 31-Tage-Schübe hintereinander.
- **Prognosen und Korrekturprofil-Daten bleiben erhalten.** Pro Tag rettet der Mechanismus die PV-Prognose, SFML-Prognose, Solcast-Prognose und die gefrorenen Day-Ahead-Stundenprofile (die seit v3.26.0 die Datenbasis für das Korrekturprofil-Lernen sind) — sie werden nach der Neu-Aggregation zurückgeschrieben. Diese Werte stammen aus Live-Endpoints und wären sonst nicht rekonstruierbar.
- **Explizite Bestätigung „ohne Support-Anspruch".** Vor dem Plan-Erstellen muss eine Pflicht-Checkbox angehakt werden: Per-Feld-Provenance älterer Verfahrensläufe wird überschrieben, MQTT-Only-Felder und Strompreis-Sensor-Werte ohne HA-LTS-Pendant gehen verloren falls vorhanden. Wir wollen, dass dieser Knopf bewusst gedrückt wird, nicht versehentlich.

#### Was sich *nicht* ändert

- **Bestehendes „Tag neu aggregieren" bleibt unverändert.** Der Einzeltag-Pfad ist weiterhin der konservative Default für punktuelle Reparatur.
- **Vollbackfill bleibt strikt additiv** (siehe v3.25.3). Bereits vorhandene Tage rührt er nicht an — wer einen Tag *überschreiben* will, nutzt den neuen Mehrere-Tage-Pfad.
- **Kein automatisches Pauschal-Heilen.** eedc bietet weiterhin keine „heile alles"-Funktion an — die neue Operation ist Power-User-Werkzeug mit klarer Auswirkung auf einen begrenzten Zeitraum, nicht der Universal-Reset-Knopf.

---

## v3.27.x — Reparatur-Werkbank und Daten-Schutz (Mai 2026)

### UX-Konsistenz-Cluster + PV-Ertrag-Spalte *(v3.27.5)*

> 🪛 **Anwender-gemeldete UX-Verbesserungen aus dem detLAN-Cluster** plus eine Spalten-Erweiterung von dietmar1968. Kein neuer Funktionsumfang — fünf koordinierte Detail-Verbesserungen, die in Summe die Konsistenz spürbar anziehen.

#### Was sich für dich ändert

- **„PV-Ertrag" als neue Spalte in „Auswertungen → Energieprofil → Tagesübersicht".** Tages-Summe der PV-Erzeugung über alle Anlagen-Komponenten (PV-Module + Balkonkraftwerk), default eingeblendet wie die anderen Tages-Summen-Spalten (Überschuss/Defizit). Wer den Spalten-Selektor angepasst hatte, bekommt die neue Spalte automatisch dazu — die eigenen Anpassungen bleiben erhalten. *(Dank an dietmar1968.)*
- **Live-Ansicht: zwei Animationen weg.** Der pulsierende grüne Punkt links und der Refresh-Spinner rechts im Live-Header machten auf schmalen Fenstern unruhige Layout-Sprünge — der Update-Timestamp zeigt eh, wann zuletzt aktualisiert wurde. Statischer Live-Punkt bleibt als Online-Indikator, jetzt neben der Update-Zeile statt auf der anderen Seite. *(Mehrere Tester hatten das in unterschiedlichen Worten gemeldet — Rainer per PN, dietmar1968 im Forum, detLAN als GitHub-Issue.)*
- **Überflüssige Überschriften in Einstellungen entfernt.** „Anlagen", „Strompreise", „Investitionen", „Sensor-Zuordnung", „HA-Statistik Import" und „HA-Sensor-Export" wiederholten den Sub-Tab-Namen direkt darunter — überall weg, der Sub-Tab benennt den Bereich. Bei MQTT-Export war die alte Überschrift „HA-Sensor-Export" zudem irreführend (Sub-Tab heißt „MQTT-Export"); die Info-Box darunter erklärt das schon. Plus: Sub-Tab Singular „Anlage" heißt jetzt korrekt „Anlagen". *(detLAN.)*
- **Vier Aktualisieren-Buttons als Schaltfläche statt nackter Icon.** In Solarprognose-Setup, Daten-Checker, MQTT-Export und System-Einstellungen ist der Refresh-Knopf jetzt ein vollwertiger grauer Button mit Icon + „Aktualisieren"-Label — konsistent zu „+ Neue Anlage", „+ Neuer Tarif" etc., nicht mehr fünf verschiedene Stile in einer App. *(detLAN.)*
- **Komponenten-Reihenfolge in Community vereinheitlicht.** An vier Stellen (Community → Statistiken Ausstattung + Quoten-Cards, Community → Übersicht Komponenten-Benchmarks, Community → Komponenten Deep-Dives) war die Reihenfolge teils Wallbox-vor-E-Auto, teils E-Auto-vor-Wallbox, und Balkonkraftwerk landete oft ans Ende. Jetzt überall einheitlich: Speicher → Balkonkraftwerk → Wärmepumpe → Wallbox → E-Auto (eedc-Standard-Sortierung). *(detLAN.)*

#### Was sich *nicht* ändert

- **Keine funktionalen Änderungen, keine Schema-Updates, keine Konzept-Etappe.** Wer keine der genannten Ansichten regelmäßig nutzt, merkt nichts vom Release.

---

### Wärmepumpen-Aggregation für getrennte Strommessung *(v3.27.4)*

> 🪛 **Zwei strukturelle Lücken im Wärmepumpen-Stundenpfad behoben**, beide aus Martins Forum-Befund.

#### Was sich für dich ändert

- **Wärmepumpe-Spalte in der Stundenwerte-Tabelle wird befüllt, wenn du Strom Heizen und Strom Warmwasser getrennt erfasst.** Wer im Sensor-Mapping die seit v3.25.x verfügbare Option "Getrennte Strommessung" gewählt hat und zwei Stromsensoren für Heizung und Warmwasser gemappt hatte, sah im Live-Tagesverlauf eine korrekte WP-Kurve, aber in „Auswertungen → Energieprofil → Tagesdetail" blieb die Wärmepumpe-Spalte leer und die Heatmap zeigte für die WP nichts. Der stündliche Snapshot-Mechanismus kannte die getrennten Feldnamen nicht und hat sie ignoriert. Behoben — beide Felder werden jetzt regulär stündlich aufgezeichnet und in der Stundenwerte-Tabelle als Wärmepumpen-Verbrauch summiert. **Damit Bestandstage rückwirkend korrekt erscheinen, einmal über Auswertungen → Energieprofil → Datenverwaltung → "Vollbackfill" laufen lassen**: HA-Statistics hat die Historie, eedc holt die fehlenden Snapshots nach.
- **WP-Kompressor-Starts: kein einzelner Unsinns-Wert mehr in der Stunden-Detail-Tabelle.** Wenn der Tagestab 0 WP-Starts für einen Tag zeigt, aber die Stunden-Detail-Tabelle in einer einzelnen Stunde dann z. B. 49.073 stehen hat, ist das kein realer Wert sondern ein bekannter HA-Statistics-Bug (`sum=NULL` direkt nach HA-Restart, der `state`-Fallback liefert den Lebensdauer-Zählerstand). eedc filtert solche Spikes jetzt im Stunden-Pfad heraus (Plausibilitäts-Schwelle: > 200 Starts/h sind physikalisch ausgeschlossen). Sobald du den Tag über die Reparatur-Werkbank reaggregierst, ist die Anzeige bereinigt. *(Dank an MartyBr für die scharfe Beobachtung mit Screenshots.)*

#### Was sich *nicht* ändert

- **Reines Aggregations-Fix.** Keine neuen Funktionen, keine Schema-Änderungen. Wer keine getrennte Strommessung für die WP nutzt und auch sonst keine WP-Starts-Anomalien gesehen hat, merkt nichts vom Release.

---

### Folge-Päckchen Tester-Bugs *(v3.27.3)*

> 🪛 **Reaktion auf v3.27.2-Feedback + drei frische Bug-Meldungen.** Rainer und NongJoWo hatten gemeldet, dass die v3.27.2-Fixes ihre Probleme nicht gelöst hatten — diesmal mit Backend-Logs bzw. Datei-Anhang, sodass die tatsächlichen Pfade gefunden werden konnten. Plus drei neue Issues von JanKgh und NongJoWo. Alles Polish, kein neuer Funktionsumfang.

#### Was sich für dich ändert

- **CSV-Export funktioniert auch mit Sonderzeichen im Anlagenname.** Wer als Browser-Fehler "Failed to fetch" gesehen hat, obwohl der Server in den Logs ein sauberes HTTP 200 OK zeigte, hatte vermutlich Leerzeichen, Umlaute oder andere Sonderzeichen im Anlagenname — die landeten ungefiltert in einem HTTP-Header und der Browser-Fetch hat den Stream als ungültig abgebrochen. Backend sanitisiert den Namen jetzt vor dem Header (Umlaute → ae/oe/ue, Sonderzeichen → _) und quotet den Filename korrekt. *(Dank an rapahl für die ausführlichen Backend-Logs.)*
- **"Eigene Dateien" — Vorschau erkennt automatisch zugeordnete Investitions-Spalten.** Bisher meldete die Vorschau "Keine gültigen Monatsdaten", wenn deine CSV-Datei nur Jahr/Monat plus Spalten enthielt, die eedc automatisch einer E-Auto- oder Wallbox-Investition zuordnen würde (Suffix-Match auf den csv_suffix in den Felddefinitionen). Beim eigentlichen Import hätten sie sauber gelandet — die Vorschau wusste nur nichts davon. Jetzt prüft sie die gleiche Auto-Erkennung wie der Apply-Pfad und zeigt einen klaren Hinweis "X Investitions-Spalten automatisch erkannt". *(Dank an NongJoWo mit Test-CSV.)*
- **Datenchecker mahnt keine Batterie-Daten für Monate vor der Batterie-Installation an.** Wer eine PV-Anlage vor der Batterie hatte (typisch: PV 2021, Speicher 2022 oder später) bekam für jeden Vor-Anschaffungs-Monat eine Warnung "Batterie-Ladung nicht erfasst" — was per Definition nicht erfasst werden konnte. Der Datenchecker respektiert jetzt Anschaffungs- und Stilllegungsdatum pro Speicher. *(Dank an JanKgh.)*
- **Tagesverlaufsgrafik addiert Wallbox und E-Auto nicht mehr doppelt.** Wenn deine Wallbox und das E-Auto unabhängig in eedc angelegt sind und beide denselben Leistungs-Sensor nutzen (typisch bei "Wallbox misst Ladung am Stecker, E-Auto-App misst die gleiche Leistung von der anderen Seite"), wurden bisher beide getrennt im Tagesverlauf gestackt — Σ Verbrauch um die Fahrzeug-Ladung zu hoch. Backend dedupliziert jetzt automatisch: wenn zwei Investitionen dieselbe Entity teilen, wird die Wallbox bevorzugt, das E-Auto entfällt. Sauberer Weg bleibt: Fahrzeug-Investition öffnen → "Gehört zu Wallbox" → Wallbox auswählen — damit der bestehende parent-basierte Schutz greift. *(Dank an JanKgh mit Tooltip-Screenshot.)*
- **Vollzyklen pro Monat zeigt wieder einen runden Wert.** Im Cockpit → Speicher → "Vollzyklen pro Monat"-Diagramm zeigte der Tooltip Werte wie "10.5252891704708..." statt "10,5". Ein Edge-Case in der Tooltip-Komponente hat die Nachkommastellen-Vorgabe verschluckt, sobald keine Einheit dabei war. Behoben. Bonus: deutsches Komma-Trennzeichen wird in Chart-Tooltips jetzt durchgängig verwendet, auch wenn die Zahl ohne Einheit angezeigt wird. *(Dank an NongJoWo.)*

#### Was sich *nicht* ändert

- **Keine Funktionen verändert.** Reines Bugfix-Päckchen ohne neue Konzepte oder Architektur-Etappen.

---

### Tester-Bugfix-Päckchen *(v3.27.2)*

> 🪛 **Drei Anwender-gemeldete Bugs hintereinander erledigt.** Patch-Päckchen ohne neue Funktionen — repariert nur, was eine kaputte oder irreführende Anzeige produziert hat.

#### Was sich für dich ändert

- **Der „Daten exportieren"-Button funktioniert wieder.** Wer als Browser-Fehler „Failed to fetch" beim CSV-Export gesehen hat, war von einem stillen Backend-Crash betroffen: Sonderkosten oder sonstige Positionen, die irgendwann mal als Text (z. B. `"150,00"` mit Komma) statt als Zahl gespeichert wurden, haben den Export-Endpoint abrupt abbrechen lassen. Der Export verträgt jetzt sowohl klassische Zahlen als auch Komma-Schreibweise und fällt im Zweifel sicher auf 0 zurück, statt komplett zu kippen. *(Dank an rapahl für die scharfe Bug-Beschreibung mit Screenshot.)*
- **„Eigene Dateien" — Import-Vorschau mit klarerer Fehlermeldung und ohne Falsch-Alarm.** Wer im Mapping-Wizard E-Auto- oder Wallbox-spezifische Slots manuell zugeordnet hat (die sonst automatisch erkannt werden), bekam bisher die unverständliche Meldung „Keine gültigen Monatsdaten mit diesem Mapping gefunden". Die Vorschau akzeptiert diese Doppel-Zuordnung jetzt und sagt dir transparent: „X Spalte(n) als Investitions-Daten gemappt — werden beim Import automatisch zugeordnet". Falls es doch ein echtes Format-Problem ist (Datums-Format wird nicht erkannt oder Punkt/Komma vertauscht), nennt die Meldung die konkrete Verdachtsursache statt nur „prüfe Jahr/Monat". *(Dank an NongJoWo für das ausführliche Issue.)*
- **Monatsbericht → Finanzen: PV-Eigenverbrauch-Ersparnis ohne Doppelzählung der Wallbox-PV-Ladung.** Im T-Konto war der Posten „PV-Eigenverbrauch-Ersparnis" bisher zu hoch, weil die Wallbox-PV-Ladung sowohl dort als auch separat im Posten „Wallbox — PV-Ladung-Ersparnis" gerechnet wurde. Σ Haben war damit um diesen Betrag überhöht und das Monatsergebnis entsprechend zu optimistisch. Bei einer 150-kWh-Wallbox-PV-Ladung typische Korrektur ≈ 45 €/Monat nach unten. *(Dank an NongJoWo für den Hinweis mit Tooltip-Vergleich — ohne den wäre der Bug wahrscheinlich noch lange unter dem Radar geblieben.)*

#### Was sich *nicht* ändert

- **Keine Funktionen verändert.** Wer den Export nicht nutzt, kein Custom-Import macht und in den Monatsberichten keine Wallbox-PV-Ladung pflegt, merkt nichts vom Release.

---

### UX-Sprint und Power-Sensor-Bug *(v3.27.1)*

> 🪛 **Bugfix-Release zwischen den Etappen.** Bündelt UX-Quick-Wins aus dem detLAN-Cluster (Tab-Style einheitlich als Schaltfläche, kompakteres Cockpit-Banner, konsistente Komponenten-Reihenfolge mit Wärmepumpe vor Wallbox) und einen Datenintegritäts-Bug, den rcmcronny gemeldet hatte: Leistungs-Sensoren ließen sich versehentlich als kWh-Tageswert eintragen — die Live-Heute-Anzeige zeigte dann mal 0, mal 1000+ kWh.

#### Was sich für dich ändert

- **Power-Sensor schützt sich jetzt selbst.** Wer im Sensor-Mapping einen Leistungs-Sensor (Einheit W/kW) versehentlich in einen kWh-Slot wie „Netzbezug Tageswert" einträgt, bekommt im Wizard direkt eine Warnung „Einheit XXX passt nicht in einen kWh-Slot" mit Wegweiser auf den richtigen Slot („Live-Sensoren / Aktuelle Leistung"). Falls der Sensor schon eingetragen war: der Live-Heute-Pfad ignoriert ihn jetzt für die Tagessumme und rechnet stattdessen aus dem Wattverlauf — physikalisch korrekt. Vorher kam es bei dieser Konstellation zu unsinnigen Werten.
- **Tab-Leisten in Auswertungen, Aussichten, Community jetzt als Schaltflächen** statt Unterstrich. Konsistenter Look mit dem Sensor-Mapping-Wizard und der Cockpit-Sub-Navigation. Aktiver Tab in Akzentfarbe, inaktive in dezentem Grau — leichter erfassbar, gerade auf kleinen Bildschirmen.
- **Cockpit Top-Banner kompakter.** Das große Home-Icon ist weg, Anlagenname und kWp stehen jetzt inline statt zweizeilig. Das nutzlose Calendar-Icon vor dem Jahres-Filter ist auch weg — es war nicht klickbar (im Gegensatz zum Share-Button daneben), das war verwirrend.
- **Daten → Monatsdaten ohne Überschrift, Selektoren in einer Zeile.** Die „Monatsdaten"-Überschrift wiederholte den Hauptmenü-Titel — weg. Anlage-Selektor verschwindet automatisch, wenn du nur eine Anlage hast. Mehr Platz für die eigentlichen Daten.
- **„Erstellt mit eedc" jetzt auch in der kompakten Share-Variante.** Bisher war der Hinweis nur im ausführlichen Teilen-Text — jetzt konsistent in beiden, am Ende des Texts.
- **Wallbox vor E-Auto** in der Community-Übersicht („Stärken/Schwächen"-Reihen + Komponenten-Tab + Empty-State). Spiegelt den Anwender-Workflow: Ladeinfrastruktur vor Fahrzeug.
- **Wärmepumpe vor Wallbox** im Daten-Checker. Die Anomalie-Liste pro Komponente folgt jetzt einer einheitlichen Reihenfolge (Wechselrichter → PV-Module → Speicher → Balkonkraftwerk → Wärmepumpe → Wallbox → E-Auto → Sonstiges) statt der zufälligen DB-Reihenfolge.
- **Jahresübersicht in Community → PV-Ertrag absteigend** (neueste oben).
- **Wallbox-Card im Dark Mode hat wieder einen sichtbaren Rahmen.** Bei der Komponenten-Übersicht in Community → Statistiken war die Wallbox-Card im dunklen Modus rahmenlos (CSS-Build-Falle); jetzt sauber mit Cyan-Akzent wie die anderen Cards.
- **Performance-Profil Radar-Chart: Community-Linie jetzt in Amber statt Grau.** Die alte graue Linie verschmolz mit den grauen Gitterlinien des Charts — jetzt klar erkennbar.
- **Plural-Bug „1 Hinweise" / „1 Warnungen" gefixt.** Steht jetzt korrekt „1 Hinweis" / „1 Warnung".
- **Übernehmen-Knopf im Monatsabschluss-Wizard rückt neben das Eingabefeld** statt darüber — die Spinner-Pfeile am Number-Input sind dadurch nicht mehr verdeckt.
- **Doppeltes Info-Icon in Aussichten → Prognosen** entfernt.
- **Auto-Fill für die Ø-Außentemperatur im Monatsabschluss-Wizard.** Wenn das Feld leer ist und die Wetter-Daten verfügbar sind (Bright Sky oder Open-Meteo Archive), füllt eedc den Wert direkt vor — du musst ihn nur prüfen oder bewusst überschreiben.

#### Was sich *nicht* ändert

- **Funktionsumfang bleibt identisch.** Es ist ein Bugfix- und UX-Polish-Release — keine neue Architektur-Etappe, keine neuen Konzepte. Was du bisher gewohnt bist, funktioniert weiter wie zuvor.

→ [Auswertung → Energieprofil](HANDBUCH_BEDIENUNG.md#42-auswertung) · [Cockpit](HANDBUCH_BEDIENUNG.md#41-cockpit)

---

### Daten-Provenance & Reparatur-Werkbank *(v3.27.0)*

> 🛠 **Architektur-Etappe 3d sichtbar als zwei neue Anwender-Funktionen:** eine zentrale Reparatur-Werkbank ersetzt die verstreuten Schnellbuttons, und manuell gepflegte Werte werden jetzt automatisch vor Cloud-/Portal-Import geschützt. Dazu wurde unter der Haube eine Quellen-Hierarchie eingeführt, die jeder Schreiber respektieren muss — keine stillen Überschreibungen mehr.

#### Was sich für dich ändert

- **Reparatur-Werkbank** im Energieprofil unter „Datenverwaltung". Du wählst eine Operation (z. B. *Heute neu aggregieren*, *Vollbackfill*, *Cloud-Import-Werte zurücksetzen*) und siehst **vor** dem Klick auf „Anwenden" eine Vorschau-Tabelle mit jeder Feld-Änderung — gruppiert pro Datensatz, mit Sticky-Header. Erst der Bestätigungs-Knopf „N Änderungen anwenden" schreibt etwas. Der Vorgang lässt sich nach 30 Sekunden über einen Cancel-Knopf abbrechen, das Verlauf-Akkordeon zeigt, was du bisher angewendet hast inklusive Audit-Log-Counter. Die alten Schnellbuttons (Aggregat heute / Vollbackfill / etc.) bleiben als Wrapper bestehen — wer sie gewohnt ist, drückt sie einfach weiter.
- **Manuell gepflegte Werte überleben Cloud- oder Portal-Import.** Wer einen Wert im Monatsabschluss-Wizard eingetragen oder per CSV-Backup wiederhergestellt hat, war bisher der Willkür des nächsten Cloud-Apply ausgeliefert: ein „Überschreiben"-Klick im Wizard zog auch manuell gepflegte Werte mit. Ab v3.27.0 schützt eine Quellen-Hierarchie die manuellen Werte automatisch — der Cloud-Apply gibt anschließend zurück „X Felder durch manuelle Werte geschützt — Reset über Reparatur-Werkbank wenn gewollt". Du siehst also explizit, was nicht überschrieben wurde, und kannst es bewusst über die Reparatur-Werkbank zurücknehmen, falls du den Cloud-Wert doch willst.
- **Daten-Checker zeigt Provenance-Konflikte.** Wenn ein Cloud-Import versucht hätte, einen manuellen Wert zu überschreiben, und das blockiert wurde, taucht das in der Anlagen-Diagnose als neuer Befund `PROVENANCE_CONFLICT` auf. Hilft, Drift zwischen Cloud-Quelle und manueller Pflege zu sehen, bevor sie zu einer Vertrauensfrage wird.
- **Pool-Doppelzählung bei E-Auto + Wallbox im Cockpit + Monatsbericht weg.** Wer 1 E-Auto + 1 Wallbox erfasst hatte, sah teils E-Mob-PV-Anteil > 100 % (mathematisch unmöglich, aber Folge davon dass Vehicle und Loadpoint denselben Stromfluss aus zwei Perspektiven messen). Saubere Trennung pro Fahrzeug folgt erst mit Phase 2 des Wallbox/E-Auto-Konzepts (eigene Vehicle-Sensor-Zuordnung).

#### Was sich *nicht* ändert

- **Tagesgesamt-Werte und Heatmaps bleiben unverändert.** Die Etappe ist eine Architektur-Konsolidierung der Schreib-Pfade — sie aggregiert nicht neu und verwirft nichts. Nur die Schreib-Reihenfolge bei mehreren Quellen pro Feld ist jetzt explizit geregelt.
- **Manuelle Eingabe geht weiter wie bisher.** Du musst keine Reparatur-Werkbank öffnen, um einen Wert einzugeben — der Monatsabschluss-Wizard und das direkte Bearbeiten in der Anlagen-Sicht bleiben unverändert.
- **Bestandsdaten gehen nicht verloren.** Beim ersten App-Start nach Update werden vorhandene Werte einmalig als Quelle „Legacy unbekannt" markiert. Sie bleiben sichtbar und nutzbar; jeder neue Schreiber gewinnt automatisch gegen sie.
- **Cloud-Import-Buttons bleiben sichtbar und nutzbar.** Sie laden weiter Werte — die Hierarchie greift nur, wenn du an derselben Stelle bereits einen manuellen Wert hast. Bei leeren Feldern landet der Cloud-Wert wie zuvor direkt.

→ [Auswertung → Energieprofil → Datenverwaltung](HANDBUCH_BEDIENUNG.md#42-auswertung)

---

## v3.26.x — Wetter-Stratifizierung und Lernfaktor-Diagnose (Mai 2026)

### Architektur-Konsolidierung Etappe 3c — Konsistenz-Fixes unter der Haube *(v3.26.8)*

> 🧱 **Architektur-Etappe sichtbar nur als saubereres Verhalten.** Vier strukturelle Aufräum-Päckchen am Energieprofil-Datenpfad: Slot-Ausrichtung, Tagessumme HA-konform, Snapshot-Herkunft trackbar, Reaggregat-Modal mit klar getrennten Aktionen. Kein neuer Knopf, keine neuen Konzepte — die Selbst-Heilung aus v3.26.6 ist jetzt strukturell abgesichert statt heuristisch.

#### Was sich für dich ändert

- **WP-Kompressor-Starts-Heatmap wandert beim ersten Start um eine Stunde nach rechts — das ist Absicht, kein Bug.** Wer WP-Kompressor-Starts erfasst (seit v3.24.0 möglich), wird nach dem Update einmalig sehen, dass die gewohnte Stundenverteilung in der Heatmap um eine Spalte verschoben ist. Was vorher in Stunde 6 stand (Aktivität *zwischen* 06:00–07:00), steht ab jetzt in Stunde 7 — derselbe Wert, andere Spalte. Die Verschiebung gleicht den Counter-Pfad an die kWh-Heatmap an, die schon seit v3.20.0 die HA-übliche Backward-Konvention nutzt (Slot N = Aktivität *zwischen* (N−1):00 und N:00, [#144](https://github.com/supernova1963/eedc-homeassistant/issues/144)). Vorher waren beide Heatmaps eine Stunde gegeneinander verschoben — jetzt symmetrisch. **Tagessumme der Kompressor-Starts ändert sich nicht.** Die Migration läuft beim ersten App-Start einmalig und automatisch (idempotent über interne `migrations`-Tabelle), keine User-Aktion nötig.
- **eedc-Tagessummen für Komponenten-Energien entsprechen ab jetzt exakt dem HA Energy Dashboard.** Für Wallbox / WP / BKW / E-Auto / Speicher wird die Tageszahl ab jetzt aus Tagesanfang/Tagesende-Zählerdiff gerechnet — derselbe Pfad, den auch HA selbst nutzt. Bei normalen Anlagen ohne Sensor-Lücken praktisch identisch zur alten Stundensummen-Variante; bei Anlagen mit Sensor-Resets oder Spike-Korrekturen kann es geringfügig anders aussehen — und genau dort ist der neue Wert der konsistente. Greift für *neue* Aggregate (heute und morgen); historische Tagessummen bleiben unverändert, können aber bei Bedarf über den Reaggregate-Knopf pro Tag nachgezogen werden.
- **Reaggregate-Modal mit zwei klaren Aktions-Buttons.** Statt einem „Übernehmen"-Knopf zeigt das Vorschau-Modal jetzt *Snapshots neu holen + Tagesaggregat rechnen* (vollständiger Resnap) und *Nur neu rechnen* (wenn die Snapshots längst stimmen). Die Auto-Erkennung aus v3.26.6 macht den Default-Knopf vor — du kannst aber jetzt explizit überschreiben (z. B. nach Sensor-Tausch, wenn Snapshots ungeprüft erscheinen). Cancel-Knopf erscheint, wenn der Resnap länger als 30 Sekunden braucht.
- **Vorbereitung Daten-Herkunft sichtbar machen** (Schablone für Etappe 3d). Jeder gespeicherte Sensor-Schnappschuss trägt ab jetzt einen Quelle-Marker (HA-Statistics / MQTT-Inbound / MQTT-Live / Live-Fallback / Unknown für historische Snapshots). Sichtbar wird das später in der Datenverwaltungs-Seite — als Vorlage für Konflikt-Auflösung zwischen Cloud-Import, manueller Eingabe und Auto-Aggregation in Etappe 3d.

#### Was sich *nicht* ändert

- **Tagessumme der Kompressor-Starts bleibt unverändert** — die kommt aus einem eigenen Pfad, der schon vorher korrekt war (Tagesanfang/Tagesende-Counter-Diff). Nur die Stundenverteilung in der Heatmap wandert um eine Spalte.
- **Werte gehen nicht verloren.** Slot-Wert-Anzahl bleibt gleich; an Stellen, wo bei der neuen Konvention ein Snapshot-Boundary fehlt, wird ein Slot leer — an genau einer anderen Stelle als vorher (NULL-Slots wandern mit, die Anzahl bleibt).
- **Historische komponenten_kwh-Tagessummen werden nicht stillschweigend umgeschrieben.** Der Reaggregate-Knopf pro Tag liefert auf Wunsch den HA-konformen Boundary-Diff-Wert.
- **Resnap-Backend war seit v3.26.6 schon da.** Was neu ist, ist die UX-Trennung im Frontend — die `mit_resnap=true/false`-Auswahl gab es serverseitig schon.

→ [Auswertung → Energieprofil](HANDBUCH_BEDIENUNG.md#42-auswertung)

### UX-Bündel aus Forum-Beobachtungen *(v3.26.7)*

> ✨ **Vier kleine UX-Verbesserungen aus aktiven Tester-Anfragen, in einem Patch zusammengefasst.**
>
> - **Live-Heute Batterie-Pfeile** zeigen jetzt in dieselbe Richtung wie das HA Energy Dashboard: ▼ wenn Strom in den Speicher rein, ▲ wenn raus. Vorher umgekehrt (Tank-Metapher), das hat verwirrt. (#201)
> - **Schreibweise „eedc" durchgängig** (statt gemischt eedc/eedc), und **„Home Assistant Add-on" → „Home Assistant App"**, wo es um eedc selbst geht. HA-eigene Menü-Pfade („Einstellungen → Add-ons → ⋮") bleiben natürlich — das heißt in HA wirklich so. (#199)
> - **Redundante Seitentitel entfernt** im Cockpit, in Auswertungen, Aussichten, Live-Daten, Community-Vergleich und mehreren Einstellungs-Seiten. Da die Top-/Sub-Navigation immer sichtbar ist, war die zusätzliche `<h1>` direkt darunter eine reine Doppelung. Pages mit dynamischem Untertitel (Anlagenname etc.) bleiben unverändert. (#196)
>
> Alle drei UX-Punkte kommen aus detLAN-Feedback. Auch Ronnys gemeldete „Live-Netzbezug zu hoch"-Anomalie (#200) ist code-seitig bereits seit v3.26.6 gefixt — die Verifikation läuft.

### Hotfix: Wetter-Backfill schließt jetzt auch die letzten 5 Tage *(v3.26.4)*

> 🩹 **Hotfix wenige Stunden nach v3.26.3** — der „Wetter-Historie nachladen"-Button hat die letzten 5 Tage strukturell ausgelassen, weil Open-Meteo Archive sie wegen 2–5 Tage Reanalyse-Lag nicht hat. Per Designkommentar sollten diese Tage über den Live-Forecast-Pfad mitkommen, taten es aber nicht — also blieb die „5 Tage noch nicht geladen"-Meldung dauerhaft sichtbar und ein erneuter Klick lieferte „0 Stunden / 0 Tage geladen". Verständlich verwirrend.
>
> Jetzt holt der Backfill zwei Range-Calls: Open-Meteo Archive für ältere Tage, Open-Meteo Forecast (mit Reanalyse-Approximation für die Vergangenheit) für die jüngsten Tage. Der nächtliche Tagesabschluss-Aggregator (`aggregate_day`) verwendet denselben Routing-Cutoff. Damit ist die Lücke der letzten 5 Tage strukturell geschlossen — Empty-State-Ghost und „0 geladen" sollten nach einem Klick verschwinden.

→ [Aussichten → Prognosen-Vergleich](HANDBUCH_BEDIENUNG.md#43-aussichten)

### Hotfix: Korrekturprofil-Skalar wirkt sofort, auch ohne Stundenprofile *(v3.26.3)*

> 🩹 **Hotfix wenige Stunden nach v3.26.2** — der Aggregator hat „Keine Day-Ahead-Snapshots im Zeitraum" zurückgemeldet, sobald das stündliche Day-Ahead-Profil (`pv_prognose_stundenprofil`, erst seit v3.26.0 mitgeschrieben) im Auswertungsfenster noch leer war. Bestehende Anlagen haben Tages-Prognose schon seit Monaten — die Skalar-Stufe hätte ab Tag 1 verfügbar sein müssen, war aber wegen meiner zu strikten Voraussetzung gesperrt. Damit fiel der Live-Pfad weiter auf den Legacy-Lernfaktor zurück, statt auf das neue Korrekturprofil.
>
> Jetzt schreibt der Aggregator den Skalar unabhängig vom Stundenprofil; Sonnenstand- und Wetter-Bins bleiben leer, solange die Stundenprofile reinwachsen — und füllen sich automatisch über die nächsten Wochen. Die Heatmap-Card erklärt das jetzt explizit, wenn nur die Skalar-Stufe vorhanden ist.

→ [Aussichten → Prognosen-Vergleich](HANDBUCH_BEDIENUNG.md#43-aussichten)

### Päckchen 2: Stündliches Korrekturprofil scharf *(v3.26.2)*

> ✨ **Das stündliche Korrekturprofil aus dem Päckchen-1-Konzept ist jetzt produktiv.** Pro Stunde wird die OpenMeteo-Strahlung mit einem Faktor multipliziert, der von Sonnenstand (Azimut × Elevation) *und* Wetterklasse abhängt — also zum Beispiel "Süd-Mittag bei klarem Himmel" anders als "West-Nachmittag bei diffuser Bewölkung". Damit fängt die Live-Prognose Verschattungs- und Wetter-Asymmetrien strukturell ein, die ein einziger Anlagen-Skalar nicht trennen kann.

#### Was sich für dich ändert

- **Live-Strahlung wird pro Stunde individuell korrigiert.** Bisher wurde der Lernfaktor (z. B. ×0.97) gleichmäßig auf alle Stunden multipliziert. Ab v3.26.2 ermittelt eedc für jede Stunde Sonnenstand-Bin (10° × 10°) und Wetterklasse, und greift den Korrekturfaktor aus dem über die Anlage gelernten Profil. Effekt sichtbar im Live-Dashboard und in der Tagesrest-Prognose: Stunden mit Verschattung oder schwacher Wetterleistung kriegen einen passenderen Faktor als Stunden ohne.
- **Heatmap im Prognosen-Vergleich-Tab.** Eine neue Card zeigt das gelernte Korrekturprofil als Tabelle (Azimut horizontal, Elevation vertikal, Farbe = Faktor) — pro Wetterklasse umschaltbar plus Fallback-Sicht ohne Wetter-Achse. Macht sichtbar, welche Sonnenstand-Bereiche bei welcher Wetterlage über- oder unterschätzt werden.
- **Sanftverlauf für neue oder datenarme Anlagen.** Ein Sonnenstand-Bin braucht mindestens 10 Stunden Datenbestand, um produktiv genutzt zu werden (Stufe 1: Sonnenstand × Wetter), bzw. 15 Stunden ohne Wetter-Achse (Stufe 2). Reicht das nicht, fällt eedc automatisch auf den klassischen Skalar-Lernfaktor zurück — neue Anlagen merken zunächst nichts und bauen ihr Profil organisch auf.
- **Nightly Aggregator.** Das Profil wird täglich um 02:30 frisch gerechnet aus Day-Ahead-Snapshots + IST-Stunden + Wetter-Historie. Manuelles "Neu aggregieren" ist über den Button in der Heatmap-Card jederzeit möglich.

#### Was sich *nicht* ändert

- **Solcast-Spalte und alle bisherigen Cards bleiben unverändert.** Die Heatmap kommt additiv unter den vorhandenen Diagnose-Cards.
- **Anlage ohne Day-Ahead-Snapshots oder Koordinaten** → Aggregator wird übersprungen, Live-Pfad bleibt auf dem klassischen Skalar.
- **Tagesrest-Pfad konzeptionell wie bisher:** eedc fragt frische Forecasts und multipliziert mit dem Faktor — neu ist nur, dass der Faktor jetzt pro Stunde aus dem Profil kommt statt einem globalen Skalar.

→ [Aussichten → Prognosen-Vergleich](HANDBUCH_BEDIENUNG.md#43-aussichten)

### Hotfix: Wetter-Backfill-Button erscheint jetzt zuverlässig *(v3.26.1)*

> 🩹 **Hotfix wenige Stunden nach v3.26.0** — der Empty-State mit dem "Wetter-Historie nachladen"-Button blieb auf vielen Anlagen unsichtbar, weil meine ursprüngliche Trigger-Bedingung an einem Datenfeld hing (`pv_prognose_stundenprofil` aka Day-Ahead-Snapshot), das auf länger laufenden Anlagen lückenhaft gefüllt ist. Damit war das Hauptfeature von v3.26.0 für viele praktisch unsichtbar. Jetzt erscheint der Button, sobald irgendwo in den letzten 90 Tagen Stunden ohne Wetter-Daten vorhanden sind — also überall.
>
> Wenn die Stratifizierungs-Tabelle nach dem Backfill leer bleibt, weil noch keine Day-Ahead-Stundenprofile gespeichert sind, sagt das die Card jetzt explizit — die nachgeladenen Wetter-Daten dienen dann als Vorbereitung für Päckchen 2.

→ [Aussichten → Prognosen-Vergleich](HANDBUCH_BEDIENUNG.md#43-aussichten)

### Päckchen 1: Daten-Layer für stündliches Korrekturprofil *(v3.26.0)*

> ✨ **Vorbereitungs-Release für ein stündliches PV-Korrekturprofil mit Verschattungs- *und* Wetter-Dimension.** Päckchen 1 von zwei: legt die Datenbasis an, baut zwei neue Diagnose-Cards im Prognosen-Vergleich-Tab und verbessert die Lernfaktor-Berechnung statistisch — der Live-Pfad selbst bleibt unverändert. Päckchen 2 (das eigentliche stündliche Korrekturprofil mit Anwendung im Live-Dashboard) folgt nach einer Beobachtungs-Phase.

#### Was sich für dich ändert

- **Stündliches Wetter wird ab sofort mitgespeichert.** Bei jedem Tagesabschluss schreibt eedc zusätzlich Bewölkung (%), Niederschlag (mm) und WMO-Wettercode pro Stunde — kommt aus dem Open-Meteo-Aufruf, den eedc für die Strahlungs-Daten ohnehin macht. Kein neuer API-Call, kein Quota-Verbrauch.
- **Wetter-Historie nachladen (manuell anstoßbar).** Open-Meteo Archive bietet 2 Jahre Historie kostenlos. Wer den vollen Diagnose-Wert direkt sehen will, kann die Historie für seine Anlage einmalig nachladen lassen — ein Klick reicht (siehe Stratifizierungs-Card im Prognosen-Tab).
- **Lernfaktor — Doppel-Variante "O1+O2".** eedc rechnet den Anlage-Skalar (Verhältnis IST/Prognose) ab sofort *zusätzlich* mit zwei statistischen Verbesserungen aus: Trim-Mean (entfernt Ausreißer-Tage durch Sensor-Aussetzer) und Recency-Boost (gewichtet die letzten 30 Tage stärker). **Wichtig:** der Live-Pfad nutzt weiter den klassischen Faktor — die neue Variante läuft parallel und ist nur als Diagnose sichtbar. Erst nach mehrwöchiger Beobachtung wird entschieden, ob sie zum Default wird.
- **Zwei neue Cards im Prognosen-Vergleich-Tab.**
  - *Lernfaktor — Doppel-Variante O1+O2:* zeigt Live-Faktor (Legacy) und O1+O2-Faktor nebeneinander mit Δ-Anzeige. Macht sichtbar, ob die statistische Verbesserung stabil zum Legacy-Wert läuft (Δ &lt; 1 %) oder systematisch nach oben/unten zieht.
  - *Wetter-Stratifizierung:* zeigt MAE/MBE der Day-Ahead-Stundenprognose getrennt nach drei Wetter-Klassen — *klar*, *diffus*, *wechselhaft*. Erst dadurch wird sichtbar, ob die Prognose bei klarem Himmel super läuft und nur bei Schauer-Tagen abweicht (oder umgekehrt). Ohne diese Aufschlüsselung war ein einziger gemittelter Tagesfehler die einzige Sicht.

#### Was sich *nicht* ändert

- **Solcast-Spalte und Tab-Inhalte bleiben** — die Diagnose-Cards sind additiv, nichts wird entfernt oder neu sortiert.
- **Tagesrest-Prognose im Live-Dashboard** läuft genauso wie bisher: aktuelle Open-Meteo-Forecast × Lernfaktor (Legacy). Wird nicht durch die neue O12-Variante beeinflusst.
- **Ohne IST-Vergleich keine Stratifizierung.** Die Wetter-Stratifizierungs-Card erscheint erst, wenn eedc genug Tage mit gleichzeitiger Day-Ahead-Prognose und IST-Stundenwerten gefunden hat — typisch wenige Tage nach Aktivierung.

→ [Aussichten → Prognosen-Vergleich](HANDBUCH_BEDIENUNG.md#43-aussichten)

---

## v3.25.x — Investitions-Parameter aufgeräumt (April–Mai 2026)

### Tab-Bildlaufleiste auf drei Seiten weg *(v3.25.23)*

> 🩹 **Kleine UI-Politur (#193 detLAN)** — Wer die Tab-Header-Zeile auf den Seiten **Auswertungen**, **Aussichten** und **Community** schmal hatte (Smartphone, geteiltes Browser-Fenster, HA Companion-App), sah unter den Tab-Buttons eine permanente graue Bildlaufleiste. Sie ist weg. Die Tabs lassen sich weiterhin horizontal wischen, scrollen oder per Touch/Wheel verschieben — die statische Scrollbar-Spur darunter ist nur kosmetisch entfernt.

→ [Auswertungen](HANDBUCH_BEDIENUNG.md#42-auswertungen) · [Aussichten](HANDBUCH_BEDIENUNG.md#43-aussichten)

### Vollbackfill nur noch additiv + Wärmepumpe-Strom-Splits + Monatsberichte-Scroll *(v3.25.22)*

> ✨ **Vier zusammengehörige Items aus drei Issues** — eines davon eine bewusste Architektur-Korrektur:
>
> - **„Vollbackfill" heißt jetzt „Energieprofil-Lücken nachfüllen" und ist immer additiv.** Die Checkbox „Bestehende Tage überschreiben" und die rote Empfehlungsbox sind weg. Hintergrund: der Überschreiben-Modus war ein Recovery-Tool für die alten Aggregations-Bugs (Off-by-one in den Stunden-Snapshots, Counter-Doppelzählung, Vortag-Boundary). Diese Bugs sind seit v3.25.20 alle gefixt — der Modus richtete inzwischen mehr Schaden an als er verhinderte: HA-LTS reicht in vielen Setups (Recorder-Purge, Sensor-Umbau) kürzer zurück als das gepflegte Profil; „löschen + überschreiben" hat dann Wochen oder Monate Historie unwiederbringlich gelöscht. Wer einen einzelnen Tag verzerrt findet, nutzt jetzt ausschließlich den Reload-Knopf in der Tagestabelle (mit Vorschau vor Übernahme — siehe v3.25.18). (#190)
> - **Vollbackfill-Banner sagt warum nicht alle Tage geschrieben wurden.** Bisher meldete der Erfolgs-Hinweis nur „X von Y Tagen geschrieben" — wer dann nur 79 % sah, dachte an Datenverlust. Tatsächlich wurden Tage ohne HA-Statistics-Werte stillschweigend übersprungen (Sensor existierte noch nicht, HA-Recorder war down). Das Banner zeigt jetzt explizit: „X Tage geschrieben · Y Tage ohne HA-Daten übersprungen · Z Tage bereits vorhanden". (#190 Klausnn)
> - **Monatsbericht: Wärmepumpe-Strom-Aufteilung Heizung/Warmwasser sichtbar.** Wer in der Wärmepumpe-Investition die getrennte Strommessung aktiviert hat, sieht im Monatsbericht jetzt unter „Stromverbrauch" zwei „davon"-Zeilen — Heizung und Warmwasser. Konsistent zur bereits vorhandenen Wärme-Aufteilung darunter. Anlagen ohne getrennte Messung sehen die Zeilen weiter nicht. (#191 rapahl, der war Ideengeber für die getrennte Strommessung)
> - **Monatsbericht: Scroll-Position bleibt beim Monatswechsel.** Wer die Wärmepumpe-Sektion aufgeschlagen hat und auf einen anderen Monat klickt, bleibt jetzt an der Wärmepumpe — die rechte Inhaltsspalte springt nicht mehr ungewollt an den Seitenanfang. Der Sprung an den Seitenanfang bei einem Wechsel des Hauptmenü-Punktes (Cockpit → Aussichten etc.) bleibt natürlich erhalten. (#182 detLAN-Folge zu v3.25.21)

→ [Daten → Energieprofil](HANDBUCH_EINSTELLUNGEN.md) · [Cockpit → Monatsberichte](HANDBUCH_BEDIENUNG.md#41-cockpit)

### Reihenfolge korrigiert + Stammdaten sortiert + Monatsberichte-Spalte bleibt stehen *(v3.25.21)*

> 🩹 **Drei Folge-Items zum gestrigen UX-Bündel** — direkt aus der detLAN-Rückmeldung zu v3.25.19/20:
>
> - **Reihenfolge korrigiert: Wärmepumpe wieder vor Wallbox/E-Auto.** v3.25.19 hatte das Cockpit-Banner-Bild aus #186 falsch gelesen und WB+EAuto vor die WP gestellt. Korrekt ist `PV-Anlage → Speicher → Wärmepumpe → Wallbox → E-Auto` (genau die Reihenfolge im Cockpit-Banner). Wirkt jetzt einheitlich auf Cockpit-Subtabs, Sensor-Mapping-Wizard, Statistik-Import, MQTT-/HA-Sensoren-Export — und neu auch auf **Stammdaten → Investitionen**, das bisher noch eine eigene alte Reihenfolge hatte.
> - **Stammdaten → Investitionen sortiert jetzt sinnvoll.** Innerhalb jeder Typ-Gruppe steht die neueste Anschaffung oben (nach Anschaffungsdatum absteigend). Investitionen ohne hinterlegtes Datum landen am Ende der jeweiligen Gruppe.
> - **Monatsberichte: linke Monats-Spalte bleibt jetzt wirklich stehen.** v3.25.13 hatte einen Wheel-Bubble-Bug behoben, das Verhalten beim Klick auf einen alten Monat blieb aber kaputt — die rechte Inhalts-Spalte verschob sich, ältere Monate (2023) waren ohne Umweg nicht erreichbar. Jetzt ist die Monats-Spalte ein eigener, oben klebender Scroll-Container — ältere Monate erreichst du per Wheel direkt in der Spalte, und die rechte Seite bleibt unverrückbar.
> - **Schreibweise „Gefahrene km"** statt „km gefahren" — wirkt einheitlich im Statistik-Import, in der E-Auto-Σ-Kachel und im Sensor-Mapping.

→ [Cockpit → Monatsberichte](HANDBUCH_BEDIENUNG.md#41-cockpit) · [Stammdaten → Investitionen](HANDBUCH_EINSTELLUNGEN.md)

### Daten-Checker: keine Fehlalarme mehr für Strompreis-Sensor und Dienstwagen-E-Autos *(v3.25.20)*

> 🩹 **Zwei Warnungen, die für viele Anwender keine waren** — nach Joachim-PN-Folge zu v3.25.19:
>
> - **Strompreis-Sensor wird nicht mehr als kWh-Counter geprüft.** Die Warnung „1 kWh-Sensor(en) nicht in HA-Long-Term-Statistics" mit Verweis auf `sensor.grid_price_monitor_average_price_today` (oder einen vergleichbaren Tibber-/aWATTar-/EPEX-Sensor) war ein Fehlalarm — der Strompreis ist ct/kWh, kein kumulativer Energiezähler. Wir lesen ihn nur live für die Tagesverlauf-Anzeige; ein fehlendes `state_class` ist hier irrelevant. Warnung verschwindet automatisch nach dem Update.
> - **Dienstwagen-E-Autos werden im „Energieprofil – Zähler-Abdeckung"-Check übersprungen.** Bisher meldete der Check „verbrauch_kwh oder ladung_kwh fehlt" auch für E-Autos, die als Dienstwagen markiert sind — bei einem Dienstwagen ist die Forderung aber sinnlos: kein PV-Bezug, keine Verbrauchsbilanz, keine ROI-Auswertung. Den Skip hatten wir schon in den ROI-Checks, aber im Abdeckungs-Check vergessen. Wer also ein E-Auto mit gesetzter „Dienstwagen"-Markierung hat, sieht die Warnung nicht mehr.

→ [Daten-Werkzeuge → Daten-Checker](HANDBUCH_EINSTELLUNGEN.md)

### UX-Konsistenz-Bündel: Cockpit-Reihenfolge, Statistik-Import-Lesbarkeit, Kompressor-KPI *(v3.25.19)*

> ✨ **Sichtbar an mehreren Stellen** — Sammlung kleiner Schliff-Items aus den Issues #185, #186, #187, #188 (detLAN + rapahl):
>
> - **Wallbox vor E-Auto vor Wärmepumpe** als globale Reihenfolge — wirkt auf Cockpit-Subtabs, HA-Sensoren-Export-Liste, Sensor-Mapping-Wizard, Statistik-Import. Wallbox+E-Auto bilden ein Paar (fest installierte Anschlussstelle + mobiler Verbraucher), Wärmepumpe folgt danach. (#187/2)
> - **Statistik-Import lesbar** — Basis-Felder erscheinen mit deutschen Labels („Einspeisung", „Netzbezug", „PV Erzeugung Gesamt") statt Backend-Schlüsseln (`einspeisung`, `netzbezug`, `pv_gesamt`). Kompressor-Starts heißen so statt `wp_starts_anzahl`. Investitions-Typen werden als „Wallbox" / „E-Auto" / „Wärmepumpe" angezeigt, nicht als Klein-Slugs. Monatsliste chronologisch absteigend (aktuellster Monat oben). (#187/1, #186/3)
> - **Cockpit-Übersicht** — Sektion „E-Auto & Wallbox" heißt jetzt „Wallbox & E-Auto", und die E-Auto-Komponenten erscheinen unter den Wallbox-Komponenten — konsistent zur globalen Reihenfolge. (#186/1)
> - **HA-Sensoren-Export → Verfügbare Sensoren** — Kategorien-Reihenfolge nach detLAN-Vorschlag: Anlage → Energie → Speicher → Investition (+ Komponenten-Detailkategorien) → Finanzen → Quoten → Umwelt → Status. (#186/4)
> - **Monatsbericht KPI-Kachel „Kompressor-Starts"** — zeigt jetzt die Monats-Summe groß und das Tages-Maximum klein im Subtitel — konsistent zu allen anderen Σ-Werten. (Vorher: Max groß, Σ klein.) (#185)
> - **Kraftstoff-Box bedingt** — Der Hinweis „Kraftstoffpreise nachpflegen" erscheint nur noch, wenn mindestens eine E-Auto-Investition gepflegt ist; sonst ist die Information für die Anlage irrelevant. Wirkt in **Daten → Monatsdaten** und in **Daten → Energieprofil**. (#188 rapahl)
> - **Sensor-Mapping „keine HA-Statistik"-Badge** — erscheint nur noch bei kumulativen kWh-Sensoren, wo eine Long-Term-Statistik tatsächlich gebraucht wird. Bei Live-Leistungs-Sensoren (W), SoC-Werten (%) oder Temperaturen (°C) ist der Badge weg — die werden direkt aus dem HA-State gelesen, da gibt es keine Statistik-Voraussetzung. (Joachim-PN nach Wattpilot-Mapping)

→ [Auswertungen → Energieprofil](HANDBUCH_BEDIENUNG.md#42-auswertungen)

### „Tag neu aggregieren" mit Vorschau-Tabelle vor Übernahme *(v3.25.18)*

> 🩹 **User-sichtbare Reparatur** — Wer in **Einstellungen → Daten → Energieprofil** auf das Reload-Symbol eines Tages klickt, sieht ab sofort zuerst eine Vergleichstabelle: pro Stunde und Energiefluss (PV / Einspeisung / Bezug / …) eine Spalte „Alt" (was steht in der DB) und eine Spalte „Neu" (was käme jetzt aus Home Assistant). Erst nach „Übernehmen" werden die Werte tatsächlich überschrieben. Differenzen über 1 kWh sind fett markiert, kleinere Abweichungen orange — auf einen Blick sichtbar, ob die Reparatur sinnvoll ist oder ob HA selbst gerade Müll liefert.
>
> Außerdem zwei Bug-Fixes im Reparatur-Pfad: Stunde 0 hängt rechnerisch vom Snapshot des Vortags um 23:00 ab — der wurde bisher beim Reload **nicht** mit überschrieben, sodass ein alter, korrupter Vortags-Wert den Spike beliebig oft wieder produzieren konnte. Ab v3.25.18 wird er mitgenommen. Dazu ist ein zweiter, älterer Mechanismus entfernt, der bei Tagesreset-Zählern (utility_meter daily) gelegentlich den falschen Wert in die Snapshot-Tabelle geschrieben hat — das war die Wurzel des ursprünglichen Issue #184. Wer ältere Counter-Spikes in der Historie hat, kommt damit jetzt mit einem Klick + „Übernehmen" sauber durch.
>
> **Außerdem im Bündel** — drei kleine UX-Items aus dem detLAN-Pakt: Tagesdetail-Pfeile blättern bis einschließlich heute (rollierend aktualisiert, vorher endete bei gestern). Der `Lade…`-Hinweis am Datums-Picker erscheint nur noch, wenn der Fetch länger als 250 ms braucht — kein Aufploppen-und-Weg-Flash mehr. Reihenfolge im Sensor-Mapping-Wizard: Wallbox steht jetzt vor E-Auto (konsistent zum Cockpit, fest installierte Komponente vor mobilem Verbraucher).

→ [Auswertungen → Energieprofil](HANDBUCH_BEDIENUNG.md#42-auswertungen)

### „Tag neu aggregieren" repariert prä-#184-Spikes jetzt wirklich *(v3.25.17)*

> 🩹 **User-sichtbare Reparatur** — Rainer hat nach v3.25.16 gemeldet, dass das Reparatur-Tool unter **Einstellungen → Daten → Energieprofil** den Counter-Spike vom 1. Mai nicht beseitigt, sondern nur „an den Tagesanfang verschoben" hat: PV plötzlich 1047 kW in Stunde 0:00, alle anderen Stunden ~0. Ursache war, dass das Reparatur-Tool nur Snapshots überschrieb, für die Home Assistant einen sauberen Wert liefert — wenn HA für einen Slot weiterhin `sum=NULL` zurückgibt (typisch nach HA-Restart, bevor `recompile_statistics` durchgelaufen ist), blieb der alte korrupte Snapshot stehen und der Spike kam aus den DB-Werten zurück.
>
> Ab v3.25.17: liefert HA für einen Slot `None`, wird der vorhandene Snapshot **gelöscht**. Die Aggregation sieht dann eine echte Lücke und überspringt die Stunde sauber, statt einen falschen Lifetime-Sprung als Stunden-Δ zu interpretieren. Der reguläre stündliche Snapshot-Job ist davon nicht betroffen — er behält sein defensives Verhalten, damit kein temporärer HA-Hänger einen frisch geschriebenen Slot wegnimmt.
>
> Wer noch einen alten Counter-Spike in der Historie hat: einmalig den betroffenen Tag unter **Einstellungen → Daten → Energieprofil** über das Reload-Symbol neu aggregieren — der Spike sollte danach weg sein (oder als Lücke sichtbar bleiben, falls HA für die Stunde wirklich keinen Wert mehr hat).

→ [Daten-Werkzeuge](HANDBUCH_EINSTELLUNGEN.md)

### WP-Kompressor-Starts: Σ Lebensdauer kommt direkt aus dem Hersteller-Sensor *(v3.25.16)*

> ⚠ **User-sichtbare Wert-Korrektur** — Nach v3.25.14 meldete detLAN, dass das Cockpit immer noch driftet (146 statt 134 Starts). Statt die Eichungs-Logik noch eine Runde nachzuschärfen, fliegt der ganze Selbstkalibrierungs-Mechanismus raus. Σ Lebensdauer im Cockpit zeigt ab sofort einfach das, was der Hersteller-Sensor sagt — keine Berechnung, keine Eichung, keine Drift-Möglichkeit. Wenn eedc im Lauf der Zeit weniger Tagesinkremente erfasst als der Hersteller intern hochzählt (z. B. wegen Sensor-Aktivierungs-Lücken), bleibt das zwischen den Anzeigen sichtbar: Cockpit zeigt die Hersteller-Wahrheit, Monatsbericht zeigt was eedc erfasst hat. Diagnose ohne versteckte Magic.

Bei reinen MQTT-Standalone-Setups ohne direkten HA-State-Zugriff fällt der Read auf die Statistics- bzw. den jüngsten Snapshot zurück — höchstens eine Stunde alt.

→ [Cockpit → Wärmepumpe](HANDBUCH_BEDIENUNG.md#41-cockpit)

### Tagesdetail-Ansicht: Vor/Zurück-Pfeile zum Blättern *(v3.25.15)*

> ✨ **Sichtbar in Auswertungen → Energieprofil → Tagesdetail** — Neben dem Datums-Eingabefeld stehen jetzt links und rechts kleine Chevron-Buttons (`<` `>`) zum Blättern um einen Tag. Genau das, was die Monats-Ansicht schon hat — die beiden Tabs sind nun symmetrisch in der Bedienung. Der „nächster Tag"-Button wird automatisch deaktiviert, sobald gestern erreicht ist (heute hat noch keinen abgeschlossenen Energieprofil-Tag).

→ [Auswertungen → Energieprofil](HANDBUCH_BEDIENUNG.md#42-auswertungen)

### WP-Kompressor-Starts: Σ Lebensdauer wächst nicht mehr im Tagesverlauf zu hoch *(v3.25.14)*

> ⚠ **User-sichtbare Wert-Korrektur** — Folgebefund zu v3.25.13: nach dem dortigen Wizard-Save-Fix beobachtete detLAN, dass die Σ-Lebensdauer-Anzeige im Lauf des Tages nach oben driftet — bei 7 realen Kompressor-Starts heute zeigte das Cockpit 136 statt 131. Ursache war keine fehlerhafte Sensor-Erfassung, sondern eine doppelte Buchhaltung des heutigen Tages: zum Save-Zeitpunkt floss er bereits in die Baseline-Berechnung ein, später dann nochmal in die Σ-Aggregation. Beide Stellen lasen den heutigen TagesZusammenfassung-Eintrag, der während des Tages aber noch instabil ist (Snapshot-Job läuft stündlich, der Tagesabschluss `morgen 00:00` existiert ja noch nicht).

Fix: heutiger Tag wird konsistent aus der TagesZusammenfassung-Aggregation ausgeschlossen, der heutige Verlauf kommt stattdessen aus einer Live-Hochrechnung (aktueller Hersteller-Counter minus Snapshot vom heutigen Tagesanfang). Σ Lebensdauer bleibt damit jederzeit synchron mit dem WP-Display, ohne im Lauf des Tages zu driften. Tooltip im Cockpit zerlegt die Anzeige jetzt in drei Anteile: Hersteller-Baseline + eedc abgeschlossene Tage + heute live. Gleicher Fix gilt auch für die „Aktueller Monat"-Ansicht.

Bei reinen MQTT-Standalone-Setups ohne direkten Live-State-Zugriff fehlt der heutige Anteil bis zum Tagesabschluss — das ist bewusst so, lieber konservativ als doppelt gezählt.

→ [Cockpit → Wärmepumpe](HANDBUCH_BEDIENUNG.md#41-cockpit)

### Sensor-Zuordnung-Zusammenfassung: Großschreibung, Reihenfolge, Sensor-IDs nicht mehr abgeschnitten *(v3.25.14)*

> ✨ **Sichtbar im Sensor-Mapping-Wizard** — Der „Zusammenfassung"-Tab zeigte Investitions-Typen in Klammern als interne Schlüssel (`(e-auto)`, `(pv-module)`, `(speicher)`, `(waermepumpe)`, `(wallbox)`) statt als deutsche Bezeichnung. Feldnamen kamen ungekämmt aus den Backend-Schlüsseln: `pv erzeugung (kWh)`, `wp starts anzahl`, `km gefahren`. Auf breiten Bildschirmen wurde die Sensor-ID rechts trotzdem bei 200 Pixeln abgeschnitten — sichtbar als `…sensor.bat…`.

Behoben: Investitions-Typen jetzt mit deutschen Labels (`(E-Auto)`, `(PV-Module)`, `(Wärmepumpe)`, …), Feldnamen mit Akronym-Behandlung (`PV-Erzeugung (kWh)`, `Kompressor-Starts`, `Kilometer gefahren`), Investitions-Karten in fester Reihenfolge (PV → Wechselrichter → Speicher → BKW → WP → E-Auto → Wallbox → Sonstiges) statt API-Reihenfolge, und die Sensor-ID-Truncation greift nur noch auf schmalen Viewports — auf Desktop wird die volle ID angezeigt.

→ [Sensor-Zuordnung](HANDBUCH_EINSTELLUNGEN.md#11-ha-sensor-zuordnung-add-on)

### MQTT-Export: Kategorien mit deutschen Labels und passenden Icons *(v3.25.14)*

> ✨ **Sichtbar im HA-Sensor-Export-Tab** — Der „Verfügbare Sensoren"-Block listete mehrere Kategorien (Anlage, Quote, Investition, Speicher, Status, Wärmepumpe, E-Auto, Wallbox) als rohen Schlüssel mit Stecknadel-Icon, weil deren Mapping fehlte. Die Investitions-Sensoren-Kachel hatte das gleiche Problem in der Klammer; zusätzlich war die abgerundete Ecke der Karten beim Hover „defekt" — der Hintergrund schnitt über den Border.

Behoben: alle Kategorien haben jetzt deutsche Labels und sprechende Icons (Anlage 🏠, Quoten 📊, Investition 💼, Wärmepumpe 🔥, Speicher 🔋, E-Auto 🚗, Wallbox 🔌, Status ⚙️). Anzeige-Reihenfolge: Anlage zuerst, dann Auswertungs-Pyramide (Energie / Quoten / Finanzen / Umwelt), dann Investitions-Aspekte, Status zuletzt. Investitions-Sensoren-Block analog sortiert. Card-Border-Radius-Bug behoben.

→ [HA-Sensor-Export](HANDBUCH_EINSTELLUNGEN.md#13-ha-sensor-export)

### Wärmepumpe: „Heizenergie" → „Heizwärme" mit Tooltips elektrisch / thermisch *(v3.25.14)*

> ✨ **Sichtbar in der Monatsdaten-Eingabe** — In der Eingabemaske der WP-Monatsdaten wurde „Heizenergie" leicht mit „Stromverbrauch" verwechselt — beide klingen elektrisch. Wer in beiden Feldern denselben Wert eintrug (oder dachte, „Heizenergie" sei einfach der Strom), bekam einen COP von 1.0 angezeigt. Das ist der Verräter, aber für Erstnutzer nicht selbsterklärend.

Konsistent über alle Stellen umgestellt: das Eingabefeld heißt jetzt **„Heizwärme"** (nicht mehr „Heizenergie"), und unter jedem Eingabefeld steht ein erklärender Hinweis:

- **Stromverbrauch / Strom Heizen / Strom Warmwasser:** „Stromaufnahme … (elektrisch)"
- **Heizwärme:** „Abgegebene Heizwärme (thermisch) — COP = Heizwärme / Strom"
- **Warmwasser:** „Abgegebene Warmwasser-Wärme (thermisch)"

Wer beim Hovern über das Eingabefeld zusätzlich den HTML-Tooltip sehen möchte: derselbe Text steht auch dort. Der Backend-Schlüssel `heizenergie_kwh` und der CSV-Suffix `_Heizung_kWh` bleiben unverändert — bestehende CSV-Templates und Imports funktionieren weiter.

→ [Monatsdaten erfassen](HANDBUCH_BEDIENUNG.md#43-monatsdaten)

### WP-Kompressor-Starts-Baseline bleibt nach Investitionen-Speichern erhalten *(v3.25.13)*

> ⚠ **User-sichtbare Wert-Korrektur** — Wer einen Kompressor-Starts-Sensor seiner Wärmepumpe gemappt hat und die im Sensor-Zuordnung-Wizard gesetzte Baseline (Σ aller Lebensdauer-Starts vor dem ersten Tag bei eedc) erleben möchte, hatte bisher folgendes Problem: jedes Schließen des Investitionen → Wärmepumpe-Dialogs mit „Speichern" — auch ohne irgendeine Datenänderung — setzte die Baseline auf `None` zurück. Cockpit → Wärmepumpe zeigte dann nur die Σ der eedc-Tagesdifferenzen (also die Starts seit Inbetriebnahme), nicht den korrekten `Baseline + Σ Tagesdifferenzen`-Lebensdauer-Wert.

Hintergrund: das Investitionen-Form sammelte beim Speichern nur die im Form sichtbaren Felder ein und sendete das als komplettes neues `parameter`-Objekt ans Backend. Wizard-only-Felder wie `wp_starts_anzahl_baseline`, die der Sensor-Zuordnung-Wizard direkt in `parameter` schreibt aber nirgendwo im Form sichtbar macht, fielen dadurch raus.

Der Fix mergt jetzt das `parameter`-Objekt mit dem bestehenden statt es zu ersetzen — Wizard-Keys bleiben erhalten. **Nach dem Update einmalig Sensor-Zuordnung → Speichern & Abschließen**, dann ist die Baseline neu gesetzt und bleibt von da an stabil.

→ [Cockpit → Wärmepumpe](HANDBUCH_BEDIENUNG.md#41-cockpit)

### Mobile-Ansicht der Monatsberichte vollständig scrollbar *(v3.25.13)*

> ⚠ **Mobile-Sichtbar** — Wer die App auf einem Smartphone oder im DevTools-Mobile-Mode aufruft, kann jetzt mit aufgeklappter Energie-Bilanz auch die Sektionen darunter (Community-Vergleich, Speicher, Wärmepumpe, E-Mobilität, Balkonkraftwerk, Sonstiges) erreichen.

Vorher endete der Scroll-Bereich bei aufgeklappter Energie-Bilanz an der Finanzen-Sektion — alles darunter war zwar im DOM gerendert, aber außerhalb des Layout-Scroll-Bereichs. Auf Desktop war die Ansicht unbeeinflusst, weil dort der Sticky-Sidebar-Layout-Pfad greift.

→ [Cockpit → Monatsberichte](HANDBUCH_BEDIENUNG.md#41-cockpit)

### iOS-Smartphones / kleine Viewports: kein „Durchscrollen" mehr bis zur HA-Titelleiste *(v3.25.13)*

> ⚠ **Mobile-Sichtbar** — Auf iPhone SE und im HA-Companion-WebView konnte die eedc-App so weit nach oben gescrollt werden, dass unter dem Footer eine leere Fläche entstand und nur noch die HA-App-Titelleiste sichtbar blieb. Der eigentliche App-Inhalt war dann oberhalb des Sichtbereichs.

Ursache war ein Drift zwischen dem dynamischen Viewport-Layout-Container (`100dvh`) und dem Document-Root, das auf iOS und in DevTools-Mobile-Simulationen unter bestimmten Viewports unabhängig scrollen konnte. Der Layout-Wrapper ist jetzt der einzige Scroll-Owner — Document-Root wurde an die Viewport-Höhe gepinnt.

iPhone 11 und iPhone 16 Pro hatten den Drift in der Praxis nicht gezeigt, das Symptom war auf kleine Viewports beschränkt.

### Stundenwerte-Spike durch Counter-Sensor-Ungereimtheit gefixt *(v3.25.13)*

> ℹ️ **Folge-Patch zu v3.25.10/v3.25.11** — Verstärkt die Counter-Spike-Vermeidung bei Sensoren, die in HA-Statistics zeitweise keinen `sum`-Wert lieferten (typisch nach Restart). Der `get_value_at`-Pfad mischte in solchen Fällen `sum` und `state` aus aufeinanderfolgenden Slots, was extrem große oder kleine Stunden-Differenzen erzeugen konnte.

Wer in den letzten Tagen Counter-Spikes im Tagesprofil gesehen hatte, repariert sie wie in v3.25.11 beschrieben über den Daten-Checker und „Tag neu aggregieren". Neu auftretende Spikes durch dieses Pattern werden ab v3.25.13 nicht mehr produziert.

→ [Daten-Checker → Energieprofil-Plausibilität](HANDBUCH_DATEN_CHECKER.md)

### Wärmepumpe mit getrennter Strommessung: konsistente JAZ in allen Cockpits *(v3.25.13)*

> ⚠ **User-sichtbare Wert-Korrektur** — Wer im WP-Setup `getrennte_strommessung` aktiviert hat (Strom Heizen + Strom Warmwasser separat statt Sammel-Sensor), sieht in v3.25.13 in allen WP-Cockpits + Monatsbericht + ROI + HA-Export + PDF-Jahresbericht **denselben** JAZ-Wert.

Vorher las jede Stelle die Daten leicht unterschiedlich — manche summierten Heizen+Warmwasser, manche nutzten den alten Sammel-Sensor (sofern noch gemappt). Folge: leicht abweichende JAZ-Werte zwischen Cockpit Komponenten und Monatsbericht.

Ein neuer SoT-Helper `get_wp_strom_kwh` ist jetzt der einzige Lese-Pfad. Bei aktiver getrennter Messung wird der Sammel-Sensor ignoriert. Im Sensor-Zuordnung → Zusammenfassung-Schritt erscheint der alte Sammel-Sensor als „(obsolet)" mit Hinweis, dass er entfernt werden kann.

→ [Cockpit → Wärmepumpe](HANDBUCH_BEDIENUNG.md#41-cockpit)

### Energiefluss-Tile: kleinere Optik-Korrekturen *(v3.25.13)*

Zwei Detail-Fixes im Live-Dashboard:

- **Sunset-/Alps-Hintergründe:** die Effekt-Layer (Sonnenstrahlen, Atmosphären-Bögen, Sterne, Aurora) ragten bisher in die abgerundeten Tile-Ecken hinein. Jetzt sauber an den Border-Radius geclippt.
- **Mittlere Fensterbreite (Notebook-Standard 1024–1280 px):** der Energiefluss zentrierte sich vertikal mit Lücken oberhalb und unterhalb, weil die Heute-Box rechts höher war als das SVG-Aspect-Ratio. Das Side-by-Side-Layout greift jetzt erst ab 1280 px Fensterbreite — im Notebook-Standard stapelt Heute-Box unter dem Energiefluss.

→ [Live-Dashboard → Energiefluss](HANDBUCH_BEDIENUNG.md#3-live-dashboard)

### Sonstige Erträge im Monatsbericht-T-Konto sichtbar + Monatsergebnis korrigiert *(v3.25.11)*

> ⚠ **User-sichtbare Wert-Korrektur** — Wer Sonstige Erträge erfasst hat (z. B. AG-Erstattung beim Dienstwagen, THG-Quote, eingespielte Kostenrückerstattung), sieht nach diesem Update ein höheres Monatsergebnis und neue HABEN-Zeilen im T-Konto.

Bisher wurden im Monatsabschluss-Wizard erfasste Positionen vom Typ „Ertrag" auf der HABEN-Seite des T-Kontos im Monatsbericht nicht angezeigt und im Monatsergebnis ignoriert — bei E-Autos mit Dienstwagen-Flag wurde sogar der ganze Wirtschaftlichkeits-Block übersprungen, sodass weder die AG-Erstattung als Ertrag noch andere zugehörige Positionen sichtbar waren. Auf der SOLL-Seite tauchte zwar eine Aggregat-Zeile „Sonderkosten" (= Σ Ausgaben) auf, das Pendant für Erträge fehlte aber komplett. Im Monatsergebnis am Card-Header wurden die Ausgaben abgezogen, die Erträge aber nicht aufaddiert — wer also 35 € AG-Erstattung erfasst hatte, fand 35 € weniger in seinem Monatsergebnis als erwartet.

Jetzt wertet der Backend-Pfad `sonstige_positionen` typ-unabhängig pro Investition aus, das Frontend zeigt im T-Konto pro Investition eigene HABEN-Zeilen („Tiguan Hybrid — Sonstige Erträge 35,00 €") und SOLL-Zeilen („Tiguan Hybrid — Sonstige Ausgaben"). Das Monatsergebnis im Card-Header rechnet `Gesamt-Nettoertrag − Betriebskosten + Sonstige Netto`. Wer Erträge erfasst hat, sieht den korrekten Wert ab dem nächsten Cockpit-Aufruf — alte Monate werden automatisch neu berechnet, kein Eingriff nötig.

→ [Monatsabschluss → T-Konto](HANDBUCH_BEDIENUNG.md#10-monatsabschluss)

### Pool-Doppelzählung Wallbox/E-Auto im Cockpit entschärft *(v3.25.11)*

> ⚠ **User-sichtbare Wert-Korrektur** — Wer sowohl eine Wallbox als auch ein E-Auto als getrennte Investitionen pflegt, sieht nach diesem Update niedrigere und realistischere Werte für „Ladung gesamt", „Verbrauch (kWh/100km)" und einen plausiblen PV-Anteil im E-Mobilitäts-Block der Monatsberichte.

Die Wallbox als Investitionstyp misst aus Loadpoint-Sicht (was am Stromanschluss raus geht), das E-Auto als Investitionstyp aus Vehicle-Sicht (was im Auto angekommen ist). Beide messen also denselben Stromfluss aus zwei Perspektiven. Bisher wurden die `ladung_kwh`-Werte beider Investitionen aufaddiert — bei einer Anlage mit 1 E-Auto + 1 Wallbox kam dadurch der Wert für „Ladung gesamt" doppelt so hoch wie real, und der `kWh/100km`-Wert ebenfalls. Bei ungleicher Pflege der zwei Eingabe-Quellen konnte der angezeigte PV-Anteil sogar über 100 % laufen — z. B. wenn die Wallbox einen hohen `ladung_pv_kwh`-Wert hat, das E-Auto aber nur einen kleinen `verbrauch_kwh`-Wert.

Als Übergangslösung nimmt eedc jetzt pro Feld die größere der beiden Quellen als Wahrheit (Loadpoint-Sicht ist üblicherweise inklusiv) und stellt sicher, dass der PV-Anteil mathematisch ≤ 100 % bleibt. Eine saubere Per-Fahrzeug-Trennung folgt mit der Phase 2 des [Wallbox/E-Auto-Datenarchitektur-Konzepts](https://github.com/supernova1963/eedc-homeassistant/blob/main/docs/KONZEPT-WALLBOX-EAUTO.md) — bis dahin bleibt die Cockpit-Gesamtübersicht und der HA-Statistics-/MQTT-Aggregator-Pfad bewusst auf der alten Pool-Logik (sichtbar als Drift-Möglichkeit zwischen Cockpit-Übersicht und Monatsbericht).

Bei Anlagen mit Dienstwagen + Privatauto an gemeinsamer Wallbox bleibt eine Restungenauigkeit: die `kWh/100km`-Berechnung dividiert die Wallbox-Lieferung (inkl. Dienstwagen-Strom) durch die Privat-km — der Wert ist nach diesem Update plausibler, aber noch nicht perfekt. Phase 2 löst das mit Vehicle-Sensoren pro Fahrzeug.

→ [Monatsbericht → E-Mobilität](HANDBUCH_BEDIENUNG.md#10-monatsabschluss)

### Selbsthilfe gegen Counter-Spikes im Tagesprofil *(v3.25.11)*

> ℹ️ **Folge des Off-by-one-Fixes aus v3.25.10** — Der dort behobene Bug hat in seltenen Fällen unphysikalisch hohe Stundenwerte hinterlassen (z. B. ein PV-Spike von 2.384 kWh in einer Stunde statt der realistischen 5 kWh). Bestehende Snapshot-Werte werden vom Service-Bugfix selbst nicht repariert.

Drei aufeinander abgestimmte Selbsthilfe-Wege:

- **„Verlauf nachrechnen" mit Überschreiben** in der Datenverwaltung zieht jetzt vor dem Aggregat zusätzlich die SensorSnapshots des Bereichs frisch aus HA-Statistics — repariert verzerrte Stundenwerte in einem Schritt mit dem Tagesprofil-Aggregat. Bei deaktiviertem Überschreiben (Initial-Backfill) bleibt das Verhalten unverändert.
- **„Tag neu aggregieren"** (das grüne Reload-Symbol in der Tagesliste des Energieprofils) ruft vor dem Aggregat ebenfalls einen Resnap auf — ein Klick auf das Symbol heilt den ausgewählten Tag jetzt vollständig (Snapshots + Aggregate + Heatmap).
- **Daten-Checker erkennt Counter-Spikes selbst:** Neue Kategorie „Energieprofil-Plausibilität" prüft die letzten 30 Tage und meldet Stunden mit `pv_kw` oder `einspeisung_kw` über 1,5× der Anlagen-Spitzenleistung — eindeutig unphysikalisch. Die Detail-Meldung verlinkt direkt auf den Reparatur-Workflow.

Alte Tage älter als 14 Tage können nur in Hourly-Granularität repariert werden, weil HA selbst die 5-Min-Statistik nur ~10–14 Tage zurück bereithält.

→ [Daten-Checker → Energieprofil-Plausibilität](HANDBUCH_DATEN_CHECKER.md) | [Energieprofil → Tag neu aggregieren](HANDBUCH_BEDIENUNG.md#7-auswertung)

### Daten-Checker-Falsch-Warnung „Komponenten ohne kWh-Zähler-Abdeckung" für E-Autos *(v3.25.11)*

Wenn du einen Sensor für die Gesamt-Ladung deines E-Autos im Sensor-Mapping hinterlegt hattest, blieb trotzdem die Warnung „Komponenten ohne vollständige kWh-Zähler-Abdeckung" mit Hinweis `ladung_kwh` stehen. Hintergrund: Das E-Auto-Schema bietet im Wizard das Feld unter dem Schlüssel `verbrauch_kwh` an, der Daten-Checker prüfte aber hartcodiert auf `ladung_kwh` — ein Schlüssel, den du gar nicht zur Auswahl hattest. Andere Stellen im Code akzeptieren beide Schreibweisen.

Der Checker erkennt jetzt beide Schlüssel als korrekt gemappt. Wer einen Sensor hinterlegt hat, sieht den Befund nicht mehr.

→ [Daten-Checker → Energieprofil-Zähler-Abdeckung](HANDBUCH_DATEN_CHECKER.md)

### Off-by-one-Stunde-Bug in Counter-Snapshots behoben *(v3.25.10)*

> ⚠ **Stiller Bug seit v3.19** — Der Bug betrifft die Stundenwerte im Energieprofil (z. B. Tagesverlauf, Heatmap, 24h-Tabellen). Tagessummen und Monatswerte waren NICHT betroffen, weil sich die Verschiebung über 24 h ausmittelt.

Ein Lookup-Helfer in eedc's HA-Statistics-Service las den Zählerstand pro Stunde aus der falschen Zeile in HA's Statistik-Tabelle. HA's Konvention ist „last value of the period": die Zeile bei Stunde 11 enthält den Zählerstand AM ENDE der Stunde, also um 12:00 Uhr — wir lasen aber denselben Wert für Stunde 12. Konsequenz: alle Stunden-Werte im Tagesverlauf seit v3.19 (Snapshot-Rework Oktober 2025) waren systematisch um eine Stunde nach hinten verschoben. Bei einer Anlage mit z. B. 9 kWh PV-Erzeugung in der Stunde 11–12 hat eedc diese 9 kWh stattdessen unter „Stunde 12" verbucht — die Tagessumme war richtig, aber die Stundenposition falsch.

Verursacht wurde der Bug durch eine Fehlinterpretation von HA's API-Konvention; maskiert wurde er einerseits dadurch, dass Tagessummen unbeeinflusst sind, andererseits durch HA-Latenz beim hourly-Snapshot-Job (der zufällig oft den korrekten Vorgänger-Slot las, weil die aktuelle Stunde noch nicht finalisiert war). Mit der Phase-1-Erprobung der 5-Min-Snapshots auf Winterborn 2026-05-01 wurde die Diskrepanz erstmals systematisch sichtbar: HA Energy Dashboard zeigte 8,9 kWh für Stunde 11–12, eedc zeigte 10,1 kWh.

**Was du tun kannst:** Nichts — der Fix wirkt automatisch ab dem nächsten Snapshot. Wer die Vergangenheit korrigieren will, kann den neuen Resnap-Endpoint `POST /api/diagnostics/resnap-snapshots?days=7` aufrufen (regeneriert die letzten 7 Tage). Für Tage älter als 14 Tage steht nur die Hourly-Korrektur zur Verfügung; die 5-Min-Granularität limitiert HA selbst auf ~10–14 Tage. Der reguläre `Vollbackfill aus HA Statistics` (Datenverwaltung) bleibt unverändert nutzbar — dieser nutzt eine andere Quelle (mean-Werte) und war vom Bug nicht betroffen.

→ [Energieprofil-Auswertung](HANDBUCH_BEDIENUNG.md#7-auswertung)

### Drift-Audit-Initiative abgeschlossen *(als Teil von v3.25.10 ausgeliefert)*

> ℹ️ **Versionssprung 3.25.8 → 3.25.10 ist beabsichtigt:** Die hier beschriebenen Drift-Audit-Bündel-G-Änderungen waren ursprünglich für v3.25.9 vorgesehen. Während der CHANGELOG schon stand, wurde der Off-by-one-Bug entdeckt — beide Pakete sind unter Tag `v3.25.10` zusammen ausgeliefert worden, statt zwei Releases im Minutenabstand zu schießen. Es gibt also kein Tag `v3.25.9` im Repository.

Letzter Bündel der Aufräum-Aktion, die mit #178 ([Werte-Drift bei der Wärmepumpe](https://github.com/supernova1963/eedc-homeassistant/issues/178)) startete. Insgesamt wurden 16 Drift-Stellen in 6 Domänen identifiziert und in v3.25.7–v3.25.10 abgearbeitet. Dieses Bündel hat **keine User-sichtbare Werte-Wirkung** — es konsolidiert nur intern Daten in der Datenbank auf einheitliche Schlüssel und ersetzt 23 verstreute Doppel-Read-Stellen im Code durch fünf zentrale Helper. Die DB-Migration läuft beim Add-on-Start einmalig automatisch durch.

Hintergrund: bei mehreren früheren Schema-Wechseln blieben Code-Stellen mit Doppel-Reads der Form `data.get("alt", 0) or data.get("neu", 0)` als Sicherheitsnetz zurück. Gleichzeitig waren in der DB beide Schlüssel-Versionen parallel vorhanden. Beides wurde jetzt vereinheitlicht — bei künftigen Schema-Änderungen muss nur noch eine zentrale Stelle gepflegt werden.

### Speicher- und V2H-Ersparnis im Aussichten-Tab konsistent zur Detail-Ansicht *(v3.25.8)*

> ⚠ **User-sichtbarer Wert-Sprung** — Wer den Aussichten-Tab als Referenz für Speicher-Ersparnis nutzt, wird nach diesem Update einen ~25 % niedrigeren Wert sehen. Das ist eine Korrektur, kein Verlust.

Bisher rechneten Aussichten und Investitionen-Detail die Speicher-Ersparnis mit unterschiedlichen Formeln: Aussichten nahm den vollen Bezugspreis (`Entladung × 30 ct`), die Detail-Ansicht den Spread zwischen Bezug und Einspeisevergütung (`Entladung × (30 − 8) ct`). Bei einer Anlage mit 2.000 kWh Speicher-Durchsatz/Jahr ergab das 600 € (Aussichten) gegen 440 € (Detail) — für dieselbe Anlage.

Korrekt ist das Spread-Modell, weil der gespeicherte Strom ohne Speicher als Einspeisung Vergütung erwirtschaftet hätte — nur die Differenz ist echter Netto-Gewinn. Aussichten ist jetzt darauf umgestellt; alle Tabs zeigen denselben Wert. Gleiche Logik gilt für V2H (E-Auto-Rückspeisung ins Haus).

Im Speicher-Dashboard war außerdem das Formel-Label ungenau („Ersparnis = Entladung × Strompreis") — passt jetzt zur tatsächlichen Berechnung.

→ [Aussichten-Tab](HANDBUCH_BEDIENUNG.md#5-aussichten--prognose) | [Speicher-Dashboard](HANDBUCH_BEDIENUNG.md#33-speicher-dashboard)

### Cockpit-E-Auto-Ersparnis liest jetzt deine gepflegten Werte *(v3.25.8)*

Cockpit → Übersicht und Cockpit → Monatsberichte hatten bisher 7 L/100 km Vergleichsverbrauch und 1,80 €/L Benzinpreis hartcodiert — selbst wenn du im E-Auto-Formular andere Werte hinterlegt hattest, wurden die ignoriert. Aussichten und PDF haben deine Eingaben schon respektiert; Cockpit zog deshalb 7–9 % höhere Ersparnis-Werte. Jetzt rufen alle Stellen denselben Helper auf, kanonische Defaults sind 7,5 L/100 km und 1,65 €/L (entspricht den Voreinstellungen im Formular).

→ [Investitionen pflegen → E-Auto](HANDBUCH_BEDIENUNG.md#11-investitionen-pflegen)

### Drei stille Datenfehler bei Anlagen mit historischem Backfill behoben *(v3.25.8)*

Wenn du via CSV-Import oder HA-LTS-Backfill Daten geladen hast, die zeitlich vor dem Anschaffungsdatum einer Komponente liegen (z. B. WP-Daten ab Januar, obwohl die WP erst im April installiert wurde), wurden diese Vor-Daten in drei Endpoints fälschlich mitberechnet:

- **Cockpit → Prognose** (Vergleich Soll-PV/Ist-PV) — falls PV-Module mid-year angeschafft wurden
- **HA-Sensor-Export** (z. B. `eedc_wp_ersparnis_euro`) — falls WP/Speicher mid-year angeschafft wurden
- **Community-Server-Submission** — gleicher Effekt; bei betroffenen Anlagen wurden Vor-Anschaffungs-Werte als Anlage-Beitrag hochgeladen

Alle drei greifen jetzt auf den gleichen Anschaffungsdatum-Filter zu, der seit v3.23.1 in Cockpit-Übersicht/Auswertungen aktiv ist. Wenn du betroffen warst, normalisiert sich dein Wert beim nächsten Cockpit-Aufruf bzw. nächster Community-Submission automatisch.

### Hintergrund: Drift-Audit-Initiative

Der WP-Ersparnis-Bug aus #178 (v3.25.7) hat eine systematische Inventur aller Investitions-Berechnungen ausgelöst. 16 Drifts in 6 Domänen identifiziert. v3.25.8 schließt davon 5 Bündel; eine weitere Folge-Version macht den Rest (vereinheitlichte Reader für die JSON-Felder im `verbrauch_daten`-Speicher mit Datenbank-Migration). Was davon bei dir ankommt, steht in den Einträgen zu v3.25.8 und den Folgeversionen — eine gesonderte Inventur-Datei gibt es im Repository nicht (der frühere Verweis auf `docs/drafts/…` ging ins Leere: Entwurfs-Notizen sind nicht Teil der Auslieferung).

### Wärmepumpe: Ersparnis-Anzeige in allen vier Tabs konsistent *(v3.25.7)*

Vor v3.25.7 zeigten Cockpit → Monatsberichte, Cockpit → Übersicht, Cockpit → Wärmepumpe und Auswertungen → Komponenten teils unterschiedliche WP-Ersparnis-Werte für dieselbe Anlage (z. B. 7 € / 61 € / 77 € / 61 €). Ursache: vier Code-Pfade mit unterschiedlichen hartcodierten Defaults und teils falschen Param-Keys, sodass gepflegte Werte für „alter Heizungspreis" oder „alter Energieträger" stillschweigend ignoriert wurden. Jetzt rufen alle vier denselben Helper auf — der Wert ist konsistent. Issue [#178](https://github.com/supernova1963/eedc-homeassistant/issues/178), detLAN-Bericht.

→ [Cockpit-Wärmepumpe](HANDBUCH_BEDIENUNG.md#36-wärmepumpe-dashboard)

### Wärmepumpe: Hersteller-Lebensdauer-Counter im Cockpit *(v3.25.3)*

Wärmepumpen-Hersteller wie Nibe oder Viessmann liefern einen Counter „Kompressor-Starts gesamt" — die echte Lebensdauer-Zahl ab Werks-Inbetriebnahme, oft 4-stellig im Auslieferungszustand. eedc zählt seit v3.24.0 selbst über Snapshot-Differenzen — das hat den 4-stelligen Sockel aber nicht abgebildet, sodass das WP-Cockpit unter „Σ Kompressor-Starts" eine viel zu kleine Zahl zeigte (z. B. 87 statt 5.234). Beim nächsten Speichern im Sensor-Mapping-Wizard eicht eedc die Hersteller-Baseline jetzt einmalig (`baseline = sensor.gesamt − Σ eedc-Tagesdifferenzen seit Anschaffung`) und addiert sie beim Anzeigen wieder dazu. Der Tooltip auf der Kachel zeigt die Zerlegung Hersteller-Baseline + eedc-seit-Aktivierung + höchste Tagessumme. Selbstkorrigierend bei jedem Wizard-Rerun. Issue [#173](https://github.com/supernova1963/eedc-homeassistant/issues/173), detLAN-Vorschlag.

→ [Bedienung §3.6 Wärmepumpe](HANDBUCH_BEDIENUNG.md#36-wärmepumpe-dashboard)

### Auf-/Zuklappen + Sortierung jetzt in allen Cockpit-Dashboards *(v3.25.3)*

Die seit v3.21.0 im Auswertungs-Tab vorhandene Mechanik zum Einklappen einzelner Sektionen und zum Drag-and-Drop-Umsortieren ist jetzt auch in den Dashboards Cockpit → PV-Anlage, Cockpit → Wärmepumpe und Monatsabschluss aktiv. Reihenfolge wird pro Anlage gespeichert (ein User mit zwei Anlagen kann sie unterschiedlich anordnen). Verhalten ist 1:1 identisch zur Auswertungs-Implementierung, nur jetzt überall verfügbar. Issue [#175](https://github.com/supernova1963/eedc-homeassistant/issues/175), detLAN-Vorschlag.

→ [Bedienung §3 Cockpit](HANDBUCH_BEDIENUNG.md#3-cockpit-dashboards)

### WP-Kompressor-Starts: Slot 23:00 + Tageswerte rückwirkend reparieren *(v3.25.2)*

Bei Wärmepumpen mit Kompressor-Starts-Sensor ohne `state_class` (typisch lokale Nibe/Viessmann-Integration) fehlte regelmäßig der Stunden-Slot 23:00 im Tagesdetail, und derselbe Tag tauchte im Cockpit-WP / Monatsbericht nicht in der Aggregat-Sicht auf. Beide Effekte hatten dieselbe Wurzel: ein verlorener Modul-Import in der Live-Vorab-Erfassung kurz vor Mitternacht ließ den 00:00-Snapshot still ausfallen — und der wird sowohl für die Stunde 23:00 als auch für den Tages-Counter gebraucht. Behoben. Künftige Tage werden sauber erfasst; für die offenen Vortage hilft *Auswertung → Energieprofil → Datenverwaltung → Verlauf nachrechnen* (oder Per-Tag-Reaggregation), weil HA die fehlenden LTS-Einträge inzwischen nachgepflegt hat. Issue [#136](https://github.com/supernova1963/eedc-homeassistant/issues/136), detLAN-Beobachtung.

### PV-Cockpit: Module + Speicher nebeneinander statt untereinander *(v3.25.2)*

Innerhalb der Wechselrichter-Karte unter „Cockpit → PV-Anlage → PV-Komponenten" werden Module und Speicher jetzt nebeneinander in zwei Spalten dargestellt (Desktop) — auf Smartphone-Breite weiterhin gestapelt. Wirkt für typische Anlagen-Konfigurationen ausgewogener als das vertikale Layout aus v3.24.6. Issue [#172](https://github.com/supernova1963/eedc-homeassistant/issues/172), detLAN-Mockup.

→ [Bedienung §3.4 PV-Anlage](HANDBUCH_BEDIENUNG.md#34-pv-anlage-dashboard)

### Hilfe-Seite: Inhaltsverzeichnis-Links und Browser-Zurück funktionieren wieder *(v3.25.1)*

In der seit v3.24.2 verfügbaren In-App-Hilfe sprangen Klicks auf die Inhaltsverzeichnis-Einträge (z. B. „2. Installation" am Anfang von *Teil I: Installation & Einrichtung*) aus der Hilfe-Seite heraus statt zur Sektion zu scrollen — die Hilfe-Seite verschwand komplett. Das war ein technischer Konflikt zwischen den Anker-Links im TOC und der App-internen Navigation. Behoben: Inhaltsverzeichnisse, Querverweise zwischen Hilfe-Dokumenten und der Browser-Zurück-Knopf funktionieren jetzt erwartungsgemäß. Rainer-PN.

→ [Bedienung §9 Hilfe](HANDBUCH_BEDIENUNG.md#9-hilfe-in-der-app)

### Mehrere ROI- und Aussichten-Werte rechnen jetzt mit deinen tatsächlichen Eingaben *(v3.25.0)*

Hinter den Kulissen war das `parameter`-JSON, in dem Investitionen ihre typ-spezifischen Detail-Daten halten (z. B. Speicher-Kapazität, V2H-Aktivierung, E-Auto-Fahrleistung), zwischen Form/Wizard und Backend-Lese-Code an mehreren Stellen auseinandergedriftet. Eine Vollinventur hat 7 Bugs zutage gefördert, in denen das Backend Schlüssel las, die Form/Wizard nie geschrieben haben — d. h. deine Eingaben wurden stillschweigend durch Default-Werte ersetzt. Konkret:

- **V2H** (E-Auto Vehicle-to-Home) war im Aussichten-Tab, in der Live-Komponenten-Erkennung und im E-Auto-ROI tot — der Haken im Formular hatte dort keine Wirkung.
- **Arbitrage** (Speicher) war im ROI tot — Aktivierung im Formular wurde ignoriert. Im Speicher-Dashboard funktionierte sie korrekt.
- **Wallbox-Leistung** im Wallbox-Dashboard und im Community-Datensatz zeigte immer 11 kW, unabhängig vom eingegebenen Wert.
- **E-Auto Jahresfahrleistung / PV-Ladeanteil / Vergleichsverbrauch** wurden im ROI nicht berücksichtigt — der ROI rechnete mit 15 000 km, 60 % bzw. 7,0 L/100 km, egal was im Formular stand.
- **WP „Alter Heizungspreis"** hatte je nach Tab unterschiedliche Default-Werte (10 vs. 12 ct/kWh) → unterschiedliche Ersparnis-Anzeigen für denselben Zustand.
- **WP „Getrennte Strommessung"**: ein subtiler String-vs-Boolean-Fehler ließ den Schalter nicht ausgehen, wenn man ihn von „aktiv" zurücksetzte.

Eine einmalige DB-Migration räumt die Drift in deiner bestehenden Datenbank automatisch auf. **Sichtbare Auswirkung für dich:** Wenn du eine der oben genannten Optionen aktiviert oder eingegeben hattest, siehst du ab v3.25.0 plötzlich neue Werte im ROI, im Aussichten-Tab und im Wallbox-Dashboard. Die alten Werte waren Default-Anzeigen, nicht deine Werte.

→ [Bedienung §3 Cockpit](HANDBUCH_BEDIENUNG.md#3-cockpit-dashboards) · [Bedienung §7 Aussichten](HANDBUCH_BEDIENUNG.md#7-aussichten-prognosen)

---

## v3.24.x — In-App-Hilfe & WP-Kompressor-Starts (April 2026)

### PV-Cockpit: Speicher-Kapazität wieder sichtbar + getrennte Sub-Boxen *(v3.24.6)*

Im „Cockpit → PV-Anlage → PV-Komponenten"-Block las das Frontend die Speicher-Kapazität unter dem falschen Schlüssel — gepflegte Daten waren da, blieben aber unsichtbar. Behoben. Zusätzlich werden Module und Speicher jetzt in eigenen, beschrifteten Sub-Sektionen innerhalb der Wechselrichter-Karte dargestellt (statt in einem gemischten Grid), und Speicher ohne Wechselrichter-Zuordnung tauchen in einem separaten Block am Ende auf statt stillschweigend zu verschwinden. Issue [#172](https://github.com/supernova1963/eedc-homeassistant/issues/172).

→ [Bedienung §3.4 PV-Anlage](HANDBUCH_BEDIENUNG.md#34-pv-anlage-dashboard)

### Diese Seite — „Was ist neu" als Pull-Variante *(v3.24.5)*

Die Seite, die du gerade liest. Statt eines Banner-Pop-ups nach Update gibt es einen festen Eintrag in der Hilfe-Sidebar: wer wissen will, was neu ist, schaut hier rein. HA-Add-on-Nutzer sehen den Changelog ohnehin schon im Add-on-Store, GitHub-Releases haben einen eigenen — kein Bedarf für eine dritte Stimme. Discussion [#130](https://github.com/supernova1963/eedc-homeassistant/discussions/130) Folge-Wunsch von Safi105.

### In-App-Hilfe-Seite *(v3.24.2)*

Das Benutzerhandbuch ist jetzt direkt in eedc verfügbar — ohne Browser-Wechsel und ohne Ingress-Login-Probleme in der HA-Companion-App. Acht kuratierte Dokumente in drei Kategorien (*Einstieg* / *Handbuch* / *Referenz*), Sidebar am Desktop, Dropdown auf dem Smartphone. URL-Parameter `?doc=<slug>` macht Direktlinks teilbar (z. B. `?doc=bedienung#7-aussichten-prognosen`). Discussion [#130](https://github.com/supernova1963/eedc-homeassistant/discussions/130).

→ [Bedienung §9 Hilfe](HANDBUCH_BEDIENUNG.md#9-hilfe-in-der-app)

### Wärmepumpe: Kompressor-Starts als Verschleiß- und Auslegungs-Indikator *(v3.24.0 Counter / v3.24.4 Tiles)*

Optionaler Total-Increasing-Sensor im Sensor-Mapping erfasst die Kompressor-Starts der Wärmepumpe (z. B. aus der lokalen „Nibe Heat Pump"-Integration). Cockpit → Monatsberichte zeigt die höchste Tagessumme des Monats als Verschleiß-Indikator („wie heftig hat die WP an ihrem schlechtesten Tag getaktet"), Cockpit → Wärmepumpe zeigt die Σ Starts seit Anschaffung als Auslegungs-Indikator. Stunden-/Tages-Detail in der Energieprofil-Tabelle. Issue [#136](https://github.com/supernova1963/eedc-homeassistant/issues/136), [#169](https://github.com/supernova1963/eedc-homeassistant/issues/169).

→ [Sensor-Referenz §4](SENSOR-REFERENZ.md) · [Bedienung §3.6 Wärmepumpe](HANDBUCH_BEDIENUNG.md#36-wärmepumpe-dashboard)

### Sensor-Mapping: Sensoren ohne HA-Statistics sichtbar machen *(v3.24.1)*

Sensoren ohne `state_class` (z. B. Nibe-Roh-Counter) lassen sich jetzt über einen Fallback-Link „Alle Sensoren ohne Filter anzeigen" auswählen. Die Auswahl wird mit einem amber-farbenen **„ohne Statistik"**-Badge markiert. Begleitend prüft der Daten-Checker eine neue Kategorie *Sensor-Mapping HA-Statistics* — kWh-Felder ohne LTS sind kritisch (Korrektur-Werkzeuge greifen nicht), Counter-Felder unproblematisch. Damit ist der Sensor-Mapping-Wizard auch für nicht-Standard-Integrationen nutzbar.

→ [Einstellungen §3 Sensor-Mapping](HANDBUCH_EINSTELLUNGEN.md#3-sensor-mapping) · [Einstellungen §8 Daten-Checker](HANDBUCH_EINSTELLUNGEN.md#8-daten-checker)

### state_class-Hinweise auf den richtigen Hebel umgestellt *(v3.24.3)*

Im Wizard-Banner und Daten-Checker-Hinweisen stand bisher „vergangene Tage bleiben leer" — das passiert aber auch mit `customize.yaml`-Korrektur, weil HA Long-Term-Statistics erst ab Aktivierung persistiert. Der relevante Hebel im Betrieb ist: ohne `state_class` greifen die **Korrektur-Werkzeuge in der Datenverwaltung** nicht — Vollbackfill, „Verlauf nachrechnen" und Per-Tag-Reaggregation lesen alle aus HA's LTS. Texte und Daten-Checker-Severity entsprechend angepasst.

---

## v3.23.x — Cockpit-Harmonisierung & Diagnose-Werkzeuge (April 2026)

### Cockpit: Reihenfolge umsortiert + WP-KPIs harmonisiert *(v3.23.4)*

Cockpit-Sub-Tabs jetzt in der Reihenfolge **Übersicht → Monatsberichte → PV-Anlage → Balkonkraftwerk → Speicher → Wärmepumpe → Wallbox → E-Auto → Sonstiges** (Erzeuger oben, Speicher in der Mitte, Verbraucher unten). Wärmepumpen-KPIs nutzen über alle vier Render-Stellen (Cockpit-Übersicht, WP-Dashboard, Auswertung, Monatsabschluss) dieselbe Reihenfolge **JAZ → Wärme → Strom → Ersparnis** mit identischen Icons (Thermometer / Flame / Zap / TrendingUp). Anlagenname als Tab-Titel (kein redundantes „Wärmepumpe"-Echo).

→ [Bedienung §3 Cockpit](HANDBUCH_BEDIENUNG.md#3-cockpit-dashboards)

### Aggregate ignorieren Daten vor dem Anschaffungsdatum *(v3.23.0–v3.23.1)*

Cockpit- und Auswertungs-Aggregate für Wärmepumpe / Speicher / Wallbox / E-Auto / Balkonkraftwerk berücksichtigen nur noch Monate **ab dem Anschaffungsdatum** der jeweiligen Komponente. Migrationen (z. B. Wechsel auf Shelly-erfasste WP-Strommessung) verfälschen damit nicht mehr historische JAZ und Ersparnis. Issue [#153](https://github.com/supernova1963/eedc-homeassistant/issues/153).

### Asymmetrie-Diagnostik im Genauigkeits-Tracking *(v3.23.3)*

Toggle **„Kompakt / Diagnostisch"** in der Genauigkeits-Tracking-Card. Der Diagnostisch-Modus splittet die Streuung pro Quelle (OpenMeteo / eedc / Solcast) in „darüber"-und „darunter"-Boxen — Ø-Über-/Unterschätzung in Prozent plus Anzahl Tage. Damit sichtbar, ob ein systematischer Hebel vorliegt („bei dichten Wolken zu hoch, bei klarem Himmel zu niedrig") oder reine Streuung. Issue [#151](https://github.com/supernova1963/eedc-homeassistant/issues/151).

→ [Bedienung §7.2 Prognosen](HANDBUCH_BEDIENUNG.md#72-prognosen)

### Reparatur-Popover bei IST-Datenlücken im Prognosen-Tab *(v3.23.0)*

Klick auf das ⚠ neben einem Tageswert öffnet jetzt einen Popover statt eines Hover-Tooltips. Inhalt: Liste der fehlenden Stunden, kurze Erklärung, Button **„Tag neu berechnen"** (löst eine Per-Tag-Reaggregation aus) und Fallback-Link zum Sensor-Mapping. Direkter Reparatur-Pfad statt Diagnose-Suche.

### Live-Dashboard: Bilanz-Sortierung & Eigenverbrauchs-Cap *(v3.23.5)*

Tageswerte-Kacheln im Live-Dashboard in Energie-Logik-Reihenfolge: **PV → Batterie → Eigenverbrauch (Quellen-Σ) → Netzbezug → Hausverbrauch → Einspeisung**. Eigenverbrauchs-Quote ist jetzt auf 100 % gecappt (vorher konnten ev/pv > 100 % rechnen, wenn Batterie-Entladung aus Vortagen einfloss). Issue [#157](https://github.com/supernova1963/eedc-homeassistant/issues/157).

→ [Bedienung §2 Live Dashboard](HANDBUCH_BEDIENUNG.md#2-live-dashboard)

---

## v3.22.0 — Genauigkeits-Tracking & Mobile-Layout (April 2026)

### MAE und Bias getrennt ausweisen

Genauigkeits-Tracking zeigt jetzt zwei Kennzahlen pro Quelle: **MAE** (mittlere absolute Abweichung — Streuung) und **MBE** (mittlerer signed Error — systematischer Bias). Bias neutral gefärbt (das Vorzeichen ist Information, nicht Wertung). eedc wird zusätzlich zu OpenMeteo und Solcast bewertet. Spaltenstruktur stabilisiert: kein Spaltenflattern mehr nach Tag 7, gedämpfter Header bei fehlendem Lernfaktor.

### Mobile-Layout-Bündel

Sieben Mobile-Layout-Korrekturen aus detLAN-Bugreport: Cockpit-/Energieprofil-SubTabs scrollen aktiven Tab in den sichtbaren Bereich, Monatsberichte-T-Konto auf Mobile als 2-Spalten-Layout (Label | Wert+VJ+Δ gestapelt), Sticky-Bars über Tabellen-thead, Energieprofil-Subtabs mit `flex-wrap` (umbricht statt rechts rauszulaufen), Aussichten-Langfrist-Steuerung vertikal gestapelt, Tabellen mit vielen Spalten zeigen Querformat-Hinweis. Issue [#149](https://github.com/supernova1963/eedc-homeassistant/issues/149).

### VM/NM-Split an astronomischer Tagesmitte

Tageshälften (Vormittag/Nachmittag) splitten jetzt am Solar Noon (via Equation of Time, je nach Standort und Datum bis ~30 min von 12:00 abweichend) statt hart bei 12:00 Uhr Clockzeit. Slots, die Solar Noon enthalten, werden proportional verteilt.

### Banner: Restzeit bis Lernfaktor-Schwelle

Der Hinweis „eedc-Prognose nicht verfügbar" zeigt jetzt zusätzlich, wie viele Tage bereits gesammelt sind und wie viele bis zur 7-Tage-Schwelle fehlen.

---

## v3.21.0 — Energieprofil-Komfort & WP-Alternativvergleich (April 2026)

### Tage-Tabelle im Auswertung-Monat-Tab + aufklappbare Sektionen

Auswertung → Energieprofil → Monat hat jetzt eine prominente **Tage-Tabelle** als eigene Sektion: pro Tag eine Zeile mit Heatmap-Zellfarben, Negativpreis-Tage mit amber-Streifen + §51-Badge, sticky Σ-Monat-Footer mit Spalten-Aggregat. Alle Sektionen unter `<CollapsibleSection>` mit localStorage-Persistenz pro Anker. Issue [#148](https://github.com/supernova1963/eedc-homeassistant/issues/148).

→ [Bedienung §5.8 Energieprofil](HANDBUCH_BEDIENUNG.md#58-energieprofil-tab-beta)

### Pro-Tag-Reaggregation per Knopf

Selbsthilfe-Mechanismus für einzelne Tage mit offensichtlich falschen Werten: Refresh-Icon-Button am Ende jeder Tageszeile in der Energieprofil-Datenverwaltung. Klick → Confirmation → API-Aufruf → Reload. Statt manueller DB-Edit oder Vollbackfill. Wirkt auch in Auswertung → Energieprofile (Beta) → Monat (geteilte Komponente). Issue [#146](https://github.com/supernova1963/eedc-homeassistant/issues/146).

### Snapshot-Job-Toleranz & :55-Live-Preview

Stundenwerte zeigen nicht mehr gelegentlich „Stunde 0.00 + Folge-Spike" durch HA-Statistics-Latenz. Toleranz von 60 → 10 min reduziert (Stunden, die zur Zeit des :05-Jobs noch nicht in HA sind, werden vom späteren Self-Healing-Lauf nachgeholt statt mit dem Vorstunden-Wert beschrieben). Neuer :55-Job schreibt zusätzlich einen Live-Vorschau-Eintrag, damit die laufende Stunde zum Stundenende sofort sichtbar ist. Issue [#146](https://github.com/supernova1963/eedc-homeassistant/issues/146).

### WP-Alternativvergleich: Zusatzkosten + Monats-Gaspreis

Zwei Lücken im Gas-vs-WP-Vergleich geschlossen:

- Neuer Investitions-Parameter **`alternativ_zusatzkosten_jahr`** (€/Jahr) für Schornsteinfeger / Wartung / Gaszähler-Grundpreis — wird in allen Berechnungs-Stellen (Aussichten, HA-Export, PDF-Jahresbericht, Investitions-Vorschau) zu den Alt-Heizungs-Kosten addiert, in historischen Aggregaten anteilig pro erfasstem Monat.
- Neue optionale **`Monatsdaten.gaspreis_cent_kwh`**-Spalte (analog zu `kraftstoffpreis_euro` für Benzin): pro Monat gepflegt wird sie in der historischen Aggregation Monat für Monat verwendet, Fallback bleibt der Investitions-Parameter `alter_preis_cent_kwh`. Damit ändert ein Tarifwechsel nicht mehr rückwirkend die ganze Historie.

Issue [#141](https://github.com/supernova1963/eedc-homeassistant/issues/141).

→ [Berechnungen §3.5 WP-Einsparung](BERECHNUNGEN.md#35-wärmepumpe-einsparung)

### ROI-Sicht-Hinweise in allen Tooltips

Alle ROI-/Amortisations-Anzeigen (Cockpit, Investitionen-Tab, ROI-Dashboard, Aussichten-Finanzen) zeigen im Tooltip an, **welche Sicht** die Zahl darstellt — z. B. „Pro Investition · Jahres-ROI · Mehrkosten-Ansatz · Prognose" vs. „Gesamt-Anlage · IST-Werte · kumuliert". Adressiert die im Forum berichtete Verwirrung über mehrere parallele ROI-Werte.

---

## v3.20.x — Backward-Slot-Konvention & PR mit GTI (April 2026)

### Backward-Slot-Konvention für Stunden-Energie

OpenMeteo, Solcast und IST nutzen jetzt durchgängig **Slot N = Energie [N-1, N)** — Industriestandard (HA Energy Dashboard, SolarEdge, SMA, Fronius, Tibber). Vorher zeigten die drei Quellen unter demselben Slot-Label physikalisch unterschiedliche Zeitintervalle. Strompreis-Stunden bleiben Forward (`[N, N+1)`, industrieüblich für aWATTar/Tibber/EPEX). Issue [#144](https://github.com/supernova1963/eedc-homeassistant/issues/144).

> **Nach Update einmalig:** „Verlauf nachberechnen + überschreiben" auslösen, damit historische Stundenwerte umverteilt werden. Tagessummen bleiben konventionsunabhängig korrekt.

→ [Berechnungen §6b Energieprofil](BERECHNUNGEN.md#6b-energieprofil-berechnungen-tages-aggregation)

### Performance Ratio nutzt GTI statt GHI

Die PR-Formel berücksichtigt jetzt die **Global Tilted Irradiance** (auf die Modulfläche projiziert, kWp-gewichtet bei Multi-String-Anlagen) statt der horizontalen Globalstrahlung. Bei steilen Modulen und tiefstehender Wintersonne kann GTI 2–3× höher sein als GHI — vorher liefen PR-Werte im Winter auf physikalisch unmögliche 1.2–2.8. Issue [#139](https://github.com/supernova1963/eedc-homeassistant/issues/139).

### Snapshot-Lücken-Interpolation

Fehlt ein stündlicher Sensor-Snapshot, wird die Lücke jetzt **linear zwischen den Nachbar-Stunden interpoliert** statt das Gesamt-Delta in eine Stunde aufzustauen. Damit kein „Stunde-0 + Folge-Spike"-Muster mehr in den Stundenwerten. Issue [#145](https://github.com/supernova1963/eedc-homeassistant/issues/145).

---

## v3.19.0 — Energieprofil aus Zähler-Snapshots (April 2026)

### kWh-Werte aus kumulativen Zähler-Snapshots statt W-Integration

Die Stunden-kWh in den Tagesprofilen werden jetzt als **Differenz kumulativer Zählerstände** berechnet (Quelle: HA Long-Term-Statistics oder MQTT-Energy-Snapshots) statt aus 10-Min-`leistung_w`-Samples integriert. Drift-Reduktion von ~9 % auf ~0,1 %, validiert auf der Winterborn-Anlage über 538 Tage Backfill. Prognosen-IST, Lernfaktor und Heatmaps stimmen mit dem Live-Dashboard und der Zähler-Realität überein. Issue [#135](https://github.com/supernova1963/eedc-homeassistant/issues/135).

> **Empfohlene Aktion nach Update:** Einstellungen → Energieprofil → „Verlauf nachberechnen" mit aktiver „Überschreiben"-Option auslösen (1–5 Min Laufzeit), damit historische Tagesprofile aus den Zählern statt aus Leistungs-Schätzung stammen.

→ [Einstellungen §10 Energieprofile-Hintergrund](HANDBUCH_EINSTELLUNGEN.md#10-energieprofile--hintergrund)

### Daten-Checker: Neue Kategorie „Energieprofil – Zähler-Abdeckung"

Prüft pro Anlage und Komponente, welche kumulativen kWh-Zähler gemappt sind. Warnt mit konkreter Liste fehlender Zähler und verlinkt zum Sensor-Mapping-Wizard. Damit ist beim Onboarding sofort sichtbar, was für genaue Energieprofile noch fehlt.

### Live-Dashboard: Lite-Modus jetzt wirklich „lite"

Drei Performance-Verbesserungen am Energiefluss-Diagramm für iPad und Mobile-Safari: SMIL-Partikel-Animationen werden im Lite-Modus weggelassen, `filter`-Attribute der Knoten-Karten ebenso, der Hintergrund ist `React.memo`-gewrappt. Effekt-Modus bleibt unverändert. Forum-Bericht dietmar1968.

---

## v3.18.0 — Eigene Energieprofil-Seite (April 2026)

### Datenverwaltung pro Anlage

Neue Seite **Einstellungen → Energieprofil** bündelt die anlage-spezifischen Auswertungen und Datenverwaltungs-Aktionen. Datenbestand-Kacheln (Stundenwerte/Tagessummen/Monatswerte, Abdeckung, Zeitraum), Tages-Tabelle mit Jahr/Monat-Selektor und Spalten-Selektor in Gruppen (Peak-Leistungen, Tages-Summen, Performance, Wetter, §51-Börsenpreise). Aktionen: Vollbackfill aus HA-Statistik, Kraftstoffpreis-Backfill, Energieprofil-Daten löschen — anlage-spezifisch statt global. Tab-Konsolidierung: `Monatsabschluss` aus der Einstellungen-Tab-Leiste entfernt (Dropdown-Eintrag bleibt). Issue [#133](https://github.com/supernova1963/eedc-homeassistant/issues/133).

→ [Einstellungen §1.6 Energieprofil-Seite](HANDBUCH_EINSTELLUNGEN.md#16-energieprofil-seite)

---

## v3.17.0 — Echte monatliche Benzinpreise (April 2026)

### Dynamische Kraftstoffpreise für E-Auto-ROI

Statt statischem `benzinpreis_euro`-Parameter werden jetzt **echte monatliche Kraftstoffpreise aus dem EU Weekly Oil Bulletin** verwendet. Neues Feld `Monatsdaten.kraftstoffpreis_euro` (€/L) mit automatischem Vorschlagswert im Monatsabschluss-Wizard. ROI-Berechnung (Aussichten), HA-Sensor-Export und PDF-Finanzbericht nutzen pro Monat den echten Preis — Fallback auf den statischen Parameter wenn kein Monatswert vorhanden. Backfill-Endpoint befüllt Monatsdaten rückwirkend (Oil Bulletin History seit 2005).

> **Hinweis:** Die E-Auto-Ersparnis kann sich gegenüber früheren Versionen verändern — nach oben oder unten, je nachdem ob der reale Preis über oder unter dem konfigurierten Wert lag.

→ [Einstellungen §1.4 Monatsdaten](HANDBUCH_EINSTELLUNGEN.md#14-monatsdaten)

---

## v3.16.x — Dynamischer Strompreis & Solcast-Prognosen (April 2026)

### Solcast PV Forecast — Neuer Prognosen-Tab *(v3.16.4–v3.16.8)*

Neuer Tab **„Prognosen"** in Aussichten als Evaluierungs-Cockpit für das Zusammenspiel von OpenMeteo, eedc (kalibriert mit Lernfaktor), Solcast und IST. KPI-Matrix Heute/Morgen/Übermorgen mit VM/NM-Split, Stundenprofil-Chart mit p10/p90-Konfidenzband, 24h- und 7-Tage-Vergleichstabellen, Genauigkeits-Tracking. Solcast wird über einen Toggle im Sensor-Mapping-Wizard aktiviert — entweder API-Zugang (Free/Paid) oder via HA-Integration BJReplay. L1/L2-Cache überlebt Neustarts.

→ [Bedienung §7.2 Prognosen](HANDBUCH_BEDIENUNG.md#72-prognosen)

### Dynamischer Strompreis — Sensor-Mapping + EPEX-Börsenpreis *(v3.16.0)*

Neues optionales Feld **„Strompreis (dynamischer Tarif)"** im Sensor-Mapping unter Basis-Sensoren — Tibber, aWATTar, EPEX oder eigener Template-Sensor zuordnen. EPEX Day-Ahead-Preise (DE/AT) werden zusätzlich automatisch via aWATTar-API geholt — als Overlay im Tagesverlauf, auch ohne eigenen Sensor. MQTT-Topic `eedc/{id}/live/strompreis_ct` für Standalone-Docker-Nutzer.

→ [Einstellungen §3 Sensor-Mapping](HANDBUCH_EINSTELLUNGEN.md#3-sensor-mapping)

### Saisonaler Lernfaktor (MOS-Kaskade) *(v3.16.15)*

Der Lernfaktor nutzt jetzt eine saisonale Kaskade: **Monatsfaktor** (≥15 Tage gleicher Kalendermonat) → **Quartalsfaktor** (≥15 Tage) → **30-Tage-Fenster** (≥7 Tage, bisheriges Verhalten). Bei wachsendem Datenbestand wird die Kalibrierung automatisch präziser. Im Prognosen-Tab wird die aktive Stufe angezeigt.

→ [Berechnungen §4.1c Prognose-Genauigkeit](BERECHNUNGEN.md#41c-prognose-genauigkeit-mae-mbe-asymmetrie)

### Stündliche Strompreis-Mitschrift im Energieprofil

Zwei getrennte Preisfelder pro Stunde: **`strompreis_cent`** (Endpreis aus HA-Sensor) und **`boersenpreis_cent`** (EPEX, immer befüllt). Tagesaggregation mit Negativpreis-Zählung und Einspeisung bei negativem Börsenpreis (§51 EEG). Datengrundlage für künftige Negativpreis-Auswertungen.

### Investitionsformular verschlankt — Stammdaten in Infothek *(v3.16.2)*

Geräte-Stammdaten (`stamm_*`), Ansprechpartner (`ansprechpartner_*`) und Wartungsvertrag (`wartung_*`) sind aus dem Investitionsformular verschwunden — alle diese Daten werden jetzt über die **Infothek** verwaltet (N:M-Verknüpfung Datenblatt ↔ Investition). Beim Bearbeiten einer Investition erscheinen verknüpfte Infothek-Einträge als kompakte Liste mit Direktlink. PDF-Jahresbericht entsprechend bereinigt.

→ [Infothek-Handbuch](HANDBUCH_INFOTHEK.md)

---

## Ältere Versionen

Für Versionen vor v3.16 — siehe [CHANGELOG](https://github.com/supernova1963/eedc-homeassistant/blob/main/CHANGELOG.md) auf GitHub.

Wichtige Meilensteine als Stichworte: Live Dashboard + MQTT-Inbound (v3.0), GTI-Prognose (v3.3), Wettermodell-Kaskade (v3.4), Infothek-Modul Etappe 1 (v3.5), L1/L2-Cache (v3.7), Live-Dashboard-Generalüberholung (v3.9), Import-Strategie (v3.10), Aktueller Monat → Monatsberichte (v3.12), Energieprofil-Monatsauswertung (v3.13), Stilllegungsdatum (v3.14), PDF-Anlagendokumentation + Finanzbericht (v3.15).

---

## Weitere Quellen

- **Vollständiger CHANGELOG (technisch):** [CHANGELOG.md auf GitHub](https://github.com/supernova1963/eedc-homeassistant/blob/main/CHANGELOG.md) — alle Bugfixes und Code-Änderungen, auch die nicht-anwender-sichtbaren.
- **GitHub-Releases:** [supernova1963/eedc-homeassistant/releases](https://github.com/supernova1963/eedc-homeassistant/releases) — versionsweise gebündelt mit Zusammenfassung.
- **Issues und Discussions:** [supernova1963/eedc-homeassistant](https://github.com/supernova1963/eedc-homeassistant) — Bugs melden, Features anfragen, Diskussionen mitlesen.
- **Online-Dokumentation:** [supernova1963.github.io/eedc-homeassistant](https://supernova1963.github.io/eedc-homeassistant/) — Web-Variante derselben Hilfe, gut zum Verlinken in Foren.
