# Konzept — Wirtschaftlichkeitsrechnung: wo eine Zahl hingehört und warum

> **Status: ENTSCHIEDEN und GEBAUT (2026-08-10).** Dieses Dokument hält die
> Entscheidungen fest, die am 09./10.08.2026 zwischen Maintainer und Entwicklung
> getroffen wurden — samt der **verworfenen** Wege und der Messungen, die sie
> verworfen haben.
>
> **Es existiert, damit diese Diskussion nicht erneut geführt werden muss.**
> Wer einen Einwand hat, findet ihn mit hoher Wahrscheinlichkeit unten in
> §6 („Häufige Einwände") oder §7 („Verworfen") — mit der Zahl, an der er
> gemessen wurde. Ein **echter Rechenfehler** ist davon ausdrücklich ausgenommen:
> der gehört gemeldet und behoben, nicht abgewehrt.
>
> | Was | Dauerhafte Heimat |
> | --- | --- |
> | Die Formeln selbst | [`docs/BERECHNUNGEN.md`](BERECHNUNGEN.md) §3.6 |
> | Der Layer-SoT | `eedc/backend/core/berechnungen/kapitalrechnung.py` |
> | Der Prüfer (**Regression**, ADR-002-Sprachgebrauch) | `eedc/backend/tests/test_kapitaleinsatz_vier_sichten_symmetrie.py` |
> | Der gemeinsame Nenner (Mehrkosten) | ADR-002-Umfeld, `investitionskosten.py`, N-137 |
> | Anwender-Sicht | [`docs/HANDBUCH_BEDIENUNG.md`](HANDBUCH_BEDIENUNG.md) §Auswertungen → ROI |
>
> **§8 — die Bauliste — ist am 10.08. abgearbeitet**, zuletzt Schritt 7. Sie war
> Release-Bedingung (Entscheid Maintainer, 10.08.); ein GitHub-Issue gibt es
> deshalb bewusst nicht. Der maschinelle Stand steht im Dict
> ``BAUSCHRITTE_OFFEN`` (leer), nicht in diesem Papier.
> **§10** hält die Anleitung für Komponenten-Erweiterungen fest (der Fall, aus dem
> alles entstand), **§11** regelt, wer was über welchen Kanal erfährt — inklusive
> der einen Mitteilung, die einem Bauschritt **vorausgehen** musste (sie ist
> gepostet).

---

## 1. Die Frage, die dieses Papier beantwortet

Ein Anwender pflegt Geldbeträge an drei Stellen: als Jahreswert an einer
Investition, als Position im Monatsabschluss bei einer Komponente, oder als
Position im Monatsabschluss für die ganze Anlage. Daraus entstehen vier
verschiedene Zahlen — Netto-Ertrag, ROI, Amortisationsdauer,
Amortisations-Fortschritt — in fünf verschiedenen Sichten.

**Die Frage lautet nicht „wie rechnet man das", sondern „welcher Betrag wirkt
wo, und woher weiß eedc das".** Der Kern dieses Papiers ist die zweite Hälfte:
eedc rät nichts. Der Anwender sagt es durch die **Form** und den **Ort** seiner
Eingabe.

## 2. Die Regel in drei Sätzen

1. **Ein Jahresbetrag an der Investition** ist per Form wiederkehrend. Er wirkt
   jährlich — im laufenden Ergebnis **und** in der Prognose.
2. **Ein Einzelbetrag im Monatsabschluss** ist per Form einmal geflossen. Er
   wirkt einmal — im Kapitaleinsatz, nicht in der Prognose.
3. **Der Monatsabschluss trägt zweierlei:** Einmaliges *und* **Abweichungen**
   von den regelmäßigen Beträgen der Investition. Wer dort etwas einträgt, sagt
   damit „zusätzlich zum Plan".

⚑ **Warum das ohne Kategorien auskommt.** Ältere Entwürfe wollten ein Feld
`art: aufwand|kapital` oder ein Kennzeichen `einmalig`. Beide wurden verworfen
(§7). Die Unterscheidung steckt bereits in der **Form der Zahl**: Ein
Jahresbetrag *kann* nicht einmalig wirken, ein Einzelbetrag *kann* nicht
jährlich wirken, ohne dass man ihm eine Wiederholung unterstellt. Es gibt
nichts zu klassifizieren — und damit nichts, was eedc falsch raten könnte.

## 3. Die vier Zellen

| Erfassungsort | Beispiel | Prognose | laufendes Ergebnis | Kapitaleinsatz |
| --- | --- | :---: | :---: | :---: |
| Investition — **Kosten/Jahr** (`betriebskosten_jahr`) | Versicherung 180 € | ✔ | Abzug | — |
| Investition — **Ertrag/Jahr** (`einsparung_prognose_jahr`) | zweiter Erzeuger ≈ 500 € | ✔ | Zuschlag | — |
| Monatsabschluss, `typ: ausgabe` | Reparatur 3.000 € | ✘ | — | **+** |
| Monatsabschluss, `typ: ertrag` | THG-Quote, Förderung | ✘ | — | **−** |

> ⚠ **Der Zeitraum-Bilanz ist das alles egal.** „Was hat der März gekostet und
> eingebracht?" beantworten Cockpit, Monatsbericht, Jahresbericht-PDF, CSV-Export
> und der HA-Sensor `netto_ertrag_euro` unverändert: dort ist eine Reparatur ein
> **Aufwand des Zeitraums**, und das ist richtig. Die Trennlinie verläuft
> zwischen *Bilanz* und *Kapitalrechnung*, nicht zwischen zwei Rechenwegen.
> Wer diese beiden Sichten gegeneinander hält, sieht eine Drift, wo keine ist.

## 4. Zwei Zahlen nebeneinander — und warum keine allein reicht

| | **Amortisations-Fortschritt** | **Amortisationsdauer** |
| --- | --- | --- |
| Frage | „Wie viel ist zurückgeflossen?" | „Wie lange dauert es noch?" |
| Art | **Messung** | **Modell** |
| Annahme über die Zukunft | **keine** | zwingend eine (§5) |
| Beispiel | „2.470 € von 13.000 €" | „10,5 Jahre" |

