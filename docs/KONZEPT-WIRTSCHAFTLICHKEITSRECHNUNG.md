# Konzept — Wirtschaftlichkeitsrechnung: wo eine Zahl hingehört und warum

> **Status: ENTSCHIEDEN (2026-08-10), teilweise gebaut.** Dieses Dokument hält die
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
> **Offen ist §8** — die Bauliste. Ohne deren Abarbeitung wird nicht released
> (Entscheid Maintainer, 10.08.); ein GitHub-Issue gibt es deshalb bewusst nicht.
> **§10** hält die Anleitung für Komponenten-Erweiterungen fest (der Fall, aus dem
> alles entstand), **§11** regelt, wer was über welchen Kanal erfährt — inklusive
> der einen Mitteilung, die einem Bauschritt **vorausgehen** muss.

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
| Investition — **Ertrag/Jahr** *(Feld noch nicht pflegbar, §8)* | zweiter Erzeuger ≈ 500 € | ✔ | Zuschlag | — |
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

> **Und die Ausgangsfrage, aus der das alles entstand, ist damit beantwortet:**
> *Es gibt keine Restwert-Behandlung, weil eedc keine Wertfortschreibung kennt.*
> Es rechnet Ausgaben gegen Ersparnis. Wer eine Komponente erweitert, legt einen
> neuen Datensatz an; **jeder Datensatz trägt, was für ihn bezahlt wurde**.

## 8. Was noch fehlt — die Bauliste

**Ohne diese Punkte wird nicht released** (Entscheid Maintainer, 10.08.2026).

