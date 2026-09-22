# Konzept — Flexible Strompreise in eedc

> **Was dieses Dokument ist.** Das Zielbild: welchen Preis eedc einer Kilowattstunde zuordnet,
> auf welcher Zeitebene, aus welcher Quelle — und welche Aussage daraus folgen darf. Geschrieben
> **aus dem Fachraum**, nicht aus den Fundstellen: es sagt, was richtig ist, nicht was eedc heute
> tut. Die Differenz zum Ist-Zustand wird danach gemessen und ist die Arbeitsliste (§10).
>
> **Auslöser:** Gernots Entscheid vom 2026-09-17 — *„Tage bleiben Messung, Monat bleibt
> Abrechnung."* Dieses Dokument schreibt die Regel aus, die darin steckt, und zieht ihre Folgen.
>
> **Stand:** Fassung 2, abgenommen und gebaut (Gernot, 18.09.2026: „Flex komplett bauen"). Der Kern
> ist mit v4.0.46 (17.09.) ausgeliefert, die Monats-/Jahresebene der Ersparnis (F4b), der gewichtete
> Tabellenfuß und die Zeitumstellungs-Proben am 18.09. — Stand der Umsetzung je Regel in §12 am Ende.
> Dieses Dokument ist das **Konzept** der Fläche; das SOLL unter `~/.claude/plans/soll-flex-tarife.md`
> ist seither historisch.
>
> ## Jede Aussage trägt eine Marke
>
> | Marke | Bedeutung |
> | --- | --- |
> | **[F]** | **Fachaussage** — folgt aus der Sache selbst (Tarifmechanik, Arithmetik); nachvollziehbar ohne eedc |
> | **[E]** | **Entscheid** — von Gernot getroffen, mit Datum |
> | **[A]** | **Annahme** — plausibel, aber nicht geprüft. Alle [A] stehen zusätzlich in §9 |
>
> **[A] ist keine Zusage.** Was in §9 steht, wird niemandem versprochen.

---

## 1. Der Grundsatz, aus dem alles Übrige folgt

**Der Preis ist bei einem flexiblen Tarif eine Messgröße wie die Kilowattstunde — kein
Stammdatum.** [F]

Das ist der ganze Unterschied zum Festpreis, und er wird in der Software leicht übersehen, weil
der Preis dort aussieht wie eine Einstellung: eine Zahl in einem Formularfeld. Bei einem
dynamischen Tarif ändert er sich laufend, eedc schreibt ihn laufend mit, und damit steht er auf
**jeder** Zeitebene so fein zur Verfügung wie die Menge selbst.

Daraus folgt die Gegenprobe, die an jede Geldzahl anzulegen ist — **drei Fragen, nicht zwei**:

> 1. **Welche Zeitauflösung hat die Menge, und welche der Preis**, mit dem sie multipliziert wird?
> 2. **Welche Menge wird bewertet** — und ist der Preis mit *dieser* Menge gewichtet oder mit
>    einer anderen?
> 3. **Über welchen Zeitraum und welche Größe** spricht die Quelle, aus der der Preis stammt?

Fallen Auflösungen auseinander, entsteht keine Näherung, sondern eine Verzerrung — und ihre
Richtung hängt davon ab, *wann* verbraucht wurde. Sie ist damit weder abschätzbar noch
korrigierbar. [F]

Wer nachts lädt und abends verbraucht, wird von einem Monatsmittel systematisch falsch
abgebildet, und zwar in beide Richtungen gleichzeitig: die Ladung zu teuer, der Nutzen zu
billig. Genau deshalb ist ein Mittelwert kein konservativer Kompromiss, sondern eine eigene
Fehlerquelle.

---

## 2. Der Slot — die Zeiteinheit, auf der alles aufsetzt

**Ein Slot ist der feinste Zeitraum, in dem Preis und Menge gemeinsam vorliegen — heute die
Stunde.** [F]

Er ist ein **Intervall der Anlagen-Ortszeit** (eedc folgt der Zeitzone von Home Assistant); ein
Tag der Zeitumstellung hat entsprechend mehr oder weniger Slots. **Preis und Menge eines Slots
gehören zusammen** und werden nie getrennt weiterverarbeitet.

⚠ **Keine Regel dieses Dokuments zählt Slots je Tag oder nennt eine Slot-Länge.** Der Day-Ahead-
Markt rechnet seit 2025 viertelstündlich **[A]**, und die Steuerung nach §14a arbeitet ebenfalls
feiner als stündlich. Wird der Slot künftig 15 Minuten, bleibt jede Regel hier wörtlich gültig;
nur die Tabellen in §3 nennen die Stunde als heutigen Wert. *Wer „Stunde" in eine Regel schreibt,
baut sie zweimal.*

---

## 3. Die Tarifarten — was jede über die Zeit aussagt

**Regel T-1 — Ableitbar oder messbar.** [F]
*Ein Slot-Preis ist **ableitbar**, wenn er eine Funktion aus Zeitpunkt und Vertrag ist; sonst ist
er **messbar**. Eine Mischform ist messbar, sobald einer ihrer Bestandteile nicht aus dem Vertrag
folgt.*

Das ist die tragende Unterscheidung des ganzen Dokuments, und sie ersetzt jede Aufzählung von
Tarifformen. Die folgende Tabelle ist **Fachkunde, keine Ableitungsgrundlage**:

| Art | Preisverlauf | Slot-Preis |
| --- | --- | --- |
| **Festpreis** | ein Arbeitspreis bis zur nächsten Vertragsänderung | ableitbar (überall gleich) |
| **Zeitfenster** (HT/NT, §14a Modul 3) | mehrere Preise nach Zeitpunkt, deterministisch | ableitbar, sobald die Fenster gepflegt sind |
| **Dynamisch** (börsenorientiert) | je Slot verschieden, am Vortag bekannt | messbar — und **nur** messbar |
| **Mischform** (z. B. dynamisch mit Deckel) | `min(Markt, Deckel)` o. ä. | messbar, weil der Marktanteil nicht aus dem Vertrag folgt |

Daraus folgt unmittelbar: „kein Slot-Preis vorhanden" ist bei einem Festpreis kein Problem
(er ist ableitbar) und bei einem dynamischen Tarif eine echte Lücke.

**Der Endpreis ist nicht der Börsenpreis.** [F] Zwischen beiden liegen Beschaffungsaufschlag,
Netzentgelte, Abgaben und Steuern — je nach Anbieter ein Vielfaches des Börsenanteils. Ein
Börsenpreis darf die **Form** über die Zeit liefern, nie den Betrag, mit dem gerechnet wird; es
sei denn, der Anwender hat ausdrücklich einen dynamischen Tarif und die Zahl ist als Näherung
beschriftet.

---

## 4. Die drei Preisebenen

| Ebene | Definition | Quelle |
| --- | --- | --- |
| **Slot** | der Preis dieses Slots | gemessener Endpreis; bei ableitbaren Tarifen aus dem Vertrag |
| **Tag** | Σ(Preis_s × Menge_s) ÷ Σ Menge_s über die Slots **dieses Tages** | aus der Slot-Ebene |
| **Monat** | **abgerechnet:** aus der Rechnung des Versorgers · **gemessen:** Σ(Preis_s × Menge_s) ÷ Σ Menge_s über den Monat | Anwendereingabe bzw. Slot-Ebene |

**Regel A-1 — Ein Durchschnittspreis ist immer mengengewichtet, nie arithmetisch.** [F]
Das arithmetische Mittel beantwortet eine Frage, die niemand stellt („was kostete ein
durchschnittlicher Slot") statt der, um die es geht („was kostete die Energie, die geflossen
ist"). Ein teurer Winter- und ein billiger Sommermonat wiegen sonst gleich viel, obwohl im Winter
das Dreifache bezogen wurde.

> **Die Abdeckung wird als Anteil der bewerteten *Menge* angegeben, nicht als Anteil der Slots.**
> „68 % der Monatsstunden" sagt weniger als „68 % des Bezugs" — fehlen ausgerechnet die
> verbrauchsstarken Slots, ist eine hohe Slot-Abdeckung wertlos.

**Regel A-2 — Gewichtet wird mit der Menge, die bewertet wird.** [F]
Der Bezugspreis mit dem Bezug, der Ladepreis eines Speichers mit der Netzladung, der vermiedene
Preis mit der vermiedenen Menge je Slot.

> ⛔ **Hier stand in Fassung 1: „gewichtet wird mit der Menge derselben Richtung."** Das ist
> widerlegt. Für die Eigenverbrauchs-Ersparnis gibt es in den Slots, in denen der Bezug vermieden
> wurde, **gar keine gemessene Bezugsmenge** — Eigenverbrauch fällt mittags an, Netzbezug abends.
> Ein mit dem Bezug gewichteter Ø bewertet die vermiedene Menge deshalb systematisch **zu hoch**.
> Die Menge, die bewertet wird, ist die vermiedene — und nur sie darf gewichten.

**Regel A-3 — Kosten sind die Summe der Slot-Kosten; ein Durchschnitt ist daraus abgeleitet,
nie umgekehrt.** [F]
Die Kosten einer Ebene sind Σ(Preis_s × Menge_s) über die Slots, die **beides** tragen. Wer
stattdessen Ø × Gesamtmenge rechnet, interpoliert bei Teilabdeckung nach unten: 18 Slots mit
Preis, 24 mit Menge — und die sechs preislosen bekommen stillschweigend den Durchschnitt.

Der Nebeneffekt dieser Regel ist wertvoll: Die Teilsumme ist **additiv und richtungssicher zu
niedrig** (sie kann beschriftet werden, statt unterdrückt zu werden), und der Durchschnitt ist
ein Quotient über genau dieselbe Slot-Menge — ein Abdeckungskonflikt zwischen Zähler und Nenner
kann gar nicht erst entstehen.

---

## 5. Präzedenz — welcher Preis gilt wo

Dies ist der Kern des Dokuments.

### P-1 · Eine Abrechnung gilt für den Zeitraum **und die Größe**, für die sie ausgestellt ist [E, 17.09.2026]

Ein abgerechneter Monatswert ist die Wahrheit über **den Bezug dieses Monats**. Er ist keine
Aussage über einen einzelnen Slot, keine über einen Tag — **und keine über eine andere Größe**.
Eine Bezugsabrechnung sagt nichts über Eigenverbrauch, nichts über die Ladung eines Speichers und
nichts über den Wert vermiedener Energie. Der Versorger hat diese Größen nie bepreist.

### P-2 · Unterhalb des abgerechneten Zeitraums gilt die Messung [E, 17.09.2026]

Für Slot und Tag gibt es keine Abrechnung. Dort ist die gemessene Slot-Reihe die beste — und
einzige — Quelle. Ein Monatswert wird **nicht** nach unten durchgereicht.

> **Das ist die Umkehrung des heute üblichen Vorgehens** und der eigentliche Inhalt des
> Entscheids. Bisher galt: der Monat gewinnt und schreibt nach unten durch. Künftig gilt: jede
> Ebene nimmt die feinste Quelle, die sie hat.

### P-3 · Die Abweichung wird benannt, nicht beseitigt [E, 17.09.2026]

Sobald ein Monat abgerechnet ist, kann die Summe der slot-scharf gerechneten Tage vom
abgerechneten Monatsbetrag abweichen. **Diese Abweichung ist zulässig.** Sie wird ausgewiesen,
nicht durch Skalieren der Tage beseitigt.

Begründung [F]: Skalieren würde eine Messung verfälschen, um eine Summe zu retten. Die Messung
ist das Wertvollere — sie sagt, *wann* das Geld angefallen ist, und genau das ist der Zweck einer
Tagesansicht bei einem flexiblen Tarif.

⚠ **Die Abweichung muss klein sein, sonst stimmt etwas nicht.** Wird sie groß, ist entweder die
Slot-Erfassung lückenhaft oder der eingetragene Abrechnungswert falsch. Sie ist damit zugleich
eine **Prüfgröße**, nicht nur ein Schönheitsfehler. [F]

> **Wortwahl:** „Abweichung", nicht „Differenz". Im Projekt bezeichnet „Differenz" die Subtraktion
> zweier Größen, die bei ungleicher Abdeckung *unterdrückt* wird
> (`KONZEPT-UNVOLLSTAENDIGE-WERTE.md` §3). Hier ist das Gegenteil gemeint: ein Vergleich zweier
> gültiger Zahlen, der sichtbar bleibt.

### P-3a · Aggregate werden aus Monaten gebildet, nie aus Tagen [F]

Jahr, Lebensdauer, Bericht, Export und steuerliche Größen summieren **Monatswerte**. Die
Tagesebene ist eine **Sicht**, keine Summationsbasis.

Damit ist P-3 eingehegt: Die Abweichung existiert an genau einer Stelle — im Vergleich einer
Tagesreihe mit ihrem Monat — und kann sich nicht in Jahres- oder Lebensdauerzahlen fortpflanzen.
Ohne diese Regel bräche die nächste Jahreskostenlinie, die jemand aus Tagen zeichnet, P-3 leise.

### P-4 · Es wird nie nach unten interpoliert [F]

Ein Monats- oder Tagesmittel darf niemals als Preis einer feineren Ebene ausgegeben werden.
Fehlt bei einem messbaren Tarif die Slot-Reihe, hat der Slot **keinen** Preis — und das ist die
Aussage, die eedc trifft.

**Abgrenzung (T-1):** Bei ableitbaren Tarifen ist der Slot-Preis kein interpolierter Wert,
sondern der vertraglich vereinbarte. Ihn zu verwenden ist keine Verletzung dieser Regel, sondern
ihre Anwendung.

### P-5 · Beide Seiten einer Differenz tragen dieselbe Auflösung [F]

Wo zwei Preise voneinander abgezogen werden — Bezug gegen Einspeisevergütung, Bezug gegen
Ladepreis, Bezug gegen Alternativkosten —, müssen beide auf derselben Zeitebene und mit
derselben Gewichtung gebildet sein. Sonst misst die Differenz nicht den Effekt, sondern den
Unterschied der Auflösungen.

Dies ist die Übertragung der bestehenden Projektregel *„eine Differenz erbt die
Unvollständigkeit jedes Summanden"* von der Erfassungs- auf die **Zeitachse**.

### P-6 · Eine Kaskade je Ebene — und sie gehört einem Zähler [F]

Für eine Ebene und einen Zähler existiert **eine** Auflösungsreihenfolge, die alle Konsumenten
teilen. Zwei Sichten dürfen nicht zwei verschiedene Preise für dieselbe Größe, denselben Zeitraum
und dieselbe Anlage nennen.

| Ebene | Reihenfolge | gilt für |
| --- | --- | --- |
| **Slot** | gemessener Endpreis → Vertragspreis → *kein Wert* | alle Verwendungen an diesem Zähler |
| **Tag** | aus Slot-Ebene gewichtet → *kein Wert* | dito |
| **Monat** | abgerechnet → aus Slot-Ebene gewichtet → Vertragspreis → *kein Wert* | dito |

**„Vertragspreis"** subsumiert dabei die ableitbaren Stufen: Zeitfenster, sonst Arbeitspreis.

**Ein gemessener Endpreis gehört zu dem Zähler, an dem er gemessen wurde.** Er gilt für **jede**
Verwendung hinter diesem Zähler und für **keine** andere. Eine Verwendung mit eigenem Tarif
(Wärmepumpe, Wallbox mit eigenem Zähler) hat eine **eigene Kaskade gleicher Form** mit eigener
Quelle — eigener Preissensor oder eigener Vertragspreis. Wer den Flex-Ø des Hauszählers auf eine
separat belieferte Wärmepumpe anwendet, verrechnet zwei Verträge miteinander.

⚠ **„Kein Wert" ist ein zulässiges Ergebnis** und keine Fehlfunktion. Es ist die einzige ehrliche
Antwort, wenn ein messbarer Tarif ohne Preiserfassung betrieben wird.

### P-7 · Der Stichtag eines Vertragspreises ist der Beginn des Zeitraums, den die Zahl beschreibt [F]

Für einen Slot ist das sein Tag, für einen Monat der Monatserste. Ein Tarifwechsel mitten im
Monat wirkt damit auf der Slot-Ebene **sofort** und auf der Monatsebene erst im Folgemonat.

> **Erweitert ADR-002/P8**, widerspricht ihr nicht: P8 regelt die Monatsebene („ein Tarif ab
> Monatsmitte gilt erst im Folgemonat") und bleibt dort wörtlich gültig. Die Slot-Ebene war dort
> nie geregelt.

### P-8 · Null und negative Preise sind Werte [F]

Eine Kaskade prüft **„vorhanden"**, nie **„größer null"**. Bei dynamischen Tarifen sind
Negativstunden Alltag; eine Prüfung auf `> 0` wirft genau die interessantesten Slots weg und
fällt für sie auf eine gröbere Quelle zurück — also auf einen zu hohen Preis, ausgerechnet dort,
wo der echte null oder negativ war.

---

## 6. Was daraus für die einzelnen Größen folgt

**Netzbezugskosten.** Auf Slot- und Tagesebene aus Slot-Preis × Slot-Menge (A-3); auf Monatsebene
aus dem abgerechneten Preis, solange einer vorliegt, sonst aus derselben Slot-Reihe. [F]

**Eigenverbrauchs-Ersparnis.** Der vermiedene Bezug wird mit dem Preis **des Slots bewertet, in
dem er vermieden wurde**, gewichtet mit der vermiedenen Menge (A-2). Nach P-1 gibt es für diese
Größe **auch auf Monatsebene keine Abrechnung** — der abgerechnete Bezugs-Ø ist dort nur der
Rückfall, nicht die bessere Quelle. [F]

**Einspeiseseite — symmetrisch.** Dieselben Regeln gelten für Erlöse: fester Vertragspreis,
gepflegter Monatswert bei variabler Vergütung, und bei Direktvermarktung slot-scharf. **§51 EEG
ist eine Slot-Regel:** der Erlös eines Slots mit negativem Preis ist null. [F]

**Speicher-Arbitrage.** Der Gewinn ist definitionsgemäß eine Differenz zwischen zwei Zeitpunkten
— er existiert nur, weil Preise schwanken. Nach P-5 müssen **beide** Seiten slot-scharf sein: die
Ladung mit dem Preis der Ladeslots, die Entladung mit dem vermiedenen Preis der Entladeslots. Ein
Mittelwert auf einer der beiden Seiten macht den Gewinn unbrauchbar. [F]

Der Speicherwirkungsgrad gehört an die **Menge**, nicht an den Spread: bezahlt wurde die volle
eingespeicherte Energie, nutzbar ist nur der Teil nach Verlusten. [F]

**Zeitunabhängige Beträge.** Grundpreis und Zählergebühr haben **keine** Slot-Ebene. Sie
erscheinen auf der Ebene ihrer Periode und wandern nie in einen kWh-Preis. [F]

**Steuern und Umlagen.** Ein Endpreis ist vollständig; Bestandteile mit eigenem Stichtag werden
nicht separat auf Slots verteilt. [F]

**Aussagen über die Zukunft** (Prognose, Aussichten). Hier gibt es keine Messung — es gilt der
Vertragspreis bzw. ein gepflegter Erwartungswert, und die Zahl ist als Erwartung zu beschriften.
Eine Prognose darf nie aussehen wie eine Messung. [F]

⭐ **Für einen dynamischen Tarif gibt es keinen Vertragspreis je Stunde — und genau deshalb einen
abgeleiteten Erwartungswert** (Abnahme Gernot, 22.09.2026). Er entsteht als
`(1 + USt) × Börsenpreis + Aufschlag`, und der **Aufschlag** kommt aus einer Kaskade, die das
Spiegelbild der Vergangenheits-Kaskade ist (gemessen › abgerechnet › Vertrag):

1. **Abrechnung** — der letzte abgerechnete Monat **im laufenden Tarifzeitraum**: sein
   Durchschnittspreis minus dem verbrauchsgewichteten Börsenmittel desselben Monats. Gewichtet,
   weil der Monats-Ø selbst gewichtet ist (A-1: keine arithmetischen Mittel über Preise).
2. **Gemessene Stunden** — der Median über `Endpreis_h − (1 + USt) × Börse_h` der letzten sieben
   Tage, mindestens 24 Paare. Median statt Mittel aus demselben Grund wie A-1.
3. **Keiner** — dann bleibt der **nackte Börsenpreis** stehen, und zwar ausdrücklich beschriftet
   (`preisquelle: boersenpreis`, `aufschlag_quelle: keiner`). Das ist die einzige nach **T-1**
   zulässige Form, einen Börsenpreis in Endpreis-Position zu zeigen.

**Es gibt dafür kein Pflegefeld.** Das Verfahren braucht kein Tarifmodell, nur die Annahme „Börse
plus ein über den Zeitraum konstanter Anteil"; ein Deckel- oder Staffeltarif bekommt darunter einen
Durchschnitt, und `aufschlag_basis` sagt, worauf er beruht. Ein manuelles Feld wird nachgereicht,
wenn ein Anwender es braucht.

⚠ **Die Grenze nach P-5:** Aus einer Näherung wird **kein** Eigenverbrauchs-Wert gebildet. „Nackter
Börsenpreis minus Vertragsvergütung" wäre keine gröbere Näherung, sondern eine Differenz aus zwei
verschiedenen Preisebenen — und damit eine Zahl ohne Bedeutung. Fehlt der Aufschlag, fehlt der Wert,
und der Grund steht daneben.

---

## 7. Herkunft und Beschriftung

**H-1 — Jede angezeigte Preiszahl nennt ihre Auflösung und ihre Quelle.** [F]
„31,5 ct" allein ist keine Aussage. „31,5 ct — Arbeitspreis deines Tarifs" und „35,6 ct — Ø deiner
gemessenen Slot-Preise (68 % des Bezugs)" sind zwei verschiedene Aussagen, und der Anwender muss
sie unterscheiden können.

**H-2 — Die Beschriftung beschreibt die Zahl daneben.** [F]
Eine Formelzeile, die „gemessen" sagt, während die Kachel den Vertragspreis zeigt, ist schlimmer
als gar keine Beschriftung: Sie erzeugt Vertrauen in eine falsche Zuordnung.

**H-2a — Ein Preis nennt auch, aus welcher *Ableitung* er stammt, nicht nur aus welcher Quelle.** [F]
Zwei Zahlen können beide „aus dem Tarif" kommen und doch verschieden entstanden sein: der
Arbeitspreis einer Festpreis-Zeile ist **exakt**, der Endpreis eines dynamischen Tarifs ist
**gerechnet**. Die Sensoren tragen dafür `preisquelle` (`vertrag` · `zeitfenster` ·
`boerse_plus_aufschlag` · `boersenpreis` · `keine`) und, wo ein Aufschlag im Spiel ist,
`aufschlag_quelle` samt `aufschlag_basis`. Dieselbe Unterscheidung beim Speicher-Wirkungsgrad
(`wirkungsgrad_quelle` `gemessen`/`parameter` **und** `wirkungsgrad_messung` mit dem Grund, falls
die Messung nicht ging) — ein Rückfall auf einen gepflegten Wert ist nach §8 keine stille Ersetzung,
solange er sich nennt.

**H-3 — Abdeckung wird mitgeliefert, nicht als Schwelle verwendet.** [F]
Eine Mindestschwelle, unterhalb derer auf eine gröbere Quelle zurückgefallen wird, verwirft die
bessere Information genau dann, wenn sie am nötigsten ist — im laufenden Monat, der naturgemäß
erst teilweise abgedeckt ist.

---

## 8. Was eedc ausdrücklich nicht tut

- **Keinen Börsenpreis als Endpreis** ausgeben. Er darf die Form liefern, nicht den Betrag.
- **Nicht nach unten interpolieren** (P-4).
- **Keine arithmetischen Mittel** über Preise (A-1).
- **Kein Ø × Gesamtmenge** statt Σ Slot-Kosten (A-3).
- **Keine stille Ersetzung**: Wo die feinere Quelle fehlt, steht „kein Wert" samt Grund.
- **Keine Schwelle**, die eine vorhandene Messung verwirft (H-3).
- **Keine Prüfung auf `> 0`** in einer Preis-Kaskade (P-8).
- **Keinen zweiten Wahrheitsort**: Preise werden nicht mehrfach unabhängig gebildet (P-6).

---

## 9. Annahmen und offene Punkte

**[A-1] Ist der gepflegte Monatswert die Abrechnung?** Das Feld „Ø Strompreis" wird als
abgerechneter Wert behandelt und schlägt deshalb die Messung. Tatsächlich nimmt es auch einen
übernommenen Vorschlag oder eine Schätzung auf — dann schlägt eine Messung sich selbst.
*Zu entscheiden: bleibt es ein Feld, oder trennt eedc „abgerechnet" von „geschätzt"?*

**[A-2] — ENTSCHIEDEN [E, 17.09.2026]: Beim Ladepreis schlägt die Messung den gepflegten Wert.**
Anders als beim Netzbezug gibt es hier **keine externe Wahrheit** — ein Ladepreis steht auf keiner
Rechnung; der gepflegte Wert ist entweder der übernommene Vorschlag (also die Messung) oder eine
Schätzung. „Gepflegt" bleibt als **bewusste Korrektur** erhalten und trägt eine eigene Herkunft,
schlägt aber die slot-scharfe Messung nicht mehr. Folgt zugleich aus P-1 in der geschärften
Fassung: Die Bezugsabrechnung sagt nichts über die Speicherladung.

> ⚠ **Damit ist die Kaskade des Ladepreises nicht die des Netzbezugs.** Die Reihenfolge in P-6
> gilt für Größen **mit** Abrechnung. Für den Ladepreis lautet sie: gemessen → gepflegt
> (Korrektur) → *kein Wert*. Wer beide Kaskaden gleichsetzt, baut den Fehler wieder ein.

**[A-3] Ab welcher Größe meldet eedc die P-3-Abweichung?** Dass sie klein sein *muss*, folgt aus
der Sache; die Schwelle braucht eine Messung an echten Daten, keine gesetzte Zahl.

**[A-4] Rückwirkung und Kommunikation.** Trägt ein Anwender den abgerechneten Ø nachträglich ein,
ändert sich der Monatsbetrag, die Tage bleiben. ⚠ **Dazu gehört eine Korrektur nach außen:** Die
Antwort an OB73 vom 15.09. sagt, der gepflegte Ø gelte „rückwirkend für alle Tage des Monats" —
P-2 hebt das auf. Die Korrektur geht mit dem Bau hinaus, nicht vorher.

**[A-5] Viertelstunden-Slots.** Dass der Day-Ahead-Markt seit 2025 viertelstündlich rechnet, ist
Fachkunde, nicht von uns gemessen. Die Slot-Formulierung (§2) macht das Konzept davon unabhängig;
der Zeitpunkt einer Umstellung ist offen.

---

## 10. Die zwei Prüfsteine

Ein Konzept, das nur die bekannten Fälle trifft, ist eine Fallsammlung. Diese beiden Fälle kommen
in keiner Meldung vor:

> **Prüfstein 1 — der ungepflegte Flex-Anwender.** Eine Anlage mit dynamischem Tarif, Speicher und
> Wärmepumpe, deren Anwender den Monat **nie** abschließt. Nach P-2 bekommt sie auf Slot- und
> Tagesebene durchgehend gemessene Preise, auf Monatsebene den gewichteten Ø derselben Reihe — und
> damit in *allen* Sichten dieselbe Zahl, ohne dass ein einziges Feld gepflegt wurde.

> **Prüfstein 2 — die Regression.** Eine Anlage mit **Festpreis** und Speicher: Alle Regeln
> liefern je Slot denselben Preis, und **keine Zahl bewegt sich gegenüber heute.** Das ist der
> Beweis, dass das Konzept nur dort etwas ändert, wo es etwas ändern soll.

⚠ Dazu ein dritter Fall, der beim **Bau** zu prüfen ist, nicht am Konzept: der Tag der
Zeitumstellung. Gewichtete Mittel sind gegen 23 und 25 Slots robust; eine Datenstruktur, die
Slots je Tag fest indiziert, ist es nicht.

---

## 11. Arbeitsliste — Differenz zum Ist-Zustand

Gemessen am Code (17.09.2026). **Bereits SOLL-konform und nicht anzufassen:** die Monats-Kaskade
`aufgeloester_monatspreis` (keine Schwelle, Herkunft, mengengewichtet) · die Zeitfenster-Auflösung
`preis_je_slot` · `berechne_effektiver_ladepreis` (slot-scharf, korrekt gewichtet, Quelle
benannt, Börsenpreis nur als Form) · §51 stundenscharf · der Vorschlag im Monatsabschluss · alle
Aggregat-Sichten summieren bereits Monate (P-3a gilt faktisch schon).

| Paket | Inhalt | Regeln | Stand |
| --- | --- | --- | --- |
| **F1** | Monatskachel liest den Kaskadenwert statt des Tarif-Felds | H-2 | ✅ **gebaut** (`85bbac6d`) |
| **F2** | **Tagesebene = Messung** (der Entscheid): Tageskosten aus Slot-Kosten statt Monatspreis × Tagesmenge; Ø, Herkunft und Abdeckung in der Antwort; Formeltexte | P-2, P-4, A-3, H-1/H-3 | ✅ **gebaut** (`85bbac6d`) |
| **F3a** | Speicher-Ladeseite: eine Kette, Monats-Ø-Rückfall weg, `> 0` → `vorhanden`, η an die Menge | P-1, P-6, P-8, §6 | ✅ **gebaut** (`85bbac6d`) |
| **F3b** | Speicher-**Nutzenseite** slot-scharf, für **beide** Anteile | P-5 | ✅ **gebaut** (`a45d0079`) |
| **F4** | EV-Ersparnis mit der vermiedenen Menge gewichtet | A-2, P-1 | ✅ **gebaut** (`a5b7241e`) |
| **F5** | P-3-Abweichung als Prüfgröße im Daten-Checker | P-3, [A-3] | ⛔ **verworfen** (17.09.2026) — s. u. |
| **F6** | „Slot" statt „Stunde" im Code; Prognose-Beschriftung | §2, §6 | ⛔ **verworfen** (17.09.2026) — s. u. |
| **F7** | Recorder-Datei wird auf Lesbarkeit geprüft, statt den WebSocket-Weg zu blockieren | — (Transport, nicht Preis) | ✅ **gebaut** |

> ⭐ **Die korrigierenden Pakete sind vollständig.** F1–F4 beheben je eine Stelle, an der eedc
> eine **falsche Zahl** zeigte oder rechnete. Was offen bleibt, fügt hinzu: F5 eine neue Warnung,
> F6 eine Umbenennung. Keines von beiden korrigiert einen Wert.
>
> ### ⛔ F6 ist verworfen, nicht vertagt (Entscheid Gernot, 17.09.2026)
>
> Der Gedanke dahinter steht in §2 und er ist richtig: *„Wer ‚Stunde' in eine Regel schreibt,
> baut sie zweimal."* Der Day-Ahead-Markt rechnet seit 2025 viertelstündlich, §14a arbeitet
> ebenfalls feiner als stündlich.
>
> **Trotzdem nicht gebaut, und zwar aus dem Grund, der die Regel selbst schützt:** F6 ändert
> **kein Verhalten und keine Zahl** — es benennt Variablen um. Der Nutzen entsteht erst bei der
> tatsächlichen Umstellung auf 15-Minuten-Slots, und die ist in **[A-5]** ausdrücklich offen.
> Kommt sie, fasst sie ohnehin jede betroffene Stelle an; die Umbenennung ist dann Teil der
> Arbeit und kostet fast nichts. Heute ist sie eine breite Änderung ohne Wirkung — mit dem
> Flüchtigkeitsrisiko, das jede breite Umbenennung hat.
>
> ⭐ **Was dabei NICHT verloren geht:** Das Konzept ist bereits slot-neutral formuliert. Der
> Schutz, um den es §2 geht, wirkt also schon — nur im Code stehen noch die alten Namen.
>
> **Nicht neu aufrollen.** Wer es doch will, bringt die Entscheidung über die Slot-Länge mit,
> nicht das Argument der Lesbarkeit.

> ### ⛔ F5 ist verworfen, nicht vertagt (17.09.2026)
>
> Die Idee war, eedc melden zu lassen, wenn die Summe der Tageskosten stark vom abgerechneten
> Monatsbetrag abweicht — als Hinweis auf eine lückenhafte Erfassung oder einen falsch
> eingetragenen Abrechnungswert. **Beide Hälften sind bereits gedeckt, und zwar besser:**
>
> * **Lückenhafte Erfassung** — die **Abdeckung steht schon neben jedem Wert** (H-3), als Anteil
>   der bewerteten Menge. Eine zweite Meldung über denselben Sachverhalt ist genau der „zweite
>   Turm", den der Daten-Checker in seinen eigenen Docstrings ablehnt.
> * **Falscher Abrechnungswert** — der Monatsabschluss **schlägt den gemessenen Ø bereits vor**
>   (`vorschlag_service`, Konfidenz 90). Wer einen stark abweichenden Wert einträgt, hat den
>   Vorschlag gesehen und bewusst überschrieben. Ihn danach zu ermahnen, wäre Bevormundung —
>   *eedc ist nicht die Strom-Polizei.*
>
> Dazu kam **[A-3]**: Eine feste Prozent-Schwelle wäre eine erfundene Zahl gewesen, und die
> selbstkalibrierende Fassung hätte einen Mechanismus gebaut, um einen Sachverhalt zu melden,
> den zwei vorhandene Stellen schon zeigen.
>
> **Nicht neu aufrollen.** Wer es doch will, bringt einen Anwender mit, den die vorhandene
> Abdeckungs-Angabe und der Abschluss-Vorschlag nachweislich nicht erreicht haben.


## 12. Prüfung gegen den gebauten Stand (18.09.2026, Auftrag Gernot: „erneut prüfen, analysieren, Notwendigkeiten einwerten")

**Kern gebaut und am Code belegt:** T-1, A-1/A-3 (Slot/Tag/Monat), P-2, P-4, P-5, P-8, P-3a, §6 (Netzbezug, Speicher-Arbitrage beidseitig, η an
der Menge, Grundpreis ohne Slot), H-2, H-3 (keine Schwelle); F1 `85bbac6d` · F2 `85bbac6d` · F3a/b `85bbac6d`/`a45d0079` · F4 `a5b7241e` (Tag) ·
F7 `72cfe80e`; F5/F6 verworfen (§11). Prüfstein 2 als Probe (`test_slot_kosten_tagesebene.py`). **P-7 auf Slot-Ebene bewusst nicht gebaut**
(`tage_werte.py:210-217`, Einhängestelle vorbereitet) — gehört als benannte Grenze ins Konzept.

**Heute erledigt (18.09., `7caffbca`):** A-4 — Aufhebungs-Vermerk am alten Satz in `docs/WAS-IST-NEU.md` (v4.0.44) und `CHANGELOG.md` [4.0.44];
die Antwort an OB73 (#412) trug die Korrektur schon am 17.09. · dritter Prüffall Zeitumstellung — zwei Proben (23 Slots März, 24 speicherbare
Slots Oktober; Grenze: die 25. Stunde ist im Datenmodell nicht speicherbar, `UniqueConstraint(datum, stunde)`).

**Zwei Befunde, die im SOLL nicht standen — beide erzeugen einen falschen Wert, Entscheid Gernot mit Empfehlung „bauen":**
* **(a) EV-Ersparnis nur am Tag A-2-konform.** `ev_preis_cent` wird allein in `tage_werte.py:362` gesetzt; Monat, Jahr, Netto-Ertrag, PDF und
  HA-Export laufen über `finanz_aggregat.py:168` und bewerten die vermiedene Menge mit dem **bezugsgewichteten** Ø — nach der eigenen Probe des
  Bau-Commits systematisch zu hoch (`test_ev_ersparnis_slot_gewichtet.py:79`: 0,30 € statt 1,50 € an einem Tag). Dazu P-1: der abgerechnete Bezugs-Ø
  hat dort Vorrang, obwohl §6 ihn für diese Größe zum Rückfall erklärt ⇒ zwei Sichten derselben Anlage widersprechen sich (P-6-Klasse).
  **Bauweg F4b:** den EV-Ø je Monat aus derselben Slot-Abfrage bilden und in `FinanzZeileEingabe` durchreichen; Rechenseite existiert.
* **(b) „Ø Netzpreis" in Auswertungen → Tabelle ist ein arithmetisches Mittel über Monate** (`lib/werte/registry.ts:125` `aggregation: 'avg'`,
  `aggregate.ts:24`) — §8 verbietet das wörtlich. Entschärfend: `defaultVisible: false`, nur Monats-Granularität. **Bauweg:** Fuß mengengewichtet aus
  `netzbezug_kosten ÷ netzbezug` oder Fußzelle leer wie bei der Grundlast (Muster in `registry.ts` vorhanden).

**Einwertung der offenen Punkte (Empfehlung je Zeile, Entscheid Gernot):**

| Punkt | Zustand am Code | Notwendigkeit | Empfehlung |
| --- | --- | --- | --- |
| **A-1** ein Feld „Ø Strompreis" oder abgerechnet/geschätzt trennen | ein Feld (`monatsdaten.py:70`), seit `9fa84473` normativ beschriftet „dein **abgerechneter** Ø … schlägt jede Berechnung" | gering — der Vorschlag aus dem Abschluss ist derselbe gewichtete Ø wie Stufe 2, kein falscher Wert | **archivieren** (Textlösung vom 11.09. trägt) |
| **A-3** Schwelle der P-3-Abweichung | keine Meldung, keine Schwelle (konsistent mit F5 verworfen); die Abweichung ist aber **nirgends benannt** — Σ-Zeile der Tages-Tabelle addiert stumm neben dem Monatsbetrag | Meldung: keine · Benennung: ein Satz | **Schwelle archivieren, einen Fußnotensatz unter der Tabelle bauen** („Tage sind gemessen, der Monat ist abgerechnet — die Summe kann abweichen"; gehört zu H-1/H-2) |
| **A-5** Viertelstunden-Slots | Preis-Code slot-neutral (`strompreis_aggregator.py:377-433`); die 24er-Bindung sitzt im Datenmodell (`tages_energie_profil.py:37-48`) und ~40 Profil-/Prognose-Stellen | heute keine, Auslöser extern (Zulieferer mit 15-Minuten-Endpreisen) | **archivieren als Annahme**, Klausel wie F6: wer aufrollt, bringt die Slot-Länge mit |
| **P-6** „eine Kaskade gehört einem Zähler" | `monats_fakten/tarif.py::_lade_tarif` wendet den Hauszähler-Flex-Ø bewusst auf den Wallbox-Tarif an (Konsistenz im `TarifFakten`) | Regel und Code sagen Verschiedenes; ohne zählerscharfe Tarifzuordnung ist der Code vertretbar | **SOLL-Satz präzisieren** („gilt erst mit eigenem Zähler"), Code lassen |
| Nebenkante `sollstunden = tage_im_monat * 24` (`:121`, `:236`) | Abdeckung im Oktober 100,1 %, im März max. 99,87 %, Anzeige ohne Nachkommastelle | niemand sieht es | **archivieren** |
| Monats-Abdeckung ist ein **Slot**-Anteil (`:61-63`, `MonatBilanz.tsx:198`); A-1-Zusatz verlangt den Mengen-Anteil (Tagesebene rechnet ihn, `:288-298`, ohne Leser) | Beschriftung „% der Monatsstunden" ist ehrlich | klein | als benannte Grenze ins Konzept; Umstellung nur mit (a) |

**Kann das SOLL als „abgenommen und gebaut" gelten?** Noch nicht: (a) und (b) offen, dazu die Archiv-Vermerke für A-1/A-3-Schwelle/A-5/P-6. Danach wird
daraus `docs/KONZEPT-FLEX-TARIFE.md`, mit P-7 (Slot-Ebene) und der Slot-Abdeckung als benannten Grenzen.


### Entscheide Gernot, 18.09.2026 (zweite Runde: „Flex komplett bauen")

| Punkt | Entscheid | Umsetzung |
| --- | --- | --- |
| **(a)** EV-Ersparnis Monat/Jahr bezugsgewichtet | **gebaut** | `MonatsPreis.ev_cent` aus derselben Messung (`StrompreisAggregat.ev_gewichtet_cent`, Einzelmonat und gebündelt), `baue_finanz_zeile` reicht ihn an alle sieben Aufrufer durch; P-1 gilt: gepflegter Bezugs-Ø ist für die Ersparnis nur Rückfall. Proben `test_ev_ersparnis_monat_gewichtet.py`, Symmetrie um das fünfte Feld erweitert |
| **(b)** „Ø Netzpreis" arithmetisch in der Tabelle | **gebaut** | Fuß-Aggregation `gewichtet` (Gewicht Netzbezug) in `lib/werte`; Börsenpreis Ø bleibt `avg` als **benannte Ausnahme** (zeitgewichteter Marktwert, kein bezahlter Preis) |
| **A-3** Schwelle | **archiviert**; Satz gebaut | Fußnote unter der Tages-Tabelle: „Tage sind gemessen, der Monat ist abgerechnet — die Summe der Tage kann vom Monatsbetrag abweichen." Keine Schwelle, kein Checker (P-3: benennen, nicht beseitigen) |
| **A-1** ein Feld „Ø Strompreis" | **archiviert** | Textlösung vom 11.09. trägt („dein abgerechneter Ø … schlägt jede Berechnung"); der Vorschlag aus dem Abschluss ist derselbe gewichtete Ø wie Stufe 2 — kein falscher Wert |
| **A-5** Viertelstunden-Slots | **archiviert als Annahme** | Preis-Code slot-neutral; die 24er-Bindung sitzt im Datenmodell (`tages_energie_profil.py:37-48`). Wer es aufrollt, bringt die Slot-Länge mit (Klausel wie F6) |
| **P-6** „eine Kaskade gehört einem Zähler" | **SOLL-Satz präzisiert** | gilt erst, wenn eedc einen eigenen Zähler je Komponente modelliert; bis dahin wendet `monats_fakten/` den Hauszähler-Flex-Ø bewusst auch auf den Wallbox-Tarif an (Konsistenz im `TarifFakten`) |
| Nebenkante `sollstunden = tage_im_monat * 24` | **archiviert** | Abdeckung 100,1 % im Oktober, max. 99,87 % im März — ohne Nachkommastelle unsichtbar |
| Monats-Abdeckung als Slot-Anteil | **benannte Grenze** | `MonatBilanz.tsx` sagt „% der Monatsstunden"; der Mengen-Anteil existiert auf der Tagesebene (`SlotKosten.abdeckung_menge`) ohne Leser |
| **P-7** auf Slot-Ebene | **benannte Grenze** | ein Tarifwechsel zur Monatsmitte wirkt in den Slot-Kosten erst im Folgemonat (`tage_werte.py:210-217`); Einhängestelle vorbereitet |
