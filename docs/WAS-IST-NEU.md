# Was ist neu

> **Stand:** Mai 2026 (v3.30.2)
> **Diese Seite** zeigt pro Version, was sich für dich als Anwender geändert hat — kürzer als der technische [CHANGELOG](https://github.com/supernova1963/eedc-homeassistant/blob/main/CHANGELOG.md), ausführlicher als die Schnellübersicht-Tabelle in der [Übersicht](BENUTZERHANDBUCH.md#was-ist-neu-seit-v316).
>
> **Kein Banner, kein Pop-up:** eedc zeigt diese Liste nicht ungefragt an. HA-App-Nutzer sehen den Changelog ohnehin schon im Add-on-Store, GitHub-Releases haben einen eigenen. Wer wissen will, was neu ist, schaut hier rein — Pull statt Push.
>
> **Lesehinweis:** Die jüngsten Versionen stehen oben. Jeder Punkt verlinkt entweder auf die zuständige Hilfe-Sektion oder direkt auf die App-Funktion (sofern erreichbar). Anker-URLs (`?doc=was-ist-neu`) sind teilbar.

---

## v3.30.x — Prognosequellen-Wahl, Strompreis-Vorschlag, Counter-Spike-Schutz (Mai 2026)

### PV-Counter-Spike-Cap *(v3.30.2)*

> 🛡️ **Schluss mit „die Reparatur ändert nichts".** Wenn der HA-PV-Zähler nach einem Neustart einen unsinnigen Stunden-Sprung hatte (z. B. +109 kWh in einer Stunde bei einer 11-kWp-Anlage), wurde dieser Spike bisher vom Daten-Checker zwar *erkannt*, aber „Tag neu aggregieren" hat ihn nicht geheilt — Reaggregation lieferte denselben falschen Wert. Ab v3.30.2 cappt der Aggregator solche Stundenwerte präventiv.

#### Was sich für dich ändert

- **Stundenwerte > kWp × 1,5 werden zur Datenlücke**. Beispiel bei einer 11,2 kWp-Anlage: alles über 16,8 kWh in einer einzelnen Stunde gilt als Counter-Off-by-one und wird in `TagesEnergieProfil` als Lücke (—) gespeichert statt als Spike. Heatmap, Lernfaktor und Monatsbericht zeigen die Lücke ehrlich statt einen physikalisch unmöglichen Wert mitzuschleppen.
- **„Tag neu aggregieren" funktioniert jetzt auch bei Counter-Spikes**. Wer einen Spike in der Vergangenheit hat: **Wartung → Reparatur-Werkbank → Tag neu aggregieren** für den betroffenen Tag — die Werkbank zeigt jetzt eine echte Änderung statt „0 Slots geändert".
- **Anlagen ohne hinterlegte PV-Leistung** sind nicht betroffen — ohne kWp-Angabe kann eedc keine sinnvolle Schwelle ableiten. Der Stammdaten-Check erinnert ohnehin separat daran.

*(Forum-Beitrag #529, dietmar1968.)*

---

### Prognosequellen-Wahl pro Anlage *(v3.30.0 / v3.30.1)*

> ☀️ **Drei PV-Prognosequellen zur Auswahl.** Jede Anlage kann jetzt entscheiden, welche Quelle sie als Tagesprognose hernimmt — und Auto-Discovery erkennt die installierten Integrationen automatisch.

#### Was sich für dich ändert

- **Drei Optionen in den Anlagen-Einstellungen**:
    - **eedc-optimiert** (Standard, Empfehlung): OpenMeteo × anlagenspezifischer Lernfaktor — funktioniert überall, auch standalone, lernt mit der Zeit aus deinen eigenen IST-Werten.
    - **Solcast** (pur): Satellitenbasierte Prognose direkt, ohne eedc-Korrektur. Ideal für alle, die Solcast schon nutzen und der Quelle vertrauen.
    - **Solar Forecast ML** (pur): ML-basierte Prognose direkt aus der HA-Integration, ohne eedc-Korrektur. Nur im HA-Add-on verfügbar.
- **Auto-Discovery**: Wenn du Solcast oder Solar Forecast ML in HA installiert hast, erkennt eedc die Sensoren automatisch — kein Sensor-Mapping mehr im Wizard nötig.
- **Solcast Standalone**: Wer eedc als Docker-Container ohne HA betreibt, kann den Solcast-API-Token + Resource-IDs direkt im Sensor-Mapping-Wizard eintragen.
- **Quellen-Hinweis im Dashboard**: WetterWidget und Live-Dashboard zeigen die aktive Quelle an (nur bei Nicht-Default-Wahl). Wenn die gewählte Quelle ausfällt (Solcast-Quota leer, SFML-Sensor unbekannt), erscheint ein Amber-Hinweis und eedc fällt automatisch auf den eedc-Standard zurück.
- **Lernfaktor O12 ist jetzt der Live-Default** statt einer Diagnose-Option: Der verbesserte Lernfaktor mit Recency-Boost und Trim-Mean (über extreme Tage drüber). Der alte Legacy-Skalar dient nur noch als Fallback und Vergleichs-Wert im Log.
- **Migration alter Einstellungen**: Wer früher `prognose_basis=solcast` gesetzt hatte (Solcast als eedc-Basis), wird automatisch auf `prognose_quelle=solcast` (Solcast pur) migriert.

#### Was sich *nicht* ändert

- **Wer nichts ändert, bekommt eedc-optimiert** — die bewährte Standardwahl mit Lernfaktor. Keine Aktion nötig.
- **Kein Quellenvergleich mehr in Aussichten → Prognosen**: Die alte SFML-Vergleichs-Tabelle/Chart-Spalte entfällt zugunsten der direkten Wahl. Prognosen-Tab bleibt als reine eedc-Diagnose-Sicht (OpenMeteo vs. eedc-kalibriert vs. Solcast vs. IST).

---

### Verbrauchsgewichteter Ø-Strompreis im Monatsabschluss *(v3.30.1)*

> 💶 **Bei dynamischen Tarifen rechnet eedc jetzt mit.** Wer Tibber, aWATTar oder einen anderen stündlich variablen Tarif nutzt: Der Wizard schlägt im Monatsabschluss ab jetzt den verbrauchsgewichteten Monats-Durchschnittspreis vor — aus den über den Monat gesammelten Stundendaten.

#### Was sich für dich ändert

- **Im Monatsabschluss-Wizard**: bei dynamischen Tarifen erscheint der vorgeschlagene Wert direkt mit einer **Konfidenz-Staffelung** (je nachdem, wie viele Stunden im Monat mit Preisdaten abgedeckt sind — voll, teilweise, dünn).
- **Berechnung**: `Σ(strompreis_cent × netzbezug_kWh)` ÷ `Σ(netzbezug_kWh)` über den Monat — also nicht der arithmetische Stundenmittelwert, sondern der tatsächlich-bezahlte Schnitt. Wer abends viel bezieht, sieht den Abendpreis stärker gewichtet.
- **Fallback bleibt**: Wer keine Stunden-Mitschrift hat (kein Strompreis-Sensor gemappt), bekommt wie bisher den aktuellen HA-Sensor-Momentanwert — nur mit reduzierter Konfidenz und einem Hinweis.

*(stlorenz + Joachim-xo, Issue #250 + #122 vandecook.)*

---

### „Database is locked"-Reparatur *(v3.30.1)*

> 🔓 **SQLite-Journal auf WAL umgestellt.** Wer parallel zur Add-on-UI noch andere Schreibvorgänge laufen hatte (MQTT-Inbound, Background-Aggregator, Wizard), bekam gelegentlich „database is locked"-Fehler. Mit Write-Ahead-Logging + 10-Sekunden-Timeout warten parallele Writer jetzt aufeinander statt sofort abzubrechen.

*(PR #248, @stlorenz.)*

---

## v3.29.x — Aggregations- und UX-Bündel (Mai 2026)

### Vorab-Fixes vor Menüstruktur-Konzept *(v3.29.2)*

> 🧹 **Stall ausmisten vor dem großen Konzept.** Kleine UX-Fehler und Schreibweisen-Drift, die nicht auf das künftige Menüstruktur-Konzept warten sollten. Kein neuer Funktionsumfang.

#### Was sich für dich ändert

- **Komponenten-Beiträge zur Finanzierung — Reihenfolge und Icons konsistent**. In **Aussichten → Finanzen** stehen die Komponenten-Beiträge ab jetzt in derselben Reihenfolge wie überall in der App: Speicher → Wärmepumpe → Wallbox/E-Auto-Cluster → Sonstiges. Vorher stand die Wärmepumpe hinter dem E-Auto, und drei Beitragstypen („WP-PV-Nutzung", „WP-Ersparnis vs. Gas/Öl", „E-Auto vs. Benziner") zeigten als Icon einen Batterie-Fallback — jetzt das passende WP-Flammen- bzw. Tank-Icon. Die kleine 4-Kacheln-Zusammenfassung darunter (Speicher EV+ / V2H / E-Auto-PV-Ladung / WP-PV-Direkt) folgt derselben Reihenfolge. *(detLAN, Issue #210.)*
- **Auswertungen: dekoratives Kalender-Icon vor dem Jahres-Filter entfernt**. Genau das gleiche Phänomen, das schon im Cockpit-Banner gefixt war: ein nicht-klickbares Kalender-Icon stand direkt neben dem Jahres-Dropdown — verwirrt, weil's aussieht wie ein Knopf, ist aber keiner. Weniger ist mehr. *(detLAN, Issue #206 P2-Folge.)*
- **Schreibweise „eedc" jetzt durchgängig kleingeschrieben** — passend zum Logo und zur seit v3.26.7 angefangenen Linie:
    - **In der App**: Browser-Tab-Titel, „Erstellt mit eedc"-Footer in Share-Texten, PDF-Bericht-Titel („eedc Anlagenbericht …"), Neustart-Bestätigungs-Meldung, HA-Verbindungsfehler.
    - **In MQTT-Discovery**: HA-Devices erscheinen ab jetzt unter „eedc - <Anlagenname>" statt „EEDC - <Anlagenname>". Entity-IDs bleiben gleich (`sensor.eedc_*`) — keine Daten-Migration nötig, kein Re-Mapping in Dashboards.
    - **Im HA-Sensor-Export-YAML**: die generierten Sensor-Friendly-Names heißen ab jetzt „eedc <SensorName>" statt „EEDC <SensorName>". Wer das Snippet manuell in seine `configuration.yaml` übernommen hat: Nichts brennt, aber für Konsistenz das Snippet aus *Einstellungen → HA-Export* neu kopieren.
    - **In allen Hilfe-Dokumenten**: ~130 Stellen Inline-Erwähnungen umgestellt. Formel-Variablen (z. B. `EEDC_Prognose` in den Berechnungs-Formeln) und historische Env-Var-Namen bleiben in Code-Form unangetastet.

  *(detLAN, Issue #206 P4 — Hilfe-Sweep der noch ausstand seit v3.26.7.)*

#### Was sich *nicht* ändert

- **Funktional ändert sich nichts.** Reine Reparatur-/Polish-Welle.
- **Keine ID-Migration bei MQTT- oder Sensor-Export-Nutzern.** Nur Anzeige-Namen.
- **Code-Identifier und Formel-Variablen** wie `EEDC_ENERGIEPROFIL_QUELLE` (historisches Feature-Flag) oder `EEDC_Abweichung` (Berechnungs-Variable) bleiben — das sind keine Marken-Erwähnungen.

---

### Anschaffungsdatum-Komplettierung + UX-Cluster *(v3.29.1)*

> 🪛 **Tester-Welle vom 13./14. Mai gebündelt geschlossen.** detLAN-Folge zu #236 mit zwei zusätzlichen Pfaden, JanKgh-Multi-String-Verteilungsbug, fünf UX-Verbesserungen. Kein neuer Funktionsumfang.

#### Was sich für dich ändert

- **Wärmepumpe / Speicher / E-Mobilität / Balkonkraftwerk / Sonstiges**: in Monaten vor Anschaffungsdatum wird die Sektion im Monatsbericht jetzt komplett ausgeblendet — kein leerer Block mehr mit „—" überall. Zwei zusätzliche Pfade zu v3.29.0 wurden geschlossen: Sektions-Sichtbarkeit + HA-Sensor-Aggregation respektieren jetzt ebenfalls das Anschaffungsdatum. *(detLAN, Issue #239.)*
- **„—" einheitlich für leere Felder**: an manchen Stellen wurde „---" (drei Bindestriche), an anderen „—" gezeigt — jetzt überall einheitlich „—". *(detLAN, Issue #239.)*
- **Modul-Verteilung bei SolarEdge-Multi-String-Setups**: Wer mehrere PV-Modul-Investitionen mit unterschiedlicher kWp pflegt (z. B. Ost/West-Aufteilung) und die Anlagengesamterzeugung aus einem Wechselrichter-Sensor importiert, sah bisher eine Gleichverteilung (1/N je Modul) statt anteilig nach Modulleistung. Der Verteilungs-Algorithmus liest die kWp jetzt primär aus der Tabellen-Spalte (sauberer Source of Truth) und fällt nur als Fallback auf das Parameter-JSON zurück. Wirkt im CSV-Import und im HA-Live-Datenstrom gleichermaßen. *(JanKgh, Diskussion #229.)*
- **Einstellungen → Allgemein und Protokolle**: zwei weitere überflüssige Page-Überschriften entfernt. In den Protokollen sitzen „Debug" und „Neustart" jetzt in der gleichen Reihe wie die Sub-Sub-Tabs „System-Logs / Aktivitäten" — eine gemeinsame Toolbar statt zwei getrennter Header-Zeilen. Bonus für alle Einstellungs-Seiten: gleichmäßiger Abstand zwischen Sub-Tabs und erstem Inhalt (vorher war der zu eng). *(detLAN, Issue #233.)*
- **Cockpit → Wärmepumpe: kWh-Einheiten überall**. Tabellen-Header („Strom (kWh)" usw.), Wärme-Verteilung Summary und der Wärmeerzeugung-pro-Monat-Chart (Y-Achsen-Beschriftung + Tooltip-Einheit) zeigen jetzt durchgehend die Einheit. *(detLAN, Issue #237.)*
- **Daten-Checker: keine „3× Vorjahr"-Warnung mehr, wenn die Anlage im Vorjahresmonat erst in Betrieb genommen wurde**. Beispiel: Anlage seit Ende März 2022 → März 2022 hat nur ein paar Tage Daten, der März-2023-Vergleich (3× höher) ist deshalb kein Anomaliefall. *(NongJoWo, Issue #240.)*
- **Cockpit → Übersicht → Energie-Bilanz → PV-Monatserträge**: der Mouseover-Tooltip zeigt jetzt den Monatsnamen („Mär 22" / „Jan 26") statt der fortlaufenden Nummer. *(NongJoWo, Issue #241.)*

---

### Fünf Reparaturen + ein UX-Fix in der Vorschau *(v3.29.0)*

> 🪛 **Tester-Welle vom 12./13. Mai gebündelt geschlossen.** Fünf Bugfixes aus detLAN- und NongJoWo-Meldungen plus ein UX-Fix in „Eigene Dateien". Kein neuer Funktionsumfang.

#### Was sich für dich ändert

- **Anschaffungs- und Stilllegungsdatum greifen jetzt überall in den Auswertungen.** Wer für eine Investition (z. B. Wärmepumpe, Speicher, Wallbox) ein Anschaffungsdatum hinterlegt hat, sah trotzdem in einigen Auswertungs-Ansichten Werte aus Monaten *vor* der Anschaffung — typischerweise wegen versehentlich erfasster Vor-Anschaffungs-Sensordaten. Der Filter wirkt jetzt einheitlich über 13 Read-Sites (Cockpit-Übersicht, Komponenten-Tab, Aktueller Monat, Aussichten, Investitionen-Dashboards, Aggregierte Monatsdaten, HA-Sensor-Export, PDF-Jahresbericht, PV-Strings, Nachhaltigkeit, Sozial-Bilanz). Außerdem unterscheidet die API jetzt sauber zwischen `0` (Komponente aktiv, Wert echt 0 — z. B. Wärmepumpe im Sommer) und `—` (Komponente in dem Monat nicht aktiv). Bonus: die JAZ-Kachel im Wärmepumpen-Dashboard zeigt jetzt den tatsächlichen WP-Datenbereich („2025-2026") statt den Anlagen-weiten Zeitraum. *(detLAN, Issue #236.)*
- **Live-Heute zeigt korrekte Werte, wenn dein Energiezähler in Wh meldet.** Wer einen Energiesensor mit Einheit `Wh` statt `kWh` gemappt hatte, sah heute morgen in den Live-Heute-Kacheln Werte mit Faktor 1000 zu hoch (z. B. 87.000 statt 87 kWh) — der Wh→kWh-Konverter fehlte in einem Statistics-Pfad. Behoben — der gleiche `_is_energy_sensor`-Check, der schon im Sensor-Mapping-Wizard und im Live-Pfad greift, ist jetzt auch im Statistics-Fallback aktiv. *(NongJoWo, Issue #232.)*
- **Wallbox + E-Auto: keine Doppelzählung mehr in Auswertungen → Komponenten.** Wenn du eine Wallbox und ein E-Auto unabhängig in eedc führst und beide denselben Stromfluss aus unterschiedlichen Perspektiven messen (Loadpoint-Seite + Vehicle-Seite), wurden die Werte bisher in „Auswertungen → Komponenten" addiert — PV-Anteil konnte > 100 % anzeigen. Backend führt jetzt eine Max-Pool-Logik pro Monat (analog zu „Aktueller Monat") — die größere Quelle gewinnt, Dienstwagen werden ohnehin ausgeschlossen. Km und V2H bleiben vom E-Auto, Wallbox kennt das nicht. *(NongJoWo, Issue #231.)*
- **Reparatur-Werkbank: „Plan erstellen" verschwindet nicht mehr nach erfolgreichem Lauf.** Nach einem Tag- oder Range-Lauf wurden die Steuerelemente in der Werkbank weiter ausgeblendet — neuer Plan war nur mit Modal-Schließen-Öffnen erreichbar. Der UI-State setzt sich jetzt nach Abschluss eines Laufs sauber zurück. *(detLAN, Issues #234 + #235.)*
- **„Eigene Dateien" — Vorschau zeigt die automatisch erkannten Investitions-Spalten als Tabellen-Spalten.** Wer eine CSV mit ausschließlich Investitions-Spalten (z. B. nur E-Auto-Ladewerte) importieren wollte, sah in der Vorschau eine Tabelle voller „—" — die Spalten wurden korrekt erkannt, aber die Werte tauchten in der Vorschau-Tabelle nicht auf, sondern erst nach dem eigentlichen Import. Jetzt rendert die Tabelle die Investitions-Spalten zusätzlich zu den fünf Standard-Spalten dynamisch — der „nicht sichtbar"-Banner-Text entfällt. *(NongJoWo, Issue #222.)*

#### Was sich *nicht* ändert

- **Reine Reparatur-/Polish-Welle.** Keine neuen Konzepte, keine Schema-Updates über das `AggregierteMonatsdatenResponse`-Nullable hinaus.
- **Bestehende Workflows bleiben gleich.** Wer keinen der genannten Pfade nutzt, merkt nichts vom Release.
- **Vollbackfill bleibt additiv** (siehe v3.25.3) — kein Massenheiler-Knopf hier dazugekommen.

---

## v3.28.x — Mehrere Tage neu aggregieren (Mai 2026)

### Reparatur-Werkbank: Zeitbereich-Reaggregation *(v3.28.0)*

> 🪛 **Neue Reparatur-Operation für mehrere Tage am Stück.** Bisher konnte die Reparatur-Werkbank Tagesprofile nur Tag für Tag neu aggregieren — für einen größeren Zeitraum hieß das viele Einzelklicks. Jetzt gibt es eine Mehrere-Tage-Variante mit Datums-Bereich und Pflicht-Bestätigung, weil pauschale Reparatur-Knöpfe mit Datenverlust-Risiken einhergehen können und das transparent kommuniziert werden soll. Auslöser war Martins Anregung in #230.

#### Was sich für dich ändert

- **Neue Operation „Mehrere Tage neu aggregieren" in der Reparatur-Werkbank.** Du wählst Start- und Enddatum (max. 31 Tage pro Lauf), entscheidest ob Snapshots pro Tag frisch aus HA-Statistics gezogen werden sollen (Default an), und haakst die Pflicht-Bestätigung. Die Operation läuft seriell pro Tag — bei Abbruch (Netz, Browser zu, Worker-Restart) sind die bereits verarbeiteten Tage drin, der Rest unverändert.
- **31 Tage als Maximum pro Lauf** — bewusst eng gesetzt: ein längerer Lauf wäre Black-Box-Verhalten ohne Zwischen-Feedback, ein Abbruch in Stunde 5 weniger ärgerlich als in Stunde 1. Für größere Zeiträume (z. B. komplettes Vorjahr) einfach mehrere 31-Tage-Schübe hintereinander.
- **Prognosen und Korrekturprofil-Daten bleiben erhalten.** Pro Tag rettet der Mechanismus die PV-Prognose, SFML-Prognose, Solcast-Prognose und die gefrorenen Day-Ahead-Stundenprofile (die seit v3.26.0 die Datenbasis für das Korrekturprofil-Lernen sind) — sie werden nach der Neu-Aggregation zurückgeschrieben. Diese Werte stammen aus Live-Endpoints und wären sonst nicht rekonstruierbar.
- **Explizite Bestätigung „ohne Support-Anspruch".** Vor dem Plan-Erstellen muss eine Pflicht-Checkbox angehakt werden: Per-Feld-Provenance älterer Verfahrensläufe wird überschrieben, MQTT-Only-Felder und Strompreis-Sensor-Werte ohne HA-LTS-Pendant gehen verloren falls vorhanden. Wir wollen, dass dieser Knopf bewusst gedrückt wird, nicht versehentlich.

#### Was sich *nicht* ändert

- **Bestehendes „Tag neu aggregieren" bleibt unverändert.** Der Einzeltag-Pfad ist weiterhin der konservative Default für punktuelle Reparatur.
- **Vollbackfill bleibt strikt additiv** (siehe v3.25.3). Bereits vorhandene Tage rührt er nicht an — wer einen Tag *überschreiben* will, nutzt den neuen Mehrere-Tage-Pfad.
- **Kein automatisches Pauschal-Heilen.** eedc bietet weiterhin keine „heile alles"-Funktion an — die neue Operation ist Power-User-Werkzeug mit klarer Auswirkung auf einen begrenzten Zeitraum, nicht der Universal-Reset-Knopf.

---

## v3.27.x — Reparatur-Werkbank und Daten-Schutz (Mai 2026)

### UX-Konsistenz-Cluster + PV-Ertrag-Spalte *(v3.27.5)*

> 🪛 **Anwender-gemeldete UX-Verbesserungen aus dem detLAN-Cluster** plus eine Spalten-Erweiterung von dietmar1968. Kein neuer Funktionsumfang — fünf koordinierte Detail-Verbesserungen, die in Summe die Konsistenz spürbar anziehen.

#### Was sich für dich ändert

- **„PV-Ertrag" als neue Spalte in „Auswertungen → Energieprofil → Tagesübersicht".** Tages-Summe der PV-Erzeugung über alle Anlagen-Komponenten (PV-Module + Balkonkraftwerk), default eingeblendet wie die anderen Tages-Summen-Spalten (Überschuss/Defizit). Wer den Spalten-Selektor angepasst hatte, bekommt die neue Spalte automatisch dazu — die eigenen Anpassungen bleiben erhalten. *(Dank an dietmar1968.)*
- **Live-Ansicht: zwei Animationen weg.** Der pulsierende grüne Punkt links und der Refresh-Spinner rechts im Live-Header machten auf schmalen Fenstern unruhige Layout-Sprünge — der Update-Timestamp zeigt eh, wann zuletzt aktualisiert wurde. Statischer Live-Punkt bleibt als Online-Indikator, jetzt neben der Update-Zeile statt auf der anderen Seite. *(Mehrere Tester hatten das in unterschiedlichen Worten gemeldet — Rainer per PN, dietmar1968 im Forum, detLAN als GitHub-Issue.)*
- **Überflüssige Überschriften in Einstellungen entfernt.** „Anlagen", „Strompreise", „Investitionen", „Sensor-Zuordnung", „HA-Statistik Import" und „HA-Sensor-Export" wiederholten den Sub-Tab-Namen direkt darunter — überall weg, der Sub-Tab benennt den Bereich. Bei MQTT-Export war die alte Überschrift „HA-Sensor-Export" zudem irreführend (Sub-Tab heißt „MQTT-Export"); die Info-Box darunter erklärt das schon. Plus: Sub-Tab Singular „Anlage" heißt jetzt korrekt „Anlagen". *(detLAN.)*
- **Vier Aktualisieren-Buttons als Schaltfläche statt nackter Icon.** In Solarprognose-Setup, Daten-Checker, MQTT-Export und System-Einstellungen ist der Refresh-Knopf jetzt ein vollwertiger grauer Button mit Icon + „Aktualisieren"-Label — konsistent zu „+ Neue Anlage", „+ Neuer Tarif" etc., nicht mehr fünf verschiedene Stile in einer App. *(detLAN.)*
- **Komponenten-Reihenfolge in Community vereinheitlicht.** An vier Stellen (Community → Statistiken Ausstattung + Quoten-Cards, Community → Übersicht Komponenten-Benchmarks, Community → Komponenten Deep-Dives) war die Reihenfolge teils Wallbox-vor-E-Auto, teils E-Auto-vor-Wallbox, und Balkonkraftwerk landete oft ans Ende. Jetzt überall einheitlich: Speicher → Balkonkraftwerk → Wärmepumpe → Wallbox → E-Auto (eedc-Standard-Sortierung). *(detLAN.)*

#### Was sich *nicht* ändert

- **Keine funktionalen Änderungen, keine Schema-Updates, keine Konzept-Etappe.** Wer keine der genannten Ansichten regelmäßig nutzt, merkt nichts vom Release.

---

### Wärmepumpen-Aggregation für getrennte Strommessung *(v3.27.4)*

> 🪛 **Zwei strukturelle Lücken im Wärmepumpen-Stundenpfad behoben**, beide aus Martins Forum-Befund.

#### Was sich für dich ändert

- **Wärmepumpe-Spalte in der Stundenwerte-Tabelle wird befüllt, wenn du Strom Heizen und Strom Warmwasser getrennt erfasst.** Wer im Sensor-Mapping die seit v3.25.x verfügbare Option "Getrennte Strommessung" gewählt hat und zwei Stromsensoren für Heizung und Warmwasser gemappt hatte, sah im Live-Tagesverlauf eine korrekte WP-Kurve, aber in „Auswertungen → Energieprofil → Tagesdetail" blieb die Wärmepumpe-Spalte leer und die Heatmap zeigte für die WP nichts. Der stündliche Snapshot-Mechanismus kannte die getrennten Feldnamen nicht und hat sie ignoriert. Behoben — beide Felder werden jetzt regulär stündlich aufgezeichnet und in der Stundenwerte-Tabelle als Wärmepumpen-Verbrauch summiert. **Damit Bestandstage rückwirkend korrekt erscheinen, einmal über Auswertungen → Energieprofil → Datenverwaltung → "Vollbackfill" laufen lassen**: HA-Statistics hat die Historie, eedc holt die fehlenden Snapshots nach.
- **WP-Kompressor-Starts: kein einzelner Unsinns-Wert mehr in der Stunden-Detail-Tabelle.** Wenn der Tagestab 0 WP-Starts für einen Tag zeigt, aber die Stunden-Detail-Tabelle in einer einzelnen Stunde dann z. B. 49.073 stehen hat, ist das kein realer Wert sondern ein bekannter HA-Statistics-Bug (`sum=NULL` direkt nach HA-Restart, der `state`-Fallback liefert den Lebensdauer-Zählerstand). eedc filtert solche Spikes jetzt im Stunden-Pfad heraus (Plausibilitäts-Schwelle: > 200 Starts/h sind physikalisch ausgeschlossen). Sobald du den Tag über die Reparatur-Werkbank reaggregierst, ist die Anzeige bereinigt. *(Dank an MartyBr für die scharfe Beobachtung mit Screenshots.)*

#### Was sich *nicht* ändert

- **Reines Aggregations-Fix.** Keine neuen Funktionen, keine Schema-Änderungen. Wer keine getrennte Strommessung für die WP nutzt und auch sonst keine WP-Starts-Anomalien gesehen hat, merkt nichts vom Release.

---

### Folge-Päckchen Tester-Bugs *(v3.27.3)*

> 🪛 **Reaktion auf v3.27.2-Feedback + drei frische Bug-Meldungen.** Rainer und NongJoWo hatten gemeldet, dass die v3.27.2-Fixes ihre Probleme nicht gelöst hatten — diesmal mit Backend-Logs bzw. Datei-Anhang, sodass die tatsächlichen Pfade gefunden werden konnten. Plus drei neue Issues von JanKgh und NongJoWo. Alles Polish, kein neuer Funktionsumfang.

#### Was sich für dich ändert

- **CSV-Export funktioniert auch mit Sonderzeichen im Anlagenname.** Wer als Browser-Fehler "Failed to fetch" gesehen hat, obwohl der Server in den Logs ein sauberes HTTP 200 OK zeigte, hatte vermutlich Leerzeichen, Umlaute oder andere Sonderzeichen im Anlagenname — die landeten ungefiltert in einem HTTP-Header und der Browser-Fetch hat den Stream als ungültig abgebrochen. Backend sanitisiert den Namen jetzt vor dem Header (Umlaute → ae/oe/ue, Sonderzeichen → _) und quotet den Filename korrekt. *(Dank an rapahl für die ausführlichen Backend-Logs.)*
- **"Eigene Dateien" — Vorschau erkennt automatisch zugeordnete Investitions-Spalten.** Bisher meldete die Vorschau "Keine gültigen Monatsdaten", wenn deine CSV-Datei nur Jahr/Monat plus Spalten enthielt, die eedc automatisch einer E-Auto- oder Wallbox-Investition zuordnen würde (Suffix-Match auf den csv_suffix in den Felddefinitionen). Beim eigentlichen Import hätten sie sauber gelandet — die Vorschau wusste nur nichts davon. Jetzt prüft sie die gleiche Auto-Erkennung wie der Apply-Pfad und zeigt einen klaren Hinweis "X Investitions-Spalten automatisch erkannt". *(Dank an NongJoWo mit Test-CSV.)*
- **Datenchecker mahnt keine Batterie-Daten für Monate vor der Batterie-Installation an.** Wer eine PV-Anlage vor der Batterie hatte (typisch: PV 2021, Speicher 2022 oder später) bekam für jeden Vor-Anschaffungs-Monat eine Warnung "Batterie-Ladung nicht erfasst" — was per Definition nicht erfasst werden konnte. Der Datenchecker respektiert jetzt Anschaffungs- und Stilllegungsdatum pro Speicher. *(Dank an JanKgh.)*
- **Tagesverlaufsgrafik addiert Wallbox und E-Auto nicht mehr doppelt.** Wenn deine Wallbox und das E-Auto unabhängig in eedc angelegt sind und beide denselben Leistungs-Sensor nutzen (typisch bei "Wallbox misst Ladung am Stecker, E-Auto-App misst die gleiche Leistung von der anderen Seite"), wurden bisher beide getrennt im Tagesverlauf gestackt — Σ Verbrauch um die Fahrzeug-Ladung zu hoch. Backend dedupliziert jetzt automatisch: wenn zwei Investitionen dieselbe Entity teilen, wird die Wallbox bevorzugt, das E-Auto entfällt. Sauberer Weg bleibt: Fahrzeug-Investition öffnen → "Gehört zu Wallbox" → Wallbox auswählen — damit der bestehende parent-basierte Schutz greift. *(Dank an JanKgh mit Tooltip-Screenshot.)*
- **Vollzyklen pro Monat zeigt wieder einen runden Wert.** Im Cockpit → Speicher → "Vollzyklen pro Monat"-Diagramm zeigte der Tooltip Werte wie "10.5252891704708..." statt "10,5". Ein Edge-Case in der Tooltip-Komponente hat die Nachkommastellen-Vorgabe verschluckt, sobald keine Einheit dabei war. Behoben. Bonus: deutsches Komma-Trennzeichen wird in Chart-Tooltips jetzt durchgängig verwendet, auch wenn die Zahl ohne Einheit angezeigt wird. *(Dank an NongJoWo.)*

#### Was sich *nicht* ändert

- **Keine Funktionen verändert.** Reines Bugfix-Päckchen ohne neue Konzepte oder Architektur-Etappen.

---

### Tester-Bugfix-Päckchen *(v3.27.2)*

> 🪛 **Drei Anwender-gemeldete Bugs hintereinander erledigt.** Patch-Päckchen ohne neue Funktionen — repariert nur, was eine kaputte oder irreführende Anzeige produziert hat.

#### Was sich für dich ändert

- **Der „Daten exportieren"-Button funktioniert wieder.** Wer als Browser-Fehler „Failed to fetch" beim CSV-Export gesehen hat, war von einem stillen Backend-Crash betroffen: Sonderkosten oder sonstige Positionen, die irgendwann mal als Text (z. B. `"150,00"` mit Komma) statt als Zahl gespeichert wurden, haben den Export-Endpoint abrupt abbrechen lassen. Der Export verträgt jetzt sowohl klassische Zahlen als auch Komma-Schreibweise und fällt im Zweifel sicher auf 0 zurück, statt komplett zu kippen. *(Dank an rapahl für die scharfe Bug-Beschreibung mit Screenshot.)*
- **„Eigene Dateien" — Import-Vorschau mit klarerer Fehlermeldung und ohne Falsch-Alarm.** Wer im Mapping-Wizard E-Auto- oder Wallbox-spezifische Slots manuell zugeordnet hat (die sonst automatisch erkannt werden), bekam bisher die unverständliche Meldung „Keine gültigen Monatsdaten mit diesem Mapping gefunden". Die Vorschau akzeptiert diese Doppel-Zuordnung jetzt und sagt dir transparent: „X Spalte(n) als Investitions-Daten gemappt — werden beim Import automatisch zugeordnet". Falls es doch ein echtes Format-Problem ist (Datums-Format wird nicht erkannt oder Punkt/Komma vertauscht), nennt die Meldung die konkrete Verdachtsursache statt nur „prüfe Jahr/Monat". *(Dank an NongJoWo für das ausführliche Issue.)*
- **Monatsbericht → Finanzen: PV-Eigenverbrauch-Ersparnis ohne Doppelzählung der Wallbox-PV-Ladung.** Im T-Konto war der Posten „PV-Eigenverbrauch-Ersparnis" bisher zu hoch, weil die Wallbox-PV-Ladung sowohl dort als auch separat im Posten „Wallbox — PV-Ladung-Ersparnis" gerechnet wurde. Σ Haben war damit um diesen Betrag überhöht und das Monatsergebnis entsprechend zu optimistisch. Bei einer 150-kWh-Wallbox-PV-Ladung typische Korrektur ≈ 45 €/Monat nach unten. *(Dank an NongJoWo für den Hinweis mit Tooltip-Vergleich — ohne den wäre der Bug wahrscheinlich noch lange unter dem Radar geblieben.)*

#### Was sich *nicht* ändert

- **Keine Funktionen verändert.** Wer den Export nicht nutzt, kein Custom-Import macht und in den Monatsberichten keine Wallbox-PV-Ladung pflegt, merkt nichts vom Release.

---

### UX-Sprint und Power-Sensor-Bug *(v3.27.1)*

> 🪛 **Bugfix-Release zwischen den Etappen.** Bündelt UX-Quick-Wins aus dem detLAN-Cluster (Tab-Style einheitlich als Schaltfläche, kompakteres Cockpit-Banner, konsistente Komponenten-Reihenfolge mit Wärmepumpe vor Wallbox) und einen Datenintegritäts-Bug, den rcmcronny gemeldet hatte: Leistungs-Sensoren ließen sich versehentlich als kWh-Tageswert eintragen — die Live-Heute-Anzeige zeigte dann mal 0, mal 1000+ kWh.

#### Was sich für dich ändert

- **Power-Sensor schützt sich jetzt selbst.** Wer im Sensor-Mapping einen Leistungs-Sensor (Einheit W/kW) versehentlich in einen kWh-Slot wie „Netzbezug Tageswert" einträgt, bekommt im Wizard direkt eine Warnung „Einheit XXX passt nicht in einen kWh-Slot" mit Wegweiser auf den richtigen Slot („Live-Sensoren / Aktuelle Leistung"). Falls der Sensor schon eingetragen war: der Live-Heute-Pfad ignoriert ihn jetzt für die Tagessumme und rechnet stattdessen aus dem Wattverlauf — physikalisch korrekt. Vorher kam es bei dieser Konstellation zu unsinnigen Werten.
- **Tab-Leisten in Auswertungen, Aussichten, Community jetzt als Schaltflächen** statt Unterstrich. Konsistenter Look mit dem Sensor-Mapping-Wizard und der Cockpit-Sub-Navigation. Aktiver Tab in Akzentfarbe, inaktive in dezentem Grau — leichter erfassbar, gerade auf kleinen Bildschirmen.
- **Cockpit Top-Banner kompakter.** Das große Home-Icon ist weg, Anlagenname und kWp stehen jetzt inline statt zweizeilig. Das nutzlose Calendar-Icon vor dem Jahres-Filter ist auch weg — es war nicht klickbar (im Gegensatz zum Share-Button daneben), das war verwirrend.
- **Daten → Monatsdaten ohne Überschrift, Selektoren in einer Zeile.** Die „Monatsdaten"-Überschrift wiederholte den Hauptmenü-Titel — weg. Anlage-Selektor verschwindet automatisch, wenn du nur eine Anlage hast. Mehr Platz für die eigentlichen Daten.
- **„Erstellt mit eedc" jetzt auch in der kompakten Share-Variante.** Bisher war der Hinweis nur im ausführlichen Teilen-Text — jetzt konsistent in beiden, am Ende des Texts.
- **Wallbox vor E-Auto** in der Community-Übersicht („Stärken/Schwächen"-Reihen + Komponenten-Tab + Empty-State). Spiegelt den Anwender-Workflow: Ladeinfrastruktur vor Fahrzeug.
- **Wärmepumpe vor Wallbox** im Daten-Checker. Die Anomalie-Liste pro Komponente folgt jetzt einer einheitlichen Reihenfolge (Wechselrichter → PV-Module → Speicher → Balkonkraftwerk → Wärmepumpe → Wallbox → E-Auto → Sonstiges) statt der zufälligen DB-Reihenfolge.
- **Jahresübersicht in Community → PV-Ertrag absteigend** (neueste oben).
- **Wallbox-Card im Dark Mode hat wieder einen sichtbaren Rahmen.** Bei der Komponenten-Übersicht in Community → Statistiken war die Wallbox-Card im dunklen Modus rahmenlos (CSS-Build-Falle); jetzt sauber mit Cyan-Akzent wie die anderen Cards.
- **Performance-Profil Radar-Chart: Community-Linie jetzt in Amber statt Grau.** Die alte graue Linie verschmolz mit den grauen Gitterlinien des Charts — jetzt klar erkennbar.
- **Plural-Bug „1 Hinweise" / „1 Warnungen" gefixt.** Steht jetzt korrekt „1 Hinweis" / „1 Warnung".
- **Übernehmen-Knopf im Monatsabschluss-Wizard rückt neben das Eingabefeld** statt darüber — die Spinner-Pfeile am Number-Input sind dadurch nicht mehr verdeckt.
- **Doppeltes Info-Icon in Aussichten → Prognosen** entfernt.
- **Auto-Fill für die Ø-Außentemperatur im Monatsabschluss-Wizard.** Wenn das Feld leer ist und die Wetter-Daten verfügbar sind (Bright Sky oder Open-Meteo Archive), füllt eedc den Wert direkt vor — du musst ihn nur prüfen oder bewusst überschreiben.

#### Was sich *nicht* ändert

- **Funktionsumfang bleibt identisch.** Es ist ein Bugfix- und UX-Polish-Release — keine neue Architektur-Etappe, keine neuen Konzepte. Was du bisher gewohnt bist, funktioniert weiter wie zuvor.

→ [Auswertung → Energieprofil](HANDBUCH_BEDIENUNG.md#42-auswertung) · [Cockpit](HANDBUCH_BEDIENUNG.md#41-cockpit)

---

### Daten-Provenance & Reparatur-Werkbank *(v3.27.0)*

> 🛠 **Architektur-Etappe 3d sichtbar als zwei neue Anwender-Funktionen:** eine zentrale Reparatur-Werkbank ersetzt die verstreuten Schnellbuttons, und manuell gepflegte Werte werden jetzt automatisch vor Cloud-/Portal-Import geschützt. Dazu wurde unter der Haube eine Quellen-Hierarchie eingeführt, die jeder Schreiber respektieren muss — keine stillen Überschreibungen mehr.

#### Was sich für dich ändert

- **Reparatur-Werkbank** im Energieprofil unter „Datenverwaltung". Du wählst eine Operation (z. B. *Heute neu aggregieren*, *Vollbackfill*, *Cloud-Import-Werte zurücksetzen*) und siehst **vor** dem Klick auf „Anwenden" eine Vorschau-Tabelle mit jeder Feld-Änderung — gruppiert pro Datensatz, mit Sticky-Header. Erst der Bestätigungs-Knopf „N Änderungen anwenden" schreibt etwas. Der Vorgang lässt sich nach 30 Sekunden über einen Cancel-Knopf abbrechen, das Verlauf-Akkordeon zeigt, was du bisher angewendet hast inklusive Audit-Log-Counter. Die alten Schnellbuttons (Aggregat heute / Vollbackfill / etc.) bleiben als Wrapper bestehen — wer sie gewohnt ist, drückt sie einfach weiter.
- **Manuell gepflegte Werte überleben Cloud- oder Portal-Import.** Wer einen Wert im Monatsabschluss-Wizard eingetragen oder per CSV-Backup wiederhergestellt hat, war bisher der Willkür des nächsten Cloud-Apply ausgeliefert: ein „Überschreiben"-Klick im Wizard zog auch manuell gepflegte Werte mit. Ab v3.27.0 schützt eine Quellen-Hierarchie die manuellen Werte automatisch — der Cloud-Apply gibt anschließend zurück „X Felder durch manuelle Werte geschützt — Reset über Reparatur-Werkbank wenn gewollt". Du siehst also explizit, was nicht überschrieben wurde, und kannst es bewusst über die Reparatur-Werkbank zurücknehmen, falls du den Cloud-Wert doch willst.
- **Daten-Checker zeigt Provenance-Konflikte.** Wenn ein Cloud-Import versucht hätte, einen manuellen Wert zu überschreiben, und das blockiert wurde, taucht das in der Anlagen-Diagnose als neuer Befund `PROVENANCE_CONFLICT` auf. Hilft, Drift zwischen Cloud-Quelle und manueller Pflege zu sehen, bevor sie zu einer Vertrauensfrage wird.
- **Pool-Doppelzählung bei E-Auto + Wallbox im Cockpit + Monatsbericht weg.** Wer 1 E-Auto + 1 Wallbox erfasst hatte, sah teils E-Mob-PV-Anteil > 100 % (mathematisch unmöglich, aber Folge davon dass Vehicle und Loadpoint denselben Stromfluss aus zwei Perspektiven messen). Saubere Trennung pro Fahrzeug folgt erst mit Phase 2 des Wallbox/E-Auto-Konzepts (eigene Vehicle-Sensor-Zuordnung).

#### Was sich *nicht* ändert

- **Tagesgesamt-Werte und Heatmaps bleiben unverändert.** Die Etappe ist eine Architektur-Konsolidierung der Schreib-Pfade — sie aggregiert nicht neu und verwirft nichts. Nur die Schreib-Reihenfolge bei mehreren Quellen pro Feld ist jetzt explizit geregelt.
- **Manuelle Eingabe geht weiter wie bisher.** Du musst keine Reparatur-Werkbank öffnen, um einen Wert einzugeben — der Monatsabschluss-Wizard und das direkte Bearbeiten in der Anlagen-Sicht bleiben unverändert.
- **Bestandsdaten gehen nicht verloren.** Beim ersten App-Start nach Update werden vorhandene Werte einmalig als Quelle „Legacy unbekannt" markiert. Sie bleiben sichtbar und nutzbar; jeder neue Schreiber gewinnt automatisch gegen sie.
- **Cloud-Import-Buttons bleiben sichtbar und nutzbar.** Sie laden weiter Werte — die Hierarchie greift nur, wenn du an derselben Stelle bereits einen manuellen Wert hast. Bei leeren Feldern landet der Cloud-Wert wie zuvor direkt.

→ [Auswertung → Energieprofil → Datenverwaltung](HANDBUCH_BEDIENUNG.md#42-auswertung)

---

## v3.26.x — Wetter-Stratifizierung und Lernfaktor-Diagnose (Mai 2026)

### Architektur-Konsolidierung Etappe 3c — Konsistenz-Fixes unter der Haube *(v3.26.8)*

> 🧱 **Architektur-Etappe sichtbar nur als saubereres Verhalten.** Vier strukturelle Aufräum-Päckchen am Energieprofil-Datenpfad: Slot-Ausrichtung, Tagessumme HA-konform, Snapshot-Herkunft trackbar, Reaggregat-Modal mit klar getrennten Aktionen. Kein neuer Knopf, keine neuen Konzepte — die Selbst-Heilung aus v3.26.6 ist jetzt strukturell abgesichert statt heuristisch.

#### Was sich für dich ändert

- **WP-Kompressor-Starts-Heatmap wandert beim ersten Start um eine Stunde nach rechts — das ist Absicht, kein Bug.** Wer WP-Kompressor-Starts erfasst (seit v3.24.0 möglich), wird nach dem Update einmalig sehen, dass die gewohnte Stundenverteilung in der Heatmap um eine Spalte verschoben ist. Was vorher in Stunde 6 stand (Aktivität *zwischen* 06:00–07:00), steht ab jetzt in Stunde 7 — derselbe Wert, andere Spalte. Die Verschiebung gleicht den Counter-Pfad an die kWh-Heatmap an, die schon seit v3.20.0 die HA-übliche Backward-Konvention nutzt (Slot N = Aktivität *zwischen* (N−1):00 und N:00, [#144](https://github.com/supernova1963/eedc-homeassistant/issues/144)). Vorher waren beide Heatmaps eine Stunde gegeneinander verschoben — jetzt symmetrisch. **Tagessumme der Kompressor-Starts ändert sich nicht.** Die Migration läuft beim ersten App-Start einmalig und automatisch (idempotent über interne `migrations`-Tabelle), keine User-Aktion nötig.
- **eedc-Tagessummen für Komponenten-Energien entsprechen ab jetzt exakt dem HA Energy Dashboard.** Für Wallbox / WP / BKW / E-Auto / Speicher wird die Tageszahl ab jetzt aus Tagesanfang/Tagesende-Zählerdiff gerechnet — derselbe Pfad, den auch HA selbst nutzt. Bei normalen Anlagen ohne Sensor-Lücken praktisch identisch zur alten Stundensummen-Variante; bei Anlagen mit Sensor-Resets oder Spike-Korrekturen kann es geringfügig anders aussehen — und genau dort ist der neue Wert der konsistente. Greift für *neue* Aggregate (heute und morgen); historische Tagessummen bleiben unverändert, können aber bei Bedarf über den Reaggregate-Knopf pro Tag nachgezogen werden.
- **Reaggregate-Modal mit zwei klaren Aktions-Buttons.** Statt einem „Übernehmen"-Knopf zeigt das Vorschau-Modal jetzt *Snapshots neu holen + Tagesaggregat rechnen* (vollständiger Resnap) und *Nur neu rechnen* (wenn die Snapshots längst stimmen). Die Auto-Erkennung aus v3.26.6 macht den Default-Knopf vor — du kannst aber jetzt explizit überschreiben (z. B. nach Sensor-Tausch, wenn Snapshots ungeprüft erscheinen). Cancel-Knopf erscheint, wenn der Resnap länger als 30 Sekunden braucht.
- **Vorbereitung Daten-Herkunft sichtbar machen** (Schablone für Etappe 3d). Jeder gespeicherte Sensor-Schnappschuss trägt ab jetzt einen Quelle-Marker (HA-Statistics / MQTT-Inbound / MQTT-Live / Live-Fallback / Unknown für historische Snapshots). Sichtbar wird das später in der Datenverwaltungs-Seite — als Vorlage für Konflikt-Auflösung zwischen Cloud-Import, manueller Eingabe und Auto-Aggregation in Etappe 3d.

#### Was sich *nicht* ändert

- **Tagessumme der Kompressor-Starts bleibt unverändert** — die kommt aus einem eigenen Pfad, der schon vorher korrekt war (Tagesanfang/Tagesende-Counter-Diff). Nur die Stundenverteilung in der Heatmap wandert um eine Spalte.
- **Werte gehen nicht verloren.** Slot-Wert-Anzahl bleibt gleich; an Stellen, wo bei der neuen Konvention ein Snapshot-Boundary fehlt, wird ein Slot leer — an genau einer anderen Stelle als vorher (NULL-Slots wandern mit, die Anzahl bleibt).
- **Historische komponenten_kwh-Tagessummen werden nicht stillschweigend umgeschrieben.** Der Reaggregate-Knopf pro Tag liefert auf Wunsch den HA-konformen Boundary-Diff-Wert.
- **Resnap-Backend war seit v3.26.6 schon da.** Was neu ist, ist die UX-Trennung im Frontend — die `mit_resnap=true/false`-Auswahl gab es serverseitig schon.

→ [Auswertung → Energieprofil](HANDBUCH_BEDIENUNG.md#42-auswertung)

### UX-Bündel aus Forum-Beobachtungen *(v3.26.7)*

> ✨ **Vier kleine UX-Verbesserungen aus aktiven Tester-Anfragen, in einem Patch zusammengefasst.**
>
> - **Live-Heute Batterie-Pfeile** zeigen jetzt in dieselbe Richtung wie das HA Energy Dashboard: ▼ wenn Strom in den Speicher rein, ▲ wenn raus. Vorher umgekehrt (Tank-Metapher), das hat verwirrt. (#201)
> - **Schreibweise „eedc" durchgängig** (statt gemischt eedc/eedc), und **„Home Assistant Add-on" → „Home Assistant App"**, wo es um eedc selbst geht. HA-eigene Menü-Pfade („Einstellungen → Add-ons → ⋮") bleiben natürlich — das heißt in HA wirklich so. (#199)
> - **Redundante Seitentitel entfernt** im Cockpit, in Auswertungen, Aussichten, Live-Daten, Community-Vergleich und mehreren Einstellungs-Seiten. Da die Top-/Sub-Navigation immer sichtbar ist, war die zusätzliche `<h1>` direkt darunter eine reine Doppelung. Pages mit dynamischem Untertitel (Anlagenname etc.) bleiben unverändert. (#196)
>
> Alle drei UX-Punkte kommen aus detLAN-Feedback. Auch Ronnys gemeldete „Live-Netzbezug zu hoch"-Anomalie (#200) ist code-seitig bereits seit v3.26.6 gefixt — die Verifikation läuft.

### Hotfix: Wetter-Backfill schließt jetzt auch die letzten 5 Tage *(v3.26.4)*

> 🩹 **Hotfix wenige Stunden nach v3.26.3** — der „Wetter-Historie nachladen"-Button hat die letzten 5 Tage strukturell ausgelassen, weil Open-Meteo Archive sie wegen 2–5 Tage Reanalyse-Lag nicht hat. Per Designkommentar sollten diese Tage über den Live-Forecast-Pfad mitkommen, taten es aber nicht — also blieb die „5 Tage noch nicht geladen"-Meldung dauerhaft sichtbar und ein erneuter Klick lieferte „0 Stunden / 0 Tage geladen". Verständlich verwirrend.
>
> Jetzt holt der Backfill zwei Range-Calls: Open-Meteo Archive für ältere Tage, Open-Meteo Forecast (mit Reanalyse-Approximation für die Vergangenheit) für die jüngsten Tage. Der nächtliche Tagesabschluss-Aggregator (`aggregate_day`) verwendet denselben Routing-Cutoff. Damit ist die Lücke der letzten 5 Tage strukturell geschlossen — Empty-State-Ghost und „0 geladen" sollten nach einem Klick verschwinden.

→ [Aussichten → Prognosen-Vergleich](HANDBUCH_BEDIENUNG.md#43-aussichten)

### Hotfix: Korrekturprofil-Skalar wirkt sofort, auch ohne Stundenprofile *(v3.26.3)*

> 🩹 **Hotfix wenige Stunden nach v3.26.2** — der Aggregator hat „Keine Day-Ahead-Snapshots im Zeitraum" zurückgemeldet, sobald das stündliche Day-Ahead-Profil (`pv_prognose_stundenprofil`, erst seit v3.26.0 mitgeschrieben) im Auswertungsfenster noch leer war. Bestehende Anlagen haben Tages-Prognose schon seit Monaten — die Skalar-Stufe hätte ab Tag 1 verfügbar sein müssen, war aber wegen meiner zu strikten Voraussetzung gesperrt. Damit fiel der Live-Pfad weiter auf den Legacy-Lernfaktor zurück, statt auf das neue Korrekturprofil.
>
> Jetzt schreibt der Aggregator den Skalar unabhängig vom Stundenprofil; Sonnenstand- und Wetter-Bins bleiben leer, solange die Stundenprofile reinwachsen — und füllen sich automatisch über die nächsten Wochen. Die Heatmap-Card erklärt das jetzt explizit, wenn nur die Skalar-Stufe vorhanden ist.

→ [Aussichten → Prognosen-Vergleich](HANDBUCH_BEDIENUNG.md#43-aussichten)

### Päckchen 2: Stündliches Korrekturprofil scharf *(v3.26.2)*

> ✨ **Das stündliche Korrekturprofil aus dem Päckchen-1-Konzept ist jetzt produktiv.** Pro Stunde wird die OpenMeteo-Strahlung mit einem Faktor multipliziert, der von Sonnenstand (Azimut × Elevation) *und* Wetterklasse abhängt — also zum Beispiel "Süd-Mittag bei klarem Himmel" anders als "West-Nachmittag bei diffuser Bewölkung". Damit fängt die Live-Prognose Verschattungs- und Wetter-Asymmetrien strukturell ein, die ein einziger Anlagen-Skalar nicht trennen kann.

#### Was sich für dich ändert

- **Live-Strahlung wird pro Stunde individuell korrigiert.** Bisher wurde der Lernfaktor (z. B. ×0.97) gleichmäßig auf alle Stunden multipliziert. Ab v3.26.2 ermittelt eedc für jede Stunde Sonnenstand-Bin (10° × 10°) und Wetterklasse, und greift den Korrekturfaktor aus dem über die Anlage gelernten Profil. Effekt sichtbar im Live-Dashboard und in der Tagesrest-Prognose: Stunden mit Verschattung oder schwacher Wetterleistung kriegen einen passenderen Faktor als Stunden ohne.
- **Heatmap im Prognosen-Vergleich-Tab.** Eine neue Card zeigt das gelernte Korrekturprofil als Tabelle (Azimut horizontal, Elevation vertikal, Farbe = Faktor) — pro Wetterklasse umschaltbar plus Fallback-Sicht ohne Wetter-Achse. Macht sichtbar, welche Sonnenstand-Bereiche bei welcher Wetterlage über- oder unterschätzt werden.
- **Sanftverlauf für neue oder datenarme Anlagen.** Ein Sonnenstand-Bin braucht mindestens 10 Stunden Datenbestand, um produktiv genutzt zu werden (Stufe 1: Sonnenstand × Wetter), bzw. 15 Stunden ohne Wetter-Achse (Stufe 2). Reicht das nicht, fällt eedc automatisch auf den klassischen Skalar-Lernfaktor zurück — neue Anlagen merken zunächst nichts und bauen ihr Profil organisch auf.
- **Nightly Aggregator.** Das Profil wird täglich um 02:30 frisch gerechnet aus Day-Ahead-Snapshots + IST-Stunden + Wetter-Historie. Manuelles "Neu aggregieren" ist über den Button in der Heatmap-Card jederzeit möglich.

#### Was sich *nicht* ändert

- **Solcast-Spalte und alle bisherigen Cards bleiben unverändert.** Die Heatmap kommt additiv unter den vorhandenen Diagnose-Cards.
- **Anlage ohne Day-Ahead-Snapshots oder Koordinaten** → Aggregator wird übersprungen, Live-Pfad bleibt auf dem klassischen Skalar.
- **Tagesrest-Pfad konzeptionell wie bisher:** eedc fragt frische Forecasts und multipliziert mit dem Faktor — neu ist nur, dass der Faktor jetzt pro Stunde aus dem Profil kommt statt einem globalen Skalar.

→ [Aussichten → Prognosen-Vergleich](HANDBUCH_BEDIENUNG.md#43-aussichten)

### Hotfix: Wetter-Backfill-Button erscheint jetzt zuverlässig *(v3.26.1)*

> 🩹 **Hotfix wenige Stunden nach v3.26.0** — der Empty-State mit dem "Wetter-Historie nachladen"-Button blieb auf vielen Anlagen unsichtbar, weil meine ursprüngliche Trigger-Bedingung an einem Datenfeld hing (`pv_prognose_stundenprofil` aka Day-Ahead-Snapshot), das auf länger laufenden Anlagen lückenhaft gefüllt ist. Damit war das Hauptfeature von v3.26.0 für viele praktisch unsichtbar. Jetzt erscheint der Button, sobald irgendwo in den letzten 90 Tagen Stunden ohne Wetter-Daten vorhanden sind — also überall.
>
> Wenn die Stratifizierungs-Tabelle nach dem Backfill leer bleibt, weil noch keine Day-Ahead-Stundenprofile gespeichert sind, sagt das die Card jetzt explizit — die nachgeladenen Wetter-Daten dienen dann als Vorbereitung für Päckchen 2.

→ [Aussichten → Prognosen-Vergleich](HANDBUCH_BEDIENUNG.md#43-aussichten)

### Päckchen 1: Daten-Layer für stündliches Korrekturprofil *(v3.26.0)*

> ✨ **Vorbereitungs-Release für ein stündliches PV-Korrekturprofil mit Verschattungs- *und* Wetter-Dimension.** Päckchen 1 von zwei: legt die Datenbasis an, baut zwei neue Diagnose-Cards im Prognosen-Vergleich-Tab und verbessert die Lernfaktor-Berechnung statistisch — der Live-Pfad selbst bleibt unverändert. Päckchen 2 (das eigentliche stündliche Korrekturprofil mit Anwendung im Live-Dashboard) folgt nach einer Beobachtungs-Phase.

#### Was sich für dich ändert

- **Stündliches Wetter wird ab sofort mitgespeichert.** Bei jedem Tagesabschluss schreibt eedc zusätzlich Bewölkung (%), Niederschlag (mm) und WMO-Wettercode pro Stunde — kommt aus dem Open-Meteo-Aufruf, den eedc für die Strahlungs-Daten ohnehin macht. Kein neuer API-Call, kein Quota-Verbrauch.
- **Wetter-Historie nachladen (manuell anstoßbar).** Open-Meteo Archive bietet 2 Jahre Historie kostenlos. Wer den vollen Diagnose-Wert direkt sehen will, kann die Historie für seine Anlage einmalig nachladen lassen — ein Klick reicht (siehe Stratifizierungs-Card im Prognosen-Tab).
- **Lernfaktor — Doppel-Variante "O1+O2".** eedc rechnet den Anlage-Skalar (Verhältnis IST/Prognose) ab sofort *zusätzlich* mit zwei statistischen Verbesserungen aus: Trim-Mean (entfernt Ausreißer-Tage durch Sensor-Aussetzer) und Recency-Boost (gewichtet die letzten 30 Tage stärker). **Wichtig:** der Live-Pfad nutzt weiter den klassischen Faktor — die neue Variante läuft parallel und ist nur als Diagnose sichtbar. Erst nach mehrwöchiger Beobachtung wird entschieden, ob sie zum Default wird.
- **Zwei neue Cards im Prognosen-Vergleich-Tab.**
  - *Lernfaktor — Doppel-Variante O1+O2:* zeigt Live-Faktor (Legacy) und O1+O2-Faktor nebeneinander mit Δ-Anzeige. Macht sichtbar, ob die statistische Verbesserung stabil zum Legacy-Wert läuft (Δ &lt; 1 %) oder systematisch nach oben/unten zieht.
  - *Wetter-Stratifizierung:* zeigt MAE/MBE der Day-Ahead-Stundenprognose getrennt nach drei Wetter-Klassen — *klar*, *diffus*, *wechselhaft*. Erst dadurch wird sichtbar, ob die Prognose bei klarem Himmel super läuft und nur bei Schauer-Tagen abweicht (oder umgekehrt). Ohne diese Aufschlüsselung war ein einziger gemittelter Tagesfehler die einzige Sicht.

#### Was sich *nicht* ändert

- **Solcast-Spalte und Tab-Inhalte bleiben** — die Diagnose-Cards sind additiv, nichts wird entfernt oder neu sortiert.
- **Tagesrest-Prognose im Live-Dashboard** läuft genauso wie bisher: aktuelle Open-Meteo-Forecast × Lernfaktor (Legacy). Wird nicht durch die neue O12-Variante beeinflusst.
- **Ohne IST-Vergleich keine Stratifizierung.** Die Wetter-Stratifizierungs-Card erscheint erst, wenn eedc genug Tage mit gleichzeitiger Day-Ahead-Prognose und IST-Stundenwerten gefunden hat — typisch wenige Tage nach Aktivierung.

→ [Aussichten → Prognosen-Vergleich](HANDBUCH_BEDIENUNG.md#43-aussichten)

---

## v3.25.x — Investitions-Parameter aufgeräumt (April–Mai 2026)

### Tab-Bildlaufleiste auf drei Seiten weg *(v3.25.23)*

> 🩹 **Kleine UI-Politur (#193 detLAN)** — Wer die Tab-Header-Zeile auf den Seiten **Auswertungen**, **Aussichten** und **Community** schmal hatte (Smartphone, geteiltes Browser-Fenster, HA Companion-App), sah unter den Tab-Buttons eine permanente graue Bildlaufleiste. Sie ist weg. Die Tabs lassen sich weiterhin horizontal wischen, scrollen oder per Touch/Wheel verschieben — die statische Scrollbar-Spur darunter ist nur kosmetisch entfernt.

→ [Auswertungen](HANDBUCH_BEDIENUNG.md#42-auswertungen) · [Aussichten](HANDBUCH_BEDIENUNG.md#43-aussichten)

### Vollbackfill nur noch additiv + Wärmepumpe-Strom-Splits + Monatsberichte-Scroll *(v3.25.22)*

> ✨ **Vier zusammengehörige Items aus drei Issues** — eines davon eine bewusste Architektur-Korrektur:
>
> - **„Vollbackfill" heißt jetzt „Energieprofil-Lücken nachfüllen" und ist immer additiv.** Die Checkbox „Bestehende Tage überschreiben" und die rote Empfehlungsbox sind weg. Hintergrund: der Überschreiben-Modus war ein Recovery-Tool für die alten Aggregations-Bugs (Off-by-one in den Stunden-Snapshots, Counter-Doppelzählung, Vortag-Boundary). Diese Bugs sind seit v3.25.20 alle gefixt — der Modus richtete inzwischen mehr Schaden an als er verhinderte: HA-LTS reicht in vielen Setups (Recorder-Purge, Sensor-Umbau) kürzer zurück als das gepflegte Profil; „löschen + überschreiben" hat dann Wochen oder Monate Historie unwiederbringlich gelöscht. Wer einen einzelnen Tag verzerrt findet, nutzt jetzt ausschließlich den Reload-Knopf in der Tagestabelle (mit Vorschau vor Übernahme — siehe v3.25.18). (#190)
> - **Vollbackfill-Banner sagt warum nicht alle Tage geschrieben wurden.** Bisher meldete der Erfolgs-Hinweis nur „X von Y Tagen geschrieben" — wer dann nur 79 % sah, dachte an Datenverlust. Tatsächlich wurden Tage ohne HA-Statistics-Werte stillschweigend übersprungen (Sensor existierte noch nicht, HA-Recorder war down). Das Banner zeigt jetzt explizit: „X Tage geschrieben · Y Tage ohne HA-Daten übersprungen · Z Tage bereits vorhanden". (#190 Klausnn)
> - **Monatsbericht: Wärmepumpe-Strom-Aufteilung Heizung/Warmwasser sichtbar.** Wer in der Wärmepumpe-Investition die getrennte Strommessung aktiviert hat, sieht im Monatsbericht jetzt unter „Stromverbrauch" zwei „davon"-Zeilen — Heizung und Warmwasser. Konsistent zur bereits vorhandenen Wärme-Aufteilung darunter. Anlagen ohne getrennte Messung sehen die Zeilen weiter nicht. (#191 rapahl, der war Ideengeber für die getrennte Strommessung)
> - **Monatsbericht: Scroll-Position bleibt beim Monatswechsel.** Wer die Wärmepumpe-Sektion aufgeschlagen hat und auf einen anderen Monat klickt, bleibt jetzt an der Wärmepumpe — die rechte Inhaltsspalte springt nicht mehr ungewollt an den Seitenanfang. Der Sprung an den Seitenanfang bei einem Wechsel des Hauptmenü-Punktes (Cockpit → Aussichten etc.) bleibt natürlich erhalten. (#182 detLAN-Folge zu v3.25.21)

→ [Daten → Energieprofil](HANDBUCH_EINSTELLUNGEN.md) · [Cockpit → Monatsberichte](HANDBUCH_BEDIENUNG.md#41-cockpit)

### Reihenfolge korrigiert + Stammdaten sortiert + Monatsberichte-Spalte bleibt stehen *(v3.25.21)*

> 🩹 **Drei Folge-Items zum gestrigen UX-Bündel** — direkt aus der detLAN-Rückmeldung zu v3.25.19/20:
>
> - **Reihenfolge korrigiert: Wärmepumpe wieder vor Wallbox/E-Auto.** v3.25.19 hatte das Cockpit-Banner-Bild aus #186 falsch gelesen und WB+EAuto vor die WP gestellt. Korrekt ist `PV-Anlage → Speicher → Wärmepumpe → Wallbox → E-Auto` (genau die Reihenfolge im Cockpit-Banner). Wirkt jetzt einheitlich auf Cockpit-Subtabs, Sensor-Mapping-Wizard, Statistik-Import, MQTT-/HA-Sensoren-Export — und neu auch auf **Stammdaten → Investitionen**, das bisher noch eine eigene alte Reihenfolge hatte.
> - **Stammdaten → Investitionen sortiert jetzt sinnvoll.** Innerhalb jeder Typ-Gruppe steht die neueste Anschaffung oben (nach Anschaffungsdatum absteigend). Investitionen ohne hinterlegtes Datum landen am Ende der jeweiligen Gruppe.
> - **Monatsberichte: linke Monats-Spalte bleibt jetzt wirklich stehen.** v3.25.13 hatte einen Wheel-Bubble-Bug behoben, das Verhalten beim Klick auf einen alten Monat blieb aber kaputt — die rechte Inhalts-Spalte verschob sich, ältere Monate (2023) waren ohne Umweg nicht erreichbar. Jetzt ist die Monats-Spalte ein eigener, oben klebender Scroll-Container — ältere Monate erreichst du per Wheel direkt in der Spalte, und die rechte Seite bleibt unverrückbar.
> - **Schreibweise „Gefahrene km"** statt „km gefahren" — wirkt einheitlich im Statistik-Import, in der E-Auto-Σ-Kachel und im Sensor-Mapping.

→ [Cockpit → Monatsberichte](HANDBUCH_BEDIENUNG.md#41-cockpit) · [Stammdaten → Investitionen](HANDBUCH_EINSTELLUNGEN.md)

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

> ⚠ **User-sichtbare Wert-Korrektur** — Nach v3.25.14 meldete detLAN, dass das Cockpit immer noch driftet (146 statt 134 Starts). Statt die Eichungs-Logik noch eine Runde nachzuschärfen, fliegt der ganze Selbstkalibrierungs-Mechanismus raus. Σ Lebensdauer im Cockpit zeigt ab sofort einfach das, was der Hersteller-Sensor sagt — keine Berechnung, keine Eichung, keine Drift-Möglichkeit. Wenn eedc im Lauf der Zeit weniger Tagesinkremente erfasst als der Hersteller intern hochzählt (z. B. wegen Sensor-Aktivierungs-Lücken), bleibt das zwischen den Anzeigen sichtbar: Cockpit zeigt die Hersteller-Wahrheit, Monatsbericht zeigt was eedc erfasst hat. Diagnose ohne versteckte Magic.

Bei reinen MQTT-Standalone-Setups ohne direkten HA-State-Zugriff fällt der Read auf die Statistics- bzw. den jüngsten Snapshot zurück — höchstens eine Stunde alt.

→ [Cockpit → Wärmepumpe](HANDBUCH_BEDIENUNG.md#41-cockpit)

### Tagesdetail-Ansicht: Vor/Zurück-Pfeile zum Blättern *(v3.25.15)*

> ✨ **Sichtbar in Auswertungen → Energieprofil → Tagesdetail** — Neben dem Datums-Eingabefeld stehen jetzt links und rechts kleine Chevron-Buttons (`<` `>`) zum Blättern um einen Tag. Genau das, was die Monats-Ansicht schon hat — die beiden Tabs sind nun symmetrisch in der Bedienung. Der „nächster Tag"-Button wird automatisch deaktiviert, sobald gestern erreicht ist (heute hat noch keinen abgeschlossenen Energieprofil-Tag).

→ [Auswertungen → Energieprofil](HANDBUCH_BEDIENUNG.md#42-auswertungen)

### WP-Kompressor-Starts: Σ Lebensdauer wächst nicht mehr im Tagesverlauf zu hoch *(v3.25.14)*

> ⚠ **User-sichtbare Wert-Korrektur** — Folgebefund zu v3.25.13: nach dem dortigen Wizard-Save-Fix beobachtete detLAN, dass die Σ-Lebensdauer-Anzeige im Lauf des Tages nach oben driftet — bei 7 realen Kompressor-Starts heute zeigte das Cockpit 136 statt 131. Ursache war keine fehlerhafte Sensor-Erfassung, sondern eine doppelte Buchhaltung des heutigen Tages: zum Save-Zeitpunkt floss er bereits in die Baseline-Berechnung ein, später dann nochmal in die Σ-Aggregation. Beide Stellen lasen den heutigen TagesZusammenfassung-Eintrag, der während des Tages aber noch instabil ist (Snapshot-Job läuft stündlich, der Tagesabschluss `morgen 00:00` existiert ja noch nicht).

Fix: heutiger Tag wird konsistent aus der TagesZusammenfassung-Aggregation ausgeschlossen, der heutige Verlauf kommt stattdessen aus einer Live-Hochrechnung (aktueller Hersteller-Counter minus Snapshot vom heutigen Tagesanfang). Σ Lebensdauer bleibt damit jederzeit synchron mit dem WP-Display, ohne im Lauf des Tages zu driften. Tooltip im Cockpit zerlegt die Anzeige jetzt in drei Anteile: Hersteller-Baseline + eedc abgeschlossene Tage + heute live. Gleicher Fix gilt auch für die „Aktueller Monat"-Ansicht.

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

> ⚠ **User-sichtbare Wert-Korrektur** — Wer einen Kompressor-Starts-Sensor seiner Wärmepumpe gemappt hat und die im Sensor-Zuordnung-Wizard gesetzte Baseline (Σ aller Lebensdauer-Starts vor dem ersten Tag bei eedc) erleben möchte, hatte bisher folgendes Problem: jedes Schließen des Investitionen → Wärmepumpe-Dialogs mit „Speichern" — auch ohne irgendeine Datenänderung — setzte die Baseline auf `None` zurück. Cockpit → Wärmepumpe zeigte dann nur die Σ der eedc-Tagesdifferenzen (also die Starts seit Inbetriebnahme), nicht den korrekten `Baseline + Σ Tagesdifferenzen`-Lebensdauer-Wert.

Hintergrund: das Investitionen-Form sammelte beim Speichern nur die im Form sichtbaren Felder ein und sendete das als komplettes neues `parameter`-Objekt ans Backend. Wizard-only-Felder wie `wp_starts_anzahl_baseline`, die der Sensor-Zuordnung-Wizard direkt in `parameter` schreibt aber nirgendwo im Form sichtbar macht, fielen dadurch raus.

Der Fix mergt jetzt das `parameter`-Objekt mit dem bestehenden statt es zu ersetzen — Wizard-Keys bleiben erhalten. **Nach dem Update einmalig Sensor-Zuordnung → Speichern & Abschließen**, dann ist die Baseline neu gesetzt und bleibt von da an stabil.

→ [Cockpit → Wärmepumpe](HANDBUCH_BEDIENUNG.md#41-cockpit)

### Mobile-Ansicht der Monatsberichte vollständig scrollbar *(v3.25.13)*

> ⚠ **Mobile-Sichtbar** — Wer die App auf einem Smartphone oder im DevTools-Mobile-Mode aufruft, kann jetzt mit aufgeklappter Energie-Bilanz auch die Sektionen darunter (Community-Vergleich, Speicher, Wärmepumpe, E-Mobilität, Balkonkraftwerk, Sonstiges) erreichen.

Vorher endete der Scroll-Bereich bei aufgeklappter Energie-Bilanz an der Finanzen-Sektion — alles darunter war zwar im DOM gerendert, aber außerhalb des Layout-Scroll-Bereichs. Auf Desktop war die Ansicht unbeeinflusst, weil dort der Sticky-Sidebar-Layout-Pfad greift.

→ [Cockpit → Monatsberichte](HANDBUCH_BEDIENUNG.md#41-cockpit)

### iOS-Smartphones / kleine Viewports: kein „Durchscrollen" mehr bis zur HA-Titelleiste *(v3.25.13)*

> ⚠ **Mobile-Sichtbar** — Auf iPhone SE und im HA-Companion-WebView konnte die eedc-App so weit nach oben gescrollt werden, dass unter dem Footer eine leere Fläche entstand und nur noch die HA-App-Titelleiste sichtbar blieb. Der eigentliche App-Inhalt war dann oberhalb des Sichtbereichs.

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

Als Übergangslösung nimmt eedc jetzt pro Feld die größere der beiden Quellen als Wahrheit (Loadpoint-Sicht ist üblicherweise inklusiv) und stellt sicher, dass der PV-Anteil mathematisch ≤ 100 % bleibt. Eine saubere Per-Fahrzeug-Trennung folgt mit der Phase 2 des [Wallbox/E-Auto-Datenarchitektur-Konzepts](https://github.com/supernova1963/eedc-homeassistant/blob/main/docs/KONZEPT-WALLBOX-EAUTO.md) — bis dahin bleibt die Cockpit-Gesamtübersicht und der HA-Statistics-/MQTT-Aggregator-Pfad bewusst auf der alten Pool-Logik (sichtbar als Drift-Möglichkeit zwischen Cockpit-Übersicht und Monatsbericht).

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

Ein Lookup-Helfer in eedc's HA-Statistics-Service las den Zählerstand pro Stunde aus der falschen Zeile in HA's Statistik-Tabelle. HA's Konvention ist „last value of the period": die Zeile bei Stunde 11 enthält den Zählerstand AM ENDE der Stunde, also um 12:00 Uhr — wir lasen aber denselben Wert für Stunde 12. Konsequenz: alle Stunden-Werte im Tagesverlauf seit v3.19 (Snapshot-Rework Oktober 2025) waren systematisch um eine Stunde nach hinten verschoben. Bei einer Anlage mit z. B. 9 kWh PV-Erzeugung in der Stunde 11–12 hat eedc diese 9 kWh stattdessen unter „Stunde 12" verbucht — die Tagessumme war richtig, aber die Stundenposition falsch.

Verursacht wurde der Bug durch eine Fehlinterpretation von HA's API-Konvention; maskiert wurde er einerseits dadurch, dass Tagessummen unbeeinflusst sind, andererseits durch HA-Latenz beim hourly-Snapshot-Job (der zufällig oft den korrekten Vorgänger-Slot las, weil die aktuelle Stunde noch nicht finalisiert war). Mit der Phase-1-Erprobung der 5-Min-Snapshots auf Winterborn 2026-05-01 wurde die Diskrepanz erstmals systematisch sichtbar: HA Energy Dashboard zeigte 8,9 kWh für Stunde 11–12, eedc zeigte 10,1 kWh.

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

Wärmepumpen-Hersteller wie Nibe oder Viessmann liefern einen Counter „Kompressor-Starts gesamt" — die echte Lebensdauer-Zahl ab Werks-Inbetriebnahme, oft 4-stellig im Auslieferungszustand. eedc zählt seit v3.24.0 selbst über Snapshot-Differenzen — das hat den 4-stelligen Sockel aber nicht abgebildet, sodass das WP-Cockpit unter „Σ Kompressor-Starts" eine viel zu kleine Zahl zeigte (z. B. 87 statt 5.234). Beim nächsten Speichern im Sensor-Mapping-Wizard eicht eedc die Hersteller-Baseline jetzt einmalig (`baseline = sensor.gesamt − Σ eedc-Tagesdifferenzen seit Anschaffung`) und addiert sie beim Anzeigen wieder dazu. Der Tooltip auf der Kachel zeigt die Zerlegung Hersteller-Baseline + eedc-seit-Aktivierung + höchste Tagessumme. Selbstkorrigierend bei jedem Wizard-Rerun. Issue [#173](https://github.com/supernova1963/eedc-homeassistant/issues/173), detLAN-Vorschlag.

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

Das Benutzerhandbuch ist jetzt direkt in eedc verfügbar — ohne Browser-Wechsel und ohne Ingress-Login-Probleme in der HA-Companion-App. Acht kuratierte Dokumente in drei Kategorien (*Einstieg* / *Handbuch* / *Referenz*), Sidebar am Desktop, Dropdown auf dem Smartphone. URL-Parameter `?doc=<slug>` macht Direktlinks teilbar (z. B. `?doc=bedienung#7-aussichten-prognosen`). Discussion [#130](https://github.com/supernova1963/eedc-homeassistant/discussions/130).

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

Toggle **„Kompakt / Diagnostisch"** in der Genauigkeits-Tracking-Card. Der Diagnostisch-Modus splittet die Streuung pro Quelle (OpenMeteo / eedc / Solcast) in „darüber"-und „darunter"-Boxen — Ø-Über-/Unterschätzung in Prozent plus Anzahl Tage. Damit sichtbar, ob ein systematischer Hebel vorliegt („bei dichten Wolken zu hoch, bei klarem Himmel zu niedrig") oder reine Streuung. Issue [#151](https://github.com/supernova1963/eedc-homeassistant/issues/151).

→ [Bedienung §7.2 Prognosen](HANDBUCH_BEDIENUNG.md#72-prognosen)

### Reparatur-Popover bei IST-Datenlücken im Prognosen-Tab *(v3.23.0)*

Klick auf das ⚠ neben einem Tageswert öffnet jetzt einen Popover statt eines Hover-Tooltips. Inhalt: Liste der fehlenden Stunden, kurze Erklärung, Button **„Tag neu berechnen"** (löst eine Per-Tag-Reaggregation aus) und Fallback-Link zum Sensor-Mapping. Direkter Reparatur-Pfad statt Diagnose-Suche.

### Live-Dashboard: Bilanz-Sortierung & Eigenverbrauchs-Cap *(v3.23.5)*

Tageswerte-Kacheln im Live-Dashboard in Energie-Logik-Reihenfolge: **PV → Batterie → Eigenverbrauch (Quellen-Σ) → Netzbezug → Hausverbrauch → Einspeisung**. Eigenverbrauchs-Quote ist jetzt auf 100 % gecappt (vorher konnten ev/pv > 100 % rechnen, wenn Batterie-Entladung aus Vortagen einfloss). Issue [#157](https://github.com/supernova1963/eedc-homeassistant/issues/157).

→ [Bedienung §2 Live Dashboard](HANDBUCH_BEDIENUNG.md#2-live-dashboard)

---

## v3.22.0 — Genauigkeits-Tracking & Mobile-Layout (April 2026)

### MAE und Bias getrennt ausweisen

Genauigkeits-Tracking zeigt jetzt zwei Kennzahlen pro Quelle: **MAE** (mittlere absolute Abweichung — Streuung) und **MBE** (mittlerer signed Error — systematischer Bias). Bias neutral gefärbt (das Vorzeichen ist Information, nicht Wertung). eedc wird zusätzlich zu OpenMeteo und Solcast bewertet. Spaltenstruktur stabilisiert: kein Spaltenflattern mehr nach Tag 7, gedämpfter Header bei fehlendem Lernfaktor.

### Mobile-Layout-Bündel

Sieben Mobile-Layout-Korrekturen aus detLAN-Bugreport: Cockpit-/Energieprofil-SubTabs scrollen aktiven Tab in den sichtbaren Bereich, Monatsberichte-T-Konto auf Mobile als 2-Spalten-Layout (Label | Wert+VJ+Δ gestapelt), Sticky-Bars über Tabellen-thead, Energieprofil-Subtabs mit `flex-wrap` (umbricht statt rechts rauszulaufen), Aussichten-Langfrist-Steuerung vertikal gestapelt, Tabellen mit vielen Spalten zeigen Querformat-Hinweis. Issue [#149](https://github.com/supernova1963/eedc-homeassistant/issues/149).

### VM/NM-Split an astronomischer Tagesmitte

Tageshälften (Vormittag/Nachmittag) splitten jetzt am Solar Noon (via Equation of Time, je nach Standort und Datum bis ~30 min von 12:00 abweichend) statt hart bei 12:00 Uhr Clockzeit. Slots, die Solar Noon enthalten, werden proportional verteilt.

### Banner: Restzeit bis Lernfaktor-Schwelle

Der Hinweis „eedc-Prognose nicht verfügbar" zeigt jetzt zusätzlich, wie viele Tage bereits gesammelt sind und wie viele bis zur 7-Tage-Schwelle fehlen.

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

Neuer Tab **„Prognosen"** in Aussichten als Evaluierungs-Cockpit für das Zusammenspiel von OpenMeteo, eedc (kalibriert mit Lernfaktor), Solcast und IST. KPI-Matrix Heute/Morgen/Übermorgen mit VM/NM-Split, Stundenprofil-Chart mit p10/p90-Konfidenzband, 24h- und 7-Tage-Vergleichstabellen, Genauigkeits-Tracking. Solcast wird über einen Toggle im Sensor-Mapping-Wizard aktiviert — entweder API-Zugang (Free/Paid) oder via HA-Integration BJReplay. L1/L2-Cache überlebt Neustarts.

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
