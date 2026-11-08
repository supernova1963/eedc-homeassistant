## 4. Wärmepumpe

### Monatserfassung

<!-- erzeugt: eingabefelder typ=waermepumpe liste=monat merkmal=!je_innengeraet -->

### Live-Dashboard

<!-- erzeugt: eingabefelder typ=waermepumpe liste=live -->

> ⚠️ **`leistung_w` verdrängt `leistung_heizen_w`, `leistung_warmwasser_w` und
> `leistung_kuehlen_w`.** Ist die Gesamtleistung zugeordnet, wertet eedc die drei
> Funktions-Sensoren im Tagesverlauf **nicht** aus — die Wärmepumpe erscheint dort als **eine**
> Fläche. Bleibt `leistung_w` leer, bekommt jeder zugeordnete Funktions-Sensor im Tagesverlauf
> von *Cockpit → Live* eine eigene Fläche mit eigenem Namen (Heizen, Warmwasser, Kühlen). Der
> **Stundenverlauf des Tages** schlüsselt erst ab **zwei** Funktions-Sensoren auf — ein einzelner
> wäre dort die Gerätereihe unter anderem Namen. Beides ist richtig, es ist eine Wahl: Die
> Gesamtleistung ist der vollständige Anlagenwert (und die einzige Quelle des
> Wärmepumpen-Anteils in der Verbrauchsprognose), die getrennten Felder sind die feinere
> Auskunft — die Verbrauchsprognose nimmt `leistung_warmwasser_w` und `leistung_kuehlen_w` aus den
> Tagesprofilen, um diese Anteile nicht mit der Außentemperatur zu skalieren. Details und Folgen: [Handbuch Wärme & Klima §5, Schritt 6](HANDBUCH_WAERME_KLIMA.md#schritt-6--live-werte-optional).
>
> ⚠️ **Kein Ersatz für kWh-Zähler.** Diese Felder sind Momentanleistungen und speisen die
> Mengen nicht — Stromverbrauch, Wärme und alle Arbeitszahlen kommen aus den kWh-Feldern oben.

### MQTT Energy Topics

Welche MQTT-Topics eedc für dieses Gerät erwartet — Energie- und Live-Topics je Feld —, steht in [MQTT-Inbound](MQTT_INBOUND.md#topic-struktur).

### 4a. Verbrauch je Betriebsart und je Innengerät

> **Bei einer Klimaanlage stehen diese Felder gleich mit da.** An jeder anderen
> Wärmepumpenart findest du sie unter *Einstellungen → Datenquellen* beim Gerät
> hinter **„Weitere Größen erfassen"** — sie sind dort seltener, aber genauso
> zuordenbar. Wer einen getrennten Kühlzähler an seiner
> Luft-Wasser- oder Sole-Wasser-Wärmepumpe hat, trägt ihn dort ein; sobald ein
> Sensor zugeordnet ist, steht das Feld oben bei den anderen.
>
> Alle Felder sind **optional**: kein Sensor, keine Anzeige.

Ein Gerät, das heizt, kühlt, lüftet und entfeuchtet, tut das oft über
**denselben** Zähler. Wer die Anteile getrennt messen kann, trägt sie hier ein —
sie sind **Teilmengen** des Gesamtverbrauchs und werden nie dazuaddiert.

⚠️ **Kühlen, Lüften und Entfeuchten zählen nicht in die Arbeitszahl.** Sie
erzeugen keine Wärme, die sich messen ließe; läge ihr Strom im Nenner, sähe eine
Anlage, die im Sommer kühlt oder viel lüftet, wie eine schlechte Heizung aus.
Für Wirtschaftlichkeit und CO₂ gilt beim Kühlen dasselbe schon länger. Ist der
ganze Verbrauch eines Zeitraums Kühlbetrieb, steht statt der Arbeitszahl der
Grund dafür.

**Lüften und Entfeuchten bekommen eine eigene Zeile in der Aufteilung, sobald du
einen Zähler dafür zugeordnet hast** — vorher stecken sie in „nicht aufgeteilt".
Eine **Kennzahl** bekommen sie bewusst nicht: Es gibt keinen Nutzen, gegen den
man sie rechnen könnte. Misst du zusätzlich ihre *abgegebene Nutzenergie*, steht
sie seit v4.0.45 als eigene **Mengenzeile** daneben — im Komponenten-Hub und im
Wärme/Klima-Block von Cockpit → Monat/Jahr, und nur dann, wenn ein Zähler etwas
gemeldet hat.

**Nutzenergie Heizbetrieb ist die Heizwärme deines Geräts.** Hast du keinen
Wärmemengenzähler am Gerät selbst (Feld *Heizwärme* bzw. *Wärme gesamt*), rechnet
eedc seit v4.0.45 mit ihr: Sie trägt dann die Wärme-Kachel und die Arbeitszahl.
Ist beides gepflegt, gewinnt der Gerätezähler — er misst mehr als eine einzelne
Betriebsart. Bei mehreren Innengeräten werden ihre Werte summiert; ein Wert am
Gerät schlägt die Summe seiner Innengeräte und wird nie dazuaddiert.

<!-- erzeugt: eingabefelder typ=waermepumpe liste=monat merkmal=je_innengeraet -->

Soll- und Raumtemperatur je Innengerät (`soll_temperatur_c`, `ist_temperatur_c`) stehen in der Live-Tabelle von §4.

**Kompressor-Starts und Betriebsstunden** sind keine Felder der Feld-Registry: Sie stehen in `KUMULATIVE_COUNTER_FELDER` (`backend/services/snapshot/keys.py`) — Zählwerke ohne Energie-Einheit, die der stündliche Snapshot wie einen Zählerstand erfasst und die nie in die Energie-Bilanz gehen (§9); ihre Beschriftung kommt aus `core/field_definitions/karten.py`.

| Feld | Label | Einheit | Sensortyp | Beschreibung | Ausgewertet in |
|------|-------|---------|-----------|-------------|-----------------|
| `wp_starts_anzahl` | Kompressor-Starts | Anzahl | Counter (Total-Increasing) | **Optional, ab v3.24.0 (#136).** Kumulativer Anzahl-Zähler für Kompressor-Starts der Wärmepumpe. Z. B. aus der lokalen „Nibe Heat Pump"-Integration: `sensor.compressor_number_of_starts_…`. Stündlicher Snapshot-Job erfasst den Counter wie kWh-Zähler; Tagesabschluss berechnet Stunden- und Tages-Differenzen. **Bewusst kein Fallback** aus `leistung_w` oder Compressor-Binary — würde gerade kurze Takte (wo der KPI sticht) systematisch unterzählen. Anzeige: [Cockpit → Tag](HANDBUCH_BEDIENUNG.md#22-tag) (Spalte „WP-Starts", default ausgeblendet) und Wärmepumpe-Komponentensicht ([Bedienung §3.4](HANDBUCH_BEDIENUNG.md#34-wärmepumpe)). | Komponenten → Wärmepumpe · Jahresbericht (PDF) |
| `wp_betriebsstunden` | Betriebsstunden | h | Counter (Total-Increasing) | **Optional, ab v3.34 (#238).** Kumulativer Zähler der Gesamt-Betriebsstunden der WP. Kombiniert mit `wp_starts_anzahl` ergibt sich „Ø Laufzeit pro Start" als Auslegungs-/Verschleiß-Maß. Wird wie ein Counter behandelt — keine Energie-Einheit, keine Aufnahme in die Energie-Bilanz (siehe §9). | Komponenten → Wärmepumpe |

> **`betriebsart_nutzenergie_kuehlen_kwh` ist die Kältemenge — und der einzige
> Zähler, der die *Arbeitszahl Kühlen* möglich macht** (Kältemenge ÷ Kühlstrom).
> Ohne ihn steht dort der Grund statt einer Zahl; geschätzt wird nichts, weil aus
> einem angenommenen Wirkungsgrad genau der Faktor zurückkäme, mit dem gerechnet
> wurde. **Sie heißt bewusst nicht „SEER"** — das ist eine genormte
> Prüfstandsgröße, dies hier ist der Quotient deiner beiden Zähler. Ausführlich:
> [Wärme & Klima §3](HANDBUCH_WAERME_KLIMA.md#3-was-eedc-bewusst-nicht-sagt).

**Mehrere Innengeräte (Multisplit):** Trag sie beim Gerät unter *Innengeräte*
ein (Bezeichnung, z. B. „Büro"). Danach gibt es **jedes** der Felder oben
zusätzlich je Innengerät — der Feld-Key trägt dessen Nummer
(`betriebsart_strom_kuehlen_kwh-3`), das Label den Raumnamen
(„Büro: Strom Kühlbetrieb").

**Vorrang:** Liegt ein Betriebsart-Zähler vor, gilt er — und zwar für **alle**
Betriebsarten dieses Geräts. Die Aufteilung, die eedc sonst aus dem
`betriebsmodus` ableitet, tritt dann zurück; eine Betriebsart ohne Zähler
erscheint unter „nicht aufgeteilt". Steht ein Wert **am Gerät**, schlägt er die
Summe der Innengeräte — beide beschreiben dieselbe Menge, sie werden nie addiert.

> ⚠️ **Was ein Innengerät NICHT misst.** An einem Multisplit hängt **ein**
> Außengerät an mehreren Innengeräten. Was eine Hersteller-App dort als
> Verbrauch eines Innengeräts anzeigt, ist der Anteil des **Außengeräts**,
> zugeschrieben an das gerade **anfordernde** Innengerät — und welches das ist,
> entscheidet die Einschaltreihenfolge. Mitsubishi sagt es selbst:
> *„It is not possible to attribute the output of the outdoor units to specific
> indoor units."* Die belastbare Menge ist ein eigener Zähler am Außengerät.

#### So bekommst du die vier Zähler in Home Assistant

**Weg 1 — Utility Meter (empfohlen, für die kWh-Felder).** Er *zählt* und
übersteht Neustarts; ein Template-Sensor kann das nicht.

1. *Einstellungen → Geräte & Dienste → Helfer → Helfer erstellen → **Utility
   Meter***.
2. **Eingangssensor**: der Energie-Sensor deiner Klimaanlage (kWh).
3. **Tarife**: `heizen`, `kuehlen`, `lueften`, `entfeuchten`.
   HA legt daraus je Tarif einen eigenen zählenden Sensor an.
4. Eine Automatisierung schaltet den aktiven Tarif, ausgelöst vom Zustand der
   `climate`-Entität — Aktion **`select.select_option`** auf die
   `select.…`-Entität, die der Utility Meter mit angelegt hat.
5. In eedc unter *Einstellungen → Datenquellen* die vier Tarif-Sensoren den
   vier Feldern zuordnen.

**Weg 2 — Template-Sensor**, für Momentanwerte und Umrechnungen: Leistung je
Betriebsart (`{{ leistung if modus == 'cool' else 0 }}`), Einheiten- und
Vorzeichenkorrekturen, oder das Zusammenfassen mehrerer Entitäten zu einer.

---

