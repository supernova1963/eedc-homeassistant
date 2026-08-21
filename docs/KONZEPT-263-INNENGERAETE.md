# Konzept #263 — Innengeräte einer Luft-Luft-Wärmepumpe

> **Status:** Entwurf, 2026-08-20, fortgeschrieben 2026-08-21.
> **Gebaut ist bisher nur Etappe F** (§6) — alles Übrige ist Plan.
> Basis ist der ausgelieferte Stand **v4.0.23**.
> **Vorgänger:** [`KONZEPT-263-klima-split.md`](KONZEPT-263-klima-split.md) — gilt unverändert
> weiter für alles, was dort steht und gebaut ist (Teilmengen-Grundsatz, Sechser-Kanon,
> `modus_abdeckung_h`, Persistenz beim Monatsabschluss, E-G/E-H/E-I). **Eine** Zeile davon ist
> widerlegt, und die trägt die Datenstruktur.

---

## 1. Der Fehler im Vorgänger

Das alte Konzept schließt aus **D3**:

> *„Der Modus gehört der Anlage, nicht dem Innengerät ⇒ **ein** Signal je Außengerät genügt."*

Der Vordersatz stimmt, der Schluss nicht. Dass das Außengerät nur einen Modus fährt, heißt nicht,
dass ein **beliebiges** Innengerät ihn verrät — ein ausgeschaltetes sagt gar nichts. eedc zieht
heute eine Stichprobe von einem Gerät und behandelt sie als Aussage über die Anlage.

---

## 2. Die Datenlage — an drei Anlagen gemessen, 15.–20.08.2026

