## 5. E-Auto

> **Die Wallbox ist die Summe, ein Auto mit eigener Messung trägt seine eigene Heimladung (seit v4.0.51).** Die Heim-Felder `ladung_pv_kwh` („Heim: PV“), `ladung_netz_kwh` („Heim: Netz“) und `ladung_kwh` („Heim: gesamt“) werden **jedem** E-Auto angeboten, auch neben einer Wallbox. Trägt ein Auto dort einen Wert (auch 0) oder — im laufenden Monat — eine zugeordnete Quelle, zählt dieser Wert für dieses Auto; die Wallbox trägt den Rest, und der Rest geht nach Kilometern an die privaten Autos ohne eigene Messung ([Berechnungen, Heimladung je Auto](BERECHNUNGEN.md)). Nur an einem **Dienstwagen neben einer dienstlichen Wallbox** fehlen die Felder: dort ist die dienstliche Wallbox die dienstliche Ladung. Km-, Verbrauchs-, Extern- und V2H-Felder bleiben in jedem Fall am E-Auto. Ist die Summe der Autos größer als die Wallbox, meldet der Daten-Checker es.

### Monatserfassung

<!-- erzeugt: eingabefelder typ=e-auto liste=monat -->

> **Aus der früheren Spalte „Beschreibung"** — was die Hinweise der Tabelle (noch) nicht sagen:
>
> - `ladung_kwh`: Zu Hause in dieses Auto geladene Energie **gesamt** — für einen Zähler am Auto, der PV und Netz nicht trennt (z. B. evcc „Ladevorgänge: Energie [Fzg.]“; er springt am Ende jedes Ladevorgangs um dessen Menge). Neben einer Wallbox mit Ladezähler ordnet eedc jeden solchen Sprung den Stunden der Wallbox zu: die Menge bleibt der Sprung, PV-Anteil und Monat kommen aus den Stunden des Vorgangs ([Berechnungen, Ladevorgänge je Auto](BERECHNUNGEN.md)). Ohne diese Zuordnung (Monatswert von Hand, Monat nicht ganz neu gerechnet) wird mit dem PV-Anteil der Wallbox im Monat geteilt, ohne Wallbox wie „Heim: PV“ abgeleitet. Mit „Heim: PV“/„Heim: Netz“ leer lassen. Ein alter Wert in diesem Feld aus der Zeit vor v4.0.51 mit „Herkunft unbekannt“ zählt neben einer Wallbox nicht.
> - `verbrauch_kwh`: Gefahrener Energieverbrauch des E-Autos (reiner **Fahrverbrauch**), für die kWh/100 km-Effizienz mit `km_gefahren` verrechnet und beim Plug-in-Hybrid für den elektrischen Anteil. **Keine Ladung:** Als Heimladung setzt eedc ihn nur als ausdrücklich gekennzeichnete **Schätzung** ein, wenn für die Heimladung weder ein Wert (auch 0) noch — im laufenden Monat — eine Quelle bekannt ist ([Berechnungen, Heimladung und Fahrverbrauch](BERECHNUNGEN.md)). Hat die Wallbox einen Sensor und im Monat 0 kWh geladen, ist die Heimladung 0. Optional — fehlt der Wert, nähert eedc die kWh/100 km aus der geladenen Energie (Heim + Extern) an (inkl. Ladeverluste). Mit kumulativem Zähler zusätzlich **„Fahrverbrauch heute"** (Karte „Heute", Zuwachs der abgeschlossenen Stunden; seit der nächsten Version).
> - `km_gefahren`: Gefahrene Kilometer im Monat. Sensor (Auto-Integration, OBD) oder manuell. Ohne Sensor: im Monatsabschluss den **Tachostand** eintragen — eedc rechnet die Differenz zum Vormonat und schlägt sie hier vor. **Mit Zähler** (seit der nächsten Version): live als **Kilometerstand** an der E-Auto-Karte (bis 60 s alt) und stündlich als Kanal — aus HA gespiegelt (Datenquellen-Wahl HA), sonst die MQTT-Mitschrift — für **„Gefahren heute"** (Karte „Heute", nur abgeschlossene Stunden).
> - `v2h_entladung_kwh`: Vehicle-to-Home Entladung. Nur bei V2H-fähigem Fahrzeug. Optional. Am Tag eine Tagesgröße (Eigenverbrauch, Gesamtverbrauch, Autarkie), keine Stunde; im Monat ab dem Abschluss.

### Live-Dashboard

<!-- erzeugt: eingabefelder typ=e-auto liste=live -->

> **Aus der früheren Spalte „Beschreibung"** — was die Hinweise der Tabelle (noch) nicht sagen:
>
> - `soc`: State of Charge des Fahrzeugakkus. 0–100%.
> - `ladezustand_fahrzeug`: Was das Auto meldet: `nicht_verbunden` · `verbunden` · `laedt` · `laedt_dc` · `fertig` · `fehler` (Werte-Tabelle: [Einstellungen §7.10](HANDBUCH_EINSTELLUNGEN.md#710-zustand-und-sitzung-e-mobilität)). Chip an der Auto-Karte, nur ohne Wallbox-Zuordnung; **stündlich mitgeschrieben** (Karte „Betrieb heute", ab Zuordnung). *Ab der nächsten Version.*
> - `zu_hause`: `device_tracker` des Autos: `home` ⇒ zu Hause, `not_home` ⇒ unterwegs; nur die Zone; **stündlich mitgeschrieben** (Karte „Betrieb heute", Standort). *Ab der nächsten Version.*
> - `reichweite_km`: Restreichweite. evcc nur, solange das Auto am Ladepunkt hängt. *Ab der nächsten Version.*

> Die fünf Zustands- und Sitzungsfelder (und die neun an der Wallbox, darunter das Textfeld „Fahrzeug am Ladepunkt") sind
> **reine Anzeige**: eedc liest sie live, speichert sie nicht und rechnet nicht mit ihnen (kein Kanal, keine Monatsmenge).
> Keine Einheiten-Umrechnung. Das Gegenstück zum Textfeld der Wallbox ist kein Sensor, sondern das Stammdatum
> **„Kennung in der Steuerung"** am E-Auto (Einstellungen → Investitionen).

### MQTT Energy Topics

Welche MQTT-Topics eedc für dieses Gerät erwartet — Energie- und Live-Topics je Feld —, steht in [MQTT-Inbound](MQTT_INBOUND.md#topic-struktur).

---

