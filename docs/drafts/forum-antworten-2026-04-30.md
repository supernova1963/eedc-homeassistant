# Forum-Antworten 2026-04-30 (Drafts, noch nicht publiziert)

Stand: 5 Antworten vorbereitet, Code-Änderungen für #136 + #172 lokal in Working Tree, ungetestet.
Pflege-Logik: Vor Posten Versionsnummer prüfen — Antworten verwenden bewusst „im nächsten Update / nächsten Bündel" statt feste Version.

---

## #136 — detLAN, WP-Starts (Slot 23 + Diskrepanz)

URL: https://github.com/supernova1963/eedc-homeassistant/issues/136

Hi detLAN, danke für die Geduld mit den Detail-Screenshots — die haben jetzt zwei zusammenhängende Effekte greifbar gemacht.

**Diagnose**

Beide Beobachtungen — der fehlende Slot 23:00 im Tagesdetail UND die fehlenden Werte für 29.04. in der Aggregat-Sicht — haben dieselbe Wurzel: zur Berechnung der Stunde 23:00 (also 23:00 → 00:00) **und** des Tages-Counters für 29.04. wird der Snapshot um 00:00 des Folgetages gebraucht. Wenn der fehlt, fehlt beides — die Stunde im Tagesdetail UND der Tageswert in Monat/Cockpit-WP, weil sich die Aggregation auf den Tages-Snapshot stützt.

Fehlen kann er aus zwei Gründen:

1. **Bug in der Live-Vorab-Erfassung um :55** — der Job, der kurz vor Mitternacht den anstehenden 00:00-Snapshot vorzeitig schreibt (Issue #146), ist seit der Einführung still abgestürzt (verlorener `timedelta`-Import). Damit gab es den 00:00-Wert nur, wenn der reguläre :05-Job ihn um 00:05 aus HA Statistics gezogen hat — und das setzt voraus, dass HA's LTS für 00:00 zu diesem Zeitpunkt schon bereit ist.
2. **HA-Statistics-Verzögerung** für Counter ohne `state_class` (vor deinem `customize.yaml`-Eintrag): LTS-Einträge für 00:00 erscheinen manchmal mit Verzögerung, dann liefert der :05-Lookup nichts.

Punkt 1 ist im nächsten Bündel gefixt — der :55-Job läuft wieder und schreibt den 00:00-Slot direkt am Stundenende. Damit ist die Slot-23-Lücke für künftige Tage vom Tisch.

**Für die offenen Tage (28.–29.04.)**

Magst du im nächsten Update einmal in **Auswertung → Energieprofil → Datenverwaltung** den Knopf „Verlauf nachrechnen" (oder die Per-Tag-Reaggregation für 28./29.04.) drücken? Damit wird `aggregate_day` neu aufgerufen — und weil HA inzwischen die LTS-Einträge nachgepflegt hat, sollten die fehlenden Snapshots beim erneuten Lauf gefunden und Slot 23 + Tageswerte rückwirkend gefüllt werden. Falls einzelne Tage trotzdem leer bleiben, gibst du Bescheid — dann ist es eine reine LTS-Lücke, die HA selbst nicht mehr nachträglich liefern kann.

---

## #172 — detLAN, PV-Komponenten Layout

URL: https://github.com/supernova1963/eedc-homeassistant/issues/172

Mockup verstanden — du wolltest **Module und Speicher nebeneinander** statt untereinander, dann wirken Karten-Höhe und Inhalt ausgewogener. Im nächsten Update sind die beiden Sub-Sektionen in einem 2-Spalten-Grid angeordnet (Desktop), auf Smartphone-Breite weiterhin gestapelt. Schau dir's bitte nochmal an, wenn das Update bei dir aufschlägt — falls du noch was nachjustieren willst (z.B. Spalten-Verhältnis, Reihenfolge), gerne hier melden.

---

## #175 — detLAN, Auf-/Zuklappen + Sortierung in andere Ansichten

URL: https://github.com/supernova1963/eedc-homeassistant/discussions/175

Berechtigte Anfrage — die Funktion ist heute lokal in Monatsberichte verdrahtet, kein wiederverwendbares Bauteil. Eingeplant fürs nächste Bündel: Section-Header mit ↑↓-Knöpfen + Collapse-Toggle als allgemeine Komponente extrahieren und in PV-Anlage / Speicher / Wärmepumpe / Wallbox / E-Auto anwenden. Der Sektions-Aufbau ist in jedem Cockpit etwas anders, deshalb wird's pro Cockpit ein eigener Mini-Cut — ich melde mich, wenn ein erster Stand drin ist und du das probehalber sortieren kannst.

---

## #174 — JanKgh, SolarEdge-Import

URL: https://github.com/supernova1963/eedc-homeassistant/discussions/174

Hi /jk, willkommen — und danke für das Test-Angebot, ich nehme es gerne an. Drei Antworten zu deinen drei Punkten:

**(1) SolarEdge-Portal-Connector** — den habe ich tatsächlich auf API-Doku-Basis implementiert, ohne dass je ein Tester mit Solaredge-Anlage damit live war. Dass Claude da was *„herbeifantasiert"* hat, ist eine ehrliche Möglichkeit — danke dass du das so direkt sagst. Wenn du mir mal in einer separaten Discussion oder per PN den Fehler beschreibst (welche Maske, welche Meldung, welcher API-Key-Bereich „energyDetails" o.ä.), kriegen wir das gemeinsam zum Laufen. Bei Solcast und EU Oil Bulletin sind die Connector-Iterationen so entstanden, das funktioniert.

