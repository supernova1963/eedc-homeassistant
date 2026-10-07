# Konzept — Wärme/Klima: Heizen · Warmwasser · Kühlen

> ## Status (Mess-Datum 2026-09-13): **das Konzept der Fläche — gebaut**
>
> **Was dieses Dokument ist.** Die eine fachliche Beschreibung der Fläche *Wärme/Klima* in eedc:
> welche Größen es gibt, wie sie erfasst werden, wann aus ihnen eine Kennzahl werden darf, welche
> Sicht was zeigt — und was die Fläche bewusst nicht kann. Es beschreibt den **gebauten Stand**,
> nicht die Baugeschichte, und jede Regel darin hat eine Codestelle oder einen Wächter
> ([Kapitel 11](#11-wächter-und-proben--was-hält-welche-regel)).
>
> ⛔ **Was es nicht ist: eine Anwender-Anleitung.** Wer wissen will, welchen Sensor er wohin
> zuordnet und was er dann sieht, liest [`HANDBUCH_WAERME_KLIMA.md`](HANDBUCH_WAERME_KLIMA.md).
> Dieses Dokument sagt, **warum** es so ist.
>
> **Es trägt bewusst keine Versionsnummer, nur ein Mess-Datum** — ein Status, der eine Version
> nennt, altert garantiert.
>
> ### Wo du stattdessen nachsiehst
>
> | Frage | Dokument |
> | --- | --- |
> | **Was sieht und tut der Anwender?** | [`HANDBUCH_WAERME_KLIMA.md`](HANDBUCH_WAERME_KLIMA.md) — Voraussetzungen je Anzeige, Zuordnung Schritt für Schritt, sieben Anlagen als Beispiel, die Sperrgründe im Wortlaut |
> | **Wie lautet die Formel je Kennzahl?** | [`BERECHNUNGEN.md`](BERECHNUNGEN.md) |
> | **Welcher Sensor, welches MQTT-Topic?** | [`SENSOR-REFERENZ.md`](SENSOR-REFERENZ.md) |
> | *Wo* eine Aggregat-Formel definiert wird | [`ADR-001-BERECHNUNGS-LAYER.md`](ADR-001-BERECHNUNGS-LAYER.md) |
> | *Was* ein Wert behaupten darf und woher er kommt (P1–P13) | [`ADR-002-WURZELMUSTER.md`](ADR-002-WURZELMUSTER.md) |
> | Die Entstehungsgeschichte der Split-Klimaanlage | [`KONZEPT-263-klima-split.md`](KONZEPT-263-klima-split.md) · [`KONZEPT-263-INNENGERAETE.md`](KONZEPT-263-INNENGERAETE.md) — beide sind **Kapitel 8** dieses Dokuments |
>
> ### Warum es dieses Dokument gibt
>
> Die Fläche war auf vier Papiere verteilt: zwei Bauform-Konzepte in `docs/` (#263) und zwei
> Maintainer-interne Dokumente (Zielbild und Bestandsaufnahme). **Die Fehler dieser Fläche saßen
> genau an der Naht.** Eine Split-Klimaanlage hat keinen Warmwasserkreis — jede Aussage über sie,
> die Warmwasser nicht erwähnt, ist für dieses Gerät richtig und für die Fläche unvollständig. So
> ist der Betriebsmodus-Kanon ohne `warmwasser` entstanden: ein Satz über drei Melder mit
> Klimaanlagen, gelesen als Regel über alle Wärmepumpen. Das eine Konzept ist die Antwort darauf
> (Entscheid Gernot, 2026-08-26, **E5**).

---

## Inhalt

1. [Der Grundsatz](#1-der-grundsatz--der-zähler-entscheidet-nicht-die-bauart)
2. [Die Größen und ihre Auflösungen](#2-die-größen-und-ihre-auflösungen)
3. [Der Erfassungs-Kanon K1–K5](#3-der-erfassungs-kanon--welcher-weg-gilt-wenn-mehrere-da-sind)
4. [Die Abgrenzungsregel R2](#4-die-abgrenzungsregel-r2--wann-eine-kennzahl-erscheinen-darf)
5. [Die Kennzahlen](#5-die-kennzahlen--was-aus-e-und-q-folgt)
6. [Die Sichten und der Verlauf](#6-die-sichten-und-der-verlauf)
7. [Mehrere Geräte](#7-mehrere-geräte)
8. [Split-Klimaanlagen](#8-split-klimaanlagen--die-bauform-als-kapitel)
9. [Datenquellen-Fläche und Daten-Checker](#9-datenquellen-fläche-und-daten-checker)
10. [Grenzen und Nicht-Ziele](#10-grenzen-und-nicht-ziele)
11. [Wächter und Proben](#11-wächter-und-proben--was-hält-welche-regel)
12. [Bezug](#12-bezug)
13. [Anhang: Entscheidungs-Register](#anhang--entscheidungs-register)

---

## 1. Der Grundsatz — der Zähler entscheidet, nicht die Bauart

**eedc misst Energie und rechnet daraus Kennzahlen. Eine Kennzahl darf nur erscheinen, wenn Zähler
und Nutzen dieselbe Abgrenzung haben** — dasselbe Gerät, dieselbe Funktion, denselben Zeitraum.

Das klingt selbstverständlich und ist der Kern der ganzen Fläche: Fast jeder gemeldete Fehler hier
war eine verletzte Abgrenzung — Strom von zwei Geräten gegen die Wärme von einem, Strom eines
Monats gegen die Wärme eines Abschlusses, ein Balken „Wärme" neben einem Balken „Strom" ohne
Beschriftung. Die Gegenprobe zu jeder Anzeige lautet deshalb: *Was genau steht im Zähler, und was
genau steht im Nutzen?* Lautet die Antwort nicht für beide gleich, gibt es keine Kennzahl —
sondern zwei Mengen nebeneinander.

Daraus folgen zwei Regeln, die alles Weitere tragen:

> ### R1 · Angeboten wird jede Größe, die das Gerät liefern kann — und was es liefern kann, sagt der zugeordnete Zähler, nicht seine Bauart.
>
> Es gibt **keine** bauartabhängige Feldliste. Wer einen Kühlzähler zuordnet, hat ein kühlendes
> Gerät; wer keinen zuordnet, sieht die Achse nicht. Die Bauart (`wp_art`) schlägt nur noch vor,
> welche Felder oben stehen.

> ### R2 · Eine Kennzahl Q/E erscheint nur, wenn Q und E dieselbe Abgrenzung tragen — dasselbe Gerät, dieselbe Funktion, denselben Zeitraum.
>
> Weicht eine der drei ab, zeigt eedc **die Mengen und den Grund**, nie den Quotienten.

**Warum R1 keine Bequemlichkeit ist, sondern eine Modellentscheidung.** Bis v4.0.28 leitete eedc
die Felder eines Geräts aus seiner Bauart ab. Eine Bauart-Tabelle hat sechs Zeilen, weil jemandem
sechs eingefallen sind — die siebte Bauart gibt es trotzdem. Der Fachraum ist nicht die Menge der
Bauarten, er ist das Kreuzprodukt aus **Funktion** und **Größe** ([Kapitel 2](#2-die-größen-und-ihre-auflösungen)).
Mit R1 brauchen passive Kühlung, Brauchwasser-Wärmepumpe und bivalente Anlagen **kein einziges
neues Feld** — sie waren nie ein Umfangsproblem, sondern das Symptom eines zu engen Modells.

⚠ **R1 hat einen Preis, und er gehört in jede Anwenderfläche:** eedc kann nicht wissen, ob ein
Gerät etwas *nicht tut* oder ob es nur *nicht gemessen* wird. Genau deshalb steht bei jeder
fehlenden Kennzahl ein **Grund** statt einer geschätzten Zahl.

### Die Arbeitsteilung im Produkt

| Ort | Achse | zeigt |
| --- | --- | --- |
| **Cockpit** (Live · Tag · Monat · Jahr) | **Zeit** | die Anlage als Ganzes, je Zeitraum |
| **Komponenten → Wärme/Klima** (Hub) | **Gerät** | ein Gerät über seine Historie, samt Herkunft jeder Zahl |

Wer beides mischt, bekommt zwei Sichten, die dasselbe verschieden sagen. Der Weg vom einen zum
anderen ist gebaut: Sperrt eine anlagenweite Kennzahl aus einem Grund, den der Hub je Gerät
beantworten kann, steht im Cockpit ein Link dorthin ([Kapitel 7](#7-mehrere-geräte)).

### Die Leitregel für die Zeit

> **Mengen und Form: bis auf die Stunde. Kennzahlen: ab dem Tag, belastbar ab dem Monat.**

Der Grund ist ein **Zeitversatz**, keine fehlende Messung: Wärme gibt es stündlich (der
Wärmemengenzähler ist ein kumulativer Zähler wie jeder andere). Aber Strom und Wärme *derselben*
Stunde gehören nicht zusammen — Aufheizen, Nachlauf und Abtauung verschieben die abgegebene Wärme
gegenüber dem aufgenommenen Strom. Ein Quotient braucht einen Zeitraum, in dem beide
zusammengehören, und das ist frühestens der Tag.

---

## 2. Die Größen und ihre Auflösungen

### 2.1 Der Fachraum — Funktion × Größe

Für **jede** Funktion gibt es genau zwei Größen; alles Weitere ist daraus abgeleitet.

| | **E** — Strom (kWh, elektrisch) | **Q** — Nutzenergie (kWh, thermisch) |
| --- | --- | --- |
| **Heizen** | E_heiz | Q_heiz (Wärme) |
| **Warmwasser** | E_ww | Q_ww (Wärme) |
| **Kühlen** | E_kühl | Q_kälte (**Kälte**, nicht Wärme) |
| **Lüften** | E_lüft | — (keine bewertete Nutzenergie) |
| **Entfeuchten** | E_entf | — (dito) |
| **gesamt** | **E_ges** — die Bilanzgröße | **Q_ges** — hat seit dem 14.09.2026 ein eigenes Feld, *Wärme gesamt* (`waerme_kwh`): der Ort für **einen** Wärmemengenzähler, der Heizung und Warmwasser zusammen misst. Steht er neben einer Aufteilung, gilt er (Gesamtwert vor Summanden); die Zeilen je Funktion sagen dann „Wärme nicht je Funktion gemessen" |

Dazu drei **Begleitgrößen**, die keine Bilanz tragen: **Betriebsmodus** (Zustand jetzt — teilt E
auf die Funktionen auf, wenn es nur *einen* Zähler gibt), **Betriebsstunden** und
**Kompressorstarts**.

**Das sind dreizehn Größen je Gerät** — zehn aus der Matrix (sechs E, vier Q) plus drei
Begleitgrößen —, **und die Liste ist abgeschlossen**: nicht weil niemandem mehr etwas einfiele,
sondern weil eine Wärmepumpe genau das tut — sie nimmt Strom auf und gibt Nutzenergie ab, in
abzählbar vielen Betriebsarten. Dazu kommen die **Momentanleistungen** als Live-Größen (gesamt,
Heizen, Warmwasser, Kühlen) und die Temperaturen. Sie tragen **keine Menge, sondern die Form**:
Aus ihnen entsteht keine Kilowattstunde und keine Kennzahl — Mengen kommen ausschließlich aus den
kWh-Zählern. Sie erscheinen im Live-Bild und im Tagesverlauf, und die **Gesamtleistung verdrängt
die feinen Felder** ([Kapitel 9](#9-datenquellen-fläche-und-daten-checker)).

⚠ **E und Q tragen dieselbe Einheit und meinen Verschiedenes.** Eine Wärmepumpe führt zwei Sorten
Kilowattstunden nebeneinander — **elektrisch** (was sie aufnimmt) und **thermisch** (was sie
abgibt). Wer die beiden verwechselt, bekommt eine Arbeitszahl, die um genau den Faktor der
Arbeitszahl danebenliegt, und zwar **lautlos**. Deshalb nennt jedes thermische Feld seine Größe im
**Label**, nicht nur im Hinweis: Eine Zuordnungsfläche, die ihre Auswahl aus Label und Einheit
baut, sieht den Hinweis nicht — genau so ist eine Umgebungswärme-Spalte im Import auf ein
Warmwasser-Feld gelandet.

⭐ **Kälte ist eine eigene Rolle, kein Wärme-Sonderfall.** Sie hat eine eigene Kennzahl, steht
nicht in `waerme_kwh`, wird im Verlauf als eigene Linie mit eigener Farbe gezeichnet — und CO₂
zählt sie nicht: vermiedene Wärme ist eine Einsparung, erzeugte Kälte ist Komfortverbrauch.

### 2.2 In welcher Auflösung eine Größe entsteht

Das ist der Knackpunkt der Fläche: Dieselbe Größe kann je nach Herkunft stündlich, täglich oder
nur monatlich vorliegen — und eine Sicht, die sie deshalb nicht zeigen kann, muss den **Grund**
nennen statt eines Strichs.

| Herkunft | Auflösung | Folge |
| --- | --- | --- |
| **kumulativer Zähler** (kWh, zählt fortlaufend hoch) | stündlich | Tag · Monat · Jahr alle möglich |
| **Momentanleistung** (W/kW) | stündlich, aber als Leistung | ergibt erst nach Integration eine Menge |
| **Handeintrag im Monatsabschluss** | monatlich | **im Tag gibt es die Größe nicht** — mit dem Satz daneben, dass sie monatlich gepflegt wird |
| **Zähler mit Tages-Reset** („…heute", Riemann-Integral) | täglich zurückgesetzt | **kein kumulativer Zähler** — wird erkannt und **abgelehnt** |
| **Betriebsart-Zähler** | stündlich messbar, aber… | der Verlauf **verteilt** den Tag auf die Stunden, statt die Stunde zu messen |

⛔ **Ein Zähler mit Tages-Reset bekommt keine Monatsmenge — und eedc rechnet auch nichts hoch**
(Entscheid Gernot, 28.08.2026). Erkennbar ist er allein an der **Monotonie**: ein kumulativer
Zähler kann nicht fallen; an seinen zwei Randständen ist er von einem ruhenden Gerät nicht
unterscheidbar. Die Menge ließe sich aus der mitgeschriebenen Standreihe summieren — das war
gebaut, gemessen (3,1 % Abschlag) und ist bewusst wieder entfernt worden: Es geht um
Datenqualität, nicht um die Unterstützung eines Zählers, von dem der Daten-Checker ohnehin abrät.
**Wer hochrechnen will, entscheidet zuerst diesen Satz um.**

⚠ **Ein Betriebsart-Zähler löst die Betriebsart auf, nicht die Funktion.** eedc bietet
Betriebsart-Zähler für Heizen · Kühlen · Lüften · Entfeuchten an, **nicht für Warmwasser** — bei
einem solchen Gerät liegt der Warmwasser-Strom im Segment *Heizen*. Wer eine Aufteilung **nach
Funktion** sehen will, braucht die Summanden `strom_heizen_kwh`/`strom_warmwasser_kwh` oder
getrennte Leistungssensoren; die Teilmengen-Familie kann sie nicht liefern
([Kapitel 3](#3-der-erfassungs-kanon--welcher-weg-gilt-wenn-mehrere-da-sind)).

---

## 3. Der Erfassungs-Kanon — welcher Weg gilt, wenn mehrere da sind

Es gibt **drei Familien** von Größen, und sie beantworten verschiedene Fragen. Wer sie
verwechselt, addiert Teilmengen zu Summanden — der Fehler, an dem schon ein Tester gescheitert
ist.

| Familie | Beispiel | Verhältnis zur Gesamtmenge |
| --- | --- | --- |
| **Gesamt** | `stromverbrauch_kwh` · Wärmemenge gesamt | **die Bilanzgröße** |
| **Summanden** | Strom Heizen + Strom Warmwasser | ergeben zusammen die Gesamtmenge |
| **Teilmengen** | Strom je Betriebsart (Heizen · Kühlen · Lüften · Entfeuchten) | **Ausschnitt**, wird nie addiert; der Rest heißt *nicht aufgeteilt* |

### Die fünf Kanon-Regeln

**K1 · Die Gesamtmenge ist immer die Wahrheit.** Jede Aufteilung steht daneben, nie an ihrer
Stelle. Bilanz, Autarkie, Kosten und CO₂ rechnen ausschließlich mit der Gesamtmenge. ⭐ **Der Satz
gilt ohne Vorbehalt, auch wenn die Aufteilung vollständig aussieht** (seit dem 14.09.2026 auch auf
der Stromseite): Ein Gesamtzähler misst, was die Achsen nicht kennen — Standby, Steuerung,
Umwälzpumpen. *Eine vollständige Aufteilung ist die Aufteilung von etwas, nicht der Beweis, dass
es nichts weiter gibt.*

**K2 · Gemessen schlägt abgeleitet — je Gerät, ganz oder gar nicht.** Liegt für ein Gerät eine
gemessene Aufteilung vor, gilt für dieses Gerät nur noch Gemessenes; eine Betriebsart ohne Zähler
erscheint dann unter *nicht aufgeteilt*. Zwei Geräte derselben Anlage dürfen verschiedene Wege
gehen. ⚠ **Der naheliegende Weg — je Betriebsart einzeln zurückfallen — ist durchgefallen:** dann
stünde in *einem* Balken die eine Hälfte aus einem Zähler und die andere aus einer Rechnung,
während die Herkunfts-Marke für beide „gemessen" sagt. *Ein halbwahres Etikett ist schlechter als
eine fehlende Zahl.*

**K3 · Ein Erfassungsweg, den es nicht gibt, entwertet keinen, den es gibt.** Ein Kennzeichen, ein
Schalter oder eine Absichtserklärung darf **niemals** dazu führen, dass ein vorhandener Zähler
ignoriert wird. Die Regel gilt in **beide** Richtungen: Wer feine Zähler hat, bekommt die feine
Aufteilung; wer sie nicht hat, behält die grobe Wahrheit. Der Satz hat keine Richtung.

**K4 · Summanden und Teilmengen schließen einander nicht aus.** Eine Wärmepumpe kann gleichzeitig
getrennte Zähler für Heizen/Warmwasser (Summanden) **und** einen Kühlzähler (Teilmenge) haben —
das ist der Normalfall einer kühlfähigen Luft-Wasser- oder Sole-Wasser-Anlage.

**K5 · Was der Kanon nicht auflösen kann, sagt er.** Bleibt nach allen Wegen ein Rest, heißt er
*nicht aufgeteilt* und trägt seine Erklärung mit. Eine fehlende Größe wird nie zu 0 gerundet
(ADR-002/**P4**).

### K3 in einer Stelle: die Vorrangkette

Die Frage *„welche Menge ist der Stromverbrauch dieses Geräts?"* wird an **einer** Stelle
beantwortet (`core/field_definitions/wp_strom.py::wp_strom_stufe`; die Auflösung samt Rest liefert
`::wp_strom_aufteilung`):

1. **Ein Gesamtzähler ist die Menge** (K1). Die feinen Achsen (Heizen, Warmwasser) und die
   Betriebsart-Zähler sind die **Aufteilung darunter**. Was er mehr misst als sie —
   **Rest = Gesamt − Σ Achsen − Σ funktionsfremde Teilmengen ≥ 0** —, heißt *nicht aufgeteilt*
   (K5) und wird als solcher geführt.
2. **Es sei denn, er misst weniger als die Aufteilung**: liegt er mehr als die Toleranz darunter,
   tragen die **Achsen**, und der Daten-Checker meldet den Widerspruch. Zwilling der
   Wärme-Invariante im nächsten Abschnitt — nur *diese* Richtung ist ein Fehler.
3. **Kein Gesamtzähler** ⇒ die Achsen tragen, vollständig oder nicht: sie sind die einzige
   Messung, die es gibt. Sie zu verwerfen hieße, den Block verschwinden zu lassen.
4. **Auch keine feinen Achsen, aber gemessene Betriebsart-Zähler** ⇒ **sie** tragen: die Menge des
   Geräts ist die Σ der gemessenen Betriebsart-Ströme, der Modus-Rest ist 0, die Herkunft heißt
   *gemessen*. Derselbe Satz wie in Regel 3, eine Familie weiter.

> ⛔ **Regel 4 fehlte bis zum 15.09.2026, und Regel 3 galt trotzdem schon** (N-486). Gemessen:
> `get_wp_strom_kwh({'betriebsart_strom_heizen_kwh': 700}, {'wp_art': 'luft_luft'})` = **0,0**. Wer
> an seiner Split-Klimaanlage nur Betriebsart-Zähler zuordnete, bekam **gar keinen** Strom — keine
> Kosten, kein CO₂, keine Kennzahl —, während die Datenquellen-Fläche daneben „ausgewertet in …"
> behauptete. Die Begründung gilt **der Kategorie**, nicht dem Beispiel: *ein Zähler, der misst, ist
> die einzige Messung, die es gibt.*
>
> ⚠ **Die Reihenfolge ist keine Geschmacksfrage.** Betriebsart-Zähler sind **Teilmengen**; neben
> einer Summanden-Achse dürfen sie die Menge nicht tragen, sonst stünde eine Teilmenge an der Stelle
> eines Summanden. Sie kommen erst, wenn **weder** Gesamtzähler **noch** feine Achse da sind — dann
> teilen sie nichts mehr auf, sondern *sind* die Menge.
>
> ⚠ **E7 bleibt unberührt:** Die Summe ist eine **Menge**, kein Funktions-Nenner. Eine
> Funktions-Arbeitszahl nimmt weiterhin nur den gemessenen Strom *dieser* Funktion — und den gibt es
> in dieser Stufe per Definition nicht.
>
> ⭐ **Und die Additionsseite des Tages folgt seit dem 15.09.2026 der des Monats** (W-16 am Tag): Ein
> **gemessener** funktionsfremder Betriebsart-Zähler (Kühlen · Lüften · Entfeuchten) steht *neben*
> den beiden Achsen, nicht darin — die Monatszeile rechnet das seit W-16, die Tagesbilanz ließ ihn
> weg. Gemessen an der Prüfstand-Anlage r28 am 15.07.2026: **0,921 statt 5,398 kWh**; 4,5 kWh
> gemessener Kühlstrom fielen aus Tagesbilanz, Kosten und CO₂. ⛔ *Heizen* gehört nicht dazu — es
> steht **in** `strom_heizen_kwh`, und beide zu nehmen wäre die Doppelzählung von W-16b.

**Die Toleranz steht an einer Stelle** (`wp_strom_toleranz_kwh`) und gilt für die Rechnung **und**
den Checker: 1 % der Summe, mindestens 0,5 kWh im Monat bzw. 0,05 kWh im Tag. Zwei Schwellen für
dieselbe Frage wären die Drift-Klasse, an der F-56 entstanden ist.

> ⛔ **Bis zum 14.09.2026 stand hier eine erste Stufe davor:** *„Die feine Aufteilung ist
> vollständig ⇒ fein. Sie ist die Gesamtmenge; ein zusätzlicher Gesamtzähler wird verworfen, sonst
> zählte derselbe Strom zweimal."* Der Satz stimmte für die **Doppelzählung** und war für die
> **Menge** falsch. Misst der Gesamtzähler mehr als die beiden Achsen — Standby, Steuerung,
> Umwälzpumpen; bei dietmar1968 **145 von 2193 kWh im Jahr**, 6,6 % —, verlor eedc diese
> Kilowattstunden aus Strom, Kosten, CO₂ und dem Arbeitszahl-Nenner. Das verletzt **K1** und
> **K5**. *Doppelzählung entsteht beim **Addieren** von Gesamt und Achsen, nicht beim
> **Ersetzen*** — die alte Regel verhinderte das Falsche und verwarf dabei eine Messung.
>
> ⭐ **Der Arbeitszahl-Nenner zieht mit** (E7/Option A): Er ist *Menge − Kühlstrom*; der Rest
> bleibt darin. Das ist die ehrliche Zahl — Standby gehört zur Wärmepumpe, und die Systemzahl, die
> der Melder selbst führt, enthält ihn. **Funktions**-Arbeitszahlen bleiben unberührt: ihr Nenner
> ist der gemessene Strom *dieser* Funktion.
>
> ⭐ **#183 bleibt ausgeschlossen, nur mit anderer Begründung.** Nicht die Wahl der **Menge**
> trennt die drei Arbeitszahlen, sondern die Wahl des **Nenners** — und `arbeitszahl_je_funktion`
> nimmt dafür ausschließlich den gemessenen Strom der jeweiligen Funktion. Der Gesamtzähler kann
> deshalb neben zwei Funktionszahlen stehen, ohne dass eine dritte aus einer anderen Quelle
> entsteht.

⚠ **Tag und Monat beantworten „belegt?" verschieden — und sie müssen das.** Der Tag fragt *„ist
ein Zähler zugeordnet?"*, der Monat *„steht ein Wert in der Zeile?"* — eine Monatszeile darf ohne
jeden Zähler von Hand gepflegt sein. Was beide teilen, ist die **Vorrangkette**; sie steht deshalb
an einer Stelle und nicht zweimal. **Folge für Regel 2:** Auf der Zuordnungs-Ebene gibt es keine
Werte, also auch keinen Widerspruch zu prüfen — er wird an der Monatszeile gemeldet, wo die Zahlen
stehen.

⭐ **Und der Tag fragt seit dem 15.09.2026 ein zweites Mal — an den Werten** (N-482). Ein
zugeordneter Gesamtzähler, der an **diesem** Tag keinen Stand liefert, ließ die gemessenen feinen
Achsen daneben nicht tragen: die Beitragsschicht entscheidet 1-aus-n an der *Zuordnung*, und der
vorhandene Either-Or-Mechanismus nähme bei zwei Achsen genau eine. Fehlt der aggregierte Tageswert
eines Geräts, löst der Tag seinen Strom deshalb **nach** dem Lesen der Randstände mit derselben
Vorrangkette auf (`core/berechnungen/wp_tages_praezedenz.py`, Bauform `pv_tages_praezedenz`). ⛔ Die
**Tageszeile gewinnt**, wo sie eine Zahl trägt — sie ist die Zahl, mit der Bilanz, Kosten und CO₂
dieses Tages gerechnet haben; eine zweite daneben wäre ein S1-Bruch.

⛔ **Das Kennzeichen `getrennte_strommessung` entscheidet nur, ob die feinen Achsen *Summanden*
sind** — nicht, ob ein Zähler zählt. Kennzeichen aus, kein Gesamtzähler, aber ein feiner Zähler
zugeordnet ⇒ Regel 3, er trägt. K3 gilt weiter in beide Richtungen.

⚠ **Zwei Reste, zwei Aufteilungen, und sie werden nie addiert.** Dieselbe Menge wird auf zwei
Weisen aufgeteilt, und jede lässt ihren eigenen Rest übrig:

| Aufteilung | Rest | Herkunft des Rests |
| --- | --- | --- |
| **Summanden** — Strom Heizen + Strom Warmwasser | `WpFakten.strom_nicht_aufgeteilt_kwh` | der Gesamtzähler misst mehr als die Achsen |
| **Teilmengen** — Betriebsart bzw. Modus-Split | `WpFakten.modus_nicht_aufgeteilt_kwh` | Stunden ohne Modus-Signal, nicht gemessene Betriebsarten |

Beide sind ≥ 0, beide sind K5, und beide dürfen nebeneinander stehen — sie zu summieren wäre
Doppelzählung. ⚠ *„Nicht aufgeteilt" setzt eine Aufteilung voraus:* Wer nur einen Gesamtzähler
pflegt, hat keinen Rest, sondern nur eine Menge; dass die Achsen fehlen, sagt der Daten-Checker.

### Die Wärmeseite: Gesamtwert vor Summanden — je Gerät

Auf der Wärmeseite gibt es dieselben zwei Familien — *Wärme gesamt* (`waerme_kwh`, seit dem
14.09.2026) als Bilanzgröße und *Heizwärme* + *Warmwasser-Wärme* als Summanden. Die Frage
*„welche Menge ist die Wärme dieses Geräts?"* wird mit **einer** Regel an **einer** Stelle
beantwortet (`core/berechnungen/waermepumpe_kennzahl.py::waerme_gesamt_kwh`): **Steht ein
Gesamtwert, gilt er; sonst die Summe dessen, was gemessen ist.** Das ist K1 auf der Wärmeseite —
ein Gesamtzähler neben einer Aufteilung addiert nicht, er ersetzt.

⭐ **Beide Seiten sagen seit dem 14.09.2026 denselben Satz.** ⛔ Bis dahin stand hier der Zusatz
*„aber keine drei Stufen: Es gibt kein Kennzeichen, das die Summanden zur ‚vollständigen'
Aufteilung erklärt"* — die Wärmeseite war die Ausnahme, die Stromseite die Regel. Es war umgekehrt:
Das Kennzeichen `getrennte_strommessung` erklärt die zwei Zähler zu **Summanden**, nicht dazu, dass
sie **alles** messen. Der Unterschied, der bleibt, ist nur der **Rest**: Auf der Stromseite wird er
geführt (*nicht aufgeteilt*, K5); auf der Wärmeseite gibt es ihn als eigene Größe nicht, weil die
Wärme keine dritte Achse hat, auf die er fallen könnte.

* **Je Gerät, dann summiert** ([Kapitel 7](#7-mehrere-geräte)). Zwei Geräte mit verschiedener
  Zählerlage — eines mit Gesamtzähler, eines mit Aufteilung — ergeben die **Summe ihrer je
  aufgelösten Wärme**, nicht die Auflösung ihrer Summe. Monats-Fakten, Hub, Cockpit → Monat,
  Aussichten/ROI (Jahresformel), HA-Export, Checker, Community-Payload und Tag lesen alle so. Der
  erste Bau erreichte drei Geldstellen nicht (die Jahresformel schrieb die Summe im Klartext, nicht
  über den Helfer — in Lage B stand dort 0) und der Tag löste zunächst auf der Anlagensumme auf (im
  Mischfall 30 statt 55). *Wer eine Regel an jede Lesestelle bringt, sucht nach dem Feldnamen, nicht
  nach dem Helfer.*
* **Die Kennzahl je Funktion behält ihre Zahl, wo sie eine hat.** Wer Gesamtzähler *und*
  Aufteilung pflegt, hat für Heizen und Warmwasser gemessene Zähler und Nenner (R2) — beide Zahlen
  bleiben. Nur eine Funktion **ohne** eigenen Wärmewert sagt *„Wärme nicht je Funktion gemessen"*
  statt *„kein Wärmemengenzähler zugeordnet"* — der Zähler ist ja zugeordnet. Eine pauschale
  Sperre „sobald ein Gesamtwert dasteht" ist durchgefallen: Sie träfe auch das Gerät, dessen
  Wärmemengenzähler nur am Heizkreis sitzt und dessen Heiz-Arbeitszahl richtig ist.
* **Nur eine Richtung ist ein Widerspruch.** Gesamtwärme *kleiner* als Heizwärme + Warmwasser-Wärme
  ⇒ der Daten-Checker warnt (meist ist unter „Wärme gesamt" die Heizwärme gelandet). Gesamt
  *größer* als die Summe ist die normale Lage, wenn nur eine Achse eigens gemessen wird.
* **Keine Migration.** Bestandszeilen, die einen Gesamtzähler unter „Heizwärme" führen, bleiben,
  wie sie sind — eedc kann die drei Lagen (nur Heizung · beides mit einem Zähler · beides ohne
  Zähler) in den Daten nicht unterscheiden (ADR-002/P3b: kein stiller Overwrite). Der Anwender
  trägt um; der Vorschlag aus dem Gesamtstrom (F2) steht seitdem an *Wärme gesamt*, nicht mehr an
  *Heizwärme*.

### Was jeder vorausgesetzte Wert leisten muss

| Wert | Herkunft muss sein | Bedeutung | Invariante — wird sie verletzt, gilt K5 |
| --- | --- | --- | --- |
| **Gesamt-Stromzähler** | ein Zähler, der **das ganze Gerät** erfasst — Außengerät **und** Innengeräte | Gesamt (K1) | **Σ Teilmengen ≤ Gesamt.** Wird sie verletzt, ist entweder der Zähler unvollständig oder die Teilmengen sind keine Messungen — eedc kann die beiden nicht unterscheiden ⇒ **beide** nennen, keine Aufteilung ausweisen |
| **Betriebsmodus-Signal** | **genau eine** Quelle je Gerät | Zustand jetzt, stündlich mitgeschrieben | Er muss eine **Richtung** nennen. Nennt der *eingestellte* Modus keine (`aus`, Automatik, kein Wert), ist die Stunde `unbestimmt` und fällt in *nicht aufgeteilt*. Der **Ist-Betrieb** (`hvac_action`) ist eine zweite Größe und **verfeinert nur**: `idle` ist kein Modus ohne Richtung, sondern eine Aussage über den Augenblick — der eingestellte Modus bleibt stehen. **Verschiedene** Quellen an einem Gerät ⇒ kein Anlagen-Modus; die Zusammenführung gehört dem Anlagenbesitzer (Template-Sensor), nicht eedc |
| **Betriebsart-Zähler** | **Messung** dieser einen Betriebsart; herstellerseitig anteilig zugerechnete Werte sind keine | Teilmenge, nie Summand | Gerätefeld **schlägt** Σ Innengeräte, sie werden **nie addiert**. Ein einziger zugeordneter Zähler schaltet das Gerät ganz auf den gemessenen Weg (K2) |
| **Getrennte Zähler Heizen/Warmwasser** | zwei Zähler, die zusammen den Gesamtverbrauch ergeben | Summanden | Sie ersetzen den Gesamtzähler **nicht** (K3) |
| **Wärmemengenzähler** | thermische Energie in kWh, **an derselben Grenze** wie der Stromzähler | Zähler des Quotienten | Q und E müssen dasselbe Gerät im selben Zeitraum meinen (R2). Riemann-Integration über eine Momentanleistung ist zulässig, überschätzt aber taktende Geräte — eine überschätzte Eingangsgröße heilt eedc nicht |
| **Kältemengenzähler** | wie oben, für die Kälteseite | Zähler der Kühl-Kennzahl | ohne ihn **keine Arbeitszahl Kühlen** — und ein **Grund** statt einer Zahl |

⛔ **Eigene Versorgung je Innengerät wird nicht unterstützt.** eedc setzt voraus, dass der
Anlagenzähler den gesamten Verbrauch erfasst, Innengeräte eingeschlossen — alles je Innengerät ist
**Aufschlüsselung, niemals Summand**. Beide Verdrahtungen existieren real; im Modell steht die
Grenze trotzdem, weil die Invariante der ersten Zeile sonst falsch diagnostiziert.

> ⛔ **Und der Satz, der in jede Anwenderfläche gehört:** *Falsche Eingangswerte erzeugen falsche
> Ergebnisse.* eedc prüft, was es prüfen kann, und **sagt**, welche Voraussetzung fehlt — es
> repariert keine Eingangsgröße und rechnet keine hinzu (ADR-002/P4, K5).

---

## 4. Die Abgrenzungsregel R2 — wann eine Kennzahl erscheinen darf

R2 ist §1 als Prüfvorschrift. Sie ersetzt eine Fallsammlung durch eine Regel, und der Prüfstein
dafür, dass die Abstraktionshöhe stimmt, ist der **bivalente** Fall: ein zweiter Wärmeerzeuger
speist denselben Heizkreis, sein Aufwand liegt nicht auf dem Wärmepumpen-Zähler ⇒ **Q ist zu
groß**. Er hat keinen Melder und stand in keiner Aufzählung — R2 fängt ihn trotzdem, weil er
dieselbe Regel bricht wie der Heizstab, nur mit umgekehrtem Vorzeichen.

| Lage | Abweichung |
| --- | --- |
| Fremder Verbraucher (typisch ein Heizstab) auf dem Wärmepumpen-Zähler, seine Wärme fehlt | **E zu groß** ⇒ Zahl zu niedrig |
| Bivalent: zweiter Erzeuger am Wärmezähler, sein Aufwand fehlt | **Q zu groß** ⇒ Zahl zu hoch |
| Zwei Geräte auf einem Zähler, nur eines meldet Wärme | E zu groß |
| Wärme von Gerät A, Strom von Gerät B — gleiche Anzahl, verschiedene Geräte | **beide Seiten tragen Geräte, aber nicht dieselben** |
| Ein Monat trägt Wärme ohne Strom, ein anderer trägt Strom | **Zeitraum** — sichtbar erst in der Jahressumme |
| Q aus dem Monatsabschluss gegen E aus laufenden Sensoren | Zeitraum |
| Q abgeleitet statt gemessen | Q ist keine Messung |

### 4.1 R2 gilt je Funktion, nicht je Block

⭐ **Die Trennlinie ist die Abgrenzung, nicht die Bauart** (Entscheid Gernot, 10.09.2026). Ein
Block darf als Ganzes vermischt sein und trotzdem einzelne Funktionen sauber abgrenzen — dann
**erscheint deren Kennzahl**. Bei einer Wärmepumpe neben einer Split-Klimaanlage standen vorher
drei Striche, während der Komponenten-Hub für dieselben Geräte 3,0 und 2,5 auswies.

**Die Prüfvorschrift je Funktion:** *Zähler und Nenner müssen von **denselben** Geräten stammen.*

| Lage | Reichweite | warum |
| --- | --- | --- |
| Anwender-Angabe (`fremdstrom` · `fremdwaerme`) | **alle Funktionen** | ⚠ nicht, weil ein Heizstab immer beide träfe — ein Legionellen-Heizstab trifft nur das Warmwasser. Sondern weil die **Angabe keine Funktion trägt**: wir wissen nicht, welche betroffen ist, und dürfen keine freigeben |
| Zeitraum-Versatz | **alle Funktionen** | die Herkunft ist je Größe bekannt, die Funktion nicht |
| Gemischte Bauarten · Geräte ohne Wärme | **nur die vermischten Funktionen** | die Geräte-Deckung entscheidet, nicht die Bauart |

⛔ **Gezählt wird beidseitig, und das ist nicht verhandelbar.** Eine einseitige Fassung („jedes
Gerät mit Strom liefert auch Wärme") fängt nur den Nenner. Der Zähler kippt genauso — und in die
**teurere** Richtung, weil dort eine zu hohe Kennzahl erscheint statt gar keiner.

> ⭐ **Die Regel hat einen Fehler mitgelöst, den niemand gemeldet hatte.** Eine
> **Brauchwasser-Wärmepumpe** neben einer Wärmepumpe mit getrennter Strommessung fiel durch jede
> bisherige Sperre: Beide sind Luft-Wasser-Geräte, beide melden Wärme. Die Warmwasser-Wärme kam von
> beiden, der getrennt gemessene Strom von einem ⇒ **4,75 ohne jeden Hinweis**. Das ist keine
> Übersperre, sondern eine **fehlende Lage** — sie heißt jetzt *„Nutzenergie und Strom dieser
> Funktion stammen von verschiedenen Geräten"*.

⚠ **Über mehrere Perioden wird das Urteil gefaltet, nicht die Gerätezahl.** Ein Monat, der Wärme
ohne den Strom derselben Funktion trägt, schiebt seine Wärme in die Jahressumme und seinen Strom
nicht — die Zahl der beteiligten Geräte ist dabei in jedem Monat gleich. Monate ohne Aussage
zählen nicht mit; ein Sommermonat ohne Heizbetrieb ist kein Abgrenzungsfehler.

### 4.2 Die Vorrangkette — welcher Grund gewinnt

⭐ **Die folgenden Tabellen sind aus dem Layer erzeugt, nicht abgeschrieben** (Mess-Datum
2026-09-13): jede Zeile ist die Antwort eines Aufrufs von
`core/berechnungen/waermepumpe_kennzahl.py`. Wer die Reihenfolge ändert, ändert diese Tabellen mit.

**Block-Ebene** (`abgrenzungs_grund`) — die anlagenweite Zahl. Ermittelt durch Paarvergleich:
jeder Grund gegen jeden anderen.

| Rang | Lage | Grund im Wortlaut |
| --- | --- | --- |
| 1 | Anwender-Angabe `fremdstrom` | „Ein weiterer Verbraucher auf dem WP-Zähler (z. B. Heizstab)" |
| 1 | Anwender-Angabe `fremdwaerme` | „zweiter Erzeuger am Wärmezähler" |
| 2 | gemischte Bauarten | „Wärmepumpe und Klimaanlage in einer Zahl" |
| 3 | Geräte ohne Wärme | „nicht alle Geräte melden Wärme" |
| 4 | Zeitraum versetzt | „Zähler messen verschiedene Zeiträume" |
| 5 | Geräte verschieden | „Wärme und Strom stammen von verschiedenen Geräten" |
| 6 | Perioden versetzt | „Wärme und Strom stammen aus verschiedenen Monaten" |

⭐ **Die Reihenfolge ist eine Entscheidung, keine Willkür** (Entscheid Gernot, 26.08.2026): **Die
Anwender-Angabe schlägt die Selbsterkennung.** Wer eingetragen hat, dass ein Fremdverbraucher auf
seinem Zähler liegt, bekommt genau diesen Satz zu lesen — nicht den allgemeineren, der auf
dieselbe Anlage ebenfalls zutrifft. Aus demselben Grund steht *gemischte Bauarten* vor *Geräte
ohne Wärme*: Die Klimaanlage ist eines der Geräte ohne Wärmemeldung, aber sie kann bauartbedingt
nie eine liefern; der allgemeinere Satz riete zu einer Zuordnung, die es beim Anwender nicht geben
kann. **Der konkretere Grund ist die bessere Auskunft.**

⚠ **Die beiden letzten Glieder hängen bewusst ans Ende — auch hinter *Zeitraum versetzt*.** Im
Monat können *Geräte verschieden* und *Zeitraum versetzt* gemeinsam wahr sein; stünde das neue
Glied davor, wechselte dort ein gezeigter Grund samt Hub-Link, ohne dass sich an der Anlage etwas
geändert hätte.

**Funktions-Ebene** (`abgrenzung_je_funktion`) — je Funktion ihr eigener Grund:

| Lage | Heizen | Warmwasser | Kühlen |
| --- | --- | --- | --- |
| Anwender-Angabe `fremdstrom` | Fremdverbraucher-Satz | Fremdverbraucher-Satz | Fremdverbraucher-Satz |
| Anwender-Angabe `fremdwaerme` | Zweiterzeuger-Satz | Zweiterzeuger-Satz | Zweiterzeuger-Satz |
| Zeitraum versetzt | Zeitraum-Satz | Zeitraum-Satz | Zeitraum-Satz |
| Bauarten gemischt, nur Heizen vermischt | „Wärmepumpe und Klimaanlage in einer Zahl" | — (Zahl erscheint) | — (Zahl erscheint) |
| Geräte ohne Wärme, Heizen + Kühlen vermischt | „nicht alle Geräte melden Wärme" | — (Zahl erscheint) | „Nutzenergie und Strom dieser Funktion stammen von verschiedenen Geräten" |
| Deckung verletzt, kein Block-Grund | „…von verschiedenen Geräten" | — | „…von verschiedenen Geräten" |
| Deckung über **Monate** verletzt | „…aus verschiedenen Monaten" | — | — |
| Hub-Aufruf (Deckung unbekannt) | Block-Grund | Block-Grund | Block-Grund |

⛔ **Der Block-Satz „nicht alle Geräte melden Wärme" darf an der Kühl-Zeile nicht stehen.** Der
Zähler der Kühlzahl ist eine **Kälte**menge; ein Satz über fehlende *Wärme*-Melder wäre darunter
eine Falschaussage. Für `kuehlen` tritt deshalb der Funktions-Satz an seine Stelle — er sagt
dasselbe in der Sprache dieser Funktion. **Nur dieser eine Grund wird getauscht**; Anwender-Angabe,
gemischte Bauarten und Zeitraum-Versatz beschreiben den Block und nennen keine Nutzenergie-Art.

### 4.3 Die Datenlage geht der Abgrenzung vor

Bevor R2 überhaupt gefragt wird, prüft `arbeitszahl` die Datenlage. Die Kette in der Reihenfolge,
in der sie greift (erzeugt aus dem Layer):

| # | Lage | Ergebnis |
| --- | --- | --- |
| 1 | kein Strom erfasst (der Strom **fehlt** — eine gemessene 0 ist erfasst und trifft diese Stufe nicht) | „kein Stromverbrauch erfasst" |
| 2 | der ganze Strom ist funktionsfremd | „nur Kühlbetrieb in diesem Zeitraum" |
| 3 | Wärme **gemessen** 0, Grund bekannt | „kein Heizbetrieb in diesem Zeitraum" bzw. „keine Warmwasserbereitung in diesem Zeitraum" |
| 3′ | Funktions-Strom **gemessen** 0, die Wärme nur **gesamt** gemessen (ein Zähler über Heizung und Warmwasser) | wie 3 — vor „Wärme nicht je Funktion gemessen" (Fachentscheid Master zu E4f, H-3) |
| 4 | Wärme fehlt, besserer Grund gereicht | dieser Grund (z. B. Zählerrücksprung) |
| 5 | Wärme fehlt, kein Grund bekannt | „kein Wärmemengenzähler zugeordnet" |
| 5′ | Strom **gemessen** 0, Wärme **nicht erfasst** (Gegenfall, §8a-Nachtrag) | Stufe 4/5: der gereichte Wärme-Grund, sonst „kein Wärmemengenzähler zugeordnet" (Klasse Ausstattung) — der Strom ist erfasst, es fehlt die Wärme |
| 6 | Wärme ist abgeleitet | „Wärme ist gerechnet, nicht gemessen" |
| 7 | Abgrenzung verletzt | der Grund aus 4.2 |
| 8 | sonst | **die Zahl**, dazu Zähler und Nenner (A6) und unter 2,0 der Heizstab-Hinweis |

⭐ **Eine gemessene 0 ist erfasst; bei Strom 0 und Wärme 0 gilt Stufe 3** (HA-Bauform E4d, Bauplan §8a, Rest N-585):
Stufe 1 trifft nur den **nicht erfassten** Strom (kein Wert) — nie eine gemessene 0. Sind Strom und Wärme gemessen 0,
lief das Gerät nicht — die Kette nennt den
vorhandenen Zeitraum-Grund („kein Heizbetrieb in diesem Zeitraum", an einer Einheit nur mit Warmwasser-Achse „keine
Warmwasserbereitung in diesem Zeitraum"; `waermepumpe_kennzahl.kein_betrieb_grund_der_achsen`), die Mengen stehen mit
0, die Ersparnis ist 0 € und die Ergebnis-Leiter führt die Zeile nicht als „fehlt". Kein neuer Grund-Text. ⚠ Strom 0
bei Wärme > 0 regelt dieser Satz nicht (es bleibt bei Stufe 1, ohne Ersparnis-Zeile; Entscheid H-2, Kandidat
Daten-Checker „Wärme ohne Strom"), Strom > 0 bei Wärme 0 (Standby) ist Stufe 5. **Gegenfall** (Zeile 5′, Nachtrag §8a
aus der Nachmessung E4d): Strom gemessen 0 und Wärme **nicht erfasst** ⇒ Stufe 5 „kein Wärmemengenzähler zugeordnet"
(bzw. der gereichte Wärme-Grund) — wahr ist, dass die Wärmemessung fehlt, nicht der Strom. Am Layer
`systemarbeitszahl` (Wärme `None`) und `arbeitszahl` (mit dem Riegel `kein_betrieb_grund`: Wärme `None` oder ein
Wärme-Grund), je Gerät über `GeraetMengen.strom_null_waerme_fehlt`, in der Übersicht über die Marken
`strom_gemessen`/`waerme_gemessen` (eine 0 ohne Marke geht als `None` in den Layer).

⭐ **Zeile 3′ — der Zeitraum ohne Betrieb geht dem Ausstattungs-Grund vor** (Fachentscheid Master Wärme/Klima zu HA-Bauform
E4f, H-3, 07.10.2026). Ist der Strom einer Funktion im Zeitraum bekannt und 0 — gemessen bzw. getrennt gemessen —, gilt
„kein Heizbetrieb in diesem Zeitraum" bzw. „keine Warmwasserbereitung in diesem Zeitraum" (Klasse Zeitraum, stilles
„—"), auch wenn die Wärme nur als Gesamtwert eines gemeinsamen Zählers vorliegt. **Begründung an der Kategorie:** ein
Zeitraum ohne Betrieb hat keinen Handgriff, den der Anwender tun könnte; der Ausstattungs-Satz „Wärme nicht je Funktion
gemessen" (Handgriff „zweiten Wärmemengenzähler setzen") wäre dort falsch — die Datenlage geht der Abgrenzung vor
(Stufe 2/3 vor 5/6). Fließt Strom der Funktion, bleibt „Wärme nicht je Funktion gemessen" (N-391); fehlt die Wärme ganz,
bleibt Zeile 5′. Als „Wärme gemessen" zählt in Monat und Jahr dafür auch die gemessene Gesamtwärme
(`aktueller_monat/komponenten.py`, `waermepumpe_jahreskennzahlen.py`); der Komponenten-Hub reicht keinen Zeitraum-Grund
herein (N-479 gilt dort nicht) und bleibt bei Stufe 1. Anlass: der Golden Master v4.1.2 ↔ E4f an der Prüfstand-Anlage
(Sommer, Heizstrom 0, Gesamt-Wärmezähler) — seit E4d stand dort der Ausstattungs-Satz. ⚑ Ein aus dem Betriebsart-Etikett
abgeleiteter Funktions-Strom geht in die Funktions-Arbeitszahl nicht ein (SOLL §9-E7, ohne getrennte Messung gilt
„Strom nicht getrennt je Funktion gemessen") und trägt deshalb auch Zeile 3′ nicht — offen beim Master (Bericht E4f).

⚠ **Warum bei 3 kein Quotient statt eines Grundes.** 0 kWh Wärme ÷ 1 kWh Strom ergibt 0 — wahr und
trotzdem irreführend: Der Strom ist Standby und Umwälzung, kein misslungenes Heizen. Eine 0 an der
Stelle einer Arbeitszahl liest sich als Bewertung des Geräts. ⚠ Und `q == 0` ist **nicht**
`q <= 0`: eine negative Wärme ist ein Zählerrücksprung und kein ruhiges Gerät.

Für die Kühl-Kennzahl gilt dieselbe Bauform mit eigenen Sätzen: *kein Kühlbetrieb in diesem
Zeitraum* (kein Kühlstrom) · *keine Kälte abgegeben in diesem Zeitraum* (Kälte gemessen 0) · *kein
Kältemengenzähler zugeordnet* (Kälte fehlt).

---

## 5. Die Kennzahlen — was aus E und Q folgt

### 5.1 Je Funktion eine eigene Zahl

| Funktion | Kennzahl | Formel | Bedingung |
| --- | --- | --- | --- |
| **Heizen** | Arbeitszahl Heizen | Q_heiz / E_heiz | beide Größen für **dieselbe** Funktion |
| **Warmwasser** | Arbeitszahl Warmwasser | Q_ww / E_ww | typisch **niedriger** als Heizen (höhere Zieltemperatur) — das ist kein Mangel |
| **Kühlen** | Arbeitszahl Kühlen | Q_kälte / E_kühl | **Kälte**menge, nicht Wärmemenge |
| **gesamt** | Arbeitszahl gesamt (JAZ) | Σ Q / Σ E | nur bei gleicher Abgrenzung aller Anteile |

⛔ **Die Kühlzahl heißt nicht „SEER".** SEER ist eine genormte, saisonal gewichtete
Prüfstandsgröße. Was eedc bilden kann, ist der schlichte Quotient zweier Zähler über einen
Zeitraum; ihn „SEER" zu nennen behauptete eine Vergleichbarkeit mit Datenblatt-Werten, die er
nicht hat.

⚠ **Der Name der Kennzahl nennt ihren Zeitraum.** „JAZ" heißt Jahresarbeitszahl; über einen Monat
gerechnet ist es die Monats-Arbeitszahl, über einen Tag eine Tageszahl mit sehr begrenzter
Aussage. Dieselbe Zahl unter demselben Namen für drei Zeiträume auszuweisen lädt zum Vergleichen
von Dingen ein, die nicht vergleichbar sind.

⚠ **Eine Kennzahl entsteht nur im Layer** (ADR-002/**P12**): Ein Quotient aus einer Wärme- und
einer Stromgröße wird ausschließlich in `waermepumpe_kennzahl.py::arbeitszahl` gebildet; jede Sicht
liest das Ergebnis **samt Begründung**. Eine rohe Division im Client kann von der Anwender-Angabe,
vom funktionsfremden Strom und von abgeleiteter Wärme nichts wissen.

#### 5.1a · Die Achsen des Geräts entscheiden, welche Funktions-Zahl es gibt (E1 ∘ R1, 15.09.2026)

**Eine Funktions-Arbeitszahl gibt es nur für eine Achse, die das Gerät hat.** Welche das sind, sagt
die **Registry** (`field_definitions/bedingungen.py::wp_waerme_achsen`) und nicht die Bauart-Kette: Eine
**Brauchwasser**-Wärmepumpe trägt nur *Warmwasser*, eine **Split-Klimaanlage** nur *Heizen*
(N-304, kein Warmwasserkreis), jedes andere Gerät beide. Für eine Achse, die nicht gilt, gibt es
**weder Zahl noch Grund** — kein Strich mit Text, gar nichts. Das ist WK-15c eine Fläche weiter:
*eine Achse, die am Gerät nicht gilt, trägt in keiner Rechnung und keinem Hinweis eine Zahl.*

> **Hat eine Einheit genau EINE Wärme-Achse, ist die Funktions-Arbeitszahl dieser Achse die
> Gesamt-Arbeitszahl.** Strom und Wärme sind per Bauart dieser Funktion zugeordnet; ein getrennter
> Zähler könnte nichts anderes messen. **Der Grund steht an der Kategorie, nicht am Beispiel:** Ein
> Gerät ohne zweite Funktion **hat** keine Aufteilung, die fehlen könnte.

⭐ **Gemessen an der nachgestellten Prüfstand-Anlage (r28, 15.09.2026), und beides traf Anwender**
(N-499):

| Gerät | vorher | nachher |
| --- | --- | --- |
| Brauchwasser-WP *Stiebel WWK 300* | Gesamt **3,31**, daneben zweimal *„Strom nicht getrennt je Funktion gemessen"* | Arbeitszahl **Warmwasser 3,31**; die Heiz-Achse ist leer |
| Split-Klimaanlage *Bosch Multisplit* | *Heizen:* „Strom nicht getrennt…", *Warmwasser:* derselbe Satz | *Heizen:* **„kein Wärmemengenzähler zugeordnet"**; Warmwasser ist leer |

⭐ **Damit fällt die Grund-Rangfolge heraus, ohne zweite Regel:** Fehlt die **Wärme** einer Achse,
ist das der Grund — *vor* „Strom nicht getrennt gemessen", weil getrennte Stromzähler ohne
Wärmemengenzähler keine einzige Kennzahl brächten. An einem Ein-Achsen-Gerät sagt die Gesamtzahl
genau das; ein zweiter Wortlaut daneben wäre die W-3-Klasse.

⚠ **Die Regel ersetzt einen Grund, nie eine Zahl.** Wo die feinen Zähler eine Funktions-Zahl
hergeben, bleibt sie stehen: Sie ist eine Messung *dieser* Funktion, und der Gesamtzähler wäre
dafür der gröbere Nenner (er enthält Standby und Steuerung, K1). ⛔ Und eine **Schranke** (E1b)
geht nie mit: Die Funktions-Zeilen haben keine Bauform für ein „≥", und eine Schranke ohne ihr
Zeichen behauptete mehr, als sie weiß (**P4**).

**Anlagenweit gilt derselbe Satz, über die Geräte, die im Zeitraum beitragen**
(`waerme_klima_block.py::achsen_der_anlage`, *Beitrag statt Bestand* wie bei der Schranke). Trägt an
einem Tag allein die Klimaanlage Strom bei, gibt es anlagenweit keine Warmwasser-Achse — und damit
auch keine Kasten-Zeile *„Getrennte Strommessung einschalten und beide Zähler zuordnen"*, die an
diesem Gerät ins Leere führte (gemessen Demo-Anlage r28, 15.06.2026).

⭐ **Und die Regel gilt anlagenweit auch für die MENGEN** (15.09.2026, N-506): Ein Gerät mit genau
einer Achse steht mit `waerme_kwh` und `strom_kwh` auf **beiden** Seiten dieser Achse
(`waerme_klima_block.py::funktions_eingaenge_der_anlage`). Ohne das trüge die Brauchwasser-WP ihre
Wärme in den Zähler und ihren Strom in keinen Nenner — die Zahl je Gerät (3,31) und die Auskunft
darüber widersprächen einander. Bedingung und Grenzen: [§7](#7-mehrere-geräte).

### 5.2 Woher der Nenner kommen darf

> **SOLL-§9-E7 (Entscheid Gernot, 12.09.2026):** Der Nenner einer Funktions-Arbeitszahl ist der
> getrennt **gemessene** Strom dieser Funktion. Der aus dem Betriebsmodus **abgeleitete** Strom ist
> eine **Verteilung** des Gesamtstroms und taugt als Nenner nur für **Kühlen** — weil dort keine
> andere Messung existiert und die Kältemenge ohnehin nur mit Zähler vorliegt.

Begründet an der **Kategorie**, nicht am Beispiel: Eine Verteilung erbt jede Unschärfe ihres
Schlüssels (Laufzeit je Modus, Standby-Anteil), eine Messung nicht; für Heizen und Warmwasser gibt
es den gemessenen Weg, für Kühlen keinen.

**Folge, ausdrücklich gewollt:** Ein Gerät mit Betriebsmodus-Sensor, aber ohne getrennte
Strommessung bekommt eine Kühl-, aber **keine** Heiz-Arbeitszahl. Das ist keine Lücke. Wer
Modus-Strom auch für Heizen als Nenner will, ändert **zuerst diesen Satz** — nicht den Code.

### 5.3 Abgezogen wird nur, was im Nenner steht

> **Ergänzung zu E7 (Entscheid Gernot, 12.09.2026, Option A):** Ein funktionsfremder Stromanteil
> (Kühlen · Lüften · Entfeuchten) wird vom Nenner der **Gesamt**-Arbeitszahl nur abgezogen, wenn er
> auch **darin steht**: im nicht-getrennten Zweig immer (der Gesamtzähler enthält ihn), im
> getrennten Zweig nur, wenn er **gemessen** ist.

Ein aus dem Betriebsmodus **abgeleiteter** Anteil kürzt einen gemessenen Nenner nicht — er ist eine
Verteilung dieses Topfs, keine Menge darin. Dieselbe Kategorie wie E7, nur auf der Abzugsseite.
**Gemessen:** dieselbe Anlage zeigte **4,24** mit Betriebsmodus-Sensor und **3,79** mit
Kühlzähler — rund 12 % zu gut. Die Funktions-Arbeitszahlen bleiben davon unberührt (E7: gemessener
Nenner, kein Abzug).

⚠ **Ob der Abzug greift, hängt an der Stufe, die der Strom dieser Zeile genommen hat** — nicht am
Kennzeichen. Fällt eine Zeile trotz gesetztem Kennzeichen auf den Gesamtzähler zurück (Stufe 2),
steckt der Kühlstrom darin und muss abgezogen werden; am Kennzeichen festgemacht zeigte dasselbe
Gerät mit denselben Zählern **3,0 statt 3,75**, allein weil ein Schalter gesetzt war, der in dieser
Lage nichts misst.

⚠ **Warum hier abgezogen und bei abgeleiteter Wärme gesperrt wird — das ist kein Widerspruch.** Bei
abgeleiteter Wärme enthält der **Zähler** einen Anteil, der aus dem Nenner gerechnet wurde; ihn
abzuziehen ergäbe gemessene Wärme durch Gesamtstrom, also **falsch statt unbekannt**. Beim
funktionsfremden Strom enthält der **Nenner** einen Anteil, der zu einer anderen Funktion gehört
und separat bekannt ist — ihn abzuziehen stellt die Abgrenzung erst her.

⭐ **Der Vergleichsserver bekommt den Abzug mit, nicht nur die Kühlmenge.** Er rechnet nichts nach;
zöge er die Menge selbst ab, hätte dieselbe Anlage in eedc und im Benchmark zwei Zahlen.

### 5.4 Lüften und Entfeuchten — erfassen ja, bewerten nein

**E4 (Entscheid Gernot, 26.08.2026).** Beide Betriebsarten erscheinen in der Aufteilung, wenn
Zähler dafür da sind. Eine Kennzahl bekommen sie nicht: Sie erzeugen keine Nutzenergie, die sich
messen ließe. Ihr Strom fällt deshalb auch **aus dem Nenner** der Arbeitszahl — sonst drückte er
eine Zahl, mit der er nichts zu tun hat. Wer sie nicht erfasst, sieht sie nicht; sie bleiben dann
im Rest *nicht aufgeteilt*.

### 5.5 Wirtschaftlichkeit und CO₂

| Funktion | Vergleich | Warum |
| --- | --- | --- |
| **Heizen** | gegen Gas/Öl/Fernwärme | die Wärmepumpe hat eine Heizung ersetzt |
| **Warmwasser** | gegen Gas/Öl **oder** gegen den Heizstab | je nachdem, was vorher da war |
| **Kühlen** | **kein Vergleich** | Kühlen ersetzt keine Heizung; ohne das Gerät gäbe es schlicht keine Kühlung |

**E-B (Entscheid Gernot, 18.08.2026): Kühlen ist Komfortverbrauch — Kosten ja, Ersparnis nein.**
Die Formeln stellten vorher die Stromkosten des *Kühlens* gegen die vermiedenen Gaskosten des
*Heizens*; an einer nachgestellten Anlage gemessen −45,04 € und −52 kg CO₂, nach der Korrektur
+2,48 € und +8,2 kg. Der Kühlstrom ist seither aus dem Vergleich, seine Kosten stehen eigens.

**Ein Vergleich setzt voraus, dass etwas ersetzt wurde.** Steht beim ersetzten Energieträger
„Nichts ersetzt (Neubau)", wird weder Ersparnis noch CO₂-Ersparnis konstruiert, und ohne
gepflegten Wärmebedarf gibt es keinen Default, sondern „—" samt Begründung. **Das gilt für jede
Bauart** — eine Luft-Luft-Wärmepumpe kann sehr wohl eine Gasheizung ersetzen.

**Ein Vorzeichen wird nie vorweggenommen.** Ist die Wärmepumpe teurer als die Alternative, steht
dort ein Minus und das Wort **Mehrkosten** — nicht „Ersparnis +−49,53 €".

**CO₂ zählt vermiedene Wärme, nicht erzeugte Kälte** (ADR-001/DI-2). Die einzige
Konstruktionsstelle ist `berechne_co2_bilanz`; der Client rechnet nichts.

> ### S1b · Der Strom einer Wärmepumpe wird in jeder Geld- und CO₂-Rechnung voll belastet
>
> (Entscheid Gernot, 13.09.2026; ADR-002/**P9**, zweiter Fall.) Ihr PV-Anteil senkt weder ihre
> Stromkosten noch ihre Emission — er ist auf der PV-Seite gutgeschrieben: als **Eigenverbrauch**
> (Geld) und als **vermiedener Netzstrom** (CO₂). Ihn in der Wärmepumpen-Rechnung ein zweites Mal
> abzuziehen zählte dieselbe Kilowattstunde doppelt.
>
> Begründet an der Kategorie: Gegen die Baseline „ohne PV, ohne Wärmepumpe" ist die wahre Ersparnis
> `Gas − W·p + EV·p + F·v`. Bucht die PV-Seite `EV·p + F·v` und trägt die Wärmepumpe nur ihren
> Netzanteil, weicht die Summe um genau `W_PV·p` nach oben ab — **allein der volle Strom macht die
> Summe exakt**. Gemessen an der Demo-Anlage: 206,53 €/Jahr doppelt.
>
> Das Feld **„PV-Anteil (%)"** am Gerät beantwortet eine **Mengenfrage** — wie viel des
> Wärmepumpen-Stroms kam aus der eigenen Anlage — und speist genau zwei Stellen: den
> Eigenverbrauchs-Fallback der Prognose und die Zuordnung des Eigenverbrauchs auf das Gerät. Es
> beantwortet **keine Preisfrage**.

### 5.6 Wetternormierung — kWh je Heizgradtag

> **SOLL-§9-E8 (Entscheid Gernot, 12.09.2026).** Wetternormiert wird ausschließlich der
> **Heizbetrieb**.

* **Zähler:** der getrennt gemessene Heizstrom bzw. die Heizwärme. Warmwasser geht nie ein (nicht
  wetterabhängig), der Gesamtstrom nie (er enthält es). Ein abgeleiteter Heizstrom ist eine
  Verteilung, kein Zähler (E7); ein **gemessener** Betriebsart-Zähler *Heizen* scheidet aus, weil
  er den Warmwasser-Strom enthält.
* **Nenner:** **Heizgradtage** mit Heizgrenze **15 °C** (`HDD_Tag = max(0; 15 − Tagesmittel)`) —
  **eine** Definitionsstelle im Layer, dieselbe Konstante wie die Verbrauchsprognose.
* **Nur aus Tagesmitteln**, nie aus einem gepflegten Monats-Ø: `max(0; 15 − T)` ist konvex, ein
  Monatsmittel unterschätzt die Summe (gemessen **−26,6 %** im Mai 2026 der Demo-Anlage).
* **Saison-Größe:** Σ Strom ÷ Σ Kd über ein Saison-Fenster, nie ein Monatsquotient — an derselben
  Maschine Faktor 7,3 zwischen November und Mai, im Juni kein Nenner.
* **Ort:** Komponenten-Hub, Vergleich-Sektion, Achse *Saison*. Eine normierte **Arbeitszahl** gibt
  es nicht — sie ist bereits ein Quotient.

Wo eine der Größen fehlt, steht der Grund (S3).

### 5.7 Der Heizstab — drei Fälle, und nur einer ist ein Fehler

Ein elektrischer Heizstab wandelt Strom nahezu vollständig in Wärme (Wirkungsgrad ≈ 1). Gegenüber
einer Wärmepumpe mit Arbeitszahl 3–4 braucht er für dieselbe Wärme das Drei- bis Vierfache an
Strom — das ist der Grund, warum er jede Kennzahl nach unten zieht, in die sein Strom einfließt.

| Fall | Lage | Bewertung |
| --- | --- | --- |
| **H-A** | eigener Heizstab, eigener Zähler — als *Sonstiges/Verbraucher* erfasst | ✅ so vorgesehen; die Wärmepumpen-Zahl bleibt sauber |
| **H-B** | Heizstab **in der Wärmepumpe verbaut**, Strom **und** Wärme über dieselben Zähler | ✅ **das ist die Wahrheit über die Anlage** — fachlich die Systemarbeitszahl |
| **H-C** | Strom über den Wärmepumpen-Zähler, seine **Wärme nicht mitgemessen** | ⛔ der einzige echte Fehlerfall — R2 verletzt |

⭐ **eedc repariert H-B nicht, es erklärt es.** Eine Arbeitszahl unter 2,0 bekommt einen Satz
daneben: *„Eine Arbeitszahl nahe 1 entsteht, wenn ein großer Teil der Wärme direkt elektrisch
erzeugt wurde … Die Zahl beschreibt die Anlage in diesem Zeitraum, sie ist kein Fehler."* Das ist
keine Bewertung des Anwenders, sondern die Auskunft, die die Zahl lesbar macht.

⚠ **Die Schwelle feuert nur nach unten.** Der bivalente Fall (Q zu groß) erzeugt eine systematisch
**zu hohe** Zahl und wird von ihr nie gefangen — dafür gibt es die Anwender-Angabe
*„zweiter Erzeuger am Wärmezähler"*, und ihr Text nennt den elektrischen Heizstab ausdrücklich
mit: Bei Daikin und Nibe ist genau das der Regelfall.

---

## 6. Die Sichten und der Verlauf

**Der Grundsatz: Eine Sicht zeigt, was in ihrem Zeitraum messbar war — und benennt, was sie
deshalb nicht zeigen kann.** Ein „—" ohne Grund ist die häufigste Beschwerde dieser Fläche.

| Sicht | Zeigt | Zeigt bewusst nicht |
| --- | --- | --- |
| **Cockpit → Live** | Leistung je Gerät (bei getrennten Sensoren je Funktion), Betriebsart im Klartext, Anteil am Hausverbrauch | Mengen |
| **Cockpit → Tag** | alles aus stündlichen Zählern: Strom gesamt · je Funktion · je Betriebsart, Wärme und Kälte sofern gemessen, daraus die Tages-Arbeitszahl, dazu der Stundenverlauf | was nur der Monatsabschluss trägt — **mit dem Satz daneben, dass es monatlich gepflegt wird** |
| **Cockpit → Monat** | alles: gemessene und gepflegte Größen, alle Aufteilungen, alle Kennzahlen, Verlauf je Tag | — |
| **Cockpit → Jahr** | Σ der Monate; Kennzahlen **neu gerechnet**, nie gemittelt; Verlauf je Monat | — |
| **Komponenten-Hub** | dasselbe **je Gerät**, zusätzlich die **Herkunft** jeder Zahl (gemessen · geschätzt) und den Saison-Vergleich | anlagenweite Summen |
| **Auswertungen** | Vergleiche über die Zeit, Wirtschaftlichkeit, CO₂, Rohgrößen je Monat | — |
| **HA-Export · Bericht · Community** | dieselben Layer-Größen | Größen ohne stabile Bedeutung |

### 6.1 Die Regeln für alle Sichten

**S1 · Dieselbe Größe trägt überall denselben Namen und denselben Wert.** Wo zwei Sichten dieselbe
Frage beantworten, rechnet **eine** Stelle — der Layer, nicht der Client (ADR-001).

**S1a · Eine Tageszeile hat EIN Fenster.** Jede Teilmenge, jeder Anteil und jeder Quotient einer
Tagessicht wird in dem Fenster erhoben, in dem **der Bezug dieser Zeile** steht — unabhängig vom
Gerätetyp. Welches Fenster das ist, entscheidet die **Herkunft des Bezugs**: eine Wärmepumpen-Zeile
trägt das Fenster ihrer Provenance (Langzeitstatistik rückwärts, Snapshot-Pfad [0, 24)), ein Bezug
aus den Stundenzeilen liegt immer rückwärts. Lässt sich ein Zähler im Fenster seines Bezugs nicht
lesen, gibt es **keinen Wert und einen Grund** — nicht den Wert aus dem anderen Fenster.
⚠ Die Regel heißt **nicht** „alle rückwärts": ein unbedingter Schalter machte die Wärmepumpe im
Snapshot-Pfad wieder falsch.

**S1b · Der Wärmepumpen-Strom wird in jeder Geld- und CO₂-Rechnung voll belastet** → [5.5](#55-wirtschaftlichkeit-und-co₂).

**S2 · Ein Balken sagt, was er zeigt.** Wärme-Aufteilung und Strom-Aufteilung sind verschiedene
Größen; sie dürfen nicht unbeschriftet denselben Platz einnehmen. Wechselt der Inhalt je nach
Datenlage, wechselt auch die Beschriftung.

**S2a · Ein Stapel, eine Familie.** Der Wärme/Klima-Verlauf zeigt je Stunde **entweder** den Strom
nach **Betriebsart** (Teilmengen und Rest) **oder** nach **Funktion** (Summanden Heizen ·
Warmwasser, Rest „übrige") — **nie beide Stapel zugleich**, sonst addierte die Sicht Teilmengen zu
Summanden. Ein Umschalter am Verlauf wählt die Sicht; Titel und Legende nennen die gestapelte
Größe. „Nach Funktion" gibt es nur mit gepflegten Funktions-Zählern; vorbelegt bleibt die
Betriebsart-Sicht.

**S3 · Eine Sicht, die weniger zeigt als die Nachbarsicht, sagt warum.** Nicht „—", sondern „liegt
nur monatlich vor" oder „kein Wärmemengenzähler zugeordnet".

**S4 · Ein Verlauf zeigt nur GEMESSENE Wärme.** Wo die Wärme aus `Strom × Arbeitszahl` abgeleitet
ist, wird sie **nicht** als Linie gezeichnet: Sie ist ein Vielfaches des Stroms und hätte exakt die
Form der Stromfläche darunter — eine Linie, die nichts sagt, aber wie eine zweite Messung aussieht.
Die **Menge** steht weiterhin in der Kachel, mit ihrer Herkunft daneben.

> ⚠ **Und S4 meint die MENGE, nicht das Flag.** „Irgendein Teil irgendeines Geräts ist abgeleitet"
> ist für eine **Kennzahl** die richtige Auskunft (alles-oder-nichts; sonst käme gemessene Wärme ÷
> Gesamtstrom heraus). Ein **Verlauf** darf danach nicht ausblenden: Bei einer Wärmepumpe mit
> Wärmemengenzähler neben einer Klimaanlage ohne einen solchen wäre das Flag gesetzt, obwohl fast
> die ganze Wärme gemessen ist. Gezeichnet wird `Wärme − abgeleiteter Anteil`, je Periode. Eine
> Periode ohne gemessenen Rest ist eine **Lücke** in der Linie, keine Null und keine Verbindung
> darüber hinweg — die Lücke ist die Aussage.

**S5 · Der laufende Monat hat FÜNF Quellen — und die leere Kachel nennt ihren Grund** (N-472,
14.09.2026). Die Präzedenz ist *Monatsabschluss → HA-Statistik → Connector → MQTT → **lokale
Tagesebene***; die fünfte füllt nur, was die vier davor nicht beantworten, und verdrängt nie.

> **Warum sie überhaupt gebraucht wird.** Einen automatischen Monatsabschluss gibt es nicht — der
> laufende Monat hat **nie** eine `Monatsdaten`-Zeile. Wer weder HA-Statistik noch Connector noch
> eine MQTT-Zählerreihe hat, sah dort bis dahin **nichts**, während der Verlauf daneben dieselben
> Tage vollständig zeichnete. Gemessen an der Prüfstand-Anlage der Demo-DB r28: dreizehn
> aggregierte September-Tage, drei leere Kacheln darüber. **Das ist ein S3-Verstoß in Reinform** —
> eine Sicht, die weniger zeigt als ihre Nachbarin, ohne zu sagen warum.

1. **Jede Quelle nennt sich.** Die Tagesebene heißt *„Tageswerte"*, nicht *„gespeichert"*: Dahinter
   steckt kein Monatsabschluss, und wer danach suchte, fände keine Zeile.
2. **Wer nur einen Teil des Monats misst, sagt es** (P4). Das gilt für die Tagesebene, die erst
   mitten im Monat beginnt, **und** für den MQTT-Rückfall: Fehlt der Stand am Monatsersten, misst
   eedc ab dem **ersten Stand des Monats** und schreibt den Zeitraum ans Quellen-Etikett
   (*„MQTT (14.–30.09.)"*). ⛔ **Hochgerechnet wird nichts** — der Träger ist derselbe
   `abdeckung_von`/`abdeckung_bis`-Slot, den der Connector seit #361 benutzt, nicht ein zweiter.
3. **Der Rückfall gilt nur für die Anzeige.** Der Monatsabschluss-**Vorschlag** bekommt ihn nicht:
   Dort würde eine Menge „seit dem 14." als *Monatsmenge* gespeichert — genau der Datenverlust, den
   F-66 abgestellt hat.
4. **Bleibt eine Kachel leer, nennt sie ihren Grund** (W-18-Klasse, eine Zeitebene höher): *„für
   diesen Monat liegen noch keine Werte vor"* gegen *„für diese Größe hat keine Quelle geliefert"*
   — mit dem Handgriff daneben. Der Satz steht im Layer (`core/monatswert_grund.py`), nicht im
   Client; er trägt ihn nur. Und er steht an den **Basis**-Größen, nicht an den daraus abgeleiteten
   — sonst stünde derselbe Satz fünfmal, und das wäre die Strich-Flut, gegen die die **D-Sicht**
   unten gebaut ist.

5. **Die Wärme/Klima-Größen kommen aus demselben Leser wie der Verlauf daneben** —
   `waerme_verlauf.lade_waerme_monatsmengen_je_geraet`, also dieselben vier Leser, aus denen
   *Cockpit → Tag* seine Kacheln speist. ⛔ **Nicht aus einer zweiten Quelle**: Genau das
   Nebeneinander (*„der Verlauf zeigt dieselben Tage, die Kacheln nicht"*) war der Anlass, und zwei
   Quellen hätten daraus zwei Zahlen gemacht (**S1**). Geliefert werden **Rohfelder je Gerät** —
   K3 und D1 fallen danach wie bei jeder anderen Nicht-DB-Quelle. Die Tabelle *Zahlen je Gerät*
   fällt für den laufenden Monat auf `mengen_aus_tageswerten` zurück (dieselbe zweite Herkunft,
   die der Tag benutzt); ersetzt wird **nur, was leer ist**.

6. **S5 gilt für alle anlagenweiten Wärme/Klima-Eingänge, nicht nur für die Kacheln** (15.09.2026,
   N-503). Fehlt die Monatszeile, entstehen auch *Heizwärme*, *Warmwasser-Wärme*, *Strom Heizen*,
   *Strom Warmwasser*, das Kennzeichen **getrennte Strommessung**, der Hinweis auf einen
   **gemeinsamen** Wärmemengenzähler (N-391) und die **Deckung je Funktion** (R2) aus **denselben
   Geräte-Mengen** — eine Faltung an einer Stelle
   (`waerme_klima_block.funktions_eingaenge_der_anlage`), Σ über die Geräte, die die Achse
   **haben** ([5.1a](#51a--die-achsen-des-geräts-entscheiden-welche-funktions-zahl-es-gibt-e1--r1-15092026)),
   *Beitrag statt Bestand*. ⛔ **Der Anlass war ein Kasten, der seiner eigenen Tabelle
   widersprach:** *„Arbeitszahl Heizen · Arbeitszahl Warmwasser — Strom nicht getrennt je Funktion
   gemessen → Getrennte Strommessung einschalten"*, und **direkt darüber** zeigte die Tabelle
   *Zahlen je Gerät* für dieselbe Anlage 5,58 und 3,32 (r28/Prüfstand, September 2026). Der
   Handgriff führte ins Leere — beide Geräte tragen das Kennzeichen längst.
   ⚠ **Die Deckung gehört dazu, sonst wäre der Rückfall eine neue Falschaussage:** An derselben
   Anlage steuert ein Gerät Funktions-**Strom** bei und misst seine Wärme mit einem Gesamtzähler,
   ein anderes steuert Warmwasser-**Wärme** ohne Funktions-Strom bei. Ohne R2 stünden dort 3,35 und
   4,21 — Zahlen, die **derselbe** Monat nach seinem Abschluss sperrt (gemessen Juli und August
   2026). Eine zu Unrecht gezeigte Kennzahl ist teurer als eine zu Unrecht gesperrte
   ([§7](#7-mehrere-geräte)).
   ⛔ **Die Monatszeile gewinnt, wo sie eine Zahl trägt** — auch dort, wo die Faltung strenger
   wäre. Sie ist der Rückfall, nicht die bessere Lesart.

⭐ **Der Abgleich, den der Klassen-Docstring für jede neue Größe verlangt** — r28/Anlage 2, die
beiden Monate mit **beiden** Quellen, Σ Tagesebene gegen die DB-Monatszeile:

| Größe | Juli 2026 | August 2026 |
| --- | --- | --- |
| Strom (K3) | 215,40 / 215,40 — **+0,00 %** | 185,41 / 185,40 — **+0,01 %** |
| **Wärme (D1)** | 351,80 / 351,80 — **+0,00 %** | 343,40 / 343,40 — **+0,00 %** |
| Kälte | 360,00 / 360,00 — **+0,00 %** | 269,99 / 270,00 — **−0,00 %** |
| Kühlstrom · Nenner-Abzug | 120,0 / 120,0 — **+0,00 %** | 90,0 / 90,0 — **+0,00 %** |
| *Modus Warmwasser* | *28,30 / 26,30 — +7,59 %* | *28,30 / 26,30 — +7,61 %* |

⚠ **Die letzte Zeile ist ein Datensatz-Artefakt, keine Modell-Abweichung** — und sie speist keine
Kennzahl. Das Prüfstand-Gerät trägt in seiner IMD-Zeile **zwei** Zahlen für denselben Sachverhalt
(`strom_warmwasser_kwh: 28,3` aus dem Funktions-Zähler, `modus_strom_warmwasser_kwh: 26,3` aus dem
Betriebsart-Zähler); der Monatspfad liest den zweiten, die Tagesebene leitet aus den Snapshots ab,
die der Seed nach dem ersten gefüllt hat. Die Differenz ist in beiden Monaten konstant **2,0 kWh**
= genau 28,3 − 26,3.

⚠ **Die ehrliche Grenze, die bleibt:** Die **E-Mob**-Mengen trägt die Tagesebene weiterhin nicht
(`TagesMonatsSumme` führt dort nur die *Aufteilung* der Heimladung, nicht die Menge). Und eine
Wärme-Kachel bleibt leer, wo gar kein Wärmemengenzähler zugeordnet ist — dann greift Punkt 4.

**S6 · Der Tag sagt, was er abdeckt — und liest wie der Monat** (R-4, 15.09.2026, N-491 · N-492).
Ein Tageswert entsteht aus **zwei** Randständen. Fehlt einer, gab es bis dahin **keine** Zahl je
Gerät — und der Grund daneben war falsch.

1. **Fehlt der Stand am Tagesanfang, gilt der erste Stand des Tages.** Der Regelfall nach einer
   frischen Zuordnung: Snapshots entstehen erst ab der Zuordnung, der Monatswert kommt aus der
   HA-Langzeitstatistik und steht deshalb da. Die Zahl trägt dann *„gemessen ab 11:00 Uhr"*.
2. **Fehlt der Stand am Tagesende, gilt der letzte Stand** — der **laufende Tag**, dessen rechter
   Rand in der Zukunft liegt. Marke: *„gemessen bis 05:00 Uhr"*.
3. ⛔ **Hochgerechnet wird nichts** (ADR-002/**P4**) — und ein **Zählerrücksprung** bekommt keinen
   Rückfall: sein „keine Aussage" ist eine Entscheidung über Datenqualität (N-341), kein fehlender
   Punkt. Deshalb wird nur der Rand nachgefragt, der wirklich fehlt.
4. **Der W-18-Grund *„für diesen Tag keine Zählerstände"* bleibt** — aber nur, wenn im Tag **kein
   einziger** Stand liegt. Ein Stand allein ist kein Fenster; er ergäbe eine gemessene 0.
5. **Die Marke steht an der Basis-Größe**, nicht an jeder abgeleiteten — dieselbe Regel, mit der
   **S5** die Gründe im laufenden Monat verteilt. Der Wortlaut kommt aus dem Layer
   (`core/tageswert_grund.py::tages_abdeckung_hinweis`), der Client trägt ihn nur.
6. **Und eine Strommenge je Bildschirm** (N-492): *„kein Stromverbrauch erfasst"* ist eine Aussage
   über das **Gerät**. Sie ist falsch, wenn die Kachel daneben eine Zahl trägt und nur der Randstand
   dieses Tages fehlt — dann nennt der Grund die tatsächliche Lücke. Gemessen an der **Demo-Anlage**
   der r27: am 05.12.2025 stand *„Strom verbraucht 10,3 kWh"* neben *„Arbeitszahl — kein
   Stromverbrauch erfasst"*. ⛔ Ist **gar kein** Stromzähler zugeordnet, bleibt der alte Satz samt
   Handgriff: der W-18-Wortlaut spräche dort von einem *Wärme*mengenzähler.

7. **Die Deckung je Funktion prüft der Tag an seinen EIGENEN Geräte-Kennzahlen** (15.09.2026,
   N-506) — derselbe Aufruf wie der Monat (`waerme_klima_block.funktions_eingaenge_der_anlage`,
   [S5 Punkt 6](#61-die-regeln-für-alle-sichten)), nicht die Monats-Näherung. ⛔ **Der Grund ist
   gemessen:** Die Näherung ist im **laufenden** Monat leer — es gibt dort keine `Monatsdaten`-Zeile
   —, und damit fiel jede R2-Sperre aus. An der nachgestellten Prüfstand-Anlage (r28,
   `tag-detail?datum=2026-09-10`) standen *Arbeitszahl Heizen* **3,346** und *Warmwasser* **4,211**
   ohne jeden Grund, während *Cockpit → Monat* derselben Anlage mit dem zutreffenden Satz sperrte
   und derselbe Monat sie nach seinem Abschluss ebenfalls sperrt (Juli, August 2026). **Eine
   Deckungs-Aussage kommt aus denselben Mengen, die die Zahl bildet** — sonst bewacht sie eine
   andere Rechnung, als sie sieht. Deshalb stehen die Geräte-Kennzahlen des Tages im Code **vor**
   der Deckung, und deshalb kommt auch der **Nenner** der Funktions-Arbeitszahl aus derselben
   Faltung (sie kennt die Ein-Achsen-Regel, [5.1a](#51a--die-achsen-des-geräts-entscheiden-welche-funktions-zahl-es-gibt-e1--r1-15092026),
   die Tages-Summe nicht).
   ⚠ **Die Kühl-Deckung bleibt, wie sie ist** — sie zählt seit Bauschnitt 6 am Tag selbst und
   beidseitig; die Faltung beantwortet *kuehlen* ausdrücklich nicht.
   ⚠ **Der Zähler bleibt die Tagessumme**, und das ist keine Inkonsequenz, sondern Deckung: Die
   Faltung sieht nur die Geräte mit **Strom**-Beitrag des Tages, die Tagessumme jedes Gerät mit
   Wärme (r27/Demo, 05.12.2025: 29,9 kWh Heizwärme ohne einen einzigen Stromstand). Eine Kachel darf
   nicht schrumpfen, weil ein Nachbargerät seinen Zähler hat.

⚠ **Die ehrliche Grenze, die bleibt:** Kachel *„Strom verbraucht"* (Σ der Stundenspalte) und
Arbeitszahl-Nenner (Randdifferenz) messen weiterhin zwei um eine Stunde versetzte Fenster
([6.3](#63-die-fenster--warum-tag-und-monat-um-eine-stunde-auseinanderliegen)). An einem vollen Tag
mit stetigem Zähler ist der Unterschied nicht sichtbar; an einem **angeschnittenen** Tag ist er eine
von dreizehn Stunden (gemessen 16.09.: 2,16 gegen 2,34 kWh). Im HA-Add-on entfällt er, weil die
Tageszeile dort rückwärts liegt und der Detailpfad ihr folgt (**S1a**).

**A3a · Eine Sicht zeigt EINE Periode.** Nutzlasten tragen ihren Zeitraum, und eine Sicht paart nur
Antworten desselben Zeitraums. Zwei Abfragen mit denselben Abhängigkeiten, von denen eine ihren
Vorwert behält und die andere nicht, mischen sonst zwei Tage in einem Bild — auch ohne Cache, schon
über die Reihenfolge, in der sie auflösen.

**D-Sicht · Der Block zeigt, was die Daten hergeben — und sagt EINMAL, was noch
möglich wäre** (Entscheid Gernot, 14.09.2026). Anlass war der Vergleich mit
dietmar1968s selbstgebautem Dashboard: Auf **derselben** Datenlage zeigt es
überall Zahlen und „–" nur dort, wo wirklich nichts ist, während *Cockpit →
Monat* aus vier Strichen mit Grund-Texten bestand. Gemessen stimmte beides; der
Unterschied war die Form.

1. **Kacheln und Zeilen nur mit Zahl.** Eine Größe, die die **Ausstattung** nicht
   hergibt (kein Kältemengenzähler · keine getrennte Strommessung · ein
   gemeinsamer Wärmemengenzähler · kein Betriebsart-Zähler …), erscheint **nicht**
   als Kachel mit „—", sondern **einmal je Sicht** im Kasten **„Was noch möglich
   wäre"** am Blockende: je Grund eine Zeile mit den betroffenen Größen, dem
   Handgriff und dem Weg dorthin. Der Kasten ist aufgeklappt (**S3**: eine
   Auskunft, die man erst aufklappen muss, ist auf dem Telefon keine),
   einklappbar und parkbar wie jedes Block-Element.
2. **Eine Größe, die die Ausstattung hergibt, aber in diesem Zeitraum leer ist**
   (Arbeitszahl Heizen im Juni), zeigt **„—" ohne Text**. Dafür muss der Grund
   unterscheidbar sein: **Ausstattungs-Grund** (Kasten) gegen **Zeitraum-Grund**
   („—"). ⛔ **Die Zuordnung steht an der Grund-Konstante im Layer**
   (`waermepumpe_kennzahl.GRUND_KLASSE`), nicht im Client — dort müsste er
   Grund-**Texte** vergleichen, und dieselbe Aussage stünde an zwei Orten (die
   W-3-Klasse). Ein Grund **ohne** Eintrag gilt als Ausstattung: Er landet im
   Kasten, wo ihn jemand liest, statt als stummes „—" zu verschwinden.
3. **Kennzahlen je Gerät stehen im Block selbst** — Tabelle *Gerät · Wärme ·
   Strom · Arbeitszahl · Heizen · Warmwasser · Kühlen*. Der Hub-Link bleibt
   daneben; er führt jetzt zu *mehr* (Verlauf, Saison, Wirtschaftlichkeit) statt
   zu dem, was im Block fehlte. ⛔ **Eine Rechenstelle:** Die Kennzahl je Gerät
   gab es im Komponenten-Hub; sie ist nach
   `services/waermepumpe_kennzahlen_je_geraet.py` gehoben, und Hub **und**
   Cockpit lesen dasselbe Ergebnis.
4. Anlagenweite **Funktions**-Arbeitszahlen zeigt der Block nur, wo alle Geräte
   sie tragen — R2 je Funktion gilt unverändert.
5. **Kein Strich ohne Grund, keine Kachel ohne Zahl** (15.09.2026, N-500 ·
   N-502). Die Tabelle aus Punkt 3 kann eine Zeile nicht weglassen, solange das
   Gerät Mengen trägt — ihre Zellen haben deshalb eine eigene Regel:

   | Lage | Zelle |
   | --- | --- |
   | eine Zahl | die Zahl, ohne Tooltip — sie erklärt sich selbst |
   | kein Wert, Achse gilt | „—" **mit dem API-Grund als Tooltip** |
   | Achse gilt am Gerät nicht ([5.1a](#51a--die-achsen-des-geräts-entscheiden-welche-funktions-zahl-es-gibt-e1--r1-15092026)) | **leer** — „gilt nicht" ist kein Mangel |

   ⛔ **Dass die Tabelle einen Ausstattungs-Grund als Tooltip trägt und die
   Kachel nicht, ist kein Widerspruch:** Eine Kachel kann entfallen, dann steht
   ihr Grund einmal im Kasten. Eine Tabellenzeile kann das nicht; ihre Zelle
   bliebe sonst ein Strich ohne jede Auskunft. **Der Kasten nimmt den Grund
   zusätzlich auf** — mit dem Gerätenamen davor (*„Bosch Climate 5000
   Multisplit: kein Wärmemengenzähler zugeordnet → Wärmemengenzähler
   zuordnen"*), dedupliziert gegen die anlagenweiten Zeilen, damit dieselbe
   Auskunft nicht zweimal dasteht. Vorher stand **nirgends** im Block, dass
   diesem Gerät der Zähler fehlt: Der einzige Hinweis war der Schranken-Satz an
   der Kachel darüber, und der erklärt das „≥", nicht den Strich.

   ⭐ **Und eine Kachel ohne Zahl entfällt jetzt IMMER, nicht nur mit
   Kasten-Eintrag.** *Cockpit → Tag* zeigte die Kachel *„Ersparnis vs.
   Alternative"* an jedem geprüften Tag als „—" ohne Betrag, ohne Untertitel und
   ohne Tooltip — der Tag rechnet keine Ersparnis, `tag-detail` kennt das Feld
   gar nicht ([10.3](#103-benannte-grenzen-mit-ereignis-trigger)). ⛔ **Ohne
   Kasten-Zeile:** Der Kasten heißt *„Was noch möglich wäre"* und nennt
   Ausstattung, an der man etwas ändern kann; hier fehlt kein Zähler, sondern
   eine Rechnung in dieser Sicht.

⚠ **W-18 ist damit nicht zurückgenommen, sondern zu Ende geführt.** Der
zutreffende Grund bleibt Pflicht; neu ist, dass er **einmal** dasteht statt an
vier Kacheln — und dass der **Handgriff** danebensteht, den es vorher nirgends
gab.

**A6 · Eine Kennzahl zeigt, womit sie gerechnet hat.** Wer auf eine Arbeitszahl zeigt, sieht neben
der Formel die eingesetzten Zahlen — *„210,0 kWh Wärme ÷ 313,6 kWh Strom"*. Damit lässt sich eine
unplausible Zahl sofort einordnen: Passt eine der beiden nicht zu dem, was das Gerät meldet, liegt
es an der Zuordnung, nicht an der Rechnung. Ausgenommen sind triviale Summen mit **sichtbaren**
Summanden — ein Quotient aus zwei Nachbarkacheln ist dieselbe Klasse.

### 6.2 Der Verlauf — was er je Periode zeigt

Reihenfolge im Block: **Kacheln → Verlauf → Aufteilung**.

| | **Tag** (x = Stunde) | **Monat** (x = Tag) | **Jahr** (x = Monat) |
| --- | --- | --- | --- |
| **Strom**, gestapelt nach Betriebsart oder Funktion, Rest = *nicht aufgeteilt* | aus den Stundenzeilen je Gerät | je Tag aus **beiden** Zweigen | je Monat aus der Monatszeile |
| **Wärme** als **Linie** (gleiche kWh-Achse, nicht gestapelt) | je Stunde | je Tag | je Monat |
| **Kälte** als eigene Linie, eigene Farbe | je Stunde | je Tag | je Monat |
| **Außentemperatur** als Linie, zweite Achse, per Legende ausblendbar | Stundenwerte | Tagesmittel | Monatsmittel |

**Die Stunde verteilt den Tag, sie misst ihn nicht.** Die Stunden-kWh stammen aus dem
Leistungspfad, der Tageswert aus dem Zähler; der Stapel wird deshalb auf den Tageswert **normiert**
(*Zähler = Menge, Leistungspfad = Form*). Ohne diesen Faktor hätte der Stunden-Stapel eine andere
Summe als die Kachel darüber. Läuft alles über Home Assistant, stammen Tageswert und Stundenform
aus derselben Zählerreihe im selben Fenster — dort ist die Verteilung rechnerisch dasselbe wie eine
Stundenmessung. Auf dem MQTT-/Standalone-Pfad bleibt es eine Verteilung; **geglättet wird trotzdem
nichts**, denn eine über den Tag geschmierte Kurve wäre eine erfundene Form.

⛔ **Was keine Stundenform hat, wird genannt, nicht verteilt** — und **nicht über Gerätegrenzen
hinweg**: Eine Menge von Gerät A darf nicht nach der Stundenform von Gerät B verteilt werden.

**Der Verlauf erbt zwei Dinge vom Balken, statt sie neu zu beantworten:**

* **Die Grundmenge.** Der Stapel summiert nur die Geräte **mit** Aufteilung, nicht die Kachel
  „Strom verbraucht". Die Antwort darauf steht im Balken und im Verlauf gleich: *„Aufgeteilte
  Menge X von Y kWh"* — kein zweiter Turm über demselben Sachverhalt.
* **Das Tor.** Eine Periode ohne Modus-Signal und ohne Betriebsart-Zähler trägt **nichts** bei
  statt einer Reihe Nullen; hat keine Periode eine Aufteilung, fehlt der Stapel ganz.

**Die Außentemperatur kommt aus einer Vorrangkette, nicht aus einem Feld** (von genau nach
ungenau): (1) Stundenwerte — das echte Mittel über die gemessenen Stunden; (2) Tages-Min/Max —
`(min + max) / 2`, die klimatologische Näherung, für ältere Monate; (3) der gepflegte Monatswert —
zuletzt, weil die gemessenen Reihen der Anlage näher sind als ein Wert aus einem Archiv. ⛔ **Kein
Netzabruf für eine Hilfslinie.** ⚠ **Ø und Kd sind zwei Größen aus derselben Tagesreihe, nicht
dieselbe:** Für die **Heizgradtage** gelten nur die Stufen 1 und 2 — ein gepflegter Monats-Ø ist
dort kein Eingang ([5.6](#56-wetternormierung--kwh-je-heizgradtag)).

### 6.2b Die Verteilung — wohin der Strom gegangen ist (WK-16c, 14.09.2026)

**Der Verlauf sagt *wann*, die Verteilung sagt *wofür*.** Unter dem Verlauf steht
in allen drei Cockpit-Sichten ein weiterer parkbarer Blockteil *Verteilung &
Verlauf*: der Wärme/Klima-Strom je **Gerät und Funktion** als Anteile, dazu die
**Kosten je Funktion**, dazu dieselben Segmente über die Perioden — Stunden eines
Tages, Tage eines Monats, Monate eines Jahres — mit Ø-Außentemperatur und
Wettersymbol.

**Die Segmente sind keine neue Aufteilung, sondern die vorhandene, ausgeschrieben.**
Welche Familie ein Gerät trägt, entscheidet [Kapitel 3](#3-der-erfassungs-kanon--welcher-weg-gilt-wenn-mehrere-da-sind)
— **je Gerät, dann summiert** (Kapitel 7/E1: Mengen ja, Kennzahlen nein):

| Familie | Segmente | Rest |
| --- | --- | --- |
| **Summanden** (F5) | `heizen` · `warmwasser` aus den getrennten Zählern, dazu die **gemessenen** funktionsfremden Teilmengen (K4/W-16) | `system` — *System/Standby* |
| **Teilmengen** (Betriebsart bzw. Modus) | `heizen` … `entfeuchten` | `ohne_modus` — *Ohne Modus* |
| **keine** | — | — (die Menge bleibt, die Differenz wird genannt) |

⛔ **Nie beide Familien für dasselbe Gerät** (S2a): Ein **abgeleiteter** Modus-Split
verteilt die Menge, die die Summanden schon tragen; ihn danebenzustellen wäre die
Doppelzählung, gegen die W-16b gebaut wurde. Die Weiche steht **einmal**
(`core/berechnungen/waerme_verteilung.py::verteile_geraet_strom`) und ist dieselbe,
die `wp_strom_aufteilung` für die **Menge** stellt.

⚠ **Die zwei Reste stehen nebeneinander und heißen verschieden** — sie werden nie
addiert (Kapitel 3, Zwei-Reste-Tabelle). Dass beide zugleich im Bild stehen, geht
nur bei **zwei Geräten**; ein Gerät trägt genau eine Familie.

**Die Kosten hängen am Monatstarif** (ADR-002/**P8**): kWh × `TarifFakten.wp_preis_cent`
des jeweiligen Monats — die ganze Kaskade (Wärmepumpen-Sondertarif → allgemeiner
Tarif → Zeitfenster → Default), dieselbe Zahl, mit der der Tagespfad rechnet. Über
ein Jahr wird **je Monat** gerechnet und als Preis der mengengewichtete Mittelwert
gezeigt, damit `kWh × Preis = Kosten` aufgeht (**A6**). ⛔ **Es sind die Kosten des
verbrauchten Stroms, nicht des Netzbezugs** — welche Kilowattstunde aus der PV kam,
ist je Gerät ohne Zuteilungsannahme nicht bekannt (dieselbe Begründung wie bei der
Tarif-Gewichtung in `monats_fakten/tarif.py::_komponenten_preis`).

**Das Wettersymbol ist der häufigste Code der Periode** (Stunde direkt, Tag =
häufigster Stundencode, Monat = häufigster Tagescode). ⚠ **Nicht der schlechteste
Moment:** Ein Tag mit vierzehn Sonnenstunden und einem Schauer ist ein sonniger Tag.
Der Prognosepfad korrigiert dieselbe Verzerrung über die Bewölkung
(`wetter_symbol_aus_tag`); hier liegen alle Stunden vor, und der **Modus** der Reihe
ist die einfachere Antwort. **Ohne Code kein Symbol** — `wetter_code_zu_symbol(None)`
liefert `"unknown"`, und der Client zeichnet dafür eine Sonne (P4).

⚠ **Drei Differenzen, drei Sätze** (W-8) — jede wird **genannt**, keine
hineingerechnet: *„Aufgeteilte Menge X von Y"* (ein Gerät ohne Aufteilung, W-17b),
*„Im Verlauf erfasst X von Y"* (Perioden aus einer anderen Quelle als die
Verteilung, s. 6.3), *„Strom ohne Stundenzuordnung"* (keine Stundenform, P4).

⭐ **Kein Donut, und das ist kein Geschmack:** Der Aufteilungs-Donut ist am
19.06.2026 (B7-Revision) durch `VerteilungsBalken` ersetzt worden — eine
Bildsprache für **alle** Aufteilungen, mit den Werten *in* der Zeile statt in einer
Legende. dietmar1968s Donut, der den Anlass gab, zeigt dieselbe Information.

### 6.3 Die Fenster — warum Tag und Monat um eine Stunde auseinanderliegen

Liest eedc die Tageswerte aus der Langzeitstatistik von Home Assistant (der Regelfall im Add-on),
steht ein Tag für das Fenster *Vortag 23 Uhr bis heute 23 Uhr*. Das ist Absicht: Es ist dasselbe
Fenster, in dem eedc die Stunden zählt, und **nur deshalb geht eine Tageszeile in sich auf** —
Strom, Aufteilung, Wärme und Arbeitszahl desselben Tages messen dieselben 24 Stunden (S1a). Der
**Monats**wert läuft dagegen vom Monatsersten 0 Uhr bis zum Monatsletzten 24 Uhr.

⇒ **Die Summe der Tagessäulen enthält die letzte Stunde des Vormonats und nicht die letzte Stunde
des Monats.** Beide Zahlen sind richtig, sie messen nur nicht dieselben 24 Stunden. **Zu tun ist
nichts** — würde eedc eines der beiden Fenster verbiegen, wäre entweder die Tagesansicht in sich
falsch oder der Monatswert nicht mehr der, den Home Assistant kennt.

---

## 7. Mehrere Geräte

| Größe | addierbar? |
| --- | --- |
| Strom, Wärme, Kälte, Betriebsstunden, Starts | **ja** |
| Arbeitszahl, EER, JAZ | **nein** — nur neu berechnen aus Σ Q ÷ Σ E, und nur bei **gleicher Abgrenzung** |

**Addiert wird, was je Gerät schon aufgelöst ist.** Die Vorrangregel für die Wärme ([Kapitel 3](#3-der-erfassungs-kanon--welcher-weg-gilt-wenn-mehrere-da-sind))
wird **je Gerät** angewandt und erst danach summiert — genau wie K2 die Aufteilung je Gerät
entscheidet. Die Auflösung der Anlagensumme ist etwas anderes als die Summe der aufgelösten
Geräte, sobald zwei Geräte verschiedene Zählerlagen haben.

**Eine Kennzahl je Funktion gibt es für die Anlage nur, wenn jedes Gerät sie je Funktion misst.**
Trägt ein Gerät seine Wärme mit einem gemeinsamen Zähler, bleiben die Funktions-Zeilen der Anlage
ohne Zahl — auch wenn ein zweites Gerät seine beiden Achsen sauber trennt. Das ist R2, nicht
Vorsicht: Die Heizwärme des einen Geräts durch den Heizstrom beider zu teilen ergäbe eine Zahl,
deren Zähler und Nenner nicht dasselbe Gerät meinen. **Den Grund nennt die Vorrangkette aus
[4.2](#42-die-vorrangkette--welcher-grund-gewinnt):** am Gerät steht *„Wärme nicht je Funktion
gemessen"*, anlagenweit der genauere Satz *„Nutzenergie und Strom dieser Funktion stammen von
verschiedenen Geräten"* (gemessen 14.09.2026 an der nachgestellten Prüfstand-Anlage). Monat und
Tag entscheiden das gleich (ODER über die Geräte).

> ### ⭐ **Die Ein-Achsen-Regel gilt anlagenweit gleich — auch für die MENGEN** (15.09.2026, N-506)
>
> **Ein Gerät mit genau einer Wärme-Achse steht mit `waerme_kwh` und `strom_kwh` auf beiden Seiten
> dieser Achse** — Nutzenergie *und* Strom. Das ist [5.1a](#51a--die-achsen-des-geräts-entscheiden-welche-funktions-zahl-es-gibt-e1--r1-15092026)
> eine Ebene höher: Was je Gerät die Funktions-Arbeitszahl trägt, muss anlagenweit auch die Mengen
> tragen, aus denen sie entsteht.
>
> ⛔ **Sonst widerspricht der Block sich selbst.** Gemessen an der Prüfstand-Anlage (r28, September
> 2026): Die Brauchwasser-WP steuerte ihre 60,8 kWh Warmwasser-**Wärme** bei, ihre 18,4 kWh Strom
> **nicht** — er steht unter `stromverbrauch_kwh`, nicht unter `strom_warmwasser_kwh`. Die Deckung
> Warmwasser fiel damit auch an einer Anlage, an der es nichts zu beanstanden gibt, und im Kasten
> stand ein Handgriff (*„Getrennte Strommessung am zweiten Gerät einschalten"*) für ein Gerät
> **ohne zweite Funktion** — während die Tabelle darunter für dasselbe Gerät **3,31** zeigte.
>
> ⚠ **Sie ersetzt einen Grund, nie eine Zahl** (wie je Gerät): Wo die feinen Zähler **beide**
> Seiten hergeben, bleiben sie stehen — sie sind eine Messung *dieser* Funktion, der Gesamtzähler
> wäre der gröbere Nenner (K1).
>
> ⛔ **Und sie greift nicht, wo funktionsfremder Strom gemessen ist.** Der tragende Satz lautet
> *„sein ganzer Strom **ist** der Strom dieser Achse"* — er gilt einem Gerät ohne zweite
> **Funktion**, nicht jedem mit einer Wärme-**Achse**. Eine Split-Klimaanlage hat nach der Registry
> nur *Heizen* (kein Warmwasserkreis, N-304), **kühlt** aber; ihren Junistrom als *Strom Heizen*
> auszuweisen wäre eine Falschaussage über eine Menge (gemessen r28/Demo, 15.06.2026: **2,15 kWh**).
> ⚠ Gefragt wird die **Messung** (`modus_strom_kuehlen_kwh`, `funktionsfremd_abzug_kwh`), nicht die
> Bauart (ADR-002/**P13**). Ohne Betriebsart-Zähler weiß eedc von einem Kühlbetrieb nichts — dort
> greift die Regel wie bei einem Ein-Funktions-Gerät; dieselbe Annahme trifft die Kennzahl je Gerät.

> ### ⭐ **Der Kasten führt je Größe genau eine Auskunft — die mit der Adresse** (15.09.2026)
>
> **Steht für eine Größe eine Geräte-Zeile im Kasten, entfällt dort die generische.** Sie sagt
> dasselbe ohne Adresse, und ihr Handgriff kann sogar in die Irre führen. Gemessen (r28/Prüfstand,
> September 2026, *Cockpit → Monat*) standen **zwei** Zeilen für **dieselben** zwei Größen:
>
> * *„Arbeitszahl Heizen · Arbeitszahl Warmwasser — Nutzenergie und Strom dieser Funktion stammen
>   von verschiedenen Geräten → Getrennte Strommessung am zweiten Gerät einschalten …"*
> * *„Arbeitszahl Heizen · Arbeitszahl Warmwasser — Vaillant aroTHERM plus: Wärme nicht je Funktion
>   gemessen → Einen zweiten Wärmemengenzähler setzen …"*
>
> Die erste zeigte auf die Brauchwasser-WP, die keine zweite Funktion hat; die zweite nennt das
> Gerät, an dem es wirklich etwas zu tun gibt. **Ein Handgriff darf nie auf ein Gerät zeigen, das
> die Achse nicht hat.**
>
> ⛔ **Die Gegenrichtung bleibt unverändert:** Trägt die Geräte-Zeile **denselben** Grund,
> verschwindet *sie* (Dedup seit WK-16h) — der Gerätename brächte dann keine neue Auskunft. Die
> Regel greift also genau dort, wo die beiden Sätze **verschieden** sind.
>
> ⚠ **Die Größe bleibt im Kasten**, nur in der anderen Zeile: Der Client fragt über den
> Größen-**Namen** (`imKasten`), nie über den Text — es kommt keine Kachel zurück (**D-Sicht 1**).
> ⚠ Ein **Zeitraum**-Grund am Gerät verdrängt nichts: Er steht als „—" an der Kachel und nie im
> Kasten, erklärt dort also auch nichts (gemessen r28/Demo, Juni 2026 — ohne diese Unterscheidung
> fiel die richtige Zeile *„Arbeitszahl Kühlen — kein Kältemengenzähler zugeordnet"* weg).

**E1 (Entscheid Gernot, 26.08.2026): Geräte verschiedener Bauart werden nicht zu einer Kennzahl
zusammengefasst.** Eine Luft-Wasser-Wärmepumpe und eine Split-Klimaanlage haben verschiedene
Funktionen, verschiedene Nutzenergie und verschiedene Vergleichsmaßstäbe. **Mengen dürfen
nebeneinander stehen, eine gemeinsame JAZ nicht.** ⚠ Genauer nach R1: Die Trennlinie ist nicht die
*Bauart*, sondern die **Abgrenzung** — zwei Geräte teilen sich nur dann eine Kennzahl, wenn Q und E
beider dieselbe Funktion und denselben Zeitraum tragen. Bei verschiedenen Bauarten ist das
praktisch nie der Fall, weshalb der Entscheid trägt.

> ### ⭐ **E1b (Entscheid Gernot, 14.09.2026): die Anlage bekommt eine eigene Größe — die Systemarbeitszahl der Wärmeerzeugung**
>
> **E1 bleibt unverändert für die Kennzahl EINES Geräts.** Was hinzukommt, ist
> eine **andere Frage**: nicht *„wie gut ist diese Wärmepumpe?"*, sondern *„wie
> effizient erzeugt dieses Haus Wärme?"*
>
> **Die Formel:** Σ gemessene Wärme aller Wärmeerzeuger ÷ (Σ Strom aller
> Wärmeerzeuger − Kühlstrom nach [E7/Option A](#53-abgezogen-wird-nur-was-im-nenner-steht)).
> Sie steht an **einer** Stelle: `core/berechnungen/waermepumpe_kennzahl.py::systemarbeitszahl`,
> neben `arbeitszahl` und mit denselben Wortlauten für ihre Sperren.
>
> **Trägt ein Gerät Strom ohne gemessene Wärme bei** (Split-Klimaanlage ohne
> Wärmemengenzähler, Heizstab auf eigenem Zähler), ist die Zahl eine **untere
> Schranke** und wird so gezeigt: **„≥ 3,25"**, mit dem einen Satz *„<Gerät>:
> Strom ohne Wärmemessung enthalten"*. Ohne solches Gerät ist sie die gewohnte
> Arbeitszahl, ohne „≥".
>
> **Der technische Grund:** Mehr Strom im Nenner als gemessene Wärme im Zähler
> kann den Quotienten nur **kleiner** machen. ADR-002/**P4** verbietet eine
> *falsche* Zahl, nicht eine *wahre Schranke* — und ein Strich mit Grund-Text ist
> keine bessere Auskunft als „mindestens 3,25". **Der Melder rechnet selbst so**
> (dietmar1968, 14.09.2026: 7075 ÷ [2193 − 17] = 3,25).
>
> ⛔ **In der Gegenrichtung gibt es keine Schranke, und das ist der Kern.** Steht
> im **Zähler** Wärme, deren Strom fehlt (*„Wärme und Strom stammen von
> verschiedenen Geräten"*, *„zweiter Erzeuger am Wärmezähler"*, *„… aus
> verschiedenen Monaten"*), kippt die Zahl nach **oben** — dort bleibt die
> Sperre. Ebenso bei *„Zähler messen verschiedene Zeiträume"*: Die Richtung ist
> unbekannt, und eine Schranke ohne bekannte Richtung ist keine.
>
> ⚠ **Die beiden Gründe, die dadurch aufhören zu sperren**, sind
> *„Wärmepumpe und Klimaanlage in einer Zahl"* und *„nicht alle Geräte melden
> Wärme"* — **als Sperre der Anlagenzahl**. Je Funktion und im Hub gelten sie
> unverändert, und im Kasten *„Was noch möglich wäre"* stehen sie samt Weg in den
> Hub.
>
> ⛔ **Der PDF-Jahresbericht liest weiterhin `arbeitszahl`, nicht die
> Systemzahl** — eine Zahl ohne sichtbares „≥" im Druck wäre genau das, was P4
> verbietet. Zwei Fragen, zwei Größen.

**Multisplit: mehrere Innengeräte an einem Außengerät zählen als EIN Gerät für die Kennzahl**; die
Innengeräte sind eine **Aufteilung darunter**. Innengeräte-eigene Zähler sind als Mengenquelle
unbrauchbar — gemessen meldete ein Innengerät mehr als die ganze Anlage.

### Der Weg zwischen Cockpit und Hub

Sperrt eine anlagenweite Kennzahl, hilft der Komponenten-Hub **nicht immer**: Er rechnet je Gerät
und kennt alles nicht, was aus dem Zusammenspiel *mehrerer* Geräte entsteht. Deshalb steht im Layer
eine **Positivliste** und keine „alles außer"-Regel — ein neuer Grund erscheint dann ohne Link,
statt einen falschen zu erben. **Ein Link auf eine Sicht, die dasselbe sagt, ist schlechter als
keiner.**

| Grund | Hub hilft? | warum |
| --- | --- | --- |
| „Wärmepumpe und Klimaanlage in einer Zahl" | ✅ ja | der Hub zeigt jedes Gerät für sich |
| „nicht alle Geräte melden Wärme" | ✅ ja | dito |
| „Zähler messen verschiedene Zeiträume" | ✅ ja | dito |
| „Wärme und Strom stammen von verschiedenen Geräten" | ✅ ja | der Hub **nennt je Gerät die fehlende Seite** — „kein Stromverbrauch erfasst" am wärmemeldenden, „kein Wärmemengenzähler zugeordnet" am strommeldenden. Das ist die Diagnose, die die anlagenweite Zahl nicht geben kann |
| „Nutzenergie und Strom dieser Funktion stammen von verschiedenen Geräten" | ✅ ja | dito |
| Anwender-Angabe (Fremdverbraucher · zweiter Erzeuger) | ⛔ nein | die Angabe hängt am Gerät, der Hub sperrt genauso |
| „… aus verschiedenen Monaten" (Block **und** Funktion) | ⛔ nein | der Hub sperrt mit **demselben** Grund |
| „Wärme ist gerechnet, nicht gemessen" | ⛔ nein | dieselbe Regel je Gerät |
| Datenlage-Gründe („kein Wärmemengenzähler", „kein Heizbetrieb") | ⛔ nein | dort fehlt dem Hub dasselbe |

⚠ **Die Entscheidung gehört in den Layer, nicht in den Client.** Dort müsste er Grund-**Texte**
vergleichen; dieselbe Aussage stünde dann an zwei Orten und liefe beim nächsten Wortlaut
auseinander. Der Link ist ein Element des Blocks, keine Zeile je Kennzahl — deshalb **eine** Frage
und nicht vier.

---

## 8. Split-Klimaanlagen — die Bauform als Kapitel

Eine „Klimaanlage" ist physikalisch eine **Luft-Luft-Wärmepumpe**. Sie heizt und kühlt über
*denselben* Zähler und hat **keinen Warmwasserkreis**. Alles Übrige aus den Kapiteln 1–7 gilt für
sie unverändert — dieses Kapitel nennt nur, was diese Bauform zusätzlich braucht.

> **Die Entstehungsgeschichte steht weiterhin in zwei eigenen Dokumenten** und wird dort nicht
> gelöscht: [`KONZEPT-263-klima-split.md`](KONZEPT-263-klima-split.md) (Vermessung am Testgerät,
> Modus-Kanon, Entscheide E-A…E-I) und
> [`KONZEPT-263-INNENGERAETE.md`](KONZEPT-263-INNENGERAETE.md) (Multisplit). An ihren
> Abschnittsnummern hängen Code-Kommentare: `#263` steht an **154 Stellen in 68
> Produktivdateien** (gemessen 13.09.2026).

### 8.1 Der Betriebsmodus

**Der Kanon kennt sieben Werte:** `heizen` · `warmwasser` · `kuehlen` · `entfeuchten` · `lueften` ·
`aus` · `unbestimmt`. `unbestimmt` ist die Automatik-Stellung ohne Ist-Signal — sie einer Seite
zuzuschlagen wäre eine erfundene Aufteilung.

⭐ **`warmwasser` kam nachträglich dazu, und das ist die Lehre dieses Kapitels.** Der Kanon war
ohne ihn gebaut, belegt durch einen Satz über *drei Melder mit Klimaanlagen* — gelesen als Regel
über alle Wärmepumpen. **Eine Aussage über eine Bauform ist keine Aussage über die Fläche.**

Gespeichert werden drei Mengen plus Rest. `modus_abdeckung_h` trennt die zwei Fälle, die der
Anwender unterscheiden können muss: **Abdeckung hoch, Rest > 0** ⇒ das Gerät lief in anderen
Betriebsarten (Standby, Lüften). **Abdeckung niedrig** ⇒ eedc hat in dieser Zeit nicht hingesehen.

Der Modus ist ein **Momentanwert je Stunde, kein Zähler** — er steht deshalb als eigene Spalte in
der Stundenzeile und **nicht** im Komponenten-Dict, das kW/kWh trägt und von Whitelist-Konsumenten
summiert wird. Ein Zustandswert darin wäre die Einheiten-Verwechslung, aus der schon eine
Doppelzählung entstanden ist.

⚠ **Der Ist-Betrieb verfeinert, er überschreibt nicht** ([Kapitel 3](#was-jeder-vorausgesetzte-wert-leisten-muss)).

### 8.2 Die Wärme — ein Feld, eine Bedeutung, zwei Herkünfte

**Eine Luft-Luft-Wärmepumpe liefert dieselbe Heizenergie wie jede andere.** Der Unterschied ist
**messtechnisch, nicht physikalisch**: Bei Luft-Wasser geht die Wärme in einen Wasserkreis, in den
ein Wärmemengenzähler passt; bei Luft-Luft direkt in die Raumluft, wo es keinen Kreis gibt. Das
erklärt eine **Häufigkeit, keine Regel** — wer doch einen Zähler hat, ordnet ihn zu (R1).

⇒ **Ein Feld, eine Bedeutung, für jede Wärmepumpenart.** Unterschieden wird über die **Herkunft**:

| Herkunft | wie | Folge |
| --- | --- | --- |
| **gemessen** | Wärmemengenzähler | volle Verwendung |
| **abgeleitet** | `Strom × gepflegte JAZ` — nie aus einem Default | trägt die Marke, erscheint als *„geschätzt: Strom × JAZ 3,5"*, speist Ersparnis und CO₂ **mit dieser Kennzeichnung** und ist **nie** Kennzahl-Basis |

**Die Regel dahinter hat nichts mit der Bauart zu tun — sie trennt teilen von multiplizieren:**

| | darf abgeleitete Wärme verwenden? | warum |
| --- | --- | --- |
| **teilt** Wärme durch Strom → Arbeitszahl | **nein** | sonst kommt exakt die gepflegte JAZ heraus — eine Zahl, die nichts misst |
| **multipliziert** Wärme mit Preis / η / CO₂-Faktor | **ja**, mit Kennzeichnung | ohne sie verlöre jeder Anwender ohne Wärmemengenzähler Ersparnis und CO₂ vollständig |

⚠ **Warum die Schätzung überhaupt bleibt** (Präzisierung 05.09.2026): Ohne sie verlöre der
häufigste Fall — ein Gerät mit nur einem Stromzähler — Ersparnis und CO₂ ganz. Ohne Kennzeichnung
entsteht der gemeldete Fall: 889 kWh, die aussahen wie eine Messung, und eine Arbeitszahl, die die
gepflegte JAZ zurückgab. **Die Marke trennt beides.**

### 8.3 Innengeräte

**Gerätespezifisch ist nur der Zustand; jede Energiegröße bleibt ein Außengerätewert.** Alles je
Innengerät ist **Aufschlüsselung, niemals Summand** — das Gerätefeld schlägt die Summe der
Innengeräte, und sie werden nie addiert.

**Die eine Auflösung:** Quer durchs Backend entscheiden Namens-Whitelists über das Verhalten eines
Feldes (Poller? Snapshot? Einheit? Pflicht?). Alle vergleichen den *ganzen* Key — ohne Auflösung
fiele ein Innengerät-Suffix durch jede einzelne, **still**: Das Feld wäre zuordenbar und käme
nirgends an. Deshalb löst jeder dieser Leser über **eine** Funktion auf den Basis-Key auf. Der
Trenner ist sicher, weil kein einziger Registry-Key ihn enthält — und genau das hält eine Probe
fest.

**Grenze: kein Komponenten-Beitrag.** Betriebsart-Zähler werden gesnapshottet, erzeugen aber
**keinen** Tagesbeitrag — Strom je Betriebsart ist eine Teilmenge von `stromverbrauch_kwh`,
Nutzenergie ist thermisch. Als eigener Beitrag stünde die Wärmepumpe in der Tagesbilanz doppelt.

### 8.4 Was die Bauform am Modell nicht ändert

* **Kostenvergleich, Alternativkosten, CO₂, Monatsbericht, HA-Export** behandeln sie wie jede
  Wärmepumpe — nur ohne Warmwasser-Zweig, und die Arbeitszahl bleibt „—", solange die Wärme
  abgeleitet ist. **Ohne eine einzige eigene Read-Site.**
* **Ein Warmwasser-Feld wird ihr nicht angeboten und nicht gefordert.** Wer es fordert, verlangt
  etwas Unmögliches — genau das tat der Daten-Checker, bis R1 galt.

---

## 9. Datenquellen-Fläche und Daten-Checker

**Zwei Orte, zwei Fragen — und kein zweiter Turm über demselben Sachverhalt.**

| Ort | beantwortet | Ton |
| --- | --- | --- |
| **Datenquellen-Fläche** (Einstellungen → Datenquellen) | *„Was gehört hier hin, und was passiert, wenn ich es zuordne?"* — **zustandsabhängig, neben dem Feld** | Hinweis am Feld, kein Alarm |
| **Daten-Checker** | *„Was stimmt an meinen Daten nicht, und was tue ich dagegen?"* — **über die ganze Anlage, nach der Zuordnung** | INFO · WARNING mit Folge und Handgriff |

### 9.1 Die Zuordnungs-Fläche

* **Jedes Feld sagt seinen Bedarf** — Pflicht · optional · **inaktiv mit Grund**. „Inaktiv" heißt
  nicht „unwichtig", sondern *„hier ist nichts einzutragen, weil es woanders schon steht"*.
* **Die Bedarfs-Gruppe gilt je Gerät, nicht anlagenweit.** Zwei Wärmepumpen decken sich nicht
  gegenseitig ab; nur die Anlagen-Ebene (ein Hauszähler) tut das noch. Vorher meldete die eine
  Fläche „alles zugeordnet", während der Abdeckungs-Check ein fehlendes Feld anmahnte — **zwei
  Flächen, gegenteilige Aussage** über dieselbe Anlage.
* **Bei getrennter Strommessung bleiben beide Stromfelder Pflicht.** Sie sind **Summanden**, keine
  Alternativen — das leere Feld darf nicht „inaktiv" heißen. ⭐ **Und das Gesamtstromfeld daneben
  auch nicht** (seit 14.09.2026): Es ist **optional** und sagt, was es bringt — *„misst dieser
  Zähler mehr als Strom Heizen und Strom Warmwasser zusammen (Standby, Steuerung, Umwälzpumpen),
  gilt sein Wert als Verbrauch des Geräts und die Differenz erscheint als ‚nicht aufgeteilt'."*
  ⛔ Bis dahin stand dort *„Der WP-Stromverbrauch ist bereits zugeordnet — hier ist nichts
  einzutragen."*; wer dem folgte, verlor genau diese Kilowattstunden. **Eine Summanden-Gruppe deckt
  ihre Mitglieder nie ab** — das unterscheidet sie von einer Alternativ-Gruppe.
* **Heizwärme und Wärme gesamt sind Alternativen** derselben Größe (Gruppe `wp_waerme`). Ist
  eines zugeordnet, sagt das andere *„Die abgegebene Wärme ist bereits zugeordnet — hier ist nichts
  einzutragen."* — das Gegenstück zu den Stromfeldern oben, die Summanden sind und beide Pflicht
  bleiben. Der Daten-Checker mahnt deshalb die Heizwärme nicht an, wenn der gemeinsame Zähler
  gepflegt ist (sonst: dieselbe Anlage, zwei Flächen, gegenteilige Aussage).
* **Gesamtleistung verdrängt die Aufteilung.** Solange „Leistung gesamt" zugeordnet ist, wertet
  eedc „Leistung Heizen", „Leistung Warmwasser" und „Leistung Kühlen" im Verlauf nicht aus. Der
  Satz steht **am verdrängten Feld**, im Info-Ton, mit Info-Symbol — und **ohne** Knopf, der das
  falsche Feld leeren würde.

* ⭐ **Kein Feld ohne Auswertung — und die Fläche nennt sie (R-A, 14.09.2026).** Ein Feld, das
  die Fläche anbietet, wird in mindestens einer **Sicht** (Cockpit · Komponenten · Auswertungen ·
  Monatsbericht) **oder** als **HA-Sensor/MQTT-Publish** verarbeitet — und am Feld steht, wo:
  *„Ausgewertet in: Cockpit → Monat · Komponenten → Wärmepumpe."*

  **Der Grund gilt der Kategorie, nicht dem Auslöser:** Eine Zuordnung ist ein **Versprechen an
  den Anwender**. Ein Feld, das nirgends erscheint, bricht es **still** — und still ist das
  Problem: Der Anwender sieht eine 0 oder einen Strich und sucht den Fehler bei sich. Das ist die
  ADR-002/**P4**-Klasse eine Ebene früher: Nicht die Zahl fehlt, sondern jede Zahl.

  ⛔ **Daten-Checker und Vorschlags-Logik zählen NICHT als Auswertung.** Sie *prüfen* bzw.
  *schlagen vor*; beides beantwortet die Frage „wofür habe ich das zugeordnet?" gerade nicht. Ein
  Feld, das nur sie lesen, gilt als Feld ohne Auswertung und steht mit Begründung in
  ``FELDER_OHNE_AUSWERTUNG_BEKANNT`` (heute zwei, beide außerhalb Wärme/Klima: der Monatswert am
  *Wechselrichter*, der seit dem 24.08.2026 bewusst nichts mehr tut, und der *Tachostand*, aus dem
  nur der km-Vorschlag entsteht).

  ⚠ **Eine Quelle, kein zweiter Turm:** Die Liste steht in ``core/feld_auswertungen.py``, die
  Route liefert sie als ``ausgewertet_in``, der Client zeigt sie. Die Spalte in
  [`SENSOR-REFERENZ.md`](SENSOR-REFERENZ.md) ist von dort abgeschrieben und handgepflegt — es gibt
  keinen Generator.

* ⭐ **Nutzenergie Heizbetrieb ist Heizwärme (R-B, N-398).** Sie war seit dem 26.08.2026
  zuordenbar und hatte **keinen Leser**; wer sie pflegte, sah *Heizwärme 0* und den **falschen**
  Grund *„kein Wärmemengenzähler zugeordnet"*. Es gilt jetzt dieselbe Weiche wie beim Strom:
  Gerätefeld ``heizenergie_kwh`` (bzw. der Legacy-Name) schlägt sie; **fehlt es, trägt die Summe
  der gemessenen Nutzenergie Heizbetrieb** — je Innengerät aufgelöst wie jedes Betriebsart-Feld
  (**K2**: Gerätefeld schlägt Σ Innengeräte, nie addiert). Damit fließt sie in **D1** (Wärme gesamt
  aus Summanden, wenn kein Gesamtwert) und in jede Kennzahl, die auf D1 steht. Eine gepflegte **0**
  im Gerätefeld bleibt eine Messung und verdrängt den Rückfall.

  ⚠ **Sie stellt keinen NENNER — entschieden (Fable, 14.09.2026, Abnahme WK-16f).** Ein gemessener
  Betriebsart-*Strom Heizen* wird **kein** Nenner einer Funktions-Arbeitszahl; der bleibt der
  getrennt gemessene Strom dieser Funktion (``getrennte_strommessung``, E7). Begründet an der
  Kategorie *Gerät mit / ohne Warmwasser-Achse*: **Ohne** Warmwasser-Achse (Luft-Luft) trägt die
  **Gesamt**-Arbeitszahl dieselbe Zahl — Heizwärme ÷ (Strom − gemessener Kühlstrom, E7/Option A) —,
  eine zweite Kachel wäre dieselbe Zahl unter zweitem Namen (W-3-Klasse). **Mit** Warmwasser-Achse
  enthält der Betriebsart-Strom *Heizen* den Warmwasser-Strom (Kap. 5.6) und wäre als
  Funktions-Nenner zu groß. Wer es doch will, bringt ein Gerät mit, bei dem die Gesamt-Arbeitszahl
  eine andere Zahl trägt als die gewünschte Funktions-Arbeitszahl.

* ⭐ **Nutzenergie Lüften/Entfeuchten sind Mengenzeilen (R-C).** **E4 bleibt: keine Kennzahl.**
  Ihre Auswertung ist eine Zeile *„Nutzenergie Lüften"* / *„Nutzenergie Entfeuchten"* neben
  *„Strom Lüften/Entfeuchten"* — im Komponenten-Hub und im Wärme/Klima-Block von Cockpit →
  Monat/Jahr. **D-Sicht: nur mit Zahl.** Sie sind **kein** Segment des Strom-Balkens und zählen in
  **keine** Wärmesumme; kein Feld verlässt die Registry, keine Migration.

⛔ **Warum dieser Hinweis nicht in den Daten-Checker gehört** (Entscheid Gernot, 12.09.2026): Der
Checker meldet den Fall nicht, und eine zweite Meldung über denselben Sachverhalt wäre ein zweiter
Turm. Ein statischer Feld-Hinweis wiederum kennt den Zustand nicht und stünde auch dort, wo nichts
verdrängt wird. **Zustandsabhängig neben dem Schalter ist der einzige Ort, der beides kann.**

### 9.2 Was der Daten-Checker auf dieser Fläche prüft

| Befund | Ton | Aussage |
| --- | --- | --- |
| **Arbeitszahl auffällig hoch** (> 7,0) | WARNING | Verdacht: der Wärmemengenzähler sitzt hinter einem zweiten Erzeuger. Rechnet mit **denselben Eingängen** wie die Anzeige — sonst sähe er getrennt messende Anlagen nie |
| **Eine Stromseite fehlt bei getrennter Messung** | WARNING **je Seite** | Warmwasser-Wärme ohne Warmwasser-Strom (oder umgekehrt) ⇒ Nenner unvollständig, Arbeitszahl zu hoch. Handgriff: Monatsabschluss zuerst, Zuordnung zusätzlich |
| **Gesamtzähler kleiner als die Summe der Achsen** | WARNING | Regel 2 des Kanons: Strom Heizen und Strom Warmwasser sind Teile des Gesamtverbrauchs und können zusammen nicht mehr sein. Meist misst der Gesamtzähler nur einen Teil des Geräts. eedc rechnet in diesen Monaten mit der Summe der Achsen, damit nichts verloren geht |
| **Der Gesamtzähler misst deutlich mehr als die Achsen** (Rest > 25 % der Menge) | INFO | **eine Frage, kein Fehler:** Standby, Steuerung und Umwälzpumpen laufen auf keiner der beiden Achsen — es kann aber auch heißen, dass am Zähler noch etwas anderes hängt. Handgriff: Datenquellen prüfen |
| **Heiz- + Kühlstrom > Gesamtverbrauch** | WARNING | die Teilmengen-Invariante ist verletzt |
| **Gesamtwärme kleiner als Heizwärme + Warmwasser-Wärme** | WARNING | einer der Werte meint etwas anderes als gedacht — meist ist unter „Wärme gesamt" die Heizwärme gelandet; eedc rechnet mit der Gesamtwärme, die Monate fallen zu niedrig aus. Handgriff: im Monatsabschluss prüfen, welcher Zähler welchen Wert liefert. Die Gegenrichtung (Gesamt größer) ist kein Fehler |
| **Heizend-kühlendes Gerät ohne Modus-Quelle** | INFO | Heiz- und Kühlstrom bleiben zusammen; der OK-Titel unterscheidet „gemessen" von „abgeleitet" |
| **Modus-Quelle mehrdeutig** | INFO | mehrere Innengeräte zeigen auf verschiedene Entitäten ⇒ keine Aufteilung. Weg: eine Entität oder ein Template-Sensor |
| **Geschätzter Kühlanteil** | INFO | bei getrennter Messung ohne Kühlzähler: der Kühlanteil wird verteilt und kürzt die Arbeitszahl **nicht** ([5.3](#53-abgezogen-wird-nur-was-im-nenner-steht)). Handgriff: „Strom Kühlbetrieb" zuordnen |
| **Ø Temperatur fehlt in n Monaten** | INFO | mit der Angabe, für wie viele davon die eigene Messreihe reicht — dazu die **Aktion**, genau diese Monate nachzutragen |
| **Wert in einem nicht geführten Feld** | INFO | z. B. ein Warmwasser-Wert an einer Split-Klimaanlage — mit der Inline-Aktion, ihn zu entfernen |
| **Zähler mit Tages-Reset** | WARNING | keine Monatsmenge, und eedc rechnet nichts hoch ([2.2](#22-in-welcher-auflösung-eine-größe-entsteht)) |

⚠ **Die erwarteten Zähler kommen aus der Registry, nicht aus der Bauart** — dieselbe Quelle, die
die Zuordnungs-Fläche liest. Eine Klimaanlage bekommt deshalb kein Warmwasser-Pflichtfeld, ohne
dass irgendwo ein `if wp_art` steht.

⚠ **Ein Hinweis nennt die Ursache und den Ausweg — und keinen „Akzeptiert"-Knopf.** Eine Meldung,
die zu einem Sensor rät, den der Anwender längst hat, führt ihn in die Irre; das ist auf dieser
Fläche zweimal passiert.

---

## 10. Grenzen und Nicht-Ziele

### 10.1 Was eedc bewusst nicht sagt

Die vollständige Liste steht in
[`HANDBUCH_WAERME_KLIMA.md` §3](HANDBUCH_WAERME_KLIMA.md#3-was-eedc-bewusst-nicht-sagt) und §8 —
hier nur die Überschriften, damit sie an einem Ort nachlesbar sind: **kein SEER** · **keine
geschätzte Kältemenge** · **keine Bewertung von Lüften und Entfeuchten** · **keine Note für die
Anlage** · **keine 0, wo „unbekannt" gemeint ist** · **kein Vergleich passiv gegen aktiv gekühlt**
· **keine erfundene Stunde**.

### 10.2 Geerbte Grenzen, die ein Anwender sehen kann

Sie sind **keine Funde**, sondern Eigenschaften der Datenlage. Alle vier stehen im Handbuch:

1. **Monat gegen Jahr.** Die Tagessäulen des Monatsverlaufs kommen aus Snapshots, der Jahrespunkt
   aus der Monatszeile. Ein **importierter oder von Hand gepflegter** Monat hat keine Tageswerte —
   im Jahr steht sein Punkt, im Monatsverlauf bleiben die Säulen leer; ein Monat **vor der
   Zuordnung** hat es umgekehrt.
2. **Laufender Monat.** Kälte und Kühlstrom-Aufteilung kommen nur aus der gespeicherten
   Monatszeile; die laufende Vorschau kennt sie nicht. Linie und Kühlzahl stimmen dabei überein,
   weil beide aus derselben Quelle kommen.
3. **Randstunde.** Σ der Tagessäulen weicht im Rückwärtsfenster um genau eine Stunde vom
   Monatswert ab ([6.3](#63-die-fenster--warum-tag-und-monat-um-eine-stunde-auseinanderliegen)).
4. **Verteilung innerhalb eines Geräts im Snapshot-Pfad.** Wo einer Stunde ein Zählerstand fehlt,
   bleibt der Stundenwert eine Verteilung — genannt, nicht geglättet.

### 10.3 Benannte Grenzen mit Ereignis-Trigger

Diese Punkte sind **gemessen, begründet offen und nicht releaseblockierend** (Entscheid Gernot,
12./13.09.2026). Jeder trägt ein **Ereignis** als Auslöser, keinen Plan-Verweis — tritt es ein,
wird der Punkt fällig. Die Zuordnung zu den Fund-IDs steht in [Kapitel 12](#12-bezug).

| Grenze | Auslöser |
| --- | --- |
| **Der abgeleitete Zweig der Tagesaufteilung mischt im Snapshot-Pfad zwei Fenster** — die Form aus den Rückwärts-Slots, die Menge aus 0–24 Uhr. Der gemessene Zweig ist geheilt (S1a), dieser nicht | der erste Melder mit Betriebsmodus-Signal, dessen Tageszeile aus dem Snapshot-Pfad stammt — oder der nächste Eingriff an der abgeleiteten Tagesaufteilung |
| **„Nutzenergie Heizbetrieb" hat keinen Leser** — wer das Feld pflegt, bekommt den falschen Grund „kein Wärmemengenzähler zugeordnet" | der erste Anwender, der Heizwärme je Betriebsart oder je Innengerät zuordnet — oder der nächste Eingriff an der Wärme-Faltung |
| **Zwei Jahresschleifen über dieselben Fakten** — Formel zentral, Gruppierung je Sicht eigen | die fünfte Sicht — oder der nächste Eingriff an den Bilanz-Eingängen |
| **Die Bauart-Vorbelegung wird beim Umstellen mitgespeichert** — heute folgenlos | ein Lesepfad, der sie für Luft-Luft auswertet |
| **Eine Split-Klimaanlage bekommt den Wärmepumpen-Default für graue Last** — als `default` ausgewiesen, also kein erfundener Wert | klimaspezifische Defaults |
| **Die Counter holen ihren Lebensdauer-Stand im Fallback als Menge** | der nächste Eingriff an den Counter-Pfaden; der Umbau verlangt, die bestehende Snapshot-Reihe mitzuziehen |
| **Ein Modus-Feld je Innengerät** (Multisplit) | ein zweiter Multisplit-Melder, oder die Meldung, dass die Fernbedienungen auseinanderlaufen |
| **27 Eingabefelder im Monatsabschluss bei zwei Innengeräten** — doktrinkonform, aber viel Formular | die erste Melder-Rückmeldung. **Kein Bau ohne sie** |
| **Der Tag rechnet keine Ersparnis gegen die Alternative** — Monat und Jahr tun es; die Zusatzkosten der Altanlage sind Monatsgrößen und müssten anteilig verteilt werden. Seit 15.09.2026 **entfällt** die Kachel dort, statt als Strich ohne Grund zu stehen (D-Sicht 5) | ein Melder, der die Ersparnis am Tag vermisst |

### 10.4 Nicht-Ziele — verworfen und begründet

| Verworfen | Grund |
| --- | --- |
| **Geräte-Gruppen im Cockpit** | bricht die Achsentrennung Zeit/Gerät ([Kapitel 1](#die-arbeitsteilung-im-produkt)) |
| **Die Tages-Arbeitszahl entfernen** | das Zielbild verlangt sie, und ein Melder hat sie vermisst |
| **Heizgradtage im Cockpit** | sie gehören in die Vergleich-Sektion des Hubs ([5.6](#56-wetternormierung--kwh-je-heizgradtag)) |
| **Eine vereinheitlichte Rest-Kategorie** | es gibt bereits eine — *nicht aufgeteilt* (K5) |
| **Wärme als neues Feld im Stunden-JSON** | thermische Werte gehören nicht in eine Strombilanz |
| **Ein Kennzeichen „kann kühlen" am Gerät** | exakt die Bauform, an der K3 gescheitert ist: ein Kennzeichen, das einen vorhandenen Zähler entwerten kann |
| **Eine Faltung mehrerer Modus-Signale zu einem Anlagen-Modus** | eedc leitet nichts ab, wo es messen kann; die Zusammenführung gehört dem Anlagenbesitzer |
| **Aufteilung je Innengerät aus dem Modus-Signal** | die Innengeräte-Zähler sind Außengerätewerte; der Bedarf ist über **gemessene** Betriebsart-Zähler je Innengerät gelöst |
| **Hochrechnung eines Tagesreset-Zählers** | Datenqualität vor Bequemlichkeit ([2.2](#22-in-welcher-auflösung-eine-größe-entsteht)) |
| **Eigene Versorgung je Innengerät** | ohne diese Voraussetzung diagnostiziert die Teilmengen-Invariante falsch |

---

## 11. Wächter und Proben — was hält welche Regel

**Die Spalten wie in ADR-002:** **Wächter** = baumweit, fängt auch eine Stelle, die es heute noch
nicht gibt · **Regression** = schützt nur die namentlich aufgerufenen Stellen. Eine Regel ohne
Code-Beleg gilt als **nicht gesichert** und steht in [10.3](#103-benannte-grenzen-mit-ereignis-trigger)
oder im Bericht, nicht hier.

### 11.1 Die Grundsätze

| Regel | Wo sie gebaut ist | gesichert durch | Art |
| --- | --- | --- | --- |
| **R1** — der Zähler entscheidet, nicht die Bauart | `core/field_definitions.py` (Registry-Bedingungen), `pflicht_felder_am_geraet` | ADR-002/**P13**: `test_wurzelmuster_konformitaet.py::test_p13_bauart_leser_sind_klassifiziert` · `::test_p13_ausnahmen_sind_alle_erreichbar` · `::test_p13_offener_rest_schrumpft_nur`; Client-Hälfte `npm run check:bauart-roh` (Vitest-Wrapper `src/test/check-bauart-roh.test.ts`) | **Wächter** (Backend AST · Client datei-granular) |
| **R1** an der Fläche | dieselbe Registry | `test_soll_waerme_klima_achse1_erfassung.py` — 15 Proben, u. a. `test_i4_kuehl_achse_an_jeder_bauart_zuordenbar` · `test_i5_brauchwasser_waermepumpe_traegt_nur_die_warmwasser_achse` · `test_i6_luft_luft_fordert_kein_warmwasser`; `test_b2_daten_checker_registry.py::test_pflicht_felder_je_geraet_ohne_if_wp_art` | Regression |
| **R2** — gleiche Abgrenzung | `core/berechnungen/waermepumpe_kennzahl.py::abgrenzungs_grund` · `::abgrenzung_je_funktion` | `test_soll_waerme_klima_achse2_abgrenzung.py` (18 Proben, u. a. `test_ii2_bivalent_fremde_waerme_im_nutzen` · `test_ii2d_die_anwender_angabe_schlaegt_die_selbsterkennung`); `test_r2_je_funktion.py` (23 Proben); `test_n441_geraete_identitaet.py` (20 Lagen) | Regression |
| **Eine Arbeitszahl entsteht nur im Layer** | dasselbe Modul | ADR-002/**P12**: `test_wurzelmuster_konformitaet.py::test_p12_arbeitszahl_nur_im_layer` (AST, baumweit); Client-Hälfte `npm run check:cop-roh` (Wrapper `src/test/check-cop-roh.test.ts`); dazu `test_p12_arbeitszahl_alle_wege.py` | **Wächter** + Regression |
| **Eine Lücke ist keine 0** | ADR-002/**P4** | `test_wurzelmuster_p4_teilsumme.py`; auf der Fläche `test_soll_waerme_klima_achse3_aufloesung.py` (W-18-Gruppe) | **Wächter** + Regression |

### 11.2 Der Kanon und die Auflösung

| Regel | Wo sie gebaut ist | gesichert durch | Art |
| --- | --- | --- | --- |
| **K1 · K3** — die Vorrangkette | `core/field_definitions/wp_strom.py::wp_strom_stufe` · `::wp_strom_aufteilung` | `test_soll_waerme_klima_achse1_erfassung.py::test_i1…test_i3c` (sieben Lagen: Kennzeichen an/aus × Zählerbestand); `test_n451_monatspfad_k3.py` (Tag **und** Monat **und** Stundenpfad, Lagen i–ix); `test_n451b_k3_laufender_monat.py` (8 Proben: der **laufende Monat aus Nicht-DB-Quellen** — `aktueller_monat.py::_wp_strom_k3`, je Gerät; bis zum 14.09.2026 addierte dieser Pfad Gesamtzähler und Aufteilung: 2000 statt 1000, Arbeitszahl 1,5 statt 3,0) | Regression |
| **K1 · K5** — der Gesamtzähler ist die Menge, der Rest heißt *nicht aufgeteilt* | `field_definitions/wp_strom.py::wp_strom_aufteilung` (Menge · Rest · Toleranz an **einer** Stelle), `daten_checker/monatsdaten.py` (Widerspruch + Plausibilitätsfrage), `datenquellen_validierung.py::stufe_bedarf_ein` (eine Summanden-Gruppe deckt nichts ab) | `test_k3_gesamtzaehler_ist_die_menge.py` (17 Proben: Gesamt > Σ · Gleichstand · Toleranzkante · Widerspruch · Rest > 25 % · die zwei Ebenen · Handbuch B/B2 · Mischfall · Nicht-getrennt-Zweig) | Regression |
| **K3 Regel 4** — Betriebsart-Zähler sind feine Zähler (R-1) | `field_definitions/wp_strom.py::wp_strom_stufe` (die Stufe) · `betriebsart_gemessen.py::ModusStromZeile.gemessene_summe_kwh` (die Menge) · `::betriebsart_strom_felder_belegt` (K2 an der Zuordnung) · `komponenten_beitraege.py` (Tag/Stunde/Vorschau) · `aktueller_monat.py::_wp_strom_k3` (laufender Monat) | `test_wk16g_tag_liest_wie_der_monat.py::TestR1Menge` (8 Lagen: alle vier Betriebsarten · Innengeräte · Legacy-Gesamtfeld · abgeleiteter Split · **zwei Gegenproben**, Gesamtzähler und feine Achse schlagen die Teilmenge) · `::TestR1Zuordnung` (6 Lagen inkl. **W-16 am Tag** und seiner Gegenprobe) · `::TestR1AmTag` (Ende zu Ende) | Regression |
| **K2** — gemessen schlägt abgeleitet, je Gerät ganz oder gar nicht | `core/berechnungen/betriebsart_gemessen.py`, `core/berechnungen/tages_stapel.py` | `test_tages_stapel_gemessen_verdraengt_abgeleitet.py`; `test_263_innengeraete_varianten.py` (acht benannte Datenlagen V1–V8 über sechs Flächen, dazu die Mischanlage aus zwei Geräten) | Regression |
| **K4** — Summanden und Teilmengen nebeneinander | Registry + `funktionsfremd_abzug_kwh` | `test_n445_kuehlstrom_im_f5_heizstrom.py` (14 Proben, F5 mit und ohne Kühlzähler) | Regression |
| **K5** — der Rest heißt *nicht aufgeteilt* | `core/betriebsmodus.py`, Modus-Split | `test_263_k2_modus_split.py`; `test_soll_waerme_klima_e4_lueften_entfeuchten.py::test_e4_restmenge_zieht_die_neuen_segmente_ab` | Regression |
| **Gesamtwert vor Summanden (Wärme) — je Gerät** | `core/berechnungen/waermepumpe_kennzahl.py::waerme_gesamt_kwh` (Monat · Hub · HA-Export · Checker · Community) und die Geräte-Auflösung im Tag | `test_n391_gesamtwaerme.py` (15 Proben: Hub · Monat · Jahr · Tag · HA-Sensoren · Community · Checker · Invariante · CSV-Rundlauf · Client-Spiegel · Gruppen-Deckung; Lage D behält ihre Zahl); Mischfall zwei Geräte: `test_n391b_tag_je_geraet.py` (Kachel · Stundenlinie · Tagesliste · **Tag = Monat**); Geldpfade und Nicht-DB-Pfad: `test_n391c_geldpfade_d1.py` (Cockpit → Monat · Jahresformel · Aussichten · `typ_aggregation` mit Lage BEIDES, je Lage B = Lage D) | Regression |
| **Σ Teilmengen ≤ Gesamt** | Modus-Split-Normierung | `test_263_innengeraete_varianten.py::test_teilmengen_ueberschreiten_nie_den_gesamtwert` | Regression |
| **Strom je Betriebsart als abgeleiteter Kanal — K3-Menge der Stunde × Anteil, K2 (gemessen ⇒ kein Kanal), gleich der Tagesebene auf denselben Stunden** (HA-Bauform E4d) | `core/berechnungen/modus_split.py::modus_strom_der_stunde`, `services/kanal/modus_strom.py`, Leser `services/kanal/wp_leser.py`, Monatsabschluss `services/energie_profil/modus_split_schreiben.py::kanal_split_des_monats` | `test_kanal_modus_strom.py` (11 Proben: Regel der Stunde · Gleichheit mit `falte_modus_split_tag` · K3 je Stunde · Σ = Strom · Mitschrift-Verzug · K2 · Neuaufbau · beide Einstiege · Beginn mit dem laufenden Monat · abgeleitete Heizwärme wie beim Abschluss); `test_kanal_wp_gleichheit.py` (12 Proben: Wahl · Kanal-Monat ohne Abschluss = nach Abschluss = Bestand · ohne HA · Cockpit → Monat N-630 · der Bestand lädt gedeckte Monate nicht · der Abschluss schreibt im gedeckten Monat den Kanal-Split); die Matrix-Formen M05–M07 (`test_achsen_matrix.py`) | Regression |
| **Tagesreset-Zähler bekommt keine Menge** | Monats- und Tagespfad | `test_n341_reset_zaehler_wird_abgelehnt.py` (eedc liefert **keine Zahl**) und `test_n341_checker_zaehler_ruecksprung.py` (der Anwender **erfährt warum** — WARNING); `test_soll_waerme_klima_achse3_aufloesung.py::test_iii1a…test_iii1d` (fünf Lagen inkl. „ruhendes Gerät behält seine Null") | Regression |
| **Registry-Keys tragen keinen Bindestrich** (Voraussetzung der Innengeräte-Auflösung) | `field_definitions.basis_feld_key` | `test_263_innengeraete.py::test_kein_registry_feld_traegt_einen_bindestrich` (16 Proben in der Datei, je Eigenschaft eine) | **Wächter** (über die Registry) |
| **Ein thermisches Feld nennt seine Größe im Label, nicht nur im Hinweis** | Registry-Labels der Wärme-/Kältefelder | `test_thermische_felder_benennen_ihre_groesse.py` — vier Proben über alle thermischen Felder und ihre elektrischen Schwestern | **Wächter** |
| **Betriebsart-Zähler erzeugen keinen Komponenten-Beitrag** | `_SNAPSHOT_OHNE_KOMPONENTEN_BEITRAG` | `test_snapshot_felder_sot_konformitaet.py` | **Wächter** |

### 11.3 Die Kennzahlen

| Regel | Wo sie gebaut ist | gesichert durch | Art |
| --- | --- | --- | --- |
| **Je Funktion eine eigene Zahl** | `waermepumpe_kennzahl.py::arbeitszahl_je_funktion` | `test_soll_waerme_klima_w4_arbeitszahl_je_funktion.py` (8 Proben) | Regression |
| **Die Achsen des Geräts entscheiden — und ein Ein-Achsen-Gerät trägt seine Gesamtzahl als Funktions-Zahl** ([5.1a](#51a--die-achsen-des-geräts-entscheiden-welche-funktions-zahl-es-gibt-e1--r1-15092026)) | die Frage in `field_definitions/bedingungen.py::wp_waerme_achsen` (Registry, `feld_urteil == URTEIL_GILT`), die Folge in `waermepumpe_kennzahl.py::arbeitszahl_je_funktion(achsen=…, gesamt=…)` — **eine** Stelle, kein Nachbau je Read-Site; anlagenweit `waerme_klima_block.py::achsen_der_anlage`; die Namen kommen aus dem Kanon (`betriebsmodus.WAERME_ACHSEN`) | `test_wk16h_achsen_der_kennzahl.py` (29 Proben: Registry je Bauart · Brauchwasser = Gesamt · nicht geltende Achse ohne Grund · **Gegenprobe** „ersetzt einen Grund, nie eine Zahl“ · zwei Achsen **bitgleich** · Schranke geht nicht mit · Beitrag statt Bestand mit Gegenprobe · Monat · Jahr · **Tag** · Kasten mit Gerätenamen und Dedup) | Regression |
| **Kühl-Kennzahl aus der Kältemenge** | `::arbeitszahl_kuehlen` | `test_soll_waerme_klima_w5_arbeitszahl_kuehlen.py` (7 Proben) | Regression |
| **Eine gemessene 0 ist erfasst; Strom 0 und Wärme 0 ⇒ Stufe 3** ([4.3](#43-die-datenlage-geht-der-abgrenzung-vor), HA-Bauform E4d) | `::systemarbeitszahl(kein_betrieb_grund=…)` · `::kein_betrieb_grund_der_achsen` · `GeraetMengen.kein_betrieb` · `wp_wirtschaftlichkeit.wp_ersparnis_zeile(null_ist_kein_betrieb=…)`; die Marken `WpFakten.strom_gemessen`/`waerme_gemessen`; im Jahr `cockpit/uebersicht.py` (Übersicht und Kopf von Cockpit → Jahr) | `test_n585_gemessene_null.py::test_wp_kein_betrieb_*` (laufender Monat, Juni ohne Abschluss, je Gerät, Monat mit Zeile, Jahr in Übersicht und Cockpit → Jahr); Gegenfall Strom 0 ohne Wärme `::test_wp_strom_null_ohne_*` (Layer, je Gerät, Monat und Jahr); Matrix-Form M07 (`test_achsen_matrix.py`, 25 Zellen); Zeile 3′ (Funktions-Strom 0, Gesamtwärme) `test_e4f_h3_kein_heizbetrieb_vor_waerme_nicht_je_funktion.py` (Layer, Monat, Jahr, Prüfstand-Lage) | Regression |
| **E7 — der Nenner ist der gemessene Strom dieser Funktion** | `hat_split`-Tor in `arbeitszahl_je_funktion`; `imd_monatsaggregat.py` | `test_soll_waerme_klima_w4_*::test_w4_ohne_getrennte_strommessung_gibt_es_die_zahlen_nicht` · `::test_w4_zieht_keinen_funktionsfremden_strom_ab` | Regression |
| **Abgezogen wird nur, was im Nenner steht** | `betriebsart_gemessen.py::funktionsfremd_abzug_kwh` + `field_definitions/wp_strom.py::nenner_ist_feine_summe` | `test_n445_kuehlstrom_im_f5_heizstrom.py`; `test_n445_nachtrag_pfad_abzug.py`; `test_n451_monatspfad_k3.py::test_k8_*` · `::test_k9_*`; Community-Seite `test_community_funktionsfremd_abzug.py` | Regression |
| **E4 — Lüften/Entfeuchten erfassen, nicht bewerten** | Modus-Split + Nenner-Abzug | `test_soll_waerme_klima_e4_lueften_entfeuchten.py` (8 Proben) | Regression |
| **S1b — WP-Strom voll belastet** | ADR-002/**P9**, zweiter Fall; `alternativkosten.py`, `aussichten/finanz_prognose.py`, `wp_wirtschaftlichkeit.py`, `calculations.py` | `test_n459_wp_strom_voll_belastet.py` (⚠ **die Datei sagt es selbst:** Regressionen, kein Wächter — nach dem Bau existiert nur noch **eine** Bildungsvorschrift, es kann nichts mehr driften) | Regression |
| **E-B — Kühlen hat keine Ersparnis** | `alternativkosten.py`, `berechne_wp_ersparnis`, `berechne_co2_bilanz` | `test_roi_klimaanlage_nicht_bewertet.py`; `test_f41_f42_klima_bewertbarkeit.py`; `test_b5_ersparnis_symmetrie.py` | Regression |
| **Ein Vergleich setzt voraus, dass etwas ersetzt wurde** | `alternativkosten.py::ersetzt_keine_heizung` | `test_wp_ersetzt_nichts_n88.py` | Regression |
| **E8 — Heizgradtage, eine Definitionsstelle** | `core/berechnungen/heizgradtage.py` (`HEIZGRENZE_C = 15.0`) | `test_berechnungs_layer_konformitaet.py::test_heizgrenze_nur_im_layer` — **zwei Klauseln**: eine zweite Konstante **und** die ausgeschriebene Formel ohne Konstante (die gefährlichere, weil sie keinen Namen trägt) | **Wächter** |
| **E8 — Größe, Nenner, Achse** | `heizgradtage.py`, `mitteltemperatur.py`, Hub-Vergleich | `test_heizgradtage.py`; `test_mitteltemperatur.py`; `test_wp_hub_wetternormierung.py`; Client `WaermepumpeVergleichNormierung.test.tsx` | Regression |
| **E1b — die Systemarbeitszahl der Anlage** | `waermepumpe_kennzahl.py::systemarbeitszahl` (die einzige Stelle; Routen Tag · Monat · Jahr rufen sie) | `test_wk16_e1b_d_sicht.py` — 29 Proben: dietmars Rechnung (7075 ÷ [2193 − 17] = 3,25) · **Gegenprobe** ohne Schranke · Kühlstrom-Abzug · Q = 0 ⇒ Grund · Gegenrichtung sperrt weiter · Heizstab-Satz getrennt vom Schranken-Satz · Monat/Jahr/Tag über die Routen · **Tages-Kreuzung** (Wärme von A, Strom von B ⇒ Sperre statt „≥ 30,0") | Regression |
| **Eine Rechenstelle je Gerät** | `services/waermepumpe_kennzahlen_je_geraet.py` (Hub **und** Cockpit) | `test_wk16_e1b_d_sicht.py::test_der_dienst_ist_die_eine_rechenstelle_fuer_cockpit_und_hub` (mit gemessenem Kühlstrom, damit eine naive Rechnung sichtbar abwiche); dazu die **Hub-Bilanz** der Demo r28 vor/nach dem Umhängen — bitgleich | Regression |
| **Der Heizstab-Hinweis unter 2,0** | `JAZ_HEIZSTAB_SCHWELLE` | `test_soll_waerme_klima_achse2_abgrenzung.py::test_ii4d_heizstab_schwelle`; `test_soll_waerme_klima_w4_*::test_w4_heizstab_hinweis_erscheint_auch_je_funktion` | Regression |

### 11.4 Die Sichten

| Regel | Wo sie gebaut ist | gesichert durch | Art |
| --- | --- | --- | --- |
| **S1a — eine Tageszeile, ein Fenster** | `services/snapshot/boundary_range.py::TAGESFENSTER_JE_TYP` · `::tagesfenster_fuer` | `test_n444_tagesdetail_ein_fenster.py::test_jeder_ausgabe_typ_steht_in_der_tabelle` (**kein Typ fällt still durch**) + acht Offset-Fälle + Bitgleichheits-Probe | **Wächter** (über die Typ-Tabelle) + Regression |
| **S2a — ein Stapel, eine Familie** | `src/v4/waermeVerlauf.ts` (`VerlaufSicht`, `zeigtVerlauf`, `verlaufTitel`), Umschalter in `KomponentenSektionen.tsx` | `src/v4/waermeVerlaufUmschalter.test.tsx` — prüft ausdrücklich, dass der Betriebsart-Titel nach dem Umschalten **verschwindet**; „ohne Funktions-Zähler kein Umschalter"; „mit nur der Funktions-Sicht trotzdem ein Verlauf" | Regression |
| **S4 — nur gemessene Wärme im Verlauf** | `src/v4/waermeVerlauf.ts` (`Wärme − abgeleitet`, Lücke statt 0) | `src/v4/waermeVerlauf.test.ts`; `src/v4/waermeVerlaufMonat.test.ts`; `src/v4/waermeVerlaufTag.test.ts` | Regression |
| **Kälte als eigene Rolle und Farbe** | `waermeVerlauf.ts` (`kaelte`-Reihe), `lib/colors.ts::kaelteGemessen` | `src/v4/waermeVerlaufKaelte.test.ts` — eigene Farbe (≠ Kühl-Strom-Rolle), nie in der Wärme, Lücke statt 0, Durchreichung Jahr/Monat/Tag, Titel und Rest je Größe; Backend `test_bs6_kaelte_je_tag.py`, `test_bs6b_kaelte_linie.py` | Regression |
| **Deckel-Regel: Zähler = Menge, Leistungspfad = Form** | `src/lib/erzeugerSpalten.ts::wpSplitKw` (Senke) · `::pvSplitKw` (Quelle) | `src/components/tag/tagGeraeteSerien.test.tsx` (Einzelwerte, Rest aus der Differenz, K1 in beide Richtungen); `src/lib/erzeugerSpalten.test.ts` (drei Lagen unter/gleich/über, „er skaliert, er verteilt nicht") | Regression |
| **Funktions-Gruppen in der Detail-Liste** | `src/v4/wpFunktionsGruppen.ts`, `KomponentenSektionen.tsx::FunktionsGruppenListe` | `src/v4/wpFunktionsGruppen.test.tsx` (u. a. „keine Überschrift ohne Menge", „gemessene 0 bleibt stehen", „ohne Wert und ohne Grund keine Arbeitszahl-Zeile"); Backend `test_bs8_funktions_gruppen.py` | Regression |
| **Hub-Link nur, wo der Hub hilft** | `waermepumpe_kennzahl.py::GRUENDE_HUB_HILFT` · `::hub_hilft`; Client liest nur das Flag | `test_n441_geraete_identitaet.py::test_p11_der_hub_link_erscheint_nur_wo_der_hub_hilft`; `test_r2_je_funktion.py::test_hub_hilft_nur_bei_gruenden_die_der_hub_beantwortet` ⚠ **Client-seitig ohne eigene Probe** — der Client vergleicht keine Texte, er liest ein Flag | Regression (Backend) |
| **A3a — eine Sicht zeigt EINE Periode** | `CockpitTagV4.tsx`, `CockpitMonatV4.tsx`, `CockpitJahrV4.tsx`, `ZaehlerstaendeBlock.tsx` (Marke · Paarung · Beschriftung) | `CockpitTagEinTag.test.tsx`, `CockpitMonatEinePeriode.test.tsx`, `CockpitJahrEinePeriode.test.tsx` ⛔ **maschinelles Gegenstück bewusst keines** — so steht es im Style-Guide | Regression |
| **D-Sicht — Kacheln nur mit Zahl, ein Kasten je Sicht** | Klasse an der Grund-Konstante (`GRUND_KLASSE`, `HANDGRIFF_JE_GRUND`), Zusammenstellung in `services/waerme_klima_block.py`, Anzeige `src/v4/waermeKlimaSicht.ts` + `KomponentenSektionen.tsx` | Backend `test_wk16_e1b_d_sicht.py` (jeder Grund trägt genau eine Klasse · **jeder Ausstattungs-Grund einen Handgriff** · **kein Zeitraum-Grund einen** · jeder Grund genau einmal im Kasten · Größen-Namen als Vertrag); Client `src/v4/waermeKlimaSicht.test.tsx` (12 Proben: „≥" nur bei Schranke **und Gegenprobe** · Kachel entfällt nur mit Kasten-Eintrag **und Gegenprobe** · Kasten mit Handgriff und Link · Tabelle je Gerät) | **Wächter** (über die Klassen-Tabelle) + Regression |
| **Kein Strich ohne Grund, keine Kachel ohne Zahl** (D-Sicht 5) | `waerme_klima_block.py` (`WpGeraetZeile.achsen` · `waerme_grund` · `was_noch_moeglich(geraete=…)` mit Dedup), Anzeige `src/v4/waermeKlimaSicht.ts::geraetZelle` + die Tabelle in `KomponentenSektionen.tsx`; die Ersparnis-Kachel dort an der Wert-Bedingung | Backend `test_wk16h_achsen_der_kennzahl.py` (Kasten: Gerätename · Dedup gegen die Anlage · Zeitraum-Grund bleibt draußen · nicht geltende Achse bringt nichts mit · **Fail-open** ohne Achsen-Liste · Wärme-Zelle mit Grund **und Gegenprobe**); Client `src/v4/waermeKlimaSicht.test.tsx` (`geraetZelle` als reine Funktion · title je Zelle · leere Zelle ohne title · **Gegenprobe** geltende Achse ohne Zahl · Ersparnis-Kachel entfällt am Tag **und Gegenprobe** mit Betrag) | Regression |
| **Verteilung je Gerät und Funktion — eine Familie je Gerät, zwei Reste, Kosten am Monatstarif** | `core/berechnungen/waerme_verteilung.py::verteile_geraet_strom` (die Weiche) · `services/waerme_verteilung.py` (Eingänge, Preise, Wetter) · `services/energie_profil/waerme_verteilung_tag.py` (Stunden) · Client `src/v4/waermeVerteilung.ts` | Backend `test_wk16c_verteilung_verlauf.py` (24 Proben: Familien-Weiche · K4 neben den Achsen · **Doppelzählung mit Gegenprobe** · gemessene 0 ist kein Segment · beide Reste getrennt · Σ Geräte = Anlagenstapel · Zeitfilter · Kosten von Hand nachgerechnet · zwei Tarife, ein gewichteter Preis · häufigster Wettercode · kein Symbol ohne Code); Client `src/v4/waermeVerteilung.test.tsx` (13 Proben: Reihenfolge Funktion vor Gerät · `null` statt 0 · kein Stapel ohne Verlaufsmenge · drei Differenz-Sätze) | Regression |
| **S6 — der Tag sagt, was er abdeckt, und liest wie der Monat** (R-4 · R-5) | Rückfall in `services/snapshot/aggregator.py::_tagesdetail_boundary_diff_mit_grund` (`rueckfall_tagesrand`, **Schalter**) + `reader.py::letzter_stand_im_fenster`; die n-gegen-1-Präzedenz je Gerät in `core/berechnungen/wp_tages_praezedenz.py::loese_wp_tagesstrom_auf`; Wortlaut der Marke in `core/tageswert_grund.py::tages_abdeckung_hinweis`; der Strom-Grund in `waermepumpe_kennzahl.py::systemarbeitszahl(strom_fehlt_grund=…)`; Anzeige `KomponentenSektionen.tsx` (Untertitel an der Basis-Größe) | Backend `test_wk16g_tag_liest_wie_der_monat.py::TestR4Tagesrand` (8 Proben: erster Tag · laufender Tag · **kein Stand ⇒ Grund bleibt** · voller Tag bitgleich · Rücksprung · **der Rand knapp vor dem Tag**, die geschärfte Fassung nach Sprengsatz S9 · ein Stand ist kein Fenster · die Betriebsart-Zähler im selben Fenster) · `::TestR4StummerGesamtzaehler` (3: stumm ⇒ Achsen tragen · sprechend ⇒ K1 · **Tageszeile schlägt Tagesrand**) · `::TestR5EinBildschirm` (2 mit Gegenprobe); Client `KomponentenSektionen.wk16g-abdeckung.test.tsx` (4: Satz da · genau einmal · Gegenprobe · **die Naht** `baueTagAlsMonat`) | Regression |
| **S5 — fünf Quellen im laufenden Monat, und die leere Kachel nennt ihren Grund** | Präzedenz in `core/berechnungen/datenquellen.py` (`merge_datenquellen(tagesebene=…)`, `mqtt_teilzeitraum_felder`), Rückfall in `services/snapshot/reader.py::delta_mit_rand` + `mqtt_energy_history_service.py::mqtt_monats_mengen`, fünfte Quelle in `aktueller_monat.py::_collect_tagesebene_data`, **Wärme/Klima je Gerät** in `services/energie_profil/waerme_verlauf.py::lade_waerme_monatsmengen_je_geraet` (derselbe Leser wie der Verlauf), Wortlaut in `core/monatswert_grund.py` | Backend `test_n472_laufender_monat_quellen.py` (25 Proben: Rückfall nennt seinen Zeitpunkt · **ohne Schalter bitgleich** (F-66) · Stand am Ersten bitgleich · **Rücksprung bekommt keinen Rückfall, auch mit Rand knapp vor dem Monat** · Tagesebene füllt nur Lücken · gespeicherte Zeile schlägt sie · Komponentenwert ersetzt sie (#361-Klasse) · abgeschlossener Monat bleibt aus · Abdeckung wird ausgewiesen · Grund nur an den Basis-Größen · **WP-Strom/Wärme/JAZ aus der Tagesebene** · **Tabelle je Gerät ohne Monatszeile** · **gepflegte Zeile schlägt sie auch bei der WP** · ohne Tagesspur bleibt es beim Grund); Client `src/v4/MonatBilanz.test.tsx` (Grund-Gruppe, 3 Proben) + `src/v4/ProvenanzQuellen.test.tsx` (MQTT-Teilzeitraum · „Tageswerte" schweigt ab dem Ersten) | Regression |
| **S5 anlagenweit — die Eingänge der Funktions-Arbeitszahl aus denselben Geräte-Mengen** (WK-16i, N-503) | **Eine** Faltung in `services/waerme_klima_block.py::funktions_eingaenge_der_anlage` (Σ über die Geräte mit der Achse · *Beitrag statt Bestand* · `hat_split` · `waerme_ist_gesamt` · Deckung je Funktion über den Layer-SoT `deckung_aus_geraeten`), die S5-Weiche `::traegt_menge` für **beide** Fragen (je Gerät und anlagenweit), Aufruf in `aktueller_monat.py` — beide Herkünfte tragen dieselben Feldnamen, deshalb **ein** Codeweg | `test_wk16i_laufender_monat_funktionen.py` (19 Proben: Achsen-Filter in Faltung **und** Route · Beitrag statt Bestand · `waerme_ist_gesamt` · Deckung als Identitäts-Vergleich (drei Lagen) · **Kühlen beantwortet sie nicht** · leere Faltung sagt nichts (P4) · Vokabular-Wächter über beide Herkünfte · der Kasten widerspricht der Tabelle nicht mehr · Deckung je Funktion statt je Block · **die Monatszeile gewinnt, auch wo die Faltung strenger wäre** · ohne Tagesspur bleibt der alte Grund · abgeschlossener Monat liest die Zeile); dazu 24 Antworten aus r27/r28 gegen HEAD, **23 bitgleich** | Regression |
| **Der Tag prüft die Deckung an seinen eigenen Geräte-Kennzahlen** (WK-16j, N-506) | **derselbe** Aufruf wie der Monat — `api/routes/energie_profil/tag.py::get_tag_detail` ruft `waerme_klima_block.funktions_eingaenge_der_anlage`, und der Block mit den Geräte-Kennzahlen steht dafür **vor** der Deckung; der **Nenner** der Funktions-Arbeitszahl kommt aus derselben Faltung, der **Zähler** bleibt die Tagessumme (sie kennt jedes Gerät mit Wärme). Die Kühl-Deckung bleibt am Tag (`deckung_aus_geraeten`, Bauschnitt 6) | `test_wk16j_tag_deckung.py` (19 Proben: Ein-Achsen-Regel in der Faltung **mit** Zahl-Schranke und **mit** Gegenprobe funktionsfremder Strom · zwei Achsen fallen nicht zurück · Wärme ohne Strom bleibt im Zähler-Kreis · Kennzeichen weiter *Beitrag statt Bestand* · Handrechnung Nibe + Brauchwasser (96,359 ÷ 29,083) · **Gegenprobe** mit dem dritten Gerät · Kasten R-5 mit drei Gegenproben · über die Route: Sperre wie im Monat · **die Monatszeile entscheidet die Tages-Deckung nicht mehr** · Ein-Geräte-Tag behält seine Zahlen · **12,5 ÷ 3,5 statt 8,33** · die Wärme-Menge schrumpft nicht); dazu 22 Antworten aus r27/r28 gegen HEAD — **r27 vollständig bitgleich** | Regression |
| **Der Kasten führt je Größe eine Auskunft — die mit der Adresse** (WK-16j) | `waerme_klima_block.py::was_noch_moeglich` (R-5 nach dem Aufbau: generische Zeile verliert jede Größe, die eine **überlebende** Geräte-Zeile erklärt; der Dedup der Gegenrichtung bleibt) | `test_wk16j_tag_deckung.py` (vier Proben: generische Zeile entfällt · **je Größe**, nicht als Ganzes · derselbe Grund lässt die anlagenweite Zeile stehen · **ein Zeitraum-Grund verdrängt nichts**) | Regression |
| **A6 — eine Kennzahl zeigt ihre eingesetzten Werte** | Kacheln in Cockpit und Hub | `npm run check:formel-herleitung` (Wrapper `src/test/check-formel-herleitung.test.ts`) — TypeScript-AST über `src/**`, zwei Trägerformen (Objektliteral inkl. Shorthand, JSX-Attribut), drei Prüfungen, **abschmelzende** Allowlist mit Pflicht-Begründung; dazu `TKonto.a6-herleitung.test.tsx`, `KomponentenSektionen.jaz-herleitung.test.tsx`, `test_a6_arbeitszahl_je_funktion_herleitung.py` | **Wächter** + Regression |
| **R-A — kein Feld ohne Auswertung, und die Fläche nennt sie** | Liste `core/feld_auswertungen.py` (je Registry-Feld Sicht · Datei · Symbol, dazu `FELDER_OHNE_AUSWERTUNG_BEKANNT` mit Obergrenze); Route `api/routes/datenquellen.py::get_datenquellen_felder` (`ausgewertet_in`); Client `components/live/DatenquellenZuordnung.tsx` | `test_jedes_feld_hat_eine_auswertung.py` — leitet seine Referenzmenge bei **jedem Lauf** aus den Registries ab (`alle_registry_felder`, inkl. `BASIS_ENERGY_TOPICS` und `KUMULATIVE_COUNTER_FELDER`) und prüft je Eintrag: Datei existiert · Symbol ist dort definiert · Feldname **oder** die deklarierten Trägertoken stehen im Quelltext genau dieser Funktion. Dazu: ein modus-generischer Leser (`betriebsart_*_kwh(daten, modus)`) muss **seinen Modus** nennen — ohne diese Klausel belegte er alle vier Betriebsarten und reproduzierte den N-398-Blindfleck (an einem Sprengsatz gemessen, 14.09.2026). Baseline **0** für `waermepumpe`. Client `DatenquellenZuordnung.ausgewertet-in.test.tsx` (3 Proben, mit Gegenprobe „ohne Auswertung kein Satz") | **Wächter** (über die Registries) + Regression |
| **R-B/R-C — jede gemessene Betriebsart-Nutzenergie erscheint, auch am TAG** (R-2) | `waermepumpe_kennzahl.py::heizwaerme_kwh` (D1-Stufe 3, die **eine** Weiche) · seit dem 15.09.2026 je Gerät am Tag über `::heizwaerme_je_geraet` und den Ausgabe-Key `wp_betriebsart_heizen_kwh` (`aggregator.TAGESDETAIL_AUSGABE`) · `betriebsart_gemessen.py::nutzenergie_ohne_kennzahl_kwh` (E4: Menge ohne Kennzahl) · die Lesestellen von D1 (Layer · Hub/Cockpit je Gerät · Geldpfade · HA-Export) | `test_wk16g_tag_liest_wie_der_monat.py::TestR2Heizwaerme` (4: die Weiche je Gerät · **eine gemessene 0 der Achse gewinnt** · der Tag trägt die Betriebsart-Wärme · **Σ Tage = Monat**); `test_n398_nutzenergie_je_betriebsart.py` (25 Proben: die Weiche und ihre drei Stufen · **Bitgleichheit zur alten Lesetür** für Bestandszeilen · Anlage F4h über Hub, Cockpit → Monat und Jahr · Gegenprobe ohne Zähler · Gerätefeld und Gesamtwert gewinnen · Mengenzeile nur mit Zahl · keine Kennzahl für Lüften/Entfeuchten · keine Wärmesumme); Client `WaermepumpeNutzenergieZeilen.test.tsx` + `KomponentenSektionen.soll-waerme-klima.test.tsx` (je mit Gegenprobe) | Regression |
| **Keine Inline-Hex-Farben außerhalb des Farb-SoT** | `src/lib/colors.ts` | `npm run check:design` | **Wächter** |

### 11.5 Erfassung, Checker und Doku

| Regel | Wo sie gebaut ist | gesichert durch | Art |
| --- | --- | --- | --- |
| **Bedarfs-Gruppe je Gerät** | `services/datenquellen_validierung.py::_deckt_ab`; `field_definitions/bedingungen.py::pflicht_felder_am_geraet` | `test_n456_bedarfsgruppe_je_geraet.py` (u. a. „zwei Wärmepumpen werden getrennt eingestuft", „bei F5 bleibt das zweite Stromfeld Pflicht", „die Fläche folgt derselben Quelle wie der Abdeckungs-Check") | Regression |
| **Eine Alternativ-Gruppe zählt als Ganzes** (`BEDARF_GRUPPEN_ALTERNATIV`: Heizwärme ⇔ Wärme gesamt; Summanden-Gruppen wie `wp_strom` decken einander **nicht**) | `mqtt_topic_registry` (`pflicht_am_geraet`), `daten_checker/monatsdaten.py`, `daten_checker/energieprofil.py::_alternativ_geschwister` | `test_n391_gesamtwaerme.py::test_k8_…`/`::test_k12_…`; `test_daten_checker_tages_zusatzfelder_dok9.py` (Wärme gesamt deckt die Heizwärme ab · Warmwasser bleibt genannt · Summanden decken nichts) | Regression |
| **Gesamtleistung verdrängt die Aufteilung** | `datenquellen_validierung.py` (Satz + Erkennung), `DatenquellenZuordnung.tsx` | `test_n439_leistung_kuehlen_anzeige.py::test_gesamtleistung_verdraengt_jetzt_auch_das_kuehlfeld`; Client `DatenquellenZuordnung.info-hinweis.test.tsx` („keine Schaltfläche, die das falsche Feld leeren würde", Info-Ton, Info-Symbol) | Regression |
| **Fall L — jede fehlende Stromseite wird einzeln genannt** | `daten_checker/monatsdaten.py::_check_wp_monatsdaten` | `test_n443_f5_ein_stromfeld_fehlt.py` (drei Lagen: Warmwasser fehlt · Heizen fehlt · beide fehlen ⇒ eine Meldung) | Regression |
| **Der Arbeitszahl-Prüfer liest dieselben Eingänge wie die Anzeige** | `daten_checker/waermepumpe.py` · seit R-3 (15.09.2026) auch die **Heizwärme-Weiche** D1-Stufe 3 (`heizwaerme_kwh` statt der alten Lesetür `get_wp_heizenergie_kwh`), ebenso `daten_checker/monatsdaten.py` (Widerspruch Gesamtwärme · Fall L) | `test_daten_checker_wp_arbeitszahl.py::test_n450_die_getrennt_messende_anlage_wird_ueberhaupt_gesehen` · `::test_e7_der_pruefer_kuerzt_keinen_gemessenen_f5_nenner`; R-3: `test_wk16g_tag_liest_wie_der_monat.py::TestR3Checker` (3 Proben mit Gegenprobe — der Prüfer sieht die Betriebsart-Wärme, die Achse behält den Vorrang) | Regression |
| **Geschätzter Kühlanteil wird gemeldet, mit Handgriff und ohne „Akzeptiert"** | `daten_checker/datenquelle/klima.py` | `test_daten_checker_geschaetzter_kuehlanteil.py` (drei Proben) | Regression |
| **Temperatur-Historie: Zeile nennt beide Zahlen, Aktion nur die erreichbaren Monate** | `daten_checker/monatsdaten.py`, `api/routes/monatsdaten.py` | `test_n426_temperatur_historie.py` (u. a. „ohne erreichbare Monate gibt es keinen Knopf", „ein gepflegter Wert bleibt stehen", „der zweite Lauf findet nichts mehr") | Regression |
| **`leistung_kuehlen_w` erreicht Live-Bild, Snapshot und Tagesverlauf** | `live_komponenten_builder.py`, `live_sensor_config.py`, `live_tagesverlauf_service.py`, `mqtt_live_history_service.py` | `test_n439_leistung_kuehlen_anzeige.py` (16 Proben, u. a. Snapshot-Key, MQTT-Zweig, Symbolwahl, „die Gesamtleistung gewinnt gegen die Summe") | Regression |
| **Das Handbuch zitiert die Sperrgründe wörtlich** | `docs/HANDBUCH_WAERME_KLIMA.md` §4 | `test_soll_waerme_klima_achse3_aufloesung.py::test_handbuch_waerme_klima_zitiert_die_gruende_woertlich` · `::test_handbuch_nennt_jeden_lesbaren_betriebsmodus_wert` | **Wächter** (über die Konstanten) |
| **Der bivalente Fall nennt den elektrischen Heizstab — an allen vier Anwenderstellen** | Formular, Handbuch (zwei Stellen), Glossar | `::test_der_bivalente_fall_nennt_den_elektrischen_heizstab` · `::test_n349_die_abschnitte_trennen_die_beiden_lagen` — mit **Gegenanker** je Stelle, weil ein dateiweiter Substring-Test grün gewesen wäre | **Wächter** (über die Abschnitte) |
| **Die #263-Dokumente verweisen weiter** | Kopf beider Dateien | `::test_die_263_konzepte_verweisen_auf_den_geltenden_sot_und_das_handbuch` | **Wächter** |

### 11.6 Die nachgestellten Anlagen — der Ersatz für den fehlenden Gegenprüfer

`test_soll_waerme_klima_simulation_anlagen.py` (39 Proben) fragt etwas anderes als alle Tabellen
darüber: **Kommt die Zahl bei einer echten Datenlage auf der echten Fläche an** — vom Feld in
`verbrauch_daten` über die Monats-Fakten bis in die Antwort der Route?

⭐ **Warum das auf dieser Fläche mehr wiegt als anderswo.** Bei jeder anderen Größe ist der
Maintainer die letzte Instanz: Er sieht seine Anlage und merkt, wenn eine Zahl nicht stimmt. Hier
nicht — er besitzt weder Wärmepumpe noch Klimaanlage noch Heizstab. **Diese nachgestellten Anlagen
sind der Ersatz für den fehlenden Gegenprüfer**, nicht eine zusätzliche Bequemlichkeit.

⚠ **Der Prüfumfang ist die Größen-Matrix, nicht die Menge der Melder.** Was keine reale Anlage
belegt — passive Kühlung, Brauchwasser-Wärmepumpe, bivalente Anlagen, Lüften und Entfeuchten — wird
**als Fixture geprüft und als unbelegt gekennzeichnet**. Das ist etwas anderes als ungeprüft.

---

## 12. Bezug

### Dokumente

| Dokument | Verhältnis |
| --- | --- |
| [`HANDBUCH_WAERME_KLIMA.md`](HANDBUCH_WAERME_KLIMA.md) | die Anwendersicht derselben Fläche — Voraussetzungen, Zuordnung, Sperrgründe im Wortlaut, sieben Beispielanlagen |
| [`KONZEPT-263-klima-split.md`](KONZEPT-263-klima-split.md) · [`KONZEPT-263-INNENGERAETE.md`](KONZEPT-263-INNENGERAETE.md) | **Kapitel 8** — die Bauform Split-/Multisplit-Klimaanlage samt Entstehungsgeschichte |
| [`ADR-001-BERECHNUNGS-LAYER.md`](ADR-001-BERECHNUNGS-LAYER.md) | *wo* eine Formel definiert wird (S1) |
| [`ADR-002-WURZELMUSTER.md`](ADR-002-WURZELMUSTER.md) | **P4** (Lücke ist keine 0) · **P9** (ein Energiefluss trägt genau einmal bei, zweiter Fall = S1b) · **P12** (Arbeitszahl nur im Layer) · **P13** (die Bauart entscheidet keine Größe = R1) |
| [`KONZEPT-STYLE-GUIDE.md`](KONZEPT-STYLE-GUIDE.md) | **A3a** (eine Sicht, eine Periode) · **A6** (Berechnungs-Transparenz) · Regel 0/0a |
| [`BERECHNUNGEN.md`](BERECHNUNGEN.md) · [`GLOSSAR.md`](GLOSSAR.md) · [`SENSOR-REFERENZ.md`](SENSOR-REFERENZ.md) | Formeln, Begriffe, Sensoren |
| GitHub [#263](https://github.com/supernova1963/eedc-homeassistant/issues/263) | der Vorgang, aus dem Kapitel 8 entstanden ist |

### Die Grenzen aus 10.3 und ihre Fund-IDs

**Nur hier stehen die IDs** — im Fließtext hat eine Fund-Nummer nichts zu suchen, sie sagt einem
Leser nichts.

| Grenze (Kurzform) | ID | Band |
| --- | --- | --- |
| Abgeleitete Tagesaufteilung mischt im Snapshot-Pfad zwei Fenster | N-436 | P4 |
| „Nutzenergie Heizbetrieb" ohne Leser | N-398 | P4 |
| Zwei Jahresschleifen über dieselben Fakten | N-135 | P4 |
| Bauart-Vorbelegung wird mitgespeichert | N-91 | P6 |
| Grauer-Last-Default für die Split-Klimaanlage | N-278 | P6 |
| Counter-Lebensdauerstand im Fallback als Menge | N-307 | P6 |
| Ein Modus-Feld je Innengerät | N-298 | P6 |
| 27 Eingabefelder bei zwei Innengeräten | N-303 | P6 |

---

## Anhang — Entscheidungs-Register

Alle Entscheide sind von Gernot getroffen; das Datum ist das der Entscheidung, nicht des Baus.

### Die Zielbild-Entscheide

| # | Frage | Entscheid | Datum |
| --- | --- | --- | --- |
| **E1** | Werden Geräte verschiedener Bauart im Block getrennt dargestellt? | **ja** — Mengen bleiben summiert, **Kennzahlen** werden getrennt. Genauer: Die Trennlinie ist die **Abgrenzung** (R2), nicht die Bauart | 26.08.2026 |
| ~~E2~~ | Bekommt „Kühlen" eine Wirtschaftlichkeit? | **entfällt** — durch **E-B** bereits entschieden (18.08.) und gebaut (19.08.) | — |
| **E3** | Heißt die Kennzahl weiterhin überall „JAZ"? | **nachrangig, kein Fehlerbefund.** Die Vereinheitlichung COP → JAZ bleibt; offen ist allein, dass „Jahres"arbeitszahl über einen Tag irreführend klingt | 26.08.2026 |
| **E4** | Werden Lüften und Entfeuchten bewertet? | **nein** — erfassen ja, bewerten nein. Die Erfassung hängt seit R1 nicht mehr an der Bauart | 26.08.2026 |
| **E5** | Wird die Fläche unter **ein** Konzept gestellt (mit #263 als Kapitel)? | **ja** — die Fehler saßen an der Naht zwischen den Papieren. **Dieses Dokument ist die Ausführung** | 26.08.2026 |
| **E6** | Woran erkennt eedc, dass ein Gerät kühlen (heizen, entfeuchten …) kann? | **am zugeordneten Zähler** — beantwortet durch **R1**. Der Gegenvorschlag „Kennzeichen am Gerät" ist verworfen: exakt die Bauform, an der K3 gescheitert ist | 26.08.2026 |
| **E7** | Welcher Strom darf Nenner einer Funktions-Arbeitszahl sein? | **nur der gemessene**; der abgeleitete ist eine Verteilung und taugt allein für Kühlen. **Ergänzung (Option A):** abgezogen wird nur, was im Nenner steht | 12.09.2026 |
| **E8** | Wetternormierung: welche Größe, welcher Nenner, welche Achse? | **nur Heizbetrieb** mit gemessenem Heizstrom bzw. Heizwärme; **Heizgradtage 15 °C aus Tagesmitteln** (nie Monats-Ø); **nur auf der Saison-Achse** im Hub-Vergleich | 12.09.2026 |

⚠ **Namensgleichheit, die zweimal für Verwirrung gesorgt hat:** Es gibt ein **E7** im Zielbild
(Nenner-Herkunft, hier oben) und ein zweites **E7** in der Verlaufs-Planung („nur gemessene Wärme
im Verlauf") — letzteres ist in diesem Dokument **S4** und heißt nirgends mehr E7.

### Die Bauform-Entscheide (#263, Kapitel 8)

| # | Gegenstand | Entscheid | Datum |
| --- | --- | --- | --- |
| **E-A** | abgeleitete Wärme persistieren oder bei jedem Lesen rechnen? | persistieren | 18.08.2026 |
| **E-B** | Wird die Kühlhälfte wirtschaftlich bewertet? | **nein** — Kosten ja, Ersparnis nein | 18.08.2026 |
| **E-C** | Die drei Daten-Checker-Hinweise | **dreigeteilt**, nicht umgehängt | 18.08.2026 |
| **E-D** | Vier erfundene Nullen im Komponenten-Hub | entfernt | 18.08.2026 |
| **E-E** | Wem wird das Modus-Feld angeboten? | **jeder Wärmepumpe** | 18.08.2026 |
| **E-F** | Fährt ein Schnitt mit? | **abgelehnt** — der Schnitt bleibt | 18.08.2026 |
| **E-G** | Eigene Feldnamen statt Wiederverwendung | eigene | 19.08.2026 |
| **E-H** | Zählertreue Normierung | Invariante statt Kappung | 19.08.2026 |
| **E-I** | Ein Lader, zwei Aufrufer | persistiert mit `auto:monatsabschluss` | 19.08.2026 |
| — | Faltung mehrerer Modus-Signale | **gestrichen** — eedc leitet nichts ab, wo es messen kann | 21.08.2026 |
| **E1 (b)** | Ersetzen die Funktions-Gruppen alle drei Aufteilungs-Blöcke? | nein — **der Betriebsart-Balken bleibt**, er zeigt eine andere Größe | 11.09.2026 |
| **E3 (b)** | Wie heißt der Betriebsart-Balken bei getrennter Messung? | „Strom-Aufteilung nach Betriebsart" (S2) | 11.09.2026 |

### Die Tore der Fertigstellung

| Tor | Frage | Ergebnis | Datum |
| --- | --- | --- | --- |
| **G-A** | „Wärme und Strom stammen von verschiedenen Geräten" in die Hub-Positivliste? | **ja** | 12.09.2026 |
| **G-B** | Perioden-Klasse der Block-Ebene als eigener Fund? | **ja** | 12.09.2026 |
| **G-C** | Fall L als Fund am Daten-Checker, Fix am **Text** statt an der Zahl? | **ja** | 12.09.2026 |
| **G-D** | Zwölf Kacheln mit sichtbaren Nachbarwerten als A6-Ausnahme führen? | **ja** — ein Quotient aus zwei Nachbarkacheln ist dieselbe Klasse wie eine triviale Summe | 12.09.2026 |
| **G-E** | Drei Verdachte als Funde ablegen (Tagesfenster · Kühlstrom im F5-Nenner · Perioden-Mischung im Tag)? | **alle drei** | 12.09.2026 |
| **G-F** | Nenner-Herkunft als Zielbild-Satz festschreiben? | **ja** ⇒ E7 | 12.09.2026 |
| **G-G** | Wetternormierung: Heizgradtage 15 °C, Ort Hub-Vergleich, Glossar berichtigen? | **ja** ⇒ E8 | 12.09.2026 |
| **G-H** | Restliche Funde: bauen · offen mit Ereignis-Trigger · löschen | **so** — drei gebaut, sieben offen mit Trigger ([10.3](#103-benannte-grenzen-mit-ereignis-trigger)), einer verworfen | 12.09.2026 |
| **G-I** | PV-Anteil am Wärmepumpen-Strom: voller Strom überall? | **ja** (Kandidat A) ⇒ **S1b**, ADR-002/P9 erweitert; die E-Mob-Hälfte wird ein eigenes Vorhaben nach dem Release | 13.09.2026 |
| **G-J** | Der Monatspfad kennt K3 nicht — bauen? Stundenpfad mit? | **beides** — K3 ist Zielbild, der Handbuch-Satz war ein Doku-Stand | 13.09.2026 |
| **G-K** | „Leistung Kühlen": Anzeigepfad bauen oder Zusage zurücknehmen? | **Anzeigepfad bauen** (gegen die Empfehlung — der Umfang ist die Wahl des Maintainers); Multisplit-Erfassung bleibt begründet offen | 13.09.2026 |

### Die Methodenkorrektur, ohne die dieses Konzept anders aussähe

⛔ **Am 26.08.2026 hat Gernot die Ableitungsmethode verworfen, nicht eine einzelne Zeile.**
Wörtlich: *„Nicht gut finde ich, bei der Entwicklung eines sauberen, umfänglichen,
zukunftssicheren Konzeptes auf Probleme von Benutzern mit einer unvollkommenen Umsetzung
zurückzugreifen und davon auszugehen, dass die paar meldenden Benutzer das neue Konzept als
repräsentativ einschränken."*

Er hatte an drei Stellen recht: Die Melder-Population war zum Maßstab für den Bauumfang geworden,
die **Felder** wurden aus einer Aufzählung von Bauarten abgeleitet, und eine Beleglage las sich als
Prüfumfang. **Daraus entstanden R1 und R2** — beide ersetzen eine Aufzählung durch eine Regel.

⭐ **Der Prüfstein, dass die Korrektur trägt:** R2 fängt den **bivalenten** Fall, für den es keinen
Melder gibt und der in keiner Fallliste stand. Eine Fallsammlung kann das nicht.

**Die Trennlinie, die seither gilt:**

| Was | muss vollständig sein | warum |
| --- | --- | --- |
| **Das Modell** — welche Größen es gibt, welche Abgrenzung sie tragen, wann eine Kennzahl gültig ist | **ja, sofort und über den ganzen Fachraum** | Ein Modell, das einen Fall nicht ausdrücken kann, ist später **nicht nachrüstbar**: die bis dahin gespeicherten Daten sind dann falsch, nicht bloß unvollständig |
| **Die Ansicht** — welche Kachel wann erscheint, welcher Schritt existiert | nein, darf der Reihe nach entstehen | Eine fehlende Ansicht kostet einen Anwender eine Anzeige. Ein fehlendes Modell kostet ihn seine Historie |

Verhältnismäßigkeit gilt weiter — **für die Reihenfolge des Bauens, nicht für den Umfang des
Denkens.** Sie beantwortet *„was zuerst?"*, nie *„was überhaupt?"*.
