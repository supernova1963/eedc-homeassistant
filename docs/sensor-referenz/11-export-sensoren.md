## 11. Export-Sensoren (eedc → HA)

Die bisherigen Abschnitte beschreiben Sensoren, die eedc **aus HA liest**. Dieser Abschnitt beschreibt die umgekehrte Richtung: berechnete eedc-Werte, die als **HA-Entitäten** bereitgestellt werden — per MQTT Discovery (empfohlen) oder REST. Einrichtung: [Einstellungen → Integration → MQTT-Export](HANDBUCH_EINSTELLUNGEN.md#63-mqtt-export).

> **Nicht alles muss kommen.** Jeder Sensor dieser Liste lässt sich in eedc **abwählen** — Häkchen weg in der Sensorliste unter [Einstellungen → Integration → MQTT-Export](HANDBUCH_EINSTELLUNGEN.md#63-mqtt-export), einzeln oder kategorieweise. Bei einer **Neuinstallation** sind alle an; abgewählt wird bewusst, und eedc fragt vorher nach, weil die bisherigen Daten des Sensors in HA und auf dem Broker damit verloren sind. ⭐ **Kommen mit einem Update neue Sensoren dazu, starten sie bei einer bestehenden Installation abgewählt** — sie tragen in der Liste die Markierung **„Neu"**, und du hakst an, was du haben willst (ein Knopf nimmt alle auf einmal). Dabei geht nichts verloren: sie waren nie in Home Assistant. Der Grund für diese Voreinstellung: Ein Sensor, den es nicht gibt, zeichnet nichts auf — und Home Assistant kennt keine Zeitmaschine. Wer einen Wert später braucht, bekäme ihn erst ab dem Einschalten.

> **Zeithorizont:** Sofern nicht anders angegeben, beziehen sich die Werte auf die **Gesamtlaufzeit** (alle erfassten Monate, jeweils ab Anschaffungsdatum der Komponenten). Der laufende Monat fließt erst nach dem Monatsabschluss ein. Einzige Ausnahme: der **Spezifische Ertrag** ist aufs Jahr normiert (siehe unten).

> **Nachkommastellen — gleich für MQTT und REST:** Wie viele Nachkommastellen ein Export-Wert trägt, hängt an seiner **Größenart**, nicht am Export-Weg: Energie und Mengen (kWh, kWh/kWp, km, kg) **ganzzahlig**, Geld auf **2** Stellen, Prozent auf **1**, Leistung (kW) auf **2**, Stunden/Jahre auf **1**, übrige Kennwerte (COP, Zyklen, Rang) auf **2**. **Eine Ausnahme: die PV-Prognose-Sensoren tragen eine Nachkommastelle** — sie nennen eine Tagesmenge (0–60 kWh) und keinen Zählerstand, und ihre Zahlen sollen sich addieren lassen: *Rest heute* plus das bereits Erzeugte ergibt *heute (nachgeführt)*. Auf ganze Zahlen gerundet ging diese Summe sichtbar nicht mehr auf. Ein kleiner, aber echter Wert wird dabei **nie auf 0 gerundet** — er bekommt so viele Stellen wie nötig (höchstens 3), damit aus 0,35 kW keine 0 wird. Sensor-Namen, Einheiten und die Anzahl der Entitäten sind unverändert; die HA-Historie zeigt für zurückliegende Zeitpunkte weiter die alten Werte.
>
> Ab v4.0.6 galt diese Regel zunächst nur für MQTT; der REST-Weg lieferte für dieselbe Größe eine andere Zahl (kWh mit einer Nachkommastelle). **Seit v4.0.7 sagen beide Wege dasselbe.** Wer eedc-Sensoren über die `rest`-Plattform eingebunden hat, sieht dort einmalig kürzere Werte — 39.692,4 kWh wird zu 39.692 kWh. Der Vollzyklen-Sensor geht den umgekehrten Weg (380 → 380,19): er ist eine dimensionslose Kennzahl und trägt jetzt dieselben zwei Stellen wie die Speicher-Anzeige in eedc.

### Anlage-weite Sensoren

<!-- erzeugt: export-sensoren kategorie=energie,quote,anlage,finanzen,umwelt,investition,speicher,status,e_auto -->

Zusätzlich erscheinen **pro Komponente** (E-Auto, Wärmepumpe, Speicher, Wallbox …) eigene Sensoren (z. B. `e_auto_pv_anteil_prozent`, `wp_cop_durchschnitt`, `wp_betriebsstunden`). Sie hängen — wie alle eedc-Sensoren — **unter dem einen Gerät deiner Anlage**; der Gerätename steht im Sensornamen (*„Daikin3 ECH₂O COP Durchschnitt"*).

> **E-Auto: `e_auto_verbrauch_kwh_100km` und `e_auto_pv_anteil_prozent`.** Der Verbrauch je 100 km folgt derselben Regel wie die App: je Monat der gemessene Fahrverbrauch (Feld „Verbrauch"), sonst die Ladung (Heim + Extern); über den Zeitraum die **Summe der Monatswerte geteilt durch die Summe der Kilometer** dieser Monate. Das Attribut **`quelle`** sagt `gemessen` (jeder Monat mit Kilometern hat einen Fahrverbrauch) oder `ladung` (Näherung über die Ladung, inkl. Ladeverluste). Bis v4.0.50 war der Sensor meist leer, weil eedc den erfassten Fahrverbrauch beim Start in eine Ladung umbuchte — er erscheint jetzt neu. Der **PV-Anteil** bezieht sich auf die **Heimladung** (PV + Netz), nicht auf „Ladung gesamt" mit Extern.
>
> **E-Auto: `e_auto_ersparnis_vs_benzin_euro`.** Die Ersparnis gegenüber dem Verbrenner zieht die **externen Ladekosten** ab — nach derselben Regel wie der E-Auto-Hub: steht die externe Ladung am Wallbox-Topf und am Auto, zählt das Paar mit den höheren Kosten. Sensor und Hub nennen damit für denselben Zeitraum dieselbe Zahl. ⚠ **Bis v4.0.50 blieb das Laden unterwegs im Sensor unberücksichtigt**: wer externe Ladung pflegt, sieht ihn — und über den E-Auto-Posten `jahres_ersparnis_euro`, `roi_prozent`, `amortisation_jahre` — einmalig sinken bzw. die Amortisation länger werden; in der Langzeitstatistik ist das ein Sprung an einem Tag, es gehen keine Daten verloren.

> ⛔ **Hier stand bis August 2026 „jeweils unter einem eigenen HA-Gerät", und genau so war es mit v4.0.30 auch gebaut.** Zwei Anwender haben innerhalb von 24 Stunden gemeldet, dass das Ergebnis schlechter ist: Bei einer PV-Anlage mit mehreren Modulflächen, Wechselrichter und Speicher entstehen so **etliche HA-Geräte mit je einer einzigen Entität** — zusätzlich zum Gerät der Integration. Seit **v4.0.32** gibt es wieder **ein** Gerät je Anlage.
>
> ⭐ **Für bestehende Installationen ändert sich nichts an den Daten:** `unique_id` und Topic hängen an der Komponente, nicht am Gerät. Home Assistant erkennt dieselben Entitäten wieder und hängt sie lediglich um — `entity_id`, Langzeitstatistik und Automationen bleiben erhalten, der angezeigte Name ebenfalls (HA setzt ihn aus Gerät + Sensor zusammen). ⚠ Die alten, jetzt leeren Geräte entfernt HA beim nächsten Neustart; sonst lassen sie sich einmalig von Hand löschen.

### Steuerungshilfen — die Gruppe für Automationen (neu)

Stufe 1 der Sensorliste sagt, **was ist**. Diese Gruppe sagt, **was jetzt gilt** und **wann es gilt** — die zwei Fragen, die eine Automation stellt. Alle Sensoren hier sind anlagenweit; die Geräte-Stücke stehen weiter unten.

⛔ **Sie sind Vorschläge, keine Anweisungen.** eedc schaltet nichts, ruft keinen Dienst auf und schreibt nichts nach Home Assistant. Es nennt ein Fenster und einen Betrag; was daraus folgt, entscheidest du.

<!-- erzeugt: export-sensoren kategorie=steuerung komponente=sensor -->

> **An Tagen aus dem HA-Spiegel bzw. den eigenen Zählerständen** (seit S5a) kommen `eedc_ueberschuss_heute_kwh` und
> `eedc_ueberschuss_jetzt_kw` sowie das Stundenmittel von `eedc_netzbezug_spitze_heute_kw` aus denselben Stunden wie
> *Cockpit → Tag* — der Überschuss heute ist dort Σ der Stunden aus dem Spiegel, „letzte Stunde" die letzte Stunde, für
> die Home Assistant schon einen Wert hat. Die Zeitangaben (`seit`, `stunde_von`/`stunde_bis`, `stand`,
> `stunde_max_mittel`) stehen dann im Kalendertag (Stunde „11–12" = 11:00 bis 12:00), wie die Stundenansicht. Die
> Netzbezugs-Spitze selbst (Leistung) bleibt die gemessene Spitze des Tages. Eine Stunde, die Home Assistant mit der
> Menge mehrerer Stunden nachliefert, zählt für „jetzt" nicht (sie ist kein Stundenmittel); ihre Energie steht im
> Überschuss heute.

**Die Schalter (`binary_sensor`) — an, aus oder nicht verfügbar**

<!-- erzeugt: export-sensoren kategorie=steuerung komponente=binary_sensor -->

> **Warum „Abregelung heute" in der Skala der Rohprognose steht.** Der Wert ist die Differenz zwischen dem, was deine Module könnten, und dem, was der Wechselrichter durchlässt — und diese Kappung rechnet eedc auf der **ungefilterten** OpenMeteo-Prognose, **bevor** der gelernte Korrekturfaktor deiner Anlage darauf angewendet wird. Das Attribut `skala: openmeteo_roh_vor_korrektur` sagt es ausdrücklich.
>
> ⭐ **Den Verlust mitzukorrigieren wäre falsch, nicht nur ungenau.** Kappung ist `max(0, Leistung − Grenze)` — sie skaliert nicht mit einem Faktor. Eine Anlage, deren Rohprognose die Grenze um 1 kW überschreitet, hat bei einem Korrekturfaktor von 0,8 nicht 0,8 kW Verlust, sondern unter Umständen **gar keinen**: das korrigierte Profil liegt dann komplett unter der Grenze. Eine „korrigierte Abregelung" wäre eine Zahl, die niemand gerechnet hat.
>
> **Was du damit anfangen kannst:** die Größenordnung und die **Uhrzeiten**. `stundenprofil_kwh` zeigt, in welchen Stunden gekappt wird — das sind die Stunden, in denen sich eine verschiebbare Last am meisten lohnt, weil ihr Strom sonst gar nicht erst entsteht. `grenzen_kw` nennt die Grenzen, an denen gekappt wird, `rest_heute_kwh` den noch bevorstehenden Teil.

> **Warum die Ampel „Prognose-Abweichung auffällig" heißt und nicht „Anlage defekt".** eedc sieht Verschattung, Schnee auf den Modulen, einen ausgefallenen Sensor und einen echten Defekt als **dieselbe Zahl**. Ein Urteil wäre eine Behauptung über eine Ursache, die eedc nicht kennt. Die Schwelle ist außerdem **anlagenspezifisch**: Sie hängt am mittleren Fehler *deiner* Anlage der letzten 30 Tage — eine Anlage mit 8 % Streuung schlägt bei 16 % an, eine mit 25 % erst bei 50 %. Ein fester Prozentwert hätte je nach Anlage entweder dauernd oder nie ausgelöst. **Ohne Genauigkeits-Tracking gibt es die Ampel nicht.**

### Was ein `binary_sensor` in eedc ist — und was er nicht kann

Bis September 2026 hat eedc genau **eine** Sorte HA-Entität angelegt: `sensor`. Mit den Steuerungshilfen kommt eine zweite dazu, der `binary_sensor` — er kennt zwei Zustände, `ON` und `OFF`, und keine Einheit, keine Langzeitstatistik über Zahlenwerte.

⚠ **Er kennt kein „unbekannt" — deshalb wird er *nicht verfügbar*.** Verliert ein `binary_sensor` seine Grundlage (der Preis-Abruf fällt aus, das Tagesprofil bricht ab), gibt es keinen dritten Zustand, den eedc schreiben könnte: Home Assistant protokolliert jeden anderen Wert als Fehler. eedc meldet die Entität stattdessen über einen eigenen Verfügbarkeits-Kanal als **nicht verfügbar** (`unavailable` in HA) und schreibt **keinen** Zustand.

⭐ **Warum das wichtiger ist, als es klingt.** Bliebe stattdessen einfach der letzte Zustand stehen, bekäme eine Automation ihn weiter als Wahrheit geliefert — ein ausgefallener Preisabruf ließe `eedc_guenstige_stunde` womöglich dauerhaft auf `ON` stehen, und das Auto lüde zur teuersten Stunde. Ein fehlender Eingang muss sichtbar sein; „nicht verfügbar" ist die einzige Form, die HA dafür kennt.

**Was das für Automationen heißt:** Eine Bedingung `is_state('binary_sensor.eedc_haus_gunstige_stunde', 'on')` (Anlage „Haus" — die Entity-ID trägt deinen Anlagennamen, s. die Automations-Beispiele am Ende von §11) ist bei einem Ausfall von selbst `false` — sie löst nicht mehr fälschlich aus. Wer den Unterschied zwischen „aus" und „keine Daten" ausdrücklich behandeln will, fragt `states(...) == 'unavailable'` ab. Für einen **gewöhnlichen Sensor** gilt das *nicht*: der zeigt bei fehlendem Wert weiterhin „unbekannt" (`unknown`) und bleibt verfügbar — dort ist der leere Wert selbst die Aussage.

### Stufe 3 je Gerät — Fenster mit Betrag

Diese Sensoren entstehen **je Gerät** und nur, wenn eedc alle drei Fragen aus vorhandenen Daten beantworten kann: *wie viel* (die Menge des Geräts), *wogegen* (Preis- bzw. Überschussreihe) und *was kommt heraus* (ein Fenster mit Betrag). Fehlt eine Antwort, fehlt der Sensor.

<!-- erzeugt: export-sensoren kategorie=waermepumpe,sonstiges -->

> **Woher der Preis je Stunde kommt.** Der Ausgangspunkt ist **dein Tarif**, nicht die Börse — `preisquelle` sagt in jedem Fenster-Sensor, welcher der vier Fälle vorliegt:
>
> | `preisquelle` | Was drinsteht |
> |---|---|
> | `vertrag` | Der Arbeitspreis deines Tarifs, **exakt**. Für einen Festpreis ist das derselbe Wert in jeder Stunde |
> | `zeitfenster` | Der Preis des Zeitfensters, das die jeweilige Stunde deckt (Hoch-/Niedertarif, §14a) |
> | `boerse_plus_aufschlag` | Dynamischer Tarif: `(1 + USt) × Börsenpreis + Aufschlag`. Der **Aufschlag** ist abgeleitet — s. den nächsten Absatz |
> | `boersenpreis` | Dynamischer Tarif **ohne** ableitbaren Aufschlag: der nackte Börsenpreis als ausdrücklich beschriftete Näherung. Netzentgelte und Abgaben fehlen darin |
>
> ⭐ **Wie eedc den Aufschlag eines dynamischen Tarifs findet — ohne dass du ihn pflegst.** Die Annahme ist einfach: dein Endpreis ist der Börsenpreis plus ein über den Vertrag gleichbleibender Anteil. Diesen Anteil rechnet eedc aus, was ohnehin da ist, in dieser Reihenfolge:
>
> 1. **Aus deiner Abrechnung** — der letzte abgerechnete Monat innerhalb deines aktuellen Tarifs: dein Monats-Durchschnittspreis minus dem (verbrauchsgewichteten) Börsenmittel desselben Monats. Attribut `aufschlag_quelle: abrechnung 2026-08`.
> 2. **Aus gemessenen Stunden** — wenn du einen Strompreis-Sensor zugeordnet hast (Tibber, aWATTar): der mittlere Abstand zwischen gemessenem Endpreis und Börsenpreis der letzten sieben Tage (mindestens 24 Stunden). Attribut `aufschlag_quelle: sensor 7 tage`.
> 3. **Gar nicht** — dann bleibt der nackte Börsenpreis stehen, und `aufschlag_quelle` sagt `keiner`.
>
> **Es gibt kein Feld dafür, das du ausfüllen müsstest.** Trägt dein Vertrag einen Deckel oder eine Staffel, bekommst du einen Durchschnitt — und `aufschlag_basis` sagt, worauf er beruht.
>
> ⚠ **In einer Stunde mit Überschuss sinkt der Preis anteilig:** Wer dort zusätzlich verbraucht, verdrängt Einspeisung und keinen Netzbezug — bei 3 kWh Überschuss kostet die erste kWh nichts. Deshalb liegt ein Fenster mittags oft **vor** dem Preistal in der Nacht. Liegt gar kein Preis vor (kein Tarif hinterlegt), entstehen Fenster **nur innerhalb** der Überschuss-Stunden, und `preisquelle` sagt `keine`.
>
> ⛔ **Bis v4.0.49 stand hier der Börsenpreis für alle** — auch für einen Haushalt mit festem Arbeitspreis, der den Börsenpreis nie zu Gesicht bekommt. Die damalige Begründung („ein fester Aufschlag verschiebt jede Stunde um denselben Betrag und ist deshalb für die Fensterwahl neutral") hält nicht, sobald Überschuss im Spiel ist: der Überschussanteil mindert den Preis **anteilig**, ein Aufschlag verschiebt die Überschuss-Stunden also weniger als die übrigen — und die Reihenfolge der Fenster kann kippen.

> **Wie eedc eine Stunde beschriftet.** Jede Stundenangabe in diesen Sensoren sagt, ob sie einen **Beginn** oder ein **Ende** meint. Das ist nötig, weil eedc in Stunden-*Intervallen* rechnet: Der Slot „14" ist die Stunde von 13:00 bis 14:00 (dieselbe Konvention wie im HA-Energie-Dashboard und bei jedem Stromzähler — ein Zählerstand um 14:00 gehört zur Stunde davor).
>
> | Art | Attribute |
> |---|---|
> | **Beginn** — ab wann etwas gilt | `ab`, `seit`, `stunden`, `stunde_von`, `naechste_negative_ab`, `stunde_max_mittel`, `guenstige_heizstunden` |
> | **Ende** — bis wann gerechnet wurde, wann etwas erreicht ist | `bis`, `stand`, `frist`, `stunde_bis`, `bis_stunde`, alles auf `_um` (`speicher_voll_um`, `min_soc_um`) |
>
> Ein `stundenprofil_*`-Attribut trägt **24 Werte je Tag**, Index 0 ist die Stunde von 23:00 des Vortags bis 00:00 — genau wie `stundenprofil_kwh` der Prognose-Sensoren. Jede dieser Reihen nennt das im Attribut `slot_konvention: backward`.
>
> ⛔ **Bis v4.0.49 lagen fünf dieser Angaben eine Stunde daneben** (vier zu spät, `stand` eine voraus): die Fenster-Achse folgte der Börse, die stundenweise vorwärts beschriftet ist, während alle anderen Reihen rückwärts liegen. Wer eine Automation auf die alten Zeiten gebaut hat, verschiebt sie um eine Stunde.

> **Attribute je Verbrauchs-Sensor: `profil_typ` und `profil_tage`.** eedc führt **zwei** Verbrauchsmodelle, und das bleibt so: die Stundenreihen für heute stammen aus dem 7-Tage-Profil der Live-Kachel, die Speicher-Simulation hinter „Speicher voll um" und der Arbitrage-Vorschlag aus einem gewichteten 8-Wochen-Profil. Sie beantworten verschiedene Fragen. **Jeder Sensor nennt sein Modell** — wer zwei Zahlen verrechnet, sieht damit, ob sie aus derselben Annahme stammen.

### Wann ein Sensor `entity_category: diagnostic` trägt

Home Assistant meint damit *„schreibgeschützte Systemausgaben über den Zustand der Hardware"* (Batteriestand, Signalstärke, Laufzeit, Firmware). eedc hat keine Hardware — das Gegenstück ist der **Zustand der eedc-Instanz und ihrer Datenlage**, nicht der Zustand deiner Anlage:

| Kategorie | Was sie in eedc trägt |
| --- | --- |
| **ohne Kategorie** (Standard) | Alles, was eine Aussage über **die Anlage** macht: Mengen, Geld, CO₂, Kennzahlen, Prognosen, Preise — und auch Stammdaten wie die Investitionssumme. Diese Sensoren gehören aufs Dashboard. |
| **`diagnostic`** | Aussagen über **eedc selbst**: *Letzter Import* (Jahr/Monat/Monatsname) und *Erfasste Monate*. Sie beantworten „hat eedc aktuelle Daten?", nicht „wie läuft die Anlage?". |
| `config` / `system` | eedc exportiert nichts Steuerbares — beide bleiben ungenutzt. |

⚠ **Die Testfrage vor jeder neuen Definition:** *Beschreibt der Wert die Anlage oder eedc?* Die Investitionssumme etwa ist ein Stammdatum der Anlage und deshalb **kein** Diagnose-Wert — auch wenn sie sich nie ändert.

**Neu je Wärmepumpe/Klimaanlage:** `wp_betriebsmodus` — der **aktuelle** Betrieb im Klartext (*Heizen · Kühlen · Entfeuchten · Lüften · Aus · Unbestimmt*), aus der zugeordneten `climate`-Quelle — oder, ohne HA-Quelle, aus dem MQTT-Topic `…/betriebsmodus` (Wort oder Code 0–5) — über den eedc-Kanon normalisiert. Liefert dein Gerät zusätzlich `hvac_action` (den Ist-Betrieb), verfeinert der den eingestellten Modus: Nennt er eine Richtung, hat er Vorrang — steht dort **Leerlauf** (`idle`), bleibt dein eingestellter Modus stehen, denn ein taktendes Gerät verliert seine Betriebsart nicht. **Ohne zugeordnete Quelle gibt es den Sensor nicht** — eedc behauptet keinen Modus, den es nicht kennt.
>
**`wp_ersparnis_euro` und `wp_cop_durchschnitt` je Wärmepumpe (ab 05.09.2026 dieselbe Rechnung wie Hub und Cockpit):** Die Ersparnis kommt aus derselben Layer-Formel wie der Komponenten-Hub — je Monat mit dem Tarif seines Stichtags, mit dem Monats-Gaspreis, mit den fixen Zusatzkosten der Altheizung, und **ohne den Kühlstrom** (Kühlen ersetzt keine Heizung; das Attribut `berechnung` nennt den herausgehaltenen Betrag). Ist die Wärme geschätzt (Strom × JAZ) oder hängt ein zweiter Erzeuger am Wärmezähler, trägt der Sensor den Vorbehalt als Attribut **`vorbehalt`** — dieselben Worte wie unter der Ersparnis im Hub; in *Einstellungen → Integration → MQTT-Export* steht er unter der Berechnung. Die Arbeitszahl kennt dieselben Sperren wie der Hub (geschätzte Wärme, Heizstab-Fremdanteil, zweiter Erzeuger). Für den Strom je Betriebsart gibt es Sensoren für Heizen, Kühlen und Warmwasser; **Lüften und Entfeuchten** haben bewusst keinen — sie sind Mengen ohne Kennzahl (Cockpit und Hub zeigen sie), und eine Automation braucht sie nicht.

**Monate vor deinem ersten Stromtarif (`wp_ersparnis_euro`, `e_auto_ersparnis_vs_benzin_euro`, ab 12.10.2026):** Gilt in einem Monat noch kein Tarif, rechnen beide Sensoren mit der Vorbelegung 30 ct/kWh — derselbe Preis wie im Cockpit und in der Meldung des Daten-Checkers, über MQTT und REST gleich. Bis dahin nahm MQTT dafür den jüngsten Tarif-Eintrag (auch einen Wärmepumpen-, Wallbox- oder künftigen Tarif) und REST den heutigen Tarif; wer solche Monate hat, sieht einmalig einen Sprung in der Langzeitstatistik. Der Handgriff steht beim Daten-Checker: beim ältesten Tarif das „Gültig ab" auf den Beginn der Daten setzen.

**Derselbe Monatspreis für die Anlagen-Sensoren und den gepflegten Ø (ab 12.10.2026):** Auch Jahresersparnis, ROI und Amortisation der Anlage (über die bisherige Wärmepumpen- und E-Auto-Ersparnis) rechnen Monate vor dem ersten Tarif jetzt mit der Vorbelegung 30 ct statt mit dem heutigen Tarif. Und pflegst du im Monatsabschluss einen Ø-Strompreis, aber keinen eigenen Wärmepumpen-Tarif, nimmt `wp_ersparnis_euro` (und die Wärmepumpen-Ersparnis in ROI und Amortisation) diesen Ø — wie Cockpit und Wärmepumpen-Hub — statt des Tarif-Arbeitspreises; mit eigenem Wärmepumpen-Tarif bleibt es bei dessen Preis. Wer solche Monate oder einen gepflegten Ø ohne eigenen Wärmepumpen-Tarif hat, sieht in diesen Sensoren einmalig einen Sprung in der Langzeitstatistik.

**Ein Sensor, der seinen Wert verliert, bleibt nicht stehen (ab 05.09.2026):** Kann eedc einen Wert in einem Lauf nicht mehr bilden — die Arbeitszahl nach einem eingetragenen Fremdanteil, die Ersparnis nach „nichts ersetzt", ein Betriebsart-Sensor nach dem Entfernen seiner Quelle, der Speicher-Wirkungsgrad über 100 % —, setzt eedc den Sensor in Home Assistant auf **unbekannt**, statt den letzten Wert liegen zu lassen. Eine **gesperrte Kennzahl** trägt dabei ihren Grund im Attribut `grund` (dieselben Worte wie im Hub). Die Langzeitstatistik bekommt an dieser Stelle eine Lücke — das ist die richtige Aussage, keine Störung. Bis dahin blieb der letzte publizierte Wert stehen und lief stündlich in die Statistik weiter. Was nie erfasst war, bekommt weiterhin keinen Sensor.

> ⏱ **Aktualisierung im Publish-Takt** (Standard 60 Minuten, einstellbar). Für einen Modus, der in der Praxis saisonal gestellt wird, ist das genug; wer sekundengenau steuern will, liest die `climate`-Entität direkt. Was es **nur** von eedc gibt, ist die über die Stunde stabilisierte, auf den Kanon gebrachte Aussage — und dieselbe Einteilung, nach der eedc den Strom aufteilt.

> **Wertsemantik `netto_ertrag_euro` (ab v4.0):** Der Sensor trägt den kanonischen Netto-Ertrag aus dem Finanz-Aggregat-SoT: **Einspeiseerlös + EV-Ersparnis + BKW-Ersparnis + Sonstige-Netto** (Erträge − Ausgaben aus den Sonstigen Positionen, inklusive der auf **Anlage-Ebene** erfassten Positionen ab v4.0). Der Sensor-Name und die Einheit sind unverändert; nur der **Wert** enthält jetzt die Sonstigen Positionen. Achtung: die frühere Kurzformel „Einspeiseerlös + EV-Ersparnis" (noch als statisches `formel`-Label in der Definition) beschreibt nur zwei der vier Bausteine — maßgeblich ist die Summe in [Berechnungen §3.2](BERECHNUNGEN.md#32-finanzen-cockpit). Der **USt-Eigenverbrauchs-Abzug** (nur bei Regelbesteuerung) ist seit der #326-Inventur ebenfalls enthalten — `ha_export.py` rechnet `netto_ertrag -= ust_eigenverbrauch` über denselben SoT-Helper wie Cockpit und Aussichten. (Bis dahin stand hier das Gegenteil: „bleibt eine Cockpit-Zusatzlogik und ist im Export-Sensor nicht enthalten." Das war der Stand vor v4.0; die Zeile ist beim Fix nicht mitgezogen worden.)
>
> **Ergänzung 2026-07-31 (N-13):** Bei Anlagen mit einem **Dienstwagen** (E-Auto oder Wallbox mit „ausschließlich dienstliches Laden") zieht der Sensor jetzt auch die **dienstlichen Ladekosten** ab — bis dahin tat er das als einzige der drei Sichten nicht und stand damit über der Cockpit-Kachel, auf die er sich bezieht. Für diese Anlagen fällt der Wert einmalig; alle anderen sind unberührt. Formel und Begründung: [Berechnungen §3.10](BERECHNUNGEN.md).
>
> **Damit nennt der Sensor alle vier Abzüge/Bausteine der Cockpit-Kachel** — Einspeiseerlös, EV-Ersparnis, BKW-Ersparnis, Sonstige-Netto, abzüglich Netzbezugskosten, USt-Eigenverbrauch und dienstlicher Ladekosten. Er ist mit ihr deckungsgleich.

> **Wertsemantik `amortisation_jahre` · `roi_prozent` · `jahres_ersparnis_euro` (ab v4.0.12):** Nenner aller drei ist der **Kapitaleinsatz** — relevante Anschaffungskosten **plus** einmalige Ausgaben aus dem Monatsabschluss **minus** einmalige Erträge (Förderung, THG-Quote). Vorher wurde eine einmalige Ausgabe wie eine jährlich wiederkehrende Belastung vom Zähler abgezogen (eine Reparatur verlängerte die Amortisation dauerhaft und wurde jedes Folgejahr schlechter), ein einmaliger Ertrag wurde umgekehrt jedes Prognosejahr gutgeschrieben. Zweite Korrektur an derselben Rechnung: **jeder Ersparnis-Posten wird mit seiner eigenen Laufzeit** hochgerechnet, nicht mit der Monatszahl der Anlage — eine später angeschaffte Komponente wurde im Zähler zeitanteilig verdünnt, während ihre Kosten voll im Nenner standen.
>
> ⚠ **Die drei Sensoren springen dadurch einmalig** (an der Referenzanlage 26,4 → 18,5 Jahre); in der Langzeitstatistik ist das ein Sprung an einem Tag, es gehen keine Daten verloren. **`netto_ertrag_euro` ist unberührt** — die Zeitraum-Bilanz rechnet unverändert. Der ausgeschriebene **Rechenweg** im Attribut nennt seit derselben Version jeden Posten mit seiner Monatszahl und den Betriebskosten-Abzug; vorher wich er um mehrere hundert Euro vom Wert daneben ab. Herleitung: [Berechnungen §3.6](BERECHNUNGEN.md), Begriffe im [Glossar](GLOSSAR.md).

> **Wertsemantik `co2_ersparnis_kg` (ab v4.0, DI-2/DI-2-B):** Der Sensor trägt die **volle CO₂-Bilanz** aus dem kanonischen Helfer `berechne_co2_bilanz` — **PV-Eigenverbrauch** (inkl. der Erzeugung von BKW/sonstigen Erzeugern hinter dem Zähler) **+ Wärmepumpe** (vermiedenes Gas mit η_gas = 0,90 minus WP-Strom-CO₂) **+ E-Mobilität** (vermiedener Benziner minus Netzladung). Damit ist er **exakt deckungsgleich** mit der Cockpit-CO₂-Kachel (früher rechnete der Sensor nur `PV-Eigenverbrauch × Strom-Faktor`). Ein sonstiger Erzeuger (z. B. BHKW) zählt in EV/Autarkie, und sein selbst verbrauchter Strom gilt — wie im Geldwert — als vermiedener Netzstrom (0,38 kg/kWh); seine eigene Emission (etwa das Gas eines BHKW) zieht eedc nicht ab, weil es sie nicht kennt. Herleitung: [Berechnungen §3.8](BERECHNUNGEN.md#38-co2-bilanz).

> **Wertsemantik `autarkie_prozent` / `eigenverbrauch_quote_prozent` (ab v4.0, DI-2-B):** Beide Quoten werden **identisch zum Cockpit** gerechnet und beziehen die **Erzeugung hinter dem Zähler** ein (`erzeugung_hinter_zaehler_kwh` = PV inkl. Balkonkraftwerk + sonstige Erzeuger, die in denselben Hauszähler speisen). Der Nenner der Eigenverbrauchsquote ist diese Gesamt-Erzeugung, nicht „nur PV". Der **spezifische Ertrag** bleibt bewusst eine reine PV-Kennzahl (nur `pv_erzeugung`).

> **Spezifischer Ertrag — warum nicht einfach kWh ÷ kWp?** Der Sensor ist **annualisiert** und damit deckungsgleich mit der Cockpit-Kachel: saisonal gewichtet (PVGIS-Monatsverteilung) und mit der pro Monat tatsächlich aktiven PV-Leistung (Erweiterung/Teil-Rückbau wird korrekt gewichtet). Die naive Division *Gesamterzeugung ÷ heutiges kWp* würde bei 3 Jahren Historie etwa das Dreifache des gewohnten Jahreswerts anzeigen.
>
> **Woher die kWp im Nenner kommt (ab v4.0.2):** aus dem Feld **Leistung (kWp)** der jeweiligen Investition; ist es leer, aus den Detail-Feldern der Komponente (`kwp`/`leistung_kwp`, bei Balkonkraftwerken auch `leistung_wp` × `anzahl`). Vorher zählte nur das Leistungsfeld — bei importierten oder sehr alten Komponenten stand dort nichts, der Nenner war zu klein und der Sensorwert entsprechend **zu hoch**. Wer das betrifft, sieht nach dem Update einen einmaligen Sprung nach unten auf den richtigen Wert; Cockpit-Kachel und Sensor bleiben dabei deckungsgleich.

### PV-Prognose-Sensoren (`eedc_prognose_*`)

Quelle ist **immer die eedc-eigene Prognose** (OpenMeteo × Korrekturprofil) — nie Solcast/SFML, denn deren Werte liegen über die jeweilige HA-Integration ohnehin nativ in HA (kein Doppel-Export, keine Drift).

Die Korrektur erfolgt **pro Stunde** über die Korrekturprofil-Kaskade (Sonnenstand × Wetter → Saison-Stunde → Sonnenstand → Skalar; bei Anlagen ohne gelerntes Profil greift wie bisher der Lernfaktor-Skalar). Der Tagessensor ist dabei stets die Σ seiner korrigierten Stundenwerte — Sensor-State und `stundenprofil_kwh`-Attribut passen exakt zusammen. Dieselbe Berechnung speist die Spalte „eedc" im Prognosen-Vergleich: App-Ansicht und HA-Sensor zeigen denselben Tageswert.

<!-- erzeugt: export-sensoren kategorie=prognose -->

> **Vormittag/Nachmittag:** eigene VM/NM-Sensoren gibt es bewusst nicht — beides ist per HA-Template direkt aus `stundenprofil_kwh` ableitbar (z. B. `{{ state_attr('sensor.…_day_plus_1_kwh', 'stundenprofil_kwh')[:13] | sum }}` für die Stunden bis 12 Uhr).

### Börsenpreis-Trigger (`eedc_preis_*`)

Grundlage ist der **Day-Ahead-Börsenpreis** (nicht der Anbieter-Endpreis — der variiert je Vertrag/Region, die Kurvenform ist dieselbe). Tag- und Nacht-Fenster werden **solar-basiert getrennt** bewertet (Sonnenauf-/-untergang, wandert saisonal).

**Welcher Tag gemeint ist:** der Kalendertag der **Strommarkt-Zeitzone** (CET/CEST für DE und AT) — Stunde 0 ist die Stunde nach Mitternacht deiner Uhr, unabhängig davon, in welcher Zeitzone der eedc-Container läuft. Bis v4.0 wurde stattdessen ein UTC-Tag abgefragt: Die Stunden 0 und 1 trugen dadurch die Preise des **Folgetages** (in der Winterzeit die Stunde 0), und in einem Container ohne gesetzte Zeitzone lagen alle Stunden um denselben Betrag daneben. An den beiden Umstellungstagen hat das Rang-Profil folgerichtig 23 bzw. 24 Einträge — im Oktober zählt die erste der beiden Zwei-Uhr-Stunden.

**Wann der Wert wechselt:** mit dem MQTT-Versand, und der läuft **an der Uhr** — bei der Voreinstellung (alle 60 Minuten) also zur vollen Stunde, bei kürzeren Abständen im passenden Raster (`:00`, `:15`, `:30`, `:45`). Bis dahin lief der Versand ab dem Startzeitpunkt des Add-ons durch; der neue Preis kam damit um einen Versatz zu spät an, den allein der letzte Neustart bestimmte (gemeldet: `09:12:56` und, nach einem Update, `11:08:02`). Ein Intervall, das nicht auf die Uhr passt (z. B. 90 Minuten), behält seinen freien Takt — dort würde jede Ausrichtung den eingestellten Abstand verändern.

**Günstig-Definition:** Eine Stunde gilt als günstig, wenn ihr Preis unter der **Günstig-Schwelle** liegt — standardmäßig 10 % unter dem Tagesdurchschnitt ohne die 3 teuersten Stunden („optimierter Ø"). Der Prozentsatz ist je Anlage einstellbar ([MQTT-Export-Seite](HANDBUCH_EINSTELLUNGEN.md#63-mqtt-export)). Ohne die Schwelle wären die „günstigsten" Stunden rein relativ — erzwungener Verbrauch oder Netzladung in einer kaum billigeren Stunde ergibt keinen Sinn.

**Rang und „günstig" sind zwei verschiedene Aussagen** (ab v4.0.10). Der **Rang** beantwortet „gehört diese Stunde zu den fünf billigsten ihres Fensters?" und ist deshalb bei 5 gedeckelt. **Günstig** beantwortet „liegt sie unter der Schwelle?" und ist es nicht: liegen sieben Nachtstunden unter der Schwelle, meldet der Zähler auch sieben. Bis v4.0.9 zählte er nur die Ränge und war damit ebenfalls bei 5 gedeckelt — als Anzeige stimmig, als **Divisor** in einer Automation zu klein.

**Was 0 % bedeutet:** Der Prozentsatz gibt an, wie weit *unter* dem optimierten Ø eine Stunde liegen muss. Bei **0 %** liegt die Schwelle damit **genau auf dem Ø** — günstig ist dann alles, was unter dem Tagesdurchschnitt (ohne die 3 Peaks) liegt. Die Schwelle ist also nicht abgeschaltet, sie ist nur nicht zusätzlich abgesenkt. (Bis v4.0 stand hier „0 % deaktiviert die Schwelle, dann zählen wieder die 5 günstigsten". Das hat der Code nie getan; der Top-5-Deckel hat den Unterschied verdeckt.)

<!-- erzeugt: export-sensoren kategorie=preis -->

> ⚠ **Zwei Durchschnitte, zwei Fragen — nicht verwechseln.** `eedc_preis_tages_durchschnitt_cent`
> sagt, was der Strom heute im Mittel kostet; `eedc_preis_optimierter_durchschnitt_cent` sagt,
> ab wann sich das Laden lohnt. Die Günstig-Schwelle und **beide** Abstands-Größen beziehen
> sich auf den **zweiten**, nie auf den ersten. Wer in einer Automation den Tagesschnitt
> meint, nimmt den ersten (rapahl-PN 2026-08-23).
>
> **Die vier letzten sind für eigene Preis-Regeln da** (v4.0.10, Wunsch aus der Tester-Runde): „nur entladen, wenn der Strom gerade teurer ist als der Tagesschnitt" ist damit eine Bedingung auf `eedc_preis_abstand_prozent > 0` — ohne Template und ohne dass eedc eine Lade-/Entlade-Strategie vorgibt.

> ### Prozent oder Cent? Beide, und sie sagen Verschiedenes
>
> Der **Prozentwert** misst gegen den Ø **dieses Tages**: −50 % heißt „halb so teuer wie der Tagesschnitt". Er ist über Tage hinweg vergleichbar, aber **nicht** auf deinen Endpreis übertragbar.
>
> Der **ct-Wert** ist es. Denn du zahlst nicht den Börsenpreis, sondern Börsenpreis **plus** feste Bestandteile (Netzentgelt, Abgaben, Marge). Dieser Aufschlag verschiebt Stundenpreis **und** Tagesmittel um denselben Betrag — die Differenz bleibt gleich, der Prozentwert nicht. An einem echten Tag (Ø 9,92 ct): die billigste Stunde liegt **−9,93 ct** unter dem Mittel, auf der Börsenkurve wie auf dem Endpreis; in Prozent sind das **−100,1 %** bzw. **−33,2 %**. Eine Prozentzahl, die für beide Welten dasselbe bedeutet, kann es folglich nicht geben.
>
> ⚠ **Was −100 % NICHT heißt:** nicht „billigste Stunde des Tages", sondern **„Preis = 0 ct"**. Der Wert kann unter −100 % fallen — jeder negative Börsenpreis tut das. Wer „ist das eine der besten Stunden?" fragt, nimmt `eedc_preis_rang` (1–5), nicht den Prozentwert.
>
> **Faustregel:** Schwellen für Automationen (`< -5` ct) und alles, was mit deinem Tarif zu tun hat → **ct**. Tagesübergreifende Vergleiche → **Prozent**. „Eine der günstigsten Stunden" → **Rang**.

**Das Rang-Profil als Attribut** trägt je Stunde fünf Angaben: `stunde`, `rang`, `preis_cent`, `unter_schwelle` und `abstand_cent`. `preis_cent`/`unter_schwelle` gibt es ab v4.0.10, `abstand_cent` seit dem ct-Sensor — vorher stand dort nur der Rang, und damit ließ sich in HA weder eine eigene Schwelle noch ein eigenes Zeitfenster auswerten.

> ### Morgen steht daneben, sobald es ihn gibt
>
> Die Day-Ahead-Auktion veröffentlicht die Preise des Folgetages gegen **13 Uhr**. Ab dann tragen
> die Attribute von `eedc_preis_rang` einen **zweiten Satz** für morgen — dieselbe Gestalt wie
> heute, damit eine Automation beide mit demselben Code liest:
>
> | Attribut | Bedeutung |
> |---|---|
> | `morgen_verfuegbar` | `true`/`false` — **immer vorhanden**. Vor der Auktion `false`; du musst also nicht auf ein fehlendes Attribut prüfen |
> | `datum_morgen` | Kalendertag, für den der Morgen-Satz gilt |
> | `rang_profil_morgen` | 24 Stunden in derselben Form wie `rang_profil` |
> | `guenstig_schwelle_cent_morgen` | die Günstig-Schwelle **des Folgetages** |
> | `optimierter_durchschnitt_cent_morgen` | dessen Bezugsgröße |
>
> ⚠ **Jeder Tag hat seine eigene Schwelle**, und das ist Absicht: Day-Ahead ist ein Tagesprodukt.
> Ein gemeinsamer Durchschnitt über 48 Stunden würde an einem teuren Tag *keine* günstige Stunde
> ausweisen und am billigen fast alle. Wer das Morgen-Profil auswertet, nimmt deshalb
> `guenstig_schwelle_cent_morgen` — nicht die von heute.
>
> **Warum `datum` und `datum_morgen` dabeistehen:** ein Profil ohne seinen Kalendertag ist nach
> Mitternacht nicht von einem stehengebliebenen zu unterscheiden. Eine Automation, die dann auf
> „morgen" plant, plant auf gestern.
>
> **Vor 13 Uhr fragt eedc gar nicht an.** Das ist keine Sparmaßnahme, sondern der Marktrhythmus:
> vor der Auktion gibt es die Zahlen nicht.

> **Eigene Kriterien:** Wer eine andere Schwelle bevorzugt, stellt den Prozentsatz auf der Export-Seite um — oder rechnet in HA per Template direkt auf den Attributen (`rang_profil` mit den Stundenpreisen, `optimierter_durchschnitt_cent`). eedc liefert bewusst nur die **Trigger-Werte**; die Lade-/Entlade-Strategie baut jeder selbst in seinen Automationen.

### Drei Vorlagen für den HA-Template-Editor

Der Absatz darüber sagt, dass sich mit `rang_profil` eigene Kriterien rechnen lassen — er sagte
bisher nicht, **wie**. Das hat gefehlt: Wer nur die Sensorliste durchsieht, findet neun
`eedc_preis_*`-Sensoren und darunter **keinen Höchstpreis** und **keine Rang-Preise**, und
schließt daraus, dass eedc sie nicht liefert. Sie sind da — als Attribut, nicht als Sensor.

Die drei Vorlagen lassen sich unverändert in *Entwicklerwerkzeuge → Vorlage* kopieren. Wer eine
davon als Sensor haben will, setzt sie in `configuration.yaml` unter `template: - sensor:` mit
`state: >`. **Sie nehmen eine Anlage namens „Haus" an:** Home Assistant bildet die Entity-ID aus dem
Gerätenamen `eedc - <Anlage>` und dem Anzeigenamen des Sensors („Börsenpreis-Rang", Umlaut ohne
Punkte), also `sensor.eedc_haus_borsenpreis_rang` — an einer Anlage „Winterborn" heißt er
`sensor.eedc_winterborn_borsenpreis_rang`. Setz deinen Anlagennamen ein; welche ID dein Sensor trägt,
zeigt *Einstellungen → Geräte & Dienste → MQTT*, Gerät „eedc - *dein Anlagenname*".

**1) Der Tageshöchstpreis**

```jinja
{%- set p = state_attr('sensor.eedc_haus_borsenpreis_rang','rang_profil') or [] -%}
{{ (p | map(attribute='preis_cent') | max | round(2)) if p else 'unbekannt' }}
```

Für morgen dasselbe mit `rang_profil_morgen` — aber erst, wenn `morgen_verfuegbar` `true` ist.

**2) Die Ränge mit ihren Preisen**

```jinja
{%- set p = state_attr('sensor.eedc_haus_borsenpreis_rang','rang_profil') or [] -%}
{%- for s in p | rejectattr('rang','eq',99) | sort(attribute='stunde') %}
{{ '%02d'|format(s.stunde) }}:00 Uhr | Rang {{ s.rang }} | {{ s.preis_cent | round(2) }} ct
{%- endfor -%}
```

> ⚠ **Es kommen bis zu ZEHN Zeilen, nicht fünf — und „Rang 1" kann zweimal vorkommen.**
> Tag- und Nachtfenster werden **getrennt** bewertet (Grenze: Sonnenauf-/-untergang), jedes
> vergibt seine eigenen Ränge 1–5. An einem Tag, an dem die PV-Mittagsdelle die Nachtstunden
> aus der Rangliste drängt, kommen dagegen nur fünf. **Wer auf `rang <= 5` filtert, filtert
> nicht die fünf billigsten Stunden des Tages** — dafür sortiert man nach `preis_cent`.

**3) Die beste Lade-/Entladespanne, über die Tagesgrenze hinweg**

```jinja
{%- set eta = 0.90 -%}
{%- set heute  = state_attr('sensor.eedc_haus_borsenpreis_rang','rang_profil') or [] -%}
{%- set morgen = state_attr('sensor.eedc_haus_borsenpreis_rang','rang_profil_morgen') or [] -%}
{%- set r = namespace(reihe=[]) -%}
{%- for s in heute if s.stunde >= now().hour -%}
  {%- set r.reihe = r.reihe + [{'t': s.stunde, 'p': s.preis_cent}] -%}
{%- endfor -%}
{%- for s in morgen -%}
  {%- set r.reihe = r.reihe + [{'t': s.stunde + 24, 'p': s.preis_cent}] -%}
{%- endfor -%}
{%- set b = namespace(spread=0, lade=none, ent=none) -%}
{%- for a in r.reihe -%}
  {%- for z in r.reihe if z.t > a.t -%}
    {%- if (z.p * eta - a.p) > b.spread -%}
      {%- set b.spread = z.p * eta - a.p -%}
      {%- set b.lade = a -%}{%- set b.ent = z -%}
    {%- endif -%}
  {%- endfor -%}
{%- endfor -%}
{%- if b.lade is none -%}
keine lohnende Spanne
{%- else -%}
Laden {{ '%02d'|format(b.lade.t % 24) }}:00{{ ' (morgen)' if b.lade.t >= 24 else '' }} zu {{ b.lade.p | round(2) }} ct | Entladen {{ '%02d'|format(b.ent.t % 24) }}:00{{ ' (morgen)' if b.ent.t >= 24 else '' }} zu {{ b.ent.p | round(2) }} ct | Spanne {{ b.spread | round(2) }} ct/kWh
{%- endif -%}
```

Sie gibt **eine** Zeile aus (rund 90 Zeichen) und ist damit ohne Nacharbeit als Template-Sensor
verwendbar. `eta` ist dein Speicher-Wirkungsgrad — trag deinen eigenen Wert ein.

> **Warum die Spanne *gerichtet* ist:** Entladen kann man nur, was vorher geladen wurde. Ein
> ungerichtetes Tages-Min/Max nennt bei „billig 13 Uhr, teuer 08 Uhr" eine Spanne, die es an
> diesem Tag nicht mehr gibt. Die Vorlage sucht deshalb nur Paare, bei denen die teure Stunde
> **nach** der billigen liegt — und über die Tagesgrenze hinweg, sobald das Morgen-Profil da ist.
>
> **`keine lohnende Spanne`** heißt: Es gibt im bekannten Horizont kein Paar, das nach Abzug der
> Speicherverluste noch etwas übrig lässt. Das ist eine Aussage, kein Fehler — spät am Abend ohne
> Morgen-Profil ist es der Normalfall.

> ⚠ **Der Tag hat nicht immer 24 Stunden.** Am Ende der Sommerzeit fehlt die zweite Zwei-Uhr-
> Stunde, im Frühjahr die Stunde 2 ganz; `rang_profil` hat dann 23 Einträge. Alle drei Vorlagen
> laufen darüber, weil keine auf eine feste Länge prüft — wer eigene baut, prüft es auch nicht.

### Drei Automationen, die auf diesen Sensoren aufsetzen

eedc nennt Fenster, Preise und Mengen — **schalten tust du.** Die drei Beispiele zeigen, wie
eine HA-Automation die Sensoren dieser Gruppe liest. Sie sind vollständig, aber jede enthält
**eine Zeile, die du ersetzen musst:** die Entität deines Geräts (Speicher, Wallbox, Heizstab). Wie
dein Speicher „nicht entladen" oder „aus dem Netz laden" heißt, weiß nur seine Integration —
eedc kennt kein Schaltelement und erfindet keins.

Die YAML-Blöcke sind so geschrieben, dass sie sich unter *Einstellungen → Automationen → Neue
Automation → ⋮ → In YAML bearbeiten* einfügen lassen. **Die Entity-IDs darin gelten für eine Anlage
namens „Haus"** — Home Assistant bildet die ID aus dem Gerätenamen `eedc - <Anlage>` und dem
**Anzeigenamen** des Sensors, nicht aus seinem Schlüssel: aus `eedc_bezugspreis_jetzt_cent` an der
Anlage „Winterborn" wird `sensor.eedc_winterborn_bezugspreis_jetzt`, aus dem Schalter „Speicher
voll" `binary_sensor.eedc_winterborn_speicher_voll`; Umlaute fallen weg (`borsenpreis_rang`,
`gunstige_stunde`). Welche ID dein Sensor trägt, zeigt *Einstellungen → Geräte & Dienste → MQTT*, Gerät „eedc - *dein Anlagenname*". Alle drei nutzen native Bedingungen
(`numeric_state`, `state`) statt Vorlagen, wo Home Assistant das kann; nur das dritte Beispiel
liest eine Stundenreihe und braucht dafür eine Vorlage.

> **Zwei Eigenschaften der Sensoren, auf die sich die Beispiele verlassen.** Erstens: ein
> `binary_sensor` wird bei fehlender Grundlage **nicht verfügbar** — eine Bedingung auf `on` ist
> dann von selbst falsch, die Automation schaltet nichts (s. oben). Zweitens: ein Sensor, den eedc
> nicht bilden kann, **fehlt** — `eedc_speicher_netzladen_kosten_cent` gibt es nur für Speicher mit
> „lädt aus dem Netz", `eedc_abregelung_heute_kwh` nur mit gepflegter Wechselrichter-Grenze.
> Fehlt der Sensor, läuft die Automation ins Leere, ohne Fehler. Prüfe vor dem Bau in
> *Einstellungen → Integration → MQTT-Export*, ob er bei dir entsteht.

**1) Speicher schonen, solange Netzstrom billiger ist als Speicherstrom**

Strom aus dem Speicher kostet die entgangene Einspeisevergütung geteilt durch den Wirkungsgrad
(`eedc_speicher_strom_kosten_cent`, bei der Demo-Anlage 9,8 ct). In einer Stunde, in der der
Bezugspreis darunter liegt — bei einem dynamischen Tarif nachts oder bei negativen Börsenpreisen —
ist es günstiger, den Speicher zu **halten** und den Haushalt aus dem Netz zu versorgen. Die
Automation vergleicht die beiden Sensoren bei jedem neuen Preis und stellt den Speicher auf
„nicht entladen", solange das gilt.

```yaml
alias: "eedc — Speicher schonen bei billigem Netz"
description: >
  Solange der Bezugspreis der laufenden Stunde unter den Kosten einer Speicher-Kilowattstunde
  liegt, wird der Speicher nicht entladen. Beide Zahlen kommen von eedc; die Schalt-Entität
  ist die des Speichers.
mode: single
triggers:
  - trigger: state
    entity_id: sensor.eedc_haus_bezugspreis_jetzt
    note: "eedc publiziert zur vollen Stunde einen neuen Preis — das ist der Takt."
actions:
  - if:
      - condition: numeric_state
        entity_id: sensor.eedc_haus_bezugspreis_jetzt
        below: sensor.eedc_haus_speicherstrom_kostet
        note: "Netz billiger als Speicher: halten."
    then:
      - action: select.select_option
        target:
          entity_id: select.speicher_betriebsmodus   # ← Entität deines Speichers
        data:
          option: "Entladung sperren"                # ← Wortlaut deiner Integration
    else:
      - action: select.select_option
        target:
          entity_id: select.speicher_betriebsmodus   # ← Entität deines Speichers
        data:
          option: "Automatik"                        # ← Wortlaut deiner Integration
```

Bei einem **Festpreis** greift der `then`-Zweig praktisch nie (30 ct gegen 9,8 ct) — die
Automation ist dann harmlos, aber nutzlos. Sie ist für dynamische Tarife gedacht; dort trägt
`eedc_bezugspreis_jetzt_cent` den Endpreis inklusive abgeleitetem Aufschlag, nicht den nackten
Börsenpreis (Attribut `preisquelle`).

**2) Aus dem Netz laden, wenn die Kilowattstunde unter deiner Grenze bleibt**

`eedc_speicher_netzladen_kosten_cent` ist der Bezugspreis geteilt durch den Wirkungsgrad — also
das, was eine später *entnommene* Netz-Kilowattstunde wirklich kostet. Die Grenze legst du in
einem Zahlen-Helfer fest (*Einstellungen → Geräte & Dienste → Helfer → Zahl*, hier
`input_number.netzladen_grenze_cent`); so änderst du sie, ohne die Automation anzufassen. Geladen
wird nur, wenn der Speicher nach heutiger Simulation **nicht** bis Mitternacht reicht — sonst
würdest du Netzstrom einlagern, den die PV am Tag ohnehin liefert.

```yaml
alias: "eedc — Netzladen unter Preisgrenze"
description: >
  Startet die Netzladung, wenn eine aus dem Speicher entnommene Netz-Kilowattstunde unter der
  eigenen Grenze kostet und der Speicher heute nicht bis Mitternacht reicht; beendet sie, sobald
  eine der Bedingungen fällt oder der Speicher voll ist.
mode: single
triggers:
  - trigger: state
    entity_id:
      - sensor.eedc_haus_netzladen_kostet
      - binary_sensor.eedc_haus_speicher_reicht_bis_mitternacht
      - binary_sensor.eedc_haus_speicher_voll
    note: "Jeder dieser drei Sensoren kann die Entscheidung kippen."
actions:
  - if:
      - condition: numeric_state
        entity_id: sensor.eedc_haus_netzladen_kostet
        below: input_number.netzladen_grenze_cent
      - condition: state
        entity_id: binary_sensor.eedc_haus_speicher_reicht_bis_mitternacht
        state: "off"
        note: "Bei »nicht verfügbar« (keine Simulation möglich) wird nicht geladen."
      - condition: state
        entity_id: binary_sensor.eedc_haus_speicher_voll
        state: "off"
    then:
      - action: switch.turn_on
        target:
          entity_id: switch.speicher_netzladen      # ← Entität deines Speichers
    else:
      - action: switch.turn_off
        target:
          entity_id: switch.speicher_netzladen      # ← Entität deines Speichers
```

Wer stattdessen der **Menge** folgen will, nimmt `eedc_arbitrage_vorschlag_kwh` (empfohlene
Netzladung heute, mit `stunden` als Liste der günstigen Stunden) — er entsteht nur, wenn sich
Laden und späteres Entladen nach Abzug der Verluste lohnt.

**3) Einen Verbraucher in die Abregelung legen**

Was der Wechselrichter an seiner Grenze abregelt, entsteht gar nicht erst. Ein Heizstab, eine
Poolpumpe oder ein Warmwasserboiler läuft in diesen Stunden also mit Strom, der sonst verloren
wäre — billiger als jedes Überschuss-Fenster. `eedc_abregelung_heute_kwh` trägt in
`stundenprofil_kwh` je Stunde die erwartete Kappung (24 Werte, Index 0 = 23–00 Uhr des Vortags,
Index 15 = 14–15 Uhr) und in `rest_heute_kwh`, was heute noch bevorsteht. Eine Stundenreihe
lässt sich nicht nativ lesen — hier ist die Vorlage die richtige Form.

```yaml
alias: "eedc — Heizstab in die Abregelung"
description: >
  Schaltet den Heizstab ein, solange eedc für die laufende Stunde eine Abregelung an der
  Wechselrichter-Grenze erwartet, und danach wieder aus. Die Reihe ist eine Prognose auf der
  Rohvorhersage (Attribut skala) — Größenordnung und Uhrzeiten, keine Messung.
mode: single
triggers:
  - trigger: state
    entity_id: sensor.eedc_haus_abregelung_heute
    note: "Feuert bei jedem Publish, auch wenn sich nur die Attribute ändern."
  - trigger: time_pattern
    minutes: 1
    note: "Zusätzlich zur vollen Stunde, falls der Publish später kommt."
variables:
  kappung_jetzt_kwh: >-
    {% set p = state_attr('sensor.eedc_haus_abregelung_heute', 'stundenprofil_kwh') or [] %}
    {% set i = now().hour + 1 %}
    {{ (p[i] | float(0)) if p | length > i else 0 }}
actions:
  - if:
      - condition: numeric_state
        entity_id: sensor.eedc_haus_abregelung_heute
        attribute: rest_heute_kwh
        above: 0.5
        note: "Heute steht überhaupt noch eine nennenswerte Kappung bevor."
      - "{{ kappung_jetzt_kwh > 0.2 }}"
    then:
      - action: switch.turn_on
        target:
          entity_id: switch.heizstab                # ← dein Verbraucher
    else:
      - action: switch.turn_off
        target:
          entity_id: switch.heizstab                # ← dein Verbraucher
```

`now().hour + 1` ist der Index der **laufenden** Stunde: die Reihe ist rückwärts beschriftet
(Index 15 = 14:00–15:00), also liegt 14:37 Uhr in Index 15. Um 23 Uhr gibt es keinen Eintrag
(er wäre Index 24 — die Stunde gehört schon zur Reihe von morgen), die Vorlage liefert dann 0;
für einen PV-Verbraucher ist das kein Verlust. Die Schwellen (0,5 kWh Rest, 0,2 kWh in der Stunde)
sind Beispiele — bei einem 3-kW-Heizstab lohnt eine Stunde mit 0,2 kWh Kappung kaum, bei einer
Poolpumpe mit 0,5 kW schon.

> ⚠ **Was keins der drei Beispiele tut:** einen Live-Wert lesen. `eedc_ueberschuss_jetzt_kw` ist ein
> Stundenmittel und bis zu 15 Minuten alt; wer eine Wallbox nach dem *aktuellen* Überschuss regeln
> will, braucht dafür die Leistungssensoren seines Zählers, nicht eedc. eedc liefert die Planung
> für heute — Fenster, Reihen, Preise —, und die drei Beispiele bleiben in genau diesem Rahmen.

---