**Der Fortschritt ist die Vollkostenrechnung in Reinform:** alle eingesetzten
Beträge gegen alle erzielten, kumuliert, ohne Projektion, ohne Unterscheidung.
Er kann nicht geschönt sein, weil er nichts unterstellt.

**Die Dauer kann ohne Annahme nicht existieren.** Jede Aussage über die Zukunft
braucht eine — die Frage ist nur, welche (§5). Deshalb stehen beide
nebeneinander, auf **demselben Nenner** (N-137), sodass sich die eine in die
andere überführen lässt.

> ⚠ **„Keine Annahme" gilt für den Prozentwert, nicht für die Zeile darunter.**
> Die Fortschritts-Kachel nennt im Untertitel „noch 9.000 € · **voraussichtlich
> 2032**" — und dieses Jahr rechnet den offenen Rest mit der Jahres-Prognose
> hoch. Es ist damit selbst eine **Dauer-Aussage** und fällt unter §5, obwohl es
> in der gemessenen Kachel steht. Beim Bau von §8/6 (2026-08-10) aufgefallen und
> mitgenommen: die Restlaufzeit trägt denselben Satz wie das ROI-Dashboard,
> gebildet aus demselben Layer-SoT. **Der Fortschritt in Prozent bleibt, was
> diese Tabelle sagt** — er unterstellt nichts.

## 5. Die Annahme hinter der Dauer — drei Modelle, eines gewählt

Ein Euro kann **Kapitaleinsatz oder laufender Aufwand** sein, nicht beides.
Steht eine Reparatur im Nenner *und* wird sie in die Zukunft projiziert,
behauptet eedc zwei verschiedene Dinge über dasselbe Geld.

| Modell | Annahme | Reparatur wirkt |
| --- | --- | --- |
| **A** | „es geht nie wieder etwas kaputt" | einmal, im Nenner |
| **B** | „es geht so oft kaputt wie bisher" | jährlich, im Zähler (IST-Hochrechnung) |
| **C** | „ich rechne mit *diesem* Betrag" | jährlich, im Zähler (`betriebskosten_jahr`) |

**Gemessen** (Wärmepumpe, relevante Kosten 10.000 €, Einsparung 1.235 €/Jahr,
**eine** Reparatur 3.000 €):

| Beobachtungsdauer | **A** | **B** |
| --- | ---: | ---: |
| 2 Jahre | 10,5 J | *Zähler negativ → nie* |
| 5 Jahre | 10,5 J | 15,7 J |
| 10 Jahre | 10,5 J | 10,7 J |
| 20 Jahre | 10,5 J | 10,6 J |

⚑ **Entscheid: A als Basis, C als bewusste Ergänzung. B entfällt.**

* **B ist nicht falsch — es konvergiert gegen A**, sobald die Datenbasis trägt.
  Aber es leitet einen Erwartungswert aus wenigen Beobachtungen ab, und die Zahl
  **ändert sich jedes Jahr, ohne dass etwas passiert wäre**. Typische
  eedc-Anwender haben ein bis drei Jahre Historie — genau der Bereich, in dem B
  unbrauchbar schwankt.
* **B und C zusammen wären eine Doppelzählung** desselben Aufwands. Es ist ein
  Entweder-oder, und C ist die Variante, bei der der Anwender bestimmt, was
  drinsteht.
