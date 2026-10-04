# eedc Handbuch — Wärme & Klima

> Dieses Handbuch ist Teil der eedc-Dokumentation.
> Siehe auch: [Bedienung](HANDBUCH_BEDIENUNG.md) | [Einstellungen & Datenquellen](HANDBUCH_EINSTELLUNGEN.md) | [Daten-Checker](HANDBUCH_DATEN_CHECKER.md) | [Berechnungen & Kennzahlen](BERECHNUNGEN.md) | [Sensor-Referenz](SENSOR-REFERENZ.md) | [Glossar](GLOSSAR.md)

---

## Inhaltsverzeichnis

1. [Was diese Fläche umfasst](#1-was-diese-fläche-umfasst)
2. [Voraussetzungen — welcher Zähler für welche Anzeige](#2-voraussetzungen--welcher-zähler-für-welche-anzeige)
3. [Was eedc bewusst *nicht* sagt](#3-was-eedc-bewusst-nicht-sagt)
4. [Wann eine Kennzahl verschwindet — und warum das richtig ist](#4-wann-eine-kennzahl-verschwindet--und-warum-das-richtig-ist)
5. [Sensoren zuordnen, Schritt für Schritt](#5-sensoren-zuordnen-schritt-für-schritt)
6. [Sieben Anlagen, sieben Ergebnisse](#6-sieben-anlagen-sieben-ergebnisse)
7. [Verteilung und Verlauf — wohin der Strom gegangen ist](#7-verteilung-und-verlauf--wohin-der-strom-gegangen-ist)
8. [Häufige Missverständnisse](#8-häufige-missverständnisse)

---

## 1. Was diese Fläche umfasst

In eedc heißt der Bereich **„Wärme/Klima"**. Er umfasst **jedes Gerät, das Strom in Wärme oder Kälte verwandelt** — unabhängig davon, wie es heißt:

- Luft-Wasser-, Sole-Wasser- und Grundwasser-Wärmepumpen
- Split-Klimaanlagen (Luft-Luft), auch als Multisplit mit mehreren Innengeräten
- Brauchwasser-Wärmepumpen, die ausschließlich Warmwasser machen
- Heizstäbe, Zusatz- und Notheizungen — als **Teil** der Anlage, nicht als eigenes Gerät

> **Alle diese Geräte legst du als Investition vom Typ *Wärmepumpe* an.** Die **Wärmepumpenart** (Luft-Wasser, Sole-Wasser, Grundwasser, Luft-Luft, Brauchwasser) ist eine Angabe *am* Gerät, kein eigener Investitionstyp. Sie steuert vor allem, **welche Felder eedc dir anbietet und welche es erwartet** — nicht, was du erfassen darfst.

### Der Grundsatz: der Zähler entscheidet, nicht die Bauart

Bis v4.0.28 hing die Frage, welche Größen ein Gerät haben *kann*, an seiner Bauart. Eine Kühl-Achse gab es nur an Luft-Luft-Geräten; wer an einer Luft-Wasser-Wärmepumpe einen getrennten Kühlzähler hatte, konnte ihn **nirgends** eintragen.

**Seit v4.0.29 gilt umgekehrt: Was du messen kannst, kannst du auch zuordnen.** Die Bauart schlägt nur noch *vor*, welche Felder oben stehen. Alles andere liegt unter dem zugeklappten Abschnitt **„Weitere Größen erfassen"** und rückt nach oben, sobald du dort einen Sensor einträgst.

Das hat einen Preis, den du kennen solltest: **eedc kann nicht wissen, ob dein Gerät etwas nicht tut oder ob du es nur nicht misst.** Genau deshalb steht in [§4](#4-wann-eine-kennzahl-verschwindet--und-warum-das-richtig-ist) bei jeder fehlenden Kennzahl ein Grund statt einer geschätzten Zahl.

### Wo die Fläche in der App erscheint

| Ort | Was dort steht |
|-----|----------------|
| **Cockpit → Live** | Momentanleistung gesamt und je Funktion, Betriebsmodus, Warmwasser-Temperatur |
| **Cockpit → Tag** | Block *Wärme/Klima*: Arbeitszahl (auch je Funktion und für das **Kühlen**, sobald ein Kältemengenzähler zugeordnet ist — am Gerät oder je Innengerät), Wärme, Strom, Kompressor-Starts, die **Liste je Funktion** und die Betriebsart-Aufteilung — **alles tagesgenau**. Dazu ein **Verlauf je Stunde**: Strom nach Betriebsart gestapelt, gemessene Wärme als Linie, mit Kältemengenzähler die **gemessene Kälte als eigene Linie**, Außentemperatur auf der zweiten Achse. Jedes Gerät bleibt dabei in seinen eigenen Stunden. Die Stunden ergeben zusammen genau die Aufteilung darunter; was sich keiner Stunde zuordnen lässt, steht darunter als *„Strom / Wärme / Kälte ohne Stundenzuordnung"*; eine Arbeitszahl je Stunde gibt es bewusst nicht (Wärme und Strom derselben Stunde gehören nicht zusammen). Mit **getrennten Stromzählern für Heizen und Warmwasser** schaltet ein Wähler über dem Verlauf zwischen *nach Betriebsart* und *nach Funktion* um — nie beides zugleich, weil Betriebsarten Ausschnitte und Funktionen Summanden des Stroms sind; der Titel nennt die gerade gestapelte Größe. Im **Stundenverlauf** des Tages (dem Butterfly-Chart darüber, nicht in diesem Block) erscheint die Wärmepumpe getrennt nach *Heizen* und *Warmwasser*, wenn du beide **Leistungs**-Sensoren zugeordnet hast **und** *Leistung gesamt* leer bleibt — dieselben zwei Flächen wie in *Cockpit → Live* ([Schritt 6](#schritt-6--live-werte-optional)) |
| **Cockpit → Monat** | derselbe Block auf Monatsbasis, dazu die Arbeitszahlen je Funktion und ein **Verlauf je Tag** (dieselbe Darstellung wie am Tag, mit Kälte-Linie) |
| **Cockpit → Jahr** | Jahressummen, dieselben Kennzahlen wie im Monat — Arbeitszahl mit Grund und Heizstab-Satz, je Funktion, Kühlen, Aufteilung nach Betriebsart mit Restmenge — über das Jahr **neu gerechnet** (nicht gemittelt), ein **Verlauf je Monat** (Strom, gemessene Wärme und Kälte), Block *CO₂-Bilanz* |
| **PDF-Jahresbericht** | dieselben Kennzahlen wie *Cockpit → Jahr* aus derselben Rechnung — Arbeitszahl mit Grund, je Funktion, Kühlen, Herkunft einer geschätzten Wärme, Vorbehalt an der CO₂-Zeile (seit 05.09.2026; vorher stand dort eine Arbeitszahl ohne Grund und nichts je Funktion) |
| **Auswertungen → CO₂ · Cockpit → Jahr (CO₂-Bilanz) · PDF-Monatsbericht** | die CO₂-Einsparung der Wärmepumpe trägt denselben Vorbehalt wie die Ersparnis, wenn die Wärme geschätzt ist oder ein zweiter Erzeuger am Wärmezähler hängt; der Monatsbericht nennt die Herkunft einer geschätzten Wärme mit denselben Worten wie der Hub (seit 05.09.2026) |
| **Komponenten → Wärmepumpe** | je Gerät einzeln: Status, Verlauf, Monats-/Saisonvergleich, Kostenvergleich gegen Gas/Öl |
| **Auswertungen → CO₂** | Einsparung inkl. Wärmepumpen-Anteil |
| **Einstellungen → Datenquellen** | die Zuordnung der Zähler ([§5](#5-sensoren-zuordnen-schritt-für-schritt)) |

> **Im Verlauf steht nur gemessene Wärme.** Ist die Wärme aus Strom × Arbeitszahl geschätzt, hätte
> ihre Linie genau die Form der Stromfläche darunter — sie sähe aus wie eine zweite Messung und
> sagte nichts. Die geschätzte Menge steht weiterhin in der Kachel, mit ihrer Herkunft daneben.
> **Die Kälte** ist immer gemessen (es gibt keinen Weg, sie zu schätzen) und steht als **eigene Linie
> in eigener Farbe** — nie in der Wärme. Du siehst sie, sobald ein Kältemengenzähler zugeordnet ist, am
> Gerät oder je Innengerät.

> **Die Liste „Je Funktion"** im Block *Wärme/Klima* (Cockpit → Tag, Monat, Jahr) stellt je Funktion
> beisammen, woraus ihre Arbeitszahl entsteht: *Heizen* — Strom Heizen, Heizwärme, Arbeitszahl;
> *Warmwasser* — Strom Warmwasser, Warmwasser-Wärme, Arbeitszahl; *Kühlen* — Strom Kühlen, **Kälte**,
> Arbeitszahl. Eine Überschrift steht nur bei einer Funktion mit einer Menge; eine Funktion, die dein
> Gerät nicht hat (Warmwasser an einer Split-Klima, Kühlen im Winter), bleibt eine einzelne Zeile mit
> ihrem Grund. **Zwei Mengen „Heizen" sind nicht dasselbe:** Die Liste zeigt die **Funktion** (dein
> getrennt gemessener Heizstrom), der Balken darunter die **Betriebsart** — die Betriebsart „Heizen"
> enthält den Warmwasser-Strom, solange Warmwasser keine eigene Betriebsart ist. Wo beides zu sehen ist,
> heißt der Balken deshalb *„Strom-Aufteilung nach Betriebsart"*. Wer die Liste parkt, parkt Wärme und
> Kälte je Funktion mit.

> **Der Block *Wärme/Klima* im Cockpit fasst alle Geräte zusammen**, der Komponenten-Hub zeigt sie **einzeln**. Das ist kein Widerspruch, sondern der wichtigste Unterschied auf dieser Fläche — siehe [§8](#8-häufige-missverständnisse).

---

## 2. Voraussetzungen — welcher Zähler für welche Anzeige

Diese Tabelle ist der Kern dieses Handbuchs. Sie beantwortet die Frage, die fast alle Rückfragen auslöst: **„Warum steht da ein Strich?"**

| Was du sehen willst | Was du dafür brauchst | Ohne das … |
|---------------------|------------------------|------------|
| **Stromverbrauch** der Anlage | *Stromverbrauch* (kWh) — **oder** *Strom Heizen* + *Strom Warmwasser* bei getrennter Messung | keine Auswertung, das Gerät fehlt in der Verbrauchsseite |
| **Wärme erzeugt** | Wärmemengenzähler: *Heizwärme* (kWh) und/oder *Warmwasser-Wärme* (kWh) | eedc **rechnet** sie aus Strom × gepflegter Arbeitszahl — und kennzeichnet sie als abgeleitet — im Komponenten-Hub und unter *Cockpit → Monat/Jahr* steht die Herkunft unter der Wärme-Kachel („geschätzt: Strom × JAZ 3,5"), und Ersparnis wie CO₂ tragen den Vorbehalt „Wärme geschätzt" |
| **Arbeitszahl (JAZ)** | beides: Strom **und** gemessene Wärme | „—" mit Grund |
| **Arbeitszahl Heizen / Warmwasser getrennt** | getrennte Strommessung **und** getrennte Wärmemengen | „—" mit Grund *„Strom nicht getrennt je Funktion gemessen"* — **außer** dein Gerät hat nur eine der beiden Funktionen, dann steht dort seine Gesamtzahl (s. Lage F) |
| **Arbeitszahl Kühlen** | *Strom Kühlbetrieb* **und** *Nutzenergie Kühlbetrieb* (Kältemengenzähler) | „—" mit Grund *„kein Kältemengenzähler zugeordnet"* |
| **Aufteilung Heizen/Kühlen/Lüften/Entfeuchten** | entweder **gemessene** Betriebsart-Zähler **oder** ein *Betriebsmodus*-Sensor, den eedc laufend mitliest | der Block fehlt ganz — und zwar bewusst, statt vier Nullen zu zeigen |
| **Ersparnis vs. Alternative** | gemessene oder abgeleitete Wärme **und** ein Alt-Preis am Gerät | die Kachel erscheint gar nicht. ⚠ In *Cockpit → **Tag*** gibt es sie **nie**: eedc rechnet die Ersparnis monatsweise, weil die Zusatzkosten der Altanlage Monatsgrößen sind. Der Monat und das Jahr zeigen sie |
| **CO₂-Einsparung** | Stromverbrauch und Wärme | der Wärmepumpen-Anteil fehlt in der Bilanz |
| **Kompressor-Starts / Betriebsstunden** | ein *Total-Increasing*-Zähler dafür | die Kacheln erscheinen gar nicht |
| **Tages**werte statt nur Monatswerte | dieselben Zähler — aber **fortlaufend mitgeschrieben** | „—" mit Grund, siehe Kasten |

> ⚑ **Der Strom der Wärmepumpe wird immer voll gerechnet, auch der Teil aus der eigenen PV — dessen Wert steht auf der PV-Seite als Eigenverbrauch.** Sonst zählte dieselbe Kilowattstunde zweimal.

> ### ⚠ Monat da, Tag leer — das ist der häufigste Fall und kein Fehler
>
> Monats- und Tageswerte kommen aus **zwei verschiedenen Quellen**:
>
> - Der **Monatswert** kann aus der **Langzeitstatistik von Home Assistant** kommen. Die reicht Monate zurück — auch für einen Sensor, den du gerade erst zugeordnet hast.
> - Der **Tageswert** entsteht aus **Zählerständen, die eedc selbst mitschreibt**, jeweils zum Tagesanfang und Tagesende. Die gibt es erst **ab dem Zeitpunkt der Zuordnung**.
>
> Deshalb kann *Cockpit → Monat* eine Wärmemenge zeigen, während *Cockpit → Tag* für dieselbe Anlage noch „—" sagt. **eedc schreibt das seit v4.0.29 hin:** *„Zähler zugeordnet, aber für diesen Tag liegen keine Zählerstände vor."*
>
> **Was du tun kannst:** Frühere Tage lassen sich über die **Reparatur-Werkbank** nachrechnen (*Einstellungen → Daten → Tag neu berechnen*). Oder du wartest — ab morgen entstehen die Werte von selbst.

> ### ⭐ Der erste Tag und der heutige — was du seit v4.0.45 siehst
>
> Ein Tageswert entsteht aus **zwei** Zählerständen: einem zum Tagesanfang, einem zum Tagesende.
> An zwei Tagen fehlt davon einer, und beide Tage sind der Normalfall:
>
> | Wann | Was fehlt | Was eedc jetzt tut |
> | --- | --- | --- |
> | **Der erste Tag nach der Zuordnung** | der Stand um 0 Uhr — eedc hat erst ab 11:30 mitgeschrieben | misst **ab dem ersten Stand** und schreibt *„gemessen ab 11:30 Uhr"* unter die Strom-Kachel |
> | **Heute** | der Stand um 24 Uhr — der Tag läuft noch | misst **bis zum letzten Stand**: *„gemessen bis 05:00 Uhr"* |
>
> **Bis v4.0.44 blieb an beiden Tagen alles leer** — keine Zahlen je Gerät, keine Arbeitszahl, keine
> Aufteilung —, obwohl die Zählerstände längst da waren. Dass die Anzeige darüber trotzdem eine
> Strommenge nannte, machte es nicht besser: Daneben stand *„kein Stromverbrauch erfasst"*.
>
> ⛔ **Hochgerechnet wird nichts.** Die Zahl ist die Menge des **gemessenen** Zeitraums, nicht eine
> auf 24 Stunden gestreckte Schätzung — deshalb steht die Uhrzeit daneben. Und **liegt an einem Tag
> gar kein Stand vor**, bleibt es beim bisherigen Satz: dann gibt es wirklich nichts zu messen.
>
> ⚠ **Ein Zähler, der an diesem Tag zurückgesprungen ist, bekommt den Rückfall nicht** — eedc sagt
> dort weiterhin nichts, statt eine kleinere, ebenso falsche Zahl zu bilden.

### Kumulativ oder Tageszähler — beides geht

eedc erwartet **fortlaufend steigende Zählerstände** („total increasing"). Ein Sensor, der jede Nacht auf 0 zurückspringt (`utility_meter` mit Tages-Zyklus), funktioniert über Home Assistant trotzdem: Dort liest eedc die reset-bereinigte Summe, nicht den Rohwert.

⚠ **Auf dem MQTT-/Standalone-Pfad gilt das nicht** — dort kommt der rohe veröffentlichte Wert an. Springt er zurück, erkennt eedc das und sagt für diesen Tag **nichts**, statt eine falsche Zahl zu bilden: *„Der Zähler ist an diesem Tag zurückgesprungen."*

---

> ⚑ **„Alternative" ist die Heizung, die du ersetzt hast** — am Gerät gepflegt als *Gas*, *Öl*
> oder *Strom (Direktheizung)*. eedc rechnet mit dem Wirkungsgrad des jeweiligen Trägers (0,90 ·
> 0,85 · 1,00) und mit deinem Preis. Bis 4.0.43 stand über der Zahl unbedingt „vs. Gas", auch wenn
> du Öl gepflegt hattest — die Rechnung stimmte, die Beschriftung nicht. Wo mehrere Wärmepumpen in
> **einer** Zahl zusammengefasst sind, kann sie ohnehin keinem einzelnen Träger folgen.

## 3. Was eedc bewusst *nicht* sagt

Dieser Abschnitt ist so wichtig wie die Tabelle darüber. **Mehrere Dinge fehlen mit Absicht** — sie zu ergänzen wäre eine Verschlechterung, keine Verbesserung.

**Kein „SEER".** Für den Kühlbetrieb bildet eedc die **Arbeitszahl Kühlen** = Kältemenge ÷ Kühlstrom. Sie heißt **nicht** SEER, obwohl es naheläge: SEER ist eine genormte Größe, die auf einem Prüfstand unter festgelegten Bedingungen ermittelt wird. Was eedc bilden kann, ist das Verhältnis deiner beiden Zähler über einen Zeitraum. Sie „SEER" zu nennen würde eine Vergleichbarkeit mit dem Datenblatt behaupten, die sie nicht hat.

**Keine geschätzte Kältemenge.** Ohne Kältemengenzähler gibt es keine Arbeitszahl Kühlen. Man könnte sie aus einem angenommenen Wirkungsgrad rechnen — dann käme genau der Faktor zurück, mit dem gerechnet wurde. Das wäre keine Messung, sondern eine Rückgabe der eigenen Annahme.

**Keine Bewertung von Lüften und Entfeuchten.** Beide Betriebsarten **erscheinen** in der Aufteilung, wenn du dafür Zähler hast. Eine Kennzahl bekommen sie nicht: Sie erzeugen keinen Nutzen, den eedc bewerten könnte. Ihr Strom fällt deshalb auch **aus dem Nenner der Arbeitszahl** — sonst drückte er eine Zahl, mit der er nichts zu tun hat. ⭐ **Misst du zusätzlich ihre abgegebene Nutzenergie** (*Nutzenergie Lüftbetrieb* / *Nutzenergie Entfeuchtungsbetrieb*), steht sie seit v4.0.45 als eigene **Mengenzeile** neben ihrem Strom — im Komponenten-Hub und im Wärme/Klima-Block von Cockpit → Monat/Jahr, und nur dann, wenn ein Zähler etwas gemeldet hat. **An der Kennzahl ändert das nichts**, und in eine Wärmesumme zählt sie nicht: Ein Zähler macht aus Lüften keine Heizung.

> ⚑ **Die Kachel zeigt, womit sie gerechnet hat.** Wer auf die Arbeitszahl zeigt (auf dem Telefon: antippen), sieht neben der Formel die beiden eingesetzten Zahlen — *„210,0 kWh Wärme ÷ 313,6 kWh Strom"*. Damit lässt sich eine unplausible Zahl sofort einordnen: Passt eine der beiden nicht zu dem, was dein Gerät meldet, liegt es an der Zuordnung, nicht an der Rechnung. ⚠ **Der Nenner ist nicht immer der volle Stromverbrauch** — Kühlen, Lüften und Entfeuchten sind abgezogen, wenn du den Betriebsmodus erfasst (sonst stünde Kühlstrom im Nenner, ohne dass die Kältemenge im Zähler steht). ⭐ **Dasselbe gilt in der Monatstabelle** unter *Komponenten → Wärmepumpe*: Wo die Arbeitszahl eines Monats mit anderen Zahlen gebildet wurde als in seiner Zeile stehen, steht die Rechnung klein darunter — „210 ÷ 96 kWh“. Wo Zähler und Nenner die Spalten daneben sind, geht die Zeile ohne Zusatz auf, und es steht nichts da.

**Keine Note für deine Anlage.** eedc rechnet mit deinen Zahlen, es bewertet dich nicht. Eine Arbeitszahl von 1,8 ist kein Mangel, sondern die Beschreibung einer Anlage, die viel direkt elektrisch heizt. Steht sie unter 2, schreibt eedc genau das daneben:

> *„Eine Arbeitszahl nahe 1 entsteht, wenn ein großer Teil der Wärme direkt elektrisch erzeugt wurde (Heizstab, Zusatz- oder Notheizung). Die Zahl beschreibt die Anlage in diesem Zeitraum, sie ist kein Fehler."*

**Keine 0, wo „unbekannt" gemeint ist.** Eine 0 heißt „gemessen und es war null". Wo eedc etwas nicht weiß, steht „—" **mit dem Grund daneben** — nie eine Null, die wie eine Messung aussieht. ⚑ **In den Tabellen steht dieser Grund sichtbar unter der Tabelle**, einmal je Grund statt in jeder Zeile — er folgt meist aus deiner Anlagenkonfiguration und wiederholt sich sonst über alle Monate. Ein Hinweis, den man erst suchen muss, ist keine Auskunft: Niemand tippt auf eine leere Zelle, um dort eine Erklärung zu vermuten.

**Kein Vergleich von passiv gegen aktiv gekühlt.** Passive Kühlung läuft nur über Umwälzpumpen und erreicht ein Vielfaches der Effizienz einer aktiv gekühlten Anlage. Beide Zahlen sind für sich richtig; sie gegeneinander zu stellen wäre die Falschaussage. Deshalb gibt es am Gerät das Feld **„Kühlung: aktiv oder passiv"** — es ändert **keine** deiner Zahlen, es hält dich nur aus dem falschen Vergleich heraus.

**Keine erfundene Stunde.** Der Verlauf je Stunde in *Cockpit → Tag* zeigt **gemessene** Mengen, aber er misst nicht jede Stunde für sich: Er nimmt den Tageswert und verteilt ihn nach der **Form** der Stunden — jede Stunde bekommt den Anteil, den dein Zähler an diesem Tag dort getragen hat. Das ist der Grund für die beiden Eigenschaften aus [§1](#1-was-diese-fläche-umfasst): dass die 24 Stunden zusammen immer genau den Balken darunter ergeben, und dass eine Menge ohne Stundenform lieber genannt als umgelegt wird. Läuft alles über Home Assistant, stammen Tageswert und Stundenform aus **derselben** Zählerreihe im selben Zeitfenster; die Verteilung ist dort rechnerisch dasselbe wie eine Stundenmessung. Auf dem MQTT-/Standalone-Pfad und überall dort, wo einer Stunde ein Zählerstand fehlt, bleibt es eine Verteilung — geglättet wird trotzdem nichts, denn eine über den Tag geschmierte Kurve wäre eine erfundene Form, keine Auskunft.

---

## 4. Wann eine Kennzahl verschwindet — und warum das richtig ist

**Eine Arbeitszahl ist Wärme ÷ Strom. Sie ist nur dann eine Aussage, wenn Zähler und Nenner dasselbe meinen** — dieselbe Anlage, dieselbe Funktion, denselben Zeitraum. Wo das nicht gesichert ist, lässt eedc die Zahl weg und schreibt den Grund hin.

Das ist die unangenehmste Eigenschaft dieser Fläche und zugleich ihre wichtigste. **Eine plausible falsche Zahl ist schlimmer als ein ehrlicher Strich** — sie landet im Jahresbericht, im Community-Vergleich und in deiner Entscheidung über die nächste Investition.

> ### ⭐ Seit v4.0.45: die Zahl der **Anlage** verschwindet nicht mehr, sie sagt „mindestens"
>
> Zwei Dinge, die man auseinanderhalten muss:
>
> * **Die Arbeitszahl EINES Geräts** — *„diese Wärmepumpe hat 3,75"*. Sie
>   verschwindet weiterhin, sobald Zähler und Nenner nicht dasselbe meinen. Alles
>   unten in diesem Kapitel gilt für sie unverändert.
> * **Die Zahl der ganzen Anlage** — *„wie effizient erzeugt dieses Haus Wärme?"*.
>   Sie teilt alle gemessene Wärme durch allen Strom deiner Wärmeerzeuger (ohne
>   den Kühlstrom). Steckt darin Strom, dem **keine** gemessene Wärme
>   gegenübersteht — deine Klimaanlage heizt mit, ein Heizstab läuft mit —, dann
>   ist das Ergebnis **zu klein** und nie zu groß. eedc zeigt es dann als
>   **Mindestwert: „≥ 3,25"**, mit dem Satz *„Klimaanlage: Strom ohne
>   Wärmemessung enthalten"* darunter.
>
> **Warum das keine Aufweichung ist:** Ein Mindestwert ist eine **wahre**
> Aussage. Vorher stand an derselben Stelle ein Strich mit dem Satz *„Wärmepumpe
> und Klimaanlage in einer Zahl"* — richtig, aber als Auskunft ärmer, denn die
> Zahl ist ja bekannt, nur eben nach unten verschoben. **Die Zahl deiner
> Wärmepumpe steht daneben**, in der Tabelle *Zahlen je Gerät* im selben Block.
>
> ⛔ **In die andere Richtung gibt es keinen Mindestwert.** Wenn ein Gerät
> **Wärme** beisteuert, ohne dass sein Strom mitgezählt wird, wäre die Zahl zu
> **groß** — dort bleibt es beim Strich und beim Grund. Dasselbe gilt für deine
> eigene Angabe *Fremdanteil auf den Zählern* und für versetzte Messzeiträume.

> ### ⭐ Und seit v4.0.45 steht jeder Grund nur noch EINMAL auf der Seite
>
> Bis dahin bekam jede fehlende Kennzahl ihre eigene Kachel mit „—" und
> demselben Satz darunter — ein einziger fehlender Zähler erzeugte bis zu vier
> gleichlautende Zeilen. Jetzt gilt:
>
> * **Was deine Ausstattung nicht hergibt** (kein Kältemengenzähler, keine
>   getrennte Strommessung, ein gemeinsamer Wärmemengenzähler …) steht **einmal**
>   am Ende des Blocks im Kasten **„Was noch möglich wäre"** — mit dem Handgriff
>   daneben und dem Weg dorthin. Die Kachel dazu erscheint gar nicht erst.
> * **Was deine Ausstattung hergibt, aber in diesem Zeitraum leer war** (die
>   Arbeitszahl Heizen im Juni) bleibt als **„—" ohne Text** stehen. Es gibt
>   nichts zu tun, und ein Satz daneben legte das Gegenteil nahe.
>
> ⭐ **Und der Grund ist trotzdem da — eine Geste entfernt:** Fährst du mit der
> Maus über so einen Strich (auf dem Telefon: antippen und halten), nennt er
> ihn — *„kein Heizbetrieb in diesem Zeitraum"*. Die Auskunft geht also nicht
> verloren, sie drängt sich nur nicht auf.
>
> Der Kasten ist aufgeklappt, einklappbar und wie jedes Element des Blocks
> parkbar. Die Tabelle unten gilt unverändert — sie sagt, **welcher** Satz wann
> erscheint; neu ist nur, **wo** er steht.

### Die Gründe, wörtlich

| Grund in der App | Was dahintersteckt | Was du tun kannst |
|------------------|--------------------|-------------------|
| **kein Stromverbrauch erfasst** | Für den Zeitraum liegt kein Strom vor. | Zähler zuordnen oder Monatswert pflegen |
| **kein Wärmemengenzähler zugeordnet** | Es gibt keine gemessene Wärme. | Zähler zuordnen — oder die gepflegte Arbeitszahl nutzen (dann ist die Wärme *abgeleitet*) |
| **kein Heizbetrieb in diesem Zeitraum** | Der Wärmemengenzähler ist zugeordnet und meldet für den Zeitraum **null** — das Gerät hat schlicht nicht geheizt. Typisch für einen Sommertag: Auf dem Stromzähler steht trotzdem etwas, das ist Standby und Umwälzung. | nichts, das ist die Wahrheit über den Tag. **Nicht mit *kein Wärmemengenzähler zugeordnet* verwechseln** — dort fehlt die Messung, hier ist sie da und sagt null |
| **keine Warmwasserbereitung in diesem Zeitraum** | Dasselbe für den Warmwasserkreis. | dito |
| **kein Kühlbetrieb in diesem Zeitraum** | Gegenstück auf der Kühlseite: Der Kühlstrom ist null, es gab keinen Kühlbetrieb. | nichts, das ist die Wahrheit über einen Wintermonat |
| **Wärme ist gerechnet, nicht gemessen** | Die Wärme kam aus *Strom × Arbeitszahl*. Sie durch denselben Strom zu teilen gäbe genau die Arbeitszahl zurück, mit der gerechnet wurde. | nichts — die Zahl wäre zirkulär |
| **nur Kühlbetrieb in diesem Zeitraum** | Der Zähler lief, aber nicht fürs Heizen. „Kein Stromverbrauch" wäre hier die falsche Auskunft. | nichts, das ist die Wahrheit über einen Sommermonat |
| **Wärmepumpe und Klimaanlage in einer Zahl** | Der Block fasst eine klassische Wärmepumpe und eine Split-Klimaanlage zusammen. Beide heizen, aber sie sind nicht vergleichbar: andere Nutzenergie, anderer Maßstab. Eine gemeinsame Arbeitszahl wäre ein Quotient aus zwei Welten. | jedes Gerät einzeln im Komponenten-Hub ansehen — dort hat jedes seine eigene Zahl |
| **nicht alle Geräte melden Wärme** | Der Block fasst mehrere Geräte zusammen; im Nenner steht der Strom von allen, im Zähler die Wärme von einem. | einzelnes Gerät im Komponenten-Hub ansehen |
| **Wärme und Strom stammen von verschiedenen Geräten** | Die Gegenrichtung: Ein Gerät steuert Wärme bei, ohne dass sein Strom im Nenner steht — die Zahl wäre zu **hoch**. Der Satz erscheint auch dann, wenn beide Seiten gleich viele Geräte tragen; entscheidend ist, ob es **dieselben** sind. | einzelnes Gerät im Komponenten-Hub ansehen — dort steht je Gerät, welche Seite fehlt. Hängen mehrere Geräte an **einem** Zähler, erfasse sie als **ein** Gerät ([Schritt 1](#schritt-1--gerät-anlegen-und-die-bauart-wählen)) |
| **Wärme und Strom stammen aus verschiedenen Monaten** | Dieselbe Störung über die **Zeit** statt über die Geräte: Ein Monat trägt Wärme ohne Strom, ein anderer trägt Strom — die Jahressumme nimmt beide mit. Typisch, wenn der Stromzähler erst mitten im Jahr in Betrieb ging. | die fehlenden Monatswerte nachpflegen — oder einen Zeitraum wählen, in dem beide Seiten gemessen sind |
| **Nutzenergie und Strom dieser Funktion stammen von verschiedenen Geräten** | Wie zwei Zeilen darüber, aber für **eine** Arbeitszahl (*Heizen*, *Warmwasser* oder *Kühlen*): Genau diese Funktion mischt Geräte, die übrigen Zahlen dürfen bleiben. Beim Kühlen ist die Nutzenergie die **Kälte**menge — deshalb nicht „Wärme". | getrennte Strommessung am zweiten Gerät einschalten und zuordnen, wenn es sie gibt |
| **Nutzenergie und Strom dieser Funktion stammen aus verschiedenen Monaten** | Dieselbe Lage je Funktion, über die Zeit statt über die Geräte. Bei nur **einem** Gerät ist das die zutreffende Auskunft — von „Geräten" zu sprechen wäre dort falsch. | die fehlenden Monatswerte nachpflegen |
| **Ein weiterer Verbraucher auf dem WP-Zähler (z. B. Heizstab)** | Deine eigene Angabe im Feld *Fremdanteil auf den Zählern*. Der Stromwert ist zu groß. | Angabe korrigieren, wenn sie nicht mehr stimmt |
| **zweiter Erzeuger am Wärmezähler** | Dieselbe Angabe, andere Richtung: Ein zweiter Erzeuger speist denselben Heizkreis — ein Gas- oder Ölkessel, oder ein **elektrischer Heizstab, dessen Strom getrennt gezählt wird**. Der Wärmewert ist zu groß. | dito Ersparnis und CO₂ bleiben stehen, tragen aber den Vorbehalt *„zweiter Erzeuger am Wärmezähler — Ersparnis und CO₂ enthalten dessen Wärme"*: eedc kennt den Anteil des zweiten Erzeugers nicht und rechnet ihn nicht heraus. |
| **Zähler messen verschiedene Zeiträume** | Strom und Wärme stammen aus verschieden langen Messzeiträumen. | Lücken im Monatsabschluss schließen |
| **Strom nicht getrennt je Funktion gemessen** | Betrifft nur die Arbeitszahlen *Heizen* und *Warmwasser*. Ein Betriebsmodus-Sensor ersetzt die getrennte Messung hier **nicht** — siehe den Kasten unter dieser Tabelle. | getrennte Strommessung einschalten und zuordnen |
| **Wärme nicht je Funktion gemessen** | Das Gegenstück auf der Wärmeseite: Deine Wärme steht unter *Wärme gesamt*, kommt also aus **einem** Zähler über Heizung und Warmwasser. Die Menge stimmt, aber sie lässt sich nicht auf die beiden Funktionen aufteilen. | so lassen — oder einen zweiten Wärmemengenzähler setzen und dann *Heizwärme* und *Warmwasser-Wärme* getrennt pflegen |
| **kein Kältemengenzähler zugeordnet** | Betrifft nur die Arbeitszahl *Kühlen*. | Kältemengenzähler zuordnen — oder es bleibt so |
| **keine Kälte abgegeben in diesem Zeitraum** | Nur am **Tag**: Der Kältemengenzähler ist zugeordnet und meldet **null**, obwohl Kühlstrom geflossen ist — typisch, wenn das Gerät im Kühlmodus stand und pausierte (die Stunde zählt dann zum Kühlen, siehe *„Leerlauf behält deinen Modus"*). | nichts. **Nicht mit *kein Kältemengenzähler zugeordnet* verwechseln** — dort fehlt die Messung, hier ist sie da und sagt null |

> ### ⚑ Warum ein Betriebsmodus-Sensor keine Arbeitszahl *Heizen* ergibt — die Kühlzahl aber schon
>
> Das sieht auf den ersten Blick nach einer Lücke aus: Du hast einen Betriebsmodus-Sensor
> zugeordnet, eedc weist dir damit *Heizen · Warmwasser · Kühlen* getrennt aus — und bekommst
> trotzdem für *Kühlen* eine Arbeitszahl und für *Heizen* keine. Das ist gewollt.
>
> **Der Nenner einer Arbeitszahl je Funktion ist der getrennt *gemessene* Strom dieser Funktion.**
> Was aus dem Betriebsmodus entsteht, ist keine zweite Messung, sondern eine **Verteilung** deines
> Gesamtstroms auf die Stunden: eedc schaut nach, was das Gerät wann tat, und teilt danach auf. Eine
> Verteilung erbt jede Unschärfe ihres Schlüssels — wie lange dein Gerät wirklich in welchem Modus
> lief, wie viel davon Standby war —, eine Messung nicht. Aus so einem Anteil eine Effizienzzahl zu
> bilden hieße, die Ungenauigkeit der Aufteilung als Eigenschaft deiner Wärmepumpe auszuweisen.
>
> **Beim Kühlen ist es trotzdem richtig, und zwar aus einem Grund, den es nur dort gibt:** Für Heizen
> und Warmwasser existiert der gemessene Weg — *Strom Heizen* und *Strom Warmwasser* ([Schritt 2](#schritt-2--entscheiden-ein-zähler-oder-getrennte)).
> Für den Kühlbetrieb gibt es ihn nicht überall, und die Kältemenge selbst liegt ohnehin nur mit
> Zähler vor. Wo keine bessere Zahl möglich ist, ist die verteilte die einzige — und sie steht neben
> einer gemessenen Kältemenge, nicht neben einer geschätzten.
>
> **Was du tun kannst:** Willst du auch für Heizen und Warmwasser eine Arbeitszahl, brauchst du zwei
> Stromzähler statt eines — *Getrennte Strommessung* einschalten und beide zuordnen ([Schritt 2](#schritt-2--entscheiden-ein-zähler-oder-getrennte)). Der
> Betriebsmodus-Sensor bleibt dabei sinnvoll: Er trägt weiter die Aufteilung nach Betriebsart.
>
> ⚑ **Dieselbe Unterscheidung wirkt auf der Abzugsseite**, und dort ändert sie die Gesamt-Arbeitszahl:
> Abgezogen wird nur, was im Nenner auch drinsteht. Ein aus dem Betriebsmodus verteilter Kühlanteil
> kürzt deinen gemessenen Heiz- und Warmwasserstrom nicht — nachgerechnet in
> [Fall B2](#b2--getrennte-zähler-für-heizung-und-warmwasser-betriebsmodus-sensor-kein-kühlzähler)
> und erklärt in [§8](#8-häufige-missverständnisse).

### Und drei Gründe, die nur der **Tag** kennt

Sie beantworten die Frage „Warum ist der Tag leer, obwohl der Monat gefüllt ist?" (siehe [§2](#2-voraussetzungen--welcher-zähler-für-welche-anzeige)):

- **Kein Zähler zugeordnet** — mit dem Weg dorthin.
- **Zähler zugeordnet, aber für diesen Tag liegen keine Zählerstände vor. Tageswerte entstehen ab der Zuordnung; frühere Tage lassen sich in der Reparatur-Werkbank nachrechnen.** ⭐ **Seit v4.0.45 nur noch, wenn im Tag wirklich kein einziger Stand liegt** — beginnt die Reihe mitten am Tag, zeigt eedc die Menge und schreibt *„gemessen ab hh:mm Uhr"* dazu (Kasten in [§2](#2-voraussetzungen--welcher-zähler-für-welche-anzeige)).
- **Der Zähler ist an diesem Tag zurückgesprungen — für diesen Tag gibt es deshalb keine Aussage.**

> ⛔ **Bis v4.0.28 stand an dieser Stelle unterschiedslos *„Sensor zuordnen"*** — auch bei jemandem, der zugeordnet hatte. Ein Tester hat daraufhin zu Recht gefragt, was die Anzeige ihm eigentlich sagen will. **Eine falsche Ursache ist schlimmer als keine:** Ohne Hinweis sucht man selbst, mit einem falschen sucht man an der falschen Stelle.

### Und einer, den nur der **laufende Monat** kennt

Seit v4.0.45 springt für den laufenden Monat eine fünfte Quelle ein, wenn Monatsabschluss,
HA-Statistik, Connector und MQTT nichts hergeben: die **Tageswerte**, die eedc ohnehin
mitschreibt (siehe [Bedienung → Cockpit → Monat](HANDBUCH_BEDIENUNG.md#23-monat)). Am
Quellen-Etikett über den Kacheln steht dann „Tageswerte".

⭐ **Das gilt auch für Wärme, Kälte und die Arbeitszahlen.** Sie kommen aus **demselben
Leser, aus dem der Verlauf daneben seine Tage zeichnet** — Strom je Gerät, gemessene
Wärme, Kältemenge und die Betriebsart-Aufteilung. Damit nennen Kachel, Tabelle *Zahlen je
Gerät* und Verlauf dieselbe Zahl, statt dass die eine gefüllt ist und die andere leer.
Auch die Tabelle *Zahlen je Gerät* steht jetzt im laufenden Monat, obwohl es dafür noch
keinen Monatsabschluss gibt.

> ⚠ **Was eine gepflegte Zahl war, bleibt eine gepflegte Zahl.** Hast du für diesen Monat
> schon Werte eingetragen oder importiert, gelten sie — die Tageswerte füllen nur, was
> sonst fehlt.
>
> ⚠ **Ohne zugeordneten Wärmemengenzähler bleibt die Wärme leer**, und damit auch die
> Arbeitszahl. Die Tageswerte können nur zeigen, was gemessen wurde; eine Arbeitszahl aus
> gemessenem Strom und **fehlender** Wärme wäre keine halbe Auskunft, sondern eine falsche.
> Was dann zu tun ist, steht im Kasten *„Was noch möglich wäre"* unter dem Block.

⭐ **Und seit v4.0.45 auch für die Arbeitszahlen je Funktion.** Wer Heizung und Warmwasser
getrennt misst, sieht *Arbeitszahl Heizen* und *Arbeitszahl Warmwasser* jetzt schon im
laufenden Monat — vorher stand dort bis zum Monatsabschluss *„Strom nicht getrennt je
Funktion gemessen"*, obwohl beide Zähler zugeordnet waren und die Tabelle *Zahlen je Gerät*
direkt darunter die Zahlen zeigte.

> ⚠ **Bei mehreren Geräten kann trotzdem ein Grund stehen — und er ist der richtige.** Eine
> Arbeitszahl je Funktion gibt es für die ganze Anlage nur, wenn Wärme und Strom **derselben**
> Funktion von **denselben** Geräten kommen. Misst ein zweites Gerät seine Wärme mit einem
> gemeinsamen Zähler, dann steht dort *„Nutzenergie und Strom dieser Funktion stammen von
> verschiedenen Geräten"* — mit dem Weg in den Komponenten-Hub, der jedes Gerät für sich zeigt.
> **Die Zahlen je Gerät bleiben davon unberührt.**
>
> ⭐ **Eine Brauchwasser-Wärmepumpe daneben ist dabei kein Hindernis** (seit v4.0.45). Sie hat
> nur eine Funktion — ihr **ganzer** Strom ist Warmwasser-Strom, auch ohne getrennte Zähler.
> eedc rechnet sie deshalb auf beiden Seiten mit: Eine Anlage aus Wärmepumpe und
> Brauchwasser-WP bekommt ihre *Arbeitszahl Warmwasser* aus der Wärme **und** dem Strom
> beider Geräte. ⚠ Für eine **Klimaanlage** gilt das nicht: Sie kühlt auch, ihr Strom gehört
> nicht ganz zum Heizen.

### Und der Tag rechnet jetzt wie der Monat

⭐ **Seit v4.0.45 prüft auch *Cockpit → Tag*, ob Wärme und Strom einer Funktion von denselben
Geräten kommen** — an den Zahlen **dieses Tages**. Vorher fragte er den Monat, und solange der
noch läuft, weiß der nichts: An einer Anlage aus drei Wärmepumpen standen im Tag zwei
Arbeitszahlen ohne jeden Hinweis, während *Cockpit → Monat* für dieselbe Anlage schon sagte,
warum es sie nicht gibt.

> ⚠ **Damit kann im Tag ein Grund auftauchen, wo vorher eine Zahl stand.** Die Zahl war nicht
> belastbar: In ihrem Zähler stand die Wärme des einen Geräts, in ihrem Nenner der Strom eines
> anderen. Es ist derselbe Grund, den derselbe Monat nach seinem Abschluss nennt — und
> **dieselbe Auskunft auf allen drei Zeitebenen** ist der eigentliche Gewinn.

### Der Fremdanteil — die einzige Angabe, die eedc nicht messen kann

Zwei Lagen machen jede Arbeitszahl unbrauchbar, **ohne dass man es den Zahlen ansieht**:

1. Ein **weiterer Verbraucher hängt am Stromzähler** der Wärmepumpe, seine Wärme läuft aber nicht über den Wärmemengenzähler. ⇒ Der Stromwert ist zu groß, die Arbeitszahl zu klein.
   Typisch ist der **Heizstab** — es gilt aber genauso für eine **Klimaanlage**, einen Pool-Heizer oder jeden anderen Verbraucher hinter demselben Zähler.
2. Ein **zweiter Erzeuger speist denselben Heizkreis**, den der Wärmemengenzähler misst; der Stromzähler erfasst nur die Wärmepumpe. ⇒ Der Wärmewert ist zu groß, die Arbeitszahl zu gut.
   Das ist der Gas- oder Ölkessel im bivalenten Betrieb — **und ebenso ein elektrischer Heizstab, dessen Wärme durch denselben Wärmemengenzähler läuft, während sein Strom getrennt gezählt wird.** Bei vielen Geräten (Daikin, Nibe) ist genau das die Werkseinstellung.

> ⚑ **Der Heizstab steht in beiden Lagen, und das ist kein Fehler.** Nicht das Gerät entscheidet, welcher Fall bei dir vorliegt, sondern **wo deine Zähler sitzen**. Zwei Fragen genügen:
>
> 1. *Zählt der Stromzähler der Wärmepumpe den Heizstab mit?* → Ja: **Lage 1**.
> 2. *Läuft die Wärme des Heizstabs durch denselben Wärmemengenzähler?* → Ja, aber sein Strom wird getrennt gezählt: **Lage 2**.
>
> Trennst du den Heizstab auf der **Strom**seite ab — etwa, indem du ihn als eigenen Verbraucher unter *Sonstiges* führst —, seine **Wärme** aber weiter im gemeinsamen Zähler steht, dann bist du in Lage 2. Die Arbeitszahl wird dadurch nicht sauber, sondern **zu gut**: Im Zähler steht Wärme, die dein Kompressor nie erzeugt hat.

Beide trägst du am Gerät unter **„Fremdanteil auf den Zählern"** ein. **Sie ändern keine einzige deiner Mengen** — Strom, Wärme, Kosten und CO₂ bleiben, wie sie sind. eedc lässt nur die Arbeitszahl weg und schreibt den Grund daneben.

> **Warum es ein Feld ist und nicht zwei Kennzeichen:** Es ist *eine* Regel — Zähler und Nenner müssen dasselbe meinen. Ein Kennzeichen je Beispiel hätte eine Fallsammlung daraus gemacht, und der bivalente Fall (Nr. 2) blieb genau deshalb jahrelang unsichtbar.

---

## 5. Sensoren zuordnen, Schritt für Schritt

Alles läuft über **Einstellungen → Datenquellen**. Dort steht je Gerät eine Liste von Feldern; neben jedem Feld wählst du die Quelle: **HA-Sensor**, **MQTT**, **Connector** oder **Keine**.

### Schritt 1 — Gerät anlegen und die Bauart wählen

*Einstellungen → Investitionen → Neu → Wärmepumpe.* Die **Wärmepumpenart** bestimmt, welche Felder oben stehen:

| Art | Felder oben | Nicht angeboten (aber erreichbar) |
|-----|-------------|-----------------------------------|
| **Luft-Wasser / Sole-Wasser / Grundwasser** | Stromverbrauch, Heizwärme, Warmwasser, Wärme gesamt | Betriebsart-Zähler (Kühlen, Lüften, Entfeuchten) |
| **Luft-Luft (Klimaanlage)** | Stromverbrauch, Wärme gesamt, Betriebsart-Zähler | Warmwasser — den Kreis gibt es dort nicht |
| **Brauchwasser (nur Warmwasser)** | Stromverbrauch, Warmwasser, Wärme gesamt | Heizwärme, Strom Heizen |

> ⚑ ***Wärme gesamt* ist der Platz für EINEN gemeinsamen Wärmemengenzähler** und steht deshalb bei jeder Bauart — welche Zähler es gibt, sagt deine Anlage, nicht die Bauart. Mit **getrennten** Zählern lässt du das Feld leer und trägst *Heizwärme* und *Warmwasser-Wärme* ein; mit **einem** Zähler ist es umgekehrt.

> **„Nicht angeboten" heißt nicht „gesperrt".** Alles Übrige liegt unter **„Weitere Größen erfassen"** und rückt nach oben, sobald du dort einen Sensor einträgst. Die einzige echte Ausnahme ist **Warmwasser an einer Luft-Luft-Klimaanlage**: Den Kreis gibt es dort nicht.
>
> ⚑ **Hast du dort früher einmal einen Wert gepflegt, ist er nicht verloren — er zählt nur nicht mehr als Wärme des Geräts.** Bis 2026 floss ein solcher Altwert in *Wärme erzeugt*, in die Arbeitszahl und in die Ersparnis gegenüber der alten Heizung; das war eine Ersparnis für Wärme, die eine Klimaanlage nicht abgibt. Der **Daten-Checker** nennt dir jeden betroffenen Monat. Stammt der Wert aus dem **Kühlbetrieb**, gehört er unter *Nutzenergie Kuehlbetrieb* — daraus rechnet eedc deine **Arbeitszahl Kühlen**. **eedc verschiebt und löscht nichts von allein**, der gespeicherte Wert bleibt stehen, bis du ihn umträgst.

> ⚑ **Und was du gar nicht führst, verschwindet von selbst aus der Anzeige.** Hat eine Wärmepumpe **nie** einen Warmwasser-Wert getragen und ist auch kein Warmwasser-Zähler zugeordnet, zeigt der Block *Wärme nach Zweck* im Komponenten-Hub keine Warmwasser-Achse mehr — weder Balken noch Spalte noch Legendeneintrag. Das ist der Fall, wenn deine Heizungs-Wärmepumpe nur heizt und eine **eigene Brauchwasser-Wärmepumpe** daneben das Warmwasser macht. Du musst dafür nichts einstellen, und sobald du einen Zähler zuordnest oder einen Wert pflegst, ist die Achse wieder da. **Ein einziger gepflegter Monat genügt — auch mit dem Wert 0**: Dann ist die Null eine Messung und keine Leerstelle.
>
> ⭐ **Führst du Heizung und Warmwasser über *einen* Wärmemengenzähler**, trag seinen Wert unter ***Wärme gesamt*** ein — nicht unter *Heizwärme*. eedc rechnet dann mit der Gesamtwärme: Wärmemenge, Arbeitszahl, Ersparnis und CO₂ stimmen. **Getrennte Arbeitszahlen für Heizen und Warmwasser gibt es dabei nicht** — dafür bräuchtest du zwei Wärmemengenzähler —, und eedc sagt das mit dem Grund *„Wärme nicht je Funktion gemessen"*, statt eine Zahl zu zeigen. ⚑ **Hast du deine Summe bisher unter *Heizwärme* geführt, bleibt sie stehen, bis du sie umträgst** — eedc verschiebt nichts von allein. Bis September 2026 gab es das Feld *Wärme gesamt* nicht; wer getrennt gemessenen Strom hat, sah in dieser Lage eine **zu hohe Arbeitszahl Heizen** (die ganze Wärme geteilt durch den Heizstrom allein).

> ⭐ **Mehrere Wärmepumpen an EINEM Zähler sind für eedc EIN Gerät.** Bei einer **Kaskade** oder zwei Geräten, die auf denselben Pufferspeicher arbeiten und über einen gemeinsamen Wärmemengen- und Stromzähler laufen, leg **eine** Investition an und ordne ihr beide Zähler zu. Trägst du sie einzeln ein, steht die gemessene Wärme beim einen Gerät und der gemessene Strom beim anderen — eedc kann nicht wissen, dass die beiden Zähler dieselbe Anlage meinen, und sperrt die Arbeitszahl mit *„Wärme und Strom stammen von verschiedenen Geräten"* ([§4](#4-wann-eine-kennzahl-verschwindet--und-warum-das-richtig-ist)). Physisch wäre Σ Wärme ÷ Σ Strom hier richtig; eedc darf es nur nicht raten. ⚠ Die **Anschaffungskosten** trägst du dann ebenfalls zusammen ein — die Wirtschaftlichkeit rechnet auf derselben Investition.

### Schritt 2 — Entscheiden: ein Zähler oder getrennte?

Am Gerät gibt es den Schalter **„Getrennte Strommessung"**.

- **Aus** (Standard): Du ordnest **einen** Zähler zu — *Stromverbrauch*.
- **Ein**: Du ordnest **zwei** zu — *Strom Heizen* und *Strom Warmwasser*. Ein Gesamtzähler ist daneben **nicht nötig, aber willkommen**: Hast du einen, gilt sein Wert als Verbrauch des Geräts, und die beiden Achsen sind die Aufteilung darunter.

> ⭐ **Im Monatsabschluss** rechnet eedc den Gesamtwert bei eingeschaltetem Schalter selbst: Beim Speichern gilt *Strom Heizen + Strom Warmwasser*, und zwar **bei jedem Speichern neu** — ändert sich eine der beiden Achsen, zieht die Summe mit. Das Feld *Stromverbrauch* erscheint im Formular erst, wenn es etwas Eigenes trägt: einen **zugeordneten Gesamtzähler** (dann steht dort sein Messwert, und eedc bildet keine Summe) oder einen **von dir eingetragenen Wert**. **Leer lassen = eedc rechnet;** wer das sichtbare Feld leert und speichert, bekommt wieder die Summe. ⛔ In früheren Versionen blieb die Summe auf dem Stand des **ersten** Speicherns eines Monats stehen, wenn Heizen oder Warmwasser später noch wuchsen — ein solcher alter Wert steht jetzt sichtbar im Feld, und der Daten-Checker weist darauf hin (s. unten); leeren und speichern repariert ihn.

> ⭐ **Der Schalter sagt, WIE gezählt wird — nicht, OB gezählt wird.** Ein vorhandener Zähler wird nie ignoriert, nur weil ein Schalter etwas anderes ankündigt. ⛔ **Bis September 2026 war das anders**, und ein Tester ist daran hängen geblieben: Er hatte einen Gesamtzähler und den Schalter eingeschaltet, woraufhin der Block *Wärme/Klima* in der Tagesansicht verschwand — Ausschalten hat es damals gelöst. **Dieser Handgriff ist nicht mehr nötig**, und wer den Schalter früher umgelegt hat, bekommt seine Zahlen der Vergangenheit damit zurück.
>
> ⭐ **Und seit September 2026 zählt der Gesamtzähler auch neben zwei vollständigen Achsen.** Eine Wärmepumpe verbraucht Strom, der auf keiner der beiden Achsen liegt: **Standby, Steuerung, Umwälzpumpen.** Bei einem Tester waren das 145 von 2193 kWh im Jahr — knapp 7 %. Hast du einen Gesamtzähler, ist **er** die Menge, mit der eedc rechnet; die Differenz zu *Strom Heizen + Strom Warmwasser* erscheint in der Aufteilung als **„nicht aufgeteilt"**. ⛔ Bis dahin wurde der Gesamtzähler in dieser Lage verworfen — *„sonst zählte dieselbe Kilowattstunde zweimal"* —, und diese Kilowattstunden fehlten in Verbrauch, Kosten, CO₂ und im Nenner der Arbeitszahl. **Doppelt gezählt wird trotzdem nichts**: eedc *ersetzt* die Summe durch den Gesamtwert, es addiert sie nicht. Deine **Arbeitszahl gesamt** fällt damit etwas niedriger aus als vorher — und ist dafür ehrlich.
>
> ⚠ **Nur eine Richtung ist ein Fehler.** Steht dein Gesamtzähler **unter** der Summe der beiden Achsen, sagt der Daten-Checker es dir: Dann misst er meist nur einen Teil des Geräts (nur das Außengerät, nur einen Stromkreis). eedc rechnet in solchen Monaten mit der Summe der Achsen, damit nichts verloren geht. Umgekehrt — Gesamtzähler höher — ist die normale Lage und kein Fehler; erst wenn mehr als ein Viertel des Verbrauchs auf keiner Achse liegt, **fragt** eedc einmal nach, ob der Zähler wirklich nur die Wärmepumpe misst. Stammt der Gesamtwert eines solchen Monats aus dem Monatsformular, nennt eedc in beiden Hinweisen zusätzlich die zweite mögliche Ursache — ein stehen gebliebener alter Stand — und den Handgriff: Feld *Stromverbrauch* leeren und speichern.
>
> ⚠ **Die getrennten Arbeitszahlen brauchen die getrennten Zähler trotzdem.** Ohne *Strom Heizen* gibt es keine *Arbeitszahl Heizen*, ohne *Strom Warmwasser* keine *Arbeitszahl Warmwasser* — der Gesamtzähler kann nicht sagen, welcher Teil wohin ging. Der Bilanzwert stimmt also auch mit nur einem Zähler; **getrennt** wird erst, was getrennt gemessen ist.
>
> ⭐ **Und das gilt je Seite: der Daten-Checker nennt jede fehlende einzeln.** Fehlt in einem Monat nur *Strom Warmwasser*, während die Warmwasser-Wärme dieses Monats erfasst ist, meldet er *„Strom Warmwasser fehlt in n Monat(en)"* — und umgekehrt für die Heiz-Seite. Der Grund: eedc bildet jede Arbeitszahl aus **abgegebener Wärme ÷ eingesetztem Strom**. Fehlt eine Stromseite, sperrt die Zeile **dieser Funktion** korrekt mit *„kein Stromverbrauch erfasst"* — die **Gesamt**-Arbeitszahl kann das nicht: Hast du keinen Gesamtzähler, rechnet sie die Wärme beider Seiten über den Strom einer und fällt zu hoch aus. **Der Handgriff:** den Wert für die genannten Monate im Monatsabschluss nachtragen. ⚑ Ein Monat **ohne** Betrieb auf einer Seite ist keine Lücke — wer im Sommer nicht heizt, bekommt keine Meldung zum Heizstrom.

### Schritt 3 — Die Wärme zuordnen (oder bewusst darauf verzichten)

*Heizwärme*, *Warmwasser-Wärme* und *Wärme gesamt* sind **thermische** Größen in kWh — die abgegebene Wärme, **nicht** der Strom. Das ist die häufigste Verwechslung überhaupt, und die Felder tragen sie deshalb im Namen.

**Welches Feld deins ist, entscheidet dein Zähler:**

| Deine Zähler | Was du einträgst | Was eedc daraus rechnet |
| --- | --- | --- |
| **Zwei** — einer für die Heizung, einer fürs Warmwasser | *Heizwärme* **und** *Warmwasser-Wärme* | alles, inklusive **Arbeitszahl Heizen und Warmwasser** getrennt (mit getrennter Strommessung) |
| **Einer**, gemeinsam über Heizung und Warmwasser | ***Wärme gesamt*** | Wärmemenge, Arbeitszahl gesamt, Ersparnis, CO₂ — **keine** Zahl je Funktion |
| **Einer**, nur auf dem Heizkreis | *Heizwärme* | dasselbe wie oben, plus **Arbeitszahl Heizen** |
| **Keiner** | nichts — eedc leitet die Wärme aus *Strom × Arbeitszahl* ab und kennzeichnet sie | Mengen als Modellrechnung, **keine** Arbeitszahl (sie wäre zirkulär) |

> ⚠ **Trag denselben Wert nicht zweimal ein.** Steht in *Wärme gesamt* ein Wert, ist **er** die Wärme des Geräts; *Heizwärme* und *Warmwasser-Wärme* stehen dann nur noch als Aufteilung daneben. Ist die Aufteilung zusammen **größer** als der Gesamtwert, sagt der Daten-Checker es dir — dann meint einer der beiden Werte etwas anderes als gedacht.

> ⚠ **Besonders beim Import aus einer eigenen Datei.** Viele Hersteller-Exporte führen die abgegebene Wärme in **zwei** Spalten nebeneinander — einmal die vom Gerät erzeugte Wärme, einmal die aus der Umwelt entnommene *Umgebungswärme*. Für eedc zählt die **erzeugte** Wärme; wird die Umgebungswärme mit zugeordnet oder die bereits addierte Summe genommen, steht die Wärmemenge um ein Vielfaches zu hoch.
>
> **Woran du es merkst — und in welche Richtung:**
>
> | Was die Arbeitszahl zeigt | Was das heißt |
> | --- | --- |
> | **auffällig hoch** (deutlich über dem, was das Gerät leisten kann) | Der **Zähler** ist zu groß — typisch die mit zugeordnete Umgebungswärme |
> | **unter 1** | Der **Nenner** ist zu groß oder der Zähler unvollständig: mehrere Geräte auf einem Stromzähler, ein Heizstab auf demselben Zähler, oder es meldet nicht jedes Gerät seine Wärme |
>
> Eine Wärmepumpe kann nicht weniger Wärme abgeben, als sie Strom aufnimmt — deshalb ist eine Zahl unter 1 immer ein Hinweis auf die **Strom**seite, nie auf zu viel Wärme.

Ohne Wärmemengenzähler rechnet eedc die Heizwärme aus *Strom × gepflegter Arbeitszahl* und **kennzeichnet sie als abgeleitet**. Die Mengen sind dann eine Modellrechnung, die Arbeitszahl fällt weg (sie wäre zirkulär). Das ist ein legitimer Betriebszustand, kein Mangel. Wo diese Wärme erscheint, steht ihre Herkunft dabei — im Komponenten-Hub als „geschätzt: Strom × JAZ 3,5" unter der Wärme-Kachel; Ersparnis und CO₂ bleiben eine Modellrechnung und sagen das.

> ⚑ **Der Strom der Wärmepumpe wird immer voll gerechnet, auch der Teil aus der eigenen PV — dessen Wert steht auf der PV-Seite als Eigenverbrauch.** Das gilt für die Ersparnis wie für die CO₂-Bilanz, in jeder Sicht.

### Schritt 4 — Betriebsart erfassen (optional, aber lohnend)

Es gibt **zwei Wege**, und **gemessen schlägt abgeleitet**:

**Weg A — Betriebsart-Zähler (genauer).** Du ordnest *Strom Heizbetrieb*, *Strom Kühlbetrieb*, *Strom Lüftbetrieb*, *Strom Entfeuchtungsbetrieb* zu, soweit vorhanden. eedc rechnet nichts, es liest ab.

> ⚑ **Für Warmwasser gibt es hier bewusst kein Feld.** Wer seinen Warmwasser-Strom getrennt misst, trägt ihn unter *Strom Warmwasser* ein (Schritt 2) und bekommt daraus seine *Arbeitszahl · Warmwasser*. Ein zweites Feld für dieselbe Zahl wäre nur eine Gelegenheit, beide versehentlich zu addieren.

> ### Die Nutzenergie je Betriebsart — was eedc daraus macht
>
> Neben den vier Strom-Feldern gibt es vier **thermische**: *Nutzenergie Heizbetrieb*,
> *Nutzenergie Kühlbetrieb*, *Nutzenergie Lüftbetrieb*, *Nutzenergie Entfeuchtungsbetrieb*. Sie
> sind optional — ohne Wärmemengenzähler gibt es diese Werte nicht, und eedc rechnet sie nicht
> herbei. Was aus jedem von ihnen wird, steht hier:
>
> | Feld | Was eedc daraus macht |
> |---|---|
> | **Nutzenergie Heizbetrieb** | Das ist die **Heizwärme deines Geräts**. Hast du am Gerät keinen eigenen Wärmemengenzähler (*Heizwärme* bzw. *Wärme gesamt*), trägt sie die Wärme-Kachel und die Arbeitszahl — in Cockpit, Hub, Ersparnis, CO₂ und den HA-Sensoren. |
> | **Nutzenergie Kühlbetrieb** | Die **Kältemenge** — der einzige Weg zur *Arbeitszahl Kühlen* (Kältemenge ÷ Kühlstrom). |
> | **Nutzenergie Lüft-/Entfeuchtungsbetrieb** | Eine **Mengenzeile** neben ihrem Strom. Keine Kennzahl (siehe [Was eedc bewusst nicht sagt](#3-was-eedc-bewusst-nicht-sagt)), keine Wärmesumme. |
>
> ⭐ **Mehrere Innengeräte werden summiert.** Ein Wert **am Gerät** schlägt die Summe seiner
> Innengeräte — und wird nie dazuaddiert: Beide beschreiben dieselbe Menge auf zwei Ebenen.
>
> ⛔ **Ein Gerätezähler gewinnt gegen die Betriebsart.** Steht unter *Heizwärme* oder *Wärme
> gesamt* ein Wert, gilt er: Er misst mehr als eine einzelne Betriebsart. Auch eine gepflegte
> **0** gewinnt — sie heißt „diesen Monat nicht geheizt" und ist damit eine Aussage, keine Lücke.
>
> ⚑ **Bis v4.0.44 wurden die drei Felder außer *Kühlbetrieb* nirgends gelesen.** Wer sie pflegte,
> sah *Heizwärme 0* und als Grund *„kein Wärmemengenzähler zugeordnet"* — der Zähler war
> zugeordnet, eedc las ihn nur nicht. Gepflegte Werte aus dieser Zeit wirken jetzt rückwirkend,
> ohne dass du etwas tun musst.

**Weg B — Betriebsmodus-Sensor (bequemer).** Du ordnest einen Sensor zu, der sagt, *was das Gerät gerade tut*. eedc schreibt ihn stündlich mit und teilt den Verbrauch danach auf.

> ### Welchen Sensor eedc lesen kann
>
> Am besten die **`climate`-Entität** deines Geräts — die meldet den Modus von sich aus richtig.
>
> Ein gewöhnlicher `sensor.` geht genauso, er muss aber einen dieser **Texte** liefern:
>
> | Home-Assistant-Schreibweise | deutsch | eedc versteht es als |
> |---|---|---|
> | `heat` | `heizen` | Heizen |
> | `dhw` · `hot_water` · `water_heating` | `warmwasser` · `brauchwasser` · `trinkwasser` | Warmwasser |
> | `cool` | `kuehlen` · `kühlen` | Kühlen |
> | `dry` | `entfeuchten` | Entfeuchten |
> | `fan_only` | `lueften` · `lüften` | Lüften |
> | `off` | `aus` | Aus |
> | `auto` · `heat_cool` | `automatik` | *unbestimmt* — das Gerät lief, die Seite ist nicht zuordenbar |
>
> Groß-/Kleinschreibung ist egal.
>
> ⚑ **Warmwasser kennt Home Assistant nicht als Betriebsmodus** — es führt die Trinkwassererwärmung in einer eigenen Gerätegruppe. Eine `climate`-Entität allein sagt dir also meist nur *heizen/kühlen*. Wenn deine Wärmepumpe Warmwasser macht, ist der Template-Sensor unten der Weg dorthin.
>
> ⛔ **Eine Zahl reicht nicht.** Manche Integrationen liefern den Modus als **Rohwert** — Viessmann zum Beispiel als `sensor.…_hk1_mode_raw` mit dem Wert `1`. Was `1` bedeutet, weiß nur dein Gerät; eedc rät es nicht und zeigt deshalb **„Unbestimmt"**. Dasselbe gilt für jeden anderen Text, den die Tabelle nicht kennt.
>
> **Der Ausweg ist ein Template-Sensor in Home Assistant**, der aus dem, was du hast, einen der Texte oben macht. Hast du **Leistungssensoren je Funktion**, brauchst du die Codierung deines Geräts gar nicht:
>
> ```yaml
> template:
>   - sensor:
>       - name: "Wärmepumpe Betriebsmodus (eedc)"
>         state: >
>           {% set kuehl = states('sensor.DEIN_KUEHL_LEISTUNG')|float(0) %}
>           {% set heiz  = states('sensor.DEIN_HEIZ_LEISTUNG')|float(0) %}
>           {% set ww    = states('sensor.DEIN_WARMWASSER_LEISTUNG')|float(0) %}
>           {% if kuehl > 20 %}kuehlen
>           {% elif ww > 20 %}warmwasser
>           {% elif heiz > 20 %}heizen
>           {% else %}aus{% endif %}
> ```
>
> ⚠ **Die 20 stehen für 20 Watt — prüf zuerst die Einheit deiner Sensoren.** Die Schwelle soll nur das Standby-Rauschen abfangen. Meldet deine Wärmepumpe ihre Leistung in **kW** (also `0,8` statt `800`), wird sie **nie** über 20 kommen: der Sensor steht dann dauerhaft auf **„aus"**, obwohl das Gerät läuft — und es sieht so aus, als hätte alles funktioniert. Bei kW-Sensoren nimm einen Wert wie `0.02`, bei W-Sensoren einen, der zum Standby-Verbrauch deines Geräts passt.
>
> **So prüfst du es:** In Home Assistant unter *Entwicklerwerkzeuge → Zustände* den Sensor suchen — dort steht der aktuelle Wert. Läuft die Wärmepumpe gerade, ist eine dreistellige Zahl Watt und eine Zahl mit Komma kW.
>
> ⚠ **Die Reihenfolge im Template ist nicht beliebig.** Läuft die Wärmepumpe für Warmwasser, kann dabei auch der Heiz-Leistungssensor Werte zeigen; deshalb wird Warmwasser **vor** Heizen geprüft. Wer es umdreht, bucht seine Warmwasserstunden aufs Heizen.
>
> ⚑ **Was du davon siehst:** *Strom-Aufteilung nach Betriebsart* unter deiner Wärmepumpe bekommt eine eigene Zeile **Warmwasser** — in Cockpit → Tag, Monat und Jahr, im Komponenten-Hub und als Sensor *Strom Warmwasserbetrieb* in Home Assistant.
>
> ⚠ **Das ist etwas anderes als das Feld *Strom Warmwasser***, auch wenn beide dieselbe Energie meinen können. *Strom Warmwasser* ist ein **eigener Zähler** und ein Summand: Heizen + Warmwasser ergeben zusammen deinen Gesamtverbrauch. Die Zeile im Balken ist eine **Teilmenge** des Gesamtverbrauchs, aus mitgeschriebenen Stunden. **Addiere sie nie.**
>
> ⚠ **Weg B wirkt nur ab jetzt.** Die Aufteilung entsteht aus mitgeschriebenen Stunden — **rückwirkend gibt es sie nicht**. Deshalb steht unter dem Balken, wie viele Stunden eedc tatsächlich mitgelesen hat.

> ### Mehrere Innengeräte — eedc braucht **eine** Aussage über die Anlage
>
> Dein Stromzähler ist **einer** (meist eine Messsteckdose am Außengerät). Für die Aufteilung
> braucht eedc deshalb genau **eine** Aussage darüber, was die **Anlage** gerade tut — nicht drei
> Aussagen über drei Innengeräte.
>
> **Der einfache Weg, und für die meisten der richtige:** Ordne bei **allen** Innengeräten
> **dieselbe** `climate`-Entität zu. Bei einer Anlage mit einem Kältekreis gibt ohnehin das
> Außengerät die Richtung vor — das zuerst eingeschaltete Innengerät bestimmt sie, die anderen
> können dann nur dasselbe. Mehrere Zuordnungen auf dieselbe Entität zählt eedc als **eine**
> Quelle; deine Aufteilung funktioniert wie gewohnt.
>
> ⛔ **Zeigen die Zuordnungen auf *verschiedene* Entitäten, teilt eedc nicht auf** und sagt es im
> Daten-Checker. Der Grund ist nicht Bequemlichkeit: Aus mehreren Innengeräte-Zuständen einen
> Anlagen-Zustand zu bilden, hängt an **deiner** Anlage — ob ein Innengerät lüften kann, während
> ein anderes heizt; ob dein Außengerät beim Enteisen etwas meldet; ob „Entfeuchten" bei dir
> kühlseitig läuft. **Das weißt du, eedc weiß es nicht — und eedc rät nicht.**
>
> **Der zweite Weg: du schreibst die Regel selbst.** Ein Template-Sensor fasst deine Innengeräte
> zu einer Anlagen-Aussage zusammen; **dessen** Ergebnis ordnest du dann als Betriebsmodus zu:
>
> ```yaml
> template:
>   - sensor:
>       - name: "Klimaanlage Betriebsmodus Anlage (eedc)"
>         state: >
>           {% set g = [states('climate.INNEN_1'),
>                       states('climate.INNEN_2'),
>                       states('climate.INNEN_3')] %}
>           {% if 'heat' in g %}heizen
>           {% elif 'cool' in g %}kuehlen
>           {% elif 'dry'  in g %}entfeuchten
>           {% elif 'fan_only' in g %}lueften
>           {% elif g | reject('eq','off') | list | count == 0 %}aus
>           {% else %}automatik{% endif %}
> ```
>
> ⚠ **Die Reihenfolge ist auch hier nicht beliebig, und sie ist deine Entscheidung.** Sie sagt:
> *ein Innengerät, das eine Richtung nennt, gewinnt gegen eines, das nur lüftet oder aus ist* —
> denn den Löwenanteil verbraucht der Verdichter, und der arbeitet für die Richtung. Passt das
> nicht zu deiner Anlage, dreh sie um.
>
> ⛔ **`aus` erst, wenn wirklich alle aus sind — und auch dann mit Vorsicht.** „Alle Innengeräte
> aus" heißt **nicht** „die Anlage ist aus": Das Außengerät kann enteisen oder nachlaufen und
> dabei kräftig Strom ziehen. Wenn du dafür eine eigene Quelle hast, nimm sie; wenn nicht, ist
> `automatik` (⇒ *unbestimmt*) die ehrlichere Antwort als `aus`.

> ### Wenn deine Anlage taktet: „Leerlauf" behält deinen Modus
>
> Meldet deine Integration zusätzlich den **Ist-Betrieb** (`Aktuelle Aktion` in Home Assistant),
> liest eedc ihn mit — er sagt genauer als der eingestellte Modus, was gerade läuft. Nennt er
> eine **Richtung** (Heizen, Kühlen, Entfeuchten, Lüften), gilt sie.
>
> Steht dort **Leerlauf**, weil die Solltemperatur erreicht ist, **bleibt dein eingestellter
> Modus stehen.** Eine Anlage, die auf *Kühlen* steht und gerade pausiert, kühlt weiterhin —
> Home Assistant schreibt es genauso auf die Kachel: „Leerlauf (Kühlbetrieb)". Die Stunde zählt
> deshalb zum Kühlen.
>
> ⛔ **Bis v4.0.30 war das anders**, und das war ein Fehler: Leerlauf verwarf den Modus, die
> Stunde fiel unter *nicht aufgeteilt*. **Bei einem gut ausgelegten Inverter-Gerät ist das der
> größte Teil der Zeit** — die Aufteilung war damit praktisch wirkungslos. Gemeldet von einem
> Anwender mit einer taktenden Multisplit-Anlage.
>
> **Was weiterhin *nicht aufgeteilt* bleibt:** Leerlauf, während **keine** Richtung eingestellt
> ist — also bei *Automatik* (`heat_cool`) oder wenn dein Gerät gar keinen Modus meldet. Dann
> gibt es nichts, worauf eedc zurückfallen könnte, und geraten wird nicht.

> ### Zähler schlagen den Betriebsmodus
>
> Hast du **Zähler je Betriebsart** (Schritt 4, Weg A), brauchst du den Betriebsmodus für die
> Aufteilung **nicht** — er wird dann gar nicht dafür herangezogen. Der Modus ist der Weg für
> alle, die **nur einen** Zähler haben. Beides zuzuordnen schadet nicht (der Modus trägt weiter
> Icon und Klartext in der Live-Sicht), bringt für die Aufteilung aber nichts dazu.
>
> ⛔ **Und das gilt schon ab dem ersten Zähler.** Ordnest du auch nur **einen** Betriebsart-Zähler
> zu, gilt für dieses Gerät **nur noch** der gemessene Weg — die übrigen Betriebsarten erscheinen
> dann unter *nicht aufgeteilt*, statt aus dem Modus abgeleitet zu werden. Ordne deshalb entweder
> alle zu, die du hast, oder verlass dich auf den Modus.

> ### Was dein Anlagenzähler erfassen muss
>
> eedc setzt voraus, dass der Zähler dieses Geräts **den ganzen Verbrauch** erfasst — Außengerät
> **und** Innengeräte. Alle Werte, die du je Innengerät pflegst, versteht eedc als
> **Aufschlüsselung** dieses Gesamtwerts, nie als etwas, das dazukommt.
>
> ⛔ **Werden deine Innengeräte über eigene Steckdosen versorgt und dort gemessen, passt das
> nicht** — dann fehlt ihr Verbrauch in deiner Bilanz, nicht nur in der Aufteilung. eedc kann
> das heute nicht abbilden. Melde dich, wenn deine Anlage so gebaut ist; die Frage ist
> beschrieben und wartet auf einen echten Fall.
>
> ⚑ **Übersteigen deine Betriebsart-Zähler den Anlagenzähler**, sagt eedc es und weist **keine**
> Aufteilung aus. Zwei Ursachen sind möglich und von außen nicht unterscheidbar: der
> Anlagenzähler erfasst nicht alles (siehe oben) — oder die Zähler sind herstellerseitig
> **gerechnete Anteile** statt Messungen. **Falsche Eingangswerte erzeugen falsche Ergebnisse;
> eedc korrigiert sie nicht, es nennt sie.**

**Beide Wege ganz oder gar nicht je Gerät.** Wer Betriebsart-Zähler hat, für den gelten sie; der abgeleitete Weg wird dort nicht zusätzlich angewendet. Eine Aufteilung, deren eine Hälfte aus einem Zähler und deren andere aus einer Rechnung stammt, trüge ein halbwahres Etikett.

### Schritt 5 — Die Kältemenge (nur mit Kältemengenzähler)

*Nutzenergie Kühlbetrieb* ist die **abgeführte Wärme** in kWh. Nur damit entsteht die **Arbeitszahl Kühlen**. Hast du keinen solchen Zähler — der Normalfall —, steht dort der Grund statt einer Zahl.

### Schritt 6 — Live-Werte (optional)

*Leistung gesamt*, *Leistung Heizen*, *Leistung Warmwasser*, *Leistung Kühlen* (alle in W), *Warmwasser-Temperatur*, *Betriebsmodus*, *Soll-* und *Raumtemperatur*.

Die Leistungsfelder erscheinen in *Cockpit → Live*: Unter dem Gerät steht *Leistung gesamt*, und wo du sie nicht misst, die Summe der Betriebsarten — das Symbol wechselt dann mit der stärksten von ihnen. Im Tagesverlauf bekommt jede gemessene Betriebsart ihre eigene Fläche. **Mengen entstehen daraus nicht** — Stromverbrauch, Wärme, Kälte und alle Arbeitszahlen kommen aus den kWh-Zählern.

> ⚑ **„Leistung gesamt" und die Aufteilung schließen sich im Verlauf aus.** Ordnest du *Leistung gesamt* zu, wertet eedc *Leistung Heizen*, *Leistung Warmwasser* und *Leistung Kühlen* im Live-Tagesverlauf **nicht** aus — dort erscheint dann eine Fläche für die ganze Wärmepumpe. Die Zuordnungs-Fläche sagt es dir an den betroffenen Feldern. Beides ist richtig, es ist eine Wahl: Die Gesamtleistung ist der vollständige Anlagenwert (und die einzige Quelle des Wärmepumpen-Anteils in der Verbrauchsprognose, solange noch keine Tagesprofile aggregiert sind), die getrennten Felder sind die feinere Auskunft. Sobald Tagesprofile vorliegen, nimmt die Verbrauchsprognose *Leistung Warmwasser* und *Leistung Kühlen* (oder den *Betriebsmodus* der Stunde), um diese Anteile **nicht** mit der Außentemperatur zu skalieren — ein Warmwasser-Zyklus braucht an einem kalten Tag nicht mehr Strom als an einem warmen.

> ### ⭐ Eine Fläche je Betriebsart — was der Stundenverlauf dafür voraussetzt
>
> Damit deine Wärmepumpe im **Stundenverlauf** des Tages (dem Butterfly-Chart über dem Block
> *Wärme/Klima*) getrennt nach *Heizen*, *Warmwasser* und *Kühlen* erscheint, müssen **beide**
> Bedingungen erfüllt sein:
>
> 1. **Mindestens zwei** der drei Felder *Leistung Heizen*, *Leistung Warmwasser* und
>    *Leistung Kühlen* sind zugeordnet. Mit nur einem davon wäre die Funktionsfläche die
>    Wärmepumpen-Fläche unter anderem Namen, und eedc lässt sie dann zusammen.
> 2. *Leistung gesamt* bleibt **leer**. Ist es zugeordnet, gilt der Kasten darüber: die
>    Gesamtleistung verdrängt die Einzelfelder.
>
> In *Cockpit → Live* genügt sogar **ein** zugeordnetes Feld: Dort bekommt jede Betriebsart, die du
> misst, ihre eigene Fläche mit eigenem Namen. Was du dort siehst, siehst du ab zwei Feldern auch
> im Stundenverlauf des Tages — in denselben Farben und unter denselben Namen.
>
> ⚑ **Liegt am selben Gerät zusätzlich ein kWh-Zähler, hat er das letzte Wort über die Menge.** Die
> Leistungsreihen sagen dann nicht mehr, *wie viel* verbraucht wurde, sondern nur noch, *wie
> es sich verteilt*. Ist der Zähler **größer** als alle Reihen zusammen, steht die Differenz als
> eigene Fläche **„Wärmepumpe (übrige)"** daneben, statt still zu verschwinden. Ist er **kleiner**,
> rechnet eedc die Flächen im selben Verhältnis auf den Zähler herunter — die Stapelhöhe
> bleibt die gemessene Menge, statt über sie hinauszuwachsen. **Ohne getrennte Leistungssensoren —
> der Normalfall — ändert sich für dich nichts.**

> ⚑ **Was diese Wahl berührt — und was nicht.** Deine **Mengen** kommen aus den kWh-Zählern und bleiben unberührt: Stromverbrauch, Wärme, Kosten, CO₂, Ersparnis und die **Arbeitszahlen für Heizen, Warmwasser und gesamt**. Die **Aufteilung nach Betriebsart** entsteht dagegen aus dem Leistungspfad — eedc liest dort die *Form* der Stunden ab und legt die Zählermenge darauf. Welchen Leistungssensor du zuordnest, kann deshalb verschieben, wie viel Strom dem Heizen, Kühlen oder Warmwasser zugerechnet wird, und damit auch die **Arbeitszahl Kühlen** (ihr Nenner ist genau dieser Anteil). Wenn dein Gerät im Kühlbetrieb läuft und du nur *Leistung Heizen* und *Leistung Warmwasser* zugeordnet hast, tragen die Kühlstunden im Leistungspfad nichts — ordne dann **Leistung Kühlen** dazu (oder statt der Aufteilung **Leistung gesamt**).

> ⛔ **Watt ist keine Kilowattstunde.** Ein Leistungssensor gehört **nie** in ein kWh-Feld. Die Stundenwerte eines Leistungssensors ergeben zwar eine plausible Zahl — sie speist aber nicht die Zählerpfade, aus denen der Block *Wärme/Klima* entsteht. Liefert dein Gerät **nur** Leistung, baue in Home Assistant unter *Helfer → Integral-Sensor* (Riemannsche Summe) einen kWh-Zähler daraus.

### Schritt 7 — Den Daten-Checker fragen

*Einstellungen → Daten.* Er nennt fehlende Zuordnungen, Monate ohne Werte und Widersprüche — und zu jedem Befund den Weg dorthin. **Ein Befund, den du nicht auflösen kannst, ist ein Fehler im Checker und keine Aufgabe für dich.** Melde ihn.

---

## 6. Sieben Anlagen, sieben Ergebnisse

Diese sieben Bauformen sind **nicht erfunden** — fünf davon stammen aus Rückmeldungen von Testern, und alle stehen als nachgestellte Anlagen im Prüflauf von eedc. Sie zeigen, was du bei welcher Ausstattung bekommst.

### A — Wärmepumpe **und** Klimaanlage, nur die Wärmepumpe meldet Wärme

*„Ist es nicht sinnvoller, die Luft-Wasser-Wärmepumpe von der Luft-Luft-Klimaanlage komplett zu trennen?"*

WP: 3000 kWh Wärme auf 800 kWh Strom. Klimaanlage: 200 kWh Strom, keine Wärme.

| Sicht | Ergebnis |
|-------|----------|
| **Cockpit** (beide zusammen) | Arbeitszahl **„≥ 3,00"** (3000 ÷ 1000), darunter *Klimaanlage: Strom ohne Wärmemessung enthalten* |
| **Cockpit**, Tabelle *Zahlen je Gerät* | Wärmepumpe **3,75** · Klimaanlage **„—"**, beim Überfahren *kein Wärmemengenzähler zugeordnet* |
| **Komponenten → Wärmepumpe** | **3,75** (3000 ÷ 800) — sauber abgegrenzt |

⭐ **Die Mengen bleiben in beiden Sichten vollständig.**

⭐ **Die Klimaanlage hat nur eine Wärme-Achse — und die Tabelle zeigt das.** Bei ihr steht in der Spalte *Heizen* derselbe Strich wie unter *Arbeitszahl* (mit demselben Grund: es fehlt der **Wärme**mengenzähler), und die Spalte *Warmwasser* bleibt **leer**: Eine Split-Klimaanlage hat keinen Warmwasserkreis. Bis v4.0.44 stand in beiden Spalten *„Strom nicht getrennt je Funktion gemessen"* — ein Hinweis auf getrennte Stromzähler, die dir hier gar nichts brächten, solange die Wärme nicht gemessen ist.

⭐ **Und im Kasten *Was noch möglich wäre* steht jetzt, welchem Gerät was fehlt** — *„Arbeitszahl · Arbeitszahl Heizen · Bosch Climate 5000 Multisplit: kein Wärmemengenzähler zugeordnet"*, mit dem Handgriff daneben. Vorher stand das nirgends im Block: Der einzige Hinweis war der Satz unter dem „≥", und der erklärt den Mindestwert, nicht den Strich in der Zeile.

⭐ **Bis v4.0.44 stand im Cockpit „—" mit dem Grund *Wärmepumpe und Klimaanlage in einer Zahl*.** Der Grund war richtig: 3000 ÷ 1000 ist keine Arbeitszahl deiner Wärmepumpe — im Zähler steht die Wärme eines Geräts, im Nenner der Strom von zweien. Er ist aber ein **Mindestwert** für die Anlage, denn die 200 kWh der Klimaanlage können die Zahl nur **kleiner** machen. Deshalb steht dort jetzt „≥ 3,00" statt eines Strichs — und die 3,75 deiner Wärmepumpe **im selben Block** eine Zeile tiefer, statt nur hinter einem Link.

### B — Drei getrennte Zähler: Heizung, Warmwasser, Kühlen

*„Ich habe getrennte Zähler für Heizung, Warmwassererwärmung … und seit dem Sommer auch für den Kühlbetrieb."*

Heizen 3000 kWh Wärme auf 750 kWh Strom · Warmwasser 600 auf 200 · Kühlen 100 kWh Strom ohne Kältemenge. Gesamtstrom 1050 kWh.

| Kennzahl | Wert |
|----------|------|
| Arbeitszahl · Heizen | **4,00** |
| Arbeitszahl · Warmwasser | **3,00** |
| Arbeitszahl gesamt | **3,79** — 3600 ÷ (1050 − 100) |
| Arbeitszahl · Kühlen | „—", *kein Kältemengenzähler zugeordnet* |

⭐ **Der Kühlstrom steht in keinem der Nenner.** Er gehört zu einer Nutzenergie, die hier nicht gemessen wird. Stünde er drin, sähe die Anlage im Sommer aus wie eine schlechte Heizung.

> ⚑ **Und wenn du zusätzlich einen Gesamtzähler hast?** Dann gilt **er** als Verbrauch des Geräts. Steht er auf 1050 kWh — also genau auf der Summe der drei —, ändert sich nichts: 3,79 bleibt 3,79. Steht er höher, ist die Differenz dein **Systemverbrauch** (Standby, Steuerung, Umwälzpumpen): Sie erscheint in der Aufteilung als *„nicht aufgeteilt"*, zählt in Verbrauch, Kosten und CO₂ mit und steht im Nenner der Arbeitszahl gesamt. Bei 1145 kWh wären das 95 kWh und **3,44** statt 3,79. Die beiden Zahlen je Funktion bleiben unverändert — ihr Nenner ist der jeweils eigene Zähler.

### B2 — Getrennte Zähler für Heizung und Warmwasser, Betriebsmodus-Sensor, **kein** Kühlzähler

Dieselbe Anlage wie B, nur ohne den dritten Zähler: Heizen 3000 kWh Wärme auf 750 kWh Strom · Warmwasser 600 auf 200. Gesamtstrom **950 kWh** — mehr misst diese Anlage nicht. Dazu ein Betriebsmodus-Sensor, aus dem eedc stündlich mitschreibt, was das Gerät gerade tat.

| Kennzahl | Wert |
|----------|------|
| Arbeitszahl · Heizen | **4,00** |
| Arbeitszahl · Warmwasser | **3,00** |
| Arbeitszahl gesamt | **3,79** — 3600 ÷ 950 |
| Aufteilung nach Betriebsart | Heizen 700 · Warmwasser 150 · **Kühlen 100** |

**Was eedc hier rechnet:** Es verteilt die **vorhandenen** 950 kWh nach dem Betriebsmodus. Die 100 kWh „Kühlen" sind kein vierter Zähler, sondern ein Ausschnitt aus den beiden vorhandenen.

**Was eedc dafür voraussetzt:** dass diese beiden Zähler den Kühlbetrieb **nicht** getrennt führen — sie sind alles, was das Gerät an Strommessung hat. ⚑ **Und genau deshalb steht in dieser Lage kein Gesamtzähler daneben.** Hättest du einen, wäre **er** die Menge (s. [Schritt 2](#schritt-2--entscheiden-ein-zähler-oder-getrennte)), der Kühlanteil steckte darin und würde vom Nenner abgezogen — du wärst rechnerisch in Fall B, ohne den dritten Zähler zu haben.

⭐ **Deshalb kürzt der Kühlanteil hier keinen Nenner.** In Fall B ist er ein eigener Zähler *neben* den anderen beiden, dort wird er abgezogen. Hier ist er eine **Verteilung** derselben 950 kWh — ihn abzuziehen hieße, um eine Menge zu kürzen, die nie hinzukam. Beide Anlagen zeigen deshalb dieselbe Zahl **3,79**, obwohl die eine einen Zähler mehr hat.

**Der Handgriff, wenn du es genauer willst:** Ordne *Strom Kühlbetrieb* zu (*Einstellungen → Datenquellen*, beim Gerät). Dann liest eedc ab, statt zu verteilen — und du bist in Fall B. Der Daten-Checker weist dich unter *Einstellungen → Daten* darauf hin.

> **Ohne Betriebsmodus-Sensor** gibt es gar keine Aufteilung — das ist Fall C.

### C — Eine Wärmepumpe, die kühlt, aber ohne getrennte Messung

Kein Betriebsart-Zähler, kein Betriebsmodus-Sensor.

**Es gibt keine Aufteilung** — der Balken fehlt ganz, statt drei Nullen zu zeigen. Die Gesamt-Arbeitszahl bleibt **unverfälscht**: Weil eedc den Kühlanteil nicht kennt, erfindet es ihn auch nicht.

### D — Wärmepumpe mit Kältemengenzähler

900 kWh Kälte auf 300 kWh Kühlstrom.

**Arbeitszahl Kühlen: 3,00** — im Komponenten-Hub und im Cockpit, mit derselben Zahl an beiden Orten. Ohne den Zähler stünde dort der Grund.

### E — Zwei Geräte, beide mit Betriebsmodus-Sensor

Wärmepumpe mit getrennter Strommessung (800 + 400 kWh) und Wärmemengenzählern (2400 + 1000 kWh), dazu eine Klimaanlage mit 200 kWh und eigenem Modus-Sensor. Beide melden an 18 Stunden.

| Anzeige | Wert |
|---------|------|
| Strom verbraucht | **1400 kWh** (alle drei Zähler) |
| Modus erfasst | **18 Stunden** — nicht 36 |
| Aufgeteilte Menge | wird genannt, sobald sie vom Gesamtstrom abweicht |
| Aggregiert aus | **Wärmepumpe · Klimaanlage** — die Namen stehen unter dem Block |
| Arbeitszahl | **„≥ …"** — ein Mindestwert, weil der Strom der Klimaanlage ohne Wärmemessung im Nenner steht (seit v4.0.45; vorher „—" mit Grund) |
| Zahlen je Gerät | jedes Gerät mit seiner eigenen Arbeitszahl, im Block |

⭐ **Kilowattstunden darf man über Geräte addieren, Stunden nicht.** Zwei Geräte, die dieselben 18 Stunden liefen, ergeben 18 Stunden Beobachtung. Bis v4.0.28 stand dort 36 — an einem Tag.

⭐ **Der Block nennt seine Geräte — und seit v4.0.31 auch unter *Cockpit → Tag*.** Solange dort niemand sagte, dass zwei Geräte in einer Summe stecken, war die Zahl nicht nachvollziehbar: Wer den Balken mit dem Zähler **einer** seiner Anlagen verglich, fand eine Differenz, für die es keine Erklärung gab. Monat und Jahr nannten die Namen längst, der Tag als einzige Sicht nicht.

**Die Mengen bleiben zusammen, und das ist Absicht.** Kilowattstunden über Geräte zu addieren ist richtig — was fehlte, war die Auskunft darüber. Wer die Geräte einzeln sehen will, öffnet *Komponenten → Wärmepumpe*; dort steht jedes für sich, mit eigener Arbeitszahl.

### F — Brauchwasser-Wärmepumpe

Ein Gerät, das ausschließlich Warmwasser macht.

Wähle die Wärmepumpenart **Brauchwasser**. eedc fragt dann nur noch nach *Stromverbrauch* und *Warmwasser* — die Heiz-Achse wird weder angeboten noch erwartet, und der Daten-Checker verlangt sie nicht.

**Deine Arbeitszahl Warmwasser ist die Arbeitszahl des Geräts.** Dein ganzer Strom geht ins Warmwasser — ein getrennter Zähler könnte gar nichts anderes messen. eedc zeigt die Zahl deshalb an beiden Stellen, mit **denselben** Werten:

| | |
|---|---|
| 4,8 kWh Wärme ÷ 1,45 kWh Strom | **Arbeitszahl 3,31** · **Arbeitszahl Warmwasser 3,31** |
| Arbeitszahl Heizen | **bleibt leer** — nicht „—", sondern gar nichts |

> ⚑ **Warum die Heizen-Spalte leer bleibt und nicht „—" zeigt:** Ein Strich heißt *„hier fehlt etwas"*. An einer Achse, die dein Gerät nicht hat, gäbe es aber nichts nachzurüsten. Bis v4.0.44 stand dort ein Strich mit dem Satz *„Strom nicht getrennt je Funktion gemessen"* — für eine Funktion, die dein Gerät gar nicht kennt, und daneben derselbe Satz für das Warmwasser, dessen Zahl direkt danebenstand.

> **Hast du doch einen Heizzähler** (manche Geräte unterstützen einen kleinen Heizkreis): Trag ihn unter *„Weitere Größen erfassen"* ein. Die Bauart ist ein Vorschlag, kein Verbot. Die **Menge** zählt dann überall mit; eine eigene *Arbeitszahl Heizen* verspricht eedc dir trotzdem nicht — dafür bräuchte es einen getrennten Stromzähler für diesen Kreis.

### G — Ein Wärmemengenzähler für Heizung und Warmwasser

Der Regelfall bei einer Luft-Wasser-Wärmepumpe mit Umschaltventil: **ein** Vorlauf, **ein** Wärmemengenzähler, und er misst beides. Dazu getrennte Stromzähler für Heizen und Warmwasser.

3000 kWh Wärme aus dem gemeinsamen Zähler · Strom Heizen 600 kWh · Strom Warmwasser 400 kWh.

Trag die 3000 unter ***Wärme gesamt*** ein und lass *Heizwärme* und *Warmwasser-Wärme* leer.

| Sicht | Ergebnis |
|-------|----------|
| **Wärme erzeugt** | **3000 kWh** — gemessen, in Cockpit, Komponenten-Hub, Tag und Jahr dieselbe Zahl |
| **Arbeitszahl (gesamt)** | **3,0** (3000 ÷ 1000) |
| **Arbeitszahl Heizen / Warmwasser** | **„—"**, Grund: *Wärme nicht je Funktion gemessen* |
| **Ersparnis und CO₂** | vollständig — sie brauchen nur die Menge |
| **Wärme nach Zweck** | kein Balken: Es gibt nichts aufzuteilen |

⚠ **Trägst du die 3000 stattdessen unter *Heizwärme* ein** (so stand es bis September 2026 im Handbuch), rechnet eedc **3000 ÷ 600 = 5,0** als *Arbeitszahl Heizen* — eine plausibel aussehende Zahl, die zwei verschiedene Dinge ins Verhältnis setzt. Die Mengen, die Gesamt-Arbeitszahl, Ersparnis und CO₂ sind auch dann richtig; falsch ist nur die Zuordnung zur Funktion.

⭐ **Und wenn dein einziger Zähler nur den Heizkreis misst** (Warmwasser läuft ungemessen mit oder über ein eigenes Gerät): Dann gehört sein Wert weiterhin unter *Heizwärme* — und die *Arbeitszahl Heizen* ist richtig. Genau deshalb entscheidet **dein Eintrag**, nicht eine Vermutung von eedc: In den Daten sehen die beiden Anlagen sonst gleich aus.

---

## 7. Verteilung und Verlauf — wohin der Strom gegangen ist

*Seit v4.0.45.* Unter dem Block *Wärme/Klima* steht in **Cockpit → Tag, Monat und
Jahr** ein Teil mit drei Bildern, die dieselbe Frage beantworten: **Wohin ist der
Strom deiner Wärme- und Klimageräte gegangen — und was hat es gekostet?**

| Teil | Was er zeigt |
|------|--------------|
| **Anteile** | Je Gerät und Funktion eine Zeile: *Heizen · Warmwasser · Kühlen · Lüften · Entfeuchten* und, was keine davon erklärt, mit kWh und Prozent |
| **Kosten je Funktion** | Dieselben Zeilen mit **Herkunft**, **Arbeitspreis** und **Betrag** — und einer Summe |
| **Verlauf** | Dieselben Segmente über die Zeit: **Stunden** eines Tages, **Tage** eines Monats, **Monate** eines Jahres. Darüber die **Ø-Außentemperatur** als Linie (rechte Achse, per Legendenklick ausblendbar) und, wo eedc den Wettercode kennt, ein **Wettersymbol** über der Zeitachse |

Der Blockteil ist parkbar und fokussierbar wie jedes andere Element.

### Woher die Aufteilung kommt — und warum sie je Gerät entschieden wird

**Jedes Gerät teilt seinen Strom auf dem Weg auf, den seine Zähler hergeben**
(der Erfassungs-Kanon, [§5 Schritt 2](#schritt-2--entscheiden-ein-zähler-oder-getrennte)):

* **Getrennte Stromzähler** für Heizen und Warmwasser ⇒ die beiden Achsen sind die
  Aufteilung. Kommt ein **gemessener** Betriebsart-Zähler dazu (Kühlen, Lüften,
  Entfeuchten), steht er daneben — er misst etwas anderes, nicht dasselbe noch einmal.
* **Kein getrennter Stromzähler, aber ein Betriebsart-Zähler oder ein
  Betriebsmodus-Sensor** ⇒ die Aufteilung entsteht daraus. Die Spalte *Herkunft*
  sagt dir, welcher Weg gegriffen hat: **gemessen** (ein Zähler) oder
  **abgeleitet** (aus dem Modus gerechnet).
* **Weder noch** ⇒ das Gerät steht in keiner Zeile. Sein Strom zählt trotzdem zur
  Anlage; die Zeile *„Aufgeteilte Menge X von Y kWh"* unter dem Bild sagt, wie viel
  davon aufgeteilt ist.

**Zwei Geräte dürfen verschiedene Wege gehen** — eine Wärmepumpe mit getrennten
Zählern neben einer Klimaanlage mit Modus-Sensor ergibt ein Bild mit beiden. Was
**nicht** geht, ist eine gemeinsame Arbeitszahl für die beiden: Mengen darf man
addieren, Kennzahlen nicht ([§8](#8-häufige-missverständnisse)).

> ⚠ **Die zwei Reste heißen verschieden, und das ist wichtig.**
>
> * **System/Standby** — dein **Gesamtzähler** misst mehr als die Summe deiner
>   Funktionszähler. Das ist echter Verbrauch: Steuerung, Umwälzpumpen, Standby.
>   Bei einem Melder waren das 145 von 2193 kWh im Jahr (6,6 %).
> * **Ohne Modus** — es gab **Stunden ohne Betriebsmodus-Signal**, oder eine
>   Betriebsart hat keinen eigenen Zähler. Das ist kein Verbrauch eigener Art,
>   sondern fehlende Erkenntnis.
>
> **Sie werden nie addiert.** Ein Gerät trägt immer nur einen von beiden; stehen
> beide im Bild, gehören sie zu **verschiedenen Geräten**.

### Die Kosten

**Kosten = kWh × Arbeitspreis des jeweiligen Monats.** Hast du einen
**Wärmepumpen-Sondertarif** hinterlegt, gilt der; sonst dein allgemeiner Tarif,
und bei Zeitfenstern (HT/NT) der über deinen gemessenen Netzbezug gewichtete
Preis. Im **Jahr** rechnet eedc **Monat für Monat** und zeigt als Preis den
mengengewichteten Mittelwert — eine Preiserhöhung im Juli schreibt den Januar
also nicht um.

> ⚠ **Es sind die Kosten des Stroms, den diese Geräte verbraucht haben** — nicht
> deine Netzbezugskosten. Ob eine Kilowattstunde aus der PV oder aus dem Netz kam,
> weiß eedc je Gerät nicht (dafür bräuchte es eine Zuteilungsannahme, und die wäre
> erfunden). Die Zahl beantwortet *„was hat mich dieser Betrieb gekostet"*, nicht
> *„was steht auf meiner Stromrechnung"*.

### Temperatur und Wettersymbol

Die **Ø-Außentemperatur** kommt aus deinen eigenen Reihen, nicht aus einem Abruf:
zuerst die Stundenwerte, sonst *(Min + Max) / 2* des Tages, zuletzt ein von Hand
gepflegter Monatswert. Fehlt alles, fehlt die Linie — ein kalter Monat ohne
Messreihe ist kein 0-°C-Monat.

Das **Wettersymbol** ist der **häufigste** Wettercode der Periode: bei einer
Stunde ihr eigener, bei einem Tag der häufigste seiner Stunden, bei einem Monat
der häufigste seiner Tage. Ein Tag mit vierzehn Sonnenstunden und einem Schauer
ist damit ein sonniger Tag. **Fehlt der Code, fehlt das Symbol** — geraten wird
nichts. Auf schmalen Geräten erscheint die Symbolreihe nur, wenn die Symbole
nebeneinander passen (bis zwölf Perioden); überlappende Symbole wären eine
Auskunft, die niemand lesen kann.

### Drei Zeilen, die eine Differenz benennen

Sie erscheinen nur, wenn es etwas zu sagen gibt — und jede meint etwas anderes:

| Zeile | Bedeutung |
|-------|-----------|
| **Aufgeteilte Menge X von Y kWh** | Ein Gerät hat gar keine Aufteilung (s. o.) |
| **Im Verlauf erfasst X von Y kWh** | Der Verlauf kommt aus einer anderen Quelle als die Anteile darüber: die Tagessäulen aus dem, was eedc täglich mitschreibt, die Anteile aus deiner Monatszeile. Was nur monatlich gepflegt ist, steht deshalb oben und nicht im Verlauf |
| **Strom ohne Stundenzuordnung** | Nur am Tag: eine Menge, für die es keine Stundenform gab. Sie wird **genannt** statt gleichmäßig über den Tag verteilt — eine geschmierte Kurve wäre eine erfundene Form |

---

## 8. Häufige Missverständnisse

**„Der Block zeigt eine andere Arbeitszahl als der Komponenten-Hub."**
Das ist so gewollt und der wichtigste Unterschied auf dieser Fläche. Der Block *Wärme/Klima* im Cockpit fasst **alle** Geräte zusammen; der Hub zeigt **eines**. Bei gemischter Ausstattung steht im Block deshalb ein **Mindestwert** („≥ 3,00"), während das einzelne Gerät eine höhere, saubere Zahl hat. Unter dem Block steht, aus welchen Geräten er entsteht — und seit v4.0.45 steht die Zahl **je Gerät** gleich daneben.

**„Warum steht vor meiner Arbeitszahl ein ‚≥'?"**
Weil im Nenner Strom steckt, dem keine gemessene Wärme gegenübersteht — typisch eine Split-Klimaanlage, die mitheizt, oder ein Heizstab auf eigenem Zähler. Deine Anlage ist also **mindestens** so effizient wie die Zahl, vermutlich besser. Der Satz darunter nennt das Gerät. **Was du tun kannst:** Wenn das Gerät eine Wärmemessung haben kann, ordne sie zu; wenn nicht (eine Klimaanlage hat bauartbedingt keinen Wärmemengenzähler), ist der Mindestwert die ehrlichste Zahl, die es gibt. Die saubere Zahl deiner Wärmepumpe steht in derselben Sicht in der Tabelle *Zahlen je Gerät*.

**„Wo ist der Grund hin, der früher unter der leeren Kachel stand?"**
Er steht seit v4.0.45 **einmal** am Ende des Blocks, im Kasten *„Was noch möglich wäre"* — mit dem Handgriff daneben. Vorher trug jede fehlende Kennzahl ihre eigene Kachel mit „—" und demselben Satz; ein einziger fehlender Zähler erzeugte damit bis zu vier gleichlautende Zeilen. **Ein „—" ohne Text heißt etwas anderes:** Die Messung ist da, dieser Zeitraum war leer — die Arbeitszahl Heizen im Juni zum Beispiel. Dort gibt es nichts zu tun.

**„Heizwärme ist doch der Stromverbrauch fürs Heizen."**
Nein. *Heizwärme* ist die **abgegebene thermische Wärme**. Der Strom fürs Heizen heißt *Strom Heizen*. Trägst du Strom in ein Wärmefeld ein, kommt eine Arbeitszahl um 1 heraus.

**„Die Summe der Tage passt nicht zum Monat."**
Bei der CO₂-Einsparung ist das **so vorgesehen**: Der Tageswert trägt nur den PV-Anteil, weil es Wärmepumpen-Wärme und E-Auto-Kilometer nur monatlich gibt. Die Spalte heißt deshalb ausdrücklich *„CO₂-Einsparung (PV)"*.

Bei **Wärme/Klima** kommt ein zweiter Grund dazu, und er ist genau **eine Stunde** groß. Liest eedc deine Tageswerte aus der Langzeitstatistik von Home Assistant — der Regelfall im Add-on —, dann steht ein Tag für das Fenster *Vortag 23 Uhr bis heute 23 Uhr*. Das ist Absicht: Es ist dasselbe Fenster, in dem eedc auch die Stunden zählt, und nur deshalb geht eine Tageszeile in sich auf — Strom, Aufteilung, Wärme und Arbeitszahl desselben Tages messen dieselben 24 Stunden. Der **Monats**wert läuft dagegen vom Monatsersten 0 Uhr bis zum Monatsletzten 24 Uhr. Die Summe der Tagessäulen enthält damit die letzte Stunde des Vormonats und nicht die letzte Stunde des Monats: **Beide Zahlen sind richtig, sie messen nur nicht dieselben 24 Stunden.** **Zu tun ist nichts** — würde eedc eines der beiden Fenster verbiegen, wäre entweder die Tagesansicht in sich falsch oder der Monatswert nicht mehr der, den Home Assistant kennt. Dieselbe Fensterfrage stellt sich auch bei Speicher, Wallbox und E-Auto; die Tabelle dazu steht in [Berechnungen & Kennzahlen](BERECHNUNGEN.md).

**„Der Monatsverlauf zeigt Tagessäulen, im Jahresverlauf fehlt derselbe Monat — oder umgekehrt."**
Die beiden Verläufe stammen aus zwei Quellen, und das ist der Preis dafür, dass es beide überhaupt gibt. Der **Monats**verlauf zeichnet je Tag, was eedc an diesem Tag selbst mitgeschrieben hat. Der **Jahres**verlauf zeichnet je Monat die **Monatszeile** — also das, was gespeichert, importiert oder aus der Langzeitstatistik ergänzt wurde. Wo beides vorliegt, stimmen sie überein. Auseinander laufen sie in zwei Lagen:

- Ein **importierter oder von Hand gepflegter** Monat hat keine Tageswerte. Im Jahr steht sein Punkt, im Monatsverlauf bleiben die Säulen leer.
- Ein Monat **vor deiner Zuordnung** hat es umgekehrt: Die Langzeitstatistik reicht zurück und füllt den Jahrespunkt, mitgeschriebene Zählerstände gibt es für diese Tage nicht. Das ist derselbe Sachverhalt wie im Kasten *„Monat da, Tag leer"* ([§2](#2-voraussetzungen--welcher-zähler-für-welche-anzeige)).

**Was du tun kannst:** Wo Zählerstände vorliegen, hilft *Einstellungen → Daten → Tag neu berechnen*. Für einen rein importierten Monat gibt es dagegen nichts nachzurechnen — dort hat nie jemand einen Tag gemessen, und eine erfundene Verteilung auf 30 Säulen wäre keine Auskunft.

**„Im laufenden Monat sehe ich Strom und Wärme, aber keine Aufteilung und keine Kältemenge."**
Solange ein Monat läuft, ist er eine **Vorschau**: eedc füllt die Kacheln aus den Quellen, die es gerade lesen kann. Für eine Wärmepumpe sind das genau zwei Größen — **Stromverbrauch** und **Wärme**. Die **Aufteilung nach Betriebsart**, die **Kältemenge** und die **Arbeitszahl Kühlen** kommen dagegen ausschließlich aus der gespeicherten Monatszeile, und die entsteht erst mit dem Monatsabschluss. Deshalb können daneben Zahlen stehen, während diese drei leer bleiben. **Das ist keine Messlücke, sondern der Unterschied zwischen einer laufenden Vorschau und einer abgeschlossenen Zeile** — und weil Kältemenge und Kühlstrom aus **derselben** Quelle kommen, widersprechen sie einander dabei nie.

**Was du tun kannst:** Tagesgenau stehen Aufteilung und Kältemenge längst da — in *Cockpit → Tag*, sobald die Zähler zugeordnet sind. Im Monat sind sie da, sobald du den Monat im Monatsabschluss gepflegt hast.

**„Der Balken summiert sich nicht auf den Wert der Kachel darüber."**
Richtig — und seit v4.0.29 steht darunter, warum: **„Aufgeteilte Menge: 30 von 284 kWh".** Die Aufteilung entsteht nur für Geräte und Zeiträume, in denen eedc die Betriebsart mitlesen konnte; die Kachel zählt alle Geräte.

**„‚Nicht aufgeteilt' ist fast alles — die Aufteilung ist kaputt."**
Meistens nicht. *Nicht aufgeteilt* ist Standby, alles, was weder Heizen noch Kühlen war, **und die Zeit, in der eedc keinen Modus mitlesen konnte**. Bei einem Gerät, das überwiegend aus war, ist ein hoher Anteil die Wahrheit. Die Zeile *Modus erfasst* sagt dir, wie lange mitgelesen wurde.

**„Ich sehe ‚nicht aufgeteilt' an zwei Stellen mit verschiedenen Zahlen."**
Das ist kein Widerspruch — deine Kilowattstunden werden auf **zwei** Weisen aufgeteilt, und jede lässt ihren eigenen Rest übrig. Die eine Aufteilung ist **nach Funktion**: *Strom Heizen* und *Strom Warmwasser*; ihr Rest ist das, was dein Gesamtzähler mehr misst als die beiden zusammen — Standby, Steuerung, Umwälzpumpen. Die andere ist **nach Betriebsart**: Heizen, Kühlen, Lüften, Entfeuchten; ihr Rest sind die Stunden, in denen eedc keinen Modus mitlesen konnte. **Beide sind richtig, und sie werden nie addiert.** Hast du nur eine der beiden Aufteilungen, siehst du auch nur einen Rest.

**„Meine Arbeitszahl ist mit dem Update kleiner geworden, obwohl ich nichts geändert habe."**
Wenn du **getrennte Zähler und zusätzlich einen Gesamtzähler** führst: Ja, und das war eine Korrektur. Bis September 2026 hat eedc den Gesamtzähler in dieser Lage weggeworfen und mit *Strom Heizen + Strom Warmwasser* gerechnet. Alles, was dein Gerät darüber hinaus zieht — Standby, Steuerung, Umwälzpumpen —, fehlte damit im Verbrauch, in den Kosten, in der CO₂-Bilanz und im Nenner der Arbeitszahl. Jetzt zählt der Gesamtzähler, die Differenz steht als *„nicht aufgeteilt"* daneben, und die Arbeitszahl gesamt fällt entsprechend niedriger aus. **Deine Zahlen je Funktion ändern sich nicht** — die rechnen weiter mit dem jeweils eigenen Zähler. ⚑ Steht dein Gesamtzähler genau auf der Summe der beiden Achsen, ändert sich gar nichts.

**„Meine Arbeitszahl ist plötzlich niedriger geworden."**
Wenn du getrennte Zähler samt Kühlmessung führst: Ja, und das war eine Korrektur. Bis v4.0.28 fehlte der Kühlstrom im Verbrauch der Wärmepumpe und wurde zugleich ein zweites Mal aus dem Nenner gezogen — die Arbeitszahl fiel rund 12 % zu gut aus. Der Verbrauch steigt jetzt um den Kühlanteil, die Zahl sinkt auf ihren richtigen Wert.

**„Warum ist meine Arbeitszahl kleiner geworden?"**
Wenn du Heizung und Warmwasser getrennt misst **und** einen Betriebsmodus-Sensor zugeordnet hast, aber **keinen** eigenen Zähler für den Kühlbetrieb: Ja, und das war eine Korrektur. eedc hatte den geschätzten Kühlanteil aus dem Nenner gezogen, obwohl er darin gar nicht enthalten war — deine zwei Zähler messen ihn nicht getrennt, die Aufteilung verteilt sie nur. Im Beispiel von [Fall B2](#b2--getrennte-zähler-für-heizung-und-warmwasser-betriebsmodus-sensor-kein-kühlzähler) stand dort **4,24** statt **3,79**, also rund **12 %** zu gut. **Deine Mengen ändern sich dadurch nicht** — Verbrauch, Wärme, Kosten und CO₂ bleiben gleich; es ändert sich allein der Nenner dieser einen Kennzahl. Der Vorteil: Deine Zahl ist jetzt mit der einer baugleichen Anlage vergleichbar, die einen Kühlzähler hat — vorher war sie es nicht.

**„Meine Arbeitszahl ist plötzlich höher geworden."**
Wenn du Lüften oder Entfeuchten getrennt misst: Ja. Ihr Strom fällt seit v4.0.29 aus dem Nenner, weil sie keine messbare Nutzenergie erzeugen. **Deine Mengen ändern sich dadurch nicht.**

**„eedc sagt, ich soll einen Sensor zuordnen, den ich habe."**
Das war ein Fehler und ist behoben. Bis v4.0.28 hing an jedem „—" derselbe fest eingebaute Satz. Seit v4.0.29 nennt eedc den zutreffenden Grund — siehe [§4](#4-wann-eine-kennzahl-verschwindet--und-warum-das-richtig-ist). Begegnet dir trotzdem ein Hinweis, den keine Eingabe abstellt: **melden.**

**„Was sagt mir ‚kWh/Kd' im Vergleich?"**
Wie viel Strom deine Heizung je **Heizgradtag** braucht — je Grad, um den es draußen kälter war als 15 °C, mal Tage. Damit lassen sich zwei Winter vergleichen, auch wenn einer mild und einer streng war: Sinkt die Zahl, arbeitet die Anlage sparsamer. **Sie ist kein Qualitätsurteil wie die Arbeitszahl** und zwischen zwei Häusern nicht vergleichbar — ein großes, schlecht gedämmtes Haus braucht immer mehr je Kältegrad als ein kleines. Sie zählt **nur den Heizbetrieb**: Warmwasser bleibt außen vor, weil es nicht vom Wetter abhängt. Du siehst sie deshalb nur mit **getrennt gemessenem Heizstrom**, nur auf der Achse *Saison* und erst, wenn eine Heizperiode auch eine Außentemperatur-Messreihe hat — der Vergleich zweier Winter kommt mit der nächsten Heizperiode. Ein **von Hand gepflegter Monatsdurchschnitt** dient dabei ausdrücklich **nicht** als Quelle: Er unterschätzt die Heizgradtage in Übergangsmonaten deutlich, weil warme und kalte Tage sich darin wegmitteln. ⚠ **Auch dann nicht, wenn das Feld *Ø Temperatur* im Monatsabschluss inzwischen automatisch gefüllt wird** — die Heizgradtage lesen die **Tagesreihe** direkt und rechnen jeden Tag einzeln; ein Monatsmittel, egal woher, kann das nicht ersetzen. Steht keine Zahl da, sagt eedc daneben, was fehlt.

**„Meine Wärmepumpe läuft zur Hälfte mit PV — warum senkt das ihre Stromkosten nicht?"**
Weil dieser Strom schon auf der anderen Seite gutgeschrieben ist. Deine PV-Anlage bekommt für jede selbst verbrauchte Kilowattstunde den vollen Netzbezugspreis gutgeschrieben — das ist die Position *Eigenverbrauch*. Würde eedc denselben Strom bei der Wärmepumpe noch einmal abziehen, stünde er zweimal im Ergebnis. Deshalb trägt die Wärmepumpe **ihren ganzen Strom** zum Netztarif, in der Ersparnis wie in der CO₂-Bilanz. Das Feld *PV-Anteil (%)* am Gerät bleibt trotzdem sinnvoll: Es sagt eedc, **wie viel** deines PV-Stroms in die Wärmepumpe geht, und wirkt damit auf die Eigenverbrauchs-Prognose und darauf, welcher Komponente der Eigenverbrauch zugerechnet wird. Es ist eine Mengenangabe, keine Preisangabe. Hast du es nie ausgefüllt, rechnet eedc mit 30 %. Leerst du einen eingetragenen Wert, bleibt das Feld leer, und die Wärmepumpe zählt nicht mehr zum Prognose-Mittel der PV-Anteile.

**„Ich vergleiche meine JAZ mit der aus dem Datenblatt."**
Das sind verschiedene Größen. Datenblatt-Werte (SCOP, COP, SEER) entstehen auf einem Prüfstand unter genormten Bedingungen. eedc misst deine Anlage in deinem Haus, mit deinen Vorlauftemperaturen, deinem Warmwasserbedarf und deinem Wetter. **Eine niedrigere Zahl ist kein Defekt** — sie ist die Realität, für die du dich interessierst.

---

> **Rückmeldungen willkommen.** Diese Fläche ist stark von Tester-Rückmeldungen geprägt — mehrere Abschnitte hier existieren, weil jemand gefragt hat, warum eine Anzeige aussieht, wie sie aussieht. Wenn dir etwas begegnet, das du nicht erklären kannst: melden, das ist wertvoll.
