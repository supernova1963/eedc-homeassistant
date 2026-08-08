# Konzept #263 — Split-Klimaanlagen besser unterstützen

> ## **Status (gemessen 2026-08-08): Fundament gebaut · Kern offen, an ein Testgerät gebunden**
>
> **Aus `docs/drafts/` nach `docs/` gewandert (2026-08-08).** Es erklärt den Roadmap-Punkt **#263 Klima-WP Phase 2** aus [#110](https://github.com/supernova1963/eedc-homeassistant/issues/110) und gehört zum offenen Issue [#263](https://github.com/supernova1963/eedc-homeassistant/issues/263).
> Es trägt bewusst **keine Versionsnummer, nur dieses Mess-Datum** (Muster aus #359) — ein Status,
> der eine Version nennt, altert garantiert.
>
> **Nicht auf der Website und nicht in der In-App-Hilfe:** `website/scripts/sync-docs.sh` und
> `scripts/sync-help.sh` arbeiten beide mit einer **Allowlist**, in der Konzepte und ADRs bewusst
> fehlen. Dieses Dokument ist im Repository lesbar — es ist kein Anwender-Handbuch.
>
> **Offen:** **K-1** (SEER) · **K-2** (Heizen-vs-Kühlen-Trennung, der Kern) · **K-3** (PV-Anteil je Klima-Komponente). ⚠ **Harte Vorbedingung für K-2/K-3: eine Klimaanlage mit Betriebsmodus-Sensor bei einem Tester** — ohne sie wird die Hersteller-Vielfalt blind gebaut (dieselbe Lehre wie bei den Kompressor-Starts, #238). Ein Melder hat einen Modus-Sensor, misst aber **drei Innengeräte über einen einzigen Zähler** — damit ist K-2 nur zur Hälfte entsperrt.


Status: **Konzept, Issue bleibt offen.** Kein Code in dieser Etappe.
Entwurf für einen #263-Kommentar (Freigabe ausstehend).

## Maßnahmen-Register (fortschreibbar — Stand 2026-08-02)

| # | Maßnahme | Status | Notiz |
| --- | --- | --- | --- |
| **K-0** | Subtyp „Luft-Luft (Klimaanlage)" (`wp_art = luft_luft`) · SCOP-Modus · Stromsensor genügt · Daten-Checker ignoriert fehlende Heizwärme | ✅ seit v3.30.3 | Fundament steht |
| **K-0b** | **Wegräumen, was es bei einer Klimaanlage nicht gibt:** keine Heizwärme-/Warmwasserbedarfs-Felder, keine konstruierte Ersparnis gegen Gas/Öl, keine daraus abgeleitete CO₂-Ersparnis — die Anlage wird als **Verbraucher** ausgewertet (Strom · PV-Anteil · Kosten) | ✅ gebaut 2026-08-02 | Die **unbeantwortete Hälfte des Issues** (3dmaster90: „Das sowas wie Warmwasser, Wärmebedarf etc. entfällt"). Einzige Maßnahme **ohne Testgerät**. Auslöser: das ROI-Dashboard wies rund **1.100 €/Jahr** und **2.210 kg CO₂** gegen eine nie ersetzte Gasheizung aus |
| **K-1** | **SEER** (Kühl-Effizienz) als Parameter | ⬜ | ~1–2 Tage. **Allein halbnützlich** — ohne K-2 ein Effizienz-Faktor ohne Bezugsgröße ⇒ **nicht zuerst bauen** |
| **K-2** | **Heizen-vs-Kühlen-Trennung** über Betriebsmodus-Sensor (+ Normalisierungs-Schicht, modus-gewichtete Aggregation, Serien-Split in 4 Read-Sites) | ⬜ **Kern, zuerst** | ~3–4 Tage + Live-Serien-Split |
| **K-3** | PV/Speicher/Netz-Anteil **pro Klima-Komponente** | ⬜ | klein (globale Quote als Näherung) bis groß (echte Prioritäts-Logik) — eigene Etappe |

> **Harte Vorbedingung für K-2/K-3:** eine **Test-Klimaanlage mit Modus-Sensor** bei einem Tester.
> Ohne sie wird die Hersteller-Vielfalt (Daikin/Mitsubishi/ESPHome) blind gebaut — dieselbe Lehre wie
> bei den Kompressor-Starts (#238). Deshalb wird das Paket **anlassgebunden** geführt — als
> [#263](https://github.com/supernova1963/eedc-homeassistant/issues/263) und in der Roadmap
> [#110](https://github.com/supernova1963/eedc-homeassistant/issues/110),
> nicht in der Feature-Folge. Verwandt: #331 PHEV-Anteile.

## Was seit v3.30.3 schon da ist

- Wärmepumpenart-Subtyp **„Luft-Luft (Klimaanlage)"** (`wp_art = luft_luft`).
- **SCOP-Modus** als Effizienz-Berechnungsmodus (EU-Label-Werte statt JAZ-Default).
- Stromverbrauchssensor reicht; Wärmemengenzähler optional (Klima-Realität).
- Daten-Checker ignoriert fehlende Heizwärme bei Klima-Subtyp.

## K-0b — die Klimaanlage als Verbraucher statt als halbe Wärmepumpe

**Warum das eine eigene Maßnahme ist und nicht Teil von K-0:** K-0 hat dafür gesorgt, dass eedc
eine Klimaanlage **nicht mehr nach Wärmedaten fragt**. Es hat aber nicht verhindert, dass eedc sich
die fehlenden Wärmedaten an anderer Stelle **selbst ausdenkt**. Genau das tat die ROI-Auswertung:
sie behandelte jede `waermepumpe` als Ersatz einer Gasheizung und füllte den dafür nötigen
Wärmebedarf aus den Vorbelegungen auf (12.000 kWh Heizwärme + 3.000 kWh Warmwasser). Ergebnis waren
rund **1.100 €/Jahr** und **2.210 kg CO₂** Ersparnis gegen eine Heizung, die es nie gab — während
dieselbe Komponente in der Nachhaltigkeits-Sicht **0 kg** trug.

**Der dritte Weg statt eines Typwechsels.** Naheliegend wäre gewesen, eine Klimaanlage als
`sonstiges/verbraucher` zu führen. Das kostet aber den **WP-Spezialtarif** (die Tarif-Kaskade kennt
nur `waermepumpe` und `wallbox`), erzwingt eine **Migration** und verwaist die Alttage der
Komponenten-Beiträge. Deshalb: **Typ bleibt `waermepumpe`** — aber solange keine Wärme gemessen
wird, **zeigt eedc das Gerät als Verbraucher**: Strom, PV-Anteil, Kosten. Die Wärme-Kennzahlen
erscheinen als Leerwert `—` mit sichtbarem Grund, nicht als 0.

**Was gebaut wurde (2026-08-02):**

- ROI-Dashboard konstruiert für `luft_luft` **keine** Ersparnis und **keine** CO₂-Ersparnis mehr;
  die Zeile bleibt mit ihren Anschaffungskosten sichtbar und trägt `nicht_bewertet` samt Begründung.
  Die Anlagen-Summen (Gesamt-Ersparnis, ROI %, Amortisation, Gesamt-CO₂) sind damit ebenfalls frei
  von dem Phantomwert.
- Das Investitionsformular fragt bei `luft_luft` **Heizwärme- und Warmwasserbedarf nicht mehr ab**
  und belegt sie nicht mehr vor.
- Die drei Daten-Checker-Hinweise, die ausschließlich den Gas-Vergleich füttern (Alternativkosten,
  alter Energiepreis, Heizwärmebedarf), entfallen für Klimaanlagen — sonst wären sie Forderungen
  ohne Zweck bzw. gar nicht mehr auflösbar.

**Was K-0b bewusst NICHT tut:** gespeicherte Werte löschen. Die Klima-Unterstützung ist nicht
abgeschlossen; was heute unbenutzt in `parameter` liegt, wird nicht weggeworfen. Und K-0b greift
**K-2 nicht vor**: es entfernt nur das falsche Vokabular (Heizwärme/Warmwasser), statt ein neues zu
setzen — die Heizen-/Kühlen-Trennung rechnet später in `strom_heizen_kwh`/`strom_kuehlen_kwh`.

> **Angrenzend, bewusst offen:** Auch eine klassische Wärmepumpe im **Neubau** ersetzt keine
> Heizung, bekommt aber weiterhin eine Gaskessel-Ersparnis angerechnet — `alter_energietraeger`
> kennt kein „nichts ersetzt", und der Default ist Gas. Das ist **nicht** Klima-spezifisch und
> gehört nicht in dieses Konzept; es ist als eigener Fund notiert.

## Drei offene Bausteine — Architektur + Aufwand

### 1. SEER (Kühl-Effizienz, Pendant zum SCOP) — klein, aber allein halbnützlich
- Reine Parameter-Erweiterung analog SCOP: `seer_kuehlung` in
  `core/investition_parameter.py` (+ Frontend `lib/investitionParameter.ts`),
  Form-Feld in `InvestitionForm.tsx`, Branch in `core/calculations.py
  ::berechne_wp_einsparung`.
- **Haken:** Eine SEER-Zahl ohne getrennte Kühl-kWh sagt nicht, *wie viel* Strom
  ins Kühlen ging. Ohne Baustein 2 ist das ein Effizienz-Faktor ohne Bezugsgröße
  → erst zusammen mit der Modus-Trennung wirklich aussagekräftig.
- Aufwand: ~1–2 Tage.

### 2. Heizen-vs-Kühlen-Trennung über Modus-Sensor — der eigentliche Kern
- Neuer optionaler **Betriebsmodus-Sensor** im `sensor_mapping`
  (`live_sensor_config.py`, WP-Felder), Werte heizen/kühlen/idle. Modus-Sensor
  ist herstellerabhängig (Daikin/Mitsubishi/ESPHome) → braucht eine
  Normalisierungs-Schicht (analog zur Strompreis-/Counter-Mapping-Logik).
- Modus-gewichtete Aggregation: Stromverbrauch je Modus getrennt in
  `verbrauch_daten` (z. B. `strom_heizen_kwh` / `strom_kuehlen_kwh`),
  Snapshot-Aggregator schreibt pro Modus.
- Auswirkung auf Read-Sites: Cockpit-WP-Komponente, Monatsbericht, Energieprofil,
  Live-Tagesverlauf (getrennte Serien Heizen/Kühlen wie heute Heizen/Warmwasser).
- Aufwand: ~3–4 Tage (Sensor-Mapping + Aggregation), Live-Serien-Split zusätzlich.

### 3. PV/Speicher/Netz-Aufteilung pro Klima-Komponente — größter Brocken
- Heute wird der PV-/Netz-Anteil **global auf Anlagenebene** gerechnet
  (`calculations.py`), nicht pro Verbraucher. Eine komponenten-spezifische
  Quote (analog zum E-Mob-Pool-Attribution-Pfad) wäre nötig, um „wie viel
  Klima-Strom kam aus PV" sauber zu zeigen.
- Einfache Variante: globale PV-Quote auf den Klima-Stromverbrauch anwenden
  (grobe Näherung). Saubere Variante: Prioritäts-Aufteilung (Speicher lädt
  zuerst aus PV, dann Klima) → Snapshot-Aggregator-Erweiterung.
- Aufwand: klein (Näherung) bis groß (echte Prioritäts-Logik).

## Vorgeschlagene Reihenfolge (wenn umgesetzt wird)

1. **Baustein 2 zuerst** (Modus-Trennung) — er schafft die Bezugsgröße, ohne die
   SEER und Komponenten-Aufteilung in der Luft hängen.
2. **Baustein 1 (SEER)** direkt danach, dann hat die Kühl-Effizienz auch Kühl-kWh.
3. **Baustein 3** als eigene Etappe, zunächst als globale Näherung mit klarem
   Hinweis, später ggf. Prioritäts-Logik.

Voraussetzung für belastbares Bauen ist eine **Test-Klimaanlage mit
Modus-Sensor** bei einem Tester — sonst bauen wir die Hersteller-Vielfalt blind
(gleiche Lehre wie bei den Kompressor-Starts, #238).

## Bezug

- Roadmap-SoT #110. Verwandte Klima-Diskussion: alex_s9027 #548, 3dmaster90 #263.
- Keine eedc-community-/Datenmodell-Synchronisation nötig (rein lokal).