**(2) „Alle Monate löschen"-Button** — dein Backup-vor-dem-Test/Restore-Workflow ist eigentlich genau die richtige Lösung dafür: in Datenverwaltung → Backup eine leere Anlage anlegen, dann ist der Wiederanfang ein One-Click. Bevor wir einen dedizierten „alles wegwerfen"-Knopf einbauen (mit allen Confirm-Dialogen, die so was braucht, damit es nicht versehentlich getroffen wird), würde ich erstmal bei dem Restore-Pfad bleiben.

**(3) CSV-Template — fehlende PV-Gesamt-Spalte** — das löst sich über die Investitions-Hierarchie statt über das Template selbst. Wenn du eine zusätzliche Investition vom Typ **„PV-Module"** mit deiner Gesamt-kWp anlegst (z.B. „PV-Anlage gesamt", optional einem WR zugeordnet oder ohne), dann generiert das Template automatisch eine Spalte mit dieser Bezeichnung — und du trägst da deinen monatlichen Gesamt-PV-Wert aus dem Portal ein. Die String-/Modul-Aufteilung kannst du weglassen, wenn du sie eh nicht hast. Damit bleibt der Datenfluss konsistent (alles geht über `InvestitionMonatsdaten`), und im Cockpit erscheint deine PV-Anlage als ein Block.

Zur generellen Architektur-Frage „SolarEdge-Daten vs. OpenWB direkt" hast du eigentlich schon die richtige Aufteilung gewählt: Erzeugung/Akku aus dem Portal (saubere Counter-Werte), E-Auto-Ladung aus der OpenWB. Das sollte funktionieren — sobald (1) durch ist.

---

## #173 — detLAN, Kompressor-Starts Baseline

URL: https://github.com/supernova1963/eedc-homeassistant/discussions/173

Sauberer Vorschlag, danke. Aktuell zählt EEDC die Kompressor-Starts ab dem Moment der Sensor-Aktivierung über Snapshot-Differenzen, weshalb die historischen Starts deines Nibe-Sensors (der ja schon eine hohe Lebensdauer-Zahl hat) im Cockpit-WP-„Σ Lebensdauer" nicht erscheinen.

Plan fürs nächste Bündel: für die Cockpit-Anzeige „Σ Lebensdauer" wird direkt der **aktuelle Sensor-Wert** angezeigt (z.B. die echten 5234 Starts deines Sensors), nicht die Aufsummierung aus EEDC's Tagesdifferenzen seit Aktivierung. Das ist genau die Baseline-Idee, nur ohne neues Feld in der Maske — der Sensor *ist* schon die Baseline. Tageswerte (Max/Tag, Σ-Monat) bleiben weiterhin Snapshot-basiert, weil die Hersteller-Counter da keinen historischen Tagesschnitt liefern.

Manuelles Override-Feld bauen wir nur, wenn jemand einen Sensor hat, dessen Counter falsch resettet ist — bei dir reicht der Sensor-Live-Wert vermutlich aus. Du sagst aber gerne Bescheid, falls deine 5234 Starts irgendwo nicht korrekt rauskommen.

---

## Code-Stand fürs nächste Bündel

| Datei | Änderung | Status |
|---|---|---|
| `eedc/backend/services/scheduler.py` | `timedelta` zu Import hinzugefügt (Fix #136 :55-Preview-Crash) | uncommitted |
| `eedc/frontend/src/pages/PVAnlageDashboard.tsx` | Module + Speicher 2-Spalten-Grid (#172) | uncommitted, ungetestet |

**Offen für nächstes Bündel:**
- #175: SortableSection extrahieren (Section-Logik aus `MonatsabschlussView.tsx:100-238`) → `components/ui/SortableSection.tsx` → in 5–7 Cockpits anwenden
- #173: PVAnlageDashboard / WaermepumpeDashboard zeigt für „Σ Lebensdauer Kompressor-Starts" den HA-Live-Sensor-Wert statt Aufsummierung der Tagesdifferenzen. Erfordert HA-State-Lookup im WP-Dashboard-Endpoint (analog zu Live-State-Service in `ha_state_service.py`).
- #136 (Folge): Self-Healing für `get_snapshot` bei tag_ende = 00:00 Folgetag stabilisieren — z.B. zweiter Recovery-Versuch um 02:00 oder erhöhte HA-Toleranz beim Tageswechsel-Lookup. Aktuell nur :55-Preview gefixt.
- #174 (1): Solaredge-Connector mit JanKgh durchgehen, sobald er Fehlerdetails liefert.
