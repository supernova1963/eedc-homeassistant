<!-- anker: 425-wetterwerte-fehlende-monatswerte -->
### 4.25 Wetterwerte – fehlende Monatswerte <a name="425-wetterwerte-fehlende-monatswerte"></a>

**Was wird geprüft:** Trägt jeder abgeschlossene Monat seine **drei Wetterwerte** — Globalstrahlung, Sonnenstunden und Ø Temperatur —, stammen sie **aus derselben Quelle**, und ist diese Quelle überhaupt **festgehalten**? Die Ø Temperatur hat eigene Zeilen; Globalstrahlung und Sonnenstunden stehen gemeinsam in **einer** Zeile mit **einer** Aktion, «Wetterreihe nachziehen».

**Warum das zählt:** Globalstrahlung und Sonnenstunden sagen, wie viel Sonne ein Monat hatte — ohne sie lässt sich ein schwaches Jahr nicht von einer schwachen Anlage unterscheiden, und eine Reihe aus zwei Quellen vergleicht Lineale statt Sonne. Das Feld *„Ø Temperatur"* im Monatsabschluss wird beim Abschließen automatisch gefüllt — eedc nimmt zuerst **deine eigene Messreihe** (Stundenwerte der Außentemperatur, ersatzweise das Tages-Min/Max) und sonst das Wetter-Archiv. Zwischen Juli und September 2026 gab es dieses Auto-Fill nicht: Jeder in dieser Zeit abgeschlossene Monat kann ohne Wert dastehen.

> **eedc rechnet mit der Ø Temperatur heute keine Kennzahl aus.** Die Außentemperatur-Linie im Wärme/Klima-Verlauf und der Vergleich *kWh je Heizgradtag* lesen die **Tagesreihe** — feiner und unabhängig von diesem Feld. Der Monatswert ist die gepflegte **Rückfallebene** für Zeiträume, in denen diese Reihe fehlt. Deshalb ist der Befund ein **Hinweis** und keine Warnung.

> **Der laufende Monat wird nie bemängelt** — und auch nicht nachgezogen. Die Wetter-Archive liefern einen Monat erst ein paar Tage nach seinem Ende vollständig; ein halber Monat, als ganzer festgeschrieben, wäre eine falsche Zahl, die danach feststeht.

> **Warum «Wetterreihe nachziehen» immer erst eine Vorschau zeigt.** Die Aktion **ersetzt** vorhandene Werte — das ist ihr Zweck, denn eine Reihe aus zwei Quellen wird man nicht anders los. Etwas, das ersetzt, bekommt bei eedc immer erst eine Vorschau: sie sagt vorher, wie viele Monate betroffen sind und wie viele davon überschrieben werden.

> **Die fehlende Quellenangabe ist der Normalfall jeder Bestandsanlage.** An einer echten Anlage nachgemessen (39 Monate): Globalstrahlung und Sonnenstunden fehlten in **keinem** Monat, und **kein einziger** trug eine festgehaltene Quelle. Ohne diesen Teil der Zeile bliebe eine möglicherweise gemischte Reihe unbemerkt. **Er geht wieder weg:** Sobald jeder Monat seine Quelle trägt, ist die Menge leer — ein Übergangsbefund, kein Dauerzustand. Die **Ø Temperatur** zählt dabei bewusst nicht mit: Kommt sie aus deiner eigenen Messreihe, hat sie legitim keinen Wetterdienst als Quelle.

> **Was diese Prüfung nicht sehen kann.** Sie liest die mitgeschriebene **Herkunft** jedes Werts und fragt dafür kein Wetter-Archiv (eine Prüfung ohne Nebenwirkung). Werte, die geschrieben wurden, bevor eedc die Herkunft mitschrieb, gelten als *unbekannt*, nicht als *abweichend*. Der Bestand heilt beim ersten Nachzug: der schreibt die echte Quelle mit.

**Wo du den Wert siehst:** *Einstellungen → Daten → Monatsdaten*, Monat öffnen, Abschnitt «Wetterdaten (optional)». Ein von Hand gesetzter Wert wird **nie** überschrieben — weder vom Auto-Fill noch von «Temperatur aus Messung übernehmen» noch vom täglichen Lückenschluss. Die **einzige** Ausnahme ist «Wetterreihe nachziehen», und die löst du ausdrücklich aus. Als Kurve stehen Globalstrahlung und Sonnenstunden in den Auswertungen unter «Prognose» im Block «Sonnenangebot».

**Was eedc von allein tut:** Einmal täglich sieht eedc nach, ob ein abgeschlossener Monat eines der drei Felder vermissen lässt, und füllt **nur diese Lücken** — mit der an der Anlage gewählten Quelle. Was schon dasteht, bleibt stehen. Liefert kein messendes Archiv (das kommt außerhalb des DWD-Netzes vor), **bleibt die Lücke sichtbar**, statt mit einem langjährigen Mittelwert zugedeckt zu werden: ein Durchschnitt über viele Jahre würde ein schwaches Jahr unsichtbar machen.

---