| # | Was | Größe | Warum |
| --- | --- | --- | --- |
| 1 | **Ertragsfeld an der Investition pflegbar machen** — `einsparung_prognose_jahr` ins Formular, neben `betriebskosten_jahr` | klein | Das Feld existiert und wird gelesen (`crud.py`, Typ *Wallbox/Sonstiges*), hat aber **kein Eingabefeld**. Ohne es fehlt der Ort für wiederkehrende Erträge — die Regel aus §2 wäre nur halb anwendbar |
| 2 | **Prognose zieht die Investitions-Jahreswerte** | klein | Die Aussichten kennen `einsparung_prognose_jahr` bisher nicht (0 Treffer) |
| 3 | **Monatsabschluss-Positionen werden nicht projiziert** | klein | §5, Modell A |
| ~~4~~ | ~~**Allgemeine Positionen in den Fortschritt** (Monatsdaten-Zeile, G19-1)~~ | ~~klein~~ | ✅ **gebaut 2026-08-10.** Der Fortschritt sammelte nur aus `historische_inv_daten` und übersah damit genau den Ort, der für „mehrere Komponenten" vorgesehen ist. ⚑ **Beim Bau wurde die Zeile zweimal zu eng befunden:** die Lücke saß nicht nur im *Fortschritt*, sondern auch im **Nenner**, und nicht nur in `aussichten.py`, sondern ebenso in `crud.py::get_roi_dashboard` (⇒ auch im PDF). **Gemessen 10.08.:** eine anlagenweite Ausgabe von 3.000 € ergab HA-Sensor **18.000 €** gegen ROI/Aussichten **15.000 €**; eine anlagenweite Förderung war in beiden Sichten unsichtbar. Jetzt liest `aussichten.py` die Monats-Fakten (P10-Bereinigung), `crud.py` zieht den `anlage_*_euro`-Anteil in die **Gesamt**-Zahlen (eine Position ohne Investition kann auf keiner ROI-Zeile stehen). Der Symmetrie-Wächter hatte den Fall nicht gesehen, weil seine Fixture die Position komponentengebunden anlegt — Probe ergänzt |
| 5 | **Amortisations-Fortschritt je Investition** | **groß** | Der Nenner liegt vor (jede ROI-Zeile trägt ihren Kapitaleinsatz); es fehlen die **kumulierten Erträge je Komponente**. Bedingung des Maintainers für Modell C — ohne die Gegenkachel wäre die Dauer die geschönte Zahl ohne Korrektiv |
| 6 | **Dauer-Anzeige schreibt ihre Annahme aus** | klein | §5, letzter Punkt |
| 8 | **Zwei Daten-Checker-Regeln** — wiederkehrender Posten im Monatsabschluss · Doppelerfassung Jahresbetrag/Monatsposition | klein | §8.1. Das Modell verlagert die Entscheidung zum Erfassungsort; **genau dort** kann ein Anwender es verfehlen, und nur dort ist es erkennbar |
| 7 | **Erträge zurück in den Nenner** — erst nach 1–3 **und nach der Kommunikation** | mittel | Vollendet die Vollkostenrechnung. ⛔ **Zwei Vorbedingungen, beide hart:** (a) der Umstiegsweg muss existieren (§9.1), sonst gäbe es keinen Ort für wiederkehrende Erträge; (b) wer sie heute monatlich pflegt, muss es **vorher** wissen (§11, letzte Zeile) — dieser Schritt ändert die Wirkung **bestehender Daten**. Dabei ist zu prüfen, ob eine Migration nötig ist. ⏳ **Und vier Stellen nachziehen — aber nur DREI davon sind per `⏳` auffindbar:** Modul-Docstring `kapitalrechnung.py` · Docstring von `test_kapitaleinsatz_vier_sichten_symmetrie.py` — die Probe `test_ertrag_bleibt_im_zaehler_…` ist dann **umzuschreiben**, nicht der Code zu reparieren · `BERECHNUNGEN.md` §3.6. ⚠ **Die vierte ist `HANDBUCH_BEDIENUNG.md`** („Du musst dafür nichts umstellen") und trägt **absichtlich kein Kennzeichen** — Anwender-Doku beschreibt den IST-Zustand, nicht künftige Pläne (N-217). **Ein `grep ⏳` findet sie deshalb nicht**, und sie ist die Stelle mit der größten Anwenderwirkung: sie steht in der ausgelieferten In-App-Hilfe |

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
| **Wiederkehrendes im Monatsabschluss** — z. B. „Wartung" in mehreren Monaten | dieselbe Bezeichnung an einer Investition in **≥ 3 Monaten** | Hinweis: gehört als **Jahresbetrag an die Investition** (§2/1). Dort wirkt sie auch in der Prognose — im Monatsabschluss nie |
| **Doppelerfassung** — Jahresbetrag gepflegt **und** derselbe Posten monatlich gebucht | `betriebskosten_jahr` > 0 **und** gleichnamige Monatsposition an derselben Investition | Hinweis: im Monatsabschluss gehört nur die **Abweichung** vom Plan (§2/3), sonst zählt der Betrag doppelt |

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

**Schritte für den Anwender**, sobald §8/1 gebaut ist:

1. Neue Investition **„Sonstiges", Kategorie *Erzeuger*** anlegen, mit dem
   Anschaffungsdatum und den Kosten des zweiten Erzeugers.
2. Seine Sensoren zuordnen (Erzeugung, ggf. Einspeisung/Eigenverbrauch) — ab
   hier läuft die Energieseite ohne Handpflege.
3. Den Erlös bewerten: entweder Jahresbetrag am Ertragsfeld (§8/1) oder
   monatsgenau über das €-Feld per Helfer-Sensor (§8, sobald gebaut).
4. Die bisherigen **monatlichen Handbuchungen** ab dem Umstiegsmonat
   **einstellen** — sonst zählt derselbe Erlös zweimal.

> ⛔ **Bauschritt 7 („Erträge zurück in den Nenner") ist erst zulässig, wenn
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
| **rilmor-mhrs** (#310, geschlossen) | GitHub-Issue-Kommentar | Sein Anliegen bleibt erfüllt; **zusätzlich** der bessere Weg aus §9.1. ⚠ **Und die Warnung vor Bauschritt 7** — bevor der kommt, muss er umgestellt haben | **vor** Bauschritt 7, nicht erst danach |

⚑ **Der letzte Punkt ist der einzige mit einer harten Reihenfolge.** Alle
anderen Mitteilungen sind Information; diese eine ist **Voraussetzung** dafür,
dass ein Bauschritt überhaupt gefahren werden darf (§9.1).

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
