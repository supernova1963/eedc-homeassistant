## 7. Sonstiges (Erzeuger / Verbraucher / Abgabe an Dritte / Speicher / Verbrauchszähler)

### Monatserfassung

<!-- erzeugt: eingabefelder typ=sonstiges liste=monat -->

> **Aus der früheren Spalte „Beschreibung"** — was die Hinweise der Tabelle (noch) nicht sagen:
>
> - `erzeugung_kwh` (Erzeuger): Erzeugte Energie (z.B. BHKW, Windrad). Zählt hinter dem Hauszähler in die Eigenverbrauchs-/Autarkie-Bilanz.
> - `abgabe_kwh` (Abgabe an Dritte): **Seit 05.09.2026.** An Dritte abgegebene Energie (Mieterstrom, Allgemeinstrom, Nachbarhaus) — Zähler an der Übergabestelle, kumulativ oder Tagessensor. Weder Eigenverbrauch noch Netz-Einspeisung; eedc zieht sie vom Eigenverbrauch ab (Autarkie und Quote sinken entsprechend). Ohne Zähler gibt es keine Schätzung.
> - `zaehlerstand` (Verbrauchszähler): #377 — der abgelesene Stand eines Gas-, Wasser- oder Ölzählers. **Erfasst, nicht bewertet:** geht in keine Bilanz, keine Quote, keine Wirtschaftlichkeit, kein CO₂ und nicht in die Gemeinschaftsdaten.

> ⚠ **Der Zählerstand ist bewusst einheitenlos gespeichert.** Was neben der Zahl
> steht (m³, l, kg, t, kWh), gehört zum **Gerät** (`zaehler_einheit`) und wird
> nur zur Anzeige geholt — eedc rechnet Zählerstände nie um. Genau diese leere
> Einheit ist die Sicherung dagegen, dass ein Gasverbrauch in der Strombilanz
> landet.
>
> **Sensor-Anforderung:** ein monoton steigender Zählerstand
> (`state_class: total_increasing`). Ein Sensor, der den *Verbrauch je Tag*
> liefert und nachts zurückspringt, passt hier **nicht** — eedc bildet die
> Menge aus der Differenz zweier Stände.
>
> **Zählerwechsel:** altes Gerät stilllegen (Stilllegungsdatum setzen, `aktiv`
> **an** lassen) und ein neues anlegen. Details:
> [Handbuch Einstellungen §3.4a](HANDBUCH_EINSTELLUNGEN.md).

### Live-Dashboard

<!-- erzeugt: eingabefelder typ=sonstiges liste=live -->

> Ein **Verbrauchszähler** hat kein Live-Feld: Er führt keine Leistung, und eine
> m³-Reihe auf der kW-Achse des Energieflusses wäre eine Einheiten-Verwechslung.
> Sein aktueller Stand steht stattdessen in *Live → Auf einen Blick* unter
> **Zählerstände**.

---

