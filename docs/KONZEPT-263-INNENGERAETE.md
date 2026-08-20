# Konzept #263 — Innengeräte einer Luft-Luft-Wärmepumpe

> **Status:** Entwurf, 2026-08-20. **Nichts davon ist gebaut.**
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

**E5 + E6 sind der Kern: ein Innengerät liefert Zustand, keine Menge.** Damit ist K-3 (Aufteilung
je Innengerät) nicht vertagt, sondern **abgeschlossen** — es gibt nichts zu messen.

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

1. **Ein Innengerät liefert keinen Verbrauch.** Was so heißt, ist der Wert des Außengeräts (E5).
   Je Raum messen geht nur mit eigener Messstelle — und die gibt es bei gemeinsamer Zuleitung nicht.
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

## 7. Bezug

Vorgänger [`KONZEPT-263-klima-split.md`](KONZEPT-263-klima-split.md) ·
Issue [#263](https://github.com/supernova1963/eedc-homeassistant/issues/263) ·
Melder kingcap1 (Mitsubishi/MELCloud, 3 Innengeräte) · Klausnn (Panasonic Multisplit, 2 Innen) ·
OB73-gif · dietmar1968 · azywietz-web · [ADR-002](ADR-002-WURZELMUSTER.md) P4
