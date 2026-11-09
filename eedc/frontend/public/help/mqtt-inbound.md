# MQTT-Inbound: Universelle Datenbruecke

> **Erzeugt — nicht von Hand ändern —** Bausteine in `docs/mqtt-inbound/`, `scripts/groessen-uebersicht.sh`. Die Topic-Tabellen je Gerätetyp und die Preset-Tabelle kommen aus dem Code (`services/mqtt_topic_registry.py`, Feld-Registry, `services/mqtt_presets.py`).

MQTT-Inbound ermoeglicht es, Live-Leistungsdaten und Zaehlerstaende von **jedem Smarthome-System** an EEDC zu senden. Es wird nur ein MQTT-Broker benoetigt (z.B. Mosquitto).

## Unterstuetzte Systeme

- Home Assistant (Automation oder Node-RED Add-on)
- Node-RED (standalone oder als Add-on)
- ioBroker (JavaScript-Adapter)
- FHEM (MQTT2-Modul)
- openHAB (MQTT Binding)
- Jedes System mit MQTT-Publish-Faehigkeit

## Einrichtung

1. **MQTT-Broker installieren** (z.B. Mosquitto)
2. In EEDC unter *Einstellungen > Einrichtung > MQTT-Inbound*:
   - Broker-Adresse und Port eintragen
   - Optional: Benutzername/Passwort
   - "Speichern & Verbinden" klicken
3. Die generierten Topics im Smarthome-System befuellen

## Topic-Struktur

EEDC generiert die Topics automatisch aus den angelegten Anlagen und Investitionen. Das Format ist:

```
eedc/{anlage_id}_{name}/
├── live/                              # Momentanwerte (W, °C, %) und der Betriebsmodus
│   ├── einspeisung_w                  → 1100
│   ├── netzbezug_w                    → 0
│   └── inv/{inv_id}_{name}/
│       ├── leistung_w                 → 4200
│       ├── soc                        → 72       (nur Speicher/E-Auto)
│       ├── vorlauf_temperatur_c       → 34.5     (nur Waermepumpe; ebenso ruecklauf_/warmwasser_temperatur_c)
│       └── betriebsmodus              → 1        (nur Waermepumpe: Wort oder Code, siehe unten)
│
└── energy/                            # ZAEHLERSTAENDE (kWh, kumuliert)
    ├── einspeisung_kwh                → 6675.3
    ├── netzbezug_kwh                  → 6424.8
    └── inv/{inv_id}_{name}/
        └── {key}                      → Wert     (siehe Felder-Referenz)
```

### Energy-Felder Referenz (Investitions-Topics)

> ⚠ **Unter `energy/` gehoert der ZAEHLERSTAND, nicht der Monatsverbrauch.** Also der
> fortlaufende Stand, den dein Zaehler oder Wechselrichter anzeigt — eedc bildet die
> Differenzen daraus selbst (Tag, Monat, Jahr).
>
> ⛔ **Ein taeglich oder monatlich zurueckgesetzter Zaehler ist dafuer NICHT geeignet** — also
> ein Feld, das „heute" oder „diesen Monat" meint und dann wieder bei null anfaengt. eedc
> erkennt den Ruecksprung und liefert fuer diesen Zeitraum **keinen Wert**, statt zwei Staende
> voneinander abzuziehen, die zu verschiedenen Zaehlerlaeufen gehoeren.
>
> **Warum nicht einfach hochrechnen?** Technisch ginge es: Die Staende sind stuendlich
> mitgeschrieben, eine Summe daraus traefe auf rund 3 % genau. eedc tut es trotzdem nicht.
> Was zwischen dem letzten Stand und dem Ruecksprung verbraucht wird, taucht in keinem Stand
> mehr auf — der Fehlbetrag geht **immer** in dieselbe Richtung, und im Monatsabschluss wuerde
> aus so einer Zahl per Knopfdruck ein gespeicherter Wert, der aussieht wie eine Messung.
> Genau davor warnt der Daten-Checker schon beim Anlegen: *Zuruecksetzen „nie" (ohne Zyklus)*.
>
> ⭐ **Was du stattdessen tust:** Publiziere den **fortlaufenden** Stand. Bei einem
> `utility_meter` in Home Assistant heisst das Zuruecksetzen auf *„nie"*; kommt der Wert aus
> einer eigenen App, sende den Lebenszaehler statt des Tageswerts. eedc bildet Tag, Monat und
> Jahr daraus selbst — und exakt.
>
> ⛔ **Bis eedc 4.0.32 stimmte dieser Absatz nicht.** Hier stand *„Ein taeglich oder monatlich
> zurueckgesetzter Zaehler funktioniert ebenfalls; eedc erkennt den Ruecksprung"*. Im
> **Tagesfenster** stimmte das, im **Monatsfenster** nur dann, wenn der Ruecksprung zufaellig an
> den Raendern ablesbar war. Ein „…heute"-Zaehler ergab im laufenden Monat einen Wert, der
> aussah wie eine Messung und den Verbrauch **eines** Tages nannte (gemessen: 5,6 statt
> 140 kWh) — *Cockpit → Monat* zeigte ihn an.
>
> **Bis eedc 4.0.29 stand hier „Monatswerte", und das war missverstaendlich.** Wer korrekt
> seinen Zaehlerstand schickte, bekam ihn im Monatsabschluss als Monatsmenge vorgehalten
> („weicht ab": 6675,3 gegen 552,75 kWh) und in *Cockpit → Monat* sogar angezeigt. Seit
> 4.0.30 rechnet eedc die Differenz ueber den Monat. **Du musst nichts umstellen** — der
> Zaehlerstand war und ist das Richtige.
>
> ⭐ **`km_gefahren` und `ladevorgaenge` folgen derselben Regel — seit sie eine eigene
> Zaehlerreihe haben.** Sie tragen keine kWh, und deshalb schrieb eedc fuer sie lange
> gar keine Reihe mit: Ein HA-Anwender bekam seine Monatswerte trotzdem, weil die
> HA-Statistik die Differenz direkt rechnet, ein Standalone-Anwender bekam **nichts** und
> trug von Hand ein — obwohl derselbe Feld-Hinweis ihm den „kumulativen km-Zaehler
> (Auto-Integration/OBD)" als Quelle anbot (Discussion #396). Jetzt schreibt eedc auch
> diese beiden Staende mit. **Schick den Tachostand, nicht die gefahrenen Kilometer.**
>
> **Seit P-433-2b K4** zeigt das E-Auto den Stand von `km_gefahren` live als **Kilometerstand** (aus dem Energie-Cache des
> Inbound, `inv/<id>/km_gefahren`, bis 60 s alt) und die Karte „Heute" den Zuwachs der abgeschlossenen Stunden als
> **„Gefahren heute"** (dazu `verbrauch_kwh` als **„Fahrverbrauch heute"**). Der Kanal-Katalog fuehrt `km_gefahren` und
> `ladevorgaenge` am Geraet als Spiegel/Mitschrift: mit HA-Entitaet (Datenquellen-Wahl HA) spiegelt eedc den Stand aus der
> Langzeitstatistik, sonst schreibt es den MQTT-Stand mit.

Die Felder unter `energy/inv/{id}_{name}/` entsprechen den Monatsdaten-Feldern der jeweiligen Investition. EEDC erkennt alle Felder automatisch — es muss kein Mapping konfiguriert werden.

