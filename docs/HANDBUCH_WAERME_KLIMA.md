# eedc Handbuch — Wärme & Klima

**Version 4.0** | Stand: 2026-08-27

> Dieses Handbuch ist Teil der eedc-Dokumentation.
> Siehe auch: [Bedienung](HANDBUCH_BEDIENUNG.md) | [Einstellungen & Datenquellen](HANDBUCH_EINSTELLUNGEN.md) | [Daten-Checker](HANDBUCH_DATEN_CHECKER.md) | [Berechnungen & Kennzahlen](BERECHNUNGEN.md) | [Sensor-Referenz](SENSOR-REFERENZ.md) | [Glossar](GLOSSAR.md)

---

## Inhaltsverzeichnis

1. [Was diese Fläche umfasst](#1-was-diese-fläche-umfasst)
2. [Voraussetzungen — welcher Zähler für welche Anzeige](#2-voraussetzungen--welcher-zähler-für-welche-anzeige)
3. [Was eedc bewusst *nicht* sagt](#3-was-eedc-bewusst-nicht-sagt)
4. [Wann eine Kennzahl verschwindet — und warum das richtig ist](#4-wann-eine-kennzahl-verschwindet--und-warum-das-richtig-ist)
5. [Sensoren zuordnen, Schritt für Schritt](#5-sensoren-zuordnen-schritt-für-schritt)
6. [Sechs Anlagen, sechs Ergebnisse](#6-sechs-anlagen-sechs-ergebnisse)
7. [Häufige Missverständnisse](#7-häufige-missverständnisse)

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
| **Cockpit → Tag** | Block *Wärme/Klima*: Arbeitszahl, Wärme, Strom, Ersparnis, Kompressor-Starts, Betriebsart-Aufteilung — **alles tagesgenau** |
| **Cockpit → Monat** | derselbe Block auf Monatsbasis, dazu die Arbeitszahlen je Funktion |
| **Cockpit → Jahr** | Jahressummen, Block *CO₂-Bilanz* |
| **Komponenten → Wärmepumpe** | je Gerät einzeln: Status, Verlauf, Monats-/Saisonvergleich, Kostenvergleich gegen Gas/Öl |
| **Auswertungen → CO₂** | Einsparung inkl. Wärmepumpen-Anteil |
| **Einstellungen → Datenquellen** | die Zuordnung der Zähler ([§5](#5-sensoren-zuordnen-schritt-für-schritt)) |

> **Der Block *Wärme/Klima* im Cockpit fasst alle Geräte zusammen**, der Komponenten-Hub zeigt sie **einzeln**. Das ist kein Widerspruch, sondern der wichtigste Unterschied auf dieser Fläche — siehe [§7](#7-häufige-missverständnisse).

---

## 2. Voraussetzungen — welcher Zähler für welche Anzeige

Diese Tabelle ist der Kern dieses Handbuchs. Sie beantwortet die Frage, die fast alle Rückfragen auslöst: **„Warum steht da ein Strich?"**

| Was du sehen willst | Was du dafür brauchst | Ohne das … |
|---------------------|------------------------|------------|
| **Stromverbrauch** der Anlage | *Stromverbrauch* (kWh) — **oder** *Strom Heizen* + *Strom Warmwasser* bei getrennter Messung | keine Auswertung, das Gerät fehlt in der Verbrauchsseite |
| **Wärme erzeugt** | Wärmemengenzähler: *Heizwärme* (kWh) und/oder *Warmwasser* (kWh) | eedc **rechnet** sie aus Strom × gepflegter Arbeitszahl — und kennzeichnet sie als abgeleitet |
| **Arbeitszahl (JAZ)** | beides: Strom **und** gemessene Wärme | „—" mit Grund |
| **Arbeitszahl Heizen / Warmwasser getrennt** | getrennte Strommessung **und** getrennte Wärmemengen | „—" mit Grund *„Strom nicht getrennt je Funktion gemessen"* |
| **Arbeitszahl Kühlen** | *Strom Kühlbetrieb* **und** *Nutzenergie Kühlbetrieb* (Kältemengenzähler) | „—" mit Grund *„kein Kältemengenzähler zugeordnet"* |
| **Aufteilung Heizen/Kühlen/Lüften/Entfeuchten** | entweder **gemessene** Betriebsart-Zähler **oder** ein *Betriebsmodus*-Sensor, den eedc laufend mitliest | der Block fehlt ganz — und zwar bewusst, statt vier Nullen zu zeigen |
| **Ersparnis vs. Gas/Öl** | gemessene oder abgeleitete Wärme **und** ein Alt-Preis am Gerät | „—" |
| **CO₂-Einsparung** | Stromverbrauch und Wärme | der Wärmepumpen-Anteil fehlt in der Bilanz |
| **Kompressor-Starts / Betriebsstunden** | ein *Total-Increasing*-Zähler dafür | die Kacheln erscheinen gar nicht |
| **Tages**werte statt nur Monatswerte | dieselben Zähler — aber **fortlaufend mitgeschrieben** | „—" mit Grund, siehe Kasten |

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

### Kumulativ oder Tageszähler — beides geht

eedc erwartet **fortlaufend steigende Zählerstände** („total increasing"). Ein Sensor, der jede Nacht auf 0 zurückspringt (`utility_meter` mit Tages-Zyklus), funktioniert über Home Assistant trotzdem: Dort liest eedc die reset-bereinigte Summe, nicht den Rohwert.

⚠ **Auf dem MQTT-/Standalone-Pfad gilt das nicht** — dort kommt der rohe veröffentlichte Wert an. Springt er zurück, erkennt eedc das und sagt für diesen Tag **nichts**, statt eine falsche Zahl zu bilden: *„Der Zähler ist an diesem Tag zurückgesprungen."*

---

## 3. Was eedc bewusst *nicht* sagt

Dieser Abschnitt ist so wichtig wie die Tabelle darüber. **Mehrere Dinge fehlen mit Absicht** — sie zu ergänzen wäre eine Verschlechterung, keine Verbesserung.

**Kein „SEER".** Für den Kühlbetrieb bildet eedc die **Arbeitszahl Kühlen** = Kältemenge ÷ Kühlstrom. Sie heißt **nicht** SEER, obwohl es naheläge: SEER ist eine genormte Größe, die auf einem Prüfstand unter festgelegten Bedingungen ermittelt wird. Was eedc bilden kann, ist das Verhältnis deiner beiden Zähler über einen Zeitraum. Sie „SEER" zu nennen würde eine Vergleichbarkeit mit dem Datenblatt behaupten, die sie nicht hat.

**Keine geschätzte Kältemenge.** Ohne Kältemengenzähler gibt es keine Arbeitszahl Kühlen. Man könnte sie aus einem angenommenen Wirkungsgrad rechnen — dann käme genau der Faktor zurück, mit dem gerechnet wurde. Das wäre keine Messung, sondern eine Rückgabe der eigenen Annahme.

**Keine Bewertung von Lüften und Entfeuchten.** Beide Betriebsarten **erscheinen** in der Aufteilung, wenn du dafür Zähler hast. Eine Kennzahl bekommen sie nicht: Sie erzeugen keine Nutzenergie, die sich messen ließe. Ihr Strom fällt deshalb auch **aus dem Nenner der Arbeitszahl** — sonst drückte er eine Zahl, mit der er nichts zu tun hat.

**Keine Note für deine Anlage.** eedc rechnet mit deinen Zahlen, es bewertet dich nicht. Eine Arbeitszahl von 1,8 ist kein Mangel, sondern die Beschreibung einer Anlage, die viel direkt elektrisch heizt. Steht sie unter 2, schreibt eedc genau das daneben:

> *„Eine Arbeitszahl nahe 1 entsteht, wenn ein großer Teil der Wärme direkt elektrisch erzeugt wurde (Heizstab, Zusatz- oder Notheizung). Die Zahl beschreibt die Anlage in diesem Zeitraum, sie ist kein Fehler."*

**Keine 0, wo „unbekannt" gemeint ist.** Eine 0 heißt „gemessen und es war null". Wo eedc etwas nicht weiß, steht „—" **mit dem Grund daneben** — nie eine Null, die wie eine Messung aussieht.

**Kein Vergleich von passiv gegen aktiv gekühlt.** Passive Kühlung läuft nur über Umwälzpumpen und erreicht ein Vielfaches der Effizienz einer aktiv gekühlten Anlage. Beide Zahlen sind für sich richtig; sie gegeneinander zu stellen wäre die Falschaussage. Deshalb gibt es am Gerät das Feld **„Kühlung: aktiv oder passiv"** — es ändert **keine** deiner Zahlen, es hält dich nur aus dem falschen Vergleich heraus.

---

## 4. Wann eine Kennzahl verschwindet — und warum das richtig ist

**Eine Arbeitszahl ist Wärme ÷ Strom. Sie ist nur dann eine Aussage, wenn Zähler und Nenner dasselbe meinen** — dieselbe Anlage, dieselbe Funktion, denselben Zeitraum. Wo das nicht gesichert ist, lässt eedc die Zahl weg und schreibt den Grund hin.

Das ist die unangenehmste Eigenschaft dieser Fläche und zugleich ihre wichtigste. **Eine plausible falsche Zahl ist schlimmer als ein ehrlicher Strich** — sie landet im Jahresbericht, im Community-Vergleich und in deiner Entscheidung über die nächste Investition.

### Die Gründe, wörtlich

| Grund in der App | Was dahintersteckt | Was du tun kannst |
|------------------|--------------------|-------------------|
| **kein Stromverbrauch erfasst** | Für den Zeitraum liegt kein Strom vor. | Zähler zuordnen oder Monatswert pflegen |
| **kein Wärmemengenzähler zugeordnet** | Es gibt keine gemessene Wärme. | Zähler zuordnen — oder die gepflegte Arbeitszahl nutzen (dann ist die Wärme *abgeleitet*) |
| **Wärme ist gerechnet, nicht gemessen** | Die Wärme kam aus *Strom × Arbeitszahl*. Sie durch denselben Strom zu teilen gäbe genau die Arbeitszahl zurück, mit der gerechnet wurde. | nichts — die Zahl wäre zirkulär |
| **nur Kühlbetrieb in diesem Zeitraum** | Der Zähler lief, aber nicht fürs Heizen. „Kein Stromverbrauch" wäre hier die falsche Auskunft. | nichts, das ist die Wahrheit über einen Sommermonat |
| **Wärmepumpe und Klimaanlage in einer Zahl** | Der Block fasst eine klassische Wärmepumpe und eine Split-Klimaanlage zusammen. Beide heizen, aber sie sind nicht vergleichbar: andere Nutzenergie, anderer Maßstab. Eine gemeinsame Arbeitszahl wäre ein Quotient aus zwei Welten. | jedes Gerät einzeln im Komponenten-Hub ansehen — dort hat jedes seine eigene Zahl |
| **nicht alle Geräte melden Wärme** | Der Block fasst mehrere Geräte zusammen; im Nenner steht der Strom von allen, im Zähler die Wärme von einem. | einzelnes Gerät im Komponenten-Hub ansehen |
| **Heizstab-Strom auf dem WP-Zähler** | Deine eigene Angabe im Feld *Fremdanteil auf den Zählern*. Der Stromwert ist zu groß. | Angabe korrigieren, wenn sie nicht mehr stimmt |
| **zweiter Erzeuger am Wärmezähler** | Dieselbe Angabe, andere Richtung: Ein Gas- oder Ölkessel speist denselben Heizkreis. Der Wärmewert ist zu groß. | dito |
| **Zähler messen verschiedene Zeiträume** | Strom und Wärme stammen aus verschieden langen Messzeiträumen. | Lücken im Monatsabschluss schließen |
| **Strom nicht getrennt je Funktion gemessen** | Betrifft nur die Arbeitszahlen *Heizen* und *Warmwasser*. | getrennte Strommessung einschalten und zuordnen |
| **kein Kältemengenzähler zugeordnet** | Betrifft nur die Arbeitszahl *Kühlen*. | Kältemengenzähler zuordnen — oder es bleibt so |

### Und drei Gründe, die nur der **Tag** kennt

Sie beantworten die Frage „Warum ist der Tag leer, obwohl der Monat gefüllt ist?" (siehe [§2](#2-voraussetzungen--welcher-zähler-für-welche-anzeige)):

- **Kein Zähler zugeordnet** — mit dem Weg dorthin.
- **Zähler zugeordnet, aber für diesen Tag liegen keine Zählerstände vor. Tageswerte entstehen ab der Zuordnung; frühere Tage lassen sich in der Reparatur-Werkbank nachrechnen.** Der Regelfall kurz nach einer Zuordnung.
- **Der Zähler ist an diesem Tag zurückgesprungen — für diesen Tag gibt es deshalb keine Aussage.**

> ⛔ **Bis v4.0.28 stand an dieser Stelle unterschiedslos *„Sensor zuordnen"*** — auch bei jemandem, der zugeordnet hatte. Ein Tester hat daraufhin zu Recht gefragt, was die Anzeige ihm eigentlich sagen will. **Eine falsche Ursache ist schlimmer als keine:** Ohne Hinweis sucht man selbst, mit einem falschen sucht man an der falschen Stelle.

### Der Fremdanteil — die einzige Angabe, die eedc nicht messen kann

Zwei Lagen machen jede Arbeitszahl unbrauchbar, **ohne dass man es den Zahlen ansieht**:

1. Der **Heizstab hängt am Stromzähler** der Wärmepumpe, seine Wärme läuft aber nicht über den Wärmemengenzähler. ⇒ Der Stromwert ist zu groß, die Arbeitszahl zu klein.
2. Ein **Gas- oder Ölkessel speist denselben Heizkreis**, den der Wärmemengenzähler misst; der Stromzähler erfasst nur die Wärmepumpe. ⇒ Der Wärmewert ist zu groß, die Arbeitszahl zu gut.

Beide trägst du am Gerät unter **„Fremdanteil auf den Zählern"** ein. **Sie ändern keine einzige deiner Mengen** — Strom, Wärme, Kosten und CO₂ bleiben, wie sie sind. eedc lässt nur die Arbeitszahl weg und schreibt den Grund daneben.

> **Warum es ein Feld ist und nicht zwei Kennzeichen:** Es ist *eine* Regel — Zähler und Nenner müssen dasselbe meinen. Ein Kennzeichen je Beispiel hätte eine Fallsammlung daraus gemacht, und der bivalente Fall (Nr. 2) blieb genau deshalb jahrelang unsichtbar.

---

## 5. Sensoren zuordnen, Schritt für Schritt

Alles läuft über **Einstellungen → Datenquellen**. Dort steht je Gerät eine Liste von Feldern; neben jedem Feld wählst du die Quelle: **HA-Sensor**, **MQTT**, **Connector** oder **Keine**.

### Schritt 1 — Gerät anlegen und die Bauart wählen

*Einstellungen → Investitionen → Neu → Wärmepumpe.* Die **Wärmepumpenart** bestimmt, welche Felder oben stehen:

| Art | Felder oben | Nicht angeboten (aber erreichbar) |
|-----|-------------|-----------------------------------|
| **Luft-Wasser / Sole-Wasser / Grundwasser** | Stromverbrauch, Heizwärme, Warmwasser | Betriebsart-Zähler (Kühlen, Lüften, Entfeuchten) |
| **Luft-Luft (Klimaanlage)** | Stromverbrauch, Betriebsart-Zähler | Warmwasser — den Kreis gibt es dort nicht |
| **Brauchwasser (nur Warmwasser)** | Stromverbrauch, Warmwasser | Heizwärme, Strom Heizen |

> **„Nicht angeboten" heißt nicht „gesperrt".** Alles Übrige liegt unter **„Weitere Größen erfassen"** und rückt nach oben, sobald du dort einen Sensor einträgst. Die einzige echte Ausnahme ist **Warmwasser an einer Luft-Luft-Klimaanlage**: Ein gefüllter Wert erzeugt dort eine Ersparnis, die es nicht gibt.

### Schritt 2 — Entscheiden: ein Zähler oder getrennte?

Am Gerät gibt es den Schalter **„Getrennte Strommessung"**.

- **Aus** (Standard): Du ordnest **einen** Zähler zu — *Stromverbrauch*.
- **Ein**: Du ordnest **zwei** zu — *Strom Heizen* und *Strom Warmwasser*. Der Gesamtverbrauch ist dann die Summe; ein zusätzlicher Gesamtzähler wird nicht mehr erwartet.

> ⚠ **Der Schalter ist eine Zusage, kein Wunsch.** Steht er auf *ein* und du ordnest die beiden Zähler nicht zu, hat das Gerät **keinen** Stromverbrauch — nicht nur keine getrennte Aufteilung. Genau daran ist ein Tester hängen geblieben: Er hatte einen Gesamtzähler, den Schalter aber eingeschaltet; der Block *Wärme/Klima* fehlte daraufhin in der Tagesansicht komplett. **Ausschalten hat es gelöst.**

### Schritt 3 — Die Wärme zuordnen (oder bewusst darauf verzichten)

*Heizwärme* und *Warmwasser* sind **thermische** Größen in kWh — die abgegebene Wärme, **nicht** der Strom. Das ist die häufigste Verwechslung überhaupt.

Ohne Wärmemengenzähler rechnet eedc die Heizwärme aus *Strom × gepflegter Arbeitszahl* und **kennzeichnet sie als abgeleitet**. Die Mengen sind dann eine Modellrechnung, die Arbeitszahl fällt weg (sie wäre zirkulär). Das ist ein legitimer Betriebszustand, kein Mangel.

### Schritt 4 — Betriebsart erfassen (optional, aber lohnend)

Es gibt **zwei Wege**, und **gemessen schlägt abgeleitet**:

**Weg A — Betriebsart-Zähler (genauer).** Du ordnest *Strom Heizbetrieb*, *Strom Kühlbetrieb*, *Strom Lüftbetrieb*, *Strom Entfeuchtungsbetrieb* zu, soweit vorhanden. eedc rechnet nichts, es liest ab.

> ⚑ **Für Warmwasser gibt es hier bewusst kein Feld.** Wer seinen Warmwasser-Strom getrennt misst, trägt ihn unter *Strom Warmwasser* ein (Schritt 2) und bekommt daraus seine *Arbeitszahl · Warmwasser*. Ein zweites Feld für dieselbe Zahl wäre nur eine Gelegenheit, beide versehentlich zu addieren.

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
> Die 20 W sind eine Schwelle gegen Standby-Rauschen — nimm einen Wert, der zu deinem Gerät passt.
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

> ⛔ **Watt ist keine Kilowattstunde.** Ein Leistungssensor gehört **nie** in ein kWh-Feld. Die Stundenwerte eines Leistungssensors ergeben zwar eine plausible Zahl — sie speist aber nicht die Zählerpfade, aus denen der Block *Wärme/Klima* entsteht. Liefert dein Gerät **nur** Leistung, baue in Home Assistant unter *Helfer → Integral-Sensor* (Riemannsche Summe) einen kWh-Zähler daraus.

### Schritt 7 — Den Daten-Checker fragen

*Einstellungen → Daten.* Er nennt fehlende Zuordnungen, Monate ohne Werte und Widersprüche — und zu jedem Befund den Weg dorthin. **Ein Befund, den du nicht auflösen kannst, ist ein Fehler im Checker und keine Aufgabe für dich.** Melde ihn.

---

## 6. Sechs Anlagen, sechs Ergebnisse

Diese sechs Bauformen sind **nicht erfunden** — fünf davon stammen aus Rückmeldungen von Testern, und alle sechs stehen als nachgestellte Anlagen im Prüflauf von eedc. Sie zeigen, was du bei welcher Ausstattung bekommst.

### A — Wärmepumpe **und** Klimaanlage, nur die Wärmepumpe meldet Wärme

*„Ist es nicht sinnvoller, die Luft-Wasser-Wärmepumpe von der Luft-Luft-Klimaanlage komplett zu trennen?"*

WP: 3000 kWh Wärme auf 800 kWh Strom. Klimaanlage: 200 kWh Strom, keine Wärme.

| Sicht | Ergebnis |
|-------|----------|
| **Cockpit** (beide zusammen) | Arbeitszahl **„—"**, Grund: *Wärmepumpe und Klimaanlage in einer Zahl* |
| **Komponenten → Wärmepumpe** | **3,75** (3000 ÷ 800) — sauber abgegrenzt |

⭐ **Die Mengen bleiben in beiden Sichten vollständig.** Weg ist nur die Zahl, die 3000 ÷ 1000 gerechnet hätte — Wärme von einem Gerät, Strom von zweien.

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
| Arbeitszahl | „—", *Wärmepumpe und Klimaanlage in einer Zahl* |

⭐ **Kilowattstunden darf man über Geräte addieren, Stunden nicht.** Zwei Geräte, die dieselben 18 Stunden liefen, ergeben 18 Stunden Beobachtung. Bis v4.0.28 stand dort 36 — an einem Tag.

⭐ **Der Block nennt seine Geräte — und seit v4.0.31 auch unter *Cockpit → Tag*.** Solange dort niemand sagte, dass zwei Geräte in einer Summe stecken, war die Zahl nicht nachvollziehbar: Wer den Balken mit dem Zähler **einer** seiner Anlagen verglich, fand eine Differenz, für die es keine Erklärung gab. Monat und Jahr nannten die Namen längst, der Tag als einzige Sicht nicht.

**Die Mengen bleiben zusammen, und das ist Absicht.** Kilowattstunden über Geräte zu addieren ist richtig — was fehlte, war die Auskunft darüber. Wer die Geräte einzeln sehen will, öffnet *Komponenten → Wärmepumpe*; dort steht jedes für sich, mit eigener Arbeitszahl.

### F — Brauchwasser-Wärmepumpe

Ein Gerät, das ausschließlich Warmwasser macht.

Wähle die Wärmepumpenart **Brauchwasser**. eedc fragt dann nur noch nach *Stromverbrauch* und *Warmwasser* — die Heiz-Achse wird weder angeboten noch erwartet, und der Daten-Checker verlangt sie nicht.

> **Hast du doch einen Heizzähler** (manche Geräte unterstützen einen kleinen Heizkreis): Trag ihn unter *„Weitere Größen erfassen"* ein. Die Bauart ist ein Vorschlag, kein Verbot.

---

## 7. Häufige Missverständnisse

**„Der Block zeigt eine andere Arbeitszahl als der Komponenten-Hub."**
Das ist so gewollt und der wichtigste Unterschied auf dieser Fläche. Der Block *Wärme/Klima* im Cockpit fasst **alle** Geräte zusammen; der Hub zeigt **eines**. Bei gemischter Ausstattung kann der Block deshalb „—" sagen, während das einzelne Gerät eine saubere Zahl hat. Unter dem Block steht, aus welchen Geräten er entsteht.

**„Heizwärme ist doch der Stromverbrauch fürs Heizen."**
Nein. *Heizwärme* ist die **abgegebene thermische Wärme**. Der Strom fürs Heizen heißt *Strom Heizen*. Trägst du Strom in ein Wärmefeld ein, kommt eine Arbeitszahl um 1 heraus.

**„Die Summe der Tage passt nicht zum Monat."**
Bei der CO₂-Einsparung ist das **so vorgesehen**: Der Tageswert trägt nur den PV-Anteil, weil es Wärmepumpen-Wärme und E-Auto-Kilometer nur monatlich gibt. Die Spalte heißt deshalb ausdrücklich *„CO₂-Einsparung (PV)"*.

**„Der Balken summiert sich nicht auf den Wert der Kachel darüber."**
Richtig — und seit v4.0.29 steht darunter, warum: **„Aufgeteilte Menge: 30 von 284 kWh".** Die Aufteilung entsteht nur für Geräte und Zeiträume, in denen eedc die Betriebsart mitlesen konnte; die Kachel zählt alle Geräte.

**„‚Nicht aufgeteilt' ist fast alles — die Aufteilung ist kaputt."**
Meistens nicht. *Nicht aufgeteilt* ist Standby, alles, was weder Heizen noch Kühlen war, **und die Zeit, in der eedc keinen Modus mitlesen konnte**. Bei einem Gerät, das überwiegend aus war, ist ein hoher Anteil die Wahrheit. Die Zeile *Modus erfasst* sagt dir, wie lange mitgelesen wurde.

**„Meine Arbeitszahl ist plötzlich niedriger geworden."**
Wenn du getrennte Zähler samt Kühlmessung führst: Ja, und das war eine Korrektur. Bis v4.0.28 fehlte der Kühlstrom im Verbrauch der Wärmepumpe und wurde zugleich ein zweites Mal aus dem Nenner gezogen — die Arbeitszahl fiel rund 12 % zu gut aus. Der Verbrauch steigt jetzt um den Kühlanteil, die Zahl sinkt auf ihren richtigen Wert.

**„Meine Arbeitszahl ist plötzlich höher geworden."**
Wenn du Lüften oder Entfeuchten getrennt misst: Ja. Ihr Strom fällt seit v4.0.29 aus dem Nenner, weil sie keine messbare Nutzenergie erzeugen. **Deine Mengen ändern sich dadurch nicht.**

**„eedc sagt, ich soll einen Sensor zuordnen, den ich habe."**
Das war ein Fehler und ist behoben. Bis v4.0.28 hing an jedem „—" derselbe fest eingebaute Satz. Seit v4.0.29 nennt eedc den zutreffenden Grund — siehe [§4](#4-wann-eine-kennzahl-verschwindet--und-warum-das-richtig-ist). Begegnet dir trotzdem ein Hinweis, den keine Eingabe abstellt: **melden.**

**„Ich vergleiche meine JAZ mit der aus dem Datenblatt."**
Das sind verschiedene Größen. Datenblatt-Werte (SCOP, COP, SEER) entstehen auf einem Prüfstand unter genormten Bedingungen. eedc misst deine Anlage in deinem Haus, mit deinen Vorlauftemperaturen, deinem Warmwasserbedarf und deinem Wetter. **Eine niedrigere Zahl ist kein Defekt** — sie ist die Realität, für die du dich interessierst.

---

> **Rückmeldungen willkommen.** Diese Fläche ist stark von Tester-Rückmeldungen geprägt — mehrere Abschnitte hier existieren, weil jemand gefragt hat, warum eine Anzeige aussieht, wie sie aussieht. Wenn dir etwas begegnet, das du nicht erklären kannst: melden, das ist wertvoll.
