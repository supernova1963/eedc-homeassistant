### Betriebsmodus der Waermepumpe (Zustand statt Zahl)

Der Betriebsmodus traegt **keine Zahl im physikalischen Sinn**, sondern einen Zustand (wie die Zustaende der
E-Mobilitaet weiter unten). eedc versteht dieselben Woerter wie bei einem HA-Sensor und zusaetzlich — nur hier, ueber MQTT — einen **Zahlencode**:

| Code | Wort (Beispiele) | eedc versteht es als |
|---|---|---|
| `0` | `aus`, `off` | Aus |
| `1` | `heizen`, `heat` | Heizen |
| `2` | `warmwasser`, `dhw` | Warmwasser |
| `3` | `kuehlen`, `cool` | Kuehlen |
| `4` | `lueften`, `fan_only` | Lueften |
| `5` | `entfeuchten`, `dry` | Entfeuchten |

Die vollstaendige Wortliste steht im Handbuch Waerme & Klima (Werte-Tabelle) und in *Einstellungen → Datenquellen*
am Feld „Betriebsmodus". `1.0` gilt wie `1`. Jeder andere Wert zaehlt als *unbestimmt* (das Geraet lief, die
Betriebsart ist nicht zuordenbar).

```
eedc/1_Meine_PV/live/inv/7_Vitocal/betriebsmodus → 2
```

- **Senden bei jeder Aenderung genuegt** (retained empfohlen): eedc haelt den letzten Wert, bis ein neuer kommt.
- **Was eedc daraus macht:** den Modus-Chip in *Cockpit → Live* und im Hub, den HA-Sensor/das Export-Topic des
  Modus, und je abgeschlossener Stunde die **Betriebsart-Mitschrift** (Anteil der Stunde je Modus, aus 5-Minuten-
  Fenstern) — daraus „Strom nach Betriebsart" und „Betrieb heute".
- **Grenzen:** Die Mitschrift beginnt mit dem ersten empfangenen Wert und ist **nicht rueckwirkend**. Faellt der
  Broker aus, bleibt die Zeit ohne Verbindung eine Luecke; ein Publisher, der verstummt, waehrend der Broker laeuft,
  behaelt seinen letzten Wert. **Leerlauf** (die HA-Aktion `idle`) gibt es ueber MQTT nicht. Das **Gateway**
  (Fremd-Topic umschreiben) steht fuer dieses Feld nicht zur Wahl (es reicht am Modus nur Zahlen weiter; den Text gibt es
  seit der naechsten Version nur an den Zustandsfeldern der E-Mobilitaet). Die Topic-Abdeckung
  im Daten-Checker ueberwacht das Modus-Topic nicht (ein Modus, der sich stundenlang nicht aendert, ist kein Ausfall).
- **Hat das Geraet in eedc einen HA-Sensor fuer den Modus, gilt der HA-Sensor**; das MQTT-Topic wird dann nicht
  gelesen.

