# Was ist neu

> **Stand:** Mai 2026 (v3.25.20)
> **Diese Seite** zeigt pro Version, was sich für dich als Anwender geändert hat — kürzer als der technische [CHANGELOG](https://github.com/supernova1963/eedc-homeassistant/blob/main/CHANGELOG.md), ausführlicher als die Schnellübersicht-Tabelle in der [Übersicht](BENUTZERHANDBUCH.md#was-ist-neu-seit-v316).
>
> **Kein Banner, kein Pop-up:** EEDC zeigt diese Liste nicht ungefragt an. HA-Add-on-Nutzer sehen den Changelog ohnehin schon im Add-on-Store, GitHub-Releases haben einen eigenen. Wer wissen will, was neu ist, schaut hier rein — Pull statt Push.
>
> **Lesehinweis:** Die jüngsten Versionen stehen oben. Jeder Punkt verlinkt entweder auf die zuständige Hilfe-Sektion oder direkt auf die App-Funktion (sofern erreichbar). Anker-URLs (`?doc=was-ist-neu`) sind teilbar.

---

## v3.25.x — Investitions-Parameter aufgeräumt (April–Mai 2026)

### Daten-Checker: keine Fehlalarme mehr für Strompreis-Sensor und Dienstwagen-E-Autos *(v3.25.20)*

> 🩹 **Zwei Warnungen, die für viele Anwender keine waren** — nach Joachim-PN-Folge zu v3.25.19:
>
> - **Strompreis-Sensor wird nicht mehr als kWh-Counter geprüft.** Die Warnung „1 kWh-Sensor(en) nicht in HA-Long-Term-Statistics" mit Verweis auf `sensor.grid_price_monitor_average_price_today` (oder einen vergleichbaren Tibber-/aWATTar-/EPEX-Sensor) war ein Fehlalarm — der Strompreis ist ct/kWh, kein kumulativer Energiezähler. Wir lesen ihn nur live für die Tagesverlauf-Anzeige; ein fehlendes `state_class` ist hier irrelevant. Warnung verschwindet automatisch nach dem Update.
> - **Dienstwagen-E-Autos werden im „Energieprofil – Zähler-Abdeckung"-Check übersprungen.** Bisher meldete der Check „verbrauch_kwh oder ladung_kwh fehlt" auch für E-Autos, die als Dienstwagen markiert sind — bei einem Dienstwagen ist die Forderung aber sinnlos: kein PV-Bezug, keine Verbrauchsbilanz, keine ROI-Auswertung. Den Skip hatten wir schon in den ROI-Checks, aber im Abdeckungs-Check vergessen. Wer also ein E-Auto mit gesetzter „Dienstwagen"-Markierung hat, sieht die Warnung nicht mehr.

→ [Daten-Werkzeuge → Daten-Checker](HANDBUCH_EINSTELLUNGEN.md)

### UX-Konsistenz-Bündel: Cockpit-Reihenfolge, Statistik-Import-Lesbarkeit, Kompressor-KPI *(v3.25.19)*

> ✨ **Sichtbar an mehreren Stellen** — Sammlung kleiner Schliff-Items aus den Issues #185, #186, #187, #188 (detLAN + rapahl):
>
> - **Wallbox vor E-Auto vor Wärmepumpe** als globale Reihenfolge — wirkt auf Cockpit-Subtabs, HA-Sensoren-Export-Liste, Sensor-Mapping-Wizard, Statistik-Import. Wallbox+E-Auto bilden ein Paar (fest installierte Anschlussstelle + mobiler Verbraucher), Wärmepumpe folgt danach. (#187/2)
> - **Statistik-Import lesbar** — Basis-Felder erscheinen mit deutschen Labels („Einspeisung", „Netzbezug", „PV Erzeugung Gesamt") statt Backend-Schlüsseln (`einspeisung`, `netzbezug`, `pv_gesamt`). Kompressor-Starts heißen so statt `wp_starts_anzahl`. Investitions-Typen werden als „Wallbox" / „E-Auto" / „Wärmepumpe" angezeigt, nicht als Klein-Slugs. Monatsliste chronologisch absteigend (aktuellster Monat oben). (#187/1, #186/3)
> - **Cockpit-Übersicht** — Sektion „E-Auto & Wallbox" heißt jetzt „Wallbox & E-Auto", und die E-Auto-Komponenten erscheinen unter den Wallbox-Komponenten — konsistent zur globalen Reihenfolge. (#186/1)
> - **HA-Sensoren-Export → Verfügbare Sensoren** — Kategorien-Reihenfolge nach detLAN-Vorschlag: Anlage → Energie → Speicher → Investition (+ Komponenten-Detailkategorien) → Finanzen → Quoten → Umwelt → Status. (#186/4)
> - **Monatsbericht KPI-Kachel „Kompressor-Starts"** — zeigt jetzt die Monats-Summe groß und das Tages-Maximum klein im Subtitel — konsistent zu allen anderen Σ-Werten. (Vorher: Max groß, Σ klein.) (#185)
> - **Kraftstoff-Box bedingt** — Der Hinweis „Kraftstoffpreise nachpflegen" erscheint nur noch, wenn mindestens eine E-Auto-Investition gepflegt ist; sonst ist die Information für die Anlage irrelevant. Wirkt in **Daten → Monatsdaten** und in **Daten → Energieprofil**. (#188 rapahl)
> - **Sensor-Mapping „keine HA-Statistik"-Badge** — erscheint nur noch bei kumulativen kWh-Sensoren, wo eine Long-Term-Statistik tatsächlich gebraucht wird. Bei Live-Leistungs-Sensoren (W), SoC-Werten (%) oder Temperaturen (°C) ist der Badge weg — die werden direkt aus dem HA-State gelesen, da gibt es keine Statistik-Voraussetzung. (Joachim-PN nach Wattpilot-Mapping)

→ [Auswertungen → Energieprofil](HANDBUCH_BEDIENUNG.md#42-auswertungen)

### „Tag neu aggregieren" mit Vorschau-Tabelle vor Übernahme *(v3.25.18)*

> 🩹 **User-sichtbare Reparatur** — Wer in **Einstellungen → Daten → Energieprofil** auf das Reload-Symbol eines Tages klickt, sieht ab sofort zuerst eine Vergleichstabelle: pro Stunde und Energiefluss (PV / Einspeisung / Bezug / …) eine Spalte „Alt" (was steht in der DB) und eine Spalte „Neu" (was käme jetzt aus Home Assistant). Erst nach „Übernehmen" werden die Werte tatsächlich überschrieben. Differenzen über 1 kWh sind fett markiert, kleinere Abweichungen orange — auf einen Blick sichtbar, ob die Reparatur sinnvoll ist oder ob HA selbst gerade Müll liefert.
>
> Außerdem zwei Bug-Fixes im Reparatur-Pfad: Stunde 0 hängt rechnerisch vom Snapshot des Vortags um 23:00 ab — der wurde bisher beim Reload **nicht** mit überschrieben, sodass ein alter, korrupter Vortags-Wert den Spike beliebig oft wieder produzieren konnte. Ab v3.25.18 wird er mitgenommen. Dazu ist ein zweiter, älterer Mechanismus entfernt, der bei Tagesreset-Zählern (utility_meter daily) gelegentlich den falschen Wert in die Snapshot-Tabelle geschrieben hat — das war die Wurzel des ursprünglichen Issue #184. Wer ältere Counter-Spikes in der Historie hat, kommt damit jetzt mit einem Klick + „Übernehmen" sauber durch.
>
> **Außerdem im Bündel** — drei kleine UX-Items aus dem detLAN-Pakt: Tagesdetail-Pfeile blättern bis einschließlich heute (rollierend aktualisiert, vorher endete bei gestern). Der `Lade…`-Hinweis am Datums-Picker erscheint nur noch, wenn der Fetch länger als 250 ms braucht — kein Aufploppen-und-Weg-Flash mehr. Reihenfolge im Sensor-Mapping-Wizard: Wallbox steht jetzt vor E-Auto (konsistent zum Cockpit, fest installierte Komponente vor mobilem Verbraucher).

→ [Auswertungen → Energieprofil](HANDBUCH_BEDIENUNG.md#42-auswertungen)

### „Tag neu aggregieren" repariert prä-#184-Spikes jetzt wirklich *(v3.25.17)*

> 🩹 **User-sichtbare Reparatur** — Rainer hat nach v3.25.16 gemeldet, dass das Reparatur-Tool unter **Einstellungen → Daten → Energieprofil** den Counter-Spike vom 1. Mai nicht beseitigt, sondern nur „an den Tagesanfang verschoben" hat: PV plötzlich 1047 kW in Stunde 0:00, alle anderen Stunden ~0. Ursache war, dass das Reparatur-Tool nur Snapshots überschrieb, für die Home Assistant einen sauberen Wert liefert — wenn HA für einen Slot weiterhin `sum=NULL` zurückgibt (typisch nach HA-Restart, bevor `recompile_statistics` durchgelaufen ist), blieb der alte korrupte Snapshot stehen und der Spike kam aus den DB-Werten zurück.
>
> Ab v3.25.17: liefert HA für einen Slot `None`, wird der vorhandene Snapshot **gelöscht**. Die Aggregation sieht dann eine echte Lücke und überspringt die Stunde sauber, statt einen falschen Lifetime-Sprung als Stunden-Δ zu interpretieren. Der reguläre stündliche Snapshot-Job ist davon nicht betroffen — er behält sein defensives Verhalten, damit kein temporärer HA-Hänger einen frisch geschriebenen Slot wegnimmt.
>
> Wer noch einen alten Counter-Spike in der Historie hat: einmalig den betroffenen Tag unter **Einstellungen → Daten → Energieprofil** über das Reload-Symbol neu aggregieren — der Spike sollte danach weg sein (oder als Lücke sichtbar bleiben, falls HA für die Stunde wirklich keinen Wert mehr hat).

→ [Daten-Werkzeuge](HANDBUCH_EINSTELLUNGEN.md)

### WP-Kompressor-Starts: Σ Lebensdauer kommt direkt aus dem Hersteller-Sensor *(v3.25.16)*

> ⚠ **User-sichtbare Wert-Korrektur** — Nach v3.25.14 meldete detLAN, dass das Cockpit immer noch driftet (146 statt 134 Starts). Statt die Eichungs-Logik noch eine Runde nachzuschärfen, fliegt der ganze Selbstkalibrierungs-Mechanismus raus. Σ Lebensdauer im Cockpit zeigt ab sofort einfach das, was der Hersteller-Sensor sagt — keine Berechnung, keine Eichung, keine Drift-Möglichkeit. Wenn EEDC im Lauf der Zeit weniger Tagesinkremente erfasst als der Hersteller intern hochzählt (z. B. wegen Sensor-Aktivierungs-Lücken), bleibt das zwischen den Anzeigen sichtbar: Cockpit zeigt die Hersteller-Wahrheit, Monatsbericht zeigt was EEDC erfasst hat. Diagnose ohne versteckte Magic.

Bei reinen MQTT-Standalone-Setups ohne direkten HA-State-Zugriff fällt der Read auf die Statistics- bzw. den jüngsten Snapshot zurück — höchstens eine Stunde alt.

→ [Cockpit → Wärmepumpe](HANDBUCH_BEDIENUNG.md#41-cockpit)

### Tagesdetail-Ansicht: Vor/Zurück-Pfeile zum Blättern *(v3.25.15)*

> ✨ **Sichtbar in Auswertungen → Energieprofil → Tagesdetail** — Neben dem Datums-Eingabefeld stehen jetzt links und rechts kleine Chevron-Buttons (`<` `>`) zum Blättern um einen Tag. Genau das, was die Monats-Ansicht schon hat — die beiden Tabs sind nun symmetrisch in der Bedienung. Der „nächster Tag"-Button wird automatisch deaktiviert, sobald gestern erreicht ist (heute hat noch keinen abgeschlossenen Energieprofil-Tag).

→ [Auswertungen → Energieprofil](HANDBUCH_BEDIENUNG.md#42-auswertungen)

### WP-Kompressor-Starts: Σ Lebensdauer wächst nicht mehr im Tagesverlauf zu hoch *(v3.25.14)*

> ⚠ **User-sichtbare Wert-Korrektur** — Folgebefund zu v3.25.13: nach dem dortigen Wizard-Save-Fix beobachtete detLAN, dass die Σ-Lebensdauer-Anzeige im Lauf des Tages nach oben driftet — bei 7 realen Kompressor-Starts heute zeigte das Cockpit 136 statt 131. Ursache war keine fehlerhafte Sensor-Erfassung, sondern eine doppelte Buchhaltung des heutigen Tages: zum Save-Zeitpunkt floss er bereits in die Baseline-Berechnung ein, später dann nochmal in die Σ-Aggregation. Beide Stellen lasen den heutigen TagesZusammenfassung-Eintrag, der während des Tages aber noch instabil ist (Snapshot-Job läuft stündlich, der Tagesabschluss `morgen 00:00` existiert ja noch nicht).

Fix: heutiger Tag wird konsistent aus der TagesZusammenfassung-Aggregation ausgeschlossen, der heutige Verlauf kommt stattdessen aus einer Live-Hochrechnung (aktueller Hersteller-Counter minus Snapshot vom heutigen Tagesanfang). Σ Lebensdauer bleibt damit jederzeit synchron mit dem WP-Display, ohne im Lauf des Tages zu driften. Tooltip im Cockpit zerlegt die Anzeige jetzt in drei Anteile: Hersteller-Baseline + EEDC abgeschlossene Tage + heute live. Gleicher Fix gilt auch für die „Aktueller Monat"-Ansicht.

Bei reinen MQTT-Standalone-Setups ohne direkten Live-State-Zugriff fehlt der heutige Anteil bis zum Tagesabschluss — das ist bewusst so, lieber konservativ als doppelt gezählt.

→ [Cockpit → Wärmepumpe](HANDBUCH_BEDIENUNG.md#41-cockpit)

### Sensor-Zuordnung-Zusammenfassung: Großschreibung, Reihenfolge, Sensor-IDs nicht mehr abgeschnitten *(v3.25.14)*

> ✨ **Sichtbar im Sensor-Mapping-Wizard** — Der „Zusammenfassung"-Tab zeigte Investitions-Typen in Klammern als interne Schlüssel (`(e-auto)`, `(pv-module)`, `(speicher)`, `(waermepumpe)`, `(wallbox)`) statt als deutsche Bezeichnung. Feldnamen kamen ungekämmt aus den Backend-Schlüsseln: `pv erzeugung (kWh)`, `wp starts anzahl`, `km gefahren`. Auf breiten Bildschirmen wurde die Sensor-ID rechts trotzdem bei 200 Pixeln abgeschnitten — sichtbar als `…sensor.bat…`.

Behoben: Investitions-Typen jetzt mit deutschen Labels (`(E-Auto)`, `(PV-Module)`, `(Wärmepumpe)`, …), Feldnamen mit Akronym-Behandlung (`PV-Erzeugung (kWh)`, `Kompressor-Starts`, `Kilometer gefahren`), Investitions-Karten in fester Reihenfolge (PV → Wechselrichter → Speicher → BKW → WP → E-Auto → Wallbox → Sonstiges) statt API-Reihenfolge, und die Sensor-ID-Truncation greift nur noch auf schmalen Viewports — auf Desktop wird die volle ID angezeigt.

→ [Sensor-Zuordnung](HANDBUCH_EINSTELLUNGEN.md#11-ha-sensor-zuordnung-add-on)

### MQTT-Export: Kategorien mit deutschen Labels und passenden Icons *(v3.25.14)*

> ✨ **Sichtbar im HA-Sensor-Export-Tab** — Der „Verfügbare Sensoren"-Block listete mehrere Kategorien (Anlage, Quote, Investition, Speicher, Status, Wärmepumpe, E-Auto, Wallbox) als rohen Schlüssel mit Stecknadel-Icon, weil deren Mapping fehlte. Die Investitions-Sensoren-Kachel hatte das gleiche Problem in der Klammer; zusätzlich war die abgerundete Ecke der Karten beim Hover „defekt" — der Hintergrund schnitt über den Border.

Behoben: alle Kategorien haben jetzt deutsche Labels und sprechende Icons (Anlage 🏠, Quoten 📊, Investition 💼, Wärmepumpe 🔥, Speicher 🔋, E-Auto 🚗, Wallbox 🔌, Status ⚙️). Anzeige-Reihenfolge: Anlage zuerst, dann Auswertungs-Pyramide (Energie / Quoten / Finanzen / Umwelt), dann Investitions-Aspekte, Status zuletzt. Investitions-Sensoren-Block analog sortiert. Card-Border-Radius-Bug behoben.

→ [HA-Sensor-Export](HANDBUCH_EINSTELLUNGEN.md#13-ha-sensor-export)

### Wärmepumpe: „Heizenergie" → „Heizwärme" mit Tooltips elektrisch / thermisch *(v3.25.14)*

> ✨ **Sichtbar in der Monatsdaten-Eingabe** — In der Eingabemaske der WP-Monatsdaten wurde „Heizenergie" leicht mit „Stromverbrauch" verwechselt — beide klingen elektrisch. Wer in beiden Feldern denselben Wert eintrug (oder dachte, „Heizenergie" sei einfach der Strom), bekam einen COP von 1.0 angezeigt. Das ist der Verräter, aber für Erstnutzer nicht selbsterklärend.

Konsistent über alle Stellen umgestellt: das Eingabefeld heißt jetzt **„Heizwärme"** (nicht mehr „Heizenergie"), und unter jedem Eingabefeld steht ein erklärender Hinweis:

- **Stromverbrauch / Strom Heizen / Strom Warmwasser:** „Stromaufnahme … (elektrisch)"
- **Heizwärme:** „Abgegebene Heizwärme (thermisch) — COP = Heizwärme / Strom"
- **Warmwasser:** „Abgegebene Warmwasser-Wärme (thermisch)"

Wer beim Hovern über das Eingabefeld zusätzlich den HTML-Tooltip sehen möchte: derselbe Text steht auch dort. Der Backend-Schlüssel `heizenergie_kwh` und der CSV-Suffix `_Heizung_kWh` bleiben unverändert — bestehende CSV-Templates und Imports funktionieren weiter.

→ [Monatsdaten erfassen](HANDBUCH_BEDIENUNG.md#43-monatsdaten)

### WP-Kompressor-Starts-Baseline bleibt nach Investitionen-Speichern erhalten *(v3.25.13)*

> ⚠ **User-sichtbare Wert-Korrektur** — Wer einen Kompressor-Starts-Sensor seiner Wärmepumpe gemappt hat und die im Sensor-Zuordnung-Wizard gesetzte Baseline (Σ aller Lebensdauer-Starts vor dem ersten Tag bei EEDC) erleben möchte, hatte bisher folgendes Problem: jedes Schließen des Investitionen → Wärmepumpe-Dialogs mit „Speichern" — auch ohne irgendeine Datenänderung — setzte die Baseline auf `None` zurück. Cockpit → Wärmepumpe zeigte dann nur die Σ der EEDC-Tagesdifferenzen (also die Starts seit Inbetriebnahme), nicht den korrekten `Baseline + Σ Tagesdifferenzen`-Lebensdauer-Wert.

Hintergrund: das Investitionen-Form sammelte beim Speichern nur die im Form sichtbaren Felder ein und sendete das als komplettes neues `parameter`-Objekt ans Backend. Wizard-only-Felder wie `wp_starts_anzahl_baseline`, die der Sensor-Zuordnung-Wizard direkt in `parameter` schreibt aber nirgendwo im Form sichtbar macht, fielen dadurch raus.

Der Fix mergt jetzt das `parameter`-Objekt mit dem bestehenden statt es zu ersetzen — Wizard-Keys bleiben erhalten. **Nach dem Update einmalig Sensor-Zuordnung → Speichern & Abschließen**, dann ist die Baseline neu gesetzt und bleibt von da an stabil.

→ [Cockpit → Wärmepumpe](HANDBUCH_BEDIENUNG.md#41-cockpit)

### Mobile-Ansicht der Monatsberichte vollständig scrollbar *(v3.25.13)*

> ⚠ **Mobile-Sichtbar** — Wer die App auf einem Smartphone oder im DevTools-Mobile-Mode aufruft, kann jetzt mit aufgeklappter Energie-Bilanz auch die Sektionen darunter (Community-Vergleich, Speicher, Wärmepumpe, E-Mobilität, Balkonkraftwerk, Sonstiges) erreichen.

Vorher endete der Scroll-Bereich bei aufgeklappter Energie-Bilanz an der Finanzen-Sektion — alles darunter war zwar im DOM gerendert, aber außerhalb des Layout-Scroll-Bereichs. Auf Desktop war die Ansicht unbeeinflusst, weil dort der Sticky-Sidebar-Layout-Pfad greift.

→ [Cockpit → Monatsberichte](HANDBUCH_BEDIENUNG.md#41-cockpit)

### iOS-Smartphones / kleine Viewports: kein „Durchscrollen" mehr bis zur HA-Titelleiste *(v3.25.13)*

> ⚠ **Mobile-Sichtbar** — Auf iPhone SE und im HA-Companion-WebView konnte die EEDC-App so weit nach oben gescrollt werden, dass unter dem Footer eine leere Fläche entstand und nur noch die HA-App-Titelleiste sichtbar blieb. Der eigentliche App-Inhalt war dann oberhalb des Sichtbereichs.

Ursache war ein Drift zwischen dem dynamischen Viewport-Layout-Container (`100dvh`) und dem Document-Root, das auf iOS und in DevTools-Mobile-Simulationen unter bestimmten Viewports unabhängig scrollen konnte. Der Layout-Wrapper ist jetzt der einzige Scroll-Owner — Document-Root wurde an die Viewport-Höhe gepinnt.

iPhone 11 und iPhone 16 Pro hatten den Drift in der Praxis nicht gezeigt, das Symptom war auf kleine Viewports beschränkt.

### Stundenwerte-Spike durch Counter-Sensor-Ungereimtheit gefixt *(v3.25.13)*

> ℹ️ **Folge-Patch zu v3.25.10/v3.25.11** — Verstärkt die Counter-Spike-Vermeidung bei Sensoren, die in HA-Statistics zeitweise keinen `sum`-Wert lieferten (typisch nach Restart). Der `get_value_at`-Pfad mischte in solchen Fällen `sum` und `state` aus aufeinanderfolgenden Slots, was extrem große oder kleine Stunden-Differenzen erzeugen konnte.

Wer in den letzten Tagen Counter-Spikes im Tagesprofil gesehen hatte, repariert sie wie in v3.25.11 beschrieben über den Daten-Checker und „Tag neu aggregieren". Neu auftretende Spikes durch dieses Pattern werden ab v3.25.13 nicht mehr produziert.

→ [Daten-Checker → Energieprofil-Plausibilität](HANDBUCH_DATEN_CHECKER.md)

### Wärmepumpe mit getrennter Strommessung: konsistente JAZ in allen Cockpits *(v3.25.13)*

> ⚠ **User-sichtbare Wert-Korrektur** — Wer im WP-Setup `getrennte_strommessung` aktiviert hat (Strom Heizen + Strom Warmwasser separat statt Sammel-Sensor), sieht in v3.25.13 in allen WP-Cockpits + Monatsbericht + ROI + HA-Export + PDF-Jahresbericht **denselben** JAZ-Wert.

Vorher las jede Stelle die Daten leicht unterschiedlich — manche summierten Heizen+Warmwasser, manche nutzten den alten Sammel-Sensor (sofern noch gemappt). Folge: leicht abweichende JAZ-Werte zwischen Cockpit Komponenten und Monatsbericht.

Ein neuer SoT-Helper `get_wp_strom_kwh` ist jetzt der einzige Lese-Pfad. Bei aktiver getrennter Messung wird der Sammel-Sensor ignoriert. Im Sensor-Zuordnung → Zusammenfassung-Schritt erscheint der alte Sammel-Sensor als „(obsolet)" mit Hinweis, dass er entfernt werden kann.

→ [Cockpit → Wärmepumpe](HANDBUCH_BEDIENUNG.md#41-cockpit)

### Energiefluss-Tile: kleinere Optik-Korrekturen *(v3.25.13)*

Zwei Detail-Fixes im Live-Dashboard:

- **Sunset-/Alps-Hintergründe:** die Effekt-Layer (Sonnenstrahlen, Atmosphären-Bögen, Sterne, Aurora) ragten bisher in die abgerundeten Tile-Ecken hinein. Jetzt sauber an den Border-Radius geclippt.
- **Mittlere Fensterbreite (Notebook-Standard 1024–1280 px):** der Energiefluss zentrierte sich vertikal mit Lücken oberhalb und unterhalb, weil die Heute-Box rechts höher war als das SVG-Aspect-Ratio. Das Side-by-Side-Layout greift jetzt erst ab 1280 px Fensterbreite — im Notebook-Standard stapelt Heute-Box unter dem Energiefluss.

→ [Live-Dashboard → Energiefluss](HANDBUCH_BEDIENUNG.md#3-live-dashboard)

### Sonstige Erträge im Monatsbericht-T-Konto sichtbar + Monatsergebnis korrigiert *(v3.25.11)*

> ⚠ **User-sichtbare Wert-Korrektur** — Wer Sonstige Erträge erfasst hat (z. B. AG-Erstattung beim Dienstwagen, THG-Quote, eingespielte Kostenrückerstattung), sieht nach diesem Update ein höheres Monatsergebnis und neue HABEN-Zeilen im T-Konto.

Bisher wurden im Monatsabschluss-Wizard erfasste Positionen vom Typ „Ertrag" auf der HABEN-Seite des T-Kontos im Monatsbericht nicht angezeigt und im Monatsergebnis ignoriert — bei E-Autos mit Dienstwagen-Flag wurde sogar der ganze Wirtschaftlichkeits-Block übersprungen, sodass weder die AG-Erstattung als Ertrag noch andere zugehörige Positionen sichtbar waren. Auf der SOLL-Seite tauchte zwar eine Aggregat-Zeile „Sonderkosten" (= Σ Ausgaben) auf, das Pendant für Erträge fehlte aber komplett. Im Monatsergebnis am Card-Header wurden die Ausgaben abgezogen, die Erträge aber nicht aufaddiert — wer also 35 € AG-Erstattung erfasst hatte, fand 35 € weniger in seinem Monatsergebnis als erwartet.

Jetzt wertet der Backend-Pfad `sonstige_positionen` typ-unabhängig pro Investition aus, das Frontend zeigt im T-Konto pro Investition eigene HABEN-Zeilen („Tiguan Hybrid — Sonstige Erträge 35,00 €") und SOLL-Zeilen („Tiguan Hybrid — Sonstige Ausgaben"). Das Monatsergebnis im Card-Header rechnet `Gesamt-Nettoertrag − Betriebskosten + Sonstige Netto`. Wer Erträge erfasst hat, sieht den korrekten Wert ab dem nächsten Cockpit-Aufruf — alte Monate werden automatisch neu berechnet, kein Eingriff nötig.

→ [Monatsabschluss → T-Konto](HANDBUCH_BEDIENUNG.md#10-monatsabschluss)

### Pool-Doppelzählung Wallbox/E-Auto im Cockpit entschärft *(v3.25.11)*

> ⚠ **User-sichtbare Wert-Korrektur** — Wer sowohl eine Wallbox als auch ein E-Auto als getrennte Investitionen pflegt, sieht nach diesem Update niedrigere und realistischere Werte für „Ladung gesamt", „Verbrauch (kWh/100km)" und einen plausiblen PV-Anteil im E-Mobilitäts-Block der Monatsberichte.

Die Wallbox als Investitionstyp misst aus Loadpoint-Sicht (was am Stromanschluss raus geht), das E-Auto als Investitionstyp aus Vehicle-Sicht (was im Auto angekommen ist). Beide messen also denselben Stromfluss aus zwei Perspektiven. Bisher wurden die `ladung_kwh`-Werte beider Investitionen aufaddiert — bei einer Anlage mit 1 E-Auto + 1 Wallbox kam dadurch der Wert für „Ladung gesamt" doppelt so hoch wie real, und der `kWh/100km`-Wert ebenfalls. Bei ungleicher Pflege der zwei Eingabe-Quellen konnte der angezeigte PV-Anteil sogar über 100 % laufen — z. B. wenn die Wallbox einen hohen `ladung_pv_kwh`-Wert hat, das E-Auto aber nur einen kleinen `verbrauch_kwh`-Wert.

Als Übergangslösung nimmt EEDC jetzt pro Feld die größere der beiden Quellen als Wahrheit (Loadpoint-Sicht ist üblicherweise inklusiv) und stellt sicher, dass der PV-Anteil mathematisch ≤ 100 % bleibt. Eine saubere Per-Fahrzeug-Trennung folgt mit der Phase 2 des [Wallbox/E-Auto-Datenarchitektur-Konzepts](https://github.com/supernova1963/eedc-homeassistant/blob/main/docs/KONZEPT-WALLBOX-EAUTO.md) — bis dahin bleibt die Cockpit-Gesamtübersicht und der HA-Statistics-/MQTT-Aggregator-Pfad bewusst auf der alten Pool-Logik (sichtbar als Drift-Möglichkeit zwischen Cockpit-Übersicht und Monatsbericht).

Bei Anlagen mit Dienstwagen + Privatauto an gemeinsamer Wallbox bleibt eine Restungenauigkeit: die `kWh/100km`-Berechnung dividiert die Wallbox-Lieferung (inkl. Dienstwagen-Strom) durch die Privat-km — der Wert ist nach diesem Update plausibler, aber noch nicht perfekt. Phase 2 löst das mit Vehicle-Sensoren pro Fahrzeug.

→ [Monatsbericht → E-Mobilität](HANDBUCH_BEDIENUNG.md#10-monatsabschluss)

### Selbsthilfe gegen Counter-Spikes im Tagesprofil *(v3.25.11)*

> ℹ️ **Folge des Off-by-one-Fixes aus v3.25.10** — Der dort behobene Bug hat in seltenen Fällen unphysikalisch hohe Stundenwerte hinterlassen (z. B. ein PV-Spike von 2.384 kWh in einer Stunde statt der realistischen 5 kWh). Bestehende Snapshot-Werte werden vom Service-Bugfix selbst nicht repariert.

Drei aufeinander abgestimmte Selbsthilfe-Wege:

- **„Verlauf nachrechnen" mit Überschreiben** in der Datenverwaltung zieht jetzt vor dem Aggregat zusätzlich die SensorSnapshots des Bereichs frisch aus HA-Statistics — repariert verzerrte Stundenwerte in einem Schritt mit dem Tagesprofil-Aggregat. Bei deaktiviertem Überschreiben (Initial-Backfill) bleibt das Verhalten unverändert.
- **„Tag neu aggregieren"** (das grüne Reload-Symbol in der Tagesliste des Energieprofils) ruft vor dem Aggregat ebenfalls einen Resnap auf — ein Klick auf das Symbol heilt den ausgewählten Tag jetzt vollständig (Snapshots + Aggregate + Heatmap).
- **Daten-Checker erkennt Counter-Spikes selbst:** Neue Kategorie „Energieprofil-Plausibilität" prüft die letzten 30 Tage und meldet Stunden mit `pv_kw` oder `einspeisung_kw` über 1,5× der Anlagen-Spitzenleistung — eindeutig unphysikalisch. Die Detail-Meldung verlinkt direkt auf den Reparatur-Workflow.

Alte Tage älter als 14 Tage können nur in Hourly-Granularität repariert werden, weil HA selbst die 5-Min-Statistik nur ~10–14 Tage zurück bereithält.

→ [Daten-Checker → Energieprofil-Plausibilität](HANDBUCH_DATEN_CHECKER.md) | [Energieprofil → Tag neu aggregieren](HANDBUCH_BEDIENUNG.md#7-auswertung)

### Daten-Checker-Falsch-Warnung „Komponenten ohne kWh-Zähler-Abdeckung" für E-Autos *(v3.25.11)*

Wenn du einen Sensor für die Gesamt-Ladung deines E-Autos im Sensor-Mapping hinterlegt hattest, blieb trotzdem die Warnung „Komponenten ohne vollständige kWh-Zähler-Abdeckung" mit Hinweis `ladung_kwh` stehen. Hintergrund: Das E-Auto-Schema bietet im Wizard das Feld unter dem Schlüssel `verbrauch_kwh` an, der Daten-Checker prüfte aber hartcodiert auf `ladung_kwh` — ein Schlüssel, den du gar nicht zur Auswahl hattest. Andere Stellen im Code akzeptieren beide Schreibweisen.

Der Checker erkennt jetzt beide Schlüssel als korrekt gemappt. Wer einen Sensor hinterlegt hat, sieht den Befund nicht mehr.

→ [Daten-Checker → Energieprofil-Zähler-Abdeckung](HANDBUCH_DATEN_CHECKER.md)

### Off-by-one-Stunde-Bug in Counter-Snapshots behoben *(v3.25.10)*

> ⚠ **Stiller Bug seit v3.19** — Der Bug betrifft die Stundenwerte im Energieprofil (z. B. Tagesverlauf, Heatmap, 24h-Tabellen). Tagessummen und Monatswerte waren NICHT betroffen, weil sich die Verschiebung über 24 h ausmittelt.

Ein Lookup-Helfer in EEDC's HA-Statistics-Service las den Zählerstand pro Stunde aus der falschen Zeile in HA's Statistik-Tabelle. HA's Konvention ist „last value of the period": die Zeile bei Stunde 11 enthält den Zählerstand AM ENDE der Stunde, also um 12:00 Uhr — wir lasen aber denselben Wert für Stunde 12. Konsequenz: alle Stunden-Werte im Tagesverlauf seit v3.19 (Snapshot-Rework Oktober 2025) waren systematisch um eine Stunde nach hinten verschoben. Bei einer Anlage mit z. B. 9 kWh PV-Erzeugung in der Stunde 11–12 hat EEDC diese 9 kWh stattdessen unter „Stunde 12" verbucht — die Tagessumme war richtig, aber die Stundenposition falsch.

Verursacht wurde der Bug durch eine Fehlinterpretation von HA's API-Konvention; maskiert wurde er einerseits dadurch, dass Tagessummen unbeeinflusst sind, andererseits durch HA-Latenz beim hourly-Snapshot-Job (der zufällig oft den korrekten Vorgänger-Slot las, weil die aktuelle Stunde noch nicht finalisiert war). Mit der Phase-1-Erprobung der 5-Min-Snapshots auf Winterborn 2026-05-01 wurde die Diskrepanz erstmals systematisch sichtbar: HA Energy Dashboard zeigte 8,9 kWh für Stunde 11–12, EEDC zeigte 10,1 kWh.

**Was du tun kannst:** Nichts — der Fix wirkt automatisch ab dem nächsten Snapshot. Wer die Vergangenheit korrigieren will, kann den neuen Resnap-Endpoint `POST /api/diagnostics/resnap-snapshots?days=7` aufrufen (regeneriert die letzten 7 Tage). Für Tage älter als 14 Tage steht nur die Hourly-Korrektur zur Verfügung; die 5-Min-Granularität limitiert HA selbst auf ~10–14 Tage. Der reguläre `Vollbackfill aus HA Statistics` (Datenverwaltung) bleibt unverändert nutzbar — dieser nutzt eine andere Quelle (mean-Werte) und war vom Bug nicht betroffen.

→ [Energieprofil-Auswertung](HANDBUCH_BEDIENUNG.md#7-auswertung)

### Drift-Audit-Initiative abgeschlossen *(als Teil von v3.25.10 ausgeliefert)*

> ℹ️ **Versionssprung 3.25.8 → 3.25.10 ist beabsichtigt:** Die hier beschriebenen Drift-Audit-Bündel-G-Änderungen waren ursprünglich für v3.25.9 vorgesehen. Während der CHANGELOG schon stand, wurde der Off-by-one-Bug entdeckt — beide Pakete sind unter Tag `v3.25.10` zusammen ausgeliefert worden, statt zwei Releases im Minutenabstand zu schießen. Es gibt also kein Tag `v3.25.9` im Repository.

Letzter Bündel der Aufräum-Aktion, die mit #178 ([Werte-Drift bei der Wärmepumpe](https://github.com/supernova1963/eedc-homeassistant/issues/178)) startete. Insgesamt wurden 16 Drift-Stellen in 6 Domänen identifiziert und in v3.25.7–v3.25.10 abgearbeitet. Dieses Bündel hat **keine User-sichtbare Werte-Wirkung** — es konsolidiert nur intern Daten in der Datenbank auf einheitliche Schlüssel und ersetzt 23 verstreute Doppel-Read-Stellen im Code durch fünf zentrale Helper. Die DB-Migration läuft beim Add-on-Start einmalig automatisch durch.

Hintergrund: bei mehreren früheren Schema-Wechseln blieben Code-Stellen mit Doppel-Reads der Form `data.get("alt", 0) or data.get("neu", 0)` als Sicherheitsnetz zurück. Gleichzeitig waren in der DB beide Schlüssel-Versionen parallel vorhanden. Beides wurde jetzt vereinheitlicht — bei künftigen Schema-Änderungen muss nur noch eine zentrale Stelle gepflegt werden.

### Speicher- und V2H-Ersparnis im Aussichten-Tab konsistent zur Detail-Ansicht *(v3.25.8)*

> ⚠ **User-sichtbarer Wert-Sprung** — Wer den Aussichten-Tab als Referenz für Speicher-Ersparnis nutzt, wird nach diesem Update einen ~25 % niedrigeren Wert sehen. Das ist eine Korrektur, kein Verlust.

Bisher rechneten Aussichten und Investitionen-Detail die Speicher-Ersparnis mit unterschiedlichen Formeln: Aussichten nahm den vollen Bezugspreis (`Entladung × 30 ct`), die Detail-Ansicht den Spread zwischen Bezug und Einspeisevergütung (`Entladung × (30 − 8) ct`). Bei einer Anlage mit 2.000 kWh Speicher-Durchsatz/Jahr ergab das 600 € (Aussichten) gegen 440 € (Detail) — für dieselbe Anlage.

Korrekt ist das Spread-Modell, weil der gespeicherte Strom ohne Speicher als Einspeisung Vergütung erwirtschaftet hätte — nur die Differenz ist echter Netto-Gewinn. Aussichten ist jetzt darauf umgestellt; alle Tabs zeigen denselben Wert. Gleiche Logik gilt für V2H (E-Auto-Rückspeisung ins Haus).

Im Speicher-Dashboard war außerdem das Formel-Label ungenau („Ersparnis = Entladung × Strompreis") — passt jetzt zur tatsächlichen Berechnung.

→ [Aussichten-Tab](HANDBUCH_BEDIENUNG.md#5-aussichten--prognose) | [Speicher-Dashboard](HANDBUCH_BEDIENUNG.md#33-speicher-dashboard)

### Cockpit-E-Auto-Ersparnis liest jetzt deine gepflegten Werte *(v3.25.8)*

Cockpit → Übersicht und Cockpit → Monatsberichte hatten bisher 7 L/100 km Vergleichsverbrauch und 1,80 €/L Benzinpreis hartcodiert — selbst wenn du im E-Auto-Formular andere Werte hinterlegt hattest, wurden die ignoriert. Aussichten und PDF haben deine Eingaben schon respektiert; Cockpit zog deshalb 7–9 % höhere Ersparnis-Werte. Jetzt rufen alle Stellen denselben Helper auf, kanonische Defaults sind 7,5 L/100 km und 1,65 €/L (entspricht den Voreinstellungen im Formular).

→ [Investitionen pflegen → E-Auto](HANDBUCH_BEDIENUNG.md#11-investitionen-pflegen)

### Drei stille Datenfehler bei Anlagen mit historischem Backfill behoben *(v3.25.8)*

Wenn du via CSV-Import oder HA-LTS-Backfill Daten geladen hast, die zeitlich vor dem Anschaffungsdatum einer Komponente liegen (z. B. WP-Daten ab Januar, obwohl die WP erst im April installiert wurde), wurden diese Vor-Daten in drei Endpoints fälschlich mitberechnet:

- **Cockpit → Prognose** (Vergleich Soll-PV/Ist-PV) — falls PV-Module mid-year angeschafft wurden
- **HA-Sensor-Export** (z. B. `eedc_wp_ersparnis_euro`) — falls WP/Speicher mid-year angeschafft wurden
- **Community-Server-Submission** — gleicher Effekt; bei betroffenen Anlagen wurden Vor-Anschaffungs-Werte als Anlage-Beitrag hochgeladen

Alle drei greifen jetzt auf den gleichen Anschaffungsdatum-Filter zu, der seit v3.23.1 in Cockpit-Übersicht/Auswertungen aktiv ist. Wenn du betroffen warst, normalisiert sich dein Wert beim nächsten Cockpit-Aufruf bzw. nächster Community-Submission automatisch.

### Hintergrund: Drift-Audit-Initiative

Der WP-Ersparnis-Bug aus #178 (v3.25.7) hat eine systematische Inventur aller Investitions-Berechnungen ausgelöst. 16 Drifts in 6 Domänen identifiziert. v3.25.8 schließt davon 5 Bündel; eine weitere Folge-Version macht den Rest (vereinheitlichte Reader für die JSON-Felder im `verbrauch_daten`-Speicher mit Datenbank-Migration). Die komplette Inventur liegt im Repo unter `docs/drafts/INVENTUR-DRIFT-AUDIT.md`.

### Wärmepumpe: Ersparnis-Anzeige in allen vier Tabs konsistent *(v3.25.7)*

Vor v3.25.7 zeigten Cockpit → Monatsberichte, Cockpit → Übersicht, Cockpit → Wärmepumpe und Auswertungen → Komponenten teils unterschiedliche WP-Ersparnis-Werte für dieselbe Anlage (z. B. 7 € / 61 € / 77 € / 61 €). Ursache: vier Code-Pfade mit unterschiedlichen hartcodierten Defaults und teils falschen Param-Keys, sodass gepflegte Werte für „alter Heizungspreis" oder „alter Energieträger" stillschweigend ignoriert wurden. Jetzt rufen alle vier denselben Helper auf — der Wert ist konsistent. Issue [#178](https://github.com/supernova1963/eedc-homeassistant/issues/178), detLAN-Bericht.

→ [Cockpit-Wärmepumpe](HANDBUCH_BEDIENUNG.md#36-wärmepumpe-dashboard)

### Wärmepumpe: Hersteller-Lebensdauer-Counter im Cockpit *(v3.25.3)*

Wärmepumpen-Hersteller wie Nibe oder Viessmann liefern einen Counter „Kompressor-Starts gesamt" — die echte Lebensdauer-Zahl ab Werks-Inbetriebnahme, oft 4-stellig im Auslieferungszustand. EEDC zählt seit v3.24.0 selbst über Snapshot-Differenzen — das hat den 4-stelligen Sockel aber nicht abgebildet, sodass das WP-Cockpit unter „Σ Kompressor-Starts" eine viel zu kleine Zahl zeigte (z. B. 87 statt 5.234). Beim nächsten Speichern im Sensor-Mapping-Wizard eicht EEDC die Hersteller-Baseline jetzt einmalig (`baseline = sensor.gesamt − Σ EEDC-Tagesdifferenzen seit Anschaffung`) und addiert sie beim Anzeigen wieder dazu. Der Tooltip auf der Kachel zeigt die Zerlegung Hersteller-Baseline + EEDC-seit-Aktivierung + höchste Tagessumme. Selbstkorrigierend bei jedem Wizard-Rerun. Issue [#173](https://github.com/supernova1963/eedc-homeassistant/issues/173), detLAN-Vorschlag.

→ [Bedienung §3.6 Wärmepumpe](HANDBUCH_BEDIENUNG.md#36-wärmepumpe-dashboard)

### Auf-/Zuklappen + Sortierung jetzt in allen Cockpit-Dashboards *(v3.25.3)*

Die seit v3.21.0 im Auswertungs-Tab vorhandene Mechanik zum Einklappen einzelner Sektionen und zum Drag-and-Drop-Umsortieren ist jetzt auch in den Dashboards Cockpit → PV-Anlage, Cockpit → Wärmepumpe und Monatsabschluss aktiv. Reihenfolge wird pro Anlage gespeichert (ein User mit zwei Anlagen kann sie unterschiedlich anordnen). Verhalten ist 1:1 identisch zur Auswertungs-Implementierung, nur jetzt überall verfügbar. Issue [#175](https://github.com/supernova1963/eedc-homeassistant/issues/175), detLAN-Vorschlag.

→ [Bedienung §3 Cockpit](HANDBUCH_BEDIENUNG.md#3-cockpit-dashboards)

### WP-Kompressor-Starts: Slot 23:00 + Tageswerte rückwirkend reparieren *(v3.25.2)*

Bei Wärmepumpen mit Kompressor-Starts-Sensor ohne `state_class` (typisch lokale Nibe/Viessmann-Integration) fehlte regelmäßig der Stunden-Slot 23:00 im Tagesdetail, und derselbe Tag tauchte im Cockpit-WP / Monatsbericht nicht in der Aggregat-Sicht auf. Beide Effekte hatten dieselbe Wurzel: ein verlorener Modul-Import in der Live-Vorab-Erfassung kurz vor Mitternacht ließ den 00:00-Snapshot still ausfallen — und der wird sowohl für die Stunde 23:00 als auch für den Tages-Counter gebraucht. Behoben. Künftige Tage werden sauber erfasst; für die offenen Vortage hilft *Auswertung → Energieprofil → Datenverwaltung → Verlauf nachrechnen* (oder Per-Tag-Reaggregation), weil HA die fehlenden LTS-Einträge inzwischen nachgepflegt hat. Issue [#136](https://github.com/supernova1963/eedc-homeassistant/issues/136), detLAN-Beobachtung.

### PV-Cockpit: Module + Speicher nebeneinander statt untereinander *(v3.25.2)*

Innerhalb der Wechselrichter-Karte unter „Cockpit → PV-Anlage → PV-Komponenten" werden Module und Speicher jetzt nebeneinander in zwei Spalten dargestellt (Desktop) — auf Smartphone-Breite weiterhin gestapelt. Wirkt für typische Anlagen-Konfigurationen ausgewogener als das vertikale Layout aus v3.24.6. Issue [#172](https://github.com/supernova1963/eedc-homeassistant/issues/172), detLAN-Mockup.

→ [Bedienung §3.4 PV-Anlage](HANDBUCH_BEDIENUNG.md#34-pv-anlage-dashboard)

### Hilfe-Seite: Inhaltsverzeichnis-Links und Browser-Zurück funktionieren wieder *(v3.25.1)*

In der seit v3.24.2 verfügbaren In-App-Hilfe sprangen Klicks auf die Inhaltsverzeichnis-Einträge (z. B. „2. Installation" am Anfang von *Teil I: Installation & Einrichtung*) aus der Hilfe-Seite heraus statt zur Sektion zu scrollen — die Hilfe-Seite verschwand komplett. Das war ein technischer Konflikt zwischen den Anker-Links im TOC und der App-internen Navigation. Behoben: Inhaltsverzeichnisse, Querverweise zwischen Hilfe-Dokumenten und der Browser-Zurück-Knopf funktionieren jetzt erwartungsgemäß. Rainer-PN.

→ [Bedienung §9 Hilfe](HANDBUCH_BEDIENUNG.md#9-hilfe-in-der-app)

### Mehrere ROI- und Aussichten-Werte rechnen jetzt mit deinen tatsächlichen Eingaben *(v3.25.0)*

Hinter den Kulissen war das `parameter`-JSON, in dem Investitionen ihre typ-spezifischen Detail-Daten halten (z. B. Speicher-Kapazität, V2H-Aktivierung, E-Auto-Fahrleistung), zwischen Form/Wizard und Backend-Lese-Code an mehreren Stellen auseinandergedriftet. Eine Vollinventur hat 7 Bugs zutage gefördert, in denen das Backend Schlüssel las, die Form/Wizard nie geschrieben haben — d. h. deine Eingaben wurden stillschweigend durch Default-Werte ersetzt. Konkret:

- **V2H** (E-Auto Vehicle-to-Home) war im Aussichten-Tab, in der Live-Komponenten-Erkennung und im E-Auto-ROI tot — der Haken im Formular hatte dort keine Wirkung.
- **Arbitrage** (Speicher) war im ROI tot — Aktivierung im Formular wurde ignoriert. Im Speicher-Dashboard funktionierte sie korrekt.
- **Wallbox-Leistung** im Wallbox-Dashboard und im Community-Datensatz zeigte immer 11 kW, unabhängig vom eingegebenen Wert.
- **E-Auto Jahresfahrleistung / PV-Ladeanteil / Vergleichsverbrauch** wurden im ROI nicht berücksichtigt — der ROI rechnete mit 15 000 km, 60 % bzw. 7,0 L/100 km, egal was im Formular stand.
- **WP „Alter Heizungspreis"** hatte je nach Tab unterschiedliche Default-Werte (10 vs. 12 ct/kWh) → unterschiedliche Ersparnis-Anzeigen für denselben Zustand.
- **WP „Getrennte Strommessung"**: ein subtiler String-vs-Boolean-Fehler ließ den Schalter nicht ausgehen, wenn man ihn von „aktiv" zurücksetzte.

Eine einmalige DB-Migration räumt die Drift in deiner bestehenden Datenbank automatisch auf. **Sichtbare Auswirkung für dich:** Wenn du eine der oben genannten Optionen aktiviert oder eingegeben hattest, siehst du ab v3.25.0 plötzlich neue Werte im ROI, im Aussichten-Tab und im Wallbox-Dashboard. Die alten Werte waren Default-Anzeigen, nicht deine Werte.

→ [Bedienung §3 Cockpit](HANDBUCH_BEDIENUNG.md#3-cockpit-dashboards) · [Bedienung §7 Aussichten](HANDBUCH_BEDIENUNG.md#7-aussichten-prognosen)

---

## v3.24.x — In-App-Hilfe & WP-Kompressor-Starts (April 2026)

### PV-Cockpit: Speicher-Kapazität wieder sichtbar + getrennte Sub-Boxen *(v3.24.6)*

Im „Cockpit → PV-Anlage → PV-Komponenten"-Block las das Frontend die Speicher-Kapazität unter dem falschen Schlüssel — gepflegte Daten waren da, blieben aber unsichtbar. Behoben. Zusätzlich werden Module und Speicher jetzt in eigenen, beschrifteten Sub-Sektionen innerhalb der Wechselrichter-Karte dargestellt (statt in einem gemischten Grid), und Speicher ohne Wechselrichter-Zuordnung tauchen in einem separaten Block am Ende auf statt stillschweigend zu verschwinden. Issue [#172](https://github.com/supernova1963/eedc-homeassistant/issues/172).

→ [Bedienung §3.4 PV-Anlage](HANDBUCH_BEDIENUNG.md#34-pv-anlage-dashboard)

### Diese Seite — „Was ist neu" als Pull-Variante *(v3.24.5)*

Die Seite, die du gerade liest. Statt eines Banner-Pop-ups nach Update gibt es einen festen Eintrag in der Hilfe-Sidebar: wer wissen will, was neu ist, schaut hier rein. HA-Add-on-Nutzer sehen den Changelog ohnehin schon im Add-on-Store, GitHub-Releases haben einen eigenen — kein Bedarf für eine dritte Stimme. Discussion [#130](https://github.com/supernova1963/eedc-homeassistant/discussions/130) Folge-Wunsch von Safi105.

### In-App-Hilfe-Seite *(v3.24.2)*

Das Benutzerhandbuch ist jetzt direkt in EEDC verfügbar — ohne Browser-Wechsel und ohne Ingress-Login-Probleme in der HA-Companion-App. Acht kuratierte Dokumente in drei Kategorien (*Einstieg* / *Handbuch* / *Referenz*), Sidebar am Desktop, Dropdown auf dem Smartphone. URL-Parameter `?doc=<slug>` macht Direktlinks teilbar (z. B. `?doc=bedienung#7-aussichten-prognosen`). Discussion [#130](https://github.com/supernova1963/eedc-homeassistant/discussions/130).

→ [Bedienung §9 Hilfe](HANDBUCH_BEDIENUNG.md#9-hilfe-in-der-app)

### Wärmepumpe: Kompressor-Starts als Verschleiß- und Auslegungs-Indikator *(v3.24.0 Counter / v3.24.4 Tiles)*

Optionaler Total-Increasing-Sensor im Sensor-Mapping erfasst die Kompressor-Starts der Wärmepumpe (z. B. aus der lokalen „Nibe Heat Pump"-Integration). Cockpit → Monatsberichte zeigt die höchste Tagessumme des Monats als Verschleiß-Indikator („wie heftig hat die WP an ihrem schlechtesten Tag getaktet"), Cockpit → Wärmepumpe zeigt die Σ Starts seit Anschaffung als Auslegungs-Indikator. Stunden-/Tages-Detail in der Energieprofil-Tabelle. Issue [#136](https://github.com/supernova1963/eedc-homeassistant/issues/136), [#169](https://github.com/supernova1963/eedc-homeassistant/issues/169).

→ [Sensor-Referenz §4](SENSOR-REFERENZ.md) · [Bedienung §3.6 Wärmepumpe](HANDBUCH_BEDIENUNG.md#36-wärmepumpe-dashboard)

### Sensor-Mapping: Sensoren ohne HA-Statistics sichtbar machen *(v3.24.1)*

Sensoren ohne `state_class` (z. B. Nibe-Roh-Counter) lassen sich jetzt über einen Fallback-Link „Alle Sensoren ohne Filter anzeigen" auswählen. Die Auswahl wird mit einem amber-farbenen **„ohne Statistik"**-Badge markiert. Begleitend prüft der Daten-Checker eine neue Kategorie *Sensor-Mapping HA-Statistics* — kWh-Felder ohne LTS sind kritisch (Korrektur-Werkzeuge greifen nicht), Counter-Felder unproblematisch. Damit ist der Sensor-Mapping-Wizard auch für nicht-Standard-Integrationen nutzbar.

→ [Einstellungen §3 Sensor-Mapping](HANDBUCH_EINSTELLUNGEN.md#3-sensor-mapping) · [Einstellungen §8 Daten-Checker](HANDBUCH_EINSTELLUNGEN.md#8-daten-checker)

### state_class-Hinweise auf den richtigen Hebel umgestellt *(v3.24.3)*

Im Wizard-Banner und Daten-Checker-Hinweisen stand bisher „vergangene Tage bleiben leer" — das passiert aber auch mit `customize.yaml`-Korrektur, weil HA Long-Term-Statistics erst ab Aktivierung persistiert. Der relevante Hebel im Betrieb ist: ohne `state_class` greifen die **Korrektur-Werkzeuge in der Datenverwaltung** nicht — Vollbackfill, „Verlauf nachrechnen" und Per-Tag-Reaggregation lesen alle aus HA's LTS. Texte und Daten-Checker-Severity entsprechend angepasst.

---

## v3.23.x — Cockpit-Harmonisierung & Diagnose-Werkzeuge (April 2026)

### Cockpit: Reihenfolge umsortiert + WP-KPIs harmonisiert *(v3.23.4)*

Cockpit-Sub-Tabs jetzt in der Reihenfolge **Übersicht → Monatsberichte → PV-Anlage → Balkonkraftwerk → Speicher → Wärmepumpe → Wallbox → E-Auto → Sonstiges** (Erzeuger oben, Speicher in der Mitte, Verbraucher unten). Wärmepumpen-KPIs nutzen über alle vier Render-Stellen (Cockpit-Übersicht, WP-Dashboard, Auswertung, Monatsabschluss) dieselbe Reihenfolge **JAZ → Wärme → Strom → Ersparnis** mit identischen Icons (Thermometer / Flame / Zap / TrendingUp). Anlagenname als Tab-Titel (kein redundantes „Wärmepumpe"-Echo).

→ [Bedienung §3 Cockpit](HANDBUCH_BEDIENUNG.md#3-cockpit-dashboards)

### Aggregate ignorieren Daten vor dem Anschaffungsdatum *(v3.23.0–v3.23.1)*

Cockpit- und Auswertungs-Aggregate für Wärmepumpe / Speicher / Wallbox / E-Auto / Balkonkraftwerk berücksichtigen nur noch Monate **ab dem Anschaffungsdatum** der jeweiligen Komponente. Migrationen (z. B. Wechsel auf Shelly-erfasste WP-Strommessung) verfälschen damit nicht mehr historische JAZ und Ersparnis. Issue [#153](https://github.com/supernova1963/eedc-homeassistant/issues/153).

### Asymmetrie-Diagnostik im Genauigkeits-Tracking *(v3.23.3)*

Toggle **„Kompakt / Diagnostisch"** in der Genauigkeits-Tracking-Card. Der Diagnostisch-Modus splittet die Streuung pro Quelle (OpenMeteo / EEDC / Solcast) in „darüber"-und „darunter"-Boxen — Ø-Über-/Unterschätzung in Prozent plus Anzahl Tage. Damit sichtbar, ob ein systematischer Hebel vorliegt („bei dichten Wolken zu hoch, bei klarem Himmel zu niedrig") oder reine Streuung. Issue [#151](https://github.com/supernova1963/eedc-homeassistant/issues/151).

→ [Bedienung §7.2 Prognosen](HANDBUCH_BEDIENUNG.md#72-prognosen)

### Reparatur-Popover bei IST-Datenlücken im Prognosen-Tab *(v3.23.0)*

Klick auf das ⚠ neben einem Tageswert öffnet jetzt einen Popover statt eines Hover-Tooltips. Inhalt: Liste der fehlenden Stunden, kurze Erklärung, Button **„Tag neu berechnen"** (löst eine Per-Tag-Reaggregation aus) und Fallback-Link zum Sensor-Mapping. Direkter Reparatur-Pfad statt Diagnose-Suche.

### Live-Dashboard: Bilanz-Sortierung & Eigenverbrauchs-Cap *(v3.23.5)*

Tageswerte-Kacheln im Live-Dashboard in Energie-Logik-Reihenfolge: **PV → Batterie → Eigenverbrauch (Quellen-Σ) → Netzbezug → Hausverbrauch → Einspeisung**. Eigenverbrauchs-Quote ist jetzt auf 100 % gecappt (vorher konnten ev/pv > 100 % rechnen, wenn Batterie-Entladung aus Vortagen einfloss). Issue [#157](https://github.com/supernova1963/eedc-homeassistant/issues/157).

→ [Bedienung §2 Live Dashboard](HANDBUCH_BEDIENUNG.md#2-live-dashboard)

---

## v3.22.0 — Genauigkeits-Tracking & Mobile-Layout (April 2026)

### MAE und Bias getrennt ausweisen

Genauigkeits-Tracking zeigt jetzt zwei Kennzahlen pro Quelle: **MAE** (mittlere absolute Abweichung — Streuung) und **MBE** (mittlerer signed Error — systematischer Bias). Bias neutral gefärbt (das Vorzeichen ist Information, nicht Wertung). EEDC wird zusätzlich zu OpenMeteo und Solcast bewertet. Spaltenstruktur stabilisiert: kein Spaltenflattern mehr nach Tag 7, gedämpfter Header bei fehlendem Lernfaktor.

### Mobile-Layout-Bündel

Sieben Mobile-Layout-Korrekturen aus detLAN-Bugreport: Cockpit-/Energieprofil-SubTabs scrollen aktiven Tab in den sichtbaren Bereich, Monatsberichte-T-Konto auf Mobile als 2-Spalten-Layout (Label | Wert+VJ+Δ gestapelt), Sticky-Bars über Tabellen-thead, Energieprofil-Subtabs mit `flex-wrap` (umbricht statt rechts rauszulaufen), Aussichten-Langfrist-Steuerung vertikal gestapelt, Tabellen mit vielen Spalten zeigen Querformat-Hinweis. Issue [#149](https://github.com/supernova1963/eedc-homeassistant/issues/149).

### VM/NM-Split an astronomischer Tagesmitte

Tageshälften (Vormittag/Nachmittag) splitten jetzt am Solar Noon (via Equation of Time, je nach Standort und Datum bis ~30 min von 12:00 abweichend) statt hart bei 12:00 Uhr Clockzeit. Slots, die Solar Noon enthalten, werden proportional verteilt.

### Banner: Restzeit bis Lernfaktor-Schwelle

Der Hinweis „EEDC-Prognose nicht verfügbar" zeigt jetzt zusätzlich, wie viele Tage bereits gesammelt sind und wie viele bis zur 7-Tage-Schwelle fehlen.

---

## v3.21.0 — Energieprofil-Komfort & WP-Alternativvergleich (April 2026)

### Tage-Tabelle im Auswertung-Monat-Tab + aufklappbare Sektionen

Auswertung → Energieprofil → Monat hat jetzt eine prominente **Tage-Tabelle** als eigene Sektion: pro Tag eine Zeile mit Heatmap-Zellfarben, Negativpreis-Tage mit amber-Streifen + §51-Badge, sticky Σ-Monat-Footer mit Spalten-Aggregat. Alle Sektionen unter `<CollapsibleSection>` mit localStorage-Persistenz pro Anker. Issue [#148](https://github.com/supernova1963/eedc-homeassistant/issues/148).

→ [Bedienung §5.8 Energieprofil](HANDBUCH_BEDIENUNG.md#58-energieprofil-tab-beta)

### Pro-Tag-Reaggregation per Knopf

Selbsthilfe-Mechanismus für einzelne Tage mit offensichtlich falschen Werten: Refresh-Icon-Button am Ende jeder Tageszeile in der Energieprofil-Datenverwaltung. Klick → Confirmation → API-Aufruf → Reload. Statt manueller DB-Edit oder Vollbackfill. Wirkt auch in Auswertung → Energieprofile (Beta) → Monat (geteilte Komponente). Issue [#146](https://github.com/supernova1963/eedc-homeassistant/issues/146).

### Snapshot-Job-Toleranz & :55-Live-Preview

Stundenwerte zeigen nicht mehr gelegentlich „Stunde 0.00 + Folge-Spike" durch HA-Statistics-Latenz. Toleranz von 60 → 10 min reduziert (Stunden, die zur Zeit des :05-Jobs noch nicht in HA sind, werden vom späteren Self-Healing-Lauf nachgeholt statt mit dem Vorstunden-Wert beschrieben). Neuer :55-Job schreibt zusätzlich einen Live-Vorschau-Eintrag, damit die laufende Stunde zum Stundenende sofort sichtbar ist. Issue [#146](https://github.com/supernova1963/eedc-homeassistant/issues/146).

### WP-Alternativvergleich: Zusatzkosten + Monats-Gaspreis

Zwei Lücken im Gas-vs-WP-Vergleich geschlossen:

- Neuer Investitions-Parameter **`alternativ_zusatzkosten_jahr`** (€/Jahr) für Schornsteinfeger / Wartung / Gaszähler-Grundpreis — wird in allen Berechnungs-Stellen (Aussichten, HA-Export, PDF-Jahresbericht, Investitions-Vorschau) zu den Alt-Heizungs-Kosten addiert, in historischen Aggregaten anteilig pro erfasstem Monat.
- Neue optionale **`Monatsdaten.gaspreis_cent_kwh`**-Spalte (analog zu `kraftstoffpreis_euro` für Benzin): pro Monat gepflegt wird sie in der historischen Aggregation Monat für Monat verwendet, Fallback bleibt der Investitions-Parameter `alter_preis_cent_kwh`. Damit ändert ein Tarifwechsel nicht mehr rückwirkend die ganze Historie.

Issue [#141](https://github.com/supernova1963/eedc-homeassistant/issues/141).

→ [Berechnungen §3.5 WP-Einsparung](BERECHNUNGEN.md#35-wärmepumpe-einsparung)

### ROI-Sicht-Hinweise in allen Tooltips

Alle ROI-/Amortisations-Anzeigen (Cockpit, Investitionen-Tab, ROI-Dashboard, Aussichten-Finanzen) zeigen im Tooltip an, **welche Sicht** die Zahl darstellt — z. B. „Pro Investition · Jahres-ROI · Mehrkosten-Ansatz · Prognose" vs. „Gesamt-Anlage · IST-Werte · kumuliert". Adressiert die im Forum berichtete Verwirrung über mehrere parallele ROI-Werte.

---

## v3.20.x — Backward-Slot-Konvention & PR mit GTI (April 2026)

### Backward-Slot-Konvention für Stunden-Energie

OpenMeteo, Solcast und IST nutzen jetzt durchgängig **Slot N = Energie [N-1, N)** — Industriestandard (HA Energy Dashboard, SolarEdge, SMA, Fronius, Tibber). Vorher zeigten die drei Quellen unter demselben Slot-Label physikalisch unterschiedliche Zeitintervalle. Strompreis-Stunden bleiben Forward (`[N, N+1)`, industrieüblich für aWATTar/Tibber/EPEX). Issue [#144](https://github.com/supernova1963/eedc-homeassistant/issues/144).

> **Nach Update einmalig:** „Verlauf nachberechnen + überschreiben" auslösen, damit historische Stundenwerte umverteilt werden. Tagessummen bleiben konventionsunabhängig korrekt.

→ [Berechnungen §6b Energieprofil](BERECHNUNGEN.md#6b-energieprofil-berechnungen-tages-aggregation)

### Performance Ratio nutzt GTI statt GHI

Die PR-Formel berücksichtigt jetzt die **Global Tilted Irradiance** (auf die Modulfläche projiziert, kWp-gewichtet bei Multi-String-Anlagen) statt der horizontalen Globalstrahlung. Bei steilen Modulen und tiefstehender Wintersonne kann GTI 2–3× höher sein als GHI — vorher liefen PR-Werte im Winter auf physikalisch unmögliche 1.2–2.8. Issue [#139](https://github.com/supernova1963/eedc-homeassistant/issues/139).

### Snapshot-Lücken-Interpolation

Fehlt ein stündlicher Sensor-Snapshot, wird die Lücke jetzt **linear zwischen den Nachbar-Stunden interpoliert** statt das Gesamt-Delta in eine Stunde aufzustauen. Damit kein „Stunde-0 + Folge-Spike"-Muster mehr in den Stundenwerten. Issue [#145](https://github.com/supernova1963/eedc-homeassistant/issues/145).

---

## v3.19.0 — Energieprofil aus Zähler-Snapshots (April 2026)

### kWh-Werte aus kumulativen Zähler-Snapshots statt W-Integration

Die Stunden-kWh in den Tagesprofilen werden jetzt als **Differenz kumulativer Zählerstände** berechnet (Quelle: HA Long-Term-Statistics oder MQTT-Energy-Snapshots) statt aus 10-Min-`leistung_w`-Samples integriert. Drift-Reduktion von ~9 % auf ~0,1 %, validiert auf der Winterborn-Anlage über 538 Tage Backfill. Prognosen-IST, Lernfaktor und Heatmaps stimmen mit dem Live-Dashboard und der Zähler-Realität überein. Issue [#135](https://github.com/supernova1963/eedc-homeassistant/issues/135).

> **Empfohlene Aktion nach Update:** Einstellungen → Energieprofil → „Verlauf nachberechnen" mit aktiver „Überschreiben"-Option auslösen (1–5 Min Laufzeit), damit historische Tagesprofile aus den Zählern statt aus Leistungs-Schätzung stammen.

→ [Einstellungen §10 Energieprofile-Hintergrund](HANDBUCH_EINSTELLUNGEN.md#10-energieprofile--hintergrund)

### Daten-Checker: Neue Kategorie „Energieprofil – Zähler-Abdeckung"

Prüft pro Anlage und Komponente, welche kumulativen kWh-Zähler gemappt sind. Warnt mit konkreter Liste fehlender Zähler und verlinkt zum Sensor-Mapping-Wizard. Damit ist beim Onboarding sofort sichtbar, was für genaue Energieprofile noch fehlt.

### Live-Dashboard: Lite-Modus jetzt wirklich „lite"

Drei Performance-Verbesserungen am Energiefluss-Diagramm für iPad und Mobile-Safari: SMIL-Partikel-Animationen werden im Lite-Modus weggelassen, `filter`-Attribute der Knoten-Karten ebenso, der Hintergrund ist `React.memo`-gewrappt. Effekt-Modus bleibt unverändert. Forum-Bericht dietmar1968.

---

## v3.18.0 — Eigene Energieprofil-Seite (April 2026)

### Datenverwaltung pro Anlage

Neue Seite **Einstellungen → Energieprofil** bündelt die anlage-spezifischen Auswertungen und Datenverwaltungs-Aktionen. Datenbestand-Kacheln (Stundenwerte/Tagessummen/Monatswerte, Abdeckung, Zeitraum), Tages-Tabelle mit Jahr/Monat-Selektor und Spalten-Selektor in Gruppen (Peak-Leistungen, Tages-Summen, Performance, Wetter, §51-Börsenpreise). Aktionen: Vollbackfill aus HA-Statistik, Kraftstoffpreis-Backfill, Energieprofil-Daten löschen — anlage-spezifisch statt global. Tab-Konsolidierung: `Monatsabschluss` aus der Einstellungen-Tab-Leiste entfernt (Dropdown-Eintrag bleibt). Issue [#133](https://github.com/supernova1963/eedc-homeassistant/issues/133).

→ [Einstellungen §1.6 Energieprofil-Seite](HANDBUCH_EINSTELLUNGEN.md#16-energieprofil-seite)

---

## v3.17.0 — Echte monatliche Benzinpreise (April 2026)

### Dynamische Kraftstoffpreise für E-Auto-ROI

Statt statischem `benzinpreis_euro`-Parameter werden jetzt **echte monatliche Kraftstoffpreise aus dem EU Weekly Oil Bulletin** verwendet. Neues Feld `Monatsdaten.kraftstoffpreis_euro` (€/L) mit automatischem Vorschlagswert im Monatsabschluss-Wizard. ROI-Berechnung (Aussichten), HA-Sensor-Export und PDF-Finanzbericht nutzen pro Monat den echten Preis — Fallback auf den statischen Parameter wenn kein Monatswert vorhanden. Backfill-Endpoint befüllt Monatsdaten rückwirkend (Oil Bulletin History seit 2005).

> **Hinweis:** Die E-Auto-Ersparnis kann sich gegenüber früheren Versionen verändern — nach oben oder unten, je nachdem ob der reale Preis über oder unter dem konfigurierten Wert lag.

→ [Einstellungen §1.4 Monatsdaten](HANDBUCH_EINSTELLUNGEN.md#14-monatsdaten)

---

## v3.16.x — Dynamischer Strompreis & Solcast-Prognosen (April 2026)

### Solcast PV Forecast — Neuer Prognosen-Tab *(v3.16.4–v3.16.8)*

Neuer Tab **„Prognosen"** in Aussichten als Evaluierungs-Cockpit für das Zusammenspiel von OpenMeteo, EEDC (kalibriert mit Lernfaktor), Solcast und IST. KPI-Matrix Heute/Morgen/Übermorgen mit VM/NM-Split, Stundenprofil-Chart mit p10/p90-Konfidenzband, 24h- und 7-Tage-Vergleichstabellen, Genauigkeits-Tracking. Solcast wird über einen Toggle im Sensor-Mapping-Wizard aktiviert — entweder API-Zugang (Free/Paid) oder via HA-Integration BJReplay. L1/L2-Cache überlebt Neustarts.

→ [Bedienung §7.2 Prognosen](HANDBUCH_BEDIENUNG.md#72-prognosen)

### Dynamischer Strompreis — Sensor-Mapping + EPEX-Börsenpreis *(v3.16.0)*

Neues optionales Feld **„Strompreis (dynamischer Tarif)"** im Sensor-Mapping unter Basis-Sensoren — Tibber, aWATTar, EPEX oder eigener Template-Sensor zuordnen. EPEX Day-Ahead-Preise (DE/AT) werden zusätzlich automatisch via aWATTar-API geholt — als Overlay im Tagesverlauf, auch ohne eigenen Sensor. MQTT-Topic `eedc/{id}/live/strompreis_ct` für Standalone-Docker-Nutzer.

→ [Einstellungen §3 Sensor-Mapping](HANDBUCH_EINSTELLUNGEN.md#3-sensor-mapping)

### Saisonaler Lernfaktor (MOS-Kaskade) *(v3.16.15)*

Der Lernfaktor nutzt jetzt eine saisonale Kaskade: **Monatsfaktor** (≥15 Tage gleicher Kalendermonat) → **Quartalsfaktor** (≥15 Tage) → **30-Tage-Fenster** (≥7 Tage, bisheriges Verhalten). Bei wachsendem Datenbestand wird die Kalibrierung automatisch präziser. Im Prognosen-Tab wird die aktive Stufe angezeigt.

→ [Berechnungen §4.1c Prognose-Genauigkeit](BERECHNUNGEN.md#41c-prognose-genauigkeit-mae-mbe-asymmetrie)

### Stündliche Strompreis-Mitschrift im Energieprofil

Zwei getrennte Preisfelder pro Stunde: **`strompreis_cent`** (Endpreis aus HA-Sensor) und **`boersenpreis_cent`** (EPEX, immer befüllt). Tagesaggregation mit Negativpreis-Zählung und Einspeisung bei negativem Börsenpreis (§51 EEG). Datengrundlage für künftige Negativpreis-Auswertungen.

### Investitionsformular verschlankt — Stammdaten in Infothek *(v3.16.2)*

Geräte-Stammdaten (`stamm_*`), Ansprechpartner (`ansprechpartner_*`) und Wartungsvertrag (`wartung_*`) sind aus dem Investitionsformular verschwunden — alle diese Daten werden jetzt über die **Infothek** verwaltet (N:M-Verknüpfung Datenblatt ↔ Investition). Beim Bearbeiten einer Investition erscheinen verknüpfte Infothek-Einträge als kompakte Liste mit Direktlink. PDF-Jahresbericht entsprechend bereinigt.

→ [Infothek-Handbuch](HANDBUCH_INFOTHEK.md)

---

## Ältere Versionen

Für Versionen vor v3.16 — siehe [CHANGELOG](https://github.com/supernova1963/eedc-homeassistant/blob/main/CHANGELOG.md) auf GitHub.

Wichtige Meilensteine als Stichworte: Live Dashboard + MQTT-Inbound (v3.0), GTI-Prognose (v3.3), Wettermodell-Kaskade (v3.4), Infothek-Modul Etappe 1 (v3.5), L1/L2-Cache (v3.7), Live-Dashboard-Generalüberholung (v3.9), Import-Strategie (v3.10), Aktueller Monat → Monatsberichte (v3.12), Energieprofil-Monatsauswertung (v3.13), Stilllegungsdatum (v3.14), PDF-Anlagendokumentation + Finanzbericht (v3.15).

---

## Weitere Quellen

- **Vollständiger CHANGELOG (technisch):** [CHANGELOG.md auf GitHub](https://github.com/supernova1963/eedc-homeassistant/blob/main/CHANGELOG.md) — alle Bugfixes und Code-Änderungen, auch die nicht-anwender-sichtbaren.
- **GitHub-Releases:** [supernova1963/eedc-homeassistant/releases](https://github.com/supernova1963/eedc-homeassistant/releases) — versionsweise gebündelt mit Zusammenfassung.
- **Issues und Discussions:** [supernova1963/eedc-homeassistant](https://github.com/supernova1963/eedc-homeassistant) — Bugs melden, Features anfragen, Diskussionen mitlesen.
- **Online-Dokumentation:** [supernova1963.github.io/eedc-homeassistant](https://supernova1963.github.io/eedc-homeassistant/) — Web-Variante derselben Hilfe, gut zum Verlinken in Foren.
