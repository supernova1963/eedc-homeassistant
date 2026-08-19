# Konzept #263 — Split-Klimaanlagen: Heizen und Kühlen trennen

> ## Status (2026-08-18): **S1 + S2 gebaut · S3 + S4 offen**
>
> **Gernot, 2026-08-18:** den Empfehlungen E-A bis E-E gefolgt, **E-F abgelehnt** (der Schnitt
> bleibt: F-41 und F-42 fahren mit K-2 in **einem** Paket, vor dem nächsten Release).
> Bau-Auftrag: `~/.claude/plans/auftrag-263-k2-bau.md`.
>
> **Dies ist die geltende Fassung.** Sie ersetzt die Fassung vom 2026-08-08 vollständig — jene war
> über zehn Nachträge gewachsen und an drei Stellen mit sich selbst im Widerspruch. Die
> Entstehungsgeschichte (Vermessung am Testgerät, verworfene Zwischenstände, Gegenproben) steht in
> `~/.claude/plans/vorlage-263-k2-s0-bestandsaufnahme.md` und in der Git-Historie dieser Datei;
> **hier steht nur, was gilt.**
>
> Es trägt bewusst **keine Versionsnummer, nur dieses Mess-Datum** — ein Status, der eine Version
> nennt, altert garantiert.
>
> **Nicht auf der Website und nicht in der In-App-Hilfe:** `sync-docs.sh` und `sync-help.sh`
> arbeiten mit Allowlists, in denen Konzepte bewusst fehlen. Dieses Dokument ist Entwickler-SoT.
>
> Issue [#263](https://github.com/supernova1963/eedc-homeassistant/issues/263) · Roadmap-SoT
> [#110](https://github.com/supernova1963/eedc-homeassistant/issues/110).

---

## 1. Das Problem in drei Sätzen

Eine Split-Klimaanlage ist physikalisch eine **Luft-Luft-Wärmepumpe**: dasselbe Gerät heizt im
Winter und kühlt im Sommer, über **denselben** Stromzähler. eedc sieht deshalb nur eine Jahreszahl
„Stromverbrauch" und kann weder sagen, was das Heizen gekostet hat, noch was das Kühlen — und damit
auch nicht, ob sich das Gerät gegenüber der ersetzten Heizung rechnet.

**Die Aufteilung ist nicht aus vorhandenen Feldern rekonstruierbar.** Sie entsteht nur, wenn eedc
den **Betriebsmodus zur Messzeit mitschreibt** und den Verbrauchszuwachs dem dann geltenden Modus
zuschlägt.

---

## 2. Die Datenlage — was am Code und an Testgeräten gemessen wurde

| | Befund | Beleg |
| --- | --- | --- |
| **D1** | **Der Modus ist auslesbar, aber nur als eigene `climate`-Entität.** Er ist der *eingestellte* Modus (`hvac_mode`), nicht der Ist-Betrieb | kingcap1 (Mitsubishi/MELCloud), sechs Screenshots, 2026-08-16 |
| **D2** | **`hvac_action` (Ist-Betrieb) wird NICHT verlangt.** In `melcloud/climate.py` definiert nur `AtwDeviceZoneClimate` (Luft-**Wasser**) die Property; `AtaDeviceClimate` (Luft-Luft) und die Basisklasse nicht. Wer es verlangt, baut für Daikin und sperrt den Rest aus | HA-Core `dev`, 2026-08-17 |
| **D3** | **Der Modus gehört der Anlage, nicht dem Innengerät.** Ein Innengerät auf *Heizen* bei kühlenden anderen tut nichts (2-Rohr-Bauart) ⇒ **ein** Signal je Außengerät genügt | kingcap1s Selbstversuch, 2026-08-16 |
| **D4** | **Der kWh-Zähler ist modus-blind.** Je Gerät genau ein Zähler; Heizen und Kühlen laufen in dieselbe Zahl | ebd. |
| **D5** | **Die Innengeräte-Zähler sind unverwertbar.** Ein Innengerät steht bei 4.115,70 kWh, die ganze Anlage laut Shelly bei 3.190 kWh Lebensdauer ⇒ **K-3 bleibt zu** | ebd. |
| **D6** | **„Aus" ist nicht null:** 10 W Dauerverbrauch (~7 kWh/Monat), weil das Außengerät drei Innengeräte samt WLAN versorgt | kingcap1, 2026-08-17 |
| **D7** | **Es gibt Geräte, die nur kühlen können** (Einhell SKA2500, AN/AUS ohne Inverter). `heizen` darf strukturell fehlen | ebd. |
| **D8** | **Der Sensor-Lesepfad ist durchgängig `float`-only.** `_state_wert_und_einheit → Optional[tuple[float,str]]`, `get_sensor_history → list[tuple[datetime,float]]`, `live_power_service` `float(...)` im `try/except`. Ein `climate`-Zustand wird an jeder Stelle still zu `None`. **Negativbeweis:** `hvac_mode`/`hvac_action`/`betriebsmodus`/`betriebsart` kommen baumweit **0-mal** vor | 2026-08-18 |
| **D9** | **Kein Backfill.** `get_sensor_history` liest den **recorder** (Default-Purge 10 Tage); LTS gibt es nur für numerische Sensoren mit `state_class`, ein `climate`-Zustand hat keine | 2026-08-18 |
| **D10** | **Der Split entsteht nur auf dem Snapshot-Pfad.** `InvestitionMonatsdaten.verbrauch_daten` hat **sieben** Schreiber daneben: `monatsabschluss/wizard.py` · `monatsabschluss/views.py` · `ha_statistics.py` · `custom_import/apply.py` · `import_export/csv_operations.py` · `services/import_writer.py` · `import_export/json_operations.py` | 2026-08-18 |
| **D11** | **In der Praxis werden nur Heizen und Kühlen gefahren.** Entfeuchten/Nur-Lüften nutzt keiner der drei Melder; der Modus wird saisonal manuell gestellt | kingcap1, dietmar1968 |

---

## 3. Zielarchitektur

### 3.1 Grundsatz: die Gesamtmenge bleibt die Wahrheit, die Aufteilung steht daneben

**`stromverbrauch_kwh` bleibt unverändert der Gesamtwert und die einzige Bilanzgröße.** Heizen und
Kühlen sind **Teilmengen daraus** — sie werden ausgewiesen und **nie** aufaddiert.

Diese Bauform ist in eedc bereits Kanon, nicht neu erfunden:

> `services/snapshot/komponenten_beitraege.py:326` — *„`ladung_pv_kwh` / `ladung_netz_kwh` sind
> **Teilmengen** von `ladung_kwh` — **NICHT** zusätzlich addieren (sonst Doppelzählung wie bei
> Gernots Wallbox: 14 + 9,24 = 23,24 statt korrekt 14)."*

Dasselbe beim Speicher (`ladung_netz_kwh`). **`getrennte_strommessung` ist die Ausnahme**, nicht die
Regel: dort gibt es zwei *physische* Zähler und keinen belastbaren Gesamtzähler. Beim Modus-Split
gibt es **einen** Zähler (D4) ⇒ er gehört zur Regel.

**Vier Folgen, alle erwünscht:**

1. **Keine der 28 Read-Sites bricht** — was heute `stromverbrauch_kwh` liest, liest weiter dasselbe.
2. **Der Rest ist abgeleitet:** `nicht_aufgeteilt = Gesamt − Σ Teilmengen`. Er wird **nie
   gespeichert** und ist damit **immer** vollständig — für Altmonate, Ausfälle, Importe und manuelle
   Pflege gleichermaßen. **Es entsteht kein Altdaten-Bruch, er wird nicht abgefedert.**
3. **Fehlt das Modus-Signal, fehlt nur die Aufteilung** — die Menge stimmt weiter.
4. Eine spätere siebte Betriebsart kostet ein Feld, keine Migration.

### 3.2 Die Mengen

| Feld | Bedeutung | Herkunft | in der Bilanz? |
| --- | --- | --- | --- |
| `stromverbrauch_kwh` | **Gesamtstrom des Geräts** | Sensor | **ja — einzige Bilanzgröße** |
| `strom_heizen_kwh` | Teilmenge: Strom im Heizbetrieb | Modus-Split **oder** eigener Zähler | nein (Ausweis) |
| `strom_kuehlen_kwh` | Teilmenge: Strom im Kühlbetrieb | Modus-Split | nein (Ausweis) |
| `modus_abdeckung_h` | Stunden des Monats mit gültigem Modus-Signal | Modus-Split | nein (Qualitätsmaß) |
| `heizenergie_kwh` | **Wärme, die ins Heizen ging** | Wärmemengenzähler **oder** abgeleitet | nein (thermisch) |

**Genau zwei Felder sind neu** (`strom_kuehlen_kwh`, `modus_abdeckung_h`); Negativbeweis: `kuehl`
kommt baumweit **0-mal** vor. `strom_heizen_kwh` existiert und wird von **12 Read-Sites** bereits
angezeigt — es wird wiederverwendet, weil seine Bedeutung identisch ist: *Strom, der ins Heizen ging.*

**Die Summenbildung bleibt an genau einer Stelle** (`core/field_definitions.py::get_wp_strom_kwh`)
und bekommt eine reine Ergänzung, keinen Eingriff:

```
getrennte_strommessung = True   →  Gesamt = strom_heizen + strom_warmwasser   (unverändert)
getrennte_strommessung = False  →  Gesamt = stromverbrauch_kwh
                                   strom_heizen / strom_kuehlen sind Teilmengen daraus
```

⚠ **Warum der bestehende Schalter NICHT wiederverwendet wird:** Er ist an drei Stellen ein hartes
Entweder-Oder, das `stromverbrauch_kwh` verwirft (`get_wp_strom_kwh:1553` · `snapshot/keys.py:303` ·
`komponenten_beitraege.py:317`). Liefe die Klimaanlage darüber, wäre `Gesamt = heizen + kühlen` —
und alles dazwischen fiele **aus der Energiebilanz**, bei kingcap1 die 10 W Standby aus D6. Ohne
Modus-Signal wäre der WP-Strom sogar 0.

### 3.3 Der Betriebsmodus

**Kanon (sechs Werte, für Klassifikation):**
`heizen` · `kuehlen` · `entfeuchten` · `lueften` · `aus` · `unbestimmt`.
`unbestimmt` ist die Automatik-Stellung ohne Ist-Signal (D2) — sie einer Seite zuzuschlagen wäre
eine erfundene Aufteilung.

**Gespeichert werden zwei Mengen plus Rest** (§3.2). Die vier übrigen Klassen fallen bewusst in die
abgeleitete Zeile *„nicht aufgeteilt"* — belegt durch D11. `modus_abdeckung_h` trennt dort die zwei
Fälle, die der Anwender unterscheiden können muss:

* **Abdeckung hoch, Rest > 0** → das Gerät lief in anderen Betriebsarten (Standby, Lüften).
* **Abdeckung niedrig** → eedc hat in dieser Zeit nicht hingesehen.

⚑ `modus_abdeckung_h` ist zugleich die **Zeitbasis, die K-1 (SEER) ohnehin braucht** — sie wird
nicht auf Vorrat gebaut.

**Lesepfad (neu, eng gehalten):** `hvac_action` wird **nicht** verlangt (D2); wo es vorhanden ist,
verfeinert es. Der Lesepfad ist bewusst **kein** generischer Zustandssensor-Umbau: eine feste
Wertemenge, eine Normalisierungstabelle Hersteller→Kanon, sonst nichts. Ein zweiter Anwendungsfall
existiert nicht, und die P-11-Lehre lautet: nicht auf Vorrat bauen.

**Speicherung (der Präzedenzfall steht im Baum):** Der Modus ist ein **Momentanwert je Stunde**, kein
Zähler — er gehört deshalb **nicht** in `sensor_snapshots` (`wert_kwh: Float`, kumulativ,
Boundary-Diff), sondern als eigene Spalte in die Stundenzeile:

```python
# models/tages_energie_profil.py — neben soc_je_speicher
betriebsmodus_je_wp: Mapped[Optional[dict]] = mapped_column(
    JSON(none_as_null=True), nullable=True
)   # {investition_id: "heizen"}
```

Das ist **exakt das N-239-Muster**, mit derselben Begründung: eigene Spalte und **nicht** in
`komponenten` — jenes Dict trägt kW/kWh und wird von Whitelist-Konsumenten summiert; ein
Zustandswert darin wäre die Einheiten-Verwechslung, aus der der BKW-Doppelzählungs-Bug entstand.
`none_as_null=True` ist Bedingung, nicht Geschmack (sonst findet die Altbestands-Erkennung je nach
Herkunft die eine Hälfte nicht).

⚑ **Damit entsteht der Split in derselben Zeile, in der die Menge schon steht:**
`TagesEnergieProfil` führt `komponenten["waermepumpe_<id>"]` als Stunden-kWh je Gerät. Stunde ×
Modus × kWh — mehr braucht die Aggregation nicht.

### 3.4 Die Wärme — ein Feld, eine Bedeutung, zwei Herkünfte

**Eine Luft-Luft-Wärmepumpe liefert dieselbe Heizenergie wie jede andere Wärmepumpe.** Der
Unterschied ist **messtechnisch, nicht physikalisch**: Bei Luft-Wasser geht die Wärme in einen
Wasserkreis, in den ein Wärmemengenzähler passt; bei Luft-Luft direkt in die Raumluft, wo es keinen
Kreis gibt. Das erklärt eine **Häufigkeit, keine Regel** — das Investitionsformular sagt es selbst:
*„Hast du doch einen Wärmemengenzähler an deiner Klimaanlage, ordne ihn weiter zu."*

⇒ **`heizenergie_kwh` wird genutzt, nicht umgangen.** Ein Feld, eine Bedeutung, für jede
Wärmepumpenart. Unterschieden wird über die **Herkunft**, und die Mechanik existiert feldgenau:
`InvestitionMonatsdaten.source_provenance` wird je Feld geführt (Schlüssel wie
`"verbrauch_daten.pv_erzeugung_kwh"`), und bei der PV-String-Verteilung reicht eedc genau diese
Unterscheidung bis in die Anzeige durch (`ist_quelle === 'verteilt'` → *„geschätzt (kWp-Anteil)"*).

| Herkunft | wie | Provenance |
| --- | --- | --- |
| **gemessen** | Wärmemengenzähler | wie bisher |
| **abgeleitet** | `strom_heizen_kwh × JAZ` — nur wenn die JAZ gepflegt ist, **nie** aus einem Default | eigener Marker, bis in die Anzeige durchgereicht |

**Gemessen schlägt abgeleitet** — dasselbe Präzedenz-Muster wie ADR-002/P7 bei der PV.

⚑ **Das ist keine neue Erfindung, sondern die Umkehrung einer Rechnung, die eedc seit jeher macht.**
`core/calculations.py:522` wörtlich: *„das belegt `wp_strom_kwh = gesamt_waermebedarf / jaz` oben
(die JAZ ist als Wärme/Strom definiert)"*. Die ROI-Prognose teilt eine **geschätzte Jahres-Wärme**
durch die JAZ, um auf den Strom zu kommen. Die neue Richtung ist die **genauere**: der Strom ist
gemessen und monatsgenau, die Jahresschätzung war geraten.

### 3.5 Die eine Regel, die daraus folgt

Sie hat nichts mit der Bauart zu tun — sie trennt **teilen von multiplizieren**:

| | darf abgeleitete Wärme verwenden? | Stellen |
| --- | --- | --- |
| **teilt** Wärme durch Strom → JAZ/COP | **nein** — sonst kommt exakt die gepflegte JAZ heraus, eine Zahl, die nichts misst | `dashboards.py:824` · `:967` · `:970` · `cockpit/komponenten.py:203` · `cockpit/uebersicht.py:451` · `ha_export.py:1449` · `pdf/jahresbericht.py:470` |
| **multipliziert** Wärme mit Preis / η / CO₂-Faktor | **ja**, mit Kennzeichnung | `gas_kosten_altanlage` · `co2_wp_ersparnis_kg` · `alternativkosten.py` · `aussichten.py` |

Eine Luft-Wasser-WP **ohne** Wärmemengenzähler fällt unter dieselbe Regel; eine Luft-Luft-WP **mit**
Zähler ist gemessen wie jede andere.

⇒ **Die Klimaanlage wird damit in allen Sichten zur normalen Wärmepumpe** — Kostenvergleich,
Alternativkosten, CO₂, Monatsbericht, HA-Export — nur ohne Warmwasser-Zweig, und die JAZ-Kachel
bleibt „—", solange die Wärme abgeleitet ist. **Ohne eine einzige neue Read-Site.**

---

## 4. Was der Anwender sieht

**Komponenten → Wärme/Klima**, Gerät mit Modus-Signal:

```
Strom gesamt      1.240 kWh
  davon Heizen      520 kWh   (42 %)   → Wärme 1.820 kWh · abgeleitet aus JAZ 3,5
  davon Kühlen      680 kWh   (55 %)
  nicht aufgeteilt   40 kWh   ( 3 %)   → Standby und andere Betriebsarten
Modus erfasst     97 % des Monats
JAZ               —                    (kein Wärmemengenzähler)
```

Ohne Modus-Signal steht dort **nur** die erste Zeile plus *„Betriebsmodus nicht erfasst — die
Aufteilung nach Heizen und Kühlen braucht einen Modus-Sensor"*, mit Weg zur Zuordnungsfläche.
**Keine 0, keine geschätzte Aufteilung** (ADR-002/P4).

**Wirtschaftlichkeit:** Die Heizhälfte wird wie bei jeder Wärmepumpe gegen den ersetzten
Energieträger gerechnet. Die **Kühlhälfte spart nichts** — sie ist Komfortverbrauch und wird als
Kosten ausgewiesen, nicht als Ersparnis. Wer „Nichts ersetzt (Neubau)" gepflegt hat, bekommt für
beide Hälften nur die Kosten.

---

## 5. Grenzen — sie gehören in den Anwender-Text, nicht ins Kleingedruckte

1. ⛔ **Der Split entsteht nur auf dem Snapshot-Pfad** (D10). Wer seine Klimaanlage über den
   Monatsabschluss, den HA-Statistik-Import oder CSV pflegt, bekommt **nie** eine Aufteilung —
   dauerhaft, nicht nur rückwirkend. **K-2 ist ein Feature für Anwender mit Live-Anbindung.**
2. ⛔ **Keine Rückrechnung der Vergangenheit** (D9). Wer den Modus-Sensor heute zuordnet, bekommt
   den Split ab heute. Ein eedc-Ausfall über 10 Tage reißt ein Loch, das bleibt.
3. ⛔ **Nur der eingestellte Modus** (D1/D2). Steht das Gerät auf Automatik, ist die Zeit
   `unbestimmt` und landet in *nicht aufgeteilt* — sie wird **nicht** geraten.
4. ⛔ **2-Rohr-Systeme** (D3). Eine 3-Rohr-Anlage mit Wärmerückgewinnung kann gleichzeitig heizen
   und kühlen; sie wird nicht unterstützt. Weil das Signal an der **Investition** hängt (nicht an
   der Anlage), kostet eine spätere Unterstützung keinen Umbau der Aggregation.
5. ⛔ **Keine Aufteilung je Innengerät** (D5) — K-3 bleibt zu.
6. ⚠ **Geräte, die nur kühlen** (D7), tragen `heizen` nie. Das ist kein Fehler und muss als
   „gibt es hier nicht" erscheinen, nicht als 0.
7. ⛔ **Der Modus ist nur als HA-Sensor zuordenbar, nicht über MQTT** (gemessen bei S1). Der
   Inbound-Parser ist `float(payload)` (`mqtt_inbound_service:74`) — ein Modus-String käme dort
   nicht an. Die Fläche blendet die MQTT-Optionen für dieses Feld deshalb aus (`nur_ha`), und es
   bekommt kein Standard-Topic; sonst stünde im MQTT-Abdeckungs-Check ein Dauer-Hinweis auf ein
   Topic, das niemand bedienen kann (die P-6-Falle).

---

## 6. Etappen

| # | Etappe | Inhalt | Risiko |
| --- | --- | --- | --- |
| **S1** | **Lesen** | Zustandssensor-Pfad in `ha_state_service` (Live **und** Historie), Normalisierung Hersteller→Kanon, Feld `betriebsmodus` in der Zuordnungsfläche (`FELD_BEDARF`, **optional**, für **alle** WP-Arten), Validierung, Daten-Checker-Zeile | ✅ **gebaut 2026-08-18** (s. §8) |
| **S2** | **Mitschreiben** | Spalte `betriebsmodus_je_wp` auf `TagesEnergieProfil`, gefüllt vom **`energie_profil/aggregator`** (Jobs *Heute* alle 15 Min · *Vortag* 00:15 · Recovery 02:15) — **nicht** vom Snapshot-Job, s. §8 | ✅ **gebaut 2026-08-18** |
| **S3** | **Summieren** | Faltung `Stunde × Modus × kWh` je Monat, tagesweise auf die Zählersumme normiert; die zwei Teilmengen + Abdeckung beim Monatsabschluss persistiert; `heizenergie_kwh` abgeleitet mit Provenance-Marke | ✅ **gebaut 2026-08-19** (s. §8) |
| **S4** | **Zeigen** | Aufteilungs-Block im Komponenten-Hub und in Cockpit → Monat/Jahr, zwei HA-Sensoren; „nicht aufgeteilt“ nach §4; die JAZ-Sperre aus §3.5 | ✅ **gebaut 2026-08-19** |
| **S5** | **F-41** | Die drei Daten-Checker-Hinweise dreiteilen (§7, E-C) | klein |
| **S6** | **F-42** | Die vier erfundenen Nullen im Komponenten-Hub (§7, E-D) | klein |

⚠ **Vor S2 gehört eine Messung an einer echten Instanz** — Gernots Anlage hat keine Klimaanlage,
kingcap1 hat MELCloud. Ohne diesen Beleg wird die Hersteller-Vielfalt blind gebaut (#238-Lehre).

✅ **Die drei ungemessenen Sichten sind nachgeholt (2026-08-18, vor S1):**

* **Monatsabschluss-Formular** (`lib/fieldDefinitions.ts:56`): Eine Klimaanlage bekommt
  *Stromverbrauch · Heizwärme · Warmwasser*. Die neuen Größen tauchen dort nicht auf und sollen
  es auch nicht. ⚠ **Aber `strom_heizen_kwh` ist dort bereits belegt** — als **Summand** bei
  `getrennte_strommessung=true`. Derselbe Feldname trägt dann zwei Bedeutungen; **S3 braucht dort
  eine Weiche**, und der Schreibpfad darf das Feld bei getrennter Messung nicht anfassen.
* **Cockpit → Live / Energiefluss** (`live_komponenten_builder.py:97`): Die Klimaanlage ist eine
  Verbrauchs-Komponente. Es gibt dort **schon ein Modus-Icon**, aber auf der Achse
  *Heizen/Warmwasser* aus `leistung_heizen_w`/`leistung_warmwasser_w` — bei einer Klimaanlage
  immer `None`. Saubere Anschlussstelle für S4, kein Eingriff in S1/S2.
* **Jahresbericht-PDF** — ⛔ **neuer Fehler, als eigener Vorgang ausgelagert (F-43, Gernots
  Entscheid 18.08.).** `builders/jahresbericht.py:254` summiert `WpFakten`-Felder mit Default
  `float = 0.0`; das Template rendert `fmt_kwh(0.0)` → **„0 kWh"** (nur `None` ergibt „–"). Eine
  Klimaanlage ohne Wärmemengenzähler bekommt dort drei erfundene Nullen (*Wärmeenergie gesamt ·
  davon Heizung · davon Warmwasser*), während der COP korrekt „–" sagt. **Die F-42-Klasse an
  einer vierten Stelle** — Sitzung A hat sie nicht erwischt, weil das PDF einen eigenen Builder
  hat und nicht die Dashboard-Zusammenfassung liest.

---

## 7. Entscheidungen — **entschieden am 2026-08-18 (Gernot)**

> **E-A bis E-E: den Empfehlungen gefolgt.** **E-F: abgelehnt** — der Schnitt bleibt, F-41 und F-42
> fahren mit K-2 in **einem** Paket vor dem nächsten Release. **Nicht neu aufrollen.**
> Die Empfehlungen stehen unverändert darunter, weil sie die Begründung tragen.

### ✅ E-A — Wird die abgeleitete Wärme persistiert oder bei jedem Lesen gerechnet? — **(a) entschieden**

* **(a) Beim Monatsabschluss persistieren**, mit Provenance-Marker.
* **(b) On-the-fly** aus `strom_heizen_kwh × JAZ`.

> **Empfehlung: (a).** Das ist die **ADR-002/P8-Klasse**: eine on-the-fly gerechnete Wärme schreibt
> bei jeder JAZ-Korrektur die **gesamte Historie** um — genau der Fehler, den P8 für Tarife
> abgeschafft hat („ein Wert trägt den Stichtag seines Monats"). Persistiert trägt jeder Monat den
> damals gültigen Faktor, und die Vergangenheit bleibt stabil.

### ✅ E-B — Wird die Kühlhälfte wirtschaftlich bewertet? — **(a) entschieden**

* **(a) Nein** — Kühlen ist Komfortverbrauch: Kosten ja, Ersparnis nein.
* **(b) Ja**, gegen ein hypothetisches Vorgängergerät.

> **Empfehlung: (a).** (b) verlangt eine Angabe, die praktisch niemand hat, und erzeugt genau die
> Sorte konstruierter Ersparnis, die K-0b/N-87 abgeschafft haben. **eedc ist nicht die
> Strom-Polizei**: der Kühlstrom wird gezeigt und bepreist, aber nicht bewertet.

### ✅ E-C — F-41: die drei Daten-Checker-Hinweise werden **dreigeteilt**, nicht umgehängt — **entschieden**

Gemessen (2026-08-18): `stammdaten.py:1007` gated **eine** Prüfung auf die **Bauart**
(`ist_luft_luft_waermepumpe`) und leitet daraus **drei** Hinweise ab. Das ist an zwei Stellen falsch:

| Hinweis | hängt am Feld | das Feld speist | die richtige Frage |
| --- | --- | --- | --- |
| **Alternativkosten (Gas-/Ölheizung) fehlen** (WARNING) | `anschaffungskosten_alternativ` (Spalte) | `core/berechnungen/investitionskosten.py::relevante_kosten_aus_investitionen` — `Σ max(0, gesamt − alternativ)` ⇒ **USt-Bemessungsgrundlage · Amortisations-Fortschritt · Amortisationsdauer** | *„Was hättest du stattdessen kaufen müssen?"* — **hat mit Ersetzen nichts zu tun.** Ein Neubau ersetzt keine Heizung, hat aber trotzdem keinen Gaskessel gekauft |
| Alter Energiepreis nicht gesetzt (INFO) | `alter_preis_cent_kwh` | laufende Kosten der **ersetzten** Anlage | `ersetzt_keine_heizung()` |
| Heizwärmebedarf nicht gesetzt (INFO) | `heizwaermebedarf_kwh` | Einsparungsschätzung gegen die ersetzte Anlage | `ersetzt_keine_heizung()` |

**Negativbeweis:** In `investitionskosten.py` und allen weiteren Lesestellen von
`anschaffungskosten_alternativ` kommt `alter_energietraeger`/`ersetzt_keine_heizung` **0-mal** vor.
Die beiden Achsen berühren sich nirgends.

> **Empfehlung:**
> **(a)** Die zwei **INFO** hängen künftig an `ersetzt_keine_heizung()` statt an der Bauart. Damit
> ist der Falsch-positiv für **jede** Neubau-Wärmepumpe weg und der Falsch-negativ für die
> **heizende** Klimaanlage ebenfalls.
> **(b)** Die **WARNING** wird von **beiden** Achsen gelöst — sie fragt nach der vermiedenen
> Investition und gilt für jede Wärmepumpe. Was sich ändert, ist **Text und Weg**: der Hinweis nennt
> **0 als gültige Antwort**, und `investitionFormHelpers.ts:147` bekommt denselben Zusatz, den fünf
> andere Investitionstypen längst tragen (*„Meist 0 — es gibt keine echte Alternative"*).
> ⚑ **An der Testinstanz belegt:** eine **0** in *Alternative Kosten (€)* lässt die Warnung
> verschwinden (`stammdaten.py:1009` prüft `is None`). Der Defekt ist **Beschriftung, nicht
> Unauflösbarkeit** — die frühere Darstellung war an dieser Stelle zu breit.
> **(c)** Für den Altbestand wird **keine neue Mechanik erfunden**: `crud.py:969` trägt die Brücke
> bereits (die exakt unveränderte Vorbelegung 12.000/3.000 zählt als offene Frage, nicht als
> Antwort). Der Checker benutzt dasselbe Prädikat.
>
> ⚠ **Zwei `ist_luft_luft`-Stellen bleiben bewusst unverändert** (`daten_checker/energieprofil.py:419`,
> `daten_checker/monatsdaten.py:848`) und ebenso `field_definitions.py:722`: sie fragen nach einem
> **Wärmemengenzähler**, den ein Splitgerät physisch nicht hat — **Messbarkeit → Bauart,
> Bewertbarkeit → Pflege.**

### ✅ E-D — F-42: die vier erfundenen Nullen im Komponenten-Hub — **entschieden, als S6**

Gemessen an einer Testinstanz mit echter Klimaanlage: 4.375 kWh Strom, kein Wärmemengenzähler,
„nichts ersetzt" ⇒ *Komponenten → Wärme/Klima* zeigt `JAZ 0,00` · `Stromkosten 0,00 €` ·
`Gas/Öl 0,00 €` · `Ersparnis 0,00 €`, dazu die Blöcke *„CO₂-Ersparnis 0 kg vs. fossile Heizung"*
(Guard ist `!= null`, `0.0` ist nicht `null`) und *„Kostenvergleich WP vs. Gas/Öl"* (**ohne jeden
Guard**). **Dieselbe Anlage sagt in *Cockpit → Jahr* `None` („—") und in *Auswertungen → ROI*
„nicht bewertet".**

Ursache: `services/wp_wirtschaftlichkeit.py:105/115` gibt beim Frühausstieg auch
`wp_kosten_euro = 0` zurück — *Strom × Preis* hat mit der ersetzten Heizung aber nichts zu tun.

> **Empfehlung: als eigene Etappe S6 mitbauen.** Es ist die **N-258-Klasse** („nicht bewertet heißt
> keine Zahl"), die v4.0.17 an der ROI-Tabelle behoben hat und die im Hub stehengeblieben ist — und
> es ist eine **nicht eingelöste Zusage**: Forum T77723 **#550** (16.05.2026) sagt alex_s9027 zu,
> die JAZ-Kachel bleibe *„sauber leer („—")"*. Für *Cockpit* stimmt das, für den Hub nicht.
> ⚑ Mit §3.4/§3.5 löst sich der größere Teil ohnehin auf: sobald die Klimaanlage eine (abgeleitete)
> Wärme und echte Stromkosten trägt, sind drei der vier Nullen keine Nullen mehr.

### ✅ E-E — Wem wird das Modus-Feld angeboten? — **(a) entschieden: jeder Wärmepumpe**

* **(a) Jeder Wärmepumpe**, optional.
* **(b) Nur `wp_art = luft_luft`.**

> **Empfehlung: (a).** (b) baut an genau der Gruppe vorbei, die das Thema meldet: azywietz-webs
> zwei Klimaanlagen laufen als `luft_wasser`, weil das Feld „Wärmepumpenart" als
> **Community-Einstellung** beschriftet ist (*„Wird für den fairen JAZ-Vergleich in der Community
> verwendet"*), obwohl es die gesamte Wärmemengen-Erwartung des Daten-Checkers steuert. Es gibt
> außerdem Luft-Wasser-Wärmepumpen **mit** Kühlfunktion. Kosten von (a): null.
> ⚑ **Der Feld-Hinweis wird bei dieser Gelegenheit mitgeändert** — er beschreibt heute die
> Nebenwirkung und verschweigt die Hauptwirkung.

### ⛔ E-F — Der Schnitt: fährt F-41 wirklich mit K-2 mit? — **ABGELEHNT, der Schnitt bleibt**

Der Entscheid vom 18.08. lautete *„F-41 nicht einzeln bauen, sondern mit K-2 mitziehen — an
derselben Stelle zweimal hintereinander aufzureißen, hat noch nie gut funktioniert."*

> **Empfehlung: den Entscheid revidieren — F-41 und F-42 vorziehen, K-2 danach.**
>
> **Begründung, und sie ist eine Messung, kein Zeitargument:** Die Prämisse „dieselbe Stelle" hält
> nach §3 **nicht mehr**. F-41 sitzt in `daten_checker/stammdaten.py` und fragt nach der
> **Bewertbarkeit** (`alter_energietraeger`, `anschaffungskosten_alternativ`); K-2 sitzt im
> Snapshot-/Aggregations-Pfad und in der **Messbarkeit** (`betriebsmodus`). Sie berühren sich in
> **keiner Funktion** — der Daten-Checker-Anteil von K-2 ist eine **neue** Zeile („Modus-Sensor nicht
> zugeordnet"), nicht eine Änderung an den drei bestehenden. **Ein Präzedenzfall trägt nur so weit
> wie seine Begründung, und diese trägt hier nicht.**
>
> **Was das löst:** F-41 ist als Fehler klassifiziert und sperrt damit über die stehende Regel
> („kein Release, solange ein gemeldeter Fehler offen ist") **jedes** Release — auch die bereits
> gebauten F-38/F-39/F-40, auf die drei Melder warten. F-41 + F-42 sind **klein, unabhängig und in
> einer Sitzung baubar**. Danach ist das Release frei, und K-2 wird **ohne selbst erzeugten
> Zeitdruck** gebaut — was einem Bau dieser Größe zusteht.
>
> ⚠ **Die Gegenrichtung ehrlich benannt:** azywietz-web hat für #383 ausdrücklich **keine** Zusage
> zum Zeitplan bekommen, sondern die Auskunft, der Fix fahre mit #263 mit. Ihn früher zu bedienen
> ist eine positive Abweichung — sie sollte im Release-Text stehen, damit die frühere Aussage nicht
> unkommentiert überholt wird.
>
> ⛔ **Entscheid Gernots (2026-08-18): abgelehnt.** Der Schnitt bleibt — **ein** Paket, und es geht
> vor dem nächsten Release raus. Damit hält die Auskunft an azywietz-web wortgleich, und die
> Melder-Punkte F-38/F-39/F-40 warten auf dasselbe Release. **Baureihenfolge frei:** S5/S6 zuerst
> ist zulässig und empfohlen (klein, melder-relevant, risikofrei) — das ändert den Schnitt nicht.

### ✅ E-G — Eigene Feldnamen statt Wiederverwendung von `strom_heizen_kwh` — **entschieden (2026-08-19)**

`modus_strom_heizen_kwh` · `modus_strom_kuehlen_kwh` · `modus_abdeckung_h`.

> **Das revidiert §3.2**, wo die Wiederverwendung von `strom_heizen_kwh` empfohlen war („seine
> Bedeutung ist identisch"). Am Code gemessen hält die Begründung nicht: Die zwölf Read-Sites
> zeigen das Feld nicht als *Teilmenge*, sondern als **Summand unter getrennter Strommessung** —
> und **drei** Stellen leiten aus seiner bloßen *Anwesenheit* ein Verhalten ab.
> `investitionen/dashboards.py` (`if 'strom_heizen_kwh' in d`) setzt daraufhin
> `hat_getrennte_strom` und liefert `cop_heizen`; daran hängt `WaermepumpeHubBloecke.tsx`
> (`hatGetrennteStrom`). Mit abgeleiteter Wärme (§3.4) stünde dort als „JAZ" **exakt die
> gepflegte JAZ** — der §3.5-Verstoß, gegen den S3 gebaut ist.
>
> Eigene Namen machen die Kollision **strukturell** unmöglich, statt sie an vier Stellen
> abzufangen; eine WP mit getrennter Messung **und** Modus-Sensor behält beide Angaben
> nebeneinander. Kosten: drei neue Feldnamen. **Nebenbei wird §3.2s „Ergänzung im `False`-Zweig
> von `get_wp_strom_kwh`" gegenstandslos** — der Zweig addiert schon heute nichts.
>
> ⚑ **Die Namen sind an den Kanon gebunden, nicht frei gewählt:**
> `test_263_k2_modus_split.py::test_feldnamen_folgen_dem_kanon` hält `MODUS_STROM_FELD` gegen
> `AUFGETEILTE_MODI` — für jeden aufgeteilten Modus genau ein Feld, Name
> `modus_strom_<modus>_kwh`. Eine siebte Betriebsart kostet damit **einen Eintrag im Kanon**, und
> der Wächter sagt sofort, was dazu fehlt. Ohne ihn wäre §3.1/Folge 4 eine Behauptung.

### ✅ E-H — Zählertreue Normierung, Invariante statt Kappung — **entschieden (2026-08-19)**

Die Stundenform kommt aus `TagesEnergieProfil.komponenten` (Leistungspfad), die **Menge** je Tag
aus `TagesZusammenfassung.komponenten_kwh` (Zählerpfad). Präzedenz: v3.45.5 Live-Tagesverlauf —
*„nur die Kurvenform fällt auf den Leistungssensor zurück, die Stunden-Energie bleibt
zählertreu"*.

> **Die Normierung ist die Verbesserung, die Invariante ist der Schutz.** Die Zählersumme je
> Gerät ist **nicht garantiert vorhanden** (`get_komponenten_tageskwh` sagt das selbst; an der
> Demo-Box ist `komponenten_kwh` über alle Tageszeilen `NULL`). Wo sie fehlt, gilt die Roh-Summe
> — und was `Σ Teilmengen ≤ Gesamt` dann hält, ist allein die Regel im Schreibpfad:
> **Summe > Gesamtwert ⇒ gar nichts schreiben** und einen vorhandenen Split **wegräumen**, nicht
> kappen. Eine stille Kappung machte aus einem Widerspruch eine plausibel aussehende Zahl.
> Auslöser sind zwei reale Fälle: die Achse-2-Drift zwischen den zwei Pfaden (#356, bei der
> Wallbox einmal Faktor ≈ 2) und der nachträglich kleiner gepflegte Monatswert. Letzterer bekommt
> im Daten-Checker einen auflösbaren Hinweis mit zwei Wegen.
>
> **Keine Hochrechnung:** Stunden ohne Modus-Signal tragen zu keiner Teilmenge bei, ihre Menge
> gehört aber in den **Nenner** der Normierung. ⛔ Das war im ersten Bau falsch und ist erst an
> einer Instanz aufgefallen: der SQL-Filter `betriebsmodus_je_wp IS NOT NULL` hatte die
> Standby-Stunden auch aus dem Nenner entfernt, wodurch die erfassten Stunden auf die volle
> Tagesmenge hochgerechnet wurden und „nicht aufgeteilt" **0** ergab statt 6,4 kWh. Der Lader
> wählt deshalb **Tage** über die Modus-Spur aus und lädt **Stunden** vollständig.
>
> ⛔ **Zweiter Fund derselben Messung: der Bezug der Restmenge.** `Gesamt − Σ Teilmengen` ist nur
> **je Gerät** richtig. Auf Anlagenebene wies eine Anlage mit Klimaanlage (191,2 kWh, mit Split)
> **und** Luft-Wasser-WP ohne Modus-Sensor (90 kWh) „nicht aufgeteilt 96,4 kWh" aus — 90 davon
> gehörten dem anderen Gerät. Bezug ist deshalb `WpFakten.modus_strom_bezug_kwh`, der Strom
> **nur der Geräte mit Split**.

### ✅ E-I — Ein Lader, zwei Aufrufer; persistiert mit `auto:monatsabschluss` — **entschieden (2026-08-19)**

Reine Faltung in `core/berechnungen/modus_split.py` (ADR-001), Lader in
`services/energie_profil/modus_split_monat.py`, Schreiber als **Schritt 4** in
`run_post_monatsabschluss_aggregation` (nach dem Backfill — er liest dessen Stundenzeilen).

> **Ein Lader, zwei Aufrufer** ist Bedingung, nicht Ordnungsliebe: Einen automatischen
> Monatsabschluss gibt es in eedc nicht (`monats_aus_tagen.py` sagt es im Modul-Kopf), der
> **laufende** Monat hat also nie eine gespeicherte Aufteilung. Wer nur den Schreibpfad baut,
> zwingt die nächste Sitzung zu einer zweiten Faltung daneben — die Drift-Klasse, gegen die
> dieses Projekt seit zehn Vorfällen arbeitet.
>
> ⚑ **„Gemessen schlägt abgeleitet" braucht keine Sonderregel:** `auto:monatsabschluss` ist
> `SourcePriority.AUTO_AGGREGATION` (3), `MANUAL` ist 1 und `EXTERNAL_AUTHORITATIVE` 2 — beide
> schlagen den Schreiber. Wer einen Wärmemengenzähler zuordnet oder die Heizwärme von Hand
> pflegt, behält seinen Wert **per Konstruktion** (Präzedenz ADR-002/P7 bei der PV).
>
> ⚠ **Der Preis von E-A, ausgesprochen:** Persistiert trägt jeder Monat den damals gültigen
> Faktor — eine *korrigierte* JAZ heilt alte Monate deshalb **nicht**. Das gehört in den
> Anwender-Text.

### ✅ E-B — Nachtrag: die Kühlhälfte war noch im Vergleich — **korrigiert (2026-08-19)**

E-B stand seit dem 18.08. („Kosten ja, Ersparnis nein"), war im Bau aber zunächst **nicht
umgesetzt**. An einer eigenen Instanz gemessen (Klimaanlage, Juni: 26,4 kWh Heizen · 158,4 kWh
Kühlen · Gas ersetzt): **Ersparnis −45,04 €** und **CO₂ −52 kg** — die Formeln stellten die
Stromkosten des *Kühlens* gegen die vermiedenen Gaskosten des *Heizens*.

> Kein Rechenfehler, sondern ein **Kategorienfehler**: Kühlen ersetzt keine Heizung; ohne die
> Klimaanlage gäbe es schlicht keine Kühlung. `berechne_wp_ersparnis` und `co2_wp_ersparnis_kg`
> nehmen den Kühlstrom jetzt aus dem Vergleich (Parameter `strom_kuehlen_kwh`, Default 0.0 ⇒
> Verhalten ohne Split unverändert); die Kosten bleiben in `wp_kosten_euro` und werden als
> `kuehl_kosten_euro` eigens ausgewiesen. **Gegenmessung: +2,48 € und +8,2 kg**, die
> Luft-Wasser-WP derselben Anlage unverändert (1.290,43 € · 2.744,3 kg).

---

## 8. Maßnahmen-Register

| ID | Maßnahme | Status | Anmerkung |
| --- | --- | --- | --- |
| **K-0** | Subtyp `wp_art = luft_luft` · SCOP-Modus · Stromsensor genügt · Daten-Checker verlangt keine Heizwärme | ✅ **gegen den Code geprüft (2026-08-18)** | alle vier belegt: `WP_ART_OPTIONEN`, `effizienz_modus == "scop"`, `KLIMA_OHNE_WAERMEMENGE`, `energieprofil.py:419`, `monatsdaten.py:848` |
| **K-0b** | Klimaanlage als Verbraucher statt halbe Wärmepumpe | ✅ ersetzt durch K-0c | — |
| **K-0c** | Die Bewertung hängt an der **Pflege**, nicht an der Bauart (`alter_energietraeger = "nichts"`) | ✅ **durchgezogen — Rechnung (7 Stellen) UND Daten-Checker (S5, 2026-08-18)** | Der Satz „Typ-Sonderweg entfällt" gilt weiterhin **nicht** uneingeschränkt: er bleibt in `crud.py:969` als **Altbestandsschutz** (begründet). An den drei **Messbarkeits**-Stellen (`field_definitions.py:722` · `energieprofil.py:419` · `monatsdaten.py:848`) bleibt die Bauart bewusst maßgeblich. Gemessen an einer Instanz mit zwei Varianten: vorher Klima 0 / Neubau-WP 3 Meldungen, nachher **beide nur die WARNING** (auflösbar) |
| **F-41** | Die drei Daten-Checker-Hinweise dreiteilen (§7 E-C) | ✅ **gebaut (S5, 2026-08-18)** | Zwei INFO an `ersetzt_keine_heizung`, WARNING von beiden Achsen gelöst + Text nennt 0 als Antwort, Formular-Hint nachgezogen. Wächter `test_f41_f42_klima_bewertbarkeit.py` (12 Proben zu F-41, DB-Weg statt Stub) |
| **F-42** | Die vier erfundenen Nullen im Komponenten-Hub (§7 E-D) | ✅ **gebaut (S6, 2026-08-18)** | Gelöst **im Backend** statt im Client: `WPErsparnisErgebnis.bewertbar` + `None` statt `0` in der Dashboard-Zusammenfassung. Der Auftrag nannte einen Frontend-Guard — gemessen waren **drei** Konsumenten derselben Null (Hub · *Cockpit → Aussicht* · Kostenvergleich), ein Client-Guard hätte einen davon geheilt. `wp_kosten_euro` wird echt (gemessen 1.340,50 €) |
| **K-1** | **SEER** (Kühl-Effizienz) | ⬜ offen, **nach K-2** | Negativbeweis: `seer` kommt baumweit **0**-mal vor. Ohne getrennte Kühl-kWh ein Faktor ohne Bezugsgröße; `modus_abdeckung_h` liefert die Zeitbasis |
| **K-2** | **Heizen/Kühlen-Trennung** | ✅ **S1–S4 gebaut (2026-08-18/19)** | Vorbedingung „Testgerät mit Modus-Sensor“ seit 2026-08-16 erfüllt (kingcap1, MELCloud). Sitzung A (S5+S6), Sitzung B (S1+S2), Sitzung C (S3+S4). **Mit Fixtures und einer eigenen Instanz abgenommen, nicht an einem Gerät** — es gibt keins im Zugriff. Die drei Entscheide der Sitzung C stehen unter §7 als **E-G · E-H · E-I** |
| **S1** | **Lesen** — Kanon, Zustands-Lesepfad, Feld, Daten-Checker-Zeile | ✅ **gebaut (2026-08-18)** | Neu `core/betriebsmodus.py` (sechs Kanon-Werte, Normalisierung HA→Kanon, `hvac_action` verfeinert wo vorhanden). `ha_state_service.get_zustand_history` steht **neben** dem float-Pfad — `get_sensor_history` unverändert (D8). Feld `betriebsmodus` in `LIVE_FELDER_INV`, `FELD_BEDARF` optional für **jede** WP-Art (E-E), SoT-Markierung `zustand: True` steuert **drei** Weichen statt drei verstreuter `if`. ⛔ **Ein Befund, der in keinem D-Punkt stand:** `datenquellen.py::_ha_sensor_relevant` verwarf jede Nicht-`sensor.`-Entity **unbedingt** (der Test steht vor `filter_energy`) — der Modus-Sensor war damit **gar nicht auswählbar**, egal wie gut der Lesepfad ist. Neue Kategorie `KLIMA_MODUS_SENSOR` (INFO, nur `luft_luft` — Gernots Entscheid 18.08.); N-280 mitgelöst |
| **S2** | **Mitschreiben** — Stundenzeile trägt den Modus | ✅ **gebaut (2026-08-18)** | Spalte `betriebsmodus_je_wp` (N-239-Muster, `none_as_null=True`), gefüllt von `_get_betriebsmodus_history` im **`energie_profil/aggregator`**. ⛔ **Nicht wie beauftragt:** Der Auftragssatz „5-Minuten-Snapshot hält den Modus, die :05/:55-Aggregation schreibt ihn" hält an **beiden** Enden nicht — der 5-Min-Job steht hinter `LIVE_SNAPSHOT_5MIN_ENABLED` (Default **aus**, `run.sh`) und liest HA short_term_statistics (kein `climate` darin); die :05/:55-Jobs schreiben `sensor_snapshots` (kWh-Zähler), nicht diese Tabelle. Wörtlich gebaut wäre der Split bei Default-Konfiguration **still leer** geblieben. ⚑ **Eine Regel, die eine SoC-Kopie falsch gemacht hätte:** ein Zustand hat eine **Dauer** — je Stunde gewinnt die längste Verweildauer, nicht der Mittelwert und nicht der letzte Wert; der letzte Punkt **davor** trägt fort (HA schreibt nur bei Änderung, D11) |
| **S3** | **Summieren** — Teilmengen, Abdeckung, abgeleitete Wärme | ✅ **gebaut (2026-08-19)** | Neu `core/berechnungen/modus_split.py` (reine Faltung, volles Kanon-Dict ⇒ K-1 wird ein Lesevorgang) + `services/energie_profil/modus_split_monat.py` (**ein** Lader, zwei Aufrufer: Schreiben beim Abschluss, Lesen für den laufenden Monat — einen automatischen Monatsabschluss gibt es nicht) + `modus_split_schreiben.py` (Schritt 4 in `run_post_monatsabschluss_aggregation`). ⛔ **Der Auftrag nannte den falschen Ort:** `imd_monatsaggregat` ist ein reiner Per-Zeilen-Resolver über `verbrauch_daten` **ohne** Zugriff auf Stundenzeilen (zweite Auftrags-Korrektur nach S2). ⛔ **Und `get_wp_strom_kwh` brauchte gar keinen Eingriff** — sein `False`-Zweig addiert schon heute nichts |
| **S4** | **Zeigen** — Aufteilungs-Block, HA-Export, JAZ-Sperre | ✅ **gebaut (2026-08-19)** | Komponenten-Hub (§4-Block, Wärme mit Herkunfts-Satz) · Cockpit → Monat/Jahr · zwei HA-Sensoren (`wp_strom_heizen_modus_kwh`/`…kuehlen…`; ohne Modus **abwesend** statt 0) · JAZ-Sperre an allen **sieben** §3.5-Stellen über `WpFakten.jaz_belastbar` bzw. `heizwaerme_ist_abgeleitet`. Farb-SoT um `kuehlung`/`nicht_aufgeteilt` erweitert (Regel 0a, Fall 2). **N-282 entschieden und NICHT gebaut** — s. eigene Zeile |
| **N-282** | Live-Modus-Icon auf der Achse Heizen/**Warmwasser** | ✅ **entschieden: bleibt** (2026-08-19) | Bei einer Klimaanlage sind beide Leistungsfelder `None`, das Icon bleibt leer — **keine Falschaussage, sondern „keine Aussage“**. Den echten Modus zu zeigen hieße, ihn in den Live-Poller zu holen; S1 hat ihn dort **bewusst** ausgeschlossen (`normalize_to_w` ergibt für einen `climate`-State garantiert `None` ⇒ Dauerabruf alle 5 s ins Leere). Ein Symbol ist das nach der L-1-Entlastung nicht wert; die Begründung steht an der Fundstelle im Code |
| **K-3** | Aufteilung **je Innengerät** | ⛔ **zu** | D5 — die Innengeräte-Zähler sind unverwertbar |

> ⚑ **Wer hier eine Maßnahme auf ✅ setzt, misst vorher — und zwar Rechnung *und* Prüfung getrennt.**
> Das ist zweimal schiefgegangen: K-0 trug „Fundament steht" (⇒ N-86) und K-0c trug „Typ-Sonderweg
> entfällt" (⇒ F-41), beide ohne dass es jemand gegen den Code gehalten hatte.

---

## 9. Abnahme

* Gates vollständig: beide Zeitzonen (`TZ=UTC`), `lint` vor `tsc`, alle `check:*` über den Exit-Code.
* **Je Etappe ein Sprengsatz, einzeln gefahren.** Bei S2 ausdrücklich einer, der die
  **Modus-Zuordnung** aushebelt, nicht nur die Summe — *bei falscher Zuordnung bleibt die Summe
  gleich*, ein Summen-Prüfer wäre stumm.
* Ein Wächter, der die **Teilmengen-Invariante** hält: `Σ (strom_heizen + strom_kuehlen) ≤
  stromverbrauch_kwh`, und dass keine Bilanz-Read-Site die Teilmengen addiert.
* Ein Wächter für §3.5: keine JAZ/COP-Stelle rechnet mit abgeleiteter Wärme.
* Doku: dieses Konzept auf dem gemessenen Stand, `HANDBUCH_DATEN_CHECKER.md` §4.6 (✅ **korrigiert
  2026-08-18** — der Text behauptete, die drei Hinweise versorgten „ausschließlich die
  Ersparnis-Rechnung", und stellte die Ausnahme auf die Bauart; beides trägt jetzt einen
  Korrektur-Vermerk), `BERECHNUNGEN.md`, CHANGELOG + WAS-IST-NEU unter `[Unreleased]`.
* **Die Grenzen aus §5 gehören in den Anwender-Text**, nicht nur in den Commit.

---

## 10. Bezug

* Issue [#263](https://github.com/supernova1963/eedc-homeassistant/issues/263) — Melder **3dmaster90**
  (Eröffnung), **kingcap1** (Testgerät Mitsubishi/MELCloud + Einhell).
* Issue [#383](https://github.com/supernova1963/eedc-homeassistant/issues/383) — **azywietz-web**,
  Midea PortaSplit + Panasonic Multisplit ⇒ **F-41**.
* Forum **T77723 #548** (2026-05-15) — **alex_s9027**, zwei Split-Klimas; hat die Heizen/Kühlen-
  Trennung dort zuerst gefordert. ⚠ Das ist ein **Forum**-Beitrag; die frühere Notiz „Discussion
  #548" ging ins Leere (der Vorgang existiert auf GitHub nicht).
* Forum **T89667 #87/#92** — **dietmar1968**: ein Gesamtzähler, **kein** Modus-Signal ⇒ seine Anlage
  ist der Beleg für Grenze §5.1, nicht für die Machbarkeit.
* Roadmap-SoT [#110](https://github.com/supernova1963/eedc-homeassistant/issues/110).
* **Keine eedc-community-/Datenmodell-Synchronisation nötig** (rein lokal) — `wp_art` geht bereits
  in den anonymen Datensatz, die Modus-Aufteilung nicht.