* **A ist optimistisch, und das wird ausgeschrieben**, nicht verschwiegen: die
  Dauer-Anzeige nennt ihre Annahme („ohne künftige Instandhaltung"). Wer
  Instandhaltung einplanen will, pflegt sie als Jahresbetrag an der Investition
  — das ist C, und dafür braucht es kein neues Feld.

## 6. Häufige Einwände — mit der Antwort

**„Meine Amortisation ist plötzlich kürzer als früher."**
Richtig, und das war der Zweck. Bis 2026-08 wurde eine einmalige Ausgabe über
die Laufzeit **annualisiert** und vom jährlichen Ertrag abgezogen. Eine
Reparatur von 3.000 € verlängerte die Amortisation einer Wärmepumpe damit von
**8,1 auf 42,6 Jahre**, in der Jahressicht erschien das Gerät als *nie
amortisiert* — und die Zahl wurde jedes Folgejahr schlechter, ohne dass etwas
passiert war. Das Geld ist einmal geflossen, nicht jedes Jahr.

**„Warum verlängert meine Reparatur die Amortisation überhaupt noch?"**
Weil sie Geld gekostet hat. Sie erhöht den Kapitaleinsatz — aus 10.000 € werden
13.000 €, aus 8,1 Jahren werden **10,5**. Sie verschwindet nicht, sie wirkt nur
einmal statt dauernd.

**„Warum steht meine THG-Quote im Zähler und die Reparatur im Nenner?"**
Sie stehen dort nicht wegen ihrer Art, sondern wegen ihrer Richtung — und die
hast du beim Erfassen selbst gewählt (`Ertrag` / `Ausgabe`). Rechnerisch:
Ein wiederkehrender Ertrag `E` im Nenner ergäbe `(K − E·n) ÷ Z` — eine Zahl,
die jedes Jahr schrumpft, bei `n = K/E` durch null geht und danach negativ
wird. Sie wäre keine Amortisationsdauer mehr. Im Zähler ergibt derselbe Ertrag
`K ÷ (Z + E)` und konvergiert.

**„Meine Anlage hält keine 10 Jahre — die Zahl ist geschönt."**
Die Dauer sagt nicht, wie lange die Anlage hält. Sie sagt: *bei diesem Nutzen
bräuchte es so lange, um das eingesetzte Geld zurückzuverdienen.* Wenn die
Anlage vorher ersetzt wird, ist die Amortisation schlicht nicht erreicht —
das sagt dir die **Fortschritts**-Anzeige daneben, und die unterstellt nichts.
Deshalb stehen beide da.

**„Warum wird meine Reparatur nicht in die Prognose eingerechnet?"**
Weil eine einmalige Ausgabe keine Vorhersage über künftige Ausgaben ist. Wer
mit Instandhaltung rechnen will, trägt sie als Jahresbetrag an der Investition
ein (Modell C) — dann steht sie in der Prognose, und zwar in der Höhe, die
*du* für realistisch hältst, nicht in der, die sich aus einem Zufall der
Historie ergibt.

**„Ich habe zwei Einspeisetarife / einen zweiten Erzeuger."**
Siehe §9. Der vorgesehene Weg ist eine eigene Investition, nicht die monatliche
Handbuchung.

**„Cockpit und ROI zeigen verschiedene Zahlen."**
Sie beantworten verschiedene Fragen — Zeitraum-Bilanz gegen Kapitalrechnung
(§3, Kasten). Beide sind richtig, und beide schreiben ihre Bezugsbasis im
Tooltip aus.

## 7. Verworfen — mit der Messung, die es verworfen hat

Diese Wege sind **nicht neu aufzurollen**. Jeder wurde durchgerechnet, keiner
scheiterte an Geschmack.

| Verworfen | Woran es scheitert |
| --- | --- |
| **Restwert als sonstiger Ertrag** buchen | zählt Kapital doppelt (179.500 statt 169.900 €) **und** annualisiert ihn |
| **Restwert per Kostenumbuchung** in den Stammdaten | `anschaffungskosten_gesamt` hat **keinen Zeitbezug** und wird von 11 Produktionsstellen gelesen ⇒ ändert **jedes** Altjahr |
| **Nullsumme** (Ertrag alt / Ausgabe neu) | auf Anlagenebene korrekt, auf Komponentenebene absurd (ROI 30,1 % beim alten, −2.743 €/Jahr beim neuen) |
| Kennzeichen **`einmalig`** an der Position | bucht den Betrag nur *sauberer in die falsche Kategorie* — **Häufigkeit ist nicht Art** |
| Feld **`art: aufwand|kapital`** | eine **neue** Kategorie, die niemand pflegt; die Form der Zahl sagt es bereits (§2) |
| **Alles** in den Nenner, auch Erträge | bricht bei wiederkehrenden Erträgen (§6, dritter Einwand) |
| **Instandhaltungsrücklage** als eigenes Konzept | fachlich identisch mit `betriebskosten_jahr` — das Feld existiert |
| **Modell B** (IST-Hochrechnung in die Prognose) | instabil bei kurzer Historie (§5) |
| **Zweite Anlage** für den zweiten Erzeuger anlegen | **Für die Abrechnung wäre es der saubere Weg** — die Vergütung hängt an `Strompreis.anlage_id`, die Anlage ist die einzige Ebene mit eigenem Einspeisesatz, und eedc ist mehr-anlagen-fähig. Es scheitert an der **Bilanz und an der Sicht**: ein Haus hat einen Hausverbrauch, einen Speicher, eine Autarkie — beides je Anlage gerechnet, der Speicher gehört genau einer, der Hausverbrauch müsste willkürlich geteilt werden, und im Community-Vergleich erschienen zwei halbe Anlagen. Dazu **jede** Sicht hängt an `useSelectedAnlage()`: es gibt **keine** anlagenübergreifende Auswertung, nur Selektoren (am Code erhoben 2026-08-10) — der Anwender sähe seine Anlage nie auf einen Blick und müsste ständig umschalten und im Kopf addieren. **Richtig bleibt die zweite Anlage für einen wirklich getrennten Zählpunkt** (zweites Haus, Anlage der Eltern), **falsch für einen zweiten Erzeuger hinter demselben Hausanschluss** |

> **Und die Ausgangsfrage, aus der das alles entstand, ist damit beantwortet:**
> *Es gibt keine Restwert-Behandlung, weil eedc keine Wertfortschreibung kennt.*
> Es rechnet Ausgaben gegen Ersparnis. Wer eine Komponente erweitert, legt einen
> neuen Datensatz an; **jeder Datensatz trägt, was für ihn bezahlt wurde**.

## 8. Was noch fehlt — die Bauliste

**Ohne diese Punkte wird nicht released** (Entscheid Maintainer, 10.08.2026).

✅ **Abgearbeitet am 2026-08-10** — alle neun Schritte sind gebaut, der letzte
war Nr. 7. Maschineller Stand: das Dict ``BAUSCHRITTE_OFFEN`` in
`eedc/backend/tests/test_konzept_wirtschaftlichkeit_konformitaet.py` ist
**leer**; jede Zeile unten hat dort ihre Probe, die die Konzept-Erwartung prüft
statt den Ist-Zustand. Wer einen neuen Bauschritt eröffnet, trägt ihn **hier**
ein und legt seinen Eintrag im Dict an — nicht umgekehrt.

| # | Was | Größe | Warum |
| --- | --- | --- | --- |
| ~~1~~ | ~~**Ertragsfeld an der Investition pflegbar machen** — `einsparung_prognose_jahr` ins Formular, neben `betriebskosten_jahr`~~ | ~~klein~~ | ✅ **gebaut 2026-08-10.** Feld in `InvestitionCreate`/`InvestitionUpdate`, im Formular als **„Ertrag/Jahr (€)"** — sichtbar nur bei *Wallbox* und *Sonstiges*, denn nur dort liest es das ROI-Dashboard (SoT der Menge: `models/investition.py::ERTRAGSFELD_TYPEN`, Client-Pendant in `investitionFormHelpers.ts`). ⚑ **Eine Stelle kam dazu, die die Zeile nicht nannte:** der JSON-Export/Import trug `betriebskosten_jahr`, aber nicht das Ertragsfeld — ein Backup/Restore hätte genau den Wert verloren, den dieser Schritt pflegbar macht. Additiv, Export-Version bleibt 1.3 |
| ~~2~~ | ~~**Prognose zieht die Investitions-Jahreswerte**~~ | ~~klein~~ | ✅ **gebaut 2026-08-10.** `aussichten.py` addiert den Jahres-Ertrag ungeteilt in `jahres_netto_ertrag` (er ist bereits eine Jahresgröße, §2/1) — begrenzt auf `ERTRAGSFELD_TYPEN` **und** auf heute aktive Investitionen: eine stillgelegte Komponente bringt keinen künftigen Ertrag. ⚑ **Auch hier war die Zeile zu eng:** die HA-Sensoren `jahres_ersparnis_euro` · `roi_prozent` · `amortisation_jahre` bilden ihre Jahresgröße selbst (`kapitalrechnung.jahres_ersparnis_euro`) und hätten eine andere Zahl gezeigt als die Oberfläche, sobald jemand das Feld pflegt. Der Layer-SoT nimmt den Betrag jetzt als eigenen Summanden `jahres_ertraege_euro` — **ohne** Annualisierung, spiegelbildlich zu den Betriebskosten — und schreibt ihn in der Erklärzeile aus (N-212). Das PDF war bereits gedeckt: seine Amortisation kommt aus dem ROI-Dashboard, die Spalte „Einsparung/Jahr" zeigt das Feld je Investition |
| ~~3~~ | ~~**Monatsabschluss-Positionen werden nicht projiziert**~~ | ~~klein~~ | ✅ **gebaut 2026-08-10.** F-19 hatte die Ausgabenseite geheilt; hier folgt die **Ertragsseite** in denselben drei Sichten (`aussichten.py` · `crud.py::get_roi_dashboard` · `ha_export.py`). **Gemessen an der DB-Kopie:** Jahres-Netto-Ertrag der Aussichten 5.794,52 → **5.618,39 €**, ROI-Jahreseinsparung 5.951,72 → **5.800,05 €** (15,4 → **15,8 Jahre**), HA `jahres_ersparnis_euro` 4.972,96 → **4.796,83 €**, `amortisation_jahre` 18,48 → **19,16**, `roi_prozent` 5,41 → **5,22**. ⚑ **Unverändert, und das ist die Probe auf §3/§4:** `netto_ertrag_euro` (Zeitraum-Bilanz), der Amortisations-**Fortschritt** (10,8 %) und der Kapitaleinsatz. Der Ertrag verschwindet also nicht — er hört nur auf, sich zu wiederholen. ⛔ Bis Bauschritt 7 wirkt er in der Kapitalrechnung dadurch **gar nicht** mehr; das ist der ausdrückliche Zwischenstand aus §9.1 |
| ~~4~~ | ~~**Allgemeine Positionen in den Fortschritt** (Monatsdaten-Zeile, G19-1)~~ | ~~klein~~ | ✅ **gebaut 2026-08-10.** Der Fortschritt sammelte nur aus `historische_inv_daten` und übersah damit genau den Ort, der für „mehrere Komponenten" vorgesehen ist. ⚑ **Beim Bau wurde die Zeile zweimal zu eng befunden:** die Lücke saß nicht nur im *Fortschritt*, sondern auch im **Nenner**, und nicht nur in `aussichten.py`, sondern ebenso in `crud.py::get_roi_dashboard` (⇒ auch im PDF). **Gemessen 10.08.:** eine anlagenweite Ausgabe von 3.000 € ergab HA-Sensor **18.000 €** gegen ROI/Aussichten **15.000 €**; eine anlagenweite Förderung war in beiden Sichten unsichtbar. Jetzt liest `aussichten.py` die Monats-Fakten (P10-Bereinigung), `crud.py` zieht den `anlage_*_euro`-Anteil in die **Gesamt**-Zahlen (eine Position ohne Investition kann auf keiner ROI-Zeile stehen). Der Symmetrie-Wächter hatte den Fall nicht gesehen, weil seine Fixture die Position komponentengebunden anlegt — Probe ergänzt |
| ~~5~~ | ~~**Amortisations-Fortschritt je Investition**~~ | ~~groß~~ | ✅ **gebaut 2026-08-10.** Gebaut als **Zerlegung, nicht als zweite Rechnung**: der anlagenweite Zähler wird auf die ROI-Zeilen verteilt (`core/berechnungen/ertrag_zerlegung.py`), sodass `Σ Zeilen + Rest == gesamt` **per Konstruktion** gilt statt per Test. Schlüssel der Erzeugungsseite ist die **gemessene Erzeugung je Zeile** (Entscheid Maintainer) — kWp sagt, was ein Modul könnte, kWh sagt, was es beigetragen hat; ein Wechselrichter ohne Module hat Gewicht 0 und erbt deshalb nichts. Alles, was bereits komponentenscharf vorliegt, wird **nicht** verteilt, sondern direkt zugeordnet (WP je Gerät, E-Auto je Fahrzeug, BKW, gepflegte Monats-Erträge). ⚑ **N-228 ließ sich nicht abtrennen:** mit dem alten, anlagenweiten Betriebskosten-Abzug trug der Rest systematisch die Differenz — **am Dev-Bestand 566,67 €** (1.291,67 € statt 725,00 €), und ein Rest mit bekannter Ursache ist keine Restgröße mehr. Der anlagenweite Fortschritt steigt dadurch von **10,8 % auf 11,4 %**. **Nicht zurechenbare** Erträge (anlagenweite Positionen, §8/4) stehen als eigener Rest in der Response, statt still auf die Zeilen verteilt zu werden |
| ~~6~~ | ~~**Dauer-Anzeige schreibt ihre Annahme aus**~~ | ~~klein~~ | ✅ **gebaut 2026-08-10.** Formuliert wird der Satz **einmal** (`core/berechnungen/kapitalrechnung.py::annahme_dauer_text`) und von jedem Ausgabeweg abgeholt. ⚑ **„Die Dauer-Anzeige" gibt es nicht — es sind neun Stellen in fünf Dateien**, gespeist aus vier Quellen: ROI-Dashboard gesamt (Kachel · Break-Even-Kurve · Summenzeile · v4-Block-Zusammenfassung) und je Zeile (Tabellen-Tooltip), PDF-Finanzbericht, HA-Sensor `amortisation_jahre` — dort **im Rechenweg-Attribut**, weil ein Sensor keinen Tooltip hat. Dazu die Wallbox-Dauer im Komponenten-Hub, die im Client aus `Anschaffung ÷ Ersparnis` entsteht und deshalb den festen Modell-A-Text aus `lib/amortisationAnnahme.ts` trägt. ⚠ **Und die Zeile kannte den zweiten Fall nicht:** sobald `betriebskosten_jahr` gepflegt ist, rechnet eedc **Modell C** — der Betrag ist im Zähler bereits abgezogen, „ohne künftige Instandhaltung" wäre dort eine falsche Aussage über die eigene Rechnung. Der Text richtet sich deshalb nach den Daten. **Am Dev-Bestand gemessen:** die Anlage trägt 500 €/Jahr ⇒ „inkl. 500,00 €/Jahr Betriebskosten …", die WP-Zeile 200 €, das BHKW 300 €, alle übrigen Zeilen Modell A — der statische Satz wäre dort in **drei** von vier Sichten falsch gewesen. **Keine Zahl bewegt sich**, nur ihre Beschriftung |
| ~~8~~ | ~~**Zwei Daten-Checker-Regeln**~~ | ~~klein~~ | ✅ **gebaut 2026-08-10** (`daten_checker/monatsdaten.py::ErfassungsortChecks`, Kategorien `position_wiederkehrend` · `position_doppelerfassung`, beide **INFO** mit Weg zur Behebung). ⚑ **Zwei Präzisierungen waren nötig, beide unten in §8.1 nachgetragen:** die Schwelle der zweiten Regel (das Papier nannte nur „gleichnamige Monatsposition" — ohne Schwelle meldete sie jede einzelne Reparatur neben einer gepflegten Versicherung, also **≥ 2** Monate bei gepflegtem Jahresbetrag gegen **≥ 3** ohne) und die **Ertragsrichtung**: der Fall aus §9 (zweiter Erzeuger, monatlich gepflegt) ist genau der, für den Bauschritt 1 gebaut wurde — aber „Ertrag/Jahr" gibt es nur bei *Wallbox* und *Sonstiges*, bei allen anderen Typen wäre der Rat ein Verweis auf ein Feld, das der Anwender nicht findet (P-6). ⚠ **Beide Regeln schließen sich aus** — ein Sachverhalt, eine Meldung: mit gepflegtem Jahresbetrag ist „trag es als Jahresbetrag ein" ein falscher Rat |
| ~~9~~ | ~~**Erlös je Erzeuger als €-Feld, per Sensor befüllbar** (§9, Weg 2)~~ | ~~mittel~~ | ✅ **gebaut 2026-08-10.** Entscheid Maintainer 2026-08-10: der Jahresbetrag aus §8/1 ist für den Fall aus §9 nur die Notlösung. Mit einem €-Feld an *Sonstiges/Erzeuger*, das ein **HA-Template-Sensor** befüllt, entfällt jede Schätzung: die Tarif-Logik bleibt in Home Assistant, der Wert kommt monatsgenau und wird im Monatsabschluss vorgeschlagen. **Am Code erhoben (10.08.):** *Sonstiges/Erzeuger* trägt heute **nur** `erzeugung_kwh` · `eigenverbrauch_kwh` · `einspeisung_kwh` — **ein €-Feld existiert dort nicht und muss angelegt werden** (SoT `field_definitions.py`, drei Pflicht-Stellen); `€`/`monetary` steht bereits in der Sensor-Allowlist der Datenquellen-Fläche, ein €-Sensor ist also auswählbar. ⚠ **Der Erlös entsteht heute ausschließlich aus `Monatsdaten.einspeisung_kwh` × EINEM Satz** (`monats_fakten.py:706`); die Einspeisung eines Sonstiges-Erzeugers wird **nirgends** in Geld bewertet. Das neue Feld ist deshalb ein **zusätzlicher** Ertrag dieses Erzeugers — **kein Herausrechnen aus der Anlagenbewertung nötig**. ⚑ **Begründung (Maintainer, 10.08., korrigiert einen Fehlschluss der Entwicklung):** zwei Vergütungssätze bedeuten **zwei Messungen** — anders könnte der Netzbetreiber nicht abrechnen. In den Anlagen-Einspeisezähler gehört also ohnehin nur die zum Anlagentarif vergütete Menge; die kWh des zweiten Erzeugers stehen dort gar nicht. Was bleibt, ist ein **Hinweis am Feld** (was in den Anlagenzähler gehört) — mehr kann eedc nicht wissen, welchen Sensor jemand gemappt hat, weiß nur er. **Gebaut als durchgehende Kette:** `field_definitions.py` (Registry ⇒ Monatsabschluss · CSV · MQTT · Datenquellen-Zuordnung kommen von selbst) → `imd_monatsaggregat` (kategorie-bewusst: ein Verbraucher hat keinen Einspeise-Erlös) → `monats_fakten` (Anlagen-Summe **und** je Gerät) → Layer-SoT `finanz_aggregat` als **fünfter** Summand → Aussichten · HA-Export · Cockpit → Jahr · Jahresbericht-PDF. ⚠ **Das Cockpit baut seinen Netto-Ertrag selbst aus den Einzel-Komponenten zusammen** (USt-Abzug dazwischen) und musste eigens angeschlossen werden — dieselbe Stelle, an der #326 auseinanderlief. **Am Dev-Bestand gemessen:** das Mini-BHKW (Kategorie *Erzeuger*) trägt das Feld, der Heizstab (*Verbraucher*) nicht |
| ~~7~~ | ~~**Erträge zurück in den Nenner**~~ | ~~mittel~~ | ✅ **gebaut 2026-08-10** — der letzte der Bauliste. Die sonstigen **Erträge** mindern den Kapitaleinsatz, spiegelbildlich zu F-19 auf der Ausgabenseite; damit ist die Vollkostenrechnung vollständig und §3 Zeile 4 („Kapitaleinsatz **−**") eingelöst. **Beide Vorbedingungen waren erfüllt und wurden vor dem Bau nachgeprüft**, nicht abgeschrieben: (a) der Umstiegsweg §9.1 existiert seit §8/1 **und** §8/9 (das €-Feld je Erzeuger ist der bessere der beiden), (b) die Kommunikation an rilmor-mhrs steht als [Kommentar zu #310](https://github.com/supernova1963/eedc-homeassistant/issues/310#issuecomment-5242379712) vom 10.08. — mit der Aufforderung, die monatlichen Handbuchungen einzustellen. ⚑ **Keine Migration** (Entscheid Maintainer 10.08.): einmalige Erträge gehören nach der Regel aus §2 ohnehin in den Kapitaleinsatz, und wiederkehrende erkennt seit §8/8 der Daten-Checker **am Erfassungsort**. **Gemessen am Dev-Bestand (455 € Ertrags-Positionen):** Kapitaleinsatz **91.915 → 91.460 €** in allen vier Sichten, Tesla-Zeile 17.560 → 17.105 € (14,3 → 14,0 Jahre), HA `amortisation_jahre` 19,16 → **19,07**, `roi_prozent` 5,219 → **5,245 %**, Amortisations-Fortschritt 11,4 → **10,9 %** (der Ertrag verlässt den Zähler ganz, mindert den Nenner aber nur anteilig) — **unverändert** `netto_ertrag_euro` (Zeitraum-Bilanz) und die Modell-Dauer 15,8 Jahre. ⚑ **Ein Nebeneffekt fiel beim Bau auf und fuhr mit:** der gepflegte Erzeuger-Erlös aus §8/9 landete in der Zerlegung (§8/5) im **nicht zurechenbaren Rest**, obwohl seine Investition bekannt ist — jetzt direkt zugeordnet. Die vier ⏳-Stellen sind nachgezogen, die vierte (`HANDBUCH_BEDIENUNG.md`) trug wie angekündigt kein Kennzeichen |

**Bereits gebaut** (2026-08-09, ungepusht): sonstige **Ausgaben** kumuliert in den
Nenner statt annualisiert in den Zähler · jeder Ersparnis-Posten wird mit
**seiner eigenen** Monatszahl annualisiert · die Rechenwege der HA-Sensoren
schreiben ihre Bestandteile aus · der PDF-Finanzbericht nennt dieselbe Zahl wie
die Oberfläche.

### 8.1 Daten-Checker — welche Fehleingaben das Modell überhaupt erzeugen kann

Die Regel aus §2 verlagert die Entscheidung vom Code zum **Erfassungsort**. Das
ist der Grund, warum eedc nichts raten muss — und zugleich die einzige Stelle,
an der ein Anwender das Modell verfehlen kann. **Zwei Fehleingaben sind
belastbar erkennbar**, weil sie auf **Wiederholung** beruhen und nicht auf der
Deutung eines Wortes:

| Fehleingabe | Woran erkennbar | Meldung |
| --- | --- | --- |
| **Wiederkehrendes im Monatsabschluss** — z. B. „Wartung" in mehreren Monaten | dieselbe Bezeichnung an einer Investition in **≥ 3 Monaten**, **ohne** gepflegten Jahresbetrag | Hinweis: gehört als **Jahresbetrag an die Investition** (§2/1). Dort wirkt sie auch in der Prognose — im Monatsabschluss nie |
| **Doppelerfassung** — Jahresbetrag gepflegt **und** derselbe Posten monatlich gebucht | Jahresbetrag > 0 **und** dieselbe Bezeichnung an derselben Investition in **≥ 2 Monaten** | Hinweis: im Monatsabschluss gehört nur die **Abweichung** vom Plan (§2/3), sonst zählt der Betrag doppelt |

> ⚑ **Beide Schwellen präzisiert beim Bau (2026-08-10).** Die zweite Regel
> nannte ursprünglich keine — wörtlich hätte sie **jede einzelne** Reparatur
> neben einer gepflegten Versicherung gemeldet, und ein Hinweis, der keinen
> Fehler beschreibt, ist die P-6-Falle. Tragend ist auch hier die
> **Wiederholung**, nur früher: bei gepflegtem Jahresbetrag ist bereits die
> zweite Buchung ein Muster. Und weil beide Regeln denselben Sachverhalt
> beschreiben, **schließen sie sich aus** — mit gepflegtem Jahresbetrag wäre
> „trag es als Jahresbetrag ein" ein falscher Rat.
>
> ⚠ **Die Ertragsrichtung gilt nur, wo es das Feld gibt.** Der Fall aus §9
> (zweiter Erzeuger mit eigenem Vergütungssatz, monatlich von Hand gepflegt)
> ist genau der, für den Bauschritt 1 das Feld **„Ertrag/Jahr"** geschaffen
> hat — es existiert aber nur bei *Wallbox* und *Sonstiges*
> (`models/investition.py::ERTRAGSFELD_TYPEN`). Bei allen anderen Typen rechnet
> eedc die Jahres-Einsparung selbst; dort schweigt die Regel, statt auf ein
> Feld zu verweisen, das im Formular nicht steht.

> ⛔ **Nicht prüfen: was eine Position *bedeutet*.** Naheliegend wäre, aus
> Bezeichnungen wie „Restwert", „Verkauf" oder „Förderung" auf einen
> Kapitalzufluss zu schließen. Das wäre eine **erfundene Regel** über
> Freitext — dieselbe Klasse, die dieses Konzept mit `art` und `einmalig`
> bereits verworfen hat (§7). Die Richtung sagt `typ`, die Häufigkeit sagt der
> Ort; mehr weiß eedc nicht, und mehr soll es nicht raten.

⚠ **Beide Meldungen sind Hinweise, keine Fehler** — die Erfassung ist nicht
falsch, sie ist nur an der Stelle, an der sie weniger kann. Und sie folgen der
Checker-Regel des Projekts: **kein „Akzeptiert"-Knopf**, sondern ein Weg zur
Behebung.

## 9. Der Beispielfall: zwei Erzeuger, zwei Einspeisetarife

Ein Anwender betreibt neben der Hauptanlage weitere Wechselrichter, die mit
**eigenen Einspeisesätzen** abgerechnet werden. eedc kennt **einen**
Einspeisesatz je Anlage — es gibt keine Vergütung je Erzeuger, und
`Monatsdaten.einspeisung_kwh` ist ein Anlagen-Zählerwert.

**Bisheriger Behelf:** die Erlöse monatlich von Hand als sonstige Erträge
buchen. Funktioniert, ist aber eine Krücke — und sie war der Grund, warum
Erträge nicht pauschal in den Nenner dürfen (§6).

**Vorgesehener Weg:** eine eigene Investition vom Typ **„Sonstiges", Kategorie
*Erzeuger*.** Sie trägt bereits die passenden Felder — `erzeugung_kwh`,
`eigenverbrauch_kwh`, `einspeisung_kwh` —, **alle sensorfähig**. Damit läuft
die kWh-Seite automatisch.

Für die **Bewertung** stehen zwei Wege offen, beide noch nicht gebaut:

| Weg | Aufwand | Ergebnis |
| --- | --- | --- |
| **Tarif je Investition** | groß — berührt die gesamte Tarif-Auflösung | eedc rechnet den Erlös selbst, monatsgenau, mit historischen Sätzen |
| **€-Feld an der Investition, per Helfer-Sensor befüllt** | klein — €-Felder mit Sensor existieren bereits (`ladung_extern_euro`) | exakt und automatisch; die Tarif-Logik bleibt in Home Assistant |

Der zweite Weg ist dem Jahres-Schätzwert aus §8/1 **überlegen**: monatsgenau
statt gemittelt, ohne jede Handpflege.

### 9.1 Der Umstiegsweg — und warum er vor Bauschritt 7 liegen muss

**Schritte für den Anwender** (§8/1 ist seit 2026-08-10 gebaut — das Feld
heißt im Formular **„Ertrag/Jahr (€)"** und steht bei *Wallbox* und
*Sonstiges* neben den Betriebskosten):

1. Neue Investition **„Sonstiges", Kategorie *Erzeuger*** anlegen, mit dem
   Anschaffungsdatum und den Kosten des zweiten Erzeugers.
2. Seine Sensoren zuordnen (Erzeugung, ggf. Einspeisung/Eigenverbrauch) — ab
   hier läuft die Energieseite ohne Handpflege.
3. Den Erlös bewerten: entweder Jahresbetrag am Ertragsfeld (§8/1) oder
   monatsgenau über das €-Feld per Helfer-Sensor (§8, sobald gebaut).
4. Die bisherigen **monatlichen Handbuchungen** ab dem Umstiegsmonat
   **einstellen** — sonst zählt derselbe Erlös zweimal.

> ✅ **Erfüllt am 10.08.** — beide Schritte des Wegs sind gebaut (§8/1 und
> §8/9), die Mitteilung an #310 ist gepostet, **danach** wurde Bauschritt 7
> gefahren. Der Absatz bleibt als Begründung stehen, nicht als offene Auflage.
>
> ⛔ **Bauschritt 7 („Erträge zurück in den Nenner") war erst zulässig, wenn
> dieser Weg existiert und die Betroffenen ihn kennen.** Sonst ändert sich die
> Wirkung **bestehender Daten**: wer wiederkehrende Erträge weiterhin monatlich
> pflegt, sähe seine Amortisation danach nicht mehr verkürzt, sondern seinen
> Kapitaleinsatz gemindert — bei einer eigenen Ertrags-Investition sogar
> `(K − E·n) ÷ Z`, die Zahl aus §6. **Reihenfolge ist hier keine Vorliebe,
> sondern Datenschutz an bestehenden Beständen.** Vor Schritt 7 gehört deshalb
> eine Kommunikation (§11) — und die Prüfung, ob eine Migration nötig ist.

## 10. Erweiterung einer Komponente (Speicher, PV)

Die Frage, aus der dieses ganze Papier entstanden ist. **eedc kennt keine
Wertfortschreibung und damit keinen Restwert** (§7-Kasten) — eine Erweiterung
wird deshalb nicht umgebucht, sondern **abgebildet**.

### 10.1 Speicher — durchgespielt und gemessen

**An einer Kopie des Dev-Bestands durchgeführt (2026-08-09), nicht hergeleitet.**
Ausgangslage: ein Speicher 15,4 kWh, 12.000 €, ab 06/2023, 31 Monate Daten.
Erweiterung zum 01.07.2025 auf 30,8 kWh für 8.000 €.

| Schritt | ⚠ Fallstrick |
| --- | --- |
| 1. Am alten Gerät **`stilllegungsdatum`** setzen | **Niemals `aktiv = false`** — das entfernt es auch aus der Historie |
| 2. Neuen Datensatz ab dem Erweiterungstag anlegen, mit der **Gesamtkapazität** (nicht mit der Differenz) | — |
| 3. **Denselben Wechselrichter-Parent** setzen | Ohne ihn gilt der neue Speicher als *Standalone* und bekommt eine **eigene ROI-Zeile**, während der alte Komponente des PV-Systems bleibt: gleicher Gerätetyp, zwei Darstellungen |
| 4. **Monatsdaten ab dem Wechselmonat umhängen** | Sie bleiben sonst am alten Datensatz und fallen nach dessen Stilllegung aus der Anzeige |
| 5. **Kosten: jeder Datensatz trägt, was für ihn bezahlt wurde** (12.000 € / 8.000 €) | Kein Restwert-Transfer — jede Variante davon ist in §7 gemessen und verworfen |

**Ergebnis der Messung:** Der Komponenten-Hub zeigt beide Speicher getrennt mit
je eigenem Zeitraum und eigener Kapazität — **A: 15,4 kWh · 273,6 Vollzyklen ·
25 Monate · 4.820,6 kWh** und **B: 30,8 kWh · 35,1 Vollzyklen · 6 Monate ·
1.345,4 kWh**. Σ Ladung **6.166,0 kWh = Ausgangswert auf die Stelle** — keine
Energie verloren, keine doppelt. Vorher liefen 343,8 Vollzyklen gegen *einen*
15,4-kWh-Nenner; jetzt rechnet jeder Abschnitt gegen seine eigene Kapazität.

> ⛔ **Offen und ausdrücklich NICHT zugesichert: derselbe Sensor an beiden
> Datensätzen.** Der Schreibpfad des Monatsabschlusses filtert **nicht** je
> Monat (`monatsabschluss/views.py` iteriert über alle Investitionen der Anlage
> ohne Laufzeitprüfung) — im Formular eines Monats *vor* der Erweiterung
> erscheint der neue Speicher mit. Der ältere Befund „beiden zugeordnet =
> Doppelzählung, nur einem = der zweite bleibt leer" steht damit weiter.
> ⚠ **Der Testdurchlauf oben widerlegt ihn nicht** — er hat die Monatsdaten
> **von Hand** umgehängt und damit nur die Auswertungsseite geprüft, nie den
> Import. *Ein Durchlauf belegt nur den Pfad, den er wirklich gelaufen ist.*
> **Bis das gemessen ist, gilt die Anleitung nur für Bestände, bei denen die
> Monatswerte gepflegt oder umgehängt werden — nicht für den automatischen
> Sensor-Import.**

### 10.2 PV — einfacher, und geprüft

Ein zusätzliches **Modulfeld mit eigenem Anschaffungsdatum** genügt. Keine
Stilllegung, kein neuer Datensatz für das Bestehende, keine Restwert-Frage
(`services/pv_monatswerte.py`, #236).

### 10.3 Wärmepumpe · Wallbox · E-Auto

⚠ **Ungeprüft.** Es liegt nahe, dass 10.1 überträgt, aber gemessen ist es
nicht. **Kein „vermutlich" in die Anwender-Doku** — entweder vorher messen oder
die Anleitung ausdrücklich auf Speicher und PV beschränken.

## 11. Kommunikation — wer erfährt was, über welchen Kanal

> **Kanalregel:** GitHub (Issues/Discussions) kann aus der Entwicklung heraus
> beantwortet werden, **Forum und PN ausschließlich durch den Maintainer** —
> und beides nur nach ausdrücklicher Freigabe. Für die Änderungen dieses
> Konzepts entstehen **keine neuen Issues** (Entscheid Maintainer): Erklärungen
> gehören in `docs/`, ins Handbuch und in die In-App-Hilfe.

| Empfänger | Kanal | Was mitzuteilen ist | Wann |
| --- | --- | --- | --- |
| **Alle Anwender** | CHANGELOG + WAS-IST-NEU | **Fünf ausgelieferte HA-Sensoren ändern ihren Wert** (`amortisation_jahre` · `roi_prozent` · `jahres_ersparnis_euro` sowie die Amortisations-Anzeigen in *Auswertungen → ROI* und *Aussichten*). Richtung: die Amortisation wird **kürzer**. Die Langzeitstatistik springt an einem Tag. `netto_ertrag_euro` bleibt unberührt | **vor** dem Release, ganz oben |
| **Reupchen** (#374) | GitHub-Discussion | Der Weg aus §10.1, mit dem Ergebnis der Messung — und der offenen Sensor-Frage aus dem Kasten, ehrlich benannt | nach dem Release |
| **Pelzar** (T90480) | Forum | dasselbe; er hatte den Fall zuerst gemeldet | nach dem Release, **nur Maintainer** |
| **Radiocarbonat** (T90480) | Forum | Seine Meldung ist **eingelöst**: eine einmalige sonstige Ausgabe verschlechtert die Amortisation nicht mehr dauerhaft. Der damals vorgeschlagene Weg (Investitionshistorie mit Gültigkeitsdatum) wurde **nicht** gebaut — die Wirkung ist trotzdem da | nach dem Release, **nur Maintainer** |
| **rilmor-mhrs** (#310, wieder geöffnet) | GitHub-Issue-Kommentar | Sein Anliegen bleibt erfüllt; **zusätzlich** der bessere Weg aus §9.1, samt der Aufforderung, die monatlichen Handbuchungen einzustellen | ✅ **gepostet 10.08.**, vor Bauschritt 7 |

⚑ **Der letzte Punkt war der einzige mit einer harten Reihenfolge** — und er
ist eingehalten: Kommentar zuerst, Bauschritt 7 danach (beides am 10.08.). Alle
anderen Mitteilungen sind Information; diese eine war **Voraussetzung** dafür,
dass der Bauschritt überhaupt gefahren werden durfte (§9.1).

⚠ **Und sie ist keine Abhängigkeit von einer Antwort.** Robert *kann*
antworten, muss aber nicht: die Migrationsfrage ist ohne ihn entschieden
(keine Migration, s. §8 Zeile 7). Ein Projekt, das einen Bauschritt an eine
Anwender-Rückmeldung hängt, hätte sich selbst blockiert.

## 12. Belege

* **Layer-SoT:** `eedc/backend/core/berechnungen/kapitalrechnung.py` — Nenner
  und Zähler-Annualisierung an einem Ort, mit der Begründung im Modul-Docstring.
* **Regression** (nicht Wächter — ADR-002 §„gesichert durch": er ruft die vier
  Sichten **namentlich** auf, eine fünfte mit demselben Fehler sähe er nicht):
  `test_kapitaleinsatz_vier_sichten_symmetrie.py` — ein gemeinsamer
  Nenner über *Auswertungen → ROI*, HA-Sensoren, Aussichten und PDF, dazu beide
  Seiten des Bruchs. Er prüft **bewusst keine gleichen Endwerte**: die vier
  Sichten meinen nicht dieselbe Größe (Modell neben Messung), und ein Test auf
  Gleichheit wäre aus sachfremden Gründen rot.
* **Nenner-Symmetrie (Mehrkosten):** `test_amortisation_nenner_symmetrie.py`, N-137.
* **Messungen:** an einer Kopie des Dev-Bestands erhoben (2026-08-09), nie an
  der Produktionsanlage.