| | Befund | Beleg |
| --- | --- | --- |
| **E1** | **Ein Innengerät kann „Aus" sein, während ein anderes kühlt** — *Vic-Schlafzimmer* = Aus, *Klima Glen Büro* = Kühlbetrieb, dieselbe Anlage, dieselbe Minute | kingcap1, 15.08. |
| **E2** | **Der Ist-Betrieb (`hvac_action`) existiert je Innengerät** — Panasonic führt *„Aktuelle Aktion: Leerlauf"*, während der eingestellte Modus `cool` ist | Klausnn, 20.08. |
| **E3** | **Ein Kältekreis ⇒ das zuerst eingeschaltete Innengerät bestimmt den Modus**, alle weiteren folgen oder tun nichts | Klausnn, 20.08. |
| **E4** | **Es gibt Mehrkreis-Multisplits** — dort heizen und kühlen Innengeräte gleichzeitig und unabhängig | ebd. |
| **E5** | **Jede Energiegröße an einem Innengerät ist ein Außengerätewert.** Mitsubishi: *„It is not possible to attribute the output of the outdoor units to specific indoor units."* Panasonic: alle Innengeräte tragen dieselben Energie-Sensoren. Und beide nennen es selbst eine Schätzung — Daikin *„estimated"*, Panasonic *„Extrapolated Power"* | MELCloud-Handbuch S. 56 · Klausnn 20.08. · `daikin/strings.json` |
| **E6** | **Innengerätespezifisch ist nur der Zustand:** Raum-Ist, Soll, Modus, Lüfterstufe, Lamellen. Klausnn unabhängig: *„das sind sie nicht, bis auf die Inside Temperatur"* | alle drei Melder |
| **E7** | **Die Recorder-Tiefe variiert** — OB73-gif konnte 90 Tage nachimportieren; D9 („kein Backfill") gilt nur für den Default | OB73-gif, 20.08. |
| **E8** | **Der ausgelieferte Lesepfad verliert `hvac_action`** (s. §6) | 20.08., am Code gemessen |
| **E9** | **Es gibt einen lokalen Weg mit deutlich mehr Daten.** `pymitsubishi/homeassistant-mitsubishi` spricht die WLAN-Adapter der Innengeräte **direkt** an (je eigene IP) — **17 Entitäten** statt 4, darunter **`Power` in Watt (live)**, `Operating Status` („In Betrieb"), Inside Temperature *coarse* **und** *fine*, Outside Temperature, Dehumidifier Level, Vane-Stellungen. Der `Energy`-Zähler trägt denselben Wert wie MELCloud (4.130,90 gegen 4.115,70 fünf Tage zuvor) ⇒ **dieselbe Quelle, nur ohne Cloud** | kingcap1, 20.08. |
| **E10** | **Der Verbrauch hängt am anfordernden Gerät, nicht am Raum.** *„Das erste Gerät, was angeschaltet wird, gibt den Takt an … auch bei dem Gerät wird der Hauptverbrauch gemessen (Innen+Außengerät). Bei den anderen Geräten misst er nur den Standby oder den Ventilator-Strom des Innengerätes."* ⚠ **„Das erste" ist rollierend, keine Geräte-Eigenschaft** — ist es aus, übernimmt ein anderes. Dass bei kingcap1 faktisch alles beim Büro landet, ist seine **Gewohnheit** (*„quasi das Hauptgerät, was ich meist als erstes schalte"*), nicht die Technik | ebd. |
| **E11** | **Die Größenordnungen bestätigen E10** — Momentanwerte: Shelly am Außengerät **600 W**, anforderndes Büro-Gerät **677 W**, mitlaufendes WZ **14 W**, ausgeschaltetes SZ **1 W**. ⚠ **Kein Beleg für eine Überschätzung:** dasselbe Büro-Gerät zeigt auf seinen Bildern 363 · 377 · 677 W — ein Inverter moduliert binnen Sekunden, und die Ablesungen sind nicht nachweislich zeitgleich. Die 77 W liegen **innerhalb** dieser Unschärfe. **Ungeklärt bleibt allein die kumulierte Differenz** (Σ Innen 4.233 gegen Shelly 3.190 kWh) — dort helfen keine Momentanwerte, und Nullpunkte wie Zeiträume der drei Zähler sind unbekannt (HA-Crash 08/2025). Meldersatz: *„also Shelly ist im Stromverbrauch wohl die BESTE Messquelle"* | ebd. |

**E5 + E6 sind der Kern: ein Innengerät liefert Zustand, keine Menge.** Damit ist K-3 (Aufteilung
je Innengerät) nicht vertagt, sondern **abgeschlossen** — es gibt nichts zu messen.

⚑ **E10/E11 präzisieren E5, ohne es zu entkräften.** Der Innengerät-Wert ist nicht diffus
„konsolidiert": **das gerade anfordernde Gerät trägt Innen + Außen, die mitlaufenden nur
ihren Ventilator.** Das deckt sich mit dem, was die Hersteller selbst sagen (E5) — der
Außenanteil steckt im Wert eines Innengeräts. **Genau deshalb ist er nicht raumbezogen:**

1. **Wer anfordert, wechselt** (E3/E10). Über Wochen wandert die Anlagenmenge zwischen den
   Innengeräten. Eine Raum-Aufteilung daraus wäre eine Aussage über die
   **Einschaltreihenfolge**, nicht über den Raum.
2. **Die mitlaufenden Geräte melden ihren Ventilator**, nicht ihren Kälteanteil — der Raum,
   der am meisten gekühlt wird, kann dort mit 14 W stehen.

⛔ **Und damit wäre ein Verbrauchsfeld am Innengerät nicht nur nutzlos, sondern gefährlich:** Wer
das gerade anfordernde Gerät zuordnet, bekommt eine Zahl in der Größenordnung des
**Anlagenverbrauchs** — und hält sie für den Raumverbrauch. Wer eines der anderen zuordnet,
bekommt einen Ventilator. **Und welches von beidem, entscheidet die Einschaltreihenfolge.**

---

## 3. Der Ansatz

**Eine Luft-Luft-Wärmepumpe ist zunächst ein Monosplit — wie heute, unverändert.** Wer mehrere
Innengeräte hat, legt sie als Liste an der Wärmepumpe an. Ein Innengerät ist **keine Investition**,
sondern ein Parameter des Geräts: es hat Bezeichnung, Modus und optional Soll-/Ist-Temperatur —
und **keine einzige kWh-Größe** (E5).

```jsonc
// Investition.parameter
"innengeraete": [
  { "id": 1, "bezeichnung": "Büro" },
  { "id": 3, "bezeichnung": "Wohnzimmer" }   // id 2 wurde gelöscht und bleibt frei
]
```

**Die Liste ist selbst der Schalter** (Entscheid Gernots, 20.08.): `multisplit` wird **abgeleitet**
(`len(innengeraete) >= 2`) und **nicht gespeichert**. Damit kann Schalter und Liste nie
auseinanderlaufen — der Widerspruchsfall existiert nicht.

### 3.1 Die Felder entstehen aus dem Parameter — mit dem vorhandenen Mechanismus

`get_felder_fuer_investition(typ, parameter, …)` leitet die Feldliste **heute schon** aus
`inv.parameter` ab: `getrennte_strommessung`, `arbitrage_faehig`, `v2h_faehig`, `laedt_aus_netz`
und `hat_speicher` schalten Felder frei oder aus, bei *Sonstiges* erzeugt die `kategorie` die
ganze Liste. Die Innengeräte-Liste ist derselbe Mechanismus, kein zweiter.

**Feld-Keys tragen die vergebene ID, nicht die Position:**

```
betriebsmodus-1     betriebsmodus-3
soll_temperatur-1   soll_temperatur-3      (optional)
ist_temperatur-1    ist_temperatur-3       (optional)
```

⚠ **Die ID wird beim Anlegen vergeben und nie wiederverwendet.** Wird das mittlere von drei
Innengeräten gelöscht, behalten die anderen ihre Zuordnungen; das nächste neue bekommt die 4.
Eine durchnummerierte Position würde beim Löschen alle folgenden Zuordnungen verschieben —
`sensor_mapping` speichert nach Key.

**Die MQTT-Hälfte kommt geschenkt:** `mqtt_topic_registry.py:171` ruft
`get_live_felder_fuer_investition(inv.typ, inv.parameter)`. Jedes neue Feld hat damit sein Topic,
und die Topic-Liste auf der Datenquellen-Fläche zeigt es ohne weiteres Zutun. **Ein Feld = eine
Quelle** (HA-Sensor · MQTT · Connector) bleibt der Kanon, es gibt keinen Sonderweg.

### 3.2 Die Faltung: n Signale → ein Anlagen-Modus je Stunde

Geschrieben wird weiter **ein** Modus je Wärmepumpe und Stunde
(`TagesEnergieProfil.betriebsmodus_je_wp`) — neu ist nur, woraus er entsteht. Je Innengerät wird
wie bisher der Modus mit der längsten Verweildauer der Stunde bestimmt, dann gefaltet:

| Lage | Anlagen-Modus |
| --- | --- |
| alle Signale `aus` | `aus` |
| genau eine Betriebsseite vertreten (`heizen` **oder** `kuehlen`) | diese Seite |
| **`heizen` und `kuehlen` in derselben Stunde** | `unbestimmt` — nicht aufteilbar (E4) |
| nur `entfeuchten` / `lueften` / `unbestimmt` | der häufigste dieser Werte |
| kein Signal | **kein Eintrag** — „nicht hingesehen" |

**Zwei Regeln, die nicht verhandelbar sind:**

1. **`aus` zählt nicht mit, solange ein anderes Gerät läuft** (E1). Nur wenn *alle* aus sind, ist
   die Anlage aus.
2. **Der Ist-Betrieb schlägt den eingestellten Modus** — je Innengerät, vor der Faltung (E2).

⚑ **Zeile 3 ist der eigentliche Gewinn.** Heute liest eedc ein Gerät, findet „Heizen" und bucht
die Stunde ins Heizen — auch wenn nebenan gekühlt wird. Mit allen Signalen wird der Widerspruch
sichtbar und ehrlich als „nicht aufgeteilt" ausgewiesen (ADR-002/P4). **Kein Mehrheitsentscheid**
(Entscheid Gernots): zwei kühlende gegen ein heizendes Gerät sind keine Kühlstunde, sondern eine
Stunde, in der die Anlage beides getan hat.

### 3.3 Bestehende Zuordnungen bleiben gültig

Wer heute eine `climate`-Entität an der Wärmepumpe zugeordnet hat (kingcap1, Klausnn, OB73-gif),
behält sie — sie ist ein Signal wie jedes andere und nimmt an der Faltung teil. Ohne Innengeräte
verhält sich alles **bitgleich** zu heute. Keine Migration, kein Altdaten-Bruch.

---

## 4. Etappen

| # | Etappe | Inhalt |
| --- | --- | --- |
| **F** | **Folgefehler E8** — Aktion getrennt durchreichen, Pfad-Wächter | ✅ **gebaut 2026-08-20** (s. §6) |
| **I1** | Innengeräte-Liste am WP-Formular (Bezeichnung, Anlegen/Löschen), ID-Vergabe |
| **I2** | Felder je Innengerät aus dem Parameter; Zuordnungsfläche zeigt sie gruppiert |
| **I3** | **Faltung** nach §3.2 — die einzige Etappe, die Zahlen bewegt |
| **I4** | Soll-/Ist-Temperatur, **erfasst ohne Auswertung** |
| **I5** | „nicht aufteilbar (gegenläufige Innengeräte)" getrennt ausweisen |
| **T1** | **Die Spalte „Wärmepumpe" in der Tagesansicht kennt nur einen von zwei Pfaden** (§7) | ✅ **gebaut 2026-08-21** |
| **T2** | **Die Aufteilungs-Übersicht fehlt in Cockpit → Tag** (§8) | ✅ **gebaut 2026-08-21** |

⚠ **Vor I3 gehört eine Messung an einer echten Anlage mit mehreren Innengeräten** — sonst ist die
Faltungsregel eine Behauptung. Klausnn und kingcap1 haben passende Geräte.

### 4.1 F ist gebaut — und I1–I5 bleiben 1:1 umsetzbar

**Geprüft am Code, nicht angenommen** (Auflage Gernots, 20.08.): F fasst zwei Stellen an, die
I1–I5 **nicht** brauchen — den Rückgabetyp von `get_zustand_history` (Paar → Tripel) und die
Verweildauer-Schleife in `_get_betriebsmodus_history`. I3 setzt an einer **dritten** Stelle an,
der Zuweisung am Ende derselben Funktion:

```python
gewinner = max(dauer.items(), …)[0]
for inv_id in entity_zu_inv[entity_id]:
    ergebnis.setdefault(h, {})[inv_id] = gewinner   # ← hier hängt sich I3 ein
```

Heute ist das eine **Zuweisung**, aus ihr wird eine **Faltung**: je Investition die Gewinner aller
zugehörigen Innengeräte sammeln, dann nach §3.2 zusammenführen. Dazu dreht sich `entity_zu_inv`
(Entity → Investitionen) zu Investition → Entities. **Kein Umbau an F nötig** — F liefert den
Stundengewinner je Entity, und genau der ist die Eingabe der Faltung. F ist damit Vorarbeit, kein
Hindernis.

⚠ **Eine Präzisierung, die aus dem Bau von F folgt und in §3.2 gehört:** Die Faltung arbeitet auf
den **Stundengewinnern** je Innengerät, nicht auf Zeitscheiben. Wechselt ein Gerät *innerhalb*
einer Stunde von Heizen auf Kühlen, erscheint die Stunde als „nicht aufteilbar" — obwohl nichts
gleichzeitig lief. **Das ist gewollt:** die Zählersumme ist stundengranular, eedc könnte die kWh
dieser Stunde ohnehin nicht auf die beiden Hälften verteilen. „Nicht aufteilbar" ist dort die
ehrliche Antwort, keine Näherung.

---

## 5. Grenzen — sie gehören in den Anwender-Text

1. **Ein Innengerät liefert keinen Verbrauch.** Was so heißt, ist der Wert des Außengeräts —
   und zwar bei dem Gerät, das gerade **anfordert** — und das wechselt (E5/E10). Je Raum messen geht nur mit
   eigener Messstelle, und die gibt es bei gemeinsamer Zuleitung nicht.
2. **Mehrkreis-Anlagen sind in gegenläufigen Stunden nicht aufteilbar** — mit beliebig vielen
   Innengeräten nicht. eedc kann sie nur benennen.
3. **Kein Backfill über die Recorder-Tiefe hinaus** (E7). Wer heute zuordnet, hat ab heute eine
   Aufteilung.
4. **Cloud-Werte sind Schätzungen**, auch wo sie nach Messung aussehen. Die belastbare Menge ist
   ein eigener Zähler am Außengerät — beide Melder sind unabhängig darauf gekommen.

---

## 6. Der Folgefehler E8 — ✅ gebaut am 2026-08-20

`get_zustand_history` faltet `hvac_action` **in den State-Punkt** (`ha_state_service.py:400`), der
Aufrufer normalisiert **einargumentig** (`_helpers.py:421,425`). Die Aktions-Tabelle
`_AKTION_ZU_KANON` ist aber nur über den *zweiten* Parameter erreichbar, den kein Produktivpfad
übergibt. Gemessen:

```
n('cooling')          = 'unbestimmt'      ← Produktivpfad
n('cool', 'cooling')  = 'kuehlen'         ← nur der Test
```

**Wirkung:** Jedes Gerät mit Ist-Signal (Panasonic, Daikin, die meisten Luft-Wasser-WP) verliert
seine **gesamte** Aufteilung — `heating`, `cooling`, `defrosting`, `drying`, `fan` werden alle zu
`unbestimmt`. Geräte **ohne** `hvac_action` (MELCloud/Luft-Luft) sind nicht betroffen. **Das
bessere Signal verschlechtert das Ergebnis.** Und still: die Zuordnungsfläche zeigt „Kühlen
(cool)", weil sie den State liest.

**Der Import ist derselbe Pfad.** `aggregate_day` ist der einzige Schreiber für Live-Job, Vortag,
Recovery, `backfill_range` und die Reparatur-Werkbank; der Monatsabschluss persistiert die
Teilmengen. Wer 90 Tage importiert, schreibt 90 Tage `unbestimmt` fest.

**Warum kein Wächter griff:** `test_263_k2_…` prüft `normalisiere_betriebsmodus("heat","cooling")`
— eine Schnittstelle, die kein Produktivpfad benutzt. Die Probe zeigt aufs falsche Objekt.

**Fix:** Zustand und Aktion getrennt zurückgeben, Aufrufer ruft
`normalisiere_betriebsmodus(state, aktion)`; Wächter auf den **Pfad** (History-Antwort → Kanon).
Das Aktions-Vokabular in `_ZUSTAND_ZU_KANON` zu ergänzen wäre kürzer und falsch — `off` und `fan`
bedeuten in beiden Tabellen Unterschiedliches.

**Heilbar, soweit der Recorder reicht** (`aggregate_day` ist idempotent). Je später der Fix, desto
mehr Historie ist endgültig weg.

### ✅ Gebaut — was tatsächlich geändert wurde

* `ha_state_service.get_zustand_history` gibt **Tripel** `(ts, zustand, aktion)` statt Paare; die
  Aktion wird nur noch **mitgeführt**, nicht mehr angewendet.
* `_get_betriebsmodus_history` trägt Zustand und Aktion als Paar durch die Verweildauer-Schleife
  und ruft `normalisiere_betriebsmodus(zustand, aktion)`.
* **Zwei Wächter statt einem**, weil ein einzelner die Lücke nicht sieht:
  `test_f_die_ha_antwort_haelt_zustand_und_aktion_getrennt` prüft die **Naht zu HA** (rohe
  Antwort → getrennte Felder), `test_f_der_ist_betrieb_erreicht_die_stundenzeile` den **ganzen
  Weg** bis `betriebsmodus_je_wp` — mit Gegenprobe: dieselbe Historie *ohne* Ist-Signal ergibt
  eine reine Kühlstunde.
* **Der Fake im Test lieferte Paare und kannte `hvac_action` gar nicht** — er konnte den Verlust
  deshalb nicht bemerken. Jetzt Tripel; Fixtures dürfen weiter Paare schreiben (Aktion `None`).

**Beide Gegenproben gefahren:** Sprengsatz in `ha_state_service` (alte Faltung) ⇒ Naht-Wächter
rot; Sprengsatz in `_helpers` (einargumentig normalisieren) ⇒ Pfad-Wächter rot. Rückbau jeweils
per Dateikopie.

**Gates:** pytest **3.293 in beiden Zonen** (vorher 3.291) · lint 0 · tsc 0 ohne Pipe ·
Vitest 1.191 · 25/25 `check:*` (`park-leertest` ausgelassen — Livetest, kein Frontend-Quellcode
berührt) · Website unberührt (`sync-docs.sh` spiegelt eine feste Liste, Konzepte gehören nicht
dazu).

---

## 7. T1 — ✅ gebaut: die Geräte-Spalten kennen beide Pfade

**Gemeldet von OB73-gif** (#263, 20.08.): *„Sowohl in den Stundenwerten wie im Stundenverlauf ist
nur Wärmepumpe aufgeführt und die Werte sind leer."* — von jemandem, der in derselben Nachricht
bestätigt, dass die **Monatsansicht** Heizen und Kühlen korrekt zeigt.

**Zwei Pfade tragen dieselbe Größe, und die Tagesspalte kennt nur einen:**

| | Quelle | wer liest sie |
| --- | --- | --- |
| `TagesEnergieProfil.waermepumpe_kw` | **Zähler-Snapshot** — `snap_h["wp"]` ← `verbrauch_wp` ← ein zugeordneter **kWh-Zählersensor** auf `stromverbrauch_kwh` | die Spalte „Wärmepumpe" der Stundenwerte (`defaultVisible: true`) |
| `TagesEnergieProfil.komponenten['waermepumpe_<id>']` | **Leistungspfad** | der **Monats-Modus-Split** (`waermepumpe_kwh_je_investition`) und die gerätebenannte Spalte |

`views.py::get_stundenwerte` reicht `waermepumpe_kw=r.waermepumpe_kw` **ohne Fallback** durch.

**An einer nachgestellten Instanz gemessen** (Klima-Investition, `komponenten` gefüllt, kein
kWh-Zähler):

```
Sammelspalte waermepumpe_kw : [None, None, None, None] ... alle None? True
komponenten je Gerät        : [-0.5, -0.5, -0.5, -0.5]
Serien (dynamische Spalten) : [('waermepumpe_1', 'Splitklima')]
```

⇒ **Die Spalte „Wärmepumpe" ist leer, während dieselbe Stunde in der gerätebenannten Spalte
danebensteht** — und genau daraus rechnet der Monat seine Aufteilung. Das erklärt die Meldung
vollständig: *Monat kann es, Tag nicht.*

**Wen es trifft:** jede Wärmepumpe oder Klimaanlage **ohne kWh-Zählersensor, aber mit
Leistungssensor**. Bei Split-Klimaanlagen ist das der Normalfall — die Cloud-Wege liefern
Leistung und Tagessummen (E5, E9), keinen sauberen Verbrauchszähler.

**Gebaut wurde (a) — als Angleichung, nicht als neue Regel** (Entscheid Gernots, 21.08.:
*„gleiches Verhalten wie bei anderen Geräten auf dieser Seite"*). Die Messung dahinter:

| Wo | Quelle für die Wärmepumpe | Fallback |
| --- | --- | --- |
| **Live-Seite** | Leistungspfad; fehlt der Gesamtwert, Σ der Teilwerte (`live_komponenten_builder.py:120`) | **ja** |
| Tag, Spalte „Wärmepumpe" | Zählerpfad | **nein** ← der Fehler |
| Tag, **Hausverbrauch** | WP + Wallbox aus **Zähler**, sonstige Verbraucher aus **`komponenten`** | **gemischt** |
| Monats-Modus-Split | Leistungspfad | — |

⇒ **Die Seite war schon in sich uneinheitlich**, nicht erst gegenüber Live.

⚑ **Die leere Zelle war nicht der schwerste Teil.** `berechneHausverbrauch` zieht die Wärmepumpe
über `s.waermepumpe_kw ?? 0` ab — ohne Zähler wurde **nichts** abgezogen, obwohl derselbe Wert für
sonstige Verbraucher in derselben Zeile sehr wohl benutzt wird. **Der Hausverbrauch stand um den
WP-Verbrauch zu hoch.** Er liest denselben Wert und heilt ohne eigenen Eingriff mit. (Der
Funktions-Kommentar benannte die Lücke bereits selbst: *„ein `null` heißt ‚nicht vorhanden' **oder**
‚hat nicht gemessen'"* — die N-95-Klasse.)

**Umsetzung:** neue Layer-Funktion `core/berechnungen/energie.py::geraete_spalte_kw`
(ADR-001 — die Auflösung ist eine Formel, kein Routen-Detail), aufgerufen in
`views.py::get_stundenwerte` für `waermepumpe_kw` und `wallbox_kw`. **Bei Lesezeit, nicht beim
Schreiben:** ein Leistungswert in einer Zählerspalte verlöre seine Herkunft. Im Frontend wären es
drei Kopien (Tabelle · Chart · CSV) gewesen — Regel 0a.

**Drei Eigenschaften, jede mit eigener Probe:**

1. **Zähler schlägt Leistung.** Wo beides vorliegt, gewinnt der Zähler — sonst zwei Zahlen für
   dieselbe Größe (Achse-2-Drift, #356).
2. **Betrag statt Vorzeichen.** `komponenten` führt Senken negativ (N-261); ein −0,5 in der
   Sammelspalte hieße „so viel wurde *nicht* verbraucht".
3. **Kein Key heißt `None`, nicht 0.** Ein **vorhandener** Key mit Wert 0 bleibt dagegen eine echte
   Null — die F-42-Klasse in beide Richtungen.

⛔ **Bewusst nur die Geräte-Spalten.** `pv_kw` und `verbrauch_kw` sind **Bilanzgrößen** — an ihnen
hängen Performance-Ratio sowie Überschuss/Defizit (`aggregator.py`). Ein Fallback dort änderte die
**Bilanz**, nicht eine Anzeige; das wäre ein eigener Vorgang mit eigener Messung. Eine Probe hält
die Grenze fest, damit sie nicht beiläufig verschoben wird.

**Wächter:** `test_263_t1_geraete_spalten_beide_pfade.py` — **sechs Proben auf die ROUTE**, nicht
auf den Layer allein. Der Layer wäre grün gewesen, ohne dass ein Anwender etwas gesehen hätte —
genau der Fehler, an dem der `hvac_action`-Wächter scheiterte (§6). Gegenprobe gefahren: alten
Zustand wiederhergestellt ⇒ die Melder-Probe rot, Rückbau per Dateikopie.

**Gates:** pytest **3.299 in beiden Zonen** (vorher 3.293) · lint 0 · tsc 0 ohne Pipe ·
Vitest 1.191 · 25/25 `check:*` (`park-leertest` ausgelassen — kein Frontend-Quellcode berührt).

---

## 8. T2 — ✅ gebaut: die Aufteilung gibt es auch je Tag

**Gemeldet von OB73-gif** (ebd.): *„Die Übersicht am Ende (wie beim Monat), wieviel Energie in
heizen/kühlen/nicht aufgeteilt floss, fehlt hier auch."*

**Zutreffend, und es ist eine Lücke, kein Defekt.** `WaermepumpeModusSplit` ist an **genau einer
Stelle** eingehängt (`WaermepumpeHubBloecke.tsx:56`); S4 hat den Hub und die Monats-/Jahressicht
gebaut, der Tag war nie dabei.

**Gebaut — und es war klein, weil die Architektur es hergab.** Drei Messungen vorab:

1. **Die Faltung ist ohnehin tagesweise.** `falte_modus_split_tag` rechnet je Tag (die Normierung
   braucht die Tages-Zählersumme); die Monatssicht summiert nur hinterher auf. Der neue Lader
   bleibt **eine Ebene früher** stehen.
2. **Cockpit → Tag und → Monat teilen sich die Blockfabrik** (`TagKomponenten.tsx`: *„Konvergenz
   statt zweiter Code-Pfad"* — Tagesdaten werden in ein `AktuellerMonatResponse`-Shape gegossen).
   Und diese Fabrik **hatte den Balken bereits**, gated durch `wp_modus_abdeckung_h > 0`.
3. ⇒ **Kein neuer Block, keine zweite Komponente, kein `period`-Sonderfall.** Im Frontend war es
   eine Zuweisung; die Datenlage entscheidet, wo der Block erscheint.

**Umsetzung:**

* `_lade_tages_eingaenge` aus `lade_modus_split_je_monat` **extrahiert** — Monat und Tag teilen
  sich jetzt den Ladepfad samt seiner Auswahlregeln („Tage über die Modus-Spur, Stunden
  vollständig"). Ohne das wären es zwei Pfade, und der Modul-Kopf sagt, warum das nicht geht:
  *eine Regel, die an zwei Stellen nachgebaut wird, driftet.*
* Neu `lade_modus_split_tag(db, anlage_id, datum)`.
* `tag-detail` liefert vier Felder (`wp_modus_strom_heizen_kwh` · `…_kuehlen_kwh` ·
  `…_nicht_aufgeteilt_kwh` · `wp_modus_abdeckung_h`), anlagenweite Σ wie die übrigen WP-Felder
  dort. **Mit denselben zwei Achsen wie überall:** `ist_aktiv_an(datum)` und die
  Teilmengen-Invariante — passt ein Gerät nicht, wird es **ganz** ausgelassen statt gekappt.
* **Der Rest kommt aus dem Backend**, nicht aus einer Client-Subtraktion: welcher Bezug gilt,
  entscheidet die Faltung. Zwei Stellen, die denselben Rest rechnen, driften.

⚠ **Ohne Modus-Signal bleiben alle vier Felder `None`** — der Block erscheint dann gar nicht,
statt drei Nullen zu zeigen (ADR-002/P4, die F-42-Klasse).

**Wächter:** `test_263_t2_modus_split_tag.py`, sieben Proben — darunter **der Endpunkt** (nicht
nur der Lader), die Tagesgrenze, das noch nicht angeschaffte Gerät und die Gleichheit
*Σ Tag == Monat*, die belegt, dass beide denselben Weg nehmen. Gegenprobe gefahren.

**Gates:** pytest **3.306 in beiden Zonen** (vorher 3.299) · lint 0 · tsc 0 ohne Pipe ·
Vitest 1.191 · **26/26 `check:*` inkl. `park-leertest`** (18 Sichten, **Exit 0**, gegen einen
frischen Demo-Build auf der Dev-Box — diesmal Pflicht, weil Frontend-Quellcode berührt ist).

---

## 9. Bezug

Vorgänger [`KONZEPT-263-klima-split.md`](KONZEPT-263-klima-split.md) ·
Issue [#263](https://github.com/supernova1963/eedc-homeassistant/issues/263) ·
Melder kingcap1 (Mitsubishi/MELCloud, 3 Innengeräte) · Klausnn (Panasonic Multisplit, 2 Innen) ·
OB73-gif · dietmar1968 · azywietz-web · [ADR-002](ADR-002-WURZELMUSTER.md) P4