Welche Felder das je Gerätetyp sind, steht in den Tabellen unter [Topics je Gerätetyp](#topics-je-gerätetyp) — vollständig, auch die Felder ohne Topic.

> ⭐ **Ein selbst errechneter PV-Ladezaehler (Discussion #414).** Liefert die Wallbox oder evcc
> keinen eigenen PV-Zaehlerstand, sondern nur einen Solar-Anteil in Prozent, laesst sich
> `ladung_pv_kwh` als Produkt *Gesamtzaehler × kumulierter Solaranteil* bilden — **aber nur,
> wenn Prozent und Zaehler dieselbe Energiebasis haben** (derselbe Zaehler seit demselben Tag).
> eedc bildet aus diesem Stand die Monatsdifferenz wie aus jedem anderen. Die Monatswerte zeigen
> dann den **Anteil des jeweiligen Monats** (Sommer nahe 100 %, Winter nahe 0 %), nicht den
> kumulierten Durchschnitt, den evcc anzeigt — die Summe ueber die Monate trifft ihn wieder.

Was nicht per MQTT lieferbar ist (Wetterdaten, Preise, Sonderkosten, Notizen — im Monatsabschluss von Hand eingetragen oder berechnet), nennt die Basis-Tabelle unter [Topics je Gerätetyp](#topics-je-gerätetyp) mit „kein MQTT-Topic".

### Topics je Gerätetyp

Je Gerätetyp eine Tabelle der Energie-Topics (`energy/`, Zählerstände) und eine der Live-Topics (`live/`), erzeugt aus
der Erwartungsliste von eedc (`services/mqtt_topic_registry.py` — dieselbe Liste, die der Block **MQTT-Topics** am Ende
der Datenquellen-Fläche zum Kopieren zeigt) und der Feld-Registry. Jedes Feld steht genau einmal, auch eines ohne Topic.
`{anlage_id}` und `{inv_id}` sind die Datenbank-IDs, `{name}` dient nur der Lesbarkeit (siehe [Beispiel](#beispiel)).

- **Payload** sagt, was eedc auf dem Topic erwartet und was es daraus macht. Bei einem Zustand steht das Wort, das eedc
  intern führt, vorn; in Klammern die übrigen Werte, die eedc als dasselbe versteht (Herstellerwörter und Zahlencodes —
  die Codes gelten nur über MQTT).
- **Bedingung** nennt den Geräte-Parameter, an dem das Feld hängt; „(weich)" heißt: an dieser Bauart untypisch, aber
  möglich. Ein Live-Feld, dessen Bedingung am Gerät nicht gilt, erwartet eedc dort nicht (außer bei „weich");
  Energie-Topics erwartet es unabhängig von der Bedingung.
- „kein MQTT-Topic — Monatsabschluss (Hand oder HA-Sensor)": eedc verarbeitet diesen Wert nicht aus MQTT — er ist eine
  optionale Aufteilung oder ein Anteil (Eigenverbrauch, Einspeisung, PV-/Netz-Bezug), auswärts geladene Energie oder ein
  Geldbetrag. Er kommt im Monatsabschluss von Hand oder als Vorschlag aus einem zugeordneten HA-Sensor; bei Geldbeträgen
  steht „(Hand)".
- Was ein Feld bedeutet, sagt die Spalte „Hinweis" der [Sensor-Referenz](SENSOR-REFERENZ.md) — dieselbe Registry.

#### Anlage (Basis)

Energie-Topics:

| Feld | Label | Einheit | Topic | Payload | Bedingung | Beschreibung |
|---|---|---|---|---|---|---|
| `pv_gesamt_kwh` | PV-Erzeugung Zählerstand | kWh | `eedc/{anlage_id}_{name}/energy/pv_gesamt_kwh` | Zählerstand (kumuliert) | — | Zählerstand der gesamten PV-Erzeugung — aller Erzeuger, auch des Balkonkraftwerks. Haben alle PV-Module und Balkonkraftwerke einen eigenen Zähler, dient er dem Vergleich (Wandlungsverluste); fehlt einem der eigene Zähler, verteilt eedc den Rest nach kWp auf ihn — in Tag, Monat und Live gleich. Misst dein Zähler nur den Wechselrichter, ordne ihn dem PV-Modul als Erzeugungszähler zu. Kumulierter kWh-Zählerstand. Speist die „Heute"-Kachel — EEDC bildet das Tagesdelta gegen den Mitternachtswert (täglich resettende oder fortlaufende Zähler funktionieren beide). |
| `einspeisung_kwh` | Einspeisung Zählerstand | kWh | `eedc/{anlage_id}_{name}/energy/einspeisung_kwh` | Zählerstand (kumuliert) | — | Zählerstand der ins Netz eingespeisten Energie. Kernwert: ohne ihn lassen sich Eigenverbrauch und Autarkie nicht berechnen. Ohne Sensor im Monatsabschluss manuell erfassbar. Kumulierter kWh-Zählerstand. Speist die „Heute"-Kachel — EEDC bildet das Tagesdelta gegen den Mitternachtswert (täglich resettende oder fortlaufende Zähler funktionieren beide). |
| `netzbezug_kwh` | Netzbezug Zählerstand | kWh | `eedc/{anlage_id}_{name}/energy/netzbezug_kwh` | Zählerstand (kumuliert) | — | Zählerstand der aus dem Netz bezogenen Energie. Kernwert: ohne ihn lassen sich Gesamtverbrauch und Stromkosten nicht berechnen. Ohne Sensor im Monatsabschluss manuell erfassbar. Kumulierter kWh-Zählerstand. Speist die „Heute"-Kachel — EEDC bildet das Tagesdelta gegen den Mitternachtswert (täglich resettende oder fortlaufende Zähler funktionieren beide). |
| `globalstrahlung_kwh_m2` | Globalstrahlung | kWh/m² | kein MQTT-Topic — Monatsabschluss | — | — | — |
| `sonnenstunden` | Sonnenstunden | h | kein MQTT-Topic — Monatsabschluss | — | — | — |
| `durchschnittstemperatur` | Ø Temperatur | °C | kein MQTT-Topic — Monatsabschluss | — | — | — |
| `netzbezug_durchschnittspreis_cent` | Ø Strompreis | ct/kWh | kein MQTT-Topic — Monatsabschluss | — | Anlage: `dynamischer_tarif` | — |
| `einspeise_durchschnittspreis_cent` | Einspeisevergütung (Monat) | ct/kWh | kein MQTT-Topic — Monatsabschluss | — | Anlage: `variable_einspeisung` | — |
| `kraftstoffpreis_euro` | Ø Benzinpreis | €/L | kein MQTT-Topic — Monatsabschluss | — | Anlage: `hat_eauto` | — |
| `gaspreis_cent_kwh` | Ø Gas-/Ölpreis | ct/kWh | kein MQTT-Topic — Monatsabschluss | — | Anlage: `hat_waermepumpe` | — |
| `sonderkosten_euro` | Sonderkosten | € | kein MQTT-Topic — Monatsabschluss | — | — | — |
| `sonderkosten_beschreibung` | Beschreibung | — | kein MQTT-Topic — Monatsabschluss | — | — | — |
| `notizen` | Notizen | — | kein MQTT-Topic — Monatsabschluss | — | — | — |

Live-Topics:

| Feld | Label | Einheit | Topic | Payload | Bedingung |
|---|---|---|---|---|---|
| `einspeisung_w` | Einspeisung | W | `eedc/{anlage_id}_{name}/live/einspeisung_w` | Zahl (Momentanwert) — 5-Minuten- und Stundenmittel | — |
| `netzbezug_w` | Netzbezug | W | `eedc/{anlage_id}_{name}/live/netzbezug_w` | Zahl (Momentanwert) — 5-Minuten- und Stundenmittel | — |
| `netz_kombi_w` | Netz kombiniert (±) | W | `eedc/{anlage_id}_{name}/live/netz_kombi_w` | Zahl (Momentanwert) — 5-Minuten- und Stundenmittel | — |
| `pv_gesamt_w` | PV gesamt | W | `eedc/{anlage_id}_{name}/live/pv_gesamt_w` | Zahl (Momentanwert) — 5-Minuten- und Stundenmittel | — |
| `aussentemperatur_c` | Außentemperatur | °C | `eedc/{anlage_id}_{name}/live/aussentemperatur_c` | Zahl (Momentanwert) — 5-Minuten- und Stundenmittel | — |
| `strompreis` | Strompreis (dynamischer Tarif) | ct/kWh | kein MQTT-Topic | — | Anlage: `dynamischer_tarif` |

Den Strompreis nimmt eedc als `live/strompreis_ct` (ct/kWh) entgegen und zeigt ihn nur im Tagesverlauf (siehe
[Live-Mittelwerte](#live-mittelwerte-was-eedc-aus-den-live-topics-mitschreibt)); die Erwartungsliste nennt dieses Topic nicht.

#### PV-Module

Energie-Topics:

| Feld | Label | Einheit | Topic | Payload | Bedingung |
|---|---|---|---|---|---|
| `pv_erzeugung_kwh` | PV-Erzeugung | kWh | `eedc/{anlage_id}_{name}/energy/inv/{inv_id}_{name}/pv_erzeugung_kwh` | Zählerstand (kumuliert) | — |

Live-Topics:

| Feld | Label | Einheit | Topic | Payload | Bedingung |
|---|---|---|---|---|---|
| `leistung_w` | Leistung | W | `eedc/{anlage_id}_{name}/live/inv/{inv_id}_{name}/leistung_w` | Zahl (Momentanwert) — 5-Minuten- und Stundenmittel | — |

#### Balkonkraftwerk

Energie-Topics:

| Feld | Label | Einheit | Topic | Payload | Bedingung |
|---|---|---|---|---|---|
| `pv_erzeugung_kwh` | Erzeugung | kWh | `eedc/{anlage_id}_{name}/energy/inv/{inv_id}_{name}/pv_erzeugung_kwh` | Zählerstand (kumuliert) | — |
| `eigenverbrauch_kwh` | Eigenverbrauch | kWh | kein MQTT-Topic — Monatsabschluss (Hand oder HA-Sensor) | — | — |
| `speicher_ladung_kwh` | Speicher Ladung | kWh | kein MQTT-Topic — nur manuell | — | `hat_speicher` |
| `speicher_entladung_kwh` | Speicher Entladung | kWh | kein MQTT-Topic — nur manuell | — | `hat_speicher` |

Live-Topics:

| Feld | Label | Einheit | Topic | Payload | Bedingung |
|---|---|---|---|---|---|
| `leistung_w` | Leistung | W | `eedc/{anlage_id}_{name}/live/inv/{inv_id}_{name}/leistung_w` | Zahl (Momentanwert) — 5-Minuten- und Stundenmittel | — |

#### Speicher

Energie-Topics:

| Feld | Label | Einheit | Topic | Payload | Bedingung |
|---|---|---|---|---|---|
| `ladung_kwh` | Ladung — mit `laedt_aus_netz`: «Ladung (gesamt, inkl. Netz)» | kWh | `eedc/{anlage_id}_{name}/energy/inv/{inv_id}_{name}/ladung_kwh` | Zählerstand (kumuliert) | — |
| `entladung_kwh` | Entladung | kWh | `eedc/{anlage_id}_{name}/energy/inv/{inv_id}_{name}/entladung_kwh` | Zählerstand (kumuliert) | — |
| `ladung_netz_kwh` | Netzladung | kWh | `eedc/{anlage_id}_{name}/energy/inv/{inv_id}_{name}/ladung_netz_kwh` | Zählerstand (kumuliert) | `laedt_aus_netz` |
| `speicher_ladepreis_cent` | Ø Ladepreis | ct/kWh | kein MQTT-Topic — nur manuell | — | `arbitrage_faehig` |

Live-Topics:

| Feld | Label | Einheit | Topic | Payload | Bedingung |
|---|---|---|---|---|---|
| `leistung_w` | Leistung | W | `eedc/{anlage_id}_{name}/live/inv/{inv_id}_{name}/leistung_w` | Zahl (Momentanwert) — 5-Minuten- und Stundenmittel | — |
| `soc` | Ladestand | % | `eedc/{anlage_id}_{name}/live/inv/{inv_id}_{name}/soc` | Zahl (Momentanwert) — 5-Minuten- und Stundenmittel | — |

#### Wärmepumpe

Energie-Topics:

| Feld | Label | Einheit | Topic | Payload | Bedingung |
|---|---|---|---|---|---|
| `stromverbrauch_kwh` | Stromverbrauch | kWh | `eedc/{anlage_id}_{name}/energy/inv/{inv_id}_{name}/stromverbrauch_kwh` | Zählerstand (kumuliert) | `!getrennte_strommessung` (weich) |
| `strom_heizen_kwh` | Strom Heizen | kWh | `eedc/{anlage_id}_{name}/energy/inv/{inv_id}_{name}/strom_heizen_kwh` | Zählerstand (kumuliert) | `['getrennte_strommessung', '!brauchwasser']` (weich) |
| `strom_warmwasser_kwh` | Strom Warmwasser | kWh | `eedc/{anlage_id}_{name}/energy/inv/{inv_id}_{name}/strom_warmwasser_kwh` | Zählerstand (kumuliert) | `['getrennte_strommessung', '!luft_luft']` |
| `heizenergie_kwh` | Heizwärme | kWh | `eedc/{anlage_id}_{name}/energy/inv/{inv_id}_{name}/heizenergie_kwh` | Zählerstand (kumuliert) | `!brauchwasser` (weich) |
| `warmwasser_kwh` | Warmwasser-Wärme | kWh | `eedc/{anlage_id}_{name}/energy/inv/{inv_id}_{name}/warmwasser_kwh` | Zählerstand (kumuliert) | `!luft_luft` |
| `waerme_kwh` | Wärme gesamt | kWh | `eedc/{anlage_id}_{name}/energy/inv/{inv_id}_{name}/waerme_kwh` | Zählerstand (kumuliert) | — |
| `heizstab_strom_kwh` | Strom Zusatzheizung | kWh | `eedc/{anlage_id}_{name}/energy/inv/{inv_id}_{name}/heizstab_strom_kwh` | Zählerstand (kumuliert) | — |
| `netzbezug_eigener_tarif_kwh` | Netzbezug zum WP-Tarif | kWh | `eedc/{anlage_id}_{name}/energy/inv/{inv_id}_{name}/netzbezug_eigener_tarif_kwh` | Zählerstand (kumuliert) | — |
| `betriebsart_strom_heizen_kwh` · je Innengerät zusätzlich `betriebsart_strom_heizen_kwh-<id>` | Strom Heizbetrieb | kWh | `eedc/{anlage_id}_{name}/energy/inv/{inv_id}_{name}/betriebsart_strom_heizen_kwh` | Zählerstand (kumuliert) | `luft_luft` (weich) |
| `betriebsart_strom_kuehlen_kwh` · je Innengerät zusätzlich `betriebsart_strom_kuehlen_kwh-<id>` | Strom Kühlbetrieb | kWh | `eedc/{anlage_id}_{name}/energy/inv/{inv_id}_{name}/betriebsart_strom_kuehlen_kwh` | Zählerstand (kumuliert) | `kuehlt` (weich) |
| `betriebsart_strom_lueften_kwh` · je Innengerät zusätzlich `betriebsart_strom_lueften_kwh-<id>` | Strom Lüftbetrieb | kWh | `eedc/{anlage_id}_{name}/energy/inv/{inv_id}_{name}/betriebsart_strom_lueften_kwh` | Zählerstand (kumuliert) | `luft_luft` (weich) |
| `betriebsart_strom_entfeuchten_kwh` · je Innengerät zusätzlich `betriebsart_strom_entfeuchten_kwh-<id>` | Strom Entfeuchtungsbetrieb | kWh | `eedc/{anlage_id}_{name}/energy/inv/{inv_id}_{name}/betriebsart_strom_entfeuchten_kwh` | Zählerstand (kumuliert) | `luft_luft` (weich) |
| `betriebsart_nutzenergie_heizen_kwh` · je Innengerät zusätzlich `betriebsart_nutzenergie_heizen_kwh-<id>` | Nutzenergie Heizbetrieb | kWh | `eedc/{anlage_id}_{name}/energy/inv/{inv_id}_{name}/betriebsart_nutzenergie_heizen_kwh` | Zählerstand (kumuliert) | `luft_luft` (weich) |
| `betriebsart_nutzenergie_kuehlen_kwh` · je Innengerät zusätzlich `betriebsart_nutzenergie_kuehlen_kwh-<id>` | Nutzenergie Kühlbetrieb | kWh | `eedc/{anlage_id}_{name}/energy/inv/{inv_id}_{name}/betriebsart_nutzenergie_kuehlen_kwh` | Zählerstand (kumuliert) | `kuehlt` (weich) |
| `betriebsart_nutzenergie_lueften_kwh` · je Innengerät zusätzlich `betriebsart_nutzenergie_lueften_kwh-<id>` | Nutzenergie Lüftbetrieb | kWh | `eedc/{anlage_id}_{name}/energy/inv/{inv_id}_{name}/betriebsart_nutzenergie_lueften_kwh` | Zählerstand (kumuliert) | `luft_luft` (weich) |
| `betriebsart_nutzenergie_entfeuchten_kwh` · je Innengerät zusätzlich `betriebsart_nutzenergie_entfeuchten_kwh-<id>` | Nutzenergie Entfeuchtungsbetrieb | kWh | `eedc/{anlage_id}_{name}/energy/inv/{inv_id}_{name}/betriebsart_nutzenergie_entfeuchten_kwh` | Zählerstand (kumuliert) | `luft_luft` (weich) |

Live-Topics:

| Feld | Label | Einheit | Topic | Payload | Bedingung |
|---|---|---|---|---|---|
| `leistung_w` · je Innengerät zusätzlich `leistung_w-<id>` | Leistung gesamt | W | `eedc/{anlage_id}_{name}/live/inv/{inv_id}_{name}/leistung_w` | Zahl (Momentanwert) — 5-Minuten- und Stundenmittel | — |
| `leistung_heizen_w` | Leistung Heizen | W | `eedc/{anlage_id}_{name}/live/inv/{inv_id}_{name}/leistung_heizen_w` | Zahl (Momentanwert) — 5-Minuten- und Stundenmittel | `!brauchwasser` (weich) |
| `leistung_warmwasser_w` | Leistung Warmwasser | W | `eedc/{anlage_id}_{name}/live/inv/{inv_id}_{name}/leistung_warmwasser_w` | Zahl (Momentanwert) — 5-Minuten- und Stundenmittel | `!luft_luft` (weich) |
| `leistung_kuehlen_w` | Leistung Kühlen | W | `eedc/{anlage_id}_{name}/live/inv/{inv_id}_{name}/leistung_kuehlen_w` | Zahl (Momentanwert) — 5-Minuten- und Stundenmittel | `kuehlt` (weich) |
| `warmwasser_temperatur_c` | Warmwasser-Temperatur | °C | `eedc/{anlage_id}_{name}/live/inv/{inv_id}_{name}/warmwasser_temperatur_c` | Zahl (Momentanwert) — 5-Minuten- und Stundenmittel | `!luft_luft` (weich) |
| `vorlauf_temperatur_c` | Vorlauf | °C | `eedc/{anlage_id}_{name}/live/inv/{inv_id}_{name}/vorlauf_temperatur_c` | Zahl (Momentanwert) — 5-Minuten- und Stundenmittel | — |
| `ruecklauf_temperatur_c` | Rücklauf | °C | `eedc/{anlage_id}_{name}/live/inv/{inv_id}_{name}/ruecklauf_temperatur_c` | Zahl (Momentanwert) — 5-Minuten- und Stundenmittel | — |
| `heizstab_leistung_w` | Leistung Zusatzheizung | W | `eedc/{anlage_id}_{name}/live/inv/{inv_id}_{name}/heizstab_leistung_w` | Zahl (Momentanwert) — 5-Minuten- und Stundenmittel | — |
| `betriebsmodus` | Betriebsmodus | — | `eedc/{anlage_id}_{name}/live/inv/{inv_id}_{name}/betriebsmodus` | Zustand: `heizen` (auch `heat`, `1`) · `warmwasser` (auch `brauchwasser`, `trinkwasser`, `dhw`, `hot_water`, `water_heating`, `2`) · `kuehlen` (auch `cool`, `kühlen`, `3`) · `entfeuchten` (auch `dry`, `5`) · `lueften` (auch `fan_only`, `lüften`, `4`) · `aus` (auch `off`, `0`) · als unbestimmt gezählt: `auto`, `heat_cool`, `automatik` — Betriebsart-Mitschrift (Anteil der Stunde je Betriebsart) | — |
| `soll_temperatur_c` · je Innengerät zusätzlich `soll_temperatur_c-<id>` | Soll-Temperatur | °C | `eedc/{anlage_id}_{name}/live/inv/{inv_id}_{name}/soll_temperatur_c` | Zahl (Momentanwert) — 5-Minuten- und Stundenmittel | `luft_luft` |
| `ist_temperatur_c` · je Innengerät zusätzlich `ist_temperatur_c-<id>` | Raumtemperatur | °C | `eedc/{anlage_id}_{name}/live/inv/{inv_id}_{name}/ist_temperatur_c` | Zahl (Momentanwert) — 5-Minuten- und Stundenmittel | `luft_luft` |

Felder mit „je Innengerät" erwartet eedc an einer Klimaanlage mit Innengeräten zusätzlich einmal je Innengerät; die
konkreten Topics mit der Nummer des Innengeräts zeigt der Block **MQTT-Topics** am Ende der Datenquellen-Fläche.

#### E-Auto

Energie-Topics:

| Feld | Label | Einheit | Topic | Payload | Bedingung |
|---|---|---|---|---|---|
| `km_gefahren` | Gefahrene km | km | `eedc/{anlage_id}_{name}/energy/inv/{inv_id}_{name}/km_gefahren` | Zählerstand (kumuliert) | — |
| `km_stand` | Tachostand | km | kein MQTT-Topic — nur manuell | — | — |
| `verbrauch_kwh` | Verbrauch | kWh | `eedc/{anlage_id}_{name}/energy/inv/{inv_id}_{name}/verbrauch_kwh` | Zählerstand (kumuliert) | — |
| `ladung_pv_kwh` | Heim: PV | kWh | `eedc/{anlage_id}_{name}/energy/inv/{inv_id}_{name}/ladung_pv_kwh` | Zählerstand (kumuliert) | Anlage: `keine_dienstliche_wallbox` |
| `ladung_netz_kwh` | Heim: Netz | kWh | `eedc/{anlage_id}_{name}/energy/inv/{inv_id}_{name}/ladung_netz_kwh` | Zählerstand (kumuliert) | Anlage: `keine_dienstliche_wallbox` |
| `ladung_kwh` | Heim: gesamt | kWh | `eedc/{anlage_id}_{name}/energy/inv/{inv_id}_{name}/ladung_kwh` | Zählerstand (kumuliert) | Anlage: `keine_dienstliche_wallbox` |
| `ladung_extern_kwh` | Extern | kWh | kein MQTT-Topic — Monatsabschluss (Hand oder HA-Sensor) | — | — |
| `ladung_extern_euro` | Extern Kosten | € | kein MQTT-Topic — Monatsabschluss (Hand) | — | — |
| `v2h_entladung_kwh` | V2H Entladung | kWh | `eedc/{anlage_id}_{name}/energy/inv/{inv_id}_{name}/v2h_entladung_kwh` | Zählerstand (kumuliert) | `v2h_faehig` |

Live-Topics:

| Feld | Label | Einheit | Topic | Payload | Bedingung |
|---|---|---|---|---|---|
| `leistung_w` | Ladeleistung | W | `eedc/{anlage_id}_{name}/live/inv/{inv_id}_{name}/leistung_w` | Zahl (Momentanwert) — 5-Minuten- und Stundenmittel | — |
| `soc` | Ladestand | % | `eedc/{anlage_id}_{name}/live/inv/{inv_id}_{name}/soc` | Zahl (Momentanwert) — 5-Minuten- und Stundenmittel | — |
| `ladezustand_fahrzeug` | Ladezustand (Fahrzeug) | — | `eedc/{anlage_id}_{name}/live/inv/{inv_id}_{name}/ladezustand_fahrzeug` | Zustand: `nicht_verbunden` (auch `not_connected`) · `verbunden` (auch `plugged_not_charging`, `plugged_in`, `waiting_for_charging`) · `laedt` (auch `charging`) · `laedt_dc` (auch `dc_connected`, `dc_charging`) · `fertig` (auch `complete`, `fully_charged`, `finished_fully_charged`, `finished_not_full`, `target_reached`) · `fehler` (auch `error`) — Zustands-Mitschrift (Anteil der Stunde je Wert) | — |
| `reichweite_km` | Reichweite | km | `eedc/{anlage_id}_{name}/live/inv/{inv_id}_{name}/reichweite_km` | Zahl (Momentanwert) — nur Anzeige | — |
| `ziel_ladestand_prozent` | Ladeziel | % | `eedc/{anlage_id}_{name}/live/inv/{inv_id}_{name}/ziel_ladestand_prozent` | Zahl (Momentanwert) — nur Anzeige | — |
| `restzeit_min` | Restzeit | min | `eedc/{anlage_id}_{name}/live/inv/{inv_id}_{name}/restzeit_min` | Zahl (Momentanwert) — nur Anzeige | — |
| `zu_hause` | Zu Hause | — | `eedc/{anlage_id}_{name}/live/inv/{inv_id}_{name}/zu_hause` | Zustand: `zu_hause` (auch `home`) · `unterwegs` (auch `not_home`) — Zustands-Mitschrift (Anteil der Stunde je Wert) | — |

Heimladung am Auto: entweder `ladung_pv_kwh` und `ladung_netz_kwh` oder `ladung_kwh` (gesamt, für einen Zähler, der PV
und Netz nicht trennt — dann die beiden anderen leer lassen). Neben einer Wallbox zählt der Wert für dieses Auto, die
Wallbox trägt den Rest.

#### Wallbox

Energie-Topics:

| Feld | Label | Einheit | Topic | Payload | Bedingung |
|---|---|---|---|---|---|
| `ladung_kwh` | Ladung gesamt | kWh | `eedc/{anlage_id}_{name}/energy/inv/{inv_id}_{name}/ladung_kwh` | Zählerstand (kumuliert) | — |
| `ladung_pv_kwh` | Ladung PV | kWh | `eedc/{anlage_id}_{name}/energy/inv/{inv_id}_{name}/ladung_pv_kwh` | Zählerstand (kumuliert) | — |
| `ladevorgaenge` | Ladevorgänge | — | `eedc/{anlage_id}_{name}/energy/inv/{inv_id}_{name}/ladevorgaenge` | Zählerstand (kumuliert) | — |
| `netzbezug_eigener_tarif_kwh` | Netzbezug zum Wallbox-Tarif | kWh | `eedc/{anlage_id}_{name}/energy/inv/{inv_id}_{name}/netzbezug_eigener_tarif_kwh` | Zählerstand (kumuliert) | — |

Live-Topics:

| Feld | Label | Einheit | Topic | Payload | Bedingung |
|---|---|---|---|---|---|
| `leistung_w` | Leistung | W | `eedc/{anlage_id}_{name}/live/inv/{inv_id}_{name}/leistung_w` | Zahl (Momentanwert) — 5-Minuten- und Stundenmittel | — |
| `ladezustand` | Ladezustand | — | `eedc/{anlage_id}_{name}/live/inv/{inv_id}_{name}/ladezustand` | Zustand: `kein_fahrzeug` (auch `not_connected`, `1`) · `verbunden` (auch `sleep_mode`) · `wartet` (auch `3`) · `laedt` (auch `active_mode`, `2`) · `fertig` (auch `4`) · `gesperrt` (auch `station_locked`) · `fehler` (auch `station_fault`, `0`, `5`) — Zustands-Mitschrift (Anteil der Stunde je Wert) | — |
| `lademodus` | Lademodus | — | `eedc/{anlage_id}_{name}/live/inv/{inv_id}_{name}/lademodus` | Zustand: `aus` (auch `off`, `charge_stop`) · `pv` (auch `smart_charging`) · `smart` (auch `minpv`) · `schnell` (auch `now`, `boost_charging`, `3`) · `plan` (auch `5`) · `eco` (auch `4`) — nur Anzeige | — |
| `fahrzeug_am_ladepunkt` | Fahrzeug am Ladepunkt | — | `eedc/{anlage_id}_{name}/live/inv/{inv_id}_{name}/fahrzeug_am_ladepunkt` | Text (getrimmt, höchstens 80 Zeichen) — nur Anzeige | — |
| `evcc_verbunden` | evcc: Fahrzeug verbunden | — | `eedc/{anlage_id}_{name}/live/inv/{inv_id}_{name}/evcc_verbunden` | Zustand: `an` (auch `on`, `true`, `1`) · `aus` (auch `off`, `false`, `0`) — nur Anzeige | — |
| `evcc_laedt` | evcc: lädt | — | `eedc/{anlage_id}_{name}/live/inv/{inv_id}_{name}/evcc_laedt` | Zustand: `an` (auch `on`, `true`, `1`) · `aus` (auch `off`, `false`, `0`) — nur Anzeige | — |
| `evcc_freigegeben` | evcc: Laden freigegeben | — | `eedc/{anlage_id}_{name}/live/inv/{inv_id}_{name}/evcc_freigegeben` | Zustand: `an` (auch `on`, `true`, `1`) · `aus` (auch `off`, `false`, `0`) — nur Anzeige | — |
| `sitzung_kwh` | Energie dieser Sitzung | kWh | `eedc/{anlage_id}_{name}/live/inv/{inv_id}_{name}/sitzung_kwh` | Zahl (Momentanwert) — nur Anzeige | — |
| `sitzung_dauer_s` | Dauer dieser Sitzung | s | `eedc/{anlage_id}_{name}/live/inv/{inv_id}_{name}/sitzung_dauer_s` | Zahl (Momentanwert) — nur Anzeige | — |
| `ladestrom_a` | Ladestrom | A | `eedc/{anlage_id}_{name}/live/inv/{inv_id}_{name}/ladestrom_a` | Zahl (Momentanwert) — nur Anzeige | — |
| `phasen_aktiv` | Aktive Phasen | — | `eedc/{anlage_id}_{name}/live/inv/{inv_id}_{name}/phasen_aktiv` | Zahl (Momentanwert) — nur Anzeige | — |
| `ziel_ladestand_prozent` | Ladeziel | % | `eedc/{anlage_id}_{name}/live/inv/{inv_id}_{name}/ziel_ladestand_prozent` | Zahl (Momentanwert) — nur Anzeige | — |
| `restzeit_min` | Restzeit | min | `eedc/{anlage_id}_{name}/live/inv/{inv_id}_{name}/restzeit_min` | Zahl (Momentanwert) — nur Anzeige | — |

#### Sonstiges

Die Spalte „Art" ist die Kategorie des Geräts. Ohne gepflegte Kategorie erwartet eedc die Felder von Verbraucher,
Erzeuger und Speicher.

Energie-Topics:

| Art | Feld | Label | Einheit | Topic | Payload | Bedingung |
|---|---|---|---|---|---|---|
| `erzeuger` | `erzeugung_kwh` | Erzeugung | kWh | `eedc/{anlage_id}_{name}/energy/inv/{inv_id}_{name}/erzeugung_kwh` | Zählerstand (kumuliert) | — |
| `erzeuger` | `eigenverbrauch_kwh` | Eigenverbrauch | kWh | kein MQTT-Topic — Monatsabschluss (Hand oder HA-Sensor) | — | — |
| `erzeuger` | `einspeisung_kwh` | Einspeisung | kWh | kein MQTT-Topic — Monatsabschluss (Hand oder HA-Sensor) | — | — |
| `erzeuger` | `einspeise_erloes_euro` | Einspeise-Erlös | € | kein MQTT-Topic — Monatsabschluss (Hand) | — | — |
| `verbraucher` | `verbrauch_sonstig_kwh` | Verbrauch | kWh | `eedc/{anlage_id}_{name}/energy/inv/{inv_id}_{name}/verbrauch_sonstig_kwh` | Zählerstand (kumuliert) | — |
| `verbraucher` | `bezug_pv_kwh` | davon PV | kWh | kein MQTT-Topic — Monatsabschluss (Hand oder HA-Sensor) | — | — |
| `verbraucher` | `bezug_netz_kwh` | davon Netz | kWh | kein MQTT-Topic — Monatsabschluss (Hand oder HA-Sensor) | — | — |
| `abgabe` | `abgabe_kwh` | Abgabe | kWh | `eedc/{anlage_id}_{name}/energy/inv/{inv_id}_{name}/abgabe_kwh` | Zählerstand (kumuliert) | — |
| `abgabe` | `einspeise_erloes_euro` | Erlös | € | kein MQTT-Topic — Monatsabschluss (Hand) | — | — |
| `speicher` | `erzeugung_kwh` | Erzeugung/Entladung | kWh | `eedc/{anlage_id}_{name}/energy/inv/{inv_id}_{name}/erzeugung_kwh` | Zählerstand (kumuliert) | — |
| `speicher` | `verbrauch_sonstig_kwh` | Verbrauch/Ladung | kWh | `eedc/{anlage_id}_{name}/energy/inv/{inv_id}_{name}/verbrauch_sonstig_kwh` | Zählerstand (kumuliert) | — |
| `zaehler` | `zaehlerstand` | Zählerstand | vom Gerät (`zaehler_einheit`) | `eedc/{anlage_id}_{name}/energy/inv/{inv_id}_{name}/zaehlerstand` | Zählerstand (kumuliert) | — |

Live-Topics:

| Feld | Label | Einheit | Topic | Payload | Bedingung |
|---|---|---|---|---|---|
| `leistung_w` | Leistung | W | `eedc/{anlage_id}_{name}/live/inv/{inv_id}_{name}/leistung_w` | Zahl (Momentanwert) — 5-Minuten- und Stundenmittel | — |

#### Wechselrichter

Wechselrichter haben keine eigenen Topics: ihre Werte gehören zu den PV-Modulen und Speichern, denen sie zugeordnet sind
(`SKIP_TYPEN` in `services/mqtt_topic_registry.py`).

### Live-Mittelwerte: was eedc aus den Live-Topics mitschreibt

Jedes Live-Topic mit einer Zahl ist ein Momentanwert — senden bei jeder Aenderung genuegt (ein Wert gilt bis zur
naechsten Nachricht, wie in Home Assistant). Alle 5 Minuten haelt eedc daraus das **zeitgewichtete Mittel** des
Fensters fest (mit Minimum und Maximum) und bildet je abgeschlossener Stunde **Stundenmittel** — dasselbe, was Home
Assistant aus seinen 5-Minuten-Statistiken macht (seit Standalone-Gleichstand S2). Mitgeschrieben werden die
Live-Topics, deren Spalte „Payload" unter [Topics je Gerätetyp](#topics-je-gerätetyp) „5-Minuten- und Stundenmittel"
nennt (Leistung, Ladestand, Temperatur); den Betriebsmodus schreibt eedc als Anteil je Modus mit (siehe naechster
Abschnitt).

Daraus entstehen ohne Home Assistant u. a. das Temperatur-Diagramm, Ø Vorlauf und Ø Spreizung der Waermepumpe. Der
**Tagesverlauf** in *Cockpit → Live* zeigt ueber MQTT damit 5-Minuten-Mittel statt einzelner Momentanwerte, ab der
ersten Aufzeichnung — ohne Home Assistant auch ohne jede Zuordnung unter *Datenquellen* (reine Inbound-Anlage).

**Add-on mit MQTT-Geraeten (Mischform).** Laeuft eedc mit Home Assistant, liefern aber einzelne oder alle Geraete ihre
Leistung nur ueber diese Topics (kein HA-Sensor zugeordnet), zeichnet der Tagesverlauf auch sie aus den 5-Minuten-
Aufzeichnungen: ohne jede `live`-Zuordnung die ganze Kurve aus MQTT, sonst die Geraete ohne HA-Leistungssensor aus MQTT
neben den Geraeten aus HA — Netz, PV gesamt und Preis bleiben dann bei HA. Ein Geraet mit HA-Sensor bleibt bei HA. Die
Tagesaggregation liest dieselbe Kurve (Geraetewerte je Stunde). Voraussetzung: „Daten ueber MQTT empfangen (Import)" an.

- **Nicht rueckwirkend:** Die Stundenmittel beginnen mit der Zuordnung (dem ersten empfangenen Wert).
- **Broker-Ausfall:** Die Zeit ohne Verbindung bleibt eine Luecke; die Stunde ist das Mittel der uebrigen Minuten.
  Ein Absender, der verstummt, waehrend der Broker laeuft, behaelt seinen letzten Wert.
- **HA-Sensor geht vor:** Ist einem Feld ein HA-Sensor zugeordnet, gilt er — auch ohne Langzeitstatistik (der
  Daten-Checker nennt ihn dann); das MQTT-Topic wird fuer die Stundenmittel nicht gelesen.
- **Strompreis:** `strompreis_ct` zeigt eedc nur im Tagesverlauf; Stundenpreise und Kosten entstehen nur aus einem
  HA-Preissensor.

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

### Zustand und Sitzung der E-Mobilität

Wallbox und E-Auto haben eigene Live-Topics für den Überblick im Komponenten-Hub — Topic = Registry-Feld unter
`…/live/inv/{id}_{name}/`. Welche das sind und welche Werte eedc je Zustand versteht, steht in den Live-Tabellen von
[Wallbox](#wallbox) und [E-Auto](#e-auto) unter Topics je Gerätetyp (Spalte „Payload").

```
eedc/1_Meine_PV/live/inv/4_SMA_eCharger_22/ladezustand → laedt
eedc/1_Meine_PV/live/inv/4_SMA_eCharger_22/sitzung_kwh → 9.8
eedc/1_Meine_PV/live/inv/5_Smart_1/reichweite_km     → 312
```

- Zustände wie der Betriebsmodus: bei jeder Änderung senden (retained empfohlen); die volle Werte-Tabelle steht im
  Handbuch Einstellungen §7.10 und am Feld in *Einstellungen → Datenquellen*. Ein fremder Wert ergibt keinen Chip; der
  Daten-Checker nennt ihn („E-Mobilität – unbekannter Zustand").
- **Reine Anzeige:** eedc speichert diese Werte nicht (kein Stundenmittel, kein Kanal) und rechnet keine Einheit um — die
  Sitzung in **kWh** senden (nicht Wh), die Restzeit in **Minuten**. **Ausnahme — die Zustands-Mitschrift:**
  für `ladezustand`, `ladezustand_fahrzeug` und `zu_hause` führt der Inbound wie beim Betriebsmodus
  ein **Haltezeit-Fenster je Gerät und Feld** (ein Zustand gilt bis zur nächsten Nachricht); der 5-Minuten-Snapshot
  schreibt daraus `inv:<id>:<feld>:<wert>` = Anteil des Fensters und an der Wallbox `inv:<id>:ladezustand:wechsel_laedt` =
  Zahl der Übergänge nach `laedt` im Fenster (nur > 0). Der Stundenlauf (:05) verdichtet sie je abgeschlossener Stunde in
  die Kanäle `zustand:inv:<id>:<feld>:<wert>` und `wechsel:inv:<id>:ladezustand:laedt` — daraus „Betrieb heute" und
  „Ladevorgänge heute". Eine Nachricht auf `evcc_verbunden`/`evcc_laedt`/`evcc_freigegeben` schreibt das Fenster des
  Ladezustands fort (Option A, dieselbe Regel wie unten; ein gesendeter `ladezustand` geht vor). Grenzen wie beim Modus: ab
  dem ersten Wert, nicht rückwirkend; Broker weg ⇒ Lücke; nach einem Neustart zählt die Stunde erst ab der nächsten
  Meldung, und der erste Wert ist **kein** Ladevorgang. `lademodus`, `fahrzeug_am_ladepunkt` und die drei `evcc_…`-Werte
  selbst werden nicht mitgeschrieben. Hat das Feld einen HA-Sensor, schreibt der HA-Weg mit, nicht MQTT.
- Der Zustand ist bis zu 60 s alt (derselbe Takt wie der Betriebsmodus).
- **Ladezustand aus drei Binär-Werten (Option A):** liefert `ladezustand` keinen Wert (nicht gesendet, `unknown`, fremder
  Wert), setzt eedc ihn aus `evcc_verbunden`/`evcc_laedt`/`evcc_freigegeben` zusammen: verbunden `aus` ⇒ `kein_fahrzeug`;
  verbunden `an` und laedt `an` ⇒ `laedt`; verbunden `an` und freigegeben `aus` ⇒ `wartet`; sonst `verbunden`. Ein
  gesendeter Ladezustand geht immer vor. ⚠ Der Cache hat keine Ablaufzeit: wer von `ladezustand` auf die drei Werte
  wechselt, sendet einmal `unknown` auf `ladezustand` (ein gelöschter retained-Wert erreicht eedc nicht).
- **Gateway an Zustandsfeldern:** an `ladezustand`, `lademodus`, `fahrzeug_am_ladepunkt`,
  `ladezustand_fahrzeug`, `zu_hause` und den drei `evcc_…`-Feldern reicht das Gateway den Text **unverändert** weiter
  (`plain`: der getrimmte Payload, auch leer; `json`/`json_array`: der Wert am Pfad als Text). Faktor und Offset gelten dort
  nicht. Ein Wort auf einem Zahlenfeld bleibt ein Transform-Fehler (Zähler `transform_fehler`, kein Republish). Am
  Betriebsmodus bleibt das Gateway aus — der Modus kommt über das Inbound-Topic.
- **Hat das Gerät in eedc einen HA-Sensor für das Feld, gilt der HA-Sensor**; das Topic wird dann nicht gelesen.
- **`fahrzeug_am_ladepunkt` — leer ist ein Wert.** Anders als bei einem Zustand legt eedc hier einen **leeren Payload** als
  Wert ab („die Steuerung kennt kein Fahrzeug") — evcc schreibt `nil` als leeren String. Hängt dann ein Fahrzeug dran
  (`ladezustand` verbunden · wartet · laedt · fertig), zeigt die Wallbox-Karte „Gastfahrzeug"; ein Name, der mit der
  „Kennung in der Steuerung" eines E-Autos übereinstimmt (Groß/Klein egal), nennt genau dieses Auto. `null`, `none` und
  `-` gelten ebenfalls als leer, `unknown`/`unavailable` als keine Antwort; länger als 80 Zeichen wird abgeschnitten. Nur
  dieses Textfeld hat die Weiche — ein leerer Betriebsmodus oder Ladezustand wird weiter verworfen.
  ⚠ Ein leerer **retained** Payload löscht die retained Nachricht am Broker: nach einem Neustart von eedc kommt bis zur
  nächsten Meldung der Steuerung keine Antwort an (dann gibt es keinen Gast, die Karte zeigt die Regel ohne Steuerung).
  Kein Startwert „0" für dieses Topic (es ist kein Zahlenfeld).

```
eedc/1_Meine_PV/live/inv/4_SMA_eCharger_22/fahrzeug_am_ladepunkt → Smart
eedc/1_Meine_PV/live/inv/4_SMA_eCharger_22/fahrzeug_am_ladepunkt → (leer)   # Gast, wenn ein Fahrzeug dranhaengt
```

#### Preset „evcc Ladepunkt"

Ein Gateway-Preset legt für **einen** evcc-Ladepunkt alle Zeilen auf einmal an (Wallbox-Investition wählen). Variablen:
`prefix` (Wurzel-Topic aus `evcc.yaml` → `mqtt: topic`, Vorgabe `evcc`) und `loadpoint` (Nummer in evcc, der erste ist `1`,
Vorgabe `1`). Die Einheiten stammen aus der evcc-Quelle (`server/mqtt.go`: Kommazahlen mit höchstens drei Nachkommastellen,
Dauern als ganze Sekunden, `true`/`false`, kein Wert als leerer Payload; retained):

| Quell-Topic (Vorlage) | Ziel in eedc | Umrechnung | Beschreibung (aus dem Preset) |
|---|---|---|---|
| `{prefix}/loadpoints/{loadpoint}/chargePower` | `live/inv/{inv_id}/leistung_w` | 1 | Ladeleistung in W |
| `{prefix}/loadpoints/{loadpoint}/sessionEnergy` | `live/inv/{inv_id}/sitzung_kwh` | 0,001 | Energie dieser Sitzung — evcc meldet Wh, Faktor 0,001 ⇒ kWh |
| `{prefix}/loadpoints/{loadpoint}/chargeDuration` | `live/inv/{inv_id}/sitzung_dauer_s` | 1 | Ladedauer dieser Sitzung in Sekunden |
| `{prefix}/loadpoints/{loadpoint}/chargeRemainingDuration` | `live/inv/{inv_id}/restzeit_min` | 1/60 | Restzeit — evcc meldet Sekunden, Faktor 1/60 ⇒ Minuten |
| `{prefix}/loadpoints/{loadpoint}/phasesActive` | `live/inv/{inv_id}/phasen_aktiv` | 1 | Aktive Phasen |
| `{prefix}/loadpoints/{loadpoint}/chargeTotalImport` | `energy/inv/{inv_id}/ladung_kwh` | 1 | Zählerstand der Wallbox in kWh (nur mit Lademeter) — eedc bildet daraus die Monatsdifferenz |
| `{prefix}/loadpoints/{loadpoint}/mode` | `live/inv/{inv_id}/lademodus` | — (Text) | Lademodus (off · smart · now; ältere evcc: pv · minpv) — Text |
| `{prefix}/loadpoints/{loadpoint}/connected` | `live/inv/{inv_id}/evcc_verbunden` | — (Text) | Fahrzeug verbunden (true/false) — Text |
| `{prefix}/loadpoints/{loadpoint}/charging` | `live/inv/{inv_id}/evcc_laedt` | — (Text) | Lädt (true/false) — Text |
| `{prefix}/loadpoints/{loadpoint}/enabled` | `live/inv/{inv_id}/evcc_freigegeben` | — (Text) | Laden freigegeben (true/false) — Text |
| `{prefix}/loadpoints/{loadpoint}/vehicleName` | `live/inv/{inv_id}/fahrzeug_am_ladepunkt` | — (Text) | Fahrzeugname der Steuerung — Text, leer heißt kein bzw. unbekanntes Fahrzeug |

- **Nicht im Preset:** Ladestand und Reichweite (`vehicleSoc`, `vehicleRange` — Werte des Autos, das Preset legt die Zeilen
  einer Wallbox; am E-Auto einzeln über das Gateway zuordnen) und `chargeCurrent`/`effectiveLimitSoc` (in der evcc-Doku
  nicht beschrieben).
- **`chargeTotalImport` ist ein fortlaufender Zählerstand** (kWh, nur mit Lademeter in evcc): das Preset legt ihn unter
  `energy/` ab, eedc bildet daraus Tag und Monat selbst (siehe oben, „Publiziere den fortlaufenden Stand"). Ohne Lademeter
  publiziert evcc das Topic nicht — die Zeile bleibt dann stumm.
- **Anlegen in der Oberfläche:** *Einstellungen → Datenquellen* → Wallbox → **„Preset
  anwenden …"** → „evcc Ladepunkt" (Vorgaben prüfen) → „Anwenden". Welche Presets an welchem Gerät stehen, sagt das Preset
  selbst (`typen`, z. B. `wallbox`); Presets ohne Gerät stehen an „Anlage / Zähler". Weiterhin möglich über die
  Programmierschnittstelle (`POST /api/live/mqtt/gateway/presets/apply` mit
  `{"preset_id": "evcc_ladepunkt", "anlage_id": 1, "investition_id": 4, "variablen": {"prefix": "evcc", "loadpoint": "1"}}`
  — leere Variablen bekommen die Vorgabe).
- **Ersetzen statt Doppeln:** vor dem Anlegen löscht eedc die **aktiven** Gateway-Zeilen derselben Felder (auch eine im
  Gateway-Picker angelegte Zeile mit Namensteil `live/inv/<id>_<name>/<feld>` — über die Investitions-ID ist es dasselbe
  Feld); die Antwort nennt sie (`ersetzt`). Andere Felder bleiben unberührt.
- **Quelle „Gateway":** danach stellt eedc jedes gemappte Feld in den Datenquellen auf **„Gateway"** mit dem Topic (bis dahin
  zeigten Preset-Felder „Inbound", weil die Preset-Zeilen das Topic ohne Namensteil tragen). Eine Zeile, deren Ziel kein
  Feld der Fläche ist, bleibt angelegt, ihre Quelle unverändert (Antwort `ohne_feld`). Das Gateway schreibt weiter auf
  `eedc/<anlage>/live/inv/<id>/<feld>`.
- evcc rundet Kommazahlen auf drei Nachkommastellen; das Gateway gibt Zahlen auf zwei Nachkommastellen weiter.

### Themen je Gerät

An Wärmepumpe, Wallbox und E-Auto kannst du unter *Einstellungen → Datenquellen* **Themen** mit frei gewählten
Einträgen anlegen ([Handbuch Einstellungen §7.11](HANDBUCH_EINSTELLUNGEN.md#711-themen-frei-gewählte-entitäten)). Jeder
Eintrag hat ein eigenes Live-Topic:

```
eedc/{anlage_id}_{anlage_name}/live/inv/{id}_{name}/thema_e{n}
```

- `e{n}` ist die Kennung des Eintrags (`e2`, `e5` …) — sie steht in der Zeile der Zuordnung und bleibt, auch wenn du den
  Eintrag umbenennst oder verschiebst. Eine gelöschte Kennung wird nie wieder vergeben.
- Der Payload ist **Text** und wird **wie geliefert** angezeigt (`locked`, `2.4`, `2026-11-02T07:00:00+00:00`) — keine
  Umrechnung, keine Einheit. Leer, `unknown` und `unavailable` gelten als „kein Wert".
- Publiziere **retained**: eedc liest den letzten Wert aus dem Cache; ohne retained steht nach einem Neustart nichts da.
- Der Wert wird nicht mitgeschrieben (kein Verlauf), und der Daten-Checker erwartet das Topic nicht.
- Über das **Gateway** reicht eedc ein Fremd-Topic als Text an `…/thema_e{n}` weiter (Faktor und Offset gelten nicht).

### Beispiel

Fuer eine Anlage "Meine PV" (ID 1) mit Speicher "BYD HVS" (ID 3):

```
eedc/1_Meine_PV/live/einspeisung_w          → 1100
eedc/1_Meine_PV/live/inv/3_BYD_HVS/leistung_w → -500
eedc/1_Meine_PV/live/inv/3_BYD_HVS/soc      → 72
eedc/1_Meine_PV/energy/pv_gesamt_kwh         → 627.0
eedc/1_Meine_PV/energy/inv/3_BYD_HVS/ladung_kwh → 128.6
```

**Hinweis:** Die numerische ID am Anfang (`1_`, `3_`) ist die DB-ID. Der Name danach ist optional und dient nur der Lesbarkeit. EEDC extrahiert nur die ID.

## Datenquellen-Prioritaet

MQTT-Inbound hat Konfidenz 91% und liegt zwischen Connector (90%) und HA Statistics (92%):

```
Gespeichert (85%) → Connector (90%) → MQTT-Inbound (91%) → HA Statistics (92%)
```

**Diese Reihenfolge gilt nur fuer den laufenden Monat.** Dort ist sie eine
Live-Vorschau: die frischere Quelle gewinnt, wer HA Statistics hat, sieht deren
Werte statt der MQTT-Werte.

Im **abgeschlossenen** Monat gilt das Gegenteil: gespeicherte Werte sind
authoritativ. Connector und HA-Statistics fuellen dort nur Felder, die noch
leer sind, und ueberschreiben nichts rueckwirkend; MQTT-Inbound wird fuer
vergangene Monate gar nicht erst abgefragt. Ein importierter Monatswert
(Cloud-, Portal- oder CSV-Import) bleibt damit stehen, auch wenn fuer dasselbe
Feld ein HA-Sensor zugeordnet ist — die Zuordnung muss dafuer niemand
entfernen.

**Das ist die Anzeige-Seite.** Beim *Schreiben* gilt eine eigene Hierarchie
(`backend/core/source_priority.py`): Cloud-/Portal-Import und HA-Statistik-
Import liegen dort auf **derselben** Stufe, bei gleicher Stufe gewinnt der
spaetere Schreiber. Ein HA-Statistik-Import mit angehaktem „ueberschreiben"
ersetzt also einen importierten Wert dauerhaft. Nur ein im Formular gepflegter
Wert (Stufe `manual:form`) ist gegen beide geschuetzt.

SoT der Regeln: Anzeige
`backend/core/berechnungen/datenquellen.py::merge_datenquellen`, Schreiben
`backend/services/provenance.py::write_with_provenance`.

## Home Assistant als Sender

Einen eingebauten Automations-Generator gibt es seit der Oberfläche 4.0 nicht mehr. Wer Werte aus Home Assistant
per MQTT an eedc schickt, legt die Automation selbst an — Vorlage im nächsten Abschnitt. Im HA-Add-on ist das
in der Regel unnötig: dort ordnest du HA-Sensoren direkt unter *Einstellungen → Datenquellen* zu, ohne MQTT.
Die erwarteten Topics deiner Anlage zeigt der Block **MQTT-Topics** am Ende der Datenquellen-Fläche zum Kopieren.

## Beispiel-Flows (andere Systeme)

Die folgenden Beispiele zeigen die manuelle Konfiguration fuer andere Smarthome-Systeme.

### Home Assistant Automation

```yaml
automation:
  - alias: "EEDC PV-Leistung senden"
    trigger:
      - platform: state
        entity_id: sensor.pv_power
    action:
      - service: mqtt.publish
        data:
          topic: "eedc/1_Meine_PV/live/inv/2_SMA_Tripower/leistung_w"
          payload: "{{ states('sensor.pv_power') }}"
```

Mehrere Sensoren:

```yaml
automation:
  - alias: "EEDC Live-Daten senden"
    trigger:
      - platform: time_pattern
        seconds: "/5"
    action:
      - service: mqtt.publish
        data:
          topic: "eedc/1_Meine_PV/live/einspeisung_w"
          payload: "{{ states('sensor.grid_export_power') }}"
      - service: mqtt.publish
        data:
          topic: "eedc/1_Meine_PV/live/netzbezug_w"
          payload: "{{ states('sensor.grid_import_power') }}"
      - service: mqtt.publish
        data:
          topic: "eedc/1_Meine_PV/live/inv/2_SMA/leistung_w"
          payload: "{{ states('sensor.pv_power') }}"
      - service: mqtt.publish
        data:
          topic: "eedc/1_Meine_PV/live/inv/3_BYD/leistung_w"
          payload: "{{ states('sensor.battery_power') }}"
      - service: mqtt.publish
        data:
          topic: "eedc/1_Meine_PV/live/inv/3_BYD/soc"
          payload: "{{ states('sensor.battery_soc') }}"
```

### Node-RED

Einfacher Flow: Sensor-Node → MQTT-Out-Node

```json
[
  {
    "id": "eedc_pv",
    "type": "mqtt out",
    "topic": "eedc/1_Meine_PV/live/inv/2_SMA/leistung_w",
    "broker": "localhost",
    "name": "EEDC PV-Leistung"
  }
]
```

Fuer mehrere Werte einen Function-Node verwenden, der die Sensor-Werte auf die passenden Topics mappt.

### ioBroker (JavaScript-Adapter)

```javascript
// Live-Leistung senden
on('sourceDP.pv_power', (obj) => {
    sendTo('mqtt.0', 'publish', {
        topic: 'eedc/1_Meine_PV/live/inv/2_SMA/leistung_w',
        message: String(obj.state.val)
    });
});

// Batterie SoC senden
on('sourceDP.battery_soc', (obj) => {
    sendTo('mqtt.0', 'publish', {
        topic: 'eedc/1_Meine_PV/live/inv/3_BYD/soc',
        message: String(obj.state.val)
    });
});

// Netz-Werte senden
on('sourceDP.grid_export', (obj) => {
    sendTo('mqtt.0', 'publish', {
        topic: 'eedc/1_Meine_PV/live/einspeisung_w',
        message: String(obj.state.val)
    });
});
```

### FHEM

```perl
# MQTT2-Geraet fuer EEDC anlegen
define eedc_mqtt MQTT2_DEVICE

# PV-Leistung bei Aenderung senden
define eedc_pv notify pv_power:.* {\
  fhem("set mqtt2 publish eedc/1_Meine_PV/live/inv/2_SMA/leistung_w " . ReadingsVal("pv_power","state","0"))\
}
```

### openHAB

```java
rule "EEDC PV-Leistung senden"
when
    Item PV_Power changed
then
    val mqttActions = getActions("mqtt", "mqtt:broker:myBroker")
    mqttActions.publishMQTT("eedc/1_Meine_PV/live/inv/2_SMA/leistung_w", PV_Power.state.toString)
end
```

## Testen

### Kommandozeile (mosquitto_pub)

```bash
# Einzelnen Wert senden
mosquitto_pub -h localhost -t "eedc/1_Meine_PV/live/inv/2_SMA/leistung_w" -m "4200"

# Alle Topics subscriben (Monitoring)
mosquitto_sub -h localhost -t "eedc/#" -v
```

### In EEDC pruefen

1. In der MQTT-Einrichtung unter "Empfangene Werte" auf "Aktualisieren" klicken
2. Im Live-Dashboard pruefen ob die Werte angezeigt werden

## Hinweise

- **Payload-Format:** Zahlen (z.B. `4200`, `72.5`), kein JSON. Ausnahmen: die Zustands- und Textfelder (Spalte „Payload" unter [Topics je Gerätetyp](#topics-je-gerätetyp), darunter `betriebsmodus` mit Wort oder Code) und die [Themen](#themen-je-gerät).
- **Einheiten:** Leistung in **Watt** (nicht kW), Energie in **kWh** — die Einheit jedes Topics steht in der Spalte „Einheit" unter [Topics je Gerätetyp](#topics-je-gerätetyp).
- **Batterie:** Positive Werte = Ladung, negative = Entladung
- **Retained Messages:** EEDC publisht beim Speichern Initialwerte (0) als Retained, damit Topics am Broker sichtbar sind — nicht auf `betriebsmodus`: dort hiesse `0` „Aus".
- **Reconnect:** Bei Verbindungsverlust verbindet sich der Subscriber automatisch nach 10 Sekunden neu.
- **Monatsabschluss:** Energy-Topics erscheinen automatisch als Vorschlaege im Monatsabschluss-Wizard (Konfidenz 91%). Kein zusaetzliches Mapping noetig.
