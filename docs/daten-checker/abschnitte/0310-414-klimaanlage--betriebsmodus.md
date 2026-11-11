<!-- anker: 414-klimaanlage--betriebsmodus -->
### 4.14 Klimaanlage – Betriebsmodus <a name="414-klimaanlage--betriebsmodus"></a>

**Was wird geprüft:** Hat jedes Gerät, das heizt **und** kühlt, einen Weg, seinen Strom nach Heizen und Kühlen aufzuteilen? Gemeint sind Split-Klimaanlagen (Wärmepumpenart *Luft-Luft*) und jede Wärmepumpe, an der eine Kühl-Größe zugeordnet oder gepflegt ist (Kühl-Leistung, Kältemenge, Kühl-Betriebsart) — sie kühlt nachweislich, gleich welcher Bauart. Eine Luft-Wasser-Wärmepumpe ohne jede Kühl-Spur bekommt keinen Hinweis.

**Warum das zählt:** Deine Klimaanlage heizt im Winter und kühlt im Sommer — über **denselben** Stromzähler. eedc sieht deshalb nur eine Zahl „Stromverbrauch" und kann nicht sagen, welcher Teil davon ins Heizen ging und welcher ins Kühlen. Aus den vorhandenen Werten lässt sich das auch nicht nachrechnen: Es gibt kein Feld, aus dem die Aufteilung ableitbar wäre. Sie entsteht nur, wenn eedc **zur Messzeit mitschreibt**, in welchem Modus das Gerät gerade läuft — oder wenn eigene Zähler je Betriebsart messen.

> **Es gibt zwei Wege zu dieser Aufteilung, und der gemessene gewinnt.**
>
> 1. **Gemessen** — du ordnest eigene Zähler je Betriebsart zu (*Strom Heizbetrieb*, *Kühlbetrieb*, *Lüftbetrieb*, *Entfeuchtung*), am Gerät oder je Innengerät. Wer sie in Home Assistant nicht direkt bekommt, baut sie sich mit einem **Utility Meter** je Betriebsart.
> 2. **Abgeleitet** — du ordnest den **Betriebsmodus** zu (in Home Assistant die climate-Entität des Geräts), und eedc schreibt stündlich mit, was das Gerät gerade tat.
>
> Liegen **gemessene** Werte vor, rechnet eedc die abgeleitete Aufteilung für dieses Gerät gar nicht erst — ganz oder gar nicht, nie beides gemischt. Eine Zuordnung des Betriebsmodus wäre dann wirkungslos. Deshalb erscheint der Hinweis **nicht mehr**, sobald einer der beiden Wege eingerichtet ist (oder Werte auf einem von beiden angekommen sind).

> ⚠ **Die Aufteilung lässt sich nicht rückwirkend nachtragen — das ist der wichtigste Satz hier.** Home Assistant bewahrt Zustände wie „Heizen"/„Kühlen" nur wenige Tage auf (die Langzeit-Statistik gibt es nur für Zahlen-Sensoren). Wer den Sensor heute zuordnet, bekommt die Aufteilung **ab heute**; die Vergangenheit bleibt ungeteilt, und ein längerer eedc-Ausfall reißt eine Lücke, die bleibt. Deshalb lohnt sich die Zuordnung auch dann, wenn man die Auswertung noch nicht braucht.

> **Das Feld bietet eedc jeder Wärmepumpe an**: Es gibt Luft-Wasser-Geräte mit Kühlfunktion, und wer eines hat, findet den Betriebsmodus in der Datenquellen-Zuordnung.

> **Der Betriebsmodus geht auch über MQTT — als Inbound, nicht über das Gateway.** Er ist ein Zustand, kein Messwert: eedc nimmt am Modus-Topic ein Wort oder einen Zahlencode (0–5) entgegen ([Wärme & Klima, „Ohne Home Assistant: der Modus über MQTT"](HANDBUCH_WAERME_KLIMA.md#ohne-home-assistant-der-modus-über-mqtt)). Das Gateway reicht nur Zahlen weiter und steht an diesem Feld nicht zur Wahl. Über MQTT beginnt die Aufteilung mit dem ersten empfangenen Wert — auch hier nicht rückwirkend.

> **Was du nach der Zuordnung siehst:** In der Ansicht der Wärmepumpe unter Komponenten steht ein Block **„Aufteilung Heizen/Kühlen"** mit den beiden Strommengen, der Zeile *nicht aufgeteilt* und der Zahl der Stunden, in denen eedc mitlesen konnte. Dieselbe Aufteilung erscheint in der Monats- und Jahresansicht im Cockpit, dazu zwei Sensoren in Home Assistant. Die Aufteilung entsteht beim **Monatsabschluss**; für den laufenden Monat wird sie direkt aus den Tageswerten gelesen.

**Verwandte Befunde:** Ist die Aufteilung eines Monats größer als der Gesamtverbrauch des Geräts — oder hat eedc sie deshalb beim Speichern gar nicht übernommen —, meldet das die Kategorie **Investitionen** (§4.3), weil es an den Monatswerten des Geräts hängt, nicht an der Sensor-Zuordnung. eedc biegt dort nichts zurecht: Statt die Aufteilung stillschweigend auf den Gesamtwert zu kürzen, bleibt der Widerspruch sichtbar, bis du entschieden hast, welche der beiden Angaben stimmt. ⚠ **Deine Energiebilanz ist davon nicht betroffen:** dort zählt immer der Gesamtwert.

---
