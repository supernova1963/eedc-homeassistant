## 8. Solcast PV Forecast (optional, ab v3.16.5)

Solcast als dritte Prognose-Quelle wird über die Datenquellen/Anlagenstammdaten angebunden — zwei alternative Pfade. Wie eedc die Solcast-Werte im Vergleich nutzt, steht im [Handbuch Prognosen §2.3](HANDBUCH_PROGNOSEN.md#23-solcast--optional-dritte-meinung).

### Variante A: HA-Integration (BJReplay)

Setzt die [BJReplay Solcast HA-Integration](https://github.com/BJReplay/ha-solcast-solar) voraus. eedc liest die 7-Tage-Prognose direkt als Sensor-State — kein API-Key in eedc nötig.

**Auto-Discovery (v3.16.10):** Sensoren werden über `/api/states` per Suffix-Pattern gematcht:

| Suffix-Pattern | Bedeutung |
|---|---|
| `_heute` / `_today` | Tagesprognose Heute |
| `_morgen` / `_tomorrow` | Tagesprognose Morgen |
| `_uebermorgen` / `_ubermorgen` / `_tag_3` / `_day_3` | Übermorgen |
| `_tag_4` … `_tag_7` / `_day_4` … `_day_7` | Tag 4–7 |

Filter (v3.16.11): nur Sensoren mit `unit_of_measurement=kWh` und ohne „verbleibend"/„remaining" im Namen — sonst würde z. B. `prognose_verbleibende_leistung_heute` fälschlich als Tagesprognose gematcht.

**Stundenprofil:** Kommt aus dem `DetailedForecast`-Attribut der HA-Sensoren (v3.16.13 — vorher fälschlich `detailedHourly` gesucht, was bei Multi-Dach-Anlagen leer war).

### Variante B: Solcast-API (Free/Paid Key)

Direkter API-Aufruf für Standalone-Nutzer ohne HA-Integration. Konfiguration in den Anlagenstammdaten ([Einstellungen → Stammdaten → Solarprognose](HANDBUCH_EINSTELLUNGEN.md#23-solarprognose)). L1-Cache (in-memory) und L2-Cache (DB) überleben Neustarts.

### Slot-Konvention

30-Min-Buckets aus Solcast werden per `ceil(bucket_ende)` dem **Backward-Slot** zugeordnet (siehe [BERECHNUNGEN §6b](BERECHNUNGEN.md#6b-energieprofil-berechnungen-tages-aggregation)). Ein Bucket am Tagesübergang `[23:00, 23:30)` heute landet damit korrekt in Slot 0 des Folgetags.

---

## 8a. eedc-PV-Prognose nach HA exportieren (MQTT / HA-Sensoren)

eedc **exportiert** zusätzlich die eigene PV-Prognose als Sensoren (immer die **eedc**-Quelle, nie Solcast/SFML — die liegen via eigene HA-Integration bereits in HA). Alle Werte stammen aus dem **Prognose-Kanon** und sind damit identisch mit der „eedc"-Spalte im Vergleich.

> ⚠ **Hast du Solcast oder SFML als Prognosequelle gewählt, zeigt *Cockpit → Live* andere Zahlen als diese Sensoren — und das ist Absicht.** Der Block auf dem Bildschirm folgt durchgehend **deiner gewählten Quelle**, damit „bisher erzeugt + verbleibend = heute" wieder aufgeht. Diese Sensoren tragen dagegen weiterhin die **eedc-eigene** Prognose, denn die Solcast-/SFML-Werte liegen über deren eigene HA-Integration ohnehin schon in Home Assistant — ein zweiter Export derselben Zahl wäre nur eine zweite Stelle, an der sie driften kann. Mit der Standard-Quelle (eedc) zeigen beide dieselbe Zahl.

Einrichtung: [Einstellungen → Integration → MQTT-Export](HANDBUCH_EINSTELLUNGEN.md#63-mqtt-export).

Die Sensoren stehen mit Einheit, Formel und Hinweisen in der erzeugten Tabelle [§11 PV-Prognose-Sensoren](#pv-prognose-sensoren-eedc_prognose_).

> ⚠ **Welchen der drei nehme ich?** `…_heute_kwh` beantwortet *was sagt die Vorhersage für
> diesen Tag* — er ist die Zahl, die App, MQTT und Persistenz gemeinsam tragen, und er ändert
> sich nur, wenn OpenMeteo einen neuen Modelllauf liefert. `…_heute_rollend_kwh` beantwortet
> *worauf läuft der Tag tatsächlich hinaus* — er zieht die schon gemessenen Stunden heran und
> reagiert damit auf einen Tag, der besser oder schlechter läuft als vorhergesagt.
> `…_rest_today_kwh` ist der Rest, nachgeführt aus dem gemessenen Vormittag (Attribut
> `nachfuehr_faktor`; `rest_modell_kwh` ist der Rest ohne Nachführung). **Die Differenz
> `…_heute_kwh` − `…_heute_rollend_kwh` ist keine sinnvolle Größe:**
> `…_heute_kwh` enthält für die vergangenen Stunden die *Vorhersage*, nicht die Messung.
>
> **Warum diese Sensoren kein `device_class` tragen.** Sie liefern kWh, sind aber **keine
> Zähler**: eine Tagesprognose springt jeden Tag zurück, und die Summe zweier Prognosen ergibt
> keine sinnvolle Zahl. Home Assistant verlangt für `device_class: energy` genau einen Zähler
> (`state_class` `total`/`total_increasing`) und nimmt Sensoren mit einer anderen Kombination
> **von der Langzeitstatistik aus** — sie zeigen dann einen Wert, ohne dass HA ihn mitschreibt.
> Ohne `device_class` ist `state_class: measurement` zulässig, und HA führt min/mean/max je
> Stunde. Bis v4.0.27 war das falsch gesetzt (gemeldet von rapahl); die Einheit kWh stand und
> steht unverändert am Sensor.

> ⚠ **Wann diese Sensoren „unbekannt" zeigen — und warum das die richtige Antwort ist.**
> eedc holt die Prognose **je Ausrichtung getrennt** (Multi-String-Fan-out): eine Ost- und eine
> Westfläche sind zwei Abrufe, jeder mit eigenem Zwischenspeicher. Fällt einer davon aus —
> Zeitüberschreitung oder Ratenbegrenzung beim Wetterdienst —, liefern die übrigen weiter, und
> die Tagessumme wäre dann **um die fehlende Fläche zu klein**. Statt eine solche Zahl
> auszugeben, lässt eedc den Sensor für diesen Durchgang **leer** (in Home Assistant:
> „unbekannt", s. § *Ein Sensor, der seinen Wert verliert*); beim nächsten Durchgang steht der
> volle Wert wieder da. Betroffen sind `…_heute_kwh`, `…_rest_today_kwh`,
> `…_heute_rollend_kwh` und die Tage +1/+2/+3 samt Stundenprofilen — jeweils nur der Tag,
> dessen Abruf unvollständig war.
>
> **Für Automationen heisst das:** auf `unknown`/`unavailable` prüfen, statt einen Zahlenwert
> vorauszusetzen. Eine Anlage mit nur **einer** Ausrichtung kennt den Fall nicht — dort gibt es
> entweder alles oder nichts. Der gemessene Wert *„PV heute erzeugt"* bleibt in jedem Fall
> stehen: er hängt an keiner Prognose.
>
> Vor v4.0.44 stand hier die zu kleine Zahl, bis der nächste Durchgang sie ersetzte — bei der
> Voreinstellung eine volle Stunde.

> **Hinweis:** Bis v3.45.5 war `eedc_prognose_heute_kwh` „IST bisher + Rest" und wich damit von der App-Anzeige ab. Seit dem Prognose-Kanon trägt der Sensor den **vollen kanonischen Tageswert** (== Anzeige); „Rest heute" ist der reine Rest. Automationen, die auf den alten „IST+Rest"-Wert gebaut haben, sollten auf `…_rest_today_kwh` umgestellt werden, wenn sie den Rest brauchen.

---

