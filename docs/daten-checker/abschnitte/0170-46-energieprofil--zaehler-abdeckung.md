<!-- anker: 46-energieprofil--zaehler-abdeckung -->
### 4.6 Energieprofil – Zähler-Abdeckung <a name="46-energieprofil--zaehler-abdeckung"></a>

> **Variantenhinweis:** Im **HA Add-on** sind die Zähler Sensoren aus Home Assistant (`sensor.…`) mit
> `state_class: total_increasing`. Im **Standalone-Betrieb** sind sie kumulative MQTT-Topics
> (`eedc/<anlage>/inv/<id>/<feld>`). Die Prüfung ist in beiden Fällen dieselbe — sie schaut, ob in der
> Datenquellen-Zuordnung je Komponente ein kWh-Zähler eingetragen ist.

**Was wird geprüft:** Welche kumulativen kWh-Zähler sind in der Datenquellen-Zuordnung der Anlage gesetzt? Ohne sie bleibt
das Energieprofil für die betroffenen Komponenten leer — und damit Prognose-IST, Lernfaktor und die Monatsauswertungen aus
dem Energieprofil. Live-Anzeigen aus den Leistungs-Sensoren (W) funktionieren weiter, ergeben aber keine Energiemengen.

> **Die teuerste Folge betrifft Speicher und PV.** Der bilanzielle Gesamtverbrauch einer Stunde entsteht als
> PV + Netzbezug − Einspeisung − Speicher (= Eigenverbrauch + Netzbezug). Fehlt einer dieser Anteile, wird er als **0**
> gerechnet: die Stunde bleibt nicht leer, sondern fällt **zu niedrig** aus — und sieht dabei plausibel aus. Daran hängt
> die **Grundlast** (Median der Nachtstunden 0–5 Uhr) und mit ihr die Monatsansicht im Cockpit, der **Monatsbericht** und
> der HA-Sensor `eedc_grundlast_kw`. Typisches Bild bei fehlendem Speicher-Zähler: die Grundlast steht im Sommer nahe
> null und steigt scheinbar von selbst, je weniger der Akku die Nacht trägt.
>
> **Nur diese zwei Komponententypen sind betroffen.** Wärmepumpe, Wallbox und E-Auto stehen nicht in dieser Formel — sie
> sind Teil des Gesamtverbrauchs. Ein fehlender Zähler an ihnen lässt ihre eigenen Auswertungen leer, verfälscht aber
> weder Gesamtverbrauch noch Grundlast (nur der **Restverbrauch** = Gesamtverbrauch − separat erfasste Verbraucher wird zu
> hoch).

**Erwartete Zähler je Komponententyp:**

| Komponententyp | Erwartete kWh-Zähler-Felder |
|---------------|------------------------------|
| PV-Module, Balkonkraftwerk | `pv_erzeugung_kwh` |
| Speicher | `ladung_kwh`, `entladung_kwh` |
| Wärmepumpe | `stromverbrauch_kwh`; mit «Getrennte Strommessung» stattdessen `strom_heizen_kwh` und `strom_warmwasser_kwh` (an einer Split-Klimaanlage nur Heizen) |
| Wallbox, E-Auto | `ladung_kwh` |
| Sonstiges | das Zählerfeld seiner Kategorie (Verbraucher, Erzeuger, Abgabe an Dritte); ein Verbrauchszähler (Gas, Wasser, Heizöl) wird übersprungen |
| Wechselrichter | (keine — wird übersprungen) |

> **Was hier „zugeordnet“ heißt — auch MQTT.** Ein Feld trägt einen Zähler, wenn
>
> 1. ihm ein **Sensor aus Home Assistant** zugeordnet ist, **oder**
> 2. dafür **Zählerstände per MQTT ankommen**.
>
> Hast du für ein Feld ausdrücklich **«Keine»** gewählt, bleibt das deine Absage — sie schlägt beides.
>
> ⚠ **Entscheidend ist der Messwert, nicht der Eintrag.** Ein Feld, das auf MQTT steht, weil eedc das beim Einrichten als
> Grundeinstellung gesetzt hat, gilt nicht automatisch als versorgt — eedc sieht nach, ob auf dem Topic tatsächlich etwas
> angekommen ist. **Das Fenster ist eine Woche:** Bleibt ein Befund stehen, obwohl du per MQTT publizierst, kam auf diesem
> Topic seit über sieben Tagen nichts an. Dann prüfe deinen Publisher, nicht die Zuordnung.

> **Ein „—“ in der Tagesansicht im Cockpit sagt selbst, woran es liegt.** Drei Lagen führen dorthin, und nur die erste
> ist eine Aufgabe für dich: *Kein Zähler zugeordnet* · *Zähler zugeordnet, aber für diesen Tag liegen keine Zählerstände
> vor* · *Der Zähler ist an diesem Tag zurückgesprungen*. Der mittlere Fall ist der Regelfall kurz nach einer Zuordnung:
> Der **Monats**wert steht da, weil er aus der Langzeitstatistik von Home Assistant kommt — **Tages**werte entstehen erst
> ab der Zuordnung. Frühere Tage lassen sich in der Reparatur-Werkbank nachrechnen.

> **Wer hier ausgenommen ist:** **Split-Klimaanlagen** (Wärmepumpenart *Luft-Luft*) werden nicht nach Wärme gefragt, eine
> **Brauchwasser-Wärmepumpe** nicht nach Heizwärme. Das **E-Auto** wird für den Ladezähler übersprungen, wenn eine
> **Wallbox mit eigenem kWh-Zähler** in Betrieb ist (dort wird die Heimladung geführt; für die PV-Ladung als Zusatzfeld
> genügt eine Wallbox), oder wenn es als **Dienstwagen** markiert ist. Stillgelegte und inaktive Komponenten
> zählen nicht mit. Ein **Balkonkraftwerk, an dem PV-Module hängen**, braucht keinen eigenen Zähler — die Module tragen
> seine Erzeugung.

> **Hinweis:** Diese Kategorie prüft nur das **Vorhandensein** der Zuordnung — ob der Zähler tatsächlich Daten liefert,
> prüfen die MQTT-Topic-Abdeckung ([§4.8](#48-mqtt-topic-abdeckung)) bzw. Sensor-Mapping – HA-Statistics
> ([§4.9](#49-sensor-mapping--ha-statistics)). Unmögliche Stundenwerte erfasst [§4.7](#47-energieprofil--plausibilitaet).

---
